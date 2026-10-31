"""
MLB AS-OF PITCHER INPUTS (lane mlb-pitchers, #507): the reconstruction of the live pitcher layer's inputs AS OF each
game, from the stored appearances, shared by the read-only receipt (scripts/mlb_pitcher_asof_receipt.py, #702 / #703)
and the mlb-pitchers-v1 harness (ARCHITECT 2026-10-31 11:45 ET, addendum 190; src/walters/mlb_pitchers_gate.py,
docs/specs/mlb-pitchers-v1.md).

The as-of logic below is the receipt's, MOVED here without a change of logic (the receipt imports it and its console is
byte-identical; tests/test_mlb_pitcher_asof_receipt.py pins it): db_path / open_read / check_columns, load, Tally, the
kickoff-group walk (reconstruct) and the per-side classification (read_game), PATHS. What the receipt's docstring says
about the reconstruction is the definition here.

Added for the harness (addendum 190 item 7), without changing what the receipt counts:
  - the recent bullpen window carries its earned runs (a fifth element of each row; the rows sort on (kick, n), n
    unique, so the order and every count are unchanged), so the window's ERA can be computed;
  - classify(d, season): per regular-season game the receipt reads, per side, the P label (the same predicate and the
    same order of labels: read_game computes the label once and counts it) and, for a side on a live path (PATHS),
    the as-of sums: starter (outs, er, gs) when the starter component exists; bullpen season (outs, er) when the team
    has prior relief outs; the recent window (outs, er) when it holds >= 10 IP;
  - cohort_ids(classification): the games whose BOTH sides' P label is in PATHS (addendum 190 item 2);
  - pitcher_stats_asof(...): the ON arm's PitcherStats, built EXACTLY as the live _resolve_pitcher
    (src/walters/training.py, _generate_predictions_mlb) builds them, from the as-of sums instead of
    pitcher_season_stats / bullpen_season_stats (training.py is not modified; tests/test_mlb_pitchers_v1.py pins the
    live equality);
  - missing_starter_shrink(...): the live path's Phase 12.3 missing-starter shrink, copied exactly (applied in the ON
    arm for a side whose PitcherStats has starter_known False: Code's reading (d), docs/specs/mlb-pitchers-v1.md).
"""
from __future__ import annotations

import bisect
import json
import os
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta
from pathlib import Path

COMPETITION = "MLB"
SOURCE = "mlb_stats_api"                 # MLBStatsAPIAdapter.source_name (the key the stored ids carry)
FINISHED = "FINISHED"                    # MatchStatus.FINISHED as stored (an Enum column stores the member's name)
STALE_ORPHAN = "STALE_ORPHAN"            # MatchStatus.STALE_ORPHAN as stored: never a game
REGULAR = {"R"}                          # the stored gameType (MLBStatsAPIAdapter: stage=game["gameType"])
POSTSEASON = {"F", "D", "L", "W"}        # export.MLB_POSTSEASON_GAME_TYPES
RECENT_DAYS = 10                         # sync_bullpen_stats(recent_window_days=10)
RECENT_MIN_IP = 10.0                     # sync_bullpen_stats(recent_min_ip=10.0)
PATHS = ("P blend: starter and bullpen", "P starter, league bullpen", "P bullpen half-weighted, starter unknown",
         "P neutral (no data)")              # a path read on a listed, pregame identity and complete ERAs (#703)
READS = {"matches": ["id", "competition_id", "season", "utc_date", "status", "stage", "home_team_id", "away_team_id",
                     "external_ids"],
         "competitions": ["id", "code"],
         "teams": ["id", "external_ids"],
         "pitcher_appearances": ["match_id", "source_game_id", "team_source_id", "pitcher_id", "outs", "is_starter",
                                 "earned_runs"],
         "match_participants": ["id", "match_id", "team_id", "role", "kind", "player_source_id", "source", "refreshed_at"],
         "pitcher_season_stats": ["player_source_id", "season", "innings_pitched", "earned_runs"]}
SIDES = ("home", "away")

# The live path's constants (src/walters/training.py, _generate_predictions_mlb; read 2026-10-31, not imported: they
# are locals there). tests/test_mlb_pitchers_v1.py pins the ON arm against the live function itself.
STARTER_WEIGHT = 5.5 / 9.0               # 0.611
BULLPEN_WEIGHT = 3.5 / 9.0               # 0.389
BULLPEN_HALFLIFE_IP = 50.0
BULLPEN_RECENT_WEIGHT = 0.30
SHRINK_ONE, SHRINK_TWO = 0.88, 0.76      # Phase 12.3: one side unknown, both sides unknown


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


def reconstruct(d: dict, out: dict | None = None) -> dict:
    """Walk the season's finished regular games in kickoff order; each group of games sharing a kickoff reads the
    sums before any of them is added (strictly earlier starts only). `out` (classify): a dict that receives, per game
    read, its kickoff and per side the P label and the as-of sums (read_game); the counts are the same either way."""
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
    # team id -> [(kick, n, outs, er NULL, er)] relief, sorted (n: order, unique, so the rows never compare past it)
    recent = defaultdict(list)
    n = 0
    i = 0
    while i < len(reg):
        j = i
        while j < len(reg) and reg[j]["kick"] == reg[i]["kick"]:
            j += 1
        for g in reg[i:j]:
            read_game(g, d, pitch, pen, recent, c, out)
        for g in reg[i:j]:
            for a in d["apps"].get(g["id"], []):
                team = g[a["side"]]
                if a["pid"]:
                    pitch.add(a["pid"], a)
                if not a["starter"]:
                    pen.add(team, a)
                    n += 1
                    bisect.insort(recent[team], (g["kick"], n, a["outs"], a["er"] is None, a["er"]))
        i = j
    c["regular games read"] = len(reg)
    return c


def read_game(g, d, pitch, pen, recent, c, out: dict | None = None):
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
        # #703: the path stands only on an identity observed by kickoff and on ERAs the appearances rebuild whole (the
        # live loader admits a row only with a usable ERA); either missing is counted under its own name, never a path
        pregame = part is not None and part["at"] is not None and part["at"] <= g["kick"]
        torn = ((starter and pitch.er_missing[model] > 0) or
                (bullpen and (pen.er_missing[team] > 0 or (ip >= RECENT_MIN_IP and any(r[3] for r in win)))))
        label = ("P " + ("no pitcher input (no starter listed)" if part is None else
                         "identity not established pregame (refreshed after kickoff, or no time)" if not pregame else
                         "not reconstructable (an ERA the path reads is incomplete: earned_runs NULL)" if torn else
                         "blend: starter and bullpen" if starter and bullpen else
                         "starter, league bullpen" if starter else
                         "bullpen half-weighted, starter unknown" if bullpen else "neutral (no data)"))
        c[label] += 1
        if out is not None:
            on_path = label in PATHS
            out.setdefault(g["id"], {"kick": g["kick"]})[side] = {
                "label": label,
                "name": model or "",
                "starter": (pitch.outs[model], pitch.er[model], pitch.gs[model]) if on_path and starter else None,
                "bullpen": (pen.outs[team], pen.er[team]) if on_path and bullpen else None,
                "recent": ((sum(r[2] for r in win), sum(r[4] for r in win))
                           if on_path and bullpen and ip >= RECENT_MIN_IP else None),
            }


# ------------------------------------------------------------------------------------------------ the harness --

def classify(d: dict, season: str) -> dict:
    """The receipt's classification, per game: {"season", "counts" (the receipt's Counter, unchanged), "games": {match
    id: {"kick", "home": side, "away": side}}}, one entry per regular-season game the receipt reads. A side is {"label"
    (the P label, "P ..." as counted), "name" (the model's starter's source id, or ""), "starter" (outs, er, gs) | None,
    "bullpen" (outs, er) | None, "recent" (outs, er) | None}; the sums are set only for a side whose label is in PATHS
    (a live path), and each only when that input exists as of the game (the starter component; prior relief outs;
    a recent window of >= 10 IP)."""
    games: dict = {}
    c = reconstruct(d, out=games)
    return {"season": season, "counts": c, "games": games}


def on_path_sides(g: dict) -> int:
    """How many of a classified game's sides are on a live path (0, 1 or 2): sum over sides of one[k] for k in PATHS."""
    return sum(1 for side in SIDES if g[side]["label"] in PATHS)


def cohort_ids(classification: dict) -> list[int]:
    """Addendum 190 item 2: the season's regular-season games with BOTH sides reconstructed on a live path (both
    sides' P label in PATHS), sorted by id."""
    return sorted(mid for mid, g in classification["games"].items() if on_path_sides(g) == 2)


def pitcher_stats_asof(side: dict, cfg):
    """The ON arm's PitcherStats for one classified side, built EXACTLY as the live _resolve_pitcher builds them
    (src/walters/training.py, _generate_predictions_mlb), from the as-of sums instead of the stored rows:
      starter   era = 27 * er / outs, ip = outs / 3, gs (the live row is admitted only with ip > 0); gs == 0 is an
                opener (no starter component); else w from starter_shrink_weight(ip, gs, cfg), shrunk toward
                cfg.league_era;
      bullpen   season era = 27 * er / outs, ip = outs / 3 (admitted only with ip > 0); the recent window's era
                = 27 * er / outs when its IP >= 10 (sync_bullpen_stats' recent_min_ip), effective = 0.7 * season
                + 0.3 * recent (BULLPEN_RECENT_WEIGHT); shrink w = ip / (ip + 50) toward cfg.league_era;
      the blend starter and bullpen 0.611 / 0.389 (starter_known True); starter and the league bullpen (True);
                0.5 * bullpen + 0.5 * league_era (False); neither: era None (False).
    A side with no participant row has no PitcherStats in the live path (None); such a side is never on a path."""
    from src.models.baseball import PitcherStats, starter_shrink_weight

    name = side.get("name") or ""
    starter_era = None
    st = side.get("starter")
    if st is not None and st[0] > 0:
        outs, er, gs = st
        era, ip = 27 * er / outs, outs / 3
        if gs == 0:
            starter_era = None
        else:
            eff_ip, w = starter_shrink_weight(ip, gs, cfg)
            starter_era = w * era + (1 - w) * cfg.league_era
    bullpen_era = None
    bp = side.get("bullpen")
    if bp is not None and bp[0] > 0:
        outs, er = bp
        season_era, bp_ip = 27 * er / outs, outs / 3
        effective_era = season_era
        rc = side.get("recent")
        if rc is not None and rc[0] > 0 and rc[0] / 3 >= RECENT_MIN_IP:
            recent_era = 27 * rc[1] / rc[0]
            effective_era = ((1 - BULLPEN_RECENT_WEIGHT) * season_era
                             + BULLPEN_RECENT_WEIGHT * recent_era)
        w = bp_ip / (bp_ip + BULLPEN_HALFLIFE_IP)
        bullpen_era = w * effective_era + (1 - w) * cfg.league_era
    if starter_era is not None and bullpen_era is not None:
        blended = (STARTER_WEIGHT * starter_era +
                   BULLPEN_WEIGHT * bullpen_era)
        return PitcherStats(name=name, era=blended, starter_known=True)
    elif starter_era is not None:
        blended = (STARTER_WEIGHT * starter_era +
                   BULLPEN_WEIGHT * cfg.league_era)
        return PitcherStats(name=name, era=blended, starter_known=True)
    elif bullpen_era is not None:
        blended = 0.5 * bullpen_era + 0.5 * cfg.league_era
        return PitcherStats(name=name, era=blended, starter_known=False)
    return PitcherStats(name=name, era=None, starter_known=False)


def missing_starter_shrink(p_home: float, p_away: float, home_pitcher, away_pitcher) -> tuple[float, float]:
    """The live path's Phase 12.3 missing-starter shrink (src/walters/training.py, after predict_game), copied exactly:
    each side whose pitcher is None or not starter_known counts as missing; one missing shrinks toward 0.5 by 0.88,
    two by 0.76, then the pair is renormalised. Nothing missing: unchanged."""
    missing = 0
    if home_pitcher is None or not home_pitcher.starter_known:
        missing += 1
    if away_pitcher is None or not away_pitcher.starter_known:
        missing += 1
    if missing > 0:
        shrink = SHRINK_ONE if missing == 1 else SHRINK_TWO
        p_home_adj = 0.5 + (p_home - 0.5) * shrink
        p_away_adj = 0.5 + (p_away - 0.5) * shrink
        tot = p_home_adj + p_away_adj
        return p_home_adj / tot, p_away_adj / tot
    return p_home, p_away
