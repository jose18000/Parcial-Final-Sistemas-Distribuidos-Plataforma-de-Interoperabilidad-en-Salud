# Diagrama 2 · Secuencia — mensaje HL7 de una sede hasta FHIR, la base de la sede y la auditoría

**Responsables:** A — Jose Guillermo Canchila (diagrama) · B — Sharit Javier Manjarrez (revisión v2)
**Herramienta:** Mermaid `sequenceDiagram`
**Versión:** v2 — traductor universal, sede en PostgreSQL o MongoDB, reintentos en segundo plano

## Qué muestra

El recorrido de un mensaje HL7 v2 (por ejemplo `ejemplos/01_adt_a01_valido_sede2.hl7`) desde que
el sistema legado de la sede lo envía al HSB hasta que queda:

1. publicado en **HAPI FHIR R4** como Bundle `transaction` con `PUT` e ids deterministas, y
2. guardado en la **base de su sede** por el repositorio que corresponde a su motor:
   `RepositorioPostgres` (sedes 1 y 3) o `RepositorioMongo` (sede 2).

Incluye los caminos de **duplicado**, **rechazo** (error de validación), **reintento** (HAPI o la
sede no responden) y **error de datos** (va directo a MUERTO, sin reintentar).

**Sobre la auditoría.** Hay dos registros distintos y el diagrama muestra los dos:

- El **estado del mensaje** (RECHAZADO, VALIDADO, TRANSFORMADO, ENTREGADO, REINTENTANDO, MUERTO) se
  guarda en `mensaje_bus` (tabla en PostgreSQL / colección `mensajes_bus` en MongoDB) de la sede del
  mensaje. Es la trazabilidad del bus; de ahí salen la idempotencia y la recuperación tras reinicio.
- La **cadena de auditoría SHA-256** (`pg_central.evento_auditoria`) la escribe la API Gateway: cada
  consulta de una historia, cada escritura desde una vista y cada acceso denegado. El HSB no escribe
  en ella. Por eso la secuencia termina con la consulta del médico, que deja su evento encadenado.

## Diagrama

```mermaid
sequenceDiagram
    autonumber
    actor Sede as Sistema de sede (HIS legado)
    participant HSB as HSB (8001)<br/>main.py + ingesta.py
    participant Trad as Traductor 57<br/>traductor.py
    participant MB as mensaje_bus<br/>(base de la sede)
    participant Val as Validador<br/>validator.py
    participant Norm as Normalizador<br/>fhir/normalizer.py
    participant HAPI as HAPI FHIR R4 (8090)
    participant Repo as Repositorio de la sede<br/>PostgreSQL o MongoDB
    participant Cola as Cola de reintentos<br/>(hilo en segundo plano)
    actor Med as Médico
    participant API as API Gateway (8000)
    participant Aud as Auditoría<br/>pg_central

    Sede->>HSB: POST /hsb/hl7 (texto HL7 v2)
    HSB->>Trad: desde_hl7(raw)
    Trad-->>HSB: metadatos (MSH-10, sede de MSH-4, hash SHA-256)<br/>y registro canónico (57 campos, segmentos Z, derivados)
    HSB->>MB: buscar_mensaje(MSH-10 o hash)

    alt Ya existe en ENTREGADO, TRANSFORMADO o REINTENTANDO
        MB-->>HSB: encontrado
        HSB-->>Sede: 200 estado duplicado (no crea nada)
    else Mensaje nuevo
        MB-->>HSB: no existe
        HSB->>Val: validar (documento 4-15 dígitos, nombre, sexo M/F/O,<br/>sede 1-3, fechas, CIE-10, LOINC)

        alt Falla al menos una regla
            Val-->>HSB: lista de motivos
            HSB->>MB: registrar estado RECHAZADO con motivos
            HSB-->>Sede: 422 estado rechazado y motivos
        else Valida
            Val-->>HSB: válido
            HSB->>MB: registrar estado VALIDADO
            HSB->>Norm: bundle_desde_registro(registro)
            Norm-->>HSB: Bundle transaction con PUT<br/>pac-, enc-, cond-, obs-, med-, prac-, org-sede-, alg-
            HSB->>MB: registrar estado TRANSFORMADO (guarda el contenido original)

            HSB->>HAPI: POST /fhir (Bundle transaction)
            alt HAPI responde 200
                HAPI-->>HSB: 200 OK
                HSB->>Repo: guardar(registro con ids FHIR)
                Note over Repo: En PostgreSQL UPSERT de usuario, atención,<br/>diagnósticos, tecnologías y egreso en UNA transacción.<br/>En MongoDB replace_one del documento del paciente<br/>(escritura atómica de un solo documento).
                alt La sede guarda
                    Repo-->>HSB: OK
                    HSB->>MB: registrar estado ENTREGADO
                    HSB-->>Sede: 200 estado entregado y recursos FHIR
                else Error de datos (restricción violada)
                    Repo-->>HSB: IntegrityError, CheckViolation o WriteError
                    HSB->>MB: registrar estado MUERTO (motivo permanente)
                    HSB-->>Sede: 503 estado muerto (no se reintenta)
                else La sede no responde
                    Repo-->>HSB: error de conexión o timeout
                    HSB->>MB: registrar estado REINTENTANDO (intento 1)
                    HSB->>Cola: programar con espera de 2 s
                    HSB-->>Sede: 202 estado reintentando
                end
            else HAPI responde 4xx (error de datos)
                HAPI-->>HSB: HTTP 4xx
                HSB->>MB: registrar estado MUERTO (motivo permanente)
                HSB-->>Sede: 503 estado muerto
            else HAPI caído o timeout
                HAPI--xHSB: sin respuesta
                HSB->>MB: registrar estado REINTENTANDO (intento 1)
                HSB->>Cola: programar con espera de 2 s
                HSB-->>Sede: 202 estado reintentando
            end
        end
    end

    opt Mensaje en REINTENTANDO
        loop Hasta entregar o completar HSB_MAX_RETRIES = 7 intentos (esperas 2, 4, 8, 16, 32, 64 s)
            Cola->>HAPI: POST /fhir (mismo Bundle, PUT idempotente)
            Cola->>Repo: guardar (UPSERT o replace_one, idempotente)
            Cola->>MB: REINTENTANDO (intento n) o ENTREGADO
        end
        Note over Cola,MB: Si se agotan los intentos queda MUERTO.<br/>POST /hsb/reencolar/(id) lo devuelve a REINTENTANDO.<br/>Si el bus se reinicia, recuperar_pendientes() relee<br/>REINTENTANDO y TRANSFORMADO de las sedes y los reprograma.
    end

    Med->>API: GET /medico?buscar_doc=1007 (JWT rol medico)
    API->>Repo: historia(1007) en las 3 sedes, en paralelo
    Repo-->>API: historias canónicas (una sede caída se marca no disponible)
    API->>Aud: registrar evento CONSULTA_HC (hash encadenado)
    API-->>Med: historia unificada y cobertura de los 57 campos
```

## Escritura desde una vista (misma ruta, otra entrada)

Las vistas no hablan con las bases. Cuando el médico registra un diagnóstico, una fórmula o un
egreso, la API **primero** registra el evento `ESCRITURA_HC` en `pg_central`; el hash de ese evento
es el **sello** que se devuelve al médico (y, en el egreso, se guarda en `egreso.sello_hash`).
Después envía el registro al HSB por `POST /hsb/json?sede=N`, que sigue los mismos pasos del
diagrama desde el traductor (`desde_json`). Si el HSB lo rechaza, la API agrega otro evento
`ESCRITURA_HC` con resultado `FALLIDO`. El admisionista sigue el mismo camino con el evento
`APERTURA_ATENCION`.

## Coherencia con los otros diagramas

| Participante | Caso de uso (diagrama 1) | Clase (diagrama 3) | Estados que produce (diagrama 4) |
|---|---|---|---|
| Sistema de sede | UC14 | `Sede` | RECIBIDO |
| Traductor 57 | UC15 | `RegistroCanonico`, `Campo` | — |
| mensaje_bus | UC6, UC15 | `MensajeBus` | Todos los persistidos |
| Validador | UC15 | `MensajeBus` | VALIDADO / RECHAZADO |
| Normalizador y HAPI | UC15, UC2 | `RegistroCanonico` (genera el Bundle) | TRANSFORMADO / ENTREGADO / MUERTO (4xx) |
| Repositorio de la sede | UC15, UC7 | `RepositorioSede`, `RepositorioPostgres`, `RepositorioMongo`, `Usuario`, `Atencion`… | ENTREGADO / REINTENTANDO / MUERTO |
| Cola de reintentos | UC15 | `MensajeBus` (intentos) | REINTENTANDO → ENTREGADO / MUERTO |
| Médico, API Gateway, Auditoría | UC7, UC16 | `EventoAuditoria` | — |

> **Por qué HAPI primero y la sede después.** Es el orden que pide la guía de la Fase 3 (paso 6).
> Si HAPI acepta y la sede falla, el mensaje queda en REINTENTANDO y el siguiente intento repite
> los dos pasos: el `PUT` con ids deterministas sobrescribe el mismo recurso en HAPI y la sede
> hace UPSERT por las mismas llaves. Repetir no duplica, por eso no hace falta una transacción
> distribuida (2PC) entre HAPI y la sede.
