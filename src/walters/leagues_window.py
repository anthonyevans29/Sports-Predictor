"""
THE COHORT READER FOR THE FOUR DOMESTIC LEAGUES (ARCHITECT 2026-10-30 09:30 ET, addendum 178, PR ORDER item 2: "The
cohort reader per R2–R4, R8."; lane leagues, #322). Read-only.

R1, verbatim: "THE RECOMPUTE DECIDES. The verdict at the 60th game is the as-of-kickoff walk recomputed at read time
with the frozen constants (soccer_elo_poisson as the run record holds it: v22, rho -0.1, coefficient 0.0008; trained
to 2025/26; nothing retuned), on results strictly before each fixture's kickoff — La Liga's confirmation_read
precedent. The stored prospective rows are the AUDIT RECEIPT where they exist: a stored row that differs from the
recompute on the same fixture is printed and counted as a finding, never silently resolved either way. So the
declaration does not wait on the export; the export (164 item 3) is still built, as the published record and the
Cockpit's shadow."
R2, verbatim: "BEFORE GAME 60 the reader prints counts only: members n of 60 since the declaration, exclusions by
cause, pending (scheduled, LIVE, un-ingested), rows present or missing; no running figure of either arm (law 3:
nothing is read before its pre-committed n). A counts-only reader IS "in hand" once its scoring path exists and is
test-pinned (the verdict at n = 60 is its function); it is merged before any league is declared."
R3, verbatim: "THE OPENING INSTANT is the declaration's recorded time: the addendum's ET timestamp as posted, written
into the registry entry as declared_at (UTC); a fixture counts only if its kickoff is strictly after that instant. A
date is never the instant."
R4, verbatim: "MEMBERSHIP: a member the candidate cannot price (below MIN_PRIOR, no strength) is EXCLUDED and counted
by cause, it does not consume a slot; a FINISHED game with no 90-minute result stays PENDING (the read waits for it);
AWD/WO: La Liga's ruled predicate carries over unchanged (addendum 16 item 1 Q2/C1); a LIVE or un-ingested game
before the 60th makes the read WAIT, never skip; a postponed or re-dated game is a member by its ACTUAL kickoff (if
the new kickoff is after the instant it counts when played; if it is cancelled it is excluded by cause)."
R8, verbatim: "FENCED: after a declaration the window's outcomes have one reader, the cohort reader; guards_backtest
refuses any other read of them until the verdict is recorded (the NCAA fence's precedent)."
ADDENDUM 181 (ARCHITECT 2026-10-30 11:00 ET), the six open points ruled; item heads, verbatim: "1. P1 — THE FENCE
FAILS OPEN UNTIL THE ENTRY LANDS: option (b), and the ordering rule beside it." "2. P2 — AWD/WO IN THE WALK: La Liga's
ONE predicate governs the whole path" "3. P2 — C1 AGAINST R4's PENDING: C1 wins for the no-raw-code row." "4. P2 — THE
FENCE'S SCOPE, the principle: the fence bars any FIGURE OF EITHER ARM on a window game" "5. P3 — THE AUDIT TOLERANCE: no
tolerance." "6. P3 — THE ENTRY IDS: ruled as proposed."
Item 5 (a LATER PR, not this one), verbatim: "The one read at each league's 60th: strict, unrounded, a tie rejects —
the bar is 155 item 4(b)'s (below the close's log-loss), not league_gate's."

- THE DECLARATION per league: the registry entry DECLARATION_IDS[code] (docs/registry/experiments.json, registry.get).
  The ids are ruled as proposed (addendum 181 item 6); no entry exists yet, so every league reads NOT DECLARED and
  prints only that. An entry carries `competition` (LEAGUE_FIELD: the league's code, as the DB's Competition.code and
  the shadow export's rows name it; an entry whose field is not the code it was looked up under is REFUSED, 181 item
  6), `declared_at` (R3: a UTC instant, "...Z" or "+00:00"; a bare date or an instant without its zone is refused)
  and `frozen_constants` {production_version, rho, elo_goal_coeff},
  which must equal the soccer-expansion-v1 RUN RECORD's (run.result: v22 / -0.1 / 0.0008), never the current
  production model's. Missing or different: REFUSED (exit 2). An entry whose `verdict` is set has its verdict
  recorded: the fence lifts.
- MEMBERSHIP (R3, R4; 155 item 4(b): "the first 60 FINISHED 2026/27 games per league with a three-way close, counted
  from the declaration"; 158 item 2(c): "Historical October games never enter the window"): the league's 2026/27
  rows (soccer_expansion.CURRENT_SEASON, the string paper and leagues_candidate read) in order of their ACTUAL stored
  kickoff, then id; only a kickoff strictly after declared_at. Each, in this order: stale orphan -> excluded (as the
  confirmation machinery releases it, soccer_expansion.stale_orphans); cancelled -> excluded; postponed (no new
  kickoff stored) -> NOT PLACED ("postponed: placed by its actual kickoff when stored"), never a member, never
  blocking; a stored round label placement() names a play-off -> excluded (F3, the candidate walks regular rounds
  only); LIVE -> PENDING; SCHEDULED with its kickoff at or before the read clock -> PENDING (un-ingested); SCHEDULED
  ahead -> to come; FINISHED under AWD / WO -> excluded (La Liga's predicate, soccer_expansion.AWARDED, addendum 16
  item 1 Q2); FINISHED FT, or with no raw code (C1; addendum 185), whose stored 90-minute score disagrees with its
  stored score (disagrees(); addendum 184 item 2: a data finding, never read as one figure or the other) -> PENDING ("score disagreement"), listed with both
  figures; FINISHED with no usable result (result_of: no scores stored, or a non-FT code such as AET / PEN with
  no 90-minute score; addendum 181 item 3) -> PENDING; then the
  three-way close as paper scores it (paper._guarded_three_way at the kickoff: mismatched legs, or UNPRICED's cause
  -> excluded by cause); then the candidate (leagues_candidate.predict_as_of on the finished rows strictly before
  the kickoff, the entry's frozen constants): below_min_prior / no_strength -> excluded by cause, no slot; else a
  MEMBER. Counting stops at the 60th member. A FINISHED row with no raw status code and both scores stored is a
  MEMBER scored on its stored score (C1 wins, addendum 181 item 3: it is not a non-FT row, its full-time score is its
  result) and is LISTED as C2 lists it (soccer_expansion.c2_line, walk_census's line: id, kickoff, teams, raw code,
  scores).
  A stage label the code cannot place REFUSES (F3, never guessed) when it kicks off at or before the 60th member, or
  while accruing at or before the read clock or the latest member (La Liga's unplaced_through rule).
- THE GAMES AT OR BEFORE THE INSTANT are never members, but every member's walk reads the regular-round ones (R1:
  "results strictly before each fixture's kickoff"): one not final (LIVE, SCHEDULED, or FINISHED, AWD / WO apart,
  with no score stored or no usable result) is PENDING (`before_instant`) and blocks, as R4's "a LIVE or un-ingested
  game before the 60th makes the read WAIT, never skip" reads; a regular-round FT or no-raw-code one whose scores disagree is
  PENDING under its own cause and listed (addendum 184 item 2); a POSTPONED one is counted apart (it can enter by its
  actual kickoff, R4); the rest are final, never in the window (an AWD / WO row among them is final whatever its row
  stores, 181 item 2).
- THE ONE PREDICATE (addendum 181 item 2: soccer_expansion.unscoreable, La Liga's): a game finished under AWD or WO
  is neither scored nor walked (no Elo or prior update, whatever scores its row carries); a non-FT row with a stored
  90-minute score is walked and scored on the 90-minute score; a no-raw-code row is walked and scored as the gate
  walks it (C1). predict_as_of applies it to its priors (leagues_candidate: soccer_backtest._confirmation_rows, the
  confirmation walk's own), score() applies it, and the parity's gate path is the confirmation walk with it
  (run_soccer_backtest confirmation_scoring=True). The AWD / WO rows the members' walk releases are counted and
  listed (`awarded_released`), a row with no stored score included.
- THE STATE: "ready" with 60 members and nothing pending or to come before the 60th; "waiting" with 60 members and a
  PENDING (or to-come) game before the 60th (R4: the read WAITS, never skips); else "accruing".
- THE SCORING PATH (R1; item 5's PR calls it, this PR's CLI never does): score(window) recomputes every member at
  read time (predict_as_of at the frozen constants; the close by paper's own rule; the 90-minute outcome) and returns
  both arms' mean log-loss, unrounded, on the same 60, with verdict_of's PASS only when the candidate's is strictly
  below the close's (a tie REJECTS), and the AUDIT of the stored prospective rows (stored_rows; none exist until the
  export PR: "no stored rows").
- THE FENCE (R8; addendum 181 items 1(b) and 4): fence_cutoff / fence_refusal. For every league of DECLARATION_IDS
  whose verdict is not recorded, its 2026/27 games kicking off after the cut are fenced from every other reader. The
  cut is the entry's declared_at; with NO entry it is PRE_DECLARATION_CUT (2026-10-30T15:00:00Z, addendum 181's
  posted instant: the pre-declaration fence, 181 item 1(b)), so no machine running this code can score a window game,
  with or without the entry. soccer_expansion.guards_backtest refuses a walk that would read them (soccer-backtest,
  run_soccer_backtest's callers including the rho / coefficient sweeps, backtest.run_backtest), and the receipts that
  can be cut (paper.leagues_season, paper.close_record, leagues_candidate.parity, soccer_expansion.shadow_grade) read
  only the games at or before the cut and count the rest as fenced. A recorded verdict lifts it. The fence bars any
  figure of either arm on a window game, never reading a result as data (181 item 4: production training,
  soccer-refresh, price_upcoming, the web views, resync-diff, compression_probe and preflight are not fenced).
The reader prints COUNTS ONLY (R2): no log-loss, probability, hit or any running figure of either arm, before n = 60
or (in this PR) at it.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from src.walters.paper import LEAGUES, MISMATCHED, UNPRICED, WINDOW_GAMES
from src.walters.soccer_expansion import (AWARDED, CURRENT_SEASON, MIN_PRIOR, ExpansionRefused, c2_line,
                                          is_regular, placement)

ADDENDUM = "ARCHITECT 2026-10-30 09:30 ET, addendum 178"
SEASON = CURRENT_SEASON                       # "2026/27", as paper.leagues_season and leagues_candidate read it
# Ruled as proposed (addendum 181 item 6): the declaration-records PR pins each entry's id to this; none exists yet.
DECLARATION_IDS = {"SA": "leagues-sa-v1", "BL1": "leagues-bl1-v1", "FL1": "leagues-fl1-v1", "ELC": "leagues-elc-v1"}
LEAGUE_FIELD = "competition"                  # the entry's league field (181 item 6: equal to the code looked up)
# Addendum 181 item 1(b): the pre-declaration fence's cut, the addendum's posted instant (11:00 ET), naive UTC as the
# matches table and parse_instant read it. A UTC instant in code, never a date.
PRE_DECLARATION_CUT = datetime(2026, 10, 30, 15, 0)
PRE_DECLARATION_RULING = ("ARCHITECT 2026-10-30 11:00 ET, addendum 181 item 1(b), verbatim: \"A PRE-DECLARATION FENCE "
                          "from this PR's merge: for every league in DECLARATION_IDS with NO entry, the fence stands "
                          "exactly as it does for a declared league, cut at the constant PRE_DECLARATION_CUT = "
                          "2026-10-30T15:00:00Z\"")
CONSTANTS_FIELD = "frozen_constants"
CONSTANTS = ("production_version", "rho", "elo_goal_coeff")
READER = "scripts/leagues_window.py (the cohort reader, src/walters/leagues_window.py)"
EXPORT_PREFIX = "soccer_expansion_shadow_"    # soccer_expansion.FILE_PREFIX: where the export PR's rows will be read
FENCE_RULING = (f"{ADDENDUM} R8, verbatim: \"FENCED: after a declaration the window's outcomes have one reader, the "
                "cohort reader; guards_backtest refuses any other read of them until the verdict is recorded (the NCAA "
                "fence's precedent).\"")

EXCLUDED = (("stale_orphan", "stale orphan (never a fixture; released as the confirmation machinery releases it)"),
            ("cancelled", "cancelled"),
            ("not_regular", "a play-off round (F3: the candidate walks regular rounds only)"),
            ("awarded", "AWD / WO (La Liga's predicate, addendum 16 item 1 Q2: decided off the pitch)"),
            (MISMATCHED, "mismatched legs (no close formed from two events)"),
            ("unpriced_incomplete", "no close: last capture incomplete"),
            ("unpriced_cap", "no close: last capture over the cap"),
            ("unpriced_none", "no close: no capture"),
            ("unpriced_other", "no close: last capture fails the close's other checks"),
            ("below_min_prior", f"the candidate cannot price it: below MIN_PRIOR ({MIN_PRIOR})"),
            ("no_strength", "the candidate cannot price it: a team with no strength"))
PENDING = (("scheduled", "scheduled"),                    # R2's list: "pending (scheduled, LIVE, un-ingested)"
           ("live", "LIVE"),
           ("uningested", "un-ingested (scheduled, kickoff past at the read clock)"),
           ("no_result_90", "finished, no usable result (no score stored, or a non-FT code with no 90-minute "
                            "score: the read waits for ingestion; one that never fills is a finding at the read)"),
           ("before_instant", "kicking off at or before the instant, not final (LIVE, un-ingested or no score "
                              "stored: every member's walk reads it once final)"),
           ("score_disagreement", "score disagreement (an FT or no-raw-code row whose stored 90-minute score differs "
                                  "from its stored score: a data finding, addendum 184 item 2 and 185, listed below "
                                  "with both figures)"))
NOT_PLACED = "postponed: placed by its actual kickoff when stored"
assert {k for k, _ in UNPRICED} <= {k for k, _ in EXCLUDED}


class WindowRefused(ExpansionRefused):
    """A refusal of the cohort reader (exit 2): never a window, never a guess."""


# ------------------------------------------------------------------------------------------- the registry --

def _ledger() -> str:
    from src.walters import soccer_expansion as sx
    return sx._reg_paths()[0]                 # read at call time (tests point the registry at tmp paths)


def declaration(code: str) -> dict | None:
    """The league's declaration entry, or None (NOT DECLARED). An entry counts only under its own id."""
    from src.walters import registry as reg
    eid = DECLARATION_IDS.get((code or "").strip().upper())
    if eid is None:
        return None
    e = reg.get(eid, _ledger())
    return e if isinstance(e, dict) and e.get("id") == eid else None


def parse_instant(v) -> datetime | None:
    """R3's instant: an ISO time stated in UTC ("...Z" or "+00:00"), as naive UTC (the matches table's clock). None
    for anything else: a date, an instant without its zone, another offset (a date is never the instant)."""
    if not isinstance(v, str) or "T" not in v:
        return None
    try:
        t = datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None or t.utcoffset() != timezone.utc.utcoffset(None):
        return None
    return t.replace(tzinfo=None)


def verdict_recorded(e: dict | None) -> bool:
    return bool(e and e.get("verdict"))


def run_record_constants() -> dict:
    """{production_version, rho, elo_goal_coeff} as the soccer-expansion-v1 run record holds them (R1: "soccer_elo_
    poisson as the run record holds it"); never the current production model. Refused when the record lacks them."""
    from src.walters import registry as reg
    from src.walters import soccer_expansion as sx
    e = reg.get(sx.EID, _ledger())
    res = ((e or {}).get("run") or {}).get("result") or {}
    if any(res.get(k) is None for k in CONSTANTS):
        raise WindowRefused(f"{sx.EID} has no run record holding {', '.join(CONSTANTS)}: the frozen constants are "
                            "unknown (R1), nothing is read")
    try:
        return {"production_version": str(res["production_version"]), "rho": float(res["rho"]),
                "elo_goal_coeff": float(res["elo_goal_coeff"])}
    except (TypeError, ValueError):                       # Codex on #733: refused, never a traceback
        raise WindowRefused(f"{sx.EID}'s run record holds constants that are not numbers "
                            f"({ {k: res.get(k) for k in CONSTANTS}!r}): the frozen constants are unknown (R1)")


def surviving() -> list[str]:
    """The soccer-expansion-v1 run record's surviving set (PD): its confirmation machinery reads those leagues'
    results outside this reader, so a window is never declared on one of them (Codex on #733)."""
    from src.walters import registry as reg
    from src.walters import soccer_expansion as sx
    e = reg.get(sx.EID, _ledger())
    surv = ((e or {}).get("run") or {}).get("result", {}).get("surviving") if isinstance(e, dict) else None
    return list(surv or [])


def checked(code: str, e: dict) -> tuple[datetime, dict]:
    """(declared_at, constants) of a declaration, or WindowRefused: its LEAGUE_FIELD is not `code` (181 item 6), no
    UTC declared_at (R3), constants missing, or constants that differ from the run record's (R1: nothing retuned)."""
    eid = e.get("id")
    if e.get(LEAGUE_FIELD) != code:                       # addendum 181 item 6: never read under another league's id
        raise WindowRefused(f"{code} ({eid}): the entry's {LEAGUE_FIELD} is {e.get(LEAGUE_FIELD)!r}, not {code!r}, "
                            "the league it was looked up under (ARCHITECT 2026-10-30, addendum 181 item 6)")
    at = parse_instant(e.get("declared_at"))
    if at is None:
        raise WindowRefused(f"{code} ({eid}): no declared_at as a UTC instant (stored {e.get('declared_at')!r}); R3: "
                            "the opening instant is the declaration's recorded time, a date is never the instant")
    if code in surviving():
        raise WindowRefused(f"{code} ({eid}): {code} is in the soccer-expansion-v1 surviving set, whose confirmation "
                            "reads its results outside the cohort reader; a window is never declared on it (R8)")
    got = e.get(CONSTANTS_FIELD)
    if not isinstance(got, dict) or any(got.get(k) is None for k in CONSTANTS):
        raise WindowRefused(f"{code} ({eid}): the entry holds no {CONSTANTS_FIELD} {{{', '.join(CONSTANTS)}}}; R1: "
                            "the frozen constants are the run record's")
    if isinstance(got, dict) and set(got) != set(CONSTANTS):   # Codex on #733: an extra key is never dropped
        raise WindowRefused(f"{code} ({eid}): {CONSTANTS_FIELD} holds the keys {sorted(got)!r}, not exactly "
                            f"{list(CONSTANTS)!r}; R1: the frozen constants are the run record's, nothing beside them")
    want = run_record_constants()
    try:
        mine = {"production_version": str(got["production_version"]), "rho": float(got["rho"]),
                "elo_goal_coeff": float(got["elo_goal_coeff"])}
    except (TypeError, ValueError):
        mine = None
    if mine != want:
        raise WindowRefused(f"{code} ({eid}): {CONSTANTS_FIELD} {got!r} differ from the soccer-expansion-v1 run "
                            f"record's {want!r}; R1: nothing retuned")
    return at, mine


# ---------------------------------------------------------------------------------------------- the fence --

def fence_cutoff(code, season=None) -> datetime | None:
    """R8 and addendum 181 item 1(b): the instant after which `code`'s 2026/27 games are the cohort reader's alone, or
    None (no fence). Fenced: a league of DECLARATION_IDS whose verdict is not recorded, and `season` 2026/27 or unnamed
    (every season). The cut is the entry's declared_at; with NO entry it is PRE_DECLARATION_CUT (the pre-declaration
    fence: a game between the two was never a window game). A declaration whose declared_at cannot be read fences
    the whole season (datetime.min; law 4). Every other competition (PL, PD, ...) is never fenced here."""
    c = (code or "").strip().upper()
    if c not in DECLARATION_IDS:
        return None
    s_ = "" if season is None else str(season).strip()
    if s_ not in ("", SEASON):
        return None
    e = declaration(c)
    if e is None:
        return PRE_DECLARATION_CUT
    if verdict_recorded(e):
        return None
    return parse_instant(e.get("declared_at")) or datetime.min


def fence_refusal(code, season=None, through: datetime | None = None) -> str | None:
    """The refusal text for a read of `code`/`season` that the fence covers, None = allowed. A read cut at `through`
    (it reads no game kicking off after it) is allowed when `through` is at or before the instant."""
    cut = fence_cutoff(code, season)
    if cut is None or (through is not None and through <= cut):
        return None
    c = (code or "").strip().upper()
    if declaration(c) is None:
        return (f"{c} {SEASON} is not declared yet (no entry {DECLARATION_IDS[c]}): the pre-declaration fence stands, "
                f"cut at {cut:%Y-%m-%dT%H:%M:%SZ}; a walk is allowed only when cut at or before it. The window's "
                f"outcomes have one reader, {READER}. {PRE_DECLARATION_RULING}. {FENCE_RULING}")
    at = "an unreadable declared_at: the whole season" if cut == datetime.min else f"{cut:%Y-%m-%dT%H:%M:%SZ}"
    return (f"{c} {SEASON} is declared ({DECLARATION_IDS[c]}, declared_at {at}) and its verdict is not recorded: the "
            f"window's outcomes have one reader, {READER}. {FENCE_RULING}")


def fenced(cut: datetime | None, m) -> bool:
    """A game a cut reader leaves out: a fence is up and the game is of 2026/27 kicking off after the cut (the
    entry's declared_at, or PRE_DECLARATION_CUT with no entry)."""
    return cut is not None and str(getattr(m, "season", "")) == SEASON and m.utc_date is not None and m.utc_date > cut


# ----------------------------------------------------------------------------------------- stored rows --

def stored_rows(code: str, declared_at: str | None, export_dir: str = "exports") -> dict[int, dict]:
    """R1's audit receipt: {match_id: the LAST stored prospective row before its kickoff} from the shadow export's
    files (exports/soccer_expansion_shadow_*.json), only rows of `code` labelled with the league's declared_at (R5:
    "after it, predict_as_of rows labelled with the league's declared_at"). The export that writes them is a later
    PR (164 item 3); today no row carries the label, so this is {} ("no stored rows"). Rows of the current shadow
    (price_upcoming's arithmetic, unlabelled) are never read as the candidate's."""
    out: dict[int, dict] = {}
    if not declared_at:
        return out
    for f in sorted(Path(export_dir).glob(f"{EXPORT_PREFIX}*.json")):
        try:
            doc = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        at = doc.get("exported_at") or ""
        for r in doc.get("predictions") or []:
            mid, ko = r.get("match_id"), r.get("utc_date") or ""
            if (mid is None or r.get("competition") != code or r.get("declared_at") != declared_at or not at
                    or at >= ko):
                continue
            if mid not in out or at >= out[mid]["exported_at"]:
                out[mid] = {**r, "exported_at": at}
    return out


def _stored_probs(row: dict) -> tuple[float, float, float] | None:
    p = row.get("prediction") or {}
    try:
        return float(p["home_win_prob"]), float(p["draw_prob"]), float(p["away_win_prob"])
    except (KeyError, TypeError, ValueError):
        return None


# ----------------------------------------------------------------------------------------- membership --

def _status(m) -> str:
    return str(getattr(m.status, "value", m.status) or "").lower()


def _raw(m) -> str:
    return (m.status_raw or "").strip().upper()


def result_of(m) -> str | None:
    """A FINISHED row's three-way result, derived from THE ONE predicate itself (soccer_expansion.unscoreable;
    addendum 181 items 2 and 3) and read on the raw code as the predicate reads it (stripped, upper-cased), or None
    (no usable result: PENDING, or released when AWD / WO):
    - unscoreable (AWD / WO whatever scores the row carries, Q2; a non-FT code such as AET / PEN with no 90-minute
      score): None;
    - a raw code with both 90-minute scores stored: the 90-minute score (a non-FT row is walked and scored on it;
      intl_shadow.result_90's first basis for an FT row, as paper reads it);
    - otherwise ('' / 'FT' by the predicate) both stored scores: the stored score (C1: a no-raw-code row is not a
      non-FT row, its full-time score is its result; the walk reads that very score);
    - no score stored: None."""
    from src.walters.soccer_expansion import unscoreable
    if unscoreable(m, "finished"):
        return None
    if _raw(m) and m.home_score_90 is not None and m.away_score_90 is not None:
        hg, ag = m.home_score_90, m.away_score_90
    elif m.home_score is not None and m.away_score is not None:
        hg, ag = m.home_score, m.away_score
    else:
        return None
    return "H" if hg > ag else ("A" if hg < ag else "D")


def disagrees(m) -> bool:
    """ARCHITECT 2026-10-30 12:00 ET, addendum 184 item 2 (#736), verbatim: "an FT row's stored score is its
    90-minute score by definition. An FT row whose stored 90-minute score DISAGREES with its stored score is a data
    finding: PENDING under its own cause ("score disagreement"), listed with both figures, never silently one or the
    other." Addendum 185 (#737, reading 1 ruled, verbatim): "widen it. By C1 a no-raw-code row is an FT row, so a
    disagreement on it is the same data finding: `_raw(m) not in ("", "FT")`, PENDING under the same cause, listed
    with both figures". True for a raw FT row or one with no raw code (as the predicate reads the code) with both
    scores and both 90-minute scores stored
    and the two pairs differing; a 90-minute score not stored is no disagreement."""
    if _raw(m) not in ("", "FT") or None in (m.home_score, m.away_score, m.home_score_90, m.away_score_90):
        return False
    return (m.home_score, m.away_score) != (m.home_score_90, m.away_score_90)


def membership(s, code: str, declared_at: datetime, constants: dict, now: datetime) -> dict:
    """The window of one declared league as of `now` (the module docstring's order). Counts and ids only: the
    probabilities predict_as_of returns are discarded here and recomputed by score() at the read (R1)."""
    from sqlalchemy import select

    from src.db.schema import Competition, Match
    from src.walters import kalshi_legs
    from src.walters import leagues_candidate as lc
    from src.walters import paper

    games = list(s.execute(select(Match).join(Competition, Competition.id == Match.competition_id)
                           .where(Competition.code == code, Match.season == SEASON)
                           .order_by(Match.utc_date, Match.id)).scalars())
    after = [m for m in games if m.utc_date is not None and m.utc_date > declared_at]
    fin = [m for m in after if _status(m) == "finished"]
    ids = [m.id for m in fin]
    snaps = paper._kalshi_snaps(s, ids)
    mism = kalshi_legs.mismatched(s, ids) if ids else {}
    tickers, current, homes = paper._three_way_guards(s, ids, snaps)
    rows = lc._season_rows(s, code, SEASON)
    out = {"code": code, "season": SEASON, "declared_at": declared_at, "constants": dict(constants),
           "stored_games": len(games), "at_or_before": 0, "postponed_before": 0, "members": [],
           "excluded": Counter(), "pending": Counter(), "to_come": 0, "not_placed": 0, "blocking": 0,
           "awarded_released": [], "no_raw_code_members": [], "score_disagreement": [], "disagreement_before": 0}
    for m in games:
        if m.utc_date is not None and m.utc_date > declared_at:
            continue
        st = _status(m)
        if st == "postponed":        # it can still enter the window by its actual kickoff once re-dated (R4)
            out["postponed_before"] += 1
        elif is_regular(m.stage) and st == "finished" and disagrees(m):
            out["pending"]["score_disagreement"] += 1   # 184 item 2: every member's walk reads it, so the read waits
            out["disagreement_before"] += 1           # the instant's tally names it (the line still adds up)
            out["blocking"] += 1
            out["score_disagreement"].append(m)
        elif is_regular(m.stage) and (st in ("live", "scheduled") or (
                st == "finished" and _raw(m) not in AWARDED       # 181 item 2: AWD / WO is final and released first,
                and (m.home_score is None or m.away_score is None   # whatever its row stores; no score stored, or
                     or result_of(m) is None))):                    # an AET/PEN prior without its 90', waits
            out["pending"]["before_instant"] += 1    # not final: every member's walk reads it once final (R1, R4)
            out["blocking"] += 1
        else:
            out["at_or_before"] += 1                 # final (or never walked): never in the window
    for m in after:
        if len(out["members"]) >= WINDOW_GAMES:
            break                    # counting stops at the 60th member
        st = _status(m)
        if st == "stale_orphan":
            out["excluded"]["stale_orphan"] += 1
            continue
        if st == "cancelled":
            out["excluded"]["cancelled"] += 1
            continue
        if st == "postponed":
            out["not_placed"] += 1   # no new kickoff stored: never a member, never blocking
            continue
        if placement(m.stage) == "playoff":
            out["excluded"]["not_regular"] += 1
            continue
        if st == "live":
            out["pending"]["live"] += 1
            out["blocking"] += 1
            continue
        if st != "finished":         # scheduled
            if m.utc_date <= now:
                out["pending"]["uningested"] += 1
            else:
                out["to_come"] += 1
            out["blocking"] += 1
            continue
        if _raw(m) in AWARDED:
            out["excluded"]["awarded"] += 1
            continue
        if disagrees(m):             # 184 item 2: a data finding, before any slot or cause: never one figure or the other
            out["pending"]["score_disagreement"] += 1
            out["blocking"] += 1
            out["score_disagreement"].append(m)
            continue
        if result_of(m) is None:     # 181 item 3: no score stored, or a non-FT code with no 90' score: R4's PENDING
            out["pending"]["no_result_90"] += 1
            out["blocking"] += 1
            continue
        cl, why = paper._guarded_three_way(m, snaps.get(m.id, []), m.utc_date, mism, tickers, homes,
                                           current.get(m.id))
        if cl is None:
            out["excluded"][why] += 1
            continue
        pred, why = lc.predict_as_of(rows, m, constants["rho"], constants["elo_goal_coeff"])
        if pred is None:
            out["excluded"][why] += 1
            continue
        out["members"].append(m.id)
        if not _raw(m):              # 181 item 3: C1's member, scored on its stored score and listed as C2 lists it
            out["no_raw_code_members"].append(m)
    n = len(out["members"])
    mine = set(out["members"])
    last_ko = max((m.utc_date for m in after if m.id in mine), default=None)
    # F3 (never guessed), as La Liga's unplaced_through reads it: a label the code cannot place refuses when it kicks
    # off at or before the 60th member, or while accruing at or before the read clock or the latest member: any one
    # could belong before a member. A label further ahead is read when the window reaches it.
    cut = last_ko if n >= WINDOW_GAMES else max(now, last_ko or now)
    bad = [f"{code} {SEASON} {m.id} {m.stage!r} "
           + (f"{m.utc_date:%Y-%m-%dT%H:%MZ}" if m.utc_date is not None else "no kickoff")
           for m in games if _status(m) not in ("stale_orphan", "cancelled", "postponed")   # never a slot
           and placement(m.stage) is None
           and (m.utc_date is None or m.utc_date <= cut)]
    if bad:
        raise WindowRefused(f"{code}: stage / round labels the code cannot place, kicking off at or before "
                            f"{'the 60th member' if n >= WINDOW_GAMES else 'the read clock'} (F3; never guessed): "
                            + "; ".join(bad))
    # 181 item 2: the one predicate releases every FINISHED regular-round AWD / WO row from every member's walk,
    # with or without a stored score (the season's rows, not the walk's, which hold only scored rows).
    released = ([m for m in games if _status(m) == "finished" and is_regular(m.stage) and m.utc_date is not None
                 and m.utc_date < last_ko and _raw(m) in AWARDED] if last_ko is not None else [])
    if released or out["no_raw_code_members"] or out["score_disagreement"]:
        from src.db.schema import Team
        both = released + out["no_raw_code_members"] + out["score_disagreement"]
        names = {t.id: t.name for t in s.execute(select(Team).where(Team.id.in_(
            {m.home_team_id for m in both} | {m.away_team_id for m in both}))).scalars()}
        out["awarded_released"] = [c2_line(m, names) for m in released]
        out["no_raw_code_members"] = [c2_line(m, names) for m in out["no_raw_code_members"]]
        out["score_disagreement"] = [c2_line(m, names) for m in out["score_disagreement"]]   # both figures (184 item 2)
    out["n"] = n
    out["state"] = ("accruing" if n < WINDOW_GAMES else "waiting" if out["blocking"] else "ready")
    return out


def read(codes=LEAGUES, now: datetime | None = None, export_dir: str = "exports") -> dict:
    """{code: window | {"declared": False} | {"refused": why}} for each league. Read-only: one mode=ro session per
    league (src.db.database.readonly_scope: no connect hook, no commit, a missing file refused, never created). Never
    scores (R2)."""
    from src.db.database import ReadOnlyRefused, readonly_scope
    from src.timeutil import utc_now_naive
    now = now or utc_now_naive()
    out: dict = {}
    for code in codes:
        e = declaration(code)
        if e is None:
            out[code] = {"code": code, "declared": False, "id": DECLARATION_IDS[code]}
            continue
        try:
            at, constants = checked(code, e)
            with readonly_scope() as s:
                w = membership(s, code, at, constants, now)
        except (WindowRefused, ReadOnlyRefused) as err:
            out[code] = {"code": code, "declared": True, "id": e["id"], "refused": str(err)}
            continue
        stored = stored_rows(code, e.get("declared_at"), export_dir)
        w.update({"declared": True, "id": e["id"], "declared_at_text": e.get("declared_at"),
                  "verdict_recorded": verdict_recorded(e),
                  "stored_present": sum(1 for i in w["members"] if i in stored),
                  "stored_missing": sum(1 for i in w["members"] if i not in stored)})
        out[code] = w
    return out


# ------------------------------------------------------------------------------------- the scoring path --

def verdict_of(ll_candidate: float, ll_close: float) -> str:
    """155 item 4(b)'s bar as item 5 states it: "strict, unrounded, a tie rejects". PASS only when the candidate's
    mean log-loss is strictly below the close's on the same games."""
    return "PASS" if ll_candidate < ll_close else "REJECT"


def aggregate(pairs) -> dict:
    """[(p the candidate gave the 90-minute outcome, p the close gave it)] -> both means (vs_close.log_loss, one
    floor for both arms), unrounded, and verdict_of. Pure."""
    from src.walters.vs_close import log_loss
    pairs = list(pairs)
    n = len(pairs)
    if not n:
        raise WindowRefused("no member to score")
    ll_c = sum(log_loss(a) for a, _ in pairs) / n
    ll_k = sum(log_loss(b) for _, b in pairs) / n
    return {"n": n, "ll_candidate": ll_c, "ll_close": ll_k, "verdict": verdict_of(ll_c, ll_k)}


def audit(stored: dict[int, dict], recomputed: dict[int, tuple[float, float, float]]) -> dict:
    """R1's audit: each member's stored prospective row against the recompute on the same fixture. No tolerance
    (addendum 181 item 5): the recompute ROUNDED BY THE EXPORT'S OWN FUNCTION (soccer_expansion.shadow_prob, the one
    shadow_row writes with) is compared to the stored value; not equal is a finding, counted and listed, never
    resolved either way. Pure."""
    from src.walters.soccer_expansion import shadow_prob
    present = [i for i in recomputed if i in stored]
    out = {"present": len(present), "missing": len(recomputed) - len(present), "differ": [], "unreadable": []}
    for i in present:
        sp = _stored_probs(stored[i])
        if sp is None:
            out["unreadable"].append(i)
            continue
        rounded = tuple(shadow_prob(x) for x in recomputed[i])
        if sp != rounded:
            d = max(abs(a - b) for a, b in zip(sp, recomputed[i]))
            out["differ"].append({"match_id": i, "stored": sp, "recomputed": recomputed[i], "rounded": rounded,
                                  "diff": d})
    return out


def audit_lines(code: str, a: dict) -> list[str]:
    if not a["present"]:
        head = f"  - {code} · stored prospective rows: none (no stored rows; {a['missing']} members without one)"
    else:
        head = (f"  - {code} · stored prospective rows: present {a['present']} · missing {a['missing']} · "
                f"differ from the recompute {len(a['differ'])} (FINDINGS, R1: never resolved either way)"
                + (f" · unreadable {len(a['unreadable'])}" if a["unreadable"] else ""))
    L = [head]
    for f in a["differ"]:
        L.append(f"    FINDING match {f['match_id']} · stored " + "/".join(f"{x:.4f}" for x in f["stored"])
                 + " · recomputed " + "/".join(f"{x:.6f}" for x in f["recomputed"]) + " (rounded by the export's "
                 "function " + "/".join(f"{x:.4f}" for x in f["rounded"]) + f") · |diff| {f['diff']:.2g}")
    return L


def score(window: dict, export_dir: str = "exports", now: datetime | None = None) -> dict:
    """THE SCORING PATH (R1), for item 5's PR: refused unless the window is "ready" (60 members, nothing pending
    before the 60th). Every member is recomputed at read time: predict_as_of on the finished rows strictly before
    its kickoff at the frozen constants; the close by paper's own rule (_guarded_three_way at the kickoff); the
    outcome by the one predicate (result_of: the 90-minute score; C1's no-raw-code member on its stored score;
    addendum 181 items 2 and 3). A member that no longer prices, closes or has a result refuses (the window moved
    under the read: a finding, never silently dropped). Returns aggregate()'s figures and verdict on the 60, plus the audit of the stored rows. Read-only: one mode=ro session (readonly_scope)."""
    from src.db.database import readonly_scope
    from src.db.schema import Match
    from src.walters import kalshi_legs
    from src.walters import leagues_candidate as lc
    from src.walters import paper
    from src.walters.intl_shadow import OUTCOME_SIDE

    if window.get("state") != "ready" or len(window.get("members") or ()) != WINDOW_GAMES:
        raise WindowRefused(f"{window.get('code')}: the one read is at the {WINDOW_GAMES}th member with nothing "
                            f"pending before it (state {window.get('state')!r}, members "
                            f"{len(window.get('members') or ())})")
    from src.timeutil import utc_now_naive
    code, ids, c = window["code"], list(window["members"]), window["constants"]
    key = {"H": 0, "D": 1, "A": 2}
    pairs, recomputed, problems = [], {}, []
    with readonly_scope() as s:
        # Codex on #733: the cohort is re-derived in THIS transaction; a fixture, result or close ingested since the
        # read could put another game before the 60th, so the ids and the state must match the read's or nothing
        # is scored (never games 2-61 for 1-60).
        fresh = membership(s, code, window["declared_at"], c, now or utc_now_naive())
        if fresh["state"] != "ready" or fresh["members"] != ids:
            raise WindowRefused(f"{code}: the window moved between the read and the score (state "
                                f"{fresh['state']!r}; members {'unchanged' if fresh['members'] == ids else 'changed'}"
                                "): read it again; nothing is scored")
        rows = lc._season_rows(s, code, SEASON)
        snaps = paper._kalshi_snaps(s, ids)
        mism = kalshi_legs.mismatched(s, ids)
        tickers, current, homes = paper._three_way_guards(s, ids, snaps)
        for i in ids:
            m = s.get(Match, i)
            res = result_of(m) if m is not None and _status(m) == "finished" else None
            pred, why = lc.predict_as_of(rows, m, c["rho"], c["elo_goal_coeff"]) if m is not None else (None, "gone")
            cl, cwhy = (paper._guarded_three_way(m, snaps.get(i, []), m.utc_date, mism, tickers, homes,
                                                 current.get(i)) if m is not None else (None, "gone"))
            if res is None or pred is None or cl is None:
                problems.append(f"{i} ({'no usable result' if res is None else why or cwhy})")
                continue
            p = (pred.p_home, pred.p_draw, pred.p_away)
            recomputed[i] = p
            pairs.append((p[key[res]], cl["fair"][OUTCOME_SIDE[res]]))
    if problems:
        raise WindowRefused(f"{code}: members that no longer score at the read (a finding, never dropped): "
                            + "; ".join(problems))
    out = aggregate(pairs)
    out.update({"code": code, "match_ids": ids, "constants": dict(c),
                "audit": audit(stored_rows(code, window.get("declared_at_text"), export_dir), recomputed)})
    return out


# -------------------------------------------------------------------------------------------- the print --

def _causes(cnt: Counter, labels) -> str:
    got = [f"{text} {cnt[key]}" for key, text in labels if cnt.get(key)]
    return " · ".join(got) if got else "none"


def lines(res: dict, now: datetime) -> list[str]:
    """The counts-only print (R2). Never a log-loss, probability, hit or running figure of either arm."""
    L = [f"LEAGUES WINDOW — THE COHORT READER ({ADDENDUM}, R2-R4, R8; #322) · read-only · counts only (R2: nothing "
         f"of either arm before n = {WINDOW_GAMES}) · season {SEASON} · read clock {now:%Y-%m-%dT%H:%M:%SZ}"]
    for code, w in res.items():
        if not w.get("declared"):
            L.append(f"{code} · NOT DECLARED (no registry entry {w['id']}): no window")
            continue
        if w.get("refused"):
            L.append(f"{code} · REFUSED ({w['id']}): {w['refused']}")
            continue
        c = w["constants"]
        L.append(f"{code} · declared_at {w['declared_at']:%Y-%m-%dT%H:%M:%SZ} ({w['id']}; frozen "
                 f"{c['production_version']}, rho {c['rho']:g}, Elo goal coefficient {c['elo_goal_coeff']:g}, the run "
                 f"record's) · members {w['n']} of {WINDOW_GAMES} · state {w['state']}")
        L.append(f"  - stored games of {SEASON} {w['stored_games']} · kicking off at or before the instant: final or "
                 f"never walked {w['at_or_before']} (never in the window) · postponed {w['postponed_before']} "
                 f"({NOT_PLACED}) · not final {w['pending'].get('before_instant', 0)} (pending, below)"
                 + (f" · score disagreement {w['disagreement_before']} (pending, below)"
                    if w.get("disagreement_before") else ""))
        L.append(f"  - excluded (no slot): {_causes(w['excluded'], EXCLUDED)}")
        pend = Counter(w["pending"])
        L.append(f"  - pending (the read waits for them): scheduled {w['to_come']} · LIVE {pend['live']} · un-ingested "
                 f"{pend['uningested']}" + "".join(f" · {text} {pend[key]}" for key, text in PENDING[3:]
                                                    if pend.get(key)))
        L.append(f"  - after the instant: not placed {w['not_placed']} ({NOT_PLACED})")
        if w.get("awarded_released"):
            L.append(f"  - AWD / WO rows released from the members' walk {len(w['awarded_released'])} (neither scored "
                     "nor walked: addendum 16 item 1 Q2, the one predicate, addendum 181 item 2):")
            L.extend(f"    - {x}" for x in w["awarded_released"])
        if w.get("no_raw_code_members"):
            L.append(f"  - members with no raw status code {len(w['no_raw_code_members'])} (scored on the stored "
                     "score, C1; listed as C2 lists them, addendum 181 item 3):")
            L.extend(f"    - {x}" for x in w["no_raw_code_members"])
        if w.get("score_disagreement"):
            L.append(f"  - score disagreement {len(w['score_disagreement'])} (an FT or no-raw-code row whose stored "
                     "90-minute score differs from its stored score: a data finding, PENDING, never read as one figure "
                     "or the other; addendum 184 item 2 and 185):")
            L.extend(f"    - {x}" for x in w["score_disagreement"])
        L.append(f"  - stored prospective rows (R1's audit receipt): present {w['stored_present']} · missing "
                 f"{w['stored_missing']}" + ("" if w["stored_present"] else " (no stored rows: the export that "
                                                                            "writes them is a later PR)"))
        if w.get("verdict_recorded"):
            L.append(f"  - {code} · the verdict is recorded in {w['id']}: the fence is lifted")
        elif w["state"] == "ready":
            L.append(f"  - {code} · READY: {WINDOW_GAMES} members, none pending before the {WINDOW_GAMES}th. The one "
                     "read is addendum 178 PR ORDER item 5's PR; nothing is scored here")
        elif w["state"] == "waiting":
            L.append(f"  - {code} · WAITING: {WINDOW_GAMES} members, {w['blocking']} game(s) before the "
                     f"{WINDOW_GAMES}th pending (not final, or a score disagreement; R4: the read waits, never skips)")
    return L
