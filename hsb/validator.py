"""
hsb/validator.py
Reglas de validación previas a la transformación.
Ningún mensaje inválido se procesa ni se pierde en silencio:
se registra con sus motivos exactos de rechazo.
"""

import re
from typing import Dict, Any, List, Tuple

CIE10_PATTERN = re.compile(r"^[A-Z][0-9]{2}(\.[0-9]{1,4})?$")
LOINC_PATTERN = re.compile(r"^[0-9]+-[0-9]+$")


def validar_mensaje_pre_transformacion(parsed: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Evalúa las reglas de negocio sobre el mensaje parseado.
    Retorna (es_valido, lista_motivos_rechazo).
    """
    motivos: List[str] = []

    # 1. Validación de Sede
    sede = parsed.get("sede_origen")
    if sede is None or sede not in (1, 2, 3):
        motivos.append(f"sede no válida o desconocida ({parsed.get('sede_raw') or sede}): debe ser 1, 2 o 3")

    # 2. Validación de Usuario
    usr = parsed.get("usuario", {})
    doc = str(usr.get("documento_id", "")).strip()

    if not doc:
        motivos.append("documento no puede ser vacío")
    elif not doc.isdigit():
        motivos.append("documento no numérico")
    elif len(doc) < 4 or len(doc) > 15:
        motivos.append(f"documento fuera de rango: tiene {len(doc)} dígitos (debe tener entre 4 y 15 dígitos)")

    nombre = str(usr.get("nombre_completo", "")).strip()
    if not nombre:
        motivos.append("nombre no puede ser vacío")

    sexo = str(usr.get("sexo", "")).strip().upper()
    if sexo not in ("M", "F", "O"):
        motivos.append(f"sexo no válido ('{sexo}'): debe ser M, F u O")

    # 3. Validación de Fecha
    nacimiento = str(usr.get("fecha_nacimiento", "")).strip()
    if not nacimiento:
        motivos.append("fecha de nacimiento no puede ser vacía")

    # 4. Validación de Diagnósticos (CIE-10)
    # Si viene con error explícito de mapeo (ej. desde CSV)
    if parsed.get("dx_local_error"):
        motivos.append(parsed["dx_local_error"])

    diagnosticos = parsed.get("diagnosticos", [])
    for dx in diagnosticos:
        cie10 = str(dx.get("cie10_codigo", "")).strip().upper()
        sistema = str(dx.get("sistema", "")).strip().upper()

        # En HL7: si el sistema es L (local) o el código no cumple formato CIE-10
        if sistema == "L" or not CIE10_PATTERN.match(cie10):
            motivos.append("diagnóstico sin mapeo a CIE-10")

    # 5. Validación de Tecnologías / Observaciones (LOINC)
    tecnologias = parsed.get("tecnologias", [])
    for tech in tecnologias:
        loinc = str(tech.get("loinc_codigo", "")).strip()
        if not LOINC_PATTERN.match(loinc):
            motivos.append(f"código LOINC inválido: '{loinc}'")

    es_valido = len(motivos) == 0
    return es_valido, motivos
