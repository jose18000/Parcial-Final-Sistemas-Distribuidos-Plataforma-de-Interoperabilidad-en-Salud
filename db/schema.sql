-- db/schema.sql
-- Esquema RELACIONAL de los nodos PostgreSQL (Sede 1 Sincelejo y Sede 3 Corozal).
-- La Sede 2 Cartagena usa MongoDB (ver db/sede2/init-mongo.js).
--
-- Cubre los 57 campos de la historia clínica interoperable (Resolución 866 de 2021).
-- El número de campo va en el comentario de cada columna; el mapeo completo
-- HL7 / CSV / PostgreSQL / MongoDB / FHIR está en traductor/catalogo_57.py
-- y en docs/mapeo_57_campos.md.

-- 1. Sedes de la red
CREATE TABLE IF NOT EXISTS sede (
    sede_id          INTEGER PRIMARY KEY,
    nombre           VARCHAR(100) NOT NULL,
    ciudad           VARCHAR(100) NOT NULL,
    codigo_prestador VARCHAR(20)  NOT NULL,       -- código de habilitación REPS (campo 43)
    motor            VARCHAR(20)  NOT NULL,       -- postgresql | mongodb
    activa           BOOLEAN DEFAULT TRUE,
    creado_en        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Profesionales de la salud
CREATE TABLE IF NOT EXISTS profesional_salud (
    codigo           VARCHAR(50) PRIMARY KEY,
    nombre_completo  VARCHAR(150) NOT NULL,
    especialidad     VARCHAR(100) NOT NULL,
    registro_medico  VARCHAR(50),
    sede_id          INTEGER REFERENCES sede(sede_id),
    creado_en        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Usuario (paciente): campos 1-15 y 51-57
CREATE TABLE IF NOT EXISTS usuario (
    documento_id            VARCHAR(20) PRIMARY KEY,                    -- 2
    tipo_documento          VARCHAR(2)  NOT NULL DEFAULT 'CC',          -- 1
    pais_nacionalidad       VARCHAR(3),                                 -- 3  ISO 3166
    nombre_completo         VARCHAR(150) NOT NULL,                      -- 4
    apellidos               VARCHAR(100),
    nombres                 VARCHAR(100),
    fecha_nacimiento        DATE NOT NULL,                              -- 5
    edad                    INTEGER,                                    -- 6
    unidad_edad             VARCHAR(1),                                 -- 7  1 años, 2 meses, 3 días
    sexo                    CHAR(1) NOT NULL CHECK (sexo IN ('M','F','O')),  -- 8
    genero                  VARCHAR(2),                                 -- 9
    ocupacion               VARCHAR(100),                               -- 10
    voluntad_anticipada     BOOLEAN,                                    -- 11
    categoria_discapacidad  VARCHAR(2),                                 -- 12
    pais_residencia         VARCHAR(3),                                 -- 13
    municipio_residencia    VARCHAR(5),                                 -- 14 código DANE
    etnia                   VARCHAR(2),                                 -- 15
    zona_residencia         VARCHAR(2),                                 -- 51
    direccion_residencia    VARCHAR(200),                               -- 52
    telefono                VARCHAR(30),                                -- 53
    correo_electronico      VARCHAR(150),                               -- 54
    nombre_responsable      VARCHAR(150),                               -- 55
    parentesco_responsable  VARCHAR(2),                                 -- 56
    telefono_responsable    VARCHAR(30),                                -- 57
    fhir_patient_id         VARCHAR(100) DEFAULT NULL,   -- NULL al inicio: cobertura FHIR arranca en 0 %
    sede_origen_id          INTEGER REFERENCES sede(sede_id),
    creado_en               TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Atención (Encounter): campos 16-24
CREATE TABLE IF NOT EXISTS atencion (
    numero_visita         VARCHAR(60) PRIMARY KEY,
    documento_id          VARCHAR(20) NOT NULL REFERENCES usuario(documento_id),
    sede_id               INTEGER NOT NULL REFERENCES sede(sede_id),
    entidad_salud         VARCHAR(150),                                 -- 16
    fecha_ingreso         TIMESTAMP NOT NULL,                           -- 17
    modalidad_entrega     VARCHAR(2),                                   -- 18
    entorno_atencion      VARCHAR(2),                                   -- 19
    via_ingreso           VARCHAR(2),                                   -- 20
    causa_atencion        TEXT,                                         -- 21
    fecha_triage          TIMESTAMP,                                    -- 22
    clasificacion_triage  VARCHAR(1) CHECK (clasificacion_triage IN ('1','2','3','4','5')),  -- 23
    comunidad_etnica      VARCHAR(100),                                 -- 24
    clase_atencion        VARCHAR(1) NOT NULL DEFAULT 'O',  -- clase HL7 PV1-2: E, O, I
    codigo_profesional    VARCHAR(50),
    estado                VARCHAR(20) DEFAULT 'EN_CURSO',   -- EN_CURSO, FINALIZADA, CANCELADA
    fhir_encounter_id     VARCHAR(100) DEFAULT NULL,
    creado_en             TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Tecnologías en salud: medicamentos (campos 25-32) y resultados de laboratorio (LOINC)
CREATE TABLE IF NOT EXISTS tecnologia_salud (
    tecnologia_id            VARCHAR(100) PRIMARY KEY,   -- determinista: med-<visita>-<hash> / obs-<visita>-<loinc>
    numero_visita            VARCHAR(60) NOT NULL REFERENCES atencion(numero_visita) ON DELETE CASCADE,
    tipo                     VARCHAR(20) NOT NULL CHECK (tipo IN ('MEDICAMENTO','LABORATORIO')),
    descripcion_medicamento  VARCHAR(200),                -- 25
    dosis                    VARCHAR(50),                 -- 26
    via_administracion       VARCHAR(2),                  -- 27
    frecuencia               VARCHAR(50),                 -- 28
    dias_tratamiento         INTEGER,                     -- 29
    unidades_aplicadas       INTEGER,                     -- 30
    id_personal_salud        VARCHAR(50),                 -- 31
    finalidad_tecnologia     VARCHAR(2),                  -- 32
    loinc_codigo             VARCHAR(20),                 -- laboratorio
    descripcion_loinc        VARCHAR(200),
    valor                    NUMERIC(10,2),
    unidad                   VARCHAR(30),
    fecha_toma               TIMESTAMP,
    fhir_resource_id         VARCHAR(100) DEFAULT NULL,
    creado_en                TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. Diagnósticos (CIE-10): campos 33-39 como filas con rol
--    INGRESO -> 33/34, EGRESO -> 35/36, RELACIONADO orden 1..3 -> 37/38/39
CREATE TABLE IF NOT EXISTS diagnostico (
    diagnostico_id     VARCHAR(100) PRIMARY KEY,     -- determinista: cond-<visita>-<rol>-<cie10>
    numero_visita      VARCHAR(60) NOT NULL REFERENCES atencion(numero_visita) ON DELETE CASCADE,
    cie10_codigo       VARCHAR(10) NOT NULL CHECK (cie10_codigo ~ '^[A-Z][0-9]{2}(\.[0-9]{1,4})?$'),
    descripcion_cie10  VARCHAR(250) NOT NULL,
    rol                VARCHAR(15) NOT NULL CHECK (rol IN ('INGRESO','EGRESO','RELACIONADO')),
    tipo_diagnostico   VARCHAR(2) NOT NULL DEFAULT '01',  -- 01 principal, 02 relacionado, 03 complicación
    orden              INTEGER NOT NULL DEFAULT 1,
    fecha_diagnostico  DATE,
    fhir_condition_id  VARCHAR(100) DEFAULT NULL,
    creado_en          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 7. Egreso: campos 40-50
--    La fila puede existir antes del egreso: datos como las alergias (47) se conocen desde el
--    ingreso. La atención está egresada cuando fecha_salida (40) tiene valor.
CREATE TABLE IF NOT EXISTS egreso (
    numero_visita            VARCHAR(60) PRIMARY KEY REFERENCES atencion(numero_visita) ON DELETE CASCADE,
    fecha_salida             TIMESTAMP,                   -- 40 (NULL = aún no egresa)
    condicion_salida         VARCHAR(2),                  -- 41  01 vivo, 02 muerto
    diagnostico_muerte       VARCHAR(10),                 -- 42
    codigo_prestador         VARCHAR(20),                 -- 43
    tipo_incapacidad         VARCHAR(2),                  -- 44
    dias_incapacidad         INTEGER,                     -- 45
    dias_lic_maternidad      INTEGER,                     -- 46
    alergias                 TEXT,                        -- 47
    antecedentes_familiares  TEXT,                        -- 48
    riesgos_ocupacionales    TEXT,                        -- 49
    responsable_egreso       VARCHAR(150),                -- 50
    sello_hash               VARCHAR(64),                 -- SHA-256 del evento de auditoría del egreso
    creado_en                TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 8. Mensajes del bus (estado, reintentos e idempotencia persistente)
CREATE TABLE IF NOT EXISTS mensaje_bus (
    mensaje_id      VARCHAR(100) PRIMARY KEY,                -- MSH-10 o hash de la fila CSV
    formato         VARCHAR(20) NOT NULL,                    -- HL7_V2, CSV, JSON
    sede_origen     INTEGER NOT NULL,
    tipo_mensaje    VARCHAR(50) NOT NULL,
    estado          VARCHAR(30) NOT NULL DEFAULT 'RECIBIDO', -- RECIBIDO, VALIDADO, TRANSFORMADO, ENTREGADO,
                                                             -- RECHAZADO, REINTENTANDO, MUERTO
    intentos        INTEGER DEFAULT 0,
    recibido_en     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    entregado_en    TIMESTAMP,
    hash_contenido  VARCHAR(64) NOT NULL UNIQUE,
    motivo_rechazo  TEXT,
    bundle_id       VARCHAR(100),
    contenido       TEXT                                     -- mensaje original, para poder reencolar
);

CREATE INDEX IF NOT EXISTS idx_atencion_doc         ON atencion(documento_id);
CREATE INDEX IF NOT EXISTS idx_diagnostico_visita   ON diagnostico(numero_visita);
CREATE INDEX IF NOT EXISTS idx_tecnologia_visita    ON tecnologia_salud(numero_visita);
CREATE INDEX IF NOT EXISTS idx_mensaje_bus_estado   ON mensaje_bus(estado);
