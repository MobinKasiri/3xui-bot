#!/usr/bin/env bash
# Schedule daily backup pull to Mac at 3:00 AM (local Mac time).
#
# Usage (from repo root or bot folder):
#   bash deploy/backup/mac/install-mac-backup.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
PULL_SCRIPT="${BOT_ROOT}/deploy/backup/mac/pull-backup-to-mac.sh"
CONFIG_DIR="${HOME}/.config/nc-vpn"
CONFIG_FILE="${CONFIG_DIR}/mac-backup.env"
LAUNCH_AGENTS="${HOME}/Library/LaunchAgents"
PLIST="${LAUNCH_AGENTS}/com.nc.vpn.backup-pull.plist"
LOG_DIR="${HOME}/NCBackups/logs"

mkdir -p "$CONFIG_DIR" "$LOG_DIR" "$LAUNCH_AGENTS"

if [[ ! -f "$CONFIG_FILE" ]]; then
  if [[ -f "${HOME}/.config/nexora/mac-backup.env" ]]; then
    cp "${HOME}/.config/nexora/mac-backup.env" "$CONFIG_FILE"
    echo "Migrated ~/.config/nexora/mac-backup.env -> $CONFIG_FILE"
  else
    cp "${SCRIPT_DIR}/mac-backup.env.example" "$CONFIG_FILE"
    echo "Created ${CONFIG_FILE} — edit SERVER_HOST and SSH key path."
  fi
fi

chmod +x "$PULL_SCRIPT"

# Remove legacy launchd job if present
launchctl bootout "gui/$(id -u)/com.nexora.backup-pull" 2>/dev/null || true
rm -f "${LAUNCH_AGENTS}/com.nexora.backup-pull.plist"

cat >"$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.nc.vpn.backup-pull</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${PULL_SCRIPT}</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>NC_MAC_BACKUP_ENV</key>
    <string>${CONFIG_FILE}</string>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>3</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/launchd-out.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/launchd-err.log</string>
  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/com.nc.vpn.backup-pull" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/com.nc.vpn.backup-pull"

echo ""
echo "=============================================="
echo " NC VPN backup scheduled: every day at 3:00 AM"
echo "=============================================="
echo ""
echo "Config:  ${CONFIG_FILE}"
echo "Script:  ${PULL_SCRIPT}"
echo "Backups: ~/NCBackups/YYYY-MM-DD/ (keep 4 versions)"
echo "Logs:    ${LOG_DIR}/"
echo ""
echo "Edit SSH settings:"
echo "  nano ${CONFIG_FILE}"
echo ""
echo "Test now (manual pull):"
echo "  bash ${PULL_SCRIPT}"
echo ""
echo "Check schedule:"
echo "  launchctl print gui/$(id -u)/com.nc.vpn.backup-pull"
echo ""
