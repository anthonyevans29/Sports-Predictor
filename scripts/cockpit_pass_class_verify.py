"""
Cockpit PASS-REASON CLASSES headless verification (architect 2026-09-30;
presentation only). Checks, over SYNTHETIC files:
- model table: a PASS with no reference (market not two-sided, or < 3 books)
  is greyed, tagged "no reference" and carries "re-run at T-60 (HH:MM
  local)" while the game is ahead; no hint once it has kicked off;
- a PASS whose edge was measured and declined is tagged "below floor" and
  not greyed;
- PLAY rows carry no tag, even on a thin reference (no policy change);
- quarantine / pre-gate PASSes keep their own reason, no class tag;
- the summary splits the passes;
- calls and units are identical to the pre-split policy;
- venue table: "single venue — no pair" and "books < 4" are "no reference"
  (greyed + hint), "max divergence < 5pp" is "below floor", UNL is neither.

    python3 scripts/cockpit_pass_class_verify.py

Writes nothing to the repo; no DB. Needs Playwright + Chromium.
"""
import functools
import http.server
import json
import os
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone

from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cockpit_desk_files as cdf  # noqa: E402  (F1c: the Cockpit renders desk files only)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KICK = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0)
PAST = KICK - timedelta(days=3)
K = KICK.strftime("%Y-%m-%dT%H:%M:%S")
P = PAST.strftime("%Y-%m-%dT%H:%M:%S")
CHECKS = []


def check(label, ok, detail=""):
    CHECKS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


def nfl(home, away, p_home, fair_h, books=7, when=K, quarantine=False):
    mk = {"bookmaker_count": books}
    if fair_h is not None:
        mk.update(fair_prob={"HOME": fair_h, "AWAY": round(1 - fair_h, 4)}, fair_source="1X2")
    return {"home_team": home, "away_team": away, "utc_date": when,
            "prediction": {"home_win_prob": p_home, "away_win_prob": round(1 - p_home, 4), "tier": "lean"},
            "market": mk, "quarantine": quarantine,
            "market_divergence_pp": round((p_home - fair_h) * 100, 1) if fair_h is not None else None,
            "input_quality": {"book_odds": books, "injuries": {"home": {"qb_listed": []}, "away": {"qb_listed": []}}}}


# #91: a fresh book capture (30 min before now) — the Desk excludes unknown / stale ages.
CAP = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=30)).replace(microsecond=0).isoformat()


def fixture(home, away, books, fair, kal):
    return {"home_team": home, "away_team": away, "utc_date": K, "status": "scheduled",
            "market": ({"bookmaker_count": books, "fair_prob": {"HOME": fair[0], "AWAY": fair[1]},
                        "fair_source": "1X2", "captured_at": CAP} if books else None),   # fresh capture (#91)
            "kalshi": ({"status": "two_sided", "prob": {"HOME": kal[0], "AWAY": kal[1]}} if kal else None),
            "input_quality": {"book_odds": books, "kalshi": "two_sided" if kal else "absent"}}


NFL = {"sport": "nfl", "rehearsal": False, "predictions": [
    nfl("Buffalo Bills", "Miami Dolphins", 0.62, None, books=0),                # no market -> no reference
    nfl("Denver Broncos", "Las Vegas Raiders", 0.58, 0.57, books=2),            # 1pp on 2 books -> thin: no reference
    nfl("Chicago Bears", "Minnesota Vikings", 0.58, 0.57, books=7),             # 1pp on 7 books -> below floor
    nfl("Seattle Seahawks", "Los Angeles Rams", 0.64, 0.58, books=7),           # 6pp -> PLAY
    nfl("Dallas Cowboys", "Philadelphia Eagles", 0.64, 0.58, books=2),          # 6pp on 2 books -> PLAY, untouched
    nfl("Detroit Lions", "Green Bay Packers", 0.60, None, books=0, when=P),     # kicked off, no reference -> no hint
    nfl("Atlanta Falcons", "Tampa Bay Buccaneers", 0.80, 0.60, quarantine=True),  # quarantine: own reason
]}
NCAA = {"competition_code": "NCAA", "fixtures": [
    fixture("Alabama", "Auburn", 0, None, None),                     # no book, no Kalshi -> no reference
    fixture("Georgia", "Florida", 3, (0.60, 0.40), (0.58, 0.42)),    # books 3 < 4 -> no reference
    fixture("Texas", "Oklahoma", 6, (0.60, 0.40), (0.58, 0.42)),     # 2pp < 5pp -> below floor
    fixture("Ohio State", "Michigan", 6, (0.60, 0.40), (0.52, 0.48)),  # 8pp -> VENUE
]}
UNL = {"competition_code": "UNL", "fixtures": [fixture("Spain", "Italy", 5, (0.5, 0.5), None)]}


def main():
    tmp = tempfile.mkdtemp(prefix="cockpit-pass-")
    for n, d in {"nfl.json": NFL, "fixtures_NCAA.json": NCAA, "fixtures_UNL.json": UNL}.items():
        with open(os.path.join(tmp, n), "w") as f:
            json.dump(d, f)

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=os.path.join(ROOT, "tools")))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        browser = pw.chromium.launch(**({"executable_path": exe} if os.path.isfile(exe) else {}))
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{srv.server_address[1]}/cockpit.html")

        def load(*names):
            page.evaluate("document.getElementById('summary').textContent=''")
            cdf.upload(page, [os.path.join(tmp, n) for n in names])
            page.wait_for_function("document.getElementById('summary').textContent.includes('rows')")
            page.click("#tabDesk")

        def rows(table):
            return page.evaluate(f"""Array.from(document.querySelectorAll('#{table} tbody tr'))
                .filter(tr=>!tr.classList.contains('vshadow'))
                .map(tr=>({{cells:Array.from(tr.children).map(td=>td.textContent),noref:tr.classList.contains('noref')}}))""")

        def row(rs, name):
            return next(r for r in rs if name in r["cells"][0])

        print("MODEL TABLE")
        load("nfl.json")
        rs = rows("slate")
        b = row(rs, "Buffalo")
        check("no market: PASS · 'no reference', greyed, re-run hint",
              b["noref"] and b["cells"][5] == "PASSno reference" and "re-run at T-60 (" in b["cells"][7], json.dumps(b))
        d = row(rs, "Denver")
        check("1pp on 2 books: 'no reference' (thin), greyed, hint, reason names the book count",
              d["noref"] and d["cells"][5] == "PASSno reference" and "books 2 < 3 → thin reference" in d["cells"][7]
              and "re-run at T-60" in d["cells"][7], json.dumps(d))
        c = row(rs, "Chicago")
        check("1pp on 7 books: 'below floor', not greyed, no hint",
              not c["noref"] and c["cells"][5] == "PASSbelow floor" and "re-run" not in c["cells"][7], json.dumps(c))
        s = row(rs, "Seattle")
        check("PLAY: no class tag", s["cells"][5] == "PLAY" and not s["noref"], json.dumps(s))
        dal = row(rs, "Dallas")
        check("PLAY on 2 books: unchanged (presentation only)", dal["cells"][5] == "PLAY" and not dal["noref"], json.dumps(dal))
        det = row(rs, "Detroit")
        check("kicked-off no-reference row: greyed + tagged, no re-run hint",
              det["noref"] and "no reference" in det["cells"][5] and "re-run" not in det["cells"][7], json.dumps(det))
        atl = row(rs, "Atlanta")
        check("quarantine PASS keeps its own reason, no class tag",
              atl["cells"][5] == "PASS" and "QUARANTINE" in atl["cells"][7] and not atl["noref"], json.dumps(atl))
        summ = page.inner_text("#summary")
        check("summary splits the passes", "5 pass (3 no reference · 1 below floor · 1 other)" in summ, summ)
        calls = page.evaluate("deskCalls.map(x=>[x.r.home,x.call,x.units,x.passKind])")
        want = {"Buffalo Bills": ("PASS", 0), "Denver Broncos": ("PASS", 0), "Chicago Bears": ("PASS", 0),
                "Seattle Seahawks": ("PLAY", 1), "Dallas Cowboys": ("PLAY", 1), "Detroit Lions": ("PASS", 0),
                "Atlanta Falcons": ("PASS", 0)}
        check("calls and units are the policy's (no change)",
              {h: (c_, u) for h, c_, u, _ in calls} == want, json.dumps(calls))
        hint = page.evaluate("rerunHint({utc:new Date(Date.now()+2*3600e3).toISOString()})")
        exp = page.evaluate("(()=>{const a=new Date(Date.now()+3600e3);return String(a.getHours()).padStart(2,'0')})()")
        check("the hint's clock is kickoff − 60 min, local", f"re-run at T-60 ({exp}:" in hint, hint)

        print("VENUE TABLE")
        load("fixtures_NCAA.json", "fixtures_UNL.json")
        vs = rows("venueTable")
        al = row(vs, "Alabama")
        check("no pair: 'no reference', greyed, hint", al["noref"] and al["cells"][5] == "PASSno reference"
              and "re-run at T-60" in al["cells"][6], json.dumps(al))
        ga = row(vs, "Georgia")
        check("books 3 < 4: 'no reference', greyed", ga["noref"] and ga["cells"][5] == "PASSno reference", json.dumps(ga))
        tx = row(vs, "Texas")
        check("2pp < 5pp: 'below floor', not greyed", not tx["noref"] and tx["cells"][5] == "PASSbelow floor", json.dumps(tx))
        oh = row(vs, "Ohio State")
        check("eligible: VENUE 0.25u, no tag", oh["cells"][5] == "VENUE 0.25u" and not oh["noref"], json.dumps(oh))
        sp = row(vs, "Spain")
        check("UNL: PASS with its own reason, no class tag, not greyed",
              sp["cells"][5] == "PASS" and not sp["noref"] and "UNL" in sp["cells"][6], json.dumps(sp))
        check("no page errors", not errors, "; ".join(errors))
        browser.close()
    srv.shutdown()
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed" + (" — ALL GREEN" if all(CHECKS) else ""))
    return 0 if all(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
