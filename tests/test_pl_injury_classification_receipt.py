"""#688, the PL injury classification receipt (ARCHITECT 2026-10-27 16:10 ET, addendum 171 item 1): read-only.

A throwaway SQLite world (never data/), closing files as a closing run writes them, and a fake provider (no network).
Covers the happy path, failed reads, empty answers, malformed rows, the call cap and the kept payloads, the refusals
(--save / --db under data/, a missing DB, --db not given: 236 item 4), the DB opened read-only (bytes unchanged), and each ruling item (a)-(f)."""
import hashlib
import importlib.util
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("pl_injury_classification_receipt",
                                               ROOT / "scripts" / "pl_injury_classification_receipt.py")
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)

S_CHE = "2026-10-24T15:55:13.036424"          # 9240's closing stamp (the real one)
S_LIV = "2026-10-25T13:25:25.320720"
S_SUN = "2026-10-25T15:55:23.539155"
TEAMS = {"Chelsea": "49", "Tottenham": "47", "Liverpool": "40", "Brighton": "51", "Sunderland": "746",
         "Leeds": "63", "Everton": "45", "Coventry": "1346"}


def _dt(v):
    return datetime.fromisoformat(v)


def build_db(path: Path) -> None:
    from src.db.schema import Base, Competition, Injury, Lineup, Match, MatchStatus, Sport, Team
    eng = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        pl = Competition(sport=Sport.SOCCER, code="PL", name="Premier League", area="England", type="LEAGUE")
        fac = Competition(sport=Sport.SOCCER, code="FAC", name="FA Cup", area="England", type="CUP")
        s.add_all([pl, fac])
        s.flush()
        t = {}
        for n, pid in TEAMS.items():
            t[n] = Team(sport=Sport.SOCCER, name=n, external_ids={"api_football": pid})
            s.add(t[n])
        s.flush()

        def match(mid, h, a, ko, fid, comp=pl, score=(None, None)):
            s.add(Match(id=mid, sport=Sport.SOCCER, competition_id=comp.id, season="2026/27", utc_date=_dt(ko),
                        status=MatchStatus.FINISHED, home_team_id=t[h].id, away_team_id=t[a].id,
                        home_score=score[0], away_score=score[1], external_ids={"api_football": fid}))
        match(9240, "Chelsea", "Tottenham", "2026-10-24T16:30:00", "1001", score=(0, 2))
        match(9238, "Liverpool", "Brighton", "2026-10-25T14:00:00", "1002", score=(2, 0))
        match(9245, "Sunderland", "Leeds", "2026-10-25T16:30:00", "1003", score=(0, 0))
        match(9200, "Tottenham", "Coventry", "2026-10-18T12:00:00", "900", comp=fac)
        match(9300, "Everton", "Coventry", "2026-10-31T15:00:00", "1500")
        s.flush()

        def inj(team, name, typ, fid, stamp, reason="Knee Injury"):
            s.add(Injury(team_id=t[team].id, player_name=name, type=typ, reason=reason, fixture_source_id=fid,
                         refreshed_at=_dt(stamp)))
        # Chelsea: recoverable, all "this fixture"
        for n in ("E. Emegha", "J. Gittens", "R. James", "P. Chavarria", "E. Martinez"):
            inj("Chelsea", n, "Missing Fixture", "1001", S_CHE)
        # Tottenham: recoverable, every fixture-age class
        inj("Tottenham", "D. Kulusevski", "Missing Fixture", "900", S_CHE)          # an earlier fixture (FAC)
        inj("Tottenham", "W. Odobert", "Missing Fixture", "77777", S_CHE)           # fixture not stored
        inj("Tottenham", "P. Porro", "Questionable", "1001", S_CHE)                 # this fixture
        inj("Tottenham", "X. Simons", "Questionable", None, S_CHE)                  # no fixture id stored
        inj("Tottenham", "M. Mudryk", None, "1500", S_CHE)                          # a later fixture, no type
        for n in ("R. Bentancur", "L. Bergvall", "D. Udogie"):
            inj("Tottenham", n, "Missing Fixture", "1001", S_CHE)
        # Liverpool: OVERWRITTEN since (today's list must never be read as the consumed one)
        for n in ("TODAY ONE", "TODAY TWO"):
            inj("Liverpool", n, "Missing Fixture", "1500", "2026-10-30T10:00:00")
        # Brighton: the stamp matches but the count does not
        for n in ("E. Ferguson", "Y. Minteh"):
            inj("Brighton", n, "Missing Fixture", "1002", S_LIV)
        # Leeds: recoverable
        for n in ("M. Joseph", "J. Rodon", "D. James", "D. Calvert-Lewin", "N. Okafor", "A. Stach"):
            inj("Leeds", n, "Missing Fixture", "1003", S_SUN)
        s.add(Lineup(match_id=9240, team_id=t["Chelsea"].id, kind="projected", player_name="R. Sanchez"))
        s.commit()
    eng.dispose()


def row(mid, home, away, ko, hn, an, hc, ac, stamp, call="PASS"):
    return {"match_id": mid, "utc_date": ko, "competition": "PL", "season": "2026/27", "home_team": home,
            "away_team": away,
            "injuries": {"home_count": hc, "away_count": ac, "home_names": hn[:8], "away_names": an[:8]},
            "input_quality": {"lineups": "none", "injuries_synced_at": stamp,
                              "injuries": {"home": {"count": hc, "synced_at": stamp if hc else None},
                                           "away": {"count": ac, "synced_at": stamp if ac else None}}},
            "prediction": {"factor_breakdown": {"home_injuries_count": hc, "away_injuries_count": ac,
                                                "factor_notes": [], "lineup_kind": None}},
            "desk": {"call": call, "pick": "HOME"}}


def closing(ex: Path, start: str, rows: list, fam="SOCCER", sha="f0e4cbf3"):
    ex.mkdir(parents=True, exist_ok=True)
    st = datetime.fromisoformat(start)
    doc = {"exported_at": start + "Z", "git_sha": sha, "sport": fam.lower(), "competition_code": "PL",
           "count": len(rows), "predictions": rows,
           "closing": {"family": fam, "start": start + "Z", "run_id": f"run-{st:%m%d%H%M}",
                       "match_ids": [r["match_id"] for r in rows], "called_off": []}}
    (ex / f"closing_{fam}_{st:%Y-%m-%dT%H%M}Z.json").write_text(json.dumps(doc))


LIV = ["C. Bradley", "H. Ekitike", "G. Leoni", "F. Chiesa", "W. Endo", "C. Gakpo", "A. Isak", "D. Szoboszlai"]


def write_exports(ex: Path):
    che = ["E. Emegha", "J. Gittens", "R. James", "P. Chavarria", "E. Martinez"]
    tot = ["D. Kulusevski", "W. Odobert", "P. Porro", "X. Simons", "M. Mudryk", "R. Bentancur", "L. Bergvall",
           "D. Udogie"]
    lee = ["M. Joseph", "J. Rodon", "D. James", "D. Calvert-Lewin", "N. Okafor", "A. Stach"]
    closing(ex, "2026-10-19T19:00:00", [row(9231, "Tottenham", "Coventry", "2026-10-19T19:00:00", [], [], 0, 0,
                                            None)], sha="1e355f8")                       # before #615's stamping
    closing(ex, "2026-10-24T16:30:00", [row(9240, "Chelsea", "Tottenham", "2026-10-24T16:30:00", che, tot, 5, 8,
                                            S_CHE, call="PLAY")], sha="7121708")
    closing(ex, "2026-10-25T13:00:00", [row(9238, "Liverpool", "Brighton", "2026-10-25T14:00:00", LIV,
                                            ["E. Ferguson"], 12, 8, "2026-10-25T12:25:00")])   # an earlier run
    closing(ex, "2026-10-25T14:00:00", [row(9238, "Liverpool", "Brighton", "2026-10-25T14:00:00", LIV,
                                            ["E. Ferguson", "Y. Minteh", "K. Mitoma"], 12, 3, S_LIV,
                                            call="LADDER")])
    closing(ex, "2026-10-25T16:30:00", [row(9245, "Sunderland", "Leeds", "2026-10-25T16:30:00", [], lee, 0, 6,
                                            S_SUN, call="LADDER")])
    closing(ex, "2026-10-25T16:30:00", [row(9999, "X", "Y", "2026-10-25T16:30:00", [], [], 0, 0, None)],
            fam="MLB")                                                                    # another family


def slot(pid, name):
    return {"player": {"id": pid, "name": name, "number": 1, "pos": "M", "grid": None}}


def pentry(pid, name, minutes, sub):
    return {"player": {"id": pid, "name": name, "photo": ""},
            "statistics": [{"games": {"minutes": minutes, "substitute": sub, "position": "M", "number": 1}}]}


def answers():
    team = lambda n: {"id": int(TEAMS[n]), "name": n, "logo": ""}          # noqa: E731
    return {
        ("fixtures/lineups", "1001"): (200, {}, [
            {"team": team("Chelsea"), "formation": "4-3-3", "coach": {},
             "startXI": [slot(1, "E. Emegha")], "substitutes": [slot(10, "João Pedro"), slot(11, "M. Gusto")]},
            {"team": team("Tottenham"), "formation": "4-3-3", "coach": {},
             "startXI": [slot(20, "Pedro Porro")], "substitutes": [slot(21, "X. Simons"), slot(22, "M. Mudryk")]}]),
        ("fixtures/players", "1001"): (200, {}, [
            {"team": team("Chelsea"), "players": [pentry(1, "E. Emegha", 90, False), pentry(10, "João Pedro", None, True),
                                                  pentry(11, "M. Gusto", 20, True)]},
            {"team": team("Tottenham"), "players": [pentry(20, "Pedro Porro", 90, False),
                                                    pentry(21, "X. Simons", 15, True),
                                                    pentry(22, "M. Mudryk", None, True)]}]),
        ("fixtures/lineups", "1002"): (500, {}, []),                                    # FAILED
        ("fixtures/players", "1002"): (200, {}, [
            {"team": team("Liverpool"), "players": [pentry(30, "Alexander Isak", 30, True),
                                                    pentry(31, "Conor Bradley", 90, False),
                                                    pentry(32, "Giovanni Leoni", 60, None),
                                                    pentry(33, "Mohamed Salah", None, True)]},
            {"team": {"id": 999, "name": "Somebody"}, "players": []}]),                 # a block mapped to no side
        ("fixtures/lineups", "1003"): (200, {}, []),                                    # answered with no rows
        ("fixtures/players", "1003"): (200, {}, [
            "garbage",                                                                  # not an object
            {"team": team("Leeds"), "players": [pentry(40, "Dominic Calvert-Lewin", 0, True),
                                                pentry(41, "N. Okafor", None, True),
                                                pentry(42, "Noah Okafor", 12, True),
                                                7]},                                    # a member not an object
            {"team": team("Sunderland"), "players": [pentry(50, "R. Mundle", None, True)]}]),
    }


class FakeGet:
    def __init__(self, table):
        self.table, self.calls = table, []

    def __call__(self, path, **params):
        self.calls.append((path, params))
        return self.table.get((path, str(params.get("fixture"))), (404, {"x": "not in the fake"}, []))


@pytest.fixture
def world(tmp_path):
    db = tmp_path / "copy.db"
    build_db(db)
    ex = tmp_path / "exports"
    write_exports(ex)
    return {"db": db, "ex": ex, "save": tmp_path / "payloads", "tmp": tmp_path}


def run(w, *extra, get=None, table=None):
    out = []
    g = get or FakeGet(table if table is not None else answers())
    code = rc.main(["--exports", str(w["ex"]), "--db", str(w["db"]), "--save", str(w["save"]), *extra],
                   echo=out.append, get=g)
    return code, out, g


def summary(out):
    assert out[-1].startswith(rc.TAG + " ")
    return json.loads(out[-1][len(rc.TAG) + 1:])


def line(out, start):
    hits = [ln for ln in out if start in ln]
    assert hits, start
    return hits[0]


# ---- the happy path -------------------------------------------------------------------------------------------------

def test_happy_path_rows_header_and_json(world):
    code, out, g = run(world)
    assert code == 0
    sm = summary(out)
    assert sm["matches"] == [9240, 9238, 9245]                     # 9231 before the cut; the MLB file never read
    assert sm["rows"] == 3 and sm["closing_files"] == 6
    assert sm["calls"] == {"made": 6, "cached": 0, "failed": 1, "empty": 1, "cap": 100}
    assert out[1].startswith("PROVIDER (ruling 1(a)): calls made 6 · answers read from the kept payloads 0 · failed "
                             "1 · answered with no rows 1")
    hdr = line(out, "== match 9238")
    assert "closing_SOCCER_2026-10-25T1400Z.json, git_sha f0e4cbf3; earlier runs 1" in hdr   # the last run's row
    assert "desk LADDER" in hdr
    assert "git_sha 7121708" in line(out, "== match 9240")
    assert "stored lineups 1 ({'projected': 1})" in line(out, "match 9240 status finished score 0-2")
    assert sorted(p for p in world["save"].rglob("*.json")) == sorted(
        world["save"] / f for f in ("1001/lineups.json", "1001/players.json", "1002/players.json",
                                    "1003/players.json"))


def test_classes_per_listed_name(world):
    _, out, _ = run(world)
    assert "· this fixture · started — E. Emegha (exact" in line(out, "    E. Emegha")
    assert "started — Pedro Porro (initial form" in line(out, "    P. Porro")
    assert "came on — X. Simons (exact" in line(out, "    X. Simons")
    assert rc.DNP_SQUAD in line(out, "    M. Mudryk")
    assert rc.DNP_ABSENT + " — UNMATCHED in the lineups and players answers" in line(out, "    D. Kulusevski")
    assert "did not appear (in the squad answer, no minutes) — Dominic Calvert-Lewin" in \
        line(out, "    D. Calvert-Lewin")
    assert "AMBIGUOUS name — AMBIGUOUS: N. Okafor | Noah Okafor" in line(out, "    N. Okafor")
    # Leeds' players block holds a member not the provider's shape (7): a name not found is unread, never absent
    assert ("appearance unread — not found, and a missing or malformed member of the side's players answer may hide "
            "him; lineups answered with no rows") in line(out, "    A. Stach")
    assert "UNMATCHED in the players answer" in line(out, "    F. Chiesa")         # lineups FAILED, players read
    assert "· started — Conor Bradley (initial form" in line(out, "    C. Bradley")  # players only: 90 min, sub False
    assert "· " + rc.PLAYED + " — Giovanni Leoni" in line(out, "    G. Leoni")     # players only: substitute null


def test_failed_read_is_named_and_the_other_kind_still_reads(world):
    code, out, _ = run(world)
    assert code == 0
    assert "  FAILED fixture 1002 lineups: HTTP 500" in out
    assert "provider reads: lineups the read FAILED · players read" in line(out, "provider reads: lineups the read F")
    assert "came on — Alexander Isak (initial form" in line(out, "    A. Isak")
    assert ("appearance unread — lineups the read FAILED; the answers read hold no block for the team (its provider "
            "ids ['51'])") in line(out, "    K. Mitoma")


def test_every_read_failed_leaves_names_unread_never_classed(world):
    t = {k: (503, {}, []) for k in answers()}
    code, out, _ = run(world, table=t)
    assert code == 0
    sm = summary(out)
    assert sm["calls"]["failed"] == 6 and sm["calls"]["made"] == 6
    assert set(k for v in sm["by_type"].values() for k in v) == {rc.UNREAD}
    assert "appearance unread — lineups the read FAILED; players the read FAILED" in line(out, "    P. Porro")
    assert not list(world["save"].rglob("*.json"))                 # a failed answer is never kept


def test_empty_answers_are_counted_apart_from_failed(world):
    t = {k: (200, {}, []) for k in answers()}
    _, out, _ = run(world, table=t)
    sm = summary(out)
    assert sm["calls"]["empty"] == 6 and sm["calls"]["failed"] == 0
    assert "  NO ROWS fixture 1001 lineups" in out
    assert "appearance unread — lineups answered with no rows; players answered with no rows" in \
        line(out, "    P. Porro")


def test_api_errors_on_a_200_are_failed(world):
    t = dict(answers())
    t[("fixtures/players", "1001")] = (200, {"rateLimit": "too many"}, [])
    _, out, _ = run(world, table=t)
    assert any(ln.startswith("  FAILED fixture 1001 players: HTTP 200 errors") for ln in out)


def test_malformed_rows_are_counted_and_named_never_a_traceback(world):
    t = dict(answers())
    t[("fixtures/lineups", "1001")] = (200, {}, [5, {"team": {"id": 49}, "startXI": "x", "substitutes": [None]}])
    code, out, _ = run(world, table=t)
    assert code == 0
    sm = summary(out)
    assert sm["malformed"] == 5
    mal = line(out, "NOT THE PROVIDER'S SHAPE")
    for frag in ("lineups row 0: not an object", "startXI: not a list", "substitutes[0]: not a slot",
                 "players row 0: not an object", "players away[3]: not an entry"):
        assert frag in mal


def test_a_team_block_mapped_to_no_side_is_named(world):
    _, out, _ = run(world)
    assert "team blocks not mapped to a side: match 9238 (fixture 1002) players block 1 (team id 999)" in \
        line(out, "team blocks not mapped")


# ---- the cap and the kept payloads ----------------------------------------------------------------------------------

def test_the_cap_stops_cleanly_incomplete_and_a_rerun_resumes_from_the_kept_payloads(world):
    code, out, g = run(world, "--max-calls", "2")
    assert code == 0 and len(g.calls) == 2
    sm = summary(out)
    assert sm["incomplete"] is True
    assert "INCOMPLETE: the cap stopped 4 read(s)" in out[1]
    assert line(out, "INCOMPLETE: the call cap (2) left 4 read(s) unread").endswith(
        "match 9238 lineups, match 9238 players, match 9245 lineups, match 9245 players")
    assert "appearance unread — lineups capped" in line(out, "    A. Isak")
    code, out2, g2 = run(world)
    sm2 = summary(out2)
    assert sm2["calls"]["cached"] == 2 and sm2["calls"]["made"] == 4 and sm2["incomplete"] is False
    assert [c[1]["fixture"] for c in g2.calls] == ["1002", "1002", "1003", "1003"]
    code, out3, g3 = run(world)                                    # the failed and empty answers are asked again
    assert summary(out3)["calls"] == {"made": 2, "cached": 4, "failed": 1, "empty": 1, "cap": 100}


def test_save_under_data_is_refused_exit_2(world, monkeypatch):
    monkeypatch.setattr(rc, "ROOT", world["tmp"])                  # a broken refusal never writes into the checkout
    out = []
    target = world["tmp"] / "data" / "pl_injury_payloads_test"
    code = rc.main(["--exports", str(world["ex"]), "--db", str(world["db"]), "--save", str(target)],
                   echo=out.append, get=FakeGet(answers()))
    assert code == 2 and out[0].startswith("REFUSED: --save") and "under data/" in out[0]
    assert not target.exists()


def test_db_under_data_is_refused_exit_2_never_created(world, monkeypatch):
    monkeypatch.setattr(rc, "ROOT", world["tmp"])
    out = []
    target = world["tmp"] / "data" / "sp_backup_test_688.db"
    code = rc.main(["--exports", str(world["ex"]), "--db", str(target), "--save", str(world["save"])],
                   echo=out.append, get=FakeGet(answers()))
    assert code == 2 and out[0].startswith("REFUSED: --db") and not target.exists()


def test_a_missing_db_is_refused_exit_2_never_created(world):
    missing = world["tmp"] / "nope.db"
    out = []
    code = rc.main(["--exports", str(world["ex"]), "--db", str(missing), "--save", str(world["save"])],
                   echo=out.append, get=FakeGet(answers()))
    assert code == 2 and "REFUSED: no DB file" in out[0] and not missing.exists()


def test_a_missing_column_is_refused(world, tmp_path):
    from sqlalchemy import text
    eng = create_engine(f"sqlite:///{world['db']}")
    with eng.begin() as c:
        c.execute(text("ALTER TABLE injuries DROP COLUMN fixture_source_id"))
    eng.dispose()
    code, out, _ = run(world)
    assert code == 2 and out[0] == "REFUSED: columns fixture_source_id not in injuries (law 1)"


def test_no_key_and_no_fake_is_refused(world, monkeypatch):
    monkeypatch.setattr(rc, "_probe_get", lambda: (None, ""))
    out = []
    code = rc.main(["--exports", str(world["ex"]), "--db", str(world["db"]), "--save", str(world["save"])],
                   echo=out.append)
    assert code == 2 and out == ["REFUSED: no API_FOOTBALL_KEY (environment or .env)"]


def test_since_is_replaced_by_the_bounds_argparses_exit_2(world):
    """236 item 4: --since is gone (a second lower bound on the run start would conflict with --from)."""
    with pytest.raises(SystemExit) as e:
        run(world, "--since", "2026-10-20T18:42:00")
    assert e.value.code == 2


# ---- read-only ------------------------------------------------------------------------------------------------------

def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_a_fresh_wal_backup_copy_opens_immutable_and_leaves_no_sidecar(world, tmp_path):
    """Addendum 198 item 6(ii): --db opens a fresh WAL-mode .backup copy with immutable=1 beside mode=ro, reads it,
    and creates no -wal/-shm beside it."""
    import sqlite3
    live = tmp_path / "wal-live.db"
    with sqlite3.connect(world["db"]) as src, sqlite3.connect(live) as dst:
        src.backup(dst)
    with sqlite3.connect(live) as dst:
        dst.execute("PRAGMA journal_mode=WAL")
    d = tmp_path / "walcopy"
    d.mkdir()
    p = d / "sp.db"
    src = sqlite3.connect(live)
    bk = sqlite3.connect(p)
    src.backup(bk)
    bk.close()
    src.close()
    assert sorted(x.name for x in d.iterdir()) == ["sp.db"] and p.read_bytes()[18:20] == bytes([2, 2])
    before = _sha(p)
    with rc.open_db(rc.check_copy(str(p))) as (s, label):
        assert "(mode=ro + immutable=1 URI" in label
        s.execute(__import__("sqlalchemy").text("SELECT count(*) FROM matches")).scalar()
    assert sorted(x.name for x in d.iterdir()) == ["sp.db"] and _sha(p) == before


def test_the_db_copy_is_opened_read_only_bytes_unchanged(world):
    before = _sha(world["db"])
    code, out, _ = run(world)
    assert code == 0 and _sha(world["db"]) == before
    assert f"database --db {world['db'].resolve()} (mode=ro + immutable=1 URI, mode=ro&immutable=1" in out[0]
    assert f"closing files {world['ex'].resolve()} (--exports {world['ex']}; " in out[0]
    assert "machine role laptop (the machine this ran on, SP_EXPORTS_MIRROR_ROLE; never the copy's" in out[0]
    assert "LAPTOP's database" not in out[0]                                              # conftest pins the role
    assert not (world["db"].parent / "copy.db-journal").exists()


DB_REQUIRED = ("REFUSED: --db is required (236 item 4): a .backup copy outside data/, always a copy (the host run: "
               "the host's pulled backup; the laptop run: a fresh .backup copy of the laptop's file); the app's "
               "configured database is never read; nothing read")


@pytest.mark.parametrize("db", [None, "", "  "])
def test_236_4_db_missing_is_refused_exit_2_nothing_read(world, monkeypatch, db):
    """236 item 4: --db REQUIRED, always a copy: without it, exit 2 before anything is read (no closing file, no
    provider call, no payload folder, the configured database never opened)."""
    from src.db import database
    monkeypatch.setattr(database, "readonly_scope", lambda: pytest.fail("the configured database was opened"))
    monkeypatch.setattr(rc, "population", lambda *a, **k: pytest.fail("a closing file was read"))
    g = FakeGet(answers())
    out = []
    argv = ["--exports", str(world["ex"]), "--save", str(world["save"])] + ([] if db is None else ["--db", db])
    code = rc.main(argv, echo=out.append, get=g)
    assert code == 2 and out == [DB_REQUIRED] and g.calls == [] and not world["save"].exists()


@pytest.mark.parametrize("content", [b"not a sqlite file\n" * 64, b""], ids=["text", "empty"])
def test_236_4_a_db_that_is_not_a_readable_copy_is_refused_exit_2_nothing_read(world, monkeypatch, content):
    """A --db that exists but is no readable copy (not SQLite, or no matches table) is refused as qb_hold_receipt
    refuses it (mlb_pitchers_gate.open_ro before any read): exit 2, nothing read, never a traceback."""
    bad = world["tmp"] / "not_a_copy.db"
    bad.write_bytes(content)
    before = bad.read_bytes()
    monkeypatch.setattr(rc, "population", lambda *a, **k: pytest.fail("a closing file was read"))
    g = FakeGet(answers())
    out = []
    code = rc.main(["--exports", str(world["ex"]), "--db", str(bad), "--save", str(world["save"])],
                   echo=out.append, get=g)
    assert code == 2 and len(out) == 1
    assert out[0].startswith(f"REFUSED: --db {bad.resolve()}: cannot be read through a mode=ro + immutable=1 URI (")
    assert out[0].endswith("; nothing read") and not out[0].endswith("nothing read; nothing read")
    assert g.calls == [] and not world["save"].exists() and bad.read_bytes() == before


def test_236_4_the_configured_database_path_is_gone():
    assert "readonly_scope" not in Path(rc.__file__).read_text()
    import inspect
    assert list(inspect.signature(rc.open_db).parameters) == ["path"]


def test_the_script_imports_no_src_db_module_at_import():
    code = ("import importlib.util, sys; sys.path.insert(0, %r); "
            "s = importlib.util.spec_from_file_location('m', %r); m = importlib.util.module_from_spec(s); "
            "s.loader.exec_module(m); print([k for k in sys.modules if k.startswith('src.db')])"
            % (str(ROOT), str(ROOT / "scripts" / "pl_injury_classification_receipt.py")))
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(ROOT))
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "[]"


def test_a_db_match_id_of_another_game_is_never_used(world):
    """Ids are machine-local: a row whose id is another game's in the DB is found by its teams and kickoff."""
    ex = world["tmp"] / "ex2"
    closing(ex, "2026-10-24T16:30:00", [row(9300, "Chelsea", "Tottenham", "2026-10-24T16:30:00", ["E. Emegha"],
                                            [], 5, 0, S_CHE)])
    out = []
    rc.main(["--exports", str(ex), "--db", str(world["db"]), "--save", str(world["save"])], echo=out.append,
            get=FakeGet(answers()))
    assert "DB: by both team names and the row's kickoff (the match id is another game's) · match 9240" in \
        line(out, "  DB: ")


# ---- the ruling, item by item ---------------------------------------------------------------------------------------

def test_ruling_a_keys_printed_from_the_first_real_answer_before_the_rows(world):
    _, out, _ = run(world)
    k = out.index("PROVIDER KEYS (law 1, printed from the first real answer of each kind before any field is read):")
    assert k < out.index(line(out, "== match 9240"))
    assert out[k + 1] == "  first real answer: fixture 1001 (match 9240)"
    assert out[k + 2] == "  lineups: answer row keys ['coach', 'formation', 'startXI', 'substitutes', 'team']"
    assert "its player keys ['grid', 'id', 'name', 'number', 'pos']" in out[k + 4]
    assert "games keys ['minutes', 'number', 'position', 'substitute']" in out[k + 8]


def test_ruling_b_recoverable_only_on_the_exact_test_never_todays_list(world):
    _, out, _ = run(world)
    assert "recoverable (stored refreshed_at equals synced_at; counts match)" in line(out, "  HOME Chelsea")
    liv = line(out, "  HOME Liverpool")
    assert "not recoverable (overwritten at 2026-10-30T10:00:00.000000)" in liv
    assert "4 listed name(s) hidden by the 8-name cut" in liv
    assert "not recoverable (stored count 2, row count 3)" in line(out, "  AWAY Brighton")
    assert not any("TODAY" in ln for ln in out)                    # today's list is never substituted
    assert "· type '(not recoverable)' ·" in line(out, "    A. Isak")
    assert "    cross-check: the row's 5 name(s) are all in the stored list" in out
    sm = summary(out)
    assert (sm["sides_recoverable"], sm["sides_not_recoverable"], sm["sides_empty"]) == (3, 2, 1)
    assert "empty as consumed (count 0): nothing to classify" in line(out, "  HOME Sunderland")


def test_ruling_c_census_first_types_verbatim_no_other_bucket(world):
    _, out, _ = run(world)
    census = line(out, "CENSUS (ruling 1(c))")
    assert "'(no type stored)' 1 · 'Missing Fixture' 16 · 'Questionable' 2" in census
    assert out.index(census) < out.index("\nBY TYPE (verbatim; ruling 1(c)):") and out.index(census) < out.index(
        line(out, "== match"))
    assert rc.LABELS_NOTE in out[:6]
    assert "Out / doubtful / questionable are the NFL feed's words, not this one's." in rc.LABELS_NOTE
    sm = summary(out)
    assert set(sm["by_type"]) == {"Missing Fixture", "Questionable", "(no type stored)", "(not recoverable)"}
    assert sm["by_type"]["Questionable"] == {"started": 1, "came on": 1}


def test_ruling_d_stamp_age_one_bucket_and_the_entrys_fixture_age(world):
    _, out, _ = run(world)
    assert "stamp age 35 min (under 1 h)" in line(out, "  HOME Chelsea")
    sm = summary(out)
    assert set(sm["by_stamp_age"]) == {"under 1 h"}
    assert "an earlier fixture 6.2 d before (FAC, match 9200)" in line(out, "    D. Kulusevski")
    assert "fixture not stored (provider fixture 77777)" in line(out, "    W. Odobert")
    assert "· no fixture id stored ·" in line(out, "    X. Simons")
    assert "a later fixture 6.9 d after (PL, match 9300)" in line(out, "    M. Mudryk")
    assert "· this fixture ·" in line(out, "    P. Porro")
    assert set(sm["by_fixture_age"]) == {rc.THIS, rc.EARLIER, rc.LATER, rc.NOT_STORED, rc.NO_FIX_ID,
                                         rc.NOT_RECOVERABLE}


def test_ruling_e_the_guard_line_is_in_the_header(world):
    _, out, _ = run(world)
    assert rc.GUARD_COUNTS in out[:4]
    for frag in ("input_quality.injuries.<side>.count", "within 14 days of the sync, any type, one per name",
                 "It is not a count of players missing this fixture"):
        assert frag in rc.GUARD_COUNTS


def test_ruling_f_the_worked_cases_and_the_not_listed_class(world):
    _, out, _ = run(world)
    sm = summary(out)
    w = sm["worked"]
    assert set(w) == {"1 Isak", "2 João Pedro", "3 Porro", "3 Kulusevski", "4 Calvert-Lewin", "4 Stach", "4 Okafor"}
    assert w["2 João Pedro"].startswith("João Pedro (home): on no list; not listed, did not appear — João Pedro")
    assert "came on" in w["1 Isak"] and "type '(not recoverable)'" in w["1 Isak"]
    assert "started" in w["3 Porro"] and rc.DNP_ABSENT in w["3 Kulusevski"]
    assert rc.AMBIGUOUS in w["4 Okafor"]
    assert line(out, "  WORKED CASE 2 João Pedro").startswith("  WORKED CASE 2 João Pedro: João Pedro (home)")
    nl = line(out, "    not listed, did not appear 1: ")
    assert nl.endswith("João Pedro")                              # Gusto came on; Emegha is listed
    assert "    not listed, did not appear 1: R. Mundle" in out             # a side empty as consumed
    assert sm["not_listed_did_not_appear"] == 2                   # João Pedro (Chelsea), Mundle (Sunderland)
    assert sm["not_listed_unread_sides"] == 2                     # Brighton (no block), Leeds (players block malformed)
    assert sm["not_listed_side_list_cut"] == 1                    # Salah: Liverpool's list cut and not recoverable
    assert ("    not listed, did not appear 1 (4 listed name(s) hidden by the cut: some may be among these; counted "
            "apart): Mohamed Salah") in out
    assert ("    not listed, appearance unread (minutes not all read: a member of the side's players answer is missing "
            "or not the provider's shape)") in out


def test_ruling_f_not_listed_is_unread_until_the_fixture_is_read(world):
    t = {k: (500, {}, []) for k in answers()}
    _, out, _ = run(world, table=t)
    sm = summary(out)
    assert sm["not_listed_did_not_appear"] == 0 and sm["not_listed_unread_sides"] == 6
    assert sm["worked"]["2 João Pedro"] == "João Pedro (home): on no list; not listed, appearance unread"
    assert "    not listed, appearance unread (the fixture was not read for this side)" in out


# ---- names ----------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("listed,provider,how", [
    ("A. Isak", "Alexander Isak", "initial form"),
    ("Joao Pedro", "João Pedro", "exact"),
    ("João Pedro", "J. Pedro", "initial form"),
    ("E. J. Kroupi", "Eli Junior Kroupi", "initial form"),
    ("N. O'Reilly", "Nico O’Reilly", "initial form"),
    ("D. Calvert-Lewin", "Dominic Calvert Lewin", "initial form"),
    ("A. Isak", "B. Isak", "unmatched"),
    ("D. James", "Daniel James", "initial form"),
])
def test_name_matching(listed, provider, how):
    assert rc.name_match(listed, [{"names": {provider}}])[0] == how


def test_two_candidates_are_ambiguous_never_a_guess():
    how, cs = rc.name_match("D. James", [{"names": {"Daniel James"}}, {"names": {"Dan James"}}])
    assert how == "ambiguous" and len(cs) == 2


# ---- review round: the not-listed class needs the minutes, partial answers, off-shape values ------------------------

def _block(out, start, end):
    i = out.index(line(out, start))
    j = out.index(line(out, end)) if end else len(out)
    return out[i:j]


def test_lineups_read_players_failed_is_not_listed_unread_never_a_measured_0(world):
    """Ruling 1(f): with /fixtures/players FAILED and /fixtures/lineups read, the bench's minutes are unread: the side
    prints 'not listed, appearance unread' with its unlisted bench names, never 'not listed, did not appear 0'."""
    t = dict(answers())
    t[("fixtures/players", "1001")] = (500, {}, [])
    _, out, _ = run(world, table=t)
    blk = _block(out, "== match 9240", "== match 9238")
    assert not any(ln.startswith("    " + rc.NOT_LISTED_DNP) for ln in blk)
    assert ("    not listed, appearance unread (minutes not read: /fixtures/players the read FAILED): unlisted, "
            "minutes not read: João Pedro, M. Gusto") in blk
    assert "    not listed, appearance unread (minutes not read: /fixtures/players the read FAILED)" in blk  # Spurs
    for n in ("    X. Simons", "    M. Mudryk"):
        assert "appearance unread — appearance unread (on the bench; minutes not read)" in line(blk, n)
    sm = summary(out)
    assert sm["not_listed_unread_sides"] == 4 and sm["not_listed_did_not_appear"] == 1        # Mundle only
    assert sm["worked"]["2 João Pedro"].startswith("João Pedro (home): on no list; not listed, appearance unread")


def test_players_capped_after_lineups_is_not_listed_unread(world):
    _, out, _ = run(world, "--max-calls", "1")
    blk = _block(out, "== match 9240", "== match 9238")
    assert "    not listed, appearance unread (minutes not read: /fixtures/players capped (the call cap stopped the " \
           "reads)): unlisted, minutes not read: João Pedro, M. Gusto" in blk
    assert summary(out)["not_listed_did_not_appear"] == 0


def _sq(lineups=None, players=None):
    mal = []
    return rc.squad(lineups, players, {"1"}, {"2"}, "m", mal), mal


@pytest.mark.parametrize("block,why", [
    ({"team": {"id": 1}, "startX1": [{"player": {"id": 5, "name": "A. Isak"}}], "substitutes": []},
     "startXI: missing"),
    ({"team": {"id": 1}, "startXI": "x", "substitutes": []}, "startXI: not a list"),
    ({"team": {"id": 1}, "startXI": [{"player": None}, {"player": {"id": 6, "name": "B. Other"}}],
      "substitutes": []}, "startXI[0]: not a slot"),
])
def test_a_malformed_member_never_makes_a_listed_name_absent(block, why):
    sq, mal = _sq(lineups=[block])
    assert sq["home"]["lineups"] is False and sq["home"]["partial"] == ["lineups"]
    assert any(why in m for m in mal)
    cls, det = rc.classify("A. Isak", sq["home"], None)
    assert cls == rc.UNREAD and "may hide him" in det


def test_a_malformed_players_member_makes_the_sides_not_listed_unread(world):
    t = dict(answers())
    t[("fixtures/players", "1001")] = (200, {}, [
        {"team": {"id": 49}, "players": [pentry(1, "E. Emegha", 90, False), pentry(10, "João Pedro", None, True), 7]},
        {"team": {"id": 47}, "players": [pentry(20, "Pedro Porro", 90, False)]}])
    _, out, _ = run(world, table=t)
    blk = _block(out, "== match 9240", "== match 9238")
    che = blk[:blk.index(line(blk, "  AWAY Tottenham"))]
    assert not any(ln.startswith("    " + rc.NOT_LISTED_DNP) for ln in che)
    assert any(ln.startswith("    not listed, appearance unread (minutes not all read") for ln in che)
    assert "    not listed, did not appear 0: none" in blk                # Spurs: its block read in full, a real 0


@pytest.mark.parametrize("minutes", ["90", 90.0, True])
def test_minutes_not_an_int_or_null_is_unread_never_did_not_appear(minutes):
    games = {"minutes": minutes, "substitute": False}
    sq, mal = _sq(players=[{"team": {"id": 1}, "players": [
        {"player": {"id": 5, "name": "A. Isak"}, "statistics": [{"games": games}]}]}])
    cls, det = rc.classify("A. Isak", sq["home"], None)
    assert cls == rc.UNREAD and "not the provider's shape" in det
    assert any("games.minutes" in m for m in mal) and sq["home"]["partial"] == ["players"]


def test_724_an_empty_players_block_is_a_squad_unread_never_a_known_one():
    """#724 item 1 (ARCHITECT 2026-10-29, addendum 176 item 3(a)): a team block with players: [] read as a full read,
    so a listed name classed "did not appear (absent)" and the not-listed line printed a measured 0. Now the side's
    players kind is partial, named, and the name reads unread."""
    sq, mal = _sq(players=[{"team": {"id": 1}, "players": []}])
    assert sq["home"]["players"] is False and sq["home"]["partial"] == ["players"]
    assert "m players home: players is an empty list" in mal
    cls, det = rc.classify("A. Isak", sq["home"], None)
    assert cls == rc.UNREAD and "absent" not in cls


def test_724_an_empty_players_block_prints_not_listed_unread_never_a_measured_0(world):
    t = dict(answers())
    t[("fixtures/players", "1001")] = (200, {}, [
        {"team": {"id": 49}, "players": []},
        {"team": {"id": 47}, "players": [pentry(20, "Pedro Porro", 90, False)]}])
    _, out, _ = run(world, table=t)
    blk = _block(out, "== match 9240", "== match 9238")
    che = blk[:blk.index(line(blk, "  AWAY Tottenham"))]
    assert not any(ln.startswith("    " + rc.NOT_LISTED_DNP) for ln in che)
    assert not any(rc.DNP_SQUAD in ln or "(absent)" in ln for ln in che)
    assert "    not listed, did not appear 0: none" in blk                # Spurs: its block read in full, a real 0


def test_724_a_missing_minutes_key_is_a_member_not_the_providers_shape_never_a_null():
    """#724 item 2: g.get("minutes") gave None for an absent key as for a JSON null, so the member classed "did not
    appear (in the squad answer, no minutes)". Now the key is required: counted, the side partial, the name unread.
    An explicit null still reads as before (in the squad answer, no minutes)."""
    sq, mal = _sq(players=[{"team": {"id": 1}, "players": [
        {"player": {"id": 5, "name": "A. Isak"}, "statistics": [{"games": {"substitute": True}}]}]}])
    cls, det = rc.classify("A. Isak", sq["home"], None)
    assert cls == rc.UNREAD and "minutes absent not the provider's shape" in cls + det
    assert "m players home[0]: games has no minutes key" in mal and sq["home"]["partial"] == ["players"]
    sq, mal = _sq(players=[{"team": {"id": 1}, "players": [
        {"player": {"id": 5, "name": "A. Isak"}, "statistics": [{"games": {"minutes": None, "substitute": True}}]}]}])
    assert rc.classify("A. Isak", sq["home"], None)[0] == rc.DNP_SQUAD and mal == [] and sq["home"]["players"]


def test_an_unhashable_player_id_is_counted_never_a_traceback(world):
    sq, mal = _sq(lineups=[{"team": {"id": 1}, "startXI": [{"player": {"id": [5], "name": "A"}}], "substitutes": []}],
                  players=[{"team": {"id": 2}, "players": [{"player": {"id": {"a": 1}, "name": "B"},
                                                            "statistics": [{"games": {"minutes": 9}}]}]}])
    assert any("player id is a list" in m for m in mal) and any("player id is a dict" in m for m in mal)
    assert sq["home"]["partial"] == ["lineups"] and sq["away"]["partial"] == ["players"]
    t = dict(answers())
    t[("fixtures/lineups", "1001")] = (200, {}, [{"team": {"id": 49}, "startXI": [{"player": {"id": [1], "name": "X"}}],
                                                  "substitutes": []}])
    code, out, _ = run(world, table=t)
    assert code == 0 and "player id is a list" in line(out, "NOT THE PROVIDER'S SHAPE")


def test_a_provider_body_that_raises_or_is_not_a_list_is_failed(world):
    class Raising(FakeGet):
        def __call__(self, path, **params):
            if params.get("fixture") == "1001" and path == "fixtures/lineups":
                raise AttributeError("'list' object has no attribute 'get'")
            if params.get("fixture") == "1001":
                return 200, {}, "a string"
            return super().__call__(path, **params)
    code, out, _ = run(world, get=Raising(answers()))
    assert code == 0
    assert "  FAILED fixture 1001 lineups: the provider body was not readable (AttributeError: 'list' object has no " \
           "attribute 'get')" in out
    assert "  FAILED fixture 1001 players: the response is a str, not a list" in out
    assert summary(out)["calls"]["failed"] == 3                   # and 1002 lineups
    assert not (world["save"] / "1001").exists()


def test_a_kept_payload_not_a_list_is_asked_again(world):
    (world["save"] / "1001").mkdir(parents=True)
    (world["save"] / "1001" / "lineups.json").write_text("null")
    _, out, g = run(world)
    sm = summary(out)
    assert sm["calls"]["cached"] == 0 and sm["calls"]["made"] == 6
    assert json.loads((world["save"] / "1001" / "lineups.json").read_text())   # replaced by the real answer


def test_the_db_copy_refuses_a_write(world):
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError
    before = _sha(world["db"])
    with rc.open_db(rc.check_copy(str(world["db"]))) as (s, _label):
        with pytest.raises(OperationalError, match="readonly"):
            s.execute(text("CREATE TABLE t688 (x INTEGER)"))
    assert _sha(world["db"]) == before


def _liv_only(world, names, iq_count=True):
    ex = world["tmp"] / "ex_liv"
    r = row(9238, "Liverpool", "Brighton", "2026-10-25T14:00:00", names, ["E. Ferguson"], 12, 1, S_LIV)
    if not iq_count:
        del r["input_quality"]["injuries"]["home"]["count"]
    closing(ex, "2026-10-25T14:00:00", [r])
    out = []
    rc.main(["--exports", str(ex), "--db", str(world["db"]), "--save", str(world["save"])], echo=out.append,
            get=FakeGet(answers()))
    return out


def test_a_worked_case_on_a_cut_list_never_says_not_listed(world):
    names = [n for n in LIV if n != "A. Isak"] + ["J. Gomez"]
    out = _liv_only(world, names)
    w = summary(out)["worked"]["1 Isak"]
    assert w.startswith("A. Isak (home): on none of the 8 names shown (4 hidden by the 8-name cut and the list not "
                        "recoverable): listed or not is UNKNOWN; appearance: came on — Alexander Isak")
    assert "not listed" not in w


def test_a_row_with_no_count_is_hidden_unknown_never_0(world):
    out = _liv_only(world, LIV, iq_count=False)
    liv = line(out, "  HOME Liverpool")
    assert "count None (injuries.home_count 12)" in liv
    assert "listed names hidden by the 8-name cut UNKNOWN (no input_quality count" in liv
    assert ("    not listed, did not appear 1 (the listed count unknown: some may be among these; counted apart): "
            "Mohamed Salah") in out
    sm = summary(out)
    assert sm["not_listed_did_not_appear"] == 0 and sm["not_listed_side_list_cut"] == 1


def test_a_row_with_no_count_and_no_read_still_prints_not_listed_unread(world):
    ex = world["tmp"] / "ex_liv"
    r = row(9238, "Liverpool", "Brighton", "2026-10-25T14:00:00", LIV, ["E. Ferguson"], 12, 1, S_LIV)
    del r["input_quality"]["injuries"]["home"]["count"]
    closing(ex, "2026-10-25T14:00:00", [r])
    out = []
    rc.main(["--exports", str(ex), "--db", str(world["db"]), "--save", str(world["save"])], echo=out.append,
            get=FakeGet({k: (500, {}, []) for k in answers()}))
    assert summary(out)["not_listed_unread_sides"] == 2


def test_a_worked_case_with_no_row_in_the_population_is_printed_missing(world):
    out = _liv_only(world, LIV)
    msg = "no PL closing row for Chelsea v Tottenham on 2026-10-24 in the population"
    assert f"WORKED CASE 2 João Pedro: {msg}" in out
    w = summary(out)["worked"]
    assert w["2 João Pedro"] == msg and w["4 Okafor"].startswith("no PL closing row for Sunderland v Leeds")
    assert "came on" in w["1 Isak"]


def test_the_header_names_the_sqlite_sidecars(world):
    _, out, _ = run(world)
    assert rc.SIDECARS in out[:8] and "creates <file>-wal and <file>-shm" in rc.SIDECARS


def test_codex_722_a_lineup_only_bench_name_on_a_side_read_in_full_is_unread_never_dropped(world):
    """Codex on #722: a well-formed /fixtures/players block that holds no entry for a substitute of /fixtures/lineups
    leaves the side read in full, but that name's minutes are unread: it prints as 'not listed, appearance unread'
    beside the measured did-not-appear count, and is counted apart, never dropped from both lists."""
    t = dict(answers())
    t[("fixtures/players", "1001")] = (200, {}, [
        {"team": {"id": int(TEAMS["Chelsea"])}, "players": [pentry(1, "E. Emegha", 90, False),
                                                            pentry(10, "João Pedro", None, True)]},   # no M. Gusto
        {"team": {"id": int(TEAMS["Tottenham"])}, "players": [pentry(20, "Pedro Porro", 90, False),
                                                              pentry(21, "X. Simons", 15, True),
                                                              pentry(22, "M. Mudryk", None, True)]}])
    _, out, _ = run(world, table=t)
    blk = _block(out, "== match 9240", "== match 9238")
    che = blk[:blk.index(line(blk, "  AWAY Tottenham"))]
    assert "    not listed, did not appear 1: João Pedro" in che
    assert ("    not listed, appearance unread 1 (in /fixtures/lineups, no minutes entry in the players answer): "
            "M. Gusto") in che
    sm = summary(out)
    assert sm["not_listed_unread_on_read_sides"] == 1
    assert "on a side read in full, in the lineups with no minutes entry (unread, counted apart) 1" in line(
        out, "NOT LISTED (ruling 1(f)): ")


def test_codex_722_more_initials_than_given_names_never_match():
    """Codex on #722: "A. X. Smith" names no "Adam Smith" (the X is unmatched); "A. Smith" still does."""
    assert rc.name_match("A. X. Smith", [{"names": {"Adam Smith"}}])[0] == "unmatched"
    assert rc.name_match("A. Smith", [{"names": {"Adam Smith"}}])[0] == "initial form"
    assert rc.name_match("E. J. Kroupi", [{"names": {"Eli Junior Kroupi"}}])[0] == "initial form"


def test_codex_722_a_match_id_with_the_teams_but_another_kickoff_is_never_used(world):
    """Codex on #722: the id is machine-local and the same two clubs meet twice a season: a stored match with the
    row's teams but another kickoff is not the row's game; the teams-and-kickoff lookup decides (here: none stored)."""
    ex = world["tmp"] / "ex3"
    closing(ex, "2026-10-24T16:30:00", [row(9240, "Chelsea", "Tottenham", "2027-03-14T16:30:00", ["E. Emegha"],
                                            [], 5, 0, S_CHE)])
    out = []
    rc.main(["--exports", str(ex), "--db", str(world["db"]), "--save", str(world["save"])], echo=out.append,
            get=FakeGet(answers()))
    assert "DB: not in the database" in line(out, "  DB: ")


# ---- the source after the cutover (ARCHITECT 2026-11-03, addendum 230 item 2(c)) ------------------------------------

def _run_on(w, ex, table=None, db=None):
    out = []
    code = rc.main(["--exports", str(ex), "--db", str(db or w["db"]), "--save", str(w["save"])], echo=out.append,
                   get=FakeGet(table if table is not None else answers()))
    return code, out


def _move_into_dated(ex: Path) -> None:
    """The world's flat closing files moved into the mirror's layout, <ex>/<YYYY-MM-DD>/ by each file's run day."""
    for f in sorted(ex.glob("closing_*.json")):
        day = ex / f.name.split("_")[2][:10]
        day.mkdir(exist_ok=True)
        f.rename(day / f.name)


def test_230_2c_a_flat_host_directory_is_read(world):
    """exports/host/ (the laptop's cumulative pull: flat, 232 item 2(c)) is read as a flat directory."""
    host = world["tmp"] / "pull" / "exports" / "host"
    write_exports(host)
    code, out = _run_on(world, host)
    assert code == 0
    sm = summary(out)
    assert sm["matches"] == [9240, 9238, 9245] and sm["closing_files"] == 6 and sm["dated_folders"] == 0
    assert sm["exports_dir"] == str(host.resolve())
    assert f"closing files {host.resolve()} (--exports {host}; closing_*.json there and in its dated folders " \
           "<YYYY-MM-DD>/ 0, never latest/" in out[0]
    assert "closing_SOCCER_2026-10-25T1400Z.json, git_sha f0e4cbf3; earlier runs 1" in line(out, "== match 9238")


def test_230_2c_a_tree_of_dated_folders_is_read_alike(world):
    """The mirror's host/<YYYY-MM-DD>/closing_*.json: the same rows as the flat directory, each file printed with its
    folder."""
    host = world["tmp"] / "mirror" / "host"
    write_exports(host)
    _move_into_dated(host)
    assert not list(host.glob("closing_*.json"))
    code, out = _run_on(world, host)
    assert code == 0
    sm = summary(out)
    assert sm["matches"] == [9240, 9238, 9245] and sm["closing_files"] == 6 and sm["dated_folders"] == 3
    assert "in its dated folders <YYYY-MM-DD>/ 3, never latest/" in out[0]
    assert "(2026-10-25/closing_SOCCER_2026-10-25T1400Z.json, git_sha f0e4cbf3; earlier runs 1)" in \
        line(out, "== match 9238")
    assert "the rows' runs 2026-10-24T16:30Z to 2026-10-25T16:30Z" in out[0]


def test_230_2c_latest_and_other_subfolders_are_never_read(world):
    """A row only in latest/ (or in a folder not named YYYY-MM-DD) is never counted."""
    host = world["tmp"] / "mirror" / "host"
    write_exports(host)
    _move_into_dated(host)
    for sub in ("latest", "2026-11", "misc"):
        closing(host / sub, "2026-11-02T13:00:00", [row(9400, "Newcastle", "Everton", "2026-11-02T14:00:00",
                                                        ["W. Osula"], [], 5, 0, "2026-11-02T12:25:00")])
    code, out = _run_on(world, host)
    assert code == 0
    sm = summary(out)
    assert 9400 not in sm["matches"] and sm["closing_files"] == 6 and sm["dated_folders"] == 3
    assert not [ln for ln in out if "match 9400" in ln]


def test_230_2c_a_name_in_two_dated_folders_is_one_run_never_an_earlier_one(world):
    host = world["tmp"] / "mirror" / "host"
    write_exports(host)
    _move_into_dated(host)
    (host / "2026-10-26").mkdir()
    f = host / "2026-10-25" / "closing_SOCCER_2026-10-25T1630Z.json"
    (host / "2026-10-26" / f.name).write_text(f.read_text())
    code, out = _run_on(world, host)
    assert code == 0
    sm = summary(out)
    assert sm["repeated_names"] == [f.name] and sm["closing_files"] == 7
    assert f"names in more than one folder 1 (each copy read; one run, never an earlier run): {f.name}" in out[0]
    assert f"(2026-10-26/{f.name}, git_sha f0e4cbf3; earlier runs 0)" in line(out, "== match 9245")


def test_230_2c_a_latest_folder_as_exports_or_behind_a_dated_name_is_refused(world):
    """'never a latest/ folder' (232 item 2(c)): --exports at host/latest/ (by name or through a symlink), or a
    dated-named symlink into latest/, is refused before any read."""
    host = world["tmp"] / "mirror" / "host"
    write_exports(host)
    _move_into_dated(host)
    closing(host / "latest", "2026-11-02T13:00:00", [row(9401, "Newcastle", "Everton", "2026-11-02T14:00:00",
                                                         ["W. Osula"], [], 5, 0, "2026-11-02T12:25:00")])
    link = world["tmp"] / "newest"
    link.symlink_to(host / "latest", target_is_directory=True)
    for ex in (host / "latest", link):
        code, out = _run_on(world, ex)
        assert code == 2 and len(out) == 1 and out[0].startswith(f"REFUSED: --exports {ex}: a latest/ folder")
    (host / "2026-11-02").symlink_to(host / "latest", target_is_directory=True)
    code, out = _run_on(world, host)
    assert code == 2 and out == [f"REFUSED: --exports {host}: the dated folder 2026-11-02/ resolves to "
                                 f"{(host / 'latest').resolve()}, a latest/ folder; latest/ is never read; nothing read"]


def test_230_2c_exports_not_a_directory_is_refused_nothing_read(world):
    a_file = world["tmp"] / "closing_SOCCER_2026-10-25T1400Z.json"
    a_file.write_text("{}")
    for ex in (world["tmp"] / "no-such-dir", a_file):
        code, out = _run_on(world, ex)
        assert code == 2 and out == [f"REFUSED: --exports {ex}: not a directory; nothing read"]


def test_230_2c_the_header_names_the_directory_the_copy_and_the_rulings(world):
    host = world["tmp"] / "mirror" / "host"
    write_exports(host)
    _move_into_dated(host)
    code, out = _run_on(world, host)
    assert code == 0
    assert out[0].startswith("PL INJURY CLASSIFICATION RECEIPT (ARCHITECT 2026-10-27, addendum 171 item 1; #688) · "
                             f"READ-ONLY · database --db {world['db'].resolve()} (mode=ro + immutable=1 URI")
    assert f"closing files {host.resolve()} (--exports {host}; " in out[0]
    assert ("THE SOURCE AFTER THE CUTOVER (ARCHITECT 2026-11-03 09:00 ET, addendum 230 item 2(c), verbatim): "
            f"\"{rc.RULING_230_2C}\"") in out
    assert "the \"host/ is never read\" rule was the pre-cutover laptop's; it inverts" in rc.RULING_230_2C
    assert line(out, "THE SOURCE READ (ARCHITECT 2026-11-03 11:10 ET, addendum 232 item 2(c)").endswith(
        "\"The receipt reads a flat directory of closing_*.json OR a tree of dated folders alike (never a latest/ "
        "folder), so the mirror checkout still works as a second source if ever needed.\"")
    assert line(out, "THE COPY (ARCHITECT 2026-11-03 08:40 ET, addendum 229 item 1's standing rule, verbatim in part)").endswith(
        "a leagues or PL-availability read runs on the host's pulled backup, never the laptop's database; the "
        "console names the copy.\"")
    assert "a mismatch is the operator's error" in line(out, "THE PAIRING: the header names the closing-file directory")
    assert "(the one reader; host/ is never read)" not in rc.__doc__ and rc.__doc__.count("host/ is never read") == 1


def test_230_2c_a_copy_with_a_sidecar_is_refused(world):
    wal = world["db"].with_name(world["db"].name + "-wal")
    wal.write_bytes(b"")
    code, out = _run_on(world, world["ex"])
    assert code == 2 and out[0].startswith(f"REFUSED: --db {world['db'].resolve()} has a -wal sidecar")


def test_230_2c_the_app_s_configured_database_as_db_is_refused(world, monkeypatch):
    from src.walters import mlb_pitchers_gate as mp
    monkeypatch.setattr(mp, "_app_db", lambda: world["db"].resolve())
    code, out = _run_on(world, world["ex"])
    assert code == 2 and out[0].startswith("REFUSED: --db ") and "the app's configured database" in out[0]


def xi(base, *slots):
    """An XI of eleven named starters: the given slots, then fillers no listed name matches."""
    return [*slots, *(slot(base + k, f"Filler Zz{base + k}") for k in range(11 - len(slots)))]


def _add_newcastle_everton(db: Path, stamp: str) -> None:
    """The Osula instance's shape (225 item 4): Newcastle v Everton 2026-11-02, five listed for Newcastle, one for
    Everton, each side's stored list stamped as the closing row consumed it (synthetic ids)."""
    from src.db.schema import Competition, Injury, Match, MatchStatus, Sport, Team
    eng = create_engine(f"sqlite:///{db}")
    with Session(eng) as s:
        pl = s.query(Competition).filter_by(code="PL").one()
        new = Team(sport=Sport.SOCCER, name="Newcastle", external_ids={"api_football": "34"})
        s.add(new)
        s.flush()
        eve = s.query(Team).filter_by(name="Everton").one()
        s.add(Match(id=9400, sport=Sport.SOCCER, competition_id=pl.id, season="2026/27",
                    utc_date=_dt("2026-11-02T14:00:00"), status=MatchStatus.FINISHED, home_team_id=new.id,
                    away_team_id=eve.id, home_score=1, away_score=1, external_ids={"api_football": "1600"}))
        for n in ("T. Livramento", "W. Osula", "M. Jaouen", "A. Fernandez-Pardo", "L. Miley"):
            s.add(Injury(team_id=new.id, player_name=n, type="Missing Fixture", reason="Injury",
                         fixture_source_id="1600", refreshed_at=_dt(stamp)))
        s.add(Injury(team_id=eve.id, player_name="J. Grealish", type="Missing Fixture", reason="Injury",
                     fixture_source_id="1600", refreshed_at=_dt(stamp)))
        s.commit()
    eng.dispose()


def test_225_4_the_osula_shaped_row_listed_missing_who_started_classes_started(world):
    """225 item 4's shape on the host's dated tree: a player listed as missing on the closing row who STARTED (in the
    provider's startXI) classes "started"; the other listed names that did not appear class as today."""
    stamp = "2026-11-02T13:25:00"
    _add_newcastle_everton(world["db"], stamp)
    host = world["tmp"] / "mirror" / "host"
    new_names = ["T. Livramento", "W. Osula", "M. Jaouen", "A. Fernandez-Pardo", "L. Miley"]
    closing(host / "2026-11-02", "2026-11-02T13:30:00",
            [row(9400, "Newcastle", "Everton", "2026-11-02T14:00:00", new_names, ["J. Grealish"], 5, 1, stamp,
                 call="PASS")])
    t = dict(answers())
    nu = {"id": 34, "name": "Newcastle", "logo": ""}
    ev = {"id": int(TEAMS["Everton"]), "name": "Everton", "logo": ""}
    t[("fixtures/lineups", "1600")] = (200, {}, [
        {"team": nu, "formation": "4-3-3", "coach": {}, "startXI": xi(600, slot(61, "William Osula")),
         "substitutes": [slot(62, "Joe Willock")]},
        {"team": ev, "formation": "4-2-3-1", "coach": {}, "startXI": xi(700), "substitutes": []}])
    t[("fixtures/players", "1600")] = (200, {}, [
        {"team": nu, "players": [pentry(61, "William Osula", 90, False), pentry(62, "Joe Willock", None, True)]},
        {"team": ev, "players": [pentry(701, "Filler Zz701", 90, False)]}])
    code, out = _run_on(world, host, table=t)
    assert code == 0
    sm = summary(out)
    assert sm["matches"] == [9400]
    assert "(2026-11-02/closing_SOCCER_2026-11-02T1330Z.json, git_sha f0e4cbf3; earlier runs 0)" in \
        line(out, "== match 9400")
    assert "recoverable" in line(out, "  HOME Newcastle: count 5")
    osula = line(out, "    W. Osula")
    assert "type 'Missing Fixture'" in osula and "· this fixture · started — William Osula (initial form" in osula
    for n in ("T. Livramento", "M. Jaouen", "A. Fernandez-Pardo", "L. Miley"):
        assert rc.DNP_ABSENT in line(out, f"    {n}")
    assert rc.DNP_ABSENT in line(out, "    J. Grealish")
    assert sm["by_type"]["Missing Fixture"][rc.STARTED] == 1


# ---- 236 item 4: the closing run's start bounded as #810's qb_hold_receipt ----------------------------------------

BOUND = "2026-10-26T12:00:00Z"


def _host_tree(w) -> Path:
    """A host directory: a P8 rehearsal closing (2026-10-25T23:45Z, before the cutover), a closing EXACTLY at the
    bound, one after it, and a row with no run start (no closing block start, no stamp in the name)."""
    host = w["tmp"] / "pull" / "exports" / "host"
    lee = ["M. Joseph", "J. Rodon", "D. James", "D. Calvert-Lewin", "N. Okafor", "A. Stach"]
    closing(host, "2026-10-25T23:45:00", [row(9240, "Chelsea", "Tottenham", "2026-10-24T16:30:00",
                                              ["E. Emegha"], [], 5, 8, S_CHE, call="PLAY")])          # rehearsal
    closing(host, "2026-10-26T12:00:00", [row(9238, "Liverpool", "Brighton", "2026-10-25T14:00:00", LIV,
                                              ["E. Ferguson", "Y. Minteh", "K. Mitoma"], 12, 3, S_LIV)])  # at it
    closing(host, "2026-10-26T13:00:00", [row(9245, "Sunderland", "Leeds", "2026-10-25T16:30:00", [], lee, 0, 6,
                                              S_SUN)])
    doc = {"git_sha": "abc1234", "predictions": [row(9300, "Everton", "Coventry", "2026-10-31T15:00:00", [], [], 0,
                                                     0, None)], "closing": {"family": "SOCCER"}}
    (host / "closing_SOCCER_nostamp.json").write_text(json.dumps(doc))
    return host


def _bounded(w, ex, *bound):
    out = []
    g = FakeGet(answers())
    code = rc.main(["--exports", str(ex), "--db", str(w["db"]), "--save", str(w["save"]), *bound],
                   echo=out.append, get=g)
    return code, out, g


def test_236_4_the_host_run_excludes_the_rehearsal_closing_by_from_and_names_it(world):
    host = _host_tree(world)
    code, out, _ = _bounded(world, host, "--from", BOUND)
    assert code == 0
    sm = summary(out)
    assert sm["matches"] == [9238, 9245]                        # the rehearsal-era 9240 left out by the bound
    assert sm["run"] == {"era": "host", "label": f"host era, runs from {BOUND}", "from": BOUND, "through": None}
    assert f"this run: host era, runs from {BOUND} · rows 2 of 4 " in out[0]
    b = line(out, "BOUND (236 item 4: #810's bound, 232 item 2(b);")
    assert f"this run: host era, runs from {BOUND} · --from {BOUND} · --through —" in b
    assert ("excluded by the bound (not read, not classified, not counted): PL closing rows 1, from 1 run(s) "
            "(closing files 1), PL games left with no row in the bound 1 (named below)") in b
    assert ("  outside the bound (not counted): match 9240 Chelsea v Tottenham (run 2026-10-25T23:45Z, "
            "closing_SOCCER_2026-10-25T2345Z.json, desk PLAY)") in out
    assert sm["bound"]["outside"] == {"runs": 1, "files": 1, "rows": 1, "games": 1, "named": [
        "match 9240 Chelsea v Tottenham (run 2026-10-25T23:45Z, closing_SOCCER_2026-10-25T2345Z.json, desk PLAY)"]}
    assert not [ln for ln in out if ln.startswith("== match 9240")]


def test_236_4_a_run_start_exactly_at_the_bound_is_counted_by_from(world):
    host = _host_tree(world)
    code, out, _ = _bounded(world, host, "--from", BOUND)
    assert code == 0 and 9238 in summary(out)["matches"]
    assert "(closing_SOCCER_2026-10-26T1200Z.json, git_sha f0e4cbf3; earlier runs 0)" in line(out, "== match 9238")


def test_236_4_the_laptop_run_is_through_the_bound_exclusive(world):
    host = _host_tree(world)
    code, out, _ = _bounded(world, host, "--through", BOUND)
    assert code == 0
    sm = summary(out)
    assert sm["matches"] == [9240]                              # exactly at the bound is the host era's, not here
    assert sm["run"]["era"] == "laptop" and sm["run"]["label"] == f"laptop era, runs through {BOUND}"
    assert sm["bound"]["outside"]["games"] == 2 and sm["bound"]["outside"]["runs"] == 2
    named = [ln for ln in out if ln.startswith("  outside the bound (not counted): ")]
    assert [ln.split(" (run ")[0][len("  outside the bound (not counted): "):] for ln in named] == [
        "match 9238 Liverpool v Brighton", "match 9245 Sunderland v Leeds"]


def test_236_4_a_row_with_no_run_start_is_outside_every_bound_named(world):
    host = _host_tree(world)
    code, out, _ = _bounded(world, host, "--from", BOUND)
    assert code == 0
    u = line(out, "RUN START UNKNOWN, OUTSIDE EVERY BOUND (232 item 2(b); law 4")
    assert "PL closing rows 1 (closing files 1), PL games left with no row in the bound 1 (named below)" in u
    assert ("  run start unknown, outside every bound (not counted): match 9300 Everton v Coventry (run start "
            "unknown, closing_SOCCER_nostamp.json, desk PASS)") in out
    assert 9300 not in summary(out)["matches"]


def test_236_4_an_unbounded_run_says_so_and_keeps_the_floor(world):
    code, out, _ = run(world)
    assert code == 0
    sm = summary(out)
    assert sm["run"]["era"] == "unbounded" and sm["floor"] == "2026-10-20T18:42:00Z" and sm["before_floor"] == 1
    b = line(out, "BOUND (236 item 4")
    assert "this run: unbounded run (no --from, no --through: no era; not an era's count)" in b
    assert "PL closing rows before it, not the population, never classified: 1)" in b
    assert b.endswith("no bound: every run from the floor read, nothing excluded by a bound (not an era's count)")


@pytest.mark.parametrize("flag", ["--from", "--through"])
@pytest.mark.parametrize("bad", ["2026-10-26T12:00:00", "2026-10-26", "2026-10-26 12:00:00Z",
                                 "2026-10-26T12:00:00+00:00", "2026-10-26T12:00Z", "2026-13-26T12:00:00Z",
                                 "\uff12026-10-26T12:00:00Z", "2026-10-26T12:00:00z", ""])
def test_236_4_a_malformed_instant_is_refused_exit_2_nothing_read(world, monkeypatch, flag, bad):
    monkeypatch.setattr(rc, "population", lambda *a, **k: pytest.fail("a closing file was read"))
    code, out, g = _bounded(world, world["ex"], flag, bad)
    assert code == 2 and g.calls == [] and not world["save"].exists()
    assert out == [f"REFUSED: {flag} {bad!r}: not a UTC instant YYYY-MM-DDTHH:MM:SSZ (232 item 2(b)); nothing read"]


@pytest.mark.parametrize("bound, why", [
    (("--from", BOUND, "--through", BOUND), "is not before --through"),
    (("--from", "2026-10-20T18:41:59Z"), "is before the issue's floor 2026-10-20T18:42:00Z"),
    (("--through", "2026-10-20T18:42:00Z"), "is not after the issue's floor 2026-10-20T18:42:00Z"),
])
def test_236_4_a_bound_that_holds_no_row_of_the_population_is_refused(world, bound, why):
    code, out, g = _bounded(world, world["ex"], *bound)
    assert code == 2 and len(out) == 1 and why in out[0] and out[0].endswith("nothing read") and g.calls == []


def test_236_4_the_floor_itself_is_a_valid_from(world):
    code, out, _ = _bounded(world, world["ex"], "--from", "2026-10-20T18:42:00Z")
    assert code == 0 and summary(out)["matches"] == [9240, 9238, 9245]


def test_236_4_the_ruling_is_quoted_verbatim_in_the_header_and_the_docstring(world):
    code, out, _ = run(world)
    assert code == 0
    assert line(out, "THE COPY AND THE BOUND (ARCHITECT 2026-11-03 14:20 ET, addendum 236 item 4, verbatim): ").startswith(
        f"THE COPY AND THE BOUND (ARCHITECT 2026-11-03 14:20 ET, addendum 236 item 4, verbatim): \"{rc.RULING_236_4}\"")
    assert rc.RULING_236_4.startswith("4. #688's RECEIPT (230 item 2(c)) — its two: --db REQUIRED, always a copy")
    assert rc.RULING_236_4.endswith("one run per machine-era, two consoles. It opens when a slot frees.")
    assert " ".join(rc.RULING_236_4.split()) in " ".join(rc.__doc__.split())
