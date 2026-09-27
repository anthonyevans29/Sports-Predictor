#!/usr/bin/env python3
"""SQLite online-backup (the `.backup` API — sqlite3_backup via Python's
Connection.backup, the same mechanism as the sqlite3 CLI's `.backup`), then
PRAGMA integrity_check on the COPY, sha256, a `.sha256` sidecar and a receipt.

    sp_backup.py daily        -> sports_YYYY-MM-DD.db   (second run same day: _HHMM suffix)
    sp_backup.py prerefresh   -> sports_YYYY-MM-DD_prerefresh_HHMM.db

Never `cp` of the live file; never writes under data/ (law 5). The source is
opened read-only. Exit 0 only when the copy is complete and integrity is ok.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_common as c  # noqa: E402


def backup_dir() -> Path:
    return Path(c.setting("SP_BACKUP_DIR") or Path.home() / "backups" / "sports-predictor")


def target_name(kind: str, now) -> str:
    day = now.strftime("%Y-%m-%d")
    if kind == "prerefresh":
        return f"sports_{day}_prerefresh_{now.strftime('%H%M')}.db"
    return f"sports_{day}.db"


def run_backup(kind: str, lock: bool = True) -> dict:
    src = c.db_path()
    dest_dir = backup_dir()
    c.refuse_under_data(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    now = c.utc_now()
    dest = dest_dir / target_name(kind, now)
    if dest.exists():  # never overwrite an existing backup
        dest = dest.with_name(dest.stem + f"_{now.strftime('%H%M%S')}.db")
    tmp = dest.with_suffix(".db.partial")
    rec = {"kind": "backup", "backup_kind": kind, "file": dest.name, "exit": 1,
           "sha256": None, "integrity": None, "bytes": None}
    try:
        ctx = c.db_lock() if lock else _null()
        with ctx:
            s = c.ro_connect(src)
            d = sqlite3.connect(tmp)
            try:
                s.backup(d)
            finally:
                d.close()
                s.close()
        os.chmod(tmp, 0o600)
        rec["integrity"] = c.integrity(tmp)
        if rec["integrity"] != "ok":
            raise RuntimeError(f"integrity_check: {rec['integrity']}")
        tmp.rename(dest)
        rec["sha256"] = c.sha256_file(dest)
        rec["bytes"] = dest.stat().st_size
        dest.with_name(dest.name + ".sha256").write_text(f"{rec['sha256']}  {dest.name}\n")
        rec["exit"] = 0
    except Exception as e:  # receipt first, then fail loudly
        rec["error"] = c.redact(f"{type(e).__name__}: {e}")
        tmp.unlink(missing_ok=True)
    c.append_receipt(rec)
    return rec


class _null:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def todays_daily() -> Path | None:
    """Today's (UTC) daily backup if present AND its sidecar sha matches."""
    d = backup_dir()
    day = c.utc_now().strftime("%Y-%m-%d")
    for p in sorted(d.glob(f"sports_{day}*.db")):
        if "prerefresh" in p.name:
            continue
        side = p.with_name(p.name + ".sha256")
        if side.exists() and side.read_text().split()[0] == c.sha256_file(p):
            return p
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("kind", choices=["daily", "prerefresh"])
    a = ap.parse_args(argv)
    c.load_host_env()
    rec = run_backup(a.kind)
    mark = "✓" if rec["exit"] == 0 else "✗"
    print(f"{mark} backup {rec['backup_kind']}: {rec['file']} integrity={rec['integrity']} "
          f"sha256={(rec['sha256'] or '-')[:16]} bytes={rec['bytes']}"
          + (f" error={rec['error']}" if rec.get("error") else ""))
    return rec["exit"]


if __name__ == "__main__":
    sys.exit(main())
