**2026-10-11 — FINDING (ARCHITECT 2026-10-11 12:31 ET, addendum 40 item 3; #424): an empty answer from the NFL injury feed empties a team's list, and the QB rule cannot see an empty list.**
- In the laptop's 12:55Z file five teams had no injury row and no stamp: Jacksonville, Cincinnati, Las Vegas, Cleveland, Atlanta. The host's whole-league read at 14:00Z held Cleveland 13 names (one a QB, Dillon Gabriel), Cincinnati 8, Atlanta 12, Las Vegas none: the provider had answered empty at the laptop's last read. Jacksonville has answered empty since 10-04 on both machines; Las Vegas in every file either machine holds.
- From the code: `list_injuries` returns [] on an empty response; `_sync_injuries_for_team` deletes the team's rows and writes none; nothing reaches `failed_reads`, so `--strict` passes; nfl_predict.py writes count 0, qb_listed [] and synced_at null; the Desk's QB rule reads qb_listed only.
- What it cost: 15111 CLE at NYJ at 12:55Z read PLAY 1u × 10 with no flag; the host's row an hour later, same model number and books, PLAY 0.5u × 5, "QB-flagged (Dillon Gabriel) → half units". Quarterbacks among unresolved positions (Skylar Thompson, Derek Carr) are counted on the page by B7, not held by qb_listed. The model has no quarterback term (#427): its Baltimore 0.524 is a number for the team with Lamar Jackson.

**2026-10-11 — RULING + BUILT (ARCHITECT 2026-10-11 12:31 ET, addendum 40 item 4; #429): AN EMPTY NFL INJURY LIST IS UNREAD.**
- **Ruling (verbatim):**
  > "An NFL team with no stored injury row is a list we could not read, not a team with nobody hurt. A flag we could
  > not look up is not a flag that is off (addendum 23, A2). Where either team's list is empty, the Desk sizes an
  > NFL PLAY as it sizes a QB-flagged one: half units, and the reason names the team. The page says so on that
  > game's line. The sync names every team whose answer was empty, in its console and in the run's receipt, and
  > --strict does not fail on it: the provider answered."
- **Built:** the Desk rule (count 0 on either side; reason, tag `QB unread half units`, own switch, `desk_meta.nfl_injury_list_empty_rule`; quarantines, PASSes and shadows untouched; POLICY_VERSION v1.1); the sync's `EMPTY-ANSWER` line and the closing receipt's `injury_lists_empty`; the page's `injury list empty: <team>` beside B7.
- **THE HOLD OF 2026-10-11** (the architect's, NFL only): a second `CLOSING_HOLDS` row. An NFL PLAY that is QB-flagged or sized by this rule says "QB: paste to the architect before placing"; where the picked team's starter is out or doubtful it is no bet. The Desk's call and the file do not change. It stands until the model has a quarterback term that passed its gate (#427).
- **Parity:** the golden battery's rows carry no injury count, so the rule never fires there; `desk_parity_verify.py` 14/14 green, and the golden holds with the switch on and off.
- **The probe** for unresolved positions is #432 (nothing built on it until read).
