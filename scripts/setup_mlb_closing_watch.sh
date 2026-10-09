#!/bin/bash
# Installs the MLB closing watch (ARCHITECT 2026-10-08, addendum 13 item 3, Q2, A8) as a launchd job on the LAPTOP:
# `python cli.py mlb-closing-watch` every 5 minutes (StartInterval 300). The watch decides from the stored schedule
# with no network; when a first pitch is 5-65 minutes away and has no successful closing receipt it checks the MLB
# feed and starts `mlb-closing-run` once. It places nothing and never opens Kalshi's trading API.
#
# The operator installs it. Nothing installs itself, and --uninstall is the off switch. It refuses to install when
# SP_EXPORTS_MIRROR_REMOTE is not set (M1), and posts a test notification at install (M2).
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

# M1 (ARCHITECT 2026-10-08): "A closing run pushes the mirror or it is not a success. If SP_EXPORTS_MIRROR_REMOTE is
# not set, mlb-closing-run refuses before the first step, receipted, naming the setting, and the setup script
# refuses to install." Read the way the run reads it (sp_common.setting: the environment, host.env, the checkout's
# .env), so the two can never disagree.
if ! "${PYTHON}" -c 'import sys; sys.path.insert(0, sys.argv[1]); import sp_common as c; sys.exit(0 if (c.setting("SP_EXPORTS_MIRROR_REMOTE") or "").strip() else 1)' "${REPO_DIR}/deploy/hosting"; then
  echo "✗ REFUSED: SP_EXPORTS_MIRROR_REMOTE is not set (environment, host.env, ${REPO_DIR}/.env)."
  echo "  A closing run pushes the exports mirror or it is not a success, so the watch is not installed."
  echo "  Set it in ${REPO_DIR}/.env (docs/specs/exports-mirror.md), then run this script again."
  exit 2
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

# M2 (ARCHITECT 2026-10-08): "The setup script posts a test notification at install, says what the operator should
# have seen, and where to allow it if he did not. It also prints the two things the watch needs: the laptop awake, and
# VPN on with Tailscale off."
TEST_TITLE="MLB closing"
TEST_BODY="Test: the MLB closing watch is installed"
if osascript -e "display notification \"${TEST_BODY}\" with title \"${TEST_TITLE}\"" >/dev/null 2>&1; then
  NOTE_RESULT="posted"
else
  NOTE_RESULT="NOT posted (osascript failed)"
fi

echo ""
echo "✓ MLB closing watch installed: every 5 minutes."
echo "  Logs: ${LOG_DIR}/mlb_closing_watch.log"
echo "  Test now:  ${PYTHON} ${CLI} mlb-closing-watch --dry-run"
echo "  Uninstall: bash scripts/setup_mlb_closing_watch.sh --uninstall"
echo ""
echo "Test notification: ${NOTE_RESULT}."
echo "  You should have seen a notification titled \"${TEST_TITLE}\" reading \"${TEST_BODY}\" (top right of the screen)."
echo "  If you did not: System Settings → Notifications → Script Editor (osascript posts as Script Editor):"
echo "  turn on Allow notifications, alert style Banners or Alerts; check Focus / Do Not Disturb is off."
echo ""
echo "The watch needs two things, or no closing runs:"
echo "  1. The laptop awake (a sleeping laptop runs no tick; the lid closed on battery sleeps it)."
echo "  2. VPN on, Tailscale off (the MLB feed: the same network mode as Phase 1 of the morning chain)."
