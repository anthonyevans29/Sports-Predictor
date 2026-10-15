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

WHERE value_shadow_graded COMES FROM TODAY (read from the code, main c51324d; finding #544):
- desk_policy.COUNT_KEYS names it beside postseason_graded and kalshi_only_graded. The Python Desk decides nothing
  with it: evaluate() passes only postseason_graded (and intl_graded) to desk_call. It is copied into desk_meta.counts
  with counts_source.
- The count is computed in ONE place: the Cockpit, valueShadowGraded() = the ledger's calls with call_type
  "value_shadow" and a result (push and void included), over its own bd_ledger_v1 in the browser's localStorage.
- The ledger summary (kind bd_ledger_summary_v1) has ONE producer: the Cockpit's "Export ledger summary" button. It is a
  browser download named ledger_summary.json; the page asks the operator to save it by hand as
  exports/ledger_summary.json. Nothing PRODUCES it in exports/ (sp_migrate's pack and the exports mirror would copy one
  saved there; the mirror, as it stands, holds none).
- Every --desk export reads SP_LEDGER_SUMMARY, else exports/ledger_summary.json relative to the working directory
  (desk_policy.maybe_annotate). A closing step runs `python cli.py export-... --desk` with the checkout root as its
  working directory and no SP_LEDGER_SUMMARY in any example env. "default 0 (no ledger summary)" is the text
  read_ledger_summary returns only when no file is at that path. exports/ is gitignored and the save is a manual step
  documented only on the button and in docs/CLI.md. Every desk file the exports mirror keeps (14 days: 109 files,
  laptop and host, the closing files among them) reads that text: at none of those export times was a file there.
- So the n for #86 cannot come from desk_meta. It comes from the ledger itself, which this receipt reads from the
  Cockpit's "Export ledger (JSON)" file (bd_ledger_v1_<date>.json).

HOW THE LEDGER HOLDS A VALUE SHADOW (tools/cockpit.html, and the live Cockpit artifact published 2026-10-03, alike):
a call with call_type "value_shadow", engine model_edge, units 0, shadow_units 0.25 (notional), pick = the value side.
claim_model_p / claim_market_p are frozen at the first capture (the claim); value_edge_pp is overwritten by every
re-log. Grading sets status "graded", result win / loss / push / void (push: a two-way tie; the game's score is not
stored on the call), shadow_returned (units at fair odds: 0.25 / p on a win, 0.25 back on a push or void, 0 on a loss),
and close_ref.q_close (the pick's closing fair) when the results file carried a close. The kickoff audit (#178) marks
tz_audit: excluded = out of the P&L, flagged = settled at tz_audit.price_used. The Cockpit shows TWO n/30 readings: the
policy card's (every value shadow with a result) and the P&L block's (its settled rows: the audit-excluded ones left
out); the receipt prints both. Neither copy of the Cockpit has a "staked" field or a note path for a shadow; a real
Kalshi fill on a shadow's side is booked off-book as "matches a quarantine SHADOW (off-policy play)", with no link.

WHAT THE RECEIPT READS (the keys are printed with the output):
- a value shadow: call_type "value_shadow";
- staked: a truthy "staked" field on the call, or the text "value shadow, staked" in any string of it (any call_type).
  A call of another type marked so is listed in its own block, with its own units, and kept out of the totals;
- a Kalshi fill on its side: the ledger's fills, classified by the Cockpit's own matcher (src/walters/ledger_fills.py,
  its port), whose category is "matches a quarantine SHADOW (off-policy play)" and whose game and side fit the value
  shadow. Counted only: a fill's prices and sizes are dollars and are never printed;
- date: the kickoff (UTC); side: pick; edge at the call: (claim_model_p - claim_market_p) x 100, else value_edge_pp
  (no claim recorded: the last log's edge, labelled); the close: close_ref.q_close; the result: the call's graded
  result (won / lost / push / void), status open = ungraded; units: shadow_units notional, net = returned - staked over
  the settled rows (the Cockpit's settledBets; a flagged row re-settled as the Cockpit does, toFixed(4)).

Refuses a file that is not a bd_ledger_v1 export (no calls array, or a call that is not an object). Writes nothing.

    python3 scripts/value_shadow_receipt.py --ledger PATH/bd_ledger_v1_<date>.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REVIEW_N = 30                       # tools/cockpit.html VALUE.reviewN (#86: promotion after >= 30 graded)
VALUE_SHADOW = "value_shadow"
SHADOWS = ("quarantine_shadow", "value_shadow")        # tools/cockpit.html isShadow
STAKED_TEXT = "value shadow, staked"
SHADOW_FILL = "matches a quarantine SHADOW (off-policy play)"   # the Cockpit's matchFill category for any shadow
OUTCOME = {"win": "won", "loss": "lost", "push": "push", "void": "void"}
KEYS = ('value shadow = call_type "value_shadow" · staked = a truthy "staked" field, or the text '
        f'"{STAKED_TEXT}" in any string of the call · fill on its side = a ledger fill the Cockpit books "{SHADOW_FILL}" '
        "whose game and side fit (counted, never priced) · date = kickoff (UTC) · side = pick · edge at the call = "
        "(claim_model_p - claim_market_p) x 100, else value_edge_pp (last log) · close = close_ref.q_close · result = "
        "the call's graded result (the game's score is not in the ledger; status open: ungraded) · units = "
        "shadow_units; net = returned - staked over the settled rows (tz_audit excluded: out; flagged: at "
        "tz_audit.price_used)")


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


def js_fixed4(x: float) -> float:
    """Number.prototype.toFixed(4) on the exact binary value, ties away from zero (the Cockpit's +x.toFixed(4))."""
    return float(Decimal(x).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


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


def _num(v) -> float:
    return float(v) if isinstance(v, (int, float)) else 0.0


def row(c: dict, fills: int = 0) -> dict:
    """One call as the receipt prints it. A shadow settles on shadow_units / shadow_returned, any other call on
    units / units_returned (the Cockpit's settledBets)."""
    graded = c.get("status") == "graded" and c.get("result") in OUTCOME
    au = c.get("tz_audit") if isinstance(c.get("tz_audit"), dict) else None
    excluded = bool(au and au.get("excluded"))
    sh = c.get("call_type") in SHADOWS
    u = _num(c.get("shadow_units") if sh else c.get("units"))
    net = None
    if graded and not excluded:
        returned = (js_fixed4(settle(u, c["result"], au.get("price_used"))) if au
                    else _num(c.get("shadow_returned") if sh else c.get("units_returned")))
        net = returned - u
    q = (c.get("close_ref") or {}).get("q_close") if isinstance(c.get("close_ref"), dict) else None
    edge, basis = edge_at_call(c)
    return {"id": c.get("id"), "kickoff": c.get("kickoff"), "log_date": c.get("log_date"), "sport": c.get("sport"),
            "home": c.get("home"), "away": c.get("away"), "game": c.get("game"), "pick": c.get("pick"),
            "edge_pp": edge, "edge_basis": basis, "close": q if isinstance(q, (int, float)) else None,
            "outcome": OUTCOME[c["result"]] if graded else "ungraded", "units": u, "net": net,
            "audit": "excluded" if excluded else ("flagged" if au else None), "staked": staked_by(c),
            "fills": fills, "call_type": c.get("call_type")}


def shadow_fills(L: dict) -> dict:
    """{value-shadow call id: the fills on its side}: the ledger's fills the Cockpit's own matcher (the Python port)
    books as matching a shadow, re-fitted to the value shadow whose game and side they fit (the nearest start). The
    fills' prices and sizes are never read past the matcher."""
    from src.walters import ledger_fills as lf
    shadows = [c for c in L["calls"] if c.get("call_type") == VALUE_SHADOW]
    out: Counter = Counter()
    if not shadows or not L.get("fills"):
        return {}
    for fx in lf.classify_fills(L):
        if fx.get("category") != SHADOW_FILL or fx.get("composite"):
            continue

        def near(c, fx=fx):
            d = (c.get("kickoff") or c.get("log_date") or "")[:10]
            return c.get("sport") in fx["sports"] and lf.day_diff(d, fx["date"]) <= 1

        def agrees(c, fx=fx):
            if fx.get("backed_role"):
                return fx["backed_role"] == c.get("pick")
            name = {"HOME": c.get("home"), "AWAY": c.get("away")}.get(c.get("pick"), "Draw")
            b = fx.get("backed")
            return bool(b and name) and (b == name if "Draw" in (b, name) else lf._tok_subset(b, name))
        fit = [c for c in lf._start_nearest(fx, [c for c in shadows if near(c) and lf.game_fits(fx, c)]) if agrees(c)]
        if fit:
            out[fit[0].get("id")] += 1
    return dict(out)


def totals(rs: list[dict]) -> dict:
    graded = [r for r in rs if r["outcome"] != "ungraded"]
    settled = [r for r in graded if r["net"] is not None]
    rec = {k: sum(1 for r in graded if r["outcome"] == k) for k in ("won", "lost", "push", "void")}
    rec_pl = {k: sum(1 for r in settled if r["outcome"] == k) for k in ("won", "lost", "push", "void")}
    return {"n": len(rs), "graded": len(graded), "record": rec, "ungraded": len(rs) - len(graded),
            "settled": len(settled), "record_settled": rec_pl,
            "audit_excluded": sum(1 for r in graded if r["audit"] == "excluded"),
            "notional": round(sum(r["units"] for r in settled), 4),
            "units_net": round(sum(r["net"] for r in settled), 4)}


def read(L: dict) -> dict:
    fills = shadow_fills(L)
    vs = sorted((row(c, fills.get(c.get("id"), 0)) for c in L["calls"] if c.get("call_type") == VALUE_SHADOW),
                key=lambda r: (r["kickoff"] is None, r["kickoff"] or "", r["game"] or ""))
    other = [row(c) for c in L["calls"] if c.get("call_type") != VALUE_SHADOW and staked_by(c)]
    return {"rows": vs, "other_staked": other, "all": totals(vs),
            "with_close": totals([r for r in vs if r["close"] is not None]),
            "staked": {"field": sum(1 for r in vs if r["staked"] == "field"),
                       "text": sum(1 for r in vs if r["staked"] == "text")},
            "with_fill": sum(1 for r in vs if r["fills"])}


def _side(r: dict) -> str:
    team = {"HOME": r["home"], "AWAY": r["away"]}.get(r["pick"] or "")
    return f"{r['pick'] or '-'}" + (f" ({team})" if team else "")


def _line(r: dict) -> str:
    when = (r["kickoff"] or "").replace("T", " ")[:16] or f"no kickoff (logged {r['log_date'] or '-'})"
    game = f"{r['away']} @ {r['home']}" if r["home"] and r["away"] else (r["game"] or "-")
    edge = "-" if r["edge_pp"] is None else f"{r['edge_pp']:+.1f}pp ({r['edge_basis']})"
    close = "no close" if r["close"] is None else f"close {r['close']:.3f}"
    units = f"{r['units']:g}u" + ("" if r["net"] is None else f", net {r['net']:+.4f}u")
    return (f"  {when} · {r['sport'] or '-'} · {game} · {_side(r)} · edge {edge} · {close} · {r['outcome']} · {units}"
            + (f" · kickoff audit: {r['audit']}" if r["audit"] else "")
            + (f" · STAKED ({'a staked field' if r['staked'] == 'field' else 'the label'})" if r["staked"] else "")
            + (f" · Kalshi fills on its side: {r['fills']} (off-book; never priced here)" if r["fills"] else ""))


def _rec(rec: dict) -> str:
    return f"won {rec['won']} · lost {rec['lost']} · push {rec['push']} · void {rec['void']}"


def _tot(label: str, t: dict) -> str:
    return (f"  {label}: n {t['n']} · graded {t['graded']} · record {_rec(t['record'])} · ungraded {t['ungraded']} · "
            f"units net {t['units_net']:+.4f}u over {t['settled']} settled (notional {t['notional']:g}u)"
            + (f" · out of the P&L by the kickoff audit {t['audit_excluded']} (the settled record: "
               f"{_rec(t['record_settled'])})" if t["audit_excluded"] else ""))


def report(L: dict, name: str, echo=print) -> dict:
    out = read(L)
    a, wc = out["all"], out["with_close"]
    echo("VALUE-SHADOW RECEIPT (ARCHITECT 2026-10-15, addendum 79 item 2; #86): read-only, units only, no dollar figure")
    echo(f"ledger: {name} · calls {len(L['calls'])} · fills {len(L.get('fills') or [])} (never priced here) · "
         f"meta.policy_version {(L.get('meta') or {}).get('policy_version', '-')} (the Cockpit rewrites it on every "
         "load)")
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
             f"the label {out['staked']['text']}) · marked but not a value_shadow call: {len(out['other_staked'])} · "
             f"with a Kalshi fill on their side: {out['with_fill']}")
        echo(f"n/30: the policy card's counter (every value shadow with a result) {a['graded']} of {REVIEW_N} · the "
             f"P&L block's (its settled rows, the kickoff audit applied) {min(a['settled'], REVIEW_N)} of {REVIEW_N}")
    echo("VALUE-SHADOW-RECEIPT " + json.dumps({"ledger": name, "calls": len(L["calls"]), "all": a, "with_close": wc,
                                                "staked": out["staked"], "other_staked": len(out["other_staked"]),
                                                "with_fill": out["with_fill"],
                                                "n_of_30": f"{a['graded']} of {REVIEW_N}",
                                                "n_of_30_pnl": f"{min(a['settled'], REVIEW_N)} of {REVIEW_N}"},
                                               sort_keys=True))
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
