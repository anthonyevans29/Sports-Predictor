#!/usr/bin/env python3
"""Parallel-week export comparison (H0 5.4 step 12; cutover criterion
"export diffs clean on the last 3 days").

    compare_exports.py <laptop_exports_dir> <host_exports_dir> [--glob '*2026-10-08*']

For every same-named JSON file in both: record counts (top-level list, or the
longest list value in a top-level object) and a field-level diff with
timestamp-like keys ignored (*_at, ts, timestamp, generated*, captured*).
Files present on one side only are listed. Output is paste-ready; exit 0 only
when every compared file is identical after the timestamp mask. Read-only.

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
from pathlib import Path

TS_KEY = re.compile(r"(_at$|^ts$|timestamp|^generated|^captured|^as_of)", re.I)
# machine-local or reported separately — never a field diff
MASKED = {"match_id", "git_sha"}
KICKOFF, HOME, AWAY = ("utc_date", "kickoff", "date"), ("home_team", "home"), ("away_team", "away")


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
    ap = argparse.ArgumentParser()
    ap.add_argument("laptop", type=Path)
    ap.add_argument("host", type=Path)
    ap.add_argument("--glob", default="*.json")
    a = ap.parse_args(argv)
    la = {p.name: p for p in a.laptop.glob(a.glob)}
    ho = {p.name: p for p in a.host.glob(a.glob)}
    clean, skew_names = True, set()
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
    classes = "capture timing | provider pagination | code-version skew (only where named above)"
    print(f"\n{'CLEAN' if clean else 'DIVERGENT'} ({len(set(la) & set(ho))} compared) — "
          f"each divergence needs an explanation ({classes}) or a BACKLOG entry."
          + (f" Code-version skew named for: {', '.join(sorted(skew_names))}." if skew_names else ""))
    return 0 if clean else 1


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
