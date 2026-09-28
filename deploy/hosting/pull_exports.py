#!/usr/bin/env python3
"""LAPTOP side, on demand or hourly at :10 (pull-exports lane, architect
2026-09-28): pull the host's exports/ over the tailnet into the laptop's
exports/host/. That is a SEPARATE folder, never the laptop's own exports/:
writer-of-record isolation through the parallel week (H0-17). Laptop pulls
host artifacts; push is H2.

    python deploy/hosting/pull_exports.py [--host ADDR] [--dest exports/host]
                                          [--transport auto|rsync|scp]

- The host address comes from --host, else SP_HOST_ADDR (env, then the
  laptop's .env). It is never hardcoded; unset means a clear refusal.
- Lists the host's exports/ over ssh (top-level files: name, mtime, size).
- Newest wins by mtime. A host file newer than the local copy, or missing
  locally, is pulled. The same mtime and size is unchanged. An OLDER host
  file never overwrites a newer local copy (counted as kept_local_newer).
- Transfer: rsync -t (fallback scp -p) into a staging dir under the
  destination. Each file is checked against the listed size, and only
  after EVERY file has landed are they renamed into place. An unreachable
  host or a failed transfer leaves no partial files; the exit is non-zero
  and the message is clear.
- Idempotent: a second run with nothing new pulls 0.
- Receipt (kind "pull_exports") per run: files pulled / unchanged, and the
  newest window_24h.json timestamp.
- Refuses a destination that is (or contains) the laptop's own exports/,
  and any destination under data/ (law 5).
Installed as an hourly launchd job at :10 by scripts/setup_export_pull.sh.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_common as c  # noqa: E402

REMOTE_DIR = "/opt/sports-predictor/exports"
SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=15"]
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")   # export names; nothing shell-active
STAGING = ".incoming"
CARD = "window_24h.json"
MTIME_TOL_S = 1.0          # scp/rsync -t keep whole-second mtimes on some filesystems


def host_addr(cli: str | None) -> str | None:
    return cli or os.environ.get("SP_HOST_ADDR") or c._dotenv().get("SP_HOST_ADDR") or None


def check_dest(dest: Path) -> None:
    """Isolation: never the laptop's own exports/ (or a parent of it), never data/."""
    c.refuse_under_data(dest)
    own = (c.REPO / "exports").resolve()
    d = dest.resolve()
    if d == own or own.is_relative_to(d):
        raise SystemExit(f"refusing --dest {dest}: that is the laptop's own exports/ "
                         "(writer of record); host copies go to exports/host/")


def parse_listing(text: str) -> tuple[dict, list[str]]:
    """`find -printf '%f\\t%T@\\t%s\\n'` lines -> {name: (mtime, size)}; unsafe names skipped."""
    files, skipped = {}, []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        name, mt, size = parts
        if not SAFE_NAME.match(name):
            skipped.append(name)
            continue
        files[name] = (float(mt), int(size))
    return files, skipped


def plan(remote: dict, dest: Path) -> tuple[list[str], list[str], list[str]]:
    """Newest wins by mtime -> (pull, unchanged, kept_local_newer)."""
    pull, same, newer = [], [], []
    for name, (mt, size) in sorted(remote.items()):
        p = dest / name
        if not p.is_file():
            pull.append(name)
            continue
        st = p.stat()
        if mt > st.st_mtime + MTIME_TOL_S:
            pull.append(name)
        elif mt < st.st_mtime - MTIME_TOL_S:
            newer.append(name)
        elif st.st_size == size:
            same.append(name)
        else:
            pull.append(name)          # same second, different bytes: take the host's
    return pull, same, newer


def transfer(names: list[str], target: str, remote_dir: str, staging: Path, transport: str) -> str:
    """Copy names into staging, mtimes preserved. Returns the transport used."""
    use_rsync = transport == "rsync" or (transport == "auto" and shutil.which("rsync"))
    why = ""
    if use_rsync:
        try:
            subprocess.run(["rsync", "-t", "--timeout=120", "--files-from=-",
                            "-e", "ssh " + " ".join(SSH_OPTS),
                            f"{target}:{remote_dir}/", str(staging) + "/"],
                           input="\n".join(names) + "\n", text=True, capture_output=True,
                           timeout=1800, check=True)
            return "rsync"
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            if transport == "rsync":
                raise RuntimeError(f"rsync failed: {_err(e)}") from None
            why = f"rsync failed ({_err(e)}); "   # kept: the fallback must not hide the cause
            for p in staging.iterdir():   # fall back cleanly: nothing half-copied survives
                p.unlink() if p.is_file() else shutil.rmtree(p)
    try:
        subprocess.run(["scp", "-p", "-q", *SSH_OPTS,
                        *[f"{target}:{remote_dir}/{n}" for n in names], str(staging) + "/"],
                       capture_output=True, text=True, timeout=1800, check=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        raise RuntimeError(f"{why}scp failed: {_err(e) if not isinstance(e, OSError) else e}") from None
    return "scp"


def _err(e) -> str:
    out = getattr(e, "stderr", None) or getattr(e, "output", None) or ""
    return (out.strip().splitlines() or [type(e).__name__])[-1]


def card_stamp(dest: Path) -> str | None:
    """The newest window_24h.json's own exported_at (else its mtime)."""
    p = dest / CARD
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text()).get("exported_at") or None
    except (OSError, ValueError, AttributeError):
        pass
    return datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pull the host's exports/ into exports/host/.")
    ap.add_argument("--host", help="tailnet address; default SP_HOST_ADDR from .env")
    ap.add_argument("--user", default="sp")
    ap.add_argument("--dest", type=Path, default=None, help="default <checkout>/exports/host")
    ap.add_argument("--remote-dir", default=os.environ.get("SP_HOST_EXPORTS") or REMOTE_DIR)
    ap.add_argument("--transport", choices=["auto", "rsync", "scp"], default="auto")
    a = ap.parse_args(argv)
    host = host_addr(a.host)
    if not host:
        print("✗ pull-exports: no host address — set SP_HOST_ADDR in .env (see .env.example) "
              "or pass --host", file=sys.stderr)
        return 2
    dest = (a.dest or c.REPO / "exports" / "host").expanduser()
    check_dest(dest)
    dest.mkdir(parents=True, exist_ok=True)
    staging = dest / STAGING
    rec = {"kind": "pull_exports", "exit": 1, "from": host, "dest": str(dest),
           "pulled": 0, "unchanged": 0, "kept_local_newer": 0, "transport": None}
    target = f"{a.user}@{host}"
    try:
        shutil.rmtree(staging, ignore_errors=True)       # a crashed earlier run's leftovers
        ls = subprocess.run(["ssh", *SSH_OPTS, target,
                             f"find {a.remote_dir} -maxdepth 1 -type f -printf '%f\\t%T@\\t%s\\n'"],
                            capture_output=True, text=True, timeout=60)
        if ls.returncode != 0:
            raise RuntimeError(f"host unreachable or listing failed (ssh exit {ls.returncode}): "
                               f"{_err(ls)}")
        remote, skipped = parse_listing(ls.stdout)
        pull, same, newer = plan(remote, dest)
        if pull:
            staging.mkdir()
            rec["transport"] = transfer(pull, target, a.remote_dir, staging, a.transport)
            for n in pull:                     # verify EVERYTHING before placing ANYTHING
                p = staging / n
                if not p.is_file() or p.stat().st_size != remote[n][1]:
                    raise RuntimeError(f"{n}: incomplete transfer "
                                       f"({p.stat().st_size if p.is_file() else 'missing'} of {remote[n][1]} bytes)")
            for n in pull:
                os.replace(staging / n, dest / n)
        rec.update(exit=0, pulled=len(pull), unchanged=len(same), kept_local_newer=len(newer),
                   files=pull[:50], skipped_names=skipped[:20])
    except Exception as e:  # receipt first, then fail loudly
        rec["error"] = c.redact(f"{type(e).__name__}: {e}")[:300]
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    rec["window_24h"] = card_stamp(dest)
    c.append_receipt(rec)
    if rec["exit"] == 0:
        print(f"✓ pull-exports from {host}: pulled {rec['pulled']} · unchanged {rec['unchanged']}"
              + (f" · kept {rec['kept_local_newer']} newer local" if rec["kept_local_newer"] else "")
              + f" · newest {CARD} {rec['window_24h'] or 'none'}"
              + (f" (via {rec['transport']})" if rec["transport"] else "") + f" → {dest}")
    else:
        print(f"✗ pull-exports from {host}: {rec['error']} — nothing placed; "
              f"exports/host/ unchanged (newest {CARD} {rec['window_24h'] or 'none'})", file=sys.stderr)
    return rec["exit"]


if __name__ == "__main__":
    sys.exit(main())
