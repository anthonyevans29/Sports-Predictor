#!/usr/bin/env python3
"""THE LAPTOP'S MORNING ROUTINE: the step list, committed and checked, and one command that runs it.

    python deploy/hosting/laptop_routine.py [--weekly] [--dry-run]

ARCHITECT 2026-11-23 08:17 ET, addendum 451 item 3 (#1067), AMENDED by ARCHITECT 2026-11-23 12:45 ET, addendum 461
items 2 to 4. 451 item 2(a), verbatim: "The fault to mend is small: my hand-written block dropped steps. What mends it
is the step list committed and checked, and one command that runs it. Nothing more." Item 2(b): sp_run.py,
sp_backup.py and chains.py are the host's runner and its commands; NONE OF THE THREE FILES IS EDITED, no ruled pin is
widened and no backup kind is added. This module imports date_vars and the sync count lines from sp_run, and
append_receipt (with redact and git_sha) from sp_common, and changes neither. The list lives here, outside
chains.CHAINS (item 3(f) 17).

WHAT IT DOES (451 item 3(b), as 461 items 2 and 3 amend it):
- Refuses, exit 2, nothing run, when src.walters.desk_policy.not_laptop_reason() is not None (461 item 2(d): "The
  routine calls it, prints the reason and exits 2 with nothing run when it is not None"): the role is host, unset, a
  value that is neither, or host.env exists and cannot be read. That function is the fence's reading, read only, and
  not a fence input; the routine names nothing else of desk_policy's role code (461 item 2(b)), and the refusal never
  rests on closing.mirror_role(), which reads the environment first (461 item 2(c)). The refusal comes before anything
  else: no date is resolved, no database is read, no step runs. A read that raises is refused the same way (its error
  printed and receipted; by its class name alone when redacting it raises too, as for every error the module
  redacts, _redacted). A real run's refusal writes one receipt (refused: not_laptop_reason, the reason beside it;
  its time and run id resolved after the read, for that receipt alone); a --dry-run's writes none and resolves
  nothing, as sp_run's dry runs write none.
- Runs each step as the checkout's own python (sys.executable) on the checkout's cli.py (cwd the checkout), in
  order. A FAILING STEP NEVER STOPS THE NEXT: every exit is printed. No step is retried (item 3 asks for none).
- First line: the UTC dates it resolved. The step's own output streams indented ("  | "), then ONE line per step:
  its number, the command, its exit, its seconds; for a sync step (a command starting "sync-", and nhl-goalie-sync,
  step 13), its own lines of counts and any orientation, refusal, collision, skipped-listing or held line follow it,
  each "    > ". Then the counts line: steps run, steps failed (461 item 3(a): a non-zero exit, a timed-out step and a step that
  could not start are each a failed step; the last two have exit null), and non-zero exits (then steps timed out and
  steps not started, when any; routine exits counted apart; steps whose output is not whole, and receipts not
  written, when any). After the counts, one more line, always, the run's last (479 item 1(b)): EXITS_NOTE, "exits
  counted, not outcomes: a step that exits 0 may still have failed (see #1102)". One line, no logic.
- THE ROUTINE COUNTS EXITS, NOT OUTCOMES (ARCHITECT 2026-11-23, addendum 479 item 1(a); finding #1102). A step that
  exits 0 may still have failed: ten of the twelve commands of the list can end a real failure with exit 0, each read
  in cli.py and src/ (#1102 holds the lines):
    sync-kalshi: an exception, an ok:false result, and a market fetch that failed (it reads as "no open markets");
    sync-kalshi-atp and sync-kalshi-wta: a status read that failed, a listing refusal, no competition row;
    export-results: an export error prints "✗ Results export failed", no file is written;
    sync-matches: a missing competition row; rows an adapter drops before counting (no team id, a date it cannot
      read); listings whose clubs are not in the DB and SP_SYNC_HOLD are ruled exit 0 (204 item 3(c), 332 item 3);
    sync-teams: a missing competition row, after the provider call is spent;
    improve: a holdout under 30 games, or a model it cannot score, reads as REJECTED;
    dedupe-matches (the dry run): a provider lookup that failed is planned "unresolved", and a team with no
      provider id is planned "orphan";
    nhl-goalie-sync: a 200 with an empty body, or with no games in it, reads as no games (refused boxscores are
      ruled exit 0, 389 item 3(e); a non-200 answer, or a body that is not JSON, does exit non-zero);
    results-tally: five sections write "Grade unavailable." and go on; an unreadable closing file is dropped.
  evaluate and export-fixtures exit non-zero on every real failure. The architect reads each step's own lines in the
  console (479 item 1(c)); no exit is changed (479 item 2).
- A step whose non-zero exit is routine carries those exits in the list (Step.routine) and is counted apart. READ FROM
  cli.py (law 1): `improve --sport mlb --hold-on-pass` gives a rejection NO non-zero exit. improve_cmd prints
  "✓ Candidate <v>: REJECTED" (or HELD, or PROMOTED) and returns, exit 0; its one SystemExit is 2 for
  LegacySoccerImproveRefused (cli.py improve_cmd), which src/walters/training.py improve() raises for soccer only. So
  no step of the list has a routine non-zero exit today, and every non-zero exit counts as one.
- One receipt line per step (kind "step", unit "laptop-routine", as bootstrap.py writes its own steps) and one for the
  run (kind "laptop_routine", never "chain", so no reader of the host's chain receipts counts it), by
  sp_common.append_receipt as it is (SP_RECEIPTS, else the checkout's logs/receipts.jsonl). A step that could not start
  is receipted with exit null (law 4: no exit is invented) and `not_started` naming why. A receipt that cannot be
  written (append_receipt raised) is printed ("receipt NOT written: ...", the error's class name alone when redacting it
  raises too) and the run goes on; the run receipt lists those steps and the counts line counts them. A step whose output
  the routine could not read whole (its own error while reading, "output not read: ...", or a pipe still open after the
  step ended, "output not drained: ...") is printed and receipted so (output_error), never as a timeout: the child's
  exit stands, the pipe is still drained, and the run exits 1. RULED (ARCHITECT 2026-11-23 15:20 ET, addendum 469 item
  5(2)): "a step whose output could not be fully read is unreceipted in 461 item 3(d)'s sense; the run exits 1 and the
  receipt says why."
- A PER-STEP TIMEOUT (461 item 3(a)): each entry of the list carries its limit in seconds (Step.limit_s), a constant
  here: DAILY_STEP_LIMIT (1,200) for a daily step, each single-day sync counting as its own step, and WEEKLY_LINE_LIMIT
  (2,400), 461's "2,400 for each line of the weekly pass". RULED (ARCHITECT 2026-11-23 15:20 ET, addendum 469 item
  5(1)): "THE LIMIT IS EACH COMMAND'S, AS BUILT: 2,400 s for each command of a weekly line and 1,200 s for each command
  of a daily step." Each child gets its own limit, so a weekly line's two commands (W k.1, W k.2) get 2,400 s each, not
  one 2,400 s between them, and the two-command daily steps 14 and 15 (451's 15 and 16) get 1,200 s per command. At the
  limit the child is sent SIGTERM, then SIGKILL after KILL_GRACE (10) seconds if it has not ended. The step's line and
  its receipt say "timed out after N s", its exit is recorded as null, it counts as a failed step, and the next step
  runs: after the kill the pipe is drained for KILL_GRACE at most, so a descendant still holding it never holds the
  morning (the step is then also marked "output not drained"). The child's output keeps streaming while it runs (a
  reader thread; the wait is the main thread's). A limit changes only by the architect's ruling: no environment
  variable or option sets one (run() takes an override for the tests alone).
- --dry-run prints the resolved steps and runs nothing (no step, no receipt), as sp_run's --dry-run does. With
  --weekly it reads the weekly list (read-only) to print it.
- Exit (461 item 3(d)): 0 when every step is clean, or its exit is one the list marks routine, and every receipt is
  written; 1 when a step failed, timed out or went unreceipted (a step that could not start, or whose output is not
  whole, included: addendum 469 item 5(2)); 2 for the refusal, nothing run (and for a weekly list that cannot be read,
  nothing run).

THE DAILY LIST (451 item 3(d) as 461 item 2(a) amends it: 16 steps, renumbered in the same order), the architect's
block of 2026-11-23. Placeholders are UTC, from sp_run's date_vars ({today}, {yesterday}, {tomorrow}); date_vars has
no today-2 or today-8, so {today_minus2} and {today_minus8} are derived here the same way (today - timedelta(days=n),
isoformat). Step 1's 2026-10-15 is literal. Steps 6 and 7 run one day at a time (today-2, yesterday, today, tomorrow)
with a wait of 6 seconds after each day; step 11 one day at a time (yesterday, today, tomorrow); steps 14 and 15 are
two steps each (ATP, then WTA).
THE MLB ORPHAN DRY RUN IS NOT IN THE LIST (461 item 2(a)): 451's step 2 left the routine; the dry run stays in the
architect's block, by hand, after the routine returns. 451 item 3(f) 7 is amended to match: five MLB steps stay in the
routine through the off-season (steps 1 to 5 here), and the sixth is the architect's.

--weekly (451 item 3(e)): BEFORE step 8 (NCAA's sync-teams, 451's step 9), the whole-season pass. The list is read
from the laptop's database read-only (src.db.database.readonly_scope: the configured live file, mode=ro, never
created): every distinct (competition code, season) holding a match whose utc_date (naive UTC) is on or after
2026-07-01, except MLB, ATP, WTA, WC and NCAA, sorted by code then season, printed. Per line: sync-teams --competition
C --season S, then sync-matches --competition C --season S, a wait of 6 seconds after each, each with
WEEKLY_LINE_LIMIT. A list that cannot be read refuses the run (exit 2, nothing run).
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
import threading
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
from sp_run import (FALLBACK_TEAMS_LINE, HELD_LINE, MATCHES_LINE, NFL_TEAM_REFUSED_LINE,  # noqa: E402
                    SCORES_BY_TEAM_LINE, SKIPPED_LISTINGS_LINE, TEAMS_LINE, date_vars, sync_counts)

UNIT = "laptop-routine"                   # the receipts' unit: never a host chain's name (chains.CHAINS has no such key)
RUN_KIND = "laptop_routine"               # the run's receipt kind: never "chain"
TAIL = 5
SEASON = "2026"
BASKETBALL_WAIT_S = 6                     # item 3(d): "A wait of 6 seconds follows each basketball day"
WEEKLY_WAIT_S = 6                         # item 3(e): "6 seconds after each"
WEEKLY_FROM = datetime(2026, 7, 1)        # item 3(e): "every competition-season with a game from 2026-07-01"
WEEKLY_EXCLUDED = ("MLB", "ATP", "WTA", "WC", "NCAA")   # item 3(e): "except MLB, ATP, WTA, WC and NCAA"
# 461 item 3(a): "Each entry of the list carries its limit in seconds, a constant in the module: 1,200 for a daily step
# (each single-day sync counts as its own step), 2,400 for each line of the weekly pass. At the limit the child is sent
# SIGTERM, then SIGKILL after 10 seconds if it has not ended." A limit changes only by the architect's ruling.
# RULED (ARCHITECT 2026-11-23 15:20 ET, addendum 469 item 5(1)): "THE LIMIT IS EACH COMMAND'S, AS BUILT: 2,400 s for
# each command of a weekly line and 1,200 s for each command of a daily step." So WEEKLY_LINE_LIMIT is given to each of
# a weekly line's two commands, and DAILY_STEP_LIMIT to each command of steps 14 and 15.
# 479 item 1(b), verbatim, N the Issue of its item 2: the run's last printed line, after the counts.
EXITS_NOTE = "exits counted, not outcomes: a step that exits 0 may still have failed (see #1102)"
DAILY_STEP_LIMIT = 1200
WEEKLY_LINE_LIMIT = 2400
KILL_GRACE = 10


@dataclass(frozen=True)
class Step:
    """One step: its number in the daily list (a day or a sub-step as "6.2"; the weekly pass "W3.1"), its cli.py argv
    (placeholders until resolve), the seconds waited after it, its routine non-zero exits (read from cli.py), and its
    limit in seconds (461 item 3(a): DAILY_STEP_LIMIT, or WEEKLY_LINE_LIMIT on the weekly pass)."""
    label: str
    argv: tuple
    wait_s: int = 0
    routine: frozenset = field(default_factory=frozenset)
    limit_s: int = DAILY_STEP_LIMIT


def _by_day(item: int, code: str, days: tuple, wait_s: int = 0) -> list:
    """One step per day: each single-day sync is its own step, with its own DAILY_STEP_LIMIT (461 item 3(a))."""
    return [Step(f"{item}.{k}", ("sync-matches", "--competition", code, "--season", SEASON,
                                 "--date-from", "{%s}" % d, "--date-to", "{%s}" % d), wait_s, limit_s=DAILY_STEP_LIMIT)
            for k, d in enumerate(days, 1)]


BASKETBALL_DAYS = ("today_minus2", "yesterday", "today", "tomorrow")
NHL_DAYS = ("yesterday", "today", "tomorrow")

# THE DAILY LIST, 451 item 3(d) in its order (block_1123, run 13:08Z, every exit 0), less its step 2 and renumbered
# 1..16 in the same order (461 item 2(a)). Every step carries DAILY_STEP_LIMIT (Step's default; 461 item 3(a)).
DAILY = (
    Step("1", ("sync-matches", "--competition", "MLB", "--season", SEASON, "--date-from", "2026-10-15",
               "--date-to", "{tomorrow}")),
    Step("2", ("evaluate", "--sport", "mlb")),
    # Routine exits: NONE. cli.py improve_cmd: a rejection prints "✓ Candidate <v>: REJECTED" and exits 0; its only
    # SystemExit(2) is LegacySoccerImproveRefused, raised for soccer only (training.improve).
    Step("3", ("improve", "--sport", "mlb", "--hold-on-pass"), routine=frozenset()),
    Step("4", ("export-results", "--sport", "mlb", "--competition", "MLB")),
    Step("5", ("sync-kalshi",)),
    *_by_day(6, "NBA", BASKETBALL_DAYS, BASKETBALL_WAIT_S),
    *_by_day(7, "NCAAMB", BASKETBALL_DAYS, BASKETBALL_WAIT_S),
    Step("8", ("sync-teams", "--competition", "NCAA", "--season", SEASON)),
    Step("9", ("sync-matches", "--competition", "NCAA", "--season", SEASON, "--date-from", "{today_minus8}",
               "--date-to", "{yesterday}")),
    Step("10", ("dedupe-matches", "--competition", "NCAA", "--orphans", "--sample", "30")),  # the dry run: no --apply
    *_by_day(11, "NHL", NHL_DAYS),
    Step("12", ("export-fixtures", "--competition", "NHL")),
    Step("13", ("nhl-goalie-sync", "--start", "{yesterday}", "--end", "{today}")),
    Step("14.1", ("sync-matches", "--competition", "ATP", "--date-from", "{yesterday}", "--date-to", "{tomorrow}")),
    Step("14.2", ("sync-matches", "--competition", "WTA", "--date-from", "{yesterday}", "--date-to", "{tomorrow}")),
    Step("15.1", ("sync-kalshi-atp",)),
    Step("15.2", ("sync-kalshi-wta",)),
    Step("16", ("results-tally",)),
)
WEEKLY_BEFORE = "8"                       # 451 item 3(e): the pass runs BEFORE NCAA's sync-teams (451's step 9)

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
#   "nfl_team_refused N: <listing id> (match <id>), ..."    service.nfl_team_refused_line (addendum 500 3(a), 527 1)
#   "HELD CODE (SP_SYNC_HOLD)"                              sync_hold.held_line
#   "names kept: N (a historical-season listing)"           service.names_kept_line
#   "✗ ..."                                                 the tennis refusal and the STRICT lines (cli.py)
#   "  CODE refused events held by stored rows ..."         cli.py _tennis_mark_refused
#   "✓ Kalshi...: N prices stored" and "  series ... matched N · unmatched N ..."  cli.py sync-kalshi*
#   "  counts: k v · ...", "  REFUSED game <id>: goalie lists ...", "  not in our DB (sample): ..." and
#   "✗ NHL-GOALIE-SYNC: ..."                                cli.py nhl_goalie_sync_cmd (step 13, a sync whose name
#                                                           does not start "sync-"; SYNC_STEPS below)
# sp_run's own count regexes (TEAMS_LINE ... HELD_LINE) are read first; sync_counts puts the counts on the receipt.
SYNC_ECHO = re.compile(r"^\s*[✓✗]|orientation_|teams_mismatch_refused|provider_id_collision|provider_id_season_unknown"
                       r"|skipped \d+ listing|NOT created|names kept:|(?i:refus)|^\s*\S+ listing:|^\s*series .*matched"
                       r"|^\s*counts: |^\s*not in our DB")
SYNC_STEPS = ("nhl-goalie-sync",)          # item 3(b)'s "a sync": every "sync-" command, and these
_COUNT_LINES = (TEAMS_LINE, FALLBACK_TEAMS_LINE, MATCHES_LINE, SKIPPED_LISTINGS_LINE, SCORES_BY_TEAM_LINE, HELD_LINE,
                NFL_TEAM_REFUSED_LINE)

_popen = subprocess.Popen                 # tests replace these two; nothing else in the module runs a process
_sleep = time.sleep


def routine_vars(today: date) -> dict:
    """sp_run.date_vars(today) (UTC), plus today-2 and today-8, derived as date_vars derives yesterday."""
    return {**date_vars(today),
            "today_minus2": (today - timedelta(days=2)).isoformat(),
            "today_minus8": (today - timedelta(days=8)).isoformat()}


def weekly_steps(lines: list) -> list:
    """The whole-season pass for the list read (item 3(e)): per (code, season), sync-teams then sync-matches, each
    followed by WEEKLY_WAIT_S and each carrying WEEKLY_LINE_LIMIT (461 item 3(a); each command's, as built, ruled by
    addendum 469 item 5(1)). The strings are the database's own, never formatted."""
    out = []
    for k, (code, season) in enumerate(lines, 1):
        out += [Step(f"W{k}.1", ("sync-teams", "--competition", code, "--season", season), WEEKLY_WAIT_S,
                     limit_s=WEEKLY_LINE_LIMIT),
                Step(f"W{k}.2", ("sync-matches", "--competition", code, "--season", season), WEEKLY_WAIT_S,
                     limit_s=WEEKLY_LINE_LIMIT)]
    return out


def resolve(today: date, weekly: list | None = None) -> list:
    """The day's steps in order, placeholders filled (str.format, as sp_run.format_step fills a chain's); with
    `weekly` (the list read), the whole-season pass inserted before step 8 (WEEKLY_BEFORE)."""
    v = routine_vars(today)
    out = []
    for st in DAILY:
        if weekly is not None and st.label == WEEKLY_BEFORE:
            out += weekly_steps(weekly)
        out.append(Step(st.label, tuple(a.format(**v) for a in st.argv), st.wait_s, st.routine, st.limit_s))
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


def not_laptop_reason() -> str | None:
    """src.walters.desk_policy.not_laptop_reason() (461 item 2(d)): None on the laptop; otherwise why this machine is
    not the laptop (host.env first, then the environment, then the checkout's .env; read only). Not a fence input.
    Imported here, before anything runs: desk_policy's module imports only the stdlib."""
    from src.walters import desk_policy
    return desk_policy.not_laptop_reason()


def _redacted(text: str, fallback: str) -> str:
    """c.redact(text), or `fallback` (the error's class name alone) when redacting raises: sp_common.redact reads the
    checkout's .env (_dotenv), and a .env it cannot decode raises UnicodeDecodeError. Every error path of the module
    redacts through this one helper (run_step's note and could-not-start message, _receipt, main's role-read error
    and weekly-list refusal), so no error path raises and the refusal stays exit 2 (461 item 3(d))."""
    try:
        return c.redact(text)
    except Exception:                     # noqa: BLE001 — redact itself failing: the fallback, never raised
        return fallback


def command_text(st: Step) -> str:
    return "python cli.py " + " ".join(st.argv)


def timed_out_text(limit_s) -> str:
    """461 item 3(a): 'The step's line and receipt say "timed out after N s"'."""
    return f"timed out after {limit_s} s"


def _stop(proc, grace_s) -> str:
    """461 item 3(a): SIGTERM at the limit, then SIGKILL after grace_s seconds if the child has not ended. Returns the
    signal that ended it ("SIGTERM" or "SIGKILL")."""
    try:
        proc.terminate()
    except OSError:                       # it ended between the limit and the signal
        pass
    try:
        proc.wait(timeout=grace_s)
        return "SIGTERM"
    except subprocess.TimeoutExpired:
        pass
    try:
        proc.kill()
    except OSError:
        pass
    proc.wait()
    return "SIGKILL"


def run_step(st: Step, limit_s=None, grace_s=KILL_GRACE) -> tuple:
    """Run one step: (exit or None when it could not start or timed out, its echo lines, its redacted tail, seconds,
    its timeout: None, or {"limit_s", "ended_by"}, and its output: None, or why its output is not whole ("output not
    read: ..." for the routine's own error while reading, "output not drained: ..." for a pipe left open)). Its output
    streams to the console indented, from a reader thread, while the main thread waits out the step's limit
    (st.limit_s; `limit_s` overrides it for the tests alone); a sync step's own lines (SYNC_ECHO, sp_run's count
    lines) are kept."""
    limit = st.limit_s if limit_s is None else limit_s
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
        msg = _redacted(f"could not start: {e.__class__.__name__}: {e}", f"could not start: {e.__class__.__name__}")
        return None, [], [msg], time.monotonic() - t0, None, None

    lock = threading.Lock()               # the reader's lists and state, copied under it below
    state = {"lines": 0, "error": None, "quiet": False}

    def note(e):                          # the routine's own error while reading, kept once; never raised
        text = _redacted(f"{e.__class__.__name__}: {e}", e.__class__.__name__)
        with lock:
            state["error"] = state["error"] or text

    def read():
        # The routine's own error while reading (redact, a regex, the console write) is kept, and the pipe is still
        # drained (raw, from then on), so the child never blocks on a full pipe and the error never reads as the step
        # hanging.
        try:
            for line in proc.stdout:
                with lock:
                    state["lines"] += 1
                    quiet = state["quiet"]
                if quiet:                 # left by run_step (below): drained, never printed into the next step
                    continue
                s = line.rstrip("\n")
                sys.stdout.write(f"  | {s}\n")
                if s.strip():
                    red = c.redact(s)
                    keep = is_sync and (any(r.match(s) for r in _COUNT_LINES) or SYNC_ECHO.search(s))
                    red_echo = c.redact(s.strip()) if keep else None
                    with lock:
                        tail.append(red)
                        if keep:
                            echo.append(red_echo)
        except Exception as e:            # noqa: BLE001 — kept and named on the step, never raised
            note(e)
            try:
                while proc.stdout.buffer.read1(65536):
                    with lock:
                        state["lines"] += 1
            except Exception:             # noqa: BLE001
                pass

    reader = threading.Thread(target=read, name=f"{UNIT}-{st.label}", daemon=True)
    reader.start()
    timeout = None
    try:
        rc = proc.wait(timeout=limit)
    except subprocess.TimeoutExpired:
        timeout = {"limit_s": limit, "ended_by": _stop(proc, grace_s)}
        rc = None                         # 461 item 3(a): "its exit is recorded as null"
    # The pipe closes when the child ends, and the reader drains what is left: after a clean exit it is joined for as
    # long as it is still reading (a slow console included), so a sync's last count line is not lost. Only a reader
    # that reads no line for grace_s (a grandchild holding the pipe open, a console that takes nothing), or is still
    # reading after the step's limit again, is left (a daemon thread, from then on silent); the step then says so.
    # After a timeout the drain is capped at grace_s (461 item 3(a): "the next step runs"): a descendant that outlived
    # the kill and keeps writing never holds the morning a further limit; the pipe drains silently in the daemon.
    undrained = False
    end = time.monotonic() + (grace_s if timeout else max(limit, grace_s))
    while reader.is_alive():
        with lock:
            seen = state["lines"]
        reader.join(timeout=grace_s)
        if not reader.is_alive():
            break
        with lock:
            if state["lines"] == seen or time.monotonic() >= end:
                state["quiet"] = undrained = True
                break
    sys.stdout.flush()
    with lock:
        output = None
        if state["error"]:
            output = f"output not read: {state['error']}"
        elif undrained:
            output = f"output not drained: the pipe was still open {grace_s} s after the step ended"
        return rc, list(echo), list(tail), time.monotonic() - t0, timeout, output


def _exit_text(rc) -> str:
    return "?" if rc is None else str(rc)


def _receipt(rec: dict) -> str | None:
    """sp_common.append_receipt(rec), as it is; a write that raises (a full disk, a read-only logs/, an SP_RECEIPTS
    naming a directory) is printed on its own line and returned as its text, never raised: the run goes on (item
    3(b)) and its counts line counts it."""
    try:
        c.append_receipt(rec)
        return None
    except Exception as e:                # noqa: BLE001 — any write failure is printed and counted, never raised
        msg = _redacted(f"{e.__class__.__name__}: {e}", e.__class__.__name__)
        print(f"    receipt NOT written: {msg}", flush=True)
        return msg


def run(steps: list, run_id: str, limit_s=None, grace_s=KILL_GRACE) -> dict:
    """Run every step in order; a failing step never stops the next, nor does a step that timed out or a receipt that
    cannot be written. Prints the step line (and a sync's own lines) and appends one receipt per step. `limit_s` and
    `grace_s` override each step's limit and KILL_GRACE for the tests alone (main passes neither). Returns {ran,
    failed: [(label, command, exit)] (a non-zero exit), timed_out: [(label, command, limit_s)], not_started: [(label,
    command, why)], routine: [...], receipt_errors: [(label, error)], output_errors: [(label, why)]}. A failed step
    (461 item 3(a)) is one of failed, timed_out or not_started; the last two have exit null."""
    out = {"ran": 0, "failed": [], "timed_out": [], "not_started": [], "routine": [], "receipt_errors": [],
           "output_errors": []}
    sha = c.git_sha()
    for st in steps:
        rc, echo, tail, dur, timeout, output = run_step(st, limit_s, grace_s)
        out["ran"] += 1
        routine = rc is not None and rc != 0 and rc in st.routine
        line = command_text(st)
        status = (f"{timed_out_text(timeout['limit_s'])} · exit null" if timeout else f"exit {_exit_text(rc)}")
        print(f"{st.label} · {line} · {status} · {dur:.1f}s"
              + (" · routine exit (counted apart)" if routine else ""), flush=True)
        for e in echo:
            print(f"    > {e}", flush=True)
        if rc != 0 and not routine and tail:
            print(f"    last line: {tail[-1][:200]}", flush=True)
        if output:
            print(f"    {output}", flush=True)
        rec = {"kind": "step", "unit": UNIT, "run_id": run_id, "step": st.label, "command": line, "exit": rc,
               "duration_s": round(dur, 1), "git_sha": sha, "tail": tail}
        counts = sync_counts(echo)
        if counts:
            rec["sync"] = counts
        if routine:
            rec["routine_exit"] = True
        if output:                        # the receipt says its output is not whole; never a clean step's receipt
            rec["output_error"] = output
        if timeout:                       # 461 item 3(a): its exit null, the receipt saying "timed out after N s"
            rec.update(timed_out=timed_out_text(timeout["limit_s"]), limit_s=timeout["limit_s"],
                       ended_by=timeout["ended_by"])
        elif rc is None:                  # law 4: no exit is invented; the step is named as not started
            rec["not_started"] = tail[-1] if tail else "could not start"
        err = _receipt(rec)
        if err:
            out["receipt_errors"].append((st.label, err))
        if output:
            out["output_errors"].append((st.label, output))
        if routine:
            out["routine"].append((st.label, line, rc))
        elif timeout:                     # a failed step (461 item 3(a)), its exit null
            out["timed_out"].append((st.label, line, timeout["limit_s"]))
        elif rc is None:                  # a failed step that could not start, its exit null
            out["not_started"].append((st.label, line, rec["not_started"]))
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


def _run_id(now: datetime) -> str:
    return f"{now.strftime('%Y%m%dT%H%M%SZ')}-{UNIT}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="The laptop's morning routine (addendum 451 item 3, amended by 461): the "
                                             "committed step list, run in order on this checkout's cli.py.")
    ap.add_argument("--weekly", action="store_true", help="the whole-season pass before step 8 (451 item 3(e))")
    ap.add_argument("--dry-run", action="store_true", help="print the resolved steps; run nothing")
    a = ap.parse_args(argv)

    read_error = None
    try:
        reason = not_laptop_reason()      # FIRST: nothing is resolved, read or run before it
    except Exception as e:                # noqa: BLE001 — a reason that cannot be read is an unknown role: refused
        read_error = _redacted(f"{e.__class__.__name__}: {e}", e.__class__.__name__)
        reason = f"the role could not be read ({read_error})"
    if reason is not None:
        print(f"✗ laptop-routine refused: {reason}; this command runs on the laptop only "
              "(src.walters.desk_policy.not_laptop_reason). Nothing was run.", flush=True)
        if not a.dry_run:                 # the run's time and id, resolved only now, for its one receipt
            rec = {"kind": RUN_KIND, "unit": UNIT, "run_id": _run_id(c.utc_now()), "exit": 2,
                   "refused": "not_laptop_reason", "not_laptop_reason": reason}
            if read_error:
                rec["error"] = read_error
            _receipt(rec)
        return 2

    now = c.utc_now()
    run_id = _run_id(now)
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
                          "refused": "weekly_list", "error": _redacted(f"{e.__class__.__name__}: {e}",
                                                                       e.__class__.__name__)})
            return 2
        print(_list_text(lines), flush=True)
    steps = resolve(now.date(), lines)

    if a.dry_run:
        for st in steps:
            print(f"{st.label}. {command_text(st)}" + f" [limit {st.limit_s}s]"
                  + (f" [then wait {st.wait_s}s]" if st.wait_s else "")
                  + (f" [routine exits: {', '.join(map(str, sorted(st.routine)))}]" if st.routine else ""))
        print(f"laptop-routine --dry-run: {len(steps)} steps resolved; nothing run.", flush=True)
        return 0

    t0 = time.monotonic()
    r = run(steps, run_id)
    failed_n = len(r["failed"]) + len(r["timed_out"]) + len(r["not_started"])   # 461 item 3(a): each a failed step
    code = 1 if failed_n or r["receipt_errors"] or r["output_errors"] else 0     # 461 item 3(d)
    rec = {"kind": RUN_KIND, "unit": UNIT, "run_id": run_id, "exit": code, "weekly": a.weekly,
           "dates": {k: v[k] for k in ("today", "yesterday", "tomorrow", "today_minus2", "today_minus8")},
           "steps_total": len(steps), "steps_run": r["ran"],
           "nonzero": [{"step": s, "command": cmd, "exit": rc} for s, cmd, rc in r["failed"]],
           "timed_out": [{"step": s, "command": cmd, "exit": None, "timed_out": timed_out_text(n)}
                         for s, cmd, n in r["timed_out"]],
           "not_started": [{"step": s, "command": cmd, "exit": None, "not_started": why}
                           for s, cmd, why in r["not_started"]],
           "steps_failed": failed_n,
           "routine_exits": [{"step": s, "command": cmd, "exit": rc} for s, cmd, rc in r["routine"]],
           "duration_s": round(time.monotonic() - t0, 1)}
    if lines is not None:
        rec["weekly_list"] = [f"{code_} {season}" for code_, season in lines]
    if r["output_errors"]:
        rec["output_not_whole"] = [{"step": s, "output_error": why} for s, why in r["output_errors"]]
    if r["receipt_errors"]:
        rec["receipts_not_written"] = [{"step": s, "error": e} for s, e in r["receipt_errors"]]
    errors = list(r["receipt_errors"])
    err = _receipt(rec)
    if err:
        errors.append(("run", err))
        code = 1
    failed = "".join(f" · {s} exit {rc}" for s, _cmd, rc in r["failed"])
    timed = "".join(f" · {s} {timed_out_text(n)}" for s, _cmd, n in r["timed_out"])
    timed = f" · timed out {len(r['timed_out'])}{timed}" if r["timed_out"] else ""
    unstarted = "".join(f" · {s}" for s, _cmd, _why in r["not_started"])
    unstarted = f" · not started {len(r['not_started'])}{unstarted}" if r["not_started"] else ""
    routine = "".join(f" · {s} exit {rc}" for s, _cmd, rc in r["routine"])
    unread = "".join(f" · {s}" for s, _why in r["output_errors"])
    unread = f" · output not whole {len(r['output_errors'])}{unread}" if r["output_errors"] else ""
    unwritten = (f" · receipts not written {len(errors)}" + "".join(f" · {s}" for s, _e in errors)) if errors else ""
    print(f"{'✓' if code == 0 else '✗'} laptop-routine: steps run {r['ran']}/{len(steps)} · failed {failed_n} · "
          f"non-zero exits {len(r['failed'])}{failed}{timed}{unstarted} · routine exits {len(r['routine'])}{routine}"
          f"{unread}{unwritten}", flush=True)
    print(EXITS_NOTE, flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
