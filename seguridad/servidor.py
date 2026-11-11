"""
seguridad/servidor.py
Arranca un servicio FastAPI con uvicorn, en HTTPS si hay certificado.

    python -m seguridad.servidor app.main:app 8000
    python -m seguridad.servidor hsb.main:app 8001

TLS_CERT_FILE y TLS_KEY_FILE apuntan al certificado del servicio (firmado por la CA propia).
"""

import os
import sys

import uvicorn

from seguridad import tls


def main() -> None:
    aplicacion, puerto = sys.argv[1], int(sys.argv[2])
    cert, clave = os.getenv("TLS_CERT_FILE", ""), os.getenv("TLS_KEY_FILE", "")
    extra = {}
    if tls.TLS_ACTIVO and os.path.exists(cert) and os.path.exists(clave):
        extra = {"ssl_certfile": cert, "ssl_keyfile": clave}
        print(f"[seguridad] {aplicacion} en HTTPS :{puerto} (certificado {os.path.basename(cert)})", flush=True)
    elif tls.TLS_ACTIVO:
        print(f"[seguridad] AVISO: TLS_ACTIVO pero falta {cert or 'TLS_CERT_FILE'}; se sirve en HTTP", flush=True)
    uvicorn.run(aplicacion, host="0.0.0.0", port=puerto, proxy_headers=True, **extra)


if __name__ == "__main__":
    main()
