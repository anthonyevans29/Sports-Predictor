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
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TS_KEY = re.compile(r"(_at$|^ts$|timestamp|^generated|^captured|^as_of)", re.I)


def rows_of(doc) -> int | None:
    if isinstance(doc, list):
        return len(doc)
    if isinstance(doc, dict):
        lens = [len(v) for v in doc.values() if isinstance(v, list)]
        return max(lens) if lens else None
    return None


def diff(a, b, path="$", out=None, limit=40) -> list[str]:
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if TS_KEY.search(str(k)):
                continue
            if k not in a or k not in b:
                out.append(f"{path}.{k}: only in {'host' if k not in a else 'laptop'}")
            else:
                diff(a[k], b[k], f"{path}.{k}", out, limit)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: length {len(a)} vs {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            diff(x, y, f"{path}[{i}]", out, limit)
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
    clean = True
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
        d = diff(x, y)
        mark = "✓" if not d else "✗"
        clean &= not d
        print(f"{mark} {name}: rows laptop={rows_of(x)} host={rows_of(y)} diffs={len(d)}")
        for line in d[:15]:
            print(f"    {line}")
    print(f"\n{'CLEAN' if clean else 'DIVERGENT'} ({len(set(la) & set(ho))} compared) — "
          f"each divergence needs an explanation (capture timing | provider pagination) "
          f"or a BACKLOG entry.")
    return 0 if clean else 1


if __name__ == "__main__":
    sys.exit(main())
