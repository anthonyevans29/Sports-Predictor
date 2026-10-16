# tests/fixtures/lineups_history — the kept /fixtures/lineups answers, trimmed

ARCHITECT 2026-10-16, addendum 83 item 5(c): the captures. Nine answers were kept: CL 2025/26 x3 with full elevens and benches of 6 to 12, EFL 2026/27 x3 full, and FAC x3 empty. The operator pushes them on laptop/lineups-payloads-1016 (block_1016_payloads.txt), and Code trims them into tests/fixtures/lineups_history/ on #538's branch.

They are API-Football `/fixtures/lineups?fixture=<id>` answers of 2026-10-16 13:19Z, as the adapter received them. They hold no key or account. The operator pushed them on laptop/lineups-payloads-1016 (df877e3) under tests/fixtures/lineups_history/raw/. The raw branch is deleted after #538 merges, so the raw files never land on main.

**The trim** keeps whole files only, byte for byte (no trailing newline), each named by its fixture id:
- all six answers with lineups;
- one of the three empty FAC answers, kept deliberately: an empty answer is a real outcome the receipt counts ("none · an empty answer").
- The other two FAC answers (1419291, 1419292) are dropped: they are the same 167 bytes but for the fixture id.

| fixture | competition | sides (provider team id: XI + bench, formation) | sha256 (kept file = fixture) |
| --- | --- | --- | --- |
| 1383422.json | CL 2025/26 | KuPS 1165: 11 + 9, 4-2-3-1 · Milsami Orhei 691: 11 + 6, 4-1-4-1 | e9e0091464ed4304d75020f21ea531c5fc7b4e16e430ebb4d646455a26d55491 |
| 1383423.json | CL 2025/26 | Saburtalo 3502: 11 + 12, 4-3-3 · Malmo FF 375: 11 + 12, 4-4-2 | 05aa094db0d47de521525a842d4c2241e0e906f44f0a7c50f81e8aad5d2c22c8 |
| 1383424.json | CL 2025/26 | FC Noah 3684: 11 + 12, 4-2-3-1 · Buducnost Podgorica 579: 11 + 11, **null** | 1301e5fc131337087e697e5d2233e7f549f4d5d6ddfba532673fc948584d9755 |
| 1554097.json | EFL 2026/27 | Tranmere 1381: 11 + 9, 4-2-3-1 · Rochdale 1339: 11 + 7, 4-2-3-1 | f344111122772e8bdb663c672c7f7c23e5cbb0eb7543d88aff08970a269e6e28 |
| 1554098.json | EFL 2026/27 | York 1828: 11 + 9, **null** · Crawley Town 1362: 11 + 9, **null** | c6ceaca714494a4e4aba99c14fbfd48745075fb14f78373c622d9ee1a1fe426a |
| 1567390.json | EFL 2026/27 | Bristol City 56: 11 + 9, 4-2-3-1 · Walsall 1342: 11 + 9, 5-4-1 | 5a5d47df558d93d77768b98a93cdde3326d77673965e15c877f7f11545ba09a4 |
| 1419290.json | FAC 2025/26 | none: `response` [], `results` 0, `errors` [] | 93cd7347f373b5f90c06f80a54fa7d4ab3c8de16f48e6002ebd0ed9d0c03874a |

**What the kept answers hold that the synthetic payload did not** (read from the files, law 1):
- **formation null:** three sides. The parser stores it as null.
- **`grid` null on every starter of a side that has no formation.** Nothing reads `grid`.
- **`pos` null on some players:** six slots across four sides. The parser stores them as null.
- **benches of 6 to 12.**
- **Every named slot has a name.** No answer holds a nameless slot or a side short of eleven.

**The keys**, as `src/ingestion/lineups_history.KEYS` names them. The tests check them against every kept answer:
- `response`, `errors`;
- each side's `team.id`, `formation`, `startXI`, `substitutes`;
- each slot's `player.name`, `player.pos` and `player.number`.

**What the tests still write themselves**, because no kept answer holds it (no fixture file is edited):
- a nameless slot;
- a side short of eleven;
- a side that maps to neither team;
- the refusals and failures: 401, 403 and 429; a stop at `--max-calls`.
