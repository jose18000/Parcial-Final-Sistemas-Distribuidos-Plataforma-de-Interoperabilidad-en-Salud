"""
seguridad/
Piezas de seguridad compartidas por la API y el HSB.

  tls.py       Cifrado en tránsito: HTTPS entre servicios y TLS hacia PostgreSQL y MongoDB,
               todo firmado por la autoridad certificadora (CA) propia de la plataforma.
  tokens.py    Validación de tokens OAuth 2.0 (JWT RS256) con la clave pública publicada
               por el servidor de autorización en /oauth/jwks (RFC 7517).
  servidor.py  Arranca uvicorn con HTTPS cuando hay certificado.
"""
