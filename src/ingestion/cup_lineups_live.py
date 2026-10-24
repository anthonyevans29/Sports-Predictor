"""
CUPS STEP B, THE LIVE T-15 OBSERVATION STORE (ARCHITECT 2026-10-23, addendum 158 item 3(a); lane cups, #106).

Verbatim: "(a) Step B's wording is reconciled: the HISTORY ingest is done (#538, kind 'history'; #541 keeps it out of
every price). Step B, due 10-29, is the LIVE T-15 observation store: per fixture the scheduled poll time and the actual
observation time, eleven team-mapped starters per side, the FIRST complete observation preserved and every later
correction appended (never replaced: the generic sync-lineups replace-on-answer is not Step B's store), and explicit
rows for failed, partial or late observations. The T-35 inputs and forecast of a declared candidate are kept apart from
the T-15 label. The EFL probe (10-27) gates nothing and does not hold Step B."

Addendum 155 item 3(a), the window it rests on: "the provider's confirmed-lineup window is between T-30 and T-15 for
both cups; the answer carries no stamp, so Step B stores OUR poll time with each lineup, and the T-15 poll is the cups'
standing read".

    python cli.py observe-cup-lineups [--competition CL --competition UEL ...] [--loop] [--dry-run]

How it reads and writes (law 1: every name is the code's own):
- The fixtures: the stored matches of CL, UEL, EFL and FAC (lineups_history.COMPETITIONS, the cups the exam set
  holds) whose stored kickoff (matches.utc_date, UTC) is within WINDOW of now, whose status is not one of
  kalshi_match.NOT_GAMES, with an API-Football fixture id (external_ids["api_football"]). A side is mapped to a stored
  team by its provider id as sync-lineups maps it: the team's own id first, then the ids a merge recorded on it
  (team_merge.source_ids). A side that maps to neither team is counted, never matched by name (law 4).
- The polls, per fixture: POLLS (T-15, the label poll the 155 ruling names; T-5 and T+10, the later reads that catch a
  correction). A poll is DUE when its scheduled time (kickoff - offset) has passed and the store holds no row for
  (fixture, the fixture's CURRENT stored kickoff, poll). A re-dated fixture (a later schedule sync moved
  matches.utc_date) therefore starts a fresh poll set; the old kickoff's rows are kept as they were (Codex on #662). A
  due poll more than MISSED_AFTER past its time gets an explicit 'missed' row and no call. Any other due poll is asked
  once: APIFootballAdapter.list_lineup_confirmed, the call sync-lineups and the Step A probe use, its pace and parse.
  The answer is stamped with OUR clock (observed_at); late is set when that is more than LATE_LIMIT after the
  scheduled time.
- The row (CupLineupObservation, one per fixture, kickoff and poll, APPEND-ONLY): status 'complete' (both stored teams hold
  exactly ELEVEN mapped starters), 'partial' (anything short of that, or an unmapped side), 'empty' (no lineup in the
  answer), 'failed' (the call raised; its error kept), 'missed'. The lineup itself, per side: the team id, formation,
  starters and bench (name, position, shirt number), as the adapter parsed them. is_first_complete marks the first
  complete row of the fixture's kickoff; a later complete row of that kickoff carries differs_from_first (its
  starters, as sets per side, against that first's). Nothing updates or deletes a row: a correction is a new row.
- It writes nothing else. No lineups row (that table is the generic sync-lineups' replace-on-answer store, and the
  pricing's), no candidate input, no forecast: the T-35 inputs and forecast of a declared candidate live apart from
  this T-15 label (158 item 3(a)).
- It writes only when migrate_cup_lineup_observations.py has run (the table AND its marker); --dry-run prints the due
  polls and makes no call and no write. Every read is mode=ro (venue_quote_age.readonly_session), and a missing DB
  file is refused before any session opens: the app's session would create it (law 5; Codex on #662).
- A real tick holds the chains' DB lock (sp_common.sync_lock, #569, as sync-teams and sync-matches do) across the
  due-check, the provider calls and the inserts, so two overlapping runs never ask one poll twice; a run that finds
  it held waits, printing one line. An insert that still meets the unique key (a writer outside the lock) is skipped
  and counted "already observed", its row standing. The adapter is built before any row is written whenever a due
  poll needs a provider call, so a missing key refuses with nothing written (Codex on #662).
- --loop: ticks every TICK seconds until no poll of the window's fixtures remains to be made (each tick is the same
  read-due-ask-append; a re-run never asks a poll that has a row). Without --loop it makes one tick (a timer's run).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from src.ingestion.lineups_history import COMPETITIONS, ELEVEN, SOURCE

POLLS = ((15, "T-15"), (5, "T-5"), (-10, "T+10"))   # (minutes before kickoff, label); T-15 is the label poll
LABEL_POLL = "T-15"
LATE_LIMIT = timedelta(minutes=5)                    # a call more than this after its time is late (kept, flagged)
MISSED_AFTER = timedelta(minutes=30)                 # a due poll this far past its time: an explicit 'missed' row
WINDOW = timedelta(hours=3)                          # fixtures kicking off within this of now are read
TICK = 30.0
TABLE = "cup_lineup_observations"
MIGRATION_MARKER = "cup_lineup_observations_migration"


class Refused(Exception):
    pass


@dataclass
class Tick:
    now: datetime
    fixtures: int = 0
    due: int = 0
    rows: list = field(default_factory=list)          # the rows written (or, in a dry run, that would be)
    remaining: int = 0                                 # polls of the window's fixtures not yet due
    already: int = 0                                   # due polls another run stored first (the unique key; skipped)


def migrated(rs) -> bool:
    """True only when migrate_cup_lineup_observations.py ran: the table AND the marker it alone writes."""
    from sqlalchemy import inspect, text
    try:
        ins = inspect(rs.get_bind())
        if not (ins.has_table(TABLE) and ins.has_table(MIGRATION_MARKER)):
            return False
        return bool(rs.execute(text(f"SELECT COUNT(*) FROM {MIGRATION_MARKER}")).scalar())
    except Exception:  # noqa: BLE001 - an unreadable marker is not a migration
        return False


def _fixtures(s, codes, now) -> list[dict]:
    from sqlalchemy import select

    from src.db.schema import Competition, Match, Team
    from src.ingestion.kalshi_match import NOT_GAMES
    from src.ingestion.team_merge import source_ids
    rows = s.execute(select(Match, Competition.code).join(Competition, Competition.id == Match.competition_id)
                     .where(Competition.code.in_(codes), Match.utc_date >= now - WINDOW,
                            Match.utc_date <= now + WINDOW)
                     .order_by(Match.utc_date, Match.id)).all()
    teams = {t.id: t for t in s.execute(select(Team).where(Team.id.in_(
        {m.home_team_id for m, _ in rows} | {m.away_team_id for m, _ in rows}))).scalars()} if rows else {}
    out = []
    for m, code in rows:
        if str(getattr(m.status, "value", m.status) or "").lower() in NOT_GAMES:
            continue
        ids: dict = {}
        for tid in (m.home_team_id, m.away_team_id):             # sync-lineups' order: own ids first (#467)
            own = (teams[tid].external_ids or {}).get(SOURCE) if tid in teams else None
            if own is not None:
                ids[str(own)] = tid
        for tid in (m.home_team_id, m.away_team_id):
            if tid in teams:
                for sid in source_ids(teams[tid].external_ids, SOURCE):
                    ids.setdefault(sid, tid)
        fid = (m.external_ids or {}).get(SOURCE)
        out.append({"match_id": m.id, "code": code, "kickoff": m.utc_date, "home": m.home_team_id,
                    "away": m.away_team_id, "fixture_id": str(fid) if fid not in (None, "") else None, "ids": ids})
    return out


def lineup_of(answer: list[dict], f: dict) -> tuple[dict, int]:
    """({"home"|"away": {team_id, formation, starters, bench}}, the blocks mapped to neither team), from the adapter's
    parsed slots (team_source_id, formation, is_starter, player_name, player_position, shirt_number)."""
    sides: dict = {}
    unmapped = set()
    for slot in answer:
        tid = f["ids"].get(str(slot.get("team_source_id")))
        side = "home" if tid == f["home"] else "away" if tid == f["away"] else None
        if side is None:
            unmapped.add(str(slot.get("team_source_id")))
            continue
        d = sides.setdefault(side, {"team_id": tid, "formation": slot.get("formation"), "starters": [], "bench": []})
        d["starters" if slot.get("is_starter") else "bench"].append(
            {"name": slot.get("player_name"), "pos": slot.get("player_position"), "number": slot.get("shirt_number")})
    return sides, len(unmapped)


def _starter_set(lineup: dict | None, side: str) -> frozenset:
    return frozenset(p["name"] for p in ((lineup or {}).get(side) or {}).get("starters", []))


def status_of(lineup: dict, unmapped: int) -> str:
    n = {s: len((lineup.get(s) or {}).get("starters", [])) for s in ("home", "away")}
    if not lineup and not unmapped:
        return "empty"
    return "complete" if n["home"] == ELEVEN and n["away"] == ELEVEN and not unmapped else "partial"


def _db_lock():
    """The chains' DB lock (#569 RULED, addendum 153 item 2), as service._db_lock and cli._sync_lock take it:
    sp_common.sync_lock, a no-op when the caller already holds it (a chain step). Waiting prints one line."""
    import sys
    from pathlib import Path
    hosting = str(Path(__file__).resolve().parents[2] / "deploy" / "hosting")
    if hosting not in sys.path:
        sys.path.insert(0, hosting)
    import sp_common
    return sp_common.sync_lock(on_wait=lambda p: print(f"… waiting for the DB lock {p} (a chain or closing run holds "
                                                       "it)", flush=True))


def tick(now: datetime, codes=COMPETITIONS, *, dry_run: bool = False, adapter=None, clock=None) -> Tick:
    """One read-due-ask-append pass (the module docstring). Returns what it wrote (or would). Refuses a missing DB
    file before any session opens (law 5); a real tick runs under the DB lock."""
    from src.walters.venue_quote_age import db_file_path
    path = db_file_path()
    if path is None or not path.is_file():
        raise Refused(f"REFUSED: no DB file at {path or '(DATABASE_URL is not a SQLite file)'}: observe-cup-lineups "
                      "never creates one (law 5). Nothing was asked or written.")
    if dry_run:
        return _tick(now, codes, dry_run=True, adapter=adapter, clock=clock)
    with _db_lock():
        return _tick(now, codes, dry_run=False, adapter=adapter, clock=clock)


def _tick(now: datetime, codes, *, dry_run: bool, adapter, clock) -> Tick:
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError

    from src.db.database import session_scope
    from src.db.schema import CupLineupObservation as Obs
    from src.walters.venue_quote_age import readonly_session
    clock = clock or (lambda: now)
    t = Tick(now=now)
    with readonly_session() as rs:
        ok = migrated(rs)
        if not dry_run and not ok:
            raise Refused("REFUSED: migrate_cup_lineup_observations.py has not run (the table and its marker); this "
                          "command never creates either. --dry-run reads without them.")
        fixtures = _fixtures(rs, codes, now)
        t.fixtures = len(fixtures)
        have: dict = {}                                   # (match id, kickoff) -> {poll label: row}
        if fixtures and ok:
            for o in rs.execute(select(Obs).where(Obs.match_id.in_([f["match_id"] for f in fixtures]))).scalars():
                have.setdefault((o.match_id, o.kickoff_at), {})[o.poll_label] = o
        rs.expunge_all()
    plan = []
    for f in fixtures:
        for off, label in POLLS:
            if label in have.get((f["match_id"], f["kickoff"]), {}):    # done only for the CURRENT kickoff
                continue
            sched = f["kickoff"] - timedelta(minutes=off)
            if sched > now:
                t.remaining += 1
                continue
            plan.append((f, label, sched))
    t.due = len(plan)
    if (not dry_run and adapter is None
            and any(now - sched <= MISSED_AFTER and f["fixture_id"] is not None for f, _, sched in plan)):
        from src.adapters.api_football import APIFootballAdapter
        try:                                              # before any row is written: a refusal writes nothing
            adapter = APIFootballAdapter()
        except ValueError as e:                           # no key: the message names the variable only
            raise Refused(f"REFUSED: {e}") from None
    for f, label, sched in plan:
        row = {"match_id": f["match_id"], "competition": f["code"], "fixture_source_id": f["fixture_id"],
               "kickoff_at": f["kickoff"], "poll_label": label, "scheduled_at": sched, "observed_at": None,
               "late": False, "lineup": None, "home_starters": None, "away_starters": None,
               "unmapped_sides": None, "error": None, "is_first_complete": False, "differs_from_first": None,
               "source": SOURCE}
        if now - sched > MISSED_AFTER:
            row["status"] = "missed"
        elif f["fixture_id"] is None:
            row.update(status="failed", error="no API-Football fixture id on the stored match")
        elif dry_run:
            row["status"] = "(dry run: would ask)"
        else:
            try:
                answer = adapter.list_lineup_confirmed(f["fixture_id"])
            except Exception as e:  # noqa: BLE001 - a failed call is an explicit row, never a stop
                row.update(status="failed", error=f"{type(e).__name__}: {str(e)[:200]}", observed_at=clock())
            else:
                at = clock()
                lineup, unmapped = lineup_of(answer, f)
                row.update(observed_at=at, lineup=lineup or None, unmapped_sides=unmapped,
                           home_starters=len((lineup.get("home") or {}).get("starters", [])),
                           away_starters=len((lineup.get("away") or {}).get("starters", [])),
                           status=status_of(lineup, unmapped))
            row["late"] = row["observed_at"] is not None and row["observed_at"] - sched > LATE_LIMIT
        prior = have.setdefault((f["match_id"], f["kickoff"]), {})
        first = next((o for o in sorted(prior.values(), key=lambda o: o.scheduled_at)
                      if getattr(o, "is_first_complete", False)), None)
        if row["status"] == "complete":
            if first is None:
                row["is_first_complete"] = True
            else:
                row["differs_from_first"] = any(_starter_set(row["lineup"], sd) != _starter_set(first.lineup, sd)
                                                for sd in ("home", "away"))
        if dry_run:
            t.rows.append(row)
            prior[label] = type("Planned", (), {**row})
            continue
        try:
            with session_scope() as s:
                o = Obs(**row)
                s.add(o)
                s.flush()
                s.expunge(o)
        except IntegrityError as e:
            if "UNIQUE" not in str(e.orig):
                raise
            t.already += 1                                # another run stored this poll first: its row stands
            with readonly_session() as rs:
                o = rs.execute(select(Obs).where(Obs.match_id == f["match_id"], Obs.kickoff_at == f["kickoff"],
                                                 Obs.poll_label == label)).scalar_one_or_none()
                rs.expunge_all()
            if o is not None:
                prior[label] = o
            continue
        t.rows.append(row)
        prior[label] = o
    return t


def tick_lines(t: Tick, dry_run: bool) -> list[str]:
    L = [f"observe-cup-lineups · {t.now:%Y-%m-%d %H:%M:%S}Z · fixtures within {int(WINDOW.total_seconds() // 3600)} h "
         f"{t.fixtures} · polls due {t.due} · not yet due {t.remaining}"
         + (" · DRY RUN: no call, nothing written" if dry_run else f" · appended {len(t.rows)} row(s) to {TABLE}")
         + (f" · already observed {t.already} (another run stored them first; skipped)" if t.already else "")]
    for r in t.rows:
        sides = (f" · starters home {r['home_starters']} away {r['away_starters']}"
                 + (f" · unmapped sides {r['unmapped_sides']}" if r["unmapped_sides"] else "")
                 if r["home_starters"] is not None else "")
        flags = (" · FIRST COMPLETE" if r["is_first_complete"] else
                 " · a correction (differs from the first complete)" if r["differs_from_first"] else
                 " · same eleven as the first complete" if r["differs_from_first"] is False else "")
        L.append(f"  {r['competition']} match {r['match_id']} {r['poll_label']} · scheduled {r['scheduled_at']:%H:%M}Z"
                 + (f" · observed {r['observed_at']:%H:%M:%S}Z" if r["observed_at"] else " · no call")
                 + f" · {r['status']}" + (" · LATE" if r["late"] else "") + sides + flags
                 + (f" · {r['error']}" if r["error"] else ""))
    return L


def run(codes=COMPETITIONS, *, loop: bool = False, dry_run: bool = False, echo=print, adapter=None,
        now=None, sleep=time.sleep) -> int:
    from src.timeutil import utc_now_naive
    now = now or utc_now_naive
    while True:
        t = tick(now(), codes, dry_run=dry_run, adapter=adapter, clock=now)
        for ln in tick_lines(t, dry_run):
            echo(ln)
        if not loop or dry_run or not t.remaining:
            return 0
        sleep(TICK)
