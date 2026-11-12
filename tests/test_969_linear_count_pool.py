"""#969 (ARCHITECT 2026-11-12 17:20 ET, addendum 362 item 4, verbatim: "#969 (the same quadratic read in CONTRACT_COUNT
and POOL): RULED as #960 was — the same fix, the same proof (each pattern matches exactly what it matched, the timing
pinned, mutations caught), money-path review, ONE PR, behind #926, #930 and #947"). Two bulletin-guard patterns are made
linear and must match exactly the strings they matched before:
  - CONTRACT_COUNT's count arm: one start per run of digits, commas and points (#960's digit-arm fix), and the blanks
    around its dash reachable only through the dash;
  - CONTRACT_COUNT's key arm: one start per run of letters and underscores, its underscore tail found once per run by
    a lookahead, and _KEY_TAIL's three runs of blanks each reachable only through the token before it (it was cubic);
  - POOL's number-first arm: one start per run of digits, commas and points.
Every caller reads only whether a pattern matches (bool(search)), so "the same strings" is the whole contract."""
import random
import re
import time

import pytest

import src.privacy_patterns as pv

# The patterns as they stood on main before #969 (981734a4), verbatim.
OLD_KEY_TAIL = "[\"']?\\s*[:=#(\\u00d7x]?\\s*[\"']?\\s*"
OLD_CONTRACT_COUNT = re.compile("(?i)\\d[\\d,.]*\\s*-?\\s*[a-z_]*contracts?(?![a-z0-9])"
                                "|(?<![a-z0-9])[a-z_]*contracts?(?:_[a-z_]*)?" + OLD_KEY_TAIL + "\\d"
                                "|(?<![a-z0-9])contracts?[\\s_-]*count(?![a-z0-9])\\W{0,4}\\d")
OLD_POOL = re.compile(r"(?i)\bpool\b(?:\W+[a-z]+){0,3}\W{0,12}[+\-]?\.?\d"
                      r"|\d[\d,.]*\W{0,4}(?:[a-z]+\W+){0,3}pool\b")
NEW_COUNT_ARM = "(?<![\\d,.])[,.]*\\d[\\d,.]*\\s*(?:-\\s*)?[a-z_]*contracts?(?![a-z0-9])"
NEW_KEY_ARM = ("(?<![a-z_])(?:(?<![0-9])|[a-z]*_)(?:[a-z_]*contracts?|(?=[a-z_]*?contracts?_)[a-z_]*)"
               "[\"']?\\s*(?:[:=#(\\u00d7x]\\s*)?(?:[\"']\\s*)?\\d")
NEW_POOL_ARM = r"(?<![\d,.])[,.]*\d[\d,.]*\W{0,4}(?:[a-z]+\W+){0,3}pool\b"

ALPHABET = (list("0123456789,.,.  \t-_:=#(\"'xXpoolPOOL") + [
    "×", "٣", "ſ", "K", " ", "contract", "contracts", "count", "pool", "CONTRACTS", "a", "b",
    "_contract_", "5", "1,0", ".5", "contract_", "contracts_", "_", "__", "x", "X", "x5", "_x", "contract_x", "ax",
    "9_", "x\"5", "x: 5", " 5", "'"])

CURATED = [
    "5 contracts", "5contracts", "5 - contracts", "5 -contract", "1,000 contracts", ".5 contracts", ",5 contract",
    "..5 contracts", "5. contracts", "٣ contracts", "12 maker_contracts", "5 contractsx", "5 contracts1",
    "contracts: 5", "contracts = 5", "\"contracts\": 5", "'contracts': 5", "contracts=5", "contracts(5",
    "contracts × 5", "contractsx5", "contracts x 5", "contracts_x5", "contract_ax5", "maker_contracts: 5",
    "n_contracts 5", "contracts_basis: 5", "5_contracts: 3", "5contracts: 3", "a5_contracts: 3", "x__contracts: 5",
    "_contracts: 5", "contract count: 5", "contracts-count 3", "contract_count=12", "contracts \" : \" 5",
    "contracts\"  =  '  5", "contracts: x", "contracts", "contract", "5", "",
    "the pool is 25", "pool: 25", "25 remains in the pool", "25,000 in pool", ".5 pool", ",5 the pool", "5pool",
    "٣ in the pool", "1.2.3 pool", "pool", "25", "25 remains in the swimming pool", "pooled 25", "25 pools",
    "ſontracts 5", "5 Kontracts", "contractſ: 5",
]


def test_969_the_new_arms_are_the_ones_in_the_module():
    """The pins this test reads against: a change to either pattern must change this file too."""
    assert pv.CONTRACT_COUNT.pattern.startswith("(?i)" + NEW_COUNT_ARM + "|" + NEW_KEY_ARM + "|"), pv.CONTRACT_COUNT.pattern
    assert pv.POOL.pattern.endswith("|" + NEW_POOL_ARM), pv.POOL.pattern
    assert pv.CONTRACT_COUNT.flags == OLD_CONTRACT_COUNT.flags and pv.POOL.flags == OLD_POOL.flags


def test_969_the_differential_is_not_vacuous():
    """Both sides see matches and non-matches, and the old patterns are really the old ones."""
    assert OLD_CONTRACT_COUNT.pattern != pv.CONTRACT_COUNT.pattern and OLD_POOL.pattern != pv.POOL.pattern
    for p in (pv.CONTRACT_COUNT, OLD_CONTRACT_COUNT):
        assert p.search("5 contracts") and p.search("x__contracts: 5") and p.search("contract_ax5")
        assert not p.search("contracts: x") and not p.search("5contracts1")
    for p in (pv.POOL, OLD_POOL):
        assert p.search(".5 pool") and p.search("the pool is 25") and not p.search("pooled 25")


@pytest.mark.parametrize("text", CURATED)
def test_969_the_curated_lines_read_as_before(text):
    assert bool(pv.CONTRACT_COUNT.search(text)) == bool(OLD_CONTRACT_COUNT.search(text)), text
    assert bool(pv.POOL.search(text)) == bool(OLD_POOL.search(text)), text


def test_969_sixty_thousand_random_lines_read_as_before():
    """A seeded differential test over the patterns' own alphabet: the new patterns match a line exactly when the old
    ones did (300,000 such lines on 3.12 and 100,000 on 3.10 were read the same while building)."""
    rng = random.Random(969)
    for _ in range(60000):
        text = "".join(rng.choice(ALPHABET) for _ in range(rng.randint(0, 14)))
        assert bool(pv.CONTRACT_COUNT.search(text)) == bool(OLD_CONTRACT_COUNT.search(text)), repr(text)
        assert bool(pv.POOL.search(text)) == bool(OLD_POOL.search(text)), repr(text)


@pytest.mark.parametrize("name, pattern, text", [
    # The measured inputs (main, Python 3.12): 15.6 s, 7.8 s, 7.9 s and 17.3 s on 20,000 characters; each digit-run
    # shape pins one member of the count arm's lookbehind: (?<![\d,]) or (?<![0-9,.]) would match the same and be
    # quadratic again, as #960's review found for USD_WORD.
    ("CONTRACT_COUNT, 50,000 digits", "CONTRACT_COUNT", "1" * 50000),
    ("CONTRACT_COUNT, 25,000 digit-comma pairs", "CONTRACT_COUNT", "1," * 25000),
    ("CONTRACT_COUNT, 25,000 digit-point pairs", "CONTRACT_COUNT", "1." * 25000),
    ("CONTRACT_COUNT, 50,000 Arabic-Indic digits", "CONTRACT_COUNT", "٣" * 50000),
    # The dash's two runs of blanks (2.3 s on 20,000 before) and one run (6.7 s on 20,000 before).
    ("CONTRACT_COUNT, a digit, blanks, a dash, blanks", "CONTRACT_COUNT", "1" + " " * 25000 + "-" + " " * 25000 + "x"),
    ("CONTRACT_COUNT, a digit and 50,000 blanks", "CONTRACT_COUNT", "1" + " " * 50000 + "x"),
    # The key tail's runs of blanks (cubic: 2.4 s on 1,000 blanks before).
    ("CONTRACT_COUNT, contracts and 50,000 blanks", "CONTRACT_COUNT", "contracts" + " " * 50000 + "y"),
    ("CONTRACT_COUNT, contracts, blanks, a colon, blanks", "CONTRACT_COUNT",
     "contracts" + " " * 25000 + ":" + " " * 25000 + "y"),
    ("CONTRACT_COUNT, contracts, a quote and blanks twice", "CONTRACT_COUNT",
     "contracts\"" + " " * 20000 + "=" + " " * 20000 + "\"" + " " * 20000 + "y"),
    # The key arm's starts: one per run of letters and underscores, not one per underscore.
    ("CONTRACT_COUNT, 50,000 underscores", "CONTRACT_COUNT", "_" * 50000),
    ("CONTRACT_COUNT, 50,000 underscores and a partial word", "CONTRACT_COUNT", "_" * 50000 + "contrac"),
    ("CONTRACT_COUNT, a digit and 50,000 underscores", "CONTRACT_COUNT", "1" + "_" * 50000),
    # The key arm's underscore tail, once per run (18 s on 40,000 characters before).
    ("CONTRACT_COUNT, contract_ 5,000 times", "CONTRACT_COUNT", "contract_" * 5000),
    ("CONTRACT_COUNT, contract_x 5,000 times", "CONTRACT_COUNT", "contract_x" * 5000),
    ("POOL, 50,000 digits", "POOL", "1" * 50000),
    ("POOL, 25,000 digit-comma pairs", "POOL", "1," * 25000),
    ("POOL, 25,000 digit-point pairs", "POOL", "1." * 25000),
    ("POOL, 50,000 Arabic-Indic digits", "POOL", "٣" * 50000),
])
def test_969_the_measured_inputs_read_in_linear_time(name, pattern, text):
    t0 = time.perf_counter()
    assert getattr(pv, pattern).search(text) is None
    assert time.perf_counter() - t0 < 1.0, name


def test_969_the_guard_reads_a_long_digit_run_quickly_and_still_refuses_a_count():
    """Through bulletin_offence: the long digit run #960's guard test could not use (#969) now reads in well under the
    bar, and a count beside it still refuses."""
    t0 = time.perf_counter()
    assert pv.bulletin_offence("1" * 50000) is None
    assert time.perf_counter() - t0 < 3.0
    assert pv.bulletin_offence("1" * 50000 + " 5 contracts") == "contract_count"
