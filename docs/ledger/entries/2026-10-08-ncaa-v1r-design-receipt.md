**2026-10-08 — RECEIPT (ARCHITECT, addendum 11, item 3, PR A step (a)): ncaa-elo-v1r gate design receipt, a seeded simulation that reads no stored game. Stop condition: OK. The registry entry and spec wait on the architect's check.**
- **Spec (verbatim):** "130 teams in 10 conferences of 13. True strength in Elo points = a conference effect plus a team effect, both normal, in three settings of (conference sd, team sd): (110, 140), (150, 170), (190, 210). Team effects carry to the next season with persistence 0.85, the spread kept. Each season: 3 rounds of random cross-conference pairings, then 8 rounds of random in-conference pairings; home side by coin flip; 6% of games neutral. Margin = normal with mean (home strength - away strength + 55 unless neutral) / 21.5 points and sd 14, rounded, never level. One warm-up season from flat 1500, update only, then the test season scored predict-then-update under D1. 200 seeded seasons per setting. Report per setting: mean scored games, the model's mean slope, and the share of seasons passing #79's band rule as coded and passing D5 (2) and (3)."
- **Stop condition (verbatim):** "If yours contradict mine beyond noise (in the first setting the model passing D5 (2) and (3) in fewer than 85% of seasons, or passing the band rule in more than 60%), stop: write no entry and tell me."
- **Result** (`docs/receipts/ncaa-v1r-design-2026-10-08.md`, from `scripts/ncaa_v1r_design_receipt.py`, MASTER_SEED 20261008):

  | setting | mean scored | mean slope | band rule as coded | D5 (2)&(3) |
  |---|---|---|---|---|
  | (110, 140) | 675 | 1.000 | 26.5% | 87.5% |
  | (150, 170) | 675 | 1.158 | 32.0% | 65.0% |
  | (190, 210) | 675 | 1.337 | 27.5% | 14.5% |

  - Architect's numbers: slope 0.99 / 1.16 / 1.33; band rule 32% / 33% / 29%; D5 (2) and (3) 92% / 60% / 13%.
  - **OK:** in the first setting, D5 (2)&(3) passes in 87.5% of seasons (the floor is 85%) and the band rule in 26.5% (the ceiling is 60%).
- **Used as found, not reimplemented:** NCAAEloV1 (src/models/ncaa_elo.py) with its constants untouched. The band rule is `ncaa_backtest.run_gate(...).crit_bands`: BAND_MIN_N 100, BAND_TOL 0.05, 10pp bands.
- **Interpretations** (each is stated in the receipt):
  - Strength = 1500 + conf effect + team effect.
  - Next season's team effect = 0.85·team + sqrt(1-0.85²)·N(0, team sd). Conference effects stay unchanged.
  - The model's season_regression applies at the season boundary, as NCAAEloV1 does it.
  - Pairings: a cross-conference round is a random perfect matching with no same-conference pair (65 games). An in-conference round pairs each conference of 13 after a shuffle, with one bye (60 games). That gives 675 games per season.
  - A rounded 0 margin takes the sign of the raw draw.
  - Neutral handling under D1 is a thin wrapper: the model's cfg is replaced by home_advantage 0 for the duration of the call on a game labelled neutral.
  - The slope is a Newton maximum-likelihood fit with numpy (no dependency added). A fit that does not converge fails.
- Ledger: this entry plus `changelog.d/PENDING-ncaa-v1r-design-receipt.md`.
