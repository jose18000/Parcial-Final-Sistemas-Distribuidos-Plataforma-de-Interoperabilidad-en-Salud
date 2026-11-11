# Informe Fase 2 — Plataforma Distribuida de Interoperabilidad Clínica
## Capa de Datos Distribuidos, Normalización FHIR R4 y Resiliencia ACID

**Autores:**
- Jose Guillermo Canchila (A) — Responsable: esquema distribuido, HAPI FHIR y demostración ACID
- Sharit Javier Manjarrez (B) — Responsable: normalizador FHIR R4, estado del arte (8 fuentes) e identidad

**Curso:** Sistemas Distribuidos · Parcial Final  
**Fecha:** Noviembre 2026  
**Versión del informe:** Fase 2 de 5

> **Actualización v2 (10–11 de noviembre de 2026).** Corrección registrada en la bitácora: el
> esquema de la v1 cubría unos 15 de los 57 campos y las tres sedes usaban el mismo motor. Desde la
> v2, el esquema relacional cubre los 57 campos de la Res. 866 de 2021, la **Sede 2 (Cartagena) es
> MongoDB** (`mongo_sede2`) y la auditoría vive en `pg_central`. Las líneas afectadas abajo están
> marcadas con "v2". Ver el [informe final](../informe_final_v7.md).

---

## 1. Decisión de Distribución y Justificación Teórica (Teorema CAP)

Para este proyecto se seleccionó la estrategia de **un nodo de base de datos independiente por sede** (Sincelejo en `:5433`, Cartagena en `:5434` y Corozal en `:5435` en la v1; desde la v2 Cartagena es MongoDB en `:27018`), en lugar de consolidar un único clúster monolítico o delegar en sharding sintético con Citus.

### 1.1 Alineación con el Patrón de Consulta y la Soberanía de Datos
En una red de IPS real, cada sede hospitalaria opera con autonomía legal y asistencial: los pacientes que ingresan por urgencias en Cartagena son atendidos por médicos de esa sede, registrando signos vitales y formulaciones con alta concurrencia local. Si la red WAN entre ciudades sufre intermitencias, la sede local no puede detener la admisión ni los egresos clínicos. Por tanto, la clave de fragmentación natural es la **sede de atención (`sede_id`)**, que coincide en un 95 % con el patrón de escritura y consulta inmediata.

### 1.2 Análisis frente al Teorema CAP (Brewer)
Frente al teorema CAP, la arquitectura adopta un modelo **AP (Alta Disponibilidad y Tolerancia a Partición)** a nivel de red WAN, garantizando **ACID estricto** a nivel intra-nodo:
- **Consistencia Sacrificada ($C$):** Se renuncia a la consistencia transaccional global inmediata (como el protocolo *Two-Phase Commit* - 2PC, que bloquearía todas las sedes si una está inaccesible). En su lugar, se asume consistencia eventual coordinada por el HSB y el servidor central FHIR.
- **Disponibilidad Garantizada ($A$):** Si el enlace con la sede de Corozal colapsa o su contenedor falla, Sincelejo y Cartagena continúan recibiendo admisiones y consultando historias clínicas.
- **Tolerancia a Particiones ($P$):** La partición de red es inevitable en infraestructuras geográficamente dispersas (costa caribe colombiana). La consulta unificada responde de manera transparente con las sedes disponibles y etiqueta la respuesta con un aviso explícito de incompletitud.

---

## 2. Estado del Arte (8 Fuentes Verificables)

A continuación se analizan 8 fuentes académicas e industriales de ámbito global, latinoamericano y colombiano que evalúan tecnologías de integración en salud.

| ID | Referencia / Fuente | Ámbito | Tecnologías Analizadas | Conclusiones Relevantes para el Proyecto |
|---|----------------------|--------|------------------------|------------------------------------------|
| **F1** | Bender, D., & Sartipi, K. (2013). *HL7 FHIR: An Agile and RESTful approach to healthcare information exchange*. IEEE CBMS. | Global | HL7 v2 vs FHIR R4 | Demuestra que la complejidad sintáctica de HL7 v2 y la proliferación de segmentos Z personalizados limitan la interoperabilidad semántica. FHIR R4 reduce el tiempo de desarrollo al emplear recursos JSON y operaciones REST estándar (PUT, POST, GET). |
| **F2** | HAPI FHIR Community / Smile Digital Health. (2024). *HAPI FHIR: The Open Source FHIR API for Java*. Documentation & Architecture Guide. | Global | HAPI FHIR Server | Valida a HAPI FHIR como el estándar de facto para almacenamiento, indización y validación transaccional (`/fhir/Bundle/$validate`) bajo especificación R4. Se destaca su capacidad de validar Perfiles e integrarse con bases relacionales. |
| **F3** | Hohpe, G., & Woolf, B. (2003 / 2020 ed.). *Enterprise Integration Patterns: Designing, Building, and Deploying Messaging Solutions*. Addison-Wesley. | Global | Apache Camel vs Enterprise Service Bus | Define formalmente los patrones *Scatter-Gather*, *Idempotent Receiver*, *Dead Letter Channel* y *Guaranteed Delivery*. Sustenta por qué una cola con reintentos exponenciales y clave de deduplicación previene la duplicación de pacientes en redes inestables. |
| **F4** | OpenHIE Consortium. (2022). *Open Health Information Mediator (OpenHIM) Architecture Specification*. Jembi Health Systems. | Global / Países en Desarrollo | OpenHIM vs Mirth Connect | Analiza la intermediación de interoperabilidad clínica en redes públicas. OpenHIM ofrece excelente registro de auditoría y mediación REST, pero su acoplamiento con MongoDB y menor flexibilidad para parsers directos HL7 v2 en texto plano favorece una implementación ligera en FastAPI para equipos reducidos. |
| **F5** | NextGen Healthcare. (2023). *Mirth Connect Integration Engine Technical Reference Guide*. | Global | Mirth Connect (NextGen) | Reconoce a Mirth Connect como líder para transformación de mensajes legados HL7 v2 a través de canales visuales. Sin embargo, su consumo de recursos (JVM separada >1.5 GB de RAM) y gestión basada en GUI propietaria dificulta el despliegue headless nativo en un `docker-compose` mínimo de aula. |
| **F6** | Ministerio de Salud y Protección Social de Colombia. (2021). *Resolución 866 de 2021: Por la cual se reglamenta el conjunto de datos de la Historia Clínica Electrónica y su interoperabilidad*. Bogotá D.C. | Colombia | Regulación Nacional (Minsalud) | Establece la obligatoriedad de interoperabilidad para todas las IPS colombianas, exigiendo identificador unívoco de usuario (Cédula de Ciudadanía, etc.) y codificación clínica obligatoria bajo CIE-10 para morbilidad y codificación de procedimientos. Fundamenta las reglas de negocio de nuestro normalizador. |
| **F7** | Ministerio de Salud de la Nación Argentina. (2020). *Estrategia Nacional de Salud Digital: Guía de Implementación del Perfil Argentino de FHIR*. Buenos Aires. | Latinoamérica | Implementación Regional FHIR | Documenta la creación del bus de interoperabilidad federado en Argentina. Demuestra que el uso de `Bundle` de tipo `transaction` con identificadores deterministas derivados del documento nacional resuelve la coexistencia de registros duplicados en diferentes provincias/sedes. |
| **F8** | Centro Nacional en Sistemas de Información en Salud (CENS - Chile). (2022). *Guía de Interoperabilidad Clínica con HL7 FHIR en Redes Asistenciales*. Santiago de Chile. | Latinoamérica | FHIR Core + LOINC | Evidencia que el empleo conjunto de códigos LOINC para resultados de laboratorio y CIE-10 para motivos de consulta en recursos `Observation` y `Condition` reduce en un 83 % las discrepancias interpretativas entre centros hospitalarios rurales y urbanos. |

### 2.1 Comparación Tecnológica: Motores de Interoperabilidad

| Criterio | HAPI FHIR R4 | Mirth Connect | OpenHIM | Bus Propio (FastAPI + Worker) |
|----------|--------------|---------------|---------|--------------------------------|
| **Compatibilidad FHIR R4** | Nativa (Servidor de referencia) | Vía plugins / scripts JS | Mediador REST / passthrough | Cliente REST sobre HAPI |
| **Parser HL7 v2** | Requiere librerías HAPI HL7 | Nativo visual de arrastrar | Vía mediadores externos | Parser modular determinista en Python |
| **Curva de Aprendizaje** | Media (Java / REST) | Media-Alta (GUI, JavaScript Rhino) | Media (Node.js / Express) | Baja (Python nativo, tipado pydantic) |
| **Consumo de Memoria** | ~600 MB - 1 GB | >1.5 GB JVM | ~500 MB Node | <100 MB |
| **Observabilidad** | `/fhir/metadata`, métricas Spring | Dashboard GUI cerrado | Interfaz web de transacciones | `/health` y `/metrics` estándar Prometheus |
| **Licenciamiento** | Apache 2.0 (Open Source) | Mozilla Public License | MPL 2.0 | MIT / Propietario del equipo |

---

## 3. Solución Propuesta (Capa de Datos y Normalización)

### 3.1 Infraestructura en Docker Compose
Se implementó un entorno orquestado con 4 contenedores principales en red compartida:
- `pg_sede1` (Sincelejo): PostgreSQL 16 Alpine en puerto `5433` con base `clinica_sincelejo`.
- `pg_sede2` (Cartagena): PostgreSQL 16 Alpine en puerto `5434` con base `clinica_cartagena`. **v2:** reemplazado por `mongo_sede2` (MongoDB 7, puerto `27018`, misma base `clinica_cartagena`, un documento por paciente con las atenciones embebidas; `db/sede2/init-mongo.js`).
- `pg_sede3` (Corozal): PostgreSQL 16 Alpine en puerto `5435` con base `clinica_corozal`.
- `hapi-fhir` (Servidor FHIR): Contenedor oficial `hapiproject/hapi:v7.2.0` en puerto `8090`.

Cada nodo PostgreSQL cuenta con volumen dedicado (`pg_data_sede1`, `pg_data_sede3`) y healthcheck con `pg_isready`; MongoDB usa `mongo_data_sede2` y un healthcheck con `mongosh`. En la v2 se agregó `pg_central` para la auditoría.

### 3.2 Esquema Relacional Unificado
Los nodos PostgreSQL (sedes 1 y 3) aplican el mismo contrato DDL (`db/schema.sql`, ampliado en la v2 a los 57 campos de la Res. 866); la sede 2 guarda los mismos datos con otra forma y otros nombres en MongoDB, y el traductor universal (`traductor/`) convierte entre ambos. El esquema relacional está estructurado en:
1. `usuario`: Documento, nombres, sexo, fecha de nacimiento, sede origen y `fhir_patient_id` (inicia en `NULL`, marcando 0 % de cobertura FHIR inicial).
2. `atencion`: Número de visita (clave primaria), clase (`EMER`, `AMB`, `IMP`), fecha ingreso/egreso, triage y estado.
3. `diagnostico`: Vinculado a la visita con código CIE-10 validado y descripción clínica.
4. `tecnologia_salud`: Procedimientos y laboratorios vinculados con código LOINC, valor numérico y unidad de medida.
5. `egreso`: Sello SHA-256 de integridad médica y destino del paciente.
6. `mensaje_bus`: ciclo de vida de los mensajes del bus. (v2: `evento_auditoria` se movió a la base central `pg_central`.)

### 3.3 Normalizador Determinista a FHIR R4 (`fhir/normalizer.py`)
El módulo desarrollado garantiza las siguientes propiedades:
1. **Identificadores Deterministas:**
   - Paciente: `pac-{documento_id}` (ej. `pac-1001`).
   - Encuentro: `enc-{numero_visita}` (ej. `enc-V-S1-0150`).
   - Condición: `cond-{numero_visita}-{rol}-{cie10}` (ej. `cond-V-S1-0150-ing-I10`; v2 agrega el rol del diagnóstico).
   - Observación: `obs-{numero_visita}-{loinc}` (ej. `obs-V-S1-0150-718-7`).
   - v2 agrega MedicationRequest (`med-…`), Practitioner (`prac-…`), Organization (`org-sede-N`) y AllergyIntolerance (`alg-…`).
2. **Bundle Transaction con Método PUT:**
   Cada entrada del Bundle contiene `request: { method: "PUT", url: "<Tipo>/<ID>" }`. Esto significa que si el mensaje se reenvía 10 veces, HAPI FHIR actualiza el recurso determinista sin duplicar pacientes ni atenciones.
3. **Consistencia Referencial:** Todas las referencias (`Encounter.subject`, `Condition.encounter`, etc.) apuntan a recursos existentes dentro del mismo Bundle.

---

## 4. Identidad entre Sedes y Caso de Fallo Documentado

### 4.1 Regla de Coincidencia
La unificación de historias clínicas adopta la regla de **identidad unívoca por número de documento exacto (`documento_id`)**:
$$\text{Paciente}_A \equiv \text{Paciente}_B \iff \text{usuario.documento\_id}_A = \text{usuario.documento\_id}_B$$

En nuestros datos sintéticos, el paciente **Carlos Pérez (documento `1001`)** cuenta con registros en:
- **Sede 1 (Sincelejo):** Atención de urgencia `V-S1-0150` con diagnóstico `I10` (Hipertensión) y presión arterial sistólica (`8480-6`); la Hemoglobina (`718-7`) llega con el ejemplo `02`.
- **Sede 2 (Cartagena):** Control ambulatorio `V-S2-0080` con diagnóstico `J45.9` (Asma) y PCR (`1988-5`).
- **Sede 3 (Corozal):** Consulta ambulatoria `V-S3-0045` con diagnóstico `A09` (Gastroenteritis) y electrolitos (`2951-2`).

La consulta unificada (`db/consulta_unificada.py`) ejecuta un *fan-out* concurrente sobre los 3 nodos (desde la v2, dos PostgreSQL y un MongoDB, a través de `db/repositorio.py`) y agrupa cronológicamente todas las atenciones bajo un único expediente clínico consolidado.

### 4.2 Documentación de Caso de Fallo por Error de Digitación
La coincidencia exacta por documento presenta vulnerabilidades críticas en entornos legados sin validación estricta de entrada:
1. **Error de Digitación Tipográfico:** Si el admisionista de Corozal registra por error `10001` (un cero adicional) en lugar de `1001`, el sistema considerará a este paciente como una persona diferente. La consulta unificada del paciente `1001` omitirá por completo la atención de Corozal.
2. **Ausencia de Tipo de Documento:** Si un ciudadano extranjero tiene cédula de extranjería número `1001` y un nacional tiene cédula de ciudadanía `1001`, la coincidencia sólo por número generaría **colisión de identidades** (unificación errónea de dos pacientes distintos).
3. **Mitigación Diseñada:** En la Fase 3, el validador del HSB valida la longitud (4 a 15 dígitos) y caracteres estrictamente numéricos antes de admitir cualquier mensaje, y en la Fase 5 la vista de admisionista avisa cuando el mismo documento tiene nombre, fecha de nacimiento o sexo distintos entre sedes (`inconsistencias_entre_sedes`).

---

## 5. Demostración de Transacción Atómica (ACID)

En el script `db/demo_acid.sql` se demuestra la propiedad de **Atomicidad ($A$)** en PostgreSQL ante fallos de integridad:

```sql
BEGIN;
-- Inserción válida de usuario
INSERT INTO usuario (documento_id, tipo_documento, nombre_completo, fecha_nacimiento, sexo, sede_origen_id)
VALUES ('9999', 'CC', 'Paciente Prueba Fallo', '1995-01-01', 'M', 1);

-- Inserción inválida: triage=99 viola la restricción CHECK (triage BETWEEN 1 AND 5)
INSERT INTO atencion (numero_visita, clase_atencion, fecha_ingreso, triage, documento_id, sede_id)
VALUES ('V-TEST-FAIL', 'E', NOW(), 99, '9999', 1);

COMMIT;
```

### Resultado Verificado
1. **Antes:** `SELECT * FROM usuario WHERE documento_id='9999'` devuelve 0 filas.
2. **Ejecución:** El motor lanza el error `ERROR: new row for relation "atencion" violates check constraint "atencion_triage_check"`.
3. **Después:** PostgreSQL aborta la transacción y revierte todos los cambios. Al consultar `usuario` y `atencion`, **no existe ningún registro parcial del paciente 9999**. La base de datos permanece en un estado íntegro y consistente.

---

## 6. Respuesta a la Pregunta de Autoevaluación

> **Pregunta:** ¿Qué pasa con la transacción si el nodo de base de datos cae justo después del `COMMIT` pero antes de responder al cliente? ¿Cómo lo detecta su bus?

**Respuesta Arquitectural:**

1. **En el nodo de Base de Datos (Durabilidad - $D$ de ACID):**
   Dado que el motor ya ejecutó el `COMMIT` y escribió el registro en el *Write-Ahead Log* (WAL) en disco antes de la caída, los datos **están permanentemente guardados**. Cuando el contenedor vuelva a levantar, el proceso de *crash recovery* de PostgreSQL leerá el WAL y confirmará que la transacción fue confirmada.

2. **En el cliente / Bus de Servicios (HSB):**
   Como la conexión de red se interrumpió antes del *acknowledge* (ACK) de red, el HSB recibe un error de socket (`ConnectionResetError` o `Timeout`). Desde la perspectiva del bus, **el estado de la entrega es incierto**.

3. **Mecanismo de Detección y No-Duplicación:**
   - El bus marca el mensaje como `REINTENTANDO` en `mensaje_bus` y programa un nuevo intento con espera exponencial (v2: 2 s, 4 s, 8 s, 16 s, 32 s, 64 s, hasta 7 intentos).
   - Cuando el nodo vuelve y el bus reintenta el envío, entra en juego la **idempotencia**:
     - En HAPI FHIR, el `PUT` sobre `Patient/pac-<doc>` y `Encounter/enc-<visita>` sobreescribe exactamente el mismo recurso determinista sin crear filas duplicadas.
     - En el nodo de la sede, los datos clínicos se guardan con UPSERT por llaves deterministas (`ON CONFLICT (documento_id)`, `(numero_visita)`, `(diagnostico_id)`, `(tecnologia_id)` en PostgreSQL; `replace_one` por `_id` en MongoDB): si el `COMMIT` ya había ocurrido, el reintento reescribe lo mismo. `mensaje_bus` (con `hash_contenido` único) evita además que un reenvío del emisor se procese como nuevo.

---

## 7. Checklist de Cumplimiento de Fase 2

| Requisito / Entregable | Estado | Evidencia |
|------------------------|--------|-----------|
| docker-compose con un nodo por sede y HAPI FHIR (:8090) — v2: PostgreSQL :5433, MongoDB :27018, PostgreSQL :5435 | ✅ Completo | `docker-compose.yml` |
| Esquema relacional homogéneo de 8 tablas | ✅ Completo | `db/schema.sql` |
| Scripts de inicialización y datos sintéticos con `fhir_patient_id` NULL (cobertura 0 %) | ✅ Completo | `db/sede1/init.sql`, `db/sede2/init-mongo.js` (v2), `db/sede3/init.sql` |
| Paciente con atenciones en las 3 sedes (Carlos Pérez - doc: 1001) | ✅ Completo | Datos presentes en las tres sedes |
| Normalizador a Bundle transaction FHIR R4 con IDs deterministas y PUT | ✅ Completo | `fhir/normalizer.py` |
| Pruebas unitarias del normalizador (mínimo 5 casos, incluye inválido) | ✅ Completo | `tests/fase2/test_normalizer.py` (v2: 8 casos) y `tests/fase2/test_traductor_57.py` (10 casos) |
| Bundle FHIR representativo con recursos Patient, Encounter, Condition y Observation | ✅ Completo | `docs/fase2/bundle_valido.json` |
| Script de consulta unificada distribuida con soporte de tolerancia a fallos | ✅ Completo | `db/consulta_unificada.py` |
| Script de prueba de atomicidad ACID con rollback demostrado | ✅ Completo | `db/demo_acid.sql` |
| Justificación CAP, Estado del arte con 8 fuentes y respuesta de autoevaluación | ✅ Completo | Secciones 1, 2 y 6 de este informe |

