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

Pure: reads two tracked JSON files, writes nothing.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROADMAP_PATH = ROOT / "docs" / "roadmap.json"
TAXONOMY_PATH = ROOT / ".github" / "ledger" / "taxonomy.json"

STATES = ("to declare", "declared", "confirming", "blocked", "live", "closed")
OWNERS = ("architect", "operator", "code", "calendar")
LANE_KEYS = ("lane", "title", "issue", "registry_id", "state", "steps", "earliest_live", "live_needs", "vs_close",
             "moved")
STEP_KEYS = ("what", "owner", "due", "done")
DONE_KEYS = ("date", "receipt")
# the day it was moved, which date, what it was, what it is now, why, and the addendum and item
MOVED_PARTS = ("moved_on", "which", "was", "now", "why", "ruling")


class RoadmapError(ValueError):
    """A file that does not validate: the message names the entry."""


def real_date(v) -> date | None:
    """A real date written YYYY-MM-DD, else None ('2026-02-30' and '2026-1-5' are not)."""
    if not isinstance(v, str) or len(v) != 10:
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        return None


def _text(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


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
            miss = [p for p in MOVED_PARTS if not _text(mv.get(p))]
            if miss:
                errs.append(f"{mname}: missing {', '.join(miss)} (six parts: {', '.join(MOVED_PARTS)})")
                continue
            for p in ("moved_on", "was", "now"):
                if real_date(mv[p]) is None:
                    errs.append(f"{mname}: {p} {mv[p]!r} is not a real date (YYYY-MM-DD)")
    return errs


def validate_milestones(tax) -> list[str]:
    """Each milestone that has a due_on: a real date."""
    errs = []
    for m in (tax or {}).get("milestones") or []:
        if m.get("due_on") is not None and real_date(m["due_on"]) is None:
            errs.append(f"milestone {m.get('title')!r}: due_on {m['due_on']!r} is not a real date (YYYY-MM-DD)")
    return errs


def _read(path: Path, what: str):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise RoadmapError(f"{what} {path}: cannot be read as JSON ({e})") from None


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


def when(due: date, today: date) -> str:
    n = (due - today).days
    if n == 0:
        return "today"
    unit = "day" if abs(n) == 1 else "days"
    return f"in {n} {unit}" if n > 0 else f"OVERDUE {-n} {unit}"


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
        tail = f" (+{more} more step{'s' if more != 1 else ''} overdue)" if more else ""
        lines.append(f"  next: {st['what']} · {st['owner']} · due {st['due']} · "
                     f"{when(real_date(st['due']), today)}{tail}")
    dated = [m for m in tax.get("milestones") or [] if m.get("due_on")]
    lines.append(f"MILESTONES ({tp.parent.name}/{tp.name}, those with a due_on)")
    for m in dated:
        d = real_date(m["due_on"])
        overdue += d < today
        lines.append(f"  {m['title']} · {m['due_on']} · {when(d, today)}")
    lines.append(f"overdue: {overdue}")
    return lines, overdue
