# The NFL quarterback term — design packet (a PROPOSAL for the 11-02 ruling; not a declaration)

Roadmap lane `nfl-qb` (#427), state "to declare". Its next step is the architect's: "my ruling: a candidate declared,
or a written no", due 2026-11-02. This packet is Code's input to that ruling, due 10-30. **Nothing here is declared,
fitted, run or scored.** No registry entry, no gate command and no model code are in this PR. The figures this
design needs come from the two read-only receipts that ship with it, run by the operator (section 7).

## 1. The ruling this answers (ARCHITECT 2026-10-23, addendum 162 item 3, verbatim)

> "3. NFL. (a) The 11-02 QB ruling needs a design packet, Code's by 10-30, read-only: full coverage by season and
> game type (games with player passing stats / games listed; missing fields; player ids that join a roster), not
> the three-game sample; a QB-strength estimate from prior games only, shrunk hard where thin, specified as an
> adjustment RELATIVE to the quarterback contribution the team's recent Elo already carries (no double count); the
> pregame identity rule as evidence allows (the previous game's most-attempts quarterback unless our injury read
> names him out; the injury read's own stamp problem, #627, named); Elo constants fixed. The hold ends only with a
> passing, confirmed term. [...] (c) #627's receipt (raw entries vs retained, join failures, observation time, per
> closing) is due with the packet."

The hold it ends, verbatim (addendum 40 item 4, 2026-10-11): "an NFL PLAY that is QB-flagged, or sized by this rule,
says on its page line "QB: paste to the architect before placing" [...] The hold stands until the model has a
quarterback term that has passed its gate". This packet changes nothing about the hold.

## 2. What the data holds (the probe of 2026-10-23, #427 comment 6367734110)

- **What is listed:** per game for 2023–2026 (about 335 games a season), one passing line per quarterback. The line holds completions/attempts, yards, TD, INT, sacks and rating.
- **No starter field:** the game statistics and the rosters carry none, and an unplayed game names no player.
- **The starter is post hoc only:** the quarterback with the most attempts. That is OUR READ, never the provider's word.
  - **A tie for the most attempts names none** (Codex on #710). It never rests on the provider's row order, and the coverage receipt counts such team-games. Sections 4 and 5 say how such a game is read.
- **The coverage receipt** (`scripts/nfl_qb_coverage.py`, section 7) makes this whole over every game of every season and game type, beyond the probe's three games a season. It reports which games carry lines for both teams, which fields each line sends or leaves empty (sack yards in particular, see 3.1), and how many passing-line player ids join a roster.
- **Coverage gate:** the estimate in section 3 needs lines for both teams in at least 98% of the finished regular-season and postseason games of each season it reads. Below that, the design is re-read before any declaration. This is a proposed threshold for the architect.

## 3. The quarterback-strength estimate (prior games only, shrunk hard where thin)

### 3.1 The per-game measure
Per quarterback per game, from his passing line:
- `ANY/A = (passing yards + 20·TD − 45·INT − sack yards) / (attempts + sacks)`, the adjusted net yards per attempt. It is the one number the line can carry that charges sacks and interceptions.
- **Without sack yards:** where the line sends no sack yards (the coverage receipt's F line says which), `NY/A₀ = (passing yards + 20·TD − 45·INT) / (attempts + sacks)` is used. The sacks still count in the denominator. The choice is made once, from the receipt, and frozen for every season.
- **Dropbacks:** `attempts + sacks`. This is the weight of a game everywhere below.

### 3.2 Season-centring
Each game's measure has the league mean of its own season removed: the dropback-weighted mean over that season's
games strictly before the game. Weeks 1–2 of a season use the previous season's whole-season mean. This is the same
correction ruled for the NHL GSAx term on 2026-10-27 (a league level that drifts by season is not a player's skill).

**The first season in the data has no previous season.** Two proposals, for the architect to choose:
- **(a) A 2022 reference.** The coverage receipt is run on 2022 too (`--seasons 2022,...`). If the provider holds it, 2022 is read for its whole-season mean only: no estimate, rating or prior comes from it.
- **(b) 2023 centred on itself.** 2023's weeks 1–2 are centred on 2023's mean of the games strictly before each game. 2023's first game day, which has no earlier game, is centred on that day's own pooled mean.
  - That is a within-day read, confined to the warm-up: nothing of 2023 is scored, and μ₀ (3.3) is computed from 2023's centred values after the season.

**RULED (ARCHITECT 2026-10-27 10:20 ET, addendum 170 item 2(a)), verbatim:** "The coverage receipt decides, not the
PR: it runs with 2022 in --seasons. If 2022 is listed and meets the same coverage gate (lines for both teams in at least
98% of its finished regular-season and postseason games), option (a) stands — 2022 is read for its whole-season mean
only, nothing else of it enters. If 2022 is absent or under the gate, option (b) stands — 2023 centred on itself, the
first game day on its own pooled mean, confined to the warm-up that is never scored. The spec records both with this
rule; the ruling of 11-02 names which one the receipt chose." The coverage receipt prints each season's gate line
(`coverage gate`, section 7). The prior μ₀ is computed from 2023's centred values either way.

### 3.3 The estimate as of a game
For quarterback q before game g, with `x_i` his centred measures in his own earlier games i (any team, any season in
the data) and `d_i` their dropbacks:
- `S(q, g) = (Σ w_i·d_i·x_i + k·μ₀) / (Σ w_i·d_i + k)`, with
  - `w_i = 0.5^(age_i / H)` (age in the quarterback's own games, half-life H = 16 games, about one season);
  - `k = 400` dropbacks, a hard shrink: a quarterback with one full game (35 dropbacks) moves about 8% of the way from the prior, and one full season (about 550) about 58%;
  - `μ₀`, the prior: the centred dropback-weighted mean of quarterbacks' first 100 career dropbacks in the data (a replacement level, below the league's 0), computed once from 2023 and frozen.
- **Only games strictly before g enter.** A doubleheader cannot happen in the NFL, but a game sharing g's kickoff is still excluded, as the MLB as-of receipt does.

**H, k and the 100-dropback window are proposals.** If the architect rules them fixed, nothing in the term is fitted
except β (section 4).

## 4. The adjustment, RELATIVE to what Elo already carries (no double count)

`nfl_elo_v1`'s ratings are built from results. Those results were produced with the quarterbacks who played, so a
team's rating already holds its recent quarterback level. Adding a starter's whole strength would count it twice. The
term therefore adds only the difference between today's starter and the quarterback level the rating was built on.

- **The carried level** `C(t, g)` of team t before game g is built the way v1 builds the rating, as a walk over t's games in order, so it carries what the rating carries:
  - **Start:** `C = 0` before t's first game in the data. 0 is the centred league level, as v1 starts every team at default_rating 1500.
  - **After each game j of t:** `C ← (1 − ρ)·C + ρ·S(q_j, j)`, with `q_j` the game's own most-attempts quarterback measured as of that game. A game with no most-attempts quarterback (none readable, or a tie) leaves C unchanged.
  - **At t's first game of a new season:** `C ← 0.75·C` before the game. This is v1's season_regression 0.25 toward the league level, as v1 moves each rating 25% of the way back to 1500 (`src/walters/nfl_backtest.py`).
  - **Why a walk and not a weighted mean (Codex on #710):** the packet's first form was a normalized weighted mean with a 0.75 factor on the previous season's weights. That factor cancels between numerator and denominator, so at a season opener C stayed at last season's full level while the rating had regressed. Δ then over-subtracted in every opener. The walk shrinks C itself toward the league level, as the rating is shrunk. A team with a short history also stays near 0, as a new rating stays near 1500.
  - `ρ = 0.10` per game approximates Elo's own memory at K = 20. ρ is a proposal; Code's receipt can print Elo's realized decay to check it before the declaration.
  - The walk drops the first form's dropback weights, since v1's update weighs every game alike.
- **The term:** `Δ(t, g) = S(starter(t, g), g) − C(t, g)`, in centred ANY/A units.
- **Applied to the forecast only:** the game's rating difference becomes `dr + β·(Δ_home − Δ_away)`, with v1's home advantage and logistic unchanged.
- **The ratings are v1's, exactly.** The rating update after the game uses v1's own expectation, without the term. v1's walk, k_factor 20, home_advantage 48, mov_base 2.2, season_regression 0.25 and default_rating 1500 are all fixed ("Elo constants fixed"). Both arms are therefore identical in every component but the term.
- **β (Elo points per ANY/A point) is the term's one fitted parameter.** It is fit by maximum likelihood on the training seasons (section 6), then frozen. The fit's printout shows the log-likelihood at β = 0..60 by 5.

A team whose starter today is the quarterback its rating was built on gets Δ ≈ 0, and the forecast is v1's. The
term moves the forecast when the starter changes: an injury, a benching, a rookie.

## 5. The pregame identity rule (as evidence allows)

- **The starter of team t in game g:** the most-attempts quarterback of t's previous game (OUR READ, section 2). Where that game names none (a tie, or no attempts readable), the rule reads the game before it.
  - **Week 1:** t's most-attempts quarterback over its previous season's last four games.
  - **Exception:** where our injury read names him out (Out or Doubtful), the starter is t's other quarterback with the most attempts in t's games this season; if none has any, it is the replacement prior μ₀.
- **The injury read's stamp problem (#627, named, as ruled).** The injuries table is replace-on-sync, so a past read is not kept, and `synced_at` is OUR sync's time, not the provider's report time.
  - An empty list is UNREAD (addendum 40 item 4, law 4), never "nobody out".
  - #627's receipt (section 7) gives, per closing, how often a team's list was empty, whether the feed or our read emptied it, and the age of the read at the page.
  - At a live forecast with an empty or unread list, the rule takes the previous game's starter and the row carries the flag that exists today. The term is not suppressed; the hold's page line still applies.
- **The backtest cannot replay the injury clause.** No historical injury reads exist, so the scored arm uses the previous game's starter always.
  - The receipt prints the identity rule's hit rate: the previous game's starter against the game's own most-attempts quarterback, per season. It also prints the term's log-loss with the game's actual most-attempts quarterback (the oracle).
  - **Both are reported, never gated.** The oracle bounds what a better identity read could add.

## 6. The test (a PROPOSED gate, for the architect to freeze or replace before any figure is read)

- **Candidate:** `nfl_elo_qb_v1` = `nfl_elo_v1` plus the term (sections 3–5), with β the only fitted figure.
- **Split:** 2023 is warm-up (ratings and quarterback estimates accrue, nothing scored, μ₀ computed). β is fit on 2024 regular season and postseason. The scored set is 2025 regular season and postseason, preseason excluded throughout as v1's gate does.
  - v1's constants were set before 2025 was scored, and nothing of 2025 enters the fit.
  - 2025 is the window v1's own gate scored (BACKLOG "NFL PHASE 2 GATE"): a known window, declared as such.
- **Gate:** PASS iff the candidate's mean log-loss on the scored set < v1's on the same games − 0.0050 (the MLB bar's margin), strictly: an improvement of exactly 0.0050 is a tie and rejects. **The margin's strictness is RULED and frozen** (ARCHITECT 2026-10-27 10:20 ET, addendum 170 item 2(b), verbatim): "strict, as pushed. A candidate at exactly 0.0050 is a tie and a tie is a rejection (law 3). Frozen now, before any figure exists." In every 10pp band with n ≥ 30, |realized − stated| ≤ 7pp (v1's calibration rule).
- **Confirmation:** the 2026 regular-season games after the verdict, frozen once, at n = 100: CONFIRMED iff the candidate's log-loss < v1's on the same games.
- **The hold ends only with PASS and CONFIRMED**, as ruled.
- **Reported, never gated:** the identity hit rate, the oracle arm, β's likelihood curve, and the term's size (|Δ| in Elo points) by quartile.

**Noted, not yet ruled** (addendum 170 item 2: "they belong to the 11-02 declaration, after the receipts"): the 98%
coverage gate, H = 16, k = 400, the 100-dropback prior window, ρ = 0.10, the β fit on 2024, the n = 100 confirmation.
The carried level's walk form (section 4, corrected after Codex on #710) is part of the same proposal.

## 7. The two receipts in this PR (read-only; the runs are the operator's)

1. **`scripts/nfl_qb_coverage.py`, the coverage section 2 asks for.** Per season and game type: games listed, finished, with passing lines for both teams, one or neither; every field's presence on the lines; the roster join of every line and of each team-game's most-attempts quarterback.
   - It keeps every answer under `logs/nfl_qb_payloads/` (never `data/`), so a capped run resumes and the design's dry run later reads the same payloads.
   - About 1,500 calls for four seasons; `--max-calls` caps a run.
   - **What the gate line counts (Codex on #710):**
     - Only the provider's Regular Season and Post Season stages count. A finished game whose stage is missing or novel is printed and never counted.
     - A failed read (transport error, non-200 answer, API errors) is printed and kept out of every count. A read that answered with no rows is counted as an answer.
     - A game the provider marks finished but the adapter's parse drops (no id, kickoff or team id) is named and cannot be checked (#712 item 2). An all-star exhibition is the adapter's own exclusion, counted apart and never a gap.
     - Any of the last three makes the gate line INCOMPLETE, never MEETS or BELOW, and so does a capped run.
   - **The F line (#712 item 1):** each season's F line lists every passing field that any season of the run sends. A field missing for a whole season reads "on 0, ABSENT", which is the reading 3.1's ANY/A versus NY/A₀ choice takes.
2. **`scripts/nfl_injury_receipt.py`, #627's receipt.** Per NFL closing since 10-11, from the closing files and the closing receipts: the teams with an empty list, each FEED (the provider answered no entry), OUR READ (it answered and nothing was retained) or UNKNOWN (no receipt); the join failures (positions unresolved); and the observation age (the page's start minus `synced_at`).
   - `--live` reads every team's injuries now: raw entries, the entries the read takes, retained, and positions the roster join leaves unresolved. The position lookup is not asked.
   - A live read counts as answered only when it is HTTP 200 with no errors (#712 item 3). Anything else is FAILED, never an empty list or an empty roster; a failed /teams read reads no team.
   - It opens no database, so it runs on either machine. The NFL record is the host's since the cutover.

## 8. Not proposed

No market input (doctrine: "the market is a reference, never a model feature"). No passer rating or QBR (the
provider's rating mixes components; ANY/A is computed from the line itself). No rushing component (the passing group
is what the probe verified; a rushing term is its own later question). No change to the hold, the Desk, the export
contract or the live model. Nothing is fitted or scored by this PR.
