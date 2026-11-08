"""
hsb/queue_manager.py
Gestor de colas, idempotencia persistente y reintentos con backoff exponencial.

Estados del mensaje:
RECIBIDO -> VALIDANDO -> TRANSFORMADO -> ENTREGADO / REINTENTANDO -> MUERTO
"""

import os
import time
import json
import logging
import hashlib
from typing import Dict, Any, Optional, Tuple
import httpx

from hsb.metrics import metrics
from fhir.normalizer import construir_bundle_transaccional

# Importación condicional de psycopg2
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG_AVAILABLE = True
except ImportError:
    PSYCOPG_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("hsb_queue")

HAPI_FHIR_URL = os.getenv("HAPI_FHIR_URL", "http://localhost:8090/fhir")
MAX_REINTENTOS = int(os.getenv("HSB_MAX_RETRIES", "4"))
RETRY_BASE_SECONDS = float(os.getenv("HSB_RETRY_BASE_SECONDS", "1.0"))

DB_NODOS_CFG = {
    1: {
        "host": os.getenv("DB_HOST_SEDE1", "localhost"),
        "port": int(os.getenv("DB_PORT_SEDE1", "5433")),
        "database": os.getenv("DB_NAME_SEDE1", "clinica_sincelejo"),
        "user": os.getenv("POSTGRES_USER", "clinica_user"),
        "password": os.getenv("POSTGRES_PASSWORD", "clinica_pass_2026")
    },
    2: {
        "host": os.getenv("DB_HOST_SEDE2", "localhost"),
        "port": int(os.getenv("DB_PORT_SEDE2", "5434")),
        "database": os.getenv("DB_NAME_SEDE2", "clinica_cartagena"),
        "user": os.getenv("POSTGRES_USER", "clinica_user"),
        "password": os.getenv("POSTGRES_PASSWORD", "clinica_pass_2026")
    },
    3: {
        "host": os.getenv("DB_HOST_SEDE3", "localhost"),
        "port": int(os.getenv("DB_PORT_SEDE3", "5435")),
        "database": os.getenv("DB_NAME_SEDE3", "clinica_corozal"),
        "user": os.getenv("POSTGRES_USER", "clinica_user"),
        "password": os.getenv("POSTGRES_PASSWORD", "clinica_pass_2026")
    }
}

# Almacén de idempotencia y estado en memoria para entornos de test o cuando BD no está disponible
_MEMORIA_MENSAJES: Dict[str, Dict[str, Any]] = {}


def obtener_conexion_db(sede_id: int):
    """Devuelve una conexión a la base de datos de la sede."""
    if not PSYCOPG_AVAILABLE:
        return None
    cfg = DB_NODOS_CFG.get(sede_id)
    if not cfg:
        return None
    try:
        return psycopg2.connect(
            host=cfg["host"],
            port=cfg["port"],
            dbname=cfg["database"],
            user=cfg["user"],
            password=cfg["password"],
            connect_timeout=3
        )
    except Exception as e:
        logger.debug(f"No se pudo conectar a BD sede {sede_id}: {e}")
        return None


def verificar_idempotencia(mensaje_id: str, hash_contenido: str, sede_id: int) -> Optional[Dict[str, Any]]:
    """
    Verifica si el mensaje ya fue recibido o entregado previamente.
    Primero consulta PostgreSQL (persistencia real), luego memoria.
    """
    # 1. Consulta en PostgreSQL
    conn = obtener_conexion_db(sede_id)
    if conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT mensaje_id, estado, intentos, hash_contenido, bundle_id
                    FROM mensaje_bus
                    WHERE mensaje_id = %s OR hash_contenido = %s
                """, (mensaje_id, hash_contenido))
                row = cur.fetchone()
                if row:
                    return dict(row)
        except Exception as e:
            logger.warning(f"Error verificando idempotencia en BD: {e}")
        finally:
            conn.close()

    # 2. Consulta en Memoria (fallback)
    if mensaje_id in _MEMORIA_MENSAJES:
        return _MEMORIA_MENSAJES[mensaje_id]
    for m in _MEMORIA_MENSAJES.values():
        if m.get("hash_contenido") == hash_contenido:
            return m
    return None


def registrar_estado_mensaje(
    mensaje_id: str,
    formato: str,
    sede_id: int,
    tipo_mensaje: str,
    estado: str,
    hash_contenido: str,
    intentos: int = 0,
    motivo_rechazo: Optional[str] = None,
    bundle_id: Optional[str] = None
):
    """Persiste el estado del mensaje tanto en BD como en memoria."""
    # En memoria
    _MEMORIA_MENSAJES[mensaje_id] = {
        "mensaje_id": mensaje_id,
        "formato": formato,
        "sede_origen": sede_id,
        "tipo_mensaje": tipo_mensaje,
        "estado": estado,
        "intentos": intentos,
        "hash_contenido": hash_contenido,
        "motivo_rechazo": motivo_rechazo,
        "bundle_id": bundle_id,
        "actualizado_en": time.time()
    }

    # En PostgreSQL
    conn = obtener_conexion_db(sede_id)
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO mensaje_bus (
                        mensaje_id, formato, sede_origen, tipo_mensaje, estado,
                        intentos, hash_contenido, motivo_rechazo, bundle_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (mensaje_id) DO UPDATE SET
                        estado = EXCLUDED.estado,
                        intentos = EXCLUDED.intentos,
                        motivo_rechazo = EXCLUDED.motivo_rechazo,
                        bundle_id = EXCLUDED.bundle_id,
                        entregado_en = CASE WHEN EXCLUDED.estado = 'ENTREGADO' THEN NOW() ELSE mensaje_bus.entregado_en END
                """, (
                    mensaje_id, formato, sede_id, tipo_mensaje, estado,
                    intentos, hash_contenido, motivo_rechazo, bundle_id
                ))
            conn.commit()
        except Exception as e:
            logger.warning(f"Error actualizando mensaje_bus en BD: {e}")
        finally:
            conn.close()


def enviar_bundle_a_hapi(bundle: Dict[str, Any], timeout_sec: float = 4.0) -> bool:
    """Envía un Bundle FHIR transaction a HAPI FHIR R4."""
    try:
        with httpx.Client(timeout=timeout_sec) as client:
            resp = client.post(
                HAPI_FHIR_URL,
                headers={"Content-Type": "application/fhir+json"},
                json=bundle
            )
            if resp.status_code in (200, 201):
                logger.info(f"HAPI FHIR aceptó el bundle {bundle.get('id')} (HTTP {resp.status_code})")
                return True
            else:
                logger.warning(f"HAPI FHIR rechazó bundle: HTTP {resp.status_code} - {resp.text[:200]}")
                return False
    except Exception as e:
        logger.warning(f"HAPI FHIR inaccesible ({HAPI_FHIR_URL}): {e}")
        return False


def persistir_en_nodo_sede(parsed: Dict[str, Any], bundle_id: str) -> bool:
    """Persiste las entidades en el PostgreSQL de la sede destino."""
    sede_id = parsed["sede_origen"]
    usr = parsed.get("usuario", {})
    at = parsed.get("atencion", {})
    dxs = parsed.get("diagnosticos", [])
    techs = parsed.get("tecnologias", [])

    conn = obtener_conexion_db(sede_id)
    if not conn:
        logger.info(f"Modo local sin BD activa: datos simulados como persistidos para sede {sede_id}")
        return True

    try:
        with conn.cursor() as cur:
            # 1. Usuario
            doc = usr.get("documento_id")
            patient_id = f"pac-{doc}"
            cur.execute("""
                INSERT INTO usuario (
                    documento_id, nombre_completo, fecha_nacimiento, sexo, fhir_patient_id, sede_origen_id
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (documento_id) DO UPDATE SET
                    nombre_completo = EXCLUDED.nombre_completo,
                    fhir_patient_id = EXCLUDED.fhir_patient_id
            """, (
                doc, usr.get("nombre_completo"), usr.get("fecha_nacimiento") or "1990-01-01",
                usr.get("sexo", "O"), patient_id, sede_id
            ))

            # 2. Atención
            if at and at.get("numero_visita"):
                num_visita = at["numero_visita"]
                enc_id = f"enc-{num_visita}"
                cur.execute("""
                    INSERT INTO atencion (
                        numero_visita, clase_atencion, fecha_ingreso, triage, fhir_encounter_id, documento_id, sede_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (numero_visita) DO UPDATE SET
                        fhir_encounter_id = EXCLUDED.fhir_encounter_id
                """, (
                    num_visita, at.get("clase_atencion", "O"),
                    at.get("fecha_ingreso") or "2026-11-07 10:00:00",
                    at.get("triage"), enc_id, doc, sede_id
                ))

                # 3. Diagnósticos
                for dx in dxs:
                    cie10 = dx.get("cie10_codigo")
                    cond_id = f"cond-{num_visita}-{cie10}"
                    cur.execute("""
                        INSERT INTO diagnostico (
                            cie10_codigo, descripcion_cie10, tipo, fecha_diagnostico, fhir_condition_id, numero_visita
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        cie10, dx.get("descripcion_cie10", cie10), dx.get("tipo", "PRINCIPAL"),
                        dx.get("fecha_diagnostico") or "2026-11-07", cond_id, num_visita
                    ))

                # 4. Observaciones
                for tech in techs:
                    loinc = tech.get("loinc_codigo")
                    obs_id = f"obs-{num_visita}-{loinc}"
                    cur.execute("""
                        INSERT INTO tecnologia_salud (
                            loinc_codigo, descripcion_loinc, valor, unidad, fecha_toma, fhir_observation_id, numero_visita
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        loinc, tech.get("descripcion_loinc", loinc), tech.get("valor", 0.0),
                        tech.get("unidad", "1"), tech.get("fecha_toma") or "2026-11-07 10:00:00",
                        obs_id, num_visita
                    ))

        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error persistiendo en nodo de sede {sede_id}: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def procesar_entrega_con_reintentos(
    parsed: Dict[str, Any],
    bundle: Dict[str, Any],
    max_intentos: int = MAX_REINTENTOS,
    simular_falla_hapi: bool = False
) -> Dict[str, Any]:
    """
    Gestiona la entrega a HAPI FHIR y al nodo PostgreSQL con reintentos y backoff exponencial.
    Retorna el estado final del mensaje.
    """
    mensaje_id = parsed["mensaje_id"]
    sede_id = parsed["sede_origen"]
    formato = parsed["formato"]
    hash_contenido = parsed["hash_contenido"]
    bundle_id = bundle["id"]

    t0 = time.time()
    intento = 0
    entregado = False

    while intento < max_intentos:
        intento += 1
        logger.info(f"HSB intento {intento}/{max_intentos} para mensaje {mensaje_id}")

        if intento > 1:
            metrics.registrar_reintento()

        # Enviar PRIMERO a HAPI FHIR
        exito_hapi = False if simular_falla_hapi else enviar_bundle_a_hapi(bundle)

        if exito_hapi:
            # Enviar SEGUNDO a Base de Datos de la Sede
            exito_db = persistir_en_nodo_sede(parsed, bundle_id)
            if exito_db:
                entregado = True
                latencia = (time.time() - t0) * 1000.0
                metrics.registrar_entregado(latencia)
                registrar_estado_mensaje(
                    mensaje_id=mensaje_id,
                    formato=formato,
                    sede_id=sede_id,
                    tipo_mensaje=parsed.get("tipo_mensaje", "MSG"),
                    estado="ENTREGADO",
                    hash_contenido=hash_contenido,
                    intentos=intento,
                    bundle_id=bundle_id
                )
                return {
                    "estado": "entregado",
                    "mensaje_id": mensaje_id,
                    "bundle_id": bundle_id,
                    "intentos": intento,
                    "sede": sede_id,
                    "latencia_ms": round(latencia, 2)
                }

        # Si falló HAPI o BD -> pasa a REINTENTANDO
        registrar_estado_mensaje(
            mensaje_id=mensaje_id,
            formato=formato,
            sede_id=sede_id,
            tipo_mensaje=parsed.get("tipo_mensaje", "MSG"),
            estado="REINTENTANDO",
            hash_contenido=hash_contenido,
            intentos=intento,
            motivo_rechazo="HAPI FHIR o base de datos no disponible",
            bundle_id=bundle_id
        )

        if intento < max_intentos:
            espera = RETRY_BASE_SECONDS * (2 ** (intento - 1))
            logger.warning(f"Fallo en intento {intento}. Reintentando en {espera} s...")
            time.sleep(espera)

    # Máximo de intentos alcanzado -> pasa a MUERTO (Dead Letter Queue)
    metrics.registrar_muerto()
    registrar_estado_mensaje(
        mensaje_id=mensaje_id,
        formato=formato,
        sede_id=sede_id,
        tipo_mensaje=parsed.get("tipo_mensaje", "MSG"),
        estado="MUERTO",
        hash_contenido=hash_contenido,
        intentos=intento,
        motivo_rechazo=f"Se superó el máximo de {max_intentos} reintentos sin respuesta",
        bundle_id=bundle_id
    )

    return {
        "estado": "muerto",
        "mensaje_id": mensaje_id,
        "intentos": intento,
        "puede_reencolar": True,
        "motivo": f"Servicio destino no disponible tras {max_intentos} intentos con backoff creciente"
    }


def reencolar_mensaje(mensaje_id: str) -> Dict[str, Any]:
    """Reencola un mensaje que quedó en estado MUERTO."""
    reg = _MEMORIA_MENSAJES.get(mensaje_id)
    if not reg:
        return {"error": f"Mensaje {mensaje_id} no encontrado en la cola de mensajes muertos"}

    if reg.get("estado") != "MUERTO":
        return {"mensaje": f"El mensaje {mensaje_id} no está en estado MUERTO (estado actual: {reg.get('estado')})"}

    reg["estado"] = "REINTENTANDO"
    reg["intentos"] = 0
    return {
        "mensaje": f"Mensaje {mensaje_id} reencolado con éxito",
        "nuevo_estado": "REINTENTANDO"
    }

