# tests/

Pruebas automatizadas (36) con `pytest`. No necesitan los contenedores.

| Suite | Pruebas | Qué cubre |
|---|---|---|
| `fase2/test_normalizer.py` | 8 | Recursos FHIR, ids deterministas, referencias internas, caso inválido |
| `fase2/test_traductor_57.py` | 10 | Catálogo de 57 campos, esquema SQL frente al catálogo, ida y vuelta MongoDB, CSV, JSON por número de campo |
| `fase3/test_hsb_integration.py` | 10 | Los 4 ejemplos oficiales, idempotencia, reintento, muerto y reencolar, sede caída |
| `fase4/test_security_resilience.py` | 8 | Permisos por rol (403 y auditoría), cadena de hash y alteración, resiliencia |

`datos/06_adt_a03_57_campos_sede1.hl7` — mensaje HL7 con los 57 campos (incluye segmentos `ZPI`,
`ZPV`, `ZRX`, `ZEG`); produce 11 recursos FHIR y cubre 56 de 57 campos (falta el 42 porque el
paciente sale vivo).

Ejecutar:
```bash
pip install -r hsb/requirements.txt -r app/requirements.txt pytest
python -m pytest tests/ -v
```
