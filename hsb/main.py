"""
hsb/main.py
Health Service Bus (HSB) — Plataforma de Interoperabilidad Clínica.

Entradas (guía Fase 3, paso 2):
  POST /hsb/hl7            HL7 v2 en texto plano (ADT^A01, ORU^R01, RDE^O11)
  POST /hsb/csv?sede=N     CSV legado con separador ';'
  POST /hsb/json?sede=N    Registro JSON (lo usan las vistas de admisión y médico)
Operación:
  GET  /hsb/mensajes       Estado de los mensajes de las 3 sedes (monitor)
  POST /hsb/reencolar/{id} Saca un mensaje de la cola de muertos
  GET  /hsb/catalogo       Los 57 campos y su mapeo HL7/CSV/PostgreSQL/MongoDB/FHIR
  GET  /health             Estado del bus y de sus dependencias
  GET  /metrics            Contadores, latencia, % fallidos, duplicados

Seguridad (hsb/autorizacion.py): las entradas exigen un token OAuth 2.0 con scope hsb.ingesta y
la operación (mensajes, reencolar, migrar) exige hsb.admin. Con TLS_ACTIVO el bus sirve HTTPS.
"""

import json
import time
from dataclasses import asdict
from typing import Any, Dict, Optional

import httpx
from fastapi import Depends, FastAPI, Query, Request, status
from fastapi.responses import JSONResponse

from traductor.traductor import desde_hl7, desde_json
from traductor.catalogo_57 import CAMPOS_57, SEDES
from hsb.parser_csv import parse_csv_rows
from hsb.ingesta import procesar, contenido_csv, meta_json
from hsb.queue_manager import (HAPI_FHIR_URL, COLA, MAX_REINTENTOS, RETRY_BASE_SECONDS, reencolar_mensaje,
                               recuperar_pendientes, listar_mensajes, contar_por_estado)
from hsb.metrics import metrics
from db.repositorio import todos_los_repositorios
from hsb.autorizacion import requerir, verificar_sede
from seguridad import tls

app = FastAPI(title="Health Service Bus (HSB)",
              description="Bus de servicios de salud: HL7 v2 / CSV / JSON -> traductor 57 campos -> FHIR R4",
              version="2.0.0")

CODIGO_HTTP = {"entregado": 200, "duplicado": 200, "reintentando": 202, "rechazado": 422, "muerto": 503}


@app.on_event("startup")
def arrancar():
    COLA.iniciar()
    recuperar_pendientes()


def _respuesta(resultado: Dict[str, Any]) -> JSONResponse:
    return JSONResponse(status_code=CODIGO_HTTP.get(resultado.get("estado"), 200), content=resultado)


@app.post("/hsb/hl7")
async def recibir_hl7(request: Request, claims: Dict[str, Any] = Depends(requerir("hsb.ingesta"))):
    raw = (await request.body()).decode("utf-8", errors="replace")
    if not raw.strip():
        metrics.registrar_rechazado()
        return JSONResponse(status_code=400, content={"estado": "rechazado", "motivo": "El mensaje HL7 está vacío"})
    try:
        meta, reg = desde_hl7(raw)
    except Exception as e:
        metrics.registrar_rechazado()
        return JSONResponse(status_code=422, content={"estado": "rechazado", "motivo": f"Error de sintaxis HL7: {e}"})
    verificar_sede(claims, meta.get("sede_origen"))
    return _respuesta(procesar(meta, reg, raw.strip()))


@app.post("/hsb/csv")
async def recibir_csv(request: Request, sede: int = Query(..., description="Sede que envía el CSV (1 a 3)"),
                      claims: Dict[str, Any] = Depends(requerir("hsb.ingesta"))):
    verificar_sede(claims, sede)
    contenido = (await request.body()).decode("utf-8", errors="replace")
    if not contenido.strip():
        return JSONResponse(status_code=400, content={"estado": "rechazado", "motivo": "Contenido CSV vacío"})
    if sede not in SEDES:
        return JSONResponse(status_code=422, content={"estado": "rechazado", "motivo": f"Sede {sede} no existe"})

    filas = parse_csv_rows(contenido, sede)
    resumen: Dict[str, list] = {"entregados": [], "rechazados": [], "duplicados": [], "reintentando": [], "muertos": []}
    for f in filas:
        reg = {k: f[k] for k in ("usuario", "atencion", "tecnologias", "diagnosticos", "egreso", "_observaciones")}
        if f.get("dx_local_error"):
            reg["dx_local_error"] = f["dx_local_error"]
        meta = {k: f[k] for k in ("formato", "mensaje_id", "tipo_mensaje", "sede_origen", "sede_raw", "hash_contenido")}
        res = procesar(meta, reg, contenido_csv(f["encabezado"], f["linea"]))
        item = {"fila": f["fila_indice"], "documento": f["usuario"].get("documento_id"), "mensaje_id": f["mensaje_id"]}
        clave = {"entregado": "entregados", "rechazado": "rechazados", "duplicado": "duplicados",
                 "reintentando": "reintentando", "muerto": "muertos"}[res["estado"]]
        if res["estado"] == "rechazado":
            item["motivos"] = res.get("motivos")
        elif res["estado"] in ("reintentando", "muerto"):
            item["motivo"] = res.get("motivo")
        else:
            item["bundle_id"] = res.get("bundle_id")
        resumen[clave].append(item)

    return {"estado": "procesado", "sede": sede, "total_filas": len(filas),
            **{f"total_{k}": len(v) for k, v in resumen.items()}, **resumen}


@app.post("/hsb/json")
async def recibir_json(request: Request, sede: int = Query(..., description="Sede destino (1 a 3)"),
                       claims: Dict[str, Any] = Depends(requerir("hsb.ingesta"))):
    verificar_sede(claims, sede)
    try:
        obj = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"estado": "rechazado", "motivo": "JSON mal formado"})
    if sede not in SEDES:
        return JSONResponse(status_code=422, content={"estado": "rechazado", "motivo": f"Sede {sede} no existe"})
    meta = meta_json(obj, sede)
    reg = desde_json(obj.get("registro", obj), sede)
    return _respuesta(procesar(meta, reg, json.dumps(obj, ensure_ascii=False)))


@app.get("/hsb/mensajes", dependencies=[Depends(requerir("hsb.admin"))])
def mensajes(limite: int = 50, estado: Optional[str] = None):
    return listar_mensajes(limite, estado.upper() if estado else None)


@app.post("/hsb/reencolar/{mensaje_id}", dependencies=[Depends(requerir("hsb.admin"))])
def reencolar(mensaje_id: str):
    return reencolar_mensaje(mensaje_id)


@app.post("/hsb/migrar", dependencies=[Depends(requerir("hsb.admin"))])
def migrar_a_fhir(sede: Optional[int] = None):
    """Publica en FHIR los registros legados de una sede (o de las 3) que aún no lo estén."""
    from hsb.migracion import migrar
    if sede is not None and sede not in SEDES:
        return JSONResponse(status_code=422, content={"error": f"Sede {sede} no existe"})
    return migrar(sede)


@app.get("/hsb/catalogo")
def catalogo():
    return {"total": len(CAMPOS_57), "campos": [asdict(c) for c in CAMPOS_57], "sedes": SEDES}


@app.get("/health")
def healthcheck():
    try:
        hapi_ok = httpx.get(f"{HAPI_FHIR_URL}/metadata", timeout=3.0, verify=tls.verificacion_http()).status_code == 200
    except Exception:
        hapi_ok = False
    sedes = {f"sede_{r.sede_id}": {"motor": r.motor, "estado": "UP" if r.ping() else "DOWN"}
             for r in todos_los_repositorios()}
    todo_ok = hapi_ok and all(s["estado"] == "UP" for s in sedes.values())
    return {"status": "UP" if todo_ok else "DEGRADED", "servicio": "hsb", "timestamp": time.time(),
            "dependencias": {"hapi_fhir_r4": "UP" if hapi_ok else "DOWN", "sedes": sedes},
            "cola_reintentos": len(COLA.pendientes())}


@app.get("/metrics")
def obtener_metricas():
    datos = metrics.obtener_metricas()
    datos["mensajes_por_estado_persistidos"] = contar_por_estado()
    datos["pendientes_en_cola_reintentos"] = len(COLA.pendientes())
    datos["configuracion_reintentos"] = {"max_intentos": MAX_REINTENTOS, "espera_base_s": RETRY_BASE_SECONDS}
    return datos
