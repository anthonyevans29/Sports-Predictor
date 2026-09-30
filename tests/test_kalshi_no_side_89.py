"""#89 (architect 2026-09-30): the derived NO-side exec cost for AWAY picks.
On a TWO-WAY market the away side is the NO side of the HOME contract:
NO ask = 1 - home YES bid, NO bid = 1 - home YES ask, the same fee formula per
fill (#88 nearest, N = 10) and the same maker rules mirrored. On a three-way
1X2 market (soccer) NO on HOME is draw-or-away, so the away fields stay null."""
import json
from datetime import datetime, timedelta

from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, OddsSnapshot, Prediction, Sport, Team
from src.walters import venue
from src.walters.export import export_fixtures, export_predictions

NOW = datetime(2034, 5, 6, 12, 0)
AWAY_KEYS = ("away_bid", "away_ask", "exec_cost_taker_away", "exec_cost_maker_away")


def test_two_way_away_costs_mirror_the_home_rules():
    e = venue.kalshi_exec(0.55, 0.58, "NFL", two_way=True)
    assert (e["away_ask"], e["away_bid"]) == (0.45, 0.42)          # 1 - bid, 1 - ask
    # taker: 0.45 + round(10 x 0.07 x 1 x 0.45 x 0.55 x 100 = 17.3c -> 17c) / 10
    assert e["exec_cost_taker_away"] == 0.467
    # maker: join 0.43 + round(10 x 0.0175 x 0.25 x 0.43 x 0.57 x 100 = 1.07c -> 1c) / 10
    assert e["exec_cost_maker_away"] == 0.431
    # the home block is unchanged by the away block
    assert (e["exec_cost_taker"], e["exec_cost_maker"], e["kalshi_exec_cost"]) == (0.597, 0.561, 0.597)
    # MLB pre-live M = 0.5 applies to the NO side too
    m = venue.kalshi_exec(0.54, 0.56, "MLB", two_way=True)
    assert (m["away_ask"], m["away_bid"], m["exec_cost_taker_away"], m["exec_cost_maker_away"]) == (
        0.46, 0.44, 0.469, 0.452)


def test_away_maker_null_cases():
    one = venue.kalshi_exec(0.57, 0.58, "NFL", two_way=True)        # 1c spread: NO 0.42 / 0.43
    assert one["exec_cost_maker_away"] is None and one["exec_cost_taker_away"] == 0.447
    no_ask = venue.kalshi_exec(0.55, None, "NFL", two_way=True)     # no home ask -> no NO bid
    assert no_ask["away_bid"] is None and no_ask["exec_cost_maker_away"] is None
    assert no_ask["exec_cost_taker_away"] == 0.467
    no_bid = venue.kalshi_exec(None, 0.58, "NFL", two_way=True)     # no home bid -> no NO ask
    assert no_bid["away_ask"] is None and no_bid["exec_cost_taker_away"] is None
    assert no_bid["exec_cost_maker_away"] == 0.431                  # NO bid 0.42 joins at 0.43
    unk = venue.kalshi_exec(0.50, 0.55, "UNKNOWN", two_way=True)    # unlisted: maker M not assumed
    assert unk["exec_cost_maker_away"] is None and unk["exec_cost_taker_away"] == 0.518


def test_three_way_and_unstated_markets_have_no_away_cost():
    for e in (venue.kalshi_exec(0.47, 0.49, "PL"),                  # default: two_way not stated
              venue.kalshi_exec(0.47, 0.49, "PL", two_way=False)):  # soccer 1X2
        assert all(e[k] is None for k in AWAY_KEYS)
        assert e["exec_cost_taker"] == 0.507                        # the home contract is unchanged
    assert set(AWAY_KEYS) <= set(venue.KALSHI_EXEC_NULL)
    assert all(venue.KALSHI_EXEC_NULL[k] is None for k in AWAY_KEYS)


def _game(s, sport, code, tag, legs, pred=None):
    comp = s.execute(select(Competition).where(Competition.sport == sport,
                                               Competition.code == code)).scalar_one_or_none()
    if comp is None:
        comp = Competition(sport=sport, code=code, name=code, area="X", type="LEAGUE")
        s.add(comp)
        s.flush()
    h = Team(sport=sport, name=f"N89 {tag} H", external_ids={"n89": f"{tag}h"})
    a = Team(sport=sport, name=f"N89 {tag} A", external_ids={"n89": f"{tag}a"})
    s.add_all([h, a])
    s.flush()
    m = Match(sport=sport, competition_id=comp.id, season="2034", utc_date=NOW + timedelta(hours=5),
              status=MatchStatus.SCHEDULED, home_team_id=h.id, away_team_id=a.id)
    s.add(m)
    s.flush()
    if pred:
        s.add(Prediction(match_id=m.id, model_version="t", home_win_prob=pred[0],
                         draw_prob=pred[1], away_win_prob=pred[2]))
    for sel, p, bid, ask in legs:
        s.add(OddsSnapshot(match_id=m.id, market="ML", selection=sel, devig_prob=p, n_books=1,
                           captured_at=NOW - timedelta(hours=1), source="kalshi", yes_bid=bid, yes_ask=ask))
    return m.id


def test_fixtures_export_two_way_carries_away_soccer_does_not(tmp_path, monkeypatch):
    monkeypatch.setitem(venue.KALSHI_SERIES_BY_COMPETITION, "N89NHL", "KXNHLGAME")
    init_db()
    with session_scope() as s:
        nhl = _game(s, Sport.NHL, "N89NHL", "nhl", [("HOME", 0.565, 0.55, 0.58), ("AWAY", 0.435, 0.42, 0.45)])
        soc = _game(s, Sport.SOCCER, "N89SOC", "soc",
                    [("HOME", 0.48, 0.47, 0.49), ("DRAW", 0.27, 0.26, 0.28), ("AWAY", 0.25, 0.24, 0.26)])
    fx = {r["match_id"]: r for r in json.loads(open(export_fixtures(
        "N89NHL", start="2034-05-06", end="2034-05-07", out_dir=str(tmp_path))).read())["fixtures"]}
    r = fx[nhl]
    assert (r["away_ask"], r["away_bid"], r["exec_cost_taker_away"], r["exec_cost_maker_away"]) == (
        0.45, 0.42, 0.467, 0.431)
    sx = {r["match_id"]: r for r in json.loads(open(export_fixtures(
        "N89SOC", start="2034-05-06", end="2034-05-07", out_dir=str(tmp_path))).read())["fixtures"]}
    assert sx[soc]["input_quality"]["kalshi"] == "two_sided"
    assert sx[soc]["exec_cost_taker"] is not None                    # home contract still priced
    assert all(sx[soc][k] is None for k in AWAY_KEYS)                # NO on HOME = draw-or-away


def test_prediction_export_mlb_carries_away_soccer_does_not(monkeypatch):
    monkeypatch.setitem(venue.KALSHI_SERIES_BY_COMPETITION, "N89MLB", "KXMLBGAME")
    init_db()
    with session_scope() as s:
        mlb = _game(s, Sport.MLB, "N89MLB", "mlb", [("HOME", 0.55, 0.54, 0.56), ("AWAY", 0.45, 0.44, 0.46)],
                    pred=(0.42, None, 0.58))
        soc = _game(s, Sport.SOCCER, "N89PS", "ps",
                    [("HOME", 0.48, 0.47, 0.49), ("DRAW", 0.27, 0.26, 0.28), ("AWAY", 0.25, 0.24, 0.26)],
                    pred=(0.25, 0.25, 0.5))
    lo, hi = NOW - timedelta(days=1), NOW + timedelta(days=1)
    m = {r["match_id"]: r for r in json.loads(export_predictions(
        sport=Sport.MLB, start_date=lo, end_date=hi, competition_code="N89MLB"))["predictions"]}[mlb]
    assert (m["away_ask"], m["away_bid"], m["exec_cost_taker_away"], m["exec_cost_maker_away"]) == (
        0.46, 0.44, 0.469, 0.452)
    sc = {r["match_id"]: r for r in json.loads(export_predictions(
        sport=Sport.SOCCER, start_date=lo, end_date=hi, competition_code="N89PS"))["predictions"]}[soc]
    assert sc["market"]["kalshi"]["normalized"] is True and sc["exec_cost_taker"] == 0.507
    assert all(sc[k] is None for k in AWAY_KEYS)
