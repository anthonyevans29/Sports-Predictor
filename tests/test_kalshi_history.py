"""KALSHI SETTLED-MARKET HISTORY, the ingest (ARCHITECT 2026-10-14, addendum 67 item 1; #519): `kalshi-history` on the
kept payloads of 2026-10-14 11:54Z (tests/fixtures/kalshi_history: the probe's five files, trimmed; see its README)
and a throwaway DB. The kept files are of series KXNFLGAME; the series map points it at a test competition ZKN for the
test, so no other NFL row of the session's DB reaches the matcher. The MLB shape (a clock in the ticker), which the
kept files do not carry, is written in the tests that need it, on a synthetic series KXZKHGAME (competition ZKH)."""
import copy
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner
from sqlalchemy import inspect, select, text

from src.adapters.kalshi import KalshiAdapter
from src.ingestion import kalshi_history as kh
from src.ingestion import kalshi_match as km

FIX = Path(__file__).parent / "fixtures" / "kalshi_history"
NFL, ZKH = "KXNFLGAME", "KXZKHGAME"
NOW = datetime(2026, 10, 14, 12, 0)


def _load(name):
    return json.loads((FIX / f"{name}.json").read_text())


H_TICKER = _load("historical_candlesticks")["ticker"]          # KXNFLGAME-25JUL31LACDET-LAC
L_TICKER = _load("live_candlesticks")["ticker"]                # KXNFLGAME-26OCT12BUFLAR-LAR
H_CURSOR = _load("historical_markets_page")["cursor"]          # each kept page is its list's first, cursor and all
L_CURSOR = _load("settled_markets_page")["cursor"]
END = {"markets": [], "cursor": ""}        # a list's end, written here: the kept files hold each list's first page only


def _leg(page, ticker):
    return next(m for m in _load(page)["markets"] if m["ticker"] == ticker)


def lacdet_page():
    """The listing of the kept historical candle reply's market, written here: that market (the oldest NFL market the
    probe sampled) is older than the kept page (the list's newest 200). Its event's two legs carry the reply's ticker,
    the two names as the kept page spells them (its LACHOU-LAC and DETCIN-DET legs) and a close_time after the reply's
    last candle; no other key."""
    lac = _leg("historical_markets_page", "KXNFLGAME-26AUG13LACHOU-LAC")["yes_sub_title"]
    det = _leg("historical_markets_page", "KXNFLGAME-26AUG13DETCIN-DET")["yes_sub_title"]
    ev = H_TICKER.rsplit("-", 1)[0]
    return {"markets": [{"ticker": f"{ev}-LAC", "event_ticker": ev, "yes_sub_title": lac,
                         "close_time": "2025-08-01T04:00:00Z"},
                        {"ticker": f"{ev}-DET", "event_ticker": ev, "yes_sub_title": det,
                         "close_time": "2025-08-01T04:00:00Z"}], "cursor": ""}


def kept_pages():
    """Each list as the kept files answer it: the kept page first, its cursor answered by the next page."""
    return {"historical/markets": {None: _load("historical_markets_page"), H_CURSOR: lacdet_page()},
            "markets": {None: _load("settled_markets_page"), L_CURSOR: END}}


def _candles(name, path):
    """The kept reply of the shape, for its own market; any other market's reply holds no candle (written here: the
    kept files hold one reply of each shape)."""
    t = path.rsplit("/", 2)[-2]
    reply = _load(name)
    return reply if reply["ticker"] == t else {"candlesticks": [], "ticker": t}


def route(path, params, pages):
    if path == "historical/cutoff":
        return _load("cutoff")
    if path in ("historical/markets", "markets"):
        return pages[path][(params or {}).get("cursor")]
    if path.startswith("historical/markets/") and path.endswith("/candlesticks"):
        return _candles("historical_candlesticks", path)
    if path.startswith("series/") and path.endswith("/candlesticks"):
        return _candles("live_candlesticks", path)
    raise AssertionError(f"unexpected call {path}")


class FakeKalshi(KalshiAdapter):
    def __init__(self, pages=None):
        super().__init__()
        self.pages, self.calls = pages or kept_pages(), []

    def _get(self, path, params=None):
        self.calls.append((path, dict(params or {})))
        return route(path, params, self.pages)


def _world(code, sport, series, games):
    """Competition `code` with its games {key: (away, home, kickoff UTC)}, read for `series`; no stored row of the
    series (the throwaway DB is shared by the session). Returns {key: match id}."""
    from src.db.database import get_engine, init_db, session_scope
    from src.db.schema import Competition, Match, MatchStatus, Team
    init_db()
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == code)).scalar_one_or_none()
        if comp is None:
            comp = Competition(sport=sport, code=code, name=code, area="X", type="LEAGUE")
            names = sorted({n for a, h, _ in games.values() for n in (a, h)})
            teams = {n: Team(sport=sport, name=n) for n in names}
            s.add_all([comp, *teams.values()])
            s.flush()
            for a, h, kick in games.values():
                s.add(Match(sport=sport, competition_id=comp.id, season=str(kick.year), utc_date=kick,
                            status=MatchStatus.FINISHED, home_team_id=teams[h].id, away_team_id=teams[a].id))
    with get_engine().begin() as c:
        c.execute(text("DELETE FROM kalshi_settled_markets WHERE series = :s"), {"s": series})
    with session_scope() as s:
        by_kick = {m.utc_date: m.id for m in
                   s.execute(select(Match).join(Competition).where(Competition.code == code)).scalars()}
    return {k: by_kick[kick] for k, (_, _, kick) in games.items()}


# the kept events' games as the test stores them (the ticker's away team first): kickoffs on the ticker's US Eastern
# day. DETCIN (historical) and DETARI (live) have no stored game: the matcher refuses them.
NFL_GAMES = {
    "LACDET": ("Los Angeles Chargers", "Detroit Lions", datetime(2025, 8, 1, 0, 0)),          # 8 pm ET, 07-31
    "LACHOU": ("Los Angeles Chargers", "Houston Texans", datetime(2026, 8, 14, 0, 0)),
    "INDNE": ("Indianapolis Colts", "New England Patriots", datetime(2026, 8, 13, 23, 30)),
    "BUFLAR": ("Buffalo Bills", "Los Angeles Rams", datetime(2026, 10, 13, 0, 15)),           # 8:15 pm ET, 10-12
    "NYGWAS": ("New York Giants", "Washington Commanders", datetime(2026, 10, 11, 17, 0)),
}


@pytest.fixture
def nfl(monkeypatch):
    from src.db.schema import Sport
    from src.walters import venue
    monkeypatch.delitem(venue.KALSHI_SERIES_BY_COMPETITION, "NFL")
    monkeypatch.setitem(venue.KALSHI_SERIES_BY_COMPETITION, "ZKN", NFL)
    return _world("ZKN", Sport.NFL, NFL, NFL_GAMES)


@pytest.fixture
def zkh(monkeypatch):
    """Alpha Owls @ Beta Bears on 2025-07-04 23:15Z: a clock ticker of 19:10 ET (23:10Z) reads the stored kickoff."""
    from src.db.schema import Sport
    from src.walters import venue
    monkeypatch.setitem(venue.KALSHI_SERIES_BY_COMPETITION, "ZKH", ZKH)
    return _world("ZKH", Sport.MLB, ZKH, {"ALPBET": ("Alpha Owls", "Beta Bears", datetime(2025, 7, 4, 23, 15))})


def rows(series=NFL):
    from src.db.database import session_scope
    from src.db.schema import KalshiSettledMarket
    with session_scope() as s:
        return {r.ticker: {c: getattr(r, c) for c in KalshiSettledMarket.__table__.c.keys()}
                for r in s.execute(select(KalshiSettledMarket).where(KalshiSettledMarket.series == series)).scalars()}


def _ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def go(series=NFL, **kw):
    out = []
    kw.setdefault("adapter", FakeKalshi())
    run = kh.run_history(series, echo=out.append, now=NOW, **kw)
    return run, out


REFUSED = {"KXNFLGAME-26AUG13DETCIN-DET", "KXNFLGAME-26AUG13DETCIN-CIN",
           "KXNFLGAME-26OCT11DETARI-DET", "KXNFLGAME-26OCT11DETARI-ARI"}
TIES = ("KXNFLGAME-26AUG13INDNE-NE", "KXNFLGAME-26AUG13INDNE-IND",
        "KXNFLGAME-26OCT11NYGWAS-WAS", "KXNFLGAME-26OCT11NYGWAS-NYG")


# ---- the kept payloads ---------------------------------------------------------------------------------------------

def test_every_key_is_read_from_the_kept_files():
    """Law 1, KEYS checked against the kept files (addendum 68 item 5), settled_time's included (settlement_ts): every
    market of both kept pages carries every market key, the cutoff file its key, each candle reply its list and end
    keys, and every candle its own shape's bid and ask leaf, never the other shape's."""
    K = kh.KEYS
    assert K["settled_time"] == "settlement_ts"
    assert kh.parse_ts(_load("cutoff")[K["cutoff"]]) == datetime(2026, 8, 15)
    for page in ("historical_markets_page", "settled_markets_page"):
        p = _load(page)
        assert len(p[K["list"]]) == 6 and p[K["cursor"]]
        for m in p[K["list"]]:
            for k in ("ticker", "event", "yes_sub_title", "result", "close_time", "settled_time"):
                assert m.get(K[k]) not in (None, ""), (page, m.get("ticker"), k)
            assert kh.parse_ts(m[K["close_time"]]) and kh.parse_ts(m[K["settled_time"]])
    for name, shape, other in (("historical_candlesticks", "historical", "live"),
                               ("live_candlesticks", "live", "historical")):
        cs = _load(name)[K["candles"]]
        assert cs and all(isinstance(c[K["end"]], int) for c in cs)
        assert all(None not in kh.bid_ask(c, shape) for c in cs)               # every kept candle two-sided
        assert all(kh.bid_ask(c, other) == (None, None) for c in cs)           # and read by its own keys only


def test_a_stored_row_reads_each_shape_by_its_own_keys(nfl):
    """Historical: yes_bid.close / yes_ask.close; live: yes_bid.close_dollars / yes_ask.close_dollars, each from its
    own endpoint, the window starting six hours before the stored kickoff and ending at close_time. The last two-sided
    candle at or before kickoff is the quote; an in-play candle never is."""
    fake = FakeKalshi()
    run, out = go(adapter=fake)
    got = rows()
    h = got[H_TICKER]
    assert (h["source"], h["match_id"], h["side"], h["kalshi_result"]) == ("historical", nfl["LACDET"], "AWAY", None)
    assert h["last_ts"] == datetime(2025, 8, 1, 0, 0) and (h["last_bid"], h["last_ask"]) == (0.45, 0.46)
    assert h["last_mid"] == pytest.approx(0.455)
    # (18:00, 00:00]: the kept reply starts at 21:56, with minutes missing here and there
    assert (h["candles_6h"], h["candles_two_sided"], h["gaps"]) == (107, 107, 253)
    assert got[H_TICKER.replace("-LAC", "-DET")]["side"] == "HOME"
    lv = got[L_TICKER]
    assert (lv["source"], lv["match_id"], lv["side"], lv["kalshi_result"]) == ("live", nfl["BUFLAR"], "HOME", "no")
    assert lv["close_time"] == datetime(2026, 10, 13, 3, 48, 50)
    assert lv["settled_time"] == datetime(2026, 10, 13, 3, 53, 55, 667276)
    assert lv["last_ts"] == datetime(2026, 10, 13, 0, 15) and (lv["last_bid"], lv["last_ask"]) == (0.61, 0.62)
    assert lv["last_mid"] == pytest.approx(0.615)
    assert (lv["candles_6h"], lv["candles_two_sided"], lv["gaps"]) == (147, 147, 213)
    candle_calls = {p: q for p, q in fake.calls if p.endswith("/candlesticks")}
    assert candle_calls[f"historical/markets/{H_TICKER}/candlesticks"]["start_ts"] == _ts(datetime(2025, 7, 31, 18))
    assert candle_calls[f"series/{NFL}/markets/{L_TICKER}/candlesticks"] == {
        "start_ts": _ts(datetime(2026, 10, 12, 18, 15)), "end_ts": _ts(datetime(2026, 10, 13, 3, 48, 50)),
        "period_interval": 1}
    # each list is paged by its kept cursor
    assert [q.get("cursor") for p, q in fake.calls if p == "historical/markets"] == [None, H_CURSOR]
    assert [q.get("cursor") for p, q in fake.calls if p == "markets"] == [None, L_CURSOR]
    assert all(r["fetched_at"] == NOW for r in got.values())
    assert "  cutoff market_settled_ts: 2026-08-15T00:00:00Z" in out
    assert "  stored: 14 (placed on a stored game 10, refused and kept 4) · already stored 0" in out


def test_a_null_price_minute_stays_null(nfl):
    """A zero-volume minute carries a null price with bid and ask present (the kept historical reply holds them): it
    is two-sided, and the price is never read or filled; the first candle is kept as sent. A minute with no ask (none
    in the kept files: one is written here from a kept candle) is one-sided, and nothing fills it."""
    go()
    h = rows()[H_TICKER]
    kept = _load("historical_candlesticks")["candlesticks"]
    assert h["raw_first_candle"] == kept[0]
    null_price = [c for c in kept if c["price"]["close"] is None]
    assert null_price and all(c["volume"] == "0.00" for c in null_price)
    assert all(kh.bid_ask(c, "historical") == (float(c["yes_bid"]["close"]), float(c["yes_ask"]["close"]))
               for c in null_price)
    assert h["candles_two_sided"] == h["candles_6h"]
    live = copy.deepcopy(_load("live_candlesticks")["candlesticks"])
    at_kick = next(c for c in live if c["end_period_ts"] == _ts(datetime(2026, 10, 13, 0, 15)))
    at_kick["yes_ask"]["close_dollars"] = None
    assert kh.bid_ask(at_kick, "live") == (0.61, None)
    st = kh.window_stats(live, datetime(2026, 10, 13, 0, 15), "live")
    assert st["last_ts"] == datetime(2026, 10, 13, 0, 14) and st["candles_two_sided"] == 146    # not filled from it


def test_a_tied_game_is_kept_with_its_result_as_read(nfl):
    """A tie settles both legs as "scalar" (0.50) in the kept pages: kalshi_result stays null (the table holds 'yes',
    'no' or null) and notes carries the result as read; the game is still placed."""
    go()
    got = rows()
    for t in TIES:
        assert got[t]["kalshi_result"] is None and got[t]["match_id"] is not None
        assert "result as read: 'scalar'" in got[t]["notes"]
    assert got["KXNFLGAME-26OCT12BUFLAR-BUF"]["kalshi_result"] == "yes"


def test_an_unmatched_market_stores_match_id_null_with_its_reason(nfl):
    """Refused rows are kept, never guessed: match_id and side null, the matcher's reason in notes, listed by reason
    at the end of the run. An NFL ticker carries no clock, so no candle is fetched for them and notes says so."""
    fake = FakeKalshi()
    run, out = go(adapter=fake)
    got = rows()
    for t in REFUSED:
        assert got[t]["match_id"] is None and got[t]["side"] is None and got[t]["candles_6h"] is None
        assert got[t]["notes"].startswith(f"refused by the matcher: {km.NO_FIT}")
        assert "no candles fetched: unmatched and the ticker carries no clock" in got[t]["notes"]
        assert not any(t in p for p, _ in fake.calls)
    assert run.refused == {km.NO_FIT: 4}
    i = out.index("  refused by the matcher, by reason (kept with match_id null):")
    assert out[i + 1] == f"        4  {km.NO_FIT}"


def test_the_cap_stops_the_run_prints_where_and_the_next_run_resumes(nfl):
    """Six calls: the cutoff, two pages of each list, and the candles of the first placed market. The run stores what
    it holds and prints where it stopped; the next run skips the stored rows and places the rest: the matcher reads
    every listed leg in range, stored or not, so an event is never matched on part of it."""
    run, out = go(max_calls=6)
    first = rows()
    assert set(first) == {"KXNFLGAME-26AUG13LACHOU-LAC"}
    assert out[-1] == ("  STOPPED at the cap (6 calls) before the candles of KXNFLGAME-26AUG13LACHOU-HOU "
                       "(historical); 13 market(s) left for the next run, which skips the stored ones")
    run2, out2 = go()
    assert run2.already == 1 and len(rows()) == 14
    hou = rows()["KXNFLGAME-26AUG13LACHOU-HOU"]
    assert (hou["match_id"], hou["side"]) == (nfl["LACHOU"], "HOME")
    assert run2.refused == {km.NO_FIT: 4} and not run2.stopped


def test_the_cap_inside_a_list_stores_nothing_and_prints_the_cursor(nfl):
    """A list cut short is never half-read: nothing is placed or stored, and the run names the list and the kept
    cursor it stopped at."""
    run, out = go(max_calls=2)
    assert rows() == {} and run.rows == []
    assert out[-1] == (f"  STOPPED at the cap (2 calls) while listing historical (historical/markets), before page 2 "
                       f"at cursor {H_CURSOR}; nothing is placed or stored from a list cut short (a larger "
                       "--max-calls lists it whole)")


def test_dry_run_writes_nothing_and_prints_what_would_be_stored(nfl):
    from src.db.database import get_engine
    eng = get_engine()

    def counts():
        with eng.connect() as c:
            return {t: c.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar()
                    for t in inspect(eng).get_table_names()}
    before = counts()
    run, out = go(dry_run=True)
    assert counts() == before and rows() == {}
    assert "  would be stored: 14 (placed on a stored game 10, refused and kept 4) · already stored 0" in out
    assert any(ln.startswith(f"    {L_TICKER} · live · match ") and "bid 0.61 ask 0.62" in ln for ln in out)


def test_a_run_writes_its_one_table_and_nothing_else(nfl):
    from src.db.database import get_engine
    eng = get_engine()

    def counts():
        with eng.connect() as c:
            return {t: c.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar()
                    for t in inspect(eng).get_table_names() if t != kh.TABLE}
    before = counts()
    go()
    assert counts() == before and len(rows()) == 14


def test_since_and_until_keep_the_markets_of_their_game_days(nfl):
    run, out = go(since=date(2026, 10, 1))
    assert {t.split("-")[1] for t in rows()} == {"26OCT12BUFLAR", "26OCT11NYGWAS", "26OCT11DETARI"}
    assert run.out_of_range == 8
    go(until=date(2025, 12, 31))
    assert H_TICKER in rows() and "KXNFLGAME-26AUG13LACHOU-LAC" not in rows()


def test_the_command_runs_dry_and_refuses_a_bad_date(nfl, monkeypatch):
    import cli
    pages = kept_pages()
    monkeypatch.setattr(KalshiAdapter, "_get", lambda self, path, params=None: route(path, params, pages))
    res = CliRunner().invoke(cli.cli, ["kalshi-history", "--series", NFL, "--dry-run", "--since", "2026-10-12"])
    assert res.exit_code == 0, res.output
    assert "cutoff market_settled_ts: 2026-08-15T00:00:00Z" in res.output
    assert "would be stored: 2 (placed on a stored game 2, refused and kept 0)" in res.output and rows() == {}
    bad = CliRunner().invoke(cli.cli, ["kalshi-history", "--series", NFL, "--since", "2026-13-01"])
    assert bad.exit_code == 2 and "REFUSED: --since '2026-13-01' is not a date" in bad.output


def test_a_failed_page_stores_nothing_and_the_next_run_places_both_legs(nfl):
    """A list that does not reach its end is never half-read: the page the kept cursor asks for fails, nothing is
    placed or stored; the next run lists it whole and places both legs of its event."""
    import requests

    class Failing(FakeKalshi):
        def _get(self, path, params=None):
            if path == "historical/markets" and (params or {}).get("cursor") == H_CURSOR:
                self.calls.append((path, dict(params)))
                resp = requests.Response()
                resp.status_code = 429
                raise requests.HTTPError(response=resp)
            return super()._get(path, params)
    run, out = go(adapter=Failing())
    assert rows() == {} and run.rows == []
    assert any("historical: page 2 of historical/markets failed (status 429): the list stops here, and nothing is "
               "placed or stored" in ln for ln in out)
    assert "  markets listed: 6 (historical 6, live settled 0)" in out
    go()
    got = rows()
    assert (got[H_TICKER]["match_id"], got[H_TICKER]["side"]) == (nfl["LACDET"], "AWAY")
    assert got[H_TICKER.replace("-LAC", "-DET")]["side"] == "HOME"


def test_a_cursor_that_comes_back_ends_the_list_short_and_stores_nothing(nfl):
    pages = kept_pages()
    pages["historical/markets"][H_CURSOR] = {"markets": [], "cursor": H_CURSOR}
    fake = FakeKalshi(pages=pages)
    run, out = go(adapter=fake)
    assert rows() == {} and len(fake.calls) == 3          # the cutoff and two pages: the cap is not spent
    assert any(f"the cursor {H_CURSOR!r} came back on page 2 of historical/markets" in ln for ln in out)


@pytest.mark.parametrize("status, stored", [(404, True), (400, True), (429, False), (503, False), (408, False)])
def test_a_candle_call_refused_for_good_is_stored_without_a_quote(nfl, status, stored):
    """A 4xx (not 408 / 429) is stored with no quote and the status in notes, never asked again; any other failure
    stores nothing and the next run asks again."""
    import requests

    class Refusing(FakeKalshi):
        def _get(self, path, params=None):
            if path.endswith("/candlesticks") and L_TICKER in path:
                self.calls.append((path, dict(params)))
                resp = requests.Response()
                resp.status_code = status
                raise requests.HTTPError(response=resp)
            return super()._get(path, params)
    run, out = go(adapter=Refusing())
    got = rows()
    assert (L_TICKER in got) is stored and len(got) == 13 + stored
    if stored:
        r = got[L_TICKER]
        assert r["match_id"] == nfl["BUFLAR"] and r["last_ts"] is None and r["candles_6h"] is None
        assert f"candle call refused (status {status}): no quote" in r["notes"]
    assert any(ln.startswith("  ✗ candle calls that failed: 1 (") for ln in out)


def test_an_unreadable_timestamp_is_skipped_never_a_crash():
    assert kh.parse_ts(1_751_670_300_000_000) is None and kh.parse_ts("2025-13-45T00:00:00Z") is None
    cs = _load("historical_candlesticks")["candlesticks"] + [{"end_period_ts": 1_751_670_300_000_000,
                                                             "yes_bid": {"close": 0.1}, "yes_ask": {"close": 0.2}}]
    st = kh.window_stats(cs, datetime(2025, 8, 1, 0, 0), "historical")
    assert st["last_ts"] == datetime(2025, 8, 1, 0, 0) and st["candles_6h"] == 107


# ---- the MLB shape (a clock in the ticker), written here: the kept files are NFL --------------------------------------

def _mk(ticker, sub, result="yes", close="2025-07-05T03:00:00Z"):
    return {"ticker": ticker, "event_ticker": ticker.rsplit("-", 1)[0], "yes_sub_title": sub, "title": f"{sub} wins",
            "result": result, "close_time": close}


def _one_page(*markets):
    return {"historical/markets": {None: {"markets": list(markets), "cursor": ""}}, "markets": {None: END}}


def test_the_window_reads_the_stored_kickoff_not_the_ticker_clock(zkh):
    """Matched: the window is the stored kickoff's (23:15Z), not the ticker clock's (19:10 ET = 23:10Z)."""
    fake = FakeKalshi(pages=_one_page(_mk("KXZKHGAME-25JUL041910ALPBET-ALP", "Alpha"),
                                      _mk("KXZKHGAME-25JUL041910ALPBET-BET", "Beta")))
    go(ZKH, adapter=fake)
    got = rows(ZKH)
    assert {t: (r["match_id"], r["side"]) for t, r in got.items()} == {
        "KXZKHGAME-25JUL041910ALPBET-ALP": (zkh["ALPBET"], "AWAY"), "KXZKHGAME-25JUL041910ALPBET-BET": (zkh["ALPBET"], "HOME")}
    starts = {q["start_ts"] for p, q in fake.calls if p.endswith("/candlesticks")}
    assert starts == {_ts(datetime(2025, 7, 4, 17, 15))}
    assert all("no two-sided candle at or before kickoff" in r["notes"] for r in got.values())


def test_an_unmatched_clock_market_fetches_its_candles_on_the_ticker_clock(zkh):
    """Unmatched with a clock: kept with match_id null and its reason, its candles fetched on the ticker's time."""
    close = "2025-07-06T03:30:00Z"
    fake = FakeKalshi(pages=_one_page(_mk("KXZKHGAME-25JUL052005GAMDEL-GAM", "Gamma", close=close),
                                      _mk("KXZKHGAME-25JUL052005GAMDEL-DEL", "Delta", result="no", close=close)))
    run, out = go(ZKH, adapter=fake)
    start = {p.rsplit("/", 2)[-2]: q["start_ts"] for p, q in fake.calls if p.endswith("/candlesticks")}
    for t in ("KXZKHGAME-25JUL052005GAMDEL-GAM", "KXZKHGAME-25JUL052005GAMDEL-DEL"):
        r = rows(ZKH)[t]
        assert r["match_id"] is None and r["side"] is None
        assert r["notes"].startswith(f"refused by the matcher: {km.NO_FIT}")
        # 20:05 ET on 07-05 = 00:05Z on 07-06, less six hours
        assert start[t] == _ts(datetime(2025, 7, 5, 18, 5)) and r["candles_6h"] == 0
    assert run.refused == {km.NO_FIT: 2}


def test_two_events_claiming_one_side_of_one_game_are_all_refused(zkh):
    """The claims rule is read across events, as one place() call reads it: two clock events of the same pair on the
    same date and one stored game -> every leg refused, "two markets claim one side of one game", kept null."""
    fake = FakeKalshi(pages=_one_page(
        _mk("KXZKHGAME-25JUL041310ALPBET-ALP", "Alpha"), _mk("KXZKHGAME-25JUL041310ALPBET-BET", "Beta"),
        _mk("KXZKHGAME-25JUL041910ALPBET-ALP", "Alpha"), _mk("KXZKHGAME-25JUL041910ALPBET-BET", "Beta")))
    run, out = go(ZKH, adapter=fake)
    got = rows(ZKH)
    assert len(got) == 4 and all(r["match_id"] is None and r["side"] is None for r in got.values())
    assert all(f"refused by the matcher: {km.TWO_CLAIMS}" in r["notes"] for r in got.values())
    assert run.refused == {km.TWO_CLAIMS: 4}
    assert any(ln.startswith(f"  ✗ match {zkh['ALPBET']} HOME: 2 markets of 2 events claim it") for ln in out)


def test_a_window_that_starts_after_close_time_asks_nothing(zkh):
    fake = FakeKalshi(pages=_one_page(_mk("KXZKHGAME-25JUL041910ALPBET-ALP", "Alpha", close="2025-07-04T12:00:00Z"),
                                      _mk("KXZKHGAME-25JUL041910ALPBET-BET", "Beta", close="2025-07-04T12:00:00Z")))
    go(ZKH, adapter=fake)
    assert not any(p.endswith("/candlesticks") for p, _ in fake.calls)
    r = rows(ZKH)["KXZKHGAME-25JUL041910ALPBET-ALP"]
    assert r["match_id"] == zkh["ALPBET"] and r["last_ts"] is None
    assert "no candles fetched: the window (kickoff - 6h) starts at or after close_time" in r["notes"]


# ---- refusals before any call ----------------------------------------------------------------------------------------

def test_a_series_the_syncs_do_not_read_is_refused(nfl):
    with pytest.raises(ValueError, match="REFUSED: KXNOPEGAME is not a series the syncs read"):
        kh.run_history("KXNOPEGAME", adapter=FakeKalshi(), echo=lambda *_: None)


def test_a_competition_not_in_the_db_refuses_before_any_call(nfl, monkeypatch):
    from src.walters import venue
    monkeypatch.setitem(venue.KALSHI_SERIES_BY_COMPETITION, "ZKQ", "KXZKQGAME")
    fake = FakeKalshi()
    with pytest.raises(ValueError, match="REFUSED: competition ZKQ .* is not in the DB"):
        kh.run_history("KXZKQGAME", adapter=fake, echo=lambda *_: None, dry_run=True)
    assert fake.calls == []


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
