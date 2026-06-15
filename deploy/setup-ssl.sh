#!/usr/bin/env bash
# Obtain Let's Encrypt cert for bot.nexoranode.xyz via DNS challenge.
# Run on the server: bash deploy/setup-ssl.sh
set -euo pipefail

DOMAIN="bot.nexoranode.xyz"
CERT_DIR="$(cd "$(dirname "$0")" && pwd)/nginx/certs"

echo "=== SSL setup for ${DOMAIN} ==="
echo ""
echo "Port 443 is used by Reality, so we use DNS challenge (not HTTP)."
echo ""

if ! command -v certbot &>/dev/null; then
    echo "Installing certbot..."
    apt-get update && apt-get install -y certbot
fi

mkdir -p "${CERT_DIR}"

echo "Starting certbot DNS challenge..."
echo "Certbot will ask you to add a TXT record to your DNS."
echo ""

certbot certonly \
    --manual \
    --preferred-challenges dns \
    --agree-tos \
    --no-eff-email \
    -m admin@nexoranode.xyz \
    -d "${DOMAIN}"

cp "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" "${CERT_DIR}/"
cp "/etc/letsencrypt/live/${DOMAIN}/privkey.pem" "${CERT_DIR}/"
chmod 644 "${CERT_DIR}/fullchain.pem"
chmod 600 "${CERT_DIR}/privkey.pem"

echo ""
echo "✅ Certs copied to ${CERT_DIR}"
echo "Now restart nginx:"
echo "  cd /opt/nexoranode-bot"
echo "  docker compose -f deploy/docker-compose.prod.yml restart nginx"
