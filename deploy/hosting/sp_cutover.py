#!/usr/bin/env python3
"""H2 cutover, HOST side: the ruled morning sequence as receipted steps
(docs/specs/h2-cutover-runbook.md; hosting-h1.md "H2"). Cutover itself is an
ARCHITECT RULING on the frozen parallel-week criteria (H0-18) — nothing here
decides or triggers it; this only executes the sequence once ruled.

    sp_cutover.py <step> --pack <dir> [--timers-file F] [--lock-timeout S]
    sp_cutover.py run    --pack <dir> --dry-run --scratch <DIR>
    sp_cutover.py shot-gate [--pack <dir>]   (internal: the preflight's read of the NHL shot GATE; --pack reads the
                                              pack's DB, without it the host's live DB)

Steps (in order; `run` = all six, the first failure stops):
  preflight  pack present; sp_migrate verify PASS (sha256 + integrity + every
             table count); the pack's DATABASE_URL relative; timers list
             readable; every sp timer active on the host is on the list (addendum
             57 item 8: one off the list refuses, named; the list is never
             written here); host.env present, writable, at most one
             SP_WRITER_OF_RECORD line with a known value; host.env itself says
             SP_EXPORTS_MIRROR_ROLE=host (addendum 47 item 7(c)); no target under data/.
             Addendum 79 item 4: every listed timer is active (one that is not refuses,
             named). Addendum 80 item 3: the preflight runs BEFORE runbook step 2 stops the
             timers. Past the pack, data/ and timer-list reads, when every listed timer is
             inactive and no sp timer off the list is active, it stops: it prints "timers
             already stopped: run the preflight before step 2" and its receipt (exit 1,
             `stopped`, never `refused`; no ✗, REFUSED or FAIL line), runs no further check
             (no shot read, no verify), and `run` goes no further. An active sp timer off the
             list still refuses, named (addendum 57 item 8). The NHL shot GATE (nhl-shot-coverage's own numbers,
             read by `shot-gate` as the service user) reads the PACK's DB, the laptop's that
             install puts in place, and refuses below 95% in any season it names (named with
             its share); the host's live DB is read and printed for the record and never
             refuses. Below 95% on the host, the backfill's exact host command is printed,
             --dry-run first, never run here, "optional before cutover; not a prerequisite".
             The dry run reads neither. Past the pack, data/ and timer-list reads, each check
             prints its line and one refusal names every failure; sp_migrate verify runs only
             when they all pass.
             Prints, by name only, each setting the pack's .env changes on the host
             (those host.env gives a value left out); the list refuses nothing by itself.
             Everything that could fail install is refused HERE, before pause.
  pause      systemctl stop <timers.enabled>; every timer must read inactive.
             Running sp-chain@ services are listed (install waits on the DB lock).
  install    sp_migrate install --replace (verify again, place, re-verify),
             under the DB lock; S2 = S1 and R2 = R1 for every table, or refuse.
             Addendum 168 item 3: then removes from the checkout's .env each ruled
             setting (PACK_ONLY_SCRUB) that came only from the pack (the preflight's
             comparison, read before the .env is replaced) and that host.env gives no
             value; line-preserving; the .env before it kept where git cannot see
             it, beside host.env as checkout.env.pre-scrub-<ts> (created 0600, then
             root:sp 0640); prints and receipts the names, never a value. Other
             names are never removed.
  flip       SP_WRITER_OF_RECORD=host in host.env (ARCHITECT-RULE 2026-10-01:
             the REAL writer-of-record flag, laptop|host; SP_PARALLEL_MODE
             stays the H0-16 quota mode and is never touched). Line-preserving;
             the old file is kept beside it as host.env.pre-cutover-<ts>.
  resume     systemctl start <timers>; every timer active; then
             systemctl start sp-backup.service and its backup receipt must
             read integrity=ok.
  receipt    boot-receipt-style summary: running release, db sha (S2 = S1),
             R2 = R1, flag value, timers, first backup — from this cutover's
             own receipts (cutover id = the pack dir name).

Every step appends a receipt {kind: cutover, step, exit, cutover_id} and a
failing step refuses (exit 1, receipt carries `refused`); a preflight run after
runbook step 2 stops instead (exit 1, receipt carries `stopped`, addendum 80
item 3). After `pause` a refusal leaves the timers STOPPED by design (runbook:
Rollback).

Privileges: run as root (`sudo venv/bin/python ...`) — systemctl and the
root:sp host.env need it. As root, every step that opens the DB or the pack
(preflight's verify, install) re-runs as the service user (`runuser -u sp`,
SP_SERVICE_USER) so data/sports.db, .env and exports/ stay sp-owned.

--dry-run --scratch DIR (with `run` only): the WHOLE sequence against a scratch
world under DIR — scratch checkout (with a rehearsal DB), host.env seeded from
etc/host.env.example, timers.enabled seeded from the runbook's T11 list,
receipts, lock, backups — and a systemctl stand-in that records calls and
never runs one. Refuses a DIR under the checkout's data/ or a non-empty DIR,
and refuses unless every resolved path lies under DIR. The real DB, host.env,
receipts and systemd are never touched. Prints each receipt, then PASS/FAIL.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sp_common as c  # noqa: E402
import sp_migrate  # noqa: E402

STEPS = ("preflight", "pause", "install", "flip", "resume", "receipt")
ROLE_SETTING = "SP_EXPORTS_MIRROR_ROLE"     # addendum 47 item 7(c): host.env itself must say host
TIMERS_ENABLED = Path("/etc/sports-predictor/timers.enabled")   # hosting-h1.md T11
TIMER_NAME = re.compile(r"^sp-[a-z0-9-]+\.timer$")
BACKUP_UNIT = "sp-backup.service"
SHOT_GATE_TAG = "SHOT-GATE "             # addendum 79 item 4: the one line `sp_cutover.py shot-gate` prints
# ARCHITECT 2026-10-15, addendum 80 item 3, verbatim: (Q1) "sp_cutover prints "timers already stopped: run the
# preflight before step 2" when every listed timer is inactive"; (Q3) the backfill print "labelled "optional before
# cutover; not a prerequisite"".
TIMERS_STOPPED = "timers already stopped: run the preflight before step 2"
BACKFILL_OPTIONAL = "optional before cutover; not a prerequisite"
PACK_WHOSE, HOST_WHOSE = "the pack's", "the host's live"       # whose NHL shot GATE streams a line reads
# The writer-of-record setting H2 step 6 names: the existing H0-16 variable
# (grep: sp_run.metered_skip, etc/host.env.example). Values: full | designated.
FLAG, FLAG_VALUE, FLAG_KNOWN = "SP_WRITER_OF_RECORD", "host", ("laptop", "host")
FLAG_LINE = re.compile(r"^(\s*(?:export\s+)?)" + FLAG + r"\s*=(.*?)(\r?\n)?$")
# ARCHITECT 2026-10-26, addendum 168 item 3 (#677), verbatim: "the env_changes list stays names-only, but `install`
# (or the runbook's step right after it) REMOVES pack-only settings that host.env does not define and that name a path
# or a key (a list in sp_cutover, ruled: SP_EXPORTS_MIRROR_KEY, CFBD_API_KEY, SP_HOST_ADDR today), printing their
# names". A name not on this list is never removed: it stays on env_changes, names only, as before.
PACK_ONLY_SCRUB = ("SP_EXPORTS_MIRROR_KEY", "CFBD_API_KEY", "SP_HOST_ADDR")

Runner = Callable[[list], "tuple[int, str]"]


class Refused(Exception):
    pass


class Stopped(Refused):
    """Addendum 80 item 3 (Q1): a run that is not the step (the preflight after runbook step 2). It stops like a
    refusal (exit 1, nothing after it runs); its line and its receipt are already printed, and drive() adds no ✗,
    REFUSED or FAIL line."""


def _euid() -> int:  # tests pin it
    return os.geteuid()


def system_runner(argv: list) -> tuple[int, str]:
    """The real runner: one subprocess, output captured. Never a shell."""
    try:
        r = subprocess.run([str(a) for a in argv], capture_output=True, text=True, timeout=3 * 3600)
    except (OSError, subprocess.SubprocessError) as e:
        return 127, f"{type(e).__name__}: {e}"
    return r.returncode, (r.stdout or "") + (r.stderr or "")


class DryRunner:
    """systemctl stand-in for --dry-run: records every call, runs nothing.
    `start sp-backup.service` is simulated with sp_backup.run_backup against
    the scratch DB (same code the unit runs). Anything not systemctl is refused."""

    def __init__(self, active=()):
        self.calls: list[list[str]] = []
        self.active = set(active)

    def __call__(self, argv):
        argv = [str(a) for a in argv]
        self.calls.append(argv)
        if argv[:1] != ["systemctl"] or len(argv) < 2:
            return 1, f"dry-run: refused non-systemctl call {argv[:1]}"
        verb, units = argv[1], argv[2:]
        if verb == "stop":
            self.active -= set(units)
            return 0, ""
        if verb == "start":
            for u in units:
                if u == BACKUP_UNIT:
                    import sp_backup
                    rec = sp_backup.run_backup("daily")
                    if rec["exit"] != 0:
                        return 1, f"backup failed: {rec.get('error')}"
                else:
                    self.active.add(u)
            return 0, ""
        if verb == "is-active":
            states = ["active" if u in self.active else "inactive" for u in units]
            return (0 if all(s == "active" for s in states) else 3), "\n".join(states)
        if verb == "list-units":
            if "--type=timer" in argv:          # the scratch list's timers, all active (addendum 57 item 8)
                return 0, "\n".join(f"{u} loaded active waiting" for u in sorted(self.active)
                                    if u.startswith("sp-") and u.endswith(".timer"))
            return 0, ""
        return 1, f"dry-run: unknown systemctl verb {verb}"


@dataclass
class Ctx:
    pack: Path | None
    timers_file: Path
    runner: Runner
    dry_run: bool = False
    scratch: Path | None = None
    release: str | None = None
    lock_timeout: float = 3600.0
    service_user: str = "sp"
    cutover_id: str = ""
    done: dict = field(default_factory=dict)
    shot_read: Callable | None = None      # tests inject a fake read (ctx, pack: bool) -> dict (None: run_shot_read)
    env_kept_copy: Path | None = None      # the `sp` install: the copy root kept before it (step_install)


# ------------------------------------------------------------ plumbing ----

def _as_service_user(ctx: Ctx) -> bool:
    """Real run as root: DB/pack work re-runs as the service user."""
    return not ctx.dry_run and _euid() == 0


def _receipt(ctx: Ctx, step: str, exit_: int, **kw) -> dict:
    rec = {"kind": "cutover", "step": step, "exit": exit_, "cutover_id": ctx.cutover_id,
           "dry_run": ctx.dry_run, **kw}
    if ctx.dry_run:  # the scratch checkout is not a git tree: name the code under test
        rec["release"] = ctx.release
    p = c.receipts_path()
    existed = p.exists()
    line = c.append_receipt(rec)
    if not existed and _as_service_user(ctx):  # never leave a root-owned log for sp
        try:
            import pwd
            pw = pwd.getpwnam(ctx.service_user)
            os.chown(p, pw.pw_uid, pw.pw_gid)
        except (KeyError, OSError):
            pass
    print(f"  receipt {json.dumps(line, ensure_ascii=False)}")
    return line


def _refuse(ctx: Ctx, step: str, reason: str, **kw):
    _receipt(ctx, step, 1, refused=reason, **kw)
    raise Refused(f"✗ REFUSED {step}: {reason}")


def _no_data(ctx: Ctx, step: str, paths) -> None:
    """Law 5: nothing this script writes or reads as a target sits under data/
    (the DB install is sp_migrate's, and only sp_migrate places it)."""
    for p in paths:
        if p is None:
            continue
        try:
            c.refuse_under_data(Path(p))
        except SystemExit as e:
            _refuse(ctx, step, str(e).lstrip("✗ ").strip())


def _manifest(ctx: Ctx) -> dict:
    return json.loads((ctx.pack / sp_migrate.MANIFEST).read_text())


def read_timers(ctx: Ctx, step: str) -> list[str]:
    try:
        names = ctx.timers_file.read_text().split()
    except OSError as e:
        _refuse(ctx, step, f"timers list unreadable: {ctx.timers_file} ({type(e).__name__})")
    bad = [n for n in names if not TIMER_NAME.match(n)]
    if bad:
        _refuse(ctx, step, f"timers list has non-timer names {bad[:5]} ({ctx.timers_file})")
    if not names:
        _refuse(ctx, step, f"timers list empty: {ctx.timers_file}")
    return list(dict.fromkeys(names))


def _flag_lines(text: str) -> list[tuple[int, re.Match]]:
    return [(i, m) for i, line in enumerate(text.splitlines(keepends=True))
            if (m := FLAG_LINE.match(line))]


def _flag_value(m: re.Match | None) -> str | None:
    if m is None:
        return None
    v = m.group(2).strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    return v


def _cutover_receipts(ctx: Ctx) -> list[dict]:
    p = c.receipts_path()
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("kind") == "cutover" and r.get("cutover_id") == ctx.cutover_id:
            out.append(r)
    return out


def _last_ok(ctx: Ctx, step: str) -> tuple[int, dict] | None:
    rs = _cutover_receipts(ctx)
    for i in range(len(rs) - 1, -1, -1):
        if rs[i].get("step") == step:
            return (i, rs[i]) if rs[i].get("exit") == 0 else None
    return None


# --------------------------------------------------------------- steps ----

def active_sp_timers(ctx: Ctx, step: str) -> list[str]:
    """The sp timers active on the host now, as systemd lists them (addendum 57 item 8), whatever their names: one
    the list's name pattern cannot carry (sp-x@y.timer, an underscore) is still an active sp timer and is kept, never
    dropped. A listing that cannot be read refuses: an unread listing is never read as empty."""
    rc, out = ctx.runner(list(c.ACTIVE_SP_TIMERS_ARGV))
    if rc != 0:
        _refuse(ctx, step, f"cannot read the active sp timers: systemctl list-units exit {rc}: "
                           f"{c.redact(out.strip())[:200]}")
    return c.parse_active_sp_timers(out)


def _shot_argv(ctx: Ctx, pack: bool) -> list:
    argv = [sys.executable, str(HERE / "sp_cutover.py"), "shot-gate", *(["--pack", str(ctx.pack)] if pack else [])]
    return ["runuser", "-u", ctx.service_user, "--", *argv] if _as_service_user(ctx) else argv


def run_shot_read(ctx: Ctx, pack: bool) -> dict:
    """An NHL shot GATE read (addendum 79 item 4; addendum 80 item 3: pack=True the PACK's DB, which gates; False the
    host's live DB, for the record): `sp_cutover.py shot-gate` in a process of its own (as the service user when run
    as root, as install is), whose one SHOT-GATE line is returned as read. Anything else is {"error": ...}: an unread
    gate is never read as a pass (law 4)."""
    rc, out = ctx.runner(_shot_argv(ctx, pack))
    line = next((ln for ln in reversed(out.splitlines()) if ln.startswith(SHOT_GATE_TAG)), None)
    if line is None:
        return {"error": f"the read printed no {SHOT_GATE_TAG.strip()} line (exit {rc}): "
                         f"{c.redact(out.strip())[-200:]}"}
    try:
        d = json.loads(line[len(SHOT_GATE_TAG):])
    except ValueError as e:
        return {"error": f"its {SHOT_GATE_TAG.strip()} line is not JSON ({e})"}
    if not isinstance(d, dict):
        return {"error": f"its {SHOT_GATE_TAG.strip()} line is not an object"}
    if rc != 0 and "error" not in d:
        return {"error": f"the read exit {rc}"}
    return d


def shot_gate_read(pack: Path | None = None) -> int:
    """`sp_cutover.py shot-gate [--pack <dir>]` (internal, never a step): one DB's NHL shot GATE streams as ONE line
    `SHOT-GATE {json}`, read-only. With --pack, the pack's DB (<dir>/sports.db, the laptop's that install puts in
    place; addendum 80 item 3), opened as sp_migrate opens the pack's copy (sp_common.copy_connect: mode=ro and
    immutable, nothing created beside it, addendum 73 item 4); without it, the host's live DB (DATABASE_URL), mode=ro
    (sp_common.ro_connect; never immutable on the live DB, #340). The counts are nhl_shots.coverage()["gate_stream"]
    (nhl-shot-coverage's own numbers, never re-derived); per season, the first and last UTC date of nhl_backtest's own
    stream (the backfill's span). The app's sessions read through that connection of their own (no WAL pragma, no
    mkdir, nothing written); a missing file is refused (never created) and init_db is never called."""
    def out(d: dict) -> None:
        print(SHOT_GATE_TAG + json.dumps(d, sort_keys=True))
    p = pack / sp_migrate.DB if pack is not None else c.db_path()
    if not p.is_file():
        out({"error": f"no database at {p} (never created here)"})
        return 1
    os.environ["DATABASE_URL"] = f"sqlite:///{p}"
    sys.path.insert(0, str(c.REPO))
    try:
        from sqlalchemy import create_engine

        import src.db.database as dbm
        from src.ingestion import nhl_shots as nsh
        from src.walters import nhl_backtest as nb
        # READ-ONLY for real: the app's sessions are rebound to an engine of their own on sp_common's own read-only
        # open (the pack's copy: copy_connect; the live DB: ro_connect, never immutable, #340), so the app engine's
        # connect hooks (PRAGMA journal_mode=WAL, the data/ mkdir) never run and nothing is written.
        connect = c.copy_connect if pack is not None else c.ro_connect
        dbm.SessionLocal.configure(bind=create_engine("sqlite://", creator=lambda: connect(p)))
        gate = nsh.coverage()["gate_stream"]
        st = nb.build_stream(nb.load_games())
        seasons = {}
        for season, games in ((nb.TRAIN_SEASON, st.train), (nb.TEST_SEASON, st.test)):
            b = gate.get(season) or {"games": 0, "with_shots": 0}
            days = sorted(g.utc_date.date() for g in games)
            seasons[season] = {"games": b["games"], "with_shots": b["with_shots"],
                               "first": days[0].isoformat() if days else None,
                               "last": days[-1].isoformat() if days else None}
    except Exception as e:  # noqa: BLE001 - printed as unread; the preflight refuses on it (law 4)
        out({"error": f"{type(e).__name__}: {c.redact(str(e))[:200]}"})
        return 1
    out({"db": str(p), "source": "pack" if pack is not None else "live", "bar": nsh.FEEDABLE["games_with_events"],
         "seasons": seasons})
    return 0


def shot_gate_lines(read: dict, whose: str = PACK_WHOSE) -> tuple[list[str], list[str]]:
    """(printed lines, failures) for a shot read: one line per GATE-stream season with nhl-shot-coverage's own PASS
    rule (games read and the share at or above the bar); a season below it is a failure named with its share.
    whose=PACK_WHOSE gates (addendum 80 item 3); HOST_WHOSE is the record: its lines carry no fault mark, and the
    caller never refuses on its failures."""
    gates = whose == PACK_WHOSE
    head = "" if gates else "for the record, never refuses: "
    bad = "✗" if gates else "·"
    tail = " (the pack carries the laptop's DB, the one install puts in place)" if gates else ""
    if "error" in read:
        return ([f"{bad} {head}{whose} NHL shot GATE: not read ({read['error']})"],
                [f"{whose} NHL shot GATE streams not read ({read['error']})"])
    bar, seasons = read.get("bar"), read.get("seasons") or {}
    if not isinstance(bar, (int, float)) or not seasons:
        return ([f"{bad} {head}{whose} NHL shot GATE: the read named no season or no bar"],
                [f"{whose} NHL shot GATE read named no season or no bar"])
    lines, below = [], []
    for season, b in sorted(seasons.items()):
        n, w = b.get("games") or 0, b.get("with_shots") or 0
        pct = w / n * 100 if n else 0.0
        ok = bool(n) and pct >= bar
        lines.append(f"{'·' if ok else bad} {head}{whose} NHL shot GATE stream {season}: {w}/{n} = {pct:.1f}% "
                     f"[{'PASS' if ok else 'BELOW'} >= {bar:g}%]")
        if not ok:
            below.append(f"{season} {w}/{n} = {pct:.1f}%")
    return lines, ([f"{whose} NHL shot GATE streams below {bar:g}%: {', '.join(below)}{tail}"] if below else [])


def backfill_lines(ctx: Ctx, read: dict) -> list[str]:
    """Addendum 79 item 4: the exact host command for the shot backfill, printed and never run; addendum 80 item 3:
    "optional before cutover; not a prerequisite" (the host catching up is still useful if the cutover slips). --start
    is the day
    before the first GATE-stream game's UTC date (the sync walks the schedule by local dates and skips games already
    stored); --end is the last one's (the sync keeps games up to a day past --end). The backup line is
    nhl-shot-sync's own docstring ("Take the .backup first")."""
    seasons = read.get("seasons") or {}
    firsts = sorted(b["first"] for b in seasons.values() if b.get("first"))
    lasts = sorted(b["last"] for b in seasons.values() if b.get("last"))
    if not firsts or not lasts:
        return ["· the host's NHL shot backfill: no stream date read, so no command is printed (law 4; the host's "
                "read is the record and never refuses)"]
    start = (date.fromisoformat(firsts[0]) - timedelta(days=1)).isoformat()
    py = f"sudo -u {ctx.service_user} venv/bin/python"
    sync = f"{py} cli.py nhl-shot-sync --start {start} --end {lasts[-1]}"
    return [f"· the host's NHL shot backfill: {BACKFILL_OPTIONAL} (addendum 80 item 3: the pack's DB is the one the "
            "cutover installs). Printed here, never run. FIRST, the dry run, pasted to the architect:",
            f"    cd {c.REPO}",
            f"    {sync} --dry-run",
            "  STOP: the write below is the operator's block after the architect has read that dry run.",
            f"    cd {c.REPO}",
            f"    {py} deploy/hosting/sp_backup.py daily",
            f"    {sync}",
            f"    {py} cli.py nhl-shot-coverage",
            f"  (--start {start}: the day before the first GATE-stream game, {firsts[0]} UTC; --end {lasts[-1]}: the "
            "last one's)"]


def step_preflight(ctx: Ctx) -> dict:
    s = "preflight"
    if ctx.pack is None or not (ctx.pack / sp_migrate.MANIFEST).is_file():
        _refuse(ctx, s, f"missing pack (no {sp_migrate.MANIFEST} in {ctx.pack})")
    _no_data(ctx, s, (ctx.pack, ctx.timers_file, c.HOST_ENV, c.receipts_path(), c.lock_path(),
                      ctx.scratch))
    print(f"· pack {ctx.pack}: its {sp_migrate.MANIFEST} present · no target under data/")
    timers = read_timers(ctx, s)
    # ARCHITECT 2026-10-13, addendum 57 item 8 (#481), verbatim: "The cutover's preflight reads the sp timers that
    # are active on the host. An active timer that is not on the list refuses the preflight, and the refusal names
    # it. The operator corrects the list by hand; the tool never writes it." (The pause stops only the listed timers:
    # one off the list would stay armed while the database is replaced.)
    active = active_sp_timers(ctx, s)
    listed_inactive = [t for t in timers if t not in active]
    off_list = [t for t in active if t not in timers]
    # ARCHITECT 2026-10-15, addendum 80 item 3 (Q1), verbatim: "The preflight runs BEFORE runbook step 2 stops the
    # timers [...] A run after step 2 is not the preflight; sp_cutover prints "timers already stopped: run the
    # preflight before step 2" when every listed timer is inactive, rather than a refusal that reads as a fault."
    # An sp timer active OFF the list is not "already stopped": addendum 57 item 8's refusal names it, so the stop
    # never stands in for it (the checks below refuse, naming both lists).
    if len(listed_inactive) == len(timers) and not off_list:
        print(TIMERS_STOPPED)
        _receipt(ctx, s, 1, stopped=TIMERS_STOPPED, timers=len(timers), timers_active=len(active),
                 timers_listed_inactive=listed_inactive, timers_file=str(ctx.timers_file))
        raise Stopped(TIMERS_STOPPED)
    # ARCHITECT 2026-10-15, addendum 79 item 4: "deploy/hosting/sp_cutover.py's preflight refuses when any listed
    # timer is not active (naming it) and when the host's nhl-shot-coverage GATE streams for the seasons it names
    # read below 95% (naming the stream and its percentage), and prints each check as a line." Past the pack, the
    # data/ guard and the two timer reads (nothing else reads without them), every check prints its line and the
    # preflight refuses ONCE, naming every check that failed.
    fails: list[str] = []
    extra: dict = {}

    def check(ok: bool, line: str, reason: str | None = None, **kw) -> bool:
        print(f"{'·' if ok else '✗'} {line}")
        if not ok:
            fails.append(reason or line)
            extra.update(kw)
        return ok

    odd = [t for t in off_list if not TIMER_NAME.match(t)]
    check(not off_list, f"active sp timers on the host: {len(active)} · not on the list: "
                        f"{', '.join(off_list) or 'none'}",
          f"active sp timers not on the timers list {ctx.timers_file}: {', '.join(off_list)} "
          "(add them to the list by hand; the tool never writes it)"
          + (f"; {', '.join(odd)} cannot go on the list as built (its names match {TIMER_NAME.pattern})"
             if odd else ""), timers_off_list=off_list)
    check(not listed_inactive, f"timers list {ctx.timers_file}: {len(timers)} · listed but not active: "
                               f"{', '.join(listed_inactive) or 'none'}",
          f"listed sp timers not active on the host: {', '.join(listed_inactive)} (start them, or take them off the "
          "list by hand, before the cutover)", timers_listed_inactive=listed_inactive)
    before, role, host_env = None, "", {}
    if check(c.HOST_ENV.is_file(), f"host env {c.HOST_ENV}: " + ("present" if c.HOST_ENV.is_file() else "MISSING"),
             f"host env missing: {c.HOST_ENV} (never created here — law 4)"):
        hits = _flag_lines(c.HOST_ENV.read_text())
        before = _flag_value(hits[0][1]) if len(hits) == 1 else None
        if check(len(hits) <= 1, f"{FLAG} lines in host.env: {len(hits)}",
                 f"{FLAG} set on {len(hits)} lines of {c.HOST_ENV} — ambiguous, fix by hand"):
            check(before is None or before in FLAG_KNOWN,
                  f"{FLAG} now: " + ("unset (no line)" if before is None else repr(before)),
                  f"{FLAG}={before!r} is not one of {FLAG_KNOWN} (law 4)")
        else:
            print(f"  ({FLAG}'s value not read: it is set on {len(hits)} lines)")
        if not ctx.dry_run:
            w_file, w_dir = os.access(c.HOST_ENV, os.W_OK), os.access(c.HOST_ENV.parent, os.W_OK)
            check(w_file and w_dir, f"host env writable by this user: file {'yes' if w_file else 'no'} · its "
                                    f"directory {'yes' if w_dir else 'no'}",
                  f"{c.HOST_ENV} not writable by this user — run with sudo")
        # ARCHITECT 2026-10-12, addendum 47 item 7(c): "The cutover's preflight refuses unless host.env itself says
        # SP_EXPORTS_MIRROR_ROLE=host." (install --replace copies the pack's .env, whose role is the laptop's, over
        # the checkout's; setting() reads host.env before .env, so only host.env's own line keeps the host's role.)
        host_env = c.parse_env_file(c.HOST_ENV)
        role = (host_env.get(ROLE_SETTING) or "").strip()
        check(role == "host", f"host.env's own {ROLE_SETTING}: {role[:20] or 'not set'}",
              f"{c.HOST_ENV} does not say {ROLE_SETTING}=host "
              f"({'not set there' if not role else 'it says ' + repr(role[:20])}): the pack's .env "
              "replaces the checkout's, and its role is the laptop's")
    else:
        print("  (host.env not read: its checks wait for the file)")
    problem = sp_migrate.pack_env_problem(ctx.pack)
    check(not problem, f"the pack's .env: {problem or 'DATABASE_URL relative'}", problem)
    # ARCHITECT 2026-10-15, addendum 80 item 3 (Q3), verbatim: "The shot gate reads the PACK's DB — the laptop's, the
    # one the cutover installs — and refuses on it; the host's live DB is read and printed for the record [...] and
    # never refuses." Below the bar on the host, the backfill's command is printed: optional, not a prerequisite.
    if ctx.dry_run:
        print("· NHL shot GATE: not read in a dry run (the scratch world holds no NHL games; the real preflight reads "
              "the pack's DB, which gates, and the host's live DB, for the record)")
        shot_pack = shot_host = None
    else:
        read = ctx.shot_read or run_shot_read
        shot_pack = read(ctx, True)
        lines, gate_fails = shot_gate_lines(shot_pack, PACK_WHOSE)
        shot_host = read(ctx, False)
        host_lines, host_below = shot_gate_lines(shot_host, HOST_WHOSE)
        for ln in lines + host_lines:
            print(ln)
        if host_below and "error" not in shot_host and shot_host.get("seasons"):   # a read, and below: never ✗
            for ln in backfill_lines(ctx, shot_host):
                print(ln)
        fails.extend(gate_fails)
    extra.update(shot_gate_pack=shot_pack if shot_pack is not None else "not read (dry run)",
                 shot_gate_host=shot_host if shot_host is not None else "not read (dry run)")
    if fails:
        _refuse(ctx, s, " | ".join(fails), **extra)          # one refusal, every failed check named; both reads kept
    env_changes = env_changes_by_pack(ctx.pack, host_env)
    if any(env_changes.values()):
        print("· settings whose value on the host changes when the pack's .env replaces the checkout's "
              "(names only, never values; those host.env gives a value left out):")
        for k, label in (("pack_only", "in the pack, not in the checkout's .env"),
                         ("checkout_only", "in the checkout's .env, not in the pack"),
                         ("differ", "in both, different values")):
            print(f"    {label}: {', '.join(env_changes[k]) or '—'}")
        print("  The cutover ruling names the settings it expects on this list; a name it did not give stops the "
              "cutover before pause (h2-cutover-runbook.md section 1 step 4).")
    else:
        print("· settings changed by the pack's .env: none")
    if _as_service_user(ctx):
        rc, out = ctx.runner(["runuser", "-u", ctx.service_user, "--", sys.executable,
                              str(HERE / "sp_migrate.py"), "verify", "--pack", str(ctx.pack)])
        print(out.rstrip())
    else:
        rc = sp_migrate.verify(ctx.pack)
    man = _manifest(ctx)
    if rc != 0:
        _refuse(ctx, s, "sp_migrate verify FAIL (see the migrate receipt)", pack=str(ctx.pack),
                s1=man["files"].get(sp_migrate.DB), **extra)
    return _receipt(ctx, s, 0, pack=str(ctx.pack), s1=man["files"].get(sp_migrate.DB),
                    n_tables=len(man["counts"]), source_host=man.get("source_host"),
                    pack_git_sha=man.get("git_sha"), timers=len(timers), timers_active=len(active),
                    timers_listed_inactive=listed_inactive, timers_file=str(ctx.timers_file),
                    host_env=str(c.HOST_ENV), flag_before=before, mirror_role=role, env_changes=env_changes,
                    **extra)


def env_changes_by_pack(pack: Path, host_env: dict) -> dict:
    """Addendum 47 item 7(c): "each setting whose value on the host changes when the pack's .env replaces the
    checkout's: in the pack and not in the checkout's .env, in the checkout's .env and not in the pack, or in both
    with different values. A setting host.env carries is left out, since host.env wins. The list refuses nothing by
    itself." Addendum 48 item 6 (#460): "Only a setting to which host.env gives a value is left out of the list."
    Names only; values are compared, never returned."""
    if not (pack / sp_migrate.ENV).is_file():  # no env in the pack: install leaves the checkout's .env (Codex on #457)
        return {"pack_only": [], "checkout_only": [], "differ": []}
    packed = c.parse_env_file(pack / sp_migrate.ENV)
    cur_p = c.REPO / ".env"
    current = c.parse_env_file(cur_p) if cur_p.is_file() else {}
    keep = lambda k: not (host_env.get(k) or "").strip()   # addendum 48 item 6 (#460): only a value host.env gives
                                                           # is left out ("NTFY_TOPIC=" falls back to the .env)
    return {"pack_only": sorted(k for k in packed if k not in current and keep(k)),
            "checkout_only": sorted(k for k in current if k not in packed and keep(k)),
            "differ": sorted(k for k in packed if k in current and packed[k] != current[k] and keep(k))}


def step_pause(ctx: Ctx) -> dict:
    s = "pause"
    timers = read_timers(ctx, s)
    rc, out = ctx.runner(["systemctl", "stop", *timers])
    if rc != 0:
        _refuse(ctx, s, f"systemctl stop exit {rc}: {c.redact(out.strip())[:200]}")
    rc, out = ctx.runner(["systemctl", "is-active", *timers])
    states = out.split()
    still = [t for t, st in zip(timers, states) if st != "inactive"]
    if len(states) != len(timers) or still:
        _refuse(ctx, s, f"timers not all inactive after stop: {still or states}")
    _, out = ctx.runner(["systemctl", "list-units", "--type=service", "--state=active,activating",
                         "--no-legend", "--plain", "sp-chain@*"])
    running = [ln.split()[0] for ln in out.splitlines() if ln.strip()]
    return _receipt(ctx, s, 0, timers_stopped=len(timers), chains_running=running)


def _env_key(line: str) -> str | None:
    """The setting a .env line defines, read exactly as sp_common.parse_env_file reads it (None: no setting)."""
    t = line.strip()
    if not t or t.startswith("#") or "=" not in t:
        return None
    return t.split("=", 1)[0].strip().removeprefix("export ").strip()


def _scrub_plan(ctx: Ctx, man: dict) -> dict:
    """Addendum 168 item 3, decided BEFORE sp_migrate.install replaces the checkout's .env: the ruled names
    (PACK_ONLY_SCRUB) that the preflight's own comparison (env_changes_by_pack: the pack's .env against the checkout's
    .env as it stands, host.env's values left out) lists as pack-only. When the checkout's .env is already the pack's,
    byte for byte, the .env the pack replaces is gone and which names came only from the pack cannot be read here;
    nothing is removed and the names are reported as undecided (law 4). The same when host.env cannot be read."""
    pe = ctx.pack / sp_migrate.ENV
    if not pe.is_file():                      # no env in the pack: install leaves the checkout's .env (Codex on #457)
        return {"remove": [], "undecided": [], "why": None}
    carried = [k for k in PACK_ONLY_SCRUB if k in c.parse_env_file(pe)]
    envp = c.REPO / ".env"
    why = None
    if envp.is_file() and c.sha256_file(envp) == man["files"].get(sp_migrate.ENV):
        why = "the checkout's .env was already the pack's before install, so which settings came only from the pack " \
              "cannot be read here"
    elif not (c.HOST_ENV.is_file() and os.access(c.HOST_ENV, os.R_OK)):
        why = f"host.env {c.HOST_ENV} cannot be read, so which settings it defines cannot be read here"
    if why:
        return {"remove": [], "undecided": carried, "why": why if carried else None}
    pack_only = env_changes_by_pack(ctx.pack, c.parse_env_file(c.HOST_ENV))["pack_only"]
    return {"remove": [k for k in PACK_ONLY_SCRUB if k in pack_only], "undecided": [], "why": None}


def _write_private(path: Path, data: bytes, owner: tuple[int, int] | None = None, mode: int | None = None) -> None:
    """Create `path` with mode 0600 from the outset (O_CREAT | O_EXCL: never an existing file, never a wider mode while
    the secret bytes are written; Codex on #682), write `data`, then, when named, give it `owner` and `mode` through the
    open descriptor, after the bytes. FileExistsError if the name is taken."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            if owner is not None:
                os.fchown(f.fileno(), *owner)
            if mode is not None:
                os.fchmod(f.fileno(), mode)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


ENV_COPY_PREFIX = "checkout.env.pre-scrub-"
ENV_COPY_MODE = 0o640


def _read_pack_env(ctx: Ctx, man: dict) -> bytes:
    """The pack's .env as root reads it for the copy (Codex on #682, P1): opened without following a symlink, a regular
    file only, and its bytes the manifest's (sha256), so a name swapped after _scrub_plan read it is never copied into
    a group-readable file. OSError otherwise."""
    fd = os.open(ctx.pack / sp_migrate.ENV, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            raise OSError(f"the pack's {sp_migrate.ENV} is not a regular file")
        data = f.read()
    if hashlib.sha256(data).hexdigest() != man["files"].get(sp_migrate.ENV):
        raise OSError(f"the pack's {sp_migrate.ENV} is not the manifest's (sha256)")
    return data


def _keep_env_copy(ctx: Ctx, plan: dict, man: dict) -> Path | None:
    """The copy of the .env the scrub edits, kept BEFORE install (ARCHITECT 2026-10-26, on Codex's two P1s on #682:
    "a copy of a file that holds secrets must be created 0600 before any byte is written, and it must live where git
    can't see it (beside `host.env.pre-cutover-<ts>` under `/etc/sports-predictor/`, root:sp 0640, is the pattern the
    flip already uses — not in the checkout behind a `.gitignore` line)"). It is written beside host.env as
    checkout.env.pre-scrub-<ts> (a taken name gets a -N suffix, never overwritten), created 0600, then host.env's owner
    (as root) and 0640. Its bytes are the pack's .env, the file install places and the scrub edits (_scrub_env checks
    them against the placed .env before it edits anything). Root writes it before the `sp` install, which cannot write
    that directory. None when nothing is to be removed."""
    if not plan["remove"]:
        return None
    data = _read_pack_env(ctx, man)
    st = c.HOST_ENV.stat()
    owner = (st.st_uid, st.st_gid) if _euid() == 0 else None
    stamp = c.utc_now().strftime("%Y%m%dT%H%M%SZ")
    for n in range(100):
        keep = c.HOST_ENV.with_name(f"{ENV_COPY_PREFIX}{stamp}{'' if n == 0 else f'-{n}'}")
        try:
            _write_private(keep, data, owner, ENV_COPY_MODE)
            return keep
        except FileExistsError:
            continue
    raise FileExistsError(f"{ENV_COPY_PREFIX}{stamp}[-N]: 100 names taken")


def _scrub_env(ctx: Ctx, man: dict, plan: dict, keep: Path | None) -> dict:
    """Addendum 168 item 3: remove the planned names from the checkout's .env once it is the pack's. Line-preserving
    (every other line byte-identical); the .env before it is `keep`, the copy _keep_env_copy wrote before install, and
    nothing is edited unless that copy holds the placed .env's bytes. Names printed and returned, never a value. An
    OSError propagates to the caller, which receipts it as a refusal (Codex on #682)."""
    envp = c.REPO / ".env"
    out = {"env_scrub_ruled": list(PACK_ONLY_SCRUB), "env_removed": [], "env_kept_copy": None}
    placed = envp.is_file() and c.sha256_file(envp) == man["files"].get(sp_migrate.ENV)
    names = plan["remove"] if placed else []
    if names:
        if keep is None or not keep.is_file() or c.sha256_file(keep) != c.sha256_file(envp):
            raise FileNotFoundError(f"no kept copy of the placed .env ({keep or 'none written'}): nothing edited")
        data = envp.read_bytes()              # bytes: every line's own ending kept, \r\n included
        lines = data.splitlines(keepends=True)
        kept = [ln for ln in lines if _env_key(ln.decode("utf-8", "replace")) not in names]
        mode = envp.stat().st_mode & 0o7777
        tmp = envp.with_name(f".{envp.name}.scrub-tmp")
        tmp.unlink(missing_ok=True)           # a stale temporary name from an interrupted run is never written into
        _write_private(tmp, b"".join(kept))
        os.chmod(tmp, mode)                   # the .env's own mode, as install left it
        os.replace(tmp, envp)
        out.update(env_removed=list(names), env_kept_copy=str(keep))
        print(f"· pack-only settings removed from the checkout's .env (addendum 168 item 3; names only, never "
              f"values): {', '.join(names)} · the .env before it kept as {keep}")
    else:
        print("· pack-only settings removed from the checkout's .env (addendum 168 item 3): none")
        if keep is not None:                  # written before install; nothing edited (the .env was not placed)
            out["env_kept_copy"] = str(keep)
            print(f"· the copy kept before install is unused, nothing was removed: {keep}")
    if plan["undecided"]:
        out.update(env_scrub_undecided=list(plan["undecided"]), env_scrub_undecided_why=plan["why"])
        print(f"· NOT decided, nothing removed: {', '.join(plan['undecided'])} — {plan['why']}; check them by hand "
              "against the preflight's env_changes (h2-cutover-runbook.md section 1 step 4)")
    return out


def _scrub_failed(plan: dict, e: OSError, keep: Path | None = None) -> dict:
    """The receipt fields for a scrub that raised (Codex on #682): the names it meant to remove, none removed."""
    err = f"{e.__class__.__name__}: {e}"
    print(f"✗ the ruled pack-only settings could not be removed from the checkout's .env ({err}): remove "
          f"{', '.join(plan['remove']) or '(none planned)'} from it by hand (addendum 168 item 3)")
    return {"env_scrub_ruled": list(PACK_ONLY_SCRUB), "env_removed": [], "env_kept_copy": str(keep) if keep else None,
            "env_scrub_planned": list(plan["remove"]), "env_scrub_error": err}


def _keep_copy_or_refuse(ctx: Ctx, plan: dict, man: dict) -> Path | None:
    """_keep_env_copy, before install changes anything: a copy that cannot be kept refuses install, nothing placed."""
    try:
        return _keep_env_copy(ctx, plan, man)
    except OSError as e:
        _refuse(ctx, "install", f"the .env copy could not be kept beside {c.HOST_ENV} ({e.__class__.__name__}: {e}) "
                                "— nothing installed", env_scrub_ruled=list(PACK_ONLY_SCRUB),
                env_scrub_planned=list(plan["remove"]))


def _install_in_process(ctx: Ctx) -> dict:
    s = "install"
    man = _manifest(ctx)
    scrub: dict = {}
    try:
        with c.db_lock(ctx.lock_timeout):
            plan = _scrub_plan(ctx, man)
            keep = ctx.env_kept_copy or _keep_copy_or_refuse(ctx, plan, man)
            try:
                rc = sp_migrate.install(ctx.pack, replace=True)
            finally:                          # the pack's .env never stays unscrubbed, whatever install did after it
                try:
                    scrub = _scrub_env(ctx, man, plan, keep)
                except OSError as e:          # receipted, never a traceback (Codex on #682)
                    scrub = _scrub_failed(plan, e, keep)
            if scrub.get("env_scrub_error"):
                _refuse(ctx, s, f"the pack's .env is in place but the ruled pack-only settings could not be removed "
                                f"({scrub['env_scrub_error']}) — remove them from the checkout's .env by hand", **scrub)
            target = c.db_path()
            s2 = c.sha256_file(target) if target.exists() else None
            r2 = c.table_counts(target)
    except SystemExit as e:
        _refuse(ctx, s, str(e).lstrip("✗ ").strip(), **scrub)
    except TimeoutError as e:
        _refuse(ctx, s, f"{e} — a chain still holds the DB lock")
    s1, r1 = man["files"].get(sp_migrate.DB), man["counts"]
    if rc != 0 or s2 != s1 or r2 != r1:
        _refuse(ctx, s, "installed DB does not match the manifest (S2/R2 vs S1/R1)",
                s1=s1, s2=s2, r_mismatch=sorted(t for t in set(r1) | set(r2) if r1.get(t) != r2.get(t)), **scrub)
    aside = sorted(p.name for p in target.parent.glob("rehearsal_*.db"))
    return _receipt(ctx, s, 0, db=str(target), s1=s1, s2=s2, s2_eq_s1=True, r2_eq_r1=True,
                    n_tables=len(r2), counts=r2, rehearsal_aside=aside[-1:] or None, **scrub)


def step_install(ctx: Ctx) -> dict:
    if not _as_service_user(ctx):
        return _install_in_process(ctx)
    # The .env copy is root's to write (the service user cannot write host.env's directory): it is kept here, before
    # the service user's install, and named to it (ARCHITECT 2026-10-26, on Codex's P1s on #682).
    man = _manifest(ctx)
    keep = _keep_copy_or_refuse(ctx, _scrub_plan(ctx, man), man)
    rc, out = ctx.runner(["runuser", "-u", ctx.service_user, "--", sys.executable, str(HERE / "sp_cutover.py"),
                          "install", "--pack", str(ctx.pack), "--timers-file", str(ctx.timers_file),
                          "--lock-timeout", str(ctx.lock_timeout), *(["--env-kept-copy", str(keep)] if keep else [])])
    print(out.rstrip())
    got = _last_ok(ctx, "install")
    if rc != 0 or not got:
        _refuse(ctx, "install", f"install as {ctx.service_user} exit {rc} (see its receipt)")
    return got[1]


def step_flip(ctx: Ctx) -> dict:
    s = "flip"
    p = c.HOST_ENV
    _no_data(ctx, s, (p,))
    try:
        text = p.read_text()
    except OSError as e:
        _refuse(ctx, s, f"host env unreadable: {p} ({type(e).__name__})")
    lines = text.splitlines(keepends=True)
    hits = _flag_lines(text)
    if len(hits) > 1:
        _refuse(ctx, s, f"{FLAG} set on {len(hits)} lines — ambiguous")
    before = _flag_value(hits[0][1]) if hits else None
    stamp = c.utc_now().strftime("%Y%m%dT%H%M%SZ")
    keep = p.with_name(f"{p.name}.pre-cutover-{stamp}")
    if keep.exists():
        _refuse(ctx, s, f"{keep} exists — never overwritten")
    st = p.stat()
    shutil.copy2(p, keep)
    if _as_service_user(ctx):
        os.chown(keep, st.st_uid, st.st_gid)
    changed = before != FLAG_VALUE
    if changed:
        if hits:
            i, m = hits[0]
            lines[i] = f"{m.group(1)}{FLAG}={FLAG_VALUE}{m.group(3) or ''}"
        else:
            if lines and not lines[-1].endswith("\n"):
                lines[-1] += "\n"
            lines.append(f"{FLAG}={FLAG_VALUE}\n")
        tmp = p.with_name(f".{p.name}.cutover-tmp")
        tmp.write_text("".join(lines))
        os.chmod(tmp, st.st_mode & 0o7777)
        if _as_service_user(ctx):
            os.chown(tmp, st.st_uid, st.st_gid)
        os.replace(tmp, p)
    after = c.parse_env_file(p)
    if after.get(FLAG) in FLAG_KNOWN:          # this process's receipts name the NEW writer from here on
        os.environ[FLAG] = after[FLAG]
    old = c.parse_env_file(keep)
    others_kept = {k: v for k, v in after.items() if k != FLAG} == {k: v for k, v in old.items() if k != FLAG}
    if after.get(FLAG) != FLAG_VALUE or not others_kept:
        _refuse(ctx, s, f"post-check failed: {FLAG}={after.get(FLAG)!r}, other keys kept={others_kept}",
                kept_copy=str(keep))
    return _receipt(ctx, s, 0, host_env=str(p), flag=FLAG, before=before, after=FLAG_VALUE,
                    changed=changed, kept_copy=str(keep), other_keys_unchanged=True)


def _backup_receipt_since(ts: str) -> dict | None:
    p = c.receipts_path()
    if not p.exists():
        return None
    found = None
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("kind") == "backup" and r.get("ts", "") >= ts:
            found = r
    return found


def step_resume(ctx: Ctx) -> dict:
    s = "resume"
    timers = read_timers(ctx, s)
    t0 = c.iso()
    rc, out = ctx.runner(["systemctl", "start", *timers])
    if rc != 0:
        _refuse(ctx, s, f"systemctl start exit {rc}: {c.redact(out.strip())[:200]}")
    rc, out = ctx.runner(["systemctl", "is-active", *timers])
    states = out.split()
    off = [t for t, st in zip(timers, states) if st != "active"]
    if len(states) != len(timers) or off:
        _refuse(ctx, s, f"timers not all active after start: {off or states}")
    rc, out = ctx.runner(["systemctl", "start", BACKUP_UNIT])
    if rc != 0:
        _refuse(ctx, s, f"{BACKUP_UNIT} exit {rc}: {c.redact(out.strip())[:200]}", timers_active=len(timers))
    bk = _backup_receipt_since(t0)
    if not bk or bk.get("exit") != 0 or bk.get("integrity") != "ok":
        _refuse(ctx, s, f"no clean backup receipt after {BACKUP_UNIT} (law 2)", timers_active=len(timers),
                backup=bk)
    return _receipt(ctx, s, 0, timers_active=len(timers), backup_file=bk.get("file"),
                    backup_sha256=bk.get("sha256"), backup_integrity=bk.get("integrity"))


def _read(p: str) -> str | None:
    try:
        return Path(p).read_text().strip()
    except OSError:
        return None


def step_receipt(ctx: Ctx) -> dict:
    s = "receipt"
    got, last = {}, -1
    order_ok = True
    for st in STEPS[:-1]:
        hit = _last_ok(ctx, st)
        if hit is None:
            _refuse(ctx, s, f"no successful '{st}' receipt for cutover {ctx.cutover_id}")
        order_ok &= hit[0] > last
        last = hit[0]
        got[st] = hit[1]
    if not order_ok:
        _refuse(ctx, s, f"step receipts out of order for cutover {ctx.cutover_id}")
    ins, res = got["install"], got["resume"]
    flag_now = c.parse_env_file(c.HOST_ENV).get(FLAG)
    ok = ins.get("s2") == ins.get("s1") and ins.get("r2_eq_r1") is True and flag_now == FLAG_VALUE
    summary = dict(running=ctx.release if ctx.dry_run else c.running_release(),
                   db_sha256=ins.get("s2"), s2_eq_s1=ins.get("s2") == ins.get("s1"),
                   r2_eq_r1=ins.get("r2_eq_r1"), n_tables=ins.get("n_tables"),
                   flag=f"{FLAG}={flag_now}", timers_active=res.get("timers_active"),
                   first_backup=res.get("backup_file"), first_backup_sha256=res.get("backup_sha256"),
                   boot_id=_read("/proc/sys/kernel/random/boot_id"))
    if not ok:
        _refuse(ctx, s, "summary does not hold (S2=S1, R2=R1, flag)", **summary)
    rec = _receipt(ctx, s, 0, **summary)
    print(f"cutover receipt: {ctx.cutover_id} · running {summary['running'] or 'release ?'} · "
          f"db sha256 {summary['db_sha256']} (S2 = S1) · R2 = R1 on {summary['n_tables']} tables · "
          f"{summary['flag']} · timers {summary['timers_active']} active · first backup "
          f"{summary['first_backup']} {(summary['first_backup_sha256'] or '-')[:16]}")
    return rec


STEP_FN = {"preflight": step_preflight, "pause": step_pause, "install": step_install,
           "flip": step_flip, "resume": step_resume, "receipt": step_receipt}


def drive(ctx: Ctx, steps) -> int:
    for st in steps:
        print(f"── {st}")
        try:
            ctx.done[st] = STEP_FN[st](ctx)
        except Stopped:                      # addendum 80 item 3: its one line is already printed; never a fault
            return 1
        except Refused as e:
            print(str(e))
            if "pause" in ctx.done and "resume" not in ctx.done:
                print("  timers remain STOPPED — fix and re-run, or follow the runbook's Rollback.")
            print(f"{'DRY-RUN ' if ctx.dry_run else ''}FAIL at {st}")
            return 1
    if list(steps) == list(STEPS):
        print(f"{'DRY-RUN ' if ctx.dry_run else ''}PASS — {len(steps)}/{len(STEPS)} steps receipted "
              f"(cutover {ctx.cutover_id})")
    return 0


# ------------------------------------------------------------- dry run ----

@contextmanager
def isolated():
    """Snapshot sp_common's module state and os.environ; restore on exit."""
    saved = (c.REPO, c.HOST_ENV, c._DOTENV_CACHE, dict(os.environ))
    try:
        yield
    finally:
        c.REPO, c.HOST_ENV, c._DOTENV_CACHE = saved[:3]
        os.environ.clear()
        os.environ.update(saved[3])


def runbook_timers() -> list[str]:
    """The T11 enable list from hosting-h1.md (the list H2 steps 2 and 6 reuse)."""
    return c.t11_lists(HERE.parents[1] / "docs" / "specs" / "hosting-h1.md")["TIMERS"]


def _under(root: Path, p: Path) -> bool:
    p, root = p.resolve(), root.resolve()
    return p == root or root in p.parents


def dry_run(pack: Path | None, scratch: Path, timers_seed: Path | None, runner: Runner | None) -> int:
    c.refuse_under_data(scratch)          # the REAL checkout's data/, before any re-pointing
    scratch = scratch.resolve()
    if scratch.exists() and any(scratch.iterdir()):
        raise SystemExit(f"✗ REFUSED: scratch {scratch} exists and is not empty.")
    release = c.running_release()
    example = HERE / "etc" / "host.env.example"
    timers = (timers_seed.read_text().split() if timers_seed else runbook_timers())
    with isolated():
        repo, etc = scratch / "repo", scratch / "etc"
        (repo / "data").mkdir(parents=True)
        etc.mkdir()
        con = sqlite3.connect(repo / "data" / "sports.db")   # the host's rehearsal DB (scratch)
        con.executescript("CREATE TABLE matches(id INTEGER); INSERT INTO matches VALUES (1),(2);")
        con.commit()
        con.close()
        (repo / ".env").write_text("# scratch host checkout .env (rehearsal)\n"
                                   "DATABASE_URL=sqlite:///./data/sports.db\n")
        shutil.copyfile(example, etc / "host.env")
        (etc / "timers.enabled").write_text(" ".join(timers) + "\n")
        c.REPO, c.HOST_ENV, c._DOTENV_CACHE = repo, etc / "host.env", None
        os.environ.update(SP_RECEIPTS=str(scratch / "log" / "receipts.jsonl"),
                          SP_LOCK=str(scratch / "lib" / "db.lock"),
                          SP_BACKUP_DIR=str(scratch / "backups"),
                          DATABASE_URL="sqlite:///./data/sports.db")
        for k in ("SP_PARALLEL_MODE", "SP_DESIGNATED_DAYS", "SP_WRITER_OF_RECORD"):
            os.environ.pop(k, None)
        resolved = {"db": c.db_path(), "receipts": c.receipts_path(), "lock": c.lock_path(),
                    "host_env": c.HOST_ENV, "timers": etc / "timers.enabled",
                    "backups": Path(os.environ["SP_BACKUP_DIR"])}
        outside = {k: str(v) for k, v in resolved.items() if not _under(scratch, v)}
        if outside:
            raise SystemExit(f"✗ REFUSED: dry-run paths outside the scratch dir: {outside}")
        run = runner or DryRunner(active=timers)
        ctx = Ctx(pack=pack.resolve() if pack else None, timers_file=etc / "timers.enabled", runner=run,
                  dry_run=True, scratch=scratch, release=release,
                  cutover_id=f"dryrun-{pack.name if pack else 'nopack'}")
        print(f"DRY-RUN scratch {scratch} · code {release or 'release ?'} · {len(timers)} timers "
              f"({'seed ' + str(timers_seed) if timers_seed else 'hosting-h1.md T11'})")
        rc = drive(ctx, STEPS)
        for call in getattr(run, "calls", []):
            print(f"  systemctl (recorded, not run): {' '.join(call[1:])}")
        print(f"real host.env / DB / receipts / systemd untouched; scratch kept at {scratch}")
    return rc


# ---------------------------------------------------------------- main ----

def main(argv=None, runner: Runner | None = None, shot_read: Callable | None = None) -> int:
    ap = argparse.ArgumentParser(description="H2 cutover orchestrator (host side).")
    ap.add_argument("step", choices=[*STEPS, "run", "shot-gate"],
                    help="shot-gate: internal, the preflight's read of an NHL shot GATE (never a step): with --pack the "
                         "pack's DB, without it the host's live DB")
    ap.add_argument("--pack", type=Path)
    ap.add_argument("--timers-file", type=Path, default=None,
                    help=f"default: SP_TIMERS_ENABLED or {TIMERS_ENABLED}")
    ap.add_argument("--lock-timeout", type=float, default=3600.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--scratch", type=Path)
    ap.add_argument("--env-kept-copy", type=Path, default=None,
                    help="internal: the .env copy root kept before the service user's install (step_install)")
    a = ap.parse_args(argv)
    if a.dry_run != (a.scratch is not None):
        raise SystemExit("✗ REFUSED: --dry-run and --scratch go together (flag mismatch).")
    if a.dry_run and a.step != "run":
        raise SystemExit("✗ REFUSED: --dry-run runs the whole sequence: use `run` (flag mismatch).")
    if a.dry_run:
        return dry_run(a.pack, a.scratch, a.timers_file, runner)
    c.load_host_env()
    if a.step == "shot-gate":
        return shot_gate_read(a.pack.resolve() if a.pack else None)
    if _euid() == 0:  # root reading the sp-owned checkout: let git (release name) read it
        os.environ.setdefault("GIT_CONFIG_COUNT", "1")
        os.environ.setdefault("GIT_CONFIG_KEY_0", "safe.directory")
        os.environ.setdefault("GIT_CONFIG_VALUE_0", str(c.REPO))
    timers_file = a.timers_file or Path(c.setting("SP_TIMERS_ENABLED") or TIMERS_ENABLED)
    pack = a.pack.resolve() if a.pack else None
    ctx = Ctx(pack=pack, timers_file=timers_file, runner=runner or system_runner,
              lock_timeout=a.lock_timeout, service_user=c.setting("SP_SERVICE_USER") or "sp",
              cutover_id=pack.name if pack else "nopack", shot_read=shot_read, env_kept_copy=a.env_kept_copy)
    return drive(ctx, STEPS if a.step == "run" else [a.step])


if __name__ == "__main__":
    sys.exit(main())
