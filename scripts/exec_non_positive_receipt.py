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
  desk.model_p, never re-derived. A row with no exec edge stored is counted, never read as zero (law 4). That edge is
  the GATE's (#87 (h): the order the PLAY would place at tier size); the final order's (exec.final_edge_pp, addendum 309
  item 1) is written from the next file on and is not read here, and the header says so in one line;
- a closing.match_ids that is not a list is read as none: every row of that file counts as outside the run's match_ids
  (a string, a number or an object is never iterated into ids).
A START is (family, start stamp), both read from the FILE NAME, which write_closing_file builds from them;
closing.family is never the key. Within the one file read for a start, a row repeated is counted once per match id.
THE AUTHORITATIVE COPY (#907, Codex's third review of #903, item 3): of the files holding one start, only the NEWEST is
read, whole. Newest is by exported_at when every copy carries one (then the folder, then the path), else by the folder
(then the path): a copy that cannot be read, or carries no exported_at, never ranks below one that does. Every other
copy is listed SUPERSEDED and none of its rows is counted, so a game the newer copy dropped (started, or called off) is
not re-added from a stale one. If the newest copy is unreadable, the start is UNREADABLE: an older copy never stands in
for it (law 4).
MALFORMED SHAPES (#907 items 1 and 2) are listed UNREADABLE and the run goes on: invalid JSON, a top level that is not
an object, or a `predictions` that is not a list (an object, a scalar, null, or no key at all) makes the file
unreadable, never an empty file; a row whose match_id is not an id (anything but an int or a string; a bool, a float,
None, a list, an object) is a malformed row, counted on its own UNREADABLE line and skipped.

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

GATE_LINE = ("  reads the stored GATE exec edge (desk.exec.edge_pp, the order the PLAY would place at tier size) on the "
             "files that exist; the final order's (desk.exec.final_edge_pp, addendum 309 item 1) is written from the "
             "next file on and is not read here")
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


def _match_ids(v) -> set:
    """closing.match_ids as a set; anything but a list is none (Codex P2 on #903: a string or an object was iterated
    into ids, a number raised); an element of a list that is not an int or a string (a float, a bool, a list, an
    object) is skipped, never hashed."""
    if not isinstance(v, list):
        return set()
    return {x for x in v if isinstance(x, (int, str)) and not isinstance(x, bool)}


def _f3(x) -> str:
    return f"{x:.3f}" if _num(x) else "not stored"


def _pp(x) -> str:
    return f"{x:+.2f}pp" if _num(x) else "not stored"


def _pick(row: dict, pick):
    return {"HOME": row.get("home_team"), "AWAY": row.get("away_team")}.get(pick, pick)


def _is_id(x) -> bool:
    """A row's match_id as an id: an int or a string, never a bool (the same rule as _match_ids)."""
    return isinstance(x, (int, str)) and not isinstance(x, bool)


def read_rows(files: list[tuple[str, str, Path]], root: Path):
    """(emitted PLAY rows, would-be PLAY rows, unreadable entries, distinct rows read, superseded copies, starts read).
    Every file joins its start's group, read or not; per start only the newest copy is read (#907 item 3), its others
    SUPERSEDED. A file that cannot be read (invalid JSON, a top level that is not an object, a `predictions` that is
    not a list) is UNREADABLE, and as the newest copy it makes its start unreadable (#907 item 2; law 4). A row whose
    match_id is not an id is malformed and listed (#907 item 1). The run always goes on."""
    plays, would, bad, seen, superseded = [], [], [], set(), []
    groups: dict = {}
    for role, day, f in files:
        m = NAME.match(f.name)
        why, doc = None, None
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            why = type(e).__name__
        else:
            if not isinstance(doc, dict):
                why = f"top level is {type(doc).__name__}, not an object"
            elif not isinstance(doc.get("predictions"), list):
                why = ("no predictions key" if "predictions" not in doc
                       else f"predictions is {type(doc['predictions']).__name__}") + ", not a list"
        at = doc.get("exported_at") if why is None else None
        groups.setdefault((m.group(1), f"{m.group(2)}T{m.group(3)}Z"), []).append(
            {"f": f, "day": day, "doc": doc, "why": why, "at": at if isinstance(at, str) and at else None})
    starts_read = 0
    for (fam, stamp), copies in sorted(groups.items()):
        if all(c["at"] for c in copies):
            copies.sort(key=lambda c: (c["at"], c["f"].parent.name, c["f"].as_posix()), reverse=True)
        else:                                             # a copy without a stamp (or unreadable) never ranks last
            copies.sort(key=lambda c: (c["f"].parent.name, c["f"].as_posix()), reverse=True)
        top, older = copies[0], copies[1:]
        superseded.extend((c["f"].relative_to(root), c["why"]) for c in older)
        if top["why"]:
            bad.append((top["f"].relative_to(root), top["why"]))
            continue
        starts_read += 1
        doc, f, day = top["doc"], top["f"], top["day"]
        cl = doc.get("closing") if isinstance(doc.get("closing"), dict) else {}
        ids = _match_ids(cl.get("match_ids"))
        for n, r in enumerate(doc["predictions"]):
            d = r.get("desk") if isinstance(r, dict) else None
            if not isinstance(d, dict):
                continue
            mid = r.get("match_id")
            if not _is_id(mid):                           # a bool, float, None, list or object is never a key
                bad.append((f.relative_to(root), f"prediction row {n}: match_id is {type(mid).__name__}, not an id "
                                                  "(row skipped)"))
                continue
            key = (fam, mid, stamp)
            if key in seen:
                continue
            seen.add(key)
            ex = d.get("exec") if isinstance(d.get("exec"), dict) else {}
            rec = {"fam": fam, "mid": mid, "day": day, "ko": r.get("utc_date"),
                   "pick": _pick(r, d.get("pick")), "edge": ex.get("edge_pp"), "basis": ex.get("basis"),
                   "cost": ex.get("cost"), "p": d.get("model_p"), "on_page": mid in ids,
                   "file": f.relative_to(root).as_posix()}
            if d.get("call") == "PLAY":
                plays.append(rec)
            h = d.get("market_only_hold")
            if (d.get("call") == "PASS" and d.get("pass_kind") == "market_only" and isinstance(h, dict)
                    and h.get("would_call") == "PLAY"):
                would.append(rec)
    return plays, would, bad, len(seen), superseded, starts_read


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
    say(GATE_LINE)
    for role in sorted({r for r, _, _ in files}) or ["(none)"]:
        mine = [(d, f) for r, d, f in files if r == role]
        days = [d for d, _ in mine]
        fams = Counter(NAME.match(f.name).group(1) for _, f in mine)
        say(f"  {role}: {len(mine)} closing file(s), dates {min(days) if days else '-'} .. "
            f"{max(days) if days else '-'}, by family {dict(sorted(fams.items()))}")
    plays, would, bad, n, superseded, starts_read = read_rows(files, root)
    for f, why in bad:
        say(f"  UNREADABLE {f.as_posix()}: {why}")
    for f, why in superseded:                             # an older copy that is also unreadable says so
        say(f"  SUPERSEDED {f.as_posix()}: an older copy of a start a newer file holds; none of its rows read"
            + (f"; also unreadable: {why}" if why else ""))
    say(f"\nfiles read: {starts_read} · superseded copies: {len(superseded)} · "
        f"rows de-duplicated by (family, match id, start stamp): {n}")
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
