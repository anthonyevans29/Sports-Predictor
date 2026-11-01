# pl-availability-v1 — the PL availability candidate (declared ARCHITECT 2026-11-01 10:05 ET, addendum 198)

Lane `pl-availability` (docs/roadmap.json), finding #754, registry entry `pl-availability-v1` (docs/registry/experiments.json). Code: src/walters/pl_availability.py (the rule, the arm, the fence, the grader's second arm, the window reader and the one read), scripts/pl_availability_window.py.

## 1. The ruling, verbatim (the head, the receipts paragraph and items 1-5)

Item 6 (two standing lines) is carried by #759 and is not this lane's; it is not quoted here.

> ARCHITECT 2026-11-01 10:05 ET — addendum 198: THE PL AVAILABILITY CANDIDATE DECLARED (lane pl-availability; the finding #754; the receipts of 09:47 and 09:50 ET on #754), and two standing lines.
>
> THE RECEIPTS, READ. (a) Exposure, the host at v1.6.1, Sunday 14:47Z: 134 stored entries over the 20 PL teams; the model scores all 134 as missing their next match (seven clubs at the 25% cap); the rule of 196 item 3 scores 10. By type: Missing Fixture 110, Questionable 24. By the fixture named: 117 past, 17 next. (b) Lineups, four provider reads: of the 46 names the Saturday pages listed as missing, 6 started, 10 sat on the bench, 30 were absent. Cross-referenced against (a)'s per-entry lines: of the 16 available players, 14 carried a "Missing Fixture" entry naming an EARLIER fixture — a previous PL game, or a UEL/CL game where "Off the roster" means not registered for Europe (Doucouré, Guessand, Lerma, Madjo, Aarons, Forster, Jebbison, Sánchez) — and 2 (James, Stach) were "Questionable" for Saturday's own fixture. The two Bournemouth players with "Missing Fixture" entries naming Saturday's fixture (Araújo, Scott) were absent. The feed is right about the fixture it names; the model reads every entry as being about the next one.
>
> 1. THE CANDIDATE, declared at 2026-11-01T15:05:00Z — v22 with ONE classification rule, tightened from 196 item 3 by the receipt: an injury entry counts as a player missing a fixture only if its type is exactly "Missing Fixture" AND its fixture_source_id is THAT fixture's (this fixture only — not a later one: a later entry carries the European-squad class the receipt exposed, and the feed publishes this-fixture entries before the slate). "Questionable" entries, entries naming any other fixture, and entries naming no fixture count for nothing. The position weights, the 25% cap, the ingest's 14-day keep and the Desk's one-sided-list rule stay exactly as they are. Registry id pl-availability-v1 (track:model, class:lane, sport:soccer); nothing is retuned, one rule, one candidate.
>
> 2. WHY PROSPECTIVE: the injuries table is wipe-and-replace with no history and the exports carry names without types, so no as-of backtest exists for this rule (law 4: no reconstruction is guessed). The candidate runs as a SHADOW beside v22 on the host's PL pages: every PL slate and closing row carries a second probability set computed by the same model on the same inputs with the rule applied (candidate_probabilities, candidate_version, the candidate's missing counts beside the model's) — never a call, never a Desk input, never a Cockpit call; the grader scores both arms at the same close on the same 90-minute outcome.
>
> 3. THE WINDOW AND THE BAR, pre-committed: the window opens at the first PL kickoff strictly after the shadow's FIRST HOST PAGE (the entry records declared_at = this addendum's instant and window_opens_at = that kickoff, written by Code's PR when the deploy receipt is in hand), and holds the first 60 FINISHED PL games with a three-way close from it, counted as the leagues' reader counts (cancelled / AWD-WO / no close excluded by cause; LIVE or un-ingested waits; postponed by actual kickoff); the Desk's floor and quarantine play no part in membership. The read at the 60th: mean three-way log-loss of each arm, unrounded; PASS only if the candidate's is below v22's by at least 0.0050 (the house bar), less or a tie REJECTS; the close's log-loss printed beside both and gating nothing; Brier and the per-club counts printed for the record. One read; the fence: no other read of either arm on the window until the verdict (guards_backtest's pattern). A PASS makes the rule v23 by a ruling and a version bump (no other change rides it); a REJECT retires the rule and the finding closes with a written no.
>
> 4. v22 STAYS THE LIVE MODEL throughout; the Desk's calls come from v22; the shadows the audit counts (value-side) are unchanged. The declared rule is not applied to any live price before the verdict, by anyone.
>
> 5. FOR CODE (gate-class, one PR, the leagues' export switch as the pattern): the second probability set on the PL rows (slate and closing, host only), the registry entry and the frozen rule, the grader's second arm, the window reader (counts only before 60, the leagues reader's R2), the fence, tests on synthetic injury rows (an earlier-fixture entry counts for nothing; a this-fixture Questionable counts for nothing; a this-fixture Missing Fixture counts; the cap), the roadmap lane (declared; steps: the shadow PR by 11-05, the first host page on the tag after v1.6.2, the 60th game projected from the PL schedule, the one read), the ledger entry. The PR body quotes this addendum. NFL is untouched: its feed is current-status (a different adapter) and its QB rule stands.

## 2. Code's readings (law 1), named for the architect

- (a) **THAT fixture's id.** The rule compares `str(fixture_source_id).strip()` with the match's own
  `external_ids["api_football"]`. A previous provider id (`api_football_prev`, written only by
  `match_dedupe.stamp_rekey` on a twin merge, an orphan merge or relink, or a re-key) does NOT count: the injuries are
  synced wipe-and-replace per team and name the provider's current fixture id at the sync, and item 1 reads "THAT
  fixture's (this fixture only)"; law 4 keeps an unknown out. (#688's receipt labelled a `_prev` match; no src code
  treats one as the same fixture.)
- (b) **The adapter keeps one entry per player** (`api_football.list_injuries`: the entry with the latest fixture
  timestamp). A player whose newest entry names a later fixture (a European game after the PL game, say) has no
  stored entry for this fixture, so the rule counts him for nothing. That is the feed as stored, not a choice here.
  **KNOWN LIMITATION, RULED (addendum 199 item 6):** the candidate under-counts that case; the ingest is NOT changed
  (a dedupe change would move v22's own input list, and v22 does not move). Written into the registry entry
  (`limitation`); if the window PASSES, the dedupe is revisited as part of v23's declaration, not before.
- (c) **Where the arm is priced.** In the same pass as v22 (`training._generate_predictions_soccer`), for PL on the
  host only, and stored in the Prediction row's `factor_breakdown` under `pl_availability_v1`. The export prices
  nothing (it reads the stored row), so this is the one place "the same model on the same inputs" holds exactly, and
  both arms are then graded from one row at one close on one outcome. v22's probabilities and every other
  factor_breakdown key are unchanged (pinned by a test against the laptop pass). The key is removed from every
  exported `factor_breakdown`, on every machine. The local web view (`src/web/routes/home.py`) passes
  `factor_breakdown` whole to its own page; on the host it would show the key there. It is not the Desk or the
  Cockpit, and it is left unchanged.
- (d) **Host only, and absent off it.** The training pass, the rows and the grader's arm all ask
  `desk_policy.not_host_reason()`, the leagues export switch's gate (addendum 178 R6). Off the host the four row keys
  (`candidate_version`, `candidate_probabilities`, `candidate_missing`, `candidate_reason`) and the results row's
  `candidate` are ABSENT, as the leagues lane writes no file or field off the host. On the host, a PL row whose
  stored prediction carries no arm keeps the keys with the probabilities and counts null and `candidate_reason`
  saying why.
- (e) **Rounding.** `candidate_probabilities` are rounded to 4 places on the rows, as `prediction.probabilities`
  is. The read takes both arms unrounded from the stored row.
- (f) **The close and the outcome.** The close is `close.grading_close`, the close the PL grader grades v22 at ("the
  grader scores both arms at the same close"), not the leagues' Kalshi three-way. Membership requires it priced. The
  outcome is `leagues_window.result_of` (the 90-minute score). The grader's per-row arm scores the outcome v22's
  graded row holds; PL has no extra time.
- (g) **Membership causes beyond the ruling's list.** These are excluded by cause and named, as R4 excludes a member
  the candidate cannot price: a game with no v22 prediction stored; a stored prediction of another model than v22
  (the entry's `base_version`); and a prediction with no candidate arm.
- (h) **window_opens_at is a kickoff**, so the game kicking off at it is in the window (`>=`). While it is null, the
  reader refuses.
- (i) **The bar.** PASS when v22 − candidate >= 0.0050, so exactly 0.0050 passes ("by at least"). A tie of the arms
  rejects.
- (j) **THE FENCE'S SCOPE, a ruling question.**
  - Fenced until the verdict is recorded, by `pl_availability.fence_refusal`:
    - the PL 2026/27 walk, or the walk of every season, in `soccer_backtest.run_soccer_backtest` (which `sealed_read`
      does not lift), `backtest.run_backtest` and `soccer-backtest`;
    - the grader's second arm on a window game, and the candidate keys of a FINISHED window game's
      predictions-export row (its row carries the result beside them; `candidate_reason` says withheld);
    - `scripts/soccer_injury_factor_receipt.py` (#430) on PL: it re-prices v22 by its injury lists, the candidate's
      own question, and is not v22's live grading, so a fenced game is left out and counted (`fenced (...)`).
  - The cut is `window_opens_at`. While that is null it is `declared_at`; with no entry it is the addendum's instant;
    an unreadable registry or instant fences the whole season.
  - NOT fenced: v22's production grading on the window. That is `evaluate`, `export-results`' `predicted` / `graded`,
    `results-tally`, the value-side cohort's read and the PL positive-edge receipt. Item 4 keeps v22 live, but item
    3's "no other read of either arm on the window" literally covers v22's live grading. Code fenced neither and asks
    for the ruling.
- (k) **The one read.** `scripts/pl_availability_window.py --read` reserves the read with an exclusive create of
  `docs/registry/pl-availability-v1.started.json`, then scores. It records nothing in the registry: the verdict is
  recorded by Code's PR after the architect reads it.
- (l) **THE COMPARE, a ruling question.** The host-only keys on the `soccer_PL_*` slate files and the
  `soccer_PL_results_*` files make the laptop-vs-host compare print `only in host` on every PL row once the shadow
  deploys. That is DIVERGENT under `compare_exports` as it stands. The compare is not changed here, following
  addendum 185 D3's "THE COMPARE: no change" for the leagues' separate files. The choices are a mask for these keys
  or an explained class. The receipt (a synthetic pair, review round 1): with 10 PL rows a side, the four keys per
  row fill the compare's 40-line diff budget and its 15 printed lines, so a real v22 probability divergence in the
  same file is never printed. Until a ruling, `compare_exports --ignore-keys` (the #420 cutover option) is the only
  existing way to leave them out; Code changes nothing here. Options for the ruling: (a) the arm in its own
  host-only file, as the leagues switch does; (b) a named host-only class in the compare, counted, as the
  unit-bearing mask is.
- (m) **The roadmap's dates.**
  - Step 2 (the first host page on the tag after v1.6.2) is dated 2026-11-06, the leagues lane's v1.6.2 date, as
    the earliest it can be. Owner: operator, who does the deploy and holds its receipt.
  - Steps 3 (the 60th game) and 4 (the one read) carry the same date as a floor, written in their text as NOT a
    projection. `roadmap.validate` requires a real date on every step, and no fixture calendar is in the
    repository; the projection is made from the PL schedule as the database stores it, with a moved line.

## 3. The five questions, ruled (ARCHITECT 2026-11-01 12:05 ET, addendum 199), verbatim

> ARCHITECT 2026-11-01 12:05 ET — addendum 199: #760 (pl-availability-v1, the shadow) — the five questions ruled; one push, then the merge block.
>
> 1. THE FENCE AND v22's LIVE GRADING — AS BUILT. Item 3's "no other read of either arm on the window" fences the WINDOW'S PAIRED FIGURES: the candidate's arm anywhere, the backtest walks on the window, #430's receipt. v22's production grading (evaluate, export-results, results-tally, the value-side n=30 read, the PL positive-edge receipt) is the live model's own ledger and keeps running: it is not a read of the window's verdict, it predates the window and it carries no candidate figure. One line in the fence's docstring says so.
>
> 2. THE COMPARE — option (b): a NAMED, COUNTED host-only class. compare_exports treats every `candidate_*` key as "shadow-arm keys (host-only, pl-availability-v1)": never compared, never printed, counted on its own line beside the unit-bearing count (#735's pattern), so a real v22 divergence in the same file still prints inside the budget. Its own small tooling PR after #760 (stop rule item 5), merged before the compare morning of the tag that carries the shadow (v1.6.3). #760 itself leaves the compare untouched, as built.
>
> 3. THE ROADMAP DATES — projections, said so: "the 60th window game is final" due 2026-12-20 (the PL calendar from the first host page on v1.6.3: six full rounds — 11-07/08, 11-21/22 after the international break, 11-28/29, 12-05/06, 12-12/13, 12-19/20 — a projection from the schedule, not a floor); "the one read and the verdict" due 2026-12-21, owner architect. If the first host page slips or the schedule differs, the dates move with moved lines that day. The 11-06 floor is withdrawn (a floor that reads overdue is noise, not a commitment).
>
> 4. THE THREE EXCLUSION CAUSES — ruled in, as built: no v22 prediction stored; a prediction of another model than v22; no candidate arm (a labelled failure included) — each EXCLUDED BY CAUSE, named and counted, consuming no slot (R4's pattern).
>
> 5. soccer-backtest ON PL WITH NO --season — as built: the fence refuses a walk that would read 2026/27 until the verdict; a PL walk names a season (2025/26 or earlier) until then, and the refusal says so. `--candidate` with no --season running its gate seasons stands.
>
> 6. THE READINGS 2(a)–(i) — all stand, with one recorded LIMITATION: the adapter keeps one entry per player, so a player whose newest entry names a LATER fixture has none for this one and the rule counts him for nothing — the candidate under-counts that case. It is the feed as stored and the ingest is NOT changed (a dedupe change would move v22's own input list, and v22 does not move); it is written into the registry entry and the lane's ledger text as a known limitation, and if the window PASSES the dedupe is revisited as part of v23's declaration, not before. "Exactly 0.0050 passes" is the bar as written (at least 0.0050). The local web view is left as is.
>
> 7. THE PUSH: item 3's dates with their moved lines, item 1's docstring line, item 6's limitation text in the entry and the fragment; CI green; the automatic review's findings handled under the stop rule; then my merge block on the new head. The shadow reaches the host on the tag after v1.6.2; the first host page records window_opens_at; v22's outputs are pinned unchanged by test and stay the Desk's.
