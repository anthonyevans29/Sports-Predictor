"""THE LEAGUES' CONFIRMATION READ, AS A COMMAND (ARCHITECT 2026-11-22 09:18 ET, addendum 447 item 3 C1 and item 4 PR 3;
addendum 448 item 1(e)-(f); addendum 467 item 1(a); lane leagues, #322; the plan, #322 issuecomment-7066669252: "the
same arguments and refusals as (b)").

`python cli.py leagues-confirmation-read --code <PD|SA|FL1|ELC|BL1> --db COPY --exports DIR --pages-digest HEX` in two
invocations, each its own:
  1. `--preflight` (ARCHITECT 2026-11-25, addendum 540 item 1 Q1(ii), ruled: "A PREFLIGHT THAT COMPUTES NO FIGURE
     and reserves nothing: the refusals in order, the cohort's count, the pages digest, the first date the read is
     allowed"): the read's refusals in the read's order, counts only, the pages and their digest, the opening, the
     games named against it, the first date the read is allowed, then the CONFIRMATION FINGERPRINT. Scores nothing (no figure
     of either arm), reserves nothing, writes nothing.
  2. `--architect-word "<word>" --confirmation-fingerprint HEX --ruling "<the addendum that orders the read, by
     number and date (never an outcome)>" [--no-fetch]`: THE ONE READ, and its record. ONE invocation (540 item 1 Q1,
     ruled, like the two confirm commands that exist): the outcome is COMPUTED by registry.record_confirmation
     (CONFIRMED iff the candidate's mean log-loss is strictly below the close's on the same 60; a tie fails), never
     stated, so there is no --record-verdict. Q1(i): "NO WORD OF MINE ABOUT THE OUTCOME IS TAKEN IN ADVANCE. The
     outcome is the computed one. What I give beside the fingerprint is the addendum that orders the read, by number
     and date." So --ruling is the addendum that orders the read, by number and date (never an outcome), and a
     --architect-word or --ruling that names CONFIRMED or NOT_CONFIRMED (any case, as a word) REFUSES, exit 2, before
     any load, nothing reserved (OUTCOME_WORD).

THE COHORT (447 C1, RULED, verbatim in part): "the confirmation opens at the 60th member's PLACE IN THE WINDOW'S OWN
ORDER ... The confirmation's games are the games later in that order: a later kickoff, or the same kickoff and a higher
id. Its cohort is the first 60 of them that qualify by the window's own rules." The opening is read ONLY from the run
record (`confirmation_opens_after`, written by the window's one read), never from a caller and never from the DB
(leagues_window.confirmation_basis). THE OPENING'S RESOLUTION: the opening is stored to the second, with the Z (addendum
448 item 1(d): "The opening's kickoff is written as the callers write theirs"), so every comparison with it (the
cohort's "later", the account, the findings, the window members now after it, and the backstop's place check) reads
each game's kickoff CUT to the whole second, never rounded, against the opening as stored (leagues_window.after_opening).
A game the run record names as a WINDOW MEMBER is after the opening ONLY when its cut kickoff is in a LATER second than
the opening's (re-dated past the opening's second): a member still in the opening's second, whatever its id (a 59th
member at +200 ms with an id above the 60th's at +500 ms), stays a window member, never after it, never refused. Every
other game by its place (leagues_window.place: the cut kickoff, then its id): in the opening's second with a higher id
it is after the opening, with a lower or equal id before it; at whole-second kickoffs nothing changes. In this read
a ruled item's kickoff (written to the second, with the Z) is compared with the game's kickoff cut to the whole second
(leagues_window.apply_ruled, cut), so an item copied from a refusal matches a sub-second kickoff; the window's read
compares exactly, unchanged. 447 C1(d): a game kicking off after declared_at and before the opening in that order that
the run record does not account for (neither a member nor a game that took no slot: re-dated, or at sub-second
precision in the opening's second with an id not above the opening's) is a FINDING, counted and named, in neither
cohort, covered by the fingerprint, never a member.
448 item 1(e): a game the window's loop passed (a postponed one) enters by its real kickoff once it is re-dated after
the opening.

WHERE AND ON WHAT: as the window's read (leagues_read, B2): the laptop, the host's pulled .backup copy (`--db`) and the
host's pages (`--exports`, refused inside the checkout, never written, its digest the host's). The registry writes (the
reservation, the confirmation and its ids file) land in this checkout and travel by the laptop/<eid>-confirmation-
record branch (#329).

EVERY REFUSAL BEFORE ANYTHING IS SCORED, in this order (leagues_read.ReadRefused; the CLI prints REFUSED, exit 2;
nothing reserved, nothing written):
  1. the arguments (leagues_read.check_args); in the run, no word, no fingerprint or no ruling, or a word or ruling
     that names an outcome (540 item 1 Q1(i)); all before any load;
  2. the registry entry (check_entry): absent; a stored plan that is not the ruled plan; no run, or a run not recorded
     by leagues-window-read; a verdict that is not a recorded PASS; a status that is not confirming; a confirmation
     recorded (the fence lifted); no readable opening; a run record that does not hold together (60 distinct integer
     members, the last one the opening's match, took_no_slot readable); the run's ids file missing, or not the 60
     members, or not its sha256; the confirmation's reservation present (spent);
  3. the copy, 4. the pages (leagues_read's fences, unchanged);
  5. the entry's own checks and ruled list (the entry's one ruled_exclusions list, #803; 540 item 1 Q4, ruled)
     inside the read;
  6. no window member is now in a later second than the opening's (moved_refusal; 540 item 1 Q3, ruled: "THE READ REFUSES BEFORE
     ITS RESERVATION, NAMING THE GAME"; it lifts only by the architect's registry write naming the game in the entry's
     ruled_exclusions list, and the game is then out by its named cause and takes no slot: leagues_window.membership),
     read BEFORE the state, so a re-dated member that is not final refuses named and never makes the read WAIT; then
     the confirmation: ready (60 members after the opening, nothing pending before its 60th), else the read WAITS;
  7. THE BACKSTOP (backstop): no confirmation member is a window member, no window member is now later than the
     opening (moved_refusal again), the first member is later than the opening, and
     registry.confirmation_refusal finds nothing record_confirmation would refuse (467 item 1(a)'s tie and 540 item 1
     Q5's three guards included);
  8. THE DAY AFTER (B2(d)) on the 60th CONFIRMATION member (the plan's "the same refusals as (b)"; 540 item 1: "YOUR
     INFERENCE STANDS ... It is the more binding reading");
  9. the fingerprint (confirmation_fingerprint: the window fingerprint's parts under this command's own tag, with the
     opening, the findings and the sha of the run record's account);
 10. the bytes read, unchanged since they were digested and hashed.
Then the #329 cross-ref guard (its kinds now include the confirmation record and its reservation, 448 item 1(f)) and
the reservation docs/registry/<eid>.confirm.started.json (leagues_read.reserve: exclusive create, serialised first,
fsynced, removed if the write fails). From there THE READ IS SPENT: the score (leagues_window.score on the same copy
session, the confirmation re-derived in its own pass), the pages digest, the copy's sha256 and its sidecars again;
any failure there raises SpentRefused (the reservation stands; released by the architect's ruling only) and nothing is
recorded. Then record: registry.record_confirmation (ids/<eid>.confirm.txt, the entry's `confirmation`, status
production or closed), the result checked JSON-serialisable first.

THE CONFIRMATION'S RESULT: n; `log_loss` (the candidate) and `reference_log_loss` (the close), unrounded; first_game_at
and first_game_id (467 item 1(a)); the members in order; the opening as read; every reached game that took no slot,
by id with its cause; the findings (447 C1(d)) and the took-no-slot games re-dated still at or before the opening; the
audit; the frozen constants; the ruled list; the copy's sha256; the pages; the word; the fingerprint; the read clock;
the first allowed date; the run's ids sha256; the reservation. NO KEY holds a calls rule (540 item 1 Q2, ruled: "a
record is never rewritten, and a rule that may be amended does not belong in one"; 505 item 2(c) is quoted verbatim in
the PR body and the two fragments). ONE ADDITION, console only and stored nowhere: a read whose recorded outcome is
CONFIRMED prints CONFIRMED_NOTE (production on a leagues entry turns on no call; 220 item 3; 505 item 2(c)).

Changes no prediction output: no prediction, export, Desk call or model is written or read differently; production on
a leagues entry turns nothing on (447 C3(b)).
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime

from src.walters import leagues_read as lr
from src.walters import leagues_window as lw

COMMAND = "leagues-confirmation-read"
FINGERPRINT_TAG = "leagues-confirmation-read v1"
# ARCHITECT 2026-11-25, addendum 540 item 1 Q1(i): no word of the architect's about the outcome is taken in advance; a
# --architect-word or --ruling naming either outcome, as a word in any case, refuses before any load.
OUTCOME_WORD = re.compile(r"\b(?:NOT_CONFIRMED|CONFIRMED)\b", re.IGNORECASE)
# 540 item 1 Q2: "ONE ADDITION, console only and stored nowhere: a read whose outcome is CONFIRMED prints one line saying
# that production on a leagues entry turns on no call (220 item 3; 505 item 2(c))."
CONFIRMED_NOTE = ("NOTE (console only, stored nowhere; addendum 540 item 1 Q2): production on a leagues entry turns on "
                  "no call (addendum 220 item 3; addendum 505 item 2(c)).")
ReadRefused = lr.ReadRefused
SpentRefused = lr.SpentRefused


def _reg():
    from src.walters import registry as reg
    return reg


SUFFIX = _reg().CONFIRM_RESERVATION_SUFFIX        # ".confirm.started.json": the cross-ref guard's own name (448 1(f))


def reservation_path(eid: str) -> str:
    return lr.reservation_path(eid, SUFFIX)


# ---------------------------------------------------------------------------------------- 2. the entry --

def check_entry(code: str) -> dict:
    """The entry the confirmation reads, refused (ReadRefused, nothing reserved) in the module docstring's order."""
    reg = _reg()
    eid = lw.DECLARATION_IDS[code]
    try:
        e = lw.declaration(code)
    except lw.WindowRefused as err:
        raise ReadRefused(f"{eid}: {err}") from err
    if e is None:
        raise ReadRefused(f"{eid}: no declared entry in the registry; nothing to confirm")
    why = lw.plan_refusal(e)                 # 448 item 2(b), as the window read refuses it
    if why:
        raise ReadRefused(f"{why}; nothing read")
    res = lw._run_result(e)
    if not e.get("run") or res.get("command") != lr.COMMAND:
        raise ReadRefused(f"{eid}: no run recorded by {lr.COMMAND} (the window's one read): there is no opening to "
                          "confirm from; nothing read")
    v = e.get("verdict")
    if not isinstance(v, dict) or v.get("verdict") != "PASS":
        raise ReadRefused(f"{eid}: the verdict is {(v or {}).get('verdict') if isinstance(v, dict) else v!r}, not a "
                          "recorded PASS: only a PASS enters the confirmation; nothing read")
    if e.get("status") != lw.CONFIRMING:
        raise ReadRefused(f"{eid}: the status is {e.get('status')!r}, not {lw.CONFIRMING!r}; nothing read")
    if lw.lifted(e):
        raise ReadRefused(f"{eid}: a confirmation is recorded ({(e.get('confirmation') or {}).get('outcome')}): the "
                          "confirmation's one read is spent; nothing read")
    if lw.opening(e) is None:
        raise ReadRefused(f"{eid}: the run record holds no readable opening ({lw.OPENING_FIELD}): never a fall-back "
                          "to declared_at or verdict.at (law 4); nothing read")
    try:
        basis = lw.confirmation_basis(e)
    except lw.WindowRefused as err:
        raise ReadRefused(f"{err}") from err
    try:
        held = reg._ids_of(e, reg.IDS_DIR)
    except (OSError, ValueError) as err:
        raise ReadRefused(f"{eid}: the run's ids file cannot be read ({type(err).__name__}: {err}); nothing read") \
            from err
    run = e["run"]
    if held is None:
        raise ReadRefused(f"{eid}: the run's ids file ({run.get('ids_file')!r}) is missing: the scored set cannot be "
                          "checked, so no confirmation is read (law 4); nothing read")
    if sorted(held) != sorted(basis["members"]) or reg._ids_sha(sorted(held)) != run.get("ids_sha256"):
        raise ReadRefused(f"{eid}: the run's ids file ({run.get('ids_file')}) is not the run record's 60 members or "
                          "not its ids_sha256: the scored set does not hold together; nothing read")
    p = reservation_path(eid)
    if os.path.lexists(p):
        raise ReadRefused(f"{eid}: the confirmation's one read was started at {lr._started_at(p)} "
                          f"({os.path.relpath(p)}): it is spent, recorded or not; nothing reads it again without the "
                          "architect's ruling")
    return e


# ----------------------------------------------------------------------------------- 7. the backstop --

def moved_refusal(e: dict, w: dict) -> str | None:
    """ARCHITECT 2026-11-25, addendum 540 item 1 Q3, ruled: "THE READ REFUSES BEFORE ITS RESERVATION, NAMING THE
    GAME": the refusal naming each window member whose kickoff is now in a later second than the opening's
    (leagues_window.after_opening) and not lifted by a ruled item (leagues_window.MEMBERS_AFTER), else None. Read BEFORE the confirmation's state, by the read and the preflight
    alike: a re-dated member that is not final would otherwise make the read WAIT without naming it."""
    moved = w.get(lw.MEMBERS_AFTER) or []
    if not moved:
        return None
    return (f"{e.get('id')}: window member(s) now kick off later than the opening: "
            + "; ".join(f"match {mid} at {lr._iso(ko)}" for mid, ko in moved)
            + " (re-dated after the window's read to a later second than the opening's; the read refuses, never "
            "placing a scored game, until the architect's registry write names it in the entry's ruled_exclusions: "
            "addendum 540 item 1 Q3)")


def backstop(e: dict, w: dict) -> str | None:
    """Why the registry would refuse this cohort after the read is spent, else None (law 4: the read is never spent on
    a cohort record_confirmation must refuse, short of a race). (i) no confirmation member is a window member, and no
    window member is now later than the opening (540 item 1 Q3: refused, each named); (ii) the first member is later
    than the opening in the window's order, its kickoff cut to the whole second as the opening is stored
    (leagues_window.after_opening, by the same rule as the read; an invariant); (iii) registry.confirmation_refusal on the 60 members with the first member's
    kickoff as the registry reads it (to the second with the Z) and its id (467 item 1(a)'s tie: a first member in the
    opening's second has an id above the opening's by (ii), so the reader and the registry agree)."""
    reg = _reg()
    eid = e.get("id")
    basis = w.get("accounted") or {}
    window = set(basis.get("members") or ())
    accounted = window | set(basis.get("no_slot") or {})       # the members and the games reached with no slot
    scored = [i for i in w["members"] if i in window]
    if scored:
        return (f"{eid}: confirmation member(s) {', '.join(str(i) for i in scored)} were window members (scored by the "
                "window's one read): a game already scored is never a confirmation game")
    why = moved_refusal(e, w)
    if why:
        return why
    op, first = w.get("opening"), w.get(lw.FIRST_MEMBER)
    if op is None or first is None or not lw.after_opening(first[1], first[0], op, first[0] in accounted):
        return (f"{eid}: the first confirmation member {first!r} is not later than the opening {op!r} in the "
                "window's order (an invariant of the read)")
    why = reg.confirmation_refusal(eid, list(w["members"]), lr._iso(first[1]), first[0], path=reg.LEDGER,
                                   ids_dir=reg.IDS_DIR)
    return None if why is None else f"the registry would refuse this cohort: {why}"


# -------------------------------------------------------------------------------------- the fingerprint --

def confirmation_fingerprint(code: str, w: dict, stored: dict, copy_sha: str, digest: str) -> str:
    """leagues_read.window_fingerprint under this command's own tag, over the confirmation's read (its opening, its
    findings and the run record's account included): a window fingerprint is never this one."""
    return lr.window_fingerprint(code, w, stored, copy_sha, digest, tag=FINGERPRINT_TAG)


# ------------------------------------------------------------------------------------------ the preflight --

def preflight_lines(code, db, exports, pages_digest, now: datetime | None = None) -> list[str]:
    """--preflight (540 item 1 Q1(ii)): the read's refusals in its order (each raises ReadRefused as the read would),
    counts only (leagues_window.lines on the confirmation's read: no figure of either arm), the pages and their digest,
    the opening, the games named against it, the first date the read is allowed, the backstop, then the fingerprint when the
    confirmation is ready. Computes no figure, reserves nothing, writes nothing."""
    from src.timeutil import utc_now_naive
    now = now or utc_now_naive()
    code = lr.check_args(code, db, exports, pages_digest)
    e = check_entry(code)
    path = lr.check_copy(db)
    sha, pages, w, stored = lr.load(code, e, path, exports, pages_digest, now, confirmation=True)
    why = lr.unchanged(path, exports, sha, pages)
    if why:
        raise ReadRefused(f"{lw.DECLARATION_IDS[code]}: {why} while the confirmation was read; no fingerprint; "
                          "nothing read")
    op = w["opening"]
    L = [f"LEAGUES CONFIRMATION READ · PREFLIGHT · {code} · clock {lr._iso(now)} (scores nothing, reserves nothing, "
         "writes nothing; addendum 447 item 3 C1)"]
    L += lr._label(code, path, sha, pages)
    L += lw.lines({code: w}, now)
    L.append(f"  the opening (the run record's, 447 C1): after match {op[1]} at {lr._iso(op[0])}, in the window's "
             f"order · findings, not accounted for by the run record (447 C1(d)) {len(w.get(lw.REDATED) or [])}")
    fa = lr.first_allowed(w)
    why = moved_refusal(e, w)            # 540 item 1 Q3: before the state, so a moved member never reads as waiting
    if why:
        L.append(f"PREFLIGHT only: the read REFUSES before the reservation: {why}: NO fingerprint.")
        return L
    if w["state"] != "ready":
        state = "not yet" if fa is None else f"provisional (the confirmation is {w['state']})"
        L.append(f"  the 60th confirmation member: {state}"
                 + ("" if fa is None else f" · the first date the read would be allowed {fa.isoformat()} (UTC)"))
        L.append(f"PREFLIGHT only: the confirmation is {w['state']!r}, not ready: NO fingerprint; the read refuses.")
        return L
    first = w[lw.FIRST_MEMBER]
    L.append(f"  the first confirmation member: match {first[0]} at {lr._iso(first[1])} (first_game_id, first_game_at; "
             "467 item 1(a))")
    L.append(f"  the 60th confirmation member kicks off {lr._iso(w[lw.LAST_MEMBER][1])}: the read is allowed from "
             f"{fa.isoformat()} (UTC), the day after (447 item 2 B2(d), held for the confirmation too)"
             + ("" if now.date() >= fa else f" · NOT TODAY ({now.date().isoformat()}): the read refuses until then"))
    why = backstop(e, w)
    if why:
        L.append(f"PREFLIGHT only: the read REFUSES before the reservation: {why}: NO fingerprint.")
        return L
    L.append(f"CONFIRMATION FINGERPRINT {confirmation_fingerprint(code, w, stored, sha, pages['digest'])} (the read "
             "takes it as --confirmation-fingerprint)")
    return L


# ----------------------------------------------------------------------------------------- THE ONE READ --

def outcome_refusal(word, ruling) -> str | None:
    """540 item 1 Q1(i): the refusal text when --architect-word or --ruling names CONFIRMED or NOT_CONFIRMED (case-
    insensitive, as a word), else None. Read before any load: nothing read, nothing reserved."""
    for flag, v in (("--architect-word", word), ("--ruling", ruling)):
        hit = OUTCOME_WORD.search(str(v or ""))
        if hit:
            return (f"{flag} names an outcome ({hit.group(0)!r}): no word about the outcome is taken in advance; the "
                    "outcome is the computed one, and --ruling is the addendum that orders the read, by number and "
                    "date, never an outcome (ARCHITECT 2026-11-25, addendum 540 item 1 Q1(i)); nothing read")
    return None


def confirmed_note(e: dict) -> str | None:
    """540 item 1 Q2: CONFIRMED_NOTE when the recorded outcome is CONFIRMED, else None. Console only: it is never
    written into the result, the entry or any file."""
    return CONFIRMED_NOTE if (e.get("confirmation") or {}).get("outcome") == "CONFIRMED" else None


def run(code, db, exports, pages_digest, word, fingerprint, ruling, now: datetime | None = None,
        no_fetch: bool = False, echo=None) -> dict:
    """THE ONE READ (the module docstring's order). Returns the result record() records."""
    from src.timeutil import utc_now_naive
    code = lr.check_args(code, db, exports, pages_digest)
    eid = lw.DECLARATION_IDS[code]
    if not word or not str(word).strip():
        raise ReadRefused("the read starts only on the architect's word: pass --architect-word verbatim; nothing read")
    if not fingerprint or not str(fingerprint).strip():
        raise ReadRefused(f"the word refers to one confirmation (the preflight's): pass --confirmation-fingerprint "
                          f"with the last line of {COMMAND} --preflight; nothing read")
    if not ruling or not str(ruling).strip():
        raise ReadRefused("--ruling is required: the addendum that orders the read, by number and date (never an "
                          "outcome), recorded with the computed outcome (one invocation); nothing read")
    why = outcome_refusal(word, ruling)
    if why:
        raise ReadRefused(why)
    now = now or utc_now_naive()
    e = check_entry(code)
    path = lr.check_copy(db)            # opened once, so the read and the score share one immutable session
    with lr._copy_session(path) as s:
        sha, pages, w, stored = lr.load(code, e, path, exports, pages_digest, now, s=s, confirmation=True)
        why = moved_refusal(e, w)        # 540 item 1 Q3: before the state, naming the game, never 'waiting'
        if why:
            raise ReadRefused(f"{why}; nothing reserved")
        if w["state"] != "ready":
            raise ReadRefused(f"{eid}: the confirmation is {w['state']!r}, not ready (60 members after the opening, "
                              "nothing pending before the 60th): the read WAITS; nothing reserved")
        why = backstop(e, w)
        if why:
            raise ReadRefused(f"{why}; nothing reserved")
        fa = lr.first_allowed(w)
        if now.date() < fa:
            raise ReadRefused(f"{eid}: the 60th confirmation member kicks off {lr._iso(w[lw.LAST_MEMBER][1])}; the "
                              f"read is allowed from {fa.isoformat()} (UTC), the day after (addendum 447 item 2 "
                              f"B2(d)), and the clock reads {now.date().isoformat()}; nothing reserved")
        fp = confirmation_fingerprint(code, w, stored, sha, pages["digest"])
        if str(fingerprint).strip().lower() != fp:
            raise ReadRefused(f"the confirmation fingerprint given ({fingerprint!r}) is not this confirmation's ({fp}): "
                              f"run {COMMAND} --preflight again and take the word on it; nothing reserved")
        why = lr.unchanged(path, exports, sha, pages)
        if why:
            raise ReadRefused(f"{eid}: {why} while the confirmation was read; nothing reserved")
        if echo:
            for ln in lr._label(code, path, sha, pages):
                echo(ln.strip())
        op = w["opening"]
        meta = {"architect_word": word, "confirmation_fingerprint": fp, "copy_sha256": sha,
                "pages_digest": pages["digest"], "pages": pages["pages"], "code_sha": lr._code_sha(),
                "opening": {"kickoff": lr._iso(op[0]), "match_id": op[1]}}
        held = lr.reserve(eid, meta, no_fetch=no_fetch, echo=echo, path=reservation_path(eid))
        # from here on, the confirmation's one read is spent
        try:
            r = lw.score(w, export_dir=str(exports), now=now, s=s)
            after = lw.pages_digest(exports)
        except Exception as err:  # noqa: BLE001 - after the reservation every failure is the spent REFUSED line
            raise SpentRefused(f"after the reservation ({os.path.relpath(held)}), the score stopped: "
                               f"{'' if isinstance(err, lw.WindowRefused) else type(err).__name__ + ': '}{err}; the "
                               "reservation stands and the confirmation's one read is spent (released only by the "
                               "architect's ruling); nothing recorded") from err
    try:
        sha_after, sides_after = lr.copy_state(path)
    except ReadRefused as err:
        raise SpentRefused(f"after the reservation ({os.path.relpath(held)}): {err}; the reservation stands and the "
                           "read is spent; nothing recorded") from err
    if after["digest"] != pages["digest"] or sha_after != sha or sides_after:
        raise SpentRefused(f"after the reservation ({os.path.relpath(held)}): "
                           + ("the pages changed during the read" if after["digest"] != pages["digest"] else
                              "the copy changed during the read" if sha_after != sha else
                              f"a sidecar appeared beside the copy ({', '.join(sides_after)})")
                           + "; the reservation stands and the read is spent; nothing recorded")
    if (r["match_ids"] != w["members"] or r.get(lw.LAST_MEMBER) != w.get(lw.LAST_MEMBER)
            or r.get(lw.FIRST_MEMBER) != w.get(lw.FIRST_MEMBER) or r.get(lw.REDATED) != w.get(lw.REDATED)):
        raise SpentRefused(f"after the reservation ({os.path.relpath(held)}): the score's confirmation is not the "
                           "read's; the reservation stands and the read is spent; nothing recorded")
    return result(code, e, w, r, sha, pages, word, fp, now, held)


def result(code, e, w, r, sha, pages, word, fp, now, held) -> dict:
    """The confirmation's `result` (the module docstring), JSON text throughout."""
    reg = _reg()
    a = r["audit"]
    first_id, first_ko = r[lw.FIRST_MEMBER]
    out = {"command": COMMAND, "code": code, "n": r["n"],
           "log_loss": r["ll_candidate"], "reference_log_loss": r["ll_close"],
           "first_game_at": lr._iso(first_ko), "first_game_id": first_id,
           "members_in_order": list(r["match_ids"]),
           "opening": lr._jsonable(lw._run_result(e).get(lw.OPENING_FIELD)),
           "took_no_slot": [{"match_id": i, "kickoff": lr._iso(ko), "cause": c} for i, ko, c in r[lw.TOOK_NO_SLOT]],
           "redated_findings": [{"match_id": i, "kickoff": lr._iso(ko), "status": st}
                                for i, ko, st in r.get(lw.REDATED) or []],
           "redated_no_slot": [{"match_id": i, "recorded_kickoff": lr._iso(rk), "kickoff": lr._iso(ko), "status": st}
                               for i, rk, ko, st in r.get(lw.REDATED_NO_SLOT) or []],
           "audit": lr._jsonable(a), "audit_lines": lw.audit_lines(code, a),
           "frozen_constants": dict(r["constants"]), "ruled_exclusions": lr._jsonable(e.get(lw.RULED_FIELD) or []),
           "copy_sha256": sha, "pages": dict(pages), "architect_word": word, "confirmation_fingerprint": fp,
           "read_clock": lr._iso(now), "first_allowed_date": lr.first_allowed(w).isoformat(),
           "window_ids_sha256": (e.get("run") or {}).get("ids_sha256"),
           "reservation": os.path.relpath(held, reg.ROOT)}
    try:
        json.dumps(out, allow_nan=False)
    except (TypeError, ValueError) as err:
        raise SpentRefused(f"the confirmation could not be written as JSON ({err}); the reservation stands and the "
                           "read is spent; nothing recorded") from err
    return out


def run_lines(res: dict) -> list[str]:
    """The read's console: both figures unrounded and the rule the registry computes by; the opening, the first game,
    the counts of the reached games that took no slot and of the findings, the audit lines. The outcome is the
    registry's, printed after it records."""
    from collections import Counter
    causes = Counter(x["cause"] for x in res["took_no_slot"])
    p = res["pages"]
    return ([f"  read: the copy sha256 {res['copy_sha256']} and the pages ({p['pages']} · first {p['first']} · last "
             f"{p['last']} · digest {p['digest']}) found unchanged after the score",
             f"  n={res['n']} · candidate mean log-loss {res['log_loss']!r} · the close's {res['reference_log_loss']!r}"
             " · CONFIRMED iff the candidate's is strictly below the close's; a tie fails (computed by the registry)",
             f"  the opening (447 C1, the run record's): after match {res['opening']['match_id']} at "
             f"{res['opening']['kickoff']} · the first game: match {res['first_game_id']} at {res['first_game_at']}",
             f"  reached and took no slot, by id in the result: {len(res['took_no_slot'])}"
             + ("" if not causes else " — " + ", ".join(f"{k} {v}" for k, v in sorted(causes.items()))),
             f"  not accounted for by the run record, in neither cohort (447 C1(d)): {len(res['redated_findings'])} "
             "finding(s) · took no slot in "
             f"the window, re-dated, still at or before the opening: {len(res['redated_no_slot'])}"]
            + res["audit_lines"])


def record(code: str, res: dict, ruling: str) -> dict:
    """registry.record_confirmation on the 60 members, the result and the ruling: the outcome computed there."""
    reg = _reg()
    return reg.record_confirmation(lw.DECLARATION_IDS[code], list(res["members_in_order"]), res, ruling, reg.LEDGER,
                                   reg.IDS_DIR)


def recorded_line(e: dict) -> str:
    eid = e["id"]
    return (f"RECORDED: {e['confirmation']['outcome']} · status {e['status']} — commit docs/registry/ (experiments.json, "
            f"ids/{eid}.confirm.txt, {eid}{SUFFIX}) on laptop/{eid}-confirmation-record")
