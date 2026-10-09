"""The chain definitions the host runs — the ONE place commands live.

Every step is `python cli.py <argv>` verbatim from docs/CLI.md and
docs/pl_weekly_routine.md, with options made explicit. tests/test_hosting_pack.py
checks every command and every option against cli.py's click definitions
(law 1), so a guessed flag (the H0 D1 `sync-matches --date` class) fails CI.

Placeholders, computed in UTC by sp_run: {today} {yesterday} {tomorrow}
{sat} (the coming Saturday, today if Saturday) {sat_plus3} (the Tuesday
after: pl_weekly_routine's "--end <MON-date+1>"). Midweek soccer rounds
(H0-10) override with `sp_run.py soccer-prematch --set sat=... --set sat_plus3=...`.

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
# sync-odds) on the soccer chains, laptop and host. No predict, no export: the shadow is its own command.
EXPANSION_CODES = ("PD", "SA", "BL1", "FL1", "ELC")
EXPANSION = [("--competition", c, "--season", "2026/27") for c in EXPANSION_CODES]
# Kalshi series PINNED (ARCHITECT 2026-10-07, addendum 2): "A pinned series never makes a league live." Their
# sync-kalshi-soccer runs on the shadow chain (soccer-prematch) as CAPTURE ONLY. They are deliberately NOT in
# WINDOW_KALSHI: the window card spans every competition, and a capture-only league adds no venue line to it.
KALSHI_CAPTURE_ONLY = EXPANSION_CODES

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
    "soccer-prematch": {  # Friday and Saturday: the PL lines + the expansion leagues' data lines
        "steps": [
            ["sync-matches", *PL],
            ["sync-odds", *PL],
            ["sync-injuries", *PL],
            *[[verb, *x] for x in EXPANSION for verb in ("sync-matches", "sync-odds")],
            *[["sync-kalshi-soccer", "--competition", c] for c in KALSHI_CAPTURE_ONLY],   # capture only
            ["sync-kalshi-soccer"],
            ["predict", "--sport", "soccer", *PL],
            ["export-predictions", "--sport", "soccer", "--competition", "PL",
             "--start", "{sat}", "--end", "{sat_plus3}", "--status", "scheduled"],
        ],
    },
    "soccer-morning-after": {
        "backup": "daily",
        "steps": [
            ["sync-matches", *PL],
            *[["sync-matches", *x] for x in EXPANSION],
            ["evaluate", "--sport", "soccer"],
            ["export-results", "--sport", "soccer", "--competition", "PL"],
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
    "nfl-predict": {
        # Exhibit 1 ruling (2026-09-28): injuries first — the host predicted
        # with 0 injury inputs vs the laptop's 280 (CHAIN GAP). freshen:NFL
        # already had it; the audit found no other gap (MLB has no injury
        # source: sync-injuries MLB is a no-op).
        "steps": [["sync-injuries", "--competition", "NFL", "--season", "2026"],
                  ["capture-weather-nfl"], ["predict-nfl"], ["export-nfl-predictions"]],
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
        ],
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
    # --- Weekly full-season sync (CLAUDE.md: "full-season weekly") ---
    # Steps come from SP_FULLSEASON_LIST (one "CODE|SEASON" per line), written
    # at provisioning from a read-only DB query — per-comp season strings are
    # what the DB stores, never assumed. Missing/empty list = chain FAILS.
    "weekly-fullseason": {
        "backup": "daily",
        "fullseason": True,
        "steps": [],
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
#   then the Kalshi syncs for the competitions in WINDOW_KALSHI, then
#   `window-card`. After a clean run, sp_window_page pages CARD DELTAS (post).
# NO predict/improve step, ever: model fields stay canonical from their slot.
# SP_SKIP_FAMILIES (host.env, e.g. "MLB") drops a family's sync-matches only
# (statsapi.mlb.com 406s the DO ASN; MLB syncing is a laptop duty).
WINDOW_HOURS = 24
WINDOW_KALSHI: dict[str, list[list[str]]] = {
    # competition code -> its Kalshi sync. CI pins the soccer entries to
    # src/adapters/kalshi.py SOCCER_GAME_SERIES (PL; UNL pinned to KXUEFANLGAME,
    # ARCHITECT 2026-10-05, so no --series flag) + SOCCER_SERIES_DISCOVERY,
    # less KALSHI_CAPTURE_ONLY (the soccer-expansion leagues, shadow chain only).
    "MLB": [["sync-kalshi", "--date-from", "{today}", "--date-to", "{tomorrow}"]],
    "NFL": [["sync-kalshi-nfl"]],
    "NCAA": [["sync-kalshi-ncaa"]],
    "NHL": [["sync-kalshi-nhl"]],
    "PL": [["sync-kalshi-soccer", "--competition", "PL"]],
    "UNL": [["sync-kalshi-soccer", "--competition", "UNL"]],
}
CHAINS["window"] = {"window_plan": True, "post": "window_page", "steps": []}

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
CHAINS["freshen:NFL"] = {"steps": [
    ["sync-injuries", "--competition", "NFL", "--season", "2026"],
    ["sync-odds-football"],
    ["sync-kalshi-nfl"],
    ["predict-nfl"],
    ["export-nfl-predictions"],
]}
CHAINS["freshen:MLB"] = {"steps": [list(s) for s in CHAINS["mlb-preslate"]["steps"]]}  # the 10
# MLB CLOSING-RUN AUTOPILOT (ARCHITECT 2026-10-08, addendum 13 item 3, Q2, A1): "It runs the ten mlb-preslate steps
# as chains.py lists them (chains.py stays the one place commands live), with the export carrying the Desk's call."
# Derived from mlb-preslate, never a copy: steps 1-9 are mlb-preslate's own; step 10 is its export plus `--date
# {today}` (the first pitch's America/New_York date, which closing.py sets as {today}: the export's default
# slate is the UTC date, which drops a 22:10 ET game run after 20:00 ET) and `--desk`. LAPTOP ONLY ("the host
# cannot reach the MLB feed"): run through `python cli.py closing-run --family MLB` (deploy/hosting/closing.py), never
# sp_run, which refuses it.
CHAINS["mlb-closing"] = {
    "laptop_only": "python cli.py closing-run --family MLB",
    "steps": [list(s) for s in CHAINS["mlb-preslate"]["steps"][:-1]]
             + [[*CHAINS["mlb-preslate"]["steps"][-1], "--date", "{today}", "--desk"]],
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
# Derived from the freshen chains, never copied: the schedule read first (one UTC day per call: the american-football
# and hockey adapters honour a date window only when from == to, the window service's form; {start_day} and
# {end_day} are the UTC dates of the run's first and last covered start time, and an identical second call is
# dropped by the run), then every freshen step in its order, with these options added:
#   sync-injuries        --kickoff-within-hours {within_h} --strict   (the covered teams; addendum 22 strict mode)
#   sync-odds-football   --match-ids {match_ids}                      (the covered games only)
#   sync-odds            --match-ids {match_ids}                      (the covered games only)
#   the export           --desk                                       (the file carries the Desk's call)
# The Kalshi syncs, predict and predict-nfl run as the freshen chains list them (one series listing each; the model
# step writes every upcoming game, as it always has). Run through `python cli.py closing-run --family F`
# (deploy/hosting/closing.py), never sp_run, which refuses them. C7: "The host runs NFL and SOCCER with the same
# command under a timer from the cutover ruling on, not before." No timer ships here.
_CLOSING_ADD = {
    "sync-injuries": ["--kickoff-within-hours", "{within_h}", "--strict"],
    "sync-odds-football": ["--match-ids", "{match_ids}"],
    "sync-odds": ["--match-ids", "{match_ids}"],
    "export-nfl-predictions": ["--desk"],
    "export-predictions": ["--desk"],
}


def _closing_from_freshen(freshen: str, comp: str, season: str) -> list[list[str]]:
    read = [["sync-matches", "--competition", comp, "--season", season, "--date-from", d, "--date-to", d]
            for d in ("{start_day}", "{end_day}")]
    return read + [[*s, *_CLOSING_ADD.get(s[0], [])] for s in CHAINS[freshen]["steps"]]


# A sample of the run-time placeholders, for the law-1 option check (tests/test_hosting_pack.py) only.
CLOSING_VARS_EXAMPLE = {"start_day": "2026-10-11", "end_day": "2026-10-11", "match_ids": "1,2", "within_h": "0.75"}
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
    "sync-kalshi-ncaa", "evaluate", "nfl-grade", "predict", "predict-nfl",
    "improve", "results-tally", "export-results", "export-predictions", "window-card",
    "export-nfl-predictions", "export-nfl-results", "export-fixtures",
    "export-nhl-predictions",
    "nhl-shot-sync",          # api-web.nhle.com (the NHL's free API), never api-sports
    "export-unl-predictions",  # reads the DB only
})
