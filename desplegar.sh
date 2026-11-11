#!/usr/bin/env bash
# ============================================================================
#  desplegar.sh — Despliegue completo de la Plataforma de Interoperabilidad Clínica
#  Red de IPS Sincelejo · Cartagena · Corozal
#
#  Deja el sistema funcionando en un Linux con apt (Kali, Debian, Ubuntu):
#    1. Instala Docker, Docker Compose y openssl si faltan.
#    2. Crea el .env (contraseñas aleatorias para los roles de las bases) y elige puertos libres.
#    3. Seguridad: genera la CA propia y los certificados TLS de cada servidor (certs/),
#       levanta las bases y les aplica los roles de mínimo privilegio (db/seguridad/).
#    4. Construye y levanta HAPI FHIR R4 (HTTPS), el HSB (HTTPS + OAuth 2.0) y la API (HTTPS,
#       servidor OAuth 2.0) y espera a que todo esté sano.
#    5. Opcional: carga los mensajes del docente y datos sintéticos, y los publica en FHIR.
#    6. Opcional: corre la verificación de interoperabilidad sede por sede.
#
#  Uso:
#    bash desplegar.sh                      # instala/levanta conservando los datos existentes
#    bash desplegar.sh --desde-cero         # borra volúmenes y arranca limpio (cobertura FHIR 0 %)
#    bash desplegar.sh --con-datos          # además carga ejemplos + 60 pacientes sintéticos y migra a FHIR
#    bash desplegar.sh --verificar          # al final corre scripts/verificar_interoperabilidad.py
#    bash desplegar.sh --desde-cero --con-datos --verificar     # todo
#    bash desplegar.sh --detener            # apaga la plataforma (conserva los datos)
#
#  Todos los datos son sintéticos. Credenciales de prueba en README.md.
# ============================================================================
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

DESDE_CERO=0; CON_DATOS=0; VERIFICAR=0; DETENER=0; PACIENTES=60
for arg in "$@"; do
  case "$arg" in
    --desde-cero) DESDE_CERO=1 ;;
    --con-datos)  CON_DATOS=1 ;;
    --verificar)  VERIFICAR=1 ;;
    --detener)    DETENER=1 ;;
    --pacientes=*) PACIENTES="${arg#*=}" ;;
    -h|--help) sed -n '2,27p' "$0"; exit 0 ;;
    *) echo "Opción desconocida: $arg (use --help)"; exit 1 ;;
  esac
done

# ── Utilidades ─────────────────────────────────────────────────────────────
if [ -t 1 ]; then V="\033[1;32m"; A="\033[1;33m"; R="\033[1;31m"; B="\033[1;36m"; N="\033[0m"; else V=""; A=""; R=""; B=""; N=""; fi
paso()  { echo -e "\n${B}==> $*${N}"; }
ok()    { echo -e "   ${V}✔${N} $*"; }
aviso() { echo -e "   ${A}!${N} $*"; }
error() { echo -e "   ${R}✘ $*${N}" >&2; }
SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"

# Docker con o sin sudo (recién agregado al grupo docker hace falta una sesión nueva)
DOCKER="docker"
compose() { $DOCKER compose "$@"; }

# ── 1. Docker y Docker Compose ─────────────────────────────────────────────
instalar_docker() {
  paso "Instalando Docker (requiere sudo)"
  command -v apt-get >/dev/null || { error "Este script instala con apt. Instale Docker manualmente: https://docs.docker.com/engine/install/"; exit 1; }
  $SUDO apt-get update -qq
  $SUDO apt-get install -y -qq docker.io curl python3 openssl >/dev/null
  $SUDO systemctl enable --now docker >/dev/null 2>&1 || $SUDO service docker start || true
  ok "Docker instalado: $(docker --version)"
}
instalar_compose() {
  paso "Instalando Docker Compose v2"
  for pkg in docker-compose-plugin docker-compose-v2 docker-compose; do
    if $SUDO apt-get install -y -qq "$pkg" >/dev/null 2>&1 && $DOCKER compose version >/dev/null 2>&1; then
      ok "Compose instalado ($pkg): $($DOCKER compose version --short)"; return 0
    fi
  done
  error "No se pudo instalar Docker Compose v2. Instálelo y vuelva a ejecutar."; exit 1
}

if [ "$DETENER" -eq 1 ]; then
  docker info >/dev/null 2>&1 || DOCKER="$SUDO docker"
  paso "Deteniendo la plataforma (los datos se conservan)"; compose down; ok "Detenida"; exit 0
fi

paso "Comprobando requisitos"
command -v docker >/dev/null || instalar_docker
if ! docker info >/dev/null 2>&1; then
  $SUDO systemctl start docker >/dev/null 2>&1 || true
  if docker info >/dev/null 2>&1; then :; elif $SUDO docker info >/dev/null 2>&1; then
    DOCKER="$SUDO docker"
    if [ -n "$SUDO" ] && ! id -nG | grep -qw docker; then
      $SUDO usermod -aG docker "$USER" && aviso "Se agregó $USER al grupo docker; en la próxima sesión no hará falta sudo."
    fi
  else error "Docker no responde. Revise: sudo systemctl status docker"; exit 1; fi
fi
ok "Docker $($DOCKER version --format '{{.Server.Version}}' 2>/dev/null)"
$DOCKER compose version >/dev/null 2>&1 || instalar_compose
ok "Compose $($DOCKER compose version --short)"
command -v curl >/dev/null || $SUDO apt-get install -y -qq curl >/dev/null
command -v python3 >/dev/null || $SUDO apt-get install -y -qq python3 >/dev/null
command -v openssl >/dev/null || $SUDO apt-get install -y -qq openssl >/dev/null
ok "curl, python3 y openssl disponibles"

MEM=$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo 2>/dev/null || echo 0)
[ "${MEM:-0}" -lt 4 ] && aviso "La máquina tiene ~${MEM} GB de RAM; se recomiendan 4 GB (HAPI FHIR usa hasta 768 MB)."

# ── 2. Configuración (.env y puertos) ──────────────────────────────────────
paso "Configurando .env"
puerto_ocupado() {
  # Ocupado si algo escucha y no es un contenedor de esta misma plataforma
  local p="$1"
  if ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]${p}$"; then
    $DOCKER ps --format '{{.Names}} {{.Ports}}' 2>/dev/null | grep -E "(pg_sede1|mongo_sede2|pg_sede3|pg_central|hapi_fhir_r4|hsb_bus|api_gateway) .*:${p}->" >/dev/null && return 1
    return 0
  fi
  return 1
}
libre_desde() { local p="$1"; while puerto_ocupado "$p"; do p=$((p + 10)); done; echo "$p"; }
fijar() { # fijar CLAVE VALOR  (en .env)
  if grep -q "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else echo "$1=$2" >> .env; fi
}

aleatorio() { python3 -c 'import secrets; print(secrets.token_urlsafe(18))'; }
if [ ! -f .env ]; then
  cp .env.example .env
  for clave in HSB_DB_PASSWORD API_DB_PASSWORD API_CENTRAL_DB_PASSWORD HAPI_DB_PASSWORD HAPI_KEYSTORE_PASSWORD; do
    fijar "$clave" "$(aleatorio)"
  done
  ok ".env creado con contraseñas aleatorias para los roles de las bases"
else
  ok ".env existente conservado"
fi
# Variables nuevas de la v3 que falten en un .env anterior (se toman de .env.example)
while IFS='=' read -r clave valor; do
  case "$clave" in ''|\#*) continue ;; esac
  grep -q "^${clave}=" .env || { echo "${clave}=${valor}" >> .env; aviso "Agregado a .env: ${clave}"; }
done < .env.example
for par in HAPI_PORT:8090 HSB_PORT:8001 API_PORT:8000; do
  clave="${par%%:*}"; defecto="${par##*:}"
  actual="$(grep -E "^${clave}=" .env | cut -d= -f2)"; actual="${actual:-$defecto}"
  nuevo="$(libre_desde "$actual")"
  if [ "$nuevo" != "$actual" ]; then
    fijar "$clave" "$nuevo"; aviso "Puerto $actual ocupado por otro servicio: $clave -> $nuevo"
  else
    fijar "$clave" "$actual"
  fi
done
set -a; . ./.env; set +a
ok "Puertos: API ${API_PORT} · HSB ${HSB_PORT} · HAPI ${HAPI_PORT} (solo localhost) · bases sin puertos publicados"

# Nombres fijos de contenedor: si existe uno igual de OTRO proyecto, avisar en vez de pisarlo
PROYECTO="$(basename "$DIR" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')"
for c in pg_sede1 mongo_sede2 pg_sede3 pg_central hapi_fhir_r4 hsb_bus api_gateway; do
  dueno="$($DOCKER inspect -f '{{ index .Config.Labels "com.docker.compose.project" }}' "$c" 2>/dev/null || true)"
  if [ -n "$dueno" ] && [ "$dueno" != "$PROYECTO" ]; then
    error "Ya existe un contenedor '$c' de otro proyecto ($dueno). Detenga/elimine ese contenedor y vuelva a ejecutar."; exit 1
  fi
done

# ── 3. Construir y levantar ────────────────────────────────────────────────
if [ "$DESDE_CERO" -eq 1 ]; then
  paso "Borrando contenedores y volúmenes anteriores (--desde-cero)"
  compose down -v --remove-orphans >/dev/null 2>&1 || true
  ok "Limpio: las bases se recrean desde db/ (cobertura FHIR 0 %)"
fi
# ── 3. Seguridad: certificados TLS, bases y roles de mínimo privilegio ─────
paso "Generando la CA propia y los certificados TLS (certs/)"
HAPI_KEYSTORE_PASSWORD="$HAPI_KEYSTORE_PASSWORD" CERT_IPS_EXTRA="${CERT_IPS_EXTRA:-}" bash scripts/generar_certificados.sh
CURL="curl -s --cacert certs/ca.pem"

paso "Levantando las bases de datos (TLS obligatorio, sin puertos publicados)"
compose up -d pg_sede1 mongo_sede2 pg_sede3 pg_central 2>&1 | grep -E "Started|Created|Recreated|Error|error" | sed 's/^/   /' || true
RENOVADOS=0; [ -f certs/.renovados ] && RENOVADOS=1 && rm -f certs/.renovados
if [ "$RENOVADOS" -eq 1 ]; then
  aviso "Certificados nuevos: se reinician las bases para que los tomen"
  compose restart pg_sede1 mongo_sede2 pg_sede3 pg_central >/dev/null 2>&1 || true
fi
for c in pg_sede1 mongo_sede2 pg_sede3 pg_central; do
  for i in $(seq 1 60); do
    estado="$($DOCKER inspect -f '{{.State.Health.Status}}' "$c" 2>/dev/null || echo ninguno)"
    [ "$estado" = "healthy" ] && break; sleep 3
  done
  [ "$estado" = "healthy" ] && ok "$c listo" || { error "$c no quedó sano (docker logs $c)"; exit 1; }
done

paso "Aplicando roles de mínimo privilegio (db/seguridad/)"
$DOCKER exec pg_sede1 sh /seguridad/roles_sede.sh | sed 's/^/   /'
$DOCKER exec pg_sede3 sh /seguridad/roles_sede.sh | sed 's/^/   /'
$DOCKER exec pg_central sh /seguridad/roles_central.sh | sed 's/^/   /'
$DOCKER exec mongo_sede2 mongosh --quiet --tls --tlsCAFile /etc/mongo-tls/ca.pem --host localhost \
  -u "$POSTGRES_USER" -p "$POSTGRES_PASSWORD" --authenticationDatabase admin "$DB_NAME_SEDE2" /seguridad/mongo_roles.js | sed 's/^/   /'

# ── 4. Construir y levantar los servicios ──────────────────────────────────
paso "Construyendo y levantando HAPI FHIR, el bus y la API (la primera vez descarga ~2 GB)"
compose up -d --build 2>&1 | grep -E "Built|Started|Created|Recreated|Error|error" | sed 's/^/   /' || true
[ "$RENOVADOS" -eq 1 ] && compose restart hapi-fhir hsb api >/dev/null 2>&1 || true

paso "Esperando a HAPI FHIR por HTTPS (suele tardar 1-2 minutos)"
for i in $(seq 1 90); do
  [ "$($CURL -o /dev/null -w '%{http_code}' "https://localhost:${HAPI_PORT}/fhir/metadata")" = "200" ] && break; sleep 4
done
[ "$($CURL -o /dev/null -w '%{http_code}' "https://localhost:${HAPI_PORT}/fhir/metadata")" = "200" ] && ok "HAPI FHIR R4 listo (HTTPS)" \
  || { error "HAPI no respondió (docker logs hapi_fhir_r4)"; exit 1; }
for i in $(seq 1 30); do
  [ "$($CURL -o /dev/null -w '%{http_code}' "https://localhost:${HSB_PORT}/health")" = "200" ] && \
  [ "$($CURL -o /dev/null -w '%{http_code}' "https://localhost:${API_PORT}/health")" = "200" ] && break; sleep 2
done
SALUD="$($CURL "https://localhost:${HSB_PORT}/health" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["status"], {k: v["motor"]+":"+v["estado"] for k, v in d["dependencias"]["sedes"].items()})')"
ok "Bus: $SALUD"
ok "API: $($CURL "https://localhost:${API_PORT}/health" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["status"], "· sedes", d["nodos_activos"])')"
TOKEN="$($CURL -u "herramientas_qa:${OAUTH_SECRETO_QA}" -d grant_type=client_credentials "https://localhost:${API_PORT}/oauth/token" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin).get("access_token",""))')"
[ -n "$TOKEN" ] && ok "OAuth 2.0: token de servicio emitido (client_credentials, RS256)" || { error "No se pudo obtener un token OAuth"; exit 1; }
SIN_TOKEN="$($CURL -o /dev/null -w '%{http_code}' -X POST --data-binary @ejemplos/01_adt_a01_valido_sede2.hl7 "https://localhost:${HSB_PORT}/hsb/hl7")"
[ "$SIN_TOKEN" = "401" ] && ok "El bus rechaza mensajes sin token (HTTP 401)" || aviso "El bus respondió $SIN_TOKEN a un mensaje sin token"

# ── 5. Datos ───────────────────────────────────────────────────────────────
if [ "$CON_DATOS" -eq 1 ]; then
  paso "Cargando los mensajes oficiales del docente"
  for f in ejemplos/01_adt_a01_valido_sede2.hl7 ejemplos/02_oru_r01_laboratorio_sede1.hl7 ejemplos/03_adt_a01_invalido.hl7 tests/datos/06_adt_a03_57_campos_sede1.hl7; do
    e="$($CURL -H "Authorization: Bearer $TOKEN" -X POST --data-binary @"$f" "https://localhost:${HSB_PORT}/hsb/hl7" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("estado"))')"
    ok "$(basename "$f") -> $e"
  done
  e="$($CURL -H "Authorization: Bearer $TOKEN" -X POST --data-binary @ejemplos/04_sede3_legado.csv "https://localhost:${HSB_PORT}/hsb/csv?sede=3" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["total_entregados"]+d["total_duplicados"], "válidas,", d["total_rechazados"], "rechazadas")')"
  ok "04_sede3_legado.csv -> $e"
  paso "Generando ${PACIENTES} pacientes sintéticos por el bus"
  python3 scripts/generar_datos_prueba.py --url "https://localhost:${HSB_PORT}" --api "https://localhost:${API_PORT}" \
    --ca certs/ca.pem --secreto "$OAUTH_SECRETO_QA" --pacientes "$PACIENTES" | sed 's/^/   /'
  paso "Publicando en FHIR los registros históricos de cada sede (migración)"
  $CURL -H "Authorization: Bearer $TOKEN" -X POST "https://localhost:${HSB_PORT}/hsb/migrar" | python3 -c '
import sys, json
for s in json.load(sys.stdin)["sedes"]:
    print("   ✔ {} ({}): {} publicados, cobertura FHIR {} %".format(s["nombre"], s["motor"], s["publicados"], s["cobertura_fhir"]))'
fi

# ── 6. Verificación ────────────────────────────────────────────────────────
if [ "$VERIFICAR" -eq 1 ]; then
  paso "Verificando la interoperabilidad sede por sede"
  python3 scripts/verificar_interoperabilidad.py --api "https://localhost:${API_PORT}" --hsb "https://localhost:${HSB_PORT}" \
    --fhir "https://localhost:${HAPI_PORT}/fhir" --ca certs/ca.pem --secreto-qa "$OAUTH_SECRETO_QA" \
    --secreto-sede1 "$OAUTH_SECRETO_SEDE1" --salida docs/evidencias/07_verificacion_por_sede.md | tail -1 | sed 's/^/   /'
fi

# ── Resumen ────────────────────────────────────────────────────────────────
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"; IP="${IP:-localhost}"
echo -e "\n${V}Plataforma lista.${N}"
cat <<FIN
   Vistas web ......... https://${IP}:${API_PORT}       (login con los usuarios de prueba del README)
   OAuth 2.0 .......... https://${IP}:${API_PORT}/.well-known/oauth-authorization-server
   Bus (HSB) .......... https://${IP}:${HSB_PORT}/health  (las entradas exigen Bearer token)
   HAPI FHIR R4 ....... https://localhost:${HAPI_PORT}/fhir  (solo desde este servidor)
   Bases de datos ..... sin puertos publicados: red interna red_datos, TLS y un rol por servicio
   CA de la plataforma  certs/ca.pem  (impórtela en el navegador para no ver el aviso de certificado)

   Usuarios: admin_plataforma / Admin123! · medico_mateo / Medico123! · admision_laura / Admision123!
             auditor_elena / Auditor123! · paciente_carlos / Paciente123!

   Detener: bash desplegar.sh --detener      Desde cero con datos: bash desplegar.sh --desde-cero --con-datos
FIN
