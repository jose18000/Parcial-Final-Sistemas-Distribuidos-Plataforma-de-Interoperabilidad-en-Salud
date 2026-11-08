"""
app/dashboard.py
Recolector de Métricas del Tablero de Estado de la Plataforma.

Consolida:
1. Disponibilidad de los nodos PostgreSQL de cada sede
2. Cobertura de recursos FHIR por sede (%)
3. Métricas del Health Service Bus (mensajes por estado, latencia)
4. Resultado del verificador de auditoría encadenada
"""

import os
import httpx
from typing import Dict, Any, List

from app.audit import verificar_cadena_auditoria, _CADENA_AUDITORIA
from db.consulta_unificada import CONFIG_NODOS, PSYCOPG_AVAILABLE

if PSYCOPG_AVAILABLE:
    import psycopg2
    from psycopg2.extras import RealDictCursor

HSB_METRICS_URL = os.getenv("HSB_METRICS_URL", "http://localhost:8001/metrics")


def obtener_cobertura_fhir_por_sede() -> Dict[str, Any]:
    """Calcula el porcentaje de pacientes con fhir_patient_id no nulo en cada sede."""
    cobertura = {}

    for nodo in CONFIG_NODOS:
        sede_id = nodo["sede_id"]
        nombre = nodo["nombre"]

        if not PSYCOPG_AVAILABLE:
            cobertura[f"sede_{sede_id}"] = {
                "nombre": nombre,
                "disponible": False,
                "total_pacientes": 0,
                "pacientes_con_fhir": 0,
                "porcentaje_cobertura": 0.0
            }
            continue

        conn = None
        try:
            conn = psycopg2.connect(
                host=nodo["host"],
                port=nodo["port"],
                dbname=nodo["database"],
                user=nodo["user"],
                password=nodo["password"],
                connect_timeout=2
            )
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM usuario")
                total = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM usuario WHERE fhir_patient_id IS NOT NULL")
                con_fhir = cur.fetchone()[0]

                pct = (con_fhir / total * 100.0) if total > 0 else 0.0
                cobertura[f"sede_{sede_id}"] = {
                    "nombre": nombre,
                    "disponible": True,
                    "total_pacientes": total,
                    "pacientes_con_fhir": con_fhir,
                    "porcentaje_cobertura": round(pct, 1)
                }
        except Exception:
            cobertura[f"sede_{sede_id}"] = {
                "nombre": nombre,
                "disponible": False,
                "total_pacientes": 0,
                "pacientes_con_fhir": 0,
                "porcentaje_cobertura": 0.0
            }
        finally:
            if conn:
                conn.close()

    return cobertura


def obtener_metricas_bus() -> Dict[str, Any]:
    """Consulta las métricas en tiempo real expuestas por el HSB."""
    try:
        with httpx.Client(timeout=2.0) as client:
            resp = client.get(HSB_METRICS_URL)
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass

    return {
        "total_recibidos": 0,
        "total_entregados": 0,
        "total_rechazados": 0,
        "total_duplicados_detectados": 0,
        "total_mensajes_muertos": 0,
        "latencia_media_ms": 0.0,
        "porcentaje_fallidos": 0.0,
        "estado_general": "DESCONOCIDO_O_INACTIVO"
    }


def obtener_estado_general_plataforma() -> Dict[str, Any]:
    """Consolida el estado integral para el tablero de mando."""
    # 1. Cobertura FHIR y estado de nodos
    cobertura = obtener_cobertura_fhir_por_sede()
    nodos_activos = sum(1 for s in cobertura.values() if s.get("disponible"))

    # 2. Métricas del Bus
    metricas_bus = obtener_metricas_bus()

    # 3. Verificación de Auditoría Encadenada
    es_integra, fallo = verificar_cadena_auditoria()
    auditoria_status = {
        "cadena_integra": es_integra,
        "total_eventos_registrados": len(_CADENA_AUDITORIA),
        "estado_verificador": "INTEGRA (Sin alteraciones)" if es_integra else "¡ALERTA! ALTERACIÓN DETECTADA",
        "detalle_alteracion": fallo
    }

    return {
        "nodos": {
            "total": len(CONFIG_NODOS),
            "activos": nodos_activos,
            "detalles": cobertura
        },
        "bus": metricas_bus,
        "auditoria": auditoria_status
    }
