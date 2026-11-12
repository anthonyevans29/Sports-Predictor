**2026-11-12 — BUILT (#945; ARCHITECT 2026-11-12, addendum 348 item 2 and addendum 354 item 4): the read-only tools to answer what the twenty NCAA "live, resync needed" rows are.**
- **The provider's answer per row:** `dedupe-matches --competition NCAA --orphans --sample 30` prints, on each `[live_resync]` line, what the provider serves (status, code, score, kickoff), from the read it already makes.
- **The rows and their labels:** `scripts/ncaa_live_resync_rows.py --db <copy>` lists them with their CFBD labels and whether each was walked (a current label), on a .backup copy, read-only.
- **No write:** both are reads. The certified count stands; the architect reads both consoles before any resync is ruled.
