"""RETIRE-ORPHANS FOR MLB (ARCHITECT 2026-10-20, addendum 146 item 3(a); #568), verbatim: "A retire-orphans step for
MLB, explicit, dry run first, in the morning block after the MLB sync (never inside the watch): a SCHEDULED MLB row
becomes STALE_ORPHAN on TWO receipts, both printed per row: (1) the row's provider id is absent from the provider's
answer for a window that covers its date (the strict read's own evidence, one call), and (2) the series arithmetic
from the #605 fields shows the series decided before this row's game number: the pair's FINISHED games of the same
season and stage, wins per side, against games_in_series of any row of that series (needed = ceil(gis/2)). Either
receipt missing -> the row stays SCHEDULED (law 4). Never CANCELLED: the provider said nothing. Acceptance cases: 50555
(ALCS Game 7, dropped 10-20) and 50549 (MIL at LAD, dropped 10-16; its own series fields are null, so receipt (2) reads
the series' other rows)."

The world is synthetic in the statsapi /schedule shape (no statsapi payload is kept under tests/fixtures; the entries
come from tests/test_match_series_fields.py's game()). ALCS (stage L, 7 games): 50546 / 849818 Game 3, 50550 / 849816
Game 4, 50548 / 849817 Game 5 (addendum 130 item 1(a)); 50551 Game 6 with Cleveland away and Tampa Bay home (addendum
146 item 2); 50555 Game 7, SCHEDULED, dropped. Games 1, 2 and 6's ids, every gamePk but those three, the results (Tampa
Bay in six) and the clocks are this file's own. NLCS: 50549, MIL at LAD, stored 2026-10-17 01:00Z ("Fri 2026-10-16
9:00pm ET", the 10-17 ledger entry), SCHEDULED, its own four series fields NULL; its siblings (this file's own: Los
Angeles in five) carry them. Each test has a throwaway DB of its own, migrated (migrate_match_series_fields.py)."""
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
import requests
from click.testing import CliRunner
from sqlalchemy import create_engine, select

from tests.test_match_series_fields import ALCS, BOS, CLE, NYY, TB, game, schedule

ROOT = Path(__file__).resolve().parents[1]
Z = datetime.fromisoformat
NOW = Z("2026-10-20T12:00")                          # Tuesday 08:00 ET: the morning block, after the MLB sync
MIL, LAD = (158, "Milwaukee Brewers"), (119, "Los Angeles Dodgers")
NLCS = "NL Championship Series"
PARAMS = {"sportId": 1, "gameType": "F,D,L,W", "season": 2026}
# (id, gamePk, start UTC, status, away, home, away runs, home runs, stage, n, gis, description)
ALCS_ROWS = [
    (50530, 849820, "2026-10-12T20:08", "FINISHED", CLE, TB, 1, 4, "L", 1, 7, ALCS),
    (50533, 849819, "2026-10-13T22:08", "FINISHED", CLE, TB, 2, 5, "L", 2, 7, ALCS),
    (50546, 849818, "2026-10-15T22:08", "FINISHED", TB, CLE, 2, 3, "L", 3, 7, ALCS),
    (50550, 849816, "2026-10-18T00:08", "FINISHED", TB, CLE, 7, 3, "L", 4, 7, ALCS),
    (50548, 849817, "2026-10-18T21:08", "FINISHED", TB, CLE, 1, 6, "L", 5, 7, ALCS),
    (50551, 849815, "2026-10-20T00:08", "FINISHED", CLE, TB, 2, 4, "L", 6, 7, ALCS),     # Tampa Bay in six
    (50555, 849814, "2026-10-21T00:08", "SCHEDULED", CLE, TB, None, None, "L", 7, 7, ALCS),
]
NLCS_ROWS = [
    (50520, 849901, "2026-10-11T00:08", "FINISHED", MIL, LAD, 1, 3, "L", 1, 7, NLCS),
    (50524, 849902, "2026-10-12T00:08", "FINISHED", MIL, LAD, 2, 6, "L", 2, 7, NLCS),
    (50536, 849903, "2026-10-14T00:08", "FINISHED", LAD, MIL, 4, 5, "L", 3, 7, NLCS),
    (50541, 849904, "2026-10-15T00:08", "FINISHED", LAD, MIL, 5, 3, "L", 4, 7, NLCS),
    (50545, 849906, "2026-10-16T00:08", "FINISHED", LAD, MIL, 6, 2, "L", 5, 7, NLCS),    # Los Angeles in five
    (50549, 849905, "2026-10-17T01:00", "SCHEDULED", MIL, LAD, None, None, "L", None, None, None),
]
OTHER_ROWS = [                                       # SCHEDULED and past their start, never candidates (printed)
    (49001, 776101, "2026-09-27T17:05", "SCHEDULED", BOS, NYY, None, None, "R", None, None, None),
    (49002, None, "2026-09-28T17:05", "SCHEDULED", NYY, BOS, None, None, None, None, None, None),
]
DROPPED = {849814, 849905}                           # 50555 and 50549: no longer in the provider's answer
ALCS_IDS = tuple(r[0] for r in ALCS_ROWS)


def entries(rows=ALCS_ROWS + NLCS_ROWS, drop=DROPPED):
    """The provider's postseason answer: each listed row's own entry (its coded state, runs and series fields)."""
    out = []
    for i, pk, when, st, away, home, ar, hr, stage, n, gis, desc in rows:
        if pk is None or pk in drop or stage not in ("F", "D", "L", "W"):
            continue
        series = {k: v for k, v in (("seriesGameNumber", n), ("gamesInSeries", gis), ("seriesDescription", desc))
                  if v is not None}
        out.append(game(pk, when + ":00Z", {"FINISHED": "F", "SCHEDULED": "S"}[st], away, home, ar, hr,
                        game_type=stage, **series))
    return out


class Stats:
    """The statsapi adapter with its one HTTP call replaced: answers `payload`, or raises `raises`."""

    def __new__(cls, payload=None, raises=None):
        from src.adapters.mlb_stats_api import MLBStatsAPIAdapter
        a = MLBStatsAPIAdapter.__new__(MLBStatsAPIAdapter)
        a.calls = []

        def get(path, params=None):
            a.calls.append((path, params))
            if raises is not None:
                raise raises
            return payload
        a._get = get
        return a


@pytest.fixture
def db(tmp_path, monkeypatch):
    """A throwaway DB of its own (tests/test_match_series_fields.py's pattern), migrated, the clock fixed at NOW."""
    from sqlalchemy.orm import sessionmaker

    import migrate_match_series_fields as mig
    import src.db.database as dbm
    import src.timeutil as tu
    path = tmp_path / "fresh.db"
    eng = create_engine(f"sqlite:///{path}", future=True)
    monkeypatch.setattr(dbm, "_engine", eng)
    monkeypatch.setattr(dbm, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                          expire_on_commit=False))
    monkeypatch.delenv("SP_SKIP_FAMILIES", raising=False)                  # statsapi, the laptop's path
    monkeypatch.setattr(tu, "utc_now_naive", lambda: NOW)
    dbm.init_db()
    assert mig.main() == 0
    seed(ALCS_ROWS + NLCS_ROWS + OTHER_ROWS)
    yield path
    eng.dispose()


def seed(rows, season="2026"):
    from src.db.database import session_scope, write_match_series
    from src.db.schema import Competition, Match, MatchStatus, Sport, Team
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == "MLB")).scalar_one_or_none()
        if comp is None:
            comp = Competition(sport=Sport.MLB, code="MLB", name="Major League Baseball", area="USA", type="LEAGUE")
            s.add(comp)
        teams = {t.external_ids.get("mlb_stats_api"): t for t in s.execute(select(Team)).scalars()}
        for tid, name in (TB, CLE, NYY, BOS, MIL, LAD):
            if str(tid) not in teams:
                teams[str(tid)] = Team(sport=Sport.MLB, name=name, external_ids={"mlb_stats_api": str(tid)})
                s.add(teams[str(tid)])
        s.flush()
        pairs = []
        for i, pk, when, st, away, home, ar, hr, stage, n, gis, desc in rows:
            s.add(Match(id=i, sport=Sport.MLB, competition_id=comp.id, season=season, stage=stage, utc_date=Z(when),
                        status=MatchStatus[st], home_team_id=teams[str(home[0])].id,
                        away_team_id=teams[str(away[0])].id, home_score=hr, away_score=ar,
                        status_raw={"FINISHED": "F"}.get(st), external_ids={"mlb_stats_api": str(pk)} if pk else {}))
            pairs.append((i, {"series_game_number": n, "games_in_series": gis, "series_description": desc}))
        s.flush()
        write_match_series(s, pairs)


def update(mid, **cols):
    from src.db.database import session_scope
    from src.db.schema import Match, MatchStatus
    with session_scope() as s:
        m = s.get(Match, mid)
        for k, v in cols.items():
            setattr(m, k, MatchStatus[v] if k == "status" else v)


def set_series(mid, **cols):
    from sqlalchemy import text

    from src.db.database import session_scope
    with session_scope() as s:
        for k, v in cols.items():
            s.execute(text(f"UPDATE matches SET {k} = :v WHERE id = :i"), {"v": v, "i": mid})


def drop_row(path, mid):
    con = sqlite3.connect(path)
    con.execute("DELETE FROM matches WHERE id = ?", (mid,))
    con.commit()
    con.close()


def snapshot(path):
    """Every matches row, every column (the unmapped series fields included), by raw SQL."""
    con = sqlite3.connect(path)
    try:
        cur = con.execute("SELECT * FROM matches ORDER BY id")
        cols = [d[0] for d in cur.description]
        return {r[0]: dict(zip(cols, r)) for r in cur.fetchall()}
    finally:
        con.close()


def cli_run(monkeypatch, adapter, *args):
    import cli
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda code: adapter)
    r = CliRunner().invoke(cli.cli, ["retire-orphans", "--competition", "MLB", "--season", "2026", *args])
    return r.exit_code, r.output


def plan(adapter=None, **kw):
    """The planner's receipt, {match id: plan entry}, and the run (python API, as the command calls it)."""
    from src.ingestion import mlb_orphans as mo
    r = mo.run("2026", adapter or Stats(schedule(*entries())), **kw)
    return {p["id"]: p for p in r["plan"]}, r


def backup(src, dst):
    with sqlite3.connect(src) as a, sqlite3.connect(dst) as b:
        a.backup(b)
    return str(dst)


# ------------------------------------------------------------------------------------- the acceptance cases --

def test_the_dry_run_retires_both_acceptance_cases_on_both_receipts_and_writes_nothing(db, monkeypatch):
    before = snapshot(db)
    stats = Stats(schedule(*entries()))
    rc, out = cli_run(monkeypatch, stats)
    assert rc == 0, out
    lines = out.splitlines()
    assert lines[0] == ("RETIRE-ORPHANS MLB 2026 (mlb_stats_api) · DRY-RUN (nothing written) · candidates 2 "
                        "(SCHEDULED, no score, stage F/D/L/W) · not candidates, past their start 2 · provider calls 1")
    assert lines[1] == ("  provider answer: GET schedule {sportId 1, gameType F,D,L,W, season 2026} (the season's "
                        "postseason, one call) · 11 game(s) · dates 2026-10-11..2026-10-20")
    assert "  plan: retire 2 · stays SCHEDULED 0 (listed 0 · not decided 0 · no receipt 1 0 · no receipt 2 0)" in lines
    i = lines.index("  [retire] match 50549 gamePk 849905 · Milwaukee Brewers @ Los Angeles Dodgers · stage L · "
                    "2026-10-17T01:00:00Z (Fri 2026-10-16 21:00 ET)")
    assert lines[i + 1] == ("    receipt 1: ABSENT (gamePk 849905 is not in the provider's answer, which lists 5 of the "
                            "series' other 5 gamePks) · params {sportId 1, gameType F,D,L,W, season 2026} · answer 11 "
                            "game(s)")
    assert lines[i + 2] == (
        "    receipt 2: DECIDED (the clinch started before this row's start) · series \"NL Championship Series\" · stage "
        "L · season 2026 · games_in_series 7 (from 50520, 50524, 50536, 50541, 50545) · needed 4 · wins Los Angeles "
        "Dodgers 4, Milwaukee Brewers 1 over 5 FINISHED · clinch match 50545 (Thu 2026-10-15 20:08 ET) · game number: "
        "null (own); read by start: the clinch Thu 2026-10-15 20:08 ET, this row Fri 2026-10-16 21:00 ET")
    assert lines[i + 3] == ("      match 50520 · gamePk 849901 · game 1 of 7 · Sat 2026-10-10 20:08 ET · FINISHED · "
                            "status_raw F · Milwaukee Brewers 1 @ Los Angeles Dodgers 3")
    assert lines[i + 8] == ("      match 50549 · gamePk 849905 · game null of null · Fri 2026-10-16 21:00 ET · SCHEDULED "
                            "· status_raw null · Milwaukee Brewers @ Los Angeles Dodgers, no score")
    j = lines.index("  [retire] match 50555 gamePk 849814 · Cleveland Guardians @ Tampa Bay Rays · stage L · "
                    "2026-10-21T00:08:00Z (Tue 2026-10-20 20:08 ET)")
    assert lines[j + 1].startswith("    receipt 1: ABSENT (gamePk 849814 is not in the provider's answer, which lists 6 "
                                   "of the series' other 6 gamePks)")
    assert lines[j + 2] == (
        "    receipt 2: DECIDED (decided in game 6, before game 7) · series \"AL Championship Series\" · stage L · "
        "season 2026 · games_in_series 7 (from 50530, 50533, 50546, 50550, 50548, 50551, 50555) · needed 4 · wins "
        "Tampa Bay Rays 4, Cleveland Guardians 2 over 6 FINISHED · clinch match 50551 (Mon 2026-10-19 20:08 ET) · "
        "this row game 7 (own), the series over after game 6")
    assert [ln for ln in lines if "[not a candidate]" in ln] == [
        "  [not a candidate] match 49001 · stage R · 2026-09-27T17:05:00Z (Sun 2026-09-27 13:05 ET) · SCHEDULED, past "
        "its start · stage R: not a postseason row (the series arithmetic is the postseason's; never a candidate)",
        "  [not a candidate] match 49002 · stage null · 2026-09-28T17:05:00Z (Mon 2026-09-28 13:05 ET) · SCHEDULED, "
        "past its start · stage null: not a postseason row (the series arithmetic is the postseason's; never a "
        "candidate)"]
    assert lines[-1] == "  state before: MLB rows 15 · stale orphans 0"
    assert stats.calls == [("schedule", PARAMS)]                       # one call, the season's postseason
    assert snapshot(db) == before                                      # nothing written


def test_the_one_call_is_the_seasons_postseason_schedule_as_mlb_time_audit_reads_it(db):
    """Receipt (1)'s window (the lead's reading of "a window that covers its date ... one call"): the season's
    postseason, one GET, no dates: mlb-time-audit's params. Not the strict read's D..D window: an if-necessary game's
    own day can list zero games."""
    import inspect

    import cli
    from src.ingestion import mlb_apisports as fb
    stats = Stats(schedule(*entries()))
    plan(stats)
    assert stats.calls == [("schedule", PARAMS)]
    assert PARAMS["gameType"] == ",".join(fb.POSTSEASON_TYPES)
    assert '"gameType": ",".join(fb.POSTSEASON_TYPES), "season": int(season)' in inspect.getsource(cli.mlb_time_audit_cmd.callback)


def test_no_candidate_no_call(db):
    for mid in (50555, 50549):
        update(mid, status="FINISHED", home_score=1, away_score=0)
    stats = Stats(schedule(*entries()))
    got, r = plan(stats)
    assert got == {} and stats.calls == [] and r["answer"]["calls"] == 0


def test_a_scheduled_row_with_a_score_is_no_candidate_and_only_past_rows_print(db):
    """Both scores NULL make a candidate; a SCHEDULED postseason row with a score is printed with why when its start is
    past, and a SCHEDULED row whose start is still ahead (a scored 50555, a regular-season game next week) is not
    printed at all."""
    from src.ingestion import mlb_orphans as mo
    update(50549, home_score=3)                                        # past its start
    update(50555, away_score=2)                                        # starts tonight, after NOW
    seed([(49003, 776103, "2026-10-25T17:05", "SCHEDULED", BOS, NYY, None, None, "R", None, None, None)])
    stats = Stats(schedule(*entries()))
    got, r = plan(stats)
    assert got == {} and stats.calls == []
    assert [(o["id"], o["why"]) for o in r["others"]] == [
        (49001, "stage R: not a postseason row (the series arithmetic is the postseason's; never a candidate)"),
        (49002, "stage null: not a postseason row (the series arithmetic is the postseason's; never a candidate)"),
        (50549, "a score is stored (3-None)")]
    assert ("  [not a candidate] match 50549 · stage L · 2026-10-17T01:00:00Z (Fri 2026-10-16 21:00 ET) · SCHEDULED, "
            "past its start · a score is stored (3-None)") in mo.lines(r)


def test_no_database_file_is_refused_and_never_created(tmp_path, monkeypatch):
    """Law 5: the dry run is run from a worktree of the branch with the laptop checkout as the working directory; an
    engine whose file is not there (a wrong cwd, a DATABASE_URL naming another path) is refused, exit 2, with no
    provider call, and no file or directory is created (the engine's connect hooks would make both)."""
    import src.db.database as dbm
    missing = tmp_path / "nowhere" / "sports.db"
    eng = create_engine(f"sqlite:///{missing}", future=True)
    monkeypatch.setattr(dbm, "_engine", eng)
    monkeypatch.delenv("SP_SKIP_FAMILIES", raising=False)
    stats = Stats(schedule(*entries()))
    rc, out = cli_run(monkeypatch, stats)
    assert rc == 2 and out.startswith(f"no database at {missing.resolve()}; retire-orphans never creates one")
    assert stats.calls == [] and not missing.exists() and not missing.parent.exists()
    eng.dispose()

def test_a_season_that_is_not_digits_is_refused_with_no_call(db, monkeypatch):
    import cli
    stats = Stats(schedule(*entries()))
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda code: stats)
    before = snapshot(db)
    r = CliRunner().invoke(cli.cli, ["retire-orphans", "--competition", "MLB", "--season", "2026/27"])
    assert r.exit_code == 2 and "--season takes the stored MLB season, e.g. 2026 (got '2026/27')" in r.output, r.output
    assert stats.calls == [] and snapshot(db) == before


# ----------------------------------------------------------------------------------------------- the write --

def test_apply_retires_the_named_rows_and_nothing_else(db, monkeypatch, tmp_path):
    before = snapshot(db)
    good = backup(db, tmp_path / "good.backup")
    stats = Stats(schedule(*entries()))
    rc, out = cli_run(monkeypatch, stats, "--apply", "--backup", good, "--match-ids", "50555,50549")
    assert rc == 0, out
    lines = out.splitlines()
    assert lines[0].startswith("backup verified:")
    assert lines[1].startswith("RETIRE-ORPHANS MLB 2026 (mlb_stats_api) · APPLIED · candidates 2")
    assert "  applied: retired 2 (50549, 50555) · refused at apply 0 · named 50549, 50555" in lines
    assert lines[-1] == "  state after:  MLB rows 15 · stale orphans 2 (+2)"
    after = snapshot(db)
    assert len(after) == len(before)
    for mid in (50549, 50555):
        b, a = before.pop(mid), after.pop(mid)
        assert (b["status"], a["status"]) == ("SCHEDULED", "STALE_ORPHAN")                  # never CANCELLED
        assert a["external_ids"] == b["external_ids"][:-1] + ', "mlb_stats_api_orphaned_at": "2026-10-20T12:00:00"}'
        assert {k: v for k, v in a.items() if k not in ("status", "external_ids")} == \
            {k: v for k, v in b.items() if k not in ("status", "external_ids")}
    assert after == before                                             # every other row as it was
    assert "CANCELLED" not in {r["status"] for r in snapshot(db).values()}
    rc, again = cli_run(monkeypatch, Stats(schedule(*entries())))     # the re-run finds nothing left to retire
    assert rc == 0 and "candidates 0" in again.splitlines()[0] and "provider calls 0" in again.splitlines()[0]
    assert again.splitlines()[-1] == "  state before: MLB rows 15 · stale orphans 2"


def test_the_apply_plans_again_and_refuses_a_named_row_planned_otherwise(db, monkeypatch, tmp_path):
    """A named row whose fresh plan is not retire is REFUSED and stays; a row planned retire but not named stays."""
    good = backup(db, tmp_path / "good.backup")
    payload = schedule(*entries(drop={849905}))                        # since the dry run, 50555 is listed again
    rc, out = cli_run(monkeypatch, Stats(payload), "--apply", "--backup", good, "--match-ids", "50555,50546,7")
    assert rc == 0, out
    lines = out.splitlines()
    assert "  applied: retired 0 (none) · refused at apply 3 · named 7, 50546, 50555" in lines
    assert "  REFUSED match 7: not a candidate: no such match" in lines
    assert "  REFUSED match 50546: not a candidate: status FINISHED, not SCHEDULED" in lines
    assert "  REFUSED match 50555: its plan is 'listed', not retire (it stays SCHEDULED)" in lines
    assert ("  [not named] match 50549: planned retire, not named by --match-ids: stays SCHEDULED") in lines
    assert {snapshot(db)[i]["status"] for i in (50549, 50555)} == {"SCHEDULED"}


@pytest.mark.parametrize("args, says", [
    (["--apply", "--match-ids", "50555"], "REFUSED [check: --backup given]"),
    (["--apply", "--backup", "BACKUP"], "REFUSED: --apply without --match-ids"),
    (["--match-ids", "50555"], "REFUSED: --match-ids names the rows to retire and is read only with --apply"),
    (["--apply", "--backup", "STALE", "--match-ids", "50555"], "REFUSED [check: matches count = live]"),
], ids=["no-backup", "no-match-ids", "match-ids-without-apply", "stale-backup"])
def test_the_write_refusals_exit_2_with_no_call_and_nothing_written(db, monkeypatch, tmp_path, args, says):
    good = backup(db, tmp_path / "good.backup")
    stale = backup(db, tmp_path / "stale.backup")
    con = sqlite3.connect(stale)
    con.execute("DELETE FROM matches WHERE id = 49001")
    con.commit()
    con.close()
    before = snapshot(db)
    stats = Stats(schedule(*entries()))
    rc, out = cli_run(monkeypatch, stats, *[{"BACKUP": good, "STALE": stale}.get(a, a) for a in args])
    assert rc == 2 and says in out, out
    assert stats.calls == [] and snapshot(db) == before


def test_refusal_order_competition_then_fallback_then_the_write_checks(db, monkeypatch):
    import cli
    stats = Stats(schedule(*entries()))
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda code: stats)
    before = snapshot(db)
    monkeypatch.setenv("SP_SKIP_FAMILIES", "MLB")
    nfl = CliRunner().invoke(cli.cli, ["retire-orphans", "--competition", "NFL", "--season", "2026", "--apply"])
    assert nfl.exit_code == 2 and "REFUSED: retire-orphans reads statsapi: MLB only (got NFL)" in nfl.output
    rc, out = cli_run(monkeypatch, stats, "--apply")                   # the host's fallback, before the write checks
    assert rc == 2 and out.splitlines() == [
        "REFUSED: retire-orphans reads statsapi (the laptop's MLB path); this machine syncs MLB from the api-sports "
        "fallback (SP_SKIP_FAMILIES names MLB). Nothing was read or written."]
    assert stats.calls == [] and snapshot(db) == before


def test_mlb_not_stored_is_an_error_with_no_call(db, monkeypatch):
    con = sqlite3.connect(db)
    con.execute("UPDATE competitions SET code = 'MLBX' WHERE code = 'MLB'")
    con.commit()
    con.close()
    stats = Stats(schedule(*entries()))
    rc, out = cli_run(monkeypatch, stats)
    assert rc == 1 and "competition MLB not in DB" in out, out
    assert stats.calls == []


def test_a_db_behind_the_code_is_refused_with_the_remedy(db, monkeypatch):
    con = sqlite3.connect(db)
    con.execute("ALTER TABLE matches DROP COLUMN status_raw")
    con.commit()
    con.close()
    stats = Stats(schedule(*entries()))
    rc, out = cli_run(monkeypatch, stats)
    assert rc == 2 and "REFUSED: the live DB is behind the code (no such column: matches.status_raw)" in out, out
    assert stats.calls == []


def test_the_check_guard_refuses_every_retire_at_apply(db, monkeypatch, tmp_path):
    from src.ingestion import match_dedupe as md
    monkeypatch.setattr(md, "_check_allows_orphan", lambda s: "the matches table carries a status CHECK constraint "
                                                               "without STALE_ORPHAN")
    good = backup(db, tmp_path / "good.backup")
    rc, out = cli_run(monkeypatch, Stats(schedule(*entries())), "--apply", "--backup", good, "--match-ids",
                      "50555,50549")
    assert rc == 0, out
    assert out.count("orphan mark refused: the matches table carries a status CHECK constraint") == 2
    assert {snapshot(db)[i]["status"] for i in (50549, 50555)} == {"SCHEDULED"}


def test_a_self_healed_row_takes_the_listings_status_and_keeps_its_marker(db, monkeypatch, tmp_path):
    """No code: a later sync that lists the gamePk again finds the row by its id (service.py) and sets its status from
    the listing; the orphaned_at marker stays (docs/CLI.md says so)."""
    import cli
    plan(apply=True, named={50555})
    listed = Stats(schedule(game(849814, "2026-10-21T00:08:00Z", "S", CLE, TB, seriesGameNumber=7, gamesInSeries=7,
                                 seriesDescription=ALCS)))
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda code: listed)
    r = CliRunner().invoke(cli.cli, ["sync-matches", "--competition", "MLB", "--date-from", "2026-10-20",
                                     "--date-to", "2026-10-20"])
    assert r.exit_code == 0, r.output
    row = snapshot(db)[50555]
    assert (row["status"], row["status_raw"]) == ("SCHEDULED", "S")
    assert '"mlb_stats_api_orphaned_at": "2026-10-20T12:00:00"' in row["external_ids"]


# ------------------------------------------------------------------------------------------- receipt (1) --

def test_a_listed_gamepk_keeps_the_row_though_the_series_is_decided(db):
    """The raw gamePks: an entry the sync would skip (no team ids; a date it cannot read) still lists its game."""
    bare = {"gamePk": 849814, "gameDate": "2026-10-21T00:08:00Z", "status": {"codedGameState": "S"}, "teams": {}}
    bad_date = dict(game(849905, "2026-10-17T01:00:00Z", "S", MIL, LAD), gameDate="Fri 9pm")
    payload = schedule(*entries())
    payload["dates"].append({"date": "2026-10-20", "games": [bare, bad_date]})
    got, _ = plan(Stats(payload))
    for mid in (50555, 50549):
        assert got[mid]["action"] == "listed" and got[mid]["r1"]["verdict"] == "LISTED"
        assert got[mid]["r2"]["verdict"] == "DECIDED"                  # both printed; the series alone never retires


def test_a_failed_call_is_no_receipt_never_absent(db, monkeypatch):
    stats = Stats(raises=requests.HTTPError("503 Server Error: Service Unavailable"))
    rc, out = cli_run(monkeypatch, stats)
    assert rc == 0, out
    lines = out.splitlines()
    assert lines[1] == ("  provider answer: GET schedule {sportId 1, gameType F,D,L,W, season 2026} (the season's "
                        "postseason, one call) · ERROR HTTPError: 503 Server Error: Service Unavailable · no receipt 1 "
                        "for any row")
    assert "  plan: retire 0 · stays SCHEDULED 2 (listed 0 · not decided 0 · no receipt 1 2 · no receipt 2 0)" in lines
    assert sum("receipt 1: NO RECEIPT (the provider call failed: HTTPError: 503" in ln for ln in lines) == 2
    assert stats.calls == [("schedule", PARAMS)]


@pytest.mark.parametrize("payload", [
    {"dates": []}, {"totalGames": 0}, {"dates": [{"date": "2026-10-20", "games": []}]},
    {"dates": [{"date": "2026-10-20", "games": [{"gamePk": None}, {"gamePk": " "}]}]}, None, [],
], ids=["no-dates", "no-dates-key", "empty-day", "null-gamepks", "null", "a-list"])
def test_an_answer_that_lists_no_game_is_no_receipt(db, payload):
    got, r = plan(Stats(payload))
    assert r["answer"]["pks"] == []
    for mid in (50555, 50549):
        assert got[mid]["action"] == "no receipt 1"
        assert got[mid]["r1"]["why"] == "the provider's answer lists no game"


def test_a_row_with_no_provider_id_is_no_receipt(db):
    update(50555, external_ids={"api_baseball": "91"})
    got, _ = plan()
    assert got[50555]["r1"]["verdict"] == "NO RECEIPT"
    assert got[50555]["r1"]["why"] == "the row has no mlb_stats_api id" and got[50555]["action"] == "no receipt 1"
    assert got[50549]["action"] == "retire"


def test_an_answer_that_lists_no_game_of_the_rows_series_is_no_receipt(db):
    """ABSENT needs the answer to list a stored gamePk of the row's own series (its siblings): an answer of unrelated
    games is no evidence about the series. Both acceptance cases still retire on the full answer (the dry-run test)."""
    got, _ = plan(Stats({"dates": [{"date": "2025-10-20", "games": [{"gamePk": 1}, {"gamePk": 2}]}]}))
    assert got[50555]["r1"]["why"] == ("the answer lists no game of this series (its other gamePks 849815, 849816, "
                                       "849817, 849818, 849819, 849820: none listed)")
    assert got[50549]["r1"]["why"] == ("the answer lists no game of this series (its other gamePks 849901, 849902, "
                                       "849903, 849904, 849906: none listed)")
    for mid in (50555, 50549):
        assert got[mid]["r1"]["verdict"] == "NO RECEIPT" and got[mid]["action"] == "no receipt 1"
        assert got[mid]["r2"]["verdict"] == "DECIDED"                  # the series alone never retires
    got, _ = plan(Stats(schedule(*entries(rows=ALCS_ROWS))))           # the ALCS listed, no NLCS game
    assert got[50555]["action"] == "retire" and got[50555]["r1"]["series_listed"] == [
        "849815", "849816", "849817", "849818", "849819", "849820"]
    assert got[50549]["action"] == "no receipt 1" and got[50549]["r1"]["series_listed"] == []
    got, _ = plan(Stats(schedule(*entries(rows=[r for r in ALCS_ROWS if r[1] == 849820]))))   # one sibling listed
    assert got[50555]["r1"]["why"] == ("gamePk 849814 is not in the provider's answer, which lists 1 of the series' "
                                       "other 6 gamePks") and got[50555]["action"] == "retire"


def test_listed_game_pks_reads_every_entry_raw():
    from src.adapters.mlb_stats_api import listed_game_pks
    data = {"dates": [{"date": "d", "games": [{"gamePk": 1}, {"gameId": "2"}, {"gamePk": None, "gameId": 3},
                                              {"teams": {}}, "x", {"gamePk": ""}]},
                      "y", {"games": None}, {"date": "e", "games": [{"gamePk": 4, "gameDate": "not a date"}]}]}
    assert listed_game_pks(data) == ["1", "2", "4"]
    assert listed_game_pks({"dates": {"a": 1}}) == [] and listed_game_pks(None) == []


# ------------------------------------------------------------------------------------------- receipt (2) --

def test_a_series_not_yet_decided_keeps_the_row(db):
    update(50551, home_score=2, away_score=4)                          # Cleveland wins Game 6: 3-3
    got, _ = plan()
    assert got[50555]["r2"]["verdict"] == "NOT DECIDED" and got[50555]["r2"]["why"] == "no side has 4 wins"
    assert got[50555]["action"] == "not decided" and got[50549]["action"] == "retire"


@pytest.mark.parametrize("change, why", [
    (lambda: [set_series(i, games_in_series=None) for i in (50530, 50533, 50546, 50550, 50548, 50551, 50555)],
     "games_in_series null on every row of the series (50530, 50533, 50546, 50550, 50548, 50551, 50555)"),
    (lambda: set_series(50530, games_in_series=5),
     "games_in_series disagree across the series (5 on 50530; 7 on 50533, 50546, 50550, 50548, 50551, 50555)"),
    (lambda: update(50548, home_score=None), "FINISHED without a decided score: 50548 (None-1)"),
    (lambda: update(50548, home_score=1), "FINISHED without a decided score: 50548 (1-1)"),
    (lambda: update(50548, status="LIVE"), "a game of the series is LIVE (50548)"),
    (lambda: update(50548, external_ids={"mlb_stats_api": "849816"}), "two FINISHED rows of one gamePk (849816)"),
    (lambda: set_series(50548, series_game_number=4), "two FINISHED rows of one game number (4)"),
    (lambda: update(50548, home_score=0), "a game after the clinch (5 wins against needed 4)"),
    (lambda: (update(50548, home_score=0), update(50551, home_score=1)),
     "the latest FINISHED game (50551) was won by the side without 4 wins"),
], ids=["gis-null", "gis-disagree", "null-score", "tied", "live", "twin-gamepk", "twin-number", "after-clinch",
        "clinch-other-side"])
def test_receipt_two_missing_keeps_the_row(db, change, why):
    change()
    got, _ = plan()
    assert (got[50555]["r2"]["verdict"], got[50555]["r2"]["why"]) == ("NO RECEIPT", why)
    assert got[50555]["action"] == "no receipt 2" and got[50549]["action"] == "retire"


@pytest.mark.parametrize("change, mids, why", [
    (lambda db: seed([(50600 + i, 849950 + i, f"2026-10-1{2 + i}T18:00", "FINISHED", MIL, LAD, 5, 1, "L", None, 7,
                       NLCS) for i in range(3)]),
     (50549,), "8 FINISHED games, more than games_in_series 7"),
    (lambda db: update(50551, utc_date=Z("2026-10-18T21:08")),
     (50555,), "two FINISHED games share the latest start (50548, 50551)"),
    (lambda db: ([set_series(i, games_in_series=6) for i in ALCS_IDS], update(50551, home_score=2, away_score=4)),
     (50555,), "games_in_series 6 is even: both sides can reach needed 3 (a tied series)"),
    (lambda db: ([set_series(i, games_in_series=6) for i in ALCS_IDS], update(50530, home_score=4, away_score=5)),
     (50555,), "games_in_series 6 is even: both sides can reach needed 3 (a tied series)"),
    (lambda db: (drop_row(db, 50546), seed([(50562, 849897, "2026-10-21T00:08", "SCHEDULED", CLE, TB, None, None,
                                              "L", 6, 7, ALCS)])),
     (50555, 50562), "a FINISHED game of the series is not stored (clinch is game 6, 5 FINISHED)"),
    (lambda db: seed([(50563, 849896, "2026-10-14T22:08", "FINISHED", TB, CLE, 1, 5, "L", None, 7, ALCS)]),
     (50555,), "more FINISHED games than the clinch's game number (clinch is game 6, 7 FINISHED)"),
    (lambda db: (drop_row(db, 50546), set_series(50551, series_game_number=None),
                 seed([(50562, 849897, "2026-10-21T00:08", "SCHEDULED", CLE, TB, None, None, "L", 6, 7, ALCS)])),
     (50555, 50562), "a FINISHED game of the series is not stored (game 5 FINISHED before the clinch, 5 FINISHED)"),
    (lambda db: (update(50550, away_score=3, home_score=7), update(50548, away_score=6, home_score=1),
                 update(50551, status="SCHEDULED", home_score=None, away_score=None),
                 seed([(50570, 849870, "2026-10-18T22:08", "FINISHED", TB, CLE, 6, 1, "L", None, 7, ALCS)])),
     (50555,), "two FINISHED games on one day (2026-10-18 ET: 50548, 50570)"),
], ids=["k-over-gis", "shared-latest-start", "tied-3-3-clinch-other-side", "tied-3-3-clinch-first-side",
        "clinch-game-not-stored", "more-finished-than-clinch-number", "no-clinch-number-a-finished-game-missing",
        "an-earlier-game-stored-twice"])
def test_receipt_two_refuses_a_count_or_a_clinch_the_stored_rows_cannot_carry(db, change, mids, why):
    """The count of FINISHED games and the clinch row must agree with the series: more FINISHED than gis, an even gis
    (both sides can reach needed: a tie), two FINISHED games at the latest start, or a clinch whose stored game number
    is not k (a FINISHED game not stored, or one more FINISHED row than its number) is no receipt. The other acceptance
    row still retires."""
    change(db)
    got, _ = plan()
    for mid in mids:
        assert (got[mid]["r2"]["verdict"], got[mid]["r2"]["why"]) == ("NO RECEIPT", why)
        assert got[mid]["action"] == "no receipt 2"
    assert got[50549 if 50549 not in mids else 50555]["action"] == "retire"


@pytest.mark.parametrize("gis", [0, -1])
def test_a_games_in_series_under_one_is_no_receipt_and_the_run_goes_on(db, monkeypatch, gis):
    """needed < 1 is no series: that row's receipt (2) says so; the run plans every other row and exits 0."""
    seed([(60001, 900001, "2026-10-19T20:08", "SCHEDULED", MIL, TB, None, None, "W", 1, gis, "World Series")])
    got, _ = plan()
    assert (got[60001]["r2"]["verdict"], got[60001]["r2"]["why"]) == (
        "NO RECEIPT", f"games_in_series {gis} is not a series length (needed 0)")
    assert got[60001]["r1"]["why"] == "the answer lists no game of this series (no other row of the series carries " \
                                      "a gamePk)"
    assert got[50555]["action"] == got[50549]["action"] == "retire"
    rc, out = cli_run(monkeypatch, Stats(schedule(*entries())))
    assert rc == 0, out
    assert "  plan: retire 2 · stays SCHEDULED 1 (listed 0 · not decided 0 · no receipt 1 1 · no receipt 2 0)" in \
        out.splitlines()


def test_with_no_stored_clinch_game_number_the_receipt_reads_k_finished_games(db):
    set_series(50551, series_game_number=None)
    got, _ = plan()
    r2 = got[50555]["r2"]
    assert (r2["verdict"], r2["why"]) == ("DECIDED", "decided after 6 FINISHED games, before game 7")
    assert r2["by"] == "this row game 7 (own), the series over after 6 FINISHED games" and r2["clinch_n"] is None
    set_series(50555, series_game_number=6)
    got, _ = plan()
    assert (got[50555]["r2"]["verdict"], got[50555]["r2"]["why"]) == ("NOT DECIDED",
                                                                      "game 6 (own) is not after 6 FINISHED games")


def test_an_unmigrated_db_is_no_receipt_two_naming_the_migration(db):
    con = sqlite3.connect(db)
    for c in ("series_game_number", "games_in_series", "series_description", "rescheduled_from"):
        con.execute(f"ALTER TABLE matches DROP COLUMN {c}")
    con.commit()
    con.close()
    got, _ = plan()
    for mid in (50555, 50549):
        assert got[mid]["r2"]["why"] == "series fields not stored (migrate_match_series_fields.py not run)"
        assert got[mid]["action"] == "no receipt 2"


def test_a_game_number_already_played_is_not_decided(db):
    set_series(50555, series_game_number=6)                            # its own n is not after the clinch, game 6
    got, _ = plan()
    assert got[50555]["r2"]["verdict"] == "NOT DECIDED"
    assert got[50555]["r2"]["why"] == "game 6 (own) is not after game 6, the clinch"


@pytest.mark.parametrize("start, et", [
    ("2026-10-15T23:00", "Thu 2026-10-15 19:00 ET"),                    # stored before Game 5's first pitch
    ("2026-10-16T00:08", "Thu 2026-10-15 20:08 ET"),                    # stored at the clinch's own start
], ids=["before-the-clinch", "at-the-clinchs-start"])
def test_with_no_own_game_number_a_clinch_not_before_this_rows_start_is_not_decided(db, start, et):
    update(50549, utc_date=Z(start))
    got, _ = plan()
    assert (got[50549]["r2"]["verdict"], got[50549]["r2"]["why"]) == (
        "NOT DECIDED", "the clinch did not start before this row's start")
    assert got[50549]["r2"]["by"] == ("game number: null (own); read by start: the clinch Thu 2026-10-15 20:08 ET, "
                                      f"this row {et}")
    assert got[50549]["action"] == "not decided"


def test_the_series_is_the_pair_either_way_round_of_one_season_and_stage(db):
    """Home and away flip inside a series (Games 1, 2 and 6 at Tampa Bay; 3 to 5 at Cleveland): every row counts. The
    same pair in another stage (an ALDS meeting) or another season is another series, never mixed in."""
    seed([(50400, 849700, "2026-10-05T20:08", "FINISHED", CLE, TB, 1, 9, "D", 1, 5, "AL Division Series"),
          (50401, 849701, "2026-10-06T20:08", "FINISHED", CLE, TB, 1, 9, "D", 2, 5, "AL Division Series")])
    seed([(40555, 749814, "2025-10-21T00:08", "FINISHED", CLE, TB, 0, 3, "L", 7, 7, ALCS)], season="2025")
    got, _ = plan()
    r2 = got[50555]["r2"]
    assert r2["ids"] == [50530, 50533, 50546, 50550, 50548, 50551, 50555]
    assert r2["wins"] == [("Tampa Bay Rays", 4), ("Cleveland Guardians", 2)] and r2["verdict"] == "DECIDED"


def test_a_description_that_differs_is_printed_never_a_gate(db, monkeypatch):
    set_series(50530, series_description="ALCS")
    got, r = plan()
    assert got[50555]["action"] == "retire" and got[50555]["r2"]["descriptions"] == [ALCS, "ALCS"]
    from src.ingestion import mlb_orphans as mo
    assert any('series "AL Championship Series" | "ALCS" (they differ; printed, never a gate)' in ln
               for ln in mo.lines(r))


# ---------------------------------------------------------------------------------------- never the watch --

def test_never_inside_the_watch():
    """Explicit, in the morning block (docs/CLI.md), never a chain or closing step: no CHAINS step and no
    deploy/hosting file names the command."""
    import sys
    sys.path.insert(0, str(ROOT / "deploy" / "hosting"))
    import chains
    steps = [st for chain in chains.CHAINS.values() for st in chain.get("steps", [])]
    assert steps and not any("retire-orphans" in st for st in steps)
    for f in (ROOT / "deploy" / "hosting").rglob("*"):
        if f.is_file() and f.suffix in (".py", ".sh", ".service", ".timer", ".plist", ".json", ".txt"):
            text = f.read_text(errors="replace")
            assert "retire-orphans" not in text and "retire_orphans" not in text, f


def test_a_row_retired_on_its_own_game_day_stays_in_that_days_prediction_export(db):
    """D9, documented, not changed here (an export change is gate-class): export-predictions' default status for
    today's range is all (cli.py), so a row retired on its game day, holding an earlier prediction, is still a row of
    that day's file, its status stale_orphan; the SCHEDULED-only readers (predict, scenarios) drop it. Whether the
    export should drop it as the fixtures export does is a question for the architect."""
    import json

    from src.db.database import session_scope
    from src.db.schema import MatchStatus, Prediction, Sport
    from src.walters.export import export_predictions
    with session_scope() as s:
        s.add(Prediction(match_id=50555, model_version="t", home_win_prob=0.55, draw_prob=None, away_win_prob=0.45))
    plan(apply=True, named={50555})
    lo, hi = Z("2026-10-20T08:00"), Z("2026-10-21T08:00")
    rows = json.loads(export_predictions(sport=Sport.MLB, start_date=lo, end_date=hi, competition_code="MLB"))
    assert [(r["match_id"], r["status"]) for r in rows["predictions"]] == [(50555, "stale_orphan")]
    sched = json.loads(export_predictions(sport=Sport.MLB, start_date=lo, end_date=hi, competition_code="MLB",
                                          statuses=[MatchStatus.SCHEDULED]))
    assert sched["predictions"] == []


def test_the_apply_holds_the_lock_from_the_backup_check_through_the_plan_and_the_write(db, monkeypatch, tmp_path):
    """#709 item 4 (Codex on #704): the apply takes the chains' DB lock before _verify_backup and holds it through the
    plan (its one call) and the write, so no chain commits between the backup check and the retire; a dry run takes
    none."""
    import cli
    from src.ingestion import mlb_orphans as mo
    from tests.test_mlb_twins import lock_taken, spy_db_lock
    monkeypatch.setenv("SP_LOCK", str(tmp_path / "db.lock"))
    lock_taken()
    taken, seen = spy_db_lock(monkeypatch), []
    real_verify, real_run = cli._verify_backup, mo.run
    monkeypatch.setattr(cli, "_verify_backup", lambda *a: seen.append(("backup", lock_taken())) or real_verify(*a))
    monkeypatch.setattr(mo, "run", lambda *a, **k: seen.append(("run", lock_taken())) or real_run(*a, **k))
    stats = Stats(schedule(*entries()))
    real_get = stats._get
    stats._get = lambda *a, **k: seen.append(("call", lock_taken())) or real_get(*a, **k)
    rc, out = cli_run(monkeypatch, stats)
    assert rc == 0, out
    assert seen == [("run", (0, False)), ("call", (0, False))] and taken == []
    seen.clear()
    good = backup(db, tmp_path / "good.backup")
    rc, out = cli_run(monkeypatch, stats, "--apply", "--backup", good, "--match-ids", "50555,50549")
    assert rc == 0, out
    assert "  applied: retired 2 (50549, 50555) · refused at apply 0 · named 50549, 50555" in out.splitlines()
    assert seen == [("backup", (1, True)), ("run", (1, True)), ("call", (1, True))]
    assert len(taken) == 1 and lock_taken() == (0, False)
