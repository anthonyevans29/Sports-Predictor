# PL Weekly Routine (S5)

The Premier League is weekend-clustered, not daily. Three touchpoints per
matchweek, coexisting with the MLB daily chain (which is unchanged). Written
2026-08-20 from the dress rehearsal; amend from practice, not theory.

---

## STEP ZERO — every session that follows a Claude build day
Re-extract the latest tarball BEFORE running anything
(`cd ~/Downloads && tar -xzf sports_predictor.tar.gz`). The 2026-08-20
dress rehearsal ran on stale code and shipped an export missing two
input_quality fields — caught only because the missing keys were compared
against the packaged source. Extraction preserves venv/ and the DB.

## FRIDAY — pre-matchweek run (~afternoon UK time)

```
python cli.py sync-matches --competition PL --season "2026/27"
python cli.py sync-odds    --competition PL --season "2026/27"
python cli.py sync-injuries --competition PL --season "2026/27"
python cli.py sync-kalshi-soccer
python cli.py predict --sport soccer --competition PL --season "2026/27"
python cli.py export-predictions --sport soccer --competition PL \
    --start <SAT-date> --end <MON-date+1> --status scheduled
```

Notes:
* `sync-matches` first: catches postponements/rearrangements before anything
  prices against a stale kickoff (the Kalshi time gate depends on utc_date).
* Export window: Saturday through Monday inclusive (`--end` is exclusive-ish
  bound; use the day AFTER the last fixture). Midweek rounds get their own
  Tue–Thu window run.
* Read the sync-kalshi-soccer summary: `wide-spread skipped` should be LOW for
  in-window games by Friday (spreads tighten near kickoff); a high in-window
  skip count means thin liquidity — the export's kalshi column will show
  `partial`/`absent` accordingly.
* Hand the export to the GPT layer WITH the standing consumer notes:
  (1) positive model-vs-market edges in soccer are historically
  anti-predictive (two-season verdict) — market-is-right is the default
  reading; (2) `strengths_backfilled: true` means "matches" = last season —
  the model is blind to summer until current-season games accumulate;
  (3) `lineups: "none"` — v1 has no starting-XI information. INJURIES are
  different: they DO feed the model (xG adjustment in factor_breakdown,
  names/counts in the injuries block) — hence the sync-injuries step in this
  chain; run it every time or the adjustment silently uses stale data.
  Freshness stamp: injuries_synced_at now ships in input_quality (added
  2026-08-25).
  (3b) promoted_this_season (added 2026-08-27): season-long cohort flag for
  Coventry/Hull that SURVIVES their graduation off the prior —
  new_to_league reflects only the current strengths source and went false
  after MW1. Consumers keep promoted-club caution keyed on
  promoted_this_season. Registry is season-keyed in export.py and expires
  automatically at season rollover; add next season's promoted set each
  August.

## SATURDAY — pre-kickoff refresh (~2h before first kickoff)

```
python cli.py sync-matches --competition PL --season "2026/27"
python cli.py sync-odds    --competition PL --season "2026/27"
python cli.py sync-injuries --competition PL --season "2026/27"
python cli.py sync-kalshi-soccer
python cli.py predict --sport soccer --competition PL --season "2026/27"
python cli.py export-predictions --sport soccer --competition PL \
    --start <SAT-date> --end <MON-date+1> --status scheduled
```

Notes:
* Full chain INCLUDING the fixture sync — do not trim it for speed. It is
  the only step that flips already-played games (e.g. a Friday fixture
  inside the export window) to finished so the status filter drops them;
  without it, stale pre-match rows for played games leak into the export as
  "scheduled". It also catches kickoff changes and postponements — exactly
  Saturday-morning news. (Amended 2026-08-22 from practice: user caught the
  omission before it shipped a stale Arsenal row.) This capture is the de-facto
  "closing-ish" book price for CLV grading — do not skip it.
* The in-play gate makes a mid-slate re-run safe (started games are refused,
  their last pre-kickoff capture stands), but the standard routine is one
  run before the 12:30 kickoff.
* Predictions for already-started games are frozen by status; that is
  expected, same as MLB's 2:20 games.

## MORNING AFTER THE FINAL MATCHWEEK FIXTURE — grading + weekly refresh
(usually Monday; a Monday-night fixture pushes this to Tuesday. Interim
matchday mornings run the same chain WITHOUT soccer-refresh to grade the
previous day's games: sync-matches -> evaluate -> export-results.)

```
python cli.py evaluate --sport soccer
python cli.py export-results --sport soccer --competition PL
python cli.py soccer-refresh
```

Notes:
* Order matters: grade first (refresh calls evaluate too, but the results
  export should exist before any promotion changes model version strings in
  later exports).
* `soccer-refresh` is the S6 sanity-gated state refresh: expect data-growth,
  config-inheritance, Elo-health and drift lines, then promote/reject with a
  reason. A REJECTION is a stop-and-investigate, not a retry.
* First few Mondays: eyeball the drift line — the 80-pt default has seen only
  synthetic corruption; real matchweeks calibrate it.
* Ledgers that accrue from the results file: promoted_default cohort
  (strengths_source), 70-90% home band vs actual, pick-edge sign buckets
  (the thermometer verdict's forward test), Kalshi three-way coverage.

## Midweek rounds / cup weeks

Same Friday/matchday/Monday shape shifted to Tue–Thu. Cup competitions are
OUT OF SCOPE (PL-only guard in the backlog) — the sync commands are
PL-filtered and stay that way until PL discipline is proven.

## What is deliberately NOT in this routine

* No totals anywhere (S8: totals_available=false until a goals pulse exists).
* No lineup/team-news ingestion (S7: exported as lineups:"none"; Stage-1
  candidate post-launch).
* No config changes: those go through the market-scored backtest +
  set-soccer-config, never through the weekly refresh.
