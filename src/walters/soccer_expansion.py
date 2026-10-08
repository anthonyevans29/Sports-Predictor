"""
SOCCER EXPANSION v1 — ONE registered experiment (ARCHITECT 2026-10-07, item 1; GATE-CLASS).
The ruling, verbatim, and the operational definitions: docs/specs/soccer-expansion-v1.md. Registry id
`soccer-expansion-v1` (docs/registry/experiments.json).

    soccer-expansion-gate --preflight   stream receipts only (matches per league-season, the 2023/24 naive
                                        frequencies, stage labels + placement, closing-odds coverage); scores NOTHING
    soccer-expansion-gate               the ONE run: refused unless the registry holds the experiment declared and
                                        unrun AND the spec's open findings are ruled; per-league lines, the
                                        surviving set, the scored-ids sidecar (registry.record_run)
    export-soccer-expansion-shadow      the five leagues as a greyed SHADOW (engine model_shadow; no Desk call,
                                        no order line, no prediction row)
    soccer-expansion-shadow-grade       read-only: the shadow's top pick vs the three-way book close
    soccer-expansion-confirm            the confirmation window (ARCHITECT 2026-10-08, addendum 11, item 4): freeze,
                                        substitute, progress, record, on the intl-elo-confirm pattern (section at the
                                        end of this module)

- CANDIDATE: the PRODUCTION soccer model exactly as shipped. Its params (dixon_coles_rho, elo_goal_coeff) are
  resolved at run time from the production model version; no refit, no per-league tuning. The walk is the existing
  leakage-free harness, soccer_backtest.run_soccer_backtest, per league-season from a cold start, at its default
  min_prior, the two test seasons pooled per league (F2); regular-season rounds only (F3); fixtures sharing a kickoff
  predicted before any of them updates the state (F5). A league without a complete stored 2023/24 season is dropped
  before the run (F1).
- GATE, PER LEAGUE: log-loss < naive − 0.010 on the same matches, unrounded, ties reject (F4; crit_ll) AND the
  intl-elo-v2 calibration bands (10pp bands, gated at n >= 100, ±5pp, three pairs per match:
  nhl_backtest.calibration_bands). RPS reported. Naive = that league's OWN H/D/A frequencies over its 2023/24
  season (frozen; never the test seasons).
- A league that misses its own gate is DROPPED. Verdict PASS iff at least one league survives; it names the set.
- Reported beside the gate, NEVER gated: the same matches against stored closing odds (bookmaker fdcuk_close,
  soccer-odds-history) where held: market log-loss and the >= +5pp positive-edge cohort.
- Nothing here touches PL: PL is not a league of this experiment, the shadow writes no prediction row, and
  nothing enters evaluate / improve / the results tally / the n=30 read.
"""
from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from src.timeutil import utc_now_naive

EID = "soccer-expansion-v1"
LEAGUES = ("PD", "SA", "BL1", "FL1", "ELC")
TEST_SEASONS = ("2024/25", "2025/26")
NAIVE_SEASON = "2023/24"
CURRENT_SEASON = "2026/27"
LL_MARGIN = 0.010
MIN_PRIOR = 40                      # the harness default (soccer-backtest --min-prior; run_soccer_backtest)
EDGE_COHORT_PP = 5.0                # reported only: the positive-edge cohort (>= +5pp vs the close)
CLOSE_BOOKMAKER = "fdcuk_close"
ENGINE = "model_shadow"
FILE_PREFIX = "soccer_expansion_shadow_"
WINDOW_HOURS = 72
SHADOW_NOTE = ("SHADOW — soccer-expansion-v1 (PD, SA, BL1, FL1, ELC). Until CONFIRMED every one of these leagues "
               "is SHADOW: never a Desk call, never an order line, never a prediction row; nothing enters PL's "
               "evaluate / improve / results tally / n=30 read.")

# Points the ruling leaves undefined are FINDINGS for a ruling, listed in the spec (section 7). The one run
# REFUSES while any is open; a ruling closes them by editing this tuple and the spec in a reviewed PR.
# F1-F5 RULED (ARCHITECT 2026-10-07, addendum 3, item B; spec section 7a). F6 RULED (ARCHITECT 2026-10-08,
# addendum 7, item 1; spec section 7b): a league with no gated band is DROPPED, "no gated band".
# R1 RULED (ARCHITECT 2026-10-08, addendum 8, item 1; spec 7b): no new field or schema; the reading of record is the
# entry's `ratified` annotation beside the untouched gate text (F4: the gate's <= is read as strict). Nothing is open.
OPEN_FINDINGS: tuple = ()

# F5 (ruled): for THIS gate the walk predicts every fixture sharing a kickoff timestamp before any of them updates
# the state (run_soccer_backtest batch_same_kickoff; the harness default stays the row-by-row walk).
BATCH_SAME_KICKOFF = True

# F3 (ruled): only regular-season rounds are scored and walked, in the test seasons and in the 2023/24 baseline.
# Match.stage stores api-football's fixture `league.round` verbatim (adapters/api_football.py), e.g.
# "Regular Season - 14". A label the code cannot place refuses the run (never guessed); the architect confirms the
# placement from --preflight before the run.
REGULAR_ROUND = re.compile(r"Regular Season - \d+")                 # full match, case-sensitive, as stored
PLAYOFF_ROUND = re.compile(r"\b(play-?offs?|play offs?|relegation|promotion|championship round|quarter-finals?"
                           r"|semi-finals?|finals?)\b", re.IGNORECASE)


def placement(label: str | None) -> str | None:
    """A stored stage / round label -> "regular" | "playoff" | None (cannot place: the run refuses). Pure.
    "regular" only for the exact api-football league-round form "Regular Season - <n>"; "playoff" only for a label
    naming a play-off, relegation / promotion / championship round or a (quarter- / semi-) final; anything else,
    NULL or empty included, is None."""
    if not label:
        return None
    if REGULAR_ROUND.fullmatch(label):
        return "regular"
    if PLAYOFF_ROUND.search(label):
        return "playoff"
    return None


def is_regular(label: str | None) -> bool:
    """The walk's stage filter for this gate (run_soccer_backtest stage_filter)."""
    return placement(label) == "regular"


class ExpansionRefused(RuntimeError):
    pass


def _reservation_default() -> str:
    from src.walters import registry as reg
    return os.path.join(os.path.dirname(reg.LEDGER), f"{EID}.started.json")


# Codex on #326: the one run RESERVES the gate (an exclusive create) after its pre-checks and before the first
# test-season read, so an interrupted, failed or concurrent run cannot read the sealed seasons a second time. A
# reservation without a recorded run refuses every later attempt until the architect rules (fails closed).
RESERVATION = None                  # None = docs/registry/<EID>.started.json (tests point it at a tmp path)


def reservation_path() -> str:
    return RESERVATION or _reservation_default()


def reserve(meta: dict | None = None, no_fetch: bool = False, echo=None) -> str:
    """The exclusive create, after the cross-ref guard (#329 RULED 2026-10-08): a cohort, run record or reservation
    of this experiment on any ref the clone knows refuses, naming the ref and the commit."""
    from src.walters import registry as reg
    p = reservation_path()
    if os.path.exists(p):
        raise ExpansionRefused(_reserved_why(p))
    try:
        receipt = reg.cross_ref_guard(EID, no_fetch=no_fetch)
    except reg.RegistryError as e:
        raise ExpansionRefused(str(e))
    if echo:
        echo(receipt)
    try:
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ExpansionRefused(_reserved_why(p))
    with os.fdopen(fd, "w") as f:
        json.dump({"id": EID, "started_at": utc_now_naive().strftime("%Y-%m-%dT%H:%M:%SZ"), **(meta or {})}, f)
        f.write("\n")
    return p


def _reserved_why(p: str) -> str:
    try:
        with open(p) as f:
            at = json.load(f).get("started_at", "?")
    except (OSError, ValueError):
        at = "?"
    return (f"{EID}: a run was started at {at} ({os.path.relpath(p)}) and the test seasons may have been read; "
            "it is the one run, recorded or not. Nothing reruns without an architect ruling")


# ------------------------------------------------------------------ pure --

def ll3(p: float) -> float:
    return -math.log(max(p, 1e-12))


def naive_from(outcomes) -> dict | None:
    """H/D/A frequencies from a 2023/24 outcome list ("H"/"D"/"A"). None when empty (finding F1)."""
    c = Counter(outcomes)
    n = sum(c.values())
    if not n:
        return None
    return {"H": c["H"] / n, "D": c["D"] / n, "A": c["A"] / n, "n": n}


def league_gate(results: list[dict], naive: dict) -> dict:
    """One league's gate over its scored test matches (soccer_backtest result rows). Pure.
    F4 (ruled, TIES REJECT): crit_ll iff ll_model < ll_naive - LL_MARGIN on unrounded values; equality fails."""
    from src.walters.evaluation import rps_1x2
    from src.walters.nhl_backtest import calibration_bands

    n = len(results)
    if not n:
        return {"n": 0, "verdict": "DROPPED — no scored matches", "survives": False}
    key = {"H": "p_home", "D": "p_draw", "A": "p_away"}
    ll_m = sum(ll3(r[key[r["actual"]]]) for r in results) / n
    ll_n = sum(ll3(naive[r["actual"]]) for r in results) / n
    rps_m = sum(rps_1x2(r["p_home"], r["p_draw"], r["p_away"], r["actual"]) for r in results) / n
    rps_n = sum(rps_1x2(naive["H"], naive["D"], naive["A"], r["actual"]) for r in results) / n
    pairs = [(r[key[o]], int(r["actual"] == o)) for r in results for o in "HDA"]
    bands = calibration_bands(pairs)
    crit_ll = ll_m < ll_n - LL_MARGIN                     # F4: strict, no tolerance; a tie rejects
    gated = [b for b in bands if b["gated"]]
    # F6 (ruled 2026-10-08): no band at >= 100 observations FAILS the bands criterion (DROPPED, "no gated band");
    # a league never passes on log-loss alone. The intl, NHL and NCAA gates keep their recorded rule.
    crit_bands = bool(gated) and all(b["ok"] for b in gated)
    ok = crit_ll and crit_bands
    why = [w for w, good in (("log-loss margin", crit_ll),
                             ("no gated band" if not gated else "calibration", crit_bands)) if not good]
    return {"n": n, "ll_model": ll_m, "ll_naive": ll_n, "bar": ll_n - LL_MARGIN, "rps_model": rps_m,
            "rps_naive": rps_n, "bands": bands, "crit_ll": crit_ll, "crit_bands": crit_bands,
            "survives": ok, "verdict": "PASS" if ok else "DROPPED — " + ", ".join(why)}


def overall(per_league: dict, dropped_before_run: dict | None = None) -> dict:
    """PASS iff at least one league survives its own gate; the verdict names the surviving set. Pure.
    `dropped` = leagues that ran and missed their own gate; `dropped_before_run` (F1) = code -> reason for leagues
    with no complete stored 2023/24 baseline, never read, never a FAIL, named separately in the verdict text."""
    pre = dict(dropped_before_run or {})
    surv = [c for c in LEAGUES if c not in pre and (per_league.get(c) or {}).get("survives")]
    verdict = ("PASS — surviving set " + ", ".join(surv)) if surv else "FAIL — no league survives"
    if pre:
        verdict += (f" · dropped before the run (no complete stored {NAIVE_SEASON} baseline; not gated): "
                    + "; ".join(f"{c} ({pre[c]})" for c in LEAGUES if c in pre))
    return {"surviving": surv, "dropped": [c for c in LEAGUES if c not in surv and c not in pre],
            "dropped_before_run": pre, "verdict": verdict}


def market_side(results: list[dict], closes: dict[int, dict]) -> dict | None:
    """REPORTED, NEVER GATED: the same scored matches against de-vigged closing odds where held.
    closes: match_id -> {"HOME", "DRAW", "AWAY"} decimal prices. Pure."""
    key = {"H": ("p_home", "HOME"), "D": ("p_draw", "DRAW"), "A": ("p_away", "AWAY")}
    j = []
    for r in results:
        p = closes.get(r["match_id"])
        if not p or not {"HOME", "DRAW", "AWAY"} <= set(p):
            continue
        inv = {k: 1.0 / p[k] for k in ("HOME", "DRAW", "AWAY")}
        t = sum(inv.values())
        j.append((r, {k: v / t for k, v in inv.items()}))
    if not j:
        return None
    n = len(j)
    cohort = []
    for r, mk in j:
        rk, sel = max((key["H"], key["D"], key["A"]), key=lambda x: r[x[0]])
        edge = (r[rk] - mk[sel]) * 100
        if edge >= EDGE_COHORT_PP - 1e-9:
            cohort.append((edge, key[r["actual"]][1] == sel))
    return {"n_priced": n, "n_unpriced": len(results) - n,
            "ll_model": sum(ll3(r[key[r["actual"]][0]]) for r, _ in j) / n,
            "ll_market": sum(ll3(mk[key[r["actual"]][1]]) for r, mk in j) / n,
            "edge_cohort": {"min_edge_pp": EDGE_COHORT_PP, "n": len(cohort),
                            "hits": sum(1 for _, h in cohort if h),
                            "mean_edge_pp": (sum(e for e, _ in cohort) / len(cohort)) if cohort else None}}


# ------------------------------------------------------------ registry --

def declared_unrun():
    """The registry entry, refusing unless declared and unrun (the test seasons are read ONCE)."""
    from src.walters import registry as reg
    e = reg.get(EID)
    if e is None or e.get("status") != "declared" or e.get("run") is not None:
        raise ExpansionRefused(f"{EID} must be declared and unrun in the registry "
                               f"(status {e.get('status') if e else 'absent'}): the test seasons are read once")
    if os.path.exists(reservation_path()):
        raise ExpansionRefused(_reserved_why(reservation_path()))
    return e


def guards_backtest(competition_code: str) -> str | None:
    """soccer-backtest on a league of this experiment is refused while it is declared and unrun: an ad-hoc
    read would spend the test seasons outside the one run. None = allowed."""
    from src.walters import registry as reg
    if (competition_code or "").upper() not in LEAGUES:
        return None
    e = reg.get(EID)
    if e is not None and e.get("run") is None:
        return (f"{competition_code} is a {EID} league, declared and unrun: its test seasons are read once, by "
                "soccer-expansion-gate (docs/specs/soccer-expansion-v1.md)")
    return None


# ------------------------------------------------------------- the DB --

def _comp(s, code):
    from sqlalchemy import select
    from src.db.schema import Competition
    return s.execute(select(Competition).where(Competition.code == code)).scalar_one_or_none()


def _outcome(m) -> str | None:
    if m.home_score is None or m.away_score is None:
        return None
    return "H" if m.home_score > m.away_score else "A" if m.home_score < m.away_score else "D"


def _season_rows(s, code: str, season: str, *cols):
    """(competition stored?, rows) for a league-season, STALE_ORPHAN rows excluded (never a fixture, ARCHITECT
    2026-10-03). Only the requested columns are selected."""
    from sqlalchemy import select
    from src.db.schema import Match, MatchStatus
    c = _comp(s, code)
    if c is None:
        return False, []
    return True, s.execute(select(*cols).where(Match.competition_id == c.id, Match.season == season,
                                               Match.status != MatchStatus.STALE_ORPHAN)).all()


def stage_census(s, code: str, season: str) -> list[tuple[str | None, int, str | None]]:
    """F3: every distinct stored stage / round label of a league-season (STALE_ORPHAN excluded) with its count and
    its placement, sorted by label. Labels and counts only: no score or outcome is read."""
    from src.db.schema import Match
    _, rows = _season_rows(s, code, season, Match.stage)
    cnt = Counter(r.stage for r in rows)
    return [(lab, n, placement(lab)) for lab, n in sorted(cnt.items(), key=lambda kv: (kv[0] is None, kv[0] or ""))]


def unplaced(s) -> list[str]:
    """F3: every label of the five leagues' 2023/24 and test seasons the code cannot place. Any one refuses the run."""
    return [f"{c} {se} {lab!r} ({n})" for c in LEAGUES for se in (NAIVE_SEASON, *TEST_SEASONS)
            for lab, n, pl in stage_census(s, c, se) if pl is None]


def baseline_complete(s, code: str) -> tuple[bool, str]:
    """F1: is the league's 2023/24 season COMPLETELY stored? Operational definition (a reading, spec section 7a):
    over the season's stored regular-season rows (STALE_ORPHAN excluded), at least one exists, every one is
    FINISHED with both scores, and they form a full double round-robin: T distinct clubs, exactly T*(T-1) rows,
    every ordered (home, away) pair once. Returns (complete, reason). Whether a score is stored is checked; no
    score or outcome is read."""
    from src.db.schema import Match, MatchStatus
    stored, rows = _season_rows(s, code, NAIVE_SEASON, Match.stage, Match.status, Match.home_team_id,
                                Match.away_team_id, Match.home_score.isnot(None).label("hs"),
                                Match.away_score.isnot(None).label("as_"))
    if not stored:
        return False, "competition not stored"
    reg = [r for r in rows if is_regular(r.stage)]
    if not reg:
        return False, f"no regular-season row stored for {NAIVE_SEASON}"
    teams = {r.home_team_id for r in reg} | {r.away_team_id for r in reg}
    t, n = len(teams), len(reg)
    unfinished = sum(1 for r in reg if r.status != MatchStatus.FINISHED or not (r.hs and r.as_))
    pairs = len({(r.home_team_id, r.away_team_id) for r in reg})
    if unfinished or n != t * (t - 1) or pairs != n:
        return False, (f"{NAIVE_SEASON} incomplete: {n} regular-season rows, {t} clubs (a double round-robin is "
                       f"{t * (t - 1)}), {pairs} distinct home/away pairs, {unfinished} not finished with both scores")
    return True, f"{NAIVE_SEASON} complete: {n} regular-season rows, {t} clubs, all finished with both scores"


def naive_for(s, code: str) -> dict | None:
    """That league's own 2023/24 H/D/A frequencies over its REGULAR-SEASON rows (F3), finished and scored. None =
    nothing stored. The run only uses it for a league whose 2023/24 is complete (F1)."""
    from sqlalchemy import select
    from src.db.schema import Match, MatchStatus
    c = _comp(s, code)
    if c is None:
        return None
    ms = s.execute(select(Match).where(Match.competition_id == c.id, Match.season == NAIVE_SEASON,
                                       Match.status == MatchStatus.FINISHED)).scalars()
    return naive_from([o for o in (_outcome(m) for m in ms if is_regular(m.stage)) if o])


def _walk_rows(s, code: str, season: str):
    """The rows the gate's walk reads, from fixture order and team ids only: FINISHED, both scores stored, a
    kickoff, regular-season (F3). Sorted by kickoff exactly as the walk sorts them. No score is read."""
    from sqlalchemy import select
    from src.db.schema import Match, MatchStatus
    c = _comp(s, code)
    if c is None:
        return []
    rows = s.execute(select(Match.id, Match.utc_date, Match.stage, Match.home_team_id, Match.away_team_id).where(
        Match.competition_id == c.id, Match.season == season, Match.status == MatchStatus.FINISHED,
        Match.home_score.isnot(None), Match.away_score.isnot(None), Match.utc_date.isnot(None))).all()
    rows = [r for r in rows if is_regular(r.stage)]
    rows.sort(key=lambda r: r.utc_date)
    return rows


def finished_count(s, code: str, season: str) -> int:
    """Regular-season (F3) finished matches with both scores stored for a league-season (a count; no outcome is
    read)."""
    return len(_walk_rows(s, code, season))


def scoreable_count(s, code: str, season: str, min_prior: int = MIN_PRIOR,
                    batch_same_kickoff: bool = BATCH_SAME_KICKOFF) -> int:
    """How many matches the gate's walk WOULD score for a league-season, from fixture order and team ids only (Codex
    on #326). It mirrors run_soccer_backtest's predicate on the same rows (finished, both scores, regular-season,
    sorted by kickoff): row-by-row, a row is scored once >= min_prior rows precede it and both its teams appear
    among them; batched (F5, the gate's mode), "precede" means a strictly earlier kickoff. No score is read."""
    rows = _walk_rows(s, code, season)
    seen, n, i = set(), 0, 0
    while i < len(rows):
        j = i + 1
        if batch_same_kickoff:
            while j < len(rows) and rows[j].utc_date == rows[i].utc_date:
                j += 1
        for r in rows[i:j]:
            if i >= min_prior and r.home_team_id in seen and r.away_team_id in seen:
                n += 1
        for r in rows[i:j]:
            seen.update((r.home_team_id, r.away_team_id))
        i = j
    return n


def preflight(s) -> dict:
    """Stream receipts, scoring NOTHING: per league, stored matches per season and status, every stage / round label
    per league-season with its count and placement (F3), the 2023/24 completeness verdict (F1), the 2023/24 naive
    frequencies, and closing-odds coverage on the test seasons. Counts only: no test-season OUTCOME is read."""
    from sqlalchemy import func, select
    from src.db.schema import Match, Odds
    out = {}
    for code in LEAGUES:
        c = _comp(s, code)
        if c is None:
            out[code] = {"stored": False, "baseline": (False, "competition not stored")}
            continue
        seasons = {}
        for season in (NAIVE_SEASON, *TEST_SEASONS, CURRENT_SEASON):
            rows = s.execute(select(Match.status, func.count()).where(
                Match.competition_id == c.id, Match.season == season).group_by(Match.status)).all()
            seasons[season] = {getattr(st, "value", str(st)): n for st, n in rows}
        stages = {se: stage_census(s, code, se) for se in (NAIVE_SEASON, *TEST_SEASONS)}
        test_ids = select(Match.id).where(Match.competition_id == c.id, Match.season.in_(TEST_SEASONS))
        closes = s.execute(select(func.count(func.distinct(Odds.match_id))).where(
            Odds.match_id.in_(test_ids), Odds.bookmaker == CLOSE_BOOKMAKER, Odds.market == "1X2")).scalar()
        out[code] = {"stored": True, "seasons": seasons, "stages": stages, "baseline": baseline_complete(s, code),
                     "naive": naive_for(s, code), "close_matches": closes}
    return out


def _closes(s, ids) -> dict[int, dict]:
    from sqlalchemy import select
    from src.db.schema import Odds
    out: dict[int, dict] = {}
    if not ids:
        return out
    for o in s.execute(select(Odds).where(Odds.match_id.in_(list(ids)), Odds.bookmaker == CLOSE_BOOKMAKER,
                                          Odds.market == "1X2")).scalars():
        out.setdefault(o.match_id, {})[o.selection] = o.price_decimal
    return out


def run(rho: float, coeff: float, progress=None, meta: dict | None = None, no_fetch: bool = False,
        echo=None) -> dict:
    """The ONE run's computation (the CLI records it). Every pre-check runs BEFORE the reservation and before any
    test-season read, so a refusal never follows a read: open findings; any stage / round label the code cannot
    place (F3); the F1 pre-run drops (a league without a complete stored 2023/24 is dropped, never read; all five
    dropped refuses: nothing to test); a kept league's test season the walk would score nothing in. Then it
    reserves the gate (after the cross-ref guard, #329; no_fetch skips its fetch and says so through `echo`) and
    walks the kept leagues (regular-season rows only, same-kickoff fixtures batched)."""
    if OPEN_FINDINGS:
        raise ExpansionRefused("open findings need a ruling before the run: " + "; ".join(OPEN_FINDINGS))
    from src.db.database import session_scope
    from src.walters.soccer_backtest import run_soccer_backtest

    with session_scope() as s:
        bad = unplaced(s)
        base = {c: baseline_complete(s, c) for c in LEAGUES}
        pre = {c: why for c, (ok, why) in base.items() if not ok}
        kept = [c for c in LEAGUES if c not in pre]
        naives = {c: naive_for(s, c) for c in kept}
        # Codex on #326: a season the walk would score nothing in is refused here, before any read. The predicate
        # is the walk's own (>= MIN_PRIOR earlier rows AND both teams among them), from fixture order and team ids
        empty = [f"{c} {se} ({finished_count(s, c, se)} finished regular-season, 0 scoreable at min_prior "
                 f"{MIN_PRIOR})" for c in kept for se in TEST_SEASONS if scoreable_count(s, c, se) == 0]
        s.rollback()
    if bad:                          # F3: never guessed
        raise ExpansionRefused("stage / round labels the code cannot place (F3; run --preflight, the architect "
                               "confirms placement): " + "; ".join(bad))
    if not kept:
        raise ExpansionRefused(f"every league is dropped before the run (no complete stored {NAIVE_SEASON}, F1): "
                               + "; ".join(f"{c} ({pre[c]})" for c in LEAGUES) + " — nothing to test")
    if empty:                        # checked BEFORE any league is scored: a refusal never follows a read
        raise ExpansionRefused(f"too few finished matches stored for {', '.join(empty)} (or the season string differs "
                               "from the stored one): run --preflight; missing data is never a silent DROP")
    missing = [c for c in kept if naives[c] is None]
    if missing:                      # unreachable for a complete season; kept as a law-4 guard, still pre-read
        raise ExpansionRefused(f"no stored {NAIVE_SEASON} outcomes for {', '.join(missing)}: naive undefined")
    reserve({"rho": rho, "elo_goal_coeff": coeff, "dropped_before_run": pre, **(meta or {})}, no_fetch=no_fetch,
            echo=echo)
    # from here on, the one read is spent
    per, scored = {}, []
    for code in kept:
        res = []
        for season in TEST_SEASONS:
            got = run_soccer_backtest(code, season, MIN_PRIOR, dixon_coles_rho=rho, elo_goal_coeff=coeff,
                                      sealed_read=True, stage_filter=is_regular,
                                      batch_same_kickoff=BATCH_SAME_KICKOFF) or []
            if not got:              # law 4: missing data is never a silent DROP
                raise ExpansionRefused(f"{code} {season}: no scored matches (not stored, or season string differs "
                                       "from the stored one); run --preflight")
            res += got
        g = league_gate(res, naives[code])
        with session_scope() as s:
            g["market"] = market_side(res, _closes(s, [r["match_id"] for r in res]))
            s.rollback()
        g["naive_freq"] = naives[code]
        per[code] = g
        scored += [r["match_id"] for r in res]
        if progress:
            progress(code, g)
    return {"per_league": per, **overall(per, pre), "scored_ids": scored}


# ------------------------------------------------------------- shadow --

def _status_label(e: dict | None, code: str) -> str:
    if e is None:
        return "NOT DECLARED"
    if not e.get("run"):
        return "DECLARED — gate not run"
    pl = ((e["run"].get("result") or {}).get("per_league") or {}).get(code) or {}
    v = (e.get("verdict") or {}).get("verdict")
    league = pl.get("verdict", "?")
    return f"{league} · verdict {v or 'pending'}" + (" · confirmation open" if e.get("status") == "confirming" else "")


def price_upcoming(code: str, now: datetime, hours: int, rho: float, coeff: float, season: str = CURRENT_SEASON):
    """The production model, walked over this season's finished matches before `now` (the harness's own walk),
    pricing the SCHEDULED matches in the window. Returns ([(match, pred)], counts)."""
    from sqlalchemy import select
    from src.db.database import session_scope
    from src.db.schema import Match, MatchStatus
    from src.walters import soccer_backtest as sb

    out, cnt = [], Counter()
    with session_scope() as s:
        c = _comp(s, code)
        if c is None:
            return [], {"not_stored": 1}
        rows = list(s.execute(select(Match).where(Match.competition_id == c.id, Match.season == season)
                              .order_by(Match.utc_date, Match.id)).scalars())
        done = [m for m in rows if m.status == MatchStatus.FINISHED and m.utc_date and m.utc_date < now
                and m.home_score is not None and m.away_score is not None]
        due = [m for m in rows if m.status == MatchStatus.SCHEDULED and m.utc_date
               and now <= m.utc_date < now + timedelta(hours=hours)]
        import dataclasses
        ctx, elo = sb.CompetitionScoringContext(), sb.EloState(config=sb.EloConfig())
        cfg = dataclasses.replace(sb.PoissonConfig(), dixon_coles_rho=rho, elo_goal_coeff=coeff)
        for m in done:
            nh, na = sb.update_after_match(elo.get(m.home_team_id), elo.get(m.away_team_id),
                                           m.home_score, m.away_score, elo.config)
            elo.set(m.home_team_id, nh)
            elo.set(m.away_team_id, na)
        if len(done) < MIN_PRIOR:
            cnt["below_min_prior"] = len(due)
            due = []
        st = sb.estimate_strengths([{"home_team_id": p.home_team_id, "away_team_id": p.away_team_id,
                                     "home_score": p.home_score, "away_score": p.away_score} for p in done], ctx) \
            if due else {}
        for m in due:
            hs, as_ = st.get(m.home_team_id), st.get(m.away_team_id)
            if not (hs and as_):
                cnt["no_strength"] += 1
                continue
            out.append((m.id, sb.predict_match(home_elo=elo.get(m.home_team_id), away_elo=elo.get(m.away_team_id),
                                               home_strength=hs, away_strength=as_, context=ctx, config=cfg)))
        s.rollback()
    cnt["priced"] = len(out)
    return out, dict(cnt)


def shadow_row(fixture_row: dict, pred, model_version: str, label: str, code: str) -> dict:
    """A greyed shadow row. Pure. No desk, no order, never a prediction."""
    probs = {"home_win": pred.p_home, "draw": pred.p_draw, "away_win": pred.p_away}
    top = max(probs.items(), key=lambda kv: kv[1])
    return {**fixture_row, "competition": code, "engine": ENGINE, "model_version": model_version,
            "gate_verdict": label,
            "prediction": {"home_win_prob": round(pred.p_home, 4), "draw_prob": round(pred.p_draw, 4),
                           "away_win_prob": round(pred.p_away, 4), "top_pick": top[0],
                           "top_pick_prob": round(top[1], 4)}}


def export_shadow(prod: tuple, now: datetime | None = None, hours: int = WINDOW_HOURS,
                  out_dir: str = "exports") -> tuple[str, dict]:
    """prod = (version, rho, coeff) of the PRODUCTION soccer model (resolved by the caller, never faked)."""
    from src.db.database import session_scope
    from src.db.schema import Match
    from src.walters import registry as reg
    from src.walters.export import _fixture_row

    version, rho, coeff = prod
    now = now or utc_now_naive()
    e = reg.get(EID)
    rows, counts = [], {}
    for code in LEAGUES:
        priced, counts[code] = price_upcoming(code, now, hours, rho, coeff, season=CURRENT_SEASON)
        with session_scope() as s:
            for mid, pred in priced:
                fx = _fixture_row(s, s.get(Match, mid), code, Counter(), Counter())
                rows.append(shadow_row(fx, pred, version, _status_label(e, code), code))
            s.rollback()
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    path = str(Path(out_dir) / f"{FILE_PREFIX}{now.strftime('%Y-%m-%d_%H%M')}.json")
    doc = {"sport": "soccer", "engine": ENGINE, "experiment": EID, "model_version": version,
           "gate_verdict": e and e.get("status") or "not declared", "contains_predictions": False,
           "exported_at": now.isoformat(), "window_hours": hours, "note": SHADOW_NOTE, "counts": counts,
           "count": len(rows), "predictions": rows}
    with open(path, "w") as f:
        json.dump(doc, f, indent=2, default=str)
    return path, doc


def last_calls(export_dir: str = "exports") -> dict[int, dict]:
    """match_id -> the LAST shadow row written before its kickoff."""
    out: dict[int, dict] = {}
    for f in sorted(Path(export_dir).glob(f"{FILE_PREFIX}*.json")):
        try:
            doc = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if doc.get("engine") != ENGINE:
            continue
        at = doc.get("exported_at") or ""
        for r in doc.get("predictions") or []:
            mid, ko = r.get("match_id"), r.get("utc_date") or ""
            if mid is None or not at or at >= ko:
                continue
            if mid not in out or at >= out[mid]["exported_at"]:
                out[mid] = {**r, "exported_at": at}
    return out


PICK = {"home_win": "HOME", "draw": "DRAW", "away_win": "AWAY"}


def shadow_grade(days: int = 30, export_dir: str = "exports", now: datetime | None = None) -> dict:
    """READ-ONLY: the shadow's top pick vs the three-way book close (#207 contract), per league."""
    from src.db.database import session_scope
    from src.db.schema import Match, MatchStatus, Odds
    from src.walters.close import close_1x2, outcomes_for, priced
    from sqlalchemy import select

    now = now or utc_now_naive()
    per: dict[str, dict] = {}
    lines = []
    with session_scope() as s:
        for mid, c in sorted(last_calls(export_dir).items(), key=lambda kv: kv[1].get("utc_date") or ""):
            m = s.get(Match, mid)
            if m is None or m.status != MatchStatus.FINISHED or m.utc_date < now - timedelta(days=days):
                continue
            code = c.get("competition") or "?"
            d = per.setdefault(code, {"graded": 0, "priced": 0, "clv": []})
            d["graded"] += 1
            sel = PICK[c["prediction"]["top_pick"]]
            cl = close_1x2(list(s.execute(select(Odds).where(Odds.match_id == m.id, Odds.market == "1X2"))
                                .scalars()), m.utc_date, outcomes_for(m.sport))
            clv = None
            if priced(cl):
                clv = c["prediction"]["top_pick_prob"] - cl["fair"][sel]
                d["priced"] += 1
                d["clv"].append(clv)
            lines.append(f"  {code:4} {m.away_team.name[:14]:14} @ {m.home_team.name[:15]:15} pick {sel} "
                         f"{c['prediction']['top_pick_prob']:.3f} div="
                         + ("%+.1fpp" % (clv * 100) if clv is not None else "—"))
        s.rollback()
    for d in per.values():
        v = d.pop("clv")
        d["mean_clv_pp"] = round(sum(v) / len(v) * 100, 2) if v else None
    return {"per_league": per, "lines": lines}


# -------------------------------------------------------- confirmation --
# ARCHITECT 2026-10-08, addendum 11, item 4: "By Tuesday: soccer-expansion-confirm (freeze, substitute, progress,
# record) on the intl-elo-confirm pattern." The declared window (registry confirmation_window, verbatim): "the first
# 60 league games of the surviving set kicking off after the verdict, pooled, cohort frozen by fixture id with the
# intl-elo-v2 machinery (unscoreable-only substitution); CONFIRMED iff pooled log-loss <= ln 3 AND < the pooled naive
# - 0.010 on the same games; per-league lines reported, not gated".
#   - the experiment must hold a run record and a PASS verdict; the surviving set is the run record's `surviving`
#     (refused when empty or when the computed run verdict is not PASS);
#   - eligible: a surviving league, a regular-season round (F3; an unplaced label is never guessed), kickoff strictly
#     after the verdict's `at`, not in the scored test set, not a stale orphan, ANY status; ordered (kickoff, id);
#   - unscoreable: the intl machinery's own predicate (intl_shadow._unscoreable), unchanged;
#   - the read: the gate's walk exactly (run_soccer_backtest per league-season from a cold start, min_prior 40,
#     stage_filter is_regular, F5 batching) at the RUN RECORD's rho / elo_goal_coeff (the candidate as gated, never
#     refit), predict-then-update; only the frozen cohort is scored;
#   - naive: each surviving league's 2023/24 H/D/A as the run record stores it (per_league[code].naive_freq); only
#     when absent, recomputed with naive_for exactly as the gate did, and labelled so.
CONFIRM_RULE = ("first n eligible stored fixtures by (kickoff, id): a surviving league (the run record's set), a "
                "regular-season round (F3), kickoff after the verdict, not in the test set, not a stale orphan, ANY "
                "status (result availability never enters)")
NAIVE_FROM_RECORD = "run record (per_league.naive_freq, the gate's frozen 2023/24 H/D/A)"
NAIVE_RECOMPUTED = "recomputed (naive_for over the stored 2023/24 regular season, exactly as the gate did)"


def _reg_paths() -> tuple[str, str]:
    """The ledger and ids dir, read at call time (tests point them at tmp paths; the real docs/registry/ otherwise)."""
    from src.walters import registry as reg
    return reg.LEDGER, reg.IDS_DIR


def confirming() -> tuple[dict, list[str], dict]:
    """(entry, surviving set, params) — refuses unless the experiment has its run record AND a PASS verdict and the
    run names at least one surviving league. params = the run record's production_version, rho, elo_goal_coeff."""
    from src.walters import registry as reg
    path, _ = _reg_paths()
    e = reg.get(EID, path)
    if e is None or not e.get("run"):
        raise ExpansionRefused(f"{EID} has no run record in docs/registry — the confirmation follows the one run")
    v = (e.get("verdict") or {}).get("verdict")
    if v != "PASS":
        raise ExpansionRefused(f"{EID} has no PASS verdict recorded (verdict {v or 'none'}) — the confirmation "
                               "window opens only on a PASS")
    res = e["run"].get("result") or {}
    surv = list(res.get("surviving") or [])
    if not str(res.get("verdict") or "").startswith("PASS") or not surv:
        raise ExpansionRefused(f"{EID}: the run record names no surviving league (computed verdict "
                               f"{res.get('verdict')!r}) — nothing to confirm")
    bad = [c for c in surv if c not in LEAGUES]
    if bad:
        raise ExpansionRefused(f"{EID}: the run record's surviving set holds {bad}, not leagues of this experiment")
    if res.get("rho") is None or res.get("elo_goal_coeff") is None:
        raise ExpansionRefused(f"{EID}'s run record lacks rho / elo_goal_coeff — the candidate as gated is unknown")
    return e, surv, {"production_version": res.get("production_version"), "rho": float(res["rho"]),
                     "elo_goal_coeff": float(res["elo_goal_coeff"])}


def confirmation_naives(e: dict, surv: list[str], s) -> tuple[dict, dict]:
    """({code: {H, D, A}}, {code: source}): the run record's frozen naive per surviving league; only when it is not
    stored there, naive_for (the gate's own function), labelled. None anywhere refuses (law 4)."""
    per = ((e["run"].get("result") or {}).get("per_league") or {})
    out, src = {}, {}
    for c in surv:
        nv = (per.get(c) or {}).get("naive_freq")
        if nv and all(isinstance(nv.get(k), (int, float)) for k in "HDA"):
            out[c], src[c] = nv, NAIVE_FROM_RECORD
            continue
        nv = naive_for(s, c)
        if nv is None:
            raise ExpansionRefused(f"{c}: no {NAIVE_SEASON} naive in the run record and none stored — naive undefined")
        out[c], src[c] = nv, NAIVE_RECOMPUTED
    return out, src


def eligible_fixtures(s, e: dict, surv: list[str]) -> tuple[list[dict], list[dict]]:
    """(eligible, unplaced): every STORED fixture of a surviving league kicking off after the verdict, WHATEVER ITS
    STATUS, in (kickoff, id) order; regular-season rounds only (F3); test-set ids and stale orphans excluded.
    `unplaced` lists the rows whose stage label the code cannot place (never guessed: a freeze or substitution they
    could precede refuses). Result availability never enters."""
    from sqlalchemy import select
    from src.db.schema import Competition, Match, MatchStatus
    from src.walters import registry as reg
    from src.walters.intl_shadow import _unscoreable, _verdict_at

    _, ids_dir = _reg_paths()
    at = _verdict_at(e)
    comps = {c.id: c.code for c in s.execute(select(Competition).where(Competition.code.in_(surv))).scalars()}
    if not comps:
        return [], []
    test_ids = reg._ids_of(e, ids_dir) or set()
    elig, unpl = [], []
    for m in s.execute(select(Match).where(Match.competition_id.in_(list(comps)), Match.utc_date > at,
                                           Match.status != MatchStatus.STALE_ORPHAN)
                       .order_by(Match.utc_date, Match.id)).scalars():
        status = m.status.value if hasattr(m.status, "value") else str(m.status)
        f = {"id": m.id, "kickoff": m.utc_date, "code": comps[m.competition_id], "season": m.season,
             "stage": m.stage, "status": status, "status_raw": m.status_raw,
             "has_score": m.home_score is not None and m.away_score is not None,
             "unscoreable": _unscoreable(m, status)}
        pl = placement(m.stage)
        if pl is None:
            unpl.append(f)
        elif pl == "regular" and m.id not in test_ids:
            elig.append(f)
    return elig, unpl


def unplaced_through(unpl: list[dict], kickoff) -> list[str]:
    """Unplaced rows kicking off at or before `kickoff`: any one could belong before the chosen fixture."""
    return [f"{f['code']} {f['id']} {f['stage']!r} {f['kickoff']:%Y-%m-%dT%H:%MZ}" for f in unpl
            if f["kickoff"] <= kickoff]


def cohort(e: dict, s, surv: list[str]) -> dict:
    """The FROZEN ids from the registry when frozen; otherwise the provisional first n eligible fixtures (possibly
    fewer than n while the schedule is short). Never depends on results."""
    from src.walters import registry as reg
    _, ids_dir = _reg_paths()
    n = e["confirmation_plan"]["n_games"]
    elig, unpl = eligible_fixtures(s, e, surv)
    try:
        frozen_ids = reg.frozen_cohort(e, ids_dir)
    except reg.RegistryError as err:
        raise ExpansionRefused(str(err))
    if frozen_ids is not None:
        return {"state": "frozen", "ids": frozen_ids, "n_games": n, "eligible_stored": len(elig), "unplaced": unpl}
    return {"state": "provisional", "ids": [f["id"] for f in elig[:n]], "n_games": n,
            "eligible_stored": len(elig), "fixtures": elig[:n], "unplaced": unpl}


def substitutions_due(e: dict, s, surv: list[str]) -> list[dict]:
    """The intl-elo-v2 rule (ARCHITECT 2026-10-02), on this cohort: every UNSCOREABLE cohort fixture is released and
    replaced by the next eligible fixture AFTER the cohort (kickoff order, after every fixture that is or was in the
    cohort, never unscoreable itself, never one already used); the reason is the raw provider code. A postponed /
    scheduled / live fixture, or a FT row still waiting for its score, is never released. Read-only."""
    c = e.get("confirmation_cohort")
    if not c:
        return []
    co = cohort(e, s, surv)
    elig, _ = eligible_fixtures(s, e, surv)
    by_id = {f["id"]: f for f in elig}
    ever = set(co["ids"]) | {int(x["released"]) for x in c.get("substitutions") or []}
    last = max(((by_id[i]["kickoff"], i) for i in ever if i in by_id), default=None)
    pool = [f for f in elig if f["id"] not in ever and not f["unscoreable"]
            and (last is None or (f["kickoff"], f["id"]) > last)]
    out = []
    for i in co["ids"]:
        f = by_id.get(i)
        if f is None or not f["unscoreable"]:
            continue
        out.append({"released": f, "replacement": pool.pop(0) if pool else None,
                    "reason": (f["status_raw"] or f["status"]).upper()})
    return out


def confirmation_read() -> dict:
    """The plan's read so far: the cohort priced by the gate's own walk (per league-season from a cold start, min_prior
    40, regular-season rows, F5 batching, the run record's params), predict-then-update; pooled model log-loss vs the
    pooled naive (each league's frozen 2023/24 H/D/A) − 0.010; per-league lines (reported, not gated)."""
    from src.db.database import session_scope
    from src.walters.soccer_backtest import run_soccer_backtest

    e, surv, params = confirming()
    with session_scope() as s:
        co = cohort(e, s, surv)
        elig, unpl = eligible_fixtures(s, e, surv)
        naives, nsrc = confirmation_naives(e, surv, s)
        s.rollback()
    by_id = {f["id"]: f for f in elig}
    want = set(co["ids"])
    priced: dict[int, dict] = {}
    for code, season in sorted({(by_id[i]["code"], by_id[i]["season"]) for i in want if i in by_id}):
        for r in run_soccer_backtest(code, season, MIN_PRIOR, dixon_coles_rho=params["rho"],
                                     elo_goal_coeff=params["elo_goal_coeff"], stage_filter=is_regular,
                                     batch_same_kickoff=BATCH_SAME_KICKOFF) or []:
            if r["match_id"] in want:
                priced[r["match_id"]] = r
    key = {"H": "p_home", "D": "p_draw", "A": "p_away"}
    scored = sorted((i for i in want if i in priced and i in by_id and not by_id[i]["unscoreable"]),
                    key=lambda i: (by_id[i]["kickoff"], i))
    per: dict[str, dict] = {}
    ll_m = ll_n = 0.0
    for i in scored:
        r, code = priced[i], by_id[i]["code"]
        m, n = ll3(r[key[r["actual"]]]), ll3(naives[code][r["actual"]])
        ll_m, ll_n = ll_m + m, ll_n + n
        d = per.setdefault(code, {"n": 0, "ll_model": 0.0, "ll_naive": 0.0})
        d["n"], d["ll_model"], d["ll_naive"] = d["n"] + 1, d["ll_model"] + m, d["ll_naive"] + n
    for d in per.values():
        d["ll_model"] /= d["n"]
        d["ll_naive"] /= d["n"]
    plan = e["confirmation_plan"]
    pending = sorted(want - set(scored))

    def why(i):
        f = by_id.get(i)
        if f is None:
            return "not stored as an eligible fixture"
        if f["status"] == "finished" and f["has_score"] and not f["unscoreable"]:
            return "finished, not priced by the walk"          # below min_prior / a club not yet seen: listed, law 4
        return f["status"]
    n = len(scored)
    out = {"n": n, "n_games": plan["n_games"], "bar": plan["bar"], "scored_ids": scored, "surviving": surv,
           "params": params, "naive": {c: {k: naives[c][k] for k in "HDA"} for c in surv}, "naive_source": nsrc,
           "first_game_at": by_id[scored[0]]["kickoff"].strftime("%Y-%m-%dT%H:%M:%SZ") if scored else None,
           "cohort_state": co["state"], "cohort_size": len(co["ids"]), "eligible_stored": co["eligible_stored"],
           "unplaced": [f"{f['code']} {f['id']} {f['stage']!r}" for f in unpl],
           "pending": [{"id": i, "status": why(i)} for i in pending],
           "release_due": sum(1 for i in pending if (by_id.get(i) or {}).get("unscoreable") and co["state"] == "frozen"),
           "per_league": per,
           # recordable only as the WHOLE frozen cohort, every fixture labelled
           "complete": co["state"] == "frozen" and not pending and n == plan["n_games"]}
    if n:
        out.update({"log_loss": ll_m / n, "naive_log_loss": ll_n / n, "reference_log_loss": ll_n / n - LL_MARGIN})
    return out
