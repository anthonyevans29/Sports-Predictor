## 2026-11-21 (#PR: 803-leagues-ruled-exclusions — the leagues windows' per-entry list of RULED exclusions the reader honours (ARCHITECT 2026-11-02, addendum 223 item 2(b); built by addendum 442 item 2(a); #803, #322))
- **docs/registry/experiments.json:** each of the five leagues entries (leagues-pd-v1, -sa-v1, -fl1-v1, -elc-v1, -bl1-v1) gains `ruled_exclusions: []`. The list starts empty: "Nothing on the list exists" (#803).
- **src/walters/leagues_window.py:**
  - `ruled_items` validates the list. Each item is exactly `{match_id, kickoff, cause, ruling}`: a match id named once, a UTC instant, and non-empty cause and ruling text.
  - `apply_ruled` checks that each listed game is a stored game of the window (kicking off after the declaration) at exactly the listed kickoff.
  - A malformed item, or one naming no game of the window, refuses the read and the score (law 4).
  - `membership` excludes a listed game by ruled cause when it reaches the stored-row step: no slot, never a refusal, counted under `excluded` and listed with its cause and ruling. A no-row game after a page that carried the entry and is NOT listed still refuses (223 item 2(b)).
  - A listed game that an earlier step excludes or holds pending is named "listed, not applied". The list never overrides another cause.
  - `read()` and `score()` both honour the list; the score re-reads the entry. The print and the audit receipt carry their own named line when the list holds an item. An empty list leaves the reader's print, its window and the score byte for byte as before.
- **Tests:** tests/test_803_leagues_ruled_exclusions.py (15), on 223 item 2(b)'s own synthetic SA window:
  - a listed game is excluded and does not refuse (the read, and the score at the 60th);
  - an unlisted game refuses;
  - a malformed item refuses the read and the score (11 cases);
  - a listed game under an earlier cause is named, never overridden;
  - the list starts empty, and an empty list changes nothing.

  Nothing run on either machine.
