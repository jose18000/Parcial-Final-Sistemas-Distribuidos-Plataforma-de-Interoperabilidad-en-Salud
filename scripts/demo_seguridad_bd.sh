#!/usr/bin/env bash
# scripts/demo_seguridad_bd.sh — demuestra la seguridad de las bases de datos en vivo.
#
#     bash scripts/demo_seguridad_bd.sh
#
# Cada prueba intenta algo que NO debe poder hacerse y muestra el rechazo del motor.
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1
set -a; . ./.env; set +a
T() { echo; echo -e "\033[1;36m== $*\033[0m"; }
MONGO="docker exec mongo_sede2 mongosh --quiet --tls --tlsCAFile /etc/mongo-tls/ca.pem --host localhost"

T "1. Las bases no publican puertos (solo API, bus y HAPI en 127.0.0.1)"
docker ps --format '{{.Names}}\t{{.Ports}}' | grep -E "pg_sede|mongo_sede2|pg_central|hapi_fhir_r4|hsb_bus|api_gateway" | sort

T "2. Mínimo privilegio · el bus (hsb_escritor) intenta BORRAR un paciente de la sede 1"
docker exec -e PGPASSWORD="$HSB_DB_PASSWORD" pg_sede1 psql -h localhost -U hsb_escritor -d clinica_sincelejo \
  -c "DELETE FROM usuario WHERE documento_id = '1001'" 2>&1 | head -1

T "3. Mínimo privilegio · la API (api_lector) intenta MODIFICAR la sede 3 (y luego solo lee)"
docker exec -e PGPASSWORD="$API_DB_PASSWORD" pg_sede3 psql -h localhost -U api_lector -d clinica_corozal \
  -c "UPDATE usuario SET telefono = '000'" 2>&1 | head -1
docker exec -e PGPASSWORD="$API_DB_PASSWORD" pg_sede3 psql -h localhost -U api_lector -d clinica_corozal \
  -Atc "SELECT 'lectura permitida: ' || count(*) || ' pacientes' FROM usuario" 2>&1 | head -1

T "4. Auditoría de solo agregar · la API (api_central) intenta alterar y borrar la cadena"
docker exec -e PGPASSWORD="$API_CENTRAL_DB_PASSWORD" pg_central psql -h localhost -U api_central -d clinica_central \
  -c "UPDATE evento_auditoria SET usuario_sistema = 'intruso' WHERE indice = 3" 2>&1 | head -1
docker exec -e PGPASSWORD="$API_CENTRAL_DB_PASSWORD" pg_central psql -h localhost -U api_central -d clinica_central \
  -c "DELETE FROM evento_auditoria" 2>&1 | head -1

T "5. MongoDB (sede 2) · api_lector intenta insertar y hsb_escritor intenta borrar"
$MONGO -u api_lector -p "$API_DB_PASSWORD" --authenticationDatabase clinica_cartagena clinica_cartagena \
  --eval 'db.pacientes.insertOne({_id: "x"})' 2>&1 | grep -o "MongoServerError: not authorized[^{]*" | head -1
$MONGO -u hsb_escritor -p "$HSB_DB_PASSWORD" --authenticationDatabase clinica_cartagena clinica_cartagena \
  --eval 'db.pacientes.deleteOne({_id: "1007"})' 2>&1 | grep -o "MongoServerError: not authorized[^{]*" | head -1

T "6. Cifrado obligatorio · conexión SIN TLS a PostgreSQL y a MongoDB"
docker exec -e PGPASSWORD="$HSB_DB_PASSWORD" pg_sede1 psql "host=localhost user=hsb_escritor dbname=clinica_sincelejo sslmode=disable" \
  -c "select 1" 2>&1 | grep -o "FATAL.*" | head -1
docker exec mongo_sede2 mongosh --quiet "mongodb://localhost:27017/?serverSelectionTimeoutMS=3000" \
  --eval 'db.adminCommand({ping: 1})' 2>&1 | head -1

T "7. Quién se conecta a cada base y con qué cifrado (registro de PostgreSQL)"
for c in pg_sede1 pg_sede3 pg_central; do
  docker logs "$c" 2>&1 | grep "connection authorized" | grep -vE "application_name=(psql|pg_isready)" | tail -1 \
    | sed "s/.*connection authorized: /   $c: /"
done
docker logs pg_central 2>&1 | grep "connection authorized" | grep hapi_srv | tail -1 | sed "s/.*connection authorized: /   pg_central: /"
echo
