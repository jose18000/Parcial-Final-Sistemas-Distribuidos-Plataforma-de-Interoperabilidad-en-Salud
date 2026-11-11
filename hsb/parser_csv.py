"""
hsb/parser_csv.py
Lectura del CSV legado (separador ';') y tabla de terminología dx_local -> CIE-10.

Columnas aceptadas: las del CSV legado de la Sede 3 (documento, nombre, sexo, nacimiento,
dx_local, fecha, triage, profesional) y, además, cualquier clave canónica de los 57 campos
(municipio_residencia, entidad_salud, causa_atencion...). La traducción la hace
traductor/traductor.py (desde_fila_csv).
"""

import os
import csv
from typing import Any, Dict, List

from traductor.traductor import desde_fila_csv, leer_csv

TERMINOLOGIA_DEFAULT = {
    "DIARREA": {"cie10": "A09", "descripcion": "Diarrea y gastroenteritis"},
    "HIPERTENSION": {"cie10": "I10", "descripcion": "Hipertensión esencial"},
    "DIABETES": {"cie10": "E11.9", "descripcion": "Diabetes mellitus tipo 2"},
    "ASMA": {"cie10": "J45.9", "descripcion": "Asma"},
    "INFECCION URINARIA": {"cie10": "N39.0", "descripcion": "Infección de vías urinarias"},
    "LUMBAGO": {"cie10": "M54.5", "descripcion": "Lumbago"},
    "NEUMONIA": {"cie10": "J18.9", "descripcion": "Neumonía"},
    "CEFALEA": {"cie10": "R51", "descripcion": "Cefalea"},
}


def cargar_tabla_terminologia(ruta_csv: str = None) -> Dict[str, Dict[str, str]]:
    """Carga ejemplos/05_ref_terminologia.csv (la tabla oficial del profe) sobre la tabla por defecto."""
    tabla = dict(TERMINOLOGIA_DEFAULT)
    if not ruta_csv:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for p in (os.path.join(base, "ejemplos", "05_ref_terminologia.csv"), "/app/ejemplos/05_ref_terminologia.csv"):
            if os.path.exists(p):
                ruta_csv = p
                break
    if ruta_csv and os.path.exists(ruta_csv):
        with open(ruta_csv, encoding="utf-8") as f:
            for row in csv.DictReader(f, delimiter=";"):
                dx = (row.get("dx_local") or "").strip().upper()
                if dx:
                    tabla[dx] = {"cie10": row.get("cie10", "").strip(), "descripcion": row.get("descripcion", "").strip()}
    return tabla


TABLA_TERMINOLOGIA = cargar_tabla_terminologia()


def parse_csv_rows(content: str, sede_id: int) -> List[Dict[str, Any]]:
    """Una entrada por fila: metadatos + registro canónico + contenido original para reencolar."""
    encabezado = content.strip().splitlines()[0].strip() if content.strip() else ""
    salida = []
    for idx, (fila, linea) in enumerate(leer_csv(content), start=1):
        meta, reg = desde_fila_csv(fila, sede_id, TABLA_TERMINOLOGIA, linea)
        salida.append({**meta, **reg, "fila_indice": idx, "encabezado": encabezado, "linea": linea})
    return salida
