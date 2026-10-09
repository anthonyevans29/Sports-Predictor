"""
ncaa-elo-v1r: THE GATE (D3-D6) AND THE CONFIRMATION READ (D7). GATE-CLASS. ARCHITECT 2026-10-08, addendum 11, item 3,
PR B (verbatim): "PR B, after PR A: the gate command for D3 to D6 with --preflight, the reservation and the one
recorded run, on the soccer-expansion-v1 pattern; then the confirmation command for D7 on the intl-elo-confirm
pattern. #79's ncaa-backtest stays as it is." The declaration (D1-D9, verbatim): docs/specs/ncaa-elo-v1r.md;
registry id `ncaa-elo-v1r` (docs/registry/experiments.json).

    ncaa-v1r-gate --preflight          scores nothing; per season the stream by season_type, the neutral count,
                                       the coverage and the D4 baseline (D6); its last line is the stream
                                       fingerprint (addendum 17 item 1)
    ncaa-v1r-gate --architect-word T --stream-fingerprint F
                                       the ONE run (D3-D6): refused unless declared and unrun, the architect's word
                                       given, 2024 and 2025 covered; then the stream is loaded (nothing scored) and
                                       the run refuses unless its fingerprint is F, its scored set numbers >= 500
                                       (addendum 17 items 1, 2) and the D4 baseline is defined (addendum 21 item
                                       4 (2)); the reservation (after the #329 cross-ref guard),
                                       carrying the word and the fingerprint, is written BEFORE the first game is
                                       scored; the scored ids are recorded (registry.record_run)

ADDENDUM 17 (ARCHITECT 2026-10-08 18:56 ET), item 1 (verbatim): "The run takes my word as --architect-word, verbatim,
and writes it into the reservation and the run record. There is no OPEN_ITEMS gate: one lock is enough, and this is the
one that leaves my word in the record. What the word needs is to refer to one stream. --preflight ends with one line, a
fingerprint of the 2024 and 2025 stream exactly as the gate would walk it: the games in order, with every label field
the gate reads. The run takes that fingerprint as a required option and refuses, before the reservation, when the
stream it is about to walk no longer matches. The fingerprint is recorded beside the word."
Item 2 (verbatim): "The scored set is known before any game is scored: the 2025 games whose season_type is exactly
'regular', less the level scores. If it numbers under 500 the run refuses before the reservation and records nothing;
no game has been scored. That is #79's rule: not scored, re-run later, the bar does not move."
    ncaa-v1r-confirm                   D7 on the intl-elo-confirm pattern: --freeze-cohort (once, via
                                       registry.freeze_confirmation_cohort, which calls the guard), --substitute
                                       (cancelled fixtures only), progress, --record --ruling (registry
                                       .record_confirmation computes CONFIRMED / NOT_CONFIRMED)

THE WALK (D1, D2, D3). The D2 stream is ncaa_backtest.load_v1r_stream (PR A); the model is the shared D1 wrapper
ncaa_backtest.NeutralRuleElo (NCAAEloV1, constants untouched; a game labelled neutral priced and updated with home
advantage 0). In stream order: a 2024 game is updated only; a 2025 game whose season_type is exactly 'regular' is
predicted, then updated (the test set); any other 2025 game (another season_type, or none) is walked and never
scored. The walk ends after the last 2025 game walked: no 2026 game is ever scored, and none after that point is
walked. D4's baseline is computed from the stream's 2024 non-neutral 'regular' games BEFORE the walk starts.

D5 (2) and (3) are ncaa_backtest.level_gap / level_ok / logistic_slope / slope_ok: the one implementation the design
receipt (scripts/ncaa_v1r_design_receipt.py) also calls.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime

from src.timeutil import utc_now_naive
from src.walters import ncaa_backtest as nb

EID = "ncaa-elo-v1r"
COMPETITION = nb.NCAA_COMPETITION_CODE
GATE_SEASONS = (nb.V1R_WARMUP, nb.V1R_TEST)          # D6: the gate run refuses unless 2024 and 2025 are covered
CONFIRM_SEASONS = nb.V1R_SEASONS                       # D6: the confirmation read needs 2024, 2025 and 2026
REGULAR = "regular"                                    # D3 / D4: season_type EXACTLY 'regular'
MIN_SCORED = nb.MIN_TEST_N                             # D5 / addendum 17 item 2: under 500 the run refuses (#79's)
LL_MARGIN = nb.LL_MARGIN                               # D5 (1): 0.010 (#79's), strict, unrounded, ties reject
RATING_MIN, RATING_MAX = nb.RATING_MIN, nb.RATING_MAX  # D5 (4): 1000 to 2000 (#79's)
CONFIRM_BAR = 0.6931                                   # D7: log-loss <= 0.6931

# The stream fingerprint (addendum 17 item 1): "the games in order, with every label field the gate reads". The
# fields, each read by the walk (run_gate / NeutralRuleElo / NCAAEloV1.predict + update) or defining its order:
#   match_id      the scored id (run_gate rows, scored_ids) and the order's tie-break (v1r_stream: kickoff, match id)
#   utc_date      the stored kickoff: the walk's order (v1r_stream sorts by it)
#   season        the label's season: the split (is_test, d4_baseline, the last 2025 game) and NCAAEloV1's regression
#   season_type   the test set (is_test: exactly 'regular'), D4 and the not-scored census
#   home_id, away_id   the J2 merged ids: NCAAEloV1's ratings, cold starts
#   home_score, away_score   the outcome (home_win) and NCAAEloV1's margin of victory
#   neutral       D1 (NeutralRuleElo.home_adv), D4 (non-neutral only) and the baseline's 0.5 at a neutral site
#   label_source  NeutralRuleElo.update counts a cfbd label without a neutral flag (reported)
FINGERPRINT_FIELDS = ("match_id", "utc_date", "season", "season_type", "home_id", "away_id", "home_score",
                      "away_score", "neutral", "label_source")
FINGERPRINT_TAG = f"{EID} stream fingerprint v1"


class GateRefused(RuntimeError):
    """A precondition is not met: printed with its reason, exit 2; nothing read, nothing written."""


def _reg():
    from src.walters import registry as reg
    return reg


def _iso(d: datetime | None) -> str | None:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ") if d else None


# ------------------------------------------------------------------ the reservation (soccer-expansion-v1's) --

RESERVATION = None                  # None = docs/registry/<EID>.started.json (tests point it at a tmp path)


def reservation_path() -> str:
    return RESERVATION or os.path.join(os.path.dirname(_reg().LEDGER), f"{EID}.started.json")


def _reserved_why(p: str) -> str:
    try:
        with open(p) as f:
            at = json.load(f).get("started_at", "?")
    except (OSError, ValueError):
        at = "?"
    return (f"{EID}: a run was started at {at} ({os.path.relpath(p)}) and the test set may have been read; it is "
            "the one run, recorded or not. Nothing reruns without an architect ruling")


def reserve(meta: dict | None = None, no_fetch: bool = False, echo=None) -> str:
    """D6 "a reservation written before the first read": the exclusive create, after the cross-ref guard (#329
    RULED 2026-10-08: every one-run reservation calls it; a cohort, run record or reservation of this experiment on
    any ref the clone knows refuses, naming the ref and the commit). The guard runs before the file is created."""
    reg = _reg()
    p = reservation_path()
    if os.path.exists(p):
        raise GateRefused(_reserved_why(p))
    try:
        receipt = reg.cross_ref_guard(EID, no_fetch=no_fetch)
    except reg.RegistryError as e:
        raise GateRefused(str(e))
    if echo:
        echo(receipt)
    try:
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise GateRefused(_reserved_why(p))
    with os.fdopen(fd, "w") as f:
        json.dump({"id": EID, "started_at": _iso(utc_now_naive()), "guard": receipt, **(meta or {})}, f)
        f.write("\n")
    return p


def declared_unrun() -> dict:
    """The registry entry, refusing unless declared and unrun (the test set is read once) and unreserved."""
    reg = _reg()
    e = reg.get(EID, reg.LEDGER)
    if e is None or e.get("status") != "declared" or e.get("run") is not None:
        raise GateRefused(f"{EID} must be declared and unrun in the registry (status "
                          f"{e.get('status') if e else 'absent'}): the test set is read once")
    if os.path.exists(reservation_path()):
        raise GateRefused(_reserved_why(reservation_path()))
    return e


def coverage(seasons, s=None) -> dict[str, dict]:
    """L2 + L3 (ncaa_cfbd.stored_coverage, the #362 coverage fact) for `seasons`. Reads ingest records and label
    counts only: no game, no outcome."""
    from src.ingestion.ncaa_cfbd import stored_coverage
    if s is not None:
        return stored_coverage(s, seasons)
    from src.db.database import session_scope
    with session_scope() as s2:
        out = stored_coverage(s2, seasons)
        s2.rollback()
    return out


def require_coverage(fbs: dict[str, dict], seasons, what: str) -> None:
    bad = nb.coverage_misses(fbs, seasons)
    if bad:
        raise GateRefused(f"{what} refuses unless {', '.join(seasons)} are covered (D6; L2 + L3: the side table labels "
                          f">= {nb.COVERAGE_MIN:.0%} of CFBD's completed both-FBS games, current labels numbering "
                          f"the record's joined count); not covered: {'; '.join(bad)} — if a season misses, nothing "
                          "in the declaration bends to fit it: the architect rules again (`python cli.py "
                          "ncaa-cfbd-coverage` lists every unlabelled game)")


# ------------------------------------------------------------------------------------------- pure: D3, D4, D5 --

def is_test(g) -> bool:
    """D3: the test set is the 2025 games whose season_type is exactly 'regular'."""
    return g.season == nb.V1R_TEST and g.season_type == REGULAR


def walked(games) -> list:
    """The games the gate walks, in stream order: every stream game up to and including the last 2025 game (D3; the
    end of the walk, addendum 17 item 3: "as built"). [] when the stream holds no 2025 game."""
    last = max((i for i, g in enumerate(games) if g.season == nb.V1R_TEST), default=None)
    return [] if last is None else list(games[:last + 1])


def scored_set(games) -> list:
    """Addendum 17 item 2: "the 2025 games whose season_type is exactly 'regular', less the level scores" (the D2
    stream has already skipped the level scores). Known before any game is scored."""
    return [g for g in walked(games) if is_test(g)]


def _fp_value(v):
    return v.strftime("%Y-%m-%dT%H:%M:%S.%f") if isinstance(v, datetime) else v


def stream_fingerprint(games) -> tuple[str, int]:
    """Addendum 17 item 1: sha256 over a canonical serialization of the stream exactly as the gate walks it (walked():
    the 2024 and 2025 games, plus any 2026 game kicking off before the last 2025 game, which the walk updates on), in
    walk order, each game carrying FINGERPRINT_FIELDS. JSON, sorted keys, no whitespace, one game per list entry.
    Returns (hex digest, number of games)."""
    import hashlib

    w = walked(games)
    body = {"tag": FINGERPRINT_TAG, "fields": list(FINGERPRINT_FIELDS),
            "games": [[_fp_value(getattr(g, f)) for f in FINGERPRINT_FIELDS] for g in w]}
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("ascii")).hexdigest(), len(w)


def d4_baseline(games) -> tuple[float | None, int]:
    """D4 (verbatim): "the home win rate of the stream's 2024 non-neutral games whose season_type is 'regular'". A
    label without a neutral flag is non-neutral (D1). (rate, n); rate None when n is 0."""
    base = [g for g in games if g.season == nb.V1R_WARMUP and g.season_type == REGULAR and g.neutral is not True]
    return (sum(g.home_win for g in base) / len(base) if base else None), len(base)


def d4_undefined_why() -> str:
    """Addendum 21 item 4 (2) (verbatim): "When 2024 has no non-neutral regular game, D4 is undefined and nothing can
    be scored: the run refuses before the reservation and records nothing, as it does under 500 games. It is not an
    INVALID run and the read is not spent." """
    return (f"no {nb.V1R_WARMUP} non-neutral '{REGULAR}' game in the stream: the D4 baseline is undefined and nothing "
            "can be scored (addendum 21 item 4 (2)); nothing reserved or recorded, not an INVALID run, the read is "
            "not spent")


def baseline_p(g, rate: float) -> float:
    """D4: the baseline's home probability: the frozen rate in a non-neutral game, 0.5 at a neutral site."""
    return 0.5 if g.neutral is True else rate


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def run_gate(games, model=None) -> dict:
    """D3-D5 on the D2 stream's games (V1RStream.games: kickoff then match id, level scores already skipped). Pure.
    Returns the result (every gated and reported quantity, unrounded) and `scored_ids`. An undefined D4 baseline
    raises GateRefused before anything is walked (addendum 21 item 4 (2); run() refuses before the reservation)."""
    rate, n_base = d4_baseline(games)                  # FROZEN before any test game is scored (D4)
    out = {"verdict": None, "n_scored": 0, "scored_ids": [], "baseline_home_rate": rate, "baseline_n": n_base,
           "min_scored": MIN_SCORED}
    if rate is None:     # pure backstop: run() refuses before the reservation (addendum 21 item 4 (2))
        raise GateRefused(d4_undefined_why())
    walk = walked(games)                               # the walk ends after the last 2025 game walked
    if not walk:
        out["verdict"] = f"INVALID — no {nb.V1R_TEST} game in the stream (nothing scored)"
        return out
    last = len(walk) - 1
    model = model or nb.NeutralRuleElo()
    seen: set[int] = set()
    by_season, not_scored = Counter(), Counter()
    rows = []                                          # (match_id, p, q, y, neutral, cold)
    for g in walk:
        by_season[g.season] += 1
        if is_test(g):
            cold = g.home_id not in seen or g.away_id not in seen
            p = model.predict(g)
            rows.append((g.match_id, p, baseline_p(g, rate), g.home_win, g.neutral is True, cold))
        elif g.season == nb.V1R_TEST:
            not_scored[g.season_type if g.season_type else nb.NO_SEASON_TYPE] += 1
        model.update(g)
        seen.update((g.home_id, g.away_id))
    ratings = model.ratings()
    n = len(rows)
    out.update({
        "n_scored": n, "scored_ids": [r[0] for r in rows],
        "walked_by_season": dict(sorted(by_season.items())),
        "walked_2026": by_season.get("2026", 0),            # reported: 2026 games kicking off before the last 2025 game
        "not_walked_after_last_2025": sum(1 for g in games[last + 1:]),
        "walked_not_scored_2025_by_season_type": dict(sorted(not_scored.items())),
        "neutral_updates": getattr(model, "neutral_updates", None),
        "neutral_unflagged": getattr(model, "unflagged_updates", None),
        "teams_rated": len(ratings),
        "rating_min": min(ratings.values()) if ratings else None,
        "rating_max": max(ratings.values()) if ratings else None,
        "outliers": sorted([t, v] for t, v in ratings.items() if not RATING_MIN <= v <= RATING_MAX),
    })
    if not n:
        out["verdict"] = f"INVALID — 0 scored games < {MIN_SCORED} (D5)"
        return out
    pairs = [(r[1], r[3]) for r in rows]
    ll_model = sum(nb._ll(p, y) for p, y in pairs) / n
    ll_base = sum(nb._ll(r[2], r[3]) for r in rows) / n
    bar = ll_base - LL_MARGIN
    gap = nb.level_gap(pairs)
    a, b = nb.logistic_slope(pairs)
    neu = [r for r in rows if r[4]]
    non = [r for r in rows if not r[4]]
    crit = {"margin": ll_model < bar,                   # (1) strict, unrounded: a tie with the bar rejects
            "level": nb.level_ok(gap),                  # (2)
            "spread": nb.slope_ok(b),                   # (3) a fit that does not converge fails
            "range": not out["outliers"] and bool(ratings)}   # (4)
    out.update({
        "ll_model": ll_model, "ll_baseline": ll_base, "bar": bar, "crit_margin": crit["margin"],
        "mean_p": _mean([p for p, _ in pairs]), "realized_home_rate": _mean([y for _, y in pairs]),
        "level_gap": gap, "crit_level": crit["level"],
        "slope_b": b, "fit_converged": b is not None, "crit_spread": crit["spread"],
        "crit_range": crit["range"],
        # reported, never gated (D5)
        "intercept_a": a,
        "ll_const": sum(nb._ll(0.5, y) for _, y in pairs) / n,
        "brier_model": sum(nb._brier(p, y) for p, y in pairs) / n,
        "brier_baseline": sum(nb._brier(r[2], r[3]) for r in rows) / n,
        "bands_79": nb.calibration_bands(pairs),
        "cold_starts": sum(1 for r in rows if r[5]),
        "ll_neutral": _mean([nb._ll(r[1], r[3]) for r in neu]), "n_neutral": len(neu),
        "ll_nonneutral": _mean([nb._ll(r[1], r[3]) for r in non]), "n_nonneutral": len(non),
    })
    if n < MIN_SCORED:     # pure backstop: run() refuses before the reservation (addendum 17 item 2)
        out["verdict"] = f"INVALID — {n} scored games < {MIN_SCORED} (D5; the criteria below are not a verdict)"
    elif all(crit.values()):
        out["verdict"] = ("PASS — the architect rules; PASS does not make college football a call (D8): the Desk "
                          "stays market-only for NCAA")
    else:
        out["verdict"] = "FAIL — " + ", ".join(f"({i}) {k}" for i, k in enumerate(crit, 1) if not crit[k])
    return out


def result_record(r: dict, word: str) -> dict:
    """The durable run record (registry run.result): everything but the scored ids (they are the sidecar). The word
    verbatim, and the stream fingerprint the run checked (r["stream_fingerprint"]) beside it (addendum 17 item 1)."""
    rec = {k: v for k, v in r.items() if k != "scored_ids"}
    rec["bands_79"] = [{**b, "stated": round(b["stated"], 6), "realized": round(b["realized"], 6),
                        "gap": round(b["gap"], 6)} for b in r.get("bands_79") or []]
    rec["architect_word"] = word
    return rec


# ------------------------------------------------------------------------------------------- the DB: preflight --

def preflight(v, fbs: dict[str, dict]) -> dict:
    """D6 (verbatim): "--preflight scores nothing and prints, per season, the stream by season_type, the neutral
    count, the coverage and the D4 baseline." Pure over a loaded stream: counts per season, and the D4 baseline (a
    2024 rate). No model is built; no 2025 or 2026 outcome is computed or printed."""
    rate, n_base = d4_baseline(v.games)
    fp, fp_n = stream_fingerprint(v.games)
    per = {}
    for season in nb.V1R_SEASONS:
        walked = v.by_season(season)
        per[season] = {"walked": len(walked), "by_season_type": dict(sorted(v.census.get(season, {}).items())),
                       "neutral": v.neutral[season], "no_neutral_flag": v.unflagged[season],
                       "level_scores": v.level_by_season[season], "coverage": fbs.get(season)}
    return {"seasons": per, "baseline_home_rate": rate, "baseline_n": n_base,
            "test_n": len(scored_set(v.games)), "fingerprint": fp, "fingerprint_n": fp_n,
            "gate_covered": not nb.coverage_misses(fbs, GATE_SEASONS),
            "confirm_covered": not nb.coverage_misses(fbs, CONFIRM_SEASONS),
            "stale": len(v.stale), "outside": dict(sorted(v.outside.items())),
            "unlabelled": dict(sorted(v.unlabelled.items())), "merge_groups": len(v.merge.groups)}


def preflight_lines(pf: dict) -> list[str]:
    from src.ingestion.ncaa_cfbd import stored_coverage_lines

    L = [f"NCAA-ELO-V1R · PREFLIGHT (D6: scores nothing) · warm-up {nb.V1R_WARMUP} (update only) · test "
         f"{nb.V1R_TEST} season_type exactly '{REGULAR}' (predict, then update) · no {nb.V1R_SEASONS[-1]} game scored"]
    for season, c in pf["seasons"].items():
        role = {nb.V1R_WARMUP: "warm-up", nb.V1R_TEST: "test (regular) + walked"}.get(season, "never scored by the gate")
        L.append(f"  {season} ({role}): stream {c['walked']} · by season_type "
                 + (", ".join(f"{k} {n}" for k, n in c["by_season_type"].items()) or "none")
                 + f" · neutral {c['neutral']} · no neutral flag {c['no_neutral_flag']} (non-neutral, D1) · level "
                 f"scores skipped {c['level_scores']}")
        cov = c["coverage"]
        L.append("    coverage: " + ("not computed (no ingest record read)" if cov is None else
                                      stored_coverage_lines({season: cov})[0].strip()))
    rate = pf["baseline_home_rate"]
    L.append(f"  D4 baseline (frozen before any test game is scored): {nb.V1R_WARMUP} non-neutral '{REGULAR}' home "
             f"win rate " + (f"{rate:.6f} (n {pf['baseline_n']})" if rate is not None else
                             f"UNDEFINED (n 0)") + " · 0.5 at a neutral site")
    L.append(f"  test set if run now: {pf['test_n']} {nb.V1R_TEST} '{REGULAR}' games (addendum 17 item 2: under "
             f"{MIN_SCORED} the run refuses before the reservation and records nothing)")
    L.append(f"  coverage: gate ({', '.join(GATE_SEASONS)}) {'COVERED' if pf['gate_covered'] else 'NOT COVERED — the run refuses'}"
             f" · confirmation ({', '.join(CONFIRM_SEASONS)}) {'COVERED' if pf['confirm_covered'] else 'NOT COVERED'}")
    L.append(f"  not walked: stale labels {pf['stale']} · current labels outside the seasons {pf['outside'] or 0} · "
             f"unlabelled or stale by season {pf['unlabelled'] or 0} · J2 merge groups {pf['merge_groups']}")
    L.append("PREFLIGHT only: nothing scored, nothing reserved, nothing recorded.")
    L.append(f"STREAM FINGERPRINT {pf['fingerprint']} ({pf['fingerprint_n']} games: the {nb.V1R_WARMUP} and "
             f"{nb.V1R_TEST} stream as the gate walks it; the run takes it as --stream-fingerprint)")
    return L


# ------------------------------------------------------------------------------------------- the DB: the run --

def run(word: str | None, fingerprint: str | None = None, no_fetch: bool = False, echo=None) -> dict:
    """The ONE run (D6, addendum 17). Checked BEFORE the reservation, each refusal exit 2 with nothing written:
    declared and unrun and unreserved; the architect's word given (non-empty, verbatim); the stream fingerprint
    given; 2024 and 2025 covered (L2 + L3; ingest records and label counts only). Then the stream is loaded
    (load_v1r_stream, the read --preflight makes; no model is built, nothing is scored) and the run refuses unless
    its fingerprint equals `fingerprint` (item 1), its scored set numbers >= 500 (item 2) and the D4 baseline is
    defined (addendum 21 item 4 (2): 2024 has a non-neutral 'regular' game). Then the reservation
    (after the cross-ref guard), carrying the word and the fingerprint, then the walk over that same loaded stream
    and the verdict. The caller records the run (record())."""
    declared_unrun()
    if not word or not str(word).strip():
        raise GateRefused("the run starts only on the architect's word (D6): pass --architect-word with it verbatim")
    if not fingerprint or not str(fingerprint).strip():
        raise GateRefused("the word refers to one stream (addendum 17 item 1): pass --stream-fingerprint with the "
                          "last line of ncaa-v1r-gate --preflight")
    fbs = coverage(GATE_SEASONS)
    require_coverage(fbs, GATE_SEASONS, "the gate run")
    v = nb.load_v1r_stream()                           # the stream about to be walked; nothing scored
    fp, fp_n = stream_fingerprint(v.games)
    if fp != str(fingerprint).strip():
        raise GateRefused(f"the stream no longer matches the fingerprint given (addendum 17 item 1): given "
                          f"{str(fingerprint).strip()}, the stream about to be walked is {fp} ({fp_n} games); "
                          "nothing reserved, nothing scored — re-run --preflight and take the architect's word on it")
    n_test = len(scored_set(v.games))
    if n_test < MIN_SCORED:
        raise GateRefused(f"the scored set numbers {n_test} < {MIN_SCORED} (addendum 17 item 2, #79's rule): not "
                          "scored, nothing reserved or recorded; re-run later, the bar does not move")
    if d4_baseline(v.games)[0] is None:                # addendum 21 item 4 (2): as under 500, before the reservation
        raise GateRefused(d4_undefined_why())
    reserve({"architect_word": word, "stream_fingerprint": fp, "stream_games": fp_n, "scored_set_n": n_test,
             "coverage": {s_: c.get("share") for s_, c in fbs.items()}}, no_fetch=no_fetch, echo=echo)
    # from here on, the one run is spent
    r = run_gate(v.games)
    r["stream_fingerprint"] = fp
    r["stream_games"] = fp_n
    r["census"] = {s_: dict(sorted(c.items())) for s_, c in sorted(v.census.items())}
    r["level_scores_skipped"] = dict(sorted(v.level_by_season.items()))
    r["coverage"] = {s_: c.get("share") for s_, c in fbs.items()}
    return r


def record(r: dict, word: str) -> dict:
    """registry.record_run: the scored ids (sidecar + sha256) and the result. A second run is refused there too."""
    reg = _reg()
    return reg.record_run(EID, r["scored_ids"], result_record(r, word), reg.LEDGER, reg.IDS_DIR)


def run_lines(r: dict) -> list[str]:
    f = lambda x, d=4: "—" if x is None else f"{x:.{d}f}"          # noqa: E731
    ok = lambda b: "PASS" if b else "FAIL"                          # noqa: E731
    L = [f"  D4 baseline: {nb.V1R_WARMUP} non-neutral '{REGULAR}' home win rate {f(r.get('baseline_home_rate'), 6)} "
         f"(n {r.get('baseline_n')}), frozen before the first test game; 0.5 at a neutral site"]
    if "walked_by_season" in r:
        L.append(f"  walked {r['walked_by_season']} · {nb.V1R_TEST} walked, never scored (by season_type) "
                 f"{r['walked_not_scored_2025_by_season_type'] or 'none'} · after the last {nb.V1R_TEST} game, not "
                 f"walked {r['not_walked_after_last_2025']} · no {nb.V1R_SEASONS[-1]} game scored")
    if r.get("stream_fingerprint"):
        L.append(f"  stream fingerprint {r['stream_fingerprint']} ({r.get('stream_games')} games walked), checked "
                 "before the reservation and recorded beside the word")
    L.append(f"  scored: {r['n_scored']} {nb.V1R_TEST} '{REGULAR}' games (addendum 17 item 2: under {MIN_SCORED} the "
             "run refuses before the reservation)")
    if r.get("ll_model") is not None:
        L.append(f"  (1) margin: model log-loss {r['ll_model']:.6f} vs baseline {r['ll_baseline']:.6f} − "
                 f"{LL_MARGIN:.3f} = bar {r['bar']:.6f} (strict, unrounded; a tie rejects) -> {ok(r['crit_margin'])}")
        L.append(f"  (2) level: mean model home p {r['mean_p']:.6f} vs realized home rate "
                 f"{r['realized_home_rate']:.6f}: gap {r['level_gap'] * 100:+.3f}pp (|gap| <= 5pp) -> "
                 f"{ok(r['crit_level'])}")
        L.append(f"  (3) spread: slope b " + (f"{r['slope_b']:.6f} (|b − 1| <= 0.20)" if r["slope_b"] is not None
                                               else "— (fit did not converge: fails)") + f" -> {ok(r['crit_spread'])}")
    if r.get("teams_rated") is not None:
        L.append(f"  (4) range: ratings after the last {nb.V1R_TEST} game walked {f(r['rating_min'], 1)}–"
                 f"{f(r['rating_max'], 1)} over {r['teams_rated']} teams (1000–2000)"
                 + (f" OUTLIERS {r['outliers']}" if r["outliers"] else "")
                 + (f" -> {ok(r['crit_range'])}" if "crit_range" in r else ""))
    if r.get("ll_model") is not None:
        L.append(f"  REPORTED, NEVER GATED: intercept a {f(r['intercept_a'])} · constant-0.5 log-loss "
                 f"{r['ll_const']:.4f} · Brier model {r['brier_model']:.4f} / baseline {r['brier_baseline']:.4f} · "
                 f"cold starts {r['cold_starts']}/{r['n_scored']} · log-loss neutral {f(r['ll_neutral'])} "
                 f"(n {r['n_neutral']}) / non-neutral {f(r['ll_nonneutral'])} (n {r['n_nonneutral']})")
        for b in r["bands_79"]:
            tag = ("ok" if b["ok"] else "miss") if b["gated"] else f"n < {nb.BAND_MIN_N}"
            L.append(f"      #79 band {b['band'] * 10:>2}-{b['band'] * 10 + 10}%: n {b['n']:>4} · stated "
                     f"{b['stated']:.3f} · realized {b['realized']:.3f} · {tag} (reported, never gated)")
    L.append(f"  VERDICT (computed; the architect rules): {r['verdict']}")
    return L


# ------------------------------------------------------------------------------- D7: the confirmation read --

def confirming() -> dict:
    """The entry, refusing unless it has its run record (with the D4 baseline) and a PASS verdict (confirming)."""
    reg = _reg()
    e = reg.get(EID, reg.LEDGER)
    if e is None or not e.get("run"):
        raise GateRefused(f"{EID} has no run record in docs/registry: the confirmation follows the one run")
    if (e.get("verdict") or {}).get("verdict") != "PASS":
        raise GateRefused(f"{EID} has no PASS verdict recorded: the confirmation window opens only after a PASS")
    rate = (e["run"].get("result") or {}).get("baseline_home_rate")
    if not isinstance(rate, (int, float)) or isinstance(rate, bool):
        raise GateRefused(f"{EID}'s run record lacks baseline_home_rate (the D4 baseline, frozen by the run)")
    return e


def _verdict_at(e) -> datetime:
    return datetime.fromisoformat(e["verdict"]["at"].replace("Z", "+00:00")).replace(tzinfo=None)


STALE_ORPHAN = "stale_orphan"


def eligible_fixtures(s, e, merge=None) -> list[dict]:
    """D7: every stored NCAA fixture kicking off after the verdict, by kickoff then id, whose two teams, as merged ids
    (J2), both carry a current label NOW (ncaa_shadow.fbs_teams: current labels only, L3); ANY status. Result
    availability never enters. A STALE_ORPHAN row is not a fixture (MatchStatus: "never deleted, never a fixture,
    never an odds target"), so it is never eligible, at the freeze or as a replacement (Codex on #375)."""
    from sqlalchemy import select

    from src.db.schema import Competition, Match, Sport
    from src.ingestion.ncaa_cfbd import ncaa_teams
    from src.walters.ncaa_shadow import fbs_teams

    merge = merge or nb.team_merge(ncaa_teams(s))
    fbs = fbs_teams(s, merge)
    at = _verdict_at(e)
    out = []
    q = (select(Match).join(Competition, Match.competition_id == Competition.id)
         .where(Match.sport == Sport.NFL, Competition.code == COMPETITION, Match.utc_date > at)
         .order_by(Match.utc_date, Match.id))
    for m in s.execute(q).scalars():
        if merge(m.home_team_id) not in fbs or merge(m.away_team_id) not in fbs:
            continue
        status = m.status.value if hasattr(m.status, "value") else str(m.status)
        if status == STALE_ORPHAN:      # a retired provider row is "never a fixture" (schema, ARCHITECT 2026-10-03)
            continue
        out.append({"id": m.id, "kickoff": m.utc_date, "status": status, "status_raw": m.status_raw,
                    "releasable": status == "cancelled"})
    return out


def cohort(e, s) -> dict:
    """The frozen ids (registry.frozen_cohort, substitutions applied) when frozen; else the provisional first n
    eligible fixtures (possibly fewer while the schedule is short)."""
    reg = _reg()
    n = e["confirmation_plan"]["n_games"]
    elig = eligible_fixtures(s, e)
    try:
        frozen_ids = reg.frozen_cohort(e, reg.IDS_DIR)
    except reg.RegistryError as err:
        raise GateRefused(str(err))
    if frozen_ids is not None:
        return {"state": "frozen", "ids": frozen_ids, "n_games": n, "eligible_stored": len(elig)}
    return {"state": "provisional", "ids": [f["id"] for f in elig[:n]], "n_games": n,
            "eligible_stored": len(elig), "fixtures": elig[:n]}


def _statuses(s, ids) -> dict[int, dict]:
    from sqlalchemy import select

    from src.db.schema import Match
    if not ids:
        return {}
    out = {}
    for m in s.execute(select(Match).where(Match.id.in_(list(ids)))).scalars():
        status = m.status.value if hasattr(m.status, "value") else str(m.status)
        out[m.id] = {"id": m.id, "kickoff": m.utc_date, "status": status, "status_raw": m.status_raw}
    return out


def substitutions_due(e, s) -> list[dict]:
    """D7 (verbatim): "A cancelled fixture is released and replaced by the next eligible one. A finished fixture
    without a label is pending, never replaced." Every CANCELLED fixture of the frozen cohort is released; its
    replacement is the next eligible fixture after every fixture that is or was in the cohort (kickoff, then id),
    never cancelled itself, never one already used. Postponed / scheduled / live / finished fixtures stay. The reason
    is the stored raw status code (else the status). Read-only: the write is ncaa-v1r-confirm --substitute."""
    c = e.get("confirmation_cohort")
    if not c:
        return []
    co = cohort(e, s)
    elig = eligible_fixtures(s, e)
    ever = set(co["ids"]) | {int(x["released"]) for x in c.get("substitutions") or []}
    st = _statuses(s, ever)
    last = max(((st[i]["kickoff"], i) for i in ever if i in st), default=None)
    pool = [f for f in elig if f["id"] not in ever and not f["releasable"]
            and (last is None or (f["kickoff"], f["id"]) > last)]
    out = []
    for i in co["ids"]:
        f = st.get(i)
        if f is None or f["status"] != "cancelled":
            continue
        out.append({"released": f, "replacement": pool.pop(0) if pool else None,
                    "reason": (f["status_raw"] or f["status"]).upper()})
    return out


def score_cohort(games, cohort_ids, rate: float, model=None) -> dict:
    """D7: "Scored by the same replay as the gate, the label's flags applied, every cohort fixture whatever its
    season_type." The D2 stream walked in order with the D1 wrapper; a cohort fixture carrying a current label is
    predicted, then updated, whatever its season_type; the D4 baseline (the run's frozen rate; 0.5 at a neutral
    site) priced on the same games. Pure."""
    model = model or nb.NeutralRuleElo()
    want = set(cohort_ids)
    rows, first = [], None
    for g in games:
        if g.match_id in want:
            p = model.predict(g)
            rows.append((g.match_id, p, baseline_p(g, rate), g.home_win))
            first = g.utc_date if first is None else min(first, g.utc_date)
        model.update(g)
    n = len(rows)
    out = {"n": n, "scored_ids": [r[0] for r in rows], "first_game_at": _iso(first)}
    if n:
        ll = sum(nb._ll(r[1], r[3]) for r in rows) / n
        base = sum(nb._ll(r[2], r[3]) for r in rows) / n
        out.update({"log_loss": ll, "baseline_log_loss": base, "reference_log_loss": base - LL_MARGIN})
    return out


def confirmation_read() -> dict:
    """The plan's read so far: refuses unless PASS (confirming) and 2024, 2025 and 2026 covered (D6)."""
    from src.db.database import session_scope

    e = confirming()
    require_coverage(coverage(CONFIRM_SEASONS), CONFIRM_SEASONS, "the confirmation read")
    with session_scope() as s:
        co = cohort(e, s)
        st = _statuses(s, co["ids"])
        s.rollback()
    v = nb.load_v1r_stream()
    # D7: "A cancelled fixture is released and replaced by the next eligible one." A cancelled cohort fixture is never
    # scored, label or not: it stays pending (release due) until --substitute replaces it (Codex on #375).
    live = [i for i in co["ids"] if (st.get(i) or {}).get("status") != "cancelled"]
    sc = score_cohort(v.games, live, float(e["run"]["result"]["baseline_home_rate"]))
    plan = e["confirmation_plan"]
    pending = sorted(set(co["ids"]) - set(sc["scored_ids"]))
    return {**sc, "n_games": plan["n_games"], "bar": plan["bar"], "cohort_state": co["state"],
            "cohort_size": len(co["ids"]), "eligible_stored": co["eligible_stored"],
            "pending": [{"id": i, "status": (st.get(i) or {}).get("status", "not stored")} for i in pending],
            "release_due": sum(1 for i in pending if (st.get(i) or {}).get("status") == "cancelled"
                               and co["state"] == "frozen"),
            "complete": co["state"] == "frozen" and not pending and sc["n"] == plan["n_games"]}


def freeze(no_fetch: bool = False, echo=None) -> dict:
    """--freeze-cohort: the first n eligible fixtures, frozen once by fixture id (registry
    .freeze_confirmation_cohort, which calls the #329 cross-ref guard before it writes)."""
    from src.db.database import session_scope

    reg = _reg()
    e = confirming()
    require_coverage(coverage(CONFIRM_SEASONS), CONFIRM_SEASONS, "the cohort freeze")
    with session_scope() as s:
        co = cohort(e, s)
        s.rollback()
    if co["state"] == "frozen":
        raise GateRefused("the cohort is already frozen — a frozen cohort never changes")
    if len(co["ids"]) < co["n_games"]:
        raise GateRefused(f"{co['eligible_stored']} eligible fixtures stored < {co['n_games']} — sync the NCAA "
                          "schedule before freezing")
    fx = co["fixtures"]
    basis = {"selected_at": _iso(utc_now_naive()),
             "rule": "D7: first n stored NCAA fixtures by (kickoff, id) kicking off after the verdict whose two teams "
                     "(J2 merged ids) both carry a current CFBD label at the freeze; ANY status",
             "eligible_stored": co["eligible_stored"], "first_kickoff": _iso(fx[0]["kickoff"]),
             "last_kickoff": _iso(fx[-1]["kickoff"]),
             "status_at_freeze": dict(Counter(f["status"] for f in fx))}
    return reg.freeze_confirmation_cohort(EID, co["ids"], basis, reg.LEDGER, reg.IDS_DIR, no_fetch=no_fetch,
                                          echo=echo)


def substitute(echo=print) -> int:
    """--substitute: registry.substitute_cohort_fixture for every cancelled cohort fixture with a replacement."""
    from src.db.database import session_scope

    reg = _reg()
    e = confirming()
    require_coverage(coverage(CONFIRM_SEASONS), CONFIRM_SEASONS, "the substitution")
    with session_scope() as s:
        due = substitutions_due(e, s)
        s.rollback()
    done = 0
    for d in due:
        f, rep = d["released"], d["replacement"]
        if rep is None:
            echo(f"  WAITING: {f['id']} ({d['reason']}) — no eligible fixture after the cohort is stored yet")
            continue
        reg.substitute_cohort_fixture(EID, f["id"], rep["id"], d["reason"], {
            "status": f["status"], "status_raw": f["status_raw"], "unscoreable": True, "kickoff": _iso(f["kickoff"]),
            "replacement_kickoff": _iso(rep["kickoff"])}, reg.LEDGER, reg.IDS_DIR)
        echo(f"  SUBSTITUTED: {f['id']} ({d['reason']}, {_iso(f['kickoff'])}) -> {rep['id']} "
             f"({_iso(rep['kickoff'])})")
        done += 1
    return done


def record_confirmation(r: dict, ruling: str) -> dict:
    """registry.record_confirmation: CONFIRMED iff log-loss <= 0.6931 and < the D4 baseline's log-loss − 0.010 on
    the same games (computed there; a tie fails)."""
    reg = _reg()
    if not r["complete"]:
        raise GateRefused("the read is incomplete — " + ("the cohort is not frozen (--freeze-cohort)"
                          if r["cohort_state"] != "frozen" else f"{len(r['pending'])} cohort fixture(s) lack a "
                                                                 "current label (pending, never replaced)"))
    return reg.record_confirmation(EID, r["scored_ids"], {
        "log_loss": r["log_loss"], "reference_log_loss": r["reference_log_loss"],
        "baseline_log_loss": r["baseline_log_loss"], "first_game_at": r["first_game_at"]}, ruling,
        reg.LEDGER, reg.IDS_DIR)
