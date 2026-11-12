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
                     or a sign after a number (12 USD, USD 12, 12 dollars, 12$); and, spelled out (addendum 320 item 1),
                     a number word beside USD / dollar(s) / buck(s) on either side, or a sign before or after one
                     (twenty-five dollars, one hundred USD, dollars twenty, a buck twenty, $ twenty-five, $-twenty)
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
  pool               a pool figure: the word pool beside a number or within three words of it, either side
                     ("the pool is 25", "pool balance: 25"; addendum 304 item 1), or an amount before it within three words
                     ("25 remains in the pool"; addendum 301 item 1)
  field_name         a field name that only ever holds a count or a figure (fee_order_contracts, order_contracts,
                     unit_usd, pool_usd, balance_dollars, market_exposure_dollars, half_fraction, contracts_basis), or
                     any name ending _usd / _dollars, anywhere
  uuid               an account id's shape: ANY UUID-shaped token, ticker or none (a bulletin carries no UUID at all:
                     match ids are integers, run ids are stamps; the stricter reading, law 4)
Each pattern reads every line as written, every line as RENDERED (rendered(): HTML entities decoded, tags and
Markdown emphasis removed; read twice, the second time with HTML comments and tags of any length stripped first,
addendum 318 item 2), NFKC-folded, format characters dropped, whitespace one space) and the whole text as
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
# LINEAR (#960; ARCHITECT 2026-11-12 14:25 ET, addendum 358 item 4(1): "a real finding, slow and never wrong; its PR is
# queued behind the dated work, the shared pattern's change reviewed as money-path"): the blanks after the sign are
# reachable only through the sign, so a "$" and a long run of blanks is read once, never split two ways (it took 5 s on
# 20,000 blanks). It matches exactly the strings it matched before (tests/test_960_linear_dollar_patterns.py).
DOLLAR = re.compile("[$\uff04\ufe69][ \t\u00a0]*(?:[+\\-\u2212][ \t\u00a0]*)?\\.?[0-9]")


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
# LINEAR (#969; ARCHITECT 2026-11-12 17:20 ET, addendum 362 item 4: "RULED as #960 was — the same fix, the same proof
# (each pattern matches exactly what it matched, the timing pinned, mutations caught), money-path review, ONE PR"):
# each pattern below matches exactly the strings it matched before (tests/test_969_linear_count_pool.py) and reads a
# long run once. Every run of blanks is reachable only through the token before it, so no two runs split one stretch
# of blanks (the tail took 2.4 s on "contracts" and 1,000 blanks before, cubic).
_KEY_TAIL = "[\"']?\\s*(?:[:=#(\\u00d7x]\\s*)?(?:[\"']\\s*)?"
# The count arm starts once per run of digits, commas and points (skipping commas or points before its first digit): a
# later start in the run can only match where the run's first digit does (15.6 s on 20,000 digits before). The key
# arm starts once per run of letters and underscores: at the run's start, or, when a digit precedes the run, just
# after its first underscore (the earliest start the old lookbehind allowed), never once per underscore. Its
# underscore tail is found once per run by a lookahead: the key tail can follow a run of letters only at the run's end
# (or one letter before it, an "x" separator), so a tail through the run's end is the same test as one through an
# underscore after the word, read once, not once per "contract_" (it was cubic: 15.8 s on 4,000 characters of
# "contract_", 186 s on 9,000).
CONTRACT_COUNT = re.compile("(?i)(?<![\\d,.])[,.]*\\d[\\d,.]*\\s*(?:-\\s*)?[a-z_]*contracts?(?![a-z0-9])"
                            "|(?<![a-z_])(?:(?<![0-9])|[a-z]*_)(?:[a-z_]*contracts?|(?=[a-z_]*?contracts?_)[a-z_]*)"
                            + _KEY_TAIL + "\\d"
                            # addendum 299 item 1: the `count` label between the word and the number
                            # ("contract count: 5", "contract count = 12", "contracts-count 3")
                            "|(?<![a-z0-9])contracts?[\\s_-]*count(?![a-z0-9])\\W{0,4}\\d")
ORDER_TEXT = re.compile("(?i)\\bBUY\\s+(?:YES|NO)\\b|\\u00d7\\s*\\d"
                        "|@\\s*[\\d.]+\\s*c?\\s*x\\s*\\d"                       # "@ 0.45 x 3", "@ 45c x 3"
                        "|(?<![A-Za-z0-9])x\\s*\\d+\\s*(?:@|\\bat\\b)"          # "x 3 at 45c", "x3 @"
                        "|(?<![A-Za-z0-9])x\\d+\\b")                            # "x3" standing alone (lower case only)
UNIT_LABEL = re.compile(r"\b\d+(?:\.\d+)?\s*u\s*=")
FRACTION = re.compile("(?i)(?<![a-z0-9])[a-z_]*fraction(?![a-z0-9])[\"']?\\W{0,4}[+\\-]?\\.?\\d|\\bhalf_fraction\\b")
POOL = re.compile(r"(?i)\bpool\b(?:\W+[a-z]+){0,3}\W{0,12}[+\-]?\.?\d"   # 304 item 1: "the pool is 25"
                  # addendum 301 item 1: "25 remains in the pool"; LINEAR (#969, 362 item 4): one start per run of
                  # digits, commas and points, as CONTRACT_COUNT's count arm (3.4 s on 10,000 digits before)
                  r"|(?<![\d,.])[,.]*\d[\d,.]*\W{0,4}(?:[a-z]+\W+){0,3}pool\b")
FIELD_NAME = re.compile(r"(?i)\b(?:fee_order_contracts|order_contracts|unit_usd|pool_usd|balance_dollars|"
                        r"market_exposure_dollars|half_fraction|contracts_basis)\b|[a-z0-9]_(?:usd|dollars)\b")
# A dollar figure without the plain sign before it (the DOLLAR pattern is the #817 sign-then-digit one): a number
# beside USD / dollar(s), USD before a number, or a sign AFTER a number ("12$").
# SPELLED-OUT DOLLARS (ARCHITECT 2026-11-10 12:20 ET, addendum 320 item 1, verbatim: "the BULLETIN guard's own dollar
# pattern widens to number words beside a dollar word (one..ninety-nine, hundred, thousand, million; dollars, USD,
# bucks; `$` followed by a number word), refusing; `sp_common.redact` is UNCHANGED"). A number word is one .. nineteen,
# the tens twenty .. ninety, hundred, thousand or million, optionally after a tens word with any joiner or none
# ("twenty-five", "twenty five", "twentyfive"). It is refused beside a dollar word (USD, dollar(s), buck(s); "US" or
# "U.S." may stand between), on either side ("twenty-five dollars", "dollars twenty", "a buck twenty"), and after a
# dollar sign with an optional sign between ("$ twenty-five", "$-twenty"), or before one ("twenty$"). Joiners take any
# blank, an underscore or asterisk (Markdown emphasis GitHub hides) and the typographic hyphens and dashes U+2010..2015
# and U+2212; a word edge is a letter edge, so "_twenty_" is read as GitHub shows it. A digit beside bucks is NOT here
# (the ruling names number words; "Celtics 112, Bucks 108" would refuse). This pattern only: the shared #817 DOLLAR (the
# CI test's) matches what it matched before, and so do the digit arms. Every run of blanks is a single star: the blanks after a
# sign are reachable only through the sign, so no two runs can split one stretch of blanks: these arms stay linear on a
# long line. The two older arms are linear too since #960 (358 item 4(1)): the digit arm starts only where a run of
# digits, commas and points starts (a run that ends anywhere but at its last character cannot reach the dollar word,
# so one start per run is the same test, read once, not once per digit: 55 s on 50,000 digits before), skipping any
# commas or points before the run's first digit (".5 dollars" still refuses); and "usd" before a number takes the
# sign's blanks only through the sign, as DOLLAR does. Each matches exactly what it matched before.
_L, _R = "(?<![A-Za-z])", "(?![A-Za-z])"
_JOIN = "[\\s_*\\-\\u2010-\\u2015\\u2212]*"
_NUM_WORD = ("(?:(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)" + _JOIN + ")?"
             "(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen"
             "|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand"
             "|million)")
_DOLLAR_WORD = "(?:usd|dollars?|bucks?)"
_US = "(?:u\\.?" + "[ ]?" + "s\\.?" + _JOIN + ")?"                     # "twenty US dollars", "twenty U.S. dollars"
_SIGN = "[$\\uff04\\ufe69]"
USD_WORD = re.compile("(?i)(?<![\\d,.])[,.]*\\d[\\d,.]*\\s*(?:usd|dollars?)\\b"            # 12 dollars, 1,000 USD
                      "|\\busd\\s*(?:[+\\-\\u2212]\\s*)?\\.?\\d|\\d\\s*" + _SIGN +
                      "|" + _L + _NUM_WORD + _JOIN + _US + _DOLLAR_WORD + _R +            # twenty-five dollars
                      "|" + _L + _DOLLAR_WORD + "[\\s_*:\\-\\u2010-\\u2015\\u2212]*" + _NUM_WORD + _R +   # dollars twenty
                      "|" + _SIGN + "[\\s\\u00a0_*]*(?:[+\\-\\u2212\\u2010-\\u2015][\\s\\u00a0_*]*)?" + _NUM_WORD + _R +  # $-twenty
                      "|" + _L + _NUM_WORD + "[\\s_*]*" + _SIGN)                          # twenty$

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
# ARCHITECT 2026-11-10 08:50 ET, addendum 318 item 2 (Codex #894 P1 at :130): "the rendered reading strips HTML
# comments (`<!--` … `-->`, any length; an unterminated comment hides to the end of the text, and the raw reading — which
# the credential check already takes — still sees it) and tags of any length with a small scanner, as the link collapse
# is". The scanner reads the text as written, before entities are decoded (an entity-written `&lt;!--` is text GitHub
# shows, not a comment). It is a SECOND rendered reading beside the first, never in its place (renderings()): GitHub
# shows some of what the scanner strips (a `<!--` mid-line with no `-->`, a tag across a blank line, a backslash-escaped
# `\<`, markup in a code span), so replacing the reading would hide text the guard read before (the pre-push review
# of 0212ba1c). Every pattern reads both, the first match winning: a tightening only.
_ATTRS = r"""(?:\s+[A-Za-z_:][A-Za-z0-9_.:-]*(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'=<>`]+))?)*\s*/?>"""
_OPEN_TAG = re.compile(r"<[A-Za-z][A-Za-z0-9-]*" + _ATTRS)
_CLOSE_TAG = re.compile(r"</[A-Za-z][A-Za-z0-9-]*\s*>")


def strip_html(text: str) -> str:
    """HTML comments and tags removed, of any length, as GitHub hides them (addendum 318 item 2): a comment from `<!--`
    to the first `-->` after it (`<!-->` and `<!--->` are empty comments), an unterminated one to the end of the text;
    an open tag (a letter-led name, attributes whose quoted values may hold `>`, `<` or a line break) or a closing tag.
    A `<` that starts neither is kept as written."""
    t = str(text)
    out: list[str] = []
    i, n = 0, len(t)
    while i < n:
        if t[i] == "<":
            if t.startswith("<!--", i):
                e = t.find("-->", i + 2)
                if e == -1:
                    break                              # unterminated: hidden to the end of the text
                i = e + 3
                continue
            m = _OPEN_TAG.match(t, i) or _CLOSE_TAG.match(t, i)
            if m:
                i = m.end()
                continue
        out.append(t[i])
        i += 1
    return "".join(out)
# ARCHITECT 2026-11-09 09:55 ET, addendum 304 item 1: Markdown link and image syntax collapses to its visible label
# BEFORE any pattern runs ("[label](url) → label, ![alt](url) → alt, reference-style [label][ref] → label, and
# autolinks <url> → the url"), so a value broken by link syntax reads as GitHub shows it.


def _balanced_end(t: str, j: int, open_: str, close_: str) -> int | None:
    """The index just past the `close_` that balances an `open_` already read (j is the index after it), on one line,
    a backslash-escaped character never counted; None when it never balances."""
    depth, n = 1, len(t)
    while j < n:
        ch = t[j]
        if ch == "\n":
            return None
        if ch == "\\":
            j += 2
            continue
        if ch == open_:
            depth += 1
        elif ch == close_:
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return None


def _destination_end(t: str, j: int) -> int | None:
    """The index just past an inline link's closing ')' (j is the index after its '('), read as GitHub reads it
    (addendum 306 item 1(a)): a destination in <...> taken whole, balanced parentheses inside the destination, a quoted
    title after whitespace taken whole, backslash escapes skipped; on one line; None when it never closes."""
    n, k = len(t), j
    while k < n and t[k] in " \t":
        k += 1
    if k < n and t[k] == "<":
        e = k + 1
        while e < n and t[e] not in "<>\n":
            e += 2 if t[e] == "\\" else 1
        if e < n and t[e] == ">":
            j = e + 1
    depth = 1
    while j < n:
        ch = t[j]
        if ch == "\n":
            return None
        if ch == "\\":
            j += 2
            continue
        if ch in "\"'" and t[j - 1] in " \t":
            e = t.find(ch, j + 1)
            if e != -1 and "\n" not in t[j + 1:e]:
                j = e + 1
                continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return None


def _collapse_once(t: str) -> str:
    """One pass of the scanner: every `[label](destination)`, `![alt](destination)` and `[label][ref]` to its label,
    the label's own brackets balanced; text that is not a whole link is kept as written."""
    out: list[str] = []
    i, n = 0, len(t)
    while i < n:
        ch = t[i]
        if ch == "\\":
            out.append(t[i:i + 2])
            i += 2
            continue
        if ch == "[":
            e = _balanced_end(t, i + 1, "[", "]")
            if e is not None and e < n and t[e] in "([":
                end = _destination_end(t, e + 1) if t[e] == "(" else _balanced_end(t, e + 1, "[", "]")
                if end is not None:
                    if out and out[-1] == "!":
                        out.pop()                      # an image: its alt text is what shows
                    out.append(t[i + 1:e - 1])
                    i = end
                    continue
        out.append(ch)
        i += 1
    return "".join(out)


_MD_AUTOLINK = re.compile(r"<((?:[a-z][a-z0-9+.-]{1,31}:|www\.)[^<>\s]*|[^<>\s@]+@[^<>\s@]+\.[^<>\s@]+)>", re.IGNORECASE)


def collapse_links(text: str) -> str:
    """Markdown links and images to their visible label (addendum 304 item 1), by a small scanner that reads a link
    target's balanced parentheses (addendum 306 item 1(a)), repeated until nothing changes so a link inside a label
    collapses too; autolinks to the url they show."""
    t = str(text)
    for _ in range(8):
        before = t
        t = _MD_AUTOLINK.sub(r"\1", _collapse_once(t))
        if t == before:
            break
    return t
_MARKUP = str.maketrans("", "", "\\*`~")


def rendered(text: str, strip_markup: bool = False) -> str:
    """The text as a reader sees it once it is rendered: HTML entities decoded (&#36; is a $ on GitHub), tags and
    Markdown's emphasis and escape characters removed; with `strip_markup`, HTML comments and tags of any length removed
    first (strip_html, addendum 318 item 2: renderings() reads both forms), link and image syntax collapsed to its label (addendum 304
    item 1), compatibility forms folded (NFKC: a fullwidth sign or digit is
    the plain one), format characters (zero-width spaces, joiners) dropped, and every whitespace run, line breaks
    included, one space (the card's textwrap and a Markdown list item's continuation both join a broken line)."""
    t = strip_html(text) if strip_markup else str(text)
    t = unicodedata.normalize("NFKC", _TAG.sub("", collapse_links(html.unescape(t))))
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Cf").translate(_MARKUP)
    return re.sub(r"\s+", " ", t)


def renderings(text: str) -> tuple[str, str]:
    """Both rendered readings (addendum 318 item 2): rendered() as before, and rendered() with HTML comments and tags of
    any length stripped first. A pattern matching either refuses."""
    return rendered(text), rendered(text, strip_markup=True)


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
        got = _first(line) or next((g for g in map(_first, renderings(line)) if g), None)
        if got:
            return got
    return next((g for g in map(_first, renderings(text)) if g), None)
