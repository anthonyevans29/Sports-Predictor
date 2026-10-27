**2026-10-26 — FIXED (#703; ARCHITECT 2026-10-26 17:00 ET: "#703's fixes before the receipt's first run"): the as-of pitcher receipt's live path counts only what it can rebuild. No bar moves.**
- **The findings** (#702's round-2 Codex P2s, verified, carried to #703 under the review stop rule):
  - The P line took a side's path from innings alone, though an ERA the path reads could be incomplete.
  - It took a path from a participant row refreshed after the kickoff, though that row cannot show the pregame identity.
- **The fix** (`scripts/mlb_pitcher_asof_receipt.py`): such sides are counted under their own names, "identity not established pregame" and "not reconstructable", ahead of the path branches. A component's ERA is incomplete when an earned_runs NULL sits in its season sums or, for the bullpen, in a recent window of 10 IP or more, the window the live read blends in. The summary prints the sides whose live path is reconstructed whole.
- **Reading for the architect:** a side with no participant row stays "no pitcher input": that is the live layer's exact path on the stored data.
