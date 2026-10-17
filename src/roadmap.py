"""The model roadmap (ARCHITECT 2026-10-13 10:12 ET, addendum 59 item 5, Issue #486).

The operator, 2026-10-13 09:46 ET, verbatim: "It's a P1 for any sport where we don't have a prediction model. We need
to track ETA's on when we're going to be live and hold ourselves accountable. Otherwise, we're just building a really
expensive market extrapolation service"

(a), verbatim: "A model lane is a lane whose exit is a prediction model live on a competition that has none, or a term
the live model lacks while a hold waits on it. Live means the Desk may make a call on the competition from the model's
number."

(c) The fence, verbatim: "A date on the roadmap is a commitment to do the step, never to its outcome. No date is a
reason to move a bar, to shorten a confirmation, to run anything before its declaration says, or to shorten a review.
A run that fails moves its lane to the next candidate, and the roadmap says so the same day."

(d) The file is docs/roadmap.json: tracked, never under data/, changed only in a PR that quotes the ruling for the
change. One entry per model lane: lane (a short id, unique), title, issue, registry_id (or null), state, steps (what,
owner, due, done: null or {date, receipt}), earliest_live (a date or null), live_needs, vs_close, moved (a list of
{moved_on, which, was, now, why, ruling}). The rules, verbatim:
"A lane's next step is its first step not done. A step is overdue when its due date is before today and it is not
done."
"A due date or an earliest-live date changes only by my ruling, entered in the lane's moved list: the day it was moved,
which date, what it was, what it is now, why, and the addendum and item. The earlier date is never erased."

(e) `python cli.py roadmap` prints it: read-only, no database, no network. Per lane, in the file's order, its title,
Issue, state, earliest live and record against the close, then its next step with "in N days", "today" or "OVERDUE N
days"; then every milestone of .github/ledger/taxonomy.json that has a due_on; then how many are overdue. It exits 0
whatever is overdue; a file that does not validate exits 2 and names the entry. validate() is the ruled validation,
run on the real file by tests/test_roadmap.py so a bad file cannot merge.

THE BASE CHECK (ARCHITECT 2026-10-13 11:08 ET, addendum 60 item 3, #490; one sentence replaced by addendum 61 item 4,
13:11 ET), verbatim: "A pull request that changes docs/roadmap.json is checked against the file on its base. For each
lane both sides hold, by its lane id: an earliest_live that differs, and a due that differs on a step both sides hold,
needs a moved line on the head. A step is the same step where its what is the same, word for word. The moved line's
which is the word earliest_live, or the step's what, word for word; its was is the base's date and its now is the
head's. A date set where the base had none needs no moved line. An earliest_live cleared needs its moved line, with now
null. A lane or a step that only one side holds needs nothing from this check: the ruling the pull request quotes
carries it, and I read it. The check fails the pull request and names the lane and the date. It never rewrites the
file." And: "within a lane no two steps share a what." Where: beside check-fragments, in the job that already reads the
base (`python scripts/ledger.py check-roadmap --base REF`).

#492 RULED (addendum 61 item 4), verbatim: "Setting a first earliest_live is not a move and needs no moved line.
Clearing one is a move, and it is how a failed run is written: its moved line has which earliest_live, was the date,
now null, and why. In a moved line now may be null where which is earliest_live; was is always a real date. A step's
due is never cleared: a step is done, moved, or removed by a quoted ruling."

#504 RULED (ARCHITECT 2026-10-13 16:37 ET, addendum 62 item 3), verbatim: "Every moved line the base holds is on the head,
word for word, and in the base's order; the head only appends. A moved line changed or removed fails the pull request,
and the refusal names the lane and the line. A lane only one side holds needs nothing from this: the ruling the pull
request quotes carries it, and I read it." Why: "'The earlier date is never erased' (addendum 59 item 5(d)) is a
sentence about the record, and the record is the moved list."

THE COMPETITIONS FIELD (ARCHITECT 2026-10-17 10:35 ET, addendum 111 item 2, #575), verbatim: "roadmap.json: each lane
gains `competitions: [codes]` (a data-only roadmap change; I rule it in — the lane text is unchanged). Nations League
[UNL]; La Liga [PD]; the four-league lane [SA, BL1, FL1, ELC]; College [NCAA]; Hockey [NHL]; Cups [CL, EFL, UEL]; NFL
QB [NFL]; MLB pitcher [MLB]." Optional in the validation (OPTIONAL_LANE_KEYS): where a lane carries it, it is a
non-empty list of competition codes as the DB stores them, each named once. The print does not show it; `python cli.py
coverage` reads it (a lane names a competition through it, never through its prose). The base check compares dates and
moved lines only, so adding it moves nothing.

Addendum 61 item 5: "#494 is in: a milestone with no due_on key is refused, named." And: "One day is singular: 'in 1
day', 'OVERDUE 1 day', '(+1 more step overdue)'. Addendum 59 5(e) named the pattern, not the grammar."

Pure: reads two tracked JSON files, writes nothing. The base check reads the base's file through `git show`.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROADMAP_PATH = ROOT / "docs" / "roadmap.json"
ROADMAP_REL = "docs/roadmap.json"          # the path git reads on the base
TAXONOMY_PATH = ROOT / ".github" / "ledger" / "taxonomy.json"

STATES = ("to declare", "declared", "confirming", "blocked", "live", "closed")
OWNERS = ("architect", "operator", "code", "calendar")
LANE_KEYS = ("lane", "title", "issue", "registry_id", "state", "steps", "earliest_live", "live_needs", "vs_close",
             "moved")
OPTIONAL_LANE_KEYS = ("competitions",)     # addendum 111 item 2 (#575): the competition codes the lane is for
STEP_KEYS = ("what", "owner", "due", "done")
DONE_KEYS = ("date", "receipt")
# the day it was moved, which date, what it was, what it is now, why, and the addendum and item
MOVED_PARTS = ("moved_on", "which", "was", "now", "why", "ruling")


_YMD = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


class RoadmapError(ValueError):
    """A file that does not validate: the message names the entry."""


def real_date(v) -> date | None:
    """A real date written YYYY-MM-DD, else None ('2026-02-30', '2026-1-5' and the ISO week '2026-W01-1', which
    date.fromisoformat would read as 2025-12-29, are not)."""
    if not isinstance(v, str) or not _YMD.fullmatch(v):
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        return None


def _text(v) -> bool:
    """Non-empty text the print can write (a lone surrogate from a JSON escape cannot be written: not text)."""
    if not isinstance(v, str) or not v.strip():
        return False
    try:
        v.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _done(step: dict) -> bool:
    return step.get("done") is not None


def validate(doc) -> list[str]:
    """The ruled validation, one message per problem, each naming its entry. [] when the file validates."""
    if not isinstance(doc, dict) or not isinstance(doc.get("lanes"), list):
        return ["the file: no 'lanes' list"]
    errs: list[str] = []
    seen: set[str] = set()
    for i, ln in enumerate(doc["lanes"], 1):
        if not isinstance(ln, dict):
            errs.append(f"lane {i}: not an object")
            continue
        name = f"lane {ln.get('lane')!r}" if _text(ln.get("lane")) else f"lane {i}"
        missing = [k for k in LANE_KEYS if k not in ln]
        if missing:
            errs.append(f"{name}: missing {', '.join(missing)}")
            continue
        if not _text(ln["lane"]):
            errs.append(f"{name}: no lane id")
        elif ln["lane"] in seen:
            errs.append(f"{name}: lane id not unique")
        else:
            seen.add(ln["lane"])
        if not _text(ln["title"]):
            errs.append(f"{name}: no title")
        if not isinstance(ln["issue"], int) or isinstance(ln["issue"], bool):
            errs.append(f"{name}: issue {ln['issue']!r} is not an integer")
        if ln["registry_id"] is not None and not _text(ln["registry_id"]):
            errs.append(f"{name}: registry_id {ln['registry_id']!r} is neither null nor an id")
        if "competitions" in ln:           # addendum 111 item 2 (#575): optional, the codes the lane is for
            cs = ln["competitions"]
            if not isinstance(cs, list) or not cs or any(not _text(x) or x != x.strip() for x in cs):
                errs.append(f"{name}: competitions {cs!r} is not a list of competition codes")
            elif len(set(cs)) != len(cs):
                errs.append(f"{name}: competitions {cs!r} names a code twice")
        if ln["state"] not in STATES:
            errs.append(f"{name}: state {ln['state']!r} is not one of {', '.join(STATES)}")
        for k in ("live_needs", "vs_close"):
            if not _text(ln[k]):
                errs.append(f"{name}: no {k}")
        steps = ln["steps"]
        if not isinstance(steps, list):
            errs.append(f"{name}: steps is not a list")
            steps = []
        dues: list[tuple[int, date]] = []
        whats: dict[str, int] = {}
        for j, st in enumerate(steps, 1):
            sname = f"{name} step {j}"
            if not isinstance(st, dict):
                errs.append(f"{sname}: not an object")
                continue
            miss = [k for k in STEP_KEYS if k not in st]
            if miss:
                errs.append(f"{sname}: missing {', '.join(miss)}")
                continue
            if not _text(st["what"]):
                errs.append(f"{sname}: no what")
            elif st["what"] in whats:      # addendum 60 item 3: "within a lane no two steps share a what"
                errs.append(f"{sname}: what {st['what']!r} is step {whats[st['what']]}'s too (within a lane no two "
                            "steps share a what)")
            else:
                whats[st["what"]] = j
            if st["owner"] not in OWNERS:
                errs.append(f"{sname}: owner {st['owner']!r} is not one of {', '.join(OWNERS)}")
            due = real_date(st["due"])
            if due is None:
                errs.append(f"{sname}: due {st['due']!r} is not a real date (YYYY-MM-DD)")
            else:
                dues.append((j, due))
            done = st["done"]
            if done is not None:
                if not isinstance(done, dict) or any(k not in done for k in DONE_KEYS):
                    errs.append(f"{sname}: done is neither null nor {{date, receipt}}")
                else:
                    if real_date(done["date"]) is None:
                        errs.append(f"{sname}: done date {done['date']!r} is not a real date (YYYY-MM-DD)")
                    if not _text(done["receipt"]):
                        errs.append(f"{sname}: done with no receipt")
        for (j0, d0), (j1, d1) in zip(dues, dues[1:]):
            if d1 < d0:
                errs.append(f"{name} step {j1}: due {d1} goes backwards from step {j0}'s {d0}")
        if ln["state"] not in ("live", "closed") and not any(isinstance(st, dict) and not _done(st) for st in steps):
            errs.append(f"{name}: state {ln['state']!r} and no step left to do")
        el = ln["earliest_live"]
        if el is not None:
            eld = real_date(el)
            if eld is None:
                errs.append(f"{name}: earliest_live {el!r} is not a real date (YYYY-MM-DD)")
            elif dues and eld < dues[-1][1]:
                errs.append(f"{name}: earliest_live {eld} is before the last step's due date {dues[-1][1]}")
        moved = ln["moved"]
        if not isinstance(moved, list):
            errs.append(f"{name}: moved is not a list")
            continue
        for k, mv in enumerate(moved, 1):
            mname = f"{name} moved {k}"
            if not isinstance(mv, dict):
                errs.append(f"{mname}: not an object")
                continue
            # addendum 61 item 4: "In a moved line now may be null where which is earliest_live; was is always a real date."
            cleared = mv.get("which") == "earliest_live" and "now" in mv and mv["now"] is None
            miss = [p for p in MOVED_PARTS if not _text(mv.get(p)) and not (p == "now" and cleared)]
            if miss:
                errs.append(f"{mname}: missing {', '.join(miss)} (six parts: {', '.join(MOVED_PARTS)})")
                continue
            for p in ("moved_on", "was", "now"):
                if not (p == "now" and cleared) and real_date(mv[p]) is None:
                    errs.append(f"{mname}: {p} {mv[p]!r} is not a real date (YYYY-MM-DD)")
    return errs


def validate_milestones(tax) -> list[str]:
    """The taxonomy as the print reads it: an object whose milestones are a list of objects, each with a title, and
    a due_on key that is null or a real date."""
    if not isinstance(tax, dict):
        return ["the taxonomy: not an object"]
    ms = tax.get("milestones")
    if not isinstance(ms, list):
        return ["the taxonomy: no 'milestones' list"]
    errs = []
    for i, m in enumerate(ms, 1):
        if not isinstance(m, dict):
            errs.append(f"milestone {i}: not an object")
            continue
        if not _text(m.get("title")):
            errs.append(f"milestone {i}: no title")
        if "due_on" not in m:                  # addendum 61 item 5 (#494): "a milestone with no due_on key is refused, named"
            errs.append(f"milestone {m['title']!r}: no due_on" if _text(m.get("title")) else f"milestone {i}: no due_on")
        elif m["due_on"] is not None and real_date(m["due_on"]) is None:
            errs.append(f"milestone {m.get('title')!r}: due_on {m['due_on']!r} is not a real date (YYYY-MM-DD)")
    return errs


def _read(path: Path, what: str):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError) as e:
        raise RoadmapError(f"{what} {path}: cannot be read as JSON ({type(e).__name__})") from None


def load(path: Path | None = None) -> dict:
    """The roadmap file, validated; RoadmapError naming the entry otherwise."""
    p = Path(path or ROADMAP_PATH)
    doc = _read(p, "the roadmap")
    errs = validate(doc)
    if errs:
        raise RoadmapError(f"{p}: " + "; ".join(errs))
    return doc


def next_step(lane: dict) -> tuple[int, dict] | None:
    """"A lane's next step is its first step not done." (1-based index, step), or None."""
    return next(((j, st) for j, st in enumerate(lane["steps"], 1) if not _done(st)), None)


def overdue_steps(lane: dict, today: date) -> list[int]:
    """"A step is overdue when its due date is before today and it is not done." Their 1-based indexes."""
    return [j for j, st in enumerate(lane["steps"], 1) if not _done(st) and real_date(st["due"]) < today]


def _days(n: int) -> str:
    """Addendum 61 item 5: "One day is singular"."""
    return f"{n} day" if n == 1 else f"{n} days"


def when(due: date, today: date) -> str:
    """The ruled forms: "in N days", "today" or "OVERDUE N days"; one day is singular, "in 1 day", "OVERDUE 1 day"."""
    n = (due - today).days
    if n == 0:
        return "today"
    return f"in {_days(n)}" if n > 0 else f"OVERDUE {_days(-n)}"


def report(today: date, path: Path | None = None, taxonomy_path: Path | None = None) -> tuple[list[str], int]:
    """The print's lines and the overdue count. RoadmapError (naming the entry) when a file does not validate."""
    p = Path(path or ROADMAP_PATH)
    doc = load(p)
    tp = Path(taxonomy_path or TAXONOMY_PATH)
    tax = _read(tp, "the ledger taxonomy")
    errs = validate_milestones(tax)
    if errs:
        raise RoadmapError(f"{tp}: " + "; ".join(errs))
    lines = [f"ROADMAP {p.name} · today {today.isoformat()} · {len(doc['lanes'])} model lanes"]
    overdue = 0
    for ln in doc["lanes"]:
        el = ln["earliest_live"] or "not set"
        lines.append(f"{ln['title']} · #{ln['issue']} · {ln['state']} · earliest live {el} · "
                     f"vs close: {ln['vs_close']}")
        late = overdue_steps(ln, today)
        overdue += len(late)
        nx = next_step(ln)
        if nx is None:
            lines.append(f"  next: none ({ln['state']})")
            continue
        j, st = nx
        more = len([k for k in late if k != j])
        tail = f" (+{more} more step{'' if more == 1 else 's'} overdue)" if more else ""
        lines.append(f"  next: {st['what']} · {st['owner']} · due {st['due']} · "
                     f"{when(real_date(st['due']), today)}{tail}")
    dated = [m for m in tax["milestones"] if m.get("due_on")]
    lines.append(f"MILESTONES ({tp.parent.name}/{tp.name}, those with a due_on)")
    for m in dated:
        d = real_date(m["due_on"])
        overdue += d < today
        lines.append(f"  {m['title']} · {m['due_on']} · {when(d, today)}")
    lines.append(f"overdue: {overdue}")
    return lines, overdue


# --------------------------------------------------------------------------------------------- the base check --

def _written(lines: list[dict], used: set, which: str, was, now) -> bool:
    """A moved line the head adds, not yet the line of another move (Codex on #503: one line records one move): which
    word for word, was the base's date, now the head's (null for a cleared earliest_live). Takes the line."""
    for i, mv in enumerate(lines):
        if i not in used and mv.get("which") == which and mv.get("was") == was and "now" in mv and mv["now"] == now:
            used.add(i)
            return True
    return False


def _added_lines(head_moved: list, base_moved) -> list[dict]:
    """The moved lines the head adds: its list less the base's, line for line. A line already on the base was written
    for an earlier move and is never the line of this one (a second failed run is written again)."""
    left = [mv for mv in base_moved if isinstance(mv, dict)] if isinstance(base_moved, list) else []
    added = []
    for mv in head_moved:
        if not isinstance(mv, dict):
            continue
        if mv in left:
            left.remove(mv)
        else:
            added.append(mv)
    return added


def _line(mv) -> str:
    """A moved line as a refusal names it."""
    if not isinstance(mv, dict):
        return json.dumps(mv, default=str)
    return (f"(moved_on {mv.get('moved_on')!r}, which {mv.get('which')!r}, was {mv.get('was')!r}, "
            f"now {json.dumps(mv.get('now'))})")


def _kept_lines(name: str, head_moved: list, base_moved) -> list[str]:
    """Addendum 62 item 3 (#504): "Every moved line the base holds is on the head, word for word, and in the base's
    order; the head only appends." One message per base line that is not at its place, naming the lane and the line."""
    if not isinstance(base_moved, list):
        return []
    errs = []
    for k, mv in enumerate(base_moved, 1):
        if k <= len(head_moved) and head_moved[k - 1] == mv:
            continue
        if mv in head_moved:
            errs.append(f"{name} moved {k}: the base's line {_line(mv)} is on the head out of the base's order "
                        f"(the head only appends)")
        else:
            errs.append(f"{name} moved {k}: the base's line {_line(mv)} is changed or removed on the head "
                        f"(every moved line the base holds stays, word for word)")
    return errs


def check_moves(base, head) -> list[str]:
    """Addendum 60 item 3 as amended by addendum 61 item 4: every date the head moves from the base has its moved line
    on the head, a line the head adds. Addendum 62 item 3: every moved line the base holds is on the head, word for
    word, in the base's order. One message per date without its line and per base line not kept, naming the lane and
    the date or the line. [] when every move is written and every line kept. `head` is a file that validates; `base`
    is the base's file as read (None where the base has none)."""
    if not isinstance(base, dict) or not isinstance(base.get("lanes"), list):
        return []
    blanes: dict = {}
    for ln in base["lanes"]:
        if isinstance(ln, dict) and _text(ln.get("lane")):
            blanes.setdefault(ln["lane"], ln)
    errs = []
    for ln in head["lanes"]:
        b = blanes.get(ln["lane"])
        if b is None:                      # "A lane ... that only one side holds needs nothing from this check"
            continue
        name = f"lane {ln['lane']!r}"
        errs += _kept_lines(name, ln["moved"], b.get("moved"))   # "A lane only one side holds needs nothing from this"
        lines, used = _added_lines(ln["moved"], b.get("moved")), set()
        bel, hel = b.get("earliest_live"), ln["earliest_live"]
        # "A date set where the base had none needs no moved line." Moved or cleared needs one.
        if real_date(bel) is not None and bel != hel and not _written(lines, used, "earliest_live", bel, hel):
            now = "null (cleared)" if hel is None else hel
            errs.append(f"{name}: earliest_live {bel} -> {now} has no moved line on the head "
                        f"(which 'earliest_live', was {bel!r}, now {json.dumps(hel)})")
        bsteps: dict = {}
        for st in b.get("steps") if isinstance(b.get("steps"), list) else []:
            if isinstance(st, dict) and isinstance(st.get("what"), str):
                bsteps.setdefault(st["what"], st)   # "the same step where its what is the same, word for word"
        for j, st in enumerate(ln["steps"], 1):
            bs = bsteps.get(st["what"])
            if bs is None or real_date(bs.get("due")) is None:   # "... or a step that only one side holds"; a due
                continue                   # set where the base had none needs no moved line
            if bs["due"] != st["due"] and not _written(lines, used, st["what"], bs["due"], st["due"]):
                errs.append(f"{name} step {j}: due {bs.get('due')} -> {st['due']} has no moved line on the head "
                            f"(which {st['what']!r}, was {bs.get('due')!r}, now {st['due']!r})")
    return errs


def _git(root: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def check_base(base_ref: str, root: Path | None = None, echo=print) -> int:
    """The CI step: the head's docs/roadmap.json (the working tree) against the file on its base, read where the head
    branched from `base_ref` (their merge-base, as check-fragments' `base...HEAD`), so a date the base moved after the
    branch point is never charged to the pull request. 0 when the file is unchanged or every move has its moved line;
    1 naming each lane and date otherwise, or a head that cannot be read or does not validate; 2 when the base cannot
    be read. Never writes the file."""
    root = Path(root or ROOT)
    rel = ROADMAP_REL
    if _git(root, "rev-parse", "--verify", "--quiet", f"{base_ref}^{{commit}}").returncode != 0:
        echo(f"✗ ROADMAP: the base {base_ref!r} is not a commit here: nothing can be compared")
        return 2
    mb = _git(root, "merge-base", base_ref, "HEAD")
    if mb.returncode != 0 or not mb.stdout.strip():
        echo(f"✗ ROADMAP: the head has no merge-base with {base_ref}: nothing can be compared")
        return 2
    point = mb.stdout.strip()
    at = f"{base_ref} (merge-base {point[:7]})"
    head_path = root / rel
    head_bytes = head_path.read_bytes() if head_path.exists() else None
    shown = subprocess.run(["git", "-C", str(root), "show", f"{point}:{rel}"], capture_output=True)
    if shown.returncode != 0:
        if _git(root, "cat-file", "-e", f"{point}:{rel}").returncode != 0:
            echo(f"✓ ROADMAP: {rel} is not on the base {at}: nothing to compare")
            return 0
        echo(f"✗ ROADMAP: {rel} on {at} cannot be read: {shown.stderr.decode('utf-8', 'replace').strip()}")
        return 2
    if head_bytes == shown.stdout:
        echo(f"✓ ROADMAP: {rel} is unchanged against {at}")
        return 0
    if head_bytes is None:
        echo(f"✗ ROADMAP: {rel} is on the base {at} and not on the head")
        return 1
    try:
        head_text = head_bytes.decode("utf-8")
    except UnicodeDecodeError as e:
        echo(f"✗ ROADMAP: the head's {rel} is not UTF-8 ({e.reason} at byte {e.start})")
        return 1
    try:
        base_text = shown.stdout.decode("utf-8")
    except UnicodeDecodeError as e:
        echo(f"✗ ROADMAP: {rel} on {at} is not UTF-8 ({e.reason} at byte {e.start})")
        return 2
    try:
        head = json.loads(head_text)
    except (ValueError, RecursionError) as e:
        echo(f"✗ ROADMAP: the head's {rel} cannot be read as JSON ({type(e).__name__})")
        return 1
    errs = validate(head)
    if errs:
        for e in errs:
            echo(f"✗ ROADMAP: the head's {rel} does not validate: {e}")
        return 1
    try:
        base = json.loads(base_text)
    except (ValueError, RecursionError) as e:
        echo(f"✗ ROADMAP: {rel} on {at} cannot be read as JSON ({type(e).__name__})")
        return 2
    fails = check_moves(base, head)
    if fails:
        for f in fails:
            echo(f"✗ ROADMAP: {f}")
        echo("  A date moves only with its moved line, and every moved line the base holds stays on the head, word for "
             "word, in its order (ARCHITECT 2026-10-13, addendum 60 item 3; addendum 61 item 4; addendum 62 item 3).")
        return 1
    echo(f"✓ ROADMAP: every date {rel} moves against {at} has its moved line, and every moved line the base holds "
         "is kept")
    return 0
