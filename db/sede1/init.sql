-- db/sede1/init.sql
-- Inicialización Sede 1: Sincelejo (pg_sede1 :5433)

\i /docker-entrypoint-initdb.d/00_schema.sql

-- 1. Sede (catálogo completo de sedes)
INSERT INTO sede (sede_id, nombre, ciudad, activa)
VALUES
    (1, 'IPS Sincelejo Central',     'Sincelejo', TRUE),
    (2, 'IPS Cartagena Bocagrande',  'Cartagena', TRUE),
    (3, 'IPS Corozal La Perla',      'Corozal',   TRUE)
ON CONFLICT (sede_id) DO NOTHING;

-- 2. Profesionales de Sede 1
INSERT INTO profesional_salud (codigo, nombre_completo, especialidad, registro_medico, sede_id)
VALUES 
    ('MED-01', 'Dra. Laura Vega', 'Medicina General', 'RM-10492-SIN', 1),
    ('MED-04', 'Dr. Alfonso Bermejo', 'Medicina Interna', 'RM-11204-SIN', 1)
ON CONFLICT (codigo) DO NOTHING;

-- 3. Pacientes sintéticos
-- NOTA CRÍTICA: fhir_patient_id es NULL (cobertura FHIR arranca en 0%)
-- Paciente 1001 (Carlos Perez) TIENE REGISTROS EN LAS 3 SEDES (requisito RF4/Paso 3)
INSERT INTO usuario (documento_id, tipo_documento, nombre_completo, fecha_nacimiento, sexo, direccion, telefono, fhir_patient_id, sede_origen_id)
VALUES 
    ('1001', 'CC', 'Carlos Perez', '1980-04-12', 'M', 'Calle 22 # 14-30, Sincelejo', '3001234567', NULL, 1),
    ('1002', 'CC', 'Maria Fernandez Diaz', '1992-09-25', 'F', 'Carrera 19 # 25-10, Sincelejo', '3109876543', NULL, 1)
ON CONFLICT (documento_id) DO NOTHING;

-- 4. Atenciones en Sede 1
INSERT INTO atencion (numero_visita, clase_atencion, fecha_ingreso, fecha_egreso, triage, estado, fhir_encounter_id, documento_id, sede_id, codigo_profesional)
VALUES 
    ('V-S1-0150', 'E', '2026-11-07 11:00:00', '2026-11-07 15:30:00', 2, 'FINALIZADA', NULL, '1001', 1, 'MED-01'),
    ('V-S1-0151', 'O', '2026-10-15 08:30:00', '2026-10-15 09:15:00', 4, 'FINALIZADA', NULL, '1002', 1, 'MED-04')
ON CONFLICT (numero_visita) DO NOTHING;

-- 5. Diagnósticos
INSERT INTO diagnostico (cie10_codigo, descripcion_cie10, tipo, fecha_diagnostico, fhir_condition_id, numero_visita)
VALUES 
    ('I10', 'Hipertensión esencial', 'PRINCIPAL', '2026-11-07', NULL, 'V-S1-0150'),
    ('R51', 'Cefalea', 'RELACIONADO', '2026-10-15', NULL, 'V-S1-0151');

-- 6. Tecnologías en salud / Observaciones
INSERT INTO tecnologia_salud (loinc_codigo, descripcion_loinc, valor, unidad, fecha_toma, tipo, fhir_observation_id, numero_visita)
VALUES 
    ('718-7', 'Hemoglobina [Masa/volumen] en sangre', 13.80, 'g/dL', '2026-11-07 11:30:00', 'LABORATORIO', NULL, 'V-S1-0150'),
    ('8480-6', 'Presión arterial sistólica', 145.00, 'mm[Hg]', '2026-11-07 11:15:00', 'SIGNO_VITAL', NULL, 'V-S1-0150');

-- 7. Egreso
INSERT INTO egreso (fecha_egreso, motivo_egreso, condicion_salida, destino_post_egreso, sello_hash, numero_visita)
VALUES 
    ('2026-11-07 15:30:00', 'Mejoria clinica', 'ESTABLE', 'DOMICILIO', 'a6b4f7e2d9c1048e91f03bb748a12e847c10d32f5891ac37de41b98a02c3d561', 'V-S1-0150');

