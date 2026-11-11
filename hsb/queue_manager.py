"""
hsb/queue_manager.py
Cola del HSB: idempotencia persistente, entrega (HAPI primero, sede después),
reintentos con espera creciente en segundo plano y cola de mensajes muertos.

Estados del mensaje (diagrama de estados de la Fase 1):

    RECIBIDO -> VALIDADO -> TRANSFORMADO -> ENTREGADO
        |                        |
        v                        v
    RECHAZADO               REINTENTANDO --(máx. intentos)--> MUERTO --(reencolar)--> REINTENTANDO

Por qué no duplica:
  - HAPI recibe un Bundle `transaction` con PUT e ids deterministas: repetirlo sobrescribe.
  - La sede hace UPSERT por las mismas llaves deterministas (PostgreSQL ON CONFLICT /
    MongoDB replace_one por _id).
  - El estado del mensaje vive en la base de su sede (mensaje_bus), con MSH-10 o el hash
    de la fila CSV como llave: sobrevive a reinicios del bus.
  - Si el bus cae entre "HAPI OK" y "sede OK", al reiniciar recupera el mensaje en
    REINTENTANDO y lo repite completo: ambos pasos son idempotentes.
"""

import os
import json
import time
import heapq
import logging
import threading
from typing import Any, Dict, List, Optional, Tuple

import httpx

from hsb.metrics import metrics
from db.repositorio import obtener_repositorio, todos_los_repositorios, marcar_ids_fhir
from fhir.normalizer import bundle_desde_registro

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("hsb_queue")

HAPI_FHIR_URL = os.getenv("HAPI_FHIR_URL", "http://localhost:8090/fhir")
MAX_REINTENTOS = int(os.getenv("HSB_MAX_RETRIES", "7"))
RETRY_BASE_SECONDS = float(os.getenv("HSB_RETRY_BASE_SECONDS", "2.0"))

# Copia en memoria del último estado conocido de cada mensaje: respaldo cuando la base de
# la sede está caída (el estado se vuelve a persistir en cuanto la sede responde).
_MEMORIA_MENSAJES: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()


# ══════════════════════════════════════════════════════════════════════════
# Estado del mensaje
# ══════════════════════════════════════════════════════════════════════════

def _sede_registro(sede_id: Optional[int]) -> int:
    """Los mensajes con sede inválida se registran (rechazados) en el nodo 1 con sede_origen 0."""
    return sede_id if sede_id in (1, 2, 3) else 1


def registrar_estado_mensaje(mensaje_id: str, formato: str, sede_id: Optional[int], tipo_mensaje: str,
                             estado: str, hash_contenido: str, intentos: int = 0,
                             motivo_rechazo: Optional[str] = None, bundle_id: Optional[str] = None,
                             contenido: Optional[str] = None) -> bool:
    """Persiste el estado en la base de la sede (PostgreSQL o MongoDB). Devuelve si quedó persistido."""
    msg = {"mensaje_id": mensaje_id, "formato": formato, "sede_origen": sede_id or 0,
           "tipo_mensaje": tipo_mensaje or "MSG", "estado": estado, "intentos": intentos,
           "hash_contenido": hash_contenido, "motivo_rechazo": motivo_rechazo, "bundle_id": bundle_id,
           "contenido": contenido}
    with _LOCK:
        previo = _MEMORIA_MENSAJES.get(mensaje_id, {})
        _MEMORIA_MENSAJES[mensaje_id] = {**previo, **{k: v for k, v in msg.items() if v is not None},
                                         "estado": estado, "intentos": intentos,
                                         "motivo_rechazo": motivo_rechazo, "actualizado_en": time.time(),
                                         "persistido": False}
    try:
        obtener_repositorio(_sede_registro(sede_id)).registrar_mensaje(msg)
        _MEMORIA_MENSAJES[mensaje_id]["persistido"] = True
        return True
    except Exception as e:
        logger.warning(f"No se pudo persistir el estado de {mensaje_id} en la sede {sede_id}: {e}")
        return False


def verificar_idempotencia(mensaje_id: str, hash_contenido: str, sede_id: Optional[int]) -> Optional[Dict[str, Any]]:
    """Busca el mensaje por id o por hash del contenido: primero en la base de la sede, luego en memoria."""
    try:
        encontrado = obtener_repositorio(_sede_registro(sede_id)).buscar_mensaje(mensaje_id, hash_contenido)
        if encontrado:
            return encontrado
    except Exception as e:
        logger.warning(f"Idempotencia: sede {sede_id} no disponible, se consulta la memoria ({e})")
    if mensaje_id in _MEMORIA_MENSAJES:
        return _MEMORIA_MENSAJES[mensaje_id]
    return next((m for m in _MEMORIA_MENSAJES.values() if m.get("hash_contenido") == hash_contenido), None)


# ══════════════════════════════════════════════════════════════════════════
# Entrega
# ══════════════════════════════════════════════════════════════════════════

def enviar_bundle_a_hapi(bundle: Dict[str, Any], timeout_sec: float = 8.0) -> Tuple[bool, str]:
    try:
        with httpx.Client(timeout=timeout_sec) as client:
            resp = client.post(HAPI_FHIR_URL, headers={"Content-Type": "application/fhir+json"}, json=bundle)
        if resp.status_code in (200, 201):
            logger.info(f"HAPI FHIR aceptó el bundle {bundle.get('id')} (HTTP {resp.status_code})")
            return True, "ok"
        detalle = resp.text[:300]
        logger.warning(f"HAPI FHIR rechazó el bundle: HTTP {resp.status_code} - {detalle}")
        return False, f"HAPI respondió HTTP {resp.status_code}: {detalle}"
    except Exception as e:
        logger.warning(f"HAPI FHIR inaccesible ({HAPI_FHIR_URL}): {e}")
        return False, f"HAPI FHIR no disponible: {e.__class__.__name__}"


ERRORES_DE_DATOS = ("IntegrityError", "DataError", "NotNullViolation", "CheckViolation", "ForeignKeyViolation",
                    "InvalidTextRepresentation", "DuplicateKeyError", "WriteError", "DocumentTooLarge")
PERMANENTE = "[permanente] "


def intentar_entrega(reg: Dict[str, Any], bundle: Dict[str, Any], sede_id: int) -> Tuple[bool, str]:
    """
    Un intento: HAPI primero y después la base de la sede (guía Fase 3, paso 6).
    Un error de DATOS (restricción violada, HTTP 4xx de HAPI) no se arregla reintentando:
    se marca como permanente y el mensaje va directo a MUERTO con su motivo.
    """
    ok, motivo = enviar_bundle_a_hapi(bundle)
    if not ok:
        if motivo.startswith("HAPI respondió HTTP 4"):
            return False, PERMANENTE + motivo
        return False, motivo
    try:
        obtener_repositorio(sede_id).guardar(marcar_ids_fhir(reg))
        return True, "ok"
    except Exception as e:
        texto = str(e).splitlines()[0][:200] if str(e) else e.__class__.__name__
        # Errores de datos (psycopg2.IntegrityError/DataError y subclases, pymongo WriteError...).
        # Las caídas (OperationalError, ServerSelectionTimeoutError, ConnectionError) sí se reintentan.
        if any(t in c.__name__ for c in type(e).__mro__ for t in ERRORES_DE_DATOS):
            logger.error(f"Sede {sede_id} rechazó los datos (no se reintenta): {texto}")
            return False, f"{PERMANENTE}La sede {sede_id} rechazó los datos: {texto}"
        logger.warning(f"Sede {sede_id} no disponible para guardar: {texto}")
        return False, f"Base de la sede {sede_id} no disponible: {texto}"


# ══════════════════════════════════════════════════════════════════════════
# Trabajador de reintentos (segundo plano)
# ══════════════════════════════════════════════════════════════════════════

class ColaReintentos:
    """Cola por prioridad de tiempo: (momento_del_próximo_intento, mensaje_id)."""

    def __init__(self):
        self._heap: List[Tuple[float, str]] = []
        self._trabajos: Dict[str, Dict[str, Any]] = {}
        self._cv = threading.Condition()
        self._hilo: Optional[threading.Thread] = None

    def iniciar(self):
        if self._hilo and self._hilo.is_alive():
            return
        self._hilo = threading.Thread(target=self._bucle, name="hsb-reintentos", daemon=True)
        self._hilo.start()

    def programar(self, trabajo: Dict[str, Any], espera: float):
        with self._cv:
            self._trabajos[trabajo["mensaje_id"]] = trabajo
            heapq.heappush(self._heap, (time.time() + espera, trabajo["mensaje_id"]))
            self._cv.notify()

    def pendientes(self) -> List[str]:
        return list(self._trabajos)

    def _bucle(self):
        while True:
            with self._cv:
                while not self._heap or self._heap[0][0] > time.time():
                    self._cv.wait(timeout=(self._heap[0][0] - time.time()) if self._heap else 5)
                _, mid = heapq.heappop(self._heap)
                trabajo = self._trabajos.pop(mid, None)
            if trabajo:
                try:
                    _reintentar(trabajo)
                except Exception as e:
                    logger.exception(f"Error inesperado reintentando {mid}: {e}")


COLA = ColaReintentos()


def _espera(intento: int) -> float:
    """1 s, 2 s, 4 s, 8 s... (base configurable con HSB_RETRY_BASE_SECONDS)."""
    return RETRY_BASE_SECONDS * (2 ** (intento - 1))


def _reintentar(t: Dict[str, Any]):
    t["intentos"] += 1
    metrics.registrar_reintento()
    logger.info(f"HSB reintento {t['intentos']}/{t['max_intentos']} del mensaje {t['mensaje_id']}")
    ok, motivo = intentar_entrega(t["registro"], t["bundle"], t["sede_id"])
    if ok:
        latencia = (time.time() - t["t0"]) * 1000.0
        metrics.registrar_entregado(latencia)
        registrar_estado_mensaje(t["mensaje_id"], t["formato"], t["sede_id"], t["tipo_mensaje"], "ENTREGADO",
                                 t["hash_contenido"], t["intentos"], None, t["bundle"]["id"], t.get("contenido"))
        logger.info(f"Mensaje {t['mensaje_id']} ENTREGADO tras {t['intentos']} intentos ({latencia:.0f} ms)")
        return
    if t["intentos"] >= t["max_intentos"] or motivo.startswith(PERMANENTE):
        metrics.registrar_muerto()
        registrar_estado_mensaje(t["mensaje_id"], t["formato"], t["sede_id"], t["tipo_mensaje"], "MUERTO",
                                 t["hash_contenido"], t["intentos"],
                                 motivo if motivo.startswith(PERMANENTE) else
                                 f"Superó {t['max_intentos']} intentos. Último error: {motivo}",
                                 t["bundle"]["id"], t.get("contenido"))
        logger.error(f"Mensaje {t['mensaje_id']} pasa a MUERTO (cola de mensajes muertos): {motivo}")
        return
    espera = _espera(t["intentos"])
    registrar_estado_mensaje(t["mensaje_id"], t["formato"], t["sede_id"], t["tipo_mensaje"], "REINTENTANDO",
                             t["hash_contenido"], t["intentos"], motivo, t["bundle"]["id"], t.get("contenido"))
    logger.warning(f"Intento {t['intentos']} de {t['mensaje_id']} falló ({motivo}). Siguiente en {espera:.0f} s")
    COLA.programar(t, espera)


# ══════════════════════════════════════════════════════════════════════════
# Flujo principal
# ══════════════════════════════════════════════════════════════════════════

def procesar_entrega_con_reintentos(meta: Dict[str, Any], reg: Dict[str, Any], bundle: Dict[str, Any],
                                    contenido: Optional[str] = None,
                                    max_intentos: int = MAX_REINTENTOS) -> Dict[str, Any]:
    """
    Primer intento sincrónico. Si falla, el mensaje queda en REINTENTANDO (persistido) y el
    trabajador en segundo plano lo sigue intentando con espera creciente hasta entregarlo o
    declararlo MUERTO.
    """
    mid, sede = meta["mensaje_id"], meta["sede_origen"]
    t0 = time.time()
    registrar_estado_mensaje(mid, meta["formato"], sede, meta["tipo_mensaje"], "TRANSFORMADO",
                             meta["hash_contenido"], 0, None, bundle["id"], contenido)
    ok, motivo = intentar_entrega(reg, bundle, sede)
    if ok:
        latencia = (time.time() - t0) * 1000.0
        metrics.registrar_entregado(latencia)
        registrar_estado_mensaje(mid, meta["formato"], sede, meta["tipo_mensaje"], "ENTREGADO",
                                 meta["hash_contenido"], 1, None, bundle["id"], contenido)
        return {"estado": "entregado", "mensaje_id": mid, "bundle_id": bundle["id"], "intentos": 1,
                "sede": sede, "latencia_ms": round(latencia, 2)}

    trabajo = {"mensaje_id": mid, "formato": meta["formato"], "sede_id": sede, "tipo_mensaje": meta["tipo_mensaje"],
               "hash_contenido": meta["hash_contenido"], "registro": reg, "bundle": bundle, "contenido": contenido,
               "intentos": 1, "max_intentos": max_intentos, "t0": t0}
    if max_intentos <= 1 or motivo.startswith(PERMANENTE):
        metrics.registrar_muerto()
        registrar_estado_mensaje(mid, meta["formato"], sede, meta["tipo_mensaje"], "MUERTO", meta["hash_contenido"],
                                 1, motivo, bundle["id"], contenido)
        return {"estado": "muerto", "mensaje_id": mid, "intentos": 1, "motivo": motivo, "puede_reencolar": True}
    espera = _espera(1)
    registrar_estado_mensaje(mid, meta["formato"], sede, meta["tipo_mensaje"], "REINTENTANDO",
                             meta["hash_contenido"], 1, motivo, bundle["id"], contenido)
    logger.warning(f"Mensaje {mid}: intento 1 falló ({motivo}). Pasa a REINTENTANDO, siguiente en {espera:.0f} s")
    COLA.programar(trabajo, espera)
    return {"estado": "reintentando", "mensaje_id": mid, "bundle_id": bundle["id"], "intentos": 1,
            "max_intentos": max_intentos, "proximo_intento_s": espera, "motivo": motivo}


# ══════════════════════════════════════════════════════════════════════════
# Reencolar y recuperar tras reinicio
# ══════════════════════════════════════════════════════════════════════════

def _reconstruir(fila: Dict[str, Any]):
    """Vuelve a traducir el contenido original guardado del mensaje."""
    from hsb.ingesta import traducir_contenido  # import tardío para evitar ciclo
    return traducir_contenido(fila["formato"], fila.get("contenido") or "", fila.get("sede_origen"))


def _buscar_en_sedes(mensaje_id: str) -> Optional[Dict[str, Any]]:
    for repo in todos_los_repositorios():
        try:
            fila = repo.obtener_contenido(mensaje_id)
            if fila:
                return fila
        except Exception:
            continue
    return _MEMORIA_MENSAJES.get(mensaje_id)


def reencolar_mensaje(mensaje_id: str) -> Dict[str, Any]:
    """Saca un mensaje de la cola de muertos y lo vuelve a intentar desde cero."""
    fila = _buscar_en_sedes(mensaje_id)
    if not fila:
        return {"error": f"Mensaje {mensaje_id} no encontrado"}
    if fila.get("estado") != "MUERTO":
        return {"mensaje": f"El mensaje {mensaje_id} no está MUERTO (estado actual: {fila.get('estado')})"}
    if not fila.get("contenido"):
        return {"error": f"El mensaje {mensaje_id} no guardó su contenido original; no se puede reencolar"}
    meta, reg = _reconstruir(fila)
    bundle = bundle_desde_registro(reg)
    trabajo = {"mensaje_id": mensaje_id, "formato": fila["formato"], "sede_id": meta["sede_origen"],
               "tipo_mensaje": meta["tipo_mensaje"], "hash_contenido": fila["hash_contenido"], "registro": reg,
               "bundle": bundle, "contenido": fila["contenido"], "intentos": 0, "max_intentos": MAX_REINTENTOS,
               "t0": time.time()}
    registrar_estado_mensaje(mensaje_id, fila["formato"], meta["sede_origen"], meta["tipo_mensaje"], "REINTENTANDO",
                             fila["hash_contenido"], 0, "Reencolado manualmente desde la cola de muertos",
                             bundle["id"], fila["contenido"])
    COLA.programar(trabajo, 0)
    return {"mensaje": f"Mensaje {mensaje_id} reencolado", "nuevo_estado": "REINTENTANDO"}


def recuperar_pendientes() -> int:
    """Al arrancar el bus: vuelve a programar los mensajes que quedaron en REINTENTANDO o TRANSFORMADO."""
    n = 0
    for repo in todos_los_repositorios():
        for estado in ("REINTENTANDO", "TRANSFORMADO"):
            try:
                filas = repo.listar_mensajes(limite=500, estado=estado)
            except Exception:
                continue
            for f in filas:
                try:
                    completa = repo.obtener_contenido(f["mensaje_id"])
                    if not completa or not completa.get("contenido"):
                        continue
                    meta, reg = _reconstruir(completa)
                    bundle = bundle_desde_registro(reg)
                    COLA.programar({"mensaje_id": f["mensaje_id"], "formato": completa["formato"],
                                    "sede_id": meta["sede_origen"], "tipo_mensaje": meta["tipo_mensaje"],
                                    "hash_contenido": completa["hash_contenido"], "registro": reg, "bundle": bundle,
                                    "contenido": completa["contenido"], "intentos": int(completa.get("intentos") or 0),
                                    "max_intentos": MAX_REINTENTOS, "t0": time.time()}, 1)
                    n += 1
                except Exception as e:
                    logger.warning(f"No se pudo recuperar {f.get('mensaje_id')}: {e}")
    if n:
        logger.info(f"Recuperados {n} mensajes pendientes tras el arranque del bus")
    return n


def listar_mensajes(limite: int = 50, estado: Optional[str] = None) -> Dict[str, Any]:
    """Mensajes de las 3 sedes para el monitor del admisionista."""
    mensajes, sedes_caidas = [], []
    for repo in todos_los_repositorios():
        try:
            for m in repo.listar_mensajes(limite, estado):
                m["sede_registro"] = repo.sede_id
                m["motor"] = repo.motor
                mensajes.append(m)
        except Exception:
            sedes_caidas.append(repo.sede_id)
    vistos = {m["mensaje_id"] for m in mensajes}
    for m in _MEMORIA_MENSAJES.values():   # estados que no se pudieron persistir (sede caída)
        if not m.get("persistido") and m["mensaje_id"] not in vistos and (not estado or m.get("estado") == estado):
            mensajes.append({k: v for k, v in m.items() if k not in ("contenido",)})
    mensajes.sort(key=lambda m: str(m.get("actualizado_en") or ""), reverse=True)
    return {"mensajes": mensajes[:limite], "sedes_no_disponibles": sedes_caidas,
            "pendientes_en_cola": COLA.pendientes()}


def contar_por_estado() -> Dict[str, int]:
    """Mensajes por estado en las 3 sedes, consultadas en paralelo (una sede caída no frena a las demás)."""
    from concurrent.futures import ThreadPoolExecutor

    def contar(repo):
        try:
            return repo.contar_por_estado()
        except Exception:
            return {}
    total: Dict[str, int] = {}
    repos = todos_los_repositorios()
    with ThreadPoolExecutor(max_workers=len(repos)) as pool:
        for parcial in pool.map(contar, repos):
            for estado, n in parcial.items():
                total[estado] = total.get(estado, 0) + n
    return total
