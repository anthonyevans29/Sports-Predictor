**2026-11-12 — RECORDED (ARCHITECT 2026-11-12 16:00 ET, addendum 360 item 5): the release record now follows the host the same day.**
- **The finding:** docs/RELEASES.md said `sp-availability-observe.timer` "stays disabled until its own block", and hosting-h1.md gave only the block's recipe. A reader of the public repo concluded the NHL watch was not collecting.
- **The facts now recorded:**
  - The timer has been enabled on the host since 15:23–15:25Z, by the architect's block (354 item 1). The first tick, at 15:25:02Z, wrote observation #5. The timer set read CLEAN at 21.
  - The first fixtures_NHL pair under v1.6.7's comparator read CLEAN on the host's 16:00:38Z push (355).
- **Where:** v1.6.7's "After the tag" in docs/RELEASES.md, and a line under the recipe in hosting-h1.md.
- **The rule, verbatim (360 item 5):** "The record follows the host the same day, not at the next tag."
