# Guion de la demostración en vivo (15 minutos)

**Equipo:** Jose Guillermo Canchila (A) · Sharit Javier Manjarrez (B)
**Versión del sistema:** v2 — 57 campos, traductor universal, Sede 2 en MongoDB
**Regla:** todo lo que se hace aquí está en el `README.md`; no hay pasos manuales fuera de él.

Sigue el orden de la guía de la Fase 5 (arranque limpio → cobertura 0 % → HL7 y CSV → duplicado →
caída de sede → auditoría alterada → consulta unificada y Reporte de HC) y agrega lo que la v2
tiene de nuevo: el mensaje de 57 campos y el reintento con HAPI apagado.

---

## Antes de entrar (no cuenta en los 15 min)

- Terminal en la raíz del repositorio, con `.env` copiado de `.env.example`. En Kali, si los
  puertos 5433/5435/5436/27018 ya están ocupados, se cambian en `.env` (`DB_PORT_SEDE1`,
  `DB_PORT_SEDE3`, `DB_PORT_CENTRAL`, `MONGO_PORT_SEDE2`); la demo no usa esos puertos desde fuera
  (todo se hace con `docker exec` o por la API), así que el guion no cambia.
- Haber corrido una vez `docker compose build` para que las imágenes del HSB y la API estén en
  caché: el `--build` del arranque tarda segundos y no minutos.
- Firefox con dos ventanas (una normal y una privada) para tener dos sesiones a la vez.
- Una segunda terminal con `docker compose logs -f hsb` lista para el bloque 5.
- `jq` instalado (formatea las respuestas JSON).

Usuarios (contraseñas en el README):

| Usuario | Contraseña | Rol |
|---|---|---|
| `paciente_carlos` | `Paciente123!` | paciente (doc. 1001) |
| `admision_laura` | `Admision123!` | admisionista |
| `medico_mateo` | `Medico123!` | médico |
| `auditor_elena` | `Auditor123!` | auditor |

---

## Resumen de tiempos

| Minuto | Bloque | Presenta | Qué se ve |
|---|---|---|---|
| 00:00–02:00 | 1. Arranque limpio desde cero | A | `down -v && up -d --build`, `ps`, `/health` |
| 02:00–03:00 | 2. Cobertura FHIR en 0 % | B | Tablero como auditor: 3 sedes, 2 motores, 0 % |
| 03:00–05:30 | 3. HL7 y CSV entran; la cobertura sube | A | Ejemplos 01 a 04, tablero, Bundle en HAPI |
| 05:30–06:30 | 4. Reenvío: duplicado | B | `duplicado`; 1 Patient en HAPI y 1 documento en MongoDB |
| 06:30–07:30 | 5. Mensaje de 57 campos con HAPI apagado | A | `reintentando` (se entrega solo más tarde) |
| 07:30–09:30 | 6. Caída de la sede MongoDB | B | Historia con 2 sedes, aviso, `DEGRADED`; recuperación |
| 09:30–10:30 | 7. Se entregó solo: 56 de 57 campos | A | Logs del HSB, monitor del bus, reporte de 1020 |
| 10:30–12:00 | 8. Acceso denegado y auditoría alterada | B | 403; `UPDATE` en `pg_central`; alerta en el índice 3 |
| 12:00–15:00 | 9. Consulta unificada de 1001 y Reporte de HC | A + B | 3 sedes, 2 motores, 52/57, sello, Bundle; escritura del médico con sello |

---

## Bloque 1 · Arranque limpio (A, 2 min)

```bash
docker compose down -v && docker compose up -d --build
docker compose ps
```

**Se ve:** `pg_sede1`, `mongo_sede2`, `pg_sede3` y `pg_central` en `healthy`; `hapi_fhir_r4`,
`hsb_bus` y `api_gateway` en `running` (HAPI no tiene healthcheck propio).

Mientras HAPI arranca (85–95 s en la VM), **A explica la arquitectura** con la diapositiva 2:
tres sedes con su propio motor, el HSB con el traductor de 57 campos, HAPI, la API con las 4 vistas
y `pg_central` solo para auditoría.

```bash
curl -s http://localhost:8001/health | jq
```

**Se ve:** `"status": "UP"` cuando HAPI ya responde (antes sale `DEGRADED` con
`hapi_fhir_r4: DOWN`); `sede_1` postgresql, `sede_2` mongodb, `sede_3` postgresql, todas `UP`.

**Qué decir:** "Un solo comando, desde volúmenes vacíos. Las bases arrancan con datos sintéticos y
`fhir_patient_id` en nulo."

---

## Bloque 2 · Cobertura FHIR en 0 % (B, 1 min)

1. Abrir `http://localhost:8000/login` y entrar como `auditor_elena`.
2. Ir a la pestaña **Tablero de estado** (`http://localhost:8000/reporte?pestana=tablero`).

**Se ve:** 3 nodos activos con su motor (PostgreSQL, MongoDB, PostgreSQL); cobertura FHIR **0 %**
en las tres sedes (sede 1: 0 de 2 pacientes; sede 2: 0 de 2; sede 3: 0 de 1); bus sin mensajes;
auditoría **íntegra**.

**Qué decir:** "La cobertura es el porcentaje de pacientes de cada sede que ya tienen su Patient en
HAPI. Arranca en 0 % porque los legados nunca publicaron en FHIR."

---

## Bloque 3 · HL7 y CSV entran; la cobertura sube (A, 2 min 30 s)

```bash
# HL7 ADT^A01 de la Sede 2 (Cartagena, MongoDB) -> entregado
curl -s -X POST --data-binary @ejemplos/01_adt_a01_valido_sede2.hl7 http://localhost:8001/hsb/hl7 | jq '{estado, mensaje_id, sede, recursos_fhir}'

# HL7 ORU^R01 de la Sede 1 (Sincelejo, PostgreSQL) -> entregado, hemoglobina 13.8 g/dL
curl -s -X POST --data-binary @ejemplos/02_oru_r01_laboratorio_sede1.hl7 http://localhost:8001/hsb/hl7 | jq '{estado, sede, recursos_fhir}'

# HL7 inválido -> rechazado con 3 motivos
curl -s -X POST --data-binary @ejemplos/03_adt_a01_invalido.hl7 http://localhost:8001/hsb/hl7 | jq '{estado, motivos}'

# CSV legado de la Sede 3 (Corozal, PostgreSQL) -> 3 entregados, 2 rechazados
curl -s -X POST --data-binary @ejemplos/04_sede3_legado.csv "http://localhost:8001/hsb/csv?sede=3" | jq '{total_entregados, total_rechazados, rechazados}'
```

**Se ve:**
- 01: `"estado": "entregado"`, `mensaje_id` `MSG-0001`, sede 2, 5 recursos: `Organization/org-sede-2`,
  `Practitioner/prac-MED-02`, `Patient/pac-1007`, `Encounter/enc-V-S2-0101`,
  `Condition/cond-V-S2-0101-ing-J45.9`.
- 02: entregado, `Observation/obs-V-S1-0150-718-7`.
- 03: `rechazado` con *documento no numérico*, *sexo no válido* y *diagnóstico sin mapeo a CIE-10*.
- CSV: `total_entregados: 3` (1008, 1009, 1010) y `total_rechazados: 2` (dx `DOLOR MISTERIOSO` sin
  mapeo y documento de 2 dígitos).

Refrescar el **Tablero**: cobertura sede 1 **50 %**, sede 2 **33,3 %**, sede 3 **75 %**.

Ver el Bundle publicado en HAPI:

```bash
curl -s http://localhost:8090/fhir/Patient/pac-1007 | jq '{id, name, gender, birthDate}'
curl -s "http://localhost:8090/fhir/Observation?patient=pac-1001&code=718-7" | jq '.entry[0].resource.valueQuantity'
```

**Qué decir:** "El mismo bus atiende tres formatos. El traductor lleva cada uno al registro
canónico de 57 campos y de ahí sale el Bundle para HAPI y, según la sede, filas de PostgreSQL o el
documento de MongoDB. Lo que no cumple se rechaza con todos sus motivos, no en silencio."

---

## Bloque 4 · Reenvío: duplicado (B, 1 min)

```bash
curl -s -X POST --data-binary @ejemplos/01_adt_a01_valido_sede2.hl7 http://localhost:8001/hsb/hl7 | jq
```

**Se ve:** `"estado": "duplicado"`, `"estado_original": "ENTREGADO"` y el motivo *Mensaje recibido
previamente: no se vuelve a crear el paciente ni la atención*.

Comprobar que hay uno solo:

```bash
# HAPI: un solo Patient con el documento 1007
curl -s "http://localhost:8090/fhir/Patient?identifier=1007&_summary=count" | jq .total

# MongoDB (sede 2): un solo documento del paciente 1007
docker exec mongo_sede2 mongosh -u clinica_user -p clinica_pass_2026 --authenticationDatabase admin \
  clinica_cartagena --quiet --eval 'db.pacientes.countDocuments({_id: "1007"})'
```

**Se ve:** `1` y `1`.

**Qué decir:** "Tres defensas: el bus reconoce el `MSH-10` guardado en `mensajes_bus` de la sede;
aunque lo reprocesara, el Bundle usa `PUT` a `Patient/pac-1007`, que reemplaza el mismo recurso; y
la sede guarda por la misma llave (`_id` en MongoDB, `ON CONFLICT` en PostgreSQL)."

---

## Bloque 5 · Mensaje de 57 campos con HAPI apagado (A, 1 min)

```bash
docker compose stop hapi-fhir
curl -s -X POST --data-binary @tests/datos/06_adt_a03_57_campos_sede1.hl7 http://localhost:8001/hsb/hl7 | jq '{estado, intentos, max_intentos, proximo_intento_s, motivo}'
docker compose start hapi-fhir
```

**Se ve:** HTTP 202 con `"estado": "reintentando"`, `intentos: 1`, `max_intentos: 7`,
`proximo_intento_s: 2`. En la terminal de logs: `HSB reintento 2/7`, `3/7`… con esperas de 2, 4, 8,
16, 32 y 64 s.

**Qué decir:** "El bus no bloquea la petición: responde 202 y un hilo en segundo plano reintenta.
HAPI tarda más de un minuto en volver; por eso la espera crece hasta 64 s y hay 7 intentos (unos
2 minutos en total). Seguimos con la demo y volvemos a mirarlo." (Medido en Kali: se entregó 129,5 s
después del primer intento.)

---

## Bloque 6 · Caída de la sede MongoDB (B, 2 min)

1. En la ventana normal, cerrar sesión y entrar como `medico_mateo`; buscar `1001`. Se ven
   atenciones de las 3 sedes.
2. Detener la sede 2:

```bash
docker stop mongo_sede2
```

3. Volver a buscar `1001` en la vista del médico y abrir el Reporte de HC
   (`http://localhost:8000/reporte?buscar_doc=1001`).

**Se ve:** atenciones de Sincelejo (`V-S1-0150`) y Corozal (`V-S3-0045`); aviso de que la Sede 2 -
Cartagena (mongodb) no respondió y de que la historia puede estar incompleta; la sede 2 marcada
como no disponible en el reporte.

```bash
curl -s http://localhost:8000/health | jq '{status, nodos_activos, dependencias}'
```

**Se ve:** `"status": "DEGRADED"`, `"nodos_activos": "2/3"`, `sede_2` `DOWN`.

4. Recuperar:

```bash
docker start mongo_sede2
```

Refrescar: vuelven las atenciones de Cartagena (`V-S2-0080`) y el reporte deja de mostrar el aviso.

**Qué decir:** "Es la decisión AP de CAP: preferimos responder con dos sedes y decir que falta una,
a dejar al médico sin nada. Las tres sedes se consultan en paralelo; la caída cuesta su timeout de
3 s, no se suma a las demás."

---

## Bloque 7 · Se entregó solo: 56 de 57 campos (A, 1 min)

En la terminal de logs del HSB debe aparecer `Mensaje MSG-0057 ENTREGADO tras N intentos`.

```bash
curl -s "http://localhost:8001/hsb/mensajes?limite=5" | jq '.mensajes[] | {mensaje_id, estado, intentos, motor}'
curl -s "http://localhost:8090/fhir/Patient?identifier=1020&_summary=count" | jq .total
```

**Se ve:** `MSG-0057` en `ENTREGADO` (motor postgresql) y un solo Patient 1020.

En el navegador (médico): `http://localhost:8000/reporte?buscar_doc=1020`.

**Se ve:** cobertura **56 de 57** campos y **100 %** de los obligatorios; el único faltante es el
**42, diagnóstico de muerte**, porque la paciente sale viva. El mensaje produjo 11 recursos FHIR:
Organization `org-sede-1`, Practitioner `prac-MED-01`, Patient `pac-1020`, Encounter
`enc-V-S1-0157`, 5 Condition (ingreso, egreso y 3 relacionados), 1 MedicationRequest y 1
AllergyIntolerance. En el Tablero, la cobertura de la sede 1 pasa a **67 %**.

**Qué decir:** "HL7 v2.5 no trae todos los campos de la Resolución 866; los que faltan viajan en
segmentos Z acordados para el proyecto: ZPI, ZPV, ZRX y ZEG. El catálogo dice de dónde sale cada
uno y dónde queda en PostgreSQL, en MongoDB y en FHIR."

> Si el mensaje todavía no aparece entregado, mostrar el monitor del bus en `REINTENTANDO` con su
> número de intento y volver a mirarlo al final del bloque 9.

---

## Bloque 8 · Acceso denegado y auditoría alterada (B, 1 min 30 s)

1. En la ventana privada, entrar como `paciente_carlos` y abrir
   `http://localhost:8000/api/pacientes/1002/historia` (historia de otro paciente).

**Se ve:** HTTP **403** — *Un paciente sólo puede consultar su propia historia clínica*.

2. Alterar una fila de la auditoría directamente en la base:

```bash
docker exec -it pg_central psql -U clinica_user -d clinica_central \
  -c "UPDATE evento_auditoria SET usuario_sistema='intruso' WHERE indice = 3"
```

3. En la ventana del médico (o como `auditor_elena`), abrir el **Tablero de estado**.

**Se ve:** la caja de auditoría en alerta: *¡ALERTA! ALTERACIÓN DETECTADA*, índice **3**, motivo
*Alteración de contenido: el hash_propio no corresponde con los datos del evento*. El 403 del paso 1
aparece en la cadena como `ACCESO_DENEGADO`.

**Qué decir:** "Cada evento guarda el hash del anterior y su propio hash sobre todos sus campos. El
`UPDATE` cambió el usuario pero no pudo recalcular el hash sin rehacer toda la cadena; el
verificador recalcula y señala el primer evento que no cuadra."

> La cadena queda alterada hasta el siguiente `docker compose down -v`. No afecta el resto de la demo.

---

## Bloque 9 · Consulta unificada de 1001 y Reporte de HC (A + B, 3 min)

**A — Reporte de HC** (como médico): `http://localhost:8000/reporte?buscar_doc=1001`.

**Se ve:**
- Atenciones agrupadas por sede: Sincelejo `V-S1-0150` (PostgreSQL, hemoglobina 13,8 g/dL del
  ejemplo 02), Cartagena `V-S2-0080` (MongoDB, asma, PCR 2,1 mg/L), Corozal `V-S3-0045`
  (PostgreSQL, gastroenteritis, sodio y potasio).
- Cobertura **52 de 57** campos, **100 %** de obligatorios, con la lista de faltantes.
- Sello SHA-256 del contenido del reporte; botones de imprimir y de descargar el Bundle.

```bash
# El mismo Bundle que descarga la vista (con la cookie del médico se hace desde el navegador):
# http://localhost:8000/api/pacientes/1001/bundle  -> 26 recursos
```

**Qué decir:** "Una sola consulta junta tres sedes y dos motores. El traductor lee filas de
PostgreSQL y el documento de MongoDB y los devuelve en la misma forma. Este Bundle de 26 recursos lo
validamos en HAPI con `$validate`: 0 errores."

**B — Escritura del médico con sello** (vista `/medico`, paciente 1001, atención `V-S1-0150`):
registrar un diagnóstico CIE-10 (por ejemplo `E11.9`, rol RELACIONADO).

**Se ve:** estado `entregado` y el **sello** (hash del evento `ESCRITURA_HC`). El diagnóstico
aparece en la historia.

**Qué decir:** "La vista no toca la base: la API registra primero el evento de auditoría, cuyo hash
es el sello, y manda el registro al HSB por `/hsb/json`. Pasa por la misma validación que un HL7."

**Cierre rápido de las otras dos vistas (si queda tiempo):**
- `admision_laura` en `/admision`: buscar `1001` → en qué sedes existe, sin diagnósticos; tabla de
  mensajes del bus.
- `paciente_carlos` en `/paciente`: su historia de 3 sedes, botón de Bundle y lista de quién accedió
  (aparece `medico_mateo`).

---

## Si algo falla en vivo

| Síntoma | Qué hacer |
|---|---|
| `/health` del HSB sigue `DEGRADED` por HAPI | Esperar; HAPI tarda ~90 s. `docker compose logs hapi-fhir | tail` |
| El ejemplo 01 responde `duplicado` la primera vez | El volumen no se borró: repetir `docker compose down -v` |
| Un puerto está ocupado al arrancar | Cambiarlo en `.env` y repetir el bloque 1 |
| El mensaje de 57 campos quedó `MUERTO` (HAPI tardó más de ~2 min) | `curl -X POST http://localhost:8001/hsb/reencolar/MSG-0057` |
