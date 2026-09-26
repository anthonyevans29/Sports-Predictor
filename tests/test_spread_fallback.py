"""Spread -> win-prob fallback (architect spec 2026-09-26): math, pairing,
export labelling, and the read-only acceptance receipt."""
import json
import math
from datetime import datetime, timedelta
from types import SimpleNamespace as NS

import pytest
from click.testing import CliRunner
from sqlalchemy import func, select

from src.db.database import get_engine, init_db, session_scope
from src.db.schema import (Base, Competition, Match, MatchStatus, Odds, Prediction, Sport,
                           Team)
from src.walters import spread_fallback as fb

KICK = datetime.utcnow().replace(microsecond=0) + timedelta(days=2)


# ---------------------------------------------------------------- pure math

def test_frozen_constants():
    assert fb.SIGMA_NFL == 13.45 and fb.SIGMA_NCAA == 16.5
    assert fb.ACCEPTANCE_MEAN_ABS_PP == 3.0
    assert fb.sigma_for("nfl") == 13.45 and fb.sigma_for("NCAA") == 16.5
    assert fb.sigma_for("NHL") is None and fb.sigma_for("PL") is None and fb.sigma_for(None) is None


def test_pickem_is_half():
    assert fb.spread_to_home_prob(0.0, fb.SIGMA_NFL) == pytest.approx(0.5, abs=1e-12)


def test_symmetry():
    for s in (1.5, 3.0, 7.0, 13.5, 24.0):
        for sig in (fb.SIGMA_NFL, fb.SIGMA_NCAA):
            assert (fb.spread_to_home_prob(-s, sig) + fb.spread_to_home_prob(s, sig)
                    == pytest.approx(1.0, abs=1e-12))


def test_known_value_and_sign():
    # home -7 (home favoured by 7) under sigma 13.45 -> Phi(7/13.45) ~ 0.6986
    p = fb.spread_to_home_prob(-7.0, 13.45)
    assert p == pytest.approx(0.5 * (1 + math.erf((7 / 13.45) / math.sqrt(2))), abs=1e-12)
    assert p == pytest.approx(0.6986, abs=5e-4)
    assert fb.spread_to_home_prob(+7.0, 13.45) < 0.5          # home underdog
    # wider sigma pulls toward 0.5
    assert 0.5 < fb.spread_to_home_prob(-7.0, 16.5) < p


def test_sigma_must_be_positive():
    with pytest.raises(ValueError):
        fb.spread_to_home_prob(-3, 0)


def _o(book, sel, line, price):
    return NS(bookmaker=book, selection=sel, line=line, price_decimal=price,
              market="SPREADS", captured_at=None)


def test_book_main_line_picks_balanced_pair_over_alternates():
    rows = [_o("A", "HOME", -3.5, 1.91), _o("A", "AWAY", 3.5, 1.91),      # main
            _o("A", "HOME", -7.5, 3.10), _o("A", "AWAY", 7.5, 1.35),      # alternate
            _o("A", "HOME", -1.5, 1.55), _o("A", "AWAY", 1.5, 2.45)]      # alternate
    assert fb.book_home_line(rows) == -3.5
    # one-sided fallbacks
    assert fb.book_home_line([_o("B", "HOME", -2.5, 1.9)]) == -2.5
    assert fb.book_home_line([_o("B", "AWAY", 4.5, 1.9)]) == -4.5
    assert fb.book_home_line([_o("B", "HOME", None, 1.9)]) is None


def test_consensus_is_median_across_books():
    rows = [_o("A", "HOME", -3.0, 1.9), _o("A", "AWAY", 3.0, 1.9),
            _o("B", "HOME", -3.5, 1.9), _o("B", "AWAY", 3.5, 1.9),
            _o("C", "HOME", -6.5, 1.9), _o("C", "AWAY", 6.5, 1.9)]
    assert fb.consensus_home_spread(rows) == (-3.5, 3)
    assert fb.consensus_home_spread(rows[:4]) == (-3.25, 2)
    assert fb.consensus_home_spread([]) is None


def test_derive_block_labelled_and_scoped():
    rows = [_o("A", "HOME", -7.0, 1.9), _o("A", "AWAY", 7.0, 1.9)]
    blk = fb.derive_spread_market(rows, "NFL")
    assert blk["fair_source"] == "spread_derived" and blk["spread_sigma"] == 13.45
    assert blk["consensus_home_spread"] == -7.0 and blk["bookmaker_count"] == 1
    assert blk["fair_prob"]["HOME"] == pytest.approx(0.6986, abs=1e-4)
    assert blk["fair_prob"]["HOME"] + blk["fair_prob"]["AWAY"] == pytest.approx(1.0, abs=1e-4)
    assert fb.derive_spread_market(rows, "NHL") is None       # out of family
    assert fb.derive_spread_market([], "NFL") is None


# ---------------------------------------------------------- DB-backed paths

def _counts():
    with session_scope() as s:
        return {t.name: s.execute(select(func.count()).select_from(t)).scalar_one()
                for t in Base.metadata.sorted_tables}


def _ml(s, mid, book, h, a, cap):
    s.add(Odds(match_id=mid, source="t", bookmaker=book, market="1X2", selection="HOME",
               price_decimal=h, captured_at=cap))
    s.add(Odds(match_id=mid, source="t", bookmaker=book, market="1X2", selection="AWAY",
               price_decimal=a, captured_at=cap))


def _sp(s, mid, book, home_line, cap, hp=1.91, ap=1.91):
    s.add(Odds(match_id=mid, source="t", bookmaker=book, market="SPREADS", selection="HOME",
               line=home_line, price_decimal=hp, captured_at=cap))
    s.add(Odds(match_id=mid, source="t", bookmaker=book, market="SPREADS", selection="AWAY",
               line=-home_line, price_decimal=ap, captured_at=cap))


@pytest.fixture(scope="module")
def af():
    init_db()
    pre = KICK - timedelta(hours=3)
    with session_scope() as s:
        # get-or-create: other test modules share this throwaway DB and may
        # already hold the NFL / NCAA competitions (unique on sport+code)
        def comp(code, name):
            c = s.execute(select(Competition).where(Competition.sport == Sport.NFL,
                                                    Competition.code == code)).scalar_one_or_none()
            if c is None:
                c = Competition(sport=Sport.NFL, code=code, name=name, area="USA", type="LEAGUE")
                s.add(c)
            return c
        nfl = comp("NFL", "NFL")
        ncaa = comp("NCAA", "NCAA Football")
        t = [Team(sport=Sport.NFL, name=n) for n in
             ("Chiefs", "Bills", "Eagles", "Cowboys", "Bama", "Auburn", "Jets", "Pats")]
        s.add_all(t)
        s.flush()

        def mk(comp, h, a, when):
            m = Match(sport=Sport.NFL, competition_id=comp.id, season="2026", utc_date=when,
                      status=MatchStatus.SCHEDULED, home_team_id=t[h].id, away_team_id=t[a].id)
            s.add(m)
            s.flush()
            return m

        both = mk(nfl, 0, 1, KICK)                     # 1X2 + spreads
        sp_only = mk(nfl, 2, 3, KICK + timedelta(hours=3))   # spreads only (NFL)
        ncaa_sp = mk(ncaa, 4, 5, KICK + timedelta(hours=1))  # spreads only (NCAA)
        none_ = mk(nfl, 6, 7, KICK + timedelta(hours=5))     # no market
        # both: ML ~ home 0.70 fair; spread -7 -> 0.6986
        _ml(s, both.id, "A", 1.40, 3.10, pre)
        _ml(s, both.id, "B", 1.42, 3.00, pre)
        _sp(s, both.id, "A", -7.0, pre)
        _sp(s, both.id, "B", -7.0, pre)
        _sp(s, both.id, "A", -10.5, pre, hp=2.6, ap=1.5)          # alternate line
        _sp(s, both.id, "B", 14.0, KICK + timedelta(minutes=20))  # in-game: excluded
        _sp(s, sp_only.id, "A", 3.0, pre)
        _sp(s, sp_only.id, "B", 3.5, pre)
        _sp(s, sp_only.id, "C", 2.5, pre)
        _sp(s, ncaa_sp.id, "A", -10.0, pre)
        for m, p in ((both, 0.62), (sp_only, 0.80), (none_, 0.55)):
            s.add(Prediction(match_id=m.id, model_version="nfl_elo_v1", home_win_prob=p,
                             away_win_prob=1 - p, draw_prob=None))
        ids = {"both": both.id, "sp_only": sp_only.id, "ncaa": ncaa_sp.id, "none": none_.id}
    yield ids
    Base.metadata.drop_all(get_engine())


def test_fixtures_export_labels_source(af, tmp_path):
    from src.walters.export import export_fixtures
    before = _counts()
    rc = {}
    doc = json.loads(open(export_fixtures("NFL", out_dir=str(tmp_path), receipts=rc)).read())
    assert _counts() == before                                   # read-only
    rows = {r["match_id"]: r for r in doc["fixtures"]}
    assert rows[af["both"]]["market"]["fair_source"] == "1X2"
    assert "consensus_home_spread" not in rows[af["both"]]["market"]
    d = rows[af["sp_only"]]["market"]
    assert d["fair_source"] == "spread_derived" and d["consensus_home_spread"] == 3.0
    assert d["spread_sigma"] == 13.45 and d["bookmaker_count"] == 3
    assert d["fair_prob"]["HOME"] == pytest.approx(fb.spread_to_home_prob(3.0, 13.45), abs=1e-4)
    assert rows[af["none"]]["market"] is None                    # no market stays null
    assert rc["with_books"] == 1 and rc["with_spread_derived"] == 1

    doc = json.loads(open(export_fixtures("NCAA", out_dir=str(tmp_path))).read())
    # by id: other modules sharing the throwaway DB may add NCAA fixtures
    n = {r["match_id"]: r for r in doc["fixtures"]}[af["ncaa"]]["market"]
    assert n["fair_source"] == "spread_derived" and n["spread_sigma"] == 16.5
    assert n["fair_prob"]["HOME"] == pytest.approx(fb.spread_to_home_prob(-10.0, 16.5), abs=1e-4)


def test_nfl_predictions_export_fallback_does_not_touch_quarantine(af, tmp_path):
    from src.walters.nfl_predict import export_nfl_predictions
    doc = json.loads(open(export_nfl_predictions(out_dir=str(tmp_path))).read())
    rows = {r["match_id"]: r for r in doc["predictions"]}
    b = rows[af["both"]]
    assert b["market"]["fair_source"] == "1X2" and b["market_divergence_pp"] is not None
    sp = rows[af["sp_only"]]
    assert sp["market"]["fair_source"] == "spread_derived"
    # model 0.80 vs derived ~0.41 would be a ~39pp divergence — the quarantine
    # contract stays on the 1X2 consensus only, so no divergence/quarantine here.
    assert sp["market_divergence_pp"] is None and sp["quarantine"] is False
    assert rows[af["none"]]["market"] is None


def test_receipt_check_and_cli(af):
    before = _counts()
    r = fb.spread_fallback_check("NFL")
    assert _counts() == before                                   # read-only
    assert r["n"] == 1 and r["rows"][0]["match_id"] == af["both"]
    row = r["rows"][0]
    assert row["spread"] == -7.0 and row["spread_books"] == 2    # alt + in-game ignored
    ih = (1 / 1.40 + 1 / 1.42) / 2
    ia = (1 / 3.10 + 1 / 3.00) / 2
    assert row["ml_fair_home"] == pytest.approx(ih / (ih + ia), abs=1e-9)
    assert r["mean_abs_pp"] == pytest.approx(abs(row["derived_home"] - row["ml_fair_home"]) * 100)
    assert r["pass"] is (r["mean_abs_pp"] <= 3.0)
    assert fb.spread_fallback_check("NCAA")["n"] == 0            # spreads only: not in receipt
    with pytest.raises(ValueError):
        fb.spread_fallback_check("NHL")

    from cli import cli
    out = CliRunner().invoke(cli, ["spread-fallback-check", "--competition", "NFL"]).output
    assert "Bills @ Chiefs" in out and "n = 1 games" in out
    assert "VERDICT: PASS" in out or "VERDICT: FAIL" in out
    out = CliRunner().invoke(cli, ["spread-fallback-check", "--competition", "NCAA"]).output
    assert "NO DATA, verdict withheld" in out
