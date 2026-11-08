"""
hsb/parser_csv.py
Parser de archivos CSV legados con separador ';' y mapeo terminológico a CIE-10.
"""

import os
import csv
import io
import hashlib
from typing import Dict, Any, List, Tuple


TERMINOLOGIA_DEFAULT = {
    "DIARREA": {"cie10": "A09", "descripcion": "Diarrea y gastroenteritis"},
    "HIPERTENSION": {"cie10": "I10", "descripcion": "Hipertensión esencial"},
    "DIABETES": {"cie10": "E11.9", "descripcion": "Diabetes mellitus tipo 2"},
    "ASMA": {"cie10": "J45.9", "descripcion": "Asma"},
    "INFECCION URINARIA": {"cie10": "N39.0", "descripcion": "Infección de vías urinarias"},
    "LUMBAGO": {"cie10": "M54.5", "descripcion": "Lumbago"},
    "NEUMONIA": {"cie10": "J18.9", "descripcion": "Neumonía"},
    "CEFALEA": {"cie10": "R51", "descripcion": "Cefalea"}
}


def cargar_tabla_terminologia(ruta_csv: str = None) -> Dict[str, Dict[str, str]]:
    """Carga la tabla de referencia de diagnósticos locales a CIE-10."""
    tabla = dict(TERMINOLOGIA_DEFAULT)
    if not ruta_csv:
        # Intentar buscar ruta estándar
        posibles = [
            "ejemplos/05_ref_terminologia.csv",
            "../ejemplos/05_ref_terminologia.csv",
            "/app/ejemplos/05_ref_terminologia.csv"
        ]
        for p in posibles:
            if os.path.exists(p):
                ruta_csv = p
                break

    if ruta_csv and os.path.exists(ruta_csv):
        try:
            with open(ruta_csv, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter=";")
                for row in reader:
                    dx_local = row.get("dx_local", "").strip().upper()
                    if dx_local:
                        tabla[dx_local] = {
                            "cie10": row.get("cie10", "").strip(),
                            "descripcion": row.get("descripcion", "").strip()
                        }
        except Exception:
            pass
    return tabla


TABLA_TERMINOLOGIA = cargar_tabla_terminologia()


def parse_csv_rows(content: str, sede_id: int) -> List[Dict[str, Any]]:
    """
    Parsea el contenido de un CSV legado con separador ';' y devuelve
    una lista de registros listos para validación y procesamiento.
    """
    records = []
    stream = io.StringIO(content.strip())
    reader = csv.DictReader(stream, delimiter=";")

    for idx, row in enumerate(reader, start=1):
        doc = row.get("documento", "").strip()
        nombre = row.get("nombre", "").strip()
        sexo = row.get("sexo", "").strip().upper()
        nacimiento = row.get("nacimiento", "").strip()
        dx_local = row.get("dx_local", "").strip().upper()
        fecha = row.get("fecha", "").strip()
        triage = row.get("triage", "").strip()
        profesional = row.get("profesional", "").strip()

        # Generar identificador de visita y de mensaje único por fila
        row_str = f"{sede_id}-{doc}-{fecha}-{idx}"
        mensaje_id = f"MSG-CSV-S{sede_id}-{doc}-{idx}"
        hash_fila = hashlib.sha256(row_str.encode("utf-8")).hexdigest()
        numero_visita = f"V-S{sede_id}-CSV-{doc}"

        record: Dict[str, Any] = {
            "formato": "CSV",
            "fila_indice": idx,
            "mensaje_id": mensaje_id,
            "hash_contenido": hash_fila,
            "sede_origen": sede_id,
            "tipo_mensaje": "CSV_ROW",
            "usuario": {
                "documento_id": doc,
                "nombre_completo": nombre,
                "fecha_nacimiento": nacimiento,
                "sexo": sexo,
                "sede_origen_id": sede_id
            },
            "atencion": {
                "numero_visita": numero_visita,
                "clase_atencion": "E" if triage else "O",
                "fecha_ingreso": fecha,
                "triage": int(triage) if triage and triage.isdigit() else None,
                "codigo_profesional": profesional or None,
                "sede_id": sede_id,
                "documento_id": doc
            },
            "diagnosticos": [],
            "tecnologias": [],
            "dx_local_raw": dx_local
        }

        # Mapeo terminológico de dx_local
        if dx_local:
            if dx_local in TABLA_TERMINOLOGIA:
                mapa = TABLA_TERMINOLOGIA[dx_local]
                record["diagnosticos"].append({
                    "cie10_codigo": mapa["cie10"],
                    "descripcion_cie10": mapa["descripcion"],
                    "tipo": "PRINCIPAL",
                    "fecha_diagnostico": fecha[:10] if fecha else "",
                    "numero_visita": numero_visita
                })
            else:
                record["dx_local_error"] = f"diagnóstico sin mapeo a CIE-10: '{dx_local}'"

        records.append(record)

    return records
