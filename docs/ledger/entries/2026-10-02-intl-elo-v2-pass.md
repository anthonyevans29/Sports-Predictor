**2026-10-02 — intl-elo-v2 PASS recorded (ARCHITECT); run record spliced from the laptop; confirmation window open.**
- **Ruling (verbatim):** "intl-elo-v2 VERDICT — PASS under the frozen gate (0.7889 vs bar 1.0424; gated bands ok; RPS 0.153 vs 0.237). Ratified. Record (prior reads = 2 once v1 is spliced). Grid-edge pick, 13.7% v3 neutral share, and 57% unflagged venues recorded as declared limitations. CONFIRMATION WINDOW: 60 games after 2026-10-02 (UNL matchday 4 this weekend + November's WCQ_EU), scored by the plan; production allowed only on CONFIRMED."
- **Splice receipts:**
  - `laptop/intl-elo-v2-run-record` (4f6922f) was cut before #247. Its declaration fields are identical to main's (only `run` and `status` differ).
  - The ids file has 392 ids, all distinct, matching the recorded sha256. They are the same 392 test ids as intl-elo-v1.
- **Prior reads:** the laptop recorded 0, because its ledger lacked v1's run. Recomputed with `registry.prior_reads` against main's ledger, the count is 1 earlier read (intl-elo-v1). That is the ruling's "= 2" counting this read; the architect also counted v1 itself as "= 1".
- **Verdict time:** the registry stamps the verdict at the recording time (2026-10-02T18:11:47Z). The confirmation cohort counts fixtures kicking off after it.
- **Effect:** status `confirming`. The UNL shadow (#248) unlocks once both are merged; `production_allowed` is False until CONFIRMED.
- **Finding:** `nhl-v7`'s recorded `prior_read_count` is 5, but the earlier runs on its test set are 6 (v1–v6). It was carried from the laptop record when v6 was not yet in the laptop's ledger. It is left as merged, pending a ruling on whether to correct it.
