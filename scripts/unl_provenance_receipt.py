"""
UNL VENUE-INPUT PROVENANCE RECEIPT (ARCHITECT 2026-10-23, addendum 159 item 2; #336) — read-only.

src/walters/intl_provenance.py says what is read (the cohort's input snapshot with each flag's ingest time, the
fixtures whose stored flag changed after their pre-kickoff shadow file, the replayed vs saved probability on those,
the missing files) and how. The DB is the one DATABASE_URL names (else ./data/sports.db); a path with no file is
refused before anything opens it (the receipt never creates a database). One session, rolled back; nothing written;
nothing fetched. The shadow files are read from --export-dir (default exports).

Run:  python3 scripts/unl_provenance_receipt.py [--export-dir exports]
Paste the whole output on #336.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def db_file() -> Path:
    url = os.getenv("DATABASE_URL")
    if not url:
        try:
            from dotenv import load_dotenv
            load_dotenv(".env")
            url = os.getenv("DATABASE_URL")
        except ImportError:
            pass
    url = url or "sqlite:///./data/sports.db"
    if not url.startswith("sqlite:///"):
        raise SystemExit(f"not a SQLite URL ({url.split(':')[0]}): the receipt is SQLite-only")
    return Path(url.replace("sqlite:///", ""))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--export-dir", default="exports", help="where the unl_shadow_*.json files are (default exports)")
    a = ap.parse_args(argv)
    f = db_file()
    if not f.is_file():
        raise SystemExit(f"no database at {f}: the receipt never creates one")
    from src.walters import intl_provenance as ip
    from src.walters import intl_shadow as sh
    try:
        r = ip.receipt(a.export_dir)
    except sh.ShadowRefused as e:
        print(f"REFUSED: {e}")
        return 2
    for line in ip.lines(r):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
