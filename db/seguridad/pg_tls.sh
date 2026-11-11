#!/bin/sh
# db/seguridad/pg_tls.sh — entrypoint de los PostgreSQL de la plataforma.
# Copia el certificado del servidor con el dueño y permisos que exige PostgreSQL y arranca con:
#   TLS 1.2+ obligatorio para conexiones de red, SCRAM-SHA-256 y registro de cada conexión.
# Si no hay certificados (certs/ sin generar) arranca como antes, sin TLS.
set -e
N="${TLS_NOMBRE:?Falta TLS_NOMBRE}"
if [ -f "/certs/$N.crt" ] && [ -f "/certs/$N.key" ]; then
  mkdir -p /etc/postgresql/tls
  install -o postgres -g postgres -m 600 "/certs/$N.key" /etc/postgresql/tls/server.key
  install -o postgres -g postgres -m 644 "/certs/$N.crt" /etc/postgresql/tls/server.crt
  install -o postgres -g postgres -m 644 /certs/ca.pem /etc/postgresql/tls/ca.pem
  install -o postgres -g postgres -m 644 /seguridad/pg_hba.conf /etc/postgresql/pg_hba.conf
  exec docker-entrypoint.sh "$@" \
    -c ssl=on -c ssl_min_protocol_version=TLSv1.2 \
    -c ssl_cert_file=/etc/postgresql/tls/server.crt -c ssl_key_file=/etc/postgresql/tls/server.key \
    -c ssl_ca_file=/etc/postgresql/tls/ca.pem -c hba_file=/etc/postgresql/pg_hba.conf \
    -c password_encryption=scram-sha-256 -c log_connections=on
fi
echo "[seguridad] AVISO: sin certificado /certs/$N.crt; PostgreSQL arranca sin TLS" >&2
exec docker-entrypoint.sh "$@"
