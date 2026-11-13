"""THE CLASS CLOSED (#979; ARCHITECT 2026-11-13 09:00 ET, addendum 364 item 2, verbatim: "AND THE CLASS IS CLOSED IN IT,
since this is the third sample: one test that takes EVERY compiled pattern in src/privacy_patterns.py, by reading the
module and not by a list of names, and runs each against your 34 shapes at a size that separates linear from
quadratic, under one bound — so a pattern added next month is held to it without anyone remembering to add it").

The patterns are read from the module, not named here: every re.Pattern the module holds, and every pattern it builds
inside a function, found by reading its source. A pattern the source builds at call time from anything but a string
literal cannot be held to the bound, so it fails here until it is a module-level name; so does re itself, or one of its
pattern functions, held under another name (an alias, getattr, lru_cache(re.compile)), since a call through it could
not be read. The shapes are the 33 of #979's scan (the Issue said 34: a miscount), three found while building #979's PR
and four its review found. Each pattern reads each shape through finditer (the most any caller asks: search, sub and
split read no more) at 2,000, 10,000 and 50,000 characters, under ONE bound, 20 microseconds a character: a linear
pattern here reads a character in about one microsecond at most; the quadratic reads #960, #969 and #979 fixed took
50 to 90 microseconds a character at 2,000 to 10,000 characters, more the longer the line. Each pattern reads in a
child process, and each read there has a deadline (ten times its bound and a second): an exponential pattern, which
would never finish a read, fails naming its shape instead of hanging the run."""
import ast
import json
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

import src.privacy_patterns as pv

BOUND_PER_CHAR = 20e-6
SIZES = (2_000, 10_000, 50_000)
DEADLINE_FACTOR, DEADLINE_SLACK = 10, 1.0
ROOT = Path(__file__).resolve().parent.parent
_RE_CALLS = {"compile", "search", "match", "fullmatch", "sub", "subn", "split", "findall", "finditer"}

SHAPES = {
    # #979's scan, the 33 shapes
    "digits": lambda n: "1" * n, "digit-comma": lambda n: "1," * (n // 2), "digit-point": lambda n: "1." * (n // 2),
    "arabic": lambda n: "\u0663" * n, "blanks+x": lambda n: " " * n + "x", "1+blanks+x": lambda n: "1" + " " * n + "x",
    "underscores": lambda n: "_" * n, "a_ runs": lambda n: "a_" * (n // 2), "contract_": lambda n: "contract_" * (n // 9),
    "fraction_": lambda n: "fraction_" * (n // 9), "letters": lambda n: "a" * n, "commas": lambda n: "," * n,
    "a,": lambda n: "a," * (n // 2), "1,a,": lambda n: "1,a," * (n // 4), "semicolons": lambda n: "a;" * (n // 2),
    "pipes": lambda n: "a|" * (n // 2), "tabs": lambda n: "a\t" * (n // 2), "words": lambda n: "ab " * (n // 3),
    "dashes": lambda n: "-" * n, "twenty-": lambda n: "twenty-" * (n // 7), "dollar ": lambda n: "dollar " * (n // 7),
    "pool ": lambda n: "pool " * (n // 5), "usd ": lambda n: "usd " * (n // 4), "$ ": lambda n: "$ " * (n // 2),
    "x1 ": lambda n: "x1 " * (n // 3), "@ ": lambda n: "@ 1 " * (n // 4), "quotes": lambda n: '"a":' * (n // 4),
    "key=": lambda n: "key=" * (n // 4), "api key ": lambda n: "api key " * (n // 8), "hex": lambda n: "ab12" * (n // 4),
    "b64": lambda n: "Ab1+" * (n // 4), "url-ish": lambda n: "a/" * (n // 2), "colons": lambda n: "a:" * (n // 2),
    # found while building #979's PR: a field and a run of tabs (CSV_RUN's delimiter, quadratic before), and upper case
    "field+tabs": lambda n: "a" + "\t" * n + "!", "field+space-tabs": lambda n: "a" + " \t" * (n // 2) + "!",
    "upper-case": lambda n: "A" * n,
    # found by #979's review: blanks before a delimiter that are only spaces (a field, or a field and a comma, and a
    # run of spaces), and FRACTION's digit-led start (a digit, an underscore or not, and a run of letters)
    "field+spaces": lambda n: "a" + " " * n + "!", "field,+spaces": lambda n: "a," + " " * n + "!",
    "1_+letters": lambda n: "1_" + "a" * n, "1+letters": lambda n: "1" + "a" * n,
}


def _flags(node):
    """A flags argument the source spells as re.NAME, or re.NAME | re.NAME."""
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "re":
        return getattr(re, node.attr)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _flags(node.left) | _flags(node.right)
    raise AssertionError(f"line {node.lineno}: flags the test cannot read: {ast.dump(node)}")


def module_patterns():
    """Every compiled pattern src/privacy_patterns.py holds or builds, by reading the module: the re.Pattern values it
    holds, and each pattern its source passes to re.* (a module-level NAME = re.compile(...) is one it holds)."""
    found = {name: p for name, p in vars(pv).items() if isinstance(p, re.Pattern)}
    tree = ast.parse(Path(pv.__file__).read_text(encoding="utf-8"))
    held = {}
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
            held[id(stmt.value)] = [t.id for t in stmt.targets if isinstance(t, ast.Name)]
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.value, ast.Call) and isinstance(stmt.target, ast.Name):
            held[id(stmt.value)] = [stmt.target.id]
    parent = {id(child): node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "re":
            up = parent.get(id(node))
            assert isinstance(up, ast.Attribute) and up.value is node, (
                f"line {node.lineno}: re itself is passed on (getattr, an alias); this test cannot read its calls")
            if up.attr in _RE_CALLS:
                call = parent.get(id(up))
                assert isinstance(call, ast.Call) and call.func is up, (
                    f"line {node.lineno}: re.{up.attr} is held under another name (an alias, lru_cache); call it as "
                    f"re.{up.attr}(...) so this test can read the pattern")
        if isinstance(node, ast.ImportFrom):
            assert node.module != "re", f"line {node.lineno}: names imported from re are not read by this test"
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "re" or alias.asname is None, f"line {node.lineno}: re under another name"
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "re"
                and node.func.attr in _RE_CALLS):
            continue
        if node.func.attr == "compile" and id(node) in held:
            names = held[id(node)]
            assert names and all(n in found for n in names), (node.lineno, names)
            continue
        arg = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg == "pattern"), None)
        assert isinstance(arg, ast.Constant) and isinstance(arg.value, str), (
            f"line {node.lineno}: re.{node.func.attr} builds its pattern at call time; name it at module level so "
            f"this test can hold it to the bound")
        flags = 0
        if node.func.attr == "compile" and len(node.args) > 1:
            flags = _flags(node.args[1])
        for k in node.keywords:
            if k.arg == "flags":
                flags = _flags(k.value)
        key = f"line {node.lineno} col {node.col_offset}: re.{node.func.attr}"
        assert key not in found, key
        found[key] = re.compile(arg.value, flags)
    return found


PATTERNS = module_patterns()


def _elapsed(pattern, text):
    t0 = time.perf_counter()
    for _ in pattern.finditer(text):
        pass
    return time.perf_counter() - t0


def _read(pattern, text, bound):
    """One read under its deadline: past it the child process ends (SIGALRM's default action), since a regular
    expression read cannot be interrupted from Python while it runs."""
    if hasattr(signal, "setitimer"):
        signal.setitimer(signal.ITIMER_REAL, DEADLINE_FACTOR * bound + DEADLINE_SLACK)
    t = _elapsed(pattern, text)
    if hasattr(signal, "setitimer"):
        signal.setitimer(signal.ITIMER_REAL, 0)
    return t


def child(pattern):
    """In the child: each shape the pattern reads over the bound, at the first size it does (a retry or two first: a
    pause is not a quadratic read). Each read is announced first, so a read past its deadline is named."""
    if hasattr(signal, "SIGALRM"):
        signal.signal(signal.SIGALRM, signal.SIG_DFL)
    for shape, make in SHAPES.items():
        for n in SIZES:
            text = make(n)
            bound = BOUND_PER_CHAR * len(text)
            print(json.dumps({"reading": f"{shape} at {len(text):,} characters"}), flush=True)
            t = _read(pattern, text, bound)
            if t > bound:
                t = min(t, _read(pattern, text, bound), _read(pattern, text, bound))
            if t > bound:
                print(json.dumps({"slow": f"{shape} at {len(text):,} characters: {t:.3f} s (bound {bound:.3f} s)"}),
                      flush=True)
                break


_CHILD = """import re, sys
sys.path.insert(0, sys.argv[1])
import tests.test_privacy_patterns_linear as t
if sys.argv[2] == "name":
    t.child(t.module_patterns()[sys.argv[3]])
else:
    t.child(re.compile(sys.argv[3], int(sys.argv[4])))
"""


def slow_reads(*how, timeout=900):
    """Run the reads in a child process: ("name", NAME) for a pattern of the module, ("source", PATTERN, FLAGS) for
    another. Returns each read over its bound, or the read the child was killed in."""
    try:
        proc = subprocess.run([sys.executable, "-c", _CHILD, str(ROOT), *map(str, how)], capture_output=True,
                              text=True, timeout=timeout, cwd=ROOT)
        out, code = proc.stdout, proc.returncode
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        code = "timeout"
    lines = [json.loads(line) for line in out.splitlines() if line.startswith("{")]
    slow = [line["slow"] for line in lines if "slow" in line]
    if code != 0:
        last = next((line["reading"] for line in reversed(lines) if "reading" in line), "before any read")
        if hasattr(signal, "SIGALRM") and code == -signal.SIGALRM:
            slow.append(f"{last}: past its deadline ({DEADLINE_FACTOR} times its bound and {DEADLINE_SLACK:g} s)")
        else:
            slow.append(f"{last}: the child ended with {code}: {proc.stderr[-2000:] if code != 'timeout' else ''}")
    return slow


def test_the_module_is_read_not_listed():
    """Every pattern the guard and the #817 test use is among those read, and so are the two built inside functions."""
    for name in ("UUID", "TICKER", "CSV_RUN", "DOLLAR", "CONTRACT_COUNT", "ORDER_TEXT", "UNIT_LABEL", "FRACTION",
                 "POOL", "FIELD_NAME", "USD_WORD", "_TAG", "_OPEN_TAG", "_CLOSE_TAG", "_MD_AUTOLINK"):
        assert PATTERNS[name] is getattr(pv, name)
    inline = sorted(p.pattern for name, p in PATTERNS.items() if name.startswith("line "))
    assert inline == ["[,\\u241f\\t;|]", "\\s+"], inline
    assert len(SHAPES) == 40


@pytest.mark.parametrize("name", sorted(PATTERNS))
def test_every_pattern_reads_every_shape_in_linear_time(name):
    slow = slow_reads("name", name)
    assert not slow, f"{name} is super-linear: " + "; ".join(slow)


def test_the_bound_separates_the_reads_this_class_fixed():
    """The harness is not vacuous: main's CSV_RUN and FRACTION before #979 read over the bound."""
    field = r'"?[A-Za-z_][A-Za-z0-9_]*"?'
    old_csv = re.compile(field + r"(?:[ \t]*[,\u241f\t;|][ \t]*" + field + r")+")
    old_fraction = re.compile("(?i)(?<![a-z0-9])[a-z_]*fraction(?![a-z0-9])[\"']?\\W{0,4}[+\\-]?\\.?\\d"
                              "|\\bhalf_fraction\\b")
    for pattern, shape in ((old_csv, "letters"), (old_csv, "field+tabs"), (old_fraction, "underscores")):
        text = SHAPES[shape](10_000)
        assert _elapsed(pattern, text) > BOUND_PER_CHAR * len(text), shape


@pytest.mark.skipif(not hasattr(signal, "setitimer"), reason="the per-read deadline needs setitimer")
def test_an_exponential_pattern_fails_naming_its_read_and_does_not_hang():
    """(?:a|a?)+b took 8.8 s on 24 letters (#979's review): on 2,000 letters it would never finish. It fails at its
    deadline, naming the shape."""
    t0 = time.perf_counter()
    slow = slow_reads("source", "(?:a|a?)+b", 0, timeout=120)
    assert any(s.startswith("letters at 2,000 characters: past its deadline") for s in slow), slow
    assert time.perf_counter() - t0 < 60
