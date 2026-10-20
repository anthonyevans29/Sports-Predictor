"""#431, THE CLOSING MARKS (ARCHITECT 2026-10-11, addendum 40 item 2, fourth paragraph): "In the ledger a position is
executed where its closing file calls it. A claim that the closing page does not repeat was not executed: it stays in
the ledger as a claim, marked, and it leaves the P&L and the counts that gate sizing. A shadow follows the same rule."
Built as RULED (ARCHITECT 2026-10-20, addendum 145 item 3(b), R2–R14; the escalated switches of Issue #431 comment
6290951464 in tools/cockpit.html CLOSING_MARK_RULES, each at its proposed value and its alternative).

The page runs WHOLE under node: its own script from tools/cockpit.html after a stub of the DOM, of localStorage (a
Map) and of the clock (2026-10-19 16:30Z, TZ=UTC). Slates are built with desk_policy.annotate and closings with
deploy/hosting/closing.closing_doc (tests/test_closing_runs.py's row()), then fed to loadDocs as the file picker does;
pure functions run on synthetic rows. Skipped without node (as tests/test_cockpit_today.py). Repo copy only: the live
Cockpit is republished on the operator's word, after the architect's read."""
import copy
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.test_closing_runs import dp, mc, row  # noqa: E402  (deploy/hosting is on sys.path there)

ROOT = Path(__file__).resolve().parents[1]
COCKPIT = ROOT / "tools" / "cockpit.html"
FIXTURE = ROOT / "tests" / "fixtures" / "value_shadow" / "bd_ledger_v1_cockpit.json"

SLATE_AT = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
CLOSE_AT = datetime(2026, 10, 19, 16, 25, tzinfo=timezone.utc)
LATER_AT = datetime(2026, 10, 19, 16, 40, tzinfo=timezone.utc)
START = CLOSE_AT + timedelta(minutes=35)                            # every game kicks off at 17:00Z
RUN, RUN2 = "20261019T162500Z-nfl", "20261019T164000Z-nfl"
RUN_SAME_AS_OF = "20261019T162600Z-nfl"                           # a later run whose Desk read the same as_of
CLOSING_NAME = "closing_NFL_2026-10-19T1700Z.json"
SLATE_NAME = "nfl_predictions_2026-10-19.json"
DEFAULT_SRC = "default 0 (no ledger summary)"
# match id: (home, p_home, books' fair home, Kalshi bid, ask). Away = "<home> Visitors".
GAMES = {301: ("Buffalo", 0.62, 0.55, 0.54, 0.55),   # PLAY, exec +5.3pp: no hold, the page repeats it
         306: ("Miami", 0.60, 0.55, 0.56, 0.57),     # PLAY, exec +1.2pp, a QB listed for the picked (home) team
         307: ("Dallas", 0.60, 0.55, 0.59, 0.60),    # PLAY, exec -1.6pp, the away team's injury list unread
         304: ("Denver", 0.52, 0.515, 0.51, 0.52),   # PASS on the closing page (the slate's variant: PLAY at 0.60)
         302: ("Newark", 0.75, 0.55, 0.54, 0.55),    # quarantine shadow
         303: ("Tampa", 0.60, 0.70, 0.69, 0.70)}     # value shadow, AWAY


def tick(home, side="HOME"):
    """#431 R17: a Kalshi game ticker the fill matcher parses for "<home> Visitors @ <home>" on 2026-10-19
    (KXNFLGAME-26OCT19<away code><home code>-<side code>; Denver: KXNFLGAME-26OCT19DVDEN-DEN, DVDEN below)."""
    away, hc = home[0] + "V", home[:3].upper()
    return f"KXNFLGAME-26OCT19{away}{hc}-{hc if side == 'HOME' else away}"


def _nfl(quotes=None, ticked=False, **p_home):
    """quotes {home: (bid, ask)} moves a game's Kalshi quotes; ticked gives every leg a ticker the matcher parses
    (R17)."""
    rows = [row(mid, home, p_home.get(home, p), fair_h=fh, bid=(quotes or {}).get(home, (b, a))[0],
                ask=(quotes or {}).get(home, (b, a))[1], comp="NFL", series="KXNFLGAME", now=CLOSE_AT, minutes=35)
            for mid, (home, p, fh, b, a) in GAMES.items()]
    rows[1]["input_quality"] = {"injuries": {"home": {"count": 2, "qb_listed": ["H. Quarterback"]},
                                             "away": {"count": 1, "qb_listed": []}}}
    rows[2]["input_quality"] = {"injuries": {"home": {"count": 2, "qb_listed": []}, "away": {"count": 0, "qb_listed": []}}}
    for r in rows if ticked else []:
        for side, leg in r["kalshi_legs"].items():
            leg["ticker"] = tick(r["home_team"], side)
    return rows


def _annotate(rows, at, src="parameter"):
    return dp.annotate({"sport": "nfl", "predictions": copy.deepcopy(rows)}, now=at, counts_source=src)


def slate(quotes=None, ticked=False, **p_home):
    """The morning slate at 12:00Z; Denver a PLAY there (p 0.60)."""
    return _annotate(_nfl(quotes, ticked, **{"Denver": 0.60, **p_home}), SLATE_AT)


def closing(at=CLOSE_AT, run=RUN, ids=None, src=DEFAULT_SRC, quotes=None, ticked=False, **p_home):
    doc = _annotate(_nfl(quotes, ticked, **p_home), at, src)
    return mc.closing_doc(doc, "NFL", START, run, ids or [r["match_id"] for r in doc["predictions"]], [])


def _html():
    return COCKPIT.read_text(encoding="utf-8")


def _fn(html, name):
    """The top-level function `name`, whole (braces counted), as tests/test_cockpit_today.py reads it."""
    m = re.search(r"^(?:async )?function " + name + r"\(", html, re.M)
    assert m, name
    i, depth = html.index("{", m.end()), 0
    for j in range(i, len(html)):
        depth += {"{": 1, "}": -1}.get(html[j], 0)
        if depth == 0:
            return html[m.start():j + 1]
    raise AssertionError(name)


def _page():
    html = _html()
    return html[html.index("<script>") + len("<script>"):html.rindex("</script>")]


# The browser the page expects, stubbed: every element is a plain object (its innerHTML/textContent kept for reading),
# localStorage a Map, the clock fixed at 2026-10-19 16:30Z (after the closing's as_of, before the 17:00Z kickoffs)
STUBS = r'''"use strict";
const __NOW=Date.parse("2026-10-19T16:30:00Z"), __RealDate=Date;
globalThis.Date=class extends __RealDate{ constructor(...a){ super(...(a.length?a:[__NOW])); } static now(){ return __NOW; } };
const __els={};
function __el(id){ return {id,value:"",textContent:"",innerHTML:"",hidden:false,className:"",placeholder:"",disabled:false,
  dataset:{},style:{},children:[],addEventListener(){},querySelector(){ return __el("?"); },querySelectorAll(){ return []; },
  appendChild(){},insertAdjacentHTML(p,h){ this.innerHTML+=h; },classList:{contains(){ return false; }},remove(){},click(){},
  focus(){},select(){}}; }
globalThis.document={getElementById:id=>__els[id]||(__els[id]=__el(id)),querySelectorAll:()=>[],createElement:t=>__el(t),
  body:{appendChild(){}}};
const __store=new Map();
globalThis.localStorage={getItem:k=>__store.has(k)?__store.get(k):null,setItem:(k,v)=>{ __store.set(k,String(v)); },
  removeItem:k=>{ __store.delete(k); }};
globalThis.window=globalThis;
'''

# Helpers after the page (T_ names: never the page's own)
HELP = r'''
const T_out=x=>console.log(JSON.stringify(x));
const T_doc=(name,d)=>({name,text:JSON.stringify(d)});
const T_pages=(d,name)=>{ const rr=normalize(d); stampClosing(rr,d,name); return closingPages(rr); };
const T_seed=(calls,meta)=>localStorage.setItem(LEDGER_KEY,JSON.stringify({meta:{policy_version:"v1.1",...(meta||{})},calls}));
const T_stored=()=>localStorage.getItem(LEDGER_KEY);
const T_reset=()=>localStorage.removeItem(LEDGER_KEY);
const T_note=()=>document.getElementById("logNote").textContent;
const T_DEF={...CLOSING_MARK_RULES};
const T_rules=sw=>Object.assign(CLOSING_MARK_RULES,T_DEF,sw||{});
const T_BASE={log_date:"2026-10-19",sport:"NFL",three_way:false,status:"open",tier:"lean",engine:"model_edge",
  call_type:"straight",pick:"HOME",units:1,model_p:0.6,market_p:0.52,kickoff:"2026-10-19T17:00:00",
  claim_at:"2026-10-19T12:00:00.000Z",captured_at:"2026-10-19T12:00:00.000Z",claim_market_p:0.52,
  exec_mode:"close_default",executed_at:"2026-10-19T12:00:00.000Z",exec_market_p:0.52,claim_source:"auto",rules:[]};
function T_mk(home,o){ const c={...T_BASE,home,away:home+" Visitors",game:`${home} Visitors @ ${home}`,...(o||{})};
  for(const k of Object.keys(c)) if(c[k]===undefined) delete c[k];
  c.id=c.id||callKey(c); return c; }
const T_marks=L=>Object.fromEntries(L.calls.filter(c=>c.not_executed).map(c=>[`${c.home}|${c.call_type}|${c.pick}`,
  c.not_executed.closing.run_id]));
'''


def _node(tmp_path, body, **data):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    consts = "".join(f"const {k}={json.dumps(v)};\n" for k, v in data.items())
    js = (STUBS + _page() + "\n" + HELP + consts + "(async()=>{\n" + body
          + "\n})().catch(e=>{console.error(e&&e.stack||e);process.exit(1);});\n")
    f = tmp_path / "closing_marks.js"
    f.write_text(js, encoding="utf-8")
    r = subprocess.run([node, str(f)], capture_output=True, text=True, timeout=120, env={**os.environ, "TZ": "UTC"})
    assert r.returncode == 0, r.stderr[-4000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def _docs():
    return {"S": slate(), "C": closing(), "SN": SLATE_NAME, "CN": CLOSING_NAME}


# ------------------------------------------------------------------------------------------------- the switches --

SWITCHES = '''const CLOSING_MARK_RULES={   // #431 escalations (comment 6290951464): PROPOSED values, awaiting the architect's ruling
  execUnknown:"not_repeated",          // esc 5: exec block or edge_pp null on a PLAY  ("repeated" is the alternative)
  writtenRuleFrom:"2026-10-18T04:00:00Z", // esc 6: pages with as_of before this read the OLD rule (every exec<4 PLAY repeated, incl <=0 and unknown)
  qb:"picked_side",                    // esc 7: QB-tagged NFL PLAY: picked side's qb_listed non-empty OR picked side's injury list unread (count 0) -> not repeated; opponent-only -> repeated. Alternatives "all_repeated" | "all_not_repeated"
  bothHolds:"any_not",                 // esc 8
  execLeZeroAllFamilies:true,          // esc 9: exec<=0 reads every family whose row carries desk.exec.edge_pp (false = only MLB/NFL, the CLOSING_HOLDS families)
  ownCapture:"skip",                   // esc 4: a closing row's NOT-REPEATED PLAY is not auto-captured ("mark" = capture and mark it even though claim_at==as_of)
  missingGame:"per_game",              // esc 11: a game an earlier page carries and a later page lacks keeps the earlier page ("whole_page" alternative)
  csvFillExempt:true,                  // esc 12: RULED as built (addendum 148 item 1(a)): a Kalshi CSV fill exempts a call from the mark when matchFill, R7's unmarked preference applied, still lands it on that call
  importIdCollision:"rekey",           // esc 1 (R4): incoming call whose id a local call holds under a different pick takes the new-format id (callKey), old kept as id_imported ("refuse" alternative)
};'''
READ_SITES = {"execUnknown": "holdRead", "writtenRuleFrom": "holdRead", "qb": "holdRead", "bothHolds": "holdRead",
              "execLeZeroAllFamilies": "holdRead", "ownCapture": "ownCaptureSkips", "missingGame": "wholePageStands",
              "csvFillExempt": "markClosings", "importIdCollision": "upsertCalls"}


def test_the_switches_are_one_object_at_the_proposed_values_each_read_in_one_place():
    html = _html()
    assert html.count("const CLOSING_MARK_RULES={") == 1 and SWITCHES in html
    for key, site in READ_SITES.items():
        assert html.count(f"CLOSING_MARK_RULES.{key}") == 1, key
        assert f"CLOSING_MARK_RULES.{key}" in _fn(html, site), (key, site)
    # COMMIT 2: esc 11's one read serves the stored pages and this load's rows alike (R1 under the same rule as R9)
    assert all("wholePageStands()" in _fn(html, f) for f in ("putPage", "closingDedupe"))
    assert html.count("wholePageStands()") == 3                # its definition and the two callers


# -------------------------------------------------------------------------------------------------------- R4 --

def test_r4_the_pick_joins_callkey_and_a_same_day_flip_is_two_claims_each_at_its_own_price(tmp_path):
    """"a same-day pick flip is two claims, never one": the receipt Code found (a DRAW ending with AWAY's claim price)
    ends as two calls, each with its own claim price; a later-day re-log reprices its own pick's position."""
    assert "c.call_type,c.pick,c.parlay_id" in _fn(_html(), "callKey")
    got = _node(tmp_path, r'''
const F=(pick,p,at,day)=>({log_date:day||"2026-10-19",sport:"SOCCER",game:"Chelsea @ Arsenal",home:"Arsenal",
  away:"Chelsea",kickoff:"2026-10-20T19:00:00",three_way:true,status:"open",pick,tier:"shadow",engine:"model_edge",
  call_type:"value_shadow",units:0,shadow_units:0.25,model_p:p+0.05,market_p:p,captured_at:at});
let L={meta:{},calls:[]};
upsertCalls(L,[F("AWAY",0.30,"2026-10-19T12:30:00.000Z")],{relog:true});
upsertCalls(L,[F("DRAW",0.27,"2026-10-19T16:25:00.000Z")],{relog:true});
const one=L.calls.map(c=>[c.pick,c.claim_market_p,c.claim_at,c.exec_market_p,c.id]);
L={meta:{},calls:[]};                       // day 1 AWAY, day 2 DRAW, day 2 AWAY again
upsertCalls(L,[F("AWAY",0.30,"2026-10-18T12:00:00.000Z","2026-10-18")],{relog:true});
upsertCalls(L,[F("DRAW",0.27,"2026-10-19T12:00:00.000Z")],{relog:true});
upsertCalls(L,[F("AWAY",0.33,"2026-10-19T13:00:00.000Z")],{relog:true});
T_out({one,two:L.calls.map(c=>[c.pick,c.claim_market_p,c.exec_market_p,c.log_date])});''')
    assert [x[:4] for x in got["one"]] == [["AWAY", 0.3, "2026-10-19T12:30:00.000Z", 0.3],
                                          ["DRAW", 0.27, "2026-10-19T16:25:00.000Z", 0.27]]
    assert len({x[4] for x in got["one"]}) == 2 and all(x[4].endswith("|AWAY|") or x[4].endswith("|DRAW|")
                                                        for x in got["one"])
    assert got["two"] == [["AWAY", 0.3, 0.33, "2026-10-18"], ["DRAW", 0.27, 0.27, "2026-10-19"]]


def test_r4_a_stored_ledger_loads_and_saves_byte_identical_with_no_duplicate_and_no_lost_call(tmp_path):
    """"Stored calls are not re-keyed: the index is rebuilt from fields on every load, and c.id stays; ... a stored
    ledger loading with no duplicate and no lost call." The kept ledger (written by the Cockpit's own code, ids in the
    old six-part format) loads and saves with every id kept; the second save writes the first's bytes; a self-import
    changes nothing."""
    fix = json.loads(FIXTURE.read_text())
    got = _node(tmp_path, r'''
localStorage.setItem(LEDGER_KEY,JSON.stringify(FIX));
let L=loadLedger(); const d1=saveLedger(L), s1=T_stored();
L=loadLedger(); const d2=saveLedger(L), s2=T_stored();
importLedgerDoc(JSON.parse(s2));
T_out({s1,same:s1===s2&&T_stored()===s2,d:[d1.total,d2.total],keys:new Set(JSON.parse(s2).calls.map(callKey)).size,
  note:document.getElementById("ledgerNote").textContent});''', FIX=fix)
    s1 = json.loads(got["s1"])
    strip = [{k: v for k, v in c.items() if k != "legacy_join"} for c in s1["calls"]]
    assert strip == [{k: v for k, v in c.items() if k != "legacy_join"} for c in fix["calls"]]   # every call, every id
    assert s1["meta"] == fix["meta"] and "closings" not in s1["meta"]
    assert got["same"] is True and got["d"] == [0, 0] and got["keys"] == len(fix["calls"])
    assert got["note"] == (f"Imported {len(fix['calls'])} calls: 0 new · 0 updated · {len(fix['calls'])} unchanged/kept"
                           " (merged by key; graded entries never downgraded)")


@pytest.mark.parametrize("mode", ["rekey", "refuse"])
def test_r4_an_incoming_id_held_by_a_local_call_of_another_pick_is_rekeyed_or_refused(tmp_path, mode):
    """esc 1 (r4 (iv)): two ledgers written before the pick joined the key, apart on a same-day flip, hold the two
    positions under one id. "rekey": the incoming call takes its own key as its id, the old one kept as id_imported (an
    import of the same ledger again changes nothing); "refuse": it is not imported and the note names it."""
    got = _node(tmp_path, r'''
T_rules({importIdCollision:MODE});
const OLD="SOCCER|Chelsea @ Arsenal|2026-10-19|model_edge|value_shadow|";
const c=pick=>({log_date:"2026-10-19",sport:"SOCCER",game:"Chelsea @ Arsenal",home:"Arsenal",away:"Chelsea",
  kickoff:"2026-10-20T19:00:00",three_way:true,status:"open",pick,engine:"model_edge",call_type:"value_shadow",units:0,
  shadow_units:0.25,market_p:0.3,id:OLD});
T_seed([c("DRAW")]);
importLedgerDoc({calls:[c("AWAY")]});
const n1=document.getElementById("ledgerNote").textContent, L1=loadLedger();
importLedgerDoc({calls:[c("AWAY")]});
T_out({n1,n2:document.getElementById("ledgerNote").textContent,
  calls:L1.calls.map(x=>[x.pick,x.id,x.id_imported??null]),after:loadLedger().calls.length,key:callKey(c("AWAY"))});''',
                MODE=mode)
    old = "SOCCER|Chelsea @ Arsenal|2026-10-19|model_edge|value_shadow|"
    if mode == "rekey":
        assert got["calls"] == [["DRAW", old, None], ["AWAY", got["key"], old]] and got["key"] != old
        assert got["n1"] == ("Imported 1 calls: 1 new · 0 updated · 0 unchanged/kept (merged by key; graded entries never"
                             " downgraded) · R4 (#431): 1 incoming call(s) re-keyed (a local call of another pick holds"
                             " their id; the old id kept as id_imported)")
        assert got["n2"].startswith("Imported 1 calls: 0 new · 0 updated · 1 unchanged/kept") and got["after"] == 2
    else:
        assert got["calls"] == [["DRAW", old, None]] and got["after"] == 1
        assert got["n1"] == ("Imported 1 calls: 0 new · 0 updated · 0 unchanged/kept (merged by key; graded entries never"
                             " downgraded) · R4 (#431): 1 incoming call(s) refused (a local call of another pick holds"
                             f" their id): Chelsea @ Arsenal model_edge value_shadow AWAY ({old})")


def test_r4_upsertcalls_returns_its_four_keys_and_the_rekey_pair_only_on_an_import_id_collision(tmp_path):
    """upsertCalls' result keeps the four keys every caller read before #431 on a plain re-log and an import with no
    collision; rekeyed and refusedIds join it only when an incoming id is held by a local call of another pick
    (reverify P3 #4: cockpit_redated_verify was the only reader of this before)."""
    got = _node(tmp_path, r'''
const OLD="SOCCER|Chelsea @ Arsenal|2026-10-19|model_edge|value_shadow|";
const c=(pick,id)=>({log_date:"2026-10-19",sport:"SOCCER",game:"Chelsea @ Arsenal",home:"Arsenal",away:"Chelsea",
  kickoff:"2026-10-20T19:00:00",three_way:true,status:"open",pick,engine:"model_edge",call_type:"value_shadow",units:0,
  shadow_units:0.25,market_p:0.3,captured_at:"2026-10-19T12:00:00.000Z",...(id?{id}:{})});
let L={meta:{},calls:[]};
const relog=Object.keys(upsertCalls(L,[c("DRAW")],{relog:true}));
const again=Object.keys(upsertCalls(L,[c("DRAW")],{relog:true}));
const plain=Object.keys(upsertCalls(L,[c("HOME")],{incoming:true}));
L={meta:{},calls:[c("DRAW",OLD)]};
const coll=upsertCalls(L,[c("AWAY",OLD)],{incoming:true});
T_out({relog,again,plain,coll:Object.keys(coll),rekeyed:coll.rekeyed,refused:coll.refusedIds});''')
    four = ["added", "updated", "kept", "repriced"]
    assert got["relog"] == four and got["again"] == four and got["plain"] == four
    assert got["coll"] == four + ["rekeyed", "refusedIds"] and got["rekeyed"] == 1 and got["refused"] == []


# -------------------------------------------------------------------------------------------------------- R6 --

NEW, OLD_RULE, AT_RULE, BEFORE_RULE = ("2026-10-19T16:25:00Z", "2026-10-17T16:25:00Z", "2026-10-18T04:00:00Z",
                                      "2026-10-18T03:59:59Z")
PICKED_LISTED = {"injuries": {"home": {"count": 1, "qb_listed": ["Q"]}, "away": {"count": 1, "qb_listed": []}}}
OPP_LISTED = {"injuries": {"home": {"count": 1, "qb_listed": []}, "away": {"count": 1, "qb_listed": ["Q"]}}}
PICKED_UNREAD = {"injuries": {"home": {"count": 0, "qb_listed": []}, "away": {"count": 2, "qb_listed": []}}}
OPP_UNREAD = {"injuries": {"home": {"count": 2, "qb_listed": []}, "away": {"count": 0, "qb_listed": []}}}
QBF, QBU = ["QB-flagged half units"], ["QB unread half units"]
# (label, family, exec edge ("noexec": no exec block; None: edge_pp null), tags, rawIQ, pick, as_of, switches, class)
R6 = [
    # the exec kind (MLB, NFL), the written rule
    ("exec >= 4: no hold", "MLB", 5.0, [], {}, "HOME", NEW, {}, "repeated"),
    ("0 < exec < 4: the placed cohort", "MLB", 2.0, [], {}, "HOME", NEW, {}, "repeated"),
    ("exec a hair under 4: placed", "NFL", 4 - 1e-12, [], {}, "HOME", NEW, {}, "repeated"),
    ("exec == 0: no bet", "MLB", 0.0, [], {}, "HOME", NEW, {}, "not_repeated"),
    ("exec < 0: no bet", "NFL", -0.2, [], {}, "HOME", NEW, {}, "not_repeated"),
    ("exec block null (esc 5)", "MLB", "noexec", [], {}, "HOME", NEW, {}, "not_repeated"),
    ("edge_pp null (esc 5)", "NFL", None, [], {}, "HOME", NEW, {}, "not_repeated"),
    ("exec block null, alternative", "MLB", "noexec", [], {}, "HOME", NEW, {"execUnknown": "repeated"}, "repeated"),
    ("edge_pp null, alternative", "NFL", None, [], {}, "HOME", NEW, {"execUnknown": "repeated"}, "repeated"),
    # the old rule (esc 6): every exec < 4 a paste step, so repeated
    ("old rule, 0 < exec < 4", "MLB", 2.0, [], {}, "HOME", OLD_RULE, {}, "repeated"),
    ("old rule, exec == 0", "MLB", 0.0, [], {}, "HOME", OLD_RULE, {}, "repeated"),
    ("old rule, exec < 0", "NFL", -3.0, [], {}, "HOME", OLD_RULE, {}, "repeated"),
    ("old rule, exec unknown", "NFL", "noexec", [], {}, "HOME", OLD_RULE, {}, "repeated"),
    ("a second before the rule", "MLB", -1.0, [], {}, "HOME", BEFORE_RULE, {}, "repeated"),
    ("at the rule's instant", "MLB", -1.0, [], {}, "HOME", AT_RULE, {}, "not_repeated"),
    ("the rule dated later (alternative date)", "MLB", -1.0, [], {}, "HOME", NEW,
     {"writtenRuleFrom": "2026-10-20T04:00:00Z"}, "repeated"),
    # esc 9: exec <= 0 in a family outside CLOSING_HOLDS
    ("SOCCER exec < 0 (every family)", "SOCCER", -1.0, [], {}, "HOME", NEW, {}, "not_repeated"),
    ("SOCCER exec < 0, alternative", "SOCCER", -1.0, [], {}, "HOME", NEW, {"execLeZeroAllFamilies": False}, "repeated"),
    ("SOCCER 0 < exec < 4: no hold", "SOCCER", 2.0, [], {}, "HOME", NEW, {}, "repeated"),
    ("SOCCER exec unknown: no hold", "SOCCER", "noexec", [], {}, "HOME", NEW, {}, "repeated"),
    ("SOCCER exec < 0, old rule", "SOCCER", -1.0, [], {}, "HOME", OLD_RULE, {}, "repeated"),
    # the QB kind (NFL), esc 7, exec clear of the hold
    ("QB flagged, the picked team's", "NFL", 5.0, QBF, PICKED_LISTED, "HOME", NEW, {}, "not_repeated"),
    ("QB flagged, the picked team's (away pick)", "NFL", 5.0, QBF, OPP_LISTED, "AWAY", NEW, {}, "not_repeated"),
    ("QB flagged, the opponent's only", "NFL", 5.0, QBF, OPP_LISTED, "HOME", NEW, {}, "repeated"),
    ("QB unread, the picked team's list", "NFL", 5.0, QBU, PICKED_UNREAD, "HOME", NEW, {}, "not_repeated"),
    ("QB unread, the opponent's list only", "NFL", 5.0, QBU, OPP_UNREAD, "HOME", NEW, {}, "repeated"),
    ("QB picked, all_repeated", "NFL", 5.0, QBF, PICKED_LISTED, "HOME", NEW, {"qb": "all_repeated"}, "repeated"),
    ("QB opponent, all_repeated", "NFL", 5.0, QBF, OPP_LISTED, "HOME", NEW, {"qb": "all_repeated"}, "repeated"),
    ("QB picked, all_not_repeated", "NFL", 5.0, QBF, PICKED_LISTED, "HOME", NEW, {"qb": "all_not_repeated"},
     "not_repeated"),
    ("QB opponent, all_not_repeated", "NFL", 5.0, QBU, OPP_UNREAD, "HOME", NEW, {"qb": "all_not_repeated"},
     "not_repeated"),
    ("a QB tag outside NFL: no QB hold", "MLB", 5.0, QBF, PICKED_LISTED, "HOME", NEW, {}, "repeated"),
    # both kinds (esc 8)
    ("both: placed exec + picked QB, any_not", "NFL", 2.0, QBF, PICKED_LISTED, "HOME", NEW, {}, "not_repeated"),
    ("both: placed exec + picked QB, all_not", "NFL", 2.0, QBF, PICKED_LISTED, "HOME", NEW, {"bothHolds": "all_not"},
     "repeated"),
    ("both: exec < 0 + picked QB, all_not", "NFL", -1.0, QBF, PICKED_LISTED, "HOME", NEW, {"bothHolds": "all_not"},
     "not_repeated"),
    ("both: placed exec + opponent QB", "NFL", 2.0, QBF, OPP_LISTED, "HOME", NEW, {}, "repeated"),
    ("both: exec < 0 + opponent QB, any_not", "NFL", -1.0, QBU, OPP_UNREAD, "HOME", NEW, {}, "not_repeated"),
    ("both, old rule + picked QB", "NFL", -1.0, QBF, PICKED_LISTED, "HOME", OLD_RULE, {}, "not_repeated"),
]


def test_r6_every_row_of_the_table_by_the_holds_kind_and_each_switchs_alternative(tmp_path):
    """R6, RULED "by the hold's kind": a PLAY held for a PLACEMENT STEP is repeated by its page; a PLAY held under a rule
    that ENDS IN NO BET (the QB hold on the picked team; exec <= 0) is not. The table of SPEC_V2 item 3 (read_r6.md
    section 2), row by row, at the proposed switches and each alternative; a PASS or LADDER row is never a held PLAY."""
    cases = []
    for label, fam, e, tags, iq, pick, as_of, sw, _ in R6:
        desk = {"call": "PLAY", "pick": pick, "units": 0.5, "tags": tags}
        desk["exec"] = None if e == "noexec" else {"edge_pp": e}
        cases.append({"label": label, "fam": fam, "desk": desk, "iq": iq, "as_of": as_of, "sw": sw})
    for call in ("PASS", "LADDER"):
        cases.append({"label": call, "fam": "MLB", "desk": {"call": call, "pick": "HOME", "units": 0.5, "tags": [],
                                                             "exec": {"edge_pp": -3}}, "iq": {}, "as_of": NEW, "sw": {}})
    got = _node(tmp_path, r'''
T_out(CASES.map(k=>{ T_rules(k.sw);
  const r={sport:k.fam,home:"H",away:"A",pick:"HOME",utc:"2026-10-19T17:00:00",fileDesk:k.desk,rawIQ:k.iq,
    closing:{family:k.fam,start:"2026-10-19T17:00:00Z",run_id:"R",as_of:k.as_of,file:"f"}};
  return [k.label,holdClass(r)]; }));''', CASES=cases)
    assert got == [[x[0], x[-1]] for x in R6] + [["PASS", "repeated"], ["LADDER", "repeated"]]


def test_r6_a_real_closing_pages_rows_classify_and_read_as_the_page_reads_them(tmp_path):
    """The closing page built by closing_doc from desk_policy.annotate rows (closing.py's hold_for holds 306, 307 and
    308): the page's call set per game ("engine|call_type|pick") and its own words; a PLAY its page does not repeat says
    under which hold it is no bet."""
    rows = _nfl()
    extra = row(308, "Boston", 0.60, fair_h=0.55, comp="NFL", series="KXNFLGAME", now=CLOSE_AT, minutes=35)
    extra["kalshi_bid"] = extra["kalshi_ask"] = None
    extra.pop("kalshi_legs")
    doc = _annotate(rows + [extra], CLOSE_AT, DEFAULT_SRC)
    cdoc = mc.closing_doc(doc, "NFL", START, RUN, [r["match_id"] for r in doc["predictions"]], [])
    holds = {r["match_id"]: mc.hold_for(r["desk"], "NFL") for r in cdoc["predictions"]}
    assert holds[301] is None and holds[304] is None and holds[306] and holds[307] and holds[308]
    got = _node(tmp_path, r'''
const rr=normalize(C); stampClosing(rr,C,CN);
T_out(rr.map(r=>[r.home,holdClass(r),[...closingCalls(r)].sort(),closingCallText(r)]));''', C=cdoc, CN=CLOSING_NAME)
    assert got == [
        ["Buffalo", "repeated", ["model_edge|straight|HOME"], "PLAY Buffalo 1u"],
        ["Miami", "not_repeated", [],
         "PLAY Miami 0.5u — not a bet under the QB hold: H. Quarterback listed for the picked team (#431 R6)"],
        ["Dallas", "not_repeated", [], "PLAY Dallas 0.5u — not a bet under exec -1.6pp ≤ 0 (the written rule) (#431 R6)"],
        ["Denver", "repeated", [], "PASS"],
        ["Newark", "repeated", ["model_edge|quarantine_shadow|HOME"], "PASS · quarantine shadow Newark 0.5u"],
        ["Tampa", "repeated", ["model_edge|value_shadow|AWAY"], "PASS · value shadow Tampa Visitors 0.25u"],
        ["Boston", "not_repeated", [],
         "PLAY Boston 0.5u — not a bet under exec unknown (no executable quote) (#431 R6)"]]


def test_the_pages_call_set_follows_snapshot_calls_and_tests_the_quarantine_tag_as_the_page_does(tmp_path):
    """closingCalls: snapshotCalls' mapping without the kickoff test; the quarantine shadow by its tag alone (the page's
    is_quarantine_shadow), never isQuarShadow's r.quar fallback; a market-only row gives its venue call only."""
    got = _node(tmp_path, r'''
const R=(desk,o)=>({sport:"NFL",home:"H",away:"A",pick:"HOME",utc:"2026-10-19T17:00:00",fileDesk:desk,rawIQ:{},
  closing:{family:"NFL",start:"s",run_id:"R",as_of:"2026-10-19T16:25:00Z",file:"f"},...(o||{})});
const tagged={call:"PASS",pick:"HOME",units:0,shadow_units:0.5,tags:["quarantine ≥ 15pp (shadow)"]};
const untagged={call:"PASS",pick:"HOME",units:0,shadow_units:0.5,tags:[]};
const cs=r=>[...closingCalls(r)].sort();
T_out({ladder:cs(R({call:"LADDER",pick:"AWAY",units:0.5})),
  quar:cs(R(tagged)),quarFallback:[cs(R(untagged,{quar:true})),isQuarShadow(fileCall(R(untagged,{quar:true})),R(untagged,{quar:true}))],
  value:cs(R({call:"PASS",pick:"HOME",units:0,value_shadow:{side:"DRAW",edge_pp:5,units:0.25}})),
  venue:cs(R({call:"PASS",pick:"HOME",units:0,venue:{eligible:true,side:"AWAY"}})),
  marketOnly:cs(R({call:"PLAY",pick:"HOME",units:1,value_shadow:{side:"AWAY"},venue:{eligible:true,side:"HOME"}},{marketOnly:true})),
  pass:cs(R({call:"PASS",pick:"HOME",units:0}))});''')
    assert got == {"ladder": ["model_edge|ladder|AWAY"], "quar": ["model_edge|quarantine_shadow|HOME"],
                   "quarFallback": [[], True], "value": ["model_edge|value_shadow|DRAW"],
                   "venue": ["venue_edge|straight|AWAY"], "marketOnly": ["venue_edge|straight|HOME"], "pass": []}


# --------------------------------------------------------------------------------------------- the main receipt --

CLOSING_SEGMENT = (" · closing: 1 page(s) read · 6 game(s) stored · 0 kept (the stored page is newer or the same) · 3 claim(s)"
                   " marked NOT EXECUTED (the page did not repeat them; 3 new, 0 cleared by a later page) · 3 repeated · 0"
                   " executed early or filled, not repeated (never marked) · 2 closing PLAY(s) not a bet, not claimed")
COUNTS_NOTE = (' · the closing file(s) read counts_source "default 0 (no ledger summary)": their Desk sized with postseason 0'
               " · value shadow 0 · kalshi-only 0 (no export reads a ledger summary, #544) — this ledger's own counts:"
               " postseason 0/30 · value shadow 0/30 · kalshi-only 0/30 (NOT EXECUTED claims left out).")
MARK_DENVER = {"flag": "not executed (#431)",
               "closing": {"family": "NFL", "start": "2026-10-19T17:00:00Z", "run_id": RUN, "as_of": "2026-10-19T16:25:00Z",
                           "file": CLOSING_NAME},
               "closing_call": {"text": "PASS", "calls": []}}


def test_a_slate_then_its_closing_marks_the_claims_the_page_did_not_repeat_shown_and_logged(tmp_path):
    """The receipt: the morning slate's claims (12:00Z), then the closing page (16:25Z). Denver (the page says PASS),
    Miami (the QB hold on the picked team) and Dallas (exec <= 0) are marked with the page's words; Buffalo, the
    quarantine shadow and the value shadow are repeated. The load note, the stored page, the P&L line, the
    #notExecuted list and the open table say so."""
    got = _node(tmp_path, r'''
await loadDocs([T_doc(SN,S)]);
const before=JSON.parse(T_stored()).calls.length;
await loadDocs([T_doc(CN,C)]);
const L=loadLedger(), pnl=pnlBlock(L).split("\n"), i=pnl.findIndex(l=>l.startsWith("Kickoff audit (#178)"));
const den=L.calls.find(c=>c.home==="Denver"), buf=L.calls.find(c=>c.home==="Buffalo");
const open=document.getElementById("openList").innerHTML;
T_out({before,n:L.calls.length,note:T_note(),marks:T_marks(L),den:den.not_executed,
  miami:L.calls.find(c=>c.home==="Miami").not_executed.closing_call,
  stored:L.meta.closings,next:pnl[i+1],
  list:(open.match(/<div class="note" id="notExecuted">.*?<\/div>/)||[""])[0],
  denRow:open.includes('<td><b class="caution">NOT EXECUTED</b> at close')&&!open.includes(`execBtn" data-id="${den.id}"`),
  bufExec:open.includes(`execBtn" data-id="${buf.id}"`),
  psProgress:document.getElementById("psProgress").textContent});''', **_docs())
    assert got["before"] == got["n"] == 6                       # the closing's captures reprice, nothing is added
    assert got["note"].startswith('Auto-claimed 3 call(s) at their file\'s as_of — 0 new · 3 position(s) repriced · ')
    assert got["note"].endswith('"Re-log at T-60" refreshes prices.' + CLOSING_SEGMENT + COUNTS_NOTE)
    assert got["marks"] == {"Miami|straight|HOME": RUN, "Dallas|straight|HOME": RUN, "Denver|straight|HOME": RUN}
    assert got["den"] == MARK_DENVER
    assert got["miami"] == {"text": "PLAY Miami 0.5u — not a bet under the QB hold: H. Quarterback listed for the"
                                    " picked team (#431 R6)", "calls": []}
    st = got["stored"]["NFL|2026-10-19T17:00:00Z"]
    assert list(got["stored"]) == ["NFL|2026-10-19T17:00:00Z"] and st["family"] == "NFL"
    assert st["pages"] == {RUN: {"as_of": "2026-10-19T16:25:00Z", "file": CLOSING_NAME}} and len(st["games"]) == 6
    assert st["games"]["NFL|Tampa|Tampa Visitors|2026-10-19T17:00:00"] == {
        "sport": "NFL", "home": "Tampa", "away": "Tampa Visitors", "kickoff": "2026-10-19T17:00:00",
        "calls": ["model_edge|value_shadow|AWAY"], "text": "PASS · value shadow Tampa Visitors 0.25u", "run_id": RUN,
        "as_of": "2026-10-19T16:25:00Z", "file": CLOSING_NAME,
        # #431 R16/R17 (addendum 146 item 1(iv)): the row's Kalshi legs, copy-exact; the page's orders (a shadow: none)
        "legs": {"HOME": {"ticker": "KXNFLGAME-26OCT11-TAMH", "bid": 0.69, "ask": 0.7},
                 "AWAY": {"ticker": "KXNFLGAME-26OCT11-TAMA", "bid": 0.3, "ask": 0.31}}, "orders": {}}
    assert got["next"] == ("Not executed (addendum 40 item 2, #431): 3 claim(s) the closing page did not repeat (0"
                           " position(s), 0 ticket(s) settled) — out of the P&L, the sizing gate and the graded n/30"
                           " counts; marked, never deleted.")
    assert got["list"].startswith('<div class="note" id="notExecuted"><b>3 claim(s) not executed</b> (the closing page'
                                  " did not repeat them: out of the P&L and the graded counts, marked, never deleted;"
                                  " the claim's own numbers stay):")
    assert ("<br>2026-10-19 · NFL · Denver Visitors @ Denver · Denver · model_edge straight · claim 0.515 10-19 12:00 ·"
            " <b>NOT EXECUTED</b> · closing NFL 2026-10-19T17:00:00Z: PASS · open") in got["list"]
    assert got["denRow"] is True and got["bufExec"] is True
    assert got["psProgress"] == "graded 0/30"                  # the 144 note is in the load note only


def test_the_mark_is_the_contract_shape_and_a_save_or_a_reload_writes_the_same_bytes(tmp_path):
    """The mark is a contract the Python ports read (closing.family, closing.start, closing_call.text): deterministic,
    no clock field, so a re-save, and a reload of the same page (every game kept, every claim already claimed), leave
    the stored ledger byte for byte."""
    got = _node(tmp_path, r'''
await loadDocs([T_doc(SN,S)]); await loadDocs([T_doc(CN,C)]);
const s1=T_stored(); saveLedger(loadLedger()); const s2=T_stored();
await loadDocs([T_doc(CN,C)]);
T_out({same:s1===s2&&T_stored()===s1,note:T_note(),
  shapes:loadLedger().calls.filter(c=>c.not_executed).map(c=>[Object.keys(c.not_executed),
    Object.keys(c.not_executed.closing),Object.keys(c.not_executed.closing_call)])});''', **_docs())
    assert got["same"] is True
    assert " · closing: 1 page(s) read · 0 game(s) stored · 6 kept (the stored page is newer or the same) · 3 claim(s)" \
           " marked NOT EXECUTED (the page did not repeat them; 0 new, 0 cleared by a later page)" in got["note"]
    assert got["shapes"] == [[["flag", "closing", "closing_call"], ["family", "start", "run_id", "as_of", "file"],
                              ["text", "calls"]]] * 3


def test_nothing_is_deleted_the_mark_is_one_field_beside_the_claims_own(tmp_path):
    """"Marked, never deleted": the same calls, and every stored field of each equal once not_executed is set aside."""
    got = _node(tmp_path, r'''
await loadDocs([T_doc(SN,S)]);
const before=JSON.parse(T_stored()).calls;
const ne=storeClosings(T_pages(C,CN));
const after=JSON.parse(T_stored()).calls;
T_out({n:[before.length,after.length],marked:ne.marked,
  same:before.every((c,i)=>JSON.stringify(c)===JSON.stringify(unmarked(after[i]))),
  only:after.map(c=>Object.keys(c).filter(k=>!(k in before.find(b=>b.id===c.id))))});''', **_docs())
    assert got["n"] == [6, 6] and got["marked"] == 3 and got["same"] is True
    assert sorted(map(tuple, got["only"])) == [(), (), (), ("not_executed",), ("not_executed",), ("not_executed",)]


# -------------------------------------------------------------------------------------------------- R2 and R3 --

def test_r2_a_kickoff_within_the_hour_is_the_same_game_and_beyond_it_is_not(tmp_path):
    """R2: same sport, home and away, kickoffs within DESK_CLOCK_DRIFT (1 h, inclusive); no machine-local id."""
    got = _node(tmp_path, r'''
T_out(["2026-10-19T18:00:00","2026-10-19T16:00:00","2026-10-19T18:01:00","2026-10-19T15:59:00"].map(k=>{
  T_seed([T_mk("Denver",{kickoff:k,match_id:999999})]); const ne=storeClosings(T_pages(C,CN));
  return [k,ne.covered,ne.marked]; }));''', **_docs())
    assert got == [["2026-10-19T18:00:00", 1, 1], ["2026-10-19T16:00:00", 1, 1],
                   ["2026-10-19T18:01:00", 0, 0], ["2026-10-19T15:59:00", 0, 0]]


def test_r3_a_claim_at_or_after_the_page_is_not_marked_and_a_legacy_claim_is_counted_not_marked(tmp_path):
    """R3: claim_at strictly before the closing's as_of marks; a claim at or after it is not marked; a legacy call with
    no claim_at/captured_at is not marked and the line says how many such calls sit on covered games."""
    got = _node(tmp_path, r'''
const run=calls=>{ T_seed(calls); const ne=storeClosings(T_pages(C,CN)), L=loadLedger();
  return {later:ne.later,legacy:ne.legacy,marked:ne.marked,note:closingMarkNote(ne,0),line:(settledBets(L),notExecutedLine(L))}; };
T_out({after:run([T_mk("Denver",{claim_at:"2026-10-19T16:30:00.000Z",captured_at:"2026-10-19T16:30:00.000Z"})]),
  at:run([T_mk("Denver",{claim_at:"2026-10-19T16:25:00.000Z",claim_source:undefined})]),
  legacy:run([T_mk("Denver",{claim_at:undefined,captured_at:undefined})])});''', **_docs())
    assert [got["after"][k] for k in ("later", "legacy", "marked")] == [1, 0, 0]
    assert [got["at"][k] for k in ("later", "legacy", "marked")] == [1, 0, 0]
    assert [got["legacy"][k] for k in ("later", "legacy", "marked")] == [0, 1, 0]
    assert " · 1 legacy claim(s) on covered games carry no claim time (not marked)" in got["legacy"]["note"]
    assert got["legacy"]["line"].endswith(" · 1 legacy claim(s) on covered games carry no claim time and are not marked")
    assert "legacy" not in got["after"]["line"]


def test_r3_a_page_with_no_as_of_marks_nothing_and_the_claims_on_its_games_are_counted(tmp_path):
    """R3 asks "strictly before the closing's as_of"; a page whose as_of does not read cannot establish it (law 4:
    conservative unknowns): its games mark nothing, before or after, and the note counts the claims (only when there
    are any)."""
    got = _node(tmp_path, r'''
const P=JSON.parse(JSON.stringify(C)); delete P.desk_meta.as_of; delete P.exported_at;
const run=(calls,doc)=>{ T_seed(calls); const ne=storeClosings(T_pages(doc,CN));
  return {marked:ne.marked,later:ne.later,noAsOf:ne.noAsOf,note:closingMarkNote(ne,0),marks:T_marks(loadLedger())}; };
T_out({asOf:T_pages(P,CN)[0].as_of,
  before:run([T_mk("Denver")],P),
  after:run([T_mk("Denver",{claim_at:"2026-10-19T18:30:00.000Z",captured_at:"2026-10-19T18:30:00.000Z"})],P),
  read:run([T_mk("Denver")],C)});''', **_docs())
    assert got["asOf"] is None
    for k in ("before", "after"):
        assert [got[k]["marked"], got[k]["later"], got[k]["noAsOf"], got[k]["marks"]] == [0, 0, 1, {}], k
        assert (" · 1 claim(s) on a covered game whose closing page carries no as_of (not marked: before or after the"
                " page cannot be read, law 4)") in got[k]["note"]
    assert [got["read"]["marked"], got["read"]["noAsOf"]] == [1, 0] and "no as_of" not in got["read"]["note"]


def test_a_claim_two_starts_pages_cover_is_ambiguous_its_mark_lifted_and_counted_under_ambiguous_only(tmp_path):
    """Law 4: a call whose game two starts' pages cover (kickoffs within the hour of both) is never guessed: not marked,
    counted as ambiguous. A mark it carried is lifted and counted there, never as "cleared by a later page"."""
    got = _node(tmp_path, r'''
T_seed([T_mk("Denver")]);
const ne1=storeClosings(T_pages(C,CN)), m1=T_marks(loadLedger());
const P=JSON.parse(JSON.stringify(C)); P.closing.start="2026-10-19T17:30:00Z"; P.closing.run_id="20261019T165500Z-nfl";
P.desk_meta.as_of="2026-10-19T16:55:00Z"; P.predictions.forEach(r=>{ r.utc_date="2026-10-19T17:30:00Z"; });
const ne2=storeClosings(T_pages(P,"c2.json"));
T_out({m1,ne1:[ne1.marked,ne1.ambiguous],ne2:[ne2.marked,ne2.ambiguous,ne2.cleared,ne2.covered],m2:T_marks(loadLedger()),
  note:closingMarkNote(ne2,0)});''', **_docs())
    assert got["m1"] == {"Denver|straight|HOME": RUN} and got["ne1"] == [1, 0]
    assert got["ne2"] == [0, 1, 0, 0] and got["m2"] == {}
    assert ("0 claim(s) marked NOT EXECUTED (the page did not repeat them; 0 new, 0 cleared by a later page)"
            in got["note"])
    assert " · 1 claim(s) on a game two closing pages cover (not marked, never guessed)" in got["note"]


def test_a_mark_whose_page_is_not_stored_is_kept_and_counted_and_one_whose_page_is_stored_is_lifted(tmp_path):
    """A call carrying a mark whose closing page this ledger does not store (a calls-only import, or a page another
    browser holds) keeps it as it came, counted as an orphan, with or without stored pages; a mark whose page is stored
    but no longer covers the call's game is lifted (counted cleared)."""
    got = _node(tmp_path, r'''
const NE=(start)=>({flag:"not executed (#431)",closing:{family:"NFL",start,run_id:"R0",as_of:"2026-10-12T16:25:00Z",
  file:"f"},closing_call:{text:"PASS",calls:[]}});
const old=T_mk("Albany",{kickoff:"2026-10-12T17:00:00",log_date:"2026-10-12",not_executed:NE("2026-10-12T17:00:00Z")});
T_seed([old]); const s0=saveLedger(loadLedger()).marks, k0=!!loadLedger().calls[0].not_executed;
T_seed([old,T_mk("Denver")]); const ne=storeClosings(T_pages(C,CN)), L=loadLedger();
const moved=T_mk("Albany",{not_executed:NE("2026-10-19T17:00:00Z")});
T_seed([moved]); const ne3=storeClosings(T_pages(C,CN));
T_out({s0:[s0.orphan,s0.marked],k0,ne:[ne.orphan,ne.marked,ne.cleared],note:closingMarkNote(ne,0),
  kept:L.calls.map(c=>[c.home,c.not_executed?c.not_executed.closing.start:null]),
  moved:[ne3.orphan,ne3.cleared,!!loadLedger().calls[0].not_executed]});''', **_docs())
    assert got["s0"] == [1, 0] and got["k0"] is True
    assert got["ne"] == [1, 1, 0]
    assert got["kept"] == [["Albany", "2026-10-12T17:00:00Z"], ["Denver", "2026-10-19T17:00:00Z"]]
    assert " · 1 mark(s) whose closing page is not stored here (kept as they came)" in got["note"]
    assert got["moved"] == [0, 1, False]


# ------------------------------------------------------------------------------------------------------- esc 4 --

@pytest.mark.parametrize("mode", ["skip", "mark"])
def test_esc4_the_closings_own_no_bet_play_is_never_counted_executed(tmp_path, mode):
    """R3 x R6 (esc 4): the closing's own capture of a PLAY its page does not repeat has claim_at == as_of. "skip": it
    is never claimed (counted on the note); "mark": it is claimed and marked. Either way it never counts executed."""
    got = _node(tmp_path, r'''
T_rules({ownCapture:MODE});
await loadDocs([T_doc(CN,C)]);
const L=loadLedger();
const note=T_note();
for(const c of L.calls){ c.status="graded"; c.result="win"; c.graded_date="2026-10-20"; c.units_returned=+(c.units*1.9).toFixed(4);
  if(isShadow(c)) c.shadow_returned=+((c.shadow_units||0)*1.9).toFixed(4); }
saveLedger(L); const G=loadLedger(), bets=settledBets(G);
T_out({calls:L.calls.map(c=>c.home).sort(),marks:T_marks(G),note,bets:bets.map(b=>b.call_type),ne:{...lastNotExec}});''',
                MODE=mode, **_docs())
    # every claim graded a win: the settled bets are Buffalo's straight and the two shadows in either mode, so a PLAY its
    # closing page does not repeat never reaches the P&L; "mark" holds it out as not executed (lastNotExec)
    assert got["bets"] == ["straight", "quarantine_shadow", "value_shadow"]
    if mode == "skip":
        assert got["calls"] == ["Buffalo", "Newark", "Tampa"] and got["marks"] == {}
        assert " · 2 closing PLAY(s) not a bet, not claimed" in got["note"]
        assert got["ne"] == {"positions": 0, "tickets": 0, "voidLeg": 0}
    else:
        assert got["calls"] == ["Buffalo", "Dallas", "Miami", "Newark", "Tampa"]
        assert got["marks"] == {"Miami|straight|HOME": RUN, "Dallas|straight|HOME": RUN}
        assert "not a bet, not claimed" not in got["note"]
        assert got["ne"] == {"positions": 2, "tickets": 0, "voidLeg": 0}
    # no claim from before the page anywhere in this ledger (R14 (a)); no slate row in the load, so no ⚠
    assert got["note"].endswith(" · 6 of 6 covered game(s) hold no claim from before their page in this browser's"
                                " ledger: nothing there to mark. A local Cockpit keeps its own ledger: import the ledger,"
                                " then load." + COUNTS_NOTE)


# -------------------------------------------------------------------------------------------------- R5 and R7 --

def _ticket(home2, **o):
    leg = {"call_type": "parlay_leg", "parlay_id": "P-2026-10-19-T", "units": 0.25, "tier": "parlay", "status": "graded",
           "result": "win", "ticket_result": "win", "units_returned": 1.0, "graded_date": "2026-10-20"}
    return [dict(leg), {**leg, **o, "home2": home2}]


def test_r5_a_ticket_with_a_leg_the_page_did_not_repeat_leaves_the_pnl_and_an_executed_ticket_is_never_marked(tmp_path):
    """R5, the literal reading: a ticket's leg on a covered game the page does not repeat is marked (closings carry no
    tickets) and the ticket leaves the P&L; a ticket with an execution record on any leg is never marked (R7)."""
    got = _node(tmp_path, r'''
const leg=(home,o)=>T_mk(home,{call_type:"parlay_leg",parlay_id:"P-2026-10-19-T",units:0.25,tier:"parlay",status:"graded",
  result:"win",ticket_result:"win",units_returned:1,graded_date:"2026-10-20",...(o||{})});
const won=T_mk("Buffalo",{status:"graded",result:"win",units_returned:1.8,graded_date:"2026-10-20"});
const run=early=>{ T_seed([leg("Denver"),leg("Albany",early?{exec_mode:"operator_early"}:{}),won]);
  const ne=storeClosings(T_pages(C,CN)), L=loadLedger(), bets=settledBets(L);
  return {marks:T_marks(L),exempt:ne.exempt,bets:bets.map(b=>b.call_type),ne:{...lastNotExec}}; };
T_out({plain:run(false),executed:run(true)});''', **_docs())
    assert got["plain"] == {"marks": {"Denver|parlay_leg|HOME": RUN}, "exempt": 0, "bets": ["straight"],
                            "ne": {"positions": 0, "tickets": 1, "voidLeg": 0}}
    assert got["executed"] == {"marks": {}, "exempt": 1, "bets": ["parlay", "straight"],
                               "ne": {"positions": 0, "tickets": 0, "voidLeg": 0}}


DVDEN = "KXNFLGAME-26OCT19DVDEN-DEN"                   # YES on Denver (home): the Denver straight's game and side


@pytest.mark.parametrize("case", ["operator_early", "fill_recorded", "csv", "csv_alternative", "csv_other_side"])
def test_r7_executed_early_a_recorded_fill_and_a_csv_fill_are_never_marked(tmp_path, case):
    """R7: "operator-early executions and recorded fills are never marked ("executed early, not repeated")"; esc 12: a
    Kalshi CSV fill that matchFill's candidate rule (marks set aside) gives to the call exempts it too (false: it does
    not); a fill on the other side never does."""
    got = _node(tmp_path, r'''
const o={operator_early:{exec_mode:"operator_early"},fill_recorded:{fill_recorded_at:"2026-10-19T13:00:00.000Z"}}[CASE]||{};
if(CASE==="csv_alternative") T_rules({csvFillExempt:false});
const fills=CASE.startsWith("csv")?[{id:"F1",ticker:CASE==="csv_other_side"?TK.replace(/-DEN$/,"-DV"):TK,side:"yes",qty:10,
  entry:0.5,title:""}]:[];
T_seed([T_mk("Denver",o)]); const L0=loadLedger(); L0.fills=fills; saveLedger(L0);
const ne=storeClosings(T_pages(C,CN));
T_out({exempt:ne.exempt,marked:ne.marked,note:closingMarkNote(ne,0)});''', CASE=case, TK=DVDEN, **_docs())
    exempt = case in ("operator_early", "fill_recorded", "csv")
    assert [got["exempt"], got["marked"]] == ([1, 0] if exempt else [0, 1])
    assert f" · {got['exempt']} executed early or filled, not repeated (never marked)" in got["note"]


@pytest.mark.parametrize("case", ["venue_repeated", "venue_repeated_alternative", "both_marked"])
def test_r7_esc12_a_csv_fill_exempts_only_a_marked_call_it_still_lands_on(tmp_path, case):
    """esc 12 under R7 (verify_cockpit #1): the marks come first, without the CSV exemption; matchFill then runs over
    the calls carrying them (R7: "matchFill prefers an unmarked call of the same game and side"), and only a marked call
    the fill still lands on is exempt. The morning model straight on Denver HOME and a venue straight on the same side;
    the closing page says PASS on the model and calls the venue straight; one Kalshi fill on Denver YES: the fill is
    the venue call's, so the claim the page did not repeat stays marked ("it leaves the P&L", addendum 40 item 2), with
    the switch at either value. The page calling neither: the fill's tie group is all marked, so both are exempt."""
    got = _node(tmp_path, r'''
if(CASE==="venue_repeated_alternative") T_rules({csvFillExempt:false});
const model=T_mk("Denver",{id:"MODEL"}), ven=T_mk("Denver",{id:"VENUE",engine:"venue_edge",tier:"shadow"});
T_seed([model,ven]); const L0=loadLedger(); L0.fills=[{id:"F1",ticker:TK,side:"yes",qty:10,entry:0.5,title:""}]; saveLedger(L0);
const P=JSON.parse(JSON.stringify(C));
if(CASE!=="both_marked") P.predictions.find(r=>r.home_team==="Denver").desk.venue={eligible:true,side:"HOME",div_pp:6,
  book_p:0.5,kalshi_p:0.56};
const pages=T_pages(P,CN), ne=storeClosings(pages), L=loadLedger(), f=classifyFills(L)[0];
T_out({calls:Object.values(pages[0].games).find(g=>g.home==="Denver").calls,marked:ne.marked,exempt:ne.exempt,
  repeated:ne.repeated,marks:L.calls.map(c=>[c.id,!!c.not_executed]),fill:[f.call_id,f.ambiguous_calls||null]});''',
                CASE=case, TK=DVDEN, **_docs())
    if case == "both_marked":
        assert got["calls"] == [] and [got["marked"], got["exempt"], got["repeated"]] == [0, 2, 0]
        assert got["marks"] == [["MODEL", False], ["VENUE", False]] and got["fill"] == ["MODEL", ["MODEL", "VENUE"]]
    else:
        assert got["calls"] == ["venue_edge|straight|HOME"]
        assert [got["marked"], got["exempt"], got["repeated"]] == [1, 0, 1]
        assert got["marks"] == [["MODEL", True], ["VENUE", False]] and got["fill"] == ["VENUE", None]


def test_r7_matchfill_prefers_an_unmarked_call_straight_and_ladder_and_flags_only_the_chosen_group(tmp_path):
    """R7: "matchFill prefers an unmarked call of the same game and side". A marked claim and the closing's own
    executed call on one side: the fill goes to the unmarked call, with no tie flag, in either order; two unmarked
    calls are still a tie; a marked call alone keeps its fill. The ladder (composite NO) branch the same."""
    got = _node(tmp_path, r'''
const fx=(t,side)=>{ const p=parseTicker(t); return {...p,...sideFields(p,"",side)}; };
const NE={flag:"x"};
const M=T_mk("Denver",{id:"M",not_executed:NE}), U=T_mk("Denver",{id:"U",engine:"venue_edge",tier:"shadow"}),
  U2=T_mk("Denver",{id:"U2",engine:"venue_edge",tier:"x"});
const f=fx(TK,"yes"), m=(cs)=>{ const r=matchFill(f,cs,[]); return [r.call_id,r.ambiguous_calls||null]; };
const lad=(id,o)=>({...T_mk("Arsenal",{sport:"SOCCER",away:"Chelsea",game:"Chelsea @ Arsenal",three_way:true,
  call_type:"ladder",pick:"AWAY",units:0.5,...(o||{})}),id});
const g=fx("KXEPLGAME-26OCT19CHEARS-ARS","no"), ml=cs=>{ const r=matchFill(g,cs,[]); return [r.call_id,r.ambiguous_calls||null]; };
T_out({first:m([M,U]),second:m([U,M]),tie:m([U,U2]),alone:m([M]),
  ladder:[ml([lad("LM",{not_executed:NE}),lad("LU")]),ml([lad("LU"),lad("LM",{not_executed:NE})]),ml([lad("LM",{not_executed:NE})])],
  composite:g.composite});''', TK=DVDEN)
    assert got["first"] == ["U", None] and got["second"] == ["U", None]
    assert got["tie"] == ["U", ["U", "U2"]] and got["alone"] == ["M", None]
    assert got["composite"] is True and got["ladder"] == [["LU", None], ["LU", None], ["LM", None]]


# R7 x R2 (verify_ports #1): the timed tickers of the drift cases, and the calls (ledger_fills.match_fill takes the same,
# tests/test_closing_mark_ports.py)
DRIFT_MLB = "KXMLBGAME-26SEP291305NYYBOS-BOS"          # 13:05 ET = 17:05Z, YES on Boston (home)
DRIFT_EPL = "KXEPLGAME-26OCT191500CHEARS-ARS"          # 15:00 ET = 19:00Z, NO on Arsenal (home): an AWAY ladder's order


def test_r7_the_unmarked_call_of_the_same_game_takes_the_fill_when_kickoffs_drift_within_the_hour(tmp_path):
    """R7 under R2: "matchFill prefers an unmarked call of the same game and side", and R2 counts kickoffs within
    DESK_CLOCK_DRIFT (1 h, inclusive) as one game. The marked claim sits at the ticker's start (17:05Z) and the unmarked
    call 5 minutes later: the nearest start's group is all marked, so the unmarked call within the hour of it takes the
    fill, in either order; at exactly the hour too; past the hour it is another game and the marked call keeps the fill.
    Two unmarked calls within the hour are still a tie (flagged); the 3h doubleheader rule stands (an unmarked call
    within the hour of the marked one but past 3h of the ticker's start never takes it); the composite ladder branch
    the same."""
    got = _node(tmp_path, r'''
const B={log_date:"2026-09-29",sport:"MLB",game:"New York Yankees @ Boston Red Sox",home:"Boston Red Sox",
  away:"New York Yankees",status:"open",pick:"HOME",tier:"lean",call_type:"straight",units:1};
const NE={flag:"x"}, M={...B,id:"m",engine:"model_edge",kickoff:"2026-09-29T17:05:00",not_executed:NE};
const U=(k,id)=>({...B,id:id||"u",engine:"venue_edge",kickoff:k});
const F={id:"f",ticker:MLB,side:"yes",qty:3,entry:0.55,title:"Boston wins — New York Yankees"};
const run=calls=>{ const f=classifyFills({calls,fills:[F]})[0]; return [f.call_id,f.ambiguous_calls||null]; };
const both=k=>[run([M,U(k)]),run([U(k),M])];
const LB={log_date:"2026-10-19",sport:"SOCCER",game:"Chelsea @ Arsenal",home:"Arsenal",away:"Chelsea",three_way:true,
  status:"open",pick:"AWAY",tier:"lean",engine:"model_edge",call_type:"ladder",units:0.5};
const LM={...LB,id:"lm",kickoff:"2026-10-19T19:00:00",not_executed:NE}, LU={...LB,id:"lu",kickoff:"2026-10-19T19:15:00"};
const FL={id:"n",ticker:EPL,side:"no",qty:2,entry:0.5,title:"Arsenal wins — Chelsea"};
const lrun=calls=>{ const f=classifyFills({calls,fills:[FL]})[0]; return [f.call_id,f.ambiguous_calls||null,!!f.composite]; };
T_out({drift5:both("2026-09-29T17:10:00"),before:both("2026-09-29T16:05:00"),hour:both("2026-09-29T18:05:00"),
  past:both("2026-09-29T18:06:00"),same:both("2026-09-29T17:05:00"),
  tie:run([M,U("2026-09-29T17:10:00","u1"),U("2026-09-29T17:20:00","u2")]),
  far:run([{...M,kickoff:"2026-09-29T19:35:00"},U("2026-09-29T20:20:00")]),
  ladder:[lrun([LM,LU]),lrun([LU,LM]),lrun([LM])]});''', MLB=DRIFT_MLB, EPL=DRIFT_EPL)
    for k in ("drift5", "before", "hour", "same"):
        assert got[k] == [["u", None], ["u", None]], k
    assert got["past"] == [["m", None], ["m", None]]
    assert got["tie"] == ["u1", ["u1", "u2"]]
    assert got["far"] == ["m", None]
    assert got["ladder"] == [["lu", None, True], ["lu", None, True], ["lm", None, True]]


def test_r7_execute_now_and_record_fill_are_hidden_on_a_marked_call_and_every_leg_of_its_ticket(tmp_path):
    """R7: Execute now / Record fill hidden on a marked open call, and on every leg of a ticket with a marked leg
    (executeEarly and recordFill act on every open leg of a ticket); an unmarked call keeps both."""
    got = _node(tmp_path, r'''
const leg=home=>T_mk(home,{call_type:"parlay_leg",parlay_id:"P-2026-10-19-T",units:0.25,tier:"parlay"});
T_seed([T_mk("Denver"),T_mk("Buffalo"),leg("Denver"),leg("Albany")]);
storeClosings(T_pages(C,CN)); renderLedger();
const L=loadLedger(), h=document.getElementById("openList").innerHTML;
const ids=cls=>[...h.matchAll(new RegExp(`${cls}" data-id="([^"]+)"`,"g"))].map(x=>x[1]);
T_out({exec:ids("execBtn"),fill:ids("fillBtn"),buf:L.calls.find(c=>c.home==="Buffalo").id,
  locked:(h.match(/not executed \(#431\): no fill to record/g)||[]).length,marks:T_marks(L)});''', **_docs())
    assert got["exec"] == [got["buf"]] and got["fill"] == [got["buf"]] and got["locked"] == 3
    assert got["marks"] == {"Denver|straight|HOME": RUN, "Denver|parlay_leg|HOME": RUN}


# ------------------------------------------------------------------------------------------------- R8 and R9 --

def test_r8_a_closing_loaded_first_marks_a_slate_claimed_in_a_later_load_the_same_as_the_other_order(tmp_path):
    """R8: the page's calls are stored and the mark re-applied on every save, so it never depends on the order things
    loaded: the closing first, then the slate in a later load, marks what the slate-first order marks."""
    got = _node(tmp_path, r'''
await loadDocs([T_doc(SN,S)]); await loadDocs([T_doc(CN,C)]);
const a=T_marks(loadLedger()); T_reset();
await loadDocs([T_doc(CN,C)]); await loadDocs([T_doc(SN,S)]);
T_out({a,b:T_marks(loadLedger()),note:T_note()});''', **_docs())
    assert got["a"] == got["b"] == {"Miami|straight|HOME": RUN, "Dallas|straight|HOME": RUN,
                                    "Denver|straight|HOME": RUN}
    assert got["note"].endswith(" · NOT EXECUTED (#431): 3 claim(s) newly marked · 0 mark(s) cleared by the stored"
                                " closing pages")


def test_r8_an_import_is_covered_the_same_way(tmp_path):
    """R8: "an import is covered the same way": a ledger holding the closing page (meta.closings) imported into one
    that holds only the slate's claims marks them on the merge's save; the note says so."""
    got = _node(tmp_path, r'''
await loadDocs([T_doc(CN,C)]); const A=JSON.parse(T_stored()); T_reset();
await loadDocs([T_doc(SN,S)]); const none=T_marks(loadLedger());
importLedgerDoc(A);
T_out({none,marks:T_marks(loadLedger()),note:document.getElementById("ledgerNote").textContent});''', **_docs())
    assert got["none"] == {}
    assert got["marks"] == {"Miami|straight|HOME": RUN, "Dallas|straight|HOME": RUN, "Denver|straight|HOME": RUN}
    assert " · closings: 6 page game(s) taken (newer) · 0 kept · 3 claim(s) marked NOT EXECUTED after the merge" \
           in got["note"]
    got = _node(tmp_path, r'''
importLedgerDoc({calls:[],meta:{closings:{x:{family:"NFL"}}}});
T_out(document.getElementById("ledgerNote").textContent);''')
    assert got == ("Imported 0 calls: 0 new · 0 updated · 0 unchanged/kept (merged by key; graded entries never"
                   " downgraded) · closings: 0 page game(s) taken (newer) · 0 kept · 0 claim(s) marked NOT EXECUTED"
                   " after the merge · 1 closing record(s) or game(s) refused (not a closings record)")


def test_r9_a_later_page_clears_a_mark_it_repeats_and_an_older_page_never_overwrites(tmp_path):
    """R9: "a later page of the same start recomputes that start's marks, sets new ones and clears a mark it repeats;
    an older page never overwrites". The 16:40Z page calls Denver PLAY: its mark clears; loading the 16:25Z page
    again keeps every game of the later page."""
    later = closing(at=LATER_AT, run=RUN2, Denver=0.60)
    got = _node(tmp_path, r'''
await loadDocs([T_doc(SN,S)]); await loadDocs([T_doc(CN,C)]);
const m1=T_marks(loadLedger());
await loadDocs([T_doc("closing_NFL_2026-10-19T1700Z_b.json",C2)]);
const m2=T_marks(loadLedger()), n2=T_note();
await loadDocs([T_doc(CN,C)]);
const L=loadLedger();
T_out({m1,m2,n2,m3:T_marks(L),n3:T_note(),pages:Object.keys(L.meta.closings["NFL|2026-10-19T17:00:00Z"].pages)});''',
                C2=later, **_docs())
    assert got["m1"]["Denver|straight|HOME"] == RUN
    assert got["m2"] == {"Miami|straight|HOME": RUN2, "Dallas|straight|HOME": RUN2}
    assert " · 6 game(s) stored · 0 kept (the stored page is newer or the same) · 2 claim(s) marked NOT EXECUTED (the" \
           " page did not repeat them; 0 new, 1 cleared by a later page) · 4 repeated" in got["n2"]
    assert got["m3"] == got["m2"] and got["pages"] == [RUN2]
    assert " · 0 game(s) stored · 6 kept (the stored page is newer or the same)" in got["n3"]


def test_r9_two_runs_with_one_as_of_order_by_the_run_id_in_either_load_order(tmp_path):
    """R1/R9's order of two pages is desk_meta.as_of, then the run id ("%Y%m%dT%H%M%SZ-<chain>"): two runs of one start
    whose Desk read the same as_of, the later run calling Denver PLAY. Either load order ends with the later run's
    page stored for every game and Denver unmarked; the same run again is one page (0)."""
    later = closing(run=RUN_SAME_AS_OF, Denver=0.60)
    got = _node(tmp_path, r'''
const order=async(...ds)=>{ T_reset(); await loadDocs([T_doc(SN,S)]); for(const d of ds) await loadDocs([d]);
  const L=loadLedger(); return {marks:T_marks(L),pages:Object.keys(L.meta.closings["NFL|2026-10-19T17:00:00Z"].pages)}; };
const a=T_doc(CN,C), b=T_doc("closing_NFL_2026-10-19T1700Z_b.json",C2);
const pa=T_pages(C,CN)[0], pb=T_pages(C2,"b.json")[0];
T_out({ab:await order(a,b),ba:await order(b,a),cmp:[pageCmp(pb,pa),pageCmp(pa,pb),pageCmp(pa,{...pa}),pa.as_of===pb.as_of]});''',
                C2=later, **_docs())
    marks = {"Miami|straight|HOME": RUN_SAME_AS_OF, "Dallas|straight|HOME": RUN_SAME_AS_OF}
    assert got["ab"] == got["ba"] == {"marks": marks, "pages": [RUN_SAME_AS_OF]}
    assert got["cmp"] == [1, -1, 0, True]


def test_closing_pages_of_one_name_but_two_runs_in_one_load_stay_two_pages(tmp_path):
    """closingPages keys a page on its file, run and as_of (verify_cockpit #6): two runs of one start arriving under one
    file name in one load are two pages, and the newer one (16:40Z, Denver PLAY) stands for Denver whatever the
    order."""
    later = closing(at=LATER_AT, run=RUN2, Denver=0.60)
    got = _node(tmp_path, r'''
const res=[];
for(const ds of [[C2,C],[C,C2]]){ T_reset(); await loadDocs([T_doc(SN,S)]);
  const rr=ds.flatMap(d=>{ const r=normalize(d); stampClosing(r,d,CN); return r; }), pages=closingPages(rr);
  storeClosings(pages);
  res.push({n:pages.length,runs:pages.map(p=>p.run_id),den:Object.values(pages[0].games).find(g=>g.home==="Denver").run_id,
    marks:T_marks(loadLedger())}); }
T_out(res);''', C2=later, **_docs())
    marks = {"Miami|straight|HOME": RUN2, "Dallas|straight|HOME": RUN2}
    assert got == [{"n": 2, "runs": [RUN2, RUN], "den": RUN2, "marks": marks},
                   {"n": 2, "runs": [RUN, RUN2], "den": RUN, "marks": marks}]


def test_r9_on_import_a_call_follows_the_side_whose_stored_page_is_newer(tmp_path):
    """R9: on import, each call follows the side whose stored page for its start is newer, in either direction."""
    later = closing(at=LATER_AT, run=RUN2, Denver=0.60)
    got = _node(tmp_path, r'''
const build=async(...ds)=>{ T_reset(); for(const d of ds) await loadDocs([d]); return JSON.parse(T_stored()); };
const X=await build(T_doc(SN,S),T_doc(CN,C));
const Y=await build(T_doc(SN,S),T_doc(CN,C),T_doc("b.json",C2));
const into=(base,inc)=>{ localStorage.setItem(LEDGER_KEY,JSON.stringify(base)); importLedgerDoc(inc);
  return T_marks(loadLedger())["Denver|straight|HOME"]||null; };
const bare={...X,calls:X.calls.map(c=>unmarked(c))};      // the same calls, every mark set aside
const self=into(X,bare), selfNote=document.getElementById("ledgerNote").textContent;
T_out({x:T_marks(X)["Denver|straight|HOME"]||null,yIntoX:into(X,Y),xIntoY:into(Y,X),self,selfNote});''',
                C2=later, **_docs())
    assert {k: got[k] for k in ("x", "yIntoX", "xIntoY", "self")} == {"x": RUN, "yIntoX": None, "xIntoY": None,
                                                                    "self": RUN}
    # R8: a difference in the mark alone is no update; the stored page re-derives the mark on the save
    assert got["selfNote"].startswith("Imported 6 calls: 0 new · 0 updated · 6 unchanged/kept")


@pytest.mark.parametrize("mode", ["per_game", "whole_page"])
def test_r9_a_game_the_later_page_lacks_keeps_its_page_per_game_or_leaves_with_the_whole_page(tmp_path, mode):
    """esc 11: the 16:40Z page carries Denver alone (a PLAY now). "per_game": Miami and Dallas keep the 16:25Z page's
    entries and marks; "whole_page": the newer page stands for the whole start, so their marks clear."""
    later = closing(at=LATER_AT, run=RUN2, ids=[304], Denver=0.60)
    got = _node(tmp_path, r'''
T_rules({missingGame:MODE});
await loadDocs([T_doc(SN,S)]); await loadDocs([T_doc(CN,C)]); await loadDocs([T_doc("b.json",C2)]);
const L=loadLedger(), st=L.meta.closings["NFL|2026-10-19T17:00:00Z"];
T_out({marks:T_marks(L),games:Object.keys(st.games).length,pages:Object.keys(st.pages).sort()});''',
                MODE=mode, C2=later, **_docs())
    if mode == "per_game":
        assert got == {"marks": {"Miami|straight|HOME": RUN, "Dallas|straight|HOME": RUN}, "games": 6,
                       "pages": sorted([RUN, RUN2])}
    else:
        assert got == {"marks": {}, "games": 1, "pages": [RUN2]}


# ------------------------------------------------------------------------------------------------------- R10 --

def test_r10_a_marked_claim_leaves_settled_bets_the_sizing_gate_the_four_n30_counts_and_the_summary(tmp_path):
    """R10: "out of settledBets (the P&L, the counterfactuals, the Sizing gate N/50) and gradedCount (the four n/30
    counters, ledgerSummary.counts)"; graded_per_rule too. One marked and one unmarked graded call per counter."""
    got = _node(tmp_path, r'''
const NE={flag:"not executed (#431)",closing:{family:"NFL",start:"s",run_id:"R",as_of:"a",file:"f"},closing_call:{text:"PASS",calls:[]}};
const g=(home,o,ne)=>T_mk(home,{status:"graded",result:"win",units_returned:1.9,graded_date:"2026-10-19",...o,...(ne?{not_executed:NE}:{})});
const calls=[];
for(const ne of [false,true]){ const s=ne?"N":"U";
  calls.push(g("Post"+s,{stage:"postseason",rules:["ps "+s]},ne), g("Val"+s,{call_type:"value_shadow",units:0,shadow_units:0.25,shadow_returned:0.5,rules:["vs "+s]},ne),
    g("Ko"+s,{reference:"kalshi_only",rules:["ko "+s]},ne), g("Intl"+s,{sport:"INTL",rules:["intl "+s]},ne)); }
T_seed(calls);
const L=loadLedger(), bets=settledBets(L), ne={...lastNotExec}, sum=ledgerSummary();
renderLedger();
T_out({counts:[postseasonGraded(),valueShadowGraded(),kalshiOnlyGraded(),intlGraded()],sum:sum.counts,
  rules:Object.keys(sum.graded_per_rule).sort(),bets:bets.length,ne,
  gate:pnlBlock(L).split("\n").find(l=>l.startsWith("Sizing gate")),
  line:pnlBlock(L).split("\n").find(l=>l.startsWith("Not executed")),
  totals:document.getElementById("ledgerTotals").innerHTML,progress:document.getElementById("vsProgress").textContent});''')
    assert got["counts"] == [1, 1, 1, 1]
    assert got["sum"] == {"postseason_graded": 1, "value_shadow_graded": 1, "kalshi_only_graded": 1, "intl_graded": 1}
    assert got["rules"] == ["intl U", "ko U", "ps U", "vs U"]
    assert got["bets"] == 4 and got["ne"] == {"positions": 4, "tickets": 0, "voidLeg": 0}
    assert got["gate"] == "Sizing gate: model_edge 3/50 · venue_edge 0/50 graded before any sizing proposal"
    assert got["line"].startswith("Not executed (addendum 40 item 2, #431): 4 claim(s) the closing page did not repeat"
                                  " (4 position(s), 0 ticket(s) settled)")
    assert f'<div class="caution" id="notExecLine">⚠ {got["line"].replace("&", "&amp;")}</div>' in got["totals"]
    assert "<b>3</b> settled bets" in got["totals"] and got["progress"] == "graded 1/30"   # the value shadow: not real


def test_a_marked_call_later_voided_as_re_dated_is_listed_void_only_and_its_ticket_stays_locked(tmp_path):
    """markClosings leaves a void_redated call as it is, so a call marked and then re-dated keeps its mark. The NOT
    EXECUTED count (the P&L line) and the #notExecuted list leave it out, as k_receipt.not_executed_calls and
    value_shadow_receipt do (verify_ports #2): it is listed void only. The ticket lock (no Execute now / Record fill on a
    ticket with a marked leg) is unchanged."""
    got = _node(tmp_path, r'''
const NE={flag:"not executed (#431)",closing:{family:"NFL",start:"2026-10-19T17:00:00Z",run_id:"R",as_of:"2026-10-19T16:25:00Z",
  file:"f"},closing_call:{text:"PASS",calls:[]}};
const V="void: re-dated 2026-10-19 17:00Z → 2026-10-20 17:00Z";
const leg=(home,o)=>T_mk(home,{call_type:"parlay_leg",parlay_id:"P-2026-10-19-T",units:0.25,tier:"parlay",...(o||{})});
T_seed([T_mk("Denver",{not_executed:NE}),T_mk("Buffalo",{status:"void",void_redated:V,not_executed:NE}),
  leg("Miami",{status:"void",void_redated:V,not_executed:NE}),leg("Albany")]);
renderLedger(); const L=loadLedger(); settledBets(L);
const h=document.getElementById("openList").innerHTML;
T_out({line:notExecutedLine(L),list:(h.match(/<div class="note" id="notExecuted">.*?<\/div>/)||[""])[0],
  albany:L.calls.find(c=>c.home==="Albany").id,fill:[...h.matchAll(/fillBtn" data-id="([^"]+)"/g)].map(x=>x[1]),
  locked:(h.match(/not executed \(#431\): no fill to record/g)||[]).length,marks:L.calls.filter(c=>c.not_executed).length});''')
    assert got["marks"] == 3                                    # nothing is deleted: the void calls keep their marks
    assert got["line"].startswith("Not executed (addendum 40 item 2, #431): 1 claim(s) the closing page did not repeat")
    assert got["list"].startswith('<div class="note" id="notExecuted"><b>1 claim(s) not executed</b>')
    assert "Denver Visitors @ Denver" in got["list"] and "Buffalo" not in got["list"] and "Miami" not in got["list"]
    assert got["locked"] == 2 and got["albany"] not in got["fill"]     # Denver and the ticket's open leg, as before


def test_a_settled_ticket_held_out_only_by_a_void_marked_leg_is_named_on_the_line(tmp_path):
    """A ticket whose only marked leg was later re-dated (void) stays out of the P&L (R5) while the void leg is listed
    void only; the NOT EXECUTED line names the held-out ticket instead of reading "0 claim(s) ... 1 ticket(s) settled"
    with nothing beside it (reverify P3 #2)."""
    got = _node(tmp_path, r'''
const NE={flag:"not executed (#431)",closing:{family:"NFL",start:"2026-10-19T17:00:00Z",run_id:"R",as_of:"2026-10-19T16:25:00Z",
  file:"f"},closing_call:{text:"PASS",calls:[]}};
const V="void: re-dated 2026-10-19 17:00Z → 2026-10-20 17:00Z";
const leg=(home,o)=>T_mk(home,{call_type:"parlay_leg",parlay_id:"P-2026-10-19-T",units:0.25,tier:"parlay",...(o||{})});
T_seed([leg("Miami",{status:"void",void_redated:V,not_executed:NE,ticket_result:"win",units_returned:0.6}),
  leg("Albany",{status:"graded",result:"win",ticket_result:"win",units_returned:0.6,graded_date:"2026-10-19"})]);
const L=loadLedger(), bets=settledBets(L);
T_out({bets:bets.length,ne:{...lastNotExec},line:notExecutedLine(L)});''')
    assert got["bets"] == 0 and got["ne"] == {"positions": 0, "tickets": 1, "voidLeg": 1}
    assert got["line"].startswith("Not executed (addendum 40 item 2, #431): 0 claim(s) the closing page did not repeat"
                                  " (0 position(s), 1 ticket(s) settled)")
    assert got["line"].endswith(" · 1 ticket(s) held out by a leg marked before it was re-dated (void)")


def test_r10_executed_positions_and_clv_lines_keep_a_marked_call(tmp_path):
    """R10: "kept in executedPositions and clvLines, the claim-against-close read, as the ruling's own words keep it":
    a marked graded call with a close and a matched Kalshi fill stays an executed position."""
    got = _node(tmp_path, r'''
const NE={flag:"not executed (#431)",closing:{family:"NFL",start:"s",run_id:"R",as_of:"a",file:"f"},closing_call:{text:"PASS",calls:[]}};
const c=T_mk("Denver",{status:"graded",result:"win",units_returned:1.9,graded_date:"2026-10-19",not_executed:NE,
  close_ref:{version:"p0-3 v2",q_close:0.55,fair:{HOME:0.55,AWAY:0.45},close_at:null,close_source:"x",ref_move_claim:0.03,
  ref_move_relog:0.03,quoted_edge_relog:null}});
T_seed([c]); const L=loadLedger(); L.fills=[{id:"F1",ticker:TK,side:"yes",qty:10,entry:0.5,title:"",open_fee:0.02}];
const ep=executedPositions(L);
T_out({pos:ep.pos.map(p=>p.c.id),mine:c.id,line:clvLines(L).find(l=>/graded call\(s\) with a close/.test(l))});''',
                TK=DVDEN)
    assert got["pos"] == [got["mine"]]
    assert got["line"].startswith("  1 graded call(s) with a close · 1 executed (matched fill) · 0 without matched")


# ------------------------------------------------------------------------------------------------------- R11 --

def test_r11_loaddocs_stamps_in_the_loop_takes_the_pages_before_policy_and_marks_after_autoclaim():
    """R11: automatic on load, after autoClaim. The rows are stamped in the loop (after the F1c refusal, before they
    join `rows`); ticketRows and the pages are taken after the loop, then the dedupe (COMMIT 2, R1: so #183 reads the
    ticket's own file and every page is stored), all before policy() and autoClaim(); the pages are stored (and the
    marks re-derived) after autoClaim; did.closings is set after the literal; the four returns and the two refused
    copies stand (tests/test_cockpit_today.py)."""
    body = _fn(_html(), "loadDocs")
    refuse, stamp, concat = (body.index("if(rr.some(r=>!r.fileDesk)){ refusedFiles.push(f.name); continue; }"),
                             body.index("stampClosing(rr,doc,f.name);"), body.index("rows=rows.concat(rr);"))
    assert refuse < stamp < concat
    tr, cp, dd, lab, pol, ac, st, note = (body.index("ticketRows=slateRows(rows);"),
                                          body.index("const cpages=closingPages(rows);"),
                                          body.index("const cd=closingDedupe(rows); rows=cd.rows;"),
                                          body.index("sportLabel="), body.index("policy();"),
                                          body.index("const ac=autoClaim();"),
                                          body.index("const ne=storeClosings(cpages);"),
                                          body.index('$("logNote").textContent=loadLogNote(ac,ne);'))
    assert concat < tr < cp < dd < lab < pol < ac < st < note
    assert body.count("closingDedupe(") == 1 and body.count("closingPages(") == 1
    assert "rows=[]; shadowRows=[]; fileParlays=null; refusedFiles=[]; ticketRows=[]; closingLoad=null;" in body
    assert dd < body.index("closingLoad={files:cd.files,superseded:cd.superseded,partly:cd.partly,copies:cd.copies,"
                           "slateRowsDropped:cd.slateRowsDropped};") < lab
    assert "did.closings" not in body[:body.index("\n", body.index("const did="))] and body.index("did.closings") > st
    assert "did.closings={...closingLoad,marks:ne};" in body
    assert re.findall(r"return[^;]*;", body) == ["return did;"] * 4
    assert body.count("did.refused=refusedFiles.slice();") == 2
    assert "if(ac||ne){" in body


def test_r11_with_no_closing_the_load_note_is_the_auto_claim_note_as_it_was_and_a_null_autoclaim_is_guarded(tmp_path):
    """No closing loaded: the note is byte for byte today's (scripts/cockpit_autoclaim_verify.py pins "Auto-claimed
    ..."), did.closings.marks is null. autoClaim returns null when the load holds no desk call: the closing segment
    then leads the note."""
    got = _node(tmp_path, r'''
const d1=await loadDocs([T_doc(SN,S)]); const n1=T_note();
await loadDocs([T_doc(SN,S)]); const n2=T_note();
T_reset(); const ne=storeClosings(T_pages(C,CN));
T_out({n1,n2,marks:d1.closings.marks,lead:loadLogNote(null,ne)});''', **_docs())
    tail = " · 0 past kickoff at as_of (not claimed). \"Re-log at T-60\" refreshes prices."
    assert got["n1"] == ("Auto-claimed 6 call(s) at their file's as_of — 6 new · 0 position(s) repriced · 0 already claimed"
                         " from this file · 0 older than the ledger (kept)" + tail)
    assert got["n2"] == ("Auto-claimed 0 call(s) at their file's as_of — 0 new · 0 position(s) repriced · 6 already claimed"
                         " from this file · 0 older than the ledger (kept)" + tail)
    assert got["marks"] is None
    assert got["lead"].startswith("closing: 1 page(s) read · 6 game(s) stored · 0 kept")


# ------------------------------------------------------------------------------------------------------- R12 --

def test_r12_the_not_executed_check_runs_before_183s_and_183_reads_the_file_that_built_the_ticket():
    html = _html()
    sb = _fn(html, "settledBets")
    assert sb.index("if(all.some(l=>l.not_executed)){lastNotExec.tickets++; if(all.every(l=>!l.not_executed||l.void_redated))") \
        < sb.index('l.leg_check.status==="not_play"')
    assert sb.index("if(c.not_executed){lastNotExec.positions++; continue;}") < sb.index("const a=auditCall(c); tally(a);")
    assert "legAuditCalls()" in _fn(html, "auditParlayLegs") and "deskCalls" not in _fn(html, "auditParlayLegs")
    assert "ticketRows.find(" in _fn(html, "parlaysFromFile") and "rows.find(" not in \
        _fn(html, "parlaysFromFile").replace("ticketRows.find(", "")
    assert '$("ledgerNote").textContent=legAuditCalls().length?auditParlayLegs()' in html
    assert "lastNotExec" not in _fn(html, "auditLine")         # the kickoff audit's line and lastAudit's keys unchanged
    assert "let lastAudit={flagged:0,fallback:0,excluded:0,legNotPlay:0};" in html


def test_r12_183_checks_a_leg_against_the_slate_not_the_closing_and_a_marked_ticket_is_not_a_183_exclusion(tmp_path):
    """R12: "#183 keeps reading the file that built the ticket". With the slate (Denver PLAY) and its closing (Denver
    PASS) in one load, the Denver leg is checked against the slate's call, a play; the ticket, its Denver leg marked,
    leaves the P&L as not executed, not as a #183 exclusion."""
    got = _node(tmp_path, r'''
const leg=home=>T_mk(home,{call_type:"parlay_leg",parlay_id:"P-2026-10-19-T",units:0.25,tier:"parlay",status:"graded",
  result:"win",ticket_result:"win",units_returned:1,graded_date:"2026-10-20"});
T_seed([leg("Denver"),leg("Albany")]);
await loadDocs([T_doc(SN,S),T_doc(CN,C)]);
auditParlayLegs(); const L=loadLedger(); settledBets(L);
T_out({check:L.calls.filter(c=>c.call_type==="parlay_leg").map(c=>[c.home,c.leg_check?c.leg_check.status:null]),
  ne:{...lastNotExec},audit:{...lastAudit},legRows:legAuditCalls().map(x=>x.r.closing?"closing":"slate")});''',
                **_docs())
    assert got["check"] == [["Denver", "play"], ["Albany", None]]
    assert got["ne"] == {"positions": 0, "tickets": 1, "voidLeg": 0}
    assert got["audit"] == {"flagged": 0, "fallback": 0, "excluded": 0, "legNotPlay": 0}   # lastAudit's four keys only
    assert set(got["legRows"]) == {"slate"}


# ------------------------------------------------------------------------------------------------------- R14 --

def test_r14_a_covered_game_with_no_earlier_claim_is_named_with_the_warning_when_a_slate_of_the_load_called_it(tmp_path):
    """R14 (a): "the control's note when the ledger has no claim on a covered game, and the runbook line "import the
    ledger, then load"". The closing loaded first claims Buffalo and the two shadows at its own as_of; the slate and the
    closing loaded together then claim nothing from the slate (COMMIT 2, R1: the closing file's row stands over the
    slate row of each of its games, so no slate row of a covered game reaches the Desk): all six covered games hold no
    claim from before their page, and a slate row of this load called each (⚠: ticketRows is taken before the
    dedupe). A closing whose counts_source is the ledger summary's prints no 144 note."""
    summary = closing(src="ledger summary bd_ledger_summary.json generated 2026-10-19T10:00:00Z")
    got = _node(tmp_path, r'''
await loadDocs([T_doc(CN,C)]);
await loadDocs([T_doc(SN,S),T_doc(CN,C)]);
const n=T_note(); T_reset();
await loadDocs([T_doc(CN,C3)]);
T_out({n,n3:T_note()});''', C3=summary, **_docs())
    assert got["n"].endswith(" · ⚠ 6 of 6 covered game(s) hold no claim from before their page in this browser's ledger:"
                             " nothing there to mark. A local Cockpit keeps its own ledger: import the ledger, then load."
                             + COUNTS_NOTE)
    assert "counts_source" not in got["n3"] and got["n3"].endswith("import the ledger, then load.")


def test_r14_the_runbook_names_the_order_and_the_version_skew_line():
    doc = " ".join((ROOT / "docs" / "specs" / "exports-mirror.md").read_text(encoding="utf-8").split())
    assert "**Closings: import the ledger, then load (#431, ARCHITECT 2026-10-20, addendum 145 item 3(b) R14).**" in doc
    # COMMIT 2: the paragraph names the control it now has ("import the ledger, then load the closings with Load
    # closings + latest from laptop"), the folders it reads as the mirror writes them, and R1 verbatim
    assert ("A closing file loaded into the Cockpit (the file picker, Load latest from host, or Load closings + latest"
            " from laptop) marks NOT EXECUTED the claims its page did not repeat") in doc
    assert ("In the local page, import the ledger, then load the closings with Load closings + latest from laptop: first"
            " Import ledger (the published page's Export ledger (JSON)), then press the control.") in doc
    assert ("`laptop/latest/*.json`, the newest file of every kind (its `closing_<FAMILY>.json` is a copy of a dated"
            " file and is not fetched), and the `closing_*.json` files of `laptop/<yesterday UTC>` and"
            " `laptop/<today UTC>` (a dated folder is the file's UTC mtime day") in doc
    assert ('R1: "the closing file\'s row stands over any slate row for its games; among pages of one family and start'
            ' the newest desk_meta.as_of wins. A rule by kind, never by the listing\'s order."') in doc
    assert "the load note, and the control's note, say how many covered games hold no claim from before their page" in doc
    # COMMIT 2 fix round: the parse stop, the standing-row rule, the partly superseded count and the order-free store
    assert ('a file that does not parse stops the load there, and the note says "load stopped" with the parse message,'
            ' never "Loaded"') in doc
    assert ("a slate row leaves only against a closing row that stands; the Desk summary says how many slate rows were"
            " replaced, how many files a later page superseded (no row of theirs stands) and how many it partly"
            " superseded (some games stand)") in doc
    assert ("A copy of a page listed under two names is read once under its smallest name, and the pages are stored"
            " newest first, so no listing order decides which row stands, the notes, or the stored pages and their"
            " marks.") in doc
    assert '"Load latest from host" fails ("Fetch failed"), and so does "Load closings + latest from laptop"' in doc
    assert ("Until the published page carries this build, do not import a ledger exported from the local page into the"
            " published page.") in doc
    spec = " ".join((ROOT / "docs" / "specs" / "cockpit-v04-pnl-organ.md").read_text(encoding="utf-8").split())
    assert "Idempotency: keyed on (sport, game, log_date) — re-logging updates, never duplicates." in spec   # verbatim
    assert "is (sport, game, log_date, engine, call_type, pick, parlay slot); the pick joined it by ARCHITECT" \
           " 2026-10-20, addendum 145 item 3(b) R4" in spec


# ================================================================================ COMMIT 2: the dedupe and the control --
# R1 (ARCHITECT 2026-10-20, addendum 145 item 3(b), verbatim): "the closing file's row stands over any slate row for its
# games; among pages of one family and start the newest desk_meta.as_of wins. A rule by kind, never by the listing's
# order." R2 for rows: same sport, home and away, kickoffs within DESK_CLOCK_DRIFT (1 h). R14: "the control's note when
# the ledger has no claim on a covered game, and the runbook line "import the ledger, then load"".

SUMMARY_SLATE = ("NFL · 6 rows → 4 play · 0 ladder · 2 pass (0 no reference · 1 below floor · 1 other) · 1 value shadow"
                 " (not staked) · desk: rendered from file (as of 2026-10-19T12:00:00Z)")
DEDUPE_NOTE = " · closing: 1 file(s) (NFL 2026-10-19T17:00:00Z) · 6 slate row(s) replaced by their closing row · 0 superseded by a later page"


def slate_moved():
    """The morning slate with Buffalo's Kalshi quote at 0.50/0.51 (its closing page quotes 0.54/0.55): two exec prices."""
    rows = _nfl(Denver=0.60)
    rows[0] = row(301, "Buffalo", 0.62, fair_h=0.55, bid=0.50, ask=0.51, comp="NFL", series="KXNFLGAME", now=CLOSE_AT,
                  minutes=35)
    return _annotate(rows, SLATE_AT)


def test_r1_the_closing_row_stands_over_the_slate_row_and_its_exec_price_wins_in_either_file_order(tmp_path):
    """The Codex P1 of the original declaration: with the slate and its closing in one load, the closing exec price wins
    over the slate's in EITHER listing order, and the Desk holds one row per game. Both orders end with the same rows
    (every one the closing page's), the same Desk summary and a byte-identical stored ledger; Buffalo's claim carries
    the closing page's exec cost, never the slate's. The slate rows stay in ticketRows (R12)."""
    got = _node(tmp_path, r'''
const run=async(...ds)=>{ T_reset(); const did=await loadDocs(ds), L=loadLedger();
  const buf=L.calls.find(c=>c.home==="Buffalo"&&c.call_type==="straight");
  return {n:rows.length,closing:rows.every(r=>r.closing&&r.closing.file===CN),games:rows.map(r=>r.home),
    exec:rows.find(r=>r.home==="Buffalo").fileDesk.exec.cost,desk:deskCalls.length,bufK:buf.claim_exec_cost,
    bufAt:buf.claim_at,tickets:ticketRows.map(r=>r.closing?"closing":"slate"),
    summary:document.getElementById("summary").textContent,
    closings:{files:did.closings.files,superseded:did.closings.superseded,copies:did.closings.copies,
      slateRowsDropped:did.closings.slateRowsDropped},stored:T_stored()}; };
const a=await run(T_doc(SN,M),T_doc(CN,C)), b=await run(T_doc(CN,C),T_doc(SN,M));
const k=d=>normalize(d).find(r=>r.home==="Buffalo").fileDesk.exec.cost;
T_out({a,b,closingK:k(C),slateK:k(M)});''', M=slate_moved(), **_docs())
    a, b = got["a"], got["b"]
    assert got["closingK"] != got["slateK"]
    for x in (a, b):
        assert x["n"] == x["desk"] == 6 and x["closing"] is True
        assert sorted(x["games"]) == ["Buffalo", "Dallas", "Denver", "Miami", "Newark", "Tampa"]
        assert x["exec"] == x["bufK"] == got["closingK"] and x["bufAt"] == "2026-10-19T16:25:00.000Z"
        assert x["tickets"] == ["slate"] * 6
        assert x["closings"] == {"files": [{"file": CLOSING_NAME, "family": "NFL", "start": "2026-10-19T17:00:00Z",
                                            "run_id": RUN, "as_of": "2026-10-19T16:25:00Z"}],
                                 "superseded": [], "copies": 0, "slateRowsDropped": 6}
    assert a["summary"] == b["summary"] and a["summary"].endswith(
        " · desk: rendered from file (as of 2026-10-19T16:25:00Z)" + DEDUPE_NOTE)
    assert a["games"] == b["games"] and a["stored"] == b["stored"]


def test_r1_uncovered_slate_rows_stay_a_byte_copy_is_one_page_and_the_note_follows_the_refusals(tmp_path):
    """A closing page carrying Buffalo and Denver only: those two slate rows leave, the other four stay. The same page
    under two names is one page (counted once, its rows once). The Desk summary's closing line follows the refusals'."""
    two = closing(ids=[301, 304])
    got = _node(tmp_path, r'''
await loadDocs([T_doc(SN,S),T_doc(CN,C2)]);
const one={rows:rows.map(r=>[r.home,r.closing?"closing":"slate"]),summary:document.getElementById("summary").textContent};
const LEG={...S,predictions:S.predictions.map(p=>{ const {desk,...x}=p; return x; })};
const did=await loadDocs([T_doc("legacy.json",LEG),T_doc(SN,S),T_doc(CN,C),T_doc("copy_"+CN,C)]);
T_out({one,rows:rows.length,from:[...new Set(rows.map(r=>r.closing.file))],copies:did.closings.copies,
  files:did.closings.files.length,summary:document.getElementById("summary").textContent});''', C2=two, **_docs())
    assert got["one"]["rows"] == [["Miami", "slate"], ["Dallas", "slate"], ["Newark", "slate"], ["Tampa", "slate"],
                                  ["Buffalo", "closing"], ["Denver", "closing"]]
    assert got["one"]["summary"].endswith(" · closing: 1 file(s) (NFL 2026-10-19T17:00:00Z) · 2 slate row(s) replaced by"
                                          " their closing row · 0 superseded by a later page")
    assert got["rows"] == 6 and got["from"] == [CLOSING_NAME] and got["copies"] == 1 and got["files"] == 1
    assert got["summary"].endswith(" · ⚠ REFUSED 1 file(s) without desk blocks (legacy.json) — export with --desk"
                                   + DEDUPE_NOTE + " · 1 copy(ies) of a page read once")


@pytest.mark.parametrize("order", ["older_first", "newer_first"])
def test_r1_among_pages_of_one_game_the_newest_page_stands_and_the_older_is_superseded(tmp_path, order):
    """Two pages of one start in one load (16:25Z, then 16:40Z calling Denver PLAY): every game's row is the 16:40Z
    page's, whichever file is listed first; the 16:25Z file is named superseded; the stored page is the newer."""
    later = closing(at=LATER_AT, run=RUN2, Denver=0.60)
    got = _node(tmp_path, r'''
const a=T_doc(CN,C), b=T_doc("closing_b.json",C2);
const did=await loadDocs([T_doc(SN,S),...(ORDER==="older_first"?[a,b]:[b,a])]);
T_out({runs:[...new Set(rows.map(r=>r.closing.run_id))],n:rows.length,sup:did.closings.superseded,
  files:did.closings.files.map(f=>f.run_id),summary:document.getElementById("summary").textContent,
  den:rows.find(r=>r.home==="Denver").fileDesk.call,marks:T_marks(loadLedger())});''', ORDER=order, C2=later,
                **_docs())
    assert got["runs"] == [RUN2] and got["n"] == 6 and got["sup"] == [CLOSING_NAME] and got["den"] == "PLAY"
    assert sorted(got["files"]) == sorted([RUN, RUN2])
    assert got["summary"].endswith(" · closing: 2 file(s) (NFL 2026-10-19T17:00:00Z) · 6 slate row(s) replaced by"
                                   " their closing row · 1 superseded by a later page")
    assert got["marks"] == {}           # nothing claimed before either page in this ledger (the slate rows left)


@pytest.mark.parametrize("mode", ["per_game", "whole_page"])
def test_r1_a_game_the_later_page_lacks_follows_esc11_on_the_desk_as_in_the_ledger(tmp_path, mode):
    """esc 11, read once (wholePageStands) for the Desk and the ledger. The 16:40Z page carries Denver alone. "per_game":
    Denver's row is the later page's and the other five games keep the 16:25Z page's rows; "whole_page": the later page
    stands for the start, so the other five games are no page's and their slate rows stay. The stored pages agree.
    P3-4: "superseded" counts only a file no row of which stands; per_game leaves 5 of the 16:25Z page's 6 rows standing,
    so it is named "partly superseded (some games stand)"; whole_page leaves none, so it is superseded."""
    later = closing(at=LATER_AT, run=RUN2, ids=[304], Denver=0.60)
    got = _node(tmp_path, r'''
T_rules({missingGame:MODE});
const did=await loadDocs([T_doc(SN,S),T_doc("closing_b.json",C2),T_doc(CN,C)]);
const st=loadLedger().meta.closings["NFL|2026-10-19T17:00:00Z"];
T_out({rows:rows.map(r=>[r.home,r.closing?r.closing.run_id:"slate"]).sort(),sup:did.closings.superseded,
  partly:did.closings.partly,dropped:did.closings.slateRowsDropped,
  stored:Object.values(st.games).map(g=>[g.home,g.run_id]).sort(),summary:document.getElementById("summary").textContent});''',
                MODE=mode, C2=later, **_docs())
    head = " · closing: 2 file(s) (NFL 2026-10-19T17:00:00Z) · "
    if mode == "per_game":
        want = sorted([["Buffalo", RUN], ["Miami", RUN], ["Dallas", RUN], ["Denver", RUN2], ["Newark", RUN],
                       ["Tampa", RUN]])
        assert {k: v for k, v in got.items() if k != "summary"} == {"rows": want, "sup": [], "partly": [CLOSING_NAME],
                                                                    "dropped": 6, "stored": want}
        assert got["summary"].endswith(head + "6 slate row(s) replaced by their closing row · 0 superseded by a later"
                                       " page · 1 partly superseded (some games stand)")
    else:
        assert got["rows"] == sorted([["Buffalo", "slate"], ["Miami", "slate"], ["Dallas", "slate"], ["Denver", RUN2],
                                      ["Newark", "slate"], ["Tampa", "slate"]])
        assert got["sup"] == [CLOSING_NAME] and got["partly"] == [] and got["dropped"] == 1
        assert got["stored"] == [["Denver", RUN2]]
        assert got["summary"].endswith(head + "1 slate row(s) replaced by their closing row · 1 superseded by a later"
                                       " page")


# The dedupe on synthetic rows (pure): {sport, home, away, utc, closing}
DEDUPE_JS = r'''
const R=(id,utc,cl,o)=>({id,sport:"NFL",home:"Denver",away:"Denver Visitors",utc,closing:cl||null,...(o||{})});
const P=(file,as_of,run_id,start)=>({family:"NFL",start:start||"2026-10-19T17:00:00Z",run_id,as_of,file});
const K=res=>res.rows.map(r=>r.id);
'''


def test_r2_for_rows_a_closing_row_covers_a_slate_row_within_the_hour_and_not_beyond(tmp_path):
    """R2 for rows: a slate row whose kickoff is within the hour of a closing row's (inclusive) is the same game and
    leaves; beyond the hour, or another sport, home or away, or no kickoff at all, it stays (law 4: never guessed). Two
    closing rows of one game an hour apart: the newer page's stands; beyond the hour both stand (two games)."""
    got = _node(tmp_path, DEDUPE_JS + r'''
const p1=P("c1.json","2026-10-19T16:25:00Z","r1");
const slate=[R("s18",  "2026-10-19T18:00:00"),R("s16",  "2026-10-19T16:00:00"),R("s1801","2026-10-19T18:01:00"),
  R("s1559","2026-10-19T15:59:00"),R("sNHL","2026-10-19T17:00:00",null,{sport:"NHL"}),
  R("sAway","2026-10-19T17:00:00",null,{away:"Other"}),R("sNone","")];
const a=closingDedupe([...slate,R("c","2026-10-19T17:00:00",p1)]);
const p2=P("c2.json","2026-10-19T16:40:00Z","r2","2026-10-19T17:40:00Z");
const b=closingDedupe([R("c1","2026-10-19T17:00:00",p1),R("c2","2026-10-19T18:00:00",p2)]);
const c=closingDedupe([R("c1","2026-10-19T17:00:00",p1),R("c2","2026-10-19T18:01:00",p2)]);
T_out({a:K(a),dropped:a.slateRowsDropped,b:K(b),bsup:b.superseded,c:K(c),csup:c.superseded});''')
    assert got == {"a": ["s1801", "s1559", "sNHL", "sAway", "sNone", "c"], "dropped": 2,
                   "b": ["c2"], "bsup": ["c1.json"], "c": ["c1", "c2"], "csup": []}


def test_r1_a_rule_by_kind_never_by_the_listings_order_every_permutation_keeps_the_same_rows(tmp_path):
    """"A rule by kind, never by the listing's order": every order of two slate rows, two pages of one game, a byte copy
    of the newer page and an uncovered slate row keeps the same rows and says the same counts. A copy (one page) keeps
    ONE name, its smallest (P3-1): the standing row is c2.json's in every order, never c2copy.json's, and the pages
    read are named and ordered alike (newest first, then the name)."""
    got = _node(tmp_path, DEDUPE_JS + r'''
const p1=P("c1.json","2026-10-19T16:25:00Z","r1"), p2=P("c2.json","2026-10-19T16:40:00Z","r2"), p2c=P("c2copy.json","2026-10-19T16:40:00Z","r2");
const base=[R("s1","2026-10-19T17:00:00"),R("s2","2026-10-19T17:30:00"),R("c1","2026-10-19T17:00:00",p1),
  R("c2","2026-10-19T17:00:00",p2),R("c2copy","2026-10-19T17:00:00",p2c),R("far","2026-10-20T17:00:00")];
const perms=a=>a.length<2?[a]:a.flatMap((x,i)=>perms([...a.slice(0,i),...a.slice(i+1)]).map(p=>[x,...p]));
const seen=new Set();
for(const order of perms(base)){ const r=closingDedupe(order);
  seen.add(JSON.stringify([K(r).sort(),r.files.map(f=>f.file),r.superseded,r.partly,r.copies,r.slateRowsDropped,
    closingNote(r)])); }
T_out({n:perms(base).length,seen:[...seen]});''')
    assert got["n"] == 720
    assert got["seen"] == [json.dumps([["c2", "far"], ["c2.json", "c1.json"], ["c1.json"], [], 1, 2,
                                       " · closing: 2 file(s) (NFL 2026-10-19T17:00:00Z) · 2 slate row(s) replaced by"
                                       " their closing row · 1 superseded by a later page · 1 copy(ies) of a page read"
                                       " once"], separators=(",", ":"), ensure_ascii=False)]


def test_r1_a_slate_row_leaves_only_against_a_standing_closing_row_never_a_superseded_one(tmp_path):
    """P3-2: a kickoff that moved between two pages of one start. The 16:25Z page has the game at 17:50, the 16:40Z page
    at 17:00: one game (50 minutes apart), the newer page's row stands. A slate row at 18:30 is within the hour of the
    superseded 17:50 row only: it stays on the Desk (the ledger, which stores only the newer page's 17:00 entry, does
    not cover it either); a slate row at 17:30 is within the hour of the standing row and leaves. Either order."""
    got = _node(tmp_path, DEDUPE_JS + r'''
const p1=P("c1.json","2026-10-19T16:25:00Z","r1"), p2=P("c2.json","2026-10-19T16:40:00Z","r2");
const base=[R("s1830","2026-10-19T18:30:00"),R("s1730","2026-10-19T17:30:00"),R("c1750","2026-10-19T17:50:00",p1),
  R("c1700","2026-10-19T17:00:00",p2)];
T_out([base,[...base].reverse()].map(o=>{ const r=closingDedupe(o);
  return {rows:K(r).sort(),dropped:r.slateRowsDropped,sup:r.superseded,partly:r.partly}; }));''')
    want = {"rows": ["c1700", "s1830"], "dropped": 1, "sup": ["c1.json"], "partly": []}
    assert got == [want, want]


def test_r1_a_kickoff_moved_twice_leaves_the_desk_the_games_the_ledger_stores(tmp_path):
    """Re-verify P3: three pages of one start move one game's kickoff twice (18:30, then 17:50, then 17:00): each pair
    of neighbours within the hour, the first and last 90 minutes apart. Taken newest first (pageOrder), as storeClosings
    stores them, the 17:00 row stands, the 17:50 row is its game and leaves, and the 18:30 row (not within the hour of
    the standing 17:00 row) stands too: the Desk keeps the rows the ledger stores, in any listing order."""
    got = _node(tmp_path, DEDUPE_JS + r'''
const p1=P("c1.json","2026-10-19T16:05:00Z","r1"), p2=P("c2.json","2026-10-19T16:15:00Z","r2"),
  p3=P("c3.json","2026-10-19T16:25:00Z","r3");
const base=[R("c1830","2026-10-19T18:30:00",p1),R("c1750","2026-10-19T17:50:00",p2),R("c1700","2026-10-19T17:00:00",p3)];
const orders=[base,[...base].reverse(),[base[1],base[0],base[2]]];
const G=(run,ko)=>({sport:"NFL",home:"Denver",away:"Denver Visitors",kickoff:ko,calls:[],text:"PASS",run_id:run});
const page=(p,ko)=>({family:"NFL",start:p.start,run_id:p.run_id,as_of:p.as_of,file:p.file,desk_meta:{},
  games:{["NFL|Denver|Denver Visitors|"+ko]:{...G(p.run_id,ko),as_of:p.as_of,file:p.file}}});
T_reset(); T_seed([]); storeClosings([page(p1,"2026-10-19T18:30:00"),page(p2,"2026-10-19T17:50:00"),
  page(p3,"2026-10-19T17:00:00")]);
const stored=Object.values(loadLedger().meta.closings["NFL|2026-10-19T17:00:00Z"].games).map(g=>g.kickoff.slice(11,16)).sort();
T_out({desk:orders.map(o=>K(closingDedupe(o)).sort()),stored});''')
    assert got["desk"] == [["c1700", "c1830"]] * 3 and got["stored"] == ["17:00", "18:30"]

def test_r1_two_runs_of_one_start_with_one_as_of_the_higher_run_id_stands_in_either_order(tmp_path):
    """P3-3: R1/R9's order is desk_meta.as_of, THEN the run id. Two runs of one start whose Desk read one as_of: the
    later run (the higher run id) stands for the game in either listing order, the earlier is superseded, and the slate
    row leaves against it; the pages read are listed newest first. (Comparing as_of alone would keep both rows.)"""
    got = _node(tmp_path, DEDUPE_JS + r'''
const p1=P("c1.json","2026-10-19T16:25:00Z",RUN), p2=P("c2.json","2026-10-19T16:25:00Z",RUN_SAME);
const base=[R("s","2026-10-19T17:00:00"),R("c1","2026-10-19T17:00:00",p1),R("c2","2026-10-19T17:00:00",p2)];
T_out([base,[...base].reverse()].map(o=>{ const r=closingDedupe(o);
  return {rows:K(r),sup:r.superseded,files:r.files.map(f=>f.run_id),dropped:r.slateRowsDropped,note:closingNote(r)}; }));''',
                RUN=RUN, RUN_SAME=RUN_SAME_AS_OF)
    want = {"rows": ["c2"], "sup": ["c1.json"], "files": [RUN_SAME_AS_OF, RUN], "dropped": 1,
            "note": " · closing: 2 file(s) (NFL 2026-10-19T17:00:00Z) · 1 slate row(s) replaced by their closing row"
                    " · 1 superseded by a later page"}
    assert got == [want, want]


def test_r1_no_listing_order_reaches_the_stored_ledger_a_copy_keeps_its_smallest_name(tmp_path):
    """P3-1: storeClosings stores this load's pages newest first (pageCmp), then by file name; a byte copy of one page
    listed under two names keeps ONE name, its smallest, in closingDedupe's files, the Desk rows, the stored page and
    every mark's closing.file. The slate, then the copies as [a, b] or [b, a]: byte-identical stored ledgers, notes and
    summaries. Two pages of one start (16:25Z, 16:40Z) after the slate, in either order: the same load note ("6 game(s)
    stored · 6 kept": the newer page first, the older kept out game by game) and the same stored bytes."""
    got = _node(tmp_path, r'''
const A="laptop/2026-10-19/"+CN, B="laptop/2026-10-18/"+CN;
const run=async ds=>{ T_reset(); await loadDocs([T_doc(SN,S)]); const did=await loadDocs(ds), L=loadLedger();
  const st=L.meta.closings["NFL|2026-10-19T17:00:00Z"];
  return {stored:T_stored(),note:T_note(),summary:document.getElementById("summary").textContent,
    files:did.closings.files.map(f=>f.file),rows:[...new Set(rows.map(r=>r.closing.file))],
    pages:Object.values(st.pages).map(p=>p.file),
    marks:[...new Set(L.calls.filter(c=>c.not_executed).map(c=>c.not_executed.closing.file))]}; };
const ab=await run([T_doc(A,C),T_doc(B,C)]), ba=await run([T_doc(B,C),T_doc(A,C)]);
const p1=await run([T_doc(CN,C),T_doc("closing_b.json",C2)]), p2=await run([T_doc("closing_b.json",C2),T_doc(CN,C)]);
T_out({ab,ba,p1,p2,B});''', C2=closing(at=LATER_AT, run=RUN2, Denver=0.60), **_docs())
    ab, ba, p1, p2 = got["ab"], got["ba"], got["p1"], got["p2"]
    assert ab == ba
    assert ab["files"] == ab["rows"] == ab["pages"] == ab["marks"] == [got["B"]]
    assert " · closing: 1 page(s) read · 6 game(s) stored · 6 kept (the stored page is newer or the same) · 3 claim(s)" \
           in ab["note"] and ab["summary"].endswith(" · 1 copy(ies) of a page read once")
    assert p1 == p2 and p1["files"] == ["closing_b.json", CLOSING_NAME]
    assert " · closing: 2 page(s) read · 6 game(s) stored · 6 kept (the stored page is newer or the same) · " in p1["note"]
    assert p1["pages"] == p1["rows"] == ["closing_b.json"]


def test_with_no_closing_file_the_rows_and_every_note_are_todays(tmp_path):
    """No closing file in the load: closingDedupe hands the very rows back, the Desk summary and the load note are
    byte for byte today's (the strings origin/main prints for this slate), and did.closings says nothing was read."""
    got = _node(tmp_path, r'''
const same=closingDedupe(normalize(S)), arr=normalize(S);
const did=await loadDocs([T_doc(SN,S)]);
T_out({identity:closingDedupe(arr).rows===arr,same:[same.files,same.superseded,same.copies,same.slateRowsDropped],
  summary:document.getElementById("summary").textContent,note:T_note(),closings:did.closings,
  line:closingNote(did.closings)});''', **_docs())
    assert got["identity"] is True and got["same"] == [[], [], 0, 0]
    assert got["summary"] == SUMMARY_SLATE
    assert got["note"] == ("Auto-claimed 6 call(s) at their file's as_of — 6 new · 0 position(s) repriced · 0 already"
                           " claimed from this file · 0 older than the ledger (kept) · 0 past kickoff at as_of (not"
                           " claimed). \"Re-log at T-60\" refreshes prices.")
    assert got["closings"] == {"files": [], "superseded": [], "partly": [], "copies": 0, "slateRowsDropped": 0,
                               "marks": None}
    assert got["line"] == ""


def test_the_desk_summary_carries_the_closing_line_after_the_refusals_at_both_returns():
    html = _html()
    ds = _fn(html, "deskSourceNote")
    assert "if(!rows.length) return refusedNote()+closingNote(closingLoad);" in ds
    assert ds.count("refusedNote()+closingNote(closingLoad)") == 2 and ds.count("closingNote(") == 2
    assert "let closingLoad=null;" in html


# ------------------------------------------------------------------------------------------------ the control --

API = "https://api.github.com/repos/anthonyevans29/Sports-Predictor-exports/contents/"
# fetch stubbed: every request recorded (URL, Accept, Authorization); a path not routed answers 404, "throw" throws
FETCH = r'''
const API="https://api.github.com/repos/anthonyevans29/Sports-Predictor-exports/contents/", T_req=[];
function T_route(map){ globalThis.fetch=async(url,o)=>{ T_req.push([url,o.headers.Accept,o.headers.Authorization]);
  const r=map[url.startsWith(API)?url.slice(API.length):url];
  if(r===undefined) return {ok:false,status:404,json:async()=>({message:"Not Found"}),text:async()=>"{}"};
  if(r==="throw") throw new Error("network down");
  const st=r.status||200, b=r.body;
  return {ok:st>=200&&st<300,status:st,json:async()=>b,text:async()=>typeof b==="string"?b:JSON.stringify(b)}; }; }
const T_file=n=>({type:"file",name:n});
const T_mirror=()=>document.getElementById("mirrorNote").textContent;
document.getElementById("mirrorToken").value="github_pat_TEST";
'''
LAPTOP_NOTE = "Loaded 3 file(s) from anthonyevans29/Sports-Predictor-exports laptop: 1 closing file(s) of 2026-10-18, 2026-10-19 UTC"
MLB_START = datetime(2026, 10, 19, 23, 0, tzinfo=timezone.utc)


def mlb_closing():
    """An MLB closing page (start 23:00Z, Clearwater PLAY): a real document, so a fetch that failed and were loaded
    anyway would put an MLB row on the Desk (the 500 route's body)."""
    at = MLB_START - timedelta(minutes=35)
    doc = dp.annotate({"sport": "mlb", "predictions": [row(401, "Clearwater", 0.60, fair_h=0.53, bid=0.51, ask=0.52,
                                                           now=at)]}, now=at, counts_source="parameter")
    return mc.closing_doc(doc, "MLB", MLB_START, "20261019T222500Z-mlb", [401], [])


def _control_docs():
    return {**_docs(), "CM": mlb_closing()}


def _routes_js():
    return r'''
const LEG={...S,predictions:S.predictions.map(p=>{ const {desk,...x}=p; return x; })};
const ROUTES={"laptop/latest":{body:[T_file("nfl_predictions.json"),T_file("closing_NFL.json"),T_file("RESULTS.md"),
    {type:"dir",name:"sub.json"},T_file("window 24h.json")]},
  "laptop/2026-10-19":{body:[T_file(CN),T_file("closing_MLB_2026-10-19T2300Z.json"),T_file("nfl_predictions_2026-10-19.json")]},
  "laptop/latest/nfl_predictions.json":{body:JSON.stringify(S)},"laptop/latest/window%2024h.json":{body:JSON.stringify(LEG)},
  ["laptop/2026-10-19/"+CN]:{body:JSON.stringify(C)},
  "laptop/2026-10-19/closing_MLB_2026-10-19T2300Z.json":{status:500,body:JSON.stringify(CM)},
  "laptop/latest/closing_NFL.json":{body:JSON.stringify(C)}};
'''


def test_the_laptop_control_requests_exactly_latest_and_the_two_utc_day_folders_and_names_what_it_did_not_load(tmp_path):
    """The control lists laptop/latest (JSON files only; its closing_* copy, a non-JSON file and a folder never
    fetched) and laptop/<yesterday UTC> and laptop/<today UTC> (2026-10-18 and 2026-10-19 at 16:30Z; closing_*.json
    only), then fetches each file raw, every path segment encoded. The 2026-10-18 folder answers 404: named, not
    fatal. The MLB closing answers 500 (with a real MLB page as its body: loaded, it would put an MLB row on the Desk):
    named and never loaded. One load: the closing row stands over the slate's; the note is this load's, R14's line
    included (the ledger holds no claim from before the page: ⚠, the slate called)."""
    got = _node(tmp_path, FETCH + _routes_js() + r'''
T_route(ROUTES);
await loadClosingsFromLaptop(Date.now());
T_out({req:T_req,note:T_mirror(),rows:rows.map(r=>[r.home,r.closing?r.closing.file:"slate"]),
  sports:[...new Set(rows.map(r=>r.sport))],token:localStorage.getItem("bd_mirror_token"),
  input:document.getElementById("mirrorToken").value,logNote:T_note()});''', **_control_docs())
    lst, raw, auth = "application/vnd.github+json", "application/vnd.github.raw+json", "Bearer github_pat_TEST"
    assert got["req"] == [[API + "laptop/latest", lst, auth], [API + "laptop/2026-10-18", lst, auth],
                          [API + "laptop/2026-10-19", lst, auth],
                          [API + "laptop/latest/nfl_predictions.json", raw, auth],
                          [API + "laptop/latest/window%2024h.json", raw, auth],
                          [API + "laptop/2026-10-19/" + CLOSING_NAME, raw, auth],
                          [API + "laptop/2026-10-19/closing_MLB_2026-10-19T2300Z.json", raw, auth]]
    assert got["note"] == (LAPTOP_NOTE + " · 2 newest of the other kinds · laptop/2026-10-18: no folder yet"
                           " · 1 not fetched, not loaded: laptop/2026-10-19/closing_MLB_2026-10-19T2300Z.json (GitHub 500)"
                           + DEDUPE_NOTE + " · 0 claim(s) marked NOT EXECUTED (0 new, 0 cleared by a later page)"
                           " · 1 without desk blocks refused · ⚠ 6 of 6 covered game(s) hold no claim from before their"
                           " page in this browser's ledger: nothing there to mark. A local Cockpit keeps its own ledger:"
                           " import the ledger, then load.")
    assert got["rows"] == [[h, "laptop/2026-10-19/" + CLOSING_NAME] for h in
                           ("Buffalo", "Miami", "Dallas", "Denver", "Newark", "Tampa")]
    assert got["sports"] == ["NFL"] and got["token"] == "github_pat_TEST" and got["input"] == ""
    assert got["logNote"].endswith(COUNTS_NOTE)                 # the 144 note rides the load note, as for any load


def test_the_laptop_control_after_import_the_ledger_marks_the_claims_the_page_did_not_repeat(tmp_path):
    """The runbook's order, "import the ledger, then load": a ledger that already holds the slate's claims (12:00Z)
    loads the laptop's closings and the page marks Denver, Miami and Dallas; no R14 line (every covered game holds a
    claim from before its page)."""
    got = _node(tmp_path, FETCH + _routes_js() + r'''
await loadDocs([T_doc(SN,S)]); const A=JSON.parse(T_stored()); T_reset(); importLedgerDoc(A);
T_route(ROUTES);
await loadClosingsFromLaptop(Date.now());
T_out({note:T_mirror(),marks:T_marks(loadLedger())});''', **_control_docs())
    assert got["marks"] == {"Miami|straight|HOME": RUN, "Dallas|straight|HOME": RUN, "Denver|straight|HOME": RUN}
    assert got["note"].endswith(DEDUPE_NOTE + " · 3 claim(s) marked NOT EXECUTED (3 new, 0 cleared by a later page)"
                                " · 1 without desk blocks refused")


@pytest.mark.parametrize("case", ["latest401", "latest403", "latest404", "day403", "day500", "network"])
def test_the_laptop_control_aborts_on_a_rejected_token_or_an_unreadable_listing_and_loads_nothing(tmp_path, case):
    """laptop/latest not ok aborts as the host control does (401/403 "token rejected / no read access", else
    "laptop/latest not found"); a day folder not ok but 404 aborts too; a listing that throws reads "Fetch failed".
    Nothing is fetched beyond the listing and nothing loads: the slate loaded before stays, the ledger as it was."""
    got = _node(tmp_path, FETCH + _routes_js() + r'''
await loadDocs([T_doc(SN,S)]); const before=T_stored(), rows0=JSON.stringify(rows);
const R2={...ROUTES};
if(CASE==="latest401") R2["laptop/latest"]={status:401,body:{}};
if(CASE==="latest403") R2["laptop/latest"]={status:403,body:{}};
if(CASE==="latest404") delete R2["laptop/latest"];
if(CASE==="day403") R2["laptop/2026-10-18"]={status:403,body:{}};
if(CASE==="day500") R2["laptop/2026-10-19"]={status:500,body:{}};
if(CASE==="network") R2["laptop/latest"]="throw";
T_route(R2);
await loadClosingsFromLaptop(Date.now());
T_out({note:T_mirror(),fetched:T_req.filter(x=>x[1]==="application/vnd.github.raw+json").length,
  same:T_stored()===before&&JSON.stringify(rows)===rows0});''', CASE=case, **_control_docs())
    want = {"latest401": "GitHub 401 — token rejected / no read access",
            "latest403": "GitHub 403 — token rejected / no read access",
            "latest404": "GitHub 404 — laptop/latest not found",
            "day403": "GitHub 403 — token rejected / no read access",
            "day500": "GitHub 500 — laptop/2026-10-19 could not be listed",
            "network": "Fetch failed: network down"}[case]
    assert got == {"note": want, "fetched": 0, "same": True}


def test_the_laptop_control_names_a_file_fetch_that_throws_and_its_note_is_this_loads_only(tmp_path):
    """#589: the note is built from THIS load's did. A file-picker load refused a file and stored a closing; the
    control's load then reads latest alone (both day folders 404, a file fetch throwing): its note names no refusal, no
    closing line, no mark and no R14 line from the load before, only what it did."""
    got = _node(tmp_path, FETCH + _routes_js() + r'''
await loadDocs([T_doc("legacy.json",LEG),T_doc(SN,S),T_doc(CN,C)]);
T_route({"laptop/latest":{body:[T_file("nfl_predictions.json"),T_file("bad.json")]},
  "laptop/latest/nfl_predictions.json":{body:JSON.stringify(S)},"laptop/latest/bad.json":"throw"});
await loadClosingsFromLaptop(Date.now());
T_out({note:T_mirror(),rows:rows.length,closing:rows.some(r=>r.closing),
  summary:document.getElementById("summary").textContent});''', **_control_docs())
    assert got["note"] == ("Loaded 1 file(s) from anthonyevans29/Sports-Predictor-exports laptop: 0 closing file(s) of"
                           " 2026-10-18, 2026-10-19 UTC · 1 newest of the other kinds · laptop/2026-10-18: no folder yet"
                           " · laptop/2026-10-19: no folder yet · 1 not fetched, not loaded: laptop/latest/bad.json"
                           " (network down)")
    assert got["rows"] == 6 and got["closing"] is False and got["summary"] == SUMMARY_SLATE


def test_the_laptop_control_when_every_file_fetch_fails_keeps_the_desk_and_claims_nothing(tmp_path):
    """Every listed file answers 500, each with its real body: nothing is handed to loadDocs, so the Desk keeps the slate
    loaded before (its rows and summary), the ledger is as it was (nothing claimed, nothing marked), and the note names
    every file that did not fetch."""
    got = _node(tmp_path, FETCH + _routes_js() + r'''
await loadDocs([T_doc(SN,S)]); const before=T_stored(), rows0=JSON.stringify(rows), sum0=document.getElementById("summary").textContent;
const R2={...ROUTES}; for(const k of Object.keys(R2)) if(/\.json$/.test(k)) R2[k]={status:500,body:R2[k].body};
T_route(R2);
await loadClosingsFromLaptop(Date.now());
T_out({note:T_mirror(),same:T_stored()===before&&JSON.stringify(rows)===rows0,
  summary:document.getElementById("summary").textContent===sum0,rows:rows.length,closing:rows.some(r=>r.closing)});''',
                **_control_docs())
    assert got == {"note": "Loaded 0 file(s) from anthonyevans29/Sports-Predictor-exports laptop: 0 closing file(s) of"
                           " 2026-10-18, 2026-10-19 UTC · 0 newest of the other kinds · laptop/2026-10-18: no folder yet"
                           " · 4 not fetched, not loaded: laptop/latest/nfl_predictions.json (GitHub 500),"
                           " laptop/latest/window 24h.json (GitHub 500), laptop/2026-10-19/" + CLOSING_NAME
                           + " (GitHub 500), laptop/2026-10-19/closing_MLB_2026-10-19T2300Z.json (GitHub 500)",
                   "same": True, "summary": True, "rows": 6, "closing": False}


def test_the_laptop_control_says_the_load_stopped_when_a_fetched_file_does_not_parse(tmp_path):
    """#431 commit 2 review (P3-5): a file that answers 200 but is not JSON stops loadDocs at "Could not parse" (#summary
    names it). The control's note says so from THIS load's did (did.parseError, #589), never "Loaded": nothing after it
    was loaded, so nothing is claimed or marked and the closing page is never stored. The stop is that load's, never a
    global's: a next load whose every file fetch fails hands loadDocs nothing (#summary still shows the parse message)
    and its note reads "Loaded 0 file(s)"; a good load after it reads "Loaded" too."""
    got = _node(tmp_path, FETCH + _routes_js() + r'''
await loadDocs([T_doc(SN,S)]); const before=T_stored();
let why=""; try{ JSON.parse(BAD); }catch(e){ why=e.message; }
T_route({"laptop/latest":{body:[T_file("broken.json"),T_file("nfl_predictions.json")]},
  "laptop/latest/broken.json":{body:BAD},"laptop/latest/nfl_predictions.json":{body:JSON.stringify(S)},
  "laptop/2026-10-19":{body:[T_file(CN)]},["laptop/2026-10-19/"+CN]:{body:JSON.stringify(C)}});
await loadClosingsFromLaptop(Date.now());
const one={note:T_mirror(),summary:document.getElementById("summary").textContent,same:T_stored()===before};
T_route({"laptop/latest":{body:[T_file("nfl_predictions.json")]},"laptop/latest/nfl_predictions.json":{status:500,body:"{}"}});
await loadClosingsFromLaptop(Date.now());
const two={note:T_mirror(),summary:document.getElementById("summary").textContent};
T_route({"laptop/latest":{body:[T_file("nfl_predictions.json")]},"laptop/latest/nfl_predictions.json":{body:JSON.stringify(S)}});
await loadClosingsFromLaptop(Date.now());
T_out({one,why,two,three:T_mirror()});''', BAD="{not json", **_control_docs())
    msg = "Could not parse laptop/latest/broken.json: " + got["why"]
    assert got["one"] == {"note": f"load stopped: {msg}; no Desk file of this load was loaded (nothing claimed or"
                                  " marked)", "summary": msg, "same": True}
    assert got["two"]["summary"] == msg and got["two"]["note"].startswith(
        "Loaded 0 file(s) from anthonyevans29/Sports-Predictor-exports laptop: ")
    assert got["three"].startswith("Loaded 1 file(s) from anthonyevans29/Sports-Predictor-exports laptop: ")


LOAD_LATEST_FROM_HOST = r'''async function loadLatestFromHost(){
  const typed=$("mirrorToken").value.trim(), repo=$("mirrorRepo").value.trim()||MIRROR_REPO_DEFAULT;
  if(typed){ lsSet(MIRROR_TOKEN_KEY,typed); $("mirrorToken").value=""; $("mirrorToken").placeholder="token saved in this browser"; }
  lsSet(MIRROR_REPO_KEY,repo);
  const tok=lsGet(MIRROR_TOKEN_KEY);
  if(!tok){ $("mirrorNote").textContent="Paste a read-only token first."; return; }
  const api=`https://api.github.com/repos/${repo}/contents/host/latest`;
  const hdr={Authorization:`Bearer ${tok}`,"X-GitHub-Api-Version":"2022-11-28"};
  try{
    const r=await fetch(api,{headers:{...hdr,Accept:"application/vnd.github+json"}});
    if(!r.ok){ $("mirrorNote").textContent=`GitHub ${r.status} — ${r.status===401||r.status===403?"token rejected / no read access":"host/latest not found"}`; return; }
    const list=(await r.json()).filter(x=>x.type==="file"&&x.name.endsWith(".json"));
    const docs=await Promise.all(list.map(async x=>{
      const q=await fetch(`${api}/${encodeURIComponent(x.name)}`,{headers:{...hdr,Accept:"application/vnd.github.raw+json"}});
      return {name:`host/latest/${x.name}`,text:q.ok?await q.text():"{}"};}));
    const did=await loadDocs(docs);      // the note is THIS load's (#589 review): never an earlier load's refusals
    $("mirrorNote").textContent=`Loaded ${docs.length} file(s) from ${repo} host/latest`
      +(did.coverage?` · ${did.coverage} coverage file${did.coverage===1?"":"s"} on the Today tab`
        +(did.coverageError?` (not rendered: ${did.coverageError})`:""):"")
      +(did.refused.length?` · ${did.refused.length} without desk blocks refused`:"");
  }catch(e){ $("mirrorNote").textContent=`Fetch failed: ${(e&&e.message)||e}`; }
}'''


def test_the_laptop_control_sits_beside_the_host_control_which_is_unchanged_and_its_note_reads_only_its_did():
    """The button beside #mirrorBtn, the same token, repo and note; loadLatestFromHost byte for byte as on origin/main
    (scripts/cockpit_mirror_verify.py and tests/test_cockpit_today.py pin its behaviour); the new function after it,
    wired after its wiring; #589's rule: the note is built from this load's did, never a global."""
    html = _html()
    assert ('<button id="mirrorBtn">Load latest from host</button>\n'
            '      <button id="mirrorLaptopBtn">Load closings + latest from laptop</button>\n'
            '      <span class="note" id="mirrorNote"></span></div>') in html
    assert _fn(html, "loadLatestFromHost") == LOAD_LATEST_FROM_HOST
    host, laptop = html.index("async function loadLatestFromHost("), html.index("async function loadClosingsFromLaptop(")
    wire_h = html.index('$("mirrorBtn").addEventListener("click",loadLatestFromHost);')
    wire_l = html.index('$("mirrorLaptopBtn").addEventListener("click",()=>loadClosingsFromLaptop(Date.now()));')
    assert host < wire_h < laptop < wire_l
    fn = _fn(html, "loadClosingsFromLaptop")
    assert fn.count("loadDocs(") == 1 and "const did=await loadDocs(docs);" in fn
    for glob in ("refusedFiles", "closingLoad", "lastNotExec", "lastCapture", "rows.", "ticketRows", '$("summary")'):
        assert glob not in fn, glob
    assert "if(did.parseError){" in fn and ("`load stopped: ${did.parseError}; no Desk file of this load was loaded"
                                            " (nothing claimed or marked)`") in fn
    assert "did.refused.length" in fn and "did.coverage" in fn and "closingNote(dc)" in fn \
        and "noClaimNote(m&&m.noClaim)" in fn and "const dc=did.closings||{}, m=dc.marks" in fn
    assert '!x.name.startsWith("closing_")' in fn and r"/^closing_.*\.json$/.test(x.name)" in fn
    assert 'Accept:"application/vnd.github.raw+json"' in fn and "p.split(\"/\").map(encodeURIComponent).join(\"/\")" in fn
    assert "days=[utcDay(t-86400000),utcDay(t)]" in fn
    assert _fn(html, "utcDay") == "function utcDay(ms){ return new Date(ms).toISOString().slice(0,10); }"


# ------------------------------------------------------------------------------------------------ R16 and R17 --
# ARCHITECT 2026-10-20, addendum 146 item 1(iv), verbatim: "R16 the ledger stores the page's ORDERED size and limit
# beside the FILLED size and entry; R17 each position carries entry minus the closing ask on its pick (true CLV, in
# cents) and the P&L view sums it beside the P&L". The sign CORRECTED (addendum 148 item 1(b)): "ask minus entry, + =
# bought below the close, the direction the page's existing CLV lines already use ... the line names its direction:
# "Closing CLV (close − entry; + = beat the close)"". Addendum 148 item 1(c)-(i): each default accepted.

ORDER_KEYS = ("ticker", "side", "limit", "contracts", "unit")
CLV_HEAD = "Closing CLV (close − entry; + = beat the close) (addendum 146 item 1(iv) R17, #431): "
CLV_NONE = CLV_HEAD + "0 position(s), 0 fill(s) · sum none · mean none per position"
UNIT10 = "1u = 10 contracts (SP_UNIT_USD unset)"


def _order(doc, home):
    """The page's order for `home`'s pick as R16 stores it: the file's desk.order, its five fields, copy-exact."""
    o = next(r for r in doc["predictions"] if r["home_team"] == home)["desk"]["order"]
    return {k: o[k] for k in ORDER_KEYS}


def _legs(doc, home):
    return next(r for r in doc["predictions"] if r["home_team"] == home)["kalshi_legs"]


# A synthetic ledger's pieces (pure reads of closingPositions): a stored game G(home, {...}) with its Kalshi legs at a
# HOME bid/ask (the AWAY leg the two-way complement, as tests/test_closing_runs.row writes it), an order O, a fill F
R17_JS = r'''
const TICK=(h,s)=>{ const a=h[0]+"V", c=h.slice(0,3).toUpperCase(); return `KXNFLGAME-26OCT19${a}${c}-${s==="AWAY"?a:c}`; };
const LEGS=(h,b,a)=>({HOME:{ticker:TICK(h),bid:b,ask:a},AWAY:{ticker:TICK(h,"AWAY"),bid:+(1-a).toFixed(2),ask:+(1-b).toFixed(2)}});
const O=(ticker,side,limit,contracts)=>({ticker,side,limit,contracts,unit:"1u = 10 contracts (SP_UNIT_USD unset)"});
const G=(h,o)=>({sport:"NFL",home:h,away:h+" Visitors",kickoff:"2026-10-19T17:00:00",calls:["model_edge|straight|HOME"],
  text:`PLAY ${h} 1u`,run_id:"20261019T162500Z-nfl",as_of:"2026-10-19T16:25:00Z",file:"closing_NFL_2026-10-19T1700Z.json",
  legs:LEGS(h,0.52,0.53),orders:{"model_edge|straight|HOME":O(TICK(h),"YES",0.53,10)},...(o||{})});
const PUT=(L,games,start)=>putPage(L,{family:"NFL",start:start||"2026-10-19T17:00:00Z",
  games:Object.fromEntries(games.map(g=>[`${g.sport}|${g.home}|${g.away}|${g.kickoff}`,g]))});
const F=(id,ticker,side,qty,entry)=>({id,ticker,side,qty,entry,title:""});
const R4=x=>x==null?null:+x.toFixed(4);
const PJ=ps=>ps.map(p=>({id:p.id,status:p.status,cover:p.cover,page:p.page,legacy:p.legacy,ordered:p.ordered,
  filled:{...p.filled,entry:R4(p.filled.entry)},asks:p.asks,quote:p.quote,clv:R4(p.clv_c),above:R4(p.above_limit_c),
  above_fills:p.above_fills,over:p.over_size,partial:p.partial}));
const RUN17=(calls,fills,games,more)=>{ const L={meta:{},calls,fills}; if(games) PUT(L,games); if(more) more(L);
  return {ps:PJ(closingPositions(L)),line:closingClvLine(L)}; };
'''


def test_r16_r17_the_stored_page_keeps_the_rows_legs_and_its_orders_copy_exact_and_a_resave_is_byte_identical(tmp_path):
    """Per stored game: `legs`, the closing row's Kalshi legs as the export carries them (normalize keeps them on the
    row, kLegs), and `orders`, the page's order by call key for each staked call it repeats (R16), the five fields of
    its desk.order; a shadow, and a PLAY the page does not repeat, carry none. A re-save and a reload of the same page
    write the same bytes."""
    C = closing(ticked=True)
    got = _node(tmp_path, r'''
const ne=storeClosings(T_pages(C,CN)), s1=T_stored(); saveLedger(loadLedger()); const s2=T_stored();
storeClosings(T_pages(C,CN));
const g=Object.values(loadLedger().meta.closings["NFL|2026-10-19T17:00:00Z"].games);
T_out({same:s1===s2&&T_stored()===s1,kept:ne.took,
  by:Object.fromEntries(g.map(x=>[x.home,{calls:x.calls,legs:x.legs,orders:x.orders,keys:Object.keys(x)}]))});''',
                C=C, CN=CLOSING_NAME)
    assert got["same"] is True and got["kept"] == 6
    by = got["by"]
    assert by["Buffalo"]["calls"] == ["model_edge|straight|HOME"]
    assert by["Buffalo"]["orders"] == {"model_edge|straight|HOME": _order(C, "Buffalo")}
    assert _order(C, "Buffalo")["ticker"] == tick("Buffalo") and _order(C, "Buffalo")["side"] == "YES"
    for home in ("Buffalo", "Miami", "Dallas", "Denver", "Newark", "Tampa"):
        assert by[home]["legs"] == _legs(C, home), home
        assert by[home]["keys"] == ["sport", "home", "away", "kickoff", "calls", "text", "run_id", "as_of", "file",
                                    "legs", "orders"]
    for home in ("Miami", "Dallas", "Denver", "Newark", "Tampa"):     # not repeated, PASS, the two shadows
        assert by[home]["orders"] == {}, home


def test_r16_closing_orders_by_kind_a_why_only_order_and_the_venue_tables_own_read(tmp_path):
    """closingOrders: a PLAY's and a LADDER's desk.order (a LADDER's is NO on HOME as desk_policy.order_line writes
    it); a VENUE call's only on a market-only row (renderVenue's read); a page that wrote no order stores {why}; a row
    with no order block and a shadow store nothing."""
    got = _node(tmp_path, r'''
const ord={ticker:"T",side:"NO",limit:0.6,limit_basis:"take at the ask (spread 1c)",contracts:5,unit:"1u = 10 contracts (SP_UNIT_USD unset)",
  text:"BUY NO T @ 0.60 × 5",why:null};
const why={ticker:null,side:null,limit:null,limit_basis:null,contracts:null,unit:"u",text:null,why:"no Kalshi ticker on file for the HOME leg"};
const R=(d,mo)=>({fileDesk:d,marketOnly:!!mo});
T_out({play:closingOrders(R({order:ord}),["model_edge|straight|HOME","model_edge|value_shadow|AWAY"]),
  ladder:closingOrders(R({order:ord}),["model_edge|ladder|AWAY"]),
  why:closingOrders(R({order:why}),["model_edge|straight|HOME"]),
  venue:closingOrders(R({order:ord},true),["venue_edge|straight|HOME"]),
  venueModel:closingOrders(R({order:ord}),["venue_edge|straight|HOME"]),
  none:closingOrders(R({order:null}),["model_edge|straight|HOME"]),
  shadow:closingOrders(R({order:ord}),["model_edge|quarantine_shadow|HOME"])});''')
    full = {"ticker": "T", "side": "NO", "limit": 0.6, "contracts": 5, "unit": UNIT10}
    assert got["play"] == {"model_edge|straight|HOME": full} and got["ladder"] == {"model_edge|ladder|AWAY": full}
    assert got["why"] == {"model_edge|straight|HOME": {"why": "no Kalshi ticker on file for the HOME leg"}}
    assert got["venue"] == {"venue_edge|straight|HOME": full}
    assert got["venueModel"] == got["none"] == got["shadow"] == {}


def test_r16_claim_order_is_frozen_exec_order_follows_the_closing_relog_and_an_early_execution_locks_it(tmp_path):
    """R16, the slate side: every claim stores kalshi_order (the row's desk.order: PLAY, LADDER, VENUE; null on a
    shadow and a ticket leg), claim_order frozen at the first capture and exec_order following each re-log, as the
    exec_* fields do; an early execution locks it (executeEarly sets it): the order the call follows at that moment,
    the closing page's after a closing re-log moved it, never its claim's. Written at claim, never at save. A page that
    wrote no order is stored as {why}."""
    S, C2 = slate(ticked=True), closing(at=LATER_AT, run=RUN2, ticked=True, quotes={"Buffalo": (0.55, 0.56)})
    got = _node(tmp_path, r'''
const B=L=>L.calls.find(c=>c.home==="Buffalo"&&c.call_type==="straight");
const pick=c=>({kalshi_order:c.kalshi_order,claim_order:c.claim_order,exec_order:c.exec_order});
await loadDocs([T_doc(SN,S)]);
const s0=JSON.parse(T_stored()).calls, at=pick(B(loadLedger()));
await loadDocs([T_doc("closing_NFL_2026-10-19T1700Z_b.json",C2)]);
const relog=pick(B(loadLedger()));
T_reset(); await loadDocs([T_doc(SN,S)]); executeEarly(B(loadLedger()).id);
await loadDocs([T_doc("closing_NFL_2026-10-19T1700Z_b.json",C2)]);
const early=pick(B(loadLedger()));
T_reset(); await loadDocs([T_doc(SN,S)]); await loadDocs([T_doc("closing_NFL_2026-10-19T1700Z_b.json",C2)]);
const note=executeEarly(B(loadLedger()).id), late=pick(B(loadLedger()));
T_reset(); const P=JSON.parse(JSON.stringify(S)), b=P.predictions.find(r=>r.home_team==="Buffalo");
b.desk.order={...b.desk.order,ticker:null,side:null,limit:null,contracts:null,text:null,why:"no Kalshi ticker on file"};
await loadDocs([T_doc(SN,P)]);
T_out({at,relog,early,late,note:note.slice(0,16),why:pick(B(loadLedger())),
  shadows:s0.filter(c=>c.call_type!=="straight").map(c=>[c.call_type,c.kalshi_order,c.claim_order,c.exec_order]),
  every:s0.every(c=>"kalshi_order" in c&&"claim_order" in c&&"exec_order" in c)});''',
                S=S, C2=C2, SN=SLATE_NAME)
    slate_o, close_o = _order(S, "Buffalo"), _order(C2, "Buffalo")
    assert slate_o != close_o and close_o["limit"] == 0.56
    assert got["at"] == {"kalshi_order": slate_o, "claim_order": slate_o, "exec_order": slate_o}
    assert got["relog"] == {"kalshi_order": close_o, "claim_order": slate_o, "exec_order": close_o}
    assert got["early"] == {"kalshi_order": close_o, "claim_order": slate_o, "exec_order": slate_o}
    assert got["note"] == "Executed EARLY ("               # after the re-log: the closing page's order is locked
    assert got["late"] == {"kalshi_order": close_o, "claim_order": slate_o, "exec_order": close_o}
    w = {"why": "no Kalshi ticker on file"}
    assert got["why"] == {"kalshi_order": w, "claim_order": w, "exec_order": w}
    assert got["every"] is True and got["shadows"] and all(x[1:] == [None, None, None] for x in got["shadows"])
    html = _html()
    assert 'rules:["parlay 0.25u"],kalshi_order:null' in _fn(html, "snapshotCalls")       # a ticket leg: no order
    assert "kalshi_order:r.marketOnly?orderOf(r.fileDesk&&r.fileDesk.order):null" in _fn(html, "snapshotCalls")
    assert "x.exec_order=x.kalshi_order??null;" in _fn(html, "executeEarly")
    for f in ("saveLedger", "markClosings", "putPage"):                    # written at claim, never at save
        assert "exec_order" not in _fn(html, f) and "claim_order" not in _fn(html, f), f


def test_r16_a_claim_from_before_r16_executed_early_stays_legacy_never_outside_any_page(tmp_path):
    """Execute now on a claim made before R16 (no kalshi_order key: the slate it followed stored none), with no re-log
    after it, writes no exec_order: the claim stays legacy, counted "legacy claim(s)", never "outside any page" (a
    false (g) flag). A claim made after R16 whose page wrote no order block (kalshi_order null) executed early locks
    exec_order null: outside any page. The port reads the same keys (ledger_fills.closing_positions)."""
    from src.walters import ledger_fills as LF
    got = _node(tmp_path, R17_JS + r'''
const f=[F("a",TICK("Denver"),"yes",10,0.55)], keys=c=>["kalshi_order","claim_order","exec_order"].filter(k=>k in c);
const run=o=>{ T_reset(); T_seed([T_mk("Denver",{id:"D",...o})]); const note=executeEarly("D");
  const L=loadLedger(); L.fills=f; saveLedger(L); const M=loadLedger(), c=M.calls[0];
  return {note:note.slice(0,16),mode:c.exec_mode,keys:keys(c),exec_order:"exec_order" in c?c.exec_order:"absent",line:closingClvLine(M),L:M}; };
T_out({pre:run({}),post:run({kalshi_order:null,claim_order:null,exec_order:null})});''')
    pre, post = got["pre"], got["post"]
    assert pre["note"] == post["note"] == "Executed EARLY (" and pre["mode"] == post["mode"] == "operator_early"
    assert pre["keys"] == [] and pre["exec_order"] == "absent"                     # nothing written: still legacy
    assert pre["line"] == (CLV_HEAD + "1 position(s), 1 fill(s) · sum none · mean none per position · graded 0 · open 1"
                           " — read against the closing page 0, the slate page 0, outside any page 0 · 1 legacy claim(s)"
                           " carry no stored order (claimed before R16) · 1 with no stored closing page · R16: 0 fill(s)"
                           " above their page's limit · 0 over the ordered size · 0 partial")
    assert post["keys"] == ["kalshi_order", "claim_order", "exec_order"] and post["exec_order"] is None
    assert "outside any page 1 · 1 with no stored closing page" in post["line"] and "legacy" not in post["line"]
    (pp,), (qp,) = LF.closing_positions(pre["L"]), LF.closing_positions(post["L"])
    assert (pp["legacy"], pp["page"], qp["legacy"], qp["page"]) == (True, None, False, None)
    assert 'if("kalshi_order" in x) x.exec_order=x.kalshi_order??null;' in _fn(_html(), "executeEarly")


def test_r17_the_held_contracts_closing_ask_and_the_ruled_sign(tmp_path):
    """(f) the held contract's ask, by the fill's ticker and side: YES on the pick's leg its ask; NO on the opponent
    1 − its bid (desk_policy.order_line prices NO so), rounded to 4 dp (against an AWAY bid of 0.43 it is 0.57, never
    0.5700000000000001); a ladder's NO on HOME the same; a ticker the page does not quote
    is counted, not priced; a stored leg's ticker padded and in lower case still matches (trimmed, upper case). (b)
    the sign: close − entry, + = beat the close: a 55c fill against a 53c closing ask prints -2.0c, a 53c fill against
    55c +2.0c; a blend at the close prints +0.0c, never -0.0c. (c) qty-weighted: 4@0.55 + 6@0.53 against 0.53 is
    -0.8c; one unpriced fill leaves the position unpriced (null), counted."""
    got = _node(tmp_path, R17_JS + r'''
const D=()=>[T_mk("Denver",{id:"D",exec_order:null})];
const lad={...T_mk("Arsenal",{id:"L",sport:"SOCCER",away:"Chelsea",game:"Chelsea @ Arsenal",three_way:true,
  call_type:"ladder",pick:"AWAY",units:0.5,kickoff:"2026-10-19T19:00:00"})};
const ARS="KXEPLGAME-26OCT19CHEARS-ARS";
const LG={sport:"SOCCER",home:"Arsenal",away:"Chelsea",kickoff:"2026-10-19T19:00:00",calls:["model_edge|ladder|AWAY"],
  text:"LADDER Chelsea 0.5u",run_id:"R",as_of:"2026-10-19T18:25:00Z",file:"f",legs:{HOME:{ticker:ARS,bid:0.40,ask:0.41}},
  orders:{"model_edge|ladder|AWAY":O(ARS,"NO",0.60,5)}};
T_out({yes55:RUN17(D(),[F("a",TICK("Denver"),"yes",10,0.55)],[G("Denver")]),
  yes53:RUN17(D(),[F("a",TICK("Denver"),"yes",10,0.53)],[G("Denver",{legs:LEGS("Denver",0.54,0.55)})]),
  noOpp:RUN17(D(),[F("a",TICK("Denver","AWAY"),"no",10,0.50)],[G("Denver")]),
  no43:RUN17(D(),[F("a",TICK("Denver","AWAY"),"no",10,0.50)],[G("Denver",{legs:LEGS("Denver",0.56,0.57)})]),
  ladder:RUN17([lad],[F("a",ARS,"no",5,0.58)],null,L=>putPage(L,{family:"SOCCER",start:"2026-10-19T19:00:00Z",games:{x:LG}})),
  qty:RUN17(D(),[F("a",TICK("Denver"),"yes",4,0.55),F("b",TICK("Denver"),"yes",6,0.53)],[G("Denver")]),
  oneOff:RUN17(D(),[F("a",TICK("Denver"),"yes",4,0.55),F("b","KXNFLGAME-26OCT191300DVDEN-DEN","yes",6,0.53)],[G("Denver")]),
  offPage:RUN17(D(),[F("a",TICK("Denver"),"yes",10,0.55)],[G("Denver",{legs:{HOME:{ticker:"KXNFLGAME-26OCT11-DENH",bid:0.52,ask:0.53}}})]),
  // the page's T: a stored leg's ticker padded and lower case still matches the fill's (the port's lc case)
  lc:RUN17(D(),[F("a",TICK("Denver"),"yes",10,0.55)],[G("Denver",{legs:{HOME:{ticker:"  "+TICK("Denver").toLowerCase()+"  ",bid:0.52,ask:0.53}}})]),
  // a blend at the close: 5@0.28 + 5@0.32 against a 30c ask is (5×(0.30−0.28) + 5×(0.30−0.32)) / 10 × 100 = 0 in
  // cents, -2.8e-15 in floating point: c1 rounds first, so the line prints +0.0c (clvLines' zero is "+0.00pp")
  zero:RUN17(D(),[F("a",TICK("Denver"),"yes",5,0.28),F("b",TICK("Denver"),"yes",5,0.32)],[G("Denver",{legs:LEGS("Denver",0.29,0.30)})])});''')
    zero = got.pop("zero")
    assert zero["ps"][0]["quote"] == "priced" and zero["ps"][0]["clv"] == 0          # R4 of -2.8e-15
    assert zero["line"].startswith(CLV_HEAD + "1 position(s), 2 fill(s) · sum +0.0c · mean +0.0c per position")
    assert "-0.0c" not in zero["line"]
    zr = _node(tmp_path, R17_JS + r'''
const L={meta:{},calls:[T_mk("Denver",{id:"D",exec_order:null})],
  fills:[F("a",TICK("Denver"),"yes",5,0.28),F("b",TICK("Denver"),"yes",5,0.32)]};
PUT(L,[G("Denver",{legs:LEGS("Denver",0.29,0.30)})]); T_out(closingPositions(L)[0].clv_c);''')
    assert -1e-9 < zr < 0                                       # the raw value is the negative zero the line rounds
    p = {k: v["ps"] for k, v in got.items()}
    assert all(len(v) == 1 for v in p.values()), p
    assert p["yes55"][0]["asks"] == [0.53] and p["yes55"][0]["clv"] == -2.0 and p["yes55"][0]["quote"] == "priced"
    assert p["yes53"][0]["asks"] == [0.55] and p["yes53"][0]["clv"] == 2.0
    assert got["yes55"]["line"].startswith(CLV_HEAD + "1 position(s), 1 fill(s) · sum -2.0c · mean -2.0c per position")
    assert got["yes53"]["line"].startswith(CLV_HEAD + "1 position(s), 1 fill(s) · sum +2.0c · mean +2.0c per position")
    assert p["noOpp"][0]["asks"] == [0.53] and p["noOpp"][0]["clv"] == 3.0          # 1 − the AWAY leg's bid 0.47
    assert p["no43"][0]["asks"] == [0.57] and p["no43"][0]["clv"] == 7.0    # 1 − 0.43 is 0.5700000000000001 unrounded
    assert p["ladder"][0] == {"id": "L", "status": "open", "cover": "page", "page": "closing", "legacy": False,
                              "ordered": {"ticker": ARS_TICK, "side": "NO", "limit": 0.6, "contracts": 5,
                                          "unit": UNIT10},
                              "filled": {"contracts": 5, "entry": 0.58, "fills": 1}, "asks": [0.6], "quote": "priced",
                              "clv": 2.0, "above": None, "above_fills": 0, "over": False, "partial": False}
    assert p["qty"][0]["clv"] == -0.8 and p["qty"][0]["filled"] == {"contracts": 10, "entry": 0.538, "fills": 2}
    assert p["oneOff"][0]["asks"] == [0.53, None] and p["oneOff"][0]["quote"] == "unpriced"
    assert p["oneOff"][0]["clv"] is None
    assert p["offPage"][0]["asks"] == [None] and p["offPage"][0]["quote"] == "unpriced"
    assert p["lc"][0]["asks"] == [0.53] and p["lc"][0]["quote"] == "priced" and p["lc"][0]["clv"] == -2.0
    for k in ("oneOff", "offPage"):
        assert got[k]["line"].startswith(CLV_HEAD + f"1 position(s), {2 if k == 'oneOff' else 1} fill(s) · sum none ·"
                                         " mean none per position") \
            and " · 1 on a contract the page does not quote (not priced) · " in got[k]["line"], k


ARS_TICK = "KXEPLGAME-26OCT19CHEARS-ARS"


def test_r17_no_stored_page_two_covering_pages_and_a_page_with_no_quote_are_counted_never_priced(tmp_path):
    """No stored closing page: counted, not priced, the order read from the slate (exec_order), or none (a claim from
    before R16 stored no order: legacy, never "outside any page"). Two covering pages (two starts within the hour):
    ambiguous, never guessed (law 4), neither page's order nor quote read. (i) a page stored before this build (no
    legs): "no closing quote stored", never priced from anything else; its order stays readable."""
    got = _node(tmp_path, R17_JS + r'''
const sl=O(TICK("Denver"),"YES",0.52,10), f=[F("a",TICK("Denver"),"yes",10,0.55)];
T_out({slate:RUN17([T_mk("Denver",{id:"D",exec_order:sl})],f,null),
  legacy:RUN17([T_mk("Denver",{id:"D"})],f,null),
  two:RUN17([T_mk("Denver",{id:"D",exec_order:sl})],f,[G("Denver")],L=>PUT(L,[G("Denver",{kickoff:"2026-10-19T17:30:00"})],"2026-10-19T17:30:00Z")),
  noQuote:RUN17([T_mk("Denver",{id:"D",exec_order:sl})],f,null,L=>{ const g=G("Denver"); delete g.legs; delete g.orders; PUT(L,[g]); })});''')
    p = {k: v["ps"][0] for k, v in got.items()}
    assert (p["slate"]["cover"], p["slate"]["page"], p["slate"]["quote"], p["slate"]["clv"]) == \
        ("none", "slate", "no_page", None)
    assert p["slate"]["ordered"] == {"ticker": DVDEN, "side": "YES", "limit": 0.52, "contracts": 10, "unit": UNIT10}
    assert p["slate"]["above"] == 3.0 and p["slate"]["above_fills"] == 1             # R16 reads the slate's limit
    assert (p["legacy"]["page"], p["legacy"]["legacy"], p["legacy"]["ordered"], p["legacy"]["quote"]) == \
        (None, True, None, "no_page")
    assert (p["two"]["cover"], p["two"]["page"], p["two"]["ordered"], p["two"]["quote"], p["two"]["clv"]) == \
        ("ambiguous", None, None, "ambiguous", None)
    assert (p["noQuote"]["cover"], p["noQuote"]["quote"], p["noQuote"]["page"], p["noQuote"]["clv"]) == \
        ("page", "no_quote", "slate", None)                                          # stored as legs null, orders {}
    assert got["legacy"]["line"] == (CLV_HEAD + "1 position(s), 1 fill(s) · sum none · mean none per position · graded 0"
                                     " · open 1 — read against the closing page 0, the slate page 0, outside any page 0"
                                     " · 1 legacy claim(s) carry no stored order (claimed before R16) · 1 with no stored"
                                     " closing page · R16: 0 fill(s) above their page's limit · 0 over the ordered size"
                                     " · 0 partial")
    assert " · 1 ambiguous · " in got["two"]["line"] and "outside any page 0 · 1 ambiguous" in got["two"]["line"]
    assert " · 1 with no closing quote stored · " in got["noQuote"]["line"]


def test_r17_which_positions_open_and_graded_marked_or_not_never_a_shadow_a_ticket_a_void_or_a_manual_fill(tmp_path):
    """(d) every filled straight, VENUE or LADDER position matched to a call, open included, marked or not (a mark is
    R10's business); a shadow is never filled, a ticket leg is no position (R5), a void (re-dated) call is out, and a
    manual Record fill is not a position ((h); its contracts box is Issue #634). The filters read the call's kind and
    its void label, never only whether matchFill handed it a fill (the port's Reno and Provo cases): a value shadow
    carrying units (isShadow reads call_type value_shadow; matchFill takes any non-quarantine call with units > 0) and a
    void label on a graded row are no positions. A fill with qty 0, and one with no entry (set in the ledger directly,
    not through the CSV import), are not read: Denver's position is its one 10@0.55 fill."""
    got = _node(tmp_path, R17_JS + r'''
const NE={flag:"not executed (#431)",closing:{family:"NFL",start:"s",run_id:"R",as_of:"a",file:"f"},closing_call:{text:"PASS",calls:[]}};
const f=h=>F(h,TICK(h),"yes",10,0.55), hs=["Denver","Buffalo","Miami","Dallas","Newark","Tampa","Albany","Reno","Provo"];
const calls=[T_mk("Denver",{status:"graded",result:"win"}),T_mk("Buffalo",{not_executed:NE}),
  T_mk("Miami",{engine:"venue_edge",tier:"shadow"}),T_mk("Dallas",{call_type:"quarantine_shadow",units:0,shadow_units:0.5}),
  T_mk("Newark",{call_type:"parlay_leg",parlay_id:"P-2026-10-19-X",units:0.25}),T_mk("Tampa",{void_redated:"re-dated",status:"void"}),
  T_mk("Albany",{order_type:"limit",fill_price:0.55,fill_recorded_at:"2026-10-19T13:00:00.000Z"}),
  T_mk("Reno",{call_type:"value_shadow",units:0.25}),T_mk("Provo",{void_redated:"re-dated",status:"graded"})];
const fills=["Denver","Buffalo","Miami","Dallas","Newark","Tampa","Reno","Provo"].map(f)
  .concat([F("Denver-q0",TICK("Denver"),"yes",0,0.40),F("Denver-null",TICK("Denver"),"yes",5,null)]);
const L={meta:{},calls,fills}, by=Object.fromEntries(classifyFills(L).map(x=>[x.id,x.call_id||null]));
const r=RUN17(calls,fills,hs.map(h=>G(h)));
T_out({ps:r.ps.map(p=>[p.id.split("|")[1],p.status]),den:r.ps[0].filled,line:r.line,
  matched:["Reno","Provo","Denver-q0","Denver-null"].map(k=>[k,!!by[k]&&by[k]===calls.find(c=>c.home===k.split("-")[0]).id]),
  isShadow:isShadow(calls[7])});''')
    assert got["ps"] == [["Denver Visitors @ Denver", "graded"], ["Buffalo Visitors @ Buffalo", "open"],
                         ["Miami Visitors @ Miami", "open"]]
    # matchFill hands each of these its call; closingPositions' own filters leave them out
    assert got["matched"] == [["Reno", True], ["Provo", True], ["Denver-q0", True], ["Denver-null", True]]
    assert got["isShadow"] is True
    assert got["den"] == {"contracts": 10, "entry": 0.55, "fills": 1}                # the qty-0 and no-entry fills unread
    assert got["line"].startswith(CLV_HEAD + "3 position(s), 3 fill(s) · ")


def test_r17_the_line_the_1c_shape_and_every_count_it_names(tmp_path):
    """The P&L view's line, verbatim shape (addendum 148 item 1): the positions and fills, the sum and the mean per
    position over the priced ones, graded and open, where each order was read ((e): the closing page, the slate page,
    outside any page), why one is not priced, and R16's flags ((g): above the limit, over the ordered size, partial,
    flagged and counted, never left out of the CLV). The 1(c) shape: two fills 2c above their page's limit, one
    partial, one over size. (e) pinned both ways: Denver's slate order (0.50 x 12) differs from its stored closing
    order (0.53 x 10), and the closing order is read. R16's count and its max pinned: Fresno has two fills above the
    limit by different amounts and Gilroy a third excess, so the line's K counts fills (not positions), each position
    keeps its largest excess, and the line names the largest of those.

    Every number by hand (G's legs: HOME bid 0.52 ask 0.53; G's order: YES 0.53 x 10):
      Denver  10@0.55, ask .53: clv (.53-.55)x100 = -2.0; above .55-.53 = 2.0c (1 fill); 10 = 10 ordered
              (the slate's 0.50 x 12 would read 5.0c above and partial)
      Buffalo  6@0.55: clv -2.0; above 2.0c (1 fill); 6 < 10: partial
      Miami   12@0.50, ask .50 (legs 0.49/0.50, no page order: the slate's 0.50 x 10): clv 0.0; above 0; 12 > 10: over
      Dallas   5@0.39, ask .41 (no page order, exec_order null: outside any page): clv +2.0
      Newark  two covering pages (17:00Z and 17:30Z): ambiguous, not priced
      Tampa   a page with legs null: no closing quote stored; 10@0.70 against its 0.70 limit: above 0
      Albany  no stored page, the slate's 0.60 x 3: 3@0.60, above 0, 3 = 3
      Lowell  no stored page and no exec_order key: legacy
      Camden  a ticker the page does not quote (the 13:00 ET ticker): unpriced; 10@0.45 against 0.45: above 0
      Fresno  5@0.54 + 5@0.56: entry (5x.54 + 5x.56)/10 = 0.55; clv (5x(.53-.54) + 5x(.53-.56))/10 x100
              = (-0.05 - 0.15)/10 x100 = -2.0; above [1.0, 3.0]: max 3.0c, 2 fills (min 1.0c); 10 = 10
      Gilroy  10@0.54: clv -1.0; above 1.0c (1 fill)
    The line: 11 positions; fills 9 + 3 = 12; priced Denver, Buffalo, Miami, Dallas, Fresno, Gilroy: sum -2.0 - 2.0
    + 0.0 + 2.0 - 2.0 - 1.0 = -5.0c, mean -5.0/6 = -0.83 -> -0.8c; graded 1 (Denver), open 10; closing page 6
    (Denver, Buffalo, Tampa, Camden, Fresno, Gilroy), slate page 2 (Miami, Albany), outside any page 1 (Dallas), legacy
    1 (Lowell), no stored closing page 2 (Albany, Lowell), ambiguous 1, not quoted 1 (Camden), no quote 1 (Tampa).
    R16: fills above 1 + 1 + 2 + 1 = 5 (positions above: 4); max over the positions' maxima [2.0, 2.0, 3.0, 1.0] =
    +3.0c (each position's min instead: max [2.0, 2.0, 1.0, 1.0] = 2.0; the line's min instead: 1.0); over 1
    (Miami); partial 1 (Buffalo)."""
    got = _node(tmp_path, R17_JS + r'''
const sl=(h,lim,n)=>O(TICK(h),"YES",lim,n);
const calls=[T_mk("Denver",{status:"graded",result:"win",exec_order:sl("Denver",0.50,12)}),T_mk("Buffalo",{exec_order:null}),
  T_mk("Miami",{exec_order:sl("Miami",0.50,10)}),T_mk("Dallas",{exec_order:null}),T_mk("Newark",{exec_order:null}),
  T_mk("Tampa",{exec_order:null}),T_mk("Albany",{exec_order:sl("Albany",0.60,3)}),T_mk("Lowell"),T_mk("Camden",{exec_order:null}),
  T_mk("Fresno",{exec_order:null}),T_mk("Gilroy",{exec_order:null})];
const fills=[F("1",TICK("Denver"),"yes",10,0.55),F("2",TICK("Buffalo"),"yes",6,0.55),F("3",TICK("Miami"),"yes",12,0.50),
  F("4",TICK("Dallas"),"yes",5,0.39),F("5",TICK("Newark"),"yes",10,0.55),F("6",TICK("Tampa"),"yes",10,0.70),
  F("7",TICK("Albany"),"yes",3,0.60),F("8",TICK("Lowell"),"yes",10,0.50),F("9","KXNFLGAME-26OCT191300CVCAM-CAM","yes",10,0.45),
  F("10",TICK("Fresno"),"yes",5,0.54),F("11",TICK("Fresno"),"yes",5,0.56),F("12",TICK("Gilroy"),"yes",10,0.54)];
const games=[G("Denver"),G("Buffalo"),G("Miami",{legs:LEGS("Miami",0.49,0.50),orders:{}}),
  G("Dallas",{legs:LEGS("Dallas",0.40,0.41),orders:{}}),G("Newark"),
  G("Tampa",{legs:null,orders:{"model_edge|straight|HOME":O(TICK("Tampa"),"YES",0.70,10)}}),
  G("Camden",{orders:{"model_edge|straight|HOME":O(TICK("Camden"),"YES",0.45,10)}}),G("Fresno"),G("Gilroy")];
const r=RUN17(calls,fills,games,L=>PUT(L,[G("Newark",{kickoff:"2026-10-19T17:30:00"})],"2026-10-19T17:30:00Z"));
T_out({line:r.line,by:Object.fromEntries(r.ps.map(p=>[p.id.split("|")[1].split(" @ ")[1],
  [p.page,p.quote,p.clv,p.above,p.above_fills,p.over,p.partial]])),
  den:r.ps.find(p=>p.id.includes("@ Denver")).ordered});''')
    assert got["by"] == {"Denver": ["closing", "priced", -2.0, 2.0, 1, False, False],
                         "Buffalo": ["closing", "priced", -2.0, 2.0, 1, False, True],
                         "Miami": ["slate", "priced", 0.0, None, 0, True, False],
                         "Dallas": [None, "priced", 2.0, None, 0, False, False],
                         "Newark": [None, "ambiguous", None, None, 0, False, False],
                         "Tampa": ["closing", "no_quote", None, None, 0, False, False],
                         "Albany": ["slate", "no_page", None, None, 0, False, False],
                         "Lowell": [None, "no_page", None, None, 0, False, False],
                         "Camden": ["closing", "unpriced", None, None, 0, False, False],
                         "Fresno": ["closing", "priced", -2.0, 3.0, 2, False, False],
                         "Gilroy": ["closing", "priced", -1.0, 1.0, 1, False, False]}
    assert got["den"] == {"ticker": DVDEN, "side": "YES", "limit": 0.53, "contracts": 10, "unit": UNIT10}
    assert got["line"] == (CLV_HEAD + "11 position(s), 12 fill(s) · sum -5.0c · mean -0.8c per position · graded 1"
                           " · open 10 — read against the closing page 6, the slate page 2, outside any page 1 · 1 legacy"
                           " claim(s) carry no stored order (claimed before R16) · 2 with no stored closing page"
                           " · 1 ambiguous · 1 on a contract the page does not quote (not priced) · 1 with no closing"
                           " quote stored · R16: 5 fill(s) above their page's limit (max +3.0c) · 1 over the ordered size"
                           " · 1 partial")


def test_r17_the_line_sits_after_the_clv_block_outside_its_window_and_the_audit_lines_keep_their_place(tmp_path):
    """One line in pnlBlock, after the sections and the executed-position CLV block, outside clvLines' ten-line window
    (scripts/cockpit_clv_verify.py slices ten from "EXECUTED-POSITION CLV"); the Kickoff audit line is still followed
    by the Not executed line (the receipt test above), and neither function changed for it."""
    got = _node(tmp_path, r'''
await loadDocs([T_doc(SN,S)]); await loadDocs([T_doc(CN,C)]);
const L=loadLedger(), pnl=pnlBlock(L).split("\n"), i=pnl.findIndex(l=>l.startsWith("EXECUTED-POSITION CLV")),
  k=pnl.findIndex(l=>l.startsWith("Closing CLV")), a=pnl.findIndex(l=>l.startsWith("Kickoff audit (#178)"));
T_out({i,k,n:clvLines(L).length,line:pnl[k],blank:[pnl[k-1],pnl[k+1]],next:pnl[a+1].slice(0,13),
  window:pnl.slice(i,i+10).some(l=>l.startsWith("Closing CLV"))});''', **_docs())
    assert got["line"] == CLV_NONE and got["blank"] == ["", ""] and got["k"] == got["i"] + got["n"] + 1
    assert got["window"] is False and got["next"] == "Not executed "
    html = _html()
    for f in ("auditLine", "notExecutedLine", "clvLines", "executedPositions"):
        assert "closingPositions" not in _fn(html, f) and "R17" not in _fn(html, f), f
    assert "...clvLines(L), \"\",\n    closingClvLine(L), \"\",\n" in _fn(html, "pnlBlock")
    for f in ("closingPositions", "closingClvLine", "closingOrders", "orderOf"):  # READ_SITES unchanged: no switch read
        assert "CLOSING_MARK_RULES" not in _fn(html, f), f


def test_r17_a_later_page_replaces_the_legs_an_older_never_overwrites_and_it_survives_a_reload_and_an_import(tmp_path):
    """R9 carries legs and orders with their game: the 16:40Z page's quotes replace the 16:25Z page's, a load of the
    older page again changes nothing. The line reads the stored ledger alone: the same after a reload with no file
    loaded, and after an import into an empty ledger (mergeClosings)."""
    S, C1 = slate(ticked=True), closing(ticked=True)
    C2 = closing(at=LATER_AT, run=RUN2, ticked=True, quotes={"Buffalo": (0.55, 0.56)})
    got = _node(tmp_path, r'''
const leg=()=>Object.values(loadLedger().meta.closings["NFL|2026-10-19T17:00:00Z"].games).find(g=>g.home==="Buffalo");
await loadDocs([T_doc(SN,S)]); await loadDocs([T_doc(CN,C1)]); const one=leg();
await loadDocs([T_doc("closing_NFL_2026-10-19T1700Z_b.json",C2)]); const two=leg();
await loadDocs([T_doc(CN,C1)]); const three=leg();
const L=loadLedger(); L.fills=[{id:"F1",ticker:TK,side:"yes",qty:10,entry:0.55,title:""}]; saveLedger(L);
T_out({one:[one.legs,one.orders],two:[two.legs,two.orders],three:[three.legs,three.orders],line:closingClvLine(loadLedger()),
  stored:T_stored()});''', S=S, C1=C1, C2=C2, SN=SLATE_NAME, CN=CLOSING_NAME, TK=tick("Buffalo"))
    k = "model_edge|straight|HOME"
    assert got["one"] == [_legs(C1, "Buffalo"), {k: _order(C1, "Buffalo")}]
    assert got["two"] == got["three"] == [_legs(C2, "Buffalo"), {k: _order(C2, "Buffalo")}]
    assert got["line"].startswith(CLV_HEAD + "1 position(s), 1 fill(s) · sum +1.0c · mean +1.0c per position · graded 0"
                                  " · open 1 — read against the closing page 1, the slate page 0, outside any page 0")
    again = _node(tmp_path, r'''
localStorage.setItem(LEDGER_KEY,ST); const reload=closingClvLine(loadLedger());
T_reset(); importLedgerDoc(JSON.parse(ST));
T_out({reload,imported:closingClvLine(loadLedger()),rows:rows.length});''', ST=got["stored"])
    assert again == {"reload": got["line"], "imported": got["line"], "rows": 0}


def test_r16_r17_the_docs_name_the_order_fields_the_stored_quotes_and_the_line():
    """The P&L organ spec names R16's fields (a VENUE call on a model row stores null, as snapshotCalls writes it) and
    R17's line written out whole, every segment in the page's order, the legacy segment marked proposed and escalated;
    the mirror runbook says the stored pages carry their legs and orders, that only a page stored by this build is
    priced, and that a 10-10..10-19 closing loaded after the merge is priced, its floor escalated (none built)."""
    spec = " ".join((ROOT / "docs" / "specs" / "cockpit-v04-pnl-organ.md").read_text(encoding="utf-8").split())
    assert "**The order (#431 R16, ARCHITECT 2026-10-20, addendum 146 item 1(iv)).**" in spec
    assert "`kalshi_order`" in spec and "`claim_order` is frozen at the first capture. `exec_order` follows" in spec
    assert "a VENUE call on a model row stores null." in spec
    assert "kalshi_order:r.marketOnly?orderOf(r.fileDesk&&r.fileDesk.order):null" in _fn(_html(), "snapshotCalls")
    full = ("`" + CLV_HEAD + "P position(s), F fill(s) · sum ±S.Sc · mean ±M.Mc per position · graded G · open O — read"
            " against the closing page X, the slate page Y, outside any page Z · L legacy claim(s) carry no stored order"
            " (claimed before R16) · N with no stored closing page · A ambiguous · U on a contract the page does not"
            " quote (not priced) · Q with no closing quote stored · R16: K fill(s) above their page's limit (max +X.Xc)"
            " · V over the ordered size · W partial`")
    assert full in spec
    # every segment is the page's own words, in the page's order: (closingClvLine's text, the template's text)
    segs = [("position(s),", "position(s),"), ("fill(s) · sum", "fill(s) · sum"),
            ("per position", "per position"), (" · graded ", " · graded "), (" · open ", " · open "),
            ("— read against the closing page", "— read against the closing page"),
            ("the slate page", "the slate page"), ("outside any page", "outside any page"),
            ('"legacy claim(s) carry no stored order (claimed before R16)"',
             "legacy claim(s) carry no stored order (claimed before R16)"),
            ('"with no stored closing page"', "with no stored closing page"),
            (',"ambiguous")', " ambiguous · "),
            ('"on a contract the page does not quote (not priced)"', "on a contract the page does not quote (not priced)"),
            ('"with no closing quote stored"', "with no closing quote stored"),
            ("R16: ${above} fill(s) above their page's limit", "R16: K fill(s) above their page's limit"),
            ("(max ${", "(max +"), ("over the ordered size", "over the ordered size"), ("partial`", "W partial")]
    body = _fn(_html(), "closingClvLine")
    at = [(body.find(a), full.find(b)) for a, b in segs]
    assert all(i >= 0 and j >= 0 for i, j in at), list(zip(segs, at))
    assert [i for i, _ in at] == sorted(i for i, _ in at) and [j for _, j in at] == sorted(j for _, j in at), at
    assert "The legacy segment (L) is the builder's addition, outside the ruled shape: **proposed, escalated to the" \
        " architect** (#632)." in spec
    assert ("Execute now writes no `exec_order`, so the claim stays legacy (part of the legacy proposal, escalated,"
            " #632).") in spec
    assert ("A claim from before R16 is counted as legacy, never as outside any page (part of the legacy proposal,"
            " escalated, #632).") in spec
    assert '"ask minus entry, + = bought below the close"' in spec
    doc = " ".join((ROOT / "docs" / "specs" / "exports-mirror.md").read_text(encoding="utf-8").split())
    assert ("Each stored game also keeps the closing row's Kalshi legs and the page's orders by call key (`legs`,"
            " `orders`; #431 R16/R17") in doc
    assert ("R17 prices a position only from a page stored by this build: a page stored before it carries no legs, and"
            " its positions are counted \"no closing quote stored\", never priced from anything else (addendum 148 item"
            " 1(i)). A closing file of 10-10..10-19 loaded after the merge IS priced: the page cannot tell that load from"
            " a backfill. Whether to floor it is escalated to the architect (#632 body); no floor is built.") in doc
    assert "nothing is backfilled" not in doc
