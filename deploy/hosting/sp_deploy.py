#!/usr/bin/env python3
"""Code deploy on the host: check out a RELEASE TAG only, receipted.

RELEASE MODEL (architect 2026-09-30): `main` is BETA (the laptop tracks it);
PRODUCTION is tagged releases only. The host never pulls `main` again: this
fetches tags and checks out the latest `vX.Y.Z` (detached), or the exact
`--tag` given (a rollback or a pinned patch is explicit). A tag is cut only
by the architect's ruling after the day's laptop-vs-host compare passes
(docs/RELEASES.md); a hotfix is a patch tag through the same ritual.

    sp_deploy.py [--tag v1.0.1] [--dry-run]

Refuses: no release tag on origin (the host stays where it is — never falls
back to main); an unknown --tag; a checkout on a branch other than main
(main is accepted once, for the first pin); a moved tag (git refuses to
clobber a local tag); any local modification except RESULTS.md, which the
host rewrites (results-tally, H0-9) and is restored first. The host never
builds from a branch and never pushes. Run as the sp user, under the DB lock
so no chain is mid-run. Migrations in the range are run by hand afterwards,
after a backup (hosting-h1.md, "Deploying a release"). When requirements.txt
changed in the range, or this host has no successful install receipt for the
target's file, `venv/bin/pip install -r requirements.txt` runs in a temporary
worktree of the target before the checkout, printed and receipted; a failed
install refuses the deploy (ARCHITECT 2026-10-06).
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_common as c  # noqa: E402


def git(*args: str, strip: bool = True) -> str:
    out = subprocess.run(["git", "-C", str(c.REPO), *args], check=True,
                         capture_output=True, text=True).stdout
    return out.strip() if strip else out


def dirty_paths() -> list[str]:
    """Modified tracked paths. Porcelain lines are 'XY path': the output must
    NOT be stripped first — a leading ' M' would lose its space and the path
    its first letter (the pre-release deploy read ' M RESULTS.md' as
    'ESULTS.md' and refused the very case it meant to allow)."""
    return [ln[3:] for ln in git("status", "--porcelain", "--untracked-files=no", strip=False).splitlines()
            if ln.strip()]


def migration_command(scripts: list[str], expect_sha: str) -> str:
    """The exact by-hand command (ARCHITECT 2026-10-06): as the service user, with
    host.env loaded as the units load it, `sp_deploy.py --run-migrations`, which
    holds ONE DB lock across the daily .backup and every migration, in the given
    order, stopping at the first failure (Codex on #296: a chain released the
    lock between the backup and the migrations, so a timer could interleave)."""
    import shlex
    py = c.REPO / "venv" / "bin" / "python"
    py = py if py.exists() else Path(sys.executable)
    user = c.setting("SP_SERVICE_USER", "sp")
    inner = (f"cd {shlex.quote(str(c.REPO))} && set -a && . {shlex.quote(str(c.HOST_ENV))} && set +a && "
             f"{shlex.quote(str(py))} deploy/hosting/sp_deploy.py --expect {shlex.quote(expect_sha)} "
             f"--run-migrations " + " ".join(shlex.quote(m) for m in scripts))
    return f"sudo -u {user} sh -c {shlex.quote(inner)}"


REQUIREMENTS = "requirements.txt"


def pip_command() -> list[str]:
    """`venv/bin/pip` of this checkout (ARCHITECT 2026-10-06). A venv without a pip script (`--without-pip`) still
    installs INTO the venv, via its own python (Codex on #310); the running interpreter only when there is no venv."""
    venv = c.REPO / "venv"
    if (venv / "bin" / "pip").exists():
        return [str(venv / "bin" / "pip")]
    if (venv / "pyvenv.cfg").exists():
        return [str(venv / "bin" / "python"), "-m", "pip"]
    return [sys.executable, "-m", "pip"]


def _pip_run(cmd: list[str], cwd: str) -> int:
    try:
        return subprocess.run(cmd, cwd=cwd).returncode
    except OSError as e:                     # a launcher that cannot execute is a failed install, receipted
        print(f"  ✗ could not run {cmd[0]}: {e.__class__.__name__}: {e}")   # (Codex on #310)
        return 127


def requirements_state_path() -> Path:
    """The fingerprint of the last SUCCESSFUL install. It lives INSIDE the venv it describes, so deleting or
    recreating the venv deletes it too (an inode can be reused; a file in the old venv cannot survive — Codex on
    #310); never in the monthly-rotated receipt log. Without a venv: beside the receipts."""
    venv = c.REPO / "venv"
    if (venv / "pyvenv.cfg").exists():
        return venv / ".sp-requirements.installed"
    if sys.prefix != sys.base_prefix:        # running from ANOTHER virtualenv: the record lives inside it too, so
        return Path(sys.prefix) / ".sp-requirements.installed"    # recreating it drops the record (Codex on #310)
    return c.receipts_path().parent / "requirements.installed"


# ALLOWLIST (Codex on #310, six rounds): auto-install handles only plain requirements files. Every other pip
# feature (editables, local paths and archives, --find-links, URLs and `name @ ...`, environment variables, line
# continuations, any other option) refuses the deploy and is installed by hand, so nothing pip reads can change
# unseen by the fingerprint.
REFUSE = "is not auto-installable"
PIP_ENV_INPUTS = ("PIP_CONSTRAINT", "PIP_REQUIREMENT", "PIP_FIND_LINKS", "PIP_EDITABLE", "PIP_SRC")
_SPEC = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(\[[A-Za-z0-9._,\s-]*\])?\s*([<>=!~].*)?(;.*)?$")
_COMMENT = re.compile(r"(^|\s+)#.*$")
_INCLUDE = re.compile(r"^(?:-r|--requirement|-c|--constraint)(?:\s+|=)(\S+)$|^-([rc])(\S+)$")
ARCHIVE_SUFFIXES = (".whl", ".zip", ".tar.gz", ".tgz", ".tar.bz2", ".tar")


def _classify(line: str) -> tuple[str, str | None]:
    """('blank'|'spec'|'include'|'refuse', include path or the refusal detail) for one physical line."""
    body = _COMMENT.sub("", line).strip()                # pip strips comments first: a comment never continues
    if not body:
        return "blank", None
    if body.endswith("\\"):
        return "refuse", f"line continuation: {body[:40]!r}"
    if "$" in body:
        return "refuse", f"environment variable: {body[:40]!r}"
    m = _INCLUDE.match(body)
    if m:
        path = m.group(1) or m.group(3)
        if "://" in path:
            return "refuse", f"remote include: {path[:40]!r}"
        return "include", path
    if body.startswith("-"):
        return "refuse", f"pip option: {body.split()[0]!r}"
    tok = body.split(";", 1)[0]
    opts = [w for w in tok.split()[1:] if w.startswith("-")]
    if any(not w.startswith("--hash") for w in opts):   # per-requirement options (--config-settings, ...) can name
        return "refuse", f"per-requirement option: {opts[0]!r}"   # inputs the fingerprint cannot see (Codex)
    if "@" in body or "/" in tok or "\\" in tok or tok.split("[")[0].strip().lower().endswith(ARCHIVE_SUFFIXES) \
            or not _SPEC.match(body):
        return "refuse", f"not a plain specifier: {body[:40]!r}"
    return "spec", None


def requirements_scan(rev: str) -> tuple[dict, list[str]]:
    """({path: blob} for requirements.txt and every -r/-c include, followed recursively relative to the including
    file, file symlinks followed to their target), and the refusals found. An include that is not a tracked file
    (missing, or reached through a symlinked DIRECTORY) is a refusal, never silently skipped."""
    import posixpath
    out, problems, todo = {}, [], [REQUIREMENTS]
    while todo:
        p = posixpath.normpath(todo.pop())
        if p in out:
            continue
        out[p] = _blob(rev, p)
        if out[p] is None:
            problems.append(f"{p}: not a tracked file at the target")
            continue
        rc, mode, _ = _git_rc("ls-tree", rev, "--", p)
        if rc == 0 and mode.startswith("120000"):      # a tracked FILE symlink: pip reads its target
            try:
                todo.append(posixpath.join(posixpath.dirname(p), _git_rc("show", f"{rev}:{p}")[1].strip()))
            except UnicodeDecodeError:
                problems.append(f"{p}: symlink target is not decodable text")
            continue
        try:
            rc, body, _ = _git_rc("show", f"{rev}:{p}")
        except UnicodeDecodeError:          # a BOM / PEP 263 encoding: refused (receipted), never a traceback
            problems.append(f"{p}: not decodable as UTF-8 text (encoding declarations are not auto-installable)")
            continue
        for ln in (body.splitlines() if rc == 0 else []):
            kind, detail = _classify(ln)
            if kind == "include":
                todo.append(posixpath.join(posixpath.dirname(p), detail))
            elif kind == "refuse":
                problems.append(f"{p}: {detail}")
    return out, problems


def requirements_inputs(rev: str) -> dict:
    return requirements_scan(rev)[0]


def _environment_id() -> str:
    """The install destination: the venv's path, or without a venv the running interpreter (Codex on #310). A
    recreated venv is caught by the record living inside it (requirements_state_path)."""
    import os
    cfg = c.REPO / "venv" / "pyvenv.cfg"
    if not cfg.exists():
        return f"python:{os.path.realpath(sys.executable)}"
    # the interpreter version is part of the identity: `venv --upgrade` to a new minor version switches to a new,
    # empty site-packages while the record inside the venv survives (Codex on #310)
    ver = next((ln.split("=", 1)[1].strip() for ln in cfg.read_text(encoding="utf-8", errors="replace").splitlines()
                if ln.split("=", 1)[0].strip() in ("version", "version_info")), "?")
    ssp = next((ln.split("=", 1)[1].strip().lower() for ln in cfg.read_text(encoding="utf-8", errors="replace")
                .splitlines() if ln.split("=", 1)[0].strip() == "include-system-site-packages"), "false")
    return f"venv:{cfg.parent.resolve()}:python-{ver}:system-site-packages={ssp}"


def _fingerprint(inputs: dict) -> str:
    import hashlib
    body = "\n".join([f"env={_environment_id()}"] + [f"{p}:{b}" for p, b in sorted(inputs.items())])
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def _last_installed_requirements() -> str | None:
    try:
        return requirements_state_path().read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def requirements_plan(target_sha: str, changed: list[str]) -> tuple[str | None, str | None]:
    """(fingerprint to install, reason), or (None, reason-or-None) when nothing installs. Installs when
    requirements.txt OR a file it includes changed in the range (ARCHITECT 2026-10-06; includes — Codex on #310),
    and when this host's last successful install was not of exactly these inputs: the deploy that ships this code
    still runs the OLD deployer, and the host that already lacked `cryptography` must be repaired on the next
    deploy. A target without the file installs nothing and says so."""
    if _blob(target_sha, REQUIREMENTS) is None:
        return None, ("removed in the target" if REQUIREMENTS in changed else None)
    inputs, problems = requirements_scan(target_sha)
    # pip also reads inputs from its environment (PIP_CONSTRAINT, PIP_REQUIREMENT, ...): the fingerprint cannot see
    # those files change, so their presence is a refusal like any other unsupported input (Codex on #310)
    problems += [f"environment sets {k}" for k in PIP_ENV_INPUTS if os.environ.get(k)]
    if problems:
        if _last_installed_requirements() == manual_record(_fingerprint(inputs), target_sha):
            return None, None              # this exact release was acknowledged as installed by hand
        return None, f"{REFUSE} ({'; '.join(problems[:3])}{' …' if len(problems) > 3 else ''})"
    fp = _fingerprint(inputs)
    touched = sorted(set(inputs) & set(changed))
    if _last_installed_requirements() == fp:
        return None, None              # already installed in exactly this form (e.g. a retry after a failed checkout)
    if touched:
        return fp, ("changed in this range" if touched == [REQUIREMENTS]
                    else f"changed in this range ({', '.join(touched)})")
    if _last_installed_requirements() != fp:
        return fp, "not installed on this host in this exact form (no matching install record)"
    return None, None


def record_installed(fingerprint: str) -> str | None:
    """Write the install record; the error text if it cannot be written (a read-only venv, a full disk), never an
    exception after pip has already changed the environment (Codex on #310)."""
    try:
        state = requirements_state_path()
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(fingerprint + "\n", encoding="utf-8")
        return None
    except OSError as e:
        try:                                 # the OLD record no longer describes the environment (Codex on #310)
            requirements_state_path().unlink(missing_ok=True)
        except OSError:
            pass
        return f"{e.__class__.__name__}: {e}"


def manual_record(fingerprint: str, target_sha: str) -> str:
    """A by-hand acknowledgement is bound to the TARGET COMMIT, not only to the requirements files: an unsupported
    input (a local wheel, a --find-links directory) can change while the files stay the same, so every new release
    that needs a by-hand install is acknowledged again (Codex on #310)."""
    rc, full, _ = _git_rc("rev-parse", "--verify", f"{target_sha}^{{commit}}")
    return f"{fingerprint}:manual:{full.strip() if rc == 0 else target_sha}"     # the FULL sha, however given


def requirements_fingerprint(target_sha: str) -> str | None:
    return _fingerprint(requirements_scan(target_sha)[0]) if _blob(target_sha, REQUIREMENTS) else None


def install_requirements(target: str, target_sha: str, fingerprint: str, reason: str) -> dict:
    """ARCHITECT 2026-10-06 (the host lacked `cryptography` after v1.2.3): `venv/bin/pip install -r
    requirements.txt`, printed and receipted, run in a temporary WORKTREE of the target (so relative -r / -c /
    --find-links resolve as in the checkout — Codex on #310) BEFORE the live checkout moves; a failed install
    refuses the deploy with production still on its release."""
    import shutil
    import tempfile
    shown = " ".join(pip_command() + ["install", "-r", REQUIREMENTS])
    print(f"  requirements.txt {reason} — running `{shown}` (the {target} file)")
    try:
        tmp = tempfile.mkdtemp(prefix="sp-deploy-req-")
    except OSError as e:                     # a missing/full TMPDIR is a receipted failure, never a traceback
        return c.append_receipt({"kind": "deploy_requirements", "exit": 1, "tag": target, "to_sha": target_sha,
                                 "fingerprint": fingerprint, "reason": reason, "command": shown,
                                 "error": f"temporary directory: {e.__class__.__name__}: {e}"})
    wt = str(Path(tmp) / "wt")
    wt_rc, _, wt_err = _git_rc("worktree", "add", "--detach", wt, target_sha)
    try:
        rc = _pip_run(pip_command() + ["install", "-r", REQUIREMENTS], cwd=wt) if wt_rc == 0 else wt_rc
    finally:
        _git_rc("worktree", "remove", "--force", wt)
        _git_rc("worktree", "prune")
        shutil.rmtree(tmp, ignore_errors=True)
    if rc != 0 and wt_rc == 0:
        # pip may have changed packages before failing: the OLD record no longer describes the environment, so it
        # is dropped and the next deploy reinstalls whatever its inputs (Codex on #310)
        try:
            requirements_state_path().unlink(missing_ok=True)
        except OSError:
            pass
    state_error = record_installed(fingerprint) if rc == 0 else None
    # worktree stderr is attached ONLY when the worktree itself failed: on success git still prints
    # "Preparing worktree", which is not a pip diagnostic (Codex on #310)
    return c.append_receipt({"kind": "deploy_requirements", "exit": rc, "tag": target, "to_sha": target_sha,
                             "fingerprint": fingerprint, "reason": reason, "command": shown,
                             **({"state_error": state_error} if state_error else {}),
                             **({"error": f"worktree add failed: {wt_err}"} if wt_rc != 0 else {})})


MIGRATION_NAME = re.compile(r"^migrate_[A-Za-z0-9_]+\.py$")


def run_migrations(scripts: list[str], expect_sha: str | None) -> int:
    """Backup, then each migration in order, all under one DB lock; the first failure stops
    the run. Receipted step by step. Only top-level migrate_*.py files of this checkout, and
    only when HEAD is still the release the plan was made for (`--expect`, Codex on #296:
    after another deploy, the same names could hold different migration logic)."""
    import sp_backup
    if not expect_sha:
        raise SystemExit("✗ --run-migrations needs --expect <sha> (the deploy prints it) — refusing.")
    with c.db_lock():
        # validated UNDER the lock (Codex on #296): a concurrent deploy cannot swap the files between
        # the check and the run
        for m in scripts:
            if not MIGRATION_NAME.match(m) or not (c.REPO / m).is_file():
                raise SystemExit(f"✗ {m!r} is not a migrate_*.py file in {c.REPO} — refusing.")
        rc, head, err = _git_rc("rev-parse", "HEAD")
        if rc != 0 or not head.strip().startswith(expect_sha):
            raise SystemExit(f"✗ HEAD is {head.strip()[:12] or '?'} ({err or 'read'}), not the planned release "
                             f"{expect_sha} — refusing; re-run the deploy's printed command for this release.")
        bk = sp_backup.run_backup("daily", lock=False)          # the lock is already held here
        if bk["exit"] != 0:
            c.append_receipt({"kind": "migrations", "exit": 1, "step": "backup", "scripts": scripts,
                              "error": bk.get("error")})
            print(f"✗ backup failed ({bk.get('error')}) — no migration ran")
            return 1
        print(f"✓ backup {bk['file']} integrity={bk['integrity']}")
        for i, m in enumerate(scripts):
            r = subprocess.run([sys.executable, m], cwd=str(c.REPO))
            c.append_receipt({"kind": "migrations", "exit": r.returncode, "step": m, "index": i,
                              "backup": bk["file"]})
            if r.returncode != 0:
                print(f"✗ {m} exited {r.returncode} — stopped; not run: {scripts[i + 1:]}")
                return r.returncode
            print(f"✓ {m}")
    return 0


def _git_rc(*args: str) -> tuple[int, str, str]:
    r = subprocess.run(["git", "-c", f"safe.directory={c.REPO}", "-C", str(c.REPO), *args],
                       capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr.strip()


def _root_migrations(rev: str) -> set:
    rc, out, err = _git_rc("ls-tree", "--name-only", rev)
    if rc != 0:
        raise SystemExit(f"✗ cannot list {rev}: {err} — refusing to plan migrations.")
    return {p for p in out.splitlines() if MIGRATION_NAME.match(p)}


def _blob(rev: str, path: str):
    """The blob id of `path` at `rev`; None when absent (never raises: a missing blob simply matches nothing)."""
    rc, out, _ = _git_rc("rev-parse", "--verify", "--quiet", f"{rev}:{path}")
    return out.strip() if rc == 0 and out.strip() else None


def migration_plan(before: str, after: str, changed: list[str]) -> dict:
    """Which migrations to run by hand, in which order (Codex on #296).
    - Only a FORWARD deploy (before is an ancestor of after) runs migrations. A
      rollback or a sideways move never does: its diff lists migrations the
      target lacks or predates, and the DB keeps its additive columns. An
      ancestry check that ERRORS (not "no") refuses the plan, never guesses.
    - New = absent at `before`, present at `after` (a migration added in a merge
      result counts). Order = first appearance in before..after's history,
      merges included (-m), oldest first; never git's alphabetical path order
      (migrate_score_90.py needs migrate_status_raw.py first). A new migration
      the history does not place is appended and flagged. Migrations that were
      only modified are listed separately, never as runnable."""
    found = [p for p in changed if p.startswith("migrate_") and p.endswith(".py")]
    if not found:
        return {"forward": True, "run": [], "modified": [], "skipped": [], "unordered": [], "undetermined": [],
                "new": [], "renamed": {}, "lineage_unknown": False,
                "deleted_migrations": []}
    rc, _, err = _git_rc("merge-base", "--is-ancestor", before, after)
    if rc == 1:
        return {"forward": False, "run": [], "modified": [], "skipped": found, "unordered": [], "undetermined": [],
                "new": [], "renamed": {}, "lineage_unknown": False,
                "deleted_migrations": []}
    if rc != 0:
        raise SystemExit(f"✗ ancestry check {before}..{after} failed ({err or f'git exit {rc}'}) — "
                         "refusing to plan migrations.")
    before_migrations = _root_migrations(before)
    new = _root_migrations(after) - before_migrations
    # a RENAME is not a new migration (it already ran under its old name): reported as modified, only when its
    # source was a migration at `before`. An UNCHANGED COPY of a prior migration is not one either (running it
    # would apply a one-shot twice). Copies are decided by CONTENT, not by git's copy detection: the new file's
    # blob equals some migration's blob at `before` (git picks one candidate among identical files, which may
    # be a non-migration template — Codex on #304). A template-derived new migration stays new.
    rc, out, err = _git_rc("diff", "-M", "--name-status", before, after)
    if rc != 0:
        raise SystemExit(f"✗ git diff {before}..{after} failed ({err}) — refusing to plan migrations.")
    renamed = {}
    for ln in out.splitlines():
        parts = ln.split("\t")
        if len(parts) == 3 and parts[2] in new and parts[1] in before_migrations and parts[0].startswith("R"):
            renamed[parts[2]] = parts[1]
    prior = {_blob(before, m): m for m in sorted(before_migrations)}
    for m in sorted(new - set(renamed)):
        src = prior.get(_blob(after, m))
        if src:
            renamed[m] = src
    new -= set(renamed)
    # --no-renames: a file RENAMED into a migration name is an addition of that migration (git would otherwise
    # report it as R and --diff-filter=A would drop it — Codex on #304)
    rc, out, err = _git_rc("log", "--reverse", "-m", "--no-renames", "--diff-filter=A", "--name-only",
                           "--format=@@%H %P", f"{before}..{after}")
    if rc != 0:
        raise SystemExit(f"✗ git log {before}..{after} failed ({err}) — refusing to plan migrations.")
    # CONSERVATIVE ORDERING (Codex on #296 and #304, five rounds): history is evidence of order only when it is
    # unambiguous. Per migration, exactly ONE ordinary (non-merge) commit added it — or none did and exactly ONE
    # merge commit did (a merge-result addition; `-m` re-lists a merged branch's additions in the merge, which
    # never count when an ordinary commit added the path). Anything else (re-adds, competing or identical
    # additions on several branches, several merge additions) is undetermined. Across migrations, the chosen
    # commits must form a strict ANCESTRY CHAIN: two migrations from one commit, or from commits on parallel
    # branches, have no knowable order — the whole plan is then undetermined and the operator orders it.
    seen, cur, idx = {}, None, 0
    for ln in out.splitlines():
        p = ln.strip()
        if p.startswith("@@"):
            h, *parents = p[2:].split()
            cur = (h, parents)
            continue
        if p in new:
            idx += 1
            seen.setdefault(p, []).append((idx, cur[0], cur[1]))
    chosen, ambiguous = {}, set()
    # LINEAGE (sweep, Codex post-merge on #304 and five rounds on #305): a migration moved, rewritten, copied
    # through intermediate names, replayed by merges or split into copy-then-delete carries an older migration's
    # age (or IS an applied one under a new name), and path-by-path reconstruction kept missing shapes. So: when ANY
    # diff in the range (merge parents included via -m, --no-renames, so moves show as D + A/M) deletes a migration,
    # lineage is unknown and EVERY new migration is undetermined; the operator reads the history before running
    # anything. Migration deletions are rare, so this costs little.
    rc, rout, err = _git_rc("log", "-m", "--no-renames", "--diff-filter=D", "--name-only", "--format=",
                            f"{before}..{after}")
    if rc != 0:
        raise SystemExit(f"✗ git log {before}..{after} failed ({err}) — refusing to plan migrations.")
    deleted_migrations = sorted({ln.strip() for ln in rout.splitlines() if MIGRATION_NAME.match(ln.strip())})
    lineage_unknown = bool(deleted_migrations)
    if lineage_unknown:
        ambiguous.update(new)
    # an UNCHANGED COPY of a migration introduced inside the range (source kept) would run one one-shot twice:
    # new migrations with identical content at `after` are undetermined (the prior-blob check above only sees
    # copies of migrations present at `before` — Codex on #305)
    by_blob = {}
    for m in sorted(new):
        by_blob.setdefault(_blob(after, m), []).append(m)
    for group in by_blob.values():
        if len(group) > 1:
            ambiguous.update(group)
    for p, apps in seen.items():
        if p in ambiguous:
            continue
        # a merge commit ADDS a path only when NONE of its parents had it (a merge-result addition, e.g. a
        # re-add in the merge); when a parent had it, `-m` is just re-listing that branch's addition (Codex on #304)
        adds = {h for _, h, parents in apps
                if len(parents) <= 1 or all(_blob(par, p) is None for par in parents)}
        pick = adds
        if len(pick) != 1:
            ambiguous.add(p)
            continue
        (h,) = pick
        chosen[p] = next(a for a in apps if a[1] == h)
    # order by TOPOLOGICAL position (parents before children), never by log/date order
    rc, out, err = _git_rc("rev-list", "--topo-order", "--reverse", f"{before}..{after}")
    if rc != 0:
        raise SystemExit(f"✗ git rev-list {before}..{after} failed ({err}) — refusing to plan migrations.")
    topo = {h: i for i, h in enumerate(out.split())}
    ordered = sorted(chosen, key=lambda p: (topo.get(chosen[p][1], len(topo)), p))
    together, unchained = set(), set()
    for a, b in zip(ordered, ordered[1:]):
        ha, hb = chosen[a][1], chosen[b][1]
        if ha == hb:
            together |= {a, b}                # one commit: git lists paths alphabetically, not by dependency
            continue
        rc, _, err = _git_rc("merge-base", "--is-ancestor", ha, hb)
        if rc == 1:
            unchained |= set(ordered)         # parallel branches: traversal order is not dependency order
        elif rc != 0:
            raise SystemExit(f"✗ ancestry check {ha}..{hb} failed ({err or f'git exit {rc}'}) — "
                             "refusing to plan migrations.")
    unplaced = sorted(new - set(ordered) - ambiguous)
    undetermined = sorted(together | unchained | ambiguous | set(unplaced))
    return {"forward": True, "run": [] if undetermined else ordered, "undetermined": undetermined,
            "new": ordered + sorted(ambiguous) + unplaced, "renamed": renamed,
            "modified": [m for m in found if m not in new and m not in renamed] + sorted(renamed),
            "skipped": [], "unordered": unplaced, "lineage_unknown": lineage_unknown,
            "deleted_migrations": deleted_migrations}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Deploy a release tag (production = tags only).")
    ap.add_argument("--tag", default=None, help="Exact release tag (vX.Y.Z); default: the latest.")
    ap.add_argument("--dry-run", action="store_true", help="Fetch and name the target; change nothing.")
    ap.add_argument("--run-migrations", nargs="+", metavar="MIGRATION", default=None,
                    help="Run these migrate_*.py files in order under one DB lock, after a daily backup "
                         "(the command a deploy prints).")
    ap.add_argument("--expect", default=None, metavar="SHA",
                    help="With --run-migrations: the release commit the plan was made for; refused otherwise.")
    ap.add_argument("--requirements-installed-by-hand", action="store_true",
                    help="The target's requirements were installed by hand: record that (receipted) instead of "
                         "running pip, so a release the auto-install refuses can be deployed.")
    a = ap.parse_args(argv)
    c.load_host_env()
    if a.run_migrations and a.dry_run:          # dry run changes nothing (Codex on #296)
        raise SystemExit("✗ --dry-run with --run-migrations: a dry run never backs up or migrates — refusing.")
    if a.run_migrations:
        return run_migrations(a.run_migrations, a.expect)
    if a.tag is not None and not c.release_key(a.tag):
        raise SystemExit(f"✗ --tag {a.tag!r} is not a release tag (vMAJOR.MINOR.PATCH) — refusing.")
    with c.db_lock():
        before, before_rel = git("rev-parse", "--short", "HEAD"), c.running_release()
        branch = git("rev-parse", "--abbrev-ref", "HEAD")
        if branch not in ("HEAD", "main"):
            raise SystemExit(f"✗ checkout is on branch {branch!r} — refusing (production runs tags only).")
        dirty = dirty_paths()
        if [p for p in dirty if p != "RESULTS.md"]:
            raise SystemExit(f"✗ local modifications {dirty} — refusing.")
        git("fetch", "--tags", "origin")               # a moved tag fails here (no clobber): refused
        tags = git("tag", "-l", "v*").split()
        target = a.tag or c.latest_release(tags)
        if target is None:
            raise SystemExit("✗ no release tag (vX.Y.Z) on origin — refusing; the host stays at "
                             f"{before_rel or before}. Production runs tags only; main is never pulled.")
        if target not in tags:
            raise SystemExit(f"✗ tag {target} not found on origin — refusing.")
        target_sha = git("rev-parse", "--short", f"{target}^{{commit}}")
        target_full = git("rev-parse", f"{target}^{{commit}}")
        # The migration plan is computed BEFORE the checkout moves (Codex on #296): a planning failure
        # (ancestry / tree / history unreadable) refuses here, with production still on `before`.
        changed = git("diff", "--name-only", before, target_sha).splitlines() if before != target_sha else []
        plan = migration_plan(before, target_sha, changed)
        req_blob, req_reason = requirements_plan(target_sha, changed)
        by_hand = a.requirements_installed_by_hand and (req_blob or (req_reason or "").startswith(REFUSE))
        if a.dry_run:
            print(f"DRY RUN: would deploy {before_rel or before} -> {target} ({target_sha})"
                  + (f"; new migrations, in order: {plan['run']}" if plan["run"] else "")
                  + (f"; new migrations whose order is NOT determinable (no command will be generated): "
                     f"{plan['new']}" if plan.get("undetermined") else "")
                  + (f"; this range DELETES migration(s) {plan['deleted_migrations']} (lineage unknown)"
                     if plan.get("lineage_unknown") else "")
                  + (f"; rollback skips {plan['skipped']}" if plan["skipped"] else "")
                  + (f"; requirements.txt {req_reason}: would be RECORDED as installed by hand (no pip run)"
                     if by_hand else "")
                  + (f"; requirements.txt {req_reason}: would run `{' '.join(pip_command())} install -r "
                     f"{REQUIREMENTS}` (the {target} file) before the checkout" if req_blob and not by_hand else "")
                  + ((f"; requirements.txt {req_reason}: the deploy would be REFUSED"
                      if req_reason.startswith(REFUSE) else f"; requirements.txt {req_reason}: nothing to install")
                     if req_reason and not req_blob and not by_hand else ""))
            return 0
        # PREFLIGHT the checkout BEFORE installing (Codex on #310): an untracked host file at a path the target
        # adds would make `git checkout` fail after pip had already installed the target's dependencies
        # --no-renames: a renamed DESTINATION is an addition too; every path prefix is checked, since an
        # untracked FILE (or symlink) at an ancestor directory blocks the checkout as well (Codex on #310)
        import os
        added = git("diff", "--name-only", "--no-renames", "--diff-filter=A", before, target_sha).splitlines() \
            if before != target_sha else []
        tracked_before = set(git("ls-tree", "-r", "--name-only", before).splitlines()) if added else set()

        def _blocks(p: str) -> bool:
            parts = p.split("/")
            for i in range(1, len(parts) + 1):
                q, rel = Path(c.REPO, *parts[:i]), "/".join(parts[:i])
                last = i == len(parts)
                if os.path.lexists(q) and rel not in tracked_before and (last or q.is_symlink() or not q.is_dir()):
                    if last and q.is_dir() and not q.is_symlink():
                        # git removes a directory tree that holds nothing it would lose: a TRACKED directory (whose
                        # files the target drops) or an untracked tree of only EMPTY directories; an untracked FILE or
                        # symlink inside blocks (Codex on #310)
                        # files AND symlinked directories (os.walk lists those under dirs and does not follow)
                        inside = [str(Path(root, n).relative_to(c.REPO)).replace(os.sep, "/")
                                  for root, dirs, files in os.walk(q)
                                  for n in files + [d for d in dirs if Path(root, d).is_symlink()]]
                        if all(t in tracked_before for t in inside):
                            continue
                    return True
            return False
        blockers = [p for p in added if _blocks(p)]
        if blockers:
            c.append_receipt({"kind": "deploy", "exit": 1, "from_sha": before, "tag": target,
                              "error": f"untracked files block the checkout: {blockers[:10]}"})
            print(f"✗ untracked file(s) on the host where {target} adds tracked ones: {blockers[:10]} — deploy refused "
                  f"before anything was installed; the host stays at {before_rel or before}. Move them aside.")
            return 1
        installed = False
        if by_hand:
            fp = requirements_fingerprint(target_sha)
            err = record_installed(manual_record(fp, target_sha) if (req_reason or "").startswith(REFUSE) else fp)
            c.append_receipt({"kind": "deploy_requirements", "exit": 1 if err else 0, "tag": target,
                              "to_sha": target_sha, "manual": True, "fingerprint": fp, "reason": req_reason,
                              **({"state_error": err} if err else {})})
            if err:
                print(f"✗ could not record the by-hand install ({err}) — deploy refused; the host stays at "
                      f"{before_rel or before}")
                return 1
            print(f"  requirements.txt {req_reason}: recorded as INSTALLED BY HAND (--requirements-installed-by-hand)")
            req_blob = req_reason = None
        if req_blob:
            req = install_requirements(target, target_sha, req_blob, req_reason)
            if req["exit"] == 0 and req.get("state_error"):
                c.append_receipt({"kind": "deploy", "exit": 1, "from_sha": before, "tag": target,
                                  "error": f"install record not written: {req['state_error']}"})
                print(f"✗ pip installed {target}'s requirements, but the install record could not be written "
                      f"({req['state_error']}) — deploy refused; the code stays at {before_rel or before} while the "
                      f"venv already holds {target}'s requirements. Fix the cause and deploy again.")
                return 1
            if req["exit"] != 0:
                c.append_receipt({"kind": "deploy", "exit": 1, "from_sha": before, "tag": target,
                                  "error": f"pip install exited {req['exit']}"})
                print(f"✗ pip install exited {req['exit']} — deploy refused; the code stays at {before_rel or before}. "
                      f"pip does not roll back packages it already upgraded in this run, so the venv may be "
                      f"PARTIALLY updated: fix the cause, run `{req['command']}` by hand from a checkout of "
                      f"{target}, then deploy again")
                return 1
            installed = True
        elif req_reason and req_reason.startswith(REFUSE):
            c.append_receipt({"kind": "deploy_requirements", "exit": 1, "tag": target, "to_sha": target_sha,
                              "error": f"requirements.txt {req_reason}"})
            c.append_receipt({"kind": "deploy", "exit": 1, "from_sha": before, "tag": target,
                              "error": f"requirements.txt {req_reason}"})
            print(f"✗ requirements.txt {req_reason} — deploy refused; the host stays at {before_rel or before}. "
                  f"Install the target's requirements by hand, then deploy again with "
                  f"--requirements-installed-by-hand.")
            return 1
        elif req_reason:
            c.append_receipt({"kind": "deploy_requirements", "exit": 0, "tag": target, "to_sha": target_sha,
                              "skipped": f"requirements.txt {req_reason}"})
            print(f"  ! requirements.txt {req_reason}: nothing installed — install the target's dependencies by hand")
        if dirty:
            git("checkout", "--", "RESULTS.md")
        try:
            git("checkout", "--quiet", "--detach", f"{target}^{{commit}}")
        except subprocess.CalledProcessError as e:
            c.append_receipt({"kind": "deploy", "exit": 1, "from_sha": before, "tag": target,
                              "error": f"checkout failed: {(e.stderr or '').strip()[:300]}",
                              "requirements_installed": installed})
            print(f"✗ checkout of {target} failed ({(e.stderr or '').strip()[:200]}) — the code stays at "
                  f"{before_rel or before}"
                  + (f"; NOTE the venv already has {target}'s requirements installed: re-run the deploy once the "
                     f"cause is fixed" if installed else ""))
            return 1
        after, after_rel = git("rev-parse", "--short", "HEAD"), c.running_release()
        # ARCHITECT-RULE 2026-10-02 (per-PR fragments): the fold runs in the tag ritual on main
        # (`ledger.py compile --commit`); the host never commits, so this step only REPORTS what the
        # deployed tag still carries uncompiled (expected 0).
        pending = sorted(str(p.relative_to(c.REPO)) for d in ("changelog.d", "docs/ledger/entries")
                         for p in (Path(c.REPO) / d).glob("*.md") if p.name != "README.md")
    c.append_receipt({"kind": "deploy", "exit": 0, "from_sha": before, "to_sha": after,
                      "from_release": before_rel, "to_release": after_rel, "tag": target,
                      "files_changed": len(changed), "new_migrations": plan["new"],
                      "migration_order_undetermined": plan["undetermined"], "renamed_migrations": plan["renamed"],
                      "deleted_migrations": plan.get("deleted_migrations", []),
                      "modified_migrations": plan["modified"], "rollback_migrations_skipped": plan["skipped"],
                      "requirements_installed": installed,
                      "ledger_fragments_pending": len(pending)})
    print(f"✓ deploy {before_rel or before} -> {after_rel} ({after}, {len(changed)} files)"
          + (f"\n  ✓ requirements installed ({REQUIREMENTS} {req_reason})" if installed else "")
          + (f"\n  ! new migrations, in the order they were added (backup first, then run by hand, in this "
             f"order): {plan['run']}\n      {migration_command(plan['run'], target_full)}" if plan["run"] else "")
          + (f"\n  ! new migrations whose ORDER (or identity) is not determinable (added together in one commit, "
             f"not placed by the history, or carrying another migration's lineage): {plan['new']} — no command "
             f"generated. Read the range's history first (`git log --no-renames --name-status {before}..{after}`; "
             f"`--follow` misses a rewritten move): a rename or copy of a migration that already ran must NOT "
             f"run again. Then run only the ones that are new, in order: "
             f"`sp_deploy.py --expect {target_full} --run-migrations <ordered names>` as the service user"
             + (" (any of them may be an applied migration under a new name: see the deletion warning)"
                if plan.get("lineage_unknown") else "")
             if plan.get("undetermined") else "")
          + (f"\n  ! this range DELETES migration(s) {plan['deleted_migrations']}: lineage is unknown. Any new "
             f"migration may be one of them under a new name (a rewritten move is invisible to `--follow`); "
             f"compare them with `git log --no-renames --name-status {before}..{after}` before running anything"
             if plan.get("lineage_unknown") else "")
          + (f"\n  ! renamed / copied migrations (already ran under the source name; NOT runnable): {plan['renamed']}"
             if plan.get("renamed") else "")
          + (f"\n  ! migrations MODIFIED in this range (not new; read before re-running): {plan['modified']}"
             if plan["modified"] else "")
          + (f"\n  ! rollback / non-forward deploy: migrations in the diff are NOT run (the target predates "
             f"them; the DB keeps its additive columns): {plan['skipped']}" if plan["skipped"] else "")
          + (f"\n  ! {len(pending)} ledger fragment(s) uncompiled in {target} — the tag was cut without "
             "`ledger.py compile` (docs/RELEASES.md step 2)" if pending else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
