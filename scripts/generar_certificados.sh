#!/usr/bin/env bash
# ============================================================================
#  scripts/generar_certificados.sh
#  Autoridad certificadora (CA) propia y certificados TLS de cada servidor.
#
#  certs/ca.pem                 CA de la plataforma (todos los servicios confían solo en ella)
#  certs/<servicio>.crt / .key  api, hsb, hapi, pg_sede1, pg_sede3, pg_central, mongo_sede2
#  certs/mongo_sede2.pem        certificado + clave juntos (formato que pide MongoDB)
#  certs/hapi.p12               almacén PKCS#12 para HAPI FHIR (Java / Spring Boot)
#  certs/oauth_firma.key/.pub   par RSA con el que la API firma los tokens OAuth 2.0 (RS256)
#
#  Es idempotente: la CA y la clave de firma se conservan; los certificados se rehacen solo si
#  faltan, vencen en menos de 30 días o cambió la lista de nombres/IP (p. ej. otra red Wi-Fi).
#  certs/ no se versiona (.gitignore).
# ============================================================================
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$DIR/certs"; cd "$DIR/certs"
command -v openssl >/dev/null || { echo "Falta openssl (sudo apt-get install -y openssl)"; exit 1; }

CLAVE_P12="${HAPI_KEYSTORE_PASSWORD:-hapi_keystore_2026}"
CERT_IPS_EXTRA="${CERT_IPS_EXTRA:-}"
IPS="$(hostname -I 2>/dev/null || true)"
# CERT_IPS_EXTRA (en .env): IPs desde las que se entra a la plataforma y que no son de la VM,
# p. ej. la del PC anfitrión cuando la VM está en NAT con reenvío de puertos.
EXTRA_IP=""; for ip in $IPS ${CERT_IPS_EXTRA//,/ }; do case "$ip" in *:*|172.1[6-9].*|172.2[0-9].*|172.3[01].*) ;; *) EXTRA_IP="$EXTRA_IP,IP:$ip" ;; esac; done

# ── CA ──────────────────────────────────────────────────────────────────────
# Las extensiones keyUsage y basicConstraints críticas las exige la verificación estricta de
# Python 3.13+ (VERIFY_X509_STRICT); una CA anterior sin ellas se reemplaza (y con ella todo).
if [ -f ca.pem ] && ! openssl x509 -in ca.pem -noout -ext keyUsage 2>/dev/null | grep -q "Certificate Sign"; then
  echo "   CA anterior sin keyUsage: se regenera la CA y todos los certificados"
  rm -f ca.key ca.pem ca.srl ./*.san
fi
if [ ! -f ca.key ] || [ ! -f ca.pem ]; then
  openssl genrsa -out ca.key 4096 2>/dev/null
  openssl req -x509 -new -key ca.key -sha256 -days 3650 -out ca.pem \
    -subj "/C=CO/O=Red IPS Sucre-Bolivar/OU=Plataforma de Interoperabilidad Clinica/CN=CA Plataforma Interoperabilidad" \
    -addext "basicConstraints=critical,CA:TRUE,pathlen:0" -addext "keyUsage=critical,keyCertSign,cRLSign" \
    -addext "subjectKeyIdentifier=hash"
  echo "   CA creada: certs/ca.pem"
  touch .renovados
fi

# ── Certificado de un servidor ─────────────────────────────────────────────
certificado() {  # certificado NOMBRE "SAN"
  local n="$1" san="$2"
  if [ -f "$n.crt" ] && [ -f "$n.key" ] && [ "$(cat "$n.san" 2>/dev/null)" = "$san" ] \
     && openssl x509 -checkend 2592000 -noout -in "$n.crt" >/dev/null 2>&1; then
    return 0
  fi
  openssl genrsa -out "$n.key" 2048 2>/dev/null
  openssl req -new -key "$n.key" -out "$n.csr" -subj "/C=CO/O=Red IPS Sucre-Bolivar/CN=$n"
  printf "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth,clientAuth\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\nsubjectAltName=%s\n" "$san" > "$n.ext"
  touch .renovados
  openssl x509 -req -in "$n.csr" -CA ca.pem -CAkey ca.key -CAcreateserial -out "$n.crt" -days 825 -sha256 \
    -extfile "$n.ext" 2>/dev/null
  rm -f "$n.csr" "$n.ext"
  echo "$san" > "$n.san"
  echo "   certificado $n.crt  ($san)"
}

LOCAL="DNS:localhost,IP:127.0.0.1"
certificado api         "DNS:api,DNS:api_gateway,$LOCAL$EXTRA_IP"
certificado hsb         "DNS:hsb,DNS:hsb_bus,$LOCAL$EXTRA_IP"
certificado hapi        "DNS:hapi-fhir,DNS:hapi_fhir_r4,$LOCAL"
certificado pg_sede1    "DNS:pg_sede1,$LOCAL"
certificado pg_sede3    "DNS:pg_sede3,$LOCAL"
certificado pg_central  "DNS:pg_central,$LOCAL"
certificado mongo_sede2 "DNS:mongo_sede2,$LOCAL"

cat mongo_sede2.crt mongo_sede2.key > mongo_sede2.pem
if [ ! -f hapi.p12 ] || [ hapi.crt -nt hapi.p12 ]; then
  openssl pkcs12 -export -in hapi.crt -inkey hapi.key -certfile ca.pem -name hapi -out hapi.p12 -passout "pass:$CLAVE_P12"
fi

# ── Clave de firma de los tokens OAuth 2.0 ─────────────────────────────────
if [ ! -f oauth_firma.key ]; then
  openssl genrsa -out oauth_firma.key 2048 2>/dev/null
  echo "   clave de firma OAuth 2.0 creada: certs/oauth_firma.key"
fi
openssl rsa -in oauth_firma.key -pubout -out oauth_firma.pub 2>/dev/null

# Claves privadas solo para el dueño; lo público legible. (Los contenedores las copian con el
# dueño correcto al arrancar: ver db/seguridad/*.sh). hapi.p12 está protegido por contraseña.
chmod 600 ./*.key mongo_sede2.pem
chmod 644 ./*.crt ca.pem oauth_firma.pub hapi.p12
echo "   certificados al día en certs/ (CA: $(openssl x509 -noout -subject -in ca.pem | sed 's/.*CN *= *//'))"
