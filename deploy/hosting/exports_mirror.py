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
  cannot be read when the push copies it (no read permission, or gone since the plan: `unreadable: <error>`), a
  source swapped since the plan for a symlink, file or folder above it, or for a FIFO or anything else that is not a
  regular file (#851 R2-2: read with every folder opened by dir fd and the file with O_NOFOLLOW|O_NONBLOCK, fstat
  requiring a regular file: `symlink: not followed` / `not a regular file`, never read through, never blocked on), and a
  path git itself refuses (`git refused the path`: git decides, by `add --force --ignore-errors`, not a list kept here;
  with core.protectNTFS, its default, that is `.git`'s other spellings GIT~1, `.git.`, `.git `). The DESTINATION is
  never followed either (Codex on #847): the mirror's own tree may already track a symlink, so before a bulletin is
  read back or written, every component from <role>/ down to the file is lstat'ed, and a symlink there (the role
  folder, bulletins/, a family or date folder, or the file itself: `destination path has a symlink`), a component
  above the file that is not a folder (`destination path has a non-folder`) or a file that is not a regular file
  (`destination not a regular file`) skips that bulletin, receipted; what the mirror tracks there is left as it is
  (never unlinked, never written through), the missing folders are made only below real ones, and git's own check
  never walks a <role>/ or <role>/bulletins/ that is not a real folder. A submodule the index holds on the path
  (a gitlink checks out as an empty real folder) is refused too (`destination path has a submodule`), by its text
  and by its checkout folder's (st_dev, st_ino) (#851 R2-3: on a case-insensitive clone, the macOS laptop's,
  `bulletins/nfl` IS a gitlink `bulletins/NFL`'s folder), and git's check never walks into one. One bad bulletin
  is local to that file: a copy git refused is removed from the working clone (it is the push's own planned copy),
  so it never jams a later push, and the top-level files and the other bulletins still go.
  Absent exports/bulletins/: nothing happens.

WHAT A PUSH PUBLISHES (ARCHITECT 2026-11-06, addendum 277 item 1, R2-1 on #847): "the mirror publishes ONLY the paths
its plan copied [...] The fix is the add limited to planned paths (never `git clean -fd`: the mirror deletes nothing
it did not plan either); a leftover from a killed run is then never published and the next run's receipt names it as
untracked-and-skipped." Never a whole-tree `add -A`: the push stages, by name (git reads the list on stdin,
NUL-separated, as literal pathspecs), exactly the dated and latest copies of the top-level plan, the kept bulletins it
carried (minus the skipped and the refused), tools/compare_exports.py and .github/workflows/compare.yml, with
`--force` (the list is the plan: no ignore rule, a stray untracked .gitignore or a .git/info/exclude entry, vetoes a
planned path or makes the add abort the push; core.protectNTFS still refuses); its planned
deletions go through `git rm` on TRACKED paths only (the latest cleanup: a tracked <role>/latest/ file no planned kind
holds; the prune: the tracked contents of an expired <role>/<YYYY-MM-DD>/ folder, `pruned` naming the folders that
held any). A planned path beyond a symlink or inside a submodule is never staged (git refuses that pathspec, and the
whole-tree add never carried it either); the top-level rule never writes one (#852, below). Any
OTHER untracked file in the working clone (a killed run's leftover whose source is gone, a file another writer dropped
there, under <role>/bulletins/, <role>/, <role>/latest/, an expired folder or the clone root) is not staged, so it never
reaches the remote; it is never deleted (no clean, no unlink); and every push names it: `untracked_skipped`
(clone-relative paths) on the result and `· untracked-and-skipped N (<first five paths>[, +K more])` on the console
line. A TRACKED file the plan does not write, edited in the clone by another writer between the sync and the add, is
not staged either (the remote keeps its tracked bytes); it is not untracked, so it is not on the receipt, and the next
sync's `reset --hard` puts the tracked bytes back, as on main. The weekly squash commits the index as the sync left it
(the remote tip's tree), never a whole-tree add, and names the same files on its result.

THE TOP-LEVEL RULE'S DESTINATION (#852; ARCHITECT 2026-11-06, addendum 277 item 1): "THE PRE-EXISTING HOLE (main's
top-level rule follows a tracked symlink out of the clone: the latest cleanup can unlink files OUTSIDE the clone, the
dated copy can write outside it, the prune can abort every push; a tracked submodule at <role> silently swallows the
day's files): [...] RULED: [...] the review's fix as proposed (lstat every component as _dest_refusal does; refuse a
symlinked or submodule <role>, <role>/latest, <role>/<date>; receipt the skip; follow nothing, unlink nothing through a
link)." As built, by _dest_refusal itself (one rule, the bulletins' own): every planned dated and latest copy's path is
lstat'ed from <role>/ down before it is read back or written, and a symlink there (<role>, <role>/latest, <role>/<date>
or the file itself, a relative escape or an absolute link: `destination path has a symlink`), a component that is not a
folder, a file that is not a regular file, or a component the index holds as a submodule (`destination path has a
submodule`) skips that copy: never written through, never written into the submodule's folder, never staged. The latest
cleanup never reads a <role>/ or <role>/latest/ that is not a real folder, and never removes a gitlink (a stale
submodule entry there is skipped). The prune picks each expired <role>/<YYYY-MM-DD> by its name, then lstat, never a
stat through it, and lstat's it again (_dest_refusal, folder=True): a symlinked one (whatever its target: a folder, a
file, nothing, one whose stat raises) or a submodule one is skipped, never followed, never unlinked, never removed,
and the push goes on; inside a real expired folder a submodule entry is skipped and the rest of its tracked contents
go. Every skip is RECEIPTED: `top_level_skipped` (role-relative path, reason) on the result and `· top-level: N skipped
(<reason> <count> · …)` on the console line, on every push it remains; the tracked link or submodule is left as the
mirror holds it; the rest of the push (the other copies, the other expired folders, the bulletins, the tools) proceeds.

THE TOOLS COPY'S DESTINATION (#858; ARCHITECT addendum 282 item 3): "the tools copy (tools/compare_exports.py and the
workflow file written through a tracked link) is the same defect in the same module and is BUILT in #858 by the same
rule — each tool path through _dest_refusal, skipped and receipted, never written through". As built: each of
tools/compare_exports.py and .github/workflows/compare.yml is lstat'ed by _dest_refusal from the clone root down before
it is read back or written; a symlink at tools/, .github/, .github/workflows/ or the file itself (relative or absolute:
`destination path has a symlink`), a submodule the index holds there (`destination path has a submodule`), a component
that is not a folder or a file that is not a regular file skips that tool: never written through, never written into
the submodule's folder, never staged. RECEIPTED: `tools_skipped` (clone-relative path, reason) on the result and
`· tools: N skipped (<reason> <count> · …)` on the console line, on every push it remains; the tracked entry stays as
the mirror holds it; the other tool, the top-level copies and the bulletins still go.
"""
from __future__ import annotations

import argparse
import errno
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


def _read_planned(exports: Path, src: Path) -> tuple[bytes | None, str | None]:
    """A planned bulletin's bytes, or (None, why). #851 R2-2 (ARCHITECT, addendum 381 item 3(v); the fix quoted on
    the thread: "`os.open` with `O_NOFOLLOW|O_NONBLOCK`, `fstat` requiring a regular file, and the parent folders
    walked by dir fd"): the plan lstat'ed each path, but a source swapped AFTER the plan for a symlink (the file or a
    folder above it) or a FIFO is never read through the link and never blocked on. Each folder from exports/ down is
    opened by name relative to its parent's fd with O_NOFOLLOW (a link there: "symlink: not followed", the plan's own
    reason), the file the same way with O_NONBLOCK (a FIFO opens at once), and fstat must say a regular file ("not a
    regular file"). Any other failure: "unreadable: <the error's class>", as before."""
    parts = src.relative_to(exports).parts
    flags_dir = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fds: list[int] = []
    try:
        fds.append(os.open(exports, os.O_RDONLY | os.O_DIRECTORY))
        for part in parts[:-1]:
            try:
                fds.append(os.open(part, flags_dir, dir_fd=fds[-1]))
            except OSError as e:                          # Linux: ENOTDIR for a link under O_DIRECTORY|O_NOFOLLOW
                if e.errno in (errno.ENOTDIR, errno.ELOOP) and st.S_ISLNK(
                        os.stat(part, dir_fd=fds[-1], follow_symlinks=False).st_mode):
                    return None, "symlink: not followed"
                raise
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fds[-1])
        fds.append(fd)
        if not st.S_ISREG(os.fstat(fd).st_mode):
            return None, "not a regular file"
        chunks = []
        while True:
            b = os.read(fd, 1 << 20)
            if not b:
                break
            chunks.append(b)
        return b"".join(chunks), None
    except OSError as e:
        if e.errno == errno.ELOOP:
            return None, "symlink: not followed"
        if e.errno == errno.ENXIO:                        # a socket (or a FIFO with no reader on some systems)
            return None, "not a regular file"
        return None, f"unreadable: {e.__class__.__name__}"
    finally:
        for f in reversed(fds):
            os.close(f)


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


def skipped_line(skipped: list[tuple[str, str]], what: str = "bulletins") -> str:
    """The console's count by reason: "bulletins: 2 skipped (suffix: not .md or .png 1 · symlink: not followed 1)";
    what="top-level" for the top-level rule's own skips (#852), what="tools" for the tools copy's (#858)."""
    by: dict[str, int] = {}
    for _, why in skipped:
        by[why] = by.get(why, 0) + 1
    return f"{what}: {len(skipped)} skipped (" + " · ".join(f"{w} {n}" for w, n in by.items()) + ")"


def expired(role_dir: Path, today: date) -> list[Path]:
    """The <role>/<YYYY-MM-DD> entries older than the retention window: by NAME first, then lstat, never a stat through
    the entry (#852 review: a tracked link's target is never read, so a target whose stat raises never aborts the
    push). A real folder or a symlink of any target (dangling, a file, a folder) is listed: the prune's _dest_refusal
    (folder=True) refuses and receipts every link; an entry lstat cannot read is listed for the same receipt."""
    lo = today - timedelta(days=RETENTION_DAYS - 1)
    out = []
    for p in role_dir.iterdir() if role_dir.is_dir() else []:
        try:
            if date.fromisoformat(p.name) >= lo:
                continue
        except ValueError:
            continue
        try:
            mode = p.lstat().st_mode
        except FileNotFoundError:
            continue
        except OSError:
            out.append(p)
            continue
        if st.S_ISDIR(mode) or st.S_ISLNK(mode):
            out.append(p)
    return out


def _git(clone: Path, *args, check=True, capture=True, text=True, input=None):
    env = dict(os.environ)
    env["GIT_LITERAL_PATHSPECS"] = "1"          # addendum 277 item 1: a planned path is a path, never a glob
    key = str(key_path())
    if os.path.isfile(key):
        env["GIT_SSH_COMMAND"] = f"ssh -i {key} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
    else:
        # Codex on #335: a url.<base>.insteadOf / pushInsteadOf rewrite can turn an HTTPS remote into SSH at push
        # time, past ssh_remote(). With no key file, any SSH transport git starts is REFUSED here, so a push can
        # never run on an agent or default identity; HTTPS is unaffected.
        env["GIT_SSH_COMMAND"] = REFUSE_SSH
    return subprocess.run(["git", "-C", str(clone), *args], check=check, env=env, text=text,
                          capture_output=capture, input=input)


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


class _Gitlinks(frozenset):
    """The submodule entries as NFC paths (a frozenset, as before) plus `inodes`: the (st_dev, st_ino) of each one's
    checkout folder that exists as a real folder (#851 R2-3, ARCHITECT, addendum 381 item 3(v): "match submodules by
    `(st_dev, st_ino)` of their checkout folder, keeping the text check for a gitlink with no folder"). On a
    case-insensitive clone (the macOS laptop) `bulletins/nfl` IS a gitlink `bulletins/NFL`'s folder, which the text
    check alone never sees."""

    def __new__(cls, paths=(), inodes=frozenset()):
        self = super().__new__(cls, paths)
        self.inodes = frozenset(inodes)
        return self


def _is_gitlink_folder(gitlinks: frozenset[str], mode_st) -> bool:
    """True when an lstat result is a real folder that is a submodule's checkout folder, by its (st_dev, st_ino)."""
    return st.S_ISDIR(mode_st.st_mode) and (mode_st.st_dev, mode_st.st_ino) in getattr(gitlinks, "inodes", ())


def _gitlinks(clone: Path, role: str | None = None) -> frozenset[str]:
    """The submodule entries (gitlinks, mode 160000) the clone's index holds at or under <role>/ (no role: anywhere in
    the index), as NFC paths: git checks one out as an empty REAL folder, so an lstat never sees it (review of #847's
    round-1 fix). With each one's checkout folder by (st_dev, st_ino) on `.inodes` (#851 R2-3): lstat'ed, never
    followed, and only when it is a real folder (a gitlink with no folder is matched by its text alone)."""
    out = _git(clone, "ls-files", "-s", "-z", *(("--", role) if role else ()), text=False).stdout
    paths = [unicodedata.normalize("NFC", os.fsdecode(e.split(b"\t", 1)[1]))
             for e in out.split(b"\0") if e.startswith(b"160000 ") and b"\t" in e]
    inodes = set()
    for rel in paths:
        try:
            got = (clone / rel).lstat()
        except OSError:
            continue
        if st.S_ISDIR(got.st_mode):
            inodes.add((got.st_dev, got.st_ino))
    return _Gitlinks(paths, inodes)


def _dest_refusal(clone: Path, dest: str, gitlinks: frozenset[str] = frozenset(), folder: bool = False) -> str | None:
    """None when <clone>/<dest> may be read and written as a plain file; else why not (Codex on #847). Every component
    from <role>/ down to the file is lstat'ed, never followed: a symlink anywhere on the path (the mirror's own tree
    may track one, and a relative or absolute link would carry the write out of the clone), a component above the
    file that is not a folder, or a file that is not a regular file is refused. A component the index holds as a
    submodule (one of `gitlinks`, from _gitlinks) is refused before its lstat: its checkout is an empty real folder,
    and a write into it is one git never carries. A component that does not exist ends the walk: everything below
    it is made by mkdir as real folders under real folders. folder=True (the prune's expired <role>/<date>/, #852): the
    last component must be a real folder too, else "destination path has a non-folder"."""
    parts = Path(dest).parts
    p = clone
    for i, part in enumerate(parts):
        p = p / part
        if unicodedata.normalize("NFC", "/".join(parts[:i + 1])) in gitlinks:
            return "destination path has a submodule"
        try:
            got = p.lstat()
        except FileNotFoundError:
            return None
        except OSError as e:
            return f"destination unreadable: {e.__class__.__name__}"
        mode = got.st_mode
        if _is_gitlink_folder(gitlinks, got):           # #851 R2-3: the same folder under another casing
            return "destination path has a submodule"
        if st.S_ISLNK(mode):
            return "destination path has a symlink"
        if (i < len(parts) - 1 or folder) and not st.S_ISDIR(mode):
            return "destination path has a non-folder"
        if i == len(parts) - 1 and not folder and not st.S_ISREG(mode):
            return "destination not a regular file"
    return None


def _nfc(rel: str) -> str:
    return unicodedata.normalize("NFC", rel)


def _real_path(clone: Path, rel: str, gitlinks: frozenset[str], last_is_dir: bool) -> bool:
    """True when every component of <clone>/<rel> above the last is a REAL folder (lstat'ed, never followed) that the
    index does not hold as a submodule, and the last is a real folder (last_is_dir) or something that is not a folder
    (a file to stage). Git refuses a pathspec beyond a symlink or inside a submodule (exit 128, the whole push lost),
    and main's whole-tree add never carried a path there either: such a path is never staged (addendum 277 item 1)."""
    parts = Path(rel).parts
    p = clone
    for i, part in enumerate(parts):
        p = p / part
        if _nfc("/".join(parts[:i + 1])) in gitlinks:
            return False
        try:
            got = p.lstat()
        except OSError:
            return False
        if _is_gitlink_folder(gitlinks, got):           # #851 R2-3: never a pathspec inside a case-folded submodule
            return False
        mode = got.st_mode
        if (i < len(parts) - 1 or last_is_dir) and not st.S_ISDIR(mode):
            return False
        if i == len(parts) - 1 and not last_is_dir and st.S_ISDIR(mode):
            return False
    return True


def _pathspec_input(clone: Path, paths: list[str]) -> bytes:
    """The NUL-separated pathspec file git reads from stdin (`--pathspec-from-file=- --pathspec-file-nul`): any number
    of paths, any bytes in a name, no command-line limit. A git that precomposes Unicode (macOS's default) matches the
    names it reads from disk in NFC, so the paths are sent in NFC there."""
    pre = _git(clone, "config", "--bool", "core.precomposeunicode", check=False).stdout.strip() == "true"
    return b"\0".join(os.fsencode(_nfc(p) if pre else p) for p in paths)


def _stage(clone: Path, paths: list[str], ignore_errors: bool = False) -> subprocess.CompletedProcess | None:
    """`git add` of exactly these paths, nothing else (addendum 277 item 1: "the add limited to planned paths").
    `--force`: the list IS the plan, so no ignore rule vetoes a path in it (review of the fix: a stray untracked
    .gitignore, or a .git/info/exclude entry, made git's add exit 1 on a planned path, and a stray is never deleted,
    so every later push would abort). It changes nothing else git checks: core.protectNTFS still refuses a path."""
    if not paths:
        return None
    return _git(clone, "add", "--force", *(("--ignore-errors",) if ignore_errors else ()), "--pathspec-from-file=-",
                "--pathspec-file-nul", check=not ignore_errors, text=False, input=_pathspec_input(clone, paths))


def _tracked(clone: Path, rel: str) -> list[str]:
    """The paths the index holds at or under <rel>."""
    out = _git(clone, "ls-files", "-z", "--", rel, text=False).stdout
    return [os.fsdecode(q) for q in out.split(b"\0") if q]


def _untracked(clone: Path) -> list[str]:
    """Every file in the working clone the index does not hold, after the push staged its plan: a leftover of a killed
    run, a file another writer dropped there. Never staged, never deleted; the receipt names each (addendum 277 item
    1: "untracked-and-skipped"). Git never lists a file inside a submodule's folder here."""
    out = _git(clone, "ls-files", "--others", "-z", text=False).stdout
    return sorted(_shown(os.fsdecode(q)) for q in out.split(b"\0") if q)


def untracked_line(untracked: list[str], shown: int = 5) -> str:
    """The console's segment: "untracked-and-skipped 2 (host/stray.md, stray.txt)", the first `shown` paths, the rest
    counted; a control character (a newline in a name) printed escaped, so the receipt stays one line."""
    def one(rel: str) -> str:
        return "".join(ch if ch.isprintable() else repr(ch)[1:-1] for ch in rel)
    more = f", +{len(untracked) - shown} more" if len(untracked) > shown else ""
    return f"untracked-and-skipped {len(untracked)} (" + ", ".join(one(u) for u in untracked[:shown]) + more + ")"


def _refused_by_git(clone: Path, role: str, carried: list[str], gitlinks: frozenset[str] = frozenset()) -> list[str]:
    """Git decides which paths under <role>/bulletins/ it carries (review of the kept subtree's PR): `add
    --force --ignore-errors` of exactly the bulletins this push carries (`carried`: clone-relative
    <role>/bulletins/<rel>, each one past _dest_refusal; addendum 277 item 1, never the folder as a whole; no ignore
    rule vetoes one, _stage) stages every one git accepts and refuses the rest (with core.protectNTFS, git's default,
    `.git`'s other spellings GIT~1, `.git.` and `.git ` among them), so a carried path not in the index afterwards is
    one git refused. Each is removed from the working clone (it is this
    push's own planned copy, so it never sits there as an untracked leftover), with only the folders its unlink emptied
    (deepest first, never <role>/bulletins/ itself); nothing else under <role>/bulletins/ is read, walked or removed
    (the mirror deletes nothing it did not plan). Returns their paths under <role>/ (bulletins/<rel>, the plan's form).
    Bytes throughout: a name that is not UTF-8 never breaks the read. Names are compared in NFC on both sides, so a git
    that precomposes Unicode (macOS's default) never reads a decomposed name on disk as refused. Never run unless
    <role>/ and <role>/bulletins/ are both real folders and neither is a submodule (Codex on #847: a tracked symlink
    there would carry git's check out of the clone; review of its fix: a pathspec inside a submodule makes git's add
    exit 128 and abort the push)."""
    sub = clone / role / BULLETINS
    if not carried or {role, f"{role}/{BULLETINS}"} & gitlinks:
        return []
    for p in (clone / role, sub):
        try:
            if not st.S_ISDIR(p.lstat().st_mode):
                return []
        except OSError:
            return []
    r = _stage(clone, carried, ignore_errors=True)
    if r.returncode not in (0, 1):                  # 1 = some path refused; anything else is not a path's fault
        raise subprocess.CalledProcessError(r.returncode, r.args, r.stdout, r.stderr)
    indexed = {_nfc(q) for q in _tracked(clone, f"{role}/{BULLETINS}")}
    refused, emptied = [], set()
    for rel in carried:
        if _nfc(rel) in indexed:
            continue
        p = clone / rel
        if p.is_file() and not p.is_symlink():
            p.unlink()
            emptied.add(p.parent)
        refused.append(rel[len(role) + 1:])
    for d in sorted(emptied, key=lambda q: len(q.parts), reverse=True):
        while d != sub and d.is_dir() and not d.is_symlink() and not os.listdir(d):
            os.rmdir(d)                                   # the refused file's now-empty folder, and its emptied parents
            d = d.parent
    return sorted(refused)


def push(role: str, exports: Path, label: str, remote: str, clone: Path, today: date | None = None,
         attempts: int = 3) -> dict:
    today = today or datetime.now(timezone.utc).date()
    files = [(p.name, p.stat().st_mtime) for p in exports.iterdir() if p.is_file()] if exports.is_dir() else []
    bp = bulletin_plan(exports, role)                             # addendum 250 item 4: the kept subtree
    late: list[tuple[str, str]] = []                              # the push's own skips, per attempt
    top: list[tuple[str, str]] = []                               # #852: the top-level rule's skips, per attempt
    tools: list[tuple[str, str]] = []                             # #858: the tools copy's skips, per attempt

    def _extra() -> dict:                                         # receipted whenever anything was left out
        skipped = [(_shown(rel), why) for rel, why in bp["skipped"] + late]
        return {**({"skipped": skipped} if skipped else {}),
                **({"top_level_skipped": [(_shown(rel), why) for rel, why in top]} if top else {}),
                **({"tools_skipped": list(tools)} if tools else {}),
                **({"untracked_skipped": untracked} if untracked else {})}
    _ensure_clone(clone, remote)
    untracked: list[str] = []
    for attempt in range(1, attempts + 1):
        _sync_to_remote(clone)
        pl = plan(files, role, today)
        copied, late, top, tools, fresh, planned, carried = 0, [], [], [], set(), [], []
        gl = _gitlinks(clone)                                     # review of #847's round 1: submodules, by the index
        for dest, name in {**pl["dated"], **pl["latest"]}.items():
            why = _dest_refusal(clone, dest, gl)                  # #852: never through a tracked link or into a
            if why:                                               # submodule at <role>, <role>/latest, <role>/<date>
                top.append((dest[len(role) + 1:], why))
                continue
            src, dst = exports / name, clone / dest
            planned.append(dest)                                  # addendum 277 item 1: staged by name, nothing else
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
            data, why = _read_planned(exports, src)               # read whole first: never a half-written copy
            if why:                                               # #851 R2-2: swapped, unreadable or gone since
                late.append((dest[len(role) + 1:], why))          # the plan
                continue
            carried.append(dest)
            if dst.is_file() and dst.read_bytes() == data:
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(data)
            copied += 1
            fresh.add(dest)
        # The planned deletions go through git on TRACKED paths only (addendum 277 item 1: the mirror deletes nothing
        # it did not plan): an untracked file in latest/ or in an expired dated folder is left on disk and receipted.
        # #852: never through a link (a linked <role>/ or <role>/latest/ is never read; a linked expired folder is
        # skipped), never a submodule (a gitlink is never removed): each skip receipted on top_level_skipped.
        pruned = []

        def _rm(paths: list[str]) -> bool:                        # tracked paths only, gitlinks never among them
            subs = [q for q in paths if _nfc(q) in gl]
            top.extend((q[len(role) + 1:], "destination path has a submodule") for q in subs)
            gone = [q for q in paths if _nfc(q) not in gl]
            if gone:
                _git(clone, "rm", "-q", "-f", "--pathspec-from-file=-", "--pathspec-file-nul", text=False,
                     input=_pathspec_input(clone, gone))
            return bool(gone)
        if _real_path(clone, role, gl, last_is_dir=True):
            if _real_path(clone, f"{role}/latest", gl, last_is_dir=True):     # latest/ is rewritten each push
                want = {_nfc(d) for d in pl["latest"]}
                _rm([q for q in _tracked(clone, f"{role}/latest") if _nfc(q) not in want])
            for p in sorted(expired(clone / role, today)):
                rel = f"{role}/{p.name}"
                why = _dest_refusal(clone, rel, gl, folder=True)
                if why:
                    top.append((p.name, why))
                    continue
                if _rm(_tracked(clone, rel)):
                    pruned.append(p.name)
        for src, rel in ((HERE / "compare_exports.py", "tools/compare_exports.py"),
                         (WORKFLOW_SRC, ".github/workflows/compare.yml")):
            why = _dest_refusal(clone, rel, gl)                   # #858 (282 item 3): never through a tracked link or
            if why:                                               # into a submodule at tools/, .github/, .github/workflows/
                tools.append((rel, why))                          # or the file itself: skipped, receipted, never staged
                continue
            dest = clone / rel
            if src.exists() and (not dest.exists() or dest.read_bytes() != src.read_bytes()):
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
            if os.path.lexists(dest):
                planned.append(rel)
        for rel in _refused_by_git(clone, role, carried, gl):     # git decides; removed from the clone
            late.append((rel, "git refused the path"))
            if f"{role}/{rel}" in fresh:
                copied -= 1
        _stage(clone, [q for q in planned if _real_path(clone, q, gl, last_is_dir=False)])
        untracked = _untracked(clone)                             # never staged, never deleted: receipted
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
    """Weekly: the current tree as ONE orphan commit, force-pushed (the repo stays small). The commit is the index as
    the sync left it, the remote tip's tree exactly (`reset --hard`; `checkout --orphan` keeps the index), never a
    whole-tree add (addendum 277 item 1): an untracked file in the clone is not in it, is left on disk, and the result
    names it (`untracked_skipped`)."""
    _ensure_clone(clone, remote)
    _sync_to_remote(clone)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    untracked = _untracked(clone)
    _git(clone, "checkout", "-q", "--orphan", "squash-tmp")
    _git(clone, "commit", "-q", "-m", f"weekly squash {stamp} (history before this date dropped; files kept)")
    _git(clone, "branch", "-q", "-M", BRANCH)
    r = _git(clone, "push", "-q", "--force", "origin", f"{BRANCH}:{BRANCH}", check=False)
    return {"squashed": r.returncode == 0, "why": (r.stderr or "").strip()[-200:] if r.returncode else None,
            **({"untracked_skipped": untracked} if untracked else {})}


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
          + (f" · {skipped_line(r['skipped'])}" if r.get("skipped") else "")
          + (f" · {skipped_line(r['top_level_skipped'], 'top-level')}" if r.get("top_level_skipped") else "")
          + (f" · {skipped_line(r['tools_skipped'], 'tools')}" if r.get("tools_skipped") else "")
          + (f" · {untracked_line(r['untracked_skipped'])}" if r.get("untracked_skipped") else ""))
    return 0 if (r["pushed"] or r.get("why") == "nothing changed") else 1


if __name__ == "__main__":
    sys.exit(main())
