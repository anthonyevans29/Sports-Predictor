"""
nfl-elo-v2's REHEARSAL ARM (GATE-CLASS: an export contract). ARCHITECT 2026-11-03 09:00 ET, addendum 230 item 1(a), as
ruled by ARCHITECT 2026-11-04 09:55 ET, addendum 247 items 2-3 (both verbatim in docs/specs/nfl-rehearsal-arm.md and
below as RULING_230_TEXT / RULING_247_TEXT; tests/test_nfl_rehearsal_arm.py pins each against the spec and the PR's
fragments). Where 230's map and 247 differ, 247 wins.

As built (docs/specs/nfl-rehearsal-arm.md is the contract):

- THE STATE READ, NEVER WRITTEN HERE (247 item 2(1)): `read_gate` / `state` read the registry entry `nfl-elo-v2`
  (registry.LEDGER at call time) and the arm is ON only when ALL hold:
    (a) the machine is the host (desk_policy.not_host_reason() is None: pl-availability-v1's host-only gate, 247 item
        2(2) "host-only");
    (b) the ARCHITECT's verdict reads PASS: entry["verdict"]["verdict"] == "PASS" (registry.record_verdict's record,
        never the gate's computed run.result.verdict text), with a non-empty verdict.at (the verdict stamp);
    (c) entry["status"] == "rehearsal";
    (d) entry["rehearsal_window"] is exactly {"opens_at": "<UTC instant>Z", "closes_at": "<UTC instant>Z"}: a dict with
        exactly those two keys, each a string ending in "Z" that pl_availability.parse_instant reads, opens_at strictly
        before closes_at. The instants are READ from the entry, never defaulted here: 247's ruled ones are
        2026-11-12T00:00:00Z and 2026-11-24T06:00:00Z, and they appear in the tests and the spec only;
    (e) the declared term and frozen constants price: nfl_v2_gate.declared_term (exactly one form, a valid value) and
        nfl_v2_gate.declared_constants (the entry's constants are NFLEloConfig()'s).
  Anything else is DORMANT with its reason (law 4: an absent entry, an unreadable registry, a null / FAIL / REJECT
  verdict, PASS with any other status, an absent or malformed window). On FAIL nothing is written to the registry, so
  every line here stays dormant for the season. The verdict-record PR after Friday's run writes (b)-(d) on PASS only
  (247 item 2(1)); this module writes no registry field.
- PER GAME (247 item 2(3)): the GAME'S KICKOFF opens the window: the arm covers a game when its stored kickoff
  (matches.utc_date, naive UTC) is in [opens_at, closes_at): opens_at included, closes_at excluded. The write clock is
  never read: a row written before the window for a game inside it carries the arm; a game outside never does,
  whenever written. 247's closes_at is 06:00Z on 11-24, so week 11's MNF (kickoff 2026-11-24T01:15Z) is inside.
- THE ARM (247 item 2(6)): predict-nfl prices nfl_elo_v2 for a covered game by v1's own live walk
  (nfl_predict._current_ratings: every stored FINISHED non-preseason NFL game, in kickoff-then-id order) under
  nfl_v2_gate.candidate's config for the WHOLE walk (home_advantage replaces v1's for price and update; a shrink is a
  price map only), never the gate's cold start re-run: the gate's walk continued into 2026, so the arm's 2025
  probabilities equal the gate's scored 2025 ones game for game (tests pin it on the synthetic stream, walked both
  ways). Stored on v1's own Prediction row under factor_breakdown[FB_KEY] (one row, one close, one outcome: the
  pl-availability shape), four places as v1's; v1's fields are written exactly as before; a failed second walk stores
  {version, error} and never stops v1's row.
- THE PAGES (247 item 2(2), item 3): export-nfl-predictions (the slate file, and the closing run's file: the same
  function) writes ROW_KEYS, the separate `rehearsal_*` prefix, on a row the gate covers (host, PASS, rehearsal, the
  kickoff in the window): the probabilities, the entry id, the term, the verdict stamp, the label "rehearsal — not a
  call" and a reason (null, or why the stored arm is missing). Outside `prediction`, never the `candidate_*` keys
  (pl-availability-v1's), and under no name desk_policy.normalize reads: the Desk reads nothing from it. After the
  window closes the export writes no new arm row. The file's top-level `rehearsal: false` (a fossil the Cockpit reads)
  is untouched.
- THE GRADER'S SECOND ARM (247 item 2(4), 2(5)): export-nfl-results reads EVERY stored arm row on the host, whatever
  the registry reads now (written once, read for the record always: the 11-24 dry read reads them): RESULT_KEY on the
  row, and RECORD_KEY in the season record, both arms over the same games (the live, non-re-dated rows carrying a
  priced arm), in total and per NFL game week (the row's `week`, matches.matchday as nfl_predict assigns it, never
  the calendar week). Each figure keeps its own tie rule, stated on its line (RULES): the log-loss is the frozen gate's
  arithmetic (nfl_backtest.walk_protocol: y = 1 for a home win, else 0, a tie a home loss; p floored at 1e-12;
  `game_log_loss` is that expression, pinned equal to walk_protocol's own figure to the bit); the Brier is (p - y)^2 on
  the same y; the W-L-P and the vs-close figure treat a tie as a push, as results-tally does.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

EID = "nfl-elo-v2"
MODEL_VERSION = "nfl_elo_v2"
FB_KEY = "nfl_elo_v2_rehearsal"         # the arm's key in v1's Prediction.factor_breakdown (never exported as is)
PREFIX = "rehearsal_"                   # 247 item 2(2): the arm's own key prefix, host-only, masked by the compare
ROW_KEYS = ("rehearsal_version", "rehearsal_probabilities", "rehearsal_term", "rehearsal_verdict_stamp",
            "rehearsal_label", "rehearsal_reason")      # pl_availability.ROW_KEYS' shape, renamed (no missing counts)
RESULT_KEY = "rehearsal_arm"            # the results row's second arm
RECORD_KEY = "rehearsal_arm"            # the results file's record block of both arms
STATUS = "rehearsal"                    # 247 item 2(1): the registry status read (never written here)
WINDOW_KEY = "rehearsal_window"         # 247 item 2(1): {"opens_at": "...Z", "closes_at": "...Z"} (never written here)
WINDOW_FIELDS = ("opens_at", "closes_at")
LABEL = "rehearsal — not a call"        # 247 item 3, verbatim
EPS = 1e-12                             # nfl_backtest.walk_protocol's floor (its local `eps`)
RULING_230 = "ARCHITECT 2026-11-03 09:00 ET, addendum 230 item 1(a)"
RULING_247 = "ARCHITECT 2026-11-04 09:55 ET, addendum 247 items 2-3"
RULING_230_TEXT = (
    "(a) nfl-v2's REHEARSAL (lane nfl-v2, the 11-23 step: \"on PASS: the rehearsal on the host's pages from the next "
    "tag, weeks 10 and 11, 11-12 through 11-23\") — PR BY 11-09, on a tag by 11-11: nfl_elo_v2's probabilities as a "
    "SECOND ARM on the NFL slate and closing pages beside v1's record-only would-be (the pl-availability shadow's "
    "shape: two probability sets, the grader's second arm, the arm labelled with the entry and its verdict stamp), "
    "written only while the entry's verdict reads PASS and its rehearsal window is open (registry state 'rehearsal', "
    "11-12 to 11-23); the Desk reads nothing from it (market-only stands until my live ruling of 11-26); the results "
    "export carries both arms' log-loss against the close and Brier per week; a FAIL on 11-06 leaves every line of it "
    "dormant. Gate-class (an export contract): the PR body shows a synthetic page with both arms and the pin that the "
    "Desk's call never reads the second arm.")
RULING_247_TEXT = (
    "2. THE REHEARSAL ARM (230 item 1(a)), the six, RULED:",
    "(1) WHO WRITES THE STATE, AND THE INSTANTS: after Friday's run, Code's verdict-record PR (the one that writes the "
    "run record and verdict into the entry, by my verdict addendum) ALSO writes, on PASS only, `status: \"rehearsal\"` "
    "and `rehearsal_window: {\"opens_at\": \"2026-11-12T00:00:00Z\", \"closes_at\": \"2026-11-24T06:00:00Z\"}` — week "
    "10's Thursday through week 11's Monday night INCLUDED (the MNF of 11-23 ET kicks off 2026-11-24T01:15Z and is "
    "week 11's last game; 215's \"11-12 through 11-23\" is ET dates). On FAIL nothing is written and the arm is dormant "
    "for the season. The shape the code reads is exactly that; a test pins it.",
    "(2) THE COMPARE: a SEPARATE key prefix `rehearsal_*` (rehearsal_version, rehearsal_probabilities, "
    "rehearsal_reason…), host-only, masked by compare_exports.py under its own line \"rehearsal-arm keys (host-only, "
    "nfl-elo-v2)\" beside the pl-availability line — #735's pattern, in the SAME PR (a compare that would fail the tag "
    "on its own arm is a defect, not a question). Never the `candidate_*` keys: those are pl-availability-v1's line "
    "and its count.",
    "(3) WHAT OPENS THE WINDOW PER ROW: the GAME'S KICKOFF inside the window (as recommended); a row written before "
    "the window for a game inside it carries the arm; a row for a game outside it never does, whenever written.",
    "(4) AFTER THE WINDOW CLOSES: the export STOPS WRITING the arm (no new rows) but the results export KEEPS READING "
    "every stored arm row — the 11-24 dry read reads them. Written once, read for the record always.",
    "(5) TIES: each figure keeps the rule it already has, stated on its line — the log-loss treats a tie as the gate's "
    "protocol does (walk_protocol's own rule, unchanged: the rehearsal's log-loss must be the gate's arithmetic), the "
    "W-L-P and the vs-close figure treat a tie as a push, as results-tally does. \"Per week\" = the NFL game week as "
    "nfl_predict assigns it (weeks 10 and 11), never the calendar week.",
    "(6) THE LIVE WALK: the same games as nfl_elo_v1's live walk (2024 to date, every non-preseason FINISHED game, in "
    "order), with the declared term for the whole walk — the gate's walk continued into 2026, so the arm's 2025 "
    "probabilities EQUAL the gate run's scored 2025 probabilities game for game: a parity test pins it (the gate's run "
    "record will hold them after Friday; before that, the test walks the synthetic stream both ways). Never the gate's "
    "cold start re-run on the host.",
    "3. The Desk reads nothing from the arm (a byte-identical pin, as planned); the arm labels every row with the entry "
    "id, the term and \"rehearsal — not a call\"; the phone page carries no arm line (the summary block and receipt "
    "do, as 223 item 3 ruled for the would-be line).",
)
DORMANT_TEXT = "a FAIL on 11-06 leaves every line of it dormant"
# Each figure's tie rule, on its own line (247 item 2(5)); the record block carries them verbatim
RULES = {
    "log_loss": ("mean per-game log-loss, the frozen gate's arithmetic (nfl_backtest.walk_protocol, unchanged): "
                 "-(y ln p + (1 - y) ln(1 - p)), p floored at 1e-12, y = 1 for a home win, else 0: a TIE COUNTS AS A "
                 "HOME LOSS, as the gate's protocol scores it; over every game of the block"),
    "brier_score": ("mean (p - y)^2 of the home probability, two-way, on the log-loss's y: a TIE COUNTS AS A HOME "
                    "LOSS; over every game of the block"),
    "wlp": ("the top pick's W-L-P (home when p >= 0.5, as v1's top_pick): a TIE IS A PUSH (P), neither W nor L, as "
            "results-tally does"),
    "vs_close": ("vs_close.block over the decided games with a close (the row's graded close, the one v1 is graded "
                 "at): a TIE IS A PUSH and out, as results-tally does"),
    "week": ("per week = the NFL game week as nfl_predict assigns it (the row's `week`, matches.matchday), never the "
             "calendar week"),
    "games": ("both arms over the same games: the season record's live, non-re-dated rows that carry a priced "
              "rehearsal arm"),
}


# --------------------------------------------------------------------------------------------- the gate --

@dataclass(frozen=True)
class Gate:
    """The predicate's reading. `on`: (a)-(e) of the module docstring; `covers(kickoff)` adds the game's half."""
    on: bool
    why: str | None
    verdict_at: str | None = None
    opens_at: datetime | None = None
    closes_at: datetime | None = None
    form: str | None = None
    value: float | None = None
    cfg: object = field(default=None, compare=False)
    price: object = field(default=None, compare=False)

    def covers(self, kickoff: datetime | None) -> bool:
        """The game's kickoff is in [opens_at, closes_at): opens_at included, closes_at excluded (247 item 2(3))."""
        k = _naive(kickoff)
        return bool(self.on and k is not None and self.opens_at <= k < self.closes_at)

    @property
    def stamp(self) -> str | None:
        return stamp(self.verdict_at) if self.on else None

    @property
    def term(self) -> dict | None:
        return {"form": self.form, "value": self.value} if self.on else None


def stamp(verdict_at: str | None) -> str:
    """The verdict stamp the arm is labelled with: "nfl-elo-v2 PASS <verdict.at>"."""
    return f"{EID} PASS {verdict_at}"


def _naive(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _off(why: str) -> Gate:
    return Gate(False, why)


def _instant(v) -> datetime | None:
    """A ruled-shape instant: a string ending in "Z" that pl_availability.parse_instant reads (naive UTC), else None."""
    from src.walters.pl_availability import parse_instant
    return parse_instant(v) if isinstance(v, str) and v.endswith("Z") else None


def state(entry: dict | None, host_why: str | None = None) -> Gate:
    """The predicate on one registry entry (pure: the tests call it on hand-built entries). `host_why`:
    desk_policy.not_host_reason()'s answer (None on the host). See the module docstring, (a)-(e)."""
    if host_why is not None:
        return _off(f"{EID}'s rehearsal arm runs on the host only: {host_why}")
    if not isinstance(entry, dict) or entry.get("id") != EID:
        return _off(f"no {EID} entry in the registry")
    v = entry.get("verdict")
    verdict = v.get("verdict") if isinstance(v, dict) else None
    if verdict != "PASS":
        return _off(f"{EID}'s verdict reads {verdict or 'null'}, not PASS ({RULING_230}: \"{DORMANT_TEXT}\")")
    at = v.get("at")
    if not isinstance(at, str) or not at.strip():
        return _off(f"{EID}'s PASS carries no verdict stamp (verdict.at): the arm is labelled with it or not written")
    if entry.get("status") != STATUS:
        return _off(f"{EID}'s status reads {entry.get('status')!r}, not {STATUS!r} ({RULING_247} item 2(1): written "
                    "by the verdict-record PR, on PASS only)")
    w = entry.get(WINDOW_KEY)
    if not isinstance(w, dict) or set(w) != set(WINDOW_FIELDS):
        return _off(f"{EID}'s {WINDOW_KEY} is not exactly {{opens_at, closes_at}} ({w!r})")
    lo, hi = _instant(w["opens_at"]), _instant(w["closes_at"])
    if lo is None or hi is None:
        return _off(f"{EID}'s {WINDOW_KEY} is not two UTC instants ending in Z ({w['opens_at']!r}, "
                    f"{w['closes_at']!r})")
    if not lo < hi:
        return _off(f"{EID}'s {WINDOW_KEY} opens at or after it closes ({w['opens_at']}, {w['closes_at']})")
    from src.walters import nfl_v2_gate as g2
    try:
        form, value = g2.declared_term(entry)
        g2.declared_constants(entry)
        cfg, price = g2.candidate(form, value)
    except g2.GateRefused as err:
        return _off(f"the declared term or constants do not price: {err}")
    return Gate(True, None, at.strip(), lo, hi, form, value, cfg, price)


def host_reason() -> str | None:
    """desk_policy.not_host_reason(), the host-only gate pl-availability-v1 uses; a failed read is never the host."""
    try:
        from src.walters.desk_policy import not_host_reason
        return not_host_reason()
    except Exception as err:                            # noqa: BLE001  (law 4: unknown is not the host)
        return f"the machine role could not be read ({type(err).__name__})"


def read_gate(path: str | None = None) -> Gate:
    """state() on the registry's entry now (registry.LEDGER at call time; `path` for a tmp registry), on this machine's
    role. Never raises: an unreadable registry or any failure of the read is dormant with its reason (law 4), never an
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
        return state(next((e for e in entries if isinstance(e, dict) and e.get("id") == EID), None))
    except Exception as err:                            # noqa: BLE001
        return _off(f"the gate could not be read ({type(err).__name__}: {err})"[:300])


# ------------------------------------------------------------------------------------------ the stored arm --

def price(gate: Gate, p_raw: float) -> float:
    """The candidate's home probability from its walk's expectation: the shrink's price map when the form is shrink,
    else the walk's own (home_advantage replaces the config for price and update: nfl_v2_gate.candidate)."""
    return float(gate.price(p_raw)) if gate.price is not None else float(p_raw)


def arm_block(gate: Gate, p_home: float) -> dict:
    """The arm as v1's Prediction row stores it under FB_KEY: four places, as v1's row stores its own."""
    return {"version": EID, "model_version": MODEL_VERSION, "p_home": round(p_home, 4),
            "p_away": round(1 - p_home, 4), "term": gate.term, "verdict": "PASS", "verdict_at": gate.verdict_at}


def failed_block(gate: Gate, err: BaseException) -> dict:
    """The marker stored when the second walk could not price a covered game (v1's row is written as always)."""
    return {"version": EID, "model_version": MODEL_VERSION, "term": gate.term, "verdict": "PASS",
            "verdict_at": gate.verdict_at, "error": f"{type(err).__name__}: {err}"[:200]}


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def stored(pred) -> dict | None:
    """The raw stored block of this module on a Prediction row (whole or failed), or None."""
    fb = getattr(pred, "factor_breakdown", None) if pred is not None else None
    a = fb.get(FB_KEY) if isinstance(fb, dict) else None
    return a if isinstance(a, dict) and a.get("version") == EID else None


def arm_of(pred) -> dict | None:
    """The stored arm when it is whole (both probabilities finite), else None (never repaired)."""
    a = stored(pred)
    return a if a is not None and _num(a.get("p_home")) and _num(a.get("p_away")) else None


def _missing_reason(pred) -> str:
    a = stored(pred)
    if a is not None and isinstance(a.get("error"), str):
        return f"the second walk failed for this game ({a['error']}); v1's row was written as always"
    return "the stored prediction carries no rehearsal arm (written before the gate read on, or before this build)"


# ----------------------------------------------------------------------------------------------- the pages --

def export_fields(gate: Gate, pred, kickoff: datetime | None) -> dict | None:
    """The slate / closing row's arm keys (ROW_KEYS), or None (absent) when the gate does not cover the game. Labelled
    from the gate read now; a stored arm priced under another stamp or term is never relabelled (reason, no
    probabilities)."""
    if not gate.covers(kickoff):
        return None
    out = {"rehearsal_version": EID, "rehearsal_probabilities": None, "rehearsal_term": gate.term,
           "rehearsal_verdict_stamp": gate.stamp, "rehearsal_label": LABEL, "rehearsal_reason": None}
    a = arm_of(pred)
    if a is None:
        out["rehearsal_reason"] = _missing_reason(pred)
    elif a.get("verdict_at") != gate.verdict_at or a.get("term") != gate.term:
        out["rehearsal_reason"] = (f"the stored arm was priced under another verdict stamp or term "
                                   f"({a.get('verdict_at')!r}, {a.get('term')!r}); the registry reads "
                                   f"{gate.verdict_at!r}, {gate.term!r}")
    else:
        out["rehearsal_probabilities"] = {"home_win": a["p_home"], "away_win": a["p_away"]}
    return out


# --------------------------------------------------------------------------------- the grader's second arm --

def _r4(x: float) -> float:
    return round(x, 4) + 0.0


def gate_y(home_score: int, away_score: int) -> int:
    """walk_protocol's outcome: 1 for a home win, else 0 (its comment: "ties count as home loss for scoring")."""
    return 1 if home_score > away_score else 0


def game_log_loss(p_home: float, y: int) -> float:
    """walk_protocol's per-game log-loss, the same expression (nfl_backtest.py, the scored pass), floored at EPS."""
    return -(y * math.log(max(p_home, EPS)) + (1 - y) * math.log(max(1 - p_home, EPS)))


def mean_as_the_gate(values) -> float | None:
    """The mean as walk_protocol accumulates it: `+=` in order from 0.0, then one division (never sum(), whose float
    summation is compensated from Python 3.12, so its last bit can differ from the gate's)."""
    acc, n = 0.0, 0
    for v in values:
        acc += v
        n += 1
    return acc / n if n else None


def brier(p_home: float, y: int) -> float:
    """The two-way Brier of one game, (p - y)^2 on the home probability, y the log-loss's."""
    return (p_home - y) ** 2


def result_arm(pred, home_score: int, away_score: int, host_why: str | None) -> dict | None:
    """The results row's second arm on the host, or None (absent) off the host or when the row stores no arm. Read
    from the STORED arm whatever the registry reads now (247 item 2(4)); labelled from what was stored."""
    if host_why is not None:
        return None
    raw = stored(pred)
    if raw is None:
        return None
    tie = home_score == away_score
    y = gate_y(home_score, away_score)
    out = {"version": EID, "model_version": MODEL_VERSION, "term": raw.get("term"),
           "verdict_stamp": stamp(raw.get("verdict_at")), "label": LABEL, "home_win_prob": None,
           "away_win_prob": None, "top_pick": None, "top_pick_hit": None, "push": tie, "log_loss": None,
           "brier_score": None, "reason": None}
    a = arm_of(pred)
    if a is None:
        out["reason"] = _missing_reason(pred)
        return out
    p = a["p_home"]
    pick_home = p >= 0.5
    out.update({"home_win_prob": p, "away_win_prob": a["p_away"], "top_pick": "home_win" if pick_home else "away_win",
                "top_pick_hit": None if tie else (pick_home == (y == 1)),
                "log_loss": _r4(game_log_loss(p, y)), "brier_score": _r4(brier(p, y))})
    return out


def _priced(r: dict) -> bool:
    a = r.get(RESULT_KEY)
    return isinstance(a, dict) and _num(a.get("home_win_prob"))


def _y(r: dict) -> int:
    a = r.get("actual") or {}
    return gate_y(a["home_score"], a["away_score"])


def _figures(rows: list[dict], p_of, model_version) -> dict:
    """One arm's figures over `rows`, each with its own tie rule (RULES)."""
    from src.walters.vs_close import block_from_rows
    n = len(rows)
    w = l_ = p_ = 0
    for r in rows:
        if (r.get("graded") or {}).get("push"):
            p_ += 1
            continue
        home = p_of(r) >= 0.5
        if home == ((r.get("actual") or {}).get("result") == "H"):
            w += 1
        else:
            l_ += 1
    graded = [{"predicted": {"home_win_prob": p_of(r)}, "actual": r.get("actual"), "graded": r.get("graded")}
              for r in rows]
    return {"model_version": model_version,
            "log_loss": _r4(mean_as_the_gate(game_log_loss(p_of(r), _y(r)) for r in rows)) if n else None,
            "brier_score": _r4(mean_as_the_gate(brier(p_of(r), _y(r)) for r in rows)) if n else None,
            "w": w, "l": l_, "p": p_, "vs_close": block_from_rows(graded)}


def _both(rows: list[dict]) -> dict:
    v1 = rows[0]["predicted"].get("model_version") if rows else None
    return {"games": len(rows),
            "v1": _figures(rows, lambda r: r["predicted"]["home_win_prob"], v1),
            "v2": _figures(rows, lambda r: r[RESULT_KEY]["home_win_prob"], MODEL_VERSION)}


def record_block(rows: list[dict], redated: list[dict] = ()) -> dict | None:
    """The results file's record of both arms (RECORD_KEY) over `rows` (the season record's: live, not re-dated) that
    carry a priced arm, in total and per week; None (absent) when no row of `rows` or `redated` carries an arm."""
    carry = [r for r in rows if isinstance(r.get(RESULT_KEY), dict)]
    red = [r for r in redated if isinstance(r.get(RESULT_KEY), dict)]
    if not carry and not red:
        return None
    arm = [r for r in carry if _priced(r)]
    weeks: dict[str, list] = {}
    for r in arm:
        weeks.setdefault(str(r.get("week")), []).append(r)
    return {"version": EID, "label": LABEL, "ruling": f"{RULING_230}, as ruled by {RULING_247}",
            "verdict_stamps": sorted({r[RESULT_KEY].get("verdict_stamp") for r in carry + red}),
            "terms": sorted({f"{(r[RESULT_KEY].get('term') or {}).get('form')} "
                             f"{(r[RESULT_KEY].get('term') or {}).get('value')}" for r in carry + red}),
            "rules": dict(RULES), "unpriced_arm_rows": len(carry) - len(arm), "redated_arm_rows": len(red),
            "total": _both(arm),
            "by_week": {k: _both(v) for k, v in sorted(weeks.items(), key=lambda kv: (len(kv[0]), kv[0]))}}
