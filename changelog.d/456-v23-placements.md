## 2026-11-23 (#PR: 456-v23-placements — soccer-v23's ruled stage placements (ARCHITECT 2026-11-23 09:26 ET, addendum 456 items 3-5; GATE-CLASS; lane soccer-v23, #656))
- **src/walters/soccer_v23.py:**
  - `RULED_PLACEMENTS` holds exactly items 4(a)-(d), each with its item number, keyed by (competition code, label form: the label without its " - N"):
    - "Championship Group" is play-off in AUT, BEL, CZE, GRE, SCO and SUI;
    - "Conference League Group" is play-off in BEL and GRE;
    - "1st Phase" is regular in SCO;
    - "2nd Phase" is play-off in SCO.
  - `placement_with_source` asks `soccer_expansion.placement` first and reads the table only where it returns nothing. A ruled form in a competition not named beside it, or any other form, stays unplaced and refuses (item 4(e)).
  - One function, `placement_of`, serves the four call sites: `in_scope`, `_first_season_census`, `stage_census` and `scored_rows`. The replay and the live path go through it alike.
  - The preflight and the run record mark every label the table places "by ruling 456" with its count (item 5(d)): `stage_census`'s `ruled`, `ruled_placement_census`, one console line, and the record's `placed_by_ruling_456`.
  - The record also carries the table's sha256 (`ruled_placements_sha256`).
- **Unchanged (item 5(c)):** soccer_expansion.py, `code_constants()`, the entry and BAR_TEXT (sha256 `d4778a27…`).
- **Line citation:** the fingerprint check's `soccer_v23.py:NNNN` citation is re-pointed to :1999 in the run docstring, the spec and docs/CLI.md.
- **Tests:** tests/test_456_v23_placements.py (32):
  - each ruled pair;
  - a ruled form in another competition refuses;
  - an unruled form refuses;
  - the code's own answer wins;
  - Scotland's first season in scope is 2024/25 on a synthetic store, and 2026/27 without the ruling;
  - item 5(b)'s pin on `soccer_expansion.placement`;
  - the marks;
  - the table is not a constant.
  - Two harness expectations follow the census's new key and the new console line.
- **The spec:** question 16 carries 456 whole. 263 item 16's answer is kept and marked amended for this case. The CLI.md row names the table.

  Nothing of soccer-v23 run on real data; no prediction output changes.
