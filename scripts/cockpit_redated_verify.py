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

ARCHITECT 2026-10-17 10:15 ET (addendum 109 item 2): "a Desk call is identified by its match id and its recorded
kickoff, not by a ±1-day join" (the calls above carry no match id: each is a legacy join, flagged and shown), and Q2's
"void: placeholder kickoff":
- the Cockpit import: the 50548 export rows (old start, then new) loaded through #predFile become calls carrying
  match_id 50548 and their kickoff; the results intake voids the old call and grades the fresh one by match id, and the
  ledger JSON export carries both fields;
- by match id: a game moved three days is void (the same call with no match id finds nothing in the ±1-day join);
  a series' two games are each graded on their own (the ±1-day join graded the wrong game); a call whose id is in no
  loaded row stays open, though a same-teams row sits on its day; a legacy call is paired by the join and shown
  "legacy join";
- a call recorded at the 04:00Z placeholder whose game kicked off at 23:30Z is "void: placeholder kickoff"; an unmoved
  placeholder is graded; the placeholder test and the labels are src/ingestion/placeholder.py's and
  src/walters/redated.py's, word for word;
- a match id is machine-local (the host and the laptop number matches apart): an NFL call whose id a loaded MLB row
  carries, and one whose id an NFL row of other teams carries, stay open, never graded or voided, counted and listed
  "id mismatch"; its own game's row under the id grades it though another file's row carries the same id, and the flag
  clears; a soccer call pairs by id with a PL fixtures row naming its teams (the files name the sport apart);
- a parlay leg the legacy join graded, its ticket waiting, keeps "legacy join" through a re-log that brings a match id.

ARCHITECT 2026-10-17 11:00 ET (addendum 114 item 1): "A parlay ticket with a leg void as re-dated: the leg is a PUSH —
removed from the ticket, the ticket re-priced on its remaining legs and settled when they are all graded; a one-leg
remainder settles as a single [...] Test: a three-leg ticket with one re-dated leg settles as a two-leg ticket when those
two grade." Addendum 115 item 4: "a ticket whose every leg moved settles as a push". Addendum 114 item 2: "Calls graded
before this change on a game later re-dated stay graded, labelled "legacy join" in the exports":
- the ruled ticket: legs A, B, C by match id, A is 50548 at its old start. A is void with the label, units 0.25 unchanged
  on the record; a same-ticket re-log of A at the moved kickoff, before the void or after it, never rewrites A, and a
  fresh call on A's game at the new start is its own call, never a leg; the ticket stays open while C is open (B graded,
  waiting), a later row for A within the hour of its kickoff never undoes the push, and the ticket settles as a two-leg
  ticket priced on B and C when they grade, once (a later intake changes nothing); a later-day re-log of the ticket
  (P-2026-10-17-T3, A at its new start) reprices B and C and keeps A: no one-leg ticket on the moved game; a legacy
  ticket the same (a sibling leg anchors it), while a different match id (the series' next game) is never read as moved;
- a legacy leg (no match id) on an open ticket, voided by the same teams' previous-day game (#578, the ±1-day join),
  is checked again at each intake: its own game on schedule grades it and the ticket settles on its three legs;
- a two-leg ticket with one re-dated leg settles as a single on the other leg (settleReturn's return); a ticket whose
  every leg moved (either label) settles as a push on its void legs and counts as a push (n, staked, returned, net 0,
  out of the hit rate), executed early it is one early position, and the P&L block's Void line names that exception;
  both settle once;
- calls graded before this change (no match id, no flag) are labelled "legacy join" in the ledger, the intake note, the
  P&L block and the ledger JSON export, their status, result and returns unchanged (a disagreeing row re-grades
  nothing); a call graded by its match id and an open call are not; an import of the rows as stored before the label is
  not "updated" by it.

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
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cockpit_desk_files as cdf  # noqa: E402
from src.ingestion.placeholder import is_placeholder_kickoff  # noqa: E402
from src.walters.redated import PLACEHOLDER_LABEL, as_utc, redated_label, void_counts  # noqa: E402

CHECKS = []
LABEL_50548 = "void: re-dated 2026-10-17 00:00Z → 2026-10-18 21:00Z"
MOVED_3D = "void: re-dated 2026-10-15 23:00Z → 2026-10-18 23:00Z"
TB_CLE = ("Cleveland Guardians", "Tampa Bay Rays")
NYM_PHI = ("New York Mets", "Philadelphia Phillies")


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


def export_row(mid, home, away, utc, p_home=0.61, fair_h=0.56):
    """An MLB --desk export row (a PLAY on books at 5pp) carrying its match id and kickoff, as the exports write it."""
    return {"match_id": mid, "home_team": home, "away_team": away, "utc_date": utc, "competition": "MLB",
            "stage": "postseason",
            "prediction": {"probabilities": {"home_win": p_home, "draw": None, "away_win": round(1 - p_home, 4)},
                           "tier": "lean"},
            "market": {"bookmaker_count": 9, "fair_prob": {"HOME": fair_h, "AWAY": round(1 - fair_h, 4)}}}


def fixture(mid, home, away, utc, hs, as_):
    """A finished fixtures row (the NCAA intake: market-only results arrive as finished fixtures)."""
    return {"match_id": mid, "home_team": home, "away_team": away, "utc_date": utc, "status": "finished",
            "home_score": hs, "away_score": as_}


def folded(page, sel):
    """A list's whole text, folded or not (the legacy-join list folds under its count: addendum 114 item 2)."""
    return page.text_content(sel) if page.query_selector(sel) else ""


def intake(page, path):
    """Results file(s) through the Cockpit's own intake: (the intake note, the stored calls by id)."""
    page.evaluate("document.getElementById('ledgerNote').textContent='';"
                  "document.getElementById('resultsFile').value=''")
    page.set_input_files("#resultsFile", path if isinstance(path, list) else [path])
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
        check("the P&L block counts them on a line of their own",
              "Void: re-dated 4 · placeholder kickoff 0 (out of every line above" in pnl)
        check("the early executions count the fresh call only (old and fresh both executed early)",
              "Early executions: 1 position(s)" in pnl and "(1/50)" in pnl,
              next((x for x in pnl.splitlines() if x.startswith("Early executions")), ""))
        check("the intake note counts them", "void: re-dated 4 · placeholder kickoff 0" in note)

        print("LEGACY JOIN (addendum 109 item 2: these calls carry no match id)")
        paired = [k for k in ("old", "fresh", "old_shadow", "mil_lad", "one_hour", "sixty_one", "date_only", "leg_old",
                              "leg_mil")]
        check("every call above was paired by the ±1-day team join and carries legacy_join, graded or void",
              all(by[k].get("legacy_join") is True and "match_id" not in by[k] for k in paired),
              json.dumps({k: by[k].get("legacy_join") for k in paired}))
        lj = folded(page, "#legacyJoin")
        check("the ledger lists the graded legacy calls with the flag \"legacy join\" (the void ones carry it there)",
              "5 call(s) legacy join" in lj and lj.count("legacy join") == 6
              and page.inner_text("#voidRedated").count("legacy join") == 4, lj[:300])
        check("the intake note and the P&L block count them",
              "legacy join 9 (no match id" in note and "Legacy join: 9 call(s) paired" in pnl,
              next((x for x in pnl.splitlines() if x.startswith("Legacy join")), ""))

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
        pairs += [("2026-10-17T04:00:00", "2026-10-17T23:30:00"), ("2026-10-17T04:00:00", "2026-10-17T04:00:00"),
                  ("2026-10-17T00:00:00-04:00", "2026-10-17T23:30:00"), ("2026-10-17T04:00:01", "2026-10-17T23:30:00"),
                  ("2026-10-17T04:00:00", "2026-10-17T05:00:00"), ("2026-10-17T23:30:00", "2026-10-18T04:00:00"),
                  ("2026-10-15T23:00:00", "2026-10-18T23:00:00")]
        js = page.evaluate("ps => ps.map(([a,b])=>redatedLabel(a,b))", pairs)
        py = [redated_label(x, y) for x, y in pairs]
        check("the Cockpit's labels are src/walters/redated.py's, word for word (the placeholder's included)",
              js == py and PLACEHOLDER_LABEL in py, f"{js} vs {py}")
        stamps = ["2026-10-17T04:00:00", "2026-10-17T04:00:00Z", "2026-10-17T00:00:00-04:00", "2026-10-17T04:00",
                  "2026-10-17T04:00:00.500", "2026-10-17T04:00:01", "2026-10-17T04:01:00", "2026-10-17T16:00:00",
                  "2026-10-17", "", None]
        jsp = page.evaluate("ss => ss.map(isPlaceholderKickoff)", stamps)
        pyp = [is_placeholder_kickoff(as_utc(x)) for x in stamps]
        check("the Cockpit's placeholder is src/ingestion/placeholder.py is_placeholder_kickoff's (04:00:00Z)",
              jsp == pyp and sum(pyp) == 5, f"{jsp} vs {pyp}")
        labs = [LABEL_50548, PLACEHOLDER_LABEL, PLACEHOLDER_LABEL, MOVED_3D]
        jvc = page.evaluate("ls => [PLACEHOLDER_LABEL, voidCounts({calls:ls.map(l=>({void_redated:l}))})]", labs)
        check("the label text and the count line are redated.py's", jvc == [PLACEHOLDER_LABEL, void_counts(labs)],
              json.dumps(jvc))

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

        print("A LEGACY LEG ON AN OPEN TICKET (#578: the ±1-day join's neighbouring-day game is not a move)")
        # three legacy legs (no match id) at 0.5; intake 1 holds only the same two teams' previous game (LCS-style back
        # to back), the join's only match for leg A: A reads void, a backward "move". Intake 2 holds A's own game on
        # schedule (a win) and B and C (wins): A is checked again while its ticket is open and graded; the ticket
        # settles on its three legs, as a straight in A's place would be graded
        tor_sea = ("Toronto Blue Jays", "Seattle Mariners")
        lb = functools.partial(call, call_type="parlay_leg", parlay_id="P-2026-10-19-B2B", units=0.25, tier="parlay",
                               market_p=0.5)
        page.evaluate("l => localStorage.setItem('bd_ledger_v1', JSON.stringify(l))", {
            "meta": {"policy_version": "v1.1"}, "calls": [
                lb("b2b_a", *tor_sea, "2026-10-20T00:08:00", "2026-10-19"),
                lb("b2b_b", *NYM_PHI, "2026-10-20T20:08:00", "2026-10-19"),
                lb("b2b_c", "Los Angeles Dodgers", "Milwaukee Brewers", "2026-10-20T23:08:00", "2026-10-19")]})
        b2b = []
        for day, rows in (("1", [res(70001, *tor_sea, "2026-10-19T00:08:00", 3, 2)]),
                          ("2", [res(70002, *tor_sea, "2026-10-20T00:08:00", 5, 1),
                                 res(70003, *NYM_PHI, "2026-10-20T20:08:00", 4, 2),
                                 res(70004, "Los Angeles Dodgers", "Milwaukee Brewers", "2026-10-20T23:08:00", 6, 3)])):
            b2b.append(os.path.join(tmp, f"b2b_{day}.json"))
            with open(b2b[-1], "w") as fh:
                json.dump({"sport": "mlb", "results": rows}, fh)
        nb1, tb1 = intake(page, b2b[0])
        check("intake 1: leg A void by the previous day's game (the join's only match), the ticket open",
              tb1["b2b_a"].get("void_redated") == "void: re-dated 2026-10-20 00:08Z → 2026-10-19 00:08Z"
              and not any("ticket_result" in x for x in tb1.values()) and "0 calls/tickets graded" in nb1,
              json.dumps(tb1["b2b_a"])[:200])
        check("... the void list says a legacy leg on an open ticket is checked again",
              "ticket awaiting its other 2 leg(s) (no match id: checked again at each intake while its ticket is open)"
              in folded(page, "#voidRedated"), folded(page, "#voidRedated")[:300])
        nb2, tb2 = intake(page, b2b[1])
        check("intake 2: A's own game on schedule grades it (label cleared) and the ticket settles on its three legs "
              "(0.25 / 0.5^3 = 2.0), no ticket_legs",
              all(tb2[k]["status"] == "graded" and tb2[k].get("result") == "win" and tb2[k].get("ticket_result") == "win"
                  and tb2[k].get("units_returned") == 2.0 and "ticket_legs" not in tb2[k] and "void_redated" not in tb2[k]
                  for k in ("b2b_a", "b2b_b", "b2b_c")) and "1 calls/tickets graded" in nb2,
              json.dumps(tb2["b2b_a"])[:300])
        bb = page.evaluate("settledBets(loadLedger()).filter(b=>b.call_type==='parlay').map(b=>[b.staked,b.returned,b.result])")
        check("... settledBets: the ticket once, staked 0.25u, returned 2.0u", bb == [[0.25, 2.0, "win"]], json.dumps(bb))
        print("THE COCKPIT IMPORT (addendum 109 item 2 (a): the 50548 case, export file → call → results intake)")
        # the 50548 export rows at the old start (Friday's file) and at the new one (Sunday's), through #predFile: the
        # auto-claimed calls carry match_id 50548 and their kickoff; the results intake pairs each by the id
        page.evaluate("localStorage.removeItem('bd_ledger_v1')")
        files = []
        for name, utc, at in (("mlb_fri.json", "2026-10-17T00:00:00", datetime(2026, 10, 16, 20, 0)),
                              ("mlb_sun.json", "2026-10-18T21:00:00", datetime(2026, 10, 18, 18, 0))):
            doc = {"sport": "mlb", "rehearsal": False, "predictions": [export_row(50548, *TB_CLE, utc)]}
            files += cdf.write(tmp, cdf.desk_files({name: doc}, at.replace(tzinfo=timezone.utc), parlays=False))
        for f in files:
            page.evaluate("document.getElementById('summary').textContent='';"
                          "document.getElementById('predFile').value=''")
            page.set_input_files("#predFile", [f])
            page.wait_for_function("document.getElementById('summary').textContent.includes('rows')")
        imp = sorted(page.evaluate("JSON.parse(localStorage.getItem('bd_ledger_v1')).calls"),
                     key=lambda c: c["kickoff"])
        check("each imported call carries match_id 50548 and its recorded kickoff",
              [(c["match_id"], c["kickoff"], c["call_type"]) for c in imp]
              == [(50548, "2026-10-17T00:00:00", "straight"), (50548, "2026-10-18T21:00:00", "straight")],
              json.dumps([(c.get("match_id"), c.get("kickoff")) for c in imp]))
        page.click("#tabLedger")
        note_i, got = intake(page, path)
        old_i, new_i = sorted(got.values(), key=lambda c: c["kickoff"])
        check("the results intake pairs by match id: the 10-17 00:00Z call is void with the ruling's label",
              old_i.get("void_redated") == LABEL_50548 and old_i["status"] == "void" and "result" not in old_i
              and "legacy_join" not in old_i, json.dumps(old_i)[:200])
        check("... and the fresh 10-18 21:00Z call is graded (a win), no legacy join",
              new_i["status"] == "graded" and new_i["result"] == "win" and "legacy_join" not in new_i
              and "void_redated" not in new_i, json.dumps(new_i)[:200])
        check("the intake note: void re-dated 1, legacy join 0",
              "void: re-dated 1 · placeholder kickoff 0" in note_i and "legacy join 0" in note_i, note_i[:200])
        with page.expect_download() as dl:
            page.click("#exportLedgerBtn")
        exported = json.load(open(dl.value.path()))
        check("the ledger JSON export carries match_id and kickoff on both calls",
              sorted((c["match_id"], c["kickoff"]) for c in exported["calls"])
              == [(50548, "2026-10-17T00:00:00"), (50548, "2026-10-18T21:00:00")],
              json.dumps([(c.get("match_id"), c.get("kickoff")) for c in exported["calls"]]))

        print("BY MATCH ID (addendum 109 item 2 (b): \"whatever the join window\")")
        oct15 = functools.partial(call, log_date="2026-10-15")
        page.evaluate("l => localStorage.setItem('bd_ledger_v1', JSON.stringify(l))", {
            "meta": {"policy_version": "v1.1"}, "calls": [
                oct15("id_3d", "Boston Red Sox", "New York Yankees", "2026-10-15T23:00:00", match_id=50560),
                call("legacy_3d", "Boston Red Sox", "New York Yankees", "2026-10-15T23:00:00", "2026-10-14",
                     pick="AWAY", market_p=0.44),                       # the same game, no match id
                call("id_s1", *NYM_PHI, "2026-10-16T23:05:00", "2026-10-16", match_id=9101),
                call("id_s2", *NYM_PHI, "2026-10-17T23:05:00", "2026-10-17", match_id=9102),
                oct15("id_none", "Los Angeles Dodgers", "Milwaukee Brewers", "2026-10-16T00:00:00", match_id=50547),
                call("legacy_mil", "Los Angeles Dodgers", "Milwaukee Brewers", "2026-10-16T00:00:00", "2026-10-14",
                     pick="AWAY", market_p=0.45),
                call("ph_moved", "Hawaii Rainbow Warriors", "Wyoming Cowboys", "2026-10-17T04:00:00", "2026-10-16",
                     sport="NCAA", match_id=8801, stage=None),
                call("ph_still", "Hawaii Rainbow Warriors", "Utah State Aggies", "2026-10-18T04:00:00", "2026-10-17",
                     sport="NCAA", match_id=8802, stage=None)]})
        f_mlb, f_ncaa = os.path.join(tmp, "by_id_mlb.json"), os.path.join(tmp, "by_id_ncaa.json")
        with open(f_mlb, "w") as fh:
            json.dump({"sport": "mlb", "results": [
                res(50560, "Boston Red Sox", "New York Yankees", "2026-10-18T23:00:00", 4, 2),   # moved three days
                res(9101, *NYM_PHI, "2026-10-16T23:05:00", 6, 2),                               # the series: game 1
                res(9102, *NYM_PHI, "2026-10-17T23:05:00", 1, 2),                               # game 2
                res(50599, "Los Angeles Dodgers", "Milwaukee Brewers", "2026-10-16T00:00:00", 1, 4)]}, fh)   # not 50547
        with open(f_ncaa, "w") as fh:
            json.dump({"competition_code": "NCAA", "fixtures": [
                fixture(8801, "Hawaii Rainbow Warriors", "Wyoming Cowboys", "2026-10-17T23:30:00", 31, 24),
                fixture(8802, "Hawaii Rainbow Warriors", "Utah State Aggies", "2026-10-18T04:00:00", 17, 20)]}, fh)
        note_b, b = intake(page, [f_mlb, f_ncaa])
        print("   ", note_b)
        check("a game moved three days is void by match id", b["id_3d"].get("void_redated") == MOVED_3D
              and b["id_3d"]["status"] == "void" and "result" not in b["id_3d"], json.dumps(b["id_3d"])[:200])
        check("... the same call with no match id finds nothing in the ±1-day join: open, unlabelled (the case the "
              "join missed)", b["legacy_3d"]["status"] == "open" and "void_redated" not in b["legacy_3d"]
              and "legacy_join" not in b["legacy_3d"], json.dumps(b["legacy_3d"])[:200])
        check("a series by match id: each call graded on its own game (game 1 a win, game 2 a loss)",
              (b["id_s1"]["status"], b["id_s1"].get("result"), b["id_s2"]["status"], b["id_s2"].get("result"))
              == ("graded", "win", "graded", "loss") and not any(b[k].get("void_redated") for k in ("id_s1", "id_s2")),
              json.dumps([b["id_s1"].get("result"), b["id_s2"].get("result")]))
        check("a call whose id is in no loaded row stays open, though a same-teams row sits on its day",
              b["id_none"]["status"] == "open" and "result" not in b["id_none"] and "void_redated" not in b["id_none"],
              json.dumps(b["id_none"])[:200])
        check("... while a legacy call (no match id) takes that row by the ±1-day join, flagged legacy join",
              b["legacy_mil"]["status"] == "graded" and b["legacy_mil"]["result"] == "win"
              and b["legacy_mil"].get("legacy_join") is True, json.dumps(b["legacy_mil"])[:200])
        check("no call with a match id is flagged legacy join",
              not any(b[k].get("legacy_join") for k in ("id_3d", "id_s1", "id_s2", "id_none", "ph_moved", "ph_still")))
        lst_b = page.inner_text("#openList")
        check("the ledger shows \"legacy join\" on the legacy call",
              "1 call(s) legacy join" in lst_b
              and "Milwaukee Brewers @ Los Angeles Dodgers" in folded(page, "#legacyJoin"), lst_b[:300])

        print("PLACEHOLDER KICKOFF (addendum 109 item 2 Q2)")
        check("a call recorded at the 04:00Z placeholder, its game at 23:30Z, is \"void: placeholder kickoff\"",
              b["ph_moved"].get("void_redated") == "void: placeholder kickoff" and b["ph_moved"]["status"] == "void"
              and "result" not in b["ph_moved"], json.dumps(b["ph_moved"])[:200])
        check("an unmoved placeholder kickoff is graded as today", b["ph_still"]["status"] == "graded"
              and b["ph_still"]["result"] == "loss" and "void_redated" not in b["ph_still"],
              json.dumps(b["ph_still"])[:200])
        pnl_b = page.inner_text("#pnlBlock")
        check("one void state, two labels: listed with its label, counted apart, out of every tally",
              "void: placeholder kickoff" in page.inner_text("#voidRedated")
              and "void: re-dated 1 · placeholder kickoff 1" in note_b
              and "Void: re-dated 1 · placeholder kickoff 1 (out of every line above" in pnl_b
              and sorted(x[0] for x in page.evaluate("settledBets(loadLedger()).map(b=>[b.call_type])"))
              == ["straight"] * 4, next((x for x in pnl_b.splitlines() if x.startswith("Void:")), ""))

        print("A MATCH ID IS MACHINE-LOCAL (the row of the id must name the call's teams)")
        # the host and the laptop number matches apart (deploy/hosting/compare_exports.py) and the Cockpit claims from
        # either machine's files: a call claimed from a host file carries the host's id, graded against laptop results
        nfl = functools.partial(call, sport="NFL", stage=None)
        page.evaluate("l => localStorage.setItem('bd_ledger_v1', JSON.stringify(l))", {
            "meta": {"policy_version": "v1.1"}, "calls": [
                nfl("kc_host", "Kansas City Chiefs", "Las Vegas Raiders", "2026-10-18T20:25:00", "2026-10-18",
                    match_id=50548),
                nfl("den_coll", "Denver Broncos", "Los Angeles Chargers", "2026-10-18T20:05:00", "2026-10-18",
                    match_id=50549),
                call("ars_pl", "Arsenal", "Chelsea", "2026-10-18T14:00:00", "2026-10-18", sport="SOCCER", stage=None,
                     three_way=True, match_id=7100)]})
        f_lap_mlb, f_lap_nfl, f_pl = (os.path.join(tmp, n) for n in ("lap_mlb.json", "lap_nfl.json", "pl_fx.json"))
        with open(f_lap_mlb, "w") as fh:     # laptop id 50548: a baseball game, the away side won
            json.dump({"sport": "mlb", "results": [
                res(50548, "Toronto Blue Jays", "Seattle Mariners", "2026-10-18T20:08:00", 2, 5)]}, fh)
        with open(f_lap_nfl, "w") as fh:     # the Chiefs' own game under the laptop's id; 50549 is another NFL game
            json.dump({"sport": "nfl", "results": [
                res(61234, "Kansas City Chiefs", "Las Vegas Raiders", "2026-10-18T20:25:00", 27, 20),
                res(50549, "Buffalo Bills", "New York Jets", "2026-10-18T17:00:00", 24, 10)]}, fh)
        with open(f_pl, "w") as fh:
            json.dump({"competition_code": "PL", "fixtures": [
                fixture(7100, "Arsenal FC", "Chelsea FC", "2026-10-18T14:00:00", 2, 1)]}, fh)
        note_m, m = intake(page, [f_lap_mlb, f_lap_nfl, f_pl])
        print("   ", note_m)
        kc, den = m["kc_host"], m["den_coll"]
        check("an NFL call whose id a loaded MLB row carries stays open: never graded on the baseball game",
              kc["status"] == "open" and "result" not in kc and "void_redated" not in kc and "close_ref" not in kc
              and kc.get("id_mismatch") is True, json.dumps(kc)[:200])
        check("a same-sport id on another game (other teams, 3h 05m apart) stays open, never voided as re-dated",
              den["status"] == "open" and "result" not in den and "void_redated" not in den
              and den.get("id_mismatch") is True, json.dumps(den)[:200])
        check("a soccer call pairs by id with a PL fixtures row naming its teams (the files name the sport apart)",
              m["ars_pl"]["status"] == "graded" and m["ars_pl"]["result"] == "win" and "id_mismatch" not in m["ars_pl"],
              json.dumps(m["ars_pl"])[:200])
        lst_m = page.inner_text("#idMismatch") if page.query_selector("#idMismatch") else ""
        check("the intake note counts them and the ledger lists them \"id mismatch\"",
              "id mismatch 2 (match id on another game: counted, never graded)" in note_m
              and "2 call(s) id mismatch" in lst_m and "match 50548" in lst_m and "match 50549" in lst_m, lst_m[:300])
        f_own = os.path.join(tmp, "lap_nfl_own.json")
        with open(f_own, "w") as fh:          # the Broncos' own game under 50549 beside another file's 50549
            json.dump({"sport": "nfl", "results": [
                res(50549, "Denver Broncos", "Los Angeles Chargers", "2026-10-18T20:05:00", 20, 23)]}, fh)
        note_o, o2 = intake(page, [f_lap_mlb, f_lap_nfl, f_own])
        check("its own game's row under the id grades it though another file's row carries the id; the flag clears",
              o2["den_coll"]["status"] == "graded" and o2["den_coll"]["result"] == "loss"
              and "id_mismatch" not in o2["den_coll"] and o2["kc_host"].get("id_mismatch") is True
              and "id mismatch 1 (" in note_o, json.dumps(o2["den_coll"])[:200])

        print("A LEGACY LEG GRADED, ITS TICKET WAITING (a re-log keeps the flag)")
        lz = functools.partial(call, call_type="parlay_leg", parlay_id="P-2026-10-16-Z", units=0.25, tier="parlay")
        page.evaluate("l => localStorage.setItem('bd_ledger_v1', JSON.stringify(l))", {
            "meta": {"policy_version": "v1.1"}, "calls": [
                lz("lz1", *NYM_PHI, "2026-10-17T17:05:00", "2026-10-16"),
                lz("lz2", "Chicago Cubs", "St. Louis Cardinals", "2026-10-19T00:05:00", "2026-10-16")]})
        f_lz = os.path.join(tmp, "legacy_leg.json")
        with open(f_lz, "w") as fh:
            json.dump({"sport": "mlb", "results": [res(21, *NYM_PHI, "2026-10-17T17:05:00", 6, 2)]}, fh)
        z = intake(page, f_lz)[1]["lz1"]
        check("the legacy join grades leg 1; its ticket waits (status open, a result, legacy join)",
              z.get("result") == "win" and z["status"] == "open" and z.get("legacy_join") is True, json.dumps(z)[:200])
        rz = page.evaluate("""c => { const L=loadLedger(); const r=upsertCalls(L,[c],{relog:true}); saveLedger(L);
            renderLedger(); return [r, L.calls.find(x=>x.id==='lz1')]; }""",
                           lz("lz1_relog", *NYM_PHI, "2026-10-17T17:05:00", "2026-10-17", parlay_id="P-2026-10-17-Z",
                              match_id=901))
        check("a re-log bringing a match id keeps the flag and the result (nothing grades that leg again)",
              rz[0]["repriced"] == 1 and rz[1].get("result") == "win" and rz[1]["status"] == "open"
              and rz[1].get("legacy_join") is True and rz[1].get("match_id") == 901
              and "1 call(s) legacy join" in folded(page, "#legacyJoin"), json.dumps(rz)[:300])

        print("THE RULED THREE-LEG TICKET (ARCHITECT 2026-10-17 11:00 ET, addendum 114 item 1)")
        # "Test: a three-leg ticket with one re-dated leg settles as a two-leg ticket when those two grade." Legs A, B, C
        # carry match ids; A is 50548 at its old start (10-17 00:00Z, moved to 10-18 21:00Z), B and C play on their dates
        tk = functools.partial(call, call_type="parlay_leg", units=0.25, tier="parlay")
        t3, lad_mil, bos_nyy = "P-2026-10-16-T3", ("Los Angeles Dodgers", "Milwaukee Brewers"), ("Boston Red Sox",
                                                                                                 "New York Yankees")
        page.evaluate("l => localStorage.setItem('bd_ledger_v1', JSON.stringify(l))", {
            "meta": {"policy_version": "v1.1"}, "calls": [
                tk("t_a", *TB_CLE, "2026-10-17T00:00:00", "2026-10-16", parlay_id=t3, match_id=50548),
                tk("t_b", *lad_mil, "2026-10-17T20:08:00", "2026-10-16", parlay_id=t3, match_id=50601, pick="AWAY",
                   market_p=0.45),
                tk("t_c", *NYM_PHI, "2026-10-17T23:05:00", "2026-10-16", parlay_id=t3, match_id=50602, market_p=0.5)]})
        relog_js = """cs => { const L=loadLedger(); const r=upsertCalls(L,cs,{relog:true}); saveLedger(L);
            return [r, L.calls.filter(x=>x.parlay_id==='P-2026-10-16-T3').map(x=>x.id).sort(),
                    L.calls.find(x=>x.id==='t_a')]; }"""
        fresh_a = tk("t_a_fresh", *TB_CLE, "2026-10-18T21:00:00", "2026-10-16", parlay_id=t3, match_id=50548)
        pre = page.evaluate(relog_js, [fresh_a])
        check("the moved game's fresh row is never substituted: a same-ticket re-log of leg A at the new kickoff is kept, "
              "A keeps its recorded kickoff", pre[0]["kept"] == 1 and pre[1] == ["t_a", "t_b", "t_c"]
              and pre[2]["kickoff"] == "2026-10-17T00:00:00" and pre[2]["status"] == "open", json.dumps(pre)[:300])
        # the later-day re-log: the 10-17 Desk re-emits the ticket (P-2026-10-17-T3, the same signature) with A at its new
        # start and B and C at theirs. B and C reprice into the 10-16 ticket by position; A misses the position index and
        # is that leg's moved game, never a one-leg ticket of its own (captured before B's kickoff: no tz-audit flag)
        d2 = functools.partial(tk, log_date="2026-10-17", parlay_id="P-2026-10-17-T3", captured_at="2026-10-17T12:00:00Z")
        later = page.evaluate("""cs => { const L=loadLedger(); const r=upsertCalls(L,cs,{relog:true}); saveLedger(L);
            return [r, L.calls.filter(x=>x.parlay_id!=='P-2026-10-16-T3').map(x=>x.id),
                    L.calls.find(x=>x.id==='t_a')]; }""", [
            d2("t_a_d2", *TB_CLE, "2026-10-18T21:00:00", match_id=50548),
            d2("t_b_d2", *lad_mil, "2026-10-17T20:08:00", match_id=50601, pick="AWAY", market_p=0.45),
            d2("t_c_d2", *NYM_PHI, "2026-10-17T23:05:00", match_id=50602, market_p=0.5)])
        check("a later-day re-log of the ticket with A at its new start: B and C reprice, A is kept, no ticket added "
              "(the moved game's fresh row is never a ticket of its own)",
              later[0] == {"added": 0, "updated": 0, "kept": 1, "repriced": 2} and later[1] == []
              and later[2]["kickoff"] == "2026-10-17T00:00:00", json.dumps(later)[:300])
        sandbox = page.evaluate("""([legacy, relogL, series, relogS]) => {
            const run=(calls,fresh)=>{ const L={meta:{policy_version:'v1.1'},calls:JSON.parse(JSON.stringify(calls))};
              return [upsertCalls(L,fresh,{relog:true}), L.calls.filter(x=>/^P-2026-10-17-/.test(x.parlay_id)).map(x=>x.id)]; };
            return [run(legacy,relogL), run(series,relogS)]; }""", [
            [tk("lg_a", *TB_CLE, "2026-10-17T00:00:00", "2026-10-16", parlay_id="P-2026-10-16-LG"),
             tk("lg_b", *lad_mil, "2026-10-17T20:08:00", "2026-10-16", parlay_id="P-2026-10-16-LG", pick="AWAY")],
            [tk("lg_a2", *TB_CLE, "2026-10-18T21:00:00", "2026-10-17", parlay_id="P-2026-10-17-LG", match_id=50548),
             tk("lg_b2", *lad_mil, "2026-10-17T20:08:00", "2026-10-17", parlay_id="P-2026-10-17-LG", pick="AWAY",
                match_id=50601)],
            [tk("sr_d", *NYM_PHI, "2026-10-16T23:05:00", "2026-10-16", parlay_id="P-2026-10-16-SR", match_id=9101),
             tk("sr_e", *bos_nyy, "2026-10-18T23:00:00", "2026-10-16", parlay_id="P-2026-10-16-SR", match_id=50603)],
            [tk("sr_d2", *NYM_PHI, "2026-10-17T23:05:00", "2026-10-17", parlay_id="P-2026-10-17-SR", match_id=9102),
             tk("sr_e2", *bos_nyy, "2026-10-18T23:00:00", "2026-10-17", parlay_id="P-2026-10-17-SR", match_id=50603)]])
        check("... a legacy ticket (no match id) the same: its sibling leg anchors it, the moved leg is kept, nothing added; "
              "a different match id (the series' next game) is never read as moved (added, as before)",
              sandbox[0] == [{"added": 0, "updated": 0, "kept": 1, "repriced": 1}, []]
              and sandbox[1] == [{"added": 1, "updated": 0, "kept": 0, "repriced": 1}, ["sr_d2"]], json.dumps(sandbox))
        t3_files = {}
        for day, rows in (("1", [res(50548, *TB_CLE, "2026-10-18T21:00:00", 5, 2),
                                 res(50601, *lad_mil, "2026-10-17T20:08:00", 1, 4)]),
                          ("1b", [res(50548, *TB_CLE, "2026-10-17T00:00:00", 1, 3)]),   # A's id at its old start
                          ("2", [res(50548, *TB_CLE, "2026-10-18T21:00:00", 5, 2),
                                 res(50601, *lad_mil, "2026-10-17T20:08:00", 1, 4),
                                 res(50602, *NYM_PHI, "2026-10-17T23:05:00", 6, 2)]),
                          ("3", [res(50548, *TB_CLE, "2026-10-17T00:00:00", 1, 3),     # A's id at its old start
                                 res(50601, *lad_mil, "2026-10-17T20:08:00", 4, 1),
                                 res(50602, *NYM_PHI, "2026-10-17T23:05:00", 2, 6)])):
            t3_files[day] = os.path.join(tmp, f"t3_{day}.json")
            with open(t3_files[day], "w") as fh:
                json.dump({"sport": "mlb", "results": rows}, fh)
        n1, t1 = intake(page, t3_files["1"])
        a1, b1, c1 = t1["t_a"], t1["t_b"], t1["t_c"]
        check("intake 1: leg A is void with the ruling's label, a push: units 0.25 unchanged on the record, no result, "
              "no share of the ticket", a1.get("void_redated") == LABEL_50548 and a1["status"] == "void"
              and a1["units"] == 0.25 and not any(k in a1 for k in ("result", "units_returned", "ticket_result")),
              json.dumps(a1)[:300])
        check("... the ticket is not settled while C is open (B graded, waiting; C open; nothing graded)",
              b1.get("result") == "win" and b1["status"] == "open" and c1["status"] == "open" and "result" not in c1
              and not any("ticket_result" in x for x in (a1, b1, c1)) and "0 calls/tickets graded" in n1, n1[:120])
        check("the void list says where A's ticket stands",
              "a push, removed from its ticket: ticket awaiting its other 2 leg(s)" in folded(page, "#voidRedated"))
        n1b, t1b = intake(page, t3_files["1b"])
        check("a push is final: a later intake holding a row for A within the hour of its kickoff (the void the earlier "
              "rule could undo) leaves A void, the ticket waiting on C", t1b["t_a"] == a1 and t1b["t_c"]["status"] == "open"
              and "result" not in t1b["t_c"] and not any("ticket_result" in x for x in t1b.values())
              and "0 calls/tickets graded" in n1b, json.dumps(t1b["t_a"])[:300])
        straight_a = call("a_fresh_straight", *TB_CLE, "2026-10-18T21:00:00", "2026-10-18", match_id=50548)
        post = page.evaluate(relog_js, [fresh_a, straight_a])
        check("after the void: the re-log never reopens A (kept); a fresh call on A's game at the new start is its own "
              "call, never a leg of the ticket", post[0]["kept"] == 1 and post[0]["added"] == 1
              and post[1] == ["t_a", "t_b", "t_c"] and post[2] == a1, json.dumps(post)[:300])
        n2, t2 = intake(page, t3_files["2"])
        want = round(0.25 / 0.45 / 0.5, 4)
        check("intake 2: B and C graded, the ticket settles as a two-leg ticket priced on B and C (0.25 / 0.45 / 0.5)",
              all(t2[k]["status"] == "graded" and t2[k].get("ticket_result") == "win"
                  and t2[k].get("units_returned") == want and t2[k].get("ticket_legs") == 2 for k in ("t_b", "t_c")),
              json.dumps(t2["t_c"])[:300])
        check("... leg A stays on the record as it was: labelled, units unchanged, status void, no ticket fields",
              t2["t_a"] == a1, json.dumps(t2["t_a"])[:300])
        check("... the fresh call on A's game is graded on its own (a win), never part of the ticket",
              t2["a_fresh_straight"]["status"] == "graded" and t2["a_fresh_straight"]["result"] == "win"
              and "parlay_id" not in t2["a_fresh_straight"] and "2 calls/tickets graded" in n2, n2[:120])
        bets3 = page.evaluate("settledBets(loadLedger()).filter(b=>b.call_type==='parlay')"
                              ".map(b=>[b.staked,b.returned,b.result])")
        check("settledBets: the ticket once, staked 0.25u, returned as the two-leg ticket (the later-day re-log added "
              "no one-leg ticket on A's moved game)", bets3 == [[0.25, want, "win"]], json.dumps(bets3))
        check("the void list: A's ticket settled on its other 2 legs",
              "a push, removed from its ticket: ticket settled on its other 2 leg(s)" in folded(page, "#voidRedated"))
        L3 = page.evaluate("JSON.parse(localStorage.getItem('bd_ledger_v1'))")
        n3, _ = intake(page, t3_files["3"])
        check("a ticket settles once: a later intake (A's id at its old start, B and C reversed) changes nothing",
              page.evaluate("JSON.parse(localStorage.getItem('bd_ledger_v1'))")["calls"] == L3["calls"]
              and "0 calls/tickets graded" in n3, n3[:120])

        print("A ONE-LEG REMAINDER, EVERY LEG MOVED, GRADED BEFORE THIS CHANGE (addendum 114 items 1-2; addendum 115 item 4)")
        old_t = "P-2026-10-10-OLD"
        # graded before the match-id pairing: no match id, no flag, as the live ledger holds them
        before = [
            {**call("g_straight", *NYM_PHI, "2026-10-10T23:05:00", "2026-10-10"), "status": "graded", "result": "win",
             "graded_date": "2026-10-11", "units_returned": 1.7857, "claim_units_returned": 1.75},
            {**tk("g_leg1", *lad_mil, "2026-10-10T20:00:00", "2026-10-10", parlay_id=old_t, pick="AWAY", market_p=0.45),
             "status": "graded", "result": "win", "graded_date": "2026-10-11", "units_returned": 1.1111,
             "ticket_result": "win"},
            {**tk("g_leg2", *bos_nyy, "2026-10-10T23:00:00", "2026-10-10", parlay_id=old_t, market_p=0.5),
             "status": "graded", "result": "win", "graded_date": "2026-10-11", "units_returned": 1.1111,
             "ticket_result": "win"},
            {**call("g_by_id", "Texas Rangers", "Houston Astros", "2026-10-16T23:00:00", "2026-10-16", match_id=50604),
             "status": "graded", "result": "loss", "graded_date": "2026-10-17", "units_returned": 0},
            call("g_open", "Toronto Blue Jays", "Seattle Mariners", "2026-10-19T20:00:00", "2026-10-18")]
        page.evaluate("l => localStorage.setItem('bd_ledger_v1', JSON.stringify(l))", {
            "meta": {"policy_version": "v1.1"}, "calls": [
                tk("s_a", *TB_CLE, "2026-10-17T00:00:00", "2026-10-16", parlay_id="P-2026-10-16-T2", match_id=50548),
                tk("s_b", *bos_nyy, "2026-10-17T23:00:00", "2026-10-16", parlay_id="P-2026-10-16-T2", match_id=50603,
                   market_p=0.6),
                tk("v_a", *TB_CLE, "2026-10-17T00:00:00", "2026-10-16", parlay_id="P-2026-10-16-T0", match_id=50548,
                   pick="AWAY", market_p=0.44, exec_mode="operator_early"),
                tk("v_b", "Hawaii Rainbow Warriors", "Wyoming Cowboys", "2026-10-17T04:00:00", "2026-10-16",
                   parlay_id="P-2026-10-16-T0", sport="NCAA", match_id=8801, stage=None, exec_mode="operator_early"),
                *before]})
        page.evaluate("cs => importLedgerDoc({calls: cs})", before[1:])
        imp_note = page.inner_text("#ledgerNote")
        check("an import of the rows as stored before the label is not \"updated\" by it (the label is computed on both "
              "sides)", "Imported 4 calls: 0 new · 0 updated · 4 unchanged/kept" in imp_note, imp_note[:120])
        f_s, f_s_ncaa = os.path.join(tmp, "single_push.json"), os.path.join(tmp, "single_push_ncaa.json")
        with open(f_s, "w") as fh:
            json.dump({"sport": "mlb", "results": [
                res(50548, *TB_CLE, "2026-10-18T21:00:00", 5, 2),
                res(50603, *bos_nyy, "2026-10-17T23:00:00", 4, 2),
                res(9001, *NYM_PHI, "2026-10-10T23:05:00", 1, 3)]}, fh)      # g_straight's game: the row disagrees
        with open(f_s_ncaa, "w") as fh:
            json.dump({"competition_code": "NCAA", "fixtures": [
                fixture(8801, "Hawaii Rainbow Warriors", "Wyoming Cowboys", "2026-10-17T23:30:00", 31, 24)]}, fh)
        note_s, s = intake(page, [f_s, f_s_ncaa])
        print("   ", note_s)
        single = round(page.evaluate("settleReturn(0.25,'win',0.6)"), 4)
        check("a two-leg ticket with one re-dated leg settles as a single on the other leg (0.25 / 0.6, settleReturn's)",
              s["s_b"]["status"] == "graded" and s["s_b"].get("ticket_result") == "win"
              and s["s_b"].get("units_returned") == single and s["s_b"].get("ticket_legs") == 1
              and s["s_a"].get("void_redated") == LABEL_50548
              and not any(k in s["s_a"] for k in ("ticket_result", "units_returned")), json.dumps(s["s_b"])[:300])
        va, vb = s["v_a"], s["v_b"]
        check("a ticket whose every leg moved (either label) settles as a push: stake back on its void legs, labels, "
              "status and units kept", (va.get("void_redated"), vb.get("void_redated")) == (LABEL_50548, PLACEHOLDER_LABEL)
              and all(x["status"] == "void" and x.get("ticket_result") == "push" and x.get("units_returned") == 0.25
                      and x["units"] == 0.25 and x.get("ticket_legs") == 0 and "result" not in x for x in (va, vb)),
              json.dumps(va)[:300])
        pb = page.evaluate("(()=>{const b=settledBets(loadLedger());return {p:b.filter(x=>x.call_type==='parlay')"
                           ".map(x=>[x.staked,x.returned,x.result]).sort(),a:agg(b.filter(x=>x.result==='push'))};})()")
        check("the tallies count the push as a push: one bet, staked 0.25u, returned 0.25u, net 0, out of the hit rate",
              [0.25, 0.25, "push"] in pb["p"] and [0.25, single, "win"] in pb["p"] and pb["a"]["n"] == 1
              and pb["a"]["net"] == 0 and pb["a"]["hit"] is None, json.dumps(pb))
        pnl_p = page.inner_text("#pnlBlock")
        early_p = next((x for x in pnl_p.splitlines() if x.startswith("Early executions")), "")
        check("the every-leg-moved ticket, executed early, is one early position (its push is a settled bet, as a pushed "
              "straight is); the P&L block's Void line names that exception",
              "Early executions: 1 position(s)" in early_p and "(1/50)" in early_p
              and "(out of every line above, except a ticket whose every leg moved: counted there once, as a push;"
              in pnl_p, early_p)
        vtext = folded(page, "#voidRedated")
        check("the void list: a single on the other leg; every leg moved, a push",
              "ticket settled on its other 1 leg(s) (a single)" in vtext
              and vtext.count("every leg moved, the ticket settled as a push") == 2, vtext[:400])
        check("the intake grades the two tickets and nothing graded before (2 calls/tickets graded)",
              "2 calls/tickets graded" in note_s, note_s[:120])
        seeded = {c["id"]: c for c in before}
        keys = ("status", "result", "units_returned", "claim_units_returned", "graded_date", "ticket_result")
        check("graded before this change (no match id): labelled legacy join, its status, result and returns unchanged "
              "(the disagreeing row re-grades nothing)",
              all(s[k].get("legacy_join") is True and all(s[k].get(f) == seeded[k].get(f) for f in keys)
                  for k in ("g_straight", "g_leg1", "g_leg2")), json.dumps(s["g_straight"])[:300])
        check("... a call graded by its match id, an open call and the legs with ids carry no label",
              not any(s[k].get("legacy_join") for k in ("g_by_id", "g_open", "s_a", "s_b", "v_a", "v_b")))
        ljs = folded(page, "#legacyJoin")
        pnl_s = page.inner_text("#pnlBlock")
        check("the ledger lists them \"legacy join\"; the intake note and the P&L block count them",
              "3 call(s) legacy join" in ljs and ljs.count("legacy join") == 4
              and "Philadelphia Phillies @ New York Mets" in ljs and "legacy join 3 (no match id" in note_s
              and "Legacy join: 3 call(s) paired" in pnl_s, ljs[:300])
        with page.expect_download() as dl:
            page.click("#exportLedgerBtn")
        ex = {c["id"]: c for c in json.load(open(dl.value.path()))["calls"]}
        check("the ledger JSON export carries legacy_join on the calls graded before, and only there",
              sorted(k for k, c in ex.items() if c.get("legacy_join")) == ["g_leg1", "g_leg2", "g_straight"]
              and all(ex[k].get(f) == seeded[k].get(f) for k in ("g_straight", "g_leg1", "g_leg2") for f in keys),
              json.dumps(sorted(k for k, c in ex.items() if c.get("legacy_join"))))
        Ls = page.evaluate("JSON.parse(localStorage.getItem('bd_ledger_v1'))")
        n_s2, _ = intake(page, [f_s, f_s_ncaa])
        check("the settle-once guard holds for the single and the push: a later intake changes nothing",
              page.evaluate("JSON.parse(localStorage.getItem('bd_ledger_v1'))")["calls"] == Ls["calls"]
              and "0 calls/tickets graded" in n_s2, n_s2[:120])
        check("no page errors", not errors, "; ".join(errors))
        browser.close()
    srv.shutdown()
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed" + (" — ALL GREEN" if all(CHECKS) else " — FAILURES ABOVE"))
    return 0 if all(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
