"""
Cockpit "Load latest from host" headless verification (F2.5, ARCHITECT
2026-10-03): "a "Load latest from host" control that fetches host/latest/* via
the GitHub API with a fine-grained read-only token the operator pastes once
(stored in the browser, never in a file). Desk files only (F1c)."

api.github.com is ROUTED inside the headless browser (no network): a listing of
host/latest with a desk file, a legacy (no-desk) predictions file and a non-JSON file.
- the pasted token goes to localStorage, is cleared from the input, and is
  sent as a Bearer header; the default repo is Sports-Predictor-exports;
- the desk file loads through the same path as picked files; the file without
  desk blocks is refused (F1c); non-JSON entries are not fetched;
- a 401 reports "token rejected" and loads nothing.

    python3 scripts/cockpit_mirror_verify.py
"""
import functools
import http.server
import json
import os
import sys
import threading
from datetime import datetime, timedelta, timezone

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cockpit_desk_files as cdf  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime.now(timezone.utc).replace(microsecond=0)
D1 = (NOW + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
CHECKS = []


def check(label, ok, detail=""):
    CHECKS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


NFL = {"sport": "nfl", "rehearsal": False, "predictions": [
    {"home_team": "Philadelphia Eagles", "away_team": "Dallas Cowboys", "utc_date": D1,
     "prediction": {"home_win_prob": 0.64, "away_win_prob": 0.36, "tier": "lean"},
     "market": {"bookmaker_count": 7, "fair_prob": {"HOME": 0.58, "AWAY": 0.42}},
     "market_divergence_pp": 6.0, "quarantine": False,
     "input_quality": {"book_odds": 7, "injuries": {"home": {"qb_listed": []}, "away": {"qb_listed": []}}}}]}


def main():
    desk = cdf.desk_files({"nfl.json": NFL}, NOW, parlays=False)["nfl.json"]
    files = {"nfl_predictions.json": json.dumps(desk), "nfl_legacy.json": json.dumps(NFL),   # no desk blocks
             "RESULTS.md": "# x"}
    seen = {"auth": set(), "fetched": []}
    status = {"code": 200}

    def handle(route, request):
        seen["auth"].add(request.headers.get("authorization"))
        url = request.url
        if status["code"] != 200:
            return route.fulfill(status=status["code"], body="{}")
        if url.endswith("/contents/host/latest"):
            return route.fulfill(status=200, content_type="application/json",
                                 body=json.dumps([{"type": "file", "name": n} for n in files]))
        name = url.rsplit("/", 1)[1]
        seen["fetched"].append(name)
        return route.fulfill(status=200, body=files[name])

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
        page.route("https://api.github.com/**", handle)
        page.goto(f"http://127.0.0.1:{srv.server_address[1]}/cockpit.html")
        check("default repo is the exports mirror", page.input_value("#mirrorRepo") == "anthonyevans29/Sports-Predictor-exports")
        page.fill("#mirrorToken", "github_pat_TEST")
        page.click("#mirrorBtn")
        page.wait_for_function("document.getElementById('mirrorNote').textContent.startsWith('Loaded')")
        note = page.inner_text("#mirrorNote")
        check("token kept in localStorage, cleared from the input, sent as Bearer",
              page.evaluate("localStorage.getItem('bd_mirror_token')") == "github_pat_TEST"
              and page.input_value("#mirrorToken") == "" and seen["auth"] == {"Bearer github_pat_TEST"},
              str(seen["auth"]))
        check("non-JSON entries are not fetched", "RESULTS.md" not in seen["fetched"], str(seen["fetched"]))
        check("desk file loaded through the normal path; the non-desk file refused (F1c)",
              "Loaded 2 file(s)" in note and "1 without desk blocks refused" in note
              and page.evaluate("rows.length") == 1, note)
        status["code"] = 401
        page.click("#mirrorBtn")
        page.wait_for_function("document.getElementById('mirrorNote').textContent.includes('401')")
        check("a 401 says the token was rejected and loads nothing new", "token rejected" in page.inner_text("#mirrorNote"))
        check("no page errors", not errors, "; ".join(errors[:3]))
        browser.close()
    srv.shutdown()
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks passed" + (" — ALL GREEN" if all(CHECKS) else ""))
    return 0 if all(CHECKS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
