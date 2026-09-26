"""
Venue divergence (2026-09-26, architect): book consensus vs Kalshi.

Arrives first as a LIE DETECTOR on the NFL predictions export: the
provider's football moneylines were found stale AT SOURCE (favourite
disagreements between deep, same-minute markets survived the vetted
spread check), and the same 1X2 rows feed fair / divergence / quarantine.
A large book-vs-Kalshi gap flags the book reference as suspect.

DISPLAY AND WARNING ONLY: nothing here changes the quarantine contract,
which still keys on the book divergence exactly as ratified. The Cockpit
v0.4 venue-edge engine reuses this math.
"""
from __future__ import annotations

STALE_BOOK_GAP_PP = 8.0     # frozen a-priori (architect 2026-09-26)
STALE_BOOK_FLAG = "STALE-BOOK?"


def kalshi_home_prob(snapshots, kickoff) -> dict | None:
    """Latest PRE-KICKOFF Kalshi price per side (the fixtures-export rule);
    two-sided only. Returns {"home": P(home) normalized over HOME+AWAY,
    "captured_at": latest capture} or None when not two-sided."""
    latest: dict[str, object] = {}
    for snap in snapshots:
        if snap.source != "kalshi" or snap.selection not in ("HOME", "AWAY"):
            continue
        if kickoff is not None and snap.captured_at is not None and snap.captured_at >= kickoff:
            continue  # in-play never
        cur = latest.get(snap.selection)
        if (cur is None or (snap.captured_at is not None
                            and (cur.captured_at is None or snap.captured_at > cur.captured_at))):
            latest[snap.selection] = snap
    if set(latest) != {"HOME", "AWAY"}:
        return None
    h, a = latest["HOME"].devig_prob, latest["AWAY"].devig_prob
    if h is None or a is None or h + a <= 0:
        return None
    caps = [s.captured_at for s in latest.values() if s.captured_at is not None]
    return {"home": h / (h + a), "captured_at": max(caps) if caps else None}


def venue_gap(book_home: float | None, kalshi_home: float | None) -> tuple[float | None, str | None]:
    """(|book_fair - kalshi| in pp, flag). Flag = STALE-BOOK? at >= 8.0pp."""
    if book_home is None or kalshi_home is None:
        return None, None
    gap = round(abs(book_home - kalshi_home) * 100, 1)
    return gap, (STALE_BOOK_FLAG if gap >= STALE_BOOK_GAP_PP else None)
