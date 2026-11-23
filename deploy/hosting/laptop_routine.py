#!/usr/bin/env python3
"""THE LAPTOP'S MORNING ROUTINE: the step list, committed and checked, and one command that runs it.

    python deploy/hosting/laptop_routine.py [--weekly] [--dry-run]

ARCHITECT 2026-11-23 08:17 ET, addendum 451 item 3 (#1067). Item 2(a), verbatim: "The fault to mend is small: my
hand-written block dropped steps. What mends it is the step list committed and checked, and one command that runs it.
Nothing more." Item 2(b): sp_run.py, sp_backup.py and chains.py are the host's runner and its commands; NONE OF THE
THREE FILES IS EDITED, no ruled pin is widened and no backup kind is added. This module imports date_vars and the sync
count lines from sp_run, and append_receipt (with redact and git_sha) from sp_common, and changes neither. The list
lives here, outside chains.CHAINS (item 3(f) 17).

WHAT IT DOES (item 3(b)):
- Refuses, exit 2, nothing run, unless src.walters.desk_policy.machine_role() reads "laptop". The refusal comes before
  anything else: no date is resolved, no database is read, no step runs. A role read that raises is an unknown role,
  refused the same way (its error printed and receipted). A real run's refusal writes one receipt (refused:
  machine_role); a --dry-run's writes none, as sp_run's dry runs write none.
- Runs each step as the checkout's own python (sys.executable) on the checkout's cli.py (cwd the checkout), in
  order. A FAILING STEP NEVER STOPS THE NEXT: every exit is printed. No step is retried (item 3 asks for none).
- First line: the UTC dates it resolved. The step's own output streams indented ("  | "), then ONE line per step:
  its number, the command, its exit, its seconds; for a sync step (a command starting "sync-", and nhl-goalie-sync,
  step 14), its own lines of counts and any orientation, refusal, collision, skipped-listing or held line follow it,
  each "    > ". Last line: steps run, and non-zero exits (routine exits counted apart; receipts not written, when
  any).
- A step whose non-zero exit is routine carries those exits in the list (Step.routine) and is counted apart. READ FROM
  cli.py (law 1): `improve --sport mlb --hold-on-pass` gives a rejection NO non-zero exit. improve_cmd prints
  "✓ Candidate <v>: REJECTED" (or HELD, or PROMOTED) and returns, exit 0; its one SystemExit is 2 for
  LegacySoccerImproveRefused (cli.py improve_cmd), which src/walters/training.py improve() raises for soccer only. So
  no step of the list has a routine non-zero exit today, and every non-zero exit counts as one.
- One receipt line per step (kind "step", unit "laptop-routine", as bootstrap.py writes its own steps) and one for the
  run (kind "laptop_routine", never "chain", so no reader of the host's chain receipts counts it), by
  sp_common.append_receipt as it is (SP_RECEIPTS, else the checkout's logs/receipts.jsonl). A step that could not
  start is receipted with exit null (law 4: no exit is invented) and `not_started` naming why. A receipt that cannot
  be written (append_receipt raised) is printed ("receipt NOT written: ...") and the run goes on; the run receipt
  lists those steps and the last line counts them.
- --dry-run prints the resolved steps and runs nothing (no step, no receipt), as sp_run's --dry-run does. With
  --weekly it reads the weekly list (read-only) to print it.
- Exit: 0 when no step exited non-zero outside its routine exits and every receipt was written; 1 when a step did,
  or a receipt was not written; 2 for a refusal.

THE DAILY LIST (item 3(d)), the architect's block of 2026-11-23 in its order. Placeholders are UTC, from sp_run's
date_vars ({today}, {yesterday}, {tomorrow}); date_vars has no today-2 or today-8, so {today_minus2} and
{today_minus8} are derived here the same way (today - timedelta(days=n), isoformat). Item 1's 2026-10-15 is literal.
Items 7 and 8 run one day at a time (today-2, yesterday, today, tomorrow) with a wait of 6 seconds after each day;
item 12 one day at a time (yesterday, today, tomorrow); items 15 and 16 are two steps each (ATP, then WTA).

--weekly (item 3(e)): BEFORE item 9, the whole-season pass. The list is read from the laptop's database read-only
(src.db.database.readonly_scope: the configured live file, mode=ro, never created): every distinct (competition code,
season) holding a match whose utc_date (naive UTC) is on or after 2026-07-01, except MLB, ATP, WTA, WC and NCAA,
sorted by code then season, printed. Per line: sync-teams --competition C --season S, then sync-matches --competition
C --season S, a wait of 6 seconds after each. A list that cannot be read refuses the run (exit 2, nothing run).
The list holds only what the laptop stores: a competition-season with no row on the laptop is never listed (ARCHITECT
2026-11-16, addendum 406 item 3(c): "FAC IS NOT ON THE LAPTOP AT ALL for 2026/27: the pass lists what the laptop
holds, and it holds no FAC row of this season, so it could not list it ... I add FAC to my block by name."). No
competition is added here by name: item 3(d) and (e) name none.

WHAT IT DOES NOT DO (item 3(c)), each staying in the architect's block: the backup (first, under a free name; the
block does not call this command if the backup failed); coverage (after the backup, before this command); the roadmap
read; the mirror push; the stale count; the read of the four guarded college rows. It sends no page (a step's
"SP-PAGE:" line is printed and receipted, never delivered). No timer and no launchd job. It takes no DB lock of its
own (the syncs take theirs, cli.py _sync_lock, as when the block typed them). NO soccer-refresh, EVER: no list here
holds it (tests/test_laptop_routine.py).
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))            # src.walters.desk_policy and, for --weekly, src.db (after the hosting pack)

import sp_common as c  # noqa: E402
from sp_run import (FALLBACK_TEAMS_LINE, HELD_LINE, MATCHES_LINE, SCORES_BY_TEAM_LINE,  # noqa: E402
                    SKIPPED_LISTINGS_LINE, TEAMS_LINE, date_vars, sync_counts)

UNIT = "laptop-routine"                   # the receipts' unit: never a host chain's name (chains.CHAINS has no such key)
RUN_KIND = "laptop_routine"               # the run's receipt kind: never "chain"
TAIL = 5
SEASON = "2026"
BASKETBALL_WAIT_S = 6                     # item 3(d): "A wait of 6 seconds follows each basketball day"
WEEKLY_WAIT_S = 6                         # item 3(e): "6 seconds after each"
WEEKLY_FROM = datetime(2026, 7, 1)        # item 3(e): "every competition-season with a game from 2026-07-01"
WEEKLY_EXCLUDED = ("MLB", "ATP", "WTA", "WC", "NCAA")   # item 3(e): "except MLB, ATP, WTA, WC and NCAA"


@dataclass(frozen=True)
class Step:
    """One step: its number in item 3(d) (a day or a sub-step as "7.2"; the weekly pass "W3.1"), its cli.py argv
    (placeholders until resolve), the seconds waited after it, and its routine non-zero exits (read from cli.py)."""
    label: str
    argv: tuple
    wait_s: int = 0
    routine: frozenset = field(default_factory=frozenset)


def _by_day(item: int, code: str, days: tuple, wait_s: int = 0) -> list:
    return [Step(f"{item}.{k}", ("sync-matches", "--competition", code, "--season", SEASON,
                                 "--date-from", "{%s}" % d, "--date-to", "{%s}" % d), wait_s)
            for k, d in enumerate(days, 1)]


BASKETBALL_DAYS = ("today_minus2", "yesterday", "today", "tomorrow")
NHL_DAYS = ("yesterday", "today", "tomorrow")

# THE DAILY LIST, item 3(d), verbatim in its order (block_1123, run 13:08Z, every exit 0).
DAILY = (
    Step("1", ("sync-matches", "--competition", "MLB", "--season", SEASON, "--date-from", "2026-10-15",
               "--date-to", "{tomorrow}")),
    Step("2", ("retire-orphans", "--competition", "MLB", "--season", SEASON)),        # its dry run: no --apply
    Step("3", ("evaluate", "--sport", "mlb")),
    # Routine exits: NONE. cli.py improve_cmd: a rejection prints "✓ Candidate <v>: REJECTED" and exits 0; its only
    # SystemExit(2) is LegacySoccerImproveRefused, raised for soccer only (training.improve).
    Step("4", ("improve", "--sport", "mlb", "--hold-on-pass"), routine=frozenset()),
    Step("5", ("export-results", "--sport", "mlb", "--competition", "MLB")),
    Step("6", ("sync-kalshi",)),
    *_by_day(7, "NBA", BASKETBALL_DAYS, BASKETBALL_WAIT_S),
    *_by_day(8, "NCAAMB", BASKETBALL_DAYS, BASKETBALL_WAIT_S),
    Step("9", ("sync-teams", "--competition", "NCAA", "--season", SEASON)),
    Step("10", ("sync-matches", "--competition", "NCAA", "--season", SEASON, "--date-from", "{today_minus8}",
                "--date-to", "{yesterday}")),
    Step("11", ("dedupe-matches", "--competition", "NCAA", "--orphans", "--sample", "30")),  # the dry run: no --apply
    *_by_day(12, "NHL", NHL_DAYS),
    Step("13", ("export-fixtures", "--competition", "NHL")),
    Step("14", ("nhl-goalie-sync", "--start", "{yesterday}", "--end", "{today}")),
    Step("15.1", ("sync-matches", "--competition", "ATP", "--date-from", "{yesterday}", "--date-to", "{tomorrow}")),
    Step("15.2", ("sync-matches", "--competition", "WTA", "--date-from", "{yesterday}", "--date-to", "{tomorrow}")),
    Step("16.1", ("sync-kalshi-atp",)),
    Step("16.2", ("sync-kalshi-wta",)),
    Step("17", ("results-tally",)),
)
WEEKLY_BEFORE = "9"                       # item 3(e): the whole-season pass runs BEFORE step 9

# A SYNC STEP'S OWN LINES, echoed under its step line (item 3(b): "the line of counts and any orientation, refusal,
# collision or skipped-listing line"). The texts, read from the code (law 1):
#   "✓ Teams (CODE): created=N updated=N skipped=N"        cli.py sync_teams_cmd; service.SyncResult.__str__
#   "✓ Matches (CODE): created=N updated=N skipped=N [rekeyed=N rekey_refused=N]"   cli.py sync_matches_cmd
#   "✓ Players (CODE, as teams): ..." and "  CODE listing: N markets ... refused ..."  cli.py _tennis_sync_run
#   "skipped N listing(s) of clubs not in the DB: <ids>"   service.skipped_listings_line
#   "provider_id_collision N: ..." / "provider_id_season_unknown N: ..."   service.provider_id_collision_line /
#                                                                          season_unknown_line
#   "orientation_reversed N: <ids> · teams_mismatch_refused M: <ids>"     service.scores_by_team_line (and the
#                                                                          tennis re-read's "CODE re-read: ..." line)
#   "... id N NOT created — ..."                            service.sync_matches' re-key refusal (a log warning)
#   "HELD CODE (SP_SYNC_HOLD)"                              sync_hold.held_line
#   "names kept: N (a historical-season listing)"           service.names_kept_line
#   "✗ ..."                                                 the tennis refusal and the STRICT lines (cli.py)
#   "  CODE refused events held by stored rows ..."         cli.py _tennis_mark_refused
#   "✓ Kalshi...: N prices stored" and "  series ... matched N · unmatched N ..."  cli.py sync-kalshi*
#   "  counts: k v · ...", "  REFUSED game <id>: goalie lists ...", "  not in our DB (sample): ..." and
#   "✗ NHL-GOALIE-SYNC: ..."                                cli.py nhl_goalie_sync_cmd (step 14, a sync whose name
#                                                           does not start "sync-"; SYNC_STEPS below)
# sp_run's own count regexes (TEAMS_LINE ... HELD_LINE) are read first; sync_counts puts the counts on the receipt.
SYNC_ECHO = re.compile(r"^\s*[✓✗]|orientation_|teams_mismatch_refused|provider_id_collision|provider_id_season_unknown"
                       r"|skipped \d+ listing|NOT created|names kept:|(?i:refus)|^\s*\S+ listing:|^\s*series .*matched"
                       r"|^\s*counts: |^\s*not in our DB")
SYNC_STEPS = ("nhl-goalie-sync",)          # item 3(b)'s "a sync": every "sync-" command, and these
_COUNT_LINES = (TEAMS_LINE, FALLBACK_TEAMS_LINE, MATCHES_LINE, SKIPPED_LISTINGS_LINE, SCORES_BY_TEAM_LINE, HELD_LINE)

_popen = subprocess.Popen                 # tests replace these two; nothing else in the module runs a process
_sleep = time.sleep


def routine_vars(today: date) -> dict:
    """sp_run.date_vars(today) (UTC), plus today-2 and today-8, derived as date_vars derives yesterday."""
    return {**date_vars(today),
            "today_minus2": (today - timedelta(days=2)).isoformat(),
            "today_minus8": (today - timedelta(days=8)).isoformat()}


def weekly_steps(lines: list) -> list:
    """The whole-season pass for the list read (item 3(e)): per (code, season), sync-teams then sync-matches, each
    followed by WEEKLY_WAIT_S. The strings are the database's own, never formatted."""
    out = []
    for k, (code, season) in enumerate(lines, 1):
        out += [Step(f"W{k}.1", ("sync-teams", "--competition", code, "--season", season), WEEKLY_WAIT_S),
                Step(f"W{k}.2", ("sync-matches", "--competition", code, "--season", season), WEEKLY_WAIT_S)]
    return out


def resolve(today: date, weekly: list | None = None) -> list:
    """The day's steps in order, placeholders filled (str.format, as sp_run.format_step fills a chain's); with
    `weekly` (the list read), the whole-season pass inserted before step 9."""
    v = routine_vars(today)
    out = []
    for st in DAILY:
        if weekly is not None and st.label == WEEKLY_BEFORE:
            out += weekly_steps(weekly)
        out.append(Step(st.label, tuple(a.format(**v) for a in st.argv), st.wait_s, st.routine))
    return out


@contextmanager
def _in_checkout():
    """A relative DATABASE_URL (the app default sqlite:///./data/sports.db) names the checkout's file, as it does for
    the steps (cwd the checkout): the read runs from there and the working directory is restored."""
    prev = os.getcwd()
    os.chdir(c.REPO)
    try:
        yield
    finally:
        os.chdir(prev)


def weekly_list(since: datetime = WEEKLY_FROM) -> list:
    """Item 3(e)'s list, read-only from the laptop's database (readonly_scope: mode=ro, a missing file refused, never
    created): [(code, season)] for every competition-season holding a match on or after `since` (Match.utc_date,
    naive UTC; Match.season; Competition.code, src/db/schema.py), less WEEKLY_EXCLUDED, sorted."""
    from sqlalchemy import select

    from src.db.database import readonly_scope
    from src.db.schema import Competition, Match
    q = (select(Competition.code, Match.season).join(Match, Match.competition_id == Competition.id)
         .where(Match.utc_date >= since).distinct())
    with _in_checkout(), readonly_scope() as s:
        rows = s.execute(q).all()
    return sorted({(code, season) for code, season in rows if (code or "").upper() not in WEEKLY_EXCLUDED})


def machine_role() -> str | None:
    """src.walters.desk_policy.machine_role(): host.env first, then the environment, then the checkout's .env
    (desk_policy.role_reading). Imported here, before anything runs: desk_policy's module imports only the stdlib."""
    from src.walters import desk_policy
    return desk_policy.machine_role()


def command_text(st: Step) -> str:
    return "python cli.py " + " ".join(st.argv)


def run_step(st: Step) -> tuple:
    """Run one step: (exit or None when it could not start, its echo lines, its redacted tail, seconds). Its output
    streams to the console indented; a sync step's own lines (SYNC_ECHO, sp_run's count lines) are kept."""
    cmd = [sys.executable, "cli.py", *st.argv]
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "COLUMNS": "160"}
    tail: deque = deque(maxlen=TAIL)
    echo: list = []
    is_sync = st.argv[0].startswith("sync-") or st.argv[0] in SYNC_STEPS
    t0 = time.monotonic()
    try:
        proc = _popen(cmd, cwd=c.REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                      errors="replace", env=env, bufsize=1)
    except OSError as e:
        msg = f"could not start: {e.__class__.__name__}: {e}"
        return None, [], [c.redact(msg)], time.monotonic() - t0
    for line in proc.stdout:
        s = line.rstrip("\n")
        sys.stdout.write(f"  | {s}\n")
        if s.strip():
            tail.append(c.redact(s))
            if is_sync and (any(r.match(s) for r in _COUNT_LINES) or SYNC_ECHO.search(s)):
                echo.append(c.redact(s.strip()))
    rc = proc.wait()
    return rc, echo, list(tail), time.monotonic() - t0


def _exit_text(rc) -> str:
    return "?" if rc is None else str(rc)


def _receipt(rec: dict) -> str | None:
    """sp_common.append_receipt(rec), as it is; a write that raises (a full disk, a read-only logs/, an SP_RECEIPTS
    naming a directory) is printed on its own line and returned as its text, never raised: the run goes on (item
    3(b)) and its last line counts it."""
    try:
        c.append_receipt(rec)
        return None
    except Exception as e:                # noqa: BLE001 — any write failure is printed and counted, never raised
        msg = c.redact(f"{e.__class__.__name__}: {e}")
        print(f"    receipt NOT written: {msg}", flush=True)
        return msg


def run(steps: list, run_id: str) -> dict:
    """Run every step in order; a failing step never stops the next, and neither does a receipt that cannot be
    written. Prints the step line (and a sync's own lines) and appends one receipt per step. Returns {ran, failed:
    [(label, command, exit)], routine: [...], receipt_errors: [(label, error)]}."""
    out = {"ran": 0, "failed": [], "routine": [], "receipt_errors": []}
    sha = c.git_sha()
    for st in steps:
        rc, echo, tail, dur = run_step(st)
        out["ran"] += 1
        routine = rc is not None and rc != 0 and rc in st.routine
        line = command_text(st)
        print(f"{st.label} · {line} · exit {_exit_text(rc)} · {dur:.1f}s"
              + (" · routine exit (counted apart)" if routine else ""), flush=True)
        for e in echo:
            print(f"    > {e}", flush=True)
        if rc != 0 and not routine and tail:
            print(f"    last line: {tail[-1][:200]}", flush=True)
        rec = {"kind": "step", "unit": UNIT, "run_id": run_id, "step": st.label, "command": line, "exit": rc,
               "duration_s": round(dur, 1), "git_sha": sha, "tail": tail}
        counts = sync_counts(echo)
        if counts:
            rec["sync"] = counts
        if routine:
            rec["routine_exit"] = True
        if rc is None:                    # law 4: no exit is invented; the step is named as not started
            rec["not_started"] = tail[-1] if tail else "could not start"
        err = _receipt(rec)
        if err:
            out["receipt_errors"].append((st.label, err))
        if routine:
            out["routine"].append((st.label, line, rc))
        elif rc != 0:
            out["failed"].append((st.label, line, rc))
        if st.wait_s:
            _sleep(st.wait_s)
    return out


def dates_line(v: dict, weekly: bool) -> str:
    return (f"laptop-routine{' --weekly' if weekly else ''} · UTC dates: today {v['today']} · yesterday "
            f"{v['yesterday']} · tomorrow {v['tomorrow']} · today-2 {v['today_minus2']} · today-8 {v['today_minus8']}")


def _list_text(lines: list) -> str:
    return (f"weekly list ({len(lines)} competition-season(s) with a game from {WEEKLY_FROM.date().isoformat()}, "
            f"less {', '.join(WEEKLY_EXCLUDED)}): " + (" · ".join(f"{code} {season}" for code, season in lines)
                                                     or "none"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="The laptop's morning routine (addendum 451 item 3): the committed "
                                             "step list, run in order on this checkout's cli.py.")
    ap.add_argument("--weekly", action="store_true", help="the whole-season pass before step 9 (item 3(e))")
    ap.add_argument("--dry-run", action="store_true", help="print the resolved steps; run nothing")
    a = ap.parse_args(argv)
    now = c.utc_now()
    run_id = f"{now.strftime('%Y%m%dT%H%M%SZ')}-{UNIT}"

    role_error = None
    try:
        role = machine_role()             # FIRST: nothing is resolved, read or run before it
    except Exception as e:                # noqa: BLE001 — a role that cannot be read is an unknown role: refused
        role, role_error = None, c.redact(f"{e.__class__.__name__}: {e}")
    if role != "laptop":
        print(f"✗ laptop-routine refused: this machine's role is {role or 'unknown'}, not laptop "
              f"(src.walters.desk_policy.machine_role{'; ' + role_error if role_error else ''}). Nothing was run.",
              flush=True)
        if not a.dry_run:
            rec = {"kind": RUN_KIND, "unit": UNIT, "run_id": run_id, "exit": 2, "refused": "machine_role",
                   "machine_role": role}
            if role_error:
                rec["error"] = role_error
            _receipt(rec)
        return 2

    v = routine_vars(now.date())
    print(dates_line(v, a.weekly), flush=True)
    lines = None
    if a.weekly:
        try:
            lines = weekly_list()
        except Exception as e:            # law 4: a pass asked for and not readable is refused, never dropped
            print(f"✗ laptop-routine refused: the weekly list could not be read ({e.__class__.__name__}: {e}). "
                  "Nothing was run.", flush=True)
            if not a.dry_run:
                _receipt({"kind": RUN_KIND, "unit": UNIT, "run_id": run_id, "exit": 2,
                          "refused": "weekly_list", "error": c.redact(f"{e.__class__.__name__}: {e}")})
            return 2
        print(_list_text(lines), flush=True)
    steps = resolve(now.date(), lines)

    if a.dry_run:
        for st in steps:
            print(f"{st.label}. {command_text(st)}" + (f" [then wait {st.wait_s}s]" if st.wait_s else "")
                  + (f" [routine exits: {', '.join(map(str, sorted(st.routine)))}]" if st.routine else ""))
        print(f"laptop-routine --dry-run: {len(steps)} steps resolved; nothing run.", flush=True)
        return 0

    t0 = time.monotonic()
    r = run(steps, run_id)
    code = 1 if r["failed"] or r["receipt_errors"] else 0
    rec = {"kind": RUN_KIND, "unit": UNIT, "run_id": run_id, "exit": code, "weekly": a.weekly,
           "dates": {k: v[k] for k in ("today", "yesterday", "tomorrow", "today_minus2", "today_minus8")},
           "steps_total": len(steps), "steps_run": r["ran"],
           "nonzero": [{"step": s, "command": cmd, "exit": rc} for s, cmd, rc in r["failed"]],
           "routine_exits": [{"step": s, "command": cmd, "exit": rc} for s, cmd, rc in r["routine"]],
           "duration_s": round(time.monotonic() - t0, 1)}
    if lines is not None:
        rec["weekly_list"] = [f"{code_} {season}" for code_, season in lines]
    if r["receipt_errors"]:
        rec["receipts_not_written"] = [{"step": s, "error": e} for s, e in r["receipt_errors"]]
    errors = list(r["receipt_errors"])
    err = _receipt(rec)
    if err:
        errors.append(("run", err))
        code = 1
    failed = "".join(f" · {s} exit {_exit_text(rc)}" for s, _cmd, rc in r["failed"])
    routine = "".join(f" · {s} exit {rc}" for s, _cmd, rc in r["routine"])
    unwritten = (f" · receipts not written {len(errors)}" + "".join(f" · {s}" for s, _e in errors)) if errors else ""
    print(f"{'✓' if code == 0 else '✗'} laptop-routine: steps run {r['ran']}/{len(steps)} · non-zero exits "
          f"{len(r['failed'])}{failed} · routine exits {len(r['routine'])}{routine}{unwritten}", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
