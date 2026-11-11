"""
seguridad/tls.py
Cifrado en tránsito entre los servidores de la plataforma.

Con TLS_ACTIVO=true (docker-compose lo activa):
  - API, HSB y HAPI FHIR hablan HTTPS; cada cliente verifica el certificado del otro
    contra la CA propia (/certs/ca.pem), así que nadie puede hacerse pasar por un servicio.
  - Las conexiones a PostgreSQL usan sslmode=verify-full (cifra y comprueba el nombre del
    servidor) y las de MongoDB usan TLS con la misma CA.
Sin TLS_ACTIVO (pruebas en el PC) todo funciona igual, sin cifrado.
"""

import os
import ssl
from typing import Any, Dict, Union

TLS_ACTIVO = os.getenv("TLS_ACTIVO", "false").strip().lower() in ("1", "true", "si", "sí", "yes")
CA_FILE = os.getenv("TLS_CA_FILE", "/certs/ca.pem")


def activo() -> bool:
    return TLS_ACTIVO and os.path.exists(CA_FILE)


def verificacion_http() -> Union[bool, ssl.SSLContext]:
    """Valor para `verify=` de httpx: contexto que confía solo en la CA de la plataforma."""
    if not activo():
        return True
    return ssl.create_default_context(cafile=CA_FILE)


def params_postgres() -> Dict[str, Any]:
    """Parámetros extra de psycopg2: TLS obligatorio y verificación del certificado del servidor."""
    if not activo():
        return {}
    return {"sslmode": os.getenv("PG_SSLMODE", "verify-full"), "sslrootcert": CA_FILE}


def params_mongo() -> Dict[str, Any]:
    """Parámetros extra de pymongo.MongoClient para TLS con la CA de la plataforma."""
    if not activo():
        return {}
    return {"tls": True, "tlsCAFile": CA_FILE}


def esquema() -> str:
    return "https" if activo() else "http"
