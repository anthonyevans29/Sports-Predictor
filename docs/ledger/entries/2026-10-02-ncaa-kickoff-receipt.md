**2026-10-02 — FINDING (ARCHITECT): two NCAA fixtures stored +24h; receipt script built; first VENUE calls on file.**
- **Ruling (verbatim):** "NCAA fixtures 10-02: WKU@NMSU and UNT@Tulsa carry utc_date 2026-10-03T00:00/01:00 and read "in-play — never" at 21:21Z. These were Thursday games. Receipt: stored utc_date vs provider vs the in-play test's inputs; fix whichever is wrong (stored kickoff +24h, or rollover logic). Also: first VENUE calls on file today — Pitt@VT 6.4pp (tonight), NJ@NYI 5.1pp (tomorrow)."
- **External check (public schedules):** WKU at New Mexico State was Thu 2026-10-01, 8:00 PM ET (= 2026-10-02T00:00Z). North Texas at Tulsa was Thu 2026-10-01, 8:00 PM CT (= 2026-10-02T01:00Z). The stored values are exactly **+24h**: Friday 8 PM local.
- **Code read:**
  - The api-sports american-football adapter stores the provider's epoch `timestamp` as naive UTC, and every resync overwrites `utc_date`. No ingestion path adds a day.
  - The Desk's in-play test is `utc_ms(row utc_date) <= as_of`. The row's utc and its reason come from the same row of the same export.
  - So a row carrying 2026-10-03T00:00 cannot read "in-play" at an as-of of 2026-10-02T21:21Z. The reason the architect saw must come from a different export or moment than the utc shown.
- **Receipt:** the facts that decide it are the stored row, the provider's raw date block and the exports. All live on the laptop. Run:
  `python scripts/kickoff_receipt.py --find "New Mexico" --find "Tulsa" --date 2026-10-01`
  - If PROVIDER shows the +24h timestamp, the provider is wrong. The fix is a guard on our side, scoped by a ruling.
  - If PROVIDER shows 00:00Z / 01:00Z Oct 2 but STORED shows Oct 3, the store is wrong.
  - The IN-PLAY lines show which export produced "in-play — never", and with what inputs.
- **Recorded:** the first VENUE calls on file today were Pitt@VT 6.4pp (tonight) and NJ@NYI 5.1pp (tomorrow).
