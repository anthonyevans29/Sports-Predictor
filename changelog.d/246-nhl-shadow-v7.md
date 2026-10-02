## 2026-10-02 (#246: NHL shadow engine switches to v7, v1 as reference)
- `export-nhl-predictions`: the shadow rows are `nhl_elo_v7_xg_margin_no_na` ("FAILED 0.6885 vs 0.6866"), each with a `reference` block carrying `nhl_elo_v1`'s probability; the fit receipt counts xG updates vs goal fallbacks. `nhl-shadow-grade` / RESULTS.md show v1's pick-vs-close beside v7's.
- `nhl-daily`: `nhl-shot-sync` (yesterday..today, the NHL's free API) runs before the shadow export so live games carry xG. tests/test_nhl_shadow.py updated (+1).
