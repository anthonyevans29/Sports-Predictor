"""#688, the PL injury classification receipt (ARCHITECT 2026-10-27 16:10 ET, addendum 171 item 1): read-only.

A throwaway SQLite world (never data/), closing files as a closing run writes them, and a fake provider (no network).
Covers the happy path, failed reads, empty answers, malformed rows, the call cap and the kept payloads, the refusals
(--save / --db under data/, a missing DB), the DB opened read-only (bytes unchanged), and each ruling item (a)-(f)."""
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


def test_a_bad_since_is_argparses_exit_2(world):
    with pytest.raises(SystemExit) as e:
        run(world, "--since", "2026-13-45")
    assert e.value.code == 2


# ---- read-only ------------------------------------------------------------------------------------------------------

def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_the_db_copy_is_opened_read_only_bytes_unchanged(world):
    before = _sha(world["db"])
    code, out, _ = run(world)
    assert code == 0 and _sha(world["db"]) == before
    assert f"database --db {world['db'].resolve()} (mode=ro URI)" in out[0]
    assert "machine role laptop (ruling 1(b) reads the LAPTOP's database" in out[0]       # conftest pins the role
    assert not (world["db"].parent / "copy.db-journal").exists()


def test_the_configured_db_goes_through_readonly_scope(world, monkeypatch):
    from src.db import database
    eng = create_engine(f"sqlite:///{world['db']}", future=True)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=eng, future=True))
    monkeypatch.setattr(database, "_engine", eng)
    called = []
    real = database.readonly_scope

    def spy():
        called.append(1)
        return real()
    monkeypatch.setattr(database, "readonly_scope", spy)
    before = _sha(world["db"])
    out = []
    code = rc.main(["--exports", str(world["ex"]), "--save", str(world["save"])], echo=out.append,
                   get=FakeGet(answers()))
    eng.dispose()
    assert code == 0 and called == [1] and _sha(world["db"]) == before
    assert "database.readonly_scope: mode=ro URI" in out[0]
    assert summary(out)["rows"] == 3


def test_the_configured_db_missing_is_refused(world, monkeypatch):
    from src.db import database
    missing = world["tmp"] / "absent.db"
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=create_engine(f"sqlite:///{missing}")))
    out = []
    code = rc.main(["--exports", str(world["ex"]), "--save", str(world["save"])], echo=out.append,
                   get=FakeGet(answers()))
    assert code == 2 and "REFUSED: no DB file" in out[0] and not missing.exists()


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
    with rc.open_db(str(world["db"])) as (s, _label):
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
