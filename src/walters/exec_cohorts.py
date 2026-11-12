"""THE EXEC COHORTS (ARCHITECT 2026-10-20 09:59 ET, addendum 146 item 1(v)), verbatim: "(v) results-tally gains an
"exec cohorts" block per closing family: counts, record and units at the exec cost for exec >= 4, 0 < exec < 4,
exec <= 0, from the closing files on disk, read-only, so the n=30 read in (i) is automatic. Small; it may ride #431 or
its own PR."

The rule the cohorts are read for, item 1(i), verbatim: "(i) The K-track is BINDING. desk.exec.edge_pp (the ask plus
the taker fee, basis "taker") is the number the PLAY floor applies to. The floor is +4.0 exec edge and does not move.
The written exec-hold rule of 2026-10-18 stands verbatim: exec <= 0 -> no bet; 0 < exec < 4 -> the Desk's half units
stand when the QB inputs are clean, as the pre-registered cohort; it is READ at n=30 graded (the same bar as the value
shadows, #86), never earlier. Ties are rejections."

As built (each reading is the conservative one, law 4; the PR body lists them for the architect):
- The rows are the closing files on this machine's disk (redated.closing_rows: <exports>/closing_*.json, every file,
  never host/), one row per game: the newest run's row within the hour of the game's current start (Desk clock drift,
  desk_policy.DESK_CLOCK_DRIFT); a game none of whose rows is within the hour is void when redated.void_label says so
  (re-dated, or the placeholder kickoff), left out and named; else its newest row is graded.
- Only PLAY calls count (desk.call). A LADDER carries no exec block by design (desk_policy.call_exec_block) and is
  left out, counted. Its ordered NO leg's informational price (desk.ladder_exec, #689) puts it on its own line, priced
  but ungraded: by that edge's cell, the mean edge and the unpriced rows by why, never pooled with PLAY.
- THE FLOOR-BLOCKED LINE (#690, RULING_FLOOR): a PASS row of the probability floor (the pick's model_p under the
  family's own pMin, 0.50 for SOCCER and INTL; the edge floor writes the same pass_kind and is told apart by the
  probability) with exec >= 4 at the close (desk.exec.edge_pp, basis taker) is counted on its own line per family with
  a probability floor: W-L-P and notional units at 1u (BASE_UNITS, the size a PASS row's exec block is priced at) at
  desk.exec.cost. It never enters a PLAY cell or the n=30 counter. The line prints 0 when nothing qualifies: the floor
  is frozen and the line is its receipt. Only a model-engine row is read; a non-finite model_p never is; INTL is graded
  on the 90-minute result (intl_shadow.result_90; an AET / PEN game without it stays open); a void row keeps its label
  (re-dated or placeholder kickoff) on the line (Codex on #717). PASS rows, quarantine shadows and value shadows are not calls.
- The cohort is desk.exec.edge_pp: exec >= 4 is the Desk's own exec_clears (4 less FEE_CLEAR_EPS); 0 < exec < 4 is
  e > 0 and not clears; exec <= 0 is e <= 0. A PLAY with no exec edge is "exec unknown", never guessed into a cohort;
  a basis other than taker is left out, counted. 0 < exec < 4 splits on the Desk's QB tags (QB_TAGS): QB inputs clean
  is the pre-registered cohort; a QB-flagged or unread row is outside it.
- Units are notional at desk.exec.cost (the cost edge_pp comes from): a hit wins units x (1/cost - 1), a miss loses the
  units, a push or a void 0. Never fills: the ledger holds those.
- Results from the DB: CANCELLED, POSTPONED and STALE_ORPHAN are void; FINISHED with both scores decides (a level
  two-way score is a push; a three-way board reads full_time_result, else the scores); anything else is open. A row
  whose teams are not the DB match's is left out (match ids are machine-local), as is a match id this DB lacks.
- THE WOULD-BE LINE (ARCHITECT 2026-11-02 11:20 ET, addendum 217 item 4, RULING_217_4): an NFL row the Desk called
  PASS market-only (desk_policy NFL_MARKET_ONLY_KIND: the row's own record that it was written while the model was
  uncertified) whose record-only would-be call (desk.market_only_hold.would_call) is PLAY is counted on ONE line of its
  own, labelled WOULD_BE. Each row decides from what it carries, never from the registry's state today, so a closing
  file written while uncertified counts the same after a certification. The line is printed while the registry does
  not read the NFL model certified (registry.certification_of on family "NFL" and nfl_predict.MODEL_VERSION, addendum 299 item 3(a), the uncertified() #785
  built; an unread registry or a missing entry is never judged certified, law 4), and after that whenever a would-be
  row or a #446 row is there (the registry's state is the head's text only): split by the QB tags the hold reads (QB_TAGS: QB-flagged or unread / QB inputs clean),
  W-L-P and notional units at would_units at desk.exec.cost (the exec block the chain sized, desk_policy
  call_exec_block), the exec cells counted beside. It never enters a PLAY cell, the n=30 counter or the pooled line,
  and it is never a position. Its tail is #446's thirty-row count (addendum 44 item 9): the NFL PLAY rows in a cell
  with a QB tag plus the QB-tagged would-be rows, each labelled, closing runs from the hold of 2026-10-11 (HOLD_446_FROM;
  earlier ones and undated ones beside it, not counted). Certified with neither a would-be row nor a #446 row: no line.
- THE THIRTY COUNTS ROWS (ARCHITECT 2026-11-03 07:55 ET, addendum 225 item 2(a), RULING_225_2A): a #446 row (a PLAY or
  a would-be PLAY with a QB tag) counts toward thirty BEFORE the DB / result / cohort eligibility checks; those checks
  stay for W-L-P and units, and a counted row they leave out is named beside the count by its cause, per kind (CAUSES:
  not in this copy, teams differ, re-dated void, non-taker basis), never scored. (b) the zero line (RULING_225_2B):
  while the registry does not read NFL certified, the line prints even when no NFL closing file is in the directory
  (the section's no-files path included): 0, with that cause named (NO_NFL_FILE), law 4.
- Read-only: one session, nothing written; no verdict is computed (the n=30 read is the architect's).
- The n=30 counter starts at the PRE-REGISTRATION (R41 RULED, ARCHITECT 2026-10-20 19:54 ET, addendum 151 item 2):
  it counts only the pre-registered cohort's graded rows whose closing run starts on or after 2026-10-19 07:40 ET
  (PRE_REGISTERED, addendum 136 item 5(iv)); the earlier graded rows of the same cell print beside it, "before
  pre-registration, not counted", and a row with no run start is not counted either (named when there is one). The per-family lines keep every row: they are the record.
"""
from __future__ import annotations

import math
from datetime import datetime
from zoneinfo import ZoneInfo

from src.db.schema import MatchStatus, Result
from src.walters import desk_policy
from src.walters.redated import as_utc, closing_rows, void_counts, void_label

RULING_V = ("(v) results-tally gains an \"exec cohorts\" block per closing family: counts, record and units at the "
            "exec cost for exec >= 4, 0 < exec < 4, exec <= 0, from the closing files on disk, read-only, so the n=30 "
            "read in (i) is automatic. Small; it may ride #431 or its own PR.")
QB_TAGS = ("QB-flagged half units", desk_policy.INJURY_EMPTY_TAG)      # desk_policy's two QB tags, verbatim
VOID = (MatchStatus.CANCELLED, MatchStatus.POSTPONED, MatchStatus.STALE_ORPHAN)   # closing.VOID, by name
READ_AT_N = 30
# The n=30 counter's start, R41 RULED (RULING_R41, verbatim): the pre-registration, addendum 136 item 5(iv),
# 2026-10-19 07:40 ET. Only closing runs that start on or after it count toward n=30; 1(i)'s rule of 2026-10-18
# (RULING_RULE_OF_1018, verbatim) remains the behaviour.
RULING_R41 = ("2. R41, the n=30 counter's start: the PRE-REGISTRATION, addendum 136 item 5(iv), 2026-10-19 07:40 ET. A "
              "pre-registered cohort counts from the moment it was registered, not from the rule that defined it; the "
              "rows before it (the three of 146 item 1(b)) print beside the counter as \"before pre-registration, not "
              "counted\". The written exec-hold rule of 10-18 remains the behaviour; the count is the cohort's.")
RULING_RULE_OF_1018 = ("The written exec-hold rule of 2026-10-18 stands verbatim: exec <= 0 -> no bet; 0 < exec < 4 -> "
                       "the Desk's half units stand when the QB inputs are clean, as the pre-registered cohort; it is "
                       "READ at n=30 graded (the same bar as the value shadows, #86), never earlier.")
PRE_REGISTERED = datetime(2026, 10, 19, 7, 40, tzinfo=ZoneInfo("America/New_York"))
COUNTED_FROM = as_utc(PRE_REGISTERED)                 # 2026-10-19 11:40, naive UTC: the closing runs' own clock
COUNTED_FROM_TEXT = "closing runs from the pre-registration (2026-10-19 07:40 ET)"
BEFORE_TEXT = "before pre-registration, not counted"
# THE WOULD-BE LINE (ARCHITECT 2026-11-02 11:20 ET, addendum 217 item 4, verbatim):
RULING_217_4 = ("4. RULED, a follow-up PR (small, after the v2 harness): #446's measurement keeps accruing on paper — "
                "exec_cohorts and the closing page's hold check gain one cohort line for NFL while uncertified, "
                "\"would-be PLAY (uncertified, unstaked)\", reading the record-only would-be call with the same QB-flag "
                "/ unread-list classification, never pooled with PLAY, never a position. #446's read at thirty rows "
                "counts those rows too, labelled. Not blocking #778.")
WOULD_BE = "would-be PLAY (uncertified, unstaked)"         # the ruled label, verbatim (closing.WOULD_BE: a test pins it)
WOULD_BE_FAMILIES = ("NFL",)                                # desk_policy.NFL_MARKET_ONLY_SPORTS, as a closing family
QB_OUT, QB_CLEAN = "QB-flagged or unread", "QB inputs clean"
# #446 (ARCHITECT 2026-10-12 08:41 ET, addendum 44 item 9), verbatim: "Every NFL row the Desk calls PLAY with a QB flag
# or an unread list is kept with what the page said, the price it named, the close, the result, and what was done about
# it. I read the receipt at thirty such rows or at the season's end, whichever comes first."
READ_446_AT_N = 30
HOLD_446_FROM = as_utc(datetime(2026, 10, 11, 0, 0, tzinfo=ZoneInfo("America/New_York")))   # closing.CLOSING_HOLDS'
HOLD_446_FROM_TEXT = "closing runs from the hold of 2026-10-11"                           # QB hold, "since"
# THE THIRTY COUNTS ROWS (ARCHITECT 2026-11-03 07:55 ET, addendum 225 item 2), verbatim:
RULING_225_2A = ("(a) THE THIRTY COUNTS ROWS. Addendum 44 item 9 reads \"thirty such rows\", and the hold's effect is per "
                 "row, not per graded outcome: every post-hold NFL row the hold touched — a PLAY with a QB tag or an "
                 "unread list, a would-be PLAY (uncertified, unstaked) with the same — counts toward thirty BEFORE the "
                 "DB / result / cohort eligibility checks; those checks stay for W-L-P and units, and a row they leave "
                 "out is named beside the count by its cause (not in this copy, teams differ, re-dated void, non-taker "
                 "basis), never scored. A copy that lacks games must not delay the read that the count triggers.")
RULING_225_2B = ("(b) THE ZERO LINE RENDERS whenever the registry reads NFL uncertified, independent of whether NFL is in "
                 "the closing-file family set; with no NFL closing file in the directory it prints 0 with that cause "
                 "named (law 4: a labelled absence, never silence).")
NOT_IN_COPY, TEAMS_DIFFER, REDATED, NON_TAKER = "not in this copy", "teams differ", "re-dated void", "non-taker basis"
CAUSES = (NOT_IN_COPY, TEAMS_DIFFER, REDATED, NON_TAKER)    # the ruled causes, in the ruling's order

GE4, MID, LE0, UNKNOWN = "exec >= 4", "0 < exec < 4", "exec <= 0", "exec unknown"
MID_QB = "0 < exec < 4, QB"              # the cell key of the QB-tagged half of MID (outside the cohort)
CELLS = (GE4, MID, MID_QB, LE0, UNKNOWN)
CELL_TEXT = {GE4: "exec >= 4",
             MID: "0 < exec < 4, QB inputs clean (the pre-registered cohort)",
             MID_QB: "0 < exec < 4, QB-flagged or unread (outside the cohort)",
             LE0: "exec <= 0 (no bet under the exec-hold rule of 2026-10-18; notional)",
             UNKNOWN: "exec unknown (no exec edge on the row)"}
SIDES = {Result.HOME: "HOME", Result.DRAW: "DRAW", Result.AWAY: "AWAY"}
NO_FAMILY = "(no family)"


def cohort_of(edge_pp) -> str:
    """The cohort of a PLAY's desk.exec.edge_pp: exec unknown (None, or not a finite number: law 4, never guessed into a
    cohort), exec >= 4 (desk_policy.exec_clears), 0 < exec < 4 (above zero, not clears), exec <= 0."""
    if edge_pp is None or isinstance(edge_pp, bool):
        return UNKNOWN
    try:
        e = float(edge_pp)
    except (TypeError, ValueError):
        return UNKNOWN
    if not math.isfinite(e):
        return UNKNOWN
    if desk_policy.exec_clears(e):
        return GE4
    return MID if e > 0 else LE0


def settle_units(units, result: str, cost) -> float | None:
    """Notional units at the exec cost (the stake model of the architect's 1(b) arithmetic): a win units x (1/cost -
    1), a loss -units, a push or a void 0.0 (whatever the cost: a known 0 never reads unpriced); None while open, and
    a win or a loss None (unpriced) unless 0 < cost < 1 and units is a finite number (a bool, NaN or inf in units or
    cost reads unpriced: counted, never summed, law 4, as cohort_of reads the edge)."""
    if result in ("push", "void"):
        return 0.0
    if isinstance(units, bool) or isinstance(cost, bool):
        return None
    try:
        c, u = float(cost), float(units)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(u) and math.isfinite(c)):
        return None
    if not 0.0 < c < 1.0:
        return None
    if result == "win":
        return u * (1.0 / c - 1.0)
    if result == "loss":
        return -u
    return None


def result_of(m, pick) -> str:
    """The pick's result on the DB match: void (VOID), win, loss or push (a level two-way score: the NFL tie), else
    open (not FINISHED, a null score, or a pick that names no side)."""
    from src.walters.close import THREE_WAY, outcomes_for
    if m.status in VOID:
        return "void"
    if m.status != MatchStatus.FINISHED or m.home_score is None or m.away_score is None:
        return "open"
    hs, as_ = m.home_score, m.away_score
    if tuple(outcomes_for(m.sport)) == THREE_WAY:
        side = SIDES.get(m.full_time_result) or ("HOME" if hs > as_ else "AWAY" if hs < as_ else "DRAW")
    elif hs == as_:
        return "push"
    else:
        side = "HOME" if hs > as_ else "AWAY"
    if pick not in ("HOME", "DRAW", "AWAY"):
        return "open"
    return "win" if pick == side else "loss"


def _cell() -> dict:
    return {"plays": 0, "w": 0, "l": 0, "p": 0, "open": 0, "void": 0, "units_sum": 0.0, "priced": 0, "unpriced": 0}


def _out() -> dict:
    return {"ladder": 0, "basis": 0, "not_in_db": 0, "teams": 0, "void": [], "ladder_priced": {k: 0 for k in CELLS},
            "ladder_edges": [], "ladder_unpriced": {}}


RULING_FLOOR = ("(3) FLOOR-BLOCKED COHORT (results-tally, read-only line): rows PASS by the 0.50 floor with exec >= 4 "
                "at the close (10-25: Newcastle, +8.6, won), counted notionally as \"PASS by floor, exec >= 4\", W-L and "
                "notional units, never pooled; the floor is frozen and this line is its receipt.")


def floor_blocked(desk: dict, fam: str) -> bool:
    """A closing row PASS by the probability floor with exec >= 4 at the close (ARCHITECT 2026-10-26 12:05 ET, #690;
    RULING_FLOOR). The Desk writes pass_kind "floor" for the edge floor too (desk_policy.desk_call), so the two are told
    apart by the probability: the pick's model_p under the family's own pMin (desk_policy.POLICY: SOCCER and INTL 0.50;
    a family with no probability floor has none). exec >= 4 is the Desk's own exec_clears on desk.exec.edge_pp at basis
    taker; an unknown edge is never read into it (law 4)."""
    if desk.get("engine") != "model_edge" or desk.get("call") != "PASS" or desk.get("pass_kind") != "floor":
        return False                                       # a venue-engine PASS is never the probability floor
    p_min = (desk_policy.POLICY.get(fam) or desk_policy.POLICY["DEFAULT"]).get("pMin", 0) or 0
    mp = desk.get("model_p")
    if (not p_min or isinstance(mp, bool) or not isinstance(mp, (int, float)) or not math.isfinite(mp)
            or not 0.0 <= mp < p_min):                     # a non-finite or negative p is never read in (#717, #718)
        return False
    ex = desk.get("exec") if isinstance(desk.get("exec"), dict) else None
    return bool(ex) and ex.get("basis") == "taker" and cohort_of(ex.get("edge_pp")) == GE4


def floor_result_of(m, pick, fam: str) -> str:
    """The floor-blocked row's result. INTL is graded on the 90-minute result (Codex on #717), the stream's own rule
    (intl_shadow.result_90): the 90-minute score, else the score of a FT row; an AET / PEN game with no 90-minute
    score is never graded (open, law 4). Every other family reads result_of, as the PLAY cells do."""
    if fam != "INTL" or m.status in VOID or m.status != MatchStatus.FINISHED:
        return result_of(m, pick)
    from src.walters.intl_shadow import result_90
    r = result_90(m)
    if r is None or pick not in ("HOME", "DRAW", "AWAY"):
        return "open"
    return "win" if {"H": "HOME", "D": "DRAW", "A": "AWAY"}[r] == pick else "loss"


def would_be_play(desk: dict) -> dict | None:
    """The record-only would-be call of a market-only row (desk_policy.nfl_market_only: the chain's own call, in
    desk.market_only_hold) when it is a PLAY on a PASS row of NFL_MARKET_ONLY_KIND; else None. Never a call."""
    if desk.get("call") != "PASS" or desk.get("pass_kind") != desk_policy.NFL_MARKET_ONLY_KIND:
        return None
    h = desk.get("market_only_hold")
    return h if isinstance(h, dict) and h.get("would_call") == "PLAY" else None


def qb_tagged(desk: dict) -> bool:
    """The hold's QB classification: the row carries one of the Desk's QB tags (QB_TAGS: QB-flagged or unread list)."""
    tags = desk.get("tags") if isinstance(desk.get("tags"), list) else []
    return bool({t for t in tags if isinstance(t, str)} & set(QB_TAGS))


def nfl_model_version() -> str:
    """The id predict-nfl writes (nfl_predict.MODEL_VERSION): the model the registry is read on and the line names
    ("the NFL model" if it cannot be imported: the line's text, never the section's failure)."""
    try:
        from src.walters.nfl_predict import MODEL_VERSION
        return MODEL_VERSION
    except Exception:                                   # noqa: BLE001
        return "the NFL model"


def nfl_certification(registry_path=None) -> tuple[str, str]:
    """The NFL model's certification in the registry (registry.certification_of on family "NFL" and
    nfl_predict.MODEL_VERSION, addendum 299 item 3(a)), for the line's head text: "uncertified", "certified" or
    "unread". Any failure to import or read degrades to ("unread", the exception's name) (law 4: never judged
    certified, never the section's failure)."""
    try:
        from src.walters import registry
        return registry.certification_of("NFL", nfl_model_version(), path=registry_path)
    except Exception as e:                              # noqa: BLE001
        return "unread", type(e).__name__


def _would() -> dict:
    return {QB_OUT: _cell(), QB_CLEAN: _cell(), "exec": {k: 0 for k in (GE4, MID, LE0, UNKNOWN)}, "basis": 0,
            "not_in_db": 0, "teams": 0, "void": []}


def _within(entries, current) -> list:
    """The entries whose recorded start is within the Desk's clock drift of the match's current start."""
    cur = as_utc(current)
    if cur is None:
        return []
    return [e for e in entries
            if (st := as_utc(e[2].get("utc_date"))) is not None and abs(cur - st) <= desk_policy.DESK_CLOCK_DRIFT]


def tally(exports_dir, registry_path=None) -> dict:
    """The cohorts per closing family, from the closing files on disk and this machine's DB. Read-only: one session,
    rolled back. {"files", "unreadable", "runs", "families": [sorted], "cells": {(family, cell): counts}, "left_out":
    {family: counts}, "cohort_graded": W + L of the pre-registered cohort over every family, its rows whose closing run
    starts at or after COUNTED_FROM only (the n=30 counter), "cohort_before": its graded rows of earlier runs,
    "cohort_undated": its graded rows with no run start (neither is counted), "certification": the NFL model's
    (nfl_certification, the head's text only), "model_version": the id it was read on, "would_be": {family: the would-be
    line's counts, each row by what it carries}, "count_446": {family: {"play", "would_be", "before", "undated"}},
    "unscored_446": {family: {"play" | "would_be": {cause: n}}}: the rows counted toward thirty that a DB / result /
    cohort check leaves out of W-L-P (addendum 225 item 2(a))}.
    `registry_path` None: the tracked registry."""
    from src.db.database import session_scope
    from src.db.schema import Match

    cr = closing_rows(exports_dir)
    fams = set(cr.get("families") or ())
    cells: dict = {}
    left: dict = {}
    floor: dict = {}
    pooled = {"graded": 0, "before": 0, "undated": 0}
    cert = nfl_certification(registry_path)
    would: dict = {}
    c446: dict = {}

    u446: dict = {}

    def count_446(fam, run, kind) -> bool:
        """One #446 row (225 2(a): counted before the eligibility checks); True when it counts toward thirty."""
        k = c446.setdefault(fam, {"play": 0, "would_be": 0, "before": 0, "undated": 0})
        slot = "undated" if run is None else kind if run >= HOLD_446_FROM else "before"
        k[slot] += 1
        return slot == kind

    def unscored_446(counted, fam, kind, cause):
        """A counted #446 row an eligibility check leaves out: named beside the count by its cause, never scored."""
        if counted:
            c = u446.setdefault(fam, {}).setdefault(kind, {})
            c[cause] = c.get(cause, 0) + 1

    with session_scope() as s:
        for mid in sorted(cr["rows"]):
            entries = cr["rows"][mid]
            m = s.get(Match, mid)
            lab = None
            if m is None:
                e = entries[-1]
            else:
                near = _within(entries, m.utc_date)
                if near:
                    e = near[-1]                                    # the newest page's row stands (148 item 1(j))
                else:
                    lab = void_label([(run, r.get("utc_date")) for run, _, r in entries], m.utc_date)
                    e = entries[-1]
            fam = e[1] or NO_FAMILY
            fams.add(fam)
            row = e[2]
            desk = row.get("desk") if isinstance(row.get("desk"), dict) else {}
            call = desk.get("call")
            out = left.setdefault(fam, _out())
            if call == "LADDER":
                out["ladder"] += 1
                # #689: the ordered NO leg's informational price (desk.ladder_exec), priced but never graded here
                lx = desk.get("ladder_exec") if isinstance(desk.get("ladder_exec"), dict) else None
                le = lx.get("edge_pp") if lx and lx.get("basis") == "taker" else None
                if le is None or cohort_of(le) == UNKNOWN:
                    why = (lx.get("why") if lx else None) or "no ladder_exec block on the row"
                    out["ladder_unpriced"][why] = out["ladder_unpriced"].get(why, 0) + 1
                else:
                    out["ladder_priced"][cohort_of(le)] += 1
                    out["ladder_edges"].append(float(le))
                continue
            if floor_blocked(desk, fam):                       # #690: its own line, never a PLAY cell
                fb = floor.setdefault(fam, {**_cell(), "not_in_db": 0, "teams": 0, "redated": []})
                if m is None:
                    fb["not_in_db"] += 1
                    continue
                h = m.home_team.name if m.home_team else None
                a = m.away_team.name if m.away_team else None
                if (row.get("home_team"), row.get("away_team")) != (h, a):
                    fb["teams"] += 1
                    continue
                if lab:
                    fb["redated"].append(lab)                      # its label kept (Codex on #717)
                    continue
                res = floor_result_of(m, desk.get("pick"), fam)
                fb["plays"] += 1
                fb[{"win": "w", "loss": "l", "push": "p", "void": "void", "open": "open"}[res]] += 1
                if res != "open":
                    u = settle_units(desk_policy.BASE_UNITS, res, desk["exec"].get("cost"))
                    if u is None:
                        fb["unpriced"] += 1
                    else:
                        fb["units_sum"] += u
                        fb["priced"] += 1
                continue
            wb = would_be_play(desk) if fam in WOULD_BE_FAMILIES else None     # the row's own state, not today's
            if wb is not None:                                 # addendum 217 item 4: its own line, never a PLAY cell
                w = would.setdefault(fam, _would())
                qb = qb_tagged(desk)
                counted = qb and count_446(fam, e[0], "would_be")    # 225 2(a): toward thirty BEFORE the checks
                if m is None:
                    w["not_in_db"] += 1
                    unscored_446(counted, fam, "would_be", NOT_IN_COPY)
                    continue
                h = m.home_team.name if m.home_team else None
                a = m.away_team.name if m.away_team else None
                if (row.get("home_team"), row.get("away_team")) != (h, a):
                    w["teams"] += 1
                    unscored_446(counted, fam, "would_be", TEAMS_DIFFER)
                    continue
                if lab:
                    w["void"].append(f"match {m.id} {a or '?'} @ {h or '?'}: {lab}")
                    unscored_446(counted, fam, "would_be", REDATED)
                    continue
                ex = desk.get("exec") if isinstance(desk.get("exec"), dict) else None
                edge = ex.get("edge_pp") if ex else None
                if edge is not None and ex.get("basis") != "taker":
                    w["basis"] += 1
                    unscored_446(counted, fam, "would_be", NON_TAKER)
                    continue
                w["exec"][cohort_of(edge)] += 1
                res = result_of(m, desk.get("pick"))
                c = w[QB_OUT if qb else QB_CLEAN]
                c["plays"] += 1
                c[{"win": "w", "loss": "l", "push": "p", "void": "void", "open": "open"}[res]] += 1
                if res != "open":
                    u = settle_units(wb.get("would_units"), res, ex.get("cost") if ex else None)
                    if u is None:
                        c["unpriced"] += 1
                    else:
                        c["units_sum"] += u
                        c["priced"] += 1
                continue
            if call != "PLAY":
                continue
            # #446's rows: a QB tag, whatever the exec cell, counted toward thirty BEFORE the checks (225 2(a))
            counted = fam in WOULD_BE_FAMILIES and qb_tagged(desk) and count_446(fam, e[0], "play")
            if m is None:
                out["not_in_db"] += 1
                unscored_446(counted, fam, "play", NOT_IN_COPY)
                continue
            h = m.home_team.name if m.home_team else None
            a = m.away_team.name if m.away_team else None
            if (row.get("home_team"), row.get("away_team")) != (h, a):
                out["teams"] += 1
                unscored_446(counted, fam, "play", TEAMS_DIFFER)
                continue
            if lab:
                out["void"].append(f"match {m.id} {a or '?'} @ {h or '?'}: {lab}")
                unscored_446(counted, fam, "play", REDATED)
                continue
            ex = desk.get("exec") if isinstance(desk.get("exec"), dict) else None
            edge = ex.get("edge_pp") if ex else None
            if edge is not None and ex.get("basis") != "taker":
                out["basis"] += 1
                unscored_446(counted, fam, "play", NON_TAKER)
                continue
            key = cohort_of(edge)
            tags = desk.get("tags") if isinstance(desk.get("tags"), list) else []
            if key == MID and {t for t in tags if isinstance(t, str)} & set(QB_TAGS):
                key = MID_QB
            res = result_of(m, desk.get("pick"))
            c = cells.setdefault((fam, key), _cell())
            c["plays"] += 1
            c[{"win": "w", "loss": "l", "push": "p", "void": "void", "open": "open"}[res]] += 1
            if key == MID and res in ("win", "loss"):            # the n=30 counter: from the pre-registration on
                run = e[0]
                pooled["undated" if run is None else "graded" if run >= COUNTED_FROM else "before"] += 1
            if res != "open":
                u = settle_units(desk.get("units"), res, ex.get("cost") if ex else None)
                if u is None:
                    c["unpriced"] += 1
                else:
                    c["units_sum"] += u
                    c["priced"] += 1
        s.rollback()
    return {"files": cr["files"], "unreadable": cr["unreadable"], "runs": cr["runs"], "families": sorted(fams),
            "cells": cells, "left_out": left, "floor_blocked": floor, "cohort_graded": pooled["graded"], "cohort_before": pooled["before"],
            "cohort_undated": pooled["undated"], "certification": cert,
            "model_version": nfl_model_version(), "would_be": would, "count_446": c446,
            "unscored_446": u446}


def _units_text(c: dict) -> str:
    if not c["priced"]:                      # nothing settled at a price: never a breakeven figure (law 4)
        return f"units — (unpriced {c['unpriced']})" if c["unpriced"] else "units —"
    return f"{c['units_sum']:+.2f}u" + (f" (unpriced {c['unpriced']})" if c["unpriced"] else "")


def _cell_line(fam: str, key: str, c: dict | None) -> str:
    head = f"- {fam} · {CELL_TEXT[key]}: PLAY "
    if not c or not c["plays"]:
        return head + "0"
    return (head + f"{c['plays']} · W-L-P {c['w']}-{c['l']}-{c['p']} · {_units_text(c)} · open {c['open']} · "
            f"void {c['void']}")


def _left_line(fam: str, out: dict) -> str:
    items = []
    if out["ladder"]:
        items.append(f"LADDER {out['ladder']} (no exec block by design)")
    if out["basis"]:
        items.append(f"exec basis not taker {out['basis']}")
    if out["not_in_db"]:
        items.append(f"not in this DB {out['not_in_db']}")
    if out["teams"]:
        items.append(f"teams differ {out['teams']}")
    if out["void"]:
        items.append(f"void: {void_counts(out['void'])}")
    return f"- {fam} · left out: " + (", ".join(items) if items else "none")


def _floor_line(fam: str, c: dict | None) -> str | None:
    """The floor-blocked line (#690) of a family with a probability floor (desk_policy.POLICY pMin > 0), printed
    whether or not a row qualifies: the floor is frozen and this line is its receipt. Notional at 1u (BASE_UNITS, the
    size a PASS row's desk.exec is priced at) at desk.exec.cost; never pooled with a PLAY cell."""
    p_min = (desk_policy.POLICY.get(fam) or desk_policy.POLICY["DEFAULT"]).get("pMin", 0) or 0
    if not p_min:
        return None
    head = (f"- {fam} · PASS by floor, exec >= 4 (#690: the pick's model p under the {p_min:.2f} probability floor, "
            f"exec >= 4 at the close; notional {desk_policy.BASE_UNITS}u at desk.exec.cost, never pooled; the floor is "
            "frozen and this line is its receipt): ")
    if not c or not (c["plays"] or c["not_in_db"] or c["teams"] or c["redated"]):
        return head + "0"
    lo = [f"{k} {c[v]}" for k, v in (("not in this DB", "not_in_db"), ("teams differ", "teams")) if c[v]]
    if c["redated"]:
        lo.append(f"void: {void_counts(c['redated'])}")
    return (head + f"{c['plays']} · W-L-P {c['w']}-{c['l']}-{c['p']} · {_units_text(c)} · open {c['open']} · "
            f"void {c['void']}" + (f" · left out: {', '.join(lo)}" if lo else ""))


def _would_be_line(fam: str, t: dict, absent: str | None = None) -> str | None:
    """THE WOULD-BE LINE (addendum 217 item 4) of a family the market-only rule holds, printed while its model is not
    read certified (0 when nothing qualifies: the measurement is running), and after that whenever a would-be row or a
    #446 row is there (the rows carry their own state; the registry's is the head's text only). #446's thirty-row count
    is its tail, the counted rows a check leaves out named beside it by cause (addendum 225 item 2(a)). `absent`: the
    cause named when the family has no closing file here (addendum 225 item 2(b): the zero line, never silence)."""
    cert = t.get("certification") or ("certified", "")
    if fam not in WOULD_BE_FAMILIES:
        return None
    w = (t.get("would_be") or {}).get(fam) or _would()
    k = {"play": 0, "would_be": 0, "before": 0, "undated": 0, **((t.get("count_446") or {}).get(fam) or {})}
    if cert[0] == "certified" and fam not in (t.get("would_be") or {}) and not any(k.values()):
        return None
    mv = t.get("model_version") or nfl_model_version()
    state = (f"while the registry reads {mv} uncertified ({cert[1]})" if cert[0] == "uncertified" else
             f"rows recorded while uncertified; the registry now reads {mv} certified ({cert[1]})"
             if cert[0] == "certified" else f"certification not read for {mv}: {cert[1]}")
    head = (f"- {fam} · {WOULD_BE} (addendum 217 item 4: the Desk's record-only would-be call, desk.market_only_hold, "
            f"{state}; notional at desk.exec.cost, never pooled with PLAY, never a position): ")
    n = w[QB_OUT]["plays"] + w[QB_CLEAN]["plays"]
    body = f"{n}" + (f" · {absent}" if absent else "")
    if n:
        def part(lab, c):
            if not c["plays"]:
                return f"{lab} 0"
            return (f"{lab} {c['plays']} · W-L-P {c['w']}-{c['l']}-{c['p']} · {_units_text(c)} · open {c['open']} · "
                    f"void {c['void']}")
        body += (f" · {part(QB_OUT, w[QB_OUT])} · {part(QB_CLEAN, w[QB_CLEAN])} · by exec: "
                 + " · ".join(f"{x} {w['exec'][x]}" for x in (GE4, MID, LE0, UNKNOWN)))
    lo = [f"{lab} {w[v]}" for lab, v in (("exec basis not taker", "basis"), ("not in this DB", "not_in_db"),
                                          ("teams differ", "teams")) if w[v]]
    if w["void"]:
        lo.append(f"void: {void_counts(w['void'])}")
    if lo:
        body += f" · left out: {', '.join(lo)}"
    tot = k["play"] + k["would_be"]
    tail = (f"n={READ_446_AT_N} reached — for the architect's read (no verdict is computed here)"
            if tot >= READ_446_AT_N else f"of {READ_446_AT_N}")
    body += (f" · #446's thirty-row count (addendum 44 item 9: rows with a QB flag or an unread list, "
             f"{HOLD_446_FROM_TEXT}): PLAY {k['play']} + {WOULD_BE} {k['would_be']} = {tot} {tail}"
             + _unscored_text((t.get("unscored_446") or {}).get(fam) or {})
             + (f" · before the hold, not counted {k['before']}" if k["before"] else "")
             + (f" · undated, not counted {k['undated']}" if k["undated"] else ""))
    return head + body


def _unscored_text(u: dict) -> str:
    """The rows counted toward thirty that a check left out of W-L-P, per kind, by cause (addendum 225 item 2(a))."""
    parts = [f"{lab}: " + ", ".join(f"{c} {u[kind][c]}" for c in CAUSES if u[kind].get(c))
             for kind, lab in (("play", "PLAY"), ("would_be", WOULD_BE)) if any((u.get(kind) or {}).values())]
    return f" · counted, not scored (outside the W-L-P): {'; '.join(parts)}" if parts else ""


NO_NFL_FILE = "no {fam} closing file in {d}/ on this machine"           # 225 2(b): the zero line's cause
NO_NFL_READABLE = "no readable {fam} closing file in {d}/ on this machine"


def _zero_lines(t: dict, d: str, have: set) -> list[str]:
    """THE ZERO LINE (ARCHITECT 2026-11-03 07:55 ET, addendum 225 item 2(b), RULING_225_2B): a would-be family with no
    closing file here, while the registry does not read its model certified (an unread read is never judged certified,
    law 4), prints its line at 0 with that cause named; certified, nothing."""
    cert = (t.get("certification") or ("certified", ""))[0]
    if cert == "certified":
        return []
    why = NO_NFL_READABLE if t.get("unreadable") else NO_NFL_FILE
    return [ln for fam in WOULD_BE_FAMILIES if fam not in have
            if (ln := _would_be_line(fam, t, why.format(fam=fam, d=d))) is not None]


LADDER_TEXT = ("LADDER, the ordered NO leg priced, ungraded (#689: desk.ladder_exec, notional, never pooled with "
               "PLAY; no call, units or floor reads it)")


def _ladder_line(fam: str, out: dict) -> str | None:
    """The priced-but-ungraded LADDER line (ARCHITECT 2026-10-26 12:05 ET, #689): the LADDER rows by the NO leg's
    exec edge (the same cells as a PLAY's, without the QB split), the mean edge, and the unpriced rows by why. No
    record and no units: the LADDER/NO read is the architect's (addendum 162 item 2(c))."""
    if not out["ladder"]:
        return None
    pr = out["ladder_priced"]
    n = len(out["ladder_edges"])
    cells = " · ".join(f"{k} {pr[k]}" for k in (GE4, MID, LE0))
    mean = f" · mean NO-leg exec edge {sum(out['ladder_edges']) / n:+.1f}pp" if n else ""
    un = ("; unpriced " + ", ".join(f"{w} {c}" for w, c in sorted(out["ladder_unpriced"].items()))
          if out["ladder_unpriced"] else "")
    return f"- {fam} · {LADDER_TEXT}: {out['ladder']} · priced {n}: {cells}{mean}{un}"


def _not_counted(before: int, undated: int) -> str:
    return f" · {BEFORE_TEXT} {before}" + (f" · not counted (no run start) {undated}" if undated else "")


def pooled_line(k: int, before: int = 0, undated: int = 0) -> str:
    """The n=30 line of the pre-registered cohort, every family on this machine (never across machines): the counter
    from the pre-registration on (R41 RULED), and beside it the graded rows it does not count."""
    head = f"- The pre-registered cohort, every family on this machine, {COUNTED_FROM_TEXT}: graded {k}"
    if k >= READ_AT_N:
        return (f"{head}: n={READ_AT_N} reached — for the architect's read (no verdict is computed here)"
                + _not_counted(before, undated))
    return f"{head} of {READ_AT_N} — not read before n=30" + _not_counted(before, undated)


HEADER = ("## EXEC COHORTS — PLAY calls by exec edge, per closing family (ARCHITECT 2026-10-20, addendum 146 item "
          "1(v))")


def _pooled(t: dict) -> str:
    return pooled_line(t["cohort_graded"], t.get("cohort_before", 0), t.get("cohort_undated", 0))


def section(t: dict, exports_dir) -> str:
    """The RESULTS.md section (the template of the PR's spec, word for word)."""
    d = str(exports_dir).rstrip("/")
    bad = (f"; unreadable {len(t['unreadable'])}: {', '.join(t['unreadable'])}" if t["unreadable"] else "")
    if not t["files"]:
        none = (f"No closing file in {d}/ on this machine." if not t["unreadable"] else
                f"No readable closing file in {d}/ on this machine{bad}.")
        zero = "".join(f"{z}\n" for z in _zero_lines(t, d, set()))           # 225 2(b): never silence
        return f"{HEADER}\n\n{none}\n\n{zero}{_pooled(t)}\n"
    runs = (f"runs {t['runs'][0]:%Y-%m-%d %H:%M}Z to {t['runs'][1]:%Y-%m-%d %H:%M}Z" if t["runs"] else "runs —")
    intro = (f"_Read-only, from this machine's closing files on disk ({d}/closing_*.json, every file, not the rolling "
             f"window; host/ is never read): {t['files']} files, {runs}{bad}. One PLAY row per game: the newest run's "
             "row within the hour of the game's current start. The cohort is desk.exec.edge_pp (the ask plus the taker "
             "fee, basis taker; exec >= 4 is the Desk's own exec_clears). Units are notional at desk.exec.cost: a hit "
             "wins units x (1/cost - 1), a miss loses the units, a push or a void 0. Never fills: the ledger holds "
             "those. The pre-registered 0 < exec < 4 cohort (QB inputs clean) is READ at n=30 graded (ARCHITECT "
             "2026-10-20, addendum 146 item 1(i)), never earlier._")
    out = [HEADER, "", intro, ""]
    for fam in t["families"]:
        lo = t["left_out"].get(fam) or _out()
        mine = {k: t["cells"].get((fam, k)) for k in CELLS}
        any_play = any(c and c["plays"] for c in mine.values()) or lo["basis"] or lo["not_in_db"] or lo["teams"] \
            or lo["void"]
        if not any_play:
            out.append(f"- {fam} · no PLAY call in its closing files")
        else:
            for k in CELLS:
                if k == MID_QB and not (mine[k] and mine[k]["plays"]):
                    continue                          # printed only when the QB half holds a PLAY
                out.append(_cell_line(fam, k, mine[k]))
        out.append(_left_line(fam, lo))
        if (ll := _ladder_line(fam, lo)) is not None:
            out.append(ll)
        if lo["void"]:
            out.append(f"- {fam} · void: {void_counts(lo['void'])}: " + "; ".join(lo["void"]))
        if (fl := _floor_line(fam, (t.get("floor_blocked") or {}).get(fam))) is not None:
            out.append(fl)
        if (wl := _would_be_line(fam, t)) is not None:
            out.append(wl)
    out.extend(_zero_lines(t, d, set(t["families"])))                  # 225 2(b): no NFL closing file here
    out.append(_pooled(t))
    return "\n".join(out) + "\n"


def console_line(t: dict) -> str:
    """The one console line results-tally reports."""
    k = t["cohort_graded"]
    tail = (f"n={READ_AT_N} reached — for the architect's read" if k >= READ_AT_N else "not read before n=30")
    return (f"exec cohorts ({t['files']} closing files on disk): the pre-registered 0 < exec < 4 cohort, "
            f"{COUNTED_FROM_TEXT}, graded {k} of {READ_AT_N} ({tail})"
            + _not_counted(t.get("cohort_before", 0), t.get("cohort_undated", 0)))
