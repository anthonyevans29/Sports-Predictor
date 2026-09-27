#!/usr/bin/env python3
"""The one sanctioned move (H0 section 5), as three receipted steps.

Manifest (H0-15, ruled 2026-09-27): the .backup DB, .env, the current exports/,
and the receipts log. Nothing else — the repo travels via git.

  LAPTOP  sp_migrate.py pack    --out /tmp/sp_pack_<stamp>
          .backup of the live DB (never cp), integrity_check, sha256 of every
          file, row counts for EVERY table (enumerated from sqlite_master —
          law 1), git sha -> MANIFEST.json. Refuses an --out under data/.
  (transfer the pack directory over the tailnet only: scp -r)
  HOST    sp_migrate.py verify  --pack <dir>
          every sha256 re-computed = manifest; integrity ok; every table
          count = manifest. PASS/FAIL receipt. Ties/partials are FAIL.
  HOST    sp_migrate.py install --pack <dir> [--replace]
          verify again, then place: sports.db -> data/sports.db (refused if
          one exists, unless --replace moves it aside as data/rehearsal_<ts>.db),
          env -> .env (0600), exports/* -> exports/, receipts -> a separate
          receipts.<source-host>.jsonl beside the host log (logs never merge).
          Re-verifies the installed DB (sha + counts) and receipts the result.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_common as c  # noqa: E402

DB, ENV, EXPORTS, RECEIPTS, MANIFEST = "sports.db", "env", "exports", "receipts.jsonl", "MANIFEST.json"


def pack(out: Path) -> int:
    c.refuse_under_data(out)
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"✗ {out} exists and is not empty.")
    out.mkdir(parents=True, exist_ok=True)
    os.chmod(out, 0o700)
    src = c.db_path()
    with c.db_lock():
        s, d = c.ro_connect(src), sqlite3.connect(out / DB)
        try:
            s.backup(d)
        finally:
            d.close()
            s.close()
    os.chmod(out / DB, 0o600)
    integ = c.integrity(out / DB)
    if integ != "ok":
        raise SystemExit(f"✗ integrity_check on the copy: {integ}")
    files = {DB: c.sha256_file(out / DB)}
    envp = c.REPO / ".env"
    if envp.exists():
        shutil.copyfile(envp, out / ENV)
        os.chmod(out / ENV, 0o600)
        files[ENV] = c.sha256_file(out / ENV)
    exp = c.REPO / "exports"
    if exp.is_dir():
        for p in sorted(exp.rglob("*")):
            if p.is_file():
                rel = Path(EXPORTS) / p.relative_to(exp)
                (out / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, out / rel)
                files[str(rel)] = c.sha256_file(out / rel)
    rp = c.receipts_path()
    if rp.exists():
        shutil.copyfile(rp, out / RECEIPTS)
        files[RECEIPTS] = c.sha256_file(out / RECEIPTS)
    man = {"created": c.iso(), "source_host": c.host_name(), "git_sha": c.git_sha(),
           "integrity": integ, "files": files, "counts": c.table_counts(out / DB),
           "absent": [n for n in (ENV, EXPORTS, RECEIPTS)
                      if not any(k == n or k.startswith(n + "/") for k in files)]}
    (out / MANIFEST).write_text(json.dumps(man, indent=1, sort_keys=True))
    rec = c.append_receipt({"kind": "migrate", "step": "pack", "exit": 0, "pack": str(out),
                            "db_sha256": files[DB], "n_files": len(files),
                            "n_tables": len(man["counts"]), "absent": man["absent"]})
    print(f"✓ PACK {out}: S1(db sha256)={files[DB]}\n  integrity={integ}  files={len(files)}  "
          f"tables={len(man['counts'])}  absent={man['absent'] or 'none'}  git={man['git_sha']}")
    for t, n in man["counts"].items():
        print(f"  R1 {t:32s} {n}")
    return 0 if rec else 1


def _verify(pk: Path, db_override: Path | None = None) -> tuple[bool, list[str], dict]:
    man = json.loads((pk / MANIFEST).read_text())
    problems = []
    for rel, sha in man["files"].items():
        p = db_override if (rel == DB and db_override) else pk / rel
        if not p.exists():
            problems.append(f"missing {rel}")
        elif c.sha256_file(p) != sha:
            problems.append(f"sha256 mismatch {rel}")
    dbp = db_override or pk / DB
    integ = c.integrity(dbp) if dbp.exists() else "missing"
    if integ != "ok":
        problems.append(f"integrity {integ}")
    counts = c.table_counts(dbp) if dbp.exists() else {}
    for t in sorted(set(man["counts"]) | set(counts)):
        if man["counts"].get(t) != counts.get(t) or counts.get(t) is None:
            problems.append(f"count {t}: R1={man['counts'].get(t)} R2={counts.get(t)}")
    return not problems, problems, {"man": man, "counts": counts, "integrity": integ}


def verify(pk: Path, step: str = "verify", db_override: Path | None = None) -> int:
    ok, problems, info = _verify(pk, db_override)
    c.append_receipt({"kind": "migrate", "step": step, "exit": 0 if ok else 1, "pack": str(pk),
                      "db_sha256": info["man"]["files"].get(DB), "problems": problems[:20]})
    print(f"{'✓ PASS' if ok else '✗ FAIL'} {step}: S2 {'=' if ok else '?'} S1 "
          f"({info['man']['files'].get(DB)}) integrity={info['integrity']} "
          f"tables={len(info['counts'])}")
    for t, n in info["counts"].items():
        print(f"  R2 {t:32s} {n}   (R1 {info['man']['counts'].get(t)})")
    for p in problems:
        print(f"  ✗ {p}")
    return 0 if ok else 1


def install(pk: Path, replace: bool) -> int:
    if verify(pk) != 0:
        return 1
    man = json.loads((pk / MANIFEST).read_text())
    if (pk / ENV).exists():  # the host resolves the DB through the pack's .env
        url = c.parse_env_file(pk / ENV).get("DATABASE_URL", "sqlite:///./data/sports.db")
        if not url.startswith("sqlite:///./"):
            raise SystemExit(f"✗ the pack's .env DATABASE_URL is {url!r} — refusing; on the host it "
                             f"must be sqlite:///./data/sports.db (edit the pack's env, re-run).")
        os.environ.pop("DATABASE_URL", None)
        c._DOTENV_CACHE = c.parse_env_file(pk / ENV)
    target = c.db_path()
    stamp = c.utc_now().strftime("%Y%m%dT%H%M%SZ")
    target.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(target.parent, 0o700)
    if target.exists():
        if not replace:
            raise SystemExit(f"✗ {target} exists — refusing (cutover: pass --replace to move the "
                             f"rehearsal DB aside).")
        for suf in ("", "-wal", "-shm"):
            q = Path(str(target) + suf)
            if q.exists():
                q.rename(target.with_name(f"rehearsal_{stamp}.db{suf}"))
    shutil.copyfile(pk / DB, target)
    os.chmod(target, 0o600)
    if (pk / ENV).exists():
        envp = c.REPO / ".env"
        if envp.exists() and c.sha256_file(envp) != man["files"][ENV] and not replace:
            raise SystemExit("✗ .env exists and differs — pass --replace.")
        shutil.copyfile(pk / ENV, envp)
        os.chmod(envp, 0o600)
    for rel in man["files"]:
        if rel.startswith(EXPORTS + "/"):
            dst = c.REPO / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists() and c.sha256_file(dst) != man["files"][rel] and not replace:
                raise SystemExit(f"✗ {rel} exists and differs — pass --replace.")
            shutil.copy2(pk / rel, dst)
    if (pk / RECEIPTS).exists():
        dst = c.receipts_path().with_name(f"receipts.{man['source_host']}.{stamp}.jsonl")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pk / RECEIPTS, dst)
    return verify(pk, step="install", db_override=target)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="H0 sanctioned migration (pack / verify / install).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("pack")
    p1.add_argument("--out", required=True, type=Path)
    for name in ("verify", "install"):
        p = sub.add_parser(name)
        p.add_argument("--pack", required=True, type=Path)
        if name == "install":
            p.add_argument("--replace", action="store_true")
    a = ap.parse_args(argv)
    c.load_host_env()
    if a.cmd == "pack":
        return pack(a.out)
    if a.cmd == "verify":
        return verify(a.pack)
    return install(a.pack, a.replace)


if __name__ == "__main__":
    sys.exit(main())
