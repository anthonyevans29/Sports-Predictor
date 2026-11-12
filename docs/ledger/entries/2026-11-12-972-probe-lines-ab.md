**2026-11-12 — FIXED (#972 items A and B; ARCHITECT 2026-11-12 18:15 ET, addendum 363 items 2 and 6): the NBA injury-report probe's receipt keeps a line's characters.**
- **Ruling (363 item 2):** A, B and C go to #972 unpatched, and none blocks #970. Per 363 item 6, A and B may be taken as ONE small PR (one review round, no adversarial pass beyond the standing two) only when Lane B has nothing else.
- **As built:** text breaks only at CR, LF and CRLF. The control characters VT, \x1c-\x1f and NEL are kept by the folding and trimming; every space still folds as before.
- **The first pass:** the first version folded only HTML whitespace, so NBSP spacers became lines. The first adversarial pass caught it, and it was narrowed to the control characters.
- **Still on #972:** C (the `<meta>` prescan) and the P2 list, to be worked, if at all, after the terms are ruled (363 item 3).
