**2026-11-11 — FINDING FIXED (ARCHITECT 2026-11-11 10:50 ET, addendum 338 items 2-3): a paired window that was not read is never CLEAN; merge blocks stop on an open review thread.**
- **Decision record:** Codex's automatic review of #927 at e52424fb raised a P1. A paired file whose copies lack the declared rows list read CLEAN with no row checked against the window. Code verified it and built the fix on a side branch, leaving the head for the architect's call (337 item 4). The merge block ran before that word was read, and #927 merged with the thread open. The architect recorded it as his own miss ("a condition a block cannot check is not a safeguard"). No harm: no fixtures_NHL pair existed, and nothing on the host runs this comparator before a tag.
- **Corrected:** every merge block reads the PR's review threads and STOPS on any unresolved one.
- **Built:** the fix as ruled (338 item 3).
- **Order (338 item 4):**
  - the laptop's NHL lines join the morning block only after this fix is on main;
  - v1.6.7 carries #913, #916, #919, #918, #922, #923, #925, #927 and this fix, and the tag is ruled after it merges.
