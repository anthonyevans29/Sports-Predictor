"""THE EXPORT SWITCH (lane leagues, #322): soccer_expansion.export_shadow and its command, on a throwaway SQLite file
(tests/test_record_vs_close.py iso_db) and a tmp registry (tests/test_leagues_window.py's `ledger`: the real
docs/registry/experiments.json is never written).
- ARCHITECT 2026-10-24, addendum 164 item 3, verbatim in part: "the prospective predictions for SA/BL1/FL1/ELC — and
  for PD (159 item 6(a)) — are produced by leagues_candidate.predict_as_of from the declaration on, bound to the run
  record's frozen parameters, never by price_upcoming."
- Addendum 178 R5, verbatim: "BEFORE THE DECLARATION the four leagues get no prospective rows (nothing is a shadow
  before it is declared); after it, predict_as_of rows labelled with the league's declared_at." R6: the export runs on
  the host only. R1: the stored rows are the cohort reader's audit receipt (leagues_window.stored_rows / audit).
Pins: parity with the gate path row for row; the frozen constants, never production's; R5 before and after; the
refused declarations; every in-window fixture a row or a reason; F3 (184 item 1); R6; the audit round trip; the
consumers; the registry read at call time."""
from __future__ import annotations

import itertools
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner

from src.db.schema import MatchStatus, Sport
from src.walters import leagues_candidate as lc
from src.walters import leagues_window as lw
from src.walters import soccer_expansion as sx
from tests.test_leagues_window import (AT, AT_TEXT, FROZEN, NOW, SEASON, _comps, _game, _legs, _priors, _teams,
                                       decl, ledger)  # noqa: F401  (ledger: a fixture)
from tests.test_record_vs_close import iso_db  # noqa: F401  (a fixture: a throwaway SQLite, cwd = tmp_path)

pytestmark = pytest.mark.usefixtures("iso_db")


@pytest.fixture(autouse=True)
def _iso_has_no_ticker_column(monkeypatch):
    """database.has_kalshi_ticker reads the module's engine (conftest's DB, which an earlier test may have migrated),
    not iso_db's: the throwaway file has no market_ticker column, so the export's ticker read is told the truth."""
    from src.db import database
    monkeypatch.setattr(database, "has_kalshi_ticker", lambda: False)

VERDICT_AT = "2026-10-09T12:47:39Z"
SX_DECLARED_AT = "2026-10-07T15:17:38Z"
# The soccer-expansion-v1 record as the registry holds it (run record v22 / -0.1 / 0.0008, PASS, surviving PD)
SXRUN = {"id": sx.EID, "status": "confirming", "declared_at": SX_DECLARED_AT,
         "run": {"result": {**FROZEN, "verdict": "PASS", "surviving": ["PD"], "per_league": {"PD": {"verdict": "PASS"}}}},
         "verdict": {"verdict": "PASS", "at": VERDICT_AT}}


def _pd():
    from src.db.database import session_scope
    from src.db.schema import Competition
    with session_scope() as s:
        s.add(Competition(sport=Sport.SOCCER, code="PD", name="PD", area="X", type="LEAGUE"))


def _world(ledger_write, *entries):
    """The four leagues and PD stored; the registry holds the soccer-expansion-v1 record and `entries`."""
    _comps()
    _pd()
    ledger_write(*entries, run=SXRUN)


def _set(mid, **kw):
    from src.db.database import session_scope
    from src.db.schema import Match
    with session_scope() as s:
        s.query(Match).filter_by(id=mid).update(kw)


def _finish(mid, hs, as_):
    _set(mid, status=MatchStatus.FINISHED, home_score=hs, away_score=as_, home_score_90=hs, away_score_90=as_,
         status_raw="FT")


def _export(now, hours=72, out=None):
    return sx.export_shadow(now=now, hours=hours, out_dir=str(out or Path("exports")))


def _league_season(code, base, start=datetime(2026, 8, 15, 14, 0), n_rounds=20):
    """6 teams, a regular round every 3-4 days (three games at one kickoff: F5's batch), plus two "Relegation Round"
    games the walk never reads (F3), an AWD prior with a 3-0 on its row (released by the one predicate) and an AET
    prior with its 90-minute 1-1 stored (walked on it)."""
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, Team
    with session_scope() as s:
        c = s.query(Competition).filter_by(code=code).one()
        teams = [Team(sport=c.sport, name=f"{code}{i}") for i in range(6)]
        s.add_all(teams)
        s.flush()
        ids = [t.id for t in teams]
        mid = base
        for r in range(n_rounds):
            ko = start + timedelta(days=3 * r + (r % 2))
            rot = ids[r % 6:] + ids[:r % 6]
            for k in range(3):
                h, a = (rot[2 * k], rot[2 * k + 1]) if r % 2 == 0 else (rot[2 * k + 1], rot[2 * k])
                hs, as_ = (r + k) % 3, (r * 2 + k) % 4 // 2
                s.add(Match(id=mid, sport=c.sport, competition_id=c.id, season=SEASON, utc_date=ko,
                            status=MatchStatus.FINISHED, home_team_id=h, away_team_id=a, home_score=hs,
                            away_score=as_, home_score_90=hs, away_score_90=as_, status_raw="FT",
                            stage=f"Regular Season - {r + 1}"))
                mid += 1
        for j in range(2):
            s.add(Match(id=mid + j, sport=c.sport, competition_id=c.id, season=SEASON,
                        utc_date=start + timedelta(days=20, hours=j), status=MatchStatus.FINISHED,
                        home_team_id=ids[j], away_team_id=ids[j + 2], home_score=3, away_score=0,
                        home_score_90=3, away_score_90=0, status_raw="FT", stage="Relegation Round"))
        s.add(Match(id=mid + 2, sport=c.sport, competition_id=c.id, season=SEASON,
                    utc_date=start + timedelta(days=25, hours=2), status=MatchStatus.FINISHED, home_team_id=ids[0],
                    away_team_id=ids[5], home_score=3, away_score=0, status_raw="AWD", stage="Regular Season - 9"))
        s.add(Match(id=mid + 3, sport=c.sport, competition_id=c.id, season=SEASON,
                    utc_date=start + timedelta(days=31, hours=2), status=MatchStatus.FINISHED, home_team_id=ids[1],
                    away_team_id=ids[4], home_score=2, away_score=1, home_score_90=1, away_score_90=1,
                    status_raw="AET", stage="Regular Season - 11"))
        return ids


# ------------------------------------------------------------------------------------------- 1. parity --

@pytest.mark.parametrize("code", ["PD", "SA"])
def test_1_shadow_entry_equals_the_gate_path_row_for_row(ledger, code):
    """158 item 2(a) on the export's own function: every finished regular-round game the gate scores is priced by
    shadow_entry (prospective=False) within PARITY_TOL, and equal once rounded by shadow_prob; nothing priced by one
    path only. PD (never fenced) and SA with its verdict recorded (the fence lifted)."""
    from src.db.database import session_scope
    from src.walters.soccer_expansion import unscoreable
    _world(ledger, decl("SA", verdict={"verdict": "PASS"}))
    _league_season(code, 5000)
    gate = {r["match_id"]: r for r in lc.gate_rows(code, SEASON, -0.1, 0.0008)}
    assert gate
    with session_scope() as s:
        rows = lc._season_rows(s, code, SEASON)
        mine = {}
        for m in rows:
            if not sx.is_regular(m.stage) or unscoreable(m):
                continue
            pred, x = sx.shadow_entry(rows, m, FROZEN, None, prospective=False)
            if pred is not None:
                mine[m.id] = (pred.p_home, pred.p_draw, pred.p_away)
                assert x["n_prior"] == len(lc.priors(rows, m)) >= sx.MIN_PRIOR
        s.rollback()
    assert set(mine) == set(gate)
    for i, p in mine.items():
        g = (gate[i]["p_home"], gate[i]["p_draw"], gate[i]["p_away"])
        assert max(abs(a - b) for a, b in zip(p, g)) <= lc.PARITY_TOL
        assert tuple(map(sx.shadow_prob, p)) == tuple(map(sx.shadow_prob, g))
    p = lc.parity(code, -0.1, 0.0008, now=NOW)
    assert (p["unequal"], p["shadow_only"], p["gate_only"], p["released"]) == (0, [], [], 1)


def test_1_priors_is_predict_as_ofs_own_selection(ledger):
    """lc.priors lifted out of predict_as_of with no behaviour change: the AWD prior is released, the AET prior is
    walked, the play-off rows and the same-kickoff rows are never read."""
    from src.db.database import session_scope
    from src.db.schema import Match
    _world(ledger)
    _league_season("SA", 5000)
    with session_scope() as s:
        rows = lc._season_rows(s, "SA", SEASON)
        fx = s.get(Match, 5059)
        got = lc.priors(rows, fx)
        assert [m.utc_date for m in got] == sorted(m.utc_date for m in got)
        ids = {m.id for m in got}
        assert 5062 not in ids and 5063 in ids and not ids & {5060, 5061}
        assert all(m.utc_date < fx.utc_date for m in got) and 5057 not in ids and 5058 not in ids   # F5: same kickoff
        s.rollback()


# ------------------------------------------------------------------------------- 2. frozen, not production --

def test_2_the_rows_are_the_run_records_constants_never_the_production_models(ledger, monkeypatch, tmp_path):
    import cli
    from src.db.database import session_scope
    from src.db.schema import Match
    _world(ledger)
    t = _teams("PD")
    _priors("PD", t)
    _game(900, "PD", NOW + timedelta(hours=5), (t[0], t[1]), MatchStatus.SCHEDULED)
    monkeypatch.setattr(lc, "production_poisson", lambda: ("v99", -0.2, 0.002))
    monkeypatch.setattr(cli, "_soccer_prod_poisson", lambda: ("v99", -0.2, 0.002))
    _, doc = _export(NOW, out=tmp_path)
    (r,) = doc["predictions"]
    with session_scope() as s:
        want, _ = lc.predict_as_of(lc._season_rows(s, "PD", SEASON), s.get(Match, 900), -0.1, 0.0008)
        s.rollback()
    assert (r["prediction"]["home_win_prob"], r["prediction"]["draw_prob"], r["prediction"]["away_win_prob"]) == \
        tuple(sx.shadow_prob(x) for x in (want.p_home, want.p_draw, want.p_away))
    assert r["model_version"] == doc["model_version"] == "v22" and r["frozen_constants"] == FROZEN
    assert doc["frozen_constants"] == FROZEN


# -------------------------------------------------------------------------------------------------- R5 --

def test_3_before_the_declaration_the_four_have_no_rows_and_pd_does(ledger, tmp_path):
    _world(ledger)
    for code, base in (("PD", 1000), ("SA", 3000)):
        t = _teams(code)
        _priors(code, t, base=base)
        _game(base + 900, code, NOW + timedelta(hours=5), (t[0], t[1]), MatchStatus.SCHEDULED)
    _, doc = _export(NOW, out=tmp_path)
    assert {r["competition"] for r in doc["predictions"]} == {"PD"}
    for code in ("SA", "BL1", "FL1", "ELC"):
        assert doc["bindings"][code]["state"] == sx.SHADOW_NOT_DECLARED and doc["counts"][code] == {}
    assert not [x for x in doc["missing"] if x["competition"] != "PD"]
    pd = doc["bindings"]["PD"]
    assert pd == {"state": "exporting", "candidate": sx.EID, "declared_at": SX_DECLARED_AT,
                  "window_opens_at": VERDICT_AT, "frozen_constants": FROZEN}
    (r,) = doc["predictions"]
    assert (r["declared_at"], r["window_opens_at"], r["candidate"], r["experiment"]) == (SX_DECLARED_AT, VERDICT_AT,
                                                                                         sx.EID, sx.EID)
    assert r["gate_verdict"] == "PASS · verdict PASS · confirmation open"


def test_4_after_the_declaration_rows_carry_the_entry_text_byte_for_byte(ledger, monkeypatch, tmp_path):
    _world(ledger, decl("SA"))
    monkeypatch.setattr(lc, "code_sha", lambda: "abc1234")
    t = _teams("SA")
    rest = _priors("SA", t)
    now = AT - timedelta(hours=2)
    _game(2001, "SA", AT - timedelta(hours=1), rest[0], MatchStatus.SCHEDULED)
    _game(2002, "SA", AT, rest[1], MatchStatus.SCHEDULED)                                # at the instant: not after
    _game(2003, "SA", AT + timedelta(hours=1), rest[2], MatchStatus.SCHEDULED)
    path, doc = _export(now, out=tmp_path)
    (r,) = [x for x in doc["predictions"] if x["competition"] == "SA"]
    assert r["match_id"] == 2003 and r["declared_at"] == AT_TEXT and isinstance(r["declared_at"], str)
    assert json.loads(Path(path).read_text())["predictions"][-1]["declared_at"] == AT_TEXT    # as stored, verbatim
    assert (r["candidate"], r["experiment"], r["frozen_constants"], r["code_sha"]) == ("leagues-sa-v1", sx.EID,
                                                                                       FROZEN, "abc1234")
    assert r["utc_date"] == (AT + timedelta(hours=1)).isoformat()
    # finding 3: a prospective row's input cutoff is the export instant (the DB state it read), never the kickoff
    assert r["input_cutoff"] == r["prediction_stamp"] == doc["exported_at"] == now.isoformat()
    assert r["inputs_read"] == {"n_prior": 40, "last_prior_kickoff": datetime(2026, 9, 4, 3, 0).isoformat(),
                                "pending_before": 2}
    assert r["gate_verdict"] == f"leagues-sa-v1 · declared {AT_TEXT}"                     # D6: no verdict label
    # D1 (addendum 185): the four's rows carry window_opens_at = their declared_at, the same verbatim text
    assert r["window_opens_at"] == r["declared_at"] == AT_TEXT and doc["git_sha"] == "abc1234"
    assert doc["bindings"]["SA"]["window_opens_at"] == AT_TEXT
    assert set(r) >= {"declared_at", "window_opens_at"} and set(doc["predictions"][0]) == set(r)   # one schema
    assert sorted((x["match_id"], x["reason"]) for x in doc["missing"] if x["competition"] == "SA") == [
        (2001, "before_declared_at"), (2002, "before_declared_at")]


# ------------------------------------------------------------------------------ 5. refused declarations --

@pytest.mark.parametrize("entry, run, why", [
    (decl("SA", at=None), SXRUN, "no declared_at as a UTC instant"),
    (decl("SA", at="2026-11-06"), SXRUN, "a date is never the instant"),
    (decl("SA", at="2026-11-06T09:30:00-05:00"), SXRUN, "no declared_at as a UTC instant"),
    (decl("SA", constants=None), SXRUN, "holds no frozen_constants"),
    (decl("SA", constants={**FROZEN, "rho": -0.09}), SXRUN, "differ from the soccer-expansion-v1 run record's"),
    (decl("SA", constants={**FROZEN, "min_prior": 40}), SXRUN, "not exactly"),
    (decl("SA", competition="BL1"), SXRUN, "the entry's competition is 'BL1', not 'SA'"),
    (decl("SA"), {**SXRUN, "run": {"result": {**SXRUN["run"]["result"], "surviving": ["PD", "SA"]}}},
     "in the soccer-expansion-v1 surviving set"),
])
def test_5_a_refused_declaration_has_no_rows_and_says_why(ledger, tmp_path, entry, run, why):
    _comps()
    _pd()
    ledger(entry, run=run)
    t = _teams("SA")
    _priors("SA", t)
    _game(2003, "SA", AT + timedelta(hours=1), (t[0], t[1]), MatchStatus.SCHEDULED)
    _, doc = _export(AT - timedelta(hours=2), out=tmp_path)
    st = doc["bindings"]["SA"]["state"]
    assert st.startswith(sx.SHADOW_REFUSED) and why in st
    assert not [x for x in doc["predictions"] + doc["missing"] if x["competition"] == "SA"]


def test_5_pd_refuses_without_its_run_record_and_every_league_with_it(ledger, tmp_path):
    _comps()
    _pd()
    ledger(decl("SA"), run={"id": sx.EID, "run": None})
    _, doc = _export(NOW, out=tmp_path)
    assert "has no run record" in doc["bindings"]["PD"]["state"]
    assert "has no run record holding" in doc["bindings"]["SA"]["state"]
    assert doc["model_version"] is None and doc["frozen_constants"] is None and doc["predictions"] == []


# ----------------------------------------------------------------------------------- 6. missing reasons --

def test_6_every_in_window_fixture_is_a_row_or_a_reason(ledger, tmp_path):
    _world(ledger, decl("SA"), decl("BL1"))
    t = _teams("SA")
    rest = _priors("SA", t)
    now = AT + timedelta(days=1)
    ko = [now + timedelta(hours=h) for h in range(1, 9)]
    _game(2101, "SA", ko[0], rest[0], MatchStatus.SCHEDULED)                                    # a row
    _game(2102, "SA", ko[1], rest[1], MatchStatus.POSTPONED)
    _game(2103, "SA", ko[2], rest[2], MatchStatus.CANCELLED)
    _game(2104, "SA", ko[3], rest[3], MatchStatus.SCHEDULED, stage="Relegation Round")
    _game(2105, "SA", ko[4], rest[4], MatchStatus.LIVE)
    new = _teams("SA", n=2, tag="new")
    _game(2106, "SA", ko[5], (new[0], t[0]), MatchStatus.SCHEDULED)                             # no strength
    _game(2107, "SA", ko[6], rest[5], MatchStatus.STALE_ORPHAN)
    _game(2108, "SA", now + timedelta(hours=80), rest[6], MatchStatus.SCHEDULED)                 # outside the window
    tb = _teams("BL1")
    _priors("BL1", tb, n=5, base=6000)
    _game(6101, "BL1", ko[0], (tb[0], tb[1]), MatchStatus.SCHEDULED)                             # below MIN_PRIOR
    _, doc = _export(now, out=tmp_path)
    got = {r["match_id"]: "row" for r in doc["predictions"]}
    got.update({x["match_id"]: x["reason"] for x in doc["missing"]})
    assert got == {2101: "row", 2102: "status_postponed", 2103: "status_cancelled", 2104: "not_regular",
                   2105: "status_live", 2106: "no_strength", 2107: "status_stale_orphan", 6101: "below_min_prior"}
    for x in doc["missing"]:
        assert set(x) == {"match_id", "competition", "utc_date", "reason"}
        assert x["reason"] in {k for k, _ in sx.MISSING_REASONS}
    assert doc["counts"]["SA"] == {"priced": 1, "status_postponed": 1, "status_cancelled": 1, "not_regular": 1,
                                   "status_live": 1, "no_strength": 1, "status_stale_orphan": 1}
    assert doc["counts"]["BL1"] == {"below_min_prior": 1}


# ------------------------------------------------------------------------------------------------- 7. F3 --

def test_7_an_unplaced_label_before_the_windows_end_refuses_that_league_only(ledger, tmp_path, monkeypatch):
    import cli
    _world(ledger, decl("SA"), decl("BL1"))
    now = AT + timedelta(days=1)
    for code, base in (("SA", 1000), ("BL1", 5000)):
        t = _teams(code)
        rest = _priors(code, t, base=base)
        _game(base + 900, code, now + timedelta(hours=3), rest[0], MatchStatus.SCHEDULED)
    t = _teams("SA", n=2, tag="x")
    _game(1950, "SA", now + timedelta(hours=100), (t[0], t[1]), MatchStatus.SCHEDULED, stage="Group A")  # after
    _, doc = _export(now, out=tmp_path / "a")
    assert doc["bindings"]["SA"]["state"] == "exporting"
    _game(1951, "SA", now - timedelta(days=30), (t[1], t[0]), stage="Matchday 3")         # a prior: refuses
    _game(1952, "SA", now + timedelta(hours=2), (t[0], t[1]), MatchStatus.POSTPONED, stage=None)   # never a slot
    _, doc = _export(now, out=tmp_path / "b")
    st = doc["bindings"]["SA"]["state"]
    assert st.startswith("refused: F3") and "1951 'Matchday 3'" in st and "1950" not in st and "1952" not in st
    assert {r["competition"] for r in doc["predictions"]} == {"BL1"}
    assert not [x for x in doc["missing"] if x["competition"] == "SA"]
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "host")
    monkeypatch.setattr(sx, "utc_now_naive", lambda: now)
    r = CliRunner().invoke(cli.cli, ["export-soccer-expansion-shadow"])
    assert r.exit_code == 2 and "SA · refused: F3" in r.output
    # PD has no stored game in this world: refused by name (finding 11), never "exporting, rows 0"
    assert "PD · refused: not stored: no 2026/27 game of PD is stored in this DB" in r.output
    assert "REFUSED: PD, SA (above); the exporting leagues (BL1) were written to exports/" in r.output
    assert "a label unplaced on the second chain run is a finding Issue" in r.output          # D7, an F3 refusal
    assert "BL1 · exporting · leagues-bl1-v1" in r.output and "rows 1" in r.output
    assert len(list(Path("exports").glob(f"{sx.FILE_PREFIX}*.json"))) == 1             # the others were written


def test_7_shadow_entry_refuses_an_unplaced_fixture_never_a_skipped_row():
    from types import SimpleNamespace
    fx = SimpleNamespace(id=1, utc_date=NOW, status=MatchStatus.SCHEDULED, stage="Matchday 3")
    with pytest.raises(sx.ExpansionRefused, match="184 item 1"):
        sx.shadow_entry([], fx, FROZEN, None)


# ------------------------------------------------------------------------------------------------- 8. R6 --

@pytest.mark.parametrize("setup, why", [
    ("laptop", "this machine's role is laptop"),
    ("unset", "the role is unknown (SP_EXPORTS_MIRROR_ROLE unset)"),
    ("desk", "the role 'desk' is not host or laptop"),
    ("unreadable", "host.env exists but cannot be read"),
])
def test_8_r6_only_the_host_exports(ledger, tmp_path, monkeypatch, setup, why):
    import cli
    _world(ledger)
    if setup == "unset":
        monkeypatch.delenv("SP_EXPORTS_MIRROR_ROLE", raising=False)
    elif setup == "unreadable":
        (tmp_path / "host.env").mkdir()                    # exists, cannot be read as a file
        monkeypatch.setenv("SP_HOST_ENV", str(tmp_path / "host.env"))
        monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "host")    # never consulted after an unreadable host.env
    elif setup != "laptop":
        monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", setup)
    monkeypatch.setattr(sx, "export_shadow", lambda *a, **k: pytest.fail("the export ran"))
    monkeypatch.setattr(sx, "shadow_bindings", lambda *a, **k: pytest.fail("the registry was read"))
    from src.db import database
    monkeypatch.setattr(database, "session_scope", lambda *a, **k: pytest.fail("the DB was read"))
    # finding 9: cli.py binds session_scope / init_db at import; a read in the command body before the role check
    # would go through those names, never database's
    monkeypatch.setattr(cli, "session_scope", lambda *a, **k: pytest.fail("the DB was read (cli.session_scope)"))
    monkeypatch.setattr(cli, "init_db", lambda *a, **k: pytest.fail("the DB was touched (cli.init_db)"))
    r = CliRunner().invoke(cli.cli, ["export-soccer-expansion-shadow"])
    assert r.exit_code == 2
    assert r.output.startswith("REFUSED: export-soccer-expansion-shadow runs on the host only (the writer of record; "
                               "ARCHITECT 2026-10-30 addendum 178 R6")
    assert why in r.output and r.output.rstrip().endswith("Nothing was read or written.")
    assert not Path("exports").exists()


def test_8_r6_the_host_writes_the_file(ledger, monkeypatch):
    import cli
    _world(ledger)
    t = _teams("PD")
    _priors("PD", t)
    _game(900, "PD", NOW + timedelta(hours=5), (t[0], t[1]), MatchStatus.SCHEDULED)
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "host")
    monkeypatch.setattr(sx, "utc_now_naive", lambda: NOW)
    r = CliRunner().invoke(cli.cli, ["export-soccer-expansion-shadow"])
    assert r.exit_code == 0, r.output
    (f,) = Path("exports").glob(f"{sx.FILE_PREFIX}*.json")
    assert f.name == f"{sx.FILE_PREFIX}{NOW:%Y-%m-%d_%H%M%S}.json" and json.loads(f.read_text())["count"] == 1
    assert "PD · exporting · soccer-expansion-v1 · declared_at 2026-10-07T15:17:38Z · window opens " in r.output
    assert "SA · not declared" in r.output and "frozen v22 (the run record's; never the production model)" in r.output


# ----------------------------------------------------------------------------------- 9. the audit round trip --

def _sequenced(n=60):
    t = _teams("SA")
    _priors("SA", t)
    pairs = list(itertools.permutations(t, 2))
    out = []
    for i in range(n):
        ko = AT + timedelta(hours=1 + 6 * i)
        _game(2000 + i, "SA", ko, pairs[i % len(pairs)], MatchStatus.SCHEDULED)
        _legs(2000 + i, ko)
        out.append((2000 + i, ko, (i * 7) % 3, (i * 5) % 2))
    return out


def test_9_the_audit_reads_the_exports_rows_present_and_equal(ledger, tmp_path):
    """R1: rows exported a few minutes before each kickoff, every earlier game final: the cohort reader finds all 60
    stored rows and the audit finds no difference, nothing missing, nothing unreadable."""
    _world(ledger, decl("SA"))
    out = tmp_path / "ex"
    for mid, ko, hs, as_ in _sequenced():
        _, doc = _export(ko - timedelta(minutes=5), hours=1, out=out)
        (r,) = doc["predictions"]
        assert r["match_id"] == mid and r["inputs_read"]["pending_before"] == 0
        _finish(mid, hs, as_)
    w = lw.read(("SA",), now=NOW, export_dir=str(out))["SA"]
    assert w["state"] == "ready" and w["stored_present"] == 60 and w["stored_missing"] == 0
    a = lw.score(w, export_dir=str(out), now=NOW)["audit"]
    assert a == {"present": 60, "missing": 0, "findings": [], "expected": [], "unreadable": [], "superseded": 0}


def test_9_rows_exported_before_earlier_games_finished_are_counted_and_expected(ledger, tmp_path):
    """D4 (addendum 185): such rows are written with inputs_read.pending_before; the read's recompute differs and the
    audit counts it on its EXPECTED line, listed with the count (R1: never resolved either way); none is a FINDING."""
    _world(ledger, decl("SA"))
    out = tmp_path / "ex"
    games = _sequenced()
    _, doc = _export(AT + timedelta(minutes=5), hours=24 * 16, out=out)
    pend = {r["match_id"]: r["inputs_read"]["pending_before"] for r in doc["predictions"]}
    assert len(pend) == 60 and pend[2000] == 0 and pend[2059] == 59
    for mid, _, hs, as_ in games:
        _finish(mid, hs, as_)
    w = lw.read(("SA",), now=NOW, export_dir=str(out))["SA"]
    a = lw.score(w, export_dir=str(out), now=NOW)["audit"]
    assert a["present"] == 60 and a["expected"] and a["findings"] == [] and not a["unreadable"]
    assert all(pend[d["match_id"]] == d["pending_before"] > 0 for d in a["expected"])
    assert 2000 not in {d["match_id"] for d in a["expected"]}
    L = lw.audit_lines("SA", a)
    assert L[1] == ("  - SA · FINDINGS 0: differences on rows with pending_before = 0, or with no pending_before on "
                    "the row (addendum 185 D4)")
    assert L[2].startswith(f"  - SA · EXPECTED {len(a['expected'])}: differences on rows with pending_before > 0")
    assert all(x.startswith("    EXPECTED match ") and " · pending_before " in x for x in L[3:])
    assert len(L) == 3 + len(a["expected"])


# ------------------------------------------------------------------------------------------- 10. consumers --

def test_10_the_consumers_read_the_new_rows(ledger, tmp_path):
    import sys

    from sqlalchemy import func, select

    from src.db.database import session_scope
    from src.db.schema import Prediction
    from src.walters import desk_policy as dp
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "deploy" / "hosting"))
    import coverage_map as cm
    assert lw.EXPORT_PREFIX == sx.FILE_PREFIX
    _world(ledger, decl("SA"))
    now = AT + timedelta(days=1)
    for code, base in (("PD", 1000), ("SA", 3000)):
        t = _teams(code)
        rest = _priors(code, t, base=base)
        _game(base + 900, code, now + timedelta(hours=5), rest[0], MatchStatus.SCHEDULED)
    out = tmp_path / "ex"
    path, doc = _export(now, out=out)
    assert {r["competition"] for r in doc["predictions"]} == {"PD", "SA"}
    calls = sx.last_calls(str(out))
    assert set(calls) == {1900, 3900} and calls[3900]["exported_at"] == now.isoformat()
    _finish(1900, 1, 0)
    _finish(3900, 2, 2)
    g = sx.shadow_grade(days=60, export_dir=str(out), now=now + timedelta(days=1))["per_league"]
    assert g["PD"]["graded"] == 1 and g["SA"] == {"graded": 0, "priced": 0, "fenced": 1, "mean_clv_pp": None}
    raw = json.loads(Path(path).read_text())
    assert dp.normalize(raw) == []
    dp.annotate(raw, now=now)
    assert all("desk" not in r for r in raw["predictions"])
    with session_scope() as s:
        assert s.execute(select(func.count(Prediction.id))).scalar() == 0
    r = calls[1900]
    v, why = cm._paper_shadow(r, {"home": r["home_team"], "away": r["away_team"],
                                  "start": datetime.fromisoformat(r["utc_date"]).replace(tzinfo=timezone.utc)}, None)
    assert why is None and v["model_version"] == "v22" and v["pick"]


# ----------------------------------------------------------------------------------------- 11. the registry --

def test_11_the_registry_is_read_at_call_time(ledger, tmp_path):
    """The export reads the registry through soccer_expansion._reg_paths at call time (never the default path
    registry.get bound when it was defined): a tmp record is what binds."""
    _comps()
    _pd()
    ledger(run={**SXRUN, "status": "confirming-tmp", "verdict": {"verdict": "PASS", "at": "2026-10-20T00:00:00Z"}})
    _, doc = _export(NOW, out=tmp_path / "a")
    assert doc["gate_verdict"] == "confirming-tmp"
    assert doc["bindings"]["PD"]["window_opens_at"] == "2026-10-20T00:00:00Z"
    ledger(run={"id": sx.EID, "run": None})                 # the real registry holds a run record; this one does not
    _, doc = _export(NOW, out=tmp_path / "b")
    assert doc["bindings"]["PD"]["state"].startswith(sx.SHADOW_REFUSED)


# ------------------------------------------------------------- 12. D2: the chain step's window (addendum 185) --

def test_12_the_three_timers_are_the_timer_files_own():
    """SYNC_CHAIN_TIMERS is declared once in soccer_expansion and pinned here to deploy/hosting/systemd: each timer's
    OnCalendar line, word for word, and the chain its Unit runs."""
    import re
    root = Path(__file__).resolve().parent.parent / "deploy" / "hosting" / "systemd"
    for timer, chain, cal in sx.SYNC_CHAIN_TIMERS:
        t = (root / timer).read_text(encoding="utf-8")
        assert re.findall(r"^OnCalendar=(.+)$", t, re.M) == [cal], timer
        assert re.search(r"^Unit=(.+)$", t, re.M).group(1) == f"sp-chain@{chain}.service", timer
    assert sorted(t for t, _, _ in sx.SYNC_CHAIN_TIMERS) == sorted(
        p.name for p in root.glob("sp-soccer-*.timer"))                      # every soccer sync timer, no other


@pytest.mark.parametrize("now, at, timer", [
    # Friday's chain (14:00Z) -> Saturday 10:30 London: 09:30Z in summer time (UK clocks go back 2026-10-25)
    (datetime(2026, 10, 23, 14, 20), datetime(2026, 10, 24, 9, 30), "sp-soccer-saturday.timer"),
    (datetime(2026, 10, 30, 14, 20), datetime(2026, 10, 31, 10, 30), "sp-soccer-saturday.timer"),   # winter: 10:30Z
    (datetime(2027, 3, 26, 14, 20), datetime(2027, 3, 27, 10, 30), "sp-soccer-saturday.timer"),     # before 03-28
    (datetime(2027, 4, 2, 14, 20), datetime(2027, 4, 3, 9, 30), "sp-soccer-saturday.timer"),        # after: BST
    # Saturday's -> Sunday's morning-after 09:50Z; Sunday's -> Monday's; Monday's -> Tuesday's
    (datetime(2026, 10, 31, 10, 50), datetime(2026, 11, 1, 9, 50), "sp-soccer-morning-after.timer"),
    (datetime(2026, 11, 1, 10, 5), datetime(2026, 11, 2, 9, 50), "sp-soccer-morning-after.timer"),
    (datetime(2026, 11, 2, 10, 5), datetime(2026, 11, 3, 9, 50), "sp-soccer-morning-after.timer"),
    # Tuesday's -> Friday 14:00Z (no chain Wed / Thu: D2, no daily league sync)
    (datetime(2026, 11, 3, 10, 5), datetime(2026, 11, 6, 14, 0), "sp-soccer-friday.timer"),
    # strictly after: a clock exactly at a fire reads the next one
    (datetime(2026, 11, 6, 14, 0), datetime(2026, 11, 7, 10, 30), "sp-soccer-saturday.timer"),
])
def test_12_next_chain_run_is_the_next_timer_fire_dst_correct(now, at, timer):
    got = sx.next_chain_run(now)
    assert (got["at"], got["timer"]) == (at, timer)
    assert got["chain"] == dict((t, c) for t, c, _ in sx.SYNC_CHAIN_TIMERS)[timer]


def test_12_an_unreadable_timer_line_refuses_never_a_guessed_window(monkeypatch):
    monkeypatch.setattr(sx, "SYNC_CHAIN_TIMERS", (("sp-x.timer", "soccer-prematch", "daily"),))
    with pytest.raises(sx.ExpansionRefused, match="not a form next_chain_run reads"):
        sx.next_chain_run(NOW)


def test_12_without_hours_the_window_runs_to_the_next_chains_export_and_strictly_after_the_stamp(ledger, tmp_path):
    """The chain step's window: (now, the next chain's fire + EXPORT_WINDOW_MARGIN), Code's reading of D2's "before the
    next chain's" as before the next chain's EXPORT, ruled with the margin's name and value (ARCHITECT 2026-10-30,
    addendum 188 item 4: "EXPORT_WINDOW_MARGIN = 2 h past the next chain's fire, overlaps allowed"; finding 0/9: the
    window never ends at the fire, so a kickoff between the fire and that chain's last step is in this file). A fixture kicking off at the stamp itself is neither a row
    nor a missing entry (finding 13: last_calls and stored_rows never read a row stamped at its kickoff); one at the
    window's end is not in this file. --hours stays a manual run's explicit override."""
    _world(ledger)
    t = _teams("PD")
    rest = _priors("PD", t)
    now = datetime(2026, 11, 3, 10, 5)                         # Tuesday's morning-after run -> Friday 14:00Z
    end = datetime(2026, 11, 6, 14, 0) + sx.EXPORT_WINDOW_MARGIN
    assert sx.EXPORT_WINDOW_MARGIN == timedelta(hours=2) and end == datetime(2026, 11, 6, 16, 0)
    _game(901, "PD", now, rest[0], MatchStatus.SCHEDULED)                                 # at the stamp
    _game(902, "PD", datetime(2026, 11, 5, 19, 0), rest[1], MatchStatus.SCHEDULED)         # Thursday: a row
    _game(903, "PD", datetime(2026, 11, 6, 14, 0), rest[2], MatchStatus.SCHEDULED)         # at the next fire: a row
    _game(904, "PD", end, rest[3], MatchStatus.SCHEDULED)                                  # at the end: not here
    _, doc = _export(now, hours=None, out=tmp_path / "a")
    assert [r["match_id"] for r in doc["predictions"]] == [902, 903] and doc["missing"] == []
    assert doc["window"] == {"after": now.isoformat(), "before": "2026-11-06T16:00:00",
                             "rule": "until the next soccer sync chain's export (soccer-prematch, sp-soccer-friday."
                                     "timer + EXPORT_WINDOW_MARGIN 2h; ARCHITECT 2026-10-30, addendum 185 D2, "
                                     "addendum 188 item 4)",
                             "next_chain": {"at": "2026-11-06T14:00:00", "timer": "sp-soccer-friday.timer",
                                            "chain": "soccer-prematch", "margin_hours": 2.0}}
    assert doc["window_hours"] == round((end - now).total_seconds() / 3600, 2)
    _, doc = _export(now, hours=100, out=tmp_path / "b")
    assert [r["match_id"] for r in doc["predictions"]] == [902, 903, 904] and doc["window_hours"] == 100
    assert doc["window"]["next_chain"] is None and doc["window"]["rule"].startswith("--hours 100")


def test_12_the_sunday_10z_kickoff_has_a_row_from_saturdays_export(ledger, tmp_path):
    """Finding 0/9's case: LaLiga's Sunday 12:00 CEST slot is 10:00Z, ten minutes after sp-soccer-morning-after fires
    at 09:50Z. Sunday's export runs after that chain's syncs (here 10:10Z) and so cannot write it; Saturday's export
    (summer time: Saturday's 10:30 London is 09:30Z) reaches past Sunday's fire by EXPORT_WINDOW_MARGIN (2 h, addendum
    188 item 4), so the game has a row, and last_calls reads it (the last row written before its kickoff)."""
    _world(ledger)
    t = _teams("PD")
    rest = _priors("PD", t)
    sat, sun = datetime(2026, 10, 10, 9, 45), datetime(2026, 10, 11, 10, 10)
    assert sx.next_chain_run(sat)["at"] == datetime(2026, 10, 11, 9, 50)
    _game(911, "PD", datetime(2026, 10, 11, 10, 0), rest[0], MatchStatus.SCHEDULED)       # Sunday 10:00Z
    out = tmp_path / "x"
    _, a = _export(sat, hours=None, out=out)
    _, b = _export(sun, hours=None, out=out)
    assert [r["match_id"] for r in a["predictions"]] == [911] and a["window"]["before"] == "2026-10-11T11:50:00"
    assert b["predictions"] == [] and b["missing"] == []          # after Sunday's stamp only: never in its file
    got = sx.last_calls(str(out))
    assert list(got) == [911] and got[911]["prediction_stamp"] == sat.isoformat()


def test_12_the_chain_step_runs_bare_and_the_cli_prints_its_window(ledger, monkeypatch):
    import cli
    _world(ledger)
    t = _teams("PD")
    _priors("PD", t)
    now = datetime(2026, 10, 30, 14, 20)
    _game(900, "PD", now + timedelta(hours=5), (t[0], t[1]), MatchStatus.SCHEDULED)
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "host")
    monkeypatch.setattr(sx, "utc_now_naive", lambda: now)
    r = CliRunner().invoke(cli.cli, ["export-soccer-expansion-shadow"])
    assert r.exit_code == 0, r.output
    assert ("1 rows · kickoffs after 2026-10-30T14:20:00 and before 2026-10-31T12:30:00 (until the next soccer sync "
            "chain's export (soccer-prematch, sp-soccer-saturday.timer + EXPORT_WINDOW_MARGIN 2h; ARCHITECT "
            "2026-10-30, addendum 185 D2, addendum 188 item 4))") in r.output
    assert CliRunner().invoke(cli.cli, ["export-soccer-expansion-shadow", "--hours", "0"]).exit_code == 2   # usage


def test_12_the_command_catches_an_unreadable_timer_line_exit_2_nothing_written(ledger, monkeypatch):
    """Finding 19: the chain step's own surface. next_chain_run's refusal (a timer schedule it cannot read) is the
    command's REFUSED line and exit 2, never a traceback (exit 1), and no file is written (never a guessed window)."""
    import cli
    _world(ledger)
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "host")
    monkeypatch.setattr(sx, "utc_now_naive", lambda: NOW)
    monkeypatch.setattr(sx, "SYNC_CHAIN_TIMERS", (("sp-x.timer", "soccer-prematch", "daily"),))
    r = CliRunner().invoke(cli.cli, ["export-soccer-expansion-shadow"])
    assert r.exit_code == 2 and isinstance(r.exception, SystemExit), r.output       # the catch, not a traceback
    assert ("REFUSED: sp-x.timer: OnCalendar 'daily' is not a form next_chain_run reads (never guessed). Nothing was "
            "written.") in r.output
    assert not list(Path("exports").glob(f"{sx.FILE_PREFIX}*.json"))


# ------------------------------------------------------- 13. law 4: a league this DB does not store (finding 11) --

def test_13_a_bound_league_not_stored_is_refused_by_name_never_a_quiet_window(ledger, tmp_path):
    _comps()                                                   # SA, BL1, FL1, ELC stored; PD's competition is not
    ledger(decl("SA"), run=SXRUN)
    _, doc = _export(NOW, out=tmp_path / "a")
    assert doc["bindings"]["PD"]["state"] == ("refused: not stored: the competition PD is not stored in this DB (law "
                                              "4: missing data is labelled, never an empty window)")
    assert doc["bindings"]["SA"]["state"] == ("refused: not stored: no 2026/27 game of SA is stored in this DB (law 4: "
                                              "missing data is labelled, never an empty window)")
    assert doc["counts"]["PD"] == doc["counts"]["SA"] == {} and doc["predictions"] == []
    _pd()
    t = _teams("PD")
    _game(950, "PD", NOW - timedelta(days=2), (t[0], t[1]))    # one stored game: PD binds and exports (0 rows)
    _, doc = _export(NOW, out=tmp_path / "b")
    assert doc["bindings"]["PD"]["state"] == "exporting" and doc["counts"]["PD"] == {}


# --------------------------------------------- 14. a non-numeric run-record constant refuses (finding 12) --

def test_14_a_non_numeric_constant_refuses_cleanly_through_the_command(ledger, monkeypatch):
    import cli
    _comps()
    _pd()
    ledger(run={**SXRUN, "run": {"result": {**SXRUN["run"]["result"], "rho": "abc"}}})
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "host")
    monkeypatch.setattr(sx, "utc_now_naive", lambda: NOW)
    r = CliRunner().invoke(cli.cli, ["export-soccer-expansion-shadow"])
    assert r.exit_code == 2 and not isinstance(r.exception, ValueError), r.output
    assert "PD · refused: soccer-expansion-v1's run record holds constants that are not numbers" in r.output
    assert "REFUSED: PD (above); no league was exported (exports/" in r.output and "holds no row)" in r.output
    assert "finding Issue" not in r.output                 # D7's label sentence only on an F3 refusal (finding 20)


# ------------------------- 15. pending_before is D4's count, by status (addendum 189 item 3; finding 15) --

ADD189_3 = ("ARCHITECT 2026-10-30 15:15 ET, addendum 189 item 3, verbatim in part: \"pending_before counts the league's "
            "games with a STORED kickoff strictly earlier than the fixture's that are not yet final AND will enter the "
            "walk once final: SCHEDULED, LIVE, or FINISHED without a result. A POSTPONED game with no new kickoff and a "
            "CANCELLED game are NOT counted [...] A re-dated game counts by its new kickoff if that is earlier than the "
            "fixture's.\"")


def test_15_pending_before_counts_every_earlier_game_not_final_by_status(ledger, tmp_path):
    """ADD189_3: SCHEDULED, LIVE and FINISHED without a result count; POSTPONED, CANCELLED, a stale orphan and a
    play-off round do not."""
    _world(ledger, decl("SA"))
    t = _teams("SA")
    rest = _priors("SA", t)
    now = AT + timedelta(days=1)
    _game(2201, "SA", now - timedelta(hours=3), rest[0], MatchStatus.POSTPONED)       # not placed (R4): not counted
    _game(2202, "SA", now - timedelta(hours=2), rest[1], MatchStatus.SCHEDULED)       # un-ingested
    _game(2203, "SA", now + timedelta(hours=1), rest[2], MatchStatus.LIVE)
    _game(2204, "SA", now + timedelta(hours=2), rest[3], MatchStatus.CANCELLED)       # never walked: not counted
    _game(2205, "SA", now + timedelta(hours=3), rest[4], MatchStatus.STALE_ORPHAN)    # never walked: not counted
    _game(2206, "SA", now + timedelta(hours=4), rest[5], MatchStatus.SCHEDULED, stage="Relegation Round")  # F3
    _game(2207, "SA", now - timedelta(hours=1), rest[6], raw="AET", s90=False)        # FINISHED, no 90': pending
    _game(2208, "SA", now + timedelta(hours=5), rest[7], MatchStatus.SCHEDULED)       # the row
    _, doc = _export(now, out=tmp_path)
    (r,) = [x for x in doc["predictions"] if x["match_id"] == 2208]
    assert r["inputs_read"]["pending_before"] == 3                     # 2202 2203 2207; never 2201 (POSTPONED)


def test_15_a_stale_postponed_game_is_not_counted_and_a_disagreement_prior_is_not_counted_as_built(ledger, tmp_path):
    """ADD189_3, the ruled behaviour (by status, not by time): (1) a POSTPONED game weeks before the export, never
    re-dated, is NOT counted (it is not in the walk), so it no longer makes every later row of its league EXPECTED; a
    SCHEDULED game left un-ingested days before the export still counts (by status, no time bound). (2) Code's reading
    of D4's "not FINISHED at export", kept for the architect: a FINISHED FT row whose stored 90-minute score disagrees
    with its stored score (#737's disagrees(), PENDING in the cohort reader's membership) is FINISHED, so it is not
    counted."""
    _world(ledger, decl("SA"))
    t = _teams("SA")
    rest = _priors("SA", t)
    now = AT + timedelta(days=30)
    _game(2401, "SA", AT + timedelta(days=2), rest[0], MatchStatus.POSTPONED)         # 4 weeks back: not counted
    _game(2402, "SA", now - timedelta(days=5), rest[1], MatchStatus.SCHEDULED)        # stale, un-ingested
    _game(2403, "SA", now - timedelta(days=1), rest[2], hs=2, as_=1)                  # FT 2-1 ...
    _set(2403, home_score_90=1, away_score_90=1)                                      # ... 1-1 at 90': disagrees
    _game(2404, "SA", now + timedelta(hours=5), rest[3], MatchStatus.SCHEDULED)       # the row
    from src.db.database import session_scope
    from src.db.schema import Match
    with session_scope() as s:
        assert lw.disagrees(s.get(Match, 2403)) and not lw.not_final(s.get(Match, 2403))
    _, doc = _export(now, out=tmp_path)
    (r,) = [x for x in doc["predictions"] if x["match_id"] == 2404]
    assert r["inputs_read"]["pending_before"] == 1                     # 2402; never 2401 (POSTPONED), never 2403


def test_15_postponed_and_cancelled_are_not_counted_a_re_dated_game_counts_by_its_new_kickoff(ledger, tmp_path):
    """ADD189_3: an earlier POSTPONED game and an earlier CANCELLED game are not counted; a game re-dated (SCHEDULED,
    its stored kickoff moved) counts by its NEW kickoff: earlier than the fixture's -> counted, later -> not, whatever
    its original kickoff was."""
    _world(ledger, decl("SA"))
    t = _teams("SA")
    rest = _priors("SA", t)
    now = AT + timedelta(days=1)
    fixture = now + timedelta(hours=6)
    _game(2501, "SA", now - timedelta(hours=4), rest[0], MatchStatus.POSTPONED)       # earlier, postponed
    _game(2502, "SA", now - timedelta(hours=3), rest[1], MatchStatus.CANCELLED)       # earlier, cancelled
    _game(2503, "SA", fixture + timedelta(days=3), rest[2], MatchStatus.SCHEDULED)    # was later ...
    _set(2503, utc_date=now + timedelta(hours=2))                                     # ... re-dated earlier: counted
    _game(2504, "SA", now - timedelta(hours=2), rest[3], MatchStatus.SCHEDULED)       # was earlier ...
    _set(2504, utc_date=fixture + timedelta(hours=1))                                 # ... re-dated later: not
    _game(2505, "SA", fixture, rest[4], MatchStatus.SCHEDULED)                        # the row
    _, doc = _export(now, out=tmp_path)
    pend = {x["match_id"]: x["inputs_read"]["pending_before"] for x in doc["predictions"]}
    assert pend[2505] == 1                                             # 2503 only
    assert pend[2503] == 0 and pend[2504] == 2                         # 2504's earlier: 2503 and 2505


# ------------------------------------------------------- 16. D4: the audit's two lines (addendum 185) --

def test_16_the_audit_splits_differences_by_the_rows_pending_before():
    """pending_before 0 -> FINDING; > 0 -> EXPECTED (listed with the count); a row without inputs_read, without the
    key, or with a value that is not a whole number >= 0 -> FINDING (never assumed expected). Equal rows are neither."""
    rec = {i: (0.5, 0.3, 0.2) for i in range(1, 9)}
    off = {"home_win_prob": 0.4, "draw_prob": 0.3, "away_win_prob": 0.3}
    same = {"home_win_prob": 0.5, "draw_prob": 0.3, "away_win_prob": 0.2}
    stored = {1: {"prediction": off, "inputs_read": {"pending_before": 0}},
              2: {"prediction": off, "inputs_read": {"pending_before": 3}},
              3: {"prediction": off},
              4: {"prediction": off, "inputs_read": {}},
              5: {"prediction": off, "inputs_read": {"pending_before": "3"}},
              6: {"prediction": off, "inputs_read": {"pending_before": True}},
              7: {"prediction": off, "inputs_read": {"pending_before": -1}},
              8: {"prediction": same, "inputs_read": {"pending_before": 5}}}
    a = lw.audit(stored, rec)
    assert [f["match_id"] for f in a["findings"]] == [1, 3, 4, 5, 6, 7]
    assert [(f["match_id"], f["pending_before"]) for f in a["expected"]] == [(2, 3)]
    assert [f["pending_before"] for f in a["findings"]] == [0, None, None, None, None, None]
    L = lw.audit_lines("SA", a)
    assert L[0].endswith("differ from the recompute 7 (R1: never resolved either way) · superseded 0 " + lw.SUPERSEDED_NOTE)
    assert L[1].startswith("  - SA · FINDINGS 6: ") and L[8].startswith("  - SA · EXPECTED 1: ")
    assert L[2].endswith("pending_before 0") and L[3].endswith("pending_before not on the row")
    assert L[9].startswith("    EXPECTED match 2 ") and L[9].endswith("pending_before 3") and len(L) == 10


# ------------------------------------------------------------- 17. the uncovered branches (finding 19) --

def test_17_pd_refuses_when_the_surviving_set_lacks_it(ledger, tmp_path):
    _comps()
    _pd()
    ledger(run={**SXRUN, "run": {"result": {**SXRUN["run"]["result"], "surviving": ["SA"]}}})
    _, doc = _export(NOW, out=tmp_path)
    assert doc["bindings"]["PD"]["state"] == ("refused: soccer-expansion-v1: the run record's surviving set ['SA'] does "
                                              "not hold PD")


@pytest.mark.parametrize("field, value", [("declared_at", "2026-10-07"), ("verdict", {"verdict": "PASS",
                                                                                      "at": "2026-10-09"}),
                                          ("verdict", {"verdict": "PASS", "at": "2026-10-09T08:47:39-04:00"})])
def test_17_pd_refuses_an_instant_that_is_not_utc(ledger, tmp_path, field, value):
    _comps()
    _pd()
    ledger(run={**SXRUN, field: value})
    _, doc = _export(NOW, out=tmp_path)
    st = doc["bindings"]["PD"]["state"]
    assert st.startswith("refused: soccer-expansion-v1: declared_at ") and st.endswith("is not a UTC instant")


def test_17_pd_refuses_a_constants_drift_between_confirming_and_the_run_record(ledger, tmp_path, monkeypatch):
    _world(ledger)
    monkeypatch.setattr(lw, "run_record_constants", lambda: {**FROZEN, "rho": -0.2})
    _, doc = _export(NOW, out=tmp_path)
    assert "confirming()'s constants" in doc["bindings"]["PD"]["state"] and "differ from leagues_window." \
        "run_record_constants()" in doc["bindings"]["PD"]["state"]


def test_17_a_label_with_no_kickoff_refuses_the_league():
    from types import SimpleNamespace
    games = [SimpleNamespace(id=7, utc_date=None, status=MatchStatus.SCHEDULED, stage="Matchday 3"),
             SimpleNamespace(id=8, utc_date=None, status=MatchStatus.POSTPONED, stage="Matchday 3"),
             SimpleNamespace(id=9, utc_date=NOW, status=MatchStatus.SCHEDULED, stage="Regular Season - 3")]
    assert sx.shadow_unplaced(games, "SA", NOW) == ["SA 2026/27 7 'Matchday 3' no kickoff"]


def test_17_the_parity_goes_through_the_exports_own_function(ledger, monkeypatch):
    _world(ledger)
    _league_season("PD", 5000)
    calls = []
    real = sx.shadow_entry
    monkeypatch.setattr(sx, "shadow_entry", lambda *a, **k: calls.append(k.get("prospective")) or real(*a, **k))
    p = lc.parity("PD", -0.1, 0.0008, now=NOW)
    assert calls and set(calls) == {False} and len(p["rows"]) <= len(calls)


def test_17_rows_continue_after_a_verdict_and_carry_no_verdict_label(ledger, tmp_path):
    """D6 (addendum 185, verbatim in part): "ROWS CONTINUE while the declaration checks out, after a verdict either
    way [...] a later PR labels them with the verdict when one exists." So a recorded REJECT changes neither the rows
    nor their label: "<id> · declared <declared_at>", no verdict text (finding 5)."""
    _world(ledger, decl("SA", verdict={"verdict": "REJECT"}))
    t = _teams("SA")
    rest = _priors("SA", t)
    now = AT + timedelta(days=1)
    _game(2301, "SA", now + timedelta(hours=2), rest[0], MatchStatus.SCHEDULED)
    _, doc = _export(now, out=tmp_path)
    (r,) = [x for x in doc["predictions"] if x["competition"] == "SA"]
    assert r["gate_verdict"] == f"leagues-sa-v1 · declared {AT_TEXT}" and "verdict" not in r["gate_verdict"]


# ------------------------------------- 18. addendum 188 item 4: NO ROW IS EVER REWRITTEN, the audit's superseded --

ADD188 = ("ARCHITECT 2026-10-30 14:50 ET, addendum 188 item 4, verbatim in part: \"NO ROW IS EVER REWRITTEN — each run "
          "writes its own dated file (one per run); a fixture covered by two runs has two rows; the audit's row for a "
          "fixture is the LAST row whose export time is before its kickoff (the lowest pending_before by construction), "
          "the earlier rows counted as superseded on the audit's line. A run never reads or edits another run's file.\"")


def _files(d):
    return sorted(Path(d).glob(f"{sx.FILE_PREFIX}*.json"))


def test_18_two_runs_in_one_minute_write_two_files_the_first_untouched(ledger, tmp_path):
    """ADD188: each run its own file, named to the second (FILE_STAMP, pass-4 findings 0/4) and published
    exclusively: two runs at different seconds of one minute leave two files, the first byte for byte as written; a
    run whose name exists (the same second, whatever its microseconds) is refused (ExpansionRefused) and writes
    nothing, the existing file untouched and no temp file left."""
    _world(ledger)
    t = _teams("PD")
    _priors("PD", t)
    _game(900, "PD", NOW + timedelta(hours=5), (t[0], t[1]), MatchStatus.SCHEDULED)
    out = tmp_path / "ex"
    p1, a = _export(NOW + timedelta(seconds=10), out=out)
    first = Path(p1).read_bytes()
    p2, b = _export(NOW + timedelta(seconds=40, microseconds=5), out=out)
    assert p1 != p2 and [f.name for f in _files(out)] == [Path(p1).name, Path(p2).name]
    assert Path(p1).name == f"{sx.FILE_PREFIX}2026-12-20_120010.json"
    assert Path(p2).name == f"{sx.FILE_PREFIX}2026-12-20_120040.json"
    assert Path(p1).read_bytes() == first and a["count"] == b["count"] == 1
    for again in (NOW + timedelta(seconds=10), NOW + timedelta(seconds=10, microseconds=7)):
        with pytest.raises(sx.ExpansionRefused, match="already exists: no row is ever rewritten"):
            _export(again, out=out)
    assert Path(p1).read_bytes() == first and len(_files(out)) == 2
    assert sorted(p.name for p in out.iterdir()) == [Path(p1).name, Path(p2).name]       # no temp file left
    calls = sx.last_calls(str(out))
    assert calls[900]["exported_at"] == (NOW + timedelta(seconds=40, microseconds=5)).isoformat()


def test_18_the_files_name_is_one_mirror_kind(ledger, tmp_path, monkeypatch):
    """Pass-4 findings 0/4: the run file's own name, as export_shadow writes it, reads as the one kind
    soccer_expansion_shadow in exports_mirror.kind_of and in compare_exports.kind_of (its copy), so host/latest keeps
    one newest file for the family, as ncaa_shadow's name does."""
    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root / "deploy" / "hosting"))
    import compare_exports as ce
    import exports_mirror as em
    _world(ledger)
    names = [Path(_export(NOW + timedelta(seconds=k, microseconds=k), out=tmp_path)[0]).name for k in (1, 59)]
    for n in names:
        assert em.kind_of(n) == ce.kind_of(n) == "soccer_expansion_shadow", n


def test_18_the_command_refuses_an_existing_name_exit_2_nothing_overwritten(ledger, monkeypatch):
    """ADD188 through the command: the second run at the same instant prints REFUSED and exits 2; the first file is
    byte for byte as written and no other file appears."""
    import cli
    _world(ledger)
    t = _teams("PD")
    _priors("PD", t)
    _game(900, "PD", NOW + timedelta(hours=5), (t[0], t[1]), MatchStatus.SCHEDULED)
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "host")
    monkeypatch.setattr(sx, "utc_now_naive", lambda: NOW)
    assert CliRunner().invoke(cli.cli, ["export-soccer-expansion-shadow"]).exit_code == 0
    (f,) = _files("exports")
    first = f.read_bytes()
    r = CliRunner().invoke(cli.cli, ["export-soccer-expansion-shadow"])
    assert r.exit_code == 2 and isinstance(r.exception, SystemExit), r.output
    assert "already exists: no row is ever rewritten" in r.output and "Nothing was written." in r.output
    assert _files("exports") == [f] and f.read_bytes() == first
    assert sorted(p.name for p in Path("exports").iterdir()) == [f.name]                 # no temp file left


def test_18_a_write_that_fails_midway_leaves_no_file_and_no_temp_exit_2(ledger, monkeypatch):
    """Pass-4 findings 2/5: the write is atomic. A write that fails part way (ENOSPC after 100 bytes) leaves no file
    under the run's name and no temp file; the command prints REFUSED and exits 2, never a traceback."""
    import cli
    import errno
    import os as _os
    _world(ledger)
    t = _teams("PD")
    _priors("PD", t)
    _game(900, "PD", NOW + timedelta(hours=5), (t[0], t[1]), MatchStatus.SCHEDULED)
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "host")
    monkeypatch.setattr(sx, "utc_now_naive", lambda: NOW)
    real = _os.fdopen

    class Half:
        def __init__(self, f):
            self.f = f

        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.f.close()

        def write(self, text):
            self.f.write(text[:100])
            self.f.flush()
            raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(sx.os, "fdopen", lambda fd, mode="r": Half(real(fd, mode)))
    r = CliRunner().invoke(cli.cli, ["export-soccer-expansion-shadow"])
    assert r.exit_code == 2 and isinstance(r.exception, SystemExit), r.output
    name = f"{sx.FILE_PREFIX}{NOW:%Y-%m-%d_%H%M%S}.json"
    assert f"REFUSED: exports/{name} could not be written (OSError: [Errno 28] No space left on device)" in r.output
    assert "Nothing was written." in r.output
    assert list(Path("exports").iterdir()) == []                                       # no file, no temp file


def test_18_the_audits_row_is_the_last_before_kickoff_the_earlier_counted_superseded(ledger, tmp_path):
    """ADD188: every member covered by two runs (one export of the whole window at the declaration, with earlier games
    pending, then one five minutes before each kickoff with every earlier game final). stored_rows keeps the later
    row (pending_before 0) and counts the earlier one superseded; the audit finds nothing, sums 60 superseded, and
    its line prints the count."""
    _world(ledger, decl("SA"))
    out = tmp_path / "ex"
    games = _sequenced()
    _, big = _export(AT + timedelta(minutes=5), hours=24 * 16, out=out)
    assert len(big["predictions"]) == 60
    for mid, ko, hs, as_ in games:
        _export(ko - timedelta(minutes=5), hours=1, out=out)
        _finish(mid, hs, as_)
    assert len(_files(out)) == 61
    rows = lw.stored_rows("SA", AT_TEXT, str(out))
    assert rows[2059]["inputs_read"]["pending_before"] == 0 and rows[2059]["superseded"] == 1
    assert rows[2059]["exported_at"] == (games[-1][1] - timedelta(minutes=5)).isoformat()
    w = lw.read(("SA",), now=NOW, export_dir=str(out))["SA"]
    a = lw.score(w, export_dir=str(out), now=NOW)["audit"]
    assert a == {"present": 60, "missing": 0, "findings": [], "expected": [], "unreadable": [], "superseded": 60}
    assert lw.audit_lines("SA", a)[0].endswith(" · superseded 60 " + lw.SUPERSEDED_NOTE)


def test_18_the_readers_order_by_exported_at_never_the_file_name(tmp_path):
    """last_calls and stored_rows keep the row with the latest exported_at before the kickoff, never the names'
    order. Contrived inputs, two different minutes: an old-style minute name of 14:35 ("_1435.json", exported_at
    14:35) sorts after a seconds-stamped name of 14:30 ("_143000.json") whose exported_at is set to 14:36, so the
    name order and the exported_at order disagree and a name-ordered read would keep the 14:35 row. Both readers keep
    the 14:36 row and count the other as superseded. (With honest stamps the two orders agree; this pins the rule,
    not a case the writer makes.)"""
    ko = "2026-11-06T18:00:00"
    base = {"match_id": 7, "utc_date": ko, "competition": "SA", "declared_at": AT_TEXT}

    def doc(at, p):
        return {"engine": sx.ENGINE, "exported_at": at,
                "predictions": [{**base, "prediction": {"home_win_prob": p, "draw_prob": 0.3, "away_win_prob": 0.7 - p,
                                                        "top_pick": "home_win", "top_pick_prob": p}}]}
    (tmp_path / f"{sx.FILE_PREFIX}2026-11-06_143000.json").write_text(json.dumps(doc("2026-11-06T14:36:00", 0.5)))
    (tmp_path / f"{sx.FILE_PREFIX}2026-11-06_1435.json").write_text(json.dumps(doc("2026-11-06T14:35:00", 0.4)))
    assert [f.name for f in _files(tmp_path)][-1].endswith("_1435.json")          # the earlier row's name is last
    assert sx.last_calls(str(tmp_path))[7]["exported_at"] == "2026-11-06T14:36:00"
    got = lw.stored_rows("SA", AT_TEXT, str(tmp_path))[7]
    assert got["exported_at"] == "2026-11-06T14:36:00" and got["prediction"]["home_win_prob"] == 0.5
    assert got["superseded"] == 1


# ----------------------------------------------------------------------------- pass-5 review (export switch) --

def test_pass5_a_missing_or_unreadable_registry_refuses_never_a_green_empty_step(ledger, tmp_path):
    """'not declared' is a fact read from a registry that exists and parses: a missing or unreadable registry file
    refuses every binding (law 4), so the chain step exits 2, never green with no row."""
    from src.walters import registry as reg
    _world(ledger, decl("SA"))
    Path(reg.LEDGER).unlink()
    b = sx.shadow_binding("PD")
    assert b["state"].startswith(sx.SHADOW_REFUSED) and "is missing" in b["state"]
    assert sx.shadow_binding("SA")["state"].startswith(sx.SHADOW_REFUSED)
    Path(reg.LEDGER).write_text("{not json")
    assert "is unreadable (JSONDecodeError)" in sx.shadow_binding("PD")["state"]


def test_pass5_the_run_file_has_the_other_exports_mode(ledger, tmp_path):
    """mkstemp creates 0600 and os.link keeps it; the run file is chmod'ed to 0666 & ~umask, as open() makes every
    other export (0644 under umask 022)."""
    import os
    import stat
    _world(ledger)
    old = os.umask(0o022)
    try:
        path, _ = _export(NOW, out=tmp_path / "m")
    finally:
        os.umask(old)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o644


def test_pass5_a_tie_on_exported_at_is_counted_superseded_the_later_name_kept(tmp_path):
    """stored_rows' superseded counts every other row of the fixture before its kickoff, ties on exported_at
    included; on a tie the later name is kept (the audit line's note says so)."""
    ko = "2026-11-06T18:00:00"
    base = {"match_id": 7, "utc_date": ko, "competition": "SA", "declared_at": AT_TEXT}

    def doc(p):
        return {"engine": sx.ENGINE, "exported_at": "2026-11-06T14:30:00",
                "predictions": [{**base, "prediction": {"home_win_prob": p, "draw_prob": 0.3, "away_win_prob": 0.7 - p,
                                                        "top_pick": "home_win", "top_pick_prob": p}}]}
    (tmp_path / f"{sx.FILE_PREFIX}2026-11-06_143000.json").write_text(json.dumps(doc(0.4)))
    (tmp_path / f"{sx.FILE_PREFIX}2026-11-06_143000_copy.json").write_text(json.dumps(doc(0.5)))
    got = lw.stored_rows("SA", AT_TEXT, str(tmp_path))[7]
    assert got["superseded"] == 1 and got["prediction"]["home_win_prob"] == 0.5
    assert "any tied on exported_at" in lw.SUPERSEDED_NOTE


def test_741_an_unreadable_registry_is_a_refusal_through_the_command_never_a_traceback(ledger, tmp_path):
    """Codex on #741: a registry that exists but is not JSON refuses every binding (shadow_binding) and the command
    exits 2 with its REFUSED line; the header's own registry read never raises before them."""
    from click.testing import CliRunner

    import cli
    from src.walters import registry as reg
    _world(ledger, decl("SA"))
    Path(reg.LEDGER).write_text("{not json")
    _, doc = _export(NOW, out=tmp_path / "u")
    assert doc["gate_verdict"] == "not declared" and doc["frozen_constants"] is None
    assert all(b["state"].startswith(sx.SHADOW_REFUSED) for b in doc["bindings"].values())
    out = CliRunner().invoke(cli.cli, ["export-soccer-expansion-shadow", "--hours", "24"],
                             env={"SP_EXPORTS_MIRROR_ROLE": "host"})
    assert out.exit_code == 2 and "Traceback" not in out.output, out.output
    assert "runs on the host only" not in out.output and "is unreadable (JSONDecodeError)" in out.output, out.output


def test_741_round2_an_unreadable_registry_is_windowrefused_at_the_source(ledger):
    """Codex on #741 (round 2): leagues_window's registry reads (declaration, run_record_constants, surviving) turn an
    unreadable file into WindowRefused at the source, so every caller refuses with its own REFUSED line."""
    from src.walters import registry as reg
    _world(ledger)
    Path(reg.LEDGER).write_text("{not json")
    for f in (lambda: lw.declaration("SA"), lw.run_record_constants, lw.surviving):
        with pytest.raises(lw.WindowRefused, match="is unreadable"):
            f()
