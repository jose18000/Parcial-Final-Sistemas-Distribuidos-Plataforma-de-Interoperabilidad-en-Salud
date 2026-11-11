"""
app/auth.py
Autenticación de usuarios: tokens OAuth 2.0 (JWT RS256) emitidos por app/oauth.py.

Roles soportados: paciente, admisionista, medico, auditor.
"""

import os
import hashlib
import datetime
from typing import Optional, Dict, Any
from jose import jwt, JWTError

# Desde la v3 los tokens son RS256 y los emite el servidor OAuth 2.0 (app/oauth.py).
JWT_ALGORITHM = "RS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

# Base de datos de usuarios de prueba (contraseñas con hash SHA-256 + salt simple)
SALT_PRUEBA = "CLINICA_SALT_2026"

def _hash_pass(password: str) -> str:
    return hashlib.sha256((SALT_PRUEBA + password).encode("utf-8")).hexdigest()

USUARIOS_PRUEBA = {
    "paciente_carlos": {
        "username": "paciente_carlos",
        "password_hash": _hash_pass("Paciente123!"),
        "rol": "paciente",
        "nombre_completo": "Carlos Perez",
        "documento_id": "1001",
        "sede_id": 1
    },
    "admision_laura": {
        "username": "admision_laura",
        "password_hash": _hash_pass("Admision123!"),
        "rol": "admisionista",
        "nombre_completo": "Laura Jimenez",
        "documento_id": "ADM-01",
        "sede_id": 2
    },
    "medico_mateo": {
        "username": "medico_mateo",
        "password_hash": _hash_pass("Medico123!"),
        "rol": "medico",
        "nombre_completo": "Dr. Mateo Ruiz",
        "documento_id": "MED-02",
        "sede_id": 2
    },
    "auditor_elena": {
        "username": "auditor_elena",
        "password_hash": _hash_pass("Auditor123!"),
        "rol": "auditor",
        "nombre_completo": "Dra. Elena Gomez",
        "documento_id": "AUD-01",
        "sede_id": None
    },
    # Rol adicional (fuera de la matriz mínima de la guía): opera el Panel de administración.
    "admin_plataforma": {
        "username": "admin_plataforma",
        "password_hash": _hash_pass("Admin123!"),
        "rol": "administrador",
        "nombre_completo": "Administrador de la plataforma",
        "documento_id": "ADMIN-01",
        "sede_id": None
    }
}


def verificar_password(plain_password: str, password_hash: str) -> bool:
    return _hash_pass(plain_password) == password_hash


def autenticar_usuario(username: str, password: str) -> Optional[Dict[str, Any]]:
    """
    Las cuentas viven en la base central (app/usuarios.py, PBKDF2). USUARIOS_PRUEBA solo
    documenta las cuentas iniciales; la semilla real está en app.usuarios.SEMILLA.
    """
    from app import usuarios
    return usuarios.autenticar(username, password)


def crear_token_jwt(datos: Dict[str, Any], expira_minutos: int = JWT_EXPIRE_MINUTES) -> str:
    """
    Token de acceso de un usuario: JWT RS256 emitido por el servidor OAuth 2.0 (app/oauth.py),
    con emisor, audiencia "api", scopes de su rol, jti y expiración.
    """
    from app import oauth
    usr = {**datos, "username": datos.get("username") or datos.get("sub")}
    return oauth.token_de_usuario(usr, client_id="portal_web")["access_token"]


def decodificar_token_jwt(token: str) -> Optional[Dict[str, Any]]:
    """Verifica firma RS256, emisor, audiencia ("api") y vencimiento. None si algo no cuadra."""
    from app import oauth
    try:
        return oauth.verificar(token, audiencia="api")
    except JWTError:
        return None
