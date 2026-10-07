# Changelog

Human-readable record of what shipped, newest first. Deep detail and the
reasoning behind each change live in `BACKLOG.md`; this file is the summary.
Every drop adds an entry going forward.

## 2026-10-06 (#316: evening-rulings-310 — ARCHITECT, ledger only)
- Records the 2026-10-06 evening rulings verbatim:
  - #310 merges at 99faed0 (follow-up ruling, amending e1a2146);
  - the requirements-install lane closes at that merge (later threads get the closed-lane reply unless they reproduce on the production layout);
  - staged virtualenv declined (#312);
  - #309 and #311 approved;
  - the follow-up approving #314 (with the architect's receipts), #315 and #316.
- No code change.

## 2026-10-06 (#315: mlb-pregame-null-scores — ARCHITECT, daily-class)
- MLB adapter (`src/adapters/mlb_stats_api.py`): when statsapi's coded state is S, P or PW, both scores are null.
  - statsapi sends a pre-game 0-0, which is not a score (law 4).
  - Live and final scores pass through unchanged.
- Test: `tests/test_mlb_pregame_scores.py`.

## 2026-10-06 (#314: desk-started-pass — ARCHITECT, gate-class)
- Desk: a model-sport row whose kickoff is at or before desk `as_of` is now PASS, units 0, `pass_kind` "started", reason "started - never a new call" (#313).
  - It carries no order, no value shadow and no exec block, and it is never a parlay leg.
  - An unknown kickoff is unchanged.
  - The rule has its own switch (`desk_policy.STARTED_RULE`). `base_v11()` turns it off, so the frozen golden holds (0 mismatches).
  - `desk_meta.started_rule` records the switch state.
- Cockpit: a started PASS is tagged "started", greyed like "no reference", and counted in the summary's pass split.
- Tests: `tests/test_desk_started_rule.py` (6). `scripts/cockpit_pass_class_verify.py` gains 3 started checks (19/19).

## 2026-10-06 (#311: kalshi-ed25519 — ARCHITECT)
- `scripts/kalshi_trade_api_probe.py` signs with Ed25519 keys as well as RSA, chosen by key type. Ed25519 signs `timestamp_ms + METHOD + path` directly; RSA stays RSA-PSS.
  - The key file may be PEM or a bare base64 PKCS#8 body (`MC4CAQAwBQYD…`).
  - Other key types are refused, and key material is never echoed.
  - The AUTH receipt names `key_type`.
  - Still read-only (GET only).

## 2026-10-06 (#310: deploy-pip-install — ARCHITECT)
- `sp_deploy` runs `venv/bin/pip install -r requirements.txt` when `requirements.txt` changed in the deploy range. It uses the target tag's file, runs before the checkout, and is printed and receipted (`deploy_requirements`). A failed install refuses the deploy, and the host stays on its release.
- Review fixes (Codex on #310): the install also runs when this host has no successful install receipt for the target's file (bootstrap). It runs in a temporary worktree of the target, so relative includes resolve. A target without `requirements.txt` installs nothing and says so. A failed install warns that the venv may be partially updated.
- Review fixes, round 2 (Codex on #310): an included-file change alone triggers the install. The install record (`requirements.installed`) survives receipt-log rotation. Worktree output is attached to a receipt only when the worktree failed.
- Review fixes, round 3 (Codex on #310): continued lines are joined before includes are parsed. Editable (`-e`) requirements refuse the deploy, because they would point into a deleted temporary tree. The install record names its destination venv or interpreter, so a recreated venv reinstalls.
- Review fixes, round 4 (Codex on #310): continuations concatenate as pip does. The install record lives inside the venv. Symlinked includes are followed. Local-path requirements are refused like editables.
- Review fixes, round 5 (Codex on #310): symlink blobs are not scanned as directives. Bare relative paths, archives and local `--find-links` count as local sources and are refused.
- Review fixes, round 6 (Codex on #310): an allowlist replaces the parsing heuristics. Only plain requirements files auto-install; anything else refuses with the reason and is installed by hand. Checkout blockers are preflighted before installing. A pip launcher that cannot run is a receipted failure.
- Review fixes, round 7 (Codex on #310): `--requirements-installed-by-hand` acknowledges a by-hand install, so a refused release can deploy. The preflight sees renamed destinations and ancestor collisions. A failed install-record write is a receipted refusal. The venv's Python version is part of the install identity.
- Review fixes, round 8 (Codex on #310): by-hand acknowledgements are per release (commit-bound). The dry run honours the flag. A tracked directory replaced by a file is not a blocker. A non-UTF-8 requirements file is a receipted refusal.
- Review fixes, round 9 (Codex on #310): an untracked file inside a tracked directory the target replaces blocks the checkout. Without a repo venv, the install record lives inside the running virtualenv.
- Review fixes, round 10 (Codex on #310): symlinked-directory children; a venv without pip installs via its own python; a failed pip run drops the record; system-site-packages is in the identity; a TMPDIR failure is receipted; per-requirement options are refused; a matching record satisfies a retry.
- Review fixes, round 11 (Codex on #310): empty untracked directories don't block. The by-hand dry run keeps the migration warnings. pip inputs set in the environment refuse auto-install. A failed record write drops the old record.

## 2026-10-06 (#309: desk-rescore-receipts — ARCHITECT rulings recorded)
- `desk-rescore` writes its receipt into `docs/receipts/` (default `desk-rescore-<UTC stamp>.md`; `--out` to name it). It never writes under `data/` and never overwrites: the file is created exclusively.
- Recorded rulings:
  - An edited copy of a migration is a new migration.
  - The migration-plan lane is closed (#305 at 00eac85).
  - The 10-06 K-track receipt stays as partial-window evidence. A FINAL receipt is re-run after 10-08 and committed beside it.

## 2026-10-06 (#307: unl-exploratory-17 — #286 ruling 1 recorded)
- `unl_ladders.EXPLORATORY_MATCH_IDS` pins the 17 exploratory UNL games by match id (31887, 31888, 31890–31904), as ruled. `unl-ladder-receipt --skew-test` no longer refuses on ruling 1.
- `docs/receipts/unl-exploratory-17.md` is spliced from the laptop (operator commit 9d30b5a).

## 2026-10-06 (#306: k-track-receipt-splice — #87 ruling evidence on file)
- `docs/receipts/k-track-2026-10-06.md` is spliced from the laptop (operator commit 687b0f1, ruling (g) on #303). It shows system_matched 3, UNKNOWN 1 (the GB side error), 3 composite NO fills off-book, and venue fee-clear 0/29 NFL · 0/32 NHL · 2/18 NCAA · 0/17 UNL.
- Effect receipt: `desk-rescore` on Sunday's four PLAYs, 0/4 halved (architect state sync).
- 1c-spread share as recorded (architect): MLB/NFL/NHL/UNL 85–99%, NCAA 82%, PL 72% (n=6). Cost model unchanged.

## 2026-10-06 (#305: sweep-migration-rename-age — post-merge Codex finding on #304)
- `sp_deploy` migration plan: a migration RENAMED from another migration inside the deploy range (migrate_temp.py → migrate_x.py) carries the source's age, not the rename commit's. It is now undetermined, never planned at the rename's position. On main, add temp, add y, then rename temp → x planned `run [y, x]`, reversing the real order.
- Review fixes (Codex on #305):
  - Renames are scanned with `-m`, so merge-result renames count.
  - Rename CHAINS through intermediate names (migrate_temp → holding.py → migrate_x) are followed.
  - The scan runs before ordering, so an ambiguous migration is listed once and never in the ordered part.
- Review fixes, round 2 (Codex on #305):
  - Moves no longer depend on git's similarity-based rename detection. A move that also rewrote the file (below `-M`'s 50% threshold) planned `run [y, x]`. Now any commit diff that deletes a migration, or a path carrying a migration's age, taints the paths it adds. A new migration added in a tainted diff is undetermined.
  - Taint follows time (topological order, oldest first). A later reuse of an intermediate name (`holding.py`) no longer reaches back and blocks a valid `[x, y]` plan.
- Review fix, round 3 (Codex on #305): taint only accumulates. A merge that replayed a side branch's `holding.py` (renamed from a migration) as a plain addition used to clear its taint, so a later `holding.py` → `migrate_x.py` planned `run [y, x]`.
- Review fixes, round 4 (Codex on #305):
  - A migration moved onto an existing placeholder path (`--no-renames`: D source + M destination) now carries the source's age. It had planned `run [y, x]`.
  - New migrations with identical content at the target, an unchanged copy of an in-range migration with the source kept, are undetermined. That case had planned `[temp, y, x]`, running one one-shot twice.
  - Recreating a deleted name stays tainted. This errs toward undetermined; the operator orders by hand.
- Review fixes, round 5 (Codex on #305): this replaces the per-path taint scan of rounds 2–4.
  - Any migration deletion in the range (merge parents included) makes every new migration undetermined.
  - A rewritten move of a pre-range migration, and a split copy-then-delete that had planned `run [y, x]`, are now undetermined.
  - The deploy prompt for undetermined migrations says to read each one's history and never re-run a rename or copy. It no longer implies that every listed name runs, and it warns when the range deletes a migration.
- Review fixes, round 6 (Codex on #305):
  - The migration-deletion warning prints on its own. A range that only deleted a migration used to say nothing.
  - The dry run previews undetermined migrations and the deletion warning.
  - An edited copy of a migration stays a new migration. Copying an existing migration and editing it is how new migrations are written, and #304 kept template-derived migrations new.
- Review fix, round 7 (Codex on #305): the deletion warning names the deleted migrations. It points to a range-wide `git log --no-renames --name-status`, never `--follow`, which misses a rewritten move. The plan and the deploy receipt carry `deleted_migrations`.

## 2026-10-06 (#304: post-merge-codex-sweep — post-merge Codex findings on #296 and #297)
- `sp_deploy` migration plan:
  - An UNCHANGED copy of an existing migration (`C100`) is reported with the renames and never planned as runnable. `-M` alone reported it as an addition. A new migration written from an old one's template stays new.
  - Only a migration's FIRST appearance groups it with a commit, so a merged branch's ordered migrations are no longer "added together" just because `log -m` re-lists them in the merge commit.
- `k-track-receipt --ledger` refuses an export whose `calls`, `fills` or `system_picks` is not a list of objects, instead of a traceback.
- The other two post-merge #297 findings (shared city words, the windowed unpriced count) are fixed on #299, which rewrites that code.
- Review fixes (Codex on #304):
  - A copy or rename is suppressed only when its SOURCE was a migration at `before`. A new migration identical to a shared non-migration template stays new.
  - Each migration counts at its LAST addition by an ordinary commit, so a re-added migration keeps its grouping. A merge commit counts only when no ordinary commit added the path.
- Review fixes (Codex on #304, round 2):
  - Copies are decided by CONTENT: a new migration whose file is identical to any migration at `before` is a copy, whichever identical source git would have named.
  - Only an addition carrying the released file's content counts, so a competing branch's different file under the same name never sets the order.
  - An explicit `"fills": null` is refused.
- Review fix (Codex on #304, round 3): when several ordinary additions carry the released file (identical files on two branches, or an identical re-add), the migration is undetermined and the operator orders it.
- Review fix (Codex on #304, round 4): **conservative ordering.** A migration counts only when exactly ONE ordinary commit added it, or none did and exactly ONE merge did. The chosen commits must form a strict ancestry chain, in topological order. Re-adds, competing or identical additions, several merge additions, one shared commit, and parallel branches are all undetermined, and the operator orders them.
- Review fix (Codex on #304, round 5): a merge commit counts as an addition exactly when NONE of its parents had the path (a merge-result addition or re-add). When a parent had it, `-m` is only re-listing that branch's addition. A merge re-add after an ordinary add is therefore a second addition, and undetermined.
- Review fix (Codex on #304, round 6): the addition log runs with `--no-renames`, so a file renamed INTO a migration name counts as an addition of that migration. A rename re-add is therefore a second addition, and undetermined.

## 2026-10-06 (#303: k-exec-addendum — #87 executable edge, Desk v1.1 addendum — ARCHITECT-RULE)
- **Cost = ask + taker fee** (`desk_policy.taker_cost_for`): the contract the order line buys, at its ask, plus 0.07·M·P(1−P) rounded to the nearest cent per fill. The maker cost is shown for reference only.
- **TAKE at the ask by default.** Join-bid applies only at a spread of 3c or more, in the order line, the exec block and the Cockpit's ledger join bid. The 2026-09-30 join-bid doctrine is superseded.
- **Sizing.** A PLAY gets full tier units only when its exec edge is at least 4pp. Otherwise, or with no executable quote, it gets HALF units. Quarantine, floors, tiers and ladders are unchanged.
- **Venue.** The 5pp fair threshold stands, AND the exec edge (book fair − cost) must clear 4pp. A venue call with no executable quote is PASS with no reference.
- **Parlays.** Ticket Π market = Π executable cost; a ticket with an unpriced leg is not offered (counted). Each ticket carries `fair_p`, each leg's `exec_cost`, and the independence-estimate label.
- New read-only `desk-rescore FILES…`: the published PLAYs, re-scored under the addendum at each file's own as_of, showing which would have been halved.
- `desk_meta.exec_addendum` stamps every file. The frozen pre-F1c golden still holds under `base_v11()`.
- New tests: `tests/test_desk_exec_addendum.py` and `scripts/cockpit_exec_addendum_verify.py`.
- Review fixes (Codex on #303):
  - The doctrine, the join price, the cost and the order now share one quote source (`side_quotes`: the contract the order line buys), so a three-way leg-priced pick no longer says "take" while its order joins.
  - There is one join price, bid + 1c at a spread of 3c or more, in both the exec block and the order line.
  - The Cockpit ledger records the file's executable cost and join price, and logs parlay legs at their executable cost (fair kept as `fair_p`), so tickets settle at the price that qualified them.
- **ARCHITECT RULINGS on (a)–(j), 2026-10-06:** (a)–(d) ratified; (e) ratified, to be revisited at the first 30 graded ladders; (f) #218 re-scoped; (g) the receipt file is committed from the laptop by the operator (pending; not in this PR); join at bid + 1c on spreads of 3c or more ratified.
  - **(h) applied:** each order is priced at its OWN contract count (`order_contracts`, as `order_line` writes it), and the 10-contract assumption ends. A 0.25u venue or parlay order is 2 contracts. A PLAY's gate prices the order it places if it clears (its tier units, × 0.5 when kalshi-only). A halved PLAY also reports its emitted order's cost (`order_cost`, `order_contracts`).
  - **(i) applied:** the venue engine backs the best side (largest fair divergence) among the sides that clear BOTH gates.
  - **(j):** unchanged. Parlay ladder legs stay straight-on-pick, and double-chance legs are a v1.2 candidate.
- Review fixes (Codex on #303, round 4):
  - Quote selection is `order_line`'s own: a ticketed side leg is the instrument (unpriceable without an ask), else NO on the opponent's ticketed leg.
  - The fill count is taken at the emitted limit (the join price at spreads of 3c or more).
  - The Cockpit ledger records a halved PLAY's `order_cost` and settles VENUE calls at their executable cost, keeping `kalshi_p` alongside.
  - Pre-addendum files keep their legacy join bid.
  - The receipt is marked pending from the laptop.
- Review fixes (Codex on #303, round 5):
  - The Cockpit's exec marker states only the gate ("exec gate clears / fails"), never a final size.
  - `desk.exec` is present whenever `side_quotes` prices the pick, including NO on the opponent's leg.
  - Value shadows log the file's executable cost.
  - `docs/CLI.md` documents the TAKE / join ≥ 3c limit.
  - `desk-rescore` applies the file's own unit basis and prints it.
- Review fixes (Codex on #303, round 6):
  - `maker_cost` is the join order's (bid + 1c) at the order's own count, and none when the doctrine takes.
  - Quarantine shadows log the file's exec cost.
  - Parlay legs keep their serialized `fair_p`.
  - `desk-parlays` documentation and CLI output describe executable pricing ("Π executable cost", Π fair, unpriced tickets excluded).
- Review fixes (Codex on #303, round 7):
  - A LADDER (which buys NO on HOME) carries no pick-leg exec block.
  - A parlay whose leg has no book reference has `fair_p` unavailable, never Π model.
  - A halved PLAY's maker reference is at the emitted order's count.
  - The Cockpit's Policy card states the #87 v1.1 doctrine: TAKE, executable sizing and the venue gate.
- Review fixes (Codex on #303, round 8):
  - Quarantine shadows' exec is priced at the shadow's size.
  - An explicit `market_p: null` on a parlay leg and an explicit `order_cost: null` (a refused resized order) stay unavailable in the Cockpit ledger. Only absent legacy fields fall back.

## 2026-10-06 (#301: prediction-history — every prediction write kept as a series, #87 K-track — ARCHITECT)
- New APPEND-ONLY `prediction_history` table: `match_id`, `model_version`, `computed_at`, the home/draw/away probabilities, and `recorded_at`.
  - Every `Prediction` insert, from any write path (`predict-nfl`, soccer and MLB predict), is appended at flush in the same transaction. A rolled-back run leaves no history.
  - `predictions` stays current-only (S13). The window chain's hourly re-predicts become a stored series, so model-vs-cost is evaluable per Kalshi capture.
- New `migrate_prediction_history.py`: additive and idempotent, with a receipt. There is no backfill, because overwritten predictions are gone.
  - Before it runs, predictions still write and the skipped history is logged as a warning.
- Chain receipts count `prediction_history`. The count is null until the migration runs.

## 2026-10-06 (#299: fill matcher — doubleheaders by the ticker's start time; three-way NO is composite — ARCHITECT)
- The Cockpit's fill matcher and its Python port (`src/walters/ledger_fills.py`) change together, with parity preserved (`scripts/ledger_fills_parity_verify.py` 30/30).
- **Doubleheaders:** the event ticker's HHMM is the scheduled start in US Eastern time (`KalshiAdapter.ticker_start`, M13; DST via Intl / zoneinfo). Among a fill's candidate calls, those within 3h of it count, nearest first. Without a time the old order stands, and an ambiguous attribution stays flagged. The Cockpit re-parses each stored ticker, so earlier imports gain the start time.
- **Three-way NO:** a NO on an EPL/UCL/FA Cup/UEFA NL HOME or AWAY leg is two outcomes, COMPOSITE. It is never matched to a single-side straight: with a candidate call it is booked off-book ("composite contract — never a straight"); a UNL single with no call stays in the fun book (ruled 2026-09-30). Its held contract stays known for the closing fair. A two-way NO still means the opposite team.
- Tests: `tests/test_fill_matcher_lane.py`; `k-track-receipt` lists composite fills.
- Review fixes (Codex on #299):
  - When the ticker carries team codes, they decide which game a fill fits. One shared title word ("United", "City") no longer stands for team identity.
  - The receipt's unpriced-position count is scoped to the window.
- Review fix (Codex on #299, round 2): a composite NO matches a real LADDER call whose pick is the opposite side. The desk order line executes an AWAY ladder as NO on HOME (X2), so executed ladders reconcile and carry their CLV. A straight still never matches a composite.
- Review fix (Codex on #299, round 3): ticker codes that do not prefix the team name (JAX for Jacksonville Jaguars, BHA for Brighton and Hove Albion) now match through a strict two-team title fallback. Both title teams must fit, on different sides, by whole-word subset. A shared "United" and Man City vs Man United still do not match.
- MATCHER BUG (ARCHITECT 2026-10-06): the ticker suffix names the side. A fill whose resolved role differs from the call's pick is off-book ("side disagrees") and is never matched. KXNFLGAME-26OCT04GBTB-GB yes (Green Bay, AWAY) had been system_matched to a HOME (Tampa Bay) call because "Green Bay" and "Tampa Bay" share the word "Bay". With a ticker role, agreement is role == pick; without one, it is a whole-name subset. Applies to both logged calls and stored predictions. Regression uses the exact fill; parity is 34/34. Reclassified on the operator's ledger, system-matched becomes 3 fills.
- Review fix (Codex on #299, round 4): the ticker's start time now picks the GAME first (the nearest start; tied starts stay together and are flagged), and only then is the pick checked. A disagreeing exact-time game no longer hands the fill to a later game. Parity: 36/36.
- Sweep fix (post-merge Codex on #297): ticker codes must fit both sides AND at least one strongly (by initials or name prefix). Two weak two-letter-initials fits are a same-city collision, not identity: a Giants–Rams fill no longer fits a Jets–Chargers call. Legacy titles without codes now need two different sides. Parity: 38/38.
- Review fix (Codex on #299, round 5): the strict-title fallback also holds the CONTRACT's team (the title's "X wins" team) on the ticker's side of the call. A call with the same teams but home and away reversed never fits. Parity: 40/40.
- Review fixes (Codex on #299, round 6):
  - NO on the TIE of a three-way market is composite (HOME-or-AWAY, `no_on_role` DRAW).
  - A WEAK code fit (only the first two letters prefix the initials) must be confirmed by a title team whose every word is a prefix of the side's name. A strong opponent no longer vouches for it: NYGSEA does not fit Jets–Seahawks. A code that fully prefixes the initials (KC, SF) stays identity.
  - Legacy "A vs B Winner?" titles orient through the other code fitting the call's opposite side.
  - Parity: 46/46.
- Review fixes (Codex on #299, round 7):
  - Title teams are now BOUND TO SIDES. "X wins — Y" puts X on the contract's side. A legacy "A vs B Winner?" title is AWAY vs HOME, per the repo's own fixtures, e.g. BUFKC = "Buffalo vs Kansas City".
  - A weak code is confirmed only by its own side's title team, so a reversed Giants/Jets game never fits.
  - A legacy title orients two non-prefix codes (UGAUNC).
  - Parity: 50/50.
- Review fix (Codex on #299, round 8): the Cockpit flags tied attributions with every candidate (`ambiguous_calls`) on the straight and ladder paths, as the port does. Parity now compares that field: 52/52, and 49/52 on the old Cockpit.

## 2026-10-06 (#298: Desk fee-clear marker — an exact 4.00pp edge clears — ARCHITECT)
- `desk_policy.exec_block`'s `fee_clears` and the Cockpit's "fee-clears?" marker compare with a 1e-9 tolerance (`FEE_CLEAR_EPS`). Before, (0.35 − 0.31)·100 = 3.9999999999999982 read as a miss. Same tolerance as `k-track-receipt`.
- Golden: no edge within 1e-6 of 4pp in `tests/golden/desk_js_v1_1.json.gz`; unchanged, still 15/15. Test: `tests/test_desk_fee_clear_boundary.py`.

## 2026-10-06 (#297: k-track-receipt — the #87 executable-edge receipt, with #75's call-to-fill reconciliation — ARCHITECT)
- New READ-ONLY `k-track-receipt`:
  - **Ladders:** every pre-kickoff Kalshi ladder captured 2026-09-23 → end of 10-07, by sport: spreads, two-sidedness (0 < bid ≤ ask < 1), and the fee-clear rate at taker and maker cost (the Desk's K2 4pp rule; `venue.kalshi_exec` costs), versus the live model's pick and versus the venue engine's book reference, never pooled.
  - **Fills** (`--ledger` reads the Cockpit's ledger export): executed-position CLV and fee-adjusted edge, plus #75's call-to-fill reconciliation, exactly one disposition per eligible call.
- `src/walters/ledger_fills.py` ports the Cockpit's fill classification and executedPositions line for line. `scripts/ledger_fills_parity_verify.py` runs the Cockpit's JS and the port on one ledger: 24/24.
- Tests: `tests/test_k_track_receipt.py`.
- Review fixes (Codex on #297):
  - The predictions table keeps the current row only (upsert). A capture taken before a re-prediction therefore has no model reference: it is reported as "captured before the current prediction was written: no history kept", never silently dropped and never a look-ahead.
  - One-sided and incomplete ladders count as not evaluable on each basis, and their two-sided legs' spreads stay in the distribution.
  - The call window compares full kickoff timestamps.
  - Each reconciled fill prints its ledger id.
- Review fixes (Codex on #297, round 2):
  - The funnel's "cost recorded" reads the recorded-cost fields for every call, MATCHED included.
  - A fill that more than one real call fits (an MLB doubleheader: same teams, same day) keeps the Cockpit's attribution for parity, but is flagged and listed as AMBIGUOUS, never silent. Fixing the matcher itself means using the ticker's start time in the Cockpit and the port together.
- Review fixes (Codex on #297, round 3):
  - Executed-position CLV is restricted to the window's calls, the same cohort as the reconciliation. Positions outside it are counted and excluded.
  - An exact 4.00pp edge clears despite binary-float drift (1e-9 tolerance; `desk_policy`'s fee-clear has the same comparison and is raised separately).
  - A NO on a three-way family's HOME/AWAY leg (two outcomes) keeps the Cockpit's attribution for parity but is flagged COMPOSITE NO and listed.

## 2026-10-06 (#296: host receipts carry the running release; deploy prints the exact migration command — ARCHITECT)
- `sp_common._git` passes `safe.directory` for the checkout. The host checkout is root-installed and the units run as `sp`, so git refused it ("dubious ownership"), `running_release()` returned None, and no receipt carried a release (cutover-readiness criterion (b)). A receipt whose release is still null now carries `release_error` with git's own message.
- `sp_deploy` prints, for each new migration, the exact by-hand command: as `sp`, with host.env loaded, `sp_backup.py daily &&` the migration.
- Tests: `test_running_release_reads_a_checkout_owned_by_another_user`, `test_a_null_release_carries_its_reason`, `test_deploy_prints_the_exact_migration_command`.
- Review fixes (Codex on #296):
  - The migration command runs the new migrations in the order they were added (commit order, oldest first) as one chained `&&` command. Git's alphabetical path order put `migrate_score_90.py` before `migrate_status_raw.py`, which it needs.
  - A rollback or other non-forward deploy prints no runnable migrations. It lists the skipped ones, and modified migrations are listed separately.
  - Test: `test_deploy_migration_plan_orders_by_commit_and_skips_rollbacks`.
- Review fixes (Codex on #296, round 2):
  - The printed command runs `sp_deploy.py --run-migrations m1 m2 …`. It holds ONE DB lock across the daily backup and every migration, runs them in order, stops at the first failure, and receipts each step. A chained `sp_backup.py daily && migrate…` released the lock in between.
  - A migration added in a merge result counts as new (absent at the old head, present at the target).
  - An ancestry check that errors refuses the plan instead of reading as a rollback.
  - An explicit release on a receipt (sp_cutover's dry run) no longer also carries `release_error`.
- Review fix (Codex on #296, round 3): the migration plan is computed before the checkout moves, inside the deploy lock. A planning failure refuses with production still on its current release, and a dry run shows the plan. Test: `test_deploy_plans_migrations_before_moving_the_checkout`.
- Review fixes (Codex on #296, round 4):
  - The printed command carries `--expect <target sha>`. `--run-migrations` refuses, before any backup, unless HEAD is still that release.
  - `--dry-run` with `--run-migrations` refuses.
  - A failed tag or branch lookup makes the release unreadable (null, with `release_error`), never a guessed `UNTAGGED@`/`BETA`.
- Review fixes (Codex on #296, round 5):
  - Migrations added together in one commit, or not placed by the history, have no determinable order. No runnable command is generated; the deploy names them and the exact `--expect … --run-migrations <ordered names>` form to run once the order is decided.
  - A renamed migration is reported (already ran under its old name), never runnable.
  - Migration files are validated under the DB lock.

## 2026-10-06 (#295: CLAUDE.md — quoted heredocs only for PR text — ARCHITECT)
- Standing rule recorded in CLAUDE.md: PR bodies, comments and commit messages are written through quoted heredocs (`<<'EOF'`) only. An unquoted heredoc runs every backticked span as a command; on 2026-10-06 one ran `nfl-grade`, which created an empty DB under the container's data/ (since removed) and blanked spans in #290's body (since repaired).

## 2026-10-06 (#294: UNL skew test v2 — the ten ratified definitions; cutoff moves to the ratification — ARCHITECT)
- `docs/specs/unl-venue-skew-test.md` is now v2. It records the 2026-10-06 ruling verbatim and states every definition. The freeze cutoff moves to `2026-10-06T14:35:31Z` (the ruling's relay on #286); anything inspected before it is exploratory.
- `unl-ladder-receipt` applies the ten definitions:
  - (1) the exploratory 17 are excluded by match id (`EXPLORATORY_MATCH_IDS`; `--skew-test` refuses until all 17 are recorded);
  - (2) book sessions use the venue engine's own rules: at least 4 books, captured no more than 3h before the Kalshi capture and never after it;
  - (5) only the latest capture counts;
  - (6) the receipt refuses without the ticker column;
  - (7) CANCELLED/POSTPONED/STALE_ORPHAN are excluded and listed;
  - (8) one event per board, with the event printed;
  - (9) two-sided means `0 < bid <= ask < 1`;
  - (10) only an exact tie on the favorite excludes a game.
- (4) `sync-kalshi-soccer --competition UNL` refuses any `--max-spread` but 0.10. Every soccer sync prints its max-spread.
- Tests: `test_the_ten_ratified_definitions`, `test_unl_sync_refuses_any_max_spread_but_the_frozen_one`.

## 2026-10-06 (#293: NFL grading — one record definition in nfl-grade and RESULTS.md — ARCHITECT)
- ARCHITECT 2026-10-06: `nfl-grade` and the RESULTS.md NFL section state the record the way the results file does (#290). Rows count from `live_since` onward. A tie is a PUSH, outside the hit denominator; it was a hit for an away pick. Pre-live rows sit under their own heading, never pooled.
- `grade_nfl` returns `games`/`decided`/`hits`/`pushes` and a `pre_live` tally. It skips unscored FINISHED rows (the #289 rule), and `days_back=None` means season to date. Log-loss keeps the gate's tie convention, averaged over live rows.
- RESULTS.md's NFL section reads the season to date, no longer a rolling 30 days. It prints `Sides: **H/D** · pushes P` and a pre-live sub-heading.
- RESULTS.md: a sport whose outcomes carry no log loss prints `Mean log-loss: — (n=0)` instead of raising ZeroDivisionError. The new test's shared-DB run surfaced this.
- Test: `test_nfl_grade_and_results_md_state_the_one_record_definition`.
- Review fix (Codex on #293): `nfl-grade` defaults to the season to date, the stated record. Before, the CLI called `grade_nfl()` with its 8-day default. `--days N` keeps the rolling read. Test: `test_nfl_grade_cli_defaults_to_the_season_record`.

## 2026-10-05 (#292: NFL prediction-set scope check expects bye weeks; Kalshi-only reference's first live fire recorded)
- `nfl_backtest.scope_line(per_week=True)`, used by `predict-nfl`'s prediction set: per week, teams = 2 × games = 32 − byes, each team once. A bye week (e.g. teams=30) no longer raises SCOPE ALERT. Duplicates, more than 32 teams, or non-NFL rows still do. Ratings and backtest keep the 32-team check. Test: `test_prediction_set_expects_32_minus_byes_per_week`.
- Recorded: the Kalshi-only reference fired live (NYY@TB 23:11Z, mid 0.475, spread 1c, +3.1pp → PASS below floor).

## 2026-10-05 (#291: `unl-ladder-receipt`: read-only per-game UNL ladder receipt + the frozen favorite-skew test — ARCHITECT #286)
- New CLI `unl-ladder-receipt` (`src/walters/unl_ladders.py`). Per UNL game after the freeze cutoff it shows the match, legs (bid/ask, spread, two-sided), capture time, series, book probability and favorite gap.
- The sample is the first 30 games qualifying under `docs/specs/unl-venue-skew-test.md`; exclusion reasons are listed. `--skew-test` runs the frozen bootstrap test once the sample is complete. `--out` writes to `docs/receipts/` and refuses `data/`. Read-only.
- Tests: `tests/test_unl_ladder_receipt.py` covers each exclusion reason, the three-leg normalized gap, a deterministic bootstrap (seed 20261005) and the CLI.
- Review fixes (Codex on #291): a leg without a stored ticker makes the series UNKNOWN (never certified by the other legs); an offset-bearing `--since` is normalized to naive UTC; a DB without UNL prints `REFUSED` instead of a KeyError; `--skew-test` refuses unless the frozen cutoff and n 30 are in force.
- Review fixes, round 2 (Codex on #291): a capture stamped exactly at the cutoff no longer qualifies (strictly after); `--n` must be at least 1; the CI keeps full precision, so the verdict and the printed bounds are the same numbers. Cancelled/postponed/stale fixtures in the cohort are escalated (frozen-definition change).
- Review fixes, round 3 (Codex on #291): the bootstrap receives UNROUNDED gaps (rounding is display-only); receipt timestamps keep seconds; the `data/` guard compares the RESOLVED target with the resolved project `data/`, so a symlink or a cwd inside `data/` cannot bypass it (the test uses a temporary stand-in, never the real `data/`).
- Review fix, round 4 (Codex on #291): a malformed `--since` is a Click usage error (exit 2), not a traceback.
- Review fix, round 5 (Codex on #291): the receipt prints every leg's book probability even when that Kalshi leg is missing. Escalated (frozen definitions): one event ticker across the three legs, boundary quotes (0.00/1.00) as one-sided, and the 4-decimal tie rule.
- Review fix, round 6 (Codex on #291): an explicitly empty `--since ""` is a usage error, not a silent fall-back to the frozen cutoff.
- Review fix, round 7 (Codex on #291): a refused receipt (e.g. no UNL competition) exits 2 and is never written to `--out`.

## 2026-10-05 (#290: NFL season record: ties are pushes; pre-live rows listed separately, never pooled — ARCHITECT)
- `export_nfl_results`: a tie is a PUSH (`result "T"`, `push: true`, `top_pick_hit: null`), out of the hit denominator and counted separately. Log loss keeps the frozen gate's tie convention.
- The season record starts at `live_since` 2026-09-22 (Week 3). Preseason and earlier rows sit under `pre_live` with their own record.
- `record` gains `live_since`, `decided` and `pushes`. Contract: `results`/`count` are live rows only.
- Test: `test_ties_are_pushes_and_pre_live_rows_are_never_pooled`.
- Review fixes (Codex on #290): the `export-nfl-results` receipt prints hits over DECIDED games with pushes shown separately (`W6 1/1 +1P`), prints the pre-live record on its own line, and `--match` finds pre-live rows ("IN the file (pre-live, not in the season record)"). The season-choice finding was already fixed via #289.

## 2026-10-05 (#289: NFL results export skips FINISHED rows with no scores instead of crashing — Codex on #278)
- `export_nfl_results`: the base query requires both scores. A FINISHED row with null scores made `home_score > away_score` raise `TypeError` and aborted the season-to-date file. Test: `test_a_finished_row_without_scores_is_skipped_not_a_crash` (fails on main, passes here).
- Escalated, unchanged: tie grading in the record and preseason predictions in the season record.
- Review fix (Codex on #289): the season is chosen from every FINISHED predicted game before unscored rows are dropped, so an unscored opener of a new season exports that season (empty) instead of republishing the previous one. Test: `test_an_unscored_opener_of_a_new_season_does_not_republish_the_old_season`.

## 2026-10-05 (#288: Kalshi-only grading close reads the Kalshi ML rows two-way syncs actually store — Codex on #278)
- `close.grading_close` and `clv_restate` filtered snapshots to `market == "1X2"`. Two-way Kalshi legs are stored as `"ML"`, so the ruled kalshi_only close never saw a real quote.
- New `kalshi_close_market_filter` (1X2, plus Kalshi ML). Book sessions stay 1X2-only, and `close_from_kalshi` accepts both markets.
- Tests: fixtures use `ML`, as real syncs do. A new regression test covers the grading close and the restate, with a non-Kalshi ML row that never becomes a book close. Both fail on main and pass here.

## 2026-10-05 (#287: UNL ladders — the 17 recorded as exploratory; the favorite-skew test frozen — ARCHITECT)
- Recorded: 17/18 two-sided, 1c spreads, median |book−Kalshi| 2.5pp (max 4.4pp), Kalshi sharper on favorites by 3–4pp. Ruled EXPLORATORY: they informed the hypothesis and do not count.
- Frozen `docs/specs/unl-venue-skew-test.md`: the mean signed gap (Kalshi − book) on the pre-game favorite over a FRESH 30 two-sided boards captured after 2026-10-05T17:00Z (series KXUEFANLGAME). STRUCTURAL if the bootstrap 95% CI excludes 0, in which case UNL stays ineligible unless a skew-adjusted rule is declared as a separate candidate. One-sided boards never count.
- UNL stays "never" for venue-edge. Tracked in #286.

## 2026-10-05 (#285: UNL Kalshi series pinned to KXUEFANLGAME; KXCONCACAFNLGAME reserved for CNL — ARCHITECT ruling)
- `src/adapters/kalshi.py`: UNL → `KXUEFANLGAME` in `SOCCER_GAME_SERIES`, the adapter default, so the window chain needs no `--series`. Discovery had refused on two candidates (KXUEFANLGAME, KXCONCACAFNLGAME).
- New `SOCCER_SERIES_RESERVED = {"CNL": "KXCONCACAFNLGAME"}` ("for later"): a CNL sync refuses and names the series until CNL is wired (#284).
- `SOCCER_SERIES_DISCOVERY` is now empty; the mechanism stays tested for a future unpinned competition.
- Tests: pin + reserve (no `/series` call for UNL), discovery exactly-one-or-refused on the 2026-10-05 listing, and a UNL sync storing a three-way set via "mapped" with both candidates listed. Docs: CLI.md.

## 2026-10-05 (#283: NCAA re-key receipt: post-backup rows count as accounted only on the keeper — Codex review on #279)
- `ncaa_rekey_receipt.py --reconstruct-merges`: a reference row created after the backup (rowid above the backup's max) is accounted only when it points at the keeper. A post-backup row still on the merged-away id (no FK enforcement) is flagged and the reconstruction reads REVIEW. Test: `test_post_backup_row_dangling_on_the_merged_id_is_review` (fails on main, passes here).

## 2026-10-05 (#282: PR-body lint: closing keywords only on declared closure lines — LEDGER rule 5 enforced)
- New `pr-body` check (`python scripts/ledger.py check-body`, body via `PR_BODY`). It rejects a closing keyword + Issue ref (close/fix/resolve forms, `#N`, `owner/repo#N` or an Issue URL) anywhere except a declared closure line starting `Closes #N`. It re-runs on description edits.
- Why: #273, #274 and #275 used negated closing phrases, and GitHub closed #85, #211 and #276 on merge. Their descriptions now read "Outstanding work remains on #N".
- Tests: `tests/test_ledger_pr_body.py`. The original descriptions are rejected; the corrected ones and real closure lines are accepted.

## 2026-10-05 (#281: Codex reviews are input under the fence — ARCHITECT ruling recorded)
- CLAUDE.md, Workflow: Codex review comments are handled like Anthony's. Trivia (verified correctness bugs in the PR's own code, nits) gets fix-and-reply. Anything policy/gate/ledger-semantic is escalated as `needs-ruling`. A Codex suggestion never changes a frozen threshold or a verdict. Docs only; no code.
- Tagging (ARCHITECT, amended): the only mention is the review-request phrase, posted once after a fix push. Thread replies never contain the handle in any formatting, because any other mention starts a Codex cloud task.
- Sweep (ARCHITECT): an unanswered Codex thread on a merged PR is a finding (the #278 miss, fixed in #288).

## 2026-10-05 (#280: the Desk's 2c spread cap applies to the Kalshi grading close; follow-up to #278)
- **Ruling (ARCHITECT 2026-10-05, on #278, verbatim):** "apply the SAME 2c spread cap to the grading close — a wide Kalshi mid is not a reference anywhere."
- #278 merged at its earlier head, before the cap commit landed; this carries it.
- `close.close_from_kalshi` uses the Desk's own `KALSHI_ONLY["maxSpreadC"]` (2c, the same cent rounding). When the LAST two-sided pre-kickoff quote is wider, there is no Kalshi close; an older, tighter quote is stale and never substituted.
- Regression: 2c → priced; 3c → none; last quote 10c after an earlier 1c → none.

## 2026-10-05 (#279: resync matches by natural key before creating (second re-key); dedupe skips absent tables / refuses a schema behind the code; reconstruction learns the ruled classes)
- **(A) Second re-key (ARCHITECT, verbatim):** "the provider re-keyed Abilene Christian@West Florida a SECOND time (24146 → 24111) after Saturday's dedupe … Make the resync match by natural key (home, away, kickoff ±12h) when the incoming id is unknown, before creating a row."
  - The hole: the natural-key fallback skipped a stored row whose own id was STILL in the listing (and one already re-keyed this run) as "a different game", then CREATED the new id: a twin. The 10-03 test pinned that creation.
  - Now an unknown id is created only when no live stored row holds its natural key. One free candidate is re-keyed. A candidate whose id is still listed (the provider serving both ids), already claimed this run, or ambiguous is REFUSED (skipped, receipted), never created.
  - An incoming id found in a row's `<source>_prev` history goes back to that row. Cancelled / stale_orphan rows are never candidates.
- **(B) dedupe `--apply` crash (ARCHITECT):** "no such table: intl_venue_resolved". The reference sweep now skips tables absent from the live DB (they hold no references) and names them. `dedupe-matches` / `--orphans` refuse a schema behind the code with the remedy (`python cli.py init-db`, additive, never --force; the transaction rolls back) instead of a traceback.
- **(C) #277 reconstruction 30/30, RULED ACCOUNTED (ARCHITECT).** The tool now knows the ruled classes:
  - **created after the backup:** a rowid above the backup's max;
  - **re-pointed:** a table keyed BY match_id has rowid == match_id, so the re-point moves the row to a new rowid with identical content; such rows are paired;
  - **placeholder kickoff:** 04:00Z → real kickoff within 24h.
  A clean merge carrying them reads ACCOUNTED; a replaced row, a gone row or any other shift still reads REVIEW. Also fixed: a rowid-alias key reported the match id under the column's own name and leaked it into the content.
- **Receipts:** pytest 703 passed / 1 skipped (+6: refuse-not-create on a still-listed id; second re-key after a dedupe (refused while both listed, re-keyed after, history id goes back); two new ids for one row; absent table skipped; schema refusal without a traceback; the three accounted classes).
- **Review fixes (Codex on #279):**
  - P1: a row created in the run joins the natural-key index, so two unseen ids for one fixture in one listing create once and refuse the second.
  - P2: only a missing table / column ("no such table/column", "has no column named") is refused as "behind the code"; a locked or read-only DB, disk I/O and other operational errors keep their own diagnostic.
  - P2: an empty backup table's max rowid is 0, so every current row in it is post-backup.
  - P2: the placeholder class requires the destination to be a REAL kickoff (not another 04:00Z) within 24h.
  - pytest 706 passed / 1 skipped (+3).

## 2026-10-05 (#278: NFL results season-to-date (Week 3 TNF dropped by the rolling window); Kalshi-only grading close; K-track first live fills recorded)
- **(1) K-track, first live datapoints (ARCHITECT, recorded verbatim):** "First system-matched fills: 4 · +$5.96; executed CLV n=4 mean −0.23pp, fee-adj −1.83pp, all taker — record as the K-track's first live datapoints." Recorded in the ledger entry; no code.
- **(2) NFL results window:** `nfl_NFL_results_2026-10-05` lacked match 15073 (GB–ATL, Week 3 TNF) that the 10-02 file had. Cause: a WINDOW, not a filter. `export_nfl_results` wrote a rolling 8 days (unchanged since the live era), and the game kicked off 2026-09-25 00:15Z. The 10-02 cutoff (~09-24) held it; the 10-05 cutoff (~09-27) did not. Fix: SEASON TO DATE by default, with the file carrying `window` and `record` (games, top-pick hits, by week), so a lifetime record reconciles from one file. `--days N` keeps a rolling window; `--match ID` prints a membership receipt.
- **(3) Kalshi-only grading close (ARCHITECT ruling, verbatim):** "when no book session exists pre-pitch and a two-sided Kalshi capture does, grade against the Kalshi mid, labelled reference=kalshi_only."
  - Built in `close.grading_close`: odds table → book-consensus snapshot → (only when NO pre-kickoff book capture exists in either) the mid of the last two-sided pre-kickoff Kalshi HOME quote. Two-way boards only. A book session that exists but cannot price stays unpriced.
  - Labelled everywhere: `closing_bookmaker = "kalshi_only"` on the stored grade (evaluate and its backfill, clv-restate); `close_reference` and `close_kalshi` (bid / ask / mid / spread) on results rows. `close-probe` prints the receipt.
  - The generic results export now reads THE grading close (it read the odds table alone, so MLB's replaced table left rows unpriced even where the ruled snapshot close priced them).
- **Receipts:** pytest 680 passed / 1 skipped (+6: Kalshi mid / in-play / one-sided / three-way; absent books → kalshi_only; incomplete book session stays unpriced; books win and say so; season-to-date keeps a 10-day-old game the rolling window drops).

## 2026-10-04 (#277: --audit-merges zero says only "no current nearby rows found"; --reconstruct-merges against the pre-apply backup; #270 review)
- **Review on #270 (Anthony, 2026-10-04):** replaying the previous algorithm (offsets −70h/−40h/0h/+40h; provider absent/error/absent/found) applies a merge, moves an odds reference and shifts the keeper's kickoff. The audit then printed "every merge stands" although the unresolved twin sat 80h from the mutated kickoff. "Limit that output to `no current nearby rows found`. … reconstruct the reported 30-merge cohort from the retained pre-apply backup and apply plan … Mark unavailable provenance `UNKNOWN`."
- **`scripts/ncaa_rekey_receipt.py --audit-merges`:** a zero now reads `no current nearby rows found`, plus a note that the audit sees the current table only.
- **`--reconstruct-merges --backup PRE.db [--plan FILE] [--expect N]`** (read-only; the macOS mode=ro fallback is reused and its form printed). For every orphan merge in the provenance log it prints:
  - the original connected twin group in the backup;
  - the merged row (by the logged ids, among rows gone since);
  - the keeper's pre → post kickoff, with a shift named;
  - every reference move per table referencing matches (pre counts on both rows vs post on the keeper);
  - any same-pair row near the PRE or the POST kickoff outside the group.
- `--plan` cross-checks the pasted apply output's `[merge]` lines. Rows with no provenance log, a keeper absent from the backup, or an unmatched merged row read UNKNOWN. The last line gives `merges n/N` and ACCOUNTED or REVIEW. Backup paths are not printed (sanitised).
- **Regression:** the boundary case (keeper kickoff +40h, twin 40h from the pre kickoff and 80h from the post one): the audit says only "no current nearby rows found", and the reconstruction names the shift, the twin near the pre kickoff and the odds move. pytest 675 passed / 1 skipped.
- **Review fix (2026-10-05, reproduced on `70acdbbf`):**
  - **Plan cross-check:** compares the keeper AND merged row ids and both provider ids against the reconstruction. A plan naming a different merged row, or a different provider id, prints `⚠ plan disagrees` → REVIEW. An UNKNOWN merged row leaves the plan unverifiable, counted.
  - **References:** checked by identity, not count. Every pre row (rowid + content) referencing the keeper or the merged row must end on the keeper unchanged. Rows on the keeper that were not in the backup are flagged. A replaced odds row with equal counts → REVIEW. A table without rowids reads identity UNKNOWN.
  - **Regressions:** both refusals return REVIEW; the clean baseline merge returns ACCOUNTED. pytest 677 passed / 1 skipped.

## 2026-10-04 (#275: intl-venue-resolve: venue-country normalization for the rows v3 left unknown; ARCHITECT lane 5, data lane)
- **Ruling (lane 5, 2026-10-04):** "Intl venue-country normalization for the 313 unmatched venues and the 57% unflagged rows. Data lane only; intl-elo-v2 stays frozen through its window."
- **`python cli.py intl-venue-resolve --from-dir <save> --venues-dir <dir> [--aliases FILE] [--plan]`**, for every `intl_match_venue` row with `neutral_v3` NULL:
  - route A `/venues?id=<id>` for venue ids outside the route-B catalog (the "unmatched venues"); one call per distinct id, `--max-calls` capped, saved as `venue_id_<id>.json` and replayed;
  - no venue id served: a UNIQUE city, then name, match against the saved `/venues` catalog; several countries = ambiguous, refused and counted;
  - country spelling: NFKD/casefold on both sides, plus an optional pinned `--aliases` JSON. None is built in (law 1). A neutral reading whose home-country spelling never appears as a venue country stays unknown ("alias needed"), and the receipt lists those spellings for a ruling.
- **Storage:** a NEW table `intl_venue_resolved` (created by `init_db`, additive; no migration) holding venue country, `country_source`, `neutral_resolved` and the reason a row stays unknown. `intl_match_venue` and intl-elo-v2's inputs are never touched (the frozen window holds).
- **Receipt:** the unknown-row reasons, route-A calls, outcomes per source, the unflagged share before → after, and the alias candidates.
- **Tests:** 4 new (plan, route A / city / name / ambiguity / spelling / home-unknown / unserved, v3 untouched, alias + replay with 0 calls, refusals, CLI plan). pytest 678 passed / 1 skipped.

## 2026-10-04 (#274: #211 B-track: fills-based exposure and cash-at-risk per team-outcome, beside the units cap; ARCHITECT lane 3)
- **Ruling (lane 3, 2026-10-04):** "#211 B-track: fills-based exposure and cash-at-risk per team-outcome, from the imported Kalshi CSV, beside the units-based cap." Diagnostic only: the 1.25u cap and sizing are unchanged (ARCHITECT 2026-10-01: "cap/sizing unchanged").
- **Cockpit `fillExposure(L)`:** every sport fill becomes a payoff over its game's outcomes. YES on X pays if X; NO on X pays on every other outcome. Soccer families settle three ways (TIE = the draw); the rest settle two ways. Per game it reports gross stake, fees, hedge offset (= the worst outcome's payout, so > 0 only when the contracts pay on EVERY outcome) and cash at risk (= gross + fees − hedge offset). Per team-outcome it reports contracts and ≈ units at 10 contracts per 1u, flagged when above the 1.25u cap-equivalent.
- A fill whose contract role the ticker does not decide is excluded and counted (law 4).
- Fills are realized positions, so this is the exposure as executed. The result does not depend on load order (keyed by game, summed).
- **Where:** a "B-track exposure — fills-based" table in the Ledger tab's Realized card (top 25 games by cash at risk), plus a headline line in the P&L text.
- **Receipts:** new `scripts/cockpit_exposure_verify.py` 13/13 (two-way hedge, NO contract, soccer tie unhedged, cap-equivalent flag, exclusion, reversed-order identity, render, P&L line); all other Cockpit verifies green; pytest 674 passed / 1 skipped.
- **Still open on #211 (not this lane):** desk load-order invariance (resolve by as_of) and the ticket-product "independence estimate" label.
- **Review fix (2026-10-05):** a game is now the FULL settlement event ticker before its outcome suffix (e.g. `KXMLBGAME-26SEP271305NYYBOS`). Before, family+date+teams collapsed two intraday MLB doubleheader events into one game with a false hedge offset. Opposite sides of different events never hedge. A ticker whose event part fails the game grammar is excluded and counted apart ("event identity ambiguous"). Regression: doubleheader = two events, zero cross-game hedge, downside 1.53 + 1.47 (the old grouping read a 3-contract hedge and 0 at risk); same-event hedge and soccer-tie checks still green. Verify 16/16.

## 2026-10-04 (#273: cutover-readiness: the ruled #85 criteria in one read-only readout; ARCHITECT lane 2)
- **Ruled criteria (2026-10-02, verbatim):** "cutover when (a) 5 consecutive morning compares show only explained classes, (b) the host has run a full day on a tag carrying #246 with desk calls emitted, (c) parity harness green on that tag — earliest Oct 8 stands."
- **`cli.py cutover-readiness`** (`deploy/hosting/cutover_readiness.py`) prints:
  - (a) the five-compare streak from the exports mirror, pairing laptop/<date> with host/<date> as the Action does: dates, verdicts, and the classes named per divergent line;
  - (b) the host tag, days on it, whether it carries #246 (`git merge-base --is-ancestor`), and desk calls emitted per chain (chain receipts' exports, read from the mirror);
  - (c) `scripts/desk_parity_verify.py` run on that tag in a scratch git worktree;
  - a `GO` / `NOT-YET — <each unmet>` line (exit 0/1), including the earliest date.
- **Conservative naming (law 4):** the tool machine-names only identical, capture timing (market / Kalshi / price fields and the Desk fields that follow them, on matched rows) and the guarded code-version skew. Rows or files on one side only and model fields are UNNAMED, and they break the streak unless `--named` names that date, which then prints as operator-named. GO is a readout, never the decision.
- **Receipts:** 7 new tests; a synthetic five-day mirror + host receipts read GO with the real parity run on v1.2.2 (14/14 GREEN); v1.1.0 does not carry #246, v1.2.0 and v1.2.2 do.
- **Review fix (2026-10-05, reproduced on `9757e76c`):**
  - **Chain completion:** a chain counts only when it COMPLETED: an explicit integer exit 0, nothing refused, and every counted step run. A missing exit is a failure, a season-gated skip completes nothing, and a full day needs at least one completed chain and none failed.
  - **One-sided dates:** a date only one writer pushed is pending only when it is today, by the declared clock. An older one is OVERDUE, and the streak reads 0, as it does when the newest common date is more than a day stale.
  - **Regressions:** missing exit and partial steps → no full day → NOT-YET; a host-only date the day before today → `(a) streak 0/5 (overdue one-sided …)` → NOT-YET; the same date as today → pending, streak 5/5. pytest 683 passed / 1 skipped.

## 2026-10-04 (#272: Desk ORDER LINE — copy-exact Kalshi orders on PLAY / VENUE / ticket rows; ARCHITECT 2026-10-04)
- **Ruling (verbatim):** "ORDER LINE on every Desk PLAY/VENUE/ticket row: the Kalshi market ticker (we already resolve it in sync-kalshi), side (YES/NO), limit price per doctrine (join bid; the ask when spread is 1c), and contract count for the row's units at a declared unit size (SP_UNIT_USD in env, default 10 contracts) — so placing an order is copy-exact, never a lookup. Parlay tickets list the legs the same way. Cockpit renders from the file; no policy change."
- **Storage:** `odds_snapshots.market_ticker` (new, additive; `migrate_kalshi_ticker.py`). `sync-kalshi-*` (shared MLB/NFL/NHL/NCAA and soccer paths) stores the ticker it already resolved per leg. The column is deliberately NOT mapped in the ORM (on SQLAlchemy 2.1 an ORM INSERT names every mapped column, deferred included, so a mapped column would break every snapshot insert before the migration). It is written and read by guarded Core SQL (`write_kalshi_tickers` / `read_kalshi_tickers`), so a deploy before the migration keeps working; the test covers both states. No backfill (the tickers were never stored).
- **Exports:** prediction / NFL / fixtures rows carry `kalshi_legs` {selection: ticker, bid, ask} from the latest pre-kickoff Kalshi snapshot per leg.
- **Desk:** `desk.order` {ticker, side, limit, limit_basis, contracts, unit, text, why} on PLAY / LADDER rows, eligible market-only VENUE rows and every `desk-parlays` leg. LADDER = BUY NO on HOME (mirrored prices); a two-way market falls back to NO on the opponent, a three-way never does; a DRAW ladder is refused. Join bid, the ask at ≤ 1c spread, no bid = refused. Contracts = floor(units × 10), or floor(units × SP_UNIT_USD / limit) when set. A refusal is a `why`, never a guess. Calls and units are unchanged (parity golden green).
- **Cockpit:** renders `desk.order.text` verbatim under the call (model table, venue table, parlay legs).
- **Receipts:** pytest 682 passed / 1 skipped; `scripts/desk_parity_verify.py` 14/14; new `scripts/cockpit_order_line_verify.py` 11/11; all 21 other Cockpit verifies green (`cockpit_pass_class_verify.py` now reads the call cell without the order element).

## 2026-10-04 (#271: UNL Kalshi series discovered and stored; published-Cockpit CSP noted, local launcher)
- **`sync-kalshi-soccer --competition UNL`:** the soccer sync knew only `KXEPLGAME`. UNL has Kalshi markets (operator fills exist) but no receipted ticker.
  - `KalshiAdapter.resolve_soccer_series` discovers the UNL series from Kalshi's own `/series` listing (keywords "nations league"; game-winner series only, i.e. tickers ending `GAME` like every wired series).
  - Exactly one match is required, else it refuses and lists the candidates (law 1: never a guessed ticker).
  - The legs are stored like PL's (Home/Away/Tie snapshots, same gates), so `export-fixtures --competition UNL` and the venue engine read UNL three-way sets.
  - `--series` pins the ticker once receipted, and the receipt line names how the series was resolved.
  - UNL is added to the window chain's Kalshi table; the CI pin now covers mapped plus discoverable series.
- **Published Cockpit:** its CSP blocks api.github.com, so "Load latest from host" fails there. `docs/specs/exports-mirror.md` says so, and the new `scripts/cockpit_local.py` serves a saved copy of the published artifact (or the repo copy, flagged) on 127.0.0.1, where the control works. The ledger is per origin: move it with Export/Import and keep the same port.
- tests/test_unl_kalshi_discovery.py (2): discovery exactly-one / refused (2 or 0) / override / unmapped; UNL legs stored as a three-way set with quotes (Kalshi mocked).

## 2026-10-03 (#270: dedupe-matches --orphans: incomplete lookup coverage leaves the whole candidate set UNRESOLVED)
- PR #266 review (Anthony) found two cases on `d14c3f83`. A failed date lookup plus one observed provider game still permitted a RELINK. One found twin plus an unresolved competing twin still permitted a MERGE.
- Now a twin whose provider lookup errors, or any day of the ±2d search that fails, leaves the candidate and every twin it was weighed against UNRESOLVED and untouched (no merge, no relink) until complete lookups establish uniqueness. The plan line names the gap.
- tests/test_dedupe_orphans.py (+1): both cases, dry-run and apply, with ids, rows and references unchanged. The test was verified to fail on the old code (it relinked).
- **Review 2 (Anthony):** overlapping candidate sets still bypassed uniqueness. Same-pair kickoffs at t−30h, t, t+30h and t+40h with provider states absent / error / absent / found merged in one insertion order and refused in another.
  - Uniqueness is now decided per connected component of the twin graph (same home+away, ≤48h, different ids). Every id in the set is looked up first, and any error leaves every candidate UNRESOLVED.
  - A merge happens only when the set is exactly one absent candidate plus one found twin; any larger or multi-live set is refused for review.
  - With no live id in the set, each candidate is searched at the provider, and one failed search day leaves the whole set unresolved.
  - Merges in which the live row keeps its id now log provenance too (`<source>_rekeys`).
  - `scripts/ncaa_rekey_receipt.py --audit-merges` is the provenance audit of the applied merges: re-keyed rows with another same-pair row still within 48h.
  - Regressions: both overlap scenarios across all 24 insertion orders, dry-run and apply, rows / ids / odds references unchanged, one identical plan for every order (fails on the previous code); the audit test.

## 2026-10-03 (#269: ledger: evening state sync — WAL cause confirmed, NCAA re-key residue cleared, v1.2.2 deployed, mirror host side live)
- Record only (no code). It captures the architect's evening receipts for #265 (zero-pair explanation + `--orphans` apply), #268 (WAL confirmed), #264 / #208 (published Cockpit + production tag), #261 (host mirror live, laptop pending) and #263 (what remains).

## 2026-10-03 (#268: HOTFIX: backup verify falls back to a plain read when the read-only URI open fails)
- **`_verify_backup`** (`dedupe-matches --apply`, `clv-restate --apply`) tries two open forms in order, and the receipt names the one that read the backup:
  1. the read-only URI (`Path.as_uri() + "?mode=ro"`, `integrity_check`);
  2. if that raises, a plain `sqlite3.connect(path)` with `PRAGMA query_only = ON` (no writes possible) and `quick_check`.
- On macOS an existing 248 MB backup refused the URI form with "unable to open database file". The success line now reads `opened via <form> (after: <URI error>) · integrity ok (<check>) · journal_mode <mode> · <table> n = live`. If both forms fail, the refusal lists both errors.
- tests/test_backup_verify.py (+3): a macOS-style absolute path whose URI open raises falls back and verifies (the backup bytes are unchanged); both forms failing names both; `query_only` blocks writes.

## 2026-10-03 (#267: exports mirror: the first push to an empty remote no longer reads "nothing changed"; keygen path)
- **`exports_mirror.py push`** judges "changed" against the REMOTE's tip, not the local HEAD.
  - On the host the remote was set in `host.env` before the deploy key worked, so the chain hook's pushes committed in the working clone and failed to push. The hand-run first push then compared against that local commit and printed "not pushed — nothing changed" over an empty remote.
  - Unpushed local commits are now pushed ("incl. N earlier unpushed commit(s)").
  - The clone's `origin` follows `host.env` if the remote changes.
- **Deploy key path:** `keygen` and `push` resolve the key the same way: `SP_EXPORTS_MIRROR_KEY`, else an installed `/etc/sports-predictor/exports_deploy_key`, else `~/.ssh/sp_exports_deploy_key` (writable by `sp`). `keygen --key PATH` is accepted. An unwritable target refuses and prints both routes (the `--key` route and the root step). `docs/specs/exports-mirror.md` step 2 is updated.
- tests/test_exports_mirror.py: first push after failed attempts (reproduced: "nothing changed" over an empty remote), first push of 18 files from a fresh clone, key resolution, keygen into a writable path, unwritable-dir refusal.

## 2026-10-03 (#266: dedupe-matches --orphans; the apply summary reports state, not just this run's merges)
- **Reporting fix:** a `dedupe-matches` apply that found nothing left to merge printed "merged 0" on a table where 962 rows had already been re-keyed in place.
  - Every summary now prints the STATE before and, on apply, after: rows, deleted, rows carrying `<source>_prev`, stale orphans, and re-keys by provenance.
  - A 0-pair run says the rows were already re-keyed, so nothing was missed.
  - Re-keys now log `<source>_rekeys` entries {from, to, via, at}. `via` is one of: dedupe-merge, orphan-merge, orphan-relink, sync.
- **`dedupe-matches --orphans`** (dry-run unless `--apply --backup`). Candidates are SCHEDULED rows with no score that are stale (kickoff more than 6h past) or have a twin (same home AND away within 48h, a different id). Each id is resolved at the provider (`GET /games?id=`):
  - found → untouched;
  - lookup error → UNRESOLVED;
  - NOT FOUND + one live twin → merged (the older row keeps the references);
  - NOT FOUND, no twin → a provider search of the row's date ±2d for the pair. If exactly one game is found and no row holds its id, the row is RELINKED in place; if none is found, it is marked `STALE_ORPHAN` (never deleted);
  - ambiguous, swapped, held-elsewhere or already-claimed cases → refused and reported.
- **New status `MatchStatus.STALE_ORPHAN`:**
  - `export-fixtures` excludes it (counted);
  - the odds / Kalshi `match_lookup` and NFL rest-days skip it;
  - a SQLite status CHECK constraint lacking it refuses the mark cleanly.
- **Adapter:** `APIAmericanFootballAdapter.get_game(id)` (`/games?id=`), with the listing parse factored into `_parse_games` (behaviour unchanged).
- tests/test_dedupe_orphans.py (6).

## 2026-10-03 (#265: NCAA re-key receipt: why `dedupe-matches --apply` found 0 pairs)
- **`scripts/ncaa_rekey_receipt.py`** (read-only; opens the DB with `mode=ro`, writes nothing). It prints:
  - rows re-keyed in place, and the source-id classes (22xxx old vs 23xxx/24xxx new);
  - the natural-key clusters under `find_pairs`' own rules: mergeable / SAME id / missing id / 3+ rows, so a 0 is explained rather than assumed;
  - rows with no twin, with stale SCHEDULED orphans counted;
  - export-window rows vs distinct games, flagging duplicates still in the window;
  - per-id rows (ext ids, `_prev`, status, odds and snapshot counts);
  - `--game "Away@Home"` rows, with `--resolve` looking each row's id up at the provider (GET `/games?id=`, `/odds?game=`; the key is never printed).
- tests/test_ncaa_rekey_receipt.py (1).

## 2026-10-03 (#264: P0-3 follow-up, refs #208: fee-adjusted edge only from a recorded opening fee)
- **Cockpit `executedPositions()`** (PR #259 review 2, Anthony): the fee-adjusted edge requires `open_fee` on EVERY fill of the position (a recorded zero counts).
  - It no longer substitutes the combined/total `fees` for a missing opening fee and no longer defaults it to zero.
  - Without it the fee-adjusted edge is unavailable (null); entry-price CLV stays.
  - Positions are tagged `open_fee` / `missing` / `combined_only`, and the P&L prints both exclusion counts.
  - Opening and closing fees stay recorded separately at import (a re-import fills them in on older rows); nothing splits a combined figure.
- `scripts/cockpit_clv_verify.py` 19/19: missing-fee, combined-fee, recorded-zero and mixed-fill regressions with exclusion counts. Stored series and sizing unchanged.

## 2026-10-03 (#263: PRIORITY: backup verify opens Windows/space paths; names the failed check; sync-odds-football paced + 429 retry)
- **`dedupe-matches --apply` and `clv-restate --apply`** now share `_verify_backup`. It opens the backup with `Path.as_uri() + "?mode=ro"`; the old `f"file:{path}?mode=ro"` failed with "unable to open database file" on a Windows absolute path or any path with a space, `#` or `?`. It expands `~` and refuses only paths inside this project's `data/`. Every refusal names its check and the path it tried. `sp_common.ro_connect` and the k0 probe use the same safe open.
- **`sync-odds-football`** paces its per-game odds calls below the provider limit (`SP_ODDS_FOOTBALL_RPM`, default 280/min). A game still rate limited after the adapter's own retry (new `RateLimited`) is deferred and retried after the window (`Retry-After`, else 60s), for up to 2 rounds, never dropped. Odds are stamped at fetch time. The receipt counts rate-limited / recovered games.
- tests: test_backup_verify (6, a real `.backup` file under "my backups #1/"), test_odds_football_throttle (2).

## 2026-10-03 (#262: auto-claim includes parlay tickets; #208 segment scope ruled)
- `tools/cockpit.html`: loading the desk files auto-claims parlay tickets too, each at the `desk_parlays` file's as_of (whole ticket or nothing; a leg started at as_of skips the ticket). The idempotency key includes `parlay_id`, so a leg shared by two tickets is claimed once per ticket. `scripts/cockpit_autoclaim_verify.py` 13/13 (+2); the leg_audit verify counts the auto-claimed ticket legs.

## 2026-10-03 (#261: F2.5 exports mirror — the host pushes exports/ after every chain step; the laptop pushes at the end of the morning chain; compare Action; Cockpit "Load latest from host")
- `deploy/hosting/exports_mirror.py` (`push --role host|laptop`, `squash`, `keygen`): writes `<role>/<date>/<file>` plus `<role>/latest/<kind>.json`, keeps 14 days, and also ships `tools/compare_exports.py` and the compare Action into the mirror. Copies only. A push race retries from the remote's tip.
- `sp_run`: the mirror push runs after every chain step. It is non-fatal, takes at most 90 s and is receipted; it is off until `SP_EXPORTS_MIRROR_REMOTE` is set. New `sp-exports-squash.timer` (Sun 06:10 UTC), on the T11 list.
- `deploy/exports-mirror/compare.yml`: the commit status `compare_exports` (clean / DIVERGENT / pending) for the newest date both writers pushed.
- Cockpit: "Load latest from host". It uses a fine-grained read-only token kept in localStorage and fetches `host/latest/*.json` into the same load path (F1c refusal intact); upload handling is refactored into `loadDocs`.
- `docs/specs/exports-mirror.md` covers the operator setup. tests/test_exports_mirror.py (5); `scripts/cockpit_mirror_verify.py` (6).
- Review fix (Anthony): the shipped `tools/compare_exports.py` imported `sp_common.py`, which the mirror never shipped (`ModuleNotFoundError` in the Action). It is now standalone: it falls back to `SP_WRITER_OF_RECORD` from the environment. Its exits are 0 CLEAN / 1 DIVERGENT / 2 ERROR (bad arguments, a missing side directory, a crash), and it ends on a `VERDICT:` line. The Action posts `error` ("not a data verdict") unless the exit code AND the VERDICT line agree. Regression: a fresh clone of the mirror, with no PYTHONPATH, runs the shipped CLI and the Action's own step script → CLEAN, DIVERGENT, ERROR (tests/test_exports_mirror.py now has 6 tests).
- Review fix 2 (Anthony): a zero-file comparison is never CLEAN. Exit 3 = NO-COVERAGE ("VERDICT: NO-COVERAGE (0 compared) — not a data verdict"); the Action posts `error` "NO COVERAGE · <date>". Every run prints a `coverage:` line: JSON compared, one-side-only, outside the window, and files the glob left out (e.g. Markdown). Regressions on the shipped tree in a clean checkout: Markdown-only dated folders and empty folders → exit 3 / state=error (tests/test_exports_mirror.py now has 7 tests).

## 2026-10-03 (#260: Kalshi trade-API probe — read-only, no orders)
- `scripts/kalshi_trade_api_probe.py`: on the host it answers REACH (prod + demo `/exchange/status`), AUTH (RSA-PSS-signed key; `/portfolio/balance`), ORDERS (`/portfolio/orders` keys) and FILLS (`/portfolio/fills`: `is_taker`, fee fields). GET only by construction; no order is placed or cancelled. `cryptography>=41.0.0` added to requirements.txt (ruled: the signing dependency is real). tests/test_kalshi_trade_probe.py (3; the signing test skips where `cryptography` is unusable).

## 2026-10-03 (#259, closes #208 — P0-3: "model-close divergence" rename; entry-price CLV and fee-adjusted closing edge on executed positions)
- **Rename (labels and docs; stored series and keys kept):** the per-game metric stored as `clv` (model p − close fair on the pick) is now labelled "model-close divergence" in RESULTS.md, the NHL/UNL shadow grades and sections, `nfl-grade`, `clv-restate`, the web predictions page, the Cockpit shadow card and `docs/CLI.md`.
- **Exports:** results exports (`export-results`, `export-nfl-results`) carry `graded.close_fair` per side plus `close_at` / `close_books` / `close_source`, from `close.close_block` (the ruled `close_1x2`).
- **Cockpit (`close_ref`, version "p0-3 v2"; review fix):** graded straight/ladder positions gain a REFERENCE block = {q_close, fair by role, ref_move_claim = q_close − claim ref, ref_move_relog = q_close − re-log ref, quoted_edge_relog = q_close − quoted taker cost}. A ladder uses pick + DRAW. There is no complement guess and no block without a close. These are labelled reference movement, not CLV. Legacy `clv_v2` ("p0-3 v1") blocks are kept as stored, never rewritten and never read.
- **P&L block:**
  - EXECUTED-POSITION CLV comes ONLY from matched Kalshi fills. Per position, qty-weighted: the held contract's closing fair minus the fill entry (a NO is priced as 1 − the NO'd side), and that less the charged fee per contract. It is broken out by sport.
  - Calls with no matched fill are excluded and counted, as are fills whose held contract cannot be priced at the close.
  - REFERENCE MOVEMENT (claim → close, re-log → close, quoted taker edge) is printed separately, under its own label.
  - Every series reports n / mean / median / positive share / 90% bootstrap CI clustered by day.
- **Review regression (Anthony, PR #259):** q 0.65, re-log 0.60, matched fill at 0.70 → reference movement +5pp, executed entry CLV −5pp (v1 read +5pp as "exec CLV"). Separately, a graded call with no fill → not an executed position. Sizing unchanged.
- tests/test_close_block_208.py (2); `scripts/cockpit_clv_verify.py` (15); three tests updated for the new labels.

## 2026-10-03 (#258: Cockpit AUTO-CLAIM — loading a desk file claims its calls at the file's as_of)
- `tools/cockpit.html`: loading a `--desk` prediction or fixtures file logs its PLAY / LADDER, VENUE, quarantine-shadow and value-shadow calls as claims automatically. The claim is stamped at the file's `desk_meta.as_of`, and the kickoff test also reads it. Claims are idempotent on (match, pick, call type, engine, as_of) via `L.meta.auto_claims`, and a file older than the ledger never reprices a position. Parlay tickets stay on the button, now "Re-log at T-60". Fixtures rows now carry their file's as_of (bug found by the new verify).
- `scripts/cockpit_autoclaim_verify.py` (11 checks): two Braves PLAYs and Thursday's Pitt@VT VENUE claimed; PASS and started-at-as_of rows not claimed; idempotent reload; newer file reprices, older never does. Four verifies adjusted (render-comparison loads now claim). Desk golden unchanged.

## 2026-10-03 (#257: NCAA duplicate rows — the resync re-keys instead of duplicating; dedupe-matches; export prefers the finished row)
- `IngestionService.sync_matches` (american-football family): a source-id miss falls back to the natural key: same competition, same home and away team, kickoff within 12h, and the stored id absent from the listing. The stored row is UPDATED and takes the new id; the old id is kept as `<source>_prev`. Ambiguous candidates or a home/away-swapped pair are refused and receipted, never created. `SyncResult` reports `rekeyed` / `rekey_refused`.
- `python cli.py dedupe-matches --competition NCAA [--apply --backup PATH]`: the receipt of how each duplicate pair differs. Apply merges the newer row into the older, referenced one: references are re-pointed, the empty row is deleted, and conflicts are refused.
- `export-fixtures` carries one row per fixture, preferring the finished one, and counts `duplicates_suppressed`.
- tests/test_ncaa_rekey_dedupe.py (5).

## 2026-10-02 (#256: NCAA market chain syncs results before the export; closes #254)
- `ncaa-market` (host `sp-ncaa-market`, Thu / Fri / Sat) now runs `sync-matches --competition NCAA --season 2026` for yesterday and today as single-day calls, before `sync-kalshi-ncaa` and `export-fixtures`. Games finished since the last run (Thursday's slate before Friday's export) leave the window instead of reading SCHEDULED.
- The laptop routine is documented in `docs/CLI.md` (Market-only competitions); `docs/specs/hosting-h1.md` timer table updated. tests/test_hosting_pack.py (+1).

## 2026-10-02 (#255, refs #254: NCAA kickoff +24h finding — read-only receipt script)
- `scripts/kickoff_receipt.py` (read-only), for each match:
  - the STORED row: utc_date, status, external ids;
  - the PROVIDER's raw date block and timestamp (`/games?id=`, one GET; `--no-provider` skips it);
  - every EXPORT carrying the match: as_of, row utc, the Desk's reason, and the in-play test recomputed on that file's own inputs.
- tests/test_kickoff_receipt.py (1). No pipeline change until the receipt says which side is wrong.

## 2026-10-02 (#253: nhl-v7 ledger annotation; AET/PEN release ratified)
- `docs/registry/experiments.json`: nhl-v7 gains `ledger_count_at_record: 6` and a one-line `ledger_count_note`. Its run record's `prior_read_count: 5` stays as written (ARCHITECT: never rewrite a run record; the live count is the ledger's). `docs/REGISTRY.md` records the doctrine. tests/test_nhl_v6_record.py (+1).
- Ratified, no code change: AET/PEN rows without a stored 90-minute score are unscoreable and released from the intl-elo-v2 cohort, as built in #252.

## 2026-10-02 (#252: intl-elo-v2 cohort — UNSCOREABLE fixtures are released, raw code as reason)
- ARCHITECT 2026-10-02: "AWD/WO (forfeit, walkover) games are RELEASED and substituted exactly like cancelled/abandoned — unscoreable is the criterion, not the status label; record the raw code as reason."
- A cohort fixture is released when it can never be scored: cancelled (CANC / ABD), or finished under a non-FT code without a 90-minute score (AWD / WO, and AET / PEN missing the split). A FT row still waiting for its score stays pending.
- `registry.substitute_cohort_fixture` requires evidence of a cancelled or finished fixture marked unscoreable, and the raw code as the reason. Replacements are never unscoreable themselves. `intl-elo-confirm --substitute` writes the substitutions. tests: registry, intl shadow.

## 2026-10-02 (#251: intl-elo-v2 run record spliced; PASS recorded — confirmation window open)
- `docs/registry/`: the laptop's intl-elo-v2 run (392 scored ids, the same ids as v1, sha256 verified; log-loss 0.7889 vs bar 1.0424; RPS 0.153 vs 0.237; fit c×1.5, K×2.0; neutral rule v3) is spliced. Its prior reads are recomputed against main's ledger: intl-elo-v1, so 2 reads counting this one, as ruled.
- Verdict PASS recorded verbatim. Status is `confirming`, and production is refused until a CONFIRMED read. The declared limitations are recorded: grid-edge pick, 13.7% v3 neutral share, 57% unflagged venues. tests/test_intl_elo_v2.py (+1).

## 2026-10-02 (#250, closes #91 RULED: a venue-edge book capture older than 3h at decision time is NO reference)
- `desk_policy.venue_edge`: when the row's `market.captured_at` is more than 3h (`VENUE["maxBookAgeH"]`) before the Desk's as-of, the row is PASS / `noref` ("books captured X.Xh ago > 3h — no reference"). It is excluded, not stale-flagged: no side, no divergence, `stale_book_zone` false. This is the same class as absent books. The Next-24h card (`window_venue`) obeys the same rule.
- Exactly 3h and fresher are judged as before. Review on #250: a capture AFTER the decision time is unavailable, giving PASS / `noref`. An UNKNOWN age (missing or unparseable `captured_at`) also gives PASS / `noref` under law 4. Ratified by the architect (2026-10-02): "UNKNOWN capture age = NO REFERENCE — ratified, no longer provisional."
- tests/test_venue_stale_books_91.py (6) pins >3h, exactly 3h, missing, malformed, future and at-decision captures.
- The desk golden is unchanged (810/810). The battery's fixtures now carry a fresh capture time; the deleted JS never read it. The Cockpit verify fixtures do the same.

## 2026-10-02 (#249, closes #130: the export's `kalshi_exec_cost` alias is RETIRED)
- **Announcement (ruling (1) on #129):** exports no longer write `kalshi_exec_cost`. `venue.kalshi_exec` and `KALSHI_EXEC_NULL` drop it; the taker cost is `exec_cost_taker` (with `exec_cost_maker`, and the `_away` pair on two-way rows). Condition met: the published Cockpit was republished twice after #88 (the #178 republish and the post-F1c republish).
- The pre-split fallback goes from the Python Desk (`desk_policy`, `kExec.cost`) and from `tools/cockpit.html`. The LEDGER's own `kalshi_exec_cost` / `_maker` fields on call records are not the alias and keep their taker/maker meaning.
- Receipts and verify scripts read `exec_cost_taker`. The desk golden battery maps its pre-split rows (alias only) to `exec_cost_taker`, which is equivalent under the deleted JS's `exec_cost_taker ?? kalshi_exec_cost`: all 810 frozen calls still match row for row.

## 2026-10-02 (#248: UNL shadow engine — intl-elo-v2 greyed in its confirmation window; daily intl chain)
- `export-unl-predictions`: intl-elo-v2 three-way rows for scheduled competitive internationals (36h), `engine: model_shadow`, labelled "PASS — confirmation n/60"; multipliers read from the registry run record; refuses until the run record + PASS are spliced. Never a Desk call, never in the Prediction table.
- `unl-shadow-grade` (top pick vs the three-way close) and a RESULTS.md shadow section; `intl-elo-confirm [--record --ruling]` scores the declared window (first 60 competitive after the verdict) predict-then-update vs naive − 0.010.
- Host chain `intl-daily` (07:20 UTC, `sp-intl-daily.timer`): `intl-sync --since {today}` → `intl-venue-sync` → `export-unl-predictions`. `intl-sync` keeps friendlies of senior sides already stored (incremental sync). Cockpit shadow card shows three-way picks ("Draw") and each model's gate label. tests/test_intl_shadow.py (7), test_intl_history (+1).
- Review on #248: the confirmation COHORT is the first 60 eligible FIXTURE ids whatever their status (never chosen from results), frozen once in the registry (`intl-elo-confirm --freeze-cohort`, `registry.freeze_confirmation_cohort`, sidecar `<id>.cohort.txt` + sha256). `record_confirmation` refuses any scored set that is not exactly the frozen cohort; a pending or unscoreable fixture leaves the read incomplete, never replaced by game 61. tests: registry (+2), intl shadow (reproduction of the review's case).
- ARCHITECT 2026-10-02 (2): a CANCELLED or ABANDONED cohort fixture is RELEASED. It is replaced by the next eligible fixture after the cohort (61st, 62nd …) and recorded as a substitution with its reason and evidence (`registry.substitute_cohort_fixture`, `intl-elo-confirm --substitute`). A postponed, scheduled or unplayed fixture is never swapped. The frozen file never changes; the effective cohort applies the substitutions, and `record_confirmation` reads against it. tests: registry (+1), intl shadow (+1).

## 2026-10-02 (#247: nhl-v8 + intl-elo-v1 run records and FAIL verdicts in the registry)
- The laptop run records of nhl-v8 (0.6963; 1,394 ids) and intl-elo-v1 (FAIL on calibration; 392 ids) are spliced with their ids files (sha verified) and FAIL verdicts recorded verbatim. NHL 2025: 8 reads, retired (a ninth declaration is refused). intl test set: 1 read.

## 2026-10-02 (#246: NHL shadow engine switches to v7, v1 as reference)
- `export-nhl-predictions`: the shadow rows are `nhl_elo_v7_xg_margin_no_na` ("FAILED 0.6885 vs 0.6866"), each with a `reference` block carrying `nhl_elo_v1`'s probability; the fit receipt counts xG updates vs goal fallbacks. `nhl-shadow-grade` / RESULTS.md show v1's pick-vs-close beside v7's.
- `nhl-daily`: `nhl-shot-sync` (yesterday..today, the NHL's free API) runs before the shadow export so live games carry xG. tests/test_nhl_shadow.py updated (+1).

## 2026-10-02 (#244: intl-venue-sync — fix the crash on /venues payloads with None fields)
- `src/ingestion/intl_venues.py`: the law-1 key receipt counts keys (`Counter.update(v.keys())`), not dict values, which crashed on a None field and would have summed numeric ones. Regression test on a real-shaped payload. A re-run with the same `--venues-dir` replays the saved responses.

## 2026-10-02 (#243: per-PR ledger fragments — CHANGELOG/BACKLOG are compiled, never edited by a PR)
- `python scripts/ledger.py compile [--commit] [--dry-run]` folds `changelog.d/<PR>-<slug>.md` and `docs/ledger/entries/<date>-<slug>.md` into CHANGELOG.md / BACKLOG.md newest first, deletes them, and commits the fold alone; `ledger.py pending` counts what is uncompiled.
- CI `fragments` job: a PR that edits CHANGELOG.md / BACKLOG.md (except a pure compile) or lacks its fragments fails. The tag ritual compiles before the release notes; `sp_deploy` reports uncompiled fragments in the deployed tag (read-only). tests/test_ledger_fragments.py (6). Retires the merge-up ritual.

## 2026-10-02 (#220: intl-elo-v2 declared — train-only fit + neutral rule v3)
- `docs/specs/intl-elo-v2.md` + registry `intl-elo-v2`: (a) c multiplier and global K multiplier fitted on the training stream only (48-pair declared grid); (b) neutral v3 (venue country ≠ home country). Same bar/bands/test set; train-only attribution printed.
- `python cli.py intl-venue-sync` (route B; new table `intl_match_venue`) and `intl-elo-backtest --candidate v2`. tests/test_intl_elo_v2.py (5). intl-elo-v1 FAIL is recorded once its laptop run record is spliced.

## 2026-10-02 (#153: NHL v8 declared — train-only fit of scale and k; the 2025 test set retired after it)
- `nhl-backtest --candidate v8`: v7's xG + Elo with the logistic divisor and k fitted by maximum likelihood on 2024 only over the declared grid (56 pairs; tie → (400, 6)); chosen and printed before any 2025 read. Registry `nhl-v8` declared; doc `docs/specs/nhl-xg-v8.md`.
- Doctrine: `registry.RETIRED_TEST_SETS` — after v8 the NHL 2025 test set refuses any declaration or run; later NHL candidates declare 2026-27 (≥ 600 games). `docs/REGISTRY.md` updated. (v6/v7 FAIL records: #239.)

## 2026-10-02 (#153: nhl-v7 run record + FAIL verdict in the registry)
- The laptop's v7 run record (1,394 scored ids, sha verified; the same set as v6) is spliced with `docs/registry/ids/nhl-v7.txt`; FAIL recorded verbatim. NHL 2025: 7 prior reads. v7's stored prior_read_count (5) is kept as written.

## 2026-10-02 (#153: nhl-v6 run record + FAIL verdict in the registry)
- The laptop's v6 run record (1,394 scored ids, sha verified) is spliced into `docs/registry/experiments.json` with `docs/registry/ids/nhl-v6.txt`; the FAIL verdict is recorded verbatim (status closed). NHL 2025: 6 prior reads. tests/test_nhl_v6_record.py.

## 2026-10-02 (#220/#240: intl-elo-v1 known limitation declared)
- `docs/specs/intl-elo-v1.md` and the registry entry carry the declared limitation (neutral-venue play-offs/finals priced with the home edge; v2's 10% check vacuous under the HOME ruling). The fix, v3 (venue country), is for the next candidate.

## 2026-10-02 (#220: intl-elo-v1 preflight rulings — v2 check gated, v3 pre-declared)
- `intl-elo-backtest`: v2's RULE CHECK printed on the same home-and-away denominator and gated at 10% (a breach refuses); a city hosted only by this competitive match is HOME (ruled); `rule_check_v1/v2` recorded with the run. Gap games update ratings (pinned by a test).
- intl-neutral-v3 (venue country ≠ home country) pre-declared; `scripts/intl_venue_route_probe.py` reports its cheapest route from the saved responses with zero calls.

## 2026-10-02 (#153: NHL v6 FAIL; v7 declared — the xG `na` level removed)
- v6 ruled FAIL (0.6886 vs 0.6866; calibration FAIL; shot information +0.0023). The verdict is recorded once the laptop's run record is committed.
- `docs/specs/nhl-xg-v7.md` + registry `nhl-v7`: v6 with the xG model's `na` shot-type level removed (a label leak: missing shot type occurs on ~0.3% of goals); untyped events take the baseline level. Same bar, splits, gate and confirmation plan. `nhl-backtest --candidate v7` (one recorded run). tests/test_nhl_xg_v7.py (4); the nhl-v6 repo test accepts the coming run record.

## 2026-10-02 (#153: NHL shot coverage receipt — both denominators, thresholds on the gate stream)
- `nhl-shot-coverage` / the `nhl-shot-sync` receipt report all finished games (preseason included; not judged) AND the v6 gate stream (nhl-backtest's own stream). P1/P6 thresholds apply to the gate stream (ruled 2026-10-02). Regression test with the ruling's numbers. v6 may run.

## 2026-10-02 (#234 rulings: CNL_Q K 40; intl-neutral-v2 leave-one-out)
- `intl_elo`: CNL_Q is Nations League class (K 40). v2 host-city sets are built from home-and-away competitions only, with each match left out of its own set; the "hosted only this match" count is printed. Doc, registry and tests updated (still unrun).

## 2026-10-02 (#220 lane 2: intl-elo-v1 RATIFIED; harness built, not run)
- `docs/specs/intl-elo-v1.md` RATIFIED (draws S=0.5 with max(margin,1); no regression; unknown venue +100; RULE CHECK 10% with the pre-declared intl-neutral-v2; naive symmetric at neutral). Registry entry carries `ratified`; still unrun.
- `python cli.py intl-elo-backtest [--preflight]` (`src/walters/intl_elo.py`): registry refusal before any data load; walk-forward Elo with the soccer Elo→Poisson three-way; naive − 0.010 + bands; RPS; one recorded run. Refuses while CNL_Q's K class is unruled (#234). tests/test_intl_elo.py (11).

## 2026-10-02 (#230: CONCACAF Nations League codes — intl-sync refused on id 808)
- Adapter codes `CNL` (536, CONCACAF Nations League) and `CNL_Q` (808, its 2018 qualification), ruled. The ingest codes both by name; the provisional, never-written `CONCACAF_NL` is renamed `CNL`. `intl-inventory` includes both. A regression test reproduces the refusal.

## 2026-10-02 (#220 lane 2: international Elo v1 declared — frozen, not run, awaiting ratification)
- `docs/specs/intl-elo-v1.md`: the frozen pre-commitment (H +100 / 0 at derived-neutral; K 20/40/50/60 by class; ln(|margin|+1) with our Elos' 2.2 gap factor; the soccer Elo→Poisson draw mapping with ρ −0.10; train 2018–2024-08, test UNL 2024/25 + WCQ_EU 2025-26; bar = naive − 0.010; bands; RPS). Five RATIFY items, including the draw update (ln(0+1) = 0 would freeze ratings on every draw).
- Registry: `intl-elo-v1` declared (unrun, 0 prior reads) with a 60-game executable confirmation plan. tests/test_intl_elo_declaration.py.

## 2026-10-02 (#230: national-team history ingest — UNL lane reopened, data-ready)
- `python cli.py intl-sync` (`src/ingestion/intl_history.py`): the ruled set from 2018 (WCQ all confederations, Euro + qualifiers, Nations League, friendlies). Leagues are discovered by name and coded by name (new: WCQ_IC, UEFA_EURO_Q, CONCACAF_NL); an adapter-id clash or unmapped name is refused. `/fixtures` + `/teams` per competition-season; `--max-calls`, `--dry-run`, `--save` / `--from-dir`; never touches data/.
- Senior-team filter: a fixture is kept only when both teams play in UNL / WCQ_* / UEFA_EURO / UEFA_EURO_Q; exclusions are printed.
- New table `match_neutral_derived`: `neutral_derived` under the stated rule (venue city vs the home team's ground city, same competition-season; NULL when unknown), with both cities kept. Never a provider fact.
- `python cli.py intl-coverage`: the per-competition-season receipt with the rule's home-and-away sanity check. tests/test_intl_history.py (5).

## 2026-10-02 (#228: national-team source probe — read-only; UNL lane #220 SUSPENDED-PENDING-DATA)
- `scripts/intl_source_probe.py`: can API-Football serve national-team history 2018-present (WCQ all confederations, Euro + qualifiers, Nations League, friendlies)? League ids are discovered by name and cross-checked against the adapter; a coverage receipt per competition-season (scored, 90-minute, venue shares, neutral keys detected, never inferred); `--plan` cost in calls; `--max-calls` budget refusal; `--save` / `--from-dir` replay; never touches data/.
- tests/test_intl_source_probe.py (5, synthetic replay; the API is never reached).

## 2026-10-02 (#153: NHL v6 declaration RATIFIED — the update direction follows the xG margin)
- `NHLEloV6.update`: the result term is the sign of xG_home − xG_away (1 / 0; an exact tie moves nothing); the magnitude is |xG margin| through the same ln(margin + 1); the mov gap is taken from the xG winner. The actual result only scores the prediction. Games without xG fall back to v1 on goals (counted).
- `docs/specs/nhl-xg-v6.md` is marked RATIFIED with the ruling quoted; the confirmation window is ratified. The registry entry `nhl-v6` is updated before any run (still `declared`, unrun).
- New test: a home team that wins on goals but loses on xG moves DOWN.

## 2026-10-02 (#153 part 2: NHL v6 declared — frozen, not run)
- `docs/specs/nhl-xg-v6.md`: the frozen declaration under the corrected manifest (#210), awaiting ratification. The event code is eligibility/target only; shot type is a nullable feature; rules R1–R7 (blocked, shootout, side, situation, empty net, coordinates, orientation); fit on 2023-24 only; v6 = v1 with the margin input = |xG_home − xG_away|; rolling team xG is reported only; same gate; a proposed confirmation window.
- `src/models/nhl_xg.py` (rules, IRLS logistic fit with window assertion, game xG, rolling team xG) and `NHLEloV6` (`src/models/nhl_elo.py`).
- `nhl-backtest --candidate v6`: refused unless the registry holds `nhl-v6` and it has not run (the refusal comes before any data load); asserts the fit ended before the first train game; reports v1 beside v6, shot information, RPS and the exclusions; records the ONE run in the registry.
- Registry: `nhl-v6` declared (status declared; 5 prior reads of NHL 2025 shown). tests/test_nhl_xg_v6.py: 7 tests, including the no-same-game-leakage proof.

## 2026-10-02 (#212 review fix: the confirmation is executable and cannot be recorded early)
- `declare()` requires a structured `confirmation_plan` {n_games, metric, bar, must_beat_reference, reference} (`check_plan`).
- `record_confirmation(eid, scored_ids, result, ruling)` executes the plan and computes CONFIRMED/NOT_CONFIRMED (metric <= bar and, when required, strictly below the reference; a tie fails). The scored ids are stored in a `<id>.confirm.txt` sidecar with sha256, and the result is kept.
- It refuses: no PASS; fewer games than planned; any game starting before the verdict; any game from the scored test set; a missing metric or reference.
- `production_allowed()` also requires a complete confirmation record. Regression tests: immediate confirmation fails (fails on the old code: 3 failed).

## 2026-10-02 (#220: UNL lane step 1 — national-team results inventory)
- `src/walters/intl_inventory.py` + `python cli.py intl-inventory` (read-only). For UNL, WC, UEFA_EURO, WCQ_* and FRIENDLIES_INT, per competition and season: finished+scored matches, date span, teams, raw home/draw/away shares and venue completeness. Also each UNL team's prior international results before its first UNL match.
- No neutral site is inferred (law 4). tests/test_intl_inventory.py.

## 2026-10-02 (#176: NCAA source probe — read-only, row-level)
- `scripts/ncaa_source_probe.py`: CollegeFootballData (CFBD) `/games` by year, FBS by default. Field names are discovered from the first record and printed; a missing required field refuses the run.
- Each completed game is joined to OUR NCAA matches through the shared matcher (ambiguity refused), in the source's orientation, else swapped. It compares labels and scores (in our orientation); neutral games are counted separately and never relabel ours.
- It reports the source's home rate and margin (non-neutral / neutral), ours on the same joined games, the join rate, swapped / score-mismatch / unmatched samples and the access receipt (HTTP status, rate-limit headers).
- Key from `CFBD_API_KEY` (.env, never printed); `--from-file` for offline re-runs; refuses `--save` under data/; writes nothing. tests/test_ncaa_source_probe.py: 3 tests.

## 2026-10-02 (#191: F1c — the Cockpit renders desk files only; the in-browser policy is deleted)
- **Golden first** (a separate commit, before any deletion): `scripts/desk_golden_capture.py` drove the pre-F1c `tools/cockpit.html` (sha256 37250ba4…, = main) on the seeded battery (clock and counts pinned, America/New_York), the 600-slate parlay fuzz and the toFixed sample, writing `tests/golden/desk_js_v1_1.json.gz`. `tests/test_desk_golden.py` and `scripts/desk_parity_verify.py` check the Python Desk against it row for row with no browser (14/14).
- **`tools/cockpit.html`:**
  - Deleted: `computeCall`, `valueSide`, `venueEdge`, `kalshiOnlyRef`, the parlay builder, `execFacts`/`execEdgeHTML`/`deskCostFor`/`execEdgePP`, and the policy constants (POLICY, BASE_UNITS, the policy halves of VENUE/PASSCLASS/KALSHI_ONLY).
  - Prediction and fixtures files without `desk` blocks are **REFUSED whole**: "REFUSED n file(s) without desk blocks (…) — export with --desk". `model_shadow` and `desk_parlays` files keep their own paths.
  - Tickets come only from the `desk_parlays` file.
  - Kept: the ledger, fills, audits, rendering and the export-quote accessors the ledger capture reads.
- **The Next-24h card's venue verdict** is stamped by `window.py` as `desk_venue` via the new `desk_policy.window_venue`; the card renders it.
- **Verifies:** `cockpit_render_verify` is rewritten: rendered == the deleted JS's frozen outputs in all three scenarios, plus tamper, refusal, no-parlays and version-mismatch checks. 13 legacy-path verifies now load through `scripts/cockpit_desk_files.upload()` (the Python Desk with the page's own ledger-summary counts, plus the desk_parlays file). `cockpit_window_verify` stamps `desk_venue`. All 18 verifies are green.

## 2026-10-02 (#212: experiment registry + confirmation doctrine)
- `src/walters/registry.py` and the git-tracked ledger `docs/registry/experiments.json`. Each candidate goes through declare (before any run; the confirmation window is required), run (once per id; scored ids in a sidecar `docs/registry/ids/<id>.txt` with count and sha256; prior reads computed), verdict (verbatim), then confirmation. `production_allowed()` encodes the doctrine: a PASS is not production until a declared confirmation window closes CONFIRMED.
- Seeded with the pre-registry verdicts, unchanged: NHL v1–v5, S19, DC-fit, S14 stage 2 and cups fix-v2. Their ids are "not recorded" and are never reconstructed. NHL's 2025 test set shows 5 prior reads.
- `python cli.py registry [--id ID]` (read-only). docs/REGISTRY.md. tests/test_registry_212.py: 5 tests.

## 2026-10-02 (#153 part 1: NHL-xG shot-event ingest)
- New table `nhl_shot_events` (additive; `init_db` creates it). One row per shot-type play (shot on goal, missed, blocked, goal) from api-web play-by-play, 2023-24 onward. Raw values only: event type (stored for eligibility and target only, never a feature, per #210), nullable shot type, x/y, shooter, goalie in net (NULL = empty net or absent), situation code, period, time, zone, home defending side, and shooter side vs play-owner side.
- `src/ingestion/nhl_shots.py`: discovery-based parsing (law 1); links through the goalie-sync mapping, else the refusal-on-ambiguity matcher; upserts without deleting and never blanks a stored value on refetch; relinks unlinked rows; coverage receipt.
- CLI `nhl-shot-sync` and `nhl-shot-coverage`. The receipt reports P1–P6 against the probe's frozen FEEDABLE bars (95/95/90/95/90, plus every season).
- tests/test_nhl_shot_events.py: 3 tests.

## 2026-10-02 (MLB odds history: snapshot per sync, close = last pre-first-pitch session)
- `sync_odds_mlb` (bulk window and rollover fallback, via `_mlb_store_odds`):
  - A game at or after first pitch is never touched: no wipe, no insert. The pre-game session survives and no in-game price is stored.
  - A pre-game sync replaces the current board and APPENDS one book-consensus `OddsSnapshot` (1X2, `api_baseball`, `n_books` = complete books, #207 contract), as NFL's sync does.
  - The sync's log line counts snapshots and post-first-pitch games kept.
- Grading close (`close.grading_close`): the odds table's last pre-kickoff session under the contract; when it cannot price, the last COMPLETE pre-kickoff book-consensus snapshot session (`close_from_snapshots`; Kalshi, in-game and incomplete sessions never count). Used by evaluate, its M11b backfill (which re-grades NULL-CLV outcomes), clv-restate and the results-tally cohorts.
- `capture-odds` no longer writes its own pooled 1X2 snapshot (the sync writes it under the contract) and is bounded to games before first pitch (#174).
- New `close-probe --match ID` (read-only receipt). tests/test_mlb_odds_history.py: 5 tests, including the PHI@ATL shape re-graded from the snapshot.

## 2026-10-01 (#207: P0-2 the close contract)
- `close_1x2(rows, before, outcomes)` now requires the outcome set: binary HOME/AWAY or 3-way HOME/DRAW/AWAY. `outcomes_for(sport)` is the one mapping (soccer is 3-way, every other sport binary, as read from the adapters).
- A book counts only with a COMPLETE same-session set. Each complete book is de-vigged on its own, then the books are averaged. With no complete book the result is UNPRICED: `fair` is None and `missing` names each quoted book's absent legs. `books` counts complete books, `books_quoted` every book in the session. `priced(cl)` is the caller check.
- All 11 call sites pass the outcome set and check `priced`: evaluate CLV, the M11b backfill, the market blend, NFL export/grade (3 sites), nhl_shadow, miss_analysis, clv_restate (2 sites) and the sync_odds snapshot.
- results-tally reports the **verified-close** CLV cohort as the headline and the **retained-legacy** cohort on its own line, never pooled (`clv_restate.clv_cohort`, read-only).
- tests/test_close_contract_207.py: missing draw, one-sided, mismatched coverage, post-kickoff replacement, same-session completeness, per-book de-vig, cohorts, no pooled headline.
- **Exports (ARCHITECT-RULE 2026-10-01):** the MLB/soccer prediction export's market block and the fixtures export (incl. the window card's rows) use the same contract, so there is one definition.
  - `bookmaker_count` now means complete books; `bookmaker_count_quoted` is added.
  - `overround_pct` is the mean per-book booksum.
  - An unpriced close ships the no-1X2 shape plus an additive `close_unpriced` receipt. Fixtures receipts gain a `close_unpriced` count.
  - `scripts/export_close_compare.py BEFORE AFTER` is the read-only receipt for a real export of each kind.

## 2026-10-01 (#209: P1-1 legacy soccer improve refused)
- `training.improve(sport=SOCCER)` raises `LegacySoccerImproveRefused` before its first write (`evaluate_finished`). The message points to `soccer-backtest` (the chronological, market-scored gates) with `set-soccer-config`, and to `soccer-refresh`.
- `cli.py improve --sport soccer`, and the bare `improve` (whose default is soccer), print the refusal and exit 2. The admin web job returns "REFUSED: …". MLB is unchanged, including the host chain's `improve --sport mlb --hold-on-pass`.

## 2026-10-01 (#204 / #175: Kalshi in-play guard on OUR start time — merged in #205; record backfilled)
- `sync_kalshi_mlb` (the shared path for MLB, NFL, NHL and NCAA): the in-play guard now runs after matching and checks the matched game's `utc_date`, not the market's `occurrence_datetime`. A game with no start time on record is never treated as pre-game.
- Gate 1 (time) has two anchors: games within 5h of the occurrence OR within 2h of the ticker's ET start stamp (`KalshiAdapter.ticker_start`, the M13 parse). The fallback for a missing occurrence is kept.
- `sync-kalshi --date-to D` covers the whole UTC day D. The window's `--date-to {tomorrow}` had dropped first pitches after 00:00Z (#175).
- tests/test_kalshi_inplay_guard.py: 4 tests. Run against the old code, they reproduce "matched 0 / in-play 2" and the stored in-play leak.

## 2026-10-01 (#213: review hygiene)
- RESULTS.md is marked REGENERATED, NOT AUTHORITATIVE IN GIT: in the `results-tally` header (every regeneration), README, docs/CLI.md, and a banner on the stale committed copy (2026-09-17).
- #83 re-closed with an `ARCHITECT`-opening comment (S19 REJECT, 2026-09-30). #98's description is refreshed: #167 met its reopening condition in code, and it waits on a live PL receipt.

## 2026-10-01 (#206: P0-1 maker fee no longer double-counts the 25%)
- `venue.KALSHI_FEE_M`: game series (NFL/NHL/NCAAF/EPL) maker M changes from 0.25 to 1.0; MLB pre-live stays (0.5, 0.5). The maker discount is the 0.0175 rate (= ¼ × 0.07), applied once. Before: NFL maker, 100 contracts at 50c, cost $0.11. Published: $0.44.
- Cockpit `FEE_M_BY_FAMILY` (the fill classifier) gets the same fix, and the policy card text is corrected. `scripts/kalshi_fee_fill_receipt.py` reads the fixed table.
- Desk maker costs re-state through the export's `exec_cost_maker`: +0.2 to +0.3pp per contract on a 10-lot (NFL join 0.56: 0.561 → 0.564). K2 stays informational: no call, unit or tier effect.
- tests/test_kalshi_maker_fee_published_206.py (published-schedule fixtures: $0.44 and $1.75 per 100 at 50c; MLB taker $0.04–$0.88, maker $0.01–$0.22). Two older tests are re-derived by hand. Two Cockpit verifies get corrected synthetic fees and costs.

## 2026-10-01 (#201: seed-thread links recorded)
- The first `discussions` / `list` dispatch receipt is on #201. Discussions are enabled with six categories. The four seed threads are #197 and #198 (Q&A), #199 (Ideas) and #200 (Receipts).
- docs/LEDGER.md gains a table of the posted seed threads. The seed file's header points to it.
- The `list` call ran with the token's current scopes. `write:discussion` is added only if the first `post` or `reply` is refused.

## 2026-10-01 (#201: Discussions posting via the ledger workflow)
- `ledger.yml` + `scripts/ledger.py`: a workflow_dispatch mode
  `discussions`. `list` (the default) prints categories and thread links;
  `post` sends a `docs/discussions/` file to a named category; `reply`
  answers by thread number. It uses `LEDGER_PROJECT_TOKEN`, and nothing
  posts without a dispatch that names the file.
- `tests/test_ledger_discussions.py` (5).

## 2026-10-01 (#170: Discussions — Receipts category + S14 receipts post)
- `docs/LEDGER.md` adds the Receipts category. Discussions setup is all
  operator steps (Code has no Discussions tool).
- `docs/discussions/seed-2026-10-01.md`: four categories, and post 4 is the
  S14 residual receipt (+1.17 live vs +0.18 pooled).

## 2026-10-01 (#192: one injured QB = one news item)
- Card pager: a QB's injury status change pages ONCE per player, listing
  every game his team has in the window (new class `qb_news`). Half units
  per game are unchanged.
- B-track shadow logs `qb_shared_risk` (a QB flag spanning two or more live
  games), with no cap change. It appears in the `desk-parlays` CLI, the
  parlay card and the ledger tally.

## 2026-10-01 (#193 B-track cross-book rules, shadow; #192 QB finding)
- `desk_policy.b_track_shadow`: an exposure cap of 1.25u per team-outcome
  and ticket dedup, pre-committed and shadow only. `desk_parlays` reports
  what the rules would cut and the tickets v1.2 would build.
- Cockpit: the parlay card shows "exposure-capped N · deduped N" and marks
  the would-cut tickets. Logged legs carry `b_shadow_cut`. The ledger keeps
  a per-slate tally, and the P&L block gets the B-track shadow line (n/30
  slates, net of the would-cut tickets).
- `scripts/cockpit_btrack_verify.py` (8 checks). Finding #192 (QB flags
  counted per game, not per player).

## 2026-10-01 (card page content, F2 slice 1; #189 NCAA label)
- Card pager: every line and digest row reads "competition · away @ home ·
  kickoff ET · model pick prob (tier) · reference · edge · Desk call ·
  flags". Market-only rows say so. Each delta adds a "↳" line.
- New delta classes "model updated" and "call changed". The digest lists
  Desk calls first.
- NCAA games show "NCAA", not the "NFL" family (#189).
- `tests/test_card_page.py` (6).

## 2026-10-01 (#187: MLB start times — statsapi kept, card flags unconfirmed, audit)
- `mlb_apisports`: the api-sports fallback never overwrites a
  statsapi-sourced start time. Disagreements are receipted and stamped on
  the row.
- Window card / pager: MLB rows whose time statsapi has not confirmed show
  "⚠ time unconfirmed".
- `mlb-time-audit`: read-only statsapi vs api-sports postseason start-time
  comparison (laptop).

## 2026-10-01 (#151 F1b: the Cockpit renders desk calls from the file)
- `tools/cockpit.html`: rows from `--desk` exports are rendered from their
  `desk` blocks (calls, value shadows, venue, exec text); parlay tickets
  come only from a loaded `desk_parlays` file. The summary names the source
  and flags legacy rows or a policy-version mismatch. Legacy files without
  desk blocks still compute in the browser, labelled as such.
- `desk_policy`: unrounded desk numbers, `desk.venue` on every row, raw
  ticket edge.
- `scripts/cockpit_render_verify.py`: computed vs rendered identical
  (calls, shadows, venue, tickets, table text, ledger capture); the policy
  functions are never called in render mode. 16/16.

## 2026-10-01 (#183: parlay-leg audit in the Cockpit ledger)
- "Audit parlay legs (#183)" checks each logged parlay leg against the
  Desk call of its game in the export files loaded for the leg's day. A
  ticket with a leg that was not a play is flagged "leg not a play
  (#183)" and left out of the P&L. Nothing is deleted.
- `scripts/cockpit_leg_audit_verify.py`: 9 checks.

## 2026-10-01 (#151 F1: parlays ported; #183 parlay legs fixed)
- `tools/cockpit.html`: parlay legs come from the Desk's non-PASS calls.
  Before this, a fixtures file loaded ahead of a predictions file could
  build tickets from PASS rows (#183).
- `desk_policy.build_parlays` + `desk-parlays FILES…` write
  `exports/desk_parlays_<date>.json` (cross-sport tickets in one file).
- Parity verify: tickets row-for-row in every run, plus a 600-slate parlay
  fuzz (889 tickets identical). 31/31.
- #181 (NHL 0.5u on PASS) is parity-preserved until the v1.2 bump, as
  ruled.

## 2026-10-01 (#151 F1: the Desk's call in the export, off by default)
- `src/walters/desk_policy.py`: a Python port of the Cockpit Desk v1.1, the
  single source of truth once parity is proven. `--desk` (or
  `SP_DESK_CALLS=1`) on `export-predictions` / `export-nfl-predictions` /
  `export-fixtures` adds `desk` per row and `desk_meta` (as_of, counts).
  Off by default; with it off, files are unchanged.
- Cockpit: "Export ledger summary" writes `ledger_summary.json` (graded
  counts per rule), which the export reads when present; otherwise it
  counts 0, the cautious side.
- `scripts/desk_parity_verify.py`: JS vs Python row-for-row, with the clock
  and counts pinned (synthetic battery 16/16; real exports by argument).
- `tests/test_desk_policy.py` (8 tests). Finding #181 (NHL PASS rows can
  show 0.5u).

## 2026-10-01 (#178: ledger kickoff audit in the Cockpit)
- `tools/cockpit.html`: every position's claim, execution and reprices are
  checked against the true UTC kickoff. Post-kickoff prices are flagged
  "post-kickoff (tz bug)" and left out of the P&L, which falls back to the
  last pre-kickoff reprice or the claim, or excludes the position. Stored
  fields are never rewritten; flagged positions carry a `tz_audit` mark.
  The P&L block shows a one-line count.
- Reprice history is now logged per position (`reprices`); before this it
  was overwritten on each re-log.
- `scripts/cockpit_ledger_audit_verify.py`: 19 checks.

## 2026-10-01 (#178: Cockpit reads kickoff times as UTC)
- `tools/cockpit.html`: new `utcMs()` reads the exports' naive `utc_date`
  as UTC. The capture window, Kalshi-only T-60, the venue in-play check
  and KO / re-run-by were shifted by the viewer's UTC offset in any non-UTC
  browser. The live artifact needs republishing.
- `scripts/cockpit_utc_verify.py`: 28 checks across four timezones
  (main: 14/28; fixed: 28/28).

## 2026-10-01 (#163 verdicts, NCAA source finding, NHL 2024 Utah alias, H2 rehearsal)
- #163 soccer candidates, both REJECT, production unchanged: DC-FIT
  (−0.0003 out of sample); S14-STAGE2 (criterion (i): the +1.17 offset
  overshoots the pool's +0.18 residual to −0.99). No re-tune.
- NCAA: the provider's current 2025 labels match ours, so the fault is at
  the source. The gate stays SUSPENDED-PENDING-DATA and the banner now
  says so. The offseason alternative-source probe is #176.
- `nhl_goalies.NAME_ALIASES`: the 2024 doubled form "Utah Utah Hockey Club"
  maps to Utah Mammoth / Utah Hockey Club. Re-sync owed; the 2024 target
  is >= 90%.
- H2 dry run PASS recorded as the cutover rehearsal receipt.

## 2026-10-01 (#170: GitHub Discussions as the input channel)
- `docs/LEDGER.md`: the Discussions fence (threads are data, never rulings;
  adoption = ruling + Issue with `Source: Discussion #N`), the RFC rule
  (name the gate), and ledger rules 5 (`Refs #N` only) and 6 (ruling closes
  start with ARCHITECT).
- `docs/discussions/seed-2026-10-01.md`: three seed threads for the
  operator to post.

## 2026-10-01 (#82: snapshot retention design, for ruling)
- `docs/specs/snapshot-retention.md`: proposed retention for odds/Kalshi
  snapshots. Raw rows are kept 30 days; first captures and closes are kept
  forever; hourly rollups are kept beyond that. It includes a reader-by-reader
  impact check, a DDL sketch and safety design. Design only; no code
  deletes anything.

## 2026-10-01 (#166: H2-PREP — cutover orchestrator, dry run, runbook)
- `deploy/hosting/sp_cutover.py`: the ruled H2 sequence (preflight, pause,
  install, flip, resume, receipt), each step receipted and refusing on
  failure. `--dry-run --scratch DIR` runs it against a scratch copy.
- `scripts/h2_dry_run.py` proves the sequence on a scratch DB.
- `docs/specs/h2-cutover-runbook.md`: the operator steps, the
  fresh-fingerprint compare, the MLB doubleheader/postponed waivers and
  rollback.

## 2026-10-01 (audit rulings: NCAA gate suspended + resync-diff; NHL Utah alias + unlinked listing)
- `resync-diff` (read-only): compares the provider's current listing with
  our stored rows (labels, scores, home rate on both copies).
  `sync-matches` never rewrites home/away on existing rows, so a re-sync
  cannot repair labels and could flip stored results.
- `ncaa-backtest` announces the NCAA gate as SUSPENDED-PENDING-DATA; v1's
  verdict is void.
- NHL goalie mapping: "Utah Hockey Club" ↔ "Utah Mammoth" alias.
  `nhl-goalie-audit --list-ours` lists every one of our unlinked games with
  the nearest API game, its delta and a named cause.

## 2026-10-01 (#167 CORRECTION: the soccer/NHL "close" was an average of every capture)
- **Correction.** The general odds sync (soccer, cups, NHL) appended a full
  book set on every run. Every reader then de-vigged ALL of a match's rows
  at once, so the "closing price" behind soccer CLV, NFL grading's close,
  the NHL shadow close and the prediction export's market reference was a
  mean over every capture, not the close. **Soccer CLV figures published
  before 2026-10-01 are not closing-line value**; they are re-stated by
  `clv-restate --apply` and `results-tally`.
- The close is now ONE definition (`src/walters/close.py`): the last
  pre-kickoff capture session, latest row per book. In-game prices are
  never the close; MLB rollover games captured after first pitch become
  unpriced.
- The odds sync now replaces per match, stores the totals/spread line, and
  appends history to odds_snapshots.
- New: `odds-audit` (read-only receipt) and `clv-restate` (dry-run by
  default; `--apply` only with a verified backup).

## 2026-10-01 (#163: soccer candidates — Dixon-Coles rho fit, S14 Stage-2)
- `soccer-backtest --candidate dixon-coles-fit` (backtest-only): ρ fitted
  on PL 2023/24 only, frozen, gated against production's ρ on PL 2023/24 to
  2025/26 pooled.
- `soccer-backtest --candidate s14-totals` (backtest-only): +1.17 goals on
  uncertain-winner games. The verdict needs both the improve rule and S14's
  frozen Stage-2 criteria.
- Both are pre-committed, write nothing and change no production model.

## 2026-10-01 (#159/#160/#161: postseason sizing; kalshi-only reference; Desk kickoff + n/30)
- MLB prediction exports carry `stage` (`regular` / `postseason` from our
  statsapi gameType mapping; null when unknown) and `stage_raw`.
- Desk: postseason rows play at half units until 30 postseason calls are
  graded.
- Desk: KALSHI-ONLY provisional reference (ruled). Model sports with no
  books at T-60, a two-sided Kalshi market (spread ≤ 2c) and a series in
  the fee table use the Kalshi mid as the reference, are flagged
  "kalshi-only", and size at 0.5 ×. The ledger records
  `reference: kalshi_only`. Review at 30 graded calls.
- Desk rows show the kickoff and "re-run by" (T-60). The policy card shows
  "graded n/30" for value shadows, postseason and kalshi-only calls.
- Finding logged: NHL venue gaps ≤ 3.2pp over 18 games; threshold unchanged.

## 2026-10-01 (#157: morning chain in two network phases; compare_exports --since)
- `docs/CLI.md`: the laptop morning chain runs in two phases. Phase 1 runs
  the statsapi steps under the VPN. Then quit the VPN and bring Tailscale
  up. Phase 2 runs the host pull/compare under Tailscale.
- `compare_exports.py --since N` (default 3) compares only exports dated
  within the last N UTC days, plus undated files, so settled exhibits stop
  re-printing. The skipped count is printed, and `--since 0` compares
  everything.

## 2026-09-30 (#155: MLB postseason night-game odds coverage)
- `python cli.py mlb-odds-timing --start D [--end D] [--only-missing]`
  (read-only): shows when api-sports first priced each MLB game, from our
  odds_snapshots. It flags UTC-rollover and night starts and gives each
  game a verdict: PRICED_PRE_START, PRICED_ONLY_AFTER_START or
  NO_BOOKS_CAPTURED. It is the receipt for the finding that postseason
  night games got no books.

## 2026-09-30 (#148: release model — main = BETA, production = tags)
- `deploy/hosting/sp_deploy.py` deploys the latest `vX.Y.Z` tag (detached)
  or an exact `--tag`. It never pulls `main` and refuses when no tag exists.
- Every receipts line carries `release` (`v1.0.0` / `BETA main@sha` /
  `UNTAGGED@sha`). Boot, chain and `sp_receipts.py` output print it.
- `scripts/release_notes.py`: the CHANGELOG slice since the previous tag.
- Ledger: `release` label and a per-release milestone (`v1.0.0`).
  `docs/RELEASES.md` holds the promotion ritual and the hotfix path.
- Fixed #149: the deploy read a host-rewritten RESULTS.md as `ESULTS.md`
  and refused.

## 2026-09-30 (#79: NCAA data audit)
- `python cli.py ncaa-audit` (read-only; `--season`, `--limit`) — the audit
  the architect ordered before any NCAA v2 (v1 verdict PROVISIONAL: log-loss
  PASS, calibration FAIL, 2025 home rate 0.489 implausible vs 2026's 0.708).
  Over the gate's stream WITHOUT its exclusions, per season: home rate by
  verbatim stage and by UTC month, repeated/reversed pairings with dates,
  two labelled HEURISTICS (home side had fewer prior-season games; home rate
  when both sides are "established" >= 8 games vs not), an inventory of
  every stored field that could indicate a neutral site or division, and a
  suspects list. Infers nothing; writes nothing. Module
  `src/walters/ncaa_audit.py`; tests `tests/test_ncaa_audit.py`.

## 2026-09-30 (gate verdicts; NHL shot-quality probe + unlinked-games audit)
- Verdicts logged: S19 REJECT (+0.0005 vs 0.0050, #83 closed); NHL v5 FAIL
  (0.6912 vs 0.6866; goalie information −0.0003 = the goalie floor; NHL
  stays market-only, reopening now needs xG-class shot data); NCAA v1
  provisional pending a data audit.
- `scripts/nhl_pbp_probe.py`: read-only probe of NHL play-by-play shot
  events (location, type, shooter, situation), 2023-24 onward.
- `nhl-goalie-audit`: why NHL games are unlinked (UTC-boundary offsets and
  more), with an opt-in `nhl-goalie-sync --tolerance-hours`.

## 2026-09-30 (#138: plain soccer-backtest evaluates production params)
- `soccer-backtest` (plain report) now uses production's `elo_goal_coeff`
  (0.0008) as well as its `dixon_coles_rho`; it used the default 0.0023.
  **Historical plain-report numbers shift**: runs before this change are
  not comparable. The S19 gate verdict was already on production params
  and is unaffected.
- The #137 / #140 / #141 / #139 pre-commitments are ratified (BACKLOG).

## 2026-09-30 (#79 NCAA v1: frozen gate + Elo candidate)
- `python cli.py ncaa-backtest` — the NCAA v1 gate, frozen before any run:
  train 2025, test = the finished 2026 games at run time (n and date range
  printed), pre/postseason excluded. Pass = log-loss <= the 2025 home-rate
  baseline − 0.010, every 10pp band with n >= 100 within ±5pp, final
  ratings 1000-2000; fewer than 500 test games = INVALID. `--baselines-only`
  prints the bar before any candidate is scored.
- Candidate `ncaa_elo_v1` (src/models/ncaa_elo.py): plain Elo, MOV + season
  regression, constants fixed a priori (k 24, home 55, mov_base 2.2,
  regression 0.25, default 1500), no selection. Read-only: nothing is
  written, no export changes; NCAA stays market-only until the architect
  rules on a verdict.

## 2026-09-30 (S19 + S20: soccer time-decay candidate, RPS reported)
- S20 (#84): the soccer backtest reports the Ranked Probability Score
  (H<D<A ordered) beside log-loss: `soccer-backtest` (calibration and
  model-vs-close blocks), an RPS column in `dixon-coles-sweep` and
  `elo-coeff-sweep`, and both arms of the S19 comparison. It is reported
  only and is in no acceptance criterion.
- S19 (#83): `soccer-backtest --candidate time-decay` scores production
  and a time-decay candidate on the same matches. The candidate weights
  the attack/defense fit by 0.5^(age_days/365); the 365-day half-life
  (Dixon & Coles 1997, ~373 days) was frozen before any run. The existing
  gate decides: candidate log-loss better by >= 0.0050, ties reject.
  It is evaluated on PL 2023/24 + 2024/25 + 2025/26, pooled. Backtest-only:
  nothing is written and production (v22) is unchanged. The frozen
  half-life, the evaluation set and four more choices wait on architect
  ratification.
- FINDING: plain `soccer-backtest` scores at the default elo_goal_coeff
  (0.0023), not production's 0.0008. It is left unchanged here; the S19
  comparison uses production's value.

## 2026-09-30 (#89: NO-side exec cost for away picks)
- On two-way markets (NFL/NHL/NCAA/MLB) the exports now carry the AWAY side's
  Kalshi cost: the NO side of the home contract (NO ask = 1 − home bid, NO
  bid = 1 − home ask), taker and maker, with the same per-fill fee as the home
  side (`away_bid`, `away_ask`, `exec_cost_taker_away`, `exec_cost_maker_away`).
- Soccer (1X2) away fields stay null: NO on HOME is draw-or-away, not an away bet.
- The Desk prices an AWAY pick from it ("… maker (join 0.xx, NO side)") and
  the ledger records those costs; pre-#89 exports and soccer still show
  "exec —". Informational only: no call, unit or tier change.

## 2026-09-30 (NHL-GOALIE: NHL API goalie ingest + v5 candidate)
- New `nhl_goalie_appearances` table and `nhl-goalie-sync`: per-game goalie
  appearances (starter flag, shots / saves / goals against) from
  api-web.nhle.com, mapped to our NHL matches, 2023-24 onward.
  `nhl-goalie-coverage` is the receipt.
- `nhl-backtest --candidate v5`: v1 + each starter's shrunk, decayed save%
  over league average as an Elo adjustment, through the frozen NHL gate.
  Constants are fixed a priori and await ratification before the run.

## 2026-09-30 (#88 re-fit: Kalshi fee rounding is fitted, not assumed)
- The per-fill ceiling failed its receipt (253/629 legs; the misses sat 1¢
  below it). `scripts/kalshi_fee_fill_receipt.py` now scores ceil /
  nearest / floor / banker's over every multi-contract leg (shards priced
  0.00 excluded), prints each rule's rate, and adopts one only at >= 95%;
  otherwise it prints the residuals.
- ADOPTED: Kalshi rounds each fill's fee to the NEAREST cent (542/548 =
  98.9%; ceil 45.3%, floor 54.7%). Exec costs move down by at most 0.1¢
  per contract (NFL 0.55/0.58: taker 0.597, maker 0.561).

## 2026-09-30 (Desk: PASS reasons in two classes)
- A Desk PASS is now tagged "no reference" (no two-sided reference, or too
  few books: greyed, with a "re-run at T-60" hint) or "below floor" (a real
  edge measured and declined). Presentation only: no call, unit or policy
  change. The summary splits the pass count.

## 2026-09-30 (#88 ruled: Kalshi fees round per fill)
- Fees are modelled as one ceiling per FILL of N contracts; the Desk
  assumes N = 10 (provisional until the B-track sizes units). Exec costs
  now carry fractions of a cent (NFL 0.55/0.58: taker 0.598, maker 0.562)
  and the Cockpit shows them to 3 decimals.
- `scripts/kalshi_fee_fill_receipt.py --csv` reproduces multi-contract
  fill fees from the Kalshi CSV (the receipt: five to the cent).
- DEPRECATION: the export's `kalshi_exec_cost` (= `exec_cost_taker`) is
  retired two Cockpit republishes from now (architect 2026-09-30). Read
  `exec_cost_taker` / `exec_cost_maker`.

## 2026-09-30 (#93 ruled: Kalshi maker and taker costs)
- Exports carry `exec_cost_taker` and `exec_cost_maker` (the ruled fee
  multipliers: game series taker M=1 / maker M=0.25, MLB pre-live M=0.5).
  `kalshi_exec_cost` stays as the taker alias.
- The Desk's exec edge and "fee-clears?" use the maker cost by default,
  with the taker cost as the fallback. Calls and units are unchanged.
- The ledger records both costs; imported fills are classified maker /
  taker from their fee, with an alarm for MLB fills at the live rate
  (doctrine: MLB is never executed live).

## 2026-09-30 (NHL-API-PROBE: the H2 goalie-source probe)
- `scripts/nhl_api_probe.py` is read-only. It probes api-web.nhle.com
  (schedule, boxscore goalie stats, roster, pre-game starter and lead time,
  2023–2025 depth) and MoneyPuck's projected-starters CSV, then prints
  FEEDABLE / NOT per need and the H2 reopening line.
- Run it on the laptop and on the host (the datacenter-IP receipt).

## 2026-09-30 (NHL shadow: the failed v1 as a greyed reference model)
- `export-nhl-predictions` writes the FAILED `nhl_elo_v1` for every NHL
  game in the next 36h. Every row is stamped `engine: model_shadow` and
  `gate_verdict: FAILED 0.6909 vs 0.6866`. Nothing is written to the DB.
- The Cockpit shows them greyed under "Reference model — failed gate".
  They never become a Desk call, a venue input or a ledger entry, and the
  window card ignores them.
- `nhl-shadow-grade` and a RESULTS.md shadow section report live CLV only
  (pick-vs-close, value-side). The `nhl-daily` host chain gains the export.

## 2026-09-30 (CORRECTION: soccer Kalshi read as two-way in the fixtures export, window card and line-move)
- CORRECTION, not a feature (#117). On soccer rows the window card's Kalshi
  home price was H/(H+A) even with the TIE leg present. So its venue gap
  and STALE-BOOK? flag compared a two-way number with a three-way book fair.
- A soccer set missing a leg was also labelled two-sided in the fixtures
  export (cups, UNL).
- Soccer now reads P(home) over HOME + DRAW + AWAY. A set missing a leg is
  "partial": no Kalshi price, exec fields, venue gap or Kalshi line-move.
  The Cockpit reads Kalshi-only 1X2 fixtures three-way.
- NFL, NCAA, NHL and MLB are unchanged. Receipt:
  `scripts/kalshi_soccer_twoway_receipt.py`.

## 2026-09-30 (ledger: auto-close reads "Closes #N" lines only)
- The ledger bot matched a closing keyword anywhere in a PR description,
  so a prose mention ("…which closes #111…") closed #111 under the wrong
  PR's name.
- It now reads only lines that start with the keyword (optionally after
  "Ledger:" or a list marker), such as "Closes #1, #2 and #3".

## 2026-09-30 (CORRECTION: soccer Kalshi sets missing a leg were normalized as two-way)
- CORRECTION, not a feature (#113). A soccer prediction row whose Kalshi
  capture lacked a leg (usually the TIE) was normalized over HOME + AWAY
  and marked two-sided, so its exported Kalshi `prob` was inflated.
- Such rows now ship `normalized: false`, `prob: null`, `missing_legs`,
  `input_quality.kalshi: "partial"` and null Kalshi cost fields. Complete
  1X2 sets and MLB rows are unchanged.
- The before/after receipt is `scripts/kalshi_soccer_incomplete_receipt.py`.

## 2026-09-30 (ledger: the bot closes a merged PR's "Closes #N" itself)
- GitHub did not register the `Closes #N` links of Claude-opened PRs, so
  merged work left its Issues open. The ledger bot now closes them on
  merge (Done), keeps a limitation open unless the PR says "Resolves
  limitation", and can replay an already-merged PR (`close-merged`).

## 2026-09-30 (Cockpit: the fun book; Kalshi quotes on MLB/soccer exports)
- The fills importer has a "fun" book: NHL and UNL singles with no
  system call, MVE combos, and non-sport markets. "Off-book other" is
  retired; the REALIZED table and the Copy P&L block print every book.
- MLB and soccer prediction exports gain `kalshi_bid` / `kalshi_ask` /
  `kalshi_exec_cost` (HOME contract, two-sided only; additive), so the
  Desk's exec-edge and join-bid columns work for baseball and soccer.

## 2026-09-30 (Cockpit fills: side from the ticker suffix; a fourth book; no default order)
- The Kalshi fills importer resolves the side from the ticker suffix first
  (`KX{FAM}GAME-{date}{AWAY}{HOME}-{SIDE}`, TIE = draw) and the title second
  ("{Team} wins — {Team}"). Stored fills are re-derived at classification,
  so the 33 "side not resolvable" fills re-classify.
- A fourth book, "system-pick, unlogged": fills that match a stored
  prediction (harvested from results exports) when no ledger call exists.
- The Open calls table shows "—" instead of a default "limit 0.59" on rows
  without a Kalshi ladder.

## 2026-09-29 (the ledger: Issues = state, BACKLOG = history, one Project board = order)
- A fixed label taxonomy (track: / class: / sport: / size: plus
  needs-ruling / needs-operator) and six dated or condition-bound
  milestones, in `.github/ledger/taxonomy.json`.
- `scripts/ledger.py` + the `ledger` workflow:
  - an idempotent bootstrap (labels, milestones, the backfill Issues,
    the board in queue order);
  - an Issue label lint (comments, never blocks);
  - PR title prefix -> track label;
  - `Closes #N` -> In progress / Done;
  - limitations close only with "Resolves limitation"; no closing by
    hand without a PR or a quoted ruling.
- The backfill manifest covers the queue, the open rulings, the
  operator actions and every known limitation, each linked to its
  BACKLOG commit + line.
- CLAUDE.md's queue is now a pointer to the board; `docs/LEDGER.md`
  holds the rules and the six views.

## 2026-09-29 (MLB PHASE A rulings)
- The four PHASE A rulings are logged:
  - empty stage on host-created rows is ratified;
  - the three-status map stands (the observed vocabulary was FT / CANC /
    NS);
  - MLB market-only rows on the host window card are accepted;
  - the doubleheader game-2 difference is waived in the compare
    ("apisports doubleheader gap"). The runbook carries the compare
    line.

## 2026-09-29 (MLB PHASE A: api-sports fallback for host MLB history; PHASE B closed negative)
- `sync-matches` / `sync-teams --competition MLB` use api-sports Baseball
  wherever `SP_SKIP_FAMILIES` names MLB (the DO host); the laptop keeps
  statsapi. Gate met: 100.0% score parity.
- Stage is never read from the provider's `week`: created rows carry
  stage NULL, and paired statsapi rows keep theirs. Status mapping is
  conservative, and a finished row is never downgraded.
- Known limitation, receipted every run: doubleheader game 2 is absent
  from api-sports. Existing rows are marked "apisports-unavailable",
  never fabricated.
- Host chain `mlb-history` + `sp-mlb-history.timer` (10:30 UTC): sync
  only, no MLB predictions on the host.
- PHASE B verdict logged: api-sports Baseball has no pitcher, bullpen
  or umpire feed. MLB predictions stay on the laptop.

## 2026-09-29 (MLB PHASE B probe: pitchers / bullpen / umpires from api-sports?)
- `scripts/mlb_phase_b_probe.py` is read-only. It classifies candidate
  api-sports Baseball endpoints and flags pitcher / bullpen / umpire
  fields, with a verdict per need.
- To be run on the laptop. The receipt is pending.

## 2026-09-29 (MLB-PROBE verdict + follow-up)
- Architect verdict logged: api-sports Baseball is GREEN for MLB
  schedule/results and AMBER for predictions (no pitcher, umpire or
  bullpen data).
- The probe fix: our DB stores status "finished" (lowercase), so score
  parity was never computed.
- It now prints score parity against the 99.5% PHASE A gate, a sample of
  disagreements, and every unpaired finished game with a doubleheader /
  UTC-boundary suspect read.

## 2026-09-29 (cosmetics lane C: utcnow sweep, MVE combo fills, ntfy topic validation)
- `datetime.utcnow()` / `utcfromtimestamp()` are replaced everywhere by
  `src/timeutil.py` helpers. These are built on `now(timezone.utc)` and
  stay naive UTC, so there is no behavior change.
- The fills importer classifies Kalshi MVE combos by leg content:
  sports legs → off-book sports parlays.
- An ntfy topic containing whitespace is refused at startup: chains fail
  loudly and never page the wrong topic.

## 2026-09-29 (late-news follow-on: T-90 injuries in the imminent tier, quarantine-class line moves)
- The window service's imminent tier syncs injuries for the NFL/soccer
  games kicking off within 2h. The sync is scoped per team, and the
  T-90 check now compares injury content.
- Line-move pages ignore quiet hours and go out at high priority.
- `late-news?` is also on the MLB and soccer prediction exports.
- Known limits logged: soccer line-move is Kalshi-only; MLB follows
  capture cadence.

## 2026-09-29 (MLB-PROBE: api-sports Baseball vs statsapi, read-only)
- `scripts/mlb_apisports_probe.py` reports coverage vs our 2025/2026
  MLB matches, ID mapping via the odds join, status vocabulary and
  postseason game types. No wiring.
- To be run on the laptop. The receipt is pending.

## 2026-09-29 (hosting: bootstrap catch-up — laptop completeness sweep)
- `bootstrap.py catch-up --reference <host fingerprint>`: for each
  competition-season where the laptop counts fewer games, it runs
  sync-teams then sync-matches.
- Dry run by default. `--apply` backs up first, receipts each season
  before and after, and stops at the first failure.

## 2026-09-29 (K-track: Kalshi fee schedule receipt; K2 join bid + order type/fill)
- Fee schedule receipt (July 2026 schedule): taker 0.07 is confirmed.
  Maker is 0.0175 × M, with M = 0 unless the series is listed.
  - The game-series maker multiplier is NOT verified: the PDF is
    unreadable from the build environment.
  - Kalshi rounds to the centicent per order, so our per-contract cent
    rounding overstates the fee (logged; unchanged pending a ruling).
- Desk: join bid (bid + 1¢) beside exec cost. A 1¢ spread shows
  "joining = taking".
- Positions record order type (limit/market) and fill price.

## 2026-09-29 (Cockpit K2: executable-edge display)
- The Desk shows exec edge = model − Kalshi (ask + fee) beside the fair
  edge, with "fee-clears?" at ≥ 4pp. It is informational only: no
  sizing, tier or call change.
- Positions record the Kalshi exec cost at claim and at execution.

## 2026-09-29 (MNF QB verdict; line-move alarm; T-60 closing-freshen doctrine)
- QB audit verdict logged: the cause was sync timing plus provider
  latency. The Chicago starter was absent from the provider's report at
  both pre-game syncs. The detection code is exonerated.
- New line-move alarm:
  - inside T-3h, a ≥ 6pp net move on book or Kalshi (stored snapshots,
    no provider calls) marks the row `late-news?` in the window card
    and the NFL export;
  - it pages on the card topic and triggers `freshen:<family>`.
- CLI.md doctrine: the game-day T-60 closing freshen is mandatory for
  model sports while the laptop is writer of record.
- The host-journal receipt for Monday's T-90 check is pending, to be run
  on the host (commands in the PR).

## 2026-09-29 (#63 rulings: value-side anchor timestamp on every grade)
- The architect ratified all four #63 decisions: all-sport scope, the
  earliest pre-kickoff book anchor, tagged quarantine shadows, and
  snapshot growth deferred to pruning.
- `nfl-grade` value-side lines now show the anchor and prediction
  timestamps, and flag an anchor that came after the prediction.
- `export-nfl-results` rows carry the value-side fields and anchor
  timestamp (additive).

## 2026-09-29 (Week 4 MNF rulings: value-side shadow, value-side CLV, QB feed audit)
- Cockpit: the Desk evaluates edge on every side. A value side that is
  not the top pick and clears 4pp logs a `value_shadow` at 0.25u
  notional.
  - It is graded like quarantine shadows and never staked.
  - It has its own counterfactual line, with promotion review at 30
    graded (policy v1.2 candidate).
- `nfl-grade` and RESULTS.md print value-side-vs-close beside
  pick-vs-close.
  - `sync-odds-football` now appends a book-consensus snapshot on every
    sync, which serves as the anchor.
  - Games without one are counted as unanchored.
- NFL QB detection: positions resolve by id, then name, then a unique
  initial+surname. QB/Quarterback both count. Still-listed players are
  no longer dropped by the 14-day filter.
- The export gains `positions_unresolved`.
- New read-only `nfl-qb-audit` (with `--live` for the H1/H2/H3 verdict).
  The receipt on MNF data must run on the host/laptop.

## 2026-09-28 (hosting: sp_run transient-step retry)
- sp_run retries a step that fails TRANSIENTLY (connection errors,
  timeouts, HTTP 5xx/429) twice, 15s then 45s. The receipt says
  `retried N`.
- A step still failing pages as before. Other 4xx and exceptions in our
  own code never retry.

## 2026-09-28 (Cockpit: execution-timing rule, policy v1.1 addendum)
- Positions carry claim_at (frozen claim price) and executed_at (default:
  last freshen before kickoff; or an explicit, recorded "Execute now").
- Grading settles at the execution price, with a claim-price counterfactual.
  The P&L block gains a "claim vs exec" column and an EXECUTION TIMING
  section. No sizing changes.

## 2026-09-28 (hosting: ncaa-market Thursday run)
- sp-ncaa-market adds Thu 16:00 UTC (Thursday-night slates' fixtures
  file). On the host: re-run install.sh after the pull.

## 2026-09-28 (hosting: exhibit 1 fixes — injuries, keyed comparator, SHA-stamped exports)
- nfl-predict syncs NFL injuries first (chain gap); a CI guard audits every
  prediction chain (MLB exempt: no injury source).
- compare_exports keys game rows on (kickoff, home, away), not match_id,
  and names unmatched rows.
- Every JSON export carries its producing `git_sha`. "Code-version skew"
  is an explained class only when both SHAs are present and named.
- Exhibit 1's divergence log is recorded in the runbook.

## 2026-09-28 (hosting: nhl-daily single-day syncs)
- nhl-daily syncs yesterday/today/tomorrow as three single-day calls that
  the hockey adapter honours, instead of one silent whole-season pull.

## 2026-09-28 (hosting: NHL opening-day gate + season gates as config)
- nhl-daily activates 2026-09-29 (2026-27 opening day; was the 2025-derived
  2026-10-07).
- Season gates are configurable per chain (`SP_NHL_ACTIVE_FROM` in
  host.env; malformed fails loudly). Every run prints and receipts
  `active from <date> [<source>]`.

## 2026-09-28 (hosting: P4 Tailscale SSH status)
- Tailscale SSH is enabled server-side (`sudo tailscale set --ssh=true`
  returned silently). The invalid `tailscale status --json | grep -i ssh`
  receipt is dropped. Client-side verification is pending (Mac MagicDNS);
  the tailnet-IP door is the proven standard, and the P4 receipt uses it.

## 2026-09-28 (exports: current-slate windowing)
- Prediction exports default to the current slate: kickoffs in the next
  36h for NFL and soccer. MLB keeps its one 08:00-UTC slate-day (ruling:
  it plays daily). Use
  `--week` (NFL) / `--days N` for the full look-ahead. Explicit dates keep
  their slate-day meaning. Generation is unchanged; only the file's rows
  are scoped.
- A `window:` receipt line is printed. freshen:SOCCER now uses the 36h
  default (a one-slate closing file).

## 2026-09-28 (hosting: H1b day one + runbook field amendments)
- H1b parallel week started 2026-09-28 13:45 UTC: 12 host timers,
  SP_PARALLEL_MODE=full, MLB timers off by ruling. The earliest cutover
  decision is after 2026-10-05 13:45 UTC (criterion 1: 7/7 days).
- Runbook P4: sp gets NOPASSWD sudo + Tailscale SSH (receipt-gated) before
  root is sealed. The console is emergency-only after P4. Mac VPN clients
  conflict with Tailscale (quit them before tailnet steps).

## 2026-09-28 (hosting: pull-exports lane)
- `deploy/hosting/pull_exports.py`: the laptop pulls the host's exports/
  over the tailnet into exports/host/ (never its own exports/). The host
  comes from SP_HOST_ADDR. Newest-wins, idempotent, all-or-nothing on an
  unreachable host, receipted (pulled / unchanged / newest window_24h.json).
- `scripts/setup_export_pull.sh`: optional hourly launchd job at :10.
- Docs: CLI.md hosting table, runbook T12b (laptop pulls; push is H2).

## 2026-09-28 (Cockpit: ledger doubling fix)
- Root cause: re-logging a multi-day file on a later day re-captured every
  call under a new log_date key (reproduced: 12 → 24). Import ledger merged
  by stored id. The Kalshi CSV import only re-rendered the doubled totals.
- The ledger key is enforced on every write path; import merges by
  recomputed key. Unit of account = the POSITION (ratified): a re-log on a
  later day reprices that position in place, never a second row.
- New "Dedupe ledger" repair (reports how many it removed) + a stored-
  duplicates warning on the Ledger tab.
- Capture only before kickoff (multi-week files no longer log played
  games); "Copy ledger (JSON)" with a text-box fallback + "Import pasted".
- scripts/cockpit_ledger_verify.py: 21/21 (import twice → identical totals).

## 2026-09-27 (window service: freshen chains + proximity tiers)
- freshen:NFL / freshen:MLB / freshen:SOCCER defined; the window service
  triggers them on T-90 news (chain lock, one per family per hour, MLB
  never on the host), then rebuilds the card.
- Proximity tiers: far (>6h) schedule check only, near (2-6h) + odds and
  Kalshi, imminent (<2h) + T-90 detection; receipt counts steps skipped.

## 2026-09-27 (window service: Next-24h card + delta pages)
- Hourly `window` chain (sp-window.timer, enabled on H1b day 1): single-day
  match syncs, window-scoped odds + Kalshi, then `window-card` →
  exports/window_24h.json. No model runs; model fields copied from the
  canonical exports.
- Delta pages to a second ntfy topic (NTFY_CARD_TOPIC), quiet hours
  00-07 ET except quarantine flips, one 08:00 ET digest.
- Quota line on every chain receipt.
- Cockpit "Next 24h" tab (headless receipt 12/12).

## 2026-09-27 (H1a CERTIFIED PASS)
- Host bootstrap certified: compare clean, no waivers. The laptop was the
  side short 67 UEL 2024/25 games (clubs never team-synced), now fixed.
- Law recorded: sync-teams before sync-matches for every new
  competition-season (CLAUDE.md, CLI.md).
- compare rows label each count laptop / host.

## 2026-09-27 (fingerprint receipts + hardening)
- bootstrap explain / explain-diff: the counting predicate, the same rows
  counted four ways, and every uncounted row's status/status_raw/stage/
  external_ids, diffed laptop vs host.
- Fingerprint groups by competition_id (LEFT JOIN, orphans labelled),
  self-checks against raw COUNT(*); compare sums duplicate status entries.
- remove_allstar_rows dry-run prints the NFL teams with the fewest games.

## 2026-09-27 (host Pro Bowl cleanup, authorized)
- deploy/hosting/remove_allstar_rows.py: host-only, receipted removal of
  pre-exclusion Pro Bowl rows (dry-run default; --apply backs up first,
  cascades through declared FKs in one transaction, prints post-counts).
- Event backups (_precleanup_, _prerefresh_) never count as the daily.
- Waiver policy: real provider drift only; UEL 2024/25 needs none.

## 2026-09-27 (H1a compare rulings: Pro Bowl exclusion, waivers, EL1/EL2 refresh)
- NFL adapter excludes Pro Bowl / all-star games and teams, printing each
  excluded row.
- bootstrap compare --waive COMP:SEASON:reason: row still printed as
  WAIVED, recorded in the receipt.
- Monday soccer-refresh (chain + routine doc) syncs EL1/EL2 2026/27 first.
- Fingerprints embed the producing bootstrap.py git blob SHA; compare
  refuses version-mismatched or unstamped fingerprints (the UEL 269 vs 202
  delta was version skew, not data).

## 2026-09-27 (bootstrap --skip-family: MLB Stats API blocks datacenter ASNs)
- bootstrap.py --skip-family MLB: MLB sync-teams/sync-matches receipted
  SKIPPED-ASN, numbering unchanged (resume --from 8); compare reports the
  family N/A-host.
- Runbook: MLB is a laptop duty; host MLB timers off; post-cutover egress
  is an H2-era decision.

## 2026-09-27 (Hosting H1 phasing: fresh bootstrap first)
- Runbook re-ordered: H1a fresh bootstrap (host syncs its own DB;
  acceptance = BACKLOG fingerprints reproduced), H1b independent parallel
  week, H2 cutover = the one .backup migration (why it can't be skipped).
- deploy/hosting/bootstrap.py: fingerprint / plan / run / compare.
- compare_exports: divergence classes = capture timing + provider
  pagination.
- Model registry seed (ratified): production model_versions rows seeded
  at bootstrap (config only; books stay empty); compare verifies model
  identity; the four model-bearing timers enable with the rest.
- Cutover criterion 3 amended before day 1: "capture timing or explained
  provider pagination, each explained".

## 2026-09-27 (Hosting H0 final four; FOUND SAFETY GAP logged)
- Paging via ntfy.sh (NTFY_TOPIC in .env); held PASS pages and logs.
- Backups: DO weekly on + nightly laptop pull (deploy/hosting/pull_backup.py,
  scripts/setup_backup_pull.sh); host retention 14 dailies, prune
  report-only until the first manual prune is reviewed.
- CLV captures confirmed on America/New_York; NCAA timer enabled.
- On the record: improve auto-promoted on PASS (masked by 36 rejections);
  closed by hold-on-pass + ratify-candidate.

## 2026-09-27 (Hosting H1: systemd pack + runbook, inert until provisioning)
- deploy/hosting/: chain definitions (CI-checked against cli.py), sp_run
  receipts writer, .backup/prune/notify/boot-receipt/deploy scripts,
  migration pack/verify/install, parallel-week export diff, 21 systemd
  unit/timer files, install.sh (enables nothing).
- docs/specs/hosting-h1.md: provisioning runbook (BROWSER/TERMINAL),
  frozen cutover criteria, H0 rulings record, 4 open items.
- H0-5 guard: `improve --hold-on-pass` holds a PASS and pages;
  `ratify-candidate` promotes on explicit ratification. Default unchanged.
- CLI.md: pre-slate `sync-umpires --today`; improve/ratify rows.

## 2026-09-27 (Cockpit: Kalshi fills import, two-book accounting)
- Ledger tab: "Import Kalshi CSV" -> REALIZED section (system-matched /
  off-book sports / off-book other; staked, fees, pre-fee, net, avg fill,
  fees % of loss) + plausible-match review list; in the Copy P&L block.
- CSV mapping verified on the real Kalshi export header; trailing-30-day
  avg fill + fee per $ staked (ledger-level).
- scripts/cockpit_fills_verify.py (20/20, real header).

## 2026-09-27 (K1: Kalshi bid/ask stored; executable-cost fields)
- odds_snapshots.yes_bid / yes_ask filled by every Kalshi sync going
  forward. Run `python migrate_kalshi_quotes.py` after merge, before any
  chain.
- NFL predictions + fixtures exports add kalshi_bid, kalshi_ask,
  kalshi_exec_cost (ask + fee; fee formula ARCHITECT-VERIFY) —
  informational until the executable-edge ruling.

## 2026-09-27 (K0: Kalshi storage receipt)
- `scripts/k0_kalshi_storage_probe.py`: read-only probe of what a stored
  Kalshi snapshot holds. Code read: only a derived prob (bid/ask mid,
  single side, or last price) — bid/ask are not persisted.

## 2026-09-27 (cosmetics batch)
- nfl-backtest verdict text for the live era (provenance/regression);
  stale rehearsal docstrings updated.
- export-nfl-results no longer writes the fossil `"rehearsal": true`.
- docs/CLI.md: sync-matches options, sync-kalshi-ncaa, daily backup,
  NFL LIVE section, full Kalshi series list. .env.example: football and
  hockey API keys. api_hockey docstring matches its actual key fallback.

## 2026-09-27 (U2: NFL export "why" fields)
- NFL predictions export adds elo_home, elo_away, elo_gap,
  home_adv_applied, rest_days_home, rest_days_away. Additive only.
- export-nfl-predictions warns (ELO DRIFT) when an NFL game finished
  after the predictions were written; silent otherwise.

## 2026-09-26 (Cockpit v0.4 — P&L / self-grading organ, policy v1.1)
- tools/cockpit.html: Ledger tab (localStorage bd_ledger_v1, export/
  import), "Log today's calls", venue-edge engine (shadow, 0.25u),
  results/fixtures grading intake, by-engine reports, equity + quarantine
  counterfactual, per-rule attribution, Copy P&L block, non-claims.
- docs/specs/cockpit-v04-pnl-organ.md (spec, verbatim).
- scripts/cockpit_v04_verify.py: headless capture -> grade -> report
  check (24/24).
- Venue-edge charter narrowed (ruling): market-only family only (NHL,
  NCAA, cups when priced); model sports (NFL etc.) emit model_edge only.
- venue.py: doc line — fixtures' kalshi.prob is the raw stored value.

## 2026-09-26 (NFL export: STALE-BOOK? venue flag)
- NFL predictions export adds kalshi_prob, venue_gap_pp and venue_flag
  ("STALE-BOOK?" when |book fair - Kalshi| >= 8pp). Warning only —
  quarantine unchanged. export-nfl-predictions prints the flagged games.
- Logged: vetted verdicts (NFL FAIL, NCAA INSUFFICIENT-REF) and the
  stale-at-source football moneyline finding.

## 2026-09-26 (full-loop ruling logged: venue-edge engine)
- Docs only. Architect ruling: a second recommendation engine
  (venue_edge: book fair vs Kalshi, |div| >= 5.0pp, fixed 0.25u, shadow)
  beside model_edge; ledger reports by engine; policy -> v1.1. Build
  held for the v0.4 spec.

## 2026-09-26 (spread-fallback check vetted; fallback dark)
- `spread-fallback-check`: per-row ML_books + capture timestamps/gap;
  verdict on the vetted set only (ML_books >= 4, gap <= 24h; same 3.0pp
  bar); UNRELIABLE-REF rows printed; INSUFFICIENT-REF when vetted n < 10.
- Spread fallback gated DARK (`FALLBACK_LIVE = False`): exports carry
  1X2-sourced fair prices only until a vetted PASS.
- Logged: lane 6 closed (scope clean, gate 0.6361 PASS), score-90 HOLD,
  quarantine ruling ratified as built, #27 lands as a draft.

## 2026-09-26 (hosting H0 draft, for review)
- Docs only. `docs/specs/hosting-h0.md`: VPS candidates, Tailscale-only
  posture, systemd unit inventory from the CLI.md chains, `.backup`-API
  migration runbook (checksums, 7-day parallel run), receipts-log
  format, CLI.md/cli.py discrepancies, ARCHITECT-RULE open questions.
  Draft for architect review — not a decision; nothing deployed.

## 2026-09-26 (spread->win-prob fallback, american football)
- NFL/NCAA games with no 1X2 consensus but posted spreads now get a
  spread-derived fair (normal margin; median book home line; sigma
  frozen a-priori NFL 13.45 / NCAA 16.5). Additive export field
  `fair_source` ("1X2" | "spread_derived") on every market block, plus
  `consensus_home_spread` / `spread_sigma` on derived blocks. NFL
  quarantine/divergence unchanged (1X2 only). Receipt command:
  `python cli.py spread-fallback-check --competition NFL|NCAA`.
  Acceptance receipt pending Anthony's real run; bar 3.0pp frozen
  before results.

## 2026-09-26 (data/ created at connect time)
- Importing the package no longer creates an empty data/ directory; the
  SQLite directory is created on first connection instead.

## 2026-09-26 (sync-odds-football rename)
- `sync-odds-nfl` renamed `sync-odds-football` (covers NFL + NCAA); the
  old name remains an alias — no chain changes needed.

## 2026-09-26 (NCAA book-market finding logged)
- Docs only. College books post spreads, not moneylines: 12/116 book
  consensus vs Kalshi 99/116 — Kalshi-primary confirmed. Queued:
  spread->win-prob fallback (K-track, after Cockpit v0.4, architect
  spec); `sync-odds-nfl` -> `sync-odds-football` rename (next daily batch).

## 2026-09-26 (NFL model paths scoped to competition NFL)
- Ratings, backtest pot, prediction set, export and grading now select
  Competition.code == "NFL" explicitly (NCAA shares Sport.NFL).
  predict-nfl and nfl-backtest print a scope line (teams, games,
  competitions) with a SCOPE ALERT on contamination.

## 2026-09-26 (H2 goalie probe verdict: NEGATIVE)
- Docs only. The hockey provider has no goalie/lineup/player endpoints
  (only /games/events answers). H2 reopens only via an external data
  source; NHL market-only indefinitely. Bounded authorization closed.

## 2026-09-26 (migrate_score_90 invariant revised)
- Receipt prints breaching rows verbatim + the AET/PEN stage table.
  Revised law: FT 90'==score; AET/PEN 90'<=stored per side; level at
  90' only for single-match ties (stage-based). No column changes —
  re-run `python migrate_score_90.py` after merge.

## 2026-09-26 (H2 probe fix; morning findings logged)
- `scripts/h2_goalie_probe.py`: prints one raw /games object verbatim
  first; date/timestamp parsing tolerant of the hockey string shape
  (fixes the `_game_ids` crash).
- BACKLOG: architect findings — NHL 20-25% past-regulation (status_raw
  splits); lineup probe GREEN (XI from ~2015, minutes from ~2018).

## 2026-09-26 (soccer ET flag + 90-minute score)
- Football adapter stores status_raw (FT/AET/PEN) and score.fulltime in
  new matches.home_score_90 / away_score_90. Storage only — scores and
  results unchanged. Run `python migrate_score_90.py` after merge
  (receipt includes the 90-minute invariants).

## 2026-09-26 (lineup-history probe)
- `scripts/lineup_history_probe.py`: read-only probe of API-Football's
  per-match lineup history — declared coverage per season plus spot
  checks (lineups + per-player minutes). No DB access, no wiring.
  Anthony runs it and pastes the output to the architect.

## 2026-09-26 (H2 goalie/lineup probe)
- `scripts/h2_goalie_probe.py`: read-only probe of the hockey provider
  for starting-goalie / lineup data — endpoints, fields, historical
  depth, pre-game availability. No DB access, no wiring. Anthony runs
  it and pastes the output to the architect.

## 2026-09-26 (NHL raw status storage)
- matches.status_raw: the provider's status code kept verbatim; the
  hockey adapter stores FT/AOT/AP (OT/SO wins distinguishable). Run
  `python migrate_status_raw.py` after merge, then a full NHL sync.

## 2026-09-26 (mission declared)
- CLAUDE.md: Mission section (architect, verbatim) at the top; queue
  re-ranked — Cockpit v0.4 P&L/self-grading at the head, K-track
  (Kalshi-executable edge accounting) and B-track (bankroll doctrine)
  opened behind it; closed items moved to a record list. Docs only.

## 2026-09-25 (NHL Phase 2 closed; market-only launch wiring)
- nhl_elo_v4 FAIL ratified (0.6907). Ledger v1 0.6909 / v2 0.6921 /
  v3 0.6952 / v4 0.6907 — schedule-only floor ~0.691 vs bar 0.6866.
  NHL model track suspended; Oct 7 launch is market-only.
- `export-fixtures`: Kalshi presence, latest pre-kickoff book consensus,
  printed odds-label receipt; NHL-ready. Cockpit: fixtures header +
  Kalshi fixed. Docs: NHL daily market-only chain.

## 2026-09-25 (NHL candidate v4 — last schedule-only; cup track suspended)
- nhl_elo_v3 FAIL ratified (0.6952). `nhl-backtest --candidate v4`: v1
  form, 12-point shrink grid (k 3-6 x home adv 35/40/45), v3 selection,
  2025 once. If it fails: no v5, Oct 7 market-only, track suspends
  pending the H2 goalie probe.
- Cup fix-v2 re-exam FAIL (14.76pp; inversion cleared): cup model
  track SUSPENDED for the season (rotation information floor); EFL/CL/
  UEL market-only; machinery stays merged.
- CLAUDE.md production state + queue status updated.

## 2026-09-25 (cup fix-v2 — gate-class)
- Cup re-exam FAIL ratified (sign inversion 2/5, mean 18.11pp).
- Cup elo_goal_coeff by context (same-/cross-league), tuned on prior
  cup matches with the exam's seasons excluded; `cup-exam` tunes then
  prices (`--cup-coeffs base` reproduces the old exam). League pricing
  untouched; nothing persisted.
- CLAUDE.md: market-is-a-reference doctrine; queue tail S19-S20, H2,
  data items (football 90'/ET flag, NHL OT/SO); S18 retired as
  already-shipped; deep-research disposition logged.

## 2026-09-25 (NHL candidate v3 — gate-class)
- nhl_elo_v2 FAIL ratified (2025 0.6921, upper bands overconfident).
- `nhl-backtest --candidate v3`: params selected by walk-forward
  validation inside 2024 (60% fit / 40% validation), full-2024 refit,
  2025 scored once; grid extended downward/center only. Gate unchanged.
- Standing fallback logged: no pass by Oct 6 -> NHL opens Oct 7
  market-only.

## 2026-09-25 (cup fix — gate-class)
- Cup/intl pricing: attack/defense from each team's domestic
  league-season fit (as-of-date), blended toward the cup fit by n/(n+5);
  every fit leave-self-out, strictly before kickoff.
- Ruling B: unrated / no-domestic-league cup fixtures are market-only
  (never priced); the exam reports them separately, outside INVALID.
- elo_goal_coeff unchanged (0.0008). League pricing untouched.
- Coverage floor: fewer than 45 scored fixtures = exam INVALID
  (architect amendment).

## 2026-09-25 (NHL candidate v2 — gate-class)
- nhl_elo_v1 FAIL ratified (0.6909 vs <= 0.6866); bar unchanged.
- `nhl-backtest --candidate v2`: frozen 720-point grid tuned on
  2024-internal sequential loss only, then 2025 scored once. v2 = v1 +
  rest days (back-to-back emphasis) from the existing schedule.

## 2026-09-25 (cup pricing hypothesis check)
- `cup-exam --detail` adds strength-fit receipts: per-side fit n,
  attack/defense, promoted-prior flag, self-in-fit, pool/backfill,
  summary. No pricing change.
- BACKLOG: code receipts for the cup strength window and the
  elo_goal_coeff under-dispersion; architect ruling B (out-of-pot =
  market-only) logged.

## 2026-09-25 (NHL Phase 2 — gate, then Elo v1; gate-class)
- `python cli.py nhl-backtest`: frozen NHL gate (train 2024, test 2025,
  preseason excluded by stage/date, OT/SO-inclusive home win), both
  baselines, three acceptance criteria, verdict. Writes nothing.
- nhl_elo_v1: MOV + per-team season regression; parameters a priori,
  home advantage from the 2024 home rate.

## 2026-09-25 (cup exam diagnostics)
- Cup exam verdict FAIL (mean |Δ_H| 13.86pp, sign 60%): cups stay locked.
- `cup-exam --detail`: per-row Elo/league/bonus inputs, |Δ_H| splits
  by pot membership and tier, default-Elo team count. No pricing change.

## 2026-09-25 (cup acceptance exam — gate-class)
- `_generate_predictions_soccer(include_finished=True)`: report-only
  pricing of finished fixtures; returns rows, writes nothing.
- `python cli.py cup-exam`: scores production pricing against
  exports/cup_answer_key.csv on the frozen bar (±8pp MAE, <=13 over
  8pp, EFL round-2 sign check); necessary-not-sufficient semantics.
- Removed superseded tools/betting_desk.html and
  tools/predictions_card.html (cockpit.html is the live surface).
- BACKLOG: architect's stale-entry disposition logged verbatim.

## 2026-09-25 (security warm-up — first Claude Code PR)
- Web UI: cross-site (CSRF) check on all state-changing requests;
  Host allowlist against DNS rebinding; Tailwind pre-built and
  htmx/Chart.js vendored — the UI loads no third-party scripts.
- tools/cockpit.html: escapes file- and model-supplied text (XSS).
- tests/ + pytest in CI; CLAUDE.md workflow: Claude Code works
  branch + PR only, Anthony merges.

## 2026-09-25 (working arrangement v2)
- CLAUDE.md shipped: Claude Code onboarded as repo executor; chat
  remains architect. Tarball era closes.

## 2026-09-25 (NCAA)
- NCAA wired into the american-football adapter (league map, both
  competitions listed, per-code resolution); cli routes NCAA; data +
  market-only doctrine.

## 2026-09-24 (cockpit)
- Card + Desk merged into one tabbed cockpit artifact (same URL);
  per-game signal expanders; tools/cockpit.html supersedes both files.

## 2026-09-24 (predictions card)
- Predictions Card artifact: sport-aware model viewer over the exports
  (bars, edges, quarantine, QB, gaps) — the post-GPT cockpit's second
  organ; in-repo copy versioned.

## 2026-09-24 (SDLC)
- Community standards shipped (CONTRIBUTING = the laws, CoC, SECURITY,
  MIT LICENSE, issue/PR templates) + CI (parse + import smoke on every
  push). PR doctrine: direct-to-main daily; branch+PR for gate-class.

## 2026-09-24 (H-track 1c)
- sync-kalshi-nhl (third sport on the shared matcher); export success
  string updated to LIVE format.

## 2026-09-23 (NHL Phase 1)
- api_hockey adapter shipped (cloned from american-football; id 57,
  AOT/ASO handling, preseason captured); registry, sport router, and
  --seasons wired. Backfill block issued.

## 2026-09-23 (H-track)
- NHL Phase 0 probe shipped: read-only plan/id/season-format recon with
  famous-club receipts.

## 2026-09-23 (cup exam prep)
- scripts/extract_cup_key.py: read-only answer-key extractor for the
  cup acceptance exam; report-only pricing mode scoped for next session.

## 2026-09-23 (perf)
- Match-sync O(n^2) fixed: per-sync prefetch cache replaces per-row JSON
  full scans; morning chains move to 2-day sync windows (full-season
  weekly).

## 2026-09-23
- H-track opened: NHL onboarding planned on the NFL playbook (phased,
  gate-first, preseason-as-shakedown); sequenced behind the cup
  acceptance exam.

## 2026-09-22
- **NFL LIVE (Week 3 ratified):** rehearsal flag dropped; per-row
  market_divergence_pp + quarantine field (>=15pp) implements the
  contract rule structurally.

## 2026-09-21 (rebuild)
- DB destroyed by packaging incident; restored from 09-17 backup and
  fully rebuilt same morning. v22 re-promoted on the full 16,546-match
  / 24-competition pot (spread 101%, documented drift override).
  Packaging + backup laws now in force.

## 2026-09-21 (desk v0.3)
- Betting Desk v0.3: multi-sport multi-file intake, cross-sport parlay
  builder (correlation-screened, positive-edge, 0.25u), audit expanded
  to per-game notes + parlay critique + prediction-layer signals
  feedback.

## 2026-09-21
- Engine-level SQLite pragmas (WAL + synchronous=NORMAL + busy_timeout)
  on every connection — fixes the morning-lag regression from db-tune's
  per-connection NORMAL.

## 2026-09-20 (desk v0.2)
- Betting Desk v0.2: sport-aware ladder (no DC on 2-way boards),
  monotone sizing, near-floor tempering, correlation flag — both day-1
  NFL defects fixed by the desk's own audit arm; now versioned in-repo
  (tools/betting_desk.html).

## 2026-09-20 (shadow day 1)
- First divergence report: slate-shape convergence; three structural B1
  requirements identified (input freshness, consensus quality,
  two-stage clearance); app-side injury-recency flag queued.

## 2026-09-20 (B1)
- Betting Desk artifact shipped: browser-local policy engine + Claude
  audit over daily exports — the B1 shadow vehicle.

## 2026-09-20 (B-track)
- B-track opened: native betting layer design committed (policy-as-code,
  shadow-vs-GPT migration path, audits-as-requirements). Sequenced after
  cup acceptance + U1 unless platform deadlines force it.

## 2026-09-20 (db)
- `db-tune`: WAL mode, ANALYZE, composite indexes, optional VACUUM,
  probe timing — first response to season-scale DB lag; snapshot
  pruning/rollup queued as the structural fix.

## 2026-09-20
- API-Football request spacing now env-configurable (API_FOOTBALL_RPM;
  default 10/min): the 2:04-per-odds-sync metronome was the free-tier
  pace hardcoded — paid plans can cut the European sweep's odds legs
  from ~12 minutes to ~30 seconds. 429 backoff unchanged as safety net.

## 2026-09-19 (feeder backfill)
- Nine feeder leagues backfilled: ~7,988 matches, zero skips. Monday
  refresh pot ~20,600 across 24 competitions.

## 2026-09-19 (feeders)
- Nine CL/UEL feeder leagues wired data-only (NED POR BEL SCO TUR AUT
  SUI GRE CZE) with strength priors; Nordic calendar-year leagues
  deferred pending season-string support.

## 2026-09-19 (backfill)
- Expansion backfill complete: 4,468 matches / 4 leagues, zero skips;
  ELC activated. 15 competitions, 5 countries.

## 2026-09-19 (expansion)
- Coverage expansion decided: La Liga, Serie A, Bundesliga, Ligue 1 +
  ELC activation — no code needed (pre-wired); backfill plan issued,
  refresh held to Monday as one gated transition, shadow-matchweek
  doctrine applies.

## 2026-09-19 (v22)
- **v22 promoted** — first soccer model change since v18: per-team
  regression, 8,137-match pot (pyramid/Euro/WC), spread guard passed
  99%; Southampton drift justified (50 ELC matches entered) with a
  documented one-time --max-drift override. Refresh reopened.

## 2026-09-19 (later)
- Compression CONVICTED by the probe (interleaved "2026"/"2026/27"
  season strings firing six tail regressions; pyramid exonerated) and
  FIXED: per-team season regression in elo.train (NFL semantics).

## 2026-09-19
- `scripts/compression_probe.py`: instrumented double-train (pot A/B)
  with inline regression markers — locates the Elo collapse empirically.
- U1 (per-sport daily cards + unified page) committed as next dedicated
  build session.

## 2026-09-17
- `capture-weather-nfl` (N1 phase 1): 32-stadium map keyed by home team,
  roofed handling, Open-Meteo capture into GameWeather — tracking only.
- S14 Stage-1: flat +1.0 uncertain-bucket totals correction selected
  counterfactually (direction 39%->52% in-sample); Stage-2 out-of-sample
  acceptance frozen pre-results.
- Cap-variant verdicts: all four declined (caps cost log-loss; shrink
  degraded the weakest band) — v1 unchanged; bonus finding: the >0.80
  zone was under-confident on 2025 (0.800 stated / 0.833 realized).
- `nfl-backtest-caps`: R-track cap/shrink variant harness (acceptance
  frozen pre-results); untestable asks (road-inversion, divisional)
  declined with reasons. Matched-zero sentinel extended to the shared
  MLB/NFL Kalshi path.

## 2026-09-16
- S14 verdict: soccer totals under-projection is bucket-shaped
  (uncertain-winner games +1.17 goals, confident +0.08, n=46) — fix
  hypothesis queued for Stage-1 backtest. CLI.md corrected:
  totals-check/calibration-series are MLB-only.

## 2026-09-15
- Hotfix: results-tally join corrected (outcomes link via prediction_id
  → Prediction → Match, not match_id) — caught on first run.
- **`results-tally`** → `RESULTS.md`: rolling 30-day per-sport record
  (sides, log-loss, CLV), auto-generated, linked from README; joins the
  morning rhythm.
- **`export-nfl-results`**: graded NFL results file in the standard
  consumer shape (rehearsal-flagged) — NFL joins the results-file rhythm.
- Week 1 NFL final: 9/16, log-loss 0.6755 (both max-conviction rows
  lost); MW4 soccer: 5/10, giant edges split — Forest won, Hull and
  Everton missed by draw (cohort 6/12, four misses-by-draw).

## 2026-09-14
- NFL Week 1 graded via `nfl-grade` (first live read): 9/15 sides,
  log-loss 0.6441 vs 0.6361 backtest — performance transferred live.
- **`docs/CLI.md`**: full CLI catalog (~55 commands with options),
  organized by workflow, plus the required-services matrix (providers,
  endpoints, env vars, subscription notes) and local component
  requirements. README links it as the primary interface reference.
- **README rewritten** to current four-sport reality; this CHANGELOG seeded.
- **`nfl-grade`**: grades NFL predictions vs finished games and banked
  closing consensus (sides, log-loss, CLV) — read-only, feeds the Week-2
  rehearsal decision.
- **Kalshi soccer hardening**: matched-zero sentinel (loud warning when
  games and markets are both present but nothing matches) and an in-play
  guard keyed on our own kickoff time at capture.
- **GitHub repo live** (this repo): pre-push security scan clean; tarball →
  extract → commit → push workflow established.

## 2026-09-13
- **Kalshi soccer matcher fixed** after an upstream title-format change
  ("A vs B Winner?" → "A wins") silently blinded it for two matchweeks:
  pairing now derived structurally from sibling legs sharing an
  event_ticker, old title parse kept as fallback. Matched 36/36 on return.
- NFL Week-1 game-day file: full model-vs-market comparison (15 priced
  games), Kalshi NFL board matched 28 legs / 14 games two-sided.

## 2026-09-10 → 09-12
- **NFL tier thresholds frozen** pre-results (strong ≥0.68, lean ≥0.57).
- Injury position enrichment: provider's injuries feed carries no
  positions; adapter now joins the team roster by player id (QB status
  live end-to-end).
- MW4 false alarm resolved on the record: two probe-falsified theories;
  file shipped; lesson logged (verify before withholding).

## 2026-09-09
- **NFL phase 2 in one day, gate-first**: backtest gate frozen before any
  model code; v1 Elo (margin-of-victory, per-team season regression)
  passed decisively (0.6361 vs 0.6911 baseline, all bands ≤7pp);
  prediction path + rehearsal-format export built; Week-1 shakedown run
  internally. `sync-odds-nfl` closed the book-capture gap.
- Kalshi sync parameterized (sport + series) — one matcher serves MLB and
  NFL; `sync-kalshi-nfl` added.

## 2026-09-05 → 09-08
- **NFL phase 1**: full data wiring from zero — adapter
  (api-american-football), registry/CLI routing, 3-season backfill
  (989 games), status inference (score-presence beats status-absence),
  spread-sign preservation, season-format hardening.
- **`export-fixtures`**: market-only files for gated competitions
  (matches + odds tables only; `contains_predictions: false`). First live
  consumption by the downstream layer same week.
- EFL Trophy consciously excluded (training-pot contamination); FA Cup
  sync deferred to its trigger rounds; CL ruled data-only behind the cup
  acceptance gate.
- Elo compression diagnosis narrowed: v19/v20 rejections deterministic;
  rating-spread guard added to the soccer gate.

## 2026-08-28 → 09-04
- S17: results export includes draw in top-pick labeling (+ assertion).
- M12: per-match skip warnings aggregated to one summary line.
- Doubleheader guard in the MLB odds fallback (nearest-time + claimed-id).
- EL→UEL competition normalization; pyramid (ELC/EL1/EL2) + CL/UEL
  history backfilled for the cup project.
- Aug-31 quality review: run_shrink_frac=0.35 confirmed on 509 games;
  starter-cap and bullpen-swing ledgers closed clean; M15/M16 tracking
  opened with pre-committed reads.

## 2026-08-11 → 08-27 (from the earlier phase)
- MLB production model v2 shipped behind the daily improve gate; CLV
  lifecycle automated (overnight closer backfill).
- Soccer v18 production through PL matchweeks; thermometer/pick-edge
  ledgers established.
- EFL Cup round-2 dress rehearsal caught the cup-path defects (league
  bonus misfire); S16 doctrine: no cup predictions until acceptance.
- Kalshi integration (MLB + soccer) with refuse-safe matching.
