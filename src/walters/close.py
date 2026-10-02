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

THE CLOSE CONTRACT (P0-2, #207, ARCHITECT 2026-10-01, external review):
  4. the caller names the OUTCOME SET — binary (HOME/AWAY: MLB, NFL, NCAA,
     NHL moneylines — the api-sports adapters map Home/Away/Moneyline only)
     or 3-way (HOME/DRAW/AWAY: soccer, api-football "Match Winner");
     `outcomes_for(sport)` is the one mapping;
  5. a BOOK counts only when it quoted EVERY outcome in the last session; each
     complete book is de-vigged on its own, then the books are averaged.
     A book quoting a subset (a 3-way board without its draw, one side only)
     is QUOTED but not COMPLETE and contributes nothing;
  6. no complete book -> UNPRICED: `fair` is None, `missing` names each quoted
     book's absent legs (the receipt), never a partial de-vig;
  7. `books` = complete books, `books_quoted` = every book in the session;
     `overround` = the mean per-book booksum of the complete books.
EXPORTS (ARCHITECT-RULE 2026-10-01): the MLB/soccer prediction export's
market block and the fixtures export's market use THIS contract — one
definition; the export block is the Desk's reference (#117 showed what a
pooled de-vig does to it). An unpriced close ships the no-1X2 shape plus an
additive `close_unpriced` receipt (quoted books + missing legs).
`close_1x2` returns None only when there is no pre-cutoff capture at all.
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


BINARY = ("HOME", "AWAY")
THREE_WAY = ("HOME", "DRAW", "AWAY")


def outcomes_for(sport) -> tuple[str, ...]:
    """The 1X2 outcome set our stored odds carry for a sport (read from the
    adapters, 2026-10-01): soccer boards are 3-way, every other sport's
    1X2 market is the two-way moneyline."""
    v = getattr(sport, "value", sport)
    return THREE_WAY if str(v).lower() == "soccer" else BINARY


def priced(cl) -> bool:
    """True when a close carries a fair price (at least one complete book)."""
    return cl is not None and cl.get("fair") is not None


def close_1x2(rows, before: datetime | None, outcomes: tuple[str, ...]) -> dict | None:
    """The close of the last pre-cutoff 1X2 capture session under the contract
    above. None when there is no pre-cutoff capture; otherwise a dict whose
    `fair` is None (UNPRICED, with the missing-leg receipt) unless at least one
    book quoted the whole outcome set."""
    sess = last_capture([o for o in rows if o.market == "1X2"], before)
    if not sess:
        return None
    outcomes = tuple(outcomes)
    books: dict[str, dict[str, float]] = {}
    for o in sess:
        if o.selection in outcomes and o.price_decimal and o.price_decimal > 1.0:
            books.setdefault(o.bookmaker, {})[o.selection] = o.price_decimal
    quoted = {o.bookmaker for o in sess}
    complete = {bk: px for bk, px in books.items() if all(k in px for k in outcomes)}
    missing = {bk: [k for k in outcomes if k not in books.get(bk, {})]
               for bk in sorted(quoted) if bk not in complete}
    out = {"fair": None, "books": len(complete), "books_quoted": len(quoted),
           "captured_at": max(o.captured_at for o in sess), "best": {},
           "rows": sess, "outcomes": outcomes, "missing": missing}
    if not complete:
        return out
    fair = {k: 0.0 for k in outcomes}
    overs = []
    for px in complete.values():
        imp = {k: 1.0 / px[k] for k in outcomes}
        over = sum(imp.values())
        overs.append(over)
        for k in outcomes:
            fair[k] += imp[k] / over
    out["fair"] = {k: v / len(complete) for k, v in fair.items()}
    out["overround"] = sum(overs) / len(overs)            # mean per-book booksum
    out["best"] = {k: max(((bk, px[k]) for bk, px in complete.items()), key=lambda x: x[1])
                   for k in outcomes}
    return out


def close_from_snapshots(snaps, before: datetime | None, outcomes: tuple[str, ...]) -> dict | None:
    """The close from BOOK-CONSENSUS odds_snapshots (MLB odds history, ARCHITECT
    2026-10-02: replace-on-sync sources lost the pre-first-pitch session when a
    later sync rewrote the odds table). A snapshot session is one captured_at
    stamp; the LAST pre-cutoff session that carries EVERY outcome is the close
    (the #207 contract: an incomplete session is never a price). Kalshi rows
    and non-1X2 markets never count. None when no such session exists.
    `best` is empty: a consensus snapshot has no single book price."""
    pre = [x for x in snaps
           if x.captured_at is not None and (before is None or x.captured_at < before)
           and getattr(x, "source", None) != "kalshi" and x.market == "1X2"
           and x.devig_prob is not None]
    by_t: dict = {}
    for x in pre:
        by_t.setdefault(x.captured_at, {})[x.selection] = x
    for t in sorted(by_t, reverse=True):
        legs = by_t[t]
        if all(k in legs for k in outcomes):
            tot = sum(legs[k].devig_prob for k in outcomes)
            if tot <= 0:
                continue
            n = max((legs[k].n_books or 0) for k in outcomes)
            return {"fair": {k: legs[k].devig_prob / tot for k in outcomes}, "books": n,
                    "books_quoted": n, "captured_at": t, "best": {}, "rows": [],
                    "outcomes": tuple(outcomes), "missing": {}, "overround": None,
                    "source": "snapshot"}
    return None


def grading_close(s, match) -> dict | None:
    """THE close for grading a finished match: the odds table's last
    pre-kickoff session under the contract; when that cannot price (no
    pre-kickoff capture survives — MLB's replace-on-sync — or no complete
    book), the last complete pre-kickoff BOOK-CONSENSUS snapshot session.
    Returns a priced close (with "source": "odds" | "snapshot") or the
    odds-table result / None, so callers keep using priced()."""
    from sqlalchemy import select

    from src.db.schema import Odds, OddsSnapshot

    outcomes = outcomes_for(match.sport)
    odds = list(s.execute(select(Odds).where(Odds.match_id == match.id, Odds.market == "1X2")).scalars())
    cl = close_1x2(odds, match.utc_date, outcomes) if odds else None
    if priced(cl):
        cl["source"] = "odds"
        return cl
    snaps = list(s.execute(select(OddsSnapshot).where(
        OddsSnapshot.match_id == match.id, OddsSnapshot.market == "1X2",
        OddsSnapshot.source != "kalshi")).scalars())
    return close_from_snapshots(snaps, match.utc_date, outcomes) or cl
