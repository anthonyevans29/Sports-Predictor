"""#93 RESOLVED (architect ruling 2026-09-30): the export's single
kalshi_exec_cost becomes exec_cost_taker (ask + 0.07*M*P(1-P)) and
exec_cost_maker ((bid + 1c) + 0.0175*M*P(1-P)). Game series: taker M=1, maker
M=0.25; MLB pre-live M=0.5 for both. kalshi_exec_cost stays as the taker alias.
Rounding is unchanged (per-contract cent ceiling, pending the ruling on #88)."""
import json
from datetime import datetime, timedelta

from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, OddsSnapshot, Sport, Team
from src.walters import venue
from src.walters.export import export_fixtures

NOW = datetime(2033, 4, 5, 12, 0)


def test_ruled_multipliers_per_series():
    assert venue.KALSHI_FEE_M["KXMLBGAME"] == (0.5, 0.5)
    for s in ("KXNFLGAME", "KXNHLGAME", "KXNCAAFGAME", "KXEPLGAME"):
        assert venue.KALSHI_FEE_M[s] == (1.0, 0.25)
    assert venue.KALSHI_SERIES_BY_COMPETITION == {
        "NFL": "KXNFLGAME", "NHL": "KXNHLGAME", "NCAA": "KXNCAAFGAME", "PL": "KXEPLGAME", "MLB": "KXMLBGAME"}


def test_fee_formula_takes_m_and_rate():
    # #88: one NEAREST-cent rounding per fill of N = 10 (re-fit #134, 98.9%)
    assert venue.kalshi_fee(0.50) == 0.018                                  # 17.5c -> 18c / 10
    assert venue.kalshi_fee(0.56, 0.5) == 0.009                             # 8.6c -> 9c / 10
    assert venue.kalshi_fee(0.56, 0.25, venue.KALSHI_MAKER_RATE) == 0.001   # 1.08c -> 1c / 10
    assert venue.kalshi_fee(0.56, 0.25, venue.KALSHI_MAKER_RATE, n=1) == 0.0  # 0.108c -> 0c on a 1-lot


def test_exec_nfl_taker_and_maker():
    e = venue.kalshi_exec(0.55, 0.58, "NFL")
    assert (e["exec_cost_taker"], e["exec_cost_maker"]) == (0.597, 0.561)  # 0.58+1.7c ; join 0.56 + 0.1c
    assert e["kalshi_exec_cost"] == e["exec_cost_taker"]                    # deprecated alias
    assert (e["fee_series"], e["fee_m_taker"], e["fee_m_maker"]) == ("KXNFLGAME", 1.0, 0.25)


def test_exec_mlb_pre_live_half_multiplier():
    e = venue.kalshi_exec(0.54, 0.56, "MLB")
    assert (e["exec_cost_taker"], e["exec_cost_maker"]) == (0.569, 0.552)  # M=0.5: 0.56+0.9c ; 0.55+0.2c
    # the same quotes at M=1
    assert venue.kalshi_exec(0.54, 0.56, "NFL")["exec_cost_taker"] == 0.577


def test_no_maker_price_cases():
    assert venue.kalshi_exec(0.57, 0.58, "NFL")["exec_cost_maker"] is None   # 1c spread: joining = taking
    assert venue.kalshi_exec(None, 0.58, "NFL")["exec_cost_maker"] is None   # no bid
    u = venue.kalshi_exec(0.50, 0.55, "UNKNOWN")                             # unlisted: maker M not assumed
    assert u["exec_cost_maker"] is None and u["exec_cost_taker"] == 0.567 and u["fee_m_taker"] == 1.0
    n = venue.kalshi_exec(0.50, None, "NFL")                                 # bid only
    assert n["exec_cost_taker"] is None and n["exec_cost_maker"] == 0.511
    assert set(venue.KALSHI_EXEC_NULL) <= set(u)                             # null block: same cost keys


def _game(s, sport, code, tag, legs):
    comp = s.execute(select(Competition).where(Competition.code == code)).scalars().first()
    if comp is None:
        comp = Competition(sport=sport, code=code, name=code, area="X", type="LEAGUE")
        s.add(comp)
        s.flush()
    h = Team(sport=sport, name=f"M93 {tag} H", external_ids={"m93": f"{tag}h"})
    a = Team(sport=sport, name=f"M93 {tag} A", external_ids={"m93": f"{tag}a"})
    s.add_all([h, a])
    s.flush()
    m = Match(sport=sport, competition_id=comp.id, season="2033", utc_date=NOW + timedelta(hours=5),
              status=MatchStatus.SCHEDULED, home_team_id=h.id, away_team_id=a.id)
    s.add(m)
    s.flush()
    for sel, p, bid, ask in legs:
        s.add(OddsSnapshot(match_id=m.id, market="ML", selection=sel, devig_prob=p, n_books=1,
                           captured_at=NOW - timedelta(hours=1), source="kalshi", yes_bid=bid, yes_ask=ask))
    return m.id


def test_fixtures_export_carries_both_costs_per_series(tmp_path, monkeypatch):
    # a private code mapped to the NHL series: other tests own the real "NHL" row
    monkeypatch.setitem(venue.KALSHI_SERIES_BY_COMPETITION, "M93NHL", "KXNHLGAME")
    init_db()
    with session_scope() as s:
        nhl = _game(s, Sport.NHL, "M93NHL", "nhl", [("HOME", 0.565, 0.55, 0.58), ("AWAY", 0.435, 0.42, 0.45)])
        tight = _game(s, Sport.NHL, "M93NHL", "tight", [("HOME", 0.575, 0.57, 0.58), ("AWAY", 0.425, 0.42, 0.43)])
    fx = {r["match_id"]: r for r in json.loads(open(export_fixtures(
        "M93NHL", start="2033-04-05", end="2033-04-06", out_dir=str(tmp_path))).read())["fixtures"]}
    r = fx[nhl]
    assert (r["kalshi_bid"], r["kalshi_ask"], r["exec_cost_taker"], r["exec_cost_maker"],
            r["kalshi_exec_cost"]) == (0.55, 0.58, 0.597, 0.561, 0.597)
    assert fx[tight]["exec_cost_maker"] is None and fx[tight]["exec_cost_taker"] == 0.597


def test_mlb_prediction_export_prices_at_the_pre_live_multiplier(monkeypatch):
    from src.db.schema import Prediction
    from src.walters.export import export_predictions
    monkeypatch.setitem(venue.KALSHI_SERIES_BY_COMPETITION, "M93MLB", "KXMLBGAME")
    init_db()
    with session_scope() as s:
        mid = _game(s, Sport.MLB, "M93MLB", "mlb", [("HOME", 0.55, 0.54, 0.56), ("AWAY", 0.45, 0.44, 0.46)])
        s.add(Prediction(match_id=mid, model_version="t", home_win_prob=0.58, draw_prob=None, away_win_prob=0.42))
    lo, hi = NOW - timedelta(days=1), NOW + timedelta(days=1)
    rows = {r["match_id"]: r for r in json.loads(export_predictions(
        sport=Sport.MLB, start_date=lo, end_date=hi, competition_code="M93MLB"))["predictions"]}
    r = rows[mid]
    assert (r["exec_cost_taker"], r["exec_cost_maker"], r["fee_series"], r["fee_m_taker"]) == (0.569, 0.552, "KXMLBGAME", 0.5)
