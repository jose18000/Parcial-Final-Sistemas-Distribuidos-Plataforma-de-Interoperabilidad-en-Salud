-- db/demo_acid.sql
-- Demostración de Atomicidad (Propiedad A de ACID) en PostgreSQL
-- Intenta insertar usuario y atención forzando un error intencional a la mitad.

\echo '====================================================='
\echo 'PASO 1: ESTADO INICIAL (Verificar que usuario 9999 no existe)'
\echo '====================================================='
SELECT documento_id, nombre_completo FROM usuario WHERE documento_id = '9999';
SELECT numero_visita, documento_id FROM atencion WHERE numero_visita = 'V-TEST-FAIL';

\echo ''
\echo '====================================================='
\echo 'PASO 2: INICIAR TRANSACCIÓN Y FORZAR ERROR'
\echo '====================================================='
BEGIN;

-- 2.1 Insertar usuario (operación exitosa en memoria de la transacción)
INSERT INTO usuario (documento_id, tipo_documento, nombre_completo, fecha_nacimiento, sexo, direccion_residencia, telefono, sede_origen_id)
VALUES ('9999', 'CC', 'Paciente Prueba Fallo', '1995-01-01', 'M', 'Calle Falsa 123', '3000000000', 1);

-- 2.2 Intentar insertar atención con violación intencional de CHECK constraint
--     (clasificacion_triage = '9': solo se permite '1' a '5', campo 23 de la Res. 866)
-- Esto provoca un error fatal de constraint a nivel de base de datos
INSERT INTO atencion (numero_visita, clase_atencion, fecha_ingreso, clasificacion_triage, estado, documento_id, sede_id)
VALUES ('V-TEST-FAIL', 'E', NOW(), '9', 'EN_CURSO', '9999', 1);

-- 2.3 Si no hubiera fallado, haría commit
COMMIT;

\echo ''
\echo '====================================================='
\echo 'PASO 3: ESTADO POSTERIOR AL ERROR (Verificar Rollback total)'
\echo '====================================================='
-- PostgreSQL realiza automáticamente un ROLLBACK de toda la transacción.
-- Ni el usuario 9999 ni la atención deben existir en la base de datos.
SELECT documento_id, nombre_completo FROM usuario WHERE documento_id = '9999';
SELECT numero_visita, documento_id FROM atencion WHERE numero_visita = 'V-TEST-FAIL';

\echo '====================================================='
\echo 'CONCLUSION: Atomicidad demostrada. No queda ningún registro parcial.'
\echo '====================================================='

