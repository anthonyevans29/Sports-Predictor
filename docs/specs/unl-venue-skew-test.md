# UNL venue-eligibility: the favorite-skew test (FROZEN, 2026-10-05)

Status: **FROZEN on merge.** Written before any game of the sample exists
(law 3). Never edited after the first sample game is read. A change is a new
version with its own fresh sample.

## Rulings (ARCHITECT 2026-10-05, verbatim)

> 1. FREEZE NOW. Test: over the sample, the signed gap (Kalshi − book) on the
>    pre-game favorite; structural skew = bootstrap 95% CI excludes 0. If
>    structural, UNL stays ineligible unless a skew-adjusted rule is declared
>    as a separate candidate. The 17 are EXPLORATORY (their gaps informed the
>    hypothesis); the 30 are a FRESH sample captured after this ruling.
> 2. One-sided boards do not count toward the 30.
> 3. YES — a read-only receipt command printing per-game rows (match, legs,
>    bid/ask, spread, two-sided, capture time, series); its output for the 30
>    is committed under docs/receipts/ via PR.
> 4. The 17 came from KXUEFANLGAME via operator --series (console line on
>    file). For the fresh 30 the series receipt is required and automatic
>    once #285's default pin is in.

## Operational definitions

These were written by Claude Code to make the ruling executable. They mirror
the Cockpit venue engine's book-vs-Kalshi comparison. Merging this file is
the architect's confirmation; anything the architect changes is changed
before merge.

- **Sample:** UNL (competition code `UNL`) games meeting all of:
  - kickoff after the freeze cutoff `2026-10-05T17:00:00Z`;
  - a qualifying Kalshi capture taken after that cutoff;
  - a qualifying book session.

  The sample is the FIRST 30 such games in kickoff order (ties by match id).
  Games that fail any criterion are listed in the receipt, with the reason,
  and do not count.
- **Qualifying Kalshi capture:** the LAST pre-kickoff Kalshi capture
  (`odds_snapshots`, `source = kalshi`) in which all three legs (HOME, DRAW,
  AWAY) carry both a yes bid and a yes ask, with the same `captured_at`.
  - Every leg's ticker must belong to series `KXUEFANLGAME`; the series is
    shown on every receipt row.
  - A board with any one-sided or missing leg at that capture does not count
    (ruling 2). An earlier two-sided capture is never substituted.
- **Kalshi probability:** per leg, mid = (bid + ask) / 2. The three mids are
  normalized to sum to 1 (the Cockpit's `kalNormalize` over three legs).
- **Book probability:** the LAST pre-kickoff complete book-consensus session.
  - Source: `odds_snapshots`, non-Kalshi, market `1X2`, all three outcomes at
    one `captured_at`, de-vigged `devig_prob` normalized to 1.
  - The `close_from_snapshots` contract applies (an incomplete session is
    never a price).
- **Pre-game favorite:** the outcome (HOME, DRAW or AWAY) with the highest
  book probability. If two outcomes tie to 4 decimals, the game is excluded
  (listed).
- **Statistic:** per game, gap = Kalshi probability − book probability, both
  on the favorite, in percentage points. The test statistic is the mean gap
  over the 30.
- **Bootstrap:** resample the 30 games with replacement.
  - B = 10,000 resamples, seed 20261005.
  - The 95% CI is the 2.5th and 97.5th percentiles of the resampled means.
- **Verdict:**
  - **STRUCTURAL** if the 95% CI excludes 0, with the sign reported. UNL then
    stays ineligible for venue-edge unless a skew-adjusted rule is declared
    as a separate candidate.
  - **NOT STRUCTURAL** otherwise. The architect then rules on eligibility;
    the verdict is never automatic.
- **Exploratory cohort:** the 17 games recorded 2026-10-05 (from
  KXUEFANLGAME via operator `--series`) informed this hypothesis. They are
  never part of the sample.

## Receipt

The 30-game receipt (ruling 3) is the read-only receipt command's output for
the sample: per game, the match, each leg's bid/ask, spread, two-sidedness,
capture time and series, plus the book probability and gap above. It is
committed under `docs/receipts/` via PR, with the test result.
