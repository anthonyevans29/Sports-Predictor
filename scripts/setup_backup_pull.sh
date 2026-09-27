#!/bin/bash
# Installs the nightly laptop pull of the host's newest daily .backup (hosting
# H0-14 second layer) as a launchd job: 22:00 local, catch-up on wake. The copy
# lands in ~/sp-backups (the laptop's own backed-up disk), never under data/.
#
# Usage:   bash scripts/setup_backup_pull.sh [host]      (default sp-vps-1)
# Remove:  bash scripts/setup_backup_pull.sh --uninstall

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${REPO_DIR}/venv/bin/python"
LABEL="com.sportspredictor.backuppull"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
LOG_DIR="${REPO_DIR}/logs"

if [[ "${1:-}" == "--uninstall" ]]; then
  launchctl unload "${PLIST}" 2>/dev/null || true
  rm -f "${PLIST}"
  echo "✓ ${LABEL} uninstalled."
  exit 0
fi

HOST="${1:-sp-vps-1}"
mkdir -p "${LOG_DIR}" "$(dirname "${PLIST}")"
cat > "${PLIST}" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>${LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON}</string>
        <string>${REPO_DIR}/deploy/hosting/pull_backup.py</string>
        <string>--host</string><string>${HOST}</string>
    </array>
    <key>WorkingDirectory</key><string>${REPO_DIR}</string>
    <key>StartCalendarInterval</key>
    <dict><key>Hour</key><integer>22</integer><key>Minute</key><integer>0</integer></dict>
    <key>StandardOutPath</key><string>${LOG_DIR}/backup_pull.log</string>
    <key>StandardErrorPath</key><string>${LOG_DIR}/backup_pull.err</string>
</dict>
</plist>
PLISTEOF
launchctl unload "${PLIST}" 2>/dev/null || true
launchctl load "${PLIST}"
echo "✓ ${LABEL} loaded: nightly 22:00 local, pulls from ${HOST} into ~/sp-backups"
echo "  Test now: ${PYTHON} ${REPO_DIR}/deploy/hosting/pull_backup.py --host ${HOST}"
