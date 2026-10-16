"""tests/ledger_text.py: a quoted ledger entry is read from its fragment until the tag ritual's compile folds it into
BACKLOG.md, then from its block there (c546168, the v1.4.0 commit of ARCHITECT 2026-10-16 addendum 84, failed three
tests that read a folded fragment's file). And no test reads a fragment file directly any more."""
import re
from pathlib import Path

import pytest

from ledger_text import entry_text, flat

HEAD = "**2026-10-08 — DECLARATION (ARCHITECT, addendum 11): x declared**"
ENTRY = f"{HEAD}\n- **Declaration (RULED, verbatim):**\n  - \"D1. a ruling\n    wrapped\"\n- Done: the entry.\n"


def _root(tmp_path, fragment: bool, backlog: str):
    (tmp_path / "docs" / "ledger" / "entries").mkdir(parents=True)
    if fragment:
        (tmp_path / "docs" / "ledger" / "entries" / "2026-10-08-x.md").write_text(ENTRY)
    (tmp_path / "BACKLOG.md").write_text(backlog)
    return tmp_path


def test_the_fragment_is_read_while_it_exists(tmp_path):
    root = _root(tmp_path, True, "# BACKLOG\n\n### MLB / baseball\n\n")
    assert entry_text("2026-10-08-x", HEAD[:30], root) == ENTRY


def test_after_the_compile_the_folded_block_is_read_up_to_the_next_heading(tmp_path):
    """The compile inserts each entry verbatim after the anchor, newest first (ledger_fragments.compile_fragments)."""
    later = "**2026-10-09 — RULED: a later entry.**\n- its line.\n"
    backlog = f"# BACKLOG\n\n### MLB / baseball\n\n{later}\n{ENTRY}\n**2026-10-07 — an older one.**\n- x\n\n### NFL\n"
    root = _root(tmp_path, False, backlog)
    got = entry_text("2026-10-08-x", HEAD[:30], root)
    assert got.strip() == ENTRY.strip() and "later entry" not in got and "older one" not in got
    assert flat(got).endswith("Done: the entry.") and '"D1. a ruling wrapped"' in flat(got)
    last = f"# BACKLOG\n\n### MLB / baseball\n\n{ENTRY}\n### NFL\n- not the entry\n"
    assert entry_text("2026-10-08-x", HEAD[:30], _root(tmp_path / "b", False, last)).strip() == ENTRY.strip()


@pytest.mark.parametrize("backlog", ["# BACKLOG\n", f"{ENTRY}\n{ENTRY}"])
def test_a_missing_or_doubled_heading_fails_loudly(tmp_path, backlog):
    with pytest.raises(AssertionError, match="neither docs/ledger/entries/2026-10-08-x.md nor exactly one"):
        entry_text("2026-10-08-x", HEAD[:30], _root(tmp_path, False, backlog))


def test_no_test_reads_a_fragment_file_directly():
    """A fragment is deleted by the compile the tag is cut on: tests quote entries through ledger_text only (the
    fragments' own checker, test_ledger_fragments.py, builds its own in a tmp root)."""
    here = Path(__file__).resolve().parent
    pat = re.compile(r"ledger[\"' ,/]+entries|changelog\.d")
    offenders = [p.name for p in sorted(here.glob("*.py"))
                 if p.name not in ("ledger_text.py", "test_ledger_text.py", "test_ledger_fragments.py")
                 and pat.search(p.read_text())]
    assert offenders == []
