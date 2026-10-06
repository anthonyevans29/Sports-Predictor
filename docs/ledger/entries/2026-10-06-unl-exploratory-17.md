**2026-10-06 — UNL exploratory 17 pinned as excluded by match id (#286 ruling 1); receipt spliced into docs/receipts/.**
- **Ruling (ARCHITECT, verbatim):** "UNL exploratory 17 (ruling 1), by match id, from the 2026-10-05T15:33:57Z capture: 31887, 31888, 31890, 31891, 31892, 31893, 31894, 31895, 31896, 31897, 31898, 31899, 31900, 31901, 31902, 31903, 31904. Pin as excluded; the fresh 30 start with the first qualifying capture after 2026-10-06T14:35:31Z (next UNL window: November). Receipt pushed on laptop/unl-exploratory-17."
- **Pinned:** `unl_ladders.EXPLORATORY_MATCH_IDS` holds exactly these 17 ids (`EXPLORATORY_N` = 17), so `unl-ladder-receipt --skew-test` no longer refuses on ruling 1. The freeze cutoff (`2026-10-06T14:35:31Z`) and the sample rule are unchanged; they already match "the first qualifying capture after" the cutoff.
- **Splice:** `docs/receipts/unl-exploratory-17.md` comes from `laptop/unl-exploratory-17` (9d30b5a, the operator's commit, kept as is). Its header reads "exploratory ids recorded: 0/17" because it ran before this pin.
- **What the receipt shows (read, not assumed):** it lists games kicking off between 2026-10-05T00:00Z and its run time (about 18:37Z on 10-06), so it shows 8 of the 17 ids.
  - Seven are SAMPLE rows on the 15:33:57Z capture: 31887, 31888, 31890–31894.
  - 31895 (FRO @ KAZ, kickoff 10-06T14:00Z) is listed with its last pre-kickoff capture (10-06T13:13Z, 1 book) and is excluded under ruling 2.
  - 31889 (TUR @ ITA) had no Kalshi capture and is not one of the 17.
  - The other 9 ids (31896–31904) kick off after the receipt's run time, so it could not list them. They kick off after the freeze cutoff, which is why pinning them by id matters: their 10-05 capture was inspected.
- **Effect:** #286 stays open until the fresh 30 (November's UNL window).
