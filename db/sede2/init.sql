-- db/sede2/init.sql
-- Inicialización Sede 2: Cartagena (pg_sede2 :5434)

\i /docker-entrypoint-initdb.d/00_schema.sql

-- 1. Sede
INSERT INTO sede (sede_id, nombre, ciudad, activa)
VALUES (2, 'IPS Cartagena Bocagrande', 'Cartagena', TRUE)
ON CONFLICT (sede_id) DO NOTHING;

-- 2. Profesionales de Sede 2
INSERT INTO profesional_salud (codigo, nombre_completo, especialidad, registro_medico, sede_id)
VALUES 
    ('MED-02', 'Dr. Mateo Ruiz', 'Neumología', 'RM-20831-CTG', 2),
    ('MED-05', 'Dra. Patricia Gomez', 'Pediatría', 'RM-22190-CTG', 2)
ON CONFLICT (codigo) DO NOTHING;

-- 3. Pacientes sintéticos
-- NOTA CRÍTICA: fhir_patient_id es NULL (cobertura FHIR arranca en 0%)
-- Paciente 1001 (Carlos Perez) con atenciones aquí también (Sede 2)
INSERT INTO usuario (documento_id, tipo_documento, nombre_completo, fecha_nacimiento, sexo, direccion, telefono, fhir_patient_id, sede_origen_id)
VALUES 
    ('1001', 'CC', 'Carlos Perez', '1980-04-12', 'M', 'Calle 22 # 14-30, Sincelejo (Temporal CTG)', '3001234567', NULL, 1),
    ('1007', 'CC', 'Andrea Rojas', '1990-02-14', 'F', 'Avenida San Martin # 8-12, Cartagena', '3157778899', NULL, 2)
ON CONFLICT (documento_id) DO NOTHING;

-- 4. Atenciones en Sede 2
INSERT INTO atencion (numero_visita, clase_atencion, fecha_ingreso, fecha_egreso, triage, estado, fhir_encounter_id, documento_id, sede_id, codigo_profesional)
VALUES 
    ('V-S2-0080', 'O', '2026-08-20 14:00:00', '2026-08-20 15:00:00', 3, 'FINALIZADA', NULL, '1001', 2, 'MED-02'),
    ('V-S2-0101', 'O', '2026-11-07 10:15:00', NULL, 3, 'EN_CURSO', NULL, '1007', 2, 'MED-02')
ON CONFLICT (numero_visita) DO NOTHING;

-- 5. Diagnósticos
INSERT INTO diagnostico (cie10_codigo, descripcion_cie10, tipo, fecha_diagnostico, fhir_condition_id, numero_visita)
VALUES 
    ('J45.9', 'Asma, no especificada', 'PRINCIPAL', '2026-08-20', NULL, 'V-S2-0080'),
    ('J45.9', 'Asma, no especificada', 'PRINCIPAL', '2026-11-07', NULL, 'V-S2-0101');

-- 6. Observaciones
INSERT INTO tecnologia_salud (loinc_codigo, descripcion_loinc, valor, unidad, fecha_toma, tipo, fhir_observation_id, numero_visita)
VALUES 
    ('1988-5', 'Proteína C reactiva [Masa/volumen] en suero o plasma', 2.10, 'mg/L', '2026-08-20 14:30:00', 'LABORATORIO', NULL, 'V-S2-0080');

-- 7. Egreso
INSERT INTO egreso (fecha_egreso, motivo_egreso, condicion_salida, destino_post_egreso, sello_hash, numero_visita)
VALUES 
    ('2026-08-20 15:00:00', 'Control ambulatorio cumplido', 'ESTABLE', 'DOMICILIO', '7c89f1e03b4d2a9e51c82f0d9b4a1c6e83d2f5a7b1e9c0d4f6a8b2c4e6d8f0a2', 'V-S2-0080');
