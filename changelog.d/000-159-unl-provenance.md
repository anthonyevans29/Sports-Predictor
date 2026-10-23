## 2026-10-23 (#000: 159-unl-provenance — ARCHITECT addendum 159 item 2 (#336) and addendum 160 item 3; UNL, before 11-11)
- `scripts/unl_provenance_receipt.py` (src/walters/intl_provenance.py), read-only. It prints the confirmation read's input snapshot per cohort fixture: result, stored and provider-only neutral_v3, the flag's ingest time, and the pre-kickoff shadow file or MISSING.
- For each fixture whose stored flag changed after that file, it prints the replayed probability against the saved one; a material difference goes to the architect.
- `intl-elo-confirm` reports the read both ways: a second line gives the same read on the provider's flags. The verdict and `--record` stay on the stored, corrected flags (`intl_shadow.confirmation_read(flags=...)`).
