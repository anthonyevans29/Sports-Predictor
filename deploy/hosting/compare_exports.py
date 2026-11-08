#!/usr/bin/env python3
"""Parallel-week export comparison (H0 5.4 step 12; cutover criterion
"export diffs clean on the last 3 days").

    compare_exports.py <laptop_exports_dir> <host_exports_dir> [--glob '*2026-10-08*'] [--since 3]

For every same-named JSON file in both: record counts (top-level list, or the
longest list value in a top-level object) and a field-level diff with
timestamp-like keys ignored (*_at, ts, timestamp, generated*, captured*).
The unit-bearing fields of Desk policy v1.2 (order.unit, order.text,
order.contracts, desk_meta.unit, and pool_usd at any depth) are never compared
or printed, in either mode; their count is printed (ARCHITECT 2026-10-30,
addendum 182 item 4). The shadow-arm keys of pl-availability-v1 (every
`candidate_*` key at any depth, and a results row's `candidate` arm) are never
compared or printed either, and counted on their own line beside that count
(ARCHITECT 2026-11-01, addendum 199 item 2; SHADOW-ARM KEYS below). The
graded-export keys of #755 (every key of a results row's `graded_export` object
and of the file-level `graded_exports` block) are never compared or printed,
and counted on their own line beside those two (ARCHITECT 2026-11-01, addendum
206 item 1; GRADED-EXPORT KEYS below). The rehearsal-arm keys of nfl-elo-v2
(every `rehearsal_*` key at any depth) are never compared or printed, and
counted on their own line right after the shadow-arm one (ARCHITECT 2026-11-04,
addendum 247 item 2(2); REHEARSAL-ARM KEYS below). Files
present on one side only are listed. Output is paste-ready. Exit 0 =
CLEAN (every compared file identical after the timestamp mask), 1 = DIVERGENT,
2 = ERROR (the comparison could not run: bad arguments, a side directory
missing, a crash), 3 = NO-COVERAGE (nothing was compared: zero JSON files on
both sides in the window — an empty folder, or Markdown-only dated folders).
2 and 3 are never data verdicts; CLEAN needs at least one compared file. A
"coverage:" line always counts the JSON compared and the files the glob left
out. The last line always reads "VERDICT: CLEAN|DIVERGENT|ERROR|NO-COVERAGE".
Read-only.

--since N (architect 2026-10-01; default 3): only files whose name carries a
YYYY-MM-DD date within the last N UTC days (today and the N-1 days before)
are compared, so settled exhibits stop re-printing. Files with NO date in
their name (window_24h.json, fixtures_<comp>_<label>.json) are always
compared — never hidden by the window (law 4). The skipped files are counted
on the header line, never silently dropped. --since 0 compares everything.

H1b (amended 2026-09-27): the two sides are INDEPENDENT pipelines (each
syncs from the providers itself). The explained divergence classes are
capture timing AND provider-pagination differences. Anything else is a
BACKLOG entry.

Exhibit 1 ruling (2026-09-28):
- Game rows (lists of dicts with home/away) are KEYED on (kickoff, home,
  away), never match_id (machine-local ids differ between the two DBs). Rows
  are compared field-by-field only AFTER keying; rows on one side only are
  reported BY NAME. `match_id` is masked everywhere.
- A third explained class, CODE-VERSION SKEW, is available only with its
  guard: both files carry the producing `git_sha` and the comparator names the
  mismatch. A file missing its SHA cannot claim the class (law 4).

MACHINE STATE (#592 RULED, ARCHITECT 2026-10-18, addendum 128 item 3,
verbatim): "a coverage file is MACHINE STATE by nature — each machine's own
view of the day, with `now`, `due` vs `ahead`, `started` — and can never be a
divergence. Option 1, as a KIND rule: the compare treats kind `coverage` as
"machine state": listed by presence on each side (one side, both sides,
neither), never compared for content, never DIVERGENT, never counted toward or
against criterion (a). Printed as its own line ("machine-state files: coverage
laptop yes / host no")." The kind is the exports mirror's (the name with its
date/time stamp removed): the dated coverage_<date>.json and the latest copy
coverage.json are both kind coverage. A machine-state file in the window is
never opened: it is not a `·` or `✗` line, not in the compared or the
one-side count, and cannot make a verdict (a folder holding only it is
NO-COVERAGE). One line, always printed, names its presence per side among
the files --glob and the window select (one they leave out reads no there and
is counted as not matched or settled; the Action's *.json and --since 0
select the whole folder). The --since window and the header's settled count
treat it like any dated file.
cutover_readiness.compare_day (criterion (a)) applies the same rule.

THE HOST'S TALLY (ARCHITECT 2026-11-08 07:50 ET, addendum 289 item 3,
verbatim in part: "results-tally's RESULTS.md and its JSON written on the HOST
by the morning-after chain and mirrored, so the compare morning reads one tally
per machine (the laptop's is regenerated; the host's is the record of
production)"; addendum 230 item 2(b): "a JSON beside it to the mirror as a kind
of its own"). Kind `results_tally` (exports/results_tally.json, written by
`results-tally --host-export` on the host alone; the mirror's host/<date>/ and
host/latest/ copies) is MACHINE STATE by the same rule: each machine's own tally
of its own database and its own closing files, so it can never be a
divergence; never opened, never compared, never counted, never DIVERGENT (a
folder holding only it is NO-COVERAGE). Its own kind (TALLY_KINDS) on its own
line, printed only when a tally file is among the selected files on either side
("the host's tally (machine state, never compared): results_tally laptop no /
host yes"), so the machine-state line above and every run without a tally file
read exactly as before. Its RESULTS.md is not *.json: counted as not matched,
as any Markdown is.

SHADOW-ARM KEYS (ARCHITECT 2026-11-01 12:05 ET, addendum 199 item 2, verbatim):
"THE COMPARE — option (b): a NAMED, COUNTED host-only class. compare_exports
treats every `candidate_*` key as "shadow-arm keys (host-only,
pl-availability-v1)": never compared, never printed, counted on its own line
beside the unit-bearing count (#735's pattern), so a real v22 divergence in the
same file still prints inside the budget. Its own small tooling PR after #760
(stop rule item 5), merged before the compare morning of the tag that carries
the shadow (v1.6.3). #760 itself leaves the compare untouched, as built."
#760 writes, on the host only, candidate_version, candidate_probabilities,
candidate_missing and candidate_reason on every PL slate and closing row, and a
key named `candidate` on a PL results row (pl_availability.RESULT_KEY) holding
the arm. A shadow-arm key is (shadow_arm): any key whose name starts with
"candidate_", at any depth, as ruled; and a key named exactly `candidate` ONLY
when its value (either side's) is a dict whose `version` is
"pl-availability-v1" — every value pl_availability.result_arm returns carries
that version. The test is by value, not by name alone or by parent, because
other writers use a key named `candidate` for something else
(leagues_candidate rows, soccer_expansion bindings, registry listings,
training's promote result: a string or null): those are never masked. Both
modes (the generic mask and --ignore-keys) leave the class out; a structural
mismatch printed whole shows its values as "<masked>"; the count is the file
pair's own walk (a key on either side once, past the diff limit and under
pruned keys), printed as "shadow-arm keys (host-only, pl-availability-v1): N"
right after the unit-bearing line.

GRADED-EXPORT KEYS (ARCHITECT 2026-11-01 15:45 ET, addendum 206 item 1,
verbatim): "#768 (#755, the results row names the export it graded) — RULED
option (a): a NAMED, COUNTED machine-local class in compare_exports,
"graded-export keys (machine-local)": every key of a results row's
graded_export object and of the file-level graded_exports block, never
compared, never printed as a diff, counted once per file on its own line beside
the unit-bearing (#735) and shadow-arm (#761) lines, so a real grading
divergence in the same file still prints inside the budget. The premise is
right: the laptop and the host each grade their OWN closing file, so the file
name and run id differ by nature and are not a skew." #768 writes, on every
results row of export-results and export-nfl-results (live and pre-live), a
key `graded_export` = {kind, file, run_id, exported_at}
(src/walters/graded_export.py KEY), and on the file a block `graded_exports` =
{closing, slate, none, closing_files, slate_files, unreadable} (name_rows'
counts). The class is matched by those two PARENT names exactly
(graded_export_class), at any depth: no other writer in src/, deploy/,
scripts/, tools/ or cli.py writes a key named either (law 1, read on main and on
#768's branch, 2026-11-01), so the name is exact. A key that only starts with
either name (graded_export_x) and the results row's `graded` block are compared
as before. Both modes (the generic mask and --ignore-keys) leave the class out;
a structural mismatch printed whole shows the object as "<masked>"; the count
is every key of each object, a key on either side once (graded_count: 4 per
results row, 6 for the file's block), by the file pair's own walk (past the
diff limit and under pruned keys); a parent whose value is not an object on
either side counts 1. Printed as "graded-export keys (machine-local): N" right
after the rehearsal-arm line (itself right after the shadow-arm line).
cutover_readiness.compare_day reads the same diff().

REHEARSAL-ARM KEYS (ARCHITECT 2026-11-04 09:55 ET, addendum 247 item 2(2),
verbatim): "THE COMPARE: a SEPARATE key prefix `rehearsal_*` (rehearsal_version,
rehearsal_probabilities, rehearsal_reason…), host-only, masked by
compare_exports.py under its own line "rehearsal-arm keys (host-only,
nfl-elo-v2)" beside the pl-availability line — #735's pattern, in the SAME PR (a
compare that would fail the tag on its own arm is a defect, not a question).
Never the `candidate_*` keys: those are pl-availability-v1's line and its
count." nfl-elo-v2's rehearsal arm (src/walters/nfl_rehearsal.py) writes, on the
host only, rehearsal_version, rehearsal_probabilities, rehearsal_term,
rehearsal_verdict_stamp, rehearsal_label and rehearsal_reason on an NFL slate
and closing row the window covers, `rehearsal_arm` on an NFL results row that
stores the arm, and `rehearsal_arm` in that file's record block. A
rehearsal-arm key (rehearsal_arm_key) is any key whose name starts with
"rehearsal_", at any depth, as ruled. Law 1 (read on main, 2026-11-04): no other
writer of a compared export in src/, deploy/, scripts/, tools/ or cli.py writes a
key with that prefix (sp_cutover's `rehearsal_aside` is a cutover receipt in
the receipts log, never an export), and the NFL file's top-level `rehearsal`
(false, a fossil the Cockpit reads) does not start with it and is compared as
before. Both modes leave the class out; a structural mismatch printed whole
shows its values as "<masked>"; the count is the file pair's own walk (a key on
either side once), printed as "rehearsal-arm keys (host-only, nfl-elo-v2): N"
right after the shadow-arm line. The shadow-arm line and its count are
unchanged.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# Standalone (PR #261 review): the exports mirror ships THIS file alone into
# Sports-Predictor-exports/tools/, where sp_common.py does not exist. In the
# repo, the writer of record comes from sp_common (env, host env file, .env);
# shipped, from the SP_WRITER_OF_RECORD environment variable only.
WRITERS = ("laptop", "host")
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from sp_common import writer_of_record  # noqa: E402
except ImportError:
    def writer_of_record() -> str | None:
        import os
        v = (os.environ.get("SP_WRITER_OF_RECORD") or "").strip()
        return v if v in WRITERS else None

# Exit codes — a data verdict is never confused with a broken run:
#   0 CLEAN · 1 DIVERGENT · 2 ERROR (bad arguments, a missing side, a crash) ·
#   3 NO-COVERAGE (zero files compared: never a clean verdict; PR #261 review).
EXIT_CLEAN, EXIT_DIVERGENT, EXIT_ERROR, EXIT_NO_COVERAGE = 0, 1, 2, 3

TS_KEY = re.compile(r"(_at$|^ts$|timestamp|^generated|^captured|^as_of)", re.I)
# machine-local or reported separately — never a field diff
MASKED = {"match_id", "git_sha"}
# THE UNIT-BEARING FIELDS (ARCHITECT 2026-10-30 11:20 ET, addendum 182 item 4, verbatim): "compare_exports masks the
# unit-bearing fields — order.unit, order.text, order.contracts, desk_meta.unit (and the laptop-only pool field
# wherever it appears) — compares the rest, and prints the masked count ("unit-bearing fields masked (policy v1.2):
# N"); a divergence in exec figures from fee rounding is real and still prints (no dollar in it)." Each machine reads
# its own pool (Desk policy v1.2, #732), so these differ by construction and carry a dollar figure: never printed, in
# either mode (the --ignore-keys check included), counted instead.
UNIT_BEARING = {"order": {"unit", "text", "contracts"}, "desk_meta": {"unit"}}
POOL_FIELD = "pool_usd"


def unit_bearing(parent, key) -> bool:
    """True for a field addendum 182 item 4 masks: under a key named `order` its unit / text / contracts, under
    `desk_meta` its unit, and the laptop-only pool field at any depth."""
    return key == POOL_FIELD or key in UNIT_BEARING.get(parent, ())


# THE SHADOW-ARM KEYS (ARCHITECT 2026-11-01 12:05 ET, addendum 199 item 2; the module docstring quotes it): the
# pl-availability-v1 candidate's keys, written on the host only (#760), never compared or printed, counted.
SHADOW_EID = "pl-availability-v1"               # pl_availability.EID (this file ships alone: copied, not imported)
SHADOW_PREFIX = "candidate_"                    # pl_availability.ROW_KEYS, and any other candidate_* key, any depth
SHADOW_RESULT_KEY = "candidate"                 # pl_availability.RESULT_KEY: the results row's arm
SHADOW_LINE = "shadow-arm keys (host-only, pl-availability-v1)"     # the ruling's name, verbatim


def shadow_arm(key, *values) -> bool:
    """True for a shadow-arm key (addendum 199 item 2): a name starting with "candidate_" at any depth, or a key named
    exactly `candidate` whose value on either side is the arm (a dict whose `version` is pl-availability-v1). Another
    writer's `candidate` (a string or null) is compared as before."""
    k = str(key)
    return k.startswith(SHADOW_PREFIX) or (k == SHADOW_RESULT_KEY and any(
        isinstance(v, dict) and v.get("version") == SHADOW_EID for v in values))


# THE REHEARSAL-ARM KEYS (ARCHITECT 2026-11-04 09:55 ET, addendum 247 item 2(2); the module docstring quotes it):
# nfl-elo-v2's rehearsal arm, written on the host only, never compared or printed, counted on its own line.
REHEARSAL_EID = "nfl-elo-v2"                    # nfl_rehearsal.EID (this file ships alone: copied, not imported)
REHEARSAL_PREFIX = "rehearsal_"                 # nfl_rehearsal.PREFIX: ROW_KEYS, RESULT_KEY, RECORD_KEY, any depth
REHEARSAL_LINE = "rehearsal-arm keys (host-only, nfl-elo-v2)"      # the ruling's name, verbatim


def rehearsal_arm_key(key) -> bool:
    """True for a rehearsal-arm key (addendum 247 item 2(2)): a name starting with "rehearsal_", at any depth. The NFL
    file's top-level `rehearsal` and every `candidate_*` key (shadow_arm's) are not."""
    return str(key).startswith(REHEARSAL_PREFIX)


# THE GRADED-EXPORT KEYS (ARCHITECT 2026-11-01 15:45 ET, addendum 206 item 1; the module docstring quotes it): the
# export a results row stands behind (#768), named by each machine from its OWN closing file: machine-local, never
# compared or printed, counted.
GRADED_EXPORT_KEYS = ("graded_export",      # graded_export.KEY: a results row's {kind, file, run_id, exported_at}
                      "graded_exports")     # the results file's block: name_rows' counts (this file ships alone)
GRADED_LINE = "graded-export keys (machine-local)"                  # the ruling's name, verbatim


def graded_export_class(key) -> bool:
    """True for a graded-export parent (addendum 206 item 1): a key named exactly `graded_export` or `graded_exports`,
    at any depth (no other writer uses either name). Its whole object is masked; graded_export_x is compared."""
    return key in GRADED_EXPORT_KEYS


def graded_keys(x, y) -> int:
    """The keys one graded-export parent counts: every key of its object, a key on either side once; 1 when neither
    side's value is an object (the parent itself, so a masked key is never silent)."""
    if isinstance(x, dict) or isinstance(y, dict):
        return len(set(x if isinstance(x, dict) else ()) | set(y if isinstance(y, dict) else ()))
    return 1


def _masked_count(a, b, hit, parent=None, weight=None) -> int:
    """The fields `hit(parent, key, a_value, b_value)` masks in one file pair, a field on either side counted once: its
    own walk (Codex on #735), so the count reaches past the 40-line diff limit, into keys --ignore-keys prunes, into rows
    on one side only and across a dict-vs-other mismatch. Lists keep their parent key (as `diff` does); game rows pair
    by row key. A masked field is counted once (or `weight(a_value, b_value)`, the keys of its object, for the
    graded-export class) and not walked into."""
    if isinstance(a, dict) or isinstance(b, dict):
        da, db = (a if isinstance(a, dict) else {}), (b if isinstance(b, dict) else {})
        return sum((weight(da.get(k), db.get(k)) if weight else 1) if hit(parent, k, da.get(k), db.get(k))
                   else _masked_count(da.get(k), db.get(k), hit, k, weight) for k in set(da) | set(db))
    if isinstance(a, list) or isinstance(b, list):
        la, lb = (a if isinstance(a, list) else []), (b if isinstance(b, list) else [])
        if is_game_rows(la) and is_game_rows(lb):
            ka, kb = keyed(la), keyed(lb)
            return sum(_masked_count(ka.get(k), kb.get(k), hit, parent, weight) for k in set(ka) | set(kb))
        return sum(_masked_count(la[i] if i < len(la) else None, lb[i] if i < len(lb) else None, hit, parent, weight)
                   for i in range(max(len(la), len(lb))))
    return 0


def unit_count(a, b, parent=None) -> int:
    """The unit-bearing fields of one file pair (addendum 182 item 4), a field on either side counted once."""
    return _masked_count(a, b, lambda p, k, x, y: unit_bearing(p, k), parent)


def shadow_count(a, b, parent=None) -> int:
    """The shadow-arm keys of one file pair (addendum 199 item 2), a key on either side counted once, by the same walk
    as unit_count: 4 per PL row carrying the four candidate_* keys, 1 per results row carrying the arm."""
    return _masked_count(a, b, lambda p, k, x, y: shadow_arm(k, x, y), parent)


def rehearsal_count(a, b, parent=None) -> int:
    """The rehearsal-arm keys of one file pair (addendum 247 item 2(2)), a key on either side once, by the same walk:
    6 per NFL slate or closing row carrying the arm, 1 per results row carrying it, 1 for the record's block."""
    return _masked_count(a, b, lambda p, k, x, y: rehearsal_arm_key(k), parent)


def graded_count(a, b, parent=None) -> int:
    """The graded-export keys of one file pair (addendum 206 item 1), by the same walk: every key of each
    `graded_export` / `graded_exports` object, a key on either side once (4 per results row, 6 for the file's block)."""
    return _masked_count(a, b, lambda p, k, x, y: graded_export_class(k), parent, graded_keys)


def redacted(v, parent=None):
    """`v` with every unit-bearing field's value, every shadow-arm key's (addendum 199 item 2) and every graded-export
    object (addendum 206 item 1) replaced by "<masked>", for a structural mismatch printed whole (an `order` or
    `desk_meta` object against null; Codex on #735; a PL row against null; a results row against null): neither a
    dollar figure, a candidate figure nor a graded export's file or run id reaches the output."""
    if isinstance(v, dict):
        return {k: "<masked>" if (unit_bearing(parent, k) or shadow_arm(k, x) or rehearsal_arm_key(k)
                                  or graded_export_class(k))
                else redacted(x, k)
                for k, x in v.items()}
    if isinstance(v, list):
        return [redacted(x, parent) for x in v]
    return v


KICKOFF, HOME, AWAY = ("utc_date", "kickoff", "date"), ("home_team", "home"), ("away_team", "away")

# MACHINE STATE (ARCHITECT 2026-10-18, addendum 128 item 3; the module docstring quotes it): the kinds listed by
# presence, never compared. The kind rule is exports_mirror.kind_of's, copied because this file ships alone
# (tools/compare_exports.py has neither sp_common nor exports_mirror); tests/test_compare_exports_machine_state.py pins
# the copy to the mirror's.
MACHINE_STATE_KINDS = ("coverage",)
# THE HOST'S TALLY (addendum 289 item 3; the module docstring quotes it): machine state by the same rule, its own kind on
# its own line (tally_line), so the ruled machine-state line keeps its one kind
TALLY_KINDS = ("results_tally",)
_STAMP = re.compile(r"_?\d{4}-\d{2}-\d{2}(?:[T_]\d{2}:?\d{2}(?::?\d{2})?Z?)?")      # exports_mirror.STAMP


def kind_of(name: str) -> str:
    """exports_mirror.kind_of: the name with its date/time stamp removed (coverage_2026-10-19.json -> coverage,
    coverage.json -> coverage, fixtures_EFL_2026-10-01_to_2026-10-07.json -> fixtures_EFL)."""
    stem = name.rsplit(".", 1)[0]
    stem = _STAMP.sub("", stem).replace("_to", "")
    return re.sub(r"__+", "_", stem).strip("_") or stem


def machine_state_kind(name: str) -> str | None:
    """The file's kind when it is machine state (addendum 128 item 3; the host's tally, addendum 289 item 3), else
    None."""
    k = kind_of(name)
    return k if k in MACHINE_STATE_KINDS or k in TALLY_KINDS else None


def tally_line(laptop_names, host_names) -> str | None:
    """The host's tally by presence on each side, "the host's tally (machine state, never compared): results_tally
    laptop no / host yes"; None when neither side holds one (the line is not printed)."""
    def yn(names, kind):
        return "yes" if any(kind_of(n) == kind for n in names) else "no"
    if not any(kind_of(n) in TALLY_KINDS for n in [*laptop_names, *host_names]):
        return None
    return "the host's tally (machine state, never compared): " + " · ".join(
        f"{k} laptop {yn(laptop_names, k)} / host {yn(host_names, k)}" for k in TALLY_KINDS)


def machine_state_line(laptop_names, host_names) -> str:
    """The ruled line, by presence on each side: "machine-state files: coverage laptop yes / host no"."""
    def yn(names, kind):
        return "yes" if any(machine_state_kind(n) == kind for n in names) else "no"
    return "machine-state files: " + " · ".join(
        f"{k} laptop {yn(laptop_names, k)} / host {yn(host_names, k)}" for k in MACHINE_STATE_KINDS)


NAME_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def name_date(name: str) -> date | None:
    """The first valid YYYY-MM-DD in a file name, else None (undated)."""
    for m in NAME_DATE.finditer(name):
        try:
            return date.fromisoformat(m.group(1))
        except ValueError:
            continue
    return None


def in_window(name: str, since: int, today: date) -> bool:
    """True when the file is compared under --since: undated files always;
    dated files when today - date < since days; since <= 0 = everything."""
    d = name_date(name)
    return since <= 0 or d is None or (today - d) < timedelta(days=since)


def _first(d: dict, keys):
    for k in keys:
        if d.get(k) not in (None, ""):
            return d[k]
    return None


def is_game_rows(v) -> bool:
    return (isinstance(v, list) and v and all(isinstance(r, dict) for r in v)
            and all(_first(r, HOME) is not None and _first(r, AWAY) is not None for r in v))


def row_key(r: dict) -> str:
    ko = str(_first(r, KICKOFF) or "?")[:16]
    return f"{_first(r, AWAY)} @ {_first(r, HOME)} {ko}"


def keyed(rows: list) -> dict:
    out: dict = {}
    for r in rows:
        k = row_key(r)
        n = 2
        while k in out:                      # a true double-header keeps both rows
            k = f"{row_key(r)} #{n}"
            n += 1
        out[k] = r
    return out


def rows_of(doc) -> int | None:
    if isinstance(doc, list):
        return len(doc)
    if isinstance(doc, dict):
        lens = [len(v) for v in doc.values() if isinstance(v, list)]
        return max(lens) if lens else None
    return None


def diff(a, b, path="$", out=None, limit=40, unmatched=None, ignore=None, parent=None) -> list[str]:
    """`ignore`: None = the generic mask (TS_KEY + MASKED). A set (--ignore-keys; the cutover PL check only, #420)
    REPLACES that mask: only those keys and git_sha (code, never read from the database) are left out, so every
    database-read timestamp and match_id is compared (Codex on #439). In both modes the unit-bearing fields
    (addendum 182 item 4, unit_bearing), the shadow-arm keys (addendum 199 item 2, shadow_arm), the rehearsal-arm keys
    (addendum 247 item 2(2), rehearsal_arm_key) and the graded-export keys (addendum 206 item 1, graded_export_class)
    are left out and never printed: a mismatch printed whole is redacted first; unit_count, shadow_count,
    rehearsal_count and graded_count count them."""
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if (unit_bearing(parent, k) or shadow_arm(k, a.get(k), b.get(k)) or rehearsal_arm_key(k)
                    or graded_export_class(k)):
                continue
            if (ignore is None and (TS_KEY.search(str(k)) or k in MASKED)) or (
                    ignore is not None and (k in ignore or k == "git_sha")):
                continue
            if k not in a or k not in b:
                out.append(f"{path}.{k}: only in {'host' if k not in a else 'laptop'}")
            else:
                diff(a[k], b[k], f"{path}.{k}", out, limit, unmatched, ignore, k)
    elif is_game_rows(a) and is_game_rows(b):
        ka, kb = keyed(a), keyed(b)            # key FIRST, then compare pairs
        if unmatched is not None:
            unmatched.setdefault(path, {"laptop": [], "host": []})
            unmatched[path]["laptop"] += sorted(set(ka) - set(kb))
            unmatched[path]["host"] += sorted(set(kb) - set(ka))
        for k in sorted(set(ka) & set(kb)):
            diff(ka[k], kb[k], f"{path}[{k}]", out, limit, unmatched, ignore, parent)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: length {len(a)} vs {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            diff(x, y, f"{path}[{i}]", out, limit, unmatched, ignore, parent)
    elif a != b:
        out.append(f"{path}: {str(redacted(a, parent))[:60]!r} vs {str(redacted(b, parent))[:60]!r}")
    return out


def main(argv=None) -> int:
    """CLEAN 0 / DIVERGENT 1 / ERROR 2; the last line printed names the verdict."""
    try:
        return _main(argv)
    except SystemExit as e:                   # argparse: --help is 0, a usage error is 2
        if e.code in (0, None):
            raise
        print(f"VERDICT: ERROR (usage, exit {e.code}) — not a data verdict")
        return EXIT_ERROR
    except Exception as e:                    # noqa: BLE001 — a crash is an ERROR, never DIVERGENT
        print(f"VERDICT: ERROR ({type(e).__name__}: {e}) — the comparison did not run; not a data verdict")
        return EXIT_ERROR


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(epilog=(
        "Never compared or printed, in either mode, and counted on their own lines: the unit-bearing fields "
        "(addendum 182 item 4), the shadow-arm keys (ARCHITECT 2026-11-01, addendum 199 item 2: \"compare_exports "
        "treats every `candidate_*` key as \"shadow-arm keys (host-only, pl-availability-v1)\": never compared, never "
        "printed, counted on its own line beside the unit-bearing count\"; also a results row's `candidate` arm), the "
        "rehearsal-arm keys (ARCHITECT 2026-11-04, addendum 247 item 2(2): every `rehearsal_*` key, \"masked by "
        "compare_exports.py under its own line \"rehearsal-arm keys (host-only, nfl-elo-v2)\" beside the "
        "pl-availability line\"), and "
        "the graded-export keys (ARCHITECT 2026-11-01, addendum 206 item 1: \"graded-export keys (machine-local)\": "
        "every key of a results row's graded_export object and of the file-level graded_exports block, never "
        "compared, never printed as a diff, counted once per file on its own line)."))
    ap.add_argument("laptop", type=Path)
    ap.add_argument("host", type=Path)
    ap.add_argument("--glob", default="*.json")
    ap.add_argument("--since", type=int, default=3,
                    help="Compare only files dated (YYYY-MM-DD in the name) within the last N UTC days; "
                         "undated files always compared; 0 = everything. Default 3.")
    ap.add_argument("--today", default=None, help=argparse.SUPPRESS)   # tests pin the clock
    # THE CUTOVER PL CHECK ONLY (#420 RULED, ARCHITECT 2026-10-11, addendum 38): "every field that is read from the
    # database is compared, number for number. A field that is read off the clock is not compared: the Desk block,
    # desk_meta, line_move and late_news_flag. The check prints the keys it left out, and a file with no predictions
    # is still no coverage." Both flags are off by default; every other comparison is unchanged.
    ap.add_argument("--ignore-keys", default="",
                    help="Comma-separated keys left out of the comparison at any depth (printed). The cutover PL "
                         "check only (h2-cutover-runbook.md section 1 step 4).")
    ap.add_argument("--require-predictions", action="store_true",
                    help="Count, per side, the rows with a prediction and its probabilities; a compared file with "
                         "none on either side is NO-COVERAGE (#422 item 4). The cutover PL check only.")
    a = ap.parse_args(argv)
    ignore = frozenset(k.strip() for k in a.ignore_keys.split(",") if k.strip()) or None
    today = date.fromisoformat(a.today) if a.today else datetime.now(timezone.utc).date()
    missing = [f"{side}={d}" for side, d in (("laptop", a.laptop), ("host", a.host)) if not d.is_dir()]
    if missing:                               # an absent side must never read as "0 compared, CLEAN"
        print(f"VERDICT: ERROR (side directory missing: {', '.join(missing)}) — not a data verdict")
        return EXIT_ERROR
    la_all = {p.name: p for p in a.laptop.glob(a.glob)}
    ho_all = {p.name: p for p in a.host.glob(a.glob)}
    la = {n: p for n, p in la_all.items() if in_window(n, a.since, today)}
    ho = {n: p for n, p in ho_all.items() if in_window(n, a.since, today)}
    settled = len(set(la_all) | set(ho_all)) - len(set(la) | set(ho))
    # addendum 128 item 3: a machine-state file leaves the comparison here, listed by presence and never opened
    ms_line = machine_state_line(la, ho)
    t_line = tally_line(la, ho)                   # addendum 289 item 3: printed only when a tally file is there
    la = {n: p for n, p in la.items() if not machine_state_kind(n)}
    ho = {n: p for n, p in ho.items() if not machine_state_kind(n)}
    wor = writer_of_record()
    print(f"writer of record: {wor or 'UNKNOWN (SP_WRITER_OF_RECORD unset/invalid)'} — canonical side: "
          f"{wor or '?'}" + (f"; divergences are read as the {'host' if wor == 'laptop' else 'laptop'} "
                              f"side departing from it" if wor else ""))
    if a.since > 0:
        print(f"window: --since {a.since} → files dated {today - timedelta(days=a.since - 1)} .. {today} "
              f"(UTC) + undated; {settled} settled file(s) earlier not re-printed")
    if ignore:
        print(f"left out of the comparison (--ignore-keys, read off the clock): {', '.join(sorted(ignore))}")
        print("the timestamp mask is off: every other key is compared (git_sha is reported on its own line)")
    clean, skew_names, compared = True, set(), 0
    # #680: what made a run DIVERGENT, each file named on the summary line (Codex on #683: field diffs and rows on one
    # side within a file are separate causes; a file's own line prints diffs=0 when only its rows differ)
    field_diffs, row_diffs, unparseable, one_sided = [], [], [], []
    unit_masked = 0                               # addendum 182 item 4: the unit-bearing fields left out, counted
    shadow_masked = 0                             # addendum 199 item 2: the shadow-arm keys left out, counted
    rehearsal_masked = 0                          # addendum 247 item 2(2): the rehearsal-arm keys left out, counted
    graded_masked = 0                             # addendum 206 item 1: the graded-export keys left out, counted
    pred_rows = {"laptop": 0, "host": 0}
    for name in sorted(set(la) | set(ho)):
        if name not in la or name not in ho:
            print(f"· {name}: only on {'host' if name not in la else 'laptop'}")
            clean = False
            one_sided.append(name)
            continue
        try:
            x, y = json.loads(la[name].read_text()), json.loads(ho[name].read_text())
        except json.JSONDecodeError as e:
            print(f"✗ {name}: unparseable ({e})")
            clean = False
            unparseable.append(name)
            continue
        compared += 1
        if a.require_predictions:
            for side, doc in (("laptop", x), ("host", y)):
                pred_rows[side] += predicted_rows(doc)
        um: dict = {}
        d = diff(x, y, unmatched=um, ignore=ignore)
        unit_masked += unit_count(x, y)
        shadow_masked += shadow_count(x, y)
        rehearsal_masked += rehearsal_count(x, y)
        graded_masked += graded_count(x, y)
        only = {s: [k for v in um.values() for k in v[s]] for s in ("laptop", "host")}
        ok = not d and not only["laptop"] and not only["host"]
        clean &= ok
        if d:
            field_diffs.append(name)
        if only["laptop"] or only["host"]:
            row_diffs.append(name)
        sha = sha_line(x, y)
        skew_names.update([name] if sha.startswith("code-version skew") else [])
        print(f"{'✓' if ok else '✗'} {name}: rows laptop={rows_of(x)} host={rows_of(y)} "
              f"diffs={len(d)} · {sha}")
        for side in ("laptop", "host"):
            if only[side]:
                print(f"    only on {side} ({len(only[side])}): " + "; ".join(only[side][:12])
                      + (" …" if len(only[side]) > 12 else ""))
        for line in d[:15]:
            print(f"    {line}")
    other = {side: sorted(f.name for f in d.iterdir() if f.is_file() and f.name not in names)
             for side, d, names in (("laptop", a.laptop, la_all), ("host", a.host, ho_all))}
    one_side = len(set(la) ^ set(ho))
    print(ms_line)
    if t_line:
        print(t_line)
    print(f"\ncoverage: {compared} JSON file(s) compared ({a.glob}) · {one_side} on one side only · "
          f"{settled} outside the window · not matched by {a.glob}: laptop {len(other['laptop'])}, "
          f"host {len(other['host'])}" + (f" (e.g. {', '.join((other['laptop'] + other['host'])[:3])})"
                                          if other['laptop'] or other['host'] else ""))
    print(f"unit-bearing fields masked (policy v1.2): {unit_masked}")   # addendum 182 item 4
    print(f"{SHADOW_LINE}: {shadow_masked}")                            # addendum 199 item 2
    print(f"{REHEARSAL_LINE}: {rehearsal_masked}")                      # addendum 247 item 2(2)
    print(f"{GRADED_LINE}: {graded_masked}")                            # addendum 206 item 1
    if a.require_predictions:
        print(f"predictions compared (rows with a prediction and its probabilities): laptop {pred_rows['laptop']} "
              f"· host {pred_rows['host']}")
        # Codex on #439: a missing host file (nothing compared) is NO-COVERAGE too, never DIVERGENT
        if compared == 0 or pred_rows["laptop"] == 0 or pred_rows["host"] == 0:
            print("NO COVERAGE — a side carries no row with a prediction and its probabilities; nothing is "
                  "verified (#422 item 4), so this is not a clean verdict.")
            print(f"VERDICT: NO-COVERAGE ({'0 compared' if not compared else 'no predictions compared'}) — "
                  "not a data verdict")
            return EXIT_NO_COVERAGE
    if clean and compared == 0:
        print(f"NO COVERAGE — no {a.glob} file was compared on both sides; nothing is verified, so this is "
              f"not a clean verdict.")
        print("VERDICT: NO-COVERAGE (0 compared) — not a data verdict")
        return EXIT_NO_COVERAGE
    classes = "capture timing | provider pagination | code-version skew (only where named above)"
    # #680 (ARCHITECT 2026-10-26, a verdict-line nit): a DIVERGENT run names each cause on this line, with its files:
    # field diffs, rows on one side within a file, unparseable, on one side only. The VERDICT line and the exit code are
    # unchanged; a CLEAN run's line reads as before.
    causes = (("with field diffs", field_diffs), ("with rows on one side", row_diffs), ("unparseable", unparseable),
              ("on one side only", one_sided))
    why = "".join(f"; {len(names)} {label}: {', '.join(names)}" for label, names in causes if names)
    print(f"{'CLEAN' if clean else 'DIVERGENT'} ({compared} compared{why}) — "
          f"each divergence needs an explanation ({classes}) or a BACKLOG entry."
          + (f" Code-version skew named for: {', '.join(sorted(skew_names))}." if skew_names else ""))
    print(f"VERDICT: {'CLEAN' if clean else 'DIVERGENT'}")
    return EXIT_CLEAN if clean else EXIT_DIVERGENT


def predicted_rows(doc) -> int:
    """Rows of a predictions export carrying a prediction with probabilities (#422 item 4)."""
    rows = doc.get("predictions") if isinstance(doc, dict) else None
    return sum(1 for r in rows or [] if isinstance(r, dict) and isinstance(r.get("prediction"), dict)
               and r["prediction"].get("probabilities"))


def sha_line(x, y) -> str:
    """The code-version-skew guard: the class is claimable ONLY when both files
    carry their producing git_sha and they differ; a missing SHA is named."""
    sa = x.get("git_sha") if isinstance(x, dict) else None
    sb = y.get("git_sha") if isinstance(y, dict) else None
    if sa and sb:
        return (f"code-version skew: laptop {sa} ≠ host {sb}" if sa != sb
                else f"same code {sa}")
    missing = [s for s, v in (("laptop", sa), ("host", sb)) if not v]
    return f"git_sha missing on {' + '.join(missing)} — code-version skew NOT claimable"


if __name__ == "__main__":
    sys.exit(main())
