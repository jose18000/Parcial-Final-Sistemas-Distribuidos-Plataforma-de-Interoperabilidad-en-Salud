"""
hsb/main.py
Servicio Health Service Bus (HSB) - Plataforma de Interoperabilidad Clínica.

Endpoints:
- POST /hsb/hl7          : Ingesta de texto plano HL7 v2 (ADT^A01, ORU^R01)
- POST /hsb/csv?sede=N   : Ingesta de CSV legado con separador ';'
- GET /health            : Estado del servicio y chequeo de dependencias
- GET /metrics           : Métricas operacionales (latencia, fallidos, duplicados)
- POST /hsb/reencolar/{id}: Reencolar mensaje en estado MUERTO
"""

import os
import time
import httpx
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Request, Query, Response, status
from fastapi.responses import JSONResponse

from hsb.parser_hl7 import parse_hl7_message
from hsb.parser_csv import parse_csv_rows
from hsb.validator import validar_mensaje_pre_transformacion
from hsb.queue_manager import (
    verificar_idempotencia,
    registrar_estado_mensaje,
    procesar_entrega_con_reintentos,
    reencolar_mensaje,
    HAPI_FHIR_URL,
    DB_NODOS_CFG,
    obtener_conexion_db
)
from hsb.metrics import metrics
from fhir.normalizer import construir_bundle_transaccional

app = FastAPI(
    title="Health Service Bus (HSB)",
    description="Bus de Servicios de Salud e Interoperabilidad Clínica (HL7 v2 / CSV -> FHIR R4)",
    version="1.0.0"
)


@app.post("/hsb/hl7")
async def recibir_hl7(request: Request):
    """Recibe un mensaje HL7 v2 en texto plano (ADT^A01 u ORU^R01)."""
    t_inicio = time.time()
    metrics.registrar_recibido()

    body_bytes = await request.body()
    raw_text = body_bytes.decode("utf-8", errors="replace")

    if not raw_text.strip():
        metrics.registrar_rechazado()
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"estado": "rechazado", "motivo": "El cuerpo del mensaje HL7 está vacío"}
        )

    try:
        parsed = parse_hl7_message(raw_text)
    except Exception as e:
        metrics.registrar_rechazado()
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"estado": "rechazado", "motivo": f"Error de sintaxis HL7: {str(e)}"}
        )

    mensaje_id = parsed["mensaje_id"]
    sede_id = parsed["sede_origen"] or 1
    hash_contenido = parsed["hash_contenido"]

    # 1. Control de Idempotencia Persistente
    existente = verificar_idempotencia(mensaje_id, hash_contenido, sede_id)
    if existente and existente.get("estado") == "ENTREGADO":
        metrics.registrar_duplicado()
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "estado": "duplicado",
                "mensaje_id": mensaje_id,
                "bundle_id": existente.get("bundle_id"),
                "motivo": "Mensaje procesado previamente. Idempotencia garantizada, no se duplicó el paciente ni la atención."
            }
        )

    # 2. Validación Estricta Previa a la Transformación
    es_valido, motivos = validar_mensaje_pre_transformacion(parsed)
    if not es_valido:
        metrics.registrar_rechazado()
        motivos_str = "; ".join(motivos)
        registrar_estado_mensaje(
            mensaje_id=mensaje_id,
            formato="HL7_V2",
            sede_id=sede_id,
            tipo_mensaje=parsed.get("tipo_mensaje", "ADT"),
            estado="RECHAZADO",
            hash_contenido=hash_contenido,
            motivo_rechazo=motivos_str
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "estado": "rechazado",
                "mensaje_id": mensaje_id,
                "total_motivos": len(motivos),
                "motivos": motivos
            }
        )

    # 3. Transformación Normalizada a Bundle FHIR R4
    try:
        bundle = construir_bundle_transaccional(
            usuario=parsed["usuario"],
            atenciones=[parsed["atencion"]],
            diagnosticos=parsed.get("diagnosticos"),
            tecnologias=parsed.get("tecnologias")
        )
    except Exception as e:
        metrics.registrar_rechazado()
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"estado": "rechazado", "motivo": f"Fallo al normalizar a FHIR R4: {str(e)}"}
        )

    # 4. Enrutamiento y Entrega con Reintentos
    resultado = procesar_entrega_con_reintentos(parsed, bundle)
    codigo_http = (
        status.HTTP_200_OK if resultado.get("estado") == "entregado"
        else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return JSONResponse(status_code=codigo_http, content=resultado)


@app.post("/hsb/csv")
async def recibir_csv(
    request: Request,
    sede: int = Query(..., description="ID de la sede que emite el CSV legado (1 a 3)")
):
    """Recibe un archivo CSV legado con separador ';' para la sede indicada."""
    body_bytes = await request.body()
    content = body_bytes.decode("utf-8", errors="replace")

    if not content.strip():
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"estado": "rechazado", "motivo": "Contenido CSV vacío"}
        )

    rows = parse_csv_rows(content, sede)
    total = len(rows)
    entregados = []
    rechazados = []
    duplicados = []

    for r in rows:
        metrics.registrar_recibido()
        mensaje_id = r["mensaje_id"]
        hash_fila = r["hash_contenido"]

        # Idempotencia por fila
        existente = verificar_idempotencia(mensaje_id, hash_fila, sede)
        if existente and existente.get("estado") == "ENTREGADO":
            metrics.registrar_duplicado()
            duplicados.append({
                "fila": r["fila_indice"],
                "documento": r["usuario"].get("documento_id"),
                "motivo": "Fila procesada previamente (duplicada)"
            })
            continue

        # Validación
        es_valido, motivos = validar_mensaje_pre_transformacion(r)
        if not es_valido:
            metrics.registrar_rechazado()
            motivos_str = "; ".join(motivos)
            registrar_estado_mensaje(
                mensaje_id=mensaje_id,
                formato="CSV",
                sede_id=sede,
                tipo_mensaje="CSV_ROW",
                estado="RECHAZADO",
                hash_contenido=hash_fila,
                motivo_rechazo=motivos_str
            )
            rechazados.append({
                "fila": r["fila_indice"],
                "documento": r["usuario"].get("documento_id"),
                "motivos": motivos
            })
            continue

        # Transformación a FHIR
        try:
            bundle = construir_bundle_transaccional(
                usuario=r["usuario"],
                atenciones=[r["atencion"]],
                diagnosticos=r.get("diagnosticos"),
                tecnologias=r.get("tecnologias")
            )
            res = procesar_entrega_con_reintentos(r, bundle)
            if res.get("estado") == "entregado":
                entregados.append({
                    "fila": r["fila_indice"],
                    "documento": r["usuario"].get("documento_id"),
                    "bundle_id": res.get("bundle_id")
                })
            else:
                rechazados.append({
                    "fila": r["fila_indice"],
                    "documento": r["usuario"].get("documento_id"),
                    "motivo": res.get("motivo")
                })
        except Exception as e:
            metrics.registrar_rechazado()
            rechazados.append({
                "fila": r["fila_indice"],
                "documento": r["usuario"].get("documento_id"),
                "motivo": f"Error de normalización: {str(e)}"
            })

    return {
        "estado": "procesado",
        "sede": sede,
        "total_filas": total,
        "total_entregados": len(entregados),
        "total_rechazados": len(rechazados),
        "total_duplicados": len(duplicados),
        "entregados": entregados,
        "rechazados": rechazados,
        "duplicados": duplicados
    }


@app.get("/health")
def healthcheck():
    """Verifica la salud del HSB y el estado de sus dependencias externas."""
    # 1. HAPI FHIR
    hapi_ok = False
    try:
        r = httpx.get(f"{HAPI_FHIR_URL}/metadata", timeout=2.0)
        hapi_ok = r.status_code == 200
    except Exception:
        hapi_ok = False

    # 2. PostgreSQL Sedes 1, 2, 3
    db_status = {}
    for sede_id in (1, 2, 3):
        conn = obtener_conexion_db(sede_id)
        if conn:
            db_status[f"sede_{sede_id}"] = "CONECTADO"
            conn.close()
        else:
            db_status[f"sede_{sede_id}"] = "DESCONECTADO_O_LOCAL"

    servicios_ok = hapi_ok and any(v == "CONECTADO" for v in db_status.values())

    return {
        "status": "UP" if hapi_ok else "DEGRADED",
        "hsb_service": "UP",
        "timestamp": time.time(),
        "dependencias": {
            "hapi_fhir_r4": "UP" if hapi_ok else "DOWN",
            "nodos_postgresql": db_status
        }
    }


@app.get("/metrics")
def obtener_metricas():
    """Expone contadores operacionales y métricas de rendimiento."""
    return metrics.obtener_metricas()


@app.post("/hsb/reencolar/{mensaje_id}")
def reencolar(mensaje_id: str):
    """Reencola manualmente un mensaje en estado MUERTO."""
    return reencolar_mensaje(mensaje_id)
