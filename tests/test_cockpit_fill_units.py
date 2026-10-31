"""COCKPIT FILL UNITS (#487, ARCHITECT 2026-10-13; addendum 67 item 3, 2026-10-14): a fill's units are its entry cost
over the unit dollars read from the loaded files' order lines ("1u = $N", as desk_policy.file_unit_basis reads it);
FILL_UNIT_CONTRACTS=10 goes; the page holds no dollar figure; a file whose order lines carry no unit basis shows the
fill in contracts with the label "contracts (no unit basis in file)", never a guessed unit. The page's own functions
run under node on synthetic fills.

DESK POLICY v1.2 (#740). The ruling (ARCHITECT 2026-10-30 11:20 ET, addendum 182 item 6), as recorded on #734: "the
Cockpit gets one follow-up PR:" / "- `POLICY_VERSION` v1.2;" / "- fills converted by the file's own ET day;" / "- the
"unit unread" label rendered as contracts only.". The Issue's plan (#740, "The PR (one, after #734)"): "1. Set
`POLICY_VERSION` to v1.2." "2. Convert each fill's units by the unit of the file's own ET day: its `desk_meta.unit`
label, read on that file's ET date, never another day's." "3. Render an unread day's label ("unit unread — no order")
as contracts only, with no dollar basis." "4. Test it through the cockpit verifies, on synthetic files only." Every unit
below is a synthetic fixture."""
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
    assert "BY THE FILE'S ET DAY (Desk policy v1.2, #740" in head and '"unit unread — no order"' in head
    assert '"contracts (no unit basis for <date> in the loaded files)"' in head


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


JS_FNS = ("esc", "tickerRole", "unitLabelBasis", "fillUnitBasis", "fillUnitLabel", "fileDayUnit", "fillDayBases",
          "fillEtDate", "fillDayBasis", "fillDayText", "fillExposure", "exposureOutcomeName", "exposureDaysText",
          "exposureHeadline", "exposureHTML")


def _node(tmp_path, body, name="fill_units.js"):
    html = _html()
    js = "\n".join([_const(html, "MONTHS"), _const(html, "THREE_WAY_FAMILIES"), _const(html, "BTRACK_CAP_U")]
                   + [_fn(html, n) for n in JS_FNS] + [body])
    f = tmp_path / name
    f.write_text(js)
    return json.loads(subprocess.run(["node", str(f)], capture_output=True, text=True, check=True).stdout)


def _run(tmp_path, rows, fills=FILLS, parlays=None):
    """The page's exposure over `fills` with `rows` (and a desk_parlays file) loaded: the day bases, every game (its
    ET date, its day's unit, its outcomes), the summary, the headline and the block's HTML."""
    return _node(tmp_path, "\n".join([
        f"const rows={json.dumps(rows)}; let fileParlays={json.dumps(parlays)};",   # the page's two globals
        f"const L={json.dumps({'fills': fills})};",
        "const db=fillDayBases(rows,fileParlays), x=fillExposure(L,db);",
        "const g0=x.games.find(g=>g.teams==='MILLAD')||x.games[0];",
        "const home=g0?g0.outcomes.find(o=>o.outcome==='HOME'):null;",
        "const games=Object.fromEntries(x.games.map(g=>[g.key,{etDate:g.etDate,unit:g.unit,outcomes:g.outcomes}]));",
        "console.log(JSON.stringify({db,basis:db.legacy,label:g0?g0.unit.label:null,home,over:x.summary.over,"
        "summary:x.summary,days:x.days,games,head:exposureHeadline(x),html:exposureHTML(L)}));"]))


needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


# ---- v1.1 files (no dated desk_meta.unit): the order-line basis, today's behaviour, for the days before any v1.2 day

@needs_node
def test_a_dollar_unit_reads_the_entry_cost_over_the_files_unit(tmp_path):
    out = _run(tmp_path, [_row("1u = $20"), _row("1u = $20")])
    assert out["basis"] == {"mode": "usd", "value": 20} and out["label"] == "1u = $20"
    assert out["db"]["days"] == {} and out["days"][0]["kind"] == "legacy"
    h = out["home"]
    assert h["contracts"] == 60 and h["cost"] == pytest.approx(23.0)
    assert h["units"] == pytest.approx(23.0 / 20) and h["over"] is False      # 1.15u, under the 1.25u cap
    out = _run(tmp_path, [_row("1u = $15")])
    assert out["home"]["units"] == pytest.approx(23.0 / 15) and out["home"]["over"] is True and out["over"] == 1
    assert "units by the file's ET day: 1 day(s) no v1.2 file names at 1u = $15 (the v1.1 files' order lines)" \
        in out["head"]
    assert "over the 1.25u cap-equivalent 1 (of 1 team-outcome(s) with a unit)" in out["head"]
    assert "60 ct ≈ 1.53u &gt; 1.25u" in out["html"] and "2026-10-14: 1u = $15" in out["html"]


@needs_node
def test_a_contracts_unit_reads_contracts_over_the_files_count(tmp_path):
    out = _run(tmp_path, [_row("1u = 10 contracts (SP_UNIT_USD unset)")])
    assert out["basis"] == {"mode": "contracts", "value": 10}
    assert out["home"]["units"] == pytest.approx(6.0) and out["home"]["over"] is True
    assert "contracts ≈ units at the unit of the game&#39;s own ET day, beside the 1.25u cap" in out["html"]
    assert "2026-10-14: 1u = 10 contracts" in out["html"]


@needs_node
def test_no_unit_basis_in_the_file_shows_contracts_never_a_guessed_unit(tmp_path):
    for rows in ([], [{"fileDesk": {"order": {"why": "no order"}}}], [{"fileDesk": None}]):
        out = _run(tmp_path, rows)
        assert out["basis"] is None and out["label"] == "contracts (no unit basis for 2026-10-14 in the loaded files)"
        assert out["home"]["units"] is None and out["home"]["over"] is None and out["over"] is None
        assert "per team-outcome (contracts only: no unit for these days in the loaded files)" in out["html"]
        assert "60 ct · if it lands" in out["html"] and "≈" not in out["html"].split("<tbody>")[1]
        assert "cap-equivalent not read (no unit)" in out["head"]
        assert "3 fill(s) in contracts only (no unit for their day)" in out["head"]


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
    parl = {"kind": "desk_parlays_v1", "tickets": [{"legs": [{"order": {"text": "BUY", "unit": "1u = $20"}},
                                                             {"order": {"text": "BUY", "unit": "1u = $20"}}]}]}
    out = _node(tmp_path, "\n".join([
        f"const P={json.dumps(parl)};",
        "console.log(JSON.stringify([fillUnitBasis([],P), fillUnitLabel(fillUnitBasis([],P)),"
        f"fillUnitLabel(fillUnitBasis({json.dumps([_row('1u = $25')])},P)), fillUnitBasis([],null)]));"]), "parl.js")
    assert out[0] == {"mode": "usd", "value": 20} and out[1] == "1u = $20"
    assert out[2] == "contracts (the loaded files' unit bases differ: 1u = $25 vs 1u = $20)"
    assert out[3] is None


def test_the_page_reads_the_basis_from_the_rows_and_the_parlays_file():
    html = _html()
    assert html.count("fillDayBases(rows,fileParlays)") == 2 and "fillUnitBasis(rows" not in html
    assert "fillExposure(L,fillUnitBasis" not in html


# ---- v1.2 (#740): the unit of the file of the fill's own ET day ----------------------------------------------------

def _meta(et_date, label, state="read", as_of=None):
    """A v1.2 file's desk_meta, as desk_policy.unit_meta writes it (synthetic units only)."""
    return {"policy_version": "v1.2", "as_of": as_of or f"{et_date}T16:00:00Z",
            "unit": {"state": state, "et_date": et_date, "label": label, "why": None, "fraction": 0.08,
                     "half_fraction": 0.04, "floor_name": "SP_UNIT_FLOOR_USD"}}


def _row12(et_date, label, state="read", as_of=None):
    unit = label if state == "read" else "unit unread"
    order = {"text": "BUY ...", "unit": unit} if state == "read" else {"text": None, "unit": unit,
                                                                       "why": "unit unread — no order"}
    return {"fileDesk": {"order": order}, "deskMeta": _meta(et_date, label, state, as_of)}


def _fill(ticker, side, qty, entry, fees=0.05):
    """A sport fill in the fixtures' shape above (family, teams, side code; the exposure reads the day from the
    ticker, never from `date`)."""
    ev, code = ticker.rsplit("-", 1)
    mid = ev.split("-", 1)[1]
    teams = mid[11:] if mid[7:11].isdigit() else mid[7:]      # yyMONdd[hhmm]TEAMS
    fam = ev.split("-")[0][2:-4]
    return {"kind": "sport", "family": fam, "date": mid[:7], "teams": teams,
            "sideCode": code, "side": side, "qty": qty, "entry": entry, "fees": fees, "ticker": ticker}


# day 2 (10-15): YES on BOS (home) 10 at 0.50 = 5.00 of entry cost; day 3 (10-16): YES on KC (home) 20 at 0.40 = 8.00
DAY2 = _fill("KXMLBGAME-26OCT151905NYYBOS-BOS", "yes", 10, 0.50)
DAY3 = _fill("KXNFLGAME-26OCT16BUFKC-KC", "yes", 20, 0.40)
MULTI = FILLS + [DAY2, DAY3]
G1, G2, G3 = "KXMLBGAME-26OCT142000MILLAD", "KXMLBGAME-26OCT151905NYYBOS", "KXNFLGAME-26OCT16BUFKC"


def _home(out, key):
    return next(o for o in out["games"][key]["outcomes"] if o["outcome"] == "HOME")


@needs_node
def test_each_fill_converts_by_the_unit_of_its_own_et_day(tmp_path):
    """Item 2: two days with different units; each fill on its own day's file, never the other's."""
    out = _run(tmp_path, [_row12("2026-10-14", "1u = $20"), _row12("2026-10-15", "1u = $4")], MULTI)
    assert out["db"]["days"] == {"2026-10-14": {"mode": "usd", "value": 20}, "2026-10-15": {"mode": "usd", "value": 4}}
    assert out["db"]["legacy"] is None            # a v1.2 file's order lines never make a basis for another day
    assert out["games"][G1]["etDate"] == "2026-10-14" and out["games"][G2]["etDate"] == "2026-10-15"
    assert _home(out, G1)["units"] == pytest.approx(23.0 / 20) and _home(out, G1)["over"] is False
    assert _home(out, G2)["units"] == pytest.approx(5.0 / 4) and _home(out, G2)["over"] is False   # 1.25u: at the cap
    # 10-16: no file of that day is loaded -> contracts only, labelled, no cap comparison
    g3 = out["games"][G3]
    assert g3["unit"]["kind"] == "missing" and _home(out, G3)["units"] is None and _home(out, G3)["over"] is None
    assert g3["unit"]["label"] == "contracts (no unit basis for 2026-10-16 in the loaded files)"
    assert out["summary"]["withUnit"] == 2 and out["over"] == 0 and out["summary"]["contractsOnlyFills"] == 1
    assert ("units by the file's ET day: 2026-10-14 1u = $20; 2026-10-15 1u = $4; 2026-10-16 contracts (no unit "
            "basis for 2026-10-16 in the loaded files)") in out["head"]
    assert "over the 1.25u cap-equivalent 0 (of 2 team-outcome(s) with a unit)" in out["head"]
    assert "1 fill(s) in contracts only (no unit for their day)" in out["head"]
    assert "20 ct · if it lands" in out["html"] and "2026-10-16: contracts (no unit basis for 2026-10-16" in out["html"]
    # the same fills, the days' units swapped: each game follows its own day
    out = _run(tmp_path, [_row12("2026-10-14", "1u = $4"), _row12("2026-10-15", "1u = $20")], MULTI)
    assert _home(out, G1)["units"] == pytest.approx(23.0 / 4) and _home(out, G1)["over"] is True
    assert _home(out, G2)["units"] == pytest.approx(5.0 / 20) and out["over"] == 1


@needs_node
def test_an_unread_day_is_contracts_only_with_the_unread_label(tmp_path):
    """Item 3: an unread day's fills are contracts only, labelled "unit unread — no order", no dollar basis."""
    for state in ("unread", "absent", "file", "unknown"):
        out = _run(tmp_path, [_row12("2026-10-14", "1u = $20"), _row12("2026-10-15", "unit unread", state)], MULTI)
        assert out["db"]["days"]["2026-10-15"] == {"unread": True}
        g2 = out["games"][G2]
        assert g2["unit"] == {"basis": None, "kind": "unread", "label": "unit unread — no order"}
        assert _home(out, G2)["units"] is None and _home(out, G2)["over"] is None
        assert _home(out, G1)["units"] == pytest.approx(23.0 / 20)      # the read day keeps its own unit
        assert "2026-10-15 unit unread — no order (contracts only)" in out["head"]
        assert ('2026-10-15: unit unread — no order (contracts only)</span><br><span class="">BOS (home): 10 ct · if it '
                'lands') in out["html"]
    # a label the state does not vouch for is never a unit (law 4): read with a contracts label, contracts with dollars
    out = _run(tmp_path, [_row12("2026-10-15", "1u = 10 contracts", "read")], [DAY2])
    assert out["db"]["days"]["2026-10-15"] == {"unread": True}
    out = _run(tmp_path, [_row12("2026-10-15", "1u = $20", "contracts")], [DAY2])
    assert out["db"]["days"]["2026-10-15"] == {"unread": True}
    out = _run(tmp_path, [_row12("2026-10-15", "1u = 10 contracts (SP_UNIT_USD unset)", "contracts")], [DAY2])
    assert out["db"]["days"]["2026-10-15"] == {"mode": "contracts", "value": 10}


@needs_node
def test_a_fill_whose_day_has_no_loaded_file_is_contracts_only(tmp_path):
    out = _run(tmp_path, [_row12("2026-10-15", "1u = $20")], FILLS)
    assert out["label"] == "contracts (no unit basis for 2026-10-14 in the loaded files)"
    assert out["home"]["units"] is None and out["home"]["over"] is None and out["over"] is None
    assert "cap-equivalent not read (no unit)" in out["head"] and "3 fill(s) in contracts only" in out["head"]
    assert "≈" not in out["html"].split("<tbody>")[1]


@needs_node
def test_two_files_of_one_day_that_disagree_are_a_conflict(tmp_path):
    out = _run(tmp_path, [_row12("2026-10-14", "1u = $20"), _row12("2026-10-14", "1u = $25")], FILLS)
    assert out["db"]["days"]["2026-10-14"] == {"conflict": ["1u = $20", "1u = $25"]}
    assert out["label"] == "contracts (the loaded files of 2026-10-14 differ on the unit: 1u = $20 vs 1u = $25)"
    assert out["home"]["units"] is None and out["home"]["over"] is None and out["over"] is None
    # a desk_parlays file of that day is a loaded file too
    parl = {"kind": "desk_parlays_v1", "desk_meta": _meta("2026-10-14", "1u = $25"), "tickets": []}
    out = _run(tmp_path, [_row12("2026-10-14", "1u = $20")], FILLS, parl)
    assert out["db"]["days"]["2026-10-14"] == {"conflict": ["1u = $20", "1u = $25"]} and out["over"] is None
    # agreeing files of one day are that day's unit; an unread page of a day another page read leaves the read unit
    out = _run(tmp_path, [_row12("2026-10-14", "1u = $20"), _row12("2026-10-14", "1u = $20"),
                          _row12("2026-10-14", "unit unread", "unread")], FILLS, {"desk_meta": _meta("2026-10-14", "1u = $20"),
                                                                                  "tickets": []})
    assert out["db"]["days"]["2026-10-14"] == {"mode": "usd", "value": 20}
    assert out["home"]["units"] == pytest.approx(23.0 / 20)


V11 = {"fileDesk": {"order": {"text": "BUY", "unit": "1u = $10"}},
       "deskMeta": {"policy_version": "v1.1", "as_of": "2026-10-13T16:00:00Z"}}


@needs_node
def test_a_v11_file_beside_v12_files_keeps_its_order_line_basis_before_the_first_v12_day(tmp_path):
    """A v1.1 file (no dated desk_meta.unit; a v1.2 file with an undated unit, the tests' contracts pin, reads the
    same way) keeps today's behaviour for the days before the first ET day a loaded v1.2 file names; the days a v1.2
    file names are its own, and a later day no v1.2 file names is contracts only: the retired v1.1 unit is never
    another (v1.2-era) day's (item 2, "never another day's"; law 4)."""
    out = _run(tmp_path, [V11, _row12("2026-10-15", "unit unread", "unread")], MULTI)
    assert out["db"]["legacy"] == {"mode": "usd", "value": 10}
    assert out["games"][G1]["unit"]["kind"] == "legacy" and _home(out, G1)["units"] == pytest.approx(23.0 / 10)
    assert out["games"][G2]["unit"]["kind"] == "unread" and _home(out, G2)["units"] is None     # never the v1.1 unit
    g3 = out["games"][G3]
    assert g3["unit"]["kind"] == "missing" and _home(out, G3)["units"] is None and _home(out, G3)["over"] is None
    assert g3["unit"]["label"] == "contracts (no unit basis for 2026-10-16 in the loaded files)"
    assert ("2026-10-15 unit unread — no order (contracts only); 2026-10-16 contracts (no unit basis for 2026-10-16 in "
            "the loaded files); 1 day(s) no v1.2 file names at 1u = $10 (the v1.1 files' order lines)") in out["head"]
    # with no v1.2 file loaded, the v1.1 basis is every day's, as before
    out = _run(tmp_path, [V11], MULTI)
    assert all(out["games"][k]["unit"]["kind"] == "legacy" for k in (G1, G2, G3))
    pinned = {"fileDesk": {"order": {"text": "BUY", "unit": "1u = 10 contracts (SP_UNIT_USD unset)"}},
              "deskMeta": {"policy_version": "v1.2", "unit": {"state": "contracts", "et_date": None,
                                                               "label": "1u = 10 contracts (SP_UNIT_USD unset)"}}}
    out = _run(tmp_path, [pinned], FILLS)
    assert out["db"] == {"days": {}, "legacy": {"mode": "contracts", "value": 10}}
    assert out["home"]["units"] == pytest.approx(6.0)


@needs_node
def test_a_conflicted_day_stays_a_conflict_beside_a_v11_file(tmp_path):
    """Two 10-14 files that differ, a v1.1 file loaded too: 10-14 is a conflict (contracts only), never the v1.1 unit."""
    out = _run(tmp_path, [V11, _row12("2026-10-14", "1u = $20"), _row12("2026-10-14", "1u = $25")], FILLS)
    assert out["db"]["legacy"] == {"mode": "usd", "value": 10}
    assert out["games"][G1]["unit"]["kind"] == "conflict"
    assert out["home"]["units"] is None and out["home"]["over"] is None and out["over"] is None


@needs_node
def test_a_files_day_is_its_unit_et_date_never_the_utc_date_of_as_of(tmp_path):
    """Item 2, "read on that file's ET date": an evening export (21:30 ET on 10-14) has as_of on the next UTC day; its
    unit is 10-14's, and 10-15 has no file."""
    row = _row12("2026-10-14", "1u = $20", as_of="2026-10-15T01:30:00Z")
    out = _run(tmp_path, [row], MULTI)
    assert out["db"]["days"] == {"2026-10-14": {"mode": "usd", "value": 20}}
    assert out["games"][G1]["unit"]["kind"] == "day" and _home(out, G1)["units"] == pytest.approx(23.0 / 20)
    assert out["games"][G2]["unit"]["label"] == "contracts (no unit basis for 2026-10-15 in the loaded files)"
    assert _home(out, G2)["units"] is None


@needs_node
def test_the_headline_names_the_latest_8_days_and_counts_the_rest(tmp_path):
    """C6: fills on 10 ET days (no file loaded): the 2 earliest are counted, the latest 8 named in date order."""
    fills = [_fill(f"KXMLBGAME-26OCT{d:02d}MILLAD-LAD", "yes", 10, 0.50) for d in range(5, 15)]
    out = _run(tmp_path, [], fills)
    clause = "; ".join(f"2026-10-{d:02d} contracts (no unit basis for 2026-10-{d:02d} in the loaded files)"
                       for d in range(7, 15))
    assert f"units by the file's ET day: 2 earlier day(s) not named; {clause} · " in out["head"]


@needs_node
def test_the_fills_et_date_is_the_tickers(tmp_path):
    out = _node(tmp_path, "console.log(JSON.stringify(['KXMLBGAME-26OCT142000MILLAD','KXNFLGAME-26NOV01BUFKC',"
                          "'kxeplgame-26dec26arsche','KXMLBGAME','KXMLBGAME-26XYZ14MILLAD'].map(fillEtDate)));",
                "dates.js")
    assert out == ["2026-10-14", "2026-11-01", "2026-12-26", None, None]


def test_policy_version_is_v12_and_the_ledger_follows_it():
    html = _html()
    assert _const(html, "LEDGER_KEY") == 'const LEDGER_KEY="bd_ledger_v1", POLICY_VERSION="v1.2";'
    assert "function emptyLedger(){return {meta:{policy_version:POLICY_VERSION},calls:[]};}" in html
    assert "L.meta.policy_version=POLICY_VERSION;" in html and "policy_version:POLICY_VERSION," in html


@needs_node
def test_a_v11_file_shows_the_policy_mismatch_banner(tmp_path):
    html = _html()
    js = "\n".join([_const(html, "LEDGER_KEY"), _fn(html, "deskSourceNote"), "let refusedFiles=[];",
                     _fn(html, "refusedNote"),
                     "let rows=[{deskMeta:{policy_version:'v1.1',as_of:'2026-10-29T16:00:00Z'}}];",
                     "const a=deskSourceNote();",
                     "rows=[{deskMeta:{policy_version:'v1.2',as_of:'2026-10-31T16:00:00Z'}}];",
                     "console.log(JSON.stringify([a,deskSourceNote()]));"])
    f = tmp_path / "banner.js"
    f.write_text(js)
    a, b = json.loads(subprocess.run(["node", str(f)], capture_output=True, text=True, check=True).stdout)
    assert "⚠ file policy v1.1 ≠ Cockpit v1.2" in a and "≠" not in b
