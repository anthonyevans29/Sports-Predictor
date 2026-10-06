**2026-10-05 — RECORDED + RULED (ARCHITECT): first UNL ladders (exploratory) and the frozen favorite-skew test.**
- **Recorded (verbatim):** "first UNL ladders — 17/18 two-sided, 1c spreads, median |book−Kalshi| 2.5pp, max 4.4pp; Kalshi consistently sharper on favorites (+3–4pp on Spain/Albania/Switzerland/England). Record as the venue-eligibility measurement's first 17 games; the 30-game review must test whether the skew is structural (favorite-longshot bias on three-way boards) before any eligibility ruling."
- **Ruled on #286 (verbatim):**
  1. "FREEZE NOW. Test: over the sample, the signed gap (Kalshi − book) on the pre-game favorite; structural skew = bootstrap 95% CI excludes 0. If structural, UNL stays ineligible unless a skew-adjusted rule is declared as a separate candidate. The 17 are EXPLORATORY (their gaps informed the hypothesis); the 30 are a FRESH sample captured after this ruling."
  2. "One-sided boards do not count toward the 30."
  3. "YES — a read-only receipt command printing per-game rows (match, legs, bid/ask, spread, two-sided, capture time, series); its output for the 30 is committed under docs/receipts/ via PR."
  4. "The 17 came from KXUEFANLGAME via operator --series (console line on file). For the fresh 30 the series receipt is required and automatic once #285's default pin is in."
- **So the 17 are EXPLORATORY.** They informed the hypothesis and do not count toward the 30. The 30 are a fresh sample of two-sided boards captured after the ruling.
- **Frozen:** `docs/specs/unl-venue-skew-test.md`.
  - The ruling is quoted verbatim.
  - The operational definitions mirror the Cockpit venue engine: Kalshi three-leg normalized mids vs the last complete pre-kickoff book session, the favorite by book probability, mean signed gap, and a 10,000-resample bootstrap with seed 20261005.
  - Freeze cutoff 2026-10-05T17:00Z.
  - Merging the file is the architect's confirmation of those definitions.
- **Receipt command:** a separate PR.
- **Unchanged:** UNL stays "never" for venue-edge.
