#!/usr/bin/env bash
# Install LOCAL backup on Germany server (Mac pull at 3 AM).
#
# Usage:
#   cd /opt/nexoranode-bot
#   sudo bash deploy/backup/install-local-backup.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/usr/local/lib/nc-vpn-backup"
ENV_FILE="/etc/nc-vpn/backup.env"
LEGACY_ENV="/etc/nexora/backup.env"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash $0"
  exit 1
fi

echo "==> Installing packages ..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq postgresql-client gzip curl tar rsync ca-certificates

mkdir -p /etc/nc-vpn /var/lib/nc-vpn-backup/export "${INSTALL_DIR}"
chmod 700 /etc/nc-vpn

if [[ -f "$LEGACY_ENV" && ! -f "$ENV_FILE" ]]; then
  cp -a "$LEGACY_ENV" "$ENV_FILE"
  echo "Migrated $LEGACY_ENV -> $ENV_FILE"
fi

install -m 755 "${SCRIPT_DIR}/lib.sh" "${INSTALL_DIR}/lib.sh"
install -m 755 "${SCRIPT_DIR}/run-local-backup.sh" "${INSTALL_DIR}/run-local-backup.sh"
install -m 755 "${SCRIPT_DIR}/restore-full-server.sh" "${INSTALL_DIR}/restore-full-server.sh"

if [[ ! -f "$ENV_FILE" ]]; then
  install -m 600 "${SCRIPT_DIR}/backup.local.env.example" "$ENV_FILE"
  echo "Created $ENV_FILE — set XUI_PG_PASSWORD"
else
  echo "Kept existing $ENV_FILE"
fi

echo ""
echo "=============================================="
echo " NC VPN local backup installed"
echo "=============================================="
echo ""
echo "1. Edit server config:"
echo "     sudo nano ${ENV_FILE}"
echo ""
echo "2. Test export on server:"
echo "     sudo ${INSTALL_DIR}/run-local-backup.sh"
echo "     ls -la /var/lib/nc-vpn-backup/export/latest/"
echo ""
echo "3. On your Mac — install 3 AM pull:"
echo "     bash deploy/backup/mac/install-mac-backup.sh"
echo ""
