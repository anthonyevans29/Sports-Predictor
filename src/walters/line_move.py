"""
LINE-MOVE ALARM (architect ruling 2026-09-29, after the Week 4 MNF QB audit:
Williams was absent from the provider's injury report at both pre-game
syncs. The injury feed lags, but the market doesn't).

Snapshot-based, NO provider calls: it reads the odds_snapshots already
stored, the NFL book consensus that sync-odds-football appends and the
Kalshi captures (MLB's capture-odds book rows count as well). Inside T-3h
before kickoff, a move of >= 6pp in the home probability on EITHER venue
marks the row "late-news?".
- The window card and the NFL export carry that flag.
- sp_window_page pages it on the card topic and requests freshen:<family>.

The move per venue is the net move, latest pre-kickoff capture minus a
reference. The reference is the venue's price as of T-3h (its last capture
at or before kickoff - 3h), or, when it has none by then, its first capture
inside T-3h. The move is only evaluated while now is inside [kickoff - 3h,
kickoff). In-play captures never count.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

LINE_MOVE_PP = 6.0
LINE_MOVE_WINDOW_H = 3
LATE_NEWS_FLAG = "late-news?"


def _series(snaps, venue: str, kickoff: datetime, now: datetime,
            three_way: bool = False) -> list[tuple[datetime, float]]:
    """[(captured_at, P(home))] for one venue, ascending, pre-kickoff and
    <= now. Book: home de-vig normalized over that capture's selections.
    Kalshi: sides are stored separately, so each capture time uses the
    latest price per side as of then, normalized over the full outcome set
    (HOME+AWAY; soccer: HOME+DRAW+AWAY — CORRECTION #117, 2026-09-30), and
    only once every leg exists."""
    rows = [x for x in snaps
            if x.captured_at is not None and x.captured_at < kickoff and x.captured_at <= now
            and ((x.source == "kalshi") == (venue == "kalshi"))
            and (venue == "kalshi" or x.market == "1X2")]
    out: list[tuple[datetime, float]] = []
    if venue == "book":
        by_t: dict[datetime, dict[str, float]] = {}
        for x in rows:
            by_t.setdefault(x.captured_at, {})[x.selection] = x.devig_prob
        for t in sorted(by_t):
            tot = sum(v for v in by_t[t].values() if v is not None)
            h = by_t[t].get("HOME")
            if h is not None and tot > 0:
                out.append((t, h / tot))
        return out
    legs = {"HOME", "DRAW", "AWAY"} if three_way else {"HOME", "AWAY"}
    latest: dict[str, float] = {}
    for t in sorted({x.captured_at for x in rows}):
        for x in rows:
            if x.captured_at == t and x.selection in legs and x.devig_prob is not None:
                latest[x.selection] = x.devig_prob
        tot = sum(latest.values())
        if set(latest) == legs and tot > 0:
            out.append((t, latest["HOME"] / tot))
    return out


def line_move(snaps, kickoff: datetime, now: datetime,
              threshold_pp: float = LINE_MOVE_PP, window_h: int = LINE_MOVE_WINDOW_H,
              three_way: bool = False) -> dict | None:
    """None outside [kickoff - window_h, kickoff). Else {"flag", "venues"}.
    Each venue with >= 2 points reports {from, to, move_pp, from_at, to_at,
    alarm}; flag = LATE_NEWS_FLAG when any venue's |move| >= threshold."""
    if kickoff is None or not (kickoff - timedelta(hours=window_h) <= now < kickoff):
        return None
    start = kickoff - timedelta(hours=window_h)
    snaps = list(snaps)
    venues = {}
    for venue in ("book", "kalshi"):
        ser = _series(snaps, venue, kickoff, now, three_way=three_way)
        before = [p for p in ser if p[0] <= start]
        inside = [p for p in ser if p[0] > start]
        ref = before[-1] if before else (inside[0] if inside else None)
        cur = ser[-1] if ser else None
        if ref is None or cur is None or cur[0] <= ref[0]:
            continue
        mv = round((cur[1] - ref[1]) * 100, 1)
        venues[venue] = {"from": round(ref[1], 4), "to": round(cur[1], 4), "move_pp": mv,
                         "from_at": ref[0].isoformat(), "to_at": cur[0].isoformat(),
                         "alarm": abs(mv) >= threshold_pp}
        if venue == "book":
            # SOURCE TIME (ARCHITECT 2026-10-09, addendum 32 item 4): beside each book
            # capture time, the provider's own update time of that capture's
            # snapshots (the oldest where they differ; null = unknown, never fresh)
            venues[venue]["from_source_updated_at"] = _book_source_time(snaps, ref[0])
            venues[venue]["to_source_updated_at"] = _book_source_time(snaps, cur[0])
    return {"flag": LATE_NEWS_FLAG if any(v["alarm"] for v in venues.values()) else None,
            "threshold_pp": threshold_pp, "window_h": window_h, "venues": venues}


def _book_source_time(snaps, t: datetime) -> str | None:
    """The source time of the book capture at `t` (the rows _series reads for
    the book venue at that stamp), isoformat like from_at / to_at, or None."""
    from src.timeutil import oldest_source_time
    rows = [x for x in snaps if x.captured_at == t and x.source != "kalshi" and x.market == "1X2"]
    v = oldest_source_time(rows)
    return v.isoformat() if v else None


def line_move_for_match(s, m, now: datetime | None = None) -> dict | None:
    from sqlalchemy import select

    from src.db.schema import OddsSnapshot
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)   # naive UTC (the storage convention)
    if m.utc_date is None or not (m.utc_date - timedelta(hours=LINE_MOVE_WINDOW_H) <= now < m.utc_date):
        return None
    snaps = s.execute(select(OddsSnapshot).where(OddsSnapshot.match_id == m.id)).scalars()
    return line_move(snaps, m.utc_date, now, three_way=_is_soccer(m))


def _is_soccer(m) -> bool:
    return str(getattr(m.sport, "value", m.sport)).lower() == "soccer"


def describe(lm: dict | None) -> str:
    """One line for pages/receipts: 'book 0.489→0.560 (+7.1pp) · kalshi …'."""
    if not lm:
        return ""
    return " · ".join(f"{k} {v['from']:.3f}→{v['to']:.3f} ({v['move_pp']:+.1f}pp)"
                      for k, v in lm["venues"].items() if v["alarm"])
