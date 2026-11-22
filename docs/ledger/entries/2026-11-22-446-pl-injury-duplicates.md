**2026-11-22 — The PL injury duplicate receipt, read-only tooling (addendum 446 item 1; Refs #1052).**
- **Order (446 item 1), verbatim:**
  > 1. ONE PLAYER LISTED TWICE IN A SIDE'S INJURY LIST. Chelsea's list on the slate and on the 15:00Z closing
  >    page holds seven names, and two pairs are one player each under two spellings: one name with and
  >    without its accent, and one double surname beside its short form (the names stay off the public
  >    record; they are on the page). The row's home_injuries_count reads 7 where five players are listed.
  >    That count is an input of v22's injury factor, so Chelsea was marked down for seven. The Desk's
  >    call was PASS (the pick under the probability floor), so no call rested on it.
  >    THE RECEIPT, read-only, on the host's pulled copy and the mirror's pages: for every Premier League
  >    closing row of 2026/27, each side's entries, its distinct players by the source's own player id,
  >    and the pairs that are the same person by name once accents and a double surname are folded; how
  >    many rows and sides carry such a pair; and whether the two entries of a pair carry two source ids
  >    or one. Counts and the rule you used. I rule on the receipt; nothing is de-duplicated before that.
- **What landed:**
  - `scripts/pl_injury_duplicate_receipt.py`, with 48 tests.
  - The rule, declared before any result: #688's `tokens()`, pairs within one side of one row only, the kinds `accent` and `double surname` in the headline, `identical` counted, `initial form` apart, and AMBIGUOUS never paired.
  - A side above 8 entries is counted as names cut.
  - "Two source ids or one" reads UNKNOWN: the page carries no id, and the soccer adapter never reads `player.id` (api_football.py:460-475). The copy's PRAGMA result is printed.
  - No player name is printed.
- **Next:** the architect's block runs it on the host's pulled copy and the pages. He rules on the receipt; nothing is de-duplicated before that.
