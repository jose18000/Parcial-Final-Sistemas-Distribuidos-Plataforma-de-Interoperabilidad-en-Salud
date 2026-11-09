-- db/sede3/init.sql
-- Inicialización Sede 3: Corozal (pg_sede3 :5435)

\i /docker-entrypoint-initdb.d/00_schema.sql

-- 1. Sede (catálogo completo de sedes)
INSERT INTO sede (sede_id, nombre, ciudad, activa)
VALUES
    (1, 'IPS Sincelejo Central',     'Sincelejo', TRUE),
    (2, 'IPS Cartagena Bocagrande',  'Cartagena', TRUE),
    (3, 'IPS Corozal La Perla',      'Corozal',   TRUE)
ON CONFLICT (sede_id) DO NOTHING;

-- 2. Profesionales de Sede 3
INSERT INTO profesional_salud (codigo, nombre_completo, especialidad, registro_medico, sede_id)
VALUES 
    ('MED-01', 'Dra. Laura Vega', 'Medicina General (Rotativa)', 'RM-10492-SIN', 3),
    ('MED-03', 'Dr. Camilo Orozco', 'Urgencias', 'RM-33109-CRZ', 3)
ON CONFLICT (codigo) DO NOTHING;

-- 3. Pacientes sintéticos
-- NOTA CRÍTICA: fhir_patient_id es NULL (cobertura FHIR arranca en 0%)
-- Paciente 1001 (Carlos Perez) con atenciones aquí también (Tercera sede: completa el requisito de 1 paciente en las 3 sedes)
INSERT INTO usuario (documento_id, tipo_documento, nombre_completo, fecha_nacimiento, sexo, direccion, telefono, fhir_patient_id, sede_origen_id)
VALUES 
    ('1001', 'CC', 'Carlos Perez', '1980-04-12', 'M', 'Calle 22 # 14-30, Sincelejo (Atencion Corozal)', '3001234567', NULL, 1),
    ('1008', 'CC', 'Camila Suarez Pineda', '1996-02-10', 'F', 'Carrera 28 # 12-40, Corozal', '3124445566', NULL, 3),
    ('1009', 'CC', 'Ricardo Mendoza Lara', '1971-07-19', 'M', 'Barrio San Jose Manzana B, Corozal', '3189991122', NULL, 3),
    ('1010', 'CC', 'Sofia Blanco Mesa', '2004-12-01', 'F', 'Calle 30 # 20-15, Corozal', '3015556677', NULL, 3)
ON CONFLICT (documento_id) DO NOTHING;

-- 4. Atenciones en Sede 3
INSERT INTO atencion (numero_visita, clase_atencion, fecha_ingreso, fecha_egreso, triage, estado, fhir_encounter_id, documento_id, sede_id, codigo_profesional)
VALUES 
    ('V-S3-0045', 'E', '2026-05-10 18:30:00', '2026-05-10 21:00:00', 3, 'FINALIZADA', NULL, '1001', 3, 'MED-03'),
    ('V-S3-0050', 'E', '2026-11-07 08:30:00', '2026-11-07 10:00:00', 3, 'FINALIZADA', NULL, '1008', 3, 'MED-01'),
    ('V-S3-0051', 'O', '2026-11-07 09:10:00', '2026-11-07 09:40:00', NULL, 'FINALIZADA', NULL, '1009', 3, 'MED-03')
ON CONFLICT (numero_visita) DO NOTHING;

-- 5. Diagnósticos
INSERT INTO diagnostico (cie10_codigo, descripcion_cie10, tipo, fecha_diagnostico, fhir_condition_id, numero_visita)
VALUES 
    ('A09', 'Diarrea y gastroenteritis de presunto origen infeccioso', 'PRINCIPAL', '2026-05-10', NULL, 'V-S3-0045'),
    ('A09', 'Diarrea y gastroenteritis de presunto origen infeccioso', 'PRINCIPAL', '2026-11-07', NULL, 'V-S3-0050'),
    ('I10', 'Hipertensión esencial', 'PRINCIPAL', '2026-11-07', NULL, 'V-S3-0051');

-- 6. Observaciones
INSERT INTO tecnologia_salud (loinc_codigo, descripcion_loinc, valor, unidad, fecha_toma, tipo, fhir_observation_id, numero_visita)
VALUES 
    ('2951-2', 'Sodio [Moles/volumen] en suero o plasma', 138.00, 'mmol/L', '2026-05-10 19:00:00', 'LABORATORIO', NULL, 'V-S3-0045'),
    ('2823-3', 'Potasio [Moles/volumen] en suero o plasma', 4.10, 'mmol/L', '2026-05-10 19:00:00', 'LABORATORIO', NULL, 'V-S3-0045');

-- 7. Egreso
INSERT INTO egreso (fecha_egreso, motivo_egreso, condicion_salida, destino_post_egreso, sello_hash, numero_visita)
VALUES 
    ('2026-05-10 21:00:00', 'Hidratacion oral exitosa', 'ESTABLE', 'DOMICILIO', '9f8e7d6c5b4a3928170e1f2d3c4b5a6978e0f1d2c3b4a59687e0f1d2c3b4a596', 'V-S3-0045'),
    ('2026-11-07 10:00:00', 'Plan de rehidratacion formulado', 'ESTABLE', 'DOMICILIO', '3b4c5d6e7f8a90123456789abcdef0123456789abcdef0123456789abcdef01', 'V-S3-0050');

