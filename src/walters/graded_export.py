"""THE GRADED EXPORT ON A RESULTS ROW (#755).

ARCHITECT 2026-11-01 09:00 ET (addendum 196 item 4(i)), verbatim: "(i) the results row names the export it graded (the
closing run's run_id and exported_at) — the closing row stands over the slate row by design (#632's rule), but the
grade must say which row it took; an Issue, size:S." ARCHITECT 2026-11-01 13:15 ET (addendum 200 item 2), verbatim:
"#755 (policy lane, ruled in addendum 196 item 4(i)): build it today as its own small PR — each graded results row
carries the graded export's run_id and exported_at; read-side naming only; no grade, threshold or Desk rule moves; the
tests pin the two keys on a closing row and on a slate row of one game."

WHAT THE GRADE READS (law 1): export_results grades from the DATABASE. result_row builds a row from the stored
prediction, its prediction_outcomes row and the match (the close from close.grading_close_block); no export file is
opened to grade it. The one place export_results reads export files is the void rule (redated.label_rows, the closing
files by match id). So the naming here is the narrowest faithful one the ruling allows: the export file whose row the
results row stands behind, chosen by #632's rule (R1, verbatim: "the closing file's row stands over any slate row for
its games") with the void rule's own selection (exec_cohorts.tally; pl_positive_edge_receipt.final_call):

- CLOSING: the match's rows in <exports>/closing_*.json (redated.closing_rows, the one reader; host/ is never read):
  the newest run's row whose recorded start (the row's utc_date) is within desk_policy.DESK_CLOCK_DRIFT of the match's
  current start, else the newest run's row (the one a re-dated label reads). run_id is the file's closing block's
  run_id; exported_at is the file's top-level exported_at (the run export's own, which closing.closing_doc keeps).
- SLATE, only where no closing file names the match: the Desk slate exports in <exports> (<sport>_*.json, the slate
  names closing.FAMILIES' export_glob gives: mlb_MLB_*, soccer_PL_*, nfl_predictions_*; the top level a predictions
  list, a desk_meta block, no closing block, its sport the results' sport: coverage's slate kind, where a file with no
  desk calls never stands), the same selection by the file's exported_at, then its name. exported_at is the file's
  top-level exported_at. run_id is None: a slate file carries no run id (the slate run's id is in its logs/ copy's
  name only, closing.slate_steps and link_slate_file), and none is made up (law 4).
- NEITHER: every key None.

The block, under KEY on every results row: {"kind": "closing" | "slate" | None, "file": the file's name, "run_id",
"exported_at"}, each value as the file holds it. A file that cannot be read is counted ("unreadable"), never fatal.
Read-only: nothing is written, no grade, threshold, Desk rule or existing field moves.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.walters import desk_policy
from src.walters.redated import CLOSING_GLOB, as_utc, closing_rows

KEY = "graded_export"
CLOSING, SLATE = "closing", "slate"


def _pick(entries: list, current):
    """The void rule's selection (exec_cohorts.tally): over entries (sort key, row, source) oldest first, the newest
    whose row's recorded start is within the Desk's clock drift of the match's current start, else the newest. None
    with no entry."""
    if not entries:
        return None
    cur = as_utc(current)
    if cur is not None:
        near = [e for e in entries
                if (st := as_utc(e[1].get("utc_date"))) is not None and abs(cur - st) <= desk_policy.DESK_CLOCK_DRIFT]
        if near:
            return near[-1]
    return entries[-1]


def slate_rows(exports_dir, sport: str) -> dict:
    """The Desk slate exports' rows by match id: {"rows": {match id: [(exported_at, file name, row, source), ...]
    oldest first}, "files": n read, "unreadable": [names]}. A file is a slate of `sport` (the Sport's value) when its
    name is <sport>_*.json and not a closing file, and its top level is a dict with a predictions list, a desk_meta
    dict, no closing block and sport == `sport`; any other file is not a slate (never counted). source = {"file",
    "run_id": None, "exported_at": the file's own}. Writes nothing."""
    d = Path(exports_dir)
    rows: dict[int, list] = {}
    files, bad = 0, []
    for p in sorted(d.glob(f"{sport}_*.json")) if d.is_dir() else []:
        if p.match(CLOSING_GLOB):
            continue
        try:
            doc = json.loads(p.read_text())
        except (OSError, ValueError):
            bad.append(p.name)
            continue
        if not (isinstance(doc, dict) and isinstance(doc.get("predictions"), list)
                and isinstance(doc.get("desk_meta"), dict) and "closing" not in doc and doc.get("sport") == sport):
            continue
        files += 1
        at = doc.get("exported_at")
        src = {"file": p.name, "run_id": None, "exported_at": at}
        key = (as_utc(at) is not None, as_utc(at) or datetime.min, p.name)
        for r in doc["predictions"]:
            if isinstance(r, dict) and isinstance(r.get("match_id"), int) and not isinstance(r.get("match_id"), bool):
                rows.setdefault(r["match_id"], []).append((key, r, src))
    for v in rows.values():
        v.sort(key=lambda x: x[0])
    return {"rows": rows, "files": files, "unreadable": bad}


def block(kind: str | None, src: dict | None) -> dict:
    """The row's block: the kind and the source's file, run_id and exported_at (all None without a source)."""
    src = src or {}
    return {"kind": kind if src else None, "file": src.get("file"), "run_id": src.get("run_id"),
            "exported_at": src.get("exported_at")}


def name_rows(rows: list[dict], exports_dir, sport: str, date_key: str = "date") -> dict:
    """Every results row (match_id, and its match's current start under `date_key`) gains KEY, the export it stands
    behind (the module docstring's rule). Returns the counts: {"closing": n, "slate": n, "none": n, "closing_files",
    "slate_files", "unreadable": [names]}."""
    cr = closing_rows(exports_dir)
    sl = slate_rows(exports_dir, sport)
    out = {CLOSING: 0, SLATE: 0, "none": 0, "closing_files": cr["files"], "slate_files": sl["files"],
           "unreadable": sorted(cr["unreadable"] + sl["unreadable"])}
    for r in rows:
        mid, cur = r.get("match_id"), r.get(date_key)
        held = [(run, row, src) for (run, _, row), src in zip(cr["rows"].get(mid) or [], cr["exports"].get(mid) or [])]
        e = _pick(held, cur)
        kind = CLOSING
        if e is None:
            e, kind = _pick(sl["rows"].get(mid) or [], cur), SLATE
        r[KEY] = block(kind, e[2] if e else None)
        out[r[KEY]["kind"] or "none"] += 1
    return out


def counts_line(c: dict) -> str:
    """The console's line: "graded export: closing N · slate M · none K", the unreadable files named."""
    s = f"graded export: closing {c[CLOSING]} · slate {c[SLATE]} · none {c['none']}"
    if c["unreadable"]:
        s += f" (unreadable, never read: {', '.join(c['unreadable'])})"
    return s
