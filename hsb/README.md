# hsb/

Health Service Bus (contenedor `hsb_bus`, puerto 8001).

Entradas:
- `POST /hsb/hl7` — HL7 v2 en texto plano (ADT^A01, ADT^A03, ORU^R01, RDE^O11)
- `POST /hsb/csv?sede=N` — CSV legado con separador `;` de la sede N
- `POST /hsb/json?sede=N` — registro JSON (lo usan las vistas de admisión y médico)

Operación:
- `GET /hsb/mensajes` — estado de los mensajes de las 3 sedes (monitor del admisionista)
- `POST /hsb/reencolar/{mensaje_id}` — saca un mensaje de la cola de muertos
- `GET /hsb/catalogo` — los 57 campos y su mapeo HL7 / CSV / PostgreSQL / MongoDB / FHIR
- `GET /health` — estado del bus, de HAPI y de las 3 sedes (con su motor)
- `GET /metrics` — contadores por estado, latencia media, % fallidos, duplicados, reintentos

Flujo (`ingesta.py`): traductor universal (`traductor/`) → idempotencia (`MSH-10` o hash, en
`mensaje_bus` de la sede) → validación (`validator.py`) → Bundle FHIR (`fhir/normalizer.py`) →
entrega HAPI primero y sede después (`queue_manager.py`).

Reintentos en segundo plano: espera `HSB_RETRY_BASE_SECONDS × 2^(n-1)` (2, 4, 8, 16, 32, 64 s por
defecto), hasta `HSB_MAX_RETRIES` = 7 intentos; luego MUERTO. Los errores de datos (restricción
violada en la sede, HTTP 4xx de HAPI) van directo a MUERTO. Al arrancar, el bus recupera los
mensajes que quedaron en REINTENTANDO o TRANSFORMADO.

Estados: RECIBIDO, VALIDADO, TRANSFORMADO, ENTREGADO, RECHAZADO, REINTENTANDO, MUERTO
(ver `docs/fase1/diagramas/04_estados_mensaje.md`).
