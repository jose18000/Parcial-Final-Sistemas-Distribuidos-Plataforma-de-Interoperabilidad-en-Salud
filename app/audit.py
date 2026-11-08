"""
app/audit.py
Motor de Auditoría Encadenada por Hash SHA-256 Inmutable.

Cada evento almacena el hash del evento anterior:
hash_propio = SHA-256(hash_anterior + timestamp + usuario + tipo_evento + resultado + detalle)

Incluye el verificador criptográfico que recorre la cadena e identifica el
primer evento alterado (a prueba de adulteración en bases de datos).
"""

import os
import time
import json
import uuid
import hashlib
import datetime
from typing import Dict, Any, List, Optional, Tuple

GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000"

# Almacén en memoria de la cadena de auditoría (respaldo y pruebas)
_CADENA_AUDITORIA: List[Dict[str, Any]] = []


def calcular_hash_evento(
    hash_anterior: str,
    timestamp: str,
    usuario_sistema: str,
    tipo_evento: str,
    resultado: str,
    detalle_str: str
) -> str:
    """Calcula el hash criptográfico SHA-256 determinista de un evento."""
    bloque = f"{hash_anterior}|{timestamp}|{usuario_sistema}|{tipo_evento}|{resultado}|{detalle_str}"
    return hashlib.sha256(bloque.encode("utf-8")).hexdigest()


def registrar_evento_auditoria(
    tipo_evento: str,
    usuario_sistema: str,
    rol: str,
    recurso_afectado: str,
    resultado: str,
    detalle: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Inserta un nuevo evento enlazado a la cadena criptográfica.
    Garantiza inmutabilidad y ordenamiento temporal estricto.
    """
    ts = datetime.datetime.utcnow().isoformat() + "Z"
    detalle_dict = detalle or {}
    detalle_str = json.dumps(detalle_dict, sort_keys=True)

    # Obtener el hash del último bloque de la cadena
    hash_anterior = _CADENA_AUDITORIA[-1]["hash_propio"] if _CADENA_AUDITORIA else GENESIS_HASH

    # Calcular el hash de este nuevo bloque
    hash_propio = calcular_hash_evento(
        hash_anterior=hash_anterior,
        timestamp=ts,
        usuario_sistema=usuario_sistema,
        tipo_evento=tipo_evento,
        resultado=resultado,
        detalle_str=detalle_str
    )

    evento = {
        "evento_id": str(uuid.uuid4()),
        "indice": len(_CADENA_AUDITORIA),
        "tipo_evento": tipo_evento,
        "usuario_sistema": usuario_sistema,
        "rol": rol,
        "recurso_afectado": recurso_afectado,
        "resultado": resultado,
        "timestamp": ts,
        "hash_anterior": hash_anterior,
        "hash_propio": hash_propio,
        "detalle": detalle_dict
    }

    _CADENA_AUDITORIA.append(evento)
    return evento


def verificar_cadena_auditoria(cadena: Optional[List[Dict[str, Any]]] = None) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Verifica la integridad de la cadena de auditoría de extremo a extremo.
    Si detecta una alteración, retorna (False, detalle_del_primer_evento_alterado).
    Si toda la cadena es íntegra, retorna (True, None).
    """
    lista = cadena if cadena is not None else _CADENA_AUDITORIA

    if not lista:
        return True, None

    for idx, ev in enumerate(lista):
        # 1. Verificar hash_anterior
        if idx == 0:
            esperado_anterior = GENESIS_HASH
        else:
            esperado_anterior = lista[idx - 1]["hash_propio"]

        if ev["hash_anterior"] != esperado_anterior:
            return False, {
                "evento_id": ev["evento_id"],
                "indice": idx,
                "motivo": "Ruptura de enlace: hash_anterior no coincide con el hash del bloque previo",
                "hash_anterior_encontrado": ev["hash_anterior"],
                "hash_esperado": esperado_anterior,
                "usuario": ev.get("usuario_sistema"),
                "tipo_evento": ev.get("tipo_evento")
            }

        # 2. Recalcular hash_propio y comparar con el almacenado
        detalle_str = json.dumps(ev.get("detalle", {}), sort_keys=True)
        hash_recalculado = calcular_hash_evento(
            hash_anterior=ev["hash_anterior"],
            timestamp=ev["timestamp"],
            usuario_sistema=ev["usuario_sistema"],
            tipo_evento=ev["tipo_evento"],
            resultado=ev["resultado"],
            detalle_str=detalle_str
        )

        if ev["hash_propio"] != hash_recalculado:
            return False, {
                "evento_id": ev["evento_id"],
                "indice": idx,
                "motivo": "Alteración de contenido: el hash_propio no corresponde con los datos del bloque",
                "hash_propio_almacenado": ev["hash_propio"],
                "hash_recalculado": hash_recalculado,
                "usuario": ev.get("usuario_sistema"),
                "tipo_evento": ev.get("tipo_evento")
            }

    return True, None


def adulterar_evento_para_prueba(indice: int = 0, campo: str = "usuario_sistema", nuevo_valor: str = "hacker_anonimo") -> Dict[str, Any]:
    """
    Modifica intencionalmente un campo en memoria sin recalcular el hash,
    para demostrar que el verificador detecta la alteración en vivo.
    """
    if not _CADENA_AUDITORIA or indice >= len(_CADENA_AUDITORIA):
        raise ValueError("Cadena vacía o índice fuera de rango")
    ev = _CADENA_AUDITORIA[indice]
    ev[campo] = nuevo_valor
    return ev


def obtener_ultimos_eventos(limite: int = 50) -> List[Dict[str, Any]]:
    """Retorna los eventos más recientes de la auditoría."""
    return list(reversed(_CADENA_AUDITORIA[-limite:]))
