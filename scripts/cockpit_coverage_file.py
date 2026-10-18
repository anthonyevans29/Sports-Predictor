"""
TODAY TAB (#589; ARCHITECT 2026-10-18, addendum 125 item 2) helper for the headless Cockpit verify: a coverage_v1
file written by the REAL command, `python cli.py coverage --json --out PATH`, on a SCRATCH database built from the
ORM's own schema (src/db/schema.py, Base.metadata.create_all) in a temporary folder. Never data/: DATABASE_URL,
SP_RECEIPTS and SP_HOST_ENV all point inside the folder, so neither the operator's DB, the watch's receipts nor
host.env is read. The day is TOMORROW in US Eastern (every closing group is ahead of the page's clock, so each one
carries a countdown), with one closing run already receipted for it (a done group). `all_done=True` (--all-done)
receipts a run for every closing group of the day as well (PL's and NFL's tiles then hold done groups only, and the
line's closing clause ends "none left to run").

    python3 scripts/cockpit_coverage_file.py [DIR] [--all-done]     # prints the console and the file's path

The scratch day: PL (LIVE: one production soccer_elo_poisson row; two games with rows, one without, one postponed),
NFL (LIVE: predict-nfl; no rows, a gap), NHL (MARKET-ONLY, shadow v7 where nhl-daily runs), NCAA (MARKET-ONLY) and
EL1 (UNKNOWN).
"""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
NY = ZoneInfo("America/New_York")
COMPS = [(1, "SOCCER", "PL"), (2, "NFL", "NFL"), (3, "NHL", "NHL"), (4, "NFL", "NCAA"), (5, "SOCCER", "EL1")]


def scratch_day(now: datetime | None = None):
    """(tomorrow in US Eastern, its noon ET as UTC)."""
    now = now or datetime.now(timezone.utc)
    day = now.astimezone(NY).date() + timedelta(days=1)
    return day, datetime.combine(day, time(12), tzinfo=NY).astimezone(timezone.utc)


def build_db(path: Path, noon: datetime) -> dict:
    """The scratch DB: the ORM's tables, then the day's rows. Returns {code: [match ids]}."""
    from sqlalchemy import create_engine
    sys.path.insert(0, str(ROOT))
    from src.db.schema import Base
    eng = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(eng)
    eng.dispose()
    fmt = "%Y-%m-%d %H:%M:%S.000000"
    at = lambda h: (noon + timedelta(hours=h)).strftime(fmt)  # noqa: E731
    games = [(401, 1, at(2), "SCHEDULED"), (402, 1, at(2), "SCHEDULED"), (403, 1, at(4.5), "SCHEDULED"),
             (404, 1, at(4.5), "POSTPONED"), (301, 2, at(5), "SCHEDULED"), (501, 3, at(7), "SCHEDULED"),
             (502, 3, at(7.5), "SCHEDULED"), (601, 4, at(4), "SCHEDULED"), (704, 5, at(2), "SCHEDULED")]
    con = sqlite3.connect(path)
    try:
        con.executemany("INSERT INTO competitions(id, sport, code, name, area, type, external_ids) "
                        "VALUES (?, ?, ?, ?, 'scratch', 'LEAGUE', '{}')", [(i, s, c, c) for i, s, c in COMPS])
        con.executemany("INSERT INTO teams(id, sport, name, external_ids) VALUES (?, 'SOCCER', ?, '{}')",
                        [(1, "Home FC"), (2, "Away & Sons <Utd>")])        # markup in a name: the page escapes it
        con.executemany("INSERT INTO matches(id, sport, competition_id, season, utc_date, status, home_team_id, "
                        "away_team_id, external_ids) VALUES (?, 'SOCCER', ?, '2026', ?, ?, 1, 2, '{}')", games)
        computed = (noon - timedelta(hours=3)).strftime(fmt)
        con.executemany("INSERT INTO predictions(match_id, model_version, computed_at, home_win_prob, away_win_prob, "
                        "factor_breakdown) VALUES (?, 'v22', ?, 0.5, 0.3, '{}')", [(401, computed), (402, computed)])
        con.execute("INSERT INTO model_versions(sport, model_family, version, status, parameters, created_at) "
                    "VALUES ('SOCCER', 'soccer_elo_poisson', 'v22', 'production', '{}', ?)", (computed,))
        con.commit()
    finally:
        con.close()
    out: dict = {}
    for mid, cid, _, st in games:
        out.setdefault(dict((i, c) for i, _, c in COMPS)[cid], []).append(mid)
    return out


def _receipt(fam: str, run_id: str, start: str, ids: list[int]) -> str:
    """closing.run's receipt line for one successful run (read-only by the command)."""
    return json.dumps({"kind": "closing", "family": fam, "run_id": run_id, "trigger": "watch", "start": start,
                       "exit": 0, "covers": [{"match_id": i, "start": start} for i in ids],
                       "closing_file": {"file": f"exports/closing_{fam}_{start[:13]}{start[14:16]}Z.json"}}) + "\n"


def make(folder: str | None = None, now: datetime | None = None, all_done: bool = False) -> dict:
    """Build the scratch DB and run the real command on it. {path, doc, console, day, rc}. `all_done`: every closing
    group of the day has a successful run receipted (none left to run)."""
    d = Path(folder or tempfile.mkdtemp(prefix="coverage-scratch-"))
    d.mkdir(parents=True, exist_ok=True)
    day, noon = scratch_day(now)
    db = d / "scratch.db"
    build_db(db, noon)
    at = lambda h: (noon + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
    lines = [_receipt("SOCCER", "scratch-soccer-closing", at(2), [401, 402])]
    if all_done:
        lines += [_receipt("SOCCER", "scratch-soccer-closing-2", at(4.5), [403]),
                  _receipt("NFL", "scratch-nfl-closing", at(5), [301])]
    (d / "receipts.jsonl").write_text("".join(lines))
    out = d / f"coverage_{day.isoformat()}.json"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db}", "SP_RECEIPTS": str(d / "receipts.jsonl"),
           "SP_HOST_ENV": str(d / "no-host.env")}
    for k in ("SP_SKIP_FAMILIES", "SP_NHL_ACTIVE_FROM"):
        env.pop(k, None)
    r = subprocess.run([sys.executable, str(ROOT / "cli.py"), "coverage", "--date", day.isoformat(), "--json",
                        "--out", str(out)], cwd=d, env=env, capture_output=True, text=True)
    doc = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
    return {"path": str(out), "doc": doc, "console": r.stdout + r.stderr, "day": day.isoformat(), "rc": r.returncode}


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--all-done"]
    res = make(args[0] if args else None, all_done="--all-done" in sys.argv[1:])
    print(res["console"], end="")
    print(f"exit {res['rc']} · {res['path']}")
    sys.exit(res["rc"])
