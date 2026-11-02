"""
nfl-elo-v2: THE ONE-RUN GATE (GATE-CLASS). ARCHITECT 2026-11-02 10:35 ET, addendum 215.

Item 2 (verbatim): "a successor candidate, nfl_elo_v2, through the FROZEN phase-2 gate on the CORRECTED stream, one
run. The protocol is unchanged and not re-read against friendlier numbers: warm-up 2024 complete (285), scored 2025
regular + post (285), preseason excluded, baseline the warm-up's realized home rate, PASS iff log-loss ≤ baseline −
0.010 AND every band with n ≥ 30 within 7pp; then the gate's own promotion path — a two-week rehearsal (shadow on the
host's pages beside the uncertified v1) and the GPT dry read — then live by my ruling. The constants are chosen BEFORE
the run and written into the declaration; the 2025 scored set is read once. The failing mode is overconfidence in the
70–80% band, so the candidate's one change is a calibration term fitted on the WARM-UP season only (2024's own
realized-vs-stated gap, never 2025's): the exact form Code proposes in the declaration PR from the 2024 walk (a
probability shrink toward 0.5, or a smaller home advantage, one or the other, with its 2024-fitted value) — I rule the
form, the PR writes it before any 2025 figure is printed."
Item 3 (in part, verbatim): "11-03 code — the harness PR (the candidate entry nfl_elo_v2 with its constants and bar, a
one-run gate with the reservation pattern of ncaa-gate: the architect's word, the stream fingerprint, nothing recorded
on a refusal; the corrected stream as the fingerprint)".

    nfl-v2-gate --preflight            scores nothing: the scope line, the warm-up and scored counts (printed beside
                                       215's 285, never asserted), the 2024 baseline, the declared term (or NOT
                                       DECLARED), the warm-up fingerprint against the one the fit read; its last line
                                       is the stream fingerprint. No 2025 outcome is computed or printed.
    nfl-v2-gate --architect-word T --stream-fingerprint F
                                       the ONE run: refused (exit 2, nothing written, nothing recorded) unless the
                                       entry is declared and unrun and unreserved, the word and the fingerprint are
                                       given, and the calibration term is declared (exactly one form, a valid value);
                                       then the stream is loaded (nothing scored) and the run refuses unless both
                                       seasons hold games and its fingerprint is F; then the reservation (after the
                                       #329 cross-ref guard) carrying the word and the fingerprint, written BEFORE the
                                       first game is scored; then the frozen protocol's walk (nfl_backtest
                                       .walk_protocol, the code nfl-backtest runs) and the record (registry
                                       .record_run: the scored 2025 ids and the result, the word and the fingerprint).

THE MACHINERY IS ncaa-gate's (src/walters/ncaa_v1r_gate.py): declared_unrun, the word, the fingerprint checked against
the stream about to be walked, reserve() after registry.cross_ref_guard with an exclusive create, record_run. It is
mirrored here, not shared, because ncaa's Spec is college-shaped (coverage, labels, D4/D5); the order and the
refusals are the same.

THE CANDIDATE (215 item 2): nfl_elo_v1's walk (nfl_backtest.NFLEloConfig, constants untouched) with ONE calibration
term, exactly one of:
    shrink           p' = 0.5 + s·(p − 0.5) on the stated home probability, at pricing only: ratings and updates are
                     v1's (the price-only reading of ncaa-elo-v2's s, addendum 86 item 3). 0 < s < 1.
    home_advantage   NFLEloConfig.home_advantage (v1: 48.0 Elo points) replaced by the declared value for the whole
                     walk, warm-up and scored, price and update ("the Elo home advantage parameter replaced").
                     0 <= h < 48.0.
Both ranges are strict on v1's side: 215 item 2 rules "a probability shrink toward 0.5, or a smaller home advantage",
so a value that leaves v1 unchanged (s = 1, h = 48) or moves the other way (s > 1, h > 48, h < 0) refuses before the
reservation.
The form and its 2024-fitted value are ruled by the architect's declaration of 2026-11-05 and written into the
registry entry (calibration_term) before the run; the gate refuses while neither or both are set. The fit is
src/walters/nfl_v2_fit.py (nfl-v2-fit-warmup): 2024 rows only.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import replace
from datetime import datetime

from src.timeutil import utc_now_naive
from src.walters import nfl_backtest as nb

EID = "nfl-elo-v2"
COMMAND = "nfl-v2-gate"
RULING = "ARCHITECT 2026-11-02 10:35 ET, addendum 215 items 2-3"
EXPECTED_WARMUP_N = 285            # 215 item 2: "warm-up 2024 complete (285)"; printed beside, never asserted
EXPECTED_SCORED_N = 285            # 215 item 2: "scored 2025 regular + post (285)"; printed beside, never asserted
TERM_KEY = "calibration_term"      # the registry entry's block: {"shrink": s|null, "home_advantage": h|null, ...}
FORMS = ("shrink", "home_advantage")

# The stream fingerprint (ncaa-gate's addendum 17 item 1 pattern: "the games in order, with every label field the gate
# reads"). The fields, each read by the walk or defining its order:
#   match_id     the scored ids and the order's tie-break (kickoff, then id)
#   utc_date     the walk's order
#   season       the split (2024 warm-up, 2025 scored) and the per-team season regression
#   stage        the preseason exclusion (the walked rows carry the stage they were kept on)
#   home_id, away_id, home_score, away_score   the ratings, the outcome and the margin of victory
# Over the rows the gate walks: the 2024 and 2025 non-preseason FINISHED NFL rows with both scores. The 16 games #775
# turned FINISHED are in it, so the corrected stream and the defective one have different fingerprints.
FINGERPRINT_FIELDS = ("match_id", "utc_date", "season", "stage", "home_id", "away_id", "home_score", "away_score")
FINGERPRINT_TAG = f"{EID} stream fingerprint v1"
WARMUP_TAG = f"{EID} warm-up fingerprint v1"


class GateRefused(RuntimeError):
    """A precondition is not met: printed with its reason, exit 2; nothing written, nothing recorded."""


def _reg():
    from src.walters import registry as reg
    return reg


def _iso(d: datetime | None) -> str | None:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ") if d else None


# ------------------------------------------------------------------------------------- the calibration term --

def term_state(e: dict | None) -> tuple[str | None, float | None, str | None]:
    """(form, value, None) when the entry declares exactly one form with a valid value; (None, None, why) otherwise."""
    blk = (e or {}).get(TERM_KEY)
    if not isinstance(blk, dict):
        return None, None, f"the registry entry has no {TERM_KEY} block"
    set_ = [f for f in FORMS if blk.get(f) is not None]
    if not set_:
        return None, None, (f"the calibration term is not declared ({TERM_KEY}.shrink and {TERM_KEY}.home_advantage "
                            "are both null): the form and its 2024-fitted value are ruled by the architect's "
                            "declaration of 2026-11-05 (addendum 215 item 3) and written into the entry before the run")
    if len(set_) > 1:
        return None, None, (f"both forms are set ({TERM_KEY}.shrink {blk['shrink']!r} and {TERM_KEY}.home_advantage "
                            f"{blk['home_advantage']!r}): the candidate's one change is one or the other (addendum "
                            "215 item 2)")
    form, v = set_[0], blk[set_[0]]
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        return None, None, f"{TERM_KEY}.{form} is {v!r}, not a finite number"
    # 215 item 2 names the direction of each form: "a probability shrink toward 0.5, or a smaller home advantage". A
    # value that changes nothing (s = 1, h = v1's) would spend the one read of 2025 on nfl_elo_v1 under a new id; one
    # that goes the other way (s > 1, h > v1's, h < 0) is not the change ruled. Both refuse here, before the reservation.
    if form == "shrink" and not 0 < v < 1:
        return None, None, (f"{TERM_KEY}.shrink is {v!r}: addendum 215 item 2 rules \"a probability shrink toward "
                            "0.5, or a smaller home advantage\"; a shrink toward 0.5 is 0 < s < 1 (s = 1 is "
                            "nfl_elo_v1 unchanged, s > 1 an expansion away from 0.5)")
    v1_h = nb.NFLEloConfig().home_advantage
    if form == "home_advantage" and not 0 <= v < v1_h:
        return None, None, (f"{TERM_KEY}.home_advantage is {v!r}: addendum 215 item 2 rules \"a probability shrink "
                            f"toward 0.5, or a smaller home advantage\"; a smaller home advantage is 0 <= h < "
                            f"{v1_h!r} (nfl_elo_v1's; h = {v1_h!r} is nfl_elo_v1 unchanged, h < 0 an away advantage)")
    return form, float(v), None


def declared_term(e: dict | None) -> tuple[str, float]:
    form, v, why = term_state(e)
    if why:
        raise GateRefused(f"{EID}: {why}; nothing reserved, nothing scored")
    return form, v


def candidate(form: str, value: float):
    """(the walk's NFLEloConfig, the price map) for a declared term. v1's constants otherwise untouched."""
    base = nb.NFLEloConfig()
    if form == "shrink":
        return base, (lambda p, s=value: 0.5 + s * (p - 0.5))
    if form == "home_advantage":
        return replace(base, home_advantage=value), None
    raise GateRefused(f"{EID}: unknown calibration form {form!r} (one of {', '.join(FORMS)})")


def describe(form: str | None, value: float | None) -> str:
    if form == "shrink":
        return f"shrink s = {value!r}: p' = 0.5 + s·(p − 0.5), price only (ratings and updates v1's)"
    if form == "home_advantage":
        return (f"home advantage {value!r} Elo points (v1: {nb.NFLEloConfig().home_advantage!r}), the whole walk "
                "(price and update)")
    return "NOT DECLARED"


# ----------------------------------------------------------------------------------------- the fingerprints --

def _fp_value(v):
    return v.strftime("%Y-%m-%dT%H:%M:%S.%f") if isinstance(v, datetime) else v


def _digest(tag: str, rows) -> tuple[str, int]:
    body = {"tag": tag, "fields": list(FINGERPRINT_FIELDS),
            "games": [[_fp_value(getattr(g, f)) for f in FINGERPRINT_FIELDS] for g in rows]}
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("ascii")).hexdigest(), len(rows)


def stream_fingerprint(warmup, scored) -> tuple[str, int]:
    """sha256 over the stream exactly as the gate walks it: the warm-up rows then the scored rows, in walk order, each
    carrying FINGERPRINT_FIELDS (JSON, sorted keys, no whitespace). (hex digest, number of games)."""
    return _digest(FINGERPRINT_TAG, list(warmup) + list(scored))


def warmup_fingerprint(warmup) -> tuple[str, int]:
    """sha256 over the 2024 warm-up rows alone: the stream the fit read (nfl-v2-fit-warmup prints it; the declaration
    may record it as calibration_term.fit.warmup_fingerprint, and --preflight compares)."""
    return _digest(WARMUP_TAG, list(warmup))


# ------------------------------------------------------------------------------------- the reservation --

RESERVATION = None                  # None = docs/registry/nfl-elo-v2.started.json (tests point it at a tmp path)


def reservation_path() -> str:
    return RESERVATION or os.path.join(os.path.dirname(_reg().LEDGER), f"{EID}.started.json")


def _reserved_why(p: str) -> str:
    try:
        with open(p) as f:
            at = json.load(f).get("started_at", "?")
    except (OSError, ValueError):
        at = "?"
    return (f"{EID}: a run was started at {at} ({os.path.relpath(p)}) and the 2025 scored set may have been read; it "
            "is the one run, recorded or not. Nothing reruns without an architect ruling")


def reserve(meta: dict, no_fetch: bool = False, echo=None) -> str:
    """ncaa-gate's reserve(): the #329 cross-ref guard first, then the exclusive create of the reservation, before the
    first game is scored."""
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
        json.dump({"id": EID, "started_at": _iso(utc_now_naive()), "guard": receipt, **meta}, f)
        f.write("\n")
    return p


def declared_unrun() -> dict:
    """The registry entry, refusing unless declared and unrun (the 2025 scored set is read once) and unreserved."""
    reg = _reg()
    e = reg.get(EID, reg.LEDGER)
    if e is None or e.get("status") != "declared" or e.get("run") is not None:
        raise GateRefused(f"{EID} must be declared and unrun in the registry (status "
                          f"{e.get('status') if e else 'absent'}): the 2025 scored set is read once")
    if os.path.exists(reservation_path()):
        raise GateRefused(_reserved_why(reservation_path()))
    return e


# ------------------------------------------------------------------------------------------ the preflight --

def _by(rows, key) -> dict:
    out: dict = {}
    for r in rows:
        k = key(r)
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))


def preflight(rows, entry: dict | None, preseason: dict | None = None) -> dict:
    """Pure over the loaded stream (nfl_backtest.load_stream: preseason already excluded). Counts per season and per
    stage, the 2024 baseline, the declared term, the fingerprints. No model is built; no 2025 outcome is computed."""
    warmup, scored = nb.split(rows)
    fp, fp_n = stream_fingerprint(warmup, scored)
    wfp, wn = warmup_fingerprint(warmup)
    form, value, why = term_state(entry)
    fit = (((entry or {}).get(TERM_KEY) or {}).get("fit") or {})
    return {"warmup_n": len(warmup), "scored_n": len(scored),
            "warmup_by_stage": _by(warmup, lambda r: r.stage or "(none)"),
            "scored_by_stage": _by(scored, lambda r: r.stage or "(none)"),
            "not_walked_by_season": _by([r for r in rows if r.season not in (nb.WARMUP_SEASON, nb.SCORED_SEASON)],
                                        lambda r: r.season),
            "preseason_excluded": preseason or {},
            "baseline_home_rate": nb.baseline_rate(warmup) if warmup else None,
            "form": form, "value": value, "term_why": why,
            "fit_warmup_fingerprint": fit.get("warmup_fingerprint") if isinstance(fit, dict) else None,
            "warmup_fingerprint": wfp, "warmup_fingerprint_n": wn,
            "fingerprint": fp, "fingerprint_n": fp_n}


def _count_line(what: str, n: int, want: int) -> str:
    return (f"{n} games (addendum 215 item 2 names {want}: "
            + ("the same" if n == want else f"DIFFERS by {n - want:+d} — the architect reads this line") + ")")


def preflight_lines(pf: dict, scope: str | None = None) -> list[str]:
    L = [f"NFL-ELO-V2 · PREFLIGHT (scores nothing) · warm-up {nb.WARMUP_SEASON} complete (update only) · scored "
         f"{nb.SCORED_SEASON} regular + post (predict, then update) · preseason excluded · {RULING}"]
    if scope:
        L.append(f"  {scope}")
    L.append(f"  warm-up {nb.WARMUP_SEASON}: " + _count_line("warm-up", pf["warmup_n"], EXPECTED_WARMUP_N)
             + " · by stage " + (", ".join(f"{k} {n}" for k, n in pf["warmup_by_stage"].items()) or "none"))
    L.append(f"  scored {nb.SCORED_SEASON}: " + _count_line("scored", pf["scored_n"], EXPECTED_SCORED_N)
             + " · by stage " + (", ".join(f"{k} {n}" for k, n in pf["scored_by_stage"].items()) or "none")
             + f" (counts only: no {nb.SCORED_SEASON} outcome is read)")
    pre = pf["preseason_excluded"]
    L.append("  preseason excluded: " + (", ".join(f"{k} {n}" for k, n in pre.items()) or "none")
             + " · other seasons, never walked: "
             + (", ".join(f"{k} {n}" for k, n in pf["not_walked_by_season"].items()) or "none"))
    rate = pf["baseline_home_rate"]
    L.append("  baseline (the frozen protocol: the warm-up's realized home rate): "
             + (f"{rate:.6f} ({pf['warmup_n']} games)" if rate is not None else "UNDEFINED (no warm-up game)"))
    L.append("  calibration term: " + (describe(pf["form"], pf["value"]) if pf["form"] else
                                       f"NOT DECLARED — the run refuses: {pf['term_why']}"))
    rec = pf["fit_warmup_fingerprint"]
    state = ("not recorded in the entry" if not rec else
             "SAME" if rec == pf["warmup_fingerprint"] else
             "CHANGED since the fit (the architect reads this line)")
    L.append(f"  warm-up fingerprint {pf['warmup_fingerprint']} ({pf['warmup_fingerprint_n']} games; nfl-v2-fit-warmup "
             f"prints it) · the fit's, as the entry records it: {rec or '—'} · {state}")
    if not pf["warmup_n"] or not pf["scored_n"]:
        L.append("  the run refuses: the protocol needs both seasons (insufficient seasons for protocol)")
    L.append("PREFLIGHT only: nothing scored, nothing reserved, nothing recorded.")
    L.append(f"STREAM FINGERPRINT {pf['fingerprint']} ({pf['fingerprint_n']} games: the {nb.WARMUP_SEASON} and "
             f"{nb.SCORED_SEASON} stream as the gate walks it; the run takes it as --stream-fingerprint)")
    return L


def preseason_counts() -> dict:
    """The preseason rows the stream excludes, per season (counts only; nothing else read)."""
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Match, MatchStatus

    with session_scope() as s:
        rows = s.execute(nb.nfl_scoped(select(Match.season, Match.stage)).where(
            Match.status == MatchStatus.FINISHED, Match.home_score.is_not(None),
            Match.away_score.is_not(None))).all()
        s.rollback()
    return _by([r for r in rows if nb.is_preseason(r[1])], lambda r: r[0])


def preflight_read(entry: dict | None) -> list[str]:
    """--preflight's one read: the stream (nfl_backtest.load_stream), the preseason count; then preflight()."""
    scope: list[str] = []
    rows = nb.load_stream(COMMAND, scope.append)
    return preflight_lines(preflight(rows, entry, preseason_counts()), scope[0] if scope else None)


# ---------------------------------------------------------------------------------------------- the run --

def verdict_text(passed: bool, w: dict) -> str:
    if passed:
        return ("PASS — the architect rules; then the gate's own promotion path (215 item 2): the two-week rehearsal "
                "(shadow on the host's pages beside the uncertified v1) and the dry read, then live by ruling")
    why = []
    if not w["crit_logloss"]:
        why.append("(1) log-loss")
    if not w["crit_bands"]:
        why.append("(2) bands: " + ", ".join(f"{b['band'] * 10}-{b['band'] * 10 + 10}%" for b in w["bands"]
                                              if b["gated"] and not b["ok"]))
    return ("FAIL — " + "; ".join(why) + " (215 item 3: NFL stays market-only for 2026; v1's forward read of item 1 "
            "stands; the 2027 candidate declares in the offseason)")


def run(word: str | None, fingerprint: str | None, no_fetch: bool = False, echo=None) -> dict:
    """The ONE run. Checked BEFORE the reservation, each refusal exit 2 with nothing written: declared and unrun and
    unreserved; the word (non-empty, verbatim); the fingerprint; the calibration term declared (exactly one form, a
    valid value). Then the stream is loaded (nfl_backtest.load_stream, the read --preflight makes; nothing scored) and
    the run refuses unless both seasons hold games and its fingerprint equals `fingerprint`. Then the reservation
    (after the cross-ref guard), carrying the word, the fingerprint and the term; then the frozen protocol's walk over
    that same loaded stream. The caller records the run (record())."""
    e = declared_unrun()
    if not word or not str(word).strip():
        raise GateRefused("the run starts only on the architect's word (215 item 3): pass --architect-word with it "
                          "verbatim")
    if not fingerprint or not str(fingerprint).strip():
        raise GateRefused("the word refers to one stream (ncaa-gate's addendum 17 item 1): pass --stream-fingerprint "
                          f"with the last line of {COMMAND} --preflight")
    form, value = declared_term(e)
    scope: list[str] = []
    rows = nb.load_stream(COMMAND, scope.append)               # the stream about to be walked; nothing scored
    warmup, scored = nb.split(rows)
    if not warmup or not scored:
        raise GateRefused(f"the stream holds {len(warmup)} warm-up ({nb.WARMUP_SEASON}) and {len(scored)} scored "
                          f"({nb.SCORED_SEASON}) games: insufficient seasons for protocol; nothing reserved or "
                          "recorded, the read is not spent")
    fp, fp_n = stream_fingerprint(warmup, scored)
    if fp != str(fingerprint).strip():
        raise GateRefused(f"the stream no longer matches the fingerprint given: given {str(fingerprint).strip()}, the "
                          f"stream about to be walked is {fp} ({fp_n} games); nothing reserved, nothing scored — "
                          f"re-run {COMMAND} --preflight and take the architect's word on it")
    meta = {"architect_word": word, "stream_fingerprint": fp, "stream_games": fp_n, "warmup_n": len(warmup),
            "scored_n": len(scored), "calibration_term": {"form": form, "value": value}}
    reserve(meta, no_fetch=no_fetch, echo=echo)
    # from here on, the one run is spent
    cfg, price = candidate(form, value)
    lines: list[str] = []
    w = nb.walk_protocol(warmup, scored, cfg, price, lines.append)
    w.update({"verdict": verdict_text(w["pass"], w), "protocol_lines": lines, "scope": scope[0] if scope else None,
              "stream_fingerprint": fp, "stream_games": fp_n, "warmup_n": len(warmup), "scored_n": len(scored),
              "calibration_term": {"form": form, "value": value},
              "constants": {k: getattr(cfg, k) for k in ("k_factor", "home_advantage", "season_regression",
                                                         "mov_base", "default_rating")}})
    return w


def result_record(r: dict, word: str) -> dict:
    """The durable run record (registry run.result): everything but the scored ids (the sidecar holds them); the word
    verbatim and the fingerprint the run checked beside it; the bands rounded to 6 places for reading."""
    rec = {k: v for k, v in r.items() if k not in ("scored_ids", "protocol_lines")}
    rec["bands"] = [{**b, "stated": round(b["stated"], 6), "realized": round(b["realized"], 6),
                     "gap": round(b["gap"], 6)} for b in r["bands"]]
    rec["architect_word"] = word
    return rec


def record(r: dict, word: str) -> dict:
    """registry.record_run: the scored 2025 ids (sidecar + sha256) and the result. A second run is refused there too."""
    reg = _reg()
    return reg.record_run(EID, list(r["scored_ids"]), result_record(r, word), reg.LEDGER, reg.IDS_DIR)


def run_lines(r: dict) -> list[str]:
    L = []
    if r.get("scope"):
        L.append(f"  {r['scope']}")
    L.append(f"  stream fingerprint {r['stream_fingerprint']} ({r['stream_games']} games: warm-up {r['warmup_n']}, "
             f"scored {r['scored_n']}), checked before the reservation and recorded beside the word")
    L.append(f"  candidate: nfl_elo_v1's constants {r['constants']} · {describe(**r['calibration_term'])}")
    L += [f"  {x}" for x in r["protocol_lines"]]
    for b in r["bands"]:
        if not b["gated"]:
            L.append(f"    band {b['band'] * 10}-{b['band'] * 10 + 10}%: n={b['n']} < {nb.BAND_MIN_N}: reported, not "
                     f"scored (stated {b['stated']:.3f} realized {b['realized']:.3f})")
    L.append(f"  VERDICT (computed; the architect rules): {r['verdict']}")
    return L
