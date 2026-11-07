"""
THE EARLY-ENTRY ARM, ITS TABLE (#862; ARCHITECT 2026-11-07 08:55 ET, addendum 283 item 4), READ-ONLY.

The ruling, verbatim in part (addendum 283 item 4): "the #446-class receipt script gains the arm's table (count, mean
early CLV, flip count and cost, breaches) in cents and units only — never a dollar figure, never a contract count on a
public surface (238, 250)".

A #446-CLASS SCRIPT (scripts/qb_hold_receipt.py's pattern: read-only, the ledger's fills under the ledger's labels,
the closing files as the pages, a count toward thirty, the read the architect's): the arm is the PL Desk's and needs
cents, while qb_hold_receipt is NFL's QB hold and prints no price at all (223 item 5(a)), so the arm's table is this
sibling script, not a section of that one (an open question on #862).

Sources: --ledger, the Cockpit's "Export ledger (JSON)" file (bd_ledger_v1_<date>.json: calls, fills), and --exports,
the closing files (closing_*.json at its top and in its dated folders <YYYY-MM-DD>/, never latest/). The attribution is
src/walters/early_arm.attribute (the arm's kinds over ledger_fills.classify_fills, unchanged). The table: early fills,
mean early CLV in cents per contract, flips, flip cost in cents per contract, breaches, interest rows (their own kind),
the count toward thirty (early + flips, the export's rows, with the distinct games beside it). The breaches are
LISTED by the closing page's match id and teams and the breach's cause only, under their own head: CONSOLE ONLY, NOT
FOR POSTING until the architect rules where the list goes (it names the operator's own games; the 235 item 2(c)
--unmatched precedent), and never in the JSON. Everything above that head is counts and cents only.

Never printed: a dollar figure, a quantity or contract count, a fee, a stake, a P&L, a fill's id (it carries the
account id), a fill price (early_price and flip_exit_price are read, never printed: only the cents difference per
contract is), an order's text or contracts, the interest's amount or rate. Writes nothing.

Refusals (exit 2, nothing printed but the refusal): --ledger missing or unreadable, or not a bd_ledger_v1 export (no
calls array; fills not an array of objects); --exports not a directory; --exports a latest/ folder, or a dated-named
folder of it resolving to one (early_arm.LatestRefused, the 232 item 2(c) rule).

Last line: EARLY-ARM-RECEIPT {json} (counts and cents only).

    python3 scripts/early_arm_receipt.py --ledger bd_ledger_v1_<date>.json [--exports DIR]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REFUSED = 2
RULING_283_4 = ("the import's attribution gains the early fill — a fill on a match BEFORE that match's closing run, on "
                "the side the closing page PLAYs → attributed to the closing call with early = true, early_price and "
                "early_clv_cents; a fill before the closing run on a match the closing page PASSes or whose side it "
                "changed → \"arm flip\", paired with its pre-kickoff exit fill and its flip_cost_cents; a fill AFTER "
                "kickoff on an arm position → \"arm breach\", listed; the #446-class receipt script gains the arm's "
                "table (count, mean early CLV, flip count and cost, breaches) in cents and units only — never a dollar "
                "figure, never a contract count on a public surface (238, 250); the bulletins carry nothing of the arm "
                "beyond the word \"early\" on a call line.")


BREACH_HEAD = ("BREACHES LISTED (console only, NOT FOR POSTING until ruled: they name the operator's own games; "
               "never in the JSON)")


class Refused(Exception):
    """A refusal: printed as REFUSED, exit 2."""


def read_ledger(path) -> dict:
    try:
        with open(path) as fh:
            L = json.load(fh)
    except (OSError, ValueError) as e:
        raise Refused(f"--ledger {path}: cannot read the ledger export ({type(e).__name__}); nothing read") from None
    if not isinstance(L, dict) or not isinstance(L.get("calls"), list) or any(not isinstance(c, dict)
                                                                            for c in L["calls"]):
        raise Refused(f"--ledger {path}: not a bd_ledger_v1 export (no calls array of objects); nothing read")
    fills = L.get("fills") or []
    if not isinstance(fills, list) or any(not isinstance(f, dict) for f in fills):
        raise Refused(f"--ledger {path}: fills is not an array of objects; nothing read")
    return {"calls": L["calls"], "fills": fills, "system_picks": L.get("system_picks") or []}


def report(L: dict, exports_dir, echo=print) -> dict:
    from src.walters import early_arm as ea
    pages = ea.closing_pages(exports_dir)            # LatestRefused propagates: main refuses before printing
    rows = ea.attribute(L, pages=pages)
    t = ea.arm_table(rows)
    echo("EARLY-ARM RECEIPT — the early-entry arm's fills, attributed (#862), read-only")
    echo(f"RULING (ARCHITECT 2026-11-07 08:55 ET, addendum 283 item 4, verbatim in part): \"{RULING_283_4}\"")
    bad = f" · unreadable {len(pages['unreadable'])}: {', '.join(pages['unreadable'])}" if pages["unreadable"] else ""
    echo(f"SOURCES: the ledger (bd_ledger_v1: calls {len(L['calls'])}, fills {len(L['fills'])}) · the closing files "
         f"{Path(exports_dir).resolve()} (closing_*.json there and in its dated folders {pages['dated']}, never "
         f"latest/): {pages['files']} read, events {len(pages['by_event'])}{bad}")
    for ln in ea.table_lines(t):
        echo(ln)
    breaches = [r for r in rows if r.get("arm_breach")]
    if breaches:
        echo(BREACH_HEAD)
    for r in breaches:
        page = pages["by_event"].get(ea.event_of(r.get("ticker"))) or {}
        echo(f"  {ea.ARM_BREACH}: match {page.get('match_id')} {page.get('away') or '?'} @ "
             f"{page.get('home') or '?'} (kickoff {ea._iso(page.get('kickoff'))}): {r['breach_why']}")
    summary = {k: v for k, v in t.items()}
    summary.update(closing_files=pages["files"], unreadable=len(pages["unreadable"]))
    echo("EARLY-ARM-RECEIPT " + json.dumps(summary, sort_keys=True))
    return {"rows": rows, "table": t, "summary": summary}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="#862 (addendum 283 item 4): the early-entry arm's table — read-only")
    ap.add_argument("--ledger", required=True, help="the Cockpit's Export ledger (JSON) file, bd_ledger_v1_<date>.json")
    ap.add_argument("--exports", default="exports", help="the directory holding closing_*.json, at its top and in its "
                                                         "dated folders <YYYY-MM-DD>/ (latest/ never read)")
    a = ap.parse_args(argv)
    from src.walters.early_arm import LatestRefused
    try:
        L = read_ledger(a.ledger)
        if not Path(a.exports).is_dir():
            raise Refused(f"--exports {a.exports}: not a directory; nothing read")
    except Refused as err:
        print(f"REFUSED: {err}")
        return REFUSED
    lines: list[str] = []
    try:
        report(L, a.exports, echo=lines.append)
    except LatestRefused as err:
        print(f"REFUSED: {err}")
        return REFUSED
    for ln in lines:
        print(ln)
    return 0


if __name__ == "__main__":
    sys.exit(main())
