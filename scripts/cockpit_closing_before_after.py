r"""THE CLOSING MARKS ON THE OPERATOR'S LEDGER, BEFORE AND AFTER #431 (ARCHITECT 2026-10-20, addendum 145 item 3(b) R15),
READ-ONLY.

R15: "GATE-ADJACENT TO THE INCOME STATEMENT: the before/after over the operator's exported ledger with the laptop
closings loaded (pnlBlock, ledgerSummary, the settledBets counts) is pasted in the PR body before merge, and the repo
copy is republished only after my line-by-line read and the operator's word."

Two Cockpit pages in headless Chromium: BEFORE is tools/cockpit.html at --base (origin/main, by git show), AFTER the
page of the checkout this script sits in (the PR branch's worktree), or at --head when given. Each side runs in its own
fresh browser context (an empty profile: its own localStorage, nothing kept on disk) and does what the operator does,
through the page's own code:
  1. Import ledger: the exported bd_ledger_v1 file through importLedgerDoc, the function the Import ledger file input
     and Import pasted call (with the file's text, JSON.parse'd in the page as they do);
  2. with --slates, one load of those files through loadDocs (the path the file picker and the mirror controls take),
     the operator's order: the slates, then the closings;
  3. one load of the --closings files through loadDocs (the AFTER page marks what the pages did not repeat, R11; the
     BEFORE page has no closing logic and reads them as any --desk file).
Then each side prints the page's own words: the notes of the import and the loads, pnlBlock, ledgerSummary() (its
generated_at left out), the settledBets counts (with lastAudit), lastNotExec and the NOT EXECUTED line and list (the
AFTER page has them; the BEFORE page prints "n/a"); then a DIFF of the lines that moved from BEFORE to AFTER. "None
deleted" compares call ids: every id the ledger holds after the import is there after the loads.

THE OPERATOR'S FILL FIGURES STAY OUT OF THE REPO (ARCHITECT 2026-10-20, addendum 146 item 1: "the operator's Kalshi
fills (figures stay out of the repo)"), and R15 pastes this output in the PR body: pnlBlock's REALIZED block (the
page's realizedLines: real money, fees included, from the imported fills: staked, fees, pre-fee, net, the average fill,
the fee per dollar, the fills-based exposure in dollars) prints as ONE line naming its line count, on both sides and in
the DIFF. --with-realized prints it whole, for the operator's own console only. Every other line prints as the page
writes it: none of them carries a dollar figure from the fills (the EXECUTED-POSITION CLV lines are the close minus the
fill entry in pp, the timing lines prices, the ledger line a count of fills).

One clock: both pages read the same instant (the run's start, fixed with Playwright's clock), so pnlBlock's dates and
the week window are the same on both sides; the machine's timezone is the operator's browser's.

READ-ONLY: the ledger and the export files are opened for reading and never written; nothing is written beside them or
anywhere else (the pages are served from memory; every request but the page is aborted, so nothing leaves the browser
either: no GitHub, no fonts). The output names the export files by their base names and prints no path and no host. A
missing file, a file that is not JSON, a ledger that is not a bd_ledger_v1 export, a --closings file with no closing
block or a --slates file with one is refused (exit 2), as is a ref git cannot show; a page error exits 1, a step the
page could not run (Playwright's Error) too: its first line, no traceback, no path. git runs with --no-optional-locks
(its status takes no index lock and never refreshes the index).

Run it from the laptop checkout, from a worktree of the PR branch, so the checkout itself is never switched (the
ledger is the file the published page's Export ledger (JSON) button wrote; the closings are the laptop's exports):

    git fetch origin main claude/431-closing-not-executed
    git worktree add --detach /tmp/sp431 origin/claude/431-closing-not-executed
    python /tmp/sp431/scripts/cockpit_closing_before_after.py --ledger ~/Downloads/bd_ledger_v1_2026-10-20.json \
        --closings exports/closing_*.json --base origin/main
    git worktree remove /tmp/sp431

With a day's slates loaded first (that day's --desk exports and tickets file, as the operator loaded them):

    python /tmp/sp431/scripts/cockpit_closing_before_after.py --ledger ~/Downloads/bd_ledger_v1_2026-10-20.json \
        --slates exports/mlb_MLB_2026-10-19.json exports/nfl_predictions_2026-10-19.json \
        exports/desk_parlays_2026-10-19.json --closings exports/closing_*.json --base origin/main

Add --with-realized only for a run read on the operator's own console, never for the PR body's paste.

Needs Playwright + Chromium (as the cockpit_*_verify scripts) and git.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = "tools/cockpit.html"
URL = "http://cockpit.invalid/cockpit.html"           # served from memory: no file is written to serve it
SECTIONS = ("loads", "ledger", "pnlBlock", "ledgerSummary", "settledBets", "NOT EXECUTED")
REALIZED_HIDDEN = ("REALIZED: {n} line(s), not printed: fill figures stay out of the repo (addendum 146 item 1); "
                   "--with-realized prints them for the operator's own console")

# the page's state after the loads, in its own words
SNAP = r"""()=>{ renderLedger(); const L=loadLedger(), bets=settledBets(L), real=bets.filter(b=>!b.shadow);
  const by=(xs,f)=>{ const o={}; for(const x of xs){ const k=f(x); o[k]=(o[k]||0)+1; } return o; };
  const ne=typeof lastNotExec==="undefined"?null:{...lastNotExec};
  const neLine=typeof notExecutedLine==="function"?notExecutedLine(L):null;
  const el=document.getElementById("notExecuted");
  const list=el?el.innerHTML.split("<br>").map(h=>{ const d=document.createElement("div"); d.innerHTML=h;
    return d.textContent; }):null;
  const s=ledgerSummary(); delete s.generated_at;
  return {pnl:pnlBlock(L),realized:typeof realizedLines==="function"?realizedLines(L):null,summary:s,
    audit:{...lastAudit},ne,neLine,list,calls:L.calls.length,ids:L.calls.map(c=>c.id),
    marked:L.calls.filter(c=>c.not_executed).length,fills:(L.fills||[]).length,
    bets:{settled:bets.length,real:real.length,shadow:bets.length-real.length,byEngine:by(real,b=>b.engine),
      byType:by(bets,b=>b.call_type+(b.shadow?" (shadow)":""))}}; }"""
NOTE = "id=>document.getElementById(id).textContent"


def refuse(msg: str) -> int:
    print(f"REFUSED: {msg}")
    return 2


def read_json(path: Path, flag: str):
    """(text, doc) of an existing JSON file, or (None, why): read once, never written."""
    if not path.is_file():
        return None, f"no file at {flag} ({path.name}): a read-only receipt never creates one"
    try:
        text = path.read_text(encoding="utf-8")
        return text, json.loads(text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        return None, f"{flag} ({path.name}) is not a JSON file ({type(e).__name__})"


def git(*args: str) -> str | None:
    """git, read-only: --no-optional-locks, so status takes no .git/index.lock and never rewrites the index."""
    r = subprocess.run(["git", "--no-optional-locks", "-C", str(ROOT), *args], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def first_line(e) -> str:
    """An error's first line, any absolute path in it replaced: the output prints no traceback and no path."""
    line = (str(e).strip().splitlines() or [type(e).__name__])[0]
    return re.sub(r"(?<![\w:/.])/[^\s/'\"]+(?:/[^\s/'\"]*)*", "<path>", line)


def page_at(ref: str):
    """(html, label) of tools/cockpit.html at a ref, or (None, None)."""
    html, sha = git("show", f"{ref}:{PAGE}"), git("rev-parse", "--short", f"{ref}^{{commit}}")
    if not html or "<script>" not in html or not sha:
        return None, None
    return html, f"{PAGE} at {ref} ({sha.strip()})"


def working_page():
    html = (ROOT / PAGE).read_text(encoding="utf-8")
    sha = (git("rev-parse", "--short", "HEAD") or "?").strip()
    dirty = bool((git("status", "--porcelain", "--", PAGE) or "").strip())
    return html, f"the working tree's {PAGE} (HEAD {sha}{' + uncommitted changes' if dirty else ''})"


def run_side(browser, html: str, now: datetime, ledger_text: str, slates: list, closings: list) -> dict:
    """One page in a fresh context: import, load, read. Returns the page's words and its errors; a step the page could
    not run (Playwright's Error: a function the page lacks, a script that throws) returns {"fatal": its first line}."""
    from playwright.sync_api import Error as PlaywrightError
    ctx = browser.new_context()
    errors: list[str] = []
    try:
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(first_line(e)))
        page.route("**/*", lambda route, req: route.fulfill(status=200, content_type="text/html; charset=utf-8",
                                                            body=html) if req.url == URL else route.abort())
        page.clock.set_fixed_time(now)
        page.goto(URL)
        notes = []
        page.evaluate("t=>importLedgerDoc(JSON.parse(t))", ledger_text)
        notes.append(f"import: {page.evaluate(NOTE, 'ledgerNote')}")
        calls0, ids0 = page.evaluate("[loadLedger().calls.length,loadLedger().calls.map(c=>c.id)]")
        for name, docs in (("slates", slates), ("closings", closings)):
            if not docs:
                notes.append(f"{name}: (none loaded)")
                continue
            page.evaluate("document.getElementById('logNote').textContent=''")     # the note is this load's
            page.evaluate("async ds=>{ await loadDocs(ds); }", docs)
            notes.append(f"{name}, load note: {page.evaluate(NOTE, 'logNote') or '(none)'}")
            notes.append(f"{name}, Desk summary: {page.evaluate(NOTE, 'summary')}")
        out = page.evaluate(SNAP)
        out.update(notes=notes, calls0=calls0, ids0=ids0)
    except PlaywrightError as e:
        out = {"fatal": first_line(e)}
        errors.append(out["fatal"])
    finally:
        ctx.close()
    out["errors"] = errors
    return out


def pnl_lines(s: dict, with_realized: bool) -> list:
    """pnlBlock's lines, its REALIZED block (the page's realizedLines, found in place) as one line naming its line count
    unless --with-realized (addendum 146 item 1). A page whose block cannot be told apart prints no pnlBlock line."""
    lines, block = s["pnl"].split("\n"), s.get("realized")
    if with_realized:
        return lines
    if not block:
        return lines if not any(x.startswith("REALIZED") for x in lines) else [
            "pnlBlock not printed: its REALIZED lines could not be told apart (fill figures stay out of the repo)"]
    for i in range(len(lines) - len(block) + 1):
        if lines[i:i + len(block)] == block:
            return lines[:i] + [REALIZED_HIDDEN.format(n=sum(1 for x in block if x.strip()))] + lines[i + len(block):]
    return ["pnlBlock not printed: its REALIZED lines could not be told apart (fill figures stay out of the repo)"]


def sections(s: dict, with_realized: bool = False) -> dict:
    """{section: [lines]} as printed."""
    b, a, ne = s["bets"], s["audit"], s["ne"]
    gone = len(set(s["ids0"]) - set(s["ids"]))
    return {
        "loads": s["notes"],
        "ledger": [f"calls: {s['calls0']} after the import · {s['calls']} after the loads (none deleted, every call id "
                   f"of the import still there: {'yes' if not gone else f'NO, {gone} id(s) gone'}) · fills {s['fills']}"
                   f" · marked NOT EXECUTED {s['marked']}"],
        "pnlBlock": pnl_lines(s, with_realized),
        "ledgerSummary": json.dumps(s["summary"], indent=1, sort_keys=True, ensure_ascii=False).split("\n"),
        "settledBets": [
            f"settled {b['settled']} (real {b['real']} · shadow {b['shadow']})",
            "real by engine: " + (" · ".join(f"{k} {v}" for k, v in sorted(b["byEngine"].items())) or "none"),
            "by call type: " + (" · ".join(f"{k} {v}" for k, v in sorted(b["byType"].items())) or "none"),
            "lastAudit: " + " · ".join(f"{k} {v}" for k, v in a.items()),
            "lastNotExec: " + ("n/a" if ne is None else " · ".join(f"{k} {v}" for k, v in ne.items()))],
        "NOT EXECUTED": [f"line: {s['neLine'] if s['neLine'] is not None else 'n/a'}"]
                        + (["list: n/a"] if s["list"] is None else [f"list: {x}" for x in s["list"]]),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="#431 R15: the closing marks on the operator's ledger, BEFORE (main) and "
                                             "AFTER (the PR's page), read-only.")
    ap.add_argument("--ledger", required=True, help="the exported bd_ledger_v1 JSON (read, never written)")
    ap.add_argument("--closings", nargs="+", required=True, help="the laptop's closing_*.json files")
    ap.add_argument("--slates", nargs="+", default=[], help="slate --desk files loaded first (optional)")
    ap.add_argument("--base", default="origin/main", help="BEFORE: tools/cockpit.html at this ref (git show)")
    ap.add_argument("--head", default=None, help="AFTER: tools/cockpit.html at this ref (default: the working tree)")
    ap.add_argument("--with-realized", action="store_true",
                    help="print pnlBlock's REALIZED (real-money) lines whole: the operator's own console only, never "
                         "the PR body (addendum 146 item 1)")
    a = ap.parse_args(argv)
    ledger_text, L = read_json(Path(a.ledger).expanduser(), "--ledger")
    if ledger_text is None:
        return refuse(L)
    if not (isinstance(L, dict) and isinstance(L.get("calls"), list) and isinstance(L.get("meta"), dict)):
        return refuse(f"--ledger ({Path(a.ledger).name}) is not a bd_ledger_v1 export (an object with a calls list and "
                      "a meta object, as Export ledger (JSON) writes it)")
    files = {}
    for flag, paths in (("--slates", a.slates), ("--closings", a.closings)):
        files[flag] = []
        for p in paths:
            text, d = read_json(Path(p).expanduser(), flag)
            if text is None:
                return refuse(d)
            cl = d.get("closing") if isinstance(d, dict) else None
            is_closing = isinstance(cl, dict) and bool(cl.get("family")) and bool(cl.get("start"))
            if flag == "--closings" and not is_closing:
                return refuse(f"--closings ({Path(p).name}) carries no closing block (family, start): not a closing file")
            if flag == "--slates" and is_closing:
                return refuse(f"--slates ({Path(p).name}) carries a closing block: pass it with --closings")
            files[flag].append({"name": Path(p).name, "text": text})
    before, blabel = page_at(a.base)
    if before is None:
        return refuse(f"git show {a.base}:{PAGE} did not answer (is the ref fetched?)")
    if a.head:
        after, alabel = page_at(a.head)
        if after is None:
            return refuse(f"git show {a.head}:{PAGE} did not answer (is the ref fetched?)")
    else:
        after, alabel = working_page()
    now = datetime.now(timezone.utc).replace(microsecond=0)

    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as pw:
            exe = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**({"executable_path": exe} if os.path.isfile(exe) else {}))
            try:
                got = {side: run_side(browser, html, now, ledger_text, files["--slates"], files["--closings"])
                       for side, html in (("BEFORE", before), ("AFTER", after))}
            finally:
                browser.close()
    except PlaywrightError as e:
        print(f"page error: {first_line(e)}")
        return 1

    sha = {k: hashlib.sha256(v.encode("utf-8")).hexdigest()[:12] for k, v in (("BEFORE", before), ("AFTER", after))}
    print("COCKPIT CLOSING MARKS, BEFORE / AFTER (#431, ARCHITECT addendum 145 item 3(b) R15) · read-only")
    print(f"BEFORE = {blabel} · page sha256 {sha['BEFORE']}")
    print(f"AFTER  = {alabel} · page sha256 {sha['AFTER']}")
    print(f"ledger: {len(L['calls'])} call(s) · {len(L.get('fills') or [])} fill(s) · policy "
          f"{L['meta'].get('policy_version', '?')} · "
          f"slates: {', '.join(f['name'] for f in files['--slates']) or 'none'} · "
          f"closings ({len(files['--closings'])}): {', '.join(f['name'] for f in files['--closings'])}")
    print(f"one clock for both pages: {now.strftime('%Y-%m-%dT%H:%M:%SZ')}; each in a fresh browser context")
    print("REALIZED (real-money) lines: " + ("printed whole (--with-realized: the operator's own console only)"
                                            if a.with_realized else "one line each side, not printed (addendum 146 item 1)"))
    printed = {}
    # the withheld REALIZED blocks are still compared, so the DIFF sees a real-money line that moved without printing it
    both = all("fatal" not in got[side] for side in ("BEFORE", "AFTER"))
    same = both and got["BEFORE"].get("realized") == got["AFTER"].get("realized")
    for side in ("BEFORE", "AFTER"):
        print(f"\n=== {side} ===")
        if "fatal" in got[side]:
            print(f"  the page did not finish: {got[side]['fatal']}")
            continue
        printed[side] = sections(got[side], a.with_realized)
        for name in SECTIONS:
            print(f"-- {name}")
            for line in printed[side][name]:
                print(f"  {line}")
    print("\n=== DIFF (the lines that moved, BEFORE -> AFTER) ===")
    if len(printed) < 2:
        print("not computed: a side did not finish")
    else:
        for name in SECTIONS:
            moved = [x for x in difflib.unified_diff(printed["BEFORE"][name], printed["AFTER"][name], lineterm="", n=0)
                     if x[:1] in "-+" and not x.startswith(("---", "+++"))]
            print(f"[{name}]" + ("" if moved else " no line moved"))
            for x in moved:
                print(f"  {x[0]} {x[1:]}")
        if not a.with_realized:
            print("[REALIZED, not printed] " + ("no line moved" if same else "a line moved (read it with --with-realized"
                                                                              " on the operator's own console)"))
    errs = [f"{side}: {e}" for side in got for e in got[side]["errors"]]
    print("\npage errors: " + ("; ".join(errs) if errs else "none"))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
