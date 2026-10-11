"""LEGS OF TWO EVENTS ARE NEVER A PAIR (ARCHITECT 2026-10-10, addendum 37 item 3, RULED):
"A game's Kalshi legs are read as a set only when their tickers name one event and that event's current legs sit
on no other game. Otherwise the row says mismatched and names the events, and nothing is computed from those
legs: no price, no normalized probability, no cost, no venue row, no line move, no close, no order line. Legs with
no stored ticker are read as before."
- "Current legs: for each game and side, the newest stored leg before kickoff, as the readers take it today."
- "One helper, used by every reader of stored legs." This module is that helper. Nothing stored is deleted or
  rewritten: the wrong snapshots stay as history, and the guard is what stops them.

A leg's event is its market ticker without the last '-' segment (KXNCAAFGAME-26OCT10NDSUUNLV-NDSU ->
KXNCAAFGAME-26OCT10NDSUUNLV), Kalshi's own naming. The ticker column (odds_snapshots.market_ticker) is unmapped and
added by migrate_kalshi_ticker.py; before it exists every leg reads as untickered, so the guard answers nothing.

Works on a SQLAlchemy Session (the app's readers) or a raw sqlite3 connection (deploy/hosting/closing.py): the SQL
is plain SQLite, and both sides hand it positional parameters.
"""
from __future__ import annotations

RULING = "legs of two events are never a pair, ARCHITECT 2026-10-10 (addendum 37 item 3)"
GUARD = {"on": True}          # desk_meta / export metadata say the guard is on


def event_of(ticker) -> str | None:
    """The event a market ticker belongs to: the ticker without its last '-' segment. None for no ticker."""
    if not ticker or "-" not in str(ticker):
        return None
    return str(ticker).rsplit("-", 1)[0]


def _events(t) -> set:
    """The events of one side's current leg(s): a ticker, or a set of tickers tied at the newest capture."""
    ts = t if isinstance(t, (set, frozenset, list, tuple)) else [t]
    return {e for e in (event_of(x) for x in ts) if e}


def judge(tickers_by_side: dict, homes_by_event: dict, match_id) -> list[str] | None:
    """Pure. The events of a game's current legs if its legs are mismatched, else None.
    `tickers_by_side` = {selection: ticker | None | set of tickers} (the game's current legs; a set when several
    legs of one side tie at the newest capture, Codex on #414: whichever a reader keeps, all are judged);
    `homes_by_event` = {event: set of match ids whose current legs carry that event}. Untickered legs are read as
    before (they name no event)."""
    events = sorted(set().union(*[_events(t) for t in tickers_by_side.values()]) if tickers_by_side else set())
    if not events:
        return None
    if len(events) > 1:
        return events
    if homes_by_event.get(events[0], set()) - {match_id}:
        return events
    return None


# --------------------------------------------------------------------------------------------------- the DB side --

def _rows(conn, sql: str, params: list) -> list:
    """Run positional-parameter SQLite SQL on a SQLAlchemy Session/Connection or a sqlite3 connection."""
    if hasattr(conn, "exec_driver_sql"):                     # SQLAlchemy Connection
        return list(conn.exec_driver_sql(sql, tuple(params)))
    if hasattr(conn, "connection") and hasattr(conn, "get_bind"):   # SQLAlchemy Session
        return list(conn.connection().exec_driver_sql(sql, tuple(params)))
    return list(conn.execute(sql, params))                   # sqlite3


def has_tickers(conn) -> bool:
    """odds_snapshots.market_ticker exists. Checked on every call, never cached (as has_kalshi_ticker)."""
    try:
        return any(r[1] == "market_ticker" for r in _rows(conn, "PRAGMA table_info(odds_snapshots)", []))
    except Exception:
        return False


def current_tickers(conn, match_ids) -> dict:
    """{match_id: {selection: set of tickers}}: per game and side the newest stored Kalshi leg(s) before kickoff
    (captured_at < the stored kickoff; a game with no kickoff takes the newest). Legs tied at that newest capture
    are all kept (Codex on #414): the readers keep whichever tied row SQLite returns first, so the guard judges
    every one of them. An untickered leg contributes None."""
    ids = sorted({int(i) for i in match_ids if i is not None})
    out: dict = {}
    newest: dict = {}
    for k in range(0, len(ids), 500):
        chunk = ids[k:k + 500]
        sql = ("SELECT s.match_id, s.selection, s.market_ticker, s.captured_at FROM odds_snapshots s "
               "JOIN matches m ON m.id = s.match_id "
               f"WHERE s.source = 'kalshi' AND s.match_id IN ({','.join('?' * len(chunk))}) "
               "AND s.captured_at IS NOT NULL AND (m.utc_date IS NULL OR s.captured_at < m.utc_date) "
               "ORDER BY s.match_id, s.selection, s.captured_at DESC, s.id DESC")
        for mid, sel, tic, cap in _rows(conn, sql, chunk):
            key = (mid, sel)
            if key not in newest:
                newest[key] = cap
            if cap == newest[key]:
                out.setdefault(mid, {}).setdefault(sel, set()).add(tic)
    return out


def homes_of(conn, events) -> dict:
    """{event: set of match ids whose CURRENT legs carry that event}. One scan of the Kalshi rows for all the
    events together (Codex on #414: not one scan per event)."""
    events = sorted(set(e for e in events if e))
    if not events:
        return {}
    mids: set = set()
    for k in range(0, len(events), 200):
        chunk = events[k:k + 200]
        cond = " OR ".join("substr(market_ticker, 1, ?) = ?" for _ in chunk)
        params = [x for ev in chunk for x in (len(ev) + 1, ev + "-")]
        for (mid,) in _rows(conn, "SELECT DISTINCT match_id FROM odds_snapshots WHERE source = 'kalshi' "
                                  f"AND market_ticker IS NOT NULL AND ({cond})", params):
            mids.add(mid)
    homes: dict = {ev: set() for ev in events}
    for mid, legs in current_tickers(conn, mids).items():
        for e in set().union(*[_events(t) for t in legs.values()]):
            if e in homes:
                homes[e].add(mid)
    return homes


def mismatched(conn, match_ids) -> dict:
    """{match_id: [event tickers]} for every game among `match_ids` whose current legs are mismatched (addendum 37
    item 3). {} when the guard is off or before migrate_kalshi_ticker.py (no ticker is stored)."""
    if not GUARD["on"] or not match_ids or not has_tickers(conn):
        return {}
    cur = current_tickers(conn, match_ids)
    homes = homes_of(conn, {e for legs in cur.values() for t in legs.values() for e in _events(t)})
    out = {}
    for mid, legs in cur.items():
        evs = judge(legs, homes, mid)
        if evs:
            out[mid] = evs
    return out


def guard_snaps(snaps, session=None):
    """(snaps, None) for a game whose legs read as a set; ([], events) for a mismatched one. For readers that load
    one game's Kalshi snapshots as ORM rows (the session is taken from the rows when not given). Non-Kalshi rows
    in `snaps` are kept as they are."""
    snaps = list(snaps)
    kal = [x for x in snaps if getattr(x, "source", None) == "kalshi"]
    if not kal:
        return snaps, None
    if session is None:
        from sqlalchemy.orm import object_session
        session = next((object_session(x) for x in kal if object_session(x) is not None), None)
    if session is None:
        return snaps, None
    mids = {x.match_id for x in kal}
    mm = mismatched(session, mids)
    hit = sorted({e for mid in mids for e in mm.get(mid, [])})
    if not hit:
        return snaps, None
    bad = {mid for mid in mids if mid in mm}
    return [x for x in snaps if not (getattr(x, "source", None) == "kalshi" and x.match_id in bad)], hit


def status_block(events: list[str]) -> dict:
    """The export's kalshi block for a mismatched row: status, the events, nothing computed."""
    return {"status": "mismatched", "events": list(events), "rule": RULING}
