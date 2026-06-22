#!/usr/bin/env bash
# Build full-server backup bundle on Germany VPS (for Mac pull).
#
# Output: /var/lib/nc-vpn-backup/export/latest/
#   dumps/  meta/  config/  files/*.tar.gz
#
# Usage:
#   sudo bash deploy/backup/run-local-backup.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
BUNDLE="${LOCAL_EXPORT_DIR}/${TS}"

main() {
  load_server_config
  require_cmd gzip pg_dump docker curl tar

  log "=== NC VPN local export start ($TS) ==="
  mkdir -p "${BUNDLE}/dumps" "${BUNDLE}/meta" "${BUNDLE}/config" "${BUNDLE}/files"

  export_system_state "${BUNDLE}/meta"
  dump_xui_db "${BUNDLE}/dumps" "$TS"
  dump_bot_db "${BUNDLE}/dumps" "$TS"
  copy_config_snapshots "${BUNDLE}/config"
  archive_backup_paths "${BUNDLE}/files"

  echo "$TS" >"${BUNDLE}/timestamp.txt"
  du -sh "${BUNDLE}" | awk '{print "total_size=" $1}' >"${BUNDLE}/meta/size.txt"

  link_latest_export "$BUNDLE"
  prune_local_exports

  log "=== Local export OK: ${LOCAL_EXPORT_DIR}/latest ($(du -sh "${BUNDLE}" | cut -f1)) ==="
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  trap 'notify_failure "local export failed"; exit 1' ERR
  main "$@"
fi
