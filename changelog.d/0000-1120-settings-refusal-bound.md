## 2026-11-25 (#0000: 1120-settings-refusal-bound — a settings refusal lifts every closing it reaches from a resend's bound (addendum 511 item 2; addendum 530 item 3; money-path))
- **`deploy/hosting/closing.py`.** #1117's `no_chain` held only the one refused `(family, start)`, so a later start that the same settings refusal will refuse could still count as a closing ahead and hold a resend for a tick (the second review round on #1117, P2; #1120).
  - `_refuse` now also records, in the tick's new `no_chain_fams`, what a `refusal_checks` refusal reaches. A family's own refusal (`SP_SKIP_FAMILIES`) adds that family. The machine's settings (the backup folder, the mirror, the role, the card topic) add `"*"`, every family. A bad `--start` adds nothing: it lifts only that start, as before.
  - `send_resend`'s bound (`closing_ahead`) leaves out those families, or every family on `"*"`. With no family left, nothing bounds the resend.
  - `watch()` carries the set from the closings to the slate stage's resends, beside `no_chain`.
- **Unchanged:** the refusals and their exits; the two kinds that still bound a resend (a refusal that clears by itself, and a feed-down MLB closing, 138 item 3(c)); no call, no page text, no bar, no date and no held timer.
- **Test:** `tests/test_closing_runs.py::test_a_settings_refusal_lifts_every_closing_it_reaches_from_the_bound`.
