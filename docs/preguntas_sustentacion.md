# Preguntas de sustentación — respuestas preparadas

**Equipo:** Jose Guillermo Canchila (A) · Sharit Javier Manjarrez (B)
**Versión del sistema:** v2

La nota de sustentación es individual: **los dos** deben poder dar cualquiera de estas respuestas.
La columna "quién la lidera" es solo para no pisarse en vivo. Cada respuesta cita el archivo donde
está el código, para abrirlo si el docente lo pide.

| # | Pregunta | Lidera |
|---|---|---|
| 1 | Sede 2 cae a mitad de una transacción: qué garantiza y qué sacrifica (CAP) | A |
| 2 | Por qué reenviar un mensaje no crea un paciente duplicado | B |
| 3 | Cómo sabe que la auditoría no fue alterada | A |
| 4 | Cambie en vivo el rol permitido de una acción | B |
| 5 | Qué escalaría primero con 100 veces más mensajes | A |
| 6 | Por qué MongoDB en la sede 2 y cómo maneja el traductor esquemas distintos | B |
| 7 | Cómo viaja un campo de HL7 a MongoDB y a FHIR | B |
| 8 | Qué pasa si el bus muere entre "HAPI OK" y "sede OK" | A |
| 9 | Por qué los errores de datos no se reintentan | A |
| 10 | Cómo se calcula la cobertura | B |

---

## 1. Si la sede 2 cae a mitad de una transacción distribuida, ¿qué garantiza su diseño y qué sacrifica según CAP?

**Respuesta.** No usamos una transacción distribuida (2PC) entre sedes ni entre HAPI y la sede; a
propósito. Lo que hay es:

- **Dentro de cada sede, atomicidad local.** La sede 2 es MongoDB y guarda la atención completa
  (diagnósticos, tecnologías, egreso) embebida en el documento del paciente, con un solo
  `replace_one`. Una escritura de un documento es atómica: si Mongo cae, o quedó el documento nuevo
  o quedó el anterior; nunca media atención. En las sedes PostgreSQL es lo mismo con una transacción
  (`db/repositorio.py`, `RepositorioPostgres.guardar`).
- **Entre HAPI y la sede, consistencia eventual.** El bus entrega a HAPI y luego a la sede. Si la
  sede 2 no responde, el mensaje pasa a REINTENTANDO y un hilo en segundo plano lo repite con
  esperas de 2, 4, 8, 16, 32 y 64 s. Repetir es seguro porque los dos pasos son idempotentes. Si la
  sede no vuelve en 7 intentos, queda MUERTO y se reencola con `POST /hsb/reencolar/{id}`.
- **En la lectura, disponibilidad (AP).** La consulta unificada pregunta a las 3 sedes en paralelo
  (`db/consulta_unificada.py`). Si la sede 2 no responde en 3 s, devuelve lo de las sedes 1 y 3,
  marca `reporte_completo = false`, lista la sede caída y la vista muestra el aviso. `/health` dice
  `DEGRADED`, 2/3.

**Qué se sacrifica:** la consistencia mientras dura la partición. El médico no ve las atenciones de
Cartagena y, durante un reintento, HAPI puede tener un dato que la sede todavía no tiene.

**Caso borde honesto:** si la sede 2 ya estaba caída antes de que llegara el mensaje, el bus no puede
guardar el estado en su `mensajes_bus`; lo guarda en memoria y lo persiste cuando Mongo vuelve. Si
además el bus se reinicia en ese intervalo, ese estado en memoria se pierde y la sede tendría que
reenviar el mensaje.

**Para mostrar:** `docker stop mongo_sede2`, Reporte de HC de 1001, `curl localhost:8000/health`.

---

## 2. ¿Por qué reenviar un mensaje no crea un paciente duplicado?

**Respuesta.** Hay tres capas y cualquiera de ellas sola ya evita el duplicado:

1. **Bus.** Antes de validar, `verificar_idempotencia` busca el `MSH-10` (o el hash SHA-256 de la
   fila CSV o del JSON) en `mensaje_bus` de la sede (`hsb/queue_manager.py`). Si está ENTREGADO,
   TRANSFORMADO o REINTENTANDO, responde `duplicado` sin tocar nada. Esa tabla vive en la base de la
   sede, así que funciona aunque el bus se haya reiniciado. `hash_contenido` es `UNIQUE`.
2. **FHIR.** El Bundle es `transaction` con `PUT` a ids deterministas: `Patient/pac-1007`,
   `Encounter/enc-V-S2-0101`, `Condition/cond-V-S2-0101-ing-J45.9`. Un `PUT` a la misma URL
   reemplaza el recurso; repetirlo da el mismo resultado (`fhir/normalizer.py`).
3. **Sede.** PostgreSQL hace `INSERT … ON CONFLICT (llave) DO UPDATE` por `documento_id`,
   `numero_visita`, `diagnostico_id`, `tecnologia_id`; MongoDB hace `replace_one` por `_id` = documento
   y fusiona la atención por `numero_visita`.

**Medido:** reenviar el ejemplo 01 respondió `duplicado`; quedó exactamente 1 Patient 1007 en HAPI y
1 documento en MongoDB.

---

## 3. ¿Cómo sabe que la auditoría no fue alterada?

**Respuesta.** Cada evento de `pg_central.evento_auditoria` guarda dos hashes (`app/audit.py`):

```
hash_propio = SHA-256(hash_anterior | indice | timestamp | usuario | rol | tipo | recurso | resultado | detalle)
```

El primero enlaza con el evento anterior (el primero enlaza con 64 ceros). El verificador recorre la
cadena en orden y en cada evento comprueba: que el índice sea el esperado (detecta borrados o
reordenamientos), que `hash_anterior` sea el `hash_propio` del anterior y que, recalculado con los
datos actuales, el hash coincida con el guardado. Devuelve el **primer** evento que falla y el motivo.

Si alguien hace `UPDATE … SET usuario_sistema='intruso' WHERE indice = 3`, el hash recalculado del
evento 3 cambia y el verificador lo señala: "Alteración de contenido". Para ocultarlo tendría que
recalcular el hash del 3 y de **todos** los siguientes, y eso rompe el enlace que el resto del
sistema ya conoce (el último hash se muestra en el tablero y cada sello de egreso es un hash de la
cadena).

Las inserciones toman `pg_advisory_xact_lock` para que dos peticiones simultáneas no tomen el mismo
"evento anterior" y la cadena no se bifurque.

**Límite:** quien tenga acceso de escritura a `pg_central` puede rehacer toda la cadena. Por eso el
trabajo futuro es anclar periódicamente el último hash fuera (Hyperledger Fabric).

**Medido:** el `UPDATE` de la guía se detectó en el índice exacto 3.

---

## 4. Cambie en vivo el rol permitido de una acción y muestre el efecto

**Procedimiento** (los permisos se validan en la API, por eso basta con cambiar la dependencia):

1. Abrir `app/main.py`, función `vista_reporte`:
   ```python
   usuario: Dict[str, Any] = Depends(requerir_roles(["medico", "auditor", "paciente"]))
   ```
2. Quitar `"paciente"`:
   ```python
   usuario: Dict[str, Any] = Depends(requerir_roles(["medico", "auditor"]))
   ```
3. El contenedor no recarga en caliente (Uvicorn corre sin `--reload` y el código va dentro de la
   imagen), así que se reconstruye solo la API:
   ```bash
   docker compose up -d --build api
   ```
4. Entrar como `paciente_carlos` y abrir `http://localhost:8000/reporte`.
5. **Efecto:** página **403 · Acceso denegado** — *El rol 'paciente' no tiene permisos para realizar
   esta acción* — y un evento `ACCESO_DENEGADO` nuevo en la cadena (`requerir_roles` en `app/rbac.py`
   lo registra antes de lanzar el 403). Se ve en el tablero del auditor o con
   `GET /api/auditoria/eventos`.
6. Revertir el cambio y volver a `docker compose up -d --build api`.

Alternativa rápida para mostrar un 403 sin tocar código: como paciente, abrir
`/api/pacientes/1002/historia` (`validar_acceso_historia_clinica`).

---

## 5. ¿Qué escalaría primero si llegaran 100 veces más mensajes?

**Respuesta.** El **HSB**, porque es el cuello de botella por diseño:

- El primer intento de entrega es síncrono dentro de la petición (HAPI + sede) y los reintentos los
  atiende **un** hilo por proceso. Con 100× la carga, la petición tarda lo que tarde HAPI.

Orden:

1. **Broker delante del bus** (Kafka o RabbitMQ, una partición por sede para conservar el orden de
   cada sede). Los endpoints solo validan, publican y responden `202`.
2. **Varias réplicas del HSB** consumiendo el broker. Ya son casi sin estado: la idempotencia y el
   estado viven en `mensaje_bus` de cada sede, así que dos réplicas no duplican.
3. **HAPI** en más de una instancia sobre PostgreSQL (hoy es una instancia con su base embebida).
4. **Las sedes**, al final: réplicas de lectura para la consulta unificada; *replica set* en MongoDB.

No escalaríamos primero las bases: cada sede solo recibe su parte del tráfico (fragmentación por sede).

---

## 6. ¿Por qué MongoDB en la sede 2 y cómo maneja el traductor esquemas distintos?

**Por qué.** El escenario dice que cada sede conserva su sistema legado con su base; el docente nos
indicó que las sedes no usaran todas el mismo motor. Elegimos MongoDB para Cartagena porque es el caso
más distinto de un relacional: un **documento por paciente** con las atenciones embebidas y nombres
de campo propios (`identificacion.numero`, `ingreso.fecha`, `sexo_biologico`). Si la plataforma
funciona con eso, no depende de un esquema único. Además el modelo documental encaja con la unidad de
escritura: una atención completa es una escritura atómica de un documento.

**Cómo lo maneja el traductor** (`traductor/`):

- Un **catálogo único** (`catalogo_57.py`): cada campo tiene su columna PostgreSQL **y** su ruta
  MongoDB, además de HL7, CSV y FHIR.
- Un **registro canónico**: `a_postgres` / `desde_postgres` producen y leen filas por tabla;
  `a_mongo` / `desde_mongo` producen y leen el documento. Ninguna función tiene nombres de columna
  escritos a mano: los toma del catálogo.
- Un **repositorio con la misma interfaz** (`db/repositorio.py`): `obtener_repositorio(2)` devuelve
  `RepositorioMongo`, las otras `RepositorioPostgres`. El bus y la consulta unificada no preguntan
  qué motor hay.

Probado: `tests/fase2/test_traductor_57.py` hace ida y vuelta canónico → Mongo → canónico; la
historia de 1001 se arma con dos PostgreSQL y un MongoDB (52/57 campos).

---

## 7. ¿Cómo viaja un campo de HL7 a MongoDB y a FHIR?

**Campo 14, municipio de residencia (código DANE)**, en un mensaje de la sede 2:

| Paso | Dónde | Valor / ruta |
|---|---|---|
| 1. Llega en HL7 | `PID-11` (dirección), componente 9 → `PID-11.9` | `…^^^CO^^^70001` → `70001` |
| 2. Catálogo | Fila 14 de `catalogo_57.py`: `hl7="PID-11.9"`, `pg="usuario.municipio_residencia"`, `mongo="residencia.municipio_dane"`, `fhir="Patient.address.district"` | — |
| 3. Registro canónico | `desde_hl7` recorre el catálogo y llena `usuario.municipio_residencia` | `"70001"` |
| 4a. Sede 2 (MongoDB) | `a_mongo` pone el valor en la ruta del catálogo | `pacientes.residencia.municipio_dane = "70001"` |
| 4b. Sede 1 o 3 (PostgreSQL) | `a_postgres` | `usuario.municipio_residencia = '70001'` (`VARCHAR(5)`) |
| 5. FHIR | `normalizar_paciente` | `Patient.address[0].district = "70001"` |
| 6. Vuelta | `desde_mongo` lee la misma ruta y devuelve el canónico para la consulta unificada | `usuario.municipio_residencia` |

Para un campo que HL7 v2.5 no trae, por ejemplo el **23, clasificación del triage**, la ruta es
`ZPV-3` (segmento Z del proyecto) → `atenciones[].triage.clasificacion` en MongoDB /
`atencion.clasificacion_triage` en PostgreSQL → `Encounter.priority`; el dominio convierte `III` en `3`.

---

## 8. ¿Qué pasa si el bus muere entre "HAPI OK" y "sede OK"?

**Respuesta.** Antes de entregar, el bus guarda el mensaje en estado **TRANSFORMADO** en `mensaje_bus`
de la sede, **con el contenido original**. Si el proceso muere después de que HAPI aceptó y antes de
que la sede guarde:

1. HAPI ya tiene el Bundle; la sede no tiene la atención; el mensaje sigue en TRANSFORMADO.
2. Al arrancar, el bus ejecuta `recuperar_pendientes()` (`hsb/queue_manager.py`, se llama en el
   evento `startup` de `hsb/main.py`): lee de las 3 sedes los mensajes en REINTENTANDO y
   TRANSFORMADO, vuelve a traducir el contenido guardado, reconstruye el Bundle y los programa.
3. El reintento repite **los dos pasos**: el `PUT` a HAPI sobrescribe el mismo recurso y la sede hace
   el UPSERT. Resultado: queda en ENTREGADO, sin duplicados.
4. Si mientras tanto la sede reenvía el mensaje, el bus ve TRANSFORMADO y responde `duplicado`.

**Medido:** al reiniciar el bus con 2 mensajes pendientes, los recuperó y los entregó.

---

## 9. ¿Por qué los errores de datos no se reintentan?

**Respuesta.** Porque reintentar sirve para fallas **transitorias** (la sede o HAPI no responden) y
no para fallas **del dato**. Si la sede rechaza el registro por una restricción (por ejemplo
`clasificacion_triage` fuera de 1–5, un `NOT NULL`, un CIE-10 que no cumple el `CHECK`) o HAPI
responde 4xx, el mismo dato fallará igual en el intento 7. Reintentarlo solo gasta ~2 minutos de
cola y retrasa a los demás.

En `intentar_entrega` el bus mira el tipo de excepción: `IntegrityError`, `DataError`,
`CheckViolation`, `NotNullViolation`, `ForeignKeyViolation`, `DuplicateKeyError`, `WriteError`… y la
respuesta 4xx de HAPI se marcan `[permanente]` y el mensaje va **directo a MUERTO** con el motivo.
Las caídas (`OperationalError`, `ServerSelectionTimeoutError`, timeout) sí se reintentan. Un mensaje
MUERTO se puede reencolar (`/hsb/reencolar/{id}`) o la sede puede reenviarlo corregido.

---

## 10. ¿Cómo se calcula la cobertura?

Hay **dos** coberturas distintas:

**a) Cobertura FHIR por sede (tablero).** `pacientes con fhir_patient_id / pacientes de la sede`
(`RepositorioSede.cobertura_fhir`). `fhir_patient_id` arranca en nulo en los datos sintéticos (por
eso 0 %) y lo escribe el bus (`marcar_ids_fhir`) cuando el Bundle del paciente llega a HAPI.
Medido: 0 % al inicio; después de los ejemplos, sede 1 50 % (67 % con el mensaje de 57 campos),
sede 2 33,3 %, sede 3 75 %. No llega a 100 % porque los pacientes sembrados que no reciben mensajes
no se migran (falta un script de migración; está en trabajo futuro).

**b) Cobertura de los 57 campos por paciente (Reporte de HC).** `cobertura_57()` en
`traductor/traductor.py`: arma la vista de 57 campos del usuario y de **cada** atención (de
cualquier sede); un campo cuenta como cubierto si tiene valor en el usuario o en alguna atención.
Devuelve campos cubiertos / 57, obligatorios cubiertos / 23 y la lista de faltantes con su número y
si son obligatorios. Medido: mensaje de prueba 56/57 (falta el 42), paciente 1001 52/57, ambos con
100 % de obligatorios.
