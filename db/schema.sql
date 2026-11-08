-- db/schema.sql
-- Esquema relacional homogéneo para cada nodo de sede (Sincelejo, Cartagena, Corozal)

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Tabla de Sedes
CREATE TABLE IF NOT EXISTS sede (
    sede_id INTEGER PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    ciudad VARCHAR(100) NOT NULL,
    activa BOOLEAN DEFAULT TRUE,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Tabla de Profesionales de la Salud
CREATE TABLE IF NOT EXISTS profesional_salud (
    codigo VARCHAR(50) PRIMARY KEY,
    nombre_completo VARCHAR(150) NOT NULL,
    especialidad VARCHAR(100) NOT NULL,
    registro_medico VARCHAR(50),
    sede_id INTEGER REFERENCES sede(sede_id),
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Tabla de Usuarios (Pacientes)
CREATE TABLE IF NOT EXISTS usuario (
    documento_id VARCHAR(20) PRIMARY KEY,
    tipo_documento VARCHAR(10) DEFAULT 'CC',
    nombre_completo VARCHAR(150) NOT NULL,
    fecha_nacimiento DATE NOT NULL,
    sexo CHAR(1) CHECK (sexo IN ('M', 'F', 'O')),
    direccion VARCHAR(200),
    telefono VARCHAR(50),
    fhir_patient_id VARCHAR(100) DEFAULT NULL, -- Nullable para iniciar con cobertura FHIR 0%
    sede_origen_id INTEGER REFERENCES sede(sede_id),
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Tabla de Atenciones (Encounter)
CREATE TABLE IF NOT EXISTS atencion (
    numero_visita VARCHAR(50) PRIMARY KEY,
    clase_atencion VARCHAR(20) NOT NULL, -- E (Urgencia), O (Ambulatoria), I (Hospitalización)
    fecha_ingreso TIMESTAMP NOT NULL,
    fecha_egreso TIMESTAMP,
    triage INTEGER CHECK (triage BETWEEN 1 AND 5),
    estado VARCHAR(20) DEFAULT 'FINALIZADA', -- EN_CURSO, FINALIZADA, CANCELADA
    fhir_encounter_id VARCHAR(100) DEFAULT NULL,
    documento_id VARCHAR(20) NOT NULL REFERENCES usuario(documento_id),
    sede_id INTEGER NOT NULL REFERENCES sede(sede_id),
    codigo_profesional VARCHAR(50) REFERENCES profesional_salud(codigo),
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Tabla de Diagnósticos (Condition CIE-10)
CREATE TABLE IF NOT EXISTS diagnostico (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cie10_codigo VARCHAR(10) NOT NULL,
    descripcion_cie10 VARCHAR(250) NOT NULL,
    tipo VARCHAR(20) DEFAULT 'PRINCIPAL', -- PRINCIPAL, RELACIONADO
    fecha_diagnostico DATE NOT NULL,
    fhir_condition_id VARCHAR(100) DEFAULT NULL,
    numero_visita VARCHAR(50) NOT NULL REFERENCES atencion(numero_visita) ON DELETE CASCADE,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. Tabla de Tecnologías en Salud / Laboratorios (Observation LOINC)
CREATE TABLE IF NOT EXISTS tecnologia_salud (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    loinc_codigo VARCHAR(20) NOT NULL,
    descripcion_loinc VARCHAR(250) NOT NULL,
    valor NUMERIC(10, 2) NOT NULL,
    unidad VARCHAR(50) NOT NULL,
    fecha_toma TIMESTAMP NOT NULL,
    tipo VARCHAR(50) DEFAULT 'LABORATORIO',
    fhir_observation_id VARCHAR(100) DEFAULT NULL,
    numero_visita VARCHAR(50) NOT NULL REFERENCES atencion(numero_visita) ON DELETE CASCADE,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 7. Tabla de Egreso Clínico
CREATE TABLE IF NOT EXISTS egreso (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    fecha_egreso TIMESTAMP NOT NULL,
    motivo_egreso VARCHAR(100) NOT NULL,
    condicion_salida VARCHAR(100) NOT NULL,
    destino_post_egreso VARCHAR(100) NOT NULL,
    sello_hash VARCHAR(64) NOT NULL, -- SHA-256 de integridad del egreso
    numero_visita VARCHAR(50) UNIQUE NOT NULL REFERENCES atencion(numero_visita) ON DELETE CASCADE,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 8. Tabla de Mensajes del Bus (HSB & Idempotencia)
CREATE TABLE IF NOT EXISTS mensaje_bus (
    mensaje_id VARCHAR(100) PRIMARY KEY,
    formato VARCHAR(20) NOT NULL, -- HL7_V2, CSV
    sede_origen INTEGER NOT NULL REFERENCES sede(sede_id),
    tipo_mensaje VARCHAR(50) NOT NULL, -- ADT_A01, ORU_R01, CSV_BATCH
    estado VARCHAR(30) NOT NULL DEFAULT 'RECIBIDO', -- RECIBIDO, VALIDADO, TRANSFORMADO, ENTREGADO, RECHAZADO, REINTENTANDO, MUERTO
    intentos INTEGER DEFAULT 0,
    recibido_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    entregado_en TIMESTAMP,
    hash_contenido VARCHAR(64) NOT NULL UNIQUE, -- SHA-256 para idempotencia física
    motivo_rechazo TEXT,
    bundle_id VARCHAR(100)
);

-- 9. Tabla de Eventos de Auditoría Encadenada por Hash
CREATE TABLE IF NOT EXISTS evento_auditoria (
    evento_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tipo_evento VARCHAR(50) NOT NULL, -- LOGIN, CONSULTA_HC, ESCRITURA_HC, ACCESO_DENEGADO, HSB_ENTREGA
    usuario_sistema VARCHAR(100) NOT NULL,
    rol VARCHAR(50) NOT NULL,
    recurso_afectado VARCHAR(150),
    resultado VARCHAR(30) NOT NULL, -- EXITOSO, FALLIDO, DENEGADO
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    hash_anterior VARCHAR(64) NOT NULL,
    hash_propio VARCHAR(64) NOT NULL,
    detalle_json JSONB
);

-- Índices de consulta frecuente por paciente y fecha
CREATE INDEX IF NOT EXISTS idx_atencion_doc ON atencion(documento_id);
CREATE INDEX IF NOT EXISTS idx_diagnostico_visita ON diagnostico(numero_visita);
CREATE INDEX IF NOT EXISTS idx_tecnologia_visita ON tecnologia_salud(numero_visita);
CREATE INDEX IF NOT EXISTS idx_mensaje_bus_hash ON mensaje_bus(hash_contenido);
CREATE INDEX IF NOT EXISTS idx_evento_auditoria_ts ON evento_auditoria(timestamp);

