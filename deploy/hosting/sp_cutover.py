#!/usr/bin/env python3
"""H2 cutover, HOST side: the ruled morning sequence as receipted steps
(docs/specs/h2-cutover-runbook.md; hosting-h1.md "H2"). Cutover itself is an
ARCHITECT RULING on the frozen parallel-week criteria (H0-18) — nothing here
decides or triggers it; this only executes the sequence once ruled.

    sp_cutover.py <step> --pack <dir> [--timers-file F] [--lock-timeout S]
    sp_cutover.py run    --pack <dir> --dry-run --scratch <DIR>

Steps (in order; `run` = all six, the first failure stops):
  preflight  pack present; sp_migrate verify PASS (sha256 + integrity + every
             table count); the pack's DATABASE_URL relative; timers list
             readable; host.env present, writable, at most one
             SP_WRITER_OF_RECORD line with a known value; no target under data/.
             Everything that could fail install is refused HERE, before pause.
  pause      systemctl stop <timers.enabled>; every timer must read inactive.
             Running sp-chain@ services are listed (install waits on the DB lock).
  install    sp_migrate install --replace (verify again, place, re-verify),
             under the DB lock; S2 = S1 and R2 = R1 for every table, or refuse.
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
failing step refuses (exit 1, receipt carries `refused`). After `pause` a
refusal leaves the timers STOPPED by design (runbook: Rollback).

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
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sp_common as c  # noqa: E402
import sp_migrate  # noqa: E402

STEPS = ("preflight", "pause", "install", "flip", "resume", "receipt")
TIMERS_ENABLED = Path("/etc/sports-predictor/timers.enabled")   # hosting-h1.md T11
TIMER_NAME = re.compile(r"^sp-[a-z0-9-]+\.timer$")
BACKUP_UNIT = "sp-backup.service"
# The writer-of-record setting H2 step 6 names: the existing H0-16 variable
# (grep: sp_run.metered_skip, etc/host.env.example). Values: full | designated.
FLAG, FLAG_VALUE, FLAG_KNOWN = "SP_WRITER_OF_RECORD", "host", ("laptop", "host")
FLAG_LINE = re.compile(r"^(\s*(?:export\s+)?)" + FLAG + r"\s*=(.*?)(\r?\n)?$")

Runner = Callable[[list], "tuple[int, str]"]


class Refused(Exception):
    pass


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

def step_preflight(ctx: Ctx) -> dict:
    s = "preflight"
    if ctx.pack is None or not (ctx.pack / sp_migrate.MANIFEST).is_file():
        _refuse(ctx, s, f"missing pack (no {sp_migrate.MANIFEST} in {ctx.pack})")
    _no_data(ctx, s, (ctx.pack, ctx.timers_file, c.HOST_ENV, c.receipts_path(), c.lock_path(),
                      ctx.scratch))
    timers = read_timers(ctx, s)
    if not c.HOST_ENV.is_file():
        _refuse(ctx, s, f"host env missing: {c.HOST_ENV} (never created here — law 4)")
    hits = _flag_lines(c.HOST_ENV.read_text())
    if len(hits) > 1:
        _refuse(ctx, s, f"{FLAG} set on {len(hits)} lines of {c.HOST_ENV} — ambiguous, fix by hand")
    before = _flag_value(hits[0][1]) if hits else None
    if before is not None and before not in FLAG_KNOWN:
        _refuse(ctx, s, f"{FLAG}={before!r} is not one of {FLAG_KNOWN} (law 4)")
    if not ctx.dry_run and not (os.access(c.HOST_ENV, os.W_OK) and os.access(c.HOST_ENV.parent, os.W_OK)):
        _refuse(ctx, s, f"{c.HOST_ENV} not writable by this user — run with sudo")
    problem = sp_migrate.pack_env_problem(ctx.pack)
    if problem:
        _refuse(ctx, s, problem)
    if _as_service_user(ctx):
        rc, out = ctx.runner(["runuser", "-u", ctx.service_user, "--", sys.executable,
                              str(HERE / "sp_migrate.py"), "verify", "--pack", str(ctx.pack)])
        print(out.rstrip())
    else:
        rc = sp_migrate.verify(ctx.pack)
    man = _manifest(ctx)
    if rc != 0:
        _refuse(ctx, s, "sp_migrate verify FAIL (see the migrate receipt)", pack=str(ctx.pack),
                s1=man["files"].get(sp_migrate.DB))
    return _receipt(ctx, s, 0, pack=str(ctx.pack), s1=man["files"].get(sp_migrate.DB),
                    n_tables=len(man["counts"]), source_host=man.get("source_host"),
                    pack_git_sha=man.get("git_sha"), timers=len(timers),
                    timers_file=str(ctx.timers_file), host_env=str(c.HOST_ENV), flag_before=before)


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


def _install_in_process(ctx: Ctx) -> dict:
    s = "install"
    man = _manifest(ctx)
    try:
        with c.db_lock(ctx.lock_timeout):
            rc = sp_migrate.install(ctx.pack, replace=True)
            target = c.db_path()
            s2 = c.sha256_file(target) if target.exists() else None
            r2 = c.table_counts(target)
    except SystemExit as e:
        _refuse(ctx, s, str(e).lstrip("✗ ").strip())
    except TimeoutError as e:
        _refuse(ctx, s, f"{e} — a chain still holds the DB lock")
    s1, r1 = man["files"].get(sp_migrate.DB), man["counts"]
    if rc != 0 or s2 != s1 or r2 != r1:
        _refuse(ctx, s, "installed DB does not match the manifest (S2/R2 vs S1/R1)",
                s1=s1, s2=s2, r_mismatch=sorted(t for t in set(r1) | set(r2) if r1.get(t) != r2.get(t)))
    aside = sorted(p.name for p in target.parent.glob("rehearsal_*.db"))
    return _receipt(ctx, s, 0, db=str(target), s1=s1, s2=s2, s2_eq_s1=True, r2_eq_r1=True,
                    n_tables=len(r2), counts=r2, rehearsal_aside=aside[-1:] or None)


def step_install(ctx: Ctx) -> dict:
    if not _as_service_user(ctx):
        return _install_in_process(ctx)
    rc, out = ctx.runner(["runuser", "-u", ctx.service_user, "--", sys.executable, str(HERE / "sp_cutover.py"),
                          "install", "--pack", str(ctx.pack), "--timers-file", str(ctx.timers_file),
                          "--lock-timeout", str(ctx.lock_timeout)])
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
    rb = (HERE.parents[1] / "docs" / "specs" / "hosting-h1.md").read_text()
    block = rb[rb.index('TIMERS="') + len('TIMERS="'):]
    return block[:block.index('"')].split()


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

def main(argv=None, runner: Runner | None = None) -> int:
    ap = argparse.ArgumentParser(description="H2 cutover orchestrator (host side).")
    ap.add_argument("step", choices=[*STEPS, "run"])
    ap.add_argument("--pack", type=Path)
    ap.add_argument("--timers-file", type=Path, default=None,
                    help=f"default: SP_TIMERS_ENABLED or {TIMERS_ENABLED}")
    ap.add_argument("--lock-timeout", type=float, default=3600.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--scratch", type=Path)
    a = ap.parse_args(argv)
    if a.dry_run != (a.scratch is not None):
        raise SystemExit("✗ REFUSED: --dry-run and --scratch go together (flag mismatch).")
    if a.dry_run and a.step != "run":
        raise SystemExit("✗ REFUSED: --dry-run runs the whole sequence: use `run` (flag mismatch).")
    if a.dry_run:
        return dry_run(a.pack, a.scratch, a.timers_file, runner)
    c.load_host_env()
    if _euid() == 0:  # root reading the sp-owned checkout: let git (release name) read it
        os.environ.setdefault("GIT_CONFIG_COUNT", "1")
        os.environ.setdefault("GIT_CONFIG_KEY_0", "safe.directory")
        os.environ.setdefault("GIT_CONFIG_VALUE_0", str(c.REPO))
    timers_file = a.timers_file or Path(c.setting("SP_TIMERS_ENABLED") or TIMERS_ENABLED)
    pack = a.pack.resolve() if a.pack else None
    ctx = Ctx(pack=pack, timers_file=timers_file, runner=runner or system_runner,
              lock_timeout=a.lock_timeout, service_user=c.setting("SP_SERVICE_USER") or "sp",
              cutover_id=pack.name if pack else "nopack")
    return drive(ctx, STEPS if a.step == "run" else [a.step])


if __name__ == "__main__":
    sys.exit(main())
