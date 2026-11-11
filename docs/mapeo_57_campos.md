# Mapeo de los 57 campos de la historia clínica (traductor universal)

> Generado automáticamente desde `traductor/catalogo_57.py` con `python -m traductor.generar_mapeo`.
> No editar a mano.

Referencia: Resolución 866 de 2021 (MinSalud) · `57_CAMPOS_HC.md` del repositorio de referencia.

## Motores por sede

| Sede | Ciudad | Motor | Código prestador (REPS sintético) |
|---|---|---|---|
| 1 | Sincelejo | postgresql | 700010000101 |
| 2 | Cartagena | mongodb | 130010000202 |
| 3 | Corozal | postgresql | 702150000303 |

**57 campos**, 23 obligatorios (✅).

Los campos que HL7 v2.5 no transporta viajan en segmentos Z de uso nacional: `ZPI` (datos complementarios del paciente), `ZPV` (atención), `ZRX` (finalidad del medicamento) y `ZEG` (egreso). Los diagnósticos 33-39 se guardan como filas de `diagnostico` con un rol (INGRESO, EGRESO, RELACIONADO) y el traductor los reconstruye.


## Identificación del usuario

| # | Campo | Oblig. | HL7 v2 | CSV | PostgreSQL (sedes 1 y 3) | MongoDB (sede 2) | FHIR R4 |
|---|---|---|---|---|---|---|---|
| 1 | Tipo de documento de identidad | ✅ | `PID-3.5` | `tipo_documento` | `usuario.tipo_documento` | `pacientes.identificacion.tipo` | `Patient.identifier.type` |
| 2 | Número de documento de identidad | ✅ | `PID-3.1` | `documento` | `usuario.documento_id` | `pacientes.identificacion.numero` | `Patient.identifier.value` |
| 3 | País de nacionalidad | ✅ | `PID-28.1` | `pais_nacionalidad` | `usuario.pais_nacionalidad` | `pacientes.nacionalidad` | `Patient.extension(nacionalidad)` |
| 4 | Nombre completo | ✅ | `PID-5` | `nombre` | `usuario.nombre_completo` | `pacientes.nombre.completo` | `Patient.name` |
| 5 | Fecha de nacimiento | ✅ | `PID-7` | `nacimiento` | `usuario.fecha_nacimiento` | `pacientes.nacimiento.fecha` | `Patient.birthDate` |
| 6 | Edad *(derivado)* | ✅ | `—` | `edad` | `usuario.edad` | `pacientes.nacimiento.edad` | `Patient.extension(edad)` |
| 7 | Unidad de medida de la edad *(derivado)* | ✅ | `—` | `unidad_edad` | `usuario.unidad_edad` | `pacientes.nacimiento.unidad_edad` | `Patient.extension(edad).unit` |
| 8 | Sexo | ✅ | `PID-8` | `sexo` | `usuario.sexo` | `pacientes.sexo_biologico` | `Patient.gender` |
| 9 | Género |  | `ZPI-1` | `genero` | `usuario.genero` | `pacientes.identidad_genero` | `Patient.extension(genero)` |
| 10 | Ocupación |  | `ZPI-2` | `ocupacion` | `usuario.ocupacion` | `pacientes.ocupacion` | `Patient.extension(ocupacion)` |
| 11 | Voluntad anticipada |  | `ZPI-3` | `voluntad_anticipada` | `usuario.voluntad_anticipada` | `pacientes.voluntad_anticipada` | `Patient.extension(voluntad-anticipada)` |
| 12 | Categoría de discapacidad |  | `ZPI-4` | `categoria_discapacidad` | `usuario.categoria_discapacidad` | `pacientes.discapacidad` | `Patient.extension(discapacidad)` |
| 13 | País de residencia | ✅ | `PID-11.6` | `pais_residencia` | `usuario.pais_residencia` | `pacientes.residencia.pais` | `Patient.address.country` |
| 14 | Municipio de residencia (DANE) | ✅ | `PID-11.9` | `municipio_residencia` | `usuario.municipio_residencia` | `pacientes.residencia.municipio_dane` | `Patient.address.district` |
| 15 | Etnia |  | `PID-22.1` | `etnia` | `usuario.etnia` | `pacientes.pertenencia_etnica` | `Patient.extension(etnia)` |

## Datos de la atención

| # | Campo | Oblig. | HL7 v2 | CSV | PostgreSQL (sedes 1 y 3) | MongoDB (sede 2) | FHIR R4 |
|---|---|---|---|---|---|---|---|
| 16 | Entidad de salud (EPS) | ✅ | `IN1-4.1` | `entidad_salud` | `atencion.entidad_salud` | `pacientes.atenciones[].aseguradora` | `Encounter.extension(entidad-salud)` |
| 17 | Fecha y hora de ingreso | ✅ | `PV1-44` | `fecha` | `atencion.fecha_ingreso` | `pacientes.atenciones[].ingreso.fecha` | `Encounter.period.start` |
| 18 | Modalidad de entrega del servicio | ✅ | `ZPV-1` | `modalidad_entrega` | `atencion.modalidad_entrega` | `pacientes.atenciones[].ingreso.modalidad` | `Encounter.extension(modalidad)` |
| 19 | Entorno de atención | ✅ | `PV1-2` | `entorno_atencion` | `atencion.entorno_atencion` | `pacientes.atenciones[].ingreso.entorno` | `Encounter.class` |
| 20 | Vía de ingreso | ✅ | `PV1-14` | `via_ingreso` | `atencion.via_ingreso` | `pacientes.atenciones[].ingreso.via` | `Encounter.hospitalization.admitSource` |
| 21 | Causa de la atención | ✅ | `PV2-3.2` | `causa_atencion` | `atencion.causa_atencion` | `pacientes.atenciones[].ingreso.causa` | `Encounter.reasonCode.text` |
| 22 | Fecha y hora del triage |  | `ZPV-2` | `fecha_triage` | `atencion.fecha_triage` | `pacientes.atenciones[].triage.fecha` | `Encounter.extension(fecha-triage)` |
| 23 | Clasificación del triage |  | `ZPV-3` | `triage` | `atencion.clasificacion_triage` | `pacientes.atenciones[].triage.clasificacion` | `Encounter.priority` |
| 24 | Comunidad étnica |  | `ZPI-6` | `comunidad_etnica` | `atencion.comunidad_etnica` | `pacientes.atenciones[].comunidad_etnica` | `Encounter.extension(comunidad-etnica)` |

## Tecnologías en salud

| # | Campo | Oblig. | HL7 v2 | CSV | PostgreSQL (sedes 1 y 3) | MongoDB (sede 2) | FHIR R4 |
|---|---|---|---|---|---|---|---|
| 25 | Descripción del medicamento |  | `RXE-2.2` | `medicamento` | `tecnologia_salud.descripcion_medicamento` | `pacientes.atenciones[].tecnologias[].medicamento` | `MedicationRequest.medicationCodeableConcept.text` |
| 26 | Dosis |  | `RXE-3 + RXE-5` | `dosis` | `tecnologia_salud.dosis` | `pacientes.atenciones[].tecnologias[].dosis` | `MedicationRequest.dosageInstruction.text` |
| 27 | Vía de administración |  | `RXR-1.1` | `via_administracion` | `tecnologia_salud.via_administracion` | `pacientes.atenciones[].tecnologias[].via` | `MedicationRequest.dosageInstruction.route` |
| 28 | Frecuencia |  | `RXE-1.2` | `frecuencia` | `tecnologia_salud.frecuencia` | `pacientes.atenciones[].tecnologias[].frecuencia` | `MedicationRequest.dosageInstruction.timing.code.text` |
| 29 | Días de tratamiento |  | `RXE-1.3` | `dias_tratamiento` | `tecnologia_salud.dias_tratamiento` | `pacientes.atenciones[].tecnologias[].dias_tratamiento` | `MedicationRequest.dispenseRequest.expectedSupplyDuration` |
| 30 | Unidades aplicadas |  | `RXE-10` | `unidades_aplicadas` | `tecnologia_salud.unidades_aplicadas` | `pacientes.atenciones[].tecnologias[].unidades` | `MedicationRequest.dispenseRequest.quantity` |
| 31 | Identificación del personal de salud |  | `ORC-12.1` | `id_personal_salud` | `tecnologia_salud.id_personal_salud` | `pacientes.atenciones[].tecnologias[].prescriptor` | `MedicationRequest.requester` |
| 32 | Finalidad de la tecnología |  | `ZRX-1` | `finalidad_tecnologia` | `tecnologia_salud.finalidad_tecnologia` | `pacientes.atenciones[].tecnologias[].finalidad` | `MedicationRequest.extension(finalidad)` |
| 33 | Tipo de diagnóstico de ingreso |  | `DG1-15 (DG1-6=A)` | `tipo_dx` | `diagnostico.tipo_diagnostico [rol=INGRESO]` | `pacientes.atenciones[].diagnosticos[rol=INGRESO].tipo` | `Encounter.diagnosis(AD).rank` |
| 34 | Diagnóstico de ingreso (CIE-10) |  | `DG1-3.1 (DG1-6=A)` | `dx_local → CIE-10` | `diagnostico.cie10_codigo [rol=INGRESO]` | `pacientes.atenciones[].diagnosticos[rol=INGRESO].cie10` | `Condition.code + Encounter.diagnosis(AD)` |
| 35 | Tipo de diagnóstico de egreso |  | `DG1-15 (DG1-6=F)` | `—` | `diagnostico.tipo_diagnostico [rol=EGRESO]` | `pacientes.atenciones[].diagnosticos[rol=EGRESO].tipo` | `Encounter.diagnosis(DD).rank` |

## Diagnósticos

| # | Campo | Oblig. | HL7 v2 | CSV | PostgreSQL (sedes 1 y 3) | MongoDB (sede 2) | FHIR R4 |
|---|---|---|---|---|---|---|---|
| 36 | Diagnóstico de egreso (CIE-10) | ✅ | `DG1-3.1 (DG1-6=F)` | `—` | `diagnostico.cie10_codigo [rol=EGRESO]` | `pacientes.atenciones[].diagnosticos[rol=EGRESO].cie10` | `Condition.code + Encounter.diagnosis(DD)` |
| 37 | Diagnóstico relacionado 1 |  | `DG1-3.1 (DG1-15=2)` | `—` | `diagnostico.cie10_codigo [rol=RELACIONADO, orden=1]` | `pacientes.atenciones[].diagnosticos[rol=RELACIONADO][0].cie10` | `Condition.code` |
| 38 | Diagnóstico relacionado 2 |  | `DG1-3.1 (DG1-15=3)` | `—` | `diagnostico.cie10_codigo [rol=RELACIONADO, orden=2]` | `pacientes.atenciones[].diagnosticos[rol=RELACIONADO][1].cie10` | `Condition.code` |
| 39 | Diagnóstico relacionado 3 |  | `DG1-3.1 (DG1-15=4)` | `—` | `diagnostico.cie10_codigo [rol=RELACIONADO, orden=3]` | `pacientes.atenciones[].diagnosticos[rol=RELACIONADO][2].cie10` | `Condition.code` |

## Datos de egreso

| # | Campo | Oblig. | HL7 v2 | CSV | PostgreSQL (sedes 1 y 3) | MongoDB (sede 2) | FHIR R4 |
|---|---|---|---|---|---|---|---|
| 40 | Fecha y hora de salida | ✅ | `PV1-45` | `fecha_salida` | `egreso.fecha_salida` | `pacientes.atenciones[].egreso.fecha` | `Encounter.period.end` |
| 41 | Condición de salida | ✅ | `PV1-36` | `condicion_salida` | `egreso.condicion_salida` | `pacientes.atenciones[].egreso.condicion` | `Encounter.hospitalization.dischargeDisposition` |
| 42 | Diagnóstico de muerte (CIE-10) |  | `ZEG-1` | `diagnostico_muerte` | `egreso.diagnostico_muerte` | `pacientes.atenciones[].egreso.diagnostico_muerte` | `Encounter.extension(diagnostico-muerte)` |
| 43 | Código del prestador *(derivado)* | ✅ | `MSH-4 → REPS` | `codigo_prestador` | `egreso.codigo_prestador` | `pacientes.atenciones[].egreso.codigo_prestador` | `Organization.identifier` |
| 44 | Tipo de incapacidad |  | `ZEG-2` | `tipo_incapacidad` | `egreso.tipo_incapacidad` | `pacientes.atenciones[].egreso.incapacidad.tipo` | `Encounter.extension(incapacidad)` |
| 45 | Días de incapacidad |  | `ZEG-3` | `dias_incapacidad` | `egreso.dias_incapacidad` | `pacientes.atenciones[].egreso.incapacidad.dias` | `Encounter.extension(incapacidad)` |
| 46 | Días de licencia de maternidad |  | `ZEG-4` | `dias_lic_maternidad` | `egreso.dias_lic_maternidad` | `pacientes.atenciones[].egreso.licencia_maternidad_dias` | `Encounter.extension(licencia-maternidad)` |
| 47 | Alergias |  | `AL1-3.2` | `alergias` | `egreso.alergias` | `pacientes.atenciones[].egreso.alergias` | `AllergyIntolerance.code.text` |
| 48 | Antecedentes familiares |  | `ZEG-5` | `antecedentes_familiares` | `egreso.antecedentes_familiares` | `pacientes.atenciones[].egreso.antecedentes_familiares` | `Encounter.extension(antecedentes-familiares)` |
| 49 | Riesgos ocupacionales |  | `ZEG-6` | `riesgos_ocupacionales` | `egreso.riesgos_ocupacionales` | `pacientes.atenciones[].egreso.riesgos_ocupacionales` | `Encounter.extension(riesgos-ocupacionales)` |
| 50 | Responsable del egreso | ✅ | `ZEG-7` | `responsable_egreso` | `egreso.responsable_egreso` | `pacientes.atenciones[].egreso.responsable` | `Encounter.participant(DIS)` |
| 51 | Zona de residencia | ✅ | `ZPI-7` | `zona_residencia` | `usuario.zona_residencia` | `pacientes.residencia.zona` | `Patient.address.extension(zona)` |
| 52 | Dirección de residencia | ✅ | `PID-11.1` | `direccion` | `usuario.direccion_residencia` | `pacientes.residencia.direccion` | `Patient.address.line` |
| 53 | Teléfono |  | `PID-13.1` | `telefono` | `usuario.telefono` | `pacientes.contacto.telefono` | `Patient.telecom(phone)` |
| 54 | Correo electrónico |  | `PID-13.4` | `correo` | `usuario.correo_electronico` | `pacientes.contacto.correo` | `Patient.telecom(email)` |
| 55 | Nombre del responsable |  | `NK1-2` | `nombre_responsable` | `usuario.nombre_responsable` | `pacientes.responsable.nombre` | `Patient.contact.name` |
| 56 | Parentesco del responsable |  | `NK1-3.1` | `parentesco_responsable` | `usuario.parentesco_responsable` | `pacientes.responsable.parentesco` | `Patient.contact.relationship` |
| 57 | Teléfono del responsable |  | `NK1-5.1` | `telefono_responsable` | `usuario.telefono_responsable` | `pacientes.responsable.telefono` | `Patient.contact.telecom` |

## Dominios (valores permitidos y sinónimos que traduce)

- **tipo_documento**: `CC` Cédula de ciudadanía, `TI` Tarjeta de identidad, `CE` Cédula de extranjería, `PA` Pasaporte, `RC` Registro civil, `MS` Menor sin identificación, `AS` Adulto sin identificación. Sinónimos: `NI`→`CC`, `PPN`→`PA`, `CEDULA`→`CC`, `HIS`→`CC`, `MR`→`CC`.
- **sexo**: `M` Masculino, `F` Femenino, `O` Otro / indeterminado. Sinónimos: `I`→`O`, `INDETERMINADO`→`O`, `OTRO`→`O`, `MASCULINO`→`M`, `HOMBRE`→`M`, `FEMENINO`→`F`, `MUJER`→`F`, `MALE`→`M`, `FEMALE`→`F`, `OTHER`→`O`.
- **genero**: `01` Masculino, `02` Femenino, `03` Transgénero, `04` No binario, `05` Otro. Sinónimos: `M`→`01`, `F`→`02`, `O`→`05`, `TRANS`→`03`.
- **unidad_edad**: `1` Años, `2` Meses, `3` Días. Sinónimos: `ANOS`→`1`, `A`→`1`, `MESES`→`2`, `DIAS`→`3`, `D`→`3`.
- **categoria_discapacidad**: `01` Física, `02` Visual, `03` Auditiva, `04` Intelectual, `05` Psicosocial (mental), `06` Sordoceguera, `07` Múltiple, `08` Sin discapacidad. Sinónimos: `MENTAL`→`05`, `SENSORIAL`→`02`, `NINGUNA`→`08`, `NO`→`08`.
- **etnia**: `01` Indígena, `02` ROM (gitano), `03` Raizal, `04` Palenquero, `05` Negro, mulato, afrocolombiano, `06` Ninguna de las anteriores. Sinónimos: `INDIGENA`→`01`, `GITANO`→`02`, `AFRO`→`05`, `AFROCOLOMBIANO`→`05`, `NEGRO`→`05`, `OTRO`→`06`, `NINGUNA`→`06`.
- **modalidad_entrega**: `01` Intramural, `02` Extramural, `03` Telemedicina interactiva, `04` Telemedicina no interactiva, `05` Telexperticia, `06` Telemonitoreo. Sinónimos: —.
- **entorno_atencion**: `01` Urgencias, `02` Consulta externa, `03` Hospitalización, `04` Cirugía, `05` Apoyo diagnóstico, `06` Apoyo terapéutico. Sinónimos: `E`→`01`, `O`→`02`, `I`→`03`, `EMER`→`01`, `AMB`→`02`, `IMP`→`03`.
- **via_ingreso**: `01` Espontánea, `02` Remitido, `03` Contrarremitido. Sinónimos: `CONTRAREMITIDO`→`03`.
- **clasificacion_triage**: `1` I - Resucitación (rojo), `2` II - Emergencia (naranja), `3` III - Urgente (amarillo), `4` IV - Menos urgente (verde), `5` V - No urgente (azul). Sinónimos: `I`→`1`, `II`→`2`, `III`→`3`, `IV`→`4`, `V`→`5`.
- **via_administracion**: `01` Oral, `02` Intravenosa, `03` Intramuscular, `04` Subcutánea, `05` Tópica, `06` Inhalatoria, `07` Rectal, `08` Oftálmica, `09` Ótica, `10` Nasal. Sinónimos: `PO`→`01`, `IV`→`02`, `IM`→`03`, `SC`→`04`, `TP`→`05`, `IH`→`06`, `PR`→`07`, `OP`→`08`, `OT`→`09`, `NS`→`10`.
- **finalidad_tecnologia**: `01` Terapéutica, `02` Diagnóstica, `03` Paliativa, `04` Preventiva, `05` Rehabilitación. Sinónimos: —.
- **tipo_diagnostico**: `01` Principal, `02` Relacionado, `03` Complicación. Sinónimos: `PRINCIPAL`→`01`, `RELACIONADO`→`02`, `1`→`01`, `2`→`02`, `3`→`02`.
- **condicion_salida**: `01` Vivo, `02` Muerto. Sinónimos: `ESTABLE`→`01`, `MEJORADO`→`01`, `20`→`02`, `FALLECIDO`→`02`, `01`→`01`, `02`→`01`, `03`→`01`, `04`→`01`, `07`→`01`.
- **tipo_incapacidad**: `01` Temporal, `02` Permanente parcial, `03` Permanente total. Sinónimos: `PERMANENTE`→`02`.
- **zona_residencia**: `01` Urbana, `02` Rural. Sinónimos: `U`→`01`, `R`→`02`.
- **parentesco**: `01` Padre / madre, `02` Hijo / hija, `03` Esposo / esposa, `04` Hermano / hermana, `05` Abuelo / abuela, `06` Tío / tía, `07` Otro. Sinónimos: `PAR`→`01`, `MTH`→`01`, `FTH`→`01`, `MADRE`→`01`, `PADRE`→`01`, `CHD`→`02`, `HIJO`→`02`, `HIJA`→`02`, `SPO`→`03`, `ESPOSO`→`03`, `ESPOSA`→`03`, `SIB`→`04`, `GRP`→`05`, `OTH`→`07`.
