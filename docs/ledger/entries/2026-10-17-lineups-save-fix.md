**2026-10-17 — sync-lineups-history: `--save` keeps an HTTP error answer's body, and each fixture's rows carry their own time (#565, #571).**
- **Ruling (ARCHITECT 2026-10-17 07:20 ET, addendum 104 item 4), verbatim:** "#565 (--save skips HTTP error answers; refreshed_at once per run): Code may open the fix PR now; nothing in today's receipt changes its scope."
- **Built (#571):**
  - The request wrapper keeps each answer's decoded body whatever its status. The HTTPError branch saves it under `--save`, as `<fixture id>.http<status>.json`, before the run stops or moves on. It is never written over a kept lineup answer.
  - `refreshed_at` is taken per fixture, just before its store.
- **What does not change:** which fixtures are asked, the stop statuses, the receipt, and which rows are written. Only each row's `refreshed_at` value moves: it is now its fixture's own store time.
