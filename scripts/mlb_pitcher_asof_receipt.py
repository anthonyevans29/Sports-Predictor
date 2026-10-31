"""
MLB AS-OF PITCHER RECEIPT (lane mlb-pitchers, #507; roadmap step "the as-of reconstruction of the pitcher statistics the
live model reads, from the stored appearances (docs/historical_backfill_assessment.md tier 1), as a read-only receipt:
coverage per season", code, due 2026-10-28; ARCHITECT 2026-10-13, addendum 63 item 4) — read-only, counts only.

The next step is the architect's declaration: "the backtest with the pitcher layer on and off, the same games, the MLB
bar (0.0050) as the pre-committed margin, on the 2025 and 2026 regular seasons". This receipt says how much of that
layer the stored appearances can rebuild AS OF each game, so the declaration knows its coverage. No model is run, no
probability is computed, nothing is written.

The ruling the receipt answers (ARCHITECT 2026-10-23, addendum 163 item 4, verbatim): "the 10-28 receipt reconstructs
the WHOLE live layer as of each game (starter stats from prior appearances, starter identity with its source and time,
bullpen as-of totals and the recent window, the exact missing-input fallback, the canonical game ids after the #569
dedupe — the dedupe PR precedes this receipt)".

WHAT THE LIVE MODEL READS (src/walters/training.py, predict path; read 2026-10-26), per side of a game:
  starter    the side's starting_pitcher in match_participants (name, player_source_id; the read has no ORDER BY, so
             with more than one row for a side the last row it yields wins), and that pitcher's pitcher_season_stats
             row for the game's own season (addendum 162 item 1(b)): era, innings_pitched, games_started.
             games_started 0 = an opener (no starter component); no row = "no stats".
  bullpen    the team's bullpen_season_stats row for the season: era, innings_pitched, and recent_era (the relief of
             the calendar dates today - 10 days to today, both inclusive: sync_bullpen_stats' recent_window_days and
             the adapter's startDate/endDate; weighted only from 10 IP, recent_min_ip).
  fallback   _resolve_pitcher, per side: no starting_pitcher row = no pitcher input for the side (None); a row with a
             starter component and a bullpen = the blend; a starter component and no bullpen = starter with the
             league bullpen; no starter component (no source id, no stats, an opener) and a bullpen = the bullpen
             half-weighted, starter unknown; neither = neutral.
  Both tables hold the season TO DATE at their last refresh, so a past game read from them sees later games. The
  as-of reconstruction below rebuilds the same quantities from pitcher_appearances, using only games that started
  before the game read.

THE RECONSTRUCTION (per season; a game's season is matches.season as stored):
  games         STALE_ORPHAN rows are never a game (counted under G only). A statsapi id held by more than one other
                row of the season (#569's twins) REFUSES the receipt, naming the match ids: its game ids are
                canonical only after the dedupe.
  appearances   pitcher_appearances rows joined to OUR game by match_id, else by the statsapi id in source_game_id
                (matches.external_ids["mlb_stats_api"]); a row joining to no stored game is left out, counted.
  side          an appearance's team_source_id against each team's statsapi id (teams.external_ids["mlb_stats_api"]);
                one matching neither team is left out, counted.
  as of a game  the season's appearances of games whose stored kickoff (matches.utc_date) is strictly before the
                game's; a doubleheader's second game sees the first only when it started earlier.
  starter       the MODEL's starter only (match_participants): IP = outs / 3, ER = the sum of earned_runs, GS = the
                appearances with is_starter, over the pitcher's prior appearances. An appearance whose earned_runs is
                NULL (older captures predate the field) leaves the ERA incomplete: counted, never filled. The
                boxscore's starter is a comparison only, never put in the model's place.
  identity      the participant row's source and refreshed_at against the kickoff: refreshed by kickoff, after it
                (the stored identity is the last refresh's, so the pregame one is not shown), or no time.
  bullpen       the same sums over the team's prior relief appearances (is_starter false); recent = those of games on
                the kickoff's calendar date (UTC) minus 10 days up to the kickoff (the live window's inclusive lower
                date; the provider's dates are local, so a late game near the bound can differ by a day), its ERA
                incomplete when any row in it lacks earned_runs.

Sections, per season (default 2025 and 2026):
  G  the games            the MLB competition's games of the season by status; FINISHED games by stage (stored
                          gameType: R regular, F/D/L/W postseason, other or none: unknown, left out and counted).
                          Everything below reads the FINISHED regular-season games.
  A  the appearances      games with appearance rows for both sides, one side, none; rows left out (no stored game,
                          no side); rows with earned_runs NULL.
  S  the starter          per side: the starter the model reads (match_participants, kind counted), its identity's
                          source and time, and the starter the boxscore names (appearances, is_starter); agree /
                          differ / one missing. Then, for the model's starter, the as-of figures: none listed; listed
                          without a source id; no prior appearance this season (the model's "no stats"); prior
                          appearances, opener (GS 0); a starter component (GS > 0, IP > 0) with its ERA complete or
                          incomplete.
  B  the bullpen          per side: prior relief IP > 0 with ERA complete / incomplete, none; the recent window at
                          10 IP or more, its ERA complete / incomplete.
  P  the live path        per side, the fallback _resolve_pitcher takes on the as-of inputs (above). It stands only
                          on an identity refreshed by kickoff and on complete ERAs (#703): a listed identity refreshed
                          after kickoff (or with no time), and a component whose ERA is incomplete (season, or a recent
                          window of 10 IP or more), are counted under their own names, never as a path.
  C  the cross-check      per pitcher_season_stats row of the season: the season's REGULAR-season appearance outs
                          (the stored row is the provider's regular-season split) against its innings_pitched x 3
                          (agree within one out / differ / no appearances), and earned_runs the same way. Counts only.
  Summary                 per season, the as-of coverage of each input, x/y.

The database is opened mode=ro (a copy that refuses it: the plain path with PRAGMA query_only = ON, the form printed,
#421); never created. Nothing is fetched.

Run:  python3 scripts/mlb_pitcher_asof_receipt.py [--db PATH] [--seasons 2025,2026]
Paste the whole output to the architect.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The as-of logic lives in src/walters/mlb_pitcher_asof.py (moved there without a change of logic for the
# mlb-pitchers-v1 harness, ARCHITECT 2026-10-31, addendum 190 item 7); this receipt's console is byte-identical.
from src.walters.mlb_pitcher_asof import (COMPETITION, FINISHED, PATHS, POSTSEASON, READS, RECENT_DAYS,  # noqa: E402,F401
                                          RECENT_MIN_IP, REGULAR, SOURCE, STALE_ORPHAN, Tally, check_columns,
                                          db_path, ext_id, kick, load, open_read, read_game, reconstruct)

DEFAULT_SEASONS = ["2025", "2026"]


def cross_check(d: dict) -> Counter:
    """pitcher_season_stats rows of the season against the season's REGULAR-season appearance sums: the stored row is
    the provider's first split, the regular season (MLBStatsAPIAdapter.get_pitcher_season_stats)."""
    outs, er, er_null = Counter(), Counter(), Counter()
    for g in d["games"]:
        if g["stage"] not in REGULAR or g["status"] == STALE_ORPHAN:
            continue
        for a in d["apps"].get(g["id"], []):
            if a["pid"]:
                outs[a["pid"]] += a["outs"]
                if a["er"] is None:
                    er_null[a["pid"]] += 1
                else:
                    er[a["pid"]] += a["er"]
    c = Counter()
    for pid, (ip, ers) in d["pss"].items():
        if pid not in outs:
            c["no appearances"] += 1
            continue
        c["IP " + ("agree" if abs(outs[pid] - round((ip or 0) * 3)) <= 1 else "differ")] += 1
        c["ER " + ("NULL on a row" if er_null[pid] else "agree" if er[pid] == (ers or 0) else "differ")] += 1
    return c


def lines(season: str, d: dict, c: Counter, x: Counter) -> list[str]:
    n = c["regular games read"]
    sides = 2 * n

    def part(prefix):
        return " · ".join(f"{k[len(prefix):]} {v}" for k, v in sorted(c.items()) if k.startswith(prefix)) or "none"
    L = [f"\n== season {season}",
         "  G games: " + " · ".join(f"{k} {v}" for k, v in sorted(c.items()) if k.startswith(("status ", "finished ")))
         + f" · regular without a kickoff {c['regular without a kickoff']} · regular games read {n}",
         f"  A appearances: both sides {c['A both sides']} · one side {c['A one side']} · none {c['A none']} · rows "
         f"{c['A rows']} (earned_runs NULL {c['A rows earned_runs NULL']}) · left out: "
         + (" · ".join(f"{k} {v}" for k, v in sorted(d["left"].items())) or "none"),
         f"  S starter, per side ({sides}): " + part("S model starter "),
         "    the model's against the boxscore's: " + part("S starters "),
         "    identity: " + part("S identity "),
         "    as of the game, the model's starter: " + part("S asof "),
         f"  B bullpen, per side ({sides}): " + part("B "),
         f"  P the live path as of the game, per side ({sides}): " + part("P "),
         f"  C cross-check, pitcher_season_stats {season} rows {len(d['pss'])}: "
         + (" · ".join(f"{k} {v}" for k, v in sorted(x.items())) or "none")]
    comp = c["S asof starter component, ERA complete"]
    L.append(f"  SUMMARY {season}: regular games {n} · appearances both sides {c['A both sides']}/{n} · a starter "
             f"component as of the game (ERA complete) {comp}/{sides} · bullpen season ERA complete "
             f"{c['B season: ERA complete']}/{sides} · bullpen recent >= {RECENT_MIN_IP:g} IP "
             f"(ERA complete) {c[f'B recent 10 days: >= {RECENT_MIN_IP:g} IP, ERA complete']}/{sides} · identity "
             f"refreshed by kickoff {c['S identity refreshed by kickoff']}/{sides} · the live path reconstructed "
             f"(identity by kickoff, ERAs complete) {sum(c[k] for k in PATHS)}/{sides}")
    return L


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default=None, help="SQLite file (default: DATABASE_URL, else ./data/sports.db)")
    ap.add_argument("--seasons", default=",".join(DEFAULT_SEASONS), help="stored seasons, comma-separated")
    a = ap.parse_args(argv)
    p = db_path(a.db)
    con, form = open_read(p)
    read = check_columns(con)
    print(f"MLB AS-OF PITCHER RECEIPT (lane mlb-pitchers, #507) · read-only, counts only · database {p} ({form})")
    print("  reads: " + " · ".join(read))
    print(f"  as of a game: the season's appearances of games that started strictly before it · recent bullpen window "
          f"{RECENT_DAYS} days, weighted from {RECENT_MIN_IP:g} IP (sync_bullpen_stats) · no model is run")
    for season in [s.strip() for s in a.seasons.split(",") if s.strip()]:
        d = load(con, season)
        c = reconstruct(d)
        for line in lines(season, d, c, cross_check(d)):
            print(line)
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
