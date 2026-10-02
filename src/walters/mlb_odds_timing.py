"""
MLB odds TIMING receipt (architect finding 2026-09-30): "api-sports Baseball
odds absent for the two postseason night games (BOS@NYY, CHC@SD) on three
consecutive days while day games are priced ... check whether the provider
prices them only on game day ET or not at all."

Read-only. Answers from OUR append-only record, never the provider:
odds_snapshots rows with source="api_baseball" are written by capture-odds
(sp-clv-capture, 08/12/16/20 America/New_York) every time the provider
returned books for a game, so the FIRST such row per match is when the
provider first priced it as far as our captures can see. Per match:

  * start in UTC and ET; ROLLOVER = the ET calendar date differs from the
    UTC date (the M11 family: the provider's /odds window is UTC-day-scoped,
    BACKLOG "M11 MECHANISM CONFIRMED 08-24" / "M11 CLOSED 2026-08-25");
  * book captures: total, before first pitch, first/last capture time,
    max books; whether the first pre-start capture came after the start's
    UTC midnight (i.e. only once the UTC date had arrived);
  * the current odds-table rows (wipe-and-replace; their captured_at is the
    LAST sync that found books) and Kalshi snapshots before first pitch.

Verdict per game (conservative, law 4 — the capture cadence bounds what can
be claimed; "never" means "never in OUR captures"):
  PRICED_PRE_START          first book capture before first pitch
  PRICED_ONLY_AFTER_START   books appear, but only after first pitch
  NO_BOOKS_CAPTURED         no api_baseball capture at all
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
NIGHT_ET_HOUR = 18          # an ET start at/after 18:00 counts as a night game (display grouping only)


def to_et(t: datetime) -> datetime:
    return t.replace(tzinfo=UTC).astimezone(ET).replace(tzinfo=None)


def et_day_bounds_utc(d: date) -> tuple[datetime, datetime]:
    """[start, end) of an ET calendar day, as UTC-naive datetimes."""
    lo = datetime.combine(d, time()).replace(tzinfo=ET).astimezone(UTC).replace(tzinfo=None)
    hi = datetime.combine(d + timedelta(days=1), time()).replace(tzinfo=ET).astimezone(UTC).replace(tzinfo=None)
    return lo, hi


def classify(start: datetime, book_caps: list[tuple[datetime, int]]) -> dict:
    """Pure: one game's timing from its UTC start and its (captured_at, n_books)
    api_baseball captures."""
    et = to_et(start)
    rollover = et.date() != start.date()
    caps = sorted(book_caps)
    pre = [c for c in caps if c[0] < start]
    utc_midnight = datetime.combine(start.date(), time())
    out = {"start_utc": start, "start_et": et, "rollover": rollover, "night": et.hour >= NIGHT_ET_HOUR,
           "captures": len(caps), "captures_pre_start": len(pre),
           "first_capture": caps[0][0] if caps else None, "last_capture": caps[-1][0] if caps else None,
           "max_books": max((n for _, n in caps), default=0),
           "first_pre_start_after_utc_midnight": None, "lead_hours": None}
    if pre:
        out["verdict"] = "PRICED_PRE_START"
        out["first_pre_start_after_utc_midnight"] = pre[0][0] >= utc_midnight
        out["lead_hours"] = round((start - pre[0][0]).total_seconds() / 3600.0, 1)
    elif caps:
        out["verdict"] = "PRICED_ONLY_AFTER_START"
    else:
        out["verdict"] = "NO_BOOKS_CAPTURED"
    return out


def timing(start: date, end: date) -> dict:
    """Receipt over MLB matches whose ET start date is in [start, end]."""
    from sqlalchemy import func, select
    from sqlalchemy.orm import aliased

    from src.db.database import session_scope
    from src.db.schema import Match, Odds, OddsSnapshot, Sport, Team

    lo, _ = et_day_bounds_utc(start)
    _, hi = et_day_bounds_utc(end)
    H, A = aliased(Team), aliased(Team)
    with session_scope() as s:
        games = s.execute(select(Match.id, Match.utc_date, Match.stage, Match.status, H.name, A.name)
                          .join(H, Match.home_team_id == H.id).join(A, Match.away_team_id == A.id)
                          .where(Match.sport == Sport.MLB, Match.utc_date >= lo, Match.utc_date < hi)
                          .order_by(Match.utc_date)).all()
        ids = [g[0] for g in games]
        caps: dict[int, dict] = {}
        for mid, at, nb in s.execute(select(OddsSnapshot.match_id, OddsSnapshot.captured_at,
                                            func.max(OddsSnapshot.n_books))
                                     .where(OddsSnapshot.match_id.in_(ids), OddsSnapshot.source == "api_baseball")
                                     .group_by(OddsSnapshot.match_id, OddsSnapshot.captured_at)):
            caps.setdefault(mid, {})[at] = nb or 0
        kalshi = dict(s.execute(select(OddsSnapshot.match_id, func.min(OddsSnapshot.captured_at))
                                .where(OddsSnapshot.match_id.in_(ids), OddsSnapshot.source == "kalshi")
                                .group_by(OddsSnapshot.match_id)).all())
        table = {mid: (n, last) for mid, n, last in s.execute(
            select(Odds.match_id, func.count(func.distinct(Odds.bookmaker)), func.max(Odds.captured_at))
            .where(Odds.match_id.in_(ids), Odds.source == "api_baseball").group_by(Odds.match_id))}
    rows, summary = [], Counter()
    for mid, t, stage, status, home, away in games:
        r = classify(t, list(caps.get(mid, {}).items()))
        k = kalshi.get(mid)
        r.update(match_id=mid, game=f"{away} @ {home}", stage=stage or "", status=getattr(status, "value", status),
                 odds_table_books=table.get(mid, (0, None))[0], odds_table_last=table.get(mid, (0, None))[1],
                 kalshi_first=k, kalshi_pre_start=bool(k and k < t))
        rows.append(r)
        summary[(("night" if r["night"] else "day") + ("/rollover" if r["rollover"] else ""), r["verdict"])] += 1
    return {"window_utc": (lo, hi), "games": rows,
            "summary": {f"{k[0]} {k[1]}": v for k, v in sorted(summary.items())}}
