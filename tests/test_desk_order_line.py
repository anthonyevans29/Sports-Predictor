"""ORDER LINE (ARCHITECT 2026-10-04): every Desk PLAY / LADDER / VENUE row and every parlay leg carries the
copy-exact Kalshi order — market ticker, side, limit per doctrine (join bid; the ask on a 1c spread), contract
count at the declared unit size (SP_UNIT_USD, default 10 contracts per 1u). The ticker comes from the stored
snapshot (sync-kalshi-*), through the export's kalshi_legs. No policy change."""
from datetime import timedelta

from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, OddsSnapshot, Sport, Team
from src.walters import desk_policy as dp
from src.walters.venue import kalshi_legs, latest_kalshi_by_selection

LEGS2 = {"HOME": {"ticker": "KXNFLGAME-26OCT05BUFKC-KC", "bid": 0.55, "ask": 0.58},
         "AWAY": {"ticker": "KXNFLGAME-26OCT05BUFKC-BUF", "bid": 0.41, "ask": 0.44}}


def R(legs, three_way=False):
    return {"src": {"kalshi_legs": legs}, "threeWay": three_way}


def test_straight_yes_joins_the_bid_and_counts_ten_per_unit(monkeypatch):
    monkeypatch.delenv("SP_UNIT_USD", raising=False)
    o = dp.order_line(R(LEGS2), "HOME", 0.5)
    assert o["text"] == "BUY YES KXNFLGAME-26OCT05BUFKC-KC @ 0.55 × 5" and o["limit_basis"] == "join bid"
    assert o["unit"] == "1u = 10 contracts (SP_UNIT_USD unset)" and o["why"] is None
    assert dp.order_line(R(LEGS2), "AWAY", 1.0)["text"] == "BUY YES KXNFLGAME-26OCT05BUFKC-BUF @ 0.41 × 10"


def test_one_cent_spread_takes_the_ask():
    legs = {"HOME": {"ticker": "T-H", "bid": 0.55, "ask": 0.56}}
    o = dp.order_line(R(legs), "HOME", 1.0)
    assert o["limit"] == 0.56 and o["limit_basis"].startswith("ask (1c spread")


def test_unit_size_in_dollars(monkeypatch):
    monkeypatch.setenv("SP_UNIT_USD", "25")
    o = dp.order_line(R(LEGS2), "HOME", 0.5)                          # 0.5 x $25 / 0.55 = 22.7 -> 22
    assert o["contracts"] == 22 and o["unit"] == "1u = $25" and o["text"].endswith("× 22")
    monkeypatch.setenv("SP_UNIT_USD", "1")
    o = dp.order_line(R(LEGS2), "HOME", 0.25)                         # 0.25 x $1 / 0.55 < 1 contract
    assert o["text"] is None and "under one contract" in o["why"]


def test_ladder_is_no_on_home_with_mirrored_prices_and_draw_ladder_refused():
    legs = {"HOME": {"ticker": "KXEPLGAME-X-ARS", "bid": 0.47, "ask": 0.50},
            "DRAW": {"ticker": "KXEPLGAME-X-TIE", "bid": 0.25, "ask": 0.27},
            "AWAY": {"ticker": "KXEPLGAME-X-CHE", "bid": 0.26, "ask": 0.28}}
    o = dp.order_line(R(legs, three_way=True), "AWAY", 0.5, ladder=True)   # X2 = NOT HOME: NO bid = 1 - 0.50
    assert o["text"] == "BUY NO KXEPLGAME-X-ARS @ 0.50 × 5" and o["side"] == "NO"
    d = dp.order_line(R(legs, three_way=True), "DRAW", 0.5, ladder=True)
    assert d["text"] is None and "write it by hand" in d["why"]
    assert dp.order_line(R(legs, three_way=True), "DRAW", 0.5)["text"] == "BUY YES KXEPLGAME-X-TIE @ 0.25 × 5"


def test_two_way_fallback_no_on_opponent_but_never_on_a_three_way_board():
    only_home = {"HOME": {"ticker": "T-H", "bid": 0.55, "ask": 0.58}}
    o = dp.order_line(R(only_home), "AWAY", 1.0)                      # NO on HOME: bid = 1 - 0.58 = 0.42
    assert o["text"] == "BUY NO T-H @ 0.42 × 10"
    t3 = dp.order_line(R(only_home, three_way=True), "AWAY", 1.0)     # NO on HOME is draw-or-away there
    assert t3["text"] is None and "no Kalshi ticker on file for the AWAY leg" in t3["why"]


def test_no_bid_no_ticker_and_nothing_staked():
    assert "no bid to join" in dp.order_line(R({"HOME": {"ticker": "T", "bid": None, "ask": 0.6}}), "HOME", 1)["why"]
    assert "no Kalshi ticker" in dp.order_line(R({"HOME": {"ticker": None, "bid": 0.5, "ask": 0.52}}), "HOME", 1)["why"]
    assert dp.order_line(R(LEGS2), "HOME", 0) is None and dp.order_line(R(LEGS2), None, 1) is None


def test_desk_block_and_parlay_legs_carry_the_order(monkeypatch):
    monkeypatch.delenv("SP_UNIT_USD", raising=False)
    from tests.test_desk_policy import NOW, row
    doc = {"sport": "mlb", "predictions": [
        row("Kansas City", 0.66, fair_h=0.58, bid=0.55, ask=0.58, kalshi_legs=LEGS2),     # PLAY HOME
        row("Pass Town", 0.52, fair_h=0.51, kalshi_legs=LEGS2)]}                             # PASS
    dp.annotate(doc, now=NOW)
    play, pas = doc["predictions"][0]["desk"], doc["predictions"][1]["desk"]
    assert play["call"] == "PLAY" and play["order"]["text"] == f"BUY YES KXNFLGAME-26OCT05BUFKC-KC @ 0.55 × {int(play['units'] * 10)}"
    assert pas["call"] == "PASS" and pas["order"] is None
    ev = dp.evaluate(doc, float((NOW.timestamp()) * 1000))
    legs = [r for r, c in ev["calls"]]
    t = {"legs": legs[:1], "sports": 1, "pm": 0.66, "pk": 0.58, "edge": 0.08}
    b = dp.parlay_block(t)
    assert b["legs"][0]["order"]["text"] == "BUY YES KXNFLGAME-26OCT05BUFKC-KC @ 0.55 × 2"   # 0.25u x 10 -> 2


def test_stored_ticker_reaches_kalshi_legs():
    """sync -> snapshot.market_ticker -> export kalshi_legs (the latest pre-kickoff leg; in-play never)."""
    init_db()
    from src.timeutil import utc_now_naive
    now = utc_now_naive().replace(microsecond=0)
    with session_scope() as s:
        c = Competition(sport=Sport.NFL, code="OL1", name="OL1", area="US", type="LEAGUE")
        h, a = Team(sport=Sport.NFL, name="OL Home"), Team(sport=Sport.NFL, name="OL Away")
        s.add_all([c, h, a])
        s.flush()
        m = Match(sport=Sport.NFL, competition_id=c.id, season="2026", utc_date=now + timedelta(hours=3),
                  status=MatchStatus.SCHEDULED, home_team_id=h.id, away_team_id=a.id)
        s.add(m)
        s.flush()
        for sel, t, at in (("HOME", "OLD-H", now - timedelta(hours=2)), ("HOME", "NEW-H", now - timedelta(hours=1)),
                           ("AWAY", "NEW-A", now - timedelta(hours=1)), ("AWAY", "INPLAY-A", now + timedelta(hours=4))):
            s.add(OddsSnapshot(match_id=m.id, market="ML", selection=sel, devig_prob=0.5, n_books=1, captured_at=at,
                               source="kalshi", yes_bid=0.49, yes_ask=0.51, market_ticker=t))
        s.flush()
        snaps = list(s.execute(select(OddsSnapshot).where(OddsSnapshot.match_id == m.id)).scalars())
        legs = kalshi_legs(latest_kalshi_by_selection(snaps, m.utc_date))
        s.query(OddsSnapshot).filter(OddsSnapshot.match_id == m.id).delete(synchronize_session=False)
        s.query(Match).filter(Match.id == m.id).delete(synchronize_session=False)
    assert legs == {"AWAY": {"ticker": "NEW-A", "bid": 0.49, "ask": 0.51},
                    "HOME": {"ticker": "NEW-H", "bid": 0.49, "ask": 0.51}}
