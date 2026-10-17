"""
Cockpit VOID: RE-DATED headless verification (ARCHITECT 2026-10-17, addendum 106 item 4 / addendum 107 item A2; #574).

"a closing row whose recorded start differs from the match's current utc_date by more than DESK_CLOCK_DRIFT is
labelled "void: re-dated <old start> → <new start>" and excluded from every tally; the fresh closing run on the new date
is the graded row. Test with the 50548 case verbatim."

Over a crafted ledger and a results file, through the Cockpit's own intake (#resultsFile):
- 50548 TB at CLE called at its old start (2026-10-17T00:00:00) and again at its new one (2026-10-18T21:00:00), the
  results row dated 2026-10-18T21:00:00 (the match's current utc_date): the old call is void with the exact label and no
  result, the fresh call is graded; so is a value shadow and a parlay leg on the old start (the leg drops from its
  ticket, which settles on its other leg);
- 50547 (no move) is graded; exactly 1h apart is graded, 61 minutes is void; a result dated with no clock is not
  compared;
- every tally counts the graded calls only: settledBets, the n/30 counters, the ledger summary, the CLV references;
  the ledger lists the void calls with the label, the P&L block and the intake note count them;
- the labels are word for word src/walters/redated.py redated_label's; a re-log reopens a void call (no label);
- a series' neighbouring day (#574 question 1): the next day's result voids an open call, its own day's grades it;
- a ticket settles once: a leg voided at intake 1 (the ticket settles on its other leg) and matched to its own game at
  intake 2 stays void, the ticket's return and result do not change, and a re-log never reopens that leg;
- the early-execution count (the n/50 revisit) leaves a void call out.

    python3 scripts/cockpit_redated_verify.py

Writes nothing to the repo; no DB. Needs Playwright + Chromium.
"""
import functools
import http.server
import json
import os
import sys
import tempfile
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from src.walters.redated import redated_label  # noqa: E402

CHECKS = []
LABEL_50548 = "void: re-dated 2026-10-17 00:00Z → 2026-10-18 21:00Z"
TB_CLE = ("Cleveland Guardians", "Tampa Bay Rays")


def check(label, ok, detail=""):
    CHECKS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


def call(cid, home, away, kickoff, log_date, pick="HOME", market_p=0.56, call_type="straight", **kw):
    units = 0 if call_type == "value_shadow" else 1
    return {"id": cid, "log_date": log_date, "sport": "MLB", "game": f"{away} @ {home}", "home": home, "away": away,
            "kickoff": kickoff, "three_way": False, "status": "open", "quarantine": False, "pick": pick,
            "tier": "lean", "engine": "model_edge", "call_type": call_type, "units": units, "model_p": 0.61,
            "market_p": market_p, "venue_hint": "books", "stage": "postseason", "rules": ["lean 1u"], **kw}


LEDGER = {"meta": {"policy_version": "v1.1"}, "calls": [
    call("old", *TB_CLE, "2026-10-17T00:00:00", "2026-10-16", exec_mode="operator_early"),   # 50548 at its old start
    call("fresh", *TB_CLE, "2026-10-18T21:00:00", "2026-10-18", exec_mode="operator_early"), # 50548 at its new start
    call("old_shadow", *TB_CLE, "2026-10-17T00:00:00", "2026-10-16", pick="AWAY", market_p=0.44,
         call_type="value_shadow", shadow_units=0.25),
    call("mil_lad", "Los Angeles Dodgers", "Milwaukee Brewers", "2026-10-16T00:00:00", "2026-10-15",
         pick="AWAY", market_p=0.45),                                                   # 50547: no move
    call("one_hour", "Boston Red Sox", "New York Yankees", "2026-10-17T23:00:00", "2026-10-17"),
    call("sixty_one", "Texas Rangers", "Houston Astros", "2026-10-17T23:00:00", "2026-10-17"),
    call("date_only", "Toronto Blue Jays", "Seattle Mariners", "2026-10-17T20:00:00", "2026-10-17"),
    call("leg_old", *TB_CLE, "2026-10-17T00:00:00", "2026-10-16", call_type="parlay_leg", parlay_id="P-2026-10-16-X",
         units=0.25, tier="parlay"),
    call("leg_mil", "Los Angeles Dodgers", "Milwaukee Brewers", "2026-10-16T00:00:00", "2026-10-15", pick="AWAY",
         market_p=0.45, call_type="parlay_leg", parlay_id="P-2026-10-16-X", units=0.25, tier="parlay"),
]}

def res(mid, home, away, date, hs, as_, **kw):
    return {"match_id": mid, "date": date, "home_team": home, "away_team": away,
            "actual": {"home_score": hs, "away_score": as_, "result": "H" if hs > as_ else "A"},
            "graded": {"close_fair": {"HOME": 0.55, "AWAY": 0.45}}, **kw}


# the 50548 row as export-results writes it when no closing exists at the new start: the label rides "redated",
# never "status" or "void", so the Cockpit still grades the fresh call from the row's own result
RESULTS = {"sport": "mlb", "results": [
    res(50548, *TB_CLE, "2026-10-18T21:00:00", 5, 2, redated=LABEL_50548),
    res(50547, "Los Angeles Dodgers", "Milwaukee Brewers", "2026-10-16T00:00:00", 1, 4),
    res(1, "Boston Red Sox", "New York Yankees", "2026-10-18T00:00:00", 3, 2),
    res(2, "Texas Rangers", "Houston Astros", "2026-10-18T00:01:00", 3, 2),
    res(3, "Toronto Blue Jays", "Seattle Mariners", "2026-10-18", 3, 2),
]}


def intake(page, path):
    """One results file through the Cockpit's own intake: (the intake note, the stored calls by id)."""
    page.evaluate("document.getElementById('ledgerNote').textContent='';"
                  "document.getElementById('resultsFile').value=''")
    page.set_input_files("#resultsFile", [path])
    page.wait_for_function("document.getElementById('ledgerNote').textContent.includes('finished results read')")
    calls = page.evaluate("JSON.parse(localStorage.getItem('bd_ledger_v1'))")["calls"]
    return page.inner_text("#ledgerNote"), {c["id"]: c for c in calls}


def main():
    tmp = tempfile.mkdtemp(prefix="cockpit-redated-")
    path = os.path.join(tmp, "mlb_MLB_results_2026-10-18.json")
    with open(path, "w") as f:
        json.dump(RESULTS, f)

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0),
                                          functools.partial(Quiet, directory=os.path.join(ROOT, "tools")))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        browser = pw.chromium.launch(**({"executable_path": exe} if os.path.isfile(exe) else {}))
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{srv.server_address[1]}/cockpit.html")
        page.evaluate("l => localStorage.setItem('bd_ledger_v1', JSON.stringify(l))", LEDGER)
        page.click("#tabLedger")
        page.set_input_files("#resultsFile", [path])
        page.wait_for_function("document.getElementById('ledgerNote').textContent.includes('finished results read')")
        note = page.inner_text("#ledgerNote")
        print("   ", note)
        L = page.evaluate("JSON.parse(localStorage.getItem('bd_ledger_v1'))")
        by = {c["id"]: c for c in L["calls"]}

        print("50548 (addendum 107 item A2: 10-17 00:00Z → 10-18 21:00Z)")
        old = by["old"]
        check("the call at the old start is void with the ruling's label", old.get("void_redated") == LABEL_50548,
              repr(old.get("void_redated")))
        check("… and has no result, no return and status void",
              "result" not in old and "units_returned" not in old and old["status"] == "void", json.dumps(old)[:200])
        fr = by["fresh"]
        check("the fresh call at the new start is graded (a win at 1/0.56)",
              fr["status"] == "graded" and fr.get("result") == "win" and abs(fr["units_returned"] - 1 / 0.56) < 1e-3
              and "void_redated" not in fr, json.dumps(fr)[:200])
        check("the results row's redated key is never read as a void match (the fresh call is not refunded)",
              fr.get("result") != "void")
        sh = by["old_shadow"]
        check("a value shadow at the old start is void too", sh.get("void_redated") == LABEL_50548
              and "result" not in sh and sh["status"] == "void")

        print("THE RULE'S EDGES")
        check("50547 (no move) is graded", by["mil_lad"]["status"] == "graded" and by["mil_lad"]["result"] == "win")
        check("exactly 1h apart is not void", by["one_hour"]["status"] == "graded"
              and "void_redated" not in by["one_hour"])
        lab61 = "void: re-dated 2026-10-17 23:00Z → 2026-10-18 00:01Z"
        check("61 minutes apart is void", by["sixty_one"].get("void_redated") == lab61
              and "result" not in by["sixty_one"], repr(by["sixty_one"].get("void_redated")))
        check("a result dated with no clock is not compared (graded as before)",
              by["date_only"]["status"] == "graded" and "void_redated" not in by["date_only"])

        print("PARLAY")
        lo, lm = by["leg_old"], by["leg_mil"]
        check("a parlay leg at the old start is void, never graded", lo.get("void_redated") == LABEL_50548
              and "result" not in lo and lo["status"] == "void")
        check("its ticket settles on the other leg alone (0.25 / 0.45)",
              lm["status"] == "graded" and lm["ticket_result"] == "win" and abs(lm["units_returned"] - 0.25 / 0.45) < 1e-3,
              json.dumps(lm)[:200])

        print("EVERY TALLY")
        bets = page.evaluate("settledBets(loadLedger()).map(b=>[b.call_type,b.staked,b.returned,b.result])")
        check("settledBets: the four graded straights and the one ticket, nothing void",
              sorted(b[0] for b in bets) == ["parlay", "straight", "straight", "straight", "straight"], str(bets))
        a = page.evaluate("(()=>{const b=settledBets(loadLedger()).filter(x=>!x.shadow);return agg(b);})()")
        want_ret = 1 / 0.56 + 1 / 0.45 + 1 / 0.56 + 1 / 0.56 + 0.25 / 0.45
        check("agg: n 5, staked 4.25u, returned as the graded calls alone",
              a["n"] == 5 and abs(a["staked"] - 4.25) < 1e-9 and abs(a["returned"] - want_ret) < 1e-3, json.dumps(a))
        cnt = page.evaluate("({ps:postseasonGraded(),vs:valueShadowGraded(),sum:ledgerSummary()})")
        check("n/30 counters: postseason 4 (the void old call out), value shadow 0",
              cnt["ps"] == 4 and cnt["vs"] == 0, json.dumps(cnt["sum"]["counts"]))
        check("ledger summary per rule counts the graded calls only (4 straights + 1 leg)",
              cnt["sum"]["graded_per_rule"].get("lean 1u") == 5, json.dumps(cnt["sum"]["graded_per_rule"]))
        clv = page.evaluate("clvLines(loadLedger()).join('\\n')")
        check("CLV references: 4 graded calls with a close (no void call carries a close)",
              "  4 graded call(s) with a close" in clv and not any("close_ref" in by[k] for k in
                                                                 ("old", "old_shadow", "sixty_one", "leg_old")))
        lst = page.inner_text("#openList")
        check("the ledger lists the void calls with the label", "4 call(s) void" in lst and LABEL_50548 in lst
              and lab61 in lst, lst[:300])
        pnl = page.inner_text("#pnlBlock")
        check("the P&L block counts them on a line of their own", "Void: re-dated 4 (out of every line above" in pnl)
        check("the early executions count the fresh call only (old and fresh both executed early)",
              "Early executions: 1 position(s)" in pnl and "(1/50)" in pnl,
              next((x for x in pnl.splitlines() if x.startswith("Early executions")), ""))
        check("the intake note counts them", "void: re-dated 4" in note)

        print("IDEMPOTENT + PARITY")
        page.evaluate("document.getElementById('ledgerNote').textContent='';"
                      "document.getElementById('resultsFile').value=''")
        page.set_input_files("#resultsFile", [path])
        page.wait_for_function("document.getElementById('ledgerNote').textContent.includes('finished results read')")
        L2 = page.evaluate("JSON.parse(localStorage.getItem('bd_ledger_v1'))")
        check("a second intake changes nothing", L2["calls"] == L["calls"])
        pairs = [("2026-10-17T00:00:00", "2026-10-18T21:00:00"), ("2026-10-17T23:00:00", "2026-10-18T00:00:00"),
                 ("2026-10-17T23:00:00", "2026-10-18T00:01:00"), ("2026-10-17T23:00:00", "2026-10-17T21:59:00"),
                 ("2026-10-17T00:00:00", "2026-10-18"), ("2026-10-17", "2026-10-18T21:00:00"),
                 ("2026-10-17T00:00:00Z", "2026-10-18T21:00:00+00:00"), ("", "2026-10-18T21:00:00")]
        js = page.evaluate("ps => ps.map(([a,b])=>redatedLabel(a,b))", pairs)
        py = [redated_label(x, y) for x, y in pairs]
        check("the Cockpit's labels are src/walters/redated.py's, word for word", js == py, f"{js} vs {py}")

        relog = page.evaluate("""([c, lab]) => {
            localStorage.setItem('bd_ledger_v1', JSON.stringify({meta:{policy_version:'v1.1'},
              calls:[{...c, kickoff:'2026-10-17T00:00:00', status:'void', void_redated:lab}]}));
            const L=loadLedger(); upsertCalls(L,[{...c}],{relog:true}); return L.calls; }""",
                              [call("relog", *TB_CLE, "2026-10-18T21:00:00", "2026-10-16"), LABEL_50548])
        check("a re-log reopens a void call at the fresh kickoff and drops the label",
              len(relog) == 1 and relog[0]["status"] == "open" and "void_redated" not in relog[0]
              and relog[0]["kickoff"] == "2026-10-18T21:00:00", json.dumps(relog)[:200])

        print("A SERIES (the ±1-day join, #574 question 1)")
        # one day's results file is the only match for the neighbouring day's open call (same teams): before #577 it
        # was graded on the neighbour's game; now void, and graded at the intake that holds its own result
        series = {"meta": {"policy_version": "v1.1"}, "calls": [
            call("series_d1", "New York Mets", "Philadelphia Phillies", "2026-10-16T23:05:00", "2026-10-16")]}
        page.evaluate("l => localStorage.setItem('bd_ledger_v1', JSON.stringify(l))", series)
        for day, date, hs in (("d2", "2026-10-17T23:05:00", 1), ("d1", "2026-10-16T23:05:00", 6)):
            f = os.path.join(tmp, f"series_{day}.json")
            with open(f, "w") as fh:
                json.dump({"sport": "mlb", "results": [res(9, "New York Mets", "Philadelphia Phillies", date, hs, 2)]}, fh)
            c = intake(page, f)[1]["series_d1"]
            if day == "d2":
                check("the next day's result voids the open call, never grades it",
                      c.get("void_redated") == "void: re-dated 2026-10-16 23:05Z → 2026-10-17 23:05Z"
                      and "result" not in c, json.dumps(c)[:200])
            else:
                check("its own day's result grades it and clears the label",
                      c["status"] == "graded" and c["result"] == "win" and "void_redated" not in c, json.dumps(c)[:200])

        print("A TICKET SETTLES ONCE (graded history is never rewritten)")
        # leg A is the series' game 2; intake 1 (the 10-16 slate) holds game 1, the only match for A: A is void and the
        # ticket settles on leg B alone. Intake 2 (the 10-17 slate) holds game 2, a loss: the settled ticket stands
        leg = functools.partial(call, call_type="parlay_leg", parlay_id="P-2026-10-16-Y", units=0.25, tier="parlay")
        page.evaluate("l => localStorage.setItem('bd_ledger_v1', JSON.stringify(l))", {
            "meta": {"policy_version": "v1.1"}, "calls": [
                leg("leg_a", "New York Mets", "Philadelphia Phillies", "2026-10-17T23:05:00", "2026-10-16"),
                leg("leg_b", "Milwaukee Brewers", "Los Angeles Dodgers", "2026-10-16T20:00:00", "2026-10-16")]})
        slates = []
        for day, rows in (("1016", [res(11, "New York Mets", "Philadelphia Phillies", "2026-10-16T23:05:00", 6, 2),
                                    res(12, "Milwaukee Brewers", "Los Angeles Dodgers", "2026-10-16T20:00:00", 4, 1)]),
                          ("1017", [res(13, "New York Mets", "Philadelphia Phillies", "2026-10-17T23:05:00", 1, 2)])):
            slates.append(os.path.join(tmp, f"ticket_{day}.json"))
            with open(slates[-1], "w") as fh:
                json.dump({"sport": "mlb", "results": rows}, fh)
        lab_a = "void: re-dated 2026-10-17 23:05Z → 2026-10-16 23:05Z"
        n1, t1 = intake(page, slates[0])
        check("intake 1: leg A void, the ticket settles on leg B alone (a win at 0.25 / 0.56)",
              t1["leg_a"].get("void_redated") == lab_a and t1["leg_b"]["status"] == "graded"
              and t1["leg_b"]["ticket_result"] == "win" and abs(t1["leg_b"]["units_returned"] - 0.25 / 0.56) < 1e-3
              and "1 calls/tickets graded" in n1, json.dumps(t1["leg_b"])[:200])
        relog = page.evaluate("""([sameDay, laterDay]) => { const L=loadLedger();
            const r=[upsertCalls(L,[sameDay],{relog:true}), upsertCalls(L,[laterDay],{relog:true})];
            return [r, L.calls.find(c=>c.id==='leg_a')]; }""",
                              [leg("x", "New York Mets", "Philadelphia Phillies", "2026-10-18T23:05:00", "2026-10-16"),
                               leg("y", "New York Mets", "Philadelphia Phillies", "2026-10-17T23:05:00", "2026-10-17",
                                   parlay_id="P-2026-10-17-Y")])
        check("a re-log (same day at a new kickoff, or a later day) never reopens the settled ticket's void leg",
              [r["kept"] for r in relog[0]] == [1, 1] and relog[1] == t1["leg_a"], json.dumps(relog)[:300])
        n2, t2 = intake(page, slates[1])
        check("intake 2: leg A's own game (a loss) leaves it void with its label and no result",
              t2["leg_a"].get("void_redated") == lab_a and t2["leg_a"]["status"] == "void" and "result" not in t2["leg_a"],
              json.dumps(t2["leg_a"])[:200])
        check("... the ticket's return and result are unchanged and nothing is graded",
              t2["leg_b"] == t1["leg_b"] and "0 calls/tickets graded" in n2, n2[:120])
        check("no page errors", not errors, "; ".join(errors))
        browser.close()
    srv.shutdown()
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed" + (" — ALL GREEN" if all(CHECKS) else " — FAILURES ABOVE"))
    return 0 if all(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
