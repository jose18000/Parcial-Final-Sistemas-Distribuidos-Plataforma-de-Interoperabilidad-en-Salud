"""
hsb/autorizacion.py
El HSB como servidor de recursos OAuth 2.0 (RFC 6750).

Cada petición de ingesta u operación debe traer "Authorization: Bearer <token>" emitido por la
API (/oauth/token). El bus verifica, sin compartir secretos con la API:
  - la firma RS256 con la clave pública de /oauth/jwks,
  - el emisor (iss), la audiencia (aud = "hsb") y que no haya vencido,
  - el scope:  hsb.ingesta  para recibir HL7 / CSV / JSON
               hsb.admin    para ver mensajes, reencolar y migrar a FHIR
  - la sede: el sistema de una sede (cliente sistema_sedeN) solo puede enviar mensajes de SU sede.

/health, /metrics y /hsb/catalogo siguen abiertos: no contienen datos de pacientes.
"""

import logging
import os
import unicodedata
from typing import Any, Dict, Optional

from fastapi import HTTPException, Request

from seguridad.tokens import TokenInvalido, ValidadorJWT

logger = logging.getLogger("hsb.autorizacion")

REQUIERE_TOKEN = os.getenv("HSB_REQUIERE_TOKEN", "false").strip().lower() in ("1", "true", "si", "sí", "yes")

_ruta_pem = os.getenv("OAUTH_CLAVE_PUBLICA", "")
VALIDADOR = ValidadorJWT(jwks_url=os.getenv("OAUTH_JWKS_URL", "https://api:8000/oauth/jwks"),
                         clave_publica_pem=open(_ruta_pem).read() if _ruta_pem and os.path.exists(_ruta_pem) else None,
                         audiencia="hsb")


def _rechazo(e: TokenInvalido) -> HTTPException:
    # Las cabeceras HTTP deben ir en ASCII: se quitan tildes de la descripción
    desc = unicodedata.normalize("NFKD", e.motivo).encode("ascii", "ignore").decode().replace('"', "'")
    return HTTPException(status_code=e.status, detail={"error": e.codigo, "error_description": e.motivo},
                         headers={"WWW-Authenticate": f'Bearer realm="hsb", error="{e.codigo}", error_description="{desc}"'})


def requerir(*scopes: str):
    """Dependencia FastAPI: valida el token y devuelve sus claims ({} si la autenticación está apagada)."""

    def _dependencia(request: Request) -> Dict[str, Any]:
        if not REQUIERE_TOKEN:
            return {}
        cabecera = request.headers.get("authorization", "")
        token = cabecera[7:].strip() if cabecera.lower().startswith("bearer ") else ""
        try:
            claims = VALIDADOR.validar(token, scopes)
        except TokenInvalido as e:
            logger.warning("Petición rechazada en %s: %s", request.url.path, e.motivo)
            raise _rechazo(e)
        request.state.cliente = claims.get("client_id") or claims.get("sub")
        return claims

    return _dependencia


def verificar_sede(claims: Dict[str, Any], sede: Optional[int]) -> None:
    """Un sistema de sede (claim sede_id) no puede escribir en otra sede."""
    propia = claims.get("sede_id")
    if propia and sede is not None and int(propia) != int(sede):
        raise _rechazo(TokenInvalido(
            f"El cliente {claims.get('client_id')} pertenece a la sede {propia} y no puede enviar mensajes de la sede {sede}",
            codigo="insufficient_scope", status=403))
