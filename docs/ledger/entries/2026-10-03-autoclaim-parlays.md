**2026-10-03 — ARCHITECT: parlay tickets ARE auto-claimed (built); the #208 by-sport split suffices for now; `cryptography` goes into requirements.**
- **Ruling (verbatim):** "(1) parlay tickets ARE auto-claimed on load (one-line change; the ruling's intent was "every call in the file"). (2) #208 by-sport split suffices now; horizon/side/maker splits at the 50-position review. (3) `cryptography` goes into requirements .txt (the signing dependency is real); host probe runs after the next tag. Merge order #259, #260, #261, #256."
- **(1), built:**
  - `snapshotCalls({auto})` now includes `deskParlays`. A ticket's clock is the `desk_parlays` file's `desk_meta.as_of`, falling back to its first leg's file; it sets the log date, the parlay id's date, `captured_at` and the kickoff test. It is still whole ticket or nothing.
  - `autoKey` gains `parlay_id`, because tickets share legs; without it the second ticket's leg would read as "already claimed".
  - Receipt: `cockpit_autoclaim_verify` claims 3 tickets × 2 legs at the parlays file's as_of; a reload claims none.
- **(2), recorded:** horizon / side / maker-taker segments of the P0-3 metrics are deferred to the 50-position review; no change.
- **(3):** added to #260 (the probe PR), so the dependency lands with the code that needs it.
