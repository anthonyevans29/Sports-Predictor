## 2026-10-02 (#153: nhl-v7 ledger annotation; AET/PEN release ratified)
- `docs/registry/experiments.json`: nhl-v7 gains `ledger_count_at_record: 6` and a one-line `ledger_count_note`. Its run record's `prior_read_count: 5` stays as written (ARCHITECT: never rewrite a run record; the live count is the ledger's). `docs/REGISTRY.md` records the doctrine. tests/test_nhl_v6_record.py (+1).
- Ratified, no code change: AET/PEN rows without a stored 90-minute score are unscoreable and released from the intl-elo-v2 cohort, as built in #252.
