**2026-11-19 — The UNL venue-country override, PR ONE (addenda 160 item 2, 426 item 5, 427 item 3, 428 item 2(c), 429 item 1; #276, #220; #1055).**
- **Ruling (429 item 1(d)-(f), in part):** "the override inside sync() with derive() the one derivation; intl_venue_resolved untouched and resolve() left as it is; no new column; [...] the dry run by default, --apply with --db refused, the stop above two cohort fixtures [...] BUILD: PR ONE first, then PR TWO".
- **The table:** 2618 -> Andorra (ARCHITECT 2026-10-23, 160 item 2); 3989 -> Spain (ARCHITECT 2026-11-19, 428 item 2(c), replacing "unknown"). Each entry is one line with its ruling, date and evidence.
- **Found by my review before the push:**
  - **P1, its settlement for the architect to confirm on #1055:** the daily sync would have applied the override to stored rows before the architect's --apply, with no receipt and no stop. Built instead: the first change of a stored flag is --apply's alone, and after it the daily run keeps it.
  - **P2:** the dry run now reads mode=ro and never creates a database.
- **Next:** the architect's blocks. First `--provider-check`, then the dry run on the pulled copy (expected 33 changes, 0 cohort fixtures), then `--apply` on the host after a tag that carries it. PR TWO (the provenance receipt and the read both ways, #336) follows.
