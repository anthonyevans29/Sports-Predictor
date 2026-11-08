"""The chain definitions the host runs — the ONE place commands live.

Every step is `python cli.py <argv>` verbatim from docs/CLI.md and
docs/pl_weekly_routine.md, with options made explicit. tests/test_hosting_pack.py
checks every command and every option against cli.py's click definitions
(law 1), so a guessed flag (the H0 D1 `sync-matches --date` class) fails CI.

Placeholders, computed in UTC by sp_run: {today} {yesterday} {tomorrow}
{sat} (the coming Saturday, today if Saturday) {sat_plus3} (the Tuesday
after: pl_weekly_routine's "--end <MON-date+1>"). Since ARCHITECT addendum 166
item 6(B) no chain step names {sat}/{sat_plus3}: the soccer-prematch export that
priced that window is retired, and the closing watch's slate stage computes the
same window itself (closing.soccer_window, from sp_run.date_vars).

backup: "daily"      -> today's verified daily backup must exist, else one is
                        taken first; a failed backup fails the chain.
        "prerefresh" -> a fresh prerefresh backup is ALWAYS taken first (law 5:
                        mandatory before any soccer-refresh). Enforced here,
                        so it holds however the chain is started.
"""
from __future__ import annotations

MLB = ("--competition", "MLB", "--season", "2026")
PL = ("--competition", "PL", "--season", "2026/27")
# soccer-expansion-v1 (ARCHITECT 2026-10-07): PD, SA, BL1, FL1, ELC current season, DATA ONLY (sync-matches /
# sync-odds) on the soccer chains, laptop and host. No predict. THE SHADOW EXPORT (ARCHITECT 2026-10-30 12:45 ET,
# addendum 185 D2, verbatim in part: "THE EXPORT RUNS AS THE LAST STEP OF EVERY EXISTING SOCCER SYNC CHAIN
# (soccer-friday 14:00Z, soccer-saturday 10:30 London, soccer-morning-after Sun/Mon/Tue 09:50Z, and intl-daily's tail
# only if a league sync precedes it there — it does not, so not intl-daily) [...] No new timer, no daily league
# sync"): SHADOW_EXPORT_STEP, bare, is the last step of soccer-prematch (sp-soccer-friday and sp-soccer-saturday) and,
# after every sync, of soccer-morning-after but for the host's results-tally after it (HOST_TALLY_STEP, addendum 230
# item 2(b): "as the last step of soccer-morning-after"). Bare: no --competition (it binds its own leagues from the registry: PD and each declared one
# of the four, R5) and no --hours (its window runs to the next of those three timers' fires plus
# soccer_expansion.EXPORT_WINDOW_MARGIN, 2 h, so it reaches the next chain's export step: soccer_expansion.
# next_chain_run; ARCHITECT 2026-10-30 14:50 ET, addendum 188 item 4; each run writes its own new file, never a row
# rewritten). sp_run runs these chains on the host (the systemd timers); the command itself refuses on any other
# machine (addendum 178 R6).
EXPANSION_CODES = ("PD", "SA", "BL1", "FL1", "ELC")
EXPANSION = [("--competition", c, "--season", "2026/27") for c in EXPANSION_CODES]
SHADOW_EXPORT_STEP = ["export-soccer-expansion-shadow"]
# Kalshi series PINNED (ARCHITECT 2026-10-07, addendum 2): "A pinned series never makes a league live." Their
# sync-kalshi-soccer runs on the shadow chain (soccer-prematch) as CAPTURE ONLY, and since ARCHITECT 2026-10-24,
# addendum 164 item 2(a), on the hourly window chain too (WINDOW_KALSHI_CAPTURE_ONLY, below). They are deliberately
# NOT in WINDOW_KALSHI: the window card spans every competition, and a capture-only league adds no venue line to it.
KALSHI_CAPTURE_ONLY = EXPANSION_CODES
# ncaa-schedule's forward window in days past today (ARCHITECT 2026-10-09: "the next seven days")
NCAA_FORWARD_DAYS = 7
# ncaa-schedule's last step (ARCHITECT 2026-11-03, addendum 230 item 1(b)): the v2 college shadow, dormant (exit 0,
# nothing written) while the registry records no verdict or a verdict other than PASS for ncaa-elo-v2
NCAA_SHADOW_STEP = ["export-ncaa-predictions", "--id", "ncaa-elo-v2", "--dormant-ok"]
# weekly-fullseason's last step (ARCHITECT 2026-11-03 17:40 ET, addendum 240 item 4(b)): the host's one CFBD read a
# week, METERED (not in UNMETERED), its failure receipted and paged as a sync-step failure that stops nothing after it
# (the chain's `go_on`, CFBD_GO_ON)
NCAA_CFBD_STEP = ["ncaa-cfbd-labels", "--year", "2026"]
CFBD_GO_ON = ("addendum 240 item 4(b): the weekly CFBD read's failure is a sync-step failure that stops nothing "
              "after it")

# THE AVAILABILITY RECORD'S DAILY READ (ARCHITECT 2026-11-04 13:05 ET, addendum 252 item 3(a), verbatim in part: "One
# fetch a day on the host after nflverse's ~07:00 UTC load (a new chain `availability-daily`, timer 08:45 UTC, inside no
# other chain; UNMETERED; failure receipted and paged as a sync-step failure, stopping nothing)"; addendum 259 item
# 2(d): "THE TIMER: 08:45Z daily stands"). One step, the season's release file (github.com, never api-sports:
# UNMETERED). `go_on` names it (the weekly CFBD read's form, addendum 240 item 4(b)): a failed read is receipted
# (`continued`: AVAILABILITY_GO_ON), the chain's exit is its exit, so OnFailure pages, and no later step exists to stop.
# No backup key: the step appends to the record's two tables only, and the daily backup (sp-backup, 09:30 UTC; intl-daily
# at 07:20 UTC takes it first) stands as it is. The season is explicit, as every chain's is ("2026"), and moves with them.
# A TRANSIENT failure (a connection error, a timeout, HTTP 5xx or 429: the adapter words the last two as requests does)
# is retried by sp_run (RETRY_BACKOFF_S, two retries) like every step's; each attempt is its own run of the step and its
# own `failed` observation in the record (a fetch that raised is a row, 252 item 1(a)): up to three for one chain run.
AVAILABILITY_NFLVERSE_STEP = ["availability-nflverse", "--season", "2026"]
AVAILABILITY_GO_ON = ("addendum 252 item 3(a): the nflverse read's failure is receipted and paged as a sync-step "
                      "failure, stopping nothing")

# soccer-morning-after's LAST step (ARCHITECT 2026-11-03, addendum 230 item 2(b), verbatim in part: "results-tally on
# the host (DB mode=ro) as the last step of soccer-morning-after, its RESULTS.md and a JSON beside it to the mirror";
# 248 item 2(c); ARCHITECT 2026-11-08, addendum 289 item 3: "written on the HOST by the morning-after chain and
# mirrored [...] a file under exports/, the mirror's top-level rule carries it"): exports/RESULTS.md and
# exports/results_tally.json, the mirror's sp_run push after the step carrying both. After the shadow export, so D2's
# "after every sync" stands; a shadow export that exits 2 (D7) stops the chain before it, as any failed step does.
# UNMETERED (results-tally is). Never ./RESULTS.md: mlb-morning's H0-9 tally, and sp_deploy's restore of it, unchanged.
HOST_TALLY_STEP = ["results-tally", "--host-export"]

CUP_SCHEDULE = ("EFL", "CL", "UEL", "FAC")     # intl-daily's cup schedule read (#707), in this order
COVERAGE_STEP = ["coverage", "--json"]         # intl-daily's LAST step (#805, addendum 225 item 5)

CHAINS: dict[str, dict] = {
    # --- MLB (docs/CLI.md "MLB daily operation") ---
    "mlb-morning": {
        "backup": "daily",
        "steps": [
            ["sync-matches", *MLB, "--date-from", "{yesterday}", "--date-to", "{today}"],
            ["evaluate", "--sport", "mlb"],
            # H0-5: unattended — a PASS is HELD and pages; never auto-promotes.
            ["improve", "--sport", "mlb", "--hold-on-pass"],
            ["sync-appearances", *MLB, "--recent"],
            ["sync-umpires", *MLB, "--recent"],
            ["export-results", "--sport", "mlb", "--competition", "MLB"],
            ["results-tally"],  # H0-9: chain end
        ],
    },
    "mlb-preslate": {
        "steps": [
            ["sync-matches", *MLB, "--date-from", "{today}", "--date-to", "{today}"],
            ["sync-bullpen-stats", "--season", "2026"],
            ["sync-pitchers", *MLB],
            ["sync-pitcher-stats", "--season", "2026"],
            ["sync-odds", *MLB],
            ["sync-kalshi"],
            ["predict", "--sport", "mlb", *MLB],
            # --today = today's scheduled games (BACKLOG 2026-07-06 / 08-13 audit)
            ["sync-umpires", *MLB, "--today"],
            ["capture-weather"],
            ["export-predictions", "--sport", "mlb", "--competition", "MLB"],
        ],
    },
    # MLB PHASE A (architect 2026-09-29): the HOST's MLB history. Sync only:
    # no predict / evaluate / improve (the host holds no MLB predictions; MLB
    # predictions stay a laptop duty, PHASE B negative). With SP_SKIP_FAMILIES
    # naming MLB, sync-matches MLB runs the api-sports fallback
    # (src/ingestion/mlb_apisports.py): teams first, then the season's /games
    # in ONE provider call, receipted with the doubleheader-game-2 limitation.
    "mlb-history": {
        "backup": "daily",
        "steps": [
            ["sync-competitions", "--sport", "mlb"],   # static list, no provider call
            ["sync-matches", *MLB],
        ],
    },
    "clv-capture": {  # one-for-one with scripts/setup_clv_capture.sh
        "steps": [["capture-odds", "--sport", "mlb", *MLB]],
    },
    # --- Soccer (docs/pl_weekly_routine.md) ---
    # THE TIMERS RETIREMENT (ARCHITECT 2026-10-25, addendum 166 item 6(B), applying addendum 126 item 2(d): "The
    # host's fixed-time timers [...] are retired by the cutover PR"): the PL predict and the PL window export
    # (`export-predictions --sport soccer --competition PL --start {sat} --end {sat_plus3} --status scheduled`, the
    # slate file soccer_PL_<sat>_to_<sat_plus3>.json) left this chain; the closing watch's slate stage runs the same
    # predict and writes that file itself (closing.slate_steps). Every sync stays, on the same two timers.
    "soccer-prematch": {  # Friday and Saturday: the PL lines + the expansion leagues' data lines, then the shadow export
        "steps": [
            ["sync-matches", *PL],
            ["sync-odds", *PL],
            ["sync-injuries", *PL],
            *[[verb, *x] for x in EXPANSION for verb in ("sync-matches", "sync-odds")],
            *[["sync-kalshi-soccer", "--competition", c] for c in KALSHI_CAPTURE_ONLY],   # capture only
            ["sync-kalshi-soccer"],
            [*SHADOW_EXPORT_STEP],       # LAST (addendum 185 D2): reads the DB only, after every sync above
        ],
    },
    "soccer-morning-after": {
        "backup": "daily",
        "steps": [
            ["sync-matches", *PL],
            *[["sync-matches", *x] for x in EXPANSION],
            ["evaluate", "--sport", "soccer"],
            ["export-results", "--sport", "soccer", "--competition", "PL"],
            [*SHADOW_EXPORT_STEP],       # after every sync above (addendum 185 D2): reads the DB only
            [*HOST_TALLY_STEP],          # LAST (addendum 230 item 2(b), 248 item 2(c), 289 item 3): DB mode=ro
        ],
    },
    "soccer-refresh": {  # H0-6: OPERATOR-STARTED ONLY — no timer exists
        "backup": "prerefresh",
        "operator_only": True,
        "steps": [
            # EL1/EL2 feed the refresh pot. The laptop's 2026/27 rows were
            # found stale at the H1a compare (24 finished vs the host's
            # 87/94); architect ruling 2026-09-27: sync them before every refresh.
            ["sync-matches", "--competition", "EL1", "--season", "2026/27"],
            ["sync-matches", "--competition", "EL2", "--season", "2026/27"],
            ["evaluate", "--sport", "soccer"],
            ["export-results", "--sport", "soccer", "--competition", "PL"],
            ["soccer-refresh"],
        ],
    },
    # --- NFL (docs/CLI.md "NFL operation") ---
    "nfl-lines": {
        "steps": [["sync-odds-football"], ["sync-kalshi-nfl"]],
    },
    "nfl-grade": {
        "backup": "daily",
        "steps": [
            ["sync-matches", "--competition", "NFL", "--season", "2026"],
            ["nfl-grade"],
            ["export-nfl-results"],
        ],
    },
    # Was "nfl-predict" (sp-nfl-predict.timer). THE TIMERS RETIREMENT (ARCHITECT 2026-10-25, addendum 166 item 6(B),
    # applying addendum 126 item 2(d)): `predict-nfl` and `export-nfl-predictions` (the slate file
    # nfl_predictions_<date>.json) left it; the closing watch's slate stage runs the same two itself
    # (closing.slate_steps). The two steps the slate stage does not run stay, on the same Thu/Sun schedule
    # (sp-nfl-prematch.timer): the whole-league injury sync (Exhibit 1 ruling, 2026-09-28: injuries first; the slate's
    # own is scoped to the day's games) and the weather capture (tracking only: no model reads it).
    "nfl-prematch": {
        "steps": [["sync-injuries", "--competition", "NFL", "--season", "2026"],
                  ["capture-weather-nfl"]],
    },
    # --- Market-only (docs/CLI.md "Market-only competitions") ---
    "nhl-daily": {
        "backup": "daily",
        # Season gate: 2026-27 opening day, operator-confirmed 2026-09-29 (the
        # old 2026-10-07 was 2025-derived). Host override: SP_NHL_ACTIVE_FROM
        # in host.env, so next season's start is a config edit, not code.
        "active_from": "2026-09-29",
        "active_from_env": "SP_NHL_ACTIVE_FROM",
        "steps": [
            # Single-day calls (ruling 2026-09-28): api_hockey only sends a
            # `date` when from == to, so a yesterday->tomorrow range silently
            # became one whole-season pull per run. Three from==to calls, the
            # window service's approach (quota hygiene; data was correct).
            *[["sync-matches", "--competition", "NHL", "--season", "2026",
               "--date-from", d, "--date-to", d]
              for d in ("{yesterday}", "{today}", "{tomorrow}")],
            ["sync-odds", "--competition", "NHL", "--season", "2026"],
            ["sync-kalshi-nhl"],
            ["export-fixtures", "--competition", "NHL"],
            # NHL SHADOW (architect 2026-09-30; v7 from 2026-10-02): v7 updates on
            # the xG margin, so the live season's shot events are synced first
            # (api-web.nhle.com, the NHL's own free API; stored games are skipped)
            ["nhl-shot-sync", "--start", "{yesterday}", "--end", "{today}"],
            # the best failed candidate (v7) as a greyed reference model, v1 beside
            # it — never a call (engine model_shadow)
            ["export-nhl-predictions"],
        ],
    },
    # --- NBA, market-only (ARCHITECT 2026-11-05, addendum 261 item 1(b): "the chain `nba-daily` (sync-matches on a
    # [...] window, sync-kalshi, the coverage write) at a UTC minute off every existing timer (Code lists the timers
    # and picks; my block enables it)"; the window CORRECTED by ARCHITECT 2026-11-06, addendum 274 item 2(3): "THE
    # WINDOW — THREE UTC DAYS, {yesterday, today, tomorrow}, nhl-daily's own: [...] the US evening's games fall on
    # the NEXT UTC date, so at 06:47Z a {yesterday, today} window has no row for tonight's games, and the hourly
    # window chain plans NBA only from rows that exist (item 7). Without tomorrow, tonight's PAPER page has nothing
    # to capture. CORRECTS 271 item 3(d)"; and item 2(9): "ship the three-day window as nhl-daily runs it (each day
    # its own step: /leagues + /games, 6 calls a day, plus the window chain's 4 an hour while games are in its
    # window: well under 7,500; 271 item 3(f)'s "two or three" was my estimate and is CORRECTED by this item"). As
    # built:
    # - THE WINDOW: three single-day UTC steps, {yesterday}, {today} and {tomorrow}, nhl-daily's shape
    #   (api_basketball sends `date` only when from == to; a range is one whole-season pull). At the timer's 06:47
    #   UTC, {today} holds last night's US evening (00:00-03:30Z) and {yesterday} the afternoon tips before it
    #   (17:00-23:59Z), so every result of the previous US day is read; {tomorrow} holds tonight's US evening, so its
    #   rows exist for the window chain (WINDOW_KALSHI's tier, below), which plans every competition with an
    #   unfinished game in its 24 hours.
    # - THE KALSHI STEP is `sync-kalshi-nba` (KXNBAGAME): plain `sync-kalshi` is MLB's (adapters/kalshi.py
    #   GAME_SERIES), so 261's "sync-kalshi" is read as the NBA's own Kalshi sync.
    # - THE COVERAGE WRITE is NOT a step here: `coverage --json` is "the LAST step of one daily host chain"
    #   (addendum 225 item 5; COVERAGE_STEP, intl-daily's, test_805_coverage_step pins one holder). This chain runs at
    #   06:47 UTC, before intl-daily's 07:20 UTC write, so the day's one coverage file reads the fresh NBA rows. RULED
    #   by addendum 274 item 2(2): "intl-daily's 07:20 UTC `coverage --json` is THE coverage write [...] 261 item
    #   1(b)'s "the coverage write" in nba-daily is read as satisfied by the ordering. No second writer, ever."
    # - backup "daily", as nhl-daily (a morning chain opens with the backup line); no active_from (the 2026-27 season
    #   is under way); no export, no predict, no shadow: no model is declared (261 item 1(f)).
    "nba-daily": {
        "backup": "daily",
        "steps": [
            *[["sync-matches", "--competition", "NBA", "--season", "2026", "--date-from", d, "--date-to", d]
              for d in ("{yesterday}", "{today}", "{tomorrow}")],
            ["sync-kalshi-nba"],
        ],
    },
    # --- TENNIS, market-only (ARCHITECT 2026-11-05, addendum 261 item 2(c): "the chain tennis-daily"; 2026-11-06,
    # addendum 269 items 1-3: Kalshi's two tour series are the fixture source AND the results source; lane
    # tennis-market-only, #838). As built, on the NBA's pattern where tennis does not differ:
    # - THE WINDOW: one step per tour, `sync-matches` over the ticker days {yesterday} .. {tomorrow} (the adapter reads
    #   the series' whole listing to its last page, 269 item 3(d), and writes the events dated inside the window, the
    #   players first, from the same read). No --season: the tennis season is the ticker's year (int-style, the
    #   adapter stamps each row), and a fixed one would drop January's rows after 12-31. The window is three days and
    #   never wider than cli.TENNIS_MAX_WINDOW_DAYS: addendum 270 item 5, "no backfill is scheduled". {yesterday} reads
    #   the results settled since the last run; {tomorrow} gives the window chain the rows it plans from. Each step
    #   also RE-READS, from the same listing, the stored SCHEDULED rows dated in the TENNIS_MAX_WINDOW_DAYS days before
    #   {yesterday} (a late settlement; rows only, none created: cli._tennis_reread).
    # - THE KALSHI STEPS are `sync-kalshi-atp` and `sync-kalshi-wta` (the shared matcher, then tennis's player check).
    # - NO COVERAGE STEP: intl-daily's 07:20 UTC `coverage --json` is THE coverage write (addendum 274 item 2(2):
    #   "No second writer, ever."); this chain's timer (06:53 UTC) runs before it.
    # - backup "daily", as nba-daily; no active_from (the chain's timer is the architect's block, 261 item 0, and the
    #   first PAPER record is "the first KXATPMATCH / KXWTAMATCH event the chain captures on or after 12-28", 269
    #   item 2); no export, no predict, no shadow: no model is declared (261 item 2(e)).
    "tennis-daily": {
        "backup": "daily",
        "steps": [
            *[["sync-matches", "--competition", code, "--date-from", "{yesterday}", "--date-to", "{tomorrow}"]
              for code in ("ATP", "WTA")],
            ["sync-kalshi-atp"],
            ["sync-kalshi-wta"],
        ],
    },
    # --- International (ARCHITECT 2026-10-02): intl-elo-v2 PASSED; the UNL
    # shadow runs through its 60-game confirmation window. The daily intl
    # sync is INCREMENTAL (--since {today}: only seasons still running), its
    # responses saved so the venue step (route B, v3) replays them; only a
    # venue country not seen before costs a call. ---
    "intl-daily": {
        "backup": "daily",
        "steps": [
            ["intl-sync", "--since", "{today}", "--save", "exports/intl_daily"],
            ["intl-venue-sync", "--from-dir", "exports/intl_daily", "--venues-dir", "exports/intl_venues"],
            ["export-unl-predictions"],
            # THE CUPS' DAILY SCHEDULE READ (#707; ARCHITECT 2026-10-27: "a daily cup schedule step (EFL, CL, UEL, FAC)
            # on an existing daily chain [...], listed in the chain's steps"): one listing read per cup, so a cup
            # game's stored kickoff is at most a day old on its match day. Nothing else re-read a cup's schedule
            # between the Sunday full-season sync and the 24h window (EFL round 4, four of eight dates a day wrong).
            # After the intl steps, so a cup read that fails leaves the intl steps done (#805 put coverage after it).
            # TEAMS BEFORE MATCHES (ARCHITECT 2026-11-01, addendum 204 item 3(b); #728): "intl-daily runs the same
            # sync-teams step before each cup's sync-matches (four calls a day; the cup rounds are where new clubs
            # enter)". Each cup's sync-teams runs immediately before its sync-matches, under the chain's one DB lock.
            *[[verb, "--competition", code, "--season", "2026/27"] for code in CUP_SCHEDULE
              for verb in ("sync-teams", "sync-matches")],
            # THE COVERAGE FILE'S HOST WRITER (ARCHITECT 2026-11-03, addendum 225 item 5; #805), verbatim: "`coverage
            # --json` becomes the LAST step of one daily host chain (intl-daily's tail is the candidate: daily, early,
            # after its syncs; read-only, reads the DB and the registry; its failure never blocks a sync step — Code
            # names the chain and the step's exit handling in the PR body)." COVERAGE_STEP, LAST, after the cups' pairs:
            # it reads the DB mode=ro and writes exports/coverage_<date>.json (its default --out, the ET day; sp_run
            # runs every step from the checkout), which the step's mirror push carries to host/latest/coverage.json.
            # Exit handling is sp_run's, unchanged: no step follows it, so its failure blocks no sync (the chain's
            # exit is the first failure's and systemd pages); a failed step before it that stops the chain (a cup's
            # sync-matches, an intl step), or a failed daily backup before any step (sp_run skips every step), leaves
            # that day without a host coverage file.
            [*COVERAGE_STEP],
        ],
    },
    # --- The availability record (ARCHITECT 2026-11-04, addendum 252 item 3(a); lane availability-record) ---
    "availability-daily": {
        "go_on": ("availability-nflverse",),
        "go_on_why": AVAILABILITY_GO_ON,
        "steps": [AVAILABILITY_NFLVERSE_STEP],
    },
    "ncaa-market": {
        "steps": [
            # ARCHITECT 2026-10-02 (#254 residue): Thursday games still read
            # SCHEDULED 20h after finishing — no NCAA result sync ran between
            # them and Friday's export. Single-day calls, yesterday and today
            # (the american-football adapter sends a `date` only when
            # from == to), BEFORE the export, so finished games leave the window.
            # {tomorrow} (ARCHITECT 2026-10-07): kickoffs at 8pm ET or later fall
            # on the next UTC date; the operator block carried it by hand.
            *[["sync-matches", "--competition", "NCAA", "--season", "2026",
               "--date-from", d, "--date-to", d]
              for d in ("{yesterday}", "{today}", "{tomorrow}")],
            ["sync-kalshi-ncaa"],
            ["export-fixtures", "--competition", "NCAA"],
        ],
    },
    # KICKOFF FRESHNESS (ARCHITECT 2026-10-09, addendum 19 item 3): "On the host, the stored kickoff of
    # every NCAA game in the next seven days is at most one day old." The provider files an unannounced
    # college kickoff at 04:00Z (midnight US Eastern) and announces the real time days later; ncaa-market
    # (Tue-Sat) syncs only yesterday..tomorrow and the window service only its 24 hours, so on 10-09 the
    # host still held 30 of Saturday's games at 04:00Z. Single-day calls for today..today+7 (the
    # american-football adapter sends `date` only when from == to), twice a day (sp-ncaa-schedule.timer)
    # so one failed run still leaves every stored kickoff under a day old. No Kalshi; one export, last (below).
    #
    # REFRESH BY ID (ARCHITECT 2026-10-09, addendum 21 item 1): "For NCAA, the kickoff, status and score of
    # every stored SCHEDULED game kicking off in the next seven days are refreshed from the provider by the
    # game's own id, at least once a day on the host and in the laptop's morning chain. The listing reads
    # stay: they find games we do not hold." The provider's listing no longer carries college games that
    # have not started; they still answer by id. So the listing reads stay first (new games), and the
    # refresh by id runs after them, over every stored SCHEDULED game today..today+7 (one GET per game).
    #
    # THE COLLEGE SHADOW EXPORT (ARCHITECT 2026-11-03, addendum 230 item 1(b), verbatim in part: "the college shadow
    # export on the ncaa-schedule chain (the NHL shadow's shape: the entry's probabilities per fixture, market-only,
    # never a call) [...] dormant while the verdict is null or FAIL"): NCAA_SHADOW_STEP, the chain's LAST step, after
    # the syncs it reads. While the registry records no verdict, or a verdict other than PASS, for ncaa-elo-v2 it
    # prints DORMANT with the reason, writes nothing and exits 0 (--dormant-ok): the chain never fails on it. Every
    # other refusal (coverage, s, rule, constants, a file that exists) exits 2 and fails the chain, as any export step
    # does (sp_run.run_steps). Not a sync step: a real failure still pages. It reads the DB and the registry only
    # (UNMETERED).
    # THE ORDER (ARCHITECT 2026-11-03, addendum 236 item 3(4), verbatim in part): "the export runs whether or not
    # refresh-by-id succeeded, on the stored state it finds, its rows stamped with the refresh it saw (the window
    # chain's rule, 84 item 2(b): a sync step's failure does not stop the chain); the refresh failure pages as now."
    # So `go_on` names refresh-by-id: a failed refresh is receipted, the run goes on to the export, the chain's exit is
    # the first failure's (OnFailure pages as now) and its summary names the step (sp_run.run_steps). Only that step:
    # a failed listing read (sync-matches) stops the chain as before (not continue_on_sync_failure: wider than ruled).
    # A D6 coverage drop after a PASS is the export's refusal (exit 2, never DORMANT; item 3(4)): it pages.
    "ncaa-schedule": {
        "go_on": ("refresh-by-id",),
        "steps": [
            *[["sync-matches", "--competition", "NCAA", "--season", "2026", "--date-from", d, "--date-to", d]
              for d in ("{today}", *[f"{{today_plus{n}}}" for n in range(1, NCAA_FORWARD_DAYS + 1)])],
            ["refresh-by-id", "--competition", "NCAA", "--days", str(NCAA_FORWARD_DAYS)],
            NCAA_SHADOW_STEP,
        ],
    },
    # --- Weekly full-season sync (CLAUDE.md: "full-season weekly") ---
    # Steps come from SP_FULLSEASON_LIST (one "CODE|SEASON" per line), written
    # at provisioning from a read-only DB query — per-comp season strings are
    # what the DB stores, never assumed. Missing/empty list = chain FAILS.
    # TEAMS BEFORE MATCHES (ARCHITECT 2026-11-01, addendum 204 item 3(a); #765): "the weekly full-season chain runs
    # `sync-teams --competition CODE --season SEASON` immediately before each `sync-matches` line of
    # SP_FULLSEASON_LIST, under the same DB lock, teams-before-matches per competition as the law says". Two steps per
    # line, sync-teams then sync-matches (sp_run.fullseason_resolve). `sync-teams --competition MLB` routes as
    # `sync-matches` does where SP_SKIP_FAMILIES names MLB (cli.py's api-sports fallback, its own sync_teams);
    # nothing here special-cases it.
    #
    # THE HOST'S CFBD READ (ARCHITECT 2026-11-03 17:40 ET, addendum 240 item 4(b), verbatim in part: "a small ruled PR
    # after #816 puts `ncaa-cfbd-labels --year 2026` on the host's weekly-fullseason chain (Sunday 06:00Z; metered, one
    # read a week — the neutral flags of a week's games are known days ahead and seldom change), its failure a
    # sync-step failure that stops nothing after it; the daily ncaa-schedule chain stays as it is."): `steps` holds the
    # steps AFTER the list's (sp_run.resolve appends them to fullseason_resolve's; the cutover readout still counts the
    # list alone). NCAA_CFBD_STEP is the LAST step: its two joins read OUR stored NCAA fixtures (the pregame flag by the
    # exact name tier; a substring-tier label only where our stored score agrees), so that, WHEN the host's list carries
    # an NCAA|2026 line, the week's full-season sync of them runs first, as teams run before matches (the host list's
    # NCAA line is not verified here; first or last is the architect's to rule). METERED (not in UNMETERED): under
    # SP_PARALLEL_MODE=designated it runs only on a designated day. `go_on` names it: a failed read is receipted
    # (`continued`: CFBD_GO_ON), the run goes on to any later step, the chain's exit is the first failure's (OnFailure
    # pages) and the closing lines name the step (sp_run.run_steps). The read runs only when the list resolves (the
    # setting is set, the file exists and lists a competition; else resolve refuses before any step), the daily backup
    # succeeds, and no earlier sync-matches fails (a failed one still stops the chain before it, as before); in every
    # other case that week's read waits for a hand run or the next Sunday.
    "weekly-fullseason": {
        "backup": "daily",
        "fullseason": True,
        "go_on": ("ncaa-cfbd-labels",),
        "go_on_why": CFBD_GO_ON,
        "steps": [NCAA_CFBD_STEP],
    },
}

# --- Next-24h WINDOW SERVICE (architect spec 2026-09-27) ---
# Hourly; the timer ships in the pack and is enabled on H1b day 1. The steps
# are PLANNED at run time from the DB (read-only), so adding a competition
# adds rows, not code:
#   per competition with non-finished games in the next WINDOW_HOURS:
#     sync-matches --season S --date-from D --date-to D, ONE UTC day per call
#       (the hockey/american-football adapters honour a date window ONLY when
#       from == to; a range silently fetches the whole league listing);
#     sync-odds --competition C --season S --limit <that competition's window
#       game count> (sync_odds takes the next N scheduled games), except the
#       american-football family (sport NFL: NFL + NCAA), which is priced once
#       by sync-odds-football;
#   then the Kalshi syncs for the competitions in WINDOW_KALSHI, then the
#   capture-only Kalshi syncs of WINDOW_KALSHI_CAPTURE_ONLY (addendum 164
#   item 2(a)), then `window-card`. After a clean run, or a run where only sync steps failed
#   and the card ran (addendum 84 item 2(b)), sp_window_page pages CARD
#   DELTAS (post).
# NO predict/improve step, ever: model fields stay canonical from their slot.
# SP_SKIP_FAMILIES (host.env, e.g. "MLB") drops a family's sync-matches only
# (statsapi.mlb.com 406s the DO ASN; MLB syncing is a laptop duty).
WINDOW_HOURS = 24
WINDOW_KALSHI: dict[str, list[list[str]]] = {
    # competition code -> its Kalshi sync. CI pins the soccer entries to
    # src/adapters/kalshi.py SOCCER_GAME_SERIES (PL; UNL pinned to KXUEFANLGAME,
    # ARCHITECT 2026-10-05, so no --series flag) + SOCCER_SERIES_DISCOVERY,
    # less KALSHI_CAPTURE_ONLY (the soccer-expansion leagues: capture only, WINDOW_KALSHI_CAPTURE_ONLY below,
    # addendum 164 item 2(a)).
    "MLB": [["sync-kalshi", "--date-from", "{today}", "--date-to", "{tomorrow}"]],
    "NFL": [["sync-kalshi-nfl"]],
    "NCAA": [["sync-kalshi-ncaa"]],
    "NHL": [["sync-kalshi-nhl"]],
    # NBA (ARCHITECT 2026-11-05, addendum 261 item 0: "the hourly capture tier"; addendum 271 item 3(h)): the NHL
    # precedent, tiered as every entry (near / imminent only). Like NHL's, its line moves page (sp_window_page reads
    # this live list); the soccer capture-only table is pinned to the expansion leagues and is not the NBA's.
    "NBA": [["sync-kalshi-nba"]],
    # ATP / WTA (ARCHITECT 2026-11-05, addendum 261 item 0: "the hourly capture tier"; 269 item 3(a)): the NBA's
    # precedent, tiered as every entry (near / imminent only).
    "ATP": [["sync-kalshi-atp"]],
    "WTA": [["sync-kalshi-wta"]],
    "PL": [["sync-kalshi-soccer", "--competition", "PL"]],
    "UNL": [["sync-kalshi-soccer", "--competition", "UNL"]],
    # CL (ARCHITECT 2026-10-13, addendum 58): market-only like UNL, read on the window card. "The host takes it with
    # the tag that carries it." No CL sync goes into the operator's block before the architect has read one
    # replay console with CL in it (item 3).
    "CL": [["sync-kalshi-soccer", "--competition", "CL"]],
}
# CAPTURE QUALITY (ARCHITECT 2026-10-24, addendum 164 item 2(a), verbatim): "the four series plus KXLALIGAGAME join the
# host's hourly window chain's Kalshi capture from the next deploy — a capture-only step, no export, no call; the pacing
# rule holds (one series per call, 90 s apart from any laptop pull is the operator's rule, the chain's own pacing is
# Code's)". Evidence: finished 2026/27 games with a qualifying three-way close SA 0 of 50, BL1 1 of 37, FL1 1 of 46, ELC
# 1 of 96, every miss "no capture" (outside the window chain, captured only Fri/Sat). Built from KALSHI_CAPTURE_ONLY,
# one step per code, so one series per call (each code's series is mapped in src/adapters/kalshi.py SOCCER_GAME_SERIES:
# no --series flag). Tiered as WINDOW_KALSHI is (sp_run.window_plan): a league's step runs only when its next kickoff in
# the window is near or imminent (<= PROX_FAR_H), so the last capture before a kickoff is at most about an hour old (the
# timer fires at :05, outside 04-05 UTC, H0-3). A separate table, never merged into WINDOW_KALSHI: nothing on the card's
# path reads it (window-card reads the DB's stored matches and quotes, never chains.py), so it adds no venue line, no
# export and no call (desk_policy.SHADOW_VENUE_COMPS still refuses them). Pacing: the chain's steps run one after
# another, each its own process; a step failing on a 429 is retried by sp_run (RETRY_BACKOFF_S, 15 s then 45 s), and a
# step still failing is a sync step, so the chain runs on (addendum 84 item 2(b)). No bar moves: R42(b) is unchanged.
WINDOW_KALSHI_CAPTURE_ONLY: dict[str, list[list[str]]] = {
    c: [["sync-kalshi-soccer", "--competition", c]] for c in KALSHI_CAPTURE_ONLY}
# A SYNC STEP'S FAILURE DOES NOT STOP THE WINDOW CHAIN (ARCHITECT 2026-10-16 09:29 ET, addendum 84 item 2(b),
# RULED, verbatim): "in the window chain a sync step's failure is recorded and notified as now, but does not stop the
# chain — the later sync steps and the card/export steps run; a failure in a card/export step still ends the chain.
# The hourly card is what the host page and the Cockpit read; one provider hiccup should not blank an hour. [...] the
# chain's exit stays 1 when any step failed, so the failure notice still fires." A sync step is one whose command
# starts "sync-" (sp_run.SYNC_PREFIX); any other step (window-card) is a card/export step.
CHAINS["window"] = {"window_plan": True, "post": "window_page", "steps": [], "continue_on_sync_failure": True}

# PROXIMITY TIERS (architect ruling 2026-09-27): each competition's steps
# scale with the time to ITS next kickoff inside the window.
#   far       (> PROX_FAR_H)                 schedule check only (sync-matches:
#                                            status / postponement), no odds
#   near      (PROX_IMMINENT_H .. PROX_FAR_H) + odds (--limit = its games
#                                            within PROX_FAR_H) + Kalshi
#   imminent  (< PROX_IMMINENT_H)            same repricing as near, plus the
#                                            T-90 freshen_needed detection
#                                            (the card tracks games inside T-90)
# A competition with no game inside the window contributes zero steps. The
# chain receipt carries the competitions per tier and the steps skipped by
# proximity (flat plan minus tiered plan).
PROX_FAR_H = 6
PROX_IMMINENT_H = 2
# T-90 HOLE (ruling 2026-09-29 on #65): the imminent tier re-syncs injuries for
# the MODEL families' competitions, scoped to the teams kicking off inside the
# tier (sync-injuries --kickoff-within-hours), so the T-90 signature has
# something to compare. MLB stays laptop-only (no injury source; ASN).
IMMINENT_INJURY_FAMILIES = ("NFL", "SOCCER")

# FRESHEN CHAINS (architect ruling 2026-09-27): the documented operator
# sequences, run by the window service on freshen_needed inside T-90. Each
# run is under the chain lock, receipted, and rate-guarded to at most one
# freshen per family per FRESHEN_MIN_INTERVAL_S. A freshen re-writes that
# slot's prediction exactly as the laptop's T-60 freshens do today (the
# ledger's idempotent re-log absorbs it). Market-only families have no
# freshen: the window repricing IS their freshen. Families in
# SP_SKIP_FAMILIES (MLB on the DO host, ASN ruling) are logged as
# freshen_needed and never run.
# #673 RULED (ARCHITECT 2026-10-25 11:55 ET, addendum 167 postscript (b)): "a file that carries Desk blocks is never
# replaced by one without them. The freshen writes to its own name (the alternative), and the slate's kept copy and
# receipt stay true; `--desk` is not added to the freshen (the closing page is the row that counts, the freshen is an
# input refresh)." freshen:NFL's export writes {freshen_out}, logs/<freshen run id>.<the export's default name>
# (sp_run.run_vars): outside exports/, so never the slate's exports/nfl_predictions_<date>.json (a hard link to the
# slate's kept logs/ copy, addendum 133 item 3(a)), never mirrored, and never matched by closing.py's export_glob
# (nfl_predictions_*.json in exports/). The closing chain derived from it takes its own --out (_closing_from_freshen).
CHAINS["freshen:NFL"] = {"freshen_out": "nfl_predictions_{today}.json",
                         "example_vars": {"freshen_out": "logs/20261026T150000Z-freshen-NFL.nfl_predictions_2026-10-26.json"},
                         "steps": [
    ["sync-injuries", "--competition", "NFL", "--season", "2026"],
    ["sync-odds-football"],
    ["sync-kalshi-nfl"],
    ["predict-nfl"],
    ["export-nfl-predictions", "--out", "{freshen_out}"],
]}
CHAINS["freshen:MLB"] = {"steps": [list(s) for s in CHAINS["mlb-preslate"]["steps"]]}  # the 10
# MLB CLOSING-RUN AUTOPILOT (ARCHITECT 2026-10-08, addendum 13 item 3, Q2, A1): "It runs the ten mlb-preslate steps
# as chains.py lists them (chains.py stays the one place commands live), with the export carrying the Desk's call."
# Derived from mlb-preslate, never a copy: steps 1-9 are mlb-preslate's own; step 10 is its export plus `--date
# {today}` (the first pitch's America/New_York date, which closing.py sets as {today}: the export's default
# slate is the UTC date, which drops a 22:10 ET game run after 20:00 ET) and `--desk`. LAPTOP ONLY ("the host
# cannot reach the MLB feed"): run through `python cli.py closing-run --family MLB` (deploy/hosting/closing.py), never
# sp_run, which refuses it.
# A1 (ARCHITECT 2026-10-09, addendum 23): "SOCCER's and MLB's stay sync-matches by date, with an opt-in that names
# the covered games and exits non-zero unless the provider's answer held every one of them." Step 1 is mlb-preslate's
# schedule read plus `--match-ids {match_ids}` (the run's covered games); mlb-preslate itself is unchanged.
CHAINS["mlb-closing"] = {
    "laptop_only": "python cli.py closing-run --family MLB",
    "example_vars": {"match_ids": "1,2", "export_out": "logs/20261011T1625Z-mlb-closing.mlb_MLB_2026-10-11.json"},
    "steps": [[*CHAINS["mlb-preslate"]["steps"][0], "--match-ids", "{match_ids}"]]
             + [list(s) for s in CHAINS["mlb-preslate"]["steps"][1:-1]]
             + [[*CHAINS["mlb-preslate"]["steps"][-1], "--date", "{today}", "--desk", "--out", "{export_out}"]],
}
CHAINS["freshen:SOCCER"] = {"steps": [
    ["sync-odds", *PL],
    ["sync-injuries", *PL],
    ["sync-kalshi-soccer", "--competition", "PL"],
    ["predict", "--sport", "soccer", *PL],
    # export windowing (architect 2026-09-28): no dates -> the 36h current
    # slate, so a closing freshen yields a one-slate file
    ["export-predictions", "--sport", "soccer", "--competition", "PL", "--status", "scheduled"],
]}
# CLOSING RUNS FOR EVERY MODEL FAMILY (ARCHITECT 2026-10-09, addendum 21 item 3, C1/C3; addendum 22 item 3).
# C1: "A closing run exists for every family whose calls come from a live model: MLB, NFL and SOCCER (PL) today. A
# league joins when its model is CONFIRMED and the Desk calls it. A shadow has no closing run and is never paged as a
# pick." C3: "MLB's closing chain is #370's. NFL's and SOCCER's are their freshen chains (chains.py, freshen:NFL and
# freshen:SOCCER), ending in the export that carries the Desk's call. A run prices the games it covers, not the whole
# league, so that the page is out by T-30." Addendum 22: "Every closing chain opens with the schedule read for its
# games (status and start time), as MLB's does."
# Derived from the freshen chains, never copied: the schedule read first, then every freshen step in its order.
# The schedule read (ARCHITECT 2026-10-09, addendum 23 A1): "A closing run does not page a game whose schedule read
# did not answer. [...] SOCCER's and MLB's stay sync-matches by date, with an opt-in that names the covered games and
# exits non-zero unless the provider's answer held every one of them. Every default is unchanged." A1 AS AMENDED
# (ARCHITECT 2026-10-09, addendum 24 item 3, as addendum 25 item 2(i) gives it): "nfl-closing takes the SOCCER form:
# sync-matches by date, one UTC day per call, naming that day's covered games. The by_id branch goes."
#   NFL and SOCCER  sync-matches by date, one UTC day per call ({start_day} and {end_day}: the UTC dates of the run's
#           first and last covered start; an identical second call is dropped by the run), each with --match-ids
#           naming that day's covered games ({start_day_ids} / {end_day_ids})
# Options added to the freshen steps:
#   sync-injuries        --match-ids {match_ids} --strict             (the covered games' teams, Codex round 2 on
#                                                                      #385; addendum 22 strict mode; A2: NFL rosters)
#   sync-odds-football   --match-ids {match_ids}                      (the covered games only)
#   sync-odds            --match-ids {match_ids}                      (the covered games only)
#   the export           --desk                                       (the file carries the Desk's call)
#                        --out {export_out}                           (addendum 40 item 2: outside exports/)
# The Kalshi syncs, predict and predict-nfl run as the freshen chains list them (one series listing each; the model
# step writes every upcoming game, as it always has). Run through `python cli.py closing-run --family F`
# (deploy/hosting/closing.py), never sp_run, which refuses them. C7: "The host runs NFL and SOCCER with the same
# command under a timer from the cutover ruling on, not before." No timer ships here.
_CLOSING_ADD = {
    "sync-injuries": ["--match-ids", "{match_ids}", "--strict"],
    "sync-odds-football": ["--match-ids", "{match_ids}"],
    "sync-odds": ["--match-ids", "{match_ids}"],
    "export-nfl-predictions": ["--desk", "--out", "{export_out}"],
    "export-predictions": ["--desk", "--out", "{export_out}"],
}
# ONE CLOSING, ONE PAGE, ONE FILE (ARCHITECT 2026-10-11, addendum 40 item 2): "A closing run does not write, replace
# or move the family's slate file. The slate chains write it, as they did before 2026-10-09." [...] "The run's export
# step writes outside exports/." Every closing chain's export step takes --out {export_out}: closing.py sets it to
# logs/<run id>.<the slate file's name> (the name R6 gave a moved export), and writes exports/closing_<FAMILY>_<start>
# .json itself once the page went out. The freshen and slate chains are unchanged.


FRESHEN_OUT = ["--out", "{freshen_out}"]


def freshen_step(s: list[str]) -> list[str]:
    """A freshen step without the freshen's own export file (#673): the closing run names its own (--out
    {export_out}, addendum 40 item 2)."""
    i = next((i for i in range(len(s) - 1) if s[i:i + 2] == FRESHEN_OUT), None)
    return list(s) if i is None else [*s[:i], *s[i + 2:]]


def _closing_from_freshen(freshen: str, comp: str, season: str) -> list[list[str]]:
    # A1 as amended (addendum 25 2(i)): by date, one UTC day per call, naming that day's covered games
    read = [["sync-matches", "--competition", comp, "--season", season, "--date-from", d, "--date-to", d,
             "--match-ids", ids] for d, ids in (("{start_day}", "{start_day_ids}"), ("{end_day}", "{end_day_ids}"))]
    return read + [[*freshen_step(s), *_CLOSING_ADD.get(s[0], [])] for s in CHAINS[freshen]["steps"]]


# A sample of the run-time placeholders, for the law-1 option check (tests/test_hosting_pack.py) only.
CLOSING_VARS_EXAMPLE = {"start_day": "2026-10-11", "end_day": "2026-10-11", "match_ids": "1,2",
                        "start_day_ids": "1,2", "end_day_ids": "1,2",
                        "export_out": "logs/20261011T1625Z-nfl-closing.nfl_predictions_2026-10-11.json"}
CHAINS["nfl-closing"] = {"closing_command": "python cli.py closing-run --family NFL",
                         "example_vars": CLOSING_VARS_EXAMPLE,
                         "steps": _closing_from_freshen("freshen:NFL", "NFL", "2026")}
CHAINS["soccer-closing"] = {"closing_command": "python cli.py closing-run --family SOCCER",
                            "example_vars": CLOSING_VARS_EXAMPLE,
                            "steps": _closing_from_freshen("freshen:SOCCER", *PL[1::2])}
# family -> its closing chain (C1). A league joins in a reviewed PR, by ruling.
CLOSING_FAMILIES = {"MLB": "mlb-closing", "NFL": "nfl-closing", "SOCCER": "soccer-closing"}
# (sport, competition) of a card row -> its freshen family. Only the
# competitions with a live model: NCAA, NHL, the cups and UNL are market-only.
FRESHEN_FAMILY = {("nfl", "NFL"): "NFL", ("mlb", "MLB"): "MLB", ("soccer", "PL"): "SOCCER"}
FRESHEN_MIN_INTERVAL_S = 3600

# Commands verified NOT to call a metered api-sports product (2026-09-27: the
# cli.py command bodies construct no IngestionService / adapter / requests
# call, and src/walters/ does no network I/O; Kalshi is public). Everything
# else is treated as METERED — conservative unknowns (law 4). Only consulted
# in H0-16(b) designated-days mode. tests/test_hosting_pack.py re-checks it.
UNMETERED = frozenset({
    "sync-kalshi", "sync-kalshi-soccer", "sync-kalshi-nfl", "sync-kalshi-nhl",
    "sync-kalshi-ncaa", "sync-kalshi-nba", "sync-kalshi-atp", "sync-kalshi-wta", "evaluate", "nfl-grade", "predict", "predict-nfl",
    "improve", "results-tally", "export-results", "export-predictions", "window-card",
    "export-nfl-predictions", "export-nfl-results", "export-fixtures",
    "export-nhl-predictions",
    "export-ncaa-predictions",  # reads the DB and the registry only (addendum 230 item 1(b): ncaa-schedule's last step)
    "nhl-shot-sync",          # api-web.nhle.com (the NHL's free API), never api-sports
    "export-unl-predictions",  # reads the DB only
    "export-soccer-expansion-shadow",  # reads the DB and the registry only (addendum 185 D2: its chain step)
    "coverage",               # reads the DB (mode=ro), the registry, the roadmap and exports/ only (#805: its chain step)
    "availability-nflverse",  # github.com's nflverse release file, never api-sports (addendum 252 item 3(a): UNMETERED)
})
