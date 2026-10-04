#!/usr/bin/env python3
"""CUTOVER READINESS (#85; ARCHITECT build lane 2, 2026-10-04): one read-only
readout of the RULED cutover criteria (ARCHITECT 2026-10-02, verbatim):
"cutover when (a) 5 consecutive morning compares show only explained classes,
(b) the host has run a full day on a tag carrying #246 with desk calls
emitted, (c) parity harness green on that tag — earliest Oct 8 stands."

    cutover_readiness.py [--mirror DIR] [--receipts FILE] [--named FILE]
                         [--no-parity] [--today YYYY-MM-DD]
    python cli.py cutover-readiness …          (the same, from the CLI)

Prints, in order:
  (a) the compare streak: per date the exports mirror holds from BOTH writers
      (laptop/<date> vs host/<date>, the commit-status Action's own pairing),
      the verdict and the classes named for every divergent line;
  (b) the host's tag, days on it, whether it carries #246, and the desk calls
      emitted per chain (from the chain receipts + the mirrored host files);
  (c) the parity harness (scripts/desk_parity_verify.py) run ON THAT TAG, in a
      scratch git worktree outside the checkout;
  then one line: GO or NOT-YET, with every unmet criterion named.

Class naming (h2-cutover-runbook.md section 2) is CONSERVATIVE (law 4). The
tool names only what it can prove from the two files:
  - identical;
  - capture timing: every differing field is a market / Kalshi / price field
    (or a Desk field derived from them) on a matched row;
  - code-version skew: the comparator's guarded line (both files carry
    git_sha and they differ).
Anything else — a row or file on one side only (provider pagination, W1, W2
need evidence), a model probability, any other field — is UNNAMED. A date
with an UNNAMED line counts toward the streak only when --named FILE names
that date ({"2026-10-05": "provider pagination: <evidence>"}); such days are
printed as operator-named, and the architect's reading decides.

GO is a readiness readout, never the decision: cutover is the architect's
ruling (#85). Reads files only: no DB, no network, nothing written outside a
temporary worktree that is removed afterwards.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import compare_exports as ce  # noqa: E402
import sp_common as c  # noqa: E402

EARLIEST = date(2026, 10, 8)            # "earliest Oct 8 stands"
STREAK = 5                              # "(a) 5 consecutive morning compares"
CARRY_246 = "c2ac36e"                   # merge commit of #246 (git log, law 1)
PARITY_SCRIPT = "scripts/desk_parity_verify.py"
DATED = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Row-level fields whose difference is CAPTURE TIMING (runbook section 2:
# "fair_prob, market_divergence_pp, venue_gap_pp, prices or Kalshi fields
# differ on matched rows"), plus the fields computed from them.
CAPTURE_ROW_FIELDS = {
    "market", "kalshi", "kalshi_legs", "kalshi_exec", "line_move", "close_unpriced",
    "market_divergence_pp", "venue_gap_pp", "quarantine", "edge_pp", "model_edge_pp",
    "best_price", "best_bookmaker", "bookmaker_count", "bookmaker_count_quoted",
    "closing_price", "closing_bookmaker", "clv", "clv_pp",
    "desk",                              # the Desk call follows the market reference
}
CAPTURE_INPUT_QUALITY = {"book_odds", "kalshi"}
CAPTURE_DOC_FIELDS = {"kalshi_one_sided", "kalshi_two_sided", "desk_meta"}
ROW_PATH = re.compile(r"^\$\.(?P<list>[A-Za-z_]+)\[(?P<key>[^\]]+)\]\.(?P<rest>.+?)(?::|$)")


# ---------------------------------------------------------------- (a) compares

def classify_line(line: str) -> str | None:
    """'capture timing' when the diff line is a market-side field on a matched
    row (or a doc-level Kalshi count); None = unnamed."""
    path = line.split(": ", 1)[0]
    m = ROW_PATH.match(path + ":")
    if m:
        segs = [s for s in re.split(r"\.", re.sub(r"\[[^\]]*\]", "", m.group("rest"))) if s]
        if not segs:
            return None
        if segs[0] in CAPTURE_ROW_FIELDS:
            return "capture timing"
        if segs[0] == "input_quality" and len(segs) > 1 and segs[1] in CAPTURE_INPUT_QUALITY:
            return "capture timing"
        return None
    segs = [s for s in path.split(".") if s and s != "$"]
    if segs and segs[0] in CAPTURE_DOC_FIELDS:
        return "capture timing"
    return None


def compare_day(lap: Path, host: Path) -> dict:
    """Compare laptop/<date> with host/<date> as the mirror Action does
    (--since 0, every *.json) and name each divergent line's class."""
    la = {p.name: p for p in lap.glob("*.json")}
    ho = {p.name: p for p in host.glob("*.json")}
    files, classes, unnamed, compared = [], Counter(), [], 0
    for name in sorted(set(la) | set(ho)):
        if name not in la or name not in ho:
            unnamed.append(f"{name}: file only on {'host' if name not in la else 'laptop'}")
            continue
        try:
            x, y = json.loads(la[name].read_text()), json.loads(ho[name].read_text())
        except (OSError, ValueError) as e:
            unnamed.append(f"{name}: unparseable ({e})")
            continue
        compared += 1
        um: dict = {}
        lines = ce.diff(x, y, limit=10 ** 6, unmatched=um)
        only = [(s, k) for v in um.values() for s in ("laptop", "host") for k in v[s]]
        skew = ce.sha_line(x, y).startswith("code-version skew")
        if not lines and not only:
            classes["identical"] += 1
            continue
        for s, k in only:
            unnamed.append(f"{name}: row only on {s}: {k}")
        for ln in lines:
            cls = "code-version skew" if skew else classify_line(ln)
            if cls:
                classes[cls] += 1
            else:
                unnamed.append(f"{name}: {ln}")
        files.append(name)
    if compared == 0:
        verdict = "NO-COVERAGE"
    elif not files and not unnamed:
        verdict = "CLEAN"
    else:
        verdict = "DIVERGENT"
    return {"verdict": verdict, "compared": compared, "classes": dict(classes), "unnamed": unnamed}


def mirror_dates(mirror: Path) -> tuple[list[str], list[str]]:
    def ds(side):
        d = mirror / side
        return sorted(p.name for p in d.iterdir() if p.is_dir() and DATED.match(p.name)) if d.is_dir() else []
    return ds("laptop"), ds("host")


def streak(mirror: Path, named: dict, today: date) -> dict:
    """Per date (newest first) back to the first break: the compare and whether
    it counts. A date one writer has not pushed, or a calendar gap, breaks the
    streak; today is skipped while the laptop has not pushed it yet."""
    lap, hos = mirror_dates(mirror)
    both = sorted(set(lap) & set(hos), reverse=True)
    days, run, prev = [], 0, None
    for d in both:
        dd = date.fromisoformat(d)
        if prev is not None and (prev - dd).days != 1:
            days.append({"date": d, "break": f"gap: no common compare between {d} and {prev}"})
            break
        r = compare_day(mirror / "laptop" / d, mirror / "host" / d)
        r["date"] = d
        if r["verdict"] == "CLEAN" or (r["verdict"] == "DIVERGENT" and not r["unnamed"]):
            r["counts"], r["how"] = True, "machine-named"
        elif r["verdict"] == "DIVERGENT" and named.get(d):
            r["counts"], r["how"] = True, f"operator-named: {named[d]}"
        else:
            r["counts"], r["how"] = False, ("no coverage — not a data verdict" if r["verdict"] == "NO-COVERAGE"
                                            else f"{len(r['unnamed'])} UNNAMED line(s)")
        days.append(r)
        if not r["counts"]:
            break
        run += 1
        prev = dd
        if run >= STREAK:
            break
    newest = both[0] if both else None
    pending = [d for d in sorted(set(lap) ^ set(hos), reverse=True) if not newest or d > newest]
    return {"days": days, "run": run, "pending": pending, "laptop_dates": len(lap), "host_dates": len(hos)}


# ------------------------------------------------------------ (b) host on tag

def read_receipts(p: Path) -> list[dict]:
    out = []
    if not p.is_file():
        return out
    for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out


def git(*args, cwd: Path | None = None) -> tuple[int, str]:
    try:
        r = subprocess.run(["git", "-C", str(cwd or c.REPO), *args], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        return 127, str(e)
    return r.returncode, (r.stdout or "").strip() or (r.stderr or "").strip()


def carries(tag: str, commit: str = CARRY_246) -> bool | None:
    """True/False whether `tag` contains `commit`; None when git cannot tell."""
    if git("rev-parse", "--verify", "-q", f"{tag}^{{commit}}")[0] != 0:
        return None
    rc, _ = git("merge-base", "--is-ancestor", commit, tag)
    return True if rc == 0 else False if rc == 1 else None


def desk_rows(path: Path) -> Counter | None:
    """Desk calls a file carries: Counter(call) over rows with a desk block;
    None when the file is absent/unreadable, empty Counter when no desk blocks."""
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict):
        return Counter()
    rows = doc.get("predictions") or doc.get("fixtures") or []
    return Counter(r["desk"].get("call") for r in rows if isinstance(r, dict) and isinstance(r.get("desk"), dict))


def host_state(recs: list[dict], mirror: Path, now: datetime) -> dict:
    """The host's running tag (newest receipt), when it went onto it, and per
    UTC day on that tag: chains, failures, desk rows per chain."""
    rel_recs = [r for r in recs if r.get("ts") and r.get("release")]
    if not rel_recs:
        return {"tag": None}
    tag = rel_recs[-1]["release"]
    since = None
    for r in reversed(rel_recs):
        if r["release"] != tag:
            break
        since = r["ts"]
    on = [r for r in recs if r.get("release") == tag and r.get("ts") and r["ts"] >= since]
    days: dict[str, dict] = {}
    for r in on:
        if r.get("kind") != "chain":
            continue
        d = r["ts"][:10]
        day = days.setdefault(d, {"chains": [], "failed": 0, "desk_rows": 0})
        desk = Counter()
        seen_files = 0
        for e in r.get("exports") or []:
            name = Path(e).name
            if not name.endswith(".json"):
                continue
            got = desk_rows(mirror / "host" / d / name)
            if got is None:
                continue
            seen_files += 1
            desk.update(got)
        rows = sum(desk.values())
        day["desk_rows"] += rows
        day["failed"] += 1 if r.get("exit") not in (0, None) else 0
        day["chains"].append({"unit": r.get("unit"), "run_id": r.get("run_id"), "exit": r.get("exit"),
                              "skipped": r.get("skipped") or r.get("refused"), "desk_rows": rows,
                              "calls": dict(desk), "files_read": seen_files})
    t0 = datetime.fromisoformat(since.replace("Z", "+00:00"))
    if t0.tzinfo is None:
        t0 = t0.replace(tzinfo=timezone.utc)
    first_full = (t0 + timedelta(days=1)).date().isoformat() if (t0.hour, t0.minute, t0.second) != (0, 0, 0) \
        else t0.date().isoformat()
    full = [d for d in sorted(days) if first_full <= d < now.date().isoformat()
            and days[d]["chains"] and days[d]["failed"] == 0 and days[d]["desk_rows"] > 0]
    hosts = sorted({r.get("host") for r in on if r.get("host")})
    return {"tag": tag, "since": since, "days_on": round((now - t0).total_seconds() / 86400, 1),
            "days": days, "full_days": full, "hosts": hosts}


# --------------------------------------------------------------- (c) parity

def parity_on(tag: str) -> tuple[bool | None, str]:
    """scripts/desk_parity_verify.py run on `tag`'s own code, in a scratch
    worktree outside the checkout (no DB needed), removed afterwards."""
    if not c.release_key(tag):
        return None, f"{tag} is not a release tag — parity not run (criterion (c) is 'on that tag')"
    tmp = Path(tempfile.mkdtemp(prefix="sp-parity-"))
    wt = tmp / "wt"
    try:
        rc, out = git("worktree", "add", "-q", "--detach", str(wt), tag)
        if rc != 0:
            return None, f"worktree for {tag} failed: {out[-200:]}"
        if not (wt / PARITY_SCRIPT).is_file():
            return False, f"{PARITY_SCRIPT} absent on {tag}"
        try:
            r = subprocess.run([sys.executable, PARITY_SCRIPT], cwd=wt, capture_output=True, text=True,
                               timeout=600, env={**os.environ, "DATABASE_URL": f"sqlite:///{tmp / 'parity.db'}"})
        except (OSError, subprocess.SubprocessError) as e:
            return None, f"parity run failed to start: {e}"
        last = [ln for ln in (r.stdout or "").splitlines() if ln.strip()][-1:] or [(r.stderr or "")[-200:]]
        return r.returncode == 0, f"exit {r.returncode} · {last[0]}"
    finally:
        git("worktree", "remove", "--force", str(wt))
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------- report

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Cutover readiness against the ruled #85 criteria (read-only).")
    ap.add_argument("--mirror", type=Path,
                    default=Path(os.environ.get("SP_EXPORTS_MIRROR_DIR") or c.REPO / "logs" / "exports-mirror"),
                    help="a clone of Sports-Predictor-exports (default: the mirror's working clone)")
    ap.add_argument("--receipts", type=Path, default=None, help="the HOST's receipts.jsonl (default: this checkout's)")
    ap.add_argument("--named", type=Path, default=None,
                    help='JSON {"YYYY-MM-DD": "<class>: <evidence>"} naming a compare\'s UNNAMED lines')
    ap.add_argument("--no-parity", action="store_true", help="skip (c); it then reads NOT RUN")
    ap.add_argument("--today", default=None, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    now = datetime.now(timezone.utc)
    if a.today:
        now = datetime.combine(date.fromisoformat(a.today), datetime.min.time(), timezone.utc) + timedelta(hours=12)
    today = now.date()
    named = {}
    if a.named:
        try:
            named = {str(k): str(v) for k, v in json.loads(a.named.read_text()).items()}
        except (OSError, ValueError, AttributeError) as e:
            print(f"--named {a.named}: unreadable ({e}) — refused")
            return 2
    unmet = []

    print(f"CUTOVER READINESS (#85) · {now.strftime('%Y-%m-%d %H:%M')} UTC · writer of record "
          f"{c.writer_of_record() or 'UNKNOWN'}")
    print('ruled 2026-10-02: (a) 5 consecutive morning compares, only explained classes · (b) a full host day '
          'on a tag carrying #246, desk calls emitted · (c) parity green on that tag · earliest 2026-10-08')

    # (a)
    print(f"\n(a) COMPARE STREAK — mirror {a.mirror}")
    if not (a.mirror / ".git").exists() and not (a.mirror / "laptop").is_dir():
        print("    mirror clone not found — (a) cannot be read (pass --mirror DIR)")
        unmet.append("(a) no mirror clone")
    else:
        rc, head = git("log", "-1", "--format=%cI %s", cwd=a.mirror)
        print(f"    mirror HEAD: {head if rc == 0 else 'not a git clone (read as a folder)'}")
        s = streak(a.mirror, named, today)
        print(f"    dated folders: laptop {s['laptop_dates']} · host {s['host_dates']}"
              + (f" · pending (one side only): {', '.join(s['pending'])}" if s["pending"] else ""))
        for r in s["days"]:
            if "break" in r:
                print(f"    ✗ {r['break']}")
                continue
            cls = " · ".join(f"{k} {v}" for k, v in sorted(r["classes"].items())) or "—"
            print(f"    {'✓' if r['counts'] else '✗'} {r['date']}  {r['verdict']:<11} {r['compared']} compared · "
                  f"classes: {cls} · {r['how']}")
            for ln in r["unnamed"][:8]:
                print(f"        UNNAMED {ln[:160]}")
            if len(r["unnamed"]) > 8:
                print(f"        … {len(r['unnamed']) - 8} more UNNAMED")
        ops = sum(1 for r in s["days"] if r.get("counts") and str(r.get("how", "")).startswith("operator"))
        print(f"    streak: {s['run']}/{STREAK} consecutive"
              + (f" ({ops} operator-named — the architect's reading decides)" if ops else ""))
        if s["run"] < STREAK:
            unmet.append(f"(a) streak {s['run']}/{STREAK}")

    # (b)
    rp = a.receipts or c.receipts_path()
    print(f"\n(b) HOST ON TAG — receipts {rp}")
    recs = read_receipts(rp)
    hs = host_state(recs, a.mirror, now) if recs else {"tag": None}
    tag = hs.get("tag")
    if not tag:
        print("    no receipts with a release — (b) cannot be read (pass the HOST's --receipts)")
        unmet.append("(b) no host receipts")
    else:
        car = carries(tag) if c.release_key(tag) else False
        print(f"    host(s) {', '.join(hs['hosts']) or '?'} · running {tag} since {hs['since']} "
              f"({hs['days_on']} days) · carries #246: "
              f"{'yes' if car else 'NO' if car is False else 'unknown (tag not in this checkout — git fetch --tags)'}")
        for d in sorted(hs["days"]):
            day = hs["days"][d]
            print(f"    {d}: {len(day['chains'])} chain(s) · failed {day['failed']} · desk rows {day['desk_rows']}")
            for ch in day["chains"]:
                calls = " · ".join(f"{k} {v}" for k, v in sorted(ch["calls"].items())) or "no desk blocks"
                print(f"        {ch['unit'] or '?'} exit {ch['exit']}"
                      + (f" ({ch['skipped']})" if ch["skipped"] else "")
                      + f" · desk: {calls} ({ch['files_read']} file(s) read)")
        print(f"    full days on {tag} (every chain exit 0, desk calls emitted): "
              f"{', '.join(hs['full_days']) or 'none yet'}")
        if not c.release_key(tag):
            unmet.append(f"(b) host runs {tag}, not a release tag")
        elif car is not True:
            unmet.append(f"(b) {tag} does not carry #246" if car is False else f"(b) #246 on {tag} unknown")
        elif not hs["full_days"]:
            unmet.append(f"(b) no full day on {tag} yet")

    # (c)
    print("\n(c) PARITY HARNESS on the host's tag")
    if a.no_parity or not tag:
        print("    NOT RUN" + (" (--no-parity)" if a.no_parity else " (no host tag)"))
        unmet.append("(c) parity not run")
    else:
        ok, line = parity_on(tag)
        print(f"    {tag}: {'GREEN' if ok else 'FAILED' if ok is False else 'NOT RUN'} · {line}")
        if ok is not True:
            unmet.append(f"(c) parity {'failed' if ok is False else 'not run'} on {tag}")

    if today < EARLIEST:
        unmet.append(f"earliest {EARLIEST} (today {today})")
    print("\n" + ("GO — every ruled criterion is met on the record above. Cutover is the architect's ruling (#85)."
                  if not unmet else "NOT-YET — " + " · ".join(unmet)))
    return 0 if not unmet else 1


if __name__ == "__main__":
    sys.exit(main())
