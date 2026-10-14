"""KALSHI SETTLED-MARKET HISTORY, the ingest (ARCHITECT 2026-10-14, addendum 67 item 1; #519): `kalshi-history` on the
payload fixtures (tests/fixtures/kalshi_history: stand-ins for the probe's kept files until those replace them; see its
README) and a throwaway DB. Synthetic series KXZKHGAME on competition ZKH (MLB shape: clock tickers, two legs)."""
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner
from sqlalchemy import func, inspect, select, text

from src.adapters.kalshi import KalshiAdapter
from src.ingestion import kalshi_history as kh

FIX = Path(__file__).parent / "fixtures" / "kalshi_history"
SERIES = "KXZKHGAME"
NOW = datetime(2026, 10, 14, 12, 0)
NO_FIT = "no game of the competition on the event's day fits both names"


def _load(name):
    return json.loads((FIX / f"{name}.json").read_text())


def route(path, params=None, pages=None):
    """The exchange as the kept payloads answer it: the cutoff, a page of each list, a reply of each candle shape."""
    if path == "historical/cutoff":
        return _load("cutoff")
    if path in ("historical/markets", "markets"):
        if pages and path in pages:
            return pages[path][int((params or {}).get("cursor") or 0)]
        return _load("historical_markets_page" if path == "historical/markets" else "settled_markets_page")
    if path.startswith("historical/markets/") and path.endswith("/candlesticks"):
        return _load("historical_candlesticks")
    if path.startswith(f"series/{SERIES}/markets/") and path.endswith("/candlesticks"):
        return _load("live_candlesticks")
    raise AssertionError(f"unexpected call {path}")


class FakeKalshi(KalshiAdapter):
    def __init__(self, pages=None):
        super().__init__()
        self.pages, self.calls = pages, []

    def _get(self, path, params=None):
        self.calls.append((path, dict(params or {})))
        return route(path, params, self.pages)


@pytest.fixture
def world(monkeypatch):
    """Competition ZKH (series KXZKHGAME), Alpha Owls @ Beta Bears on 2025-07-04 23:15Z (the ticker's clock says
    19:10 ET = 23:10Z: the window reads the stored kickoff) and 2026-09-01 23:05Z, and no stored row of the series
    (the throwaway DB is shared by the session)."""
    from src.db.database import get_engine, init_db, session_scope
    from src.db.schema import Competition, KalshiSettledMarket, Match, MatchStatus, Sport, Team
    from src.walters import venue
    init_db()
    monkeypatch.setitem(venue.KALSHI_SERIES_BY_COMPETITION, "ZKH", SERIES)
    with session_scope() as s:
        if s.execute(select(Competition).where(Competition.code == "ZKH")).scalar_one_or_none() is None:
            comp = Competition(sport=Sport.MLB, code="ZKH", name="ZKH", area="X", type="LEAGUE")
            a, b = Team(sport=Sport.MLB, name="Alpha Owls"), Team(sport=Sport.MLB, name="Beta Bears")
            s.add_all([comp, a, b])
            s.flush()
            for kick in (datetime(2025, 7, 4, 23, 15), datetime(2026, 9, 1, 23, 5)):
                s.add(Match(sport=Sport.MLB, competition_id=comp.id, season=str(kick.year), utc_date=kick,
                            status=MatchStatus.FINISHED, home_team_id=b.id, away_team_id=a.id))
    with get_engine().begin() as c:
        c.execute(text("DELETE FROM kalshi_settled_markets WHERE series = :s"), {"s": SERIES})
    ids = {}
    with session_scope() as s:
        for m in s.execute(select(Match).join(Competition).where(Competition.code == "ZKH")).scalars():
            ids[m.utc_date.year] = m.id
    return ids


def rows():
    from src.db.database import session_scope
    from src.db.schema import KalshiSettledMarket
    with session_scope() as s:
        return {r.ticker: {c: getattr(r, c) for c in KalshiSettledMarket.__table__.c.keys()}
                for r in s.execute(select(KalshiSettledMarket).where(KalshiSettledMarket.series == SERIES)).scalars()}


def _ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def go(**kw):
    out = []
    kw.setdefault("adapter", FakeKalshi())
    run = kh.run_history(SERIES, echo=out.append, now=NOW, **kw)
    return run, out


def test_a_stored_row_reads_each_shape_by_its_own_keys(world):
    """Historical: yes_bid.close / yes_ask.close; live: yes_bid.close_dollars / yes_ask.close_dollars. A candle that
    carries the other shape's keys is not two-sided for this one; the last two-sided candle at or before kickoff is
    the quote, and a candle after kickoff never is."""
    fake = FakeKalshi()
    run, out = go(adapter=fake)
    got = rows()
    h = got["KXZKHGAME-25JUL041910ALPBET-ALP"]
    assert (h["source"], h["match_id"], h["side"], h["kalshi_result"]) == ("historical", world[2025], "AWAY", "yes")
    assert h["last_ts"] == datetime(2025, 7, 4, 23, 5) and (h["last_bid"], h["last_ask"]) == (0.52, 0.53)
    assert h["last_mid"] == pytest.approx(0.525)
    # the window is the STORED kickoff's (23:15Z), not the ticker clock's (23:10Z): (17:15, 23:15]
    assert (h["candles_6h"], h["candles_two_sided"], h["gaps"]) == (4, 2, 356)
    start = {p.rsplit("/", 2)[-2]: q["start_ts"] for p, q in fake.calls if p.endswith("/candlesticks")}
    assert start["KXZKHGAME-25JUL041910ALPBET-ALP"] == _ts(datetime(2025, 7, 4, 17, 15))
    assert got["KXZKHGAME-25JUL041910ALPBET-BET"]["side"] == "HOME"
    lv = got["KXZKHGAME-26SEP011905ALPBET-BET"]
    assert (lv["source"], lv["match_id"], lv["side"], lv["kalshi_result"]) == ("live", world[2026], "HOME", "yes")
    assert lv["last_ts"] == datetime(2026, 9, 1, 23, 0) and (lv["last_bid"], lv["last_ask"]) == (0.47, 0.49)
    assert lv["last_mid"] == pytest.approx(0.48)
    assert (lv["candles_6h"], lv["candles_two_sided"], lv["gaps"]) == (4, 2, 356)
    assert all(r["fetched_at"] == NOW and r["settled_time"] is None for r in got.values())
    assert "  stored: 6 (placed on a stored game 4, refused and kept 2) · already stored 0" in out


def test_a_null_price_minute_stays_null(world):
    """A zero-volume minute carries a null price with bid and ask present: it is two-sided, and its null price is
    kept as sent in the first candle. A minute with no bid (or no ask) is one-sided and nothing fills it."""
    go()
    h = rows()["KXZKHGAME-25JUL041910ALPBET-ALP"]
    assert h["raw_first_candle"] == _load("historical_candlesticks")["candlesticks"][0]
    assert h["raw_first_candle"]["price"]["close"] is None and h["raw_first_candle"]["volume"] == 0   # kept null
    one_sided = [c for c in _load("historical_candlesticks")["candlesticks"] if c["yes_bid"].get("close", 0) is None]
    assert one_sided and kh.bid_ask(one_sided[0], "historical") == (None, 0.54)
    zero_vol = _load("historical_candlesticks")["candlesticks"][1]
    assert zero_vol["price"]["close"] is None and kh.bid_ask(zero_vol, "historical") == (0.41, 0.46)
    lv_one = [c for c in _load("live_candlesticks")["candlesticks"] if c["yes_ask"].get("close_dollars", 1) is None]
    assert lv_one and kh.bid_ask(lv_one[0], "live") == (0.48, None)
    lv = rows()["KXZKHGAME-26SEP011905ALPBET-ALP"]
    assert lv["last_ts"] == datetime(2026, 9, 1, 23, 0)          # not the one-sided 23:05, not filled from it


def test_an_unmatched_market_stores_match_id_null_with_its_reason(world):
    """Refused rows are kept, never guessed: match_id and side null, the matcher's reason in notes, and the run lists
    the refusals by reason. Its ticker carries a clock, so its candles are fetched on the ticker's time."""
    fake = FakeKalshi()
    run, out = go(adapter=fake)
    start = {p.rsplit("/", 2)[-2]: q["start_ts"] for p, q in fake.calls if p.endswith("/candlesticks")}
    for t in ("KXZKHGAME-25JUL052005GAMDEL-GAM", "KXZKHGAME-25JUL052005GAMDEL-DEL"):
        r = rows()[t]
        assert r["match_id"] is None and r["side"] is None
        assert r["notes"].startswith(f"refused by the matcher: {NO_FIT}")
        # fetched on the ticker's clock: 20:05 ET on 07-05 = 00:05Z on 07-06, less six hours
        assert start[t] == _ts(datetime(2025, 7, 5, 18, 5)) and r["candles_6h"] is not None
    assert run.refused == {NO_FIT: 2}
    i = out.index("  refused by the matcher, by reason (kept with match_id null):")
    assert out[i + 1] == f"        2  {NO_FIT}"


def test_unmatched_with_no_clock_fetches_no_candles(world):
    """A date-only ticker that the matcher refuses has no kickoff: no candle call, and notes says so."""
    page = {"markets": [{"ticker": "KXZKHGAME-25JUL06EPSZET-EPS", "event_ticker": "KXZKHGAME-25JUL06EPSZET",
                         "yes_sub_title": "Epsilon", "result": "yes", "close_time": "2025-07-07T03:00:00Z"},
                        {"ticker": "KXZKHGAME-25JUL06EPSZET-ZET", "event_ticker": "KXZKHGAME-25JUL06EPSZET",
                         "yes_sub_title": "Zeta", "result": "no", "close_time": "2025-07-07T03:00:00Z"}],
            "cursor": ""}
    fake = FakeKalshi(pages={"historical/markets": [page], "markets": [{"markets": [], "cursor": ""}]})
    run, out = go(adapter=fake)
    r = rows()["KXZKHGAME-25JUL06EPSZET-EPS"]
    assert r["match_id"] is None and r["last_ts"] is None and r["candles_6h"] is None
    assert "no candles fetched: unmatched and the ticker carries no clock" in r["notes"]
    assert run.candle_calls == 0 and not any(p.endswith("/candlesticks") for p, _ in fake.calls)


def test_the_cap_stops_the_run_prints_where_and_the_next_run_resumes(world):
    """Four calls: the cutoff, the two lists, and the candles of the first event's first leg. The run stores that one,
    prints where it stopped, and the next run skips it (already stored) and still places its second leg on the
    game: the matcher reads every listed leg in range, stored or not, so an event is never matched on part of it."""
    run, out = go(max_calls=4)
    assert set(rows()) == {"KXZKHGAME-25JUL041910ALPBET-ALP"}
    assert out[-1] == ("  STOPPED at the cap (4 calls) before the candles of KXZKHGAME-25JUL041910ALPBET-BET "
                       "(historical); 5 market(s) left for the next run, which skips the stored ones")
    run2, out2 = go()
    assert run2.already == 1 and len(rows()) == 6
    bet = rows()["KXZKHGAME-25JUL041910ALPBET-BET"]
    assert (bet["match_id"], bet["side"]) == (world[2025], "HOME")
    assert rows()["KXZKHGAME-26SEP011905ALPBET-ALP"]["match_id"] == world[2026]
    assert run2.refused == {NO_FIT: 2} and not run2.stopped


def test_the_cap_inside_a_list_stores_nothing_and_prints_the_cursor(world):
    """A list cut short is never half-read: nothing is placed or stored, not even a market of a list read whole that
    needs no candle call, and the run names the list and its cursor."""
    no_clock = {"markets": [{"ticker": "KXZKHGAME-25JUL06EPSZET-EPS", "event_ticker": "KXZKHGAME-25JUL06EPSZET",
                             "yes_sub_title": "Epsilon", "result": "yes", "close_time": "2025-07-07T03:00:00Z"},
                            {"ticker": "KXZKHGAME-25JUL06EPSZET-ZET", "event_ticker": "KXZKHGAME-25JUL06EPSZET",
                             "yes_sub_title": "Zeta", "result": "no", "close_time": "2025-07-07T03:00:00Z"}],
                "cursor": ""}
    live = _load("settled_markets_page")["markets"]
    pages = {"historical/markets": [no_clock],
             "markets": [{"markets": live[:1], "cursor": "1"}, {"markets": live[1:], "cursor": ""}]}
    run, out = go(adapter=FakeKalshi(pages=pages), max_calls=3)
    assert rows() == {} and run.rows == []
    assert out[-1] == ("  STOPPED at the cap (3 calls) while listing live (markets), before page 2 at cursor 1; "
                       "nothing is placed or stored from a list cut short (a larger --max-calls lists it whole)")


def test_dry_run_writes_nothing_and_prints_what_would_be_stored(world):
    from src.db.database import get_engine
    eng = get_engine()

    def counts():
        with eng.connect() as c:
            return {t: c.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar()
                    for t in inspect(eng).get_table_names()}
    before = counts()
    run, out = go(dry_run=True)
    assert counts() == before and rows() == {}
    assert "  would be stored: 6 (placed on a stored game 4, refused and kept 2) · already stored 0" in out
    assert any(ln.startswith("    KXZKHGAME-26SEP011905ALPBET-BET · live · match ") and "bid 0.47 ask 0.49" in ln
               for ln in out)


def test_a_run_writes_its_one_table_and_nothing_else(world):
    from src.db.database import get_engine
    eng = get_engine()

    def counts():
        with eng.connect() as c:
            return {t: c.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar()
                    for t in inspect(eng).get_table_names() if t != kh.TABLE}
    before = counts()
    go()
    assert counts() == before and len(rows()) == 6


def test_since_and_until_keep_the_markets_of_their_game_days(world):
    run, out = go(since=date(2026, 1, 1))
    assert set(rows()) == {"KXZKHGAME-26SEP011905ALPBET-ALP", "KXZKHGAME-26SEP011905ALPBET-BET"}
    assert run.out_of_range == 4
    go(until=date(2025, 7, 4))
    assert "KXZKHGAME-25JUL041910ALPBET-ALP" in rows() and "KXZKHGAME-25JUL052005GAMDEL-GAM" not in rows()


def test_a_series_the_syncs_do_not_read_is_refused(world):
    with pytest.raises(ValueError, match="REFUSED: KXNOPEGAME is not a series the syncs read"):
        kh.run_history("KXNOPEGAME", adapter=FakeKalshi(), echo=lambda *_: None)


def test_the_command_runs_dry_and_refuses_a_bad_date(world, monkeypatch):
    import cli
    monkeypatch.setattr(KalshiAdapter, "_get", lambda self, path, params=None: route(path, params))
    res = CliRunner().invoke(cli.cli, ["kalshi-history", "--series", SERIES, "--dry-run", "--since", "2026-09-01"])
    assert res.exit_code == 0, res.output
    assert "cutoff market_settled_ts: 2026-08-15T00:00:00Z" in res.output
    assert "would be stored: 2 (placed on a stored game 2, refused and kept 0)" in res.output and rows() == {}
    bad = CliRunner().invoke(cli.cli, ["kalshi-history", "--series", SERIES, "--since", "2026-13-01"])
    assert bad.exit_code == 2 and "REFUSED: --since '2026-13-01' is not a date" in bad.output


# ---- the review's findings (adversarial review of this PR before it opened) ---------------------------------------

def _mk(ticker, sub, result="yes", close="2025-07-05T03:00:00Z"):
    return {"ticker": ticker, "event_ticker": ticker.rsplit("-", 1)[0], "yes_sub_title": sub, "title": f"{sub} wins",
            "result": result, "close_time": close}


EMPTY = {"markets": [], "cursor": ""}


def test_two_events_claiming_one_side_of_one_game_are_all_refused(world):
    """The claims rule is read across events, as one place() call reads it: two clock events of the same pair on the
    same date and one stored game -> every leg refused, "two markets claim one side of one game", kept null."""
    page = {"markets": [_mk("KXZKHGAME-25JUL041310ALPBET-ALP", "Alpha"), _mk("KXZKHGAME-25JUL041310ALPBET-BET", "Beta"),
                        _mk("KXZKHGAME-25JUL041910ALPBET-ALP", "Alpha"), _mk("KXZKHGAME-25JUL041910ALPBET-BET", "Beta")],
            "cursor": ""}
    run, out = go(adapter=FakeKalshi(pages={"historical/markets": [page], "markets": [EMPTY]}))
    got = rows()
    assert len(got) == 4 and all(r["match_id"] is None and r["side"] is None for r in got.values())
    assert all("refused by the matcher: two markets claim one side of one game" in r["notes"] for r in got.values())
    assert run.refused == {"two markets claim one side of one game": 4}
    assert any(ln.startswith(f"  ✗ match {world[2025]} HOME: 2 markets of 2 events claim it") for ln in out)


def test_a_failed_page_stores_nothing_and_the_next_run_places_both_legs(world):
    """A list that does not reach its end is never half-read: page 2 fails, nothing is placed or stored; the next run
    lists it whole and places both legs of the event split across the pages."""
    import requests

    hist = _load("historical_markets_page")["markets"][:2]

    class Failing(FakeKalshi):
        def _get(self, path, params=None):
            if path == "historical/markets" and (params or {}).get("cursor") == "1":
                self.calls.append((path, dict(params)))
                resp = requests.Response()
                resp.status_code = 429
                raise requests.HTTPError(response=resp)
            return super()._get(path, params)
    pages = {"historical/markets": [{"markets": hist[:1], "cursor": "1"}, {"markets": hist[1:], "cursor": ""}],
             "markets": [EMPTY]}
    run, out = go(adapter=Failing(pages=pages))
    assert rows() == {} and run.rows == []
    assert any("historical: page 2 of historical/markets failed (status 429): the list stops here, and nothing is "
               "placed or stored" in ln for ln in out)
    assert "  markets listed: 1 (historical 1, live settled 0)" in out
    go(adapter=FakeKalshi(pages=pages))
    got = rows()
    assert {t: (r["match_id"], r["side"]) for t, r in got.items()} == {
        "KXZKHGAME-25JUL041910ALPBET-ALP": (world[2025], "AWAY"), "KXZKHGAME-25JUL041910ALPBET-BET": (world[2025], "HOME")}


def test_a_cursor_that_comes_back_ends_the_list_short_and_stores_nothing(world):
    hist = _load("historical_markets_page")["markets"]
    fake = FakeKalshi(pages={"historical/markets": [{"markets": hist[:2], "cursor": "1"},
                                                    {"markets": hist[2:], "cursor": "1"}], "markets": [EMPTY]})
    run, out = go(adapter=fake)
    assert rows() == {} and len(fake.calls) == 3          # the cutoff and two pages: the cap is not spent
    assert any("the cursor '1' came back on page 2 of historical/markets" in ln for ln in out)


def test_a_competition_not_in_the_db_refuses_before_any_call(world, monkeypatch):
    from src.walters import venue
    monkeypatch.setitem(venue.KALSHI_SERIES_BY_COMPETITION, "ZKQ", "KXZKQGAME")
    fake = FakeKalshi()
    with pytest.raises(ValueError, match="REFUSED: competition ZKQ .* is not in the DB"):
        kh.run_history("KXZKQGAME", adapter=fake, echo=lambda *_: None, dry_run=True)
    assert fake.calls == []


def test_an_unreadable_timestamp_is_skipped_never_a_crash(world):
    assert kh.parse_ts(1_751_670_300_000_000) is None and kh.parse_ts("2025-13-45T00:00:00Z") is None
    cs = _load("historical_candlesticks")["candlesticks"] + [{"end_period_ts": 1_751_670_300_000_000,
                                                             "yes_bid": {"close": 0.1}, "yes_ask": {"close": 0.2}}]
    st = kh.window_stats(cs, datetime(2025, 7, 4, 23, 15), "historical")
    assert st["last_ts"] == datetime(2025, 7, 4, 23, 5) and st["candles_6h"] == 4


def test_a_window_that_starts_after_close_time_asks_nothing(world):
    page = {"markets": [_mk("KXZKHGAME-25JUL041910ALPBET-ALP", "Alpha", close="2025-07-04T12:00:00Z"),
                        _mk("KXZKHGAME-25JUL041910ALPBET-BET", "Beta", close="2025-07-04T12:00:00Z")], "cursor": ""}
    fake = FakeKalshi(pages={"historical/markets": [page], "markets": [EMPTY]})
    run, out = go(adapter=fake)
    assert not any(p.endswith("/candlesticks") for p, _ in fake.calls)
    r = rows()["KXZKHGAME-25JUL041910ALPBET-ALP"]
    assert r["match_id"] == world[2025] and r["last_ts"] is None
    assert "no candles fetched: the window (kickoff - 6h) starts at or after close_time" in r["notes"]


@pytest.mark.parametrize("status, stored", [(404, True), (400, True), (429, False), (503, False), (408, False)])
def test_a_candle_call_refused_for_good_is_stored_without_a_quote(world, status, stored):
    """A 4xx (not 408 / 429) is stored with no quote and the status in notes, never asked again; any other failure
    stores nothing and the next run asks again."""
    import requests

    class Refusing(FakeKalshi):
        def _get(self, path, params=None):
            if path.endswith("/candlesticks") and "-25JUL041910ALPBET-ALP" in path:
                self.calls.append((path, dict(params)))
                resp = requests.Response()
                resp.status_code = status
                raise requests.HTTPError(response=resp)
            return super()._get(path, params)
    run, out = go(adapter=Refusing())
    got = rows()
    assert ("KXZKHGAME-25JUL041910ALPBET-ALP" in got) is stored and len(got) == 5 + stored
    if stored:
        r = got["KXZKHGAME-25JUL041910ALPBET-ALP"]
        assert r["match_id"] == world[2025] and r["last_ts"] is None and r["candles_6h"] is None
        assert f"candle call refused (status {status}): no quote" in r["notes"]
    assert any(ln.startswith("  ✗ candle calls that failed: 1 (") for ln in out)


def test_the_migration_never_creates_a_database(tmp_path, monkeypatch, capsys):
    """Law 5: with no DB file at the configured path the migration refuses (exit 1) and creates neither the file nor
    its directory."""
    import importlib.util

    from src.walters import venue_quote_age
    missing = tmp_path / "nowhere" / "sports.db"
    monkeypatch.setattr(venue_quote_age, "db_file_path", lambda: missing)   # the configured DB's path, read by it
    spec = importlib.util.spec_from_file_location("mig", Path(__file__).resolve().parents[1]
                                                  / "migrate_kalshi_settled_markets.py")
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    assert mig.main() == 1
    assert f"no DB file at {missing}" in capsys.readouterr().out
    assert not missing.exists() and not missing.parent.exists()
