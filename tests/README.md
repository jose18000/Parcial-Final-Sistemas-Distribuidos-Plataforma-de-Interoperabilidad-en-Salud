# tests/

Pruebas unitarias e integración.

Organización por fase:
- `tests/fase2/` — pruebas del normalizador FHIR (≥5 casos, incluir uno inválido)
- `tests/fase3/` — pruebas de integración del HSB (4 ejemplos con resultado esperado)
- `tests/fase4/` — pruebas de acceso por rol (permitido y denegado por cada rol)

Ejecutar:
```bash
pytest tests/ -v --tb=short
```

