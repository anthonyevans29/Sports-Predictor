"""
THE TENNIS CAPTURE: KXATPMATCH / KXWTAMATCH open markets placed on the stored tennis rows and stored as
OddsSnapshot(source="kalshi", market="ML", HOME / AWAY), as every two-way series is (ARCHITECT 2026-11-05, addendum
261 item 0: "the hourly capture tier"; 261 item 2(c): "the player-name matcher with the ambiguity sentinel"; 2026-11-06,
addendum 269 item 3(a): "the matcher on yes_sub_title with the ambiguity sentinel [...] the adapter stores the full
name as served and matches on it"; lane tennis-market-only, #838).

How it reads, and where it differs from the NBA's `sync-kalshi-nba` (kalshi_sync.sync_kalshi_mlb):
- THE READ pages the series' open markets TO THE LAST PAGE with the adapter's own reader (kalshi_tennis.read_all):
  269 item 3(d), "the adapter pages to the last page always: a cursor left is a refusal, never a partial count". The
  shared path's open_markets_for_series stops quietly at its page guard, so it is not used here; a paging refusal
  stores nothing and answers with its reason.
- THE PLACEMENT is the shared matcher's, unchanged (kalshi_match.place: the event's two names from its own markets'
  yes_sub_title, the ticker's day, the run's window, in play on our kickoff, every refusal counted by its reason).
- THEN THE PLAYER CHECK, tennis's own sentinel, on every market the shared matcher placed (269 item 3(a)): the
  fixture IS the event (kalshi_tennis: the row's external id is the event ticker), so a market is kept only when its
  own event_ticker is that row's, and its yes_sub_title names EXACTLY ONE of the row's two players, the one on the
  side it was placed on (the full name as served, compared case-folded: addendum 238 item 2(b)). A yes_sub_title naming
  neither player is refused (PLAYER_NEITHER); naming both (two players stored under one name) is refused
  (PLAYER_BOTH); naming the other side's player is refused (PLAYER_SIDE); another event's row, refused (EVENT_OTHER).
  Never a guess: a refused market is counted and printed, never stored.
- THEN THE KICKOFF CHECK (ARCHITECT 2026-11-08, addendum 288 item 1: "absent on all four → the row is stored with the
  conservative UTC+14 instant AND the label START_UNREAD, so it is never captured and the receipt counts it"): a market
  that passed the player check is kept only when its row's stored kickoff source (external_ids["kalshi_kickoff"],
  written by the ingestion service from kalshi_tennis on every sync) is a served key, occurrence_datetime or
  expected_expiration_time. A START_UNREAD row is refused (START_UNREAD_ROW); a row carrying no kickoff source at all
  (written before this rule) is refused too (KICKOFF_SOURCE_MISSING) until a sync re-reads it. Counted and printed,
  never stored.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from src.adapters import kalshi_tennis as kt
from src.adapters.kalshi import KalshiAdapter
from src.db.database import session_scope
from src.db.schema import Competition
from src.ingestion import kalshi_match as km
from src.ingestion import kalshi_sync as ks
from src.timeutil import utc_now_naive

PLAYER_NEITHER = "the market's yes_sub_title names neither player of the row"
PLAYER_BOTH = "the market's yes_sub_title names both players of the row"
PLAYER_SIDE = "the market's yes_sub_title names the other side's player"
EVENT_OTHER = "the row is another event's (its event ticker differs)"
START_UNREAD_ROW = "the row's kickoff is START_UNREAD (no start served; addendum 288 item 1): never captured"
KICKOFF_SOURCE_MISSING = "the row carries no kickoff source (stored before addendum 288 item 1): never captured"
CAPTURED_SOURCES = (kt.OCCURRENCE_KEY, kt.EXPIRATION_KEY)        # the served kickoff sources a captured row carries


def player_check(res: km.Result, games: list) -> km.Result:
    """The tennis sentinel over km.place's placements (module docstring). Refusals move a placement to res.refused
    by reason (res.why names the ticker); nothing is ever moved to another side or row."""
    by_id = {g.id: g for g in games}
    keep = {}
    for (mid, side), mk in res.placed.items():
        g = by_id.get(mid)
        yes = kt.name_of(mk).casefold()
        home = (g.home_team.name or "").casefold() if g is not None else ""
        away = (g.away_team.name or "").casefold() if g is not None else ""
        ext = (getattr(g, "external_ids", None) or {}) if g is not None else {}
        why = None
        if g is None or str(ext.get(kt.SOURCE) or "") != str(mk.get("event_ticker") or ""):
            why = EVENT_OTHER
        elif yes == home and yes == away:
            why = PLAYER_BOTH
        elif yes not in (home, away):
            why = PLAYER_NEITHER
        elif yes != (home if side == "HOME" else away):
            why = PLAYER_SIDE
        if why:
            res.refused[why] += 1
            res.why[mk.get("ticker")] = why
        else:
            keep[(mid, side)] = mk
    res.placed = keep
    return res


def kickoff_check(res: km.Result, games: list) -> km.Result:
    """The START_UNREAD refusal over the placements left by player_check (module docstring): a placement is kept only
    when its row's stored kickoff source (external_ids[kalshi_tennis.KICKOFF_EXT_KEY]) is one of CAPTURED_SOURCES.
    Refusals move a placement to res.refused by reason; nothing is ever moved to another side or row."""
    by_id = {g.id: g for g in games}
    keep = {}
    for (mid, side), mk in res.placed.items():
        g = by_id.get(mid)
        src = ((getattr(g, "external_ids", None) or {}) if g is not None else {}).get(kt.KICKOFF_EXT_KEY)
        why = None
        if src is None:
            why = KICKOFF_SOURCE_MISSING
        elif src not in CAPTURED_SOURCES:
            why = START_UNREAD_ROW
        if why:
            res.refused[why] += 1
            res.why[mk.get("ticker")] = why
        else:
            keep[(mid, side)] = mk
    res.placed = keep
    return res


def sync_kalshi_tennis(competition_code: str, date_from=None, date_to=None, progress=None, get=None) -> dict:
    """Pull the tour's open markets (to the last page), place them with the shared matcher on the stored rows of the
    tour's competition, apply the player check and the kickoff check, store each placed side as
    OddsSnapshot(source="kalshi", market="ML").
    Returns a summary dict ({"ok": False, "reason"} on a refusal). `get` is the HTTP layer (tests)."""
    def report(m):
        if progress:
            progress(m)

    code = competition_code.upper()
    series = kt.SERIES.get(code)
    if series is None:
        return {"ok": False, "reason": f"{code} is not a tennis tour ({', '.join(kt.SERIES)})"}
    adapter = KalshiAdapter()
    get = get or adapter._get
    report("Checking Kalshi status…")
    try:
        st = get("exchange/status", {})
    except Exception as e:                     # noqa: BLE001 - reported, as the shared path's status read
        return {"ok": False, "series": series, "reason": f"status read failed: {type(e).__name__}: {e}"}
    if not (st or {}).get("trading_active", False):
        report("Note: Kalshi trading not currently active (prices may be stale/closed).")
    report(f"  fetching {series} open markets to the last page…")
    try:
        markets, pages = kt.read_all(get, series, "open")
    except kt.Refused as e:
        return {"ok": False, "series": series, "reason": str(e)}
    if not markets:
        return {"ok": False, "series": series, "reason": f"no open markets in {series}"}
    report(f"  {len(markets)} open markets ({pages} page(s))")
    def ours(m):
        return str(m.get("event_ticker") or "").startswith(f"{series}-")
    outside = sum(1 for m in markets if not ours(m))         # never placed: the two tour series only (269 3(f))
    markets = [m for m in markets if ours(m)]
    now = utc_now_naive()                       # stamped after the fetch, as the shared path stamps it
    lo = date_from or (now - timedelta(days=1))
    hi = date_to or (now + timedelta(days=2))
    with session_scope() as sess:
        comp = sess.execute(select(Competition).where(Competition.code == code)).scalar_one_or_none()
        if comp is None:
            return {"ok": False, "series": series, "reason": f"competition {code} not in DB"}
        games = ks.stored_games(sess, [comp.id], markets)
        report(f"  {len(games)} stored {code} rows on the events' days")
        res = km.place(markets, games, now=now, lo=lo, hi=hi, implied_prob=KalshiAdapter.implied_prob)
        res = player_check(res, games)
        res = kickoff_check(res, games)           # addendum 288 item 1: a START_UNREAD row is never captured
        if outside:
            res.refused[kt.OUTSIDE_SERIES] += outside
        for ln in km.console_lines(res):
            report(ln)
        stored = ks._store(sess, res, now=now, market="ML", implied_prob=KalshiAdapter.implied_prob,
                           yes_quotes=KalshiAdapter.yes_quotes)
        alarm = ks._alarm(sess, [comp.id], res, markets, now, lo, hi, report)
    counts = km.legacy_counts(res)
    return {"ok": True, "series": series, "markets": len(markets), **counts, "stored": stored, "alarm": alarm,
            "pages": pages}
