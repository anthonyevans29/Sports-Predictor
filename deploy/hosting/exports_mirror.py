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
The day's coverage file (`coverage --json`, exports/coverage_<date>.json; ARCHITECT 2026-10-18, addendum 125 item 2(a):
"the mirror carries it (laptop/latest/coverage.json, host/latest after the cutover)") is a kind like any other:
<role>/<date>/coverage_<date>.json and <role>/latest/coverage.json, by the rule above (tests/test_exports_mirror.py).
Dated folders older than RETENTION_DAYS are deleted. COPIES only: exports/ is
never modified. Subdirectories of exports/ (raw provider caches) are not mirrored, but ONE: the kept subtree below.

THE KEPT SUBTREE (ARCHITECT 2026-11-04, addendum 250 item 4, the bulletins lane, #826): "exports_mirror.py gains ONE
kept subtree: `exports/bulletins/**` is copied verbatim to `<role>/bulletins/**` (suffixes .md and .png there; the
top-level rule is unchanged), NEVER pruned by RETENTION_DAYS (the dated-folder rule applies to `<role>/<date>/` only;
the weekly squash keeps files, as it does today), and NO JSON is ever written under it, so the compare's `*.json`
Action glob never sees a bulletin and the compare is untouched (no new kind, no new mask, kind_of unchanged)."
  <role>/bulletins/<rel>       every exports/bulletins/<rel> whose name ends .md or .png, at its own relative path
                               (<FAMILY>/<date>/ and <FAMILY>/weeks/ kept as they are), whatever its mtime
  Never pruned: expired() reads only <role>/<YYYY-MM-DD>/ folders, so <role>/bulletins/ (and any dated folder
  nested in it) is never deleted; a bulletin removed from exports/ stays in the mirror, as a dated copy whose
  source is gone stays until its folder expires (the push copies, it never deletes a copy for a missing source).
  Never copied, and RECEIPTED (law 2: the push's result carries `skipped`, its console line the count by reason):
  any other suffix (a .json above all: no JSON is ever written under the subtree by the mirror), a symlink (file
  or folder, the subtree's own root included: never followed, in or out of the subtree), anything that is not a
  regular file, a path with a `.git` component (git cannot carry it), a folder that cannot be read, a file that
  cannot be read when the push copies it (no read permission, or gone since the plan: `unreadable: <error>`), and a
  path git itself refuses (`git refused the path`: git decides, by `add --ignore-errors`, not a list kept here;
  with core.protectNTFS, its default, that is `.git`'s other spellings GIT~1, `.git.`, `.git `). The DESTINATION is
  never followed either (Codex on #847): the mirror's own tree may already track a symlink, so before a bulletin is
  read back or written, every component from <role>/ down to the file is lstat'ed, and a symlink there (the role
  folder, bulletins/, a family or date folder, or the file itself: `destination path has a symlink`), a component
  above the file that is not a folder (`destination path has a non-folder`) or a file that is not a regular file
  (`destination not a regular file`) skips that bulletin, receipted; what the mirror tracks there is left as it is
  (never unlinked, never written through), the missing folders are made only below real ones, and git's own check
  never walks a <role>/ or <role>/bulletins/ that is not a real folder. A submodule the index holds on the path
  (a gitlink checks out as an empty real folder) is refused too (`destination path has a submodule`), and git's
  check never walks into one. One bad bulletin
  is local to that file: the copy is removed from the working clone, so it never fails the whole-tree add nor
  jams a later push, and the top-level files and the other bulletins still go.
  Absent exports/bulletins/: nothing happens.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import stat as st
import subprocess
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import sp_common as c  # noqa: E402  (setting(): environment, host.env, the checkout's .env)
RETENTION_DAYS = 14
BRANCH = "main"
SUFFIXES = (".json", ".md")
BULLETINS = "bulletins"                     # addendum 250 item 4: exports/bulletins/** -> <role>/bulletins/**
BULLETIN_SUFFIXES = (".md", ".png")         # the only suffixes ever written under <role>/bulletins/ (never .json)
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


REFUSE_SSH = "sh -c 'echo \"REFUSED: SSH transport with no deploy key (exports_mirror)\" >&2; exit 1' --"


def ssh_remote(remote: str) -> bool:
    """git's own rule (Codex on #335): a URL ("scheme://") is SSH when its scheme names ssh (ssh://, git+ssh://,
    ssh+git://); otherwise a remote is scp-like, so SSH, when a ':' comes before any '/' (git@host:p, u@h:p,
    host:p, [::1]:p). A local path (/x, ./x, ../x, ~/x) is not. An unsure call errs towards SSH, so a missing key
    is refused rather than pushed keyless."""
    r = remote.strip()
    m = re.match(r"^([A-Za-z][A-Za-z0-9+.-]*)://", r)
    if m:
        return "ssh" in m.group(1).lower().split("+")
    if r.startswith(("/", "./", "../", "~")):
        return False
    colon, slash = r.find(":"), r.find("/")
    return colon > 0 and (slash == -1 or colon < slash)


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


def _shown(rel: str) -> str:
    """A path as text that always prints (a name that is not UTF-8 shows its bytes escaped)."""
    return os.fsencode(rel).decode("utf-8", "backslashreplace")


def bulletin_plan(exports: Path, role: str) -> dict:
    """THE KEPT SUBTREE (addendum 250 item 4). Returns {"kept": {dest: src Path}, "skipped": [(rel, why)]}:
    dest = <role>/bulletins/<rel> for every regular .md / .png file under exports/bulletins/, at its own relative
    path, whatever its date (no retention window here). Never followed: a symlink anywhere (the subtree's root
    included). Skipped with the reason, never copied: any other suffix (a .json above all), a symlink, a non-regular
    file, a `.git` path component, an unreadable folder. Absent subtree: {"kept": {}, "skipped": []}. The push adds
    two reasons of its own, per file: a kept file it cannot read, and a path git refuses (_refused_by_git)."""
    root = exports / BULLETINS
    kept: dict[str, Path] = {}
    skipped: list[tuple[str, str]] = []
    if root.is_symlink():
        return {"kept": kept, "skipped": [(BULLETINS, "symlink: not followed")]}
    if not root.is_dir():
        return {"kept": kept, "skipped": skipped}

    def unreadable(e: OSError) -> None:
        try:
            where = Path(e.filename).relative_to(exports).as_posix()
        except (TypeError, ValueError):
            where = BULLETINS
        skipped.append((where, f"unreadable folder: {e.__class__.__name__}"))

    for dirpath, dirnames, filenames in os.walk(root, onerror=unreadable, followlinks=False):
        here = Path(dirpath)
        keep_dirs = []
        for d in sorted(dirnames):
            rel = (here / d).relative_to(exports).as_posix()
            if (here / d).is_symlink():
                skipped.append((rel, "symlink: not followed"))
            elif d.lower() == ".git":                  # git refuses .git (and .GIT) as a path component
                skipped.append((rel, "a .git path: git cannot carry it"))
            else:
                keep_dirs.append(d)
        dirnames[:] = keep_dirs                       # os.walk descends only into these
        for f in sorted(filenames):
            p = here / f
            rel = p.relative_to(exports).as_posix()
            try:
                mode = p.lstat().st_mode
            except OSError as e:
                skipped.append((rel, f"unreadable: {e.__class__.__name__}"))
                continue
            if st.S_ISLNK(mode):
                skipped.append((rel, "symlink: not followed"))
            elif not st.S_ISREG(mode):
                skipped.append((rel, "not a regular file"))
            elif not f.endswith(BULLETIN_SUFFIXES):
                skipped.append((rel, "suffix: not .md or .png"))
            else:
                kept[f"{role}/{rel}"] = p
    return {"kept": kept, "skipped": skipped}


def skipped_line(skipped: list[tuple[str, str]]) -> str:
    """The console's count by reason: "bulletins: 2 skipped (suffix: not .md or .png 1 · symlink: not followed 1)"."""
    by: dict[str, int] = {}
    for _, why in skipped:
        by[why] = by.get(why, 0) + 1
    return f"bulletins: {len(skipped)} skipped (" + " · ".join(f"{w} {n}" for w, n in by.items()) + ")"


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


def _git(clone: Path, *args, check=True, capture=True, text=True):
    env = dict(os.environ)
    key = str(key_path())
    if os.path.isfile(key):
        env["GIT_SSH_COMMAND"] = f"ssh -i {key} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
    else:
        # Codex on #335: a url.<base>.insteadOf / pushInsteadOf rewrite can turn an HTTPS remote into SSH at push
        # time, past ssh_remote(). With no key file, any SSH transport git starts is REFUSED here, so a push can
        # never run on an agent or default identity; HTTPS is unaffected.
        env["GIT_SSH_COMMAND"] = REFUSE_SSH
    return subprocess.run(["git", "-C", str(clone), *args], check=check, env=env, text=text,
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


def _gitlinks(clone: Path, role: str) -> frozenset[str]:
    """The submodule entries (gitlinks, mode 160000) the clone's index holds at or under <role>/, as NFC paths: git
    checks one out as an empty REAL folder, so an lstat never sees it (review of #847's round-1 fix)."""
    out = _git(clone, "ls-files", "-s", "-z", "--", role, text=False).stdout
    return frozenset(unicodedata.normalize("NFC", os.fsdecode(e.split(b"\t", 1)[1]))
                     for e in out.split(b"\0") if e.startswith(b"160000 ") and b"\t" in e)


def _dest_refusal(clone: Path, dest: str, gitlinks: frozenset[str] = frozenset()) -> str | None:
    """None when <clone>/<dest> may be read and written as a plain file; else why not (Codex on #847). Every component
    from <role>/ down to the file is lstat'ed, never followed: a symlink anywhere on the path (the mirror's own tree
    may track one, and a relative or absolute link would carry the write out of the clone), a component above the
    file that is not a folder, or a file that is not a regular file is refused. A component the index holds as a
    submodule (one of `gitlinks`, from _gitlinks) is refused before its lstat: its checkout is an empty real folder,
    and a write into it is one git never carries. A component that does not exist ends the walk: everything below
    it is made by mkdir as real folders under real folders."""
    parts = Path(dest).parts
    p = clone
    for i, part in enumerate(parts):
        p = p / part
        if unicodedata.normalize("NFC", "/".join(parts[:i + 1])) in gitlinks:
            return "destination path has a submodule"
        try:
            mode = p.lstat().st_mode
        except FileNotFoundError:
            return None
        except OSError as e:
            return f"destination unreadable: {e.__class__.__name__}"
        if st.S_ISLNK(mode):
            return "destination path has a symlink"
        if i < len(parts) - 1 and not st.S_ISDIR(mode):
            return "destination path has a non-folder"
        if i == len(parts) - 1 and not st.S_ISREG(mode):
            return "destination not a regular file"
    return None


def _refused_by_git(clone: Path, role: str, gitlinks: frozenset[str] = frozenset()) -> list[str]:
    """Git decides which paths under <role>/bulletins/ it carries (review of the kept subtree's PR): `add
    --ignore-errors` stages every path there git accepts and refuses the rest (with core.protectNTFS, git's default,
    `.git`'s other spellings GIT~1, `.git.` and `.git ` among them), so a file still on disk there and not in the index
    afterwards is one git refused. Each is removed from the working clone, so the whole-tree `add -A` never fails on
    it and it never jams a later push (a reset leaves untracked files in place). Returns their paths under <role>/
    (bulletins/<rel>, the plan's form). Bytes throughout: a name that is not UTF-8 never breaks the read. Names are
    compared in NFC on both sides, so a git that precomposes Unicode (macOS's default) never reads a decomposed
    name on disk as refused. Never walked unless <role>/ and <role>/bulletins/ are both real folders and neither is a
    submodule (Codex on #847: a tracked symlink there would carry the walk, and its unlink, out of the clone; review of
    its fix: a pathspec inside a submodule makes git's add exit 128 and abort the push). The walk never enters a
    submodule's folder, and only the folders a refused file's unlink emptied are removed (deepest first, never
    <role>/bulletins/ itself), so a tracked submodule's empty checkout folder is never deleted (its deletion would be
    staged by the whole-tree add)."""
    sub = clone / role / BULLETINS
    if {role, f"{role}/{BULLETINS}"} & gitlinks:
        return []
    for p in (clone / role, sub):
        try:
            if not st.S_ISDIR(p.lstat().st_mode):
                return []
        except OSError:
            return []
    r = _git(clone, "add", "--ignore-errors", "-A", "--", f"{role}/{BULLETINS}", check=False, text=False)
    if r.returncode not in (0, 1):                  # 1 = some path refused; anything else is not a path's fault
        raise subprocess.CalledProcessError(r.returncode, r.args, r.stdout, r.stderr)
    out = _git(clone, "ls-files", "-z", "--", f"{role}/{BULLETINS}", text=False).stdout
    indexed = {unicodedata.normalize("NFC", os.fsdecode(p)) for p in out.split(b"\0") if p}
    refused, emptied = [], set()
    for dirpath, dirnames, filenames in os.walk(sub):
        here = Path(dirpath)
        dirnames[:] = [d for d in dirnames                 # never into a submodule's checkout folder
                       if unicodedata.normalize("NFC", (here / d).relative_to(clone).as_posix()) not in gitlinks]
        for f in filenames:
            p = here / f
            rel = p.relative_to(clone).as_posix()
            if unicodedata.normalize("NFC", rel) not in indexed:
                p.unlink()
                refused.append(rel[len(role) + 1:])
                emptied.add(here)
    for d in sorted(emptied, key=lambda q: len(q.parts), reverse=True):
        while d != sub and d.is_dir() and not os.listdir(d):
            os.rmdir(d)                                   # the refused file's now-empty folder, and its emptied parents
            d = d.parent
    return sorted(refused)


def push(role: str, exports: Path, label: str, remote: str, clone: Path, today: date | None = None,
         attempts: int = 3) -> dict:
    today = today or datetime.now(timezone.utc).date()
    files = [(p.name, p.stat().st_mtime) for p in exports.iterdir() if p.is_file()] if exports.is_dir() else []
    bp = bulletin_plan(exports, role)                             # addendum 250 item 4: the kept subtree
    late: list[tuple[str, str]] = []                              # the push's own skips, per attempt

    def _extra() -> dict:                                         # receipted whenever anything was left out
        skipped = [(_shown(rel), why) for rel, why in bp["skipped"] + late]
        return {"skipped": skipped} if skipped else {}
    _ensure_clone(clone, remote)
    for attempt in range(1, attempts + 1):
        _sync_to_remote(clone)
        pl = plan(files, role, today)
        copied, late, fresh = 0, [], set()
        gl = _gitlinks(clone, role)                               # review of #847's round 1: submodules, by the index
        for dest, name in {**pl["dated"], **pl["latest"]}.items():
            src, dst = exports / name, clone / dest
            if dst.exists() and dst.read_bytes() == src.read_bytes():
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1
        for dest, src in bp["kept"].items():                      # one bad bulletin is local to that file
            dst = clone / dest
            why = _dest_refusal(clone, dest, gl)                  # Codex on #847: never through a tracked link
            if why:
                late.append((dest[len(role) + 1:], why))
                continue
            try:
                data = src.read_bytes()                           # read whole first: never a half-written copy
            except OSError as e:                                  # no read permission, or gone since the plan
                late.append((dest[len(role) + 1:], f"unreadable: {e.__class__.__name__}"))
                continue
            if dst.is_file() and dst.read_bytes() == data:
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(data)
            copied += 1
            fresh.add(dest)
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
        for rel in _refused_by_git(clone, role, gl):              # git decides; removed from the clone
            late.append((rel, "git refused the path"))
            if f"{role}/{rel}" in fresh:
                copied -= 1
        _git(clone, "add", "-A")
        staged = _git(clone, "diff", "--cached", "--quiet", check=False).returncode != 0
        # ARCHITECT 2026-10-03 (host first push): "changed" is judged against the REMOTE's tip, not
        # the local HEAD — a commit left by a push that failed (remote set before the key worked)
        # is not on an empty remote, and must not read as "nothing changed".
        unpushed = _unpushed(clone)
        if not staged and not unpushed:
            return {"role": role, "pushed": False, "copied": 0, "pruned": pruned, "why": "nothing changed", **_extra()}
        if staged:
            _git(clone, "commit", "-q", "-m", f"{role}: {label} · {copied} file(s) · pruned {len(pruned)}")
        r = _git(clone, "push", "-q", "origin", f"HEAD:{BRANCH}", check=False)
        if r.returncode == 0:
            sha = _git(clone, "rev-parse", "HEAD").stdout.strip()
            return {"role": role, "pushed": True, "copied": copied, "pruned": pruned, "sha": sha,
                    "attempt": attempt, "unpushed_before": unpushed, **_extra()}
    return {"role": role, "pushed": False, "copied": copied, "pruned": pruned,
            "why": f"push rejected {attempts}x: {(r.stderr or '').strip()[-200:]}", **_extra()}


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
          + (f" · pruned {r['pruned']}" if r["pruned"] else "")
          + (f" · {skipped_line(r['skipped'])}" if r.get("skipped") else ""))
    return 0 if (r["pushed"] or r.get("why") == "nothing changed") else 1


if __name__ == "__main__":
    sys.exit(main())
