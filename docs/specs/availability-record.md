# THE AVAILABILITY RECORD

Spec for lane `availability-record` (ARCHITECT 2026-11-04 13:05 ET, addendum 252). Sections 1-8 cover the schema PR:
the two tables, the migration, the writer, the one read path and the `availability` command. Section 9 covers the
first feed, nflverse depth charts (item 3(a); addenda 258 and 259), with the snapshot closure it brings to the read
(section 4). Section 10 covers the second feed, the NHL landing read and its watch (item 3(b); addenda 258 item 2(2),
340 and 341). Section 11 covers the graph projection (item 4; addendum 347 item 5, the pick).

Code: `src/db/schema.py` (`AvailabilityObservation`, `AvailabilityAssertion`, `AVAILABILITY_TRIGGERS`),
`migrate_availability_record.py`, `src/availability/record.py`, `cli.py availability`; the feed:
`src/availability/nflverse.py`, `cli.py availability-nflverse`, the chain `availability-daily`
(`deploy/hosting/chains.py`) and `sp-availability-daily.timer`. Tests: `tests/test_availability_record.py`,
`tests/test_availability_nflverse.py`.

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
  than `source_stamp` by more than the source's cadence (`record.SOURCE_CADENCE_HOURS`; nflverse 24 hours, FROZEN by
  addendum 259 item 2(d)). A source with no ruled cadence reads "backfill unknown", never "not backfilled".
  - **The cadence, RULED (addendum 254 item 2(2)):** "THE BACKFILL CADENCE is per source and is DECLARED WITH THE
    SOURCE'S ADAPTER PR, by my addendum on that PR, as a frozen constant per source word (`SOURCE_CADENCE_HOURS`):
    nflverse 24 h (proposed now, frozen with 3(a)'s PR); a per-game polled source with no source stamp has no cadence
    and its facts read under the recorded clock alone. "backfill unknown", never "not backfilled", where no cadence is
    declared — as built."
  - **FROZEN (ARCHITECT 2026-11-05 10:10 ET, addendum 259 item 2(d)):** "THE CADENCE CONSTANT:
    SOURCE_CADENCE_HOURS["nflverse_depth_charts"] = 24, frozen with the PR (254 item 2(2))." The nflverse feed's PR
    renamed the schema PR's `record.CADENCE` (a `timedelta` per source word, the proposal) to
    `record.SOURCE_CADENCE_HOURS = {"nflverse_depth_charts": 24}`: hours, an int, per source word, read-only at run time
    (a mapping proxy), no alias left. `record.backfilled` reads it as `timedelta(hours=...)`. Its one reader is
    `record.backfilled` (and the feed's receipt count); no other code named the old constant.
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
  - the three starter kinds: match and team, PER KIND;
  - `plays_for`: the player.
  `inactive` and `injury_status` have no slot. Every slot is per source and PER KIND (`record.slot_key` carries the
  kind): a `projected_starter`, a `confirmed_starter` and an `eventual_starter` of one game and team are three slots.
  RULED, addendum 258 item 2(3) (#835 item 3): "THE STARTER SLOT PER KIND: AS DESIGNED, confirmed — a post-hoc
  `eventual_starter` must never close a pregame `projected_starter` (the comparison the NHL lane exists to make). The
  spec's §4 says "per kind" explicitly in the feed PR; nothing else changes."
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

**Snapshot closure: BUILT in the nflverse feed's PR (addendum 254 item 2(6); addendum 259 items 1 and 2(a)-(b)).**
254 item 2(6) ruled it for the feed PR, subject to a read of the real files: "a new `dt` is read as a FULL SNAPSHOT PER
TEAM PRESENT in the load [...] The feed PR VERIFIES this against the real files first". The architect read them
(259 item 1, verbatim in part): "EVERY LOAD IS A FULL 32-TEAM SNAPSHOT [...] A team's rows at one dt are its WHOLE
chart, not its changes [...] PARTIAL GROUPS EXIST AND ARE RARE: 10 of 8,896 groups in 2026 hold fewer than 40 rows
[...] A partial group read as a full snapshot would close most of a team's slots wrongly." Ruled (259 item 2):
"(a) SNAPSHOT CLOSURE, as 254 item 2(6) proposed and the data confirms: a load (one dt) is a full snapshot for EVERY
team present in it; a team's facts not restated at that dt CLOSE at that observation; a team absent from a load (none
observed in either file, but law 4) keeps its facts open. (b) THE PARTIAL-GROUP GUARD: a (dt, team) group with fewer
than HALF the rows of that team's previous complete group is `partial` FOR THAT TEAM — its rows are asserted (a fact
seen is a fact), it CLOSES NOTHING, the prior facts stay open, and the receipt counts it ("partial team groups: N,
closing nothing"). The first group ever seen for a team is complete by definition."

As built (`record.derive`, `record.snapshot_load`, `record.guard_load`, `record.partial_group`):
- **Which groups are loads.** A per-source rule: `record.SNAPSHOT_SOURCES = {"nflverse_depth_charts": "depth_rank"}`.
  A group (one observation, one source stamp) is a LOAD when every row is that source and kind AND its observation
  keeps a payload hash (`payload_sha256`): the adapter's rows, from a fetched or hand-carried release file whose bytes
  are on disk. **RULED (ARCHITECT 2026-11-05 11:55 ET, addendum 262 item 1, verbatim in part):** "for a SNAPSHOT
  source [...] the WRITER REQUIRES `payload_sha256` on every observation that asserts a row — the hash is the load's
  identity (252 item 1(a)) and "has a hash" then means exactly "is a real load". An observation of a snapshot source
  with rows and no hash is REFUSED by the insert guard with its reason; `failed` and `missed` observations carry no
  payload and assert nothing, as before. #831's one-row test histories that exercise nflverse semantics are rewritten
  as small full charts; the generic record tests on synthetic non-snapshot sources keep their shape (the rule is per
  source, not global). The snapshot gate as built (read as a snapshot only with a hash) stays and becomes redundant by
  construction, which is the right kind of redundancy." Built: the insert guard is a trigger of its own,
  `trg_availability_assertions_snapshot_hash_guard` (section 6), which refuses an assertion whose observation is of a
  snapshot source and keeps no `payload_sha256`, with the reason, a raw INSERT included; `write_observation` refuses
  the same before any session opens ("the snapshot source nflverse_depth_charts asserts N row(s) and keeps no
  payload_sha256 [...] nothing written"). And "never keyed by name" (262 item 5) holds at the writer: an assertion of a
  snapshot source with no `source_player_id` is refused with its reason (section 9). The record's tests
  write each nflverse history as small full charts (the named rows, two filler rows of the team, a second team's
  three rows), each load carrying a hash. No other source is read this way.
- **The closure.** For each team present in a load, every open `depth_rank` fact of that source and team that the
  load does not restate closes at the load. The generic rules are tried first and keep their reasons ("asserted
  differently", "slot asserted to someone else"); a fact neither of them closes is closed "not restated in its team's
  snapshot", `closed_by` the team's first row in the load. A team absent from the load: nothing of it closes.
- **The partial guard.** The rows of each team in a load are counted. A team whose count is below half its previous
  COMPLETE group's (`rows < previous * 0.5`, `PARTIAL_GROUP_FRACTION`; exactly half is complete) is partial at that
  load: its rows restate or open as any rows do, and NO rule closes that team's facts at that load (not the snapshot,
  not "asserted differently", not the slot), so the prior facts stay open beside any new ones. The team's previous
  complete group stays the one before. The first group ever seen for a team is complete. The adapter's receipt counts
  the same groups with the same function (`guard_load`), reading the previous complete groups from the store's loads.
  A team group that lost a row the adapter refused (a blank `espn_id`, addendum 262 item 5; section 9) is partial
  the same way whatever its size: its asserted rows carry `attrs.rows_refused` (the count; `record.ROWS_REFUSED_ATTR`,
  in `VOLATILE_ATTRS`, so it never makes a restatement read "asserted differently"), `guard_load` takes those teams as
  partial (`refused`), and they never become a previous complete group.
- **"Close at that load" under each clock.** A fact closes at the load's group clock, the clock its interval opens on:
  - **source clock:** the load's `dt`. The facts in force at T are the last load at or before T, as the file says;
  - **recorded clock:** the observation's `recorded_at`. One fetch carries many loads (the first fetch carries the
    whole season), all recorded at one instant; `_groups` reads them in `dt` order, so an earlier load's intervals open
    and close at the same `recorded_at` (empty intervals: never in force under this clock, still listed by
    `--history`), and the facts in force from that `recorded_at` are the fetch's LAST load's. Nothing a fetch carries is
    in force before it was on our disk (item 1's recorded clock).
  The two clocks read the same sequence of loads in the same order, since the adapter asserts only rows newer than
  every stamp held (section 9), so each clock's as-of read is the cut of its own derivation (test 6(g)'s pin, on loads:
  `test_both_clocks_read_the_loads_and_as_of_is_the_history_cut`).

**`as_of(s, sport, instant, clock, match_id, team, kind)`** runs `derive` over the assertions whose clock is at or
before the instant, and keeps the intervals still open. **`history(...)`** returns the same assertions in the same
order, each with the end of the interval it opened or restated. One function serves both, so the as-of read is the
history cut at the instant (test 6(g)). Item 2, verbatim: "The same function is the one a model term, the bulletin's
teams section and the Cockpit will read; there is no second path."

**The bounded read (Codex on #841, round 1; `record._partitions`, `_key_filter`, `_mixed_groups`, `_derive`).** The
first build loaded every assertion of the sport (`load_rows`), cut it at the instant in Python and derived once: 57.9 s
and 2.2 GB on 750,000 synthetic rows. `as_of` and `history` now read only what their answer can depend on, and their
answer is the full derivation's, interval by interval and in the same order. What is bounded and what is not: a
`--team` or `--match-id` read is bounded by its key (its partitions' rows); an UNFILTERED read still reads every row
up to the instant once (its time is linear in that history), and since addendum 262 item 4 holds one partition's rows
and a Summary per open interval, never every restatement (the memory, index and scan lines below):
- **The clock, in SQL.** The chosen clock's column (`recorded_at`, or `source_stamp` with NULL excluded) is bounded
  before the day after the instant's date. That is a superset of "at or before the instant": the stored text begins
  with its ISO date, and the writer stores every stamp in SQLAlchemy's one form. On the last representable date
  (9999-12-31, no day after it) the bound is the NULL test alone, still a superset (the first
  bound raised OverflowError there). The exact cut (`clock <= instant`) is still applied to each row in Python. A group (one observation, one source stamp) shares both clocks, so the cut
  never splits one. A backfilled row is cut by the chosen clock like any row (under the recorded clock from its fetch,
  under the source clock from its stamp); BACKFILLED stays a label read over the interval, never a filter.
- **The partition.** Every rule of `derive` compares two rows of one source and kind only through the fact key (which
  holds the team and the player), the slot key (the team, for every kind but `plays_for`; the player, for `plays_for`)
  and, for a snapshot load, the team (its closure and its partial guard). So the intervals of a (source, kind, team),
  or a (source, kind, player) for `plays_for`, depend on that partition's rows alone, and on one fact about each group:
  whether it is a load. `snapshot_load` reads the whole group, so a group of a snapshot source whose rows in the read
  include another kind is named "not a load" to every partition (`_mixed_groups`; a read of one kind holds none). The
  SELECT is ordered by the partition's columns and read in batches; each partition is derived as it completes, and
  `as_of` keeps only its open intervals. A partition met twice (a broken order) is refused, never derived in halves.
- **The key, in SQL.** A `--team` or `--match-id` read loads, whole, only the partitions holding a row that names that
  team (the source's text, or our id) or that match. An interval the filter keeps names it on a member (`mapped_now`
  takes each id from the latest member that carries one), so its partition is loaded.
- **Pinned** by `tests/test_availability_record.py::test_the_bounded_read_equals_the_full_materialisation_on_randomized_histories`
  (four seeds, both clocks, at instants that include 9999-12-31 and `datetime.max`, with and without each key, per
  kind: every fact (its interval's first and last rows, start, end, closing row, reason and restated count, the
  mapping it carries now, every label and its printed line) and every history line (with every member of its
  interval) equal HEAD's full materialisation, whose labels are read from the members, on histories with snapshot
  loads, partial groups, a mixed group, mapping changes (our team, player and match ids moving between the members of
  one fact), starters, `plays_for` and rows with no source stamp),
  `test_262_4_as_ofs_summary_carries_the_latest_ids_its_members_carry` (one fact restated four times while its team,
  player and match ids move, the match re-mapped to one with a later kickoff) and
  `test_a_team_read_loads_that_teams_rows_not_the_records_whole_history` (an instrumented reader: 480 rows fetched
  before, at most the team's 30 plus the key's lookup after).
- **Memory: what `as_of` keeps per open interval (ARCHITECT 2026-11-05 11:55 ET, addendum 262 item 4; Codex on #841,
  round 1, P1).** Round 1's unfiltered `as_of` held every open interval with all its members, so every restatement of
  every fact still in force (on a daily snapshot feed whose depth facts mostly stand, nearly every row up to the
  instant): 202 MB at 746,140 synthetic rows, 47 MB before the read. `as_of` now derives with `keep_members=False`:
  each interval keeps its first and last rows, its restated count and a `record.Summary` (`members` is None), the
  labels' running values kept as each member is added in derivation order: whether any member is fresh and whether
  every member is backfilled (`interval_backfilled`), the earliest recorded_at of a fresh member (`live_since`), and
  the latest player_id, team_id and match_id (with that member's stored kickoff) a member carries (`mapped_now`, which
  `_keep`, `kickoff_of`, `post_hoc` and `fact_line` read). The derivation's rules read first, last and the keys fixed
  at opening, never the members, so the intervals are the same. `history` and `derive` keep every member (a history
  line names the interval each row opened or restated). The callers, enumerated before it was built: `as_of` is called
  by `cli.py` (`availability`: `f.interval.first.source` and `fact_line`) and by tests only; `Interval.members` is read
  by `record.py` itself (the labels, `_derive`, `history`) and by tests only (the equivalence test's reference and its
  history comparison); nothing in src, deploy, scripts or tools reads either. So the unfiltered read holds one
  partition's rows (one team's facts of one kind) and the open intervals' first and last rows: 86 MB on the same
  store, 72 MB at a mid-season instant (the PR body's table).
- **The index (ARCHITECT 2026-11-05 11:55 ET, addendum 262 item 4, verbatim: "AN INDEX IS ALLOWED in this PR if the
  query needs one: it joins #831's migration (additive, idempotent, the same marker file or its own, named in the PR
  body) and rides the SAME next tag — one migration ritual, not two. Named, never quiet.").** Round 1 found no (sport,
  recorded_at) index, so a recorded-clock read walked ALL the sport's rows through `ix_avail_asr_sport_stamp` (sport)
  and filtered the time cut on each. `ix_avail_asr_sport_recorded` (sport, recorded_at) on `availability_assertions`
  is declared on the mapped model (`init_db` creates it) and created by `migrate_availability_record.py`, the same
  script and the same marker: `CREATE INDEX IF NOT EXISTS ix_avail_asr_sport_recorded ON availability_assertions
  (sport, recorded_at)`, with every other index the two models declare, on every run (a store the script migrated
  before the index gains it on a rerun; the marker is kept as written; the receipt says "+ Created index" or "· Kept
  index" by name and fails on a declared index missing after the run). Every SELECT of the recorded-clock read (the
  mixed-group probe, the key lookup, the partition read) is then `SEARCH availability_assertions USING INDEX
  ix_avail_asr_sport_recorded (sport=? AND recorded_at<?)`; the source clock keeps `ix_avail_asr_sport_stamp (sport=?
  AND source_stamp>? AND source_stamp<?)`. The ordering is still a temporary B-tree. On the 746,140-row store the
  index took about a second to build. The migration is not in v1.6.4 (that tag's one migration was
  `migrate_ncaa_cfbd_pregame.py`): the next tag that carries #831 and this PR runs it once, as a new migration.
- `unread_under_source_clock` is a `COUNT` in SQL.

**Where this reads the ruling's sentence differently** (item 1(b): "'As of T' is one query: the newest observation per
source with the chosen clock <= T, and its assertions"):
- **The two readings agree** for a feed whose every observation restates every fact. The NHL landing polls are such a
  feed.
- **They disagree for nflverse.** That feed asserts only NEW rows (item 3(a)), and a byte-identical fetch asserts
  none, so "the newest observation per source with the chosen clock <= T, and its assertions" would usually be
  empty.
- **They disagree after a gap.** A `missed`, `failed` or `empty` observation asserts nothing, and the literal reading
  would blank the facts after it.

The build therefore reads "as of T" through the derived interval of the same item.

**RULED (addendum 254 item 2(1)), and the ruling's sentence CORRECTED:** "THE AS-OF READ is the cut of the derived
interval at the instant — RULED; 252 item 1(b)'s literal "the newest observation per source … and its assertions" is
CORRECTED by this item (it is empty after a byte-identical fetch or a missed day, which is exactly wrong for a feed
that asserts only new rows). The interval is the reading; `test_6g_as_of_is_the_history_cut_at_the_instant` is its
pin." So 252 item 1(b)'s literal "as of T" sentence is superseded: the as-of read is the cut of the derived interval
at the instant, and `tests/test_availability_record.py::test_6g_as_of_is_the_history_cut_at_the_instant` pins it.

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

So every NFL and NHL `player_id` is NULL. RULED (addendum 254 item 2(3)): "accepted as law 4 requires: every NFL and
NHL player NULL with the source's id and name beside it, counted on the receipt; a mapping step is its own later PR
when a players table for the sport exists, and it maps by id, never by name."

## 6. Append-only, enforced

- **Triggers:** SQLite triggers on both tables abort every UPDATE and DELETE, whoever runs it: the app, a migration,
  a sqlite3 shell, `merge-teams` or `dedupe-matches`.
  - They are created with the tables (an `after_create` hook, so `init_db()` and the tests make them too) and again by
    the migration (`CREATE TRIGGER IF NOT EXISTS`).
  - They live in the database file, so a `.backup` carries them.
- **Insert guards:** the insert triggers also refuse a row whose id, or whose poll, is already stored. An
  `INSERT OR REPLACE` deletes the row it conflicts with without firing a delete trigger, so the conflict is refused
  before it happens. An upsert's `DO UPDATE` fires the update trigger.
- **The snapshot hash guard (ARCHITECT 2026-11-05 11:55 ET, addendum 262 item 1: "An observation of a snapshot
  source with rows and no hash is REFUSED by the insert guard with its reason"):** the trigger
  `trg_availability_assertions_snapshot_hash_guard` refuses an assertion whose observation's source is in
  `SNAPSHOT_SOURCES` (declared in `schema.AVAILABILITY_SNAPSHOT_SOURCES`) and whose `payload_sha256` IS NULL. A trigger
  of its own: `CREATE TRIGGER IF NOT EXISTS` never changes the assertions' insert guard on a store #831 already
  migrated, so `migrate_availability_record.py` creates this one there on its next run ("+ Created trigger", then
  "· Kept trigger"), additive and idempotent, the same ritual and the same tag as the recorded-clock index (262 item 4).
  Seven triggers in all.
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
  - **`dedupe-matches`' record line (addendum 254 item 2(4)):** "our match_id is read as recorded; dedupe-matches
    prints one receipt line, "record rows on retired match ids: N", and rewrites nothing." N counts the rows of both
    tables whose `match_id` is an id the run retires: the newer row of each pair it merges, in the pair path and in
    `--orphans` (a relink or an orphan mark retires no id). On `--apply` a merge that `merge()` refuses (both rows
    hold an entry in a unique table) retires nothing and is left out of N. A dry run counts the newer row of every
    planned merge: a refusal at apply is not known on a dry run, so the dry run's N can exceed the apply's
    (`match_dedupe.record_rows_on`, a SELECT COUNT only). The line has three forms, never a 0 it did not count
    (law 4):
    - `record rows on retired match ids: N`;
    - `record rows on retired match ids: n/a (availability tables absent)`: a database without the record's tables
      (before the migration);
    - `record rows on retired match ids: n/a (the live DB's tables could not be read)`: the database's table list
      cannot be inspected.

    Tests: `test_dedupe_matches_prints_the_record_rows_on_the_retired_ids`,
    `test_dedupe_matches_labels_the_record_line_n_a_where_the_record_tables_are_absent`,
    `test_dedupe_matches_orphans_counts_the_record_rows_on_the_merge_it_retires` (dry run and apply each),
    `test_dedupe_matches_record_rows_are_byte_identical_after_an_apply`,
    `test_dedupe_matches_record_line_leaves_a_refused_merge_out_of_the_apply_count` and
    `test_dedupe_matches_labels_the_record_line_n_a_where_the_tables_cannot_be_read` (dry run and apply).
  - `team_id` declares its reference to `teams.id`. The app runs with `foreign_keys` off, so it is not enforced.
    `merge-teams` finds every column named `team_id` whether or not it is a foreign key. Without the declaration it
    would list `availability_assertions.team_id` as "a column the command does not know" on every dry run. With it,
    the column is a known reference: a pair whose retired team holds record rows is a candidate, and its apply meets
    the update trigger. That pair is refused with the reason receipted, and the row keeps its team id (test
    `test_merge_teams_refuses_a_pair_whose_retired_team_holds_record_rows`).

## 7. For the architect: RULED by addendum 254 item 2 (ARCHITECT 2026-11-04 15:45 ET), except where marked

Addendum 254 item 2 rules the ten questions of the PR body ("#831's ten questions RULED"). Each item below names the
part that rules it, with a one-line quote. An item the ten do not cover is marked NOT RULED and stands as built.

- **(a) No player ids exist to map by** (section 5). Keep `player_id` NULL with no foreign key until a ruling allows a
  mapping store? **RULED, 254 item 2(3):** "accepted as law 4 requires [...] a mapping step is its own later PR when a
  players table for the sport exists, and it maps by id, never by name."
- **(b) The ids and the re-pointing commands** (section 6). `match_id` has no foreign key, so `dedupe-matches`
  leaves record rows on a retired match id. `team_id` declares its reference, so `merge-teams` lists such a pair as a
  candidate, and its apply is refused by the trigger. Is that wanted, or should `merge-teams` refuse such a pair at
  plan time? **RULED, 254 item 2(4):** "`match_id` WITHOUT A FOREIGN KEY — accepted [...] dedupe-matches prints one
  receipt line, "record rows on retired match ids: N", and rewrites nothing"; and "`team_id`'s reference to teams.id
  with merge-teams REFUSED by the update trigger when the retired team holds record rows — accepted; such a merge comes
  to me". Built: the record line (section 6).
- **(c) The as-of reading** is built on the derived interval (section 4), not the literal "newest observation".
  **RULED, 254 item 2(1):** "THE AS-OF READ is the cut of the derived interval at the instant — RULED; 252 item
  1(b)'s literal [...] is CORRECTED by this item" (section 4).
- **(d) Snapshot closure.** Should an nflverse `dt` close the facts it does not restate? As built it does not: only
  the fact or its slot closes a fact. **RULED FOR THE FEED PR, 254 item 2(6):** "a new `dt` is read as a FULL
  SNAPSHOT PER TEAM PRESENT in the load [...] The feed PR VERIFIES this against the real files first" (section 4).
  Not built here. **Verified by the architect's read and RULED with its guard, 259 items 1 and 2(a)-(b); BUILT in the
  nflverse feed's PR (section 4).**
- **(e) NULL `source_stamp` under the source clock.** As built such rows are not read, and the command counts them.
  **NOT RULED:** not among the PR body's ten (its question 2 asked only about the cadence); stands as built. It is
  consistent with 254 item 2(2)'s "a per-game polled source with no source stamp has no cadence and its facts read
  under the recorded clock alone", which the builder reads as covering it; that reading is the architect's to confirm.
- **(f) The backfill cadence.** nflverse is set to 24 hours (proposed). Under the recorded clock, backfilled facts are
  shown and labelled, not removed. **RULED, 254 item 2(2):** "nflverse 24 h (proposed now, frozen with 3(a)'s PR)";
  "backfill unknown" where no cadence is declared, "as built" (section 3). **FROZEN, 259 item 2(d)**, as
  `record.SOURCE_CADENCE_HOURS` (section 3).
- **(g) What `partial` means.** The feed decides it, and the writer does not derive it. Unmapped players alone do not
  make a fetch partial, since every NFL and NHL player is unmapped today. **RULED, 254 item 2(7):** "`partial` = a
  team or match left unmapped; unmapped players counted but not status-changing — accepted".
- **(h) Writing in one transaction.** `rows_asserted` is fixed at insert, so the observation and its assertions are
  written together. The insert guard refuses an assertion on any observation but the newest. A raw insert on the
  newest observation, before the next fetch, is not refused: a per-insert count against `rows_asserted` would be
  O(n²) on a full nflverse season file. **NOT RULED:** not among the PR body's ten; stands as built.
- **(i) Where the vocabularies live.** Sources and kinds are in the insert triggers, so changing them needs a migration
  but no table rebuild. Statuses are in a CHECK. **NOT RULED:** not among the PR body's ten; stands as built.
- **(j) The lane's state** is `declared`. **RULED, 254 item 2(5):** "THE LANE'S STATE `declared`, its Issue #830, its
  board placement immediately below the model lanes — accepted."
- **(k) The undated steps.** The two paid-adapter steps are conditional on 11-13. The first host reads and the
  timers' enablement are undated blocks and are not lane steps. **RULED, 254 item 2(8):** "the paid adapter's two steps
  carry `due: null` with their condition in the step text until 11-13; on "none" they are marked "not needed
  (operator: none, 11-13)" by their moved line in the next roadmap PR. The engine pick, the first host reads and the
  timers' enablement are my blocks, not steps — as built." NOT YET IN `docs/roadmap.json`; the two steps still carry
  11-14 and 11-21, and this PR does not change `src/roadmap.py`. Both halves of the ruling meet the roadmap code:
  - `validate()` (`src/roadmap.py:195-197`; "validate() is the ruled validation", addendum 59 item 5(e)) refuses a
    `due` that is not a real date: "due None is not a real date (YYYY-MM-DD)".
  - `overdue_steps()` (`src/roadmap.py:299`) compares `real_date(st["due"]) < today`, a TypeError on a null due.
  - The later moved line that marks a step "not needed" cannot be written either. The moved-line check
    (`src/roadmap.py:230-237`) enforces addendum 61 item 4 (quoted at `src/roadmap.py:41-44`): "In a moved line now
    may be null where which is earliest_live; was is always a real date. A step's due is never cleared". A step's
    moved line from a null due has no real `was`, and "not needed" is not a real `now`.

  One ruling is needed for both: the shape of a step with `due: null`, and how a "not needed" step is recorded.
- **(l) `--team` and `--db`.** `--team` takes our id (digits) or the source's text. `--db` is a copy behind the
  standing fence. **`--db` RULED, 254 item 2(9):** "`--db` STAYS (198 item 6(ii))." `--team`'s two forms: not among
  the ten (the PR body asked about `--db` only); as built.
- **(m) The tag.** The migration must not ride Thursday's tag (item 7). The deploy finds any new top-level
  `migrate_*.py`, so the PR merges after that tag is cut. **RULED, 254 item 2(10):** "#831 merges THURSDAY, by my
  block, AFTER v1.6.4 is tagged and its deploy console reads exit 0 — so Thursday's tag carries exactly one migration
  (migrate_ncaa_cfbd_pregame.py) and #831's migration rides the next tag with its own compare morning."
- **(n) POST HOC against the current kickoff** (section 4). For a fact without a stored kickoff, the label reads
  `matches.utc_date` as it stands at read time, so a later re-date can change a past as-of read's label. Keep that,
  or freeze the label at T (which needs the kickoff as of T, and the record stores none for a league-wide file)?
  **OPEN:** this is the PR body's question 11, not among 254's ten. 254 item 2(10) says only that "The round-1 P2
  fixes (post hoc labelling by the match's kickoff; [...]) are round 1 as Code has them"; it does not answer keep
  versus freeze. As built (the current kickoff) until ruled.

## 8. What the lane never does (item 5, verbatim)

"WHAT THE LANE NEVER DOES: no model change; no Desk input; no row written to lineups, match_participants, injuries or
any existing table (the record is its own two tables; the existing stores are untouched); no provider call from a
closing run (the record is read, never fetched, inside a closing); no backdating (a fact recorded after its game is
post hoc and labelled so); no deletion ever; no payload under data/; no secret in an endpoint string; no scraping of a
source whose terms forbid it (nflverse's licence is explicit; the NHL API is the one we already read; a paid feed's
terms come with the decision)."

The schema PR adds two tables and their triggers, and touches no existing table. It makes no provider call, adds no
chain or timer, and sets no model or Desk input. The one changed write path is `drop_db`, which drops the new marker.

## 9. The nflverse depth-chart feed (item 3(a); addenda 258 and 259)

Verbatim (252 item 3(a), in part): "nflverse DEPTH CHARTS (source `nflverse_depth_charts`): the release file for the
season (github.com/nflverse/nflverse-data, release tag depth_charts, the 2025+ format: dt, team, player_name, espn_id,
gsis_id, pos_grp_id, pos_grp, pos_id, pos_name, pos_abb, pos_slot, pos_rank — the dictionary as published; the
2023–2024 weekly files are a DIFFERENT shape and are NOT ingested by this feed [...]). One fetch a day on the host
after nflverse's ~07:00 UTC load (a new chain `availability-daily`, timer 08:45 UTC, inside no other chain; UNMETERED;
failure receipted and paged as a sync-step failure, stopping nothing). Each fetch is one observation; its NEW rows (dt
later than the newest source_stamp we hold for the source) become assertions of kind depth_rank (attrs: pos_grp,
pos_abb, pos_slot, pos_rank), one per player-slot; the fetch's payload sha256 is kept, and a fetch whose file is
byte-identical to the last is a `complete` observation with rows_asserted 0. Licence CC BY 4.0 [...] A QB1 from this
feed is a DAILY RANK, not a game-day confirmation (the report's own limit): kind depth_rank says so; nothing here writes
projected_starter."

Code: `src/availability/nflverse.py`; `cli.py availability-nflverse`. Tests: `tests/test_availability_nflverse.py`,
on SYNTHETIC rows only (labelled so in the file); the real-row tests are `tests/test_availability_nflverse_real.py`
(addendum 284 item 1(a)): the two whole release files, read from the directory `NFLVERSE_REAL_DIR` names (never
committed, never downloaded by a test, skipped when unset), through the adapter; the excerpt of 259 item 3 was never
committed and is retired.

### The file (law 1)

- `csv.DictReader`, every column by its NAME. The header must hold exactly `nflverse.COLUMNS`, the twelve of 259 item 1
  ("COLUMNS, both files, exactly the dictionary's twelve"), each once; their order is not read. Anything else is
  REFUSED with the missing, unexpected and repeated names; a header holding the 2023–2024 weekly dictionary's names
  (`season`, `week`, `club_code`, `depth_team`, ...) is named "the 2023-2024 weekly shape, which this feed does NOT
  ingest" first.
- Every row: `dt` an ISO-8601 instant with `Z` or an offset (a time with no zone is never assumed UTC), `team`
  non-empty, and one of `player_name`, `gsis_id`, `espn_id` non-empty; else the whole file is refused naming the line.
- `--season` below 2025 is refused with the same reason (259 item 2(c): "2023–2024 are not ingested (the other shape;
  refused by the column check with its reason)").

### A row, one assertion

| Column | Value |
|---|---|
| `kind` | `depth_rank` (never `projected_starter`: 252 item 3(a)) |
| `source_stamp` | `dt`, UTC |
| `source_player_id` | `espn_id`, ONLY (the key: below); a row with a blank `espn_id` is never asserted (262 item 5) |
| `player_id` | NULL: no NFL player table to map by (254 item 2(3)); every row counted unmapped |
| `player_name` | verbatim |
| `source_team` | `team` verbatim |
| `team_id` | ours by the existing NFL team mapping (below); NULL when unmapped |
| `match_id` | NULL (a team-level fact) |
| `attrs` | `pos_grp`, `pos_abb`, `pos_slot`, `pos_rank` verbatim strings (252 item 3(a)); `dt_raw` (the file's `dt` text); `espn_id` and `gsis_id` verbatim (both ids kept); `rows_refused` (the count) on the rows of a (dt, team) group that lost a row with no `espn_id` (262 item 5) |

**The player's key.** `record.player_key` keys every fact and slot on `source_player_id`, so the key must be ONE id
that does not move between loads: an id switch (an empty `gsis_id` filled in later, under a "gsis else espn" key)
would close the player's interval "slot asserted to someone else" (the same player) and open a new one, a false flip
in exactly the QB1 reading the record exists for. The key is therefore `espn_id` (the chart is ESPN's: its own id).
`dt_raw`, `espn_id` and `gsis_id` are in `record.VOLATILE_ATTRS` (identity and the source's time text, not the fact),
so a `gsis_id` filled in later changes attrs only, never the key, and does not read as a flip (pinned by a test; 262
item 5: "Code's P1 fix (the gsis-filled-later false flip) stays — it is correct even though the data has not produced
the case yet").

**#840, RULED on the real files (ARCHITECT 2026-11-05 11:55 ET, addendum 262 item 5, verbatim in part):** "READ on the
real files by me (the probe over both files, by column name; the receipt): depth_charts_2025.csv, 554,215 rows — blank
`espn_id` 0 (0.00%), blank `gsis_id` 5,577 (1.01%); depth_charts_2026.csv, 747,450 rows — blank `espn_id` 0 (0.00%),
blank `gsis_id` 24,382 (3.26%). Players first seen WITHOUT an espn_id that later gained one: 0 in both files [...]
RULED: keying on `espn_id` is right (never blank in 1.3M rows); the residual case has frequency zero and gets a GUARD,
not a design: a row with a blank `espn_id` is counted and refused into the group's `partial` status, never keyed by
name." Built: `source_player_id` is the `espn_id` only. A row whose `espn_id` is blank is NEVER asserted (not keyed by
its `gsis_id`, not by its name); it is counted on the receipt ("rows with no espn_id: N, refused, never keyed by
gsis_id or name"); its (dt, team) group is `partial`: the group's other rows are asserted carrying `attrs.rows_refused`
(the count), `derive` and the receipt's guard read that team at that load as partial (it closes nothing; it is never
the team's previous complete group: section 4), and the receipt lists the group under "partial team groups" ("K
row(s) with no espn_id refused (N asserted)"). The OBSERVATION's status keeps its ruled meaning (254 item 2(7),
section 6(g): `partial` = a team or match left unmapped): a refused row makes its GROUP partial, not the observation.
A new load whose rows were all refused is still a new load: the receipt counts it ("new N") and never says "no new
load". The file is not refused for it (the row check still refuses a row naming no player at all). At the record,
"never keyed by name" is the writer's too: `write_observation` (and `assertion_refusal`, the adapter's pre-check)
refuses an assertion of a snapshot source with no `source_player_id` ("carries no source_player_id: a row is never
keyed by name"); the adapter never passes one.
`pos_grp_id`, `pos_id` and `pos_name` are not asserted (the ruling names four attrs); the raw file keeps them.

**The team mapping (law 4).** The existing mapping of an NFL abbreviation to our team: the NFL competition's teams
(`competition_teams` joined to the competition with code `NFL`) whose `teams.tla` equals the file's `team` EXACTLY.
`tla` is the api-american-football team `code` that `sync-teams` stores (`src/adapters/api_american_football.py`). A
team text no NFL team holds, or one that more than one holds (ambiguous), is UNMAPPED: `team_id` NULL with the text
beside it, counted by name, and the observation is `partial` (254 item 2(7): "`partial` = a team or match left
unmapped"). Teams of other competitions (an NCAA program is a `Sport.NFL` team too) are never candidates. Section 5's
read of the schema PR said no team row carries an nflverse abbreviation; whether the host's stored codes equal
nflverse's is read by the first host run's receipt (its unmapped-team line), not assumed here.

### Only new rows; both seasons; backfill

- A row is asserted only when its `dt` is later than the newest `source_stamp` the record holds for the source
  (`nflverse.watermark`, across every season's file: the ruling's "for the source"). The others are read and counted
  ("older rows not asserted again"). So each `dt` is asserted once, in one observation, and the record's loads arrive
  in `dt` order (section 4's two clocks rely on it).
- 2025 and 2026 alike (259 item 2(c): "2025 IS IN SCOPE"). Because the watermark is the source's, the 2025 file must
  be read BEFORE the first 2026 read. hosting-h1.md's live-host recipe makes that read REQUIRED and FIRST, and stops
  unless it exits 0; T11 states the same order for a fresh host.
- **A file that cannot add anything is never silent.** A changed file whose newest `dt` is EARLIER than the watermark
  (the 2025 file after a 2026 read; any older or smaller file) is REFUSED, naming both instants
  (`nflverse.older_refusal`): a `--file` exits 2 with nothing written; a fetched file is a `failed` observation (the
  file kept), exit 1, paged by the chain. A changed file whose newest `dt` IS the watermark (rebuilt, nothing new) is
  `complete` with 0 rows and the receipt line "no new load". The residual this check cannot see: a `--file` holding
  NEWER loads than the record but fewer teams (an excerpt) moves the watermark forward, and the full file's older
  loads are then never asserted; the live DB takes whole release files only.
- **No load from the future.** A row whose `dt` is later than our fetch's time plus `nflverse.FUTURE_SKEW` (1 hour of
  clock skew) refuses the file naming its line (`nflverse.future_refusal`; a `--file` exits 2, nothing written; a
  fetched file is a `failed` observation, kept). One such stamp, once held, would be the source's watermark for good
  (append-only) and every real load after it would read "older". RULED (262 item 3): "the 1-hour future-skew tolerance
  stands (a load stamped more than one hour ahead of our clock is refused with its reason; within the hour it is
  accepted and the skew is printed on the receipt — clock drift is a fact, not a fault)". A file whose newest `dt` is
  ahead of our fetch by up to the hour is asserted, and the receipt prints "clock skew: the newest load (dt ...) is N s
  ahead of our fetch (...), within the 60 min tolerance: accepted"; a file not ahead prints no skew line.
- Every row recorded more than `SOURCE_CADENCE_HOURS["nflverse_depth_charts"]` (24) hours after its `dt` reads
  BACKFILLED by the record's rule (section 3): every 2025 row and every 2026 row before the first fetch (259 item
  2(c)). The receipt counts them.

### The partial guard's count

The receipt's "partial team groups: N, closing nothing" lists each new (dt, team) group below half its team's
previous complete group, with both counts, and each group that lost a row with no `espn_id` (262 item 5), with the
rows refused and asserted; the line after it counts the rows with no `espn_id`. The previous complete groups come from the store's own loads first
(`nflverse.stored_complete_groups`, folded by `record.guard_load`, the function `derive` closes by), then from the
fetch's loads in `dt` order.

### The fetch: a conditional GET (259 item 2(e))

Verbatim: "the fetch sends If-None-Match with the stored ETag of the last payload (GitHub release assets serve one; the
redirect is followed — the asset host today is release-assets.githubusercontent.com); a 304 is a `complete`
observation with rows_asserted 0 carrying the previous payload's sha256 (the byte-identical case of 252 item 3(a)), so
the daily cost is one small request on an unchanged day and a ~70 MB file otherwise; the whole file is kept under
logs/availability/nflverse_depth_charts/<date>/ only when it changed."

- **The request:** `GET https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_<season>.csv`,
  redirects followed, streamed, `timeout=(10, 120)` (connect, per-read seconds: `nflverse.TIMEOUT`), a `User-Agent`
  naming the project, `If-None-Match` when an ETag is stored. No secret is needed or sent; the endpoint written is the
  requested URL, never the redirect's signed one.
- **Where the ETag is stored:** BESIDE THE PAYLOAD FILE, `<payload_path>.etag`, written when the file is kept, and
  REWRITTEN when a byte-identical 200 carries a different ETag (the sidecar is not the record: no row changes), so the
  next unchanged day sends a validator the server matches instead of downloading the file again. No
  column of `availability_observations` holds a validator (`endpoint`, `http_status`, `payload_sha256`,
  `payload_path` and `error` each mean something else), and no column or table is added. "The last payload" is the
  newest complete or partial observation of the same endpoint that kept one (`nflverse.previous_payload`); a missing
  sidecar sends no `If-None-Match` (an unconditional GET, said on the receipt).
- **The answers:**

| Answer | Observation | Payload |
|---|---|---|
| 304 | `complete`, rows_asserted 0, `http_status` 304 | the previous payload's sha256 and path |
| 200, byte-identical to the last kept payload | `complete`, rows_asserted 0 | the streamed copy removed; the previous sha256 and path; the answer's ETag, where it differs, written beside that payload |
| 200, changed | `complete` or `partial` (or `empty`: a header and no row) with its new rows | kept: `logs/availability/nflverse_depth_charts/<UTC date>/<HHMMSS>Z-<sha256, first 16 hex>-depth_charts_<season>.csv`, created exclusively, its ETag beside it |
| 200, a file the adapter refuses | `failed`, the refusal as its error | kept (the raw answer is the evidence) |
| any other status | `failed`, `HTTP <status> from the release asset (refused): <class>`, the class worded as requests words it (`503 Server Error`, `429 Client Error: Too Many Requests`, `404 Client Error`) | none |
| a raised call or a broken stream | `failed`, the error redacted | none (a partial `.part` file is removed) |

  The error text has every URL's query string cut first (a release asset redirects to a signed URL), then
  `record.redact`, then 256 characters (`nflverse._scrub`, then the cut). EVERY refusal goes through the same scrub
  before the cut, before it is printed or kept (Codex on #841, round 2): a refused fetched file's reason (its error and
  the run's refusal; the reason can quote the payload, a `dt` holding `api_token=...`), a store refusal after the keep,
  and a refusal that ends the run (exit 2, printed by the command). The receipt prints the error (`error (redacted)`)
  AS STORED, never scrubbed a second time: the cut can split a placeholder the scrub left (`?[query rem`,
  `api_token=[REDAC`), and a second scrub would regrow it and print other text than the row holds; every producer
  scrubs before its cut (the 304 and status errors are constant text). The team texts it prints (payload text) are
  scrubbed where it prints them.
- **The observation's clock (Codex on #841, round 2).** A 200's `fetched_at`, and so the `recorded_at` of every
  assertion it carries, is our clock AFTER its body has fully streamed and, when it changed, been kept at its payload
  path (a byte-identical 200: after its body has streamed and been hashed): never the headers' arrival, so no fact is
  recorded as known before its bytes were on disk, and a fetch that finishes after a kickoff never reads pregame. A
  304 (no body) is our clock at the answer. A failure keeps its own rule: a raised call is our clock when it raised; a
  refused status, a broken stream, or a failure keeping the file is our clock when the answer's headers arrived (the
  attempt's time; a failed observation asserts nothing). A fetched file refused after the keep carries the completed
  fetch's time. The kept file is named by the headers' arrival (`<UTC date>/<HHMMSS>Z`: the download's start, taken
  before the body is read), so on a download that crosses midnight UTC its date directory is the start's. A `--file`
  reads our clock once: its name and its `fetched_at` are the same instant.
- **Retries.** The chain's runner retries a step whose output falls in its transient classes (connection errors,
  timeouts, HTTP 5xx and 429; `sp_run.RETRY_BACKOFF_S`, two retries); the 5xx and 429 wording above puts those answers
  in that class, like a connection error, and every other status is never retried. Each attempt is its own run of the
  command and its own `failed` observation (a fetch that raised is a row, item 1(a)): one chain run can write up to
  three.
- **The disk:** a changed day keeps a whole file (~70 MB for 2026 per 259 item 1); unchanged days keep nothing. Under
  `logs/` (git-ignored, never under data/, never mirrored: the exports mirror carries `exports/` only).
- **`--file PATH`** reads a local release file the same way (endpoint `file:<its name>`, no HTTP status); a refused
  file exits 2 with nothing written and nothing copied; its bytes are kept under the payload directory when they differ
  from the last kept payload of that endpoint, as `<HHMMSS>Z-<sha256, first 16 hex>-<its name>`.
- **One read of a `--file` (Codex on #841, round 1, finding F; RULED by 262 item 6: "copy once to a temporary file,
  then hash, parse and keep that same copy").** `nflverse.snapshot_copy` copies the file ONCE to a private temporary
  file (`tempfile.mkstemp`, outside the checkout, so a refusal still leaves nothing under `logs/`) and hashes that copy;
  the parse, the row checks and the keep all read the copy, never the original again, and the keep hashes the bytes as
  it copies them (a mismatch is removed and refused). A file changed while the run reads it therefore cannot make the
  hash, the asserted rows and the kept bytes disagree (pinned by a test that rewrites the original after every read
  step). The temporary copy is removed whatever the run's end.
- **The kept file (Codex on #841, round 1).** Its name carries the payload's sha256 prefix, so two different payloads
  kept in one second never share a path, and it is created exclusively (`O_EXCL`): a path that already holds the same
  bytes is reused, one that holds other bytes is refused (a fetch: a `failed` observation; a `--file`: exit 2), and the
  evidence there is never overwritten. The partial download is a temporary file of its own (`mkstemp`).
- **Checked before any file (Codex on #841, round 1).** The endpoint is checked by the writer's own rule
  (`record.endpoint_refusal`: none given, longer than 512 characters, or a secret) before any call, copy or file; the
  kept path by `record.payload_path_refusal` and the file name's length (255 bytes) before any directory or file is
  made. A refused `--file` (a name like `api_token=secret.csv`, or one too long to keep) leaves nothing on disk and no
  row. A file name cannot reach 512 characters (NAME_MAX), so the endpoint's length rule is the writer's, run first.
- **Every row to be asserted, by the writer's own checks.** `record.assertion_refusal` (the same
  `_check_assertion` the writer runs: `player_name` at most 128 characters, `source_team` and `source_player_id` (the
  `espn_id`) at most 64, a player and a team named, `attrs` as JSON) runs on every row a run
  would assert. On a `--file` it runs before the keep (on the run's temporary copy): a refusal exits 2, nothing kept,
  nothing written. On a fetch
  the payload is kept before it is read (the evidence), so a refusal is a `failed` observation that keeps the
  payload's path, the writer's reason its error. A refusal the pre-checks cannot see (the store's own, a trigger) is
  never left as an orphan either: a `--file`'s copy made by the run is removed and the run exits 2; a fetch is
  written as a `failed` observation keeping the path. Rows at or before the watermark are not asserted and not
  checked.

### The command: `availability-nflverse`

`python cli.py availability-nflverse [--season YEAR] [--file PATH]`

- `--season`: the release file's season, 2025 or later. Default: the current season, the calendar year from March on,
  else the year before (the season file turns over in March: 259 item 1 read the 2025 file's last load at
  2026-03-14T07:32:09Z and the 2026 file's first on 2026-03-22).
- `--file`: a local file instead of the fetch; `--season` is not read.
- No `--db`. 254 item 2(9) ("`--db` STAYS (198 item 6(ii))") is the query command's fence for reading a `.backup`
  copy; an ingest writes, and a copy is never written, so the ingest writes the live DB only.
- It holds the chains' DB lock (`sp_common.sync_lock`, a no-op inside a chain step) across the store's read (mode=ro),
  the fetch and the write. A missing DB file or an unmigrated store is refused (exit 2) before any call.
- The receipt: the observation id, its status, endpoint, `fetched_at` (a 200's: our clock after its body streamed and
  was kept, Codex on #841 round 2) and HTTP status; the error (redacted: scrubbed before the cut, printed as stored)
  where failed; rows read, loads (and new loads), new rows, rows asserted, older rows not asserted again with the watermark;
  "partial team groups: N, closing nothing" with each group; "rows with no espn_id: N, refused, never keyed by gsis_id
  or name" (262 item 5); unmapped teams by name (scrubbed: payload text) with their rows, ambiguous codes, unmapped players; backfilled rows;
  the clock skew where the newest load is ahead of our fetch (262 item 3); the payload sha256's first 16 characters and
  path; the ETag line (sent or not, and the answer); then "Depth charts: nflverse (CC BY 4.0)".
- Exit 0 for complete, partial or empty; 1 for a failed observation (written); 2 for a refusal (nothing written).
- The write is one `record.write_observation` (one fetch, one observation; a retried chain step is another run). The
  writer inserts the assertions as one executemany INSERT per 5,000 rows (`record.WRITE_CHUNK`), in the same one
  transaction, every row through the insert triggers as before; a whole season file is ~750,000 rows (measured here on
  750,000 synthetic rows: 45 s, peak memory about 0.9 GB with the rows in hand; the ORM objects it replaced took about
  twice the time and three times the memory at 100,000 rows).

### The chain and the timer

- `availability-daily` (`deploy/hosting/chains.py`): one step, `availability-nflverse --season 2026` (the season is
  explicit, as every chain's is, and moves with them). `go_on` names it (`AVAILABILITY_GO_ON`): a failed read is
  receipted with that reason, the chain's exit is its exit, so `OnFailure` pages, and no later step exists to stop. No
  `backup` key (the daily backup stands as it is; RULED, 262 item 3: "no `backup` key on the chain — the 07:20Z and
  09:30Z daily backups bracket the 08:45Z timer, and the record is append-only, so the chain carries no backup step of
  its own, as built"). `availability-nflverse` is in `UNMETERED` (github.com, never
  api-sports). It is inside no other chain. A transient failure is retried by `sp_run` like every step's, each attempt
  its own `failed` observation (the fetch's "Retries", above).
- `sp-availability-daily.timer`: daily 08:45 UTC (259 item 2(d): "08:45Z daily stands — it captures the ~07:00Z load
  about 1.7 h later, before any kickoff of the day; a second load of the day lands the next morning, which the recorded
  clock states truthfully"). On hosting-h1.md's Schedule table and T11 `TIMERS` list, CI-checked.
- **Enablement: the architect's block** (252 item 7: "the first host reads and the timers' enablement are my blocks").
  The precedent followed is every timer since H1 (`sp-ncaa-schedule`, `sp-cup-observe`): shipped on `TIMERS`,
  `install.sh` enables nothing and `sp_deploy.py` installs no unit, so nothing runs until hosting-h1.md's live-host
  recipe is run, in that block, after the migration tag that carries `migrate_availability_record.py` is deployed.
  Until then the deploy receipt's timers line names it as a `TIMERS` timer not enabled.
  **ENABLED on the host 2026-11-09 at 14:16Z**, by that block, on v1.6.5: the 2025 read first (14:12Z, observation
  #1, exit 0), then one enable of this timer and sp-nba-daily's, exit 0, both active
  (ARCHITECT 2026-11-09 09:55 ET, addendum 304 item 2, the deploy record docs/RELEASES.md quotes under v1.6.5).

### Attribution

`record.SOURCES["nflverse_depth_charts"]` is "Depth charts: nflverse (CC BY 4.0)" (252 item 3(a)): the `availability`
command prints it whenever an nflverse fact is shown, and the ingest's receipt prints it last.

### Percent-encoded credentials (#835 item 1; addendum 258 item 2(1))

Verbatim: "`_endpoint_secret` checks the percent-decoded endpoint too (unquote) for credential names and for
environment values; `_PARAM` admits `%` escapes and classifies the decoded name; `redact` runs on the decoded string as
well as the raw one; percent-encoded cases join the endpoint-refusal and redact tests (positive controls: `api%5Ftoken`,
`s%69g`, `%6Bey` refused; a token behind an encoded name redacted). No feed PR merges without them".

As built in `record.py`: a parameter NAME may hold `%XX` escapes and is classified decoded; `_endpoint_secret` runs
every check on the endpoint and again on its decoded form (decoded until stable, at most three rounds), and its reason
says "(percent-decoded)" when only that form carried it; `redact` redacts the raw text, then its decoded form, and
returns the DECODED redacted text when that found what the raw reading did not (an encoded separator, an encoded
environment value). Tests fail-first against the schema PR's `record.py`.

### What this feed does NOT do

- The 2023–2024 weekly files: refused, a different shape; a second adapter later if a backtest wants them (252 item
  3(a)).
- `projected_starter`: never written by this feed (a daily rank is not a game-day confirmation).
- No player mapping (254 item 2(3)); no row in any existing table; no provider call from a closing run; nothing under
  data/; no update or delete path (the schema PR's triggers stand untouched).
- The NHL landing feed's poll key (#835 item 2, 258 item 2(2)): the NHL feed's PR (section 10).

## 10. The NHL landing feed (item 3(b); addenda 258 item 2(2), 340 and 341)

Verbatim (252 item 3(b)): "THE NHL LANDING READ (source `nhl_api_landing`): per game of the NHL day (the probe's
schedule read: GET /v1/schedule/<date>, game types 2 and 3), the landing page at the probe's offsets (T-120, T-90, T-60,
T-45, T-35, T-30, T-15, T-0) — each poll an observation with its poll_label — asserting projected_starter per side from
matchup.goalieComparison.<side>Team.leaders[0] (playerId, name beside it) EXACTLY as scripts/nhl_leaders_order_receipt.py
reads it, and the boxscore at T+20 asserting eventual_starter (the goalie with toi above zero; two in net = two rows,
flagged; none = an `empty` observation) — post hoc, kind-labelled, never a pregame fact. The polls run under a watch on
the host (an `availability-observe` timer every five minutes, the cup-observe pattern), each poll stamped by our clock;
a poll more than five minutes past its time is a `missed` row."

Code: `src/availability/nhl_landing.py`, `cli.py availability-nhl-observe`, `sp-availability-observe.service` and
`.timer`. Tests: `tests/test_availability_nhl_landing.py`.

### The schedule: support data (340 item 4)

"at most hourly, kept per NHL day — YES. It is support data, not an observation: it asserts nothing about who plays, so
it writes no row in availability_observations; its payload is kept beside the others under
logs/availability/nhl_api_landing/<date>/ with its sha256. A moved start recomputes the polls not yet written; a
written poll is never touched. A failed schedule read invents nothing: no missed rows for games it could not know; one
log line per tick and one notice per NHL day."

As built:
- The NHL day is the probe's: [date 10:00Z, date+1 10:00Z), games of types 2 and 3, parsed by
  `nhl_goalies.schedule_games` and filtered as the probe's `day_games` filters (a test pins the two equal).
- The answer is kept as `<NHL day>/<YYYYmmddTHHMMSS>Z-<sha256, first 16 hex>-schedule.json` only when its bytes differ
  from the newest kept for that day; `schedule.checked` ("<instant> <sha256>", or "<instant> failed") beside it says
  when the day was last read, and a day read within the hour, answered or not, is not read again (at most hourly).
- A 200 whose JSON names no game at all (`{}`, an error object; Codex on #933, round 1) is not a schedule: the games
  already known stand, its body is not kept, and the hour is stamped ("named no game"); no notice.
- A failed read uses the newest kept answer for the day when one exists (the games already known), else knows no game.
  The day's first failed read creates `schedule.notice` and makes the tick exit 1 (the unit pages once); every tick
  prints its line (a failed read, or "last read FAILED at <instant>: the next read after <instant>") and exits 0.
- "A moved start recomputes the polls not yet written": a poll counts as WRITTEN when the store holds an observation of
  the source at the game's endpoint (the landing or boxscore URL, carrying the gameId) with its label, scheduled
  against a start within SIX HOURS of the game's current start (ARCHITECT 2026-11-11 14:10 ET, addendum 343 item 1: "a
  label counts as written only against a start within SIX HOURS of the game's current start; a start that moves by six
  hours or more (a postponement) gets a fresh set of polls against the new start, new rows beside the old, nothing
  touched [...] A slip inside six hours (a delayed puck drop) schedules no second series"; `SERIES_SCOPE`), OR at its endpoint and scheduled time under another label (#835 item 2's key: a start moved
  earlier can land a recomputed poll on one already asked; it is not asked twice and never repeats "already"); an
  unwritten poll takes its time from the start this tick knows. `kickoff_at` on a row is the schedule's start as that
  tick knew it.

### The window, the polls, the lateness

- The window: games whose scheduled start is within [now − 6 h, now + 2 h] (`LOOKBACK`, `AHEAD`), from the NHL days it
  touches. Two hours ahead is T-120; six hours back covers H0-3's 04:00-05:59Z gap and a T+20 read with room. A host
  down longer than six hours leaves no row for a poll older than the window (the gap shows in the boot and timer
  receipts, not as invented rows).
- A poll whose time has passed and is not written is DUE. More than five minutes past it is a `missed` row and no call
  (252 item 3(b)); else it is asked once. A tick with a poll due plans again under the DB lock on the clock as it then
  reads, so a poll that passed its five minutes while the tick waited for the lock is `missed`, never asked late; and
  the cutoff is read again just before each call (Codex on #933, round 1), so slow earlier calls in one tick cannot
  carry a later poll past its five minutes into a call. 340 item 3: "a poll scheduled inside the 04:00–05:59Z buffer (a late
  West-coast start's T-0 or T+20) is written as a `missed` row by the first tick after the buffer, never dropped".
- `fetched_at` is our clock after the body has been read in full (a raise: the raise's instant). `late` is set when it
  is more than five minutes after the poll's time (an answer delayed by the DB lock, say).

### The rows

| Poll | Status | Assertions |
|---|---|---|
| a landing with leaders[0] on both sides | `complete`, or `partial` when a team or the match is unmapped | two `projected_starter` |
| a landing with one side's leaders[0] | the same | one; the other side's reason (the receipt's words) on the console |
| a landing with neither (no goalieComparison, empty lists) | `empty` | none |
| the T+20 boxscore | `complete` / `partial` | one `eventual_starter` per goalie above zero toi; `attrs.two_in_net` on a side with two or more |
| a boxscore with no goalie above zero | `empty` (when a goalie's toi could not be read, `error` says so: not a clean "none in net") | none |
| a boxscore the ingest refuses (goalie lists not sided one home + one away) | `failed`, the reason, the payload kept | none |
| a raised call, a non-200, an answer that is not JSON | `failed`, the error redacted (a non-JSON 200 keeps its payload) | none |
| a poll more than five minutes past its time | `missed`, no call | none |

Every assertion: `player_id` NULL (254 item 2(3)), `source_player_id` the NHL playerId, `player_name` verbatim, `team_id`
(below) and `source_team` (the schedule's own text for the side, verbatim: its abbrev, else its full name, else placeName +
commonName with accents kept; stable across polls; a side the schedule names no team for asserts nothing, counted as
missing), `match_id` (below), `attrs.side`, `attrs.source_match_id` (the gameId, `record.SOURCE_MATCH_IDS`),
`source_stamp` NULL (252 item 1(b): "the NHL landing gives none"). The eventual rows add `toi_seconds`, `two_in_net`
and `toi_unread` (the side's goalies whose toi the ingest could not read). The starter slots are per kind (section 4;
258 item 2(3)): an `eventual_starter` never closes a `projected_starter`.

### The mapping (addendum 341 item 2)

"the landing feed resolves team_id by THAT path, unchanged — a side maps only when its candidates resolve to exactly
one of the NHL competition's teams; otherwise team_id NULL with source_team verbatim and the observation `partial`.
This reuses a certified matcher; it adds no new name matching, no alias of your own, and writes no tla."

As built: the side's candidates are `nhl_goalies.team_names()` of the schedule's side (the full name, then placeName +
commonName, then `NAME_ALIASES`, accents stripped), each through `match_lookup.normalize_team_name` against the stored
names of the NHL competition's teams (the teams of its stored matches: competition code NHL, sport NHL; the host's 32
of 341 item 2). The side maps only when the UNION of the teams its candidates name is exactly one team; none, or two
or more (a name held by two rows, an alias naming an older row), leaves it unmapped. The match: the one match
`nhl_goalie_appearances` links to the gameId (two distinct links: refused), else `nhl_goalies.match_game` as it stands — read for 341 item 2: `find_match` reads the
NHL's rows within 12 hours by both names and excludes only CANCELLED and STALE_ORPHAN, so a SCHEDULED row maps before
the game — else NULL with `attrs.source_match_id`. One match, one game (law 4): a match two gameIds resolve to among every game the
tick's schedules know (not only the due ones: Codex on #933, round 1), or one the record already holds under another
game's endpoint, is refused for both (NULL): Step B's key (source, match,
kickoff, label) would otherwise read the second game's poll as the first's.

### The poll key (#835 item 2; addendum 258 item 2(2))

"the poll's uniqueness is keyed on (source, endpoint, scheduled_at) where scheduled_at is set (the endpoint carries the
game's own id; the scheduled poll time is the poll), a partial unique index beside the existing one and the
insert-guard's "already observed" branch extended to it [...] No new column."

As built: the index `uq_avail_obs_source_endpoint_scheduled` (unique, `WHERE scheduled_at IS NOT NULL`) and the trigger
`trg_availability_observations_poll_guard` (its message carries the insert guard's words, "this poll is already
observed", so `write_observation` answers "already" for it). The branch is a trigger of its own, as the snapshot hash
guard is (262 item 1): `CREATE TRIGGER IF NOT EXISTS` never changes the installed insert guard on a store already
migrated. `migrate_availability_record.py` creates both on its next run (additive and idempotent); until then the watch
refuses to write (exit 2). The nflverse rows set no `scheduled_at`, so the key reads none of them.

### The watch (340 item 3)

`sp-availability-observe.service` (oneshot, `cli.py availability-nhl-observe`, OnFailure through
`sp-notify@availability-observe`, at most one page in thirty minutes: `sp_notify.THROTTLED_UNITS`, addendum 343
item 2) and `.timer` (every five minutes at :00 .. :55, hours 00-03 and 06-23 UTC,
`Persistent=false`, `AccuracySec=1s`), on T11's `TIMERS`, shipped disabled; the architect's block enables it
(**ENABLED on the host 2026-11-12 at 15:23–15:25Z** by that block, on v1.6.7, ARCHITECT 2026-11-12 10:55 ET,
addendum 354 item 1: the first tick, at 15:25:02Z, wrote observation #5; the timer set read CLEAN at 21). Not a
chain: no `chains.py` entry, no chain receipt per tick. A tick plans mode=ro; with no poll due it calls no game page and
takes no lock; with a poll due it takes the chains' DB lock and plans again under it.

### What this feed does NOT do

No model change, no Desk input, no row in any existing table, no call from a closing run, no backdating, no deletion, no
payload under data/, no key (the NHL API takes none). No player mapping, no alias or tla of its own. The receipt's
reading of leaders[0]'s reliability stands as read on #105: this feed records what the page asserted and when.

## 11. The graph projection (item 4; addendum 347 item 5)

252 item 4, verbatim: "a nightly rebuild of the record into an EMBEDDED graph engine on the host — file-based, no
server, Cypher — nodes Player, Team, Game, Observation; edges from the assertions carrying kind, recorded_at,
source_stamp and the derived interval; rebuilt whole from SQLite (mode=ro) by one command, `availability-graph-rebuild`,
as the last step of availability-daily; its file under logs/, never under data/, never backed up, never mirrored,
deletable without loss. NEVER written by a chain other than its rebuild, NEVER read by the Desk, a prediction, an
export or a gate; a failed rebuild is a receipt line and stops nothing."

347 item 5 (ARCHITECT 2026-11-11 19:50 ET) picked LadybugDB on the candidates page (`docs/specs/availability-graph-candidates.md`,
#936): the package `ladybug`, version 0.22.3 exactly, the cp312 manylinux x86_64 wheel by its sha256. The package
imports as `ladybug`: its wheel's `top_level.txt` names `ladybug`, and there is no `lbug` module (`lbug` is the native
library's name, `ladybug/_lbug.cpython-312-x86_64-linux-gnu.so`).

**The engine, host-only (347 item 5(a) and (d)).** `requirements-graph.txt` holds one line, the exact pin with its hash;
requirements.txt does not name it and CI installs requirements.txt alone. The wheel holds `ladybug/` and its dist-info
only: no `.pth` file, no console script, no runtime dependency (every Requires-Dist is extra `dev`). Its native library
links the system OpenSSL 3 (`libssl.so.3`, `libcrypto.so.3`). `src/availability/graph.py` imports it inside `engine()`,
the one place in the app (pinned). It reads the installed version from the distribution's metadata and refuses any
other (never `ladybug.__version__`, which asks the native library), drops the package's environment overrides
(`LBUG_PYTHON_BACKEND`, `LBUG_C_API_LIB_PATH`), imports the native module (`ladybug._lbug`) through the package's own
loader before anything else is asked of it, refuses when it does not import, and opens every database with
`backend="pybind"`: the package's ctypes fallback (`ladybug._lbug_capi`, a `liblbug.so` found by path, the working
directory included) is never imported.

**The read.** `record.walk(s, sport)`: every assertion with the interval it opened or restated under the recorded clock
and, where it carries a source stamp, under the source clock: the same partitions and the same `_derive` as
`history` (item 2: "there is no second path"), one partition at a time, both clocks from one read (a partition's rows
under the source clock are exactly its stamped rows). Pinned equal, row by row, to `history(s, sport, datetime.max,
clock)` for each clock on the randomized histories.

**The graph.** Node keys are the record's own identities (`player_key`, `team_key`, `match_key`: the source's id or text,
ours only where the source gave none), per sport and source (one source's id in two sports is two nodes, #944); our
ids ride along as columns, each from the latest assertion that carries one.
- `Player(key, source, source_player_id, name, player_id)`, `Team(key, source, source_team, team_id, name)` (the name from
  our teams table where the team maps), `Game(key, source, source_match_id, match_id, competition, season, kickoff,
  status, home_team_id, away_team_id)` (the columns from our matches where the game maps; a source-keyed game carries its
  `match_id` when it maps), `Observation(...)` (every observation, missed and failed ones included), and one
  `Build(built_at, copy, copy_sha256, git_sha, engine, assertions, observations)`.
- `FACT` (Player to Team), one per assertion: `assertion_id`, `observation_id`, `sport`, `kind`, `recorded_at`,
  `source_stamp`, `game` (the game's key, where the assertion names one), `attrs` (JSON text), the recorded clock's
  interval (`rec_interval` = its opening assertion, `rec_start`, `rec_end`, `rec_closed_by`, `rec_why`), the source
  clock's (`src_*`, NULL where the row carries no source stamp), `backfilled`, `post_hoc`.
- `ASSERTED` (Observation to Player), one per assertion; `IN_GAME` (Team to Game, the side's text from the latest assertion that gives one, #944), one per pair an
  assertion names; `ABOUT` (Observation to Game), the games an observation's assertions name, else its own match.
- Timestamps are naive UTC (the engine drops an offset without converting it, so the rebuild converts first).

**The copy (347 item 5(b)).** `--backup-dir DIR`: the newest daily `.backup` copy (`sports_YYYY-MM-DD[_HHMMSS].db`,
pull_backup's pattern) whose `.sha256` sidecar matches its bytes, refused when it is older than 26 hours by its file time;
or `--db PATH`. Either passes `mlb_pitchers_gate.check_db` (never under data/, never the configured DB) and is read
through its mode=ro + immutable=1 session; the copy is byte-identical after a run (pinned).

**The build.** Staged as CSV in a directory beside `--out` (100,000 rows a file: one COPY of a million edges overflows
the 256 MB buffer pool the rebuild sets), loaded by COPY with `PARALLEL=FALSE` (the parallel CSV reader refuses a
quoted newline, and the record keeps whatever text its source gave: one such name would fail every rebuild), closed, re-opened read-only and counted (a read-write open
rewrites the file's bytes), moved onto `--out` by `os.replace` only when every count equals what was staged; the staging
directory is removed whatever the outcome, a SIGTERM (the unit's stop or timeout) included; through that cleanup a SIGTERM is
deferred, so a signal during it never turns a committed run into a failure (#944), and it is re-delivered once the
previous handler is back, after the run's line is written (Codex on #952). One run at a time (a lock
beside the graph; a second run is refused). One line of `rebuild.jsonl` beside the graph per run: ok (the counts, the
graph's sha256 and size, the copy and its sha256), refused or error; a refused `--out` writes nothing at all, and a
SIGKILL (MemoryMax) writes no line and leaves its staging, which the next run removes and names on its own line. A copy
that does not read as SQLite through the mode=ro + immutable=1 URI is refused as such, before the migration check. A
node's ids are the latest assertion's that carries one (by recorded_at), whatever order the walk yields its partitions
in, and a player's name is the latest assertion's. The move onto `--out` is the commit point: the receipt's hash and
size are computed before it, so a signal after it leaves an ok line, never an error. `--db` is never `--out` (a copy
named `.lbug` would be overwritten). Exit 0 built, 2 refused, 1 failed; the previous graph is untouched unless a run
succeeds.

**The unit (347 item 5(b)).** `sp-availability-graph.service` and `.timer`, daily 10:20 UTC (after the 09:30 sp-backup
whose copy it reads; `After=sp-backup.service`, so a catch-up of both timers after downtime runs the backup first), its own unit and not availability-daily's last step: a chain step runs inside sp-chain@'s unit,
which loads host.env and has the network. No EnvironmentFile, `PrivateNetwork=yes`, `NoNewPrivileges=yes`, `ProtectSystem=strict`, the graph's directory the one writable path; because the sp user can still read what it owns, /etc/sports-predictor (host.env and an exports-mirror deploy key installed there) and data/ are inaccessible and the checkout's .env (config.py loads it on import) is /dev/null; `PrivateUsers=yes`, `ProtectProc=invisible` and `ProcSubset=pid` so another sp process's /proc/<pid>/environ and /proc/<pid>/root (its own unmasked view) are refused; `RestrictAddressFamilies=none` (PrivateNetwork leaves filesystem sockets reachable); `PrivateDevices=yes` and `PrivateIPC=yes` (no shared /dev/shm); /tmp and /var/tmp empty and read-only. `MemoryMax=1536M`, `Nice=10`.
OnFailure pages through `sp-notify@availability-graph`. Shipped disabled; its enablement is the architect's block (347
item 6(D)); on a fresh host T11 leaves it out until that block has installed the engine and made its directory.

**Nothing reads it (347 item 5(c)).** Read on every Python file's syntax tree (pinned): no module but
`src/availability/graph.py` imports the engine (an `import`, `from`, `__import__` or `import_module` of it), no module
but `cli.py`'s command imports graph.py, and none but those two names the graph's path.

**At scale, on this PR's container (a receipt, not the host):** a SYNTHETIC history of 931,335 depth assertions (32 teams,
590 daily full charts) on a 460 MB `.backup` copy, rebuilt by `cli.py availability-graph-rebuild` inside a mount and
network namespace (no network, the root filesystem read-only, the graph's directory the one writable path, an empty
environment): 81 s, peak RSS 614 MB, one 253 MB file and no sidecar, the copy's sha256 unchanged.
