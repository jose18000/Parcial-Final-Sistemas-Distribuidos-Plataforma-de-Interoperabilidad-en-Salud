#!/usr/bin/env bash
# infra/k8s/desplegar.sh — despliega la plataforma en Minikube (bonus).
# Uso (desde la raíz del repositorio):   bash infra/k8s/desplegar.sh
# Requisitos: minikube iniciado con al menos 4 GB (minikube start --memory=4096) y kubectl.
set -euo pipefail
NS=clinica-distribuida
cd "$(dirname "$0")/../.."

echo "1/4 Construyendo imágenes dentro del Docker de Minikube"
eval "$(minikube docker-env)"
docker build -t clinica/hsb:v2 -f hsb/Dockerfile .
docker build -t clinica/api:v2 -f app/Dockerfile .

echo "2/4 Namespace y ConfigMaps de inicialización (misma fuente que docker compose)"
kubectl get ns "$NS" >/dev/null 2>&1 || kubectl create namespace "$NS"
crear() { kubectl -n "$NS" create configmap "$1" "${@:2}" --dry-run=client -o yaml | kubectl apply -f -; }
crear init-sede1   --from-file=00_schema.sql=db/schema.sql --from-file=01_init.sql=db/sede1/init.sql
crear init-sede2   --from-file=01_init.js=db/sede2/init-mongo.js
crear init-sede3   --from-file=00_schema.sql=db/schema.sql --from-file=01_init.sql=db/sede3/init.sql
crear init-central --from-file=01_init.sql=db/central/init.sql

echo "3/4 Bases de las sedes y auditoría"
kubectl apply -f infra/k8s/01_postgres_sedes.yaml
kubectl -n "$NS" rollout status deploy/pg-sede1 deploy/mongo-sede2 deploy/pg-sede3 deploy/pg-central --timeout=180s

echo "4/4 HAPI FHIR, HSB y API"
kubectl apply -f infra/k8s/02_hapi_hsb_api.yaml
kubectl -n "$NS" rollout status deploy/hapi-fhir --timeout=360s
kubectl -n "$NS" rollout status deploy/hsb-bus deploy/api-gateway --timeout=180s

IP=$(minikube ip)
echo
echo "Listo:"
echo "  Vistas web : http://$IP:30080"
echo "  HSB        : http://$IP:30081/health"
echo "  HAPI FHIR  : http://$IP:30090/fhir/metadata"
echo "Caída de una sede:  kubectl -n $NS scale deploy/mongo-sede2 --replicas=0   (volver: --replicas=1)"
