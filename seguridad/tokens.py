"""
seguridad/tokens.py
Validación de tokens de acceso OAuth 2.0 (RFC 6749 / RFC 6750) emitidos por la API.

Los tokens son JWT firmados con RS256: la API firma con su clave PRIVADA y cualquier servicio
(el HSB, por ejemplo) los verifica con la clave PÚBLICA que la API publica en /oauth/jwks.
Así el bus no necesita compartir ningún secreto con la API para confiar en un token.
"""

import logging
import os
import threading
import time
from typing import Any, Dict, Iterable, List, Optional

import httpx
from jose import jwt, JWTError

from seguridad import tls

logger = logging.getLogger("seguridad.tokens")

ISSUER = os.getenv("OAUTH_ISSUER", "https://api_gateway:8000")
ALGORITMO = "RS256"


class TokenInvalido(Exception):
    """El token no se pudo validar; `codigo` sigue RFC 6750 (invalid_token / insufficient_scope)."""

    def __init__(self, motivo: str, codigo: str = "invalid_token", status: int = 401):
        super().__init__(motivo)
        self.motivo, self.codigo, self.status = motivo, codigo, status


def scopes_de(claims: Dict[str, Any]) -> List[str]:
    return [s for s in str(claims.get("scope", "")).split() if s]


class ValidadorJWT:
    """Verifica firma RS256, emisor, audiencia, expiración y scopes de un token."""

    def __init__(self, jwks_url: Optional[str] = None, clave_publica_pem: Optional[str] = None,
                 audiencia: str = "hsb", cache_s: int = 300):
        self.jwks_url = jwks_url
        self.clave_publica_pem = clave_publica_pem
        self.audiencia = audiencia
        self.cache_s = cache_s
        self._jwks: Optional[Dict[str, Any]] = None
        self._jwks_en = 0.0
        self._lock = threading.Lock()

    def _claves(self, forzar: bool = False) -> Any:
        """JWKS del emisor (con caché). Si el emisor no responde: caché, y si no hay, la copia local del PEM."""
        if not self.jwks_url:
            return self.clave_publica_pem
        with self._lock:
            if forzar or self._jwks is None or time.time() - self._jwks_en > self.cache_s:
                try:
                    r = httpx.get(self.jwks_url, timeout=4.0, verify=tls.verificacion_http())
                    r.raise_for_status()
                    self._jwks, self._jwks_en = r.json(), time.time()
                except Exception as e:  # el servidor de autorización no responde
                    if self._jwks is not None:
                        logger.warning("JWKS no disponible; se usa la copia en caché: %s", e)
                    elif self.clave_publica_pem:
                        logger.warning("JWKS no disponible; se usa la clave pública local: %s", e)
                        return self.clave_publica_pem
                    else:
                        raise TokenInvalido(f"No se pudo obtener la clave pública del emisor ({e.__class__.__name__})",
                                            codigo="temporarily_unavailable", status=503)
            return self._jwks

    def validar(self, token: str, scopes_requeridos: Iterable[str] = ()) -> Dict[str, Any]:
        if not token:
            raise TokenInvalido("Falta el token de acceso (Authorization: Bearer ...)")
        try:
            claims = jwt.decode(token, self._claves(), algorithms=[ALGORITMO], audience=self.audiencia,
                                issuer=ISSUER)
        except JWTError as e:
            # Puede que el emisor haya rotado la clave: se refresca una vez el JWKS y se reintenta.
            if self.jwks_url and "signature" in str(e).lower():
                try:
                    claims = jwt.decode(token, self._claves(forzar=True), algorithms=[ALGORITMO],
                                        audience=self.audiencia, issuer=ISSUER)
                except JWTError as e2:
                    raise TokenInvalido(f"Token inválido: {e2}")
            else:
                raise TokenInvalido(f"Token inválido: {e}")
        faltan = [s for s in scopes_requeridos if s not in scopes_de(claims)]
        if faltan:
            raise TokenInvalido(f"El token no tiene el scope requerido: {' '.join(faltan)}",
                                codigo="insufficient_scope", status=403)
        return claims
