#!/bin/sh
# db/seguridad/roles_central.sh — mínimo privilegio en la base central (pg_central).
#
#   api_central  la API: la auditoría es de SOLO AGREGAR (SELECT e INSERT, sin UPDATE ni DELETE);
#                gestiona cuentas (usuario_sistema) y refresh tokens OAuth (token_refresco)
#   hapi_srv     HAPI FHIR: dueño únicamente de su base "hapi"
#
# Corre al crear la base (docker-entrypoint-initdb.d) y desplegar.sh la reaplica. Idempotente.
psql -v ON_ERROR_STOP=1 -q --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v pw_api="${API_CENTRAL_DB_PASSWORD:?Falta API_CENTRAL_DB_PASSWORD}" \
     -v pw_hapi="${HAPI_DB_PASSWORD:?Falta HAPI_DB_PASSWORD}" -v base="$POSTGRES_DB" <<'SQL'
SELECT 'CREATE ROLE api_central' WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'api_central')\gexec
SELECT 'CREATE ROLE hapi_srv'    WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'hapi_srv')\gexec
ALTER ROLE api_central WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION CONNECTION LIMIT 40 PASSWORD :'pw_api';
ALTER ROLE hapi_srv    WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION CONNECTION LIMIT 60 PASSWORD :'pw_hapi';

-- Refresh tokens de OAuth 2.0: se guarda solo el hash SHA-256 del token, nunca el token.
CREATE TABLE IF NOT EXISTS token_refresco (
    hash_token   CHAR(64) PRIMARY KEY,
    username     VARCHAR(60)  NOT NULL,
    client_id    VARCHAR(60)  NOT NULL,
    scope        VARCHAR(400) NOT NULL,
    emitido_en   TIMESTAMP    NOT NULL DEFAULT NOW(),
    expira_en    TIMESTAMP    NOT NULL,
    revocado     BOOLEAN      NOT NULL DEFAULT FALSE,
    revocado_en  TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_token_refresco_usuario ON token_refresco(username);

REVOKE ALL ON DATABASE :"base" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"base" TO api_central;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO api_central;

GRANT SELECT, INSERT ON evento_auditoria TO api_central;
REVOKE UPDATE, DELETE, TRUNCATE ON evento_auditoria FROM api_central;
GRANT SELECT, INSERT, UPDATE ON usuario_sistema TO api_central;
REVOKE DELETE, TRUNCATE ON usuario_sistema FROM api_central;
GRANT SELECT, INSERT, UPDATE ON token_refresco TO api_central;

-- Base de HAPI: su propio dueño; nadie más se conecta.
REVOKE ALL ON DATABASE hapi FROM PUBLIC;
ALTER DATABASE hapi OWNER TO hapi_srv;
\c hapi
SELECT format('ALTER TABLE public.%I OWNER TO hapi_srv', tablename)
  FROM pg_tables WHERE schemaname = 'public' AND tableowner <> 'hapi_srv'\gexec
SELECT format('ALTER SEQUENCE public.%I OWNER TO hapi_srv', sequencename)
  FROM pg_sequences WHERE schemaname = 'public' AND sequenceowner <> 'hapi_srv'\gexec
SELECT format('ALTER VIEW public.%I OWNER TO hapi_srv', viewname)
  FROM pg_views WHERE schemaname = 'public' AND viewowner <> 'hapi_srv'\gexec
SELECT format('ALTER LARGE OBJECT %s OWNER TO hapi_srv', oid)
  FROM pg_largeobject_metadata WHERE lomowner <> 'hapi_srv'::regrole\gexec
SQL
echo "[seguridad] base central: api_central (auditoría solo INSERT/SELECT), hapi_srv (dueño de la base hapi)"
