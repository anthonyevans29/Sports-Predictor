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
present on one side only are listed. Output is paste-ready. The verdict is THE
PAIRED KINDS' rule (addendum 335 item 4(c), below); the exit codes and their
pre-335 meanings that follow hold as written under --paired-kinds '*'. Exit 0 =
CLEAN (every compared file identical after the timestamp mask), 1 = DIVERGENT,
2 = ERROR (the comparison could not run: bad arguments, a side directory
missing, a crash), 3 = NOTHING-TO-COMPARE (no file was compared: no JSON on
both sides in the window — an empty folder, Markdown-only dated folders, or
files each on one side only; the --require-predictions check's own reading of
this exit is NO-COVERAGE). 2 and 3 are never data verdicts; CLEAN needs at
least one compared file. A "coverage:" line always counts the JSON compared
and the files the glob left out. The last line always reads
"VERDICT: CLEAN|DIVERGENT|ERROR|NOTHING-TO-COMPARE|NO-COVERAGE". Read-only.

NOTHING-TO-COMPARE (ARCHITECT 2026-11-11, addendum 334 item 3(a), verbatim):
"a red status that means "nothing to compare" is a false alarm — the verdict
for zero compared files becomes NOTHING-TO-COMPARE (neutral, not failure),
DIVERGENT reserved for files that were compared and differ". Files on one side
only still print their `·` lines and are counted on the tally, and the verdict
line names them; they no longer make a zero-compared run DIVERGENT. A file on
both sides that does not parse is not "nothing to compare": it stays
DIVERGENT. A run that compared at least one file reads as before (a file on
one side only beside it is still DIVERGENT, even when every compared file is
identical). So exit 1 means: a compared file differs, a pair does not parse,
or a file sits on one side only beside at least one compared file. Those last
two readings were #922's, RULED by addendum 335 item 2: the unparseable pair
stays DIVERGENT (confirmed, law 4); a one-sided file beside a clean pair is
replaced by THE PAIRED KINDS' rule (below), and stands only under
--paired-kinds '*'.

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
NOTHING-TO-COMPARE; NO-COVERAGE under --require-predictions and in cutover_readiness). One line, always printed, names its presence per side among
the files --glob and the window select (one they leave out reads no there and
is counted as not matched or settled; the Action's *.json and --since 0
select the whole folder). The --since window and the header's settled count
treat it like any dated file.
cutover_readiness.compare_day (criterion (a)) applies the same rule.

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

THE PAIRED KINDS (ARCHITECT 2026-11-11 08:45 ET, addendum 335 item 4, #924), verbatim (c): "the comparator carries a
declared list of PAIRED KINDS — kinds both machines are ruled to produce every day (today: fixtures_NHL alone) — and a
kind not on it is EXPECTED ONE-SIDED (coverage, the window card, the UNL and league shadows, closings, slates, the MLB
results file), printed and counted, never a cause of DIVERGENT. CLEAN = at least one paired file compared with rows
in the window, every compared file identical, no paired kind missing on a side. DIVERGENT = a compared file differs,
OR a paired kind is present on one side and missing on the other for a date both machines pushed (a missing file is a
finding), OR a pair does not parse. NOTHING-TO-COMPARE = everything else, including a pair whose in-window rows are
empty on both sides (218 item 1: an empty window is reported, never a pass) — so the 12-24 gap reads neutral." And
(b): "only rows whose utc_date falls on the file's yesterday, today or tomorrow — the days BOTH machines synced that
day; rows outside are counted "outside the window", never compared (the laptop has no weekly full-season sync, so
later kickoffs can legitimately differ). The host-only columns (market, kalshi*,
exec_cost*, fee*, k_track, kalshi_legs, input_quality, desk, desk_meta) are masked AND COUNTED in #735's pattern, a
new key in `_fixture_row` staying visible."
As built: PAIRED_KINDS declares each paired kind with its rows key and its day window; a paired file's rows outside
the window (its name's date -1, 0, +1, by utc_date's UTC day) are counted per side and never compared, and its
`count` (all rows, the window's outside included) is left out for the in-window counts printed instead. The
host-only columns (HOST_ONLY_KEYS / HOST_ONLY_PREFIXES; `away_bid` and `away_ask`, the Kalshi away leg, are the same
class) are left out of a paired file at any depth and counted on their own line. A file of a kind not on the list is
still compared when both sides carry it (a difference is DIVERGENT; an identical pair never makes CLEAN). The flag
`--paired-kinds` names the list (default: the declared one); `--paired-kinds '*'` is the pre-335 rule (every kind
paired, no window, no host-only mask), which the --require-predictions check (the cutover PL check) always uses.
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
#   3 NOTHING-TO-COMPARE (zero files compared: never a clean verdict, PR #261 review; neutral, never DIVERGENT,
#     addendum 334 item 3(a)). The --require-predictions check reads the same exit as NO-COVERAGE (#422 item 4).
EXIT_CLEAN, EXIT_DIVERGENT, EXIT_ERROR, EXIT_NO_COVERAGE = 0, 1, 2, 3
EXIT_NOTHING_TO_COMPARE = EXIT_NO_COVERAGE

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


def host_only_count(a, b, parent=None) -> int:
    """The host-only columns of one paired file pair (addendum 335 item 4(b)), a column on either side counted once."""
    return _masked_count(a, b, lambda p, k, x, y: host_only_key(k), parent)


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

# THE PAIRED KINDS (ARCHITECT 2026-11-11, addendum 335 item 4(b)-(c); see the module docstring): kind -> its rows key
# and its day window around the date in the file's name. Today fixtures_NHL alone: the laptop's morning block runs
# nhl-daily's own steps (sync-matches NHL yesterday, today, tomorrow; export-fixtures --competition NHL).
PAIRED_KINDS = {"fixtures_NHL": {"rows": "fixtures", "days": (-1, 0, 1)}}
# The host-only columns of a paired file (335 item 4(b)), left out at any depth and counted: the market machine's
# books, Kalshi, exec costs, fees and Desk. away_bid / away_ask (the Kalshi away leg, venue.KALSHI_EXEC_NULL) are the
# same class, and so is `close_unpriced` (the book close's unpriced-books note, _fixture_row; the laptop syncs no
# books). Both additions are put to the architect on the PR. A unit-bearing field inside a host-only container
# (desk_meta.unit, desk.order.*) is counted on the unit-bearing line too: each line counts its own class.
HOST_ONLY_KEYS = frozenset({"market", "kalshi", "k_track", "kalshi_legs", "input_quality", "desk", "desk_meta",
                            "away_bid", "away_ask", "close_unpriced"})
# the ruling's kalshi*, exec_cost*, fee* families, matched with their underscore so an unrelated new key (`feed_*`,
# `feedback`) stays visible (Code's review); `kalshi` itself is in HOST_ONLY_KEYS
HOST_ONLY_PREFIXES = ("kalshi_", "exec_cost_", "fee_")
HOST_ONLY_LINE = ("host-only columns (market, kalshi*, exec_cost*, fee*, k_track, kalshi_legs, input_quality, desk, "
                  "desk_meta, away_bid, away_ask, close_unpriced)")


def host_only_key(key) -> bool:
    k = str(key)
    return k in HOST_ONLY_KEYS or k.startswith(HOST_ONLY_PREFIXES)


def window_pair(x, y, spec: dict, day: date | None):
    """Both sides of a paired file cut to the window together (Code's review: one side's missing rows list must not
    crash or cut one side only). Returns (x, y, (nx, ny, ox, oy)) when BOTH carry a rows list and the name has a date;
    else (x, y, None), uncut, so a structural difference prints as a diff."""
    def has_rows(d):
        return isinstance(d, dict) and isinstance(d.get(spec["rows"]), list)
    if day is None or not (has_rows(x) and has_rows(y)):
        return x, y, None
    x2, nx, ox = window_rows(x, spec, day)
    y2, ny, oy = window_rows(y, spec, day)
    return x2, y2, (nx, ny, ox, oy)


def window_rows(doc, spec: dict, day: date | None):
    """(doc with its rows cut to the window and `count` left out, in-window rows, rows outside) for a paired file;
    (doc, None, 0) when the file carries no rows list or its name has no date (nothing is cut, law 4)."""
    rows = doc.get(spec["rows"]) if isinstance(doc, dict) else None
    if day is None or not isinstance(rows, list):
        return doc, None, 0
    days = {(day + timedelta(days=n)).isoformat() for n in spec["days"]}
    inside = [r for r in rows if isinstance(r, dict) and str(r.get("utc_date") or "")[:10] in days]
    out = {k: v for k, v in doc.items() if k != "count"}
    out[spec["rows"]] = inside
    return out, len(inside), len(rows) - len(inside)
_STAMP = re.compile(r"_?\d{4}-\d{2}-\d{2}(?:[T_]\d{2}:?\d{2}(?::?\d{2})?Z?)?")      # exports_mirror.STAMP


def kind_of(name: str) -> str:
    """exports_mirror.kind_of: the name with its date/time stamp removed (coverage_2026-10-19.json -> coverage,
    coverage.json -> coverage, fixtures_EFL_2026-10-01_to_2026-10-07.json -> fixtures_EFL)."""
    stem = name.rsplit(".", 1)[0]
    stem = _STAMP.sub("", stem).replace("_to", "")
    return re.sub(r"__+", "_", stem).strip("_") or stem


def machine_state_kind(name: str) -> str | None:
    """The file's kind when it is machine state (addendum 128 item 3), else None."""
    k = kind_of(name)
    return k if k in MACHINE_STATE_KINDS else None


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


def diff(a, b, path="$", out=None, limit=40, unmatched=None, ignore=None, parent=None, host_only=False) -> list[str]:
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
                    or graded_export_class(k) or (host_only and host_only_key(k))):
                continue
            if (ignore is None and (TS_KEY.search(str(k)) or k in MASKED)) or (
                    ignore is not None and (k in ignore or k == "git_sha")):
                continue
            if k not in a or k not in b:
                out.append(f"{path}.{k}: only in {'host' if k not in a else 'laptop'}")
            else:
                diff(a[k], b[k], f"{path}.{k}", out, limit, unmatched, ignore, k, host_only)
    elif is_game_rows(a) and is_game_rows(b):
        ka, kb = keyed(a), keyed(b)            # key FIRST, then compare pairs
        if unmatched is not None:
            unmatched.setdefault(path, {"laptop": [], "host": []})
            unmatched[path]["laptop"] += sorted(set(ka) - set(kb))
            unmatched[path]["host"] += sorted(set(kb) - set(ka))
        for k in sorted(set(ka) & set(kb)):
            diff(ka[k], kb[k], f"{path}[{k}]", out, limit, unmatched, ignore, parent, host_only)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: length {len(a)} vs {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            diff(x, y, f"{path}[{i}]", out, limit, unmatched, ignore, parent, host_only)
    elif a != b:
        out.append(f"{path}: {str(redacted(a, parent))[:60]!r} vs {str(redacted(b, parent))[:60]!r}")
    return out


def main(argv=None) -> int:
    """CLEAN 0 / DIVERGENT 1 / ERROR 2 / NOTHING-TO-COMPARE 3; the last line printed names the verdict."""
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
    ap.add_argument("--paired-kinds", default=",".join(PAIRED_KINDS),
                    help="The PAIRED KINDS (addendum 335 item 4(c)), comma-separated; default the declared list "
                         f"({', '.join(PAIRED_KINDS)}). '*' = the pre-335 rule: every kind paired, no window, no "
                         "host-only mask (the --require-predictions check always uses it).")
    a = ap.parse_args(argv)
    legacy = a.paired_kinds.strip() == "*" or a.require_predictions
    paired = frozenset() if legacy else frozenset(k.strip() for k in a.paired_kinds.split(",") if k.strip())
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
    # addendum 335 item 4(c): the paired kinds' own counts (unused under the pre-335 rule, `legacy`)
    paired_missing, expected_one_sided, paired_with_rows, paired_empty = [], [], [], []
    paired_unnamed = []          # a paired kind on both sides under different names: present, but nothing compared
    kinds = {"laptop": {kind_of(n) for n in la}, "host": {kind_of(n) for n in ho}}
    host_only_masked = 0
    outside = {"laptop": 0, "host": 0}
    for name in sorted(set(la) | set(ho)):
        kind = kind_of(name)
        if name not in la or name not in ho:
            side = "host" if name not in la else "laptop"
            other = "laptop" if side == "host" else "host"
            if legacy:
                print(f"· {name}: only on {side}")
                clean = False
                one_sided.append(name)
            elif kind in paired and kind in kinds[other]:
                print(f"· {name}: only on {side} — PAIRED KIND {kind} is on both sides under different names, so "
                      f"nothing of it was compared")
                paired_unnamed.append(name)
            elif kind in paired:
                print(f"· {name}: only on {side} — PAIRED KIND {kind} missing on {other}")
                paired_missing.append(name)
            else:
                print(f"· {name}: only on {side} (expected one-sided: {kind} is not a paired kind)")
                expected_one_sided.append(name)
            continue
        try:
            x, y = json.loads(la[name].read_text()), json.loads(ho[name].read_text())
        except json.JSONDecodeError as e:
            print(f"✗ {name}: unparseable ({e})")
            clean = False
            unparseable.append(name)
            continue
        compared += 1
        spec = None if legacy else PAIRED_KINDS.get(kind) if kind in paired else None
        win = None
        if kind in paired:
            if spec is not None:
                x, y, win = window_pair(x, y, spec, name_date(name))
                if win:
                    outside["laptop"] += win[2]
                    outside["host"] += win[3]
                host_only_masked += host_only_count(x, y)
            rows_in = (win[0] + win[1]) if win else ((rows_of(x) or 0) + (rows_of(y) or 0))
            (paired_with_rows if rows_in else paired_empty).append(name)
        if a.require_predictions:
            for side, doc in (("laptop", x), ("host", y)):
                pred_rows[side] += predicted_rows(doc)
        um: dict = {}
        d = diff(x, y, unmatched=um, ignore=ignore, host_only=spec is not None)
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
              f"diffs={len(d)} · {sha}"
              + (f" · in the window (yesterday, today, tomorrow) laptop={win[0]} host={win[1]}; outside the window, "
                 f"never compared: laptop {win[2]} · host {win[3]}" if win else "")
              + ("" if legacy or kind in paired else f" · {kind} is not a paired kind"))
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
    print(f"\ncoverage: {compared} JSON file(s) compared ({a.glob}) · {one_side} on one side only · "
          f"{settled} outside the window · not matched by {a.glob}: laptop {len(other['laptop'])}, "
          f"host {len(other['host'])}" + (f" (e.g. {', '.join((other['laptop'] + other['host'])[:3])})"
                                          if other['laptop'] or other['host'] else ""))
    print(f"unit-bearing fields masked (policy v1.2): {unit_masked}")   # addendum 182 item 4
    print(f"{SHADOW_LINE}: {shadow_masked}")                            # addendum 199 item 2
    print(f"{REHEARSAL_LINE}: {rehearsal_masked}")                      # addendum 247 item 2(2)
    print(f"{GRADED_LINE}: {graded_masked}")                            # addendum 206 item 1
    if not legacy:                                                      # addendum 335 item 4(b)-(c)
        print(f"{HOST_ONLY_LINE}: {host_only_masked}")
        print(f"paired kinds ({', '.join(sorted(paired)) or 'none'}): {len(paired_with_rows)} compared with rows in "
              f"the window · {len(paired_empty)} empty in the window · {len(paired_missing)} missing on a side · "
              + (f"{len(paired_unnamed)} under different names · " if paired_unnamed else "")
              + f"rows outside the window laptop {outside['laptop']} · host {outside['host']} · expected one-sided "
              f"(not a paired kind): {len(expected_one_sided)}")
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
    if not legacy:
        return paired_verdict(compared, field_diffs, row_diffs, unparseable, paired_missing, paired_with_rows,
                              paired_empty, expected_one_sided, skew_names, paired_unnamed)
    if compared == 0 and not unparseable:
        # addendum 334 item 3(a): zero compared is NOTHING-TO-COMPARE (neutral), whatever sits on one side only
        print(f"NOTHING TO COMPARE — no {a.glob} file was compared on both sides; nothing is verified, so this is "
              f"not a clean verdict, and nothing differed, so it is not DIVERGENT.")
        print("VERDICT: NOTHING-TO-COMPARE (0 compared"
              + (f"; {len(one_sided)} on one side only: {', '.join(one_sided)}" if one_sided else "")
              + ") — not a data verdict")
        return EXIT_NOTHING_TO_COMPARE
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


def paired_verdict(compared, field_diffs, row_diffs, unparseable, paired_missing, paired_with_rows, paired_empty,
                   expected_one_sided, skew_names, paired_unnamed=()) -> int:
    """Addendum 335 item 4(c), the verdict rule: DIVERGENT = a compared file differs, a pair does not parse, or a
    paired kind is missing on a side; else CLEAN = at least one paired file compared with rows in the window; else
    NOTHING-TO-COMPARE (an empty window, no paired kind, files of other kinds on one side only)."""
    classes = "capture timing | provider pagination | code-version skew (only where named above)"
    causes = (("with field diffs", field_diffs), ("with rows on one side", row_diffs), ("unparseable", unparseable),
              ("paired kind missing on a side", paired_missing),
              ("paired kind under different names", list(paired_unnamed)))
    if any(names for _l, names in causes):
        why = "".join(f"; {len(names)} {label}: {', '.join(names)}" for label, names in causes if names)
        print(f"DIVERGENT ({compared} compared{why}) — each divergence needs an explanation ({classes}) or a "
              f"BACKLOG entry." + (f" Code-version skew named for: {', '.join(sorted(skew_names))}."
                                   if skew_names else ""))
        print("VERDICT: DIVERGENT")
        return EXIT_DIVERGENT
    if paired_with_rows:
        print(f"CLEAN ({compared} compared; {len(paired_with_rows)} paired with rows in the window: "
              f"{', '.join(paired_with_rows)}) — every compared file identical, no paired kind missing."
              + (f" Code-version skew named for: {', '.join(sorted(skew_names))}." if skew_names else ""))
        print("VERDICT: CLEAN")
        return EXIT_CLEAN
    print("NOTHING TO COMPARE — no paired file was compared with rows in the window; nothing is verified, so this is "
          "not a clean verdict, and nothing differed, so it is not DIVERGENT.")
    parts = [f"{compared} compared", f"0 paired with rows in the window"]
    if paired_empty:
        parts.append(f"{len(paired_empty)} paired empty in the window: {', '.join(paired_empty)}")
    if expected_one_sided:
        parts.append(f"{len(expected_one_sided)} expected one-sided: {', '.join(expected_one_sided)}")
    print(f"VERDICT: NOTHING-TO-COMPARE ({'; '.join(parts)}) — not a data verdict")
    return EXIT_NOTHING_TO_COMPARE


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
