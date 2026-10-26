"""
NCAA PREGAME METADATA RECEIPT (ARCHITECT 2026-10-23, addendum 158 item 1(c)) — read-only, counts only.

Verbatim: "(c) With (b): a read-only pregame metadata receipt for the 2026 fixtures — orientation and neutral status
as known BEFORE kickoff (the CFBD labels are post-game; D8 needs pregame neutral), their observation times, and the
Kalshi benchmark's coverage (D11). Counts only."

src/walters/ncaa_pregame.py says what is read and how. The DB is the one DATABASE_URL names (else ./data/sports.db);
a path with no file is refused before anything opens it (the receipt never creates a database). One mode=ro session
(no connect hook, no PRAGMA); nothing written; nothing fetched. The saved CFBD payloads are read from --payload-dir (default exports/cfbd).

Run:  python3 scripts/ncaa_pregame_metadata_receipt.py [--season 2026] [--payload-dir exports/cfbd]
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
    ap.add_argument("--season", default="2026", help="the season as the DB stores it (default 2026)")
    ap.add_argument("--payload-dir", default="exports/cfbd", help="the saved CFBD payloads (default exports/cfbd)")
    a = ap.parse_args(argv)
    f = db_file()
    if not f.is_file():
        raise SystemExit(f"no database at {f}: the receipt never creates one")
    from src.walters import ncaa_pregame as npg
    for line in npg.lines(npg.receipt(a.season, a.payload_dir, db_path=f)):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
