"""
app/dashboard.py
Tablero de estado (pestaña del Reporte de HC, guía Fase 4 paso 4):
  1. Nodos disponibles y su motor (PostgreSQL / MongoDB)
  2. Cobertura FHIR por sede (% de pacientes enlazados a un Patient en HAPI)
  3. Métricas del HSB (mensajes por estado, latencia, % fallidos, duplicados)
  4. Resultado del verificador de la auditoría encadenada
"""

import os
import time
from typing import Any, Dict

import httpx

from app.audit import estado_auditoria
from db.repositorio import todos_los_repositorios

HSB_METRICS_URL = os.getenv("HSB_METRICS_URL", "http://localhost:8001/metrics")
HAPI_FHIR_URL = os.getenv("HAPI_FHIR_URL", "http://localhost:8090/fhir")


def _estado_sede(repo) -> Dict[str, Any]:
    t0 = time.time()
    try:
        cob = repo.cobertura_fhir()
        total, con = cob["total_pacientes"], cob["pacientes_con_fhir"]
        return {"sede_id": repo.sede_id, "nombre": repo.nombre, "motor": repo.motor, "disponible": True,
                "total_pacientes": total, "pacientes_con_fhir": con,
                "porcentaje_cobertura": round(con / total * 100, 1) if total else 0.0,
                "latencia_ms": round((time.time() - t0) * 1000, 1)}
    except Exception as e:
        return {"sede_id": repo.sede_id, "nombre": repo.nombre, "motor": repo.motor, "disponible": False,
                "total_pacientes": 0, "pacientes_con_fhir": 0, "porcentaje_cobertura": 0.0,
                "error": "La base de datos de la sede no responde"
                         if "not known" in str(e) or "timed out" in str(e).lower() or "refused" in str(e)
                         else (str(e).splitlines()[0][:120] if str(e) else e.__class__.__name__)}


def estado_sedes() -> Dict[str, Any]:
    """Las 3 sedes se consultan en paralelo: una sede caída cuesta su timeout una sola vez."""
    from concurrent.futures import ThreadPoolExecutor
    repos = todos_los_repositorios()
    with ThreadPoolExecutor(max_workers=len(repos)) as pool:
        return {f"sede_{r['sede_id']}": r for r in pool.map(_estado_sede, repos)}


def obtener_metricas_bus() -> Dict[str, Any]:
    try:
        from seguridad import tls
        resp = httpx.get(HSB_METRICS_URL, timeout=8.0, verify=tls.verificacion_http())
        if resp.status_code == 200:
            datos = resp.json()
            datos["estado_general"] = datos.get("estado_general", "SALUDABLE")
            return datos
    except Exception:
        pass
    return {"total_recibidos": 0, "total_entregados": 0, "total_rechazados": 0, "total_duplicados_detectados": 0,
            "total_mensajes_muertos": 0, "latencia_media_ms": 0.0, "porcentaje_fallidos": 0.0,
            "mensajes_ultimo_minuto": 0, "mensajes_por_estado_persistidos": {},
            "total_reintentos_ejecutados": 0, "pendientes_en_cola_reintentos": 0,
            "estado_general": "HSB NO DISPONIBLE"}


def hapi_disponible() -> bool:
    try:
        from seguridad import tls
        return httpx.get(f"{HAPI_FHIR_URL}/metadata", timeout=3.0, verify=tls.verificacion_http()).status_code == 200
    except Exception:
        return False


def obtener_estado_general_plataforma() -> Dict[str, Any]:
    sedes = estado_sedes()
    activos = sum(1 for s in sedes.values() if s["disponible"])
    total_pac = sum(s["total_pacientes"] for s in sedes.values())
    total_fhir = sum(s["pacientes_con_fhir"] for s in sedes.values())
    return {
        "nodos": {"total": len(sedes), "activos": activos, "detalles": sedes},
        "cobertura_fhir_global": round(total_fhir / total_pac * 100, 1) if total_pac else 0.0,
        "hapi_fhir": "UP" if hapi_disponible() else "DOWN",
        "bus": obtener_metricas_bus(),
        "auditoria": estado_auditoria(),
    }
