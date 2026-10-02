"""
P0-2 (#207) BEFORE/AFTER RECEIPT for the close contract on a REAL export
(ARCHITECT-RULE 2026-10-01: "Gate-class: before/after on a real export of
each kind, receipted"). Read-only: compares two export files of the same
kind, matched by match_id. Works on all three kinds:

  predictions (MLB / soccer)  row["market"]["selections"][SEL]["fair_prob"]
  NFL predictions             row["market"]["fair_prob"][SEL]
  fixtures                    row["market"]["fair_prob"][SEL]

Laptop recipe (one per kind; the DB never travels):
  git checkout main                      && python cli.py <export cmd> ... -> BEFORE
  git checkout claude/close-contract-p0-2 && python cli.py <same cmd>    -> AFTER
  python3 scripts/export_close_compare.py BEFORE.json AFTER.json

Prints per kind: rows, priced before/after, NEWLY UNPRICED (with the
missing-leg receipt), fair-prob movement (mean / max |delta| pp over rows
priced on both sides), book-count changes (quoted vs complete), and the
largest movers. Writes nothing.
"""
import json
import sys


def rows_of(doc):
    for k in ("predictions", "fixtures"):
        if isinstance(doc.get(k), list):
            return k, doc[k]
    raise SystemExit("not an export file: no predictions/fixtures list")


def fair(row):
    mk = row.get("market") or {}
    if isinstance(mk.get("fair_prob"), dict):
        return {k: v for k, v in mk["fair_prob"].items() if v is not None} or None
    sels = mk.get("selections") or {}
    out = {k: v.get("fair_prob") for k, v in sels.items() if v.get("fair_prob") is not None}
    return out or None


def books(row):
    mk = row.get("market") or {}
    return mk.get("bookmaker_count"), mk.get("bookmaker_count_quoted")


def unpriced(row):
    return row.get("close_unpriced") or (row.get("market") or {}).get("close_unpriced")


def label(row):
    return f"{row.get('match_id')} {row.get('away_team') or '?'} @ {row.get('home_team') or '?'} {row.get('utc_date', '')[:16]}"


def main(a_path, b_path):
    ka, ra = rows_of(json.load(open(a_path)))
    kb, rb = rows_of(json.load(open(b_path)))
    A = {r.get("match_id"): r for r in ra}
    B = {r.get("match_id"): r for r in rb}
    common = [m for m in A if m in B]
    deltas, newly, regained, bk_changed = [], [], [], 0
    for m in common:
        fa, fb = fair(A[m]), fair(B[m])
        if fa and not fb:
            newly.append(m)
        elif fb and not fa:
            regained.append(m)
        elif fa and fb:
            d = max(abs(fb[k] - fa[k]) for k in fa if k in fb) * 100 if set(fa) & set(fb) else 0.0
            deltas.append((d, m))
        if books(A[m])[0] != books(B[m])[0]:
            bk_changed += 1
    deltas.sort(reverse=True)
    moved = [d for d, _ in deltas if d > 0.005]
    print(f"kind: {ka}  ·  before {len(A)} rows  ·  after {len(B)} rows  ·  matched {len(common)}")
    print(f"priced: before {sum(1 for m in common if fair(A[m]))}  ·  after {sum(1 for m in common if fair(B[m]))}")
    print(f"NEWLY UNPRICED (contract: no complete book): {len(newly)}")
    for m in newly:
        print(f"  {label(B[m])}  receipt {json.dumps(unpriced(B[m]))}")
    if regained:
        print(f"priced after but not before (unexpected — investigate): {len(regained)}  {regained}")
    print(f"fair prob moved (>0.005pp) on {len(moved)}/{len(deltas)} rows priced both sides"
          + (f"  ·  mean |Δ| {sum(moved) / len(moved):.2f}pp  ·  max {moved[0]:.2f}pp" if moved else ""))
    print(f"bookmaker_count changed (now = complete books): {bk_changed}")
    for d, m in deltas[:10]:
        if d <= 0.005:
            break
        print(f"  {d:5.2f}pp  {label(B[m])}  fair {json.dumps(fair(A[m]))} -> {json.dumps(fair(B[m]))}  "
              f"books {books(A[m])} -> {books(B[m])}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2]))
