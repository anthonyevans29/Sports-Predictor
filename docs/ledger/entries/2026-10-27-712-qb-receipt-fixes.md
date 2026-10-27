**2026-10-27 — BUILT (ARCHITECT 2026-10-27 13:45 ET, #712 items 1-3): the QB receipts' field line, dropped finished games and failed live reads, fixed before the receipts run. No bar moves.**
- **The ruling, verbatim:** "#712 items 1–3 (a field absent for a whole season shown on the field line; parser-dropped finished games make the gate line INCOMPLETE; a failed live read in the injury receipt counted as failed, never empty) are fixed in ONE small PR before the receipt runs — they decide the sack-yards formula and the gate line, so the receipts are not run without them. Items 4 and 5 are declaration text for 11-02; leave them on #712."
- **Item 1:**
  - The F line lists the field universe: every passing field any season of the run sends.
  - **Read for the architect:** the provider's exact field names are not in the repository; the probe's console stays on the laptop. A field that NO season sends cannot be named, so none is seeded by a guessed name (law 1).
  - The receipt says so on its header line. Sack yards are read from the fields listed.
- **Item 2:** "finished" is the adapter's own reading: its status map's FINISHED shorts (FT, AOT), or its score-presence rule. All-star exhibitions are the adapter's own exclusion (`_non_competitive`), counted apart and never a gap. A dropped row not marked finished is neither.
- **Item 3:** every live read (/teams, roster, injuries) is answered only as HTTP 200 with no errors. On #710's code, a 503 with an empty errors object read as "teams answering empty 1 · rosters empty 1"; the new test pins it as two failed reads.
