"""
pl-availability-v1: THE PL AVAILABILITY CANDIDATE (ARCHITECT 2026-11-01 10:05 ET, addendum 198 items 1-5; lane
pl-availability, finding #754). The ruling is verbatim in docs/specs/pl-availability-v1.md; the quotes below are cut
from it word for word (tests/test_pl_availability.py pins each one against that file).

Item 1, the rule, verbatim: "an injury entry counts as a player missing a fixture only if its type is exactly
"Missing Fixture" AND its fixture_source_id is THAT fixture's (this fixture only — not a later one: a later entry
carries the European-squad class the receipt exposed, and the feed publishes this-fixture entries before the slate).
"Questionable" entries, entries naming any other fixture, and entries naming no fixture count for nothing." Then: "The
position weights, the 25% cap, the ingest's 14-day keep and the Desk's one-sided-list rule stay exactly as they are."

- THE RULE (`counts`, `rule_filter`): one function, the candidate's only difference from v22. An entry counts when its
  `type` is exactly "Missing Fixture" and `str(fixture_source_id).strip()` equals the fixture's OWN provider id,
  `matches.external_ids["api_football"]` (as a string, stripped). A previous provider id of the match
  (`api_football_prev`, written only by match_dedupe.stamp_rekey on a twin merge, an orphan merge or relink, or a
  re-key) is NOT that fixture's id here: the feed is synced wipe-and-replace per team and names the provider's
  current fixture id at the sync; the rule reads "THAT fixture's (this fixture only)" and law 4 keeps an unknown out
  (Code's reading, docs/specs/pl-availability-v1.md section 2). A match with no provider id counts nothing. The
  candidate's injury lists are the model's lists FILTERED; factors.injury_adjustment is called on them unchanged, so
  the position weights and the 25% cap are the model's own (never copied here).
- THE ARM (item 2: "every PL slate and closing row carries a second probability set computed by the same model on the
  same inputs with the rule applied (candidate_probabilities, candidate_version, the candidate's missing counts beside
  the model's)"): training._generate_predictions_soccer prices it IN THE SAME PASS as v22, for PL only and on the host
  only (`arm_off_reason`: desk_policy.not_host_reason, the leagues export switch's own gate, addendum 178 R6): the same
  Elo, strengths, lineup and XI factors, the same predict_match, with the injury factor rebuilt from the filtered
  lists. It is stored beside v22 in the Prediction row's factor_breakdown under FB_KEY, so both arms are graded from
  one row at one close on one outcome. v22's probabilities and every other factor_breakdown key are unchanged (the
  arm adds one key, on the host only); off the host nothing is computed or stored.
- THE ROWS (`export_fields`): on the host, every PL slate and closing row (export.export_predictions, which the
  closing run's export-predictions step also writes) carries candidate_version, candidate_probabilities
  {home_win, draw, away_win} (4 places, as prediction.probabilities), candidate_missing {home, away: {model,
  candidate}} and candidate_reason (null, or why the arm is missing: then the probabilities and counts are null).
  Off the host the four keys are ABSENT (the leagues switch's pattern: off the host nothing exists, no file, no
  field). FB_KEY is removed from every exported factor_breakdown, on every machine, so the arm reaches the page only
  through these keys. The Desk never reads them (desk_policy.normalize reads named fields only; the test compares
  the Desk's blocks and desk_meta byte for byte with and without them) and neither does the Cockpit.
- THE GRADER'S SECOND ARM (`result_arm`): export.result_row, on the host and for PL, adds `candidate` beside
  `predicted` and `graded` (both unchanged): the arm scored by evaluation.score_1x2 (v22's own scorer) on the outcome
  v22's PredictionOutcome holds, the close being the row's own graded close. On a window game before the verdict it
  carries only {version, fenced}: THE FENCE withholds the arm's probabilities and scores.
- THE WINDOW (item 3, verbatim): "the window opens at the first PL kickoff strictly after the shadow's FIRST HOST PAGE
  (the entry records declared_at = this addendum's instant and window_opens_at = that kickoff, written by Code's PR
  when the deploy receipt is in hand), and holds the first 60 FINISHED PL games with a three-way close from it,
  counted as the leagues' reader counts (cancelled / AWD-WO / no close excluded by cause; LIVE or un-ingested waits;
  postponed by actual kickoff); the Desk's floor and quarantine play no part in membership."
  `membership` counts the PL 2026/27 games kicking off at or after window_opens_at (a kickoff, so the first one is in),
  in the order of their ACTUAL stored kickoff, then id, in leagues_window.membership's order: stale orphan -> excluded;
  cancelled -> excluded; postponed (no new kickoff stored) -> not placed; LIVE -> pending; SCHEDULED at or before the
  read clock -> pending (un-ingested), ahead -> to come; FINISHED under AWD / WO -> excluded; an FT or no-raw-code row
  whose stored 90-minute score disagrees with its stored score -> pending (leagues_window.disagrees); no usable
  90-minute result (leagues_window.result_of) -> pending; no priced three-way close (close.grading_close, the close
  the PL grader grades v22 at) -> excluded "no close"; then the arms: no v22 prediction, a stored prediction of
  another model than v22, or no candidate arm on it -> excluded by cause (R4's rule for a member the candidate cannot
  price); else a MEMBER. Counting stops at the 60th member. State: "accruing" under 60, "waiting" at 60 with a game
  before the 60th pending, else "ready". window_opens_at null: the reader REFUSES (no window yet).
- THE READ (item 3, verbatim): "The read at the 60th: mean three-way log-loss of each arm, unrounded; PASS only if the
  candidate's is below v22's by at least 0.0050 (the house bar), less or a tie REJECTS; the close's log-loss printed
  beside both and gating nothing; Brier and the per-club counts printed for the record." `score` (only at "ready",
  re-derived in its own read-only transaction) and `read_lines`. `verdict`: PASS when v22 - candidate >= BAR, so
  exactly 0.0050 passes ("by at least"), as mlb_pitchers_gate.verdict reads its bar; a tie of the arms rejects.
- THE FENCE (item 3, verbatim): "One read; the fence: no other read of either arm on the window until the verdict
  (guards_backtest's pattern)." `fence_cutoff` / `fence_refusal` / `fenced`: until the entry records a verdict, PL
  2026/27 games kicking off at or after the cut are fenced: the cut is window_opens_at; while it is null, the
  entry's declared_at (no window game can kick off before it); with no entry, the addendum's instant (DECLARED_AT,
  the pre-declaration fence, leagues addendum 181 item 1(b)'s precedent); an unreadable registry or instant fences the
  whole season. soccer_backtest.run_soccer_backtest, backtest.run_backtest and the soccer-backtest command refuse a PL
  walk of 2026/27 (or of every season) unless it is cut before the cut; the grader's second arm withholds its figures
  on a fenced game; the window reader prints counts only before the 60th. What is NOT fenced here (named for the
  architect, docs/specs/pl-availability-v1.md section 2): v22's production grading (evaluate, export-results'
  `predicted` / `graded`, results-tally, the value-side cohort's read), which item 4 keeps live.

Read-only everywhere except the training pass's one extra factor_breakdown key on the host.
"""
from __future__ import annotations

import json
import math
import os
from collections import Counter
from datetime import datetime, timezone

from src.walters.soccer_expansion import ExpansionRefused

EID = "pl-availability-v1"
COMPETITION = "PL"
SEASON = "2026/27"
BASE_VERSION = "v22"                    # item 1: "v22 with ONE classification rule"
DECLARED_AT_TEXT = "2026-11-01T15:05:00Z"
DECLARED_AT = datetime(2026, 11, 1, 15, 5)          # naive UTC, the matches table's clock
WINDOW_GAMES = 60
BAR = 0.0050
LL_FLOOR = 1e-12                        # evaluation._log_loss_one's floor (score_1x2), vs_close.log_loss's too
RULING = "ARCHITECT 2026-11-01 10:05 ET, addendum 198"
PROVIDER = "api_football"               # Match.external_ids key of the provider whose feed the injuries come from
MISSING_TYPE = "Missing Fixture"
FB_KEY = "pl_availability_v1"           # the arm's key in the Prediction row's factor_breakdown (never exported)
ROW_KEYS = ("candidate_version", "candidate_probabilities", "candidate_missing", "candidate_reason")
RESULT_KEY = "candidate"                # the results row's second arm

# The ruling's own words (item 1, item 3), cut verbatim from docs/specs/pl-availability-v1.md (a test pins each)
RULE_TEXT = ('an injury entry counts as a player missing a fixture only if its type is exactly "Missing Fixture" AND '
             "its fixture_source_id is THAT fixture's (this fixture only — not a later one: a later entry carries the "
             "European-squad class the receipt exposed, and the feed publishes this-fixture entries before the "
             'slate). "Questionable" entries, entries naming any other fixture, and entries naming no fixture count '
             "for nothing.")
UNCHANGED_TEXT = ("The position weights, the 25% cap, the ingest's 14-day keep and the Desk's one-sided-list rule "
                  "stay exactly as they are.")
WINDOW_TEXT = ("the window opens at the first PL kickoff strictly after the shadow's FIRST HOST PAGE (the entry "
               "records declared_at = this addendum's instant and window_opens_at = that kickoff, written by Code's "
               "PR when the deploy receipt is in hand), and holds the first 60 FINISHED PL games with a three-way "
               "close from it, counted as the leagues' reader counts (cancelled / AWD-WO / no close excluded by "
               "cause; LIVE or un-ingested waits; postponed by actual kickoff); the Desk's floor and quarantine play "
               "no part in membership.")
BAR_TEXT = ("The read at the 60th: mean three-way log-loss of each arm, unrounded; PASS only if the candidate's is "
            "below v22's by at least 0.0050 (the house bar), less or a tie REJECTS; the close's log-loss printed "
            "beside both and gating nothing; Brier and the per-club counts printed for the record.")
FENCE_TEXT = ("One read; the fence: no other read of either arm on the window until the verdict (guards_backtest's "
              "pattern).")
VERDICT_TEXT = ("A PASS makes the rule v23 by a ruling and a version bump (no other change rides it); a REJECT "
                "retires the rule and the finding closes with a written no.")

READER = "scripts/pl_availability_window.py"
RESERVATION = None                      # None = docs/registry/<EID>.started.json beside the ledger (tests: a tmp path)

# membership causes, in the print's order: (key, label)
EXCLUDED = (("stale_orphan", "stale orphan"), ("cancelled", "cancelled"), ("awarded", "AWD / WO"),
            ("no_close", "no three-way close"), ("no_v22_prediction", "no v22 prediction stored"),
            ("not_base_version", f"the stored prediction is not {BASE_VERSION}'s"),
            ("no_candidate_arm", "no candidate arm on the stored prediction"),
            ("candidate_failed", "the candidate failed on the host (stored error)"))
PENDING = (("scheduled", "scheduled"), ("live", "LIVE"), ("uningested", "un-ingested"),
           ("no_result_90", "finished with no 90-minute result"), ("score_disagreement", "score disagreement"))


class WindowRefused(ExpansionRefused):
    """A refusal of the window reader or the one read (exit 2): never a window, never a guess."""


class PLFenceRefused(ExpansionRefused):
    """A walk the fence refuses (an ExpansionRefused, so every caller that maps the leagues' fence to REFUSED / exit 2
    maps this one too: the rho and coefficient sweeps, the soccer-backtest command)."""


# ------------------------------------------------------------------------------------------------- the rule --

def provider_fixture_id(match) -> str | None:
    """The fixture's OWN provider id (external_ids["api_football"], stripped), or None. Never `api_football_prev`."""
    ext = getattr(match, "external_ids", None)
    v = ext.get(PROVIDER) if isinstance(ext, dict) else None
    v = str(v).strip() if v is not None else ""
    return v or None


def counts(inj, fixture_id: str | None) -> bool:
    """THE RULE for one entry: type exactly "Missing Fixture" AND its fixture_source_id is this fixture's id."""
    if fixture_id is None or getattr(inj, "type", None) != MISSING_TYPE:
        return False
    fid = getattr(inj, "fixture_source_id", None)
    return fid is not None and str(fid).strip() == fixture_id


def rule_filter(injuries, match) -> list:
    """The candidate's list for one side of `match`: the model's list, kept in its order, with only the entries the
    rule counts. The same objects: injury_adjustment then weighs them exactly as it weighs the model's."""
    fid = provider_fixture_id(match)
    return [i for i in (injuries or []) if counts(i, fid)]


def arm_off_reason(competition_code: str | None) -> str | None:
    """None when the training pass computes the candidate's arm (PL on the host); else why not. The host is decided
    by desk_policy.not_host_reason, the gate of the leagues' export switch (addendum 178 R6)."""
    if (competition_code or "").strip().upper() != COMPETITION:
        return f"{EID} runs on {COMPETITION} only"
    from src.walters.desk_policy import not_host_reason
    why = not_host_reason()
    return None if why is None else f"{EID} runs on the host only: {why}"


def arm_block(pred, home_c: list, away_c: list, home_m: list, away_m: list, model_version: str) -> dict:
    """The arm as the Prediction row stores it (FB_KEY): unrounded probabilities and both sides' counts."""
    return {"version": EID, "base_version": model_version,
            "p_home": pred.p_home, "p_draw": pred.p_draw, "p_away": pred.p_away,
            "missing": {"home": {"model": len(home_m), "candidate": len(home_c)},
                        "away": {"model": len(away_m), "candidate": len(away_c)}}}


def failed_block(model_version: str, err: BaseException) -> dict:
    """The marker the training pass stores under FB_KEY when the candidate could not be priced for a fixture (v22's
    row is written as always): no probabilities, so arm_of reads it as no arm, but the cause is kept, never lost to a
    log line. Exported nowhere (strip_arm); the rows, the grader's arm and the window name it."""
    return {"version": EID, "base_version": model_version, "error": f"{type(err).__name__}: {err}"[:200]}


def arm_error(pred) -> str | None:
    """The stored failure of the candidate on this prediction (failed_block), or None."""
    fb = getattr(pred, "factor_breakdown", None) if pred is not None else None
    a = fb.get(FB_KEY) if isinstance(fb, dict) else None
    if isinstance(a, dict) and a.get("version") == EID and isinstance(a.get("error"), str) and arm_of(pred) is None:
        return a["error"]
    return None


def arm_of(pred) -> dict | None:
    """The stored arm on a Prediction row, or None when it is absent or not whole (never repaired)."""
    fb = getattr(pred, "factor_breakdown", None) if pred is not None else None
    a = fb.get(FB_KEY) if isinstance(fb, dict) else None
    if not isinstance(a, dict) or a.get("version") != EID:
        return None
    ps = [a.get(k) for k in ("p_home", "p_draw", "p_away")]
    if any(not isinstance(p, (int, float)) or isinstance(p, bool) or not math.isfinite(p) for p in ps):
        return None
    return a


def strip_arm(fb) -> dict:
    """factor_breakdown as exported: the arm's key removed (a new dict; the stored one is never mutated)."""
    return {k: v for k, v in (fb or {}).items() if k != FB_KEY}


# -------------------------------------------------------------------------------------------- the rows --

def export_fields(pred, competition: str | None, m=None) -> dict | None:
    """The PL row's candidate keys on the host; None (the keys are absent) for another competition or off the host.
    THE FENCE on the rows: a FINISHED window game (`m` given; fenced) carries no candidate figures before the verdict,
    since its row carries the result beside them (result_arm withholds the same game's arm); the slate and closing
    rows of a game not yet finished carry the arm as item 2 orders."""
    if arm_off_reason(competition) is not None:
        return None
    out = {"candidate_version": EID, "candidate_probabilities": None, "candidate_missing": None,
           "candidate_reason": None}
    if m is not None and _status(m) == "finished" and fenced(fence_cutoff(getattr(m, "season", None)), m):
        out["candidate_reason"] = f"withheld: {_fence_note()}"
        return out
    if pred is None:
        out["candidate_reason"] = "no v22 prediction is stored for this fixture"
        return out
    a = arm_of(pred)
    if a is None:
        err = arm_error(pred)
        out["candidate_reason"] = (f"the candidate failed on the host for this fixture ({err}); v22's row was written "
                                   "as always" if err else
                                   "the stored prediction carries no candidate arm (written before the shadow, or by "
                                   "a predict run off the host)")
        return out
    out["candidate_probabilities"] = {"home_win": round(a["p_home"], 4), "draw": round(a["p_draw"], 4),
                                      "away_win": round(a["p_away"], 4)}
    out["candidate_missing"] = a.get("missing")
    return out


# --------------------------------------------------------------------------------------- the registry --

def _reg():
    from src.walters import registry as reg
    return reg


def _entry() -> dict | None:
    """The registry entry at call time (registry.LEDGER), None when absent; an unreadable registry raises
    WindowRefused naming it (law 4)."""
    reg = _reg()
    try:
        e = reg.get(EID, reg.LEDGER)
    except (OSError, ValueError) as err:
        raise WindowRefused(f"the registry {reg.LEDGER} is unreadable ({type(err).__name__}): nothing is read "
                            "(law 4)") from None
    return e if isinstance(e, dict) and e.get("id") == EID else None


def parse_instant(v) -> datetime | None:
    """A UTC instant ("...Z" or "+00:00") as naive UTC, else None (leagues_window.parse_instant, R3: a date is never
    the instant)."""
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


def fence_cutoff(season=None) -> datetime | None:
    """The instant from which PL 2026/27 games are the window reader's alone (kicking off AT or after it), or None (no
    fence: another season, or the verdict recorded). window_opens_at; while null, declared_at; with no entry,
    DECLARED_AT (the pre-declaration fence); an unreadable registry, declared_at or window_opens_at: datetime.min
    (the whole season, law 4)."""
    s_ = "" if season is None else str(season).strip()
    if s_ not in ("", SEASON):
        return None
    try:
        e = _entry()
    except WindowRefused:
        return datetime.min
    if e is None:
        return DECLARED_AT
    if verdict_recorded(e):
        return None
    w = e.get("window_opens_at")
    if w is not None:
        return parse_instant(w) or datetime.min
    return parse_instant(e.get("declared_at")) or datetime.min


def fence_refusal(competition_code, season=None, through: datetime | None = None) -> str | None:
    """The refusal text for a PL walk of `season` (None: every season) that would read a fenced game, None = allowed.
    A walk cut at `through` (no game kicking off after it) is allowed when `through` is strictly before the cut.
    The fence covers the window's PAIRED figures only: the candidate's arm anywhere, the backtest walks on the window and
    #430's receipt; v22's production grading (evaluate, export-results, results-tally, the value-side n=30 read, the PL
    positive-edge receipt) is the live model's own ledger and keeps running (ARCHITECT 2026-11-01 12:05 ET, addendum 199
    item 1: "it is not a read of the window's verdict, it predates the window and it carries no candidate figure")."""
    if (competition_code or "").strip().upper() != COMPETITION:
        return None
    cut = fence_cutoff(season)
    if cut is None or (through is not None and through < cut):
        return None
    at = "an unreadable registry or instant: the whole season" if cut == datetime.min else \
        f"{cut:%Y-%m-%dT%H:%M:%SZ}"
    return (f"{COMPETITION} {SEASON}: {EID} is declared and its verdict is not recorded; its games kicking off at or "
            f"after {at} are the window's, and the window's outcomes have one reader, {READER}. {RULING} item 3, "
            f"verbatim: \"{FENCE_TEXT}\"")


def fenced(cut: datetime | None, m) -> bool:
    """A game the fence covers: a fence is up and the game is of 2026/27 kicking off at or after the cut."""
    return (cut is not None and str(getattr(m, "season", "")) == SEASON
            and getattr(m, "utc_date", None) is not None and m.utc_date >= cut)


def _fence_note() -> str:
    return f"a window game before the verdict: {RULING} item 3, verbatim: \"{FENCE_TEXT}\""


# ------------------------------------------------------------------------------- the grader's second arm --

def result_arm(s, pred, oc, m) -> dict | None:
    """The results row's `candidate` (export.result_row), on the host for a PL game; None (absent) elsewhere. Scored
    by v22's own scorer (evaluation.score_1x2) on the outcome v22's graded row holds; the close is the row's own
    graded close. A fenced game carries only {version, fenced}: no probability and no score before the verdict."""
    comp = getattr(getattr(m, "competition", None), "code", None)
    if arm_off_reason(comp) is not None:
        return None
    if fenced(fence_cutoff(m.season), m):
        return {"version": EID, "fenced": _fence_note()}
    a = arm_of(pred)
    if a is None:
        err = arm_error(pred)
        return {"version": EID, "probabilities": None, "missing": None, "log_loss": None, "brier_score": None,
                "reason": (f"the candidate failed on the host for this fixture ({err})" if err else
                           "the graded prediction carries no candidate arm")}
    out = {"version": EID, "probabilities": {"home_win": a["p_home"], "draw": a["p_draw"], "away_win": a["p_away"]},
           "missing": a.get("missing"), "log_loss": None, "brier_score": None, "reason": None}
    actual = getattr(getattr(oc, "actual_result", None), "value", None)
    if actual not in ("H", "D", "A"):
        out["reason"] = "the graded row holds no result"
        return out
    from src.walters.evaluation import score_1x2
    sc = score_1x2(a["p_home"], a["p_draw"], a["p_away"], actual)
    out["log_loss"], out["brier_score"] = sc.log_loss, sc.brier_score
    return out


# ---------------------------------------------------------------------------------------- membership --

def _status(m) -> str:
    return str(getattr(m.status, "value", m.status) or "").lower()


def stored_prediction(s, match_id: int):
    """The match's prediction as the export and the grader pick it: the newest computed_at, a #569 re-pointed row
    (factor_breakdown.dedupe_569) skipped."""
    from sqlalchemy import select

    from src.db.schema import Prediction
    for p in s.execute(select(Prediction).where(Prediction.match_id == match_id)
                       .order_by(Prediction.computed_at.desc(), Prediction.id.desc())).scalars():
        if not (p.factor_breakdown or {}).get("dedupe_569"):
            return p
    return None


def _arms(s, m) -> tuple[object, dict | None, str | None]:
    """(v22's prediction, the arm, None) or (.., .., the exclusion cause)."""
    p = stored_prediction(s, m.id)
    if p is None:
        return None, None, "no_v22_prediction"
    if p.model_version != BASE_VERSION:
        return p, None, "not_base_version"
    a = arm_of(p)
    if a is None or a.get("base_version") != BASE_VERSION:
        return p, None, ("candidate_failed" if a is None and arm_error(p) else "no_candidate_arm")
    return p, a, None


def membership(s, opens_at: datetime, now: datetime) -> dict:
    """The window as of `now` (the module docstring's order). Counts and ids only: nothing of either arm is kept."""
    from sqlalchemy import select

    from src.db.schema import Competition, Match
    from src.walters.close import grading_close, priced
    from src.walters.leagues_window import disagrees, result_of
    from src.walters.soccer_expansion import AWARDED

    games = list(s.execute(select(Match).join(Competition, Competition.id == Match.competition_id)
                           .where(Competition.code == COMPETITION, Match.season == SEASON)
                           .order_by(Match.utc_date, Match.id)).scalars())
    after = [m for m in games if m.utc_date is not None and m.utc_date >= opens_at]
    out = {"opens_at": opens_at, "stored_games": len(games), "before_window": len(games) - len(after),
           "members": [], "excluded": Counter(), "pending": Counter(), "to_come": 0, "not_placed": 0, "blocking": 0}
    for m in after:
        if len(out["members"]) >= WINDOW_GAMES:
            break                                   # counting stops at the 60th member
        st = _status(m)
        raw = (m.status_raw or "").strip().upper()
        if st == "stale_orphan":
            out["excluded"]["stale_orphan"] += 1
        elif st == "cancelled":
            out["excluded"]["cancelled"] += 1
        elif st == "postponed":
            out["not_placed"] += 1                  # placed by its actual kickoff once re-dated; never blocking
        elif st == "live":
            out["pending"]["live"] += 1
            out["blocking"] += 1
        elif st != "finished":                      # scheduled
            if m.utc_date <= now:
                out["pending"]["uningested"] += 1
            else:
                out["to_come"] += 1
            out["blocking"] += 1
        elif raw in AWARDED:
            out["excluded"]["awarded"] += 1
        elif disagrees(m):
            out["pending"]["score_disagreement"] += 1
            out["blocking"] += 1
        elif result_of(m) is None:
            out["pending"]["no_result_90"] += 1
            out["blocking"] += 1
        elif not priced(grading_close(s, m)):
            out["excluded"]["no_close"] += 1
        else:
            _, _, why = _arms(s, m)
            if why:
                out["excluded"][why] += 1
            else:
                out["members"].append(m.id)
    out["n"] = len(out["members"])
    out["state"] = ("accruing" if out["n"] < WINDOW_GAMES else "waiting" if out["blocking"] else "ready")
    return out


def checked(e: dict | None) -> tuple[datetime, datetime]:
    """(declared_at, window_opens_at) of the entry, or WindowRefused: no entry, its instants not UTC, or no window yet
    (window_opens_at null: Code's PR records it when the deploy receipt of the first host page is in hand)."""
    if e is None:
        raise WindowRefused(f"no registry entry {EID}: nothing is read")
    at = parse_instant(e.get("declared_at"))
    if at is None:
        raise WindowRefused(f"{EID}: no declared_at as a UTC instant (stored {e.get('declared_at')!r})")
    w = e.get("window_opens_at")
    if w is None:
        raise WindowRefused(f"{EID}: window_opens_at is null: the window has not opened (item 3: it opens at the first "
                            "PL kickoff strictly after the shadow's first host page, recorded by Code's PR when the "
                            "deploy receipt is in hand); nothing is counted")
    opens = parse_instant(w)
    if opens is None:
        raise WindowRefused(f"{EID}: window_opens_at {w!r} is not a UTC instant; a date is never the instant")
    if opens <= at:
        raise WindowRefused(f"{EID}: window_opens_at {w} is not after declared_at {e.get('declared_at')}")
    return at, opens


def read(now: datetime | None = None) -> dict:
    """The window, counts only (R2), or {"refused": why}. One mode=ro session (readonly_scope). Never scores."""
    from src.db.database import ReadOnlyRefused, readonly_scope
    from src.timeutil import utc_now_naive
    now = now or utc_now_naive()
    try:
        e = _entry()
        at, opens = checked(e)
        with readonly_scope() as s:
            w = membership(s, opens, now)
    except (WindowRefused, ReadOnlyRefused) as err:
        return {"refused": str(err)}
    w.update({"declared_at": at, "verdict_recorded": verdict_recorded(e)})
    return w


def _causes(cnt, labels) -> str:
    got = [f"{text} {cnt[key]}" for key, text in labels if cnt.get(key)]
    return " · ".join(got) if got else "none"


def lines(res: dict, now: datetime) -> list[str]:
    """The counts-only print (R2): never a log-loss, a probability, a hit or any running figure of either arm."""
    L = [f"PL AVAILABILITY WINDOW — {EID} ({RULING}; #754) · read-only · counts only (nothing of either arm before "
         f"n = {WINDOW_GAMES}) · season {SEASON} · read clock {now:%Y-%m-%dT%H:%M:%SZ}"]
    if res.get("refused"):
        L.append(f"REFUSED: {res['refused']}")
        return L
    pend = Counter(res["pending"])
    L.append(f"declared_at {res['declared_at']:%Y-%m-%dT%H:%M:%SZ} · window opens {res['opens_at']:%Y-%m-%dT%H:%M:%SZ} "
             f"(the first PL kickoff after the first host page) · members {res['n']} of {WINDOW_GAMES} · state "
             f"{res['state']}")
    L.append(f"  - stored PL games of {SEASON} {res['stored_games']} · kicking off before the window "
             f"{res['before_window']} (never in it)")
    L.append(f"  - excluded (no slot): {_causes(res['excluded'], EXCLUDED)}")
    L.append(f"  - pending (the read waits for them): scheduled {res['to_come']} · LIVE {pend['live']} · un-ingested "
             f"{pend['uningested']}" + "".join(f" · {text} {pend[key]}" for key, text in PENDING[3:]
                                                if pend.get(key)))
    L.append(f"  - postponed, not placed {res['not_placed']} (placed by its actual kickoff once re-dated)")
    if res.get("verdict_recorded"):
        L.append(f"  - the verdict is recorded in {EID}: the fence is lifted")
    elif res["state"] == "ready":
        L.append(f"  - READY: {WINDOW_GAMES} members, none pending before the {WINDOW_GAMES}th. The one read is "
                 f"{READER} --read (once: it reserves the read before it scores)")
    elif res["state"] == "waiting":
        L.append(f"  - WAITING: {WINDOW_GAMES} members, {res['blocking']} game(s) before the {WINDOW_GAMES}th pending "
                 "(the read waits, never skips)")
    return L


# ------------------------------------------------------------------------------------------- the read --

def verdict(ll_v22: float, ll_candidate: float) -> str:
    """Item 3's bar: PASS only when v22's mean log-loss minus the candidate's is at least BAR; less, or a tie, REJECTS."""
    return "PASS" if (ll_v22 - ll_candidate) >= BAR else "REJECT"


def aggregate(rows: list[dict]) -> dict:
    """[{res, v22: (h, d, a), cand: (h, d, a), close_p, home, away, missing}] -> both arms' means (score_1x2, v22's
    scorer: log-loss floored at 1e-12, three-way Brier), the close's mean log-loss (vs_close.log_loss, the same floor;
    gating nothing), the per-club counts and the verdict. Unrounded. Pure."""
    from src.walters.evaluation import score_1x2
    from src.walters.vs_close import log_loss
    n = len(rows)
    if not n:
        raise WindowRefused("no member to score")
    sv = [score_1x2(*r["v22"], r["res"]) for r in rows]
    sc = [score_1x2(*r["cand"], r["res"]) for r in rows]
    ll_v = math.fsum(x.log_loss for x in sv) / n
    ll_c = math.fsum(x.log_loss for x in sc) / n
    clubs: dict[str, dict] = {}
    for r in rows:
        for side, name in (("home", r["home"]), ("away", r["away"])):
            c = clubs.setdefault(name, {"games": 0, "model_missing": 0, "candidate_missing": 0})
            c["games"] += 1
            mis = ((r.get("missing") or {}).get(side) or {})
            c["model_missing"] += int(mis.get("model") or 0)
            c["candidate_missing"] += int(mis.get("candidate") or 0)
    return {"n": n, "ll_v22": ll_v, "ll_candidate": ll_c, "diff": ll_v - ll_c,
            "ll_close": math.fsum(log_loss(r["close_p"]) for r in rows) / n,
            "brier_v22": math.fsum(x.brier_score for x in sv) / n,
            "brier_candidate": math.fsum(x.brier_score for x in sc) / n,
            "clubs": dict(sorted(clubs.items())), "verdict": verdict(ll_v, ll_c)}


def score(window: dict, now: datetime | None = None) -> dict:
    """THE ONE READ: refused unless the window is "ready" (60 members, nothing pending before the 60th). The window is
    re-derived in the read's own mode=ro transaction and must hold the same members; each member is read at the
    close the grader uses (close.grading_close), on its 90-minute outcome (leagues_window.result_of), both arms from
    the one stored prediction row. A member that no longer scores refuses the read (a finding, never dropped)."""
    from src.db.database import readonly_scope
    from src.db.schema import Match
    from src.timeutil import utc_now_naive
    from src.walters.close import grading_close, priced
    from src.walters.intl_shadow import OUTCOME_SIDE
    from src.walters.leagues_window import result_of

    ids = list(window.get("members") or ())
    if window.get("state") != "ready" or len(ids) != WINDOW_GAMES:
        raise WindowRefused(f"the one read is at the {WINDOW_GAMES}th member with nothing pending before it (state "
                            f"{window.get('state')!r}, members {len(ids)})")
    rows, problems = [], []
    with readonly_scope() as s:
        fresh = membership(s, window["opens_at"], now or utc_now_naive())
        if fresh["state"] != "ready" or fresh["members"] != ids:
            raise WindowRefused(f"the window moved between the read and the score (state {fresh['state']!r}; members "
                                f"{'unchanged' if fresh['members'] == ids else 'changed'}): read it again; nothing "
                                "is scored")
        for i in ids:
            m = s.get(Match, i)
            res = result_of(m) if m is not None and _status(m) == "finished" else None
            cl = grading_close(s, m) if m is not None else None
            p, a, why = _arms(s, m) if m is not None else (None, None, "gone")
            if res is None or not priced(cl) or why:
                problems.append(f"{i} ({'no usable result' if res is None else why or 'no close'})")
                continue
            rows.append({"match_id": i, "res": res,
                         "v22": (p.home_win_prob, p.draw_prob or 0.0, p.away_win_prob),
                         "cand": (a["p_home"], a["p_draw"], a["p_away"]),
                         "close_p": cl["fair"][OUTCOME_SIDE[res]],
                         "home": m.home_team.name if m.home_team else f"team {m.home_team_id}",
                         "away": m.away_team.name if m.away_team else f"team {m.away_team_id}",
                         "missing": a.get("missing")})
    if problems:
        raise WindowRefused("members that no longer score at the read (a finding, never dropped): "
                            + "; ".join(problems))
    out = aggregate(rows)
    out["match_ids"] = ids
    return out


def read_lines(r: dict) -> list[str]:
    """The one read as printed: both arms' mean log-loss (unrounded), the difference against the bar and the verdict;
    the close's beside both, gating nothing; Brier and the per-club counts for the record."""
    L = [f"THE ONE READ — {EID} ({RULING} item 3) · n {r['n']} · {BAR_TEXT}",
         f"  - mean three-way log-loss: v22 {r['ll_v22']!r} · candidate {r['ll_candidate']!r} · v22 minus candidate "
         f"{r['diff']!r} (bar {BAR}: PASS only if at least the bar; less or a tie REJECTS)",
         f"  - VERDICT: {r['verdict']}",
         f"  - the close's mean log-loss (gating nothing): {r['ll_close']!r}",
         f"  - Brier (for the record): v22 {r['brier_v22']!r} · candidate {r['brier_candidate']!r}",
         "  - per club (for the record): games · missing as the model counted · missing as the candidate counted"]
    L.extend(f"    - {k}: {c['games']} · {c['model_missing']} · {c['candidate_missing']}"
             for k, c in r["clubs"].items())
    L.append(f"  - {VERDICT_TEXT}")
    return L


def reservation_path() -> str:
    return RESERVATION or os.path.join(os.path.dirname(_reg().LEDGER), f"{EID}.started.json")


def reserve(now: datetime, no_fetch: bool = False, echo=None) -> str:
    """The one read's reservation: an exclusive create of docs/registry/pl-availability-v1.started.json (refused when
    it exists: the read is spent), after the shared cross-ref guard (#329 RULED 2026-10-08: "every cohort freeze and
    every one-run reservation calls it BEFORE it writes"; mlb_pitchers_gate.reserve is the pattern): a reservation or
    run record of this experiment on any ref the clone knows that this tree does not hold identically refuses. A write
    that fails spends nothing (#749 / addendum 194 item 2): the file is removed, and a removal that fails is named.
    Returns its path."""
    reg = _reg()
    p = reservation_path()
    if os.path.exists(p):
        raise WindowRefused(f"the one read is spent: {p} exists (law 3: one read)")
    try:
        receipt = reg.cross_ref_guard(EID, no_fetch=no_fetch)
    except reg.RegistryError as e:
        raise WindowRefused(str(e)) from None
    if echo:
        echo(receipt)
    try:
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise WindowRefused(f"the one read is spent: {p} exists (law 3: one read)") from None
    try:
        with os.fdopen(fd, "w") as f:
            json.dump({"id": EID, "started_at": f"{now:%Y-%m-%dT%H:%M:%SZ}", "guard": receipt}, f)
            f.write("\n")
    except (OSError, TypeError, ValueError) as x:
        try:
            os.remove(p)
        except OSError as y:
            raise WindowRefused(f"the reservation {p} could not be written ({type(x).__name__}: {x}) and could NOT be "
                                f"removed ({y}): nothing was read, but the file now reads as a spent read; remove {p} "
                                "by hand before the read") from None
        raise WindowRefused(f"the reservation {p} could not be written ({type(x).__name__}: {x}); the file is removed: "
                            "the one read is not spent, nothing read") from None
    return p
