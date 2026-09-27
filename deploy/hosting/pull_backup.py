#!/usr/bin/env python3
"""LAPTOP side, nightly (H0-14 second layer, ruled 2026-09-27): pull the host's
newest daily .backup over the tailnet into the laptop's own backed-up disk.
$0 and off-provider.

    python deploy/hosting/pull_backup.py [--host sp-vps-1] [--dest ~/sp-backups]

- Lists the host's backup dir over ssh and takes the newest DAILY
  (prerefresh copies are not pulled).
- scp's the file and its .sha256 sidecar to <dest>/<name>.partial.
- Verifies the sha256 against the sidecar, and runs a read-only
  integrity_check.
- Only then renames it into place (mode 0600) and appends a receipt
  (kind "pull") to this machine's receipts log.
- Already pulled with the same sha = a receipted no-op.
- Refuses a --dest under the checkout's data/ (law 5).
- The laptop copy is never pruned automatically.
Installed as a launchd job by scripts/setup_backup_pull.sh.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_common as c  # noqa: E402

REMOTE_DIR = "/var/backups/sports-predictor"
DAILY = re.compile(r"^sports_\d{4}-\d{2}-\d{2}(_\d{6})?\.db$")


def newest_daily(names: list[str]) -> str | None:
    """Lexical max over daily names: a same-day re-run's _HHMMSS suffix sorts
    after the plain name ('_' > '.'), so it is correctly the newer one."""
    daily = sorted(n.strip() for n in names if DAILY.match(n.strip()))
    return daily[-1] if daily else None


def verify_and_place(partial: Path, sidecar: Path, final: Path) -> dict:
    want = sidecar.read_text().split()[0]
    got = c.sha256_file(partial)
    if got != want:
        raise RuntimeError(f"sha256 mismatch: sidecar {want[:12]} vs pulled {got[:12]}")
    integ = c.integrity(partial)
    if integ != "ok":
        raise RuntimeError(f"integrity_check: {integ}")
    os.chmod(partial, 0o600)
    partial.rename(final)
    sidecar.rename(final.with_name(final.name + ".sha256"))
    return {"sha256": got, "integrity": integ, "bytes": final.stat().st_size}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pull the host's newest daily .backup.")
    ap.add_argument("--host", default="sp-vps-1")
    ap.add_argument("--user", default="sp")
    ap.add_argument("--dest", type=Path, default=Path.home() / "sp-backups")
    a = ap.parse_args(argv)
    dest = a.dest.expanduser()
    c.refuse_under_data(dest)
    dest.mkdir(parents=True, exist_ok=True)
    remote = f"{a.user}@{a.host}"
    rec = {"kind": "pull", "exit": 1, "from": a.host, "file": None}
    try:
        ls = subprocess.run(["ssh", "-o", "BatchMode=yes", remote, f"ls -1 {REMOTE_DIR}"],
                            capture_output=True, text=True, timeout=60, check=True).stdout
        name = newest_daily(ls.splitlines())
        if name is None:
            raise RuntimeError("no daily backup on the host")
        rec["file"] = name
        final = dest / name
        side_remote = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", remote, f"cat {REMOTE_DIR}/{name}.sha256"],
            capture_output=True, text=True, timeout=60, check=True).stdout.split()[0]
        if final.exists() and c.sha256_file(final) == side_remote:
            rec.update(exit=0, sha256=side_remote, note="already present")
        else:
            partial, sidecar = dest / (name + ".partial"), dest / (name + ".sha256.partial")
            for src, dst in ((name, partial), (name + ".sha256", sidecar)):
                subprocess.run(["scp", "-q", "-o", "BatchMode=yes",
                                f"{remote}:{REMOTE_DIR}/{src}", str(dst)],
                               timeout=1800, check=True)
            rec.update(verify_and_place(partial, sidecar, final), exit=0)
    except Exception as e:  # receipt first, then fail loudly
        rec["error"] = c.redact(f"{type(e).__name__}: {e}")[:300]
        for p in dest.glob("*.partial"):
            p.unlink(missing_ok=True)
    c.append_receipt(rec)
    print(f"{'✓' if rec['exit'] == 0 else '✗'} pull {rec['file']} from {a.host}: "
          f"sha256={(rec.get('sha256') or '-')[:16]} {rec.get('note') or rec.get('error') or ''}")
    return rec["exit"]


if __name__ == "__main__":
    sys.exit(main())
