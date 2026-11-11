"""
traductor/traductor.py
TRADUCTOR UNIVERSAL de los 57 campos de la historia clínica.

Todas las representaciones pasan por un único REGISTRO CANÓNICO:

    HL7 v2.5 ─┐                         ┌─> filas PostgreSQL (sedes 1 y 3)
    CSV legado ┼─> REGISTRO CANÓNICO ───┼─> documento MongoDB  (sede 2)
    JSON      ─┘    (57 campos)         └─> Bundle FHIR R4     (fhir/normalizer.py)

Registro canónico de UNA atención:
    {
      "usuario":      {...campos 1-15 y 51-57...},
      "atencion":     {...campos 16-24...},
      "tecnologias":  [ {...campos 25-32 (MEDICAMENTO) o resultado LOINC (LABORATORIO)...} ],
      "diagnosticos": [ {cie10_codigo, rol, tipo_diagnostico, orden, ...} ],   # campos 33-39
      "egreso":       {...campos 40-50...},
      "_observaciones": [avisos de traducción]
    }

Historia de un paciente (lo que devuelve cada nodo):
    {"usuario": {...}, "atenciones": [ {...atencion, "tecnologias", "diagnosticos", "egreso"} ]}

Qué campo va dónde lo decide traductor/catalogo_57.py; aquí no hay nombres de columnas
escritos a mano: si cambia el catálogo, cambian todas las traducciones.
"""

import csv
import io
import re
import hashlib
import datetime
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

from traductor.catalogo_57 import (
    CAMPOS_57, TODOS, SEDES, OBLIGATORIOS, Campo, campos_de,
)
from traductor.dominios import normalizar_codigo, etiqueta

CONTENEDORES_PLANOS = ("usuario", "atencion", "egreso")
TABLA_PG = {"usuario": "usuario", "atencion": "atencion", "tecnologia": "tecnologia_salud",
            "diagnostico": "diagnostico", "egreso": "egreso"}

SEDE_POR_CODIGO = {"SEDE1": 1, "SEDE2": 2, "SEDE3": 3, "1": 1, "2": 2, "3": 3,
                   "SINCELEJO": 1, "CARTAGENA": 2, "COROZAL": 3}


def registro_vacio() -> Dict[str, Any]:
    return {"usuario": {}, "atencion": {}, "tecnologias": [], "diagnosticos": [], "egreso": {},
            "_observaciones": []}


# ══════════════════════════════════════════════════════════════════════════
# 1. Conversión de tipos
# ══════════════════════════════════════════════════════════════════════════

def _fecha_iso(valor: Any, con_hora: bool) -> Optional[str]:
    """Acepta YYYYMMDD, YYYYMMDDHHMM[SS], YYYY-MM-DD, ISO 8601 y date/datetime."""
    if valor is None or str(valor).strip() == "":
        return None
    if isinstance(valor, datetime.datetime):
        return valor.replace(tzinfo=None).isoformat(timespec="seconds") if con_hora else valor.date().isoformat()
    if isinstance(valor, datetime.date):
        return f"{valor.isoformat()}T00:00:00" if con_hora else valor.isoformat()
    s = str(valor).strip()
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?", s)
    if m:
        y, mo, d, hh, mi, ss = m.groups()
        fecha = f"{y}-{mo}-{d}"
        return f"{fecha}T{hh or '00'}:{mi or '00'}:{ss or '00'}" if con_hora else fecha
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?.*", s)
    if m:
        fecha, hh, mi, ss = m.groups()
        return f"{fecha}T{hh or '00'}:{mi or '00'}:{ss or '00'}" if con_hora else fecha
    return s  # se deja tal cual para que el validador lo reporte


def convertir(campo: Campo, valor: Any, observaciones: Optional[List[str]] = None) -> Any:
    """Convierte un valor crudo al tipo y código canónico del campo."""
    if valor is None or (isinstance(valor, str) and valor.strip() == ""):
        return None
    if campo.tipo == "fecha":
        return _fecha_iso(valor, con_hora=False)
    if campo.tipo == "fechahora":
        return _fecha_iso(valor, con_hora=True)
    if campo.tipo == "entero":
        try:
            return int(float(str(valor).replace(",", ".")))
        except ValueError:
            if observaciones is not None:
                observaciones.append(f"campo {campo.num or campo.clave}: '{valor}' no es un número")
            return None
    if campo.tipo == "decimal":
        try:
            return float(str(valor).replace(",", "."))
        except ValueError:
            return None
    if campo.tipo == "booleano":
        if isinstance(valor, bool):
            return valor
        return str(valor).strip().upper() in ("S", "SI", "SÍ", "Y", "YES", "1", "TRUE", "VERDADERO")
    if campo.tipo == "codigo" and campo.dominio:
        cod = normalizar_codigo(campo.dominio, valor)
        if cod is None:
            if campo.clave == "sexo":
                # El sexo inválido se conserva crudo: el validador debe rechazar el mensaje con motivo
                return str(valor).strip().upper()
            if observaciones is not None:
                observaciones.append(
                    f"campo {campo.num} ({campo.nombre}): valor '{valor}' fuera del dominio {campo.dominio}; se omite")
        return cod
    return str(valor).strip()


# ══════════════════════════════════════════════════════════════════════════
# 2. Campos derivados (los que la sede no envía pero se pueden calcular)
# ══════════════════════════════════════════════════════════════════════════

def separar_nombre(nombre: str) -> Tuple[str, str]:
    """'Camila Suarez Pineda' -> ('Suarez Pineda', 'Camila'). 'Rojas^Andrea' -> ('Rojas', 'Andrea')."""
    nombre = " ".join(str(nombre or "").split())
    if "^" in nombre:
        partes = [p.strip() for p in nombre.split("^")]
        return partes[0], " ".join(p for p in partes[1:] if p)
    tokens = nombre.split(" ")
    if len(tokens) >= 4:
        return " ".join(tokens[2:]), " ".join(tokens[:2])
    if len(tokens) == 3:
        return " ".join(tokens[1:]), tokens[0]
    if len(tokens) == 2:
        return tokens[1], tokens[0]
    return nombre, ""


def calcular_edad(fecha_nacimiento: Optional[str], referencia: Optional[str]) -> Tuple[Optional[int], Optional[str]]:
    """Edad y unidad (1 años, 2 meses, 3 días) a la fecha de referencia, como pide la Res. 866."""
    try:
        nac = datetime.date.fromisoformat(str(fecha_nacimiento)[:10])
    except (TypeError, ValueError):
        return None, None
    try:
        ref = datetime.date.fromisoformat(str(referencia)[:10]) if referencia else datetime.date.today()
    except ValueError:
        ref = datetime.date.today()
    dias = (ref - nac).days
    if dias < 0:
        return None, None
    anos = ref.year - nac.year - ((ref.month, ref.day) < (nac.month, nac.day))
    if anos >= 1:
        return anos, "1"
    meses = (ref.year - nac.year) * 12 + ref.month - nac.month - (ref.day < nac.day)
    if meses >= 1:
        return meses, "2"
    return dias, "3"


def _id_limpio(texto: Any) -> str:
    return re.sub(r"[^A-Za-z0-9\-.]", "", str(texto))[:60]


def completar_derivados(reg: Dict[str, Any], sede_id: Optional[int] = None) -> Dict[str, Any]:
    """Rellena lo calculable: nombre/apellidos, edad, prestador, ids deterministas, roles de dx."""
    u, a, e = reg["usuario"], reg["atencion"], reg["egreso"]
    sede_id = sede_id or a.get("sede_id") or u.get("sede_origen_id")

    # Nombre completo <-> apellidos / nombres
    if u.get("nombre_completo") and not (u.get("apellidos") or u.get("nombres")):
        u["apellidos"], u["nombres"] = separar_nombre(u["nombre_completo"])
    if u.get("nombre_completo") and "^" in u["nombre_completo"]:
        u["nombre_completo"] = " ".join(x for x in (u.get("nombres"), u.get("apellidos")) if x)
    if not u.get("nombre_completo") and (u.get("apellidos") or u.get("nombres")):
        u["nombre_completo"] = " ".join(x for x in (u.get("nombres"), u.get("apellidos")) if x)

    u.setdefault("tipo_documento", "CC") if u.get("documento_id") else None

    # Edad (6) y unidad (7) a la fecha de ingreso
    if u.get("fecha_nacimiento") and u.get("edad") is None:
        edad, unidad = calcular_edad(u["fecha_nacimiento"], a.get("fecha_ingreso"))
        if edad is not None:
            u["edad"], u["unidad_edad"] = edad, unidad

    if sede_id:
        u.setdefault("sede_origen_id", sede_id)
        if a:
            a.setdefault("sede_id", sede_id)
        # Código del prestador (43): sale del catálogo REPS de la sede
        if e:
            e.setdefault("codigo_prestador", SEDES.get(int(sede_id), {}).get("codigo_prestador"))

    if u.get("documento_id"):
        u.setdefault("fhir_patient_id", None)

    # Entorno (19) <-> clase HL7 (E/O/I)
    if a:
        if a.get("clase_atencion") and not a.get("entorno_atencion"):
            a["entorno_atencion"] = normalizar_codigo("entorno_atencion", a["clase_atencion"])
        if a.get("entorno_atencion") and not a.get("clase_atencion"):
            a["clase_atencion"] = {"01": "E", "03": "I"}.get(a["entorno_atencion"], "O")
        if not a.get("numero_visita") and u.get("documento_id") and a.get("fecha_ingreso"):
            compacta = re.sub(r"\D", "", str(a["fecha_ingreso"]))[:12]
            a["numero_visita"] = f"V-S{sede_id}-{u['documento_id']}-{compacta}"
        # El estado solo se fija si el mensaje lo determina (egreso). Un ORU de laboratorio
        # no debe reabrir una atención ya finalizada: sin estado, la base conserva el que tenía.
        if e.get("fecha_salida"):
            a["estado"] = "FINALIZADA"

    visita = a.get("numero_visita", "")
    # Diagnósticos: rol, tipo, orden e id determinista
    relacionados = 0
    for i, dx in enumerate(reg["diagnosticos"]):
        dx["numero_visita"] = visita
        dx["cie10_codigo"] = str(dx.get("cie10_codigo") or "").strip().upper()
        dx.setdefault("rol", "INGRESO")
        if dx["rol"] == "RELACIONADO":
            relacionados += 1
            dx.setdefault("orden", relacionados)
            dx.setdefault("tipo_diagnostico", "02")
        else:
            dx.setdefault("orden", 1)
            dx.setdefault("tipo_diagnostico", "01")
        if not dx.get("descripcion_cie10"):
            dx["descripcion_cie10"] = dx["cie10_codigo"]
        dx["diagnostico_id"] = f"cond-{_id_limpio(visita)}-{dx['rol'][:3].lower()}-{_id_limpio(dx['cie10_codigo'])}"

    # Tecnologías: tipo e id determinista
    for t in reg["tecnologias"]:
        t["numero_visita"] = visita
        if not t.get("tipo"):
            t["tipo"] = "LABORATORIO" if t.get("loinc_codigo") else "MEDICAMENTO"
        if t["tipo"] == "LABORATORIO":
            t["tecnologia_id"] = f"obs-{_id_limpio(visita)}-{_id_limpio(t.get('loinc_codigo'))}"
        else:
            base = hashlib.sha1(str(t.get("descripcion_medicamento", "")).upper().encode()).hexdigest()[:8]
            t["tecnologia_id"] = f"med-{_id_limpio(visita)}-{base}"
    return reg


# ══════════════════════════════════════════════════════════════════════════
# 3. HL7 v2.5 -> canónico
# ══════════════════════════════════════════════════════════════════════════

def segmentos_hl7(raw: str) -> Dict[str, List[List[str]]]:
    """Separa segmentos (\\r, \\n o \\r\\n) y campos (|)."""
    texto = raw.replace("\r\n", "\n").replace("\r", "\n")
    segs: Dict[str, List[List[str]]] = {}
    for linea in texto.split("\n"):
        linea = linea.strip()
        if not linea:
            continue
        partes = linea.split("|")
        segs.setdefault(partes[0].upper(), []).append(partes)
    return segs


def valor_hl7(seg: Optional[List[str]], ruta: str) -> Optional[str]:
    """
    Lee 'SEG-F' o 'SEG-F.C' de un segmento ya separado.
    MSH-1 es el propio separador, así que en MSH el campo n está en la posición n-1.
    Toma la primera repetición (~) y el componente indicado (^).
    """
    if seg is None:
        return None
    m = re.fullmatch(r"([A-Z0-9]{3})-(\d+)(?:\.(\d+))?", ruta.strip())
    if not m:
        return None
    nombre, campo, comp = m.group(1), int(m.group(2)), m.group(3)
    pos = campo - 1 if nombre == "MSH" else campo
    if pos >= len(seg):
        return None
    valor = seg[pos].split("~")[0]
    if comp is not None:
        partes = valor.split("^")
        idx = int(comp) - 1
        valor = partes[idx] if idx < len(partes) else ""
    valor = valor.split("&")[0].strip()
    return valor or None


def _primero(segs: Dict[str, List[List[str]]], nombre: str) -> Optional[List[str]]:
    return segs.get(nombre, [None])[0]


def desde_hl7(raw: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Traduce un mensaje HL7 v2 (ADT^A01, ORU^R01, RDE^O11) al registro canónico.
    Devuelve (metadatos, registro).
    """
    if not raw or not raw.strip():
        raise ValueError("El mensaje HL7 está vacío")
    segs = segmentos_hl7(raw)
    if "MSH" not in segs:
        raise ValueError("Segmento MSH no encontrado en el mensaje HL7")
    msh = _primero(segs, "MSH")
    sede_raw = valor_hl7(msh, "MSH-4") or ""
    sede_id = SEDE_POR_CODIGO.get(sede_raw.upper())
    tipo = (valor_hl7(msh, "MSH-9") or "").upper()
    meta = {
        "formato": "HL7_V2",
        "mensaje_id": valor_hl7(msh, "MSH-10") or f"MSG-{hashlib.md5(raw.encode()).hexdigest()[:8]}",
        "tipo_mensaje": tipo,
        "sede_origen": sede_id,
        "sede_raw": sede_raw,
        "hash_contenido": hashlib.sha256(raw.strip().encode("utf-8")).hexdigest(),
    }

    reg = registro_vacio()
    obs = reg["_observaciones"]

    # Campos de UNA aparición (usuario, atención, egreso) guiados por el catálogo
    for campo in TODOS:
        if campo.contenedor not in CONTENEDORES_PLANOS or not campo.hl7 or campo.rol_dx:
            continue
        ruta = campo.hl7.split(" ")[0]
        if not re.fullmatch(r"[A-Z0-9]{3}-\d+(\.\d+)?", ruta) or ruta.startswith("MSH"):
            continue
        crudo = valor_hl7(_primero(segs, ruta[:3]), ruta)
        if crudo is None:
            continue
        val = convertir(campo, crudo, obs)
        if val is not None:
            reg[campo.contenedor][campo.clave] = val

    u, a = reg["usuario"], reg["atencion"]
    # PID-5 completo (Apellido^Nombre) y PID-3 crudo para el validador
    pid = _primero(segs, "PID")
    if pid is not None:
        u["documento_raw"] = pid[3] if len(pid) > 3 else ""
        if len(pid) > 5 and pid[5]:
            u["nombre_completo"] = pid[5]
    # PV1-2 también es la clase técnica
    pv1 = _primero(segs, "PV1")
    if pv1 is not None:
        clase = valor_hl7(pv1, "PV1-2")
        if clase:
            a["clase_atencion"] = clase.upper()
    # NK1-2 nombre del responsable viene como Apellido^Nombre
    nk1 = _primero(segs, "NK1")
    if nk1 is not None and len(nk1) > 2 and nk1[2]:
        partes = nk1[2].split("^")
        u["nombre_responsable"] = " ".join(p for p in partes[1:] + partes[:1] if p)
    # IN1-4 nombre de la EPS: componente 1
    # Egreso: responsable puede venir en PV1-7 si no hay ZEG-7 y hay fecha de salida
    if reg["egreso"].get("fecha_salida") and not reg["egreso"].get("responsable_egreso") and pv1 is not None:
        partes = (pv1[7] if len(pv1) > 7 else "").split("^")
        if len(partes) > 2:
            reg["egreso"]["responsable_egreso"] = f"{partes[2]} {partes[1]}".strip()

    # Alergias (47): todas las AL1, unidas
    alergias = [valor_hl7(s, "AL1-3.2") or valor_hl7(s, "AL1-3.1") for s in segs.get("AL1", [])]
    alergias = [x for x in alergias if x]
    if alergias:
        reg["egreso"]["alergias"] = ", ".join(alergias)

    # Diagnósticos (33-39): cada DG1 es una fila con rol
    relacionados = 0
    for dg1 in segs.get("DG1", []):
        codigo = valor_hl7(dg1, "DG1-3.1") or ""
        tipo_hl7 = (valor_hl7(dg1, "DG1-6") or "A").upper()   # A=admisión, W=trabajo, F=final
        prioridad = valor_hl7(dg1, "DG1-15")
        if prioridad and prioridad.isdigit() and int(prioridad) > 1:
            relacionados += 1
            rol, orden, tipo_dx = "RELACIONADO", relacionados, "02"
        else:
            rol, orden, tipo_dx = ("EGRESO" if tipo_hl7 == "F" else "INGRESO"), 1, "01"
        reg["diagnosticos"].append({
            "cie10_codigo": codigo.upper(),
            "descripcion_cie10": valor_hl7(dg1, "DG1-3.2") or codigo,
            "sistema": (valor_hl7(dg1, "DG1-3.3") or "").upper(),
            "rol": rol, "orden": orden, "tipo_diagnostico": tipo_dx,
            "fecha_diagnostico": _fecha_iso(valor_hl7(dg1, "DG1-5"), False) or (a.get("fecha_ingreso") or "")[:10],
        })

    # Resultados de laboratorio (OBX con LOINC)
    for obx in segs.get("OBX", []):
        valor = valor_hl7(obx, "OBX-5")
        try:
            valor_num = float(str(valor).replace(",", ".")) if valor is not None else None
        except ValueError:
            valor_num = None
        reg["tecnologias"].append({
            "tipo": "LABORATORIO",
            "loinc_codigo": valor_hl7(obx, "OBX-3.1") or "",
            "descripcion_loinc": valor_hl7(obx, "OBX-3.2") or valor_hl7(obx, "OBX-3.1") or "",
            "valor": valor_num,
            "unidad": valor_hl7(obx, "OBX-6.1") or "1",
            "fecha_toma": _fecha_iso(valor_hl7(obx, "OBX-14"), True) or a.get("fecha_ingreso"),
        })

    # Medicamentos (25-32): RXE + RXR + ORC + ZRX, en el orden en que llegan
    rxrs, orcs, zrxs = segs.get("RXR", []), segs.get("ORC", []), segs.get("ZRX", [])
    for i, rxe in enumerate(segs.get("RXE", [])):
        cantidad, unidad = valor_hl7(rxe, "RXE-3"), valor_hl7(rxe, "RXE-5.1") or valor_hl7(rxe, "RXE-5")
        med = {
            "tipo": "MEDICAMENTO",
            "descripcion_medicamento": valor_hl7(rxe, "RXE-2.2") or valor_hl7(rxe, "RXE-2.1"),
            "dosis": " ".join(x for x in (cantidad, unidad) if x) or None,
            "frecuencia": valor_hl7(rxe, "RXE-1.2"),
            "dias_tratamiento": convertir(_c("dias_tratamiento"), re.sub(r"\D", "", valor_hl7(rxe, "RXE-1.3") or "")),
            "unidades_aplicadas": convertir(_c("unidades_aplicadas"), valor_hl7(rxe, "RXE-10")),
        }
        if i < len(rxrs):
            med["via_administracion"] = convertir(_c("via_administracion"), valor_hl7(rxrs[i], "RXR-1.1"), obs)
        if i < len(orcs):
            med["id_personal_salud"] = valor_hl7(orcs[i], "ORC-12.1")
        if i < len(zrxs):
            med["finalidad_tecnologia"] = convertir(_c("finalidad_tecnologia"), valor_hl7(zrxs[i], "ZRX-1"), obs)
        reg["tecnologias"].append({k: v for k, v in med.items() if v is not None})

    completar_derivados(reg, sede_id)
    if not a.get("numero_visita"):
        a["numero_visita"] = f"V-AUTO-{meta['mensaje_id']}"
        completar_derivados(reg, sede_id)
    return meta, reg


def _c(clave: str) -> Campo:
    return next(c for c in TODOS if c.clave == clave)


# ══════════════════════════════════════════════════════════════════════════
# 4. CSV legado / JSON -> canónico
# ══════════════════════════════════════════════════════════════════════════

def _columnas_csv() -> Dict[str, Campo]:
    """Columna CSV -> campo. Acepta el nombre legado (documento, nombre...) y la clave canónica."""
    mapa: Dict[str, Campo] = {}
    for c in TODOS:
        if c.rol_dx:
            continue
        if c.csv and " " not in c.csv:
            mapa[c.csv.lower()] = c
        mapa.setdefault(c.clave.lower(), c)
    return mapa


COLUMNAS_CSV = _columnas_csv()


def desde_fila_csv(fila: Dict[str, str], sede_id: int, terminologia: Dict[str, Dict[str, str]],
                   linea_cruda: str = "") -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Traduce una fila del CSV legado (o de un CSV extendido con columnas canónicas)."""
    reg = registro_vacio()
    obs = reg["_observaciones"]
    tecnologia: Dict[str, Any] = {}
    for col, valor in fila.items():
        if col is None:
            continue
        campo = COLUMNAS_CSV.get(col.strip().lower())
        if not campo:
            continue
        val = convertir(campo, valor, obs)
        if val is None:
            continue
        if campo.contenedor == "tecnologia":
            tecnologia[campo.clave] = val
        elif campo.contenedor in CONTENEDORES_PLANOS:
            reg[campo.contenedor][campo.clave] = val

    a = reg["atencion"]
    # En el CSV legado el triage implica urgencias; sin triage es consulta externa
    if not a.get("entorno_atencion"):
        a["entorno_atencion"] = "01" if a.get("clasificacion_triage") else "02"

    # dx_local en texto libre -> CIE-10 con la tabla de referencia
    dx_local = str(fila.get("dx_local", "") or "").strip().upper()
    if dx_local:
        ref = terminologia.get(dx_local)
        if ref:
            reg["diagnosticos"].append({"cie10_codigo": ref["cie10"], "descripcion_cie10": ref["descripcion"],
                                        "rol": "INGRESO", "tipo_diagnostico": "01",
                                        "fecha_diagnostico": (a.get("fecha_ingreso") or "")[:10]})
        else:
            reg["dx_local_error"] = f"diagnóstico sin mapeo a CIE-10: '{dx_local}'"
    if tecnologia.get("descripcion_medicamento"):
        tecnologia["tipo"] = "MEDICAMENTO"
        reg["tecnologias"].append(tecnologia)

    completar_derivados(reg, sede_id)
    contenido = linea_cruda or ";".join(f"{k}={v}" for k, v in sorted(fila.items()) if k)
    h = hashlib.sha256(f"S{sede_id}|{contenido}".encode("utf-8")).hexdigest()
    meta = {"formato": "CSV", "mensaje_id": f"CSV-S{sede_id}-{h[:12]}", "tipo_mensaje": "CSV_ROW",
            "sede_origen": sede_id, "sede_raw": str(sede_id), "hash_contenido": h}
    return meta, reg


def leer_csv(contenido: str) -> List[Tuple[Dict[str, str], str]]:
    """Devuelve (fila_dict, línea_cruda) por cada fila del CSV con separador ';'."""
    lineas = [l for l in contenido.strip().splitlines() if l.strip()]
    if not lineas:
        return []
    lector = csv.DictReader(io.StringIO("\n".join(lineas)), delimiter=";")
    return [(fila, lineas[i + 1].strip()) for i, fila in enumerate(lector)]


def desde_json(obj: Dict[str, Any], sede_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Acepta un registro ya estructurado ({usuario, atencion, ...}) o uno plano cuyas llaves son
    claves canónicas ('documento_id') o números de campo ('2', 'campo_2'). Lo limpia con el catálogo.
    """
    reg = registro_vacio()
    obs = reg["_observaciones"]
    plano: Dict[str, Any] = {}
    if any(k in obj for k in ("usuario", "atencion", "egreso")):
        for cont in CONTENEDORES_PLANOS:
            plano.update({k: v for k, v in (obj.get(cont) or {}).items()})
        reg["diagnosticos"] = deepcopy(obj.get("diagnosticos") or [])
        reg["tecnologias"] = deepcopy(obj.get("tecnologias") or [])
    else:
        plano = dict(obj)
        # Un registro plano también puede traer listas explícitas de diagnósticos / tecnologías
        reg["diagnosticos"] = deepcopy(obj.get("diagnosticos") or [])
        reg["tecnologias"] = deepcopy(obj.get("tecnologias") or [])

    por_clave = {c.clave: c for c in TODOS}
    tecnologia: Dict[str, Any] = {}
    for llave, valor in plano.items():
        k = str(llave).replace("campo_", "")
        campo = POR_NUM_STR.get(k) or por_clave.get(k)
        if not campo or valor is None:
            continue
        if campo.rol_dx:
            if campo.atributo_dx == "cie10_codigo" and valor:
                reg["diagnosticos"].append({"cie10_codigo": valor, "rol": campo.rol_dx,
                                            "orden": campo.orden_dx})
            continue
        val = convertir(campo, valor, obs)
        if val is None:
            continue
        if campo.contenedor == "tecnologia":
            tecnologia[campo.clave] = val
        else:
            reg[campo.contenedor][campo.clave] = val
    if tecnologia:
        reg["tecnologias"].append(tecnologia)
    for t in reg["tecnologias"]:
        for c in campos_de("tecnologia"):
            if c.clave in t:
                t[c.clave] = convertir(c, t[c.clave], obs)
    for dx in reg["diagnosticos"]:
        if dx.get("tipo_diagnostico"):
            dx["tipo_diagnostico"] = normalizar_codigo("tipo_diagnostico", dx["tipo_diagnostico"]) or "01"
    completar_derivados(reg, sede_id or reg["atencion"].get("sede_id") or reg["usuario"].get("sede_origen_id"))
    return reg


POR_NUM_STR = {str(c.num): c for c in CAMPOS_57}


# ══════════════════════════════════════════════════════════════════════════
# 5. Canónico <-> PostgreSQL
# ══════════════════════════════════════════════════════════════════════════

def _columnas_pg(contenedor: str) -> List[str]:
    return [c.pg.split(".", 1)[1] for c in campos_de(contenedor) if c.pg]


def a_postgres(reg: Dict[str, Any]) -> Dict[str, Any]:
    """Registro canónico -> {tabla: fila | [filas]} con las columnas que dicta el catálogo."""
    doc = reg["usuario"].get("documento_id")
    visita = reg["atencion"].get("numero_visita")
    salida: Dict[str, Any] = {
        "usuario": {col: reg["usuario"].get(col) for col in _columnas_pg("usuario") if col in reg["usuario"]},
        "atencion": {}, "tecnologia_salud": [], "diagnostico": [], "egreso": {},
    }
    salida["usuario"]["documento_id"] = doc
    if visita:
        fila = {col: reg["atencion"].get(col) for col in _columnas_pg("atencion") if col in reg["atencion"]}
        fila.update({"numero_visita": visita, "documento_id": doc})
        salida["atencion"] = fila
        for t in reg["tecnologias"]:
            f = {col: t.get(col) for col in _columnas_pg("tecnologia") if col in t}
            f["numero_visita"] = visita
            salida["tecnologia_salud"].append(f)
        for dx in reg["diagnosticos"]:
            f = {col: dx.get(col) for col in _columnas_pg("diagnostico") if col in dx}
            f["numero_visita"] = visita
            salida["diagnostico"].append(f)
        if reg["egreso"]:
            f = {col: reg["egreso"].get(col) for col in _columnas_pg("egreso") if col in reg["egreso"]}
            f["numero_visita"] = visita
            salida["egreso"] = f
    return salida


def _limpiar_fila(contenedor: str, fila: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Fila de PostgreSQL -> diccionario canónico (tipos JSON-serializables)."""
    if not fila:
        return {}
    salida: Dict[str, Any] = {}
    for c in campos_de(contenedor):
        if not c.pg:
            continue
        col = c.pg.split(".", 1)[1]
        if col in fila and fila[col] is not None:
            v = fila[col]
            if isinstance(v, (datetime.date, datetime.datetime)):
                v = _fecha_iso(v, con_hora=c.tipo == "fechahora")
            elif hasattr(v, "is_finite"):        # Decimal
                v = float(v)
            salida[c.clave] = v
    for extra in ("numero_visita", "documento_id"):
        if extra in fila and fila[extra] is not None:
            salida.setdefault(extra, fila[extra])
    return salida


def desde_postgres(usuario: Dict[str, Any], atenciones: List[Dict[str, Any]],
                   tecnologias: List[Dict[str, Any]], diagnosticos: List[Dict[str, Any]],
                   egresos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Filas de las 5 tablas -> historia canónica del paciente en esa sede."""
    hist = {"usuario": _limpiar_fila("usuario", usuario), "atenciones": []}
    for at in atenciones:
        v = at["numero_visita"]
        item = _limpiar_fila("atencion", at)
        item["tecnologias"] = [_limpiar_fila("tecnologia", t) for t in tecnologias if t["numero_visita"] == v]
        item["diagnosticos"] = [_limpiar_fila("diagnostico", d) for d in diagnosticos if d["numero_visita"] == v]
        eg = next((e for e in egresos if e["numero_visita"] == v), None)
        item["egreso"] = _limpiar_fila("egreso", eg)
        hist["atenciones"].append(item)
    return hist


# ══════════════════════════════════════════════════════════════════════════
# 6. Canónico <-> MongoDB (documento embebido por paciente)
# ══════════════════════════════════════════════════════════════════════════

def _poner(doc: Dict[str, Any], ruta: str, valor: Any) -> None:
    partes = ruta.split(".")
    for p in partes[:-1]:
        doc = doc.setdefault(p, {})
    doc[partes[-1]] = valor


def _sacar(doc: Dict[str, Any], ruta: str) -> Any:
    for p in ruta.split("."):
        if not isinstance(doc, dict) or p not in doc:
            return None
        doc = doc[p]
    return doc


def _a_sub(contenedor: str, datos: Dict[str, Any]) -> Dict[str, Any]:
    sub: Dict[str, Any] = {}
    for c in campos_de(contenedor):
        if c.mongo and datos.get(c.clave) is not None:
            ruta = c.mongo[len("egreso."):] if contenedor == "egreso" and c.mongo.startswith("egreso.") else c.mongo
            _poner(sub, ruta, datos[c.clave])
    return sub


def _de_sub(contenedor: str, sub: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not sub:
        return {}
    datos: Dict[str, Any] = {}
    for c in campos_de(contenedor):
        if not c.mongo:
            continue
        ruta = c.mongo[len("egreso."):] if contenedor == "egreso" and c.mongo.startswith("egreso.") else c.mongo
        v = _sacar(sub, ruta)
        if v is not None:
            datos[c.clave] = v
    return datos


def _fusion_profunda(base: Dict[str, Any], nuevo: Dict[str, Any]) -> Dict[str, Any]:
    """Copia de `base` con los valores no nulos de `nuevo` encima, entrando en sub-documentos."""
    salida = deepcopy(base)
    for k, v in nuevo.items():
        if v is None:
            continue
        if isinstance(v, dict) and isinstance(salida.get(k), dict):
            salida[k] = _fusion_profunda(salida[k], v)
        else:
            salida[k] = deepcopy(v)
    return salida


def a_mongo(reg: Dict[str, Any], existente: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Fusiona una atención canónica en el documento `pacientes` del paciente (idempotente):
    los datos del usuario se actualizan y la atención se reemplaza por numero_visita.
    """
    doc = _fusion_profunda(existente or {}, _a_sub("usuario", reg["usuario"]))
    doc["_id"] = str(reg["usuario"]["documento_id"])
    atenciones = doc.setdefault("atenciones", [])

    visita = reg["atencion"].get("numero_visita")
    if visita:
        previa = next((x for x in atenciones if x.get("numero_visita") == visita), None)
        nueva = _a_sub("atencion", reg["atencion"])
        nueva["tecnologias"] = [_a_sub("tecnologia", t) for t in reg["tecnologias"]]
        nueva["diagnosticos"] = [_a_sub("diagnostico", d) for d in reg["diagnosticos"]]
        if reg["egreso"]:
            nueva["egreso"] = _a_sub("egreso", reg["egreso"])
        if previa:
            # Mezclar sin perder lo que ya estaba (idempotencia: mismas llaves -> mismo resultado)
            for lista, llave in (("tecnologias", "id"), ("diagnosticos", "id")):
                por_id = {x.get(llave): x for x in previa.get(lista, [])}
                for x in nueva[lista]:
                    por_id[x.get(llave)] = _fusion_profunda(por_id.get(x.get(llave), {}), x)
                nueva[lista] = list(por_id.values())
            listas = {k: nueva.pop(k) for k in ("tecnologias", "diagnosticos")}
            fusionada = _fusion_profunda(previa, nueva)
            fusionada.update(listas)
            atenciones[atenciones.index(previa)] = fusionada
        else:
            atenciones.append(nueva)
    return doc


def desde_mongo(doc: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Documento `pacientes` de MongoDB -> historia canónica (misma forma que desde_postgres)."""
    if not doc:
        return {"usuario": {}, "atenciones": []}
    hist = {"usuario": _de_sub("usuario", doc), "atenciones": []}
    for at in doc.get("atenciones", []):
        item = _de_sub("atencion", at)
        item["tecnologias"] = [_de_sub("tecnologia", t) for t in at.get("tecnologias", [])]
        item["diagnosticos"] = [_de_sub("diagnostico", d) for d in at.get("diagnosticos", [])]
        item["egreso"] = _de_sub("egreso", at.get("egreso"))
        hist["atenciones"].append(item)
    return hist


# ══════════════════════════════════════════════════════════════════════════
# 7. Vista plana de los 57 campos y cobertura
# ══════════════════════════════════════════════════════════════════════════

def vista_57(usuario: Dict[str, Any], atencion: Optional[Dict[str, Any]] = None) -> Dict[int, Any]:
    """{número de campo: valor} para un usuario y (opcionalmente) una de sus atenciones."""
    atencion = atencion or {}
    egreso = atencion.get("egreso") or {}
    meds = [t for t in atencion.get("tecnologias", []) if t.get("tipo") == "MEDICAMENTO"]
    med = meds[0] if meds else {}
    dxs = atencion.get("diagnosticos", [])
    plano: Dict[int, Any] = {}
    for c in CAMPOS_57:
        if c.rol_dx:
            filas = sorted([d for d in dxs if d.get("rol") == c.rol_dx], key=lambda d: d.get("orden") or 1)
            idx = c.orden_dx - 1
            plano[c.num] = filas[idx].get(c.atributo_dx) if idx < len(filas) else None
        elif c.contenedor == "usuario":
            plano[c.num] = usuario.get(c.clave)
        elif c.contenedor == "atencion":
            plano[c.num] = atencion.get(c.clave)
        elif c.contenedor == "tecnologia":
            plano[c.num] = med.get(c.clave)
        elif c.contenedor == "egreso":
            plano[c.num] = egreso.get(c.clave)
    return plano


def _lleno(v: Any) -> bool:
    return v is not None and not (isinstance(v, str) and v.strip() == "")


def cobertura_57(usuario: Dict[str, Any], atenciones: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Cobertura de los 57 campos para un paciente: un campo cuenta como cubierto si aparece en el
    usuario o en cualquiera de sus atenciones (de cualquier sede). Devuelve los faltantes con su
    número, nombre y si son obligatorios.
    """
    vistas = [vista_57(usuario, at) for at in atenciones] or [vista_57(usuario)]
    cubiertos = {n for v in vistas for n, val in v.items() if _lleno(val)}
    faltantes = [{"num": c.num, "nombre": c.nombre, "grupo": c.grupo, "obligatorio": c.obligatorio}
                 for c in CAMPOS_57 if c.num not in cubiertos]
    oblig_ok = sum(1 for c in OBLIGATORIOS if c.num in cubiertos)
    return {
        "total_campos": 57,
        "campos_cubiertos": len(cubiertos),
        "porcentaje": round(len(cubiertos) / 57 * 100, 1),
        "obligatorios_total": len(OBLIGATORIOS),
        "obligatorios_cubiertos": oblig_ok,
        "porcentaje_obligatorios": round(oblig_ok / len(OBLIGATORIOS) * 100, 1),
        "faltantes": faltantes,
        "faltantes_obligatorios": [f for f in faltantes if f["obligatorio"]],
    }


def tabla_57_legible(usuario: Dict[str, Any], atencion: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Filas listas para pintar: número, grupo, nombre, valor, etiqueta del código, obligatorio."""
    plano = vista_57(usuario, atencion)
    filas = []
    for c in CAMPOS_57:
        val = plano.get(c.num)
        dominio = c.dominio
        filas.append({
            "num": c.num, "grupo": c.grupo, "nombre": c.nombre, "obligatorio": c.obligatorio,
            "valor": val, "etiqueta": etiqueta(dominio, val) if dominio and val is not None else None,
            "lleno": _lleno(val),
        })
    return filas
