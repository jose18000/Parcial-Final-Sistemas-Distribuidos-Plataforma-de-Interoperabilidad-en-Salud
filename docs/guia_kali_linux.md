# Guía de ejecución en Kali Linux

**Plataforma distribuida de interoperabilidad clínica — v2**
Probada en Kali Linux sobre VirtualBox con 3,8 GB de RAM y Docker 28 (Compose v2), el 10 y 11 de
noviembre de 2026.

---

## 1. Preparar Kali

```bash
sudo apt update
sudo apt install -y git curl jq docker.io docker-compose-plugin python3-pip python3-venv

sudo systemctl enable --now docker
sudo usermod -aG docker $USER
newgrp docker            # o cerrar sesión y volver a entrar

docker version           # cliente y servidor responden sin sudo
docker compose version   # Compose v2
```

Memoria: con 4 GB asignados a la VM alcanza. HAPI usa hasta 768 MB (`-Xmx768m`) y MongoDB limita su
caché a 0,25 GB (`--wiredTigerCacheSizeGB 0.25`). Cierre otras aplicaciones pesadas.

---

## 2. Obtener el repositorio

```bash
cd ~
git clone https://github.com/jose18000/Parcial-Final-Sistemas-Distribuidos-Plataforma-de-Interoperabilidad-en-Salud.git
cd Parcial-Final-Sistemas-Distribuidos-Plataforma-de-Interoperabilidad-en-Salud
git tag -l               # debe aparecer v1.0
```

---

## 3. Configurar `.env` (y reasignar puertos si hace falta)

```bash
cp .env.example .env
```

Ver qué puertos ya están ocupados en Kali (es común tener un PostgreSQL local en 5432/5433):

```bash
sudo ss -ltnp | grep -E ':(5433|5435|5436|27018|8090|8001|8000)\b'
```

Si alguno aparece, cámbielo en `.env` y nada más. Ejemplo:

```bash
sed -i 's/^DB_PORT_SEDE1=.*/DB_PORT_SEDE1=15433/; s/^DB_PORT_SEDE3=.*/DB_PORT_SEDE3=15435/; s/^DB_PORT_CENTRAL=.*/DB_PORT_CENTRAL=15436/' .env
```

| Variable | Por defecto | Para qué |
|---|---|---|
| `DB_PORT_SEDE1` | 5433 | PostgreSQL de la Sede 1 visto desde el anfitrión |
| `MONGO_PORT_SEDE2` | 27018 | MongoDB de la Sede 2 visto desde el anfitrión |
| `DB_PORT_SEDE3` | 5435 | PostgreSQL de la Sede 3 |
| `DB_PORT_CENTRAL` | 5436 | PostgreSQL de auditoría |
| `HAPI_PORT` | 8090 | HAPI FHIR |
| `HSB_PORT` | 8001 | Bus |
| `API_PORT` | 8000 | Vistas y API |

Cambiar estos puertos **no** rompe nada interno: dentro de Docker los servicios se hablan por nombre
y puerto del contenedor (`pg_sede1:5432`, `mongo_sede2:27017`, `hapi-fhir:8080`). Si cambia
`HAPI_PORT`, `HSB_PORT` o `API_PORT`, use el puerto nuevo en las URL de esta guía.

Genere también un secreto JWT propio:

```bash
sed -i "s/^JWT_SECRET=.*/JWT_SECRET=$(openssl rand -hex 32)/" .env
```

---

## 4. Levantar todo desde cero

```bash
docker compose down -v && docker compose up -d --build
docker compose ps
```

Esperado: `pg_sede1`, `mongo_sede2`, `pg_sede3` y `pg_central` en `healthy`; `hapi_fhir_r4`,
`hsb_bus` y `api_gateway` en `running`.

**Esperar a HAPI** (en la VM tarda 85–95 s en responder; no tiene healthcheck propio):

```bash
until curl -sf http://localhost:8090/fhir/metadata > /dev/null; do echo "esperando a HAPI..."; sleep 5; done
curl -s http://localhost:8001/health | jq '{status, dependencias}'
```

Esperado: `"status": "UP"`, `hapi_fhir_r4: UP` y las tres sedes `UP` con su motor
(postgresql, mongodb, postgresql).

| Servicio | URL |
|---|---|
| Vistas (login) | http://localhost:8000 |
| HSB | http://localhost:8001 (`/health`, `/metrics`, `/hsb/mensajes`, `/hsb/catalogo`) |
| HAPI FHIR R4 | http://localhost:8090/fhir |

---

## 5. Abrir las vistas

Firefox → `http://localhost:8000`.

| Usuario | Contraseña | Rol | Entra a |
|---|---|---|---|
| `paciente_carlos` | `Paciente123!` | paciente | `/paciente` |
| `admision_laura` | `Admision123!` | admisionista | `/admision` |
| `medico_mateo` | `Medico123!` | médico | `/medico` |
| `auditor_elena` | `Auditor123!` | auditor | `/reporte` |

Como `auditor_elena`, la pestaña **Tablero de estado** debe mostrar cobertura FHIR **0 %** en las
tres sedes antes de enviar mensajes.

---

## 6. Enviar los ejemplos al bus

```bash
curl -s -X POST --data-binary @ejemplos/01_adt_a01_valido_sede2.hl7 http://localhost:8001/hsb/hl7 | jq '{estado, sede, recursos_fhir}'
curl -s -X POST --data-binary @ejemplos/01_adt_a01_valido_sede2.hl7 http://localhost:8001/hsb/hl7 | jq '{estado}'
curl -s -X POST --data-binary @ejemplos/02_oru_r01_laboratorio_sede1.hl7 http://localhost:8001/hsb/hl7 | jq '{estado, sede}'
curl -s -X POST --data-binary @ejemplos/03_adt_a01_invalido.hl7 http://localhost:8001/hsb/hl7 | jq '{estado, motivos}'
curl -s -X POST --data-binary @ejemplos/04_sede3_legado.csv "http://localhost:8001/hsb/csv?sede=3" | jq '{total_entregados, total_rechazados}'
curl -s -X POST --data-binary @tests/datos/06_adt_a03_57_campos_sede1.hl7 http://localhost:8001/hsb/hl7 | jq '{estado, recursos_fhir}'
```

| Envío | Resultado esperado |
|---|---|
| 01 | `entregado` en la Sede 2 (MongoDB): Patient 1007, Encounter, Condition J45.9 |
| 01 otra vez | `duplicado` |
| 02 | `entregado` en la Sede 1 (PostgreSQL): Observation 718-7 = 13.8 g/dL de 1001 |
| 03 | `rechazado` con 3 motivos (documento no numérico, sexo no válido, diagnóstico sin mapeo a CIE-10) |
| 04 | 3 entregados (1008, 1009, 1010) y 2 rechazados |
| 06 | `entregado`, 11 recursos FHIR; en el Reporte de HC del 1020: 56 de 57 campos (falta el 42) |

Comprobar que no hay duplicados:

```bash
curl -s "http://localhost:8090/fhir/Patient?identifier=1007&_summary=count" | jq .total     # 1
docker exec mongo_sede2 mongosh -u clinica_user -p clinica_pass_2026 --authenticationDatabase admin \
  clinica_cartagena --quiet --eval 'db.pacientes.countDocuments({_id: "1007"})'               # 1
```

(Si cambió `POSTGRES_USER` / `POSTGRES_PASSWORD` en `.env`, use esos valores: MongoDB usa las mismas
credenciales.)

Cobertura FHIR en el tablero después de los ejemplos: sede 1 50 % (67 % con el mensaje 06),
sede 2 33,3 %, sede 3 75 %.

---

## 7. Pruebas en vivo

### 7.1 Reintento con HAPI apagado

Use un mensaje que el bus no haya recibido antes: un mensaje ya entregado responde `duplicado`. Lo
más simple es hacer esta prueba con el 06 **en lugar de** enviarlo en la sección 6 (así lo hace el
guion de la demo), o repetir antes `docker compose down -v && docker compose up -d --build`.

```bash
docker compose stop hapi-fhir
curl -s -X POST --data-binary @tests/datos/06_adt_a03_57_campos_sede1.hl7 http://localhost:8001/hsb/hl7 | jq '{estado, intentos, max_intentos, proximo_intento_s}'
docker compose start hapi-fhir
docker compose logs -f hsb        # "HSB reintento n/7 ..." y luego "ENTREGADO tras N intentos"
```

Esperado: `202` con `reintentando`; esperas de 2, 4, 8, 16, 32 y 64 s; entrega automática cuando HAPI
vuelve (medido: 129,5 s después del primer intento, en el 7.º intento), sin duplicado.

**Mensaje muerto:** si HAPI queda apagado más de ~2 min, el mensaje pasa a `MUERTO`. Se ve en
`curl -s "http://localhost:8001/hsb/mensajes?estado=MUERTO" | jq` y se reencola con:

```bash
curl -s -X POST http://localhost:8001/hsb/reencolar/MSG-0057 | jq
```

### 7.2 Caída de una sede (MongoDB)

```bash
docker stop mongo_sede2
curl -s http://localhost:8000/health | jq '{status, nodos_activos}'    # DEGRADED, 2/3
```

En Firefox, como `medico_mateo`: Reporte de HC de `1001` → atenciones de Sincelejo y Corozal, aviso
de que la Sede 2 no respondió y reporte incompleto. Luego:

```bash
docker start mongo_sede2
```

Al refrescar vuelven las atenciones de Cartagena y desaparece el aviso.

### 7.3 Acceso denegado

Como `paciente_carlos`, abrir `http://localhost:8000/api/pacientes/1002/historia` → **403**. Desde
terminal:

```bash
curl -s -c /tmp/cookies.txt -o /dev/null -d 'username=paciente_carlos&password=Paciente123!' http://localhost:8000/auth/login
curl -s -b /tmp/cookies.txt -w '\nHTTP %{http_code}\n' http://localhost:8000/api/pacientes/1002/historia
```

### 7.4 Alteración de la auditoría

```bash
docker exec -it pg_central psql -U clinica_user -d clinica_central \
  -c "UPDATE evento_auditoria SET usuario_sistema='intruso' WHERE indice = 3"
```

Como `auditor_elena` → **Tablero de estado**: alerta de alteración en el **índice 3**, motivo
"Alteración de contenido". También con `GET http://localhost:8000/api/auditoria/verificar` (sesión de
auditor o médico). La cadena queda marcada hasta el próximo `docker compose down -v`.

### 7.5 Atomicidad (ACID) en PostgreSQL

```bash
docker exec -i pg_sede1 psql -U clinica_user -d clinica_sincelejo < db/demo_acid.sql
```

Esperado: el `INSERT` de la atención con `clasificacion_triage = '9'` viola el `CHECK`, la transacción
se revierte completa y el usuario 9999 tampoco queda.

### 7.6 Reinicio del bus con mensajes pendientes

Con HAPI apagado, envíe un mensaje nuevo (queda en `REINTENTANDO`) y reinicie el bus. Un registro
JSON mínimo sirve (paciente sintético 2001 en la Sede 3):

```bash
docker compose stop hapi-fhir
curl -s -X POST "http://localhost:8001/hsb/json?sede=3" -H 'Content-Type: application/json' \
  -d '{"registro": {"documento_id": "2001", "nombre_completo": "Paciente Prueba Reinicio", "sexo": "F",
       "fecha_nacimiento": "1990-05-05", "numero_visita": "V-S3-PRUEBA-01", "fecha_ingreso": "2026-11-10T10:00:00"}}' | jq '{estado, mensaje_id}'
docker compose restart hsb
docker compose logs hsb | grep -i recuperados     # "Recuperados N mensajes pendientes tras el arranque del bus"
docker compose start hapi-fhir
```

Cuando HAPI vuelve, los mensajes recuperados se entregan solos.

---

## 8. Pruebas automatizadas (fuera de Docker)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r hsb/requirements.txt -r app/requirements.txt pytest
python -m pytest tests/ -v
```

Esperado: **36 passed**. Las pruebas no necesitan los contenedores (usan dobles de prueba para las
bases y HAPI).

---

## 9. Problemas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| `Bind for 0.0.0.0:5433 failed: port is already allocated` | Puerto ocupado en Kali | Cambiar la variable en `.env` (sección 3) y volver a `up -d` |
| `/health` del HSB en `DEGRADED` con `hapi_fhir_r4: DOWN` | HAPI aún arranca | Esperar con el bucle de la sección 4 |
| El ejemplo 01 da `duplicado` la primera vez | Quedaron volúmenes de una corrida anterior | `docker compose down -v` |
| `mongo_sede2` no llega a `healthy` | Poca memoria en la VM | Cerrar aplicaciones; revisar `docker compose logs mongo_sede2` |
| `permission denied` al usar `docker` | El usuario no está en el grupo `docker` | `sudo usermod -aG docker $USER` y volver a iniciar sesión |
| Contraseña con `!` falla en `curl` | El shell expande `!` entre comillas dobles | Usar comillas simples, como en 7.3 |
