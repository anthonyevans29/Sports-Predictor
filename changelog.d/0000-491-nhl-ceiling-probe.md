## 2026-11-24 (#0000: 491-nhl-ceiling-probe — the true-starter ceiling probe, built and not run (ARCHITECT 2026-11-24, addendum 491 item 9; GATE-CLASS; lane nhl, #105))
- **src/models/nhl_goalie.py:** `SeasonAppearance` and `HindsightTracker`, with GoalieTracker's interface (`advance_to`, `elo_adjustment`). GoalieTracker and every frozen constant are untouched.
  - **The rate, per goalie per season S** (491 item 5): sum(saves − m × shots) / (sum(shots) + PRIOR_SHOTS).
    - It takes only the appearances linked to the stream's games of S, relief included. No decay; PRIOR_SHOTS 2,000.
    - m and the league shots and goals per team-game are S's own, whole season, with no boot prior.
    - **Leave-one-out** (the declared measure) leaves out the starter's own appearance in the game priced. With `leave_one_out=False` it is item 7's leaked line.
  - **`elo_adjustment` takes the game's match id**, which leave-one-out needs. Without it the call refuses, never pricing a game it cannot place.
- **src/walters/nhl_ceiling.py:** the probe's run, items 3 to 7 in order. It writes nothing; the registry is only read.
  - **The copy:** the shared fence, no sidecar, opened mode=ro + immutable=1. nhl_backtest's own loaders read it unchanged, through a session binding restored on exit. Its path and sha256 print first and are read again after the walks.
  - **Item 3's refusals print no log-loss:**
    - (a) 1,394 scored games and the ids sha256 nhl-v6/v7/v8 recorded, read from 491 and checked against the three entries;
    - (b) both starters known on every scored game, with the warm-up's unknown sides counted;
    - (c) v1 0.6909 and the bar 0.6866, to four places.
  - **`NHLEloHindsight`** is NHLEloV5 exactly, with the game's match id passed to the tracker.
  - **The verdict line** is `beats_margin(leave-one-out, home-rate baseline)`. Beside it: v1, v5 (as-of), leave-one-out less v1, the LEAKED line, and the eight prior reads.
- **cli.py:** `nhl-ceiling-probe --db COPY`. Exit 0 when the console reaches the verdict line, 2 on a refusal. A row in docs/CLI.md.
- **tests/test_491_nhl_ceiling.py** (16, synthetic rows only):
  - the leave-one-out sums leave out exactly the game's own appearance;
  - the league figures;
  - the conversion;
  - the model passes the match id;
  - each refusal of item 3 prints no log-loss;
  - the one run prints items 3 to 7 in order and writes nothing (the copy's bytes, the registry's bytes and its ids folder unchanged);
  - the verdict is the gate's function;
  - the fence;
  - a declaration naming the 2025 set is still refused.

  Nothing was run on real data. No figure of the probe exists. No bar moves: the bar is 0.6866.
