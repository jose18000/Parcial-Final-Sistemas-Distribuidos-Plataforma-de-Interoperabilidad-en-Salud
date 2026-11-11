# infra/

El punto de entrada del despliegue es el `docker-compose.yml` de la raíz:

```bash
docker compose down -v && docker compose up -d --build
```

Levanta 7 contenedores: `pg_sede1` (PostgreSQL), `mongo_sede2` (MongoDB), `pg_sede3` (PostgreSQL),
`pg_central` (auditoría), `hapi_fhir_r4`, `hsb_bus` y `api_gateway`. Los puertos del anfitrión se
configuran en `.env` (ver `.env.example`).

`k8s/` — manifiestos de Kubernetes para Minikube (bonus) y el script `desplegar.sh`. Ver los
comentarios de esos archivos para sus requisitos y uso.

La autenticación es JWT emitido por la API (`app/auth.py`); Keycloak no se usa.
