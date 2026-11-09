"""THE RESTORE (ARCHITECT 2026-11-09, addendum 310 item 4 and addendum 312 item 3; #902):
scripts/restore_collided_rows.py on throwaway DB pairs built with the app's schema in tmp_path (never data/): the rows
found by PROVIDER ID and season (the laptop's ids and a host-like file whose row and team ids differ), the refusals (a
live row not the 2026 state, a copy row not the 2025 state, a live 2025 row already there, a copy row on another id,
both flags or neither, --ids that do not name the rows found), the dry run writes nothing (bytes and mtime), the apply
produces exactly the restored state and the moved rows, and is ONE transaction (an injected failure mid-way leaves the
DB unchanged); --book-rows, --move-added, and the --emit-json -> --from-json round trip."""
import hashlib
import importlib.util
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.db.schema import (AvailabilityObservation, Base, Competition, GameWeather, KalshiSettledMarket, Match,
                           MatchStats, MatchStatus, NCAACFBDLabel, NCAACFBDPregame, Odds, OddsSnapshot, Result, Sport,
                           Team)

_SPEC = importlib.util.spec_from_file_location(
    "restore_collided_rows", Path(__file__).resolve().parents[1] / "scripts" / "restore_collided_rows.py")
rc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rc)

AF = "api_american_football"
# the laptop: the row ids of item 1; the host: other row ids, other team ids, an other competition id, provider ids
# stored as ints (the identification compares them as text)
LAPTOP = {"name": "laptop", "rows": (36454, 36753, 100), "comp": 7, "pid": str,
          "teams": {"Utah": 1, "Cincinnati": 2, "Alabama": 3, "LSU": 4, "Other": 9}}
HOST = {"name": "host", "rows": (41001, 41377, 500), "comp": 12, "pid": int,
        "teams": {"Utah": 21, "Cincinnati": 23, "Alabama": 25, "LSU": 27, "Other": 29}}
UTAH, CIN, ALA, LSU = (LAPTOP["teams"][n] for n in ("Utah", "Cincinnati", "Alabama", "LSU"))

_TEMPLATES: dict = {}


def _build(path: Path, state: str, extra=None, layout=LAPTOP) -> Path:
    """A DB with the app's schema: NCAA, the four teams, the two rows in `state` ("2025": the copy; "2026": today's
    live rows, the 2026 games' scores by team in the stored orientation, the chain's key). Built once per (state,
    layout) (a template beside the first test's files), copied, then `extra` applied to the copy."""
    k = (state, layout["name"])
    if k not in _TEMPLATES:
        tpl = path.parent / f"template_{state}_{layout['name']}.db.tpl"
        _populate(tpl, state, layout)
        _TEMPLATES[k] = tpl.read_bytes()
        tpl.unlink()
    path.write_bytes(_TEMPLATES[k])
    if extra:
        eng = create_engine(f"sqlite:///{path}")
        with Session(eng) as s:
            for fn in extra:
                fn(s)
            s.commit()
        eng.dispose()
    return path


def _populate(path: Path, state: str, L: dict) -> None:
    eng = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(eng)
    a, b, other = L["rows"]
    T, comp, pid = L["teams"], L["comp"], L["pid"]
    with Session(eng) as s:
        s.add(Competition(id=comp, sport=Sport.NFL, code="NCAA", name="NCAA", area="USA", type="LEAGUE"))
        for name, tid in T.items():
            s.add(Team(id=tid, sport=Sport.NFL, name=name, external_ids={AF: f"t{tid}"}))
        if state == "2025":
            rows = [(a, "2025", datetime(2025, 11, 2, 2, 15), T["Utah"], T["Cincinnati"], 45, 14, {AF: pid("18216")}),
                    (b, "2025", datetime(2025, 11, 9, 0, 30), T["Alabama"], T["LSU"], 20, 9, {AF: pid("18240")})]
        else:
            rows = [(a, "2026", datetime(2026, 10, 31, 19, 45), T["Utah"], T["Cincinnati"], 49, 25,
                     {AF: pid("18216"), "provider_orientation": "reversed"}),
                    (b, "2026", datetime(2026, 11, 7, 20, 30), T["Alabama"], T["LSU"], 31, 13,
                     {AF: pid("18240"), "provider_orientation": "reversed"})]
        for mid, season, ko, h, aw, hs, as_, ext in rows:
            s.add(Match(id=mid, sport=Sport.NFL, competition_id=comp, season=season, utc_date=ko,
                        status=MatchStatus.FINISHED, status_raw="FT", home_team_id=h, away_team_id=aw, home_score=hs,
                        away_score=as_, home_score_ht=hs // 2, away_score_ht=as_ // 2, full_time_result=Result.HOME,
                        external_ids=ext))
        s.add(Match(id=other, sport=Sport.NFL, competition_id=comp, season="2026", utc_date=datetime(2026, 11, 1),
                    status=MatchStatus.SCHEDULED, home_team_id=T["Other"], away_team_id=T["Utah"],
                    external_ids={AF: "999"}))
        # the 2025 game's weather, the same in both copies (stays with the restored row)
        s.add(GameWeather(id=1, match_id=a, source_game_id="18216", game_date=datetime(2025, 11, 2, 2, 15),
                          venue="Utah", captured_at=datetime(2025, 11, 1)))
        if state == "2026":
            snap = dict(market="ML", n_books=0, captured_at=datetime(2026, 10, 30, 12), source="kalshi")
            s.add_all([OddsSnapshot(id=11, match_id=a, selection="HOME", devig_prob=0.80, **snap),   # Utah
                       OddsSnapshot(id=12, match_id=a, selection="AWAY", devig_prob=0.20, **snap),   # Cincinnati
                       OddsSnapshot(id=13, match_id=b, selection="HOME", devig_prob=0.70, **snap),
                       OddsSnapshot(id=14, match_id=b, selection="AWAY", devig_prob=0.30, **snap),
                       OddsSnapshot(id=15, match_id=a, market="TOTALS", selection="OVER", devig_prob=0.5,
                                    line=52.5, n_books=3, captured_at=datetime(2026, 10, 30, 12), source=AF),
                       OddsSnapshot(id=16, match_id=other, selection="HOME", devig_prob=0.5, **snap)])
            s.add(Odds(id=21, match_id=a, bookmaker="B", market="TOTALS", selection="UNDER", price_decimal=1.9,
                       line=52.5, captured_at=datetime(2026, 10, 30, 12), source=AF))
            s.add_all([MatchStats(id=31, match_id=a, team_id=T["Utah"], extra_stats={"yards": 500}),
                       MatchStats(id=32, match_id=a, team_id=T["Cincinnati"], extra_stats={"yards": 300})])
        s.commit()
    eng.dispose()


@pytest.fixture
def pair(tmp_path):
    def make(live_extra=None, from_extra=None, layout=LAPTOP):
        frm = _build(tmp_path / "from_copy.db", "2025", from_extra, layout)
        live = _build(tmp_path / "live.db", "2026", live_extra, layout)
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


def _main(live, frm, *flags, ids=None):
    return rc.main(["--db", str(live), "--from", str(frm), *(["--ids", ids] if ids is not None else []), *flags])


def _main_json(live, extract, *flags):
    return rc.main(["--db", str(live), "--from-json", str(extract), *flags])


def _written(n, moved, added, cfbd_moved=0, cfbd_restored=0) -> str:
    """The pre-commit count's line (two created, two restored; 314 item 2's CFBD parts named, zeros included)."""
    return (f"ROWS WRITTEN: {n} (expected {n}: 2 created, {moved} moved, {added} added moved, {cfbd_moved} CFBD "
            f"moved+reoriented, {cfbd_restored} CFBD restored from the copy, 2 restored)")


def _set(sql, *args):
    def fn(s):
        s.flush()
        s.connection().exec_driver_sql(sql, args)
    return fn


# ---------------------------------------------------------------------------- the flags


@pytest.mark.parametrize("flags", [(), ("--dry-run", "--apply")])
def test_exactly_one_of_dry_run_and_apply(pair, flags):
    live, frm = pair()
    before = _dump(live)
    with pytest.raises(SystemExit) as e:
        _main(live, frm, *flags)
    assert e.value.code == 2 and _dump(live) == before


def test_exactly_one_of_from_and_from_json(pair, tmp_path):
    live, frm = pair()
    before = _dump(live)
    for argv in (["--db", str(live), "--dry-run"],
                 ["--db", str(live), "--from", str(frm), "--from-json", str(tmp_path / "x.json"), "--dry-run"]):
        with pytest.raises(SystemExit) as e:
            rc.main(argv)
        assert e.value.code == 2
    assert _dump(live) == before


@pytest.mark.parametrize("ids", ["36454", "36753", "36454,36454", "36454,36454,36753", "36454,36754",
                                 "36454,100", "36454,36753,100"])
def test_ids_when_given_must_name_exactly_the_rows_found(pair, capsys, ids):
    """Codex on #906 (P1): the two rows are restored together or not at all; --ids (optional since addendum 312 item
    3(e)) must name exactly the live row ids found by provider id, each once; nothing written, dry run or apply."""
    live, frm = pair()
    before = _dump(live)
    for flag in ("--dry-run", "--apply"):
        assert _main(live, frm, flag, ids=ids) == 2
        out = capsys.readouterr().out
        if len(set(ids.split(","))) == len(ids.split(",")):
            assert "--ids must name exactly the live row ids found by provider id [36454, 36753], each once" in out
        else:
            assert "REFUSED: --ids" in out and "names no id, or one twice" in out
        assert _dump(live) == before


def test_ids_given_and_matching_is_accepted(pair, capsys):
    live, frm = pair()
    assert _main(live, frm, "--dry-run", ids="36753,36454") == 0
    assert "DRY RUN: nothing written" in capsys.readouterr().out


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
        assert names == ["from_copy.db", "live.db"]                                        # no journal, no -wal
    else:
        # a mode=ro open of a WAL file may leave SQLite's own sidecars; they hold no frame (nothing written)
        assert set(names) <= {"from_copy.db", "live.db", "live.db-wal", "live.db-shm"}
        wal = live.parent / "live.db-wal"
        assert not wal.exists() or wal.stat().st_size == 0
    assert "addendum 310 item 4 and addendum 312 item 3" in out.splitlines()[0]
    assert "--ids (not given: the rows found by provider id)" in out
    # the rows found by provider id, their ids read and printed
    assert "FOUND 18216 live: row 36454 season '2026'" in out and "FOUND 18240 from: row 36753 season '2025'" in out
    assert "ROW 18216: live row id 36454 (season 2026); the copy's 2025 row reads the same id" in out
    assert "DRY RUN: nothing written" in out
    assert "PLAN 36454 -> NEW 2026 row (the listing's orientation): season 2026 · 2026-10-31 19:45:00" in out
    assert "Cincinnati 25 v Utah 49 · ftr AWAY" in out and "LSU 13 v Alabama 31 · ftr AWAY" in out
    assert "PLAN 36454 -> its copy's content: season 2025 · 2025-11-02 02:15:00" in out
    assert "PLAN 36454 MOVE odds_snapshots: 3 row(s) to the new id (2 Kalshi HOME/AWAY swapped" in out
    assert "PLAN 36454 MOVE odds: 1 row(s)" in out and "PLAN 36454 MOVE match_stats: 2 row(s)" in out
    assert "PLAN 36454 STAY game_weather: 1 row(s)" in out
    # every moved row by id, its selection before and after, swapped or not (312 item 3(a))
    assert ("PLAN 36454 MOVE odds_snapshots row 11: match_id 36454 -> the new id, selection HOME -> AWAY (swapped: "
            "Kalshi, on the stored home's name (addendum 312 item 3(a))) (source 'kalshi', market 'ML', captured_at "
            "2026-10-30 12:00:00") in out
    assert "PLAN 36753 MOVE odds_snapshots row 14: match_id 36753 -> the new id, selection AWAY -> HOME (swapped" in out
    assert ("PLAN 36454 MOVE odds_snapshots row 15: match_id 36454 -> the new id, selection OVER -> OVER (as is) "
            "(source 'api_american_football', market 'TOTALS', captured_at 2026-10-30 12:00:00") in out
    assert "PLAN 36454 MOVE odds row 21: match_id 36454 -> the new id, selection UNDER -> UNDER (as is)" in out
    assert "PLAN 36454 MOVE match_stats row 31: match_id 36454 -> the new id" in out
    # the unkeyed append-only tables: counted, zeros included
    assert "COUNT 36454 availability_observations.match_id: 0 row(s)" in out
    assert "COUNT 36753 availability_assertions.match_id: 0 row(s)" in out
    print(out)                                                    # the receipt (pytest -s)


# ---------------------------------------------------------------------------- the identification (312 item 3(e))


@pytest.mark.parametrize("live_extra,from_extra,why", [
    ([_set("UPDATE matches SET season = '2025' WHERE id = 36454")], None,
     ["provider id 18216: 0 live NCAA row(s) in season year 2026 (none), not exactly one",
      "provider id 18216: the live file already holds a 2025 row (36454): already restored, or never collided"]),
    ([_set("UPDATE matches SET utc_date = '2026-10-31 19:46:00.000000' WHERE id = 36753")], None,
     ["live row 36753 (provider id 18240): kickoff"]),
    ([_set("""UPDATE matches SET external_ids = '{"api_american_football": "18217"}' WHERE id = 36454""")], None,
     ["provider id 18216: 0 live NCAA row(s) in season year 2026"]),
    ([_set("UPDATE teams SET name = 'Utah State' WHERE id = 1")], None,
     ["live row 36454 (provider id 18216): teams 'Utah State'"]),
    ([_set("UPDATE matches SET home_score = 25, away_score = 49 WHERE id = 36454")], None,
     ["live row 36454 (provider id 18216): score 25-49"]),
    ([_set("UPDATE competitions SET code = 'NFL' WHERE id = 7")], None,
     ["provider id 18216: 0 live NCAA row(s) in season year 2026", "FOUND 18216 live: no NCAA row"]),
    (None, [_set("UPDATE matches SET season = '2026' WHERE id = 36454")],
     ["provider id 18216: 0 NCAA row(s) in season year 2025 in the copy (none), not exactly one"]),
    (None, [_set("UPDATE matches SET home_score = 44 WHERE id = 36753")],
     ["from row 36753 (provider id 18240): score 44-9"]),
    (None, [_set("DELETE FROM matches WHERE id = 36753")],
     ["provider id 18240: 0 NCAA row(s) in season year 2025 in the copy"]),
    (None, [_set("""UPDATE matches SET external_ids = '{"api_american_football": "1"}' WHERE id = 36454""")],
     ["provider id 18216: 0 NCAA row(s) in season year 2025 in the copy"]),
])
def test_a_row_not_found_or_not_in_its_pinned_state_is_refused(pair, capsys, live_extra, from_extra, why):
    live, frm = pair(live_extra, from_extra)
    before = _dump(live)
    assert _main(live, frm, "--apply") == 2
    out = capsys.readouterr().out
    assert all(w in out for w in why), out
    assert "REFUSED" in out and _dump(live) == before


def test_a_live_file_already_holding_a_2025_row_for_the_id_is_refused(pair, capsys):
    live, frm = pair([lambda s: s.add(Match(
        id=200, sport=Sport.NFL, competition_id=7, season="2025", utc_date=datetime(2025, 11, 2, 2, 15),
        status=MatchStatus.FINISHED, home_team_id=UTAH, away_team_id=CIN, home_score=45, away_score=14,
        external_ids={AF: 18216}))])                                          # an int id: compared as text
    before = _dump(live)
    for flag in ("--dry-run", "--apply"):
        assert _main(live, frm, flag) == 2
        out = capsys.readouterr().out
        assert "FOUND 18216 live: row 200 season '2025', row 36454 season '2026'" in out
        assert "provider id 18216: the live file already holds a 2025 row (200): already restored, or never " \
               "collided" in out
    assert _dump(live) == before


def test_two_live_2026_rows_for_one_id_are_refused(pair, capsys):
    live, frm = pair([lambda s: s.add(Match(
        id=201, sport=Sport.NFL, competition_id=7, season="2026/27", utc_date=datetime(2026, 10, 31),
        status=MatchStatus.SCHEDULED, home_team_id=CIN, away_team_id=UTAH, external_ids={AF: "18216"}))])
    before = _dump(live)
    assert _main(live, frm, "--apply") == 2
    assert "provider id 18216: 2 live NCAA row(s) in season year 2026 (201, 36454), not exactly one" in \
        capsys.readouterr().out
    assert _dump(live) == before


def test_a_copy_row_on_another_id_is_refused(pair, capsys):
    live, frm = pair(None, [_set("UPDATE matches SET id = 40000 WHERE id = 36454")])
    before = _dump(live)
    assert _main(live, frm, "--apply") == 2
    assert "provider id 18216: the copy's 2025 row is 40000 and the live 2026 row is 36454: the row was overwritten " \
           "in place; a different id is another history" in capsys.readouterr().out
    assert _dump(live) == before


def test_the_host_rows_are_found_by_provider_id_not_by_row_id(pair, capsys):
    """A host-like pair: other row ids (41001 / 41377), other team ids, another competition id, provider ids stored
    as ints. No --ids: the ids found are used, printed; the apply restores them as on the laptop."""
    live, frm = pair(layout=HOST)
    T = HOST["teams"]
    from_rows = {r["id"]: r for r in _q(frm, "SELECT * FROM matches WHERE id IN (41001, 41377)")}
    assert _main(live, frm, "--dry-run") == 0
    out = capsys.readouterr().out
    assert "ROW 18216: live row id 41001" in out and "ROW 18240: live row id 41377" in out
    assert "36454" not in out and "36753" not in out
    assert _main(live, frm, "--dry-run", ids="36454,36753") == 2
    assert "--ids must name exactly the live row ids found by provider id [41001, 41377]" in capsys.readouterr().out
    assert _main(live, frm, "--apply", ids="41377,41001") == 0
    out = capsys.readouterr().out
    assert "COMMITTED" in out and "ROWS WRITTEN: 12 (expected 12" in out
    for mid in (41001, 41377):
        assert _q(live, "SELECT * FROM matches WHERE id = ?", (mid,))[0] == from_rows[mid]
    new = {r["home_team_id"]: r for r in _q(live, "SELECT * FROM matches WHERE id NOT IN (41001, 41377, 500)")}
    assert set(new) == {T["Cincinnati"], T["LSU"]}
    assert (new[T["Cincinnati"]]["away_team_id"], new[T["Cincinnati"]]["home_score"]) == (T["Utah"], 25)
    assert json.loads(new[T["LSU"]]["external_ids"]) == {AF: 18240}
    assert _q(live, "SELECT selection FROM odds_snapshots WHERE id = 11") == [{"selection": "AWAY"}]


# ---------------------------------------------------------------------------- book rows (312 item 3(b))


def _book_rows(s):
    s.add(OddsSnapshot(id=17, match_id=36454, market="1X2", selection="HOME", devig_prob=0.6, n_books=4,
                       captured_at=datetime(2026, 10, 30), source=AF))                         # before #885
    s.add(Odds(id=22, match_id=36753, bookmaker="B", market="ML", selection="AWAY", price_decimal=2.5,
               captured_at=datetime(2026, 11, 9, 3), source=AF))                               # after #885
    s.add(Odds(id=23, match_id=36753, bookmaker="C", market="ML", selection="HOME", price_decimal=1.5,
               captured_at=datetime(2026, 11, 8, 21, 21, 44), source=AF))                      # at the merge: before


def test_book_rows_are_refused_by_default_and_still_printed(pair, capsys):
    live, frm = pair([_book_rows])
    before = _dump(live)
    for flag in ("--dry-run", "--apply"):
        assert _main(live, frm, flag) == 2
        out = capsys.readouterr().out
        assert ("BOOK 36454 odds_snapshots row 17: source 'api_american_football', market '1X2', captured_at "
                "2026-10-30 00:00:00.000000, selection HOME · before #885 (the provider's, which is the new row's -> "
                "keep) · --book-rows refuse: REFUSED") in out
        assert ("BOOK 36753 odds row 22: source 'api_american_football', bookmaker 'B', market 'ML', captured_at "
                "2026-11-09 03:00:00.000000, selection AWAY · after #885 (the stored orientation -> swap) · "
                "--book-rows refuse: REFUSED") in out
        assert "BOOK 36753 odds row 23:" in out and "selection HOME · before #885" in out
        assert "REFUSED: row 36454: odds_snapshots row 17" in out and "--book-rows refuse" in out
        assert _dump(live) == before


@pytest.mark.parametrize("mode,want", [("swap", {17: "AWAY", 22: "HOME", 23: "AWAY"}),
                                       ("keep", {17: "HOME", 22: "AWAY", 23: "HOME"})])
def test_book_rows_swap_or_keep_one_mode_for_every_row(pair, capsys, mode, want):
    live, frm = pair([_book_rows])
    assert _main(live, frm, "--dry-run", "--book-rows", mode) == 0
    out = capsys.readouterr().out
    # the classification is printed in every mode; the mode decides the write
    assert "odds_snapshots row 17:" in out and "before #885 (the provider's, which is the new row's -> keep) · " \
                                                "--book-rows " + mode in out
    assert "after #885 (the stored orientation -> swap) · --book-rows " + mode in out
    assert f"BOOK 36753 odds row 22: " in out and f"--book-rows {mode}: selection AWAY -> {want[22]}" in out
    assert f"PLAN 36454 MOVE odds_snapshots row 17: match_id 36454 -> the new id, selection HOME -> {want[17]}" in out
    assert _main(live, frm, "--apply", "--book-rows", mode) == 0
    out = capsys.readouterr().out
    assert _written(15, 11, 0) in out
    got = {r["id"]: r["selection"] for r in _q(live, "SELECT id, selection FROM odds_snapshots WHERE id = 17")}
    got.update({r["id"]: r["selection"] for r in _q(live, "SELECT id, selection FROM odds WHERE id IN (22, 23)")})
    assert got == want
    # moved to the new rows, Kalshi swapped as ruled whatever the book mode
    assert _q(live, "SELECT match_id FROM odds WHERE id = 22")[0]["match_id"] not in (36753,)
    assert _q(live, "SELECT selection FROM odds_snapshots WHERE id = 11") == [{"selection": "AWAY"}]


# ---------------------------------------------------------------------------- the other tables (312 item 3(c))


def _added_weather(s):
    s.add(GameWeather(id=2, match_id=36753, source_game_id="18240", game_date=datetime(2026, 11, 7),
                      venue="Alabama", captured_at=datetime(2026, 11, 7)))


def test_a_row_added_since_in_another_table_is_refused_without_move_added(pair, capsys):
    live, frm = pair([_added_weather])
    before = _dump(live)
    assert _main(live, frm, "--apply") == 2
    out = capsys.readouterr().out
    assert "ADDED 36753 game_weather row 2: id=2, source_game_id='18240'" in out and "-> REFUSED (no --move-added)" in out
    assert "game_weather: 1 row(s) on 36753 added since the copy (2); --move-added not given" in out
    assert _dump(live) == before


def test_move_added_moves_the_added_rows_and_counts_them(pair, capsys):
    live, frm = pair([_added_weather])
    assert _main(live, frm, "--dry-run", "--move-added") == 0
    out = capsys.readouterr().out
    assert "ADDED 36753 game_weather row 2: " in out and "-> MOVE to the new id (--move-added)" in out
    assert "PLAN 36753 MOVE game_weather: 1 row(s) added since the copy to the new id (--move-added)" in out
    assert "PLAN 36454 STAY game_weather: 1 row(s)" in out
    assert _main(live, frm, "--apply", "--move-added") == 0
    out = capsys.readouterr().out
    assert _written(13, 8, 1) in out
    lsu = _q(live, "SELECT id FROM matches WHERE home_team_id = ? AND season = '2026'", (LSU,))[0]["id"]
    assert {r["id"]: r["match_id"] for r in _q(live, "SELECT id, match_id FROM game_weather")} == {1: 36454, 2: lsu}
    assert f"AFTER game_weather row 2: match_id {lsu}" in out


@pytest.mark.parametrize("live_extra,why", [
    ([_set("UPDATE game_weather SET venue = 'Elsewhere' WHERE id = 1")],
     ["CHANGED 36454 game_weather row 1", "game_weather: 1 row(s) on 36454 changed since the copy (1), 0 row(s) of "
                                          "the copy gone (none)"]),
    ([_set("DELETE FROM game_weather WHERE id = 1")],
     ["LOST 36454 game_weather row 1", "game_weather: 0 row(s) on 36454 changed since the copy (none), 1 row(s) of "
                                       "the copy gone (1)"]),
])
def test_a_changed_or_lost_row_is_refused_even_with_move_added(pair, capsys, live_extra, why):
    live, frm = pair(live_extra)
    before = _dump(live)
    assert _main(live, frm, "--apply", "--move-added") == 2
    out = capsys.readouterr().out
    assert all(w in out for w in why), out
    assert _dump(live) == before


def test_changed_and_added_are_told_by_the_key_not_the_content(pair, capsys):
    """A live row with the copy's key and other content is CHANGED (refused), never 'added + lost'."""
    live, frm = pair([_set("UPDATE game_weather SET temperature_f = 41.0 WHERE id = 1")])
    assert _main(live, frm, "--dry-run", "--move-added") == 2
    out = capsys.readouterr().out
    assert "CHANGED 36454 game_weather row 1" in out and "ADDED 36454 game_weather" not in out and "LOST" not in out


def _ksm(i, side, mid=36454):
    return lambda s: s.add(KalshiSettledMarket(
        id=i, ticker=f"KXNCAAFGAME-26OCT31UTACIN-{i}", series="KXNCAAFGAME", side=side, match_id=mid,
        yes_sub_title="Utah", source="live", fetched_at=datetime(2026, 11, 1)))


def test_an_added_row_side_column_swaps_under_move_added(pair, capsys):
    """ARCHITECT 2026-11-09 16:05 ET, addendum 313 item 1(1), verbatim: "kalshi_settled_markets.side on the moved 2026
    rows: SWAP, the same rule as the snapshots (3(a)) — the side was placed against the stored home team, and the new
    row's home is the old row's away; the dry run's ORIENTED mark becomes "swap" in the apply's print. Any other table
    whose side column is placed against the stored home follows the same rule; a table with no side column moves as
    is." HOME -> AWAY, a lowercase (nhl-style) 'home' -> 'away', DRAW and NULL untouched; without the flag the rows are
    refused, listed, like any added row."""
    live, frm = pair([_ksm(1, "HOME"), _ksm(2, "DRAW"), _ksm(3, "home"), _ksm(4, None)])
    before = _dump(live)
    assert _main(live, frm, "--apply") == 2
    out = capsys.readouterr().out
    assert "ADDED 36454 kalshi_settled_markets row 1: " in out
    assert "-> REFUSED (no --move-added); SIDE swap (addendum 313 item 1(1)): side 'HOME' -> 'AWAY'" in out
    assert "kalshi_settled_markets: 4 row(s) on 36454 added since the copy (1, 2, 3, 4); --move-added not given" in out
    assert _dump(live) == before
    assert _main(live, frm, "--dry-run", "--move-added") == 0
    out = capsys.readouterr().out
    assert "-> MOVE to the new id (--move-added); SIDE swap (addendum 313 item 1(1)): side 'HOME' -> 'AWAY'" in out
    assert "SIDE swap (addendum 313 item 1(1)): side 'home' -> 'away'" in out
    assert "no ruling swaps it" not in out
    draw = next(x for x in out.splitlines() if x.startswith("ADDED 36454 kalshi_settled_markets row 2: "))
    assert "SIDE swap" not in draw and "ORIENTED" not in draw         # DRAW names no team: moved as it is
    null = next(x for x in out.splitlines() if x.startswith("ADDED 36454 kalshi_settled_markets row 4: "))
    assert "SIDE swap" not in null and "ORIENTED" not in null
    assert _main(live, frm, "--apply", "--move-added") == 0
    out = capsys.readouterr().out
    assert _written(16, 8, 4) in out
    cin = _q(live, "SELECT id FROM matches WHERE home_team_id = ? AND season = '2026'", (CIN,))[0]["id"]
    assert _q(live, "SELECT id, match_id, side, yes_sub_title FROM kalshi_settled_markets ORDER BY id") == [
        {"id": 1, "match_id": cin, "side": "AWAY", "yes_sub_title": "Utah"},
        {"id": 2, "match_id": cin, "side": "DRAW", "yes_sub_title": "Utah"},
        {"id": 3, "match_id": cin, "side": "away", "yes_sub_title": "Utah"},
        {"id": 4, "match_id": cin, "side": None, "yes_sub_title": "Utah"}]
    assert f"AFTER kalshi_settled_markets row 1: match_id {cin}, side 'AWAY'" in out
    assert f"AFTER kalshi_settled_markets row 3: match_id {cin}, side 'away'" in out


def test_an_added_row_non_side_oriented_column_moves_as_is_printed_oriented(pair, capsys):
    """313 item 1(1): "a table with no side column moves as is" — a home/away column that is no side column (a
    home_score-like column of a test table) is moved as it is and printed ORIENTED for the block to read."""
    mk = _set("CREATE TABLE side_free (id INTEGER PRIMARY KEY, match_id INTEGER REFERENCES matches(id), "
              "home_points INTEGER, away_points INTEGER)")
    live, frm = pair([mk, _set("INSERT INTO side_free VALUES (7, 36753, 31, 13)")])
    assert _main(live, frm, "--dry-run", "--move-added") == 0
    out = capsys.readouterr().out
    assert ("ADDED 36753 side_free row 7: id=7, home_points=31, away_points=13 -> MOVE to the new id (--move-added); "
            "ORIENTED, moved as is (no side column swaps it, 313 item 1(1)): home_points=31, away_points=13") in out
    assert "SIDE swap" not in out
    assert _main(live, frm, "--apply", "--move-added") == 0
    lsu = _q(live, "SELECT id FROM matches WHERE home_team_id = ? AND season = '2026'", (LSU,))[0]["id"]
    assert _q(live, "SELECT * FROM side_free") == [{"id": 7, "match_id": lsu, "home_points": 31, "away_points": 13}]


def test_a_live_only_column_holding_a_value_reads_as_changed(pair, capsys):
    """A column the copy lacks (a migration after it) holding a value written since: the row is not the copy's, so it
    is CHANGED and refused, even with --move-added (law 4, as for a matches column the copy lacks); a NULL there
    stays."""
    add = _set("ALTER TABLE game_weather ADD COLUMN note TEXT")
    live, frm = pair([add])
    assert _main(live, frm, "--dry-run") == 0
    assert "PLAN 36454 STAY game_weather: 1 row(s)" in capsys.readouterr().out
    live, frm = pair([add, _set("UPDATE game_weather SET note = '2026 game' WHERE id = 1")])
    before = _dump(live)
    assert _main(live, frm, "--apply", "--move-added") == 2
    out = capsys.readouterr().out
    assert "CHANGED 36454 game_weather row 1: " in out and "note '2026 game' (not in the copy)" in out
    assert "STAY game_weather" not in out and _dump(live) == before


def test_a_quoted_table_name_is_read_and_moved(pair, capsys):
    """Table and column names come from the live file: an embedded double quote is doubled, not an SQL error."""
    mk = _set('CREATE TABLE "x""y" (id INTEGER PRIMARY KEY, "m""id" INTEGER REFERENCES matches(id))')
    live, frm = pair([mk, _set('INSERT INTO "x""y" (id, "m""id") VALUES (5, 36753)')])
    assert _main(live, frm, "--dry-run") == 2
    out = capsys.readouterr().out
    assert 'x"y.m"id' in out and 'ADDED 36753 x"y row 5: ' in out and "REFUSED (no --move-added)" in out
    assert _main(live, frm, "--apply", "--move-added") == 0
    lsu = _q(live, "SELECT id FROM matches WHERE home_team_id = ? AND season = '2026'", (LSU,))[0]["id"]
    assert _q(live, 'SELECT "m""id" AS m FROM "x""y"') == [{"m": lsu}]


def test_a_table_the_copy_lacks_reads_as_added(pair, capsys):
    live, frm = pair(None, [_set("DROP TABLE game_weather")])
    before = _dump(live)
    assert _main(live, frm, "--apply") == 2
    assert "game_weather: 1 row(s) on 36454 added since the copy (1); --move-added not given" in \
        capsys.readouterr().out
    assert _dump(live) == before


def test_a_2025_row_in_a_moved_table_is_refused(pair, capsys):
    live, frm = pair(None, [lambda s: s.add(MatchStats(id=40, match_id=36454, team_id=UTAH, extra_stats={}))])
    before = _dump(live)
    assert _main(live, frm, "--apply", "--move-added", "--book-rows", "swap") == 2
    assert "match_stats: the copy holds 1 row(s) on 36454" in capsys.readouterr().out
    assert _dump(live) == before


def test_a_2025_row_in_a_moved_table_still_prints_every_live_row(pair, capsys):
    """The table is refused, and its live rows are still each printed: the BOOK line (position against #885) and the
    PLAN line (selection before and after), with the copy's row listed."""
    live, frm = pair([_book_rows], [lambda s: s.add(Odds(
        id=60, match_id=36753, bookmaker="Z", market="ML", selection="HOME", price_decimal=1.4,
        captured_at=datetime(2025, 11, 8), source=AF))])
    before = _dump(live)
    for mode in ("refuse", "swap"):
        assert _main(live, frm, "--dry-run", "--book-rows", mode) == 2
        out = capsys.readouterr().out
        assert "COPY 36753 odds row 60: " in out and "odds: the copy holds 1 row(s) on 36753" in out
        assert "BOOK 36753 odds row 22: " in out and "after #885 (the stored orientation -> swap)" in out
        assert "BOOK 36753 odds row 23: " in out
        if mode == "swap":
            assert "PLAN 36753 MOVE odds row 22: match_id 36753 -> the new id, selection AWAY -> HOME" in out
    assert _dump(live) == before


def test_an_availability_row_added_since_the_copy_is_refused_even_with_move_added(pair, capsys):
    live, frm = pair([lambda s: s.add(AvailabilityObservation(
        id=1, sport=Sport.NFL, source="nflverse_depth_charts", endpoint="e", match_id=36753, status="empty",
        fetched_at=datetime(2026, 11, 6), rows_asserted=0))])
    before = _dump(live)
    assert _main(live, frm, "--apply", "--move-added") == 2
    out = capsys.readouterr().out
    assert "COUNT 36753 availability_observations.match_id: 1 row(s)" in out
    assert "ADDED 36753 availability_observations row 1: " in out and "REFUSED (append-only, never moved)" in out
    assert "availability_observations: 1 row(s) on 36753 added since the copy (1); the table is append-only" in out
    assert _dump(live) == before


# ---------------------------------------------------------------------------- the write count, the same file


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


@pytest.mark.parametrize("orphan", [
    _set("INSERT INTO odds_snapshots (id, match_id, market, selection, devig_prob, n_books, captured_at, source) "
         "VALUES (99, 36754, 'ML', 'HOME', 0.9, 0, '2026-01-01 00:00:00', 'kalshi')"),
    lambda s: s.add(AvailabilityObservation(
        id=1, sport=Sport.NFL, source="nflverse_depth_charts", endpoint="e", match_id=36755, status="empty",
        fetched_at=datetime(2026, 11, 6), rows_asserted=0)),
])
def test_a_row_already_on_a_new_rows_id_is_refused(pair, capsys, orphan):
    """matches.id is the rowid: the new rows take max(id) + 1 and + 2 (36754, 36755 here). An orphan already on one
    (a deleted match's) would silently become the 2026 row's: refused, named, dry run and apply."""
    live, frm = pair([orphan])
    before = _dump(live)
    for flag in ("--dry-run", "--apply"):
        assert _main(live, frm, flag) == 2
        out = capsys.readouterr().out
        assert "NEW ID 36754 (expected for 36454): " in out and "NEW ID 36755 (expected for 36753): " in out
        assert "is already referenced: " in out and "would become the 2026 row's unplanned" in out
        assert "CREATED" not in out
    assert _dump(live) == before


def test_the_dry_run_names_the_new_ids_free(pair, capsys):
    live, frm = pair()
    assert _main(live, frm, "--dry-run") == 0
    out = capsys.readouterr().out
    assert "NEW ID 36754 (expected for 36454): no row references it" in out
    assert "NEW ID 36755 (expected for 36753): no row references it" in out


def test_the_apply_open_never_creates_a_file(tmp_path, monkeypatch):
    """--apply opens the live file mode=rw: a path gone after the is_file check is an error, never an empty DB."""
    p = tmp_path / "gone.db"
    monkeypatch.setattr(rc.Path, "is_file", lambda self: True)
    with pytest.raises(sqlite3.OperationalError):
        rc.open_live(p, True)
    assert not p.exists()


def test_the_same_file_is_refused(pair, capsys):
    live, frm = pair()
    before = _dump(live)
    assert _main(live, live, "--apply") == 2
    assert "--db and --from are the same file" in capsys.readouterr().out
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
    # 36454 / 36753: their copy's content, every column (no provider_orientation in the copy: its text verbatim)
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
    assert _written(12, 8, 0) in out
    # a second apply refuses and writes nothing: the live file holds the 2025 rows now
    after = _dump(live)
    assert _main(live, frm, "--apply") == 2
    out = capsys.readouterr().out
    assert "the live file already holds a 2025 row (36454): already restored, or never collided" in out
    assert _dump(live) == after


@pytest.mark.parametrize("journal", ["delete", "wal"])
@pytest.mark.parametrize("where", ["after_create", "after_moves", "before_commit"])
def test_the_apply_is_one_transaction(pair, where, journal):
    live, frm = pair([_added_weather])
    if journal == "wal":
        _wal(live)
    before = _dump(live)
    with pytest.raises(RuntimeError, match="injected failure"):
        rc.run(live, frm, None, True, move_added=True, out=lambda *_: None, _fail_at=where)
    assert _dump(live) == before


# ---------------------------------------------------------------------------- --emit-json / --from-json


_WANT_EXTRACT = {"rows": [
    {"provider_id": "18216", "season": "2025", "kickoff": "2025-11-02T02:15:00", "status": "FINISHED",
     "home": "Utah", "away": "Cincinnati", "home_score": 45, "away_score": 14},
    {"provider_id": "18240", "season": "2025", "kickoff": "2025-11-09T00:30:00", "status": "FINISHED",
     "home": "Alabama", "away": "LSU", "home_score": 20, "away_score": 9}]}


def _emit(pair, tmp_path, capsys) -> Path:
    live, frm = pair()
    raw, fraw = live.read_bytes(), frm.read_bytes()
    out_dir = tmp_path / "receipts"
    out_dir.mkdir()
    p = out_dir / "restore_2025_rows.json"
    assert _main(live, frm, "--dry-run", "--emit-json", str(p)) == 0
    out = capsys.readouterr().out
    data = p.read_bytes()
    assert f"EMITTED {p} · 2 row(s) · sha256 {hashlib.sha256(data).hexdigest()}" in out
    assert "DRY RUN: nothing written" in out
    assert live.read_bytes() == raw and frm.read_bytes() == fraw              # the database files: unchanged
    return p


def test_emit_json_writes_the_two_2025_rows_fields_and_nothing_else(pair, tmp_path, capsys):
    p = _emit(pair, tmp_path, capsys)
    assert json.loads(p.read_text()) == _WANT_EXTRACT                         # no row ids, no team ids
    assert "36454" not in p.read_text() and "36753" not in p.read_text()


def test_emit_json_is_refused_without_dry_run_without_from_or_onto_an_existing_path(pair, tmp_path, capsys):
    live, frm = pair()
    before = _dump(live)
    p = tmp_path / "x.json"
    assert _main(live, frm, "--apply", "--emit-json", str(p)) == 2
    assert "--emit-json only with --dry-run and --from" in capsys.readouterr().out
    assert not p.exists() and _dump(live) == before
    src = tmp_path / "src.json"
    src.write_text(json.dumps(_WANT_EXTRACT))
    assert _main_json(live, src, "--dry-run", "--emit-json", str(p)) == 2
    assert "--emit-json only with --dry-run and --from" in capsys.readouterr().out
    assert not p.exists()
    p.write_text("already here")
    assert _main(live, frm, "--dry-run", "--emit-json", str(p)) == 2
    assert f"--emit-json {p} exists" in capsys.readouterr().out
    assert p.read_text() == "already here" and _dump(live) == before


def test_emit_json_onto_a_path_it_cannot_create_is_refused_not_a_traceback(pair, tmp_path, capsys, monkeypatch):
    live, frm = pair()
    before = _dump(live)
    p = tmp_path / "nodir" / "x.json"
    assert _main(live, frm, "--dry-run", "--emit-json", str(p)) == 2
    assert f"its directory {p.parent} does not exist" in capsys.readouterr().out
    assert not p.parent.exists()
    q = tmp_path / "x.json"
    real = os.open

    def deny(path, *a, **k):
        if str(path) == str(q):
            raise PermissionError(13, "Permission denied")
        return real(path, *a, **k)
    monkeypatch.setattr(rc.os, "open", deny)
    assert _main(live, frm, "--dry-run", "--emit-json", str(q)) == 2
    out = capsys.readouterr().out
    assert f"--emit-json {q}: not created (PermissionError" in out and "EMITTED" not in out
    assert not q.exists() and _dump(live) == before


def test_emit_json_is_not_written_when_the_dry_run_refuses(pair, tmp_path, capsys):
    live, frm = pair([_book_rows])
    p = tmp_path / "x.json"
    assert _main(live, frm, "--dry-run", "--emit-json", str(p)) == 2
    assert not p.exists() and "EMITTED" not in capsys.readouterr().out


def test_from_json_round_trip_onto_a_host_like_file(pair, tmp_path, capsys):
    """The laptop's dry run writes the extract; the host (other row ids, other team ids, int provider ids, no copy)
    restores from it: the restored row reads the 2025 state on its own team ids, the columns the extract does not
    carry are NULL and printed, the moves as on the laptop; with no copy, the other tables' rows read as added."""
    p = _emit(pair, tmp_path, capsys)
    host_dir = tmp_path / "host"
    host_dir.mkdir()
    hl = _build(host_dir / "live.db", "2026", None, HOST)
    T = HOST["teams"]
    live_rows = {r["id"]: r for r in _q(hl, "SELECT * FROM matches WHERE id IN (41001, 41377)")}
    raw = hl.read_bytes()
    # the 2025 game's weather row is on the id in the host file; with no copy it cannot be told from a 2026 row
    assert _main_json(hl, p, "--dry-run") == 2
    out = capsys.readouterr().out
    assert "ADDED 41001 game_weather row 1: " in out and "REFUSED (no --move-added)" in out
    assert hl.read_bytes() == raw
    assert _main_json(hl, p, "--dry-run", "--move-added") == 0
    out = capsys.readouterr().out
    assert hl.read_bytes() == raw
    assert "--from-json " + str(p) in out.splitlines()[0]
    assert "BEFORE 41001 extract: " in out
    assert "PLAN 41001 -> the extract's 2025 state (--from-json): season 2025 · 2025-11-02 02:15:00.000000 · " \
           "FINISHED · Utah 45 v Cincinnati 14 · ftr HOME" in out
    assert "NULLED (not in the extract) 41001.status_raw: live value 'FT' -> NULL" in out
    assert "NULLED (not in the extract) 41001.home_score_ht: live value 24 -> NULL" in out
    assert "NULLED (not in the extract) 41377.venue: live value None -> NULL" in out
    assert "PLAN 41001 MOVE odds_snapshots row 11: match_id 41001 -> the new id, selection HOME -> AWAY" in out
    assert _main_json(hl, p, "--apply", "--move-added") == 0
    out = capsys.readouterr().out
    assert "COMMITTED" in out and _written(13, 8, 1) in out
    for mid, pid, (h, a), (hs, as_), ko in ((41001, 18216, ("Utah", "Cincinnati"), (45, 14), "2025-11-02 02:15:00"),
                                            (41377, 18240, ("Alabama", "LSU"), (20, 9), "2025-11-09 00:30:00")):
        r = _q(hl, "SELECT * FROM matches WHERE id = ?", (mid,))[0]
        lr = live_rows[mid]
        assert (r["season"], r["utc_date"], r["status"]) == ("2025", ko + ".000000", "FINISHED")
        assert (r["home_team_id"], r["away_team_id"]) == (T[h], T[a]) == (lr["home_team_id"], lr["away_team_id"])
        assert (r["home_score"], r["away_score"], r["full_time_result"]) == (hs, as_, "HOME")
        assert json.loads(r["external_ids"]) == {AF: pid}                     # provider id kept, orientation removed
        assert all(r[c] is None for c in rc.NULLED)
        assert (r["sport"], r["competition_id"]) == (lr["sport"], lr["competition_id"])
    new = {r["home_team_id"]: r for r in _q(hl, "SELECT * FROM matches WHERE id NOT IN (41001, 41377, 500)")}
    assert set(new) == {T["Cincinnati"], T["LSU"]}
    assert (new[T["Cincinnati"]]["home_score"], new[T["Cincinnati"]]["away_score"], new[T["Cincinnati"]]["season"]) \
        == (25, 49, "2026")
    assert _q(hl, "SELECT match_id, selection FROM odds_snapshots WHERE id = 11") == \
        [{"match_id": new[T["Cincinnati"]]["id"], "selection": "AWAY"}]
    assert _q(hl, "SELECT match_id FROM game_weather WHERE id = 1") == [{"match_id": new[T["Cincinnati"]]["id"]}]
    # a second run refuses: the host file holds the 2025 rows now
    after = _dump(hl)
    assert _main_json(hl, p, "--apply", "--move-added") == 2
    assert "already holds a 2025 row (41001)" in capsys.readouterr().out
    assert _dump(hl) == after


def _extract(tmp_path, doc) -> Path:
    p = tmp_path / "extract.json"
    p.write_text(json.dumps(doc))
    return p


@pytest.mark.parametrize("doc,why", [
    ({"rows": [{**_WANT_EXTRACT["rows"][0], "home_score": 44}, _WANT_EXTRACT["rows"][1]]},
     "extract 18216: score 44-14, not 45-14"),
    ({"rows": [_WANT_EXTRACT["rows"][0]]}, "extract: provider id(s) ['18240'] missing"),
    ({"rows": [_WANT_EXTRACT["rows"][0], _WANT_EXTRACT["rows"][0], _WANT_EXTRACT["rows"][1]]},
     "extract: provider id 18216 more than once"),
    ({"rows": [{**_WANT_EXTRACT["rows"][0], "kickoff": "2025-11-02T02:16:00"}, _WANT_EXTRACT["rows"][1]]},
     "extract 18216: kickoff '2025-11-02T02:16:00'"),
    ({"rows": [{**_WANT_EXTRACT["rows"][0], "kickoff": "2025-11-02T02:15:00+00:00"}, _WANT_EXTRACT["rows"][1]]},
     "extract 18216: kickoff '2025-11-02T02:15:00+00:00'"),
    ({"rows": [{**_WANT_EXTRACT["rows"][0], "kickoff": "2025-11-02T02:15:00-05:00"}, _WANT_EXTRACT["rows"][1]]},
     "extract 18216: kickoff '2025-11-02T02:15:00-05:00'"),
    ({"rows": [_WANT_EXTRACT["rows"][0], {**_WANT_EXTRACT["rows"][1], "kickoff": "2025-11-09T00:30:00Z"}]},
     "extract 18240: kickoff '2025-11-09T00:30:00Z'"),
    ({"rows": [{**_WANT_EXTRACT["rows"][0], "home": "Cincinnati", "away": "Utah"}, _WANT_EXTRACT["rows"][1]]},
     "extract 18216: teams 'Cincinnati' v 'Utah'"),
    ({"rows": [{**_WANT_EXTRACT["rows"][0], "season": "2026"}, _WANT_EXTRACT["rows"][1]]},
     "extract 18216: season '2026'"),
    ({"rows": [{**_WANT_EXTRACT["rows"][0], "id": 36454}, _WANT_EXTRACT["rows"][1]]}, "extract row 0: fields"),
    ({"rows": [{**_WANT_EXTRACT["rows"][0], "provider_id": 18216}, _WANT_EXTRACT["rows"][1]]},
     "extract row 0: provider id 18216 is not a pinned provider id"),
    ([_WANT_EXTRACT["rows"]], 'not {"rows": [...]}'),
])
def test_from_json_with_a_wrong_or_missing_row_is_refused(pair, tmp_path, capsys, doc, why):
    live, _frm = pair(layout=HOST)
    before = _dump(live)
    p = _extract(tmp_path, doc)
    assert _main_json(live, p, "--apply", "--move-added") == 2
    out = capsys.readouterr().out
    assert why in out and "REFUSED" in out
    assert _dump(live) == before


def test_from_json_refuses_any_availability_row_on_the_id(pair, tmp_path, capsys):
    live, _frm = pair([lambda s: s.add(AvailabilityObservation(
        id=1, sport=Sport.NFL, source="nflverse_depth_charts", endpoint="e", match_id=41377, status="empty",
        fetched_at=datetime(2025, 11, 8), rows_asserted=0))], layout=HOST)
    before = _dump(live)
    assert _main_json(live, _extract(tmp_path, _WANT_EXTRACT), "--apply", "--move-added") == 2
    out = capsys.readouterr().out
    assert "UNKEYED 41377 availability_observations row 1: " in out
    assert "availability_observations: 1 row(s) on 41377; with --from-json no copy shows they are the 2025 game's" in out
    assert _dump(live) == before


def test_from_json_refuses_a_live_column_it_does_not_know(pair, tmp_path, capsys):
    live, _frm = pair([_set("ALTER TABLE matches ADD COLUMN series_description VARCHAR(64)"),
                       _set("UPDATE matches SET series_description = 'x' WHERE id = 41001")], layout=HOST)
    before = _dump(live)
    assert _main_json(live, _extract(tmp_path, _WANT_EXTRACT), "--apply", "--move-added") == 2
    assert "live row 41001: column series_description holds 'x'" in capsys.readouterr().out
    assert _dump(live) == before


# ---------------------------------------------------------------------------- ncaa_cfbd_labels / _pregame (314 item 2)

# ARCHITECT 2026-11-09 16:25 ET, addendum 314 item 1: the copy (10-09) holds the 2025 game's CFBD label (401756942 /
# 401752759, season 2025, orientation 'same', 45-14 / 20-9); the live file the 2026 game's written on 11-08
# (401856848 / 401856740, season 2026, orientation 'swapped', 49-25 / 31-13 in our orientation, "score-reversed: ...",
# season_type regular, week 9 / 10), CFBD's home Cincinnati and LSU.
_REVERSED = "score-reversed: provider home/away scores swapped vs CFBD (provider 49-25, CFBD 25-49)"
_LABEL_2025 = {0: dict(source_game_id=401756942, season="2025", orientation="same", neutral=False, home_score=45,
                       away_score=14, source_home_team="Utah", source_away_team="Cincinnati", week=10),
               1: dict(source_game_id=401752759, season="2025", orientation="same", neutral=False, home_score=20,
                       away_score=9, source_home_team="Alabama", source_away_team="LSU", week=11)}
_LABEL_2026 = {0: dict(source_game_id=401856848, season="2026", orientation="swapped", neutral=False, home_score=49,
                       away_score=25, source_home_team="Cincinnati", source_away_team="Utah", week=9,
                       correction_reason=_REVERSED),
               1: dict(source_game_id=401856740, season="2026", orientation="swapped", neutral=False, home_score=31,
                       away_score=13, source_home_team="LSU", source_away_team="Alabama", week=10,
                       correction_reason=_REVERSED.replace("49-25", "31-13").replace("25-49", "13-31"))}
_STAMP_2025 = dict(fetched_at=datetime(2025, 11, 10, 6), updated_at=datetime(2025, 11, 10, 6, 0, 1))
_STAMP_2026 = dict(fetched_at=datetime(2026, 11, 8, 6), updated_at=datetime(2026, 11, 8, 6, 0, 1))


def _labels(which, layout=LAPTOP, only=(0, 1), **over):
    def fn(s):
        for i in only:
            fields = {**(_LABEL_2025 if which == "2025" else _LABEL_2026)[i], **over}
            s.add(NCAACFBDLabel(match_id=layout["rows"][i], source="cfbd", join_via="exact", season_type="regular",
                                payload_file=f"exports/cfbd_{which}.json",
                                **(_STAMP_2025 if which == "2025" else _STAMP_2026), **fields))
    return fn


def _pregame(which, layout=LAPTOP, i=0):
    f = (dict(source_game_id=401756942, season="2025", orientation="same", source_home_team="Utah",
              source_away_team="Cincinnati", source_start=datetime(2025, 11, 2, 2, 15)) if which == "2025" else
         dict(source_game_id=401856848, season="2026", orientation="swapped", source_home_team="Cincinnati",
              source_away_team="Utah", source_start=datetime(2026, 10, 31, 19, 45)))
    return lambda s: s.add(NCAACFBDPregame(match_id=layout["rows"][i], source="cfbd", neutral=False, join_via="exact",
                                           payload_file=f"exports/cfbd_pregame_{which}.json",
                                           **(_STAMP_2025 if which == "2025" else _STAMP_2026), **f))


def _bump_max(s):
    """The laptop's max(matches.id) of addendum 314 item 1: the new rows take 58453 and 58454."""
    s.add(Match(id=58452, sport=Sport.NFL, competition_id=7, season="2026", utc_date=datetime(2026, 11, 8),
                status=MatchStatus.SCHEDULED, home_team_id=LAPTOP["teams"]["Other"], away_team_id=CIN,
                external_ids={AF: "998"}))


_TS = r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{6}"


@pytest.mark.parametrize("copy_has_week", [True, False])
@pytest.mark.parametrize("layout", [LAPTOP, HOST], ids=["laptop", "host"])
def test_label_rows_move_reorient_and_the_copys_rows_are_restored(pair, capsys, layout, copy_has_week):
    """314 item 2(a)/(b)/(e): the 2026 label MOVES to the new row re-expressed (orientation same, scores 25-49 /
    13-31, correction_reason NULL, updated_at the apply's time, every other column as it is); the copy's 2025 label is
    RESTORED onto the old id byte-identical (SELECT * compared), a live-only column (week, a later migration) NULL."""
    import re
    a, b, _ = layout["rows"]
    from_extra = [_labels("2025", layout)] + ([] if copy_has_week else [
        _set("ALTER TABLE ncaa_cfbd_labels DROP COLUMN week")])
    live_extra = [_labels("2026", layout)] + ([_bump_max] if layout is LAPTOP else [])
    live, frm = pair(live_extra, from_extra, layout)
    T = layout["teams"]
    nid_a, nid_b = (58453, 58454) if layout is LAPTOP else (b + 1, b + 2)
    copy_rows = {r["match_id"]: r for r in _q(frm, "SELECT * FROM ncaa_cfbd_labels")}
    live_rows = {r["match_id"]: r for r in _q(live, "SELECT * FROM ncaa_cfbd_labels")}
    raw = live.read_bytes()
    assert _main(live, frm, "--dry-run") == 0
    out = capsys.readouterr().out
    assert live.read_bytes() == raw
    assert (f"MOVE+REORIENT ncaa_cfbd_labels {a} → {nid_a}: orientation swapped→same, scores 49-25→25-49, "
            f"correction_reason cleared; RESTORE ncaa_cfbd_labels {a} ← the copy's 2025 row") in out
    assert (f"MOVE+REORIENT ncaa_cfbd_labels {b} → {nid_b}: orientation swapped→same, scores 31-13→13-31, "
            f"correction_reason cleared; RESTORE ncaa_cfbd_labels {b} ← the copy's 2025 row") in out
    assert "(the moved row: updated_at the apply's time, every other column as it is)" in out
    assert f"CHANGED {a} ncaa_cfbd_labels row {a}: " in out and "-> MOVE+REORIENT to the new id and RESTORE" in out
    assert f"PLAN {a} MOVE+REORIENT ncaa_cfbd_labels: 1 row to the new id, the copy's row RESTORED onto {a}" in out
    assert (f"RESTORE ncaa_cfbd_labels {a}.week: NULL (not in the copy)" in out) is (not copy_has_week)
    assert "DRY RUN: nothing written" in out and "REFUSED" not in out
    assert _main(live, frm, "--apply") == 0
    out = capsys.readouterr().out
    assert "COMMITTED" in out and _written(16, 8, 0, 2, 2) in out
    new = {r["home_team_id"]: r["id"] for r in _q(live, "SELECT id, home_team_id FROM matches WHERE season = '2026' "
                                                        "AND status = 'FINISHED'")}
    assert (new[T["Cincinnati"]], new[T["LSU"]]) == (nid_a, nid_b)
    assert (f"WRITTEN MOVE+REORIENT ncaa_cfbd_labels {a} → {nid_a}: orientation swapped→same, scores 49-25→25-49, "
            f"correction_reason cleared; RESTORE ncaa_cfbd_labels {a} ← the copy's 2025 row") in out
    assert f"AFTER ncaa_cfbd_labels {nid_a} (moved+reoriented): match_id={nid_a}, " in out
    assert f"AFTER ncaa_cfbd_labels {a} (restored): match_id={a}, " in out
    for old, nid, scores in ((a, nid_a, (25, 49)), (b, nid_b, (13, 31))):
        moved = _q(live, "SELECT * FROM ncaa_cfbd_labels WHERE match_id = ?", (nid,))
        was = live_rows[old]
        assert len(moved) == 1
        m = moved[0]
        assert (m["orientation"], m["home_score"], m["away_score"], m["correction_reason"]) == ("same", *scores, None)
        assert (m["home_score"], m["away_score"]) == tuple(
            _q(live, "SELECT home_score, away_score FROM matches WHERE id = ?", (nid,))[0].values())
        assert m["updated_at"] != was["updated_at"] and re.fullmatch(_TS, m["updated_at"])
        for c in was:
            if c not in ("match_id", "orientation", "home_score", "away_score", "correction_reason", "updated_at"):
                assert m[c] == was[c], c                                    # every other column as it is
        restored = _q(live, "SELECT * FROM ncaa_cfbd_labels WHERE match_id = ?", (old,))
        want = {**copy_rows[old], **({} if copy_has_week else {"week": None})}
        assert restored == [want]                                           # the copy's row, byte for byte
        assert list(restored[0]) == list(_q(live, "SELECT * FROM ncaa_cfbd_labels LIMIT 1")[0])
    # typed as the copy (text stays text, integers stay integers)
    con = sqlite3.connect(live)
    fcon = sqlite3.connect(frm)
    try:
        cols = [r[1] for r in fcon.execute("PRAGMA table_info(ncaa_cfbd_labels)")]
        q = ", ".join(f"typeof({c}), quote({c})" for c in cols)
        assert con.execute(f"SELECT {q} FROM ncaa_cfbd_labels WHERE match_id = ?", (a,)).fetchall() == \
            fcon.execute(f"SELECT {q} FROM ncaa_cfbd_labels WHERE match_id = ?", (a,)).fetchall()
    finally:
        con.close()
        fcon.close()


def test_a_pregame_row_moves_flipped_and_the_copys_pregame_row_is_restored(pair, capsys):
    """314 item 2(c): "a pregame row's orientation is the same relation; the same move and re-expression (there is no
    score to swap; orientation 'same')"."""
    live, frm = pair([_pregame("2026"), _bump_max], [_pregame("2025")])
    copy_row = _q(frm, "SELECT * FROM ncaa_cfbd_pregame")[0]
    was = _q(live, "SELECT * FROM ncaa_cfbd_pregame")[0]
    assert _main(live, frm, "--dry-run") == 0
    out = capsys.readouterr().out
    assert ("MOVE+REORIENT ncaa_cfbd_pregame 36454 → 58453: orientation swapped→same; RESTORE ncaa_cfbd_pregame "
            "36454 ← the copy's 2025 row") in out
    assert "scores" not in next(x for x in out.splitlines() if x.startswith("MOVE+REORIENT ncaa_cfbd_pregame"))
    assert _main(live, frm, "--apply") == 0
    out = capsys.readouterr().out
    assert _written(14, 8, 0, 1, 1) in out
    rows = {r["match_id"]: r for r in _q(live, "SELECT * FROM ncaa_cfbd_pregame")}
    assert set(rows) == {36454, 58453}
    assert rows[36454] == copy_row
    m = rows[58453]
    assert m["orientation"] == "same" and m["updated_at"] != was["updated_at"]
    assert {k: v for k, v in m.items() if k not in ("match_id", "orientation", "updated_at")} == \
        {k: v for k, v in was.items() if k not in ("match_id", "orientation", "updated_at")}


def test_a_changed_row_of_another_table_still_refuses_beside_the_label_handler(pair, capsys):
    """314 item 2(d): "The script's CHANGED check stays as it is for every other table — a changed row elsewhere is
    still a refusal; only these two tables get the handler"."""
    live, frm = pair([_labels("2026"), _set("UPDATE game_weather SET venue = 'Elsewhere' WHERE id = 1")],
                     [_labels("2025")])
    before = _dump(live)
    for flags in (("--dry-run",), ("--apply", "--move-added")):
        assert _main(live, frm, *flags) == 2
        out = capsys.readouterr().out
        assert "MOVE+REORIENT ncaa_cfbd_labels 36454 → 36754: orientation swapped→same" in out
        assert "CHANGED 36454 game_weather row 1: " in out and "-> REFUSED (same key as the copy's row" in out
        assert "game_weather: 1 row(s) on 36454 changed since the copy (1)" in out
        assert "REFUSED: row 36454: ncaa_cfbd_labels" not in out
    assert _dump(live) == before


@pytest.mark.parametrize("over,why", [
    ({"home_score": 49, "away_score": 24},
     "ncaa_cfbd_labels 36454: the swapped scores 24-49 are not the new row's 25-49: correction_reason is cleared only "
     "when they agree (addendum 314 item 2(a)) — not guessed"),
    ({"orientation": "unknown"},
     "ncaa_cfbd_labels 36454: orientation 'unknown' is neither 'same' nor 'swapped' — not re-expressed, not guessed"),
])
def test_a_label_the_rule_cannot_re_express_is_refused(pair, capsys, over, why):
    live, frm = pair([_labels("2026", only=(0,), **over)], [_labels("2025", only=(0,))])
    before = _dump(live)
    for flag in ("--dry-run", "--apply"):
        assert _main(live, frm, flag) == 2
        out = capsys.readouterr().out
        assert f"REFUSED: row 36454: {why}" in out and "-> REFUSED" in out
    assert _dump(live) == before


_NOT_2026 = ("ncaa_cfbd_pregame {mid}: season '2025' is not the new row's '2026': not shown to be the new row's "
             "game's (addendum 314 item 2(a): \"The live row (the 2026 label) MOVES\") — not moved, not guessed")


def test_a_2025_pregame_row_re_fetched_is_refused_not_moved(pair, capsys):
    """314 item 2(a) moves "The live row (the 2026 label)": a 2025 pregame row that only re-fetched (fetched_at differs,
    so it reads CHANGED) is the 2025 game's, and the pregame has no score check to catch it — REFUSED by its season and
    by its source_game_id (the copy's row's), never moved onto the 2026 row."""
    live, frm = pair([_pregame("2025"), _bump_max,
                      _set("UPDATE ncaa_cfbd_pregame SET fetched_at = '2025-11-20 06:00:00.000000'")],
                     [_pregame("2025")])
    before = _dump(live)
    for flags in (("--dry-run",), ("--apply",), ("--apply", "--move-added")):
        assert _main(live, frm, *flags) == 2
        out = capsys.readouterr().out
        assert f"REFUSED: row 36454: {_NOT_2026.format(mid=36454)}" in out
        assert ("REFUSED: row 36454: ncaa_cfbd_pregame 36454: source_game_id 401756942 is the copy's row's (the 2025 "
                "game's): not the new row's game's — not moved, not guessed") in out
        assert "MOVE+REORIENT ncaa_cfbd_pregame 36454 → 58453: orientation same→swapped" in out and "-> REFUSED" in out
    assert _dump(live) == before


def test_a_2026_season_label_with_the_copys_cfbd_game_is_refused(pair, capsys):
    """The CHANGED row's source_game_id is the copy's row's: the same CFBD game as the 2025 label, whatever its season
    reads — REFUSED, named."""
    live, frm = pair([_labels("2026", only=(0,), source_game_id=401756942)], [_labels("2025", only=(0,))])
    before = _dump(live)
    assert _main(live, frm, "--apply") == 2
    out = capsys.readouterr().out
    assert ("REFUSED: row 36454: ncaa_cfbd_labels 36454: source_game_id 401756942 is the copy's row's (the 2025 "
            "game's): not the new row's game's — not moved, not guessed") in out
    assert "season '2026' is not the new row's" not in out
    assert _dump(live) == before


def test_a_2025_pregame_row_read_as_added_is_refused_under_from_json(pair, tmp_path, capsys):
    """--from-json: every row reads ADDED; a 2025 pregame row still is not the 2026 game's — REFUSED by its season even
    under --move-added (the host layout, other row ids)."""
    p = _emit(pair, tmp_path, capsys)
    host_dir = tmp_path / "host"
    host_dir.mkdir()
    hl = _build(host_dir / "live.db", "2026", [_pregame("2025", HOST)], HOST)
    raw = hl.read_bytes()
    for flags in (("--dry-run", "--move-added"), ("--apply", "--move-added")):
        assert _main_json(hl, p, *flags) == 2
        out = capsys.readouterr().out
        assert f"REFUSED: row 41001: {_NOT_2026.format(mid=41001)}" in out
    assert hl.read_bytes() == raw


def test_a_copy_column_the_live_label_table_lacks_is_refused(pair, capsys):
    live, frm = pair([_labels("2026", only=(0,))],
                     [_labels("2025", only=(0,)), _set("ALTER TABLE ncaa_cfbd_labels ADD COLUMN gone TEXT")])
    before = _dump(live)
    assert _main(live, frm, "--apply") == 2
    assert ("REFUSED: row 36454: ncaa_cfbd_labels 36454: the copy's column gone is not in the live table — not "
            "restored, not guessed") in capsys.readouterr().out
    assert _dump(live) == before


def test_an_added_label_row_moves_reoriented_only_under_move_added(pair, capsys):
    """314 item 2 for a label the copy does not hold on the id: MOVE+REORIENT under --move-added, nothing restored;
    without the flag REFUSED, listed."""
    live, frm = pair([_labels("2026", only=(1,))])
    before = _dump(live)
    assert _main(live, frm, "--apply") == 2
    out = capsys.readouterr().out
    assert ("ADDED 36753 ncaa_cfbd_labels row 36753: " in out and "-> REFUSED (no --move-added); planned: "
            "MOVE+REORIENT ncaa_cfbd_labels 36753 → 36755: orientation swapped→same, scores 31-13→13-31, "
            "correction_reason cleared; no 2025 row restored (the copy holds none on 36753)") in out
    assert "ncaa_cfbd_labels: 1 row(s) on 36753 added since the copy (36753); --move-added not given" in out
    assert _dump(live) == before
    assert _main(live, frm, "--dry-run", "--move-added") == 0
    out = capsys.readouterr().out
    assert ("MOVE+REORIENT ncaa_cfbd_labels 36753 → 36755: orientation swapped→same, scores 31-13→13-31, "
            "correction_reason cleared; no 2025 row restored (the copy holds none on 36753)") in out
    assert "PLAN 36753 MOVE+REORIENT ncaa_cfbd_labels: 1 row to the new id, nothing restored" in out
    assert _main(live, frm, "--apply", "--move-added") == 0
    out = capsys.readouterr().out
    assert _written(13, 8, 0, 1, 0) in out
    assert "AFTER ncaa_cfbd_labels 36753 (nothing restored): no row" in out
    got = _q(live, "SELECT match_id, orientation, home_score, away_score, correction_reason FROM ncaa_cfbd_labels")
    assert got == [{"match_id": 36755, "orientation": "same", "home_score": 13, "away_score": 31,
                    "correction_reason": None}]


def test_a_lost_label_row_is_refused_and_an_identical_one_stays(pair, capsys):
    live, frm = pair(None, [_labels("2025", only=(0,))])
    before = _dump(live)
    assert _main(live, frm, "--apply") == 2
    out = capsys.readouterr().out
    assert "LOST 36454 ncaa_cfbd_labels row 36454: " in out and "ncaa_cfbd_labels: 0 row(s) on 36454 changed" in out
    assert _dump(live) == before
    live, frm = pair([_labels("2025", only=(0,))], [_labels("2025", only=(0,))])
    assert _main(live, frm, "--apply") == 0
    out = capsys.readouterr().out
    assert "PLAN 36454 STAY ncaa_cfbd_labels: 1 row(s)" in out and _written(12, 8, 0) in out
    assert [r["match_id"] for r in _q(live, "SELECT match_id FROM ncaa_cfbd_labels")] == [36454]


def test_from_json_with_a_live_label_row(pair, tmp_path, capsys):
    """--from-json (no copy): the live label reads as ADDED -> MOVE+REORIENT under --move-added; the print says no
    2025 row is restored (no copy)."""
    p = _emit(pair, tmp_path, capsys)
    host_dir = tmp_path / "host"
    host_dir.mkdir()
    hl = _build(host_dir / "live.db", "2026", [_labels("2026", HOST)], HOST)
    raw = hl.read_bytes()
    assert _main_json(hl, p, "--dry-run") == 2
    out = capsys.readouterr().out
    assert "ADDED 41001 ncaa_cfbd_labels row 41001: " in out and "-> REFUSED (no --move-added); planned: " in out
    assert hl.read_bytes() == raw
    assert _main_json(hl, p, "--dry-run", "--move-added") == 0
    out = capsys.readouterr().out
    assert ("MOVE+REORIENT ncaa_cfbd_labels 41001 → 41378: orientation swapped→same, scores 49-25→25-49, "
            "correction_reason cleared; no 2025 row restored (--from-json: no copy)") in out
    assert hl.read_bytes() == raw
    assert _main_json(hl, p, "--apply", "--move-added") == 0
    out = capsys.readouterr().out
    assert _written(15, 8, 1, 2, 0) in out
    got = _q(hl, "SELECT match_id, orientation, home_score, away_score, correction_reason FROM ncaa_cfbd_labels "
                 "ORDER BY match_id")
    assert got == [{"match_id": 41378, "orientation": "same", "home_score": 25, "away_score": 49,
                    "correction_reason": None},
                   {"match_id": 41379, "orientation": "same", "home_score": 13, "away_score": 31,
                    "correction_reason": None}]


@pytest.mark.parametrize("where", ["after_moves", "before_commit"])
def test_the_label_move_and_restore_are_in_the_one_transaction(pair, where):
    live, frm = pair([_labels("2026"), _pregame("2026")], [_labels("2025"), _pregame("2025")])
    before = _dump(live)
    with pytest.raises(RuntimeError, match="injected failure"):
        rc.run(live, frm, None, True, out=lambda *_: None, _fail_at=where)
    assert _dump(live) == before
