"""
THE VALUE-SHADOW RECEIPT (ARCHITECT 2026-10-15, addendum 79 item 2; for the n=30 ruling Monday 2026-10-19, #86),
READ-ONLY:

"Law 1 first: say where the ledger's "value_shadow_graded" count comes from today (desk_policy.COUNT_KEYS; the
closing files read "counts_source: default 0 (no ledger summary)" — so what produces the summary, and why the laptop's
closing runs read none). Then `scripts/value_shadow_receipt.py`: every value shadow the ledger holds (staked or not;
the operator's small stakes on shadows are logged "value shadow, staked"), per row: date, game, side, edge_pp at the
call, the close, the result, won/lost/push/ungraded, units; totals: graded n, record, units net, and the same over the
rows with a close only. No dollar figure anywhere (units only). Paste-whole output; tests on a kept ledger shape. If
the ledger holds no shadow rows at all, the receipt says so and Monday's ruling is "n=0 of 30"."

WHERE value_shadow_graded COMES FROM TODAY (read from the code, main c51324d):
- desk_policy.COUNT_KEYS names it beside postseason_graded and kalshi_only_graded. The Python Desk decides nothing
  with it: evaluate() passes only postseason_graded (and intl_graded) to desk_call. It is copied into desk_meta.counts
  with counts_source.
- The count is computed in ONE place: the Cockpit, valueShadowGraded() = the ledger's calls with call_type
  "value_shadow" and a result (push and void included), over its own bd_ledger_v1 in the browser's localStorage.
- The ledger summary (kind bd_ledger_summary_v1) has ONE producer: the Cockpit's "Export ledger summary" button. It is a
  browser download named ledger_summary.json; the page asks the operator to save it by hand as
  exports/ledger_summary.json. No command, chain step, mirror or host job writes or moves it.
- Every --desk export reads SP_LEDGER_SUMMARY, else exports/ledger_summary.json relative to the working directory
  (desk_policy.maybe_annotate). A closing step runs `python cli.py export-... --desk` with the checkout root as its
  working directory and no SP_LEDGER_SUMMARY in any example env. "default 0 (no ledger summary)" is the text
  read_ledger_summary returns only when no file is at that path: the laptop's checkout has no
  exports/ledger_summary.json. exports/ is gitignored, the step is manual and documented only on the button and in
  docs/CLI.md, so the file was never saved there. (Every desk file in the exports mirror, laptop and host, reads it.)
- So the n for #86 cannot come from desk_meta. It comes from the ledger itself, which this receipt reads from the
  Cockpit's "Export ledger (JSON)" file (bd_ledger_v1_<date>.json).

HOW THE LEDGER HOLDS A VALUE SHADOW (tools/cockpit.html, and the live Cockpit artifact published 2026-10-03, alike):
a call with call_type "value_shadow", engine model_edge, units 0, shadow_units 0.25 (notional), pick = the value side.
claim_model_p / claim_market_p are frozen at the first capture (the claim); value_edge_pp is overwritten by every
re-log. Grading sets status "graded", result win / loss / push / void (push: a two-way tie), shadow_returned (units at
fair odds: 0.25 / p on a win, 0.25 back on a push or void, 0 on a loss), and close_ref.q_close (the pick's closing
fair) when the results file carried a close. The kickoff audit (#178) marks tz_audit: excluded = out of the P&L,
flagged = settled at tz_audit.price_used. Neither copy of the Cockpit has a "staked" field or a note path for a shadow.

WHAT THE RECEIPT READS (the keys are printed with the output):
- a value shadow: call_type "value_shadow";
- staked: a truthy "staked" field on the call, or the text "value shadow, staked" in any string of it (any call_type).
  A call of another type marked so is listed in its own block and kept out of the totals;
- date: the kickoff (UTC); side: pick; edge at the call: (claim_model_p - claim_market_p) x 100, else value_edge_pp
  (no claim recorded: the last log's edge, labelled); the close: close_ref.q_close; the result: result, status open =
  ungraded; units: shadow_units notional, net = returned - staked over the settled rows (the Cockpit's settledBets).
- graded n is the Cockpit's own n/30 counter (every value shadow with a result). Fills are never read: they carry
  dollars.

Refuses a file that is not a bd_ledger_v1 export (no calls array, or a call that is not an object). Writes nothing.

    python3 scripts/value_shadow_receipt.py --ledger PATH/bd_ledger_v1_<date>.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REVIEW_N = 30                       # tools/cockpit.html VALUE.reviewN (#86: promotion after >= 30 graded)
VALUE_SHADOW = "value_shadow"
STAKED_TEXT = "value shadow, staked"
OUTCOME = {"win": "won", "loss": "lost", "push": "push", "void": "void"}
KEYS = ('value shadow = call_type "value_shadow" · staked = a truthy "staked" field, or the text '
        f'"{STAKED_TEXT}" in any string of the call · date = kickoff (UTC) · side = pick · edge at the call = '
        "(claim_model_p - claim_market_p) x 100, else value_edge_pp (last log) · close = close_ref.q_close · "
        "result = result (status open: ungraded) · units = shadow_units; net = returned - staked over the settled "
        "rows (tz_audit excluded: out; flagged: at tz_audit.price_used)")


def refusal(L) -> str | None:
    """Why `L` is not a bd_ledger_v1 export the receipt can stand behind (None: it is)."""
    if not isinstance(L, dict):
        return "not a bd_ledger_v1 export (not a JSON object)"
    if not isinstance(L.get("calls"), list):
        return "not a bd_ledger_v1 export (no calls array)"
    bad = [i for i, c in enumerate(L["calls"]) if not isinstance(c, dict)]
    if bad:
        return f"calls[{bad[0]}] is not an object ({len(bad)} such)"
    return None


def _strings(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from _strings(x)
    elif isinstance(v, list):
        for x in v:
            yield from _strings(x)


def staked_by(c: dict) -> str | None:
    """How the call is marked staked: "field" (a truthy staked), "text" (the label in a string), else None."""
    if c.get("staked"):
        return "field"
    if any(STAKED_TEXT in s.lower() for s in _strings(c)):
        return "text"
    return None


def settle(units: float, result: str | None, p) -> float:
    """tools/cockpit.html settleReturn: fair odds, decimal = 1 / p."""
    if result == "win":
        return units / p if isinstance(p, (int, float)) and p > 0 else 0.0
    if result in ("push", "void"):
        return units
    return 0.0


def edge_at_call(c: dict) -> tuple[float | None, str]:
    m, k = c.get("claim_model_p"), c.get("claim_market_p")
    if isinstance(m, (int, float)) and isinstance(k, (int, float)):
        return (m - k) * 100, "claim"
    e = c.get("value_edge_pp")
    return (float(e), "last log") if isinstance(e, (int, float)) else (None, "none")


def row(c: dict) -> dict:
    graded = c.get("status") == "graded" and c.get("result") in OUTCOME
    au = c.get("tz_audit") if isinstance(c.get("tz_audit"), dict) else None
    excluded = bool(au and au.get("excluded"))
    u = c.get("shadow_units")
    u = float(u) if isinstance(u, (int, float)) else 0.0
    net = None
    if graded and not excluded:
        if au:
            returned = round(settle(u, c["result"], au.get("price_used")), 4)
        else:
            sr = c.get("shadow_returned")
            returned = float(sr) if isinstance(sr, (int, float)) else 0.0
        net = returned - u
    q = (c.get("close_ref") or {}).get("q_close") if isinstance(c.get("close_ref"), dict) else None
    edge, basis = edge_at_call(c)
    return {"kickoff": c.get("kickoff"), "log_date": c.get("log_date"), "sport": c.get("sport"),
            "home": c.get("home"), "away": c.get("away"), "game": c.get("game"), "pick": c.get("pick"),
            "edge_pp": edge, "edge_basis": basis, "close": q if isinstance(q, (int, float)) else None,
            "outcome": OUTCOME[c["result"]] if graded else "ungraded", "units": u, "net": net,
            "audit": "excluded" if excluded else ("flagged" if au else None), "staked": staked_by(c),
            "call_type": c.get("call_type")}


def totals(rs: list[dict]) -> dict:
    graded = [r for r in rs if r["outcome"] != "ungraded"]
    settled = [r for r in graded if r["net"] is not None]
    rec = {k: sum(1 for r in graded if r["outcome"] == k) for k in ("won", "lost", "push", "void")}
    return {"n": len(rs), "graded": len(graded), "record": rec, "ungraded": len(rs) - len(graded),
            "settled": len(settled), "audit_excluded": sum(1 for r in graded if r["audit"] == "excluded"),
            "notional": round(sum(r["units"] for r in settled), 4),
            "units_net": round(sum(r["net"] for r in settled), 4)}


def read(L: dict) -> dict:
    vs = sorted((row(c) for c in L["calls"] if c.get("call_type") == VALUE_SHADOW),
                key=lambda r: (r["kickoff"] is None, r["kickoff"] or "", r["game"] or ""))
    other = [row(c) for c in L["calls"] if c.get("call_type") != VALUE_SHADOW and staked_by(c)]
    return {"rows": vs, "other_staked": other, "all": totals(vs),
            "with_close": totals([r for r in vs if r["close"] is not None]),
            "staked": {"field": sum(1 for r in vs if r["staked"] == "field"),
                       "text": sum(1 for r in vs if r["staked"] == "text")}}


def _side(r: dict) -> str:
    team = {"HOME": r["home"], "AWAY": r["away"], "DRAW": "draw"}.get(r["pick"] or "")
    return f"{r['pick'] or '-'}" + (f" ({team})" if team and team != "draw" else "")


def _line(r: dict) -> str:
    when = (r["kickoff"] or "").replace("T", " ")[:16] or f"no kickoff (logged {r['log_date'] or '-'})"
    game = f"{r['away']} @ {r['home']}" if r["home"] and r["away"] else (r["game"] or "-")
    edge = "-" if r["edge_pp"] is None else f"{r['edge_pp']:+.1f}pp ({r['edge_basis']})"
    close = "no close" if r["close"] is None else f"close {r['close']:.3f}"
    units = f"{r['units']:g}u" + ("" if r["net"] is None else f", net {r['net']:+.4f}u")
    return (f"  {when} · {r['sport'] or '-'} · {game} · {_side(r)} · edge {edge} · {close} · {r['outcome']} · {units}"
            + (f" · kickoff audit: {r['audit']}" if r["audit"] else "")
            + (f" · STAKED ({'a staked field' if r['staked'] == 'field' else 'the label'})" if r["staked"] else ""))


def _tot(label: str, t: dict) -> str:
    rec = t["record"]
    return (f"  {label}: n {t['n']} · graded {t['graded']} · record won {rec['won']} · lost {rec['lost']} · "
            f"push {rec['push']} · void {rec['void']} · ungraded {t['ungraded']} · units net {t['units_net']:+.4f}u "
            f"over {t['settled']} settled (notional {t['notional']:g}u)"
            + (f" · out of the P&L by the kickoff audit {t['audit_excluded']}" if t["audit_excluded"] else ""))


def report(L: dict, name: str, echo=print) -> dict:
    out = read(L)
    a, wc = out["all"], out["with_close"]
    echo("VALUE-SHADOW RECEIPT (ARCHITECT 2026-10-15, addendum 79 item 2; #86): read-only, units only, no dollar figure")
    echo(f"ledger: {name} · calls {len(L['calls'])} · meta.policy_version "
         f"{(L.get('meta') or {}).get('policy_version', '-')} (the Cockpit rewrites it on every load)")
    echo(f"keys: {KEYS}")
    if not out["rows"] and not out["other_staked"]:
        echo("VALUE SHADOWS: none in this ledger (0 calls with call_type value_shadow, 0 marked "
             f"\"{STAKED_TEXT}\") → n=0 of {REVIEW_N}")
    else:
        echo("ROWS (kickoff UTC · sport · game · side · edge at the call · the close · result · units)")
        for r in out["rows"]:
            echo(_line(r))
        if out["other_staked"]:
            echo(f"MARKED \"{STAKED_TEXT}\" BUT NOT call_type value_shadow (listed, kept out of the totals):")
            for r in out["other_staked"]:
                echo(_line(r) + f" · call_type {r['call_type']}")
        echo("TOTALS")
        echo(_tot("all value shadows", a))
        echo(_tot("the rows with a close only", wc))
        echo(f"  staked: {out['staked']['field'] + out['staked']['text']} (a staked field {out['staked']['field']} · "
             f"the label {out['staked']['text']}) · marked but not a value_shadow call: {len(out['other_staked'])}")
        echo(f"n/30 (the Cockpit's counter: every value shadow with a result, push and void included): "
             f"{a['graded']} of {REVIEW_N}")
    echo("VALUE-SHADOW-RECEIPT " + json.dumps({"ledger": name, "calls": len(L["calls"]), "all": a, "with_close": wc,
                                                "staked": out["staked"], "other_staked": len(out["other_staked"]),
                                                "n_of_30": f"{a['graded']} of {REVIEW_N}"}, sort_keys=True))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="addendum 79 item 2: every value shadow in a Cockpit ledger export")
    ap.add_argument("--ledger", required=True, help="the Cockpit's Export ledger (JSON) file, bd_ledger_v1_<date>.json")
    a = ap.parse_args(argv)
    p = Path(a.ledger)
    try:
        L = json.loads(p.read_text())
    except (OSError, ValueError) as e:
        print(f"REFUSED: {p}: {type(e).__name__}: {e}")
        return 2
    why = refusal(L)
    if why:
        print(f"REFUSED: {p.name}: {why}")
        return 2
    report(L, p.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
