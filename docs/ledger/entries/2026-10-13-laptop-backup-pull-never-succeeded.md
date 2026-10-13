**2026-10-13 — FINDING (ARCHITECT 2026-10-13 09:01 ET, addendum 57 item 7; #480): the laptop's nightly pull of the host's backup has never succeeded. H0-14's second layer has produced no file. Nothing built.**
- **Receipt (attributed, the laptop's logs/receipts.jsonl sent 2026-10-13):** 16 lines of kind `pull`, 2026-09-28 to 2026-10-13, each with exit 1.
  - The first says there was no daily backup on the host.
  - The other 15 are ssh failures to the host's tailnet address (exit 255, or a 60-second timeout), each between 02:00Z and 02:32Z.
  - The host's own dailies are there: its receipts show `backup:daily` with integrity ok that morning.
- **Cause, as the architect reads it:** the job runs at 22:00 local. At that hour the laptop is on the VPN for baseball and off the tailnet.
- **What happens now:**
  - Until the season's last baseball game, the pull runs in the operator's host block each morning, from 2026-10-14, when the laptop is on the tailnet. The architect reads its receipt.
  - Before the cutover, the architect rules what a day without a pull does.
- Issue #480 stays open for that ruling.
