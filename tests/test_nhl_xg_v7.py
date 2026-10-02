"""NHL-xG v7 (ARCHITECT 2026-10-02): v6 with the xG "na" shot-type level
REMOVED — the label-leak correctness fix. An untyped event takes the
baseline level; v6's model is untouched; the harness path is v6's with its
own registry id (refusals before any data load); the declaration is frozen,
unrun, and shares v6's test set, gate and confirmation plan."""
import math
import random
from datetime import timedelta

import pytest

from src.models import nhl_xg as nx
from src.models.nhl_elo import NHLEloV6, NHLEloV7
from src.walters import nhl_backtest as nb
from tests.test_nhl_xg_v6 import T, shot


def _leaky_shots(n=6000):
    """Missing shot type almost never on goals: exactly the v6 defect."""
    rng = random.Random(11)
    out = []
    for i in range(n):
        d = rng.uniform(5, 60)
        goal = rng.random() < 1 / (1 + math.exp(-(0.5 - 0.08 * d)))
        st = rng.choice(["wrist", "slap", "snap"]) if goal or rng.random() < 0.8 else None
        out.append(shot(et="goal" if goal else "shot-on-goal", x=89 - d, y=0.0, st=st,
                        start=T + timedelta(minutes=i)))
    return out


def test_v7_has_no_na_level_and_untyped_events_take_the_baseline():
    shots = _leaky_shots()
    v6 = nx.fit(shots)
    v7 = nx.fit(shots, na_level=False)
    assert "shot:na" in v6.names and v6.na_level is True                     # v6 untouched (the leak is visible)
    assert dict(zip(v6.names, v6.coef))["shot:na"] < -1.0
    assert not any(n == "shot:na" for n in v7.names) and v7.baseline_level != "na" and v7.na_level is False
    untyped = nx.prepare(shot(x=70.0, st=None))
    typed = nx.prepare(shot(x=70.0, st=v7.baseline_level))
    assert v7.row(untyped) == v7.row(typed) and v7.xg(untyped) == pytest.approx(v7.xg(typed))
    assert v6.xg(untyped) < v6.xg(typed)                                     # v6 priced the missing type as a non-goal


def test_v7_elo_is_v6_renamed():
    assert issubclass(NHLEloV7, NHLEloV6) and NHLEloV7.update is NHLEloV6.update
    assert NHLEloV7.name == "nhl_elo_v7_xg_margin_no_na"


def test_harness_v7_refuses_without_declaration_or_after_a_run(monkeypatch):
    from click.testing import CliRunner
    import cli
    from src.walters import registry as reg
    asked = []
    monkeypatch.setattr(nb, "load_games", lambda: (_ for _ in ()).throw(AssertionError("data loaded")))
    monkeypatch.setattr(reg, "get", lambda eid, path=None: asked.append(eid))
    r = CliRunner().invoke(cli.cli, ["nhl-backtest", "--candidate", "v7"])
    assert r.exit_code == 2 and "nhl-v7 is not declared" in r.output and asked == ["nhl-v7"]
    monkeypatch.setattr(reg, "get", lambda eid, path=None: {"run": {"run_at": "x"}})
    r = CliRunner().invoke(cli.cli, ["nhl-backtest", "--candidate", "v7"])
    assert r.exit_code == 2 and "nhl-v7 already ran" in r.output


def test_repo_declaration_v7_frozen_unrun_and_v6s_test_set():
    from src.walters import registry as reg
    e, v6 = reg.get("nhl-v7"), reg.get("nhl-v6")
    assert e["status"] == "declared" and e["run"] is None and e["declaration"] == "docs/specs/nhl-xg-v7.md"
    for k in ("test_set", "gate", "training_cutoff", "confirmation_plan"):
        assert e[k] == v6[k]
    ids = [x["id"] for x in reg.load()]
    assert ids.index("nhl-v6") < ids.index("nhl-v7")                          # v6's run counts as a prior read
    reads = reg.prior_reads(e["test_set"], None, before_id="nhl-v7")
    assert len(reads) == (6 if v6["run"] else 5)
