# NCAA CFBD label lane (#176 probe read) — DATA LANE

**Status: BUILT 2026-10-07; run on the laptop 2026-10-08 (receipts read).
SCOPE + JOIN (J1–J4) built 2026-10-08, re-ingest from the saved payloads
pending.** No model change. GATE #79 (frozen 2026-09-30) is unchanged and stays
SUSPENDED-PENDING-DATA until the architect reads the coverage receipt.

## SCOPE + JOIN (ARCHITECT 2026-10-08, addendum 10 item 3) — DATA LANE

No model constant changed. #79's declaration and acceptance numbers are untouched. The ncaa-elo-v1r declaration is NOT written here (no registry write).

### The rulings (verbatim)

> SCOPE: "ncaa-elo-v1r is an FBS model. Its stream is the games that carry a CFBD both-FBS label; a stored game without one is neither walked nor scored, in the gate and in the shadow. My 2026-10-07 coverage condition is restated for that stream: the side table labels at least 95% of CFBD's completed both-FBS games in each season used, read from the ingest receipt (joined over in scope), every unmatched game listed. The shadow's precondition is that same fact. #79's all-division stream stays in the record as declared; its acceptance numbers do not move (margin 0.010, bands, rating range, 500 test games). The declaration's split, neutral-site rule, postseason rule and confirmation plan are mine to rule after the re-ingest; do not write the declaration yet."

> JOIN: "J1. A source game the first pass leaves unmatched is retried against our NCAA matches within 36 hours either side. It joins only if exactly one (match, orientation) fits by the same name tiers, that match is not already joined, and the final scores agree in that orientation. join_via is dateshift. Each such row is listed with both kickoffs and the offset; a name fit whose scores disagree stays unmatched and is listed with both scores. J2. In the join and in alias vetting our team names are HTML-unescaped before normalization. In the v1r stream and the shadow, team ids whose unescaped names are identical are one team, keyed by the lowest id; the receipt lists every such group and every name that changes. J3. Aliases, pinned: App State -> Appalachian State; Massachusetts -> UMass; Buffalo -> Buffalo State; Rice -> Rice Owls. J4. The side table stores CFBD's seasonType as served: a nullable column with its own migrate script, filled on the next ingest, carried on Game as data only. Nothing in matches or teams is rewritten by any of this."

Receipt findings that led here (not repaired by this lane): 74 of the 2025 both-FBS games are stored one day early (00:00–03:59 UTC kickoffs; the 12h window misses them). "Hawai'i" and "Hawai&#x27;i" are two team rows. The stage field is the provider's division label, so #79's postseason exclusion never fired. The provider names FBS Buffalo "Buffalo State" and Rice "Rice Owls". The adapter's escaped names, the duplicate team row and the early kickoffs in `matches` stay as they are.

### What was built, by ruling point

| Point | Built (`src/ingestion/ncaa_cfbd.py` unless named) |
|---|---|
| J1 | `tier_fits` (the name tiers, shared by both passes), `dateshift_retry`, called by `build_labels` after the first pass. |
| J2 join | `our_norm` (html.unescape, then `normalize_team_name`) in `load_ours`, `vet_aliases` and `build_labels`; `escaped_names` lists every changed name in the ingest receipt. |
| J2 stream | `ncaa_backtest.team_merge` / `TeamMerge`: a read-time id mapping, applied in `v1r_stream` and in the shadow's walk and upcoming games. |
| J3 | `ncaa_cfbd_aliases.json`: the four pins. |
| J4 | `NCAACFBDLabel.season_type` (nullable), `migrate_ncaa_cfbd_season_type.py`, filled by `build_labels` / `upsert`, carried on `ncaa_backtest.Game.season_type`. |
| SCOPE stream | `ncaa_backtest.v1r_stream` / `load_v1r_stream`; the shadow's `fit`. |
| SCOPE coverage | `fbs_coverage` (the pure fact), the ingest receipt's COVERAGE line and UNLABELLED list, `stored_coverage` (the fact re-read for `ncaa-cfbd-coverage` and the shadow's `coverage_guard`). |

### J1: dateshift

- The first pass is unchanged: ±12h, exact then substring, exactly one (match, orientation) per tier, ambiguity refused.
- Only a game the first pass leaves UNMATCHED is retried. A first-pass AMBIGUOUS game is refused, not unmatched, and is never retried.
- The retry window is ±36h of CFBD's `startDate` (`DATESHIFT_HOURS`). The tiers are the first pass's own (`tier_fits`): exact, and substring only when exact finds nothing.
- The retry joins only when all of these hold:
  - exactly one (match, orientation) fits in the first tier with any fit;
  - that match is not one the first pass joined in this run ("already joined");
  - CFBD's scores, stated in that orientation, equal our row's scores. An unscored row of ours never agrees.
- A joined row carries `join_via = dateshift` (even when an alias resolved a name). It is listed with CFBD's kickoff, ours, and the offset (ours minus CFBD, hours).
- A name fit whose scores disagree stays unmatched. It is listed with both scores (ours in our orientation, CFBD in our orientation).
- An already-joined fit, and a retry with two or more fits, also stay unmatched and are listed with the reason.
- Dateshift rows go through the existing duplicate-target rule: two source games on one match are both refused.

### J2: unescaped names and the team merge

- **Join and alias vetting.** Our stored names go through `html.unescape` before the shared normalization (`our_norm`). CFBD's names are normalized as served. The receipt lists every one of our names that unescape changes.
- In alias vetting the merge does NOT apply. An alias whose target unescapes to the name of two of our team rows names 2 teams and is refused.
- **The v1r stream and the shadow.** Team ids whose unescaped names are IDENTICAL (exact string equality after `html.unescape`, no other normalization) are one team, keyed by the lowest id. This is a mapping applied when the stream is read. The `teams` and `matches` tables are never written. The `ncaa-cfbd-coverage` receipt and the shadow's `fit` receipt list every group and every changed name.
- #79's all-division stream (`load_games` + `build_stream`) is not merged: it stays as declared.

### J3: pinned aliases

`{"App State": "Appalachian State", "Massachusetts": "UMass", "Buffalo": "Buffalo State", "Rice": "Rice Owls"}`.

Direction verified against the file's own `_format` and `load_aliases` / `vet_aliases`: the key is the CFBD name as served (`homeTeam` / `awayTeam`), the value is OUR `teams.name`. That matches the ruling's "left -> right" (CFBD -> ours). On the operator's listing of our names each target names exactly one team (the test pins it): `appalachian state`, `umass` (not `umass dartmouth` or `mass maritime`), `buffalo state`, `rice owls`.

### J4: seasonType

- `ncaa_cfbd_labels.season_type VARCHAR(32) NULL`, added by `migrate_ncaa_cfbd_season_type.py` (additive and idempotent; refuses if the side table does not exist yet).
- Filled from CFBD's `seasonType` exactly as served (`regular`, `postseason`, ...) on the next ingest. NULL when the source sends none.
- Carried on `Game.season_type` as DATA ONLY. No rule reads it: the postseason rule is the architect's to rule after the re-ingest.
- Until the migration runs, `ncaa-cfbd-labels` refuses to write (a `--dry-run` works) and the readers load every other column (`label_load_options`), so `ncaa-backtest`, `ncaa-cfbd-coverage` and the shadow keep working.

### SCOPE: the v1r stream

- `ncaa_backtest.v1r_stream(games, teams)`: the gate's rows (FINISHED, both scores, as `load_games`) that carry a side-table label (`label_source == "cfbd"`), with both team ids mapped through the J2 merge, then #79's `build_stream` (same season filter, exclusions and tie rule).
- A stored game without a label is neither walked nor scored. It is counted per season ("unlabelled, NOT walked, NOT scored").
- The shadow walks this stream (`ncaa_shadow.fit`). The gate harness for v1r is NOT wired into `ncaa-backtest` here: the declaration's split, neutral-site rule and postseason rule come first, by ruling. `ncaa-backtest` still runs #79's all-division stream exactly as declared.

### SCOPE: the coverage fact

- **The fact.** Per season: labelled ÷ CFBD's completed both-FBS games, at least 95% (`fbs_coverage`, `COVERAGE_MIN`), every unlabelled game listed.
- **Before / after.** The 2026-10-07 build's condition divided by every kept game of #79's all-division stream (FCS opponents included). On the synthetic fixture in `tests/test_ncaa_cfbd_scope_join.py` (100 CFBD both-FBS games, 96 labelled, 60 unlabelled non-FBS stream games), it read 96/156 = 61.5% (NO). The ruled denominator reads 96/100 = 96.0% (YES). `label_coverage` stays as #79's information print and no longer carries a 95% verdict.
- **In the ingest receipt.** Every run prints `COVERAGE (SCOPE, ARCHITECT 2026-10-08): labelled J / CFBD completed both-FBS N = x% · >= 95%: YES/NO` (joined over in scope for that run), and lists every unlabelled in-scope game with its reason (unmatched, with any dateshift note; ambiguous; duplicate target; unusable row). The unmatched list is no longer cut at `--limit`.
- **The persisted receipt (Codex on #362).** Every NON-DRY run writes one `ncaa_cfbd_ingest_receipts` row per season, zero joins included, with:
  - season, run time, `fetched_at`, `payload_file`, division, status (`ok` / `empty` / `refused_fields`);
  - records, in-scope count, labelled (joined) count, unmatched count;
  - the in-scope CFBD ids, the joined `[match_id, CFBD id]` pairs, and every unlabelled game with its reason.

  The table is created by `migrate_ncaa_cfbd_ingest_receipts.py`. It is append-only, and a dry run writes nothing. The ingest refuses to write until the table exists.
- **Storage choice: a DB table, not a file.** The host and the laptop each have their own DB, and `exports/` is mirrored and pruned. The receipt belongs beside the side table it describes.
- **Coverage is read from the latest receipt (`stored_coverage`).** `ncaa-cfbd-coverage` and the shadow's precondition read, per season, the latest receipt's labelled / in-scope counts and its unlabelled list. The coverage is NOT met, with the reason printed (law 4), when:
  - the season has no receipt;
  - the latest run's status is not `ok`;
  - the latest run was not `--division fbs`.

  A re-ingest that joins nothing therefore reads 0/N. Before #362 the re-read inferred the latest run from the joined rows, which a zero-join run never touches, so the last good run's coverage kept reading HOLDS.
- **One scope helper (`admitted_labels`, Codex on #362).** A side-table label is a both-FBS label only if its season's latest receipt is an `ok`, division-`fbs` run that joined that exact (match, CFBD id). Three readers use this one set, so they can never disagree:
  - the v1r stream (`v1r_stream`);
  - the shadow's FBS test (`fbs_teams`);
  - the coverage numerator.

  Older rows the ingest keeps (from a `--division ''` run, or a join a later run no longer makes) are excluded from the stream. Each is listed with its reason and never walked. #79's all-division stream still reads every row, as declared.

## Re-ingest (operator, 2026-10-09, from the saved payloads)

1. The `.backup`.
2. `python migrate_ncaa_cfbd_season_type.py`
3. `python migrate_ncaa_cfbd_ingest_receipts.py`
4. Optional preview (writes nothing):
   `python cli.py ncaa-cfbd-labels --year 2025 --from-file exports/cfbd/cfbd_games_2025_20261008T140700Z.json --dry-run`
5. `python cli.py ncaa-cfbd-labels --year 2025 --from-file exports/cfbd/cfbd_games_2025_20261008T140700Z.json --unmatched-names`
6. `python cli.py ncaa-cfbd-labels --year 2026 --from-file exports/cfbd/cfbd_games_2026_20261008T140703Z.json --unmatched-names`
7. `python cli.py ncaa-cfbd-coverage`. Paste the receipts.

`--from-file` already existed (#333): it replays a saved payload with no network and no key, and `payload_file` records the path. Each payload has its own stamp, so it is one year per call (a single `--from-file` for several years must carry `{year}`).


## The ruling (ARCHITECT 2026-10-07, item 6, verbatim)

"#176 PROBE READ (operator console 2026-10-07, scripts/ncaa_source_probe.py --year 2025 --year 2026; CFBD HTTP 200 both years). 2025: 934 records, 808 both-FBS completed, joined 710 (87.9%); labels same 345 / swapped 365 (51.4%); scores agree 700/710 in our orientation, 10 with the two scores reversed; non-neutral home rate source 0.597 (margin +5.23) vs ours 0.445 (-2.67) on the joined games; 64 neutral-site games in the source. 2026: 272 both-FBS completed, joined 264 (97.1%); labels same 264 / swapped 0; scores agree 264/264; home rate 0.654 vs ours 0.663; 6 neutral. FINDING: the provider's 2025 home/away labels are no better than a coin flip and its 2026 labels are sound; CFBD is independent, sane in both seasons, and carries the neutral flag we lack. RULED: CFBD is the NCAA label source of record. (1) A side table keyed by our match id: source game id, orientation (same / swapped), neutral flag, both scores, season; 2025 and 2026. The matches table is never rewritten. (2) The NCAA stream reads orientation, score and neutral from the side table where a row exists and prints the uncovered share per season. (3) The unmatched (98 in 2025, 8 in 2026) are resolved by a PINNED alias map built from the probe's unmatched names; ambiguity is refused, never guessed. (4) The ten 2025 score-reversed rows take the source's scores, each listed with its reason. (5) Nothing from CFBD is committed: payloads stay under exports/ (their terms allow private storage and forbid republishing the data; this repo is public). GATE #79 (frozen 2026-09-30) is unchanged and un-suspends when the side table covers at least 95% of the stream in BOTH seasons and the stream's 2025 non-neutral home rate reads sane on the receipt. Then, in order: ncaa-backtest --baselines-only recorded first; ONE scored run of v1 with its constants untouched, declared beforehand in the registry as ncaa-elo-v1r with the void 2026-09-30 read listed as a prior read. Whether v1r applies home advantage at neutral sites is a declaration question: propose it in the declaration PR, do not choose. The confirmation plan is proposed there too (starting point: the first 100 both-FBS regular-season games after the verdict, frozen by id, the gate's own bar form on the same games)."

Build instruction (architect): "Build: the ingest command (operator-run; key
from .env, never printed), the side table and its migration, the alias map,
the stream read, a coverage receipt per season. No model change in this lane."

## What was built, by ruling point

| Point | Built |
|---|---|
| (1) side table | `ncaa_cfbd_labels` (`NCAACFBDLabel`, `src/db/schema.py`), created by `migrate_ncaa_cfbd_labels.py`. No code path writes `matches`. |
| ingest | `python cli.py ncaa-cfbd-labels --year 2025 --year 2026` (`src/ingestion/ncaa_cfbd.py`). |
| (2) stream read | `src/walters/ncaa_backtest.py` `load_games` / `game_from_rows`; per-season uncovered share on every `ncaa-backtest` run; `ncaa-cfbd-coverage`. |
| (3) alias map | `src/ingestion/ncaa_cfbd_aliases.json`, shipped EMPTY (see "Remaining operator steps"). |
| (4) score-reversed | the side table carries CFBD's scores; every corrected row is listed in the ingest receipt with `correction_reason`. |
| (5) nothing committed | payloads go to `exports/cfbd/` (gitignored); tests use synthetic records only. |

## Operational definitions

**Source and key.** CollegeFootballData `GET /games?year=Y&seasonType=both&classification=fbs`
(the probe's call). With `--division ''` (all classifications) the
`classification` parameter is OMITTED, so the payload is unfiltered at the
source as well as locally (Codex on #333: it used to send
`classification=fbs` regardless; the probe shares `fetch` and gets the same
fix). The key is `CFBD_API_KEY` in `.env`, read through
`config.settings.cfbd_api_key`. It travels only in the `Authorization`
header; it is never printed, logged, saved or stored (a fetch error message
is redacted). It is in the hosting `SECRET_ENV` redaction list.

**Field names (law 1).** Discovered from the first record by the probe's
regexes (`homeTeam`, `awayTeam`, `homePoints`, `awayPoints`, `neutralSite`,
`startDate`; optional `completed`, `seasonType`, `home/awayClassification`,
`id`). A missing required field refuses the season. The discovered names are
printed on every run.

**In scope.** A source game that is completed (or carries no `completed`
field), has both scores, and whose two classifications both equal `--division`
(default `fbs`). This is the probe's "both-FBS completed" count.

**Join key.** Our match id (`matches.id`). Candidates: our matches with
competition code `NCAA` (Sport.NFL family), status not CANCELLED /
STALE_ORPHAN, kickoff within ±12h of CFBD's `startDate` (UTC); ±36h for the
J1 dateshift retry (2026-10-08, above). This is the
shared matcher's window and status rule (`src/ingestion/match_lookup.py`),
restricted to NCAA. Our candidate matches are loaded once per season (no
per-game query).

**Name comparison.** Both sides go through the shared `normalize_team_name`
(our names html-unescaped first: J2, 2026-10-08).
- Tier 1, EXACT: both normalized names are equal to ours.
- Tier 2, SUBSTRING (the shared matcher's last resort): each name contains
  the other. Tier 2 is used only when tier 1 finds nothing.
- Within a tier exactly one (match, orientation) must fit. Two or more fits =
  AMBIGUOUS, REFUSED and listed. The shared matcher's start-time tiebreak is
  NOT used: college teams play no doubleheaders, so two fits are a naming
  collision, not two games.
- Two source games that land on the same match id are ALL refused and listed.

**Orientation.** `same` = CFBD's home team is our `matches.home_team_id`.
`swapped` = CFBD's home team is our `matches.away_team_id`.

**Score orientation (stored).** `ncaa_cfbd_labels.home_score` /
`away_score` are the SOURCE's scores stated in OUR orientation:
`home_score` = the points CFBD reports for our `matches.home_team_id`.
For a `swapped` row, `home_score` = CFBD `awayPoints` and `away_score` =
CFBD `homePoints`.

**Score corrections.** Compared with the matches row (our orientation):
- equal → no reason;
- the two scores reversed → `correction_reason` = `score-reversed: provider
  home/away scores swapped vs CFBD (ours X-Y, CFBD in our orientation Y-X)`;
- any other difference → `score-disagree: provider scores differ from CFBD
  (...)`;
- our row has no score → no reason (counted as "ours unscored"; such a row is
  not in the stream, which takes FINISHED scored rows only).

In every case the side table carries CFBD's scores. Every corrected row is
listed in the receipt.

**Neutral.** CFBD's `neutralSite` as served (`true` / `false`); NULL only if
the source sent null (law 4). It is NOT a derivation of ours.

**Season.** The CFBD `--year` queried, as a string (`"2025"`). When our
match's `season` differs, the row is still written and counted / listed as
"our season differs from the CFBD year" (information).

**Alias map (ruling (3)).** `src/ingestion/ncaa_cfbd_aliases.json`:
`{"aliases": {"CFBD name exactly as served": "our teams.name"}}`.
- An alias is never applied to a source name whose normalized form equals one
  of our NCAA teams' (exact wins); such an entry is reported as `shadowed`.
- An alias whose target normalizes to 0, or to more than 1, of our NCAA teams
  (teams appearing in any NCAA match) is REFUSED and reported. It is never
  applied.
- A usable alias replaces the source name before the join. Rows joined
  through an alias carry `join_via = alias`.
- The map is pinned: there is no flag to load another file.

**Unmatched.** Counted and listed. Each source name in an unmatched game that
has no exact match among our NCAA teams is counted by game
(`--unmatched-names` lists them all). Games whose two names are both known
are a date / missing-game gap, counted apart. Nothing unmatched is guessed.

**Upsert.** By match id: inserted, updated or unchanged (counted). The
ingest never deletes. An earlier row that a later run does not re-join is
kept, and counted in the receipt.

**Payload.** `exports/cfbd/cfbd_games_<year>_<UTC stamp>.json` by default
(`--save-dir` elsewhere). Inside the repository a save directory must be
under `exports/` (gitignored); any other in-repo path is refused, `data/`
included (law 5), and a path outside the repository is accepted. Real paths
are compared (symlinks resolved), so a link into a tracked directory is
refused too (Codex on #333: only `data/` used to be refused, so
`--save-dir src/cfbd` would have put a licensed payload on a tracked path).
The probe's `--save` follows the same rule. The side table's
`payload_file` names it. `--from-file` replays a saved payload. `--dry-run`
writes nothing: no row and no payload.

## The stream (ruling (2))

`ncaa_backtest.load_games` still selects the gate's rows from `matches`
(NCAA, FINISHED, both scores). For each row:
- **With a side-table row** (orientation `same` or `swapped`): the Game's
  home/away teams follow CFBD's orientation, the scores are the side table's
  (flipped with the teams for `swapped`), and `neutral` is CFBD's flag.
  `label_source = "cfbd"`.
- **Without one** (or with an orientation outside the two values): the
  matches row as before; `neutral = None` (unknown).
  `label_source = "matches"`.

The gate's exclusions (pre/postseason, ties) apply afterwards, unchanged.
Neutral-site games stay in the stream. The neutral flag is carried on the
Game as DATA ONLY: no model reads it and no constant or criterion changed.
Whether v1r applies home advantage at neutral sites is the declaration PR's
question (the ruling).

Every `ncaa-backtest` run prints, per season, the side table's coverage of
the kept games and the UNCOVERED share.

## The coverage receipt (`ncaa-cfbd-coverage`)

**Superseded in part 2026-10-08 (SCOPE, above):** the 95% condition is now
labelled ÷ CFBD's completed both-FBS games per season, every unlabelled game
listed. The receipt prints that first, then the v1r stream (labelled games
only, with the J2 merge), then the 2026-10-07 per-stream figures below as #79
information, without a 95% verdict.

Per season (2025, 2026), over the games #79's gate keeps (information):
- stream games, covered, covered share, uncovered share;
- swapped, neutral, score-corrected;
- home win rate on non-neutral covered games (CFBD `neutralSite` false), and
  on all stream games and on uncovered games for reference.

This is a computed fact. The receipt never declares the gate un-suspended:
that, and whether the 2025 non-neutral home rate "reads sane", is the
architect's read.

## Interpretations (chosen where the ruling is silent; open to correction)

1. The join is NCAA-scoped and stricter than the probe's `find_match`: it
   refuses ambiguity instead of applying the start-time tiebreak, and it
   checks both orientations before choosing. Its counts can therefore differ
   slightly from the probe's 710 / 264. The probe keeps its own `compare()`,
   so the 2026-10-07 read stays reproducible.
2. Score disagreements other than a reversal also take CFBD's scores
   (`score-disagree`, listed). The probe saw none.
3. The stored season is the CFBD year queried. A different `matches.season`
   is written anyway and listed.
4. `--dry-run` saves no payload either ("writes nothing").
5. Coverage is measured on the games the gate keeps (after its exclusions).
   The "non-neutral home rate" counts covered games with CFBD
   `neutral = false` only; uncovered games have no flag and are shown apart.
6. The ingest refuses to write until the migration has run (it does not
   create the table itself). "Has run" is the migration MARKER, not the
   table (Codex on #333): `NCAACFBDLabel` is in `Base.metadata`, so any
   `init_db()` (create_all) creates an empty `ncaa_cfbd_labels`. The
   migration alone creates the one-row table `ncaa_cfbd_labels_migration`
   (Core SQL, deliberately unmapped in the ORM, the
   `migrate_kalshi_ticker.py` convention, so create_all can never make it);
   the ingest writes only when table AND marker exist. A `--dry-run` needs
   neither. The repo had no migration-marker convention (no `user_version`,
   no meta table) before this.
   A forced reset clears the marker too (Codex on #333): `drop_db()` (the
   `init-db --force` path) drops `ncaa_cfbd_labels_migration` explicitly,
   because `drop_all()` drops only mapped tables; without it the marker
   survived, `init_db()` recreated an empty side table, and the guard read
   "migrated" for a table the migration never made. After a forced reset the
   ingest refuses again until the migration is re-run. The marker is the only
   unmapped table in the schema (the other `migrate_*.py` add columns or
   indexes to mapped tables, which drop with them).

## Remaining operator steps

1. On the laptop: the `.backup`, then `python migrate_ncaa_cfbd_labels.py`.
2. `python cli.py ncaa-cfbd-labels --year 2025 --year 2026 --dry-run`
   (2 API calls, writes nothing), then
   `python cli.py ncaa-cfbd-labels --year 2025 --year 2026 --unmatched-names`.
   The second run writes the side table, saves the payloads under
   `exports/cfbd/` and lists EVERY unmatched source name with its count.
   Paste the receipt.
3. Aliases are proposed from that list and pinned in
   `src/ingestion/ncaa_cfbd_aliases.json` in a REVIEWED PR. The map ships
   empty: the probe's unmatched names were not available to this build.
4. After that PR merges, re-join from the saved payloads (no API call), one
   year at a time because each payload has its own stamp:
   `python cli.py ncaa-cfbd-labels --year 2025 --from-file exports/cfbd/cfbd_games_2025_<stamp>.json`,
   then the same for 2026.
5. `python cli.py ncaa-cfbd-coverage`. Paste the receipt.
6. The gate stays SUSPENDED until the architect reads the coverage receipt.
   The order after that is the ruling's: `ncaa-backtest --baselines-only`
   recorded first, then the `ncaa-elo-v1r` declaration PR.
