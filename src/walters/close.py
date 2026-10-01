"""
THE CLOSE — one definition for every reader of the `odds` table (#167,
ARCHITECT-RULE 2026-10-01: "closing price = LAST pre-kickoff capture").

Found 2026-10-01 (law 1, read from code): the general `sync_odds` path
APPENDS a full book set on every run (soccer, cups, NHL — hourly from the
window job), and every reader de-vigged ALL of a match's 1X2 rows at once
(MarketSnapshot.average_implied over every capture ever stored). The "close"
for those sources was therefore a mean over every capture, and `best_price`
the best price ever seen — not the closing price. MLB (api_baseball) and NFL
(api_american_football) wipe-and-replace, so they held one capture already.

The definition, used by evaluate's CLV (and its M11b backfill), NFL grading,
nhl_shadow, the prediction/fixtures exports' market block, the market blend
and miss analysis:

  1. candidate rows: `captured_at` strictly BEFORE the cutoff — the match's
     kickoff for grading (in-game prices are never the close), or the row
     export's kickoff for a pre-game market (all stored rows of an upcoming
     game are before it). Rows with no `captured_at` are excluded (law 4).
  2. the LAST CAPTURE SESSION: the newest candidate `captured_at` t, and every
     candidate row with captured_at >= t − CAPTURE_SESSION. One sync writes a
     match's books within seconds (MLB stamps each row separately, microseconds
     apart); the window job's runs are an hour apart — so a session is one run.
  3. per (bookmaker, selection, line): the latest row of the session.
A book missing from the last session contributes nothing (a stale price from
an earlier run is never the close).
"""
from __future__ import annotations

from datetime import datetime, timedelta

CAPTURE_SESSION = timedelta(minutes=10)


def last_capture(rows, before: datetime | None):
    """The rows of the last capture session strictly before `before`
    (None = no cutoff), one per (bookmaker, selection, line)."""
    pre = [o for o in rows if o.captured_at is not None and (before is None or o.captured_at < before)]
    if not pre:
        return []
    t = max(o.captured_at for o in pre)
    latest: dict = {}
    for o in pre:
        if o.captured_at < t - CAPTURE_SESSION:
            continue
        key = (o.bookmaker, o.selection, getattr(o, "line", None))
        if key not in latest or o.captured_at > latest[key].captured_at:
            latest[key] = o
    return list(latest.values())


def by_selection(rows) -> dict[str, list[tuple[str, float]]]:
    out: dict[str, list[tuple[str, float]]] = {}
    for o in rows:
        out.setdefault(o.selection, []).append((o.bookmaker, o.price_decimal))
    return out


def close_1x2(rows, before: datetime | None) -> dict | None:
    """De-vigged fair probabilities of the last pre-cutoff 1X2 capture
    session, plus its book count, timestamp and best price per selection.
    None when there is no such row."""
    from src.walters.value import MarketSnapshot

    sess = last_capture([o for o in rows if o.market == "1X2"], before)
    if not sess:
        return None
    snap = MarketSnapshot(market="1X2", by_selection=by_selection(sess))
    implied = snap.average_implied()
    over = sum(implied.values())
    if over <= 0:
        return None
    return {"fair": {k: v / over for k, v in implied.items()},
            "books": len({o.bookmaker for o in sess}),
            "captured_at": max(o.captured_at for o in sess),
            "best": {sel: snap.best_price(sel) for sel in implied},
            "rows": sess}
