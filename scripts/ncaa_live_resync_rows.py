"""
THE NCAA "LIVE, RESYNC NEEDED" ROWS, LISTED (#945; ARCHITECT 2026-11-12 08:25 ET, addendum 348 item 2; 10:55 ET, addendum
354 item 4: "the twenty NCAA "live, resync needed" rows (348 item 2: the read-only listing and what the provider serves
for each)"). Read-only, the database only: no provider call, no write.

348 item 2, verbatim (its sentence on this): "SECOND FINDING, yours to read, one Issue (class finding, sport ncaa): the
TWENTY "live, resync needed" rows — SCHEDULED, no score, kickoffs in 2024 and 2025, found live by id — say what the
provider serves for each (a final score our rows lack because no sync reads a past season's listing, or a status our
map keeps SCHEDULED by law 4), how many fall in the seasons the NCAA candidates trained and tested on, and the
smallest read-only way to list them; no write until I read it."

THE ROWS: `dedupe-matches --orphans`'s stale candidates (src/ingestion/match_dedupe.orphans): an NCAA row that is
SCHEDULED, has no score and carries a provider id (api_american_football), with a kickoff more than STALE_H hours before
--now. A twin-only candidate (a kickoff not yet STALE_H past) is not listed: "live, resync needed" needs the kickoff
past. Which of these the provider still serves (live) is the dry run's by-id read, not this file's: this listing names
the rows; `dedupe-matches --competition NCAA --orphans --sample 30` prints, for each live one, what the provider serves
(its status, status_raw, score and kickoff, #945).

PER ROW: the match id, the provider id, our season, the stored kickoff, our status_raw as stored, and the row's CFBD
side-table label if any: its CFBD season, season type, score in our orientation, fetched_at, and whether it is CURRENT
(L3, ARCHITECT 2026-10-08, addendum 11: "A label is current when its fetched_at equals that of its season's latest
ingest record"; ncaa_cfbd.latest_record_stamps). The D2 stream (ncaa_backtest.load_v1r_games, then v1r_stream) reads
every stored NCAA match with a CURRENT label "whatever our local status or scores", with the label's scores, and walks
those whose label season is one of the candidate's own seasons, except a level score, which it lists and does not
walk. A stale label or none is never walked. So the counts by label season below answer "how many fall in the seasons
the candidates trained and tested on": a current label of a candidate's season, not level, was walked with CFBD's
score. A level score is marked on its row. Labels are read with ncaa_cfbd.label_load_options, so a copy that predates
the season_type (J4) or week (D10) migration is read, not refused (an unloaded season_type prints as none).

--db: a .backup copy outside the repo's data/ (mlb_pitchers_gate.check_db), refused with a -wal / -shm / -journal beside
it (immutable=1 would ignore it), opened mode=ro&immutable=1. Refusals exit 2, nothing read. Exit 0 otherwise. The last
line: NCAA-LIVE-RESYNC-ROWS {json} (counts and ids only).

    python3 scripts/ncaa_live_resync_rows.py --db /path/to/backup-copy.db [--now 2026-11-12T12:00:00]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REFUSED = 2
SOURCE = "api_american_football"
SIDECARS = ("-wal", "-shm", "-journal")      # immutable=1 would ignore each of them
TAIL = "NCAA-LIVE-RESYNC-ROWS"


def collect(s, now: datetime) -> list[dict]:
    """The stale orphan candidates of NCAA on the session's store, each with its label (or none), oldest first."""
    from sqlalchemy import inspect, select

    from src.db.schema import Competition, Match, MatchStatus, NCAACFBDLabel
    from src.ingestion.match_dedupe import STALE_H
    from src.ingestion.ncaa_cfbd import label_load_options

    cut = now - timedelta(hours=STALE_H)
    comp = s.execute(select(Competition).where(Competition.code == "NCAA")).scalar_one_or_none()
    if comp is None:
        return []
    has_labels = inspect(s.connection()).has_table(NCAACFBDLabel.__tablename__)
    stamps, opts = {}, []
    if has_labels:
        from src.ingestion.ncaa_cfbd import latest_record_stamps
        stamps = latest_record_stamps(s)
        opts = label_load_options(s)      # a copy without the J4 / D10 column: never selected, never refused
    rows = s.execute(select(Match).where(Match.competition_id == comp.id, Match.status == MatchStatus.SCHEDULED,
                                         Match.home_score.is_(None), Match.away_score.is_(None),
                                         Match.utc_date.is_not(None), Match.utc_date < cut)
                     .order_by(Match.utc_date, Match.id)).scalars().all()
    out = []
    for m in rows:
        sid = (m.external_ids or {}).get(SOURCE)
        if not sid:
            continue
        lab = (s.execute(select(NCAACFBDLabel).where(NCAACFBDLabel.match_id == m.id).options(*opts))
               .scalar_one_or_none() if has_labels else None)
        label = None
        if lab is not None:
            at = stamps.get(lab.season or "")
            label = {"season": lab.season, "season_type": lab.__dict__.get("season_type"),
                     "score": f"{lab.home_score}-{lab.away_score}", "fetched_at": lab.fetched_at.isoformat(),
                     "current": at is not None and lab.fetched_at == at, "level": lab.home_score == lab.away_score}
        out.append({"id": m.id, "sid": str(sid), "season": m.season, "utc": m.utc_date.isoformat(),
                    "status_raw": m.status_raw, "label": label})
    s.rollback()
    return out


def report(rows: list[dict], db_text: str, now: datetime, echo=print) -> dict:
    from src.ingestion.match_dedupe import STALE_H

    echo(f"NCAA LIVE-RESYNC ROWS · {db_text} · the stale orphan candidates: SCHEDULED, no score, a provider id, "
         f"kickoff more than {STALE_H}h before {now.isoformat()}")
    for r in rows:
        lab = r["label"]
        lt = ("no CFBD label (never walked)" if lab is None else
              f"CFBD label season {lab['season']} {lab['season_type'] or '(no type)'} {lab['score']} fetched "
              f"{lab['fetched_at']} {'CURRENT (L3)' if lab['current'] else 'STALE (kept, never walked)'}"
              f"{' · level score: listed by v1r_stream, not walked' if lab['current'] and lab['level'] else ''}")
        echo(f"  id {r['id']} sid {r['sid']} season {r['season']} {r['utc']} status_raw {r['status_raw']!r} · {lt}")
    by_year = Counter(r["utc"][:4] for r in rows)
    current = Counter(r["label"]["season"] for r in rows if r["label"] and r["label"]["current"])
    level = Counter(r["label"]["season"] for r in rows if r["label"] and r["label"]["current"] and r["label"]["level"])
    stale = Counter(r["label"]["season"] for r in rows if r["label"] and not r["label"]["current"])
    none = sum(1 for r in rows if r["label"] is None)
    echo(f"  rows {len(rows)} · by kickoff year {dict(sorted(by_year.items()))}")
    echo(f"  current CFBD labels (L3) by label season {dict(sorted(current.items()))}, of which level scores (listed, "
         f"not walked) {dict(sorted(level.items()))}: each candidate's D2 stream walks the rest of its own seasons, with "
         f"CFBD's score · stale labels {dict(sorted(stale.items()))} · no label (never walked) {none}")
    echo("  which of these the provider still serves, and what it serves: `dedupe-matches --competition NCAA "
         "--orphans --sample 30` (its [live_resync] lines, #945); this listing calls no provider")
    tail = {"rows": len(rows), "by_kickoff_year": dict(sorted(by_year.items())),
            "current_labels_by_season": dict(sorted(current.items())),
            "current_level_by_season": dict(sorted(level.items())),
            "stale_labels_by_season": dict(sorted(stale.items())), "no_label": none,
            "ids": [r["id"] for r in rows]}
    echo(f"{TAIL} {json.dumps(tail, sort_keys=True)}")
    return tail


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="#945: the NCAA stale orphan candidates and their CFBD labels, read-only")
    ap.add_argument("--db", default=None, help="a .backup copy of the database outside the repo's data/, opened "
                                               "mode=ro&immutable=1 (required)")
    ap.add_argument("--now", default=None, help="the instant the stale rule is read against (ISO, UTC; default now)")
    a = ap.parse_args(argv)
    from src.walters import mlb_pitchers_gate as mp
    try:
        now = datetime.fromisoformat(a.now) if a.now else None
    except ValueError:
        print(f"REFUSED: --now {a.now!r} is not an ISO timestamp; nothing read")
        return REFUSED
    if now is not None and now.tzinfo is not None:
        print(f"REFUSED: --now {a.now!r} carries a UTC offset; give it naive, in UTC; nothing read")
        return REFUSED
    if now is None:
        from src.timeutil import utc_now_naive
        now = utc_now_naive()
    try:
        path = mp.check_db(a.db)
        for sc in SIDECARS:
            if path.with_name(path.name + sc).exists():
                raise mp.GateRefused(f"--db {a.db} has a {sc} sidecar ({path.name + sc}): not a fresh .backup copy; "
                                     "immutable=1 would ignore it and read a stale file; take a fresh .backup copy")
        mp.open_ro(path).close()
    except mp.GateRefused as err:
        print(f"REFUSED: {err}; nothing read")
        return REFUSED
    import sqlite3

    from sqlalchemy.exc import SQLAlchemyError
    db_text = f"--db {path} (a .backup copy, opened {mp.COPY_URI_QUERY.lstrip('?')})"
    lines: list[str] = []
    try:
        with mp.readonly_session(path) as s:
            report(collect(s, now), db_text, now, echo=lines.append)
    except (SQLAlchemyError, sqlite3.Error) as err:     # a copy without the schema the read needs
        why = (str(err).strip().splitlines() or [""])[0]
        print(f"REFUSED: --db {path}: cannot be read as the schema the listing needs ({type(err).__name__}: {why}); "
              "nothing read")
        return REFUSED
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
