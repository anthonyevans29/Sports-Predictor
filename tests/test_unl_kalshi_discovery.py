"""ARCHITECT 2026-10-04: sync-kalshi-soccer only knew KXEPLGAME; UNL has Kalshi markets (operator fills exist).
The UNL series is DISCOVERED from Kalshi's /series listing at run time (law 1: no guessed ticker) — exactly
one game series or a refusal naming the candidates — and its legs are stored like PL's, so the fixtures
export and the venue engine see UNL three-way sets. Kalshi is mocked (no network)."""
from datetime import timedelta

from sqlalchemy import select

from src.adapters.kalshi import KalshiAdapter
from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, OddsSnapshot, Sport, Team
from src.ingestion import kalshi_sync
from src.timeutil import utc_now_naive

SERIES = [{"ticker": "KXUEFANLGAME", "title": "UEFA Nations League Game", "category": "Sports", "tags": ["Soccer"]},
          {"ticker": "KXUEFANLWINNER", "title": "UEFA Nations League Winner", "category": "Sports"},
          {"ticker": "KXEPLGAME", "title": "English Premier League Game", "category": "Sports"}]


def _adapter(series_payload):
    a = KalshiAdapter.__new__(KalshiAdapter)
    a._get = lambda path, params=None: {"series": series_payload} if path == "series" else {}
    return a


def test_unl_series_is_discovered_from_the_listing_exactly_one_or_refused():
    t, how = _adapter(SERIES).resolve_soccer_series("UNL")
    assert t == "KXUEFANLGAME" and how.startswith("discovered KXUEFANLGAME")    # the WINNER series is not a game
    assert _adapter(SERIES).resolve_soccer_series("PL") == ("KXEPLGAME", "mapped")
    t, how = _adapter(SERIES + [{"ticker": "KXUNLGAME", "title": "Nations League match"}]).resolve_soccer_series("UNL")
    assert t is None and "2 game series" in how and "REFUSED" in how and "KXUNLGAME" in how
    t, how = _adapter([]).resolve_soccer_series("UNL")
    assert t is None and "0 game series" in how
    assert _adapter([]).resolve_soccer_series("UNL", override="KXPINNED") == ("KXPINNED", "series KXPINNED (operator --series)")
    assert _adapter(SERIES).resolve_soccer_series("EFL")[0] is None                # neither mapped nor discoverable


def test_unl_legs_are_stored_as_a_three_way_set(monkeypatch):
    init_db()
    ko = (utc_now_naive() + timedelta(days=2)).replace(microsecond=0, second=0)
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == "UNL")).scalars().first()
        if comp is None:
            comp = Competition(sport=Sport.SOCCER, code="UNL", name="UEFA Nations League", area="EU", type="INTL")
            s.add(comp)
            s.flush()
        h, a = Team(sport=Sport.SOCCER, name="Zedlandia"), Team(sport=Sport.SOCCER, name="Qorvania")
        s.add_all([h, a])
        s.flush()
        m = Match(sport=Sport.SOCCER, competition_id=comp.id, season="2026/27", utc_date=ko,
                  status=MatchStatus.SCHEDULED, home_team_id=h.id, away_team_id=a.id)
        s.add(m)
        s.flush()
        mid = m.id
    occ = (ko + timedelta(hours=2)).isoformat() + "Z"
    legs = [{"ticker": "KXUEFANLGAME-X-ZED", "event_ticker": "EV1", "yes_sub_title": "Zedlandia",
             "yes_bid_dollars": "0.44", "yes_ask_dollars": "0.46", "occurrence_datetime": occ},
            {"ticker": "KXUEFANLGAME-X-QOR", "event_ticker": "EV1", "yes_sub_title": "Qorvania",
             "yes_bid_dollars": "0.29", "yes_ask_dollars": "0.31", "occurrence_datetime": occ},
            {"ticker": "KXUEFANLGAME-X-TIE", "event_ticker": "EV1", "yes_sub_title": "Tie",
             "yes_bid_dollars": "0.25", "yes_ask_dollars": "0.27", "occurrence_datetime": occ}]
    asked = []

    class Fake(KalshiAdapter):
        def __init__(self):
            pass

        def _get(self, path, params=None):
            return {"series": SERIES} if path == "series" else {}

        def status(self):
            return {"trading_active": True}

        def open_markets_for_series(self, t):
            asked.append(t)
            return legs

    monkeypatch.setattr(kalshi_sync, "KalshiAdapter", Fake)
    r = kalshi_sync.sync_kalshi_soccer("UNL")
    assert r["ok"] and r["series"] == "KXUEFANLGAME" and asked == ["KXUEFANLGAME"], r
    assert r["series_how"].startswith("discovered") and r["stored"] == 3, r
    with session_scope() as s:
        got = {o.selection: (o.devig_prob, o.yes_bid, o.yes_ask) for o in s.execute(
            select(OddsSnapshot).where(OddsSnapshot.match_id == mid, OddsSnapshot.source == "kalshi")).scalars()}
        s.query(OddsSnapshot).filter(OddsSnapshot.match_id == mid).delete(synchronize_session=False)
        s.query(Match).filter(Match.id == mid).delete(synchronize_session=False)
    assert got == {"HOME": (0.45, 0.44, 0.46), "AWAY": (0.3, 0.29, 0.31), "DRAW": (0.26, 0.25, 0.27)}, got
