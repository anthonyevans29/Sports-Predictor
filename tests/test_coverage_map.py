"""THE DAY'S COVERAGE (ARCHITECT 2026-10-17 09:30 ET, addendum 107 item C7): `python cli.py coverage [--date]`.
"Tests on the throwaway DB: a day with rows, a day with a gap, a market-only sport." Amended by addendum 111 items 1-2
(#575): a closing run done prints "done (run <run_id>, <exit>)" from the watch's receipt log; the status in the ruled
order (LIVE, SHADOW, MARKET-ONLY, UNKNOWN), a lane naming a competition through its `competitions` field. Against a
SCRATCH schedule under tmp_path (the tables the command reads, src/db/schema.py names; one test on the real schema),
with a scratch roadmap and registry where the status rule is under test, and a scratch receipts file for the watch's.
The clock is fixed; the no-write test blocks the network."""
import hashlib
import inspect
import json
import re
import socket
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))

import closing as cl  # noqa: E402
import coverage_map as cm  # noqa: E402
import sp_common as c  # noqa: E402

from src import roadmap as rm  # noqa: E402
from src.walters import registry as reg  # noqa: E402

NOW = datetime(2026, 10, 17, 12, 10, tzinfo=timezone.utc)          # Saturday 08:10 ET
DAY = "2026-10-17"
COMPS = {"MLB": 1, "NFL": 2, "PL": 3, "NHL": 4, "UNL": 5, "NCAA": 6, "SA": 7, "CL": 8, "EL1": 9, "EFL": 10,
         "UEL": 11, "BL1": 12, "FL1": 13, "ELC": 14, "EL2": 15, "CZE": 16, "SCO": 17}
# model_versions as the ORM stores it (the sport column holds the enum's name): the two production rows the predict
# path resolves (training.MODEL_FAMILIES); NFL has none (predict-nfl writes nfl_predict.MODEL_VERSION)
MODELS = (("MLB", "mlb_pythag_negbin", "v2", "production"), ("SOCCER", "soccer_elo_poisson", "v22", "production"),
          ("SOCCER", "soccer_elo_poisson", "v21", "shelved"))


def _ts(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S.000000")


def utc(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def make_db(path: Path, games, preds=(), wal: bool = False, models=MODELS) -> None:
    """games: (match_id, competition, UTC start 'YYYY-MM-DD HH:MM', status); preds: (match_id, model, UTC computed);
    models: model_versions rows (sport, model_family, version, status), None for no table at all.
    wal: the file in WAL mode, as src/db/database.py leaves the real DB (the mode persists in the file)."""
    con = sqlite3.connect(path)
    if wal:
        con.execute("PRAGMA journal_mode=WAL")
    con.executescript(
        "CREATE TABLE competitions(id INTEGER PRIMARY KEY, code TEXT);"
        "CREATE TABLE teams(id INTEGER PRIMARY KEY, name TEXT);"
        "CREATE TABLE matches(id INTEGER PRIMARY KEY, competition_id INT, utc_date DATETIME, status TEXT,"
        " home_team_id INT, away_team_id INT);"
        "CREATE TABLE predictions(id INTEGER PRIMARY KEY, match_id INT, model_version TEXT, computed_at DATETIME);"
        "INSERT INTO teams VALUES (1, 'Home'), (2, 'Away');")
    con.executemany("INSERT INTO competitions VALUES (?, ?)", [(i, code) for code, i in COMPS.items()])
    for mid, comp, start, status in games:
        con.execute("INSERT INTO matches VALUES (?, ?, ?, ?, 1, 2)", (mid, COMPS[comp], _ts(utc(start)), status))
    for mid, mv, at in preds:
        con.execute("INSERT INTO predictions(match_id, model_version, computed_at) VALUES (?, ?, ?)",
                    (mid, mv, _ts(utc(at))))
    if models is not None:
        con.execute("CREATE TABLE model_versions(id INTEGER PRIMARY KEY, sport VARCHAR(6), model_family VARCHAR(64),"
                    " version VARCHAR(64), status VARCHAR(32))")
        con.executemany("INSERT INTO model_versions(sport, model_family, version, status) VALUES (?, ?, ?, ?)",
                        models)
    con.commit()
    con.close()


def lane(lid, state, registry_id=None, comps=None):
    done = state in ("live", "closed")
    return {"lane": lid, "title": lid.upper(), "issue": 1, "registry_id": registry_id,
            **({"competitions": comps} if comps else {}), "state": state,
            "steps": [{"what": "a step", "owner": "architect", "due": "2026-11-01",
                       "done": {"date": "2026-10-01", "receipt": "r"} if done else None}],
            "earliest_live": None, "live_needs": "a need", "vs_close": "not read", "moved": []}


# The scratch lanes name their competitions through the ruled field (addendum 111 item 2), as the real file's do; three
# exercise the registry check (an id the registry does not hold, a lane and an entry that disagree) and one a SHADOW
# that no market-only set holds.
LANES = [lane("unl", "confirming", "intl-elo-v9", ["UNL"]), lane("ncaa", "declared", "ncaa-elo-v8", ["NCAA"]),
         lane("leagues", "to declare", None, ["SA", "BL1", "FL1", "ELC"]), lane("nhl", "to declare", None, ["NHL"]),
         lane("cups", "declared", None, ["CL", "EFL", "UEL"]), lane("el2", "confirming", "el2-elo-v3", ["EL2"]),
         lane("ghost", "confirming", "ghost-v1", ["CZE"]), lane("split", "confirming", "split-v4", ["SCO"]),
         lane("prose", "confirming", "intl-elo-v9")]          # a lane naming nothing: never matched by its id
ENTRIES = [{"id": "intl-elo-v9", "status": "confirming"}, {"id": "ncaa-elo-v8", "status": "declared"},
           {"id": "el2-elo-v3", "status": "confirming"}, {"id": "split-v4", "status": "closed"}]
V7 = "nhl_elo_v7_xg_margin_no_na"                            # nhl_shadow.MODEL_VERSION, pinned below
NHL_SHADOW = ("export._MARKET_ONLY_REASON; roadmap lane nhl: to declare; chain nhl-daily runs export-nhl-predictions "
              f"({V7})")
EXPANSION_SETS = "SHADOW_VENUE_COMPS (_refuse_shadow_league), chains.EXPANSION_CODES, chains.KALSHI_CAPTURE_ONLY"


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A scratch DB, a scratch roadmap and registry, a scratch receipts file (none yet), no machine settings, and the
    fixed clock."""
    db = tmp_path / "scratch.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.setenv("SP_RECEIPTS", str(tmp_path / "receipts.jsonl"))
    monkeypatch.setattr(c, "HOST_ENV", tmp_path / "no-host.env")
    monkeypatch.setattr(c, "_DOTENV_CACHE", {})
    monkeypatch.delenv("SP_SKIP_FAMILIES", raising=False)
    monkeypatch.delenv("SP_NHL_ACTIVE_FROM", raising=False)          # nhl-daily's season gate: chains.py's date
    road = tmp_path / "roadmap.json"
    road.write_text(json.dumps({"lanes": LANES}))
    assert rm.validate(json.loads(road.read_text())) == []          # the scratch file is a valid roadmap
    ledger = tmp_path / "experiments.json"
    ledger.write_text(json.dumps(ENTRIES))
    monkeypatch.setattr(rm, "ROADMAP_PATH", road)
    monkeypatch.setattr(reg, "LEDGER", str(ledger))
    monkeypatch.setattr(cl, "clock", lambda: NOW)
    repo = tmp_path / "repo"                                        # the SLATE line reads <repo>/exports (#590)
    (repo / "exports").mkdir(parents=True)
    monkeypatch.setattr(c, "REPO", repo)
    return db


def slate_doc(name, ids, exported_at, calls=None, desk=True, repo=None):
    """A family slate file in the scratch exports/ (the shape export-predictions --desk writes: exported_at,
    predictions with a desk block each, desk_meta): `calls` {match_id: call}, PASS by default."""
    calls = calls or {}
    doc = {"exported_at": exported_at, "count": len(ids),
           "predictions": [{"match_id": i, **({"desk": {"call": calls.get(i, "PASS")}} if desk else {})}
                           for i in ids]}
    if desk:
        doc["desk_meta"] = {"policy_version": "v1.1"}
    p = (repo or c.REPO) / "exports" / name
    p.write_text(json.dumps(doc))
    return p


def run(*args):
    from cli import cli
    r = CliRunner().invoke(cli, ["coverage", *args])
    return r.exit_code, r.output.splitlines()


def line_of(out, code):
    got = [x for x in out if x.startswith(f"{code} · ")]
    assert len(got) == 1, out
    return got[0]


def gaps(out):
    return out[out.index("GAPS:") + 1:] if "GAPS:" in out else []


# ------------------------------------------------------------------------------------- the spec's three --

def test_a_day_with_rows(env):
    make_db(env, [(50548, "MLB", "2026-10-18 00:00", "SCHEDULED"), (50549, "MLB", "2026-10-17 20:05", "SCHEDULED")],
            [(50548, "mlb_v2", "2026-10-17 11:02"), (50549, "mlb_v2", "2026-10-17 11:30")])
    slate_doc("mlb_MLB_2026-10-17.json", [50548, 50549], "2026-10-17T11:35:00Z", {50549: "PLAY"})   # #590
    rc, out = run("--date", DAY)
    assert rc == 0
    assert out[0].startswith(f"COVERAGE {DAY} ET · 1 competition · 2 games · now 2026-10-17 08:10 ET")
    mlb = line_of(out, "MLB")
    assert "· 2 games ·" in mlb
    assert "· LIVE (closing family MLB; production mlb_pythag_negbin v2) ·" in mlb     # the predict path's model
    assert "· rows: mlb_v2 2 (computed 2026-10-17 07:02 ET to 2026-10-17 07:30 ET) ·" in mlb    # computed_at in ET
    assert "· without rows: none ·" in mlb
    assert out[out.index(mlb) + 1] == ("MLB SLATE · exports/mlb_MLB_2026-10-17.json · exported 2026-10-17 07:35 ET · "
                                       "PLAY 1 · PASS 1")
    assert out[-1] == "GAPS: none"


def test_an_old_row_is_never_hidden_behind_a_fresh_one(env):
    """(model, computed_at): three rows computed this morning and one a week old print as a range, and the map holds
    each game's own computed_at. A stale row is no gap (the spec's gap is a game with no row)."""
    make_db(env, [(401, "PL", "2026-10-17 14:00", "SCHEDULED"), (402, "PL", "2026-10-17 14:00", "SCHEDULED"),
                  (403, "PL", "2026-10-17 16:30", "SCHEDULED"), (404, "PL", "2026-10-17 16:30", "SCHEDULED")],
            [(401, "v22", "2026-10-17 11:00"), (402, "v22", "2026-10-17 11:00"), (403, "v22", "2026-10-17 11:00"),
             (404, "v22", "2026-10-10 11:00")])
    rc, out = run("--date", DAY)
    assert rc == 0
    assert ("· rows: v22 4 (computed 2026-10-10 07:00 ET to 2026-10-17 07:00 ET) · without rows: none ·"
            in line_of(out, "PL"))
    assert gaps(out) == ["PL: 4 GAMES, ROWS 4, NO SLATE FILE"]          # rows are not the deliverable (#590)
    m = cm.coverage(datetime(2026, 10, 17).date(), NOW)["competitions"][0]["rows"][0]
    assert (m["earliest"], m["latest"]) == (utc("2026-10-10 11:00"), utc("2026-10-17 11:00"))
    assert m["computed"] == {401: utc("2026-10-17 11:00"), 402: utc("2026-10-17 11:00"), 403: utc("2026-10-17 11:00"),
                             404: utc("2026-10-10 11:00")}


def test_a_day_with_a_gap(env):
    make_db(env, [(401, "PL", "2026-10-17 11:30", "SCHEDULED"), (402, "PL", "2026-10-17 14:00", "SCHEDULED"),
                  (403, "PL", "2026-10-17 14:00", "SCHEDULED"), (404, "PL", "2026-10-17 16:30", "SCHEDULED"),
                  (405, "PL", "2026-10-17 16:30", "POSTPONED"),            # void: not a game of the day
                  (50548, "MLB", "2026-10-18 00:00", "SCHEDULED"), (50549, "MLB", "2026-10-17 20:05", "SCHEDULED"),
                  (301, "NFL", "2026-10-17 17:00", "SCHEDULED")],
            [(50548, "mlb_v2", "2026-10-17 11:02")])
    rc, out = run("--date", DAY)
    assert rc == 0
    pl = line_of(out, "PL")
    assert "· 4 games (+1 void, not counted: 405 POSTPONED) ·" in pl
    assert "· rows: none · without rows: 401, 402, 403, 404 ·" in pl
    assert gaps(out) == [
        "MLB: 2 GAMES, 1 PREDICTION ROW, NONE FOR 50549",                   # partial: the games named, no hint
        "MLB: 2 GAMES, ROWS 1, NO SLATE FILE",                              # addendum 126 item 2(b) (#590)
        "NFL: 1 GAME, 0 PREDICTION ROWS — nfl-predict has not run",
        "NFL: 1 GAME, ROWS 0, NO SLATE FILE",
        "PL: 4 GAMES, 0 PREDICTION ROWS — soccer-prematch has not run",     # the spec's example, word for word
        "PL: 4 GAMES, ROWS 0, NO SLATE FILE",
    ]


def test_a_market_only_sport(env):
    """MARKET-ONLY from the code (export._MARKET_ONLY_REASON names NHL and NCAA), never from a lane's state; NHL's
    shadow (v7, run by nhl-daily) rides on the same line. No prediction rows expected, so no gap is claimed."""
    make_db(env, [(501, "NHL", "2026-10-17 23:00", "SCHEDULED"), (502, "NHL", "2026-10-17 23:30", "SCHEDULED"),
                  (601, "NCAA", "2026-10-17 16:00", "SCHEDULED")])
    rc, out = run("--date", DAY)
    assert rc == 0
    nhl = line_of(out, "NHL")
    assert f"· MARKET-ONLY · shadow v7 ({NHL_SHADOW}) ·" in nhl
    assert "· rows: none (none expected: MARKET-ONLY) ·" in nhl
    assert "without rows" not in nhl
    assert nhl.endswith("· closing: none (no closing family covers NHL)")
    assert ("· MARKET-ONLY (export._MARKET_ONLY_REASON; roadmap lane ncaa: declared, no shadow export scheduled for "
            "NCAA (chains.py)) ·" in line_of(out, "NCAA"))
    assert out[-1] == "GAPS: none"


# ----------------------------------------------------------------------------------------- the status rule --
# Addendum 111 item 2: "Status derivation, in this order: LIVE [...]; SHADOW [...]; MARKET-ONLY [...]; UNKNOWN only
# when none applies."

def test_live_is_a_closing_family_and_the_model_its_predict_step_resolves(env, monkeypatch):
    """LIVE: the closing family and the model of record: PL's one production soccer_elo_poisson row (a shelved row is
    no model), NFL's nfl_predict.MODEL_VERSION (it has no model_versions row)."""
    make_db(env, [(401, "PL", "2026-10-17 14:00", "SCHEDULED"), (301, "NFL", "2026-10-17 17:00", "SCHEDULED")],
            [(401, "v22", "2026-10-17 10:00"), (301, "nfl_elo_v1", "2026-10-17 10:00")])
    rc, out = run("--date", DAY)
    assert rc == 0
    assert "· LIVE (closing family SOCCER; production soccer_elo_poisson v22) ·" in line_of(out, "PL")
    assert ("· LIVE (closing family NFL; predict-nfl writes nfl_predict.MODEL_VERSION nfl_elo_v1) ·"
            in line_of(out, "NFL"))
    assert gaps(out) == ["NFL: 1 GAME, ROWS 1, NO SLATE FILE", "PL: 1 GAME, ROWS 1, NO SLATE FILE"]     # #590


@pytest.mark.parametrize("models, why", [
    ((("SOCCER", "soccer_elo_poisson", "v22", "shelved"),), "no production soccer_elo_poisson row in model_versions"),
    ((("SOCCER", "soccer_elo_poisson", "v22", "production"), ("SOCCER", "soccer_elo_poisson", "v23", "production")),
     "2 production soccer_elo_poisson rows in model_versions (the predict path resolves exactly one)"),
    (None, "model_versions cannot be read (OperationalError: no such table: model_versions)"),
], ids=["no-production-row", "two-production-rows", "no-table"])
def test_a_closing_family_without_a_live_model_is_not_live(env, models, why):
    """Not LIVE, the reason on the line, and the derivation goes on: PL is in no lane and no market-only set, so
    UNKNOWN, named once in the gaps and no gap judged. Its closing groups still print (the watch runs them anyway)."""
    make_db(env, [(401, "PL", "2026-10-17 14:00", "SCHEDULED")], models=models)
    rc, out = run("--date", DAY)
    assert rc == 0
    pl = line_of(out, "PL")
    assert (f"· UNKNOWN (closing family SOCCER, but {why}; no roadmap lane names PL; in none of the code's "
            "market-only sets) ·") in pl
    assert pl.endswith("· closing: T-35 09:25 ET [401] → exports/closing_SOCCER_2026-10-17T1400Z.json")
    assert gaps(out) == ["MODEL STATUS UNKNOWN: PL — no gap is judged for it (its line gives the reason)"]


def test_shadow_from_a_confirming_lane_and_its_confirming_registry_entry(env):
    """SHADOW (a): the unl lane names UNL and is confirming, its entry confirming; UNL is market-only in the code as
    well, so the line is the ruling's both. EL2 (no market-only set holds it) prints SHADOW and its tag alone. The
    tag is the registry id's vN token."""
    make_db(env, [(701, "UNL", "2026-10-17 18:45", "SCHEDULED"), (702, "EL2", "2026-10-17 14:00", "SCHEDULED")])
    rc, out = run("--date", DAY)
    assert rc == 0
    unl = line_of(out, "UNL")
    assert ("· MARKET-ONLY · shadow v9 (export._MARKET_ONLY_REASON; roadmap lane unl: confirming; registry "
            "intl-elo-v9: confirming) · rows: none (none expected: MARKET-ONLY) ·") in unl
    assert ("· SHADOW v3 (roadmap lane el2: confirming; registry el2-elo-v3: confirming) · rows: none (none "
            "expected: SHADOW) ·") in line_of(out, "EL2")
    assert out[-1] == "GAPS: none"
    # the UNL shadow is also the one intl-daily runs; the lane and the registry are where it is read
    assert any(r["chain"] == "intl-daily" and r["command"] == "export-unl-predictions" for r in cm.scheduled_shadows())


def test_nhl_qualifies_as_shadow_by_the_shadow_export_nhl_daily_runs(env, monkeypatch):
    """The ruling's own example: NHL prints exactly "MARKET-ONLY · shadow v7". Its lane is "to declare", not
    confirming or declared; it qualifies by (b), nhl-daily running export-nhl-predictions (v7) in a chain whose steps
    name NHL. Without that step the shadow goes and NHL is MARKET-ONLY alone, the reason on its line."""
    make_db(env, [(501, "NHL", "2026-10-17 23:00", "SCHEDULED")])
    nhl = line_of(run("--date", DAY)[1], "NHL")
    assert f"· MARKET-ONLY · shadow v7 ({NHL_SHADOW}) ·" in nhl
    steps = [s for s in cm.CHAINS["nhl-daily"]["steps"] if s[0] != "export-nhl-predictions"]
    monkeypatch.setitem(cm.CHAINS, "nhl-daily", {**cm.CHAINS["nhl-daily"], "steps": steps})
    assert ("· MARKET-ONLY (export._MARKET_ONLY_REASON; roadmap lane nhl: to declare, no shadow export scheduled for "
            "NHL (chains.py)) ·") in line_of(run("--date", DAY)[1], "NHL")


NHL_GATED = ("· MARKET-ONLY (export._MARKET_ONLY_REASON; roadmap lane nhl: to declare, no shadow export scheduled "
             "for NHL ")


@pytest.mark.parametrize("setting, gated", [
    (None, None),                                                  # chains.py's 2026-09-29: active on 10-17
    ("2026-10-17", None),                                          # the gate's own day: sp_run runs the chain
    ("2026-10-18", "nhl-daily inactive until 2026-10-18 [SP_NHL_ACTIVE_FROM]"),
    ("2026-13-01", "nhl-daily runs nothing (SP_NHL_ACTIVE_FROM='2026-13-01' is not a YYYY-MM-DD date — fix host.env "
                   "(ruled default for nhl-daily: 2026-09-29))"),
], ids=["unset", "the-gates-own-day", "the-day-before-the-gate", "malformed"])
def test_a_shadow_chain_outside_its_season_gate_is_no_schedule_that_day(env, monkeypatch, setting, gated):
    """sp_run skips a chain before its active_from (the chain's active_from_env setting, else chains.py's date) and
    fails it on a malformed setting: nhl-daily runs no export-nhl-predictions that day, so NHL carries no shadow that
    day, the gate named on its line (sp_run.active_from, the chain's own gate, never a copy)."""
    if setting is not None:
        monkeypatch.setenv("SP_NHL_ACTIVE_FROM", setting)
    make_db(env, [(501, "NHL", "2026-10-17 23:00", "SCHEDULED")])
    rc, out = run("--date", DAY)
    assert rc == 0
    nhl = line_of(out, "NHL")
    if gated is None:
        assert f"· MARKET-ONLY · shadow v7 ({NHL_SHADOW}) ·" in nhl
    else:
        assert f"{NHL_GATED}(chains.py: {gated})) ·" in nhl
        assert "shadow v7" not in nhl
    assert out[-1] == "GAPS: none"


def test_a_past_day_before_the_chains_py_gate_has_no_shadow(env):
    """--date 2026-09-25, no setting: chains.py's ruled 2026-09-29 had not come, nhl-daily ran nothing that day."""
    make_db(env, [(501, "NHL", "2026-09-25 23:00", "SCHEDULED")])
    rc, out = run("--date", "2026-09-25")
    assert rc == 0
    assert (f"{NHL_GATED}(chains.py: nhl-daily inactive until 2026-09-29 [chains.py default (override: "
            "SP_NHL_ACTIVE_FROM)])) ·") in line_of(out, "NHL")


def test_a_declared_lane_is_shadow_only_where_a_chain_runs_its_shadow_export(env, monkeypatch):
    """NCAA's lane is declared and no chain runs a college shadow (CLAUDE.md: "No college shadow ... until then"):
    MARKET-ONLY. Were a chain to run export-ncaa-predictions it would be reported, never hidden: the tag falls back to
    the full id, ncaa_elo_v1r having no vN token."""
    make_db(env, [(601, "NCAA", "2026-10-17 16:00", "SCHEDULED")])
    assert ("· MARKET-ONLY (export._MARKET_ONLY_REASON; roadmap lane ncaa: declared, no shadow export scheduled for "
            "NCAA (chains.py)) ·") in line_of(run("--date", DAY)[1], "NCAA")
    ch = cm.CHAINS["ncaa-market"]
    monkeypatch.setitem(cm.CHAINS, "ncaa-market", {**ch, "steps": [*ch["steps"], ["export-ncaa-predictions"]]})
    assert ("· MARKET-ONLY · shadow ncaa_elo_v1r (export._MARKET_ONLY_REASON; roadmap lane ncaa: declared; chain "
            "ncaa-market runs export-ncaa-predictions (ncaa_elo_v1r)) ·") in line_of(run("--date", DAY)[1], "NCAA")


def test_the_cups_and_the_four_leagues_are_market_only_from_the_codes_sets(env, monkeypatch):
    """CL, EFL, UEL from cup_coeff.EXAM_COMPS; SA, BL1, FL1, ELC from the three expansion sets. Read from the code at
    run time (a set changed in the code changes the line), never a copy: CL out of EXAM_COMPS is UNKNOWN."""
    make_db(env, [(m, code, "2026-10-17 19:00", "SCHEDULED")
                  for m, code in enumerate(("CL", "EFL", "UEL", "SA", "BL1", "FL1", "ELC"), 800)])
    rc, out = run("--date", DAY)
    assert rc == 0
    for code in ("CL", "EFL", "UEL"):
        assert (f"· MARKET-ONLY (cup_coeff.EXAM_COMPS; roadmap lane cups: declared, no shadow export scheduled for "
                f"{code} (chains.py)) ·") in line_of(out, code)
    for code in ("SA", "BL1", "FL1", "ELC"):
        assert (f"· MARKET-ONLY ({EXPANSION_SETS}; roadmap lane leagues: to declare, no shadow export scheduled for "
                f"{code} (chains.py)) ·") in line_of(out, code)
    assert out[-1] == "GAPS: none"
    from src.walters import cup_coeff
    monkeypatch.setattr(cup_coeff, "EXAM_COMPS", {"EFL", "UEL", "EL"})
    cl_line = line_of(run("--date", DAY)[1], "CL")
    assert "· UNKNOWN (no closing family covers CL; roadmap lane cups: declared" in cl_line


def test_unknown_only_when_none_applies(env):
    """EL1: no family, no lane, no set. CZE: its lane names a registry id the registry does not hold. SCO: its lane
    and its registry entry disagree. Each prints UNKNOWN with every reason; one gaps line names them, no gap judged;
    the competitions print in status order, then by code."""
    make_db(env, [(704, "EL1", "2026-10-17 14:00", "SCHEDULED"), (705, "CZE", "2026-10-17 15:00", "SCHEDULED"),
                  (706, "SCO", "2026-10-17 15:00", "SCHEDULED"), (701, "UNL", "2026-10-17 18:45", "SCHEDULED")])
    rc, out = run("--date", DAY)
    assert rc == 0
    assert ("· UNKNOWN (no closing family covers EL1; no roadmap lane names EL1; in none of the code's market-only "
            "sets) · rows: none · without rows: 704 ·") in line_of(out, "EL1")       # unknown: the rows still shown
    assert ("· UNKNOWN (no closing family covers CZE; roadmap lane ghost: confirming; registry id ghost-v1 is not in "
            "the registry; in none of the code's market-only sets) ·") in line_of(out, "CZE")
    assert ("· UNKNOWN (no closing family covers SCO; roadmap lane split: confirming; registry split-v4: closed (the "
            "lane and the registry disagree); in none of the code's market-only sets) ·") in line_of(out, "SCO")
    assert gaps(out) == [
        "MODEL STATUS UNKNOWN: CZE, EL1, SCO — no gap is judged for them (each line gives the reason)"]
    assert [x.split(" · ")[0] for x in out[1:-2]] == ["UNL", "CZE", "EL1", "SCO"]


def test_an_unreadable_roadmap_judges_no_shadow_never_a_guess(env):
    """Law 4: with the roadmap unreadable no shadow is judged. NHL stays MARKET-ONLY from the code, the line saying so;
    EL1 (no set) is UNKNOWN with that reason; PL's LIVE reads neither file."""
    rm.ROADMAP_PATH.write_text("{not json")
    make_db(env, [(501, "NHL", "2026-10-17 23:00", "SCHEDULED"), (401, "PL", "2026-10-17 14:00", "SCHEDULED"),
                  (704, "EL1", "2026-10-17 14:00", "SCHEDULED")],
            [(401, "soccer_elo_poisson_v22", "2026-10-17 10:00")])
    rc, out = run("--date", DAY)
    assert rc == 0
    assert "· MARKET-ONLY (export._MARKET_ONLY_REASON; shadow not judged: the roadmap cannot be read:" in line_of(out,
                                                                                                               "NHL")
    assert "· UNKNOWN (no closing family covers EL1; shadow not judged: the roadmap cannot be read:" in line_of(out,
                                                                                                             "EL1")
    assert "· LIVE (closing family SOCCER; production soccer_elo_poisson v22) ·" in line_of(out, "PL")


RULED = {   # addendum 111 item 2's examples, on the tracked roadmap and registry and the code as it stands
    "MLB": ("LIVE", "LIVE"), "PL": ("LIVE", "LIVE"), "NFL": ("LIVE", "LIVE"),
    "NHL": ("MARKET-ONLY", "MARKET-ONLY · shadow v7"), "UNL": ("MARKET-ONLY", "MARKET-ONLY · shadow v2"),
    "PD": ("MARKET-ONLY", "MARKET-ONLY · shadow v1"), "NCAA": ("MARKET-ONLY", "MARKET-ONLY"),
    **{c: ("MARKET-ONLY", "MARKET-ONLY") for c in ("CL", "EFL", "UEL", "SA", "BL1", "FL1", "ELC")},
    "EL1": ("UNKNOWN", "UNKNOWN"),
}


def test_the_real_files_and_code_derive_the_ruled_statuses(tmp_path, monkeypatch):
    """On the tracked roadmap and registry, the code's own sets and chains, and the two production rows the predict
    path would resolve (MLB v2, PL v22): the ruling's statuses, word for word, on the ruling's day (no machine
    setting: nhl-daily's season gate is chains.py's date)."""
    monkeypatch.setattr(c, "HOST_ENV", tmp_path / "no-host.env")
    monkeypatch.setattr(c, "_DOTENV_CACHE", {})
    monkeypatch.delenv("SP_NHL_ACTIVE_FROM", raising=False)
    lanes, entries, unread = cm.read_ledgers()
    assert unread is None
    prod = {("mlb", "mlb_pythag_negbin"): ["v2"], ("soccer", "soccer_elo_poisson"): ["v22"]}
    got = {code: cm.model_status(code, lanes, entries, prod, day=NOW.date()) for code in RULED}
    assert {code: (s["status"], s["label"]) for code, s in got.items()} == RULED, got
    assert got["PL"]["from"] == "closing family SOCCER; production soccer_elo_poisson v22"
    assert got["MLB"]["from"] == "closing family MLB; production mlb_pythag_negbin v2"
    assert got["UNL"]["from"].endswith("roadmap lane unl: confirming; registry intl-elo-v2: confirming")
    assert got["PD"]["from"].endswith("roadmap lane pd: confirming; registry soccer-expansion-v1: confirming")
    assert got["NHL"]["from"] == NHL_SHADOW


def test_the_market_only_sets_are_the_codes_own():
    """Imported, never copied: the set cli._refuse_shadow_league refuses, the two chains sets, the market-only fixtures
    file's list and the cup track's competitions. Their union is the ruling's list (EL: the adapter's alias for UEL)."""
    import cli
    from src.walters import cup_coeff, desk_policy, export
    assert "SHADOW_VENUE_COMPS" in inspect.getsource(cli._refuse_shadow_league)
    sets = dict(cm.market_only_sets())
    assert sets == {"SHADOW_VENUE_COMPS (_refuse_shadow_league)": desk_policy.SHADOW_VENUE_COMPS,
                    "chains.EXPANSION_CODES": frozenset(cm.EXPANSION_CODES),
                    "chains.KALSHI_CAPTURE_ONLY": frozenset(cm.KALSHI_CAPTURE_ONLY),
                    "export._MARKET_ONLY_REASON": frozenset(export._MARKET_ONLY_REASON),
                    "cup_coeff.EXAM_COMPS": frozenset(cup_coeff.EXAM_COMPS)}
    assert frozenset().union(*sets.values()) == {"NHL", "NCAA", "UNL", "CL", "EFL", "UEL", "EL", "PD", "SA", "BL1",
                                                 "FL1", "ELC"}
    src = inspect.getsource(cm)
    assert not re.search(r'"(NHL|NCAA|UNL|CL|EFL|UEL|PD|SA|BL1|FL1|ELC|MLB|NFL|PL)"', src)   # no competition named


def test_the_shadow_exports_are_the_clis_own():
    """SHADOW_EXPORTS: each command is a cli command whose body reaches its module; each module writes engine
    model_shadow; every module that does is named. The chains that run one: nhl-daily (its steps name NHL) and
    intl-daily (its steps name no competition)."""
    import importlib
    import cli
    for cmd, (mod, attr) in cm.SHADOW_EXPORTS.items():
        assert mod.rsplit(".", 1)[1] in inspect.getsource(cli.cli.commands[cmd].callback), cmd
        assert importlib.import_module(mod).ENGINE == "model_shadow"
        assert isinstance(getattr(importlib.import_module(mod), attr), str)
    writers = sorted(f"src.walters.{p.stem}" for p in (ROOT / "src" / "walters").glob("*.py")
                     if 'ENGINE = "model_shadow"' in p.read_text(encoding="utf-8"))
    assert writers == sorted(mod for mod, _ in cm.SHADOW_EXPORTS.values())
    from src.walters import intl_shadow, nhl_shadow
    assert nhl_shadow.MODEL_VERSION == V7
    assert cm.scheduled_shadows() == [
        {"chain": "nhl-daily", "command": "export-nhl-predictions", "model": V7, "comps": {"NHL"}},
        {"chain": "intl-daily", "command": "export-unl-predictions", "model": intl_shadow.MODEL_VERSION,
         "comps": set()}]


def test_the_live_model_is_the_one_the_predict_path_resolves():
    """PREDICT_MODEL, one per PREDICT_COMMANDS (law 1): `predict` resolves the production row of its sport's model
    family (generate_predictions -> _generate_predictions_soccer / _mlb -> _resolve_model_version with no version ->
    _current_production_version); `predict-nfl` writes nfl_predict.MODEL_VERSION on every row."""
    from src.walters import nfl_predict, training
    assert tuple(cm.PREDICT_MODEL) == cm.PREDICT_COMMANDS
    cur = inspect.getsource(training._current_production_version)
    assert '"production"' in cur and "_family_for(sport)" in cur
    assert "_current_production_version(" in inspect.getsource(training._resolve_model_version)
    gen = inspect.getsource(training.generate_predictions)
    for sport in ("soccer", "mlb"):
        assert f"_generate_predictions_{sport}(" in gen
        assert "_resolve_model_version(" in inspect.getsource(getattr(training, f"_generate_predictions_{sport}"))
    assert "model_version=MODEL_VERSION" in inspect.getsource(nfl_predict)
    assert nfl_predict.MODEL_VERSION == "nfl_elo_v1"


@pytest.mark.parametrize("model_id, tag", [(V7, "v7"), ("intl-elo-v2", "v2"), ("soccer-expansion-v1", "v1"),
                                           ("ncaa_elo_v1r", "ncaa_elo_v1r"), ("nhl-v10", "v10")])
def test_the_shadow_tag_is_the_ids_vn_token(model_id, tag):
    assert cm.shadow_tag(model_id) == tag


# ------------------------------------------------------------------------------------- the closing groups --

def test_closing_groups_and_their_files_on_a_day_with_two_start_times(env):
    """C2 by closing.groups itself: the earliest start time covers the games within the 10 minutes after it (14:10 in,
    14:11 the next start time); T-35 in ET; the file closing_<FAMILY>_<start>.json under exports/."""
    make_db(env, [(401, "PL", "2026-10-17 14:00", "SCHEDULED"), (402, "PL", "2026-10-17 14:10", "SCHEDULED"),
                  (403, "PL", "2026-10-17 14:11", "SCHEDULED"), (404, "PL", "2026-10-17 16:30", "SCHEDULED")])
    rc, out = run("--date", DAY)
    assert rc == 0
    assert line_of(out, "PL").endswith(
        "· closing: T-35 09:25 ET [401, 402] → exports/closing_SOCCER_2026-10-17T1400Z.json; "
        "T-35 09:36 ET [403] → exports/closing_SOCCER_2026-10-17T1411Z.json; "
        "T-35 11:55 ET [404] → exports/closing_SOCCER_2026-10-17T1630Z.json")
    cov = cm.coverage(datetime(2026, 10, 17).date(), NOW)
    pl = cov["competitions"][0]
    assert [(g["start"], g["match_ids"]) for g in pl["groups"]] == [
        (utc("2026-10-17 14:00"), [401, 402]), (utc("2026-10-17 14:11"), [403]), (utc("2026-10-17 16:30"), [404])]
    assert pl["groups"][0]["run_at"] == utc("2026-10-17 13:25")
    assert pl["groups"][0]["file"] == f"exports/{cl.closing_name('SOCCER', utc('2026-10-17 14:00'))}"


def test_started_games_leave_the_closing_groups(env, monkeypatch):
    """The watch will not run a started game's closing: at 14:05Z the 14:00 game is started and the 14:10 game is the
    first start time left."""
    monkeypatch.setattr(cl, "clock", lambda: utc("2026-10-17 14:05"))
    make_db(env, [(401, "PL", "2026-10-17 14:00", "SCHEDULED"), (402, "PL", "2026-10-17 14:10", "SCHEDULED")],
            [(401, "v22", "2026-10-17 10:00"), (402, "v22", "2026-10-17 10:00")])
    rc, out = run()
    assert rc == 0
    assert "· rows: v22 2 (latest 2026-10-17 06:00 ET) ·" in line_of(out, "PL")     # one computed_at: no range
    assert line_of(out, "PL").endswith(                                    # T-5 <= 5 minutes <= T-35: due now
        "· closing: started 401; T-35 09:35 ET [402] → exports/closing_SOCCER_2026-10-17T1410Z.json (due now)")
    monkeypatch.setattr(cl, "clock", lambda: utc("2026-10-17 18:00"))
    assert line_of(run()[1], "PL").endswith("· closing: started 401, 402; none left to run")


def receipt(**rec) -> None:
    """One closing receipt in the scratch receipts file: the keys closing.run's receipt line writes and closing reads
    back (kind, family, run_id, start, exit, covers; refused / superseded on the runs that are neither)."""
    with open(c.receipts_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps({"kind": "closing", **rec}) + "\n")


MLB_RUN = "20260920T163000Z-mlb-closing"     # closing.run's run_id: f"{now:%Y%m%dT%H%M%SZ}-{chain}"
COVERS_1_2 = [{"match_id": 1, "start": "2026-09-20T17:05:00Z"}, {"match_id": 2, "start": "2026-09-20T17:13:00Z"}]
MLB_DAY = [(1, "MLB", "2026-09-20 17:05", "SCHEDULED"), (2, "MLB", "2026-09-20 17:13", "SCHEDULED"),
           (3, "MLB", "2026-09-20 17:20", "SCHEDULED"), (4, "MLB", "2026-09-20 17:27", "SCHEDULED")]


def test_the_closing_groups_are_the_watchs_own_after_a_closing(env, monkeypatch):
    """closing.due()'s own inputs, the watch's receipts included: the 17:05Z closing succeeded covering 1 and 2, so
    after first pitch the watch's next start time is 17:20Z [3, 4], never 2 re-anchored at 17:13Z (a file the watch
    never writes). The 17:05Z run itself is a done line (addendum 111 item 1). Each group to run has due()'s state:
    due now from T-35 to T-5; inside T-5 a miss, no file."""
    make_db(env, MLB_DAY, [(m, "mlb_v2", "2026-09-20 11:00") for m, *_ in MLB_DAY])
    receipt(family="MLB", run_id=MLB_RUN, start="2026-09-20T17:05:00Z", exit=0, covers=COVERS_1_2)
    done = f"T-35 12:30 ET [1, 2] done (run {MLB_RUN}, 0)"
    for at, state, tail in (
            ("2026-09-20 17:08", "due", f"· closing: started 1; {done}; T-35 12:45 ET [3, 4] → "
                                        "exports/closing_MLB_2026-09-20T1720Z.json (due now)"),
            ("2026-09-20 17:16", "inside", f"· closing: started 1, 2; {done}; T-35 12:45 ET [3, 4] inside T-5: no "
                                           "attempt, no file (the watch records a miss)")):
        now = utc(at)
        watch = cl.due("MLB", now)
        mlb = cm.coverage(datetime(2026, 9, 20).date(), now)["competitions"][0]
        to_run = [g for g in mlb["groups"] if g["state"] != "done"]
        assert [(g["start"], g["match_ids"]) for g in to_run] == [
            (g["start"], [x["match_id"] for x in g["games"]]) for g in watch["groups"]]
        assert [(g["start"], g["match_ids"]) for g in to_run] == [(utc("2026-09-20 17:20"), [3, 4])]
        assert [g["state"] for g in to_run] == [state] and watch[state] == watch["groups"]
        monkeypatch.setattr(cl, "clock", lambda now=now: now)
        assert line_of(run("--date", "2026-09-20")[1], "MLB").endswith(tail)
    assert to_run[0]["file"] is None


# ------------------------------------------------------------------------------- a run done (addendum 111 item 1) --

def test_a_closing_run_done_prints_its_run_id_and_exit(env, monkeypatch):
    """"done (run <run_id>, <exit>)": the receipt's own run_id and exit, its covers as the match ids. A refusal and a
    superseded run are no run (closing._attempts, 380.4), and a run of another day is no line of this one."""
    monkeypatch.setattr(cl, "clock", lambda: utc("2026-09-20 18:00"))
    make_db(env, MLB_DAY, [(m, "mlb_v2", "2026-09-20 11:00") for m, *_ in MLB_DAY])
    receipt(family="MLB", run_id="20260919T163000Z-mlb-closing", start="2026-09-19T17:05:00Z", exit=0,
            covers=[{"match_id": 9, "start": "2026-09-19T17:05:00Z"}])
    receipt(family="MLB", run_id=MLB_RUN, start="2026-09-20T17:05:00Z", exit=0, covers=COVERS_1_2)
    receipt(family="MLB", run_id="20260920T164500Z-mlb-closing", start="2026-09-20T17:20:00Z", exit=2,
            refused="SP_SKIP_FAMILIES names MLB", covers=[])
    receipt(family="MLB", run_id="20260920T164600Z-mlb-closing", start="2026-09-20T17:20:00Z", exit=0,
            superseded=True)
    receipt(family="NFL", run_id="20260920T163000Z-nfl-closing", start="2026-09-20T17:05:00Z", exit=0,
            covers=[{"match_id": 1, "start": "2026-09-20T17:05:00Z"}])
    rc, out = run("--date", "2026-09-20")
    assert rc == 0
    assert line_of(out, "MLB").endswith(
        f"· closing: started 1, 2, 3, 4; T-35 12:30 ET [1, 2] done (run {MLB_RUN}, 0); none left to run")
    g = cm.coverage(datetime(2026, 9, 20).date(), utc("2026-09-20 18:00"))["competitions"][0]["groups"]
    assert [(x["state"], x["run_id"], x["exit"], x["match_ids"]) for x in g] == [("done", MLB_RUN, 0, [1, 2])]


def test_a_game_finished_with_by_a_run_of_the_day_before_keeps_its_line(env, monkeypatch):
    """The run's start time (23:58 ET on 09-19) is no group of 09-20, but it covered game 2 (00:05 ET on 09-20): the
    game a closing finished with keeps its own line on 09-20. A run that recorded no covers still prints."""
    monkeypatch.setattr(cl, "clock", lambda: utc("2026-09-20 04:00"))
    make_db(env, [(1, "MLB", "2026-09-20 03:58", "SCHEDULED"), (2, "MLB", "2026-09-20 04:05", "SCHEDULED")])
    receipt(family="MLB", run_id="20260920T032300Z-mlb-closing", start="2026-09-20T03:58:00Z", exit=0,
            covers=[{"match_id": 1, "start": "2026-09-20T03:58:00Z"}, {"match_id": 2, "start": "2026-09-20T04:05:00Z"}])
    assert line_of(run("--date", "2026-09-20")[1], "MLB").endswith(
        "· closing: a closing finished with 2; none left to run")
    receipt(family="MLB", run_id="20260920T120000Z-mlb-closing", start="2026-09-20T12:35:00Z", exit=1, covers=[])
    assert line_of(run("--date", "2026-09-20")[1], "MLB").endswith(
        "· closing: a closing finished with 2; T-35 08:00 ET [] done (run 20260920T120000Z-mlb-closing, 1); "
        "none left to run")


def test_a_failed_attempt_then_a_success_prints_the_latest(env, monkeypatch):
    """Two runs for one start time: the latest (the log is append-only), the failed attempt not printed."""
    monkeypatch.setattr(cl, "clock", lambda: utc("2026-09-20 16:40"))
    make_db(env, MLB_DAY, [(m, "mlb_v2", "2026-09-20 11:00") for m, *_ in MLB_DAY])
    receipt(family="MLB", run_id="20260920T163000Z-mlb-closing", start="2026-09-20T17:05:00Z", exit=1,
            failed="stale prices", covers=COVERS_1_2)
    receipt(family="MLB", run_id="20260920T163300Z-mlb-closing", start="2026-09-20T17:05:00Z", exit=0,
            covers=COVERS_1_2)
    mlb = line_of(run("--date", "2026-09-20")[1], "MLB")
    assert mlb.endswith("· closing: T-35 12:30 ET [1, 2] done (run 20260920T163300Z-mlb-closing, 0); "
                        "T-35 12:45 ET [3, 4] → exports/closing_MLB_2026-09-20T1720Z.json")
    assert "20260920T163000Z" not in mlb and ", 1)" not in mlb


def test_a_done_start_time_is_never_printed_as_due(env, monkeypatch):
    """A failed first attempt the watch tries again (one of three, no success: closing.due() holds the start time as
    due now). Coverage prints the run as done, once, and says the watch tries again; never a second, due line for the
    same start time. After three failed attempts the watch has finished with it: the latest, and nothing more."""
    now = utc("2026-09-20 16:40")
    monkeypatch.setattr(cl, "clock", lambda: now)
    make_db(env, MLB_DAY, [(m, "mlb_v2", "2026-09-20 11:00") for m, *_ in MLB_DAY])
    receipt(family="MLB", run_id="20260920T163000Z-mlb-closing", start="2026-09-20T17:05:00Z", exit=1,
            failed="stale prices", covers=COVERS_1_2)
    assert [g["start"] for g in cl.due("MLB", now)["due"]] == [utc("2026-09-20 17:05")]   # the watch runs it again
    mlb = line_of(run("--date", "2026-09-20")[1], "MLB")
    assert mlb.endswith("· closing: T-35 12:30 ET [1, 2] done (run 20260920T163000Z-mlb-closing, 1) (attempt 1 "
                        "of 3: the watch tries again); T-35 12:45 ET [3, 4] → "
                        "exports/closing_MLB_2026-09-20T1720Z.json")
    assert "(due now)" not in mlb and "closing_MLB_2026-09-20T1705Z" not in mlb
    for k in (2, 3):
        receipt(family="MLB", run_id=f"20260920T16{30 + k}00Z-mlb-closing", start="2026-09-20T17:05:00Z", exit=1,
                failed="stale prices", covers=COVERS_1_2)
    assert line_of(run("--date", "2026-09-20")[1], "MLB").endswith(
        "· closing: T-35 12:30 ET [1, 2] done (run 20260920T163300Z-mlb-closing, 1); T-35 12:45 ET [3, 4] → "
        "exports/closing_MLB_2026-09-20T1720Z.json")


def test_a_failed_run_inside_t5_is_a_miss_never_tried_again(env, monkeypatch):
    """Two failed runs for 14:00Z (each about 15 minutes) and the clock at 13:57Z, T-3: closing.due() holds the start
    time as inside T-5, so closing.watch() records a miss and makes no attempt. The done line says so, never "the watch
    tries again", and something is still left (the miss), as for a group inside T-5 with no run."""
    now = utc("2026-10-17 13:57")
    monkeypatch.setattr(cl, "clock", lambda: now)
    make_db(env, [(401, "PL", "2026-10-17 14:00", "SCHEDULED")], [(401, "v22", "2026-10-17 10:00")])
    for rid in ("r1", "r2"):
        receipt(family="SOCCER", run_id=rid, start="2026-10-17T14:00:00Z", exit=1, failed="stale prices",
                covers=[{"match_id": 401, "start": "2026-10-17T14:00:00Z"}])
    watch = cl.due("SOCCER", now)
    assert [g["start"] for g in watch["inside"]] == [utc("2026-10-17 14:00")] and watch["due"] == []
    pl = line_of(run("--date", DAY)[1], "PL")
    assert pl.endswith("· closing: T-35 09:25 ET [401] done (run r2, 1) (inside T-5: no further attempt, the watch "
                       "records a miss)")
    assert "the watch tries again" not in pl and "none left to run" not in pl


@pytest.mark.parametrize("first, why", [
    ([1, 1, 1], "3 attempts"),                 # three failed attempts: closing.covered_ids holds the third's covers
    ([0], "a successful closing")])
def test_a_start_time_the_watch_supersedes_names_the_games_its_covers_do_not_hold(env, monkeypatch, first, why):
    """Game 5 stored at 17:05Z after the runs for 17:05Z covered 1 and 2: the watch forms a group [5] there and due()
    holds it due, but closing._under_lock supersedes a watch run for a start time with a success or three attempts
    (closing_state), so nothing runs. The done line says so and names 5; never "the watch tries again"."""
    now = utc("2026-09-20 16:40")
    monkeypatch.setattr(cl, "clock", lambda: now)
    make_db(env, MLB_DAY + [(5, "MLB", "2026-09-20 17:05", "SCHEDULED")],
            [(m, "mlb_v2", "2026-09-20 11:00") for m in (1, 2, 3, 4, 5)])
    for k, ex in enumerate(first, 1):
        receipt(family="MLB", run_id=f"F{k}", start="2026-09-20T17:05:00Z", exit=ex, covers=COVERS_1_2)
    st = cl.closing_state("MLB", "2026-09-20T17:05:00Z")
    assert st["success"] or st["attempts"] == cl.MAX_ATTEMPTS                       # _under_lock: superseded
    assert [(g["start"], [x["match_id"] for x in g["games"]]) for g in cl.due("MLB", now)["due"]] == [
        (utc("2026-09-20 17:05"), [5])]
    mlb = line_of(run("--date", "2026-09-20")[1], "MLB")
    assert mlb.endswith(f"· closing: T-35 12:30 ET [1, 2] done (run F{len(first)}, {first[-1]}) ({why}: the watch "
                        "runs it no more); not in its covers: 5; T-35 12:45 ET [3, 4] → "
                        "exports/closing_MLB_2026-09-20T1720Z.json")
    assert "the watch tries again" not in mlb


def test_a_game_added_after_a_failed_run_is_named_on_the_line_the_watch_tries_again(env, monkeypatch):
    """Game 6 stored at 17:10Z after the 17:05Z run failed covering 1 and 2: the watch's next attempt covers [1, 6, 2];
    the done line says the watch tries again and names 6, which the run's covers do not hold."""
    now = utc("2026-09-20 16:40")
    monkeypatch.setattr(cl, "clock", lambda: now)
    make_db(env, MLB_DAY + [(6, "MLB", "2026-09-20 17:10", "SCHEDULED")],
            [(m, "mlb_v2", "2026-09-20 11:00") for m in (1, 2, 3, 4, 6)])
    receipt(family="MLB", run_id="R1", start="2026-09-20T17:05:00Z", exit=1, failed="stale prices", covers=COVERS_1_2)
    assert [[x["match_id"] for x in g["games"]] for g in cl.due("MLB", now)["due"]] == [[1, 6, 2]]
    assert line_of(run("--date", "2026-09-20")[1], "MLB").endswith(
        "· closing: T-35 12:30 ET [1, 2] done (run R1, 1) (attempt 1 of 3: the watch tries again); not in its covers: "
        "6; T-35 12:45 ET [3, 4] → exports/closing_MLB_2026-09-20T1720Z.json")


def test_a_later_failed_run_never_hides_a_success(env, monkeypatch):
    """A watch success for 17:05Z, then an operator's re-run of the same start time that failed (closing-run with no
    --start picks the next unstarted start; only a watch run is superseded): closing_state still holds the success,
    and so does the line. No failed run, no "(attempt" tail."""
    now = utc("2026-09-20 16:45")
    monkeypatch.setattr(cl, "clock", lambda: now)
    make_db(env, MLB_DAY, [(m, "mlb_v2", "2026-09-20 11:00") for m, *_ in MLB_DAY])
    receipt(family="MLB", run_id="OK1", trigger="watch", start="2026-09-20T17:05:00Z", exit=0, covers=COVERS_1_2,
            closing_file={"file": "exports/closing_MLB_2026-09-20T1705Z.json"})
    receipt(family="MLB", run_id="OP2", trigger="operator", start="2026-09-20T17:05:00Z", exit=1,
            failed="stale prices", covers=COVERS_1_2)
    assert cl.closing_state("MLB", "2026-09-20T17:05:00Z")["success"] is True
    mlb = line_of(run("--date", "2026-09-20")[1], "MLB")
    assert mlb.endswith("· closing: T-35 12:30 ET [1, 2] done (run OK1, 0); closing file "
                        "exports/closing_MLB_2026-09-20T1705Z.json; T-35 12:45 ET [3, 4] → "
                        "exports/closing_MLB_2026-09-20T1720Z.json (due now)")
    assert "OP2" not in mlb and ", 1)" not in mlb and "(attempt" not in mlb
    g = cm.coverage(datetime(2026, 9, 20).date(), now)["competitions"][0]["groups"][0]
    assert (g["run_id"], g["exit"], g["attempts"], g["file"], g["file_failed"]) == (
        "OK1", 0, 2, "exports/closing_MLB_2026-09-20T1705Z.json", False)


@pytest.mark.parametrize("failed", [{"closing_file_failed": True}, {}], ids=["flagged", "error-only"])
def test_a_closing_file_not_written_is_said_on_the_done_line(env, monkeypatch, failed):
    """The page went out (exit 0) but closing.py's write of exports/closing_... failed (write_closing_file's {file,
    error}; _closing adds closing_file_failed and never runs the start time again): closing_state holds a success and
    the watch forms no group there, so nothing else on the line would show it. The done line says the file was NOT
    written, in closing.py's own words; the map carries the flag. Read from the receipt alone (exports/ is not read)."""
    now = utc("2026-10-17 13:40")
    monkeypatch.setattr(cl, "clock", lambda: now)
    make_db(env, [(401, "PL", "2026-10-17 14:00", "SCHEDULED")], [(401, "v22", "2026-10-17 10:00")])
    name = "exports/closing_SOCCER_2026-10-17T1400Z.json"
    receipt(family="SOCCER", run_id="20261017T132500Z-soccer-closing", trigger="watch", start="2026-10-17T14:00:00Z",
            exit=0, covers=[{"match_id": 401, "start": "2026-10-17T14:00:00Z"}],
            closing_file={"file": name, "error": "exists: the earlier closing file names no run id it can be kept "
                                                 "under; it cannot be moved and stands"}, **failed)
    assert cl.closing_state("SOCCER", "2026-10-17T14:00:00Z")["success"] is True     # never run again
    assert cl.due("SOCCER", now)["groups"] == []
    rc, out = run("--date", DAY)
    assert rc == 0
    assert line_of(out, "PL").endswith(
        f"· closing: T-35 09:25 ET [401] done (run 20261017T132500Z-soccer-closing, 0); closing file NOT written "
        f"({name}): receipted and notified, not run again; none left to run")
    g = cm.coverage(datetime(2026, 10, 17).date(), now)["competitions"][0]["groups"][0]
    assert (g["state"], g["exit"], g["file"], g["file_failed"]) == ("done", 0, name, True)


def test_a_family_this_machine_refuses_shows_the_refusal_and_claims_no_gap(env, monkeypatch):
    """The host (host.env: SP_SKIP_FAMILIES=MLB) runs no MLB chain and its watch refuses MLB's start times
    (closing._family_refusal): MLB's line names the refusal in place of its groups, and no prediction-row gap sends the
    operator to a chain this machine never runs. A family not refused keeps its gap. The SLATE gap is claimed for MLB
    all the same, its SLATE line naming the block to run (addendum 126 items 1 and 2(b): "If it's not on the HOST, you
    need to alert me to run these things manually")."""
    monkeypatch.setenv("SP_SKIP_FAMILIES", "MLB")
    make_db(env, [(50548, "MLB", "2026-10-18 00:00", "SCHEDULED"), (50549, "MLB", "2026-10-17 20:05", "SCHEDULED"),
                  (401, "PL", "2026-10-17 14:00", "SCHEDULED")])
    rc, out = run("--date", DAY)
    assert rc == 0
    mlb = line_of(out, "MLB")
    assert ("· LIVE (closing family MLB; production mlb_pythag_negbin v2) · rows: none · without rows: 50549, "
            "50548 ·" in mlb)
    assert mlb.endswith("· closing: refused here (laptop only: SP_SKIP_FAMILIES names MLB here (the host cannot reach "
                        "the MLB feed))")
    assert out[out.index(mlb) + 1] == "MLB SLATE · NO SLATE FILE — run block block_1017_mlb_slate.txt"
    assert gaps(out) == ["MLB: 2 GAMES, ROWS 0, NO SLATE FILE",
                         "PL: 1 GAME, 0 PREDICTION ROWS — soccer-prematch has not run",
                         "PL: 1 GAME, ROWS 0, NO SLATE FILE"]
    assert cm.coverage(datetime(2026, 10, 17).date(), NOW)["competitions"][0]["groups"] == []


def test_receipts_that_cannot_be_read_show_no_groups(env, monkeypatch, tmp_path):
    """Law 4: the watch's receipts unreadable, the groups are not shown (never the groups with nothing finished)."""
    (tmp_path / "receipts-folder").mkdir()
    monkeypatch.setenv("SP_RECEIPTS", str(tmp_path / "receipts-folder"))
    make_db(env, [(401, "PL", "2026-10-17 14:00", "SCHEDULED")], [(401, "v22", "2026-10-17 10:00")])
    rc, out = run("--date", DAY)
    assert rc == 0
    assert line_of(out, "PL").endswith("· closing: not shown (the watch's receipts cannot be read: IsADirectoryError)")


# ------------------------------------------------------------------------------- the SLATE line (#590) --
# ARCHITECT 2026-10-18, addendum 126 item 2(b): "`coverage` gains a SLATE line per LIVE competition: the newest exports
# file of that family's slate kind that covers EVERY game of the day by match id, with its exported_at and its
# PLAY/PASS counts; else "NO SLATE FILE — slate run due HH:MM ET" (or, where the watch is not the machine, "— run
# block"). Its gap line in capitals: "NFL: 12 GAMES, ROWS 12, NO SLATE FILE". `coverage --json` carries it".

NFL_DAY = [(601, "NFL", "2026-10-18 13:30", "SCHEDULED"), (602, "NFL", "2026-10-18 17:00", "SCHEDULED")]
NFL_ROWS = [(601, "nfl_elo_v1", "2026-10-17 23:00"), (602, "nfl_elo_v1", "2026-10-17 23:00")]


def test_the_slate_line_both_ways_and_the_no_slate_gap(env):
    """No file: "NO SLATE FILE — slate run due 07:00 ET" (09:30 ET less 150 minutes) and the gap in capitals; a file
    covering one of the two games is no slate file; the file covering both is named with its exported_at and counts."""
    make_db(env, NFL_DAY, NFL_ROWS)
    rc, out = run("--date", "2026-10-18")
    assert rc == 0
    nfl = line_of(out, "NFL")
    assert out[out.index(nfl) + 1] == "NFL SLATE · NO SLATE FILE — slate run due 07:00 ET"
    assert gaps(out) == ["NFL: 2 GAMES, ROWS 2, NO SLATE FILE"]                     # the ruling's form
    slate_doc("nfl_predictions_2026-10-17.json", [601], "2026-10-17T23:05:00Z")     # one of the two: not counted
    assert gaps(run("--date", "2026-10-18")[1]) == ["NFL: 2 GAMES, ROWS 2, NO SLATE FILE"]
    slate_doc("nfl_predictions_2026-10-18.json", [601, 602, 603], "2026-10-18T11:02:00Z", {601: "PLAY"})
    rc, out = run("--date", "2026-10-18")
    assert out[out.index(line_of(out, "NFL")) + 1] == (
        "NFL SLATE · exports/nfl_predictions_2026-10-18.json · exported 2026-10-18 07:02 ET · PLAY 1 · PASS 2")
    assert out[-1] == "GAPS: none"
    s = cm.coverage(datetime(2026, 10, 18).date(), NOW)["competitions"][0]["slate"]
    assert (s["file"], s["exported_at"], s["rows"], s["calls"], s["due"], s["block"], s["refused"], s["skipped"]) == (
        "exports/nfl_predictions_2026-10-18.json", utc("2026-10-18 11:02"), 3, {"PLAY": 1, "PASS": 2},
        utc("2026-10-18 11:00"), "block_1018_nfl_slate.txt", None, [])


def test_the_newest_covering_file_wins_and_other_calls_are_named(env):
    """PL's slate kind (soccer_PL_*.json): of the files covering both games the newest by exported_at; a newer file
    covering one game is not it. A LADDER is named on its own, never folded into PLAY or PASS. Due floor: a 07:30 ET
    kickoff is due at 06:00 ET."""
    make_db(env, [(401, "PL", "2026-10-17 11:30", "SCHEDULED"), (402, "PL", "2026-10-17 16:30", "SCHEDULED")],
            [(401, "v22", "2026-10-17 06:00"), (402, "v22", "2026-10-17 06:00")])
    assert "PL SLATE · NO SLATE FILE — slate run due 06:00 ET" in run("--date", DAY)[1]
    slate_doc("soccer_PL_2026-10-16_to_2026-10-19.json", [401, 402], "2026-10-16T09:00:00Z", {401: "PLAY"})
    slate_doc("soccer_PL_2026-10-17_to_2026-10-20.json", [401, 402, 403], "2026-10-17T09:00:00Z",
              {401: "PLAY", 402: "LADDER"})
    slate_doc("soccer_PL_2026-10-17.json", [401], "2026-10-17T10:00:00Z")
    out = run("--date", DAY)[1]
    assert out[out.index(line_of(out, "PL")) + 1] == (
        "PL SLATE · exports/soccer_PL_2026-10-17_to_2026-10-20.json · exported 2026-10-17 05:00 ET · PLAY 1 · PASS 1 · "
        "LADDER 1")
    assert out[-1] == "GAPS: none"


def test_a_file_that_cannot_be_parsed_or_has_no_desk_calls_is_skipped_with_its_reason(env):
    """Law 4: never counted, the reason on the line. A file named for another week cannot hold the day and is not
    read."""
    make_db(env, NFL_DAY, NFL_ROWS)
    (c.REPO / "exports" / "nfl_predictions_2026-10-18.json").write_text("{not json")
    slate_doc("nfl_predictions_2026-10-17.json", [601, 602], "2026-10-17T23:05:00Z", desk=False)
    (c.REPO / "exports" / "nfl_predictions_2026-09-01.json").write_text("{not json either")    # another week
    out = run("--date", "2026-10-18")[1]
    assert out[out.index(line_of(out, "NFL")) + 1] == (
        "NFL SLATE · NO SLATE FILE — slate run due 07:00 ET · skipped: nfl_predictions_2026-10-17.json (no desk calls); "
        "nfl_predictions_2026-10-18.json (cannot be parsed: JSONDecodeError)")
    assert gaps(out) == ["NFL: 2 GAMES, ROWS 2, NO SLATE FILE"]


def test_where_this_machine_refuses_the_family_the_line_names_the_block(env, monkeypatch):
    monkeypatch.setenv("SP_SKIP_FAMILIES", "NFL")
    make_db(env, NFL_DAY, NFL_ROWS)
    out = run("--date", "2026-10-18")[1]
    assert out[out.index(line_of(out, "NFL")) + 1] == "NFL SLATE · NO SLATE FILE — run block block_1018_nfl_slate.txt"
    assert gaps(out) == ["NFL: 2 GAMES, ROWS 2, NO SLATE FILE"]


def test_only_a_live_competition_has_a_slate_line_and_exports_are_never_written(env):
    make_db(env, NFL_DAY + [(501, "NHL", "2026-10-18 23:00", "SCHEDULED")], NFL_ROWS)
    f = slate_doc("nfl_predictions_2026-10-18.json", [601, 602], "2026-10-18T11:02:00Z")
    before = (sorted(p.name for p in f.parent.iterdir()), f.read_bytes(), f.stat().st_mtime)
    out = run("--date", "2026-10-18")[1]
    assert not any(x.startswith("NHL SLATE") for x in out) and sum(" SLATE · " in x for x in out) == 1
    assert cm.coverage(datetime(2026, 10, 18).date(), NOW)["competitions"][1]["slate"] is None    # NHL
    assert (sorted(p.name for p in f.parent.iterdir()), f.read_bytes(), f.stat().st_mtime) == before


def test_a_slate_file_the_watch_wrote_is_read_as_the_slate_kind():
    """The slate stage's file name for each family matches the family's slate kind (export_glob), the glob the SLATE
    line reads."""
    import fnmatch
    for fam, d in cl.FAMILIES.items():
        assert fnmatch.fnmatch(cl.slate_file(fam, datetime(2026, 10, 18).date()), d["export_glob"])


# ------------------------------------------------------------------------------------------------ the day --

def test_the_default_date_is_today_in_et_across_the_utc_midnight(env, monkeypatch):
    """02:30Z on 10-18 is 22:30 ET on 10-17: the default day is 10-17, and a game belongs to the day by its ET date."""
    monkeypatch.setattr(cl, "clock", lambda: utc("2026-10-18 02:30"))
    make_db(env, [(1, "MLB", "2026-10-17 03:30", "FINISHED"),       # 10-16 23:30 ET
                  (2, "MLB", "2026-10-17 04:30", "FINISHED"),       # 10-17 00:30 ET
                  (3, "MLB", "2026-10-18 01:00", "LIVE"),           # 10-17 21:00 ET
                  (4, "MLB", "2026-10-18 04:30", "SCHEDULED")])     # 10-18 00:30 ET
    rc, out = run()
    assert rc == 0
    assert out[0].startswith("COVERAGE 2026-10-17 ET · 1 competition · 2 games · now 2026-10-17 22:30 ET")
    assert "· without rows: 2, 3 ·" in line_of(out, "MLB")
    assert line_of(out, "MLB").endswith("· closing: started 2, 3; none left to run")
    rc, out = run("--date", "2026-10-18")
    assert "· without rows: 4 ·" in line_of(out, "MLB")
    # its run time is on the day before its ET date: written with its date
    assert line_of(out, "MLB").endswith(
        "· closing: T-35 2026-10-17 23:55 ET [4] → exports/closing_MLB_2026-10-18T0430Z.json")
    assert cm.day_bounds(datetime(2026, 11, 1).date()) == (utc("2026-11-01 04:00"), utc("2026-11-02 05:00"))  # 25h


def test_no_game_that_day(env):
    make_db(env, [(1, "MLB", "2026-10-19 23:00", "SCHEDULED")])
    rc, out = run("--date", DAY)
    assert (rc, out) == (0, [out[0], "no stored game that day", "GAPS: none"])
    assert out[0].startswith(f"COVERAGE {DAY} ET · 0 competitions · 0 games")


# ------------------------------------------------------------------------------------------- read-only --

@pytest.mark.parametrize("wal", [False, True], ids=["rollback-journal", "wal"])
def test_it_opens_no_write_transaction_and_makes_no_provider_call(env, monkeypatch, wal):
    """On a rollback-journal file nothing new appears. On a WAL file (the real DB's mode) SQLite itself leaves its -wal
    and -shm sidecars beside the file, as for every ro_connect reader: the -wal is empty (no frame written) and the
    file's bytes are unchanged."""
    make_db(env, [(401, "PL", "2026-10-17 14:00", "SCHEDULED"), (501, "NHL", "2026-10-17 23:00", "SCHEDULED")],
            [(401, "v22", "2026-10-17 10:00")], wal=wal)
    before = hashlib.sha256(env.read_bytes()).hexdigest()
    listing = sorted(p.name for p in env.parent.iterdir())
    real, opened, statements = sqlite3.connect, [], []

    def watched(target, *a, **k):
        con = real(target, *a, **k)
        opened.append((str(target), k.get("uri")))
        con.set_trace_callback(statements.append)
        return con

    def no_net(*a, **k):
        raise AssertionError("coverage made a network call")

    def no_session(*a, **k):
        raise AssertionError("coverage opened an ORM session (a write path)")

    monkeypatch.setattr(sqlite3, "connect", watched)
    monkeypatch.setattr(socket, "create_connection", no_net)
    monkeypatch.setattr(socket.socket, "connect", no_net)
    import cli
    import src.db.database as dbm
    monkeypatch.setattr(cli, "session_scope", no_session)
    monkeypatch.setattr(dbm, "session_scope", no_session)
    rc, out = run("--date", DAY)
    assert rc == 0 and len(out) > 2
    assert opened and all(t.endswith("?mode=ro") and u is True for t, u in opened), opened
    assert statements and all(s.lstrip().upper().startswith("SELECT") for s in statements), statements
    assert hashlib.sha256(env.read_bytes()).hexdigest() == before
    new = {p.name for p in env.parent.iterdir()} - set(listing)
    assert new <= ({env.name + "-wal", env.name + "-shm"} if wal else set()), new     # no journal, no new file
    sidecar = env.parent / (env.name + "-wal")
    assert not sidecar.exists() or sidecar.stat().st_size == 0               # no WAL frame written


def test_a_missing_db_is_refused_and_never_created(env):
    rc, out = run("--date", DAY)
    assert rc == 2
    assert out == [f"COVERAGE REFUSED: no database at {env}: nothing is created (the DB is opened read-only)"]
    assert not env.exists()


def test_a_db_that_cannot_be_opened_is_refused_never_a_traceback(env, monkeypatch, tmp_path):
    """A DATABASE_URL naming a folder, or not SQLite at all: COVERAGE REFUSED and exit 2."""
    for url, why in ((f"sqlite:///{tmp_path}", f"the DB at {tmp_path} cannot be read: "),
                     ("postgresql://x/y",
                      "Not a SQLite URL: postgresql://…: the coverage map reads a SQLite DB only")):
        monkeypatch.setenv("DATABASE_URL", url)
        out = []
        assert cm.run(DAY, echo=out.append) == 2
        assert len(out) == 1 and out[0].startswith(f"COVERAGE REFUSED: {why}"), out


def test_a_date_that_is_not_real_is_refused(env):
    make_db(env, [])
    for bad in ("2026-02-30", "2026-1-5", "today"):
        rc, out = run("--date", bad)
        assert (rc, out) == (2, [f"COVERAGE REFUSED: --date {bad!r} is not a real date (YYYY-MM-DD)"])


def test_the_real_schema(tmp_path, monkeypatch):
    """The SELECTs against src/db/schema.py's own tables (law 1): an empty DB made by the ORM's metadata."""
    from sqlalchemy import create_engine
    from src.db.schema import Base
    db = tmp_path / "real.db"
    eng = create_engine(f"sqlite:///{db}")
    Base.metadata.create_all(eng)
    eng.dispose()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.setattr(cl, "clock", lambda: NOW)
    rc, out = run("--date", DAY)
    assert (rc, out[1:]) == (0, ["no stored game that day", "GAPS: none"])


# ------------------------------------------------------------------------------------------- the hint --

def test_the_hint_is_derived_from_chains_py():
    assert cm.writer_chains("SOCCER") == ["soccer-prematch"]
    assert cm.writer_chains("MLB") == ["mlb-preslate"]
    assert cm.writer_chains("NFL") == ["nfl-predict"]


def test_no_writer_found_no_hint(env, monkeypatch):
    monkeypatch.setattr(cm, "writer_chains", lambda fam: [])
    make_db(env, [(401, "PL", "2026-10-17 14:00", "SCHEDULED")])
    assert gaps(run("--date", DAY)[1]) == ["PL: 1 GAME, 0 PREDICTION ROWS", "PL: 1 GAME, ROWS 0, NO SLATE FILE"]


def test_the_predict_commands_are_the_writers_of_prediction_rows():
    """PREDICT_COMMANDS (law 1): Prediction rows are constructed only in training.py and nfl_predict.py, reached among
    the cli commands by `predict` and `predict-nfl` (the web UI's refresh and admin predict job reach
    training.generate_predictions too)."""
    import cli
    made = re.compile(r"(?<![\w.])(?<!class )Prediction\(")             # a constructed row, not the class itself
    files = [*(ROOT / "src").rglob("*.py"), ROOT / "cli.py", ROOT / "main.py"]
    writers = sorted(str(p.relative_to(ROOT)) for p in files if made.search(p.read_text(encoding="utf-8")))
    assert writers == ["src/walters/nfl_predict.py", "src/walters/training.py"]
    assert cm.PREDICT_COMMANDS == ("predict", "predict-nfl")
    assert "generate_predictions(" in inspect.getsource(cli.cli.commands["predict"].callback)
    assert "predict_nfl(" in inspect.getsource(cli.cli.commands["predict-nfl"].callback)
