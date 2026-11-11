"""
hsb/migracion.py
Migración de los registros legados de cada sede a FHIR (guía Fase 5: «cobertura FHIR por sede:
0 % antes de migrar y 100 % después»).

Los pacientes que ya existían en las bases de las sedes antes de la plataforma nunca pasaron por el
bus. La migración los lee de su sede (PostgreSQL o MongoDB) con el traductor universal, arma un
Bundle transaction por paciente (todas sus atenciones de esa sede), lo publica en HAPI y marca el
registro con sus ids FHIR. Es idempotente: PUT con ids deterministas + UPSERT en la sede.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from db.repositorio import obtener_repositorio, marcar_ids_fhir
from fhir.normalizer import construir_bundle
from hsb.queue_manager import enviar_bundle_a_hapi
from traductor.catalogo_57 import SEDES

logger = logging.getLogger("hsb_migracion")


def _registros_por_atencion(hist: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Historia canónica de la sede -> un registro (usuario + una atención) por atención."""
    usuario = dict(hist.get("usuario") or {})
    salida = []
    for at in hist.get("atenciones", []):
        atencion = {k: v for k, v in at.items() if k not in ("diagnosticos", "tecnologias", "egreso")}
        salida.append({"usuario": usuario, "atencion": atencion,
                       "diagnosticos": [dict(d, numero_visita=at.get("numero_visita")) for d in at.get("diagnosticos", [])],
                       "tecnologias": [dict(t, numero_visita=at.get("numero_visita")) for t in at.get("tecnologias", [])],
                       "egreso": dict(at.get("egreso") or {}), "_observaciones": []})
    if not salida:
        salida.append({"usuario": usuario, "atencion": {}, "diagnosticos": [], "tecnologias": [], "egreso": {},
                       "_observaciones": []})
    return salida


def migrar_sede(sede_id: int, solo_pendientes: bool = True) -> Dict[str, Any]:
    repo = obtener_repositorio(sede_id)
    t0 = time.time()
    resumen: Dict[str, Any] = {"sede": sede_id, "nombre": SEDES[sede_id]["nombre"], "motor": repo.motor,
                               "revisados": 0, "publicados": 0, "ya_publicados": 0, "errores": []}
    try:
        pacientes = repo.listar_pacientes(None, 100000)
    except Exception as e:
        resumen["errores"].append({"documento": None, "motivo": f"La sede no responde: {str(e).splitlines()[0][:120]}"})
        return resumen
    for p in pacientes:
        resumen["revisados"] += 1
        if solo_pendientes and p.get("fhir_patient_id"):
            resumen["ya_publicados"] += 1
            continue
        doc = p["documento_id"]
        try:
            hist = repo.historia(doc)
            if not hist:
                continue
            hist["usuario"].setdefault("sede_origen_id", sede_id)
            for at in hist["atenciones"]:
                at["sede_id"] = sede_id
            bundle = construir_bundle(hist["usuario"], hist["atenciones"])
            ok, motivo = enviar_bundle_a_hapi(bundle, timeout_sec=20.0)
            if not ok:
                resumen["errores"].append({"documento": doc, "motivo": motivo})
                continue
            for reg in _registros_por_atencion(hist):
                repo.guardar(marcar_ids_fhir(reg))
            resumen["publicados"] += 1
        except Exception as e:
            logger.warning(f"Migración sede {sede_id}, paciente {doc}: {e}")
            resumen["errores"].append({"documento": doc, "motivo": str(e).splitlines()[0][:200]})
    resumen["duracion_ms"] = round((time.time() - t0) * 1000, 1)
    try:
        cob = repo.cobertura_fhir()
        resumen["cobertura_fhir"] = round(cob["pacientes_con_fhir"] / cob["total_pacientes"] * 100, 1) \
            if cob["total_pacientes"] else 100.0
    except Exception:
        resumen["cobertura_fhir"] = None
    logger.info(f"Migración sede {sede_id}: {resumen}")
    return resumen


def migrar(sede: Optional[int] = None) -> Dict[str, Any]:
    sedes = [int(sede)] if sede else sorted(SEDES)
    return {"sedes": [migrar_sede(s) for s in sedes]}
