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
    assert r["input_cutoff"] == r["utc_date"] == (AT + timedelta(hours=1)).isoformat()
    assert r["prediction_stamp"] == doc["exported_at"] == now.isoformat()
    assert r["inputs_read"] == {"n_prior": 40, "last_prior_kickoff": datetime(2026, 9, 4, 3, 0).isoformat(),
                                "pending_before": 2}
    assert r["gate_verdict"] == f"leagues-sa-v1 · declared {AT_TEXT} · verdict pending"
    assert "window_opens_at" not in r and doc["git_sha"] == "abc1234"
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
    assert r.exit_code == 2 and "SA · refused: F3" in r.output and "REFUSED: SA (above)" in r.output
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
    assert f.name == f"{sx.FILE_PREFIX}{NOW:%Y-%m-%d_%H%M}.json" and json.loads(f.read_text())["count"] == 1
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
    assert a == {"present": 60, "missing": 0, "differ": [], "unreadable": []}


def test_9_rows_exported_before_earlier_games_finished_are_counted_findings(ledger, tmp_path):
    """D4 (Code's default): such rows are written with inputs_read.pending_before; the read's recompute differs and
    the audit counts it (R1: never resolved either way)."""
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
    assert a["present"] == 60 and a["differ"] and not a["unreadable"]
    assert all(pend[d["match_id"]] > 0 for d in a["differ"]) and 2000 not in {d["match_id"] for d in a["differ"]}


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
