-- db/sede1/init.sql
-- Sede 1 · Sincelejo · PostgreSQL (pg_sede1)
-- Datos 100 % sintéticos. fhir_patient_id en NULL: la cobertura FHIR arranca en 0 %.

\i /docker-entrypoint-initdb.d/00_schema.sql

INSERT INTO sede (sede_id, nombre, ciudad, codigo_prestador, motor) VALUES
    (1, 'IPS Sincelejo Central',    'Sincelejo', '700010000101', 'postgresql'),
    (2, 'IPS Cartagena Bocagrande', 'Cartagena', '130010000202', 'mongodb'),
    (3, 'IPS Corozal La Perla',     'Corozal',   '702150000303', 'postgresql')
ON CONFLICT (sede_id) DO NOTHING;

INSERT INTO profesional_salud (codigo, nombre_completo, especialidad, registro_medico, sede_id) VALUES
    ('MED-01', 'Dra. Laura Vega',     'Medicina general', 'RM-10492-SIN', 1),
    ('MED-04', 'Dr. Alfonso Bermejo', 'Medicina interna', 'RM-11204-SIN', 1)
ON CONFLICT (codigo) DO NOTHING;

-- Paciente 1001 (Carlos Perez) tiene atenciones en las 3 sedes (requisito RF4)
INSERT INTO usuario (documento_id, tipo_documento, pais_nacionalidad, nombre_completo, apellidos, nombres,
    fecha_nacimiento, edad, unidad_edad, sexo, genero, ocupacion, voluntad_anticipada, categoria_discapacidad,
    pais_residencia, municipio_residencia, etnia, zona_residencia, direccion_residencia, telefono,
    correo_electronico, nombre_responsable, parentesco_responsable, telefono_responsable,
    fhir_patient_id, sede_origen_id) VALUES
    ('1001', 'CC', 'CO', 'Carlos Perez', 'Perez', 'Carlos', '1980-04-12', 46, '1', 'M', '01', 'Docente',
     FALSE, '08', 'CO', '70001', '06', '01', 'Calle 22 # 14-30, Sincelejo', '3001234567',
     'carlos.perez@correo.test', 'Ana Perez', '03', '3007654321', NULL, 1),
    ('1002', 'CC', 'CO', 'Maria Fernandez Diaz', 'Fernandez Diaz', 'Maria', '1992-09-25', 34, '1', 'F', '02',
     'Contadora', FALSE, '08', 'CO', '70001', '06', '01', 'Carrera 19 # 25-10, Sincelejo', '3109876543',
     NULL, NULL, NULL, NULL, NULL, 1)
ON CONFLICT (documento_id) DO NOTHING;

INSERT INTO atencion (numero_visita, documento_id, sede_id, entidad_salud, fecha_ingreso, modalidad_entrega,
    entorno_atencion, via_ingreso, causa_atencion, fecha_triage, clasificacion_triage, clase_atencion,
    codigo_profesional, estado) VALUES
    ('V-S1-0150', '1001', 1, 'Nueva EPS', '2026-11-07 11:00:00', '01', '01', '01',
     'Cefalea intensa y cifras tensionales elevadas', '2026-11-07 11:05:00', '2', 'E', 'MED-01', 'FINALIZADA'),
    ('V-S1-0151', '1002', 1, 'Sanitas EPS', '2026-10-15 08:30:00', '01', '02', '01',
     'Control de cefalea recurrente', NULL, NULL, 'O', 'MED-04', 'FINALIZADA')
ON CONFLICT (numero_visita) DO NOTHING;

INSERT INTO diagnostico (diagnostico_id, numero_visita, cie10_codigo, descripcion_cie10, rol, tipo_diagnostico, orden, fecha_diagnostico) VALUES
    ('cond-V-S1-0150-ing-I10', 'V-S1-0150', 'I10', 'Hipertensión esencial', 'INGRESO', '01', 1, '2026-11-07'),
    ('cond-V-S1-0150-egr-I10', 'V-S1-0150', 'I10', 'Hipertensión esencial', 'EGRESO',  '01', 1, '2026-11-07'),
    ('cond-V-S1-0150-rel-R51', 'V-S1-0150', 'R51', 'Cefalea',               'RELACIONADO', '02', 1, '2026-11-07'),
    ('cond-V-S1-0151-ing-R51', 'V-S1-0151', 'R51', 'Cefalea',               'INGRESO', '01', 1, '2026-10-15')
ON CONFLICT (diagnostico_id) DO NOTHING;

INSERT INTO tecnologia_salud (tecnologia_id, numero_visita, tipo, loinc_codigo, descripcion_loinc, valor, unidad, fecha_toma) VALUES
    ('obs-V-S1-0150-8480-6', 'V-S1-0150', 'LABORATORIO', '8480-6', 'Presión arterial sistólica', 145.00, 'mm[Hg]', '2026-11-07 11:15:00')
ON CONFLICT (tecnologia_id) DO NOTHING;

INSERT INTO tecnologia_salud (tecnologia_id, numero_visita, tipo, descripcion_medicamento, dosis, via_administracion,
    frecuencia, dias_tratamiento, unidades_aplicadas, id_personal_salud, finalidad_tecnologia) VALUES
    ('med-V-S1-0150-losartan', 'V-S1-0150', 'MEDICAMENTO', 'Losartán 50 mg tableta', '50 mg', '01',
     'Cada 12 horas', 30, 60, 'MED-01', '01')
ON CONFLICT (tecnologia_id) DO NOTHING;

INSERT INTO egreso (numero_visita, fecha_salida, condicion_salida, codigo_prestador, tipo_incapacidad,
    dias_incapacidad, alergias, antecedentes_familiares, riesgos_ocupacionales, responsable_egreso) VALUES
    ('V-S1-0150', '2026-11-07 15:30:00', '01', '700010000101', '01', 2, 'Penicilina',
     'Padre con hipertensión arterial', 'Uso prolongado de la voz', 'Dra. Laura Vega')
ON CONFLICT (numero_visita) DO NOTHING;
