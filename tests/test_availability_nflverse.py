"""THE NFLVERSE DEPTH-CHART FEED (ARCHITECT 2026-11-04 13:05 ET, addendum 252 item 3(a); 259 item 2; 258 item 2(1)):
the adapter, the snapshot closure and its partial guard, the conditional GET, the cadence constant, #835 item 1, the
command, and the chain and timer, on a throwaway SQLite file (fresh_db below) with a fake HTTP layer: NO NETWORK.

EVERY ROW IN THIS FILE IS SYNTHETIC. Team abbreviations, player names ("Synthetic QB A"), ids ("00-SYN0001") and
stamps are made up for the tests and do not describe any real depth chart. The real-rows excerpt of addendum 259 item 3
(nflverse_depth_charts_2026_excerpt.csv, 1,236 real rows, attributed "nflverse (CC BY 4.0)") is not in this container;
its tests (252 item 6(d) and (g) on real rows, 259 item 2(b) on CAR's 2-row group, BAL's QB1 flip) are listed in the
PR body and land with the fixture.

Item 6, the parts this feed carries, verbatim in part: "(a) append-only — the ingest commands expose no update or
delete path, and a test asserts the tables' row counts only grow across a replay of saved payloads; [...] (d) the
nflverse adapter on a saved 2025-format file: every column read by name (law 1), the 2023–2024 shape refused with its
reason; [...] (h) nothing under data/ after any test."
"""
from __future__ import annotations

import csv
import hashlib
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner
from sqlalchemy import text

import migrate_availability_record as mig
from src.availability import nflverse as nv
from src.availability import record as rec

REPO = Path(__file__).resolve().parents[1]
REPO_DATA_EXISTED = (REPO / "data").exists()

pytestmark = pytest.mark.usefixtures("fresh_db")


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """A throwaway DB (tests/test_availability_record.py's fixture), migrated; the payload directory under tmp_path;
    cwd = tmp_path. Item 6(h): after the test, no data/ under tmp_path, and the repo's data/ exactly as it was."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db
    path = tmp_path / "fresh.db"
    eng = create_engine(f"sqlite:///{path}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                         expire_on_commit=False))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(nv, "PAYLOAD_BASE", tmp_path)
    db.init_db()
    assert mig.main() == 0
    yield path
    eng.dispose()
    assert not list(tmp_path.rglob("data")), "item 6(h): nothing under data/"
    assert (REPO / "data").exists() == REPO_DATA_EXISTED, "item 6(h): the repo's data/ untouched"


def _engine():
    import src.db.database as db
    return db._engine


def _counts() -> tuple[int, int]:
    with _engine().connect() as c:
        return tuple(c.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar() for t in rec.TABLES)


def _ro():
    from src.db.database import readonly_scope
    return readonly_scope()


def _teams(*tlas, extra=()):
    """SYNTHETIC NFL teams: the NFL competition and one team per tla (the api-american-football code sync-teams stores
    as teams.tla); `extra` adds (name, tla) pairs, e.g. a second team holding one tla (ambiguous)."""
    from src.db.database import session_scope
    from src.db.schema import Competition, CompetitionTeam, Sport, Team
    ids = {}
    with session_scope() as s:
        comp = Competition(sport=Sport.NFL, code="NFL", name="National Football League", area="USA", type="LEAGUE")
        s.add(comp)
        s.flush()
        for name, tla in [(f"Synthetic {t}", t) for t in tlas] + list(extra):
            t = Team(sport=Sport.NFL, name=name, tla=tla)
            s.add(t)
            s.flush()
            s.add(CompetitionTeam(competition_id=comp.id, team_id=t.id, season="2026"))
            ids.setdefault(tla, []).append(t.id)
    return ids


# ---- SYNTHETIC release files --------------------------------------------------------------------------------------------

def _z(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def _row(dt, team, n, rank="1", abb=None, slot=None, grp="Offense", gsis=None, espn=None, name=None):
    """One SYNTHETIC row: player n of the team (ids and names made up), at the slot (abb, slot, rank)."""
    abb = abb or ("QB" if n < 3 else f"P{n}")
    return {"dt": _z(dt), "team": team, "player_name": name or f"Synthetic {team} {n}",
            "espn_id": espn if espn is not None else str(900000 + n),
            "gsis_id": gsis if gsis is not None else f"00-SYN{team}{n:04d}",
            "pos_grp_id": "1", "pos_grp": grp, "pos_id": str(n), "pos_name": abb, "pos_abb": abb,
            "pos_slot": slot or ("1" if n < 3 else str(n)), "pos_rank": rank if n < 3 else "1"}


def _chart(dt, team, size, qb1=1, qb2=2):
    """A SYNTHETIC full chart of `size` rows: QB1 is player qb1, QB2 player qb2, then one player per other slot."""
    rows = [_row(dt, team, qb1, "1"), _row(dt, team, qb2, "2")]
    return rows + [_row(dt, team, n) for n in range(3, size + 1)]


def _write(path: Path, rows, columns=nv.COLUMNS) -> Path:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(columns))
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in columns})
    return path


D1 = datetime(2026, 10, 1, 7, 1, 33)          # SYNTHETIC load stamps
D2 = datetime(2026, 10, 2, 7, 2, 10)
D3 = datetime(2026, 10, 3, 7, 0, 51)
F1 = datetime(2026, 10, 3, 8, 45)              # SYNTHETIC fetch times (our clock)
F2 = datetime(2026, 10, 4, 8, 45)


def _ingest(tmp_path, rows, at, name="depth_charts_2026.csv"):
    """One --file ingest of SYNTHETIC rows at our clock `at` (the file under its own directory each time)."""
    d = tmp_path / "in" / at.strftime("%Y%m%dT%H%M%S")
    d.mkdir(parents=True, exist_ok=True)
    return nv.run(file=str(_write(d / name, rows)), now_fn=lambda: at)


def _facts(at, clock="recorded", team=None):
    with _ro() as s:
        return rec.as_of(s, "nfl", at, clock, team=team)


def _who(facts):
    return sorted((f.interval.first.source_team, f.interval.first.player_name, f.interval.first.attrs["pos_abb"],
                   f.interval.first.attrs["pos_rank"]) for f in facts)


# ---- 6(d): the columns by name, the 2023-2024 shape refused -----------------------------------------------------------

def test_6d_the_twelve_columns_are_read_by_name_in_any_order(tmp_path):
    """Law 1: every column by its name; the order is not read (a reordered header of the same twelve reads the same)."""
    _teams("BAL")
    cols = list(reversed(nv.COLUMNS))
    p = _write(tmp_path / "depth_charts_2026.csv", [_row(D1, "BAL", 1, "1")], columns=cols)
    parsed = nv.read_file(p)
    assert [r["player_name"] for _, r in parsed.rows] == ["Synthetic BAL 1"] and parsed.loads == [D1]
    assert nv.COLUMNS == ("dt", "team", "player_name", "espn_id", "gsis_id", "pos_grp_id", "pos_grp", "pos_id",
                          "pos_name", "pos_abb", "pos_slot", "pos_rank")      # 259 item 1, verbatim


# The 2023-2024 weekly shape: a SYNTHETIC header with that dictionary's column names, no real row.
WEEKLY = ("season", "club_code", "week", "game_type", "depth_team", "last_name", "first_name", "football_name",
          "formation", "gsis_id", "jersey_number", "position", "elias_id", "depth_position", "full_name")


def test_6d_the_2023_2024_shape_is_refused_with_its_reason_and_nothing_is_written(tmp_path, capsys):
    p = _write(tmp_path / "depth_charts_2024.csv", [{"season": "2024", "club_code": "BAL", "week": "1"}],
               columns=WEEKLY)
    with pytest.raises(nv.Refused) as e:
        nv.read_file(p)
    assert "2023-2024 weekly shape" in str(e.value) and "NOT ingest" in str(e.value)
    assert "missing ['dt', 'team', 'player_name', 'espn_id'" in str(e.value)
    r = CliRunner().invoke(_cli(), ["availability-nflverse", "--file", str(p)])
    assert r.exit_code == 2 and "2023-2024 weekly shape" in r.output, r.output
    assert _counts() == (0, 0) and not (tmp_path / "logs").exists()        # refused before anything was copied
    r = CliRunner().invoke(_cli(), ["availability-nflverse", "--season", "2024"])
    assert r.exit_code == 2 and "DIFFERENT shape" in r.output and _counts() == (0, 0)


@pytest.mark.parametrize("cols,why", [
    (nv.COLUMNS[:-1], "missing ['pos_rank']"),
    ((*nv.COLUMNS, "extra"), "unexpected ['extra']"),
    ((*nv.COLUMNS[:-1], "pos_slot"), "repeated ['pos_slot']"),
])
def test_6d_a_header_short_of_or_beyond_the_twelve_is_refused(tmp_path, cols, why):
    p = tmp_path / "x.csv"
    p.write_text(",".join(cols) + "\n")
    with pytest.raises(nv.Refused, match=re.escape(why)):
        nv.read_file(p)


@pytest.mark.parametrize("field,value,why", [("dt", "2026-10-01 07:01:33", "not an ISO-8601 instant with Z"),
                                             ("dt", "yesterday", "not an ISO-8601"), ("team", "", "names no team")])
def test_a_row_the_adapter_cannot_read_refuses_the_file_naming_its_line(tmp_path, field, value, why):
    bad = {**_row(D1, "BAL", 1), field: value}
    p = _write(tmp_path / "f.csv", [_row(D1, "BAL", 2, "2"), bad])
    with pytest.raises(nv.Refused, match=f"line 3.*{re.escape(why)}"):
        nv.read_file(p)


# ---- a row -> an assertion -----------------------------------------------------------------------------------------------

def test_a_row_becomes_one_depth_rank_assertion_verbatim_with_both_ids_and_the_mapped_team(tmp_path):
    ids = _teams("BAL")
    rows = [_row(D1, "BAL", 1, "1"), _row(D1, "BAL", 2, "2", gsis="00-SYN777", espn=""), _row(D1, "LV", 1, "1")]
    ing = _ingest(tmp_path, rows, F1)
    assert ing.status == "partial" and ing.rows_asserted == 3 and ing.unmapped_teams == {"LV": 1}  # 254 item 2(7)
    with _ro() as s:
        got = {(r.source_team, r.player_name): r for r in rec.load_rows(s, "nfl")}
    a = got[("BAL", "Synthetic BAL 1")]
    assert (a.kind, a.player_id, a.source_player_id, a.team_id, a.match_id) == ("depth_rank", None, "900001",
                                                                                ids["BAL"][0], None)  # espn_id: the key
    assert a.attrs == {"pos_grp": "Offense", "pos_abb": "QB", "pos_slot": "1", "pos_rank": "1",
                       "dt_raw": "2026-10-01T07:01:33Z", "espn_id": "900001", "gsis_id": "00-SYNBAL0001"}
    assert a.source_stamp == D1 and a.recorded_at == F1 and a.payload_sha256 is not None
    b = got[("BAL", "Synthetic BAL 2")]
    assert b.source_player_id == "00-SYN777" and b.attrs["espn_id"] == "" and b.attrs["gsis_id"] == "00-SYN777"  # gsis
    #                                                                       only where espn_id is empty
    lv = got[("LV", "Synthetic LV 1")]
    assert lv.team_id is None and lv.source_team == "LV"                    # law 4: NULL + the text, never guessed
    assert ing.unmapped_players == 3                                          # 254 item 2(3): every player, counted
    assert not any(r.kind != "depth_rank" for r in got.values())              # never projected_starter (252 3(a))


def test_a_gsis_id_filled_in_between_two_loads_is_the_same_player_not_a_flip(tmp_path):
    """The key is ONE id that does not move (espn_id, the chart's own): BAL's QB1 at D1 with gsis_id empty, at D2 with
    it filled in, reads as ONE open interval under both clocks, restated, never closed "slot asserted to someone else".
    (Against the earlier "gsis else espn" key this test fails: the interval closed at D2 and a new one opened.)"""
    _teams("BAL")
    _ingest(tmp_path, [_row(D1, "BAL", 1, "1", gsis="", espn="4040"), _row(D1, "BAL", 2, "2")], F1)
    _ingest(tmp_path, [_row(D2, "BAL", 1, "1", gsis="00-0099999", espn="4040"), _row(D2, "BAL", 2, "2")], F2)
    with _ro() as s:
        rows = rec.load_rows(s, "nfl")
        for clock in rec.CLOCKS:
            ivs = [iv for iv in rec.derive(rows, clock) if iv.first.player_name == "Synthetic BAL 1"]
            assert len(ivs) == 1, (clock, [(iv.start, iv.end, iv.why_closed) for iv in ivs])
            assert ivs[0].end is None and ivs[0].why_closed is None and ivs[0].restated == 1, clock
            assert ivs[0].last.attrs["gsis_id"] == "00-0099999"                 # the filled-in id kept, as attrs
    assert [f.interval.first.player_name for f in _facts(F2) if f.interval.first.attrs["pos_rank"] == "1"] == [
        "Synthetic BAL 1"]


def test_a_tla_two_nfl_teams_hold_is_ambiguous_and_never_guessed(tmp_path):
    _teams("BAL", extra=[("Synthetic BAL twin", "BAL")])
    ing = _ingest(tmp_path, [_row(D1, "BAL", 1)], F1)
    assert ing.status == "partial" and ing.ambiguous_teams == {"BAL"}
    with _ro() as s:
        (r,) = rec.load_rows(s, "nfl")
    assert r.team_id is None
    assert any("ambiguous tla (more than one NFL team): BAL" in ln for ln in ing.lines())


def test_a_team_outside_the_nfl_competition_does_not_map(tmp_path):
    """The mapping reads the NFL competition's teams only: a Sport.NFL team of another competition (an NCAA program)
    holding the same tla is not a candidate."""
    from src.db.database import session_scope
    from src.db.schema import Competition, CompetitionTeam, Sport, Team
    with session_scope() as s:
        c = Competition(sport=Sport.NFL, code="NCAA", name="NCAA Football", area="USA", type="LEAGUE")
        t = Team(sport=Sport.NFL, name="Synthetic college", tla="BAL")
        s.add_all([c, t])
        s.flush()
        s.add(CompetitionTeam(competition_id=c.id, team_id=t.id, season="2026"))
    ing = _ingest(tmp_path, [_row(D1, "BAL", 1)], F1)
    assert ing.unmapped_teams == {"BAL": 1} and ing.status == "partial"


# ---- only new rows -------------------------------------------------------------------------------------------------------

def test_only_rows_later_than_the_newest_stamp_held_are_asserted(tmp_path):
    _teams("BAL")
    first = _ingest(tmp_path, _chart(D1, "BAL", 5), F1)
    assert (first.rows_read, first.loads, first.new_loads, first.rows_asserted, first.old_rows) == (5, 1, 1, 5, 0)
    second = _ingest(tmp_path, _chart(D1, "BAL", 5) + _chart(D2, "BAL", 5, qb1=2, qb2=1), F2)
    assert (second.rows_read, second.loads, second.new_loads, second.rows_asserted, second.old_rows) == (10, 2, 1, 5, 5)
    assert second.watermark == D1
    with _ro() as s:
        stamps = sorted({r.source_stamp for r in rec.load_rows(s, "nfl")})
    assert stamps == [D1, D2] and _counts() == (2, 10)


def test_the_watermark_is_the_sources_so_an_older_seasons_file_after_a_newer_one_is_refused_never_silent(tmp_path):
    """252 item 3(a) "the newest source_stamp we hold for the source": a 2025 file read after the 2026 one can assert
    nothing, so it is REFUSED naming both instants (a --file: nothing written, nothing copied), never a silent
    `complete`; read first, it asserts its rows (the order hosting-h1.md's recipe requires, 259 item 2(c))."""
    _teams("BAL")
    early = _ingest(tmp_path, _chart(D1 - timedelta(days=200), "BAL", 3), F1, name="depth_charts_2025.csv")
    assert (early.rows_asserted, early.status) == (3, "complete")
    _ingest(tmp_path, _chart(D2, "BAL", 3), F1 + timedelta(hours=1), name="depth_charts_2026.csv")
    before, kept = _counts(), sorted((tmp_path / "logs").rglob("*"))
    with pytest.raises(nv.Refused, match=r"every load is older than the source's watermark \(newest dt "
                                         r"2026-03-15T07:01:33Z < 2026-10-02T07:02:10Z held\).*259 item 2\(c\)"):
        _ingest(tmp_path, _chart(D1 - timedelta(days=200), "BAL", 3), F2, name="depth_charts_2025.csv")
    assert _counts() == before and sorted((tmp_path / "logs").rglob("*")) == kept


def test_a_fetched_file_older_than_the_watermark_is_a_failed_observation_and_pages(tmp_path):
    """The chain's case: a fetched file holding only loads older than the watermark is a `failed` observation (exit 1:
    the chain pages), the file kept; a changed file whose newest load IS the watermark is `complete`, 0 rows, and says
    "no new load"."""
    _teams("BAL")
    _ingest(tmp_path, _chart(D2, "BAL", 3), F1)
    ing = nv.run(2025, http_get=FakeHTTP(FakeResp(200, _body(_chart(D1, "BAL", 3)))), now_fn=lambda: F2)
    assert ing.status == "failed" and "older than the source's watermark" in ing.got.error and ing.rows_asserted == 0
    assert (tmp_path / ing.got.payload_path).is_file()
    same = nv.run(2026, http_get=FakeHTTP(FakeResp(200, _body(_chart(D2, "BAL", 3, qb1=2, qb2=1)))),
                  now_fn=lambda: F2 + timedelta(hours=1))
    assert (same.status, same.rows_asserted, same.old_rows) == ("complete", 0, 3)
    assert "  no new load: the file's newest dt is the watermark (2026-10-02T07:02:10Z); nothing to assert" in \
        same.lines()


def test_a_load_from_the_future_is_refused_and_never_holds_the_watermark(tmp_path):
    """One row stamped later than our fetch (plus FUTURE_SKEW) refuses the file naming its line: a --file writes
    nothing; a fetched file is a failed observation. The watermark stays, and the next real load is asserted."""
    _teams("BAL")
    _ingest(tmp_path, _chart(D1, "BAL", 3), F1)
    future = _chart(D2, "BAL", 3) + [_row(datetime(2062, 1, 1, 7), "BAL", 4)]
    before = _counts()
    with pytest.raises(nv.Refused, match=r"line 5: dt 2062-01-01T07:00:00Z is later than our fetch"):
        _ingest(tmp_path, future, F2)
    assert _counts() == before
    ing = nv.run(2026, http_get=FakeHTTP(FakeResp(200, _body(future))), now_fn=lambda: F2)
    assert ing.status == "failed" and "line 5: dt 2062-01-01T07:00:00Z" in ing.got.error
    within = _chart(D3, "BAL", 3)                                                # a real later load
    assert nv.future_refusal(nv.Parsed(rows=[], loads=[F2 + nv.FUTURE_SKEW]), F2) is None   # the skew is allowed
    nxt = _ingest(tmp_path, _chart(D2, "BAL", 3) + within, F2 + timedelta(hours=2))
    assert nxt.watermark == D1 and nxt.rows_asserted == 6                       # nothing from 2062 held


# ---- the snapshot closure (259 item 2(a)) ----------------------------------------------------------------------------------

def test_a_full_group_closes_every_fact_of_its_team_it_does_not_restate(tmp_path):
    """D1: BAL QB1 = 1, QB2 = 2, players 3..6 at their slots. D2: QB1 = 2, QB2 = 1 (the flip), player 6 gone, a new
    player 7. Player 6's slot is given to no one: only the snapshot closes it."""
    _teams("BAL")
    d2 = _chart(D2, "BAL", 5, qb1=2, qb2=1) + [_row(D2, "BAL", 7)]
    _ingest(tmp_path, _chart(D1, "BAL", 6) + d2, F1)
    with _ro() as s:
        ivs = rec.derive(rec.load_rows(s, "nfl"), "source")
    by = {(iv.first.player_name, iv.first.source_stamp): iv for iv in ivs}
    gone = by[("Synthetic BAL 6", D1)]
    assert (gone.end, gone.why_closed, gone.closed_by.source_team) == (D2, "not restated in its team's snapshot", "BAL")
    assert by[("Synthetic BAL 1", D1)].why_closed == "asserted differently"   # QB1 -> QB2: the ruled rules come first
    assert by[("Synthetic BAL 3", D1)].end is None and by[("Synthetic BAL 3", D1)].restated == 1
    assert _who(_facts(D2, "source")) == sorted(
        [("BAL", "Synthetic BAL 2", "QB", "1"), ("BAL", "Synthetic BAL 1", "QB", "2")]
        + [("BAL", f"Synthetic BAL {n}", f"P{n}", "1") for n in (3, 4, 5, 7)])


def test_a_team_absent_from_a_load_keeps_its_facts_open(tmp_path):
    _teams("BAL", "JAX")
    _ingest(tmp_path, _chart(D1, "BAL", 4) + _chart(D1, "JAX", 4) + _chart(D2, "BAL", 4, qb1=2, qb2=1), F1)
    now = _facts(D2, "source")
    assert len([f for f in now if f.interval.first.source_team == "JAX"]) == 4      # law 4: absent is not "gone"
    assert all(f.interval.first.source_stamp == D1 for f in now if f.interval.first.source_team == "JAX")


def test_rows_without_a_payload_hash_keep_the_generic_rules(tmp_path):
    """The snapshot rule reads LOADS of the kept file only (record.snapshot_load): nflverse rows written without a
    payload hash (the schema PR's synthetic histories) keep the generic rules, as tests/test_availability_record.py
    pins unchanged; and no other source is touched."""
    def obs(t, sha=None):
        return {"sport": "nfl", "source": nv.SOURCE, "endpoint": "file:synthetic.csv", "status": "complete",
                "fetched_at": t, "payload_sha256": sha}

    def a(n, stamp, rank="1"):
        return {"kind": "depth_rank", "source_player_id": f"00-{n}", "player_name": f"Synthetic {n}",
                "source_team": "BAL", "source_stamp": stamp,
                "attrs": {"pos_grp": "Offense", "pos_abb": "WR", "pos_slot": str(n), "pos_rank": rank}}
    rec.write_observation(obs(F1), [a(1, D1), a(2, D1)])
    rec.write_observation(obs(F2), [a(1, D2)])                                   # no hash: not a load
    assert sorted(f.interval.first.player_name for f in _facts(F2)) == ["Synthetic 1", "Synthetic 2"]
    rec.write_observation(obs(F2 + timedelta(days=1), "a" * 64), [a(1, D3)])     # a load: closes player 2
    assert [f.interval.first.player_name for f in _facts(F2 + timedelta(days=1))] == ["Synthetic 1"]


# ---- the partial-group guard (259 item 2(b)) ---------------------------------------------------------------------------------

def test_a_2_row_group_after_a_79_row_group_is_partial_closes_nothing_and_is_counted(tmp_path):
    """The CAR shape of 259 item 1 on SYNTHETIC rows: 79 rows at D1, 2 at D2 (partial: 2 < 79 / 2), 79 at D3. D2's
    rows are asserted, close nothing, and the receipt counts the group; D3, complete again, closes what it does not
    restate. The other team's 79-row group at D2 is complete and closes as ruled."""
    _teams("CAR", "JAX")
    d2_car = [_row(D2, "CAR", 1, "1"), _row(D2, "CAR", 80, abb="QB", slot="1", rank="2")]
    rows = (_chart(D1, "CAR", 79) + _chart(D1, "JAX", 79) + d2_car + _chart(D2, "JAX", 78)
            + _chart(D3, "CAR", 78) + _chart(D3, "JAX", 78))
    ing = _ingest(tmp_path, rows, F1)
    assert [(dt, team, n, prev) for dt, team, n, prev in ing.partial_groups] == [(D2, "CAR", 2, 79)]
    assert "  partial team groups: 1, closing nothing" in "\n".join(ing.lines())
    at_d2 = _facts(D2, "source", team="CAR")
    assert len(at_d2) == 80                     # D1's 79 stay open, plus the new player 80 at QB2 (a fact seen is a fact)
    assert sum(f.interval.first.player_name == "Synthetic CAR 2" for f in at_d2) == 1     # QB2 of D1, not closed
    at_d3 = _facts(D3, "source", team="CAR")
    assert len(at_d3) == 78 and not any(f.interval.first.player_name.endswith((" 79", " 80")) for f in at_d3)
    jax = _facts(D2, "source", team="JAX")
    assert len(jax) == 78                       # a complete group: player 79 closed by the snapshot


def test_the_first_group_ever_seen_is_complete_and_exactly_half_is_not_partial(tmp_path):
    _teams("BAL", "DEN")
    rows = _chart(D1, "BAL", 2) + _chart(D1, "DEN", 80) + _chart(D2, "DEN", 40) + _chart(D3, "DEN", 19)
    ing = _ingest(tmp_path, rows, F1)
    # BAL's first group (2 rows) is complete by definition; DEN at D2: 40 of 80 is not FEWER than half; at D3: 19 < 20
    assert [(dt, team, n, prev) for dt, team, n, prev in ing.partial_groups] == [(D3, "DEN", 19, 40)]
    assert len(_facts(D2, "source", team="DEN")) == 40 and len(_facts(D3, "source", team="DEN")) == 40


def test_the_guard_reads_the_stored_loads_across_fetches(tmp_path):
    """The previous complete group may be in an earlier fetch: the receipt's count and derive() agree."""
    _teams("CAR")
    _ingest(tmp_path, _chart(D1, "CAR", 79), F1)
    ing = _ingest(tmp_path, [_row(D2, "CAR", 1, "1"), _row(D2, "CAR", 2, "2")], F2)
    assert [(team, n, prev) for _, team, n, prev in ing.partial_groups] == [("CAR", 2, 79)]
    assert len(_facts(F2, team="CAR")) == 79                                     # the recorded clock: nothing closed
    with _ro() as s:
        assert nv.stored_complete_groups(s) == {(nv.SOURCE, ("src", "CAR")): 79}


# ---- both clocks -----------------------------------------------------------------------------------------------------------

def test_both_clocks_read_the_loads_and_as_of_is_the_history_cut(tmp_path):
    """One fetch at F1 carries three loads. Source clock: each load's chart from its dt. Recorded clock: nothing
    before F1, the LAST load's chart from F1 (the earlier loads' intervals open and close at F1; history keeps them).
    Under either clock as_of is the full derivation cut at the instant (test 6(g)'s pin, on loads)."""
    _teams("BAL")
    rows = _chart(D1, "BAL", 4) + _chart(D2, "BAL", 4, qb1=2, qb2=1) + _chart(D3, "BAL", 3)
    _ingest(tmp_path, rows, F1)
    assert _facts(D2, "source")[0].backfilled is True                            # recorded > 24 h after D2
    qb1 = lambda fs: [f.interval.first.player_name for f in fs if f.interval.first.attrs["pos_rank"] == "1"  # noqa
                      and f.interval.first.attrs["pos_abb"] == "QB"]
    assert qb1(_facts(D1, "source")) == ["Synthetic BAL 1"] and qb1(_facts(D2, "source")) == ["Synthetic BAL 2"]
    assert len(_facts(D3, "source")) == 3                                        # player 4 closed at D3
    assert _facts(F1 - timedelta(seconds=1)) == []                               # never before our fetch
    rec_now = _facts(F1)
    assert len(rec_now) == 3 and qb1(rec_now) == ["Synthetic BAL 1"]             # the last load's chart
    with _ro() as s:
        rows_ = rec.load_rows(s, "nfl")
        hist = rec.history(s, "nfl", F1)
        for clock in rec.CLOCKS:
            full = rec.derive(rows_, clock)
            for t in (D1, D2, D3, F1, D1 - timedelta(seconds=1), D2 + timedelta(seconds=1), F1 + timedelta(days=1)):
                cut = sorted(iv.first.id for iv in full if iv.start <= t and (iv.end is None or iv.end > t))
                assert sorted(f.interval.first.id for f in rec.as_of(s, "nfl", t, clock=clock)) == cut, (clock, t)
    assert len(hist) == 11 and any("not restated in its team's snapshot" in rec.history_line(r, iv) for r, iv in hist)


def test_backfilled_rows_are_labelled_and_a_fresh_load_puts_the_fact_in_the_live_era(tmp_path):
    """259 item 2(c): every row before our first fetch is BACKFILLED under the recorded clock (recorded more than
    SOURCE_CADENCE_HOURS after its dt); a fresh load the next day that restates the fact puts it in the live-era
    record (the schema PR's Fact.live_since)."""
    _teams("BAL")
    old = D1 - timedelta(days=30)
    first = _ingest(tmp_path, _chart(old, "BAL", 3), F1)
    assert first.backfilled == 3
    assert all(f.backfilled is True for f in _facts(F1))
    assert "BACKFILLED" in rec.fact_line(_facts(F1)[0])
    fresh = F2 - timedelta(hours=1, minutes=44)                                   # a 07:01Z load, read at 08:45Z
    second = _ingest(tmp_path, _chart(fresh, "BAL", 3), F2)
    assert second.backfilled == 0
    now = _facts(F2)
    assert all(f.backfilled is False and f.live_since == F2 for f in now) and len(now) == 3


# ---- the conditional GET (259 item 2(e)) with a fake HTTP layer ------------------------------------------------------------

class FakeResp:
    def __init__(self, status, body=b"", etag=None):
        self.status_code, self._body = status, body
        self.headers = {"ETag": etag} if etag else {}
        self.closed = False

    def iter_content(self, chunk_size=1):
        for i in range(0, len(self._body), 7):                                  # several chunks
            yield self._body[i:i + 7]

    def close(self):
        self.closed = True


class FakeHTTP:
    """No network: answers from a script, recording every call's URL and arguments."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, url, **kw):
        self.calls.append((url, kw))
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a


def _body(rows) -> bytes:
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(nv.COLUMNS), lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode()


def _obs():
    with _engine().connect() as c:
        return [dict(r._mapping) for r in c.execute(text(
            "SELECT id, endpoint, status, http_status, payload_sha256, payload_path, rows_asserted, error "
            "FROM availability_observations ORDER BY id"))]


def test_the_conditional_get_200_304_identical_changed_and_failed(tmp_path):
    _teams("BAL")
    url = nv.release_url(2026)
    b1 = _body(_chart(D1, "BAL", 3))
    b2 = _body(_chart(D1, "BAL", 3) + _chart(D2, "BAL", 3, qb1=2, qb2=1))
    http = FakeHTTP(FakeResp(200, b1, '"etag-1"'), FakeResp(304), FakeResp(200, b1, '"etag-1b"'),
                    FakeResp(200, b2, '"etag-2"'),
                    ConnectionError(f"HTTPSConnectionPool: Max retries exceeded with url: "
                                    f"https://release-assets.githubusercontent.com/x?sig=SECRETSIG123&jwt=eyJSECRET"))
    times = iter([F1, F1 + timedelta(hours=1), F1 + timedelta(hours=2), F2, F2 + timedelta(hours=1)])
    runs = [nv.run(2026, http_get=http, now_fn=lambda: next(times)) for _ in range(5)]
    assert [r.status for r in runs] == ["complete", "complete", "complete", "complete", "failed"]
    assert [r.rows_asserted for r in runs] == [3, 0, 0, 3, 0]
    o = _obs()
    sha1, sha2 = hashlib.sha256(b1).hexdigest(), hashlib.sha256(b2).hexdigest()
    assert [x["http_status"] for x in o] == [200, 304, 200, 200, None]
    assert [x["payload_sha256"] for x in o] == [sha1, sha1, sha1, sha2, None]   # 304 and identical: the previous one
    assert o[1]["payload_path"] == o[2]["payload_path"] == o[0]["payload_path"] != o[3]["payload_path"]
    assert all(x["endpoint"] == url for x in o)                                  # the requested URL, no secret
    # the If-None-Match: none on the first call, the stored ETag after; redirects followed; explicit timeouts; streamed
    sent = [kw["headers"].get("If-None-Match") for _, kw in http.calls]
    assert sent == [None, '"etag-1"', '"etag-1"', '"etag-1b"', '"etag-2"']     # the identical 200's ETag stored
    assert all(kw["allow_redirects"] is True and kw["timeout"] == nv.TIMEOUT == (10, 120) and kw["stream"]
               for _, kw in http.calls)
    # the files: kept only when changed, under logs/availability/nflverse_depth_charts/<date>/, the ETag beside them
    kept = sorted(p.relative_to(tmp_path).as_posix() for p in (tmp_path / "logs").rglob("*") if p.is_file())
    assert kept == sorted([o[0]["payload_path"], o[0]["payload_path"] + ".etag", o[3]["payload_path"],
                           o[3]["payload_path"] + ".etag"])
    assert all(k.startswith("logs/availability/nflverse_depth_charts/2026-10-0") for k in kept)
    assert (tmp_path / o[0]["payload_path"]).read_bytes() == b1                  # unaltered
    assert (tmp_path / (o[3]["payload_path"] + ".etag")).read_text().strip() == '"etag-2"'
    assert "304 not modified" in runs[1].got.etag and "byte-identical" in runs[2].got.etag
    assert (tmp_path / (o[0]["payload_path"] + ".etag")).read_text().strip() == '"etag-1b"'
    assert runs[2].got.etag.endswith("; its new ETag stored beside the kept payload")
    # the failure: a failed row, the error redacted (the signed URL's query cut, every credential-like value gone)
    assert o[4]["status"] == "failed" and o[4]["error"].startswith("ConnectionError")
    assert "SECRETSIG123" not in o[4]["error"] and "eyJSECRET" not in o[4]["error"]
    assert _counts() == (5, 6)


@pytest.mark.parametrize("answer,why,transient", [
    (FakeResp(404), "HTTP 404", None), (FakeResp(500), "HTTP 500", "500 Server Error"),
    (FakeResp(503), "HTTP 503", "503 Server Error"), (FakeResp(429), "HTTP 429", "429 Client Error"),
    (FakeResp(403), "HTTP 403", None), (FakeResp(302), "HTTP 302", None)])
def test_another_status_is_a_failed_observation_with_its_status(answer, why, transient):
    """A 5xx or a 429 is worded as requests words it, so sp_run's retry reads it in its transient class like a
    connection error (each attempt its own failed observation); any other status is never retried."""
    ing = nv.run(2026, http_get=FakeHTTP(answer), now_fn=lambda: F1)
    (o,) = _obs()
    assert ing.status == o["status"] == "failed" and o["http_status"] == answer.status_code and why in o["error"]
    tail = [ln for ln in ing.lines() if "error (redacted)" in ln]
    assert sp_run.transient_class(1, tail) == transient
    assert sp_run.transient_class(1, ["  error (redacted): ConnectionError: boom"]) == "ConnectionError"   # control


def test_a_byte_identical_200_with_a_new_etag_stores_it_and_the_next_call_sends_it(tmp_path):
    """259 item 2(e) "one small request on an unchanged day": a 200 identical to the kept payload but carrying a
    different ETag (the stored one no longer matched) writes the new ETag beside the kept payload, so the next call is
    conditional on it and gets its 304; no DB row changes."""
    _teams("BAL")
    b1 = _body(_chart(D1, "BAL", 3))
    http = FakeHTTP(FakeResp(200, b1, '"old"'), FakeResp(200, b1, '"new"'), FakeResp(304))
    times = iter([F1, F2, F2 + timedelta(hours=1)])
    runs = [nv.run(2026, http_get=http, now_fn=lambda: next(times)) for _ in range(3)]
    assert [kw["headers"].get("If-None-Match") for _, kw in http.calls] == [None, '"old"', '"new"']
    assert [r.status for r in runs] == ["complete"] * 3 and [r.rows_asserted for r in runs] == [3, 0, 0]
    o = _obs()
    assert len({x["payload_path"] for x in o}) == 1
    assert (tmp_path / (o[0]["payload_path"] + ".etag")).read_text() == '"new"\n'
    assert "its new ETag stored beside the kept payload" in runs[1].got.etag
    same = FakeHTTP(FakeResp(200, b1, '"new"'))                                  # the same ETag: nothing rewritten
    r = nv.run(2026, http_get=same, now_fn=lambda: F2 + timedelta(hours=2))
    assert r.got.etag == "ETag sent; 200 byte-identical (not kept again)"


def test_a_fetched_file_of_the_other_shape_is_a_failed_observation_and_kept(tmp_path):
    import io
    buf = io.StringIO()
    csv.writer(buf).writerow(WEEKLY)
    ing = nv.run(2026, http_get=FakeHTTP(FakeResp(200, buf.getvalue().encode())), now_fn=lambda: F1)
    (o,) = _obs()
    assert ing.status == "failed" and "2023-2024 weekly shape" in o["error"] and o["http_status"] == 200
    assert (tmp_path / o["payload_path"]).is_file() and o["rows_asserted"] == 0   # the raw answer kept (evidence)


def test_a_broken_stream_leaves_no_partial_file():
    class Broken(FakeResp):
        def iter_content(self, chunk_size=1):
            yield b"dt,team"
            raise OSError("connection reset")
    ing = nv.run(2026, http_get=FakeHTTP(Broken(200)), now_fn=lambda: F1)
    assert ing.status == "failed" and "connection reset" in ing.got.error
    assert Path("logs").is_dir() and not [p for p in Path("logs").rglob("*") if p.is_file()]   # the .part removed


def test_the_cli_fetches_through_requests_get_and_exits_1_on_a_failed_read(monkeypatch):
    import requests
    http = FakeHTTP(ConnectionError("boom"), FakeResp(200, _body(_chart(D1, "BAL", 2)), '"e"'))
    monkeypatch.setattr(requests, "get", http)                                   # no network: the fake answers
    r = CliRunner().invoke(_cli(), ["availability-nflverse", "--season", "2026"])
    assert r.exit_code == 1 and "· failed ·" in r.output and "error (redacted): ConnectionError: boom" in r.output
    r = CliRunner().invoke(_cli(), ["availability-nflverse", "--season", "2026"])
    assert r.exit_code == 0, r.output
    lines = r.output.splitlines()
    assert lines[0].startswith("AVAILABILITY-NFLVERSE · observation #2 · partial · <" + nv.release_url(2026) + ">")
    assert "  rows read 2 · loads 1 (new 1) · new rows 2 · rows asserted 2 · older rows not asserted again 0" in r.output
    assert "  partial team groups: 0, closing nothing" in lines
    assert "unmapped teams: 1 (BAL (2 row(s)))" in r.output and "unmapped players: 2 row(s)" in r.output
    assert "backfilled rows (recorded more than 24 h after their dt): 2" in r.output
    assert re.search(r"payload sha256 [0-9a-f]{16} · logs/availability/nflverse_depth_charts/\d{4}-\d\d-\d\d/", r.output)
    assert "ETag: no ETag stored (unconditional GET); 200 changed" in r.output
    assert lines[-1] == "Depth charts: nflverse (CC BY 4.0)"


def test_the_cli_refuses_an_unmigrated_store_before_any_call(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import requests
    import src.db.database as db
    other = tmp_path / "unmigrated.db"
    eng = create_engine(f"sqlite:///{other}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True))
    db.init_db()
    http = FakeHTTP()
    monkeypatch.setattr(requests, "get", http)
    r = CliRunner().invoke(_cli(), ["availability-nflverse"])
    assert r.exit_code == 2 and "has not run" in r.output and http.calls == []
    eng.dispose()


def test_the_cli_has_no_db_option_the_ingest_writes_the_live_db_only():
    """254 item 2(9): --db STAYS on the query command; the ingest takes none (a .backup copy is never written)."""
    cmd = _cli().commands["availability-nflverse"]
    opts = {o for p in cmd.params for o in p.opts}
    assert opts == {"--season", "--file"}
    assert "--db" in {o for p in _cli().commands["availability"].params for o in p.opts}


def test_the_default_season_turns_over_in_march():
    assert nv.current_season(datetime(2026, 11, 5)) == 2026 and nv.current_season(datetime(2027, 2, 28)) == 2026
    assert nv.current_season(datetime(2027, 3, 1)) == 2027
    assert nv.release_url(2025) == ("https://github.com/nflverse/nflverse-data/releases/download/depth_charts/"
                                    "depth_charts_2025.csv")


# ---- the cadence constant (259 item 2(d)) -----------------------------------------------------------------------------------

def test_the_cadence_constant_is_frozen_hours_per_source_word():
    assert dict(rec.SOURCE_CADENCE_HOURS) == {"nflverse_depth_charts": 24}
    assert type(rec.SOURCE_CADENCE_HOURS["nflverse_depth_charts"]) is int
    with pytest.raises(TypeError):
        rec.SOURCE_CADENCE_HOURS["nflverse_depth_charts"] = 48                   # read-only at run time
    assert not hasattr(rec, "CADENCE")                                           # renamed, no alias
    src = Path(rec.__file__).read_text()
    assert "frozen by addendum 259 item 2(d)" in src and "PROPOSED" not in src.split("SOURCE_CADENCE_HOURS =")[0][-600:]


# ---- 6(a): append-only across a replay ----------------------------------------------------------------------------------------

def test_6a_counts_only_grow_across_a_replay_and_the_feed_has_no_update_or_delete_path(tmp_path):
    _teams("BAL")
    files = [_chart(D1, "BAL", 3), _chart(D1, "BAL", 3) + _chart(D2, "BAL", 3, qb1=2, qb2=1)]
    seen = [_counts()]
    t = F1
    for _ in range(2):
        for rows in files:
            try:
                _ingest(tmp_path, rows, t)
            except nv.Refused as e:                       # the first file, replayed after the second: older, refused
                assert "older than the source's watermark" in str(e)
            t += timedelta(hours=1)
            seen.append(_counts())
    assert all(b[0] >= a[0] and b[1] >= a[1] for a, b in zip(seen, seen[1:]))   # the counts only grow
    assert seen == [(0, 0), (1, 3), (2, 6), (2, 6), (3, 6)]                     # the replay asserts nothing again
    public = [n for n in dir(nv) if not n.startswith("_")]
    assert not [n for n in public if re.search(r"update|delete|upsert|replace|merge|remove|correct|amend", n, re.I)]
    src = Path(nv.__file__).read_text()
    for pat in (r"\bOR\s+REPLACE\b", r"on_conflict", r"\.delete\(", r"[^h]\.update\(", r"(?<!\.)\bupdate\(",
                r"\.merge\(", r"import[^\n]*\b(update|delete)\b", r"\bUPDATE\s+\w+\s+SET\b", r"\bDELETE\s+FROM\b",
                r"\bs\.add(_all)?\(", r"session_scope", r"\.execute\((?!select\()"):
        assert not re.search(pat, src), pat          # record.write_observation only (h.update: the sha256 hasher)
    with _engine().connect() as c:                                               # #831's triggers stand
        assert c.execute(text("SELECT COUNT(*) FROM sqlite_master WHERE type = 'trigger' "
                              "AND tbl_name LIKE 'availability_%'")).scalar() == 6


# ---- #835 item 1 (258 item 2(1)): percent-encoded credential names --------------------------------------------------------
# FAIL-FIRST: each refusal and redaction below failed against HEAD b51d5e85's record.py (6 failed, the 4 controls
# passed); they pass with this PR's _endpoint_secret / _PARAM / redact.

BASE = nv.release_url(2026)


@pytest.mark.parametrize("q", ["api%5Ftoken=abc123def", "s%69g=abc123def", "%6Bey=abc123def",
                               "api%255Ftoken=abc123def"])
def test_835_percent_encoded_credential_names_are_refused_as_endpoints(q):
    why = rec._endpoint_secret(f"{BASE}?{q}")
    assert why is not None and "credential-like parameter" in why
    obs = {"sport": "nfl", "source": nv.SOURCE, "endpoint": f"{BASE}?{q}", "status": "complete", "fetched_at": F1}
    with pytest.raises(rec.Refused, match="carries a secret"):
        rec.write_observation(obs)
    assert _counts() == (0, 0)


@pytest.mark.parametrize("q", ["api_token=abc123def", "sig=abc123def", "key=abc123def"])
def test_835_positive_control_the_plain_names_are_still_refused(q):
    assert rec._endpoint_secret(f"{BASE}?{q}") is not None


def test_835_positive_control_a_benign_encoded_name_is_accepted():
    assert rec._endpoint_secret(f"{BASE}?season%5Fyear=2026") is None
    assert rec._endpoint_secret(BASE) is None


def test_835_an_encoded_environment_value_is_refused(monkeypatch):
    monkeypatch.setenv("API_HOCKEY_KEY", "ab/cd+ef-123")
    why = rec._endpoint_secret(f"{BASE}?x=ab%2Fcd%2Bef-123")
    assert why == "it holds a value of a secret environment variable (percent-decoded)"


def test_835_a_token_behind_an_encoded_name_is_redacted():
    out = rec.redact(f"GET {BASE}?api%5Ftoken=tok-SECRET-9876 failed")
    assert "tok-SECRET-9876" not in out and "[REDACTED]" in out
    out = rec.redact(f"GET {BASE}?api_token%3Dtok-SECRET-9876 failed")          # an encoded separator
    assert "tok-SECRET-9876" not in out
    assert rec.redact("GET https://example.org/a?season%5Fyear=2026") == "GET https://example.org/a?season%5Fyear=2026"


# ---- the chain and the timer (252 item 3(a); 259 item 2(d)) ---------------------------------------------------------------

sys.path.insert(0, str(REPO / "deploy" / "hosting"))
import chains  # noqa: E402
import sp_common as c  # noqa: E402
import sp_run  # noqa: E402

from tests.test_hosting_pack import receipts, sandbox  # noqa: E402,F401


def _cli():
    import cli
    return cli.cli


def test_the_chain_is_one_step_the_seasons_ingest_inside_no_other_chain_and_unmetered():
    ch = chains.CHAINS["availability-daily"]
    assert ch == {"go_on": ("availability-nflverse",), "go_on_why": chains.AVAILABILITY_GO_ON,
                  "steps": [["availability-nflverse", "--season", "2026"]]}
    assert chains.AVAILABILITY_GO_ON.startswith("addendum 252 item 3(a): ")
    assert [n for n, x in chains.CHAINS.items() if any(s and s[0] == "availability-nflverse"
                                                       for s in x.get("steps") or [])] == ["availability-daily"]
    assert "availability-nflverse" in chains.UNMETERED and "backup" not in ch and not ch.get("continue_on_sync_failure")
    cmd = _cli().commands["availability-nflverse"]
    assert "--season" in {o for p in cmd.params for o in p.opts}


def test_the_timer_is_0845_utc_on_t11_timers_with_its_schedule_row_and_live_host_recipe():
    t = (REPO / "deploy" / "hosting" / "systemd" / "sp-availability-daily.timer").read_text()
    assert re.findall(r"^OnCalendar=(.+)$", t, re.M) == ["*-*-* 08:45:00 UTC"]
    assert re.search(r"^Unit=sp-chain@availability-daily\.service$", t, re.M)
    lists = c.t11_lists()
    assert "sp-availability-daily.timer" in lists["TIMERS"]
    rb = (REPO / "docs" / "specs" / "hosting-h1.md").read_text()
    assert "| sp-availability-daily | availability-daily (" in rb and "| daily 08:45 UTC | — |" in rb
    assert "Its ENABLEMENT IS THE ARCHITECT'S BLOCK (252 item 7" in rb
    assert "sudo systemctl enable --now sp-availability-daily.timer" in rb
    import sp_notify
    assert sp_notify.unit_for("availability-daily") == "sp-chain@availability-daily.service"


FAKE_CLI = """import sys
a = sys.argv[1:]
print("ran", " ".join(a))
if a[0] == "availability-nflverse":
    print("AVAILABILITY-NFLVERSE · observation #9 · failed · <x>")
    sys.exit(1)
"""


def test_a_failed_read_is_receipted_pages_and_stops_nothing(sandbox, capsys):
    """The real chain on a fake cli.py: the read fails (exit 1, a failed observation); the receipt carries `continued`
    with the ruling, the chain's exit is the read's (OnFailure pages), and nothing is stopped."""
    (c.REPO / "cli.py").write_text(FAKE_CLI)
    capsys.readouterr()
    assert sp_run.main(["availability-daily"]) == 1
    rs = receipts(sandbox)
    (step,) = [r for r in rs if r["kind"] == "step"]
    assert step["command"] == "python cli.py availability-nflverse --season 2026" and step["exit"] == 1
    assert step["continued"] == chains.AVAILABILITY_GO_ON
    chain = rs[-1]
    assert chain["kind"] == "chain" and chain["exit"] == 1 and chain["stopped_at"] is None
    assert "stopped at step" not in capsys.readouterr().out


# ---- Codex on #841, round 1: the kept payload's path is collision-safe; a refused endpoint leaves nothing on disk ---------

def _kept_files(tmp_path):
    root = tmp_path / "logs" / "availability"
    return sorted(p.relative_to(tmp_path).as_posix() for p in root.rglob("*")) if root.exists() else []


def test_two_different_payloads_kept_in_one_second_both_stay_and_neither_is_overwritten(tmp_path):
    """Fail-first (HEAD 01a52c99 named a kept file <HHMMSS>Z-<name>: the second payload of the same second replaced
    the first, under the first observation's payload_path). The name now carries the payload's sha256 prefix and the
    file is created exclusively: two fetches and two hand-carried files in one second keep four files."""
    _teams("BAL")
    b1 = _body(_chart(D1, "BAL", 3))
    b2 = _body(_chart(D1, "BAL", 3) + _chart(D2, "BAL", 3, qb1=2, qb2=1))
    http = FakeHTTP(FakeResp(200, b1, '"e1"'), FakeResp(200, b2, '"e2"'))
    runs = [nv.run(2026, http_get=http, now_fn=lambda: F1) for _ in range(2)]
    assert [r.status for r in runs] == ["complete", "complete"] and [r.rows_asserted for r in runs] == [3, 3]
    o = _obs()
    assert o[0]["payload_path"] != o[1]["payload_path"]
    assert (tmp_path / o[0]["payload_path"]).read_bytes() == b1                  # the first payload, unaltered
    assert (tmp_path / o[1]["payload_path"]).read_bytes() == b2
    assert hashlib.sha256(b1).hexdigest()[:16] in o[0]["payload_path"]
    assert re.fullmatch(r"logs/availability/nflverse_depth_charts/2026-10-03/084500Z-[0-9a-f]{16}-depth_charts_2026\.csv",
                        o[0]["payload_path"])
    # the same through --file: two different files of one name, one second
    f1 = _ingest(tmp_path, _chart(D3, "BAL", 3), F2, name="hand.csv")
    f2 = _ingest(tmp_path, _chart(D3 + timedelta(hours=1), "BAL", 4), F2, name="hand.csv")
    assert f1.got.payload_path != f2.got.payload_path
    for ing in (f1, f2):
        assert nv.sha256_file(tmp_path / ing.got.payload_path) == ing.got.sha256
    assert len([k for k in _kept_files(tmp_path) if k.endswith(".csv")]) == 4


def test_the_kept_path_is_created_exclusively_reused_for_the_same_bytes_and_refused_for_others(tmp_path):
    src = tmp_path / "src.csv"
    src.write_bytes(b"payload")
    sha = nv.sha256_file(src)
    rel, final = nv._kept(F1, "x.csv", sha)
    assert nv._retain(src, final, sha) is True and final.read_bytes() == b"payload"
    assert nv._retain(src, final, sha) is False                                   # the same bytes: reused
    other = tmp_path / "other.csv"
    other.write_bytes(b"other bytes")
    with pytest.raises(nv.Refused, match="already holds other bytes"):
        nv._retain(other, final, nv.sha256_file(other))                          # never written over
    assert final.read_bytes() == b"payload"


@pytest.mark.parametrize("name, why", [
    ("api_token=secret.csv", "the endpoint carries a secret"),
    ("x" * 246 + ".csv", "longer than 255"),
])
def test_a_refused_file_name_leaves_no_file_and_no_row(tmp_path, name, why):
    """Fail-first (HEAD 01a52c99 copied the file under logs/availability BEFORE the writer checked the endpoint: a
    secret-bearing name stayed on disk as an orphan payload with no row; a name too long for the kept file raised an
    OSError). The endpoint (the writer's own rule) and the kept path are checked before any file or directory is
    made: refused, exit 2, nothing on disk, nothing written."""
    d = tmp_path / "in"
    d.mkdir()
    path = _write(d / name, _chart(D1, "BAL", 3))
    with pytest.raises((nv.Refused, rec.Refused), match=why):
        nv.run(file=str(path), now_fn=lambda: F1)
    assert _kept_files(tmp_path) == [] and _counts() == (0, 0)
    out = CliRunner().invoke(_cli(), ["availability-nflverse", "--file", str(path)])
    assert out.exit_code == 2 and why in out.output and _kept_files(tmp_path) == [] and _counts() == (0, 0)


def test_an_endpoint_past_the_columns_width_is_refused_by_the_one_rule():
    """A file name cannot reach 512 characters (NAME_MAX is 255 bytes), so this is the writer's rule itself, the one the
    adapter now runs first."""
    assert "longer than 512" in rec.endpoint_refusal("file:" + "x" * 600)
    assert rec.endpoint_refusal(nv.release_url(2026)) is None


# ---- Codex on #841, round 1 (finding C, its row widths): a row the writer refuses leaves no orphan payload ----------------

@pytest.mark.parametrize("field, value, why", [
    ("player_name", "N" * 200, "player_name is longer than 128 characters"),
    ("team", "T" * 70, "source_team is longer than 64 characters"),
    ("espn_id", "9" * 70, "source_player_id is longer than 64 characters"),
])
def test_a_row_past_the_writers_width_refuses_the_file_before_anything_is_copied(tmp_path, field, value, why):
    """Fail-first (round 1's head: read_file did not run the writer's widths, so --file copied the payload under
    logs/availability, then write_observation refused the row: an orphan payload with no row). Every row to be asserted
    now goes through record.assertion_refusal (the writer's own checks) BEFORE the copy: exit 2, nothing copied,
    nothing written, through run and through the cli."""
    _teams("BAL")
    rows = _chart(D1, "BAL", 3)
    rows[0] = {**rows[0], field: value}
    d = tmp_path / "in"
    d.mkdir()
    path = _write(d / "depth_charts_2026.csv", rows)
    with pytest.raises(nv.Refused, match=re.escape(why) + ".*nothing copied, nothing written"):
        nv.run(file=str(path), now_fn=lambda: F1)
    assert _kept_files(tmp_path) == [] and _counts() == (0, 0)
    out = CliRunner().invoke(_cli(), ["availability-nflverse", "--file", str(path)])
    assert out.exit_code == 2 and why in out.output, out.output
    assert _kept_files(tmp_path) == [] and _counts() == (0, 0)


def test_a_fetched_row_past_the_writers_width_is_a_failed_observation_that_keeps_its_payload(tmp_path):
    """The fetch path: the payload is kept before it is read (evidence), so a row the writer would refuse is a `failed`
    observation whose payload_path names the kept file, the writer's reason its error; never a refused write that
    leaves the kept file with no row pointing to it."""
    _teams("BAL")
    rows = _chart(D1, "BAL", 3)
    rows[1] = {**rows[1], "player_name": "N" * 200}
    body = _body(rows)
    ing = nv.run(2026, http_get=FakeHTTP(FakeResp(200, body, '"e1"')), now_fn=lambda: F1)
    (o,) = _obs()
    assert ing.status == "failed" and o["status"] == "failed" and o["rows_asserted"] == 0 and _counts() == (1, 0)
    assert "assertion 2 player_name is longer than 128 characters" in o["error"]
    assert o["http_status"] == 200 and o["payload_sha256"] == hashlib.sha256(body).hexdigest()
    assert (tmp_path / o["payload_path"]).read_bytes() == body                   # the kept file, named by its row
    assert [k for k in _kept_files(tmp_path) if k.endswith(".csv")] == [o["payload_path"]]
    assert ing.rows_read == 0 and ing.new_rows == 0 and ing.refused


def test_a_store_refusal_after_the_keep_leaves_no_orphan_payload(tmp_path, monkeypatch):
    """Belt and braces for what no pre-check can see (the store's own refusal, e.g. a trigger): a --file's copy made by
    the run is removed and the refusal stands (exit 2); a fetch is written as a `failed` observation keeping its path."""
    _teams("BAL")
    real = rec.write_observation

    def refuse_rows(obs, assertions=()):
        if assertions:
            raise rec.Refused("REFUSED: the store refused the write (a SYNTHETIC trigger refusal); nothing written")
        return real(obs, assertions)
    monkeypatch.setattr(rec, "write_observation", refuse_rows)
    with pytest.raises(rec.Refused, match="SYNTHETIC trigger refusal"):
        _ingest(tmp_path, _chart(D1, "BAL", 3), F1)
    assert _kept_files(tmp_path) == [] and _counts() == (0, 0)
    body = _body(_chart(D1, "BAL", 3))
    ing = nv.run(2026, http_get=FakeHTTP(FakeResp(200, body)), now_fn=lambda: F1)
    (o,) = _obs()
    assert ing.status == "failed" and o["status"] == "failed" and "SYNTHETIC trigger refusal" in o["error"]
    assert (tmp_path / o["payload_path"]).read_bytes() == body and _counts() == (1, 0)
    assert [k for k in _kept_files(tmp_path) if k.endswith(".csv")] == [o["payload_path"]]


def test_assertion_refusal_is_the_writers_own_check():
    """record.assertion_refusal answers exactly as write_observation's row check does (one rule, two callers)."""
    ok = {"kind": "depth_rank", "source_player_id": "1", "player_name": "A", "source_team": "BAL"}
    assert rec.assertion_refusal(ok, 1, nv.SOURCE) is None
    assert "player_name is longer than 128" in rec.assertion_refusal({**ok, "player_name": "x" * 129}, 1)
    assert rec.assertion_refusal({**ok, "player_name": "x" * 128}, 1) is None
    assert "names no team" in rec.assertion_refusal({**ok, "source_team": None}, 3)
    assert "per-game fact from nhl_api_landing" in rec.assertion_refusal(
        {**ok, "kind": "projected_starter"}, 1, "nhl_api_landing")
