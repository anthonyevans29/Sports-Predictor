"""ncaa-elo-v1r: FAIL (ARCHITECT 2026-10-09 12:30 ET, addendum 24 items 1 and 2; GATE-CLASS). Pins:
- (a) the registry holds the one run (spliced from laptop/ncaa-elo-v1r-run-record at 130b481) and the FAIL verdict
  with the ruling verbatim; the spec closes with the run's figures and the ruling;
- (b) the 2025 test set is RETIRED: ncaa-elo-v1r was its last candidate, any other refuses naming the 2026 season;
- (c) ncaa-backtest refuses, exit 2, naming the ruling, with or without --baselines-only, fence lifted or not,
  before anything is read; GATE_STATUS and its line say CLOSED with the ruling's date (ncaa-cfbd-coverage prints it);
- (d) export-ncaa-predictions refuses, exit 2, naming the ruling, once the registry records a verdict for
  ncaa-elo-v1r other than PASS (before anything is read); a PASS or no verdict does not refuse here;
- (e) the #368 fence lifted by itself: the committed registry records the run.
Every registry write goes to a tmp path; nothing reads data/."""
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from src.walters import ncaa_backtest as nb
from src.walters import ncaa_shadow as sh
from src.walters import registry as reg

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "docs" / "specs" / "ncaa-elo-v1r.md"

RULING = ("ARCHITECT, 2026-10-09 12:30 ET. ncaa-elo-v1r: FAIL. The one run (recorded 2026-10-09T16:18:32Z; 762 scored "
          "games, the 2025 regular season; ids sha256 d1951e833d3eded5424a3afb89eb101e7a671bb34fbc0ba1c4133ab176a2913b; "
          "stream 8019c4ffc49c9cf1f46eaf1c286894dced92fa7beaedfd59d1aec8ee839780ea) passes three of D5's four tests "
          "and fails the third. (1) Margin: model log-loss 0.559642 against a bar of 0.664889, the baseline's 0.674889 "
          "less 0.010: passes. (2) Level: mean home probability 0.573688, realized home rate 0.591864, a gap of 1.818pp "
          "against 5pp: passes. (3) Spread: slope b 1.420537, outside 0.80 to 1.20: fails. (4) Range: ratings 1121.1 "
          "to 1906.2 over 136 teams, inside 1000 to 2000: passes. D5 reads PASS iff all four hold, so the verdict is "
          "FAIL. The bar does not move and the run is not repeated. No confirmation window opens and no cohort is "
          "frozen. College football stays market-only. The 2025 regular season is retired as a college test season "
          "with this run: its figures now show how to correct the candidate, and a second candidate scored on it would "
          "be fitted to it. A later college candidate may train on 2024 and 2025, and declares the 2026 regular "
          "season, as it accrues, as its test.")
RULING_C = ("From this ruling until the next college candidate's run is recorded, no command scores a college model on "
            "a 2026 game: prices it and compares it with its result. #79's protocol (v1, train 2025, test 2026, all "
            "divisions) is closed without a verdict of its own: its candidate is the model v1r ran, and v1r has failed "
            "its gate. ncaa-backtest refuses, exit 2, naming this ruling, with or without --baselines-only, and it "
            "does not return when the fence lifts. Its module stays: the v1r gate, the confirmation code and the "
            "shadow import from it.")
RULING_D = ("Addendum 6 item 1 put the verdict on every shadow row once there was one. No shadow file has been written, "
            "and this verdict says the model is too timid: beside a market its rows would show value on every "
            "underdog, and that value would be its own miscalibration. export-ncaa-predictions refuses, exit 2, naming "
            "this ruling, once the registry records a verdict for ncaa-elo-v1r other than PASS. The shadow's terms for "
            "the next candidate are part of its declaration.")
TEST_SET = "NCAA FBS 2025 regular season (CFBD both-FBS labels; warm-up 2024)"
INSTEAD = "the NCAA FBS 2026 regular season as it accrues (>= 500 games)"


def _boom(*a, **k):
    raise AssertionError("read before the refusal")


# --- (a) the record ----------------------------------------------------------------------------------------------

def test_the_registry_holds_the_one_run_and_the_fail_verdict_verbatim():
    e = reg.get("ncaa-elo-v1r")
    run, r = e["run"], e["run"]["result"]
    assert (e["status"], e["verdict"]["verdict"], e["verdict"]["ruling"]) == ("closed", "FAIL", RULING)
    assert e["verdict"]["at"] > run["run_at"] == "2026-10-09T16:18:32Z"
    assert (run["n_scored"], run["prior_read_count"], run["ids_sha256"]) == (
        762, 0, "d1951e833d3eded5424a3afb89eb101e7a671bb34fbc0ba1c4133ab176a2913b")
    assert r["stream_fingerprint"] == "8019c4ffc49c9cf1f46eaf1c286894dced92fa7beaedfd59d1aec8ee839780ea"
    assert (r["crit_margin"], r["crit_level"], r["crit_spread"], r["crit_range"]) == (True, True, False, True)
    # the ruling's figures are the record's, rounded
    assert (round(r["ll_model"], 6), round(r["bar"], 6), round(r["ll_baseline"], 6)) == (0.559642, 0.664889, 0.674889)
    assert (round(r["mean_p"], 6), round(r["realized_home_rate"], 6), round(abs(r["level_gap"]) * 100, 3)) == (
        0.573688, 0.591864, 1.818)
    assert round(r["slope_b"], 6) == 1.420537
    assert (round(r["rating_min"], 1), round(r["rating_max"], 1), r["teams_rated"]) == (1121.1, 1906.2, 136)
    assert e.get("confirmation_cohort") is None                        # no cohort is frozen
    ok, why = reg.production_allowed("ncaa-elo-v1r")
    assert not ok and why == "no PASS verdict"


def test_the_spec_closes_with_the_runs_figures_and_the_ruling_verbatim():
    text_ = SPEC.read_text()
    closing = text_[text_.index("## 9. The run and the verdict: FAIL"):]
    assert f'"{RULING}"' in closing
    for figure in ("0.559642", "0.674889", "0.664889", "0.573688", "0.591864", "1.420537", "1121.1 to 1906.2",
                   "136 teams", "0.594142 on 717 games", "130b481"):
        assert figure in closing, figure


# --- (b) the retired test set ------------------------------------------------------------------------------------

def _decl(eid, test_set):
    return {"id": eid, "sport": "ncaa", "lane": "#79", "candidate": "c", "declaration": "d", "training_cutoff": "t",
            "test_set": test_set, "gate": "g", "confirmation_window": "w",
            "confirmation_plan": {"n_games": 100, "metric": "log_loss", "bar": 0.6931, "must_beat_reference": True,
                                  "reference": "baseline"}}


def test_the_2025_college_test_set_is_retired_after_v1r(tmp_path):
    assert reg.RETIRED_TEST_SETS[TEST_SET] == ("ncaa-elo-v1r", INSTEAD)
    assert reg.get("ncaa-elo-v1r")["test_set"] == TEST_SET              # the key is the entry's test set, exactly
    kw = {"path": str(tmp_path / "x.json")}
    with pytest.raises(reg.RegistryError, match="RETIRED") as ex:
        reg.declare(_decl("ncaa-elo-v2", TEST_SET), **kw)
    assert INSTEAD in str(ex.value) and "ncaa-elo-v1r was its last candidate" in str(ex.value)
    assert "addendum 24" in str(ex.value)
    reg.declare(_decl("ncaa-elo-v1r", TEST_SET), **kw)                  # the last one allowed
    reg.record_run("ncaa-elo-v1r", [1, 2], {"log_loss": 0.6}, ids_dir=str(tmp_path / "ids"), **kw)
    reg.declare(_decl("ncaa-elo-v2", INSTEAD), **kw)                    # the 2026 season is open


# --- (c) ncaa-backtest is closed ---------------------------------------------------------------------------------

def test_ncaa_backtest_refuses_for_good_naming_the_ruling_before_reading(monkeypatch):
    from cli import cli

    monkeypatch.setattr(nb, "load_games", _boom)
    monkeypatch.setattr(nb, "build_stream", _boom)
    for lifted in (True, False):                                       # the fence does not decide it
        monkeypatch.setattr(nb, "v1r_run_recorded", lambda *a, _l=lifted: _l)
        for args in ([], ["--baselines-only"], ["--candidate", "v1"]):
            res = CliRunner().invoke(cli, ["ncaa-backtest", *args])
            assert res.exit_code == 2, (lifted, args, res.output)
            assert "ncaa-backtest REFUSED (exit 2)" in res.output
            assert "ARCHITECT 2026-10-09, addendum 24 item 2(c)" in res.output and RULING_C in res.output


def test_gate_status_is_closed_with_the_rulings_date_wherever_printed():
    assert nb.GATE_STATUS == "CLOSED"
    assert nb.GATE_STATUS_LINE.startswith("NCAA GATE: CLOSED (ruling 2026-10-09")
    assert "SUSPENDED" not in nb.GATE_STATUS_LINE
    st = nb.build_stream([])
    lines = []
    nb.coverage_report(st, out=lines.append, fbs=None, fenced=False)   # what ncaa-cfbd-coverage prints
    assert any(nb.GATE_STATUS_LINE in ln for ln in lines)
    assert not any("un-suspension" in ln or "SUSPENDED" in ln for ln in lines)


# --- (d) no college shadow on v1r --------------------------------------------------------------------------------

def _entry_with(tmp_path, verdict):
    e = dict(reg.get("ncaa-elo-v1r"))
    e.update({"verdict": verdict, "status": "declared" if verdict is None else e["status"]})
    p = tmp_path / f"reg-{verdict and verdict['verdict']}.json"
    p.write_text(json.dumps([e]))
    return str(p)


def test_the_shadow_refuses_once_the_registry_records_a_verdict_other_than_pass(tmp_path):
    for v in ("FAIL", "REJECT", "WITHDRAWN"):
        with pytest.raises(sh.ShadowRefused) as ex:
            sh.frozen(_entry_with(tmp_path, {"verdict": v, "ruling": "r", "at": "2026-10-09T17:00:00Z"}))
        msg = str(ex.value)
        assert msg.startswith("export-ncaa-predictions REFUSED (exit 2)") and f"verdict as {v}" in msg
        assert "ARCHITECT 2026-10-09, addendum 24 item 2(d)" in msg and RULING_D in msg
    for verdict in (None, {"verdict": "PASS", "ruling": "r", "at": "2026-10-09T17:00:00Z"}):
        e, neutral_ha, rule = sh.frozen(_entry_with(tmp_path, verdict))    # no verdict, or a PASS: not refused here
        assert rule == "no_home_advantage_at_neutral"
    with pytest.raises(sh.ShadowRefused, match="verdict as FAIL"):
        sh.frozen()                                                      # the committed registry: FAIL


def test_export_ncaa_predictions_exits_2_naming_the_ruling_before_reading(monkeypatch):
    from cli import cli

    monkeypatch.setattr(sh, "fit", _boom)
    monkeypatch.setattr(sh, "fbs_teams", _boom)
    res = CliRunner().invoke(cli, ["export-ncaa-predictions"])
    assert res.exit_code == 2, res.output
    assert "ARCHITECT 2026-10-09, addendum 24 item 2(d)" in res.output and RULING_D in res.output


# --- (e) the fence lifted by itself ------------------------------------------------------------------------------

def test_the_fence_is_lifted_by_the_recorded_run():
    assert nb.v1r_run_recorded() is True
