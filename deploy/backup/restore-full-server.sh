#!/usr/bin/env bash
# Restore the FULL Germany main server from a Mac backup folder.
#
# Run on a FRESH replacement VPS (Ubuntu 24.04) as root.
#
# Usage:
#   sudo bash deploy/backup/restore-full-server.sh \
#     --confirm-new-server \
#     --from-dir ~/NCBackups/latest
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"

FROM_DIR=""
CONFIRM=0
SKIP_PACKAGES=0
SKIP_BUILD=0

usage() {
  cat <<'EOF'
Full-server restore (Germany main VPS)

  restore-full-server.sh --confirm-new-server --from-dir PATH

Required:
  --confirm-new-server   Safety flag — only run on a fresh replacement VPS
  --from-dir PATH        Mac backup folder (e.g. ~/NCBackups/latest)

Options:
  --skip-packages        Skip apt install (if already installed)
  --skip-build           docker compose up without --build (faster)

Before running:
  - Copy backup folder to server OR mount from Mac via scp/rsync
  - Copy /etc/nc-vpn/backup.env to this server (XUI_PG_PASSWORD)

After restore:
  - Update DNS if public IP changed
  - Run: ./scripts/update-pull-sync.sh on your Mac for PL/SG nodes

EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --confirm-new-server) CONFIRM=1; shift ;;
    --from-dir) FROM_DIR="${2:?}"; shift 2 ;;
    --skip-packages) SKIP_PACKAGES=1; shift ;;
    --skip-build) SKIP_BUILD=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown argument: $1 (try --help)" ;;
  esac
done

[[ "$CONFIRM" -eq 1 ]] || die "Refusing to run without --confirm-new-server"
[[ -n "$FROM_DIR" ]] || die "--from-dir is required (Mac backup folder)"

FROM_DIR="$(cd "$FROM_DIR" && pwd)"
[[ -d "$FROM_DIR/files" ]] || die "Invalid backup dir (missing files/): $FROM_DIR"

load_server_config
require_cmd gzip curl

install_packages() {
  log "Installing base packages ..."
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq \
    postgresql postgresql-contrib postgresql-client \
    docker.io docker-compose-plugin \
    ufw fail2ban rsync jq curl ca-certificates gnupg lsb-release
  systemctl enable --now docker postgresql
}

restore_files() {
  log "=== Restoring from Mac backup: $FROM_DIR ==="
  local t
  for t in "${FROM_DIR}/files/"*.tar.gz; do
    [[ -f "$t" ]] || continue
    log "Extract: $(basename "$t")"
    tar xzf "$t" -C /
  done
  log "File restore complete."
}

setup_xui_postgres() {
  log "Preparing native PostgreSQL for 3X-UI ..."
  systemctl enable postgresql
  systemctl start postgresql
  local role_exists db_exists
  role_exists="$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${XUI_PG_USER}'" 2>/dev/null || true)"
  if [[ "$role_exists" != "1" ]]; then
    sudo -u postgres psql -c "CREATE USER \"${XUI_PG_USER}\" WITH PASSWORD '${XUI_PG_PASSWORD}';" \
      || sudo -u postgres createuser "$XUI_PG_USER"
  fi
  db_exists="$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${XUI_PG_DB}'" 2>/dev/null || true)"
  if [[ "$db_exists" != "1" ]]; then
    sudo -u postgres createdb -O "$XUI_PG_USER" "$XUI_PG_DB"
  fi
}

import_xui_db() {
  local dump
  dump="$(find_latest_dump xui "$FROM_DIR")"
  [[ -n "$dump" ]] || die "xui SQL dump not found in $FROM_DIR"
  log "Importing 3X-UI database from $dump ..."
  gunzip -c "$dump" | sudo -u postgres psql -d "$XUI_PG_DB" -v ON_ERROR_STOP=1
  log "xui database imported."
}

ensure_docker_network() {
  local net
  net="$(read_bot_env_var DOCKER_NETWORK 2>/dev/null || echo nexora_net)"
  net="${net:-nexora_net}"
  if ! docker network inspect "$net" >/dev/null 2>&1; then
    log "Creating docker network: $net"
    docker network create "$net"
  fi
}

start_postgres_container() {
  log "Starting bot PostgreSQL container ..."
  [[ -d "${BOT_ROOT}/deploy" ]] || die "Missing ${BOT_ROOT}/deploy"
  cd "${BOT_ROOT}/deploy"
  ./compose.sh up -d postgres redis
  local i
  for i in $(seq 1 30); do
    if docker exec "$BOT_PG_CONTAINER" pg_isready -U "$BOT_PG_USER" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  die "Bot postgres did not become ready"
}

import_bot_db() {
  local dump pw
  dump="$(find_latest_dump nexorabot "$FROM_DIR")"
  [[ -n "$dump" ]] || die "nexorabot SQL dump not found in $FROM_DIR"
  pw="$(bot_postgres_password)" || die "POSTGRES_PASSWORD missing"
  log "Importing bot database from $dump ..."
  gunzip -c "$dump" | docker exec -i -e PGPASSWORD="$pw" "$BOT_PG_CONTAINER" \
    psql -U "$BOT_PG_USER" -d "$BOT_PG_DB" -v ON_ERROR_STOP=1
  log "nexorabot database imported."
}

start_all_services() {
  local build_flag=(--build)
  [[ "$SKIP_BUILD" -eq 1 ]] && build_flag=()

  log "Starting bot stack ..."
  cd "${BOT_ROOT}/deploy"
  ./compose.sh up -d "${build_flag[@]}" bot

  log "Starting admin panel ..."
  [[ -d "$PANEL_ROOT" ]] || die "Missing $PANEL_ROOT"
  cd "$PANEL_ROOT"
  docker compose up -d "${build_flag[@]}"

  log "Starting 3X-UI (xray) ..."
  systemctl daemon-reload
  if [[ -f /etc/systemd/system/x-ui.service ]]; then
    systemctl enable x-ui
    systemctl restart x-ui
  elif [[ -x "${XUI_DIR}/x-ui" ]]; then
    log "WARN: x-ui.service missing — try: ${XUI_DIR}/x-ui start"
    "${XUI_DIR}/x-ui" start 2>/dev/null || true
  fi

  if command -v ufw >/dev/null 2>&1; then
    log "Reloading UFW ..."
    ufw --force enable 2>/dev/null || true
    systemctl restart ufw 2>/dev/null || true
  fi
  systemctl restart fail2ban 2>/dev/null || true
}

set_telegram_webhook() {
  local token domain url
  token="$(read_bot_env_var BOT_TOKEN 2>/dev/null || true)"
  domain="$(read_bot_env_var BOT_DOMAIN 2>/dev/null || true)"
  [[ -n "$token" && -n "$domain" ]] || return 0
  url="https://${domain}/webhook"
  log "Setting Telegram webhook: $url"
  curl -fsS "https://api.telegram.org/bot${token}/setWebhook?url=${url}" >/dev/null \
    || log "WARN: webhook set failed — set manually after DNS propagates"
}

print_migration_checklist() {
  local old_ip new_ip
  old_ip="$(read_meta_public_ip "$FROM_DIR" || true)"
  new_ip="$(curl -4 -fsS --max-time 10 https://ifconfig.me/ip 2>/dev/null || hostname -I | awk '{print $1}')"
  log ""
  log "=============================================="
  log " RESTORE COMPLETE — verify & DNS"
  log "=============================================="
  log ""
  log "Health checks:"
  log "  systemctl status x-ui"
  log "  docker ps"
  log "  curl -k https://p.nexoranode.xyz:2057/  (panel)"
  log "  curl -k https://bot.nexoranode.xyz:8443/webhook"
  log ""
  if [[ -n "$old_ip" && -n "$new_ip" && "$old_ip" != "$new_ip" ]]; then
    log "IP CHANGED: $old_ip -> $new_ip"
    log "Update DNS A-records for panel, bot, manage, sub, bridge."
    log "Then on Mac: ./scripts/update-pull-sync.sh"
  else
    log "IP appears unchanged ($new_ip) — DNS update may not be needed."
  fi
  log ""
  log "Test: /start in bot, buy flow, subscription URL, one VPN connect."
  log "=============================================="
}

main() {
  log "=== NC VPN FULL SERVER restore ==="
  [[ "$(id -u)" -eq 0 ]] || die "Run as root"

  if [[ "$SKIP_PACKAGES" -eq 0 ]]; then
    install_packages
  fi

  restore_files
  setup_xui_postgres
  import_xui_db
  ensure_docker_network
  start_postgres_container
  import_bot_db
  start_all_services
  set_telegram_webhook
  print_migration_checklist
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  trap 'log "RESTORE FAILED — see errors above"; exit 1' ERR
  main "$@"
fi
