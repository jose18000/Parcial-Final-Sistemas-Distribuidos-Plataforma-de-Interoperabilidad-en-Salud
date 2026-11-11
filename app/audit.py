"""
app/audit.py
Auditoría encadenada por hash SHA-256, persistida en la base central (pg_central).

    hash_propio = SHA-256(hash_anterior | indice | timestamp | usuario | rol | tipo | recurso | resultado | detalle)

- Cada evento guarda el hash del anterior: alterar cualquier fila rompe su propio hash
  y el enlace del siguiente. El verificador recorre la cadena y señala el PRIMER evento alterado.
- Prueba obligatoria del profe: cambiar una fila a mano
      docker exec -it pg_central psql -U clinica_user -d clinica_central \
        -c "UPDATE evento_auditoria SET usuario_sistema='intruso' WHERE indice = 3"
  y el verificador la detecta.
- Las inserciones toman un candado (pg_advisory_xact_lock) para que dos peticiones
  simultáneas no enlacen al mismo hash anterior (la cadena nunca se bifurca).
- Si la base central no responde, los eventos esperan en memoria y se encadenan en
  orden en cuanto vuelve; no se pierde ninguno.
- Sin base central (pruebas unitarias) la cadena vive en `_CADENA_AUDITORIA`.
"""

import os
import json
import uuid
import hashlib
import logging
import datetime
import threading
from typing import Any, Dict, List, Optional, Tuple

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG_AVAILABLE = True
except ImportError:
    PSYCOPG_AVAILABLE = False

logger = logging.getLogger("auditoria")

GENESIS_HASH = "0" * 64
USAR_BD = os.getenv("AUDIT_DB_HOST") is not None and PSYCOPG_AVAILABLE
CFG_CENTRAL = {
    "host": os.getenv("AUDIT_DB_HOST", "localhost"),
    "port": int(os.getenv("AUDIT_DB_PORT", "5432")),
    "dbname": os.getenv("AUDIT_DB_NAME", "clinica_central"),
    "user": os.getenv("AUDIT_DB_USER", os.getenv("POSTGRES_USER", "clinica_user")),
    "password": os.getenv("AUDIT_DB_PASSWORD", os.getenv("POSTGRES_PASSWORD", "clinica_pass_2026")),
}

_CADENA_AUDITORIA: List[Dict[str, Any]] = []   # cadena en memoria (modo sin base de datos)
_PENDIENTES: List[Dict[str, Any]] = []         # eventos a la espera de la base central
_LOCK = threading.Lock()


def calcular_hash_evento(hash_anterior: str, indice: int, timestamp: str, usuario_sistema: str, rol: str,
                         tipo_evento: str, recurso_afectado: str, resultado: str, detalle_str: str) -> str:
    bloque = "|".join([hash_anterior, str(indice), timestamp, usuario_sistema, rol, tipo_evento,
                       recurso_afectado or "", resultado, detalle_str])
    return hashlib.sha256(bloque.encode("utf-8")).hexdigest()


def _hash_de(ev: Dict[str, Any]) -> str:
    return calcular_hash_evento(ev["hash_anterior"], ev["indice"], ev["timestamp"], ev["usuario_sistema"],
                                ev["rol"], ev["tipo_evento"], ev.get("recurso_afectado") or "", ev["resultado"],
                                ev["detalle_str"])


def _conectar():
    from seguridad import tls
    return psycopg2.connect(connect_timeout=3, **CFG_CENTRAL, **tls.params_postgres())


def _insertar_en_bd(cur, ev: Dict[str, Any]) -> Dict[str, Any]:
    cur.execute("SELECT pg_advisory_xact_lock(866)")
    cur.execute("SELECT indice, hash_propio FROM evento_auditoria ORDER BY indice DESC LIMIT 1")
    ultimo = cur.fetchone()
    ev["indice"] = (ultimo["indice"] + 1) if ultimo else 0
    ev["hash_anterior"] = ultimo["hash_propio"] if ultimo else GENESIS_HASH
    ev["hash_propio"] = _hash_de(ev)
    cur.execute("""INSERT INTO evento_auditoria (evento_id, indice, tipo_evento, usuario_sistema, rol,
                       recurso_afectado, resultado, timestamp, detalle, hash_anterior, hash_propio)
                   VALUES (%(evento_id)s, %(indice)s, %(tipo_evento)s, %(usuario_sistema)s, %(rol)s,
                       %(recurso_afectado)s, %(resultado)s, %(timestamp)s, %(detalle_str)s,
                       %(hash_anterior)s, %(hash_propio)s)""", ev)
    return ev


def _publico(ev: Dict[str, Any]) -> Dict[str, Any]:
    salida = {k: v for k, v in ev.items() if k != "detalle_str"}
    try:
        salida["detalle"] = json.loads(ev.get("detalle_str") or "{}")
    except ValueError:
        salida["detalle"] = {"texto": ev.get("detalle_str")}
    return salida


def registrar_evento_auditoria(tipo_evento: str, usuario_sistema: str, rol: str, recurso_afectado: str,
                               resultado: str, detalle: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Agrega un evento a la cadena. Devuelve el evento con su hash (el 'sello')."""
    ev = {"evento_id": str(uuid.uuid4()), "tipo_evento": tipo_evento, "usuario_sistema": usuario_sistema,
          "rol": rol, "recurso_afectado": recurso_afectado or "", "resultado": resultado,
          "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="microseconds"),
          "detalle_str": json.dumps(detalle or {}, sort_keys=True, ensure_ascii=False, default=str)}

    if not USAR_BD:
        with _LOCK:
            ev["indice"] = len(_CADENA_AUDITORIA)
            ev["hash_anterior"] = _CADENA_AUDITORIA[-1]["hash_propio"] if _CADENA_AUDITORIA else GENESIS_HASH
            ev["hash_propio"] = _hash_de(ev)
            publico = _publico(ev)
            publico["detalle_str"] = ev["detalle_str"]
            _CADENA_AUDITORIA.append(publico)
        return publico

    with _LOCK:
        _PENDIENTES.append(ev)
        try:
            conn = _conectar()
            try:
                with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                    while _PENDIENTES:
                        _insertar_en_bd(cur, _PENDIENTES[0])
                        _PENDIENTES.pop(0)
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"Base central de auditoría no disponible; {len(_PENDIENTES)} evento(s) en espera: {e}")
            ev.setdefault("hash_propio", None)
            ev["pendiente"] = True
    return _publico(ev)


def _leer_cadena_bd() -> List[Dict[str, Any]]:
    conn = _conectar()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""SELECT evento_id::text, indice, tipo_evento, usuario_sistema, rol, recurso_afectado,
                                  resultado, timestamp, detalle AS detalle_str, hash_anterior, hash_propio
                           FROM evento_auditoria ORDER BY indice""")
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def obtener_cadena() -> List[Dict[str, Any]]:
    if not USAR_BD:
        return _CADENA_AUDITORIA
    return _leer_cadena_bd()


def verificar_cadena_auditoria(cadena: Optional[List[Dict[str, Any]]] = None) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Recorre la cadena de principio a fin. Devuelve (True, None) si está íntegra o
    (False, detalle_del_primer_evento_alterado).
    """
    lista = cadena if cadena is not None else obtener_cadena()
    anterior = GENESIS_HASH
    for pos, ev in enumerate(lista):
        datos = dict(ev)
        datos.setdefault("detalle_str", json.dumps(ev.get("detalle", {}), sort_keys=True, ensure_ascii=False,
                                                     default=str))
        base = {"evento_id": ev.get("evento_id"), "indice": ev.get("indice", pos),
                "usuario": ev.get("usuario_sistema"), "tipo_evento": ev.get("tipo_evento"),
                "timestamp": ev.get("timestamp")}
        if ev.get("indice", pos) != pos:
            return False, {**base, "motivo": f"Evento faltante o reordenado: se esperaba el índice {pos}"}
        if ev["hash_anterior"] != anterior:
            return False, {**base, "motivo": "Ruptura de enlace: hash_anterior no coincide con el hash del evento previo",
                           "hash_anterior_encontrado": ev["hash_anterior"], "hash_esperado": anterior}
        recalculado = _hash_de({**datos, "indice": ev.get("indice", pos)})
        if ev["hash_propio"] != recalculado:
            return False, {**base, "motivo": "Alteración de contenido: el hash_propio no corresponde con los datos del evento",
                           "hash_propio_almacenado": ev["hash_propio"], "hash_recalculado": recalculado}
        anterior = ev["hash_propio"]
    return True, None


def estado_auditoria() -> Dict[str, Any]:
    """Resumen para el tablero: integridad, total de eventos y eventos en espera."""
    try:
        cadena = obtener_cadena()
        integra, fallo = verificar_cadena_auditoria(cadena)
        return {"disponible": True, "cadena_integra": integra, "total_eventos_registrados": len(cadena),
                "eventos_en_espera": len(_PENDIENTES), "detalle_alteracion": fallo,
                "ultimo_hash": cadena[-1]["hash_propio"] if cadena else GENESIS_HASH,
                "estado_verificador": "ÍNTEGRA (sin alteraciones)" if integra else "¡ALERTA! ALTERACIÓN DETECTADA"}
    except Exception as e:
        return {"disponible": False, "cadena_integra": None, "total_eventos_registrados": 0,
                "eventos_en_espera": len(_PENDIENTES), "detalle_alteracion": None,
                "estado_verificador": f"Base central de auditoría no disponible ({e.__class__.__name__})"}


def adulterar_evento_para_prueba(indice: int = 1, campo: str = "usuario_sistema",
                                 nuevo_valor: str = "intruso_adulterado") -> Dict[str, Any]:
    """
    Simula a un atacante con acceso directo a la base: cambia un campo SIN recalcular el hash.
    (Equivale al UPDATE manual de la prueba obligatoria.)
    """
    permitidos = {"usuario_sistema", "rol", "tipo_evento", "recurso_afectado", "resultado"}
    if campo not in permitidos:
        raise ValueError(f"Campo no permitido para la prueba: {campo}")
    if not USAR_BD:
        if indice >= len(_CADENA_AUDITORIA):
            raise ValueError("Índice fuera de rango")
        _CADENA_AUDITORIA[indice][campo] = nuevo_valor
        return _CADENA_AUDITORIA[indice]
    conn = _conectar()
    try:
        with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(f"UPDATE evento_auditoria SET {campo} = %s WHERE indice = %s RETURNING indice, {campo}",
                        (nuevo_valor, indice))
            fila = cur.fetchone()
            if not fila:
                raise ValueError("Índice fuera de rango")
            return dict(fila)
    finally:
        conn.close()


def obtener_ultimos_eventos(limite: int = 50, documento: Optional[str] = None) -> List[Dict[str, Any]]:
    """Eventos más recientes primero. Con `documento`, solo los que tocan la historia de ese paciente."""
    try:
        if not USAR_BD:
            eventos = [_publico(e) if "detalle_str" in e else e for e in _CADENA_AUDITORIA]
        else:
            conn = _conectar()
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    if documento:
                        cur.execute("""SELECT indice, tipo_evento, usuario_sistema, rol, recurso_afectado, resultado,
                                              timestamp, detalle AS detalle_str, hash_propio
                                       FROM evento_auditoria
                                       WHERE recurso_afectado LIKE %s OR detalle LIKE %s
                                       ORDER BY indice DESC LIMIT %s""",
                                    (f"%/{documento}%", f'%"documento_id": "{documento}"%', limite))
                    else:
                        cur.execute("""SELECT indice, tipo_evento, usuario_sistema, rol, recurso_afectado, resultado,
                                              timestamp, detalle AS detalle_str, hash_propio
                                       FROM evento_auditoria ORDER BY indice DESC LIMIT %s""", (limite,))
                    return [_publico(dict(r)) for r in cur.fetchall()]
            finally:
                conn.close()
    except Exception as e:
        logger.warning(f"No se pudieron leer eventos de auditoría: {e}")
        return []
    if documento:
        eventos = [e for e in eventos if f"/{documento}" in str(e.get("recurso_afectado", ""))
                   or e.get("detalle", {}).get("documento_id") == documento]
    return list(reversed(eventos[-limite:]))
