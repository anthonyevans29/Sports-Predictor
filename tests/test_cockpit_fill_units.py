"""COCKPIT FILL UNITS (#487, ARCHITECT 2026-10-13; addendum 67 item 3, 2026-10-14): a fill's units are its entry cost
over the unit dollars read from the loaded files' order lines ("1u = $N", as desk_policy.file_unit_basis reads it);
FILL_UNIT_CONTRACTS=10 goes; the page holds no dollar figure. The page's own functions run under node on synthetic
fills; every unit below is a synthetic fixture.

DESK POLICY v1.2 (#740 / #753). POLICY_VERSION v1.2 (addendum 182 item 6). The fills' units, by the ruling
(ARCHITECT 2026-11-01 08:45 ET, addendum 197 item 1, verbatim): "C1 AND C4, ONE RULE — THE STAMP, NOT A DATE: a fill
converts by the unit stamped on the Desk row whose order produced it, and by nothing else. The Cockpit matches a fill
to the loaded files' order rows by TICKER (the order line names it); where several loaded files carry an order for
that ticker, the latest row whose page time is before the fill's opened time (the closing row stands over the slate
row, #632's rule); the matched row's own "1u = $X" label is the basis — a v1.1 row by its v1.1 label, a v1.2 row by
its day's label. A fill matched to NO loaded order row converts to nothing: contracts only, labelled "no loaded page
carries this order". So: no fill is ever read on the game's day or on a file's date; no v1.1 label reaches past its
own rows; the page needs no switch date and never infers one. A fill for a ticker the Desk never ordered (the
operator's off-book bets) is contracts only by the same rule — correct, those are not the Desk's."

The Ledger card's line (addendum 197 item 2, verbatim): "ITEM 3, the ledger card line "postseason rows are sized at
half until v1.2" (addendum 125 item 4): for a loaded file at policy v1.1 the line stands verbatim as pinned; for a
loaded file at policy v1.2 the card shows instead "policy v1.2: the unit is a fraction of the pool (addendum 179);
v1.1's postseason half-sizing no longer applies" — the verify pins both texts, each under its policy version, this
addendum quoted."
"""
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


def _const_block(html, name):
    """A top-level const whose value spans lines: from its line to the first line that ends with "};"."""
    i = html.index("const " + name + "=")
    return html[i:html.index("};\n", i) + 2]


V11_TEXT = "exports read no ledger summary; postseason rows are sized at half until v1.2"   # addendum 125 item 4, pinned
V12_TEXT = ("exports read no ledger summary; policy v1.2: the unit is a fraction of the pool (addendum 179); v1.1's "
            "postseason half-sizing no longer applies")                                     # addendum 197 item 2
UNMATCHED = "no loaded page carries this order"                                             # addendum 197 item 1


def test_the_constant_is_gone_and_no_dollar_figure_is_held():
    html = _html()
    assert "FILL_UNIT_CONTRACTS" not in html
    block = html[html.index("// B-TRACK FILLS EXPOSURE"):html.index("function realizedLines(")]
    assert not re.search(r"\$\s?\d", block.replace("1u = $N", "").replace("$${", "").replace("$$(", ""))
    head = " ".join(html[:html.index("<html")].split())
    assert "FILL UNITS (#487" in head and "BY THE STAMP, NOT A DATE" in head and "addendum 197 item 1" in head
    assert f'"{UNMATCHED}"' in head


def test_the_per_day_machinery_is_gone_and_the_page_reads_the_ticker_index():
    html = _html()
    for gone in ("fillUnitBasis", "fillUnitLabel", "fileDayUnit", "fillDayBases", "fillEtDate", "fillDayBasis",
                 "fillDayText", "exposureDaysText"):
        assert gone not in html, gone
    assert html.count("fillExposure(L,fillOrderIndex(rows,fileParlays))") == 2


# ---- fixtures ------------------------------------------------------------------------------------------------------

LAD, MIL = "KXMLBGAME-26OCT142000MILLAD-LAD", "KXMLBGAME-26OCT142000MILLAD-MIL"
BOS = "KXMLBGAME-26OCT151905NYYBOS-BOS"
KC = "KXNFLGAME-26OCT16BUFKC-KC"
OPEN = "2026-10-14T23:00:00Z"            # after both of 10-14's pages below


def _fill(ticker, side, qty, entry, opened=OPEN, fees=0.05):
    """A sport fill in importKalshiCSV's shape (family, teams, side code, opened)."""
    ev, code = ticker.rsplit("-", 1)
    mid = ev.split("-", 1)[1]
    teams = mid[11:] if mid[7:11].isdigit() else mid[7:]      # yyMONdd[hhmm]TEAMS
    fam = ev.split("-")[0][2:-4]
    return {"kind": "sport", "family": fam, "date": mid[:7], "teams": teams, "sideCode": code, "side": side,
            "qty": qty, "entry": entry, "fees": fees, "ticker": ticker, "opened": opened}


# one MLB game, YES on the home team: 30 contracts at 0.40 (cost 12.00) and 10 at 0.50 (5.00); a NO on the away team:
# 20 at 0.30 (6.00), paying on HOME too. HOME pays 60 contracts on 23.00 of entry cost.
FILLS = [_fill(LAD, "yes", 30, 0.40), _fill(LAD, "yes", 10, 0.50), _fill(MIL, "no", 20, 0.30)]
G1, G2, G3 = LAD.rsplit("-", 1)[0], BOS.rsplit("-", 1)[0], KC.rsplit("-", 1)[0]


def _row(ticker, unit, page="2026-10-14T16:00:00Z", version="v1.2"):
    """A loaded Desk row whose order names `ticker` with the unit label `unit`; `page` is its file's as_of."""
    return {"fileDesk": {"order": {"ticker": ticker, "side": "yes", "text": "BUY ...", "unit": unit}},
            "deskMeta": {"policy_version": version, "as_of": page}, "exportedAt": page}


JS_FNS = ("esc", "utcMs", "tickerRole", "unitLabelBasis", "fillOrderIndex", "fillOrderMatch", "fillExposure",
          "exposureOutcomeName", "exposureUnitsText", "exposureGameUnitText", "exposureHeadline", "exposureHTML")


def _node(tmp_path, body, name="fill_units.js"):
    html = _html()
    js = "\n".join([_const(html, "MONTHS"), _const(html, "THREE_WAY_FAMILIES"), _const(html, "BTRACK_CAP_U"),
                    _const(html, "FILL_UNMATCHED_LABEL"), _const_block(html, "FILL_KIND_TEXT")]
                   + [_fn(html, n) for n in JS_FNS] + [body])
    f = tmp_path / name
    f.write_text(js)
    return json.loads(subprocess.run(["node", str(f)], capture_output=True, text=True, check=True).stdout)


def _run(tmp_path, rows, fills=FILLS, parlays=None):
    """The page's exposure over `fills` with `rows` (and a desk_parlays file) loaded: each fill's match, every game,
    the summary, the headline and the block's HTML."""
    return _node(tmp_path, "\n".join([
        f"const rows={json.dumps(rows)}; let fileParlays={json.dumps(parlays)};",   # the page's globals
        f"const L={json.dumps({'fills': fills})};",
        "const idx=fillOrderIndex(rows,fileParlays), x=fillExposure(L,idx);",
        "const matches=L.fills.map(f=>fillOrderMatch(idx,f));",
        "const games=Object.fromEntries(x.games.map(g=>[g.key,g]));",
        "console.log(JSON.stringify({matches,games,summary:x.summary,head:exposureHeadline(x),html:exposureHTML(L)}));"]))


def _out(out, key, o="HOME"):
    return next(x for x in out["games"][key]["outcomes"] if x["outcome"] == o)


needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


# ---- addendum 197 item 1: the stamp, not a date ----------------------------------------------------------------------

@needs_node
def test_a_dollar_unit_reads_the_entry_cost_over_the_matched_rows_unit(tmp_path):
    out = _run(tmp_path, [_row(LAD, "1u = $20"), _row(MIL, "1u = $20")])
    assert [m["kind"] for m in out["matches"]] == ["matched"] * 3
    assert out["matches"][0] == {"basis": {"mode": "usd", "value": 20}, "kind": "matched", "label": "1u = $20",
                                 "page": "2026-10-14T16:00:00Z", "source": "row"}
    h = _out(out, G1)
    assert h["contracts"] == 60 and h["cost"] == pytest.approx(23.0) and h["unconverted"] == 0
    assert h["units"] == pytest.approx(23.0 / 20) and h["over"] is False      # 1.15u, under the 1.25u cap
    out = _run(tmp_path, [_row(LAD, "1u = $15"), _row(MIL, "1u = $15")])
    assert _out(out, G1)["units"] == pytest.approx(23.0 / 15) and _out(out, G1)["over"] is True
    assert out["summary"]["over"] == 1 and out["summary"]["withUnit"] == 1
    assert "60 ct ≈ 1.53u &gt; 1.25u" in out["html"]


@needs_node
def test_a_contracts_unit_reads_contracts_over_the_rows_count(tmp_path):
    lab = "1u = 10 contracts (SP_UNIT_USD unset)"
    out = _run(tmp_path, [_row(LAD, lab), _row(MIL, lab)])
    assert out["matches"][0]["basis"] == {"mode": "contracts", "value": 10}
    assert _out(out, G1)["units"] == pytest.approx(6.0) and _out(out, G1)["over"] is True


@needs_node
def test_a_fill_is_matched_by_ticker_to_the_closing_row_over_the_slate_row(tmp_path):
    """Two files carry the order for LAD: the slate (16:00Z, 1u = $20) and the closing (22:00Z, 1u = $25), both before
    the fill (23:00Z): the closing row's label converts it. A fill opened between them (18:00Z) takes the slate's."""
    rows = [_row(LAD, "1u = $20", "2026-10-14T16:00:00Z"), _row(LAD, "1u = $25", "2026-10-14T22:00:00Z")]
    late, mid = _fill(LAD, "yes", 25, 0.40), _fill(LAD, "yes", 25, 0.40, opened="2026-10-14T18:00:00Z")
    out = _run(tmp_path, rows, [late])
    assert out["matches"][0]["label"] == "1u = $25" and out["matches"][0]["page"] == "2026-10-14T22:00:00Z"
    assert _out(out, G1)["units"] == pytest.approx(10.0 / 25)
    out = _run(tmp_path, list(reversed(rows)), [mid])                 # load order never matters
    assert out["matches"][0]["label"] == "1u = $20" and out["matches"][0]["page"] == "2026-10-14T16:00:00Z"
    assert _out(out, G1)["units"] == pytest.approx(10.0 / 20)
    out = _run(tmp_path, rows, [late, mid])                           # each fill on its own row
    assert [m["label"] for m in out["matches"]] == ["1u = $25", "1u = $20"]
    assert _out(out, G1)["units"] == pytest.approx(10.0 / 25 + 10.0 / 20)
    assert out["games"][G1]["labels"] == ["1u = $20", "1u = $25"]
    # a page time with an offset reads as its instant: 17:30-05:00 is 22:30Z, before 23:00Z
    out = _run(tmp_path, rows + [_row(LAD, "1u = $30", "2026-10-14T17:30:00-05:00")], [late])
    assert out["matches"][0]["label"] == "1u = $30"


@needs_node
def test_a_later_row_that_wrote_no_order_never_stands_over_the_row_that_wrote_it(tmp_path):
    """desk_policy.order_line keeps the ticker on its no-order exits ("no ask to take", "limit outside (0, 1)", "under
    one contract": text null, a why). The slate row wrote the order at 1u = $15; the closing row, later but before the
    fill, names the ticker at 1u = $20 and wrote none: the fill converts by the slate's $15 (addendum 197 item 1: "the
    Desk row whose order produced it")."""
    slate = _row(KC, "1u = $15", "2026-10-01T14:00:00Z")
    closing = {"fileDesk": {"order": {"ticker": KC, "side": "YES", "text": None, "contracts": None,
                                      "why": "no ask to take (doctrine: TAKE at the ask, #87 v1.1) — no limit written",
                                      "unit": "1u = $20"}},
               "deskMeta": {"policy_version": "v1.2", "as_of": "2026-10-04T15:00:00Z"}, "exportedAt": "2026-10-04T15:00:00Z"}
    fill = _fill(KC, "yes", 20, 0.40, opened="2026-10-04T12:30:00-04:00")      # 16:30Z, after both pages
    for rows in ([slate, closing], [closing, slate]):
        out = _run(tmp_path, rows, [fill])
        assert out["matches"][0] == {"basis": {"mode": "usd", "value": 15}, "kind": "matched", "label": "1u = $15",
                                     "page": "2026-10-01T14:00:00Z", "source": "row"}
        assert _out(out, G3)["units"] == pytest.approx(8.0 / 15)
    out = _run(tmp_path, [closing], [fill])               # the no-order row alone carries no order: unmatched
    assert out["matches"][0]["kind"] == "unmatched" and out["matches"][0]["label"] == UNMATCHED
    parl = {"desk_meta": {"policy_version": "v1.2", "as_of": "2026-10-04T16:00:00Z"},
            "tickets": [{"legs": [{"order": {"ticker": KC, "text": None, "why": "no ask", "unit": "1u = $40"}}]}]}
    out = _run(tmp_path, [slate], [fill], parl)           # a parlay leg that wrote no order, the same
    assert out["matches"][0]["label"] == "1u = $15"


@needs_node
def test_a_v11_row_converts_only_its_own_fills(tmp_path):
    """A v1.1 file's row orders LAD at 1u = $15; a v1.2 file's rows order BOS and KC at 1u = $20. Each fill converts
    by its own row's label; the KC fill, whose ticker only the v1.2 file carries, never reads the v1.1 label, and a
    fill on MIL (neither file's order) is contracts only, never the v1.1 unit."""
    rows = [_row(LAD, "1u = $15", "2026-10-13T16:00:00Z", "v1.1"),
            _row(BOS, "1u = $20", "2026-10-15T16:00:00Z"), _row(KC, "1u = $20", "2026-10-15T16:00:00Z")]
    fills = [_fill(LAD, "yes", 30, 0.40), _fill(BOS, "yes", 10, 0.50, opened="2026-10-15T23:00:00Z"),
             _fill(KC, "yes", 20, 0.40, opened="2026-10-16T17:00:00Z"), _fill(MIL, "no", 20, 0.30)]
    out = _run(tmp_path, rows, fills)
    assert [m["label"] for m in out["matches"]] == ["1u = $15", "1u = $20", "1u = $20", UNMATCHED]
    assert _out(out, G2)["units"] == pytest.approx(5.0 / 20) and _out(out, G3)["units"] == pytest.approx(8.0 / 20)
    g1 = _out(out, G1)                     # LAD 30 (converted at 15) + NO on MIL 20 (contracts only)
    assert g1["units"] == pytest.approx(12.0 / 15) and g1["unconverted"] == 20 and g1["over"] is None
    # the v1.1 file alone: the KC fill is the off-book kind, never the v1.1 unit
    out = _run(tmp_path, rows[:1], fills[2:3])
    assert out["matches"][0] == {"basis": None, "kind": "unmatched", "label": UNMATCHED, "page": None}
    assert _out(out, G3)["units"] is None and _out(out, G3)["over"] is None


@needs_node
def test_an_unmatched_fill_is_contracts_only_labelled_exactly(tmp_path):
    """An off-book bet (a ticker no loaded row orders) and a load with no rows: contracts only, "no loaded page carries
    this order", no unit and no cap comparison."""
    for rows in ([], [_row(BOS, "1u = $20")], [{"fileDesk": {"order": {"why": "no order", "unit": "1u = $20"}}}],
                 [{"fileDesk": None}]):
        out = _run(tmp_path, rows)
        assert all(m["kind"] == "unmatched" and m["label"] == UNMATCHED for m in out["matches"])
        h = _out(out, G1)
        assert h["units"] is None and h["over"] is None and h["unconverted"] == 60
        assert out["summary"]["over"] is None and out["summary"]["contractsOnlyFills"] == 3
        assert out["summary"]["contractsOnlyByKind"] == {"unmatched": 3}
        assert ("per team-outcome (contracts only: no loaded order row converts these fills (reason in each game&#39;s "
                "cell))") in out["html"]
        assert "contracts only: no loaded page carries this order (3 fill(s))" in out["html"]
        assert "60 ct · if it lands" in out["html"] and "≈" not in out["html"].split("<tbody>")[1]
        assert ("units by the Desk row whose order produced each fill (addendum 197): 0 fill(s) matched, 3 fill(s) "
                "contracts only (no loaded page carries this order: 3)") in out["head"]
        assert "the 1.25u cap-equivalent not read (no team-outcome fully converted)" in out["head"]
    # the ticker matches trimmed and uppercased, exactly (never a prefix)
    out = _run(tmp_path, [_row("  " + LAD.lower() + " ", "1u = $20"), _row(LAD + "X", "1u = $5")], FILLS[:1])
    assert out["matches"][0]["label"] == "1u = $20"


@needs_node
def test_pages_after_the_fill_or_without_a_time_never_match(tmp_path):
    out = _run(tmp_path, [_row(LAD, "1u = $20", "2026-10-15T01:00:00Z")], FILLS[:1])
    assert out["matches"][0] == {"basis": None, "kind": "after_fill",
                                 "label": "no loaded page carries this order before the fill opened", "page": None}
    out = _run(tmp_path, [_row(LAD, "1u = $20", OPEN)], FILLS[:1])     # strictly before: the same instant is not
    assert out["matches"][0]["kind"] == "after_fill"
    out = _run(tmp_path, [_row(LAD, "1u = $20", None), _row(LAD, "1u = $20", "not a time")], FILLS[:1])
    assert out["matches"][0]["kind"] == "after_fill"
    assert out["matches"][0]["label"] == ("no loaded page carries this order before the fill opened (2 order row(s) "
                                          "with no readable page time)")
    out = _run(tmp_path, [_row(LAD, "1u = $20", None), _row(LAD, "1u = $25")], FILLS[:1])
    assert out["matches"][0]["label"] == "1u = $25"                    # the untimed row is never the match
    for opened in (None, "", "soon"):
        out = _run(tmp_path, [_row(LAD, "1u = $20")], [_fill(LAD, "yes", 30, 0.40, opened=opened)])
        assert out["matches"][0]["kind"] == "no_open_time" and out["matches"][0]["basis"] is None
        assert _out(out, G1)["units"] is None


@needs_node
def test_rows_of_the_latest_page_time_that_differ_are_a_conflict(tmp_path):
    rows = [_row(LAD, "1u = $25"), _row(LAD, "1u = $20"), _row(LAD, "1u = $9", "2026-10-14T12:00:00Z")]
    out = _run(tmp_path, rows, FILLS[:1])
    m = out["matches"][0]
    assert m["kind"] == "conflict" and m["basis"] is None
    assert m["label"] == "the loaded pages of 2026-10-14T16:00:00Z differ on this order's unit: 1u = $20 vs 1u = $25"
    assert _out(out, G1)["units"] is None and _out(out, G1)["over"] is None
    out = _run(tmp_path, [_row(LAD, "1u = $20"), _row(LAD, "1u = $20")], FILLS[:1])   # agreeing rows: that label
    assert out["matches"][0]["kind"] == "matched"


@needs_node
def test_an_unread_label_is_contracts_only_with_the_label_printed(tmp_path):
    for lab in ("unit unread — no order", "unit unread", None):
        out = _run(tmp_path, [_row(LAD, lab)], FILLS[:1])
        m = out["matches"][0]
        assert m["kind"] == "label_unread" and m["basis"] is None and m["label"] == (lab or "(no unit label)")
        assert _out(out, G1)["units"] is None and _out(out, G1)["over"] is None
        assert f"contracts only: {esc_(lab or '(no unit label)')} (1 fill(s))" in out["html"]
        assert "the order&#39;s unit label does not read: 1" in out["html"]


def esc_(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;")


@needs_node
def test_a_parlay_legs_order_is_matched_at_the_parlay_files_page_time(tmp_path):
    parl = {"kind": "desk_parlays_v1", "desk_meta": {"policy_version": "v1.2", "as_of": "2026-10-14T20:00:00Z"},
            "tickets": [{"legs": [{"order": {"ticker": LAD, "text": "BUY", "unit": "1u = $40"}},
                                  {"order": {"ticker": BOS, "text": "BUY", "unit": "1u = $40"}}]}]}
    out = _run(tmp_path, [_row(LAD, "1u = $20")], FILLS[:1], parl)
    assert out["matches"][0] == {"basis": {"mode": "usd", "value": 40}, "kind": "matched", "label": "1u = $40",
                                 "page": "2026-10-14T20:00:00Z", "source": "parlay leg"}
    parl["desk_meta"] = {}
    parl["exported_at"] = "2026-10-14T10:00:00Z"                      # its exported_at when no as_of: the row is later
    out = _run(tmp_path, [_row(LAD, "1u = $20")], FILLS[:1], parl)
    assert out["matches"][0]["label"] == "1u = $20" and out["matches"][0]["source"] == "row"


@needs_node
def test_a_mixed_outcome_prints_its_partial_units_and_reads_no_cap(tmp_path):
    """HOME: the LAD fills (40 contracts, 17.00) matched at 1u = $5 (3.40u, over the cap alone) and the NO on MIL
    (20 contracts) unmatched: the units print as partial, over is null (never a partial cap read)."""
    out = _run(tmp_path, [_row(LAD, "1u = $5")])
    h = _out(out, G1)
    assert h["units"] == pytest.approx(17.0 / 5) and h["unconverted"] == 20 and h["over"] is None
    s = out["summary"]
    assert s["matchedFills"] == 2 and s["contractsOnlyFills"] == 1 and s["partial"] == 1
    assert s["withUnit"] == 0 and s["over"] is None and s["labels"] == ["1u = $5"]
    assert "60 ct ≈ 3.40u (partial: 20 ct in contracts only, no cap read)" in out["html"]
    assert "&gt; 1.25u" not in out["html"]
    assert "1u = $5 (2 fill(s)) · contracts only: no loaded page carries this order (1 fill(s))" in out["html"]
    assert ("units by the Desk row whose order produced each fill (addendum 197): 2 fill(s) matched (1u = $5), 1 "
            "fill(s) contracts only (no loaded page carries this order: 1)") in out["head"]
    assert "1 team-outcome(s) partly converted (no cap read)" in out["head"]


@needs_node
def test_the_headline_and_html_texts(tmp_path):
    rows = [_row(LAD, "1u = $20"), _row(MIL, "1u = $20"), _row(BOS, "1u = $4", "2026-10-15T16:00:00Z")]
    fills = FILLS + [_fill(BOS, "yes", 10, 0.50, opened="2026-10-15T23:00:00Z"),
                     _fill(KC, "yes", 20, 0.40, opened="2026-10-16T17:00:00Z")]
    out = _run(tmp_path, rows, fills)
    s = out["summary"]
    assert s["matchedFills"] == 4 and s["contractsOnlyFills"] == 1 and s["withUnit"] == 2 and s["over"] == 0
    assert _out(out, G2)["units"] == pytest.approx(5.0 / 4) and _out(out, G2)["over"] is False   # at the cap
    assert ("units by the Desk row whose order produced each fill (addendum 197): 4 fill(s) matched (1u = $20; "
            "1u = $4), 1 fill(s) contracts only (no loaded page carries this order: 1)") in out["head"]
    assert "over the 1.25u cap-equivalent 0 (of 2 team-outcome(s) fully converted)" in out["head"]
    assert ("per team-outcome (contracts ≈ units by the Desk row whose order produced each fill, beside the 1.25u "
            "cap; contracts only where no loaded order row converts the fill (reason in each game&#39;s cell))") in out["html"]
    assert "the closing row stands over the slate row" in out["html"] and "never a date" in out["html"]
    assert "20 ct · if it lands" in out["html"]
    for gone in ("ET day", "for 2026-10-16", "the file&#39;s"):
        assert gone not in out["html"] and gone not in out["head"]


# ---- addendum 197 item 2: the Ledger card's line by the loaded files' policy versions --------------------------------

@needs_node
def test_the_ledger_card_line_reads_each_policy_versions_text(tmp_path):
    html = _html()
    js = "\n".join([_const(html, "LEDGER_KEY"), _const_block(html, "LEDGER_LINE_TEXT"), _fn(html, "ledgerExportsText"),
                    "const v=p=>({policy_version:p,as_of:'2026-10-31T16:00:00Z'});",
                    "console.log(JSON.stringify([ledgerExportsText([v('v1.1')]),ledgerExportsText([v('v1.2')]),"
                    "ledgerExportsText([v('v1.2'),v('v1.1'),v('v1.2')]),ledgerExportsText([]),"
                    "ledgerExportsText([v('v9.9')])]));"])
    f = tmp_path / "card.js"
    f.write_text(js)
    a, b, both, none, other = json.loads(subprocess.run(["node", str(f)], capture_output=True, text=True,
                                                        check=True).stdout)
    assert a == V11_TEXT                    # policy v1.1: the line stands verbatim as pinned (addendum 125 item 4)
    assert b == V12_TEXT                    # policy v1.2: addendum 197 item 2's text
    assert both == V11_TEXT + " · " + V12_TEXT and none == V12_TEXT and other == V12_TEXT


@needs_node
def test_the_rendered_card_line_reads_the_rows_and_the_parlay_files_versions(tmp_path):
    """renderLedgerExportsLine, as the page runs it after loadDocs: a v1.1 predictions file with a v1.2 desk_parlays
    file (which lands in fileParlays, never fileMetas) shows both texts, v1.1's first; rows' deskMeta alone at v1.1
    shows the v1.1 text; nothing loaded shows the Cockpit's own v1.2 text."""
    html = _html()
    js = "\n".join([_const(html, "LEDGER_KEY"), _const_block(html, "LEDGER_LINE_TEXT"), _fn(html, "ledgerExportsText"),
                    _fn(html, "renderLedgerExportsLine"),
                    "const el={textContent:''}, $=id=>id==='ledgerExportsLine'?el:null;",
                    "const v=p=>({policy_version:p,as_of:'2026-10-31T16:00:00Z'});",
                    "let rows, fileParlays, fileMetas; const out=[];",
                    "const run=(r,p,m)=>{rows=r; fileParlays=p; fileMetas=m; renderLedgerExportsLine(); "
                    "out.push(el.textContent);};",
                    "run([{deskMeta:v('v1.1')}],{kind:'desk_parlays_v1',desk_meta:v('v1.2'),tickets:[]},[v('v1.1')]);",
                    "run([{deskMeta:v('v1.1')},{deskMeta:null}],null,[]);",
                    "run([],{tickets:[]},[]);",
                    "console.log(JSON.stringify(out));"])
    f = tmp_path / "card_render.js"
    f.write_text(js)
    mixed, rows_only, none = json.loads(subprocess.run(["node", str(f)], capture_output=True, text=True,
                                                       check=True).stdout)
    assert mixed == V11_TEXT + " · " + V12_TEXT
    assert rows_only == V11_TEXT and none == V12_TEXT


def test_the_policy_heading_reads_the_stamp_not_a_day():
    """The Desk view's Policy v1.2 heading names addendum 197's rule, never round 1's per-ET-day reading."""
    html = _html()
    head = re.search(r"<h2[^>]*>Policy v1\.2 <span class=\"note\">([^<]*)</span>", html)
    assert head and "addendum 197" in head.group(1) and "ET day" not in head.group(1)
    assert "fills read per ET day" not in html


def test_the_card_element_starts_on_the_cockpits_own_policy_and_rerenders_on_load():
    html = _html()
    m = re.search(r'<div class="note" id="ledgerExportsLine"[^>]*title="([^"]*)">([^<]*)</div>', html)
    assert m and m.group(2) == V12_TEXT.replace("'", "'") and "addendum 197 item 2" in m.group(1)
    body = html[html.index("async function loadDocs("):html.index("$(\"predFile\")")]
    assert "fileMetas=[];" in body and "if(doc.desk_meta) fileMetas.push(doc.desk_meta);" in body
    assert body.count("renderLedgerExportsLine();") == 2


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


