# Diagrama 2 · Secuencia — HL7 de sede → HSB → HAPI → Nodo → Auditoría

**Responsable:** A — Jose Guillermo Canchila
**Herramienta:** Mermaid `sequenceDiagram`

## Descripción

Muestra el flujo completo de un mensaje HL7 v2 ADT^A01 desde que el sistema legado de una sede lo envía al HSB, hasta que queda persistido en HAPI FHIR y en el nodo de base de datos de la sede, con evento de auditoría.

Se incluyen **dos caminos de error**:
1. **Fallo de validación** → mensaje rechazado (nunca se transforma).
2. **HAPI no disponible** → mensaje entra a la cola de reintentos con backoff exponencial.

## Diagrama

```mermaid
sequenceDiagram
    actor SistemaSede as Sistema Sede (legado)
    participant HSB as HSB<br/>(Parser + Validador)
    participant Idemp as Control<br/>Idempotencia
    participant Trans as Transformador<br/>FHIR
    participant Cola as Cola de<br/>Reintentos
    participant HAPI as HAPI FHIR R4<br/>:8090
    participant NodoDB as Nodo BD<br/>(sede correspondiente)
    participant Audit as Servicio<br/>Auditoría

    SistemaSede->>+HSB: POST /hsb/hl7<br/>(texto plano HL7 v2)
    HSB->>Idemp: ¿MSH-10 ya procesado?

    alt Duplicado detectado
        Idemp-->>HSB: SI — hash existe
        HSB-->>SistemaSede: 200 OK {estado:"duplicado", mensaje_id:"MSG-0001"}
        HSB->>Audit: EVENTO tipo=DUPLICADO_DETECTADO
    else Mensaje nuevo
        Idemp-->>HSB: NO — mensaje nuevo; registrar hash
        HSB->>HSB: Parsear segmentos<br/>MSH·PID·PV1·DG1·OBX

        HSB->>HSB: Validar campos<br/>(documento, sexo, sede, fecha, CIE-10)

        alt Validación FALLA
            HSB-->>SistemaSede: 422 Unprocessable<br/>{estado:"rechazado", motivos:[...]}
            HSB->>Audit: EVENTO tipo=MENSAJE_RECHAZADO<br/>motivos, sede, timestamp
            HSB->>NodoDB: INSERT mensaje_bus<br/>estado=RECHAZADO
        else Validación OK
            HSB->>+Trans: Normalizar a FHIR R4<br/>(Patient, Encounter, Condition/Observation)
            Trans-->>-HSB: Bundle transaction (PUT)<br/>IDs deterministas pac-<documento>

            HSB->>+Cola: Encolar Bundle<br/>estado=TRANSFORMADO

            Cola->>+HAPI: PUT /fhir Bundle transaction

            alt HAPI disponible
                HAPI-->>-Cola: 200 OK — Bundle aceptado
                Cola->>+NodoDB: INSERT/UPDATE usuario, atencion,<br/>diagnostico, tecnologia_salud
                NodoDB-->>-Cola: COMMIT OK
                Cola->>NodoDB: UPDATE mensaje_bus<br/>estado=ENTREGADO
                Cola->>Audit: EVENTO tipo=MENSAJE_ENTREGADO<br/>bundle_id, sede, timestamp
                Cola-->>-HSB: Entregado
                HSB-->>-SistemaSede: 202 Accepted<br/>{estado:"entregado", bundle_id:"..."}

            else HAPI no disponible (5xx / timeout)
                HAPI-->>Cola: Error 503 / timeout
                Cola->>NodoDB: UPDATE mensaje_bus<br/>estado=REINTENTANDO, intentos=1
                Cola->>Audit: EVENTO tipo=REINTENTO<br/>intento=1, prox_intento=+1s

                loop Reintentos (backoff: 1s, 2s, 4s, 8s)
                    Cola->>HAPI: PUT /fhir Bundle (reintento N)
                    alt HAPI responde
                        HAPI-->>Cola: 200 OK
                        Cola->>NodoDB: UPDATE estado=ENTREGADO
                        Cola->>Audit: EVENTO tipo=MENSAJE_ENTREGADO_TRAS_REINTENTO
                    else Sigue fallando
                        Cola->>NodoDB: UPDATE intentos=N+1
                        Note over Cola: Si intentos >= 4 → estado=MUERTO
                    end
                end

                opt Máximo intentos alcanzado
                    Cola->>NodoDB: UPDATE mensaje_bus estado=MUERTO
                    Cola->>Audit: EVENTO tipo=MENSAJE_MUERTO
                    Cola-->>HSB: Fallo permanente
                    HSB-->>SistemaSede: 503 Service Unavailable<br/>{estado:"muerto", puede_reencolar:true}
                end
            end
        end
    end
```

## Coherencia con otros diagramas

| Elemento | Aparece en casos de uso | Aparece en clases | Estado resultante |
|----------|------------------------|-------------------|-------------------|
| SistemaSede | UC14 | `Sede` | — |
| HSB (validación) | UC14 | `MensajeBus` | RECHAZADO / VALIDADO |
| HAPI FHIR | UC14 | `BundleFHIR` | ENTREGADO |
| NodoDB | UC14 | `Atencion`, `Diagnostico`, `TecnologiaSalud` | — |
| Auditoría | UC11 | `EventoAuditoria` | Todos |

> **Por qué primero HAPI y después NodoDB:** Si se guardara primero en NodoDB y luego HAPI fallara,
> habría datos en la BD que no están en el servidor FHIR, rompiendo la consistencia.
> HAPI actúa como árbitro; el PUT es idempotente y seguro de repetir.

