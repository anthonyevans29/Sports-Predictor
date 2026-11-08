"""THE PRIVACY PATTERNS, ONE DEFINITION (#813 / #817; ARCHITECT 2026-11-04 11:20 ET, addendum 250 item 2, the bulletins
lane #826): "THE GUARD LIVES IN THE WRITER, not only in CI: before any file is written the renderer runs the #817
patterns (tests/test_no_raw_kalshi_rows.py: UUID beside a ticker; the CSV header; the DOLLAR pattern, here over the
WHOLE text, not the receipts scope) plus a contract-count pattern (a digit run beside "contract"/"contracts", or
"contracts" beside a digit) over the Markdown and the card's text; a match REFUSES THE WRITE — nothing written, the
receipt carries `bulletin_refused` with the pattern's NAME and the file's intended path, never the line. The patterns
are imported from the test's module or a shared module the test imports: one definition."

This module is that shared module. tests/test_no_raw_kalshi_rows.py imports UUID, TICKER, CSV_RUN, SEQUENCE, DOLLAR,
is_row and is_header from here (its own rules, (i)-(iii), unchanged: the definitions moved, nothing else did), and the
bulletin renderer (deploy/hosting/bulletin.py) runs bulletin_offence over every file it would write.

The #817 patterns (addendum 236 item 2(c), addendum 238 item 1(c)):
  (i)   a raw Kalshi CSV row: a UUID-shaped token on the same line as a Kalshi ticker (is_row);
  (ii)  the CSV header row: the field names quantity_fp, entry_price_dollars, realized_pnl_with_fees_dollars in
        sequence in a CSV-shaped run of field names on one line (is_header);
  (iii) a dollar amount: a dollar sign (ASCII, fullwidth U+FF04, small U+FE69), optional blanks, an optional sign,
        optional blanks, an optional decimal point, then a digit (DOLLAR). A price in cents (56c, 56¢) never matches.

The bulletin's own patterns (addendum 250 item 2: "no `desk.order` text, no `desk.exec.contracts`, no
`fee_order_contracts`, no contract count of any kind, no dollar figure, no `desk_meta.unit.fraction` / `half_fraction`,
no pool figure, no account id"), each a named pattern over every line of the whole text:
  contract_count     the ruling's own: a digit run beside "contract"/"contracts" (12 contracts, 12-contract), or
                     "contract(s)" beside a digit (contracts 12, contracts: 12, contracts=12)
  order_text         the shape of desk.order.text (desk_policy.order_line: "BUY <YES|NO> <ticker> @ <limit> × <n>"):
                     the BUY YES / BUY NO lead, or a "×" before a digit (the count's own sign)
  unit_label         the unit's label (desk_policy.unit_basis_usd "1u = <figure>", the legacy "1u = <n> contracts"):
                     a units figure followed by "="
  fraction           desk_meta.unit.fraction / half_fraction printed: the word fraction (or half_fraction) beside a
                     number, or the field name half_fraction anywhere
  pool               a pool figure: the word pool beside a number
  field_name         a field name that only ever holds a count or a figure (fee_order_contracts, order_contracts,
                     unit_usd, half_fraction, contracts_basis), anywhere
  uuid               an account id's shape: ANY UUID-shaped token, ticker or none (a bulletin carries no UUID at all:
                     match ids are integers, run ids are stamps; the stricter reading, law 4)
The API key is the redaction's (sp_common.redact runs over every line before the guard), not a pattern here.
"""
from __future__ import annotations

import re

# ---- the #817 patterns (moved verbatim from tests/test_no_raw_kalshi_rows.py; the test imports them from here) ----

UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
# A Kalshi market ticker: today's KX prefix, or the ticker's own shape whatever its prefix (SERIES-YYMONDD..., the date
# segment Kalshi's game tickers carry), because prefixes change (src/adapters/kalshi.py: the KX* clearinghouse migration).
TICKER = re.compile(r"\bKX[A-Z0-9]+-[A-Z0-9]|\b[A-Z][A-Z0-9]{2,}-[0-9]{2}(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[0-9]{2}")
# (ii) the CSV header row: a run of field names joined by a CSV delimiter (comma, U+241F, tab, semicolon or pipe; a name
# may be double-quoted) holding the three names in that order. A prose sentence that names the fields (a ruling quoting
# them, `in backticks`, a list wrapped across lines) is not a header row and is not caught: the guard is for the row.
_FIELD = r'"?[A-Za-z_][A-Za-z0-9_]*"?'
CSV_RUN = re.compile(_FIELD + r"(?:[ \t]*[,␟\t;|][ \t]*" + _FIELD + r")+")
SEQUENCE = ("quantity_fp", "entry_price_dollars", "realized_pnl_with_fees_dollars")
# (iii) a dollar amount: a dollar sign ($, U+FF04 or U+FE69), optional blanks (space, tab, U+00A0), an optional sign
# (ASCII plus or minus, or U+2212), optional blanks, an optional decimal point, then a digit. A $ with no digit after it
# ($HOME, ${var}, a bare $) never matches.
DOLLAR = re.compile("[$＄﹩][ \t ]*[+\\-−]?[ \t ]*\\.?[0-9]")


def is_row(line: str) -> bool:
    """(i): a UUID-shaped token on the same line as a Kalshi ticker."""
    return bool(UUID.search(line) and TICKER.search(line))


def is_header(line: str) -> bool:
    """(ii): a CSV-shaped run of field names on the line holds the three header names in sequence."""
    for m in CSV_RUN.finditer(line):
        names = [f.strip().strip('"') for f in re.split(r"[,␟\t;|]", m.group(0))]
        at = [names.index(n) for n in SEQUENCE if n in names]
        if len(at) == len(SEQUENCE) and at == sorted(at):
            return True
    return False


# ---- the bulletin's own patterns (addendum 250 item 2), over the WHOLE text ----------------------------------------

CONTRACT_COUNT = re.compile(r"(?i)\d[\d,.]*\s*-?\s*contracts?\b|\bcontracts?\b\s*[:=#(×x]?\s*\d")
ORDER_TEXT = re.compile(r"(?i)\bBUY\s+(?:YES|NO)\b|×\s*\d")
UNIT_LABEL = re.compile(r"\b\d+(?:\.\d+)?\s*u\s*=")
FRACTION = re.compile(r"(?i)\b(?:half_)?fraction\b\W{0,3}[+\-]?\.?\d|\bhalf_fraction\b")
POOL = re.compile(r"(?i)\bpool\b\W{0,12}[+\-]?\.?\d")
FIELD_NAME = re.compile(r"\b(?:fee_order_contracts|order_contracts|unit_usd|half_fraction|contracts_basis)\b")

# (name, test) in the order a line is judged; the first that matches names the refusal.
BULLETIN_PATTERNS = (
    ("uuid_beside_ticker", is_row),
    ("csv_header", is_header),
    ("dollar", lambda line: bool(DOLLAR.search(line))),
    ("contract_count", lambda line: bool(CONTRACT_COUNT.search(line))),
    ("order_text", lambda line: bool(ORDER_TEXT.search(line))),
    ("unit_label", lambda line: bool(UNIT_LABEL.search(line))),
    ("fraction", lambda line: bool(FRACTION.search(line))),
    ("pool", lambda line: bool(POOL.search(line))),
    ("field_name", lambda line: bool(FIELD_NAME.search(line))),
    ("uuid", lambda line: bool(UUID.search(line))),
)
PATTERN_NAMES = tuple(n for n, _ in BULLETIN_PATTERNS)


def bulletin_offence(text: str) -> str | None:
    """The NAME of the first pattern any line of `text` matches, else None. Never the line (addendum 250 item 2: the
    receipt carries the pattern's name and the intended path, never the line)."""
    for line in str(text).split("\n"):
        for name, hit in BULLETIN_PATTERNS:
            if hit(line):
                return name
    return None
