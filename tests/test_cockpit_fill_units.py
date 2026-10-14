"""COCKPIT FILL UNITS (#487, ARCHITECT 2026-10-13; addendum 67 item 3, 2026-10-14): a fill's units are its entry cost
over the unit dollars read from the loaded files' order lines ("1u = $N", as desk_policy.file_unit_basis reads it);
FILL_UNIT_CONTRACTS=10 goes; the page holds no dollar figure; a file whose order lines carry no unit basis shows the
fill in contracts with the label "contracts (no unit basis in file)", never a guessed unit. The page's own functions
run under node on synthetic fills."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

COCKPIT = Path(__file__).resolve().parents[1] / "tools" / "cockpit.html"


def _html():
    return COCKPIT.read_text()


def _fn(html, name):
    """The top-level function `name`, whole: from its line to the brace that closes its body (braces counted)."""
    m = re.search(r"^function " + name + r"\(", html, re.M)
    assert m, name
    i, depth = html.index("{", m.end()), 0
    for j in range(i, len(html)):
        depth += {"{": 1, "}": -1}.get(html[j], 0)
        if depth == 0:
            return html[m.start():j + 1]
    raise AssertionError(name)


def _const(html, name):
    m = re.search(r"^const " + name + r"=.*?;$", html, re.M)
    assert m, name
    return m.group(0)


def test_the_constant_is_gone_and_no_dollar_figure_is_held():
    html = _html()
    assert "FILL_UNIT_CONTRACTS" not in html
    block = html[html.index("// B-TRACK FILLS EXPOSURE"):html.index("function realizedLines(")]
    assert not re.search(r"\$\s?\d", block.replace("1u = $N", "").replace("$${", "").replace("$$(", ""))
    head = " ".join(html[:html.index("<html")].split())
    assert "FILL UNITS (#487" in head and '"contracts (no unit basis in file)"' in head


def _row(unit):
    return {"fileDesk": {"order": {"text": "BUY ...", "unit": unit}}}


# one MLB game, YES on the home team: 30 contracts at 0.40 (cost $12.00) and 10 contracts at 0.50 ($5.00); a NO on
# the away team: 20 contracts at 0.30 ($6.00), paying on HOME too. HOME pays 60 contracts on $23.00 of entry cost.
FILLS = [
    {"kind": "sport", "family": "MLB", "date": "26OCT14", "teams": "MILLAD", "sideCode": "LAD", "side": "yes",
     "qty": 30, "entry": 0.40, "fees": 0.21, "ticker": "KXMLBGAME-26OCT142000MILLAD-LAD"},
    {"kind": "sport", "family": "MLB", "date": "26OCT14", "teams": "MILLAD", "sideCode": "LAD", "side": "yes",
     "qty": 10, "entry": 0.50, "fees": 0.07, "ticker": "KXMLBGAME-26OCT142000MILLAD-LAD"},
    {"kind": "sport", "family": "MLB", "date": "26OCT14", "teams": "MILLAD", "sideCode": "MIL", "side": "no",
     "qty": 20, "entry": 0.30, "fees": 0.10, "ticker": "KXMLBGAME-26OCT142000MILLAD-MIL"},
]


def _run(tmp_path, rows):
    html = _html()
    js = "\n".join([_const(html, "THREE_WAY_FAMILIES"), _const(html, "BTRACK_CAP_U"), _fn(html, "esc"),
                    _fn(html, "tickerRole"), _fn(html, "fillUnitBasis"), _fn(html, "fillUnitLabel"),
                    _fn(html, "fillExposure"), _fn(html, "exposureOutcomeName"), _fn(html, "exposureHeadline"),
                    _fn(html, "exposureHTML"),
                    f"const rows={json.dumps(rows)}; let fileParlays=null;",   # the page's two globals
                    f"const L={json.dumps({'fills': FILLS})};",
                    "const b=fillUnitBasis(rows), x=fillExposure(L,b);",
                    "const home=x.games[0].outcomes.find(o=>o.outcome==='HOME');",
                    "console.log(JSON.stringify({basis:b,label:x.unitLabel,home,over:x.summary.over,"
                    "head:exposureHeadline(x),html:exposureHTML(L)}));"])
    f = tmp_path / "fill_units.js"
    f.write_text(js)
    return json.loads(subprocess.run(["node", str(f)], capture_output=True, text=True, check=True).stdout)


needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


@needs_node
def test_a_dollar_unit_reads_the_entry_cost_over_the_files_unit(tmp_path):
    out = _run(tmp_path, [_row("1u = $20"), _row("1u = $20")])
    assert out["basis"] == {"mode": "usd", "value": 20} and out["label"] == "1u = $20"
    h = out["home"]
    assert h["contracts"] == 60 and h["cost"] == pytest.approx(23.0)
    assert h["units"] == pytest.approx(23.0 / 20) and h["over"] is False      # 1.15u, under the 1.25u cap
    out = _run(tmp_path, [_row("1u = $15")])
    assert out["home"]["units"] == pytest.approx(23.0 / 15) and out["home"]["over"] is True and out["over"] == 1
    assert "units at 1u = $15" in out["head"] and "60 ct ≈ 1.53u &gt; 1.25u" in out["html"]


@needs_node
def test_a_contracts_unit_reads_contracts_over_the_files_count(tmp_path):
    out = _run(tmp_path, [_row("1u = 10 contracts (SP_UNIT_USD unset)")])
    assert out["basis"] == {"mode": "contracts", "value": 10}
    assert out["home"]["units"] == pytest.approx(6.0) and out["home"]["over"] is True
    assert "contracts ≈ units at 1u = 10 contracts, beside the 1.25u cap" in out["html"]


@needs_node
def test_no_unit_basis_in_the_file_shows_contracts_never_a_guessed_unit(tmp_path):
    for rows in ([], [{"fileDesk": {"order": {"why": "no order"}}}], [{"fileDesk": None}]):
        out = _run(tmp_path, rows)
        assert out["basis"] is None and out["label"] == "contracts (no unit basis in file)"
        assert out["home"]["units"] is None and out["home"]["over"] is False and out["over"] is None
        assert "per team-outcome (contracts (no unit basis in file))" in out["html"]
        assert "60 ct · if it lands" in out["html"] and "≈" not in out["html"].split("<tbody>")[1]
        assert "cap-equivalent not read (no unit)" in out["head"]


@needs_node
def test_files_that_disagree_on_the_unit_show_contracts_and_name_both(tmp_path):
    out = _run(tmp_path, [_row("1u = $20"), _row("1u = $25")])
    assert out["label"] == "contracts (the loaded files' unit bases differ: 1u = $20 vs 1u = $25)"
    assert out["home"]["units"] is None and out["over"] is None


@needs_node
def test_a_parlay_files_ticket_legs_count_as_loaded_order_lines(tmp_path):
    """Codex on #523: every accepted loaded file counts, a desk_parlays file's ticket legs included (its legs carry
    desk_policy's order lines, unit and all). A parlays file alone gives its basis; beside prediction rows that
    disagree, the bases conflict and nothing is picked."""
    html = _html()
    parl = {"kind": "desk_parlays_v1", "tickets": [{"legs": [{"order": {"text": "BUY", "unit": "1u = $20"}},
                                                             {"order": {"text": "BUY", "unit": "1u = $20"}}]}]}
    js = "\n".join([_fn(html, "fillUnitBasis"), _fn(html, "fillUnitLabel"),
                    f"const P={json.dumps(parl)};",
                    "console.log(JSON.stringify([fillUnitBasis([],P), fillUnitLabel(fillUnitBasis([],P)),"
                    f"fillUnitLabel(fillUnitBasis({json.dumps([_row('1u = $25')])},P)), fillUnitBasis([],null)]));"])
    f = tmp_path / "parl.js"
    f.write_text(js)
    out = json.loads(subprocess.run(["node", str(f)], capture_output=True, text=True, check=True).stdout)
    assert out[0] == {"mode": "usd", "value": 20} and out[1] == "1u = $20"
    assert out[2] == "contracts (the loaded files' unit bases differ: 1u = $25 vs 1u = $20)"
    assert out[3] is None


def test_the_page_reads_the_basis_from_the_rows_and_the_parlays_file():
    html = _html()
    assert html.count("fillUnitBasis(rows,fileParlays)") == 2 and "fillUnitBasis(rows)" not in html
