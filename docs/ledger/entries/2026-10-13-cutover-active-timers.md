**2026-10-13 — FINDING + RULED + BUILT (ARCHITECT 2026-10-13 09:01 ET, addendum 57 item 8; #481): the host's timers list is two short; the cutover's preflight reads the active timers. PR #483.**
- **Finding (attributed, the host at 12:41Z, v1.3.0):** `/etc/sports-predictor/timers.enabled` names 13 timers, and `systemctl` shows 15 active. `sp-intl-daily.timer` and `sp-exports-squash.timer` are active and not on the list. The cutover's pause stops the listed timers and checks those, so a timer off the list would stay armed while the database is replaced.
- **Ruling (verbatim):** "The cutover's preflight reads the sp timers that are active on the host. An active timer that is not on the list refuses the preflight, and the refusal names it. The operator corrects the list by hand; the tool never writes it."
- **As built:** `active_sp_timers()` in deploy/hosting/sp_cutover.py, read in `step_preflight` straight after the list. Its refusal names each active timer off the list with the list's path. An unreadable listing refuses. The list is only read. The dry run's scratch list is its own and stays as it is.
- **Not built (the operator's block for the next deploy):**
  - add the two names to the host's list, and `sp-ncaa-schedule.timer` once the next tag has put it on the host;
  - add host.env's `SP_EXPORTS_MIRROR_ROLE` line, before the rehearsal. The preflight already refuses without it (addendum 47 item 7(c)).
- **Closes #481.**
