"""
CLOSING FILE BACKFILL (ARCHITECT 2026-10-11, addendum 40 item 2, #428), run ONCE on the laptop:

"THE BACKFILL, in the same PR: a script the operator runs once on the laptop, read-only on the database. For every
closing receipt whose page went out, it finds the export's bytes in the exports-mirror clone's history by the
receipt's sha256, reduces them to the receipt's Desk rows and writes the closing file under the same name rule, its
modification time set to the run's page time. One line per run. A run whose bytes are not found is listed and nothing
is rebuilt for it. That history begins at today's squash (06:10Z), so it reaches every watch-started run, and the next
squash (2026-10-18 06:10Z) drops it: the script has to run before then."

- Never opens the database. It reads the receipts (logs/receipts.jsonl, SP_RECEIPTS), the mirror clone's git history
  (SP_EXPORTS_MIRROR_DIR, default logs/exports-mirror: every blob of every commit, any role) and writes only
  exports/closing_<FAMILY>_<start>.json through closing.closing_doc / closing_name, the rule the runs use.
- The page time: the receipt's page.at (runs from this PR on), else its completed_at (the moment the steps finished,
  just before the page; the line says which).
- A receipt that already names its closing file (a run from this PR on) is skipped. A file of that name already on
  disk with the same bytes is UNCHANGED; with other bytes it is KEPT and listed, never overwritten.
- The rows are the export's rows for the receipt's Desk rows, in the export's order; the receipt's called-off games are
  named in the closing block. The next push from this machine carries the files (mirror dated folder = page time).

    python3 scripts/closing_file_backfill.py [--dry-run] [--mirror DIR] [--receipts FILE] [--exports DIR]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))
import closing as mc  # noqa: E402
import sp_common as c  # noqa: E402


def mirror_blobs(clone: Path) -> dict:
    """{sha256 of the bytes: bytes} for every .json blob reachable from any ref of the clone."""
    if not (clone / ".git").exists() and not (clone / "HEAD").exists():
        raise SystemExit(f"no exports-mirror clone at {clone} (SP_EXPORTS_MIRROR_DIR)")
    objs = subprocess.run(["git", "-C", str(clone), "rev-list", "--all", "--objects"], capture_output=True,
                          text=True, check=True).stdout.splitlines()
    ids = sorted({ln.split(" ", 1)[0] for ln in objs if " " in ln and ln.rstrip().endswith(".json")})
    if not ids:
        return {}
    p = subprocess.run(["git", "-C", str(clone), "cat-file", "--batch"], input=("\n".join(ids) + "\n").encode(),
                       capture_output=True, check=True)
    out, buf, i = {}, p.stdout, 0
    while i < len(buf):
        nl = buf.index(b"\n", i)
        head = buf[i:nl].split()
        if len(head) < 3 or head[1] != b"blob":        # "<id> missing" or a non-blob: no body follows
            i = nl + 1
            continue
        size = int(head[2])
        data = buf[nl + 1:nl + 1 + size]
        out[hashlib.sha256(data).hexdigest()] = data
        i = nl + 1 + size + 1
    return out


def closing_receipts(path: Path) -> list[dict]:
    out = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return out
    for ln in lines:
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if r.get("kind") == "closing" and mc._paged(r):
            out.append(r)
    return out


def page_time(r: dict) -> tuple[float | None, str]:
    if (r.get("page") or {}).get("at"):
        return mc.parse_utc(r["page"]["at"]).timestamp(), "page.at"
    if r.get("completed_at"):
        return mc.parse_utc(r["completed_at"]).timestamp(), "completed_at"
    return None, "none"


def rebuild(r: dict, blobs: dict, exports: Path, dry_run: bool) -> dict:
    fam, start = r.get("family"), r.get("start")
    res = {"run_id": r.get("run_id"), "family": fam, "start": start}
    if r.get("closing_file"):
        return {**res, "status": "SKIPPED", "why": f"the run wrote {r['closing_file'].get('file')} itself"}
    sha = (r.get("export_written") or {}).get("sha256")
    raw = blobs.get(sha) if sha else None
    if raw is None:
        return {**res, "status": "NOT FOUND", "why": ("the receipt records no export sha256" if not sha else
                                                      f"sha256 {sha[:12]} in no blob of the mirror's history"),
                "sha256": sha}
    s = mc.parse_utc(start)
    ids = [x.get("match_id") for x in r.get("desk_rows") or []]
    doc = mc.closing_doc(json.loads(raw), fam, s, r.get("run_id"), ids, r.get("called_off") or [])
    name = mc.closing_name(fam, s)
    mtime, src = page_time(r)
    text = json.dumps(doc, indent=2)
    dest = exports / name
    res.update({"file": f"{exports.name}/{name}", "rows": doc["count"], "page_time": src, "sha256": sha})
    missing = sorted(set(ids) - set(doc["closing"]["match_ids"]), key=str)
    if missing:
        res["rows_not_in_export"] = missing
    if dest.exists():
        same = dest.read_text() == text
        return {**res, "status": "UNCHANGED" if same else "KEPT", **({} if same else
                {"why": "a file of that name with other bytes is on disk: not overwritten"})}
    if dry_run:
        return {**res, "status": "WOULD WRITE"}
    c.refuse_under_data(exports)
    exports.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{name}.tmp")
    tmp.write_text(text)
    if mtime is not None:
        os.utime(tmp, (mtime, mtime))
    os.replace(tmp, dest)
    return {**res, "status": "WRITTEN"}


def line(x: dict) -> str:
    t = f"{x['status']:<11} {x['family']} {x['start']} · run {x['run_id']}"
    if x.get("file"):
        t += f" · {x['file']} · {x['rows']} row(s) · mtime from {x['page_time']}"
    if x.get("rows_not_in_export"):
        t += f" · Desk rows not in the export: {x['rows_not_in_export']}"
    if x.get("why"):
        t += f" · {x['why']}"
    return t


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="addendum 40 item 2: rebuild the closing files of past closing runs")
    ap.add_argument("--dry-run", action="store_true", help="list what would be written, write nothing")
    ap.add_argument("--mirror", help="the exports-mirror clone (default SP_EXPORTS_MIRROR_DIR or logs/exports-mirror)")
    ap.add_argument("--receipts", help="the receipts file (default SP_RECEIPTS or logs/receipts.jsonl)")
    ap.add_argument("--exports", help="where the closing files go (default exports/)")
    a = ap.parse_args(argv)
    clone = Path(a.mirror or c.setting("SP_EXPORTS_MIRROR_DIR") or c.REPO / "logs" / "exports-mirror")
    rec_path = Path(a.receipts) if a.receipts else c.receipts_path()
    exports = Path(a.exports) if a.exports else c.REPO / "exports"
    c.refuse_under_data(exports)
    recs = closing_receipts(rec_path)
    blobs = mirror_blobs(clone)
    print(f"closing receipts whose page went out: {len(recs)} · mirror blobs (.json, every ref): {len(blobs)} · "
          f"the database is not opened" + (" · DRY RUN: nothing written" if a.dry_run else ""))
    out = [rebuild(r, blobs, exports, a.dry_run) for r in recs]
    for x in out:
        print(line(x))
    counts: dict = {}
    for x in out:
        counts[x["status"]] = counts.get(x["status"], 0) + 1
    print("CLOSING-BACKFILL " + json.dumps({"runs": len(out), **counts}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
