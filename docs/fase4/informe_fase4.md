# Informe Fase 4 — Plataforma Distribuida de Interoperabilidad Clínica
## Seguridad RBAC, Resiliencia ante Fallos, Auditoría Inmutable y Viabilidad Técnica

**Autores:**
- Jose Guillermo Canchila (A) — Responsable: Motor de auditoría encadenada, verificador criptográfico y resiliencia ante caídas
- Sharit Javier Manjarrez (B) — Responsable: Matriz RBAC, vistas accesibles, viabilidad técnica (Ley 1581) y tablero

**Curso:** Sistemas Distribuidos · Parcial Final  
**Fecha:** Noviembre 2026  
**Versión del informe:** Fase 4 de 5 (Ponderación: 1,00 / 5,0)

---

## 1. Autenticación y Matriz de Permisos (RBAC)

Se implementó autenticación mediante tokens **JWT firmados con HMAC-SHA256 (HS256)** y tiempo de expiración de 60 minutos. La seguridad no se delega en la interfaz gráfica: **cada endpoint de la API Gateway valida estrictamente el rol y los permisos del usuario en la capa de transporte**.

### 1.1 Matriz de Permisos Evaluada en la API

| Acción del Sistema | Paciente | Admisionista | Médico | Auditor | Verificación en API |
|--------------------|:--------:|:------------:|:------:|:-------:|---------------------|
| **Ver su propia historia** | **Sí** | No | No | No | `GET /api/pacientes/{doc}/historia` (doc coincide con token) |
| **Ver la historia de otro paciente** | **No (403)** | **No (403)** | **Sí** | **Sí (reporte)** | `validar_acceso_historia_clinica()` |
| **Abrir una atención con triage** | **No (403)** | **Sí** | **No (403)** | **No (403)** | `POST /admision/abrir-atencion` |
| **Registrar diagnóstico o egreso** | **No (403)** | **No (403)** | **Sí** | **No (403)** | `POST /medico/registrar-evolucion` |
| **Ver el estado de la plataforma** | **No (403)** | **No (403)** | **Sí** | **Sí** | `GET /reporte` y `GET /metrics` |
| **Apagar / encender un nodo (demo)**| **No (403)** | **No (403)** | **No (403)**| **Sí** | `POST /api/auditoria/alterar-prueba` |

> **Comportamiento ante Acceso Denegado:** Si un usuario sin privilegios intenta invocar una acción no autorizada (por ejemplo, un admisionista intentando leer diagnósticos o un paciente cambiando el documento en la URL), la API responde inmediatamente con **HTTP 403 Forbidden** y registra un evento criptográfico de tipo `ACCESO_DENEGADO` en la cadena de auditoría inmutable.

---

## 2. Auditoría Encadenada por Hash SHA-256 Inmutable

Para asegurar la trazabilidad y la no repudición de las acciones clínicas y de administración, se implementó una **cadena criptográfica secuencial de bloques** (`app/audit.py`), inspirada en la arquitectura de un libro contable distribuido pero optimizada para ejecución relacional ligera:

$$\text{hash\_propio} = \text{SHA-256}(\text{hash\_anterior} \parallel \text{timestamp} \parallel \text{usuario} \parallel \text{tipo\_evento} \parallel \text{resultado} \parallel \text{detalle\_json})$$

### 2.1 Propiedades de la Cadena
1. **Bloque Génesis:** El sistema arranca con un hash génesis fijo de 64 ceros.
2. **Encadenamiento Temporal:** Cada evento almacena el `hash_propio` del evento anterior como su `hash_anterior`.
3. **Inmutabilidad:** Si un administrador de base de datos o un atacante altera maliciosamente una fila (por ejemplo, cambiando un diagnóstico o el usuario que consultó una historia), el hash recalculado ya no coincidirá con el `hash_propio` almacenado, y todos los hashes posteriores romperán su enlace (`hash_anterior != hash_propio_previo`).

### 2.2 Verificador Criptográfico y Prueba de Alteración Docente
Se desarrolló la función `verificar_cadena_auditoria()` que recorre secuencialmente todos los eventos desde el génesis hasta el último:
- **Prueba Normal:** Cadena íntegra $\to$ Responde `cadena_integra: true` con 0 fallos detectados.
- **Demostración de Adulteración en Vivo:**
  1. Se invoca `POST /api/auditoria/alterar-prueba` (o se modifica a mano un campo en la base de datos).
  2. El verificador detecta la discrepancia inmediatamente y devuelve:
     ```json
     {
       "cadena_integra": false,
       "primer_evento_alterado": {
         "evento_id": "c71a39f0-21a4-4f0b-9dfb-088f11d1981a",
         "indice": 0,
         "motivo": "Alteración de contenido: el hash_propio no corresponde con los datos del bloque",
         "hash_propio_almacenado": "d8e3c4...",
         "hash_recalculado": "1a2b3c...",
         "usuario": "atacante_adulterado"
       }
     }
     ```
  3. El Tablero de Estado en la interfaz web cambia de color a rojo y despliega la alerta: **"¡ALERTA! ALTERACIÓN DETECTADA"** señalando con precisión el ID del bloque adulterado.

---

## 3. Resiliencia ante Caídas de Sede (Tolerancia a Fallos Parciales)

El principio de diseño adoptado (modelo AP del teorema CAP) se comprueba de forma práctica ante la caída intencional de un nodo de datos:

```bash
# 1. Detener el contenedor de la Sede 2 (Cartagena)
docker stop pg_sede2

# 2. Consultar la historia del paciente 1001 (que tiene atenciones en las 3 sedes)
curl -s http://localhost:8000/api/pacientes/1001/historia
```

### Comportamiento Verificado del Sistema:
1. **La API NO falla con error 500:** El Gateway detecta el fallo de socket (`timeout` o `connection refused`) en `pg_sede2` de forma no bloqueante.
2. **Respuesta Parcial con Transparencia:** La API responde con `HTTP 200 OK`, retornando las atenciones de Sincelejo (Sede 1) y Corozal (Sede 3).
3. **Señalización Explícita de Incompletitud:**
   - `reporte_completo: false`
   - `sedes_disponibles: [1, 3]`
   - `sedes_no_disponibles: [{"sede_id": 2, "nombre": "Sede 2 - Cartagena", "motivo": "conexión rechazada"}]`
   - Advertencia visible en la vista web: *"⚠️ ATENCIÓN: Sede 2 no disponible. La historia clínica presentada puede estar fraccionada."*
4. **Bundle FHIR con Tag de Incompletitud:** Al descargar el Bundle FHIR R4 durante la caída, se inyecta automáticamente el metadato:
   ```json
   "meta": {
     "tag": [{
       "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationValue",
       "code": "incomplete",
       "display": "Historial clínico incompleto por caída de sede"
     }]
   }
   ```
5. **Recuperación Automática:** Al ejecutar `docker start pg_sede2`, el siguiente refresco de la vista incorpora inmediatamente las atenciones de Cartagena y marca el reporte como completo (3/3 sedes).

---

## 4. Observabilidad y Tablero de Estado

Cada componente de la plataforma expone telemetría estandarizada:
- **API Gateway (`:8000`):** `GET /health` (estado de sedes y dependencias) y `GET /metrics` (auditoría y usuarios).
- **HSB (`:8001`):** `GET /health` (HAPI + Postgres) y `GET /metrics` (latencia media en ms, tasa de fallos, duplicados detectados y mensajes por estado).
- **HAPI FHIR (`:8090`):** `GET /fhir/metadata` (CapabilityStatement R4 4.0.1).

### Tablero de Estado Integrado en el Reporte de HC:
El tablero consolida 4 cuadrantes esenciales:
1. **Disponibilidad de Nodos:** Indicador visual en verde/rojo de los 3 nodos PostgreSQL.
2. **Cobertura FHIR por Sede (%):** Mide el avance de migración legado $\to$ FHIR (pacientes con `fhir_patient_id` no nulo).
3. **Rendimiento del Bus:** Latencia media en milisegundos y contador de reintentos.
4. **Verificador Criptográfico:** Diagnóstico en tiempo real de la integridad de la cadena de hash.

---

## 5. Viabilidad Técnica: Escalabilidad y Cumplimiento Normativo

### 5.1 Escalabilidad (Diseño para Crecimiento 100×)

| Dimensión | Estado Actual (Implementado) | Propuesta para Producción a Gran Escala |
|-----------|------------------------------|------------------------------------------|
| **Capa de Ingesta (HSB)** | Contenedor único en FastAPI con colas en PostgreSQL y reintentos en memoria. | Múltiples réplicas sin estado (*stateless*) del HSB balanceadas por NGINX / Envoy; migración de colas locales hacia un clúster distribuido de **Apache Kafka** o **RabbitMQ** particionado por `sede_id`. |
| **Capa de Almacenamiento** | 3 instancias PostgreSQL independientes (1 por sede). | Clúster de PostgreSQL con réplicas de sólo lectura (*Read Replicas*) por sede y balanceo de consultas *scatter-gather* con pgpool-II; sharding horizontal con **Citus** si el volumen supera millones de pacientes por sede. |
| **Capa de Consulta (API)** | Gateway FastAPI con *fan-out* concurrente. | Despliegue en Kubernetes con *Horizontal Pod Autoscaler* (HPA) basado en métricas de CPU y latencia HTTP. |
| **Capa FHIR (HAPI)** | Servidor standalone HAPI FHIR R4 con base Derby en memoria/disco. | HAPI FHIR respaldado por clúster PostgreSQL de alta disponibilidad y caché distribuida **Redis** para indización de búsquedas frecuentes por `Patient.identifier`. |

### 5.2 Cumplimiento Normativo (Ley 1581 de 2012 y Estándares de Salud)

1. **Protección de Datos Sensibles (Habeas Data Clínico):**
   - La historia clínica constituye un dato de naturaleza sensible según la Ley Estatutaria 1581 de 2012 de Colombia.
   - **Implementado:** El rol `paciente` cuenta con su propia vista donde puede consultar de manera transparente la lista completa de accesos a su información (quién consultó, cuándo y con qué motivo).
   - **Principio de Mínimo Privilegio:** El personal de admisión tiene estrictamente vedado el acceso a diagnósticos y notas médicas.
2. **Seguridad en Tránsito:**
   - **Implementado:** Autenticación por cabeceras `Authorization: Bearer <JWT>` y cookies HttpOnly seguras.
   - **Propuesto:** Terminación TLS 1.3 con certificados X.509 emitidos por autoridad certificadora en el API Gateway y mTLS (*Mutual TLS*) en la comunicación entre el HSB y los nodos legados.
3. **No Repudio e Integridad:**
   - **Implementado:** Cadena inmutable de hash SHA-256 encadenada para toda escritura médica y egreso hospitalario.

---

## 6. Diseño de Interfaces y Accesibilidad (WCAG 2.1)

Se diseñaron 4 vistas principales y el tablero de control cumpliendo lineamientos de accesibilidad web:
1. **Contraste de Color:** Ratios de contraste superiores a 4.5:1 entre texto y fondo (botones `#0056b3` sobre blanco ratio 7.2:1; badges con combinaciones fondo claro y texto oscuro de alto contraste).
2. **Etiquetas y Formularios Semánticos:** Todos los campos de entrada cuentan con su respectivo elemento `<label for="...">` explícito, optimizado para lectores de pantalla.
3. **Navegación por Teclado:** Foco visual evidente (`outline: 2px solid`) en todos los enlaces, botones e inputs; orden de tabulación lógico.
4. **Modo Imprimible:** La vista de Reporte de HC cuenta con estilos `@media print` que ocultan menús y botones, dejando únicamente el reporte médico formal.

---

## 7. Respuesta a la Pregunta de Autoevaluación

> **Pregunta:** Un paciente cambia el número de documento en la URL por el de otro paciente (ej. de `1001` a `1002`). ¿En qué capa lo detiene su sistema y qué queda registrado?

**Respuesta Arquitectural:**

1. **Capa donde se detiene:**
   El intento es interceptado y detenido en la **Capa de Control de Acceso (Middleware RBAC del API Gateway)** en el servidor backend, mediante la función `validar_acceso_historia_clinica()` antes de emitir cualquier consulta SQL a las bases de datos de las sedes.

2. **Mecanismo de Detección:**
   El middleware inspecciona el token JWT criptográficamente firmado que viaja en la petición. El token contiene el claim inalterable `documento_id: "1001"` y el claim `rol: "paciente"`.
   Al evaluar la condición:
   $$\text{token.rol} == \text{'paciente'} \land \text{token.documento\_id} \neq \text{url.documento\_id}$$
   el sistema detecta inmediatamente la violación del principio de aislamiento, aborta la petición y responde con un código de estado **HTTP 403 Forbidden**.

3. **Qué queda registrado:**
   El middleware invoca al motor de auditoría (`app/audit.py`), que inserta un nuevo bloque inmutable en la cadena de hash con:
   - `tipo_evento`: `"ACCESO_DENEGADO"`
   - `usuario_sistema`: `"paciente_carlos"`
   - `rol`: `"paciente"`
   - `recurso_afectado`: `"/historia/1002"`
   - `resultado`: `"DENEGADO"`
   - `timestamp`: Marca de tiempo UTC exacta
   - `detalle`: `{"motivo": "Paciente 1001 intentó acceder a historia ajena 1002"}`
   - `hash_propio`: Enlazado criptográficamente con el evento previo.

El incidente queda sellado de forma permanente sin que el paciente pueda borrar el rastro de la auditoría.
