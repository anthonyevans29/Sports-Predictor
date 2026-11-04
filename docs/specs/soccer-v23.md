# soccer-v23 — the joint log-linear successor to v22 (THE DESIGN; not declared, not run)

Lane `soccer-v23` (docs/roadmap.json), Issue #656, designed with the one-prediction-function lane #789. Code:
src/models/joint_poisson.py (the fit), src/walters/soccer_v23.py (the snapshot, the one prediction function, both
arms, the walk, the availability term, the gate), `soccer-v23-gate` (cli.py; docs/CLI.md). Tests:
tests/test_soccer_v23_fit.py, tests/test_soccer_v23_harness.py, tests/test_soccer_v23_text.py, on synthetic stores
only.

**State: a design.** No registry entry exists (an undeclared candidate holds none; the registry has no undeclared
status). The declaration, its slots and the entry are the architect's (11-20). The one run is the operator's block on
the architect's word (11-27). Nothing in this design has been run on real data, and no result exists. Addendum 251
item 2 (D8) is built in: g and b are defined AS-OF, identically in the harness and the production path (§5a); v22 is
re-walked on this harness beside v23; the bar is at least 0.0050 below BOTH v22's recorded figure and the re-walked
one (§6). Addendum 253 item 2(d) (D9) is built in: for each of the five rows (the context, the Elo state, the
early-season history, the match factors, simultaneous kickoffs) replay and live are identical by construction, one
builder and one prediction function on a versioned immutable snapshot (§4b); the match factors come only from addendum
252's availability record (D10) under the recorded clock, and the term is off in both paths wherever it has nothing,
which today is everywhere (its tables are not on main).

## D. The rulings, verbatim

> **D1 — ARCHITECT 2026-11-04 10:10 ET, addendum 248 item 2(b):** (b) 230 item 1(d), soccer-v23's DESIGN PR (#656; dated 11-13): the joint log-linear μ + h + α_i + δ_j + β·ΔE with per-team early-season continuity (216 item 3), its backtest harness walking it as production would, the frozen-bar text (the pot log-loss below v22's by ≥ 0.0050; a tie rejects — written as "below", so a tie IS a rejection here) written before any result; the availability term's inputs are the entry's fixture age and type verbatim (243/244's receipt is its evidence; no figure from it becomes a parameter without the bar). NO run before 11-20's declaration. Start today; merge when ready.

> **D2 — addendum 230 item 1(d):** (d) soccer-v23, THE DESIGN PR (lane soccer-v23, dated 11-13; #656) — START NOW, merge when ready: the joint log-linear μ + h + α_i + δ_j + β·ΔE with per-team early-season continuity (216 item 3), the backtest harness that walks it as production would, the frozen-bar text (the pot log-loss below v22's by ≥ 0.0050, a tie rejects) written before any result; NO run and NO declaration before 11-20 (a date is never a reason to run early); an early merge is a done-mark.

> **D3 — addendum 216 item 1 (the normalisation finding v23 must not have by construction):** 1. THE NORMALISATION FINDING — CONFIRMED in the real code, not only in the review's reimplementation. src/walters/training.py builds the context per competition as g = total goals / (2 × matches) and b = home mean / g (clamped to [1.0, 1.30]); src/models/poisson.py estimate_strengths deflates HOME goals by b before averaging and divides BOTH averages by the undeflated g; the forecast is home λ = g·b·A_H·D_A·elo and away λ = g·A_A·D_H·elo. For a league of average teams the deflated per-team average is g·(3−b)/2, not g, so every average rating reads (3−b)/2 (0.925 at the default b = 1.15, before shrinkage), the forecast total reads g·(1+b)·((3−b)/2)² (about −8% at b = 1.15) and the home/away goal ratio the model expresses is b where the data's is b/(2−b) (1.15 against 1.35). The review's synthetic counterexample (3.000 in, 2.739 out) reproduces exactly from these lines. It is a structural bias toward fewer goals and away/draw mass, not a bug in a branch; it passed through v22's gate because the gate measures v22 against its bar, not its equations against themselves. RULED: (a) a FINDING Issue (model, finding, sport:soccer, M) with the equations above and the review cited; (b) Code's receipt PR, read-only: one test that drives the REAL estimate_strengths and the real forecast with the review's synthetic league and pins the −8.7% total (the review's script is the receipt's citation, not repository code — it reimplements the equations), plus a read-only line that evaluates the same expressions on the production model's stored PL context (g and b as stored) and prints the implied average-team rating, total and home/away ratio; posted on the Issue; (c) NO change to v22: the fix is a candidate through the frozen gate, never a patch to a live model.

> **D4 — addendum 216 item 2 (the 30-match switch; continuity is a design element):** 2. THE 30-MATCH SWITCH — CONFIRMED as a discontinuity (the current-season window drops the supplementary history at the league's 30th finished match regardless of a team's own games), and the soccer backtest's default skip of the first 40 matches means that boundary has never been evaluated. RULED: a LIMITATION Issue (model, limitation, sport:soccer, S) for the unevaluated boundary; the per-team continuity (a weight on each team's own usable exposure between its prior-season estimate and its current-season evidence, promoted clubs as a persistent prior) is a DESIGN ELEMENT of the successor candidate of item 3, not a change to v22 and not a reopening of the rejected time-decay experiment.

> **D5 — addendum 216 item 3 (the successor):** 3. THE SUCCESSOR — #656 is the vehicle, dated now (the model lanes come first; the PL is the only live model-edge family today, and v22 reads behind the close over the rolling 30): a jointly fitted log-linear model log λ_H = μ + h + α_H + δ_A + β·ΔE, log λ_A = μ + α_A + δ_H − β·ΔE, with identification constraints and regularisation, the Dixon–Coles correction kept, the per-team continuity of item 2 built in — the baseline, the home effect, attack, defence and Elo's increment estimated coherently so item 1's inconsistency cannot exist by construction. Roadmap lane "soccer-v23" (Issue #656): 11-13 code — the design PR (the fit, its constraints, the early-season treatment, the harness: one run at the frozen soccer gate on the frozen pot, the reservation pattern); 11-20 architect — the declaration with the bar written before any result: the pot's log-loss below v22's by at least 0.0050, a tie a rejection (the improve bar as it stands), with the early-season matches INCLUDED in the scored set (no 40-match skip for this candidate: its own declared window states the skip, and it is zero); 11-27 operator — the one run on my word, my block, on a .backup copy opened immutable=1; PASS → a 60-game prospective shadow on the host's PL pages beside v22 (the pl-availability pattern, its own window counted from its first host page), the read by me; earliest_live the day after that read. No date moves a bar.

> **D6 — addendum 243 item 4 (availability inputs):** 4. For the successor's design PR (230 item 1(d)): the availability term's inputs are the entry's fixture age (this fixture / an earlier fixture, N days) and its type, verbatim; the design states what it does with each and the receipt above is its evidence. No number from this receipt becomes a parameter without a frozen bar.

> **D7 — addendum 216 item 4 (the lane this harness is designed with, #789), as #789 quotes it:** 4. BACKTEST-TO-PRODUCTION PARITY — ACCEPTED as a lane, not a build today: #425 already records the injury factor's absence from v22's gate; the review's inventory (the scoring context, the Elo state, the early-season history and the match factors differ between soccer_backtest and _generate_predictions_soccer) becomes a LIMITATION Issue (model, limitation, sport:soccer, M) with that table; the engineering direction — ONE prediction function taking a versioned, immutable input snapshot, invoked by replay and by live alike, "same model, same inputs at the same instant, same probabilities" as the acceptance test — is a lane (track:model, class:lane, size:L, no date) to be designed with the soccer-v23 harness so the successor is testable where v22 was not. Historical injuries are never manufactured; the sealed availability window is never read early.

> **D8 — ARCHITECT 2026-11-04 11:50 ET, addendum 251 item 2 (the context gap):** 2. 249 ITEM 1(a) — RULED. Code's finding is correct and verified in the source: soccer_backtest.py:200 walks every row under CompetitionScoringContext() (g 1.4, b 1.15) while production (training.py:514) reads the stored trained context of the competition (PL today g ≈ 1.49, b ≈ 1.17, as #786's receipt printed them). The reason the walk does NOT read the stored context is sound and is recorded with the finding: the stored context is fitted on the whole training pot — the same games the walk scores — so a walk that read it would leak the pot's own totals into every prior-only step. So "production == the walk, row for row" cannot hold on g and b by construction, and an xfail over the WHOLE parity test would blind the one test meant to catch a live/replay divergence. Three tests, then, in the one PR (249's two, reshaped, plus the gap's own pin):
>
> (a) THE PARITY TEST, with the context INJECTED: the walk gains an optional `context` parameter whose default is today's CompetitionScoringContext() (the default path byte-identical, pinned by the existing soccer-backtest golden on the fixture store — a changed default would re-measure every soccer record and is gate-class; this is not that); the test passes production's stored context to the walk and asserts production == the walk, row for row, on the synthetic store. It PASSES on v22 (the shared path — Elo, estimate_strengths, Poisson, Dixon-Coles — reproduces its gate) and fails the day a real divergence appears. No xfail.
>
> (b) THE CONTEXT-GAP PIN, strict xfail on v22: the walk's effective context on a competition equals production's stored context for it. It turns red (xpass) the day the two paths agree, which is the successor's obligation, and it carries the leak reason in its docstring so nobody "fixes" it by reading the stored context into the walk.
>
> (c) THE NORMALISATION PIN, 249 item 1(b), unchanged: strict xfail on v22 with its positive control.
>
> THE FINDING ISSUE (filed with the PR, `Refs #789`, `Refs #786`, never closing either): "the soccer gate's walk scores under the default context (1.4 / 1.15); production runs the trained one; neither is as-of" — its resolution is the successor's design, not a patch: soccer-v23's design PR (248 item 2(b)) must state how its harness and its production path define g and b IDENTICALLY (an as-of estimate from the prior finished games in both, or a frozen pre-pot context in both — the design chooses and says why), and must re-walk v22 under that same harness beside v23 so the comparison is like for like. v22's recorded gate figure STANDS as measured; nothing about v22 changes. THE BAR, so it never loosens: v23's pot log-loss must be at least 0.0050 below BOTH v22's recorded figure AND v22's figure re-walked on v23's harness; a tie on either is a rejection (the bar is written "below"). Option 2 (the default walk reads the stored context) is REJECTED: a leak and a gate-class re-measurement of every soccer record. Option 3 (the improve gate's holdout scorer) is REJECTED: not as-of. The parity harness Code committed locally (6be9b16a, built to 248) is the base; it reshapes to (a)–(c) and opens as 248 item 2(a)'s PR, due 11-20 as before.

> **D9 — ARCHITECT 2026-11-04 13:20 ET, addendum 253 item 2(d) (the successor's obligation, the five rows):** (d) THE SUCCESSOR'S OBLIGATION, restated so #828 and the v23 design PR agree: 216 item 4's direction IS the requirement — ONE prediction function taking a versioned, immutable input snapshot, invoked by replay and by live alike ("same model, same inputs at the same instant, same probabilities"). The v23 design PR shows, for each of the five rows (the context, the Elo state, the early-season history, the match factors, simultaneous kickoffs), how replay and live become identical BY CONSTRUCTION, not by test; the as-of factor inputs come only from stored as-of data (the availability record of addendum 252 is the source going forward; where the record has nothing for an era, the term is off in BOTH paths for that era and the harness says so); v22 is re-walked under the same harness beside v23; the bar is 251 item 2's. v22 does not change.

> **D10 — addendum 252 item 1 (the availability record's two clocks; the source of the as-of factor inputs D9 names):** THE TWO CLOCKS, ruled now so no term argues it later: `recorded_at` is OUR knowledge; `source_stamp` is the source's claim. A live-era record, a forward confirmation and a closing-time input use `recorded_at` only (what we had on our disk before the cut-off). A backfilled row (recorded_at later than source_stamp by more than the feed's cadence: nflverse's season file reaches back to its first load, so our first fetch records weeks of history at once) is usable ONLY in a backtest labelled "source-stamped" in its run record and its gate text, never in the live-era record; a term that wants it declares that in its bar. Both clocks are kept on every row so either reading can be audited.

## 1. The model (src/models/joint_poisson.py)

Per fixture f of competition c in season S at the as-of instant t, the window is every admitted finished row of c in
seasons {S−1, S} visible at t. S−1 is c's season before S, ordering c's visible seasons by their earliest stored
kickoff.

```
log λ_H(r) = μ + h + α_{a,s} + δ_{b,s} + β·ΔE_r
log λ_A(r) = μ     + α_{b,s} + δ_{a,s} − β·ΔE_r
```

- **ΔE_r** is the row's own pre-kickoff difference on production's league ladder (home − away, rating points, no home
  advantage). Elo is walked (EloConfig() defaults, the per-team season regression, key `code:season`, through elo's
  own functions; a test pins the walk's end state equal to `elo.train`), never fitted. The fixture's own ΔE applies
  the regression a walk would apply at its kickoff (a team whose last row was another season's), as the window rows'
  ΔE do. The column is ΔE/100 inside the fit (conditioning only); β is reported per point.
- **Penalised objective:** the Poisson negative log-likelihood plus (τ/2)·[Σ_{T_{S−1}}(α² + δ²) +
  Σ_{T_S}((α_{k,S} − m^α_k)² + (δ_{k,S} − m^δ_k)²)] + (τ_β/2)·(100·β − BETA_PRIOR_MEAN)². m_k is the club's S−1
  parameter (× CARRY). For a club absent from c's S−1 rows it depends on how the club arrives, read from the rows of
  S−1's season label in the other competitions as of t, on the declared pyramid `PYRAMIDS` (PL > ELC > EL1 > EL2, the
  store's only multi-tier family, from src/adapters/api_football.py's England LEAGUE codes): from a lower tier or from
  outside the store (promoted), the persistent promoted prior (ln 0.85, ln 1.15 on S−1's zero mean); from a HIGHER tier
  (relegated), no directional prior (`RELEGATED_ATTACK` = `RELEGATED_DEFENCE` = 0, S−1's zero mean); from a competition
  off the pyramid, or from two places, the arrival cannot be placed and the run refuses before the reservation (never
  guessed; the preflight names each). τ = K_PRIOR·λ̄_{S−1} (λ̄ the window's S−1 goals per team per match), derived
  inside the fit.
- **β's weak prior** (every window, one rule, no count switch): centred at `BETA_PRIOR_MEAN` = 0 with precision
  `BETA_PRIOR_PRECISION` = K_PRIOR·G0 = 7.0 on the fit's column ΔE/100 (prior sd about 0.0038 per rating point; the
  first season's μ/h precision reused, no new number; chosen before any probe and never tuned). Without it β overfits
  a competition's first few rows, whose small ΔE values come out of the same results, and the walk priced later
  fixtures as near-certainties (the 2026-11-04 review's synthetic probe: |β| up to 0.08 per point, p_home 1.0). In a
  full window the likelihood's information on β (about Σλ·(ΔE/100)²) dwarfs it. A test pins bounded prices on early
  first-season windows.
- **Identification:** a hard sum-to-zero on α_{·,S−1} and δ_{·,S−1}, by substitution (the highest team id, last in
  sorted order, dependent). μ and h are unpenalised whenever S−1 exists. T_S is the teams with visible season-S
  rows; a team with none (the fixture's teams included) reads the exact optimum of its only term, the penalty: its S−1
  parameters × CARRY, the relegated prior, or the promoted prior. No row of any status other than the admitted
  finished ones is read.
- **216 item 1 by construction:** the score equations force Σλ̂_H = Σy_H and Σλ̂_A = Σy_A exactly for any β, τ or
  prior (β's included: it penalises β, never μ or h); a league of average teams gives e^ĥ = b/(2−b) and a total of 2g. No deflate-then-divide step exists. Pinned
  in tests/test_soccer_v23_fit.py on b ∈ {1.15, 1.2, 1.3}.
- **The first season of c in the window** (no S−1; open question 3): α and δ centred at 0 (no promoted concept); μ and h
  under a weak prior centred at μ0 = ln(G0·(2−B0)) and h0 = ln(B0/(2−B0)), G0 = 1.4 and B0 = 1.15 being
  CompetitionScoringContext()'s defaults converted coherently (away mean g·(2−b), home/away ratio b/(2−b)), precision
  K_PRIOR·G0. The pull identities Σ(y − λ) = τ_μ(μ − μ0) and Σ(y_H − λ_H) = τ_μ(h − h0) are pinned in place of exact
  equality.
- **Fit:** damped Newton from a cold start, never warm-started; Cholesky positive-definiteness check, then
  `np.linalg.solve`; up to 60 step halvings; converged only when the FULL Newton step max|H⁻¹g| < 1e-12, never on a
  damped step's displacement; a line search that cannot lower the objective while the Newton decrement ½·gᵀH⁻¹g is
  above PRECISION_FLOOR·|objective| refuses ("the line search stalled"), one below it takes the full step (Codex on
  #832, round 1); 100 iterations; `FitRefused` refuses the whole run, with no fallback. β is fixed at 0 and labelled
  `beta_unidentified` when the window's ΔE takes fewer than two distinct values.
- **Pricing:** λ goes to the REAL `poisson.predict_match` through an adaptor: context (1, 1), `TeamStrength(λ_H, 1)` /
  `TeamStrength(λ_A, 1)`, `elo_goal_coeff` 0, equal Elo, so home_xg = λ_H and away_xg = λ_A exactly (pinned at
  1e-15), and the 0.05 floor, v22's stored ρ (the copy's production ModelVersion `parameters["poisson"]`; the run
  refuses unless that version is v22), the 1X2 renormalisation and the over/under are v22's own. DC fitting stays
  rejected. At a fixed ρ the DC cells leave both means unchanged (p10·λ_A·ρ − p11·ρ = 0), pinned to truncation.
- **No time decay:** every row weighs 1. This is not S19 reopened.

## 2. Continuity (216 item 2)

- **Per team:** the weight on a team's own current-season evidence is about n_k/(n_k + K_PRIOR), on its own exposure
  (a test walks n_k = 0 … 20). At n_k = 0 the team reads exactly its S−1 estimate.
- **No league-wide switch:** no count branch exists in the model module (a test reads its numeric literals). A test
  prices one fixture with the league's season count at 29 and at 30 (the 30th row an unrelated match): v23 moves by
  less than 0.01, v22's arm steps by more than three times that (its backfill drops at 30).
- **Promoted clubs:** the prior persists until the club's own rows outweigh it (a test fits a promoted club with a
  few rows at the league's rate and finds it on the promoted side, about K/(n + K) of the prior's offset). A club
  relegated INTO the competition is not a promoted club: it carries no directional prior (§1; a test on a
  relegated-club window).
- **The link to S−1 is in the fit:** a test on a NON-neutral S−1 (one club twice as strong) finds its season-S attack
  between its S−1 estimate and its season-S evidence, about n/(n + K_PRIOR) of the way.
- **Season boundary:** the only stated discontinuity is S−2 leaving the window, the boundary at which Elo regresses.

## 3. The availability term (243 item 4)

The inputs per injury entry are its `type` (the stored string, verbatim) and its fixture age: one of the receipt's six
categories (scripts/pl_injury_classification_receipt.py: "this fixture", "an earlier fixture", "a later fixture",
"fixture not stored", "no fixture id stored", "fixture id held by 2+ stored matches"), with N carried as the receipt's
own one-decimal detail string ("an earlier fixture N.N d before (...)"), never as an input. A test pins the categories
and `fixture_age` equal to the script's.

| Entry | What v23 does |
|---|---|
| "Missing Fixture" + this fixture | The only class that counts: `factors.injury_adjustment`, unchanged (the position weights and the 25% cap) |
| "Missing Fixture" + an earlier fixture | Nothing, whatever N is (N recorded; no threshold) |
| "Missing Fixture" + a later fixture | Nothing |
| "Missing Fixture" + fixture not stored / no fixture id stored / fixture id held by 2+ stored matches | Nothing, labelled (an ambiguous id is refused, never guessed) |
| "Questionable", any age | Nothing |
| Any other type string | Nothing, labelled "type not ruled" |

- **Where the entries come from (253 item 2(d), row 4; §4b):** only the snapshot's `availability`, addendum 252's
  record read at the fixture's instant under the RECORDED clock (D10). Each `injury_status` fact of the fixture's
  clubs is one entry: its type is the fact's status text, verbatim; its fixture age is the receipt's own
  `fixture_age`, the fact's match (our id, with the stored kickoff the observation carried) against this fixture; its
  position the fact's, verbatim. A fact of an unmapped team (law 4: our id NULL) is kept in the notes and counts for
  nothing; facts of other kinds (lineups, depth ranks) are no input of this term. The injuries and lineups tables are
  read by neither path (they are overwritten in place: `schema.Injury` "deleting all rows for a team and
  re-inserting", `schema.Lineup` "all rows of the match are deleted and rewritten").
- The term is gated by the boolean slot `availability_on`: a switch, not a number (a numeric weight would itself be a
  parameter). It is ON at an instant only when the slot is on AND the record holds something there; otherwise it is
  OFF in both paths and the walk and the preflight print it per era (`availability_lines`).
- On the pot it is ABSENT for both arms: no injury history exists, and 216 item 4 rules "Historical injuries are never
  manufactured"; the record cannot hold a pot fixture's fact under the recorded clock (it is first fetched after the
  pot), so the term is off for every pot era. The walk stops (GateRefused) if the multiplier is ever other than
  exactly 1.0 where the term is off.
- No figure of the 243/244 receipt is in the code: a test holds both modules' numeric literals to the design's own
  allow-list.

## 4. The harness: one function, which #789 can test

- **The snapshot** (`Snapshot`, version "soccer-snapshot v2"): frozen dataclasses, one per INSTANT (never per
  fixture); the visible rows as a tuple in kickoff order (ties by id) and their chained digest; the ladder over them
  (`elo_pre`, each row's pre-kickoff ratings; `elo_state`, each club's rating and last season key after the last
  visible row); the availability record at its decision instant (`availability`: its state, reason, clock, facts and
  the backfilled facts excluded; `decision` = `visibility_bound(t)`, the rows' own bound); the
  visibility rule; the parameters (canonical JSON: v22's stored poisson config, the availability switch);
  `snapshot.sha` digests every field. v2 replaces v1 (rows and caller-supplied entries) for 253 item 2(d).
- **The one builder:** `snapshot_from_rows` fills every field (the visible rows; `walk_ladder` over them; the record
  read at the snapshot's DECISION INSTANT, `Snapshot.decision` = `visibility_bound(t)`, the rows' own bound). Live
  reaches it through `snapshot_from_session` (one SELECT bounded at the visibility instant through the same admission
  predicate `admit`, and the store's own record through the adapter); the walk calls it ITSELF at every kickoff
  instant, memo on or off (`Prefix.snapshot` is the same call over the walk's rows: no second assembly). A test spies
  the builder: the walk (memo on and off) and `predict_live_slate` each call it once per instant, and one ingredient of
  it perturbed (the ladder's final rating of a club, + 1e-6) moves live and the walk together, bitwise. Cost: one pass
  of the ladder and the row digest per instant (about 0.15 s at the pot's size on a synthetic 16,546-row probe).
- **`predict(snapshot, fixture, arm)`** is pure: no database, no clock, no global read. `arm="soccer-v23"` is §1.
  `arm="v22"` is production as of t (v22 RE-WALKED on this harness, 251 item 2): g and b from c's visible rows over
  every season (clamped to [1.0, 1.30]; §5a); the
  ladder (the stored state: no pending regression); the REAL `estimate_strengths` on S's visible rows plus, below 30,
  the 500 most recent VISIBLE other-season rows of c (production's backfill has no date bound on a replay,
  training.py:489-500), tied kickoffs taken id-ascending; the promoted default; the REAL `predict_match` with the
  stored ρ and c; no factors, labelled. A test drives the REAL `training._train_fresh_soccer` and
  `_generate_predictions_soccer` on a synthetic store and pins the arm equal at 1e-12, on the ≥ 30 path, the backfill
  path, and the backfill path where the 500 limit binds inside a tied kickoff (660 other-season rows, six rows per
  kickoff). **That equality holds on a store with no AET / PEN row in a LEAGUE-type competition** (see Admission
  below): with one, the arm differs from live v22 by exactly the 90-minute substitution, and a test pins it so (the
  arm differs from production on the store as it is, about 3.7e-4 on the synthetic probe, and equals at 1e-12 the
  production run on the same store with that row's full score set to its 90-minute score). Open question 22, RULED AS
  BUILT by addendum 254 item 3 Q22 (a): "v22 re-walked" is v22 on this harness. **The tie order is a declared reading, labelled:** production's `ORDER BY utc_date DESC LIMIT 500` has no
  tie-break, so SQL leaves the order of tied rows undefined; SQLite returns them in id-ascending scan order, and the
  arm follows that (the earlier id-descending order kept a different 500 rows at the boundary: max|Δp| up to 0.0196
  on the review's probe).
- **The production path is `predict_live_slate(session, fixtures, arm, params_json, visibility)`** (251 item 2;
  `predict_live` is its one-fixture form): the design's only live entry point, which the PASS shadow calls: per kickoff
  instant (`by_instant`) one `snapshot_from_session`, then `predict` for each fixture of the instant. It reads no ModelVersion (no stored context, no stored state). Every prediction's `info`
  carries a `context` block: `CONTEXT_DEFINITION`, the values the arm priced with, the count of the competition's
  visible rows and the latest kickoff among them; the walk records it per fixture (`walk(...)["context"]`).
- **No import of the unmerged parity code.** A parity harness can call `predict` from replay order and live order alike.
- **The memo:** `Prefix` is NOT a builder (the review of the five rows found the earlier cache assembling snapshots
  from its own ladder history and index lists, agreeing with live only because tests pinned them equal): it memoises
  predict's fits keyed by the builder's own output (the snapshot's prefix digest, the competition, the season) and the
  view of the snapshot in hand (one pass over that snapshot's own rows). A test pins memo = no memo, bitwise, over a
  whole walk; a memo built over other rows is refused.
- **Visibility (slot):** a row is visible at t only once its result is known before t. The store holds no
  final-whistle stamp (`schema.Match`: `utc_date` is the kickoff; no finished-at or recorded-at column), so "known" is
  a declared bound, kickoff + `RESULT_LAG_HOURS` (4 h: 90 minutes, half-time, stoppage, extra time, its break and a
  shoot-out, with margin for a delayed start; RULED by addendum 254 item 3 Q4 as the bound a result is known, frozen
  by the declaration, §8). "day" (the rule addendum 254 item 3 Q4 RULED; the slot still admits "kickoff", §7): the result known before t AND a kickoff
  on a UTC date strictly before the fixture's (the morning chain's reading; it batches every same-day fixture kicking
  off at least 4 h after midnight; an earlier one also loses the previous evening's games still inside the lag);
  "kickoff": the result known before t. `visibility_bound` is the one bound (the builder and `predict`'s check), so a
  game still in play at t is visible to neither the harness nor the production path. It is also THE DECISION INSTANT
  (`Snapshot.decision`): the availability record is read there, never at the kickoff, so a fact recorded after it (a
  match-day poll under "day"; a T-60 .. T-0 poll under "kickoff") is read by neither path, and a live call made at or
  after it (under "day", the morning chain of the fixture's own UTC date) holds every fact a replay reads. The
  residual, labelled (results and facts alike): the bound is a declared instant, not the time our store learned a
  result (no match row carries one; addendum 252's `recorded_at` clock exists for availability facts, not results), so
  a result the live store has not synced by the call, and, for a call made BEFORE the decision instant (a previous
  day's chain under "day"; any call earlier than t − 4 h under "kickoff"), a result or fact arriving between the call
  and the decision instant, is absent live and present in a replay on a later copy; never the reverse (open question
  27, RULED AS BUILT by addendum 254 item 3 Q27 (a): the decision instant is the cut-off; a call before it is the
  labelled residual).
- **Admission:** a finished soccer row of a LEAGUE-type competition with a kickoff and both scores, through the
  confirmation predicate (`soccer_expansion.unscoreable`: AWD / WO and cancelled released; a non-FT code with a stored
  90-minute score walked on that score). Both arms read the same admitted rows. Three labelled differences from the live
  path, which reads the raw `home_score` / `away_score` on every FINISHED row: an AWD / WO row it would read is left out
  of both arms; and on an AET / PEN row of a LEAGUE-type competition (a play-off final, e.g.) the v22 arm reads the
  stored 90-minute score where live v22's contexts (training.py:196-214), strengths input and Elo ladder (`train_elo`
  through `_to_train`) read the full score with extra-time goals. v22's own gate walk (`confirmation_scoring` False)
  reads the full score too; the 90-minute reading is the `confirmation_scoring` convention, applied to both arms
  alike; RULED AS BUILT (addendum 254 item 3 Q22 (a); open question 22): "v22 re-walked" is v22 on this harness, not
  live v22 reproduced, and BAR_TEXT and the run record say so. Under scope LEAGUE the rows stay in
  every snapshot, so on the real store this reaches v22's re-walked figure. Third: under LEAGUE_REGULAR a play-off row is out of the HISTORY as well as the scored set, for BOTH arms (`in_scope`,
  applied by the one builder and the walk; soccer_expansion F3: "only regular-season rounds are scored and walked";
  Codex on #832, round 1): v22's re-walk skips it in its contexts, strengths, backfill and ladder exactly as
  soccer-v23 does, a labelled difference from live v22, which reads every FINISHED row.
- **Printed strata, reported only, gating nothing:** the league's season count below 30 / at least 30 (the boundary
  216 item 2 found unevaluated); the lower of the two teams' own season counts; per competition; β̂ and the I1/I2
  residuals. RPS and Brier beside the log-loss. The close is never read.

## 4b. The five rows, identical by construction (253 item 2(d))

D9 requires the design to show, for each of the five rows, how replay and live become identical BY CONSTRUCTION, not
by test. The construction is two functions: ONE builder (`snapshot_from_rows`: live reaches it through
`snapshot_from_session`, and the walk calls it itself at every instant; `Prefix` only memoises fits keyed by its
output) fills every field of a versioned, immutable `Snapshot` at an instant, and ONE `predict(snapshot, fixture, arm)` reads that snapshot and the fixture and nothing
else (no database, no clock, no stored context, state or factor table). The replay is `walk`; live is
`predict_live_slate`. Each row below names the old divergence (#788's table; #828's pins), the snapshot field that
carries the row, how the one builder fills it for both paths, and what each arm reads from it.

| Row | Where the OLD v22 paths diverge | Snapshot field(s) | Filled by the one builder, for both paths | soccer-v23 reads | v22 arm (re-walked) reads | Test (tests/test_soccer_v23_harness.py) |
|---|---|---|---|---|---|---|
| (1) The context | the gate's walk scores under `CompetitionScoringContext()` (soccer_backtest.py:200); production reads the stored trained context (training.py:514), fitted on the whole pot | `rows` (with `prefix`, their digest) | the admitted rows (`admit`) with kickoff before `visibility_bound(t)`; live: one SELECT bounded there, the same predicate | μ and h, fitted on the window (S−1, S) of the competition's `rows` (§1) | g and b by training.py:196-214's formulas over the competition's `rows`, every season (`v22_context`); the default only with no visible row (training.py:217) | `test_253_row_1_the_context_is_the_snapshots_rows_in_both_paths` |
| (2) The Elo state | production carries the regressed Elo across seasons (`_train_fresh_soccer`, the league ladder over every finished match); the walk starts each season on a fresh `EloState` (soccer_backtest.py:201) | `elo_pre`, `elo_state` | `walk_ladder` over `rows` from the first admitted row: `EloConfig()`, `regress_team` at a club's season change, `update_after_match` (equal to `elo.train`); `walk_ladder` is called by the builder alone | each window row's ΔE from `elo_pre`; the fixture's ΔE from `elo_state` plus the regression its kickoff would apply (pending) | the fixture's ratings from `elo_state` as stored (no pending regression: production reads its stored state) | `test_253_row_2_the_elo_state_carries_the_prior_season_in_both_paths` |
| (3) The early-season history | production's backfill below 30 selects `Match.season != season` with no date bound (training.py:489-500), so a replay reads LATER seasons; the walk skips the first 40 matches (`min_prior=40`, soccer_backtest.py:90) | `rows` | as row 1 | S's visible rows (CUR) and S−1's (PREV), per-team continuity, skip zero | S's visible rows; below 30, the 500 newest VISIBLE other-season rows (ties id-ascending) | `test_253_row_3_the_early_season_history_is_the_same_as_of_rows` |
| (4) The match factors | production composes injury, lineup and XI multipliers into `factor_adjustment` (training.py:557-867) from tables overwritten in place (`schema.Injury`, `schema.Lineup`); the walk reconstructs none | `availability` (`AvailabilityAsOf`: state, reason, clock, facts, excluded) | `read_availability(record, d)` at the DECISION INSTANT d = `visibility_bound(t)` (the rows' own bound, never the kickoff): the record's `at(d)` through the `AvailabilityRecord` interface, checked (the recorded clock only; every fact recorded at or before d, a later one refuses; a backfilled fact, `backfill_reason`, moved to `excluded`, never read); the record comes through the same adapter in both paths: live's `availability_record(session)` on its store, the run's `availability_record` on the copy in `_load`, passed to `walk` | 243 item 4's term on the fixture's `injury_status` facts (`term_entries`, `classify`, `injury_adjustment`), ON only when the slot is on AND the record holds something at t; OFF otherwise, printed per era | none (`V22_FACTORS`: v22's factor inputs are not as-of; no history is manufactured) | `test_253_row_4_the_match_factors_come_only_from_the_record_in_both_paths`, `test_253_row_4_the_adapter_reads_no_record_while_the_tables_are_absent_and_refuses_otherwise` |
| (5) Simultaneous kickoffs | production prices a same-kickoff pair from one state; the walk with `batch_same_kickoff=False` (the default, soccer_backtest.py:97) updates between them | `as_of`, `visibility` | the builder takes an instant, never a fixture: no row with kickoff at or after `visibility_bound(t)` (itself at or before t − RESULT_LAG); `by_instant` groups fixtures by kickoff, ONE snapshot per instant, in `walk` and `predict_live_slate` alike | the shared snapshot | the shared snapshot | `test_253_row_5_simultaneous_kickoffs_share_one_snapshot_in_both_paths` |

**The rule for row 5, stated:** the snapshot for every fixture kicking off at instant t is one snapshot, built at t; it
holds no match kicking off at or after `visibility_bound(t)`, which is at or before t − `RESULT_LAG_HOURS` (and under
"day" at or before t's UTC midnight), so no fixture of an instant sees the result of another fixture of the same
instant, nor of any game still within the lag. Same-kickoff fixtures share one snapshot.

**Where the record has nothing (row 4):** the term is OFF in both paths for that instant, and the harness says so per
era (competition-season): `availability_lines` prints, for each era, how many fixtures had the term on and how many
had it off and why; the walk carries it (`walk(...)["availability"]`), `run_lines` prints it on every verdict (after the strata, and
before an INVALID verdict's line), the run record carries it (`result.availability`), and `--preflight` prints it for
the scored set before any run. The record's tables are not on main (252's schema PR is
built in another worktree): the adapter `availability_record` answers `NoRecord` while both are absent, so v23 runs
with the term off everywhere today; a store holding one table without the other, or both, refuses (open question 23).
The tables are not created here.

**Each test perturbs the input the way the old paths diverge** (row 1: a stored context planted in the store's
ModelVersion row, two values; row 2: a promoted club's PRIOR-season results changed; row 3: a whole later season added;
row 4: a synthetic injury row and lineup rows planted in the store, and a synthetic record (253 item 2(b): synthetic
rows in a synthetic store are allowed) with an entry recorded before the decision instant, a backfilled observation
recorded after the kickoff, facts recorded after the decision instant (one minute after it, thirty minutes before the
kickoff, at the kickoff) and one exactly at it, a backfilled fact recorded BEFORE the decision instant (no cadence
declared, a cadence it exceeds, a cadence it meets), a reader returning a late fact and a source-clock read; row 5: a same-kickoff pair, one result rewritten
9-0) and shows the replay (the one builder, `predict`, and `walk` memo on and off) and live
(`predict_live_slate` on the store) agree bitwise: every snapshot field for field (sha included), every prediction dict
(probabilities, xG, over/under and every info value). Mutation probes (not committed): live ignoring a given record,
the walk building one snapshot per fixture, the late-fact check removed, the facts read at the kickoff instead of the
decision instant, the backfill exclusion removed, and the walk's snapshots assembled by a second implementation each
turn these tests red.

**v22's arm under this harness, per row:** it keeps v22's own inputs as v22 defines them (training.py's context
formulas, the ladder, estimate_strengths with the backfill, the promoted default, predict_match with the stored ρ),
read from the same snapshot as soccer-v23, so the comparison is like for like; its three labelled readings stand (the
90-minute score on an AET / PEN league row, open question 22, RULED AS BUILT by addendum 254 item 3 Q22 (a); the backfill's tie order, 17; under LEAGUE_REGULAR a
play-off row out of its history, §4 Admission); it reads no factor
(row 4). v22 itself, its code and its production path do not change.

## 5. The scored set and the pot

- **Scope (slot):** every admitted row of a LEAGUE-type competition at or before the cut ("LEAGUE"), or only the
  regular rounds ("LEAGUE_REGULAR"), by `soccer_expansion.placement`'s three values and the whole of its F3 rule: a
  "regular" label is scored; a "playoff" label is left out BY CAUSE; a label it cannot place (NULL, empty, or any form
  other than "Regular Season - N", e.g. "Apertura - 3") REFUSES — "A label the code cannot place refuses the run
  (never guessed); the architect confirms the placement from --preflight before the run." The preflight lists, per
  competition-season, the regular count, the play-off labels and the unplaceable labels with their counts, and gives
  no fingerprint while any walked label cannot be placed; the run refuses before the fingerprint and the reservation;
  `scored_rows` itself raises rather than drop. Cups are not priced by v23 (production prices them through
  `cup_strengths`); a cup scope would need its own design.
- **The within-season skip is zero** (`WITHIN_SEASON_SKIP`): no prior-count condition exists. Each competition's first
  pot season is scored under the weak prior, or excluded by cause as a warm-up (slot `first_season`); neither is a
  within-season skip.
- **INVALID cannot arise from coverage:** both arms price every scored row.
- **The cut (slot):** it must clear every fence; the run calls each with `through = cut` and refuses on any refusal:
  `pl_availability.fence_refusal` (strictly before 2026-11-02T20:00Z, the window's opening) and
  `soccer_expansion.guards_backtest` with the leagues' window fence (at or before 2026-10-30T15:00Z for BL1, at or
  before each declared league's declared_at).
- **The pot:** "16,546 matches / 24 competitions" is printed as a label, never a pass condition. The scored ids and
  their sha256 are written by `registry.record_run`.
- **The stream fingerprint** ("soccer-v23 stream fingerprint v2"): the walked rows' fields in walk order (the history
  in the declared stage scope), the scored ids, the slots, v22's stored poisson params, the design's constants, the
  snapshot version and every as-of read of the availability record the walk makes (one per decision instant: state,
  reason, clock, facts, excluded; Codex on #832, round 1: a copy whose record differs is a different stream).

## 5a. The context gap (251 item 2)

**The finding (D8):** the soccer gate's walk scores v22 under the default context (soccer_backtest.py:200,
`CompetitionScoringContext()`: g 1.4, b 1.15); production reads the stored trained context (training.py:514), fitted
on the whole training pot; neither is as-of. 251 item 2 requires this design to define g and b IDENTICALLY in its
harness and its production path, choosing between an as-of estimate from the prior finished games in both and a
frozen pre-pot context in both, and to say why.

**The choice: AS-OF, in both** (`soccer_v23.CONTEXT_DEFINITION`, verbatim):

> as-of (addendum 251 item 2): g and b (the v22 arm's CompetitionScoringContext) and soccer-v23's fitted mu and h are estimated at each fixture's instant from the admitted finished rows visible under the declared visibility rule, and from nothing else, in the harness and the production path alike; the stored trained context is never read; the default context only where the competition has no visible row (production's own fallback), and G0 and B0 as frozen constants, never pot figures: the first season's prior centre, G0 also setting that season's prior precision (K_PRIOR·G0) and, in every window, beta's weak prior precision (BETA_PRIOR_PRECISION = K_PRIOR·G0)

**Why as-of, not a frozen pre-pot context:**

- It cannot leak. At a fixture's instant t the snapshot holds only the admitted rows visible under the declared rule
  (a result known before t, at kickoff + `RESULT_LAG_HOURS`; under "day" also a kickoff before t's UTC date, §4); g
  and b are computed from those rows and nothing else, so no game of
  the pot at or after t enters them. The stored context is the leak 251 item 2 names: fitted on the games the walk
  scores (Option 2, rejected).
- It keeps early season honest. A competition's first rows are priced on what was known then, which is what the
  scored set's skip of zero (216 item 3) exists to measure; a pot-wide or end-of-pot figure would price August with
  May's totals.
- A frozen pre-pot context needs a pre-pot window for every competition, and the store has none to give: the walk
  reads every admitted row of the copy at or before the cut, so each competition's earliest stored season is its first
  pot season (`first_seasons`; the `first_season` slot scores it or excludes it as a warm-up). There is no finished
  game before the pot from which to freeze a context; the only pre-pot numbers are the frozen defaults G0 = 1.4 and
  B0 = 1.15, which would be the default context 251 item 2 names as the gap, not a fix for it.
- It is identical by construction, not by two implementations kept in step: the harness (`walk`) and the production
  path (`predict_live_slate`) both call the ONE function `predict` on a `Snapshot` built by the ONE builder (§4,
  §4b): one admission predicate and one visibility rule (tested equal, field for field, digest included).

**What "g and b" mean for each arm:**

| Arm | g and b | Read from | As-of |
|---|---|---|---|
| soccer-v23 | the jointly fitted **μ and h** of the fixture's window (§1: log λ_H = μ + h + …, log λ_A = μ + …); reported beside the average team's implied g = (e^(μ+h) + e^μ)/2 and b = e^(μ+h)/g (reported only; the pricing adaptor's context is (1, 1) and carries no g or b) | c's visible rows of seasons S−1 and S | yes: the fit sees only the snapshot |
| v22 (re-walked) | the `CompetitionScoringContext` that the REAL `estimate_strengths` and `predict_match` receive: g = total goals / (2 × matches), b = home mean / g clamped to [1.0, 1.30] (training.py:196-214's formulas) | c's visible rows of every season (production's own formula, applied as-of) | yes: the snapshot's rows only |

The only constants in either: the default context where c has no visible row at all (production's own fallback,
training.py:217) and G0 / B0 as the centre of v23's first-season prior (§1), G0 also setting that season's prior
precision and β's weak prior precision in every window (`BETA_PRIOR_PRECISION` = K_PRIOR·G0); all frozen numbers,
never a pot figure. Live production's stored context is never read by either arm or either path.

**Tests** (tests/test_soccer_v23_harness.py): the harness's walk and `predict_live` give identical g, b, μ, h and
probabilities, bitwise, for the same fixtures at the same instants on the synthetic store, both arms, with a poisoned
stored context in the store's ModelVersion row that neither reads; the leak test: every row at or after the instant
rewritten (and future rows added, in the rows and in the store) changes nothing at t, bitwise, while one visible row
changed moves g, b, μ and h (the positive control); the block's latest kickoff is strictly before the visibility bound;
a game still in play at t (kicked off inside the lag: one hour before t under "kickoff", the previous evening for a
fixture just after UTC midnight under "day"), planted in the rows and in the store, moves nothing in either path,
while the same game planted one second outside the lag does (its positive control).

**v22 re-walked (251 item 2):** the run walks both arms through the same `walk` on the same scored set, under this
same definition and the same skip (zero), and records soccer-v23's pot log-loss and v22's re-walked one side by side
with v22's recorded figure (§6). v22's recorded gate figure STANDS as measured and is never recomputed: no v22 figure
on the frozen pot is machine-readable in the repository (law 1, read on main 44c8fceb: docs/registry/experiments.json's
soccer-s19-time-decay, soccer-dc-fit and soccer-s14-stage2 hold PL-pooled deltas only, and soccer-expansion-v1 holds
per-league figures on five leagues' 2024/25 + 2025/26; BACKLOG records v22's 2026-09-21 promotion "on 16,546 matches /
376 teams" with no log-loss), so it is a declaration slot pair the architect fills at 11-20: `v22_recorded_log_loss`
(the figure, as recorded) and `v22_recorded_source` (where it is recorded). The run refuses while either is null.

## 6. THE BAR (written before any result; `soccer_v23.BAR_TEXT`, sha256 pinned in tests/test_soccer_v23_text.py)

Rewritten by 251 item 2 (D8: "THE BAR, so it never loosens: v23's pot log-loss must be at least 0.0050 below BOTH
v22's recorded figure AND v22's figure re-walked on v23's harness; a tie on either is a rejection"), still before any
result:

THE BAR (ARCHITECT, addendum 216 item 3; addendum 230 item 1(d); addendum 248 item 2(b); addendum 251 item 2), written before any result: soccer-v23's mean three-way log-loss on the frozen pot must be at least 0.0050 BELOW BOTH v22's recorded figure AND v22's figure re-walked on soccer-v23's harness. PASS iff BOTH (v22's recorded mean three-way log-loss − soccer-v23's mean three-way log-loss) ≥ 0.0050 AND (v22's re-walked mean three-way log-loss − soccer-v23's mean three-way log-loss) ≥ 0.0050, every figure unrounded. v22's recorded figure STANDS as measured and is never recomputed: the run reads it from the declaration slot v22_recorded_log_loss, which the architect fills from where v22's gate recorded it and names in v22_recorded_source. v22's re-walked figure is v22 walked by the same harness beside soccer-v23, on the identical scored set, under the same context definition (as-of: g and b, and soccer-v23's mu and h, estimated at each fixture's instant from the finished games visible before it under the day visibility rule (addendum 254 item 3 Q4: a game kicking off on a UTC date before the fixture's), a game visible only once its result is known, at its kickoff plus RESULT_LAG_HOURS = 4 hours, the bound a result is known, frozen by the declaration; the stored trained context never read; for the v22 arm, the default context (g 1.4, b 1.15) only where the competition has no visible game, which is production's own fallback (training.py:217), and for soccer-v23, G0 and B0 as frozen constants, never pot figures: the first season's prior centre, G0 also setting that season's prior precision (K_PRIOR·G0) and, in every window, beta's weak prior precision (BETA_PRIOR_PRECISION = K_PRIOR·G0); neither fallback is a pot figure; in the harness and the production path alike; "v22 re-walked" is v22 on THIS harness, not live v22 reproduced: both arms read the harness's admitted rows, an AET or PEN league row at its 90-minute score where live v22 reads the full score, so on a store holding such a row it differs from live v22, by about 3.7e-4 in a probability on the design's synthetic one-row probe (a synthetic receipt, not a pot figure; the run record counts the AET and PEN rows; addendum 254 item 3 Q22)) and the same within-season skip (zero). The recorded figure is read from the slot as measured, by whatever scorer its own gate used, and is never recomputed; the re-walked figures (soccer-v23's and v22's, on this harness) are computed by soccer_backtest.soccer_calibration. Each comparison is decided by soccer_backtest.candidate_gate_verdict with min_delta = training.DEFAULT_PROMOTION_DELTA (0.005). Written as "below", so a tie on EITHER is a rejection: a difference of zero, or any difference under 0.0050, on either comparison REJECTS; a difference of exactly 0.0050 passes that comparison. INVALID, never a pass, when the two arms' scored sets differ, are empty, or number under MIN_GATE_N = 30 (soccer_backtest.compare_candidate). The early-season matches are INCLUDED in the scored set: this candidate's declared within-season skip is zero (no 40-match skip). RPS and Brier are printed for the record and gate nothing; the market is a reference, never a feature, and gates nothing. One run, on the architect's word, on a .backup copy opened mode=ro&immutable=1. No date moves this bar.

**The decision path** (`soccer_v23.decide`, the only one): `compare_candidate(v22 re-walked, soccer-v23,
DEFAULT_PROMOTION_DELTA)` scores both arms of the walk on the identical scored set (INVALID stays INVALID) and decides
the re-walked comparison; `candidate_gate_verdict(v22_recorded_log_loss, soccer-v23's log-loss,
DEFAULT_PROMOTION_DELTA)` decides the recorded one; PASS only when both PASS. The result carries `v23_log_loss`,
`v22_rewalked_log_loss`, `v22_recorded_log_loss` (with `v22_recorded_source`), both deltas and both verdicts side by
side; `run_lines` prints them on three lines; `registry.record_run` records them.

**Tests** drive `run()` itself, the walk replaced by synthetic arms and the recorded slot set per case, the
log-losses computed by `soccer_calibration`: below both by 0.0100 (PASS); at the bar on both, the smallest float
difference at or above 0.0050 on each (PASS); below the recorded figure but a tie on the re-walk (REJECT); below the
re-walk but 0.0049999 from the recorded figure (REJECT); a tie on the recorded figure (REJECT); one float step under
0.0050 on the re-walk (REJECT); one float step under 0.0050 on the recorded figure (REJECT); and an INVALID walk stays
INVALID whatever the recorded figure. `decide` is also pinned directly on the same cases, and `run()`'s `min_delta` is
`training.DEFAULT_PROMOTION_DELTA` = 0.005. A test runs 0, 0.0049999 and 0.0050 through `candidate_gate_verdict` with
the imported constant. There is no other decision path.

## 7. The declaration slots (the architect's, 11-20; the run refuses while any is null)

The declared registry entry carries them as `declaration_slots`; the code holds only the allowed values.

| Slot | Allowed | Recommended (printed, never a default) | Open question |
|---|---|---|---|
| `scope` | "LEAGUE", "LEAGUE_REGULAR" | "LEAGUE_REGULAR" | 2 |
| `first_season` | "score_under_prior", "exclude_as_warmup" | "score_under_prior" | 3 |
| `visibility` | "day", "kickoff" (each with the result known: kickoff + `RESULT_LAG_HOURS` before t, §4) | "day" | 4, RULED by addendum 254 item 3 (the DAY rule, stated in BAR_TEXT); the slot STILL ADMITS "kickoff" and nothing refuses it, against a BAR_TEXT that names the day rule: escalated to the architect, not narrowed here |
| `cut` | an ISO-8601 UTC instant clearing every fence | "2026-10-30T15:00:00Z" | 7 |
| `availability_on` | true, false | false | 6 |
| `v22_recorded_log_loss` | a finite positive number: v22's recorded gate figure, as recorded (measured on v22's own scored set by its own gate's scorer, not on this candidate's pot; never recomputed) | none: the record is the architect's to read (no machine-readable figure exists in the repository, §5a) | 18 |
| `v22_recorded_source` | a non-empty string naming where that figure is recorded | none | 18 |

The entry also carries `gate` (BAR_TEXT, character for character) and `frozen_constants` (§8), and the run refuses
any difference.

## 8. The frozen constants (proposed; the declaration freezes them)

| Constant | Value | Source |
|---|---|---|
| `K_PRIOR` | 5.0 | poisson.py's n/(n+5) shrinkage, reused |
| `G0`, `B0` | 1.4, 1.15 | CompetitionScoringContext()'s defaults: the first season's prior centre; G0 also sets that season's prior precision (K_PRIOR·G0) and β's weak prior precision in every window (`BETA_PRIOR_PRECISION` = K_PRIOR·G0, joint_poisson.py:92, applied at :277) |
| `PROMOTED_ATTACK_MULT`, `PROMOTED_DEFENCE_MULT` | 0.85, 1.15 | v22's PoissonConfig promoted priors, as log offsets on S−1's zero mean |
| `CARRY` | 1.0 | no extra regression of S−1 into S |
| `ELO_SCALE` | 100.0 | conditioning only (β is reported per point) |
| `MAX_ITER`, `MAX_HALVINGS`, `TOL`, `PRECISION_FLOOR` | 100, 60, 1e-12, 1e-12 | the fit's numerics: TOL on the full Newton step max\|H⁻¹g\| (the only convergence test); PRECISION_FLOOR the objective's relative resolution, read only when the line search stalls (Codex on #832, round 1) |
| `V22_MIN_MATCHES`, `V22_BACKFILL_LIMIT` | 30, 500 | training.py:476, :500 (the v22 arm; test-pinned to the file) |
| `WITHIN_SEASON_SKIP` | 0 | 216 item 3 |
| `RESULT_LAG_HOURS` | 4 | when a result is known (§4 Visibility): kickoff + 4 h covers extra time and a shoot-out with margin; the store holds no final-whistle stamp (RULED, addendum 254 item 3 Q4: the bound a result is known, frozen by the declaration) |
| `BETA_PRIOR_MEAN`, `BETA_PRIOR_PRECISION` | 0.0, 7.0 (= K_PRIOR·G0) | β's weak prior on ΔE/100 (§1); no new number |
| `RELEGATED_ATTACK`, `RELEGATED_DEFENCE` | 0.0, 0.0 | no directional prior for a club relegated into the competition |
| `PYRAMIDS` | [["PL", "ELC", "EL1", "EL2"]] | the declared pyramid, top tier first (src/adapters/api_football.py's England LEAGUE codes) |
| `SOURCE_CADENCE_HOURS` | {} (none declared) | 252 item 1's backfill rule: each availability source's feed cadence in hours; a fact recorded later than its `source_stamp` by more than its source's cadence, or carrying a `source_stamp` from a source with no declared cadence, is excluded from both paths (open question 27, RULED AS BUILT by addendum 254 item 3 Q27 (b): a soccer source's cadence is declared by the architect with its feed) |

## 9. The run order (the reservation before any outcome is scored or priced; RULED, addendum 254 item 3)

The order is the two precedent gates' (ARCHITECT 2026-11-04 15:45 ET, addendum 254 item 3: "the run's order matches
the nfl-v2 and NCAA gates' (preflight → fingerprint → cross_ref_guard → reservation → walk → record)"), checked
against both, line by line: `--preflight` is its own earlier invocation in all three (cli.py's `nfl-v2-gate`,
`ncaa-gate`, `soccer-v23-gate`); `run()` loads the outcome-bearing stream (the rows with their goals) and computes and
compares its fingerprint BEFORE the reservation (nfl_v2_gate.py: load :655, fingerprint :667-668, `reserve` :678;
ncaa_v1r_gate.py: load :798, fingerprint :799-800, `reserve` :824; soccer_v23.run likewise); `registry.cross_ref_guard`
runs inside `reserve()`, before the exclusive create (nfl_v2_gate.py:427, ncaa_v1r_gate.py:301, soccer_v23.reserve
likewise); then the walk; the caller records. What holds is therefore "the reservation before any outcome is scored
or priced": the goals are read and fingerprinted before it, as in both precedents, and nothing is fitted, scored or
priced before it. (The earlier heading put the reservation before any outcome was read; that was inaccurate and is
corrected here.) ONE SUB-STEP DIFFERS, named and not changed (addendum 254 item 3 rules the order the precedents
share; this is not among its steps, and the architect says whether it moves): both precedents refuse a MISSING
`--stream-fingerprint` before the load (nfl_v2_gate.py:642, ncaa_v1r_gate.py:792); soccer-v23 refuses it only at the
compare, after `_load` (one check, "no fingerprint or one that does not match"). Either way nothing is reserved.

`soccer-v23-gate` refuses, reserving nothing and recording nothing, when: there is no entry, its status is not
declared, `run` is not null, or a reservation exists; a slot is null or invalid; the entry's constants or gate differ
from the code's; the word is empty; `--db` is missing or fails `nfl_v2_gate.check_db` (outside data/, not the app's
database, never created, no -wal/-shm/-journal); the copy holds more than one soccer_elo_poisson row marked
production (never the newest picked; Codex on #832, round 1) or its production version is not v22; a fence refuses at
the cut; under LEAGUE_REGULAR a walked row's stage label cannot be placed; a club's arrival cannot be placed on the
declared pyramid; the fingerprint is missing or does not match. Then `registry.cross_ref_guard`, then the reservation
(`docs/registry/soccer-v23.started.json`, exclusive create, written and fsynced with its directory, removed if the
write fails), then the walk (both arms: v22 re-walked beside v23), `compare_candidate`, `decide` (both comparisons,
§6) and `registry.record_run`. A failure after the reservation leaves it standing (the pot may have been read; open
question 13). The run record carries addendum 254 item 3's two labels
(`record_labels`): the day rule's residual (Q4, its count not computed: no chain run time is declared in code for this model's live
path; the systemd timers and soccer_expansion.SYNC_CHAIN_TIMERS are other jobs' chains) and
"v22 re-walked" as v22 on this harness, with the rows read at their 90-minute score counted (Q22).

`--preflight --db COPY` fits nothing and prices nothing: the slots, the constants, the bar, the context definition
(251 item 2), v22's recorded figure as the slots carry it, the copy's production
version and params, the counts per competition and season with each first season, the stage census (regular, play-off
and unplaceable labels with counts, per competition-season), the arrivals that cannot be placed, the scored n, the
thin seasons
(a competition-season with no home or no away goal: a window holding only those refuses the fit), the fences and,
last, the fingerprint. With no declared slots it loads nothing; while a stage label or an arrival cannot be placed it
gives no fingerprint.

## 10. Code's readings (law 1), each checked against main 54833460 (the 251 lines against 44c8fceb)

- **No registry entry in the design PR:** tests/test_leagues_declaration_220.py limits statuses to {declared, run,
  confirming, closed, production}, and an undeclared candidate holds none. The bar text lives in `BAR_TEXT` and §6.
- **Every roadmap step has a real date** (src/roadmap.py refuses a non-date `due`): the PASS shadow and the read are in
  `live_needs`, not steps.
- **The sidecar refusal** lives in `nfl_v2_gate.check_db` (it wraps `mlb_pitchers_gate.check_db` and adds the
  -wal/-shm/-journal refusal); v23 uses it and its `db_session`.
- **The fixture age is measured in hours,** shown as days to one decimal (`f"{EARLIER} {d / 24:.1f} d before (...)"`);
  v23 copies the categories and the string, never an integer N.
- **Production's backfill can read later seasons** on a replay (`Match.season != season`, no date bound,
  training.py:489-500); the v22 arm bounds it at the snapshot.
- **The first-season prior** converts b coherently (μ0 = ln(g·(2−b)), h0 = ln(b/(2−b))); reusing b as a ratio would
  repeat 216 item 1's mismatch.
- **DC at pricing only** is coherent at a fixed ρ (§1).
- **`predict_match` prices v23 through the adaptor** exactly (§1).
- **The stage rule is F3's whole rule:** `soccer_expansion.placement` returns None for NULL, empty and unmatched
  labels (soccer_expansion.py:94-105), and F3 says such a label refuses; `is_regular` alone would drop them silently.
- **"Relegated" appears nowhere in v22's promoted logic:** a club absent from a competition's S−1 rows is not always
  promoted; in ELC the clubs relegated from the PL arrive the same way, so the design reads the direction from the
  other competitions' S−1 rows on a declared pyramid.
- **Production's backfill tie order** is undefined in SQL (`ORDER BY utc_date DESC`, no tie-break); SQLite returns
  ties id-ascending, which the arm follows (§4).
- **The context the gate's walk reads** is `CompetitionScoringContext()` (soccer_backtest.py:200) and production's
  is the stored trained context (training.py:514: `contexts.get(competition_code, CompetitionScoringContext())`, the
  `contexts` of `_train_fresh_soccer`, training.py:195-217); v23's harness reads neither (§5a).
- **No final-whistle stamp is stored:** `schema.Match` holds `utc_date` (the kickoff), the scores, `home_score_90` /
  `away_score_90` and `status_raw`, and no finished-at or recorded-at column; "a result known before t" is therefore a
  declared lag after kickoff (`RESULT_LAG_HOURS`, §4).
- **Live v22 reads the full score on AET / PEN rows** (training.py:170-180 `_to_train`, 196-214 the contexts, the
  strengths input): `home_score` / `away_score` include extra-time goals (schema.py's comment on `home_score_90`);
  soccer_backtest's default walk reads them too, and only `confirmation_scoring` substitutes the 90-minute score.
- **The availability record's tables are not on main** (`git grep` for `availability_observations` /
  `availability_assertions` on origin/main a9ee265f finds nothing; `schema.py` holds no such class): the adapter reads
  the store's table list and answers "no record" while they are absent; the column names are never taken from the
  ruling's text (open question 23).
- **The old factor tables are overwritten in place** (`schema.Injury`: "We refresh by deleting all rows for a team and
  re-inserting — the upstream feed is the source of truth and we don't try to track injury history"; `schema.Lineup`:
  "all rows of the match are deleted and rewritten"): neither is an as-of input, so neither path reads them.
- **No v22 figure on the frozen pot is machine-readable** in docs/registry/experiments.json, BACKLOG.md or the specs
  (§5a): the recorded figure is a declaration slot pair.
- **The roadmap's done-marks** are written by the records PR after a merge (the nfl-v2 and mlb-pitchers lanes'
  precedent), so this PR appends the lane with every step open.

## 11. Open questions for the architect (needs-ruling; none settled by Code; 4, 18, 20, 22, 27 and 28 ruled by addendum 254 item 3; 8 settled by 251 item 2; 22 raised by the review of the 251 follow-up; 23-26 raised by 253 item 2(d); 27 by the review of the five rows; 28 by Codex round 1)

**RULED by addendum 254 item 3 (ARCHITECT 2026-11-04 15:45 ET): 4, 18, 20, 22, 27 and 28 (the reservation order),
each marked below with its one-line quote.** The rest (1-3, 5-7, 9-17, 19, 21, 23-26) stays open, "ruled by a
dedicated addendum on 11-05" (254 item 3: "each gets a ruling or a named date before 11-20; the PR may merge with them
open, since a slot left null refuses the run and the declaration is mine").

1. **Naming.** May the registry id be `soccer-v23` (the lane's name)? Who owns the "v23" ModelVersion string, given
   pl-availability-v1's promise ("v23 by a ruling and a version bump") and `_next_version_string` minting over
   rejected rows? The engine string `soccer_joint_poisson` is proposed.
2. **Scope.** "The pot's log-loss": LEAGUE-type regular rounds only (recommended), or all 24 competitions including
   cups, which take `cup_strengths` in production?
3. **Each competition's first pot season.** Scored under the weak μ/h prior (recommended, closest to "early-season
   INCLUDED"), or excluded as a warm-up by cause? Neither is a within-season skip.
4. **Visibility.** The day rule (recommended: live morning-chain parity), or strictly before kickoff? Either way a
   row is visible only once its result is known, at kickoff + `RESULT_LAG_HOURS` (BUILT, 4 h, proposed: the store
   holds no final-whistle stamp). Under "day", morning-chain parity holds only for fixtures that kick off after the
   chain's run on their own UTC date (and at least 4 h after midnight); a fixture before the chain's run is priced live
   by the previous day's chain. Is 4 h the bound, and is that parity statement accepted?
   **RULED (254 item 3):** "Q4 VISIBILITY: the DAY rule (morning-chain parity), with `RESULT_LAG_HOURS` = 4 as the
   bound a result is known — frozen by the declaration, stated in BAR_TEXT; the parity statement accepted with its
   residual (a fixture before the chain's run priced by the previous day's chain) LABELLED in the run record, never
   silent." Built: BAR_TEXT states it; `record_labels` labels the residual on every verdict and in the record, its
   count not computed (no chain run time is declared in code for this model's live path; never guessed). NOT FULLY
   BUILT: the `visibility` slot still admits "kickoff" and nothing refuses it (`SLOT_VALUES`, `slots_state`), against
   a BAR_TEXT that names the day rule, so a declaration could contradict its own frozen bar (`record_labels` only
   prints that "kickoff" is not the ruled rule). Escalated: whether the slot narrows to "day" is the architect's; if
   so, in that ruling's push.
5. **Constants.** K_PRIOR = 5; the promoted prior ln 0.85 / ln 1.15 (it sat on v22's deflated scale); the S−1 carry
   1.0; β's weak prior (BUILT, a proposed ruling: centred at 0, precision K_PRIOR·G0 on ΔE/100, every window), or
   centred at a declared constant, or β fixed at 0 below a declared minimum of rows (a count switch, which 216 item 2
   argues against)? An unpenalised β is not offered: on synthetic first seasons it priced fixtures at p ≈ 1.0.
6. **Availability.** In the shadow, ON or OFF (recommended OFF until pl-availability-v1's verdict)? Must v23's counted
   class be exactly pl_availability's rule? May the 60-game v23 shadow overlap the pl-availability window on the same
   PL pages?
7. **The cut.** At or before 2026-10-30T15:00Z leaves out the PL 2026/27 rounds after it. Accepted?
8. *(Settled by 251 item 2, removed: the v22 arm is v22 re-walked on this harness, as-of, and the bar is against
   BOTH it and v22's recorded figure.)*
9. **Prior reads.** v22's ρ and c were selected on this pot, and S19, dc-fit, s14 and soccer-expansion-v1 read it. Is
   that tilt toward v22 accepted as conservative?
10. **Fencing v22's reads.** Should ordinary `soccer-backtest` reads of the pot be fenced while soccer-v23 is declared
    and unrun?
11. **The lane's `competitions` field.** Written ["PL"] (216 item 3: the PASS shadow is on the host's PL pages; every
    lane carries the field, tests/test_roadmap.py), or every scored league?
12. **Gate output in the PR body.** The PR is gate-class but a run is forbidden before 11-20, so the body pastes the
    synthetic test receipts instead. Is that the right content?
13. **Failure after the reservation.** Built conservatively: a failure mid-walk leaves the reservation standing (the
    nfl-v2 gate's "from here on, the one run is spent"). Or remove it on a failure (#798's shape for a failed write),
    which would permit a second attempt after outcomes were read?
14. **Thin seasons.** A competition-season with no home or no away goal makes a window the fit cannot converge on, and
    the run would stop after the reservation; the preflight names them. Is a refusal the ruling, or an exclusion by
    cause?
15. **Relegated clubs.** BUILT, a proposed ruling: a club arriving from a higher tier of the declared pyramid carries no
    directional prior (0 / 0); the promoted prior stays for arrivals from below or from outside the store. Or a
    declared relegated prior of its own? Is `PYRAMIDS` (PL > ELC > EL1 > EL2) the right declaration, and is a refusal
    the ruling for an arrival off the pyramid?
16. **Unplaceable stage labels.** BUILT: under LEAGUE_REGULAR any walked label `placement` cannot place refuses the run
    (F3's rule), and the preflight names each with its count. Should the architect rule a label's placement, the
    ruling is a code change through this PR's successor, never a guess.
17. **The v22 arm's tie order.** Production's backfill tie order is SQL-undefined; the arm reads SQLite's id-ascending
    order (pinned). Accepted as "v22's" for the bar?
18. **v22's recorded figure (251 item 2).** BUILT as two slots (`v22_recorded_log_loss`, `v22_recorded_source`): no v22
    figure on the frozen pot is machine-readable in the repository (§5a). Which record is "v22's recorded gate figure"
    (the improve gate's figure at v22's 2026-09-21 promotion, held in the database's ModelVersion row and not in the
    repository, or a soccer-backtest walk under the default context)? Whichever it is, it was measured on v22's own
    scored set (soccer-backtest's 40-match skip and the default context, or the improve gate's holdout), not on this
    candidate's (skip zero, the declared scope): the recorded comparison crosses scored sets, which "BOTH" accepts as
    written. It was also computed by that gate's own scorer, not necessarily `soccer_calibration` (the improve gate's
    holdout uses `evaluation.score_1x2`, which clamps each probability at 1e-12 without renormalising; `soccer_calibration`
    renormalises first): the bar reads the slot as measured and says so. Confirm, and fill both slots.
    **RULED (254 item 3):** "the improve gate's figure at v22's promotion of 2026-09-21, as the laptop's ModelVersion
    row holds it — read by MY BLOCK on a fresh .backup copy ... and written into the two slots at the 11-20
    declaration with its source string." As built: no code change; both slots stay null until the declaration and
    the run refuses while either is null (`slots_state`; pinned by `test_the_run_refuses_in_order_and_records_nothing`).
19. **The re-walked v22 arm's context window.** BUILT: g and b over the competition's visible rows of EVERY season
    (production's own training.py:196-214 formula, applied as-of), while soccer-v23's μ and h read seasons S−1 and S.
    Both are as-of from the prior finished games. Is every-visible-season the reading of "v22 re-walked" the ruling
    intends? Restricting v22's arm to S−1 and S would change v22's definition, which 251 item 2 forbids ("nothing
    about v22 changes"), so it is not offered.
20. **A competition's first fixture.** With no visible row in the competition, the v22 arm reads the default context
    (production's own fallback, training.py:217) and soccer-v23 centres its first-season prior on G0 / B0: the only
    places a fixed number stands in for an as-of estimate, both frozen, neither a pot figure (G0 also scales the
    first season's prior precision and β's weak prior precision in every window, K_PRIOR·G0: frozen, never a pot
    figure; the review of the five rows found BAR_TEXT's earlier "only as the first season's frozen prior centre"
    untrue to joint_poisson.py:92/:277, and the text was corrected before any declaration). Accepted under
    `first_season` = "score_under_prior"? BAR_TEXT states this fallback in its context parenthesis, as
    `CONTEXT_DEFINITION` and the code do.
    **RULED (254 item 3):** "the v22 arm's default-context fallback is production's own (training.py:217) and
    soccer-v23's G0/B0 prior centre is a frozen constant; neither is a pot figure; BAR_TEXT states the fallback as
    corrected." Built: BAR_TEXT's parenthesis now names the v22 arm's fallback with training.py:217 and says "neither
    fallback is a pot figure".
21. **The finding Issue.** 251 item 2 files it with the parity PR (248 item 2(a)), `Refs #789`, `Refs #786`. This PR
    names it once it has a number; until then it cites #656 and #789 only.
22. **The v22 arm on AET / PEN league rows.** BUILT (labelled, §4 Admission): both arms read the admitted rows, where
    an AET / PEN row carries its 90-minute score; live v22 and v22's own gate walk read the full score with extra-time
    goals in the context, the strengths input and the Elo ladder. "v22 re-walked" can mean (a) as built: the harness's
    rows for both arms (like for like with soccer-v23, the confirmation convention), or (b) the full score for the v22
    arm's context, strengths and ladder (closer to live v22; its own ladder and a second row field), the 90-minute
    score kept for the outcome. Which?
    **RULED (254 item 3):** "(a) AS BUILT — both arms on the harness's admitted rows (the 90-minute score), like for
    like with soccer-v23, the confirmation convention." Built: BAR_TEXT's parenthesis and the run record
    (`V22_REWALKED_LABEL`) say "v22 re-walked" is v22 on this harness, not live v22 reproduced, with the ~3.7e-4 (the
    synthetic probe's largest probability difference, 3.66e-4, a synthetic receipt) labelled as such; the record counts
    the rows read at their 90-minute score, scored and in the walked history.
23. **The record's reader, once its tables exist (253 item 2(d), row 4).** BUILT: the adapter `availability_record`
    answers "no record" while addendum 252's two tables are absent (today), refuses a store holding one without the
    other, and refuses a store holding both until it calls 252 item 2's query function (the schema PR's; "there is no
    second path"), whose columns it reads from the merged schema, never from the ruling's text. Once 252's migration
    reaches the laptop's database, `soccer-v23-gate` refuses (before the reservation) until that follow-up lands. Is
    the follow-up to land before the 11-20 declaration, and is refusal (not "no record") the right answer meanwhile?
24. **The era of the per-era line.** BUILT: an era is a competition-season; the term's state is decided per fixture
    instant (the record can begin mid-season), and the line counts fixtures with the term on and off, with the reason.
    Is competition-season the era 253 item 2(d) means?
25. **The record's facts as the term's entries.** BUILT: a fact of kind `injury_status` is one entry (type = its
    status text verbatim, position verbatim, fixture age by the receipt's `fixture_age` on our match id and the stored
    kickoff the observation carried); other kinds (`projected_starter`, `confirmed_starter`, `inactive`, `depth_rank`,
    `eventual_starter`, `plays_for`) are no input of soccer-v23, which has no lineup or XI term; an unmapped team's
    fact is noted and counts for nothing. A fact is read when recorded at or before the snapshot's decision instant
    (252's "<= T" with T = `visibility_bound(t)`, open question 27, RULED AS BUILT by addendum 254 item 3 Q27 (a));
    one recorded later, at the kickoff included, is
    read by neither path. Accepted, and which soccer source and attrs key carry the type when a soccer feed is named?
26. **The v22 arm and the record.** BUILT: the v22 arm reads no factor (live v22's factor tables are not as-of); on
    the pot soccer-v23's term is off too (no record), so the bar's comparison is factor-free on both arms. In the PASS
    shadow, with `availability_on` true and a record present, soccer-v23 would carry a factor the v22 arm does not.
    Is that the intended asymmetry for the shadow's beside-v22 read, or should the shadow compare against live v22?
27. **The facts' cut-off and the backfill cadence (raised by the review of the five rows).** BUILT, conservatively: (a)
    the availability record is read at the snapshot's DECISION INSTANT, `visibility_bound(t)`, the rows' own bound
    (under "day" the fixture's UTC midnight, the morning chain's reading; under "kickoff" t − 4 h), never at the
    kickoff, so replay and a live call made at or after it read the same record content by construction and no
    match-day poll (252's T-60 .. T-0) enters either path. Is that the cut-off, or a declared lead before kickoff
    (which would admit late polls, and require the live call after it)? A call before the decision instant is the
    labelled residual (§4 Visibility). (b) 252 item 1's backfill rule is applied by the builder in both paths: a fact
    recorded later than its `source_stamp` by more than its source's declared cadence (`SOURCE_CADENCE_HOURS`, frozen
    by the declaration) is excluded, counted and labelled; NO cadence is declared (252 names no soccer source), so any
    fact carrying a `source_stamp` is excluded until its source's cadence is declared with its feed; a fact with no
    `source_stamp` is read by the recorded clock alone. Is exclusion (not refusal) the ruling, and who declares a soccer
    source's cadence?
    **RULED AS BUILT (254 item 3):** "(a) the DECISION INSTANT, `visibility_bound(t)`, is the cut-off ... (b)
    EXCLUSION with count and label, not refusal ... a soccer source's cadence is declared by ME with its feed". No
    code change.
28. **The reservation and the pot's outcomes (Codex round 1, P1, escalated).** `run()` loads and fingerprints the
    outcome-bearing stream before `reserve()`, as both precedent gates do (§9). **RULED (254 item 3):** "THE
    RESERVATION ORDER: the run's order matches the nfl-v2 and NCAA gates' (preflight → fingerprint → cross_ref_guard
    → reservation → walk → record)". Verified: the two precedents agree with each other, and soccer-v23 agrees with
    both on every ruled step (§9, file:line); no order changed; run()'s docstring and §9 now say "before any outcome is
    scored or priced". One sub-step differs and is named for the architect, not changed (§9): the precedents refuse a
    MISSING fingerprint before the load (nfl_v2_gate.py:642, ncaa_v1r_gate.py:792); soccer-v23 only after `_load`.

## 12. What is NOT done

No v22 recorded figure is filled (slots, the architect's at 11-20); no change to soccer_backtest.py (the sibling
parity PR's optional `context` parameter is not depended on: this harness never calls the soccer gate's walk).

The availability record's tables are not created (252's schema PR builds them); the adapter's reader of a present
record is not built (it waits on 252 item 2's query function, open question 23); no soccer feed writes the record, so
the term is off in both paths everywhere today.

No run of v23 on any real data; no result; no declaration; no registry entry; no ModelVersion; no change to v22, its
constants, its path (poisson.py, training.py, soccer_backtest.py, elo.py, factors.py untouched), any existing bar or
threshold, or any roadmap date. The market is read nowhere.
