#!/bin/sh
# db/seguridad/roles_sede.sh — mínimo privilegio en la base PostgreSQL de una sede.
#
#   hsb_escritor  el bus: lee, inserta y actualiza; NO borra ni cambia la estructura
#   api_lector    la API: solo lee (consulta de historia, tablero)
#   clinica_user  superusuario/DBA: solo entra desde dentro del contenedor o con TLS
#
# Corre sola al crear la base (docker-entrypoint-initdb.d) y desplegar.sh la vuelve a aplicar
# en bases existentes (docker exec ... sh /seguridad/roles_sede.sh). Es idempotente.
psql -v ON_ERROR_STOP=1 -q --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v pw_hsb="${HSB_DB_PASSWORD:?Falta HSB_DB_PASSWORD}" -v pw_api="${API_DB_PASSWORD:?Falta API_DB_PASSWORD}" \
     -v base="$POSTGRES_DB" <<'SQL'
SELECT 'CREATE ROLE hsb_escritor' WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'hsb_escritor')\gexec
SELECT 'CREATE ROLE api_lector'   WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'api_lector')\gexec
ALTER ROLE hsb_escritor WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION CONNECTION LIMIT 40 PASSWORD :'pw_hsb';
ALTER ROLE api_lector   WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION CONNECTION LIMIT 40 PASSWORD :'pw_api';

REVOKE ALL ON DATABASE :"base" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"base" TO hsb_escritor, api_lector;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO hsb_escritor, api_lector;

GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO hsb_escritor;
REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA public FROM hsb_escritor;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO hsb_escritor;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO api_lector;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM api_lector;

ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE ON TABLES TO hsb_escritor;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO hsb_escritor;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO api_lector;
SQL
echo "[seguridad] roles de $POSTGRES_DB: hsb_escritor (SELECT/INSERT/UPDATE), api_lector (SELECT)"
