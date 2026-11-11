"""
hsb/validator.py
Reglas de validación ANTES de transformar (guía Fase 3, paso 5).

Rechazo (el mensaje no se entrega y queda registrado con sus motivos):
  - documento solo dígitos, de 4 a 15
  - nombre no vacío
  - sexo M, F u O
  - sede entre 1 y 3
  - fecha de nacimiento válida y no futura; fecha de ingreso válida
  - CIE-10 con formato correcto (y no un código local sin mapear)
  - LOINC con formato correcto

Advertencia (el mensaje sí se entrega): valores opcionales de los 57 campos que no
pertenecen a su dominio; el traductor los omite y aquí quedan anotados.
"""

import re
import datetime
from typing import Any, Dict, List, Tuple

CIE10_PATTERN = re.compile(r"^[A-Z][0-9]{2}(\.[0-9]{1,4})?$")
LOINC_PATTERN = re.compile(r"^[0-9]+-[0-9]+$")


def _fecha_valida(valor: Any, con_hora: bool = False) -> bool:
    s = str(valor or "").strip()
    try:
        if con_hora and "T" in s:
            datetime.datetime.fromisoformat(s.replace("Z", ""))
        else:
            datetime.date.fromisoformat(s[:10])
        return True
    except ValueError:
        return False


def validar_mensaje_pre_transformacion(parsed: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Recibe {sede_origen, usuario, atencion, diagnosticos, tecnologias, ...}. Devuelve (válido, motivos)."""
    motivos: List[str] = []

    sede = parsed.get("sede_origen")
    if sede not in (1, 2, 3):
        motivos.append(f"sede no válida o desconocida ({parsed.get('sede_raw') or sede}): debe ser 1, 2 o 3")

    usr = parsed.get("usuario") or {}
    doc = str(usr.get("documento_id") or "").strip()
    if not doc:
        motivos.append("documento no puede ser vacío")
    elif not doc.isdigit():
        motivos.append("documento no numérico")
    elif not 4 <= len(doc) <= 15:
        motivos.append(f"documento fuera de rango: tiene {len(doc)} dígitos (debe tener entre 4 y 15 dígitos)")

    if not str(usr.get("nombre_completo") or "").strip():
        motivos.append("nombre no puede ser vacío")

    sexo = str(usr.get("sexo") or "").strip().upper()
    if sexo not in ("M", "F", "O"):
        motivos.append(f"sexo no válido ('{sexo}'): debe ser M, F u O")

    nac = usr.get("fecha_nacimiento")
    if not nac:
        motivos.append("fecha de nacimiento no puede ser vacía")
    elif not _fecha_valida(nac):
        motivos.append(f"fecha de nacimiento no válida ('{nac}')")
    elif datetime.date.fromisoformat(str(nac)[:10]) > datetime.date.today():
        motivos.append("fecha de nacimiento en el futuro")

    at = parsed.get("atencion") or {}
    if at.get("fecha_ingreso") and not _fecha_valida(at["fecha_ingreso"], con_hora=True):
        motivos.append(f"fecha de ingreso no válida ('{at['fecha_ingreso']}')")

    if parsed.get("dx_local_error"):
        motivos.append(parsed["dx_local_error"])
    for dx in parsed.get("diagnosticos") or []:
        cie10 = str(dx.get("cie10_codigo") or "").strip().upper()
        if str(dx.get("sistema") or "").upper() == "L" or not CIE10_PATTERN.match(cie10):
            motivos.append("diagnóstico sin mapeo a CIE-10")

    for t in parsed.get("tecnologias") or []:
        if t.get("tipo") == "LABORATORIO" and not LOINC_PATTERN.match(str(t.get("loinc_codigo") or "")):
            motivos.append(f"código LOINC inválido: '{t.get('loinc_codigo')}'")
        if t.get("tipo") == "MEDICAMENTO" and not t.get("descripcion_medicamento"):
            motivos.append("medicamento sin descripción (campo 25)")

    return len(motivos) == 0, motivos


def advertencias(parsed: Dict[str, Any]) -> List[str]:
    """Avisos de traducción que no impiden la entrega (valores fuera de dominio en campos opcionales)."""
    return list(parsed.get("_observaciones") or [])
