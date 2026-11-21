"""soccer-v23's PASS shadow, built DORMANT (ARCHITECT 2026-11-21 08:04 ET, addendum 436 item 7, on DEV 2's plan of
2026-11-19 on #656; src/walters/soccer_v23_shadow.py). Held to, each with its test (436 item 7):
  (a) DORMANT IS BYTE-IDENTICAL: the pages, the stored rows, the Desk blocks and desk_meta, for each cause: no entry
      (today), declared and unrun, REJECT, INVALID, an unreadable registry, off the host;
  (b) ON: v22's own fields, the Desk and desk_meta unchanged byte for byte; a failed arm never stops v22's row; the arm
      reads no market field; availability is off in the shadow whatever the slot reads (263 item 6) and the page says
      so;
  and the plan's points: the arm is soccer_v23.predict_live_slate's own answer, bitwise; the fence; the horizon; the
  compare's own line (263 item 6). The baseline of (a) is the same pass and export with this PR's two hooks taken
out (training._soccer_v23_shadow -> {}, export._v23_fields -> {}, export._v23_strip -> identity): the code as on main.
Throwaway SQLite files only (tests/test_record_vs_close.py iso_db) and tmp registries (registry.LEDGER monkeypatched);
the real docs/registry/experiments.json is read, never written."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from src.db.schema import MatchStatus, Sport
from src.walters import export as ex
from src.walters import registry as reg
from src.walters import soccer_v23 as sv
from src.walters import soccer_v23_shadow as sh
from src.walters import training as tr
from tests.test_pl_availability import KICK, MIXED, SEASON, _world
from tests.test_record_vs_close import iso_db  # noqa: F401  (a fixture: a throwaway SQLite, cwd = tmp_path)

VERDICT_AT = "2026-11-01T12:00:00Z"
V22_POISSON = {"dixon_coles_rho": -0.1}              # the world's v22 row (tests.test_pl_availability._world)
V22_SHA = sv.params_sha256(V22_POISSON)              # 440 item 4(b): what the run record carries
NOW = KICK - timedelta(hours=20)                       # the run's clock: the fixture inside the horizon
SLOTS = {"cut": "2026-10-30T15:00:00Z", "availability_on": True, "v22_recorded_log_loss": 1.0,
         "v22_recorded_source": "a test's own figure (never a record)", "scope": "LEAGUE_REGULAR",
         "first_season": "score_under_prior", "visibility": "day"}


def entry(**kw) -> dict:
    """A soccer-v23 entry whose PASS is recorded and whose confirmation window is open (the arm ON), unless kw says
    otherwise. availability_on is TRUE here on purpose: the shadow keeps the term off whatever the slot reads."""
    e = {"id": sv.EID, "status": "confirming", "verdict": {"verdict": "PASS", "ruling": "test", "at": VERDICT_AT},
         "frozen_constants": sv.code_constants(), sv.SLOTS_KEY: dict(SLOTS), "gate": sv.BAR_TEXT,
         "run": {"result": {"verdict": "PASS", "thin_excluded": [], "v22_params_sha256": V22_SHA}}}
    e.update(kw)
    return e


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """write(entry dict, or None for an empty registry, or a str for raw file text) into a tmp registry."""
    path = tmp_path / "experiments.json"

    def write(e="on"):
        if e == "missing":
            path.unlink(missing_ok=True)
            return
        if isinstance(e, str) and e != "on":
            path.write_text(e)
            return
        path.write_text(json.dumps([] if e is None else [entry() if e == "on" else e]))
    monkeypatch.setattr(reg, "LEDGER", str(path))
    monkeypatch.setattr(sh, "env_now", lambda: NOW)
    write(None)
    return write


@pytest.fixture
def host(monkeypatch):
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "host")


def _rows():
    from src.db.database import session_scope
    from src.db.schema import Prediction
    with session_scope() as s:
        return [{"m": p.match_id, "v": p.model_version, "p": (p.home_win_prob, p.draw_prob, p.away_win_prob),
                 "xg": (p.expected_home_score, p.expected_away_score), "fb": json.loads(json.dumps(p.factor_breakdown))}
                for p in s.query(Prediction).order_by(Prediction.match_id).all()]


def _export(statuses=(MatchStatus.SCHEDULED,), desk=False, code="PL"):
    doc = json.loads(ex.export_predictions(sport=Sport.SOCCER, start_date=KICK - timedelta(days=1),
                                           end_date=KICK + timedelta(days=1), competition_code=code,
                                           statuses=list(statuses), desk=desk))
    for k in ("exported_at", "git_sha"):
        doc.pop(k)
    for r in doc["predictions"]:                       # the write clock of the row (Prediction.created_at): each
        if isinstance(r.get("prediction"), dict):      # pass writes its own, so two passes never share it
            r["prediction"].pop("computed_at", None)
    return doc


def _desk(doc) -> tuple:
    from src.walters import desk_policy as dp
    a = dp.annotate(json.loads(json.dumps(doc)), now=datetime(2026, 11, 8, 9, 0, tzinfo=timezone.utc))
    return (json.dumps(a["desk_meta"], sort_keys=True), [json.dumps(r["desk"], sort_keys=True) for r in a["predictions"]])


def _pass_and_page():
    sh.take_receipts()
    tr._generate_predictions_soccer("PL", SEASON, model_version="v22")
    return _rows(), _export(), sh.take_receipts()


def _baseline(monkeypatch):
    """The same pass and page with this PR's hooks taken out: the code as on main."""
    with monkeypatch.context() as mp:
        mp.setattr(tr, "_soccer_v23_shadow", lambda *a, **k: {})
        mp.setattr(ex, "_v23_fields", lambda *a, **k: {})
        mp.setattr(ex, "_v23_strip", lambda fb: fb)
        rows, doc, _ = _pass_and_page()
    return rows, doc


# ============================================================================== (a) DORMANT IS BYTE-IDENTICAL --

DORMANT = {
    "no entry (today)": (None, "no soccer-v23 entry in the registry"),
    "declared and unrun": (entry(status="declared", verdict=None, run=None), "verdict reads null, not PASS"),
    "REJECT": (entry(status="closed", verdict={"verdict": "REJECT", "ruling": "t", "at": VERDICT_AT}),
               "verdict reads REJECT, not PASS"),
    "INVALID": (entry(status="run", verdict=None, run={"result": {"verdict": "INVALID", "thin_excluded": []}}),
                "verdict reads null, not PASS"),
    "an unreadable registry": ("{ not json", "cannot be read"),
    "FAIL": (entry(status="closed", verdict={"verdict": "FAIL", "ruling": "t", "at": VERDICT_AT}),
             "verdict reads FAIL, not PASS"),
    "a registry that is not a list": ("{}", "is not a list of entries"),
    "a missing registry": ("missing", "no soccer-v23 entry in the registry"),
    "a verdict that is a bare string": (entry(verdict="PASS"), "verdict reads null, not PASS"),
    # ARCHITECT 2026-11-21 09:54 ET, addendum 440 item 4(a)-(c): each its own dormant cause, byte-identical
    "the gate is not BAR_TEXT": (entry(gate=sv.BAR_TEXT + " "), "a PASS is shown only as a PASS at the bar"),
    "a run record without v22's params sha": (
        entry(run={"result": {"verdict": "PASS", "thin_excluded": []}}), "carries no v22_params_sha256"),
    "v22's params are not the ones the run read": (
        entry(run={"result": {"verdict": "PASS", "thin_excluded": [], "v22_params_sha256": "0" * 64}}),
        "are not the params the run read"),
}


@pytest.mark.parametrize("cause", list(DORMANT))
def test_dormant_is_byte_identical_for_each_cause(cause, iso_db, ledger, host, monkeypatch):
    """436 item 7(a): the stored rows, the page and the Desk's blocks and desk_meta exactly as the code on main writes
    them, and nothing of the shadow anywhere; the receipt names the cause."""
    _world(MIXED)
    e, why = DORMANT[cause]
    ledger(e)
    base_rows, base_doc = _baseline(monkeypatch)
    rows, doc, receipts = _pass_and_page()
    assert rows == base_rows and json.dumps(doc) == json.dumps(base_doc)
    assert _desk(doc) == _desk(base_doc)
    blob = json.dumps(rows) + json.dumps(doc)
    assert sh.FB_KEY not in blob and sh.PREFIX not in blob
    assert len(set(receipts)) == 1 and receipts[0].startswith("soccer-v23 shadow: dormant (") and why in receipts[0]
    _finish_after_the_verdict()                        # a finished game of the shadow's territory: still nothing
    fin = _export(statuses=(MatchStatus.FINISHED,))
    with monkeypatch.context() as mp:
        mp.setattr(ex, "_v23_fields", lambda *a, **k: {})
        mp.setattr(ex, "_v23_strip", lambda fb: fb)
        base_fin = _export(statuses=(MatchStatus.FINISHED,))
    assert fin["count"] == 1 and json.dumps(fin) == json.dumps(base_fin) and sh.PREFIX not in json.dumps(fin)


def _finish_after_the_verdict():
    from src.db.database import session_scope
    from src.db.schema import Match
    with session_scope() as s:
        m = s.query(Match).filter(Match.utc_date == KICK).one()
        m.status, m.home_score, m.away_score, m.status_raw = MatchStatus.FINISHED, 2, 0, "FT"


def test_dormant_off_the_host_with_a_pass_recorded(iso_db, ledger, monkeypatch):
    """Off the host, even with the PASS recorded and the window open: byte-identical, nothing of the shadow."""
    _world(MIXED)
    ledger("on")
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "laptop")
    base_rows, base_doc = _baseline(monkeypatch)
    rows, doc, receipts = _pass_and_page()
    assert rows == base_rows and json.dumps(doc) == json.dumps(base_doc) and _desk(doc) == _desk(base_doc)
    assert sh.PREFIX not in json.dumps(doc) and sh.FB_KEY not in json.dumps(rows)
    assert "runs on the host only" in receipts[0]


@pytest.mark.parametrize("change, why", [
    ({"status": "production"}, "not 'confirming'"),
    ({"verdict": {"verdict": "PASS", "ruling": "t", "at": "2026-11-01T12:00:00+00:00"}}, "no readable verdict stamp"),
    ({"verdict": {"verdict": "PASS", "ruling": "t", "at": "2026-11-01 12:00:00Z"}}, "no readable verdict stamp"),
    ({"verdict": {"verdict": "PASS", "ruling": "t", "at": "2026-11-01"}}, "no readable verdict stamp"),
    ({"frozen_constants": {**sv.code_constants(), "K_PRIOR": 6.0}}, "frozen constants differ"),
    ({sv.SLOTS_KEY: {**SLOTS, "cut": None}}, "slot 'cut' is null"),
    ({"run": {"result": {"verdict": "PASS", "v22_params_sha256": V22_SHA}}}, "carries no thin_excluded set"),
    ({"run": {"result": {"verdict": "PASS", "thin_excluded": [], "v22_params_sha256": "ABC"}}},
     "carries no v22_params_sha256"),
    ({"gate": None}, "a PASS is shown only as a PASS at the bar"),
    ({"run": None}, "carries no thin_excluded set"),
])
def test_every_other_dormant_cause_is_named(change, why):
    g = sh.state(entry(**change), None, ("v22", V22_POISSON))
    assert not g.on and why in g.why


def test_another_production_version_or_pass_is_dormant(iso_db, ledger, host):
    assert "not 'v22'" in sh.state(entry(), None, ("v23", V22_POISSON)).why
    assert "are not the params the run read" in sh.state(entry(), None, ("v22", {"dixon_coles_rho": -0.2})).why
    assert "carries no poisson" in sh.state(entry(), None, ("v22", {})).why
    assert sh.state(entry()).why == sh.PRODUCTION_UNREAD
    on = sh.state(entry(), None, ("v22", V22_POISSON))
    assert on.on and "prices 'v21'" in sh.for_pass(on, "v21").why and sh.for_pass(on, "v22").on


# ========================================================================================================= (b) ON --

def _on_world(ledger, odds=False):
    """pl-availability's PL world, its rows labelled with the provider's league-round form ("Regular Season - <n>",
    the one form soccer_expansion.placement reads as regular), as the stored PL rows are."""
    from src.db.database import session_scope
    from src.db.schema import Match, Odds
    fx = _world(MIXED)
    with session_scope() as s:
        for i, m in enumerate(s.query(Match).order_by(Match.utc_date).all()):
            m.stage = f"Regular Season - {i + 1}"
        if odds:
            for sel, price in (("HOME", 1.9), ("DRAW", 3.6), ("AWAY", 4.2)):
                s.add(Odds(match_id=fx, bookmaker="b", market="1X2", selection=sel, price_decimal=price,
                           captured_at=KICK - timedelta(days=2)))
    ledger("on")
    return fx


def test_on_v22s_rows_and_page_and_the_desk_are_unchanged_and_the_arm_rides_beside(iso_db, ledger, host, monkeypatch):
    fx = _on_world(ledger)
    base_rows, base_doc = _baseline(monkeypatch)
    rows, doc, receipts = _pass_and_page()
    (r,), (b,) = rows, base_rows
    arm = r["fb"].pop(sh.FB_KEY)
    assert r == b                                                  # v22's own row byte for byte, one key beside it
    assert arm["version"] == sv.EID and arm["base_version"] == "v22" and arm["verdict_at"] == VERDICT_AT
    assert arm["availability"] == "off" and "error" not in arm
    (row,), (brow,) = doc["predictions"], base_doc["predictions"]
    v23 = {k: row.pop(k) for k in sh.ROW_KEYS}
    assert row == brow and {k: v for k, v in doc.items() if k != "predictions"} == \
        {k: v for k, v in base_doc.items() if k != "predictions"}
    assert sh.FB_KEY not in row["prediction"]["factor_breakdown"]
    assert v23["v23_version"] == sv.EID and v23["v23_reason"] is None and v23["v23_label"] == sh.LABEL
    assert v23["v23_availability"] == sh.AVAILABILITY_OFF and "263 item 6" in v23["v23_availability"]
    assert v23["v23_probabilities"] == {"home_win": round(arm["p_home"], 4), "draw": round(arm["p_draw"], 4),
                                        "away_win": round(arm["p_away"], 4)}
    with_keys = {**base_doc, "predictions": [{**brow, **v23}]}
    assert _desk(with_keys) == _desk(base_doc)                     # the Desk reads none of the v23_* keys
    assert receipts[0].startswith("soccer-v23 shadow: ON (soccer-v23 PASS 2026-11-01T12:00:00Z")
    assert fx == r["m"]


def test_the_arm_is_predict_live_slates_own_answer_with_availability_off(iso_db, ledger, host):
    """The design's only live entry point, bitwise, on params whose availability switch is FALSE although the slot
    reads true (263 item 6), with the run record's thin set."""
    from src.db.database import session_scope
    from src.db.schema import Match
    fx = _on_world(ledger)
    _pass_and_page()
    (r,) = _rows()
    arm = r["fb"][sh.FB_KEY]
    with session_scope() as s:
        m = s.get(Match, fx)
        v22p = sv.production_params(s)[1]
        pj = sv.canon_params(v22p, False, "LEAGUE_REGULAR", thin_excluded=[])
        assert json.loads(pj)["availability_on"] is False
        (got,) = sv.predict_live_slate(s, [sv.Fixture(m.id, "PL", SEASON, m.utc_date, m.home_team_id, m.away_team_id)],
                                       sv.EID, pj, "day", record=sv.NoRecord(sh.AVAILABILITY_OFF))
    assert (arm["p_home"], arm["p_draw"], arm["p_away"]) == (got["p_home"], got["p_draw"], got["p_away"])


def test_the_arm_reads_no_market_field(iso_db, ledger, host, tmp_path, monkeypatch):
    """The same store with and without the fixture's book prices: the arm is the same, number for number."""
    _on_world(ledger, odds=True)
    _pass_and_page()
    (with_odds,) = _rows()
    from src.db.database import session_scope
    from src.db.schema import Odds
    with session_scope() as s:
        assert s.query(Odds).count() == 3
        s.query(Odds).delete()
    _pass_and_page()
    (bare,) = _rows()
    assert with_odds["fb"][sh.FB_KEY] == bare["fb"][sh.FB_KEY]


def test_a_failed_arm_never_stops_v22s_row(iso_db, ledger, host, monkeypatch, caplog):
    _on_world(ledger)
    base_rows, base_doc = _baseline(monkeypatch)

    def boom(*a, **k):
        raise RuntimeError("synthetic")
    monkeypatch.setattr(sv, "predict_live_slate", boom)
    rows, doc, _ = _pass_and_page()
    (r,), (b,) = rows, base_rows
    mark = r["fb"].pop(sh.FB_KEY)
    assert r == b and mark["error"] == "RuntimeError: synthetic" and "no shadow arm for matches" in caplog.text
    (row,) = doc["predictions"]
    assert row["v23_probabilities"] is None and row["v23_reason"].startswith("the shadow arm failed for this game")
    assert _desk(doc) == _desk(base_doc)


def test_a_fixture_outside_the_horizon_is_not_priced_and_its_row_says_why(iso_db, ledger, host, monkeypatch):
    _on_world(ledger)
    monkeypatch.setattr(sh, "env_now", lambda: KICK - timedelta(hours=sh.HORIZON_HOURS + 1))
    rows, doc, _ = _pass_and_page()
    assert sh.FB_KEY not in rows[0]["fb"]
    (row,) = doc["predictions"]
    assert row["v23_probabilities"] is None and "horizon" in row["v23_reason"]


def test_a_fixture_before_the_verdict_is_outside_the_shadow(iso_db, ledger, host, monkeypatch):
    _on_world(ledger)
    ledger(entry(verdict={"verdict": "PASS", "ruling": "t", "at": "2026-11-09T00:00:00Z"}))   # after the kickoff
    base_rows, base_doc = _baseline(monkeypatch)
    rows, doc, receipts = _pass_and_page()
    assert rows == base_rows and json.dumps(doc) == json.dumps(base_doc) and receipts[0].startswith(
        "soccer-v23 shadow: ON")


def test_the_fence_withholds_a_finished_games_figures(iso_db, ledger, host):
    from src.db.database import session_scope
    from src.db.schema import Match
    fx = _on_world(ledger)
    _pass_and_page()
    with session_scope() as s:
        m = s.get(Match, fx)
        m.status, m.home_score, m.away_score, m.status_raw = MatchStatus.FINISHED, 2, 0, "FT"
    (row,) = _export(statuses=(MatchStatus.FINISHED,))["predictions"]
    assert row["status"] == "finished" and row["v23_probabilities"] is None and row["v23_reason"] == sh.WITHHELD


def test_the_report_only_mode_and_another_competition_never_read_it(iso_db, ledger, host, monkeypatch):
    _on_world(ledger)
    calls = []
    monkeypatch.setattr(sh, "read_gate", lambda *a, **k: calls.append(a) or sh.Gate(False, "x"))
    tr._generate_predictions_soccer("PL", SEASON, model_version="v22", include_finished=True)
    assert tr._soccer_v23_shadow(None, None, [], "SA", False) == {} and not calls


# ===================================================================================================== compare --

def test_the_compare_counts_the_v23_keys_on_their_own_line_and_never_prints_them(tmp_path, capsys):
    """263 item 6: "its own compare line, #735's pattern": the host's rows carry the five keys, the laptop's none; the
    pair is CLEAN, the figures never printed, the count on its own line right after the graded-export line."""
    import sys
    sys.path.insert(0, "deploy/hosting")
    import compare_exports as ce
    from tests.test_compare_exports_graded_export_keys import pair, run
    lap, host_doc = pair(2)
    for r in host_doc.get("results", host_doc.get("predictions", [])):
        r.update({"v23_version": "soccer-v23", "v23_probabilities": {"home_win": 0.7531, "draw": 0.1, "away_win": 0.1},
                  "v23_availability": "off", "v23_label": sh.LABEL, "v23_reason": None})
    rc, out = run(tmp_path, capsys, lap, host_doc)
    lines = out.splitlines()
    gi = next(i for i, x in enumerate(lines) if x.startswith(ce.GRADED_LINE))
    assert lines[gi + 1] == f"{ce.V23_LINE}: 10" and "0.7531" not in out and rc == ce.EXIT_CLEAN
    assert ce.V23_PREFIX == sh.PREFIX and ce.V23_EID == sh.EID


# ===================================================================================================== receipts --

def test_the_predict_command_prints_the_shadows_one_receipt_line(iso_db, ledger, host):
    """Plan point 1: the predict receipt prints one line, dormant with its reason here (no entry)."""
    from click.testing import CliRunner

    from cli import cli
    _on_world(ledger)
    ledger(None)
    out = CliRunner().invoke(cli, ["predict", "--sport", "soccer", "--competition", "PL", "--season", SEASON,
                                   "--version", "v22"])
    assert out.exit_code == 0, out.output
    assert "soccer-v23 shadow: dormant (no soccer-v23 entry in the registry)" in out.output.splitlines()
    assert sh.take_receipts() == []                                # read once and cleared


# ======================================================================================== the review's pins --

def test_the_run_records_thin_set_reaches_the_arms_params():
    """The arm prices on the run record's own exclusion set (a list of [code, season] as soccer_v23.record writes it)."""
    on = sh.state(entry(), None, ("v22", V22_POISSON))
    thin = sh.state(entry(run={"result": {"verdict": "PASS", "thin_excluded": [["ELC", "2019/20"]],
                                          "v22_params_sha256": V22_SHA}}), None, ("v22", V22_POISSON))
    assert on.on and thin.on and on.params_sha != thin.params_sha
    assert json.loads(thin.params_json)["thin_excluded"] == [["ELC", "2019/20"]]
    assert json.loads(on.params_json)["thin_excluded"] == [] and json.loads(thin.params_json)["availability_on"] is False


def test_a_real_refusal_of_the_snapshot_stores_its_cause_and_v22_goes_on(iso_db, ledger, host, monkeypatch):
    """End to end, no monkeypatched failure: rows whose stage label the code cannot place (soccer_expansion F3, never
    guessed) make soccer_v23's builder refuse; every covered row stores the cause, v22's rows are written as always,
    the page names the cause and the ON receipt counts the failure."""
    _world(MIXED)                                      # stage labels left empty: the builder refuses them
    ledger("on")
    base_rows, base_doc = _baseline(monkeypatch)
    rows, doc, receipts = _pass_and_page()
    (r,), (b,) = rows, base_rows
    mark = r["fb"].pop(sh.FB_KEY)
    assert r == b and mark["error"].startswith("GateRefused: a row's stage label cannot be placed")
    (row,) = doc["predictions"]
    assert row["v23_probabilities"] is None and "stage label cannot be placed" in row["v23_reason"]
    assert "priced 0 at 0 kickoff instants · failed 1 · covered outside the 72-hour horizon 0" in receipts[0]


def test_the_on_receipt_counts_the_priced_and_the_horizon(iso_db, ledger, host):
    _on_world(ledger)
    _, _, receipts = _pass_and_page()
    assert "priced 1 at 1 kickoff instants · failed 0 · covered outside the 72-hour horizon 0 · " in receipts[0]


def test_a_redated_games_stored_arm_is_never_shown_under_its_new_kickoff(iso_db, ledger, host):
    from src.db.database import session_scope
    from src.db.schema import Match
    fx = _on_world(ledger)
    _pass_and_page()
    with session_scope() as s:
        s.get(Match, fx).utc_date = KICK + timedelta(hours=26)
    (row,) = json.loads(ex.export_predictions(sport=Sport.SOCCER, start_date=KICK - timedelta(days=1),
                                              end_date=KICK + timedelta(days=3), competition_code="PL",
                                              statuses=[MatchStatus.SCHEDULED]))["predictions"]
    assert row["v23_probabilities"] is None and "priced for a kickoff of 2026-11-08T15:00:00Z" in row["v23_reason"]


def test_another_competitions_rows_never_carry_the_keys_even_on(iso_db, ledger, host):
    from src.db.database import session_scope
    from src.db.schema import Match
    _world(MIXED, comp_code="EL1")
    with session_scope() as s:
        for i, m in enumerate(s.query(Match).order_by(Match.utc_date).all()):
            m.stage = f"Regular Season - {i + 1}"
    ledger("on")
    tr._generate_predictions_soccer("EL1", SEASON, model_version="v22")
    doc = _export(code="EL1")
    assert doc["count"] == 1 and sh.PREFIX not in json.dumps(doc) and sh.FB_KEY not in json.dumps(_rows())


def test_the_export_command_prints_the_shadows_receipt_line(iso_db, ledger, host, tmp_path):
    from click.testing import CliRunner

    from cli import cli
    _on_world(ledger)
    ledger(None)
    tr._generate_predictions_soccer("PL", SEASON, model_version="v22")
    sh.take_receipts()
    out = CliRunner().invoke(cli, ["export-predictions", "--sport", "soccer", "--competition", "PL", "--start",
                                   "2026-11-07", "--end", "2026-11-09", "--status", "scheduled", "--out",
                                   str(tmp_path / "x.json")])
    assert out.exit_code == 0, out.output
    assert "soccer-v23 shadow: dormant (no soccer-v23 entry in the registry)" in out.output.splitlines()


def test_the_receipts_held_are_bounded():
    sh.take_receipts()
    for _ in range(50):
        sh.note(sh.Gate(False, "x"))
    assert len(sh.take_receipts()) == sh.LAST_RECEIPT.maxlen


def test_the_compare_masks_the_v23_keys_in_every_mode(tmp_path, capsys):
    """redacted (a mismatch printed whole), --ignore-keys, and a DIVERGENT pair: no v23 figure printed, the count
    unchanged."""
    import sys
    sys.path.insert(0, "deploy/hosting")
    import compare_exports as ce
    from tests.test_compare_exports_graded_export_keys import pair, run
    assert ce.redacted({"x": {"v23_probabilities": {"home_win": 0.7531}}}) == {"x": {"v23_probabilities": "<masked>"}}

    def with_keys(doc):
        for r in doc["results"]:
            r.update({"v23_version": "soccer-v23", "v23_probabilities": {"home_win": 0.7531}, "v23_availability": "off",
                      "v23_label": sh.LABEL, "v23_reason": None})
        return doc
    lap, host_doc = pair(2)
    rc, out = run(tmp_path / "ign", capsys, lap, with_keys(host_doc), "--ignore-keys", "desk,desk_meta")
    assert "0.7531" not in out and f"{ce.V23_LINE}: 10" in out.splitlines() and rc == ce.EXIT_CLEAN
    lap, host_doc = pair(2, {"log_loss": 1.37})
    rc, out = run(tmp_path / "div", capsys, lap, with_keys(host_doc))
    assert "0.7531" not in out and f"{ce.V23_LINE}: 10" in out.splitlines() and rc == ce.EXIT_DIVERGENT


def test_an_empty_pl_export_still_prints_the_shadows_receipt_line(iso_db, ledger, host, tmp_path):
    """Codex on #1064: a window holding no PL row builds no row, so the export command reads the gate itself."""
    from click.testing import CliRunner

    from cli import cli
    _on_world(ledger)
    ledger(None)
    sh.take_receipts()
    out = CliRunner().invoke(cli, ["export-predictions", "--sport", "soccer", "--competition", "PL", "--start",
                                   "2027-03-01", "--end", "2027-03-02", "--status", "scheduled", "--out",
                                   str(tmp_path / "empty.json")])
    assert out.exit_code == 0, out.output
    assert json.loads((tmp_path / "empty.json").read_text())["count"] == 0
    assert "soccer-v23 shadow: dormant (no soccer-v23 entry in the registry)" in out.output.splitlines()


def test_the_params_sha_is_the_canonical_json_of_v22s_stored_poisson_params():
    """440 item 4(b): the canonical form named: sha256 of json.dumps(dict(params), sort_keys=True,
    separators=(",", ":"), ensure_ascii=True, allow_nan=False). Key order does not change it; any value does."""
    import hashlib
    p = {"dixon_coles_rho": -0.1, "elo_goal_coeff": 0.0008, "promoted_attack": 0.85}
    want = hashlib.sha256(json.dumps(p, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()
    assert sv.params_sha256(p) == want == sv.params_sha256(dict(reversed(list(p.items()))))
    assert sv.params_sha256({**p, "dixon_coles_rho": -0.11}) != want

