#!/usr/bin/env python3
"""Boot receipt (H0-3: reboots appear in the receipts log). Run once per boot
by sp-boot-receipt.service. Records the boot id, kernel, uptime, the previous
boot's last journal time, and the last unattended-upgrades log line (the
usual reason for a 04:30 reboot). Anything unreadable is null (law 4)."""
from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_common as c  # noqa: E402


def _read(p: str) -> str | None:
    try:
        return Path(p).read_text().strip()
    except OSError:
        return None


def _prev_boot_end() -> str | None:
    try:
        out = subprocess.run(["journalctl", "--list-boots", "--no-pager"],
                             capture_output=True, text=True, timeout=20).stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        return None
    boots = [x for x in out if x.strip() and not x.lstrip().startswith("IDX")]
    return " ".join(boots[-2].split()[-4:]) if len(boots) >= 2 else None


def _uu_last() -> str | None:
    t = _read("/var/log/unattended-upgrades/unattended-upgrades.log")
    return t.splitlines()[-1][:200] if t else None


def main() -> int:
    c.load_host_env()
    up = _read("/proc/uptime")
    rec = c.append_receipt({
        "kind": "boot", "exit": 0,
        "boot_id": _read("/proc/sys/kernel/random/boot_id"),
        "kernel": platform.release(),
        "uptime_s": float(up.split()[0]) if up else None,
        "prev_boot_last_entry": _prev_boot_end(),
        "reason": _uu_last(),
    })
    print(f"boot receipt: {rec['boot_id']} kernel {rec['kernel']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
