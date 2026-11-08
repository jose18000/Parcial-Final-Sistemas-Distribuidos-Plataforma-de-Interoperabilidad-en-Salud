"""
hsb/parser_hl7.py
Parser de mensajes HL7 versión 2.5 (ADT^A01 y ORU^R01).

Soporta delimitadores estándar de segmentos: \r (ASCII 13), \n y \r\n.
Campos delimitados por | y componentes por ^.
"""

import re
import hashlib
from typing import Dict, Any, List, Optional


SEDE_MAP = {
    "SEDE1": 1,
    "SEDE2": 2,
    "SEDE3": 3,
    "1": 1,
    "2": 2,
    "3": 3
}


def parse_hl7_message(raw_text: str) -> Dict[str, Any]:
    """
    Parsea un mensaje HL7 v2 y extrae un diccionario normalizado con:
    - metadata (sede, tipo_mensaje, mensaje_id, hash)
    - usuario (documento, nombre, fecha_nacimiento, sexo)
    - atencion (numero_visita, clase, fecha_ingreso, medico)
    - diagnostico (opcional)
    - observacion (opcional)
    """
    if not raw_text or not raw_text.strip():
        raise ValueError("El mensaje HL7 está vacío")

    # Normalizar saltos de línea (\r, \r\n, \n)
    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in normalized.split("\n") if line.strip()]

    segments: Dict[str, List[List[str]]] = {}
    for line in lines:
        parts = line.split("|")
        seg_name = parts[0].upper()
        if seg_name not in segments:
            segments[seg_name] = []
        segments[seg_name].append(parts)

    if "MSH" not in segments:
        raise ValueError("Segmento MSH no encontrado en el mensaje HL7")

    # Segmento MSH
    # En MSH: parts[0]='MSH', parts[1]='^~\&' (delimitadores), parts[2]=EnvíaApp, parts[3]=EnvíaSede, etc.
    # Siguiendo la convención HL7:
    # MSH-3 = parts[2], MSH-4 = parts[3], MSH-9 = parts[8], MSH-10 = parts[9]
    msh = segments["MSH"][0]

    raw_sede = msh[3] if len(msh) > 3 else ""
    sede_id = SEDE_MAP.get(raw_sede.strip().upper(), None)

    tipo_mensaje_raw = msh[8] if len(msh) > 8 else ""
    tipo_mensaje = tipo_mensaje_raw.strip().upper()

    mensaje_id = msh[9].strip() if len(msh) > 9 else f"MSG-{hashlib.md5(raw_text.encode('utf-8')).hexdigest()[:8]}"
    hash_contenido = hashlib.sha256(raw_text.strip().encode("utf-8")).hexdigest()

    result: Dict[str, Any] = {
        "formato": "HL7_V2",
        "mensaje_id": mensaje_id,
        "hash_contenido": hash_contenido,
        "sede_origen": sede_id,
        "sede_raw": raw_sede,
        "tipo_mensaje": tipo_mensaje,
        "usuario": {},
        "atencion": {},
        "diagnosticos": [],
        "tecnologias": []
    }

    # Segmento PID (Identificación del Paciente)
    if "PID" in segments:
        pid = segments["PID"][0]
        # PID-3: Documento (puede tener subcomponentes: 1007^^^HIS)
        doc_raw = pid[3] if len(pid) > 3 else ""
        doc_val = doc_raw.split("^")[0].strip()

        # PID-5: Nombre (Apellido^Nombre)
        nombre_raw = pid[5] if len(pid) > 5 else ""

        # PID-7: Fecha Nacimiento (YYYYMMDD)
        nacimiento_raw = pid[7] if len(pid) > 7 else ""

        # PID-8: Sexo (M, F, O)
        sexo_raw = pid[8] if len(pid) > 8 else ""

        result["usuario"] = {
            "documento_id": doc_val,
            "documento_raw": doc_raw,
            "nombre_completo": nombre_raw,
            "fecha_nacimiento": nacimiento_raw,
            "sexo": sexo_raw.strip().upper(),
            "sede_origen_id": sede_id
        }

    # Segmento PV1 (Visita / Atención)
    if "PV1" in segments:
        pv1 = segments["PV1"][0]
        clase_raw = pv1[2] if len(pv1) > 2 else "O"
        medico_raw = pv1[7] if len(pv1) > 7 else ""
        medico_cod = medico_raw.split("^")[0].strip() if medico_raw else None
        visita_raw = pv1[19] if len(pv1) > 19 else f"V-AUTO-{mensaje_id}"
        fecha_ingreso_raw = pv1[44] if len(pv1) > 44 else ""

        result["atencion"] = {
            "numero_visita": visita_raw.strip(),
            "clase_atencion": clase_raw.strip().upper(),
            "codigo_profesional": medico_cod,
            "profesional_nombre": medico_raw,
            "fecha_ingreso": fecha_ingreso_raw.strip(),
            "sede_id": sede_id,
            "documento_id": result["usuario"].get("documento_id", "")
        }

    # Segmento DG1 (Diagnóstico)
    if "DG1" in segments:
        for dg1 in segments["DG1"]:
            # DG1-3: código^descripción^sistema (ej. J45.9^Asma^I10 o DIARREA^Diarrea^L)
            dx_field = dg1[3] if len(dg1) > 3 else ""
            dx_parts = dx_field.split("^")
            dx_cod = dx_parts[0].strip() if len(dx_parts) > 0 else ""
            dx_desc = dx_parts[1].strip() if len(dx_parts) > 1 else dx_cod
            dx_sistema = dx_parts[2].strip().upper() if len(dx_parts) > 2 else ""

            fecha_dx = dg1[5] if len(dg1) > 5 else result["atencion"].get("fecha_ingreso", "")
            tipo_dx = dg1[6] if len(dg1) > 6 else "PRINCIPAL"

            result["diagnosticos"].append({
                "cie10_codigo": dx_cod,
                "descripcion_cie10": dx_desc,
                "sistema": dx_sistema,
                "tipo": tipo_dx,
                "fecha_diagnostico": fecha_dx,
                "numero_visita": result["atencion"].get("numero_visita", "")
            })

    # Segmentos OBR y OBX (Observaciones / Laboratorios)
    if "OBX" in segments:
        for obx in segments["OBX"]:
            # OBX-2: tipo de valor (NM, ST, etc.)
            tipo_val = obx[2] if len(obx) > 2 else "NM"
            # OBX-3: código LOINC^descripción^sistema
            obs_field = obx[3] if len(obx) > 3 else ""
            obs_parts = obs_field.split("^")
            loinc_cod = obs_parts[0].strip() if len(obs_parts) > 0 else ""
            loinc_desc = obs_parts[1].strip() if len(obs_parts) > 1 else loinc_cod
            # OBX-5: valor
            val_raw = obx[5] if len(obx) > 5 else "0"
            try:
                val_num = float(val_raw.replace(",", "."))
            except ValueError:
                val_num = 0.0
            # OBX-6: unidad
            unidad_raw = obx[6] if len(obx) > 6 else ""

            fecha_obs = result["atencion"].get("fecha_ingreso", "")

            result["tecnologias"].append({
                "loinc_codigo": loinc_cod,
                "descripcion_loinc": loinc_desc,
                "valor": val_num,
                "unidad": unidad_raw.strip(),
                "fecha_toma": fecha_obs,
                "numero_visita": result["atencion"].get("numero_visita", "")
            })

    return result

