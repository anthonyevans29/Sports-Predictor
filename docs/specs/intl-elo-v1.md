# International Elo v1: the frozen pre-commitment (#220 lane 2)

**Status: DECLARED 2026-10-02, AWAITING RATIFICATION. Nothing has been built or run.**
Registry id `intl-elo-v1` (#212). Every choice below is fixed before any fit
and before the test set is read (law 3). The run harness is a separate PR
written FROM this document after ratification. It refuses to run unless this
declaration is in the registry and has not run.

## The ruling this implements

**ARCHITECT 2026-10-02 (verbatim):** "(2) PRE-COMMITMENT (write for
ratification, no run): international Elo — home advantage a priori +100 Elo,
0 at derived-neutral; match weights by competition class a priori (friendlies
20, Nations League 40, qualifiers 50, finals 60 — the public Elo convention);
margin via ln(margin+1) as our other Elos; three-way outcome via the soccer
draw mapping. Train 2018-2024, test 2024-25 UNL + 2025-26 WCQ_EU; bar =
naive-baseline log-loss − 0.010; calibration bands; RPS reported; registry
entry with a 60-game confirmation window."

**Data:** the #230 ingest (`intl-sync`). These are the ruled competitions from
2018, restricted to senior national teams. `neutral_derived` is stored in
`match_neutral_derived` under rule intl-neutral-v1.

**Five choices go beyond the ruling's text.** Each is marked RATIFY below
with a proposal: season regression, an unknown venue, the draw update, the
pre-run data condition, and the naive baseline's definition. Nothing runs
until they are ruled.

## 1. The stream

- **Matches:** every finished match stored by #230 with both scores, in
  kickoff order (ties broken by match id), across the ruled codes: UNL,
  WCQ_EU/SA/AF/AS/NA/OC/IC, UEFA_EURO, UEFA_EURO_Q, CONCACAF_NL and
  FRIENDLIES_INT.
- **Not in the stream:** WC rows (the 2026 finals are outside the ruled
  competition set) and any other code.
- **Ordering:** each match is **predicted, then updated**. A match's own
  result never reaches its own prediction.
- **Label:** the 90-minute result. Use `home_score_90` / `away_score_90` when
  stored; otherwise use the stored score, but only for a match whose
  `status_raw` is `FT`. A finished AET/PEN row with no 90-minute score is
  excluded and counted (law 4: extra time is never read as a 90-minute
  result).

## 2. Ratings

- **Start:** every team at 1500, the first time it appears in the stream.
- **Season regression:** **[RATIFY: proposal: none]**. National teams have no
  season, and the public international Elo convention does not regress. Our
  club Elos regress 0.25 per season; this proposal does not carry that over.

## 3. The update

- **Expected score:**
  - E_home = 1 / (1 + 10^((R_away − (R_home + H)) / 400)).
  - H = **+100** when `neutral_derived` is false.
  - H = **0** when it is true.
- **Unknown venue (`neutral_derived` NULL, or no row):** **[RATIFY: proposal:
  H = +100]**. This treats the provider's listed home team as at home. The
  count of matches priced this way is printed. The alternative is to exclude
  them, with a count.
- **Actual score:** home win 1, draw 0.5, away win 0 (90-minute result).
- **Weight K by competition class**, a priori (the ruling's public-Elo
  convention):

  | Class | Codes | K |
  |---|---|---|
  | friendlies | FRIENDLIES_INT | 20 |
  | Nations League | UNL, CONCACAF_NL (every stage, including finals and play-offs) | 40 |
  | qualifiers | WCQ_EU/SA/AF/AS/NA/OC/IC, UEFA_EURO_Q | 50 |
  | finals | UEFA_EURO | 60 |

- **Margin, "as our other Elos"** (NHL v1, NCAA, NFL use this exact form):
  - mov = ln(|margin| + 1) · 2.2 / (2.2 + max(gap, 0) · 0.001)
  - gap is the winner's effective rating lead (home side: R_home + H − R_away;
    away side: the negative of that).
- **Update:** Δ = K · mov · (actual − E_home). R_home += Δ and R_away −= Δ.
- **A draw [RATIFY].** Taken literally, ln(0 + 1) = 0, so **every draw would
  move nothing**. Our other Elos are two-way sports, where this never comes
  up. Here about a quarter of results are draws.
  - **Proposal:** a draw uses mov = ln(2), the one-goal value. There is no
    gap factor, because there is no winner. This is the public convention: a
    draw weighs like a one-goal result.

## 4. Three-way probabilities: the soccer draw mapping

This is the same Elo→Poisson mapping the soccer model uses
(`src/models/poisson.py` `predict_match`; `elo.py`: "for soccer we'll
convert this into a 3-way distribution via the Poisson model").

- diff = (R_home + H) − R_away.
  - λ_home = μ · exp(c · diff / 2).
  - λ_away = μ · exp(−c · diff / 2).
- **Constants:**
  - c = 0.0023 (`DEFAULT_ELO_GOAL_COEFF`).
  - μ = the TRAIN period's mean goals per team per match (90-minute scores),
    computed once from train only and printed.
  - No team attack/defence strengths: both are 1.
  - No separate home goal boost. The home term lives only in diff, so it is
    never counted twice.
- **Dixon-Coles:** ρ = −0.10, the shipped soccer value. Scores are truncated
  at 10 goals and P(H), P(D), P(A) are renormalised.

## 5. Splits

- **Train (warm-up only):** stream matches with kickoff 2018-01-01 …
  2024-08-31. Nothing is fitted except μ (§4) and the naive baseline's
  frequencies (§6), both from train only.
- **Gap (predicted and updated, never scored):** stream matches from
  2024-09-01 that are not in the test set.
- **Test (scored):**
  - **UNL** with stored season `2024/25` (league phase, March 2025
    quarter-finals and promotion/relegation play-offs, June 2025 finals);
  - **WCQ_EU** with kickoff 2025-03-01 … 2026-03-31 (the 2026 cycle: group
    stage and the March 2026 play-offs).

  The run prints the stored season strings of the WCQ_EU test rows (they are
  the DB's truth). A test set with no rows refuses the run.
- **Pre-run data condition [RATIFY: proposal: 10%]:** the #230 receipt's RULE CHECK must show
  derived-neutral ≤ **10%** in the home-and-away competitions (UNL / WCQ_* /
  UEFA_EURO_Q). If it is higher, the city rule is reading multi-city home
  grounds as neutral, and the run is **blocked pending a ruling on the rule**.
  The bar is never adjusted for it.

## 6. Naive baseline and the gate

- **Naive baseline [RATIFY: proposal below]:** the TRAIN period's three-way frequencies, frozen.
  - Non-neutral test matches get (p_H, p_D, p_A), counted over non-neutral
    train matches (H ≠ 0, the unknowns included per §3).
  - Derived-neutral test matches get (p_N, d_N, p_N), where d_N is the train
    draw rate in neutral matches and p_N = (1 − d_N) / 2. The listed home side
    of a neutral match is arbitrary, so the baseline is symmetric.
- **Gate (frozen):**
  1. Log-loss on the test set **≤ naive-baseline log-loss on the same matches
     − 0.010**. A tie is a rejection.
  2. **Calibration bands** (the same bands as the NHL and NFL gates,
     `nhl_backtest.calibration_bands`): each match contributes its three
     (p, outcome) pairs. Every 10pp band with n ≥ 100 must calibrate within
     ±5pp.
- **Reported, not gated:**
  - RPS (`evaluation.rps_1x2`) for the model and the naive baseline;
  - per-test-competition log-loss (UNL / WCQ_EU);
  - the counts for unknown venue, excluded AET/PEN rows and neutral matches.
- **The bar does not move after the run.**

## 7. Registry and the confirmation window

- **Registry:** `intl-elo-v1` is declared with this document before any run.
  The test set has **0 prior reads**: no candidate has read the
  national-team test set. The run records its scored ids and result; a
  second run is refused.
- **Confirmation window (doctrine #212; the ruling's 60 games):** on a PASS,
  the model is scored in shadow on the **first 60 senior competitive
  national-team matches** in the ingested set that kick off **after the
  verdict** and are not in the test set. These are UNL, WCQ_*, UEFA_EURO_Q,
  UEFA_EURO and CONCACAF_NL; friendlies are excluded.
  - **CONFIRMED** only if its log-loss on those games ≤ ln 3 (1.0986, the
    uniform three-way prior) **and** strictly below the naive baseline on the
    same games minus 0.010 (the gate's own margin, re-read on future games).
  - Anything else is NOT_CONFIRMED, and the bar does not move.
  - **Executable plan:** `{n_games: 60, metric: log_loss, bar: 1.0986,
    must_beat_reference: true, reference: "naive baseline (frozen train
    frequencies, §6) on the same 60 games, minus 0.010"}`. The harness
    supplies `reference_log_loss` = naive log-loss − 0.010 on those games.

## 8. Run order (after ratification)

1. `.backup`.
2. `intl-sync` (#230), then paste the coverage receipt with the RULE CHECK.
3. The harness PR (built from this document), then one run, then paste the
   output and the changed `docs/registry/` files.
