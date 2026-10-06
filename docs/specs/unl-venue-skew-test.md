# UNL venue-eligibility: the favorite-skew test (v2, RATIFIED 2026-10-06)

Status: **v2 FROZEN on merge.** v1 (2026-10-05) was frozen before its
definitions were ratified. The architect ratified all ten open definition
findings on 2026-10-06 and moved the freeze cutoff to the ratification time,
so v2 has its own fresh sample (law 3). Never edited after the first sample
game is read. A change is a new version with its own fresh sample.

## Rulings (ARCHITECT 2026-10-06 on #286, verbatim)

> ALL TEN RATIFIED as recommended — (1) exclude the exploratory 17 by match
> id; (2) book side = venue engine's own rules (>=4 books, capture <=3h before
> the Kalshi capture); (3) bootstrap pinned exactly as #291 implements
> (Random(20261005), one choice per draw, 10,000 sorted means, CI at indices
> 250/9749); (4) --max-spread 0.10 frozen for every UNL sync in the sample;
> (5) latest pre-kickoff capture, rejected if any leg incomplete, never an
> earlier board; (6) receipt refuses without the ticker column; (7)
> CANCELLED/POSTPONED/STALE_ORPHAN excluded from the cohort, listed; (8) one
> event ticker per board; (9) two-sided = 0 < bid <= ask < 1 on every leg;
> (10) exact tie only. The operator's 13:29Z acceptance criteria are
> consistent and adopted; the FREEZE CUTOFF moves to the ratification time of
> this ruling — anything inspected before it is exploratory. Follow-up PR
> against the merged spec; also: today's 09:13Z UNL capture (1 book per row)
> is exploratory by rule (2).

## Rulings (ARCHITECT 2026-10-05, verbatim; v1)

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

## Operational definitions (v2)

The numbers in brackets are the 2026-10-06 rulings.

- **Freeze cutoff:** `2026-10-06T14:35:31Z`, when the ratification was relayed
  on #286 (issuecomment-6018597888). That is not earlier than the ratification
  itself, so it can only shrink the fresh sample, never admit an inspected
  game. Everything inspected before it is exploratory, including the 17 games
  of 2026-10-05 and the 09:13Z capture of 2026-10-06 (1 book per row, which
  rule 2 would also exclude).
- **Sample:** UNL (competition code `UNL`) games meeting all of the following.
  - Kickoff is after the freeze cutoff.
  - Not one of the 17 exploratory games, excluded by match id [1]. The ids are
    recorded in `unl_ladders.EXPLORATORY_MATCH_IDS` from the laptop DB. Until
    all 17 are recorded the receipt says so and the test refuses to run.
  - Status is not CANCELLED, POSTPONED or STALE_ORPHAN [7]. Those are listed
    with the reason. A past SCHEDULED or LIVE row whose result sync is merely
    late still counts.
  - Has a qualifying Kalshi capture taken after the cutoff, and a qualifying
    book session.

  The sample is the FIRST 30 such games in kickoff order (ties by match id).
  Every other game is listed in the receipt with the first criterion it fails.
- **Qualifying Kalshi capture [5]:** the LAST pre-kickoff Kalshi capture
  (`odds_snapshots`, `source = kalshi`, one `captured_at`).
  - All three legs (HOME, DRAW, AWAY) must be two-sided there. Two-sided means
    `0 < bid <= ask < 1` on every leg [9].
  - If any leg is missing or one-sided, the game does not count. An earlier
    board is never substituted.
  - Every leg's stored ticker must be in series `KXUEFANLGAME`.
  - All three legs must share ONE event [8]. Only the market ticker is stored;
    a Kalshi market ticker is its event ticker plus one outcome suffix, so the
    event is the market ticker without its last `-` segment. The series and
    event are printed on every row.
  - The receipt refuses to run when `odds_snapshots.market_ticker` is absent
    (`migrate_kalshi_ticker.py` not run) [6].
- **Sync spread [4]:** every UNL `sync-kalshi-soccer` run during the sample
  uses `--max-spread 0.10`. The command refuses any other value for UNL and
  prints the setting in each run's console receipt.
- **Kalshi probability:** per leg, mid = (bid + ask) / 2. The three mids are
  normalized to sum to 1 (the Cockpit's `kalNormalize` over three legs).
- **Book probability [2]:** the venue engine's own rules, read from
  `desk_policy.VENUE` (`minBooks` 4, `maxBookAgeH` 3).
  - Take the LAST complete book-consensus session before kickoff and NOT
    AFTER the Kalshi capture: `odds_snapshots`, non-Kalshi, market `1X2`, all
    three outcomes at one `captured_at`, de-vigged `devig_prob` normalized to
    1, under the `close_from_snapshots` contract.
  - It must carry at least 4 books (the session's `n_books`).
  - It must be captured no more than 3 hours before the Kalshi capture.
- **Pre-game favorite [10]:** the outcome with the highest book probability.
  Only an EXACT tie on the stored values excludes the game (listed).
- **Statistic:** per game, gap = Kalshi probability − book probability, both
  on the favorite, in percentage points. The gap is carried at full precision.
  The test statistic is the mean gap over the 30.
- **Bootstrap [3]:** pinned exactly as `unl_ladders.skew_test` implements it.
  - Python `random.Random(20261005)`.
  - For each of 10,000 resamples, 30 draws, one `rng.choice` per draw; take
    the mean.
  - Sort the 10,000 means. The 95% CI is the means at sorted indices 250 and
    9749.
- **Verdict:**
  - **STRUCTURAL** if the 95% CI excludes 0, with the sign reported. UNL then
    stays ineligible for venue-edge unless a skew-adjusted rule is declared
    as a separate candidate.
  - **NOT STRUCTURAL** otherwise. The architect then rules on eligibility;
    the verdict is never automatic.
- **Scope (operator's 13:29Z criteria, adopted):** UNL stays ineligible for
  venue-edge throughout. The gap test measures structural skew; it does not
  establish profitable edge. Exit: ratified definitions, 30 qualifying
  per-game receipts, the frozen test output, and then an explicit eligibility
  ruling.

## Receipt

The 30-game receipt (ruling 3) is the read-only receipt command's output for
the sample: per game, the match, each leg's bid/ask, spread, two-sidedness,
capture time and series, plus the book probability and gap above. It is
committed under `docs/receipts/` via PR, with the test result.
