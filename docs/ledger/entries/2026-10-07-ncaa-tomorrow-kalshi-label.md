**2026-10-07 — ncaa-market syncs {tomorrow}; Kalshi syncs name the series they discover (#319).**
- **Ruling (ARCHITECT, verbatim):** "DAILY-CLASS, one PR: a. ncaa-market chain: add the {tomorrow} sync-matches line (kickoffs at 8pm ET or later fall on the next UTC date; the operator block has carried that date by hand since 2026-10-06). b. the Kalshi syncs print "Discovering MLB game series" for every sport: name the series actually being discovered."
- **Built:**
  - `ncaa-market` now runs single-day `sync-matches` NCAA for {yesterday}, {today} and {tomorrow} before `sync-kalshi-ncaa` and the export.
  - `sync_kalshi_mlb` prints "Discovering <series> game series…": the `series_override` ticker, else the adapter's `GAME_SERIES`.
  - docs/CLI.md and hosting-h1 are updated.
- **Effect:** the operator block no longer has to carry the next UTC date by hand. This is data only and changes no policy.
