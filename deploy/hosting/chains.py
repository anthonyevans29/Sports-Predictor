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
        "steps": [["capture-weather-nfl"], ["predict-nfl"], ["export-nfl-predictions"]],
    },
    # --- Market-only (docs/CLI.md "Market-only competitions") ---
    "nhl-daily": {
        "backup": "daily",
        "active_from": "2026-10-07",  # market-only launch
        "steps": [
            ["sync-matches", "--competition", "NHL", "--season", "2026",
             "--date-from", "{yesterday}", "--date-to", "{tomorrow}"],
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

# Commands verified NOT to call a metered api-sports product (2026-09-27: the
# cli.py command bodies construct no IngestionService / adapter / requests
# call, and src/walters/ does no network I/O; Kalshi is public). Everything
# else is treated as METERED — conservative unknowns (law 4). Only consulted
# in H0-16(b) designated-days mode. tests/test_hosting_pack.py re-checks it.
UNMETERED = frozenset({
    "sync-kalshi", "sync-kalshi-soccer", "sync-kalshi-nfl", "sync-kalshi-nhl",
    "sync-kalshi-ncaa", "evaluate", "nfl-grade", "predict", "predict-nfl",
    "improve", "results-tally", "export-results", "export-predictions",
    "export-nfl-predictions", "export-nfl-results", "export-fixtures",
})
