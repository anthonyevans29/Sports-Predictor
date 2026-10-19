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

from datetime import datetime, timedelta, timezone

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
                    "source": "snapshot",
                    # the legs it priced, whose provider stamp the stale-book rule reads (addendum 137 item 4)
                    "stamp_rows": [legs[k] for k in outcomes]}
    return None


KALSHI_ONLY_GRADE_RULING = ("ARCHITECT 2026-10-05: when no book session exists pre-pitch and a two-sided "
                            "Kalshi capture does, grade against the Kalshi mid, labelled reference=kalshi_only; "
                            "the Desk's 2c spread cap applies")


# Two-way Kalshi rows are stored as market "ML" (sync_kalshi_mlb and the shared
# NFL/NHL/NCAA matcher); soccer's three-way legs as "1X2". Book snapshots are
# 1X2 only. The grading close reads 1X2 rows plus Kalshi ML rows; filtering on
# 1X2 alone dropped every two-way Kalshi quote (Codex on #278).
KALSHI_CLOSE_MARKETS = ("1X2", "ML")


def kalshi_close_market_filter(OddsSnapshot):
    """SQL filter: every 1X2 snapshot, plus Kalshi's two-way ML rows."""
    from sqlalchemy import and_, or_
    return or_(OddsSnapshot.market == "1X2",
               and_(OddsSnapshot.source == "kalshi", OddsSnapshot.market == "ML"))


def close_from_kalshi(snaps, before: datetime | None, outcomes: tuple[str, ...]) -> dict | None:
    """KALSHI-ONLY GRADING CLOSE (ARCHITECT 2026-10-05, ruled after MLB 00:00Z
    rollover rows graded unpriced twice: the provider never posts pre-pitch).
    Two-way boards only (a 3-way board has no derived price — the Desk's rule).
    The LAST pre-cutoff Kalshi HOME capture that is TWO-SIDED (yes bid AND yes
    ask stored) gives mid = (bid + ask) / 2; fair = {HOME: mid, AWAY: 1 − mid},
    the Desk's kalshi_only_ref form. None when no such capture exists.
    SPREAD CAP (ARCHITECT 2026-10-05, on #278): "apply the SAME 2c spread cap to
    the grading close — a wide Kalshi mid is not a reference anywhere." The
    Desk's own cap (desk_policy.KALSHI_ONLY["maxSpreadC"], same cent rounding):
    when the LAST two-sided quote is wider, there is no Kalshi close (an older,
    tighter quote is stale, never substituted)."""
    if tuple(outcomes) != BINARY:
        return None
    pre = [x for x in snaps
           if getattr(x, "source", None) == "kalshi" and x.selection == "HOME" and x.captured_at is not None
           and getattr(x, "market", None) in KALSHI_CLOSE_MARKETS
           and (before is None or x.captured_at < before)
           and getattr(x, "yes_bid", None) is not None and getattr(x, "yes_ask", None) is not None]
    if not pre:
        return None
    from src.walters.desk_policy import KALSHI_ONLY, js_round

    k = max(pre, key=lambda x: x.captured_at)
    bid, ask = float(k.yes_bid), float(k.yes_ask)
    if not (0.0 <= bid <= ask <= 1.0) or ask <= 0.0 or bid >= 1.0:
        return None
    if js_round((ask - bid) * 100) > KALSHI_ONLY["maxSpreadC"]:
        return None                                  # a wide mid is not a reference anywhere
    mid = (bid + ask) / 2
    return {"fair": {"HOME": mid, "AWAY": 1 - mid}, "books": 0, "books_quoted": 0, "captured_at": k.captured_at,
            "best": {}, "rows": [], "outcomes": BINARY, "missing": {}, "overround": None,
            "source": "kalshi_only", "reference": "kalshi_only",
            "kalshi": {"bid": bid, "ask": ask, "mid": mid, "spread_c": round((ask - bid) * 100, 1),
                       "ruling": KALSHI_ONLY_GRADE_RULING}}


# THE STALE BOOK CLOSE (ARCHITECT 2026-10-19, addendum 137 item 4, #614; the close contract #207 gains one rule),
# verbatim: "FOR A GRADED GAME WHOSE BOOK QUOTE CARRIES A PROVIDER STAMP MORE THAN 24 HOURS BEFORE KICKOFF, THE
# RECORDED CLOSE IS THE KALSHI TWO-SIDED MID CAPTURED IN THE SAME LAST PRE-KICKOFF SESSION, and the row says so
# (`close_reference: kalshi`, with the book stamp's age in hours beside it [...]). A NULL or absent stamp keeps the
# book close (unknown is not stale: law 4 labels it, it does not switch it) until the stamp is stored. Scope: every
# family, applied where a stamp exists — which today is NFL."
STALE_BOOK_H = 24
STALE_BOOK_RULING = ("ARCHITECT 2026-10-19, addendum 137 item 4: a graded game whose book quote carries a provider "
                     "stamp more than 24 hours before kickoff grades against the Kalshi two-sided mid captured in the "
                     "same last pre-kickoff session")
KALSHI_SOURCES = ("kalshi_only", "kalshi")    # the closes priced from a Kalshi mid (the 2026-10-05 ruling's, this one's)


def _naive_utc(t: datetime) -> datetime:
    return t.astimezone(timezone.utc).replace(tzinfo=None) if t.tzinfo else t


def book_stamp(cl, session=None) -> datetime | None:
    """The provider stamp of a priced BOOK close: the oldest `source_updated_at` (src.timeutil.oldest_source_time: a
    row without one makes the whole close's stamp unknown) over the rows it priced: the complete books' outcome rows
    of its session (close_1x2's `rows`, the books not in `missing`), or the legs of its snapshot session
    (close_from_snapshots' `stamp_rows`). Read through attach_source_times (the column is not mapped; before the
    migration every row reads None). None: unknown."""
    if not priced(cl) or cl.get("source") in KALSHI_SOURCES:
        return None
    rows = cl.get("stamp_rows")
    if rows is None:
        out = set(cl.get("outcomes") or ())
        rows = [o for o in cl.get("rows") or ()
                if o.bookmaker not in (cl.get("missing") or {}) and o.selection in out]
    if not rows:
        return None
    from src.db.database import attach_source_times
    from src.timeutil import oldest_source_time
    if session is None:
        from sqlalchemy.orm import object_session
        session = next((x for x in (object_session(r) for r in rows if hasattr(r, "__table__")) if x), None)
    return oldest_source_time(attach_source_times(session, rows))


def stamp_age_hours(stamp: datetime | None, kickoff: datetime | None) -> float | None:
    """Hours from the book's provider stamp to the stored kickoff (Match.utc_date); None when either is unknown."""
    if stamp is None or kickoff is None:
        return None
    return (_naive_utc(kickoff) - _naive_utc(stamp)).total_seconds() / 3600


def session_kalshi(snaps, book_at: datetime | None, before: datetime | None, outcomes: tuple[str, ...]) -> dict | None:
    """The Kalshi two-sided mid CAPTURED IN THE SAME SESSION as a book close captured at `book_at`: of the Kalshi rows
    captured within CAPTURE_SESSION of `book_at` (either side; one closing run writes the book, then Kalshi, seconds
    apart) and before `before`, close_from_kalshi's close: the newest two-sided HOME capture, its mid under the 2c
    spread cap ("a wide Kalshi mid is not a reference anywhere", 2026-10-05). A two-way board only. None when the
    session holds no such quote (none, one-sided, wider than the cap)."""
    if book_at is None:
        return None
    at = _naive_utc(book_at)
    near = [x for x in snaps if getattr(x, "source", None) == "kalshi" and x.captured_at is not None
            and abs(_naive_utc(x.captured_at) - at) <= CAPTURE_SESSION]
    return close_from_kalshi(near, before, outcomes)


def stale_book_close(s, match, cl, snaps=None) -> dict | None:
    """Addendum 137 item 4 on a priced BOOK close `cl` of `match` (the odds table's session or a book snapshot's).
    Every return carries `book_stamp` and `book_stamp_age_h` (None: unknown):
      - the stamp unknown (NULL, absent, before the migration), or not MORE than STALE_BOOK_H before the stored
        kickoff: `cl` itself, the book close (law 4 labels an unknown stamp, it does not switch it);
      - a three-way board: `cl` itself, the book close, `stale_unswitched` saying why (the rule names a two-sided
        mid; Kalshi's three-way legs have no derived price, close_from_kalshi);
      - else the Kalshi close of the same session (session_kalshi over the game's Kalshi rows, the mismatched-legs
        guard first, addendum 37 item 3): source and reference "kalshi", captured_at the Kalshi capture's, `kalshi`
        {bid, ask, mid, spread_c, ruling}, `book_fair` and `book_captured_at` the book close it replaces;
      - or, the session holding no two-sided Kalshi quote within the cap: UNPRICED (`fair` None), `stale_book`
        saying why. The stale book is not the close and no other quote is substituted (the #207 rule: never a
        partial or a stand-in price).
    `snaps`: the game's snapshot rows when the caller has them (Kalshi rows are read from them), else read here."""
    if not priced(cl) or cl.get("source") in KALSHI_SOURCES:
        return cl
    stamp = book_stamp(cl, s)
    age = stamp_age_hours(stamp, match.utc_date)
    cl["book_stamp"], cl["book_stamp_age_h"] = stamp, age
    if age is None or age <= STALE_BOOK_H:
        return cl
    if tuple(cl.get("outcomes") or ()) != BINARY:
        cl["stale_unswitched"] = "three-way board: the rule names a two-sided Kalshi mid; none is derived for it"
        return cl
    if snaps is None:
        from sqlalchemy import select

        from src.db.schema import OddsSnapshot
        snaps = list(s.execute(select(OddsSnapshot).where(
            OddsSnapshot.match_id == match.id, OddsSnapshot.source == "kalshi",
            OddsSnapshot.market.in_(KALSHI_CLOSE_MARKETS))).scalars())
    from src.walters.kalshi_legs import guard_snaps
    kal, mismatched = guard_snaps([x for x in snaps if getattr(x, "source", None) == "kalshi"], s)
    ko = session_kalshi(kal, cl["captured_at"], match.utc_date, cl["outcomes"])
    if ko is None:
        why = (f"the game's Kalshi legs are mismatched ({', '.join(mismatched)}; addendum 37 item 3: no close from "
               "mismatched legs)" if mismatched else
               f"no two-sided Kalshi quote within the {_spread_cap()}c cap in the book close's session")
        return {"fair": None, "books": cl["books"], "books_quoted": cl.get("books_quoted", cl["books"]),
                "captured_at": cl["captured_at"], "best": {}, "rows": [], "outcomes": cl["outcomes"], "missing": {},
                "source": cl.get("source"), "reference": None, "book_stamp": stamp, "book_stamp_age_h": age,
                "stale_book": f"book stamp {age:.2f} h before kickoff; {why}"}
    ko["kalshi"]["ruling"] = STALE_BOOK_RULING
    ko.update(source="kalshi", reference="kalshi", book_stamp=stamp, book_stamp_age_h=age,
              book_fair=dict(cl["fair"]), book_captured_at=cl["captured_at"])
    return ko


def _spread_cap() -> int:
    from src.walters.desk_policy import KALSHI_ONLY
    return KALSHI_ONLY["maxSpreadC"]


def grading_close(s, match) -> dict | None:
    """THE close for grading a finished match: the odds table's last
    pre-kickoff session under the contract; when that cannot price (no
    pre-kickoff capture survives — MLB's replace-on-sync — or no complete
    book), the last complete pre-kickoff BOOK-CONSENSUS snapshot session;
    when NO BOOK SESSION EXISTS pre-kickoff at all (neither table holds a
    pre-kickoff book capture — the MLB 00:00Z rollover rows) and a two-sided
    Kalshi capture does, the Kalshi mid, labelled reference=kalshi_only
    (ARCHITECT 2026-10-05). A book session that exists but cannot price (an
    incomplete outcome set) stays UNPRICED: the ruling covers absent books only.
    A priced book close (odds or snapshot) then meets THE STALE BOOK RULE
    (ARCHITECT 2026-10-19, addendum 137 item 4, stale_book_close): its
    provider stamp more than 24 hours before kickoff, the close is the Kalshi
    two-sided mid of the same session ("source"/"reference" "kalshi"), or
    UNPRICED when that session holds none; an unknown stamp keeps the book.
    Returns a priced close (with "source": "odds" | "snapshot" | "kalshi_only"
    | "kalshi" and "reference": "books" | "kalshi_only" | "kalshi") or the
    odds-table result / None, so callers keep using priced()."""
    from sqlalchemy import select

    from src.db.schema import Odds, OddsSnapshot

    outcomes = outcomes_for(match.sport)
    odds = list(s.execute(select(Odds).where(Odds.match_id == match.id, Odds.market == "1X2")).scalars())
    cl = close_1x2(odds, match.utc_date, outcomes) if odds else None
    if priced(cl):
        cl["source"], cl["reference"] = "odds", "books"
        return stale_book_close(s, match, cl)          # addendum 137 item 4
    snaps = list(s.execute(select(OddsSnapshot).where(
        OddsSnapshot.match_id == match.id, kalshi_close_market_filter(OddsSnapshot))).scalars())
    book_snaps = [x for x in snaps if x.source != "kalshi" and x.market == "1X2"]
    sn = close_from_snapshots(book_snaps, match.utc_date, outcomes)
    if sn is not None:
        sn["reference"] = "books"
        return stale_book_close(s, match, sn, snaps)   # addendum 137 item 4
    if cl is None and not any(x.captured_at is not None and (match.utc_date is None or x.captured_at < match.utc_date)
                              for x in book_snaps):
        from src.walters.kalshi_legs import guard_snaps
        snaps, _ = guard_snaps(snaps, s)   # addendum 37 item 3: no close from mismatched Kalshi legs
        ko = close_from_kalshi(snaps, match.utc_date, outcomes)
        if ko is not None:
            return ko
    return cl


CLOSE_SOURCE = "close_1x2: last pre-kickoff capture session, complete books de-vigged then averaged (#167/#207)"


def minutes_before_start(captured_at: datetime | None, start: datetime | None) -> int | None:
    """`close_minutes_before_start` (ARCHITECT addendum 31 item 3, #382): whole minutes, ROUNDED DOWN,
    from the close's capture (`close_at`) to the stored start (`Match.utc_date`); None when either is
    missing. It is the AGE OF OUR CAPTURE, not of the quote (#348): a fresh capture of an unchanged book still reads
    young. The quote's own time, where the provider gives one (NFL since addendum 32), is the book stamp the
    stale-book rule reads (stale_book_close, `close_book_stamp_age_h`)."""
    if captured_at is None or start is None:
        return None
    if (captured_at.tzinfo is None) != (start.tzinfo is None):          # compare naive UTC with naive UTC
        captured_at, start = (x.astimezone(timezone.utc).replace(tzinfo=None) if x.tzinfo else x
                              for x in (captured_at, start))
    return (start - captured_at) // timedelta(minutes=1)


def close_age_summary(minutes) -> dict:
    """results-tally's close-age line (#382): over a sport's window, the median and the largest
    close_minutes_before_start, with n (rows with no close, a None, are not counted)."""
    import statistics
    xs = [x for x in minutes if x is not None]
    return {"n": len(xs), "median": statistics.median(xs) if xs else None, "max": max(xs) if xs else None}


def close_age_line(a: dict) -> str:
    """One RESULTS.md bullet for close_age_summary's dict."""
    head = "- Close capture age (close_minutes_before_start; our capture, not the quote, #348): "
    if not a["n"]:
        return head + "— (n=0)\n"
    med = a["median"]
    med = str(int(med)) if float(med).is_integer() else f"{med:.1f}"
    return head + f"median {med} min, largest {a['max']} min before start (n={a['n']})\n"


KALSHI_ONLY_SOURCE = ("kalshi_only: mid of the last two-sided pre-kickoff Kalshi HOME quote (no book session "
                      "pre-kickoff; ARCHITECT 2026-10-05)")
STALE_BOOK_SOURCE = ("kalshi: mid of the two-sided Kalshi HOME quote captured in the book close's session (the book "
                     "quote's provider stamp more than 24 h before kickoff; ARCHITECT 2026-10-19, addendum 137 item 4)")


def graded_block(cl, kickoff: datetime | None) -> dict:
    """The results row's close block from a grading close `cl` (grading_close's, or a family grader's close after
    stale_book_close): {close_fair, close_at, close_minutes_before_start, close_books, close_source,
    close_reference ("books" | "kalshi_only" | "kalshi" | None), close_book_stamp_age_h}, plus `close_kalshi` on a
    Kalshi close and `close_stale_book` (why) on a close the stale-book rule left unpriced. ARCHITECT 2026-10-19,
    addendum 137 item 4: "the row says so (`close_reference: kalshi`, with the book stamp's age in hours beside
    it)"; the age is carried on every row (None: no close, or the stamp unknown), in hours to two places."""
    age = (cl or {}).get("book_stamp_age_h")
    age = round(age, 2) if age is not None else None
    if not priced(cl):
        return {"close_fair": None, "close_at": None, "close_minutes_before_start": None,
                "close_books": cl["books"] if cl else 0, "close_source": CLOSE_SOURCE, "close_reference": None,
                "close_book_stamp_age_h": age,
                **({"close_stale_book": cl["stale_book"]} if cl and cl.get("stale_book") else {})}
    src = {"kalshi_only": KALSHI_ONLY_SOURCE, "kalshi": STALE_BOOK_SOURCE}.get(cl.get("source"), CLOSE_SOURCE)
    out = {"close_fair": {k: round(v, 4) for k, v in cl["fair"].items()},
           "close_at": cl["captured_at"].isoformat() if cl["captured_at"] else None,
           "close_minutes_before_start": minutes_before_start(cl["captured_at"], kickoff),
           "close_books": cl["books"], "close_source": src, "close_reference": cl.get("reference", "books"),
           "close_book_stamp_age_h": age}
    if cl.get("source") in KALSHI_SOURCES:
        out["close_kalshi"] = {k: cl["kalshi"][k] for k in ("bid", "ask", "mid", "spread_c")}
        if cl.get("source") == "kalshi":            # the book close it replaced, for the record's audit
            out["close_kalshi"]["book_fair"] = {k: round(v, 4) for k, v in cl["book_fair"].items()}
            out["close_kalshi"]["book_at"] = cl["book_captured_at"].isoformat() if cl["book_captured_at"] else None
    if cl.get("stale_unswitched"):
        out["close_stale_unswitched"] = cl["stale_unswitched"]
    return out


def grading_close_block(s, match) -> dict:
    """close_block's shape from THE grading close (odds → snapshot → kalshi_only, the stale-book rule on a book
    close), plus `close_reference` ("books" | "kalshi_only" | "kalshi" | None) — the results rows' per-side close for
    entry-price CLV, so a row graded against a Kalshi mid says so (ARCHITECT 2026-10-05; 2026-10-19, addendum 137
    item 4) — and `close_book_stamp_age_h` (graded_block). Carries close_minutes_before_start (#382) beside close_at:
    the age of our capture, not of the quote (#348)."""
    return graded_block(grading_close(s, match), match.utc_date)


def close_block(rows, kickoff: datetime | None, sport) -> dict:
    """P0-3 (#208): the per-side closing fair for a results row — `q_close` for
    entry-price CLV in the Cockpit ledger. {close_fair, close_at,
    close_minutes_before_start, close_books, close_source}; close_fair is None
    when the close is unpriced or absent (the metric is then unavailable, never
    inferred). close_minutes_before_start (#382): whole minutes, rounded down,
    from close_at to the stored start; null where there is no close. It is the
    age of OUR CAPTURE, not of the quote (#348) — see minutes_before_start."""
    cl = close_1x2([o for o in rows if getattr(o, "market", None) == "1X2"], kickoff, outcomes_for(sport))
    if not priced(cl):
        return {"close_fair": None, "close_at": None, "close_minutes_before_start": None,
                "close_books": cl["books"] if cl else 0, "close_source": CLOSE_SOURCE}
    return {"close_fair": {k: round(v, 4) for k, v in cl["fair"].items()},
            "close_at": cl["captured_at"].isoformat() if cl["captured_at"] else None,
            "close_minutes_before_start": minutes_before_start(cl["captured_at"], kickoff),
            "close_books": cl["books"], "close_source": CLOSE_SOURCE}
