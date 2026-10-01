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
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HOST_ENV = Path(os.environ.get("SP_HOST_ENV", "/etc/sports-predictor/host.env"))

# Tables whose counts ride on every chain receipt (names verified against
# src/db/schema.py __tablename__ on 2026-09-27, law 1).
CHAIN_COUNT_TABLES = ("matches", "predictions", "prediction_outcomes",
                      "odds_snapshots", "model_versions")

# Env names whose VALUES are secrets and must never reach a receipt.
SECRET_ENV = ("API_FOOTBALL_KEY", "API_BASEBALL_KEY", "API_AMERICAN_FOOTBALL_KEY",
              "API_HOCKEY_KEY", "ODDS_API_KEY", "NTFY_TOPIC", "NTFY_CARD_TOPIC")
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
    return os.environ.get(name, default)


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


def _git(*args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def running_release() -> str | None:
    """What this checkout is running, for every receipt line:
    'v1.0.0' when HEAD sits exactly on a release tag (production);
    'BETA main@<sha>' (or 'BETA <branch>@<sha>') on a branch;
    'UNTAGGED@<sha>' when detached off any release tag.
    None when git is unreadable (law 4: never a guessed tag)."""
    sha = _git("rev-parse", "--short", "HEAD")
    if not sha:
        return None
    tag = latest_release((_git("tag", "--points-at", "HEAD") or "").split())
    if tag:
        return tag
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    return f"UNTAGGED@{sha}" if branch in (None, "HEAD") else f"BETA {branch}@{sha}"


# WRITER OF RECORD (ARCHITECT-RULE 2026-10-01): the REAL flag, laptop|host,
# from host.env (host) or the checkout's .env (laptop). Anything else = None
# (unknown, labelled — law 4). Consumed by receipts and compare_exports; no
# behavior is gated on it yet. SP_PARALLEL_MODE stays the H0-16 quota mode.
WRITERS = ("laptop", "host")


def writer_of_record() -> str | None:
    v = (os.environ.get("SP_WRITER_OF_RECORD") or parse_env_file(HOST_ENV).get("SP_WRITER_OF_RECORD")
         or _dotenv().get("SP_WRITER_OF_RECORD") or "").strip()
    return v if v in WRITERS else None


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
    line = {"ts": iso(), "host": host_name(), "release": running_release(),
            "writer_of_record": writer_of_record(), **rec}
    p = receipts_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
    return line


@contextmanager
def db_lock(timeout_s: float = 3 * 3600):
    """Exclusive flock so no two chains/backups write SQLite at once."""
    p = lock_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a+") as f:
        deadline = time.monotonic() + timeout_s
        while True:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() > deadline:
                    raise TimeoutError(f"DB lock {p} not acquired in {timeout_s:.0f}s")
                time.sleep(5)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


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
    return sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=60)


def table_counts(p: Path, tables: tuple | None = None) -> dict:
    """Read-only SELECT COUNT(*). tables=None enumerates every user table from
    sqlite_master (law 1). An unreadable count is null, never 0 (law 4)."""
    out: dict = {}
    try:
        con = ro_connect(p)
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
