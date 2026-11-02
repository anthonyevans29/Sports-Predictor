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

    nfl-v2-gate --preflight [--db COPY]
                                       scores nothing: the scope line (naming the database read), the warm-up and
                                       scored counts (printed beside 215's 285, never asserted), the 2024 baseline,
                                       the declared term (or NOT DECLARED: the run refuses), the entry's frozen
                                       constants against NFLEloConfig()'s (SAME, or DIFFERS: the run refuses), the
                                       warm-up fingerprint against the one the fit recorded (fit null or CHANGED: the
                                       run refuses); its last line is the stream fingerprint, which binds the
                                       declared term (v2, below). No 2025 outcome is computed or printed.
    nfl-v2-gate --architect-word T --stream-fingerprint F [--db COPY]
                                       the ONE run: refused (exit 2, nothing written, nothing recorded) unless the
                                       entry is declared and unrun and unreserved, the word and the fingerprint are
                                       given, the calibration term is declared (exactly one form, a valid value) and
                                       its fit is recorded (calibration_term.fit with a warmup_fingerprint), and the
                                       entry's frozen constants are NFLEloConfig()'s exactly; then the stream is
                                       loaded (nothing scored) and the run refuses unless both seasons hold
                                       games, the fit's warm-up fingerprint is the loaded 2024 rows', and the stream
                                       fingerprint (the rows AND the term) is F; then the reservation (after the #329
                                       cross-ref guard) carrying the word, the fingerprints and the term, written
                                       BEFORE the first game is scored, whole or absent (a failed write is removed
                                       and the run refuses, the read not spent); then the frozen protocol's walk
                                       (nfl_backtest.walk_protocol, the code nfl-backtest runs) and the record
                                       (registry.record_run: the scored 2025 ids and the result, the word and the
                                       fingerprints).

ADDENDUM 219 item 4 (ARCHITECT 2026-11-02 12:20 ET, verbatim): "BINDING — RULED IN, the one push before merge: the run
REFUSES when `fit` is null or when the fit's warm-up fingerprint differs from the run's warm-up fingerprint, and the
term's value is INSIDE the fingerprint the architect's word binds to (the word names the term). Tests: the null fit,
the stale fit, the term inside the fingerprint. The refusal records nothing." Built: fit_binding() refuses a null fit
(or one without its warmup_fingerprint) before the stream is loaded; after the load the fit's warm-up fingerprint is
compared with the loaded 2024 rows' (the digest --preflight prints); the STREAM FINGERPRINT (v2) digests the declared
term (form and value, exactly as the run uses them) beside the rows, so a term edited after the word changes it and the
run refuses. Every one of these refusals precedes reserve(): nothing reserved, nothing recorded.

ADDENDUM 219 item 6 (verbatim): "THE DATABASE on 11-06 — a fresh .backup COPY outside data/, opened with `--db` and
immutable=1 (the standing rule of addendum 198 item 6(ii), the mlb-pitchers pattern), taken by my block that morning
after the 11-04 live re-sync has put the corrected 2024 rows on the laptop; the preflight's fingerprint on that copy is
the run's. The registry write goes to the repo, not the DB." Built: --db PATH goes through mlb_pitchers_gate's own
check_db (refused under any data/ by resolved path or by identity, refused when it is the app's configured database,
refused when missing: never created) and its readonly_session (a mode=ro&immutable=1 URI: no write, no sidecar); the
stream and the preseason count are read through that session. The ONE run REFUSES without --db (item 6 names the copy
for 11-06, and the mlb-pitchers pattern it cites requires --db: "the gate never reads the live database"); --preflight
keeps DATABASE_URL without it (215 item 3's 11-04 preflight reads the live DB). A copy with a -wal, -shm or -journal
file beside it is refused: immutable=1 would read the main file alone and miss committed pages still in the WAL, and a
fresh .backup copy has none.

CODEX P1s on #784 (verified, fixed in the PR): (a) THE CONSTANTS. The registry entry's "constants" block is the
declaration's frozen constants (215 item 2: "The constants are chosen BEFORE the run and written into the
declaration"); candidate() builds the walk from NFLEloConfig()'s defaults, so the run refuses (declared_constants,
before the stream is loaded and before reserve(): nothing read, nothing reserved, nothing recorded) when the entry has
no constants block, a key is missing or extra against NFLEloConfig's dataclass fields (a field added to the config
later is walked but not frozen: refused), or any value differs from NFLEloConfig()'s by exact float equality
(home_advantage against v1's base default; the home_advantage form replaces it separately). The refusal is the
binding: the constants are not in the stream fingerprint. --preflight prints the comparison (SAME, or DIFFERS: the run
refuses). (b) THE RESERVATION IS WHOLE OR ABSENT. reserve() serialises the body before the exclusive create (a
serialisation error creates nothing), then writes, fsyncs and closes it and fsyncs its directory (the new entry
durable before the first game is scored) inside a guard; on any failure the file is
removed and the run refuses, nothing scored, the read not spent (an empty or partial file would read as a spent run to
every later invocation). If the removal fails too, the refusal names the file to inspect. #798 (addendum 222 item 2,
#797's shape): a create that fails for any reason refuses, nothing created; the removal is followed by an fsync of the
directory, and one that cannot be made durable is said (the refusal then ends "nothing scored", never "the read is not
spent").

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
from contextlib import contextmanager
from dataclasses import fields, replace
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
# v2 (addendum 219 item 4: "the term's value is INSIDE the fingerprint the architect's word binds to (the word names
# the term)"): the stream fingerprint's digest also carries the calibration term as the run will use it, {"form":
# "shrink"|"home_advantage", "value": float} (term_state's form and float value), or null while it is not declared (a
# fingerprint of the undeclared term, which no run accepts: the run refuses an undeclared term first). A term edited
# after the word changes the fingerprint, and the run refuses. The warm-up fingerprint stays rows only (v1): it is the
# fit's, and the fit has no term.
FINGERPRINT_FIELDS = ("match_id", "utc_date", "season", "stage", "home_id", "away_id", "home_score", "away_score")
FINGERPRINT_TAG = f"{EID} stream fingerprint v2"
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


# ------------------------------------------------------------------------------------ the frozen constants --
# The registry entry's "constants" block is the declaration's (215 item 2: "The constants are chosen BEFORE the run and
# written into the declaration"); candidate() builds the walk from nfl_backtest.NFLEloConfig()'s defaults. The run
# refuses unless the two are the same, key for key and value for value (exact float equality), so a default that
# drifts after the declaration cannot spend the one read of 2025 on a model the architect did not word (Codex P1 on
# #784). home_advantage compares with v1's base default: the home_advantage form replaces it in candidate() and is
# bound separately (term_state, the stream fingerprint). Checked before the stream is loaded and before reserve():
# nothing read, nothing reserved, nothing recorded. The refusal is the binding; the constants are not in the stream
# fingerprint. The key set is NFLEloConfig's dataclass fields, never a list kept here: a field added to the config
# later (one the walk would read) is a key the entry does not freeze, and the run refuses it (review on #784).


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def code_constants() -> dict:
    """nfl_backtest.NFLEloConfig()'s defaults, every dataclass field of it: the constants candidate() walks (before
    the term)."""
    c = nb.NFLEloConfig()
    return {f.name: getattr(c, f.name) for f in fields(c)}


def constants_state(e: dict | None) -> str | None:
    """None when the entry's frozen constants block equals code_constants() exactly; else why the run refuses."""
    blk = (e or {}).get("constants")
    if not isinstance(blk, dict):
        return "the registry entry has no constants block (the declaration's frozen constants)"
    code = code_constants()
    missing = [k for k in code if k not in blk]
    extra = sorted(k for k in blk if k not in code)
    if missing or extra:
        return ("the entry's constants block does not name exactly NFLEloConfig()'s fields, " + ", ".join(code)
                + (f" (missing {', '.join(missing)}: walked, not frozen)" if missing else "")
                + (f" (not walked: {', '.join(extra)})" if extra else ""))
    diff = [f"{k}: entry {blk[k]!r}, code {code[k]!r}" for k in code
            if not (_is_number(blk[k]) and _is_number(code[k])) or float(blk[k]) != float(code[k])]
    if diff:
        return ("the entry's frozen constants differ from nfl_backtest.NFLEloConfig()'s, the walk the run would build "
                "(" + "; ".join(diff) + ")")
    return None


def declared_constants(e: dict | None) -> dict:
    """The entry's frozen constants, refusing (GateRefused, exit 2) unless they are the walk's; see constants_state."""
    why = constants_state(e)
    if why:
        raise GateRefused(f"{EID}: {why}: 215 item 2, \"The constants are chosen BEFORE the run and written into the "
                          "declaration\"; the run walks the declared constants or nothing (Codex P1 on #784); nothing "
                          "read, nothing reserved, nothing scored")
    return dict(e["constants"])


def candidate(form: str, value: float):
    """(the walk's NFLEloConfig, the price map) for a declared term. v1's constants otherwise untouched (the run has
    checked them against the entry's frozen block first: declared_constants)."""
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


def _digest(tag: str, rows, **extra) -> tuple[str, int]:
    body = {"tag": tag, "fields": list(FINGERPRINT_FIELDS),
            "games": [[_fp_value(getattr(g, f)) for f in FINGERPRINT_FIELDS] for g in rows], **extra}
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(blob.encode("ascii")).hexdigest(), len(rows)


def bound_term(e: dict | None) -> tuple[str, float] | None:
    """The term the stream fingerprint binds: (form, value) exactly as the run uses it (term_state's), or None while
    the entry declares no valid term (the run refuses that term before the stream is loaded)."""
    form, value, _ = term_state(e)
    return (form, value) if form else None


def stream_fingerprint(warmup, scored, term: tuple[str, float] | None) -> tuple[str, int]:
    """THE STREAM FINGERPRINT v2, the one the architect's word binds to: sha256 over the stream exactly as the gate
    walks it (the warm-up rows then the scored rows, in walk order, each carrying FINGERPRINT_FIELDS) AND the
    calibration term (form, value) as the run uses it, or null when none is declared (addendum 219 item 4). JSON,
    sorted keys, no whitespace. (hex digest, number of games). `term` is required: no caller fingerprints the rows
    without saying which term it binds."""
    t = {"form": term[0], "value": float(term[1])} if term is not None else None
    return _digest(FINGERPRINT_TAG, list(warmup) + list(scored), calibration_term=t)


def warmup_fingerprint(warmup) -> tuple[str, int]:
    """sha256 over the 2024 warm-up rows alone: the stream the fit read (nfl-v2-fit-warmup prints it; the declaration
    records it as calibration_term.fit.warmup_fingerprint; --preflight compares and the run refuses a difference,
    addendum 219 item 4)."""
    return _digest(WARMUP_TAG, list(warmup))


def fit_binding(e: dict | None) -> str:
    """The fit's warm-up fingerprint as the entry records it (calibration_term.fit.warmup_fingerprint), refusing
    when the fit is null, not an object, or carries no non-empty warmup_fingerprint: addendum 219 item 4, "the run
    REFUSES when `fit` is null". Checked before the stream is loaded; nothing reserved, nothing recorded."""
    blk = (e or {}).get(TERM_KEY)
    fit = blk.get("fit") if isinstance(blk, dict) else None
    rec = fit.get("warmup_fingerprint") if isinstance(fit, dict) else None
    if not isinstance(rec, str) or not rec.strip():
        what = ("null" if fit is None else "not an object" if not isinstance(fit, dict)
                else "recorded without a warmup_fingerprint")
        raise GateRefused(f"{EID}: {TERM_KEY}.fit is {what}: addendum 219 item 4, \"the run REFUSES when `fit` is null "
                          "or when the fit's warm-up fingerprint differs from the run's warm-up fingerprint\"; the "
                          "declaration records the fit's receipt (fit.warmup_fingerprint, printed by nfl-v2-fit-warmup) "
                          "beside the term; nothing reserved, nothing scored")
    return rec.strip()


def _fit_state(rec: str | None, wfp: str) -> str:
    """--preflight's reading of the fit binding (the run's two refusals of addendum 219 item 4, said in advance)."""
    if not rec:
        return "fit NOT RECORDED (calibration_term.fit null or without warmup_fingerprint): the run refuses"
    if rec != wfp:
        return "CHANGED since the fit: the run refuses (the architect reads this line)"
    return "SAME: the fit is bound to these 2024 rows"


# ------------------------------------------------------------------------------------- the database (--db) --

SIDECARS = ("-wal", "-shm", "-journal")


def check_db(db):
    """--db PATH (addendum 219 item 6): mlb_pitchers_gate.check_db itself, the standing --db fence (an existing file,
    never created; never under any data/ by resolved path or by identity; never the app's configured database); then
    refused when a -wal, -shm or -journal file sits beside it (immutable=1 ignores them, so committed pages still in a
    WAL would be missed without a word; a fresh .backup copy has none); then a probe of its matches table through the
    same mode=ro&immutable=1 URI. Refusals are this gate's."""
    from src.walters import mlb_pitchers_gate as mp
    try:
        path = mp.check_db(db)
        for s in SIDECARS:
            if path.with_name(path.name + s).exists():
                raise mp.GateRefused(f"--db {db} has a {s} sidecar ({path.name + s}): not a fresh .backup copy; "
                                     "immutable=1 would ignore it and read a stale stream; take a fresh .backup copy")
        mp.open_ro(path).close()
    except mp.GateRefused as e:
        raise GateRefused(f"{e}; nothing read, nothing reserved")
    return path


@contextmanager
def db_session(path):
    """None when there is no --db (the app's DATABASE_URL, as before); else mlb_pitchers_gate.readonly_session on the
    copy: a SQLAlchemy session through a mode=ro&immutable=1 URI (COPY_URI_QUERY), never committed, no sidecar."""
    if path is None:
        yield None
        return
    from src.walters import mlb_pitchers_gate as mp
    with mp.readonly_session(path) as s:
        yield s


def db_label(path) -> str:
    from src.walters import mlb_pitchers_gate as mp
    return (f"db --db {path} (a .backup copy, opened {mp.COPY_URI_QUERY.lstrip('?')})" if path is not None
            else "db DATABASE_URL (the app's configured database)")


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


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view):]
    os.fsync(fd)


def _fsync_dir(p: str) -> None:
    """fsync the reservation's directory, so the new file's directory entry is durable before the first game is
    scored (review on #784: without it a crash after the verdict could lose the entry, and the read could be taken
    twice). POSIX only: Windows cannot open a directory for fsync, and NTFS journals the entry itself."""
    if os.name == "nt":
        return
    dfd = os.open(os.path.dirname(os.path.abspath(p)), os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def reserve(meta: dict, no_fetch: bool = False, echo=None) -> str:
    """ncaa-gate's reserve(): the #329 cross-ref guard first, then the exclusive create of the reservation, before the
    first game is scored.

    A reservation is whole or absent (Codex P1 on #784): the body is serialised BEFORE the exclusive create (a
    serialisation error creates nothing), then written, fsynced and closed, and its directory fsynced, inside a guard;
    on any failure there the fd is closed and the file removed, and the run refuses (exit 2: nothing scored, the read is not spent). An empty or
    partial file would otherwise read as a spent run to every later invocation. If the removal itself fails the
    refusal says so and names the file to inspect (it may read as a spent run until it is). A create that fails for
    any reason refuses the same way, nothing created; a removal (ours, or a file already gone) is followed by an fsync
    of the directory, and a removal that cannot be made durable is said (#798, addendum 222 item 2: #797's shape)."""
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
        data = (json.dumps({"id": EID, "started_at": _iso(utc_now_naive()), "guard": receipt, **meta})
                + "\n").encode("utf-8")
    except Exception as err:
        raise GateRefused(f"{EID}: the reservation could not be serialised ({type(err).__name__}: {err}); nothing "
                          "written, nothing scored, the read is not spent") from err
    try:
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise GateRefused(_reserved_why(p))
    except OSError as err:                                     # ENOSPC, EACCES, EIO...: nothing was created (#798)
        raise GateRefused(f"{EID}: the reservation {os.path.relpath(p)} could not be created "
                          f"({type(err).__name__}: {err}); nothing written, nothing scored, the read is not spent"
                          ) from err
    fd_open = True
    try:
        _write_all(fd, data)
        fd_open = False
        os.close(fd)
        _fsync_dir(p)                                          # the directory entry is durable too (review on #784)
    except BaseException as err:
        if fd_open:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            os.unlink(p)
            removed = "removed"
        except FileNotFoundError:
            removed = "already gone"
        except OSError as uerr:
            raise GateRefused(f"{EID}: the reservation {os.path.relpath(p)} could not be written "
                              f"({type(err).__name__}: {err}) and could not be removed ({type(uerr).__name__}: "
                              f"{uerr}): INSPECT THE FILE before anything else; it may be empty or partial and reads as a spent run while it "
                              "stands. Nothing was scored") from err
        # the removal is durable too, ours or another process's (#798; addendum 222 item 2, #797's shape)
        try:
            _fsync_dir(p)
        except OSError as derr:
            removed = (f"{removed}, but the removal could not be made durable ({type(derr).__name__}: {derr}): "
                       f"if the machine restarts before its directory is flushed the file may return, so "
                       f"check that {os.path.relpath(p)} is absent before the run")
        if not isinstance(err, Exception):
            raise
        tail = ("nothing scored" if "could not be made durable" in removed else
                "nothing scored, the read is not spent")
        raise GateRefused(f"{EID}: the reservation {os.path.relpath(p)} could not be written ({type(err).__name__}: "
                          f"{err}); {removed}: {tail}") from err
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
    stage, the 2024 baseline, the declared term, the fit binding, the fingerprints (the stream fingerprint binding the
    declared term, or the undeclared one). No model is built; no 2025 outcome is computed."""
    warmup, scored = nb.split(rows)
    fp, fp_n = stream_fingerprint(warmup, scored, bound_term(entry))
    wfp, wn = warmup_fingerprint(warmup)
    form, value, why = term_state(entry)
    cwhy = constants_state(entry)
    try:
        rec = fit_binding(entry)
    except GateRefused:
        rec = None
    return {"warmup_n": len(warmup), "scored_n": len(scored),
            "warmup_by_stage": _by(warmup, lambda r: r.stage or "(none)"),
            "scored_by_stage": _by(scored, lambda r: r.stage or "(none)"),
            "not_walked_by_season": _by([r for r in rows if r.season not in (nb.WARMUP_SEASON, nb.SCORED_SEASON)],
                                        lambda r: r.season),
            "preseason_excluded": preseason or {},
            "baseline_home_rate": nb.baseline_rate(warmup) if warmup else None,
            "form": form, "value": value, "term_why": why,
            "constants": (entry or {}).get("constants"), "code_constants": code_constants(), "constants_why": cwhy,
            "fit_warmup_fingerprint": rec,
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
    L.append("  constants: the entry's frozen " + (repr(pf["constants"]) if pf["constants"] is not None else "(none)")
             + f" · NFLEloConfig()'s {pf['code_constants']!r} · "
             + ("SAME: the run walks the declared constants" if not pf["constants_why"] else
                f"DIFFERS — the run refuses: {pf['constants_why']}") + " (Codex P1 on #784)")
    rec = pf["fit_warmup_fingerprint"]
    L.append(f"  warm-up fingerprint {pf['warmup_fingerprint']} ({pf['warmup_fingerprint_n']} games; nfl-v2-fit-warmup "
             f"prints it) · the fit's, as the entry records it: {rec or '—'} · "
             f"{_fit_state(rec, pf['warmup_fingerprint'])} (addendum 219 item 4)")
    if not pf["warmup_n"] or not pf["scored_n"]:
        L.append("  the run refuses: the protocol needs both seasons (insufficient seasons for protocol)")
    L.append("PREFLIGHT only: nothing scored, nothing reserved, nothing recorded.")
    term = (f"and the calibration term as declared ({describe(pf['form'], pf['value'])})" if pf["form"] else
            "and the calibration term NOT DECLARED: this fingerprint binds the undeclared term and the run refuses; "
            "the declaration's term changes it")
    L.append(f"STREAM FINGERPRINT {pf['fingerprint']} ({pf['fingerprint_n']} games: the {nb.WARMUP_SEASON} and "
             f"{nb.SCORED_SEASON} stream as the gate walks it, {term}; v2, addendum 219 item 4; the run takes it as "
             "--stream-fingerprint)")
    return L


def preseason_counts(session=None) -> dict:
    """The preseason rows the stream excludes, per season (counts only; nothing else read). `session`: the --db
    copy's read-only session (nfl_backtest.read_session), else the app's."""
    from sqlalchemy import select

    from src.db.schema import Match, MatchStatus

    with nb.read_session(session) as s:
        rows = s.execute(nb.nfl_scoped(select(Match.season, Match.stage)).where(
            Match.status == MatchStatus.FINISHED, Match.home_score.is_not(None),
            Match.away_score.is_not(None))).all()
        if session is None:
            s.rollback()
    return _by([r for r in rows if nb.is_preseason(r[1])], lambda r: r[0])


def _scope(scope: list[str], path) -> str | None:
    return f"{scope[0]} · {db_label(path)}" if scope else None


def preflight_read(entry: dict | None, db=None) -> list[str]:
    """--preflight's one read: the stream (nfl_backtest.load_stream), the preseason count, from the --db copy when
    given (check_db; addendum 219 item 6: "the preflight's fingerprint on that copy is the run's"); then
    preflight()."""
    path = check_db(db) if db is not None else None
    scope: list[str] = []
    with db_session(path) as s:
        rows = nb.load_stream(COMMAND, scope.append, session=s)
        pre = preseason_counts(session=s)
    return preflight_lines(preflight(rows, entry, pre), _scope(scope, path))


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


def run(word: str | None, fingerprint: str | None, no_fetch: bool = False, echo=None, db=None) -> dict:
    """The ONE run. Checked BEFORE the reservation, each refusal exit 2 with nothing written and nothing recorded:
    declared and unrun and unreserved; the word (non-empty, verbatim); the fingerprint; the calibration term declared
    (exactly one form, a valid value); the fit recorded (calibration_term.fit.warmup_fingerprint, addendum 219 item
    4); the entry's frozen constants the walk's (declared_constants: the block present, exactly NFLEloConfig()'s fields,
    each value equal to its default; Codex P1 on #784); the --db copy given and admissible (check_db; addendum 219
    item 6: the ONE run reads the .backup copy, never DATABASE_URL). Then the stream is loaded
    (nfl_backtest.load_stream, the read --preflight makes, from the same database; nothing scored) and the run refuses
    unless both seasons hold games, the loaded 2024 rows' warm-up fingerprint is the fit's (219 item 4: a stale fit
    refuses), and the stream fingerprint over those rows AND the declared term equals `fingerprint` (219 item 4: the
    word names the term). Then the reservation (after the cross-ref guard), carrying the word, the fingerprints, the
    term and the database read; then the frozen protocol's walk over that same loaded stream. The caller records the
    run (record())."""
    e = declared_unrun()
    if not word or not str(word).strip():
        raise GateRefused("the run starts only on the architect's word (215 item 3): pass --architect-word with it "
                          "verbatim")
    if not fingerprint or not str(fingerprint).strip():
        raise GateRefused("the word refers to one stream (ncaa-gate's addendum 17 item 1): pass --stream-fingerprint "
                          f"with the last line of {COMMAND} --preflight")
    form, value = declared_term(e)
    fit_wfp = fit_binding(e)                                   # 219 item 4: a null fit refuses here, before the load
    declared_constants(e)                                      # the entry's frozen constants are the walk's, or refuse
    if db is None or not str(db).strip():                      # 219 item 6: the run reads the copy, never the live DB
        raise GateRefused("the ONE run reads a fresh .backup copy outside data/ (addendum 219 item 6, the mlb-pitchers "
                          "pattern: the gate never reads the live database): pass --db COPY, the copy --preflight "
                          "read; nothing read, nothing reserved")
    path = check_db(db)
    scope: list[str] = []
    with db_session(path) as s:
        rows = nb.load_stream(COMMAND, scope.append, session=s)   # the stream about to be walked; nothing scored
    warmup, scored = nb.split(rows)
    if not warmup or not scored:
        raise GateRefused(f"the stream holds {len(warmup)} warm-up ({nb.WARMUP_SEASON}) and {len(scored)} scored "
                          f"({nb.SCORED_SEASON}) games: insufficient seasons for protocol; nothing reserved or "
                          "recorded, the read is not spent")
    wfp, wn = warmup_fingerprint(warmup)
    if wfp != fit_wfp:
        raise GateRefused(f"the fit is stale: {TERM_KEY}.fit.warmup_fingerprint is {fit_wfp}, the {nb.WARMUP_SEASON} "
                          f"rows about to be walked are {wfp} ({wn} games): addendum 219 item 4, \"the run REFUSES ... "
                          "when the fit's warm-up fingerprint differs from the run's warm-up fingerprint\"; nothing "
                          "reserved, nothing scored — the architect rules the term on the rows the run reads")
    fp, fp_n = stream_fingerprint(warmup, scored, (form, value))
    if fp != str(fingerprint).strip():
        raise GateRefused(f"the stream and the declared term no longer match the fingerprint given: given "
                          f"{str(fingerprint).strip()}, the stream about to be walked with the term declared now "
                          f"({describe(form, value)}) is {fp} ({fp_n} games; v2 binds the term, addendum 219 item 4); "
                          f"nothing reserved, nothing scored — re-run {COMMAND} --preflight and take the architect's "
                          "word on it")
    term = {"form": form, "value": value}
    meta = {"architect_word": word, "stream_fingerprint": fp, "stream_games": fp_n, "warmup_n": len(warmup),
            "scored_n": len(scored), "calibration_term": term, "warmup_fingerprint": wfp,
            "fit_warmup_fingerprint": fit_wfp, "db": str(path)}
    reserve(meta, no_fetch=no_fetch, echo=echo)
    # from here on, the one run is spent
    cfg, price = candidate(form, value)
    lines: list[str] = []
    w = nb.walk_protocol(warmup, scored, cfg, price, lines.append)
    w.update({"verdict": verdict_text(w["pass"], w), "protocol_lines": lines, "scope": _scope(scope, path),
              "stream_fingerprint": fp, "stream_fingerprint_tag": FINGERPRINT_TAG, "stream_games": fp_n,
              "warmup_n": len(warmup), "scored_n": len(scored), "calibration_term": term,
              "warmup_fingerprint": wfp, "fit_warmup_fingerprint": fit_wfp,
              "db": str(path),
              "constants": {k: getattr(cfg, k) for k in code_constants()}})
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
             f"scored {r['scored_n']}; v2, the rows and the declared term), checked before the reservation and "
             "recorded beside the word")
    L.append(f"  warm-up fingerprint {r['warmup_fingerprint']}: the fit's ({r['fit_warmup_fingerprint']}), checked "
             "before the reservation (addendum 219 item 4)")
    L.append(f"  candidate: nfl_elo_v1's constants {r['constants']} · {describe(**r['calibration_term'])}")
    L += [f"  {x}" for x in r["protocol_lines"]]
    for b in r["bands"]:
        if not b["gated"]:
            L.append(f"    band {b['band'] * 10}-{b['band'] * 10 + 10}%: n={b['n']} < {nb.BAND_MIN_N}: reported, not "
                     f"scored (stated {b['stated']:.3f} realized {b['realized']:.3f})")
    L.append(f"  VERDICT (computed; the architect rules): {r['verdict']}")
    return L
