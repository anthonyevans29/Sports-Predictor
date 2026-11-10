"""THE COCKPIT'S PRIVATE LEDGER STORE AND MIRROR LOADER, the five fixes (ARCHITECT 2026-11-09 16:50 ET, addendum 315
item 2, verbatim in part): "(a) STALE SESSIONS — the ledger carries `rev` (an integer, +1 on every saveLedger) and
`updated_at`; the store's header records `rev`; a store write first reads the header: if the header's rev is not the
rev this page loaded or last wrote, the page RELOADS the store, MERGES by id (calls by id, fills by id, the newer
`updated_at` per record wins; never a silent drop), re-renders, then writes with rev+1. (b) EDITS BEFORE LOAD — while
the store is loading, saveLedger queues (the local copy still saves); when the load lands, the queued local state is
merged into the stored one by the same id-merge and written; the Ledger header says "store: loading… (N edits
queued)". (c) UNLOAD — `pagehide` and `visibilitychange: hidden` flush the pending write at once (no debounce); and on
load the store never overwrites a NEWER local copy: if local.rev > stored.rev, the local copy is written up (the
id-merge first), else the store wins — the current one-way rule becomes rev-ordered. (d) PARTIAL MIRROR LOAD — the
connector loader acts only when EVERY listed file read and parsed; on any failure it keeps the current slate, claims
nothing, and prints which files failed with a "Load the N that read" button that the operator presses knowingly (the
note then says "PARTIAL" in the summary line). (e) CHUNK WRITES (P2) — chunks are written under the new rev's ids
(`ledger_chunks/<rev>_<i>`), the header switches to that rev only after every chunk succeeded, and the previous rev's
chunks are deleted after the switch (a failed write leaves the old rev intact and readable)."
"Tests: the repo copy's test harness for the Cockpit exercises each with a stubbed `claude.use("db")` and
`claude.use("mcp")` (two tabs racing; an edit during load; a hidden-page flush; a 13-file listing with one failing
read; a chunk write failing at chunk 2)."

The page's own code runs under node: the connector and store sections whole (from `const GH_OWNER=` to the
`setTab("desk");` after the store), with the page's own ledger functions, each tab in its own vm context (its own
localStorage, timers, DOM stubs and clock) over ONE shared in-memory db with failure injection. Every record below is
a synthetic fixture.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

COCKPIT = Path(__file__).resolve().parents[1] / "tools" / "cockpit.html"


def _html():
    return COCKPIT.read_text(encoding="utf-8")


def _fn(html, name):
    """The top-level function `name`, whole (braces counted)."""
    m = re.search(r"^(?:async )?function " + name + r"\(", html, re.M)
    assert m, name
    i, depth = html.index("{", m.end()), 0
    for j in range(i, len(html)):
        depth += {"{": 1, "}": -1}.get(html[j], 0)
        if depth == 0:
            return html[m.start():j + 1]
    raise AssertionError(name)


def _line(html, start):
    m = re.search(r"^" + re.escape(start) + r".*$", html, re.M)
    assert m, start
    return m.group(0)


def _page_code():
    html = _html()
    a = html.index('const GH_OWNER="anthonyevans29"')
    b = html.index('setTab("desk");\n', html.index("THE PRIVATE LEDGER STORE"))
    fns = "\n".join(_fn(html, n) for n in ("utcMs", "execP", "auditCall", "markAudit", "emptyLedger", "loadLedger",
                                           "labelLegacy", "saveLedger", "callKey", "instKey", "parlaySig", "better",
                                           "enforceLedger", "dedupeNote"))
    return "\n".join([_line(html, 'const LEDGER_KEY="bd_ledger_v1"'), "let storageOK=true;",
                      _line(html, "const TZ_FLAG="), fns, html[a:b]])


HARNESS = r"""
const vm = require("vm"), fs = require("fs");
const PAGE = fs.readFileSync(process.argv[2], "utf8");
const SCEN = process.argv[3];
const settle = async (n=60) => { for (let i=0;i<n;i++) await new Promise(r=>setImmediate(r)); };
const clone = v => v===undefined?undefined:JSON.parse(JSON.stringify(v));

// addendum 316 item 1: DocumentReference.acquire as the runtime's db.d.ts (contract 0.2.96) types it: acquire({holder,
// ttlMs}) -> {acquired, version?, expiresAt? (RFC 3339, granted or not), holder? (echoed on a grant)}; ttlMs absent/0 =
// 30000, clamped to [1000, 600000]; busy while another holder's lease has not expired; the same holder renews; no
// release verb. Time is the db's clock (shared with the tabs that use it). `lease:false` = an older runtime (no acquire).
function makeDb(opts={}){
  const docs = new Map(), log = [], leases = new Map();
  const clock = opts.clock || {now: Date.parse("2026-11-09T12:00:00Z")};
  const api = { docs, log, leases, clock, failSet:null,
    doc(path){ const ref = { path,
      get: async()=>{ log.push(["get",path]); const v=docs.get(path); return {exists:v!==undefined, data:()=>clone(v)}; },
      set: async(d)=>{ log.push(["set",path,d&&d.writer]);
        if(api.failSet&&api.failSet(path)){ const e=new Error("injected failure"); e.code="unavailable"; throw e; }
        docs.set(path, clone(d)); },
      delete: async()=>{ log.push(["delete",path]); docs.delete(path); } };
      if (opts.lease!==false) ref.acquire = async({holder, ttlMs})=>{ log.push(["acquire",path,holder]);
        const now = clock.now, cur = leases.get(path), ttl = Math.min(600000, Math.max(1000, ttlMs||30000));
        if (cur && cur.holder!==holder && cur.exp>now) return {acquired:false, expiresAt:new Date(cur.exp).toISOString()};
        leases.set(path, {holder, exp:now+ttl}); return {acquired:true, holder, version:1, expiresAt:new Date(now+ttl).toISOString()}; };
      return ref; } };
  return api;
}
// a stored ledger in the page's layout: rev null = a v2 header (no rev, chunks ledger_chunks/<i>)
function seedStore(db, L, rev, chunk=120000){
  const txt = JSON.stringify(L), n = Math.max(1, Math.ceil(txt.length/chunk));
  for (let i=0;i<n;i++) db.docs.set(rev==null?`ledger_chunks/${i}`:`ledger_chunks/${rev}_${i}`, {i,n,data:txt.slice(i*chunk,(i+1)*chunk)});
  const h = {chunks:n,length:txt.length,saved_at:"2026-11-09T10:00:00.000Z"}; if (rev!=null) h.rev = rev;
  db.docs.set("cockpit/ledger", h);
}
// the page's chunk id for a header: v2 (no rev) ledger_chunks/<i>; a written header ledger_chunks/<rev>_<i>_<writer>
const chunkId = (h,i) => h.rev==null?`ledger_chunks/${i}`:h.writer?`ledger_chunks/${h.rev}_${i}_${h.writer}`:`ledger_chunks/${h.rev}_${i}`;
async function readStore(db){
  const h = db.docs.get("cockpit/ledger"); if(!h) return null;
  let t=""; for(let i=0;i<h.chunks;i++){ const c=db.docs.get(chunkId(h,i)); if(!c) return {head:h,missing:i}; t+=c.data; }
  return {head:clone(h), L:JSON.parse(t), ok:t.length===h.length};
}

function makeTab(db, opts={}){
  const clock = opts.clock || db.clock || {now: Date.parse("2026-11-09T12:00:00Z")};
  const els = {};
  const el = id => els[id] || (els[id] = {id, textContent:"", hidden:false, value:"", checked:false, disabled:false,
    listeners:{}, addEventListener(t,f){ (this.listeners[t]=this.listeners[t]||[]).push(f); }});
  const store = new Map(Object.entries(opts.local||{}));
  const ls = {fail: opts.lsFail || null};   // a key whose setItem throws (browser storage full)
  const localStorage = { getItem:k=>store.has(k)?store.get(k):null, removeItem:k=>store.delete(k),
    setItem:(k,v)=>{ if(ls.fail&&ls.fail(k)){ const e=new Error("QuotaExceededError: the quota has been exceeded"); e.name="QuotaExceededError"; throw e; } store.set(k,String(v)); } };
  const timers = new Map(); let tid = 0;
  const setTimeout = (f,ms)=>{ const id=++tid; timers.set(id,{f,ms}); return id; };
  const clearTimeout = id=>{ timers.delete(id); };
  const winL = {}, docL = {};
  const window = { addEventListener:(t,f)=>{ (winL[t]=winL[t]||[]).push(f); } };
  const document = { visibilityState:"visible", addEventListener:(t,f)=>{ (docL[t]=docL[t]||[]).push(f); } };
  class FakeDate extends Date { constructor(...a){ if(a.length) super(...a); else super(clock.now); } static now(){ return clock.now; } }
  const calls = {loadDocs:[], ingestResultsDocs:[], ingestWindowText:[], renderLedger:0};
  const gate = opts.gate || Promise.resolve();
  const claude = { use: async name => { if(name==="db"){ await gate; return db; } if(name==="mcp") return opts.mcp||null; return null; } };
  const ctx = vm.createContext({ console, JSON, Math, Promise, Map, Set, Array, Object, String, Number, Error, isFinite,
    TextDecoder, Uint8Array, atob, setImmediate, Date:FakeDate, localStorage, window, document, claude, setTimeout, clearTimeout,
    $: el, renderProgress:()=>({}), renderLedger:()=>{ calls.renderLedger++; },
    loadDocs: async fs=>{ calls.loadDocs.push(fs.map(f=>f.name)); return {coverage:0,refused:[]}; },
    ingestResultsDocs: async fs=>{ calls.ingestResultsDocs.push(fs.map(f=>f.name)); },
    ingestWindowText: t=>{ calls.ingestWindowText.push(t.length); return true; } });
  vm.runInContext(PAGE, ctx, {filename:"cockpit-store.js"});
  const ev = (s)=>vm.runInContext(s, ctx);
  return { ctx, ev, els, el, store, ls, timers, clock, calls, winL, docL, document,
    note: ()=>el("ledgerStoreNote").textContent, gh: ()=>el("ghNote").textContent,
    local: ()=>JSON.parse(store.get("bd_ledger_v1")||"null"),
    fireTimers: async()=>{ const all=[...timers.entries()]; for(const [id,t] of all){ timers.delete(id); t.f(); } await settle(); },
    // fire timers until none is left, each moving the clock by its own delay (the lease's busy retries wait on these)
    drain: async(max=40)=>{ for(let k=0;k<max&&timers.size;k++){ const all=[...timers.entries()];
      for(const [id,t] of all){ timers.delete(id); clock.now += t.ms||0; t.f(); } await settle(); } },
    edit: (fn)=>{ ctx.__fn = fn; ev("{ const L=loadLedger(); __fn(L); saveLedger(L); }"); },
  };
}
function call(id, extra={}){ return Object.assign({id, sport:"NFL", game:`${id} away @ ${id} home`, home:`${id} home`, away:`${id} away`,
  log_date:"2026-11-09", engine:"model_edge", call_type:"straight", pick:"HOME", status:"open", kickoff:"2026-11-20T18:00:00Z"}, extra); }
const ids = L => (L.calls||[]).map(c=>c.id).sort();

const S = {};
// (a) two tabs racing: both edits survive, the rev rises on every write, nothing is silently dropped
S.race = async()=>{
  const clock = {now: Date.parse("2026-11-09T12:00:00Z")}, db = makeDb({clock});
  seedStore(db, {meta:{policy_version:"v1.2"}, calls:[call("c1")], fills:[{id:"f1",ticker:"KX-1",qty:1}], rev:3}, 3);
  const A = makeTab(db,{clock}), B = makeTab(db,{clock}); await settle();
  const boot = {A:A.ev("ledgerStoreRev"), B:B.ev("ledgerStoreRev"), Anote:A.note()};
  clock.now += 1000; A.edit(L=>{ L.calls.push(call("a2")); });
  clock.now += 1000; B.edit(L=>{ L.calls.push(call("b2")); L.fills.push({id:"f2",ticker:"KX-2",qty:2}); });
  await A.fireTimers(); const afterA = await readStore(db);
  await B.drain(); const afterB = await readStore(db), Bnote = B.note();      // B waits out A's lease (316 item 1)
  // a conflicting edit of one record: A grades c1 later than B's reprice of it; the newer updated_at wins
  clock.now += 1000; B.edit(L=>{ L.calls.find(c=>c.id==="c1").market_p=0.55; });
  await B.fireTimers();
  clock.now += 1000; A.edit(L=>{ const c=L.calls.find(c=>c.id==="c1"); c.status="graded"; c.result="W"; });
  await A.drain(); const afterA2 = await readStore(db);
  return { boot, afterA:{rev:afterA.head.rev, ids:ids(afterA.L)}, afterB:{rev:afterB.head.rev, ids:ids(afterB.L), fills:afterB.L.fills.map(f=>f.id).sort(), ok:afterB.ok},
    Bnote, Anote2:A.note(), afterA2:{rev:afterA2.head.rev, writer:afterA2.head.writer, ids:ids(afterA2.L), c1:afterA2.L.calls.find(c=>c.id==="c1")},
    Alocal:ids(A.local()), Blocal:ids(B.local()), renders:{A:A.calls.renderLedger, B:B.calls.renderLedger},
    keys:[...db.docs.keys()].sort() };
};
// (b) an edit during the load: queued, the note says so, merged after the load and written
S.queued = async()=>{
  const db = makeDb(); let open; const gate = new Promise(r=>open=r);
  seedStore(db, {meta:{policy_version:"v1.2"}, calls:[call("s1")], rev:3}, 3);
  const T = makeTab(db,{gate}); await settle();
  const state0 = T.ev("ledgerStoreState");
  T.edit(L=>{ L.calls.push(call("q1")); });
  const note1 = T.note();
  T.edit(L=>{ L.calls.push(call("q2")); });
  const note2 = T.note(), localDuring = ids(T.local()), timersDuring = T.timers.size, writesDuring = db.log.filter(x=>x[0]==="set").length;
  open(); await settle();
  const st = await readStore(db);
  return { state0, note1, note2, localDuring, timersDuring, writesDuring, stored:{rev:st.head.rev, ids:ids(st.L)}, local:ids(T.local()),
    note:T.note(), queued:T.ev("ledgerQueued"), state:T.ev("ledgerStoreState") };
};
// (c) a hidden page flushes at once: no timer runs
S.hidden = async()=>{
  const db = makeDb(); seedStore(db, {meta:{}, calls:[call("s1")], rev:1}, 1);
  const T = makeTab(db); await settle();
  T.edit(L=>{ L.calls.push(call("h1")); });
  const armed = T.timers.size;
  T.document.visibilityState = "hidden"; for (const f of (T.docL.visibilitychange||[])) f(); await settle();
  const st1 = await readStore(db), timersAfter1 = T.timers.size;
  T.document.visibilityState = "visible";
  T.edit(L=>{ L.calls.push(call("h2")); });
  const armed2 = T.timers.size;
  for (const f of (T.winL.pagehide||[])) f(); await settle();
  const st2 = await readStore(db), timersAfter2 = T.timers.size;
  // a visible visibilitychange does not flush
  T.edit(L=>{ L.calls.push(call("h3")); });
  for (const f of (T.docL.visibilitychange||[])) f(); await settle();
  const st3 = await readStore(db);
  return { armed, timersAfter1, st1:{rev:st1.head.rev, ids:ids(st1.L)}, armed2, timersAfter2, st2:{rev:st2.head.rev, ids:ids(st2.L)},
    st3:{rev:st3.head.rev, ids:ids(st3.L)} };
};
// (c) the rev-ordered load: a newer local copy is merged and written up; an older one yields to the store (set aside, named)
S.revorder = async()=>{
  const db1 = makeDb(); seedStore(db1, {meta:{}, calls:[call("s1")], rev:3}, 3);
  const newer = {meta:{}, calls:[call("s1"), call("l1")], rev:5};
  const N = makeTab(db1,{local:{bd_ledger_v1:JSON.stringify(newer)}}); await settle();
  const st = await readStore(db1);
  const db2 = makeDb(); seedStore(db2, {meta:{}, calls:[call("s1"), call("s2")], rev:3}, 3);
  const older = {meta:{}, calls:[call("s1"), call("l9")], rev:2};
  const O = makeTab(db2,{local:{bd_ledger_v1:JSON.stringify(older)}}); await settle();
  const st2 = await readStore(db2);
  return { newer:{rev:st.head.rev, ids:ids(st.L), note:N.note(), local:ids(N.local())},
    older:{rev:st2.head.rev, ids:ids(st2.L), note:O.note(), local:ids(O.local()), writes:db2.log.filter(x=>x[0]==="set").length,
      aside:JSON.parse(O.store.get("bd_ledger_v1_set_aside")||"null")} };
};
// (e) a chunk write failing at chunk 2: the header stays, the old rev reads intact; a later success switches and deletes
S.chunks = async()=>{
  const db = makeDb();
  const big = {meta:{}, calls:[call("s1",{memo:"x".repeat(300000)})], rev:3};
  seedStore(db, big, 3);
  const T = makeTab(db); await settle();
  const boot = {rev:T.ev("ledgerStoreRev"), note:T.note()};
  T.edit(L=>{ L.calls.push(call("e1")); });
  const localRev = T.local().rev;
  db.failSet = p => p.startsWith(`ledger_chunks/${localRev}_2_`);
  await T.fireTimers();
  const failed = await readStore(db), failNote = T.note();
  const keysAfterFail = [...db.docs.keys()].sort();
  // a second tab reads the old rev whole
  const R = makeTab(db); await settle();
  const readerIds = ids(R.local()), readerNote = R.note();
  db.failSet = null;
  T.edit(L=>{ L.calls.push(call("e2")); });
  await T.fireTimers();
  const ok = await readStore(db);
  return { boot, localRev, failed:{rev:failed.head.rev, chunks:failed.head.chunks, ok:failed.ok, ids:ids(failed.L)}, failNote, keysAfterFail,
    readerIds, readerNote, ok:{rev:ok.head.rev, writer:ok.head.writer, chunks:ok.head.chunks, ok:ok.ok, ids:ids(ok.L)}, keys:[...db.docs.keys()].sort() };
};
// migration: a v2 header (no rev, chunks ledger_chunks/<i>) reads, and the next save upgrades it
S.legacy = async()=>{
  const db = makeDb(); seedStore(db, {meta:{}, calls:[call("v1"), call("v2")]}, null);
  const T = makeTab(db); await settle();
  const boot = {rev:T.ev("ledgerStoreRev"), note:T.note(), local:ids(T.local()), localRev:T.local().rev};
  T.edit(L=>{ L.calls.push(call("v3")); });
  await T.fireTimers();
  const st = await readStore(db);
  return { boot, st:{rev:st.head.rev, ids:ids(st.L), ok:st.ok}, writer:st.head.writer, keys:[...db.docs.keys()].sort(), note:T.note() };
};
// (d) a 13-file listing with one failing read
S.partial = async()=>{
  const names = [];
  for (let i=1;i<=11;i++) names.push(`desk_${String(i).padStart(2,"0")}.json`);
  names.push("nfl_results.json", "window_24h.json");
  const failing = "desk_07.json";
  const mcp = { listTools: async()=>({servers:[{server:"GitHub", tools:[{name:"get_file_contents"}]}]}),
    callTool: async(server, tool, args)=>{
      if (args.path==="host/latest") return JSON.stringify(names.map(n=>({name:n, path:`host/latest/${n}`, type:"file"})));
      const n = args.path.split("/").pop();
      if (n===failing){ const e=new Error("GitHub did not answer"); e.code="upstream_error"; throw e; }
      return JSON.stringify({kind:"x", name:n}); } };
  const db = makeDb(); seedStore(db, {meta:{}, calls:[call("s1")], rev:1}, 1);
  const T = makeTab(db,{mcp}); await settle();
  const ledgerBefore = T.store.get("bd_ledger_v1"), dbWritesBefore = db.log.filter(x=>x[0]==="set").length;
  await T.ev('ghLoadFolder("host/latest")'); await settle();
  const before = { note:T.gh(), btnHidden:T.el("ghPartialBtn").hidden, btnText:T.el("ghPartialBtn").textContent,
    loadDocs:T.calls.loadDocs.length, results:T.calls.ingestResultsDocs.length, window:T.calls.ingestWindowText.length,
    ledgerSame:T.store.get("bd_ledger_v1")===ledgerBefore, dbWrites:db.log.filter(x=>x[0]==="set").length-dbWritesBefore };
  for (const f of T.el("ghPartialBtn").listeners.click) await f(); await settle();
  const after = { note:T.gh(), btnHidden:T.el("ghPartialBtn").hidden, loadDocs:T.calls.loadDocs, results:T.calls.ingestResultsDocs,
    window:T.calls.ingestWindowText.length };
  // a second press of the (now hidden) button loads nothing again
  for (const f of T.el("ghPartialBtn").listeners.click) await f(); await settle();
  // a clean 13-of-13 load acts at once, and its note says nothing PARTIAL
  const mcp2 = Object.assign({}, mcp, {callTool: async(s,t,a)=>a.path==="host/latest"?JSON.stringify(names.map(n=>({name:n,path:`host/latest/${n}`,type:"file"}))):JSON.stringify({ok:1})});
  const C = makeTab(makeDb(),{mcp:mcp2}); await settle();
  await C.ev('ghLoadFolder("host/latest")'); await settle();
  return { before, after, loadsAfterSecondPress:T.calls.loadDocs.length,
    clean:{note:C.gh(), loadDocs:C.calls.loadDocs.map(x=>x.length), btnHidden:C.el("ghPartialBtn").hidden} };
};
// ---- the review of this PR: one scenario per defect ----
// a per-tab view of the shared db: `before(op,path)` may delay (await a gate) or throw
function view(db, before){ return { clock:db.clock, doc(path){ const d=db.doc(path), r={
  get: async()=>{ await before("get",path); return d.get(); },
  set: async(v)=>{ await before("set",path); return d.set(v); },
  delete: async()=>{ await before("delete",path); return d.delete(); } };
  if (d.acquire) r.acquire = async(o)=>{ await before("acquire",path); return d.acquire(o); };
  return r; } }; }
const chunkKeys = db => [...db.docs.keys()].filter(k=>k.startsWith("ledger_chunks/")).sort();
// R1: an id-merge whose save collapses two calls of one position (one log date per device) names the collapse and keeps
// the dropped copy aside; on the boot path (local rev > store rev) and on the write path (another tab's write)
S.collapse = async()=>{
  const pos = {sport:"NFL", game:"A @ B", home:"B", away:"A", engine:"elo", call_type:"straight", pick:"HOME", kickoff:"2026-11-15T18:00:00Z", status:"open"};
  const s = Object.assign({}, pos, {id:"NFL|A @ B|2026-11-08|elo|straight|", log_date:"2026-11-08", exec_market_p:0.55, executed_at:"2026-11-08T12:00:00Z", updated_at:"2026-11-08T12:00:00Z"});
  const l = Object.assign({}, pos, {id:"NFL|A @ B|2026-11-09|elo|straight|", log_date:"2026-11-09", exec_market_p:0.60, executed_at:"2026-11-09T12:00:00Z", updated_at:"2026-11-09T12:00:00Z"});
  const db = makeDb(); seedStore(db, {meta:{}, calls:[s], rev:4}, 4);
  const T = makeTab(db,{local:{bd_ledger_v1:JSON.stringify({meta:{}, calls:[l], rev:5})}}); await settle();
  const st = await readStore(db), aside = JSON.parse(T.store.get("bd_ledger_v1_set_aside")||"null");
  const boot = {note:T.note(), stored:st.L.calls.map(c=>[c.log_date,c.exec_market_p]), aside:aside&&aside.calls.map(c=>[c.log_date,c.exec_market_p])};
  // the write path: tab U holds the 11-09 copy as an edit while tab V's write put the 11-08 copy in the store
  const db2 = makeDb(); seedStore(db2, {meta:{}, calls:[call("c1")], rev:2}, 2);
  const U = makeTab(db2), V = makeTab(db2); await settle();
  V.edit(L=>{ L.calls.push(Object.assign({}, s)); }); await V.fireTimers();
  U.edit(L=>{ L.calls.push(Object.assign({}, l)); }); await U.drain();
  const st2 = await readStore(db2), aside2 = JSON.parse(U.store.get("bd_ledger_v1_set_aside")||"null");
  return {boot, write:{note:U.note(), stored:st2.L.calls.filter(c=>c.game==="A @ B").map(c=>c.log_date), aside:aside2&&aside2.calls.map(c=>c.log_date)}};
};
// R2: a pagehide flush the browser ends between the chunk writes and the header switch leaves chunks no header names;
// the journal in this browser sweeps them after a later confirmed switch
S.orphans = async()=>{
  const clock = {now: Date.parse("2026-11-09T12:00:00Z")}, db = makeDb({clock});
  const big = n => Array.from({length:n},(_,i)=>call("c"+i,{note:"x".repeat(900)}));
  seedStore(db, {meta:{}, calls:big(300), rev:3}, 3);
  let sets = 0; const never = new Promise(()=>{});
  const A = makeTab(view(db, async(op,path)=>{ if(op==="set"&&path.startsWith("ledger_chunks/")&&++sets===3) await never; }),{clock}); await settle();
  clock.now += 1000; A.edit(L=>{ L.calls.push(call("a1")); });
  for (const f of (A.winL.pagehide||[])) f(); await settle();
  const killed = {head:db.docs.get("cockpit/ledger").rev, partial:chunkKeys(db).filter(k=>k.startsWith("ledger_chunks/4_")).length,
    journal:JSON.parse(A.store.get("bd_ledger_v1_store_journal")||"[]").map(e=>[e.rev,e.n])};
  // the page is gone; the browser reopens it a minute later with the same localStorage
  clock.now += 60*1000;
  const B = makeTab(db,{clock, local:Object.fromEntries(A.store)}); await settle();
  const st = await readStore(db);
  const reopened = {rev:st.head.rev, ids:st.L.calls.length, hasA1:ids(st.L).includes("a1"), stale:chunkKeys(db).filter(k=>k.startsWith("ledger_chunks/4_")).length};
  // past the journal's age, the next confirmed switch deletes them
  clock.now += 11*60*1000; B.edit(L=>{ L.calls.push(call("b1")); }); await B.fireTimers();
  const st2 = await readStore(db);
  return {killed, reopened, after:{rev:st2.head.rev, note:B.note(), keys:chunkKeys(db), writer:st2.head.writer, chunks:st2.head.chunks,
    journal:JSON.parse(B.store.get("bd_ledger_v1_store_journal")||"[]").length}};
};
// R3: two writers of the same rev; one fails partway after the other switched the header: the header's chunks are untouched
S.samerev = async()=>{
  const clock = {now: Date.parse("2026-11-09T12:00:00Z")}, db = makeDb({clock, lease:false});   // writers not using acquire
  const big = n => Array.from({length:n},(_,i)=>call("c"+i,{note:"x".repeat(900)}));
  seedStore(db, {meta:{policy_version:"v1.2"}, calls:big(300), rev:3}, 3);
  let releaseB, gateB = new Promise(r=>releaseB=r), bSets = 0;
  const A = makeTab(db,{clock});
  const B = makeTab(view(db, async(op,path)=>{
    if(op==="set"&&path.startsWith("ledger_chunks/")){ await gateB; if(++bSets===2){ const e=new Error("injected"); e.code="unavailable"; throw e; } } }),{clock});
  await settle();
  clock.now += 1000; A.edit(L=>{ L.calls.push(call("a2")); });
  clock.now += 1000; B.edit(L=>{ L.calls[0].note="y".repeat(5000); L.calls.push(call("b2")); });
  const tb=[...B.timers.values()]; B.timers.clear(); tb.forEach(t=>t.f()); await settle();   // B read header rev 3, waits at its chunk 0
  await A.fireTimers();                                                                    // A writes rev 4 whole, the header switches
  const hA = db.docs.get("cockpit/ledger");
  releaseB(); await settle();                                                              // B writes its chunk 0, fails at its chunk 1
  const hB = db.docs.get("cockpit/ledger"), Bnote = B.note();
  const C = makeTab(db,{clock}); await settle();
  const have = new Set(ids(C.local()));
  const missing = ["a2","b2"].concat(Array.from({length:300},(_,i)=>"c"+i)).filter(x=>!have.has(x));
  // B saves again: it reads A's rev 4, merges, writes rev 5 holding both tabs' edits
  clock.now += 1000; B.edit(L=>{ L.calls.push(call("b3")); }); await B.fireTimers();
  const st = await readStore(db);
  return {headerKept: JSON.stringify(hA)===JSON.stringify(hB), rev:hB.rev, Bnote, Cnote:C.note(), missing,
    c0:(C.local().calls.find(c=>c.id==="c0")||{}).note.slice(0,3),
    after:{rev:st.head.rev, ok:st.ok, n:st.L.calls.length, has:["a2","b2","b3"].filter(x=>ids(st.L).includes(x)),
      c0:st.L.calls.find(c=>c.id==="c0").note.slice(0,3), note:B.note()}};
};
// R3b: a header whose chunk is another write's (a forged mix) is refused, never read as the ledger, and never written over at boot
S.mixed = async()=>{
  const db = makeDb(); seedStore(db, {meta:{}, calls:[call("m1")], rev:3}, 3);
  const T0 = makeTab(db); await settle(); T0.edit(L=>{ L.calls.push(call("m2")); }); await T0.fireTimers();
  const h = db.docs.get("cockpit/ledger"), k = `ledger_chunks/${h.rev}_0_${h.writer}`, c = db.docs.get(k);
  db.docs.set(k, Object.assign({}, c, {writer:"zzzzzzzzzz"}));
  const sets = db.log.filter(x=>x[0]==="set").length;
  const T = makeTab(db); await settle();
  return {note:T.note(), state:T.ev("ledgerStoreState"), sets:db.log.filter(x=>x[0]==="set").length-sets, local:T.local()&&ids(T.local())};
};
// R4: two tabs whose flushes start together, both from rev 3: the loser's post-switch read sees the other's header,
// merges and writes again, so the store holds both edits with no further edit
S.collide = async()=>{
  const clock = {now: Date.parse("2026-11-09T12:00:00Z")}, db = makeDb({clock, lease:false});   // writers not using acquire
  seedStore(db, {meta:{policy_version:"v1.2"}, calls:[call("c1")], rev:3}, 3);
  const A = makeTab(db,{clock}), B = makeTab(db,{clock}); await settle();
  clock.now += 1000; A.edit(L=>{ L.calls.push(call("a2")); });
  clock.now += 1000; B.edit(L=>{ L.calls.push(call("b2")); });
  const ta=[...A.timers.values()], tb=[...B.timers.values()]; A.timers.clear(); B.timers.clear();
  ta.forEach(t=>t.f()); tb.forEach(t=>t.f()); await settle(200);
  const s1 = await readStore(db);
  const r = {afterBoth:{rev:s1.head.rev, ids:ids(s1.L), ok:s1.ok}, Anote:A.note(), Bnote:B.note(), chunks:chunkKeys(db).length, chunksOfHead:s1.head.chunks};
  // the tab whose header the store does not hold merges on its next write too (identity, not the rev number alone)
  clock.now += 1000; A.edit(L=>{ L.calls.push(call("a3")); }); await A.fireTimers();
  clock.now += 1000; B.edit(L=>{ L.calls.push(call("b3")); }); await B.fireTimers();
  const s2 = await readStore(db); r.after = {rev:s2.head.rev, ids:ids(s2.L)};
  const C = makeTab(db,{clock}); await settle(); r.C = ids(C.local());
  return r;
};
// R6: a v2 store an interrupted v2 write left torn (the header's length no longer matches): the next save writes this
// browser's copy up under a new rev, keeps the unreadable chunks, and says so; a fresh tab then reads the new rev
S.torn = async()=>{
  const db = makeDb(); seedStore(db, {meta:{}, calls:[call("c1")]}, null);
  const h = db.docs.get("cockpit/ledger"); h.length = h.length + 5;
  const T = makeTab(db,{local:{bd_ledger_v1:JSON.stringify({meta:{}, calls:[call("c1"), call("c2")]})}}); await settle();
  const boot = T.note(), setsBoot = db.log.filter(x=>x[0]==="set").length;
  T.edit(L=>{ L.calls.push(call("c3")); }); await T.fireTimers();
  const st = await readStore(db), note = T.note();
  T.edit(L=>{ L.calls.push(call("c4")); }); await T.fireTimers();
  const st2 = await readStore(db);
  const R = makeTab(db); await settle();
  return {boot, setsBoot, note, first:{rev:st.head.rev, ids:ids(st.L), ok:st.ok}, legacyKept:db.docs.has("ledger_chunks/0"),
    second:{rev:st2.head.rev, ids:ids(st2.L)}, note2:T.note(), fresh:ids(R.local())};
};
// ---- the review of this PR (Codex, round 1) ----
// C1: an edit reverted (same body as the store's, a newer stamp) keeps its newer stamp through the merge, so a third
// tab's differing copy stamped between the two cannot win a later merge and bring the reverted data back
S.revert = async()=>{
  const clock = {now: Date.parse("2026-11-09T12:00:00Z")}, db = makeDb({clock});
  const t1 = "2026-11-09T11:00:00.000Z";
  seedStore(db, {meta:{policy_version:"v1.2"}, calls:[call("x1",{market_p:0.50, updated_at:t1})], rev:3}, 3);
  const A = makeTab(db,{clock}), B = makeTab(db,{clock}), C = makeTab(db,{clock}); await settle();
  clock.now += 1000; A.edit(L=>{ L.calls.push(call("a2")); }); await A.fireTimers();       // the store moves on (x1 untouched, t1)
  clock.now += 1000; const t2 = new Date(clock.now).toISOString();
  C.edit(L=>{ L.calls.find(c=>c.id==="x1").market_p=0.70; });                               // C: a differing x1 at t2
  clock.now += 1000; B.edit(L=>{ L.calls.find(c=>c.id==="x1").market_p=0.60; });
  clock.now += 1000; const t3 = new Date(clock.now).toISOString();
  B.edit(L=>{ L.calls.find(c=>c.id==="x1").market_p=0.50; });                               // B reverts: the stored body, at t3
  const bLocal = B.local().calls.find(c=>c.id==="x1");
  await B.drain(); const afterB = (await readStore(db)).L.calls.find(c=>c.id==="x1");
  await C.drain(); const st = await readStore(db), afterC = st.L.calls.find(c=>c.id==="x1");
  return {t1, t2, t3, bLocal:{p:bLocal.market_p, at:bLocal.updated_at}, afterB:{p:afterB.market_p, at:afterB.updated_at},
    afterC:{p:afterC.market_p, at:afterC.updated_at}, ids:ids(st.L), Cnote:C.note()};
};
// C2: a listing where every read fails names each failed file in the note, and nothing is acted on
S.allfail = async()=>{
  const names = ["desk_01.json", "desk_02.json"];
  const mcp = { listTools: async()=>({servers:[{server:"GitHub", tools:[{name:"get_file_contents"}]}]}),
    callTool: async(server, tool, args)=>{
      if (args.path==="host/latest") return JSON.stringify(names.map(n=>({name:n, path:`host/latest/${n}`, type:"file"})));
      if (args.path.endsWith("desk_01.json")){ const e=new Error("GitHub did not answer"); e.code="upstream_error"; throw e; }
      return "<html>not json</html>"; } };
  const db = makeDb(); seedStore(db, {meta:{}, calls:[call("s1")], rev:1}, 1);
  const T = makeTab(db,{mcp}); await settle();
  const ledgerBefore = T.store.get("bd_ledger_v1"), dbWritesBefore = db.log.filter(x=>x[0]==="set").length;
  await T.ev('ghLoadFolder("host/latest")'); await settle();
  const firstErr = T.ev('(()=>{ const e=new Error("GitHub did not answer"); e.code="upstream_error"; return ghErrorText(e,"host/latest"); })()');
  return { note:T.gh(), firstErr, btnHidden:T.el("ghPartialBtn").hidden, partial:T.ev("ghPartial"),
    loadDocs:T.calls.loadDocs.length, results:T.calls.ingestResultsDocs.length, window:T.calls.ingestWindowText.length,
    ledgerSame:T.store.get("bd_ledger_v1")===ledgerBefore, dbWrites:db.log.filter(x=>x[0]==="set").length-dbWritesBefore };
};
// C3: a torn v2 store whose first replacement write fails at a chunk: the next save reads the torn header again and
// keeps its unreadable chunks (keepOld), never deleting them unread
S.tornretry = async()=>{
  const db = makeDb(); seedStore(db, {meta:{}, calls:[call("c1")]}, null);
  const h = db.docs.get("cockpit/ledger"); h.length = h.length + 5;
  const T = makeTab(db,{local:{bd_ledger_v1:JSON.stringify({meta:{}, calls:[call("c1"), call("c2")]})}}); await settle();
  db.failSet = p => p.startsWith("ledger_chunks/") && p !== "ledger_chunks/0";
  T.edit(L=>{ L.calls.push(call("c3")); }); await T.fireTimers();
  const failNote = T.note(), headAfterFail = clone(db.docs.get("cockpit/ledger")), keptAfterFail = db.docs.has("ledger_chunks/0");
  db.failSet = null;
  T.edit(L=>{ L.calls.push(call("c4")); }); await T.fireTimers();
  const st = await readStore(db);
  return {failNote, headAfterFail:headAfterFail.rev===undefined, keptAfterFail, note:T.note(), legacyKept:db.docs.has("ledger_chunks/0"),
    second:{rev:st.head.rev, ids:ids(st.L), ok:st.ok}};
};
// ---- addendum 316 (ARCHITECT 2026-11-09 19:00 ET): the ruled fix, one scenario per tested part ----
const sets = (db, from=0) => db.log.slice(from).filter(x=>x[0]==="set").map(x=>[x[1]==="cockpit/ledger"?"H":x[1].startsWith("ledger_chunks/")?"C":x[1], x[2]||null]);
// 1: two tabs contending for the lease: both flush at once from rev 3; A holds it, B is busy (does not write), says so,
// retries after A's lease and saves over A's header with both edits; no header switch of one interleaves the other's
S.contend = async()=>{
  const db = makeDb(), clock = db.clock;
  seedStore(db, {meta:{policy_version:"v1.2"}, calls:[call("c1")], rev:3}, 3);
  const A = makeTab(db), B = makeTab(db); await settle();
  const tabA = A.ev("LEDGER_TAB"), tabB = B.ev("LEDGER_TAB");
  clock.now += 1000; A.edit(L=>{ L.calls.push(call("a2")); });
  clock.now += 1000; B.edit(L=>{ L.calls.push(call("b2")); });
  const mark = db.log.length;
  const ta=[...A.timers.values()], tb=[...B.timers.values()]; A.timers.clear(); B.timers.clear();
  ta.forEach(t=>t.f()); tb.forEach(t=>t.f()); await settle(200);
  const s1 = await readStore(db);
  const mid = {ids:ids(s1.L), rev:s1.head.rev, Bnote:B.note(), Bwaiting:[...B.timers.values()].map(t=>t.ms), Bsaving:B.ev("ledgerStoreSaving"),
    Bsets:sets(db, mark).filter(x=>x[1]&&x[1]!==s1.head.writer).length, Anote:A.note()};
  const c0 = clock.now; await B.drain(); const waited = clock.now - c0;
  const s2 = await readStore(db);
  const acq = db.log.slice(mark).filter(x=>x[0]==="acquire").map(x=>x[2]===tabA?"A":x[2]===tabB?"B":"?");
  return {mid, waited, acq, seq:sets(db, mark), after:{ids:ids(s2.L), rev:s2.head.rev, ok:s2.ok, writer:s2.head.writer, chunks:s2.head.chunks},
    Bnote:B.note(), chunkKeys:chunkKeys(db), Alocal:ids(A.local()), Blocal:ids(B.local()), pending:B.ev("ledgerStorePending")};
};
// 1: the busy path exhausting its five retries: NOT saved, the local copy stands, the pending flag stays set; the next
// edit retries and saves both edits; a lease expiring sooner than 2 s is retried just past its expiresAt
S.exhaust = async()=>{
  const db = makeDb(), clock = db.clock;
  seedStore(db, {meta:{}, calls:[call("s1")], rev:3}, 3);
  const T = makeTab(db); await settle();
  const tab = T.ev("LEDGER_TAB");
  db.leases.set("cockpit/ledger", {holder:"another-tab", exp:clock.now+600000});
  clock.now += 1000; T.edit(L=>{ L.calls.push(call("e1")); });
  const mark = db.log.length;
  await T.fireTimers(); const busyNote = T.note();
  const c0 = clock.now; await T.drain(); const waited = clock.now - c0;
  const st1 = await readStore(db);
  const r1 = {note:T.note(), busyNote, waited, tries:db.log.slice(mark).filter(x=>x[0]==="acquire"&&x[2]===tab).length,
    sets:sets(db, mark).length, stored:{rev:st1.head.rev, ids:ids(st1.L)}, local:ids(T.local()), pending:T.ev("ledgerStorePending"),
    saving:T.ev("ledgerStoreSaving"), timers:T.timers.size};
  // the other tab's lease now ends 500 ms from now: the retry waits until its expiresAt, not 2 s
  db.leases.set("cockpit/ledger", {holder:"another-tab", exp:clock.now+500});
  T.edit(L=>{ L.calls.push(call("e2")); });
  await T.fireTimers(); const c1 = clock.now; await T.drain(); const waited2 = clock.now - c1;
  const st2 = await readStore(db);
  return {r1, waited2, after:{rev:st2.head.rev, ids:ids(st2.L), ok:st2.ok}, note:T.note(), pending:T.ev("ledgerStorePending")};
};
// 1: acquire absent (an older runtime): the pre-316 path writes, and the note says there is no lease
S.nolease = async()=>{
  const db = makeDb({lease:false}); seedStore(db, {meta:{}, calls:[call("s1")], rev:2}, 2);
  const T = makeTab(db); await settle();
  T.edit(L=>{ L.calls.push(call("n1")); }); await T.fireTimers();
  const st = await readStore(db);
  return {note:T.note(), stored:{rev:st.head.rev, ids:ids(st.L), ok:st.ok}, timers:T.timers.size, pending:T.ev("ledgerStorePending")};
};
// 1: the ONE re-read after the switch: a writer not using acquire moves the header between this tab's switch and its
// re-read; the write is reported NOT SAVED, the pending flag stays set (no immediate retry), and the next save merges it
S.rogue = async()=>{
  const db = makeDb(); seedStore(db, {meta:{}, calls:[call("c1")], rev:3}, 3);
  let armed = false, switched = false;
  const rogueL = {meta:{}, calls:[call("c1"), call("r1")], rev:9};
  const T = makeTab(view(db, async(op,path)=>{
    if(!armed||path!=="cockpit/ledger") return;
    if(op==="set"){ switched = true; return; }
    if(op==="get"&&switched){ armed = false;                         // the rogue lands just before the re-read
      const txt = JSON.stringify(rogueL); db.docs.set("ledger_chunks/9_0_rogue", {i:0,n:1,rev:9,writer:"rogue",data:txt});
      db.docs.set("cockpit/ledger", {rev:9, writer:"rogue", chunks:1, length:txt.length, saved_at:"2026-11-09T12:00:30.000Z"}); } }));
  await settle();
  T.edit(L=>{ L.calls.push(call("a1")); }); armed = true;
  await T.fireTimers();
  const st1 = await readStore(db);
  const r1 = {note:T.note(), pending:T.ev("ledgerStorePending"), timers:T.timers.size, stored:{rev:st1.head.rev, writer:st1.head.writer, ids:ids(st1.L)},
    local:ids(T.local())};
  T.edit(L=>{ L.calls.push(call("a2")); }); await T.drain();
  const st2 = await readStore(db);
  return {r1, after:{rev:st2.head.rev, ids:ids(st2.L), ok:st2.ok}, note:T.note(), pending:T.ev("ledgerStorePending")};
};
// 1: a write longer than half the lease renews it (acquire again, this tab's holder) before its next chunk; a renewal
// refused (the lease lapsed and another tab took it) switches nothing
S.renew = async()=>{
  const db = makeDb(), clock = db.clock;
  seedStore(db, {meta:{}, calls:[call("s1")], rev:3}, 3);
  let slow = 0, steal = false;
  const T = makeTab(view(db, async(op,path)=>{
    if(op==="set"&&path.startsWith("ledger_chunks/")){ clock.now += slow;
      if(steal){ db.leases.set("cockpit/ledger", {holder:"another-tab", exp:clock.now+600000}); } } }));
  await settle();
  const tab = T.ev("LEDGER_TAB");
  T.edit(L=>{ L.calls.push(call("big",{memo:"x".repeat(300000)})); });   // three chunks
  slow = 4000; let mark = db.log.length; await T.fireTimers();
  const st1 = await readStore(db);
  const r1 = {acq:db.log.slice(mark).filter(x=>x[0]==="acquire"&&x[2]===tab).length, stored:{rev:st1.head.rev, chunks:st1.head.chunks, ok:st1.ok}, note:T.note()};
  // the next long write: after its first chunk the lease lapses and another tab takes it
  slow = 11000; steal = true; T.edit(L=>{ L.calls.push(call("r2")); }); mark = db.log.length;
  db.leases.delete("cockpit/ledger");
  await T.fireTimers();
  const st2 = await readStore(db);
  return {r1, r2:{note:T.note(), pending:T.ev("ledgerStorePending"), stored:{rev:st2.head.rev, ids:ids(st2.L), ok:st2.ok},
    headerSets:sets(db, mark).filter(x=>x[0]==="H").length, keys:chunkKeys(db).filter(k=>!k.startsWith(`ledger_chunks/${st2.head.rev}_`))}};
};
// 2: a set-aside write that throws (browser storage full): nothing is claimed as set aside, the records stay in the
// ledger, and the note says SET-ASIDE FAILED — on the boot path (store wins), the merge's collapse on the write path,
// and the merge's collapse on the boot path
S.asidefail = async()=>{
  const full = k => k==="bd_ledger_v1_set_aside";
  // (i) boot, the store wins over an older copy holding a record it lacks
  const db1 = makeDb(); seedStore(db1, {meta:{}, calls:[call("s1"), call("s2")], rev:3}, 3);
  const O = makeTab(db1,{local:{bd_ledger_v1:JSON.stringify({meta:{}, calls:[call("s1"), call("l9")], rev:2})}, lsFail:full}); await settle();
  const st1 = await readStore(db1);
  const boot = {note:O.note(), local:ids(O.local()), stored:{rev:st1.head.rev, ids:ids(st1.L)}, aside:O.store.has("bd_ledger_v1_set_aside"),
    seen:O.ev("ledgerStoreSeen"), timers:O.timers.size, pending:O.ev("ledgerStorePending")};
  O.edit(L=>{ L.calls.push(call("o1")); }); await O.drain();              // the next save reads the store and merges by id
  const st1b = await readStore(db1);
  boot.next = {stored:{rev:st1b.head.rev, ids:ids(st1b.L)}, local:ids(O.local()), note:O.note()};
  // (ii) the write path: the id-merge's collapse cannot be set aside
  const pos = {sport:"NFL", game:"A @ B", home:"B", away:"A", engine:"elo", call_type:"straight", pick:"HOME", kickoff:"2026-11-15T18:00:00Z", status:"open"};
  const s = Object.assign({}, pos, {id:"NFL|A @ B|2026-11-08|elo|straight|", log_date:"2026-11-08", exec_market_p:0.55, updated_at:"2026-11-08T12:00:00Z"});
  const l = Object.assign({}, pos, {id:"NFL|A @ B|2026-11-09|elo|straight|", log_date:"2026-11-09", exec_market_p:0.60, updated_at:"2026-11-09T12:00:00Z"});
  const db2 = makeDb(); seedStore(db2, {meta:{}, calls:[call("c1")], rev:2}, 2);
  const U = makeTab(db2,{lsFail:full}), V = makeTab(db2); await settle();
  V.edit(L=>{ L.calls.push(Object.assign({}, s)); }); await V.fireTimers();
  const before2 = await readStore(db2);
  U.edit(L=>{ L.calls.push(Object.assign({}, l)); }); await U.drain();
  const st2 = await readStore(db2);
  const write = {note:U.note(), pending:U.ev("ledgerStorePending"), timers:U.timers.size, aside:U.store.has("bd_ledger_v1_set_aside"),
    storeSame:st2.head.writer===before2.head.writer, local:U.local().calls.filter(c=>c.game==="A @ B").map(c=>c.log_date)};
  U.ls.fail = null; U.edit(L=>{ L.calls.push(call("u3")); }); await U.drain();
  const st2b = await readStore(db2), aside2 = JSON.parse(U.store.get("bd_ledger_v1_set_aside")||"null");
  write.retry = {note:U.note(), stored:st2b.L.calls.filter(c=>c.game==="A @ B").map(c=>c.log_date), has:ids(st2b.L), aside:aside2&&aside2.calls.map(c=>c.log_date)};
  // (iii) boot, a newer local copy whose merge collapses
  const db3 = makeDb(); seedStore(db3, {meta:{}, calls:[s], rev:4}, 4);
  const mark3 = db3.log.length;
  const T = makeTab(db3,{local:{bd_ledger_v1:JSON.stringify({meta:{}, calls:[l], rev:5})}, lsFail:full}); await settle();
  const st3 = await readStore(db3);
  const boot2 = {note:T.note(), sets:sets(db3, mark3).length, local:T.local().calls.map(c=>c.log_date), stored:st3.L.calls.map(c=>c.log_date),
    seen:T.ev("ledgerStoreSeen"), state:T.ev("ledgerStoreState"), aside:T.store.has("bd_ledger_v1_set_aside")};
  T.ls.fail = null; T.edit(L=>{ L.calls.push(call("t3")); }); await T.drain();
  const st3b = await readStore(db3), aside3 = JSON.parse(T.store.get("bd_ledger_v1_set_aside")||"null");
  boot2.retry = {note:T.note(), stored:st3b.L.calls.filter(c=>c.game==="A @ B").map(c=>c.log_date), has:ids(st3b.L), aside:aside3&&aside3.calls.map(c=>c.log_date)};
  return {boot, write, boot2};
};
// review of the 316 push: browser storage FULL (every setItem throws, reads still answer). (i) the boot's store-wins
// path whose set-aside fails writes nothing: the store keeps every record; the next edit's save merges by id and
// writes the merge (the page's own last save, not the older copy getItem still returns). (ii) a newer local copy
// written up with every local write refused: the write sends the merge, so the store's own records survive.
S.full = async()=>{
  const all = k=>true;
  const db1 = makeDb(); seedStore(db1, {meta:{}, calls:[call("s1"), call("s2"), call("s3")], rev:3}, 3);
  const O = makeTab(db1,{local:{bd_ledger_v1:JSON.stringify({meta:{}, calls:[call("s1"), call("l9")], rev:2})}, lsFail:all});
  await settle(); await O.drain();
  const st1 = await readStore(db1);
  const boot = {note:O.note(), stored:{rev:st1.head.rev, ids:ids(st1.L)}, oldChunk:db1.docs.has("ledger_chunks/3_0"),
    mem:O.ev("window.__ledgerMem")?ids(O.ev("window.__ledgerMem")):null, local:ids(O.local())};
  O.edit(L=>{ L.calls.push(call("f1")); }); await O.drain();
  const st1b = await readStore(db1);
  boot.next = {stored:{rev:st1b.head.rev, ids:ids(st1b.L)}, note:O.note(), mem:ids(O.ev("window.__ledgerMem"))};
  const db2 = makeDb(); seedStore(db2, {meta:{}, calls:[call("s1"), call("s2")], rev:3}, 3);
  const N = makeTab(db2,{local:{bd_ledger_v1:JSON.stringify({meta:{}, calls:[call("s1"), call("n9")], rev:5})}, lsFail:all});
  await settle(); await N.drain();
  const st2 = await readStore(db2);
  const newer = {stored:{rev:st2.head.rev, ids:ids(st2.L)}, note:N.note()};
  return {boot, newer};
};
// review of the 316 push: an unload flush under a busy lease. A saves (its lease held 10 s: there is no release verb);
// device B edits and closes inside that window (its pagehide flush busy, its retry timer dies with the page); B reopens
// a minute later with its own localStorage, its local rev equal to the store's. The kept pending flag makes the
// reopened page merge B's edit and write it, not set it aside.
S.unload = async()=>{
  const clock = {now: Date.parse("2026-11-09T12:00:00Z")}, db = makeDb({clock});
  seedStore(db, {meta:{}, calls:[call("c1")], rev:3}, 3);
  const A = makeTab(db,{clock}), B = makeTab(db,{clock}); await settle();
  A.edit(L=>{ L.calls.push(call("a2")); }); await A.fireTimers();
  const aMark = A.store.has("bd_ledger_v1_store_pending");
  clock.now += 500;
  B.edit(L=>{ L.calls.push(call("b2")); });
  for (const f of B.winL.pagehide) f(); await settle();
  const bTab = B.ev("LEDGER_TAB"), bMark = JSON.parse(B.store.get("bd_ledger_v1_store_pending")||"null");
  const mid = {bNote:B.note(), bTimers:B.timers.size, bLocal:ids(B.local()), bLocalRev:B.local().rev, stored:ids((await readStore(db)).L),
    aMark, bMarked:!!(bMark&&bMark[bTab])};
  clock.now += 60000;
  const B2 = makeTab(db,{clock, local:Object.fromEntries(B.store)}); await settle();
  const st = await readStore(db);
  return {mid, stored:ids(st.L), rev:st.head.rev, ok:st.ok, B2note:B2.note(), B2local:ids(B2.local()),
    aside:B2.store.has("bd_ledger_v1_set_aside"), markLeft:B2.store.has("bd_ledger_v1_store_pending")};
};
// 3: two overlapping mirror loads finishing out of order: the older one prints nothing, claims nothing, holds no
// subset; the newer's note, slate and button stand; the button loads only the latest load's subset
S.overlap = async()=>{
  const listing = (folder, names)=>JSON.stringify(names.map(n=>({name:n, path:`${folder}/${n}`, type:"file"})));
  const NAMES = ["desk_a.json", "desk_b.json", "window_24h.json", "nfl_results.json"];
  let gate = null, fail = {};
  const mcp = { listTools: async()=>({servers:[{server:"GitHub", tools:[{name:"get_file_contents"}]}]}),
    callTool: async(server, tool, a)=>{
      if (gate && a.path===gate.path) await gate.p;
      const parts = a.path.split("/");
      if (parts.length===2) return listing(a.path, NAMES);
      if (fail[a.path]){ const e=new Error("GitHub did not answer"); e.code="upstream_error"; throw e; }
      return JSON.stringify({file:a.path}); } };
  const hold = path=>{ let open; const p = new Promise(r=>open=r); gate = {path, p}; return open; };
  const T = makeTab(makeDb(),{mcp}); await settle();
  const snap = ()=>({note:T.gh(), btnHidden:T.el("ghPartialBtn").hidden, btnText:T.el("ghPartialBtn").textContent,
    partial:T.ev("ghPartial&&{seq:ghPartial.seq,folder:ghPartial.folder,n:ghPartial.got.length}"), seq:T.ev("ghLoadSeq"),
    loadDocs:clone(T.calls.loadDocs), results:clone(T.calls.ingestResultsDocs), window:T.calls.ingestWindowText.length});
  // (i) the older (a dated folder, one read failing) finishes after the newer (latest, clean)
  fail = {"host/2026-11-08/desk_b.json":true};
  let open = hold("host/2026-11-08/nfl_results.json");
  const p1 = T.ev('ghLoadFolder("host/2026-11-08")'); await settle();
  const oldMid = T.gh();
  await T.ev('ghLoadFolder("host/latest")'); await settle();
  const newer1 = snap();
  open(); await p1; await settle();
  const one = {oldMid, newer:newer1, after:snap()};
  // (ii) the older (latest, clean) finishes after the newer (a dated folder, one read failing: the button)
  fail = {"host/2026-11-09/desk_b.json":true};
  open = hold("host/latest/nfl_results.json");
  const p2 = T.ev('ghLoadFolder("host/latest")'); await settle();
  await T.ev('ghLoadFolder("host/2026-11-09")'); await settle();
  const newer2 = snap();
  open(); await p2; await settle();
  const two = {newer:newer2, after:snap()};
  for (const f of T.el("ghPartialBtn").listeners.click) await f(); await settle();
  two.pressed = snap();
  // (iii) a held subset whose load is no longer the latest is never loaded by the button
  fail = {"host/2026-11-10/desk_b.json":true}; gate = null;
  await T.ev('ghLoadFolder("host/2026-11-10")'); await settle();
  const held = snap();
  T.ev("ghLoadSeq++");                                   // a newer press began (its listing still in flight)
  for (const f of T.el("ghPartialBtn").listeners.click) await f(); await settle();
  const three = {held, after:snap()};
  return {one, two, three};
};
(async()=>{ const out = await S[SCEN](); process.stdout.write(JSON.stringify(out)); })()
  .catch(e=>{ console.error(e&&e.stack||e); process.exit(1); });
"""


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    d = tmp_path_factory.mktemp("cockpit315")
    page, harness = d / "page.js", d / "harness.js"
    page.write_text(_page_code(), encoding="utf-8")
    harness.write_text(HARNESS, encoding="utf-8")

    def _run(scen):
        r = subprocess.run([node, str(harness), str(page), scen], capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout)
    return _run


def test_a_two_tabs_racing_both_edits_survive_and_the_rev_rises(run):
    o = run("race")
    assert o["boot"] == {"A": 3, "B": 3, "Anote": o["boot"]["Anote"]} and "rev 3" in o["boot"]["Anote"]
    assert o["afterA"]["ids"] == ["a2", "c1"] and o["afterA"]["rev"] > 3
    # B's header check sees A's rev, reloads, merges by id and writes rev+1 over it: A's a2 survives B's write
    assert o["afterB"]["ids"] == ["a2", "b2", "c1"] and o["afterB"]["fills"] == ["f1", "f2"] and o["afterB"]["ok"]
    assert o["afterB"]["rev"] > o["afterA"]["rev"]
    assert "merged with the store's rev" in o["Bnote"]
    # the later conflicting edit (A grades c1 after B repriced it): the newer updated_at wins, and B's call stays
    assert o["afterA2"]["ids"] == ["a2", "b2", "c1"] and o["afterA2"]["rev"] > o["afterB"]["rev"]
    assert o["afterA2"]["c1"]["status"] == "graded" and o["afterA2"]["c1"]["result"] == "W"
    assert "updated_at" in o["afterA2"]["c1"]
    assert o["Alocal"] == ["a2", "b2", "c1"] and o["Blocal"] == ["a2", "b2", "c1"]
    assert o["renders"]["B"] >= 2 and o["renders"]["A"] >= 2           # boot render + the merge's re-render
    # 2(e): one rev's chunks only, the header's
    rev = o["afterA2"]["rev"]
    assert o["keys"] == ["cockpit/ledger", f"ledger_chunks/{rev}_0_{o['afterA2']['writer']}"]


def test_b_an_edit_during_the_load_is_queued_then_merged_and_written(run):
    o = run("queued")
    assert o["state0"] == "loading"
    assert o["note1"] == "store: loading… (1 edits queued)" and o["note2"] == "store: loading… (2 edits queued)"
    assert o["localDuring"] == ["q1", "q2"]                       # the local copy still saves
    assert o["timersDuring"] == 0 and o["writesDuring"] == 0     # nothing reaches the store while it loads
    assert o["stored"]["ids"] == ["q1", "q2", "s1"] and o["stored"]["rev"] == 4
    assert o["local"] == ["q1", "q2", "s1"] and o["queued"] == 0 and o["state"] == "ready"
    assert "merged 2 queued edit(s)" in o["note"]


def test_c_a_hidden_page_flushes_at_once_with_no_timer(run):
    o = run("hidden")
    assert o["armed"] == 1 and o["timersAfter1"] == 0
    assert o["st1"]["ids"] == ["h1", "s1"] and o["st1"]["rev"] == 2
    assert o["armed2"] == 1 and o["timersAfter2"] == 0
    assert o["st2"]["ids"] == ["h1", "h2", "s1"] and o["st2"]["rev"] == 3
    assert o["st3"] == o["st2"]                                   # visible: the debounce stands


def test_c_the_load_is_rev_ordered(run):
    o = run("revorder")
    n = o["newer"]
    assert n["ids"] == ["l1", "s1"] and n["rev"] == 6 and n["local"] == ["l1", "s1"]
    assert "newer copy (rev 5 > the store's 3)" in n["note"] or "wrote this browser's newer copy up" in n["note"]
    old = o["older"]
    assert old["ids"] == ["s1", "s2"] and old["rev"] == 3 and old["writes"] == 0 and old["local"] == ["s1", "s2"]
    # the store wins, and the older copy's record the store does not hold is set aside and named, never dropped silently
    assert [c["id"] for c in old["aside"]["calls"]] == ["l9"] and old["aside"]["store_rev"] == 3
    assert "1 record(s) of this browser's older copy" in old["note"] and "bd_ledger_v1_set_aside" in old["note"]


def test_e_a_chunk_write_failing_at_chunk_2_leaves_the_old_rev_whole(run):
    o = run("chunks")
    assert o["boot"]["rev"] == 3
    r = o["localRev"]
    assert r == 4
    assert o["failed"] == {"rev": 3, "chunks": 3, "ok": True, "ids": ["s1"]}
    assert "SAVE FAILED" in o["failNote"]
    assert "ledger_chunks/3_0" in o["keysAfterFail"] and "ledger_chunks/3_2" in o["keysAfterFail"]
    assert not [k for k in o["keysAfterFail"] if k.startswith("ledger_chunks/4_2")]
    # the failed write's chunks 0 and 1 carry its own token: no chunk the header names was touched
    assert len([k for k in o["keysAfterFail"] if k.startswith("ledger_chunks/4_")]) == 2
    assert o["readerIds"] == ["s1"] and "rev 3" in o["readerNote"]
    # the later success switches the header, then deletes the old rev's chunks and the failed rev's partial ones
    assert o["ok"]["rev"] == 5 and o["ok"]["ok"] and o["ok"]["ids"] == ["e1", "e2", "s1"] and o["ok"]["chunks"] == 3
    w = o["ok"]["writer"]
    assert o["keys"] == ["cockpit/ledger", f"ledger_chunks/5_0_{w}", f"ledger_chunks/5_1_{w}", f"ledger_chunks/5_2_{w}"]


def test_e_a_v2_header_reads_and_the_next_save_upgrades_it(run):
    o = run("legacy")
    assert o["boot"]["rev"] == 0 and o["boot"]["local"] == ["v1", "v2"] and o["boot"]["localRev"] == 0
    assert "v2 header" in o["boot"]["note"]
    assert o["st"] == {"rev": 1, "ids": ["v1", "v2", "v3"], "ok": True}
    assert o["keys"] == ["cockpit/ledger", f"ledger_chunks/1_0_{o['writer']}"]   # the legacy ledger_chunks/0 is deleted after the switch


def test_d_a_13_file_listing_with_one_failing_read(run):
    o = run("partial")
    b = o["before"]
    assert b["loadDocs"] == 0 and b["results"] == 0 and b["window"] == 0      # nothing acted on, nothing claimed
    assert b["ledgerSame"] and b["dbWrites"] == 0
    assert "NOTHING LOADED" in b["note"] and "the current slate stands" in b["note"]
    assert "desk_07.json (upstream_error)" in b["note"] and "1 of 13" in b["note"]
    assert b["btnHidden"] is False and b["btnText"] == "Load the 12 that read"
    a = o["after"]
    assert a["note"].startswith("PARTIAL") and "Loaded 12 of 13 file(s)" in a["note"] and "desk_07.json" in a["note"]
    assert a["btnHidden"] is True
    assert len(a["loadDocs"]) == 1 and len(a["loadDocs"][0]) == 10 and "host/latest/desk_07.json" not in a["loadDocs"][0]
    assert a["results"] == [["host/latest/nfl_results.json"]] and a["window"] == 1
    assert o["loadsAfterSecondPress"] == 1
    c = o["clean"]
    assert c["loadDocs"] == [11] and "PARTIAL" not in c["note"] and "Loaded 13 of 13" in c["note"] and c["btnHidden"] is True


def test_the_ruling_is_quoted_where_each_letter_is_built():
    html = _html()
    for q in ('"the connector loader acts\n// only when EVERY listed file read and parsed',
              '2(a) STALE SESSIONS (verbatim): "a store write first reads the header',
              '2(b) EDITS BEFORE LOAD (verbatim): "while the store is loading, saveLedger queues',
              '2(c) UNLOAD (verbatim): "`pagehide` and `visibilitychange: hidden` flush the pending write at once',
              '2(c) (verbatim): "on load the store never overwrites a NEWER local copy',
              '2(e) CHUNK WRITES (verbatim): "chunks are written under the new rev\'s ids'):
        assert q in html, q
    assert '<button id="ghPartialBtn" class="ghost" hidden></button>' in html


# ---- the review of this PR (round 1): one test per defect it confirmed ----

def test_review_a_merge_collapse_is_named_and_the_dropped_copy_kept_aside(run):
    """2(a) "never a silent drop": the id-merge keeps both calls of one position (one log date per device); the save's
    enforceLedger then collapses them by the page's own rule (better: the earliest capture). The note names it with
    the page's dedupeNote, and the copy it removed is kept aside in this browser. The collapse rule is unchanged."""
    o = run("collapse")
    for path in ("boot", "write"):
        assert "1 duplicate(s) collapsed (same key 0 · re-logged on a later day 1 · fills 0)" in o[path]["note"], path
        assert "set aside in this browser (bd_ledger_v1_set_aside)" in o[path]["note"], path
    assert o["boot"]["stored"] == [["2026-11-08", 0.55]] and o["boot"]["aside"] == [["2026-11-09", 0.6]]
    assert o["write"]["stored"] == ["2026-11-08"] and o["write"]["aside"] == ["2026-11-09"]


def test_review_chunks_of_a_flush_cut_off_by_the_browser_are_swept_later(run):
    """2(e): a pagehide flush ended between its chunk writes and its header switch leaves chunks no header names. This
    browser's journal names them; once they are older than another tab's write could be, the next confirmed switch
    deletes them, and the header's own chunks are the only ones left."""
    o = run("orphans")
    assert o["killed"] == {"head": 3, "partial": 2, "journal": [[4, 3]]}
    r = o["reopened"]
    assert r["rev"] == 5 and r["ids"] == 301 and r["hasA1"] and r["stale"] == 2   # fresh: another tab may be writing them
    a = o["after"]
    w = a["writer"]
    assert a["rev"] == 6 and a["keys"] == [f"ledger_chunks/6_{i}_{w}" for i in range(a["chunks"])]
    assert a["journal"] == 0 and "1 chunk set(s) of an earlier unfinished write deleted" in a["note"]


def test_review_two_writers_of_one_rev_never_mix_chunks(run):
    """2(e) "a failed write leaves the old rev intact and readable", under the race: tab B starts from rev 3 like tab
    A, A switches the header to rev 4, then B writes its first chunk and fails at its second. Every write's chunks
    carry its own token, so A's header still names A's chunks, untouched; a fresh tab reads A's rev 4 whole (only B's
    unsaved b2 is not there); B's next save merges A's rev 4 and holds both tabs' edits."""
    o = run("samerev")
    assert o["headerKept"] and o["rev"] == 4 and "SAVE FAILED" in o["Bnote"]
    assert o["missing"] == ["b2"] and o["c0"] == "xxx" and "301 calls" in o["Cnote"]
    a = o["after"]
    assert a["ok"] and a["rev"] == 6 and a["n"] == 303 and a["has"] == ["a2", "b2", "b3"] and a["c0"] == "yyy"
    assert "merged with the store's rev 4 by id" in a["note"]


def test_review_a_chunk_of_another_write_is_refused(run):
    """The reader takes a chunk only when its writer token, rev and index are the header's: a mix is refused at boot,
    never loaded as the ledger and never written over there."""
    o = run("mixed")
    assert "chunk 0 of 1 is not the header's write" in o["note"] and o["state"] == "error"
    assert o["sets"] == 0 and o["local"] is None


def test_review_two_flushes_from_one_header_both_survive(run):
    """2(a) under the race: tabs A and B both read rev 3 and both write rev 4. The header is compared by identity (rev
    plus writer token), so the tab whose header was written over sees a header it did not write, reads it, merges by
    id and writes again: the store holds both edits with no further edit, and later edits on both tabs merge too."""
    o = run("collide")
    assert o["afterBoth"] == {"rev": 5, "ids": ["a2", "b2", "c1"], "ok": True}
    assert "read and merged again" in o["Anote"] + o["Bnote"]
    assert o["chunks"] == o["chunksOfHead"]          # the losing write's chunks are deleted
    assert o["after"]["ids"] == ["a2", "a3", "b2", "b3", "c1"] and o["C"] == ["a2", "a3", "b2", "b3", "c1"]


def test_review_a_torn_v2_store_is_written_over_and_its_chunks_kept(run):
    """A v2 store an interrupted v2 write left torn (its header's length no longer matches) has no whole rev to merge.
    The boot writes nothing; the next save writes this browser's copy up as a new rev, leaves the unreadable legacy
    chunks in place, and says so; sync resumes (a later save and a fresh tab both read the new rev)."""
    o = run("torn")
    assert "stored length 240 ≠ header 245" in o["boot"] and o["setsBoot"] == 0
    assert o["first"] == {"rev": 1, "ids": ["c1", "c2", "c3"], "ok": True} and o["legacyKept"]
    assert "did not read whole (stored length 240 ≠ header 245)" in o["note"] and "left in place, unread" in o["note"]
    assert o["second"] == {"rev": 2, "ids": ["c1", "c2", "c3", "c4"]} and "SAVE FAILED" not in o["note2"]
    assert o["fresh"] == ["c1", "c2", "c3", "c4"]


# ---- the review of this PR (Codex, round 1): one test per finding ----

def test_codex_a_reverted_edit_keeps_its_newer_stamp_through_the_merge(run):
    """Equal bodies are no conflict, but the newer valid stamp is kept: tab B's edit-then-revert (the stored body, at
    t3) merges over the store's t1 copy as t3, so tab C's differing copy stamped t2 loses the later merge."""
    o = run("revert")
    assert o["t1"] < o["t2"] < o["t3"]
    assert o["bLocal"] == {"p": 0.5, "at": o["t3"]}
    assert o["afterB"] == {"p": 0.5, "at": o["t3"]}
    assert o["afterC"] == {"p": 0.5, "at": o["t3"]}           # B's reverted body, not C's 0.70 at t2
    assert o["ids"] == ["a2", "x1"] and "1 differing version(s)" in o["Cnote"]


def test_codex_a_listing_whose_every_read_fails_names_each_file(run):
    """The zero-success note keeps the first error's text and names every failed file with its code; nothing acts."""
    o = run("allfail")
    assert o["note"].startswith(o["firstErr"])
    assert "Failed: desk_01.json (upstream_error), desk_02.json (not a JSON document)" in o["note"]
    assert o["loadDocs"] == 0 and o["results"] == 0 and o["window"] == 0
    assert o["ledgerSame"] and o["dbWrites"] == 0 and o["btnHidden"] is True and o["partial"] is None


def test_codex_a_torn_store_whose_replacement_write_fails_keeps_its_chunks(run):
    """A torn header is not marked seen before the replacement write: when that write fails at a chunk, the next save
    reads the torn header again and writes with keepOld, so the unreadable legacy chunks stay in place."""
    o = run("tornretry")
    assert "SAVE FAILED" in o["failNote"] and o["headAfterFail"] and o["keptAfterFail"]
    assert o["second"]["ok"] and o["second"]["ids"] == ["c1", "c2", "c3", "c4"]
    assert o["legacyKept"]
    assert "did not read whole" in o["note"] and "left in place, unread" in o["note"]


# ---- ARCHITECT 2026-11-09 19:00 ET, addendum 316: the ruled fix (items 1-3), one test per tested part ----

def test_316_two_tabs_contending_for_the_lease_one_busy_both_edits_survive(run):
    """Item 1: A and B flush at once from rev 3. A holds the lease on cockpit/ledger and writes rev 4; B's acquire is
    busy, so B writes nothing, says "store: busy (another tab is saving), retrying…", retries (expiresAt or 2 s, the
    sooner) and, once A's lease lapses, reads A's header, merges by id and writes rev 5 holding both edits. Every set is
    one writer's chunks then that writer's header switch: no switch of one interleaves the other's write."""
    o = run("contend")
    m = o["mid"]
    assert m["ids"] == ["a2", "c1"] and m["rev"] == 4 and "rev 4" in m["Anote"]
    assert m["Bnote"] == "store: busy (another tab is saving), retrying…"
    assert m["Bsaving"] is True and m["Bwaiting"] == [2000] and m["Bsets"] == 0
    assert o["acq"][0] == "A" and set(o["acq"][1:]) == {"B"} and len(o["acq"]) <= 7     # one try + at most five retries
    seq = o["seq"]
    heads = [i for i, x in enumerate(seq) if x[0] == "H"]
    assert len(heads) == 2 and heads[1] == len(seq) - 1
    wa, wb = seq[heads[0]][1], seq[heads[1]][1]
    assert wa != wb
    assert all(x == ["C", wa] for x in seq[:heads[0]]) and all(x == ["C", wb] for x in seq[heads[0] + 1:heads[1]])
    a = o["after"]
    assert a == {"ids": ["a2", "b2", "c1"], "rev": 5, "ok": True, "writer": wb, "chunks": 1}
    assert o["chunkKeys"] == [f"ledger_chunks/5_0_{wb}"]                 # nothing lost, nothing to delete but A's rev 4
    assert "merged with the store's rev 4 by id" in o["Bnote"] and "waited for another tab's store lease" in o["Bnote"]
    assert "changed under this write" not in o["Bnote"]
    assert o["Blocal"] == ["a2", "b2", "c1"] and o["pending"] is False


def test_316_the_busy_path_after_five_retries_keeps_the_local_copy_and_the_pending_flag(run):
    """Item 1 "after the fifth, keep the local copy, say "store: NOT saved — another tab holds the store; try again",
    and leave the pending flag set so the next edit retries": one try and five retries 2 s apart, nothing written, no
    immediate retry; the next edit saves both edits. "retry after `expiresAt` or 2 s, whichever is sooner", word for
    word: a lease ending in 500 ms is retried after 500 ms (review of the push: no margin added)."""
    o = run("exhaust")
    r = o["r1"]
    assert r["busyNote"] == "store: busy (another tab is saving), retrying…"
    assert r["note"].startswith("store: NOT saved — another tab holds the store; try again")
    assert r["tries"] == 6 and r["waited"] == 10000 and r["sets"] == 0
    assert r["stored"] == {"rev": 3, "ids": ["s1"]} and r["local"] == ["e1", "s1"]
    assert r["pending"] is True and r["saving"] is False and r["timers"] == 0
    assert o["waited2"] == 500                                            # expiresAt (500 ms) was sooner than 2 s
    assert o["after"] == {"rev": 5, "ids": ["e1", "e2", "s1"], "ok": True} and o["pending"] is False
    assert "waited for another tab's store lease (1 retry)" in o["note"]


def test_316_a_runtime_without_acquire_writes_as_before_and_says_so(run):
    o = run("nolease")
    assert o["stored"] == {"rev": 3, "ids": ["n1", "s1"], "ok": True} and o["timers"] == 0 and o["pending"] is False
    assert "this runtime offers no store lease (DocumentReference.acquire)" in o["note"] and "SAVE FAILED" not in o["note"]


def test_316_the_one_re_read_after_the_switch_keeps_pending_and_the_next_save_merges(run):
    """Item 1 "then ONE re-read of the header to confirm the switch landed (... if it moved anyway — a writer not using
    acquire — merge again on the next save, never drop)": the write is reported NOT SAVED, no immediate retry, the
    pending flag stays set, and the next save merges the other writer's record with both of this tab's edits."""
    o = run("rogue")
    r = o["r1"]
    assert "NOT SAVED — the store's header changed under this write 1 time(s)" in r["note"]
    assert r["pending"] is True and r["timers"] == 0
    assert r["stored"] == {"rev": 9, "writer": "rogue", "ids": ["c1", "r1"]} and r["local"] == ["a1", "c1"]
    assert o["after"] == {"rev": 10, "ids": ["a1", "a2", "c1", "r1"], "ok": True} and o["pending"] is False
    assert "merged with the store's rev 9 by id" in o["note"]


def test_316_a_long_write_renews_the_lease_and_a_lost_lease_switches_nothing(run):
    """The type: "Leases expire on their own (no release verb) ... renew while working"; "Renewal requires the same
    holder". A three-chunk write past half the lease acquires again with this tab's holder; a renewal refused (the lease
    lapsed and another tab took it) deletes this write's chunks, never switches the header, and keeps the pending flag."""
    o = run("renew")
    assert o["r1"]["acq"] == 2 and o["r1"]["stored"] == {"rev": 4, "chunks": 3, "ok": True}
    r = o["r2"]
    assert "NOT SAVED — the store lease lapsed during this write and another tab holds it" in r["note"]
    assert r["pending"] is True and r["headerSets"] == 0 and r["keys"] == []
    assert r["stored"] == {"rev": 4, "ids": ["big", "s1"], "ok": True}


def test_316_a_set_aside_write_that_throws_keeps_the_records_in_the_ledger(run):
    """Item 2: "records count as set aside only after the set-aside write returns; on failure they stay in the ledger
    and the note reads "SET-ASIDE FAILED (browser storage full) — N records kept in the ledger"; nothing is reported
    kept that was not written." The three callers: the boot (store wins), the merge's collapse on the write path, the
    merge's collapse on the boot path."""
    o = run("asidefail")
    fail = "SET-ASIDE FAILED (browser storage full) — 1 records kept in the ledger"
    b = o["boot"]
    assert b["note"].startswith("store: " + fail) and b["aside"] is False
    # l9 stays in this browser's ledger, and nothing is written: the store keeps its own rev whole (review of the push)
    assert b["local"] == ["l9", "s1"] and b["stored"] == {"rev": 3, "ids": ["s1", "s2"]}
    assert "nothing was written: the store's rev 3 stands as it is" in b["note"] and "set aside in this browser" not in b["note"]
    assert b["seen"] is None and b["timers"] == 0 and b["pending"] is False
    bn = b["next"]                                    # the next save reads the store, merges by id, writes: none dropped
    assert bn["stored"] == {"rev": 4, "ids": ["l9", "o1", "s1", "s2"]} and bn["local"] == ["l9", "o1", "s1", "s2"]
    assert "merged with the store's rev 3 by id" in bn["note"]
    w = o["write"]
    assert w["note"].startswith("store: " + fail) and w["aside"] is False and w["storeSame"]
    assert w["local"] == ["2026-11-09"] and w["pending"] is True and w["timers"] == 0
    assert "set aside in this browser" not in w["note"]
    wr = w["retry"]                                   # storage frees: the next save merges, collapses and sets aside
    assert wr["stored"] == ["2026-11-08"] and wr["aside"] == ["2026-11-09"] and "u3" in wr["has"]
    assert "set aside in this browser (bd_ledger_v1_set_aside)" in wr["note"]
    b2 = o["boot2"]
    assert b2["note"].startswith("store: " + fail) and b2["sets"] == 0 and b2["aside"] is False
    assert b2["local"] == ["2026-11-09"] and b2["stored"] == ["2026-11-08"] and b2["seen"] is None and b2["state"] == "ready"
    br = b2["retry"]
    assert br["stored"] == ["2026-11-08"] and br["aside"] == ["2026-11-09"] and "t3" in br["has"]


def test_316_review_storage_full_never_writes_an_older_copy_over_the_store(run):
    """Review of the 316 push (blocking): with every localStorage write refused, the store-wins boot whose set-aside
    fails wrote the older local copy over the store (s2 and s3 deleted). Now that path writes nothing; the next save
    merges by id and sends the page's own last save (not the older copy getItem still returns), and a note never says
    "cached in this browser" for a copy the browser refused. The newer-local boot path sends the merge too."""
    o = run("full")
    b = o["boot"]
    assert b["stored"] == {"rev": 3, "ids": ["s1", "s2", "s3"]} and b["oldChunk"] is True
    assert b["note"].startswith("store: SET-ASIDE FAILED (browser storage full) — 1 records kept in the ledger")
    assert "nothing was written" in b["note"] and b["local"] == ["l9", "s1"] and b["mem"] is None
    n = b["next"]
    assert n["stored"] == {"rev": 4, "ids": ["f1", "l9", "s1", "s2", "s3"]} and n["mem"] == ["f1", "l9", "s1", "s2", "s3"]
    assert "NOT cached in this browser" in n["note"] and "· cached in this browser" not in n["note"]
    w = o["newer"]
    assert w["stored"] == {"rev": 6, "ids": ["n9", "s1", "s2"]} and "wrote this browser's newer copy up" in w["note"]
    assert "NOT cached in this browser" in w["note"]


def test_316_review_an_unload_flush_under_a_busy_lease_is_merged_on_reopen(run):
    """Review of the 316 push (blocking): the lease has no release verb, so a page closed while another device's lease
    stands loses its retry with the page. 316 item 1's "leave the pending flag set" is kept in this browser too
    (bd_ledger_v1_store_pending): the reopened page, its local rev equal to the store's, merges the unsaved edit by id
    and writes it (2(b)'s queued rule) instead of setting it aside, and clears the flag once the write lands."""
    o = run("unload")
    m = o["mid"]
    assert m["bNote"] == "store: busy (another tab is saving), retrying…" and m["bTimers"] == 1 and m["bMarked"] is True
    assert m["aMark"] is False and m["stored"] == ["a2", "c1"] and m["bLocal"] == ["b2", "c1"] and m["bLocalRev"] == 4
    assert o["stored"] == ["a2", "b2", "c1"] and o["rev"] == 5 and o["ok"] is True
    assert "merged this browser's unsaved edit(s) and saved" in o["B2note"] and o["B2local"] == ["a2", "b2", "c1"]
    assert o["aside"] is False and o["markLeft"] is False


def test_316_two_overlapping_loads_finishing_out_of_order(run):
    """Item 3: "each mirror load takes a sequence number; only the latest load may set the note, the button or the
    slate; an older load that finishes later prints nothing and claims nothing.\""""
    o = run("overlap")
    one = o["one"]
    assert one["oldMid"].startswith("Reading host/2026-11-08/")
    assert one["newer"]["note"].startswith("Loaded 4 of 4 file(s)") and "host/latest" in one["newer"]["note"]
    assert one["after"] == one["newer"]                       # the older's partial note, subset and button never appear
    assert one["after"]["partial"] is None and one["after"]["btnHidden"] is True
    assert one["after"]["loadDocs"] == [["host/latest/desk_a.json", "host/latest/desk_b.json"]]
    two = o["two"]
    assert two["newer"]["btnText"] == "Load the 3 that read" and two["newer"]["partial"]["folder"] == "host/2026-11-09"
    assert two["after"] == two["newer"]                       # the older clean load claims nothing and prints nothing
    p = two["pressed"]
    assert p["note"].startswith("PARTIAL") and "host/2026-11-09" in p["note"]
    assert p["loadDocs"][-1] == ["host/2026-11-09/desk_a.json"] and p["results"][-1] == ["host/2026-11-09/nfl_results.json"]
    three = o["three"]
    assert three["held"]["partial"]["seq"] == three["held"]["seq"]
    assert three["after"]["seq"] == three["held"]["seq"] + 1
    assert three["after"]["loadDocs"] == three["held"]["loadDocs"] and three["after"]["window"] == three["held"]["window"]


def test_316_the_ruling_is_quoted_where_each_part_is_built():
    html = _html()
    for q in ('ADDENDUM 316 ITEM 1 (ARCHITECT 2026-11-09 19:00 ET), THE STORE LEASE, verbatim: "`DocumentReference.acquire',
              'retry after\n// `expiresAt` or 2 s, whichever is sooner, up to 5 times',
              '316 item 1 "then ONE re-read of the header to confirm the switch landed',
              'ADDENDUM 316 ITEM 2 (ARCHITECT 2026-11-09 19:00 ET, verbatim): "records count as set aside only after',
              'ADDENDUM 316 ITEM 3 (ARCHITECT 2026-11-09 19:00 ET, verbatim): "each mirror load takes a sequence number'):
        assert q in html, q
    assert 'acquire({holder:LEDGER_TAB,ttlMs:LEDGER_LEASE_TTL})' in html
    assert "const LEDGER_LEASE_TTL=10000, LEDGER_LEASE_RETRIES=5, LEDGER_LEASE_WAIT=2000;" in html
    assert "LEDGER_LEASE_MARGIN" not in html
