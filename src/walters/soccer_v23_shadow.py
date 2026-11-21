"""
soccer-v23's PASS SHADOW on the host's PL pages, built DORMANT (GATE-CLASS: an export contract). ARCHITECT 2026-11-19,
addendum 434 item 2(b)(ii), as ruled by ARCHITECT 2026-11-21 08:04 ET, addendum 436 items 6(e) and 7 (DEV 2's plan of
2026-11-19 on #656, "BUILD IT AS PLANNED. Points 1 to 5 and the exclusions of point 6 are accepted as written"). The
precedents, both on main: nfl_rehearsal (the state read, on only for host + a recorded PASS + a status) and
pl_availability (a second arm on v22's own Prediction row, exported host-only under its own key prefix, fenced).

As built:

- THE STATE READ, NEVER WRITTEN HERE (plan point 1). The arm is ON only when ALL hold:
    (a) the machine is the host (desk_policy.not_host_reason() is None; a failed read is never the host);
    (b) the registry entry `soccer-v23` (registry.LEDGER read at call time, in the checkout: 436 item 6(e), "the
        verdict is read from the registry in the checkout and nowhere else") records verdict.verdict == "PASS" with a
        verdict.at stamp, and its status is "confirming" (registry.record_verdict's record, never the run's computed
        text; the confirmation window is open);
    (c) the entry's frozen_constants are the code's, its gate is BAR_TEXT (bar_state: a PASS only at the bar the
        checkout holds, 440 item 4(a)) and its declaration slots read (soccer_v23.constants_state / slots_state, the
        run's own checks), and its run record carries `thin_excluded` and `v22_params_sha256` (soccer_v23.record);
    (d) the store's production soccer_elo_poisson is exactly one row, "v22", with poisson params
        (soccer_v23.production_params) whose soccer_v23.params_sha256 equals the run record's (440 item 4(b)), and
        the pass pricing v22 is v22's.
  Anything else is DORMANT with its reason (law 4): no entry (today), declared and unrun, REJECT, INVALID, FAIL, a PASS
  with any other status, an unreadable registry, constants or slots that do not read, another production version, or
  off the host. Dormant writes NOTHING: no stored arm, no key on any page, no file (436 item 7(a): the pages, the stored
  rows, the Desk blocks and desk_meta byte-identical). The predict and export receipts print one line, RECEIPT.
- THE ARM (plan point 2), at the soccer predict pass (training._generate_predictions_soccer), beside pl-availability's:
  a PL 2026/27 fixture kicking off strictly after verdict.at and within HORIZON_HOURS of the run's clock is priced by
  soccer_v23.predict_live_slate (the design's only live entry point, 216 item 3 / 251 item 2), one call per kickoff
  instant (by_instant), on params_json = canon_params(v22's stored poisson, availability False, slots["scope"],
  thin_excluded = the run record's) under slots["visibility"], with the availability record NoRecord(AVAILABILITY_OFF)
  (263 item 6: OFF in the shadow whatever the slot reads). It reads match rows only: no market field, no ModelVersion
  context, no injuries (the live path's own contract). Stored at FULL precision on v22's own Prediction row under
  factor_breakdown[FB_KEY]. A failure stores {version, error} for that instant's fixtures and v22's row is written as
  always. HORIZON_HOURS bounds the work so v22's closing page is never late (the closing run's predict prices the
  whole season; each game's last predict before its kickoff is its own closing run, well inside the horizon).
- THE PAGES (plan point 3): on the host while the arm is ON, every PL 2026/27 row whose kickoff is after verdict.at
  carries ROW_KEYS (the `v23_*` prefix, 263 item 6: never candidate_* or rehearsal_*): the version, the probabilities
  at four places, the availability line, the label and a reason (null, or why the stored arm is missing). FB_KEY is
  stripped from every exported factor_breakdown, so the arm reaches a page only through these keys. The Desk reads
  none of them (desk_policy.normalize reads named fields only).
- THE FENCE (plan point 4): while the arm is ON, a FINISHED covered game's row carries no figures (v23_reason
  "withheld"), and nothing here reads the arm on the window until the read.
- Not here (plan point 6): the window reader, the read at the 60th, window_opens_at, any registry write.
"""
from __future__ import annotations

import hashlib
import math
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

EID = "soccer-v23"
COMPETITION = "PL"
SEASON = "2026/27"
BASE_VERSION = "v22"
STATUS = "confirming"                   # registry.record_verdict: a PASS opens the confirmation window
FB_KEY = "soccer_v23_shadow"            # the arm's key in v22's Prediction.factor_breakdown (never exported as is)
PREFIX = "v23_"                         # 263 item 6: the shadow's own key prefix, host-only, counted by the compare
ROW_KEYS = ("v23_version", "v23_probabilities", "v23_availability", "v23_label", "v23_reason")
LABEL = "shadow — not a call"
HORIZON_HOURS = 72
AVAILABILITY_OFF = ("off in the shadow until pl-availability-v1's verdict, whatever the declaration slot reads "
                    "(ARCHITECT 2026-11-05, addendum 263 item 6)")
WITHHELD = ("withheld: a finished game of soccer-v23's shadow window; no figure of the arm is read until the window's "
            "read (the fence, plan point 4)")
RULING = "ARCHITECT 2026-11-21 08:04 ET, addendum 436 item 7"
RECEIPT = "soccer-v23 shadow: {state}"
PRODUCTION_UNREAD = "the store's production soccer model was not read"
PARAMS_KEY = "v22_params_sha256"         # 440 item 4(b): the run record's field (soccer_v23.record / params_sha256)
SESSION_KEY = "soccer_v23_shadow_gate"   # the page gate, read once per session (Session.info)


@dataclass(frozen=True)
class Gate:
    """The predicate's reading. `on`: (a)-(d) of the module docstring."""
    on: bool
    why: str | None
    verdict_at: str | None = None
    verdict_instant: datetime | None = None
    params_json: str | None = None
    visibility: str | None = None
    params_sha: str | None = None
    extra: dict = field(default_factory=dict, compare=False)

    def covered(self, competition, season, kickoff) -> bool:
        """A row of the shadow's territory: PL 2026/27, kickoff strictly after the verdict's stamp."""
        k = _naive(kickoff)
        return bool(self.on and (competition or "").strip().upper() == COMPETITION and str(season) == SEASON
                    and k is not None and k > self.verdict_instant)

    def priced(self, competition, season, kickoff, now: datetime) -> bool:
        """Covered and inside the horizon of the run's clock: the fixtures the predict pass prices. No lower bound, on
        purpose: the pass rewrites every SCHEDULED row, so a covered game past its kickoff and still SCHEDULED (a
        status not yet synced; law 4 keeps an unmapped one SCHEDULED) is priced again (its snapshot is bounded at its
        kickoff, so it reads no result) and keeps its arm, where skipping it would drop the stored arm."""
        k = _naive(kickoff)
        return self.covered(competition, season, kickoff) and k <= _naive(now) + timedelta(hours=HORIZON_HOURS)

    def receipt(self, stats: dict | None = None) -> str:
        if not self.on:
            return RECEIPT.format(state=f"dormant ({self.why})")
        s = "" if stats is None else (f" · priced {stats['priced']} at {stats['instants']} kickoff instants · failed "
                                      f"{stats['failed']} · covered outside the {HORIZON_HOURS}-hour horizon "
                                      f"{stats['outside']} · {stats['seconds']:.1f}s")
        return RECEIPT.format(state=f"ON ({EID} PASS {self.verdict_at}; {AVAILABILITY_OFF}){s}")


def _naive(dt) -> datetime | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _off(why: str) -> Gate:
    return Gate(False, why)


def _stamp(at) -> datetime | None:
    """verdict.at exactly as registry.record_verdict writes it (registry._now: "%Y-%m-%dT%H:%M:%SZ"), else None: a
    hand-edited stamp in any other form is never read leniently (record_confirmation compares the raw strings)."""
    if not isinstance(at, str):
        return None
    try:
        return datetime.strptime(at, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def state(entry: dict | None, host_why: str | None = None, production: tuple | None = None) -> Gate:
    """The predicate on one registry entry (pure: the tests call it on hand-built entries). `host_why`:
    desk_policy.not_host_reason()'s answer (None on the host). `production`: soccer_v23.production_params' answer
    (version, poisson params), or None when it was not read (the predicate then refuses: (d) unread is dormant)."""
    from src.walters import soccer_v23 as sv
    if host_why is not None:
        return _off(f"{EID}'s shadow runs on the host only: {host_why}")
    if not isinstance(entry, dict) or entry.get("id") != EID:
        return _off(f"no {EID} entry in the registry")
    v = entry.get("verdict")
    verdict = v.get("verdict") if isinstance(v, dict) else None
    if verdict != "PASS":
        return _off(f"{EID}'s verdict reads {verdict or 'null'}, not PASS: the shadow exports nothing unless the "
                    f"registry records a PASS")
    at = v.get("at")
    t = _stamp(at)
    if t is None:
        return _off(f"{EID}'s PASS carries no readable verdict stamp (verdict.at {at!r})")
    if entry.get("status") != STATUS:
        return _off(f"{EID}'s status reads {entry.get('status')!r}, not {STATUS!r}: the confirmation window is not open")
    why = sv.constants_state(entry)
    if why:
        return _off(f"{EID}: {why}")
    why = sv.bar_state(entry)                           # 440 item 4(a): a PASS only at the bar the checkout holds
    if why:
        return _off(f"{EID}: {why}: a PASS is shown only as a PASS at the bar the checkout holds")
    slots, why = sv.slots_state(entry)
    if why:
        return _off(f"{EID}: {why}")
    run = entry.get("run")
    res = run.get("result") if isinstance(run, dict) else None
    thin = res.get("thin_excluded") if isinstance(res, dict) else None
    if not isinstance(thin, list) or not all(isinstance(x, list) and len(x) == 2 for x in thin):
        return _off(f"{EID}'s run record carries no thin_excluded set (soccer_v23.record): the shadow prices on the run's "
                    "own exclusion set or not at all")
    run_sha = res.get(PARAMS_KEY)
    if not (isinstance(run_sha, str) and len(run_sha) == 64 and all(c in "0123456789abcdef" for c in run_sha)):
        return _off(f"{EID}'s run record carries no {PARAMS_KEY} (440 item 4(b)): the shadow prices only on the v22 "
                    "params the run read")
    if production is None:
        return _off(PRODUCTION_UNREAD)
    version, v22p = production
    if version != BASE_VERSION or not v22p:
        return _off(f"the store's soccer production version is {version!r}, not {BASE_VERSION!r} (or carries no "
                    "poisson params): the shadow is read beside live v22")
    here = sv.params_sha256(v22p)
    if here != run_sha:
        return _off(f"the store's v22 poisson params (sha256 {here[:16]}…) are not the params the run read "
                    f"({run_sha[:16]}…; 440 item 4(b)): the shadow prices only on the v22 the run walked")
    try:
        pj = sv.canon_params(v22p, False, slots["scope"], thin_excluded=[tuple(x) for x in thin])
    except (TypeError, ValueError) as err:
        return _off(f"the shadow's params do not build: {err}")
    return Gate(True, None, at.strip(), t, pj, slots["visibility"], hashlib.sha256(pj.encode("ascii")).hexdigest())


def host_reason() -> str | None:
    """desk_policy.not_host_reason(); a failed read is never the host (law 4)."""
    try:
        from src.walters.desk_policy import not_host_reason
        return not_host_reason()
    except Exception as err:                            # noqa: BLE001
        return f"the machine role could not be read ({type(err).__name__})"


def read_gate(session, path: str | None = None) -> Gate:
    """state() on the registry's entry now (registry.LEDGER at call time; `path` for a tmp registry), on this machine's
    role and the session's production row. Never raises: any failure of the read is dormant with its reason, never an
    exception on a predict or export run."""
    try:
        why = host_reason()
        if why is not None:
            return state(None, why)
        from src.walters import registry as reg
        p = path or reg.LEDGER
        try:
            entries = reg.load(p)
        except (OSError, ValueError) as err:
            return _off(f"the registry {p} cannot be read ({type(err).__name__})")
        if not isinstance(entries, list):
            return _off(f"the registry {p} is not a list of entries")
        e = next((x for x in entries if isinstance(x, dict) and x.get("id") == EID), None)
        pre = state(e)
        if pre.why != PRODUCTION_UNREAD:
            return pre                                  # dormant before any database read
        from src.walters import soccer_v23 as sv
        try:
            prod = sv.production_params(session)
        except sv.GateRefused as err:
            return _off(f"the store's production soccer model is ambiguous: {err}")
        return state(e, None, prod)
    except Exception as err:                            # noqa: BLE001
        return _off(f"the shadow's gate could not be read ({type(err).__name__}: {err})"[:300])


def for_pass(gate: Gate, model_version) -> Gate:
    """(d)'s second half: the pass the arm rides is v22's own (a predict run naming another --version is dormant)."""
    if gate.on and model_version != BASE_VERSION:
        return _off(f"this predict pass prices {model_version!r}, not {BASE_VERSION!r}: the shadow rides v22's own rows")
    return gate


# The pass's receipt lines, read and cleared by the predict and export commands; bounded, so a long-lived process
# (the web app's per-match refresh) that never reads them holds at most the last few.
LAST_RECEIPT: deque = deque(maxlen=8)


def note(gate: Gate, stats: dict | None = None) -> None:
    LAST_RECEIPT.append(gate.receipt(stats))


def take_receipts() -> list[str]:
    out = list(LAST_RECEIPT)
    LAST_RECEIPT.clear()
    return out


def page_gate(session, path: str | None = None) -> Gate:
    """read_gate once per session (the export's rows share one read)."""
    info = getattr(session, "info", None)
    if isinstance(info, dict) and isinstance(info.get(SESSION_KEY), Gate):
        return info[SESSION_KEY]
    g = read_gate(session, path)
    note(g)
    if isinstance(info, dict):
        info[SESSION_KEY] = g
    return g


# ------------------------------------------------------------------------------------------ the stored arm --

def _kick(dt) -> str | None:
    k = _naive(dt)
    return None if k is None else k.strftime("%Y-%m-%dT%H:%M:%SZ")


def arm_block(gate: Gate, r: dict, kickoff) -> dict:
    """The arm as v22's Prediction row stores it under FB_KEY: FULL precision, predict_live_slate's own floats, and the
    kickoff it was priced at (as_of: a game re-dated after its last predict is never shown under its old instant)."""
    return {"version": EID, "base_version": BASE_VERSION, "verdict_at": gate.verdict_at, "params_sha": gate.params_sha,
            "as_of": _kick(kickoff), "p_home": float(r["p_home"]), "p_draw": float(r["p_draw"]),
            "p_away": float(r["p_away"]), "availability": "off"}


def failed_block(gate: Gate, err: BaseException) -> dict:
    """The marker stored when the arm could not price a fixture (v22's row is written as always)."""
    return {"version": EID, "base_version": BASE_VERSION, "verdict_at": gate.verdict_at,
            "params_sha": gate.params_sha, "error": f"{type(err).__name__}: {err}"[:200]}


def price_arms(session, gate: Gate, matches, now: datetime, competition_code: str, log=None) -> dict:
    """{match id: arm or failed block} for the matches the gate prices (Gate.priced), one predict_live_slate call per
    kickoff instant; {} when the gate is off. A failure of one instant stores the failed block for its fixtures only."""
    if not gate.on:
        return {}
    todo = [m for m in matches if gate.priced(competition_code, m.season, m.utc_date, now)]
    try:
        from src.walters import soccer_v23 as sv
        fx = [sv.Fixture(int(m.id), COMPETITION, str(m.season), _naive(m.utc_date), int(m.home_team_id),
                         int(m.away_team_id)) for m in todo]
        groups = sv.by_instant(fx)
        rec = sv.NoRecord(AVAILABILITY_OFF)
    except Exception as err:                            # noqa: BLE001 — the pass goes on; each row says why
        return {int(m.id): failed_block(gate, err) for m in todo}
    out: dict = {}
    for _t, group in groups:
        try:
            kicks = {f.id: f.utc_date for f in group}
            for r in sv.predict_live_slate(session, group, EID, gate.params_json, gate.visibility, record=rec):
                out[int(r["match_id"])] = arm_block(gate, r, kicks[int(r["match_id"])])
        except Exception as err:                        # noqa: BLE001 — named, never silent: stored as the cause
            if log is not None:
                log.warning("%s: no shadow arm for matches %s (%s: %s); v22's rows are written as always", EID,
                            [f.id for f in group], type(err).__name__, err)
            for f in group:
                out[f.id] = failed_block(gate, err)
    return out


def stats(gate: Gate, matches, arms: dict, now: datetime, competition_code: str, seconds: float) -> dict | None:
    """The ON receipt's counts (law 2): fixtures priced and failed, their kickoff instants, the covered ones outside the
    horizon, the seconds the arm took. None when the gate is off."""
    if not gate.on:
        return None
    covered = [m for m in matches if gate.covered(competition_code, m.season, m.utc_date)]
    failed = sum(1 for a in arms.values() if "error" in a)
    return {"priced": len(arms) - failed, "failed": failed, "seconds": seconds,
            "instants": len({_naive(m.utc_date) for m in covered if "error" not in arms.get(int(m.id), {"error": 1})}),
            "outside": sum(1 for m in covered if not gate.priced(competition_code, m.season, m.utc_date, now))}


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def stored(pred) -> dict | None:
    fb = getattr(pred, "factor_breakdown", None) if pred is not None else None
    a = fb.get(FB_KEY) if isinstance(fb, dict) else None
    return a if isinstance(a, dict) and a.get("version") == EID else None


def arm_of(pred) -> dict | None:
    """The stored arm when whole (three finite probabilities), else None (never repaired)."""
    a = stored(pred)
    return a if a is not None and all(_num(a.get(k)) for k in ("p_home", "p_draw", "p_away")) else None


def strip(fb) -> dict:
    """factor_breakdown as exported: the arm's key removed (a new dict; the stored one is never mutated)."""
    return {k: v for k, v in (fb or {}).items() if k != FB_KEY}


def _missing_reason(pred) -> str:
    a = stored(pred)
    if a is not None and isinstance(a.get("error"), str):
        return f"the shadow arm failed for this game ({a['error']}); v22's row was written as always"
    if pred is None:
        return "no v22 prediction is stored for this game"
    return (f"the stored prediction carries no shadow arm (written before the shadow read on, or outside its "
            f"{HORIZON_HOURS}-hour horizon at the last predict)")


# ----------------------------------------------------------------------------------------------- the pages --

def _status(m) -> str | None:
    st = getattr(m, "status", None)
    return getattr(st, "value", st)


def export_fields(gate: Gate, pred, competition, m) -> dict | None:
    """The PL row's ROW_KEYS, or None (absent) when the gate is off or the row is outside the shadow's territory."""
    if m is None or not gate.covered(competition, getattr(m, "season", None), getattr(m, "utc_date", None)):
        return None
    out = {"v23_version": EID, "v23_probabilities": None, "v23_availability": AVAILABILITY_OFF, "v23_label": LABEL,
           "v23_reason": None}
    if _status(m) == "finished":
        out["v23_reason"] = WITHHELD
        return out
    a = arm_of(pred)
    if a is None:
        out["v23_reason"] = _missing_reason(pred)
    elif a.get("as_of") != _kick(getattr(m, "utc_date", None)):
        out["v23_reason"] = (f"the stored arm was priced for a kickoff of {a.get('as_of')}; the game now kicks off at "
                             f"{_kick(getattr(m, 'utc_date', None))}: re-priced at the next predict")
    elif a.get("verdict_at") != gate.verdict_at or a.get("params_sha") != gate.params_sha:
        out["v23_reason"] = (f"the stored arm was priced under another verdict stamp or params "
                             f"({a.get('verdict_at')!r}, {a.get('params_sha')!r}); the registry reads "
                             f"{gate.verdict_at!r}, {gate.params_sha!r}")
    else:
        out["v23_probabilities"] = {"home_win": round(a["p_home"], 4), "draw": round(a["p_draw"], 4),
                                    "away_win": round(a["p_away"], 4)}
    return out


def env_now() -> datetime:
    """The run's clock (naive UTC)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

