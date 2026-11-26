# Experiment registry and the confirmation doctrine (#212)

**Ruled** (ARCHITECT 2026-10-01, external review): "experiment registry
(candidate, training cutoff, scored match ids, prior reads) + DOCTRINE: a gate
pass is followed by a declared future-confirmation window before production
(NFL's two-week ratification generalized). Existing verdicts unchanged."
**2026-10-02:** "the registry (#212) records every candidate from here."

## The ledger

`docs/registry/experiments.json` is tracked in git and reviewed in PRs. It never
lives under `data/`. Each run's scored match ids go in a sidecar file,
`docs/registry/ids/<id>.txt`, alongside their count and sha256. The module is
`src/walters/registry.py`.

| Step | When | What it records | Refuses |
|---|---|---|---|
| **declare** | in the candidate's PR, **before any run** | id, sport, lane, candidate, the frozen declaration document, training cutoff, test set, gate, the **confirmation window** (prose) AND its executable **confirmation_plan** {n_games, metric, bar, must_beat_reference, reference} | an incomplete declaration or plan; a duplicate id |
| **run** | the ONE scored run | scored match ids, result, **prior reads** (every earlier run on the same test set or with overlapping ids) | a run of an undeclared id; **a second run of the same id** (a test set is read once) |
| **verdict** | the architect's ruling, verbatim | PASS / FAIL / REJECT / WITHDRAWN | a verdict without a run |
| **cohort** (optional; intl-elo-v2) | as soon as the schedule holds the window | the confirmation COHORT: the first n_games eligible fixture ids, chosen whatever their status (never from available results), frozen once (sidecar `<id>.cohort.txt` + sha256). The read must then score exactly this set; a pending label leaves it incomplete, never replaced (review on #248, 2026-10-02) | a second freeze; anything but exactly n_games distinct ids; a test-set id |
| **substitution** (frozen cohorts) | when a cohort fixture becomes UNSCOREABLE (cancelled / abandoned; awarded / walkover) | ARCHITECT 2026-10-02: the fixture is RELEASED and replaced by the next eligible fixture after the cohort (61st, 62nd …), recorded with the raw provider code as reason and evidence ("unscoreable is the criterion, not the status label"); the frozen file never changes, the effective cohort applies the substitutions | evidence that is not a cancelled or finished-unscoreable fixture (a postponed or unplayed game stays); no raw code; a released id returning; a replacement already in the cohort or from the test set |
| **confirmation** | after the declared window | the confirmation READ: its scored match ids (sidecar `<id>.confirm.txt` + sha256) and result; the outcome is **computed** from the plan (metric <= bar and, when required, < the reference on the same games; a tie fails; a plan whose bar is **null**, admitted only with must_beat_reference true and a named reference, reads metric < the reference alone, strict: ARCHITECT 2026-11-23, addendum 449 item 6(b)), never stated | outside a window (no PASS); a scored set that is not exactly the frozen cohort (when one is frozen); fewer games than the plan; any game starting before the verdict; any game from the scored test set; a result without the plan's metric (or the reference's) |

**Prior reads** make a test set's history visible. A candidate that wins on a
test set read five times before says so in its own record. NHL's 2025 test set
has five prior reads already (v1 through v5).

## The confirmation doctrine

1. A gate **PASS is not production.** The entry moves to `confirming`.
2. Every declaration names its **confirmation window** before the run: future
   games the model never saw, the read that confirms it, and what would not
   confirm it. NFL's two-week ratification is the template.
3. Production follows only when the window closes with a recorded,
   **computed** CONFIRMED outcome that carries its scored ids and result
   (`production_allowed()`). An immediate or incomplete confirmation is
   refused. Review on #222 (2026-10-02) reproduced declare → run → PASS →
   CONFIRMED in one second; the regression test pins that it now fails.
4. A NOT_CONFIRMED outcome closes the entry. The bar does not move.
5. **An entry whose run record holds the opening** (`confirmation_opens_after`, the leagues windows: ARCHITECT
   2026-11-22, addendum 447 item 3 C1(b)): the first confirmation game is not earlier than the opening's kickoff
   (both to the second with the Z, compared as strings, 448 item 1(d)), never verdict.at; and a first game AT that
   kickoff carries `first_game_id` above the opening's match id (ARCHITECT 2026-11-23, addendum 467 item 1(a)); a
   later kickoff compares no id. The reader holds the order; the registry is the backstop, and
   `confirmation_refusal` reads the same checks before a reservation (`leagues-confirmation-read`). Three guards
   on the backstop, RULED IN by ARCHITECT 2026-11-25, addendum 540 item 1 Q5, each ONLY for an entry that holds an
   opening (every other entry keeps today's rule, a test for each saying so): (a) "A missing ids file REFUSES the
   record. A file that is not there is not an empty set (law 4), and the scored-set check must not pass on
   nothing."; (b) "n_games EQUALS the plan's 60. '60 more' is a number, not a floor."; (c) "first_game_id is one of
   the confirmation's ids." They are guards, like 448 item 1(f) and 467 item 1(a), not policy.
6. **The cross-ref guard's kinds** (#329) include the confirmation record (the ledger's `confirmation` with
   `ids/<eid>.confirm.txt`) and the confirmation reservation (`<eid>.confirm.started.json`): ARCHITECT 2026-11-22,
   addendum 448 item 1(f). A confirmation recorded on an unmerged laptop branch refuses that entry's later guard
   calls until it is merged.
7. **The leagues' confirmation read, its five questions RULED** (ARCHITECT 2026-11-25, addendum 540 item 1; lane
   leagues, #322). Q1: ONE invocation; the outcome is the computed one, "NO WORD OF MINE ABOUT THE OUTCOME IS TAKEN
   IN ADVANCE": `--ruling` is the addendum that orders the read, by number and date (never an outcome), and a word
   or ruling naming CONFIRMED or NOT_CONFIRMED refuses before any load; the preflight computes no figure and
   reserves nothing. Q2: NO KEY in the confirmation result ("a record is never rewritten, and a rule that may be
   amended does not belong in one"); a CONFIRMED read prints one console-only line, stored nowhere, that production
   on a leagues entry turns on no call (220 item 3; 505 item 2(c)). Q3: a window member re-dated past the opening
   refuses the read before its reservation, naming the game; it lifts only by the architect's registry write naming
   the game in the entry's one `ruled_exclusions` list, and the game is then out by its named cause and takes no
   slot. Q4: that one list, unchanged; an item added after the window's verdict changes nothing that the window's
   recorded fingerprint or any guard reads again: each of them holds a FROZEN COPY of the list as the window read
   it (the run record's `ruled_exclusions`, the window fingerprint over the items read, recorded in the run record
   and the reservation, and the guard's "run record" kind, which compares that run field), and nothing re-reads or
   recomputes any of them after the verdict, so an item added later changes none of them (the run's ids file holds
   only the 60 ids). Addendum 505 item 2(c), verbatim, standing:
   "no league leaves the shadow list for calls without its injury sync, or without an exemption that I rule by the league's name".

## A live model's certification (addendum 214)

**ARCHITECT 2026-11-02 10:15 ET, addendum 214 item 4(b)** (verbatim): "THE REGISTRY: nfl_elo_v1's entry gets the
regression line verbatim (stream 676, the 70–80% band 7.7pp, #775 issuecomment-6580087145) and the state "UNCERTIFIED —
shadow, confirmation window (addendum 214 item 3)", with the window's definition and bar written in."

- **The entry:** `nfl-elo-v1`. Its gate predates the registry (the NFL phase-2 gate, frozen 2026-09-09; PASS that
  day; LIVE from Week 3, 2026-09-22). On the complete 2024 warm-up (#775) the same gate reads FAIL, so its verdict is
  `VOID` (the earlier PASS kept under `was`), its `regression` holds the before and after figures, and its
  `certification` is the ruled state. The window and its bar are addendum 215 item 1's: every NFL regular-season and
  postseason game with a kickoff strictly after 2026-11-02 15:15Z that reaches FINISHED with a stored close, through
  the Super Bowl, read once after 2027-02-08.
- **The status vocabulary has no "uncertified".** The entry's status is `confirming` (a forward confirmation window,
  a shadow, never a call), the closest that keeps production off. `production_allowed()` refuses any entry whose
  `certification` starts with UNCERTIFIED. With no executable `confirmation_plan` (the bar is two criteria against the
  window's own baseline, not one fixed number), `record_confirmation()` and `freeze_confirmation_cohort()` refuse it.
- **Where it is read:** an entry's `model_version` is the id a predict path writes (`nfl_predict.MODEL_VERSION`).
  `registry.uncertified_live()` finds the entry that withholds that model. `cli.py coverage`, the Cockpit's Today tile,
  then reads its competitions as not LIVE: `MARKET-ONLY`, with `shadow v1` from the confirming `nfl-confirm` lane.
  Addendum 217 item 5: "the tile reads the registry". The Desk's own market-only rule is
  `desk_policy.NFL_MARKET_ONLY_RULE` (#778); the registry entry changes no Desk call.

## The live models' records (addenda 298 and 299)

**ARCHITECT 2026-11-08 16:25 ET, addendum 299 item 3** (verbatim in part): "(a) the registry lookup is keyed by FAMILY
and version, never by the bare version string [...] `certification_of(family, model_version)` resolves them; a lookup
without the family stays "unread". (b) The certification TEXT is never written by hand: each entry quotes, verbatim and
dated, the promotion record that put the model live [...] If no such record exists for a model, the entry is NOT
created".

- **The key:** an entry that names a model carries `family`, the closing family string (`SOCCER`, `MLB`, `NFL`, as
  `deploy/hosting/closing.py` FAMILIES spells it), beside `model_version`, the bare id the rows carry (`v22`).
  `registry.certification_of(family, model_version, *, path=None)` matches both. No family reads "unread"
  (`NO_FAMILY_WHY`). `uncertified_live(model_version, entries, family=None)` keeps its bare match when no family is
  given (the coverage tile's read): that can only find more withholding entries, never fewer.
- **soccer-elo-poisson-v22:** the live soccer model. Its `certification` is the BACKLOG entry of its 2026-09-21
  re-promotion, quoted (line wraps folded, nothing else changed), with the commit that wrote it (`record_commit`).
  It was never declared, run or ruled in the registry, which postdates it: those fields are null (law 4), its status is
  `production`, and `production_allowed()` reads it as no PASS verdict. It sits first in the file, before every
  declaration, because its date precedes them all.
- **No MLB entry.** No promotion record for MLB v2 exists in BACKLOG.md or in git history (v2 was live before either
  begins), so the MLB line keeps reading "certification not read".
- **nfl-elo-v1** gained `family: "NFL"` and nothing else; its line reads as before.

## Run records are never rewritten

**ARCHITECT 2026-10-02:** "never rewrite a run record". A run record's stored
prior-read count is what its machine computed at record time. When a laptop
computed it before an earlier run was spliced into its ledger, the entry gains
an annotation, `ledger_count_at_record` (plus a one-line `ledger_count_note`),
beside the untouched run block. **The live count is the ledger's**
(`registry.prior_reads`). The first case is nhl-v7: 5 recorded, 6 in the ledger.

## Retired test sets (doctrine, binding)

**ARCHITECT 2026-10-02** (verbatim; from the external review, now binding):
"the 2025 test season has been read 7 times. After v8 it is RETIRED as a test
set; any later NHL candidate declares 2026-27 (as it accrues, >=600 games) as
its test season."

| Test set | Reads | Last candidate allowed | Declare instead |
|---|---|---|---|
| NHL 2025 (2025-26 regular season; nhl_backtest TEST_SEASON, train 2024) | 7 before v8 (v1–v5 seeds, v6, v7); v8 is the 8th | `nhl-v8` | NHL 2026-27 regular season, as it accrues (≥ 600 games) |
| NCAA FBS 2025 regular season (CFBD both-FBS labels; warm-up 2024) | `ncaa-elo-v1r`, once (ARCHITECT 2026-10-09, addendum 24) | `ncaa-elo-v1r` | the NCAA FBS 2027 regular season as it accrues (2024-2026 training; declared in the off-season with its spread pre-check) (addendum 24 named the 2026 season, retired since by addendum 302; pointed on to 2027 by addendum 358 item 6(1)) |
| NCAA FBS 2026 regular season as it accrues (CFBD both-FBS labels; training and warm-up 2024 and 2025) | `ncaa-elo-v2`, once (ARCHITECT 2026-11-09, addendum 302) | `ncaa-elo-v2` | the NCAA FBS 2027 regular season as it accrues (2024-2026 training; declared in the off-season with its spread pre-check) |
| NFL 2025 regular season + postseason (nfl-backtest's scored window; warm-up 2024, preseason excluded) | v1's gate run and its re-runs, and the four R-track variants (ARCHITECT 2026-11-23, addendum 465 item 4(b)) | `nfl-elo-v1` | the NFL test season that the gate-class addendum of 465 item 4(a) rules (by Friday 2026-12-18; no season is named here before it) |
| NFL 2025 regular season + postseason (285 games on the corrected stream, #775; warm-up 2024 complete, 285; preseason excluded) | v2's run, once (ARCHITECT 2026-11-23, addendum 465 item 4(b)) | `nfl-elo-v2` | the same |

- **The college sets.** Addendum 24 item 2(b) retired 2025 with ncaa-elo-v1r's FAIL. Addendum 302 retired 2026 with
  ncaa-elo-v2's FAIL; item 3, verbatim: "2026 is RETIRED as a college test season; NCAA is MARKET-ONLY; the 2027
  candidate declares in the off-season." The 2026 refusal went into code by addendum 309 item 6 (#901). Each set is
  keyed on its last candidate's `test_set`, exactly, and the refusal names the ruling (`registry.RETIRED_BY`).
- **The NFL set** (ARCHITECT 2026-11-23, addendum 465 item 4(b), verbatim: "NFL 2025 IS RETIRED AS A TEST SEASON: read
  by v1's gate run and its re-runs, the four R-track variants and v2's run; 215 item 2 said it is read once ... it is
  keyed into registry.RETIRED_TEST_SETS under BOTH stored test_set strings, v1's and v2's ... 2024 is not retired: it
  was never a test set, and it stays training data."). One season, two stored strings, so two keys, each with its own
  entry as the last candidate. The refusal names no season to declare instead (`registry.NFL_INSTEAD`): 465 item 4(a)
  rules the candidate's test season by a gate-class addendum by Friday 2026-12-18, and no season is named before it.
- **The key is exact, and a new set's wording is ruled at its declaration** (ARCHITECT 2026-11-12, addendum 358 item
  6(2), verbatim: "The exact `test_set` string STANDS as the key: a declaration is my ruling, so a re-worded 2026
  college set cannot be declared without passing me"). No fuzzy key.
- **A refusal never sends a candidate to a retired season** (addendum 358 item 6(1), verbatim: "a refusal that sends
  a candidate to a retired season is wrong on its face"): the 2025 set's "declare instead" names 2027, as the 2026
  set's does.

- **Enforced in code:** `registry.RETIRED_TEST_SETS`. `declare()` and
  `record_run()` refuse any id other than the last allowed one on a retired
  test set, and the refusal names what to declare instead.
- **Why:** each read of a test set spends it. After many reads, a "pass" on
  that set is selection, not evidence. The prior-read count shows the cost;
  retirement stops the spending.

## Pre-registry verdicts

The verdicts already on record are seeded unchanged: NHL v1–v5, S19, DC-fit,
S14 stage 2 and cups fix-v2. Their scored ids were not recorded, and the
ledger says so; nothing is reconstructed. They count as prior reads of their
test sets.

## CLI

- `python cli.py registry`: the ledger, read-only. One line per entry with
  status, result, verdict and prior-read count.
- `python cli.py registry --id ID`: one entry in full, including its prior
  reads.
