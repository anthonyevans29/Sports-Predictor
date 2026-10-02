"""NHL-xG v6 (#153 part 2; corrected manifest #210): the pre-committed rules,
the frozen 2023-24 fit, the NO-SAME-GAME-LEAKAGE proof and the harness's
registry refusals. Synthetic data only; nothing is run against the real DB."""
import math
import random
from datetime import datetime, timedelta

import pytest

from src.models import nhl_xg as nx
from src.models.nhl_elo import NHLEloConfig, NHLEloV1, NHLEloV6
from src.walters import nhl_backtest as nb

T = datetime(2023, 11, 1, 0, 0)


def shot(et="shot-on-goal", side="home", x=80.0, y=0.0, code="1551", hds="left", st="wrist",
         period=1, ptype="REG", gt=2, start=T, mid=None, gid=1):
    return nx.Shot(gid, mid, start, gt, et, period, ptype, side, side, x, y, st, code, hds)


def test_rules_in_order_with_reasons():
    ex = lambda **k: nx.prepare(shot(**k)).excluded
    assert ex(et="blocked-shot") == "blocked"
    assert ex(et="faceoff") == "not_eligible"
    assert ex(ptype="SO") == "shootout" and ex(period=5) == "shootout"
    assert ex(period=5, gt=3) is None                                          # playoff OT is hockey, not a shootout
    assert nx.prepare(nx.Shot(1, None, T, 2, "goal", 1, "REG", None, None, 80, 0, None, "1551", "left")).excluded == "no_side"
    assert ex(code=None) == "no_situation" and ex(code="15x1") == "no_situation"
    assert ex(side="away", code="1560") == "empty_net"                         # away shoots at an empty home net
    assert ex(side="home", code="1560") is None                                # home shoots at a manned net
    assert ex(x=None) == "missing_coords"
    assert ex(hds=None) == "no_orientation"


def test_orientation_distance_angle_and_situation():
    p = nx.prepare(shot(side="home", x=80.0, y=0.0, hds="left"))                # home attacks x=+89
    assert p.distance == pytest.approx(9.0) and p.angle == pytest.approx(0.0) and p.situation == "EV"
    a = nx.prepare(shot(side="away", x=-80.0, y=9.0, hds="left"))               # away attacks x=-89
    assert a.distance == pytest.approx(math.hypot(9, 9)) and a.angle == pytest.approx(45.0)
    r = nx.prepare(shot(side="home", x=-80.0, y=0.0, hds="right"))              # sides swap by period
    assert r.distance == pytest.approx(9.0)
    assert nx.prepare(shot(side="home", code="1561")).situation == "PP"         # home 6 skaters vs away 5
    assert nx.prepare(shot(side="away", code="1561")).situation == "SH"
    assert nx.prepare(shot(et="goal")).goal == 1 and nx.prepare(shot()).goal == 0


def test_fit_recovers_the_distance_effect_and_refuses_outside_2023_24():
    rng = random.Random(7)
    shots = []
    for i in range(6000):
        d = rng.uniform(5, 60)
        p = 1 / (1 + math.exp(-(0.5 - 0.08 * d)))
        st = rng.choice(["wrist", "slap", "snap", None])
        shots.append(shot(et="goal" if rng.random() < p else "shot-on-goal", x=89 - d, y=0.0, st=st,
                          start=T + timedelta(minutes=i)))
    m = nx.fit(shots)
    c = dict(zip(m.names, m.coef))
    assert c["distance"] == pytest.approx(-0.08, abs=0.02)
    assert "shot:na" in m.names or m.baseline_level == "na"                    # missing shot type is its own level
    assert m.fit_last_game < nx.FIT_TO
    with pytest.raises(ValueError, match="fit window violated"):
        nx.fit(shots + [shot(start=datetime(2024, 10, 20))])


def _stream(n=60):
    teams = [1, 2, 3, 4]
    rng = random.Random(3)
    games = []
    for i in range(n):
        h, a = rng.sample(teams, 2)
        games.append(nb.Game(h, a, "2025", datetime(2025, 10, 10) + timedelta(days=i), rng.randint(0, 5),
                             rng.randint(0, 5), match_id=1000 + i))
    return games


def test_no_same_game_leakage_proof():
    """Changing a game's OWN shots (its xG margin) never changes that game's
    prediction — only later games'."""
    games = _stream()
    xg = {g.match_id: (2.5, 2.0) for g in games}
    k = 30

    def preds(xgmap):
        m = NHLEloV6(NHLEloConfig(home_advantage=20.0), xg_by_match=dict(xgmap))
        out = []
        for g in games:
            out.append(m.predict(g))
            m.update(g)
        return out

    base = preds(xg)
    xg2 = dict(xg)
    xg2[games[k].match_id] = (6.0, 0.1)                     # the game's own shots change a lot
    alt = preds(xg2)
    assert alt[:k + 1] == base[:k + 1]                      # up to and INCLUDING game k: identical
    assert any(a != b for a, b in zip(alt[k + 1:], base[k + 1:]))


def test_update_direction_is_the_xg_winner_not_the_actual_winner():
    """RATIFIED 2026-10-02: the actual result is the scoring label only."""
    g = nb.Game(1, 2, "2025", datetime(2025, 10, 10), 4, 1, match_id=77)          # home WINS on goals
    v6 = NHLEloV6(NHLEloConfig(), xg_by_match={77: (1.2, 3.4)})                   # but LOSES on xG
    v6.predict(g)
    v6.update(g)
    assert v6.rating(1) < 1500.0 < v6.rating(2)                                   # moved with xG, against the result
    tie = NHLEloV6(NHLEloConfig(), xg_by_match={77: (2.0, 2.0)})
    tie.update(g)
    assert tie.rating(1) == tie.rating(2) == 1500.0                                # exact xG tie: nothing moves


def test_v6_is_v1_when_xg_margin_equals_goal_margin_and_falls_back_without_xg():
    games = _stream(20)
    v1, v6 = NHLEloV1(NHLEloConfig()), NHLEloV6(NHLEloConfig(), xg_by_match={
        g.match_id: (float(g.home_score), float(g.away_score)) for g in games[:10]})
    for g in games:
        assert v6.predict(g) == pytest.approx(v1.predict(g))
        v1.update(g)
        v6.update(g)
    assert (v6.xg_updates, v6.goal_margin_fallbacks) == (10, 10)


def test_harness_refuses_without_declaration_or_after_a_run(monkeypatch):
    from click.testing import CliRunner
    import cli
    from src.walters import registry as reg
    monkeypatch.setattr(nb, "load_games", lambda: [])
    monkeypatch.setattr(reg, "get", lambda eid, path=None: None)
    r = CliRunner().invoke(cli.cli, ["nhl-backtest", "--candidate", "v6"])
    assert r.exit_code == 2 and "not declared" in r.output
    monkeypatch.setattr(reg, "get", lambda eid, path=None: {"run": {"run_at": "x"}})
    r = CliRunner().invoke(cli.cli, ["nhl-backtest", "--candidate", "v6"])
    assert r.exit_code == 2 and "evaluated once" in r.output


def test_repo_declaration_is_frozen_and_unrun():
    from src.walters import registry as reg
    e = reg.get("nhl-v6")
    assert e["status"] == "declared" and e["run"] is None and e["declaration"] == "docs/specs/nhl-xg-v6.md"
    assert len(reg.prior_reads(e["test_set"], None, before_id="nhl-v6")) == 5
