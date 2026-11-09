"""ARCHITECT 2026-11-05 09:30 ET, addendum 257 items 1 and 3, in the records PR that carries addendum 256 item 5.

Item 1: "Production is v1.6.4 (docs/RELEASES.md by Code's records PR, the deploy row as the receipt)": the release
record's line and section, read against the tag as git holds it (tag object fbb6e46a on the fold commit 284c5758).
Item 3: lane ncaa's step "the 500th both-FBS regular-season game of 2026 is final and labelled" (due 2026-11-08) is
done-marked 2026-11-05 with the host console's RECEIPT line as its receipt; its what and due unchanged; the 11-09 run
stays on its date. The quoted texts below are the architect's, verbatim."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REL_ROW = ("| `v1.6.4` | 2026-11-05 13:03:31Z | `284c575847379d545408bf88bb3939041e253ad8` | "
           "`fbb6e46a9348d2430b61ab475c3b5faa84b10025` | #837 (step 1 as rewritten, #782) |")

# addendum 257 item 1, verbatim
DEPLOY = ("THE DEPLOY (receipts 14:15Z): v1.6.3 -> v1.6.4 (284c5758, 76 files), the dry run naming exactly "
          "migrate_ncaa_cfbd_pregame.py; the migration by the deploy's printed command under one lock after the backup "
          "sports_2026-11-05_141512.db (integrity ok); four NCAA markers present; the registry on the host carries "
          "nfl-elo-v2 and the four leagues' entries; the rehearsal module present and dormant. Production is v1.6.4 "
          "(docs/RELEASES.md by Code's records PR, the deploy row as the receipt).")
# addendum 255 item 2 (ARCHITECT 2026-11-05 08:05 ET), verbatim
CUT = ("RULING: v1.6.4 is CUT on 87a5766b (the fold commit on it), A MIGRATION TAG: the release block now; the deploy "
       "block in its window (09:15–10:50 ET or 11:15–12:15 ET, never :00–:10); its dry run must name exactly "
       "migrate_ncaa_cfbd_pregame.py and nothing else; the migration by the deploy's own printed command (backup, then "
       "the migration, one lock); the four markers read back. Then the CFBD hand-run block (the first host read; "
       "Sunday's chain repeats it). Then, and only then, #831 by my block when Code names its head.")
# addendum 257 item 2's RECEIPT line, verbatim
RECEIPT = ("RECEIPT 2026: both-FBS completed 505 · joined 505 (100.0%) · same 504 · swapped 1 · neutral 10 · unmatched "
           "0 · ambiguous-refused 0; joined via exact 485, alias 20; scores agree 490 · ours unscored 5 · SCORE-DISAGREE "
           "9 · score-reversed 1.")


def _flat(s: str) -> str:
    return " ".join(s.split())


def test_257_item_1_the_release_row_and_section():
    text = (ROOT / "docs" / "RELEASES.md").read_text(encoding="utf-8")
    table = [ln for ln in text.splitlines() if ln.startswith("| `v")]
    i = table.index(REL_ROW)
    assert "`v1.6.3`" in table[i - 1] and [ln for ln in table if "`v1.6.4`" in ln] == [REL_ROW]
    sec = _flat(text[text.index("- **v1.6.4**"):text.index("## Hotfix path")])
    for verbatim in (DEPLOY, CUT, "ONE compared file, mlb_all_scored.json, 879 = 879 rows, 0 diffs",
                     "No failing row; the release block's awk gate reads 0"):
        assert verbatim in sec, verbatim
    # git's v1.6.3..v1.6.4: sixteen PRs, 83 commits with the fold commit
    assert ("sixteen PRs: #802, #804, #808, #809, #810, #812, #814, #816, #817, #818, #819, #820, #822, #824, #825, "
            "#828 (83 commits with the fold commit; 82 to 87a5766b)") in sec
    assert "the header and all 16 `## ` section headings kept (17 lines beginning with `#`)" in sec


def test_257_item_3_the_500th_game_step_done_its_what_and_due_kept():
    lanes = {ln["lane"]: ln for ln in json.loads((ROOT / "docs" / "roadmap.json").read_text())["lanes"]}
    steps = lanes["ncaa"]["steps"]
    st = steps[3]
    assert st["what"] == ("the 500th both-FBS regular-season game of 2026 is final and labelled (274 were at the run of "
                          "2026-10-09)")
    assert (st["owner"], st["due"]) == ("calendar", "2026-11-08")
    assert st["done"] == {"date": "2026-11-05", "receipt": (
        "the host's first CFBD read, 2026-11-05 14:17Z (ARCHITECT 2026-11-05 09:30 ET, addendum 257 items 2-3; #79 "
        "comment 6660320768): " + RECEIPT)}
    # "The 11-09 run stays on its date and on the LAPTOP" (257 item 3): it ran on its date. ARCHITECT 2026-11-09 09:35 ET,
    # addendum 302 item 3: the 11-09 step done (a done-mark), the two on-PASS steps (11-21, 11-23) cleared by the FAIL and
    # earliest_live 2026-11-24 cleared, by one moved line of 2026-11-09; no date moved on 11-05
    assert [(s["due"], s["done"]["date"]) for s in steps[4:]] == [("2026-11-09", "2026-11-09")]
    assert lanes["ncaa"]["earliest_live"] is None
    assert [(m["moved_on"], m["which"], m["was"], m["now"]) for m in lanes["ncaa"]["moved"]] == [
        ("2026-11-09", "earliest_live", "2026-11-24", None)]
    assert not [m for m in lanes["ncaa"].get("moved", []) if m.get("moved_on") == "2026-11-05"]
