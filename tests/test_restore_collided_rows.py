"""THE RESTORE (ARCHITECT 2026-11-09, addendum 310 item 4; #902): scripts/restore_collided_rows.py on a throwaway DB
pair built with the app's schema in tmp_path (never data/): the refusals (a live row not the 2026 state, a --from row
not the 2025 state, both flags or neither), the dry run writes nothing (bytes and mtime), the apply produces exactly
the restored state and the moved rows, and is ONE transaction (an injected failure mid-way leaves the DB unchanged)."""
import importlib.util
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.db.schema import (AvailabilityObservation, Base, Competition, GameWeather, Match, MatchStats, MatchStatus,
                           Odds, OddsSnapshot, Result, Sport, Team)

_SPEC = importlib.util.spec_from_file_location(
    "restore_collided_rows", Path(__file__).resolve().parents[1] / "scripts" / "restore_collided_rows.py")
rc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rc)

AF = "api_american_football"
UTAH, CIN, ALA, LSU = 1, 2, 3, 4


_TEMPLATES: dict = {}


def _build(path: Path, state: str, extra=None) -> Path:
    """A DB with the app's schema: NCAA, the four teams, rows 36454 / 36753 in `state` ("2025": the 10-09 copy;
    "2026": today's live rows, the 2026 games' scores by team in the stored orientation, the chain's key). Built once
    per state (a template beside the first test's files), copied, then `extra` applied to the copy."""
    if state not in _TEMPLATES:
        tpl = path.parent / f"template_{state}.db.tpl"
        _populate(tpl, state)
        _TEMPLATES[state] = tpl.read_bytes()
        tpl.unlink()
    path.write_bytes(_TEMPLATES[state])
    if extra:
        eng = create_engine(f"sqlite:///{path}")
        with Session(eng) as s:
            for fn in extra:
                fn(s)
            s.commit()
        eng.dispose()
    return path


def _populate(path: Path, state: str) -> None:
    eng = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Competition(id=7, sport=Sport.NFL, code="NCAA", name="NCAA", area="USA", type="LEAGUE"))
        for tid, name in ((UTAH, "Utah"), (CIN, "Cincinnati"), (ALA, "Alabama"), (LSU, "LSU")):
            s.add(Team(id=tid, sport=Sport.NFL, name=name, external_ids={AF: f"t{tid}"}))
        s.add(Team(id=9, sport=Sport.NFL, name="Other", external_ids={AF: "t9"}))
        if state == "2025":
            rows = [(36454, "2025", datetime(2025, 11, 2, 2, 15), UTAH, CIN, 45, 14, Result.HOME, {AF: "18216"}),
                    (36753, "2025", datetime(2025, 11, 9, 0, 30), ALA, LSU, 20, 9, Result.HOME, {AF: "18240"})]
        else:
            rows = [(36454, "2026", datetime(2026, 10, 31, 19, 45), UTAH, CIN, 49, 25, Result.HOME,
                     {AF: "18216", "provider_orientation": "reversed"}),
                    (36753, "2026", datetime(2026, 11, 7, 20, 30), ALA, LSU, 31, 13, Result.HOME,
                     {AF: "18240", "provider_orientation": "reversed"})]
        for mid, season, ko, h, a, hs, as_, ftr, ext in rows:
            s.add(Match(id=mid, sport=Sport.NFL, competition_id=7, season=season, utc_date=ko,
                        status=MatchStatus.FINISHED, status_raw="FT", home_team_id=h, away_team_id=a, home_score=hs,
                        away_score=as_, home_score_ht=hs // 2, away_score_ht=as_ // 2, full_time_result=ftr,
                        external_ids=ext))
        s.add(Match(id=100, sport=Sport.NFL, competition_id=7, season="2026", utc_date=datetime(2026, 11, 1),
                    status=MatchStatus.SCHEDULED, home_team_id=9, away_team_id=UTAH, external_ids={AF: "999"}))
        # the 2025 game's weather, the same in both copies (stays with the restored row)
        s.add(GameWeather(id=1, match_id=36454, source_game_id="18216", game_date=datetime(2025, 11, 2, 2, 15),
                          venue="Utah", captured_at=datetime(2025, 11, 1)))
        if state == "2026":
            snap = dict(market="ML", n_books=0, captured_at=datetime(2026, 10, 30, 12), source="kalshi")
            s.add_all([OddsSnapshot(id=11, match_id=36454, selection="HOME", devig_prob=0.80, **snap),   # Utah
                       OddsSnapshot(id=12, match_id=36454, selection="AWAY", devig_prob=0.20, **snap),   # Cincinnati
                       OddsSnapshot(id=13, match_id=36753, selection="HOME", devig_prob=0.70, **snap),
                       OddsSnapshot(id=14, match_id=36753, selection="AWAY", devig_prob=0.30, **snap),
                       OddsSnapshot(id=15, match_id=36454, market="TOTALS", selection="OVER", devig_prob=0.5,
                                    line=52.5, n_books=3, captured_at=datetime(2026, 10, 30, 12),
                                    source=AF),
                       OddsSnapshot(id=16, match_id=100, selection="HOME", devig_prob=0.5, **snap)])
            s.add(Odds(id=21, match_id=36454, bookmaker="B", market="TOTALS", selection="UNDER", price_decimal=1.9,
                       line=52.5, captured_at=datetime(2026, 10, 30, 12), source=AF))
            s.add_all([MatchStats(id=31, match_id=36454, team_id=UTAH, extra_stats={"yards": 500}),
                       MatchStats(id=32, match_id=36454, team_id=CIN, extra_stats={"yards": 300})])
        s.commit()
    eng.dispose()


@pytest.fixture
def pair(tmp_path):
    def make(live_extra=None, from_extra=None):
        frm = _build(tmp_path / "from_1009.db", "2025", from_extra)
        live = _build(tmp_path / "live.db", "2026", live_extra)
        return live, frm
    return make


def _dump(p: Path) -> list[str]:
    con = sqlite3.connect(p)
    try:
        return list(con.iterdump())
    finally:
        con.close()


def _q(p: Path, sql, args=()):
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql, args)]
    finally:
        con.close()


def _main(live, frm, *flags, ids="36454,36753"):
    return rc.main(["--db", str(live), "--from", str(frm), "--ids", ids, *flags])


# ---------------------------------------------------------------------------- the flags


@pytest.mark.parametrize("flags", [(), ("--dry-run", "--apply")])
def test_exactly_one_of_dry_run_and_apply(pair, flags):
    live, frm = pair()
    before = _dump(live)
    with pytest.raises(SystemExit) as e:
        _main(live, frm, *flags)
    assert e.value.code == 2 and _dump(live) == before


@pytest.mark.parametrize("ids", ["36454", "36753", "36454,36454", "36454,36454,36753"])
def test_the_ids_must_name_exactly_the_pinned_rows(pair, capsys, ids):
    """Codex on #906 (P1): the two rows are restored together or not at all; a partial or repeated --ids refuses,
    nothing written, on a dry run and on an apply."""
    live, frm = pair()
    before = _dump(live)
    for flag in ("--dry-run", "--apply"):
        assert _main(live, frm, flag, ids=ids) == 2
        cap = capsys.readouterr()
        out = cap.out + cap.err
        # a partial set is the new refusal; a repeated id is refused earlier by --ids' own parse
        assert ("--ids must name exactly the pinned rows" in out) if "," not in ids else ("REFUSED" in out)
        assert _dump(live) == before


# ---------------------------------------------------------------------------- the dry run


def _wal(p: Path) -> None:
    """Put `p` in WAL mode, as the live DB is (src/db/database.py), and close it cleanly."""
    con = sqlite3.connect(p)
    try:
        assert con.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    finally:
        con.close()


@pytest.mark.parametrize("journal", ["delete", "wal"])
def test_the_dry_run_prints_the_plan_and_writes_nothing(pair, capsys, journal):
    live, frm = pair()
    if journal == "wal":
        _wal(live)
    raw, mtime = live.read_bytes(), os.stat(live).st_mtime_ns
    fraw, fmtime = frm.read_bytes(), os.stat(frm).st_mtime_ns
    assert _main(live, frm, "--dry-run") == 0
    out = capsys.readouterr().out
    # the database files' bytes and mtimes: unchanged
    assert live.read_bytes() == raw and os.stat(live).st_mtime_ns == mtime
    assert frm.read_bytes() == fraw and os.stat(frm).st_mtime_ns == fmtime
    names = sorted(p.name for p in live.parent.iterdir())
    if journal == "delete":
        assert names == ["from_1009.db", "live.db"]                                        # no journal, no -wal
    else:
        # a mode=ro open of a WAL file may leave SQLite's own sidecars; they hold no frame (nothing written)
        assert set(names) <= {"from_1009.db", "live.db", "live.db-wal", "live.db-shm"}
        wal = live.parent / "live.db-wal"
        assert not wal.exists() or wal.stat().st_size == 0
    assert "DRY RUN: nothing written" in out
    assert "PLAN 36454 -> NEW 2026 row (the listing's orientation): season 2026 · 2026-10-31 19:45:00" in out
    assert "Cincinnati 25 v Utah 49 · ftr AWAY" in out and "LSU 13 v Alabama 31 · ftr AWAY" in out
    assert "PLAN 36454 -> its 10-09 content: season 2025 · 2025-11-02 02:15:00" in out
    assert "PLAN 36454 MOVE odds_snapshots: 3 row(s) to the new id (2 Kalshi HOME/AWAY swapped" in out
    assert "PLAN 36454 MOVE odds: 1 row(s)" in out and "PLAN 36454 MOVE match_stats: 2 row(s)" in out
    assert "PLAN 36454 STAY game_weather: 1 row(s)" in out
    # every moved row by id (item 4: "prints before and after, every id")
    assert "PLAN 36454 MOVE odds_snapshots row 11: match_id 36454 -> the new id, selection HOME -> AWAY" in out
    assert "PLAN 36454 MOVE odds_snapshots row 15: match_id 36454 -> the new id (source" in out
    assert "PLAN 36454 MOVE match_stats row 31: match_id 36454 -> the new id" in out
    # the unkeyed append-only tables: counted, zeros included
    assert "COUNT 36454 availability_observations.match_id: 0 row(s)" in out
    assert "COUNT 36753 availability_assertions.match_id: 0 row(s)" in out
    print(out)                                                    # the receipt (pytest -s)


# ---------------------------------------------------------------------------- the refusals


def _set(sql, *args):
    def fn(s):
        s.flush()
        s.connection().exec_driver_sql(sql, args)
    return fn


@pytest.mark.parametrize("live_extra,from_extra,why", [
    ([_set("UPDATE matches SET season = '2025' WHERE id = 36454")], None, "live row 36454: season '2025'"),
    ([_set("UPDATE matches SET utc_date = '2026-10-31 19:46:00.000000' WHERE id = 36753")], None,
     "live row 36753: kickoff"),
    ([_set("""UPDATE matches SET external_ids = '{"api_american_football": "18217"}' WHERE id = 36454""")], None,
     "live row 36454: api_american_football '18217'"),
    ([_set("UPDATE teams SET name = 'Utah State' WHERE id = 1")], None, "live row 36454: teams 'Utah State'"),
    ([_set("UPDATE matches SET home_score = 25, away_score = 49 WHERE id = 36454")], None,
     "live row 36454: score 25-49"),
    (None, [_set("UPDATE matches SET season = '2026' WHERE id = 36454")], "from row 36454: season '2026'"),
    (None, [_set("UPDATE matches SET home_score = 44 WHERE id = 36753")], "from row 36753: score 44-9"),
    (None, [_set("DELETE FROM matches WHERE id = 36753")], "from row 36753 does not exist"),
    (None, [_set("""UPDATE matches SET external_ids = '{"api_american_football": "1"}' WHERE id = 36454""")],
     "from row 36454: api_american_football '1'"),
])
def test_a_row_not_in_its_pinned_state_is_refused(pair, capsys, live_extra, from_extra, why):
    live, frm = pair(live_extra, from_extra)
    before = _dump(live)
    assert _main(live, frm, "--apply") == 2
    out = capsys.readouterr().out
    assert why in out and "REFUSED" in out and _dump(live) == before


def test_a_book_side_stored_home_away_is_refused_not_guessed(pair, capsys):
    live, frm = pair([lambda s: s.add(OddsSnapshot(id=17, match_id=36454, market="1X2", selection="HOME",
                                                   devig_prob=0.6, n_books=4, captured_at=datetime(2026, 10, 30),
                                                   source=AF))])
    before = _dump(live)
    assert _main(live, frm, "--apply") == 2
    out = capsys.readouterr().out
    assert "odds_snapshots row 17 (source 'api_american_football', market '1X2', selection 'HOME'" in out
    assert _dump(live) == before


def test_a_2025_row_in_a_moved_table_is_refused(pair, capsys):
    live, frm = pair(None, [lambda s: s.add(MatchStats(id=40, match_id=36454, team_id=UTAH, extra_stats={}))])
    before = _dump(live)
    assert _main(live, frm, "--apply") == 2
    assert "match_stats: the 10-09 copy holds 1 row(s) on 36454" in capsys.readouterr().out
    assert _dump(live) == before


def test_a_row_added_since_in_another_table_is_refused(pair, capsys):
    live, frm = pair([lambda s: s.add(GameWeather(id=2, match_id=36753, source_game_id="18240",
                                                  game_date=datetime(2026, 11, 7), venue="Alabama"))])
    before = _dump(live)
    assert _main(live, frm, "--apply") == 2
    assert "game_weather: 1 row(s) on 36753 added or changed since the 10-09 copy" in capsys.readouterr().out
    assert _dump(live) == before


def test_a_book_side_stored_home_away_in_odds_is_refused_not_guessed(pair, capsys):
    live, frm = pair([lambda s: s.add(Odds(id=22, match_id=36753, bookmaker="B", market="1X2", selection="AWAY",
                                           price_decimal=2.5, captured_at=datetime(2026, 11, 6), source=AF))])
    before = _dump(live)
    assert _main(live, frm, "--apply") == 2
    assert "odds row 22 (source 'api_american_football', market '1X2', selection 'AWAY'" in capsys.readouterr().out
    assert _dump(live) == before


def test_a_row_of_the_copy_the_live_file_lost_is_refused(pair, capsys):
    live, frm = pair([_set("DELETE FROM game_weather WHERE id = 1")])
    before = _dump(live)
    assert _main(live, frm, "--apply") == 2
    assert "game_weather: 0 row(s) on 36454 added or changed since the 10-09 copy, 1 row(s) of the copy gone" in \
        capsys.readouterr().out
    assert _dump(live) == before


def test_a_table_the_copy_lacks_is_refused_when_the_live_file_has_rows_on_the_id(pair, capsys):
    live, frm = pair(None, [_set("DROP TABLE game_weather")])
    before = _dump(live)
    assert _main(live, frm, "--apply") == 2
    assert "game_weather: 1 row(s) on 36454 added or changed since the 10-09 copy" in capsys.readouterr().out
    assert _dump(live) == before


def test_an_availability_row_added_since_the_copy_is_refused(pair, capsys):
    live, frm = pair([lambda s: s.add(AvailabilityObservation(
        id=1, sport=Sport.NFL, source="nflverse_depth_charts", endpoint="e", match_id=36753, status="empty",
        fetched_at=datetime(2026, 11, 6), rows_asserted=0))])
    before = _dump(live)
    assert _main(live, frm, "--apply") == 2
    out = capsys.readouterr().out
    assert "COUNT 36753 availability_observations.match_id: 1 row(s)" in out
    assert "availability_observations: 1 row(s) on 36753 added or changed since the 10-09 copy" in out
    assert _dump(live) == before


def test_a_row_count_written_other_than_planned_rolls_back(pair, capsys):
    """The pre-commit count (two creates, the moved rows, two rewrites): a write the plan does not name (here a
    trigger's, injected into the live file) refuses and rolls back."""
    def trig(s):
        s.flush()
        s.connection().exec_driver_sql("CREATE TABLE side_effect (x INTEGER)")
        s.connection().exec_driver_sql("CREATE TRIGGER t_side AFTER UPDATE ON match_stats BEGIN "
                                       "INSERT INTO side_effect VALUES (NEW.id); END")
    live, frm = pair([trig], [_set("CREATE TABLE side_effect (x INTEGER)")])
    before = _dump(live)
    assert _main(live, frm, "--apply") == 2
    out = capsys.readouterr().out
    assert "row(s) written, not the 12 planned; rolled back" in out and "ROLLED BACK" in out
    assert _dump(live) == before


def test_an_id_with_no_pinned_state_and_the_same_file_are_refused(pair, capsys):
    live, frm = pair()
    before = _dump(live)
    assert _main(live, frm, "--apply", ids="36454,100") == 2
    assert _main(live, live, "--apply") == 2
    out = capsys.readouterr().out
    assert "ids [100] have no pinned state" in out and "--db and --from are the same file" in out
    assert _dump(live) == before


# ---------------------------------------------------------------------------- the apply


def test_the_apply_writes_exactly_the_restored_state_and_moves_the_rows(pair, capsys):
    live, frm = pair()
    from_rows = {r["id"]: r for r in _q(frm, "SELECT * FROM matches WHERE id IN (36454, 36753)")}
    live_rows = {r["id"]: r for r in _q(live, "SELECT * FROM matches WHERE id IN (36454, 36753)")}
    other = _q(live, "SELECT * FROM matches WHERE id = 100") + _q(live, "SELECT * FROM odds_snapshots WHERE id = 16")
    assert _main(live, frm, "--apply") == 0
    out = capsys.readouterr().out
    assert "COMMITTED" in out
    # 36454 / 36753: their 10-09 content, every column (no provider_orientation in the copy: its text verbatim)
    for mid in (36454, 36753):
        assert _q(live, "SELECT * FROM matches WHERE id = ?", (mid,))[0] == from_rows[mid]
    new = {r["home_team_id"]: r for r in _q(live, "SELECT * FROM matches WHERE id NOT IN (36454, 36753, 100)")}
    assert set(new) == {CIN, LSU}
    cin, lsu = new[CIN], new[LSU]
    assert (cin["away_team_id"], cin["home_score"], cin["away_score"], cin["full_time_result"]) == (UTAH, 25, 49, "AWAY")
    assert (cin["home_score_ht"], cin["away_score_ht"]) == (12, 24)          # every score pair swapped
    assert (lsu["away_team_id"], lsu["home_score"], lsu["away_score"], lsu["full_time_result"]) == (ALA, 13, 31, "AWAY")
    for r, mid, sid in ((cin, 36454, "18216"), (lsu, 36753, "18240")):
        lr = live_rows[mid]
        assert (r["season"], r["status"], r["utc_date"], r["status_raw"]) == ("2026", "FINISHED", lr["utc_date"], "FT")
        assert json.loads(r["external_ids"]) == {AF: sid}                    # provider_orientation removed
    # the moved rows: Kalshi HOME/AWAY swapped (the price stays with its team), the rest as they were
    snaps = {r["id"]: r for r in _q(live, "SELECT * FROM odds_snapshots")}
    assert (snaps[11]["match_id"], snaps[11]["selection"], snaps[11]["devig_prob"]) == (cin["id"], "AWAY", 0.80)
    assert (snaps[12]["match_id"], snaps[12]["selection"]) == (cin["id"], "HOME")
    assert (snaps[13]["match_id"], snaps[13]["selection"], snaps[14]["selection"]) == (lsu["id"], "AWAY", "HOME")
    assert (snaps[15]["match_id"], snaps[15]["selection"], snaps[15]["line"]) == (cin["id"], "OVER", 52.5)
    assert _q(live, "SELECT match_id, selection FROM odds") == [{"match_id": cin["id"], "selection": "UNDER"}]
    assert sorted((r["match_id"], r["team_id"]) for r in _q(live, "SELECT * FROM match_stats")) == \
        [(cin["id"], UTAH), (cin["id"], CIN)]
    assert _q(live, "SELECT match_id FROM game_weather") == [{"match_id": 36454}]          # the 2025 game's stays
    assert _q(live, "SELECT * FROM matches WHERE id = 100") + _q(live, "SELECT * FROM odds_snapshots WHERE id = 16") \
        == other
    assert f"AFTER odds_snapshots: 0 row(s) on 36454 · 3 row(s) on {cin['id']}" in out
    assert f"AFTER odds_snapshots row 11: match_id {cin['id']}, selection AWAY" in out
    assert f"AFTER match_stats row 32: match_id {cin['id']}" in out
    assert "ROWS WRITTEN: 12 (expected 12: 2 created, 8 moved, 2 restored)" in out
    # a second apply refuses and writes nothing: the live rows read the 2025 state now
    after = _dump(live)
    assert _main(live, frm, "--apply") == 2
    assert _dump(live) == after


@pytest.mark.parametrize("journal", ["delete", "wal"])
@pytest.mark.parametrize("where", ["after_create", "after_moves", "before_commit"])
def test_the_apply_is_one_transaction(pair, where, journal):
    live, frm = pair()
    if journal == "wal":
        _wal(live)
    before = _dump(live)
    with pytest.raises(RuntimeError, match="injected failure"):
        rc.run(live, frm, [36454, 36753], True, out=lambda *_: None, _fail_at=where)
    assert _dump(live) == before
