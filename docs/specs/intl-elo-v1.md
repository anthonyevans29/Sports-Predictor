# International Elo v1: the frozen pre-commitment (#220 lane 2)

**Status: RATIFIED 2026-10-02 (five items, below). Harness: `python cli.py intl-elo-backtest` (built from this document). Not run.**

ARCHITECT-RULE on #232 (pre-run, frozen; verbatim): "(1) DRAWS — actual
score S=0.5 for both sides; the margin multiplier uses max(margin,1), so a
draw moves ratings like a one-goal result toward the expected-draw point:
ratified. (2) No season regression — ratified (no seasons). (3) Unknown venue
priced as listed home +100, count printed — ratified. (4) RULE CHECK gate at
10% — ratified, with the refinement pre-declared now so it needs no second
ruling: if breached, neutral_derived becomes "venue city not among the cities
where the home team hosted >=1 COMPETITIVE match in the pool" (multi-city
hosts like Germany, Spain, Italy handled; friendlies excluded from the
host-city set). (5) Naive baseline = frozen training-period H/D/A
frequencies, symmetric at derived-neutral — ratified. Nothing else changes;
the harness is built from the ratified doc."
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

**Five choices went beyond the ruling's text.** Each was proposed and is now
RATIFIED (marked below): season regression, an unknown venue, the draw update,
the pre-run data condition, and the naive baseline's definition.

**Codes (ruled 2026-10-02 after intl-sync refused on id 808):** CONCACAF's
Nations League is `CNL` (536); its 2018 qualification is `CNL_Q` (808). CNL
is in the Nations League class. **CNL_Q's K class is not ruled.** The harness
refuses while any CNL_Q game is in the stream; it never guesses 40 or 50.

## 1. The stream

- **Matches:** every finished match stored by #230 with both scores, in
  kickoff order (ties broken by match id), across the ruled codes: UNL,
  WCQ_EU/SA/AF/AS/NA/OC/IC, UEFA_EURO, UEFA_EURO_Q, CNL, CNL_Q and
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
- **Season regression: none (RATIFIED).** National teams have no seasons,
  and the public international Elo convention does not regress. Our club
  Elos regress 0.25 per season; that is not carried over.

## 3. The update

- **Expected score:**
  - E_home = 1 / (1 + 10^((R_away − (R_home + H)) / 400)).
  - H = **+100** when `neutral_derived` is false.
  - H = **0** when it is true.
- **Unknown venue (`neutral_derived` NULL, or no row): H = +100 (RATIFIED).**
  The provider's listed home team is treated as at home, and the count of
  matches priced this way is printed.
- **Actual score:** home win 1, draw 0.5, away win 0 (90-minute result).
- **Weight K by competition class**, a priori (the ruling's public-Elo
  convention):

  | Class | Codes | K |
  |---|---|---|
  | friendlies | FRIENDLIES_INT | 20 |
  | Nations League | UNL, CNL (every stage, including finals and play-offs) | 40 |
  | not ruled | CNL_Q | — (the run refuses) |
  | qualifiers | WCQ_EU/SA/AF/AS/NA/OC/IC, UEFA_EURO_Q | 50 |
  | finals | UEFA_EURO | 60 |

- **Margin, "as our other Elos"** (NHL v1, NCAA, NFL use this exact form):
  - mov = ln(|margin| + 1) · 2.2 / (2.2 + max(gap, 0) · 0.001)
  - gap is the winner's effective rating lead (home side: R_home + H − R_away;
    away side: the negative of that).
- **Update:** Δ = K · mov · (actual − E_home). R_home += Δ and R_away −= Δ.
- **A draw (RATIFIED).** S = 0.5 for both sides, and the multiplier uses
  max(margin, 1). A draw therefore moves ratings like a one-goal result
  (mov = ln 2) toward the expected-draw point. The gap factor is 1, because
  a draw has no winner (as proposed). Taken literally, ln(0 + 1) = 0 would
  have frozen every draw.

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
- **RULE CHECK gate at 10% (RATIFIED, with the refinement pre-declared):** the
  harness computes derived-neutral under intl-neutral-v1 in the home-and-away
  competitions (UNL / WCQ_* / UEFA_EURO_Q).
  - At ≤ 10%, the stored flags stand.
  - Above 10%, the run switches to **intl-neutral-v2**, with no second
    ruling. Neutral = the venue city is not among the cities where the home
    team hosted ≥ 1 **competitive** match in the pool. Friendlies are
    excluded from the host-city set. If either side is unknown, the flag is
    unknown (priced +100, §3).
  - The rule in force is printed and recorded with the run. The bar is never
    adjusted.

## 6. Naive baseline and the gate

- **Naive baseline (RATIFIED):** the TRAIN period's three-way frequencies, frozen.
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
  UEFA_EURO, CNL and CNL_Q; friendlies are excluded.
  - **CONFIRMED** only if its log-loss on those games ≤ ln 3 (1.0986, the
    uniform three-way prior) **and** strictly below the naive baseline on the
    same games minus 0.010 (the gate's own margin, re-read on future games).
  - Anything else is NOT_CONFIRMED, and the bar does not move.
  - **Executable plan:** `{n_games: 60, metric: log_loss, bar: 1.0986,
    must_beat_reference: true, reference: "naive baseline (frozen train
    frequencies, §6) on the same 60 games, minus 0.010"}`. The harness
    supplies `reference_log_loss` = naive log-loss − 0.010 on those games.

## 8. Run order

1. `.backup`.
2. `intl-sync` (#230), then paste the coverage receipt with the RULE CHECK.
3. `python cli.py intl-elo-backtest --preflight`. This prints the stream,
   the splits, the RULE CHECK and the rule in force; it scores nothing.
4. **A ruling on CNL_Q's K class** (the run refuses while it is open).
5. `python cli.py intl-elo-backtest`, **once**. Paste the output and the
   changed `docs/registry/` files in a PR.
