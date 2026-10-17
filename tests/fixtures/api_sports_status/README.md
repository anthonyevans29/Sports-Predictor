# tests/fixtures/api_sports_status — /games rows in the provider's shape, one per status shape (#493)

ARCHITECT 2026-10-17, addendum 112 item 4: "Tests with the raw payloads from tests/fixtures."

**No kept provider answer exists for these adapters** (law 1, read 2026-10-17): tests/fixtures held kalshi_history,
lineups_history and value_shadow only, and the american-football and hockey tests write their rows in memory. So these
two files are **written, not kept**. Each is one `/games` answer in the shape the adapters read: the envelope
(`get`, `parameters`, `errors`, `results`, `response`) and, per game, the blocks `_parse_games` reads. american
football nests the game (`game.id`, `game.date.timestamp`, `game.status`) and the totals (`scores.home.total`). Hockey
is flat (`id`, an ISO `date` string, `status`) and sends bare-int scores. The ids are synthetic (9101.., 9201..). The
format is `json.dumps(indent=1, sort_keys=True)`, no trailing newline. If the architect wants kept answers, the
operator can capture one season's `/games` on the laptop; Code then trims rows into this folder (the kalshi_history and
lineups_history precedent), and the tests stay as they are.

The shapes are #493's receipt table, plus the edges the rulings name. Both totals are present (american football 20-17,
hockey 3-2) unless the row says otherwise. Addendum 116 item 4 (4): the literal text `"None"` is NO status, the same as
absent. Addendum 116 item 4 (3): no status with both totals is FINISHED only once now >= kickoff + the sport's longest
game (NFL/NCAA 5h, NHL 4h); every fixture game kicks off in 2024, long past that, so the column below is what the parse
reads today. Before the threshold the same rows parse with no status for the game (None: the stored status is left
alone); tests/test_score_presence.py builds those rows in memory, on both sides of the threshold.

| american football | hockey | status as sent | parsed (#493, addendum 116) | before #493 |
| --- | --- | --- | --- | --- |
| 9101 | 9201 | no `status` key | FINISHED | SCHEDULED |
| 9102 | 9202 | `null` | FINISHED | SCHEDULED |
| 9103 | 9203 | `{}` | FINISHED | SCHEDULED |
| 9104 | 9204 | `{"short": null}` | FINISHED | SCHEDULED |
| 9105 | 9205 | `"None"` (the text) | FINISHED: no status, the same as absent | FINISHED |
| 9106 | 9206 | `{"short": "None"}` | FINISHED: no status, the same as absent | FINISHED |
| 9107 | 9207 | `{"short": ""}` | FINISHED | SCHEDULED |
| 9108 | 9208 | no `status` key, a total missing | SCHEDULED: no score, not FINISHED | SCHEDULED |
| 9109 | 9209 | `{"short": "NS"}` | SCHEDULED: a stated status keeps its mapping | SCHEDULED |
| 9110 | 9210 | `{"short": "FT"}` | FINISHED | FINISHED |
| 9111 | — | `{"short": "Q3"}` | LIVE | LIVE |
| — | 9211 | `{"short": "AOT"}` | FINISHED | FINISHED |
| — | 9212 | `{"short": "P2"}` | LIVE | LIVE |
| — | 9213 | no `status` key, scores 0-2 | FINISHED: a shutout side's 0 is a score | SCHEDULED |
| 9112 | 9214 | `{"short": "XYZ"}` | SCHEDULED: unknown (law 4) | SCHEDULED |

The hockey adapter's `status_raw` is the short as sent when a status is stated, and null when none is: null for
9201-9208 and 9213 (no status sent, or the text `"None"`), the code otherwise.
