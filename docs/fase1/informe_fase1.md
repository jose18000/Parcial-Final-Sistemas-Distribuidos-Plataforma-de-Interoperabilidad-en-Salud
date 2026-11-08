# Informe Fase 1 — Plataforma Distribuida de Interoperabilidad Clínica
## Análisis, Modelado UML y Diseño de Arquitectura

**Título (≤16 palabras):** Plataforma distribuida de interoperabilidad clínica para una red de IPS con tres sedes

**Autores:**
- Jose Guillermo Canchila (A) — Responsable: diagramas UML, arquitectura
- Sharit Javier Manjarrez (B) — Responsable: marco teórico, tabla de mapeo, resumen

**Curso:** Sistemas Distribuidos · Parcial Final  
**Fecha:** Noviembre 2026  
**Versión del informe:** Fase 1 de 5

---

## 1. Resumen

> *[B — Sharit Manjarrez]*

Una red de IPS con sedes en Sincelejo, Cartagena y Corozal opera con sistemas legados independientes que emiten datos clínicos en formatos HL7 v2 y CSV. La historia clínica de un paciente queda fraccionada entre las tres sedes, impidiendo una visión unificada sin reemplazar los sistemas existentes. Este proyecto propone diseñar e implementar una plataforma distribuida de interoperabilidad clínica que integra los datos de las tres sedes mediante un bus de servicios de salud (HSB), los normaliza al estándar FHIR R4 y los expone a cuatro perfiles de usuario —paciente, admisionista, médico y auditor— con control de acceso basado en roles y auditoría encadenada por hash.

La metodología combina el análisis UML (casos de uso, secuencia, clases y estados), el diseño de una arquitectura de tres capas (ingesta, normalización y consulta), y el despliegue con un único comando Docker Compose. La plataforma es tolerante a fallos parciales: si una sede cae, las demás siguen disponibles y el reporte de historia clínica indica explícitamente la ausencia de datos de la sede no disponible. El sistema implementa idempotencia persistente en el bus, reintentos con backoff exponencial y validación estricta de terminologías (CIE-10, LOINC) antes de transformar cualquier mensaje.

Los resultados esperados al finalizar las cinco fases incluyen: cobertura FHIR del 100 % de los registros migrados, latencia media de consulta unificada inferior a 500 ms con las tres sedes disponibles, y verificación de integridad de auditoría ante alteración manual de registros.

*(229 palabras)*

---

## 2. Introducción y Objetivos

> *[B — Sharit Manjarrez]*

### 2.1 Problema

Los sistemas de información en salud de Colombia operan frecuentemente en silos: cada institución prestadora de servicios de salud (IPS) mantiene su propia base de datos, con formatos propietarios y sin interoperabilidad nativa entre sedes. Cuando un paciente es atendido en más de una sede, su historia clínica queda fraccionada. El médico que lo atiende en Corozal no puede ver —de manera automática— los antecedentes registrados en Sincelejo o Cartagena.

La Ley 1438 de 2011 y la Resolución 866 de 2021 del Ministerio de Salud de Colombia establecen la interoperabilidad como requisito para el sistema de salud, pero la adopción de estándares como HL7 FHIR es todavía incipiente, especialmente en IPS de mediano tamaño.

### 2.2 Objetivo General

Diseñar e implementar una plataforma distribuida de interoperabilidad clínica que unifique la historia clínica de pacientes atendidos en tres sedes de una red de IPS, integrando sus sistemas legados sin reemplazarlos.

### 2.3 Objetivos Específicos

1. **Ingerir** datos clínicos de al menos dos formatos de intercambio (HL7 v2 ADT/ORU y CSV con separador `;`) provenientes de las tres sedes, con validación de cada campo antes de la transformación.

2. **Normalizar** los registros ingresados al estándar FHIR R4 (recursos Patient, Encounter, Condition con CIE-10 y Observation con LOINC) como Bundle transaction válido, verificado con el endpoint `POST /fhir/Bundle/$validate` de HAPI FHIR.

3. **Garantizar** que una sola consulta a la API retorne la historia completa de un paciente con atenciones en las tres sedes, con tiempo de respuesta inferior a 500 ms cuando todas las sedes están disponibles, y respuesta parcial con aviso cuando alguna sede no responde.

4. **Proteger** el acceso mediante cuatro roles diferenciados (paciente, admisionista, médico, auditor) con auditoría encadenada por hash SHA-256, de modo que cualquier alteración de un evento de auditoría sea detectada automáticamente por el verificador.

---

## 3. Marco Teórico y Conceptual

> *[B — Sharit Manjarrez]*
> **Nota:** Las fuentes que se citan a continuación son propuestas de búsqueda que el equipo debe verificar y abrir antes de incluirlas en el informe final. No se inventan DOIs.

### 3.1 Sistemas Distribuidos: Transparencia y Fallos Parciales

Un sistema distribuido es un conjunto de computadores independientes que, desde el punto de vista del usuario, se presentan como un único sistema coherente (Tanenbaum & Van Steen, obra de referencia — *buscar: "Tanenbaum distributed systems principles and paradigms"*). La **transparencia de acceso** oculta al usuario la localización física de los datos; la **transparencia de fallo** permite que el sistema continúe operando aunque alguno de sus componentes falle.

Los **fallos parciales** son la norma, no la excepción: en nuestra plataforma, si la base de datos de Cartagena cae, el resto del sistema sigue operativo. El diseño debe anticipar este escenario explícitamente: la vista unificada muestra los datos de Sincelejo y Corozal, e indica claramente que Cartagena no respondió.

> **Conexión con el repo de referencia:** Al ejecutar `docker compose up` en `jaiderreyes/historia-clinica-distribuida` y luego `docker compose stop pg_nodo2`, el middleware sigue respondiendo a consultas con los datos de los nodos 1 y 3. El dashboard muestra el estado de cada nodo. Esta es la evidencia empírica de tolerancia a fallos parciales que nuestra plataforma debe replicar y extender.

### 3.2 Teorema CAP

El teorema CAP (Brewer, 2000 — *buscar: "Brewer CAP theorem 2000 PODC"*) establece que un sistema distribuido no puede garantizar simultáneamente las tres propiedades:

- **C**onsistencia: todos los nodos ven los mismos datos al mismo tiempo.
- **A**disponibilidad (*Availability*): el sistema siempre responde.
- **P**artición tolerante: el sistema funciona aunque fallen los enlaces de red.

**Nuestra decisión de diseño:** elegimos **AP** (disponibilidad + tolerancia a partición). Cuando la sede 2 cae, preferimos responder con datos parciales de las sedes 1 y 3 (disponible pero potencialmente inconsistente) antes que rechazar la consulta por esperar la sede caída (consistente pero no disponible). Esta elección se documenta explícitamente en el Reporte de HC, que advierte: *"Historia posiblemente incompleta: sede Cartagena no disponible."*

### 3.3 Propiedades ACID

Las transacciones que modifican los datos dentro de un mismo nodo de sede mantienen las propiedades ACID:

- **Atomicidad:** `INSERT usuario + INSERT atencion` en una sola transacción; si falla a la mitad, no queda nada.
- **Consistencia:** las restricciones de integridad referencial garantizan que nunca exista una atención sin usuario.
- **Aislamiento:** lecturas y escrituras concurrentes no se interfieren (nivel READ COMMITTED en PostgreSQL).
- **Durabilidad:** tras el COMMIT, el dato persiste aunque el proceso caiga.

> **Demostración (Fase 2):** Se mostrará una transacción que fuerza un error a la mitad (violación de constraint) y se verificará que no queda ningún registro parcial.

### 3.4 Fragmentación Horizontal

La fragmentación horizontal divide una tabla en subconjuntos de filas según un criterio. En nuestra plataforma, la tabla `atencion` está fragmentada horizontalmente **por sede**: todas las atenciones de Sincelejo están en `pg_sede1`, las de Cartagena en `pg_sede2` y las de Corozal en `pg_sede3`. La clave de fragmentación (`sede_id`) coincide con el patrón de consulta más frecuente (el médico de una sede consulta primero los datos de su sede).

La consulta unificada requiere un **fan-out**: la API consulta los tres nodos en paralelo y unifica los resultados en memoria. Este patrón se conoce como *scatter-gather* o *query fan-out*.

### 3.5 HL7 v2

HL7 (*Health Level Seven*) versión 2 es el estándar de mensajería clínica más utilizado globalmente desde los años 1990 (*buscar: "HL7 version 2.5 specification"*). Un mensaje HL7 v2 consiste en segmentos separados por `\r` (CR), con campos separados por `|` y componentes por `^`. Los segmentos principales relevantes para este proyecto son:

- **MSH** (Message Header): identificador del mensaje (campo 10, clave de idempotencia), tipo de mensaje (campo 9, ADT^A01 u ORU^R01), sede de origen (campo 4).
- **PID** (Patient Identification): documento (campo 3), nombre (campo 5, `Apellido^Nombre`), nacimiento (campo 7), sexo (campo 8).
- **PV1** (Patient Visit): clase de atención (campo 2), médico (campo 7), número de visita (campo 19), fecha de ingreso (campo 44).
- **DG1** (Diagnosis): código diagnóstico (campo 3, `código^descripción^sistema`).
- **OBX** (Observation): código LOINC (campo 3), valor (campo 5), unidad (campo 6).

### 3.6 FHIR R4 — Recurso, Perfil y Bundle

**FHIR** (*Fast Healthcare Interoperability Resources*) es el estándar moderno de interoperabilidad en salud, publicado por HL7 International (*buscar: "HL7 FHIR R4 specification 4.0.1"*). Cada **Recurso** FHIR (Patient, Encounter, Condition, Observation) tiene estructura JSON predefinida con campos obligatorios y opcionales.

Un **Perfil** es una restricción de un recurso para un contexto específico (por ejemplo, el Perfil Colombiano de Patient definido por el Ministerio de Salud). En este proyecto se usa el perfil base R4 sin restricciones adicionales para mantener la simplicidad.

Un **Bundle** de tipo `transaction` agrupa múltiples recursos con instrucciones (`PUT`, `POST`) en una sola petición atómica a HAPI FHIR. Si algún recurso del Bundle falla la validación, toda la transacción se rechaza. Los IDs de los recursos son **deterministas** (ej: `Patient/pac-1007`) para garantizar idempotencia: enviar el mismo Bundle dos veces no crea duplicados.

### 3.7 Bus de Integración (ESB / HSB)

Un **bus de integración** (*Enterprise Service Bus*, ESB) es un middleware que actúa como intermediario entre sistemas heterogéneos: recibe mensajes en diferentes formatos, los valida, transforma y enruta al destino correcto (*buscar: "enterprise integration patterns Hohpe Woolf"*). En el contexto clínico se denomina **HSB** (*Health Service Bus*).

Las responsabilidades del HSB en este proyecto son:
1. **Recibir** mensajes HL7 v2 y CSV de las tres sedes.
2. **Verificar idempotencia** (no procesar el mismo mensaje dos veces).
3. **Validar** campos antes de transformar.
4. **Transformar** a Bundle FHIR R4.
5. **Enrutar** al HAPI FHIR y al nodo de BD de la sede correspondiente.
6. **Reintentar** con backoff exponencial si el destino no está disponible.

### 3.8 Idempotencia

Una operación es **idempotente** si ejecutarla múltiples veces produce el mismo resultado que ejecutarla una sola vez. En el HSB, la idempotencia se implementa en dos niveles:
- **Nivel de mensaje:** antes de procesar, se verifica si el `MSH-10` (ID del mensaje) ya existe en la tabla `mensaje_bus`. Si existe, se responde "duplicado" sin reprocesar.
- **Nivel FHIR:** los recursos tienen IDs deterministas (`Patient/pac-1007`). Un `PUT` a HAPI con el mismo ID y contenido no crea un nuevo recurso; actualiza el existente (semánticamente equivalente).

### 3.9 Terminologías Clínicas: CIE-10 y LOINC

**CIE-10** (Clasificación Internacional de Enfermedades, 10.ª revisión) es la terminología estándar para diagnósticos. En Colombia es adoptada por el Ministerio de Salud para el registro de morbilidad. Formato: `[A-Z][0-9]{2}(\.[0-9]{1,4})?` (ej: `J45.9` = Asma no especificada).

**LOINC** (*Logical Observation Identifiers Names and Codes*) es la terminología estándar para observaciones clínicas y de laboratorio (*buscar: "LOINC Regenstrief Institute"*). Formato: `[0-9]+-[0-9]+` (ej: `718-7` = Hemoglobina en sangre).

Ambas terminologías son requeridas por FHIR R4: los `Condition` usan CIE-10 en `Condition.code.coding[0]` y los `Observation` usan LOINC en `Observation.code.coding[0]`.

---

## 4. Modelado UML

> *[A — Jose Canchila]*
> Los diagramas completos (con fuente Mermaid editable) están en:
> - [`diagramas/01_casos_uso.md`](../diagramas/01_casos_uso.md)
> - [`diagramas/02_secuencia_hsb.md`](../diagramas/02_secuencia_hsb.md)
> - [`diagramas/03_clases.md`](../diagramas/03_clases.md)
> - [`diagramas/04_estados_mensaje.md`](../diagramas/04_estados_mensaje.md)

### Verificación de coherencia entre diagramas

| Elemento | Casos de uso | Secuencia | Clases | Estados |
|----------|-------------|-----------|--------|---------|
| `SistemaSede` (actor) | UC14 | Participante | `Sede` | — |
| `MensajeBus` | UC6 (estado) | Cola de reintentos | Clase completa | Ciclo completo |
| `EventoAuditoria` | UC11 | Servicio Auditoría | Clase completa | Genera en cada transición |
| `Diagnostico` | UC7 | NodoDB (INSERT) | Clase completa | — |
| `BundleFHIR` | UC2, UC10 | HAPI FHIR | Clase completa | ENTREGADO |
| Estado `RECHAZADO` | UC14 (resultado) | Camino de error | `MensajeBus.estado` | Transición explícita |
| Estado `REINTENTANDO` | — | Loop de reintentos | `MensajeBus.intentos` | Transición explícita |
| `Auditor` (actor) | UC11, UC12, UC13 | Servicio Auditoría | `UsuarioSistema` con `Rol=auditor` | Puede reencolar MUERTO |

---

## 5. Arquitectura y Justificación

> Ver documento completo: [`arquitectura/arquitectura_y_justificacion.md`](../arquitectura/arquitectura_y_justificacion.md)

---

## 6. Tabla de Mapeo de Campos

> Ver documento completo: [`arquitectura/tabla_mapeo_campos.md`](../arquitectura/tabla_mapeo_campos.md)
> Total: 22 campos mapeados (mínimo exigido: 15 ✓)

---

## 7. Observación del Repositorio de Referencia

> *[A + B — Ambos integrantes]*
> **Pendiente:** Ejecutar los siguientes comandos y anotar la salida en esta sección.

```bash
git clone https://github.com/jaiderreyes/historia-clinica-distribuida
cd historia-clinica-distribuida
docker compose up -d
docker compose ps
# Verificar que pg_nodo1, pg_nodo2, pg_nodo3 están en estado saludable
# Abrir el dashboard y ejecutar una consulta de historia de un paciente
# Anotar: ¿qué hace el middleware? ¿consulta los 3 nodos en paralelo?
```

**Lo que se espera observar (basado en la descripción del repo):**
1. El middleware recibe una petición de historia clínica.
2. Lanza consultas SQL **en paralelo** a los tres nodos PostgreSQL.
3. Recibe los resultados parciales y los une en memoria.
4. Retorna la historia unificada al dashboard.
5. Si un nodo está caído (`docker compose stop pg_nodo2`), retorna los datos de los otros dos y marca el nodo como no disponible.

> **Alimenta el marco teórico:** este comportamiento es el ejemplo empírico de *fan-out* y tolerancia a fallos parciales descrito en la sección 3.1 y 3.4.

---

## 8. Pregunta de Autoevaluación

> **¿Si la sede 2 (Cartagena) está caída, qué ve el médico al pedir la historia de un paciente con registros en las tres sedes?**

**Respuesta:**

El médico ve **la historia clínica parcial** del paciente: los registros de Sincelejo (sede 1) y Corozal (sede 3) se muestran normalmente, ordenados por fecha. El Reporte de HC incluye un **aviso explícito**:

> ⚠️ *"Sede 2 (Cartagena) no disponible. Los datos mostrados pueden estar incompletos. Este reporte NO es el expediente completo del paciente."*

Lo que el médico NO ve:
- Las atenciones, diagnósticos y resultados de laboratorio realizados en Cartagena.
- El Bundle FHIR descargable está marcado como incompleto (`Bundle.meta.tag: incomplete`).

Lo que el sistema garantiza:
- La API **no falla** ni devuelve error 500; devuelve 200 con `sedes_disponibles: [1, 3]` y `sedes_no_disponibles: [2]`.
- El HSB **encola** cualquier mensaje pendiente para la sede 2 y lo entrega en cuanto la sede vuelva a estar disponible.
- Queda un **evento de auditoría** con `tipo=CONSULTA_PARCIAL` que registra quién consultó, cuándo, y qué sedes no respondieron.
- El médico puede ver en el tablero del Reporte de HC que la sede 2 está en estado `NO_DISPONIBLE`.

**Fundamento de diseño (CAP):** elegimos Disponibilidad sobre Consistencia (AP). Preferimos respuesta parcial a no respuesta.

---

## 9. Checklist de Entregables de Fase 1

| Entregable | Estado | Ubicación |
|-----------|--------|-----------|
| ☑ Informe parcial (resumen, intro, objetivos, marco teórico) | Completo | Este archivo |
| ☑ Diagrama UML: Casos de Uso (Mermaid + análisis) | Completo | `diagramas/01_casos_uso.md` |
| ☑ Diagrama UML: Secuencia HSB (Mermaid + análisis) | Completo | `diagramas/02_secuencia_hsb.md` |
| ☑ Diagrama UML: Clases (Mermaid + análisis) | Completo | `diagramas/03_clases.md` |
| ☑ Diagrama UML: Estados del Mensaje (Mermaid + análisis) | Completo | `diagramas/04_estados_mensaje.md` |
| ☑ Diagrama de Arquitectura (Mermaid) | Completo | `arquitectura/arquitectura_y_justificacion.md` |
| ☑ Tabla de justificación de componentes | Completo | `arquitectura/arquitectura_y_justificacion.md` |
| ☑ Tabla de mapeo ≥15 campos | Completo (22 campos) | `arquitectura/tabla_mapeo_campos.md` |
| ☑ Estructura base del repositorio | Completo | Raíz del repo |
| ⬜ Commit de A (Jose Canchila) | Pendiente — ver instrucciones abajo | Git |
| ⬜ Commit de B (Sharit Manjarrez) | Pendiente — ver instrucciones abajo | Git |
| ⬜ Evidencia del repo de referencia ejecutado | Pendiente — ejecutar comandos sección 7 | Captura de pantalla / log |
| ⬜ Respuesta a pregunta de autoevaluación | Completo — sección 8 | Este archivo |

---

## 10. Instrucciones para los Commits

### Commit de A — Jose Canchila (diagramas UML)
```bash
git add docs/fase1/diagramas/ docs/fase1/arquitectura/arquitectura_y_justificacion.md
git commit -m "fase1(A): agregar 4 diagramas UML (casos de uso, secuencia, clases, estados) y diagrama de arquitectura con tabla de justificacion"
git push origin main
```

### Commit de B — Sharit Manjarrez (marco teórico + mapeo)
```bash
git add docs/fase1/informe_fase1.md docs/fase1/arquitectura/tabla_mapeo_campos.md docs/bitacora.md
git commit -m "fase1(B): agregar informe fase1 con marco teorico, tabla de mapeo de 22 campos y bitacora"
git push origin main
```

### Commit inicial (estructura) — puede ser de cualquiera
```bash
git add README.md .gitignore .env.example docker-compose.yml
git commit -m "inicio: estructura base del repositorio, README y configuracion inicial"
git push origin main
```

> **Nota:** Si el repo no está inicializado aún, ejecutar primero:
> ```bash
> cd c:\Users\Jose G Canchila\Documents\Sistemas_distribuidos\parcial_2
> git init
> git remote add origin <URL_DEL_REPO_EN_GITHUB>
> ```

