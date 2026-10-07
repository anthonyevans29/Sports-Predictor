# NCAA shadow (ARCHITECT 2026-10-07, addendum 6 item 1)

## The ruling (verbatim)

> "NCAA SHADOW. Once #333's coverage receipt shows 95% on both seasons and ncaa-elo-v1r is declared in the registry with its constants frozen, ship export-ncaa-predictions and ncaa-shadow-grade on the NHL shadow's pattern: engine model_shadow, the gate status on every row ('UNGATED — shadow only' until the verdict, then the verdict), FBS games in the next 36 hours, the market block beside each row, graded on results and on model-vs-close from the last shadow file before kickoff. Never a call, never a venue input, never in the ledger. The shadow starts before the gate run and changes nothing about it: the one run, the verdict and the confirmation cohort stand as declared, and the shadow's live record is not gate evidence. Target: the Saturday 2026-10-10 slate. If the labels are not in by Friday night, say so and Saturday stays market-only."

Build instruction: "Build it now on a branch so it is ready when the labels are. It does not run on a real DB before the coverage receipt is read."

## Commands

- `python cli.py export-ncaa-predictions [--hours 36]` writes `exports/ncaa_shadow_<YYYY-MM-DD_HHMM>.json` and nothing to the DB.
- `python cli.py ncaa-shadow-grade [--days 30]` is read-only. It reads the shadow files on disk.

## Preconditions (code, not a checklist)

`export-ncaa-predictions` refuses with exit 2 and a stated reason, writing nothing, unless both of these hold:

1. **The declaration exists.** The registry holds `ncaa-elo-v1r`, and its entry states `neutral_site_rule` as one of:
   - `home_advantage_at_neutral`
   - `no_home_advantage_at_neutral`

   #333 ruled that "whether v1r applies home advantage at neutral sites is a declaration question". The shadow therefore never chooses; it reads the key. **The declaration PR must carry this key** (named here, for the architect).
2. **Coverage holds.** The CFBD side table covers at least 95% of the gate's stream in BOTH seasons. This is `ncaa_backtest.label_coverage`, the same fact the #333 coverage receipt prints. It is re-checked on every run, so a side table that regresses stops the shadow.

The architect's read of the receipt is what leads to (1). The code never declares anything in the registry.

## Model

- **v1 with its constants untouched.** `NCAAEloConfig()`: k 24, home advantage 55, mov_base 2.2, regression 0.25, default rating 1500. The update math is `NCAAEloV1`'s verbatim.
- **Neutral rule.** Under `no_home_advantage_at_neutral`, a game whose CFBD neutral flag is true prices and updates with home advantage 0.
  - An upcoming game has no side-table row, so its neutral flag is unknown. The listed home's advantage is applied and the row says `neutral: null` (law 4).
- **Walk-forward** over the gate's stream, with #333's labels applied, pre- and postseason excluded and ties skipped: every game before now, then the predictions.

## Rows and file

- **File stamp:** the file is named `ncaa_shadow_*` and stamped `sport: "ncaa"`, `competition: "NCAA"`, `family: "NCAAF"`, `engine: "model_shadow"`, `model_version: "ncaa_elo_v1r"`, `registry_id`, `contains_predictions: false`, `gate_evidence: false`.
- **Every row carries:**
  - the fixtures export's own row (`_fixture_row`: the market block, Kalshi and execution fields);
  - `competition` / `family` / `engine` / `model_version` / `gate_verdict`;
  - a `prediction` block: home/away probability, top pick, both Elos, home advantage applied, neutral.
- **`gate_verdict`** is `UNGATED — shadow only` until the registry records a verdict for `ncaa-elo-v1r`, then that verdict.
- **FBS:** both teams appear in the CFBD side table, whose ingest's default scope is both-FBS completed games. Any other game is skipped and counted (`not_both_fbs`), never priced. *Reading chosen, for the architect:* the side table stores no classification. If it were built with `--division ''` (all classifications), this test would admit non-FBS teams.
- **Never a call:** `desk_policy` and the window card already skip `engine == "model_shadow"`. The shadow is never a venue input and never logged to the ledger.

## Grading (`ncaa-shadow-grade`)

- **The call** is the LAST shadow row written before kickoff.
- **Results:**
  - The result is the CFBD side-table score in our orientation where a row exists, else the matches row.
  - Hit rate, log-loss and Brier of the shadow probability.
  - A tied final is a data defect, skipped and counted.
- **Model-vs-close:**
  - Pick-vs-close against the stored 1X2 book close (the #167/#207 contract; nfl-grade's rule).
  - Value-side-vs-close from the earliest pre-kickoff book snapshot.
  - Unpriced and unanchored games are counted, never guessed.
- **Label:** every grade line says NOT gate evidence.

## Not done here (on purpose)

- **Not on any chain.** It is not on `ncaa-market` or the host. Wiring it in follows the preconditions, by ruling.
- **No Cockpit change.** The Cockpit is the separately published artifact; how it shows NCAA shadow rows is a Cockpit change.
- **Not run on a real DB.** The sample file in the PR comes from a scratch SQLite in the session scratchpad.
