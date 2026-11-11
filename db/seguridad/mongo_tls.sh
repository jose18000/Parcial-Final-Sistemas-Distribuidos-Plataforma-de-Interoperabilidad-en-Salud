#!/bin/sh
# db/seguridad/mongo_tls.sh — entrypoint del MongoDB de la Sede 2.
# TLS obligatorio (requireTLS) con el certificado firmado por la CA de la plataforma.
# Durante la inicialización el entrypoint oficial usa allowTLS solo para los scripts locales.
set -e
if [ -f /certs/mongo_sede2.pem ]; then
  mkdir -p /etc/mongo-tls
  install -o mongodb -g mongodb -m 600 /certs/mongo_sede2.pem /etc/mongo-tls/server.pem
  install -o mongodb -g mongodb -m 644 /certs/ca.pem /etc/mongo-tls/ca.pem
  exec docker-entrypoint.sh mongod --wiredTigerCacheSizeGB 0.25 --tlsMode requireTLS \
    --tlsCertificateKeyFile /etc/mongo-tls/server.pem --tlsCAFile /etc/mongo-tls/ca.pem \
    --tlsAllowConnectionsWithoutCertificates
fi
echo "[seguridad] AVISO: sin /certs/mongo_sede2.pem; MongoDB arranca sin TLS" >&2
exec docker-entrypoint.sh mongod --wiredTigerCacheSizeGB 0.25
