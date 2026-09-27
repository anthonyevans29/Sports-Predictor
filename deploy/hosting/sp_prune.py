#!/usr/bin/env python3
"""Backup retention (H0-14, ruled 2026-09-27: 14 dailies). REPORT-ONLY unless
SP_PRUNE_APPLY=1, which stays off until the first manual prune is reviewed;
until then the receipt lists what would be deleted.

Rules (defaults overridable in host.env):
- the newest SP_KEEP_DAILY (14) daily backups are never deleted;
- other dailies older than SP_RETAIN_DAYS (14) are eligible;
- an event backup (_prerefresh_ / _precleanup_) younger than 30 days is
  never deleted.
Only files named sports_YYYY-MM-DD*.db (+ their .sha256) in SP_BACKUP_DIR are
ever considered.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_common as c  # noqa: E402
import sp_backup  # noqa: E402

NAME = re.compile(r"^sports_(\d{4}-\d{2}-\d{2})(.*)\.db$")


def plan(d: Path, now: datetime, keep_daily: int, retain_days: int) -> list[Path]:
    dailies, pre = [], []
    for p in d.glob("sports_*.db"):
        m = NAME.match(p.name)
        if not m:
            continue
        day = datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
        (pre if "_pre" in m.group(2) else dailies).append((day, p))
    dailies.sort(reverse=True)
    protected = {p for _, p in dailies[:keep_daily]}
    doomed = [p for day, p in dailies if p not in protected and now - day > timedelta(days=retain_days)]
    doomed += [p for day, p in pre if now - day > timedelta(days=30)]
    return sorted(doomed)


def main() -> int:
    c.load_host_env()
    d = sp_backup.backup_dir()
    c.refuse_under_data(d)
    apply = c.setting("SP_PRUNE_APPLY") == "1"
    doomed = plan(d, c.utc_now(), int(c.setting("SP_KEEP_DAILY") or 14),
                  int(c.setting("SP_RETAIN_DAYS") or 14))
    if apply:
        for p in doomed:
            p.unlink(missing_ok=True)
            p.with_name(p.name + ".sha256").unlink(missing_ok=True)
    c.append_receipt({"kind": "prune", "exit": 0, "applied": apply,
                      "files": [p.name for p in doomed]})
    print(f"{'deleted' if apply else 'would delete (report-only)'}: {len(doomed)} "
          f"{[p.name for p in doomed]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
