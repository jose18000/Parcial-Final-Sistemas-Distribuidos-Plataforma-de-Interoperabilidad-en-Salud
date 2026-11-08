"""
app/auth.py
Módulo de Autenticación JWT y Gestión de Identidades por Rol.

Roles soportados: paciente, admisionista, medico, auditor.
"""

import os
import hashlib
import datetime
from typing import Optional, Dict, Any
from jose import jwt, JWTError

JWT_SECRET = os.getenv("JWT_SECRET", "CLINICA_DISTRIBUIDA_SECRET_TOKEN_KEY_2026_HS256_UNSECURED_DEV_ONLY")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
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
    }
}


def verificar_password(plain_password: str, password_hash: str) -> bool:
    return _hash_pass(plain_password) == password_hash


def autenticar_usuario(username: str, password: str) -> Optional[Dict[str, Any]]:
    usr = USUARIOS_PRUEBA.get(username)
    if not usr:
        return None
    if not verificar_password(password, usr["password_hash"]):
        return None
    return usr


def crear_token_jwt(datos: Dict[str, Any], expira_minutos: int = JWT_EXPIRE_MINUTES) -> str:
    payload = datos.copy()
    exp = datetime.datetime.utcnow() + datetime.timedelta(minutes=expira_minutos)
    payload.update({"exp": exp, "iat": datetime.datetime.utcnow()})
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token


def decodificar_token_jwt(token: str) -> Optional[Dict[str, Any]]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        return None
