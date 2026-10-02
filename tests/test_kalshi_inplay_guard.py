"""In-play guard keyed on OUR start time, not the market's (ARCHITECT 2026-10-01:
PHI@ATL 00:00Z postseason night game skipped as in-play at 22:55Z, 65 min before
first pitch — "in-play skipped 2, matched 0"; the T-60 Kalshi refresh must work
on 00:00Z starts)."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from src.adapters.kalshi import KalshiAdapter
from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, OddsSnapshot, Sport, Team
from src.timeutil import utc_now_naive


def test_ticker_start_reads_the_et_stamp():
    t = KalshiAdapter.ticker_start({"ticker": "KXMLBGAME-26OCT012000PHIATL-PHI"})
    assert t == datetime(2026, 10, 2, 0, 0)                       # 20:00 EDT = 00:00Z next day
    assert KalshiAdapter.ticker_start({"ticker": "KXMLBGAME-26AUG242145CINSF-SF"}) == datetime(2026, 8, 25, 1, 45)
    assert KalshiAdapter.ticker_start({"ticker": "KXEPLGAME-26SEP13ARSCHE-ARS"}) is None   # no time component
    assert KalshiAdapter.ticker_start({}) is None


def _game(home, away, kick):
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == "MLB")).scalar_one_or_none()
        if comp is None:
            comp = Competition(sport=Sport.MLB, code="MLB", name="MLB", area="USA", type="LEAGUE")
            s.add(comp)
        h = Team(sport=Sport.MLB, name=home, external_ids={"ipg": home})
        a = Team(sport=Sport.MLB, name=away, external_ids={"ipg": away})
        s.add_all([h, a])
        s.flush()
        m = Match(sport=Sport.MLB, competition_id=comp.id, season="2074", utc_date=kick,
                  status=MatchStatus.SCHEDULED, home_team_id=h.id, away_team_id=a.id)
        s.add(m)
        s.flush()
        return m.id


def _markets(stamp, occ, away, home, a_sub, h_sub):
    base = {"event_ticker": f"KXMLBGAME-{stamp}", "title": f"{a_sub} vs {h_sub} Winner?"}
    return [{**base, "ticker": f"KXMLBGAME-{stamp}-A", "yes_sub_title": a_sub, "occurrence_datetime": occ,
             "yes_bid_dollars": "0.44", "yes_ask_dollars": "0.46"},
            {**base, "ticker": f"KXMLBGAME-{stamp}-H", "yes_sub_title": h_sub, "occurrence_datetime": occ,
             "yes_bid_dollars": "0.54", "yes_ask_dollars": "0.56"}]


def _sync(monkeypatch, markets):
    from src.ingestion import kalshi_sync
    monkeypatch.setattr(KalshiAdapter, "status", lambda self: {"trading_active": True})
    monkeypatch.setattr(KalshiAdapter, "sports_filters", lambda self: {})
    monkeypatch.setattr(KalshiAdapter, "game_series_markets", lambda self: markets)
    return kalshi_sync.sync_kalshi_mlb()


def _stamp(kick_utc):
    from zoneinfo import ZoneInfo
    et = kick_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("America/New_York"))
    return et.strftime("%y%b%d%H%M").upper()


@pytest.fixture(scope="module", autouse=True)
def _db():
    init_db()


def test_night_game_65_min_out_is_priced_although_occurrence_has_passed(monkeypatch):
    """The PHI@ATL shape: our start is T+65 min; the market's occurrence_datetime
    is already in the past. Before: in-play skipped 2, matched 0."""
    now = utc_now_naive().replace(second=0, microsecond=0)
    kick = now + timedelta(minutes=65)
    mid = _game("Ipga Braves", "Ipgp Phillies", kick)
    occ = (now - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")   # market-side time, passed
    r = _sync(monkeypatch, _markets(_stamp(kick) + "IPGPIPGA", occ, "Ipgp Phillies", "Ipga Braves",
                                     "Ipgp", "Ipga"))
    assert r["ok"] and r["in_play"] == 0, r
    with session_scope() as s:
        sel = {x.selection for x in s.execute(select(OddsSnapshot).where(
            OddsSnapshot.match_id == mid, OddsSnapshot.source == "kalshi")).scalars()}
    assert sel == {"HOME", "AWAY"}, r


def test_game_already_started_is_still_refused_as_in_play(monkeypatch):
    """Our start 10 min ago, occurrence in the FUTURE (the soccer-derby shape):
    in-play on OUR clock, never stored."""
    now = utc_now_naive().replace(second=0, microsecond=0)
    kick = now - timedelta(minutes=10)
    mid = _game("Ipgc Cubs", "Ipgd Dodgers", kick)
    occ = (now + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = _sync(monkeypatch, _markets(_stamp(kick) + "IPGDIPGC", occ, "Ipgd Dodgers", "Ipgc Cubs",
                                     "Ipgd", "Ipgc"))
    assert r["ok"] and r["in_play"] == 2, r
    with session_scope() as s:
        n = len(list(s.execute(select(OddsSnapshot).where(
            OddsSnapshot.match_id == mid, OddsSnapshot.source == "kalshi")).scalars()))
    assert n == 0


def test_cli_date_to_covers_the_whole_utc_day(monkeypatch):
    """The window's MLB step is `sync-kalshi --date-from {today} --date-to {tomorrow}`;
    an 00:05Z first pitch on {tomorrow} must be inside the window."""
    from click.testing import CliRunner
    import cli
    from src.ingestion import kalshi_sync
    seen = {}

    def fake(date_from=None, date_to=None, progress=None, **kw):
        seen.update(lo=date_from, hi=date_to)
        return {"ok": False, "reason": "test"}
    monkeypatch.setattr(kalshi_sync, "sync_kalshi_mlb", fake)
    CliRunner().invoke(cli.cli, ["sync-kalshi", "--date-from", "2026-10-01", "--date-to", "2026-10-02"])
    assert seen["lo"] == datetime(2026, 10, 1)
    assert seen["hi"] > datetime(2026, 10, 2, 23, 59) and seen["hi"] < datetime(2026, 10, 3)
