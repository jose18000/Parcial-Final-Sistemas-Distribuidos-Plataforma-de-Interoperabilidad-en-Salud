# fhir/

Normalizador del registro canónico (57 campos, `traductor/`) a Bundle FHIR R4.

- `normalizer.py`
  - `bundle_desde_registro(reg)` — una atención canónica → Bundle (lo usa el HSB)
  - `construir_bundle(usuario, atenciones)` — historia unificada → Bundle (lo usa la API para la descarga)

Bundle de tipo `transaction` con `PUT`: reenviar el mismo contenido no duplica nada. Toda
referencia apunta a un recurso dentro del mismo Bundle.

Ids deterministas:
- Organization: `org-sede-{n}` · Practitioner: `prac-{código}`
- Patient: `pac-{documento_id}`
- Encounter: `enc-{numero_visita}`
- Condition: `cond-{numero_visita}-{rol}-{cie10}` (rol `ing`, `egr`, `rel`)
- Observation: `obs-{numero_visita}-{loinc}`
- MedicationRequest: `med-{numero_visita}-…`
- AllergyIntolerance: `alg-{documento_id}`

Terminologías: CIE-10 en Condition, LOINC en Observation. Extensiones propias bajo
`https://minsalud.gov.co/fhir/StructureDefinition/` (URLs del proyecto, no un perfil publicado).
