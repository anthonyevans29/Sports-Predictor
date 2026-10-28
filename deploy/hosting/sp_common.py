"""Shared plumbing for the hosting pack (H1): paths, host env, the DB lock,
receipts-log appends, redaction, read-only DB counts.

Stdlib only, so every sp_* script runs under the venv python or a bare
python3 alike (the laptop can use the same writer during the parallel week).
Nothing here writes under data/ — backups and migration packs are refused
there (law 5).
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import socket
import sqlite3
import subprocess
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HOST_ENV = Path(os.environ.get("SP_HOST_ENV", "/etc/sports-predictor/host.env"))

# Tables whose counts ride on every chain receipt (names verified against
# src/db/schema.py __tablename__ on 2026-09-27, law 1).
# prediction_history (2026-10-06): null until migrate_prediction_history.py ran (law 4).
CHAIN_COUNT_TABLES = ("matches", "predictions", "prediction_outcomes",
                      "odds_snapshots", "model_versions", "prediction_history")

# Env names whose VALUES are secrets and must never reach a receipt.
SECRET_ENV = ("API_FOOTBALL_KEY", "API_BASEBALL_KEY", "API_AMERICAN_FOOTBALL_KEY",
              "API_HOCKEY_KEY", "ODDS_API_KEY", "CFBD_API_KEY", "NTFY_TOPIC", "NTFY_CARD_TOPIC")
_KEYISH = re.compile(r"(?i)\b(api[_-]?key|token|secret|password|authorization)\b(\s*[=:]\s*)\S+")


def parse_env_file(path: Path) -> dict:
    """KEY=VALUE lines; '#' comments; surrounding quotes stripped. No expansion."""
    out = {}
    try:
        text = path.read_text()
    except (FileNotFoundError, PermissionError):
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip().removeprefix("export ").strip()
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        out[k] = v
    return out


def load_host_env() -> None:
    """Fill os.environ from host.env (units already get it via EnvironmentFile;
    this makes manual runs behave identically). Existing values win."""
    for k, v in parse_env_file(HOST_ENV).items():
        os.environ.setdefault(k, v)


def setting(name: str, default: str | None = None) -> str | None:
    """The process environment, else host.env (host), else the checkout's .env (laptop), else `default`.
    The environment always wins. ARCHITECT 2026-10-07 (addendum 2, item 8b): the laptop's .env carries the
    mirror's settings, so a documented line cannot be half-typed (the precedent is writer_of_record)."""
    v = os.environ.get(name)
    if v is None:
        v = parse_env_file(HOST_ENV).get(name)
    if v is None:
        v = _dotenv().get(name)
    return default if v is None else v


def receipts_path() -> Path:
    return Path(setting("SP_RECEIPTS") or REPO / "logs" / "receipts.jsonl")


def lock_path() -> Path:
    return Path(setting("SP_LOCK") or REPO / "logs" / "db.lock")


def host_name() -> str:
    return setting("SP_HOST_NAME") or socket.gethostname()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None = None) -> str:
    return (dt or utc_now()).strftime("%Y-%m-%dT%H:%M:%SZ")


def git_sha() -> str | None:
    try:
        return subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


# RELEASE MODEL (architect 2026-09-30): main = BETA, production = tagged
# releases only. A production tag is vMAJOR.MINOR.PATCH, nothing else.
RELEASE_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def release_key(tag: str) -> tuple[int, int, int] | None:
    m = RELEASE_TAG.match(tag or "")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def latest_release(tags: list[str]) -> str | None:
    """The highest vX.Y.Z among `tags` (numeric, not lexical: v1.10.0 > v1.9.0)."""
    rel = [t for t in tags if release_key(t)]
    return max(rel, key=release_key) if rel else None


_GIT_ERROR: dict = {"last": None}


def _git(*args: str) -> str | None:
    """git in REPO. `safe.directory` is passed for REPO only: the host checkout
    (/opt/sports-predictor) is installed by root and the units run as `sp`, and git
    refuses a repository owned by another user ("dubious ownership"), which left
    every receipt's release null (cutover-readiness (b), ARCHITECT 2026-10-06).
    The failure text is kept so a null release is never unexplained."""
    try:
        r = subprocess.run(["git", "-c", f"safe.directory={REPO}", "-C", str(REPO), *args],
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as e:
        _GIT_ERROR["last"] = f"git not runnable: {e}"[:200]
        return None
    if r.returncode != 0:
        _GIT_ERROR["last"] = ((r.stderr or "").strip().splitlines() or [f"git exit {r.returncode}"])[0][:200]
        return None
    return r.stdout.strip()


def running_release() -> str | None:
    """What this checkout is running, for every receipt line:
    'v1.0.0' when HEAD sits exactly on a release tag (production);
    'BETA main@<sha>' (or 'BETA <branch>@<sha>') on a branch;
    'UNTAGGED@<sha>' when detached off any release tag.
    None when git is unreadable (law 4: never a guessed tag)."""
    sha = _git("rev-parse", "--short", "HEAD")
    if not sha:
        return None
    tags = _git("tag", "--points-at", "HEAD")
    if tags is None:                # a FAILED lookup is unreadable, never "no tag" (Codex on #296)
        return None
    tag = latest_release(tags.split())
    if tag:
        return tag
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    if branch is None:
        return None
    return f"UNTAGGED@{sha}" if branch == "HEAD" else f"BETA {branch}@{sha}"


# WRITER OF RECORD (ARCHITECT-RULE 2026-10-01): the REAL flag, laptop|host,
# from host.env (host) or the checkout's .env (laptop). Anything else = None
# (unknown, labelled — law 4). Consumed by receipts and compare_exports; no
# behavior is gated on it yet. SP_PARALLEL_MODE stays the H0-16 quota mode.
WRITERS = ("laptop", "host")


def writer_of_record() -> str | None:
    v = (os.environ.get("SP_WRITER_OF_RECORD") or parse_env_file(HOST_ENV).get("SP_WRITER_OF_RECORD")
         or _dotenv().get("SP_WRITER_OF_RECORD") or "").strip()
    return v if v in WRITERS else None


# THE TIMER LISTS (ARCHITECT 2026-10-23, addendum 155 item 8(b)): hosting-h1.md T11 names every shipped timer on
# exactly one list; the host's /etc/sports-predictor/timers.enabled is the TIMERS it enabled (T11, "the list H2 steps
# 2 and 6 reuse"). tests/test_hosting_pack.py checks the lists, the shipped units and the Schedule table agree;
# sp_deploy's receipt names the shipped timers the host has not enabled. The third list, HELD_FOR_CUTOVER
# (sp-closing-watch.timer, addendum 45 P3), is retired: the timer moved to TIMERS at the cutover (ARCHITECT 2026-10-26,
# addendum 168 item 5). T11_LISTS is the lists this code expects; t11_lists reads the lists the file holds (#725).
T11_LISTS = ("TIMERS", "MLB_LAPTOP_ONLY")
TIMERS_ENABLED = Path("/etc/sports-predictor/timers.enabled")
_T11_HEAD = re.compile(r"^\*\*T11\.", re.M)
_RUNBOOK_STEP = re.compile(r"^\*\*T\d+\.", re.M)
_FENCED = re.compile(r"^```[^\n]*\n(.*?)^```", re.M | re.S)
_SHELL_LIST = re.compile(r'^([A-Z][A-Z0-9_]*)="', re.M)


def t11_lists(runbook: Path | None = None) -> dict[str, list[str]]:
    """The shell lists T11's enable block holds (hosting-h1.md, the first fenced block under "**T11."), by name in
    the file's order, each list's units in written order. ARCHITECT 2026-10-28 (#725): "the parser reads the T11
    blocks as the file now holds them". v1.6.0's parser looked up each name of a fixed tuple, so the deploy that ran
    it on v1.6.1's runbook (HELD_FOR_CUTOVER retired) raised ValueError and lost every list. Now a list T11_LISTS
    names and the block lacks is simply absent from the dict (a caller that needs one says so), and a list the
    block holds and the code never named is read too. No T11 block, no list in it, a list named twice, or a list
    whose closing quote is missing: ValueError, never a guessed list (law 4)."""
    rb = Path(runbook or REPO / "docs" / "specs" / "hosting-h1.md").read_text(encoding="utf-8")
    head = _T11_HEAD.search(rb)
    if not head:
        raise ValueError("hosting-h1.md holds no **T11. step")
    nxt = _RUNBOOK_STEP.search(rb, head.end())
    step = rb[head.end():nxt.start() if nxt else len(rb)]
    fence = _FENCED.search(step)
    if not fence:
        raise ValueError("hosting-h1.md T11 holds no closed fenced block")
    block = fence.group(1)
    out: dict[str, list[str]] = {}
    for m in _SHELL_LIST.finditer(block):
        name, rest = m.group(1), block[m.end():]
        if name in out:
            raise ValueError(f"hosting-h1.md T11 names {name} twice")
        units = rest[:rest.index('"')].split() if '"' in rest else None
        if units is None or any("=" in u for u in units):    # the quote closes on the next list's opening one
            raise ValueError(f"hosting-h1.md T11's {name} list is not closed")
        out[name] = units
    if not out:
        raise ValueError("hosting-h1.md T11's fenced block holds no list")
    return out


def shipped_timers(repo: Path | None = None) -> list[str]:
    """The timer units this checkout ships (deploy/hosting/systemd/*.timer), by file name, sorted."""
    return sorted(p.name for p in (Path(repo or REPO) / "deploy" / "hosting" / "systemd").glob("*.timer"))


# THE ACTIVE sp TIMERS, as systemd lists them (ARCHITECT 2026-10-13, addendum 57 item 8): one reader for the cutover's
# preflight (sp_cutover.active_sp_timers, which refuses on a failed read) and the deploy receipt (ARCHITECT
# 2026-10-26, addendum 168 item 2: sp_deploy names the active sp timers timers.enabled does not list).
ACTIVE_SP_TIMERS_ARGV = ("systemctl", "list-units", "--type=timer", "--state=active", "--no-legend", "--plain",
                         "sp-*")


def parse_active_sp_timers(out: str) -> list[str]:
    """The sp timers in an ACTIVE_SP_TIMERS_ARGV listing, whatever their names: one the list's name pattern cannot
    carry (sp-x@y.timer, an underscore) is still an active sp timer and is kept, never dropped. Sorted, unique."""
    units = (ln.split()[0] for ln in out.splitlines() if ln.split())
    return sorted({u for u in units if u.startswith("sp-") and u.endswith(".timer")})


def redact(line: str) -> str:
    for name in SECRET_ENV:
        val = os.environ.get(name) or _dotenv().get(name)
        if val and len(val) >= 6:
            line = line.replace(val, "[REDACTED]")
    return _KEYISH.sub(lambda m: m.group(1) + m.group(2) + "[REDACTED]", line)


_DOTENV_CACHE: dict | None = None


def _dotenv() -> dict:
    global _DOTENV_CACHE
    if _DOTENV_CACHE is None:
        _DOTENV_CACHE = parse_env_file(REPO / ".env")
    return _DOTENV_CACHE


def append_receipt(rec: dict) -> dict:
    """Append one JSON line (ts/host/release first — every receipt names the
    running tag, release model 2026-09-30). Append-only; never rewrites."""
    rel = running_release()
    line = {"ts": iso(), "host": host_name(), "release": rel,
            "writer_of_record": writer_of_record(), **rec}
    if line["release"] is None:                  # law 4: never a guessed tag, but always a stated reason
        # (the FINAL value: a caller's explicit release, e.g. sp_cutover's dry run, is not an error)
        line["release_error"] = _GIT_ERROR["last"] or "git unreadable"
    p = receipts_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
    return line


# Set in this process's environment while db_lock is held (#569, ARCHITECT 2026-10-21, addendum 153 item 2), as
# "<pid>:<lock file>": every step a holder runs inherits os.environ (sp_run's Popen, closing's runs), so a sync run as
# a step of a run that holds the lock knows it (the pid is an ancestor's) and never waits on it; a sync run by hand,
# or from the admin UI's job threads, takes the lock itself (sync_lock). The pid keeps a sibling THREAD of the holder
# from reading the marker as its own (Codex P1 on #650): in the holder's own process only the holding thread skips.
HELD_ENV = "SP_DB_LOCK_HELD"
_PROCESS_LOCK = threading.Lock()   # threads of one process wait on each other here, then on the flock
_HELD = threading.local()          # .depth > 0 in the thread holding db_lock


def lock_held_by_caller() -> bool:
    """True when this thread holds db_lock, or an ancestor process does (HELD_ENV names another pid)."""
    if getattr(_HELD, "depth", 0):
        return True
    v = os.environ.get(HELD_ENV) or ""
    return bool(v) and v.split(":", 1)[0] != str(os.getpid())


@contextmanager
def sync_lock(on_wait=None):
    """db_lock for a sync (#569): taken unless the caller already holds it (lock_held_by_caller), when it is a
    no-op; a second lock there would wait on its own run."""
    if lock_held_by_caller():
        yield
        return
    with db_lock(on_wait=on_wait):
        yield


@contextmanager
def db_lock(timeout_s: float = 3 * 3600, on_wait=None):
    """Exclusive flock so no two chains/backups write SQLite at once; threads of one process take it in turn. While
    held, HELD_ENV is "<pid>:<lock file>" in os.environ (restored after). `on_wait(path)` is called once when the lock
    is held elsewhere at the first try."""
    p = lock_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_s
    waited = False
    if not _PROCESS_LOCK.acquire(blocking=False):
        if on_wait is not None:
            on_wait(p)
        waited = True
        if not _PROCESS_LOCK.acquire(timeout=max(0.0, timeout_s)):
            raise TimeoutError(f"DB lock {p} not acquired in {timeout_s:.0f}s")
    try:
        with open(p, "a+") as f:
            while True:
                try:
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if not waited and on_wait is not None:
                        on_wait(p)
                    waited = True
                    if time.monotonic() > deadline:
                        raise TimeoutError(f"DB lock {p} not acquired in {timeout_s:.0f}s")
                    time.sleep(5)
            prev = os.environ.get(HELD_ENV)
            os.environ[HELD_ENV] = f"{os.getpid()}:{p}"
            _HELD.depth = getattr(_HELD, "depth", 0) + 1
            try:
                yield
            finally:
                _HELD.depth -= 1
                if prev is None:
                    os.environ.pop(HELD_ENV, None)
                else:
                    os.environ[HELD_ENV] = prev
                fcntl.flock(f, fcntl.LOCK_UN)
    finally:
        _PROCESS_LOCK.release()


def db_path() -> Path:
    """The live DB file from DATABASE_URL (env, else the checkout's .env,
    else the app default), relative paths resolved against the checkout —
    the units' WorkingDirectory, same as the app."""
    url = os.environ.get("DATABASE_URL") or _dotenv().get("DATABASE_URL") \
        or "sqlite:///./data/sports.db"
    if not url.startswith("sqlite:///"):
        raise ValueError(f"Not a SQLite URL: {url.split('://')[0]}://…")
    p = Path(url[len("sqlite:///"):])
    return p if p.is_absolute() else (REPO / p).resolve()


def refuse_under_data(target: Path) -> None:
    """Law 5: backups and packs never land under the checkout's data/."""
    data = (REPO / "data").resolve()
    t = target.resolve()
    if t == data or data in t.parents:
        raise SystemExit(f"✗ REFUSED: {t} is under {data} (law 5).")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ro_connect(p: Path) -> sqlite3.Connection:
    if not p.exists():
        raise FileNotFoundError(p)
    return sqlite3.connect(Path(p).resolve().as_uri() + "?mode=ro", uri=True, timeout=60)  # Windows/space-safe


def table_counts(p: Path, tables: tuple | None = None, copy: bool = False) -> dict:
    """Read-only SELECT COUNT(*). tables=None enumerates every user table from
    sqlite_master (law 1). An unreadable count is null, never 0 (law 4).
    copy=True: `p` is a COPY nobody writes, opened as copy_connect opens it (addendum 73 item 4, #532)."""
    out: dict = {}
    try:
        con = copy_connect(p) if copy else ro_connect(p)
    except (FileNotFoundError, sqlite3.Error):
        return {t: None for t in (tables or ())}
    try:
        if tables is None:
            tables = tuple(r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"))
        for t in tables:
            try:
                out[t] = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            except sqlite3.Error:
                out[t] = None
    finally:
        con.close()
    return out


def integrity(p: Path) -> str:
    con = ro_connect(p)
    try:
        rows = [r[0] for r in con.execute("PRAGMA integrity_check")]
    finally:
        con.close()
    return "ok" if rows == ["ok"] else "; ".join(rows[:5])


def copy_integrity(p: Path) -> str:
    """PRAGMA integrity_check on a COPY nobody writes (a pulled .backup), opened "?mode=ro&immutable=1".

    ARCHITECT 2026-10-14 (addendum 68 item 2, #517): "pull_backup's verify opens the pulled COPY with
    "?mode=ro&immutable=1" [...] the live DB is never opened immutable (#340 stands)." A WAL-mode copy with no
    -shm/-wal beside it cannot be opened mode=ro by the laptop's (macOS) SQLite, which has to create the -shm
    ("unable to open database file"); Linux's creates it and leaves the -shm and -wal behind. Immutable reads the
    file as it is and creates nothing beside it. Never for the live DB: ro_connect stays mode=ro (an immutable open
    skips SQLite's change detection, Codex on #340)."""
    con = copy_connect(p)
    try:
        rows = [r[0] for r in con.execute("PRAGMA integrity_check")]
    finally:
        con.close()
    return "ok" if rows == ["ok"] else "; ".join(rows[:5])


def copy_connect(p: Path) -> sqlite3.Connection:
    """An open of a COPY nobody writes, "?mode=ro&immutable=1": copy_integrity's open, closing.take_backup's open of
    its finished copy, and sp_migrate's reads of the pack's copy (ARCHITECT 2026-10-15, addendum 73 item 4, #532).
    It creates nothing beside the file. Never for the live DB (#340): ro_connect stays mode=ro."""
    if not p.exists():
        raise FileNotFoundError(p)
    return sqlite3.connect(Path(p).resolve().as_uri() + "?mode=ro&immutable=1", uri=True, timeout=60)
