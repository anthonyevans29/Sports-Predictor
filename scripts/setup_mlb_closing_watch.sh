#!/bin/bash
# Installs the MLB closing watch (ARCHITECT 2026-10-08, addendum 13 item 3, Q2, A8) as a launchd job on the LAPTOP:
# `python cli.py mlb-closing-watch` every 5 minutes (StartInterval 300). The watch decides from the stored schedule
# with no network; when a first pitch is 5-65 minutes away and has no successful closing receipt it checks the MLB
# feed and starts `mlb-closing-run` once. It places nothing and never opens Kalshi's trading API.
#
# The operator installs it. Nothing installs itself, and --uninstall is the off switch.
#
# Usage:   bash scripts/setup_mlb_closing_watch.sh
# Remove:  bash scripts/setup_mlb_closing_watch.sh --uninstall

set -euo pipefail

# --- resolve paths (run from the repo root, or it figures it out) ---
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${REPO_DIR}/venv/bin/python"
CLI="${REPO_DIR}/cli.py"
LOG_DIR="${REPO_DIR}/logs"
LABEL="com.sportspredictor.mlbclosingwatch"
PLIST_DIR="${HOME}/Library/LaunchAgents"
PLIST="${PLIST_DIR}/${LABEL}.plist"
INTERVAL_S=300

if [[ "${1:-}" == "--uninstall" ]]; then
  launchctl unload "${PLIST}" 2>/dev/null || true
  rm -f "${PLIST}"
  echo "removed ${LABEL}"
  echo "✓ MLB closing watch uninstalled (no more ticks; nothing else changed)."
  exit 0
fi

mkdir -p "${LOG_DIR}" "${PLIST_DIR}"

if [[ ! -x "${PYTHON}" ]]; then
  echo "✗ venv python not found at ${PYTHON}"
  echo "  Activate/create your venv first, or edit PYTHON in this script."
  exit 1
fi

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
        <string>mlb-closing-watch</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${REPO_DIR}</string>
    <key>StartInterval</key>
    <integer>${INTERVAL_S}</integer>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/mlb_closing_watch.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/mlb_closing_watch.err</string>
</dict>
</plist>
PLISTEOF

launchctl unload "${PLIST}" 2>/dev/null || true
launchctl load "${PLIST}"
echo "loaded ${LABEL} (mlb-closing-watch every ${INTERVAL_S}s)"

echo ""
echo "✓ MLB closing watch installed: every 5 minutes."
echo "  Logs: ${LOG_DIR}/mlb_closing_watch.log"
echo "  Test now:  ${PYTHON} ${CLI} mlb-closing-watch --dry-run"
echo "  Uninstall: bash scripts/setup_mlb_closing_watch.sh --uninstall"
