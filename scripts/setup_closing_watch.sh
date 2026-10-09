#!/bin/bash
# Installs the CLOSING WATCH (ARCHITECT 2026-10-09, addendum 21 item 3, C2/C7; addendum 22, 380.2) as ONE launchd
# job on the LAPTOP for the three model families (MLB, NFL, SOCCER): `python cli.py closing-watch` every minute
# (StartInterval 60). The watch decides from the stored schedule with no network; at T-35 of a family's earliest
# unstarted start time it starts `closing-run` for the games within the 10 minutes after it. It places nothing and
# never opens Kalshi's trading API. The host runs no timer for it (C7: not before the cutover ruling).
#
# The operator installs it, on the architect's word. Nothing installs itself, and --uninstall is the off switch
# (it also removes #370's MLB-only job, com.sportspredictor.mlbclosingwatch, if one is there).
#
# 380.2 (ARCHITECT): "The setup script reads each required setting where the launched job will find it: the
# checkout's .env or host.env, never the installing shell. A setting present only in the shell refuses the install,
# naming it. [...] No value is written into the plist, and none is printed. The script proves it: it runs the run's
# own refusal checks in the environment the launched job will have, and refuses to install on any refusal." And M2
# for the phone: "At install the script sends one test page through the card topic and says what the operator
# should have seen on his phone."
#
# Usage:   bash scripts/setup_closing_watch.sh
# Remove:  bash scripts/setup_closing_watch.sh --uninstall

set -euo pipefail

# --- resolve paths (run from the repo root, or it figures it out) ---
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${REPO_DIR}/venv/bin/python"
CLI="${REPO_DIR}/cli.py"
CLOSING="${REPO_DIR}/deploy/hosting/closing.py"
LOG_DIR="${REPO_DIR}/logs"
LABEL="com.sportspredictor.closingwatch"
OLD_LABEL="com.sportspredictor.mlbclosingwatch"
PLIST_DIR="${HOME}/Library/LaunchAgents"
PLIST="${PLIST_DIR}/${LABEL}.plist"
OLD_PLIST="${PLIST_DIR}/${OLD_LABEL}.plist"
INTERVAL_S=60
REQUIRED="SP_EXPORTS_MIRROR_REMOTE NTFY_CARD_TOPIC"

if [[ "${1:-}" == "--uninstall" ]]; then
  launchctl unload "${PLIST}" 2>/dev/null || true
  rm -f "${PLIST}"
  echo "removed ${LABEL}"
  if [[ -f "${OLD_PLIST}" ]]; then
    launchctl unload "${OLD_PLIST}" 2>/dev/null || true
    rm -f "${OLD_PLIST}"
    echo "removed ${OLD_LABEL} (#370's MLB-only watch)"
  fi
  echo "✓ closing watch uninstalled (no more ticks; nothing else changed)."
  exit 0
fi

mkdir -p "${LOG_DIR}" "${PLIST_DIR}"

if [[ ! -x "${PYTHON}" ]]; then
  echo "✗ venv python not found at ${PYTHON}"
  echo "  Activate/create your venv first, or edit PYTHON in this script."
  exit 1
fi

# The environment the launched job will have: launchd starts it with no shell profile, so none of the installing
# shell's variables. Only these few, never a setting.
launched_env() {
  env -i HOME="${HOME}" USER="${USER:-}" LOGNAME="${LOGNAME:-${USER:-}}" PATH="/usr/bin:/bin:/usr/sbin:/sbin" \
    "$@"
}

# 380.2: the required settings the INSTALLING shell has set (names only; never a value).
SHELL_SET=""
for name in ${REQUIRED}; do
  if [[ -n "${!name:-}" ]]; then
    SHELL_SET="${SHELL_SET:+${SHELL_SET},}${name}"
  fi
done

# The run's own refusal checks (deploy/hosting/closing.py preflight: a backup folder under data/, SP_SKIP_FAMILIES
# naming a family, SP_EXPORTS_MIRROR_REMOTE unset (M1), NTFY_CARD_TOPIC unset (C6)), in the launched environment,
# from the checkout's working directory, plus "set only in the installing shell".
if ! (cd "${REPO_DIR}" && launched_env "${PYTHON}" "${CLOSING}" preflight --shell-set "${SHELL_SET}"); then
  echo "✗ REFUSED: the closing watch is not installed (a closing run would refuse in the launched environment)."
  echo "  Put each setting in ${REPO_DIR}/.env (or host.env), never only in your shell, then run this script again."
  exit 2
fi

# M2 for the phone (380.2), BEFORE loading: a closing run that cannot page is not a success (C6).
if (cd "${REPO_DIR}" && launched_env "${PYTHON}" "${CLOSING}" test-page); then
  PAGE_RESULT="accepted by ntfy"
else
  echo "✗ REFUSED: ntfy did not accept the test page through the card topic (NTFY_CARD_TOPIC; value not shown)."
  echo "  A closing run that cannot page is not a success, so the watch is not installed. Check the topic, then rerun."
  exit 2
fi

# No value goes into the plist: the job reads the checkout's .env (or host.env) itself.
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
        <string>closing-watch</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${REPO_DIR}</string>
    <key>StartInterval</key>
    <integer>${INTERVAL_S}</integer>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/closing_watch.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/closing_watch.err</string>
</dict>
</plist>
PLISTEOF

if [[ -f "${OLD_PLIST}" ]]; then        # one watch for the three families (C7): #370's MLB-only job goes
  launchctl unload "${OLD_PLIST}" 2>/dev/null || true
  rm -f "${OLD_PLIST}"
  echo "removed ${OLD_LABEL} (#370's MLB-only watch; this one covers MLB)"
fi
launchctl unload "${PLIST}" 2>/dev/null || true
launchctl load "${PLIST}"
echo "loaded ${LABEL} (closing-watch every ${INTERVAL_S}s)"

# M2 (ARCHITECT 2026-10-08): the screen's test notification, what the operator should have seen, where to allow it.
TEST_TITLE="Closing watch"
TEST_BODY="Test: the closing watch is installed"
if osascript -e "display notification \"${TEST_BODY}\" with title \"${TEST_TITLE}\"" >/dev/null 2>&1; then
  NOTE_RESULT="posted"
else
  NOTE_RESULT="NOT posted (osascript failed)"
fi

echo ""
echo "✓ closing watch installed: every minute, for MLB, NFL and SOCCER (PL)."
echo "  Logs: ${LOG_DIR}/closing_watch.log"
echo "  Test now:  ${PYTHON} ${CLI} closing-watch --dry-run"
echo "  Uninstall: bash scripts/setup_closing_watch.sh --uninstall"
echo ""
echo "Test page (phone): ${PAGE_RESULT}."
echo "  On your phone, in the ntfy app subscribed to the card topic, you should have seen a page titled"
echo "  \"Closing watch\" reading \"Test: the closing watch is installed (MLB, NFL, SOCCER). Pages arrive here by T-30.\""
echo "  If it did not arrive: open the ntfy app, check you are subscribed to the card topic (the one in .env,"
echo "  NTFY_CARD_TOPIC), and that the app may send notifications."
echo "Test notification (screen): ${NOTE_RESULT}."
echo "  You should have seen a notification titled \"${TEST_TITLE}\" reading \"${TEST_BODY}\" (top right of the screen)."
echo "  If you did not: System Settings → Notifications → Script Editor (osascript posts as Script Editor):"
echo "  turn on Allow notifications, alert style Banners or Alerts; check Focus / Do Not Disturb is off."
echo ""
echo "The watch needs two things, or no closing runs:"
echo "  1. The laptop awake (a sleeping laptop runs no tick; the lid closed on battery sleeps it)."
echo "  2. VPN on, Tailscale off (the MLB feed: the same network mode as Phase 1 of the morning chain)."
