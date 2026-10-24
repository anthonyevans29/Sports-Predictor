"""
#431 THE CLOSING MARKS, headless (Chromium): the dedupe, the laptop control and the marks they feed, through the
Cockpit's own load, intake and import paths. A manual receipt, as every cockpit_*_verify (Playwright is not in CI;
tests/test_cockpit_closing_marks.py runs the same page under node in CI).

ARCHITECT 2026-10-11, addendum 40 item 2: "In the ledger a position is executed where its closing file calls it. A claim
that the closing page does not repeat was not executed: it stays in the ledger as a claim, marked, and it leaves the P&L
and the counts that gate sizing. A shadow follows the same rule." Built as RULED (ARCHITECT 2026-10-20, addendum 145
item 3(b)):
  R1 "APPROVED as proposed: the closing file's row stands over any slate row for its games; among pages of one family
  and start the newest desk_meta.as_of wins. A rule by kind, never by the listing's order."
  R10 "APPROVED: out of settledBets (the P&L, the counterfactuals, the Sizing gate N/50) and gradedCount (the four n/30
  counters, ledgerSummary.counts); kept in executedPositions and clvLines, the claim-against-close read, as the
  ruling's own words keep it."
  R11 "APPROVED: automatic on load, after autoClaim — "a closing document marks". The mark is shown and logged; no
  button."
  R14 "APPROVED: the control's note when the ledger has no claim on a covered game, and the runbook line "import the
  ledger, then load"; plus the 144 item 4 note (counts_source default 0) beside the ledger's own counts."

One NFL day (2026-10-19, every game at 17:00Z), written through the Python Desk as the exports write it
(cockpit_desk_files, base=False: the Desk as it runs today, whose exec block the marks read) and the closing page through
the closing run's own writer (deploy/hosting/closing.py closing_doc, closing_name): the 12:00Z slate (Buffalo PLAY exec
+5.3pp; Miami PLAY exec +1.2pp, its QB listed; Dallas PLAY exec -1.6pp; Denver PLAY; Newark quarantine shadow; Tampa
value shadow AWAY) with its desk_parlays file, and the 16:25Z closing page (Denver PASS, Tampa no value shadow).
- (a) the Codex P1: the slate (Buffalo quoted 0.50/0.51) and the closing (0.54/0.55) in one load, in EITHER listing
  order: one row per game, every one the closing page's, Buffalo's claim at the closing's exec cost and as_of, the same
  Desk summary (its closing line) and a byte-identical stored ledger. The base page (main) holds both files' rows;
- (b) the marks, shown with the closing call: after the slate's claims and their results, the closing page marks the
  claims it did not repeat (Miami and Dallas: holds that end in no bet, R6; Denver: PASS; Tampa's value shadow; every
  ticket leg, R5) and not Buffalo's PLAY or Newark's shadow, which it repeats; the load note logs them and the ledger
  lists each beside the page's own words (#notExecuted). On the day's order (the closing before the results) the open
  table marks them NOT EXECUTED with no Execute now and no Record fill, on a marked call or any leg of its ticket (R7);
- (c) the P&L, the Sizing gate and the n/30 counts leave the marked positions out (lastNotExec, the P&L block's line),
  and nothing is deleted: the same calls in the same order, every stored field equal once not_executed is stripped,
  each marked claim keeping its own result; the day's order ends with the same marks and the same P&L block;
- (d) no closing file: the Desk summary, the load and intake notes, the rows, the P&L block (its Not executed line,
  reading 0, set aside) and ledgerSummary are the base page's (main) byte for byte, and so is the stored ledger once
  the call id is set aside: each id differs only by the pick R4 adds to callKey;
- (e) the laptop control against a routed fake GitHub API (page.route; no network): it lists laptop/latest and
  laptop/<yesterday UTC>, laptop/<today UTC> (in that order), fetches exactly the JSON files of latest but its closing_*
  copy and the closing_*.json of the day folders (every path segment encoded: "coverage #1.json" is requested as
  coverage%20%231.json, which the browser would not do by itself, a "#" starting a fragment), names the 404 day folder
  (not fatal) and the file that answered 500 (never loaded, though its body is a real MLB closing page that would put
  an MLB row on the Desk); with an empty ledger the load claims the morning's tickets (latest's
  desk_parlays.json, at its as_of) and the page marks them (R5), and its note carries R14's line for the games no
  ticket touches; after "import the ledger, then load" it carries (b)'s marks and no R14 line; the host control's
  function is the base page's, unchanged;
- (f) a 401 on laptop/latest says so, fetches nothing more and loads nothing (rows and ledger as they were).

    python3 scripts/cockpit_closing_verify.py [--base origin/main]

--base is the ref whose tools/cockpit.html (d) and (a)'s contrast read (git show). Writes nothing to the repo (the
results file goes to a temporary directory, removed); no DB; the browser's localStorage lives in throwaway contexts.
Needs Playwright + Chromium and git.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "deploy", "hosting"))
import closing as mc  # noqa: E402  (the closing run's own closing block and file name)
import cockpit_desk_files as cdf  # noqa: E402

CHECKS = []
ERRORS = []
URL = "http://cockpit.invalid/cockpit.html"          # served from memory (page.route): nothing else is reached
API = "https://api.github.com/repos/anthonyevans29/Sports-Predictor-exports/contents/"
LIST, RAW, AUTH = "application/vnd.github+json", "application/vnd.github.raw+json", "Bearer github_pat_TEST"
SLATE_AT = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
CLOSE_AT = datetime(2026, 10, 19, 16, 25, tzinfo=timezone.utc)
START = datetime(2026, 10, 19, 17, 0, tzinfo=timezone.utc)
AT_SLATE = SLATE_AT + timedelta(minutes=5)                        # the browser's clock at the morning load
AT_CLOSE = datetime(2026, 10, 19, 16, 30, tzinfo=timezone.utc)   # after the page, before kickoff: 10-18 and 10-19 UTC
AT_RESULTS = datetime(2026, 10, 20, 4, 0, tzinfo=timezone.utc)    # the next morning's results intake
RUN = "20261019T162500Z-nfl"
SN, PN = "nfl_predictions_2026-10-19.json", "desk_parlays.json"
CN = mc.closing_name("NFL", START)                                # closing_NFL_2026-10-19T1700Z.json
MLB_START = datetime(2026, 10, 19, 23, 0, tzinfo=timezone.utc)
CM = mc.closing_name("MLB", MLB_START)                            # closing_MLB_2026-10-19T2300Z.json
COVN = "coverage #1.json"                                         # encodeURIComponent: coverage%20%231.json
STARTZ = "2026-10-19T17:00:00Z"
DEDUPE = f" · closing: 1 file(s) (NFL {STARTZ}) · 6 slate row(s) replaced by their closing row · 0 superseded by a later page"
R14 = (" covered game(s) hold no claim from before their page in this browser's ledger: nothing there to mark. A local"
       " Cockpit keeps its own ledger: import the ledger, then load.")
# match id: (home, p_home, books' fair home, Kalshi bid, ask). Away = "<home> Visitors".
GAMES = {301: ("Buffalo", 0.62, 0.55, 0.54, 0.55),   # PLAY, exec +5.3pp: the page repeats it
         306: ("Miami", 0.60, 0.55, 0.56, 0.57),     # PLAY, exec +1.2pp, a QB listed for the picked (home) team
         307: ("Dallas", 0.60, 0.55, 0.59, 0.60),    # PLAY, exec -1.6pp, the away team's injury list unread
         304: ("Denver", 0.52, 0.515, 0.51, 0.52),   # PASS on the page (the slate's p 0.60: PLAY there)
         302: ("Newark", 0.75, 0.55, 0.54, 0.55),    # quarantine shadow, on both
         303: ("Tampa", 0.60, 0.70, 0.69, 0.70)}     # value shadow AWAY on the slate; none on the page (p 0.68)
INJURIES = {306: {"home": {"count": 2, "qb_listed": ["H. Quarterback"]}, "away": {"count": 1, "qb_listed": []}},
            307: {"home": {"count": 2, "qb_listed": []}, "away": {"count": 0, "qb_listed": []}}}
SCORES = {301: (24, 17), 306: (10, 20), 307: (27, 13), 304: (21, 14), 302: (3, 9), 303: (13, 20)}
COV = {"kind": "coverage_v1", "date": "2026-10-19", "now": "2026-10-19T16:30:00Z", "now_et": "", "competitions": [],
       "gaps": [], "roadmap": [], "roadmap_unread": None}

# the page's state after a step: the stored ledger, the P&L block, ledgerSummary (its clock field left out), the
# settledBets counts and lastNotExec (null on a page without it), the notes and the marks
SNAP = r"""()=>{ renderLedger(); const L=loadLedger(), bets=settledBets(L), real=bets.filter(b=>!b.shadow);
  const t=id=>{ const e=document.getElementById(id); return e?e.textContent:null; };
  const br=id=>{ const e=document.getElementById(id); return e?e.innerHTML.split("<br>").map(h=>{
    const d=document.createElement("div"); d.innerHTML=h; return d.textContent; }):null; };
  const s=ledgerSummary(); delete s.generated_at;
  const ne=typeof lastNotExec==="undefined"?null:{...lastNotExec};
  return {stored:localStorage.getItem(LEDGER_KEY),pnl:pnlBlock(L),ledgerSummary:s,ne,
    bets:{n:bets.length,real:real.length,shadow:bets.length-real.length,
      model_edge:real.filter(b=>b.engine==="model_edge").length,tickets:bets.filter(b=>b.call_type==="parlay").length},
    calls:L.calls.length,summary:t("summary"),logNote:t("logNote"),ledgerNote:t("ledgerNote"),
    notExecuted:br("notExecuted"),notExecLine:t("notExecLine"),openList:document.getElementById("openList").innerHTML,
    rows:JSON.stringify(rows),nRows:rows.length,desk:deskCalls.length,
    marks:L.calls.filter(c=>c.not_executed).map(c=>({key:`${c.home}|${c.call_type}|${c.pick}|${c.parlay_id||""}`,
      id:c.id,game:c.game,side:c.pick==="HOME"?c.home:c.pick==="AWAY"?c.away:c.pick,engine:c.engine,
      call_type:c.call_type,status:c.status,result:c.result||null,parlay_id:c.parlay_id||null,
      text:c.not_executed.closing_call.text,closing:c.not_executed.closing}))}; }"""
LOAD = r"""async ds=>{ const did=await loadDocs(ds);
  return {refused:did.refused,closings:did.closings?{files:did.closings.files,superseded:did.closings.superseded,
    copies:did.closings.copies,slateRowsDropped:did.closings.slateRowsDropped,
    marked:did.closings.marks?did.closings.marks.marked:null}:null}; }"""


def check(label, ok, detail=""):
    CHECKS.append(bool(ok))
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


def row(mid, home, p_home, fair_h, bid, ask, comp="NFL", start=START):
    """An --desk export row before the Desk (tests/test_closing_runs.py's row()): NFL, or MLB with both starters."""
    tick, series = home[:3].upper(), f"KX{comp}GAME"
    r = {"match_id": mid, "home_team": home, "away_team": f"{home} Visitors", "competition": comp, "stage": "regular",
         "utc_date": start.strftime("%Y-%m-%dT%H:%M:%S"),
         "prediction": {"probabilities": {"home_win": p_home, "draw": None, "away_win": round(1 - p_home, 4)},
                        "tier": "lean"},
         "market": {"bookmaker_count": 9, "fair_prob": {"HOME": fair_h, "AWAY": round(1 - fair_h, 4)}},
         "kalshi_bid": bid, "kalshi_ask": ask,
         "kalshi_legs": {"HOME": {"ticker": f"{series}-26OCT19-{tick}H", "bid": bid, "ask": ask},
                         "AWAY": {"ticker": f"{series}-26OCT19-{tick}A", "bid": round(1 - ask, 2),
                                  "ask": round(1 - bid, 2)}}}
    if comp != "NFL":
        r["pitchers"] = {s: {"name": f"{s} starter", "kind": "confirmed"} for s in ("home", "away")}
        return r
    r["market_divergence_pp"] = round((p_home - fair_h) * 100, 1)
    r["quarantine"] = abs(r["market_divergence_pp"]) >= 15
    if mid in INJURIES:
        r["input_quality"] = {"injuries": INJURIES[mid]}
    return r


def nfl(quotes=None, **p_home):
    rows = []
    for mid, (home, p, fh, b, a) in GAMES.items():
        b, a = (quotes or {}).get(home, (b, a))
        rows.append(row(mid, home, p_home.get(home, p), fh, b, a))
    return {"sport": "nfl", "predictions": rows}


def docs():
    """{name: doc}: the slate and its tickets file, the moved slate, the closing page, the results, and an MLB closing
    page (Clearwater at 23:00Z: the body of (e)'s file that answers 500)."""
    slate = cdf.desk_files({SN: nfl(Denver=0.60)}, SLATE_AT, parlays=True, base=False)
    moved = cdf.desk_files({SN: nfl({"Buffalo": (0.50, 0.51)}, Denver=0.60)}, SLATE_AT, parlays=False, base=False)
    page = cdf.desk_files({"nfl.json": nfl(Tampa=0.68)}, CLOSE_AT, parlays=False, base=False)["nfl.json"]
    closing = mc.closing_doc(page, "NFL", START, RUN, [r["match_id"] for r in page["predictions"]], [])
    mlb = cdf.desk_files({"mlb.json": {"sport": "mlb", "predictions": [
        row(401, "Clearwater", 0.60, 0.53, 0.51, 0.52, comp="MLB", start=MLB_START)]}},
        MLB_START - timedelta(minutes=35), parlays=False, base=False)["mlb.json"]
    results = {"sport": "nfl", "results": [
        {"match_id": m, "date": START.strftime("%Y-%m-%dT%H:%M:%S"), "home_team": h, "away_team": f"{h} Visitors",
         "actual": {"home_score": SCORES[m][0], "away_score": SCORES[m][1],
                    "result": "H" if SCORES[m][0] > SCORES[m][1] else "A"},
         "graded": {"close_fair": {"HOME": GAMES[m][2], "AWAY": round(1 - GAMES[m][2], 4)}}}
        for m, (h, *_) in GAMES.items()]}
    return {"slate": slate[SN], "parlays": slate[PN], "moved": moved[SN], "closing": closing, "results": results,
            "mlb_closing": mc.closing_doc(mlb, "MLB", MLB_START, "20261019T222500Z-mlb", [401], [])}


def doc(name, d):
    return {"name": name, "text": json.dumps(d)}


class Pages:
    """Every page in its own browser context (its own localStorage), served from memory at URL with its clock fixed;
    every request but the page (and a routed GitHub API) is aborted."""
    def __init__(self, browser, html):
        self.browser, self.html, self.ctxs = browser, html, []

    def open(self, label, at, api=None):
        ctx = self.browser.new_context(timezone_id="UTC")
        self.ctxs.append(ctx)
        page = ctx.new_page()
        page.on("pageerror", lambda e: ERRORS.append(f"{label}: {e}"))
        page.route("**/*", lambda route, req: route.fulfill(status=200, content_type="text/html; charset=utf-8",
                                                            body=self.html[label]) if req.url == URL
                   else route.abort())
        if api:
            page.route("https://api.github.com/**", api)
        page.clock.set_fixed_time(at)
        page.goto(URL)
        return page

    def close(self):
        for c in self.ctxs:
            c.close()


def intake(page, path, at):
    """The results file through the Cockpit's own intake (#resultsFile), at the next morning's clock."""
    page.clock.set_fixed_time(at)
    page.evaluate("document.getElementById('ledgerNote').textContent=''")
    page.set_input_files("#resultsFile", [path])
    page.wait_for_function("document.getElementById('ledgerNote').textContent.includes('finished results read')")


class FakeGitHub:
    """api.github.com/repos/<repo>/contents/<path>, routed: {path: (status, body)}; every request recorded."""
    def __init__(self):
        self.routes, self.seen = {}, []

    def __call__(self, route, request):
        url = request.url
        self.seen.append((url, request.headers.get("accept"), request.headers.get("authorization")))
        got = self.routes.get(url[len(API):] if url.startswith(API) else url)
        if got is None:
            return route.fulfill(status=404, content_type="application/json", body='{"message":"Not Found"}')
        st, body = got
        return route.fulfill(status=st, content_type="application/json",
                             body=body if isinstance(body, str) else json.dumps(body))


def stripped(stored):
    """The stored calls with the mark set aside (R11: the mark is the only field the page adds)."""
    return [{k: v for k, v in c.items() if k != "not_executed"} for c in json.loads(stored)["calls"]]


# #431 R16 (ARCHITECT 2026-10-20, addendum 146 item 1(iv)): every claim stores the page's order at claim (kalshi_order,
# claim_order) and at execution (exec_order); R17: every normalized row keeps its Kalshi legs (kLegs). Fields the base
# page never wrote, set aside in (d) and checked present on every head call
R16_FIELDS = ("kalshi_order", "claim_order", "exec_order")


def no_id(stored, aside=("id",)):
    L = json.loads(stored)
    return {"meta": L["meta"], "calls": [{k: v for k, v in c.items() if k not in aside} for c in L["calls"]]}


def no_legs(rows):
    return [{k: v for k, v in r.items() if k != "kLegs"} for r in json.loads(rows)]


def r4_id(c, pick):
    keys = ("sport", "game", "log_date", "engine", "call_type")
    return "|".join([str(c[k]) for k in keys] + ([pick] if pick else []) + [c.get("parlay_id") or ""])


def main(argv=None):
    ap = argparse.ArgumentParser(description="#431 closing marks: the dedupe, the laptop control, the marks (headless).")
    ap.add_argument("--base", default="origin/main", help="the ref whose tools/cockpit.html (d) compares against")
    a = ap.parse_args(argv)
    got = subprocess.run(["git", "-C", ROOT, "show", f"{a.base}:tools/cockpit.html"], capture_output=True, text=True)
    if got.returncode != 0 or "<script>" not in got.stdout:
        print(f"REFUSED: git show {a.base}:tools/cockpit.html did not answer (is the ref fetched?)")
        return 2
    with open(os.path.join(ROOT, "tools", "cockpit.html"), encoding="utf-8") as f:
        html = {"head": f.read(), "base": got.stdout}
    D = docs()
    tmp = tempfile.mkdtemp(prefix="cockpit-closing-")
    results = os.path.join(tmp, "nfl_NFL_results_2026-10-19.json")
    with open(results, "w") as f:
        json.dump(D["results"], f)
    slate = [doc(SN, D["slate"]), doc(PN, D["parlays"])]
    try:
        with sync_playwright() as pw:
            exe = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**({"executable_path": exe} if os.path.isfile(exe) else {}))
            pages = Pages(browser, html)
            try:
                run(pages, D, slate, results, a.base)
            finally:
                pages.close()
                browser.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    check("no page errors", not ERRORS, "; ".join(ERRORS[:3]))
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed" + (" — ALL GREEN" if all(CHECKS) else ""))
    return 0 if all(CHECKS) else 1


def run(pages, D, slate, results, base):
    print("(a) the Codex P1: the slate and its closing in one load, either listing order (R1)")
    res = []
    for order in ((doc(SN, D["moved"]), doc(CN, D["closing"])), (doc(CN, D["closing"]), doc(SN, D["moved"]))):
        p = pages.open("head", AT_CLOSE)
        did = p.evaluate(LOAD, list(order))
        s = p.evaluate(SNAP)
        s["did"] = did
        s.update(p.evaluate("""cn=>{ const b=loadLedger().calls.find(c=>c.home==="Buffalo"&&c.call_type==="straight");
          return {games:rows.map(r=>r.home),closingRows:rows.filter(r=>r.closing&&r.closing.file===cn).length,
            trs:document.querySelectorAll("#slate tbody tr:not(.vshadow)").length,
            bufK:b.claim_exec_cost,bufAt:b.claim_at}; }""", CN))
        res.append(s)
    k = p.evaluate("ds=>ds.map(d=>normalize(d).find(r=>r.home==='Buffalo').fileDesk.exec.cost)",
                   [D["closing"], D["moved"]])
    check("the slate quotes Buffalo at another exec cost than its closing page", k[0] != k[1],
          f"closing {k[0]} · slate {k[1]}")
    check("either order: 6 rows, one per game, every one the closing page's; the Desk table 6 rows",
          all(r["nRows"] == r["desk"] == r["trs"] == r["closingRows"] == 6 and len(set(r["games"])) == 6 for r in res),
          str([(r["nRows"], r["closingRows"], r["trs"]) for r in res]))
    check("either order: Buffalo's claim carries the closing page's exec cost at its as_of, never the slate's",
          all(r["bufK"] == k[0] and r["bufAt"] == "2026-10-19T16:25:00.000Z" for r in res),
          f"claim {[r['bufK'] for r in res]} at {[r['bufAt'] for r in res]}")
    check("either order: the same Desk summary, naming the dedupe; a byte-identical stored ledger",
          res[0]["summary"] == res[1]["summary"] and res[0]["summary"].endswith(DEDUPE)
          and res[0]["stored"] == res[1]["stored"] and res[0]["did"]["closings"]["slateRowsDropped"] == 6,
          res[0]["summary"][-len(DEDUPE) - 10:])
    p = pages.open("base", AT_CLOSE)
    p.evaluate(LOAD, [doc(SN, D["moved"]), doc(CN, D["closing"])])
    n = p.evaluate("rows.length")
    check("the base page holds both files' rows for the same load (the defect R1 closes)", n == 12, f"{n} rows")

    print("(b) the marks, shown with the closing call (R5, R6, R11): the slate, its results, then the page")
    p = pages.open("head", AT_SLATE)
    p.evaluate(LOAD, slate)
    intake(p, results, AT_RESULTS)
    A = p.evaluate(SNAP)
    did = p.evaluate(LOAD, [doc(CN, D["closing"])])
    B = p.evaluate(SNAP)
    marks = {m["key"]: m for m in B["marks"]}
    singles = sorted(k for k in marks if not marks[k]["parlay_id"])
    legs = [c for c in json.loads(B["stored"])["calls"] if c["call_type"] == "parlay_leg"]
    check("the page marks Miami's and Dallas's PLAYs (holds that end in no bet), Denver's (PASS on the page) and "
          "Tampa's value shadow; not Buffalo's PLAY nor Newark's shadow, which it repeats",
          singles == ["Dallas|straight|HOME|", "Denver|straight|HOME|", "Miami|straight|HOME|",
                      "Tampa|value_shadow|AWAY|"], str(singles))
    check("every ticket leg is marked (R5: the page carries no tickets)",
          legs and all(c.get("not_executed") for c in legs), f"{len(legs)} leg(s)")
    check("each mark names the page: family NFL, the start, the run id, the as_of, the file",
          all(m["closing"] == {"family": "NFL", "start": STARTZ, "run_id": RUN, "as_of": "2026-10-19T16:25:00Z",
                               "file": CN} for m in B["marks"]), str(B["marks"][0]["closing"]))
    words = {k.split("|")[0]: marks[k]["text"] for k in singles}
    check("the page's own words: Denver and Tampa PASS; Miami and Dallas 'PLAY <team> 0.5u — not a bet under ...'",
          words["Denver"] == words["Tampa"] == "PASS"
          and all(words[t].startswith(f"PLAY {t} 0.5u — not a bet under ") and words[t].endswith(" (#431 R6)")
                  for t in ("Miami", "Dallas")), json.dumps(words, ensure_ascii=False))
    n = len(B["marks"])
    check("logged: the load note counts the marks (all new)",
          f" · {n} claim(s) marked NOT EXECUTED (the page did not repeat them; {n} new, 0 cleared by a later page)"
          in (B["logNote"] or "") and did["closings"]["marked"] == n, (B["logNote"] or "")[-260:])
    lines = B["notExecuted"] or [""]
    shown = all(any(f"{m['game']} · {m['side']} · {m['engine']} {m['call_type']} · claim " in ln
                    and f" · NOT EXECUTED · closing NFL {STARTZ}: {m['text']} · {m['result']}" in ln for ln in lines)
                for m in B["marks"])
    check("shown: the ledger lists every marked claim beside the page's words (#notExecuted)",
          lines[0].startswith(f"{n} claim(s) not executed") and len(lines) == n + 1 and shown, lines[0][:90])
    print("    " + "\n    ".join(lines[:6]) + ("\n    ..." if len(lines) > 6 else ""))
    q = pages.open("head", AT_SLATE)
    q.evaluate(LOAD, slate)
    q.clock.set_fixed_time(AT_CLOSE)
    q.evaluate(LOAD, [doc(CN, D["closing"])])
    # each open row by its cells (a locked row carries no control, so no data-id): the calls it can be, by game,
    # side and call type; a row whose candidates are all locked (marked, or a leg of a ticket with a marked leg) or
    # all free
    o = q.evaluate("""()=>{ renderLedger(); const L=loadLedger(), out=[];
      const side=c=>c.pick==="HOME"?c.home:c.pick==="AWAY"?c.away:c.pick;
      const lock=c=>!!c.not_executed||(!!c.parlay_id&&L.calls.some(x=>x.parlay_id===c.parlay_id&&x.not_executed));
      for(const tr of document.querySelectorAll("#openList tbody tr")){ const td=[...tr.children].map(x=>x.textContent);
        const cs=L.calls.filter(c=>c.status==="open"&&c.game===td[3]&&side(c)===td[4]&&c.call_type===td[6]);
        out.push({home:cs.length?cs[0].home:null,type:td[6],n:cs.length,locked:cs.filter(lock).length,
          marked:cs.filter(c=>c.not_executed).length,flag:tr.innerHTML.includes('<b class="caution">NOT EXECUTED</b>'),
          exec:!!tr.querySelector(".execBtn"),fill:!!tr.querySelector(".fillBtn")}); }
      return out; }""")
    locked = [v for v in o if v["n"] and v["locked"] == v["n"]]
    free = [v for v in o if v["n"] and not v["locked"]]
    buf = [v for v in free if v["home"] == "Buffalo" and v["type"] == "straight"]
    check("the day's order (page before results): the open table flags each marked call NOT EXECUTED; no Execute now, "
          "no Record fill on a marked call or any leg of its ticket; Buffalo's PLAY keeps both",
          len(locked) + len(free) == len(o) and len(locked) == len(B["marks"])
          and all(v["flag"] == bool(v["marked"]) and not v["exec"] and not v["fill"] for v in locked)
          and len(buf) == 1 and buf[0]["exec"] and buf[0]["fill"] and not buf[0]["flag"],
          f"{len(o)} open row(s): {len(locked)} locked · {len(free)} free")

    print("(c) out of the P&L, the Sizing gate and the n/30 counts; nothing deleted (R10)")
    single = [m for m in B["marks"] if not m["parlay_id"] and m["result"]]
    tickets = {m["parlay_id"] for m in B["marks"] if m["parlay_id"]}
    real = [m for m in single if m["call_type"] not in ("quarantine_shadow", "value_shadow")]
    check("settledBets: the marked positions and tickets leave it; lastNotExec counts them",
          A["bets"]["n"] - B["bets"]["n"] == len(single) + len(tickets)
          and B["ne"] == {"positions": len(single), "tickets": len(tickets), "voidLeg": 0},
          f"bets {A['bets']['n']} → {B['bets']['n']} · lastNotExec {B['ne']}")
    gate = [ln for ln in B["pnl"].split("\n") if ln.startswith("Sizing gate:")]
    me = A["bets"]["model_edge"] - len(real) - len(tickets)
    check("the Sizing gate counts only what stays", B["bets"]["model_edge"] == me
          and gate == [f"Sizing gate: model_edge {me}/50 · venue_edge 0/50 graded before any sizing proposal"],
          f"{A['bets']['model_edge']} → {gate}")
    ca, cb = A["ledgerSummary"]["counts"], B["ledgerSummary"]["counts"]
    check("the n/30 counts: Tampa's marked value shadow leaves value_shadow_graded; the other three hold",
          ca["value_shadow_graded"] - cb["value_shadow_graded"] == 1
          and all(ca[x] == cb[x] for x in ("postseason_graded", "kalshi_only_graded", "intl_graded")),
          f"{ca} → {cb}")
    ln = [x for x in B["pnl"].split("\n") if x.startswith("Not executed (addendum 40 item 2, #431): ")]
    check("the P&L block's line and the totals' caution say what left",
          ln == [f"Not executed (addendum 40 item 2, #431): {n} claim(s) the closing page did not repeat ({len(single)} "
                 f"position(s), {len(tickets)} ticket(s) settled) — out of the P&L, the sizing gate and the graded n/30 "
                 "counts; marked, never deleted."] and (B["notExecLine"] or "").startswith("⚠ Not executed"), str(ln))
    sa, sb = json.loads(A["stored"]), json.loads(B["stored"])
    moved = sorted(k for k in set(sa["meta"]) | set(sb["meta"]) if sa["meta"].get(k) != sb["meta"].get(k))
    check("nothing deleted: the same calls in the same order, every stored field equal once not_executed is stripped",
          A["calls"] == B["calls"] and stripped(A["stored"]) == stripped(B["stored"])
          and set(moved) <= {"closings", "auto_claims"}, f"{A['calls']} → {B['calls']} calls · meta moved {moved}")
    check("each marked claim keeps its own result and status (graded)",
          all(m["status"] == "graded" and m["result"] for m in B["marks"]), "")
    intake(q, results, AT_RESULTS)
    C = q.evaluate(SNAP)
    check("the day's order (page, then results) ends with the same marks and the same P&L block",
          sorted(m["key"] for m in C["marks"]) == sorted(marks) and C["pnl"] == B["pnl"]
          and C["ledgerSummary"] == B["ledgerSummary"], "")

    print(f"(d) no closing file: the base page's ({base}) behaviour")
    side = {}
    for label in ("base", "head"):
        p = pages.open(label, AT_SLATE)
        p.evaluate(LOAD, slate)
        one = p.evaluate(SNAP)
        p.evaluate(LOAD, slate)
        two = p.evaluate(SNAP)
        intake(p, results, AT_RESULTS)
        side[label] = (one, two, p.evaluate(SNAP))
    b, h = side["base"], side["head"]
    check("the Desk summary, the rows (R17's kLegs set aside) and the Desk calls of the load", all(
        b[i]["summary"] == h[i]["summary"] and json.loads(b[i]["rows"]) == no_legs(h[i]["rows"])
        and b[i]["desk"] == h[i]["desk"] for i in (0, 1)), h[0]["summary"][:120])
    check("the load notes (first load, reload) and the intake note", all(b[i]["logNote"] == h[i]["logNote"]
                                                                          for i in (0, 1))
          and b[2]["ledgerNote"] == h[2]["ledgerNote"], h[1]["logNote"][:120])
    ne0 = ("Not executed (addendum 40 item 2, #431): 0 claim(s) the closing page did not repeat (0 position(s), 0 "
           "ticket(s) settled) — out of the P&L, the sizing gate and the graded n/30 counts; marked, never deleted.")
    cc0 = ("Closing CLV (close − entry; + = beat the close) (addendum 146 item 1(iv) R17, #431): 0 position(s),"
           " 0 fill(s) · sum none · mean none per position")
    hp = h[2]["pnl"].split("\n")
    ci = hp.index(cc0) if cc0 in hp else -1
    hp = hp[:ci] + hp[ci + 2:] if ci >= 0 and hp[ci + 1:ci + 2] == [""] else hp
    check("the P&L block, its Not executed line (reading 0) and its Closing CLV line (R17, none) set aside, and"
          " ledgerSummary", ci >= 0 and ne0 in hp and "\n".join(x for x in hp if x != ne0) == b[2]["pnl"]
          and b[2]["ledgerSummary"] == h[2]["ledgerSummary"] and b[2]["bets"] == h[2]["bets"], "")
    aside = ("id",) + R16_FIELDS
    same = all(no_id(b[i]["stored"], aside) == no_id(h[i]["stored"], aside) for i in (0, 1, 2)) and all(
        all(k in c for k in R16_FIELDS) for c in json.loads(h[2]["stored"])["calls"])
    ids = [(x["id"], y["id"], y["pick"]) for x, y in zip(json.loads(b[2]["stored"])["calls"],
                                                       json.loads(h[2]["stored"])["calls"])]
    check("the stored ledger, the call id and R16's order fields (on every call) set aside; each id differs only by"
          " the pick R4 adds to callKey",
          same and ids and all(old == r4_id(c, None) and new == r4_id(c, pick)
                               for (old, new, pick), c in zip(ids, json.loads(h[2]["stored"])["calls"])),
          f"{len(ids)} calls · e.g. {ids[0][0]!r} → {ids[0][1]!r}")

    print("(e) the laptop control, against a routed fake GitHub API")
    gh = FakeGitHub()
    days = ["2026-10-18", "2026-10-19"]
    gh.routes.update({
        "laptop/latest": (200, [{"type": "file", "name": SN}, {"type": "file", "name": PN},
                                {"type": "file", "name": COVN},
                                {"type": "file", "name": "closing_NFL.json"}, {"type": "file", "name": "RESULTS.md"},
                                {"type": "dir", "name": "old"}]),
        f"laptop/{days[1]}": (200, [{"type": "file", "name": CN}, {"type": "file", "name": CM},
                                    {"type": "file", "name": SN}, {"type": "file", "name": "closing_notes.txt"}]),
        f"laptop/latest/{SN}": (200, json.dumps(D["slate"])), f"laptop/latest/{PN}": (200, json.dumps(D["parlays"])),
        "laptop/latest/coverage%20%231.json": (200, json.dumps(COV)),
        "laptop/latest/closing_NFL.json": (200, json.dumps(D["closing"])),
        f"laptop/{days[1]}/{CN}": (200, json.dumps(D["closing"])),
        f"laptop/{days[1]}/{CM}": (500, json.dumps(D["mlb_closing"]))})   # a real page: loaded, it would show
    p = pages.open("head", AT_CLOSE, gh)
    p.fill("#mirrorToken", "github_pat_TEST")
    p.click("#mirrorLaptopBtn")
    p.wait_for_function("document.getElementById('mirrorNote').textContent.startsWith('Loaded')")
    note = p.inner_text("#mirrorNote")
    print("    " + note)
    lists = [(u[len(API):], acc, au) for u, acc, au in gh.seen if acc == LIST]
    raws = sorted((u[len(API):], au) for u, acc, au in gh.seen if acc == RAW)
    check("it lists laptop/latest, then laptop/<yesterday UTC> and laptop/<today UTC>, with the token as Bearer",
          lists == [("laptop/latest", LIST, AUTH)] + [(f"laptop/{d}", LIST, AUTH) for d in days], str(lists))
    want = sorted([(f"laptop/latest/{SN}", AUTH), (f"laptop/latest/{PN}", AUTH),
                   ("laptop/latest/coverage%20%231.json", AUTH), (f"laptop/{days[1]}/{CN}", AUTH),
                   (f"laptop/{days[1]}/{CM}", AUTH)])
    check("it fetches exactly latest's JSON files and the day folders' closing_*.json, raw, each segment encoded (the "
          "'#' of 'coverage #1.json' as %23, which the browser never does by itself); latest/closing_NFL.json, "
          "RESULTS.md, the folder and the day's slate copy never",
          raws == want and len(gh.seen) == len(lists) + len(want), str([u for u, _ in raws]))
    sports = p.evaluate("[...new Set(rows.map(r=>r.sport))]")
    check("the 404 day folder is named, not fatal; the file that answered 500 (a real MLB page) is named and never "
          "loaded: no MLB row on the Desk",
          note.startswith(f"Loaded 4 file(s) from anthonyevans29/Sports-Predictor-exports laptop: 1 closing file(s) of "
                          f"{days[0]}, {days[1]} UTC · 3 newest of the other kinds · laptop/{days[0]}: no folder yet"
                          f" · 1 not fetched, not loaded: laptop/{days[1]}/{CM} (GitHub 500)")
          and sports == ["NFL"] and p.evaluate("rows.every(r=>r.closing)"), f"Desk sports {sports}")
    # an empty ledger: the morning's tickets (latest's desk_parlays.json, as_of 12:00Z) are claimed in this load and
    # the page marks them (R5); the games no ticket touches hold no claim from before the page (R14's line, ⚠: the
    # slate in this load called them)
    touched = {leg["home"] for t in D["parlays"]["tickets"] for leg in t["legs"]}
    check("one load: the closing rows stand over the slate's; the morning's tickets are claimed and marked; R14's line "
          "names the games that hold no claim from before the page",
          DEDUPE in note and f" · {len(legs)} claim(s) marked NOT EXECUTED ({len(legs)} new, 0 cleared by a later page)"
          in note and note.endswith(f" · ⚠ {6 - len(touched)} of 6{R14}") and p.evaluate("rows.length") == 6,
          f"{len(legs)} leg(s) on {sorted(touched)}")
    q = pages.open("head", AT_SLATE)
    q.evaluate(LOAD, slate)
    exported = q.evaluate("JSON.stringify(loadLedger(),null,1)")        # the Export ledger button's file
    gh.seen.clear()
    p = pages.open("head", AT_CLOSE, gh)
    p.evaluate("t=>importLedgerDoc(JSON.parse(t))", exported)
    p.fill("#mirrorToken", "github_pat_TEST")
    p.click("#mirrorLaptopBtn")
    p.wait_for_function("document.getElementById('mirrorNote').textContent.startsWith('Loaded')")
    note = p.inner_text("#mirrorNote")
    E = p.evaluate(SNAP)
    check("import the ledger, then load: the page marks the claims it did not repeat, the same as (b); no R14 line",
          f" · {n} claim(s) marked NOT EXECUTED ({n} new, 0 cleared by a later page)" in note and R14 not in note
          and sorted(m["key"] for m in E["marks"]) == sorted(marks), note[len(note) - 150:])
    host = [pages.open(x, AT_CLOSE).evaluate("loadLatestFromHost.toString()") for x in ("base", "head")]
    check("the host control (loadLatestFromHost) is the base page's, unchanged", host[0] == host[1], "")

    print("(f) a 401 aborts with the message")
    before = (p.evaluate("localStorage.getItem(LEDGER_KEY)"), p.evaluate("JSON.stringify(rows)"))
    gh.seen.clear()
    gh.routes["laptop/latest"] = (401, {})
    p.click("#mirrorLaptopBtn")
    p.wait_for_function("document.getElementById('mirrorNote').textContent.includes('401')")
    check("'GitHub 401 — token rejected / no read access'; nothing fetched past the listing; nothing loaded",
          p.inner_text("#mirrorNote") == "GitHub 401 — token rejected / no read access"
          and [u[len(API):] for u, _, _ in gh.seen] == ["laptop/latest"]
          and (p.evaluate("localStorage.getItem(LEDGER_KEY)"), p.evaluate("JSON.stringify(rows)")) == before,
          p.inner_text("#mirrorNote"))


if __name__ == "__main__":
    raise SystemExit(main())
