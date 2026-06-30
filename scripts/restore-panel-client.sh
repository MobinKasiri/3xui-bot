#!/usr/bin/env bash
# Recreate deleted 3X-UI clients from bot vpn_configs (no Telegram, no bot DB writes).
#
# Usage:
#   cd /opt/nexoranode-bot
#   ./scripts/restore-panel-client.sh --list-missing
#   ./scripts/restore-panel-client.sh --config-id 42 --dry-run
#   ./scripts/restore-panel-client.sh --config-id 42 --config-id 43
set -euo pipefail

CONTAINER="${BOT_CONTAINER:-nexoranode-bot}"
PY="/app/scripts/restore_panel_client.py"

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "Bot container '$CONTAINER' is not running." >&2
  echo "Start with: ./deploy/compose.sh up -d bot" >&2
  exit 1
fi

if ! docker exec "$CONTAINER" test -f "$PY"; then
  echo "Missing $PY inside '$CONTAINER'." >&2
  echo "On the server run:" >&2
  echo "  cd /opt/nexoranode-bot && ./deploy/pull.sh && ./deploy/compose.sh up -d --build bot" >&2
  exit 1
fi

exec docker exec -i "$CONTAINER" poetry run python "$PY" "$@"
