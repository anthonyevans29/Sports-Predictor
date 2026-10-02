**2026-10-02 — NHL v8 FAIL (ARCHITECT); the 2025 test set RETIRED (8 reads); the track stays SUSPENDED; the shadow engine switches to v7 with v1 as reference.**
- **Ruling (verbatim):** "v8 VERDICT STANDS — FAIL 0.6963 (worse than v1; shot info −0.0055); the train-only fit chose k=12 on the grid edge and over-sharpened. Record; NHL 2025 test set RETIRED (8 reads). NHL model track stays SUSPENDED. RULED: the shadow engine switches from v1 to v7 (best measured candidate, 0.6885, labelled "FAILED 0.6885 vs 0.6866") so live CLV accrues on the best read; v1 stays as reference in the grade line. Next NHL candidate declares 2026-27 as test season once >=600 games are played (~December); its training may use 2024+2025."
- **Shadow (`src/walters/nhl_shadow.py`):**
  - Model: `MODEL_VERSION = nhl_elo_v7_xg_margin_no_na`, `GATE_VERDICT = "FAILED 0.6885 vs 0.6866"`. v7 is exactly its frozen declaration: the 2023-24 xG fit without the `na` level, applied to stored shots from the 2024 opener on.
  - Each row carries a `reference` block (`nhl_elo_v1`, "FAILED 0.6909 vs 0.6866 …", v1's probability). The doc carries `reference_model`.
  - `nhl-shadow-grade` and the RESULTS.md section show v1's pick-vs-close beside v7's. Older v1-only rows grade as before.
  - Fit receipt: xG updates vs goal fallbacks (a game without stored shots updates on goals, v1's rule).
- **Chain (stated, it changes what the host runs):** `nhl-daily` gains `nhl-shot-sync --start {yesterday} --end {today}` before `export-nhl-predictions`, so the live season carries xG. It calls api-web.nhle.com (the NHL's free API), never api-sports, so it is listed UNMETERED. Stored games are skipped.
- **Registry:** v8's run record is still on the laptop. It is spliced with its FAIL once `laptop/nhl-v8-run-record` is pushed (NHL 2025 then shows 8 reads). The retirement itself is already enforced in code (#241).
- **Next candidate:** #245 (class:lane): declare on 2026-27 once ≥ 600 games; training may use 2024+2025.
