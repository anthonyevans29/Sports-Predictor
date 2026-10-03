## 2026-10-03 (#265: NCAA re-key receipt: why `dedupe-matches --apply` found 0 pairs)
- **`scripts/ncaa_rekey_receipt.py`** (read-only; opens the DB with `mode=ro`, writes nothing). It prints:
  - rows re-keyed in place, and the source-id classes (22xxx old vs 23xxx/24xxx new);
  - the natural-key clusters under `find_pairs`' own rules: mergeable / SAME id / missing id / 3+ rows, so a 0 is explained rather than assumed;
  - rows with no twin, with stale SCHEDULED orphans counted;
  - export-window rows vs distinct games, flagging duplicates still in the window;
  - per-id rows (ext ids, `_prev`, status, odds and snapshot counts);
  - `--game "Away@Home"` rows, with `--resolve` looking each row's id up at the provider (GET `/games?id=`, `/odds?game=`; the key is never printed).
- tests/test_ncaa_rekey_receipt.py (1).
