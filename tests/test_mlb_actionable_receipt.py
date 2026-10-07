"""ARCHITECT 2026-10-07 item 2: the read-only MLB actionable receipt (tier x edge vs the close).
Synthetic rows / throwaway DB only (season "2081" is this file's own)."""
from datetime import datetime, timedelta

import pytest

from src.db.database import init_db, session_scope
from src.db.schema import (Competition, Match, MatchStatus, Odds, OddsSnapshot, Prediction, PredictionOutcome,
                           Result, Sport, Team)
from src.walters import mlb_actionable as MA
from src.web.preview import TIER_LEAN_MAX, TIER_TOSSUP_MAX, classify_tier

SEASON = "2081"
KO = datetime(2081, 9, 1, 23, 5)


# ---------------------------------------------------------------- pure functions

def test_bucket_boundaries_belong_to_the_bucket_above():
    assert MA.edge_bucket(-12.0) == "<4"
    assert MA.edge_bucket(3.999) == "<4"
    assert MA.edge_bucket(4.0) == "4-8"
    assert MA.edge_bucket(7.999) == "4-8"
    assert MA.edge_bucket(8.0) == "8-15"
    assert MA.edge_bucket(14.999) == "8-15"
    assert MA.edge_bucket(15.0) == ">=15"
    assert MA.edge_bucket(40.0) == ">=15"
    # float hygiene: 0.58 - 0.54 is 3.9999999999999947pp in binary floating point
    assert (0.58 - 0.54) * 100 < 4 and MA.edge_bucket((0.58 - 0.54) * 100) == "4-8"


@pytest.mark.parametrize("p", [0.50, 0.5299, TIER_TOSSUP_MAX, 0.55, 0.5999, TIER_LEAN_MAX, 0.65, 0.80])
@pytest.mark.parametrize("hk,ak", [(True, True), (False, True), (True, False)])
def test_tier_is_the_prediction_layers_classify_tier(p, hk, ak):
    fb = {"home_starter_known": hk, "away_starter_known": ak}
    assert MA.tier_of(p, fb) == classify_tier(p, starter_known=hk and ak)
    assert MA.tier_of(p, {}) == classify_tier(p, starter_known=True)      # export default: keys absent = known
    assert MA.tier_of(p, None) == classify_tier(p, starter_known=True)


def test_top_pick_is_home_on_a_tie():
    assert MA.top_pick(0.5, 0.5) == ("HOME", 0.5)
    assert MA.top_pick(0.48, 0.52) == ("AWAY", 0.52)


def test_roi_at_the_close_fair_price():
    assert MA.roi_unit(True, 0.5) == pytest.approx(1.0)
    assert MA.roi_unit(True, 0.25) == pytest.approx(3.0)
    assert MA.roi_unit(False, 0.6) == -1.0
    rows = [{"hit": True, "fair": 0.5, "model_p": 0.6}, {"hit": False, "fair": 0.5, "model_p": 0.6},
            {"hit": True, "fair": 0.25, "model_p": 0.3}, {"hit": False, "fair": 0.8, "model_p": 0.9}]
    c = MA.cell_stats(rows, b=200)
    assert c["n"] == 4 and c["roi"] == pytest.approx((1.0 - 1.0 + 3.0 - 1.0) / 4)
    assert c["hit"] == pytest.approx(0.5) and c["fair_p"] == pytest.approx(0.5125)
    assert c["model_p"] == pytest.approx(0.6) and c["hit_minus_close_pp"] == pytest.approx(-1.25)


def test_bootstrap_is_deterministic_under_the_pinned_seed():
    pairs = [(i % 3 == 0, 0.4 + (i % 7) / 50) for i in range(40)]
    pairs = [(1 if h else 0, f) for h, f in pairs]
    a, b = MA.bootstrap_ci(pairs), MA.bootstrap_ci(pairs)
    assert a == b and a[0] < a[1]
    assert MA.bootstrap_ci(pairs, seed=MA.BOOT_SEED + 1) != a
    assert MA.bootstrap_ci([(1, 0.5)]) is None and MA.bootstrap_ci([]) is None     # n < 2 -> no CI
    rows = [{"hit": bool(h), "fair": f, "model_p": 0.6} for h, f in pairs]
    assert MA.cell_stats(rows) == MA.cell_stats(rows)


# ---------------------------------------------------------------- DB-backed

def _comp(s):
    c = s.query(Competition).filter_by(code="MLB").one_or_none()
    if c is None:
        c = Competition(sport=Sport.MLB, code="MLB", name="MLB", area="US", type="LEAGUE")
        s.add(c)
        s.flush()
    return c


def _game(s, tag, *, stage, p_home, home_won, fair_home=None, fb=None, kalshi=False):
    c = _comp(s)
    h, a = Team(sport=Sport.MLB, name=f"MA {tag} H"), Team(sport=Sport.MLB, name=f"MA {tag} A")
    s.add_all([h, a])
    s.flush()
    m = Match(sport=Sport.MLB, competition_id=c.id, season=SEASON, stage=stage, utc_date=KO,
              status=MatchStatus.FINISHED, home_team_id=h.id, away_team_id=a.id,
              home_score=5 if home_won else 1, away_score=1 if home_won else 5)
    s.add(m)
    s.flush()
    p = Prediction(match_id=m.id, model_version="mlb_test_v2", computed_at=KO - timedelta(hours=3),
                   home_win_prob=p_home, draw_prob=None, away_win_prob=1 - p_home, factor_breakdown=fb or {})
    s.add(p)
    s.flush()
    top_home = p_home >= 1 - p_home
    s.add(PredictionOutcome(prediction_id=p.id, actual_result=Result.HOME if home_won else Result.AWAY,
                            top_pick_hit=(top_home == home_won)))
    if fair_home is not None:      # one complete zero-vig book: de-vig returns fair_home exactly
        for sel, f in (("HOME", fair_home), ("AWAY", 1 - fair_home)):
            s.add(Odds(match_id=m.id, bookmaker="bk1", market="1X2", selection=sel, price_decimal=1 / f,
                       captured_at=KO - timedelta(minutes=30)))
    if kalshi:
        s.add(OddsSnapshot(match_id=m.id, market="ML", selection="HOME", devig_prob=0.5, n_books=1,
                           captured_at=KO - timedelta(hours=1), source="kalshi", yes_bid=0.49, yes_ask=0.50))
    s.flush()
    return m


def _seed():
    init_db()
    with session_scope() as s:
        if s.query(Match).filter_by(season=SEASON).count():
            return
        _game(s, "lean4", stage="R", p_home=0.58, home_won=True, fair_home=0.54)          # lean, edge 4.0 -> 4-8
        _game(s, "toss", stage="R", p_home=0.48, home_won=True, fair_home=0.50)           # AWAY 0.52 toss-up, edge 2
        _game(s, "cap", stage="R", p_home=0.65, home_won=False, fair_home=0.50,
              fb={"home_starter_known": False, "away_starter_known": True})              # capped lean, edge 15
        _game(s, "noclose", stage="R", p_home=0.60, home_won=True)                        # no close: excluded
        _game(s, "kalshi", stage="R", p_home=0.60, home_won=True, kalshi=True)            # kalshi_only: excluded
        _game(s, "post", stage="D", p_home=0.70, home_won=True, fair_home=0.62)           # postseason strong, edge 8
        _game(s, "nostage", stage=None, p_home=0.62, home_won=True, fair_home=0.60)       # stage unknown


def _rows():
    _seed()
    with session_scope() as s:
        return MA.collect(s, season=SEASON)


def test_collect_tiers_edges_and_exclusions():
    rows = _rows()
    assert len(rows) == 7
    by = {r["match_id"]: r for r in rows}
    inc = [r for r in rows if "excluded" not in r]
    exc = [r for r in rows if "excluded" in r]
    assert len(inc) == 5 and len(exc) == 2
    assert sorted(r["excluded"] for r in exc) == [
        "close is not a book close (reference=kalshi_only)",
        "no close (no pre-first-pitch capture, or unpriced)"]
    t = {(r["tier"], r["bucket"], r["stage"], r["side"]) for r in inc}
    assert ("lean", "4-8", "regular", "HOME") in t
    assert ("toss-up", "<4", "regular", "AWAY") in t
    assert ("lean", ">=15", "regular", "HOME") in t           # 0.65 capped by the unknown starter
    assert ("strong", "8-15", "postseason", "HOME") in t
    assert ("strong", "<4", "unknown", "HOME") in t
    for r in inc:                                             # actionable is the prediction layer's flag
        assert r["actionable"] == (r["tier"] != "toss-up")
        assert r["model_version"] == "mlb_test_v2"
    assert by


def test_receipt_counts_and_postseason_split():
    res = MA.receipt(_rows(), b=500)
    assert res["graded"] == 7 and res["included"] == 5 and res["excluded"] == 2 and res["capped"] == 1
    assert res["tables"]["regular"]["n"] == 3
    assert res["tables"]["postseason"]["n"] == 1
    assert res["tables"]["unknown"]["n"] == 1
    cells = {(t, b): c for t, b, c in res["tables"]["postseason"]["cells"]}
    c = cells[("strong", "8-15")]
    assert c["n"] == 1 and c["ci95"] is None and c["hit"] == 1.0
    assert c["roi"] == pytest.approx(1 / 0.62 - 1)
    assert c["hit_minus_close_pp"] == pytest.approx(38.0)
    assert cells[("all", "all")]["n"] == 1
    reg = {(t, b): c for t, b, c in res["tables"]["regular"]["cells"]}
    assert reg[("lean", "all")]["n"] == 2 and reg[("toss-up", "<4")]["n"] == 1
    assert reg[("all", "all")]["ci95"] is not None


def test_cli_out_writes_markdown_stating_the_edge_is_vs_the_close(tmp_path):
    from click.testing import CliRunner

    from cli import cli
    _seed()
    out = tmp_path / "receipts" / "mlb-actionable.md"
    res = CliRunner().invoke(cli, ["mlb-actionable-receipt", "--season", SEASON, "--out", str(out)])
    assert res.exit_code == 0, res.output
    txt = out.read_text()
    assert "THE EDGE IS AGAINST THE CLOSE, NOT THE DESK'S T-60 REFERENCE" in txt
    assert "Prediction history exists only from 2026-10-06" in txt
    assert "EXCLUDED: 2" in txt and "## Postseason" in txt and "## Regular season" in txt
    assert f"seed {MA.BOOT_SEED}" in txt
    again = CliRunner().invoke(cli, ["mlb-actionable-receipt", "--season", SEASON, "--out", str(out)])
    assert again.exit_code == 2 and "never overwritten" in again.output


def test_cli_refuses_data_dir():
    from click.testing import CliRunner

    from cli import cli
    from src.walters.unl_ladders import data_dir
    res = CliRunner().invoke(cli, ["mlb-actionable-receipt", "--season", SEASON,
                                   "--out", str(data_dir() / "x.md")])
    assert res.exit_code == 2 and "REFUSED" in res.output
    assert not (data_dir() / "x.md").exists()
