"""THE COCKPIT'S exec <= 0 DISPLAY (ARCHITECT 2026-11-09 12:50 ET, addendum 309 item 5(b), on addendum 305's rule).

Item 5(b), verbatim: "305's three display gaps — the help line's "else HALF" gains "exec ≤ 0 PASS"; `passKindTag` labels
`exec_non_positive` ("exec ≤ 0"); `passSummary` counts the kind on its own".

Pins: (1) the EXEC EDGE help line reads "else HALF ... exec ≤ 0 PASS"; (2) passKindTag labels exec_non_positive
"exec ≤ 0" and every other kind as before; (3) passSummary counts exec_non_positive rows on their own, never under
"other", and policy() counts the file's pass kind into that count; (4) the call itself is the file's (fileCall), the
Cockpit computes no exec PASS. The Cockpit renders the Desk's file; nothing here is a policy computation.
"""
import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def _cockpit():
    return open(os.path.join(ROOT, "tools", "cockpit.html"), encoding="utf-8").read()


def _fn(html, name):
    m = re.search(r"^function " + name + r"\(.*?^\}", html, re.S | re.M)
    assert m, name
    return m.group(0)


def _node(tmp_path, *lines):
    f = tmp_path / "x.js"
    f.write_text("\n".join(lines), encoding="utf-8")
    return json.loads(subprocess.run(["node", str(f)], capture_output=True, text=True, check=True,
                                     encoding="utf-8").stdout)


def test_the_help_line_says_exec_at_or_below_zero_is_a_pass():
    html = _cockpit()
    line = next(x for x in html.splitlines() if "<b>EXEC EDGE</b>" in x)
    assert "a PLAY gets full tier units only at exec edge ≥ 4pp, else HALF (no executable quote = half); exec ≤ 0 PASS" \
        in line


@NODE
def test_pass_kind_tag_labels_exec_non_positive(tmp_path):
    html = _cockpit()
    kinds = ["exec_non_positive", "noref", "floor", "started", "shadow_league", "kalshi_only_suspended",
             "kickoff_clock", "market_only", None, "something_new"]
    out = _node(tmp_path, _fn(html, "passKindTag"), f"console.log(JSON.stringify({json.dumps(kinds)}.map(passKindTag)));")
    assert out[0] == '<span class="passkind">exec ≤ 0</span>'
    assert out[1:] == ['<span class="passkind">no reference</span>', '<span class="passkind">below floor</span>',
                       '<span class="passkind">started</span>', '<span class="passkind">shadow league</span>',
                       '<span class="passkind">kalshi-only suspended</span>',
                       '<span class="passkind">kickoff disputed</span>',
                       '<span class="passkind">market-only · uncertified</span>', "", ""]


@NODE
def test_pass_summary_counts_exec_non_positive_on_its_own(tmp_path):
    html = _cockpit()
    z = dict(passes=0, passNoRef=0, passFloor=0, passStarted=0, passShadow=0, passKoSusp=0, passMktOnly=0,
             passExecNonPos=0)
    cases = [{**z, "passes": 2, "passExecNonPos": 2},
             {**z, "passes": 5, "passNoRef": 1, "passExecNonPos": 2, "passMktOnly": 1},
             {**z, "passes": 4, "passNoRef": 1, "passExecNonPos": 2},
             {**z, "passes": 3, "passNoRef": 3}]
    out = _node(tmp_path, _fn(html, "passSummary"), f"console.log(JSON.stringify({json.dumps(cases)}.map(passSummary)));")
    assert out == [" (0 no reference · 0 below floor · 2 exec ≤ 0)",
                   " (1 no reference · 0 below floor · 1 market-only (NFL, uncertified) · 2 exec ≤ 0 · 1 other)",
                   " (1 no reference · 0 below floor · 2 exec ≤ 0 · 1 other)",
                   " (3 no reference · 0 below floor)"]


def test_policy_counts_the_files_exec_non_positive_kind_into_its_own_count():
    pol = _fn(_cockpit(), "policy")
    assert 'else if(passKind==="exec_non_positive")passExecNonPos++;' in pol
    assert "passExecNonPos=0" in pol
    assert "passSummary({passes,passNoRef,passFloor,passStarted,passShadow,passKoSusp,passMktOnly,passExecNonPos})" in pol


@NODE
def test_the_call_is_the_files_pass_the_cockpit_computes_none(tmp_path):
    """A PASS exec_non_positive row renders as the file wrote it; a file PLAY with a negative exec edge stays the file's
    PLAY (the Desk decides, the Cockpit only renders)."""
    html = _cockpit()
    reason = "exec edge -0.2pp <= 0: all-in cost 73.4c above the model's 73.2c (addendum 305)"
    rows = [{"fileDesk": {"call": "PASS", "cls": "pass", "units": 0, "edge_pp": 5.1, "reasons": [reason],
                          "pass_kind": "exec_non_positive", "exec": {"exec_edge_pp": -0.2}}},
            {"fileDesk": {"call": "PLAY", "cls": "play", "units": 0.5, "edge_pp": 5.1, "reasons": [],
                          "pass_kind": None, "exec": {"exec_edge_pp": -0.2}}}]
    out = _node(tmp_path, _fn(html, "passKindTag"), _fn(html, "fileCall"), f"const R={json.dumps(rows)};",
                "console.log(JSON.stringify(R.map(r=>{const c=fileCall(r);"
                "return [c.call,c.units,c.passKind,c.reasons.join(' · '),passKindTag(c.passKind)];})));")
    assert out == [["PASS", 0, "exec_non_positive", reason, '<span class="passkind">exec ≤ 0</span>'],
                   ["PLAY", 0.5, None, "", ""]]
