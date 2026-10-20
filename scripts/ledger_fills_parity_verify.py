"""
Parity receipt for src/walters/ledger_fills.py (the K-track receipt's port of
the Cockpit's fill classification + executed-position CLV, #87, 2026-10-06).

Imports the synthetic Kalshi CSV of scripts/cockpit_fills_verify.py through the
Cockpit's own "Import Kalshi CSV" input, reads the stored ledger back, then runs
the COCKPIT's classifyFills / executedPositions in Chromium and the Python port
on the SAME ledger, field by field: book, call_id, backed_role, backed,
no_on_role, fee class; per position qty, entry CLV and fee-adj edge. One call is
graded with a close so the CLV path is exercised. Any difference is a FAIL.
#431 (ARCHITECT 2026-10-20, addendum 145 item 3(b); verify_ports #4): claims a
closing page did not repeat, marked by the Cockpit's own markClosings from stored
pages (never hand-set): R7's unmarked preference (a straight pair in both orders,
a ladder pair under a composite NO, kickoffs drifting within R2's hour) and R10
(a marked claim keeps its fill and its executed position), Cockpit and port alike.
#431 R16/R17 (ARCHITECT 2026-10-20, addendum 146 item 1(iv); addendum 148 item 1):
the Cockpit's closingPositions against ledger_fills.closing_positions on the same
stored ledger, every field of every position (its pages stored through the page's
own putPage: a page with legs, YES and NO fills, an unpriced ticker, a slate-only
order, a page stored without legs, a ladder's NO on HOME, a {why} order, two
covering pages), and the K-track receipt's line carries the Cockpit's cents.
Writes nothing to the repo; no DB. Needs Playwright + Chromium.
Run:  python3 scripts/ledger_fills_parity_verify.py
"""
import functools
import http.server
import os
import re
import sys
import tempfile
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cockpit_fills_verify as F  # noqa: E402  (fixture: LEDGER, FILLS, HDR)
from src.walters import k_receipt as K  # noqa: E402
from src.walters import ledger_fills as P  # noqa: E402

CHECKS = []


def _fill(fid, ticker, side, title, qty=2, entry=0.5):
    return {"id": fid, "ticker": ticker, "side": side, "qty": qty, "entry": entry, "exit": 1.0, "staked": qty * entry,
            "fees": 0.04, "open_fee": 0.04, "close_fee": 0, "pnl_pre": 1.0, "pnl_net": 0.96, "title": title}


EXTRA = {"calls": [
    F.call("dh1", "MLB", "Boston Red Sox", "New York Yankees", "HOME", kick="2026-09-27T17:05:00"),   # 13:05 ET
    F.call("dh2", "MLB", "Boston Red Sox", "New York Yankees", "HOME", kick="2026-09-27T23:05:00"),   # 19:05 ET
    F.call("epl", "SOCCER", "Arsenal", "Chelsea", "AWAY", kick="2026-09-27T14:00:00"),
    F.call("lad", "SOCCER", "Everton", "Fulham", "AWAY", ct="ladder", kick="2026-09-27T14:00:00"),
    F.call("tbh", "NFL", "Tampa Bay Buccaneers", "Green Bay Packers", "HOME", kick="2026-10-04T17:00:00"),
    F.call("ng1", "MLB", "Boston Red Sox", "New York Yankees", "AWAY", kick="2026-09-29T17:05:00"),   # 13:05 ET
    F.call("ng2", "MLB", "Boston Red Sox", "New York Yankees", "HOME", kick="2026-09-29T19:45:00"),   # 15:45 ET
    F.call("nyj", "NFL", "Los Angeles Chargers", "New York Jets", "AWAY", kick="2026-10-11T17:00:00"),
    F.call("rev", "MLB", "New York Yankees", "Boston Red Sox", "HOME", kick="2026-10-20T17:05:00"),  # reversed
    F.call("nyj2", "NFL", "Seattle Seahawks", "New York Jets", "AWAY", kick="2026-10-25T17:00:00"),
    F.call("jax", "NFL", "Jacksonville Jaguars", "Tennessee Titans", "HOME", kick="2026-11-01T17:00:00"),
    F.call("unc", "NCAA", "North Carolina Tar Heels", "Georgia Bulldogs", "HOME", kick="2026-11-07T19:00:00"),
    F.call("nyr", "NFL", "New York Giants", "New York Jets", "HOME", kick="2026-11-08T17:00:00"),   # Giants home
    F.call("lg1", "SOCCER", "Everton", "Fulham", "AWAY", ct="ladder", kick="2026-11-14T14:00:00"),
    F.call("lg2", "SOCCER", "Everton", "Fulham", "AWAY", ct="ladder", kick="2026-11-14T14:00:00"),  # tied ladders
    F.call("intl", "INTL", "Scotland", "England", "AWAY", kick="2026-10-10T18:45:00"),  # production INTL call
    F.call("unl", "UNL", "France", "Germany", "HOME", kick="2026-10-13T18:45:00"),
], "fills": [
    _fill("x-dh2", "KXMLBGAME-26SEP271905NYYBOS-BOS", "yes", "Boston wins — New York Y"),  # game 2, not game 1
    _fill("x-dh1", "KXMLBGAME-26SEP271305NYYBOS-BOS", "yes", "Boston wins — New York Y"),
    _fill("x-3no", "KXEPLGAME-26SEP27CHEARS-ARS", "no", "Arsenal wins — Chelsea"),          # NO on ARS: composite
    _fill("x-lad", "KXEPLGAME-26SEP27FULEVE-EVE", "no", "Everton wins — Fulham"),          # the ladder's NO HOME
    _fill("x-gb", "KXNFLGAME-26OCT04GBTB-GB", "yes", "Green Bay wins — Tampa Bay"),        # side != pick (HOME)
    _fill("x-ng", "KXMLBGAME-26SEP291305NYYBOS-BOS", "yes", "Boston wins — New York Y"),   # game 1 disagrees
    _fill("x-nyg", "KXNFLGAME-26OCT11NYGLAR-NYG", "yes", "New York G wins — Los Angeles R"),  # not Jets–Chargers
    _fill("x-rev", "KXMLBGAME-26OCT201305NYYBOS-BOS", "yes", "Boston wins — New York Yankees"),  # BOS home
    _fill("x-tie", "KXEPLGAME-26SEP27CHEARS-TIE", "no", "Tie — Chelsea vs Arsenal"),               # NO TIE: composite
    _fill("x-nygs", "KXNFLGAME-26OCT25NYGSEA-NYG", "yes", "New York G wins — Seattle"),           # weak NYG unconfirmed
    _fill("x-jax", "KXNFLGAME-26NOV01TENJAX-JAX", "yes", "Tennessee vs Jacksonville Winner?"),    # legacy title
    _fill("x-unc", "KXNCAAFGAME-26NOV07UGAUNC-UNC", "yes", "Georgia vs North Carolina Winner?"),  # 2 non-prefix codes
    _fill("x-nyj", "KXNFLGAME-26NOV08NYGNYJ-NYJ", "yes", "New York Jets wins — New York Giants"),  # NYJ home: reversed
    _fill("x-lg", "KXEPLGAME-26NOV14FULEVE-EVE", "no", "Everton wins — Fulham"),           # two tied ladder calls
    _fill("x-intl", "KXUEFANLGAME-26OCT10ENGSCO-ENG", "yes", "England wins — Scotland"),  # UEFANL -> INTL call
    _fill("x-unl", "KXUEFANLGAME-26OCT13GERFRA-FRA", "yes", "France wins — Germany"),     # UEFANL -> UNL call
]}
FIELDS = ("book", "call_id", "backed_role", "backed", "no_on_role", "fee_class_open", "fee_class_close",
          "ambiguous_calls")


# #431 R7/R10 (ARCHITECT 2026-10-20, addendum 145 item 3(b); verify_ports #4, read_ports.md). Each game has its closing
# page, stored as putPage keeps it in L.meta.closings; the page calls the venue straight (repeated) and not the model's
# claim, so the Cockpit's own markClosings marks the claim. A mark is never hand-set: saveLedger re-derives every mark
# from the stored pages (R8), so a fixture mark without its page is not a state the Cockpit keeps.
def _claim(c, at):
    """A call claimed at `at` (claim_at, which R3 reads against the page's as_of)."""
    return dict(c, log_date=at[:10], claim_at=at, captured_at=at)


def _graded(c, home_fair):
    return dict(c, status="graded", result="win", graded_date=c["kickoff"][:10],
                close_ref={"version": "p0-3 v2", "q_close": home_fair,
                           "fair": {"HOME": home_fair, "AWAY": round(1 - home_fair, 4)}})


def _page(fam, c, start, as_of, calls, text="PASS"):
    """The stored page for call c's game (closingPages' record shape; closing.py's run id and file name)."""
    run = re.sub(r"[-:]", "", as_of) + "-" + {"MLB": "mlb", "NFL": "nfl", "SOCCER": "soccer"}[fam] + "-closing"
    name = f"closing_{fam}_{start[:13]}{start[14:16]}Z.json"
    g = {"sport": c["sport"], "home": c["home"], "away": c["away"], "kickoff": start, "calls": calls, "text": text,
         "run_id": run, "as_of": as_of, "file": name}
    return {"family": fam, "start": start, "run_id": run, "as_of": as_of, "file": name,
            "games": {"|".join((c["sport"], c["home"], c["away"], start)): g}}


_BOS = ("MLB", "Boston Red Sox", "New York Yankees", "HOME")
_VEN = {"engine": "venue_edge", "tier": "shadow", "units": 0.25}
NE = {"calls": [
    # a straight pair, the marked claim first (the order that once handed it the fill); both graded with a close
    _graded(_claim(F.call("pa-m", *_BOS, kick="2026-10-01T17:05:00"), "2026-10-01T12:00:00.000Z"), 0.6),
    _graded(_claim(F.call("pa-u", *_BOS, **_VEN, kick="2026-10-01T17:05:00"), "2026-10-01T12:00:00.000Z"), 0.6),
    # the same pair, the unmarked call first
    _claim(F.call("pb-u", *_BOS, **_VEN, kick="2026-10-03T17:05:00"), "2026-10-03T12:00:00.000Z"),
    _claim(F.call("pb-m", *_BOS, kick="2026-10-03T17:05:00"), "2026-10-03T12:00:00.000Z"),
    # R2's hour: the marked claim at the ticker's start, the unmarked call 5 minutes later (verify_ports #1)
    _claim(F.call("dr-m", *_BOS, kick="2026-10-05T17:05:00"), "2026-10-05T12:00:00.000Z"),
    _claim(F.call("dr-u", *_BOS, **_VEN, kick="2026-10-05T17:10:00"), "2026-10-05T12:00:00.000Z"),
    # a ladder pair: the morning claim (marked) and one claimed after the page (R3: not marked), kickoff 30 min on
    _claim(F.call("ld-m", "SOCCER", "Everton", "Fulham", "AWAY", ct="ladder", kick="2026-11-21T15:00:00"),
           "2026-11-21T09:00:00.000Z"),
    _claim(F.call("ld-u", "SOCCER", "Everton", "Fulham", "AWAY", ct="ladder", kick="2026-11-21T15:30:00"),
           "2026-11-21T14:00:00.000Z"),
    # R10: a marked claim alone on its game and side, graded with a close, its own Kalshi fill
    _graded(_claim(F.call("r10", "NFL", "Tampa Bay Buccaneers", "Green Bay Packers", "HOME",
                          kick="2026-10-18T17:00:00"), "2026-10-18T12:00:00.000Z"), 0.62),
], "fills": [
    _fill("x-pa", "KXMLBGAME-26OCT011305NYYBOS-BOS", "yes", "Boston wins — New York Y"),
    _fill("x-pb", "KXMLBGAME-26OCT031305NYYBOS-BOS", "yes", "Boston wins — New York Y"),
    _fill("x-dr", "KXMLBGAME-26OCT051305NYYBOS-BOS", "yes", "Boston wins — New York Y"),   # 13:05 ET = 17:05Z
    _fill("x-ld", "KXEPLGAME-26NOV21FULEVE-EVE", "no", "Everton wins — Fulham"),          # NO on HOME: an AWAY ladder
    _fill("x-r10", "KXNFLGAME-26OCT18GBTB-TB", "yes", "Tampa Bay wins — Green Bay"),
]}
_VENUE_HOME = ["venue_edge|straight|HOME"]
NE["pages"] = [
    _page("MLB", NE["calls"][0], "2026-10-01T17:05:00Z", "2026-10-01T15:05:00Z", _VENUE_HOME),
    _page("MLB", NE["calls"][2], "2026-10-03T17:05:00Z", "2026-10-03T15:05:00Z", _VENUE_HOME),
    _page("MLB", NE["calls"][4], "2026-10-05T17:05:00Z", "2026-10-05T15:05:00Z", _VENUE_HOME),
    _page("SOCCER", NE["calls"][6], "2026-11-21T15:00:00Z", "2026-11-21T13:00:00Z", []),
    _page("NFL", NE["calls"][8], "2026-10-18T17:00:00Z", "2026-10-18T15:00:00Z", []),
]
NE_MARKED = ["dr-m", "ld-m", "pa-m", "pb-m", "r10"]


# #431 R16/R17 (ARCHITECT 2026-10-20, addendum 146 item 1(iv), verbatim: "R16 the ledger stores the page's ORDERED size
# and limit beside the FILLED size and entry; R17 each position carries entry minus the closing ask on its pick (true
# CLV, in cents)"; the sign CORRECTED by addendum 148 item 1(b): "ask minus entry, + = bought below the close"). Each
# game's stored page carries the closing row's Kalshi legs and the page's orders by call key as closingPages writes them
# (legs {HOME|AWAY|DRAW: {ticker, bid, ask}}; orders {"<engine>|<call_type>|<pick>": {ticker, side, limit, contracts,
# unit} | {why}}) and goes in through the page's own putPage; a call's exec_order is the slate's order, as stampTiming
# keeps it. Kansas City at home to Buffalo on five dates (KC and BUF the codes the fills above already fit), a ladder.
_KC = ("NFL", "Kansas City Chiefs", "Buffalo Bills", "HOME")
_U = "1u = 10 contracts (SP_UNIT_USD unset)"


def _tk(day, side="KC", t=""):
    """A KXNFLGAME ticker of a Buffalo @ Kansas City date ("26DEC06"); t a timed ticker's ET HHMM."""
    return f"KXNFLGAME-{day}{t}BUFKC-{side}"


def _ord(ticker, side, limit, contracts):
    return {"ticker": ticker, "side": side, "limit": limit, "contracts": contracts, "unit": _U}


def _kc_legs(day, bid, ask):
    """The two legs as the export writes a two-way game's: AWAY the complement of HOME."""
    return {"HOME": {"ticker": _tk(day), "bid": bid, "ask": ask},
            "AWAY": {"ticker": _tk(day, "BUF"), "bid": round(1 - ask, 2), "ask": round(1 - bid, 2)}}


def _quoted(pg, legs=None, orders=None):
    """The page `pg` (_page) whose one game carries legs and orders, as closingPages stores them."""
    (g,) = pg["games"].values()
    g.update({"legs": legs, "orders": orders or {}})
    return pg


_EVE = "KXEPLGAME-26DEC05FULEVE-EVE"                      # the Everton (home) leg: an AWAY ladder buys NO on it
R17C = {"calls": [
    dict(F.call("r17a", *_KC, kick="2026-12-06T18:00:00"), exec_order=_ord(_tk("26DEC06"), "YES", 0.52, 8)),
    dict(F.call("r17b", *_KC, kick="2026-12-13T18:00:00"), exec_order=_ord(_tk("26DEC13"), "YES", 0.53, 5)),
    dict(F.call("r17c", *_KC, kick="2026-12-20T18:00:00"), exec_order=_ord(_tk("26DEC20"), "YES", 0.50, 12)),
    dict(F.call("r17d", *_KC, kick="2026-12-27T18:00:00"), exec_order=_ord(_tk("26DEC27"), "YES", 0.55, 5)),
    dict(F.call("r17e", "SOCCER", "Everton", "Fulham", "AWAY", ct="ladder", units=0.5, kick="2026-12-05T15:00:00"),
         exec_order=None),
    dict(F.call("r17f", *_KC, kick="2027-01-03T18:00:00"), exec_order=None),
    dict(F.call("r17g", *_KC, kick="2027-01-10T18:00:00"), exec_order=_ord(_tk("27JAN10"), "YES", 0.50, 5)),
], "fills": [
    _fill("x-17a", _tk("26DEC06"), "yes", "Kansas City wins — Buffalo", 4, 0.55),       # YES on KC at 55c, ask 53c
    _fill("x-17a2", _tk("26DEC06", "BUF"), "no", "Buffalo wins — Kansas City", 6, 0.50),  # NO on BUF: 1 − its 47c bid
    _fill("x-17b", _tk("26DEC13"), "yes", "Kansas City wins — Buffalo", 3, 0.50),
    _fill("x-17b2", _tk("26DEC13", t="1300"), "yes", "Kansas City wins — Buffalo", 2, 0.51),  # a ticker not on the page
    _fill("x-17c", _tk("26DEC20"), "yes", "Kansas City wins — Buffalo", 5, 0.52),       # no stored page: the slate's
    _fill("x-17d", _tk("26DEC27"), "yes", "Kansas City wins — Buffalo", 5, 0.55),       # a page stored without legs
    _fill("x-17e", _EVE, "no", "Everton wins — Fulham", 5, 0.58),                         # the ladder's NO on HOME
    _fill("x-17f", _tk("27JAN03"), "yes", "Kansas City wins — Buffalo", 5, 0.50),       # the page wrote no order
    _fill("x-17g", _tk("27JAN10"), "yes", "Kansas City wins — Buffalo", 5, 0.50),       # two covering pages
]}
_C = R17C["calls"]
_PLAY = ["model_edge|straight|HOME"]
R17C["pages"] = [
    _quoted(_page("NFL", _C[0], "2026-12-06T18:00:00Z", "2026-12-06T17:25:00Z", _PLAY),
            _kc_legs("26DEC06", 0.52, 0.53), {"model_edge|straight|HOME": _ord(_tk("26DEC06"), "YES", 0.53, 8)}),
    _quoted(_page("NFL", _C[1], "2026-12-13T18:00:00Z", "2026-12-13T17:25:00Z", _PLAY),
            _kc_legs("26DEC13", 0.52, 0.53), {"model_edge|straight|HOME": _ord(_tk("26DEC13"), "YES", 0.53, 5)}),
    _page("NFL", _C[3], "2026-12-27T18:00:00Z", "2026-12-27T17:25:00Z", _PLAY),   # no legs, no orders
    _quoted(_page("SOCCER", _C[4], "2026-12-05T15:00:00Z", "2026-12-05T14:25:00Z", ["model_edge|ladder|AWAY"]),
            {"HOME": {"ticker": _EVE, "bid": 0.40, "ask": 0.41}}, {"model_edge|ladder|AWAY": _ord(_EVE, "NO", 0.60, 5)}),
    _quoted(_page("NFL", _C[5], "2027-01-03T18:00:00Z", "2027-01-03T17:25:00Z", _PLAY),
            _kc_legs("27JAN03", 0.52, 0.53), {"model_edge|straight|HOME": {"why": "no Kalshi ticker on file"}}),
    _quoted(_page("NFL", _C[6], "2027-01-10T18:00:00Z", "2027-01-10T17:25:00Z", _PLAY),
            _kc_legs("27JAN10", 0.52, 0.53)),
    _quoted(_page("NFL", _C[6], "2027-01-10T18:30:00Z", "2027-01-10T17:55:00Z", _PLAY),   # within the hour: two
            _kc_legs("27JAN10", 0.50, 0.51)),
]
R17_FIELDS = ("id", "status", "cover", "page", "legacy", "ordered", "filled", "asks", "quote", "clv_c", "above_limit_c",
              "above_fills", "over_size", "partial")


def check(label, ok, detail=""):
    CHECKS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


def main():
    tmp = tempfile.mkdtemp(prefix="ledger-parity-")
    csv_path = os.path.join(tmp, "Kalshi-Fills.csv")
    with open(csv_path, "w") as f:
        f.write(F.HDR + "\n")
        for t, sd, q, en, ex, of, cf, net, pre, title in F.FILLS:
            f.write(f'sub-1,trade,{q:.2f},{t},{sd},{en:.8f},{ex:.8f},{of:.8f},{cf:.8f},{pre:.8f},{net:.8f},'
                    f'2026-09-28T18:00:00-05:00,2026-09-27T07:00:00-05:00,predictions,2026-09-01,"{title}"\n')

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0),
                                          functools.partial(Quiet, directory=os.path.join(ROOT, "tools")))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        browser = pw.chromium.launch(**({"executable_path": exe} if os.path.exists(exe) else {}))
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{srv.server_address[1]}/cockpit.html")
        page.evaluate("l => localStorage.setItem('bd_ledger_v1', JSON.stringify(l))", F.LEDGER)
        page.click("#tabLedger")
        page.set_input_files("#kalshiCsvFile", csv_path)
        page.wait_for_function("document.getElementById('ledgerNote').textContent.includes('Kalshi CSV')")
        # fill matcher lane (2026-10-06): an MLB doubleheader told apart by the ticker's ET start time, and a
        # three-way NO (composite, two outcomes) that must never match a single-side straight
        page.evaluate("""(x) => { const L = loadLedger(); L.calls.push(...x.calls); L.fills.push(...x.fills);
            localStorage.setItem('bd_ledger_v1', JSON.stringify(L)); }""", EXTRA)
        # grade c1 (KC home, picked HOME) with a close, so executedPositions has positions
        page.evaluate("""() => { const L = loadLedger();
            const c = L.calls.find(x => x.id === 'c1');
            Object.assign(c, {status: 'graded', result: 'win', graded_date: '2026-09-28',
              close_ref: {version: 'p0-3 v2', q_close: 0.62, fair: {HOME: 0.62, AWAY: 0.38}}});
            localStorage.setItem('bd_ledger_v1', JSON.stringify(L)); }""")
        # #431 R7/R10: the pages go in through the page's own putPage and the marks come from its own markClosings
        # (saveLedger's step; enforceLedger is left out, as above, so the tied ladders lg1/lg2 stay two). esc 12 at its
        # proposed value (csvFillExempt true) lifts the mark of a claim a Kalshi CSV fill lands on, so R10's marked
        # claim with its own fill is the ledger the alternative (false) keeps: that one is stored and compared, the
        # proposed value's marks read on a copy (switches set as tests/test_cockpit_closing_marks.py's T_rules does)
        ne = page.evaluate("""(x) => { const L = loadLedger(); L.calls.push(...x.calls); L.fills.push(...x.fills);
            for (const p of x.pages) putPage(L, p);
            const marked = M => M.calls.filter(c => c.not_executed).map(c => c.id).sort();
            const live = JSON.parse(JSON.stringify(L)), s1 = markClosings(live), DEF = {...CLOSING_MARK_RULES};
            let s2, fixed;
            try { CLOSING_MARK_RULES.csvFillExempt = false; s2 = markClosings(L);
              const again = JSON.parse(JSON.stringify(L)); markClosings(again);
              fixed = JSON.stringify(again.calls) === JSON.stringify(L.calls); }
            finally { Object.assign(CLOSING_MARK_RULES, DEF); }
            localStorage.setItem('bd_ledger_v1', JSON.stringify(L));
            return {live: marked(live), alt: marked(L), s1, s2, fixed,
                    restored: CLOSING_MARK_RULES.csvFillExempt}; }""", NE)
        # #431 R16/R17: the pages go in through the page's own putPage (legs and orders copied as it copies them, a
        # record without them stored as null and {}), the ledger stored as is (enforceLedger left out, as above); the
        # Cockpit's closingPositions, its line and its c1 (the line's own cents format) read on the stored ledger
        page.evaluate("""(x) => { const L = loadLedger(); L.calls.push(...x.calls); L.fills.push(...x.fills);
            for (const p of x.pages) putPage(L, p);
            localStorage.setItem('bd_ledger_v1', JSON.stringify(L)); }""", R17C)
        jcp = page.evaluate("""(() => { const L = loadLedger(), ps = closingPositions(L);
            return {ps: ps.map(({c, ...p}) => p), line: closingClvLine(L),
                    c1: Object.fromEntries(ps.filter(p => p.clv_c != null)
                      .map(p => { const v = +p.clv_c.toFixed(1) || 0;
                        return [p.id, `${v >= 0 ? "+" : ""}${v.toFixed(1)}c`]; }))}; })()""")
        L = page.evaluate("loadLedger()")
        js = page.evaluate("classifyFills(loadLedger())")
        jpos = page.evaluate("executedPositions(loadLedger()).pos.map(p => ({id: p.c.id, clv: p.clv, "
                             "fee_adj: p.fee_adj, fee_status: p.fee_status}))")
        browser.close()
    srv.shutdown()
    check("no page errors", not errors, "; ".join(errors))
    py = P.classify_fills(L)
    check(f"same fill count ({len(js)})", len(js) == len(py), f"js {len(js)} py {len(py)}")
    for a, b in zip(js, py):
        diff = {k: (a.get(k), b.get(k)) for k in FIELDS if a.get(k) != b.get(k)}
        check(f"{a.get('ticker')} {a.get('side')} qty {a.get('qty')} → {a.get('book')}"
              + (f" ({a.get('call_id')})" if a.get("call_id") else ""), not diff, str(diff))
    by = {f.get("id"): f for f in py}
    check("doubleheader: the 19:05 ET fill matches game 2 (dh2)", by["x-dh2"].get("call_id") == "dh2"
          and next(f for f in js if f.get("id") == "x-dh2").get("call_id") == "dh2")
    check("doubleheader: the 13:05 ET fill matches game 1 (dh1)", by["x-dh1"].get("call_id") == "dh1")
    check("three-way NO is composite, never system_matched", by["x-3no"].get("book") == "off_book_sports"
          and "composite" in (by["x-3no"].get("category") or ""))
    check("composite NO on HOME matches the AWAY ladder call", by["x-lad"].get("call_id") == "lad"
          and next(f for f in js if f.get("id") == "x-lad").get("call_id") == "lad")
    check("GB/TB: a GB (AWAY) fill never matches a TB (HOME) call (shared 'Bay')",
          by["x-gb"].get("book") == "off_book_sports" and not by["x-gb"].get("call_id")
          and next(f for f in js if f.get("id") == "x-gb").get("book") == "off_book_sports")
    check("the timed game first: a 13:05 fill whose game picked AWAY is never handed to the 15:45 HOME call",
          not by["x-ng"].get("call_id") and not next(f for f in js if f.get("id") == "x-ng").get("call_id"))
    check("same-city codes: a Giants–Rams fill never fits the Jets–Chargers call",
          not by["x-nyg"].get("call_id") and not next(f for f in js if f.get("id") == "x-nyg").get("call_id"))
    check("orientation: a BOS-home fill never fits the reversed NYY-home call",
          not by["x-rev"].get("call_id") and not next(f for f in js if f.get("id") == "x-rev").get("call_id"))
    jsby = {f.get("id"): f for f in js}
    check("NO on a three-way TIE is composite (no_on_role DRAW)", all(
        x["x-tie"].get("composite") and x["x-tie"].get("no_on_role") == "DRAW" for x in (by, jsby)))
    check("a weak NYG code is not confirmed by a strong opponent: no Jets match",
          not by["x-nygs"].get("call_id") and not jsby["x-nygs"].get("call_id"))
    check("legacy 'A vs B Winner?' title with a non-prefix code still matches (opposite code orients)",
          by["x-jax"].get("call_id") == "jax" == jsby["x-jax"].get("call_id"))
    check("legacy AWAY-vs-HOME title orients two non-prefix codes (UGAUNC)",
          by["x-unc"].get("call_id") == "unc" == jsby["x-unc"].get("call_id"))
    check("weak codes are confirmed by their OWN side's title team: the reversed Giants-home call never fits",
          not by["x-nyj"].get("call_id") and not jsby["x-nyj"].get("call_id"))
    check("tied ladder calls are flagged with every candidate, Cockpit and port alike",
          by["x-lg"].get("ambiguous_calls") == ["lg1", "lg2"] == jsby["x-lg"].get("ambiguous_calls"))
    check("Codex on #325: a KXUEFANLGAME fill matches the production INTL call (never the FUN book)",
          by["x-intl"].get("call_id") == "intl" == jsby["x-intl"].get("call_id")
          and by["x-intl"].get("book") == "system_matched" == jsby["x-intl"].get("book"))
    check("...and still matches a UNL call", by["x-unl"].get("call_id") == "unl" == jsby["x-unl"].get("call_id"))
    ppos = P.executed_positions(L)["pos"]
    check(f"executed positions: js {len(jpos)} py {len(ppos)}", len(jpos) == len(ppos) and len(jpos) > 0)
    pmap = {p["c"]["id"]: p for p in ppos}
    for jp in jpos:
        pp = pmap.get(jp["id"])
        ok = pp is not None and abs(pp["clv"] - jp["clv"]) < 1e-12 and pp["fee_status"] == jp["fee_status"] and (
            (pp["fee_adj"] is None and jp["fee_adj"] is None)
            or (pp["fee_adj"] is not None and jp["fee_adj"] is not None and abs(pp["fee_adj"] - jp["fee_adj"]) < 1e-12))
        fa = "—" if jp["fee_adj"] is None else f"{jp['fee_adj'] * 100:+.4f}pp"
        check(f"position {jp['id']}: entry CLV {jp['clv'] * 100:+.4f}pp · fee-adj {fa}",
              ok, "" if ok else f"py {pp and (pp['clv'], pp['fee_adj'], pp['fee_status'])}")
    # #431 (ARCHITECT 2026-10-20, addendum 145 item 3(b)): R7 "matchFill prefers an unmarked call of the same game and
    # side; ledger_fills.match_fill moves with it", R10 "kept in executedPositions"
    s1, s2 = ne["s1"], ne["s2"]
    check("#431: the Cockpit's own markClosings marks the claims the stored pages did not repeat (esc 12's "
          "alternative, the ledger compared): 5 marked, 3 repeated, 1 claimed after its page",
          ne["alt"] == NE_MARKED and [s2["marked"], s2["repeated"], s2["later"], s2["exempt"]] == [5, 3, 1, 0],
          f"{ne['alt']} {s2}")
    check("#431 R8: the stored marks are markClosings' fixed point (a re-save writes them unchanged); the switch is "
          "back at its proposed value", ne["fixed"] is True and ne["restored"] is True)
    check("esc 12 as proposed (csvFillExempt true) under R7 (verify_cockpit #1): only R10's claim, the one its fill "
          "still lands on, is exempt; the claims whose fills R7 hands to the unmarked call stay marked",
          ne["live"] == [i for i in NE_MARKED if i != "r10"] and [s1["marked"], s1["exempt"]] == [4, 1],
          f"{ne['live']} {s1}")
    stored = {c["id"]: c for c in L["calls"]}
    lines = {i: P.not_executed_closing(stored[i]) for i in NE_MARKED}
    want = {i: f"closing {p['family']} {p['start']}: PASS"
            for i, p in zip(("pa-m", "pb-m", "dr-m", "ld-m", "r10"), NE["pages"])}
    check("R13: each mark markClosings wrote reads whole through ledger_fills.not_executed_closing (no '?')",
          lines == want, str({i: v for i, v in lines.items() if v != want[i]}))

    def got(fid):
        return [(x[fid].get("call_id"), x[fid].get("ambiguous_calls")) for x in (by, jsby)]
    check("R7: a marked and an unmarked straight of one game and side, the marked claim first: the fill is the "
          "unmarked call's, no tie flag (Cockpit and port)", got("x-pa") == [("pa-u", None)] * 2, str(got("x-pa")))
    check("R7: the same pair, the unmarked call first: the unmarked call's, no tie flag",
          got("x-pb") == [("pb-u", None)] * 2, str(got("x-pb")))
    check("R7: a composite NO goes to the unmarked ladder of the game (claimed after its page), never the marked "
          "morning claim; no tie flag", got("x-ld") == [("ld-u", None)] * 2
          and by["x-ld"].get("composite") and jsby["x-ld"].get("composite"), str(got("x-ld")))
    check("R7 under R2 (verify_ports #1): the marked claim at the ticker's 17:05Z start, the unmarked call 5 min on: "
          "the unmarked call's, no tie flag", got("x-dr") == [("dr-u", None)] * 2, str(got("x-dr")))
    check("R7: a marked claim alone on its game and side keeps its fill", got("x-r10") == [("r10", None)] * 2,
          str(got("x-r10")))
    jids = {jp["id"] for jp in jpos}
    check("R7 x R10: of the graded pair, the executed position is the unmarked call's; the marked claim holds none "
          "(Cockpit and port)", "pa-u" in jids and "pa-u" in pmap and "pa-m" not in jids and "pa-m" not in pmap)
    r10 = next((jp for jp in jpos if jp["id"] == "r10"), None)
    check("R10: the marked claim stays in executedPositions with its fill: entry CLV +12.00pp, fee-adj +10.00pp, "
          "Cockpit and port alike", bool(stored["r10"].get("not_executed")) and r10 is not None and "r10" in pmap
          and abs(r10["clv"] - 0.12) < 1e-9 and abs(pmap["r10"]["clv"] - 0.12) < 1e-9
          and abs(r10["fee_adj"] - 0.10) < 1e-9 and abs(pmap["r10"]["fee_adj"] - 0.10) < 1e-9, str(r10))
    # #431 R16/R17 (addendum 146 item 1(iv); addendum 148 item 1): every field of every position, Cockpit and port
    jps = [{k: p.get(k) for k in R17_FIELDS} for p in jcp["ps"]]
    pps = [{k: p[k] for k in R17_FIELDS} for p in P.closing_positions(L)]
    check(f"R17: the same positions in the same order, Cockpit and port ({len(jps)})",
          [p["id"] for p in jps] == [p["id"] for p in pps] and len(jps) > 0,
          f"js {[p['id'] for p in jps]} py {[p['id'] for p in pps]}")
    pm = {p["id"]: p for p in pps}
    for jp in jps:
        pp = pm.get(jp["id"])
        diff = {k: (jp[k], pp and pp[k]) for k in R17_FIELDS if pp is None or jp[k] != pp[k]}
        check(f"R17 {jp['id']}: cover {jp['cover']} · read against {jp['page'] or 'no page'}"
              + (" (legacy)" if jp["legacy"] else "") + f" · {jp['quote']}"
              + (f" · {jcp['c1'][jp['id']]}" if jp["id"] in jcp["c1"] else "") + " · every field equal",
              not diff, str(diff))
    J = {p["id"]: p for p in jps}

    def r4(x):
        return None if x is None else round(x, 4)
    a = J["r17a"]
    check("R17 (b)(c)(e)(f)(g): a page with legs, a YES fill at 55c and a NO on the opponent at 50c (1 − its 47c bid): "
          "asks 0.53 each, +1.0c qty-weighted; R16 reads the closing page's order (0.53 × 8), not the slate's: 1 fill "
          "+2.0c above the limit, over the ordered size", a["asks"] == [0.53, 0.53] and r4(a["clv_c"]) == 1.0
          and a["page"] == "closing" and a["ordered"] == _ord(_tk("26DEC06"), "YES", 0.53, 8)
          and (a["above_limit_c"], a["above_fills"], a["over_size"], a["partial"]) == (2.0, 1, True, False), str(a))
    b = J["r17b"]
    check("R17 (f): a fill on a ticker the page does not quote: counted, not priced (the position's CLV null)",
          b["asks"] == [0.53, None] and b["quote"] == "unpriced" and b["clv_c"] is None, str(b))
    c = J["r17c"]
    check("R17 (e): no stored page: the slate's order (exec_order) is read, the CLV not priced; R16 flags it",
          (c["cover"], c["page"], c["quote"], c["clv_c"]) == ("none", "slate", "no_page", None)
          and (c["above_limit_c"], c["above_fills"], c["partial"]) == (2.0, 1, True), str(c))
    d = J["r17d"]
    check("R17 (i): a page stored without legs (putPage keeps null and {}): no closing quote stored, never priced; the "
          "slate's order read", (d["cover"], d["page"], d["quote"], d["clv_c"]) == ("page", "slate", "no_quote", None),
          str(d))
    e = J["r17e"]
    check("R17 (f): a LADDER's NO on HOME: 1 − the HOME leg's 40c bid, a 58c fill: +2.0c; its order NO 0.60 × 5",
          e["asks"] == [0.6] and r4(e["clv_c"]) == 2.0 and e["ordered"] == _ord(_EVE, "NO", 0.6, 5)
          and not (e["above_fills"] or e["over_size"] or e["partial"]), str(e))
    f = J["r17f"]
    check("R16: a page that wrote no order: {why} read against the closing page, no R16 flag; the CLV still priced",
          f["ordered"] == {"why": "no Kalshi ticker on file"} and f["page"] == "closing" and r4(f["clv_c"]) == 3.0
          and (f["above_limit_c"], f["over_size"], f["partial"]) == (None, False, False), str(f))
    g = J["r17g"]
    check("R17 (j) / law 4: two stored pages cover the claim: ambiguous, neither page's order nor quote read",
          (g["cover"], g["page"], g["ordered"], g["quote"], g["clv_c"]) == ("ambiguous", None, None, "ambiguous", None),
          str(g))
    check("R16: a claim from before R16 (no exec_order key) is legacy, Cockpit and port alike",
          sum(p["legacy"] for p in jps) == sum(p["legacy"] for p in pps) > 0)
    head = f"{len(pps)} position(s), {sum(p['filled']['fills'] for p in pps)} fill(s) · "
    check(f"R17: the Cockpit's line counts the port's positions and fills ({head.strip(' ·')})", head in jcp["line"],
          jcp["line"])
    kl = K.closing_clv_lines(L, set())
    priced = [i for i in J if J[i]["clv_c"] is not None]
    st = {x["id"]: x for x in L["calls"]}
    ok = len(kl) == len(priced) == 3 and all(
        sum(f"{st[i]['game']} · {st[i]['kickoff'][:10]} · {st[i]['call_type']} {st[i]['pick']} · {jcp['c1'][i]} · "
            "filled " in x for x in kl) == 1 for i in priced)
    check("R17: the K-track receipt prints ONE line per priced position, each with the Cockpit's cents", ok,
          "\n".join(kl))
    n = sum(CHECKS)
    print(f"\n{n}/{len(CHECKS)} checks passed")
    return 0 if n == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
