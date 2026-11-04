# THE AVAILABILITY RECORD

Spec for lane `availability-record` (ARCHITECT 2026-11-04 13:05 ET, addendum 252). This file covers the schema PR:
the two tables, the migration, the writer, the one read path and the `availability` command. The feeds (item 3) and
the graph projection (item 4) are later PRs and get their own sections when they land.

Code: `src/db/schema.py` (`AvailabilityObservation`, `AvailabilityAssertion`, `AVAILABILITY_TRIGGERS`),
`migrate_availability_record.py`, `src/availability/record.py`, `cli.py availability`. Tests:
`tests/test_availability_record.py`.

---

## 1. The model (addendum 252 item 1)

Verbatim: "THE MODEL, bitemporal and append-only. Two tables, both created by one migration, both written by ingest
commands only, both read mode=ro by everything else".

### `availability_observations`: one row per fetch

Verbatim (item 1(a)): "one row per fetch: sport; source (a fixed vocabulary, item 3); endpoint (the URL or file name,
no secrets); the match_id where the fetch is per game (NULL for a league-wide file), the stored kickoff then;
poll_label where polled on a schedule (the probe's T-120 … T-0); scheduled_at; fetched_at (OUR clock, UTC);
http_status; payload_sha256; payload_path (the raw answer kept on disk under logs/availability/<source>/<date>/, never
under data/, never mirrored); status: complete | partial | empty | failed | missed (Step B's five, the same meanings);
late; error (redacted); rows_asserted. NOTHING UPDATES OR DELETES A ROW. A fetch that raised is a row; a poll whose
time passed with no call is a row."

As built:

| Column | Type | Rule |
|---|---|---|
| `id` | integer | primary key |
| `sport` | `Sport` enum | as `matches.sport` stores it |
| `source` | text(32) | one of the three words below; the insert trigger refuses any other |
| `endpoint` | text(512) | the writer refuses one that carries a secret |
| `match_id` | integer, NULL | ours, as recorded; NULL for a league-wide file; no foreign key (section 6) |
| `kickoff_at` | datetime, NULL | the stored kickoff when fetched (UTC, naive) |
| `poll_label` | text(16), NULL | a polled fetch's label; a polled row also has `scheduled_at` |
| `scheduled_at` | datetime, NULL | the poll's time; a `missed` row always has one |
| `fetched_at` | datetime, NULL | OUR clock, UTC; NULL exactly when the status is `missed` (a CHECK) |
| `http_status` | integer, NULL | |
| `payload_sha256` | text(64), NULL | 64 lower-case hex characters |
| `payload_path` | text(512), NULL | `logs/availability/<source>/<YYYY-MM-DD>/…`, relative, no `..` |
| `status` | text(16) | the five statuses (a CHECK) |
| `late` | boolean | set by the feed |
| `error` | text(256), NULL | redacted, then cut to 256; a `failed` row must carry one |
| `rows_asserted` | integer | the number of assertions written with it; 0 unless complete or partial (a CHECK) |
| `created_at` | datetime | our insert time |

One poll is asked once: a unique index on (`source`, `match_id`, `kickoff_at`, `poll_label`) where all four are
set, Step B's key. A game re-dated by a schedule sync starts a fresh poll set, and the old kickoff's rows stay as
they were.

### `availability_assertions`: one row per fact

Verbatim (item 1(b)): "one row per fact a payload asserted, keyed to its observation: observation_id; sport; kind (a
fixed vocabulary: depth_rank | projected_starter | confirmed_starter | eventual_starter | inactive | injury_status |
plays_for); player_id (ours, NULL with the source's id beside it when unmapped: source_player_id, player_name
verbatim); team_id (ours; NULL + source_team verbatim when unmapped); match_id (NULL for a team-level fact); attrs JSON
(pos_abb, pos_slot, pos_rank, status text, the side); source_stamp (THE SOURCE'S OWN TIME for the fact: nflverse's
`dt`; NULL where the source gives none — the NHL landing gives none); recorded_at (= the observation's fetched_at,
denormalised for the as-of query). No valid_to column and no update: an interval is DERIVED — a fact holds from its
observation to the next observation of the same source that asserts the same (kind, player, team[, match])
differently, or that asserts the slot to someone else."

As built: the columns as ruled. `player_id` and `match_id` are plain integers with no foreign key; `team_id`
declares its reference to `teams.id` (section 6). Two CHECKs: every row names a player (ours, the source's id or the name), and every row names a team (ours or the
source's text). The insert trigger refuses:
- a kind outside the seven;
- an observation that does not exist;
- an observation whose status is not complete or partial;
- a sport other than the observation's;
- a `recorded_at` other than the observation's `fetched_at`.

### Vocabularies

- **Sources (item 3):** `nflverse_depth_charts`, `nhl_api_landing`, `sportsdataio_goalies`. The third word is
  used only if the operator names that feed on 11-13. Each word carries its attribution. Item 3(a): "any output that
  uses the facts (a bulletin, a page) prints "Depth charts: nflverse (CC BY 4.0)"".
- **Statuses:** the five below.
- **Kinds:** the seven above.

The source and kind lists live in the insert triggers, not in a CHECK. A later ruled word therefore needs a migration
that replaces one trigger, not a table rebuild.

## 2. The statuses (Step B's five, the same meanings)

| Status | Meaning (as `schema.CupLineupObservation` defines them, applied to a fetch) | Facts |
|---|---|---|
| `complete` | the answer read in full; every team and match it names mapped | yes (0 or more) |
| `partial` | an answer short of that: a team or a match left unmapped (item 6(c): "partial (a team unmapped)") | yes |
| `empty` | an answer with nothing to assert (an NHL boxscore with no goalie in net) | none |
| `failed` | the call raised; the error is kept, redacted | none |
| `missed` | the poll's time passed with no call made; `fetched_at` NULL | none |

A byte-identical nflverse refetch is `complete` with `rows_asserted` 0 (item 3(a)). The writer refuses assertions on
an `empty`, `failed` or `missed` observation, and so does the insert trigger.

## 3. The two clocks (item 1, ruled; verbatim)

"THE TWO CLOCKS, ruled now so no term argues it later: `recorded_at` is OUR knowledge; `source_stamp` is the source's
claim. A live-era record, a forward confirmation and a closing-time input use `recorded_at` only (what we had on our
disk before the cut-off). A backfilled row (recorded_at later than source_stamp by more than the feed's cadence:
nflverse's season file reaches back to its first load, so our first fetch records weeks of history at once) is usable
ONLY in a backtest labelled "source-stamped" in its run record and its gate text, never in the live-era record; a term
that wants it declares that in its bar. Both clocks are kept on every row so either reading can be audited."

As built:
- **Recorded clock:** an assertion exists from its fetch, so a backfilled row never appears before it.
- **Source clock:** an assertion exists from its `source_stamp`. An assertion with no stamp is not read, and the
  command counts it. It is never filled from `recorded_at` (law 4).
- **Labels:** every fact carries both stamps and its observation. A row is backfilled when `recorded_at` is later
  than `source_stamp` by more than the source's cadence (`record.CADENCE`; nflverse 24 hours, PROPOSED, section 7). A
  source with no ruled cadence reads "backfill unknown", never "not backfilled".
  - **A fact** (the as-of read) is labelled `BACKFILLED` only while every row of its interval is backfilled. nflverse's
    first fetch carries weeks of history, so a fact that never changed (a QB1 since the early charts) opens on a
    backfilled row; the first fresh row that restates it puts it in the live-era record, and the line prints
    `live-era from <that row's recorded_at>` (`Fact.live_since`) instead of the label.
  - **A `--history` line** is one assertion and carries that row's own labels.

The evidence ruling (item 3, verbatim): "our own stamped observation of a source's response, fetched before the
cut-off and kept unaltered (payload sha256, the raw file on disk), IS the pregame evidence. A supplier's assignment
timestamp is welcome as source_stamp and never required."

## 4. The derived interval and the as-of read (items 1(b) and 2)

**`derive(rows, clock)`** reads the assertions in groups. A group is the assertions made together: one observation
with one source stamp. Groups are read in the chosen clock's order. For each group:
- **Restated:** an open interval whose fact (source, kind, player, team, match) the group asserts with the same
  `attrs` stays open. `attrs.dt_raw`, the source's time text, is ignored in that comparison.
- **Closed, "asserted differently":** an open interval whose fact the group asserts, but not with its attrs, closes.
- **Closed, "slot asserted to someone else":** an open interval whose slot the group gives to another player, and
  which the group does not restate, closes. The slots are:
  - `depth_rank`: team, `pos_grp`, `pos_slot`, `pos_rank`;
  - the three starter kinds: match and team;
  - `plays_for`: the player.
  `inactive` and `injury_status` have no slot.
- **Opened:** any other assertion opens an interval at the group's clock.

The player, the team and the game in a fact and a slot are the SOURCE'S OWN identifiers: its player id, else the name
verbatim; its team text; its game id. Ours are used only where the source gave none. Our ids are joined for display
and never used for identity, so a mapping that lands between two fetches (an unmapped `partial` fetch, then a mapped
one; or player-id mapping arriving for every NFL and NHL player) never splits one source fact into two.

- **The game's identity (Codex on #831, round 1):** a per-game fact (`projected_starter`, `confirmed_starter`,
  `eventual_starter`, `inactive`) is keyed on `attrs.source_match_id`, the source's own game id, stored as text. It
  falls back to our `match_id` only where the source has no game id. The writer refuses a per-game fact without it from
  a source in `record.SOURCE_MATCH_IDS`:
  - `nhl_api_landing` (3(b)) sets the NHL gameId, the id in the landing and boxscore URLs.
  - `nflverse_depth_charts` (3(a)) asserts no per-game fact (`depth_rank` only), so it sets none.
  - The paid feed's entry (3(c)) comes with its adapter's specification.

  A starter first recorded while its match is unmapped (`match_id` NULL) and restated after the match maps is
  therefore one fact, and its slot (game, team) closes when another player is given it. No column is added: the id
  lives in `attrs`.
- **The mapping it carries now (Codex on #831, round 1):** an interval's first member keeps its start and its original
  stamps. The mapping it carries now (`record.mapped_now`) takes each of our ids (`player_id`, `team_id`, `match_id`
  with its stored kickoff) from the LATEST member that carries one. A mapping change in either direction therefore
  never hides a fact: unmapped then mapped is found by the new id, and mapped then restated unmapped (a `partial`
  fetch, item 6(c); a poll whose match did not map that time) is still found by the id it had.
  - `--match-id` and `--team` filter on those ids (or the source's team text), in both `as_of` and `history`;
  - a fact line prints those ids;
  - a `--history` line prints its own row's ids as recorded, and adds `mapped now: …` where those ids differ;
  - `derive` reads the latest member's fact and slot keys (the members of one interval share them).

Two rules hold across all of this. The facts of different sources never touch. Assertions made together never close
each other, so two goalies in net are two open intervals.

**`as_of(s, sport, instant, clock, match_id, team, kind)`** runs `derive` over the assertions whose clock is at or
before the instant, and keeps the intervals still open. **`history(...)`** returns the same assertions in the same
order, each with the end of the interval it opened or restated. One function serves both, so the as-of read is the
history cut at the instant (test 6(g)). Item 2, verbatim: "The same function is the one a model term, the bulletin's
teams section and the Cockpit will read; there is no second path."

**Where this reads the ruling's sentence differently** (item 1(b): "'As of T' is one query: the newest observation per
source with the chosen clock <= T, and its assertions"):
- **The two readings agree** for a feed whose every observation restates every fact. The NHL landing polls are such a
  feed.
- **They disagree for nflverse.** That feed asserts only NEW rows (item 3(a)), and a byte-identical fetch asserts
  none, so "the newest observation per source with the chosen clock <= T, and its assertions" would usually be
  empty.
- **They disagree after a gap.** A `missed`, `failed` or `empty` observation asserts nothing, and the literal reading
  would blank the facts after it.

The build therefore reads "as of T" through the derived interval of the same item. This is listed for the
architect's ruling (section 7).

**`post_hoc` (item 5: "a fact recorded after its game is post hoc and labelled so"):** a fact is post hoc when it was
recorded at or after its kickoff. `eventual_starter` is always post hoc (item 3(b): "post hoc, kind-labelled, never a
pregame fact"). The kickoff is, in order (`record.kickoff_of`, Codex on #831, round 1):
1. the observation's stored kickoff (`kickoff_at`, a per-game fetch), as stored at FETCH time;
2. else the kickoff our `matches` table stores (`utc_date`) for the match the interval names now (`mapped_now`). A
   league-wide file stores no kickoff, and its per-game facts are compared to this one. It is read in the same
   read-only session, as stored at READ time: the current kickoff, not the kickoff as of the instant;
3. else the kickoff `matches` stores for the match the row itself names (a call without its interval);
4. else none: a per-game fact reads `kickoff unknown (post hoc undecidable; never read as pregame)` (law 4).

**The label is not frozen as of the instant.** Step 1 keeps the kickoff stored at fetch time; steps 2 and 3 read the
current one. A match re-dated after the instant can therefore change a past as-of read's POST HOC label (the same
`as_of(T)` reads differently before and after the re-date), and a per-game fetch and a league-wide fetch of the same
game, recorded at the same instant, can be labelled against different kickoffs. A model term or a backtest must not
assume the label is reproducible as of T. Using the actual kickoff for "recorded after its game" is the build's
choice; a label frozen at T is listed for the architect (section 7).

## 5. Mapping (law 4; item 1, verbatim)

"Mapping (law 4): a player or team the source names that we cannot map stays NULL with the source's text beside it;
mapping is by the existing tables' source ids (players.gsis_id / espn_id where we hold them, nhl player ids as
nhl_goalies stores them) and never by name alone; an unmapped row is counted on the ingest's console and in a receipt,
never dropped and never guessed."

As built:
- **The writer takes ids, never names.** It is given ids by the feed and maps nothing itself.
- **Unmapped rows are counted.** Its receipt counts the unmapped players, the unmapped teams and the per-game facts
  with no match.
- **Unmapped rows stay visible.** The command prints an unmapped player or team as `UNMAPPED`, with the source's id
  and text.

The read (law 1) shows that today:
- `players` has no `gsis_id` or `espn_id` column, and it holds no NFL or NHL rows.
- `nhl_goalie_appearances.goalie_id` is the NHL's own playerId.
- No team row carries an nflverse or NHL API abbreviation.

So every NFL and NHL `player_id` is NULL until a ruling allows a mapping store (section 7).

## 6. Append-only, enforced

- **Triggers:** SQLite triggers on both tables abort every UPDATE and DELETE, whoever runs it: the app, a migration,
  a sqlite3 shell, `merge-teams` or `dedupe-matches`.
  - They are created with the tables (an `after_create` hook, so `init_db()` and the tests make them too) and again by
    the migration (`CREATE TRIGGER IF NOT EXISTS`).
  - They live in the database file, so a `.backup` carries them.
- **Insert guards:** the insert triggers also refuse a row whose id, or whose poll, is already stored. An
  `INSERT OR REPLACE` deletes the row it conflicts with without firing a delete trigger, so the conflict is refused
  before it happens. An upsert's `DO UPDATE` fires the update trigger.
- **No backdating (item 5):** the assertions' insert guard refuses an assertion on any observation but the newest
  (`NEW.observation_id <> (SELECT MAX(id) FROM availability_observations)`, O(1) on the rowid). Only the observation
  just inserted receives assertions, so nothing is appended to an older fetch and reported as known since it.
  `write_observation` writes the observation and its assertions in one transaction, so its path is unchanged.
- **The module:** `record.write_observation` is the module's only writer, and the module has no update, delete or
  upsert name (test 6(a)).
- **Rebuilds still work:** `init-db --force` (`drop_db`) drops the tables with their triggers, since `DROP TABLE`
  fires no trigger. It also drops the marker `availability_record_migration` by name.
- **Our ids, and the two commands that re-point ids** (read in `src/ingestion/match_dedupe.py` and
  `src/ingestion/team_merge.py`):
  - `match_id` (both tables) and `player_id` are plain integers with no foreign key. `dedupe-matches` re-points only
    the foreign keys to `matches.id`, so it never reaches the record: a record row keeps its match id as recorded
    (the retired twin's id after a dedupe). With a foreign key, its UPDATE would meet the trigger and abort the whole
    run.
  - `team_id` declares its reference to `teams.id`. The app runs with `foreign_keys` off, so it is not enforced.
    `merge-teams` finds every column named `team_id` whether or not it is a foreign key. Without the declaration it
    would list `availability_assertions.team_id` as "a column the command does not know" on every dry run. With it,
    the column is a known reference: a pair whose retired team holds record rows is a candidate, and its apply meets
    the update trigger. That pair is refused with the reason receipted, and the row keeps its team id (test
    `test_merge_teams_refuses_a_pair_whose_retired_team_holds_record_rows`).

## 7. Open for the architect (the schema PR's choices, each reversible before the feeds land)

- **(a) No player ids exist to map by** (section 5). Keep `player_id` NULL with no foreign key until a ruling allows a
  mapping store?
- **(b) The ids and the re-pointing commands** (section 6). `match_id` has no foreign key, so `dedupe-matches`
  leaves record rows on a retired match id. `team_id` declares its reference, so `merge-teams` lists such a pair as a
  candidate, and its apply is refused by the trigger. Is that wanted, or should `merge-teams` refuse such a pair at
  plan time?
- **(c) The as-of reading** is built on the derived interval (section 4), not the literal "newest observation".
- **(d) Snapshot closure.** Should an nflverse `dt` close the facts it does not restate? As built it does not: only
  the fact or its slot closes a fact.
- **(e) NULL `source_stamp` under the source clock.** As built such rows are not read, and the command counts them.
- **(f) The backfill cadence.** nflverse is set to 24 hours (proposed). Under the recorded clock, backfilled facts are
  shown and labelled, not removed.
- **(g) What `partial` means.** The feed decides it, and the writer does not derive it. Unmapped players alone do not
  make a fetch partial, since every NFL and NHL player is unmapped today.
- **(h) Writing in one transaction.** `rows_asserted` is fixed at insert, so the observation and its assertions are
  written together. The insert guard refuses an assertion on any observation but the newest. A raw insert on the
  newest observation, before the next fetch, is not refused: a per-insert count against `rows_asserted` would be
  O(n²) on a full nflverse season file.
- **(i) Where the vocabularies live.** Sources and kinds are in the insert triggers, so changing them needs a migration
  but no table rebuild. Statuses are in a CHECK.
- **(j) The lane's state** is `declared`.
- **(k) The undated steps.** The two paid-adapter steps are conditional on 11-13. The first host reads and the
  timers' enablement are undated blocks and are not lane steps.
- **(l) `--team` and `--db`.** `--team` takes our id (digits) or the source's text. `--db` is a copy behind the
  standing fence.
- **(m) The tag.** The migration must not ride Thursday's tag (item 7). The deploy finds any new top-level
  `migrate_*.py`, so the PR merges after that tag is cut.
- **(n) POST HOC against the current kickoff** (section 4). For a fact without a stored kickoff, the label reads
  `matches.utc_date` as it stands at read time, so a later re-date can change a past as-of read's label. Keep that,
  or freeze the label at T (which needs the kickoff as of T, and the record stores none for a league-wide file)?

## 8. What the lane never does (item 5, verbatim)

"WHAT THE LANE NEVER DOES: no model change; no Desk input; no row written to lineups, match_participants, injuries or
any existing table (the record is its own two tables; the existing stores are untouched); no provider call from a
closing run (the record is read, never fetched, inside a closing); no backdating (a fact recorded after its game is
post hoc and labelled so); no deletion ever; no payload under data/; no secret in an endpoint string; no scraping of a
source whose terms forbid it (nflverse's licence is explicit; the NHL API is the one we already read; a paid feed's
terms come with the decision)."

The schema PR adds two tables and their triggers, and touches no existing table. It makes no provider call, adds no
chain or timer, and sets no model or Desk input. The one changed write path is `drop_db`, which drops the new marker.
