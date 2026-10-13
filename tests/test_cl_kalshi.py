"""CL reads Kalshi (ARCHITECT 2026-10-13 09:42 ET, addendum 58): KXUCLGAME, wired as PL is.

Item 1, verbatim: "CL reads Kalshi through the series KXUCLGAME. It is wired as PL is: the soccer path, three legs, the
same spread guard, the same placement. Nothing else about the cups changes: CL stays market-only, with no model and no
call." Item 2's tests: "the Arsenal event's three legs on Lille @ Arsenal, sides and the Tie leg; a CL event whose two
names fit no stored game is refused for no fit." Kalshi is mocked (no network).
"""
from datetime import datetime, timedelta
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import select

from src.adapters.kalshi import KalshiAdapter
from src.ingestion import kalshi_match as km

Z = lambda s: datetime.fromisoformat(s)                                      # noqa: E731  naive UTC
_IDS: dict = {}


def _team(name):
    return NS(id=_IDS.setdefault(name, len(_IDS) + 1), name=name)


def _game(gid, away, home, kick):
    h, a = _team(home), _team(away)
    return NS(id=gid, utc_date=kick, home_team=h, away_team=a, home_team_id=h.id, away_team_id=a.id, status=None)


def _event(stamp, legs, bid="0.40", ask="0.42"):
    """A KXUCLGAME event as the receipt reads KXUCLGAME-26OCT13ARSLIL: a market per name and the Tie leg."""
    e = f"KXUCLGAME-{stamp}"
    return [{"event_ticker": e, "ticker": f"{e}-{sfx}", "title": f"{name} wins", "yes_sub_title": name,
             "yes_bid_dollars": bid, "yes_ask_dollars": ask} for sfx, name in legs]


def _place(markets, games, now):
    a = KalshiAdapter.__new__(KalshiAdapter)
    return km.place(markets, games, now=now, lo=now - timedelta(days=1), hi=now + timedelta(days=7),
                    implied_prob=KalshiAdapter.implied_prob, is_tie=a.is_tie_market, spread=a.spread_dollars,
                    max_spread=0.10)


ARS_LIL = _event("26OCT13ARSLIL", [("ARS", "Arsenal"), ("LIL", "Lille"), ("TIE", "Tie")])


def test_cl_is_pinned_to_kxuclgame_with_no_discovery():
    a = KalshiAdapter.__new__(KalshiAdapter)
    a._get = lambda path, params=None: (_ for _ in ()).throw(AssertionError("no call for a pinned series"))
    assert a.resolve_soccer_series("CL") == ("KXUCLGAME", "mapped")
    assert KalshiAdapter.SOCCER_GAME_SERIES["PL"] == "KXEPLGAME"                  # PL as it was


def test_the_arsenal_events_three_legs_land_on_lille_at_arsenal():
    """The receipt's event: -ARS "Arsenal", -LIL "Lille", -TIE "Tie" on the stored Lille @ Arsenal row."""
    g = _game(91001, "Lille", "Arsenal", Z("2026-10-13T19:00"))
    res = _place(ARS_LIL, [g], now=Z("2026-10-13T12:00"))
    got = {k: mk["ticker"].rsplit("-", 1)[1] for k, mk in res.placed.items()}
    assert got == {(91001, "HOME"): "ARS", (91001, "AWAY"): "LIL", (91001, "DRAW"): "TIE"}, res.refused
    assert not res.refused


def test_a_cl_event_whose_names_fit_no_stored_game_is_refused_for_no_fit():
    other = _game(91002, "Galatasaray", "Barcelona", Z("2026-10-13T19:00"))
    res = _place(ARS_LIL, [other], now=Z("2026-10-13T12:00"))
    assert not res.placed and res.refused == {km.NO_FIT: 3}, res.refused


def test_a_wide_cl_leg_is_refused_by_the_same_spread_guard():
    g = _game(91003, "Lille", "Arsenal", Z("2026-10-13T19:00"))
    wide = [dict(m, yes_ask_dollars="0.81", yes_bid_dollars="0.03") if m["ticker"].endswith("-TIE") else m
            for m in ARS_LIL]
    res = _place(wide, [g], now=Z("2026-10-13T12:00"))
    assert res.refused.get(km.WIDE_SPREAD) == 1 and (91003, "DRAW") not in res.placed


# the nine event titles of 2026-10-13 against the stored names on the host's window card (addendum 58 item 1):
# "Each pair shares a word one each"
RECEIPT_PAIRS = [("Lens", "Lens"), ("Sporting CP", "Sporting CP"), ("Sabah Masazir", "Sabah FA"),
                 ("Slavia Prague", "Slavia Praha"), ("Arsenal", "Arsenal"), ("Lille", "Lille"),
                 ("Atletico", "Atletico Madrid"), ("Manchester United", "Manchester United"),
                 ("Galatasaray", "Galatasaray"), ("Barcelona", "Barcelona"), ("Inter", "Inter"),
                 ("Club Brugge", "Club Brugge KV"), ("Leipzig", "RB Leipzig"), ("Eindhoven", "PSV Eindhoven"),
                 ("Viking", "Viking"), ("Bayern Munich", "Bayern München"), ("Villarreal", "Villarreal"),
                 ("Napoli", "Napoli")]


@pytest.mark.parametrize("kalshi, stored", RECEIPT_PAIRS)
def test_each_receipt_name_shares_a_word_with_its_stored_name(kalshi, stored):
    assert km.side_score(kalshi, stored) >= 1


def test_the_replay_reads_kxuclgame_with_the_other_soccer_series():
    from src.ingestion.kalshi_replay import series_plan
    a = KalshiAdapter.__new__(KalshiAdapter)
    plan = {p["competition"]: p for p in series_plan(a)}
    assert plan["CL"]["series"] == "KXUCLGAME" and plan["CL"]["path"] == "soccer" and plan["CL"]["how"] == "mapped"


def test_the_host_window_syncs_cl_as_it_syncs_unl():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "chains", Path(__file__).resolve().parents[1] / "deploy" / "hosting" / "chains.py")
    chains = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(chains)
    assert chains.WINDOW_KALSHI["CL"] == [["sync-kalshi-soccer", "--competition", "CL"]]
    assert "CL" not in chains.KALSHI_CAPTURE_ONLY


def test_cl_stays_market_only_no_venue_pricing_series():
    """'Nothing else about the cups changes': no venue series is added for CL, so no call is priced through it.
    Addendum 61 item 3(2) adds KXUCLGAME's fee M for a fill (tests/test_cl_venue_stop.py)."""
    from src.walters.venue import KALSHI_SERIES_BY_COMPETITION
    assert "CL" not in KALSHI_SERIES_BY_COMPETITION


def test_sync_kalshi_soccer_cl_stores_what_the_placement_places(monkeypatch):
    from src.db.database import init_db, session_scope
    from src.db.schema import Competition, Match, MatchStatus, OddsSnapshot, Sport, Team
    from src.ingestion import kalshi_sync
    from src.ingestion.kalshi_match import et_day
    from src.timeutil import utc_now_naive

    init_db()
    ko = (utc_now_naive() + timedelta(days=2)).replace(microsecond=0, second=0)
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == "CL")).scalars().first()
        if comp is None:
            comp = Competition(sport=Sport.SOCCER, code="CL", name="UEFA Champions League", area="EU", type="CUP")
            s.add(comp)
            s.flush()
        h, a = Team(sport=Sport.SOCCER, name="Arsenal"), Team(sport=Sport.SOCCER, name="Lille")
        s.add_all([h, a])
        s.flush()
        m = Match(sport=Sport.SOCCER, competition_id=comp.id, season="2026/27", utc_date=ko,
                  status=MatchStatus.SCHEDULED, home_team_id=h.id, away_team_id=a.id)
        s.add(m)
        s.flush()
        mid = m.id
    ev = f"KXUCLGAME-{et_day(ko):%y%b%d}".upper() + "ARSLIL"
    legs = [{"ticker": f"{ev}-ARS", "event_ticker": ev, "yes_sub_title": "Arsenal",
             "yes_bid_dollars": "0.54", "yes_ask_dollars": "0.56"},
            {"ticker": f"{ev}-LIL", "event_ticker": ev, "yes_sub_title": "Lille",
             "yes_bid_dollars": "0.19", "yes_ask_dollars": "0.21"},
            {"ticker": f"{ev}-TIE", "event_ticker": ev, "yes_sub_title": "Tie",
             "yes_bid_dollars": "0.24", "yes_ask_dollars": "0.26"}]
    asked = []

    class Fake(KalshiAdapter):
        def __init__(self):
            pass

        def _get(self, path, params=None):
            raise AssertionError("a pinned series makes no discovery call")

        def status(self):
            return {"trading_active": True}

        def open_markets_for_series(self, t):
            asked.append(t)
            return legs

    monkeypatch.setattr(kalshi_sync, "KalshiAdapter", Fake)
    r = kalshi_sync.sync_kalshi_soccer("CL")
    assert r["ok"] and r["series"] == "KXUCLGAME" and r["series_how"] == "mapped" and asked == ["KXUCLGAME"], r
    assert r["stored"] == 3, r
    with session_scope() as s:
        got = {o.selection: (o.devig_prob, o.yes_bid, o.yes_ask) for o in s.execute(
            select(OddsSnapshot).where(OddsSnapshot.match_id == mid, OddsSnapshot.source == "kalshi")).scalars()}
        s.query(OddsSnapshot).filter(OddsSnapshot.match_id == mid).delete(synchronize_session=False)
        s.query(Match).filter(Match.id == mid).delete(synchronize_session=False)
    assert got == {"HOME": (0.55, 0.54, 0.56), "AWAY": (0.2, 0.19, 0.21), "DRAW": (0.25, 0.24, 0.26)}, got


def test_a_cl_row_with_its_kalshi_legs_makes_no_venue_call_today():
    """'no call': with books and a two-sided Kalshi block, the window card's CL row makes no venue call. Since
    addendum 61 item 3(1) (#498) its own stop says why, before the quote-age rule is reached."""
    from datetime import timezone
    from src.walters import desk_policy as dp
    now = datetime(2026, 10, 13, 16, 0, tzinfo=timezone.utc)
    ms = float((now - datetime(1970, 1, 1, tzinfo=timezone.utc)) // timedelta(milliseconds=1))
    row = {"engine": "market_only", "competition": "CL", "utc_date": "2026-10-13T19:00:00",
           "market": {"bookmaker_count": 10, "fair_prob": {"HOME": 0.62, "AWAY": 0.16, "DRAW": 0.22},
                      "captured_at": "2026-10-13T15:30:00"},
           "kalshi": {"status": "two_sided", "prob": {"HOME": 0.55, "AWAY": 0.20, "DRAW": 0.25}}}
    v = dp.window_venue(row, ms)
    assert (v["eligible"], v["reason"]) == (False, "three-way soccer — no venue call before the skew test is read (CL)"), v
