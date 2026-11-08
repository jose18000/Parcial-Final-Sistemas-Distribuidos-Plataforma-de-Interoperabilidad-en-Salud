"""
db/consulta_unificada.py
Servicio de Consulta Unificada Distribuida (Scatter-Gather / Fan-Out).

Responsabilidad:
Recorrer los 3 nodos de base de datos (Sincelejo, Cartagena, Corozal),
consolidar la historia clínica de un paciente por documento_id exacto,
y tolerar fallos parciales (si un nodo no responde, reportar sedes caídas
y marcar el resultado como incompleto según el principio AP del teorema CAP).
"""

import os
import sys
import json
import logging
from typing import Dict, Any, List

# Soporte opcional para psycopg2 / psycopg
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG_AVAILABLE = True
except ImportError:
    PSYCOPG_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("consulta_unificada")

# Configuración de conexiones a los 3 nodos PostgreSQL
CONFIG_NODOS = [
    {
        "sede_id": 1,
        "nombre": "Sede 1 - Sincelejo",
        "host": os.getenv("DB_HOST_SEDE1", "localhost"),
        "port": int(os.getenv("DB_PORT_SEDE1", "5433")),
        "database": os.getenv("DB_NAME_SEDE1", "clinica_sincelejo"),
        "user": os.getenv("POSTGRES_USER", "clinica_user"),
        "password": os.getenv("POSTGRES_PASSWORD", "clinica_pass_2026")
    },
    {
        "sede_id": 2,
        "nombre": "Sede 2 - Cartagena",
        "host": os.getenv("DB_HOST_SEDE2", "localhost"),
        "port": int(os.getenv("DB_PORT_SEDE2", "5434")),
        "database": os.getenv("DB_NAME_SEDE2", "clinica_cartagena"),
        "user": os.getenv("POSTGRES_USER", "clinica_user"),
        "password": os.getenv("POSTGRES_PASSWORD", "clinica_pass_2026")
    },
    {
        "sede_id": 3,
        "nombre": "Sede 3 - Corozal",
        "host": os.getenv("DB_HOST_SEDE3", "localhost"),
        "port": int(os.getenv("DB_PORT_SEDE3", "5435")),
        "database": os.getenv("DB_NAME_SEDE3", "clinica_corozal"),
        "user": os.getenv("POSTGRES_USER", "clinica_user"),
        "password": os.getenv("POSTGRES_PASSWORD", "clinica_pass_2026")
    }
]


def consultar_sede_nodo(nodo_cfg: Dict[str, Any], documento_id: str) -> Dict[str, Any]:
    """Consulta la historia clínica de un paciente en un nodo específico."""
    sede_id = nodo_cfg["sede_id"]
    nombre_sede = nodo_cfg["nombre"]

    if not PSYCOPG_AVAILABLE:
        # Modo simulado si el driver no está instalado en el entorno local
        return {
            "sede_id": sede_id,
            "disponible": False,
            "error": "Driver psycopg2 no instalado localmente"
        }

    conn = None
    try:
        conn = psycopg2.connect(
            host=nodo_cfg["host"],
            port=nodo_cfg["port"],
            dbname=nodo_cfg["database"],
            user=nodo_cfg["user"],
            password=nodo_cfg["password"],
            connect_timeout=3
        )
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 1. Datos demográficos del paciente
            cur.execute("""
                SELECT documento_id, tipo_documento, nombre_completo, fecha_nacimiento, sexo, direccion, telefono, fhir_patient_id
                FROM usuario WHERE documento_id = %s
            """, (documento_id,))
            usuario = cur.fetchone()

            if not usuario:
                return {
                    "sede_id": sede_id,
                    "disponible": True,
                    "tiene_registros": False,
                    "atenciones": []
                }

            # 2. Atenciones registradas en esta sede
            cur.execute("""
                SELECT numero_visita, clase_atencion, fecha_ingreso, fecha_egreso, triage, estado, sede_id, codigo_profesional
                FROM atencion WHERE documento_id = %s ORDER BY fecha_ingreso DESC
            """, (documento_id,))
            atenciones = [dict(r) for r in cur.fetchall()]

            # 3. Diagnósticos y Tecnologías por atención
            for at in atenciones:
                num_visita = at["numero_visita"]
                cur.execute("""
                    SELECT cie10_codigo, descripcion_cie10, tipo, fecha_diagnostico
                    FROM diagnostico WHERE numero_visita = %s
                """, (num_visita,))
                at["diagnosticos"] = [dict(d) for d in cur.fetchall()]

                cur.execute("""
                    SELECT loinc_codigo, descripcion_loinc, valor, unidad, fecha_toma
                    FROM tecnologia_salud WHERE numero_visita = %s
                """, (num_visita,))
                at["tecnologias"] = [dict(t) for t in cur.fetchall()]

            return {
                "sede_id": sede_id,
                "nombre_sede": nombre_sede,
                "disponible": True,
                "tiene_registros": True,
                "usuario": dict(usuario),
                "atenciones": atenciones
            }

    except Exception as e:
        logger.warning(f"Error consultando {nombre_sede} ({nodo_cfg['host']}:{nodo_cfg['port']}): {e}")
        return {
            "sede_id": sede_id,
            "nombre_sede": nombre_sede,
            "disponible": False,
            "error": str(e)
        }
    finally:
        if conn:
            conn.close()


def consultar_historia_unificada(documento_id: str) -> Dict[str, Any]:
    """
    Ejecuta el patrón scatter-gather / fan-out sobre las tres sedes.
    Regla de coincidencia: documento exacto (documento_id).
    Tolerancia a fallos: responde con sedes disponibles y reporta incompletitud si alguna falla.
    """
    sedes_consultadas = []
    sedes_disponibles = []
    sedes_no_disponibles = []
    todas_atenciones = []
    datos_paciente = None

    for nodo in CONFIG_NODOS:
        res = consultar_sede_nodo(nodo, documento_id)
        sede_id = nodo["sede_id"]
        sedes_consultadas.append(sede_id)

        if res.get("disponible"):
            sedes_disponibles.append(sede_id)
            if res.get("tiene_registros"):
                if not datos_paciente and res.get("usuario"):
                    datos_paciente = res["usuario"]
                for at in res.get("atenciones", []):
                    at["sede_origen"] = res.get("nombre_sede", f"Sede {sede_id}")
                    todas_atenciones.append(at)
        else:
            sedes_no_disponibles.append({
                "sede_id": sede_id,
                "nombre": nodo["nombre"],
                "motivo": res.get("error", "Tiempo de espera agotado o nodo inactivo")
            })

    # Ordenar atenciones cronológicamente (más recientes primero)
    todas_atenciones.sort(
        key=lambda x: str(x.get("fecha_ingreso") or ""),
        reverse=True
    )

    es_completo = len(sedes_no_disponibles) == 0

    return {
        "documento_id": documento_id,
        "paciente": datos_paciente,
        "reporte_completo": es_completo,
        "aviso_incompletitud": None if es_completo else f"Atención: {len(sedes_no_disponibles)} sede(s) no respondieron. La historia clínica puede estar fraccionada.",
        "sedes_disponibles": sedes_disponibles,
        "sedes_no_disponibles": sedes_no_disponibles,
        "total_atenciones_encontradas": len(todas_atenciones),
        "atenciones": todas_atenciones
    }


if __name__ == "__main__":
    doc_prueba = sys.argv[1] if len(sys.argv) > 1 else "1001"
    print(f"=== Consultando historia unificada para documento: {doc_prueba} ===")
    resultado = consultar_historia_unificada(doc_prueba)
    print(json.dumps(resultado, indent=2, default=str))

