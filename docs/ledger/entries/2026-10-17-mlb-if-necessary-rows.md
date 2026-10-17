**2026-10-17 — LIMITATION (accepted, no change): MLB if-necessary postseason rows the provider drops stay SCHEDULED, and the closing watch refuses them (strict --match-ids) (#568).**
- **Ruling (ARCHITECT 2026-10-17 07:05 ET, addendum 103 item 1), verbatim:** "FINDING, limitation class, for an Issue (Code, no change): "MLB if-necessary postseason rows the provider drops stay SCHEDULED forever; the closing watch refuses them correctly (strict --match-ids)". Nothing dedupes MLB; leave it."
- **The case:** MIL at LAD, match 50549, stored "Fri 2026-10-16 9:00pm ET SCHEDULED".
  - Three closing attempts (00:25:59Z, 00:27:03Z, 00:28:07Z) stopped at the strict schedule read: "1 of 1 named game(s) not in the provider's answer". The export was None, exit 1.
  - The provider no longer lists the game. No bet was in play, so 0 bets were missed.
- **Why it stays:** `sync-matches` writes only what the provider lists, so a dropped row keeps its stored status (law 4). `dedupe-matches --orphans` is scoped to the american-football family.
