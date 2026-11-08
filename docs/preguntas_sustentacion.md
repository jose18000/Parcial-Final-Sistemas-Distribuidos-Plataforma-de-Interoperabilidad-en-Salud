# Guía de Preparación de Preguntas de Sustentación
## Plataforma Distribuida de Interoperabilidad Clínica

Esta guía contiene las respuestas arquitecturales y fundamentos teóricos para las 5 preguntas típicas que el docente formulará durante los 10 minutos de sustentación oral individual.

---

### Pregunta 1: Si la sede 2 cae a mitad de una transacción distribuida, ¿qué garantiza su diseño y qué sacrifica según CAP?

**Quién responde:** A (Jose) o B (Sharit).

**Respuesta Técnica:**
> *"Nuestro diseño adopta el modelo **AP (Disponibilidad y Tolerancia a Partición)** del teorema CAP a nivel de red WAN, y **ACID estricto** a nivel intra-nodo.*
> 
> *1. **Qué se sacrifica:** Sacrificamos la **Consistencia Inmediata Global ($C$)**. No utilizamos un protocolo de bloqueo como Two-Phase Commit (2PC) porque si la sede 2 se cae, 2PC bloquearía a Sincelejo y Corozal impidiendo atender pacientes en el resto de la red.*
> 
> *2. **Qué se garantiza:** Garantizamos **Alta Disponibilidad ($A$)** y **Tolerancia a Particiones ($P$)**. La API Gateway responde con las sedes activas (Sincelejo y Corozal) y etiqueta con total honestidad el expediente clínico como `reporte_completo: false`, advirtiendo al médico que faltan datos de Cartagena.*
> 
> *3. **Qué pasa con la transacción en vuelo:** El Health Service Bus (HSB) recibe un error de socket/timeout, marca el mensaje en su tabla interna como `REINTENTANDO` y aplica backoff exponencial ($1\text{ s}, 2\text{ s}, 4\text{ s}, 8\text{ s}$). Dado que la entrega primero impacta HAPI FHIR mediante operaciones `PUT` deterministas y luego el nodo local con `ON CONFLICT`, cuando la sede 2 vuelve a encenderse, la transacción se completa sin riesgo de inconsistencia ni duplicidad."*

---

### Pregunta 2: ¿Por qué reenviar un mensaje no crea un paciente duplicado?

**Quién responde:** B (Sharit) o A (Jose).

**Respuesta Técnica:**
> *"La no duplicación está garantizada en tres capas independientes:*
> 
> *1. **Capa del Bus (HSB - Idempotencia Física):** Al recibir un mensaje HL7 o CSV, el HSB calcula el hash SHA-256 de todo el contenido y extrae el identificador del mensaje (`MSH-10`). Antes de parsear o transformar, consulta la tabla `mensaje_bus` donde el campo `hash_contenido` tiene restricción de unicidad (`UNIQUE`). Si el hash ya existe en estado `ENTREGADO`, el bus no procesa nada: responde de inmediato `HTTP 200 { "estado": "duplicado" }`.*
> 
> *2. **Capa FHIR (Idempotencia Lógica):** Nuestro normalizador genera **identificadores deterministas** basados en la llave natural del paciente: `Patient/pac-<documento_id>` (ej. `Patient/pac-1007`). El Bundle utiliza el verbo transaccional **`PUT`**. En la semántica REST y en la especificación FHIR R4, un `PUT` a una URL existente reemplaza el recurso con su mismo contenido, resultando en una operación matemáticamente idempotente: $f(f(x)) = f(x)$.*
> 
> *3. **Capa de Base de Datos Local:** En las tablas relacionales de cada sede (`usuario`, `atencion`), las claves primarias son el `documento_id` y el `numero_visita`, e insertamos usando `ON CONFLICT (documento_id) DO UPDATE`. Por eso, aunque el mensaje se reenvíe 100 veces, en la base de datos sólo existirá una fila para el paciente 1007."*

---

### Pregunta 3: ¿Cómo sabe que la auditoría no fue alterada?

**Quién responde:** A (Jose) o B (Sharit).

**Respuesta Técnica:**
> *"Lo sabemos porque implementamos una **cadena criptográfica inmutable enlazada por hash SHA-256**, similar al funcionamiento de una blockchain ligera sin la sobrecarga de consenso computacional:*
> 
> *1. **Fórmula del Bloque:** Cada evento almacena el hash del bloque previo:*
>    $$\text{hash\_propio}_i = \text{SHA-256}(\text{hash\_propio}_{i-1} \parallel \text{timestamp} \parallel \text{usuario} \parallel \text{tipo\_evento} \parallel \text{resultado} \parallel \text{detalle})$$
> 
> *2. **El Algoritmo Verificador:** La función `verificar_cadena_auditoria()` recorre la tabla desde el bloque génesis hasta el último evento registrado y valida dos condiciones matemáticas en cada fila:*
>    * Que `hash_anterior` sea idéntico al `hash_propio` de la fila anterior.
>    * Que al recalcular el hash SHA-256 con los datos actuales de la fila, el resultado coincida exactamente con el `hash_propio` almacenado.
> 
> *3. **Efecto Avalancha:** Si alguien entra directamente con `psql` y modifica un registro (por ejemplo, cambia el usuario que vio una historia o adultera un diagnóstico), el hash recalculado ya no coincide. El verificador detecta la ruptura criptográfica en milisegundos y devuelve el ID y el índice exacto del primer bloque violado, activando una alerta visual roja en el Tablero de Observabilidad."*

---

### Pregunta 4: Cambie en vivo el rol permitido de una acción y muestre el efecto.

**Quién responde:** A (Jose) o B (Sharit).

**Procedimiento en Vivo:**
> *Para responder a esta solicitud del docente, abrimos el archivo [`app/main.py`](file:///c:/Users/Jose%20G%20Canchila/Documents/Sistemas_distribuidos/parcial_2/app/main.py) en la línea del endpoint de egreso médico o reporte:*
> 
> 1. Ubicar la ruta:
>    ```python
>    @app.get("/reporte")
>    def vista_reporte_tablero(
>        ...,
>        usuario: Dict[str, Any] = Depends(requerir_roles(["medico", "auditor", "paciente"]))
>    ):
>    ```
> 2. Quitar el rol `"paciente"` de la lista permitida:
>    ```python
>    usuario: Dict[str, Any] = Depends(requerir_roles(["medico", "auditor"])) # Se eliminó paciente
>    ```
> 3. Guardar el archivo (Uvicorn recarga automáticamente en caliente).
> 4. En el navegador, intentar entrar a `/reporte` con el usuario `paciente_carlos`.
> 5. **Efecto visible:** La API devuelve inmediatamente **`HTTP 403 Forbidden`** con el mensaje *"El rol 'paciente' no tiene permisos para realizar esta acción"* y en la consola o tabla de auditoría aparece un nuevo evento registrado: `ACCESO_DENEGADO`.
> 6. Volver a colocar `"paciente"` y guardar para restaurar la funcionalidad.

---

### Pregunta 5: ¿Qué escalaría primero si llegaran 100 veces más mensajes?

**Quién responde:** B (Sharit) o A (Jose).

**Respuesta Técnica:**
> *"Si la carga aumentara de cientos a decenas de miles de mensajes por minuto, el primer cuello de botella sería el **Health Service Bus (HSB)** en su capa de ingesta síncrona y la base de datos central que gestiona las colas.*
> 
> *Escalaríamos en el siguiente orden de prioridad:*
> 
> *1. **Paso 1: Desacoplar la Ingesta con un Broker Distribuido:** Reemplazaríamos la cola en base de datos relacional por un clúster de **Apache Kafka** o **RabbitMQ** particionado por `sede_id`. Los endpoints `POST /hsb/hl7` y `POST /hsb/csv` se convertirían en productores ultrarrápidos que sólo publican en Kafka y responden `202 Accepted` en <5 ms.*
> 
> *2. **Paso 2: Réplicas Horizontales de Workers HSB (Stateless):** Levantaríamos múltiples instancias en paralelo del HSB mediante Kubernetes con un *Horizontal Pod Autoscaler* (HPA) que escuche el tamaño de la cola de Kafka y escale réplicas de workers según el volumen de mensajes.*
> 
> *3. **Paso 3: Servidor HAPI FHIR con Caché Distribuida:** HAPI FHIR pasaría de una instancia standalone a un clúster respaldado por PostgreSQL y una capa de caché en memoria con **Redis** para resolver rápidamente las búsquedas de identificadores de pacientes.*
> 
> *4. **Paso 4: Sharding de Base de Datos:** Si las sedes crecen en volumen histórico de millones de atenciones, activaríamos **Citus** en los nodos PostgreSQL para particionar la tabla `atencion` por rango de fechas o hash del paciente."*
