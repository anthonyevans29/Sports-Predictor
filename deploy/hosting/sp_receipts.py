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
        return f"steps {r.get('steps_ok')}/{r.get('steps_total')}; exports {len(r.get('exports') or [])}"
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
        return f"boot {r.get('boot_id', '')[:8]} kernel {r.get('kernel')} {r.get('reason') or ''}"
    if k == "deploy":
        return f"{r.get('from_sha')} -> {r.get('to_sha')}"
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
        b = (r.get("backup") or {}).get("sha256") or r.get("sha256") or ""
        ex = "—" if r.get("exit") is None else str(r.get("exit"))
        lines.append(f"| {r['ts'][5:16].replace('T', ' ')} | {r.get('host')} | {what} | "
                     f"{'**' + ex + '**' if failed(r) else ex} | {r.get('duration_s', '')} | "
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
    print(f"receipts since {a.since} on {c.host_name()}: {len(rs)} lines, {nfail} failing "
          f"(source {c.receipts_path()})\n")
    print(table(rs) if rs else "(no receipts in window)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
