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
  P  the live path        per side, the fallback _resolve_pitcher takes on the as-of inputs (above).
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
import bisect
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEFAULT_SEASONS = ["2025", "2026"]
COMPETITION = "MLB"
SOURCE = "mlb_stats_api"                 # MLBStatsAPIAdapter.source_name (the key the stored ids carry)
FINISHED = "FINISHED"                    # MatchStatus.FINISHED as stored (an Enum column stores the member's name)
STALE_ORPHAN = "STALE_ORPHAN"            # MatchStatus.STALE_ORPHAN as stored: never a game
REGULAR = {"R"}                          # the stored gameType (MLBStatsAPIAdapter: stage=game["gameType"])
POSTSEASON = {"F", "D", "L", "W"}        # export.MLB_POSTSEASON_GAME_TYPES
RECENT_DAYS = 10                         # sync_bullpen_stats(recent_window_days=10)
RECENT_MIN_IP = 10.0                     # sync_bullpen_stats(recent_min_ip=10.0)
READS = {"matches": ["id", "competition_id", "season", "utc_date", "status", "stage", "home_team_id", "away_team_id",
                     "external_ids"],
         "competitions": ["id", "code"],
         "teams": ["id", "external_ids"],
         "pitcher_appearances": ["match_id", "source_game_id", "team_source_id", "pitcher_id", "outs", "is_starter",
                                 "earned_runs"],
         "match_participants": ["id", "match_id", "team_id", "role", "kind", "player_source_id", "source", "refreshed_at"],
         "pitcher_season_stats": ["player_source_id", "season", "innings_pitched", "earned_runs"]}


def db_path(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    url = os.getenv("DATABASE_URL")
    if not url:
        try:
            from dotenv import load_dotenv
            load_dotenv(".env")
            url = os.getenv("DATABASE_URL")
        except ImportError:
            pass
    url = url or "sqlite:///./data/sports.db"
    if not url.startswith("sqlite:///"):
        raise SystemExit(f"not a SQLite URL ({url.split(':')[0]}): the receipt is SQLite-only")
    return Path(url.replace("sqlite:///", ""))


def open_read(p: Path):
    """(connection, form). mode=ro first; a copy that refuses it: the plain path with query_only set (#421). It opens
    the database no third way, and never creates one."""
    if not p.is_file():
        raise SystemExit(f"no database at {p}: the receipt never creates one")
    try:
        con = sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True)
        con.execute("SELECT 1 FROM matches LIMIT 1")
        return con, "mode=ro URI"
    except sqlite3.OperationalError:
        con = sqlite3.connect(str(p), timeout=60)
        con.execute("PRAGMA query_only = ON")
        con.execute("SELECT 1 FROM matches LIMIT 1")
        return con, "plain path with PRAGMA query_only = ON (mode=ro refused)"


def check_columns(con) -> list[str]:
    """Law 1: every table and column this receipt reads, as PRAGMA table_info gives them; a missing one refuses."""
    missing = []
    for t, cols in READS.items():
        have = {r[1] for r in con.execute(f'PRAGMA table_info("{t}")')}
        missing += [f"{t}.{c}" for c in cols if c not in have]
    if missing:
        raise SystemExit(f"REFUSED: columns this receipt reads are not in the database: {', '.join(missing)}")
    return [f"{t}({', '.join(c)})" for t, c in READS.items()]


def ext_id(ext) -> str | None:
    """The statsapi id in a stored external_ids value; None where the value is not a JSON object carrying it."""
    try:
        d = json.loads(ext) if isinstance(ext, str) else ext
    except ValueError:
        return None
    return str(d[SOURCE]) if isinstance(d, dict) and d.get(SOURCE) not in (None, "") else None


def kick(v) -> datetime | None:
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v)) if v not in (None, "") else None
    except ValueError:
        return None


def load(con, season: str) -> dict:
    """The season's games, the teams' statsapi ids, the appearances joined to the season's games, the participants'
    starters and the pitcher_season_stats rows."""
    teams = {tid: ext_id(ext) for tid, ext in con.execute("SELECT id, external_ids FROM teams")}
    games = []
    for mid, kickoff, status, stage, h, a, ext in con.execute(
            "SELECT m.id, m.utc_date, m.status, m.stage, m.home_team_id, m.away_team_id, m.external_ids FROM matches m "
            "JOIN competitions c ON c.id = m.competition_id WHERE c.code = ? AND m.season = ? ORDER BY m.utc_date, m.id",
            (COMPETITION, season)):
        games.append({"id": mid, "kick": kick(kickoff), "status": status, "stage": stage, "home": h, "away": a,
                      "pk": ext_id(ext)})
    live = [g for g in games if g["status"] != STALE_ORPHAN]
    held = defaultdict(list)
    for g in live:
        if g["pk"]:
            held[g["pk"]].append(g["id"])
    twins = {pk: ids for pk, ids in held.items() if len(ids) > 1}
    if twins:
        raise SystemExit(
            f"REFUSED (season {season}): {len(twins)} mlb_stats_api id(s) held by more than one stored game (#569). The "
            "receipt reads canonical game ids, after the dedupe (ARCHITECT 2026-10-23, addendum 163 item 4: \"the dedupe "
            "PR precedes this receipt\"): " + "; ".join(f"{pk}: matches {', '.join(map(str, ids))}"
                                                     for pk, ids in sorted(twins.items())))
    orphan_ids = {g["id"] for g in games if g["status"] == STALE_ORPHAN}
    by_id = {g["id"]: g for g in live}
    by_pk = {g["pk"]: g for g in live if g["pk"]}
    apps, left = defaultdict(list), Counter()
    for mid, sgid, team, pid, outs, starter, er in con.execute(
            "SELECT match_id, source_game_id, team_source_id, pitcher_id, outs, is_starter, earned_runs "
            "FROM pitcher_appearances"):
        g = by_id.get(mid) if mid is not None else None
        if g is None and sgid not in (None, ""):
            g = by_pk.get(str(sgid))
        if g is None:
            # a row on a STALE_ORPHAN with no source game id to reach the kept row; else every other season's rows
            left["on a STALE_ORPHAN row only" if mid in orphan_ids else "no stored game of the season"] += 1
            continue
        side = ("home" if team not in (None, "") and str(team) == teams.get(g["home"]) else
                "away" if team not in (None, "") and str(team) == teams.get(g["away"]) else None)
        if side is None:
            left["no side (team_source_id matches neither team)"] += 1
            continue
        apps[g["id"]].append({"side": side, "pid": None if pid in (None, "") else str(pid), "outs": outs or 0,
                              "starter": bool(starter), "er": er})
    parts = defaultdict(dict)
    for mid, team, kind, psid, src, ref in con.execute(
            "SELECT match_id, team_id, kind, player_source_id, source, refreshed_at FROM match_participants "
            "WHERE role = 'starting_pitcher' ORDER BY id"):
        g = by_id.get(mid)
        if g is not None:
            side = "home" if team == g["home"] else "away" if team == g["away"] else None
            if side:                            # the last row wins, as the live read's dict does
                n = parts[mid][side]["n"] + 1 if side in parts[mid] else 1
                parts[mid][side] = {"kind": kind, "psid": None if psid in (None, "") else str(psid), "source": src,
                                    "at": kick(ref), "n": n}
    pss = {str(p): (ip, er) for p, ip, er in con.execute(
        "SELECT player_source_id, innings_pitched, earned_runs FROM pitcher_season_stats WHERE season = ?", (season,))}
    return {"games": games, "apps": apps, "left": left, "parts": parts, "pss": pss}


class Tally:
    """Running sums of outs, earned runs (None once any row lacks them) and starts, keyed by pitcher or by team."""

    def __init__(self):
        self.outs, self.er, self.er_missing, self.gs, self.n = Counter(), Counter(), Counter(), Counter(), Counter()

    def add(self, key, a):
        self.n[key] += 1
        self.outs[key] += a["outs"]
        self.gs[key] += a["starter"]
        if a["er"] is None:
            self.er_missing[key] += 1
        else:
            self.er[key] += a["er"]


def reconstruct(d: dict) -> dict:
    """Walk the season's finished regular games in kickoff order; each group of games sharing a kickoff reads the
    sums before any of them is added (strictly earlier starts only)."""
    games = d["games"]
    c = Counter()
    for g in games:
        c[f"status {g['status']}"] += 1
    fin = [g for g in games if g["status"] == FINISHED]
    for g in fin:
        st = g["stage"]
        c["finished " + ("regular" if st in REGULAR else "postseason" if st in POSTSEASON else "stage unknown")] += 1
    reg = sorted([g for g in fin if g["stage"] in REGULAR and g["kick"] is not None], key=lambda g: (g["kick"], g["id"]))
    c["regular without a kickoff"] = sum(1 for g in fin if g["stage"] in REGULAR and g["kick"] is None)
    pitch, pen = Tally(), Tally()
    recent = defaultdict(list)                       # team id -> [(kick, n, outs, er NULL)] relief, sorted (n: order)
    n = 0
    i = 0
    while i < len(reg):
        j = i
        while j < len(reg) and reg[j]["kick"] == reg[i]["kick"]:
            j += 1
        for g in reg[i:j]:
            read_game(g, d, pitch, pen, recent, c)
        for g in reg[i:j]:
            for a in d["apps"].get(g["id"], []):
                team = g[a["side"]]
                if a["pid"]:
                    pitch.add(a["pid"], a)
                if not a["starter"]:
                    pen.add(team, a)
                    n += 1
                    bisect.insort(recent[team], (g["kick"], n, a["outs"], a["er"] is None))
        i = j
    c["regular games read"] = len(reg)
    return c


def read_game(g, d, pitch, pen, recent, c):
    apps = d["apps"].get(g["id"], [])
    sides = {a["side"] for a in apps}
    c["A both sides" if len(sides) == 2 else "A one side" if sides else "A none"] += 1
    c["A rows"] += len(apps)
    c["A rows earned_runs NULL"] += sum(1 for a in apps if a["er"] is None)
    for side in ("home", "away"):
        box = [a["pid"] for a in apps if a["side"] == side and a["starter"]]
        part = d["parts"].get(g["id"], {}).get(side)
        model = part["psid"] if part else None
        c[f"S model starter {'kind ' + str(part['kind']) if part else 'none listed'}"] += 1
        if part:
            at = part["at"]
            c[f"S identity source {part['source']}"] += 1
            c["S identity " + ("no refreshed_at" if at is None else "refreshed by kickoff" if at <= g["kick"] else
                               "refreshed after kickoff (the pregame identity is not shown)")] += 1
            if part["n"] > 1:
                c["S identity more than one row (the live read takes the last)"] += 1
        if len(box) > 1:
            c["S boxscore starter: more than one"] += 1
        bx = box[0] if len(box) == 1 else None
        c["S starters " + ("agree" if model and bx and model == bx else "differ" if model and bx else
                           "model only" if model else "boxscore only" if bx else "neither")] += 1
        # the as-of figures read the MODEL's starter only: the boxscore's is the comparison above, never an input
        starter = False
        if part is None:
            c["S asof no starter listed (no pitcher input for the side)"] += 1
        elif not model:
            c["S asof listed without a source id (no starter stats)"] += 1
        elif not pitch.n[model]:
            c["S asof no prior appearance this season (no stats)"] += 1
        elif not pitch.gs[model]:
            c["S asof opener (GS 0, no starter component)"] += 1
        elif pitch.outs[model] <= 0:
            c["S asof starts but no outs (no stats)"] += 1
        else:
            starter = True
            c["S asof starter component, ERA " +
              ("incomplete (earned_runs NULL on a prior row)" if pitch.er_missing[model] else "complete")] += 1
        team = g[side]
        bullpen = pen.outs[team] > 0
        if not bullpen:
            c["B season: no prior relief IP"] += 1
        else:
            c["B season: ERA " + ("incomplete" if pen.er_missing[team] else "complete")] += 1
        rows = recent.get(team, [])
        lo = bisect.bisect_left(rows, (datetime.combine(g["kick"].date() - timedelta(days=RECENT_DAYS), time.min),))
        hi = bisect.bisect_left(rows, (g["kick"],))
        win = rows[lo:hi]
        ip = sum(r[2] for r in win) / 3
        c["B recent 10 days: " + (f"< {RECENT_MIN_IP:g} IP" if ip < RECENT_MIN_IP else f">= {RECENT_MIN_IP:g} IP, ERA "
                                  + ("incomplete" if any(r[3] for r in win) else "complete"))] += 1
        c["P " + ("no pitcher input (no starter listed)" if part is None else
                  "blend: starter and bullpen" if starter and bullpen else
                  "starter, league bullpen" if starter else
                  "bullpen half-weighted, starter unknown" if bullpen else "neutral (no data)")] += 1


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
             f"refreshed by kickoff {c['S identity refreshed by kickoff']}/{sides}")
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
