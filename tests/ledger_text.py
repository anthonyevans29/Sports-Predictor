"""The text of one ledger entry, wherever the ledger keeps it (a helper for tests that quote a ruling verbatim).

A PR adds its BACKLOG entry as a fragment, docs/ledger/entries/<date>-<slug>.md (ARCHITECT-RULE 2026-10-02). The tag
ritual's compile (scripts/ledger_fragments.compile_fragments) folds every fragment into BACKLOG.md verbatim and
deletes the file. A test that reads the fragment file breaks on the compile commit, which is what the tag is cut on:
c546168 (v1.4.0, ARCHITECT 2026-10-16, addendum 84) failed three such tests. This reads the fragment while it exists,
and after the compile reads the entry's block in BACKLOG.md: from its heading line (each entry opens with
"**YYYY-MM-DD — ...") to the next entry's heading or the next section heading."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRIES = ROOT / "docs" / "ledger" / "entries"
BACKLOG = ROOT / "BACKLOG.md"
_NEXT = re.compile(r"^(?:\*\*\d{4}-\d{2}-\d{2} |#{1,6} )", re.M)


def entry_text(name: str, heading: str, root: Path = ROOT) -> str:
    """The entry `name` (its fragment's file name without .md) while it is a fragment; once folded, its block in
    BACKLOG.md, found by the start of its heading line (`heading`, which must occur there exactly once)."""
    frag = root / "docs" / "ledger" / "entries" / f"{name}.md"
    if frag.exists():
        return frag.read_text()
    backlog = (root / "BACKLOG.md").read_text()
    starts = [m.start() for m in re.finditer(r"^" + re.escape(heading), backlog, re.M)]
    if len(starts) != 1:
        raise AssertionError(f"ledger entry {name}: neither {frag.relative_to(root)} nor exactly one BACKLOG.md "
                             f"heading starting {heading!r} (found {len(starts)})")
    nxt = _NEXT.search(backlog, starts[0] + 1)
    return backlog[starts[0]:nxt.start() if nxt else len(backlog)]


def flat(text: str) -> str:
    """Line wrapping never changes a word."""
    return " ".join(text.split())
