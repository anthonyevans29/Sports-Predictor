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
after a backup (hosting-h1.md, "Deploying a release").
"""
from __future__ import annotations

import argparse
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


MIGRATION_NAME = re.compile(r"^migrate_[A-Za-z0-9_]+\.py$")


def run_migrations(scripts: list[str], expect_sha: str | None) -> int:
    """Backup, then each migration in order, all under one DB lock; the first failure stops
    the run. Receipted step by step. Only top-level migrate_*.py files of this checkout, and
    only when HEAD is still the release the plan was made for (`--expect`, Codex on #296:
    after another deploy, the same names could hold different migration logic)."""
    import sp_backup
    if not expect_sha:
        raise SystemExit("✗ --run-migrations needs --expect <sha> (the deploy prints it) — refusing.")
    for m in scripts:
        if not MIGRATION_NAME.match(m) or not (c.REPO / m).is_file():
            raise SystemExit(f"✗ {m!r} is not a migrate_*.py file in {c.REPO} — refusing.")
    with c.db_lock():
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
        return {"forward": True, "run": [], "modified": [], "skipped": [], "unordered": []}
    rc, _, err = _git_rc("merge-base", "--is-ancestor", before, after)
    if rc == 1:
        return {"forward": False, "run": [], "modified": [], "skipped": found, "unordered": []}
    if rc != 0:
        raise SystemExit(f"✗ ancestry check {before}..{after} failed ({err or f'git exit {rc}'}) — "
                         "refusing to plan migrations.")
    new = _root_migrations(after) - _root_migrations(before)
    rc, out, err = _git_rc("log", "--reverse", "-m", "--diff-filter=A", "--name-only", "--format=",
                           f"{before}..{after}")
    if rc != 0:
        raise SystemExit(f"✗ git log {before}..{after} failed ({err}) — refusing to plan migrations.")
    ordered = []
    for ln in out.splitlines():
        p = ln.strip()
        if p in new and p not in ordered:
            ordered.append(p)
    unordered = sorted(new - set(ordered))
    return {"forward": True, "run": ordered + unordered, "unordered": unordered,
            "modified": [m for m in found if m not in new], "skipped": []}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Deploy a release tag (production = tags only).")
    ap.add_argument("--tag", default=None, help="Exact release tag (vX.Y.Z); default: the latest.")
    ap.add_argument("--dry-run", action="store_true", help="Fetch and name the target; change nothing.")
    ap.add_argument("--run-migrations", nargs="+", metavar="MIGRATION", default=None,
                    help="Run these migrate_*.py files in order under one DB lock, after a daily backup "
                         "(the command a deploy prints).")
    ap.add_argument("--expect", default=None, metavar="SHA",
                    help="With --run-migrations: the release commit the plan was made for; refused otherwise.")
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
        if a.dry_run:
            print(f"DRY RUN: would deploy {before_rel or before} -> {target} ({target_sha})"
                  + (f"; new migrations, in order: {plan['run']}" if plan["run"] else "")
                  + (f"; rollback skips {plan['skipped']}" if plan["skipped"] else ""))
            return 0
        if dirty:
            git("checkout", "--", "RESULTS.md")
        git("checkout", "--quiet", "--detach", f"{target}^{{commit}}")
        after, after_rel = git("rev-parse", "--short", "HEAD"), c.running_release()
        # ARCHITECT-RULE 2026-10-02 (per-PR fragments): the fold runs in the tag ritual on main
        # (`ledger.py compile --commit`); the host never commits, so this step only REPORTS what the
        # deployed tag still carries uncompiled (expected 0).
        pending = sorted(str(p.relative_to(c.REPO)) for d in ("changelog.d", "docs/ledger/entries")
                         for p in (Path(c.REPO) / d).glob("*.md") if p.name != "README.md")
    c.append_receipt({"kind": "deploy", "exit": 0, "from_sha": before, "to_sha": after,
                      "from_release": before_rel, "to_release": after_rel, "tag": target,
                      "files_changed": len(changed), "new_migrations": plan["run"],
                      "modified_migrations": plan["modified"], "rollback_migrations_skipped": plan["skipped"],
                      "ledger_fragments_pending": len(pending)})
    print(f"✓ deploy {before_rel or before} -> {after_rel} ({after}, {len(changed)} files)"
          + (f"\n  ! new migrations, in the order they were added (backup first, then run by hand, in this "
             f"order): {plan['run']}\n      {migration_command(plan['run'], target_full)}" if plan["run"] else "")
          + (f"\n  ! the history did not place {plan['unordered']} (appended last): check their order before "
             "running" if plan.get("unordered") else "")
          + (f"\n  ! migrations MODIFIED in this range (not new; read before re-running): {plan['modified']}"
             if plan["modified"] else "")
          + (f"\n  ! rollback / non-forward deploy: migrations in the diff are NOT run (the target predates "
             f"them; the DB keeps its additive columns): {plan['skipped']}" if plan["skipped"] else "")
          + (f"\n  ! {len(pending)} ledger fragment(s) uncompiled in {target} — the tag was cut without "
             "`ledger.py compile` (docs/RELEASES.md step 2)" if pending else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
