#!/usr/bin/env python3
"""Parallel-week export comparison (H0 5.4 step 12; cutover criterion
"export diffs clean on the last 3 days").

    compare_exports.py <laptop_exports_dir> <host_exports_dir> [--glob '*2026-10-08*'] [--since 3]

For every same-named JSON file in both: record counts (top-level list, or the
longest list value in a top-level object) and a field-level diff with
timestamp-like keys ignored (*_at, ts, timestamp, generated*, captured*).
Files present on one side only are listed. Output is paste-ready. Exit 0 =
CLEAN (every compared file identical after the timestamp mask), 1 = DIVERGENT,
2 = ERROR (the comparison could not run: bad arguments, a side directory
missing, a crash), 3 = NO-COVERAGE (nothing was compared: zero JSON files on
both sides in the window — an empty folder, or Markdown-only dated folders).
2 and 3 are never data verdicts; CLEAN needs at least one compared file. A
"coverage:" line always counts the JSON compared and the files the glob left
out. The last line always reads "VERDICT: CLEAN|DIVERGENT|ERROR|NO-COVERAGE".
Read-only.

--since N (architect 2026-10-01; default 3): only files whose name carries a
YYYY-MM-DD date within the last N UTC days (today and the N-1 days before)
are compared, so settled exhibits stop re-printing. Files with NO date in
their name (window_24h.json, fixtures_<comp>_<label>.json) are always
compared — never hidden by the window (law 4). The skipped files are counted
on the header line, never silently dropped. --since 0 compares everything.

H1b (amended 2026-09-27): the two sides are INDEPENDENT pipelines (each
syncs from the providers itself). The explained divergence classes are
capture timing AND provider-pagination differences. Anything else is a
BACKLOG entry.

Exhibit 1 ruling (2026-09-28):
- Game rows (lists of dicts with home/away) are KEYED on (kickoff, home,
  away), never match_id (machine-local ids differ between the two DBs). Rows
  are compared field-by-field only AFTER keying; rows on one side only are
  reported BY NAME. `match_id` is masked everywhere.
- A third explained class, CODE-VERSION SKEW, is available only with its
  guard: both files carry the producing `git_sha` and the comparator names the
  mismatch. A file missing its SHA cannot claim the class (law 4).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# Standalone (PR #261 review): the exports mirror ships THIS file alone into
# Sports-Predictor-exports/tools/, where sp_common.py does not exist. In the
# repo, the writer of record comes from sp_common (env, host env file, .env);
# shipped, from the SP_WRITER_OF_RECORD environment variable only.
WRITERS = ("laptop", "host")
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from sp_common import writer_of_record  # noqa: E402
except ImportError:
    def writer_of_record() -> str | None:
        import os
        v = (os.environ.get("SP_WRITER_OF_RECORD") or "").strip()
        return v if v in WRITERS else None

# Exit codes — a data verdict is never confused with a broken run:
#   0 CLEAN · 1 DIVERGENT · 2 ERROR (bad arguments, a missing side, a crash) ·
#   3 NO-COVERAGE (zero files compared: never a clean verdict; PR #261 review).
EXIT_CLEAN, EXIT_DIVERGENT, EXIT_ERROR, EXIT_NO_COVERAGE = 0, 1, 2, 3

TS_KEY = re.compile(r"(_at$|^ts$|timestamp|^generated|^captured|^as_of)", re.I)
# machine-local or reported separately — never a field diff
MASKED = {"match_id", "git_sha"}
KICKOFF, HOME, AWAY = ("utc_date", "kickoff", "date"), ("home_team", "home"), ("away_team", "away")


NAME_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def name_date(name: str) -> date | None:
    """The first valid YYYY-MM-DD in a file name, else None (undated)."""
    for m in NAME_DATE.finditer(name):
        try:
            return date.fromisoformat(m.group(1))
        except ValueError:
            continue
    return None


def in_window(name: str, since: int, today: date) -> bool:
    """True when the file is compared under --since: undated files always;
    dated files when today - date < since days; since <= 0 = everything."""
    d = name_date(name)
    return since <= 0 or d is None or (today - d) < timedelta(days=since)


def _first(d: dict, keys):
    for k in keys:
        if d.get(k) not in (None, ""):
            return d[k]
    return None


def is_game_rows(v) -> bool:
    return (isinstance(v, list) and v and all(isinstance(r, dict) for r in v)
            and all(_first(r, HOME) is not None and _first(r, AWAY) is not None for r in v))


def row_key(r: dict) -> str:
    ko = str(_first(r, KICKOFF) or "?")[:16]
    return f"{_first(r, AWAY)} @ {_first(r, HOME)} {ko}"


def keyed(rows: list) -> dict:
    out: dict = {}
    for r in rows:
        k = row_key(r)
        n = 2
        while k in out:                      # a true double-header keeps both rows
            k = f"{row_key(r)} #{n}"
            n += 1
        out[k] = r
    return out


def rows_of(doc) -> int | None:
    if isinstance(doc, list):
        return len(doc)
    if isinstance(doc, dict):
        lens = [len(v) for v in doc.values() if isinstance(v, list)]
        return max(lens) if lens else None
    return None


def diff(a, b, path="$", out=None, limit=40, unmatched=None) -> list[str]:
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if TS_KEY.search(str(k)) or k in MASKED:
                continue
            if k not in a or k not in b:
                out.append(f"{path}.{k}: only in {'host' if k not in a else 'laptop'}")
            else:
                diff(a[k], b[k], f"{path}.{k}", out, limit, unmatched)
    elif is_game_rows(a) and is_game_rows(b):
        ka, kb = keyed(a), keyed(b)            # key FIRST, then compare pairs
        if unmatched is not None:
            unmatched.setdefault(path, {"laptop": [], "host": []})
            unmatched[path]["laptop"] += sorted(set(ka) - set(kb))
            unmatched[path]["host"] += sorted(set(kb) - set(ka))
        for k in sorted(set(ka) & set(kb)):
            diff(ka[k], kb[k], f"{path}[{k}]", out, limit, unmatched)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: length {len(a)} vs {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            diff(x, y, f"{path}[{i}]", out, limit, unmatched)
    elif a != b:
        out.append(f"{path}: {str(a)[:60]!r} vs {str(b)[:60]!r}")
    return out


def main(argv=None) -> int:
    """CLEAN 0 / DIVERGENT 1 / ERROR 2; the last line printed names the verdict."""
    try:
        return _main(argv)
    except SystemExit as e:                   # argparse: --help is 0, a usage error is 2
        if e.code in (0, None):
            raise
        print(f"VERDICT: ERROR (usage, exit {e.code}) — not a data verdict")
        return EXIT_ERROR
    except Exception as e:                    # noqa: BLE001 — a crash is an ERROR, never DIVERGENT
        print(f"VERDICT: ERROR ({type(e).__name__}: {e}) — the comparison did not run; not a data verdict")
        return EXIT_ERROR


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("laptop", type=Path)
    ap.add_argument("host", type=Path)
    ap.add_argument("--glob", default="*.json")
    ap.add_argument("--since", type=int, default=3,
                    help="Compare only files dated (YYYY-MM-DD in the name) within the last N UTC days; "
                         "undated files always compared; 0 = everything. Default 3.")
    ap.add_argument("--today", default=None, help=argparse.SUPPRESS)   # tests pin the clock
    a = ap.parse_args(argv)
    today = date.fromisoformat(a.today) if a.today else datetime.now(timezone.utc).date()
    missing = [f"{side}={d}" for side, d in (("laptop", a.laptop), ("host", a.host)) if not d.is_dir()]
    if missing:                               # an absent side must never read as "0 compared, CLEAN"
        print(f"VERDICT: ERROR (side directory missing: {', '.join(missing)}) — not a data verdict")
        return EXIT_ERROR
    la_all = {p.name: p for p in a.laptop.glob(a.glob)}
    ho_all = {p.name: p for p in a.host.glob(a.glob)}
    la = {n: p for n, p in la_all.items() if in_window(n, a.since, today)}
    ho = {n: p for n, p in ho_all.items() if in_window(n, a.since, today)}
    settled = len(set(la_all) | set(ho_all)) - len(set(la) | set(ho))
    wor = writer_of_record()
    print(f"writer of record: {wor or 'UNKNOWN (SP_WRITER_OF_RECORD unset/invalid)'} — canonical side: "
          f"{wor or '?'}" + (f"; divergences are read as the {'host' if wor == 'laptop' else 'laptop'} "
                              f"side departing from it" if wor else ""))
    if a.since > 0:
        print(f"window: --since {a.since} → files dated {today - timedelta(days=a.since - 1)} .. {today} "
              f"(UTC) + undated; {settled} settled file(s) earlier not re-printed")
    clean, skew_names, compared = True, set(), 0
    for name in sorted(set(la) | set(ho)):
        if name not in la or name not in ho:
            print(f"· {name}: only on {'host' if name not in la else 'laptop'}")
            clean = False
            continue
        try:
            x, y = json.loads(la[name].read_text()), json.loads(ho[name].read_text())
        except json.JSONDecodeError as e:
            print(f"✗ {name}: unparseable ({e})")
            clean = False
            continue
        compared += 1
        um: dict = {}
        d = diff(x, y, unmatched=um)
        only = {s: [k for v in um.values() for k in v[s]] for s in ("laptop", "host")}
        ok = not d and not only["laptop"] and not only["host"]
        clean &= ok
        sha = sha_line(x, y)
        skew_names.update([name] if sha.startswith("code-version skew") else [])
        print(f"{'✓' if ok else '✗'} {name}: rows laptop={rows_of(x)} host={rows_of(y)} "
              f"diffs={len(d)} · {sha}")
        for side in ("laptop", "host"):
            if only[side]:
                print(f"    only on {side} ({len(only[side])}): " + "; ".join(only[side][:12])
                      + (" …" if len(only[side]) > 12 else ""))
        for line in d[:15]:
            print(f"    {line}")
    other = {side: sorted(f.name for f in d.iterdir() if f.is_file() and f.name not in names)
             for side, d, names in (("laptop", a.laptop, la_all), ("host", a.host, ho_all))}
    one_side = len(set(la) ^ set(ho))
    print(f"\ncoverage: {compared} JSON file(s) compared ({a.glob}) · {one_side} on one side only · "
          f"{settled} outside the window · not matched by {a.glob}: laptop {len(other['laptop'])}, "
          f"host {len(other['host'])}" + (f" (e.g. {', '.join((other['laptop'] + other['host'])[:3])})"
                                          if other['laptop'] or other['host'] else ""))
    if clean and compared == 0:
        print(f"NO COVERAGE — no {a.glob} file was compared on both sides; nothing is verified, so this is "
              f"not a clean verdict.")
        print("VERDICT: NO-COVERAGE (0 compared) — not a data verdict")
        return EXIT_NO_COVERAGE
    classes = "capture timing | provider pagination | code-version skew (only where named above)"
    print(f"{'CLEAN' if clean else 'DIVERGENT'} ({compared} compared) — "
          f"each divergence needs an explanation ({classes}) or a BACKLOG entry."
          + (f" Code-version skew named for: {', '.join(sorted(skew_names))}." if skew_names else ""))
    print(f"VERDICT: {'CLEAN' if clean else 'DIVERGENT'}")
    return EXIT_CLEAN if clean else EXIT_DIVERGENT


def sha_line(x, y) -> str:
    """The code-version-skew guard: the class is claimable ONLY when both files
    carry their producing git_sha and they differ; a missing SHA is named."""
    sa = x.get("git_sha") if isinstance(x, dict) else None
    sb = y.get("git_sha") if isinstance(y, dict) else None
    if sa and sb:
        return (f"code-version skew: laptop {sa} ≠ host {sb}" if sa != sb
                else f"same code {sa}")
    missing = [s for s, v in (("laptop", sa), ("host", sb)) if not v]
    return f"git_sha missing on {' + '.join(missing)} — code-version skew NOT claimable"


if __name__ == "__main__":
    sys.exit(main())
