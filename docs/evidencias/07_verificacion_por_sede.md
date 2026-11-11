# Verificación de interoperabilidad por sede

Ejecutado el 2026-11-11 08:51 contra `http://192.168.1.94:8000` (script `scripts/verificar_interoperabilidad.py`).

**Resultado: 63 de 63 comprobaciones correctas (100.0 %).**

| Ámbito | Correctas |
|---|---|
| Sede 1 · Sincelejo (PostgreSQL) | 18 / 18 |
| Sede 2 · Cartagena (MongoDB) | 18 / 18 |
| Sede 3 · Corozal (PostgreSQL) | 18 / 18 |
| Red (3 sedes) | 9 / 9 |

## Sede 1 · Sincelejo (PostgreSQL)

| Sección | Comprobación | Resultado | Detalle |
|---|---|---|---|
| HL7 v2 | ADT^A01 entregado | ✅ | entregado |
| FHIR | Patient y Encounter en HAPI | ✅ | pac-84616592 |
| Base de la sede | Guardado en PostgreSQL y leído por la consulta unificada | ✅ | [1] |
| Idempotencia | Reenvío del mismo HL7 = duplicado | ✅ | duplicado |
| HL7 v2 | ORU^R01 entregado y Observation LOINC en HAPI | ✅ | entregado |
| FHIR | El ORU no borra el diagnóstico del Encounter | ✅ | diagnosis presente |
| CSV legado | Fila CSV entregada con dx_local -> CIE-10 | ✅ | 1 |
| FHIR | Condition I10 del CSV en HAPI | ✅ | pac-80872494 |
| JSON | Registro JSON entregado | ✅ | entregado |
| Admisión | Paciente admitido y publicado en FHIR | ✅ | pac-80195340 |
| Cuentas | Cuenta del portal creada (origen ADMISION, clave temporal) | ✅ | 80195340 |
| Médico | Diagnostico guardado con código de verificación | ✅ | entregado |
| Médico | Formula guardado con código de verificación | ✅ | entregado |
| Médico | Egreso guardado con código de verificación | ✅ | entregado |
| Médico | La sede conserva ingreso, relacionado, egreso, fórmula y laboratorio | ✅ | dx=['EGRESO', 'INGRESO', 'RELACIONADO'] tecnologías=2 |
| FHIR | Encounter finalizado con diagnóstico de ingreso y egreso | ✅ | finished ['AD', 'DD'] |
| 57 campos | Obligatorios cubiertos (paciente de la prueba) | ✅ | 34/57 · obligatorios 87.0 % |
| Cobertura FHIR | Pacientes de la sede publicados en FHIR | ✅ | 100.0 % |

## Sede 2 · Cartagena (MongoDB)

| Sección | Comprobación | Resultado | Detalle |
|---|---|---|---|
| HL7 v2 | ADT^A01 entregado | ✅ | entregado |
| FHIR | Patient y Encounter en HAPI | ✅ | pac-84348355 |
| Base de la sede | Guardado en MongoDB y leído por la consulta unificada | ✅ | [2] |
| Idempotencia | Reenvío del mismo HL7 = duplicado | ✅ | duplicado |
| HL7 v2 | ORU^R01 entregado y Observation LOINC en HAPI | ✅ | entregado |
| FHIR | El ORU no borra el diagnóstico del Encounter | ✅ | diagnosis presente |
| CSV legado | Fila CSV entregada con dx_local -> CIE-10 | ✅ | 1 |
| FHIR | Condition I10 del CSV en HAPI | ✅ | pac-80988759 |
| JSON | Registro JSON entregado | ✅ | entregado |
| Admisión | Paciente admitido y publicado en FHIR | ✅ | pac-84053834 |
| Cuentas | Cuenta del portal creada (origen ADMISION, clave temporal) | ✅ | 84053834 |
| Médico | Diagnostico guardado con código de verificación | ✅ | entregado |
| Médico | Formula guardado con código de verificación | ✅ | entregado |
| Médico | Egreso guardado con código de verificación | ✅ | entregado |
| Médico | La sede conserva ingreso, relacionado, egreso, fórmula y laboratorio | ✅ | dx=['EGRESO', 'INGRESO', 'RELACIONADO'] tecnologías=2 |
| FHIR | Encounter finalizado con diagnóstico de ingreso y egreso | ✅ | finished ['AD', 'DD'] |
| 57 campos | Obligatorios cubiertos (paciente de la prueba) | ✅ | 34/57 · obligatorios 87.0 % |
| Cobertura FHIR | Pacientes de la sede publicados en FHIR | ✅ | 100.0 % |

## Sede 3 · Corozal (PostgreSQL)

| Sección | Comprobación | Resultado | Detalle |
|---|---|---|---|
| HL7 v2 | ADT^A01 entregado | ✅ | entregado |
| FHIR | Patient y Encounter en HAPI | ✅ | pac-83223373 |
| Base de la sede | Guardado en PostgreSQL y leído por la consulta unificada | ✅ | [3] |
| Idempotencia | Reenvío del mismo HL7 = duplicado | ✅ | duplicado |
| HL7 v2 | ORU^R01 entregado y Observation LOINC en HAPI | ✅ | entregado |
| FHIR | El ORU no borra el diagnóstico del Encounter | ✅ | diagnosis presente |
| CSV legado | Fila CSV entregada con dx_local -> CIE-10 | ✅ | 1 |
| FHIR | Condition I10 del CSV en HAPI | ✅ | pac-80701780 |
| JSON | Registro JSON entregado | ✅ | entregado |
| Admisión | Paciente admitido y publicado en FHIR | ✅ | pac-84826031 |
| Cuentas | Cuenta del portal creada (origen ADMISION, clave temporal) | ✅ | 84826031 |
| Médico | Diagnostico guardado con código de verificación | ✅ | entregado |
| Médico | Formula guardado con código de verificación | ✅ | entregado |
| Médico | Egreso guardado con código de verificación | ✅ | entregado |
| Médico | La sede conserva ingreso, relacionado, egreso, fórmula y laboratorio | ✅ | dx=['EGRESO', 'INGRESO', 'RELACIONADO'] tecnologías=2 |
| FHIR | Encounter finalizado con diagnóstico de ingreso y egreso | ✅ | finished ['AD', 'DD'] |
| 57 campos | Obligatorios cubiertos (paciente de la prueba) | ✅ | 34/57 · obligatorios 87.0 % |
| Cobertura FHIR | Pacientes de la sede publicados en FHIR | ✅ | 100.0 % |

## Red (3 sedes)

| Sección | Comprobación | Resultado | Detalle |
|---|---|---|---|
| Consulta unificada | Un paciente atendido en las 3 sedes aparece completo | ✅ | sedes [1, 2, 3] |
| Consulta unificada | Mezcla PostgreSQL y MongoDB en una sola historia | ✅ | ['mongodb', 'postgresql'] |
| FHIR | Bundle de las 3 sedes validado por HAPI ($validate) | ✅ | 0 errores |
| FHIR | Bundle del paciente 1001 validado | ✅ |  |
| Seguridad | Paciente que pide la historia de otro = 403 | ✅ | 403 |
| Seguridad | Admisionista que pide una historia clínica = 403 | ✅ | 403 |
| Seguridad | Administrador de sede 2 no puede crear usuarios en la sede 1 | ✅ | 403 |
| Auditoría | Cadena SHA-256 íntegra | ✅ | 69 eventos |
| Salud | Bus, HAPI y las 3 sedes UP | ✅ | {"sede_1": {"motor": "postgresql", "estado": "UP"}, "sede_2": {"motor": "mongodb", "estado": "UP"}, "sede_3": {"motor": "postgresql", "estado": "UP"}} |
