"""#813 (ARCHITECT 2026-11-03, addendum 236 item 2(c)): no raw Kalshi CSV row in any tracked .md, .txt or .json file
outside tests/fixtures/. A row is caught by (i) a UUID-shaped token on the same line as a Kalshi ticker, or (ii) the CSV
header row's field names in sequence (quantity_fp, entry_price_dollars, realized_pnl_with_fees_dollars) in a CSV-shaped
run of field names on one line. Offenders print as file:line only; the line itself is never printed. The two fixture
files under tests/fixtures/kalshi_history/ hold UUID-shaped tokens at markets[].custom_strike.football_team (strike
entity ids, read by pattern for #813) and are outside the scan; src/adapters/kalshi.py's one (TIE_STRIKE_UUID) is a
strike id in a .py file, outside the scan's suffixes.

(iii) (ARCHITECT 2026-11-03, addendum 238 item 1(c)): a dollar amount (a dollar sign, ASCII or the fullwidth U+FF04 or
small U+FE69 form, then optional blanks, an optional sign, optional blanks, an optional decimal point and a digit) in a
tracked .md, .txt or .json file under docs/receipts/ or docs/ledger/ only. A price in cents
(56c, 56¢) is not a dollar amount and never matches; unit fractions (0.5u) and percentages carry no $ sign. The
decision and change records' historical lines are outside this rule (read once by pattern for the PR body)."""
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SUFFIXES = (".md", ".txt", ".json")
EXCLUDED = ("tests/fixtures/",)
# The patterns' ONE definition (ARCHITECT 2026-11-04, addendum 250 item 2: "The patterns are imported from the test's
# module or a shared module the test imports: one definition"): src/privacy_patterns.py, which the bulletin renderer's
# writer-side guard imports too. Moved there verbatim; the rules here are unchanged.
from src.privacy_patterns import CSV_RUN, DOLLAR, SEQUENCE, TICKER, UUID  # noqa: E402,F401
from src.privacy_patterns import is_header as _is_header  # noqa: E402
from src.privacy_patterns import is_row as _is_row  # noqa: E402

DOLLAR_SCOPE = ("docs/receipts/", "docs/ledger/")


def offenders(text: str, name: str) -> list[str]:
    dollars = name.startswith(DOLLAR_SCOPE)
    hits = {i for i, line in enumerate(text.split("\n"), 1)
            if _is_row(line) or _is_header(line) or (dollars and DOLLAR.search(line))}
    return [f"{name}:{i}" for i in sorted(hits)]


def _tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    names = [n for n in out.decode().split("\0") if n]
    return [n for n in names if n.endswith(SUFFIXES) and not n.startswith(EXCLUDED)]


def test_no_tracked_text_file_holds_a_raw_kalshi_row_or_its_header():
    files = _tracked()
    assert files, "git ls-files listed no .md/.txt/.json file: the guard would pass vacuously"
    found = []
    for name in files:
        path = ROOT / name
        if not path.is_file():
            continue
        found += offenders(path.read_text(encoding="utf-8", errors="replace"), name)
    # file:line only, never the line: the line is the thing that must not travel.
    assert not found, "raw Kalshi CSV row, header or receipt dollar amount (#813) at:\n" + "\n".join(found)


# Synthetic shapes only: an all-zero UUID, an invented ticker, no figure. Built at run time so no line here is a row.
_Z = "-".join("0" * n for n in (8, 4, 4, 4, 12))
_T = "KX" + "TEST-26JAN01AAABBB-AAA"


@pytest.mark.parametrize("line,hit", [
    (f"{_Z}␟trade␟{_T}␟yes", True),
    (f"{_Z},trade,{_T},yes", True),
    (f"{_T} yes · 2026-10-04T12:00:00Z", False),
    (f"id {_Z} with no ticker", False),
    ("a KXNFLGAME series name with no market suffix and " + _Z, False),
    (f"{_Z}␟trade␟" + "NFL" + "GAME-26OCT10AAABBB-AAA␟no", True),        # a pre-KX prefix: the ticker's shape
    (f"{_Z}," + "ZZQGAME" + "-27JAN03CCCDDD-CCC,yes", True),             # any future prefix
    (f"{_Z} next to UTF-8 and ISO-2026", False),                         # no ticker shape
])
def test_a_uuid_beside_a_ticker_is_a_row(line, hit):
    assert bool(offenders(line, "f")) is hit


def test_the_header_row_is_caught_in_any_csv_delimiter_and_a_prose_naming_is_not():
    q, e, r = "quantity" + "_fp", "entry_price" + "_dollars", "realized_pnl_with_fees" + "_dollars"
    assert offenders(f"a,{q},b,{e},c,{r}", "f") == ["f:1"]
    assert offenders(f"x\nsubtrader_id\u241ftype\u241f{q}\u241f{e}\u241f{r}", "f") == ["f:2"]
    assert offenders(f'"a"\t"{q}"\t"{e}"\t"{r}"', "f") == ["f:1"]
    assert offenders(f"| {q} | {e} | {r} |", "f") == ["f:1"]
    assert offenders(f"header: a, {q}; {e}; {r}, z", "f") == ["f:1"]
    assert offenders(f"{r},{e},{q}", "f") == []                      # out of sequence
    assert offenders(f"only {q},{e}", "f") == []                      # two of three
    # a ruling quoting the names in prose (addendum 236 item 2(c)'s own shape) and a list wrapped across lines
    assert offenders(f"the field names in sequence (`{q}`, `{e}`, `{r}`), with", "f") == []
    assert offenders(f"names {q}, {e},\n{r} in that order", "f") == []


def test_an_offender_prints_as_file_and_line_only():
    line = f"{_Z}␟{_T}"
    got = offenders(f"ok\n{line}", "docs/x.md")
    assert got == ["docs/x.md:2"] and _Z not in got[0] and _T not in got[0]


# (iii) synthetic figures, built at run time: a $ sign joined to an invented amount.
_S = "$"


@pytest.mark.parametrize("line,hit", [
    (f"fees {_S}9.99 net", True),
    (f"P&L {_S}+1.20", True),
    (f"P&L {_S}-3", True),
    (f"P&L {_S}\u22123.50", True),                                      # U+2212 minus
    (f"loss -{_S}12 with fees", True),                                  # the sign before the $
    (f"(~{_S}5/mo)", True),
    ("bid 56c ask 57c, 56\u00a2 by the cent sign", False),              # prices in cents are not dollar amounts
    ("0.5u and 1u, 3.2% and fee(0.07\u00b7M)", False),                  # unit fractions, percentages, formulas
    (f"a bare {_S} sign, {_S}HOME, {_S}{{var}}, {_S} ., {_S}-x", False), # no digit after the $
    (f"fees {_S} 5", True),                                             # a blank after the $
    (f"fees {_S}\u00a05", True),                                        # a no-break space after the $
    (f"cost {_S}.50", True),                                            # no leading zero
    (f"fee {_S}.50", True),
    (f"P&L {_S}- 3", True),                                             # a blank after the sign
    ("fees \uff045 by the fullwidth sign", True),                       # U+FF04
    ("fees \ufe695 by the small sign", True),                           # U+FE69
    ("[figure redacted by #813]", False),
])
def test_a_dollar_amount_is_caught_in_receipts_and_ledger_entries(line, hit):
    assert bool(offenders(line, "docs/receipts/x.md")) is hit
    assert bool(offenders(line, "docs/ledger/" + "e/x.md")) is hit


@pytest.mark.parametrize("name", ["BACKLOG.md", "CHANGELOG.md", "docs/LEDGER.md", "docs/x.md", "README.md"])
def test_a_dollar_amount_outside_the_two_directories_is_not_this_rule(name):
    assert offenders(f"hosting {_S}12/mo", name) == []


def test_a_dollar_offender_prints_as_file_and_line_only():
    amount = f"{_S}+4.56"
    got = offenders(f"ok\nnet {amount}", "docs/receipts/x.md")
    assert got == ["docs/receipts/x.md:2"] and amount not in got[0]
