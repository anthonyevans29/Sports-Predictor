**2026-11-26 — The NBA probe's --document-url guard, built (558 item 4; DEV 4, Lane D; Closes #1155; #1160).**
- **Ruling (557 item 1(d)):** "#1155 is the right home for the round-2 finding. The URL in my block carries no whitespace, so the run does not wait on it." 558 item 4 scheduled its head by Tuesday 2026-12-15 12:00 ET.
- **What landed:** the value stripped once, then parsed and checked inside one guard; the stripped value fetched; the receipt keeps the value as given. A malformed URL behind a leading Unicode space is refused before any request, with its receipt and tail.
- **Next:** the review rounds, then the merge; the run stays the architect's block on the host after the tag.
