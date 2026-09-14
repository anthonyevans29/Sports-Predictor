#!/bin/bash
# Sets up four daily odds-capture jobs (08:00, 12:00, 16:00, 20:00 local) via
# launchd, for closing-line-value tracking. Each job runs `capture-odds`, which
# is odds-only and does NOT disturb your morning predict routine.
#
# launchd note: if the Mac is asleep at a scheduled time, the job runs at the
# next wake (StartCalendarInterval is catch-up-on-wake by default). It won't
# fire if the machine is fully powered off through the window.
#
# Usage:   bash scripts/setup_clv_capture.sh
# Remove:  bash scripts/setup_clv_capture.sh --uninstall

set -euo pipefail

# --- resolve paths (run from the repo root, or it figures it out) ---
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${REPO_DIR}/venv/bin/python"
CLI="${REPO_DIR}/cli.py"
LOG_DIR="${REPO_DIR}/logs"
LABEL_PREFIX="com.sportspredictor.captureodds"
PLIST_DIR="${HOME}/Library/LaunchAgents"

mkdir -p "${LOG_DIR}" "${PLIST_DIR}"

HOURS=(8 12 16 20)

if [[ "${1:-}" == "--uninstall" ]]; then
  for H in "${HOURS[@]}"; do
    LABEL="${LABEL_PREFIX}.h${H}"
    PLIST="${PLIST_DIR}/${LABEL}.plist"
    launchctl unload "${PLIST}" 2>/dev/null || true
    rm -f "${PLIST}"
    echo "removed ${LABEL}"
  done
  echo "✓ CLV capture jobs uninstalled."
  exit 0
fi

if [[ ! -x "${PYTHON}" ]]; then
  echo "✗ venv python not found at ${PYTHON}"
  echo "  Activate/create your venv first, or edit PYTHON in this script."
  exit 1
fi

for H in "${HOURS[@]}"; do
  LABEL="${LABEL_PREFIX}.h${H}"
  PLIST="${PLIST_DIR}/${LABEL}.plist"
  cat > "${PLIST}" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON}</string>
        <string>${CLI}</string>
        <string>capture-odds</string>
        <string>--sport</string>
        <string>mlb</string>
        <string>--competition</string>
        <string>MLB</string>
        <string>--season</string>
        <string>2026</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${REPO_DIR}</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>${H}</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/capture_odds.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/capture_odds.err</string>
</dict>
</plist>
PLISTEOF

  launchctl unload "${PLIST}" 2>/dev/null || true
  launchctl load "${PLIST}"
  echo "loaded ${LABEL} (fires daily at ${H}:00 local)"
done

echo ""
echo "✓ Four CLV capture jobs installed (08:00, 12:00, 16:00, 20:00 local)."
echo "  Logs: ${LOG_DIR}/capture_odds.log"
echo "  Test now:  ${PYTHON} ${CLI} capture-odds --sport mlb"
echo "  Uninstall: bash scripts/setup_clv_capture.sh --uninstall"
