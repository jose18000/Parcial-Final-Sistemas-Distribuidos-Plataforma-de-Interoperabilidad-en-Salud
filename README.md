# Plataforma Distribuida de Interoperabilidad Clínica
## Red de IPS Sincelejo · Cartagena · Corozal

> **Equipo:** Jose Guillermo Canchila (A) · Sharit Javier Manjarrez (B)
> **Curso:** Sistemas Distribuidos · Parcial Final
> **Versión:** `v2` — 57 campos (Res. 866 de 2021), traductor universal y sedes con motores distintos

---

## 1. Qué hace

Cada sede conserva su sistema legado con **su propia base de datos y su propio motor**, y emite
mensajes en formatos distintos. La plataforma los integra, los traduce a un modelo común de
**57 campos** (Resolución 866 de 2021), los publica en **FHIR R4** y permite consultar la historia
unificada de un paciente **sin reemplazar los sistemas legados**.

| Sede | Ciudad | Motor | Formato que envía |
|---|---|---|---|
| 1 | Sincelejo | **PostgreSQL** (relacional) | HL7 v2 ORU^R01 |
| 2 | Cartagena | **MongoDB** (documental, no relacional) | HL7 v2 ADT^A01 |
| 3 | Corozal | **PostgreSQL** (relacional) | CSV legado (`;`) |

```
 HL7 v2 ─┐                          ┌─> HAPI FHIR R4 (Bundle transaction, PUT)
 CSV    ─┼─> HSB ─> traductor 57 ───┼─> Sede 1 PostgreSQL
 JSON   ─┘   valida, idempotencia,  ├─> Sede 2 MongoDB
             cola y reintentos      └─> Sede 3 PostgreSQL
                                          ▲
 4 vistas por rol ─> API Gateway ─────────┘  consulta unificada en paralelo
                         └─> pg_central: auditoría encadenada por hash
```

### El traductor universal (`traductor/`)

- `catalogo_57.py` — **fuente única de verdad**. Para cada uno de los 57 campos dice de qué
  segmento HL7 sale, qué columna CSV lo trae, en qué `tabla.columna` de PostgreSQL y en qué ruta
  del documento MongoDB queda, y a qué elemento FHIR corresponde.
- `dominios.py` — códigos permitidos y sinónimos de cada sede (por ejemplo, `E` de HL7 PV1-2 →
  entorno `01` Urgencias, triage `III` → `3`, sexo `I` → `O`, vía `PO` → `01` Oral).
- `traductor.py` — HL7 / CSV / JSON → **registro canónico** → filas PostgreSQL / documento MongoDB,
  y de vuelta. Calcula los derivados (edad, unidad de edad, código del prestador) y la cobertura.
- Los campos que HL7 v2.5 no trae viajan en segmentos Z: `ZPI`, `ZPV`, `ZRX`, `ZEG`.
- Mapeo completo: [`docs/mapeo_57_campos.md`](docs/mapeo_57_campos.md) (se regenera con
  `python -m traductor.generar_mapeo`).

---

## 2. Estructura del repositorio

```
├── app/          API Gateway, RBAC, auditoría, tablero y las 4 vistas (Jinja2)
├── hsb/          Health Service Bus: entradas HL7/CSV/JSON, validación, cola y reintentos, métricas
├── traductor/    Traductor universal de los 57 campos (catálogo, dominios, traducciones)
├── fhir/         Normalizador del registro canónico a Bundle FHIR R4
├── db/           Esquema PostgreSQL, semilla MongoDB, repositorios y consulta unificada
├── tests/        Pruebas por fase (36) y mensaje HL7 de 57 campos (tests/datos/)
├── ejemplos/     Mensajes oficiales del docente (NO MODIFICADOS)
├── docs/         Informes, mapeo de 57 campos, guion, bitácora
├── infra/        Manifiestos de Kubernetes (bonus)
└── docker-compose.yml
```

---

## 3. Requisitos

- Docker ≥ 24 con Compose v2 (probado en Kali Linux, 4 GB de RAM)
- `curl` para enviar los ejemplos · Python 3.11+ solo para correr las pruebas fuera de Docker

## 4. Ejecución (un solo comando)

```bash
cp .env.example .env            # ajuste puertos si alguno está ocupado
docker compose down -v && docker compose up -d --build
docker compose ps               # sedes y pg_central en "healthy"; HAPI tarda ~90 s en responder
```

| Servicio | URL / puerto |
|---|---|
| Vistas web (login) | http://localhost:8000 |
| HSB | http://localhost:8001 (`/health`, `/metrics`, `/hsb/mensajes`, `/hsb/catalogo`) |
| HAPI FHIR R4 | http://localhost:8090/fhir |
| Sede 1 PostgreSQL | `localhost:${DB_PORT_SEDE1}` (5433) |
| Sede 2 MongoDB | `localhost:${MONGO_PORT_SEDE2}` (27018) |
| Sede 3 PostgreSQL | `localhost:${DB_PORT_SEDE3}` (5435) |
| Auditoría central | `localhost:${DB_PORT_CENTRAL}` (5436) |

## 5. Usuarios de prueba (datos sintéticos)

| Usuario | Contraseña | Rol | Qué puede hacer |
|---|---|---|---|
| `paciente_carlos` | `Paciente123!` | paciente | Su historia (doc 1001) de las 3 sedes, su Bundle FHIR, quién accedió a su historia |
| `admision_laura` | `Admision123!` | admisionista | Buscar en qué sedes existe un paciente, registrar/admitir con triage, monitor del bus. **No ve diagnósticos** |
| `medico_mateo` | `Medico123!` | medico | Historia unificada; diagnóstico CIE-10, fórmula (campos 25-32) y egreso (40-50) con sello |
| `auditor_elena` | `Auditor123!` | auditor | Panel de administración, Reporte de HC, tablero de estado y verificador de auditoría |
| `admin_plataforma` | `Admin123!` | administrador (rol extra) | **Panel de administración** en vivo (`/panel`): sedes, bus, FHIR, auditoría, pacientes, registro rápido y **usuarios de toda la red** |
| `admin_sincelejo` · `admin_cartagena` · `admin_corozal` | `Admin123!` | administrador de sede | Igual que el anterior, pero solo crea y gestiona médicos, admisionistas y pacientes **de su sede** |

### Cuentas de usuario

- Las cuentas viven en la base central (`pg_central.usuario_sistema`), con contraseña PBKDF2-SHA256 y la
  trazabilidad de cómo se registraron: origen (carga inicial, panel o admisión), quién la creó, cuándo y
  último acceso. Cada alta, activación/desactivación y restablecimiento queda en la auditoría.
- **Cuenta del paciente:** al admitir a un paciente nuevo se crea su cuenta del portal (usuario = número de
  documento) con una contraseña temporal que se muestra una sola vez. En el primer ingreso el sistema obliga
  a cambiarla (`/cambiar-clave`); hasta entonces no deja usar ninguna otra pantalla.
- Toda cuenta creada desde el panel recibe también una contraseña temporal de cambio obligatorio.

### Panel de administración (`/panel`)

Una sola pantalla que se actualiza sola cada 5 s: indicadores, estado de las 3 sedes y su motor, mensajes
por estado, recursos FHIR en HAPI por tipo, últimos mensajes del bus, cadena de auditoría y la lista de
pacientes de las 3 sedes con búsqueda. Desde ahí se registra un paciente (botón «Datos de ejemplo» para
llenarlo con datos ficticios): viaja por el HSB y aparece en la lista en un segundo.

### Datos de prueba masivos

```bash
python3 scripts/generar_datos_prueba.py --pacientes 80      # ~200 mensajes HL7/CSV por el bus
```

Genera pacientes ficticios repartidos en las 3 sedes (HL7 v2 con segmentos Z a las sedes 1 y 2,
CSV extendido a la 3), con laboratorios, fórmulas, egresos, algunos errores a propósito (RECHAZADO)
y reenvíos (DUPLICADO). Es determinista: ejecutarlo otra vez no crea copias.

## 6. Enviar los ejemplos al bus

```bash
curl -X POST --data-binary @ejemplos/01_adt_a01_valido_sede2.hl7 http://localhost:8001/hsb/hl7     # entregado (Mongo)
curl -X POST --data-binary @ejemplos/01_adt_a01_valido_sede2.hl7 http://localhost:8001/hsb/hl7     # duplicado
curl -X POST --data-binary @ejemplos/02_oru_r01_laboratorio_sede1.hl7 http://localhost:8001/hsb/hl7 # entregado (PostgreSQL)
curl -X POST --data-binary @ejemplos/03_adt_a01_invalido.hl7 http://localhost:8001/hsb/hl7          # rechazado, 3 motivos
curl -X POST --data-binary @ejemplos/04_sede3_legado.csv "http://localhost:8001/hsb/csv?sede=3"     # 3 entregados, 2 rechazados
curl -X POST --data-binary @tests/datos/06_adt_a03_57_campos_sede1.hl7 http://localhost:8001/hsb/hl7 # 56/57 campos
```

## 7. Pruebas obligatorias en vivo

```bash
# Reintento: HAPI caído -> REINTENTANDO -> se entrega solo al volver (espera 2, 4, 8 ... 64 s)
docker compose stop hapi-fhir
curl -X POST --data-binary @ejemplos/02_oru_r01_laboratorio_sede1.hl7 http://localhost:8001/hsb/hl7
docker compose start hapi-fhir
docker compose logs -f hsb            # "HSB reintento n/7 ..." y luego "ENTREGADO"
# Mensaje muerto: deje HAPI apagado más de ~2 min; se reencola con
curl -X POST http://localhost:8001/hsb/reencolar/<mensaje_id>

# Caída de una sede (la Mongo, por ejemplo): la vista responde con 2 sedes y avisa
docker stop mongo_sede2      # luego:  docker start mongo_sede2

# Alteración de la auditoría: el verificador señala el primer evento alterado
docker exec -it pg_central psql -U clinica_user -d clinica_central \
  -c "UPDATE evento_auditoria SET usuario_sistema='intruso' WHERE indice = 3"
# Reporte de HC -> pestaña Tablero (auditor) o GET /api/auditoria/verificar

# Atomicidad (ACID) en PostgreSQL
docker exec -i pg_sede1 psql -U clinica_user -d clinica_sincelejo < db/demo_acid.sql
```

## 8. Colección de pruebas (Postman)

`docs/coleccion/`: 43 peticiones con pruebas automáticas (mensajes del docente, 57 campos, FHIR, permisos por
rol, auditoría, panel y usuarios). Importar en Postman con el entorno de la VM, o:

```bash
npx newman run docs/coleccion/Plataforma_Interoperabilidad.postman_collection.json -e docs/coleccion/entorno_kali.postman_environment.json
```

HAPI FHIR guarda sus recursos en PostgreSQL (base `hapi` dentro de `pg_central`), así que no se pierden al
reiniciar la VM.

## 8b. Pruebas automatizadas

```bash
pip install -r hsb/requirements.txt -r app/requirements.txt pytest
python -m pytest tests/ -v
```

| Suite | Qué cubre |
|---|---|
| `tests/fase2/test_normalizer.py` | Recursos FHIR, ids deterministas, referencias internas, caso inválido |
| `tests/fase2/test_traductor_57.py` | Catálogo de 57, esquema SQL vs catálogo, ida y vuelta Mongo, CSV, JSON por número de campo |
| `tests/fase3/test_hsb_integration.py` | Los 4 ejemplos oficiales, idempotencia, reintento, muerto y reencolar, sede caída |
| `tests/fase4/test_security_resilience.py` | Permisos por rol (403 y auditoría), cadena de hash y alteración, resiliencia |

## 9. Versión

```bash
git tag v1.0     # entrega final
```
