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
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))

import closing as cl  # noqa: E402
import coverage_map as cm  # noqa: E402
import sp_common as c  # noqa: E402

import cli  # noqa: E402,F401  #604: src.db.database binds its engine at its first import; here, under conftest's DB
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


def make_db(path: Path, games, preds=(), wal: bool = False, models=MODELS, kalshi=None) -> None:
    """games: (match_id, competition, UTC start 'YYYY-MM-DD HH:MM', status); preds: (match_id, model, UTC computed);
    models: model_versions rows (sport, model_family, version, status), None for no table at all.
    wal: the file in WAL mode, as src/db/database.py leaves the real DB (the mode persists in the file).
    kalshi: None for no odds_snapshots table (every caller before addendum 146 item 5(a)), else the stored Kalshi quotes
    (match_id, market, selection, UTC captured 'YYYY-MM-DD HH:MM', yes_bid, yes_ask[, market_ticker]); a ticker on any
    row adds the market_ticker column (migrate_kalshi_ticker.py's)."""
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
    if kalshi is not None:
        tickers = any(len(k) > 6 for k in kalshi)
        con.execute("CREATE TABLE odds_snapshots(id INTEGER PRIMARY KEY, match_id INT, market TEXT, selection TEXT, "
                    "devig_prob REAL, captured_at DATETIME, source TEXT, yes_bid REAL, yes_ask REAL"
                    + (", market_ticker TEXT" if tickers else "") + ")")
        for k in kalshi:
            mid, market, sel, at, bid, ask = k[:6]
            vals = [mid, market, sel, None if bid is None or ask is None else (bid + ask) / 2, _ts(utc(at)), "kalshi",
                    bid, ask] + ([k[6] if len(k) > 6 else None] if tickers else [])
            con.execute(f"INSERT INTO odds_snapshots(match_id, market, selection, devig_prob, captured_at, source, "
                        f"yes_bid, yes_ask{', market_ticker' if tickers else ''}) VALUES "
                        f"({', '.join('?' * len(vals))})", vals)
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
# The soccer-expansion-v1 run record (v22 / -0.1 / 0.0008, PASS, surviving PD) and a declaration the export binds
SX_RUN = {"id": "soccer-expansion-v1", "status": "confirming", "declared_at": "2026-10-07T15:17:38Z",
          "run": {"result": {"production_version": "v22", "rho": -0.1, "elo_goal_coeff": 0.0008, "verdict": "PASS",
                             "surviving": ["PD"]}},
          "verdict": {"verdict": "PASS", "at": "2026-10-09T12:47:39Z"}}
SA_DECL = {"id": "leagues-sa-v1", "competition": "SA", "declared_at": "2026-10-15T10:00:00Z",
           "frozen_constants": {"production_version": "v22", "rho": -0.1, "elo_goal_coeff": 0.0008}, "verdict": None}


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
        "NFL: 1 GAME, 0 PREDICTION ROWS",  # no hint: addendum 166 item 6(B) retired the chain's predict
        "NFL: 1 GAME, ROWS 0, NO SLATE FILE",
        "PL: 4 GAMES, 0 PREDICTION ROWS",  # no hint: addendum 166 item 6(B) retired the chain's predict
        "PL: 4 GAMES, ROWS 0, NO SLATE FILE",
    ]


def test_a_stale_orphan_is_void_like_cancelled_and_the_slate_is_due_for_the_days_games(env):
    """#568 (ARCHITECT 2026-10-20, addendum 146 item 3(c)): "The coverage map marks a STALE_ORPHAN row as VOID like
    CANCELLED (closing.py's VOID set already has it)". Already so in code (closing.VOID, read_day's "void"); pinned
    here: the retired row is named void and not counted, it forms no closing group, and the SLATE line is due for the
    day's other game only (19:08 ET less 150 minutes, never 13:05 ET's 10:35)."""
    assert "STALE_ORPHAN" in cl.VOID and "CANCELLED" in cl.VOID
    make_db(env, [(50548, "MLB", "2026-10-17 23:08", "SCHEDULED"), (50555, "MLB", "2026-10-17 17:05", "STALE_ORPHAN")],
            [(50548, "mlb_v2", "2026-10-17 11:02")])
    rc, out = run("--date", DAY)
    assert rc == 0
    mlb = line_of(out, "MLB")
    assert "· 1 game (+1 void, not counted: 50555 STALE_ORPHAN) ·" in mlb
    assert mlb.endswith("· closing: T-35 18:33 ET [50548] → exports/closing_MLB_2026-10-17T2308Z.json")
    assert out[out.index(mlb) + 1] == "MLB SLATE · NO SLATE FILE — slate run due 16:38 ET"
    assert gaps(out) == ["MLB: 1 GAME, ROWS 1, NO SLATE FILE"]


@pytest.mark.parametrize("status", ["STALE_ORPHAN", "CANCELLED"])
def test_a_day_whose_only_game_is_void_has_no_slate_line_and_no_slate_gap(env, tmp_path, status):
    """#568 (addendum 146 item 3(c)): "the Today tile stops showing a slate due for it". A LIVE MLB day whose only game
    is retired reads as one whose only game is cancelled: no SLATE line, no NO SLATE FILE gap, no closing group, and
    the coverage_v1 file carries `slate` and `slate_line` null (the tile draws only the file's slate_line)."""
    make_db(env, [(50555, "MLB", "2026-10-17 23:08", status)], [(50555, "mlb_v2", "2026-10-17 11:02")])
    out_file = tmp_path / "cov.json"
    rc, out = run("--date", DAY, "--json", "--out", str(out_file))
    assert rc == 0
    assert out[1] == (f"MLB · 0 games (+1 void, not counted: 50555 {status}) · LIVE (closing family MLB; production "
                      "mlb_pythag_negbin v2) · rows: none · without rows: none · closing: none left to run")
    assert not any(" SLATE · " in x for x in out) and out[2] == "GAPS: none"
    mlb = json.loads(out_file.read_text())["competitions"][0]
    assert (mlb["games"], mlb["void"], mlb["groups"], mlb["slate"], mlb["slate_line"]) == (
        [], [[50555, status]], [], None, None)


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


def test_a_declared_league_reads_the_shadow_the_soccer_chains_run_and_an_undeclared_one_does_not(env):
    """R5 (addendum 178) with D2 (addendum 185): export-soccer-expansion-shadow runs after the five leagues' syncs, and
    a league reads its shadow only once the registry holds its declaration (SHADOW_BINDS, read from the registry's
    entries). SA declared: MARKET-ONLY · shadow v1 by (b); BL1 still MARKET-ONLY alone."""
    make_db(env, [(860, "SA", "2026-10-17 19:00", "SCHEDULED"), (861, "BL1", "2026-10-17 19:00", "SCHEDULED")])
    Path(reg.LEDGER).write_text(json.dumps(ENTRIES + [SX_RUN, SA_DECL]))
    out = run("--date", DAY)[1]
    assert (f"· MARKET-ONLY · shadow v1 ({EXPANSION_SETS}; roadmap lane leagues: to declare; chain soccer-prematch "
            "runs export-soccer-expansion-shadow (soccer-expansion-v1)) ·") in line_of(out, "SA")
    assert "which writes no BL1 row: BL1 is not declared (no registry entry leagues-bl1-v1" in line_of(out, "BL1")
    assert "· MARKET-ONLY (" in line_of(out, "BL1")
    assert cm.SHADOW_BINDS["export-soccer-expansion-shadow"]("PL", {}) == "PL is not a league of soccer-expansion-v1"


@pytest.mark.parametrize("bad, why", [
    ({"competition": "BL1"}, "the entry's competition is 'BL1', not 'SA'"),
    ({"declared_at": "2026-10-31"}, "no declared_at as a UTC instant"),
    ({"frozen_constants": {"production_version": "v999", "rho": 0.5, "elo_goal_coeff": 9.0}},
     "differ from the soccer-expansion-v1 run record"),
])
def test_a_declaration_the_export_refuses_is_never_a_shadow_in_coverage(env, bad, why):
    """Findings 1/11: SHADOW_BINDS mirrors the export's own binding (soccer_expansion.shadow_binding): an SA entry
    present that leagues_window.checked refuses writes no SA row, so SA stays MARKET-ONLY with the export's reason on
    its line, never "shadow v1"."""
    make_db(env, [(860, "SA", "2026-10-17 19:00", "SCHEDULED")])
    Path(reg.LEDGER).write_text(json.dumps(ENTRIES + [SX_RUN, {**SA_DECL, **bad}]))
    line = line_of(run("--date", DAY)[1], "SA")
    assert "· MARKET-ONLY (" in line and "shadow v1" not in line, line
    assert ("run export-soccer-expansion-shadow, which writes no SA row: its binding of SA is refused: SA "
            "(leagues-sa-v1): ") in line and why in line, line
    assert cm.SHADOW_BINDS["export-soccer-expansion-shadow"]("SA", {e["id"]: e for e in [SX_RUN, {**SA_DECL, **bad}]})


def test_pd_binds_in_coverage_only_when_the_exports_pd_binding_passes(env):
    """PD through confirming() and its checks, as the export binds it: a run record whose surviving set does not
    hold PD refuses, and SHADOW_BINDS says so (the export's own text)."""
    Path(reg.LEDGER).write_text(json.dumps(ENTRIES + [SX_RUN]))
    assert cm.SHADOW_BINDS["export-soccer-expansion-shadow"]("PD", {SX_RUN["id"]: SX_RUN}) is None
    off = {**SX_RUN, "run": {"result": {**SX_RUN["run"]["result"], "surviving": ["SA"]}}}
    Path(reg.LEDGER).write_text(json.dumps(ENTRIES + [off]))
    why = cm.SHADOW_BINDS["export-soccer-expansion-shadow"]("PD", {off["id"]: off})
    assert why == ("its binding of PD is refused: soccer-expansion-v1: the run record's surviving set ['SA'] does not "
                   "hold PD (soccer_expansion.shadow_binding, the export's own)"), why


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
    # R5 (addendum 178): the soccer chains run export-soccer-expansion-shadow after the four's syncs (addendum 185 D2),
    # but it writes no row for a league not declared: no shadow, the reason on the line (SHADOW_BINDS)
    for code in ("SA", "BL1", "FL1", "ELC"):
        assert (f"· MARKET-ONLY ({EXPANSION_SETS}; roadmap lane leagues: to declare, no shadow export scheduled for "
                f"{code} (chains.py: soccer-prematch, soccer-morning-after run export-soccer-expansion-shadow, which "
                f"writes no {code} row: {code} is not declared (no registry entry leagues-{code.lower()}-v1; addendum "
                "178 R5: nothing is a shadow before it is declared))) ·") in line_of(out, code)
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
    # UNL is MARKET-ONLY · shadow v9: its PAPER header and line follow its line (addendum 146 item 5(a))
    assert [x.split(" · ")[0] for x in out[1:-2] if " SLATE · " not in x] == ["UNL", "CZE", "EL1", "SCO"]
    assert out[2].startswith(f"UNL {PAPER_HEAD} · 1 game · ") and out[3].startswith("UNL SLATE · PAPER · 701 ")


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
    model_shadow; every module that does is named. The chains that run one: soccer-prematch and soccer-morning-after
    (addendum 185 D2; their steps name PL and the five expansion leagues, SHADOW_BINDS narrows them), nhl-daily (its
    steps name NHL) and intl-daily (its steps name no competition)."""
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
    five = set(cm.EXPANSION_CODES)
    assert cm.scheduled_shadows() == [
        # addendum 185 D2: the last step of both soccer sync chains; the steps before it name PL and the five
        {"chain": "soccer-prematch", "command": "export-soccer-expansion-shadow", "model": "soccer-expansion-v1",
         "comps": {"PL", *five}},
        {"chain": "soccer-morning-after", "command": "export-soccer-expansion-shadow", "model": "soccer-expansion-v1",
         "comps": {"PL", *five}},
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
                         "PL: 1 GAME, 0 PREDICTION ROWS",  # no hint: addendum 166 item 6(B) retired the chain's predict
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
    covering one of the two games is no slate file; the file covering both is named with its exported_at and counts,
    the day's games only, the row beyond the day following (addendum 133 item 4, item 8: "N, PLAY and PASS count the
    DAY's games [...] rows beyond the day follow as `· +<k> beyond the day` when k > 0")."""
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
        "NFL SLATE · exports/nfl_predictions_2026-10-18.json · exported 2026-10-18 07:02 ET · PLAY 1 · PASS 1 · +1 "
        "beyond the day")
    assert out[-1] == "GAPS: none"
    s = cm.coverage(datetime(2026, 10, 18).date(), NOW)["competitions"][0]["slate"]
    assert (s["file"], s["exported_at"], s["rows"], s["calls"], s["beyond"], s["started_before"], s["older"], s["due"],
            s["block"], s["refused"], s["skipped"]) == (
        "exports/nfl_predictions_2026-10-18.json", utc("2026-10-18 11:02"), 2, {"PLAY": 1, "PASS": 1}, 1, [], None,
        utc("2026-10-18 11:00"), "block_1018_nfl_slate.txt", None, [])


def test_the_newest_covering_file_wins_and_other_calls_are_named(env):
    """PL's slate kind (soccer_PL_*.json): of the files covering both games the newest by exported_at; a newer file
    covering one game is not it. A LADDER is named on its own, never folded into PLAY or PASS; the counts are the day's
    games, the round's row beyond the day following (addendum 133 item 4, item 8). Due floor: a 07:30 ET kickoff is
    due at 06:00 ET."""
    make_db(env, [(401, "PL", "2026-10-17 11:30", "SCHEDULED"), (402, "PL", "2026-10-17 16:30", "SCHEDULED")],
            [(401, "v22", "2026-10-17 06:00"), (402, "v22", "2026-10-17 06:00")])
    assert "PL SLATE · NO SLATE FILE — slate run due 06:00 ET" in run("--date", DAY)[1]
    slate_doc("soccer_PL_2026-10-16_to_2026-10-19.json", [401, 402], "2026-10-16T09:00:00Z", {401: "PLAY"})
    slate_doc("soccer_PL_2026-10-17_to_2026-10-20.json", [401, 402, 403], "2026-10-17T09:00:00Z",
              {401: "PLAY", 402: "LADDER"})
    slate_doc("soccer_PL_2026-10-17.json", [401], "2026-10-17T10:00:00Z")
    out = run("--date", DAY)[1]
    assert out[out.index(line_of(out, "PL")) + 1] == (
        "PL SLATE · exports/soccer_PL_2026-10-17_to_2026-10-20.json · exported 2026-10-17 05:00 ET · PLAY 1 · PASS 0 · "
        "LADDER 1 · +1 beyond the day")
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


def results_doc(name, ids, day):
    """A results export as `export-results` writes it (src/walters/export.py export_results: exported_at, git_sha,
    sport, start_date, end_date, competition_code, count, record, totals_pulse, results; no predictions), under the
    name the cli gives it, exports/<sport>_<code>_results_<date>.json: the same family glob as the slate kind."""
    sport, code = ("mlb", "MLB") if name.startswith("mlb_") else ("soccer", "PL")
    rows = [{"match_id": i, "date": f"{day}T23:05:00", "away_team": "Away", "home_team": "Home",
             "predicted": {"top_pick": "home_win", "top_pick_prob": 0.55, "home_win_prob": 0.55, "draw_prob": None,
                           "away_win_prob": 0.45, "projected_total": 8.5, "over_under_line": 8.5, "over_prob": 0.5},
             "actual": {"home_score": 4, "away_score": 2, "total_runs": 6, "result": "H"},
             "graded": {"top_pick_hit": True, "total_correct": True, "total_error": -2.5, "log_loss": 0.6,
                        "brier_score": 0.2, "clv": None, "closing_price": None}} for i in ids]
    doc = {"exported_at": f"{day}T12:00:00Z", "git_sha": "abc1234", "sport": sport,
           "start_date": f"{day}T08:00:00", "end_date": f"{day}T08:00:00", "competition_code": code,
           "count": len(rows), "record": {"games": len(rows), "hits": len(rows), "vs_close": None, "redated": []},
           "totals_pulse": None, "results": rows}
    p = c.REPO / "exports" / name
    p.write_text(json.dumps(doc))
    return p


def test_a_results_export_beside_the_slate_file_is_another_kind_never_skipped(env):
    """ARCHITECT 2026-10-18, addendum 133 item 3(b): "A file of the glob with no `predictions` list is another kind:
    not a candidate, never listed as skipped (last_calls reads the same glob and passes such a file in silence).
    `skipped` is for a predictions export that cannot be parsed or has no desk calls, as built." The architect's
    repro: mlb_MLB_results_2026-10-17.json beside mlb_MLB_2026-10-18.json, and soccer_PL_results_<date>.json beside
    the PL slate file (today's mirror folder holds both)."""
    make_db(env, [(50550, "MLB", "2026-10-18 17:05", "SCHEDULED"), (401, "PL", "2026-10-18 13:00", "SCHEDULED")],
            [(50550, "mlb_v2", "2026-10-18 12:30"), (401, "v22", "2026-10-18 12:30")])
    slate_doc("mlb_MLB_2026-10-18.json", [50550], "2026-10-18T13:00:00Z")
    slate_doc("soccer_PL_2026-10-17_to_2026-10-20.json", [401], "2026-10-18T13:00:00Z")
    results_doc("mlb_MLB_results_2026-10-17.json", [50549], "2026-10-17")
    results_doc("soccer_PL_results_2026-10-17.json", [400], "2026-10-17")
    out = run("--date", "2026-10-18")[1]
    assert out[out.index(line_of(out, "MLB")) + 1] == (
        "MLB SLATE · exports/mlb_MLB_2026-10-18.json · exported 2026-10-18 09:00 ET · PLAY 0 · PASS 1")
    assert out[out.index(line_of(out, "PL")) + 1] == ("PL SLATE · exports/soccer_PL_2026-10-17_to_2026-10-20.json · "
                                                      "exported 2026-10-18 09:00 ET · PLAY 0 · PASS 1")
    assert not any("skipped" in x for x in out) and out[-1] == "GAPS: none"
    comps = {x["code"]: x["slate"] for x in cm.coverage(datetime(2026, 10, 18).date(), NOW)["competitions"]}
    assert comps["MLB"]["skipped"] == comps["PL"]["skipped"] == []
    # alone, the results file is no candidate either: no slate file, and still nothing skipped
    (c.REPO / "exports" / "mlb_MLB_2026-10-18.json").unlink()
    out = run("--date", "2026-10-18")[1]
    assert out[out.index(line_of(out, "MLB")) + 1] == "MLB SLATE · NO SLATE FILE — slate run due 10:35 ET"


def test_where_this_machine_refuses_the_family_the_line_names_the_block(env, monkeypatch):
    monkeypatch.setenv("SP_SKIP_FAMILIES", "NFL")
    make_db(env, NFL_DAY, NFL_ROWS)
    out = run("--date", "2026-10-18")[1]
    assert out[out.index(line_of(out, "NFL")) + 1] == "NFL SLATE · NO SLATE FILE — run block block_1018_nfl_slate.txt"
    assert gaps(out) == ["NFL: 2 GAMES, ROWS 2, NO SLATE FILE"]


def test_a_live_competition_has_a_slate_line_a_market_only_one_a_paper_line_and_exports_are_never_written(env):
    """The ruling's addition (ARCHITECT 2026-10-20, addendum 146 item 5(a)): NHL, MARKET-ONLY, now has its PAPER header
    and one PAPER line, never a slate (no gap is claimed); the slate file is read, never written."""
    make_db(env, NFL_DAY + [(501, "NHL", "2026-10-18 23:00", "SCHEDULED")], NFL_ROWS)
    f = slate_doc("nfl_predictions_2026-10-18.json", [601, 602], "2026-10-18T11:02:00Z")
    before = (sorted(p.name for p in f.parent.iterdir()), f.read_bytes(), f.stat().st_mtime)
    out = run("--date", "2026-10-18")[1]
    nhl = [x for x in out if x.startswith("NHL SLATE")]
    assert nhl == [f"NHL {PAPER_HEAD} · 1 game · {PAPER_NOT_READ} · shadow 0 of 1",
                   f"NHL SLATE · PAPER · 501 Away @ Home 19:00 ET · Kalshi: not read (the DB has no odds_snapshots "
                   f"table) · {NO_SHADOW}"]
    assert sum(" SLATE · " in x for x in out) == 3
    x = cm.coverage(datetime(2026, 10, 18).date(), NOW)["competitions"][1]                      # NHL
    assert x["code"] == "NHL" and x["slate"] is None and x["paper"]["label"] == "PAPER, never a call"
    assert (sorted(p.name for p in f.parent.iterdir()), f.read_bytes(), f.stat().st_mtime) == before


def _nfl_slate_line():
    out = run("--date", "2026-10-18")[1]
    return out[out.index(line_of(out, "NFL")) + 1], gaps(out)


def test_the_slate_line_reads_the_watchs_slate_receipts(env):
    """Item 2(c): "the morning page reads them as it reads the closing lines". No file: a miss the watch keeps trying
    and a failed attempt keep the due time and say so; three attempts name the block, the watch running it no more.
    A hold, a refusal and a superseded run are no attempt (closing.slate_state). The gap stands either way."""
    make_db(env, NFL_DAY, NFL_ROWS)
    gap = ["NFL: 2 GAMES, ROWS 2, NO SLATE FILE"]
    receipt(kind="slate_miss", family="NFL", date="2026-10-18", reason="the chain lock was held")
    receipt(kind="slate", family="NFL", date="2026-10-18", exit=0, queued_at="2026-10-18T12:41:00Z",
            held="closing NFL 09:30 ET (T-35 08:55 ET) is inside the 15-minute guard")
    receipt(kind="slate", family="NFL", date="2026-10-17", attempt=1, exit=1, failed="step 1")     # another day
    # the day's newest slate receipt is the hold: the line says so (the slate waits for a closing)
    assert _nfl_slate_line() == ("NFL SLATE · NO SLATE FILE — slate run due 07:00 ET (missed (the chain lock was "
                                 "held): the watch keeps trying; held since 08:41 ET (closing NFL 09:30 ET (T-35 08:55 "
                                 "ET) is inside the 15-minute guard): the slate runs after it)", gap)
    receipt(kind="slate", family="NFL", date="2026-10-18", attempt=1, exit=1, failed="step 6")
    receipt(kind="slate", family="NFL", date="2026-10-18", exit=0, superseded=True, why="1 attempts")
    assert _nfl_slate_line() == ("NFL SLATE · NO SLATE FILE — slate run due 07:00 ET (attempt 1 of 3 failed (step 6): "
                                 "the watch tries again; missed (the chain lock was held): the watch keeps trying)", gap)
    receipt(kind="slate", family="NFL", date="2026-10-18", attempt=2, exit=1, failed="step 6")
    receipt(kind="slate", family="NFL", date="2026-10-18", attempt=3, exit=1, failed="missing from export")
    assert _nfl_slate_line() == ("NFL SLATE · NO SLATE FILE — run block block_1018_nfl_slate.txt (3 attempts, the last "
                                 "failed (missing from export): the watch runs it no more)", gap)
    s = cm.coverage(datetime(2026, 10, 18).date(), NOW)["competitions"][0]["slate"]
    assert (s["attempts"], s["success"], s["last_failed"], s["misses"], s["done"], s["unread"]) == (
        3, False, "missing from export", ["the chain lock was held"], True, None)
    assert cl.slate_state("NFL", "2026-10-18") == {"success": False, "attempts": 3}             # the watch's own read


def test_the_hold_note_names_the_closing_the_slate_waits_for_now(env, monkeypatch):
    """Two closings back to back (#590 review): the laptop's first tick at 08:41 ET holds the NFL slate for the 09:30
    closing (T-35 08:55); the 08:50 tick holds it for the same closing and writes nothing; that closing runs at 08:55;
    the 09:00 tick holds the slate again, for the 09:42 closing (T-35 09:07, outside the 09:30 group's cover). The
    watch receipts each closing it waits for once (closing.record_slate_hold), so the line names the one it waits for
    now, never the closing whose run is done on the line above it. The first tick stays 08:41, the LATE line's `first
    tick` (addendum 133 item 4, item 3); late runs from the due time to the run's start."""
    make_db(env, [(601, "NFL", "2026-10-18 13:30", "SCHEDULED"), (603, "NFL", "2026-10-18 13:42", "SCHEDULED"),
                  (602, "NFL", "2026-10-18 17:00", "SCHEDULED")], NFL_ROWS)
    base = {"kind": "slate", "family": "NFL", "date": "2026-10-18", "trigger": "watch", "due": "2026-10-18T11:00:00Z"}
    day = datetime(2026, 10, 18).date()

    def hold(tick, start):
        s = utc(f"2026-10-18 {start}")
        cl.record_slate_hold("NFL", day, {**base, "run_id": "x", "queued_at": f"2026-10-18T{tick}:00Z"},
                             {"family": "NFL", "start": s, "run_at": s - timedelta(minutes=cl.RUN_LEAD_MIN)})
    hold("12:41", "13:30")
    hold("12:50", "13:30")                                         # the same closing: nothing written
    receipt(family="NFL", run_id="20261018T125500Z-nfl-closing", start="2026-10-18T13:30:00Z", exit=0,
            covers=[{"match_id": 601, "start": "2026-10-18T13:30:00Z"}])
    hold("13:00", "13:42")
    monkeypatch.setattr(cl, "clock", lambda: utc("2026-10-18 13:01"))
    out = run("--date", "2026-10-18")[1]
    assert "T-35 08:55 ET [601] done (run 20261018T125500Z-nfl-closing, 0)" in line_of(out, "NFL")
    assert out[out.index(line_of(out, "NFL")) + 1] == (
        "NFL SLATE · NO SLATE FILE — slate run due 07:00 ET (held since 09:00 ET (closing NFL 09:42 ET (T-35 09:07 "
        "ET) is inside the 15-minute guard): the slate runs after it)")
    assert [r["closing"]["start"] for r in cl.receipts((cl.SLATE_KIND,)) if r.get("held")] == [
        "2026-10-18T13:30:00Z", "2026-10-18T13:42:00Z"]
    late_s, late = cl._slate_late("NFL", "2026-10-18", utc("2026-10-18 13:20"), utc("2026-10-18 11:00"),
                                  utc("2026-10-18 13:21"))
    assert (late_s, late) == (8460.0, {"minutes": 141, "due": utc("2026-10-18 11:00"), "tick": utc("2026-10-18 12:41"),
                                       "run": utc("2026-10-18 13:21")})   # the first tick that found it due: 08:41


@pytest.mark.parametrize("read, runs, kept", [
    ("12:50", (), True),                       # 08:50 ET: the 09:30 closing still ahead, the slate waits for it
    ("13:10", (0,), False),                    # 09:10 ET: that closing ran: the hold is stale
    ("13:10", (1, 1, 1), False),               # 09:10 ET: three failed attempts: it never runs again
    ("13:26", (), False),                      # 09:26 ET: inside T-5, no attempt starts (a miss): it holds nothing
    ("13:31", (), False)],                     # 09:31 ET: started
    ids=["ahead", "done", "three-attempts", "inside-t5", "started"])
def test_a_hold_drops_out_once_its_closing_is_no_longer_ahead(env, monkeypatch, read, runs, kept):
    """The #590 review's feed-down note: the day's newest slate receipt is a hold, written at 08:41 ET for the 09:30
    closing (T-35 08:55). The line carries it only while that closing is one the watch will still run at the read
    (closing.closing_open, closing_ahead's own test: its start more than five minutes off, no success, under three
    attempts); a stale or unrunnable hold drops out, never "the slate runs after it" about a closing done, missed or
    started."""
    make_db(env, [(601, "NFL", "2026-10-18 13:30", "SCHEDULED"), (602, "NFL", "2026-10-18 17:00", "SCHEDULED")],
            NFL_ROWS)
    s = utc("2026-10-18 13:30")
    cl.record_slate_hold("NFL", datetime(2026, 10, 18).date(), {
        "kind": "slate", "family": "NFL", "date": "2026-10-18", "trigger": "watch", "due": "2026-10-18T11:00:00Z",
        "run_id": "x", "queued_at": "2026-10-18T12:41:00Z"},
        {"family": "NFL", "start": s, "run_at": s - timedelta(minutes=cl.RUN_LEAD_MIN)})
    for i, rc in enumerate(runs):
        receipt(family="NFL", run_id=f"20261018T12{55 + i}00Z-nfl-closing", start="2026-10-18T13:30:00Z", exit=rc,
                covers=[{"match_id": 601, "start": "2026-10-18T13:30:00Z"}])
    monkeypatch.setattr(cl, "clock", lambda: utc(f"2026-10-18 {read}"))
    (line,) = [x for x in run("--date", "2026-10-18")[1] if x.startswith("NFL SLATE · ")]
    assert line == "NFL SLATE · NO SLATE FILE — slate run due 07:00 ET" + (
        " (held since 08:41 ET (closing NFL 09:30 ET (T-35 08:55 ET) is inside the 15-minute guard): the slate runs "
        "after it)" if kept else "")
    (nfl,) = [x for x in cm.coverage(datetime(2026, 10, 18).date(), utc(f"2026-10-18 {read}"))["competitions"]
              if x["code"] == "NFL"]
    assert bool(nfl["slate"]["held"]) is kept


def test_a_successful_slate_no_file_holds_every_game_names_the_block(env, monkeypatch):
    """A slate that ran after the first kickoff (the laptop asleep) succeeded on the games not started. Its file counts
    (addendum 133 item 4, item 4: "the SLATE line counts a file that holds every game of the day UNSTARTED at its
    exported_at, and names the ones left out on the line (`· started before it: <ids>`); no gap is claimed for a
    started game"). With no file that holds every game unstarted at its export the gap stands, and the line says the
    watch's run succeeded and runs no more, never "slate run due" a time long past. Every game started before a slate
    ran: the same."""
    make_db(env, [(601, "NFL", "2026-10-18 13:30", "LIVE"), (602, "NFL", "2026-10-18 17:00", "SCHEDULED")], NFL_ROWS)
    monkeypatch.setattr(cl, "clock", lambda: utc("2026-10-18 14:30"))
    f = slate_doc("nfl_predictions_2026-10-18.json", [602], "2026-10-18T13:41:00Z")
    receipt(kind="slate", family="NFL", date="2026-10-18", attempt=1, exit=0, ran_at="2026-10-18T13:40:00Z",
            completed_at="2026-10-18T13:41:00Z", file="exports/nfl_predictions_2026-10-18.json")
    assert _nfl_slate_line() == ("NFL SLATE · exports/nfl_predictions_2026-10-18.json · exported 2026-10-18 09:41 ET · "
                                 "PLAY 0 · PASS 1 · started before it: 601", [])
    f.unlink()                        # no file holds the day's games: the watch's success is said, the gap claimed
    assert _nfl_slate_line() == (
        "NFL SLATE · NO SLATE FILE — run block block_1018_nfl_slate.txt (a successful slate at 09:41 ET "
        "(exports/nfl_predictions_2026-10-18.json), but no file of the day holds every game of the day: the watch runs it "
        "no more)",
        ["NFL: 2 GAMES, ROWS 2, NO SLATE FILE"])
    c.receipts_path().unlink()
    receipt(kind="slate_miss", family="NFL", date="2026-10-18", reason=cl.SLATE_ALL_STARTED)
    # 602 (13:00 ET) is still unstarted at 10:30 ET (re-dated after the miss): the watch decides from the schedule, not
    # from the miss, and slates it on its next tick, so the line keeps the due time and says the miss
    assert _nfl_slate_line()[0] == ("NFL SLATE · NO SLATE FILE — slate run due 07:00 ET (missed (every game of the day "
                                    "had started): the watch keeps trying)")
    assert not cm.coverage(datetime(2026, 10, 18).date(), utc("2026-10-18 14:30"))["competitions"][0]["slate"]["done"]
    monkeypatch.setattr(cl, "clock", lambda: utc("2026-10-18 17:30"))            # 13:30 ET: every game started
    assert _nfl_slate_line()[0] == ("NFL SLATE · NO SLATE FILE — run block block_1018_nfl_slate.txt (missed: every game "
                                    "of the day had started: the watch runs it no more)")


def test_the_days_slate_file_is_one_exported_on_the_et_day(env, monkeypatch):
    """Addendum 133 item 4, item 5: "the day's SLATE file is a file EXPORTED ON THE ET DAY. An older file never stands
    as the day's slate, whatever it covers [...] With only such a file the line reads `NO SLATE FILE — slate run due
    HH:MM ET (newest exports/<file> exported <ET>, not today's)` and the gap is claimed." Saturday's soccer window file
    holds Sunday's PL game: on Sunday it is last sync's, named, and the gap stands; Sunday's own export stands."""
    make_db(env, [(401, "PL", "2026-10-18 13:00", "SCHEDULED")], [(401, "v22", "2026-10-17 10:00")])
    monkeypatch.setattr(cl, "clock", lambda: utc("2026-10-18 12:00"))
    slate_doc("soccer_PL_2026-10-17_to_2026-10-20.json", [401, 402], "2026-10-17T09:00:00Z")
    out = run("--date", "2026-10-18")[1]
    assert out[out.index(line_of(out, "PL")) + 1] == (
        "PL SLATE · NO SLATE FILE — slate run due 06:30 ET (newest exports/soccer_PL_2026-10-17_to_2026-10-20.json "
        "exported 2026-10-17 05:00 ET, not today's)")
    assert gaps(out) == ["PL: 1 GAME, ROWS 1, NO SLATE FILE"]
    pl = cm.coverage(datetime(2026, 10, 18).date(), utc("2026-10-18 12:00"))["competitions"][0]["slate"]
    assert (pl["file"], pl["older"]) == (None, {"file": "exports/soccer_PL_2026-10-17_to_2026-10-20.json",
                                                "exported_at": utc("2026-10-17 09:00")})
    # the watch's notes follow the older file's, in the same brackets
    receipt(kind="slate_miss", family="SOCCER", date="2026-10-18", reason="the chain lock was held")
    out = run("--date", "2026-10-18")[1]
    assert out[out.index(line_of(out, "PL")) + 1] == (
        "PL SLATE · NO SLATE FILE — slate run due 06:30 ET (newest exports/soccer_PL_2026-10-17_to_2026-10-20.json "
        "exported 2026-10-17 05:00 ET, not today's; missed (the chain lock was held): the watch keeps trying)")
    # Sunday's own run rewrites the window file: exported on the day, it stands (the counts are the day's game, +1)
    slate_doc("soccer_PL_2026-10-17_to_2026-10-20.json", [401, 402], "2026-10-18T10:31:00Z")
    out = run("--date", "2026-10-18")[1]
    assert out[out.index(line_of(out, "PL")) + 1] == (
        "PL SLATE · exports/soccer_PL_2026-10-17_to_2026-10-20.json · exported 2026-10-18 06:31 ET · PLAY 0 · PASS 1 · "
        "+1 beyond the day")
    assert out[-1] == "GAPS: none"


def test_an_older_file_is_named_on_the_block_lines_too(env, monkeypatch):
    """Where this machine refuses the family, or the watch runs no slate that day, the older file is named the same
    way, first in the brackets."""
    monkeypatch.setenv("SP_SKIP_FAMILIES", "MLB")
    make_db(env, [(50548, "MLB", "2026-10-18 21:08", "SCHEDULED")])
    monkeypatch.setattr(cl, "clock", lambda: utc("2026-10-18 12:00"))
    slate_doc("mlb_MLB_2026-10-17.json", [50548], "2026-10-17T14:00:00Z")
    out = run("--date", "2026-10-18")[1]
    assert out[out.index(line_of(out, "MLB")) + 1] == (
        "MLB SLATE · NO SLATE FILE — run block block_1018_mlb_slate.txt (newest exports/mlb_MLB_2026-10-17.json "
        "exported 2026-10-17 10:00 ET, not today's)")
    assert gaps(out) == ["MLB: 1 GAME, ROWS 0, NO SLATE FILE"]


def _raw_doc(name, rows, exported_at):
    """A slate file with rows as given: (match_id, call), call None for a row with no desk block."""
    doc = {"exported_at": exported_at, "count": len(rows), "desk_meta": {"policy_version": "v1.1"},
           "predictions": [{"match_id": i, **({"desk": {"call": k}} if k else {})} for i, k in rows]}
    (c.REPO / "exports" / name).write_text(json.dumps(doc))


def test_which_file_stands_and_what_it_counts(env, monkeypatch):
    """The file of the day that holds the most of the day's games stands, of the same reach the newest: a re-export
    after a kickoff leaves the started game out, and the morning file still holds it. A row of a game of the day
    called off (VOID) is no game and not beyond the day. A file stands: no older file is named. A file exported after
    the day is neither the day's nor an older one. `started before it` names the games the file has no row for."""
    make_db(env, NFL_DAY[:1] + [(602, "NFL", "2026-10-18 17:00", "SCHEDULED"),
                                (603, "NFL", "2026-10-18 17:00", "POSTPONED")], NFL_ROWS)
    monkeypatch.setattr(cl, "clock", lambda: utc("2026-10-18 14:30"))
    _raw_doc("nfl_predictions_2026-10-18.json", [(601, "PASS"), (602, "PASS"), (603, "PASS"), (699, "PASS")],
             "2026-10-18T10:00:00Z")
    _raw_doc("nfl_predictions_2026-10-18_re.json", [(602, "PLAY")], "2026-10-18T14:00:00Z")
    _raw_doc("nfl_predictions_2026-10-17.json", [(601, "PASS"), (602, "PASS")], "2026-10-17T14:00:00Z")
    _raw_doc("nfl_predictions_2026-10-19.json", [(601, "PASS"), (602, "PASS")], "2026-10-19T12:00:00Z")
    assert _nfl_slate_line() == ("NFL SLATE · exports/nfl_predictions_2026-10-18.json · exported 2026-10-18 06:00 ET · "
                                 "PLAY 0 · PASS 2 · +1 beyond the day", [])
    nfl = cm.coverage(datetime(2026, 10, 18).date(), utc("2026-10-18 14:30"))["competitions"][0]["slate"]
    assert (nfl["beyond"], nfl["older"], nfl["started_before"]) == (1, None, [])
    (c.REPO / "exports" / "nfl_predictions_2026-10-18.json").unlink()
    # the re-export alone: it holds 602, unstarted at 10:00 ET; 601 had started and has no row in it
    assert _nfl_slate_line()[0] == ("NFL SLATE · exports/nfl_predictions_2026-10-18_re.json · exported 2026-10-18 "
                                    "10:00 ET · PLAY 1 · PASS 0 · started before it: 601")
    # a row of 601 with no desk block: the file holds it, so it is not named as left out
    _raw_doc("nfl_predictions_2026-10-18_re.json", [(601, None), (602, "PLAY")], "2026-10-18T14:00:00Z")
    assert _nfl_slate_line()[0] == ("NFL SLATE · exports/nfl_predictions_2026-10-18_re.json · exported 2026-10-18 "
                                    "10:00 ET · PLAY 1 · PASS 0 · no desk call 1")
    (c.REPO / "exports" / "nfl_predictions_2026-10-18_re.json").unlink()
    # no file of the day: the older one is the newest exported BEFORE the day, never Monday's file
    assert _nfl_slate_line()[0] == ("NFL SLATE · NO SLATE FILE — slate run due 07:00 ET (newest "
                                    "exports/nfl_predictions_2026-10-17.json exported 2026-10-17 10:00 ET, not today's)")


def test_slate_receipts_that_cannot_be_read_are_said(env, monkeypatch, tmp_path):
    (tmp_path / "receipts-folder").mkdir()
    monkeypatch.setenv("SP_RECEIPTS", str(tmp_path / "receipts-folder"))
    make_db(env, NFL_DAY, NFL_ROWS)
    assert _nfl_slate_line()[0] == ("NFL SLATE · NO SLATE FILE — slate run due 07:00 ET (the watch's receipts cannot "
                                    "be read: IsADirectoryError)")


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
    # ARCHITECT 2026-10-25, addendum 166 item 6(B): soccer-prematch's and nfl-predict's predict steps are retired (the
    # closing watch's slate stage runs them), so no slate chain writes SOCCER's or NFL's rows: no hint for them.
    assert cm.writer_chains("SOCCER") == []
    assert cm.writer_chains("MLB") == ["mlb-preslate"]
    assert cm.writer_chains("NFL") == []


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


# ------------------------------------------------------------------- --json (addendum 125 item 2(a), #589) --
# ARCHITECT 2026-10-18, addendum 125 item 2(a), verbatim: "`python cli.py coverage --json [--out PATH]` writes the dict
# `deploy/hosting/coverage_map.coverage()` already returns (date, now, competitions[], gaps[]; datetimes ISO-8601 Z),
# under `kind: "coverage_v1"`, plus `roadmap`: the lanes of docs/roadmap.json with their competitions, status and dated
# ETAs, read as `cli.py roadmap` reads them (no new source of truth; if a lane carries no date it prints "no ETA").
# Default --out exports/coverage_<date>.json; [...] Read-only as today: mode=ro, no provider call, exit 0 whatever the
# gaps."

PIN_NOW = utc("2026-10-17 13:40")
PIN_GAMES = [(401, "PL", "2026-10-17 14:00", "SCHEDULED"), (402, "PL", "2026-10-17 14:00", "SCHEDULED"),
             (403, "PL", "2026-10-17 16:30", "SCHEDULED"), (404, "PL", "2026-10-17 16:30", "POSTPONED"),
             (405, "PL", "2026-10-17 11:30", "FINISHED"), (301, "NFL", "2026-10-17 17:00", "SCHEDULED"),
             (501, "NHL", "2026-10-17 23:00", "SCHEDULED"), (601, "NCAA", "2026-10-17 16:00", "SCHEDULED"),
             (704, "EL1", "2026-10-17 14:00", "SCHEDULED"), (702, "EL2", "2026-10-17 14:00", "SCHEDULED")]
PIN_PREDS = [(401, "v22", "2026-10-17 10:00"), (402, "v22", "2026-10-17 10:00"), (405, "v22", "2026-10-10 11:00")]
PIN_RUN = "20261017T132500Z-soccer-closing"
# The text output of origin/main (92c2442) on the pin day, captured BEFORE this change: every status, a void game, a
# started game, a done run with its closing file, a group ahead, the three kinds of gap. Byte for byte. With the slate
# run (#600, merged after this): the same day as #600's own head (4a54cd2) prints it before --json, byte for byte (its
# header names the slate files read, and each LIVE competition gains its SLATE line and its slate gap). With the PAPER
# line (ARCHITECT 2026-10-20, addendum 146 item 5(a), the ruling's addition): the header names the shadow files read,
# and each MARKET-ONLY competition (NCAA, NHL) gains its PAPER header and one PAPER line per game; this scratch DB has no
# odds_snapshots table, so Kalshi is not read, and no shadow file is in exports/.
PAPER_NOT_READ = "Kalshi not read (the DB has no odds_snapshots table)"
PAPER_HEAD = ("SLATE · PAPER, never a call (market-only: no ledger, no P&L, no position; ARCHITECT 2026-10-20, addendum "
              "146 item 5(a))")
NO_SHADOW = "shadow: none (no shadow row before kickoff in exports/)"
PIN_TEXT = [
    "COVERAGE 2026-10-17 ET · 6 competitions · 9 games · now 2026-10-17 09:40 ET · read-only (the DB mode=ro, the "
    "closing-watch schedule and receipts, the slate and shadow files in exports/): no row written, no export written, "
    "no provider call",
    "NFL · 1 game · LIVE (closing family NFL; predict-nfl writes nfl_predict.MODEL_VERSION nfl_elo_v1) · rows: none · "
    "without rows: 301 · closing: T-35 12:25 ET [301] → exports/closing_NFL_2026-10-17T1700Z.json",
    "NFL SLATE · NO SLATE FILE — slate run due 10:30 ET",
    "PL · 4 games (+1 void, not counted: 404 POSTPONED) · LIVE (closing family SOCCER; production soccer_elo_poisson "
    "v22) · rows: v22 3 (computed 2026-10-10 07:00 ET to 2026-10-17 06:00 ET) · without rows: 403 · closing: started "
    "405; T-35 09:25 ET [401, 402] done (run 20261017T132500Z-soccer-closing, 0); closing file "
    "exports/closing_SOCCER_2026-10-17T1400Z.json; T-35 11:55 ET [403] → exports/closing_SOCCER_2026-10-17T1630Z.json",
    "PL SLATE · NO SLATE FILE — slate run due 06:00 ET",
    "EL2 · 1 game · SHADOW v3 (roadmap lane el2: confirming; registry el2-elo-v3: confirming) · rows: none (none "
    "expected: SHADOW) · closing: none (no closing family covers EL2)",
    "NCAA · 1 game · MARKET-ONLY (export._MARKET_ONLY_REASON; roadmap lane ncaa: declared, no shadow export scheduled "
    "for NCAA (chains.py)) · rows: none (none expected: MARKET-ONLY) · closing: none (no closing family covers NCAA)",
    f"NCAA {PAPER_HEAD} · 1 game · {PAPER_NOT_READ} · shadow 0 of 1",
    f"NCAA SLATE · PAPER · 601 Away @ Home 12:00 ET · Kalshi: not read (the DB has no odds_snapshots table) · {NO_SHADOW}",
    "NHL · 1 game · MARKET-ONLY · shadow v7 (export._MARKET_ONLY_REASON; roadmap lane nhl: to declare; chain nhl-daily "
    "runs export-nhl-predictions (nhl_elo_v7_xg_margin_no_na)) · rows: none (none expected: MARKET-ONLY) · closing: "
    "none (no closing family covers NHL)",
    f"NHL {PAPER_HEAD} · 1 game · {PAPER_NOT_READ} · shadow 0 of 1",
    f"NHL SLATE · PAPER · 501 Away @ Home 19:00 ET · Kalshi: not read (the DB has no odds_snapshots table) · {NO_SHADOW}",
    "EL1 · 1 game · UNKNOWN (no closing family covers EL1; no roadmap lane names EL1; in none of the code's market-only "
    "sets) · rows: none · without rows: 704 · closing: none (no closing family covers EL1)",
    "GAPS:",
    "NFL: 1 GAME, 0 PREDICTION ROWS",  # no hint: addendum 166 item 6(B) retired the chain's predict
    "NFL: 1 GAME, ROWS 0, NO SLATE FILE",
    "PL: 4 GAMES, 3 PREDICTION ROWS, NONE FOR 403",
    "PL: 4 GAMES, ROWS 3, NO SLATE FILE",
    "MODEL STATUS UNKNOWN: EL1 — no gap is judged for it (its line gives the reason)",
]
PIN_GAPS = PIN_TEXT[PIN_TEXT.index("GAPS:") + 1:]
PIN_LINES = [x for x in PIN_TEXT[1:PIN_TEXT.index("GAPS:")] if " SLATE · " not in x]     # the competitions' own lines
ISO_Z = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")


@pytest.fixture
def pin(env, monkeypatch):
    monkeypatch.setattr(cl, "clock", lambda: PIN_NOW)
    make_db(env, PIN_GAMES, PIN_PREDS)
    receipt(family="SOCCER", run_id=PIN_RUN, trigger="watch", start="2026-10-17T14:00:00Z", exit=0,
            covers=[{"match_id": 401, "start": "2026-10-17T14:00:00Z"},
                    {"match_id": 402, "start": "2026-10-17T14:00:00Z"}],
            closing_file={"file": "exports/closing_SOCCER_2026-10-17T1400Z.json"})
    return env


def test_without_json_the_text_output_is_unchanged_byte_for_byte(pin):
    """The ruling adds a file; the console stays as main prints it (pinned from main's own run, above)."""
    rc, out = run("--date", DAY)
    assert (rc, out) == (0, PIN_TEXT)


def _datetimes(v, path="$"):
    """Every string in the document that reads as a timestamp, with its path (the *_et fields are the line's words in
    ET, written as the console writes them, not datetimes)."""
    if isinstance(v, dict):
        return [x for k, w in v.items() if not str(k).endswith("_et") for x in _datetimes(w, f"{path}.{k}")]
    if isinstance(v, list):
        return [x for i, w in enumerate(v) for x in _datetimes(w, f"{path}[{i}]")]
    return [(path, v)] if isinstance(v, str) and re.match(r"[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:", v) else []


def test_json_writes_the_kind_the_coverage_dict_and_iso_z_datetimes(pin, tmp_path):
    out = tmp_path / "out" / "coverage.json"
    rc, lines = run("--date", DAY, "--json", "--out", str(out))
    assert rc == 0                                                  # exit 0 whatever the gaps (three here)
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["kind"] == "coverage_v1"
    cov = cm.coverage(datetime(2026, 10, 17).date(), PIN_NOW)
    assert (doc["date"], doc["now"], doc["now_et"]) == (DAY, "2026-10-17T13:40:00Z", "2026-10-17 09:40 ET")
    assert doc["gaps"] == cov["gaps"] == PIN_GAPS
    assert [x["code"] for x in doc["competitions"]] == [x["code"] for x in cov["competitions"]]
    # the dict coverage() returns, every key and value, with each datetime as ISO-8601 Z (the additions beside it)
    added = {"line", "games_text", "rows_text", "without_rows_text", "closing_text", "closing_tail", "slate_line",
             "paper_lines"}                                          # paper_lines: addendum 146 item 5(a)
    for xd, x in zip(doc["competitions"], cov["competitions"]):
        assert set(xd) - added == set(x), x["code"]
        bare = json.loads(json.dumps({k: xd[k] for k in x}))
        for g in bare["groups"]:
            assert set(g) >= {"run_lead", "run_at_et", "text"}
            for k in ("run_lead", "run_at_et", "text"):
                del g[k]
        for m in bare["rows"]:
            del m["computed_et"]
        assert bare == cm._plain(x)
    pl = next(x for x in doc["competitions"] if x["code"] == "PL")
    assert pl["games"] == [405, 401, 402, 403] and pl["void"] == [[404, "POSTPONED"]] and pl["started"] == [405]
    assert pl["rows"][0]["computed"] == {"401": "2026-10-17T10:00:00Z", "402": "2026-10-17T10:00:00Z",
                                         "405": "2026-10-10T11:00:00Z"}
    assert (pl["rows"][0]["earliest"], pl["rows"][0]["latest"]) == ("2026-10-10T11:00:00Z", "2026-10-17T10:00:00Z")
    assert [(g["state"], g["start"], g["run_at"], g["match_ids"]) for g in pl["groups"]] == [
        ("done", "2026-10-17T14:00:00Z", "2026-10-17T13:25:00Z", [401, 402]),
        ("ahead", "2026-10-17T16:30:00Z", "2026-10-17T15:55:00Z", [403])]
    stamps = _datetimes(doc)
    assert stamps and all(ISO_Z.fullmatch(v) for _, v in stamps), [s for s in stamps if not ISO_Z.fullmatch(s[1])]
    # the line's own words beside the data, so a reader computes nothing (the Cockpit's Today tab)
    assert [x["line"] for x in doc["competitions"]] == PIN_LINES
    assert (pl["games_text"], pl["rows_text"], pl["without_rows_text"]) == (
        "4 games (+1 void, not counted: 404 POSTPONED)",
        "rows: v22 3 (computed 2026-10-10 07:00 ET to 2026-10-17 06:00 ET)", "without rows: 403")
    assert pl["closing_text"] == "closing: " + PIN_LINES[1].split(" · closing: ", 1)[1]
    assert pl["rows"][0]["computed_et"] == "computed 2026-10-10 07:00 ET to 2026-10-17 06:00 ET"
    assert [(g["run_lead"], g["run_at_et"], g["text"]) for g in pl["groups"]] == [
        ("T-35", "09:25 ET", f"T-35 09:25 ET [401, 402] done (run {PIN_RUN}, 0); closing file "
                             "exports/closing_SOCCER_2026-10-17T1400Z.json"),
        ("T-35", "11:55 ET", "T-35 11:55 ET [403] → exports/closing_SOCCER_2026-10-17T1630Z.json")]
    nhl = next(x for x in doc["competitions"] if x["code"] == "NHL")
    assert (nhl["status_label"], nhl["without_rows_text"]) == ("MARKET-ONLY · shadow v7", None)
    assert pl["closing_tail"] is None and nhl["closing_tail"] is None      # a group left to run; no closing family
    # the console: the same lines, the header naming the one file written, then the file's line
    assert lines[0] == PIN_TEXT[0].replace("no export written", f"one export written ({out}, --json)")
    assert lines[1:-1] == PIN_TEXT[1:]
    assert lines[-1] == (f"COVERAGE JSON: {out} written (kind coverage_v1: the map above as data, 6 competitions, 5 "
                         f"gap lines, roadmap {len(LANES)} lanes)")


def test_json_carries_the_closing_tail_none_left_to_run_when_every_group_is_done(pin, tmp_path):
    """#589 review: the line's "none left to run" is appended outside any group's text (_closing_clause), so a reader
    rebuilding the closing section from groups / started / finished lost it. The file carries it as data,
    `closing_tail`, from the one function the line uses (_closing_tail): "none left to run", or null where the clause
    says no such thing (a group left to run, no closing family, refused here, receipts not shown)."""
    receipt(family="SOCCER", run_id="20261017T155500Z-soccer-closing", trigger="watch", start="2026-10-17T16:30:00Z",
            exit=0, covers=[{"match_id": 403, "start": "2026-10-17T16:30:00Z"}],
            closing_file={"file": "exports/closing_SOCCER_2026-10-17T1630Z.json"})
    out = tmp_path / "c.json"
    rc, lines = run("--date", DAY, "--json", "--out", str(out))
    assert rc == 0
    by = {x["code"]: x for x in json.loads(out.read_text())["competitions"]}
    pl = by["PL"]
    assert [g["state"] for g in pl["groups"]] == ["done", "done"]
    assert pl["closing_tail"] == "none left to run"
    assert pl["closing_text"].endswith("; none left to run") and not any("none left to run" in g["text"]
                                                                           for g in pl["groups"])
    assert pl["line"] == next(ln for ln in lines if ln.startswith("PL · "))     # the printed line, unchanged
    assert by["NFL"]["closing_tail"] is None                                    # its group is still ahead
    assert (by["NHL"]["closing_tail"], by["NHL"]["closing_text"]) == (None, "closing: none (no closing family covers "
                                                                         "NHL)")
    # the text output's clause is the same function's: no group at all also ends "none left to run" (started games)
    x = dict(pl, groups=[], started=[405], finished=[], refused=None, closing_unread=None, family="SOCCER")
    assert cm._closing_tail(x) == "none left to run"
    assert cm._closing_tail(dict(x, refused="SP_SKIP_FAMILIES")) is None
    assert cm._closing_tail(dict(x, closing_unread="the watch's receipts cannot be read: OSError")) is None


def test_json_roadmap_is_the_lanes_as_roadmap_reads_them_and_no_eta_where_undated(pin, tmp_path):
    """`roadmap`: src/roadmap.lanes_data on the coverage day, the lanes in the file's order with their competitions,
    state and ETA ("earliest live <date>", or "no ETA" where the lane carries none), and the print's own lines."""
    lanes = json.loads(rm.ROADMAP_PATH.read_text())["lanes"]
    lanes[0]["earliest_live"] = "2026-12-01"                       # one dated lane among undated ones
    rm.ROADMAP_PATH.write_text(json.dumps({"lanes": lanes}))
    out = tmp_path / "c.json"
    assert run("--date", DAY, "--json", "--out", str(out))[0] == 0
    road = json.loads(out.read_text())["roadmap"]
    assert road == rm.lanes_data(datetime(2026, 10, 17).date())
    assert [(r["lane"], r["competitions"], r["state"], r["eta"]) for r in road] == [
        (ln["lane"], ln.get("competitions"), ln["state"], "earliest live 2026-12-01" if i == 0 else "no ETA")
        for i, ln in enumerate(lanes)]
    assert road[0]["earliest_live"] == "2026-12-01" and road[1]["earliest_live"] is None
    assert road[-1]["competitions"] is None                         # the prose lane names none: null, never guessed
    assert road[0]["next"] == {"what": "a step", "owner": "architect", "due": "2026-11-01", "when": "in 15 days"}
    from cli import cli
    printed = CliRunner().invoke(cli, ["roadmap", "--today", DAY])
    assert printed.exit_code == 0, printed.output                   # the scratch roadmap, the real taxonomy
    for r in road:
        assert r["line"] in printed.output.splitlines() and f"  {r['next_line']}" in printed.output.splitlines()


def test_json_with_a_roadmap_that_cannot_be_read_gives_null_and_the_reason(pin, tmp_path):
    """Law 4: no lane is guessed. The map is still written (its statuses say the shadow was not judged), exit 0."""
    rm.ROADMAP_PATH.write_text("{not json")
    out = tmp_path / "c.json"
    rc, lines = run("--date", DAY, "--json", "--out", str(out))
    assert rc == 0
    doc = json.loads(out.read_text())
    assert doc["roadmap"] is None
    assert doc["roadmap_unread"].startswith(f"the roadmap cannot be read: the roadmap {rm.ROADMAP_PATH}: cannot be "
                                            "read as JSON")
    assert "shadow not judged" in next(x for x in doc["competitions"] if x["code"] == "NHL")["status_from"]
    assert lines[-1].endswith(f"roadmap null ({doc['roadmap_unread']}))")


def test_json_default_out_is_exports_coverage_of_the_coverage_day(env, monkeypatch, tmp_path):
    """Default --out exports/coverage_<date>.json, relative to the working directory as every export is; the date is
    the coverage day (--date, else today in US Eastern: 02:30Z on 10-18 is 10-17 ET). The mirror maps the name to
    latest/coverage.json (tests/test_exports_mirror.py)."""
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    make_db(env, [(401, "PL", "2026-10-17 14:00", "SCHEDULED")])
    assert run("--date", "2026-10-17", "--json")[0] == 0
    monkeypatch.setattr(cl, "clock", lambda: utc("2026-10-18 02:30"))
    assert run("--json")[0] == 0
    assert sorted(p.name for p in (work / "exports").iterdir()) == ["coverage_2026-10-17.json"]
    assert json.loads((work / "exports" / "coverage_2026-10-17.json").read_text())["now"] == "2026-10-18T02:30:00Z"
    assert cm.default_out(datetime(2026, 10, 19).date()) == "exports/coverage_2026-10-19.json"
    assert not (work / "data").exists()


def test_json_refusals_write_no_file(env, monkeypatch, tmp_path):
    """--out without --json, an --out under data/, a DB that cannot be read: exit 2, and no file is written."""
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    assert run("--date", DAY, "--out", "x.json") == (2, [
        "COVERAGE REFUSED: --out needs --json (the text output writes no file)"])
    assert run("--date", DAY, "--json", "--out", "y.json")[0] == 2          # no DB yet: refused, nothing created
    assert not env.exists() and list(work.iterdir()) == []
    make_db(env, [(401, "PL", "2026-10-17 14:00", "SCHEDULED")])
    rc, out = run("--date", DAY, "--json", "--out", "data/coverage.json")
    assert rc == 2 and out[0].startswith("COVERAGE REFUSED: --out data/coverage.json is under ")
    assert "(law 5: nothing is created under data/)" in out[0]
    assert not (work / "data").exists()
    assert cm._out_refusal(c.REPO / "data" / "x.json") is not None                # the checkout's data/ too


def test_json_an_out_at_the_top_of_exports_must_be_named_as_kind_coverage(env, monkeypatch, tmp_path):
    """#592's rule is a KIND rule (addendum 128 item 3): the compare lists kind coverage as machine state and never
    compares it. A coverage_v1 document written at the top of exports/ under another kind's name (exports/today.json:
    kind 'today') would be pushed, compared on its clock-dependent fields and read DIVERGENT (Codex review on #595), so
    it is refused, exit 2, nothing written. The kind's own names pass, and so does any name outside exports/'s top."""
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    make_db(env, [(401, "PL", "2026-10-17 14:00", "SCHEDULED")])
    rc, out = run("--date", DAY, "--json", "--out", "exports/today.json")
    assert rc == 2 and out[0].startswith("COVERAGE REFUSED: --out exports/today.json is a top-level exports/ file "
                                         "the mirror pushes as kind 'today', not 'coverage'")
    assert not (work / "exports").exists()
    assert cm._out_refusal(c.REPO / "exports" / "fixtures_PL_2026-10-17.json") is not None    # the checkout's too
    for ok in ("exports/coverage_2026-10-17.json", "exports/coverage.json", "exports/sub/today.json", "today.json"):
        assert cm._out_refusal(Path(ok)) is None, ok
    assert run("--date", DAY, "--json", "--out", "exports/coverage.json")[0] == 0


def test_json_an_out_that_names_no_file_is_refused_not_a_traceback(env, monkeypatch, tmp_path):
    """#597 item 1 (Codex on #595): `--out .` and `--out /` name no file; `out.with_name(...)` raised ValueError before
    the write's try, so the command ended in a traceback. Now COVERAGE REFUSED, exit 2, nothing written."""
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    make_db(env, [(401, "PL", "2026-10-17 14:00", "SCHEDULED")])
    for bad in (".", "/", ".."):
        assert run("--date", DAY, "--json", "--out", bad) == (2, [f"COVERAGE REFUSED: --out {bad} names no file"]), bad
    assert list(work.iterdir()) == []


def test_json_a_symlink_at_the_name_is_judged_where_the_file_lands(env, monkeypatch, tmp_path):
    """#597 item 2 (Codex on #595): the rules were checked on the resolved path only, so a symlink already at the name
    that points outside got past them, and the write then replaced the link itself with a regular file there: a
    coverage_v1 file at exports/today.json (kind 'today', compared and read DIVERGENT, #592), or a file created at a
    path under data/ (law 5). Both paths are checked now, the lexical and the resolved; the link is left as it was."""
    work = tmp_path / "work"
    (work / "exports").mkdir(parents=True)
    (work / "data").mkdir()                                       # a throwaway scratch folder of the test, not the DB's
    monkeypatch.chdir(work)
    make_db(env, [(401, "PL", "2026-10-17 14:00", "SCHEDULED")])
    outside = tmp_path / "outside.json"
    (work / "exports" / "today.json").symlink_to(outside)
    (work / "data" / "c.json").symlink_to(outside)
    rc, out = run("--date", DAY, "--json", "--out", "exports/today.json")
    assert rc == 2 and out[0].startswith("COVERAGE REFUSED: --out exports/today.json is a top-level exports/ file "
                                         "the mirror pushes as kind 'today', not 'coverage'")
    rc, out = run("--date", DAY, "--json", "--out", "data/c.json")
    assert rc == 2 and out[0].startswith("COVERAGE REFUSED: --out data/c.json is under ")
    assert (work / "exports" / "today.json").is_symlink() and (work / "data" / "c.json").is_symlink()
    assert not outside.exists()
    # a link elsewhere that points INTO data/ is refused too (the resolved path), as before
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere" / "c.json").symlink_to(work / "data" / "d.json")
    assert cm._out_refusal(tmp_path / "elsewhere" / "c.json") is not None


def test_the_json_carries_each_competitions_slate_line_in_the_lines_own_words(env, monkeypatch, tmp_path):
    """#606 item 2: the Today tile shows the SLATE line first, so the file carries it (`slate_line`), word for word as
    the console prints it under the competition's line; null where the competition has none (neither LIVE nor
    MARKET-ONLY). SA is MARKET-ONLY: its slate_line is its PAPER header (addendum 146 item 5(a), the ruling's
    addition), and its slate stays null (no gap)."""
    make_db(env, NFL_DAY + [(50, "SA", "2026-10-18 13:00", "SCHEDULED")], NFL_ROWS)
    monkeypatch.setattr(cl, "clock", lambda: utc("2026-10-18 10:00"))
    out = tmp_path / "cov.json"
    rc, lines = run("--date", "2026-10-18", "--json", "--out", str(out))
    assert rc == 0
    doc = json.loads(out.read_text())
    by = {x["code"]: x for x in doc["competitions"]}
    assert by["NFL"]["slate_line"] == "NFL SLATE · NO SLATE FILE — slate run due 07:00 ET"
    assert lines[lines.index(by["NFL"]["line"]) + 1] == by["NFL"]["slate_line"]
    assert by["SA"]["slate_line"] == f"SA {PAPER_HEAD} · 1 game · {PAPER_NOT_READ} · shadow 0 of 1"
    assert by["SA"]["slate"] is None and lines[lines.index(by["SA"]["line"]) + 1] == by["SA"]["slate_line"]
    assert doc["gaps"] == ["NFL: 2 GAMES, ROWS 2, NO SLATE FILE"]                    # the gaps: unchanged


def test_json_a_file_that_cannot_be_written_exits_2_and_leaves_no_partial(env, monkeypatch, tmp_path):
    make_db(env, [(401, "PL", "2026-10-17 14:00", "SCHEDULED")])
    (tmp_path / "taken").write_text("a file where the folder would be")
    rc, out = run("--date", DAY, "--json", "--out", str(tmp_path / "taken" / "c.json"))
    assert rc == 2 and out[0].startswith(f"COVERAGE REFUSED: --out {tmp_path / 'taken' / 'c.json'} cannot be written")
    target = tmp_path / "ok" / "c.json"
    import json as _json                                            # the writer's own json.dump
    boom = {"n": 0}

    def failing_dump(*a, **k):
        boom["n"] += 1
        raise OSError("disk full")
    monkeypatch.setattr(_json, "dump", failing_dump)
    rc, out = run("--date", DAY, "--json", "--out", str(target))
    assert (rc, boom["n"]) == (2, 1) and "disk full" in out[0]
    assert list((tmp_path / "ok").iterdir()) == []                  # no half-written file, no temporary left


@pytest.mark.parametrize("wal", [False, True], ids=["rollback-journal", "wal"])
def test_json_opens_no_write_transaction_and_makes_no_provider_call(env, monkeypatch, wal, tmp_path):
    """The no-write test above, with --json: the DB opened mode=ro, SELECTs only, its bytes unchanged, no network, no
    ORM session; the only new file is the --out file."""
    make_db(env, [(401, "PL", "2026-10-17 14:00", "SCHEDULED"), (501, "NHL", "2026-10-17 23:00", "SCHEDULED")],
            [(401, "v22", "2026-10-17 10:00")], wal=wal)
    outdir = tmp_path / "exports-here"
    outdir.mkdir()
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
    rc, out = run("--date", DAY, "--json", "--out", str(outdir / "coverage_2026-10-17.json"))
    assert rc == 0 and out[-1].startswith("COVERAGE JSON: ")
    assert opened and all(t.endswith("?mode=ro") and u is True for t, u in opened), opened
    assert statements and all(s.lstrip().upper().startswith("SELECT") for s in statements), statements
    assert hashlib.sha256(env.read_bytes()).hexdigest() == before
    new = {p.name for p in env.parent.iterdir()} - set(listing)
    assert new <= ({env.name + "-wal", env.name + "-shm"} if wal else set()), new
    sidecar = env.parent / (env.name + "-wal")
    assert not sidecar.exists() or sidecar.stat().st_size == 0
    assert sorted(p.name for p in outdir.iterdir()) == ["coverage_2026-10-17.json"]


def test_json_carries_a_status_coverage_adds_later_generically(pin, tmp_path, monkeypatch):
    """_plain is generic: a field or status coverage() gains later (the POT branch: status POT, label "POT (training
    data only)") rides into the file as it is, never dropped or translated."""
    real = cm.coverage

    def with_pot(*a, **k):
        cov = real(*a, **k)
        cov["competitions"][0].update(status="POT", status_label="POT (training data only)", pot={"from": {"x"}})
        return cov
    monkeypatch.setattr(cm, "coverage", with_pot)
    out = tmp_path / "c.json"
    assert run("--date", DAY, "--json", "--out", str(out))[0] == 0
    x = json.loads(out.read_text())["competitions"][0]
    assert (x["status"], x["status_label"], x["pot"]) == ("POT", "POT (training data only)", {"from": ["x"]})


# ---------------------------------------------------------- THE PAPER LINE (addendum 146 item 5(a)) --
# ARCHITECT 2026-10-20 09:59 ET, addendum 146 item 5(a), verbatim: "(a) coverage's SLATE line for a market-only
# competition carries, per game, the Kalshi mid (two-way, or the three-way mids) and, where a shadow export exists for
# the day, the shadow's pick and value side with their divergence against the mid, labelled PAPER and never a call. NHL
# today has a shadow (v7, FAILED gate); CL and NCAA have none and show the market line only."

NHL_GAME = [(501, "NHL", "2026-10-17 23:00", "SCHEDULED")]                    # 19:00 ET, the clock at 08:10 ET
TWO_WAY = [(501, "ML", "HOME", "2026-10-17 11:58", 0.54, 0.55), (501, "ML", "AWAY", "2026-10-17 11:58", 0.45, 0.46)]
V7_VERDICT = "FAILED 0.6885 vs 0.6866"


def nhl_shadow_file(rows, exported_at="2026-10-16T16:00:00", name="nhl_shadow_2026-10-16_1600.json"):
    """A shadow export in nhl_shadow.export's doc shape (the fit block made, no fallback): its rows are the fixtures row
    plus the shadow's keys."""
    doc = {"sport": "nhl", "engine": "model_shadow", "model_version": V7, "gate_verdict": V7_VERDICT,
           "reference_model": {"model_version": "nhl_elo_v1", "gate_verdict": "FAILED"},
           "contains_predictions": False, "exported_at": exported_at, "window_hours": 36, "note": "shadow",
           "fit": {"xg_model": "frozen 2023-24", "goal_margin_fallbacks": 0}, "skipped": {}, "count": len(rows),
           "predictions": rows}
    (c.REPO / "exports" / name).write_text(json.dumps(doc))


def shadow_row(mid, home_p, utc_date="2026-10-17T23:00:00", home="Home", away="Away"):
    return {"match_id": mid, "home_team": home, "away_team": away, "utc_date": utc_date, "competition": "X",
            "engine": "model_shadow", "model_version": V7, "gate_verdict": V7_VERDICT,
            "prediction": {"home_win_prob": home_p, "away_win_prob": round(1 - home_p, 4),
                           "top_pick": "home_win" if home_p >= 0.5 else "away_win"}}


def paper_of(out, code):
    return [x for x in out if x.startswith(f"{code} SLATE")]


def test_paper_nhl_the_two_way_mid_and_the_v7_shadow(env):
    make_db(env, NHL_GAME, kalshi=TWO_WAY)
    nhl_shadow_file([shadow_row(501, 0.60)])
    rc, out = run("--date", DAY)
    assert rc == 0
    assert paper_of(out, "NHL") == [
        f"NHL {PAPER_HEAD} · 1 game · Kalshi mid 1 of 1 · shadow 1 of 1",
        "NHL SLATE · PAPER · 501 Away @ Home 19:00 ET · Kalshi mid HOME 0.545 / AWAY 0.455 (bid 0.54, ask 0.55, 1c; "
        f"captured 2026-10-17 07:58 ET) · shadow {V7} ({V7_VERDICT}; exported 2026-10-16 12:00 ET): pick HOME 0.600 "
        "(+5.5pp vs mid); value side HOME (+5.5pp)"]
    assert out.index(paper_of(out, "NHL")[0]) == out.index(line_of(out, "NHL")) + 1
    assert out[-1] == "GAPS: none"                                             # PAPER never claims a gap


def test_paper_the_pick_and_the_value_side_can_differ(env):
    make_db(env, NHL_GAME, kalshi=[(501, "ML", "HOME", "2026-10-17 11:58", 0.59, 0.61)])     # mid 0.60, 2c
    nhl_shadow_file([shadow_row(501, 0.55)])
    line = paper_of(run("--date", DAY)[1], "NHL")[1]
    assert line.endswith("pick HOME 0.550 (-5.0pp vs mid); value side AWAY (+5.0pp)")
    assert "Kalshi mid HOME 0.600 / AWAY 0.400 (bid 0.59, ask 0.61, 2c; " in line


def test_paper_ncaa_with_a_quote_and_no_shadow_shows_the_market_line_only(env):
    make_db(env, [(601, "NCAA", "2026-10-17 16:00", "SCHEDULED")],
            kalshi=[(601, "ML", "HOME", "2026-10-17 10:00", 0.30, 0.31)])
    assert paper_of(run("--date", DAY)[1], "NCAA") == [
        f"NCAA {PAPER_HEAD} · 1 game · Kalshi mid 1 of 1 · shadow 0 of 1",
        "NCAA SLATE · PAPER · 601 Away @ Home 12:00 ET · Kalshi mid HOME 0.305 / AWAY 0.695 (bid 0.30, ask 0.31, 1c; "
        f"captured 2026-10-17 06:00 ET) · {NO_SHADOW}"]


CL_LEGS = [(801, "1X2", "HOME", "2026-10-17 11:58", 0.44, 0.45), (801, "1X2", "AWAY", "2026-10-17 11:58", 0.27, 0.28)]


@pytest.mark.parametrize("draw,head,mids", [
    ((0.27, 0.28), "Kalshi mid 1 of 1",
     "Kalshi mids HOME 0.445 / DRAW 0.275 / AWAY 0.275 (raw per leg, not normalized, display only; sum 0.995; captured "
     "2026-10-17 07:58 ET)"),
    ((0.27, 0.30), "Kalshi mid 0 of 1",
     "Kalshi mids HOME 0.445 / DRAW — / AWAY 0.275 (raw per leg, not normalized, display only; sum —; captured "
     "2026-10-17 07:58 ET)")], ids=["three-legs-1c", "draw-3c-wide"])
def test_paper_cl_three_way_mids(env, draw, head, mids):
    make_db(env, [(801, "CL", "2026-10-17 19:00", "SCHEDULED")],
            kalshi=CL_LEGS + [(801, "1X2", "DRAW", "2026-10-17 11:58", *draw)])
    assert paper_of(run("--date", DAY)[1], "CL") == [
        f"CL {PAPER_HEAD} · 1 game · {head} · shadow 0 of 1",
        f"CL SLATE · PAPER · 801 Away @ Home 15:00 ET · {mids} · {NO_SHADOW}"]


@pytest.mark.parametrize("quotes", [
    [(501, "ML", "HOME", "2026-10-17 11:58", 0.52, 0.55), (501, "ML", "HOME", "2026-10-17 10:00", 0.54, 0.55)],
    [(501, "ML", "HOME", "2026-10-17 11:58", 0.54, None), (501, "ML", "AWAY", "2026-10-17 11:58", 0.45, 0.46)],
], ids=["3c-wide-older-1c-never-substituted", "bid-only-home"])
def test_paper_no_two_sided_quote_within_the_cap_is_no_mid(env, quotes):
    make_db(env, NHL_GAME, kalshi=quotes)
    out = run("--date", DAY)[1]
    assert paper_of(out, "NHL")[0].endswith("· Kalshi mid 0 of 1 · shadow 0 of 1")
    assert " · Kalshi: no mid (no two-sided pre-kickoff quote within the 2c cap) · " in paper_of(out, "NHL")[1]


def test_paper_no_row_for_the_game_is_no_quote_stored(env):
    make_db(env, NHL_GAME, kalshi=[(999, "ML", "HOME", "2026-10-17 11:58", 0.54, 0.55)])
    assert " · Kalshi: no quote stored · " in paper_of(run("--date", DAY)[1], "NHL")[1]


def test_paper_legs_of_two_events_are_mismatched_and_show_no_mid(env):
    make_db(env, NHL_GAME, kalshi=[(501, "ML", "HOME", "2026-10-17 11:58", 0.54, 0.55, "KXNHLGAME-26OCT17AAABBB-BBB"),
                                   (501, "ML", "AWAY", "2026-10-17 11:58", 0.45, 0.46, "KXNHLGAME-26OCT17CCCDDD-CCC")])
    nhl_shadow_file([shadow_row(501, 0.60)])
    line = paper_of(run("--date", DAY)[1], "NHL")[1]
    assert (" · Kalshi: mismatched legs (KXNHLGAME-26OCT17AAABBB, KXNHLGAME-26OCT17CCCDDD): no mid (addendum 37 item 3)"
            " · ") in line
    assert line.endswith("pick HOME 0.600 (no mid: no divergence); value side not judged (no mid)")


AB, CD = "KXNHLGAME-26OCT17AAABBB", "KXNHLGAME-26OCT17CCCDDD"


def test_paper_the_older_home_quote_the_mid_reads_is_judged_with_the_newest_legs(env):
    """#641 item 1 RULED (ARCHITECT 2026-10-21, addendum 152 item 4(a)): "judge the rows a PAPER mid reads with
    close_row_mismatched; a hit prints "mismatched legs ... no mid"." Codex's round-2 shape on #640: 501's newest legs
    (11:58, HOME bid-less) are all of AAABBB, so kalshi_legs.mismatched passes it, and the mid falls back to the older
    two-sided HOME quote (10:00) of CCCDDD, whose current legs sit on 502. Before: 501 printed 502's contract as its mid
    (HOME 0.605 / AWAY 0.395, captured 06:00 ET; the header read "Kalshi mid 2 of 2"). Now: no mid; 502 is unchanged."""
    make_db(env, NHL_GAME + [(502, "NHL", "2026-10-17 23:30", "SCHEDULED")], kalshi=[
        (501, "ML", "HOME", "2026-10-17 11:58", None, 0.55, f"{AB}-BBB"),
        (501, "ML", "AWAY", "2026-10-17 11:58", 0.45, 0.46, f"{AB}-AAA"),
        (501, "ML", "HOME", "2026-10-17 10:00", 0.60, 0.61, f"{CD}-DDD"),
        (502, "ML", "HOME", "2026-10-17 11:58", 0.60, 0.61, f"{CD}-DDD"),
        (502, "ML", "AWAY", "2026-10-17 11:58", 0.39, 0.40, f"{CD}-CCC")])
    lines = paper_of(run("--date", DAY)[1], "NHL")
    assert lines[0].endswith("· Kalshi mid 1 of 2 · shadow 0 of 2")
    assert f" · Kalshi: mismatched legs ({AB}, {CD}): no mid (addendum 37 item 3) · " in lines[1]
    assert " · Kalshi mid HOME 0.605 / AWAY 0.395 (bid 0.60, ask 0.61, 1c; " in lines[2]


def test_paper_a_three_way_leg_the_mids_read_from_another_event_shows_no_mid(env):
    """#641 item 1 on a three-way board: CL 801's newest legs (11:58) are all of event XXXYYY, the DRAW's bid-less, so
    leg_mids reads the DRAW's older two-sided quote (10:00) of event ZZZWWW: "mismatched legs ... no mid", never a
    DRAW mid from another event's contract."""
    xy, zw = "KXUCLGAME-26OCT17XXXYYY", "KXUCLGAME-26OCT17ZZZWWW"
    make_db(env, [(801, "CL", "2026-10-17 19:00", "SCHEDULED")], kalshi=[
        (801, "1X2", "HOME", "2026-10-17 11:58", 0.44, 0.45, f"{xy}-XXX"),
        (801, "1X2", "AWAY", "2026-10-17 11:58", 0.27, 0.28, f"{xy}-YYY"),
        (801, "1X2", "DRAW", "2026-10-17 11:58", None, 0.28, f"{xy}-TIE"),
        (801, "1X2", "DRAW", "2026-10-17 10:00", 0.27, 0.28, f"{zw}-TIE")])
    lines = paper_of(run("--date", DAY)[1], "CL")
    assert lines[0].endswith("· Kalshi mid 0 of 1 · shadow 0 of 1")
    assert f" · Kalshi: mismatched legs ({xy}, {zw}): no mid (addendum 37 item 3) · " in lines[1]


def test_paper_a_mid_read_from_the_newest_legs_event_is_shown_as_before(env):
    """The same rows on one event: the mids read are judged and pass, so the line is as before (two-way and
    three-way)."""
    make_db(env, NHL_GAME + [(801, "CL", "2026-10-17 19:00", "SCHEDULED")], kalshi=[
        (501, "ML", "HOME", "2026-10-17 11:58", 0.54, 0.55, f"{AB}-BBB"),
        (501, "ML", "AWAY", "2026-10-17 11:58", 0.45, 0.46, f"{AB}-AAA"),
        *((*x, f"KXUCLGAME-26OCT17XXXYYY-{x[2]}") for x in CL_LEGS),
        (801, "1X2", "DRAW", "2026-10-17 11:58", 0.27, 0.28, "KXUCLGAME-26OCT17XXXYYY-TIE")])
    out = run("--date", DAY)[1]
    assert paper_of(out, "NHL")[0].endswith("· Kalshi mid 1 of 1 · shadow 0 of 1")
    assert paper_of(out, "CL")[1].startswith("CL SLATE · PAPER · 801 Away @ Home 15:00 ET · Kalshi mids HOME 0.445 / "
                                             "DRAW 0.275 / AWAY 0.275 ")


def test_paper_a_shadow_after_kickoff_is_never_used_and_another_games_row_is_not_shown(env):
    make_db(env, NHL_GAME + [(502, "NHL", "2026-10-17 23:30", "SCHEDULED")], kalshi=TWO_WAY)
    nhl_shadow_file([shadow_row(501, 0.60)], exported_at="2026-10-17T23:05:00", name="nhl_shadow_2026-10-17_2305.json")
    nhl_shadow_file([shadow_row(502, 0.58, utc_date="2026-10-17T23:30:00", home="Other Home")])
    lines = paper_of(run("--date", DAY)[1], "NHL")
    assert lines[0].endswith("· Kalshi mid 1 of 2 · shadow 0 of 2")
    assert lines[1].endswith(f"· {NO_SHADOW}")                                  # exported after its puck drop
    assert lines[2].endswith("· Kalshi: no quote stored · shadow: row names Away @ Other Home, not this game: not shown")


def test_paper_a_started_game_shows_its_last_pre_kickoff_quote(env, monkeypatch):
    monkeypatch.setattr(cl, "clock", lambda: utc("2026-10-17 23:20"))
    make_db(env, NHL_GAME, kalshi=TWO_WAY + [(501, "ML", "HOME", "2026-10-17 23:10", 0.80, 0.81)])   # in play: never
    line = paper_of(run("--date", DAY)[1], "NHL")[1]
    assert line.startswith("NHL SLATE · PAPER · 501 Away @ Home 19:00 ET (started) · Kalshi mid HOME 0.545 / ")


def test_paper_only_market_only_competitions_and_never_an_all_void_day(env):
    make_db(env, [(702, "EL2", "2026-10-17 14:00", "SCHEDULED"), (704, "EL1", "2026-10-17 14:00", "SCHEDULED"),
                  (401, "PL", "2026-10-17 14:00", "SCHEDULED"), (601, "NCAA", "2026-10-17 16:00", "CANCELLED")],
            kalshi=[(i, "ML", "HOME", "2026-10-17 11:00", 0.5, 0.51) for i in (702, 704, 401, 601)])
    out = run("--date", DAY)[1]
    assert not [x for x in out if " SLATE · PAPER" in x]
    cov = cm.coverage(datetime(2026, 10, 17).date(), NOW)
    assert {x["code"]: x["paper"] for x in cov["competitions"]} == {"PL": None, "EL2": None, "NCAA": None, "EL1": None}


def _keys(v):
    if isinstance(v, dict):
        return set(v) | {k for w in v.values() for k in _keys(w)}
    if isinstance(v, list):
        return {k for w in v for k in _keys(w)}
    return set()


def test_paper_json_carries_paper_and_paper_lines_in_the_lines_own_words(env, tmp_path):
    make_db(env, NHL_GAME + [(601, "NCAA", "2026-10-17 16:00", "SCHEDULED")], kalshi=TWO_WAY)
    nhl_shadow_file([shadow_row(501, 0.60)])
    out = tmp_path / "cov.json"
    rc, lines = run("--date", DAY, "--json", "--out", str(out))
    assert rc == 0
    doc = json.loads(out.read_text())
    for x in doc["competitions"]:
        assert x["status"] == "MARKET-ONLY" and x["slate"] is None
        assert x["slate_line"] == paper_of(lines, x["code"])[0] and x["paper_lines"] == paper_of(lines, x["code"])[1:]
        assert x["paper"]["label"] == "PAPER, never a call" and x["paper"]["ruling"] == "ARCHITECT 2026-10-20, addendum 146 item 5(a)"
        assert not {"call", "units", "order"} & _keys(x["paper"])
    nhl = next(x for x in doc["competitions"] if x["code"] == "NHL")["paper"]["games"][0]
    assert (nhl["board"], nhl["kalshi"]["fair"]["HOME"], nhl["kalshi"]["captured_at"], nhl["start"]) == \
        ("two-way", 0.545, "2026-10-17T11:58:00Z", "2026-10-17T23:00:00Z")
    assert (nhl["shadow"]["model_version"], nhl["shadow"]["exported_at"], nhl["shadow"]["value_side"]) == \
        (V7, "2026-10-16T16:00:00Z", "HOME")
    stamps = _datetimes(doc)
    assert stamps and all(ISO_Z.fullmatch(v) for _, v in stamps), [s for s in stamps if not ISO_Z.fullmatch(s[1])]


@pytest.mark.parametrize("wal", [False, True], ids=["rollback-journal", "wal"])
def test_paper_reads_odds_snapshots_read_only(env, monkeypatch, wal):
    """With odds_snapshots stored (and its ticker column, so the legs guard reads): the DB opened mode=ro, every statement
    a SELECT except exactly the guard's PRAGMA table_info(odds_snapshots), its bytes unchanged, no network, no ORM
    session. (The no-write test above reads a DB with no such table: no PRAGMA runs there.) The shadow read is read-only
    too: a shadow export in exports/ is shown, a decoy under exports/host/ (another game's row and other probabilities)
    is never read, and every file under exports/ keeps its name, bytes and mtime."""
    make_db(env, NHL_GAME + [(401, "PL", "2026-10-17 14:00", "SCHEDULED")], [(401, "v22", "2026-10-17 10:00")],
            wal=wal, kalshi=[(501, "ML", "HOME", "2026-10-17 11:58", 0.54, 0.55, "KXNHLGAME-26OCT17AAABBB-BBB"),
                             (501, "ML", "AWAY", "2026-10-17 11:58", 0.45, 0.46, "KXNHLGAME-26OCT17AAABBB-AAA")])
    nhl_shadow_file([shadow_row(501, 0.60)])
    host = c.REPO / "exports" / "host"
    host.mkdir()
    (host / "nhl_shadow_2026-10-17_0900.json").write_text(json.dumps(
        {"engine": "model_shadow", "model_version": V7, "gate_verdict": V7_VERDICT, "exported_at": "2026-10-17T09:00:00",
         "predictions": [shadow_row(501, 0.80)]}))

    def listing():
        ex = c.REPO / "exports"
        return sorted((str(q.relative_to(ex)), q.is_dir(), b"" if q.is_dir() else q.read_bytes(), q.stat().st_mtime_ns)
                      for q in [ex, *ex.rglob("*")])           # a folder's mtime moves when a file is made in it
    files_before = listing()
    before = hashlib.sha256(env.read_bytes()).hexdigest()
    real, opened, statements = sqlite3.connect, [], []

    def watched(target, *a, **k):
        con = real(target, *a, **k)
        opened.append((str(target), k.get("uri")))
        con.set_trace_callback(statements.append)
        return con

    def refuse(*a, **k):
        raise AssertionError("coverage made a network call or opened an ORM session")

    monkeypatch.setattr(sqlite3, "connect", watched)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)
    import src.db.database as dbm
    monkeypatch.setattr(sys.modules["cli"], "session_scope", refuse)
    monkeypatch.setattr(dbm, "session_scope", refuse)
    rc, out = run("--date", DAY)
    assert rc == 0 and paper_of(out, "NHL")[0].endswith("· Kalshi mid 1 of 1 · shadow 1 of 1")
    assert paper_of(out, "NHL")[1].endswith(f"shadow {V7} ({V7_VERDICT}; exported 2026-10-16 12:00 ET): pick HOME 0.600 "
                                            "(+5.5pp vs mid); value side HOME (+5.5pp)")      # exports/, never host/
    assert listing() == files_before
    assert len(opened) == 2 and all(t.endswith("?mode=ro") and u is True for t, u in opened), opened
    other = [x for x in statements if not x.lstrip().upper().startswith("SELECT")]
    # read-only PRAGMAs only: the ticker column is checked by kalshi_legs.mismatched and, for the rows a mid reads, by
    # read_paper (#641 item 1), each a PRAGMA table_info, never a write
    assert other and set(other) == {"PRAGMA table_info(odds_snapshots)"}, other
    assert any("FROM odds_snapshots" in x for x in statements)
    assert hashlib.sha256(env.read_bytes()).hexdigest() == before


def test_paper_lines_never_carry_a_call_an_order_or_units(env):
    make_db(env, NHL_GAME + [(801, "CL", "2026-10-17 19:00", "SCHEDULED")],
            kalshi=TWO_WAY + CL_LEGS + [(801, "1X2", "DRAW", "2026-10-17 11:58", 0.27, 0.28)])
    nhl_shadow_file([shadow_row(501, 0.60)])
    paper = [x for x in run("--date", DAY)[1] if " SLATE · PAPER" in x]
    assert len(paper) == 4
    for x in paper:
        assert "PLAY" not in x and "BUY" not in x and not re.search(r"\d+(\.\d+)?u\b", x), x


def test_paper_a_started_three_way_game_shows_its_last_pre_kickoff_legs(env, monkeypatch):
    """R21 on a three-way board: CL 801 LIVE at 19:30Z; its legs at 11:58Z and an in-play HOME quote at 19:20Z (never
    used: each leg reads its last two-sided quote before kickoff)."""
    monkeypatch.setattr(cl, "clock", lambda: utc("2026-10-17 19:30"))
    make_db(env, [(801, "CL", "2026-10-17 19:00", "LIVE")],
            kalshi=CL_LEGS + [(801, "1X2", "DRAW", "2026-10-17 11:58", 0.27, 0.28),
                              (801, "1X2", "HOME", "2026-10-17 19:20", 0.80, 0.81)])
    line = paper_of(run("--date", DAY)[1], "CL")[1]
    assert line.startswith("CL SLATE · PAPER · 801 Away @ Home 15:00 ET (started) · Kalshi mids HOME 0.445 / DRAW "
                           "0.275 / AWAY 0.275 (raw per leg, not normalized, display only; sum 0.995; captured "
                           "2026-10-17 07:58 ET)")


def test_paper_a_mixed_board_is_not_read(env):
    """ML HOME/AWAY and a 1X2 DRAW row stored for one game: never read as either board."""
    make_db(env, NHL_GAME, kalshi=TWO_WAY + [(501, "1X2", "DRAW", "2026-10-17 11:58", 0.20, 0.21)])
    lines = paper_of(run("--date", DAY)[1], "NHL")
    assert lines[0].endswith("· Kalshi mid 0 of 1 · shadow 0 of 1")
    assert " · Kalshi: ML and 1X2 rows both stored: not read · " in lines[1]


def test_paper_a_game_two_shadow_exports_hold_is_not_shown(env):
    import src.walters.ncaa_shadow as ns
    make_db(env, NHL_GAME, kalshi=TWO_WAY)
    nhl_shadow_file([shadow_row(501, 0.60)])
    doc = {"engine": "model_shadow", "competition": "NCAA", "exported_at": "2026-10-16T16:00:00",
           "predictions": [shadow_row(501, 0.62)]}
    (c.REPO / "exports" / f"{ns.FILE_PREFIX}2026-10-16_1600.json").write_text(json.dumps(doc))
    lines = paper_of(run("--date", DAY)[1], "NHL")
    assert lines[0].endswith("· Kalshi mid 1 of 1 · shadow 0 of 1")
    assert lines[1].endswith(" · shadow: two shadow exports hold it: not shown")


def test_paper_a_shadow_export_that_cannot_be_read_is_named(env):
    """A shadow file that is a JSON list: the module's last_calls raises; its shadows are not read, named."""
    make_db(env, NHL_GAME, kalshi=TWO_WAY)
    nhl_shadow_file([shadow_row(501, 0.60)])
    (c.REPO / "exports" / "nhl_shadow_2026-10-16_1700.json").write_text("[1, 2]")
    lines = paper_of(run("--date", DAY)[1], "NHL")
    assert lines[0].endswith("· Kalshi mid 1 of 1 · shadow not read (nhl_shadow: AttributeError)")
    assert lines[1].endswith(" · shadow: not read (nhl_shadow: AttributeError)")


def test_paper_a_row_with_no_pick_is_not_shown(env):
    make_db(env, NHL_GAME, kalshi=TWO_WAY)
    r = shadow_row(501, 0.60)
    del r["prediction"]["top_pick"]
    nhl_shadow_file([r])
    assert paper_of(run("--date", DAY)[1], "NHL")[1].endswith(" · shadow: the row carries no pick: not shown")


MALFORMED = {"prediction-a-list": ("prediction", ["junk"]), "prediction-text": ("prediction", "n/a"),
             "prob-text": ("home_win_prob", "0.6"), "prob-nan": ("home_win_prob", float("nan")),
             "top-pick-a-list": ("top_pick", ["home_win"])}


@pytest.mark.parametrize("key,value", list(MALFORMED.values()), ids=list(MALFORMED))
def test_paper_a_malformed_shadow_row_is_not_shown_and_the_page_stays_whole(env, key, value):
    """Law 4 and "it never stops a chain": one shadow row stored with a value of the wrong kind (json writes NaN by
    default) reads "the row cannot be read: not shown"; the LIVE PL line and the GAPS print exactly as with a good row,
    exit 0."""
    make_db(env, NHL_GAME + [(401, "PL", "2026-10-17 14:00", "SCHEDULED")], [(401, "v22", "2026-10-17 10:00")],
            kalshi=TWO_WAY)
    nhl_shadow_file([shadow_row(501, 0.60)])
    rc, good = run("--date", DAY)
    assert rc == 0
    r = shadow_row(501, 0.60)
    if key == "prediction":
        r["prediction"] = value
    else:
        r["prediction"][key] = value
    nhl_shadow_file([r])
    rc, out = run("--date", DAY)
    assert rc == 0
    assert line_of(out, "PL") == line_of(good, "PL") and gaps(out) == gaps(good)
    assert [x for x in out if x.startswith("PL ")] == [x for x in good if x.startswith("PL ")]
    assert paper_of(out, "NHL")[0].endswith("· Kalshi mid 1 of 1 · shadow 0 of 1")
    assert paper_of(out, "NHL")[1].endswith(" · shadow: the row cannot be read: not shown")


def test_paper_a_quote_that_cannot_be_read_is_not_shown_and_the_page_stays_whole(env):
    """A stored yes_bid that is text (SQLite does not enforce the column's type): that game's Kalshi part reads "cannot
    be read (ValueError): not shown"; the other game and the LIVE PL line print whole, exit 0."""
    make_db(env, NHL_GAME + [(502, "NHL", "2026-10-17 23:30", "SCHEDULED"),
                             (401, "PL", "2026-10-17 14:00", "SCHEDULED")], [(401, "v22", "2026-10-17 10:00")],
            kalshi=[(502, "ML", "HOME", "2026-10-17 11:58", 0.54, 0.55)])
    con = sqlite3.connect(env)
    con.execute("INSERT INTO odds_snapshots(match_id, market, selection, captured_at, source, yes_bid, yes_ask) VALUES "
                "(501, 'ML', 'HOME', ?, 'kalshi', '0.54x', 0.55)", (_ts(utc("2026-10-17 11:58")),))
    con.commit()
    con.close()
    rc, out = run("--date", DAY)
    assert rc == 0
    lines = paper_of(out, "NHL")
    assert lines[0].endswith("· 2 games · Kalshi mid 1 of 2 · shadow 0 of 2")
    assert " 501 Away @ Home 19:00 ET · Kalshi: cannot be read (ValueError): not shown · " in lines[1]
    assert " 502 Away @ Home 19:30 ET · Kalshi mid HOME 0.545 / " in lines[2]
    assert line_of(out, "PL").startswith("PL · 1 game · LIVE")


def test_paper_a_capture_time_that_cannot_be_read_says_so(env):
    """A stored Kalshi row whose captured_at is "garbage" is no quote before kickoff: a game left with no mid by it
    reads "Kalshi: cannot be read (a capture time cannot be read): not shown", never "no two-sided pre-kickoff quote";
    a game that still has a readable quote shows its mid; every other line and the GAPS are unchanged, exit 0."""
    make_db(env, NHL_GAME + [(502, "NHL", "2026-10-17 23:30", "SCHEDULED"),
                             (401, "PL", "2026-10-17 14:00", "SCHEDULED")], [(401, "v22", "2026-10-17 10:00")],
            kalshi=[(502, "ML", "HOME", "2026-10-17 11:58", 0.54, 0.55)])
    rc, good = run("--date", DAY)
    assert rc == 0 and " 501 Away @ Home 19:00 ET · Kalshi: no quote stored · " in paper_of(good, "NHL")[1]
    con = sqlite3.connect(env)
    for mid in (501, 502):
        con.execute("INSERT INTO odds_snapshots(match_id, market, selection, captured_at, source, yes_bid, yes_ask) "
                    "VALUES (?, 'ML', 'HOME', 'garbage', 'kalshi', 0.60, 0.61)", (mid,))
    con.commit()
    con.close()
    rc, out = run("--date", DAY)
    assert rc == 0
    lines = paper_of(out, "NHL")
    assert " 501 Away @ Home 19:00 ET · Kalshi: cannot be read (a capture time cannot be read): not shown · " in lines[1]
    assert lines[2] == paper_of(good, "NHL")[2]                       # 502: its readable quote's mid, as before
    assert lines[0] == paper_of(good, "NHL")[0]
    assert line_of(out, "PL") == line_of(good, "PL") and gaps(out) == gaps(good)


def test_paper_book_rows_in_odds_snapshots_never_make_a_board_mixed(env):
    """The real odds_snapshots holds book rows (market 1X2, another source) beside Kalshi's ML rows: only source kalshi
    is read, so the NHL board stays two-way with its mid."""
    make_db(env, NHL_GAME, kalshi=TWO_WAY)
    con = sqlite3.connect(env)
    con.execute("INSERT INTO odds_snapshots(match_id, market, selection, devig_prob, captured_at, source) VALUES "
                "(501, '1X2', 'HOME', 0.55, '2026-10-17 11:00:00.000000', 'consensus')")
    con.commit()
    con.close()
    line = paper_of(run("--date", DAY)[1], "NHL")[1]
    assert " · Kalshi mid HOME 0.545 / AWAY 0.455 (bid 0.54, ask 0.55, 1c; captured 2026-10-17 07:58 ET) · " in line


def test_paper_a_row_whose_away_team_differs_is_not_shown(env):
    make_db(env, NHL_GAME, kalshi=TWO_WAY)
    nhl_shadow_file([shadow_row(501, 0.60, away="Other")])
    assert paper_of(run("--date", DAY)[1], "NHL")[1].endswith(" · shadow: row names Other @ Home, not this game: not "
                                                              "shown")


def unl_file(rows, exported_at="2026-10-16T16:00:00"):
    """A UNL shadow export (intl_shadow's doc shape) in the scratch exports/."""
    doc = {"sport": "unl", "engine": "model_shadow", "model_version": "intl-elo-v2", "gate_verdict": "PASS",
           "contains_predictions": False, "exported_at": exported_at, "window_hours": 36, "note": "n", "fit": {},
           "count": len(rows), "predictions": rows}
    (c.REPO / "exports" / "unl_shadow_2026-10-16_1600.json").write_text(json.dumps(doc))


def unl_row(mid, ph, pd, pa, top):
    pred = {"home_win_prob": ph, "away_win_prob": pa, "top_pick": top}
    if pd is not None:
        pred["draw_prob"] = pd
    return {"match_id": mid, "home_team": "Home", "away_team": "Away", "utc_date": "2026-10-17T18:45:00",
            "engine": "model_shadow", "model_version": "intl-elo-v2", "gate_verdict": "PASS", "prediction": pred}


UNL_LEGS = [(901, "1X2", "HOME", "2026-10-17 11:58", 0.40, 0.41), (901, "1X2", "DRAW", "2026-10-17 11:58", 0.29, 0.30),
            (901, "1X2", "AWAY", "2026-10-17 11:00", 0.30, 0.31)]


def test_paper_three_way_legs_captured_apart_read_oldest_to_newest_and_a_draw_pick(env):
    """UNL 901: the AWAY leg captured an hour before the other two (the range reads oldest first); a three-way shadow
    picking DRAW is judged on all three legs."""
    make_db(env, [(901, "UNL", "2026-10-17 18:45", "SCHEDULED")], kalshi=UNL_LEGS)
    unl_file([unl_row(901, 0.33, 0.36, 0.31, "draw")])
    lines = paper_of(run("--date", DAY)[1], "UNL")
    assert lines[0].endswith("· 1 game · Kalshi mid 1 of 1 · shadow 1 of 1")
    assert ("Kalshi mids HOME 0.405 / DRAW 0.295 / AWAY 0.305 (raw per leg, not normalized, display only; sum 1.005; "
            "captured 2026-10-17 07:00 ET to 2026-10-17 07:58 ET)") in lines[1]
    assert lines[1].endswith("pick DRAW 0.360 (+6.5pp vs mid); value side DRAW (+6.5pp)")


def test_paper_a_two_way_shadow_on_a_three_way_board_is_never_judged(env):
    """A shadow row with no draw_prob against UNL's three legs: never judged on two of the three, and no divergence (a
    two-way p against a raw three-way mid is not comparable)."""
    make_db(env, [(901, "UNL", "2026-10-17 18:45", "SCHEDULED")], kalshi=UNL_LEGS)
    unl_file([unl_row(901, 0.50, None, 0.50, "home_win")])
    line = paper_of(run("--date", DAY)[1], "UNL")[1]
    assert line.endswith("pick HOME 0.500 (a two-way prediction on a three-way board: no divergence); value side not "
                         "judged (a two-way prediction on a three-way board)"), line


@pytest.mark.parametrize("home_p,tail", [
    (0.5454, "pick HOME 0.545 (+0.0pp vs mid); value side none (no side above its mid by 0.05pp or more, the printed "
             "precision)"),
    (0.5455, "pick HOME 0.545 (+0.1pp vs mid); value side HOME (+0.1pp)")], ids=["0.04pp", "0.05pp"])
def test_paper_the_value_side_is_judged_at_the_printed_precision(env, home_p, tail):
    """nhl_shadow rounds to 4 dp; against the 0.545 mid a side 0.04pp above prints +0.0pp and is no value side (said
    so), never "value side HOME (+0.0pp)"; 0.05pp prints +0.1pp and is one."""
    make_db(env, NHL_GAME, kalshi=TWO_WAY)
    nhl_shadow_file([shadow_row(501, home_p)])
    line = paper_of(run("--date", DAY)[1], "NHL")[1]
    assert line.endswith(tail), line


def test_paper_one_games_shadow_part_raising_leaves_the_page_whole(env, monkeypatch):
    """The per-game guard: whatever one game's shadow part raises (here IndexError, what a NaN probability raised in
    shadow_view before it read only finite numbers) reads "cannot be read (<Error>): not shown" for that game only."""
    from src.walters import paper

    def boom(pred, fair):
        raise IndexError("list index out of range")
    monkeypatch.setattr(paper, "shadow_view", boom)
    make_db(env, NHL_GAME + [(401, "PL", "2026-10-17 14:00", "SCHEDULED")], [(401, "v22", "2026-10-17 10:00")],
            kalshi=TWO_WAY)
    nhl_shadow_file([shadow_row(501, 0.60)])
    rc, out = run("--date", DAY)
    assert rc == 0 and line_of(out, "PL").startswith("PL · 1 game · LIVE")
    assert paper_of(out, "NHL")[1].endswith(" · shadow: cannot be read (IndexError): not shown")


def test_paper_a_wide_home_quote_and_an_unreadable_away_row_keep_the_caps_reason(env):
    """Two-way: the HOME leg's last quote is 3c wide (no mid by the cap); an AWAY ML row, which the mid never reads
    (close_from_kalshi reads the HOME leg), has an unreadable captured_at. The true reason is still the cap, never
    "a capture time cannot be read"."""
    nomid = "Kalshi: no mid (no two-sided pre-kickoff quote within the 2c cap)"
    make_db(env, NHL_GAME, kalshi=[(501, "ML", "HOME", "2026-10-17 11:58", 0.53, 0.56),
                                   (501, "ML", "AWAY", "2026-10-17 11:58", 0.44, 0.47)])
    assert nomid in paper_of(run("--date", DAY)[1], "NHL")[1]
    con = sqlite3.connect(env)
    con.execute("INSERT INTO odds_snapshots(match_id, market, selection, captured_at, source, yes_bid, yes_ask) "
                "VALUES (501, 'ML', 'AWAY', 'garbage', 'kalshi', 0.45, 0.46)")
    con.commit()
    con.close()
    line = paper_of(run("--date", DAY)[1], "NHL")[1]
    assert nomid in line and "a capture time cannot be read" not in line, line


def test_paper_a_three_way_shadow_on_a_three_way_board_with_a_leg_unpriced(env):
    """UNL: DRAW 3c wide (no mid). Coverage passes every leg of the board (None for the unpriced one), so a three-way
    shadow is "not judged (a leg has no mid)", never a shape mismatch, and its pick keeps its divergence."""
    make_db(env, [(901, "UNL", "2026-10-17 18:45", "SCHEDULED")],
            kalshi=[(901, "1X2", "HOME", "2026-10-17 11:58", 0.40, 0.41),
                    (901, "1X2", "DRAW", "2026-10-17 11:58", 0.28, 0.31),
                    (901, "1X2", "AWAY", "2026-10-17 11:58", 0.30, 0.31)])
    unl_file([unl_row(901, 0.45, 0.25, 0.30, "home_win")])
    line = paper_of(run("--date", DAY)[1], "UNL")[1]
    assert line.endswith("pick HOME 0.450 (+4.5pp vs mid); value side not judged (a leg has no mid)"), line


def test_paper_a_three_way_board_with_an_unreadable_draw_capture_time_says_so(env):
    """Three-way (verifier1 C1): every leg of the board is read, so a DRAW 1X2 row whose captured_at is "garbage" on a
    game left with no mid (HOME and AWAY each 3c wide) reads "a capture time cannot be read", never the cap's reason;
    the two-way rule (only the HOME leg's time counts) is not applied to a three-way board."""
    nomid = "Kalshi: no mid (no two-sided pre-kickoff quote within the 2c cap)"
    make_db(env, [(801, "CL", "2026-10-17 19:00", "SCHEDULED")],
            kalshi=[(801, "1X2", "HOME", "2026-10-17 11:58", 0.43, 0.46),
                    (801, "1X2", "AWAY", "2026-10-17 11:58", 0.26, 0.29)])
    rc, good = run("--date", DAY)
    assert rc == 0 and nomid in paper_of(good, "CL")[1]
    con = sqlite3.connect(env)
    con.execute("INSERT INTO odds_snapshots(match_id, market, selection, captured_at, source, yes_bid, yes_ask) "
                "VALUES (801, '1X2', 'DRAW', 'garbage', 'kalshi', 0.27, 0.28)")
    con.commit()
    con.close()
    rc, out = run("--date", DAY)
    assert rc == 0
    line = paper_of(out, "CL")[1]
    assert " 801 Away @ Home 15:00 ET · Kalshi: cannot be read (a capture time cannot be read): not shown · " in line
    assert nomid not in line and paper_of(out, "CL")[0] == paper_of(good, "CL")[0]


# ---- Codex round 1 on #640: the shadow row's kickoff (P2) and one module's failure (P2) ---------------------------

@pytest.mark.parametrize("recorded,tail", [
    ("2026-10-15T23:00:00", "shadow: the row is for another kickoff (re-dated): not shown"),
    ("2026-10-17T22:00:00", f"shadow {V7} ({V7_VERDICT}; exported 2026-10-15 12:00 ET): pick HOME 0.700 (+15.5pp vs "
                            "mid); value side HOME (+15.5pp)"),
    ("2026-10-17T21:59:00", "shadow: the row is for another kickoff (re-dated): not shown"),
    ("2026-10-17", "shadow: the row's kickoff cannot be read: not shown"),
    ("soon", "shadow: the row's kickoff cannot be read: not shown"),
], ids=["re-dated-2-days", "exactly-the-hour-shown", "61-minutes", "a-date-with-no-clock", "unreadable"])
def test_paper_a_shadow_row_for_another_kickoff_is_not_shown(env, recorded, tail):
    """Codex round 1 P2 on #640 (R17): NHL 501 now at 2026-10-17 23:00Z; a row recorded for another kickoff (the
    probe's 2026-10-15 23:00Z, exported 2026-10-15 16:00Z) printed "pick HOME 0.700 (+15.5pp vs mid)" as this game's
    shadow. The re-dated rule is redated.redated_label's (more than desk_policy.DESK_CLOCK_DRIFT apart; exactly the
    hour apart is the same kickoff); a recorded kickoff that cannot be read is not shown either, with its reason."""
    make_db(env, NHL_GAME, kalshi=TWO_WAY)
    nhl_shadow_file([shadow_row(501, 0.70, utc_date=recorded)], exported_at="2026-10-15T16:00:00",
                    name="nhl_shadow_2026-10-15_1600.json")
    lines = paper_of(run("--date", DAY)[1], "NHL")
    assert lines[1].endswith(f" · {tail}"), lines[1]
    assert lines[0].endswith("· shadow 1 of 1" if tail.startswith("shadow nhl") else "· shadow 0 of 1"), lines[0]


@pytest.mark.parametrize("exported,tail", [
    ("2026-10-17T23:15:00", "shadow: exported at or after the current kickoff (an in-play row): not shown"),
    ("2026-10-17T23:00:00", "shadow: exported at or after the current kickoff (an in-play row): not shown"),
    ("2026-10-17T22:45:00", f"shadow {V7} ({V7_VERDICT}; exported 2026-10-17 18:45 ET): pick HOME 0.700 (+15.5pp vs "
                            "mid); value side HOME (+15.5pp)"),
    ("2026-10-17T19:15:00-04:00", "shadow: exported at or after the current kickoff (an in-play row): not shown"),
], ids=["exported-after-the-current-start", "exported-at-the-current-start", "exported-before-it-shown",
        "an-offset-compared-as-utc"])
def test_paper_a_shadow_row_exported_at_or_after_the_current_kickoff_is_not_shown(env, exported, tail):
    """Codex round 2 P2 on #640: NHL 501 now at 2026-10-17 23:00Z; the row's recorded kickoff is 23:30Z (30 minutes
    apart: the same kickoff by the re-dated rule) and nhl_shadow.last_calls keeps a row exported before that RECORDED
    kickoff, so a row exported at 23:15Z, after the game's CURRENT start, printed as its shadow. Now a row exported at
    or after the current start is not shown (compared as UTC: 19:15 -04:00 is 23:15Z); exported 22:45Z it is shown."""
    make_db(env, NHL_GAME, kalshi=TWO_WAY)
    nhl_shadow_file([shadow_row(501, 0.70, utc_date="2026-10-17T23:30:00")], exported_at=exported,
                    name="nhl_shadow_2026-10-17_2315.json")
    from src.walters import nhl_shadow
    assert 501 in nhl_shadow.last_calls(str(c.REPO / "exports"))      # last_calls keeps it (before 23:30Z)
    lines = paper_of(run("--date", DAY)[1], "NHL")
    assert lines[1].endswith(f" · {tail}"), lines[1]
    assert lines[0].endswith("· shadow 1 of 1" if tail.startswith("shadow nhl") else "· shadow 0 of 1"), lines[0]


def test_paper_one_shadow_module_failing_hides_only_its_own_competitions(env):
    """Codex round 1 P2 on #640: an unreadable NHL shadow file (a JSON list: nhl_shadow.last_calls raises) hid UNL's
    valid intl_shadow row too ("shadow not read (nhl_shadow: AttributeError)" on every competition). Now the failure
    is tracked per module: NHL's header and games say so; UNL's row is shown."""
    make_db(env, NHL_GAME + [(901, "UNL", "2026-10-17 18:45", "SCHEDULED")], kalshi=TWO_WAY + UNL_LEGS)
    nhl_shadow_file([shadow_row(501, 0.60)])
    (c.REPO / "exports" / "nhl_shadow_2026-10-16_1700.json").write_text("[1, 2]")
    unl_file([unl_row(901, 0.33, 0.36, 0.31, "draw")])
    out = run("--date", DAY)[1]
    nhl, unl = paper_of(out, "NHL"), paper_of(out, "UNL")
    assert nhl[0].endswith("· Kalshi mid 1 of 1 · shadow not read (nhl_shadow: AttributeError)")
    assert nhl[1].endswith(" · shadow: not read (nhl_shadow: AttributeError)")
    assert unl[0].endswith("· 1 game · Kalshi mid 1 of 1 · shadow 1 of 1"), unl[0]
    assert unl[1].endswith("pick DRAW 0.360 (+6.5pp vs mid); value side DRAW (+6.5pp)"), unl[1]


def test_paper_the_intl_module_failing_never_hides_the_nhl_shadow(env):
    """The reverse: an unreadable UNL shadow file hides UNL's shadow only; NHL's v7 row is shown."""
    make_db(env, NHL_GAME + [(901, "UNL", "2026-10-17 18:45", "SCHEDULED")], kalshi=TWO_WAY + UNL_LEGS)
    nhl_shadow_file([shadow_row(501, 0.60)])
    (c.REPO / "exports" / "unl_shadow_2026-10-16_1700.json").write_text("[1, 2]")
    out = run("--date", DAY)[1]
    assert paper_of(out, "UNL")[0].endswith("· shadow not read (intl_shadow: AttributeError)")
    assert paper_of(out, "NHL")[0].endswith("· Kalshi mid 1 of 1 · shadow 1 of 1")
    assert paper_of(out, "NHL")[1].endswith("pick HOME 0.600 (+5.5pp vs mid); value side HOME (+5.5pp)")


def test_paper_each_shadow_modules_competitions_are_read_from_its_own_code():
    """paper.shadow_comps names every module of SHADOW_EXPORTS, and each one's competitions are the ones its own export
    reads (law 1): nhl_shadow.build_rows' Competition.code literal (the module has no constant), intl_shadow.build_rows'
    stream (intl_elo.STREAM_CODES less FRIENDLY), ncaa_shadow.COMPETITION, soccer_expansion.LEAGUES."""
    from src.walters import intl_elo, intl_shadow, ncaa_shadow, nhl_shadow, paper, soccer_expansion
    comps = paper.shadow_comps()
    assert set(comps) == {mod for mod, _ in cm.SHADOW_EXPORTS.values()}
    assert 'Competition.code == "NHL"' in inspect.getsource(nhl_shadow.build_rows) and \
        comps["src.walters.nhl_shadow"] == frozenset({"NHL"})
    assert "codes = [c for c in ie.STREAM_CODES if c != ie.FRIENDLY]" in inspect.getsource(intl_shadow.build_rows)
    assert comps["src.walters.intl_shadow"] == frozenset(c for c in intl_elo.STREAM_CODES if c != intl_elo.FRIENDLY)
    assert "UNL" in comps["src.walters.intl_shadow"]
    assert comps["src.walters.ncaa_shadow"] == frozenset({ncaa_shadow.COMPETITION})
    assert comps["src.walters.soccer_expansion"] == frozenset(soccer_expansion.LEAGUES)
