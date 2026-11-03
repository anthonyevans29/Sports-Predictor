"""#813 (ARCHITECT 2026-11-03, addendum 236 item 2(c)): no raw Kalshi CSV row in any tracked .md, .txt or .json file
outside tests/fixtures/. A row is caught by (i) a UUID-shaped token on the same line as a Kalshi ticker, or (ii) the CSV
header row's field names in sequence (quantity_fp, entry_price_dollars, realized_pnl_with_fees_dollars) in a CSV-shaped
run of field names on one line. Offenders print as file:line only; the line itself is never printed. The two fixture
files under tests/fixtures/kalshi_history/ hold UUID-shaped tokens at markets[].custom_strike.football_team (strike
entity ids, read by pattern for #813) and are outside the scan; src/adapters/kalshi.py's one (TIE_STRIKE_UUID) is a
strike id in a .py file, outside the scan's suffixes."""
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SUFFIXES = (".md", ".txt", ".json")
EXCLUDED = ("tests/fixtures/",)
UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
# A Kalshi market ticker: today's KX prefix, or the ticker's own shape whatever its prefix (SERIES-YYMONDD..., the date
# segment Kalshi's game tickers carry), because prefixes change (src/adapters/kalshi.py: the KX* clearinghouse migration).
TICKER = re.compile(r"\bKX[A-Z0-9]+-[A-Z0-9]|\b[A-Z][A-Z0-9]{2,}-[0-9]{2}(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[0-9]{2}")
# (ii) the CSV header row: a run of field names joined by a CSV delimiter (comma, U+241F, tab, semicolon or pipe; a name
# may be double-quoted) holding the three names in that order. A prose sentence that names the fields (a ruling quoting
# them, `in backticks`, a list wrapped across lines) is not a header row and is not caught: the guard is for the row.
_FIELD = r'"?[A-Za-z_][A-Za-z0-9_]*"?'
CSV_RUN = re.compile(_FIELD + r"(?:[ \t]*[,\u241f\t;|][ \t]*" + _FIELD + r")+")
SEQUENCE = ("quantity_fp", "entry_price_dollars", "realized_pnl_with_fees_dollars")


def _is_row(line: str) -> bool:
    return bool(UUID.search(line) and TICKER.search(line))


def _is_header(line: str) -> bool:
    """A CSV-shaped run of field names on the line holds the three header names in sequence."""
    for m in CSV_RUN.finditer(line):
        names = [f.strip().strip('"') for f in re.split(r"[,\u241f\t;|]", m.group(0))]
        at = [names.index(n) for n in SEQUENCE if n in names]
        if len(at) == len(SEQUENCE) and at == sorted(at):
            return True
    return False


def offenders(text: str, name: str) -> list[str]:
    hits = {i for i, line in enumerate(text.split("\n"), 1) if _is_row(line) or _is_header(line)}
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
    assert not found, "raw Kalshi CSV row or header (#813) at:\n" + "\n".join(found)


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
