"""#960 (ARCHITECT 2026-11-12 14:25 ET, addendum 358 item 4(1), verbatim: "#960 (the quadratic digit arms and the shared
DOLLAR): a real finding, slow and never wrong; its PR is queued behind the dated work, the shared pattern's change
reviewed as money-path"). Three patterns are made linear and must match exactly the strings they matched before:
  - the shared #817 DOLLAR: the blanks after the sign reachable only through the sign;
  - USD_WORD's digit arm: one start per run of digits, commas and points (skipping commas and points before the run's
    first digit), never one per digit;
  - USD_WORD's "usd" arm: as DOLLAR.
Every caller reads only whether a pattern matches (bool(search)), so "the same strings" is the whole contract."""
import random
import re
import time

import pytest

import src.privacy_patterns as pv

# The patterns as they stood on main before #960 (b59588f9), verbatim.
OLD_DOLLAR = re.compile("[$＄﹩][ \t ]*[+\\-−]?[ \t ]*\\.?[0-9]")
OLD_DIGIT_ARM = "\\d[\\d,.]*\\s*(?:usd|dollars?)\\b"
OLD_USD_ARM = "\\busd\\s*[+\\-\\u2212]?\\s*\\.?\\d"
NEW_DIGIT_ARM = "(?<![\\d,.])[,.]*\\d[\\d,.]*\\s*(?:usd|dollars?)\\b"
NEW_USD_ARM = "\\busd\\s*(?:[+\\-\\u2212]\\s*)?\\.?\\d"


def _old_usd_word():
    src = pv.USD_WORD.pattern
    assert src.count(NEW_DIGIT_ARM) == 1 and src.count(NEW_USD_ARM) == 1, src[:160]
    return re.compile(src.replace(NEW_DIGIT_ARM, OLD_DIGIT_ARM).replace(NEW_USD_ARM, OLD_USD_ARM))


OLD_USD_WORD = _old_usd_word()
ALPHABET = ["0", "1", "5", "9", "٣", ",", ".", " ", "\t", " ", "\n", "$", "＄", "﹩", "+", "-",
            "−", "u", "s", "d", "U", "S", "D", "usd", "USD", "dollar", "dollars", "Dollars", "x", "a", "_", "e"]

CURATED = [".5 dollars", ",5 usd", "1,000 USD", "12dollars", "1.5 Dollars", "a1,2.3 usd", "x.5dollars", "..5 usd",
           "5. dollars", "5,, usd", "1 2 usd", "12 usdx", "12 usd_", "$ -  5", "$- .5", "$  +", "$ x5", "＄12", "﹩ −3",
           "usd - .5", "USD5", "usd -", "usdx5", "xusd5", "busd 5", "usd - 5", "٣ dollars", "9 − usd",
           "", "$", "usd", "dollars", "1.2.3.4 dollar", "1,2,3", "1 , 2 usd", "3$", "3 $", "twenty-five dollars"]


@pytest.mark.parametrize("text", CURATED)
def test_960_the_curated_lines_read_as_before(text):
    assert bool(pv.DOLLAR.search(text)) == bool(OLD_DOLLAR.search(text)), text
    assert bool(pv.USD_WORD.search(text)) == bool(OLD_USD_WORD.search(text)), text


def test_960_sixty_thousand_random_lines_read_as_before():
    """A seeded differential test: the new patterns match a line exactly when the old ones did."""
    rng = random.Random(960)
    for _ in range(60000):
        text = "".join(rng.choice(ALPHABET) for _ in range(rng.randint(0, 14)))
        assert bool(pv.DOLLAR.search(text)) == bool(OLD_DOLLAR.search(text)), repr(text)
        assert bool(pv.USD_WORD.search(text)) == bool(OLD_USD_WORD.search(text)), repr(text)


def test_960_the_differential_is_not_vacuous():
    """Both sides of the differential see matches and non-matches, and the old patterns are really the old ones."""
    assert OLD_DOLLAR.pattern != pv.DOLLAR.pattern and OLD_USD_WORD.pattern != pv.USD_WORD.pattern
    assert pv.USD_WORD.search(".5 dollars") and pv.USD_WORD.search("1,000 USD") and pv.USD_WORD.search("usd - .5")
    assert pv.DOLLAR.search("$ - 5") and not pv.DOLLAR.search("$ - x") and not pv.USD_WORD.search("12 usdx")


@pytest.mark.parametrize("name, pattern, text", [
    ("DOLLAR, a sign and 20,000 blanks", "DOLLAR", "$" + " " * 20000 + "x"),
    ("DOLLAR, a sign and 20,000 no-break spaces", "DOLLAR", "＄" + " " * 20000 + "x"),
    ("USD_WORD, 50,000 digits", "USD_WORD", "1" * 50000),
    ("USD_WORD, 25,000 digit-comma pairs", "USD_WORD", "1," * 25000),
    ("USD_WORD, usd and 50,000 blanks", "USD_WORD", "usd" + " " * 50000 + "x"),
])
def test_960_the_measured_inputs_read_in_linear_time(name, pattern, text):
    """The issue's measurements: 5 s, 55 s, 27 s and 36 s before. Each is now well under a second."""
    t0 = time.perf_counter()
    assert getattr(pv, pattern).search(text) is None
    assert time.perf_counter() - t0 < 1.0, name


def test_960_the_guard_reads_the_long_lines_quickly_and_still_refuses_a_figure():
    """Through bulletin_offence, the blank-run lines (the guard's other patterns are linear on them). A long DIGIT run
    is not used here: CONTRACT_COUNT and POOL, outside #960's three, are still quadratic on it (#969)."""
    t0 = time.perf_counter()
    for text in ("$" + " " * 20000 + "x", "usd" + " " * 10000 + "x", "\uff04" + "\u00a0" * 20000):
        assert pv.bulletin_offence(text) is None or "dollar" not in pv.bulletin_offence(text)
    assert time.perf_counter() - t0 < 3.0
    assert pv.bulletin_offence("stake $25 tonight") and pv.bulletin_offence("stake 1,000 USD")
