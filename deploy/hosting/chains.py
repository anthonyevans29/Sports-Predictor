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
    "soccer-prematch": {  # Friday and Saturday: the same six lines
        "steps": [
            ["sync-matches", *PL],
            ["sync-odds", *PL],
            ["sync-injuries", *PL],
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
        ],
    },
    "ncaa-market": {
        "steps": [["sync-kalshi-ncaa"], ["export-fixtures", "--competition", "NCAA"]],
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
    # src/adapters/kalshi.py SOCCER_GAME_SERIES (only PL has a series).
    "MLB": [["sync-kalshi", "--date-from", "{today}", "--date-to", "{tomorrow}"]],
    "NFL": [["sync-kalshi-nfl"]],
    "NCAA": [["sync-kalshi-ncaa"]],
    "NHL": [["sync-kalshi-nhl"]],
    "PL": [["sync-kalshi-soccer", "--competition", "PL"]],
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
CHAINS["freshen:SOCCER"] = {"steps": [
    ["sync-odds", *PL],
    ["sync-injuries", *PL],
    ["sync-kalshi-soccer", "--competition", "PL"],
    ["predict", "--sport", "soccer", *PL],
    # export windowing (architect 2026-09-28): no dates -> the 36h current
    # slate, so a closing freshen yields a one-slate file
    ["export-predictions", "--sport", "soccer", "--competition", "PL", "--status", "scheduled"],
]}
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
})
