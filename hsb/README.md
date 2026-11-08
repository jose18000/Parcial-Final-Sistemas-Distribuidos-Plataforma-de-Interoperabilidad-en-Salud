# hsb/

Health Service Bus — implementación en Fase 3.

Endpoints a implementar:
- `POST /hsb/hl7` — recibe mensajes HL7 v2 (ADT^A01, ORU^R01) en texto plano
- `POST /hsb/csv?sede=N` — recibe CSV legado de la sede N
- `GET /health` — estado del servicio y dependencias
- `GET /metrics` — métricas: total por estado, latencia media, duplicados detectados

