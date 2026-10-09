"""#79 NCAA v1 gate (frozen 2026-09-30) + the a-priori Elo candidate:
stream rules, baselines, bar, verdict math, the model, DB scope, the CLI."""
import math
from datetime import date, datetime, timedelta

import pytest

from src.models.ncaa_elo import NCAAEloConfig, NCAAEloV1
from src.walters import ncaa_backtest as nb


def G(h, a, season, d, hs, as_, stage="Regular Season"):
    return nb.Game(h, a, season, d if isinstance(d, datetime) else datetime.combine(d, datetime.min.time()),
                   hs, as_, stage)


# --- frozen constants ---------------------------------------------------------

def test_frozen_gate_constants():
    assert (nb.TRAIN_SEASON, nb.TEST_SEASON) == ("2025", "2026")
    assert nb.NCAA_COMPETITION_CODE == "NCAA"
    assert nb.LL_MARGIN == 0.010 and nb.BAND_MIN_N == 100 and nb.BAND_TOL == 0.05
    assert (nb.RATING_MIN, nb.RATING_MAX) == (1000.0, 2000.0)
    assert nb.MIN_TEST_N == 500


def test_frozen_candidate_constants():
    c = NCAAEloConfig()
    assert (c.k_factor, c.home_advantage, c.mov_base, c.season_regression, c.default_rating) \
        == (24.0, 55.0, 2.2, 0.25, 1500.0)


# --- stream selection -------------------------------------------------------------

def test_pre_and_postseason_excluded_by_stage():
    games = [
        G(1, 2, "2025", date(2025, 9, 6), 30, 10),                           # kept
        G(1, 2, "2025", date(2025, 8, 20), 30, 10, stage="Pre Season"),      # preseason
        G(1, 2, "2025", date(2025, 12, 27), 30, 10, stage="Post Season"),    # bowl
        G(2, 1, "2026", date(2026, 9, 5), 14, 21),                           # kept
        G(2, 1, "2026", date(2026, 9, 5), 14, 21, stage=""),                 # empty stage kept
    ]
    st = nb.build_stream(games)
    assert len(st.train) == 1 and len(st.test) == 2
    assert st.excluded[("2025", "preseason")] == 1
    assert st.excluded[("2025", "postseason")] == 1


def test_other_seasons_ignored_and_ties_counted():
    games = [G(1, 2, "2024", date(2024, 9, 7), 21, 3),
             G(1, 2, "2025", date(2025, 9, 7), 17, 17)]
    st = nb.build_stream(games)
    assert not st.train and st.ties == 1
    assert st.other_seasons == {"2024": 1}


def test_stream_is_chronological():
    games = [G(1, 2, "2026", date(2026, 9, 12), 3, 0), G(3, 4, "2026", date(2026, 9, 5), 3, 0)]
    st = nb.build_stream(games)
    assert [g.home_id for g in st.test] == [3, 1]


# --- baselines + bar ------------------------------------------------------------

def _stream(train_home_wins, train_n, test_home_wins, test_n):
    d0, d1 = datetime(2025, 9, 1), datetime(2026, 9, 1)
    tr = [G(1, 2, "2025", d0 + timedelta(hours=i), 28 if i < train_home_wins else 7, 14)
          for i in range(train_n)]
    te = [G(1, 2, "2026", d1 + timedelta(hours=i), 28 if i < test_home_wins else 7, 14)
          for i in range(test_n)]
    return nb.build_stream(tr + te)


def test_baselines_use_train_home_rate_and_declare_the_bar():
    st = _stream(600, 1000, 300, 600)
    r = nb.baselines(st)
    assert not r.verdict
    assert r.home_rate == pytest.approx(0.60)
    assert r.test_home_rate == pytest.approx(0.50)
    assert r.ll_const == pytest.approx(math.log(2))
    exp = -(0.5 * math.log(0.6) + 0.5 * math.log(0.4))
    assert r.ll_home == pytest.approx(exp)
    assert r.bar == pytest.approx(exp - 0.010)
    assert r.brier_const == pytest.approx(0.25)
    assert r.test_first == datetime(2026, 9, 1)
    assert r.test_last == datetime(2026, 9, 1) + timedelta(hours=599)


def test_missing_season_is_invalid():
    st = nb.build_stream([G(1, 2, "2025", date(2025, 9, 6), 30, 10)])
    assert nb.baselines(st).verdict.startswith("INVALID — protocol")


def test_coverage_floor_is_inclusive_at_500():
    assert nb.baselines(_stream(60, 100, 250, 500)).verdict == ""
    r = nb.baselines(_stream(60, 100, 250, 499))
    assert r.verdict.startswith("INVALID — insufficient coverage")
    # the candidate is never scored on an INVALID stream
    assert nb.run_gate(_stream(60, 100, 250, 499), NCAAEloV1()).ll_model is None


# --- verdict math with stub predictors -------------------------------------------

class Const:
    def __init__(self, p, ratings=None):
        self.p, self._r = p, ratings or {1: 1650.0, 2: 1350.0}
    def predict(self, g): return self.p
    def update(self, g): pass
    def ratings(self): return self._r


class Oracle(Const):
    def predict(self, g): return self.p if g.home_win else 1 - self.p


def test_constant_home_rate_model_ties_the_baseline_and_is_rejected():
    st = _stream(330, 600, 330, 600)
    r = nb.run_gate(st, Const(0.55))
    assert r.ll_model == pytest.approx(r.ll_home)
    assert not r.crit_ll and r.verdict.startswith("FAIL")


def test_margin_is_inclusive_at_exactly_0_010():
    assert nb.beats_margin(0.680, 0.690)
    assert not nb.beats_margin(0.681, 0.690)
    assert not nb.beats_margin(0.690, 0.690)


def test_bands_gate_only_when_n_at_least_100_and_tolerance_5pp():
    pairs = [(0.65, 1)] * 99
    b = nb.calibration_bands(pairs)[0]
    assert not b["gated"] and b["ok"] is None
    assert nb.calibration_bands(pairs + [(0.65, 1)])[0]["ok"] is False
    ok = [(0.60, 1)] * 65 + [(0.60, 0)] * 35
    bad = [(0.60, 1)] * 66 + [(0.60, 0)] * 34
    assert nb.calibration_bands(ok)[0]["ok"]
    assert not nb.calibration_bands(bad)[0]["ok"]


def test_rating_spread_outlier_fails():
    st = _stream(330, 600, 330, 600)
    r = nb.run_gate(st, Oracle(0.9, ratings={1: 2050.0, 2: 1500.0, 3: 990.0}))
    assert r.outliers == [(1, 2050.0), (3, 990.0)] and not r.crit_spread
    assert "rating spread" in r.verdict


class ByTeam(Const):
    def predict(self, g): return 0.7 if g.home_id == 1 else 0.3


def _calibrated_world():
    d0, d1 = datetime(2025, 9, 1), datetime(2026, 9, 1)
    train = [G(1, 2, "2025", d0 + timedelta(hours=i), 28 if i % 2 else 7, 14) for i in range(200)]
    test = ([G(1, 2, "2026", d1 + timedelta(hours=i), 28 if i < 210 else 7, 14) for i in range(300)]
            + [G(3, 2, "2026", d1 + timedelta(hours=400 + i), 28 if i < 90 else 7, 14) for i in range(300)])
    return nb.build_stream(train + test)


def test_full_pass_path():
    r = nb.run_gate(_calibrated_world(), ByTeam(None))
    assert r.home_rate == pytest.approx(0.5)
    assert r.ll_model == pytest.approx(-(0.7 * math.log(0.7) + 0.3 * math.log(0.3)))
    assert r.brier_model == pytest.approx(0.21) and r.rps_model == pytest.approx(r.brier_model)
    assert r.crit_ll and r.crit_bands and r.crit_spread
    assert r.verdict.startswith("PASS")
    assert r.cold_start_games == 1     # team 3's first game only (no prior game)


def test_sharp_but_uncalibrated_fails_bands():
    r = nb.run_gate(_stream(300, 600, 300, 600), Oracle(0.62))
    assert r.crit_ll and not r.crit_bands and r.verdict == "FAIL — calibration"


def test_report_baselines_only_prints_bar_and_no_verdict():
    st = _stream(330, 600, 300, 600)
    lines = []
    nb.report(st, nb.baselines(st), out=lines.append)
    text = "\n".join(lines)
    assert "constant 0.5" in text and "train home rate" in text
    assert "BAR (frozen): candidate log-loss need <=" in text
    assert "TEST SET: n=600" in text and "2026-09-01 .. 2026-09-25" in text
    assert "baselines only" in text and "GATE VERDICT" not in text


def test_report_full_verdict():
    st = _calibrated_world()
    lines = []
    nb.report(st, nb.run_gate(st, ByTeam(None)), out=lines.append, model_name="stub")
    text = "\n".join(lines)
    assert "GATE VERDICT: PASS" in text and "1) log-loss" in text and "info (not gated)" in text


# --- the candidate ------------------------------------------------------------------

def test_elo_update_is_zero_sum_and_home_advantage_prices_equals():
    m = NCAAEloV1()
    g = G(1, 2, "2025", date(2025, 9, 6), 35, 7)
    p = m.predict(g)
    assert p == pytest.approx(1 / (1 + 10 ** (-55 / 400)))
    m.update(g)
    r = m.ratings()
    assert r[1] + r[2] == pytest.approx(3000.0) and r[1] > 1500 > r[2]
    # MOV multiplier: a bigger win moves more
    m2 = NCAAEloV1()
    m2.update(G(1, 2, "2025", date(2025, 9, 6), 10, 7))
    assert m2.ratings()[1] < r[1]


def test_cold_start_team_prices_at_default():
    m = NCAAEloV1()
    m.update(G(1, 2, "2025", date(2025, 9, 6), 42, 0))
    assert m.rating(99) == 1500.0
    assert m.predict(G(99, 98, "2025", date(2025, 9, 13), 0, 0)) == pytest.approx(
        1 / (1 + 10 ** (-55 / 400)))


def test_season_regression_at_a_teams_own_first_game_prices_regressed():
    m = NCAAEloV1()
    m._ratings, m._last_season = {1: 1700.0, 2: 1300.0}, {1: "2025", 2: "2025"}
    p = m.predict(G(1, 2, "2026", date(2026, 9, 5), 0, 0))
    assert m.rating(1) == pytest.approx(1650.0) and m.rating(2) == pytest.approx(1350.0)
    assert p == pytest.approx(1 / (1 + 10 ** ((1350 - 1650 - 55) / 400)))
    m.update(G(1, 2, "2026", date(2026, 9, 5), 21, 20))   # no double regression
    assert m._last_season == {1: "2026", 2: "2026"}


def test_candidate_runs_through_the_gate_on_synthetic_world():
    """Strong teams (ids < 10) beat weak teams: Elo should learn it and beat
    a constant; end-to-end smoke of the v1 path (writes nothing)."""
    import random
    rnd = random.Random(7)
    strength = {t: (1.0 if t < 10 else -1.0) for t in range(20)}
    games = []
    for season, start in (("2025", datetime(2025, 9, 1)), ("2026", datetime(2026, 9, 1))):
        for i in range(700):
            h, a = rnd.sample(range(20), 2)
            p = 1 / (1 + math.exp(-(strength[h] - strength[a] + 0.2)))
            hw = rnd.random() < p
            games.append(G(h, a, season, start + timedelta(hours=i), 28 if hw else 10, 21))
    r = nb.run_gate(nb.build_stream(games), NCAAEloV1())
    assert r.ll_model is not None and r.ll_model < r.ll_home
    assert r.rating_min is not None and r.teams_rated == 20


# --- DB loading + CLI ---------------------------------------------------------------

def _seed_ncaa(n_train=60, n_test=520):
    from src.db.database import init_db, session_scope
    from src.db.schema import Competition, Match, MatchStatus, Sport, Team

    init_db()
    with session_scope() as s:
        from sqlalchemy import select

        def comp(code, name):   # (sport, code) is unique; other tests may have made it
            c = s.execute(select(Competition).where(Competition.sport == Sport.NFL,
                                                    Competition.code == code)).scalar_one_or_none()
            if c is None:
                c = Competition(sport=Sport.NFL, code=code, name=name, area="USA", type="LEAGUE")
                s.add(c)
            return c
        ncaa, nfl = comp("NCAA", "NCAA Football"), comp("NFL", "NFL")
        a, b = Team(sport=Sport.NFL, name="Ncaa Test A"), Team(sport=Sport.NFL, name="Ncaa Test B")
        s.add_all([a, b])
        s.flush()

        def mk(comp, season, when, st, hs, as_, stage="Regular Season"):
            return Match(sport=Sport.NFL, competition_id=comp.id, season=season, utc_date=when,
                         status=st, home_team_id=a.id, away_team_id=b.id,
                         home_score=hs, away_score=as_, stage=stage)
        rows = [mk(ncaa, "2025", datetime(2025, 9, 1) + timedelta(hours=i), MatchStatus.FINISHED,
                   77 if i % 2 else 3, 76 if i % 2 else 4) for i in range(n_train)]
        rows += [mk(ncaa, "2026", datetime(2026, 9, 1) + timedelta(hours=i), MatchStatus.FINISHED,
                    77 if i % 3 else 3, 76 if i % 3 else 4) for i in range(n_test)]
        rows += [mk(ncaa, "2026", datetime(2026, 11, 1), MatchStatus.SCHEDULED, None, None),
                 mk(ncaa, "2026", datetime(2026, 9, 2), MatchStatus.FINISHED, None, None),
                 mk(nfl, "2026", datetime(2026, 9, 2), MatchStatus.FINISHED, 99, 98)]
        s.add_all(rows)
        return a.id


def _row_counts():
    from sqlalchemy import func, select

    from src.db.database import session_scope
    from src.db.schema import Base
    with session_scope() as s:
        return {t.name: s.execute(select(func.count()).select_from(t)).scalar_one()
                for t in Base.metadata.sorted_tables}


def test_load_games_scope_and_no_writes_then_cli(monkeypatch):
    from click.testing import CliRunner

    from cli import cli

    home_id = _seed_ncaa()
    before = _row_counts()
    games = nb.load_games()
    assert _row_counts() == before
    mine = [g for g in games if g.home_id == home_id]
    assert len(mine) == 580                                   # finished + scored NCAA only
    assert all((g.home_score, g.away_score) != (99, 98) for g in games)  # NFL row out

    runner = CliRunner()
    # ARCHITECT 2026-10-09, addendum 24 item 2(c): the command refuses for good, fence lifted or not; the module stays
    monkeypatch.setattr(nb, "v1r_run_recorded", lambda *a: True)
    for args in (["--baselines-only"], ["--candidate", "v1"]):
        res = runner.invoke(cli, ["ncaa-backtest", *args])
        assert res.exit_code == 2 and "ncaa-backtest REFUSED (exit 2)" in res.output and nb.CLOSED_RULING in res.output
    rep = []
    nb.report(nb.build_stream(games), nb.baselines(nb.build_stream(games)), out=rep.append)
    assert "BAR (frozen): candidate log-loss need <=" in "\n".join(rep)   # the module's report is unchanged
    assert _row_counts() == before                            # the CLI writes nothing
