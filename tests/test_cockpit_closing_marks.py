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


def _nfl(**p_home):
    rows = [row(mid, home, p_home.get(home, p), fair_h=fh, bid=b, ask=a, comp="NFL", series="KXNFLGAME",
                now=CLOSE_AT, minutes=35) for mid, (home, p, fh, b, a) in GAMES.items()]
    rows[1]["input_quality"] = {"injuries": {"home": {"count": 2, "qb_listed": ["H. Quarterback"]},
                                             "away": {"count": 1, "qb_listed": []}}}
    rows[2]["input_quality"] = {"injuries": {"home": {"count": 2, "qb_listed": []}, "away": {"count": 0, "qb_listed": []}}}
    return rows


def _annotate(rows, at, src="parameter"):
    return dp.annotate({"sport": "nfl", "predictions": copy.deepcopy(rows)}, now=at, counts_source=src)


def slate(**p_home):
    """The morning slate at 12:00Z; Denver a PLAY there (p 0.60)."""
    return _annotate(_nfl(**{"Denver": 0.60, **p_home}), SLATE_AT)


def closing(at=CLOSE_AT, run=RUN, ids=None, src=DEFAULT_SRC, **p_home):
    doc = _annotate(_nfl(**p_home), at, src)
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
  csvFillExempt:true,                  // esc 12: a Kalshi CSV fill exempts a call from the mark when matchFill, R7's unmarked preference applied, still lands it on that call
  importIdCollision:"rekey",           // esc 1 (R4): incoming call whose id a local call holds under a different pick takes the new-format id (callKey), old kept as id_imported ("refuse" alternative)
};'''
READ_SITES = {"execUnknown": "holdRead", "writtenRuleFrom": "holdRead", "qb": "holdRead", "bothHolds": "holdRead",
              "execLeZeroAllFamilies": "holdRead", "ownCapture": "ownCaptureSkips", "missingGame": "putPage",
              "csvFillExempt": "markClosings", "importIdCollision": "upsertCalls"}


def test_the_switches_are_one_object_at_the_proposed_values_each_read_in_one_place():
    html = _html()
    assert html.count("const CLOSING_MARK_RULES={") == 1 and SWITCHES in html
    for key, site in READ_SITES.items():
        assert html.count(f"CLOSING_MARK_RULES.{key}") == 1, key
        assert f"CLOSING_MARK_RULES.{key}" in _fn(html, site), (key, site)


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
        "as_of": "2026-10-19T16:25:00Z", "file": CLOSING_NAME}
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
    join `rows`); ticketRows and the pages are taken after the loop and before policy() and autoClaim(); the pages are
    stored (and the marks re-derived) after autoClaim; did.closings is set after the literal; the four returns and the
    two refused copies stand (tests/test_cockpit_today.py)."""
    body = _fn(_html(), "loadDocs")
    refuse, stamp, concat = (body.index("if(rr.some(r=>!r.fileDesk)){ refusedFiles.push(f.name); continue; }"),
                             body.index("stampClosing(rr,doc,f.name);"), body.index("rows=rows.concat(rr);"))
    assert refuse < stamp < concat
    tr, cp, lab, pol, ac, st, note = (body.index("ticketRows=slateRows(rows);"),
                                      body.index("const cpages=closingPages(rows);"), body.index("sportLabel="),
                                      body.index("policy();"), body.index("const ac=autoClaim();"),
                                      body.index("const ne=storeClosings(cpages);"),
                                      body.index('$("logNote").textContent=loadLogNote(ac,ne);'))
    assert concat < tr < cp < lab < pol < ac < st < note
    assert "rows=[]; shadowRows=[]; fileParlays=null; refusedFiles=[]; ticketRows=[];" in body
    assert "did.closings" not in body[:body.index("\n", body.index("const did="))] and body.index("did.closings") > st
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
    closing loaded together then find their slate claims older than the ledger: three covered games hold no claim from
    before their page, and a slate row of this load called each (⚠). A closing whose counts_source is the ledger
    summary's prints no 144 note."""
    summary = closing(src="ledger summary bd_ledger_summary.json generated 2026-10-19T10:00:00Z")
    got = _node(tmp_path, r'''
await loadDocs([T_doc(CN,C)]);
await loadDocs([T_doc(SN,S),T_doc(CN,C)]);
const n=T_note(); T_reset();
await loadDocs([T_doc(CN,C3)]);
T_out({n,n3:T_note()});''', C3=summary, **_docs())
    assert got["n"].endswith(" · ⚠ 3 of 6 covered game(s) hold no claim from before their page in this browser's ledger:"
                             " nothing there to mark. A local Cockpit keeps its own ledger: import the ledger, then load."
                             + COUNTS_NOTE)
    assert "counts_source" not in got["n3"] and got["n3"].endswith("import the ledger, then load.")


def test_r14_the_runbook_names_the_order_and_the_version_skew_line():
    doc = " ".join((ROOT / "docs" / "specs" / "exports-mirror.md").read_text(encoding="utf-8").split())
    assert "**Closings: import the ledger, then load (#431, ARCHITECT 2026-10-20, addendum 145 item 3(b) R14).**" in doc
    # COMMIT 1 (verify_cockpit #3): closing files come in through the file picker or Load latest from host; no laptop
    # control is named before the commit that adds it
    assert ("A closing file loaded into the Cockpit (the file picker, or Load latest from host) marks NOT EXECUTED the"
            " claims its page did not repeat") in doc
    assert ("In the local page, first Import ledger (the published page's Export ledger (JSON)), then load the closing"
            " files.") in doc
    assert "the load note says how many covered games hold no claim from before their page" in doc
    para = doc[doc.index("**Closings: import the ledger"):doc.index("**Version skew")]
    assert "control" not in para and "laptop" not in para and "replace the slate rows" not in para
    assert ("Until the published page carries this build, do not import a ledger exported from the local page into the"
            " published page.") in doc
    spec = " ".join((ROOT / "docs" / "specs" / "cockpit-v04-pnl-organ.md").read_text(encoding="utf-8").split())
    assert "Idempotency: keyed on (sport, game, log_date) — re-logging updates, never duplicates." in spec   # verbatim
    assert "is (sport, game, log_date, engine, call_type, pick, parlay slot); the pick joined it by ARCHITECT" \
           " 2026-10-20, addendum 145 item 3(b) R4" in spec
