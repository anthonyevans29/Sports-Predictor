"""
THE EXEC <= 0 RECEIPT (ARCHITECT 2026-11-09 10:05 ET, addendum 305 item 2(d); 10:15 ET, addendum 306 item 2), READ-ONLY.

The request, verbatim (305 item 2(d)): "ONE RECEIPT in the PR body, read-only from the closing files the mirror holds
(host/<date>/closing_*.json since 2026-10-06, the laptop's closing files for MLB): the count of emitted PLAYs with
exec <= 0, by family, with match ids and dates — the record of how often the gap was walked through."
The form, verbatim (306 item 2): "the receipt is a read-only SCRIPT with a `--dir` (default exports/), so the PR body
carries the mirror's span and my laptop block runs the same script over the laptop's exports/ for 10-06 to 10-26, its
console on the PR [...]; the two spans together are the record. No file moves between machines."

WHAT IT READS: every closing file (`closing_<FAMILY>_<start stamp>.json`, deploy/hosting/closing.py's
write_closing_file) under --dir, in either layout: the machine's own exports/ (the files at its top) or the exports
mirror (<role>/<date>/). A folder named `latest` and every symbolic link are skipped (the mirror's latest/ copies the
dated files). --from / --through bound the start stamp's UTC date, both inclusive. Per file, its run's games
(closing.match_ids) and every prediction row's desk block, as closing.desk_rows reads them:
- an EMITTED PLAY is desk.call == "PLAY";
- a WOULD-BE PLAY (#446, the NFL market-only record: uncertified, unstaked, never a call) is desk.call "PASS" with
  pass_kind "market_only" and market_only_hold.would_call "PLAY", counted on its own block;
- the exec edge is desk.exec.edge_pp (its basis desk.exec.basis), the all-in cost desk.exec.cost, the model's price
  desk.model_p, never re-derived. A row with no exec edge stored is counted, never read as zero (law 4).
A row repeated across files of the same start is counted once per (family, match id, start stamp).

WHAT IT PRINTS: the files read by role and date span and family; per block the count, by family, with no exec edge,
with a basis other than taker, with exec <= 0 (each: family, match id, date, kickoff, pick, exec edge, all-in cost,
model price, the file) and with exec > 0; one SUMMARY line. Never a dollar figure, a unit size, a contract count, an
order text or an account id. It writes nothing, and exits 0 whatever it finds (2 on a --dir that is not a folder or a
malformed date).

    python scripts/exec_non_positive_receipt.py                       # the machine's exports/
    python scripts/exec_non_positive_receipt.py --dir ~/sports-predictor-exports
    python scripts/exec_non_positive_receipt.py --from 2026-10-06 --through 2026-10-26
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

NAME = re.compile(r"^closing_([A-Z0-9]+)_(\d{4}-\d{2}-\d{2})T(\d{4})Z\.json$")
ROLES = ("host", "laptop")


def closing_files(root: Path, since: date | None = None, through: date | None = None) -> list[tuple[str, str, Path]]:
    """(role, start date, path) for every closing file under root, sorted; no link followed, no latest/ read."""
    out = []
    for cur, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d != "latest" and not os.path.islink(os.path.join(cur, d)))
        for n in sorted(names):
            m = NAME.match(n)
            p = Path(cur) / n
            if not m or p.is_symlink() or not p.is_file():
                continue
            day = date.fromisoformat(m.group(2))
            if (since and day < since) or (through and day > through):
                continue
            parts = p.relative_to(root).parts
            role = next((r for r in parts[:-1] if r in ROLES), "exports")
            out.append((role, m.group(2), p))
    return sorted(out, key=lambda t: (t[0], t[1], t[2].name))


def _num(x) -> bool:
    """A stored, finite number; None, a bool, NaN or an infinity is "not stored" (law 4), never a figure."""
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _f3(x) -> str:
    return f"{x:.3f}" if _num(x) else "not stored"


def _pp(x) -> str:
    return f"{x:+.2f}pp" if _num(x) else "not stored"


def _pick(row: dict, pick):
    return {"HOME": row.get("home_team"), "AWAY": row.get("away_team")}.get(pick, pick)


def read_rows(files: list[tuple[str, str, Path]], root: Path):
    """(emitted PLAY rows, would-be PLAY rows, unreadable files, distinct rows read). A start re-paged into a later
    dated folder of the mirror leaves two copies of one closing file: the NEWEST copy of each (family, match id, start
    stamp) is the one read (by the file's exported_at, then its folder), as write_closing_file's replacement is."""
    plays, would, bad, seen = [], [], [], set()
    docs = []
    for role, day, f in files:
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            bad.append((f.relative_to(root), type(e).__name__))
            continue
        if not isinstance(doc, dict):
            bad.append((f.relative_to(root), f"top level is {type(doc).__name__}, not an object"))
            continue
        docs.append((str(doc.get("exported_at") or ""), f.parent.name, role, day, f, doc))
    docs.sort(key=lambda t: (t[0], t[1], t[4].as_posix()), reverse=True)
    for _, _, role, day, f, doc in docs:
        cl = doc.get("closing") if isinstance(doc.get("closing"), dict) else {}
        m = NAME.match(f.name)
        fam = cl.get("family") or m.group(1)
        stamp = f"{m.group(2)}T{m.group(3)}Z"
        ids = set(cl.get("match_ids") or [])
        preds = doc.get("predictions") if isinstance(doc.get("predictions"), list) else []
        for r in preds:
            d = r.get("desk") if isinstance(r, dict) else None
            if not isinstance(d, dict):
                continue
            key = (fam, r.get("match_id"), stamp)
            if key in seen:
                continue
            seen.add(key)
            ex = d.get("exec") if isinstance(d.get("exec"), dict) else {}
            rec = {"fam": fam, "mid": r.get("match_id"), "day": day, "ko": r.get("utc_date"),
                   "pick": _pick(r, d.get("pick")), "edge": ex.get("edge_pp"), "basis": ex.get("basis"),
                   "cost": ex.get("cost"), "p": d.get("model_p"), "on_page": r.get("match_id") in ids,
                   "file": f.relative_to(root).as_posix()}
            if d.get("call") == "PLAY":
                plays.append(rec)
            h = d.get("market_only_hold")
            if (d.get("call") == "PASS" and d.get("pass_kind") == "market_only" and isinstance(h, dict)
                    and h.get("would_call") == "PLAY"):
                would.append(rec)
    return plays, would, bad, len(seen)


def block(say, title: str, rows: list[dict]) -> list[dict]:
    on = sum(1 for x in rows if x["on_page"])
    say(f"\n{title}: {len(rows)} row(s) ({on} on their run's page, {len(rows) - on} outside the run's match_ids)")
    say(f"  by family: {dict(sorted(Counter(x['fam'] for x in rows).items()))}")
    noex = [x for x in rows if not _num(x["edge"])]
    say(f"  no exec edge stored: {len(noex)}" + ("".join(f"\n    {x['fam']} · match {x['mid']} · {x['file']}"
                                                         for x in noex)))
    say(f"  exec basis other than taker: {sum(1 for x in rows if _num(x['edge']) and x['basis'] != 'taker')}")
    le0 = [x for x in rows if _num(x["edge"]) and x["edge"] <= 0]
    say(f"  exec edge <= 0: {len(le0)} row(s) · by family {dict(sorted(Counter(x['fam'] for x in le0).items()))} · "
        f"distinct games {len({(x['fam'], x['mid']) for x in le0})}")
    for x in sorted(le0, key=lambda x: (x["fam"], x["day"], str(x["mid"]), x["file"])):
        say(f"    {x['fam']} · match {x['mid']} · {x['day']} · kickoff {x['ko']} · pick {x['pick']} · exec "
            f"{_pp(x['edge'])} · all-in cost {_f3(x['cost'])} · model {_f3(x['p'])} · "
            f"{'on page' if x['on_page'] else 'NOT on the run page'} · {x['file']}")
    say(f"  exec edge > 0: {sum(1 for x in rows if _num(x['edge']) and x['edge'] > 0)} row(s)")
    return le0


def run(root: Path, since: date | None, through: date | None, say=print) -> int:
    files = closing_files(root, since, through)
    say(f"ADDENDUM 305 RECEIPT · {root} (read-only) · start dates "
        f"{since.isoformat() if since else 'any'} .. {through.isoformat() if through else 'any'}")
    for role in sorted({r for r, _, _ in files}) or ["(none)"]:
        mine = [(d, f) for r, d, f in files if r == role]
        days = [d for d, _ in mine]
        fams = Counter(NAME.match(f.name).group(1) for _, f in mine)
        say(f"  {role}: {len(mine)} closing file(s), dates {min(days) if days else '-'} .. "
            f"{max(days) if days else '-'}, by family {dict(sorted(fams.items()))}")
    plays, would, bad, n = read_rows(files, root)
    for f, why in bad:
        say(f"  UNREADABLE {f.as_posix()}: {why}")
    say(f"\nfiles read: {len(files) - len(bad)} · rows de-duplicated by (family, match id, start stamp): {n}")
    le0 = block(say, "EMITTED PLAYs (desk.call PLAY)", plays)
    wle0 = block(say, "WOULD-BE PLAYs (NFL market-only, #446: a record, uncertified, unstaked, never a call)", would)
    say(f"\nSUMMARY: emitted PLAYs with exec <= 0: {len(le0)} row(s), {len({(x['fam'], x['mid']) for x in le0})} "
        f"distinct game(s); would-be PLAYs with exec <= 0: {len(wle0)} row(s), "
        f"{len({(x['fam'], x['mid']) for x in wle0})} distinct game(s); the span is the files listed above only.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Addendum 305 receipt: emitted PLAYs with exec edge <= 0 (read-only).")
    ap.add_argument("--dir", default="exports", help="a machine's exports/ or the exports mirror (default exports/)")
    ap.add_argument("--from", dest="since", help="first start date, YYYY-MM-DD (UTC), inclusive")
    ap.add_argument("--through", help="last start date, YYYY-MM-DD (UTC), inclusive")
    a = ap.parse_args(argv)
    root = Path(a.dir).expanduser()
    if not root.is_dir():
        print(f"REFUSED: --dir {root} is not a folder", file=sys.stderr)
        return 2
    try:
        since = date.fromisoformat(a.since) if a.since else None
        through = date.fromisoformat(a.through) if a.through else None
    except ValueError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    return run(root, since, through)


if __name__ == "__main__":
    sys.exit(main())
