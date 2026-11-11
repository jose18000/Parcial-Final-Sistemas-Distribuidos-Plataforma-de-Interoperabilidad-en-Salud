# Verificación de interoperabilidad por sede

Ejecutado el 2026-11-11 12:06 contra `https://localhost:8000` (script `scripts/verificar_interoperabilidad.py`).

**Resultado: 70 de 70 comprobaciones correctas (100.0 %).**

| Ámbito | Correctas |
|---|---|
| Sede 1 · Sincelejo (PostgreSQL) | 18 / 18 |
| Sede 2 · Cartagena (MongoDB) | 18 / 18 |
| Sede 3 · Corozal (PostgreSQL) | 18 / 18 |
| Red (3 sedes) | 16 / 16 |

## Sede 1 · Sincelejo (PostgreSQL)

| Sección | Comprobación | Resultado | Detalle |
|---|---|---|---|
| HL7 v2 | ADT^A01 entregado | ✅ | entregado |
| FHIR | Patient y Encounter en HAPI | ✅ | pac-84284236 |
| Base de la sede | Guardado en PostgreSQL y leído por la consulta unificada | ✅ | [1] |
| Idempotencia | Reenvío del mismo HL7 = duplicado | ✅ | duplicado |
| HL7 v2 | ORU^R01 entregado y Observation LOINC en HAPI | ✅ | entregado |
| FHIR | El ORU no borra el diagnóstico del Encounter | ✅ | diagnosis presente |
| CSV legado | Fila CSV entregada con dx_local -> CIE-10 | ✅ | 1 |
| FHIR | Condition I10 del CSV en HAPI | ✅ | pac-86095896 |
| JSON | Registro JSON entregado | ✅ | entregado |
| Admisión | Paciente admitido y publicado en FHIR | ✅ | pac-80415335 |
| Cuentas | Cuenta del portal creada (origen ADMISION, clave temporal) | ✅ | 80415335 |
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
| FHIR | Patient y Encounter en HAPI | ✅ | pac-88120262 |
| Base de la sede | Guardado en MongoDB y leído por la consulta unificada | ✅ | [2] |
| Idempotencia | Reenvío del mismo HL7 = duplicado | ✅ | duplicado |
| HL7 v2 | ORU^R01 entregado y Observation LOINC en HAPI | ✅ | entregado |
| FHIR | El ORU no borra el diagnóstico del Encounter | ✅ | diagnosis presente |
| CSV legado | Fila CSV entregada con dx_local -> CIE-10 | ✅ | 1 |
| FHIR | Condition I10 del CSV en HAPI | ✅ | pac-89398835 |
| JSON | Registro JSON entregado | ✅ | entregado |
| Admisión | Paciente admitido y publicado en FHIR | ✅ | pac-86284202 |
| Cuentas | Cuenta del portal creada (origen ADMISION, clave temporal) | ✅ | 86284202 |
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
| FHIR | Patient y Encounter en HAPI | ✅ | pac-88462097 |
| Base de la sede | Guardado en PostgreSQL y leído por la consulta unificada | ✅ | [3] |
| Idempotencia | Reenvío del mismo HL7 = duplicado | ✅ | duplicado |
| HL7 v2 | ORU^R01 entregado y Observation LOINC en HAPI | ✅ | entregado |
| FHIR | El ORU no borra el diagnóstico del Encounter | ✅ | diagnosis presente |
| CSV legado | Fila CSV entregada con dx_local -> CIE-10 | ✅ | 1 |
| FHIR | Condition I10 del CSV en HAPI | ✅ | pac-85365455 |
| JSON | Registro JSON entregado | ✅ | entregado |
| Admisión | Paciente admitido y publicado en FHIR | ✅ | pac-81147970 |
| Cuentas | Cuenta del portal creada (origen ADMISION, clave temporal) | ✅ | 81147970 |
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
| Auditoría | Cadena SHA-256 íntegra | ✅ | 279 eventos |
| OAuth 2.0 | client_credentials emite token para el bus | ✅ |  |
| OAuth 2.0 | Secreto de cliente incorrecto = 401 invalid_client | ✅ | 401 |
| OAuth 2.0 | Bus sin token = 401 | ✅ | 401 |
| OAuth 2.0 | Token de usuario (audiencia api) rechazado por el bus = 401 | ✅ | 401 |
| OAuth 2.0 | Sistema de la sede 1 no puede escribir en la sede 3 = 403 | ✅ | 403 |
| OAuth 2.0 | Monitor de mensajes sin token = 401 | ✅ | 401 |
| Cifrado en tránsito | API, bus y FHIR por HTTPS verificado con la CA propia | ✅ | https + certs/ca.pem |
| Salud | Bus, HAPI y las 3 sedes UP | ✅ | {"sede_1": {"motor": "postgresql", "estado": "UP"}, "sede_2": {"motor": "mongodb", "estado": "UP"}, "sede_3": {"motor": "postgresql", "estado": "UP"}} |
