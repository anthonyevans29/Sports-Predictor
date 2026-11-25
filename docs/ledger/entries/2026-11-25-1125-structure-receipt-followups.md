**2026-11-25 — #1124's review-round-2 findings fixed in one small PR, with #1126's index line (addendum 525 item 3(c); #1125; DEV 4, Lane D; #1129).**
- **Ruling (525 item 3(c)):** "#1125's THREE DO NOT BLOCK, as you placed them. Fix them in one small PR after #1124 is on main, with #1126's index line in scripts/README.md, a head by Friday 2026-12-04."
- **What landed:**
  - the file structure receipt reads a float exponent past decimal's limit as data;
  - it reads an ISO timestamp with more than six fractional digits as a datetime, ordered exactly;
  - #1124's fragment test count is corrected to 69;
  - scripts/README.md indexes the NHL cohort count.
- Nothing was run on a real file. No model, no figure, no bar.
