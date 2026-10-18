"""THE TODAY TAB (ARCHITECT 2026-10-18, addendum 125 item 2(b), #589): tools/cockpit.html gains a fifth tab, "Today",
fed by the coverage_v1 file through the existing intake; "a `coverage_v1` document takes its own path like
`desk_parlays_v1`, and it never resets the loaded slate — a coverage file alone must not blank `rows`". The rendering
is checked in a browser by scripts/cockpit_render_verify.py (Playwright, not in CI); here, in CI, the intake order in
loadDocs is pinned and the page's own Today functions run under node on synthetic documents. Item 2(c): the title
string "Betting Desk — B1 Shadow" becomes "Cockpit". Repo copy only: the live page is republished on the operator's
word."""
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


def test_the_title_is_cockpit_and_the_old_string_is_gone():
    html = _html()
    assert "<title>Cockpit</title>" in html
    assert "Betting Desk" not in html and "B1 Shadow" not in html


def test_five_tabs_today_fifth_with_its_view():
    html = _html()
    tabs = re.findall(r'<button id="tab(\w+)"', html)
    assert tabs == ["Card", "Desk", "Ledger", "Next", "Today"]
    assert '<div id="todayView" hidden>' in html
    st = _fn(html, "setTab")
    assert '$("todayView").hidden=mode!=="today"' in st and '$("tabToday").className' in st
    assert '$("tabToday").addEventListener("click",()=>setTab("today"))' in html


def test_loaddocs_lifts_coverage_out_before_the_slate_is_reset():
    """The coverage path runs first; a load of coverage files alone returns before `rows=[]`; the slate's reset never
    touches coverageDoc."""
    body = _fn(_html(), "loadDocs")
    take, ret, reset = body.index("takeCoverage(fs)"), body.index('if(!fs.length){ setTab("today"); return; }'), \
        body.index("rows=[]; shadowRows=[]; fileParlays=null; refusedFiles=[];")
    assert take < ret < reset
    assert "coverageDoc" not in body[reset:]


def _node(script):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    r = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _today_js():
    html = _html()
    fns = "\n".join(_fn(html, n) for n in ("esc", "takeCoverage", "countdownText", "todayIds", "todayGroupHTML",
                                           "todayTileHTML"))
    return 'let coverageDoc=null, coverageName="", coverageNote="";\n' + fns


COV = {"kind": "coverage_v1", "date": "2026-10-18", "now": "2026-10-18T12:00:00Z", "now_et": "2026-10-18 08:00 ET",
       "gaps": ["PL: 1 GAME, 0 PREDICTION ROWS — soccer-prematch has not run"], "roadmap": [],
       "competitions": [{"code": "PL", "games": [401, 402], "void": [[403, "POSTPONED"]], "status": "LIVE",
                         "status_label": "LIVE", "status_from": "closing family SOCCER; <script>x()</script>",
                         "family": "SOCCER", "refused": None, "closing_unread": None, "writers": ["soccer-prematch"],
                         "rows": [{"model_version": "v22", "rows": 1, "computed_et": "latest 2026-10-18 07:00 ET"}],
                         "without_rows_text": "without rows: 402", "rows_text": "rows: v22 1 (latest …)",
                         "started": [], "finished": [], "closing_text": "closing: …", "line": "PL · …",
                         "groups": [{"state": "ahead", "run_lead": "T-35", "run_at_et": "09:25 ET",
                                     "run_at": "2026-10-18T13:25:00Z", "match_ids": [401, 402],
                                     "text": "T-35 09:25 ET [401, 402] → exports/closing_SOCCER_2026-10-18T1400Z.json"},
                                    {"state": "done", "run_lead": "T-35", "run_at_et": "08:05 ET", "run_id": "R1",
                                     "exit": 0, "run_at": "2026-10-18T12:05:00Z", "match_ids": [9], "text": "…"}]}]}


def test_the_intake_takes_coverage_apart_and_keeps_the_rest_for_the_slate():
    """A coverage file leaves the batch (the slate path gets the rest, in order, a file it cannot read included);
    several in one load: the newest by date then now is shown and the others named; nothing of the slate is read."""
    older = dict(COV, date="2026-10-17", now="2026-10-17T12:00:00Z")
    files = [{"name": "nfl.json", "text": json.dumps({"sport": "nfl", "predictions": []})},
             {"name": "coverage_2026-10-17.json", "text": json.dumps(older)},
             {"name": "broken.json", "text": "{not json"},
             {"name": "coverage_2026-10-18.json", "text": json.dumps(COV)}]
    got = _node(_today_js() + f"""
const r=takeCoverage({json.dumps(files)});
const alone=(()=>{{coverageDoc=null; return takeCoverage([{json.dumps(files[1])}]);}})();
console.log(JSON.stringify({{rest:r.rest.map(f=>f.name),taken:r.taken,alone:[alone.rest.length,alone.taken],
  shown:coverageName}}));""")
    assert got == {"rest": ["nfl.json", "broken.json"], "taken": 2, "alone": [0, 1],
                   "shown": "coverage_2026-10-17.json"}
    note = _node(_today_js() + f"""takeCoverage({json.dumps(files)});
console.log(JSON.stringify([coverageName,coverageNote,coverageDoc.date]));""")
    assert note[0] == "coverage_2026-10-18.json" and note[2] == "2026-10-18"
    assert "2 coverage files in this load: showing the newest (coverage_2026-10-17.json not shown)" in note[1]


def test_a_tile_renders_the_files_words_escaped_with_a_countdown_only_on_a_group_to_run():
    tile = _node(_today_js() + f"""console.log(JSON.stringify(todayTileHTML({json.dumps(COV["competitions"][0])})));""")
    assert 'data-games="2">2 games</span>' in tile and "void, not counted: 403 POSTPONED" in tile
    assert "<script>" not in tile and "&lt;script&gt;x()&lt;/script&gt;" in tile
    assert "soccer-prematch" in tile and "<b>v22</b> 1 row · latest 2026-10-18 07:00 ET" in tile
    assert tile.count('class="countdown"') == 1 and 'data-run-at="2026-10-18T13:25:00Z"' in tile
    assert "run <code>R1</code>, exit 0" in tile
    unknown = dict(COV["competitions"][0], status="POT", status_label="POT (training data only)", groups=[],
                   family=None, closing_text="closing: none (no closing family covers SA)")
    t2 = _node(_today_js() + f"""console.log(JSON.stringify(todayTileHTML({json.dumps(unknown)})));""")
    assert 'data-status="POT"' in t2 and '<div class="slabel">POT (training data only)</div>' in t2
    assert "closing: none (no closing family covers SA)" in t2


@pytest.mark.parametrize("ms, text", [(3907000, "T-35 in 1h 05m 07s"), (59000, "T-35 in 0h 00m 59s"),
                                      (0, "T-35 passed"), (-5000, "T-35 passed")])
def test_the_countdown_text(ms, text):
    assert _node(_today_js() + f"console.log(JSON.stringify(countdownText({ms},'T-35')));") == text
