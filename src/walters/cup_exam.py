"""
Cup acceptance exam — scoring (spec frozen 2026-09-25, BEFORE results).

Scores production soccer pricing of FINISHED cup fixtures against the
books' consensus fair in exports/cup_answer_key.csv (built by
scripts/extract_cup_key.py). Pricing comes from the report-only mode of
training._generate_predictions_soccer(include_finished=True) — nothing is
ever written to the Prediction table.

The frozen bar:
  * PASS needs mean |Δ_HOME| <= 8.0pp AND at most 13 fixtures with
    |Δ_HOME| > 8pp.
  * Sign check (pass/fail): on the EFL round-2 subset the model's favorite
    must match the market's in >= 80% of rows; < 50% = systematic
    inversion (the league-bonus defect) = automatic FAIL.
  * Key rows are joined to the DB by match_id only (no name matching).
    More than 2 key rows missing from the priced set = exam INVALID
    (data drift — stop and report).

Verdict semantics (architect, 2026-09-25): necessary-not-sufficient.
Report-only pricing of finished fixtures sees same-season results (strengths
window, v22 Elo, current injuries/lineups), so FAIL is damning but PASS
certifies "no gross cup-path defect" only — not out-of-sample accuracy. The
sign/inversion check is the decisive organ.

Everything below is pure (no DB) so the verdict logic is unit-tested.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field

MAE_BAR_PP = 8.0
MAX_OVER_BAR = 13
ROW_BAR_PP = 8.0
SIGN_PASS_SHARE = 0.80
SIGN_INVERSION_SHARE = 0.50
MAX_MISSING = 2
# Coverage floor (architect amendment 2026-09-25): ruling-B market-only rows
# are excluded, but if fewer than this many fixtures remain scored the exam
# no longer means what it was frozen to mean -> INVALID (insufficient coverage).
MIN_SCORED = 45

# Fallback when the key's stage strings don't identify EFL round 2.
ROUND2_FALLBACK_DATES = {"2026-09-16", "2026-09-17"}
_ROUND2_RE = re.compile(r"\b(2nd|second)\s+round\b|\bround\s*(2|two)\b", re.I)


# Report-row fields surfaced by `cup-exam --detail` (no pricing change).
DETAIL_KEYS = ("home_elo", "away_elo", "home_league", "away_league",
               "home_in_pot", "away_in_pot", "home_league_elo", "away_league_elo",
               "home_cup_elo", "away_cup_elo", "default_elo",
               # strength-fit receipts (architect hypothesis check 2026-09-25)
               "fit_pool_n", "strengths_backfilled", "self_in_fit",
               "home_fit_n", "away_fit_n", "home_strengths_source", "away_strengths_source",
               "home_attack", "home_defense", "away_attack", "away_defense",
               "elo_goal_coeff",
               # cup fix: domestic borrow receipts
               "home_dom_league", "away_dom_league", "home_dom_n", "away_dom_n",
               "home_cup_w", "away_cup_w")


def load_key(path: str) -> list[dict]:
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["match_id"] = int(r["match_id"])
        for k in ("fair_home", "fair_draw", "fair_away"):
            r[k] = float(r[k])
    return rows


def favorite(p_home: float, p_away: float) -> str:
    """Two-way favorite; the draw is never the favorite for this check."""
    if p_home > p_away:
        return "HOME"
    if p_away > p_home:
        return "AWAY"
    return "EVEN"


@dataclass
class ExamResult:
    rows: list[dict] = field(default_factory=list)       # scored fixtures
    missing: list[dict] = field(default_factory=list)    # UNMATCHED / UNPRICED
    # Ruling B (architect 2026-09-25): policy exclusions, NOT data drift —
    # reported, unscored, and outside the > MAX_MISSING INVALID budget.
    market_only: list[dict] = field(default_factory=list)
    efl_stages_seen: list[str] = field(default_factory=list)
    sign_selector: str = ""
    sign_n: int = 0
    sign_agree: int = 0
    n_scored: int = 0
    mae_home_pp: float | None = None
    mae_all_pp: float | None = None
    n_over: int = 0
    worst: dict | None = None
    invalid: bool = False           # data drift (> MAX_MISSING unmatched/unpriced)
    under_coverage: bool = False    # scored n < MIN_SCORED
    mae_pass: bool = False
    over_pass: bool = False
    sign_share: float | None = None
    sign_pass: bool = False
    inversion: bool = False
    verdict: str = ""


def select_round2(efl_rows: list[dict]) -> tuple[list[dict], str, list[str]]:
    """EFL round-2 subset: by stage when stages distinguish rounds, else by
    the Sept 16-17 date cluster. Returns (rows, selector used, stages seen)."""
    stages = sorted({r["stage"] for r in efl_rows if r.get("stage")})
    by_stage = [r for r in efl_rows if _ROUND2_RE.search(r.get("stage") or "")]
    if len(stages) > 1 and by_stage:
        return by_stage, "stage", stages
    by_date = [r for r in efl_rows if r["date"] in ROUND2_FALLBACK_DATES]
    return by_date, "date-fallback (2026-09-16/17)", stages


def score_exam(key_rows: list[dict], priced: dict[int, dict],
               known_match_ids: set[int], min_scored: int = MIN_SCORED) -> ExamResult:
    """
    key_rows: answer-key rows (load_key). priced: match_id -> report row
    from the report-only pricing path. known_match_ids: key match_ids that
    exist in the DB (anything else is UNMATCHED; in the DB but not priced
    is UNPRICED — e.g. no strengths).
    """
    res = ExamResult()
    for k in key_rows:
        mid = k["match_id"]
        if mid not in known_match_ids:
            res.missing.append({**k, "why": "UNMATCHED"})
            continue
        p = priced.get(mid)
        if p is None:
            res.missing.append({**k, "why": "UNPRICED"})
            continue
        if p.get("market_only"):
            res.market_only.append({**k, "why": f"MARKET-ONLY (ruling B): {p['market_only']}"})
            continue
        d_home = (p["p_home"] - k["fair_home"]) * 100
        d_draw = (p["p_draw"] - k["fair_draw"]) * 100
        d_away = (p["p_away"] - k["fair_away"]) * 100
        res.rows.append({
            "match_id": mid, "date": k["date"], "comp": k["comp"],
            "stage": k.get("stage", ""), "home": k["home"], "away": k["away"],
            "fair_H": k["fair_home"], "model_H": p["p_home"],
            "delta_pp": d_home, "abs_all": (abs(d_home), abs(d_draw), abs(d_away)),
            "fav_market": favorite(k["fair_home"], k["fair_away"]),
            "fav_model": favorite(p["p_home"], p["p_away"]),
            "home_league_bonus": p.get("home_league_bonus"),
            "away_league_bonus": p.get("away_league_bonus"),
            # --detail diagnostics, carried verbatim from the report row
            **{k: p.get(k) for k in DETAIL_KEYS},
            "flag": "",
        })

    res.invalid = len(res.missing) > MAX_MISSING
    res.n_scored = len(res.rows)
    res.under_coverage = res.n_scored < min_scored
    if res.rows:
        res.mae_home_pp = sum(abs(r["delta_pp"]) for r in res.rows) / res.n_scored
        res.mae_all_pp = sum(sum(r["abs_all"]) for r in res.rows) / (3 * res.n_scored)
        res.n_over = sum(1 for r in res.rows if abs(r["delta_pp"]) > ROW_BAR_PP)
        res.worst = max(res.rows, key=lambda r: abs(r["delta_pp"]))

    efl = [r for r in res.rows if r["comp"] == "EFL"]
    sign_rows, res.sign_selector, res.efl_stages_seen = select_round2(efl)
    res.sign_n = len(sign_rows)
    res.sign_agree = sum(1 for r in sign_rows if r["fav_model"] == r["fav_market"])
    if res.sign_n:
        res.sign_share = res.sign_agree / res.sign_n
    sign_ids = {r["match_id"] for r in sign_rows}

    for r in res.rows:
        flags = []
        if abs(r["delta_pp"]) > ROW_BAR_PP:
            flags.append(">8pp")
        if r["match_id"] in sign_ids and r["fav_model"] != r["fav_market"]:
            flags.append("SIGN")
        r["flag"] = ",".join(flags)

    res.mae_pass = res.mae_home_pp is not None and res.mae_home_pp <= MAE_BAR_PP
    res.over_pass = res.n_over <= MAX_OVER_BAR
    # An empty round-2 subset cannot pass a pass/fail check.
    res.sign_pass = res.sign_share is not None and res.sign_share >= SIGN_PASS_SHARE
    res.inversion = res.sign_share is not None and res.sign_share < SIGN_INVERSION_SHARE

    if res.invalid:
        res.verdict = (f"INVALID — {len(res.missing)} key rows unmatched/unpriced "
                       f"(> {MAX_MISSING}): data drift, stop and report")
    elif res.under_coverage:
        res.verdict = (f"INVALID — insufficient coverage: {res.n_scored} fixtures scored "
                       f"(< {min_scored}); {len(res.market_only)} market-only by ruling B")
    elif res.inversion:
        res.verdict = "FAIL — systematic sign inversion on EFL round 2 (league-bonus defect)"
    elif res.mae_pass and res.over_pass and res.sign_pass:
        res.verdict = "PASS"
    else:
        why = [n for n, ok in (("MAE", res.mae_pass), ("count>8pp", res.over_pass),
                               ("sign check", res.sign_pass)) if not ok]
        res.verdict = "FAIL — " + ", ".join(why)
    return res


def _mean_abs(rows: list[dict]) -> float | None:
    return sum(abs(r["delta_pp"]) for r in rows) / len(rows) if rows else None


def tier_of(row: dict) -> str:
    """same-tier = both home leagues known and identical; cross-tier = both
    known and different; unmapped = at least one side has no home league."""
    hl, al = row.get("home_league"), row.get("away_league")
    if not hl or not al:
        return "unmapped"
    return "same-tier" if hl == al else "cross-tier"


def detail_splits(res: ExamResult) -> dict:
    """
    Diagnostic summary for `cup-exam --detail` (architect spec 2026-09-25):
    mean |Δ_HOME| split by opponent pot membership and by tier, plus the
    teams priced at exactly the default league Elo. Pure: reads scored rows.
    """
    rows = res.rows
    in_pot = [r for r in rows if r.get("home_in_pot") and r.get("away_in_pot")]
    out_pot = [r for r in rows if not (r.get("home_in_pot") and r.get("away_in_pot"))]
    by_tier: dict[str, list[dict]] = {}
    for r in rows:
        by_tier.setdefault(tier_of(r), []).append(r)

    default_teams: set[str] = set()
    for r in rows:
        d = r.get("default_elo")
        for side in ("home", "away"):
            if d is not None and r.get(f"{side}_league_elo") == d:
                default_teams.add(r[side])
    return {
        "pot": {"in-pot": (len(in_pot), _mean_abs(in_pot)),
                "out-of-pot": (len(out_pot), _mean_abs(out_pot))},
        "tier": {t: (len(v), _mean_abs(v))
                 for t, v in sorted(by_tier.items())},
        "default_elo_teams": sorted(default_teams),
    }


def fit_summary(res: ExamResult) -> dict:
    """Strength-fit receipts across the scored rows: per-team fit sample
    sizes (bucketed), fixtures priced from a fit that contains their own
    result, backfilled pools, and promoted-default priors. Pure."""
    team_n: dict[str, int] = {}
    for r in res.rows:
        for side in ("home", "away"):
            n = r.get(f"{side}_fit_n")
            if n is not None:
                team_n[r[side]] = n
    buckets = {"0": 0, "1": 0, "2": 0, "3-5": 0, "6+": 0}
    for n in team_n.values():
        key = str(n) if n <= 2 else ("3-5" if n <= 5 else "6+")
        buckets[key] += 1
    return {
        "teams": len(team_n),
        "team_fit_n_buckets": buckets,
        "self_in_fit": sum(1 for r in res.rows if r.get("self_in_fit")),
        "backfilled_rows": sum(1 for r in res.rows if r.get("strengths_backfilled")),
        "promoted_default_sides": sum(1 for r in res.rows for side in ("home", "away")
                                      if r.get(f"{side}_strengths_source") == "promoted_default"),
        "pools": sorted({(r["comp"], r.get("fit_pool_n"), bool(r.get("strengths_backfilled")))
                         for r in res.rows if r.get("fit_pool_n") is not None}),
        "elo_goal_coeff": sorted({r.get("elo_goal_coeff") for r in res.rows
                                  if r.get("elo_goal_coeff") is not None}),
    }
