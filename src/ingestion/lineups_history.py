"""
CUP LINEUP HISTORY, the ingest (ARCHITECT 2026-10-15 10:16 ET, addendum 74 item 1; addendum 71's Step B; lane #106),
verbatim in part (docs/ledger/entries/2026-10-15-cups-plan.md): "storing each fixture's starting eleven and bench per
side in the existing lineups table (read its columns first, law 1; add nothing to the table unless the eleven cannot
be stored as it is), idempotent, paced at the adapter's limit, with a coverage receipt per competition-season
(fixtures with both elevens / fixtures). The seasons are the exam set's (the re-exam's pot) and 2025/26; the pulls are
the operator's blocks after my read of the dry run."

    python cli.py sync-lineups-history --competition CL|UEL|EFL|FAC --season YYYY [--dry-run] [--max-calls N]
                                       [--save DIR]

How it reads and writes, so the receipt can be checked against it (law 1: every name below is the code's own):
- The table as it stands (src/db/schema.py Lineup: match_id, team_id, kind, formation, is_starter, player_name,
  player_position, shirt_number, source, refreshed_at). The eleven and the bench are stored as rows; no column is
  added. Each row is kind HISTORY_KIND ("history"), never "confirmed": training.recent_xi_freq_by_team reads every
  team's last kind == "confirmed" starters across competitions, so a backfilled cup XI stored as confirmed would become
  every club's "regulars" in the live PL lineup_adjustment. source is the adapter's ("api_football"); refreshed_at is
  the ingest time: a row carries no publication time (the provider sends none), so it says nothing about WHEN the
  lineup became readable (#106, the as-of question, pending).
- The fixtures: the stored matches of the competition-season (Match.season as the DB stores it: "2025/26"; a bare
  2025 is read by the adapter's own rule and the mapping printed) whose status is FINISHED, in kickoff order. A
  fixture's provider id is external_ids["api_football"], as sync-lineups reads it; a row without one is never asked.
- One call per fixture: APIFootballAdapter.list_lineup_confirmed (one /fixtures/lineups?fixture=<id> read through the
  adapter's own throttle, 60 / API_FOOTBALL_RPM seconds a request, and its own single 429 retry), the adapter's parser
  (the payload keys in KEYS). A side is mapped to a stored team by its provider id as sync-lineups maps it (the team's
  own id first, then the ids a merge recorded on it, team_merge.source_ids); a side that maps to neither team is
  counted, never matched by name (law 4).
- Idempotent: a fixture whose two teams each hold exactly ELEVEN history starters is skipped (no call, no write). Any
  other fixture is asked; per side present in the answer its history rows are deleted (match_id, team_id, kind) and
  rewritten, one session per fixture. Rows of any other kind (sync-lineups' projected / confirmed) are never touched.
  A fixture whose answer gave fewer than two elevens is asked again on the next run (nothing records an answer that
  stored nothing).
- --dry-run reads the DB mode=ro (never creates one), prints the plan before any call, then makes the reads up to
  --max-calls and prints what would be stored; it writes nothing (the lineups table need not exist).
- --max-calls (default MAX_CALLS): one lineup call counts one; the run stops cleanly before a call past the cap,
  keeps what it stored, and prints where it stopped. The HTTP requests are printed beside it by status (the adapter's
  429 retry makes two of one call). A payload error (API-Football's errors block: a quota or plan refusal) or a 429
  after the adapter's retry stops the run (asking on would spend the cap on refusals); any other failed call is
  listed and the run goes on (the next run asks it again). A 401 or 403 (the key or the plan refused) stops it too.
  Nothing is retried in the run.
- --save DIR keeps each answer whole (<fixture id>.json), so the kept payloads the tests read can come from a real run
  (never under data/).

The coverage receipt, per competition-season, every stored fixture in exactly one line:
  fixtures = both + one + none + failed + not asked + no fixture id
- both: each of the two stored teams holds exactly ELEVEN history starters after the run (a dry run: the table plus
  what would be stored), stored now or by an earlier run.
- one / none: asked and answered this run, and one / neither stored side holds eleven; none is split by why (an empty
  answer, sides short of eleven, a side whose id maps to neither team, team blocks whose every slot had no name).
- failed: the call failed (listed). not asked: left by the cap or a stop. no fixture id: never asked.
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from dataclasses import dataclass, field

import requests

HISTORY_KIND = "history"
COMPETITIONS = ("CL", "UEL", "EFL", "FAC")
ELEVEN = 11
MAX_CALLS = 100
STOP_STATUSES = (401, 403, 429)  # the run stops: the key or plan refused, or a 429 after the adapter's own retry
SOURCE = "api_football"
# The one place the payload's keys are named, as APIFootballAdapter.list_lineup_confirmed reads them.
KEYS = {"response": "response", "team": "team", "team_id": "id", "formation": "formation",
        "starters": "startXI", "bench": "substitutes", "player": "player", "name": "name", "pos": "pos",
        "number": "number", "errors": "errors"}


class Refused(Exception):
    """A refusal before any call or write."""


class Capped(Exception):
    """The run reached --max-calls."""


@dataclass
class Fixture:
    match_id: int
    fixture_id: str | None
    kickoff: object
    home_id: int
    away_id: int
    ids: dict                                    # provider id -> stored team id (own first, then merged)


@dataclass
class Run:
    code: str
    season: str
    dry_run: bool
    fixtures: int = 0
    no_fixture_id: int = 0
    already: int = 0
    to_ask: int = 0
    both: int = 0
    one: int = 0
    none: Counter = field(default_factory=Counter)
    failed: list = field(default_factory=list)
    not_asked: int = 0
    calls: int = 0
    http: Counter = field(default_factory=Counter)
    rows: int = 0
    sides: int = 0
    fixtures_written: int = 0
    anomalies: list = field(default_factory=list)
    lines: list = field(default_factory=list)
    stopped: str = ""


def stored_season(code: str, season: str) -> str:
    """The season as the DB stores it for these competitions: "2025/26" as given; a bare 2025 by the adapter's own
    rule (api_football: a competition outside _SINGLE_YEAR_SEASON_CODES spans two years)."""
    from src.adapters.api_football import _SINGLE_YEAR_SEASON_CODES
    s = str(season).strip()
    if re.fullmatch(r"\d{4}", s) and code not in _SINGLE_YEAR_SEASON_CODES:
        return f"{s}/{str(int(s) + 1)[-2:]}"
    return s


def refuse_save_dir(save: str) -> None:
    """Law 5 for --save, before anything is created: the target, resolved, is never data/ or under it, by path and by
    file identity (a symlink, or another letter case on a case-insensitive disk, reaching data/: every existing
    ancestor is compared with os.path.samefile), as nfl_predict.refuse_out_path guards --out (#433)."""
    from pathlib import Path

    from src.walters.unl_ladders import data_dir
    tgt, data = Path(save).expanduser().resolve(), data_dir()

    def same(a, b) -> bool:
        try:
            return os.path.samefile(a, b)
        except OSError:
            return False
    if tgt == data or data in tgt.parents or (data.exists() and any(
            anc.exists() and same(anc, data) for anc in (tgt, *tgt.parents))):
        raise Refused(f"REFUSED: --save {save} reaches data/ ({data}): ingest files are never written under it "
                      "(law 5); nothing is asked or stored")


def _plan(code: str, season: str):
    """(competition id, the season's fixtures, history starters per (match, team), whether the table exists),
    read mode=ro. Refuses before any call: not one of the four, not in the DB, no finished fixture under the
    season (the stored seasons listed), UEL rows stored under EL."""
    from sqlalchemy import func, inspect, select

    from src.db.schema import Competition, Match, MatchStatus, Sport, Team
    from src.ingestion.team_merge import source_ids
    from src.walters.venue_quote_age import readonly_session

    with readonly_session() as rs:
        comps = {c.code: c for c in rs.execute(select(Competition).where(
            Competition.code.in_((code, "EL")))).scalars()
                 if str(getattr(c.sport, "value", c.sport)).lower() == Sport.SOCCER.value}

        def finished_by_season(cid):
            return dict(rs.execute(select(Match.season, func.count()).where(
                Match.competition_id == cid, Match.status == MatchStatus.FINISHED).group_by(Match.season)).all())
        comp = comps.get(code)
        el = finished_by_season(comps["EL"].id).get(season, 0) if code == "UEL" and "EL" in comps else 0
        if comp is None:
            raise Refused(f"REFUSED: competition {code} is not in the DB: sync-competitions, sync-teams and "
                          "sync-matches first; nothing is asked or stored"
                          + (f" (EL holds {el} finished fixture(s) under {season}: the Europa League is stored "
                             "under EL there; it is never read as UEL silently)" if el else ""))
        seasons = finished_by_season(comp.id)
        if not seasons.get(season):
            listed = ", ".join(f"{s} {n}" for s, n in sorted(seasons.items(), key=lambda x: str(x[0]))) or "none"
            raise Refused(f"REFUSED: {code} holds no finished fixture under season {season!r} (finished fixtures "
                          f"by stored season: {listed})"
                          + (f"; EL holds {el} under {season}: the Europa League is stored under EL there, and is "
                             "never read as UEL silently" if el else "") + "; nothing is asked or stored")
        comp_id = comp.id
        matches = list(rs.execute(select(Match).where(
            Match.competition_id == comp.id, Match.season == season, Match.status == MatchStatus.FINISHED)
            .order_by(Match.utc_date, Match.id)).scalars())
        teams = {t.id: t for t in rs.execute(select(Team).where(Team.id.in_(
            {m.home_team_id for m in matches} | {m.away_team_id for m in matches}))).scalars()}
        fixtures = []
        for m in matches:
            ids: dict = {}
            for tid in (m.home_team_id, m.away_team_id):
                own = (teams[tid].external_ids or {}).get(SOURCE) if tid in teams else None
                if own is not None:
                    ids[str(own)] = tid
            for tid in (m.home_team_id, m.away_team_id):       # sync-lineups' order: own ids first (#467)
                if tid in teams:
                    for sid in source_ids(teams[tid].external_ids, SOURCE):
                        ids.setdefault(sid, tid)
            fid = (m.external_ids or {}).get(SOURCE)
            fixtures.append(Fixture(m.id, str(fid) if fid not in (None, "") else None, m.utc_date,
                                    m.home_team_id, m.away_team_id, ids))
        has_table = inspect(rs.get_bind()).has_table("lineups")
        held: dict = {}
        if has_table and fixtures:
            from src.db.schema import Lineup
            held = {(mid, tid): n for mid, tid, n in rs.execute(
                select(Lineup.match_id, Lineup.team_id, func.count()).where(
                    Lineup.kind == HISTORY_KIND, Lineup.is_starter.is_(True),
                    Lineup.match_id.in_([f.match_id for f in fixtures]))
                .group_by(Lineup.match_id, Lineup.team_id)).all()}
    return comp_id, fixtures, held, has_table


def _both(f: Fixture, held: dict) -> bool:
    return held.get((f.match_id, f.home_id)) == ELEVEN and held.get((f.match_id, f.away_id)) == ELEVEN


def _instrument(adapter, run: Run, keep: dict) -> None:
    """Count the adapter's HTTP requests by status (its 429 retry included) and keep each answer's raw payload."""
    sess_get, raw_get = adapter._session.get, adapter._get

    def counted(*a, **k):
        try:
            resp = sess_get(*a, **k)
        except Exception as e:  # noqa: BLE001 - a request that never answered is counted under its error, re-raised
            run.http[type(e).__name__] += 1
            raise
        run.http[str(getattr(resp, "status_code", "?"))] += 1
        return resp

    def kept(path, params=None):
        data = raw_get(path, params)
        keep["raw"] = data
        return data
    adapter._session.get, adapter._get = counted, kept


def _named_blocks(raw) -> tuple[int, int]:
    """(team blocks in the answer, of them the blocks whose every slot had no name: the parser drops those slots)."""
    blocks = (raw or {}).get(KEYS["response"]) if isinstance(raw, dict) else None
    if not isinstance(blocks, list):
        return 0, 0
    nameless = 0
    for b in blocks:
        slots = list((b or {}).get(KEYS["starters"]) or []) + list((b or {}).get(KEYS["bench"]) or [])
        if not any(isinstance(((s or {}).get(KEYS["player"]) or {}).get(KEYS["name"]), str)
                   and ((s or {}).get(KEYS["player"]) or {}).get(KEYS["name"]).strip() for s in slots):
            nameless += 1
    return len(blocks), nameless


def run_lineups_history(code: str, season: str, *, dry_run: bool = False, max_calls: int = MAX_CALLS,
                        echo=print, adapter=None, save: str | None = None) -> Run:
    """The ingest (module docstring). Returns the run; the receipt is echoed."""
    from src.db.database import session_scope
    from src.db.schema import Lineup
    from src.timeutil import utc_now_naive

    code = (code or "").strip().upper()
    if code not in COMPETITIONS:
        raise Refused(f"REFUSED: --competition {code or '?'} is not one of {', '.join(COMPETITIONS)} (the ruling's "
                      "four); nothing is asked or stored")
    stored = stored_season(code, season)
    if save:
        refuse_save_dir(save)
    _, fixtures, held, has_table = _plan(code, stored)
    if not has_table and not dry_run:
        raise Refused("REFUSED: the DB has no lineups table; this command never creates one (--dry-run reads "
                      "without it)")
    run = Run(code=code, season=stored, dry_run=dry_run, fixtures=len(fixtures))
    from src.adapters import api_football as af
    echo(f"sync-lineups-history · {code} {stored}"
         + (f" (--season {season} read as {stored!r}, the adapter's rule)" if str(season).strip() != stored else "")
         + f" · {'DRY RUN: nothing is written' if dry_run else f'writes lineups (kind {HISTORY_KIND!r}) only'}"
         + f" · max calls {max_calls}")
    todo = []
    for f in fixtures:
        if f.fixture_id is None:
            run.no_fixture_id += 1
        elif _both(f, held):
            run.already += 1
        else:
            todo.append(f)
        for tid in (f.home_id, f.away_id):
            if held.get((f.match_id, tid), 0) > ELEVEN:
                run.anomalies.append(f"match {f.match_id} team {tid}: {held[(f.match_id, tid)]} history starters "
                                     "stored (more than eleven): rewritten if asked")
    run.to_ask = len(todo)
    echo(f"  plan (no call yet): finished fixtures {run.fixtures} · no fixture id {run.no_fixture_id} · both elevens "
         f"already stored {run.already} · to ask {run.to_ask} · calls a whole run needs {run.to_ask} · about "
         f"{run.to_ask * af._RATE_LIMIT_SECONDS / 60:.1f} min at {af._RATE_LIMIT_SECONDS:g} s a request "
         f"(API_FOOTBALL_RPM {60 / af._RATE_LIMIT_SECONDS:g})")
    if todo:
        if adapter is None:
            try:
                adapter = af.APIFootballAdapter()
            except ValueError as e:                     # no key: the message names the variable only
                raise Refused(f"REFUSED: {e}") from None
        keep: dict = {}
        _instrument(adapter, run, keep)
        if save:
            os.makedirs(save, exist_ok=True)
        now = utc_now_naive()
        try:
            for f in todo:
                if run.calls >= max_calls:
                    raise Capped(f)
                run.calls += 1
                keep.clear()
                try:
                    answer = adapter.list_lineup_confirmed(f.fixture_id)
                except RuntimeError as e:               # the payload's errors block: a quota or plan refusal
                    run.failed.append(f"match {f.match_id} (fixture {f.fixture_id}): {e}")
                    run.stopped = f"a payload error on match {f.match_id} (fixture {f.fixture_id}): {e}"
                    break
                except requests.HTTPError as e:
                    status = getattr(getattr(e, "response", None), "status_code", None)
                    run.failed.append(f"match {f.match_id} (fixture {f.fixture_id}): status {status}")
                    if status in STOP_STATUSES:         # 429 after the adapter's own retry; the key or plan refused
                        run.stopped = f"status {status} on match {f.match_id} (fixture {f.fixture_id})"
                        break
                    continue
                except Exception as e:  # noqa: BLE001 - a failed call is listed; the next run asks it again
                    run.failed.append(f"match {f.match_id} (fixture {f.fixture_id}): {type(e).__name__}: {e}")
                    continue
                if save and keep.get("raw") is not None:
                    with open(os.path.join(save, f"{f.fixture_id}.json"), "w") as fh:
                        json.dump(keep["raw"], fh, indent=1, sort_keys=True)
                _store(run, f, answer or [], keep.get("raw"), held, now, dry_run, session_scope, Lineup)
        except Capped as c:
            nxt = c.args[0]
            run.stopped = f"the cap ({max_calls} calls) before match {nxt.match_id} (fixture {nxt.fixture_id})"
        except KeyboardInterrupt:
            run.stopped = f"an interrupt after {run.calls} call(s); what was stored is kept"
        placed = run.both + run.one + sum(run.none.values()) + len(run.failed)
        run.not_asked = run.to_ask - placed
        if run.stopped:
            run.stopped += f"; {run.not_asked} fixture(s) not asked: the next run asks them and skips the stored ones"
    _receipt(run, echo, max_calls)
    return run


def _store(run: Run, f: Fixture, answer: list, raw, held: dict, now, dry_run: bool, session_scope, Lineup) -> None:
    """Map one answer's sides, write them (unless dry), and place the fixture in the receipt."""
    by_side: dict = {}
    unmapped = 0
    for r in answer:
        tid = f.ids.get(str(r.get("team_source_id")))
        if tid is None:
            unmapped += 1
            continue
        by_side.setdefault(tid, []).append(r)
    starters = {tid: sum(1 for r in rows if r.get("is_starter")) for tid, rows in by_side.items()}
    if by_side and not dry_run:
        with session_scope() as s:
            for tid, rows in by_side.items():
                s.query(Lineup).filter(Lineup.match_id == f.match_id, Lineup.team_id == tid,
                                       Lineup.kind == HISTORY_KIND).delete(synchronize_session=False)
                s.add_all(Lineup(match_id=f.match_id, team_id=tid, kind=HISTORY_KIND, formation=r.get("formation"),
                                 is_starter=bool(r.get("is_starter")), player_name=r["player_name"],
                                 player_position=r.get("player_position"), shirt_number=r.get("shirt_number"),
                                 source=SOURCE, refreshed_at=now) for r in rows)
        run.fixtures_written += 1
    run.rows += sum(len(rows) for rows in by_side.values())
    run.sides += len(by_side)
    after = {tid: starters.get(tid, held.get((f.match_id, tid), 0)) for tid in (f.home_id, f.away_id)}
    elevens = sum(1 for n in after.values() if n == ELEVEN)
    blocks, nameless = _named_blocks(raw)
    if elevens == 2:
        run.both += 1
        place = "both"
    elif elevens == 1:
        run.one += 1
        place = "one"
    else:
        why = ("an empty answer" if not answer and not blocks else
               "team blocks with no named slot" if not answer and nameless else
               "a side that maps to neither team" if unmapped and not by_side else "sides short of eleven")
        run.none[why] += 1
        place = f"none ({why})"
    day = f"{f.kickoff:%Y-%m-%d}" if f.kickoff else "no kickoff"
    run.lines.append(f"    match {f.match_id} (fixture {f.fixture_id}, {day}): {place} · "
                     + " · ".join(f"team {tid} {starters.get(tid, 0)} starters "
                                  f"{len(by_side.get(tid, [])) - starters.get(tid, 0)} bench"
                                  for tid in (f.home_id, f.away_id))
                     + (f" · unmapped slots {unmapped}" if unmapped else "")
                     + (f" · nameless team blocks {nameless}" if nameless else ""))


def _receipt(run: Run, echo, max_calls: int) -> None:
    w = "would be stored" if run.dry_run else "stored"
    both = run.both + run.already
    none = sum(run.none.values())
    echo(f"  COVERAGE {run.code} {run.season}: fixtures with both elevens {both} / fixtures {run.fixtures} · one "
         f"{run.one} · none {none} · failed {len(run.failed)} · not asked {run.not_asked} · no fixture id "
         f"{run.no_fixture_id}" + (" (a dry run: the table plus what would be stored)" if run.dry_run else ""))
    if run.none:
        echo("    none, by why: " + " · ".join(f"{k} {v}" for k, v in sorted(run.none.items())))
    echo(f"  {w}: {run.rows} row(s) on {run.sides} side(s) of {run.fixtures_written if not run.dry_run else '-'}"
         f" fixture(s) written · both elevens already stored (skipped, no call) {run.already}")
    echo(f"  calls {run.calls} of {max_calls} · HTTP requests "
         + (" · ".join(f"{k} ×{v}" for k, v in sorted(run.http.items())) or "0"))
    echo("  rows carry the ingest time only (refreshed_at): no publication time, so nothing here says when a lineup "
         "became readable")
    for a in run.anomalies:
        echo(f"  ! {a}")
    for x in run.failed:
        echo(f"  ✗ {x}")
    if run.dry_run:
        for ln in run.lines:
            echo(ln)
    if run.stopped:
        echo(f"  STOPPED at {run.stopped}")
