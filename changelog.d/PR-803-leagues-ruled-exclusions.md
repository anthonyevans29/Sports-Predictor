## 2026-11-21 (#PR: 803-leagues-ruled-exclusions — the leagues windows' per-entry list of RULED exclusions the reader honours (ARCHITECT 2026-11-02, addendum 223 item 2(b); built by addendum 442 item 2(a); #803, #322))
- **docs/registry/experiments.json:** each of the five leagues entries (leagues-pd-v1, -sa-v1, -fl1-v1, -elc-v1, -bl1-v1) gains `ruled_exclusions: []`. The list starts empty: "Nothing on the list exists" (#803).
- **src/walters/leagues_window.py:**
  - `ruled_items` validates the list. Each item is exactly `{match_id, kickoff, cause, ruling}`: a match id named once, a UTC instant, and non-empty cause and ruling text.
  - `apply_ruled` checks that each listed game is a stored game of the window (kicking off after the declaration) at exactly the listed kickoff.
  - A malformed item, or one naming no game of the window, refuses the read and the score (law 4).
  - The list clears exactly the refusal 223 item 2(b) built. A listed game with NO stored row, kicking off after the page whose binding carried the entry, is excluded by ruled cause: no slot, never a refusal, counted under `excluded` and listed with its cause and ruling. A no-row game after that page that is NOT listed still refuses.
  - A listed game whose premise does not hold refuses the read (law 4). That is a game that holds its stored row, or item 4(a)'s no-row game before the page. The list never removes a member and never relabels another cause.
  - A listed game that an earlier step excludes or holds pending, or one beyond the 60th member, is named "listed, not applied" with why.
  - A `null` field refuses; only a missing field is the empty list.
  - `read()` and `score()` both honour the list. The score refuses if the entry's list changed since the read. The print and the audit receipt carry their own named line when the list holds an item. An empty list leaves the reader's print, its window and the score byte for byte as before.
- **Tests:** tests/test_803_leagues_ruled_exclusions.py (23), on 223 item 2(b)'s own synthetic SA window:
  - a listed game is excluded and does not refuse (the read, and the score at the 60th);
  - an unlisted game refuses;
  - a malformed item refuses the read and the score (15 cases); a listed game with its row, or before the carrying page, refuses; an item beyond the 60th is named as such; a list changed after the read refuses the score;
  - a listed game under an earlier cause is named, never overridden;
  - the list starts empty, and an empty list changes nothing.

  Nothing run on either machine.
