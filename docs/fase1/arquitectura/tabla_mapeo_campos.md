# Tabla de Mapeo de Campos — HL7 v2 / CSV → BD → FHIR R4

**Responsable:** B — Sharit Javier Manjarrez
**Fuente de los ejemplos:** archivos `ejemplos/01..04`

---

## Notas de lectura

- **Origen HL7:** `SEG-N` = segmento, posición del campo (base 1). Ej: `PID-3` = tercer campo del segmento PID.
- **Componente HL7:** `SEG-N[k]` = k-ésimo componente dentro del campo (separador `^`). Ej: `PID-5[1]` = apellido.
- **Origen CSV:** nombre de columna en `04_sede3_legado.csv`.
- **Tabla BD:** nombre de la tabla en el esquema de cada nodo PostgreSQL (Fase 2).
- **Campo BD:** nombre de columna en esa tabla.
- **Recurso FHIR:** notación `Recurso.ruta.atributo` según FHIR R4.
- **Transformación:** lógica adicional necesaria (mapeo, formato, constante).

---

## Tabla (22 campos mapeados)

| # | Origen HL7 / CSV | Tabla BD | Campo BD | Recurso FHIR | Transformación |
|---|-----------------|----------|----------|-------------|----------------|
| 1 | `PID-3` / `documento` | `usuario` | `documento_id` | `Patient.identifier[0].value` | Validar solo dígitos, 4–15 chars |
| 2 | `PID-5[1]` / `nombre` (apellido) | `usuario` | `nombre_completo` | `Patient.name[0].family` | Separar `Apellido^Nombre` → family + given |
| 3 | `PID-5[2]` / `nombre` (nombre) | `usuario` | `nombre_completo` | `Patient.name[0].given[0]` | Componente 2 del campo PID-5 |
| 4 | `PID-7` / `nacimiento` | `usuario` | `fecha_nacimiento` | `Patient.birthDate` | HL7: `YYYYMMDD` → ISO `YYYY-MM-DD`; CSV ya viene en ISO |
| 5 | `PID-8` / `sexo` | `usuario` | `sexo` | `Patient.gender` | `M`→`male`, `F`→`female`, `O`→`other`; otros: rechazar |
| 6 | `PID-11` | `usuario` | `direccion` | `Patient.address[0].text` | Campo libre |
| 7 | `MSH-4` / `sede` (columna implícita `?sede=N`) | `atencion` | `sede_id` | `Encounter.serviceProvider.reference` | `SEDE1`→`1`, `SEDE2`→`2`, `SEDE3`→`3`; validar rango 1-3 |
| 8 | `PV1-2` | `atencion` | `clase_atencion` | `Encounter.class.code` | `E`→`EMER`, `O`→`AMB`, `I`→`IMP` (HL7 v3 ActCode) |
| 9 | `PV1-7[1]` / `profesional` | `profesional_salud` | `codigo` | `Encounter.participant[0].individual.reference` | `Practitioner/MED-01` |
| 10 | `PV1-7[2]` / `profesional` (apellido) | `profesional_salud` | `nombre_completo` | `Practitioner.name.family` | Componente 2 de PV1-7 |
| 11 | `PV1-19` | `atencion` | `numero_visita` | `Encounter.identifier[0].value` | Clave de idempotencia del Encounter |
| 12 | `PV1-44` / `fecha` | `atencion` | `fecha_ingreso` | `Encounter.period.start` | HL7: `YYYYMMDDHHmm` → ISO 8601; CSV: columna `fecha` |
| 13 | `PV1-45` | `atencion` | `fecha_egreso` | `Encounter.period.end` | Puede ser nulo (atención abierta) |
| 14 | `DG1-3[1]` | `diagnostico` | `cie10_codigo` | `Condition.code.coding[0].code` | Si sistema=`I10`: usar tal cual; si sistema=`L`: rechazar (HL7); CSV: mapear via `05_ref_terminologia.csv` |
| 15 | `DG1-3[2]` / `dx_local` (descripción) | `diagnostico` | `descripcion_cie10` | `Condition.code.coding[0].display` | Texto descriptivo; para CSV viene de la tabla de terminología |
| 16 | `DG1-5` | `diagnostico` | `fecha_diagnostico` | `Condition.onsetDateTime` | Mismo formato que PID-7 |
| 17 | `OBX-3[1]` | `tecnologia_salud` | `loinc_codigo` | `Observation.code.coding[0].code` | Validar que sea código LOINC numérico-guion |
| 18 | `OBX-3[2]` | `tecnologia_salud` | `descripcion_loinc` | `Observation.code.coding[0].display` | Texto libre del segmento |
| 19 | `OBX-5` | `tecnologia_salud` | `valor` | `Observation.valueQuantity.value` | Parsear como número decimal |
| 20 | `OBX-6` | `tecnologia_salud` | `unidad` | `Observation.valueQuantity.unit` | Texto libre; p. ej. `g/dL` |
| 21 | `triage` (CSV) | `atencion` | `triage` | `Encounter.priority.coding[0].code` | Escala 1–5; nulo → no se mapea al Bundle |
| 22 | `MSH-10` | `mensaje_bus` | `mensaje_id` | — (clave de idempotencia del bus, no va al Bundle) | Almacenada como hash SHA-256 del contenido completo |

---

## Reglas de validación derivadas de la tabla

| Campo | Regla | Acción si falla |
|-------|-------|-----------------|
| `documento_id` | Solo dígitos, longitud 4–15 | RECHAZAR · motivo: "documento no numérico" ó "longitud inválida" |
| `nombre_completo` | No vacío, mínimo 2 chars | RECHAZAR · motivo: "nombre vacío" |
| `sexo` | Exactamente `M`, `F` o `O` | RECHAZAR · motivo: "sexo no válido" |
| `sede_id` | Entero 1, 2 ó 3 | RECHAZAR · motivo: "sede desconocida" |
| `fecha_nacimiento` / `fecha_ingreso` | Fecha válida, no futura | RECHAZAR · motivo: "fecha inválida" |
| `cie10_codigo` (HL7 sistema `I10`) | Formato `[A-Z][0-9]{2}(\.[0-9]{1,4})?` | RECHAZAR · motivo: "CIE-10 con formato incorrecto" |
| `cie10_codigo` (HL7 sistema `L` / CSV) | `dx_local` debe existir en `05_ref_terminologia.csv` | RECHAZAR · motivo: "diagnóstico sin mapeo a CIE-10" |
| `loinc_codigo` | Formato `[0-9]+-[0-9]+` | RECHAZAR · motivo: "LOINC con formato incorrecto" |

---

## Verificación con los archivos de ejemplo

| Archivo | Campo crítico | Valor en archivo | Resultado esperado |
|---------|--------------|------------------|--------------------|
| `01` | PID-3 | `1007` | Válido → `Patient.identifier = 1007` |
| `01` | PID-8 | `F` | Válido → `Patient.gender = female` |
| `01` | DG1-3 | `J45.9^Asma^I10` | Sistema I10 → código válido → `Condition.code = J45.9` |
| `02` | OBX-3 | `718-7^Hemoglobina^LN` | LOINC válido → `Observation.code = 718-7` |
| `02` | OBX-5 | `13.8` | `Observation.valueQuantity.value = 13.8` |
| `03` | PID-3 | `ABC123` | **RECHAZAR** · no numérico |
| `03` | PID-8 | `X` | **RECHAZAR** · sexo inválido |
| `03` | DG1-3 | `DIARREA^Diarrea^L` | Sistema `L` en HL7 → búsqueda en tabla de mapeo; `DIARREA` SÍ existe → el tercer error es que el sistema declarado `L` no provee un código CIE-10 en posición [1]; el HSB exige que HL7 con sistema `I10` lleve el código. Con `L` se fuerza el mapeo pero el código resultante `A09` no viene en el campo [1], lo que viola el contrato del segmento DG1. **Decisión de diseño:** HL7 con sistema `L` siempre se rechaza ("diagnóstico en sistema local no permitido por HL7; use CSV para datos legados"). |
| `04` fila 4 | documento | `12` | **RECHAZAR** · longitud 2 < mínimo 4 |
| `04` fila 5 | dx_local | `DOLOR MISTERIOSO` | **RECHAZAR** · no existe en `05_ref_terminologia.csv` |

