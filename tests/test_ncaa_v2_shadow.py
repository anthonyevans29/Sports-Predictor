"""THE v2 SHADOW BINDING (ARCHITECT 2026-10-23, addendum 158 item 1(b)): "Prepare the v2 binding now (registry id, the
frozen s = 279.14222651259433, the version, input cutoff and prediction stamp on every row), under the same refusal
guard (it exports nothing unless the registry verdict is PASS) [...] A read-only receipt on synthetic cases that the
shadow's probabilities equal the gate path's." Pins:
- --id ncaa-elo-v2 refuses with no verdict, with a FAIL, with s unfrozen or not the ruled number; with a PASS it
  writes rows carrying the registry id, the version, the input cutoff, the prediction stamp and s, priced by the
  gate's own model at s; v1r is unchanged;
- grading never pools the two bindings' files;
- parity: on the seeded synthetic stream the shadow's probability of every game the gate scores equals the gate
  path's; a different model in the shadow path reads NOT EQUAL (the receipt can fail)."""
import json
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner

from src.walters import ncaa_backtest as nb
from src.walters import ncaa_shadow as sh
from tests.test_ncaa_shadow import NOW, V1, mine, world  # noqa: F401  (fixtures: the shadow's synthetic world)

ROOT = Path(__file__).resolve().parents[1]


def _v2_registry(tmp_path, verdict="PASS", s=sh.V2_FROZEN_S, name="experiments.json",
                 rule="no_home_advantage_at_neutral"):
    p = tmp_path / name
    e = {"id": sh.V2_EID, "sport": "ncaa", "constants": V1, "neutral_site_rule": rule,
         "logistic_scale": {"s": s}}
    if verdict is not None:
        e["verdict"] = {"verdict": verdict, "ruling": "x"}
    p.write_text(json.dumps([e]))
    return str(p)


def test_v2_refuses_without_a_recorded_pass_and_with_any_other_s(mine, tmp_path):
    for i, (verdict, s, msg) in enumerate(((None, sh.V2_FROZEN_S, "records no verdict for ncaa-elo-v2"),
                                           ("FAIL", sh.V2_FROZEN_S, "the verdict FAIL"),
                                           ("PASS", None, "the logistic scale s is not frozen"),
                                           ("PASS", 280.0, "not the ruled 279.14222651259433"))):
        reg = _v2_registry(tmp_path, verdict=verdict, s=s, name=f"r{i}.json")
        with pytest.raises(sh.ShadowRefused, match=msg):
            sh.export(now=NOW, out_dir=str(tmp_path / f"o{i}"), registry_path=reg, eid=sh.V2_EID)
        assert not list((tmp_path / f"o{i}").glob("ncaa_shadow_*.json"))
    with pytest.raises(sh.ShadowRefused, match="not a registry id the NCAA shadow serves"):
        sh.binding("ncaa-elo-v9")


def test_v2_rows_carry_the_binding_and_the_gates_model(mine, tmp_path):
    path, doc = sh.export(now=NOW, out_dir=str(tmp_path), registry_path=_v2_registry(tmp_path), eid=sh.V2_EID)
    assert (doc["registry_id"], doc["model_version"], doc["gate_verdict"]) == ("ncaa-elo-v2", "ncaa_elo_v2", "PASS")
    assert doc["note"] == sh.V2_NOTE and doc["fit"]["logistic_scale"] == sh.V2_FROZEN_S
    (r,) = doc["predictions"]
    assert (r["registry_id"], r["model_version"]) == ("ncaa-elo-v2", "ncaa_elo_v2")
    assert r["input_cutoff"] == NOW.isoformat() and r["prediction_stamp"] == NOW.isoformat()
    assert r["prediction"]["logistic_scale"] == sh.V2_FROZEN_S
    # the gate's own model at s (ncaa_v1r_gate.model_for's NeutralRuleElo), walked over the same stream before NOW
    m = nb.NeutralRuleElo(False, scale=sh.V2_FROZEN_S)
    sh.walk(m, nb.load_v1r_stream().games, NOW)
    t = mine["teams"]
    want = m.predict(nb.Game(t[0], t[1], "2026", NOW + timedelta(hours=5), 0, 0, "Regular Season"))
    assert r["match_id"] == mine["up"] and r["prediction"]["home_win_prob"] == round(want, 4)
    v1 = sh.export(now=NOW, out_dir=str(tmp_path / "v1"),
                   registry_path=str(Path(_v1r_registry(tmp_path))))[1]["predictions"][0]
    assert "logistic_scale" not in v1["prediction"] and v1["model_version"] == "ncaa_elo_v1r"
    assert v1["input_cutoff"] == NOW.isoformat()                      # every row, either binding
    p1, p2 = v1["prediction"]["home_win_prob"], r["prediction"]["home_win_prob"]
    assert p1 != p2 and (p1 - 0.5) * (p2 - 0.5) > 0 and abs(p2 - 0.5) > abs(p1 - 0.5)   # s < 400: sharper, same side


def _v1r_registry(tmp_path):
    p = tmp_path / "v1r.json"
    p.write_text(json.dumps([{"id": sh.EID, "sport": "ncaa", "constants": V1,
                              "neutral_site_rule": "no_home_advantage_at_neutral"}]))
    return str(p)


def test_grading_never_pools_the_two_bindings(mine, tmp_path):
    ex = tmp_path / "ex"
    sh.export(now=NOW - timedelta(hours=1), out_dir=str(ex), registry_path=_v1r_registry(tmp_path))
    sh.export(now=NOW, out_dir=str(ex), registry_path=_v2_registry(tmp_path), eid=sh.V2_EID)
    v1 = sh.last_calls(str(ex), eid=sh.EID)
    v2 = sh.last_calls(str(ex), eid=sh.V2_EID)
    assert {c["model_version"] for c in v1.values()} == {"ncaa_elo_v1r"}
    assert {c["model_version"] for c in v2.values()} == {"ncaa_elo_v2"}
    assert {c["model_version"] for c in sh.last_calls(str(ex)).values()} == {"ncaa_elo_v2"}   # None: the latest


def test_parity_on_the_synthetic_stream_is_equal_and_can_fail(monkeypatch):
    games = sh.synthetic_stream()
    r = sh.parity(games)
    assert r["compared"] == r["gate_scored"] > 100 and r["unequal"] == 0 and r["max_diff"] <= sh.PARITY_TOL
    assert r["neutral_scored"] > 0 and r["pregame_max_diff"] > 0                    # D8, reported
    assert "· EQUAL" in sh.parity_lines(r)[0]
    assert len({(g.utc_date) for g in games}) < len(games)                          # several games per kickoff
    real = sh.V1R
    monkeypatch.setattr(sh, "V1R", lambda ha, scale=None: real(ha, scale=400.0))    # a different model: caught
    bad = sh.parity(games)
    assert bad["unequal"] > 0 and "NOT EQUAL" in sh.parity_lines(bad)[0]


def test_the_receipt_script_prints_equal_and_reads_no_db(tmp_path):
    env = {"PATH": "/usr/bin:/bin", "DATABASE_URL": f"sqlite:///{tmp_path / 'absent.db'}", "PYTHONPATH": str(ROOT)}
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "ncaa_v2_shadow_parity.py")], capture_output=True,
                         text=True, cwd=tmp_path, env=env, timeout=300)
    assert out.returncode == 0, out.stderr
    assert "· EQUAL" in out.stdout and not (tmp_path / "absent.db").exists()


def test_cli_id_v2_refusal_exits_2(mine):
    from cli import cli

    res = CliRunner().invoke(cli, ["export-ncaa-predictions", "--id", "ncaa-elo-v2"])
    assert res.exit_code == 2 and "ncaa-elo-v2" in res.output


def test_architect_1026_the_v2_binding_refuses_any_neutral_rule_but_the_gates(mine, tmp_path):
    """ARCHITECT 2026-10-26 15:15 ET (#698): "the neutral-rule pin BLOCKS — the binding refuses any rule but the
    gate's". The gate's model is NeutralRuleElo's default (no home advantage at neutral sites); a v2 entry declaring
    the other rule exports nothing. v1r keeps either declared rule."""
    assert nb.NeutralRuleElo().neutral_home_advantage is False and sh.BINDINGS[sh.V2_EID].rule == sh.GATE_RULE
    reg = _v2_registry(tmp_path, rule="home_advantage_at_neutral", name="other.json")
    with pytest.raises(sh.ShadowRefused, match="not the gate's 'no_home_advantage_at_neutral'"):
        sh.export(now=NOW, out_dir=str(tmp_path / "o"), registry_path=reg, eid=sh.V2_EID)
    assert not list((tmp_path / "o").glob("ncaa_shadow_*.json"))
    assert sh.BINDINGS[sh.EID].rule is None
