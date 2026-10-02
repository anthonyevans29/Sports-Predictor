"""NHL-xG v8 (ARCHITECT 2026-10-02): v7 with the Elo's logistic divisor and k
FITTED BY MAXIMUM LIKELIHOOD on 2024 ONLY over the declared grid; the 2025
test set RETIRED after v8 (doctrine, enforced in the registry). Synthetic
data; the real DB is never read."""
import random
from datetime import datetime, timedelta

import pytest

from src.models.nhl_elo import V8_K_GRID, V8_SCALE_GRID, NHLEloConfig, NHLEloV7, NHLEloV8
from src.walters import nhl_backtest as nb
from src.walters import registry as reg

RETIRED = "NHL 2025 (2025-26 regular season; nhl_backtest TEST_SEASON, train 2024)"


def _season(season, n=120, seed=5):
    rng = random.Random(seed)
    out = []
    for i in range(n):
        h, a = rng.sample(range(1, 9), 2)
        out.append(nb.Game(h, a, season, datetime(int(season), 10, 10) + timedelta(days=i), rng.randint(0, 5),
                           rng.randint(0, 5), match_id=10_000 + i))
    return out


def test_scale_400_is_v7_and_the_divisor_changes_the_price():
    g = nb.Game(1, 2, "2024", datetime(2024, 10, 10), 3, 1, match_id=1)
    cfg = NHLEloConfig(home_advantage=45.6)
    assert NHLEloV8(cfg, scale=400.0).predict(g) == pytest.approx(NHLEloV7(cfg).predict(g))
    assert NHLEloV8(cfg, scale=600.0).predict(g) < NHLEloV8(cfg, scale=400.0).predict(g)   # flatter curve


def test_fit_is_train_only_over_the_declared_grid():
    train = _season("2024")
    xg = {g.match_id: (float(g.home_score) + 0.3, float(g.away_score)) for g in train}
    sel, rows = nb.fit_v8_scale_k(train, xg, 45.6)
    assert len(rows) == len(V8_SCALE_GRID) * len(V8_K_GRID) == 56
    best = min(r[0] for r in rows)
    assert sel["loss"] == best and (sel["scale"], sel["k"]) in {(r[1], r[2]) for r in rows if r[0] == best}
    assert sel["on_grid_edge"] == (sel["scale"] in (300.0, 600.0) or sel["k"] in (3.0, 12.0))
    with pytest.raises(ValueError, match="training season only"):
        nb.fit_v8_scale_k(train + _season("2025", 5), xg, 45.6)


def test_fit_tie_goes_to_v1s_pair():
    # no xG and no games that discriminate -> identical losses; the tie goes to (400, 6)
    g = [nb.Game(1, 2, "2024", datetime(2024, 10, 10), 2, 2, match_id=1)]
    sel, _ = nb.fit_v8_scale_k(g, {1: (2.0, 2.0)}, 0.0)
    assert (sel["scale"], sel["k"]) == (400.0, 6.0)


def _decl(eid, test_set):
    return {"id": eid, "sport": "nhl", "lane": "#153", "candidate": "c", "declaration": "d", "training_cutoff": "t",
            "test_set": test_set, "gate": "g", "confirmation_window": "w",
            "confirmation_plan": {"n_games": 150, "metric": "log_loss", "bar": 0.6866, "must_beat_reference": True,
                                  "reference": "v1"}}


def test_retired_test_set_refuses_any_candidate_after_v8(tmp_path):
    kw, ids = {"path": str(tmp_path / "x.json")}, str(tmp_path / "ids")
    with pytest.raises(reg.RegistryError, match="RETIRED.*2026-27"):
        reg.declare(_decl("nhl-v9", RETIRED), **kw)
    reg.declare(_decl("nhl-v8", RETIRED), **kw)                       # the last one allowed
    reg.record_run("nhl-v8", [1, 2], {"log_loss": 0.69}, ids_dir=ids, **kw)
    reg.declare(_decl("nhl-v9", "NHL 2026-27 regular season"), **kw)  # the new test season is open


def test_repo_v8_on_v7s_test_set_and_v9_refused():
    e, v7 = reg.get("nhl-v8"), reg.get("nhl-v7")
    assert e["status"] in ("declared", "run", "closed") and e["declaration"] == "docs/specs/nhl-xg-v8.md"
    for k in ("test_set", "gate", "confirmation_plan"):
        assert e[k] == v7[k]
    assert e["test_set"] == RETIRED and reg.RETIRED_TEST_SETS[RETIRED][0] == "nhl-v8"
    ids = [x["id"] for x in reg.load()]
    assert ids.index("nhl-v7") < ids.index("nhl-v8")
    ran = sum(1 for x in ("nhl-v6", "nhl-v7") if reg.get(x)["run"])
    assert len(reg.prior_reads(e["test_set"], None, before_id="nhl-v8")) == 5 + ran   # 7 once both are spliced


def test_harness_v8_refuses_without_declaration_or_after_a_run(monkeypatch):
    from click.testing import CliRunner
    import cli
    monkeypatch.setattr(nb, "load_games", lambda: (_ for _ in ()).throw(AssertionError("data loaded")))
    monkeypatch.setattr(reg, "get", lambda eid, path=None: None)
    r = CliRunner().invoke(cli.cli, ["nhl-backtest", "--candidate", "v8"])
    assert r.exit_code == 2 and "nhl-v8 is not declared" in r.output
    monkeypatch.setattr(reg, "get", lambda eid, path=None: {"run": {"run_at": "x"}})
    r = CliRunner().invoke(cli.cli, ["nhl-backtest", "--candidate", "v8"])
    assert r.exit_code == 2 and "nhl-v8 already ran" in r.output
