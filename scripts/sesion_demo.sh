# scripts/sesion_demo.sh — prepara la terminal para la demostración (se usa con "source").
#
#     source scripts/sesion_demo.sh
#
# Deja definidas:
#   CURL   curl que verifica HTTPS con la CA de la plataforma (certs/ca.pem)
#   TOKEN  token OAuth 2.0 del cliente herramientas_qa (client_credentials, scopes del bus)
# El token dura 15 minutos: si el bus responde 401 "expired", vuelva a ejecutar este comando.

set -a; . ./.env; set +a
CURL="curl -s --cacert certs/ca.pem"
TOKEN="$($CURL -u "herramientas_qa:${OAUTH_SECRETO_QA}" -d grant_type=client_credentials \
          https://localhost:${API_PORT:-8000}/oauth/token | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')"
export CURL TOKEN
echo "$TOKEN" | python3 -c '
import sys, json, base64, datetime
t = sys.stdin.read().strip()
cab, carga = (json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4))) for p in t.split(".")[:2])
print("Token OAuth 2.0 listo ($TOKEN)")
print("  algoritmo:", cab["alg"], "· kid:", cab["kid"])
print("  cliente:", carga["client_id"], "· audiencia:", carga["aud"], "· scope:", carga["scope"])
print("  vence:", datetime.datetime.fromtimestamp(carga["exp"]).strftime("%H:%M:%S"))'
