#!/usr/bin/env bash
# Restore deleted 3X-UI clients from bot vpn_configs — runs on Germany HOST (not Docker).
# Uses curl → 127.0.0.1:2057. No Telegram, no bot DB writes.
#
# Usage:
#   cd /opt/nexoranode-bot
#   ./scripts/restore-panel-clients-host.sh --list-missing
#   ./scripts/restore-panel-clients-host.sh --config-id 53 --config-id 54 --dry-run
#   ./scripts/restore-panel-clients-host.sh --config-id 53 --config-id 54 --config-id 55 --config-id 56
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
PG_CONTAINER="${PG_CONTAINER:-nexoranode-postgres}"
PG_USER="${PG_USER:-nexora}"
PG_DB="${PG_DB:-nexorabot}"

DRY_RUN=0
LIST_MISSING=0
CONFIG_IDS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config-id) CONFIG_IDS+=("$2"); shift 2 ;;
    --list-missing) LIST_MISSING=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

[[ -f "$ENV_FILE" ]] || { echo "Missing $ENV_FILE" >&2; exit 1; }

# shellcheck disable=SC1090
source "$ENV_FILE"

XUI_TOKEN="${XUI_TOKEN:-}"
XUI_BASE_PATH="${XUI_BASE_PATH:-/}"
PANEL_BASE="https://127.0.0.1:2057${XUI_BASE_PATH%/}/"
MS_PER_DAY=86400000

[[ -n "$XUI_TOKEN" ]] || { echo "XUI_TOKEN missing in $ENV_FILE" >&2; exit 1; }

api() {
  local method="$1" path="$2" body="${3:-}"
  if [[ -n "$body" ]]; then
    curl -sk -X "$method" "${PANEL_BASE}${path#/}" \
      -H "Authorization: Bearer ${XUI_TOKEN}" \
      -H "Content-Type: application/json" \
      -d "$body"
  else
    curl -sk -X "$method" "${PANEL_BASE}${path#/}" \
      -H "Authorization: Bearer ${XUI_TOKEN}"
  fi
}

client_exists() {
  local email="$1"
  local resp msg
  resp="$(api GET "panel/api/clients/get/$(python3 -c "import urllib.parse; print(urllib.parse.quote('${email}', safe=''))")")"
  msg="$(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('msg',''))" 2>/dev/null || true)"
  if echo "$msg" | grep -qi 'not found\|یافت نشد'; then
    return 1
  fi
  echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('success') else 1)" 2>/dev/null
}

expiry_ms_for_row() {
  local expiry="$1" plan_days="$2"
  python3 - "$expiry" "$plan_days" "$MS_PER_DAY" <<'PY'
import sys
from datetime import datetime, timezone
expiry, plan_days, ms_day = sys.argv[1], int(sys.argv[2] or 30), int(sys.argv[3])
if expiry and expiry.strip() not in ("", "NULL"):
    dt = datetime.fromisoformat(expiry.replace(" ", "T"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    print(int(dt.timestamp() * 1000))
else:
    print(-plan_days * ms_day)
PY
}

fetch_rows() {
  local ids_csv="$1"
  docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -At -F $'\t' -c \
    "SELECT id, user_id, service_name, panel_email, panel_uuid, subscription_id,
            traffic_limit_bytes, COALESCE(expiry_date::text, ''), is_active, plan_days
     FROM vpn_configs
     ${ids_csv:+WHERE id IN ($ids_csv)}
     ORDER BY id DESC;"
}

list_missing() {
  local line id email
  echo "Missing on panel:"
  while IFS=$'\t' read -r id user_id service_name email uuid sub total expiry active plan_days; do
    [[ -n "$id" ]] || continue
    if client_exists "$email"; then
      continue
    fi
    echo "  id=$id  user=$user_id  name='$service_name'  email='$email'  sub=$sub"
  done < <(fetch_rows "")
}

INBOUND_IDS=""
load_inbound_ids() {
  local resp
  resp="$(api GET panel/api/inbounds/list)"
  INBOUND_IDS="$(echo "$resp" | python3 -c "
import json, sys
data = json.load(sys.stdin)
ids = [str(x['id']) for x in (data.get('obj') or []) if x.get('enable')]
print(','.join(ids))
")"
  [[ -n "$INBOUND_IDS" ]] || { echo "No enabled inbounds" >&2; exit 1; }
}

restore_one() {
  local id="$1"
  local row id_ user_id service_name email uuid sub total expiry active plan_days
  row="$(fetch_rows "$id")"
  [[ -n "$row" ]] || { echo "Config id=$id not in bot DB" >&2; return 1; }
  IFS=$'\t' read -r id_ user_id service_name email uuid sub total expiry active plan_days <<<"$row"

  if client_exists "$email"; then
    echo "SKIP id=$id ($email) — already on panel"
    return 0
  fi

  local expiry_ms inbound_json body
  expiry_ms="$(expiry_ms_for_row "$expiry" "$plan_days")"
  inbound_json="$(python3 -c "import json; print(json.dumps([int(x) for x in '${INBOUND_IDS}'.split(',') if x]))")"

  body="$(python3 - "$email" "$uuid" "$sub" "$total" "$expiry_ms" "$user_id" "$service_name" "$active" "$inbound_json" <<'PY'
import json, sys
email, uuid, sub, total, expiry_ms, tg_id, comment, active, inbounds = sys.argv[1:10]
client = {
    "email": email,
    "uuid": uuid,
    "subId": sub,
    "totalGB": int(total),
    "expiryTime": int(expiry_ms),
    "tgId": int(tg_id),
    "limitIp": 0,
    "enable": active.lower() in ("t", "true", "1"),
    "comment": comment,
    "reset": 0,
}
print(json.dumps({"client": client, "inboundIds": json.loads(inbounds)}))
PY
)"

  echo "Restore id=$id email=$email sub=$sub uuid=$uuid expiry_ms=$expiry_ms inbounds=[$INBOUND_IDS]"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  (dry-run — no panel write)"
    return 0
  fi

  local resp ok msg
  resp="$(api POST panel/api/clients/add "$body")"
  ok="$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('success', False))" 2>/dev/null || echo false)"
  msg="$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('msg',''))" 2>/dev/null || echo "$resp")"
  if [[ "$ok" != "True" && "$ok" != "true" ]]; then
    echo "FAIL id=$id: $msg" >&2
    return 1
  fi
  echo "OK id=$id ($email)"
}

if [[ "$LIST_MISSING" -eq 1 ]]; then
  list_missing
  exit 0
fi

[[ ${#CONFIG_IDS[@]} -gt 0 ]] || {
  echo "Provide --config-id and/or --list-missing" >&2
  exit 1
}

load_inbound_ids
fail=0
for cid in "${CONFIG_IDS[@]}"; do
  restore_one "$cid" || fail=1
done

if [[ "$DRY_RUN" -eq 0 && "$fail" -eq 0 ]]; then
  echo ""
  echo "Triggering node sync (optional)..."
  if [[ -x "$ROOT/../scripts/repair-direct-nodes.sh" ]]; then
    bash "$ROOT/../scripts/repair-direct-nodes.sh" 2>/dev/null || true
  elif [[ -f /opt/VPN_project/scripts/repair-direct-nodes.sh ]]; then
    bash /opt/VPN_project/scripts/repair-direct-nodes.sh 2>/dev/null || true
  else
    echo "  (repair-direct-nodes.sh not found — sync nodes manually if needed)"
  fi
fi

exit "$fail"
