"""#431 R15's receipt (scripts/cockpit_closing_before_after.py), its printing rules without a browser: the REALIZED block
(addendum 146 item 1; APPROVED by addendum 148 item 1(j)) and the Closing CLV line (#431 R17; addendum 148 item 1(i):
"The two-week read stays the one in addendum 146 item 1(c), from my reading of the operator's fills, never in the
repo"; withholding the line is PROPOSED under 1(i), against 1(j)'s "everything else R15 names prints in full",
escalated on #632) each print as one line naming it by default and are still compared for the DIFF without being
printed. --with-closing-clv prints the Closing CLV line whole and keeps REALIZED withheld; --with-realized prints both
(the operator's own console). The line is the page's own closingClvLine(L), withheld by equality, and both fail
closed. main() runs here without a browser (Playwright faked in sys.modules); the Playwright run itself is the
operator's (R15)."""
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("cockpit_closing_before_after",
                                               ROOT / "scripts" / "cockpit_closing_before_after.py")
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)

HEAD = "Closing CLV (close − entry; + = beat the close)"
CLV = (HEAD + " (addendum 146 item 1(iv) R17, #431): 2 position(s), 2 fill(s) · sum -4.0c · mean -2.0c per position ·"
       " graded 0 · open 2 — read against the closing page 1, the slate page 1, outside any page 0 · R16: 2 fill(s) above"
       " their page's limit (max +2.0c) · 0 over the ordered size · 1 partial")
REALIZED = ["REALIZED (real money, fees included)", "  staked $57.00 · fees $0.84 · net -$3.10"]
FIGURES = ("-4.0c", "-2.0c", "+2.0c", "$57.00")                 # the fill figures the default output never prints
AUTO = object()


def _side(pnl_lines, realized=REALIZED, closing=AUTO):
    """One side's page words as run_side returns them, its pnlBlock the given lines. `closing` is what SNAP reads from
    the page's closingClvLine(L): by default the pnlBlock line with its head, None when there is none (main's page has
    no closingClvLine); None for a page without the function, a string for the page's own line."""
    if closing is AUTO:
        closing = next((x for x in pnl_lines if x.startswith(HEAD)), None)
    return {"pnl": "\n".join(pnl_lines), "realized": realized, "closing": closing, "notes": ["import: Imported 6 call(s)"],
            "calls0": 6, "calls": 6, "ids0": ["a"], "ids": ["a"], "fills": 2, "marked": 0, "summary": {"counts": {}},
            "bets": {"settled": 0, "real": 0, "shadow": 0, "byEngine": {}, "byType": {}}, "audit": {}, "ne": None,
            "neLine": None, "list": None, "errors": []}


AFTER = ["P&L", *REALIZED, "", "EXECUTED-POSITION CLV (P0-3 #208)", "  entry-price CLV (close−fill) n 0", "", CLV, "",
         "Quarantine counterfactual (shadow, NOT staked): n 0"]
BEFORE = [x for x in AFTER if not x.startswith(HEAD)]
R_HID = ["P&L", R.REALIZED_HIDDEN.format(n=2)]                                     # the REALIZED block, withheld
TAIL = ["", "EXECUTED-POSITION CLV (P0-3 #208)", "  entry-price CLV (close−fill) n 0", ""]
QUAR = ["", "Quarantine counterfactual (shadow, NOT staked): n 0"]


def test_the_head_is_the_pages_own_snap_reads_the_pages_line_and_the_withheld_lines_say_why():
    page = (ROOT / "tools" / "cockpit.html").read_text(encoding="utf-8")
    assert R.CLOSING_HEAD == HEAD and f"return `{HEAD} (addendum 146 item 1(iv) R17, #431): " in page
    assert "function closingClvLine(L){" in page and "    closingClvLine(L), \"\",\n" in page   # pnlBlock's own line
    assert 'closing:typeof closingClvLine==="function"?closingClvLine(L):null' in R.SNAP     # read as realizedLines is
    assert R.CLOSING_HIDDEN == ("Closing CLV: 1 line, not printed: fill-derived (withholding proposed under addendum 148"
                                " item 1(i), escalated, #632); --with-closing-clv prints it whole")
    assert R.CLOSING_UNFOUND == ("pnlBlock not printed: its Closing CLV line could not be told apart (fill-derived:"
                                 " withheld unless --with-closing-clv, proposed, #632)")
    assert R.CLOSING_NOTE == ("its withholding is PROPOSED under addendum 148 item 1(i) and runs against 1(j)'s"
                              " \"everything else R15 names prints in full\": escalated (#632); if the architect rules"
                              " it prints, the PR-body run adds --with-closing-clv")


def test_the_closing_clv_line_prints_as_one_line_naming_it_and_whole_only_with_a_flag():
    s = _side(AFTER)
    out = R.pnl_lines(s)
    assert out == R_HID + TAIL + [R.CLOSING_HIDDEN] + QUAR
    text = "\n".join(out)
    assert HEAD not in text and not any(x in text for x in FIGURES)                          # no fill figure
    assert R.pnl_lines(s, False, True) == R_HID + TAIL + [CLV] + QUAR       # --with-closing-clv: REALIZED still withheld
    assert R.pnl_lines(s, True) == R.pnl_lines(s, True, False) == R.pnl_lines(s, True, True) == AFTER   # --with-realized
    assert R.sections(s)["pnlBlock"] == out and R.sections(s, False, True)["pnlBlock"] == R_HID + TAIL + [CLV] + QUAR
    assert R.sections(s, True)["pnlBlock"] == R.sections(s, True, True)["pnlBlock"] == AFTER
    main_page = R.pnl_lines(_side(BEFORE))                                          # main's page: no closingClvLine
    assert main_page == R_HID + TAIL + QUAR and R.pnl_lines(_side(BEFORE), False, True) == main_page


def test_the_line_is_withheld_by_equality_with_the_pages_own_and_fails_closed():
    """By equality with the page's closingClvLine(L), never by its words: a page whose line is worded otherwise is still
    withheld. A page that defines closingClvLine but whose line is not in pnlBlock prints no pnlBlock line (as REALIZED's
    fallback does), unless the line is not withheld (--with-closing-clv, --with-realized); so does a page without
    closingClvLine whose pnlBlock still carries a line with the head."""
    other = "Closing CLV, the close against the fills: sum -4.0c over 2 position(s)"
    s = _side([other if x == CLV else x for x in AFTER], closing=other)
    assert R.pnl_lines(s) == R_HID + TAIL + [R.CLOSING_HIDDEN] + QUAR
    absent = _side([other if x == CLV else x for x in AFTER], closing=CLV)       # the page's line is not in pnlBlock
    assert R.pnl_lines(absent) == R.sections(absent)["pnlBlock"] == [R.CLOSING_UNFOUND]
    assert R.pnl_lines(absent, False, True) == R_HID + TAIL + [other] + QUAR
    assert R.pnl_lines(absent, True) == [other if x == CLV else x for x in AFTER]
    no_fn = _side(AFTER, closing=None)                                  # no closingClvLine, a line with the head
    assert R.pnl_lines(no_fn) == [R.CLOSING_UNFOUND] and R.pnl_lines(no_fn, False, True) == R_HID + TAIL + [CLV] + QUAR


@pytest.mark.parametrize("before, after, closing", [
    (BEFORE, AFTER, "a line moved"),        # main has no line, the PR's page does
    (AFTER, AFTER, "no line moved"),
    (AFTER, [x.replace("-4.0c", "-3.0c") if x.startswith(HEAD) else x for x in AFTER], "a line moved"),
])
def test_the_diff_compares_the_withheld_line_without_printing_it(before, after, closing):
    got = {"BEFORE": _side(before), "AFTER": _side(after)}
    hint = "a line moved (read it with --with-closing-clv)" if closing == "a line moved" else closing
    assert R.withheld_diff(got) == ["[REALIZED, not printed] no line moved", "[Closing CLV, not printed] " + hint]
    assert R.withheld_diff(got, False, True) == ["[REALIZED, not printed] no line moved"]       # --with-closing-clv
    assert R.withheld_diff(got, True) == R.withheld_diff(got, True, True) == []                 # --with-realized
    got["AFTER"]["realized"] = [REALIZED[0], "  staked $58.00"]
    assert R.withheld_diff(got)[0] == R.withheld_diff(got, False, True)[0] == (
        "[REALIZED, not printed] a line moved (read it with --with-realized on the operator's own console)")
    moved = [x for side in ("BEFORE", "AFTER") for x in R.sections(got[side])["pnlBlock"]]
    assert not any(x.startswith(HEAD) for x in moved)                       # the DIFF prints the sections, never the line


def test_the_help_and_the_docstring_name_both_flags_and_the_escalation(capsys, monkeypatch):
    monkeypatch.setenv("COLUMNS", "1000")                                   # argparse wraps no help line
    with pytest.raises(SystemExit) as e:
        R.main(["--help"])
    assert e.value.code == 0
    help_text = " ".join(capsys.readouterr().out.split())
    assert ("--with-closing-clv print pnlBlock's Closing CLV line (#431 R17, fill-derived) whole, REALIZED still"
            " withheld. Its default withholding is PROPOSED under addendum 148 item 1(i) and runs against 1(j)'s"
            " \"everything else R15 names prints in full\": escalated (#632); if the architect rules it prints, the"
            " PR-body run adds this flag") in help_text
    assert ("--with-realized print pnlBlock's REALIZED (real-money) lines whole, and its Closing CLV line (implies"
            " --with-closing-clv): the operator's own console only, never the PR body (addendum 146 item 1; addendum"
            " 148 item 1(j))") in help_text
    doc = " ".join(R.__doc__.split())
    assert "The Closing CLV line (#431 R17" in doc and "the page's own closingClvLine(L)" in doc
    assert ("That withholding is PROPOSED under addendum 148 item 1(i) and runs against 1(j)'s \"everything else R15"
            " names prints in full\": escalated to the architect (#632). If the architect rules it prints, the PR-body"
            " run adds --with-closing-clv, which prints the line whole and keeps REALIZED withheld.") in doc
    assert "--with-realized prints both whole (it implies --with-closing-clv)" in doc
    assert "the PR body's run adds --with-closing-clv (the line whole, REALIZED still withheld)" in doc


# ------------------------------------------------------------ main() without a browser: the wiring of the flags --

@pytest.fixture
def run(monkeypatch, tmp_path, capsys):
    """main() end to end with Playwright faked in sys.modules (CI does not install it): page_at, working_page and
    run_side return the sides above (AFTER by default the PR's page, `after` another), git is never run."""
    class Err(Exception):
        pass

    class PW:
        chromium = types.SimpleNamespace(launch=lambda **k: types.SimpleNamespace(close=lambda: None))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    mod = types.ModuleType("playwright.sync_api")
    mod.Error, mod.sync_playwright = Err, PW
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", mod)
    monkeypatch.setattr(R, "page_at", lambda ref: ("<script>BEFORE", f"page at {ref}"))
    monkeypatch.setattr(R, "working_page", lambda: ("<script>AFTER", "the working tree's page"))
    led, cl = tmp_path / "led.json", tmp_path / "closing_NFL_x.json"
    led.write_text(json.dumps({"calls": [], "meta": {}}), encoding="utf-8")
    cl.write_text(json.dumps({"closing": {"family": "NFL", "start": "2026-10-19T17:00:00Z"}}), encoding="utf-8")

    def go(*extra, after=None):
        sides = {"BEFORE": _side(BEFORE), "AFTER": after or _side(AFTER)}
        monkeypatch.setattr(R, "run_side", lambda b, html, *a: sides["BEFORE" if "BEFORE" in html else "AFTER"])
        rc = R.main(["--ledger", str(led), "--closings", str(cl), *extra])
        return rc, capsys.readouterr().out
    return go


R_HEAD_HID = ("REALIZED (real-money) lines: each block printed as one line naming its line count, never whole"
              " (addendum 146 item 1; APPROVED, addendum 148 item 1(j))")


def test_main_by_default_withholds_both_and_names_the_closing_clv_lines_move_in_the_diff(run):
    rc, out = run()
    assert rc == 0 and HEAD not in out and not any(x in out for x in FIGURES)
    assert out.count(R.CLOSING_HIDDEN) == 2              # AFTER's pnlBlock and the DIFF's "+" (main's page has no line)
    assert out.count(R.REALIZED_HIDDEN.format(n=2)) == 2                    # both pnlBlocks; the DIFF: no line moved
    assert "\n[REALIZED, not printed] no line moved\n" in out
    assert "\n[Closing CLV, not printed] a line moved (read it with --with-closing-clv)\n" in out
    assert f"\n{R_HEAD_HID}\nClosing CLV line: printed as one line naming it, never whole; {R.CLOSING_NOTE}\n" in out


def test_main_with_closing_clv_prints_the_line_whole_and_keeps_realized_withheld(run):
    rc, out = run("--with-closing-clv")
    assert rc == 0 and out.count(CLV) == 2 and R.CLOSING_HIDDEN not in out   # AFTER's pnlBlock and the DIFF's "+"
    assert "$57.00" not in out and out.count(R.REALIZED_HIDDEN.format(n=2)) == 2
    assert "\n[REALIZED, not printed] no line moved\n" in out and "[Closing CLV, not printed]" not in out
    assert f"\n{R_HEAD_HID}\nClosing CLV line: printed whole (--with-closing-clv); {R.CLOSING_NOTE}\n" in out


def test_main_with_realized_prints_both_whole_and_no_withheld_diff(run):
    rc, out = run("--with-realized")
    assert rc == 0 and CLV in out and "  staked $57.00 · fees $0.84 · net -$3.10" in out
    assert R.CLOSING_HIDDEN not in out and "not printed" not in out
    assert ("\nREALIZED (real-money) lines: printed whole (--with-realized: the operator's own console only)\n"
            f"Closing CLV line: printed whole (--with-realized); {R.CLOSING_NOTE}\n") in out


def test_main_fails_closed_when_the_pages_line_is_not_in_pnlblock(run):
    """The page defines closingClvLine, but pnlBlock carries another line (worded otherwise, a figure in it): the AFTER
    pnlBlock is one line saying so, no figure; --with-closing-clv prints it, REALIZED still withheld."""
    other = "Closing CLV, the close against the fills: sum -4.0c over 2 position(s)"
    after = _side([other if x == CLV else x for x in AFTER], closing=CLV)
    rc, out = run(after=after)
    assert rc == 0 and "=== AFTER ===\n" in out and f"-- pnlBlock\n  {R.CLOSING_UNFOUND}\n-- ledgerSummary" in out
    assert not any(x in out for x in FIGURES) and other not in out and HEAD not in out
    assert "\n[Closing CLV, not printed] a line moved (read it with --with-closing-clv)\n" in out
    rc, out = run("--with-closing-clv", after=after)
    assert rc == 0 and other in out and R.CLOSING_UNFOUND not in out and "$57.00" not in out
