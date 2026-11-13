"""#979 (ARCHITECT 2026-11-13 09:00 ET, addendum 364 item 2, verbatim: "#979 (CSV_RUN and FRACTION) — RULED as #960 and
#969 were: the same fix, the same proof, money-path review, ONE PR. AND THE CLASS IS CLOSED IN IT, since this is the
third sample"). Two patterns are made linear and must match exactly what they matched before:
  - CSV_RUN (the shared #817 header-row pattern): one start per run of letters, digits and underscores (or at a
    quote), the run's leading digits taken outside the group "run"; and the delimiter's blanks read once;
  - FRACTION (the bulletin guard): one start per run of letters and underscores, as #969's key arm.
CSV_RUN is read by is_header through finditer and the run's text, so its contract is the runs themselves: the group
"run" of every match is the old pattern's whole match, at the same place, one for one, and is_header reads every line
as before. FRACTION is read only as bool(search). The class (every pattern in the module, every shape) is closed in
tests/test_privacy_patterns_linear.py."""
import itertools
import random
import re
import time

import pytest

import src.privacy_patterns as pv

# The patterns as they stood on main before #979 (411a7008), verbatim.
OLD_FIELD = r'"?[A-Za-z_][A-Za-z0-9_]*"?'
OLD_CSV_RUN = re.compile(OLD_FIELD + r"(?:[ \t]*[,\u241f\t;|][ \t]*" + OLD_FIELD + r")+")
OLD_FRACTION = re.compile("(?i)(?<![a-z0-9])[a-z_]*fraction(?![a-z0-9])[\"']?\\W{0,4}[+\\-]?\\.?\\d|\\bhalf_fraction\\b")
NEW_CSV_RUN = ('(?:(?=")|(?<![A-Za-z0-9_])[0-9]*)(?P<run>"?[A-Za-z_][A-Za-z0-9_]*"?'
               '(?:(?:[ \\t]*[,\\u241f;|]|[ ]*\\t)[ \\t]*"?[A-Za-z_][A-Za-z0-9_]*"?)+)')
NEW_FRACTION = ("(?i)(?<![a-z_])(?:(?<![0-9])|[a-z]*_)[a-z_]*fraction(?![a-z0-9])[\"']?\\W{0,4}[+\\-]?\\.?\\d"
                "|\\bhalf_fraction\\b")


def _old_is_header(line):
    """is_header as it stood on main, over the old pattern's whole match."""
    for m in OLD_CSV_RUN.finditer(line):
        names = [f.strip().strip('"') for f in re.split(r"[,\u241f\t;|]", m.group(0))]
        at = [names.index(n) for n in pv.SEQUENCE if n in names]
        if len(at) == len(pv.SEQUENCE) and at == sorted(at):
            return True
    return False


def _same(text):
    old = [m.span() for m in OLD_CSV_RUN.finditer(text)]
    new = [m.span("run") for m in pv.CSV_RUN.finditer(text)]
    assert new == old, (repr(text), old, new)
    assert pv.is_header(text) == _old_is_header(text), repr(text)
    assert bool(pv.FRACTION.search(text)) == bool(OLD_FRACTION.search(text)), repr(text)


# Each symbol a pattern reads differently: letters either case (the Kelvin sign and long s fold to k and s under
# FRACTION's IGNORECASE), digits ASCII and not, the five delimiters, blanks, quotes, the words and the header's names.
CSV_SYMBOLS = ["a", "B", "_", "1", "0", '"', ",", "\t", " ", ";", "|", "\u241f", "x", "-", "\u0663", "\u017f",
               "\u212a"]
ALPHABET = CSV_SYMBOLS + ["f", "fraction", "fractions", "half_fraction", "F", ":", "'", "+", ".", "5", "=", "12",
                          "quantity_fp", "entry_price_dollars", "realized_pnl_with_fees_dollars", '"quantity_fp"',
                          " \t ", "\t\t", ", "]
HEADER = ("quantity_fp", "entry_price_dollars", "realized_pnl_with_fees_dollars")
CURATED = [
    ",".join(HEADER), "\t".join(HEADER), ";".join(HEADER), "|".join(HEADER), "\u241f".join(HEADER),
    " , ".join(HEADER), " \t ".join(HEADER), "\t \t".join(HEADER), ",".join('"%s"' % h for h in HEADER),
    "1" + ",".join(HEADER), '"1' + ",".join(HEADER), 'x"' + ",".join(HEADER), "x1" + ",".join(HEADER),
    "id," + ",".join(HEADER) + ",fee", ",".join(reversed(HEADER)), "quantity_fp,entry_price_dollars",
    "12abc,def", '"12abc",def', 'x"abc,d', 'a,b"c,d', 'a,b""c,d', '12"abc",x', "ab12cd,e", "a\t\t\t!", "a \t \t!",
    "a ,b", "a, b", "a\t,\tb", "a,1b", "a,,b", "", ",", "a", '"', '""',
    "fraction: 0.08", "unit_fraction=0.08", "half_fraction", "5_fraction: 1", "5a_b_fraction: 3", "5xfraction: 3",
    "a__fraction 4", "_fraction: .5", "fractions 5", "fraction_x 5", "\u0663_fraction 2", "\u017fraction 1",
    "Fraction -1", "fraction'  5", "x_half_fraction",
]


def test_979_the_new_patterns_are_the_ones_in_the_module():
    assert pv.CSV_RUN.pattern == NEW_CSV_RUN, pv.CSV_RUN.pattern
    assert pv.FRACTION.pattern == NEW_FRACTION, pv.FRACTION.pattern
    assert pv.CSV_RUN.flags == OLD_CSV_RUN.flags and pv.FRACTION.flags == OLD_FRACTION.flags


def test_979_the_differential_is_not_vacuous():
    """Both sides see matches and non-matches, the run differs from the whole match where digits lead it, and the old
    patterns are really the old ones."""
    assert OLD_CSV_RUN.pattern != pv.CSV_RUN.pattern and OLD_FRACTION.pattern != pv.FRACTION.pattern
    m = pv.CSV_RUN.search("12abc,def")
    assert m.group(0) == "12abc,def" and m.group("run") == "abc,def" == OLD_CSV_RUN.search("12abc,def").group(0)
    assert pv.is_header(",".join(HEADER)) and pv.is_header("9" + "\t".join(HEADER)) and not pv.is_header("a b c")
    for p in (pv.FRACTION, OLD_FRACTION):
        assert p.search("5a_b_fraction: 3") and p.search("half_fraction") and not p.search("5xfraction: 3")


@pytest.mark.parametrize("text", CURATED)
def test_979_the_curated_lines_read_as_before(text):
    _same(text)


def test_979_every_short_line_reads_as_before():
    """Every line of up to four symbols over the CSV symbols (88,741 lines). While building, every line of up to six of
    them (25,646,167) and every line of up to five FRACTION symbols (6,728,904) were read the same."""
    n = 0
    for size in range(5):
        for parts in itertools.product(CSV_SYMBOLS, repeat=size):
            _same("".join(parts))
            n += 1
    assert n == 88741


def test_979_sixty_thousand_random_lines_read_as_before():
    """A seeded differential test: the runs, is_header and FRACTION read every line as before (300,000 such lines
    were read the same while building)."""
    rng = random.Random(979)
    for _ in range(60000):
        _same("".join(rng.choice(ALPHABET) for _ in range(rng.randint(0, 16))))


@pytest.mark.parametrize("name, pattern, text", [
    # The measured inputs (main, Python 3.12): 11.6 s on one 20,000-letter word, 11.0 s on 20,000 underscores. Each
    # shape pins one member of the lookbehind: without the upper case, the digits or the underscore, it matches the
    # same and is quadratic again on that run.
    ("CSV_RUN, a 50,000-letter word", "CSV_RUN", "a" * 50000),
    ("CSV_RUN, a 50,000-letter upper-case word", "CSV_RUN", "A" * 50000),
    ("CSV_RUN, 50,000 underscores", "CSV_RUN", "_" * 50000),
    ("CSV_RUN, ab12 12,500 times", "CSV_RUN", "ab12" * 12500),
    ("CSV_RUN, a_ 25,000 times", "CSV_RUN", "a_" * 25000),
    ("CSV_RUN, contract_ 5,500 times", "CSV_RUN", "contract_" * 5500),
    ("CSV_RUN, 50,000 digits", "CSV_RUN", "1" * 50000),
    ("CSV_RUN, 50,000 digits and a word", "CSV_RUN", "1" * 50000 + "a"),
    ("CSV_RUN, a quote and a 50,000-letter word", "CSV_RUN", 'x"' + "a" * 50000),
    # The delimiter's blanks (4.7 s on a field and 20,000 tabs before; 2.3 s on 20,000 space-tab pairs).
    ("CSV_RUN, a field and 50,000 tabs", "CSV_RUN", "a" + "\t" * 50000 + "!"),
    ("CSV_RUN, a field and 25,000 space-tab pairs", "CSV_RUN", "a" + " \t" * 25000 + "!"),
    ("CSV_RUN, a field, a comma and 50,000 tabs", "CSV_RUN", "a," + "\t" * 50000 + "!"),
    # The spaces side of the delimiter (#979's review: hoisting the spaces before the alternation matches the same and
    # is quadratic again on a field and a run of spaces).
    ("CSV_RUN, a field and 50,000 spaces", "CSV_RUN", "a" + " " * 50000 + "!"),
    ("CSV_RUN, a field, a comma and 50,000 spaces", "CSV_RUN", "a," + " " * 50000 + "!"),
    # FRACTION (3.5 s on 20,000 underscores before).
    ("FRACTION, 50,000 underscores", "FRACTION", "_" * 50000),
    ("FRACTION, a_ 25,000 times", "FRACTION", "a_" * 25000),
    ("FRACTION, a digit and 50,000 underscores", "FRACTION", "1" + "_" * 50000),
    ("FRACTION, fraction_ 5,500 times", "FRACTION", "fraction_" * 5500),
    # The digit-led start's letters (#979's review: [a-z]*_[a-z]* there matches the same and is quadratic again).
    ("FRACTION, a digit, an underscore and 50,000 letters", "FRACTION", "1_" + "a" * 50000),
    ("FRACTION, a digit and 50,000 letters", "FRACTION", "1" + "a" * 50000),
])
def test_979_the_measured_inputs_read_in_linear_time(name, pattern, text):
    t0 = time.perf_counter()
    for _ in getattr(pv, pattern).finditer(text):
        pass
    assert time.perf_counter() - t0 < 1.0, name


def test_979_the_guard_reads_a_long_word_quickly_and_still_refuses_the_header():
    """Through bulletin_offence: one 20,000-letter word took 54.6 s before; the header row beside it still refuses."""
    t0 = time.perf_counter()
    assert pv.bulletin_offence("a" * 50000) is None
    assert pv.bulletin_offence("_" * 50000) is None
    assert time.perf_counter() - t0 < 3.0
    assert pv.bulletin_offence("a" * 50000 + " " + ",".join(HEADER)) == "csv_header"
    assert pv.bulletin_offence("_" * 50000 + " fraction: 0.08") == "fraction"
