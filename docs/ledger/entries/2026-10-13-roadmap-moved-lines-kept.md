**2026-10-13 — RULED + BUILT (ARCHITECT 2026-10-13 16:37 ET, addendum 62 items 3 and 4): the base's moved lines stay on the head (#504); the roadmap's first done step. PR #506.**
- **#504, ruled in (item 3, verbatim):** "Every moved line the base holds is on the head, word for word, and in the base's order; the head only appends. A moved line changed or removed fails the pull request, and the refusal names the lane and the line. A lane only one side holds needs nothing from this: the ruling the pull request quotes carries it, and I read it."
  - Why: "'The earlier date is never erased' (addendum 59 item 5(d)) is a sentence about the record, and the record is the moved list. Addendum 60 item 3 named the dates and left the list to my read; the list is checkable, so the check reads it."
  - The finding was Codex's P1 on #503, escalated as #504 and not acted on until this ruling.
- **Item 4 (verbatim):** "docs/roadmap.json, lane nfl-qb, its first step ('a read-only probe of the provider's quarterback data: its PR open, its checks green (see (h))'): done on 2026-10-13, receipt 'PR #489 merged at 7e6e88c'. No date moves. The print then reads the lane's next step as the operator's run, due 2026-10-23."
- **As built:**
  - `_kept_lines` in `check_moves`: each base moved line at its own place on the head, word for word. Otherwise the check fails, naming the lane, the line's number and its parts: changed or removed, or out of the base's order.
  - nfl-qb step 1 carries its done date and receipt. This PR's own check-roadmap passes: no date moved.
- Closes #504.
