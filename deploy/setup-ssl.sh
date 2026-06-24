#!/usr/bin/env bash
# Obtain Let's Encrypt cert for bot.nexoranode.xyz (HTTP-01 via nginx port 80).
# Run on server: bash /opt/nexoranode-bot/deploy/setup-ssl.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
DOMAIN="${BOT_SSL_DOMAIN:-bot.nexoranode.xyz}"
EMAIL="${BOT_SSL_EMAIL:-admin@nexoranode.xyz}"
WWW="${ROOT}/deploy/nginx/certbot-www"
CERT_DIR="${ROOT}/deploy/nginx/certs"
COMPOSE="docker compose -f ${ROOT}/deploy/docker-compose.prod.yml --env-file ${ENV_FILE}"

echo "=== SSL for ${DOMAIN} (Telegram webhooks require HTTPS) ==="
echo ""

mkdir -p "${WWW}" "${CERT_DIR}"

if ! command -v certbot &>/dev/null; then
  echo "Installing certbot..."
  apt-get update && apt-get install -y certbot
fi

echo "==> Ensure nginx is running on port 80 (serves ACME challenges)"
${COMPOSE} up -d nginx
sleep 2

if [[ -f "${CERT_DIR}/fullchain.pem" && -f "${CERT_DIR}/privkey.pem" ]]; then
  echo "Existing certs in ${CERT_DIR} — renewing..."
  certbot renew --webroot -w "${WWW}" --quiet || true
else
  echo "==> Requesting new certificate (HTTP-01 via ${WWW})"
  certbot certonly \
    --webroot -w "${WWW}" \
    -d "${DOMAIN}" \
    --agree-tos \
    --no-eff-email \
    -m "${EMAIL}" \
    --non-interactive
fi

if [[ ! -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]]; then
  echo "FAIL: certbot did not create /etc/letsencrypt/live/${DOMAIN}/"
  echo "Check: DNS A-record ${DOMAIN} → this server, port 80 reachable, Cloudflare proxy OFF."
  exit 1
fi

cp "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" "${CERT_DIR}/"
cp "/etc/letsencrypt/live/${DOMAIN}/privkey.pem" "${CERT_DIR}/"
chmod 644 "${CERT_DIR}/fullchain.pem"
chmod 600 "${CERT_DIR}/privkey.pem"

echo "==> Restart nginx (switches to HTTPS config on port 8443)"
${COMPOSE} restart nginx
sleep 2

echo "==> Test HTTPS health"
if curl -sf --resolve "${DOMAIN}:8443:127.0.0.1" "https://${DOMAIN}:8443/health" --connect-timeout 5 | grep -q OK; then
  echo "OK: https://${DOMAIN}:8443/health"
else
  echo "WARN: local HTTPS check failed — see: docker logs nexoranode-nginx --tail 20"
fi

echo ""
echo "✅ Certs installed in ${CERT_DIR}"
echo ""
echo "Next:"
echo "  1. In ${ENV_FILE} set:"
echo "       BOT_DOMAIN=${DOMAIN}:8443"
echo "       BOT_USE_HTTPS=true"
echo "  2. bash ${ROOT}/deploy/set-webhook.sh"
echo "  3. bash ${ROOT}/deploy/verify-webhook.sh"
