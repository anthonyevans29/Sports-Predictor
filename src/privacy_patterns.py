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
  usd_word           a dollar figure without the sign before it: a number beside USD / dollar(s), USD before a number,
                     or a sign after a number (12 USD, USD 12, 12 dollars, 12$)
  contract_count     the ruling's own: a digit run beside "contract"/"contracts" (12 contracts, 12-contract), or
                     "contract(s)" beside a digit (contracts 12, contracts: 12, contracts=12), or with a "count" label
                     between (contract count: 5, contract count = 12; addendum 299 item 1), the name also with a
                     prefix or suffix joined by "_" and in the export's own JSON / dict shape ("contracts": 5)
  order_text         the shape of desk.order.text (desk_policy.order_line: "BUY <YES|NO> <ticker> @ <limit> × <n>"):
                     the BUY YES / BUY NO lead, a "×" before a digit (the count's own sign), or an ASCII x count
                     after a price or before "at"/"@" ("@ 0.45 x 3", "x 3 at 45c"), or a lower-case "x3" alone
  unit_label         the unit's label (desk_policy.unit_basis_usd "1u = <figure>", the legacy "1u = <n> contracts"):
                     a units figure followed by "="
  fraction           desk_meta.unit.fraction / half_fraction printed: the word fraction (or half_fraction) beside a
                     number, or the field name half_fraction anywhere
  pool               a pool figure: the word pool beside a number, or an amount before it within three words
                     ("25 remains in the pool"; addendum 301 item 1)
  field_name         a field name that only ever holds a count or a figure (fee_order_contracts, order_contracts,
                     unit_usd, pool_usd, balance_dollars, market_exposure_dollars, half_fraction, contracts_basis), or
                     any name ending _usd / _dollars, anywhere
  uuid               an account id's shape: ANY UUID-shaped token, ticker or none (a bulletin carries no UUID at all:
                     match ids are integers, run ids are stamps; the stricter reading, law 4)
Each pattern reads every line as written, every line as RENDERED (rendered(): HTML entities decoded, tags and
Markdown emphasis removed, NFKC-folded, format characters dropped, whitespace one space) and the whole text as
rendered with every line break one space, so a value broken across lines, a fullwidth sign or an entity is read the
way the card or GitHub shows it.
The API key is the redaction's (sp_common.redact runs over every line before the guard), not a pattern here.
"""
from __future__ import annotations

import html
import re
import unicodedata

# ---- the #817 patterns (moved verbatim from tests/test_no_raw_kalshi_rows.py; the test imports them from here) ----

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
# (iii) a dollar amount: a dollar sign ($, U+FF04 or U+FE69), optional blanks (space, tab, U+00A0), an optional sign
# (ASCII plus or minus, or U+2212), optional blanks, an optional decimal point, then a digit. A $ with no digit after it
# ($HOME, ${var}, a bare $) never matches.
DOLLAR = re.compile("[$\uff04\ufe69][ \t\u00a0]*[+\\-\u2212]?[ \t\u00a0]*\\.?[0-9]")


def is_row(line: str) -> bool:
    """(i): a UUID-shaped token on the same line as a Kalshi ticker."""
    return bool(UUID.search(line) and TICKER.search(line))


def is_header(line: str) -> bool:
    """(ii): a CSV-shaped run of field names on the line holds the three header names in sequence."""
    for m in CSV_RUN.finditer(line):
        names = [f.strip().strip('"') for f in re.split(r"[,\u241f\t;|]", m.group(0))]
        at = [names.index(n) for n in SEQUENCE if n in names]
        if len(at) == len(SEQUENCE) and at == sorted(at):
            return True
    return False


# ---- the bulletin's own patterns (addendum 250 item 2), over the WHOLE text ----------------------------------------

# A count's or a figure's field name, as the export's JSON or a dict's str() writes it: the name may carry a prefix or a
# suffix joined by "_" (maker_contracts, n_contracts, unit_fraction), and its closing quote and separator may sit
# between the name and the number ("contracts": 5, 'contracts': 5, contracts=5).
_KEY_TAIL = "[\"']?\\s*[:=#(\\u00d7x]?\\s*[\"']?\\s*"
CONTRACT_COUNT = re.compile("(?i)\\d[\\d,.]*\\s*-?\\s*[a-z_]*contracts?(?![a-z0-9])"
                            "|(?<![a-z0-9])[a-z_]*contracts?(?:_[a-z_]*)?" + _KEY_TAIL + "\\d"
                            # addendum 299 item 1: the `count` label between the word and the number
                            # ("contract count: 5", "contract count = 12", "contracts-count 3")
                            "|(?<![a-z0-9])contracts?[\\s_-]*count(?![a-z0-9])\\W{0,4}\\d")
ORDER_TEXT = re.compile("(?i)\\bBUY\\s+(?:YES|NO)\\b|\\u00d7\\s*\\d"
                        "|@\\s*[\\d.]+\\s*c?\\s*x\\s*\\d"                       # "@ 0.45 x 3", "@ 45c x 3"
                        "|(?<![A-Za-z0-9])x\\s*\\d+\\s*(?:@|\\bat\\b)"          # "x 3 at 45c", "x3 @"
                        "|(?<![A-Za-z0-9])x\\d+\\b")                            # "x3" standing alone (lower case only)
UNIT_LABEL = re.compile(r"\b\d+(?:\.\d+)?\s*u\s*=")
FRACTION = re.compile("(?i)(?<![a-z0-9])[a-z_]*fraction(?![a-z0-9])[\"']?\\W{0,4}[+\\-]?\\.?\\d|\\bhalf_fraction\\b")
POOL = re.compile(r"(?i)\bpool\b\W{0,12}[+\-]?\.?\d"
                  r"|\d[\d,.]*\W{0,4}(?:[a-z]+\W+){0,3}pool\b")   # addendum 301 item 1: "25 remains in the pool"
FIELD_NAME = re.compile(r"(?i)\b(?:fee_order_contracts|order_contracts|unit_usd|pool_usd|balance_dollars|"
                        r"market_exposure_dollars|half_fraction|contracts_basis)\b|[a-z0-9]_(?:usd|dollars)\b")
# A dollar figure without the plain sign before it (the DOLLAR pattern is the #817 sign-then-digit one): a number
# beside USD / dollar(s), USD before a number, or a sign AFTER a number ("12$").
USD_WORD = re.compile("(?i)\\d[\\d,.]*\\s*(?:usd|dollars?)\\b|\\busd\\s*[+\\-\\u2212]?\\s*\\.?\\d|\\d\\s*[$\\uff04\\ufe69]")

# (name, test) in the order a line is judged; the first that matches names the refusal.
BULLETIN_PATTERNS = (
    ("uuid_beside_ticker", is_row),
    ("csv_header", is_header),
    ("dollar", lambda line: bool(DOLLAR.search(line))),
    ("usd_word", lambda line: bool(USD_WORD.search(line))),
    ("contract_count", lambda line: bool(CONTRACT_COUNT.search(line))),
    ("order_text", lambda line: bool(ORDER_TEXT.search(line))),
    ("unit_label", lambda line: bool(UNIT_LABEL.search(line))),
    ("fraction", lambda line: bool(FRACTION.search(line))),
    ("pool", lambda line: bool(POOL.search(line))),
    ("field_name", lambda line: bool(FIELD_NAME.search(line))),
    ("uuid", lambda line: bool(UUID.search(line))),
)
PATTERN_NAMES = tuple(n for n, _ in BULLETIN_PATTERNS)

_TAG = re.compile(r"<[^<>\n]{0,200}>")
_MARKUP = str.maketrans("", "", "\\*`~")


def rendered(text: str) -> str:
    """The text as a reader sees it once it is rendered: HTML entities decoded (&#36; is a $ on GitHub), tags and
    Markdown's emphasis and escape characters removed, compatibility forms folded (NFKC: a fullwidth sign or digit is
    the plain one), format characters (zero-width spaces, joiners) dropped, and every whitespace run, line breaks
    included, one space (the card's textwrap and a Markdown list item's continuation both join a broken line)."""
    t = unicodedata.normalize("NFKC", _TAG.sub("", html.unescape(str(text))))
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Cf").translate(_MARKUP)
    return re.sub(r"\s+", " ", t)


def _first(line: str) -> str | None:
    for name, hit in BULLETIN_PATTERNS:
        if hit(line):
            return name
    return None


def bulletin_offence(text: str) -> str | None:
    """The NAME of the first pattern the text matches, else None. Never the line (addendum 250 item 2: the receipt
    carries the pattern's name and the intended path, never the line). Read three ways, the first match winning:
    every line as written; every line as rendered (rendered()); and the WHOLE text as rendered, every line break one
    space, so a value broken across lines is read the way the card and the Markdown show it joined."""
    lines = str(text).splitlines() or [""]
    for line in lines:
        got = _first(line) or _first(rendered(line))
        if got:
            return got
    return _first(rendered(text))
