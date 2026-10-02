"""
#167 RECEIPTS (ARCHITECT-RULE 2026-10-01, priority): "(a) verify on the real
DB whether the general sync_odds path appends rather than replaces, drops the
totals/spread line, and averages captures for the 'close'; (b) if confirmed,
closing price = LAST pre-kickoff capture, with a receipt of how many stored
soccer/NHL/NCAA CLV grades change and by how much ..."

`audit()`   — read-only (a): per odds source, how many matches hold MORE THAN
              ONE capture session (append evidence), the NULL-line rate on
              line markets, rows captured at/after kickoff, and how far the
              legacy "average of every row" sits from the last pre-kickoff
              session's fair prob on 1X2.
`restate()` — (b): every stored PredictionOutcome's CLV recomputed with the
              ruled close (src/walters/close.py) vs the stored value, by sport
              and competition. DRY-RUN by default (writes nothing); `apply=True`
              updates clv / closing_price / closing_bookmaker in one
              transaction — the CLI gates it on a verified .backup (law 5).
              A grade the ruled close cannot price (no pre-kickoff capture)
              is counted "became_null" and LEFT AS STORED (never nulled).
NFL and NHL-shadow CLVs are not stored (computed when graded), and NCAA has
no model CLV at all; those are reported as such, never faked.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from src.walters.close import CAPTURE_SESSION, close_1x2, close_from_snapshots, outcomes_for, priced

LINE_MARKETS_HINT = ("TOTALS", "SPREADS", "OU_", "SPREAD")


def legacy_fair(rows) -> dict | None:
    """The PRE-#167 close: every 1X2 row of the match de-vigged at once."""
    from src.walters.value import MarketSnapshot
    one = [o for o in rows if o.market == "1X2"]
    if not one:
        return None
    by: dict = {}
    for o in one:
        by.setdefault(o.selection, []).append((o.bookmaker, o.price_decimal))
    imp = MarketSnapshot(market="1X2", by_selection=by).average_implied()
    over = sum(imp.values())
    return {k: v / over for k, v in imp.items()} if over > 0 else None


def sessions(rows) -> int:
    """Distinct capture sessions (gaps > CAPTURE_SESSION start a new one)."""
    ts = sorted(o.captured_at for o in rows if o.captured_at is not None)
    n, last = 0, None
    for t in ts:
        if last is None or t - last > CAPTURE_SESSION:
            n += 1
        last = t
    return n


def audit() -> dict:
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Match, Odds

    per = defaultdict(Counter)
    gap = defaultdict(list)
    with session_scope() as s:
        kick, sport_of = {}, {}
        for mid_, ko_, sp_ in s.execute(select(Match.id, Match.utc_date, Match.sport)).all():
            kick[mid_], sport_of[mid_] = ko_, sp_
        by_match: dict = defaultdict(list)
        for o in s.execute(select(Odds)).scalars():
            by_match[(o.source, o.match_id)].append(o)
    for (src, mid), rows in by_match.items():
        c = per[src or "(none)"]
        c["matches"] += 1
        c["rows"] += len(rows)
        n = sessions(rows)
        c["matches_multi_session"] += n > 1
        c["max_sessions"] = max(c["max_sessions"], n)
        ko = kick.get(mid)
        c["rows_at_or_after_kickoff"] += sum(1 for o in rows if ko and o.captured_at and o.captured_at >= ko)
        lm = [o for o in rows if o.market != "1X2" and any(h in (o.market or "") for h in LINE_MARKETS_HINT)]
        c["line_market_rows"] += len(lm)
        c["line_market_null_line"] += sum(1 for o in lm if o.line is None)
        old, new = legacy_fair(rows), close_1x2(rows, ko, outcomes_for(sport_of.get(mid)))
        if old and priced(new) and "HOME" in old and "HOME" in new["fair"]:
            gap[src or "(none)"].append(abs(old["HOME"] - new["fair"]["HOME"]) * 100)
    out = {}
    for src, c in sorted(per.items()):
        g = sorted(gap[src])
        out[src] = {**dict(c), "home_gap_pp_mean": round(sum(g) / len(g), 2) if g else None,
                    "home_gap_pp_max": round(g[-1], 2) if g else None, "home_gap_n": len(g)}
    return out


def _top(pred) -> str | None:
    probs = {"HOME": pred.home_win_prob or 0.0, "DRAW": pred.draw_prob or 0.0,
             "AWAY": pred.away_win_prob or 0.0}
    probs = {k: v for k, v in probs.items() if v > 0}
    return max(probs, key=probs.get) if probs else None


def _close_for(odds_rows, snaps, match):
    """grading_close (src/walters/close.py) over pre-fetched rows: the odds
    table's contract close, else the last complete pre-kickoff snapshot."""
    oc_ = outcomes_for(match.sport)
    cl = close_1x2(odds_rows, match.utc_date, oc_) if odds_rows else None
    if priced(cl):
        return cl
    return close_from_snapshots(snaps or [], match.utc_date, oc_) or cl


def clv_cohort(oc, pred, match, odds_rows, snaps=()) -> str | None:
    """P0-2 (#207): which cohort a STORED CLV belongs to. "verified" when the
    contract close (complete books, src/walters/close.py) prices the top pick
    and reproduces the stored value; "legacy" for any other stored CLV
    (graded under an older close and retained); None when nothing is stored.
    Read-only: the stored value is never changed here."""
    if oc.clv is None:
        return None
    top = _top(pred)
    cl = _close_for(odds_rows, snaps, match)
    if top and priced(cl) and top in cl["fair"]:
        p = {"HOME": pred.home_win_prob, "DRAW": pred.draw_prob, "AWAY": pred.away_win_prob}[top]
        if p is not None and abs((p - cl["fair"][top]) - oc.clv) <= 1e-6:
            return "verified"
    return "legacy"


def restate(apply: bool = False) -> dict:
    """Stored CLV vs the ruled close, per sport/competition. apply=True writes."""
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Competition, Match, Odds, OddsSnapshot, Prediction, PredictionOutcome

    agg: dict = defaultdict(lambda: {"n": 0, "changed": 0, "to_null": 0, "from_null": 0,
                                     "d": [], "old": [], "new": [], "price_changed": 0})
    examples = []
    with session_scope() as s:
        comp_code = dict(s.execute(select(Competition.id, Competition.code)).all())
        rows = s.execute(select(PredictionOutcome, Prediction, Match)
                         .join(Prediction, Prediction.id == PredictionOutcome.prediction_id)
                         .join(Match, Match.id == Prediction.match_id)).all()
        odds_by: dict = defaultdict(list)
        ids = {m.id for _, _, m in rows}
        for o in s.execute(select(Odds).where(Odds.market == "1X2", Odds.match_id.in_(ids))).scalars():
            odds_by[o.match_id].append(o)
        snaps_by: dict = defaultdict(list)
        for x in s.execute(select(OddsSnapshot).where(OddsSnapshot.market == "1X2",
                                                      OddsSnapshot.source != "kalshi",
                                                      OddsSnapshot.match_id.in_(ids))).scalars():
            snaps_by[x.match_id].append(x)
        for oc, pred, m in rows:
            key = (m.sport.value if m.sport else "?", comp_code.get(m.competition_id, "?"))
            a = agg[key]
            a["n"] += 1
            top = _top(pred)
            cl = _close_for(odds_by.get(m.id, []), snaps_by.get(m.id, []), m)
            new = None
            price, book = None, None
            if top and priced(cl) and top in cl["fair"]:
                p = {"HOME": pred.home_win_prob, "DRAW": pred.draw_prob, "AWAY": pred.away_win_prob}[top]
                new = p - cl["fair"][top]
                best = cl["best"].get(top)
                if best:
                    book, price = best
            old = oc.clv
            if old is None and new is None:
                continue
            if old is None:
                a["from_null"] += 1
            elif new is None:
                a["to_null"] += 1
            elif abs(new - old) > 1e-6:
                a["changed"] += 1
                a["d"].append((new - old) * 100)
                a["old"].append(old * 100)
                a["new"].append(new * 100)
                if len(examples) < 15:
                    examples.append(f"{m.utc_date:%Y-%m-%d} match {m.id} [{key[1]}] {top}: "
                                    f"{old * 100:+.2f}pp -> {new * 100:+.2f}pp")
            if price is not None and oc.closing_price is not None and abs(price - oc.closing_price) > 1e-9:
                a["price_changed"] += 1
            # a grade the ruled close cannot price (no pre-kickoff capture) is
            # REPORTED, never nulled by the restate (ARCHITECT-RULE if it should be)
            if apply and new is not None and (old is None or abs(new - old) > 1e-6
                                              or (price is not None and price != oc.closing_price)):
                oc.clv = new
                oc.closing_price, oc.closing_bookmaker = price, book
        if not apply:
            s.rollback()
    summary = {}
    for (sport, comp), a in sorted(agg.items()):
        d = a["d"]
        mean = lambda v: round(sum(v) / len(v), 3) if v else None
        summary[f"{sport}/{comp}"] = {
            "graded": a["n"], "changed": a["changed"], "became_null": a["to_null"],
            "newly_priced": a["from_null"], "closing_price_changed": a["price_changed"],
            "mean_delta_pp": mean(d), "mean_abs_delta_pp": mean([abs(x) for x in d]),
            "max_abs_delta_pp": round(max((abs(x) for x in d), default=0), 3) if d else None,
            "mean_clv_old_pp": mean(a["old"]), "mean_clv_new_pp": mean(a["new"])}
    return {"applied": apply, "by_scope": summary, "examples": examples,
            "not_stored": {"NFL": "graded on the fly (grade-nfl); re-run grading for the restated close",
                           "NHL": "shadow-only, graded on the fly from exports (nhl-shadow-grade)",
                           "NCAA": "market-only: no model CLV exists"}}
