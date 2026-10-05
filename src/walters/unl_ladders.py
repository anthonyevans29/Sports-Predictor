"""UNL ladder receipt + the frozen favorite-skew test (READ-ONLY).

ARCHITECT 2026-10-05 (#286, ruling 3): "a read-only receipt command printing
per-game rows (match, legs, bid/ask, spread, two-sided, capture time, series);
its output for the 30 is committed under docs/receipts/ via PR."

The sample and the test follow docs/specs/unl-venue-skew-test.md (FROZEN):
- the first N UNL games kicking off after the freeze cutoff whose LAST
  pre-kickoff Kalshi capture (taken after the cutoff) is two-sided on all three
  legs, in series KXUEFANLGAME, with a complete pre-kickoff book session;
- gap = Kalshi (three-leg normalized mids) − book, on the book favorite, in pp;
- mean gap, bootstrap B=10,000 seed 20261005, percentile 95% CI;
  STRUCTURAL when the CI excludes 0.
Every game is listed, the non-qualifying ones with their reason. Writes
nothing to the DB.
"""
from __future__ import annotations

import random
from datetime import datetime

FREEZE_CUTOFF = datetime(2026, 10, 5, 17, 0)        # naive UTC, as the DB stores it
SAMPLE_N = 30
SERIES = "KXUEFANLGAME"
LEGS = ("HOME", "DRAW", "AWAY")
BOOT_B = 10_000
BOOT_SEED = 20261005


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


def _last_two_sided_board(kal, kickoff):
    """(captured_at, {leg: snapshot}) of the LAST pre-kickoff Kalshi capture, and
    whether all three legs are two-sided there. Never substitutes an earlier one."""
    pre = [x for x in kal if x.captured_at is not None and kickoff is not None and x.captured_at < kickoff]
    if not pre:
        return None, {}, False
    t = max(x.captured_at for x in pre)
    legs = {x.selection: x for x in pre if x.captured_at == t and x.selection in LEGS}
    two = len(legs) == 3 and all(legs[k].yes_bid is not None and legs[k].yes_ask is not None for k in LEGS)
    return t, legs, two


def _book_session(book, kickoff):
    from src.walters.close import close_from_snapshots
    return close_from_snapshots(book, kickoff, LEGS)


def game_row(m, snaps, tickers: dict, since: datetime) -> dict:
    """One receipt row for match `m` from its odds_snapshots."""
    kal = [x for x in snaps if x.source == "kalshi" and x.market == "1X2"]
    book = [x for x in snaps if x.source != "kalshi" and x.market == "1X2"]
    t, legs, two = _last_two_sided_board(kal, m.utc_date)
    row = {"match_id": m.id, "kickoff": m.utc_date, "status": getattr(m.status, "value", m.status),
           "home": m.home_team.name if m.home_team else "?", "away": m.away_team.name if m.away_team else "?",
           "captured_at": t, "two_sided": two, "legs": {}, "series": None, "book": None,
           "favorite": None, "gap_pp": None, "qualifies": False, "reason": None}
    series = set()
    for k in LEGS:
        x = legs.get(k)
        if x is None:
            row["legs"][k] = None
            continue
        tk = tickers.get(x.id)
        series.add(series_of(tk))
        spread = (x.yes_ask - x.yes_bid) * 100 if x.yes_bid is not None and x.yes_ask is not None else None
        row["legs"][k] = {"bid": x.yes_bid, "ask": x.yes_ask,
                          "spread_c": round(spread, 1) if spread is not None else None,
                          "two_sided": x.yes_bid is not None and x.yes_ask is not None, "ticker": tk}
    # every present leg needs a stored ticker (Codex on #291): a missing one makes the
    # series UNKNOWN, never certified by the legs that do carry one
    row["series"] = None if (not series or None in series) else ",".join(sorted(series))
    cl = _book_session(book, m.utc_date)
    if cl is not None:
        row["book"] = {k: cl["fair"][k] for k in LEGS}
    # reasons, in order (the first failing criterion is reported)
    if m.utc_date is None or m.utc_date <= since:
        row["reason"] = "kickoff not after the freeze cutoff"
    elif t is None:
        row["reason"] = "no pre-kickoff Kalshi capture"
    elif t <= since:                         # strictly AFTER the cutoff (Codex on #291)
        row["reason"] = "last Kalshi capture not after the freeze cutoff"
    elif not two:
        row["reason"] = "one-sided board (ruling 2)"
    elif row["series"] != SERIES:
        row["reason"] = f"series {row['series'] or 'UNKNOWN (no stored ticker)'} is not {SERIES}"
    elif cl is None:
        row["reason"] = "no complete pre-kickoff book session"
    else:
        mids = {k: (legs[k].yes_bid + legs[k].yes_ask) / 2 for k in LEGS}
        tot = sum(mids.values())
        kn = {k: mids[k] / tot for k in LEGS} if tot > 0 else None
        ranked = sorted(LEGS, key=lambda k: row["book"][k], reverse=True)
        if kn is None:
            row["reason"] = "Kalshi mids sum to 0"
        elif round(row["book"][ranked[0]], 4) == round(row["book"][ranked[1]], 4):
            row["reason"] = "tied book favorite"
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

    from src.db.database import read_kalshi_tickers
    from src.db.schema import Competition, Match, OddsSnapshot
    from src.timeutil import utc_now_naive

    now = now or utc_now_naive()
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
        tickers = read_kalshi_tickers(s, [x.id for x in snaps if x.source == "kalshi"])
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
           f"(docs/specs/unl-venue-skew-test.md)"]

    def f(v, nd=2):
        return "—" if v is None else f"{v:.{nd}f}"
    for row in r["rows"]:
        tag = "SAMPLE" if row in r["sample"] else ("qualifies (beyond n)" if row["qualifies"] else "excluded")
        cap = f"{row['captured_at']:%Y-%m-%dT%H:%M:%SZ}" if row["captured_at"] else "—"
        out.append(f"- match {row['match_id']} {row['away']} @ {row['home']} · kickoff "
                   f"{row['kickoff']:%Y-%m-%dT%H:%M:%SZ} · capture {cap} · series {row['series'] or '—'} · "
                   f"two-sided {'yes' if row['two_sided'] else 'NO'} · {tag}")
        for k in LEGS:
            lg = row["legs"].get(k)
            out.append(f"    {k:<4} " + ("no leg" if lg is None else
                       f"bid {f(lg['bid'])} ask {f(lg['ask'])} spread {f(lg['spread_c'], 1)}c "
                       f"{'two-sided' if lg['two_sided'] else 'ONE-SIDED'}"
                       + (f" · book {row['book'][k] * 100:.1f}%" if row["book"] else "")))
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
