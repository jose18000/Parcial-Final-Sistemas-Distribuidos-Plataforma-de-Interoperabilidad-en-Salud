"""
db/consulta_unificada.py
Consulta unificada distribuida (scatter-gather) sobre sedes con motores distintos.

    Sede 1 (PostgreSQL) ─┐
    Sede 2 (MongoDB)    ─┼─> traductor universal -> historia canónica única del paciente
    Sede 3 (PostgreSQL) ─┘

- Las 3 sedes se consultan EN PARALELO: una sede caída cuesta como máximo su timeout,
  no suma al tiempo de las demás.
- Regla de coincidencia entre sedes: documento exacto (documento_id).
- Tolerancia a fallos (AP en CAP): si una sede no responde, se devuelve lo de las otras,
  se marca la sede como no disponible y el reporte NO se da por completo.
"""

import sys
import json
import time
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

from db.repositorio import todos_los_repositorios, RepositorioSede
from traductor.catalogo_57 import SEDES
from traductor.traductor import cobertura_57

logger = logging.getLogger("consulta_unificada")

# Compatibilidad con módulos que listaban los nodos
CONFIG_NODOS = [{"sede_id": s, "nombre": d["nombre"], "motor": d["motor"]} for s, d in SEDES.items()]


def consultar_sede(repo: RepositorioSede, documento_id: str) -> Dict[str, Any]:
    t0 = time.time()
    try:
        hist = repo.historia(documento_id)
        return {"sede_id": repo.sede_id, "nombre_sede": repo.nombre, "motor": repo.motor, "disponible": True,
                "tiene_registros": hist is not None, "historia": hist,
                "latencia_ms": round((time.time() - t0) * 1000, 1)}
    except Exception as e:
        logger.warning(f"{repo.nombre} ({repo.motor}) no respondió: {e}")
        return {"sede_id": repo.sede_id, "nombre_sede": repo.nombre, "motor": repo.motor, "disponible": False,
                "error": str(e).splitlines()[0][:200], "latencia_ms": round((time.time() - t0) * 1000, 1)}


def _fusionar_usuario(base: Dict[str, Any], otro: Dict[str, Any]) -> Dict[str, Any]:
    """El dato del usuario más completo gana; lo que una sede no tiene lo aporta otra."""
    for k, v in otro.items():
        if v not in (None, "") and base.get(k) in (None, ""):
            base[k] = v
    return base


def consultar_historia_unificada(documento_id: str) -> Dict[str, Any]:
    documento_id = str(documento_id).strip()
    repos = todos_los_repositorios()
    with ThreadPoolExecutor(max_workers=len(repos)) as pool:
        resultados = list(pool.map(lambda r: consultar_sede(r, documento_id), repos))

    usuario: Dict[str, Any] = {}
    atenciones: List[Dict[str, Any]] = []
    sedes_disponibles, sedes_no_disponibles, sedes_con_registros = [], [], []
    detalle_sedes = []
    usuarios_por_sede: Dict[int, Dict[str, Any]] = {}

    for res in resultados:
        detalle_sedes.append({k: res.get(k) for k in ("sede_id", "nombre_sede", "motor", "disponible",
                                                         "tiene_registros", "latencia_ms", "error")})
        if not res["disponible"]:
            sedes_no_disponibles.append({"sede_id": res["sede_id"], "nombre": res["nombre_sede"],
                                         "motor": res["motor"], "motivo": res.get("error")})
            continue
        sedes_disponibles.append(res["sede_id"])
        hist = res.get("historia")
        if not hist:
            continue
        sedes_con_registros.append(res["sede_id"])
        usuarios_por_sede[res["sede_id"]] = hist.get("usuario") or {}
        _fusionar_usuario(usuario, hist.get("usuario") or {})
        for at in hist.get("atenciones", []):
            at["sede_id"] = res["sede_id"]
            at["sede_origen"] = res["nombre_sede"]
            at["motor_origen"] = res["motor"]
            atenciones.append(at)

    atenciones.sort(key=lambda a: str(a.get("fecha_ingreso") or ""), reverse=True)
    completo = not sedes_no_disponibles

    # Posibles duplicados mal digitados: el mismo documento con datos distintos entre sedes
    inconsistencias = []
    for campo in ("nombre_completo", "fecha_nacimiento", "sexo"):
        valores = {s: u.get(campo) for s, u in usuarios_por_sede.items() if u.get(campo)}
        if len({str(v).strip().upper() for v in valores.values()}) > 1:
            inconsistencias.append({"campo": campo, "valores_por_sede": valores})
    return {
        "documento_id": documento_id,
        "paciente": usuario or None,
        "reporte_completo": completo,
        "aviso_incompletitud": None if completo else (
            f"Atención: {len(sedes_no_disponibles)} sede(s) no respondieron "
            f"({', '.join(s['nombre'] for s in sedes_no_disponibles)}). La historia puede estar incompleta."),
        "sedes_disponibles": sedes_disponibles,
        "sedes_no_disponibles": sedes_no_disponibles,
        "sedes_con_registros": sedes_con_registros,
        "inconsistencias_entre_sedes": inconsistencias,
        "detalle_sedes": detalle_sedes,
        "total_atenciones_encontradas": len(atenciones),
        "atenciones": atenciones,
        "cobertura_57": cobertura_57(usuario, atenciones) if usuario else None,
    }


if __name__ == "__main__":
    doc = sys.argv[1] if len(sys.argv) > 1 else "1001"
    print(f"=== Historia unificada del documento {doc} ===")
    print(json.dumps(consultar_historia_unificada(doc), indent=2, ensure_ascii=False, default=str))
