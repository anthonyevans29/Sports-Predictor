"""NHL Phase 2 gate (frozen 2026-09-25): stream rules, baselines, verdict math."""
import math
from datetime import date, datetime, timedelta

import pytest

from src.walters import nhl_backtest as nb


def G(h, a, season, d, hs, as_, stage=""):
    return nb.Game(h, a, season, d if isinstance(d, datetime) else datetime.combine(d, datetime.min.time()),
                   hs, as_, stage)


# --- stream selection ----------------------------------------------------------

def test_preseason_excluded_by_date_and_by_stage():
    games = [
        G(1, 2, "2024", date(2024, 9, 28), 3, 2),                     # before opener
        G(1, 2, "2024", date(2024, 10, 20), 3, 2, stage="Pre-season"),  # stage marker
        G(1, 2, "2024", date(2024, 10, 20), 3, 2),                    # kept
        G(2, 1, "2025", date(2025, 10, 1), 1, 4),                     # before opener
        G(2, 1, "2025", date(2025, 10, 9), 1, 4),                     # kept
    ]
    st = nb.build_stream(games)
    assert len(st.train) == 1 and len(st.test) == 1
    assert st.excluded[("2024", "date")] == 1
    assert st.excluded[("2024", "stage")] == 1
    assert st.excluded[("2025", "date")] == 1


def test_opener_day_is_kept_and_override_moves_the_cut():
    g = G(1, 2, "2024", date(2024, 10, 8), 2, 1)
    assert nb.preseason_reason(g, nb.SEASON_STARTS) is None
    assert nb.preseason_reason(g, {"2024": date(2024, 10, 9)}) == "date"


def test_other_seasons_ignored_and_ties_counted():
    games = [G(1, 2, "2023", date(2023, 11, 1), 3, 2),
             G(1, 2, "2024", date(2024, 11, 1), 2, 2)]
    st = nb.build_stream(games)
    assert not st.train and st.ties == 1


def test_outcome_counts_ot_and_shootout_wins():
    # provider totals include OT/SO: a 4-3 AOT/AP home win is a home win
    assert G(1, 2, "2025", date(2025, 11, 1), 4, 3).home_win == 1
    assert G(1, 2, "2025", date(2025, 11, 1), 3, 4).home_win == 0


# --- baselines ----------------------------------------------------------------

def _stream(train_home_wins, train_n, test_home_wins, test_n):
    d0, d1 = datetime(2024, 11, 1), datetime(2025, 11, 1)
    tr = [G(1, 2, "2024", d0 + timedelta(hours=i), 3 if i < train_home_wins else 1, 2)
          for i in range(train_n)]
    te = [G(1, 2, "2025", d1 + timedelta(hours=i), 3 if i < test_home_wins else 1, 2)
          for i in range(test_n)]
    return nb.build_stream(tr + te)


def test_baselines_use_train_home_rate():
    st = _stream(60, 100, 50, 100)
    r = nb.baselines(st)
    assert r.home_rate == pytest.approx(0.60)                 # frozen from 2024
    assert r.ll_const == pytest.approx(math.log(2))
    exp = -(0.5 * math.log(0.6) + 0.5 * math.log(0.4))        # 2025 is 50/50
    assert r.ll_home == pytest.approx(exp)


def test_missing_season_is_invalid():
    st = nb.build_stream([G(1, 2, "2024", date(2024, 11, 1), 3, 2)])
    assert nb.baselines(st).verdict.startswith("INVALID")


# --- verdict math with stub predictors -------------------------------------------

class Const:
    def __init__(self, p, ratings=None):
        self.p, self._r = p, ratings or {1: 1550.0, 2: 1450.0}
    def predict(self, g): return self.p
    def update(self, g): pass
    def ratings(self): return self._r


class Oracle(Const):
    """Knows the answer with fixed confidence: calibrated by construction."""
    def predict(self, g): return self.p if g.home_win else 1 - self.p


def test_constant_home_rate_model_fails_log_loss_margin():
    st = _stream(110, 200, 110, 200)             # 55% home in both seasons
    r = nb.run_gate(st, Const(0.55))
    assert r.ll_model == pytest.approx(r.ll_home)  # it IS the baseline
    assert not r.crit_ll and r.verdict.startswith("FAIL")


def test_margin_is_inclusive_at_exactly_0_010():
    assert nb.beats_margin(0.680, 0.690)          # exactly 0.010 better: pass
    assert not nb.beats_margin(0.681, 0.690)      # 0.009 better: fail
    assert not nb.beats_margin(0.690, 0.690)      # a tie is a rejection


def test_bands_gate_only_when_n_at_least_100():
    pairs = [(0.65, 1)] * 99                     # 99 obs, badly calibrated
    b = nb.calibration_bands(pairs)[0]
    assert not b["gated"] and b["ok"] is None
    b = nb.calibration_bands(pairs + [(0.65, 1)])[0]
    assert b["gated"] and b["ok"] is False       # realized 100% vs 65%


def test_band_tolerance_is_5pp():
    ok = [(0.60, 1)] * 65 + [(0.60, 0)] * 35     # realized .65, stated .60
    bad = [(0.60, 1)] * 66 + [(0.60, 0)] * 34    # realized .66
    assert nb.calibration_bands(ok)[0]["ok"]
    assert not nb.calibration_bands(bad)[0]["ok"]


def test_rating_spread_outlier_fails():
    st = _stream(110, 200, 110, 200)
    r = nb.run_gate(st, Oracle(0.9, ratings={1: 1850.0, 2: 1500.0}))
    assert r.outliers == [(1, 1850.0)] and not r.crit_spread


class ByTeam(Const):
    """States 0.7 when team 1 is home, 0.3 when team 3 is home."""
    def predict(self, g): return 0.7 if g.home_id == 1 else 0.3


def _calibrated_world():
    d0, d1 = datetime(2024, 11, 1), datetime(2025, 11, 1)
    train = [G(1, 2, "2024", d0 + timedelta(hours=i), 3 if i % 2 else 1, 2) for i in range(200)]
    test = ([G(1, 2, "2025", d1 + timedelta(hours=i), 3 if i < 140 else 1, 2) for i in range(200)]
            + [G(3, 2, "2025", d1 + timedelta(hours=300 + i), 3 if i < 60 else 1, 2) for i in range(200)])
    return nb.build_stream(train + test)


def test_full_pass_path():
    """Sharp AND calibrated (70% bin wins 70%, 30% bin wins 30%) clears all three."""
    r = nb.run_gate(_calibrated_world(), ByTeam(None))
    assert r.home_rate == pytest.approx(0.5)
    assert r.ll_model == pytest.approx(-(0.7 * math.log(0.7) + 0.3 * math.log(0.3)))
    assert r.crit_ll and r.crit_bands and r.crit_spread
    assert r.verdict.startswith("PASS")


def test_sharp_but_uncalibrated_fails_bands():
    # states .62/.38 but is always right: realized 100%/0% in its bands
    r = nb.run_gate(_stream(100, 200, 100, 200), Oracle(0.62))
    assert r.crit_ll and not r.crit_bands and r.verdict == "FAIL — calibration"


def test_report_prints_baselines_only_without_model():
    st = _stream(55, 100, 50, 100)
    lines = []
    nb.report(st, nb.baselines(st), out=lines.append)
    text = "\n".join(lines)
    assert "constant 0.5" in text and "league home rate" in text
    assert "baselines only" in text and "GATE VERDICT" not in text


# --- DB loading ------------------------------------------------------------------

def test_load_games_scope_and_no_writes():
    from sqlalchemy import func, select

    from src.db.database import init_db, session_scope
    from src.db.schema import Base, Competition, Match, MatchStatus, Sport, Team

    init_db()
    with session_scope() as s:
        nhl = Competition(sport=Sport.NHL, code="NHL", name="NHL", area="USA", type="LEAGUE")
        fourn = Competition(sport=Sport.NHL, code="4NF", name="4 Nations", area="World", type="CUP")
        s.add_all([nhl, fourn])
        a, b = Team(sport=Sport.NHL, name="Bruins"), Team(sport=Sport.NHL, name="Leafs")
        s.add_all([a, b])
        s.flush()
        mk = lambda comp, st, hs, as_: Match(sport=Sport.NHL, competition_id=comp.id, season="2025",
                                              utc_date=datetime(2025, 11, 1), status=st,
                                              home_team_id=a.id, away_team_id=b.id,
                                              home_score=hs, away_score=as_)
        s.add_all([mk(nhl, MatchStatus.FINISHED, 4, 3),      # kept
                   mk(nhl, MatchStatus.FINISHED, None, None),  # no score
                   mk(nhl, MatchStatus.SCHEDULED, None, None),
                   mk(fourn, MatchStatus.FINISHED, 2, 1)])     # other competition
    count = lambda: {t.name: s2.execute(select(func.count()).select_from(t)).scalar_one()
                     for t in Base.metadata.sorted_tables}
    with session_scope() as s2:
        before = count()
    games = nb.load_games()
    with session_scope() as s2:
        after = count()
    assert after == before
    assert [(g.home_score, g.away_score) for g in games] == [(4, 3)]
