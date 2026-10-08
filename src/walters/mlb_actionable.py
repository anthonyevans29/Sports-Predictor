"""MLB actionable receipt (READ-ONLY): tier x edge-vs-close over graded MLB predictions.

ARCHITECT 2026-10-07 (item 2, read-only receipt, NO policy change). Finding:
"The prediction layer labels a top pick under 53% 'toss-up, no actionable
side' (src/web/preview.py; actionable=false in the export). Desk v1.1 does not
read that flag on MLB (POLICY MLB pMin 0) ... The layers disagree on a rule;
the Desk stands until measured." This module measures it.

Definitions (read from the code, law 1):
- graded prediction: a `predictions` row with a `prediction_outcomes` row whose
  `top_pick_hit` is set (evaluate writes it; tied finals are never graded).
  `predictions` is current-only per match (S13), so there is one per game.
- top pick: max(home, away) with HOME on a tie, the export's and evaluate's rule
  (evaluation.score_winner: hit = p_home >= p_away when home won).
- tier: `src.web.preview.classify_tier(top_p, starter_known)`, with
  starter_known computed exactly as the export does (both
  `factor_breakdown.{home,away}_starter_known`, default True). Not reimplemented.
- the close: `src.walters.close.grading_close` (the one grading definition,
  #167/#207 + the snapshot fallback). Only a BOOK close counts
  (reference == "books"); a kalshi_only close is excluded and counted.
  Unpriced / absent closes are excluded and counted (law 4).
- edge (pp) = (model p on the pick − close fair p on the same side) × 100.
  Buckets: < 0, 0–4, 4–8, 8–15, >= 15 (lower bound inclusive; negative edges get their own bucket,
  ARCHITECT 2026-10-07 addendum 3 D, and their count is also in the header).
- stage: `export.mlb_stage(Match.stage)` — regular / postseason / unknown (null).
- hit − close (pp) = (hit rate − mean close fair p) × 100, with a percentile
  bootstrap 95% CI (games resampled within the cell, B = BOOT_B, seed BOOT_SEED;
  n < 2 -> no CI).
- ROI at the close fair price: stake 1 at decimal odds 1/fair on the pick:
  +(1/fair − 1) on a hit, −1 on a miss; ROI = sum / n.
- blend (Q3 K6, ARCHITECT 2026-10-08: "The #354 receipt splits by that record: blended, model alone, not
  recorded. Nothing is inferred for a row with no record."): read from the prediction's own
  `factor_breakdown.market_blend` (written by predict from that PR on): applied true -> blended, applied false ->
  model alone, no record -> not recorded. Never inferred from the config, the close or the version.
Writes nothing to the DB.
"""
from __future__ import annotations

import random

TIERS = ("toss-up", "lean", "strong")
BUCKETS = ("<0", "0-4", "4-8", "8-15", ">=15")      # ARCHITECT 2026-10-07 (addendum 3 D): negatives own bucket
STAGES = ("regular", "postseason", "unknown")
BLENDS = ("blended", "model alone", "not recorded")    # Q3 K6: the prediction's own record, nothing inferred
BOOT_B = 10_000
BOOT_SEED = 20261007          # pinned: the ruling's date
EDGE_ROUND = 9                # float hygiene only: 0.58 - 0.54 must bucket as 4.0pp, not 3.9999999


def edge_bucket(edge_pp: float) -> str:
    """< 0 | 0-4 | 4-8 | 8-15 | >= 15 (pp); each bound belongs to the bucket ABOVE it (0.0 is 0-4)."""
    e = round(edge_pp, EDGE_ROUND)
    if e < 0:
        return "<0"
    if e < 4:
        return "0-4"
    if e < 8:
        return "4-8"
    if e < 15:
        return "8-15"
    return ">=15"


def top_pick(p_home: float, p_away: float) -> tuple[str, float]:
    """The export's / evaluate's top pick: HOME on a tie."""
    return ("HOME", p_home) if p_home >= p_away else ("AWAY", p_away)


def tier_of(top_p: float, factor_breakdown: dict | None) -> dict:
    """The prediction layer's tier, with starter_known derived as export.py derives it."""
    from src.web.preview import classify_tier

    fb = factor_breakdown or {}
    starter_known = fb.get("home_starter_known", True) and fb.get("away_starter_known", True)
    return classify_tier(top_p, starter_known=starter_known)


def blend_of(factor_breakdown: dict | None) -> str:
    """Q3 K6: 'blended' | 'model alone' | 'not recorded', from factor_breakdown.market_blend.applied ONLY. A row
    with no record (predicted before K6), or a record whose `applied` is not a bool, is 'not recorded'."""
    rec = (factor_breakdown or {}).get("market_blend")
    applied = rec.get("applied") if isinstance(rec, dict) else None
    if applied is True:
        return "blended"
    if applied is False:
        return "model alone"
    return "not recorded"


def roi_unit(hit: bool, fair: float) -> float:
    """Profit of a 1-unit stake at decimal odds 1/fair."""
    return (1.0 / fair - 1.0) if hit else -1.0


def bootstrap_ci(pairs: list[tuple[int, float]], b: int = BOOT_B, seed: int = BOOT_SEED):
    """Percentile 95% CI (pp) of (hit rate − mean fair) over games resampled within the cell.
    pairs = [(hit 0/1, fair p)]. None when n < 2."""
    k = len(pairs)
    if k < 2:
        return None
    rng = random.Random(seed)
    d = [h - f for h, f in pairs]          # hit − fair per game; the cell statistic is their mean
    stats = [sum(rng.choices(d, k=k)) / k * 100 for _ in range(b)]
    stats.sort()
    return stats[int(0.025 * b)], stats[int(0.975 * b) - 1]


def cell_stats(rows: list[dict], b: int = BOOT_B, seed: int = BOOT_SEED) -> dict:
    """n, mean model p, mean close fair p, hit rate, hit − close (pp) + CI, ROI at close fair."""
    n = len(rows)
    if n == 0:
        return {"n": 0}
    pairs = [(1 if r["hit"] else 0, r["fair"]) for r in rows]
    hit = sum(h for h, _ in pairs) / n
    fair = sum(f for _, f in pairs) / n
    return {"n": n, "model_p": sum(r["model_p"] for r in rows) / n, "fair_p": fair, "hit": hit,
            "hit_minus_close_pp": (hit - fair) * 100, "ci95": bootstrap_ci(pairs, b, seed),
            "roi": sum(roi_unit(r["hit"], r["fair"]) for r in rows) / n}


def grade_row(*, match_id, stage_raw, p_home, p_away, factor_breakdown, hit, close) -> dict:
    """One graded prediction -> a receipt row, or {"excluded": reason}. `close` is grading_close's result."""
    from src.walters.close import priced
    from src.walters.export import mlb_stage

    side, p = top_pick(p_home, p_away)
    t = tier_of(p, factor_breakdown)
    base = {"match_id": match_id, "side": side, "model_p": p, "tier": t["tier"],
            "actionable": t["actionable"],
            "capped_by_starter": t["capped_by_starter"], "stage": mlb_stage(stage_raw) or "unknown", "hit": bool(hit),
            "blend": blend_of(factor_breakdown)}
    if not priced(close):
        return {**base, "excluded": "no close (no pre-first-pitch capture, or unpriced)"}
    if close.get("reference") != "books":
        return {**base, "excluded": f"close is not a book close (reference={close.get('reference')})"}
    fair = close["fair"].get(side)
    if fair is None or not (0.0 < fair < 1.0):
        return {**base, "excluded": "no close fair price on the pick side"}
    edge_pp = (p - fair) * 100
    return {**base, "fair": fair, "edge_pp": edge_pp, "bucket": edge_bucket(edge_pp),
            "close_source": close.get("source")}


def collect(s, season: str = "2026") -> list[dict]:
    """Every graded MLB prediction of the season, one row each (included or excluded). Read-only."""
    from sqlalchemy import select

    from src.db.schema import Match, Prediction, PredictionOutcome, Sport
    from src.walters.close import grading_close

    q = (select(Prediction, PredictionOutcome, Match)
         .join(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
         .join(Match, Match.id == Prediction.match_id)
         .where(Match.sport == Sport.MLB, Match.season == str(season),
                PredictionOutcome.top_pick_hit.isnot(None))
         .order_by(Match.utc_date, Match.id))
    out = []
    for pred, oc, m in s.execute(q).all():
        if pred.home_win_prob is None or pred.away_win_prob is None:
            out.append({"match_id": m.id, "excluded": "prediction has a null side probability"})
            continue
        r = grade_row(match_id=m.id, stage_raw=m.stage, p_home=pred.home_win_prob, p_away=pred.away_win_prob,
                      factor_breakdown=pred.factor_breakdown, hit=oc.top_pick_hit, close=grading_close(s, m))
        r["post_first_pitch"] = (pred.computed_at is not None and m.utc_date is not None
                                 and pred.computed_at >= m.utc_date)
        r["model_version"] = pred.model_version
        out.append(r)
    return out


def receipt(rows: list[dict], b: int = BOOT_B, seed: int = BOOT_SEED) -> dict:
    """Pure: the tables from collected rows."""
    inc = [r for r in rows if "excluded" not in r]
    exc = [r for r in rows if "excluded" in r]
    reasons: dict[str, int] = {}
    for r in exc:
        reasons[r["excluded"]] = reasons.get(r["excluded"], 0) + 1
    tables = {}
    for st in STAGES:
        sr = [r for r in inc if r["stage"] == st]
        cells = []
        for t in TIERS:
            for bk in BUCKETS:
                cells.append((t, bk, cell_stats([r for r in sr if r["tier"] == t and r["bucket"] == bk], b, seed)))
            cells.append((t, "all", cell_stats([r for r in sr if r["tier"] == t], b, seed)))
        cells.append(("all", "all", cell_stats(sr, b, seed)))
        tables[st] = {"n": len(sr), "cells": cells}
    # Q3 K6: the blend split (blended / model alone / not recorded) x tier, all stages, included rows only
    blend = {bl: {"n": sum(1 for r in inc if r.get("blend", "not recorded") == bl),
                  "cells": [(t, cell_stats([r for r in inc if r.get("blend", "not recorded") == bl
                                            and r["tier"] == t], b, seed)) for t in TIERS]
                  + [("all", cell_stats([r for r in inc if r.get("blend", "not recorded") == bl], b, seed))]}
             for bl in BLENDS}
    versions: dict[str, int] = {}
    for r in inc:
        versions[r.get("model_version") or "?"] = versions.get(r.get("model_version") or "?", 0) + 1
    return {"graded": len(rows), "included": len(inc), "excluded": len(exc), "reasons": reasons,
            "tables": tables, "blend": blend, "negative_edge": sum(1 for r in inc if r["bucket"] == "<0"),   # the bucket, not the raw float (Codex on #324)
            "post_first_pitch": sum(1 for r in inc if r.get("post_first_pitch")),
            "capped": sum(1 for r in inc if r.get("capped_by_starter")),
            "versions": versions, "b": b, "seed": seed}


def _f(x, fmt):
    return "—" if x is None else format(x, fmt)


def format_receipt(res: dict, season: str, run_stamp: str) -> str:
    """Markdown for the console and docs/receipts/ (no DB path, no keys)."""
    L = [f"# MLB actionable receipt · season {season} · run {run_stamp}", "",
         "READ-ONLY (ARCHITECT 2026-10-07, item 2; NO policy change). Tier (the prediction layer's "
         "`classify_tier`, src/web/preview.py: toss-up < 53% = actionable false) x edge bucket.", "",
         "**THE EDGE IS AGAINST THE CLOSE, NOT THE DESK'S T-60 REFERENCE.** Edge = model p on the pick − "
         "close fair p on the same side (pp), the close = `grading_close` (last pre-first-pitch BOOK session, "
         "complete books de-vigged then averaged; src/walters/close.py). Prediction history exists only "
         "from 2026-10-06, so the close is a PROXY for the Desk's T-60 reference.", "",
         f"- graded MLB predictions (season {season}): {res['graded']}",
         f"- included (book close on the pick): {res['included']}",
         f"- EXCLUDED: {res['excluded']}"]
    for k, v in sorted(res["reasons"].items()):
        L.append(f"  - {k}: {v}")
    L += [f"- included tiered lean by the starter cap (top p >= 60%, a starter unconfirmed): {res['capped']}",
          f"- included with edge < 0 (the `<0` bucket): {res['negative_edge']}",
          f"- included whose stored prediction was computed at/after first pitch (kept, flagged): "
          f"{res['post_first_pitch']}",
          "- model versions (included): " + (", ".join(f"{k} {v}" for k, v in sorted(res["versions"].items()))
                                             or "none"),
          f"- bootstrap: games resampled within the cell, B {res['b']}, seed {res['seed']}, percentile 95% CI; "
          "n < 2 -> —",
          "- ROI: stake 1 at decimal odds 1/(close fair p) on the pick (zero-vig close price)", ""]
    titles = {"regular": "Regular season (stage R)", "postseason": "Postseason (stage F/D/L/W)",
              "unknown": "Stage unknown (stage null or unmapped; never guessed)"}
    for st in STAGES:
        t = res["tables"][st]
        L += [f"## {titles[st]} · n {t['n']}", "",
              "| tier | edge vs close | n | mean model p | mean close fair p | hit rate | hit − close (pp) "
              "| 95% CI (pp) | ROI @ close fair |",
              "|---|---|---:|---:|---:|---:|---:|---|---:|"]
        for tier, bk, c in t["cells"]:
            label = bk if bk == "all" else f"{bk}pp"
            if c["n"] == 0:
                L.append(f"| {tier} | {label} | 0 | — | — | — | — | — | — |")
                continue
            ci = "—" if c["ci95"] is None else f"[{c['ci95'][0]:+.1f}, {c['ci95'][1]:+.1f}]"
            L.append(f"| {tier} | {label} | {c['n']} | {_f(c['model_p'], '.3f')} | {_f(c['fair_p'], '.3f')} | "
                     f"{_f(c['hit'], '.3f')} | {c['hit_minus_close_pp']:+.1f} | {ci} | {c['roi'] * 100:+.1f}% |")
        L.append("")
    if "blend" in res:
        L += ["## By market-blend record (Q3 K6, all stages) · " + " · ".join(
                  f"{bl} {res['blend'][bl]['n']}" for bl in BLENDS), "",
              "The prediction's own `factor_breakdown.market_blend` record; a row predicted before it was written is "
              "'not recorded' (nothing inferred).", "",
              "| blend | tier | n | mean model p | mean close fair p | hit rate | hit − close (pp) | 95% CI (pp) "
              "| ROI @ close fair |",
              "|---|---|---:|---:|---:|---:|---:|---|---:|"]
        for bl in BLENDS:
            for tier, c in res["blend"][bl]["cells"]:
                if c["n"] == 0:
                    L.append(f"| {bl} | {tier} | 0 | — | — | — | — | — | — |")
                    continue
                ci = "—" if c["ci95"] is None else f"[{c['ci95'][0]:+.1f}, {c['ci95'][1]:+.1f}]"
                L.append(f"| {bl} | {tier} | {c['n']} | {_f(c['model_p'], '.3f')} | {_f(c['fair_p'], '.3f')} | "
                         f"{_f(c['hit'], '.3f')} | {c['hit_minus_close_pp']:+.1f} | {ci} | {c['roi'] * 100:+.1f}% |")
        L.append("")
    return "\n".join(L).rstrip() + "\n"
