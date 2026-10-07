#!/usr/bin/env python3
"""
EXPORTS MIRROR (F2.5, ARCHITECT 2026-10-03): "a private repo
Sports-Predictor-exports; the HOST pushes exports/ after every chain step
(push-only deploy key, generated on the host; Anthony adds the public half in
the repo's deploy keys). Layout: host/<date>/<file>, plus
host/latest/<kind>.json (newest per kind, rewritten each push). Retention 14
days of dated folders; weekly history squash so the repo stays small. Files
stay on the host too. (2) The LAPTOP pushes the same way to laptop/ (writer of
record) at the end of the morning chain — then compare_exports runs as a
GitHub Action on push and posts the DIVERGENT/clean verdict as a commit
status; pull_exports over Tailscale becomes optional."

    exports_mirror.py push   [--role host|laptop] [--exports DIR] [--label TEXT]
    exports_mirror.py squash                      # weekly: one orphan commit, force-pushed
    exports_mirror.py keygen [--key PATH]         # host: make the deploy key, print the PUBLIC half

Config (host.env on the host; the checkout's .env on the laptop; the process environment wins. Read through
sp_common.setting, ARCHITECT 2026-10-07 addendum 2 item 8b):
  SP_EXPORTS_MIRROR_REMOTE  git@github.com:anthonyevans29/Sports-Predictor-exports.git
                            (unset = mirror disabled: `push` prints so and exits 0)
  SP_EXPORTS_MIRROR_KEY     the deploy key's private half. Unset: /etc/sports-predictor/exports_deploy_key
                            when that file exists (installed by root), else ~/.ssh/sp_exports_deploy_key
                            of the running user (sp cannot write /etc/sports-predictor; keygen --key PATH).
                            An SSH remote whose key file does not exist is REFUSED, never pushed without a
                            key (ARCHITECT 2026-10-07, addendum 4 F: a KEY naming a missing file ran git keyless)
  SP_EXPORTS_MIRROR_DIR     the working clone (default <repo>/logs/exports-mirror)
  SP_EXPORTS_MIRROR_ROLE    host | laptop (default host)

Layout written by a push (role = host or laptop):
  <role>/<YYYY-MM-DD>/<file>   every top-level exports/*.json|*.md written in the
                               last RETENTION_DAYS (the date is the file's UTC mtime)
  <role>/latest/<kind>.json    the newest file per kind (kind = the name with its
                               date/time stamp removed), rewritten each push
  tools/compare_exports.py     + .github/workflows/compare.yml (the verdict Action)
Dated folders older than RETENTION_DAYS are deleted. COPIES only: exports/ is
never modified. Subdirectories of exports/ (raw provider caches) are not mirrored.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import sp_common as c  # noqa: E402  (setting(): environment, host.env, the checkout's .env)
RETENTION_DAYS = 14
BRANCH = "main"
SUFFIXES = (".json", ".md")
STAMP = re.compile(r"_?\d{4}-\d{2}-\d{2}(?:[T_]\d{2}:?\d{2}(?::?\d{2})?Z?)?")
WORKFLOW_SRC = REPO / "deploy" / "exports-mirror" / "compare.yml"
ETC_KEY = Path("/etc/sports-predictor/exports_deploy_key")


def key_path() -> Path:
    """The deploy key push and keygen both use: SP_EXPORTS_MIRROR_KEY, else an installed
    /etc/sports-predictor key, else ~/.ssh/sp_exports_deploy_key (writable by the service user)."""
    env = c.setting("SP_EXPORTS_MIRROR_KEY")
    if env:
        return Path(env).expanduser()
    if ETC_KEY.is_file():
        return ETC_KEY
    return Path(os.path.expanduser("~")) / ".ssh" / "sp_exports_deploy_key"


def ssh_remote(remote: str) -> bool:
    """git@host:path or ssh://… (an HTTPS remote never uses the deploy key)."""
    return remote.startswith("ssh://") or bool(re.match(r"^[\w.-]+@[\w.-]+:", remote))


def key_refusal(remote: str) -> str | None:
    """None when the push may run; else the stated refusal (ARCHITECT 2026-10-07, addendum 4 F)."""
    if not ssh_remote(remote):
        return None
    k = key_path()
    if k.is_file():
        return None
    named = c.setting("SP_EXPORTS_MIRROR_KEY")
    return (f"REFUSED: the deploy key {k} does not exist"
            + (" (SP_EXPORTS_MIRROR_KEY names it)" if named else " (the default path; SP_EXPORTS_MIRROR_KEY unset)")
            + f" and the remote {remote} is SSH: git would run with no key and be refused. Fix the key path "
            "(exports_mirror.py keygen prints the default) — the mirror never falls back silently.")


def kind_of(name: str) -> str:
    """fixtures_NCAA_2026-10-03.json -> fixtures_NCAA; unl_shadow_2026-10-03_1200 -> unl_shadow;
    window_24h.json -> window_24h. Every date range piece goes (a_to_b)."""
    stem = name.rsplit(".", 1)[0]
    stem = STAMP.sub("", stem).replace("_to", "")
    return re.sub(r"__+", "_", stem).strip("_") or stem


def plan(files: list[tuple[str, float]], role: str, today: date) -> dict:
    """files = [(name, mtime_epoch)] at the top of exports/. Returns
    {"dated": {dest: name}, "latest": {dest: name}} for the retention window."""
    lo = today - timedelta(days=RETENTION_DAYS - 1)
    dated, newest = {}, {}
    for name, mt in files:
        d = datetime.fromtimestamp(mt, tz=timezone.utc).date()
        if d < lo or not name.endswith(SUFFIXES):
            continue
        dated[f"{role}/{d.isoformat()}/{name}"] = name
        k = kind_of(name)
        if k not in newest or mt > newest[k][1]:
            newest[k] = (name, mt)
    latest = {f"{role}/latest/{k}{Path(n).suffix}": n for k, (n, _) in newest.items()}
    return {"dated": dated, "latest": latest}


def expired(role_dir: Path, today: date) -> list[Path]:
    lo = today - timedelta(days=RETENTION_DAYS - 1)
    out = []
    for p in role_dir.glob("*") if role_dir.is_dir() else []:
        try:
            if p.is_dir() and date.fromisoformat(p.name) < lo:
                out.append(p)
        except ValueError:
            continue
    return out


def _git(clone: Path, *args, check=True, capture=True):
    env = dict(os.environ)
    key = str(key_path())
    if os.path.isfile(key):
        env["GIT_SSH_COMMAND"] = f"ssh -i {key} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
    return subprocess.run(["git", "-C", str(clone), *args], check=check, env=env, text=True,
                          capture_output=capture)


def _ensure_clone(clone: Path, remote: str) -> None:
    if not (clone / ".git").is_dir():
        clone.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", "-b", BRANCH, str(clone)], check=True)
        _git(clone, "remote", "add", "origin", remote)
        _git(clone, "config", "user.name", c.setting("SP_EXPORTS_MIRROR_AUTHOR", "sp-exports-mirror"))
        _git(clone, "config", "user.email", "sp-exports-mirror@localhost")
    else:                                   # host.env's remote may have changed since the clone was made
        _git(clone, "remote", "set-url", "origin", remote, check=False)


def _sync_to_remote(clone: Path) -> None:
    """Start from the remote's tip (the other writer's pushes kept); a fresh repo has no tip."""
    _git(clone, "fetch", "-q", "origin", check=False)
    if _git(clone, "rev-parse", "--verify", "-q", f"origin/{BRANCH}", check=False).returncode == 0:
        _git(clone, "checkout", "-q", "-B", BRANCH, f"origin/{BRANCH}")
        _git(clone, "reset", "-q", "--hard", f"origin/{BRANCH}")


def _unpushed(clone: Path) -> int:
    """Local commits the remote does not have (all of them when the remote has no branch yet)."""
    if _git(clone, "rev-parse", "--verify", "-q", "HEAD", check=False).returncode != 0:
        return 0                            # unborn branch: nothing committed locally
    if _git(clone, "rev-parse", "--verify", "-q", f"origin/{BRANCH}", check=False).returncode != 0:
        return int(_git(clone, "rev-list", "--count", "HEAD").stdout.strip() or 0)
    return int(_git(clone, "rev-list", "--count", f"origin/{BRANCH}..HEAD").stdout.strip() or 0)


def push(role: str, exports: Path, label: str, remote: str, clone: Path, today: date | None = None,
         attempts: int = 3) -> dict:
    today = today or datetime.now(timezone.utc).date()
    files = [(p.name, p.stat().st_mtime) for p in exports.iterdir() if p.is_file()] if exports.is_dir() else []
    _ensure_clone(clone, remote)
    for attempt in range(1, attempts + 1):
        _sync_to_remote(clone)
        pl = plan(files, role, today)
        copied = 0
        for dest, name in {**pl["dated"], **pl["latest"]}.items():
            src, dst = exports / name, clone / dest
            if dst.exists() and dst.read_bytes() == src.read_bytes():
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1
        latest_dir = clone / role / "latest"                      # rewritten each push
        for p in latest_dir.glob("*") if latest_dir.is_dir() else []:
            if f"{role}/latest/{p.name}" not in pl["latest"]:
                p.unlink()
        pruned = [p.name for p in expired(clone / role, today)]
        for p in expired(clone / role, today):
            shutil.rmtree(p)
        for src, dest in ((HERE / "compare_exports.py", clone / "tools" / "compare_exports.py"),
                          (WORKFLOW_SRC, clone / ".github" / "workflows" / "compare.yml")):
            if src.exists() and (not dest.exists() or dest.read_bytes() != src.read_bytes()):
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
        _git(clone, "add", "-A")
        staged = _git(clone, "diff", "--cached", "--quiet", check=False).returncode != 0
        # ARCHITECT 2026-10-03 (host first push): "changed" is judged against the REMOTE's tip, not
        # the local HEAD — a commit left by a push that failed (remote set before the key worked)
        # is not on an empty remote, and must not read as "nothing changed".
        unpushed = _unpushed(clone)
        if not staged and not unpushed:
            return {"role": role, "pushed": False, "copied": 0, "pruned": pruned, "why": "nothing changed"}
        if staged:
            _git(clone, "commit", "-q", "-m", f"{role}: {label} · {copied} file(s) · pruned {len(pruned)}")
        r = _git(clone, "push", "-q", "origin", f"HEAD:{BRANCH}", check=False)
        if r.returncode == 0:
            sha = _git(clone, "rev-parse", "HEAD").stdout.strip()
            return {"role": role, "pushed": True, "copied": copied, "pruned": pruned, "sha": sha,
                    "attempt": attempt, "unpushed_before": unpushed}
    return {"role": role, "pushed": False, "copied": copied, "pruned": pruned,
            "why": f"push rejected {attempts}x: {(r.stderr or '').strip()[-200:]}"}


def squash(remote: str, clone: Path) -> dict:
    """Weekly: the current tree as ONE orphan commit, force-pushed (the repo stays small)."""
    _ensure_clone(clone, remote)
    _sync_to_remote(clone)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    _git(clone, "checkout", "-q", "--orphan", "squash-tmp")
    _git(clone, "add", "-A")
    _git(clone, "commit", "-q", "-m", f"weekly squash {stamp} (history before this date dropped; files kept)")
    _git(clone, "branch", "-q", "-M", BRANCH)
    r = _git(clone, "push", "-q", "--force", "origin", f"{BRANCH}:{BRANCH}", check=False)
    return {"squashed": r.returncode == 0, "why": (r.stderr or "").strip()[-200:] if r.returncode else None}


def keygen(key: str) -> int:
    parent = Path(key).parent
    if not os.path.exists(key) and not os.access(parent if parent.exists() else parent.parent, os.W_OK):
        print(f"REFUSED: {parent} is not writable by {os.environ.get('USER') or 'this user'}. Either\n"
              f"  (a) generate it where you can write and point the mirror at it:\n"
              f"        exports_mirror.py keygen --key ~/.ssh/sp_exports_deploy_key\n"
              f"        then set SP_EXPORTS_MIRROR_KEY=~/.ssh/sp_exports_deploy_key in host.env\n"
              f"        (unset, the mirror already falls back to that path), or\n"
              f"  (b) the root step, keeping {key}:\n"
              f"        sudo ssh-keygen -q -t ed25519 -N '' -C 'sp-exports-mirror (push-only)' -f {key}\n"
              f"        sudo chown sp:sp {key} {key}.pub && sudo chmod 600 {key}")
        return 2
    if os.path.exists(key):
        print(f"exists: {key} (not regenerated). PUBLIC half:")
    else:
        Path(key).parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "sp-exports-mirror (push-only)",
                        "-f", key], check=True)
        os.chmod(key, 0o600)
        print(f"created {key}. Add this PUBLIC half as a deploy key WITH write access on "
              "Sports-Predictor-exports (Settings → Deploy keys):")
    print(Path(key + ".pub").read_text().strip())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="exports mirror (F2.5)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("push")
    p.add_argument("--role", default=c.setting("SP_EXPORTS_MIRROR_ROLE", "host"), choices=("host", "laptop"))
    p.add_argument("--exports", default=str(REPO / "exports"))
    p.add_argument("--label", default="push")
    sub.add_parser("squash")
    k = sub.add_parser("keygen")
    k.add_argument("--key", default=None, help="default: SP_EXPORTS_MIRROR_KEY, an installed "
                   "/etc/sports-predictor key, else ~/.ssh/sp_exports_deploy_key")
    a = ap.parse_args(argv)
    if a.cmd == "keygen":
        return keygen(str(Path(a.key).expanduser()) if a.key else str(key_path()))
    remote = c.setting("SP_EXPORTS_MIRROR_REMOTE")
    if not remote:
        print("exports mirror disabled (SP_EXPORTS_MIRROR_REMOTE unset in the environment, host.env and .env)")
        return 0
    why = key_refusal(remote)
    if why:
        print(why)
        return 2
    clone = Path(c.setting("SP_EXPORTS_MIRROR_DIR") or REPO / "logs" / "exports-mirror")
    if a.cmd == "squash":
        r = squash(remote, clone)
        print(f"EXPORTS-MIRROR squash: {r}")
        return 0 if r["squashed"] else 1
    r = push(a.role, Path(a.exports), a.label, remote, clone)
    print(f"EXPORTS-MIRROR {r['role']}: " + (f"pushed {r['copied']} file(s) @ {r['sha'][:8]} (attempt {r['attempt']})"
                                           + (f" · incl. {r['unpushed_before']} earlier unpushed commit(s)"
                                              if r.get("unpushed_before") else "")
                                           if r["pushed"] else f"not pushed — {r['why']}")
          + (f" · pruned {r['pruned']}" if r["pruned"] else ""))
    return 0 if (r["pushed"] or r.get("why") == "nothing changed") else 1


if __name__ == "__main__":
    sys.exit(main())
