# fhir/

Normalizador FHIR y scripts de validación — Fase 2-3.

Contenido previsto:
- `fhir/normalizer.py` — funciones: `hl7_to_bundle()`, `csv_to_bundle()`, `validate_bundle()`
- `fhir/mappings.py` — constantes: mapeo sexo, clase atención, sistema de codificación
- `fhir/profiles/` — perfiles FHIR R4 usados (si se definen perfiles propios)

IDs deterministas:
- Patient: `pac-{documento_id}`
- Encounter: `enc-{numero_visita}`
- Condition: `cond-{numero_visita}-{cie10}`
- Observation: `obs-{numero_visita}-{loinc}`

