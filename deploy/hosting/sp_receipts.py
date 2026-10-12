#!/usr/bin/env python3
"""The paste-ready receipts table for the architect (H0-19: the pasted table
is the H1 handoff).

    sp_receipts.py [--since 24h|7d|2026-10-08] [--steps]

Chain / backup / page / failure / boot / deploy lines, failures first, as a
markdown table: time, host, what, exit, duration, key line, backup sha prefix.
--steps adds per-step rows. Read-only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_common as c  # noqa: E402


def parse_since(s: str, now: datetime) -> datetime:
    m = re.fullmatch(r"(\d+)([hd])", s)
    if m:
        n = int(m.group(1))
        return now - (timedelta(hours=n) if m.group(2) == "h" else timedelta(days=n))
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def key_line(r: dict) -> str:
    k = r.get("kind")
    if k == "chain":
        if r.get("skipped") or r.get("refused"):
            return r.get("skipped") or f"refused: {r['refused']}"
        return (f"steps {r.get('steps_ok')}/{r.get('steps_total')}; exports {len(r.get('exports') or [])}"
                + (f"; {r['release']}" if r.get("release") else ""))
    if k == "backup":
        return f"{r.get('file')} integrity={r.get('integrity')}" + (
            f" ERROR {r['error']}" if r.get("error") else "")
    if k == "step":
        if r.get("skipped"):
            return f"skipped ({r['skipped']})"
        return (r.get("tail") or [""])[-1][:90]
    if k in ("page", "failure"):
        return f"{r.get('title')} (delivered={r.get('delivered')})"
    if k == "boot":
        return (f"boot {(r.get('boot_id') or '')[:8]} {r.get('release') or 'release ?'} kernel {r.get('kernel')} "
                f"{r.get('reason') or ''}")
    if k == "closing":                # addendum 45 (#408): the closing line's key line
        head = f"{r.get('family')} {r.get('start')}"
        if r.get("refused"):
            return f"{head} refused: {r['refused']}"
        if r.get("superseded"):
            return f"{head} superseded ({r.get('why')})"
        if r.get("failed"):
            return f"{head} attempt {r.get('attempt')} FAILED: {r['failed']}"
        push = r.get("push") or {}
        return (f"{head} attempt {r.get('attempt')} paged {len(r.get('covers') or [])} game(s); push exit "
                f"{push.get('exit')}" + (" FAILED" if r.get("push_failed") else ""))
    if k == "closing_miss":
        return f"{r.get('family')} {r.get('start')} MISSED: {r.get('reason')}"
    if k == "deploy":
        return (f"{r.get('from_release') or r.get('from_sha')} -> {r.get('to_release') or r.get('to_sha')}"
                f" ({r.get('to_sha')})")
    return ""


def failed(r: dict) -> bool:
    return r.get("kind") == "failure" or (r.get("exit") not in (0, None))


def rows(since: datetime, steps: bool) -> list[dict]:
    out = []
    p = c.receipts_path()
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("kind") == "step" and not steps:
            continue
        ts = datetime.fromisoformat(r["ts"].replace("Z", "+00:00"))
        if ts >= since:
            out.append(r)
    return out


def backup_sha(r: dict) -> str:
    """The backup sha for the table. Writers differ in shape (law 1, read
    2026-10-08): the chain receipt (sp_run.py) stores `backup` as a dict with
    `sha256`; the migrations receipt (sp_deploy.py) and the cleanup receipt
    (remove_allstar_rows.py) store `backup` as the file NAME string, the
    cleanup one with its sha beside it in `backup_sha256`; the backup receipt
    stores `sha256` at top level. A name with no sha shows empty (law 4: never
    a guessed sha); any other shape never crashes the table."""
    bk = r.get("backup")
    sha = bk.get("sha256") if isinstance(bk, dict) else None
    sha = sha or r.get("backup_sha256") or r.get("sha256")
    return sha if isinstance(sha, str) else ""


def duration(r: dict):
    """The dur s column. Writers differ (addendum 45, #408: "closing writes `seconds`, the table reads `duration_s`";
    the side that changes was left to the build): the chain and step receipts write `duration_s`, the closing receipt
    `seconds`. The table reads both; no receipt changes shape."""
    v = r.get("duration_s")
    return r.get("seconds", "") if v is None else v


def table(rs: list[dict]) -> str:
    rs = sorted(rs, key=lambda r: (not failed(r), r["ts"]))
    lines = ["| time (UTC) | host | what | exit | dur s | key line | backup sha |",
             "|---|---|---|---|---|---|---|"]
    for r in rs:
        what = r.get("unit") or r.get("kind")
        if r.get("kind") == "step":
            what = f"{r.get('run_id', '').split('-', 1)[-1]} #{r.get('step')}"
        elif r.get("kind") in ("backup", "page", "failure", "boot", "deploy"):
            what = r["kind"] + (f":{r['backup_kind']}" if r.get("backup_kind") else "")
        elif r.get("kind") in ("closing", "closing_miss"):
            what = f"{r['kind']}:{r.get('family')}"
        b = backup_sha(r)
        ex = "—" if r.get("exit") is None else str(r.get("exit"))
        lines.append(f"| {r['ts'][5:16].replace('T', ' ')} | {r.get('host')} | {what} | "
                     f"{'**' + ex + '**' if failed(r) else ex} | {duration(r)} | "
                     f"{key_line(r).replace('|', '/')} | {b[:12]} |")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="24h")
    ap.add_argument("--steps", action="store_true")
    a = ap.parse_args(argv)
    c.load_host_env()
    rs = rows(parse_since(a.since, c.utc_now()), a.steps)
    nfail = sum(failed(r) for r in rs)
    print(f"receipts since {a.since} on {c.host_name()} · running {c.running_release() or 'release ?'}: "
          f"{len(rs)} lines, {nfail} failing (source {c.receipts_path()})\n")
    print(table(rs) if rs else "(no receipts in window)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
