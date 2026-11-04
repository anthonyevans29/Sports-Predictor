# nfl-elo-v2's rehearsal arm: the export contract

The rulings: ARCHITECT 2026-11-03 09:00 ET, addendum 230 item 1(a), as ruled by ARCHITECT 2026-11-04 09:55 ET, addendum
247 items 2-3 (where 230's map and 247 differ, 247 wins), and #825's four points as ruled by ARCHITECT 2026-11-04 11:50
ET, addendum 251 item 3. Lane nfl-v2, the step due 11-23. Code:
`src/walters/nfl_rehearsal.py`. Tests: `tests/test_nfl_rehearsal_arm.py`. Gate-class (an export contract); no model
change, and no constant, bar, gate threshold, roadmap date or registry value moves.

Addendum 230 item 1(a), verbatim:

> (a) nfl-v2's REHEARSAL (lane nfl-v2, the 11-23 step: "on PASS: the rehearsal on the host's pages from the next
> tag, weeks 10 and 11, 11-12 through 11-23") — PR BY 11-09, on a tag by 11-11: nfl_elo_v2's probabilities as a
> SECOND ARM on the NFL slate and closing pages beside v1's record-only would-be (the pl-availability shadow's
> shape: two probability sets, the grader's second arm, the arm labelled with the entry and its verdict stamp),
> written only while the entry's verdict reads PASS and its rehearsal window is open (registry state 'rehearsal',
> 11-12 to 11-23); the Desk reads nothing from it (market-only stands until my live ruling of 11-26); the results
> export carries both arms' log-loss against the close and Brier per week; a FAIL on 11-06 leaves every line of it
> dormant. Gate-class (an export contract): the PR body shows a synthetic page with both arms and the pin that the
> Desk's call never reads the second arm.

Addendum 247 items 2-3, verbatim:

> 2. THE REHEARSAL ARM (230 item 1(a)), the six, RULED:
>
> (1) WHO WRITES THE STATE, AND THE INSTANTS: after Friday's run, Code's verdict-record PR (the one that writes the
> run record and verdict into the entry, by my verdict addendum) ALSO writes, on PASS only, `status: "rehearsal"`
> and `rehearsal_window: {"opens_at": "2026-11-12T00:00:00Z", "closes_at": "2026-11-24T06:00:00Z"}` — week 10's
> Thursday through week 11's Monday night INCLUDED (the MNF of 11-23 ET kicks off 2026-11-24T01:15Z and is week 11's
> last game; 215's "11-12 through 11-23" is ET dates). On FAIL nothing is written and the arm is dormant for the
> season. The shape the code reads is exactly that; a test pins it.
>
> (2) THE COMPARE: a SEPARATE key prefix `rehearsal_*` (rehearsal_version, rehearsal_probabilities,
> rehearsal_reason…), host-only, masked by compare_exports.py under its own line "rehearsal-arm keys (host-only,
> nfl-elo-v2)" beside the pl-availability line — #735's pattern, in the SAME PR (a compare that would fail the tag
> on its own arm is a defect, not a question). Never the `candidate_*` keys: those are pl-availability-v1's line and
> its count.
>
> (3) WHAT OPENS THE WINDOW PER ROW: the GAME'S KICKOFF inside the window (as recommended); a row written before the
> window for a game inside it carries the arm; a row for a game outside it never does, whenever written.
>
> (4) AFTER THE WINDOW CLOSES: the export STOPS WRITING the arm (no new rows) but the results export KEEPS READING
> every stored arm row — the 11-24 dry read reads them. Written once, read for the record always.
>
> (5) TIES: each figure keeps the rule it already has, stated on its line — the log-loss treats a tie as the gate's
> protocol does (walk_protocol's own rule, unchanged: the rehearsal's log-loss must be the gate's arithmetic), the
> W-L-P and the vs-close figure treat a tie as a push, as results-tally does. "Per week" = the NFL game week as
> nfl_predict assigns it (weeks 10 and 11), never the calendar week.
>
> (6) THE LIVE WALK: the same games as nfl_elo_v1's live walk (2024 to date, every non-preseason FINISHED game, in
> order), with the declared term for the whole walk — the gate's walk continued into 2026, so the arm's 2025
> probabilities EQUAL the gate run's scored 2025 probabilities game for game: a parity test pins it (the gate's run
> record will hold them after Friday; before that, the test walks the synthetic stream both ways). Never the gate's
> cold start re-run on the host.
>
> 3. The Desk reads nothing from the arm (a byte-identical pin, as planned); the arm labels every row with the entry
> id, the term and "rehearsal — not a call"; the phone page carries no arm line (the summary block and receipt do,
> as 223 item 3 ruled for the would-be line).

Addendum 251 item 3, verbatim:

> 3. #825 (the rehearsal arm) — the four points, RULED:
>
> (1) POST-FRIDAY PARITY: the gate stays UNCHANGED — no per-game dump is added before Friday's one run. The
> post-Friday pin is the run record's own figures: the arm's live walk over the sidecar's scored ids (registry
> IDS_DIR, sha256-checked) reproduces the record's `log_loss` to its stored precision and every band's `stated` and
> `realized` means to the record's six places; with 285 warm-up and the scored set that pins the probabilities to any
> divergence a reader could care about. Per-game equality stays pinned on the synthetic stream both ways, as the PR
> already does. The test reads the record after the verdict PR lands and is skipped (named, with the reason) until the
> record exists; a skip is never silent.
>
> (2) THE VERDICT-RECORD PR carries the five status-aware places with `rehearsal` added and a test over the enum;
> #825's body names that dependency and the arm stays dormant until the record reads PASS and `status: "rehearsal"`.
> #825 does not pre-empt it.
>
> (3) THE WALK'S FLOOR: the arm's live walk takes an EXPLICIT floor at the gate's warm-up season (`nb.WARMUP_SEASON`,
> 2024), pinned by a test in which a stored pre-2024 FINISHED NFL game does not enter the arm's walk and is counted on
> the export's summary line ("walk floor 2024; N stored games before it, excluded"). v1's own walk is NOT changed in
> this lane (the live row's walk is a v1 question, 230's scope); a pre-2024 finished NFL game appearing in the DB is a
> data event with its own Issue, never a silent inclusion.
>
> (4) THE TIE RULE: agreed — pinned by text (the test reads the gate's source and asserts the expression) and by
> value; no refactor of frozen gate code before Friday's run. A refactor to one shared function after the run is
> optional, its own small PR, and must leave the gate's bytes-as-run reproducible from the tag.
>
> THE CODEX P1 (rounding): the fix is right and is round 1 — the arm stores full precision and rounds only where it is
> shown (the slate and closing rows, the results row, the summary line, the receipt); the new test fails on the
> current code and passes on the fix. v1's four-place storage (nfl_predict.py:139) is UNCHANGED: it is the live row
> and this lane does not touch it. The weekly comparison line names the precision on its own line ("v2 at full
> precision as stored; v1 at four places as stored; the difference is bounded at about 1e-4 of log-loss") — immaterial
> against the 0.010 bar and the 7.0pp band, and stated so no reader mistakes it for a divergence.

## 1. The state read (247 item 2(1)), never written here

The registry is `registry.LEDGER`, read at call time by `nfl_rehearsal.read_gate`, which never raises. The arm is ON
only when ALL of these hold. Any other reading is DORMANT, with its reason (law 4).

1. The machine is the host: `desk_policy.not_host_reason()` is None. This is pl-availability-v1's host-only gate.
2. The entry `nfl-elo-v2` exists, and the ARCHITECT's verdict reads PASS: `entry["verdict"]["verdict"] == "PASS"`,
   with a non-empty `verdict.at` (the verdict stamp). This is the record `registry.record_verdict` writes; the gate's
   computed `run.result.verdict` text is never read.
3. `entry["status"] == "rehearsal"`.
4. `entry["rehearsal_window"]` is exactly `{"opens_at": "<instant>Z", "closes_at": "<instant>Z"}`: a dict with those
   two keys and no other, each a string ending in `Z` that `pl_availability.parse_instant` reads, with `opens_at`
   strictly before `closes_at`. 247's ruled values are `{"opens_at": "2026-11-12T00:00:00Z", "closes_at":
   "2026-11-24T06:00:00Z"}`. The code READS them from the entry and holds no default. A test pins the shape and the
   instants, and that a different window in the entry is the one followed.
5. The declared term and the frozen constants price. `nfl_v2_gate.declared_term` accepts exactly one form with a valid
   value (main holds home advantage 33.0 since #822), and `nfl_v2_gate.declared_constants` finds the entry's constants
   equal to `NFLEloConfig()`'s.

Each dormant reading is pinned by a test:

- no entry, or an unreadable registry;
- a null, FAIL or REJECT verdict, or a verdict not in the record's shape;
- a PASS without `verdict.at`;
- a PASS with status `confirming` (record_verdict's PASS status), `run`, `declared` or anything else;
- the window absent or null, missing a key or carrying an extra one;
- a window instant that is a date, carries no `Z`, carries `+00:00`, or is not a string;
- `opens_at` at or after `closes_at`;
- off the host.

A dormant reading writes nothing: no stored arm, no key on any row, no record block. Predict-nfl's rows and the slate,
closing and results files are what the code before this module writes; a test compares them with this module's writers
stubbed out. On FAIL nothing is written to the registry (247 item 2(1)), so every line stays dormant for the season.

**Who writes the state:** the verdict-record PR after Friday's run, on PASS only (247 item 2(1)). This PR writes no
registry field. The real registry reads dormant today (status `declared`, verdict null).

## 2. Per game: the kickoff (247 item 2(3))

The arm covers a game when its stored kickoff (`matches.utc_date`, naive UTC) is in `[opens_at, closes_at)`: `opens_at`
included, `closes_at` excluded. The write clock is never read. A row written before the window for a game inside it
carries the arm; a game outside it never does, whenever written. With 247's instants the week-11 MNF
(2026-11-24T01:15Z) is inside, and a kickoff at 2026-11-24T06:00:00Z is outside.

## 3. The stored arm (predict-nfl; 247 item 2(6))

For a covered game, predict-nfl prices nfl_elo_v2 by v1's own live walk, then `_expected_home`:

- The walk is `nfl_predict._current_ratings`, which now takes `cfg`: every stored FINISHED non-preseason NFL game with
  both scores, by kickoff then id. v1 is unchanged when `cfg` is None.
- THE WALK'S FLOOR (251 item 3(3)): the arm's walk also passes `floor=nfl_rehearsal.WALK_FLOOR`, which is
  `nfl_backtest.WARMUP_SEASON` (2024), the gate's warm-up season, imported and never a literal. A stored game of an
  earlier season (its season read as a year; a season that does not read as one is treated as earlier, law 4) is left
  out of the arm's walk and counted into the run's receipt. v1's walk passes no floor and is unchanged: the live row's
  walk is a v1 question, 230's scope. A pre-2024 FINISHED NFL game in the DB is a data event with its own Issue, never
  a silent inclusion; the count on the arm line is where it shows.
- The config is `nfl_v2_gate.candidate`'s, for the WHOLE walk: a home advantage applies to price and update; a shrink
  applies to the price only.
- One extra walk per run, only while the state reads on.
- Never the gate's cold start re-run. The gate's walk continued into 2026, so the arm's 2025 probabilities equal the
  gate's scored 2025 ones game for game. A test pins this on the synthetic stream, walked both ways: `walk_protocol`
  with a recording price hook, and the live walk recording its pre-update expectation.

The arm is stored on v1's own Prediction row as `factor_breakdown["nfl_elo_v2_rehearsal"]`: `{version: "nfl-elo-v2",
model_version: "nfl_elo_v2", p_home, p_away (full precision), term: {form, value}, verdict: "PASS",
verdict_at}`. One row, one close and one outcome sit under both arms, and v1's fields are written exactly as before. A
failed second walk stores `{version, model_version, term, verdict, verdict_at, error}`, and v1's row is still written.

The stored arm is FULL precision, the walk's own float, because it is the copy the grader scores (Codex on #825): the
pages and the results row round it to four places where they present it, and nothing that grades reads a rounded copy.
v1's own `home_win_prob` is stored at four places (nfl_predict's `round(p_home, 4)`, pre-existing and unchanged), so the
two arms' figures compare v2 at full precision with v1 at its stored four places. 251 item 3 ruled the fix right (round
1) and v1's four-place storage unchanged (it is the live row; this lane does not touch it), and the record block names
the precision on its own line, verbatim: "v2 at full precision as stored; v1 at four places as stored; the difference
is bounded at about 1e-4 of log-loss" (section 5).

While the state reads on, the predict run prints one receipt line:

```
rehearsal arm nfl-elo-v2 (<stamp>, <form> <value>): N of M covered rows priced (kickoff window <opens_at> to
<closes_at>, closes_at excluded); walk floor 2024; K stored games before it, excluded; rehearsal — not a call
```

The floor clause is 251 item 3(3)'s line, verbatim: "walk floor 2024; N stored games before it, excluded", with the
year rendered from `WALK_FLOOR` and the count from the walk itself (K: the stored FINISHED non-preseason NFL games
before the floor). It sits on the arm's own receipt line because the arm's walk runs in predict-nfl; the export reads
the stored arm and walks nothing for it.

## 4. The pages (export-nfl-predictions; 247 items 2(2), 3)

This covers the slate file and the closing run's file, which come from the same function. On the host, a row whose
kickoff the window covers (with the state on) gains six flat keys, outside `prediction`:

| key | value |
|---|---|
| `rehearsal_version` | `"nfl-elo-v2"` (the entry id) |
| `rehearsal_probabilities` | `{home_win, away_win}` from the stored arm, presented at four places, or null |
| `rehearsal_term` | `{form, value}` read from the entry (`home_advantage`, `33.0`) |
| `rehearsal_verdict_stamp` | `"nfl-elo-v2 PASS <verdict.at>"` |
| `rehearsal_label` | `"rehearsal — not a call"` |
| `rehearsal_reason` | null, or why there are no probabilities: no stored arm, a failed walk, or a stored arm carrying another stamp or term (never relabelled) |

The keys are absent on every other row and off the host, so a dormant file is byte-identical. They are never the
`candidate_*` keys, which are pl-availability-v1's. After the window closes the export writes no new arm row, because no
covered game is upcoming. The file's top-level `rehearsal: false` (a fossil the Cockpit reads) is untouched.

## 5. The grader's second arm (export-nfl-results; 247 items 2(4), 2(5))

On the host, every results row whose prediction STORES the arm carries `rehearsal_arm`, whatever the registry reads
now. Written once, read for the record always: the 11-24 dry read reads them. The row's arm is `{version,
model_version, term, verdict_stamp, label, p_home, home_win_prob, away_win_prob, top_pick, top_pick_hit, push,
log_loss, brier_score, reason}`. `p_home` is the stored arm's full-precision probability, the one the row's top pick,
log_loss and brier_score and the record's figures are computed from; `home_win_prob` and `away_win_prob` present it at
four places, as v1's `predicted` block does. Each log-loss and Brier is computed unrounded and rounded to four places
on output only.

When any live row carries the arm, the season record carries `record.rehearsal_arm`: `{version, label, ruling,
verdict_stamps, terms, rules, unpriced_arm_rows, redated_arm_rows, total, by_week}`. `total` and each
`by_week[<week>]` are `{games, v1: F, v2: F}`, over the same games (the live, non-re-dated rows carrying a priced
arm), with `F = {model_version, log_loss, brier_score, w, l, p, vs_close}`. Each figure keeps its own tie rule, stated
on its line in `rules`:

- `log_loss` is the frozen gate's arithmetic (`nfl_backtest.walk_protocol`, unchanged). Per game it is `-(y ln p +
  (1 - y) ln(1 - p))`, with p floored at 1e-12 and y = 1 for a home win, else 0: a tie counts as a home loss. The mean
  is accumulated as the gate accumulates it (`+=` in order, one division: `mean_as_the_gate`), and a test pins it equal
  to `walk_protocol`'s own `ll_model` to the bit on the synthetic stream. `walk_protocol`'s rule is inline in its scored
  pass, not a function, so `nfl_rehearsal.game_log_loss` is the same expression, and a test pins both lines' text.
- `brier_score` is `(p - y)^2`, two-way, on the same y: a tie counts as a home loss.
- `w`, `l`, `p` are the top pick's W-L-P (home when p >= 0.5): a tie is a push, as results-tally does.
- `vs_close` is `vs_close.block` over the decided games with a close (the row's graded close): a tie is a push and out.
- Per week is the NFL game week as nfl_predict assigns it (the row's `week`, `matches.matchday`), never the calendar
  week.
- The precision, on its own line (`rules.precision`, 251 item 3, verbatim): "v2 at full precision as stored; v1 at four
  places as stored; the difference is bounded at about 1e-4 of log-loss". It is immaterial against the 0.010 bar and
  the 7.0pp band, and stated so no reader mistakes it for a divergence.

Off the host nothing is read or written (host-only).

## 6. The Desk reads nothing; one line in the summary and the receipt, none on the phone page (247 item 3)

`desk_policy.normalize` reads named fields only, none of them `rehearsal_*`. A test pins these byte for byte across
three docs (bare, armed, and loud: the arm flipped to the extremes), on the host's own export and on the market-only
battery:

- `desk_meta` and every row's `desk` block;
- `closing.desk_rows`, with `would_be_for`;
- `exec_cohorts.would_be_play`;
- `closing.page_text`, the phone page.

No Desk code names the keys. A source scan covers desk_policy, exec_cohorts and desk_unit, and closing's desk_rows,
would_be_for, page_text, slate_page_text, slate_calls and call_text.

The line is placed as addendum 223 item 3 placed the would-be line. The closing run reads the arm with
`closing.rehearsal_arms`, BESIDE `desk_rows` and never inside it:

- The summary block prints one line for an armed row: `rehearsal arm nfl-elo-v2 (home_advantage 33.0) · <home> <p> /
  <away> <p> · nfl-elo-v2 PASS <verdict.at> · rehearsal — not a call`.
- The run receipt's desk row carries `rehearsal_arm`: `{version, probabilities, term, verdict_stamp, label, reason}`.
- The phone page's text carries no arm line.

## 7. The compare (247 item 2(2))

`deploy/hosting/compare_exports.py` treats every key starting `rehearsal_`, at any depth, as "rehearsal-arm keys
(host-only, nfl-elo-v2)". That covers the six row keys and the results row's and the record's `rehearsal_arm`. These
keys are never compared and never printed (`<masked>` in a mismatch printed whole). They are counted per file pair on
their own line, right after the pl-availability line: `rehearsal-arm keys (host-only, nfl-elo-v2): N`. The count is 6
per armed slate or closing row, 1 per armed results row, and 1 for the record block.

The pl-availability line and its count are unchanged, and the top-level `rehearsal` is compared as before. No other
writer of a compared export uses the prefix (law 1, read on main 2026-11-04).

## 8. After Friday: the parity, the dependency (251 items 3(1), 3(2))

**The post-Friday parity (251 item 3(1)).** The gate stays unchanged: no per-game dump is added before Friday's one
run. The gate's run record (`nfl_v2_gate.result_record`, in the entry's `run.result`) holds `ll_model` unrounded (the
record's log-loss: result_record keeps walk_protocol's key) and the bands with `stated` and `realized` rounded to six
places; the scored ids are the sidecar `docs/registry/ids/nfl-elo-v2.txt` under `registry.IDS_DIR`, with the record's
`n_scored` and `ids_sha256`. The pin is the record's own figures:

- `nfl_rehearsal.scored_ids(entry, ids_dir)` reads the sidecar and checks its count and sha256 (`registry._ids_sha`,
  the hash `record_run` wrote), or refuses (`ParityRefused`).
- `nfl_rehearsal.walk(games, cfg, price_map, floor)` is the arm's live walk on a stream, pure: the floor applied, the
  declared term for the whole walk. A test pins its final state equal to `nfl_predict._current_ratings(cfg=...,
  floor=WALK_FLOOR)` on the synthetic store, a stored 2023 game counted and excluded by both.
- `nfl_rehearsal.parity(games, ids, result, cfg, price_map)` walks it over the scored ids and compares the log-loss
  (`game_log_loss`, accumulated as `mean_as_the_gate`) with `ll_model` to its stored precision (every digit of a
  full-precision float), and each band (walk_protocol's index and its `sum() / n` means) by n, `stated` and
  `realized` to six places.
- On the synthetic stream the real writers make the record (walk_protocol on `load_stream`'s split, `result_record`,
  `registry.record_run` into a tmp registry): the parity passes, and it names a mismatch for a walk without the floor,
  a record one unit off in its last place, a band off by 1e-6, a dropped id, and a sidecar off its sha256.
- The real-record test reads nfl-elo-v2's entry in docs/registry/experiments.json. It is SKIPPED, with a named reason
  asserted by a test (`parity_skip`), while the entry's run is null: "nfl-elo-v2's run record does not exist yet
  (Friday 11-06's one run; the verdict-record PR lands it) — addendum 251 item 3(1)". Once the record exists, what
  needs no database runs everywhere, CI included: the sidecar's count and sha256 against the record (`scored_ids`) and
  the record's shape (`record_shape`: `ll_model` a finite number; each band's `band` and `n` ints, `stated` and
  `realized` at six places). A sidecar off its sha256 or a record off that shape FAILS. Only the walk is then skipped
  without a database, with its own named reason; given `SP_REHEARSAL_PARITY_DB`, a fresh .backup copy outside data/
  (`nfl_v2_gate.check_db`'s fence, opened read-only), it walks the copy's stream and must pass. CI sets no
  `SP_REHEARSAL_PARITY_DB`, so the DB-backed walk is a manual run on a .backup copy (see the PR's "For the architect").
- A skip is never silent on CI's own path: CI runs `python -m pytest -q tests` with no `-rs`, and pytest's default
  report omits skip reasons. The test therefore warns each named reason (`nfl_rehearsal.ParitySkipped`, a
  UserWarning) beside its `pytest.skip`, and a plain `-q` run prints it in its warnings summary.
- Per-game equality stays pinned on the synthetic stream, walked both ways (section 3).

**The dependency (251 item 3(2)).** The verdict-record PR after Friday's run carries the five status-aware places with
`rehearsal` added and a test over the enum. This PR does not pre-empt it and changes none of them:

- `registry.record_verdict` writes `confirming` on a PASS.
- `registry.record_confirmation` reads `confirming`.
- `deploy/hosting/coverage_map.py` names a disagreement when a roadmap lane reads `confirming` and its entry does not.
- `src/roadmap.py` STATES has no `rehearsal`.
- `tests/test_leagues_declaration_220.py` pins every real entry's status to declared, run, confirming, closed or
  production.

The arm stays dormant until the record reads PASS and `status: "rehearsal"` (section 1).

**The tie rule (251 item 3(4)).** `walk_protocol`'s rule is inline in the frozen function. It is pinned by text (a
test reads the gate's source and asserts the outcome, the per-game log-loss, the floor, the band index and the band
means) and by value (walk_protocol scores a one-game stream, a tie among the cases, and `game_log_loss` on `gate_y`
gives its `ll_model` to the bit). The frozen gate's code is not refactored before Friday's run; a refactor to one shared
function after the run is optional, its own small PR, and must leave the gate's bytes-as-run reproducible from the tag.
