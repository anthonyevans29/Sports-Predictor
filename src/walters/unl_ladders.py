"""UNL ladder receipt + the frozen favorite-skew test (READ-ONLY).

ARCHITECT 2026-10-05 (#286, ruling 3): "a read-only receipt command printing
per-game rows (match, legs, bid/ask, spread, two-sided, capture time, series);
its output for the 30 is committed under docs/receipts/ via PR."

The sample and the test follow docs/specs/unl-venue-skew-test.md (v2, the ten
definitions RATIFIED by the architect 2026-10-06 on #286):
- the first N UNL games kicking off after the freeze cutoff, not exploratory,
  not CANCELLED/POSTPONED/STALE_ORPHAN, whose LAST pre-kickoff Kalshi capture
  (taken after the cutoff) is two-sided (0 < bid <= ask < 1) on all three legs,
  one event in series KXUEFANLGAME, with a book session meeting the venue
  engine's own rules (>= 4 books, captured <= 3h before the Kalshi capture);
- gap = Kalshi (three-leg normalized mids) − book, on the book favorite, in pp;
- mean gap, bootstrap B=10,000 seed 20261005, percentile 95% CI;
  STRUCTURAL when the CI excludes 0.
Every game is listed, the non-qualifying ones with their reason. Writes
nothing to the DB.
"""
from __future__ import annotations

import random
from datetime import datetime

# ARCHITECT 2026-10-06: "the FREEZE CUTOFF moves to the ratification time of this
# ruling — anything inspected before it is exploratory." The ruling's relay on #286
# (issuecomment-6018597888) is the recorded, citable time; it is not earlier than the
# ratification, so it can only shrink the fresh sample, never admit an inspected game.
FREEZE_CUTOFF = datetime(2026, 10, 6, 14, 35, 31)   # naive UTC, as the DB stores it
SAMPLE_N = 30
SERIES = "KXUEFANLGAME"
LEGS = ("HOME", "DRAW", "AWAY")
BOOT_B = 10_000
BOOT_SEED = 20261005
# Ruling 1: the 17 exploratory games (2026-10-05) are excluded BY MATCH ID. The ids live
# in the laptop DB; the operator records them here (EXPLORATORY_N of them) before the
# frozen test may run. Until then the receipt says so and --skew-test refuses.
# Recorded (ARCHITECT 2026-10-06): "UNL exploratory 17 (ruling 1), by match id, from the
# 2026-10-05T15:33:57Z capture" — pinned as excluded.
EXPLORATORY_MATCH_IDS: frozenset = frozenset({
    31887, 31888, 31890, 31891, 31892, 31893, 31894, 31895, 31896,
    31897, 31898, 31899, 31900, 31901, 31902, 31903, 31904,
})
EXPLORATORY_N = 17
# Ruling 4: every UNL sync in the sample runs at this --max-spread (sync-kalshi-soccer refuses others).
FROZEN_MAX_SPREAD = 0.10
# Ruling 7: never-played statuses, excluded from the cohort and listed.
EXCLUDED_STATUSES = ("cancelled", "postponed", "stale_orphan")


def data_dir():
    """The project's data/ directory, resolved (law 5: receipts never land under it)."""
    from pathlib import Path
    return (Path(__file__).resolve().parents[2] / "data").resolve()


def to_naive_utc(dt: datetime) -> datetime:
    """The DB stores naive UTC; an offset-bearing cutoff is converted, never compared aware."""
    from datetime import timezone
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo is not None else dt


def series_of(ticker: str | None) -> str | None:
    """'KXUEFANLGAME-26OCT10ESPFRA-ESP' -> 'KXUEFANLGAME'."""
    return ticker.split("-", 1)[0] if ticker else None


def event_of(ticker: str | None) -> str | None:
    """'KXUEFANLGAME-26OCT10ESPFRA-ESP' -> 'KXUEFANLGAME-26OCT10ESPFRA' (ruling 8). Only the
    market ticker is stored; a Kalshi market ticker is its event ticker plus one outcome
    suffix, so the event is the ticker without its last segment. Printed on every row."""
    return ticker.rsplit("-", 1)[0] if ticker and "-" in ticker else None


def leg_two_sided(x) -> bool:
    """Ruling 9: two-sided means 0 < bid <= ask < 1 (a 0.00 bid or a 1.00 ask has no executable side)."""
    return (x is not None and x.yes_bid is not None and x.yes_ask is not None
            and 0 < x.yes_bid <= x.yes_ask < 1)


def _last_two_sided_board(kal, kickoff):
    """(captured_at, {leg: snapshot}) of the LAST pre-kickoff Kalshi capture, and
    whether all three legs are two-sided there. Ruling 5: never substitutes an earlier one."""
    pre = [x for x in kal if x.captured_at is not None and kickoff is not None and x.captured_at < kickoff]
    if not pre:
        return None, {}, False
    t = max(x.captured_at for x in pre)
    legs = {x.selection: x for x in pre if x.captured_at == t and x.selection in LEGS}
    two = len(legs) == 3 and all(leg_two_sided(legs[k]) for k in LEGS)
    return t, legs, two


def _book_session(book, kickoff, kalshi_at=None):
    """The last complete book session before kickoff and not after the Kalshi capture
    (ruling 2: a capture later than the Kalshi one was not available then)."""
    from src.walters.close import close_from_snapshots
    if kalshi_at is not None:
        book = [x for x in book if x.captured_at is not None and x.captured_at <= kalshi_at]
    return close_from_snapshots(book, kickoff, LEGS)


def _book_rule():
    """Ruling 2: the venue engine's own rules, read from it (never a copy)."""
    from datetime import timedelta

    from src.walters.desk_policy import VENUE
    return VENUE["minBooks"], timedelta(hours=VENUE["maxBookAgeH"])


def game_row(m, snaps, tickers: dict, since: datetime) -> dict:
    """One receipt row for match `m` from its odds_snapshots."""
    kal = [x for x in snaps if x.source == "kalshi" and x.market == "1X2"]
    book = [x for x in snaps if x.source != "kalshi" and x.market == "1X2"]
    t, legs, two = _last_two_sided_board(kal, m.utc_date)
    status = getattr(m.status, "value", m.status)
    row = {"match_id": m.id, "kickoff": m.utc_date, "status": status, "event": None,
           "home": m.home_team.name if m.home_team else "?", "away": m.away_team.name if m.away_team else "?",
           "captured_at": t, "two_sided": two, "legs": {}, "series": None, "book": None,
           "favorite": None, "gap_pp": None, "qualifies": False, "reason": None}
    series, events = set(), set()
    for k in LEGS:
        x = legs.get(k)
        if x is None:
            row["legs"][k] = None
            continue
        tk = tickers.get(x.id)
        series.add(series_of(tk))
        events.add(event_of(tk))
        spread = (x.yes_ask - x.yes_bid) * 100 if x.yes_bid is not None and x.yes_ask is not None else None
        row["legs"][k] = {"bid": x.yes_bid, "ask": x.yes_ask,
                          "spread_c": round(spread, 1) if spread is not None else None,
                          "two_sided": leg_two_sided(x), "ticker": tk}
    # every present leg needs a stored ticker (Codex on #291): a missing one makes the
    # series UNKNOWN, never certified by the legs that do carry one
    row["series"] = None if (not series or None in series) else ",".join(sorted(series))
    row["event"] = None if (not events or None in events) else ",".join(sorted(events))
    cl = _book_session(book, m.utc_date, t)
    if cl is not None:
        row["book"] = {k: cl["fair"][k] for k in LEGS}
        row["book_at"], row["book_n"] = cl["captured_at"], cl["books"]
    min_books, max_age = _book_rule()
    # reasons, in order (the first failing criterion is reported)
    if m.utc_date is None or m.utc_date <= since:
        row["reason"] = "kickoff not after the freeze cutoff"
    elif m.id in EXPLORATORY_MATCH_IDS:
        row["reason"] = "exploratory game (ruling 1: the 17 of 2026-10-05, by match id)"
    elif str(status).lower() in EXCLUDED_STATUSES:
        row["reason"] = f"status {str(status).upper()} — never played (ruling 7)"
    elif t is None:
        row["reason"] = "no pre-kickoff Kalshi capture"
    elif t <= since:                         # strictly AFTER the cutoff (Codex on #291)
        row["reason"] = "last Kalshi capture not after the freeze cutoff"
    elif not two:
        row["reason"] = "one-sided board (ruling 2)"
    elif row["series"] != SERIES:
        row["reason"] = f"series {row['series'] or 'UNKNOWN (no stored ticker)'} is not {SERIES}"
    elif row["event"] is None or "," in row["event"]:
        row["reason"] = f"legs not one event ({row['event'] or 'UNKNOWN'}) (ruling 8)"
    elif cl is None:
        row["reason"] = "no complete book session at or before the Kalshi capture"
    elif (cl["books"] or 0) < min_books:
        row["reason"] = f"book session has {cl['books'] or 0} books < {min_books} (ruling 2)"
    elif t - cl["captured_at"] > max_age:
        row["reason"] = (f"book session {(t - cl['captured_at']).total_seconds() / 3600:.1f}h before the Kalshi "
                         f"capture > {max_age.total_seconds() / 3600:.0f}h (ruling 2)")
    else:
        mids = {k: (legs[k].yes_bid + legs[k].yes_ask) / 2 for k in LEGS}
        tot = sum(mids.values())
        kn = {k: mids[k] / tot for k in LEGS} if tot > 0 else None
        ranked = sorted(LEGS, key=lambda k: row["book"][k], reverse=True)
        if kn is None:
            row["reason"] = "Kalshi mids sum to 0"
        elif row["book"][ranked[0]] == row["book"][ranked[1]]:      # ruling 10: an EXACT tie only
            row["reason"] = "tied book favorite (exact)"
        else:
            fav = ranked[0]
            # full precision: the frozen test bootstraps these values; rounding is display-only (Codex on #291)
            row.update(favorite=fav, kalshi_norm=kn, gap_pp=(kn[fav] - row["book"][fav]) * 100, qualifies=True)
    return row


def receipt(s, competition: str = "UNL", since: datetime = FREEZE_CUTOFF, n: int = SAMPLE_N,
            now: datetime | None = None) -> dict:
    """Every game of `competition` kicking off after `since` (and already kicked off),
    in kickoff order; the sample is the first `n` that qualify."""
    from sqlalchemy import select

    from src.db import database
    from src.db.schema import Competition, Match, OddsSnapshot
    from src.timeutil import utc_now_naive

    now = now or utc_now_naive()
    if not database.has_kalshi_ticker():           # ruling 6: no ticker column, no receipt
        return {"competition": competition, "error": "odds_snapshots has no market_ticker column — run "
                "migrate_kalshi_ticker.py first (ruling 6)", "rows": [], "since": since, "n": n,
                "sample": [], "complete": False}
    comp = s.execute(select(Competition).where(Competition.code == competition)).scalars().first()
    if comp is None:
        return {"competition": competition, "error": f"competition {competition} not in DB", "rows": [],
                "since": since, "n": n, "sample": [], "complete": False}
    games = list(s.execute(select(Match).where(
        Match.competition_id == comp.id, Match.utc_date > since, Match.utc_date <= now)
        .order_by(Match.utc_date, Match.id)).scalars())
    rows = []
    for m in games:
        snaps = list(s.execute(select(OddsSnapshot).where(OddsSnapshot.match_id == m.id)).scalars())
        tickers = database.read_kalshi_tickers(s, [x.id for x in snaps if x.source == "kalshi"])
        rows.append(game_row(m, snaps, tickers, since))
    sample = [r for r in rows if r["qualifies"]][:n]
    return {"competition": competition, "since": since, "n": n, "rows": rows,
            "sample": sample, "complete": len(sample) == n}


def skew_test(gaps: list[float], b: int = BOOT_B, seed: int = BOOT_SEED) -> dict:
    """Mean signed gap (pp) and its percentile bootstrap 95% CI (frozen spec)."""
    if not gaps:
        return {"n": 0, "mean_pp": None, "ci95": None, "verdict": None}
    rng = random.Random(seed)
    k = len(gaps)
    means = sorted(sum(rng.choice(gaps) for _ in range(k)) / k for _ in range(b))
    lo, hi = means[int(0.025 * b)], means[int(0.975 * b) - 1]
    structural = lo > 0 or hi < 0
    # ci95 keeps full precision: the verdict and the reported bounds are the same numbers (Codex on #291)
    return {"n": k, "mean_pp": round(sum(gaps) / k, 3), "ci95": (lo, hi),
            "verdict": "STRUCTURAL" if structural else "NOT STRUCTURAL",
            "sign": ("Kalshi above book on the favorite" if lo > 0 else
                     "Kalshi below book on the favorite" if hi < 0 else None)}


def format_receipt(r: dict, with_test: bool) -> str:
    """Plain text for the console and for docs/receipts/ (no DB path, no keys)."""
    if r.get("error"):
        return f"UNL ladder receipt · REFUSED: {r['error']}"
    out = [f"UNL ladder receipt · competition {r['competition']} · games kicking off after "
           f"{r['since']:%Y-%m-%dT%H:%M:%SZ} · sample = first {r['n']} qualifying "
           f"(docs/specs/unl-venue-skew-test.md v2)",
           f"exploratory ids recorded: {len(EXPLORATORY_MATCH_IDS)}/{EXPLORATORY_N} (ruling 1) · "
           f"UNL sync max-spread frozen at {FROZEN_MAX_SPREAD:.2f} (ruling 4)"]

    def f(v, nd=2):
        return "—" if v is None else f"{v:.{nd}f}"
    for row in r["rows"]:
        tag = "SAMPLE" if row in r["sample"] else ("qualifies (beyond n)" if row["qualifies"] else "excluded")
        cap = f"{row['captured_at']:%Y-%m-%dT%H:%M:%SZ}" if row["captured_at"] else "—"
        out.append(f"- match {row['match_id']} {row['away']} @ {row['home']} · kickoff "
                   f"{row['kickoff']:%Y-%m-%dT%H:%M:%SZ} · capture {cap} · series {row['series'] or '—'} · "
                   f"event {row.get('event') or '—'} · "
                   f"two-sided {'yes' if row['two_sided'] else 'NO'} · {tag}")
        for k in LEGS:
            lg = row["legs"].get(k)
            out.append(f"    {k:<4} " + ("no Kalshi leg" if lg is None else
                       f"bid {f(lg['bid'])} ask {f(lg['ask'])} spread {f(lg['spread_c'], 1)}c "
                       f"{'two-sided' if lg['two_sided'] else 'ONE-SIDED'}")
                       + (f" · book {row['book'][k] * 100:.1f}%" if row["book"] else ""))   # book shown either way
        if row.get("book_at") is not None:
            out.append(f"    book session {row['book_at']:%Y-%m-%dT%H:%M:%SZ} · {row['book_n'] or 0} books")
        if row["qualifies"]:
            out.append(f"    favorite {row['favorite']} · gap (Kalshi − book) {row['gap_pp']:+.2f}pp")
        else:
            out.append(f"    excluded: {row['reason']}")
    out.append(f"SAMPLE: {len(r['sample'])}/{r['n']}" + (" (complete)" if r["complete"] else " (incomplete)"))
    if with_test:
        if not r["complete"]:
            out.append(f"SKEW TEST: not run — the frozen sample needs {r['n']} qualifying games "
                       f"({len(r['sample'])} so far)")
        else:
            t = skew_test([row["gap_pp"] for row in r["sample"]])
            out.append(f"SKEW TEST (frozen): n {t['n']} · mean gap {t['mean_pp']:+.3f}pp · bootstrap 95% CI "
                       f"[{t['ci95'][0]:+.6f}, {t['ci95'][1]:+.6f}] (B {BOOT_B}, seed {BOOT_SEED}) · "
                       f"{t['verdict']}" + (f" ({t['sign']})" if t["sign"] else ""))
    return "\n".join(out)
