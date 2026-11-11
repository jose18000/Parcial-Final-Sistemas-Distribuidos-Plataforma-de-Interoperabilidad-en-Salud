-- db/central/init.sql
-- Base CENTRAL de la plataforma (pg_central). No es una sede: guarda la cadena de
-- auditoría que comparten la API y el bus. Separarla de las sedes permite apagar
-- cualquier sede en la demo sin perder la trazabilidad.

CREATE TABLE IF NOT EXISTS evento_auditoria (
    evento_id         UUID PRIMARY KEY,
    indice            INTEGER NOT NULL UNIQUE,        -- posición en la cadena (0 = primer evento)
    tipo_evento       VARCHAR(50)  NOT NULL,          -- LOGIN, CONSULTA_HC, ESCRITURA_HC, ACCESO_DENEGADO, ...
    usuario_sistema   VARCHAR(100) NOT NULL,          -- quién
    rol               VARCHAR(50)  NOT NULL,
    recurso_afectado  VARCHAR(200),                   -- qué
    resultado         VARCHAR(30)  NOT NULL,          -- EXITOSO, FALLIDO, DENEGADO
    timestamp         TEXT NOT NULL,                  -- cuándo (ISO 8601 exacto, entra al hash)
    detalle           TEXT NOT NULL DEFAULT '{}',     -- JSON canónico (llaves ordenadas), entra al hash
    hash_anterior     CHAR(64) NOT NULL,
    hash_propio       CHAR(64) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_auditoria_recurso ON evento_auditoria(recurso_afectado);

-- Cuentas de acceso (gestión de usuarios). La API siembra las cuentas iniciales al arrancar
-- (app/usuarios.py) con contraseñas PBKDF2-SHA256.
CREATE TABLE IF NOT EXISTS usuario_sistema (
    username            VARCHAR(60) PRIMARY KEY,
    password_hash       VARCHAR(200) NOT NULL,
    rol                 VARCHAR(20)  NOT NULL CHECK (rol IN ('paciente','admisionista','medico','auditor','administrador')),
    nombre_completo     VARCHAR(150) NOT NULL,
    documento_id        VARCHAR(20),
    sede_id             INTEGER CHECK (sede_id IN (1, 2, 3)),
    activo              BOOLEAN NOT NULL DEFAULT TRUE,
    debe_cambiar_clave  BOOLEAN NOT NULL DEFAULT FALSE,
    origen              VARCHAR(20)  NOT NULL DEFAULT 'PANEL',   -- SEMILLA, PANEL, ADMISION
    creado_por          VARCHAR(60),
    creado_en           TIMESTAMP NOT NULL DEFAULT NOW(),
    ultimo_acceso       TIMESTAMP
);

-- Base del servidor HAPI FHIR (persistencia de los recursos FHIR entre reinicios)
CREATE DATABASE hapi;
