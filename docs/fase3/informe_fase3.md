# Informe Fase 3 — Plataforma Distribuida de Interoperabilidad Clínica
## Health Service Bus (HSB), Middleware de Integración e Interoperabilidad Semántica

**Autores:**
- Jose Guillermo Canchila (A) — Responsable: Arquitectura del HSB, endpoints FastAPI, cola de reintentos y Dockerfile
- Sharit Javier Manjarrez (B) — Responsable: Parsers HL7/CSV, tabla de terminologías, validaciones y pruebas de integración

**Curso:** Sistemas Distribuidos · Parcial Final  
**Fecha:** Noviembre 2026  
**Versión del informe:** Fase 3 de 5 (Ponderación: 1,25 / 5,0)

> **Actualización v2 (10–11 de noviembre de 2026).** Correcciones registradas en la bitácora: los
> reintentos bloqueaban la petición y con HAPI caído más de un minuto la prueba terminaba en MUERTO;
> reentregar un mensaje podía duplicar diagnósticos. Desde la v2: el bus traduce primero con el
> **traductor universal de 57 campos** y luego verifica idempotencia y valida; la cola es persistente
> con un hilo de reintentos en segundo plano (2 → 64 s, 7 intentos); los errores de datos van directo
> a MUERTO; hay entrada `/hsb/json`; la Sede 2 es MongoDB. Las líneas afectadas abajo están marcadas
> con "v2". Ver el [informe final](../informe_final_v7.md) y el
> [diagrama de estados](../fase1/diagramas/04_estados_mensaje.md).

---

## 1. Selección y Justificación de la Herramienta del Bus

Para la implementación del Health Service Bus (HSB), se evaluaron cuatro alternativas tecnológicas: un bus propio modular en FastAPI con backend relacional, Apache Camel, Mirth Connect (NextGen) y OpenHIM.

### Tabla Comparativa de Soluciones para el Bus

| Criterio | Bus Propio (FastAPI + Worker) | Mirth Connect | Apache Camel | OpenHIM |
|----------|--------------------------------|---------------|--------------|---------|
| **Compatibilidad HL7 v2 y FHIR R4** | **Alta**: Parser HL7 modular y cliente nativo HTTP/JSON hacia servidor HAPI FHIR R4. | **Nativa**: Canales especializados en HL7 v2/v3 y conectores FHIR. | **Nativa**: Componentes `camel-hl7` y `camel-fhir`. | **Media**: Mediador REST; requiere adaptadores externos para HL7 crudo. |
| **Curva de Aprendizaje** | **Baja**: Código en Python limpio, tipado estricto con Pydantic y pruebas directas con `pytest`. | **Media-Alta**: Interfaz gráfica obligatoria, JavaScript Rhino legado y gestión de canales XML. | **Alta**: Requiere dominio profundo de Java, DSL de Camel y configuración en Spring Boot. | **Media**: Configuración basada en consolas web y microservicios Node.js. |
| **Observabilidad y Métricas** | **Nativa**: Endpoints `/health` y `/metrics` compatibles con Prometheus y alertas de mensajes muertos. | Interfaz gráfica cerrada; métricas expuestas requieren licencias o plugins comerciales. | Muy buena mediante JMX y Micrometer/Prometheus. | Dashboard web enfocado en auditoría de canales. |
| **Consumo de Recursos** | **Muy bajo (<90 MB)**: Ideal para ejecución integral en `docker-compose` de aula sin saturar RAM. | **Alto (>1.5 GB)** por instancia de JVM Java en ejecución continua. | **Alto (~800 MB - 1.2 GB)** sobre JVM. | **Medio (~500 MB)** con dependencia de MongoDB. |
| **Licenciamiento** | Abierto (código del equipo bajo MIT). | MPL 2.0 (con extensiones comerciales cerradas). | Apache 2.0. | MPL 2.0. |

**Justificación:** Se seleccionó el **Bus Propio sobre FastAPI** porque garantiza transparencia de código (ambos integrantes pueden explicar y modificar cada función en vivo), consumo mínimo de recursos, pruebas unitarias automatizables en segundos y control absoluto sobre la lógica de reintentos con backoff exponencial e idempotencia estricta.

---

## 2. Arquitectura Interna del HSB y Puertas de Entrada

El HSB actúa como mediador central desacoplado entre los sistemas legados y la capa de persistencia:

```
[ Sistema Legado ] ──(HL7 / CSV)──> [ POST /hsb/hl7 | POST /hsb/csv ]
                                            │
                                  [ Control de Idempotencia ]
                                     (SHA-256 en BD)
                                            │
                                 [ Validador Previo ] ──(Inválido)──> [ 422 Unprocessable ]
                                            │                            (Registra motivo)
                                 [ Normalizador FHIR R4 ]
                                 (Bundle transaction PUT)
                                            │
                                ┌───────────┴───────────┐
                                ▼                       ▼
                        [ 1. HAPI FHIR R4 ]     [ 2. Base de la sede ]
                            (Puerto 8090)           (Sede 1, 2 o 3)
                                │                       │
                        (Fallo: Reintentos)     (Persistencia Local)
```

### Endpoints Expuestos

1. `POST /hsb/hl7`: Acepta mensajes en texto plano HL7 v2 (`ADT^A01` para admisiones clínicas y `ORU^R01` para reportes de laboratorio).
2. `POST /hsb/csv?sede=N`: Ingesta por lotes de CSV legados delimitados por `;` para la sede especificada (1: Sincelejo, 2: Cartagena, 3: Corozal).
3. `GET /health`: Chequea el estado del HSB y la conectividad activa con HAPI FHIR y las tres sedes (v2: dos PostgreSQL y un MongoDB).
4. `GET /metrics`: Expone estadísticas operacionales en tiempo real.
5. `POST /hsb/reencolar/{mensaje_id}`: Permite a un operador reactivar un mensaje que quedó en estado `MUERTO`.
6. **v2:** `POST /hsb/json?sede=N` (registro JSON; lo usan las vistas de admisión y médico), `GET /hsb/mensajes` (monitor de estados de las 3 sedes) y `GET /hsb/catalogo` (los 57 campos y su mapeo).

---

## 3. Interoperabilidad Semántica y Tabla de Mapeo de Terminologías

La interoperabilidad semántica garantiza que el significado de los datos clínicos sea preservado inequívocamente entre sistemas heterogéneos.

### 3.1 Mapeo de Diagnósticos Locales a CIE-10 (`ejemplos/05_ref_terminologia.csv`)

| Diagnóstico Local (`dx_local`) | Código CIE-10 | Descripción Oficial CIE-10 | Recurso FHIR Generado |
|---------------------------------|---------------|----------------------------|-----------------------|
| `DIARREA` | `A09` | Diarrea y gastroenteritis de presunto origen infeccioso | `Condition.code` |
| `HIPERTENSION` | `I10` | Hipertensión esencial (primaria) | `Condition.code` |
| `DIABETES` | `E11.9` | Diabetes mellitus tipo 2 sin mención de complicación | `Condition.code` |
| `ASMA` | `J45.9` | Asma, no especificada | `Condition.code` |
| `INFECCION URINARIA` | `N39.0` | Infección de vías urinarias, sitio no especificado | `Condition.code` |
| `LUMBAGO` | `M54.5` | Lumbago no especificado | `Condition.code` |
| `NEUMONIA` | `J18.9` | Neumonía, no especificada | `Condition.code` |
| `CEFALEA` | `R51` | Cefalea | `Condition.code` |

> **Regla de Negocio:** Si un mensaje CSV contiene un `dx_local` ausente en esta tabla (por ejemplo, `DOLOR MISTERIOSO`), el registro se **rechaza inmediatamente** con el motivo `"diagnóstico sin mapeo a CIE-10: 'DOLOR MISTERIOSO'"`.

### 3.2 Mapeo de Procedimientos y Laboratorios a LOINC

| Código LOINC | Nombre / Descripción de la Prueba | Sistema / Muestra | Unidad Estándar | Recurso FHIR |
|--------------|-----------------------------------|-------------------|-----------------|--------------|
| `718-7` | Hemoglobina [Masa/volumen] | Sangre total | `g/dL` | `Observation` |
| `8480-6` | Presión arterial sistólica | Arterial sistémica | `mm[Hg]` | `Observation` |
| `1988-5` | Proteína C reactiva [Masa/volumen] | Suero o plasma | `mg/L` | `Observation` |
| `2951-2` | Sodio [Moles/volumen] | Suero o plasma | `mmol/L` | `Observation` |
| `2823-3` | Potasio [Moles/volumen] | Suero o plasma | `mmol/L` | `Observation` |

---

## 4. Resultados con los Archivos de Ejemplo Oficiales

La suite de pruebas de integración (`tests/fase3/test_hsb_integration.py`) verificó rigurosamente el comportamiento del HSB frente a los 4 archivos contractuales sin modificarlos:

| Archivo | Formato | Resultado Esperado | Resultado Obtenido en el HSB | Estado |
|---------|---------|--------------------|------------------------------|--------|
| `01_adt_a01_valido_sede2.hl7` | HL7 v2 ADT^A01 | **Entregado**: Patient 1007, Encounter y Condition J45.9 en Sede 2 | `200 OK` - Estado: `entregado`, `bundle_id`: `bundle-pac-1007`, `sede`: 2 | ✅ Cumplido |
| `02_oru_r01_laboratorio_sede1.hl7` | HL7 v2 ORU^R01 | **Entregado**: Observation LOINC 718-7 = 13,8 g/dL para paciente 1001 en Sede 1 | `200 OK` - Estado: `entregado`, Observation LOINC 718-7, valor: 13.8 g/dL | ✅ Cumplido |
| `03_adt_a01_invalido.hl7` | HL7 v2 ADT^A01 | **Rechazado** con exactamente 3 motivos | `422 Unprocessable Entity` con 3 motivos: (1) documento no numérico, (2) sexo no válido, (3) diagnóstico sin mapeo a CIE-10 | ✅ Cumplido |
| `04_sede3_legado.csv` | CSV delimitado por `;` | **3 entregados** (1008, 1009, 1010) y **2 rechazados** (1011 por dx sin mapeo y 12 por doc de 2 dígitos) | `total_filas`: 5, `entregados`: [1008, 1009, 1010], `rechazados`: [1011 (DOLOR MISTERIOSO), 12 (longitud 2)] | ✅ Cumplido |

---

## 5. Resiliencia, Idempotencia y Cola con Backoff Exponencial

### 5.1 Idempotencia Persistente
- Para mensajes HL7, la clave de unicidad combina el identificador de mensaje `MSH-10` y el hash SHA-256 de la carga útil completa.
- Al enviar `01_adt_a01_valido_sede2.hl7` por primera vez, el HSB responde `200 OK { "estado": "entregado" }`.
- Al reenviar el mismo archivo de inmediato, el HSB consulta la tabla `mensaje_bus`, detecta la preexistencia del hash y responde inmediatamente con `HTTP 200 { "estado": "duplicado", "motivo": "Mensaje recibido previamente: no se vuelve a crear el paciente ni la atención." }`. En la base de datos de Cartagena (MongoDB desde la v2) **sólo existe un documento del paciente 1007**, y en HAPI un solo `Patient/pac-1007`.

### 5.2 Cola de Reintentos y Mensajes Muertos (Dead Letter Queue)
Cuando el servidor HAPI FHIR se detiene temporalmente (`docker compose stop hapi-fhir`):
1. El HSB detecta la interrupción de conexión y asigna el estado `REINTENTANDO` (intento 1).
2. Aplica **espera creciente exponencial**:
   $$\text{Espera}(n) = \text{BASE} \times 2^{n-1}$$
   v1: base 1 s (1, 2, 4, 8 s) con la petición bloqueada. **v2:** base 2 s (`HSB_RETRY_BASE_SECONDS=2`) → 2, 4, 8, 16, 32, 64 s, en un hilo en segundo plano; la petición responde `202 reintentando` de inmediato.
3. Si el servicio HAPI FHIR se restablece (`docker compose start hapi-fhir`), el reintento se ejecuta con éxito, envía el Bundle con `PUT` y pasa a estado `ENTREGADO`.
4. Si se supera el límite de intentos sin éxito (v1: 4; **v2: 7**, `HSB_MAX_RETRIES`), el mensaje pasa a estado **`MUERTO`** (Dead Letter Queue), evitando ciclos infinitos de consumo de CPU. El mensaje queda preservado con su payload y motivo de fallo, y puede reactivarse mediante `POST /hsb/reencolar/{id}`.

---

## 6. Proceso de Desarrollo y Calidad de Software

1. **Diseño Inicial:** Modelado de estados del mensaje (Fase 1: RECIBIDO, VALIDADO, TRANSFORMADO, ENTREGADO, RECHAZADO, REINTENTANDO, MUERTO).
2. **Desarrollo Modular:** Desacoplamiento estricto entre el motor de parsing (`parser_hl7.py`, `parser_csv.py`), el validador de contratos clínicos (`validator.py`), el gestor transaccional (`queue_manager.py`) y la API web (`main.py`).
3. **Pruebas Automatizadas:** Ejecución automatizada de casos de prueba unitarios e integrados que aseguran que ningún fallo pase silencioso ni corrompa el almacenamiento.

---

## 7. Respuesta a la Pregunta de Autoevaluación

> **Pregunta:** Si el bus se cae justo después de enviar el Bundle a HAPI pero antes de guardar en el nodo de la sede, ¿qué ocurre al reiniciar el bus? ¿Por qué su diseño no duplica registros?

**Respuesta Técnica:**

1. **Estado en el momento de la caída:**
   - HAPI FHIR ya recibió y almacenó los recursos `Patient/pac-<doc>`, `Encounter/enc-<visita>`, `Condition/cond-<visita>-<cie10>`.
   - En el nodo PostgreSQL de la sede destino, la transacción local aún no fue ejecutada ni confirmada.
   - En el registro del HSB (`mensaje_bus`), el mensaje quedó registrado en estado intermedio (`TRANSFORMADO` o `REINTENTANDO`).

2. **Comportamiento al reiniciar el HSB:**
   - El HSB recupera los mensajes pendientes o recibe el reenvío por parte del sistema emisor legado.
   - El HSB retoma la secuencia programada: vuelve a intentar el envío a HAPI FHIR.
   - **Por qué NO duplica en HAPI FHIR:** El Bundle transaccional utiliza operaciones **`PUT` con identificadores deterministas** basados en el documento del paciente y el número de visita (`Patient/pac-1007`, `Encounter/enc-V-S2-0101`). En el estándar FHIR R4, un `PUT` sobre un recurso existente es estrictamente idempotente: actualiza el recurso con el mismo contenido sin generar nuevos identificadores autonuméricos.
   - **Por qué NO duplica en PostgreSQL:** Al completarse la llamada a HAPI, el bus ejecuta la inserción en el nodo de la sede utilizando UPSERT por llaves deterministas (`ON CONFLICT (documento_id)`, `(numero_visita)`, `(diagnostico_id)`, `(tecnologia_id)` `DO UPDATE` en PostgreSQL; `replace_one` por `_id` en MongoDB desde la v2). Al reiniciar, `recuperar_pendientes()` relee de las sedes los mensajes en `TRANSFORMADO` o `REINTENTANDO` y los vuelve a programar. El registro clínico se consolida de forma íntegra y el mensaje pasa formalmente a estado `ENTREGADO`.

