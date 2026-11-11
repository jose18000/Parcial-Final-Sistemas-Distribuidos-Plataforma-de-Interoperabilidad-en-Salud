# Tabla de mapeo de campos — HL7 v2 / CSV → PostgreSQL / MongoDB → FHIR R4

**Responsable:** B — Sharit Javier Manjarrez
**Versión:** v2 — 57 campos de la Resolución 866 de 2021

---

## Cómo se lee

Desde la v2 el mapeo no está escrito a mano en el código: vive en **un solo catálogo**,
`traductor/catalogo_57.py`. Cada fila del catálogo dice, para un campo:

- de qué **segmento/campo/componente HL7 v2.5** sale (`PID-11.9` = segmento PID, campo 11,
  componente 9; los separadores son `|` y `^`);
- qué **columna del CSV** legado lo trae (separador `;`);
- en qué **`tabla.columna` de PostgreSQL** queda (sedes 1 y 3, `db/schema.sql`);
- en qué **ruta del documento MongoDB** queda (sede 2, colección `pacientes`, `db/sede2/init-mongo.js`);
- a qué **elemento FHIR R4** corresponde (`fhir/normalizer.py`).

La tabla completa de los 57 campos se genera desde el catálogo y está en
[`docs/mapeo_57_campos.md`](../../mapeo_57_campos.md) (`python -m traductor.generar_mapeo`).
Aquí van 24 filas representativas, incluidas las del ejemplo de la guía de la Fase 1.

Convenciones:
- `[]` en una ruta de MongoDB es un arreglo: `atenciones[]` es cada atención embebida en el
  documento del paciente; dentro de ella, `tecnologias[]` y `diagnosticos[]`.
- Los campos que HL7 v2.5 no trae viajan en **segmentos Z** acordados para el proyecto: `ZPI`
  (datos complementarios del paciente), `ZPV` (atención), `ZRX` (finalidad del medicamento) y
  `ZEG` (egreso). Son una convención local, no un estándar nacional.
- Los diagnósticos 33–39 son filas de `diagnostico` con `rol` = INGRESO, EGRESO o RELACIONADO
  (y `orden` 1–3 para los relacionados). En HL7 el rol sale de `DG1-6` (`A` ingreso, `F` egreso).

---

## Tabla (24 filas representativas)

| # campo | Origen HL7 v2 / CSV | PostgreSQL (tabla.columna) | MongoDB (`pacientes`) | Recurso FHIR R4 | Transformación |
|---|---|---|---|---|---|
| 1 | `PID-3.5` / `tipo_documento` | `usuario.tipo_documento` | `identificacion.tipo` | `Patient.identifier.type` | Dominio con sinónimos (`NI`, `CEDULA`, `HIS`, `MR` → `CC`); si no viene, `CC` |
| 2 | `PID-3.1` / `documento` | `usuario.documento_id` | `identificacion.numero` (y `_id`) | `Patient.identifier.value`, id `pac-<doc>` | Validar solo dígitos, 4 a 15 |
| 4 | `PID-5` / `nombre` | `usuario.nombre_completo` (+ `apellidos`, `nombres`) | `nombre.completo` | `Patient.name` | `Apellido^Nombre` se separa en `family` y `given` |
| 5 | `PID-7` / `nacimiento` | `usuario.fecha_nacimiento` | `nacimiento.fecha` | `Patient.birthDate` | `YYYYMMDD` → `YYYY-MM-DD`; no futura |
| 6 | derivado / `edad` | `usuario.edad` | `nacimiento.edad` | `Patient.extension(edad)` | Se calcula con la fecha de nacimiento y la de ingreso |
| 8 | `PID-8` / `sexo` | `usuario.sexo` (CHECK M/F/O) | `sexo_biologico` | `Patient.gender` | `M`→`male`, `F`→`female`, `O`/`I`→`other`; otro valor se rechaza |
| 14 | `PID-11.9` / `municipio_residencia` | `usuario.municipio_residencia` | `residencia.municipio_dane` | `Patient.address.district` | Código DANE de 5 dígitos |
| 52 | `PID-11.1` / `direccion` | `usuario.direccion_residencia` | `residencia.direccion` | `Patient.address.line` | Texto libre |
| 55 | `NK1-2` / `nombre_responsable` | `usuario.nombre_responsable` | `responsable.nombre` | `Patient.contact.name` | — |
| 16 | `IN1-4.1` / `entidad_salud` | `atencion.entidad_salud` | `atenciones[].aseguradora` | `Encounter.extension(entidad-salud)` | — |
| — | `PV1-19.1` | `atencion.numero_visita` | `atenciones[].numero_visita` | `Encounter.identifier`, id `enc-<visita>` | Llave de la atención en las dos bases |
| 17 | `PV1-44` / `fecha` | `atencion.fecha_ingreso` | `atenciones[].ingreso.fecha` | `Encounter.period.start` | `YYYYMMDDHHMM` → ISO 8601 con zona `-05:00` en FHIR |
| 19 | `PV1-2` / `entorno_atencion` | `atencion.entorno_atencion` | `atenciones[].ingreso.entorno` | `Encounter.class` | `E`→`01` Urgencias, `O`→`02` Consulta externa, `I`→`03` Hospitalización |
| 23 | `ZPV-3` / `triage` | `atencion.clasificacion_triage` (CHECK 1–5) | `atenciones[].triage.clasificacion` | `Encounter.priority` | Romanos `I`–`V` → `1`–`5` |
| — | `PV1-7.1` / `profesional` | `atencion.codigo_profesional` | `atenciones[].profesional.codigo` | `Encounter.participant` → `Practitioner/prac-<código>` | — |
| 34 | `DG1-3.1` con `DG1-6=A` / `dx_local` | `diagnostico.cie10_codigo` con `rol='INGRESO'` | `atenciones[].diagnosticos[rol=INGRESO].cie10` | `Condition.code` (CIE-10), id `cond-<visita>-ing-<cie10>` | HL7: sistema `I10` obligatorio. CSV: texto local → CIE-10 con `ejemplos/05_ref_terminologia.csv`; sin mapeo se rechaza |
| 36 | `DG1-3.1` con `DG1-6=F` | `diagnostico.cie10_codigo` con `rol='EGRESO'` | `atenciones[].diagnosticos[rol=EGRESO].cie10` | `Condition.code` + `Encounter.diagnosis` | — |
| — | `OBX-3.1`, `OBX-5`, `OBX-6.1` | `tecnologia_salud.loinc_codigo`, `.valor`, `.unidad` (`tipo='LABORATORIO'`) | `atenciones[].tecnologias[].loinc`, `.resultado.valor`, `.resultado.unidad` | `Observation.code` (LOINC), `Observation.valueQuantity`, id `obs-<visita>-<loinc>` | Validar LOINC `^[0-9]+-[0-9]+$`; valor decimal |
| 25 | `RXE-2.2` / `medicamento` | `tecnologia_salud.descripcion_medicamento` (`tipo='MEDICAMENTO'`) | `atenciones[].tecnologias[].medicamento` | `MedicationRequest.medicationCodeableConcept.text` | — |
| 27 | `RXR-1.1` / `via_administracion` | `tecnologia_salud.via_administracion` | `atenciones[].tecnologias[].via` | `MedicationRequest.dosageInstruction.route` | `PO`→`01` Oral, `IV`→`02`, `IM`→`03`… |
| 41 | `PV1-36` / `condicion_salida` | `egreso.condicion_salida` | `atenciones[].egreso.condicion` | `Encounter.hospitalization.dischargeDisposition` | `01` vivo, `02` muerto (sinónimos `FALLECIDO`, `20`) |
| 42 | `ZEG-1` / `diagnostico_muerte` | `egreso.diagnostico_muerte` | `atenciones[].egreso.diagnostico_muerte` | `Encounter.extension(diagnostico-muerte)` | Solo si la condición de salida es muerto |
| 43 | derivado de `MSH-4` / `codigo_prestador` | `egreso.codigo_prestador` | `atenciones[].egreso.codigo_prestador` | `Organization.identifier` (`org-sede-N`) | Código REPS sintético de la sede |
| — | `MSH-10` | `mensaje_bus.mensaje_id` | `mensajes_bus._id` | — (no va al Bundle) | Llave de idempotencia; para CSV es `CSV-S<sede>-<hash>` de la fila |

Las extensiones FHIR propias usan la base `https://minsalud.gov.co/fhir/StructureDefinition/`
(por ejemplo `.../edad`, `.../entidad-salud`). Son URLs del proyecto, no perfiles publicados.

---

## Reglas de validación (antes de transformar)

Están en `hsb/validator.py`. Un mensaje que incumple cualquiera se **rechaza** con la lista
completa de motivos y queda registrado en `mensaje_bus` con estado RECHAZADO.

| Campo | Regla | Motivo que devuelve el bus |
|---|---|---|
| Documento (2) | No vacío, solo dígitos, 4 a 15 | `documento no puede ser vacío` / `documento no numérico` / `documento fuera de rango: tiene N dígitos…` |
| Nombre (4) | No vacío | `nombre no puede ser vacío` |
| Sexo (8) | `M`, `F` u `O` (tras aplicar sinónimos) | `sexo no válido ('X'): debe ser M, F u O` |
| Sede | 1, 2 o 3 (de `MSH-4` o de `?sede=N`) | `sede no válida o desconocida (...)` |
| Fecha de nacimiento (5) | Válida y no futura | `fecha de nacimiento no válida` / `en el futuro` |
| Fecha de ingreso (17) | Válida si viene | `fecha de ingreso no válida` |
| Diagnóstico (34, 36–39) | CIE-10 `^[A-Z][0-9]{2}(\.[0-9]{1,4})?$` y no un código local (`L`) sin mapear | `diagnóstico sin mapeo a CIE-10` |
| Laboratorio | LOINC `^[0-9]+-[0-9]+$` | `código LOINC inválido: '...'` |
| Medicamento (25) | Con descripción si la tecnología es un medicamento | `medicamento sin descripción (campo 25)` |

Los valores **opcionales** que no pertenecen a su dominio no rechazan el mensaje: el traductor los
omite y el bus devuelve una **advertencia**.

---

## Verificación con los archivos de ejemplo

| Archivo | Campo | Valor | Resultado medido |
|---|---|---|---|
| `01_adt_a01_valido_sede2.hl7` | `PID-3`, `PID-8`, `DG1-3` | `1007`, `F`, `J45.9^Asma^I10` | Entregado en la sede 2 (MongoDB): `Patient/pac-1007`, Encounter y Condition J45.9 |
| `02_oru_r01_laboratorio_sede1.hl7` | `OBX-3`, `OBX-5`, `OBX-6` | `718-7`, `13.8`, `g/dL` | Entregado en la sede 1 (PostgreSQL): Observation 718-7 = 13.8 g/dL para 1001 |
| `03_adt_a01_invalido.hl7` | `PID-3`, `PID-8`, `DG1-3` | `ABC123`, `X`, `DIARREA^Diarrea^L` | Rechazado con 3 motivos: documento no numérico, sexo no válido, diagnóstico sin mapeo a CIE-10 |
| `04_sede3_legado.csv` fila 4 | `dx_local` | `DOLOR MISTERIOSO` | Rechazado: no está en `05_ref_terminologia.csv` |
| `04_sede3_legado.csv` fila 5 | `documento` | `12` | Rechazado: 2 dígitos |
| `04_sede3_legado.csv` filas 1–3 | — | 1008, 1009, 1010 | Entregados en la sede 3 (PostgreSQL) |
| `tests/datos/06_adt_a03_57_campos_sede1.hl7` | todos los segmentos, incluidos `ZPI`, `ZPV`, `ZRX`, `ZEG` | paciente 1020 | 11 recursos FHIR, 56 de 57 campos (falta solo el 42 porque el paciente sale vivo) |

> **Decisión sobre `DG1-3` con sistema `L` en HL7:** aunque `DIARREA` existe en la tabla de
> terminología, un mensaje HL7 debe traer el código CIE-10 con sistema `I10`. El mapeo de texto
> local a CIE-10 solo se aplica al CSV legado, que no tiene sistema de codificación.
