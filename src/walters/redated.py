"""VOID: RE-DATED. A closing row for a game later re-dated is void, never graded (#574; #568 is its sibling).

ARCHITECT 2026-10-17 09:25 ET (addendum 106 item 4), verbatim in part: "in grading and in the results/replay exports,
a closing row whose recorded start differs from the match's current utc_date by more than DESK_CLOCK_DRIFT is labelled
"void: re-dated <old start> → <new start>" and excluded from every tally; the fresh closing run on the new date is the
graded row. Test with the 50548 case verbatim." Addendum 107 item A2 restates it: "Grading, the results exports and the
replay inventory label a closing row [...] Test with 50548 verbatim (10-17 00:00Z → 10-18 21:00Z)."

The recorded start is a closing row's utc_date (the run export's row, kept unchanged by closing.closing_doc: naive UTC);
the current one is matches.utc_date. "More than" the hour, as the ruling words it: exactly DESK_CLOCK_DRIFT apart is not
void (the Desk's own hold, addendum 83 item 2, is "at or more than"). A start that is missing, unparseable or a date
with no clock is not compared. The Cockpit grades with the same rule in JS (tools/cockpit.html redatedLabel).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from src.walters import desk_policy

CLOSING_GLOB = "closing_*.json"     # addendum 40 item 2: <exports>/closing_<FAMILY>_<start>.json; host/ is never read
_CLOCK = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
_STAMP = re.compile(r"_(\d{4}-\d{2}-\d{2}T\d{4})Z\.json$")


def as_utc(v) -> datetime | None:
    """A start as naive UTC: a datetime (an aware one converted), or ISO text ("2026-10-17T00:00:00", a trailing Z or
    an offset converted, SQLite's "2026-10-18 21:00:00.000000"). None: missing, unparseable, or a date with no clock."""
    if isinstance(v, datetime):
        d = v
    elif isinstance(v, str) and _CLOCK.match(v.strip()):
        s = v.strip()
        try:
            d = datetime.fromisoformat(s[:-1] + "+00:00" if s[-1:] in ("Z", "z") else s)
        except ValueError:
            return None
    else:
        return None
    return d.astimezone(timezone.utc).replace(tzinfo=None) if d.tzinfo else d


def redated_label(recorded_start, current_utc) -> str | None:
    """The ruling's label, "void: re-dated 2026-10-17 00:00Z → 2026-10-18 21:00Z", when the two starts differ by more
    than desk_policy.DESK_CLOCK_DRIFT; else None (within the hour, or either side not compared)."""
    old, new = as_utc(recorded_start), as_utc(current_utc)
    if old is None or new is None or abs(new - old) <= desk_policy.DESK_CLOCK_DRIFT:
        return None
    return f"void: re-dated {old:%Y-%m-%d %H:%M}Z → {new:%Y-%m-%d %H:%M}Z"


def closing_starts(exports_dir) -> dict:
    """The closing rows by match id, read from <exports_dir>/closing_*.json (the host's copies under host/ carry the
    host's match ids: never read): {"rows": {match id: [(run start, recorded start), ...] oldest run first},
    "files": n read, "unreadable": [names]}. The run start is the closing block's start, else the file name's stamp
    (a row with neither sorts oldest). An unreadable file is counted, never fatal. Writes nothing."""
    d = Path(exports_dir)
    rows: dict[int, list] = {}
    files, bad = 0, []
    for p in sorted(d.glob(CLOSING_GLOB)) if d.is_dir() else []:
        try:
            doc = json.loads(p.read_text())
            preds = [r for r in doc.get("predictions") or [] if isinstance(r, dict)]
            run = as_utc((doc.get("closing") or {}).get("start"))
        except (OSError, ValueError, AttributeError, TypeError):
            bad.append(p.name)
            continue
        stamp = _STAMP.search(p.name)
        if run is None and stamp:
            run = datetime.strptime(stamp.group(1), "%Y-%m-%dT%H%M")
        files += 1
        for r in preds:
            if isinstance(r.get("match_id"), int) and not isinstance(r.get("match_id"), bool):
                rows.setdefault(r["match_id"], []).append((run, r.get("utc_date")))
    for v in rows.values():
        v.sort(key=lambda x: (x[0] is not None, x[0] or datetime.min))
    return {"rows": rows, "files": files, "unreadable": bad}


def void_label(rows, current_utc) -> str | None:
    """The match's label when it is void: it has closing rows (closing_starts' list for it), none of them within the
    rule of its current start (the fresh closing on the new date is the graded row), and its latest is re-dated by
    the rule. Else None: graded as before."""
    cur = as_utc(current_utc)
    if not rows or cur is None:
        return None
    if any(s is not None and abs(cur - s) <= desk_policy.DESK_CLOCK_DRIFT for s in (as_utc(st) for _, st in rows)):
        return None
    return redated_label(rows[-1][1], cur)


def label_rows(rows: list[dict], exports_dir, date_key: str) -> int:
    """A results export's rows (each with match_id and its match's current utc_date under `date_key`): each row whose
    match is void gains "redated", the label, and keeps every other field (the Cockpit grades the fresh call from
    them). Never "status" or "void": the Cockpit's intake reads those as a called-off game and refunds the fresh call.
    Returns how many rows were labelled."""
    cs = closing_starts(exports_dir)["rows"]
    n = 0
    for r in rows:
        lab = void_label(cs.get(r.get("match_id")), r.get(date_key))
        if lab:
            r["redated"] = lab
            n += 1
    return n
