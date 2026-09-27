#!/usr/bin/env python3
"""Run one chain from chains.py under the DB lock, writing receipts.

    sp_run.py <chain> [--set key=value ...] [--dry-run] [--operator]

- Steps run in order; the first non-zero exit stops the chain (its exit is
  the chain's exit, so systemd's OnFailure pages).
- One `step` receipt per step (exit, duration, last <=5 console lines,
  redacted) and one `chain` receipt per run (backup, counts, exports).
- A console line starting "SP-PAGE:" (improve's H0-5 hold) pages the
  operator via sp_notify and is receipted; the chain continues.
- `operator_only` chains (soccer-refresh, H0-6) refuse without --operator.
- `active_from` chains outside their window log a skipped receipt, exit 0.
- H0-16(b): SP_PARALLEL_MODE=designated + SP_DESIGNATED_DAYS=Fri,Sat,...
  skips METERED steps on other days (receipted as skipped). Default: full.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from collections import deque
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_common as c  # noqa: E402
from chains import CHAINS, UNMETERED, WINDOW_HOURS, WINDOW_KALSHI  # noqa: E402

TAIL = 5
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def date_vars(today: date) -> dict:
    sat = today + timedelta(days=(5 - today.weekday()) % 7)
    return {
        "today": today.isoformat(),
        "yesterday": (today - timedelta(days=1)).isoformat(),
        "tomorrow": (today + timedelta(days=1)).isoformat(),
        "sat": sat.isoformat(),
        "sat_plus3": (sat + timedelta(days=3)).isoformat(),
    }


def fullseason_steps() -> list[list[str]]:
    p = c.setting("SP_FULLSEASON_LIST")
    if not p or not Path(p).exists():
        raise SystemExit("✗ weekly-fullseason: SP_FULLSEASON_LIST missing — refusing to "
                         "guess the competition list (see hosting-h1.md step T9).")
    steps = []
    for line in Path(p).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        code, season = (x.strip() for x in line.split("|", 1))
        steps.append(["sync-matches", "--competition", code, "--season", season])
    if not steps:
        raise SystemExit(f"✗ weekly-fullseason: {p} lists no competitions.")
    return steps


def window_steps(now) -> list[list[str]]:
    """The window chain's plan, read-only from the DB (see chains.py)."""
    from datetime import timedelta
    hi = now + timedelta(hours=WINDOW_HOURS)
    skip = {s.strip().upper() for s in (c.setting("SP_SKIP_FAMILIES") or "").split(",") if s.strip()}
    fmt = "%Y-%m-%d %H:%M:%S"
    import sqlite3
    try:
        con = c.ro_connect(c.db_path())
    except (FileNotFoundError, sqlite3.Error):
        return [["window-card", "--hours", str(WINDOW_HOURS)]]
    try:
        comps = con.execute(
            "SELECT c.code, c.sport, m.season, COUNT(*) FROM matches m "
            "JOIN competitions c ON c.id = m.competition_id "
            "WHERE m.utc_date >= ? AND m.utc_date < ? AND m.status != 'FINISHED' "
            "GROUP BY c.code, c.sport, m.season ORDER BY MIN(m.utc_date), c.code",
            (now.strftime(fmt), hi.strftime(fmt))).fetchall()
    except sqlite3.Error:
        # a DB without the schema (host not bootstrapped): plan only the card
        # step, which then fails loudly and pages via OnFailure
        return [["window-card", "--hours", str(WINDOW_HOURS)]]
    finally:
        con.close()
    days = sorted({now.date().isoformat(), hi.date().isoformat()})
    steps: list[list[str]] = []
    for code, sport, season, _n in comps:
        if str(sport).upper() in skip:
            continue
        for d in days:
            steps.append(["sync-matches", "--competition", code, "--season", season,
                          "--date-from", d, "--date-to", d])
    football = False
    for code, sport, season, n in comps:
        if str(sport).upper() == "NFL":
            football = True
            continue
        steps.append(["sync-odds", "--competition", code, "--season", season, "--limit", str(n)])
    if football:
        steps.append(["sync-odds-football"])
    seen = set()
    for code, *_ in comps:
        for st in WINDOW_KALSHI.get(code, []):
            if tuple(st) not in seen:
                seen.add(tuple(st))
                steps.append(list(st))
    steps.append(["window-card", "--hours", str(WINDOW_HOURS)])
    return steps


def resolve(name: str, overrides: dict, today: date, now=None) -> list[list[str]]:
    chain = CHAINS[name]
    if chain.get("window_plan"):
        steps = window_steps(now or c.utc_now().replace(tzinfo=None))
    else:
        steps = fullseason_steps() if chain.get("fullseason") else chain["steps"]
    v = {**date_vars(today), **overrides}
    return [[a.format(**v) for a in st] for st in steps]


def metered_skip(cmd: str, today: date) -> bool:
    if (c.setting("SP_PARALLEL_MODE") or "full") != "designated":
        return False
    days = {d.strip()[:3].title() for d in (c.setting("SP_DESIGNATED_DAYS") or "").split(",")
            if d.strip()}
    return cmd not in UNMETERED and DAYS[today.weekday()] not in days


def page(msg: str, run_id: str) -> None:
    import sp_notify
    sp_notify.deliver(kind="page", title="sports-predictor: operator action", body=msg,
                      extra={"run_id": run_id})


def run_step(argv: list[str], run_id: str) -> tuple[int, list[str], float]:
    cmd = [sys.executable, "cli.py", *argv]
    t0 = time.monotonic()
    tail: deque = deque(maxlen=TAIL)
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "COLUMNS": "160"}
    proc = subprocess.Popen(cmd, cwd=c.REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, env=env, bufsize=1)
    for line in proc.stdout:
        sys.stdout.write(line)
        s = line.rstrip("\n")
        if s.strip():
            tail.append(c.redact(s))
        if s.startswith("SP-PAGE:"):
            page(c.redact(s), run_id)
    rc = proc.wait()
    return rc, list(tail), time.monotonic() - t0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run a sports-predictor chain with receipts.")
    ap.add_argument("chain", choices=sorted(CHAINS))
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help="override a date placeholder (e.g. sat=2026-09-29)")
    ap.add_argument("--dry-run", action="store_true", help="print resolved steps; run nothing")
    ap.add_argument("--operator", action="store_true",
                    help="required for operator-only chains (soccer-refresh, H0-6)")
    ap.add_argument("--unit", default=None, help="unit name for the receipt")
    a = ap.parse_args(argv)
    c.load_host_env()

    chain = CHAINS[a.chain]
    now = c.utc_now()
    today = now.date()
    overrides = dict(kv.split("=", 1) for kv in a.set)
    unit = a.unit or f"sp-chain@{a.chain}.service"
    run_id = f"{now.strftime('%Y%m%dT%H%M%SZ')}-{a.chain}"
    steps = resolve(a.chain, overrides, today, now=now.replace(tzinfo=None))

    if a.dry_run:
        for i, st in enumerate(steps, 1):
            tag = " [skip: H0-16b]" if metered_skip(st[0], today) else ""
            print(f"{i}. python cli.py {' '.join(st)}{tag}")
        print(f"backup: {chain.get('backup') or 'none'}")
        return 0

    if chain.get("operator_only") and not a.operator:
        print(f"✗ {a.chain} is OPERATOR-STARTED only (H0-6): re-run with --operator.")
        c.append_receipt({"kind": "chain", "unit": unit, "run_id": run_id, "exit": 2,
                          "refused": "operator_only"})
        return 2
    if chain.get("active_from") and today.isoformat() < chain["active_from"]:
        print(f"· {a.chain} inactive until {chain['active_from']} — skipped.")
        c.append_receipt({"kind": "chain", "unit": unit, "run_id": run_id, "exit": 0,
                          "skipped": f"inactive_until_{chain['active_from']}"})
        return 0

    import sp_backup
    t0 = time.monotonic()
    exports_before = {p: p.stat().st_mtime for p in (c.REPO / "exports").glob("*")} \
        if (c.REPO / "exports").exists() else {}
    backup_rec, chain_exit, ok = None, 0, 0
    quota = {"metered_run": 0, "metered_skipped": 0, "unmetered_run": 0, "provider_calls": None,
             "provider_calls_note": "not instrumented: api-sports call counts are not surfaced "
                                    "by the CLI (null, never 0)"}
    with c.db_lock():
        need = chain.get("backup")
        if need == "prerefresh" or (need == "daily" and sp_backup.todays_daily() is None):
            backup_rec = sp_backup.run_backup(need, lock=False)
            if backup_rec["exit"] != 0:
                chain_exit = 1
        elif need == "daily":
            p = sp_backup.todays_daily()
            backup_rec = {"file": p.name, "sha256": c.sha256_file(p), "integrity": "verified-sidecar"}

        if chain_exit == 0:
            for i, st in enumerate(steps, 1):
                line = f"python cli.py {' '.join(st)}"
                if metered_skip(st[0], today):
                    c.append_receipt({"kind": "step", "unit": unit, "run_id": run_id, "step": i,
                                      "command": line, "exit": None, "skipped": "H0-16b"})
                    quota["metered_skipped"] += 1
                    continue
                quota["metered_run" if st[0] not in UNMETERED else "unmetered_run"] += 1
                print(f"\n=== [{a.chain} {i}/{len(steps)}] {line}", flush=True)
                rc, tail, dur = run_step(st, run_id)
                c.append_receipt({"kind": "step", "unit": unit, "run_id": run_id, "step": i,
                                  "command": line, "exit": rc, "duration_s": round(dur, 1),
                                  "git_sha": c.git_sha(), "tail": tail})
                if rc != 0:
                    chain_exit = rc
                    break
                ok += 1

    exports = sorted(str(p.relative_to(c.REPO)) for p in (c.REPO / "exports").glob("*")
                     if exports_before.get(p) != p.stat().st_mtime) \
        if (c.REPO / "exports").exists() else []
    page_rec = None
    if chain_exit == 0 and chain.get("post") == "window_page":
        import sp_window_page
        page_rec = sp_window_page.run(c.REPO / "exports" / "window_24h.json")
    rec = {"kind": "chain", "unit": unit, "run_id": run_id, "exit": chain_exit,
           "steps_ok": ok, "steps_total": len(steps), "quota": quota,
           "duration_s": round(time.monotonic() - t0, 1),
           "counts": c.table_counts(c.db_path(), c.CHAIN_COUNT_TABLES), "exports": exports}
    if backup_rec is not None:
        rec["backup"] = {k: backup_rec.get(k) for k in ("file", "sha256", "integrity")}
    if page_rec is not None:
        rec["page"] = {k: page_rec.get(k) for k in ("deltas", "paged", "digest", "suppressed")}
    c.append_receipt(rec)
    print(f"  quota: metered steps run {quota['metered_run']} · skipped {quota['metered_skipped']} "
          f"· unmetered run {quota['unmetered_run']} · provider calls: not instrumented")
    print(f"\n{'✓' if chain_exit == 0 else '✗'} {a.chain}: exit={chain_exit} "
          f"steps {ok}/{len(steps)} in {rec['duration_s']}s")
    return chain_exit


if __name__ == "__main__":
    sys.exit(main())
