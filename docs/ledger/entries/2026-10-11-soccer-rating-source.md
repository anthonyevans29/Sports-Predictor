**2026-10-11 — RULING + BUILT (ARCHITECT 2026-10-10 06:57 ET, addendum 36 item 2; finding #410): a default soccer rating is labelled per side, and a row with one gets no Desk call.**
- **Ruling (verbatim):**
  > 2. RULED: A DEFAULT RATING IS LABELLED, AND IT GETS NO CALL.
  > "Every soccer prediction says, for each side, where its rating came from: the model's table, or the default
  > because the team is not in the table. It is recorded per side as model or default, in the prediction's
  > factor_breakdown and in the export's input_quality. A row with a default on either side gets no Desk call and no
  > value shadow: it is a PASS, and its reason names the team. desk_meta says the rule is on. No probability
  > changes."
  > - The names: home_rating_source and away_rating_source in factor_breakdown; rating_source, home and away, in
  >   input_quality, beside strengths_source. Name in the PR every export that carries a soccer prediction and where
  >   the label lands in each.
  > - It is what ruling B of the cup fix already does for cups (training.py:681-690: an unrated team is market-only).
  >   League games had no such guard.
  > - An export contract change and a Desk rule, so the PR template. Tests: a team outside the table is labelled
  >   default and its row is a PASS with the reason; a row with both sides in the table is unchanged, the Desk
  >   golden included.
  > - Say in the PR how many rows of the laptop's current PL file it changes. I expect none.
- **Built:**
  - `src/walters/training.py` `_generate_predictions_soccer`: `_rating_source(team_id)` = `"model"` if the id is in the production row's `elo_league.ratings`, else `"default"`; written to `factor_breakdown.home_rating_source` / `away_rating_source` on the live path and to the report-only rows. Probabilities are computed exactly as before.
  - `src/walters/export.py` (soccer `input_quality`): `rating_source: {home, away}` beside `strengths_source`, read from the prediction's `factor_breakdown`.
  - `src/walters/window.py` `canonical_models`: the card's `model` block copies `rating_source` (None for rows without it).
  - `src/walters/desk_policy.py`: `DEFAULT_RATING_RULE`, `pass_kind` `default_rating` (added to `NO_CALL_KINDS`: no order, no exec, no value shadow), reason `default rating: <team(s)> not in the model's rating table → no call (default rating, ARCHITECT 2026-10-10)`; `desk_meta.default_rating_rule`; `default_rating_rule_off()`.
- **Every export that carries a soccer prediction, and where the label lands:**
  - `export-predictions --sport soccer` (the PL file, `soccer_PL_*.json`): `input_quality.rating_source`; with `--desk` the row's `desk` block is the PASS.
  - `window-card` (`window_24h.json`): `model.rating_source` on rows whose canonical model row is a soccer prediction; the card's `model.desk` is copied from that row's Desk block, so it reads PASS / `default_rating`.
  - `results-tally` / the soccer results file read graded predictions for the record only; they carry no Desk call and are not changed.
  - Not carrying the production table, so not labelled: `export-soccer-expansion-shadow` (walks its own ratings from the season's matches; never a call) and `export-unl-predictions` (intl-elo-v2, its own engine and ratings).
- **Readings:**
  1. "The model's table" is the production row's LEAGUE rating table (`elo.league.ratings`), the one `EloState.get` falls back from; a cup row is labelled by the same table (ruling B already makes an unrated cup team market-only).
  2. A row without the label (a prediction written before this PR, or another sport) is unchanged: the rule acts on a `default` label only. Predictions are current-only per match and rewritten by every predict run, so the next run labels every scheduled soccer row.
  3. The rule is checked after the started rule (a started row keeps its own reason) and before every pricing step.
- **The laptop's current PL file:** 0 rows change. It was written before the label existed (no `rating_source`), so the rule does not act on it; and the architect's receipt reads PL in 20 of 20 slots there, so its next predict run labels all 20 `model` and still changes none. The host's two files would change: every row there has at least one default side (16 of 20 slots default, the other 4 another league's club, which the table holds under the laptop's ids), so every host PL row becomes PASS / `default_rating` once its predictions are rewritten. The 4 other-league slots read `model`: the label says whether an id is in the table, not whose club it is; addendum 36 item 3 is what makes the host's soccer rows evidence of nothing until the cutover.
- **Receipts:** tests/test_soccer_rating_source.py: a team outside the table is labelled `default` in the report rows, `factor_breakdown` and the export, and its `--desk` row is PASS / `default_rating` naming that team, with no order, exec or value shadow; a row with both sides in the table is unchanged (labelled, unlabelled and rule-off give the same Desk block); the rule off restores the call; `tests/test_desk_golden.py` unchanged and green.
