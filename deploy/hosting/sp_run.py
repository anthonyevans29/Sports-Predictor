#!/usr/bin/env python3
"""Run one chain from chains.py under the DB lock, writing receipts.

    sp_run.py <chain> [--set key=value ...] [--dry-run] [--operator]

- Steps run in order; the first non-zero exit stops the chain (its exit is
  the chain's exit, so systemd's OnFailure pages). A chain flagged
  `continue_on_sync_failure` (the window chain, ARCHITECT 2026-10-16,
  addendum 84 item 2(b)) records a failed SYNC step and runs on; a failed
  card/export step still stops it; its exit is the first failed step's, so
  the notice still fires, and its post (the window page) runs when only sync
  steps failed.
- One `step` receipt per step (exit, duration, last <=5 console lines,
  redacted) and one `chain` receipt per run (backup, counts, exports).
- A console line starting "SP-PAGE:" (improve's H0-5 hold) pages the
  operator via sp_notify and is receipted; the chain continues.
- `operator_only` chains (soccer-refresh, H0-6) refuse without --operator.
- `active_from` chains outside their window log a skipped receipt, exit 0.
  The date is overridable per chain via its `active_from_env` variable
  (e.g. SP_NHL_ACTIVE_FROM in host.env); every run prints and receipts it.
- H0-16(b): SP_PARALLEL_MODE=designated + SP_DESIGNATED_DAYS=Fri,Sat,...
  skips METERED steps on other days (receipted as skipped). Default: full.
- #765/#728 (ARCHITECT 2026-11-01, addendum 204 item 3): a step's printed sync
  counts ride on its receipt (`sync`); the chain receipt carries one line per
  competition-season a sync-teams step named (`competitions`: sync-teams'
  created/updated, sync-matches' skipped count) and every step that skipped
  listings of clubs not in the DB (`listings_skipped`), which the summary line
  names. The exit is unchanged (law 4: skipped, not faked).
- A failed sync-teams step does NOT stop the chain (ARCHITECT 2026-11-01,
  addendum 207 item 4): the run goes on to that competition's sync-matches
  and every later step, the exit is the FIRST failure's, and the summary line
  names the failed step. Every other step stops a chain as before.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from collections import deque
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_common as c  # noqa: E402
from chains import (CHAINS, FRESHEN_FAMILY, FRESHEN_MIN_INTERVAL_S, IMMINENT_INJURY_FAMILIES,  # noqa: E402
                    PROX_FAR_H, PROX_IMMINENT_H, UNMETERED, WINDOW_HOURS, WINDOW_KALSHI,
                    WINDOW_KALSHI_CAPTURE_ONLY)

TAIL = 5
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def date_vars(today: date) -> dict:
    sat = today + timedelta(days=(5 - today.weekday()) % 7)
    return {
        "today": today.isoformat(),
        "yesterday": (today - timedelta(days=1)).isoformat(),
        "tomorrow": (today + timedelta(days=1)).isoformat(),
        # {today_plus1}..{today_plus7}: the ncaa-schedule chain's forward week (ARCHITECT 2026-10-09)
        **{f"today_plus{n}": (today + timedelta(days=n)).isoformat() for n in range(1, 8)},
        "sat": sat.isoformat(),
        "sat_plus3": (sat + timedelta(days=3)).isoformat(),
    }


def format_step(st: list[str], v: dict) -> list[str]:
    """One chain step with its placeholders filled ({today}, {sat}, ... and any --set key): str.format on every
    argument. resolve() fills every chain's steps with it."""
    return [a.format(**v) for a in st]


def fullseason_entries(p) -> list[tuple[int, str, str, str]]:
    """The list's ONE parser: (line number, stripped line, code, season) per line of a full-season list that is
    neither blank nor a '#' comment, in file order, split on the first '|' and each half stripped, braces as written.
    A read error raises as it always did; a line without '|', or whose code or season is empty once stripped
    ("|2026", "NFL|", "|"), raises ValueError naming the file and the line: the chain refuses it at resolve instead of
    running a step bound to fail. Read as utf-8-sig, so a hand-edited file's leading BOM never rides into the first
    code (str.strip keeps U+FEFF)."""
    out = []
    for n, line in enumerate(Path(p).read_text(encoding="utf-8-sig").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "|" not in line:
            raise ValueError(f"{p} line {n}: {line!r} is not CODE|SEASON")
        code, season = (x.strip() for x in line.split("|", 1))
        if not code or not season:
            which = "code and season" if not code and not season else "code" if not code else "season"
            raise ValueError(f"{p} line {n}: {line!r} is not CODE|SEASON (empty {which})")
        out.append((n, line, code, season))
    return out


def fullseason_resolve(p, v: dict) -> list[list[str]]:
    """weekly-fullseason's steps for the list at `p`, filled as resolve() fills every chain's steps: per line,
    `sync-teams --competition CODE --season SEASON` then `sync-matches --competition CODE --season SEASON` (TEAMS
    BEFORE MATCHES, ARCHITECT 2026-11-01, addendum 204 item 3(a): "immediately before each `sync-matches` line"), both
    from the one str.format of the line through format_step with `v`. The ONE path from the file to the commands:
    resolve() runs weekly-fullseason through it and cutover-readiness counts the list through it (ARCHITECT
    2026-10-18, addendum 122 item 3(b); one competition per sync-matches step), so a line the readout counts is a line
    the chain runs, and a line the chain fails on the readout reads UNPARSEABLE. Raises ValueError naming the file and
    line for a line the parser refuses (fullseason_entries) and for a brace str.format cannot fill ("NFL|{season}":
    KeyError; a lone '}': ValueError; "{0}": IndexError; "{today.x}": AttributeError), the error's type and text in
    the message, and for a code or season that str.format leaves empty ("NFL|{today:.0}"), as the parser refuses an
    empty half."""
    out = []
    for n, line, code, season in fullseason_entries(p):
        try:
            st = format_step(["sync-matches", "--competition", code, "--season", season], v)
        except (KeyError, ValueError, IndexError, AttributeError, TypeError) as e:
            raise ValueError(f"{p} line {n}: {line!r} does not resolve: its braces fail the chain's str.format "
                             f"({type(e).__name__}: {e})") from e
        if not st[2].strip() or not st[4].strip():
            which = ("code and season" if not st[2].strip() and not st[4].strip()
                     else "code" if not st[2].strip() else "season")
            raise ValueError(f"{p} line {n}: {line!r} is not CODE|SEASON (empty {which} after str.format)")
        out += [["sync-teams", *st[1:]], st]
    return out


def fullseason_steps(v: dict | None = None) -> list[list[str]]:
    """weekly-fullseason's steps from the file SP_FULLSEASON_LIST names, filled with `v` (default: today's date
    variables); refuses a missing setting or file, and a list with no competitions."""
    p = c.setting("SP_FULLSEASON_LIST")
    if not p or not Path(p).exists():
        raise SystemExit("✗ weekly-fullseason: SP_FULLSEASON_LIST missing — refusing to "
                         "guess the competition list (see hosting-h1.md step T9).")
    steps = fullseason_resolve(p, date_vars(c.utc_now().date()) if v is None else v)
    if not steps:
        raise SystemExit(f"✗ weekly-fullseason: {p} lists no competitions.")
    return steps


_LAST_WINDOW_PLAN: dict = {}


def window_plan(now) -> dict:
    """The window chain's plan, read-only from the DB (see chains.py), scaled
    by PROXIMITY: each competition's tier comes from its next kickoff inside
    the window. Returns {"steps", "tiers", "skipped_by_proximity"}."""
    import sqlite3
    from datetime import timedelta
    hi = now + timedelta(hours=WINDOW_HOURS)
    far = now + timedelta(hours=PROX_FAR_H)
    skip = {s.strip().upper() for s in (c.setting("SP_SKIP_FAMILIES") or "").split(",") if s.strip()}
    fmt = "%Y-%m-%d %H:%M:%S"
    card = [["window-card", "--hours", str(WINDOW_HOURS)]]
    empty = {"steps": card, "tiers": {"far": [], "near": [], "imminent": []},
             "skipped_by_proximity": 0}
    try:
        con = c.ro_connect(c.db_path())
    except (FileNotFoundError, sqlite3.Error):
        return empty
    try:
        comps = con.execute(
            "SELECT c.code, c.sport, m.season, MIN(m.utc_date), "
            "SUM(CASE WHEN m.utc_date < ? THEN 1 ELSE 0 END) FROM matches m "
            "JOIN competitions c ON c.id = m.competition_id "
            "WHERE m.utc_date >= ? AND m.utc_date < ? AND m.status != 'FINISHED' "
            "GROUP BY c.code, c.sport, m.season ORDER BY MIN(m.utc_date), c.code",
            (far.strftime(fmt), now.strftime(fmt), hi.strftime(fmt))).fetchall()
    except sqlite3.Error:
        # a DB without the schema (host not bootstrapped): plan only the card
        # step, which then fails loudly and pages via OnFailure
        return empty
    finally:
        con.close()
    days = sorted({now.date().isoformat(), hi.date().isoformat()})
    tiers: dict[str, list[str]] = {"far": [], "near": [], "imminent": []}
    tier_of = {}
    for code, sport, season, first, n6 in comps:
        first_dt = datetime.fromisoformat(str(first)[:19])
        h = (first_dt - now).total_seconds() / 3600
        tier = "far" if h > PROX_FAR_H else ("near" if h >= PROX_IMMINENT_H else "imminent")
        tier_of[(code, season)] = tier
        tiers[tier].append(code)

    def build(tiered: bool) -> list[list[str]]:
        steps: list[list[str]] = []
        for code, sport, season, _first, _n6 in comps:
            if str(sport).upper() in skip:
                continue
            for d in days:  # schedule check: every tier
                steps.append(["sync-matches", "--competition", code, "--season", season,
                              "--date-from", d, "--date-to", d])
        priced = [(code, sport, season, n6) for code, sport, season, _f, n6 in comps
                  if not tiered or tier_of[(code, season)] != "far"]
        football = False
        for code, sport, season, n6 in priced:
            if str(sport).upper() == "NFL":
                football = True
                continue
            steps.append(["sync-odds", "--competition", code, "--season", season,
                          "--limit", str(max(int(n6 or 0), 1))])
        if football:
            steps.append(["sync-odds-football"])
        seen = set()
        for code, *_ in priced:
            for st in WINDOW_KALSHI.get(code, []):
                if tuple(st) not in seen:
                    seen.add(tuple(st))
                    steps.append(list(st))
        # CAPTURE ONLY (ARCHITECT 2026-10-24, addendum 164 item 2(a)): the expansion leagues' series, tiered as the
        # Kalshi syncs above (near / imminent only), one series per step; capture for the record: no venue line, no export, no call.
        for code, *_ in priced:
            for st in WINDOW_KALSHI_CAPTURE_ONLY.get(code, []):
                if tuple(st) not in seen:
                    seen.add(tuple(st))
                    steps.append(list(st))
        # T-90 hole (ruling 2026-09-29): injuries for the model families' games
        # inside the imminent tier, BEFORE the card computes its T-90 signatures.
        for code, sport, season, _f, _n6 in comps:
            fam = FRESHEN_FAMILY.get((str(sport).lower(), code))
            if fam not in IMMINENT_INJURY_FAMILIES or str(sport).upper() in skip:
                continue
            if tiered and tier_of[(code, season)] != "imminent":
                continue
            steps.append(["sync-injuries", "--competition", code, "--season", season,
                          "--kickoff-within-hours", str(PROX_IMMINENT_H)])
        return steps + card

    steps, flat = build(True), build(False)
    return {"steps": steps, "tiers": tiers, "skipped_by_proximity": len(flat) - len(steps)}


def window_steps(now) -> list[list[str]]:
    plan = window_plan(now)
    _LAST_WINDOW_PLAN.clear()
    _LAST_WINDOW_PLAN.update(plan)
    return plan["steps"]


def resolve(name: str, overrides: dict, today: date, now=None) -> list[list[str]]:
    chain = CHAINS[name]
    v = {**date_vars(today), **overrides}
    if chain.get("window_plan"):
        steps = window_steps(now or c.utc_now().replace(tzinfo=None))
    elif chain.get("fullseason"):
        return fullseason_steps(v)      # filled by fullseason_resolve, the path cutover-readiness counts through
    else:
        steps = chain["steps"]
    return [format_step(st, v) for st in steps]


def metered_skip(cmd: str, today: date) -> bool:
    if (c.setting("SP_PARALLEL_MODE") or "full") != "designated":
        return False
    days = {d.strip()[:3].title() for d in (c.setting("SP_DESIGNATED_DAYS") or "").split(",")
            if d.strip()}
    return cmd not in UNMETERED and DAYS[today.weekday()] not in days


def page(msg: str, run_id: str) -> None:
    import sp_notify
    sp_notify.deliver(kind="page", title="sports-predictor: operator action", body=msg,
                      extra={"run_id": run_id})


# THE SYNC COUNTS A CHAIN'S RECEIPT CARRIES (ARCHITECT 2026-11-01, addendum 204 item 3(a) and (c); #765, #728): "its
# receipt line per competition carries sync-teams' created/updated and sync-matches' skipped count", and "skipped N
# listing(s) of clubs not in the DB: <ids>" is "a line the chain prints in its own receipt [...] and a chain step with
# N > 0 says so in the chain's summary line". The lines the commands print (law 1, cli.py):
#   sync-teams           "✓ Teams (CODE): created=N updated=N skipped=N"             (SyncResult.__str__)
#   sync-teams, the MLB api-sports fallback (SP_SKIP_FAMILIES names MLB; cli._mlb_fallback_run, its own sync_teams):
#                        "  teams SEASON: provider N · created N · stamped N · existing N · linked N · ..."
#                        it has no `updated`: the receipt says null (law 4), with its stamped / existing / linked
#   sync-matches         "✓ Matches (CODE): created=N updated=N skipped=N"
#   sync-matches         "skipped N listing(s) of clubs not in the DB: <ids>"         (service.skipped_listings_line)
# run_step collects every such line as it streams (never only the tail's last TAIL lines), redacted.
TEAMS_LINE = re.compile(r"^✓ Teams \((?P<code>[^)]*)\): created=(?P<created>\d+) updated=(?P<updated>\d+) "
                        r"skipped=(?P<skipped>\d+)")
FALLBACK_TEAMS_LINE = re.compile(r"^\s*teams (?P<season>\S+): provider (?P<provider>\d+) · "
                                 r"created (?P<created>\d+) · stamped (?P<stamped>\d+) · existing (?P<existing>\d+) · linked (?P<linked>\d+)")
MATCHES_LINE = re.compile(r"^✓ Matches \((?P<code>[^)]*)\): created=(?P<created>\d+) updated=(?P<updated>\d+) "
                          r"skipped=(?P<skipped>\d+)")
SKIPPED_LISTINGS_LINE = re.compile(r"^skipped (?P<n>\d+) listing\(s\) of clubs not in the DB: ?(?P<ids>.*)$")
_SYNC_LINES = (TEAMS_LINE, FALLBACK_TEAMS_LINE, MATCHES_LINE, SKIPPED_LISTINGS_LINE)


def sync_counts(lines: list[str]) -> dict:
    """The counts a sync step printed (the lines above), {} when it printed none. Keys present only when printed:
    `teams` {created, updated, skipped} (or, from the MLB fallback, {created, updated: None, stamped, existing,
    linked, via}), `matches` {created, updated, skipped}, `not_in_db` {n, ids}. The last line of each kind counts."""
    out: dict = {}
    for s in lines:
        s = s.rstrip()
        m = TEAMS_LINE.match(s)
        if m:
            out["teams"] = {k: int(m.group(k)) for k in ("created", "updated", "skipped")}
            continue
        m = FALLBACK_TEAMS_LINE.match(s)
        if m:
            out["teams"] = {"created": int(m.group("created")), "updated": None,
                            **{k: int(m.group(k)) for k in ("stamped", "existing", "linked")},
                            "via": "MLB api-sports fallback (no updated count: null)"}
            continue
        m = MATCHES_LINE.match(s)
        if m:
            out["matches"] = {k: int(m.group(k)) for k in ("created", "updated", "skipped")}
            continue
        m = SKIPPED_LISTINGS_LINE.match(s)
        if m:
            out["not_in_db"] = {"n": int(m.group("n")),
                                "ids": [x.strip() for x in m.group("ids").split(",") if x.strip()]}
    return out


def _opt(st: list[str], flag: str) -> str | None:
    i = next((i for i in range(len(st) - 1) if st[i] == flag), None)
    return None if i is None else st[i + 1]


def competition_lines(sync: list) -> list[dict]:
    """The chain's receipt line per competition (addendum 204 item 3(a)): one per competition-season a sync-teams step
    of the run RAN (whatever its exit, whether or not it printed a count), in step order, carrying sync-teams'
    created/updated and exit, and its sync-matches' step, exit and skipped count (None where the step printed no count
    -- it failed first, or the MLB fallback's own matches line has no skipped count: law 4, never a guessed 0) and the
    listings skipped for clubs not in the DB. `matches_step` None means the sync-matches step never ran (the chain
    stopped before it, or H0-16b skipped it). `sync` is run_steps' report["sync"]: [(step, argv, counts, exit)]."""
    out: dict = {}
    for i, st, counts, rc in sync:
        if st[0] not in ("sync-teams", "sync-matches"):
            continue
        key = (_opt(st, "--competition"), _opt(st, "--season"))
        if st[0] == "sync-teams":
            t = counts.get("teams") or {}
            out[key] = {"competition": key[0], "season": key[1], "teams_step": i, "teams_exit": rc,
                        "teams_created": t.get("created"), "teams_updated": t.get("updated"),
                        "matches_step": None, "matches_exit": None, "matches_skipped": None, "not_in_db": None}
        elif key in out and out[key]["matches_step"] is None:
            m, nid = counts.get("matches"), counts.get("not_in_db")
            out[key].update(matches_step=i, matches_exit=rc, matches_skipped=(m or {}).get("skipped"),
                            not_in_db=nid["n"] if nid else (0 if m else None))
    return list(out.values())


def _n(v) -> str:
    return "?" if v is None else str(v)


def competition_text(r: dict) -> str:
    """One competition's printed receipt line (the journal shows it). A step that ran and failed says `failed (exit
    N)`; a count it did not print reads `?` (law 4); `did not run` is only a sync-matches step never reached."""
    out = (f"  · {r['competition']} {r['season']}: sync-teams "
           + ("" if not r["teams_exit"] else f"failed (exit {r['teams_exit']}) ")
           + f"created {_n(r['teams_created'])} · updated {_n(r['teams_updated'])}")
    if r["matches_step"] is None:
        return out + " · sync-matches did not run"
    return out + (" · sync-matches "
                  + ("" if not r["matches_exit"] else f"failed (exit {r['matches_exit']}) ")
                  + f"skipped {_n(r['matches_skipped'])}"
                  + (" (no count printed)" if r["matches_skipped"] is None and not r["matches_exit"] else "")
                  + (f" ({r['not_in_db']} of clubs not in the DB)" if r["not_in_db"] else ""))


def run_step(argv: list[str], run_id: str, marks: list | None = None) -> tuple[int, list[str], float]:
    """`marks` (a list, opt-in; #765/#728): receives every line matching _SYNC_LINES, redacted, as it streams."""
    cmd = [sys.executable, "cli.py", *argv]
    t0 = time.monotonic()
    tail: deque = deque(maxlen=TAIL)
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "COLUMNS": "160"}
    proc = subprocess.Popen(cmd, cwd=c.REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, env=env, bufsize=1)
    for line in proc.stdout:
        sys.stdout.write(line)
        s = line.rstrip("\n")
        if s.strip():
            tail.append(c.redact(s))
        if s.startswith("SP-PAGE:"):
            page(c.redact(s), run_id)
        if marks is not None and any(r.match(s) for r in _SYNC_LINES):
            marks.append(c.redact(s))
    rc = proc.wait()
    return rc, list(tail), time.monotonic() - t0


def new_quota() -> dict:
    return {"metered_run": 0, "metered_skipped": 0, "unmetered_run": 0, "provider_calls": None,
            "provider_calls_note": "not instrumented: api-sports call counts are not surfaced "
                                   "by the CLI (null, never 0)"}


# Per-step RETRY for TRANSIENT failures only (architect ruling 2026-09-28,
# after the first live page: a UNL sync-matches died on an api-football
# ConnectionResetError). Classes: connection errors, timeouts, HTTP 5xx and
# 429. Two retries, 15s then 45s. A step that still fails pages as before
# (the chain exits non-zero; systemd OnFailure). Never retried: other 4xx and
# exceptions in our own code. The class is read from the step's TERMINAL
# exception line (the traceback's last line) when there is one, so an earlier
# log mention of a connection never masks a KeyError.
RETRY_BACKOFF_S = (15, 45)
MIRROR_TIMEOUT_S = 90      # F2.5: the exports-mirror push after each step never holds a chain longer
_sleep = time.sleep
_EXC_LINE = re.compile(r"^([A-Za-z_][\w.]*(?:Error|Exception|Timeout|Warning)\b)(?::|$)")
_TRANSIENT = re.compile(
    r"(ConnectionError|ConnectionResetError|ConnectionAbortedError|ConnectionRefusedError|"
    r"RemoteDisconnected|Connection aborted|Connection reset|BrokenPipeError|"
    r"ReadTimeout|ConnectTimeout|\bTimeout\b|TimeoutError|socket\.timeout|timed out|"
    r"\b5\d\d Server Error|\b429 Client Error|Too Many Requests)")


def transient_class(rc: int, tail: list[str]) -> str | None:
    """The transient class of a failed step, or None (never retried)."""
    if rc == 0 or rc < 0:                       # success, or killed by a signal
        return None
    terminal = [s for s in tail if _EXC_LINE.match(s.strip())]
    scope = terminal[-1:] or tail              # the terminal exception line decides
    for s in scope:
        m = _TRANSIENT.search(s)
        if m:
            return m.group(1)
    return None


SYNC_PREFIX = "sync-"      # addendum 84 item 2(b): a sync step's command starts with it; any other is card/export
# A FAILED sync-teams DOES NOT STOP THE CHAIN (ARCHITECT 2026-11-01 17:10 ET, addendum 207 item 4; #765, #728),
# verbatim: "A failed sync-teams does NOT stop the chain: the chain continues to that competition's sync-matches and to
# every later step, keeps the FIRST failure's exit code, and names the failed step in its summary line; sync-matches'
# skipped-listings line then says what the failed teams read cost (never silent). Not continue_on_sync_failure on the
# chains (wider than ruled [...])." Only the sync-teams command; every other step stops a chain as before.
TEAMS_GO_ON = "addendum 207 item 4: a failed sync-teams does not stop the chain"


def run_steps(steps, label: str, unit: str, run_id: str, today: date, quota: dict,
              continue_sync: bool = False, report: dict | None = None) -> tuple[int, int]:
    """Run steps in order (caller holds the DB lock); receipt each; stop at the
    first failure. Transient failures are retried (RETRY_BACKOFF_S) and the
    receipt says "retried N". Returns (exit, steps_ok).
    `continue_sync` (addendum 84 item 2(b)): a failed step whose command starts
    SYNC_PREFIX is receipted as now and the run goes on; a failed card/export
    step still stops it. The exit is the FIRST failed step's (non-zero when any
    step failed). `report` (a dict) receives `failed` [(step, command, exit,
    the step's last redacted output line)] and `stopped_at` (the step that
    stopped the run, or None), and `sync` [(step, argv, sync_counts, exit)] for every sync-teams/sync-matches step
    that ran (its counts {} when it printed none) and every other step that printed a sync count (#765/#728: the chain
    receipt's line per competition and its skipped listings).
    A failed `sync-teams` step (addendum 207 item 4, TEAMS_GO_ON) is receipted and the run goes on, whatever
    `continue_sync` says; it is in `failed` (so the exit is the first failure's) and never `stopped_at`."""
    ok, first_rc = 0, 0
    if report is not None:
        report.update(failed=[], stopped_at=None, sync=[])
    for i, st in enumerate(steps, 1):
        line = f"python cli.py {' '.join(st)}"
        if metered_skip(st[0], today):
            c.append_receipt({"kind": "step", "unit": unit, "run_id": run_id, "step": i,
                              "command": line, "exit": None, "skipped": "H0-16b"})
            quota["metered_skipped"] += 1
            continue
        quota["metered_run" if st[0] not in UNMETERED else "unmetered_run"] += 1
        print(f"\n=== [{label} {i}/{len(steps)}] {line}", flush=True)
        attempts, total = [], 0.0
        while True:
            marks: list = []
            rc, tail, dur = run_step(st, run_id, marks=marks)
            total += dur
            cls = transient_class(rc, tail)
            attempts.append({"exit": rc, "duration_s": round(dur, 1), "transient": cls})
            n = len(attempts) - 1
            if not cls or n >= len(RETRY_BACKOFF_S):
                break
            wait = RETRY_BACKOFF_S[n]
            print(f"↻ transient failure ({cls}) — retry {n + 1}/{len(RETRY_BACKOFF_S)} in {wait}s",
                  flush=True)
            _sleep(wait)
        rec = {"kind": "step", "unit": unit, "run_id": run_id, "step": i,
               "command": line, "exit": rc, "duration_s": round(total, 1),
               "git_sha": c.git_sha(), "tail": tail}
        if len(attempts) > 1:
            rec.update(retried=len(attempts) - 1, attempts=attempts)
            print(f"· retried {len(attempts) - 1}: {'ok' if rc == 0 else f'still failing (exit {rc})'}",
                  flush=True)
        sync_goes_on = continue_sync and st[0].startswith(SYNC_PREFIX)
        teams_goes_on = st[0] == "sync-teams"         # addendum 207 item 4: whatever continue_sync says
        if rc != 0 and sync_goes_on:
            rec["continued"] = "addendum 84 item 2(b): a sync step's failure does not stop the window chain"
        elif rc != 0 and teams_goes_on:
            rec["continued"] = TEAMS_GO_ON
        counts = sync_counts(marks)
        if counts or st[0] in ("sync-teams", "sync-matches"):
            if counts:
                rec["sync"] = counts
            if report is not None:
                report["sync"].append((i, list(st), counts, rc))
            nid = (counts.get("not_in_db") or {}).get("n", 0)
            if nid:
                print(f"⚠ step {i}/{len(steps)} skipped {nid} listing(s) of clubs not in the DB (exit stays "
                      f"{rc}: skipped, not faked)", flush=True)
        c.append_receipt(rec)
        mirror_after_step(unit, i, st[0], run_id)
        if rc != 0:
            if report is not None:
                report["failed"].append((i, line, rc, next((x for x in reversed(tail) if x.strip()), "")))
            first_rc = first_rc or rc
            if sync_goes_on:
                print(f"· sync step {i}/{len(steps)} failed (exit {rc}): {line} — recorded; the chain runs on "
                      "(addendum 84 item 2(b))", flush=True)
                continue
            if teams_goes_on:
                print(f"· sync-teams step {i}/{len(steps)} failed (exit {rc}): {line} — recorded; the chain runs on "
                      "to its sync-matches and every later step (addendum 207 item 4)", flush=True)
                continue
            if report is not None:
                report["stopped_at"] = i
            return first_rc, ok
        ok += 1
    return first_rc, ok


def mirror_after_step(unit: str, i: int, cmd: str, run_id: str) -> None:
    """EXPORTS MIRROR (F2.5, ARCHITECT 2026-10-03): push exports/ to the
    private exports repo after every chain step. NON-FATAL and time-bounded
    (MIRROR_TIMEOUT_S): a mirror failure is receipted, never fails or hangs the
    chain. Off until SP_EXPORTS_MIRROR_REMOTE is set."""
    if not c.setting("SP_EXPORTS_MIRROR_REMOTE"):
        return
    argv = [sys.executable, str(Path(__file__).resolve().parent / "exports_mirror.py"), "push",
            "--role", c.setting("SP_EXPORTS_MIRROR_ROLE") or "host",
            "--label", f"{unit} step {i} {cmd} ({run_id})"]
    rec = {"kind": "mirror", "unit": unit, "run_id": run_id, "step": i}
    try:
        r = subprocess.run(argv, cwd=c.REPO, capture_output=True, text=True, timeout=MIRROR_TIMEOUT_S)
        rec.update(exit=r.returncode,
                   tail=[c.redact(x) for x in ((r.stdout or "") + (r.stderr or "")).strip().splitlines()[-3:]])
    except subprocess.TimeoutExpired:
        rec.update(exit=None, tail=[f"timed out after {MIRROR_TIMEOUT_S}s"])
    except OSError as e:
        rec.update(exit=None, tail=[f"{e.__class__.__name__}: {e}"])
    c.append_receipt(rec)
    print(f"· exports mirror: {'ok' if rec.get('exit') == 0 else 'NOT pushed (receipted; chain continues)'}",
          flush=True)


def run_vars(name: str, run_id: str, today: date) -> dict:
    """#673 (ARCHITECT 2026-10-25, addendum 167 postscript (b): "The freshen writes to its own name"): a chain with a
    `freshen_out` name gets {freshen_out} = logs/<run id>.<that name>, the run id's ':' written '-'. Outside exports/:
    never the slate's file, never mirrored. Every other chain: nothing."""
    name_ = CHAINS[name].get("freshen_out")
    if not name_:
        return {}
    return {"freshen_out": f"logs/{run_id.replace(':', '-')}.{name_.format(**date_vars(today))}"}


def freshen_out_taken(rv: dict) -> str | None:
    """#442's rule for the freshen's own file: "Nothing a run kept is opened for writing a second time"."""
    out_ = rv.get("freshen_out")
    if out_ and ((c.REPO / out_).exists() or (c.REPO / out_).is_symlink()):
        return f"the freshen's export path {out_} already exists: nothing a run kept is opened for writing a second time"
    return None


def freshen_wrote(rv: dict) -> dict | None:
    """The receipt line naming what the freshen wrote (#673): its own file and sha256 (None: not written)."""
    out_ = rv.get("freshen_out")
    if not out_:
        return None
    p = c.REPO / out_
    return {"file": out_, "sha256": c.sha256_file(p) if p.is_file() else None}


def freshen_state_path():
    return c.receipts_path().with_name("freshen_state.json")


def run_freshens(needed: list, window_run_id: str, now, today: date) -> list[dict]:
    """freshen:<family> for the families with freshen_needed inside T-90
    (architect ruling 2026-09-27): under the chain lock, receipted, at most one
    per family per FRESHEN_MIN_INTERVAL_S. Families in SP_SKIP_FAMILIES are
    logged and never run (MLB on the DO host). Market-only rows map to no family."""
    import json as _json
    skip = {s.strip().upper() for s in (c.setting("SP_SKIP_FAMILIES") or "").split(",") if s.strip()}
    fams: dict[str, list] = {}
    why: dict[str, set] = {}
    for d in needed:
        fam = FRESHEN_FAMILY.get((str(d.get("sport")).lower(), str(d.get("competition"))))
        if fam:
            fams.setdefault(fam, []).append(d.get("id"))
            why.setdefault(fam, set()).add(d.get("reason") or "t90_news")
    sp = freshen_state_path()
    try:
        state = _json.loads(sp.read_text())
    except (OSError, ValueError):
        state = {}
    out = []
    for fam, ids in sorted(fams.items()):
        name = f"freshen:{fam}"
        base = {"kind": "freshen", "chain": name, "family": fam, "games": ids,
                "reasons": sorted(why[fam]), "triggered_by": window_run_id}
        if fam in skip:
            out.append(c.append_receipt({**base, "exit": 0, "ran": False,
                                         "skipped": "family skipped on this host (SP_SKIP_FAMILIES)"}))
            continue
        last = state.get(fam)
        if last and (now - datetime.fromisoformat(last)).total_seconds() < FRESHEN_MIN_INTERVAL_S:
            out.append(c.append_receipt({**base, "exit": 0, "ran": False,
                                         "skipped": f"rate-guard: last {name} at {last}"}))
            continue
        quota = new_quota()
        run_id = f"{now.strftime('%Y%m%dT%H%M%SZ')}-{name}"
        rv = run_vars(name, run_id, today)
        steps = resolve(name, rv, today)
        with c.db_lock():                     # checked under the lock its export runs under (Codex on #692)
            taken = freshen_out_taken(rv)
            if not taken:
                rc, ok = run_steps(steps, name, f"sp-chain@{name}.service", run_id, today, quota)
        if taken:
            print(f"✗ {name}: {taken}", flush=True)
            out.append(c.append_receipt({**base, "exit": 1, "ran": False, "run_id": run_id, "refused": taken}))
            continue
        state[fam] = now.isoformat()
        rec = {**base, "exit": rc, "ran": True, "run_id": run_id,
               "steps_ok": ok, "steps_total": len(steps), "quota": quota}
        wrote = freshen_wrote(rv)
        if wrote is not None:
            rec["wrote"] = wrote
            print(f"· {name} wrote {wrote['file']}" + (f" (sha256 {wrote['sha256'][:12]})" if wrote["sha256"]
                                                     else " — not written"), flush=True)
        out.append(c.append_receipt(rec))
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(_json.dumps(state))
    return out


def active_from(name: str) -> dict | None:
    """A season-gated chain's effective start date and where it came from:
    the chain's `active_from_env` variable (host.env) if set, else the ruled
    default in chains.py. A malformed override fails loudly, never skips."""
    ch = CHAINS[name]
    if not ch.get("active_from"):
        return None
    var = ch.get("active_from_env")
    val = (c.setting(var) or "").strip() if var else ""
    if val:
        try:
            date.fromisoformat(val)
        except ValueError:
            raise SystemExit(f"{var}={val!r} is not a YYYY-MM-DD date — fix host.env "
                             f"(ruled default for {name}: {ch['active_from']})")
        return {"date": val, "source": var}
    return {"date": ch["active_from"], "source": "chains.py default"
            + (f" (override: {var})" if var else "")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run a sports-predictor chain with receipts.")
    ap.add_argument("chain", choices=sorted(CHAINS))
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help="override a date placeholder (e.g. sat=2026-09-29)")
    ap.add_argument("--dry-run", action="store_true", help="print resolved steps; run nothing")
    ap.add_argument("--operator", action="store_true",
                    help="required for operator-only chains (soccer-refresh, H0-6)")
    ap.add_argument("--unit", default=None, help="unit name for the receipt")
    a = ap.parse_args(argv)
    c.load_host_env()
    import sp_notify
    bad = sp_notify.topic_problems()     # startup validation: fail loudly, never page the wrong topic
    if bad:
        for p in bad:
            print(f"✗ {p}", flush=True)
        c.append_receipt({"kind": "config_error", "chain": a.chain, "exit": 2, "problems": bad})
        return 2

    chain = CHAINS[a.chain]
    now = c.utc_now()
    today = now.date()
    unit = a.unit or f"sp-chain@{a.chain}.service"
    run_id = f"{now.strftime('%Y%m%dT%H%M%SZ')}-{a.chain}"
    rv = run_vars(a.chain, run_id, today)           # #673: a freshen's own file, never a --set (Codex on #692)
    overrides = {**dict(kv.split("=", 1) for kv in a.set), **rv}
    # The closing chains (deploy/hosting/closing.py) take run-time placeholders only a closing run computes, so they
    # are refused BEFORE resolving: a dry run prints the command to use and touches nothing.
    closing_cmd = chain.get("laptop_only") or chain.get("closing_command")
    if closing_cmd and a.dry_run:
        print(f"✗ {a.chain} is not an sp_run chain: dry-run it with `{closing_cmd} --dry-run`.")
        return 2
    if chain.get("laptop_only"):
        print(f"✗ {a.chain} is not an sp_run chain: run it with `{chain['laptop_only']}` (laptop only).")
        c.append_receipt({"kind": "chain", "unit": unit, "run_id": run_id, "exit": 2,
                          "refused": "laptop_only"})
        return 2
    if chain.get("closing_command"):
        print(f"✗ {a.chain} is not an sp_run chain: run it with `{chain['closing_command']}`.")
        c.append_receipt({"kind": "chain", "unit": unit, "run_id": run_id, "exit": 2,
                          "refused": "closing_only"})
        return 2
    steps = resolve(a.chain, overrides, today, now=now.replace(tzinfo=None))

    gate = active_from(a.chain)
    if gate:
        print(f"· {a.chain} active from {gate['date']} [{gate['source']}]")

    if a.dry_run:
        for i, st in enumerate(steps, 1):
            tag = " [skip: H0-16b]" if metered_skip(st[0], today) else ""
            print(f"{i}. python cli.py {' '.join(st)}{tag}")
        print(f"backup: {chain.get('backup') or 'none'}")
        return 0

    if chain.get("operator_only") and not a.operator:
        print(f"✗ {a.chain} is OPERATOR-STARTED only (H0-6): re-run with --operator.")
        c.append_receipt({"kind": "chain", "unit": unit, "run_id": run_id, "exit": 2,
                          "refused": "operator_only"})
        return 2
    if gate and today.isoformat() < gate["date"]:
        print(f"· {a.chain} inactive until {gate['date']} — skipped.")
        c.append_receipt({"kind": "chain", "unit": unit, "run_id": run_id, "exit": 0,
                          "skipped": f"inactive_until_{gate['date']}", "active_from": gate})
        return 0

    import sp_backup
    t0 = time.monotonic()
    exports_before = {p: p.stat().st_mtime for p in (c.REPO / "exports").glob("*")} \
        if (c.REPO / "exports").exists() else {}
    backup_rec, chain_exit, ok = None, 0, 0
    step_report: dict = {"failed": [], "stopped_at": None, "sync": []}
    quota = new_quota()
    with c.db_lock():
        taken = freshen_out_taken(overrides)    # under the lock the export runs under (Codex on #692)
        if taken:
            print(f"✗ {a.chain}: {taken}")
            c.append_receipt({"kind": "chain", "unit": unit, "run_id": run_id, "exit": 2, "refused": taken})
            return 2
        need = chain.get("backup")
        if need == "prerefresh" or (need == "daily" and sp_backup.todays_daily() is None):
            backup_rec = sp_backup.run_backup(need, lock=False)
            if backup_rec["exit"] != 0:
                chain_exit = 1
        elif need == "daily":
            p = sp_backup.todays_daily()
            backup_rec = {"file": p.name, "sha256": c.sha256_file(p), "integrity": "verified-sidecar"}

        if chain_exit == 0:
            chain_exit, ok = run_steps(steps, a.chain, unit, run_id, today, quota,
                                       continue_sync=bool(chain.get("continue_on_sync_failure")), report=step_report)

    exports = sorted(str(p.relative_to(c.REPO)) for p in (c.REPO / "exports").glob("*")
                     if exports_before.get(p) != p.stat().st_mtime) \
        if (c.REPO / "exports").exists() else []
    page_rec, freshens = None, []
    # addendum 84 item 2(b): the post runs after a clean run, or when only sync steps failed and the card ran
    sync_only = (chain_exit != 0 and bool(step_report["failed"]) and step_report["stopped_at"] is None
                 and (backup_rec is None or backup_rec.get("exit", 0) == 0))
    if (chain_exit == 0 or sync_only) and chain.get("post") == "window_page":
        import sp_window_page
        page_rec = sp_window_page.run(c.REPO / "exports" / "window_24h.json")
        if page_rec.get("freshen_needed"):
            freshens = run_freshens(page_rec["freshen_needed"], run_id,
                                    now.replace(tzinfo=None), today)
            if any(f.get("ran") and f.get("exit") == 0 for f in freshens):
                with c.db_lock():  # the card picks up the freshened predictions now
                    run_steps([["window-card", "--hours", str(WINDOW_HOURS)]], a.chain, unit,
                              run_id + "-recard", today, quota)
    rec = {"kind": "chain", "unit": unit, "run_id": run_id, "exit": chain_exit,
           "steps_ok": ok, "steps_total": len(steps), "quota": quota,
           "duration_s": round(time.monotonic() - t0, 1),
           "counts": c.table_counts(c.db_path(), c.CHAIN_COUNT_TABLES), "exports": exports}
    if gate:
        rec["active_from"] = gate
    wrote = freshen_wrote(overrides)
    if wrote is not None:
        rec["wrote"] = wrote
    if step_report["failed"]:
        rec["failed_steps"] = [{"step": i, "command": cmd, "exit": rc} for i, cmd, rc, _ in step_report["failed"]]
        rec["stopped_at"] = step_report["stopped_at"]
    if backup_rec is not None:
        rec["backup"] = {k: backup_rec.get(k) for k in ("file", "sha256", "integrity")}
    # #765/#728 (addendum 204 item 3(a), (c)): the line per competition a sync-teams step named, and every step that
    # skipped listings of clubs not in the DB (exit unchanged: skipped, not faked; never silent)
    comps = competition_lines(step_report["sync"])
    if comps:
        rec["competitions"] = comps
    skipped = [(i, st, counts["not_in_db"]) for i, st, counts, _rc in step_report["sync"]
               if (counts.get("not_in_db") or {}).get("n")]
    if skipped:
        rec["listings_skipped"] = [{"step": i, "command": f"python cli.py {' '.join(st)}", "n": nid["n"],
                                    "ids": nid["ids"]} for i, st, nid in skipped]
    if page_rec is not None:
        rec["page"] = {k: page_rec.get(k) for k in ("deltas", "paged", "digest", "suppressed")}
        rec["freshens"] = [{k: f.get(k) for k in ("chain", "ran", "exit", "skipped")}
                           for f in freshens]
    if chain.get("window_plan") and _LAST_WINDOW_PLAN:
        rec["proximity"] = {"tiers": _LAST_WINDOW_PLAN["tiers"],
                            "steps_skipped_by_proximity": _LAST_WINDOW_PLAN["skipped_by_proximity"]}
        tz = _LAST_WINDOW_PLAN["tiers"]
        print(f"  proximity: imminent(<{PROX_IMMINENT_H}h) {tz['imminent']} · near "
              f"({PROX_IMMINENT_H}-{PROX_FAR_H}h) {tz['near']} · far(>{PROX_FAR_H}h, schedule only) "
              f"{tz['far']} · steps skipped by proximity {_LAST_WINDOW_PLAN['skipped_by_proximity']}")
    c.append_receipt(rec)
    for r in comps:
        print(competition_text(r))
    print(f"  quota: metered steps run {quota['metered_run']} · skipped {quota['metered_skipped']} "
          f"· unmetered run {quota['unmetered_run']} · provider calls: not instrumented")
    skipped_text = ("" if not skipped else " · listings skipped (clubs not in the DB): " + ", ".join(
        f"step {i}/{len(steps)} {_opt(st, '--competition') or st[0]} {nid['n']}" for i, st, nid in skipped))
    # addendum 207 item 4: the summary line names each failed sync-teams step the chain ran on past BECAUSE of it; on
    # a continue_on_sync_failure chain addendum 84 item 2(b) carried the step (its receipt's `continued` says so), so
    # the summary never credits that step to item 4
    teams_failed = [(i, steps[i - 1], rc) for i, _cmd, rc, _ in step_report["failed"]
                    if steps[i - 1][0] == "sync-teams" and not chain.get("continue_on_sync_failure")]
    teams_text = ("" if not teams_failed else " · sync-teams failed (the chain ran on, addendum 207 item 4): "
                  + ", ".join(f"step {i}/{len(steps)} {_opt(st, '--competition') or st[0]} exit {rc}"
                              for i, st, rc in teams_failed))
    print(f"\n{'✓' if chain_exit == 0 else '✗'} {a.chain}: exit={chain_exit} "
          f"steps {ok}/{len(steps)} in {rec['duration_s']}s{teams_text}{skipped_text} · running "
          f"{c.running_release() or 'release ?'} · writer of record {c.writer_of_record() or '?'}")
    # addendum 204 item 3(c): each step that skipped listings, with its command and ids (law 4: exit unchanged)
    for i, st, nid in skipped:
        print(f"  ⚠ step {i}/{len(steps)} python cli.py {' '.join(st)}: "
              f"skipped {nid['n']} listing(s) of clubs not in the DB: {', '.join(nid['ids'])}"[:600])
    # The failure page (sp_notify) carries the journal's last 30 lines; a run that went on past a failed sync step
    # has pushed that step's output out of them, so the failures are named here, at the very end.
    for i, cmd, rc, last in step_report["failed"]:
        print(f"  ✗ step {i}/{len(steps)} exit={rc}: {cmd}" + (f" — {last.strip()[:200]}" if last.strip() else ""))
    if step_report["stopped_at"] is not None:
        print(f"  ✗ stopped at step {step_report['stopped_at']}/{len(steps)}")
    return chain_exit


if __name__ == "__main__":
    sys.exit(main())
