# Diagrama 4 · Estados del Mensaje en el Bus

**Responsable:** A — Jose Guillermo Canchila
**Herramienta:** Mermaid `stateDiagram-v2`

## Descripción

Muestra el ciclo de vida completo de un `MensajeBus` desde que entra al HSB hasta que es entregado, rechazado o muerto. Cada transición corresponde a una acción concreta del sistema y genera un `EventoAuditoria`.

## Diagrama

```mermaid
stateDiagram-v2
    [*] --> RECIBIDO : POST /hsb/hl7\nó POST /hsb/csv

    RECIBIDO --> DUPLICADO : hash(contenido)\nya existe en BD
    DUPLICADO --> [*] : Responder 200 duplicado\nregistrar en auditoría

    RECIBIDO --> VALIDANDO : Mensaje nuevo\n(idempotencia OK)

    VALIDANDO --> RECHAZADO : Falla alguna regla\n(doc, sexo, sede,\nfecha, CIE-10)
    RECHAZADO --> [*] : Registrar motivo(s)\nen auditoría\n→ nunca se pierde

    VALIDANDO --> TRANSFORMADO : Pasa todas las reglas\nde validación

    TRANSFORMADO --> ENVIANDO : Bundle listo\nencolar para HAPI

    ENVIANDO --> ENTREGADO : HAPI responde 2xx\n+ nodo BD confirma COMMIT
    ENTREGADO --> [*] : Registrar en auditoría\nactualizar fhir_patient_id

    ENVIANDO --> REINTENTANDO : HAPI no disponible\n(503 / timeout)

    REINTENTANDO --> ENVIANDO : Backoff exponencial\n(1s → 2s → 4s → 8s)\nintento < MAX_REINTENTOS(4)

    REINTENTANDO --> MUERTO : intentos >= MAX_REINTENTOS\nsin respuesta de HAPI

    MUERTO --> ENVIANDO : Reencolar manualmente\n(operador o auditor)
    MUERTO --> [*] : Dejar como evidencia\nen dead-letter queue

    note right of RECIBIDO
        Se persiste en mensaje_bus
        con estado=RECIBIDO
        antes de cualquier validación.
        Garantía: nunca se pierde en silencio.
    end note

    note right of REINTENTANDO
        El estado persiste en BD.
        Si el HSB cae y se reinicia,
        retoma desde REINTENTANDO
        sin duplicar (idempotencia PUT).
    end note

    note right of ENTREGADO
        HAPI siempre ANTES que nodo BD.
        Si nodo BD falla después del PUT
        en HAPI, el reintento es seguro
        (PUT es idempotente en FHIR).
    end note
```

## Tabla de transiciones

| Desde | Hacia | Disparador | Evento de auditoría |
|-------|-------|-----------|---------------------|
| — | RECIBIDO | POST /hsb/hl7 ó /hsb/csv | `MENSAJE_RECIBIDO` |
| RECIBIDO | DUPLICADO | Hash ya existe en BD | `DUPLICADO_DETECTADO` |
| RECIBIDO | VALIDANDO | Hash nuevo registrado | — |
| VALIDANDO | RECHAZADO | Al menos 1 regla falla | `MENSAJE_RECHAZADO` |
| VALIDANDO | TRANSFORMADO | Todas las reglas pasan | — |
| TRANSFORMADO | ENVIANDO | Bundle FHIR generado y encolado | — |
| ENVIANDO | ENTREGADO | HAPI 2xx + BD COMMIT OK | `MENSAJE_ENTREGADO` |
| ENVIANDO | REINTENTANDO | HAPI 5xx / timeout | `REINTENTO` (con nº intento) |
| REINTENTANDO | ENVIANDO | Timer backoff cumplido, intento < 4 | — |
| REINTENTANDO | MUERTO | intentos ≥ 4 | `MENSAJE_MUERTO` |
| MUERTO | ENVIANDO | Reencolar manual | `MENSAJE_REENCOLADO` |

## Coherencia con otros diagramas

- Los estados `RECIBIDO`, `VALIDADO`, `TRANSFORMADO`, `ENTREGADO`, `RECHAZADO`, `REINTENTANDO`, `MUERTO` corresponden exactamente al campo `estado` de la clase `MensajeBus` (diagrama de clases).
- Las transiciones que generan `EventoAuditoria` corresponden a los participantes del diagrama de secuencia.
- Los actores que pueden reencolar un mensaje MUERTO son el **Auditor** (UC13 en casos de uso).

