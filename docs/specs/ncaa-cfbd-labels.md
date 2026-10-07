# NCAA CFBD label lane (#176 probe read) — DATA LANE

**Status: BUILT 2026-10-07, not yet run on the laptop.** No model change. GATE
#79 (frozen 2026-09-30) is unchanged and stays SUSPENDED-PENDING-DATA until
the architect reads the coverage receipt.

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
STALE_ORPHAN, kickoff within ±12h of CFBD's `startDate` (UTC). This is the
shared matcher's window and status rule (`src/ingestion/match_lookup.py`),
restricted to NCAA. Our candidate matches are loaded once per season (no
per-game query).

**Name comparison.** Both sides go through the shared `normalize_team_name`.
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
(`--save-dir` elsewhere; anything under `data/` is refused). The side table's
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

Per season (2025, 2026), over the games the gate keeps:
- stream games, covered, covered share, uncovered share;
- swapped, neutral, score-corrected;
- home win rate on non-neutral covered games (CFBD `neutralSite` false), and
  on all stream games and on uncovered games for reference;
- `coverage >= 95%: YES/NO` per season, and whether it holds in BOTH.

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
