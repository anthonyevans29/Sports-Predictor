## 2026-11-23 (#000: 480-unl-moved-lines — lane unl's record and earliest_live move to 2027-02-05, three steps appended before the record (addendum 480 item 3))
- **docs/roadmap.json, lane unl (#220):**
  - Item 3(c)'s three steps are appended before the record step: the override table's lines ruled (architect, 2027-01-08); PR ONE (#1055) rebuilt on the ruled table (code, 2027-01-22); PR TWO (#336), the provenance receipt and the read both ways (code, 2027-01-29).
  - The confirmation record step and earliest_live move from 2026-12-01 to 2027-02-05 (3(a), 3(b)), with two moved lines quoting 3(d).
- **tests/test_roadmap.py:** the vehicle test `test_one_moved_line_records_one_move` takes its new date 30 days after lane unl's earliest_live, not a fixed 2026-11-20, so the appended 2027 steps keep its dues forward. What it pins is unchanged.
- The venue derivation's source is ruled (480 items 1 and 2): a ruled table keyed by the provider's venue id. Recorded here, built later.
- Nothing here moves a bar or changes a prediction output. The frozen cohort, the bar and the read are untouched.
