# Plataforma distribuida de interoperabilidad clínica para una red de IPS con tres sedes heterogéneas

**Autores:**
- Jose Guillermo Canchila (A) — Correo: `memocanchila@gmail.com`
- Sharit Javier Manjarrez (B) — Correo: `sharit@clinica.local`

**Asignatura:** Sistemas Distribuidos · Parcial final
**Fecha:** noviembre de 2026
**Versión del informe:** 2.0 (prototipo v2: 57 campos, traductor universal y sedes con motores distintos)
**Plantilla:** v7

---

## Resumen

Una red de IPS con sedes en Sincelejo, Cartagena y Corozal guarda la historia clínica de un mismo
paciente fraccionada en sistemas legados con bases y formatos distintos. El objetivo fue construir
una plataforma distribuida que unifique esa historia sin reemplazar los legados. Se implementó un
bus de servicios de salud (HSB) en FastAPI que recibe HL7 v2, CSV y JSON, los traduce con un
catálogo único de los 57 campos de la Resolución 866 de 2021 a un registro canónico, los valida y
los entrega como Bundle FHIR R4 a HAPI FHIR y a la base de la sede: PostgreSQL en Sincelejo y
Corozal, MongoDB en Cartagena. Una API con JWT y cuatro roles sirve las vistas, consulta las tres
sedes en paralelo y registra cada acceso en una cadena de auditoría SHA-256. En una máquina
virtual Kali Linux con 3,8 GB de RAM, el sistema arrancó desde cero con un comando; el mensaje HL7
de prueba cubrió 56 de 57 campos y el 100 % de los obligatorios; la historia del paciente 1001
reunió 52 de 57 campos desde dos motores, y su Bundle de 26 recursos validó en HAPI sin errores.
Reenviar un mensaje no creó duplicados; con HAPI apagado, el mensaje se entregó solo a los 129,5 s;
al detener la sede MongoDB, la consulta respondió con dos sedes y marcó el reporte incompleto; el
verificador señaló el índice exacto de un evento alterado. Pasaron 36 pruebas automatizadas.

**Palabras clave:** sistemas distribuidos, interoperabilidad clínica, HL7 v2, FHIR R4, Resolución 866 de 2021, MongoDB, teorema CAP, idempotencia.

---

## 1. Introducción y objetivos

### 1.1 Problema

Cuando un paciente se atiende en Sincelejo, consulta por urgencias en Cartagena y hace controles
en Corozal, cada sede guarda su parte de la historia en su propio sistema. Ninguna ve la historia
completa: se repiten exámenes y se decide con información parcial. La Resolución 866 de 2021 del
Ministerio de Salud define el conjunto de 57 datos de la historia clínica que deben poder
intercambiarse. El reto del parcial es unificar la historia **sin reemplazar** los sistemas
legados: cada sede conserva su base, su motor y su formato de envío (HL7 v2 o CSV).

En la versión 2 se tomó literalmente la heterogeneidad: por indicación del docente, las sedes no
usan el mismo motor. Sincelejo y Corozal usan PostgreSQL; Cartagena usa MongoDB, con un documento
por paciente y nombres de campo distintos. La plataforma no puede suponer un esquema común.

### 1.2 Objetivo general

Diseñar, implementar y evaluar una plataforma distribuida que unifique la historia clínica de un
paciente atendido en tres sedes con sistemas legados heterogéneos (HL7 v2, CSV; PostgreSQL,
MongoDB), usando FHIR R4 y los 57 campos de la Resolución 866 de 2021, sin reemplazar los legados.

### 1.3 Objetivos específicos

1. **Traducir** mensajes HL7 v2 (ADT^A01, ADT^A03, ORU^R01), filas CSV legadas y registros JSON de
   las tres sedes a un registro canónico de 57 campos, y medir la cobertura de campos por paciente
   (meta: 100 % de los campos obligatorios en el mensaje de prueba completo).
2. **Publicar** cada atención en HAPI FHIR R4 como Bundle `transaction` con `PUT` e ids
   deterministas, con 0 errores en `$validate` y 0 recursos duplicados al reenviar un mensaje.
3. **Reducir a una sola consulta** la búsqueda de la historia de un paciente con registros en tres
   sedes y dos motores, que siga respondiendo si una sede cae y avise que el reporte está incompleto.
4. **Controlar el acceso y la trazabilidad**: cuatro roles con permisos validados en la API (403
   auditado), auditoría encadenada por hash que señale el evento alterado exacto, y entrega
   automática de un mensaje cuando HAPI vuelve tras una caída.

---

## 2. Marco teórico y conceptual

**Sistema distribuido, transparencia y fallos parciales.** Un sistema distribuido es un conjunto de
computadores autónomos que el usuario percibe como uno solo (Tanenbaum y Van Steen, 2017). Lo
distintivo es el fallo parcial: una sede puede caer mientras las otras siguen. La plataforma no
oculta ese fallo: responde con lo que tiene y dice qué falta.

**Teorema CAP.** Ante una partición de red, un sistema distribuido elige entre consistencia (todas
las réplicas ven el mismo dato) y disponibilidad (toda petición recibe respuesta). La consulta
unificada es **AP**: si la sede 2 no responde, la historia se arma con las sedes 1 y 3 y se marca
`reporte_completo = false`. Lo que se sacrifica es ver en ese momento las atenciones de la sede caída.

**ACID.** Atomicidad, consistencia, aislamiento y durabilidad de una transacción local. En las sedes
PostgreSQL, el usuario, la atención, los diagnósticos, las tecnologías y el egreso se guardan en una
sola transacción. En MongoDB la unidad atómica es el documento: como la atención completa está
embebida en el documento del paciente, guardarla es **una** escritura de un solo documento, atómica
sin transacciones multi-documento.

**Fragmentación horizontal.** Partir los datos por filas según un criterio. Aquí el criterio es la
sede de la atención: cada sede guarda sus atenciones. La clave común entre sedes es el número de
documento del paciente.

**HL7 v2.** Mensajería por segmentos de texto (`MSH`, `PID`, `PV1`, `DG1`, `OBX`…), campos
separados por `|` y componentes por `^`. `MSH-10` identifica el mensaje. Los datos que el estándar no
trae se envían en **segmentos Z**, definidos por acuerdo entre las partes.

**FHIR R4.** Estándar de HL7 basado en recursos (Patient, Encounter, Condition, Observation…) que se
intercambian por REST en JSON (HL7 International, 2019). Un **Bundle** de tipo `transaction` agrupa
recursos que el servidor procesa como una unidad. Un **perfil** restringe un recurso para un uso
concreto; este proyecto usa extensiones propias, no un perfil publicado.

**Bus de integración (HSB) e idempotencia.** Un bus desacopla a quien envía de quien recibe y
concentra traducción, validación, enrutamiento y reintentos (Hohpe y Woolf, 2003). Una operación es
**idempotente** si repetirla deja el mismo estado que hacerla una vez; es lo que permite reintentar
sin miedo a duplicar.

**Terminologías.** CIE-10 codifica diagnósticos (`J45.9` asma, `I10` hipertensión esencial). LOINC
codifica pruebas de laboratorio (`718-7` hemoglobina).

---

## 3. Estado del arte

Fuentes de alcance global, latinoamericano y colombiano (referencias completas al final):

| # | Fuente | Alcance | Qué tomamos para el proyecto |
|---|---|---|---|
| 1 | Bender y Sartipi (2013) | Global | Argumentos a favor de FHIR (recursos REST) frente a la sintaxis de HL7 v2: base para publicar en FHIR y conservar HL7 v2 solo como formato de entrada de los legados. |
| 2 | Centro Nacional en Sistemas de Información en Salud (2022) | Latinoamérica (Chile) | Uso de Observation con LOINC y Condition con CIE-10 en redes asistenciales. |
| 3 | HAPI FHIR Community (2024) | Global | Servidor FHIR R4 de referencia, operación `$validate` y Bundles `transaction`. |
| 4 | Hohpe y Woolf (2003) | Global | Patrones *Idempotent Receiver*, *Dead Letter Channel*, *Scatter-Gather* y *Canonical Data Model*, que el HSB implementa. |
| 5 | Ministerio de Salud de la Nación Argentina (2020) | Latinoamérica (Argentina) | Experiencia nacional de implementación de FHIR con identificadores estables. |
| 6 | Ministerio de Salud y Protección Social (2021) | Colombia | Resolución 866: los 57 datos de la historia clínica interoperable y sus dominios. |
| 7 | NextGen Healthcare (2023) | Global | Mirth Connect como motor de integración HL7 de referencia. |
| 8 | OpenHIE Consortium (2022) | Global / países en desarrollo | OpenHIM: separar la mediación (seguridad, auditoría) del almacenamiento. |
| 9 | HL7 International (2019) | Global | Especificación FHIR R4: recursos, Bundle, transacciones y extensiones. |

### Comparación de herramientas

| Criterio | HAPI FHIR | Mirth Connect | OpenHIM | Apache Camel | HSB propio (FastAPI) |
|---|---|---|---|---|---|
| Papel | Servidor FHIR | Motor de integración HL7 | Mediador de intercambio | Marco de integración | Bus del proyecto |
| FHIR R4 | Nativo | Por conectores | Hacia un servidor FHIR externo | Por componentes | Cliente REST hacia HAPI |
| HL7 v2 | Librería de parsing | Nativo (canales) | No es su foco | Componente HL7 | Traductor propio guiado por catálogo |
| Plataforma | Java | Java | Node.js | Java | Python |
| Cómo se configura | Código / propiedades | Interfaz gráfica de canales | Consola web | DSL / código | Código y catálogo de 57 campos |
| Uso en el proyecto | **Sí** (servidor FHIR) | No | No | No | **Sí** (bus) |

Se usa HAPI porque es la referencia abierta de FHIR R4 y el laboratorio ya la conocía. Para el bus se
descartaron Mirth, OpenHIM y Camel porque cada integrante debe poder explicar y modificar en vivo
cualquier parte (regla del parcial) y porque agregan otra plataforma de ejecución; a cambio, el
proyecto renuncia a sus herramientas gráficas y conectores ya hechos.

---

## 4. Solución propuesta y metodología

### 4.1 Arquitectura final

Siete contenedores, levantados con `docker compose down -v && docker compose up -d --build`:

| Contenedor | Papel | Puerto en el anfitrión |
|---|---|---|
| `pg_sede1` | Sede 1 Sincelejo — PostgreSQL 16 (`clinica_sincelejo`) | 5433 |
| `mongo_sede2` | Sede 2 Cartagena — MongoDB 7 (`clinica_cartagena`), un documento por paciente | 27018 |
| `pg_sede3` | Sede 3 Corozal — PostgreSQL 16 (`clinica_corozal`) | 5435 |
| `pg_central` | Cadena de auditoría (`evento_auditoria`); no es una sede | 5436 |
| `hapi_fhir_r4` | HAPI FHIR R4 v7.2.0 | 8090 |
| `hsb_bus` | Health Service Bus | 8001 |
| `api_gateway` | API Gateway y 4 vistas por rol | 8000 |

```
 HL7 v2 ─┐                          ┌─> HAPI FHIR R4 (Bundle transaction, PUT)
 CSV    ─┼─> HSB ─> traductor 57 ───┼─> Sede 1 PostgreSQL
 JSON   ─┘   valida, idempotencia,  ├─> Sede 2 MongoDB
             cola y reintentos      └─> Sede 3 PostgreSQL
                                          ▲
 4 vistas por rol ─> API Gateway ─────────┘  consulta unificada en paralelo
                         └─> pg_central: auditoría encadenada por hash
```

El diagrama Mermaid completo y la tabla componente / requisito / justificación están en
[`fase1/arquitectura/arquitectura_y_justificacion.md`](fase1/arquitectura/arquitectura_y_justificacion.md).

### 4.2 Capa de datos: por qué PostgreSQL y MongoDB

- **Un nodo por sede (RF4).** Cada IPS conserva su base; no hay base central de datos clínicos. La
  única base central guarda la auditoría.
- **Motores distintos.** Sedes 1 y 3 usan el esquema relacional de 57 campos (`db/schema.sql`):
  `usuario`, `atencion`, `diagnostico`, `tecnologia_salud`, `egreso`, `profesional_salud`, `sede`,
  `mensaje_bus`. La sede 2 usa la colección `pacientes` con un documento por paciente y sus
  atenciones embebidas (dentro de cada una: diagnósticos, tecnologías y egreso), más
  `mensajes_bus`, `profesionales` y `sedes`. Los nombres no coinciden a propósito
  (`identificacion.numero` frente a `documento_id`, `ingreso.fecha` frente a `fecha_ingreso`).
- **Repositorio con una sola interfaz.** `RepositorioPostgres` y `RepositorioMongo`
  (`db/repositorio.py`) exponen `guardar`, `historia`, `cobertura_fhir` y los métodos de
  `mensaje_bus`, y hablan siempre en el registro canónico. El bus y la API no saben qué motor tiene
  cada sede.
- **ACID local.** En PostgreSQL, `guardar` hace UPSERT de las cinco tablas en una transacción. La
  demostración `db/demo_acid.sql` inserta un usuario y luego una atención con
  `clasificacion_triage = '9'`: el `CHECK` falla y PostgreSQL revierte todo, sin dejar al usuario
  huérfano. En MongoDB, `guardar` reemplaza el documento completo del paciente con `replace_one`,
  que es atómico por ser un solo documento.
- **CAP entre sedes.** No hay transacción distribuida entre sedes ni entre HAPI y la sede. La
  lectura es AP (ver §2). La escritura es eventualmente consistente: el bus escribe en HAPI y luego
  en la sede; si la sede falla, el mensaje queda en REINTENTANDO y se completa cuando vuelve.
  Durante ese intervalo HAPI tiene el dato y la sede no.
- **MongoDB sin réplica.** `mongo_sede2` es un nodo único (sin *replica set*): no hay
  transacciones multi-documento ni conmutación por fallo. Si cae, la sede 2 no está disponible; la
  consulta sigue con las otras dos y los mensajes de la sede 2 esperan en REINTENTANDO.

### 4.3 Traductor universal de 57 campos (`traductor/`)

- `catalogo_57.py` es la fuente única de verdad. Cada uno de los 57 campos dice de qué segmento HL7
  sale, qué columna CSV lo trae, en qué `tabla.columna` de PostgreSQL y en qué ruta del documento
  MongoDB queda, y a qué elemento FHIR corresponde, además de si es obligatorio (23 lo son) y su
  dominio.
- `dominios.py` tiene los códigos permitidos y los sinónimos que usa cada sede (`E` de PV1-2 →
  entorno `01` Urgencias, triage `III` → `3`, sexo `I` → `O`, vía `PO` → `01` Oral).
- `traductor.py` hace HL7 / CSV / JSON → **registro canónico** → filas PostgreSQL / documento
  MongoDB, y de vuelta. El canónico es el pivote: con 3 entradas y 3 salidas se escriben 6
  traducciones y no 9.
- **Segmentos Z** para lo que HL7 v2.5 no trae: `ZPI` (género, ocupación, voluntad anticipada,
  discapacidad, comunidad étnica, zona), `ZPV` (modalidad, fecha y clase de triage), `ZRX`
  (finalidad del medicamento) y `ZEG` (diagnóstico de muerte, incapacidad, licencia, antecedentes,
  riesgos, responsable del egreso).
- **Diagnósticos 33–39** como filas con `rol` INGRESO / EGRESO / RELACIONADO y `orden`.
- **Derivados:** edad y unidad de edad (de la fecha de nacimiento) y código del prestador (del REPS
  sintético de la sede).
- **Cobertura:** `cobertura_57()` cuenta, para un paciente, los campos con valor en el usuario o en
  cualquiera de sus atenciones de cualquier sede, y devuelve los faltantes y si son obligatorios.
- El mapeo completo se genera con `python -m traductor.generar_mapeo` en
  [`mapeo_57_campos.md`](mapeo_57_campos.md).

### 4.4 HSB

Entradas `POST /hsb/hl7`, `POST /hsb/csv?sede=N` y `POST /hsb/json?sede=N`; operación
`GET /hsb/mensajes`, `GET /hsb/catalogo`, `POST /hsb/reencolar/{id}`, `GET /health` y `GET /metrics`.
Flujo (`hsb/ingesta.py`):

1. **Traducir** al registro canónico.
2. **Idempotencia:** busca `MSH-10` (o el hash SHA-256 de la fila CSV / del JSON) en `mensaje_bus`
   de la sede; si ya está ENTREGADO, TRANSFORMADO o REINTENTANDO responde `duplicado`.
3. **Validar:** documento de 4 a 15 dígitos, nombre, sexo M/F/O, sede 1–3, fechas, CIE-10 y LOINC.
   Si falla, RECHAZADO con todos los motivos.
4. **Normalizar** a Bundle `transaction` con `PUT` e ids deterministas: `pac-<doc>`, `enc-<visita>`,
   `cond-<visita>-<rol>-<cie10>`, `obs-<visita>-<loinc>`, `med-<visita>-…`, `prac-<código>`,
   `org-sede-<n>`, `alg-<doc>`. Recursos: Organization, Practitioner, Patient, Encounter,
   Condition (CIE-10), Observation (LOINC), MedicationRequest y AllergyIntolerance; extensiones
   bajo `https://minsalud.gov.co/fhir/StructureDefinition/`.
5. **Entregar:** primero HAPI, después la sede; ambos pasos son idempotentes.
6. **Reintentar** en segundo plano con espera creciente 2, 4, 8, 16, 32, 64 s
   (`HSB_MAX_RETRIES=7`, `HSB_RETRY_BASE_SECONDS=2`); al agotarlos, MUERTO, y se puede reencolar.
   Los **errores de datos** (restricción violada en la sede, HTTP 4xx de HAPI) van directo a MUERTO:
   reintentarlos no los arregla. Al reiniciar, el bus recupera de las sedes los mensajes que quedaron
   en REINTENTANDO o TRANSFORMADO.

### 4.5 Seguridad

- **JWT HS256** (60 min) emitido en `/auth/login`; viaja en cookie para las vistas o como `Bearer`.
- **Cuatro roles** con permisos validados en la API: paciente (solo su historia), admisionista
  (búsqueda y admisión, sin diagnósticos), médico (historia unificada y escrituras clínicas),
  auditor (reporte, tablero y verificador). Un acceso no permitido responde **403** y deja un evento
  `ACCESO_DENEGADO`.
- **Auditoría encadenada** en `pg_central.evento_auditoria`:
  `hash_propio = SHA-256(hash_anterior | indice | timestamp | usuario | rol | tipo | recurso | resultado | detalle)`.
  La inserción toma `pg_advisory_xact_lock` para que dos peticiones simultáneas no enlacen al mismo
  hash anterior. El verificador recorre la cadena y devuelve el **primer** evento alterado.
- **Sello de escritura:** cada escritura del médico registra primero su evento; el hash de ese
  evento es el sello que se devuelve y que el egreso guarda en `sello_hash`.
- **Regla de oro:** las vistas no hablan con las bases; las escrituras viajan al HSB por `/hsb/json`.

### 4.6 Metodología y hoja de ruta

Trabajo iterativo en cinco fases, cada una con entregable funcional y revisión cruzada entre los dos
integrantes; las correcciones entre fases se anotan en la bitácora.

| Fase | Entregable | Estado |
|---|---|---|
| 1. Análisis, UML y diseño | Informe, 4 diagramas, arquitectura, mapeo | Entregada; diagramas actualizados a v2 |
| 2. Datos distribuidos y FHIR | Nodos por sede, normalizador, ACID | Entregada; en v2 esquema de 57 campos y sede 2 en MongoDB |
| 3. HSB | Bus HL7/CSV con reintentos e idempotencia | Entregada; en v2 cola en segundo plano, recuperación y `/hsb/json` |
| 4. Seguridad y resiliencia | JWT, roles, auditoría, caída de sede | Entregada; en v2 auditoría persistida en `pg_central` |
| 5. Prototipo final | 4 vistas, informe, sustentación | Este informe |

---

## 5. Modelado UML y reglas de validación

Los cuatro diagramas están en Mermaid en `docs/fase1/diagramas/` y son coherentes entre sí (los
actores del caso de uso aparecen en la secuencia, sus clases existen en el diagrama de clases y los
estados son los valores de `MensajeBus.estado`):

- [Casos de uso](fase1/diagramas/01_casos_uso.md): 5 actores (paciente, admisionista, médico,
  auditor, sistema de sede) y 17 casos de uso.
- [Secuencia](fase1/diagramas/02_secuencia_hsb.md): sede → HSB → traductor → `mensaje_bus` →
  validador → normalizador → HAPI → repositorio (PostgreSQL o MongoDB) → consulta y auditoría, con
  los caminos de duplicado, rechazo, reintento y error de datos.
- [Clases](fase1/diagramas/03_clases.md): 15 clases, entre ellas `Usuario`, `Atencion`,
  `Diagnostico`, `TecnologiaSalud`, `Egreso`, `ProfesionalSalud`, `Sede`, `MensajeBus`,
  `EventoAuditoria`, `Campo`, `RegistroCanonico` y `RepositorioSede` ← `RepositorioPostgres` /
  `RepositorioMongo`.
- [Estados](fase1/diagramas/04_estados_mensaje.md): RECIBIDO, VALIDADO, TRANSFORMADO, ENTREGADO,
  RECHAZADO, REINTENTANDO y MUERTO, con reencolar y "error de datos → MUERTO".

### Tabla de reglas de validación (antes de transformar)

| Campo | Regla | Motivo de rechazo |
|---|---|---|
| Documento (campo 2) | No vacío, solo dígitos, 4 a 15 | `documento no numérico` / `documento fuera de rango: tiene N dígitos…` |
| Nombre (4) | No vacío | `nombre no puede ser vacío` |
| Sexo (8) | `M`, `F` u `O` (tras sinónimos) | `sexo no válido ('X'): debe ser M, F u O` |
| Sede | 1, 2 o 3 (`MSH-4` o `?sede=N`) | `sede no válida o desconocida` |
| Fecha de nacimiento (5) | Válida y no futura | `fecha de nacimiento no válida` / `en el futuro` |
| Fecha de ingreso (17) | Válida si viene | `fecha de ingreso no válida` |
| Diagnósticos (34, 36–39) | CIE-10 `^[A-Z][0-9]{2}(\.[0-9]{1,4})?$`; en HL7 no se acepta sistema local `L`; en CSV el texto local se mapea con `05_ref_terminologia.csv` | `diagnóstico sin mapeo a CIE-10` |
| Laboratorio | LOINC `^[0-9]+-[0-9]+$` | `código LOINC inválido` |
| Medicamento (25) | Descripción presente | `medicamento sin descripción (campo 25)` |

Un valor opcional fuera de su dominio no rechaza el mensaje: el traductor lo omite y el bus
devuelve una advertencia.

---

## 6. Proceso de desarrollo

- **Análisis y diseño (Fase 1):** problema, UML, arquitectura y mapeo de campos.
- **Desarrollo por fases:** cada fase partió del código de la anterior. En la v2 se reescribieron la
  capa de datos (57 campos, MongoDB), el bus (cola persistente) y la auditoría (persistida), y se
  agregó el traductor. Las correcciones entre fases están en la bitácora (`docs/bitacora.md`).
- **Pruebas:** 36 pruebas automatizadas con `pytest`, todas pasan:

  | Suite | Pruebas | Qué cubre |
  |---|---|---|
  | `tests/fase2/test_normalizer.py` | 8 | Recursos FHIR, ids deterministas, referencias internas, caso inválido |
  | `tests/fase2/test_traductor_57.py` | 10 | Catálogo de 57, esquema SQL frente al catálogo, ida y vuelta MongoDB, CSV, JSON por número de campo |
  | `tests/fase3/test_hsb_integration.py` | 10 | Los 4 ejemplos oficiales, idempotencia, reintento, muerto y reencolar, sede caída |
  | `tests/fase4/test_security_resilience.py` | 8 | Permisos por rol (403 y auditoría), cadena de hash y alteración, resiliencia |

  Además se hicieron las pruebas en vivo de la sección 11 sobre Docker.
- **Despliegue:** Docker Compose con un solo comando; imágenes del HSB y la API construidas desde el
  repositorio. Manifiestos de Kubernetes para Minikube en `infra/k8s/` (bonus).
- **CI/CD:** no se configuró un pipeline de integración continua; las pruebas se corren localmente
  antes de cada commit (`python -m pytest tests/ -v`). Queda como trabajo futuro (por ejemplo,
  GitHub Actions que corra las 36 pruebas en cada *push*).
- **Control de versiones:** repositorio Git con commits de ambos integrantes en las cinco fases y
  etiqueta `v1.0` para la entrega.
- **Uso de IA declarado:** en las fases 1 a 5 (v1) se usó Antigravity (Google DeepMind); en la
  mejora v2 se usó entornos de desarrollo y pruebas locales. El detalle por actividad y la revisión humana están en
  la bitácora.

---

## 7. Diseño de interfaces

Las cuatro vistas son plantillas Jinja2 servidas por la API en `http://localhost:8000` (inicio de
sesión en `/login`). Los permisos se validan en la API, no en la pantalla.

| Vista | Ruta | Usuario de prueba | Qué muestra |
|---|---|---|---|
| Paciente | `/paciente` | `paciente_carlos` | Su historia unificada de las 3 sedes, ordenada por fecha y con la sede (y su motor) de cada atención; botón para descargar su Bundle FHIR; lista de quién accedió a su historia y cuándo |
| Admisionista | `/admision` | `admision_laura` | Búsqueda por documento que dice en qué sedes existe el paciente y si hay datos distintos entre sedes; formulario de registro / admisión con sede y triage (envía al HSB); monitor real de mensajes del bus desde `/hsb/mensajes`. No muestra diagnósticos |
| Médico | `/medico` | `medico_mateo` | Historia unificada; formularios de diagnóstico CIE-10, fórmula (campos 25–32) y egreso (40–50). Cada escritura devuelve su sello |
| Reporte de HC | `/reporte` | médico, auditor, paciente (solo el suyo) | Reporte agrupado por sede con aviso si una sede no respondió; tabla de los 57 campos con cobertura y faltantes; sello SHA-256 del contenido; imprimir y descargar Bundle; pestaña **Tablero** (`?pestana=tablero`) con nodos y motor, cobertura FHIR por sede, métricas del bus y verificación de la auditoría |

**Capturas.** Tomadas el 2026-11-11 sobre la plataforma real desplegada en Kali Linux (Docker),
con datos sintéticos, a 1440 px de ancho (Chrome). Archivos en `docs/capturas/`.

![Figura 1. Inicio de sesión con usuarios de demostración](capturas/01_login.png)
*Figura 1. Inicio de sesión: panel de la plataforma (3 sedes y sus motores, traductor de 57 campos, auditoría) y usuarios de demostración.*

![Figura 2. Vista Paciente](capturas/02_paciente_historia.png)
*Figura 2. Vista Paciente (1001): historia unificada de las 3 sedes en línea de tiempo con la sede y el motor de cada atención, descarga del Bundle FHIR y registro de quién accedió.*

![Figura 3. Admisionista: búsqueda en las 3 sedes](capturas/03_admision_busqueda_1001.png)
*Figura 3. Admisionista: el documento 1001 existe en las 3 sedes (PostgreSQL, MongoDB, PostgreSQL); datos de identificación sin diagnósticos.*

![Figura 4. Admisionista: respuesta del bus](capturas/04_admision_respuesta_hsb.png)
*Figura 4. Admisión de un paciente nuevo en la Sede 2: el HSB responde ENTREGADO, lista los recursos FHIR creados y el sello de auditoría; abajo, el monitor real de mensajes del bus con sus estados y motivos de rechazo.*

![Figura 5. Médico: historia del paciente de 57 campos](capturas/05_medico_historia_1020.png)
*Figura 5. Vista Médico con el paciente 1020 (mensaje HL7 de 57 campos) y los formularios de diagnóstico, fórmula y egreso.*

![Figura 6. Médico: sello de una escritura](capturas/06_medico_sello_escritura.png)
*Figura 6. Registro de un diagnóstico CIE-10 (A90): la escritura viaja por el HSB, queda en MongoDB y devuelve el sello SHA-256 del evento de auditoría.*

![Figura 7. Reporte de HC completo](capturas/07_reporte_hc_1001.png)
*Figura 7. Reporte de HC del paciente 1001 agrupado por sede, cobertura de los 57 campos con faltantes y sello de integridad.*

![Figura 8. Reporte del paciente de 57 campos](capturas/08_reporte_57_campos_1020.png)
*Figura 8. Reporte del paciente 1020: 56 de 57 campos diligenciados (solo falta el 42, diagnóstico de muerte, porque egresa vivo) y 100 % de los obligatorios.*

![Figura 9. Tablero de estado](capturas/09_tablero_estado.png)
*Figura 9. Tablero de estado: sedes activas con su motor, cobertura FHIR por sede, métricas del bus y verificador de auditoría ÍNTEGRA.*

![Figura 10. Reporte incompleto con la Sede 2 caída](capturas/10_reporte_incompleto_sede2_caida.png)
*Figura 10. Con `docker stop mongo_sede2` la vista sigue respondiendo con las sedes 1 y 3, marca la Sede 2 como no disponible y el reporte (y su sello) como INCOMPLETO.*

![Figura 11. Tablero con la Sede 2 caída](capturas/11_tablero_sede2_caida.png)
*Figura 11. Tablero durante la caída: 2 de 3 sedes activas y la Sede 2 (MongoDB) en DOWN.*

![Figura 12. Auditoría alterada detectada](capturas/12_auditoria_alterada_detectada.png)
*Figura 12. Tras un `UPDATE` manual en `evento_auditoria` (índice 3), el verificador pasa a ALERTA y señala el primer evento alterado.*

![Figura 13. Acceso denegado](capturas/13_acceso_denegado_403.png)
*Figura 13. La admisionista intenta abrir la vista del médico: 403 y el intento queda en la auditoría.*

![Figura 14. Inicio de sesión en móvil, modo oscuro](capturas/14_login_movil_oscuro.png)
*Figura 14. Diseño adaptable: inicio de sesión a 390 px con el tema oscuro del sistema.*

**Accesibilidad.** Criterios aplicados y que se verifican sobre las plantillas finales: etiquetas
`<label>` asociadas a cada campo de formulario, navegación completa con teclado, mensajes de estado
(sello, rechazo, sede caída) en texto y no solo por color, y contraste suficiente entre texto y
fondo.

---

## 8. Prototipo final y criterios de aceptación

**Entorno de despliegue probado:** Kali Linux en VirtualBox, 3,8 GB de RAM, Docker 28 con Compose
v2. Comando: `docker compose down -v && docker compose up -d --build`. Los puertos de PostgreSQL se
pueden reasignar en `.env` si el anfitrión ya los usa.

| Requisito | Criterio de aceptación | Estado | Evidencia |
|---|---|---|---|
| RF1 Ingesta | HL7 v2 y CSV (y JSON) de las 3 sedes | Cumplido | `/hsb/hl7`, `/hsb/csv?sede=N`, `/hsb/json?sede=N`; ejemplos 01–04 y mensaje de 57 campos |
| RF2 FHIR R4 | Patient, Encounter, Observation, Condition (CIE-10) en Bundle | Cumplido | `fhir/normalizer.py`; Bundle de 1001 (26 recursos) con 0 errores en `$validate` |
| RF3 HSB | Enrutamiento por sede, transformación, validación, reintentos, idempotencia | Cumplido | `hsb/`; prueba con HAPI apagado: entregado tras 7 intentos sin duplicar |
| RF4 Datos distribuidos | Un nodo por sede y consulta unificada | Cumplido, con motores distintos | `pg_sede1`, `mongo_sede2`, `pg_sede3`; `db/consulta_unificada.py` |
| RF5 Seguridad | Token, roles, auditoría encadenada | Cumplido (Fabric no) | `app/auth.py`, `app/rbac.py`, `app/audit.py`, `pg_central` |
| RF6 Vistas | Paciente, Admisionista, Médico, Reporte de HC con tablero | Cumplido | `app/main.py`, `app/templates/` |
| RNF Un comando | `docker compose up` levanta todo | Cumplido | HAPI tarda 85–95 s en responder |
| RNF Sede caída | La vista sigue con las otras dos y marca la sede | Cumplido | `docker stop mongo_sede2` |
| RNF Observabilidad | `/health` y `/metrics` en cada servicio | Cumplido en HSB y API | HAPI no tiene `/health` propio; su estado lo reportan HSB y API |

---

## 9. Viabilidad técnica

| Aspecto | Implementado | Propuesto (no implementado) |
|---|---|---|
| Ingesta | Un HSB con cola en hilo de segundo plano y estado en las bases | Réplicas del HSB detrás de un balanceador y un broker (Kafka o RabbitMQ) particionado por sede |
| Datos | 2 PostgreSQL y 1 MongoDB, cada uno un nodo único | Réplicas de lectura en PostgreSQL; *replica set* en MongoDB (transacciones multi-documento y conmutación por fallo); Citus si una sede crece a millones de atenciones |
| FHIR | Una instancia de HAPI con su base embebida por defecto | HAPI respaldado por PostgreSQL y en más de una instancia |
| Seguridad | JWT HS256 con usuarios de prueba en código | Proveedor de identidad (Keycloak/OIDC), TLS entre servicios y autenticación en los endpoints del HSB |
| Auditoría | Cadena SHA-256 en `pg_central` | Anclaje periódico del último hash en Hyperledger Fabric (bonus no hecho) |
| Despliegue | Docker Compose; manifiestos para Minikube en `infra/k8s/` | Autoescalado del HSB por tamaño de cola |

**Qué escalar primero ante 100× más mensajes:** el HSB. Hoy entrega de forma síncrona el primer
intento y tiene un solo hilo de reintentos por proceso. Lo primero sería poner un broker delante
para responder `202` de inmediato y repartir el trabajo entre varias réplicas del HSB; luego HAPI
(más instancias sobre PostgreSQL), y por último las bases de cada sede.

**Cumplimiento.** Solo datos sintéticos (también los códigos REPS). Ley 1581 de 2012: el paciente ve
quién accedió a su historia (finalidad y acceso); la auditoría encadenada impide reescribir sin
dejar rastro; el admisionista no ve datos clínicos (mínimo privilegio). Resolución 866 de 2021: los
57 campos están en el catálogo y se mide su cobertura.

---

## 10. Interoperabilidad basada en datos

**Pilar técnico (demostrado).** Tres formatos de entrada (HL7 v2 en texto enviado por HTTP POST, CSV con `;`,
JSON) y una salida estándar (FHIR R4 por REST, Bundle `transaction`). Las vistas y los legados no
comparten base: todo pasa por el HSB y la API. Dos motores de base con modelos distintos se integran
a través del registro canónico.

**Pilar semántico (demostrado).** CIE-10 en Condition y LOINC en Observation; los textos locales del
CSV se convierten a CIE-10 con `05_ref_terminologia.csv` y lo que no se puede mapear se rechaza con
motivo. Los dominios de la Res. 866 (tipo de documento, entorno, vía de ingreso, triage, condición
de salida…) se normalizan con tablas de sinónimos, de modo que `E` (HL7), `EMER` o `01` significan
lo mismo.

Ejemplo de un campo de punta a punta, el **14, municipio de residencia (DANE)**:

| Paso | Representación |
|---|---|
| HL7 v2 | `PID-11.9` (noveno componente de la dirección), p. ej. `70001` |
| Registro canónico | `usuario.municipio_residencia = "70001"` |
| PostgreSQL (sedes 1 y 3) | `usuario.municipio_residencia VARCHAR(5)` |
| MongoDB (sede 2) | `pacientes.residencia.municipio_dane` |
| FHIR R4 | `Patient.address[0].district` |

**Pilar organizacional (solo se menciona).** Acuerdos entre las IPS sobre los segmentos Z, los
códigos locales y la gobernanza de la tabla de terminología; el gobierno de datos se evalúa en
Arquitectura TI.

---

## 11. Resultados y discusión

Mediciones en Kali Linux (VirtualBox, 3,8 GB de RAM, Docker 28) el 10 y 11 de noviembre de 2026.

| Prueba | Resultado medido |
|---|---|
| Arranque limpio (`down -v && up -d --build`) | Todos los contenedores arriba; HAPI responde a los 85–95 s |
| Cobertura FHIR antes de enviar mensajes | 0 % en las 3 sedes |
| Ejemplo 01 (ADT^A01, sede 2 MongoDB) | Entregado |
| Ejemplo 01 reenviado | `duplicado`; exactamente 1 Patient 1007 en HAPI y 1 documento en MongoDB |
| Ejemplo 02 (ORU^R01, sede 1 PostgreSQL) | Entregado; Observation 718-7 = 13,8 g/dL |
| Ejemplo 03 (inválido) | Rechazado con 3 motivos |
| Ejemplo 04 (CSV, sede 3) | 3 entregados (1008, 1009, 1010) y 2 rechazados |
| Mensaje HL7 de 57 campos (`tests/datos/06_adt_a03_57_campos_sede1.hl7`) | 11 recursos FHIR; 56 de 57 campos; 100 % de obligatorios. Falta solo el 42 (diagnóstico de muerte) porque el paciente sale vivo |
| Cobertura FHIR por sede después de los ejemplos | Sede 1: 50 % → 67 % (tras el mensaje de 57 campos); sede 2: 33,3 %; sede 3: 75 % |
| Consulta unificada del paciente 1001 (3 sedes, 2 motores) | 52 de 57 campos; 100 % de obligatorios |
| Bundle de 1001 en HAPI `$validate` | 26 recursos; 0 errores, 33 advertencias, 46 mensajes informativos |
| HAPI apagado al enviar un mensaje | Respuesta `reintentando`; 7 intentos con esperas de 2 a 64 s; entregado solo 129,5 s después del primer intento; sin duplicado |
| `docker stop mongo_sede2` | La consulta responde con sedes 1 y 3, `reporte_completo = false`, `/health` DEGRADED 2/3; se recupera al iniciar el contenedor |
| `UPDATE evento_auditoria SET usuario_sistema='intruso' WHERE indice = 3` | El verificador señala el índice 3: "Alteración de contenido" |
| Paciente pide la historia de otro paciente | 403 y evento `ACCESO_DENEGADO` |
| ACID en PostgreSQL (`db/demo_acid.sql`) | Violación de `CHECK` en `clasificacion_triage` → rollback completo |
| Reinicio del bus con mensajes pendientes | Recuperó 2 mensajes pendientes y los entregó |
| Pruebas automatizadas | 36 de 36 pasan |

**Composición del lote de ejemplos oficiales.** Los ejemplos 01 (dos veces), 02, 03 y las 5 filas
del CSV son 9 mensajes recibidos: 5 entregados, 1 duplicado y 3 rechazados. Los 3 rechazos
(33 %) son los que el contrato de `ejemplos/LEEME.md` exige rechazar; ningún mensaje válido quedó
MUERTO en el flujo normal.

**Lo que no se midió.** No se midió de forma sistemática la latencia por mensaje entregado al primer
intento ni los mensajes por minuto bajo carga. El HSB expone `latencia_media_ms`,
`mensajes_ultimo_minuto` y `porcentaje_fallidos` en `/metrics`, pero son contadores en memoria de
una sesión de demostración, no una prueba de carga; por eso no se reportan como resultado.

**Discusión.**
- La cobertura FHIR por sede **no llega al 100 %** porque se mide como pacientes con recurso en HAPI
  sobre pacientes de la sede, y los pacientes sembrados como "legados" solo se enlazan cuando llega
  un mensaje suyo. Falta un paso de migración que reenvíe por el bus a todos los pacientes
  existentes (trabajo futuro).
- La cobertura de campos muestra el límite de los datos y no del traductor: el mensaje completo
  llega a 56/57; la historia real de 1001 llega a 52/57 porque sus atenciones no traen todos los
  opcionales.
- El reintento confirma que la idempotencia es lo que hace seguro repetir: 7 intentos, una sola
  entrega, ningún duplicado, sin coordinación distribuida (2PC). Esto coincide con los patrones de
  receptor idempotente y canal de mensajes muertos de Hohpe y Woolf (2003).
- Las 33 advertencias de `$validate` vienen de que el proyecto usa extensiones y sistemas de códigos
  propios (`minsalud.gov.co/...`) que HAPI no puede resolver; no son errores de estructura.

---

## 12. Conclusiones

1. Se puede unificar la historia de tres sedes **sin reemplazar sus legados ni igualar sus
   motores**: un registro canónico de 57 campos y un repositorio con una sola interfaz bastaron para
   tratar PostgreSQL y MongoDB igual desde el bus y la consulta.
2. Elegir disponibilidad en la lectura (AP) mantuvo la atención en marcha con una sede caída, a
   cambio de un reporte marcado como incompleto.
3. Ids deterministas, `PUT` en FHIR y UPSERT en las sedes hicieron idempotente la entrega; con eso,
   los reintentos y la recuperación tras reinicio no necesitan transacción distribuida.
4. Separar la auditoría en `pg_central` permitió apagar cualquier sede sin perder trazabilidad y
   demostrar la detección de una alteración hecha directamente en la base.

### Limitaciones

- MongoDB corre sin *replica set*: sin transacciones multi-documento ni conmutación por fallo.
  Además `guardar` lee el documento y lo reemplaza; dos escrituras simultáneas sobre el mismo
  paciente podrían pisarse (no hay control de concurrencia optimista).
- Una sola instancia de HAPI FHIR, con su base embebida por defecto.
- Los segmentos Z (`ZPI`, `ZPV`, `ZRX`, `ZEG`) son una convención del proyecto, no un estándar
  nacional.
- Códigos REPS de prestador sintéticos; extensiones FHIR con URLs propias, no perfiles publicados.
- Cobertura FHIR por sede sin paso de migración de los pacientes existentes.
- Latencia y mensajes por minuto no medidos de forma sistemática.
- Los endpoints del HSB (`:8001`) no exigen autenticación; solo la API la exige.
- Usuarios de prueba definidos en código; secreto JWT de desarrollo si no se cambia en `.env`.

### Trabajo futuro

- *Replica set* de MongoDB y control de versión del documento para escrituras concurrentes.
- Script de migración que pase a todos los pacientes legados por `/hsb/json` (cobertura FHIR 100 %).
- Prueba de carga para medir latencia, mensajes por minuto y porcentaje de fallidos.
- Keycloak/OIDC, TLS y autenticación en el HSB.
- Anclaje de la cadena de auditoría en Hyperledger Fabric; Prometheus y Grafana.
- Pipeline de CI que corra las 36 pruebas en cada *push*.

---

## Referencias (APA 7)

Bender, D., & Sartipi, K. (2013). HL7 FHIR: An agile and RESTful approach to healthcare information exchange. En *Proceedings of the 26th IEEE International Symposium on Computer-Based Medical Systems* (pp. 326–331). IEEE. https://doi.org/10.1109/CBMS.2013.6627810

Centro Nacional en Sistemas de Información en Salud. (2022). *Guía de interoperabilidad clínica con HL7 FHIR en redes asistenciales*. CENS.

HAPI FHIR Community. (2024). *HAPI FHIR: The open source FHIR API for Java* (versión 7.2.0). Smile Digital Health. https://hapifhir.io

<!-- verificar acceso: confirmar que el equipo abrió la especificación antes de entregar -->
HL7 International. (2019). *FHIR Release 4 (v4.0.1)*. https://hl7.org/fhir/R4/

Hohpe, G., & Woolf, B. (2003). *Enterprise integration patterns: Designing, building, and deploying messaging solutions*. Addison-Wesley.

Ministerio de Salud de la Nación Argentina. (2020). *Estrategia nacional de salud digital: Guía de implementación del Perfil Argentino de FHIR*. Ministerio de Salud de la Nación.

Ministerio de Salud y Protección Social. (2021). *Resolución 866 de 2021: Por la cual se reglamenta el conjunto de elementos de datos clínicos relevantes para la interoperabilidad de la historia clínica en el país*. MinSalud.

NextGen Healthcare. (2023). *Mirth Connect integration engine technical reference guide*. NextGen Healthcare.

OpenHIE Consortium. (2022). *Open Health Information Mediator (OpenHIM) architecture specification*. Jembi Health Systems.

Tanenbaum, A. S., & Van Steen, M. (2017). *Distributed systems* (3.ª ed.). Maarten van Steen.

---

## Anexos

### A. Código clave

| Archivo | Qué contiene |
|---|---|
| `traductor/catalogo_57.py` | Catálogo de los 57 campos (HL7 / CSV / PostgreSQL / MongoDB / FHIR) |
| `traductor/dominios.py` | Dominios y sinónimos |
| `traductor/traductor.py` | Traducciones al y desde el registro canónico, derivados y cobertura |
| `fhir/normalizer.py` | Registro canónico → Bundle FHIR R4 |
| `hsb/ingesta.py`, `hsb/queue_manager.py`, `hsb/main.py` | Flujo del bus, cola de reintentos, endpoints |
| `db/repositorio.py`, `db/consulta_unificada.py` | Repositorios PostgreSQL / MongoDB y consulta en paralelo |
| `db/schema.sql`, `db/sede2/init-mongo.js`, `db/central/init.sql` | Esquemas y datos sintéticos |
| `app/main.py`, `app/rbac.py`, `app/audit.py` | API, permisos, auditoría encadenada |

### B. Pruebas

- Automatizadas: `python -m pytest tests/ -v` (36 pruebas; ver §6).
- En vivo: guion de demostración (`docs/guion_demostracion.md`) y guía de Kali
  (`docs/guia_kali_linux.md`).
- Mensaje de 57 campos: `tests/datos/06_adt_a03_57_campos_sede1.hl7`.

### C. Documentos relacionados

- Mapeo completo: [`mapeo_57_campos.md`](mapeo_57_campos.md)
- Tabla de mapeo de la Fase 1: [`fase1/arquitectura/tabla_mapeo_campos.md`](fase1/arquitectura/tabla_mapeo_campos.md)
- Bitácora y uso de IA: [`bitacora.md`](bitacora.md)
