#!/usr/bin/env python3
"""H2-PREP dry run: proves the cutover sequence end-to-end on a scratch DB.
No host, no systemd, no data/: runnable on the laptop as-is.

    python scripts/h2_dry_run.py [--workdir DIR]

1. LAPTOP (scratch): DIR/laptop is a fake checkout with a small SQLite
   (matches / predictions / odds_snapshots), a .env, one export and a
   receipts log.
2. PACK: deploy/hosting/sp_migrate.py pack from it -> DIR/pack (the real
   pack code: .backup API, integrity, sha256, per-table counts).
3. HOST (scratch): deploy/hosting/sp_cutover.py run --dry-run --scratch
   DIR/host --pack DIR/pack (preflight, pause, install, flip, resume,
   receipt), systemctl recorded never run.
4. FRESH-FINGERPRINT compare, as the runbook does it after the first host
   chain: compare_exports.py <laptop exports> <host exports> --since 1.

DIR defaults to a new temp dir; it must not be under the checkout's data/
and must be empty. Everything stays under DIR (kept for inspection).
Exit 0 only when every stage passes.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HOSTING = Path(__file__).resolve().parents[1] / "deploy" / "hosting"
sys.path.insert(0, str(HOSTING))
import compare_exports  # noqa: E402
import sp_common as c  # noqa: E402
import sp_cutover  # noqa: E402
import sp_migrate  # noqa: E402


def build_laptop(laptop: Path) -> Path:
    db = laptop / "data" / "sports.db"          # a scratch checkout's data/, under DIR — never the repo's
    db.parent.mkdir(parents=True)
    con = sqlite3.connect(db)
    con.executescript("""
        CREATE TABLE matches(id INTEGER PRIMARY KEY, home TEXT, away TEXT, status TEXT);
        CREATE TABLE predictions(id INTEGER PRIMARY KEY, match_id INT, p_home REAL);
        CREATE TABLE odds_snapshots(id INTEGER PRIMARY KEY, match_id INT, price REAL);
        INSERT INTO matches VALUES (1,'NYY','BOS','finished'),(2,'LAD','SF','scheduled'),(3,'CHC','STL','postponed');
        INSERT INTO predictions VALUES (1,1,0.55),(2,2,0.61);
        INSERT INTO odds_snapshots VALUES (1,1,1.91),(2,1,1.87),(3,2,2.05),(4,2,2.10);""")
    con.commit()
    con.close()
    (laptop / ".env").write_text("# scratch laptop .env\nDATABASE_URL=sqlite:///./data/sports.db\n")
    today = datetime.now(timezone.utc).date().isoformat()
    (laptop / "exports").mkdir()
    (laptop / "exports" / f"nfl_predictions_{today}.json").write_text(json.dumps(
        {"git_sha": "dryrun", "predictions": [
            {"home_team": "KC", "away_team": "BUF", "utc_date": f"{today}T20:25", "p_home": 0.58}]}))
    return db


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workdir", type=Path, default=None)
    a = ap.parse_args(argv)
    work = (a.workdir or Path(tempfile.mkdtemp(prefix="sp-h2-dry-"))).resolve()
    c.refuse_under_data(work)
    if work.exists() and any(work.iterdir()):
        raise SystemExit(f"✗ REFUSED: {work} exists and is not empty.")
    work.mkdir(parents=True, exist_ok=True)
    laptop, pack, host = work / "laptop", work / "pack", work / "host"
    print(f"H2 DRY RUN in {work}\n== 1. scratch laptop + 2. pack")
    with sp_cutover.isolated():
        laptop.mkdir()
        db = build_laptop(laptop)
        c.REPO, c.HOST_ENV, c._DOTENV_CACHE = laptop, work / "no-host.env", None
        os.environ.update(SP_RECEIPTS=str(laptop / "logs" / "receipts.jsonl"),
                          SP_LOCK=str(laptop / "logs" / "db.lock"),
                          DATABASE_URL=f"sqlite:///{db}")
        if c.db_path() != db.resolve():
            raise SystemExit(f"✗ REFUSED: pack source resolved to {c.db_path()}, not the scratch DB")
        c.append_receipt({"kind": "h2-dry-run-seed", "exit": 0})   # so the pack carries a receipts log
        if sp_migrate.pack(pack) != 0:
            print("FAIL at pack")
            return 1
    print("== 3. host cutover sequence (dry run)")
    if sp_cutover.main(["run", "--pack", str(pack), "--dry-run", "--scratch", str(host)]) != 0:
        print("H2 DRY RUN: FAIL")
        return 1
    print("== 4. fresh-fingerprint compare (laptop last exports vs host exports, --since 1)")
    rc = compare_exports.main([str(laptop / "exports"), str(host / "repo" / "exports"), "--since", "1"])
    print(f"H2 DRY RUN: {'PASS' if rc == 0 else 'FAIL'} (scratch kept at {work})")
    return rc


if __name__ == "__main__":
    sys.exit(main())
