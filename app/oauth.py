"""
app/oauth.py
Servidor de autorización OAuth 2.0 de la plataforma.

Estándares que implementa:
  RFC 6749  OAuth 2.0: endpoint /oauth/token con los flujos
              - password            (usuario + contraseña, a través de un cliente registrado)
              - client_credentials  (servicio a servicio: API -> HSB, sistemas de cada sede -> HSB)
              - refresh_token       (renovar sin volver a pedir la contraseña; con rotación)
  RFC 6750  Uso del token: "Authorization: Bearer <token>"
  RFC 7519  Tokens JWT firmados con RS256 (clave privada solo en la API)
  RFC 7517  Clave pública publicada en /oauth/jwks para que otros servicios verifiquen
  RFC 7009  Revocación de refresh tokens en /oauth/revoke
  RFC 7662  Introspección en /oauth/introspect
  RFC 8414  Metadatos del servidor en /.well-known/oauth-authorization-server

Cada token lleva `scope` (qué puede hacer) y `aud` (para qué servicio sirve): un token de
usuario sirve para la API ("api"); uno de servicio sirve para el bus ("hsb").
"""

import base64
import datetime
import hashlib
import hmac
import os
import secrets
import threading
import uuid
from typing import Any, Dict, List, Optional, Tuple

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt, JWTError

from seguridad.tokens import ISSUER, ALGORITMO

# ── Tiempos de vida ──────────────────────────────────────────────────────
TTL_ACCESO_USUARIO_MIN = int(os.getenv("OAUTH_TTL_ACCESO_MIN", os.getenv("JWT_EXPIRE_MINUTES", "60")))
TTL_ACCESO_SERVICIO_MIN = int(os.getenv("OAUTH_TTL_SERVICIO_MIN", "15"))
TTL_REFRESCO_HORAS = int(os.getenv("OAUTH_TTL_REFRESCO_HORAS", "8"))

# ── Scopes por rol (lo que cada rol puede hacer en la API) ───────────────
SCOPES_POR_ROL: Dict[str, List[str]] = {
    "paciente": ["historia.propia"],
    "admisionista": ["pacientes.buscar", "admision.registrar"],
    "medico": ["historia.leer", "historia.escribir", "plataforma.estado", "auditoria.verificar"],
    "auditor": ["historia.leer", "plataforma.estado", "auditoria.verificar", "auditoria.leer"],
    "administrador": ["panel.admin", "usuarios.gestionar", "historia.leer", "plataforma.estado",
                      "auditoria.verificar", "auditoria.leer"],
}
SCOPES_SERVICIO = ["hsb.ingesta", "hsb.admin"]

# ── Clientes registrados (secretos en .env; los valores por defecto son de desarrollo) ──
CLIENTES: Dict[str, Dict[str, Any]] = {
    "portal_web": {"nombre": "Portal web de la plataforma (vistas por rol)",
                   "secreto": os.getenv("OAUTH_SECRETO_PORTAL", "portal_web_secreto_2026"),
                   "grants": ["password", "refresh_token"], "scopes": None, "aud": ["api"]},
    "api_gateway": {"nombre": "API Gateway (escribe en el bus)",
                    "secreto": os.getenv("OAUTH_SECRETO_API", "api_gateway_secreto_2026"),
                    "grants": ["client_credentials"], "scopes": ["hsb.ingesta", "hsb.admin"], "aud": ["hsb"]},
    "sistema_sede1": {"nombre": "Sistema legado IPS Sincelejo Central", "sede_id": 1,
                      "secreto": os.getenv("OAUTH_SECRETO_SEDE1", "sede1_secreto_2026"),
                      "grants": ["client_credentials"], "scopes": ["hsb.ingesta"], "aud": ["hsb"]},
    "sistema_sede2": {"nombre": "Sistema legado IPS Cartagena Bocagrande", "sede_id": 2,
                      "secreto": os.getenv("OAUTH_SECRETO_SEDE2", "sede2_secreto_2026"),
                      "grants": ["client_credentials"], "scopes": ["hsb.ingesta"], "aud": ["hsb"]},
    "sistema_sede3": {"nombre": "Sistema legado IPS Corozal La Perla", "sede_id": 3,
                      "secreto": os.getenv("OAUTH_SECRETO_SEDE3", "sede3_secreto_2026"),
                      "grants": ["client_credentials"], "scopes": ["hsb.ingesta"], "aud": ["hsb"]},
    "herramientas_qa": {"nombre": "Pruebas: Postman, scripts de carga y verificación",
                        "secreto": os.getenv("OAUTH_SECRETO_QA", "qa_secreto_2026"),
                        "grants": ["password", "client_credentials", "refresh_token"],
                        "scopes": ["hsb.ingesta", "hsb.admin"], "aud": ["hsb"]},
}


class ErrorOAuth(Exception):
    """Error con el formato de RFC 6749 §5.2."""

    def __init__(self, error: str, descripcion: str, status: int = 400):
        super().__init__(descripcion)
        self.error, self.descripcion, self.status = error, descripcion, status

    def cuerpo(self) -> Dict[str, str]:
        return {"error": self.error, "error_description": self.descripcion}


# ── Claves de firma RS256 ────────────────────────────────────────────────
_LOCK = threading.Lock()
_CLAVES: Dict[str, Any] = {}


def _b64url(n: int) -> str:
    datos = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode()


def _claves() -> Dict[str, Any]:
    """Carga la clave privada de /certs (generada por scripts/generar_certificados.sh) o crea una en memoria."""
    with _LOCK:
        if _CLAVES:
            return _CLAVES
        ruta = os.getenv("OAUTH_CLAVE_PRIVADA", "/certs/oauth_firma.key")
        if os.path.exists(ruta):
            with open(ruta, "rb") as f:
                privada = serialization.load_pem_private_key(f.read(), password=None)
            origen = ruta
        else:
            privada = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            origen = "memoria (sin archivo de clave: los tokens no sobreviven a un reinicio)"
        publica = privada.public_key()
        num = publica.public_numbers()
        kid = hashlib.sha256(num.n.to_bytes((num.n.bit_length() + 7) // 8, "big")).hexdigest()[:16]
        _CLAVES.update({
            "privada_pem": privada.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                 serialization.NoEncryption()).decode(),
            "publica_pem": publica.public_bytes(serialization.Encoding.PEM,
                                                serialization.PublicFormat.SubjectPublicKeyInfo).decode(),
            "jwk": {"kty": "RSA", "use": "sig", "alg": ALGORITMO, "kid": kid, "n": _b64url(num.n), "e": _b64url(num.e)},
            "kid": kid, "origen": origen})
        return _CLAVES


def jwks() -> Dict[str, Any]:
    return {"keys": [_claves()["jwk"]]}


def _ahora() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def firmar(claims: Dict[str, Any], minutos: int) -> Tuple[str, Dict[str, Any]]:
    ahora = _ahora()
    cuerpo = {**claims, "iss": ISSUER, "iat": int(ahora.timestamp()), "nbf": int(ahora.timestamp()),
              "exp": int((ahora + datetime.timedelta(minutes=minutos)).timestamp()), "jti": uuid.uuid4().hex}
    token = jwt.encode(cuerpo, _claves()["privada_pem"], algorithm=ALGORITMO, headers={"kid": _claves()["kid"]})
    return token, cuerpo


def verificar(token: str, audiencia: str = "api") -> Dict[str, Any]:
    """Verifica un token emitido por este servidor (firma, emisor, audiencia y expiración)."""
    return jwt.decode(token, _claves()["publica_pem"], algorithms=[ALGORITMO], audience=audiencia, issuer=ISSUER)


# ── Clientes ─────────────────────────────────────────────────────────────

def autenticar_cliente(client_id: Optional[str], client_secret: Optional[str]) -> Dict[str, Any]:
    cliente = CLIENTES.get(client_id or "")
    if not cliente or not client_secret or not hmac.compare_digest(cliente["secreto"].encode(), client_secret.encode()):
        raise ErrorOAuth("invalid_client", "Cliente desconocido o secreto incorrecto", status=401)
    return {"client_id": client_id, **cliente}


def credenciales_de_cabecera(autorizacion: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """client_secret_basic (RFC 6749 §2.3.1): Authorization: Basic base64(client_id:client_secret)."""
    if not autorizacion or not autorizacion.lower().startswith("basic "):
        return None, None
    try:
        from urllib.parse import unquote
        cid, _, sec = base64.b64decode(autorizacion[6:].strip()).decode("utf-8").partition(":")
        return unquote(cid), unquote(sec)
    except Exception:
        raise ErrorOAuth("invalid_client", "Cabecera Basic mal formada", status=401)


def _scopes_pedidos(scope: Optional[str], permitidos: List[str]) -> List[str]:
    if not scope:
        return list(permitidos)
    pedidos = scope.split()
    fuera = [s for s in pedidos if s not in permitidos]
    if fuera:
        raise ErrorOAuth("invalid_scope", f"Scope no permitido para este cliente o rol: {' '.join(fuera)}")
    return pedidos


# ── Refresh tokens (opacos; en la base central se guarda solo su hash) ───
_REFRESCO_MEM: Dict[str, Dict[str, Any]] = {}


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _guardar_refresco(username: str, client_id: str, scope: str) -> str:
    from app import usuarios
    token = secrets.token_urlsafe(48)
    fila = {"hash_token": _hash(token), "username": username, "client_id": client_id, "scope": scope,
            "expira_en": (_ahora() + datetime.timedelta(hours=TTL_REFRESCO_HORAS)).replace(tzinfo=None)}
    if usuarios.USAR_BD:
        conn = usuarios._conectar()
        try:
            with conn, conn.cursor() as cur:
                cur.execute("""INSERT INTO token_refresco (hash_token, username, client_id, scope, expira_en)
                               VALUES (%(hash_token)s, %(username)s, %(client_id)s, %(scope)s, %(expira_en)s)""", fila)
        finally:
            conn.close()
    else:
        _REFRESCO_MEM[fila["hash_token"]] = {**fila, "revocado": False}
    return token


def _buscar_refresco(token: str) -> Optional[Dict[str, Any]]:
    from app import usuarios
    h = _hash(token)
    if not usuarios.USAR_BD:
        return _REFRESCO_MEM.get(h)
    from psycopg2.extras import RealDictCursor
    conn = usuarios._conectar()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM token_refresco WHERE hash_token = %s", (h,))
            fila = cur.fetchone()
            return dict(fila) if fila else None
    finally:
        conn.close()


def _revocar_refresco(token: str) -> bool:
    from app import usuarios
    h = _hash(token)
    if not usuarios.USAR_BD:
        if h in _REFRESCO_MEM:
            _REFRESCO_MEM[h]["revocado"] = True
            return True
        return False
    conn = usuarios._conectar()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("UPDATE token_refresco SET revocado = TRUE, revocado_en = NOW() WHERE hash_token = %s AND NOT revocado",
                        (h,))
            return cur.rowcount > 0
    finally:
        conn.close()


def _vigente(fila: Optional[Dict[str, Any]]) -> bool:
    return bool(fila) and not fila.get("revocado") and fila["expira_en"] > _ahora().replace(tzinfo=None)


# ── Emisión ──────────────────────────────────────────────────────────────

CLAIMS_USUARIO = ("username", "rol", "nombre_completo", "documento_id", "sede_id", "debe_cambiar_clave")


def token_de_usuario(usr: Dict[str, Any], client_id: str = "portal_web", scope: Optional[str] = None,
                     con_refresco: bool = False) -> Dict[str, Any]:
    """Respuesta de /oauth/token para un usuario ya autenticado (RFC 6749 §5.1)."""
    permitidos = SCOPES_POR_ROL.get(usr.get("rol"), [])
    scopes = _scopes_pedidos(scope, permitidos)
    claims = {k: usr.get(k) for k in CLAIMS_USUARIO}
    claims.update({"sub": usr["username"], "aud": ["api"], "client_id": client_id, "scope": " ".join(scopes),
                   "token_use": "usuario"})
    token, cuerpo = firmar(claims, TTL_ACCESO_USUARIO_MIN)
    resp = {"access_token": token, "token_type": "Bearer", "expires_in": TTL_ACCESO_USUARIO_MIN * 60,
            "scope": cuerpo["scope"]}
    if con_refresco:
        resp["refresh_token"] = _guardar_refresco(usr["username"], client_id, cuerpo["scope"])
    return resp


def token_de_servicio(cliente: Dict[str, Any], scope: Optional[str] = None) -> Dict[str, Any]:
    scopes = _scopes_pedidos(scope, cliente.get("scopes") or [])
    claims = {"sub": cliente["client_id"], "aud": cliente.get("aud", ["hsb"]), "client_id": cliente["client_id"],
              "scope": " ".join(scopes), "token_use": "servicio"}
    if cliente.get("sede_id"):
        claims["sede_id"] = cliente["sede_id"]
    token, cuerpo = firmar(claims, TTL_ACCESO_SERVICIO_MIN)
    return {"access_token": token, "token_type": "Bearer", "expires_in": TTL_ACCESO_SERVICIO_MIN * 60,
            "scope": cuerpo["scope"]}


def emitir(form: Dict[str, str], autorizacion: Optional[str]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Atiende POST /oauth/token. Devuelve (respuesta, datos_para_auditoría).
    Lanza ErrorOAuth con el código de RFC 6749 si algo falla.
    """
    from app import usuarios
    cid, sec = credenciales_de_cabecera(autorizacion)
    cliente = autenticar_cliente(cid or form.get("client_id"), sec or form.get("client_secret"))
    grant = form.get("grant_type")
    if not grant:
        raise ErrorOAuth("invalid_request", "Falta grant_type")
    if grant not in ("password", "client_credentials", "refresh_token"):
        raise ErrorOAuth("unsupported_grant_type", f"grant_type no soportado: {grant}")
    if grant not in cliente["grants"]:
        raise ErrorOAuth("unauthorized_client", f"El cliente {cliente['client_id']} no puede usar {grant}")

    if grant == "client_credentials":
        return token_de_servicio(cliente, form.get("scope")), {"usuario": cliente["client_id"], "rol": "servicio"}

    if grant == "password":
        username, password = form.get("username"), form.get("password")
        if not username or not password:
            raise ErrorOAuth("invalid_request", "Faltan username y password")
        usr = usuarios.autenticar(username, password)
        if not usr:
            raise ErrorOAuth("invalid_grant", "Usuario o contraseña incorrectos, o cuenta desactivada")
        return (token_de_usuario(usr, cliente["client_id"], form.get("scope"), con_refresco=True),
                {"usuario": usr["username"], "rol": usr["rol"]})

    # refresh_token: se valida, se revoca (rotación) y se emite uno nuevo
    viejo = form.get("refresh_token") or ""
    fila = _buscar_refresco(viejo)
    if not _vigente(fila) or fila["client_id"] != cliente["client_id"]:
        raise ErrorOAuth("invalid_grant", "Refresh token inválido, vencido o revocado")
    usr = usuarios.obtener_publico(fila["username"]) if hasattr(usuarios, "obtener_publico") else None
    if not usr or not usr.get("activo", True):
        raise ErrorOAuth("invalid_grant", "La cuenta ya no está activa")
    _revocar_refresco(viejo)
    scope = form.get("scope") or fila["scope"]
    if any(s not in fila["scope"].split() for s in scope.split()):
        raise ErrorOAuth("invalid_scope", "No se puede ampliar el scope al renovar")
    return (token_de_usuario(usr, cliente["client_id"], scope, con_refresco=True),
            {"usuario": usr["username"], "rol": usr["rol"]})


def revocar(form: Dict[str, str], autorizacion: Optional[str]) -> None:
    """RFC 7009: siempre responde 200; solo los refresh tokens del mismo cliente se pueden revocar."""
    cid, sec = credenciales_de_cabecera(autorizacion)
    cliente = autenticar_cliente(cid or form.get("client_id"), sec or form.get("client_secret"))
    token = form.get("token") or ""
    fila = _buscar_refresco(token)
    if fila and fila["client_id"] == cliente["client_id"]:
        _revocar_refresco(token)


def introspeccionar(form: Dict[str, str], autorizacion: Optional[str]) -> Dict[str, Any]:
    """RFC 7662: dice si un token está activo y qué contiene."""
    cid, sec = credenciales_de_cabecera(autorizacion)
    autenticar_cliente(cid or form.get("client_id"), sec or form.get("client_secret"))
    token = form.get("token") or ""
    for aud in ("api", "hsb"):
        try:
            claims = verificar(token, aud)
            return {"active": True, "token_type": "Bearer", **claims}
        except JWTError:
            continue
    fila = _buscar_refresco(token)
    if _vigente(fila):
        return {"active": True, "token_type": "refresh_token", "username": fila["username"],
                "client_id": fila["client_id"], "scope": fila["scope"],
                "exp": int(fila["expira_en"].replace(tzinfo=datetime.timezone.utc).timestamp())}
    return {"active": False}


def metadatos(base: str) -> Dict[str, Any]:
    """RFC 8414."""
    base = base.rstrip("/")
    return {
        "issuer": ISSUER,
        "token_endpoint": f"{base}/oauth/token",
        "jwks_uri": f"{base}/oauth/jwks",
        "revocation_endpoint": f"{base}/oauth/revoke",
        "introspection_endpoint": f"{base}/oauth/introspect",
        "grant_types_supported": ["password", "client_credentials", "refresh_token"],
        "response_types_supported": [],
        "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
        "token_endpoint_auth_signing_alg_values_supported": [ALGORITMO],
        "scopes_supported": sorted({s for v in SCOPES_POR_ROL.values() for s in v} | set(SCOPES_SERVICIO)),
        "service_documentation": f"{base}/docs",
    }


# ── Token propio de la API para hablar con el HSB (client_credentials en proceso) ──
_TOKEN_API: Dict[str, Any] = {}


def token_api_para_hsb() -> str:
    """La API pide su propio token de servicio y lo reutiliza hasta un minuto antes de que venza."""
    with _LOCK:
        if _TOKEN_API and _TOKEN_API["vence"] - 60 > _ahora().timestamp():
            return _TOKEN_API["token"]
    cliente = {"client_id": "api_gateway", **CLIENTES["api_gateway"]}
    resp = token_de_servicio(cliente)
    with _LOCK:
        _TOKEN_API.update({"token": resp["access_token"], "vence": _ahora().timestamp() + resp["expires_in"]})
    return resp["access_token"]
