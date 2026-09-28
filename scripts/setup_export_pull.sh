#!/bin/bash
# OPTIONAL: installs the hourly laptop pull of the host's exports/ (pull-exports
# lane, 2026-09-28) as a launchd job at :10 past every hour — five minutes after
# the host's :05 window run. Copies land in exports/host/, never the laptop's
# own exports/ (writer of record through the parallel week). Laptop pulls host
# artifacts; push is H2.
#
# On demand (first-class, no install needed):
#          venv/bin/python deploy/hosting/pull_exports.py
# Usage:   bash scripts/setup_export_pull.sh [host]      (default: SP_HOST_ADDR from .env)
# Remove:  bash scripts/setup_export_pull.sh --uninstall

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${REPO_DIR}/venv/bin/python"
LABEL="com.sportspredictor.exportpull"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
LOG_DIR="${REPO_DIR}/logs"

if [[ "${1:-}" == "--uninstall" ]]; then
  launchctl unload "${PLIST}" 2>/dev/null || true
  rm -f "${PLIST}"
  echo "✓ ${LABEL} uninstalled."
  exit 0
fi

HOST_ARGS=""
if [[ -n "${1:-}" ]]; then
  HOST_ARGS="<string>--host</string><string>${1}</string>"
  HOST_DESC="${1}"
elif grep -qE '^SP_HOST_ADDR=.+' "${REPO_DIR}/.env" 2>/dev/null; then
  HOST_DESC="SP_HOST_ADDR from .env"
else
  echo "✗ no host: set SP_HOST_ADDR in ${REPO_DIR}/.env (see .env.example) or pass the address" >&2
  exit 2
fi

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
        <string>${REPO_DIR}/deploy/hosting/pull_exports.py</string>
        ${HOST_ARGS}
    </array>
    <key>WorkingDirectory</key><string>${REPO_DIR}</string>
    <key>StartCalendarInterval</key>
    <dict><key>Minute</key><integer>10</integer></dict>
    <key>StandardOutPath</key><string>${LOG_DIR}/export_pull.log</string>
    <key>StandardErrorPath</key><string>${LOG_DIR}/export_pull.err</string>
</dict>
</plist>
PLISTEOF
launchctl unload "${PLIST}" 2>/dev/null || true
launchctl load "${PLIST}"
echo "✓ ${LABEL} loaded: hourly at :10, pulls from ${HOST_DESC} into exports/host/"
echo "  Test now: ${PYTHON} ${REPO_DIR}/deploy/hosting/pull_exports.py ${1:+--host ${1}}"
