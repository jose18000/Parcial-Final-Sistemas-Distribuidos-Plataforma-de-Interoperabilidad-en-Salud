-- db/sede3/init.sql
-- Sede 3 · Corozal · PostgreSQL (pg_sede3). Esta sede envía CSV legado al bus.
-- Datos 100 % sintéticos. fhir_patient_id en NULL: la cobertura FHIR arranca en 0 %.

\i /docker-entrypoint-initdb.d/00_schema.sql

INSERT INTO sede (sede_id, nombre, ciudad, codigo_prestador, motor) VALUES
    (1, 'IPS Sincelejo Central',    'Sincelejo', '700010000101', 'postgresql'),
    (2, 'IPS Cartagena Bocagrande', 'Cartagena', '130010000202', 'mongodb'),
    (3, 'IPS Corozal La Perla',     'Corozal',   '702150000303', 'postgresql')
ON CONFLICT (sede_id) DO NOTHING;

INSERT INTO profesional_salud (codigo, nombre_completo, especialidad, registro_medico, sede_id) VALUES
    ('MED-01', 'Dra. Laura Vega',   'Medicina general (rotativa)', 'RM-10492-SIN', 3),
    ('MED-02', 'Dr. Mateo Ruiz',    'Neumología (interconsulta)',  'RM-20831-CTG', 3),
    ('MED-03', 'Dr. Camilo Orozco', 'Urgencias',                   'RM-33109-CRZ', 3)
ON CONFLICT (codigo) DO NOTHING;

-- 1001 también se atendió aquí: completa el paciente con registros en las 3 sedes.
-- 1008, 1009 y 1010 llegan por el CSV legado (ejemplos/04_sede3_legado.csv); aquí solo existe 1001.
INSERT INTO usuario (documento_id, tipo_documento, pais_nacionalidad, nombre_completo, apellidos, nombres,
    fecha_nacimiento, edad, unidad_edad, sexo, pais_residencia, municipio_residencia, zona_residencia,
    direccion_residencia, telefono, fhir_patient_id, sede_origen_id) VALUES
    ('1001', 'CC', 'CO', 'Carlos Perez', 'Perez', 'Carlos', '1980-04-12', 46, '1', 'M', 'CO', '70001', '01',
     'Calle 22 # 14-30, Sincelejo', '3001234567', NULL, 1)
ON CONFLICT (documento_id) DO NOTHING;

INSERT INTO atencion (numero_visita, documento_id, sede_id, entidad_salud, fecha_ingreso, modalidad_entrega,
    entorno_atencion, via_ingreso, causa_atencion, fecha_triage, clasificacion_triage, clase_atencion,
    codigo_profesional, estado) VALUES
    ('V-S3-0045', '1001', 3, 'Nueva EPS', '2026-05-10 18:30:00', '01', '01', '01',
     'Deposiciones líquidas y deshidratación leve', '2026-05-10 18:35:00', '3', 'E', 'MED-03', 'FINALIZADA')
ON CONFLICT (numero_visita) DO NOTHING;

INSERT INTO diagnostico (diagnostico_id, numero_visita, cie10_codigo, descripcion_cie10, rol, tipo_diagnostico, orden, fecha_diagnostico) VALUES
    ('cond-V-S3-0045-ing-A09', 'V-S3-0045', 'A09', 'Diarrea y gastroenteritis de presunto origen infeccioso', 'INGRESO', '01', 1, '2026-05-10'),
    ('cond-V-S3-0045-egr-A09', 'V-S3-0045', 'A09', 'Diarrea y gastroenteritis de presunto origen infeccioso', 'EGRESO',  '01', 1, '2026-05-10')
ON CONFLICT (diagnostico_id) DO NOTHING;

INSERT INTO tecnologia_salud (tecnologia_id, numero_visita, tipo, loinc_codigo, descripcion_loinc, valor, unidad, fecha_toma) VALUES
    ('obs-V-S3-0045-2951-2', 'V-S3-0045', 'LABORATORIO', '2951-2', 'Sodio en suero o plasma',   138.00, 'mmol/L', '2026-05-10 19:00:00'),
    ('obs-V-S3-0045-2823-3', 'V-S3-0045', 'LABORATORIO', '2823-3', 'Potasio en suero o plasma',   4.10, 'mmol/L', '2026-05-10 19:00:00')
ON CONFLICT (tecnologia_id) DO NOTHING;

INSERT INTO tecnologia_salud (tecnologia_id, numero_visita, tipo, descripcion_medicamento, dosis, via_administracion,
    frecuencia, dias_tratamiento, unidades_aplicadas, id_personal_salud, finalidad_tecnologia) VALUES
    ('med-V-S3-0045-sro', 'V-S3-0045', 'MEDICAMENTO', 'Sales de rehidratación oral sobre', '1 sobre', '01',
     'Después de cada deposición', 3, 6, 'MED-03', '01')
ON CONFLICT (tecnologia_id) DO NOTHING;

INSERT INTO egreso (numero_visita, fecha_salida, condicion_salida, codigo_prestador, alergias, responsable_egreso) VALUES
    ('V-S3-0045', '2026-05-10 21:00:00', '01', '702150000303', 'Ninguna conocida', 'Dr. Camilo Orozco')
ON CONFLICT (numero_visita) DO NOTHING;
