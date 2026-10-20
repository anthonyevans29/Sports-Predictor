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
  left out, counted. PASS rows, quarantine shadows and value shadows are not calls.
- The cohort is desk.exec.edge_pp: exec >= 4 is the Desk's own exec_clears (4 less FEE_CLEAR_EPS); 0 < exec < 4 is
  e > 0 and not clears; exec <= 0 is e <= 0. A PLAY with no exec edge is "exec unknown", never guessed into a cohort;
  a basis other than taker is left out, counted. 0 < exec < 4 splits on the Desk's QB tags (QB_TAGS): QB inputs clean
  is the pre-registered cohort; a QB-flagged or unread row is outside it.
- Units are notional at desk.exec.cost (the cost edge_pp comes from): a hit wins units x (1/cost - 1), a miss loses the
  units, a push or a void 0. Never fills: the ledger holds those.
- Results from the DB: CANCELLED, POSTPONED and STALE_ORPHAN are void; FINISHED with both scores decides (a level
  two-way score is a push; a three-way board reads full_time_result, else the scores); anything else is open. A row
  whose teams are not the DB match's is left out (match ids are machine-local), as is a match id this DB lacks.
- Read-only: one session, nothing written; no verdict is computed (the n=30 read is the architect's).
- The n=30 counter starts at the rule (a reading for the architect, R41): it counts only the pre-registered cohort's
  graded rows whose closing run starts on or after 2026-10-18 00:00 ET (RULE_OF_1018); the earlier graded rows of the
  same cell print beside it, "not counted (before the rule of 2026-10-18)", and a row with no run start is not counted
  either (named when there is one). The per-family lines keep every row: they are the record.
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
# The n=30 counter's start, a reading for the architect (R41). 1(i) names the cohort as the one the rule of 2026-10-18
# pre-registers and reads it at n=30, never earlier (RULING_RULE_OF_1018, verbatim); addendum 136 item 5(iv): "The exec
# cohort "0 < exec < 4, half units" (the written rule of 10-18) is graded on its own from here". Built at the rule's
# date (2026-10-18 00:00 ET): only closing runs that start on or after it count toward n=30; 136 5(iv)'s later start
# would count fewer rows.
RULING_RULE_OF_1018 = ("The written exec-hold rule of 2026-10-18 stands verbatim: exec <= 0 -> no bet; 0 < exec < 4 -> "
                       "the Desk's half units stand when the QB inputs are clean, as the pre-registered cohort; it is "
                       "READ at n=30 graded (the same bar as the value shadows, #86), never earlier.")
RULE_OF_1018 = datetime(2026, 10, 18, tzinfo=ZoneInfo("America/New_York"))
COUNTED_FROM = as_utc(RULE_OF_1018)                   # 2026-10-18 04:00, naive UTC: the closing runs' own clock
COUNTED_FROM_TEXT = "closing runs from 2026-10-18 ET"
BEFORE_TEXT = "not counted (before the rule of 2026-10-18)"

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
    return {"ladder": 0, "basis": 0, "not_in_db": 0, "teams": 0, "void": []}


def _within(entries, current) -> list:
    """The entries whose recorded start is within the Desk's clock drift of the match's current start."""
    cur = as_utc(current)
    if cur is None:
        return []
    return [e for e in entries
            if (st := as_utc(e[2].get("utc_date"))) is not None and abs(cur - st) <= desk_policy.DESK_CLOCK_DRIFT]


def tally(exports_dir) -> dict:
    """The cohorts per closing family, from the closing files on disk and this machine's DB. Read-only: one session,
    rolled back. {"files", "unreadable", "runs", "families": [sorted], "cells": {(family, cell): counts}, "left_out":
    {family: counts}, "cohort_graded": W + L of the pre-registered cohort over every family, its rows whose closing run
    starts at or after COUNTED_FROM only (the n=30 counter), "cohort_before": its graded rows of earlier runs,
    "cohort_undated": its graded rows with no run start (neither is counted)}."""
    from src.db.database import session_scope
    from src.db.schema import Match

    cr = closing_rows(exports_dir)
    fams = set(cr.get("families") or ())
    cells: dict = {}
    left: dict = {}
    pooled = {"graded": 0, "before": 0, "undated": 0}
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
                continue
            if call != "PLAY":
                continue
            if m is None:
                out["not_in_db"] += 1
                continue
            h = m.home_team.name if m.home_team else None
            a = m.away_team.name if m.away_team else None
            if (row.get("home_team"), row.get("away_team")) != (h, a):
                out["teams"] += 1
                continue
            if lab:
                out["void"].append(f"match {m.id} {a or '?'} @ {h or '?'}: {lab}")
                continue
            ex = desk.get("exec") if isinstance(desk.get("exec"), dict) else None
            edge = ex.get("edge_pp") if ex else None
            if edge is not None and ex.get("basis") != "taker":
                out["basis"] += 1
                continue
            key = cohort_of(edge)
            tags = desk.get("tags") if isinstance(desk.get("tags"), list) else []
            if key == MID and {t for t in tags if isinstance(t, str)} & set(QB_TAGS):
                key = MID_QB
            res = result_of(m, desk.get("pick"))
            c = cells.setdefault((fam, key), _cell())
            c["plays"] += 1
            c[{"win": "w", "loss": "l", "push": "p", "void": "void", "open": "open"}[res]] += 1
            if key == MID and res in ("win", "loss"):                       # the n=30 counter: from the rule on
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
            "cells": cells, "left_out": left, "cohort_graded": pooled["graded"], "cohort_before": pooled["before"],
            "cohort_undated": pooled["undated"]}


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


def _not_counted(before: int, undated: int) -> str:
    return f" · {BEFORE_TEXT} {before}" + (f" · not counted (no run start) {undated}" if undated else "")


def pooled_line(k: int, before: int = 0, undated: int = 0) -> str:
    """The n=30 line of the pre-registered cohort, every family on this machine (never across machines): the counter
    from the rule of 2026-10-18 on, and beside it the graded rows it does not count (R41)."""
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
        return f"{HEADER}\n\n{none}\n\n{_pooled(t)}\n"
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
        if lo["void"]:
            out.append(f"- {fam} · void: {void_counts(lo['void'])}: " + "; ".join(lo["void"]))
    out.append(_pooled(t))
    return "\n".join(out) + "\n"


def console_line(t: dict) -> str:
    """The one console line results-tally reports."""
    k = t["cohort_graded"]
    tail = (f"n={READ_AT_N} reached — for the architect's read" if k >= READ_AT_N else "not read before n=30")
    return (f"exec cohorts ({t['files']} closing files on disk): the pre-registered 0 < exec < 4 cohort, "
            f"{COUNTED_FROM_TEXT}, graded {k} of {READ_AT_N} ({tail})"
            + _not_counted(t.get("cohort_before", 0), t.get("cohort_undated", 0)))
