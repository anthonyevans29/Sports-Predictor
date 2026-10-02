"""#220 lane 2 harness, built from the ratified docs/specs/intl-elo-v1.md:
the update (draws S=0.5 with max(margin,1), gap factor 1; H +100 / 0 /
unknown +100; K by class), the soccer Elo->Poisson three-way, the naive
baseline, the RULE CHECK and the pre-declared v2 host-city rule, the 90-minute
label (AET/PEN without one excluded), walk-forward (a game's own result never
reaches its prediction), the unruled CNL_Q refusal, and the CLI's registry
refusal before any data load. Synthetic data; the real ledger is untouched."""
import math
from datetime import datetime, timedelta

import pytest
from click.testing import CliRunner

from src.walters import intl_elo as ie


def G(i, code, home, away, hg, ag, when, neutral=False, season="2019", city=None):
    return ie.Game(i, code, season, when, home, away, hg, ag, neutral, city)


def test_draw_moves_like_a_one_goal_result_toward_the_expected_draw_point():
    m = ie.IntlElo(mu=1.3)
    g = G(1, "UNL", 1, 2, 1, 1, datetime(2019, 9, 1))
    m.update(g)
    exp_h = 1 / (1 + 10 ** ((1500 - 1600) / 400))                    # +100 home term
    d = 40 * math.log(2) * (0.5 - exp_h)                             # K 40, gap factor 1
    assert m.r(1) == pytest.approx(1500 + d) and m.r(2) == pytest.approx(1500 - d) and d < 0
    n = ie.IntlElo(mu=1.3)
    n.update(G(1, "UNL", 1, 2, 1, 1, datetime(2019, 9, 1), neutral=True))
    assert n.r(1) == pytest.approx(1500.0)                           # neutral, equal: a draw is expected-ish


def test_win_margin_gap_factor_k_and_home_terms():
    m = ie.IntlElo(mu=1.3)
    m.update(G(1, "WCQ_EU", 1, 2, 3, 0, datetime(2019, 9, 1)))
    exp_h = 1 / (1 + 10 ** (-100 / 400))
    mov = math.log(4) * 2.2 / (2.2 + 100 * 0.001)
    assert m.r(1) - 1500 == pytest.approx(50 * mov * (1 - exp_h))
    assert ie.home_term(G(1, "UNL", 1, 2, 0, 0, datetime(2019, 1, 1), neutral=None)) == 100.0
    assert ie.home_term(G(1, "UNL", 1, 2, 0, 0, datetime(2019, 1, 1), neutral=True)) == 0.0
    assert ie.K_BY_CODE["FRIENDLIES_INT"] == 20 and ie.K_BY_CODE["CNL"] == 40 and ie.K_BY_CODE["UEFA_EURO"] == 60
    assert "CNL_Q" not in ie.K_BY_CODE


def test_three_way_is_the_soccer_mapping_and_symmetric_at_neutral():
    m = ie.IntlElo(mu=1.3)
    ph, pd, pa = m.probs(G(1, "UNL", 1, 2, 0, 0, datetime(2019, 1, 1), neutral=True))
    assert ph + pd + pa == pytest.approx(1.0) and ph == pytest.approx(pa) and pd > 0.25
    h = m.probs(G(1, "UNL", 1, 2, 0, 0, datetime(2019, 1, 1)))
    assert h[0] > ph and h[2] < pa                                   # +100 lives in the Elo difference


def test_naive_baseline_frozen_and_symmetric_at_neutral():
    t = datetime(2019, 1, 1)
    train = [G(1, "UNL", 1, 2, 1, 0, t), G(2, "UNL", 1, 2, 0, 0, t), G(3, "UNL", 1, 2, 0, 1, t),
             G(4, "UNL", 1, 2, 2, 0, t, neutral=None), G(5, "UEFA_EURO", 1, 2, 1, 1, t, neutral=True),
             G(6, "UEFA_EURO", 1, 2, 2, 1, t, neutral=True)]
    b = ie.naive(train)
    assert b["home"] == (0.5, 0.25, 0.25) and b["neutral"] == (0.25, 0.5, 0.25)
    with pytest.raises(ValueError):
        ie.naive(train[:4])


def test_rule_check_and_the_v2_host_city_rule():
    from src.ingestion.intl_history import norm_city
    t = datetime(2019, 1, 1)
    games = [G(1, "WCQ_EU", 10, 20, 1, 0, t, neutral=True, city="Munich"),     # v1: Munich != Berlin ground
             G(2, "UNL", 10, 30, 1, 0, t, neutral=True, city="Dortmund"),
             G(3, "UNL", 20, 10, 0, 0, t, neutral=False, city="Paris"),
             G(4, "FRIENDLIES_INT", 10, 40, 2, 0, t, neutral=True, city="Abu Dhabi"),
             G(5, "FRIENDLIES_INT", 10, 20, 1, 1, t, neutral=False, city="munich")]
    rc = ie.rule_check(games)
    assert (rc["neutral"], rc["known"], rc["breached"]) == (2, 3, True)
    v2, c = ie.apply_v2(games, norm_city)
    flags = {g.id: g.neutral for g in v2}
    assert flags == {1: False, 2: False, 3: False, 4: True, 5: False}   # Abu Dhabi: a friendly, not a host city
    assert ie.apply_v2([G(9, "FRIENDLIES_INT", 50, 10, 1, 0, t, city="Rome")], norm_city)[0][0].neutral is None


def _stream():
    out, i, t = [], 0, datetime(2018, 3, 1)
    while t < datetime(2026, 3, 30):
        for code, season in (("UNL", "2024/25" if datetime(2024, 9, 1) <= t < datetime(2025, 7, 1) else "2019/20"),
                             ("WCQ_EU", "2026"), ("FRIENDLIES_INT", str(t.year))):
            i += 1
            h, a = 1 + i % 6, 1 + (i + 2) % 6
            out.append(G(i, code, h, a, i % 3, (i // 3) % 2, t, neutral=(i % 7 == 0) if code != "UNL" else False,
                         season=season))
        t += timedelta(days=9)
    return out


def test_walk_forward_scores_only_the_test_set_and_never_its_own_result():
    games = _stream()
    r = ie.run(games)
    test = [g for g in games if ie.is_test(g)]
    assert r["n_test"] == len(test) > 50 and sorted(r["scored_ids"]) == sorted(g.id for g in test)
    assert set(r["per_competition"]) == {"UNL", "WCQ_EU"} and r["bar"] == pytest.approx(r["ll_naive"] - 0.010)
    k = next(j for j, g in enumerate(games) if ie.is_test(g))
    g = games[k]
    flipped = games[:k] + [ie.Game(g.id, g.code, g.season, g.kickoff, g.home, g.away, g.ag + 5, g.hg, g.neutral)] \
        + games[k + 1:]
    m1, m2 = ie.IntlElo(mu=r["mu"]), ie.IntlElo(mu=r["mu"])
    for x in games[:k]:
        m1.update(x)
    for x in flipped[:k]:
        m2.update(x)
    assert m1.probs(g) == m2.probs(flipped[k])                        # its own result never reaches it


def test_unruled_cnl_q_refuses_the_run():
    games = _stream() + [G(10**6, "CNL_Q", 1, 2, 1, 0, datetime(2018, 9, 1))]
    with pytest.raises(ValueError, match="K class not ruled for CNL_Q"):
        ie.run(games)


def test_load_uses_90_minute_labels_and_excludes_aet_without_one():
    from sqlalchemy import select

    from src.db.database import init_db, session_scope
    from src.db.schema import Competition, Match, MatchNeutralDerived, MatchStatus, Sport, Team
    init_db()
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == "UEFA_EURO")).scalar_one_or_none()
        if comp is None:
            comp = Competition(sport=Sport.SOCCER, code="UEFA_EURO", name="Euro", area="I", type="INTL")
            s.add(comp)
            s.flush()
        a, b = Team(sport=Sport.SOCCER, name="Elo Probe A"), Team(sport=Sport.SOCCER, name="Elo Probe B")
        s.add_all([a, b])
        s.flush()
        mk = lambda d, raw, hs, as_, h90, a90: Match(  # noqa: E731
            sport=Sport.SOCCER, competition_id=comp.id, season="2093", utc_date=d, status=MatchStatus.FINISHED,
            status_raw=raw, home_team_id=a.id, away_team_id=b.id, home_score=hs, away_score=as_,
            home_score_90=h90, away_score_90=a90)
        ms = [mk(datetime(2093, 6, 1), "AET", 2, 1, 1, 1), mk(datetime(2093, 6, 2), "PEN", 1, 1, None, None),
              mk(datetime(2093, 6, 3), "FT", 3, 0, None, None), mk(datetime(2093, 6, 4), None, 1, 0, None, None)]
        s.add_all(ms)
        s.flush()
        s.add(MatchNeutralDerived(match_id=ms[0].id, neutral_derived=True, rule="r", venue_city="X"))
        ids = [m.id for m in ms]
    with session_scope() as s:
        games, c = ie.load(s)
    mine = {g.id: g for g in games if g.id in ids}
    assert set(mine) == {ids[0], ids[2]}                               # PEN w/o 90' and no-status rows excluded
    assert (mine[ids[0]].hg, mine[ids[0]].ag, mine[ids[0]].neutral) == (1, 1, True)
    assert (mine[ids[2]].hg, mine[ids[2]].ag, mine[ids[2]].neutral) == (3, 0, None)
    assert c["excluded_no_90min_score"] >= 2


def test_cli_refuses_before_any_data_load_unless_declared_and_unrun(monkeypatch):
    from cli import cli
    from src.walters import registry as reg

    def boom(s):
        raise AssertionError("data was loaded")
    monkeypatch.setattr(ie, "load", boom)
    for state in (None, {"status": "run", "run": {"run_at": "x"}}):
        monkeypatch.setattr(reg, "get", lambda eid, state=state: state)
        res = CliRunner().invoke(cli, ["intl-elo-backtest"])
        assert res.exit_code == 2 and "REFUSED" in res.output


def test_cli_preflight_scores_and_records_nothing(monkeypatch):
    from cli import cli
    from src.walters import registry as reg
    monkeypatch.setattr(reg, "get", lambda eid: {"status": "declared", "run": None})
    monkeypatch.setattr(reg, "record_run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("recorded")))
    monkeypatch.setattr(ie, "load", lambda s: (_stream(), {}))
    monkeypatch.setattr(ie, "run", lambda g: (_ for _ in ()).throw(AssertionError("scored")))
    res = CliRunner().invoke(cli, ["intl-elo-backtest", "--preflight"])
    assert res.exit_code == 0, res.output
    assert "RULE CHECK" in res.output and "PREFLIGHT only" in res.output and "splits: train" in res.output
