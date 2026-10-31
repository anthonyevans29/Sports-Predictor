**2026-10-31 — BUILT (ARCHITECT 2026-10-31 11:45 ET, addendum 190 items 1-3 and 7, #507): mlb-pitchers-v1 declared in the registry with its harness — the as-of module, the ON arm behind one backtest flag, the 2026 fence, the freeze and the one-run gate. Nothing run, no cohort frozen. No bar moves.**
- **The ruling:** addendum 190 verbatim is in #747's fragment (docs/ledger/entries/2026-10-31-191-roadmap.md) and in docs/specs/mlb-pitchers-v1.md section 1; not re-quoted here. The snapshot finding (item 5) is Issue #746.
- **Item 3, the entry:** `mlb-pitchers-v1` appended to docs/registry/experiments.json at the addendum's instant (2026-10-31T15:45:00Z), status declared, run, verdict and test_cohort null; the gate is item 3 verbatim (its sha256 pinned by a test); arms, cohort, metric, bar, live_needs (item 4), snapshot_note (item 5's last sentence, #746), prior_reads_note, ratified.
- **Item 7, the harness:** src/walters/mlb_pitcher_asof.py (the #702 receipt's logic moved unchanged, the receipt's console byte-identical; `classify`, `cohort_ids`, `pitcher_stats_asof`, `missing_starter_shrink`); `backtest.run_backtest(pitcher_layer=...)` (one flag; the default pinned against a verbatim copy of today's walk); src/walters/mlb_pitchers_gate.py and the commands `mlb-pitchers-freeze --db COPY`, `mlb-pitchers-gate --db COPY`. The ON arm is pinned equal to the live `_generate_predictions_mlb` on rows equal to the as-of sums; training.py is not modified.
- **Item 2, the cohort:** frozen by the operator's `mlb-pitchers-freeze` on a `.backup` copy before the run (the files committed in a PR, the 10-09 soccer cohort precedent); the run refuses unless its own re-classification gives the same 1553 ids.
- **Item 3, the fence:** `run_backtest(pitcher_layer=True)` on MLB 2026 (or every season) refused while the entry is declared and unrun, and while it is absent; the gate's walk excepted by sealed_read after its reservation; lifted by the recorded run; OFF never fenced.
- **The --db fence (law 5):** the copy is refused under the code checkout's `data/` and, run from a git worktree, the main checkout's; a hard link into a `data/` is refused by identity; both readers open the percent-encoded `mode=ro` URI. An unreadable registry refuses and fences by name; a record that fails after the verdict printed exits 2 naming the spent reservation.
- **Code's readings, named for the architect** (docs/specs/mlb-pitchers-v1.md section 4):
  - (a) the cohort file's name is the registry's confirmation-cohort path (`{eid}.cohort.txt`); harmless: it is stored under `test_cohort`, never `confirmation_cohort`, and `freeze_confirmation_cohort` already refuses this entry (not confirming; after a PASS, no confirmation_plan), so it cannot overwrite the file. No extra refusal added.
  - (b) confirmation: none (`confirmation_window` says so, `confirmation_plan` null); the entry is hand-written because `registry.declare` requires a plan.
  - (c) the scored set is the cohort exactly: a cohort game either arm cannot price makes the run INVALID, printed with its ids and recorded, never scored on a subset.
  - (d) the missing-starter shrink (Phase 12.3) is in the ON arm, "the live path's own fallbacks"; park factor and the market blend are in neither arm.
  - (e) the bar reads >= literally: exactly 0.0050 passes; "a tie" is a tie of the arms, which rejects.
  - (f) MLB has no Elo: "the same Elo state" is read as the same run-profile history, profiles and production config, one walk.
  - (g) the freeze is a separate command run before the run on the same copy, its files committed before the run.
  - (h) ruled (addendum 192 item 2): the lane's state "declared" lands in #747; registry_id "mlb-pitchers-v1" lands in this PR after #747 merges (both touch docs/roadmap.json).
  - (i) a FINISHED cohort game stored with equal scores scores y = 0 in both arms (today's walk's `home_score > away_score`); none is expected (MLB resumes suspended games); the harness neither refuses nor relabels one.
  - (j) the operator's 10-31 counting block (a wrapper on the receipt module's `read_game`) counts 0 on this code (the receipt imports `reconstruct` from the module); the freeze's console line "both sides on a live path N" is the same figure and the freeze refuses unless it is 1553.
- **Codex round 1 on #748 (four findings).** Three were fixed in this PR's own code:
  - P1, the sealed read: `run_backtest(pitcher_layer=True, sealed_read=True)` suppresses the 2026 fence only when the gate's reservation exists (`mlb_pitchers_gate.sealed_refusal`). The flag alone is refused like the fenced walk.
  - P2, the freeze: a ledger save that fails after the cohort file is written removes the file, leaves test_cohort null, and refuses.
  - P2, the #329 guard: its cohort kind reads `test_cohort` when there is no `confirmation_cohort` (`registry._guard_state`), so a ref whose ledger froze the test cohort holds a cohort.
- **For the architect (Codex round 1, P1, not built):** the run checks the cohort's ids, not the copy. A different or replaced `.backup` copy whose 1553 ids are unchanged, but whose scores, earned runs or production config differ, would be read. Code's proposal: the freeze records a fingerprint of what the run reads (the 2026 MLB match rows, the 2026 appearance and participant rows, the production MLB model row), and the run refuses before its reservation unless the copy reproduces it. Not built: it adds a refusal to the declared run (190 item 2 names the ids check only), so it waits for a ruling.
- **Codex round 2 on #748 (three findings).**
  - P1, the model family, fixed: the gate's `production_config` reads the live MLB family's (`training._family_for`) one production row, refuses two, and refuses when the walk's row is another row. The walk's row is `backtest._load_production_config`, the newest production MLB row of any family, kept as today's query so OFF stays today's backtest. A test covers a newer production row of another family.
  - The two P2s go to the follow-up Issue #749 (review stop rule, addendum 7 item 2): a partial reservation write, and a non-numeric cohort token, each a traceback. They are also listed for the architect, since #749 item 1 can spend the one run without a read.
- **RULED (ARCHITECT 2026-10-31 13:15 ET, addendum 193), verbatim:**

> ARCHITECT 2026-10-31 13:15 ET — addendum 193: #748 (the mlb-pitchers-v1 harness) — Codex's P1 on the copy's identity RULED IN; #747 merges now.
>
> 1. THE FINGERPRINT — RULED IN, Code's proposal as written: the freeze records a fingerprint of the rows the run reads — the 1553 games' ids, kickoffs and final scores; the pitcher_appearances rows the as-of reconstruction reads for them; the production config the OFF arm runs with — and the run REFUSES before its reservation unless the copy it is given reproduces it. A mismatch is a finding on #507 (the copy is not the frozen one), never a re-freeze and never a run on the other copy. This is the NCAA gate's precedent (its frozen fingerprint stood through a stored-data change on 10-29) and it is what law 3's "one read" means when the read is on a copy: the ids check says which games, the fingerprint says which data. The freeze and the run stay on the same .backup copy in my block, as documented; the fingerprint is what makes that a check rather than a habit.
> 2. The three round-1 fixes stand as pushed (the gate flag passes the fence only under the gate's own reservation; a failed freeze leaves nothing; the cross-ref guard sees a cohort on another branch).
> 3. #747 at 05fd8c3 carries addendum 192 as ruled (the two NHL steps, the pitcher lane declared with registry_id null, live_needs' sentence): CI green, clean — the operator merges it now (block_1031_merge_747.txt). After the merge #748 sets the lane's registry_id to mlb-pitchers-v1 with the entry, as Code planned.
> 4. #748 then: the fingerprint in the round-2 push with its tests (a swapped copy with the same ids and one changed score refuses; the frozen copy passes); the review rounds under the cap; my merge block; the freeze-and-run block on the laptop 11-06 on a fresh .backup copy outside data/, my text.

- **193 item 1, built:** `mlb_pitchers_gate.fingerprint`, stored as `test_cohort.fingerprint` by the freeze. The run recomputes it on its copy and refuses before the reservation on any difference, naming the parts. It is a finding on #507, never a re-freeze. The parts:
  - games: every 2026 MLB match row the walk and the reconstruction read, a superset of the cohort's ids, kickoffs and scores, because the walk's profiles read every game;
  - appearances: the attributed appearance rows;
  - starters: the starting_pitcher rows, per the proposal as written;
  - config: the production version and the baseball_config.

  Tests:
  - a copy with the same ids and one changed score refuses, and so does one with a changed earned run or another production config;
  - the frozen copy runs;
  - a frozen cohort with no fingerprint refuses;
  - the same rows in another file give the same fingerprint.
- **193 item 3, done:** after #747 merged, docs/roadmap.json's mlb-pitchers lane carries `registry_id` "mlb-pitchers-v1", with the entry (state "declared" from #747).
