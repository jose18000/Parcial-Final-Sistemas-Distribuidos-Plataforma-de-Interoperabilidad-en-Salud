#!/bin/sh
# Healthcheck de MongoDB: con TLS si está activo.
if [ -f /etc/mongo-tls/ca.pem ]; then
  exec mongosh --quiet --tls --tlsCAFile /etc/mongo-tls/ca.pem --host localhost --eval "db.adminCommand('ping').ok"
fi
exec mongosh --quiet --eval "db.adminCommand('ping').ok"
