"""
MLB PITCHER COVERAGE PROBE (ARCHITECT 2026-10-14 10:01 ET, addendum 67 item 2; roadmap lane mlb-pitchers, #507) —
read-only.

Verbatim: "`scripts/mlb_pitcher_probe.py`, the shape of the other probes: nothing written, paste-whole output. Per
season 2024, 2025, 2026, from the DB: finished games; games with a starting pitcher recorded for both sides (from
whatever table holds appearances — enumerate the table and its columns first, law 1, and print which you used); games
with neither; and from the provider (statsapi, the laptop's network mode): for a sample of ten finished games per
season, whether the schedule hydrate names the probable starters, and for the next unplayed game whether the
probables are named now and at what hour they appeared if the payload says. Print the keys used. Summary lines per
season: starters recorded x/y, probables available on the sample z/10. The block that runs it is mine."

  D0  the database                 opened mode=ro (a copy that refuses it: the plain path with PRAGMA query_only = ON,
                                   the form printed, #421); every table whose name or columns speak of a pitcher or a
                                   starter, with its columns as PRAGMA table_info gives them; the table and columns
                                   this probe reads, printed
  D1  per season (2024..2026)      the MLB competition's games by stored status; finished games (status FINISHED);
                                   of those, games with a starter recorded for both sides, for one side only, and for
                                   neither (pitcher_appearances, is_starter = 1, by match_id or by the statsapi game
                                   id in source_game_id; a side is a distinct team_source_id); and, as a second read,
                                   the starters the predict path stores (match_participants, role starting_pitcher,
                                   each kind counted)
  P1  per season, ten finished     evenly spaced by kickoff among the season's finished games that carry a statsapi id
      games                        (matches.external_ids[MLBStatsAPIAdapter.source_name]): /schedule?sportId=1&gamePk=
                                   &hydrate=probablePitcher (the adapter's own call, get_probable_pitchers' params);
                                   per game, whether teams.home and teams.away each name a probablePitcher, and the
                                   keys the answer's game block and probablePitcher blocks carry
  P2  the next unplayed game       the DB's next MLB game not finished, after now, with a statsapi id: the same call;
                                   whether the probables are named now; and every key of the game block and of each
                                   probablePitcher block whose name speaks of a time or a date (the hour they appeared,
                                   if the payload says; a payload that does not say is printed as not saying)
  Summary                          per season: starters recorded x/y, probables available on the sample z/10

The base URL and the pace are the adapter's (src/adapters/mlb_stats_api.py: _BASE_URL, MLBStatsAPIAdapter._get and its
throttle). It never stops on an error: a call that fails is printed and counted. It writes nothing and changes no row.

Run:  python3 scripts/mlb_pitcher_probe.py [--db PATH] [--seasons 2024,2025,2026] [--sample 10] [--no-network]
Paste the whole output to the architect.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEFAULT_SEASONS = ["2024", "2025", "2026"]
SAMPLE = 10
COMPETITION = "MLB"
FINISHED = "FINISHED"            # MatchStatus.FINISHED as stored (an Enum column stores the member's name)
WORDS = ("pitch", "starter", "participant")
TIME_WORDS = ("time", "date", "updated", "ts", "when", "announced")
APPEARANCES = "pitcher_appearances"
PARTICIPANTS = "match_participants"


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
        raise SystemExit(f"not a SQLite URL ({url.split(':')[0]}): the probe is SQLite-only")
    return Path(url.replace("sqlite:///", ""))


def open_read(p: Path):
    """(connection, form). mode=ro first; a copy that refuses it: the plain path with query_only set (#421). It opens
    the database no third way, and never creates one."""
    if not p.is_file():
        raise SystemExit(f"no database at {p}: the probe never creates one")
    try:
        con = sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True)
        con.execute("SELECT 1 FROM matches LIMIT 1")
        return con, "mode=ro URI"
    except sqlite3.OperationalError:
        con = sqlite3.connect(str(p), timeout=60)
        con.execute("PRAGMA query_only = ON")
        con.execute("SELECT 1 FROM matches LIMIT 1")
        return con, "plain path with PRAGMA query_only = ON (mode=ro refused)"


def tables(con) -> dict[str, list[str]]:
    """{table: [column, ...]} for every table whose name or columns speak of a pitcher or a starter (law 1)."""
    out = {}
    for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        cols = [r[1] for r in con.execute(f'PRAGMA table_info("{t}")')]
        if any(w in t.lower() for w in WORDS) or any(any(w in c.lower() for w in WORDS) for c in cols):
            out[t] = cols
    return out


def source_name() -> str:
    from src.adapters.mlb_stats_api import MLBStatsAPIAdapter
    return MLBStatsAPIAdapter.source_name


def season_games(con, season: str) -> list[dict]:
    """The MLB competition's games of one stored season: id, kickoff, status, the statsapi game id (or None)."""
    src = source_name()
    rows = con.execute(
        "SELECT m.id, m.utc_date, m.status, m.external_ids FROM matches m JOIN competitions c "
        "ON c.id = m.competition_id WHERE c.code = ? AND m.season = ? ORDER BY m.utc_date, m.id",
        (COMPETITION, season)).fetchall()
    out = []
    for mid, kick, status, ext in rows:
        try:
            gid = (json.loads(ext) if isinstance(ext, str) else (ext or {})).get(src)
        except (ValueError, AttributeError):
            gid = None
        out.append({"id": mid, "kickoff": kick, "status": status, "game_pk": None if gid is None else str(gid)})
    return out


def starters(con, games: list[dict]) -> dict[int, int]:
    """{match id: sides with a starter} from pitcher_appearances (is_starter = 1), by match_id or by the statsapi game
    id in source_game_id; a side is a distinct team_source_id."""
    by_pk = {g["game_pk"]: g["id"] for g in games if g["game_pk"]}
    ids = {g["id"] for g in games}
    sides: dict[int, set] = {}
    for mid, sgid, team in con.execute(
            f"SELECT match_id, source_game_id, team_source_id FROM {APPEARANCES} WHERE is_starter = 1"):
        m = mid if mid in ids else by_pk.get(str(sgid)) if sgid is not None else None
        if m is not None:
            sides.setdefault(m, set()).add(team)
    return {m: len(s) for m, s in sides.items()}


def participants(con, games: list[dict]) -> Counter:
    """match_participants' starting pitchers on the finished games: (kind, sides) counted."""
    ids = {g["id"] for g in games}
    per: dict[tuple, set] = {}
    for mid, team, kind in con.execute(
            f"SELECT match_id, team_id, kind FROM {PARTICIPANTS} WHERE role = 'starting_pitcher'"):
        if mid in ids:
            per.setdefault((mid, kind), set()).add(team)
    return Counter((kind, min(len(t), 2)) for (_, kind), t in per.items())


def sample(games: list[dict], n: int) -> list[dict]:
    """n games evenly spaced by kickoff (the first, the last and between), of those carrying a statsapi id."""
    pool = [g for g in games if g["game_pk"]]
    if len(pool) <= n or n <= 1:
        return pool[:max(n, 0)]
    return [pool[round(i * (len(pool) - 1) / (n - 1))] for i in range(n)]


class Provider:
    """The adapter's own call and pace; never raises."""

    def __init__(self):
        from src.adapters.mlb_stats_api import _BASE_URL, MLBStatsAPIAdapter
        self.adapter, self.base = MLBStatsAPIAdapter(), _BASE_URL
        self.calls, self.failed = 0, 0

    def game_block(self, game_pk: str):
        """(the game block of /schedule?gamePk&hydrate=probablePitcher, or None, why)."""
        self.calls += 1
        try:
            data = self.adapter._get("schedule", params={"sportId": 1, "gamePk": game_pk,
                                                         "hydrate": "probablePitcher"})
        except Exception as e:  # noqa: BLE001 - printed and counted; the probe goes on
            self.failed += 1
            return None, f"{type(e).__name__}: {e}"
        for d in (data.get("dates") or []) if isinstance(data, dict) else []:
            for g in d.get("games") or []:
                if str(g.get("gamePk")) == str(game_pk):
                    return g, None
        self.failed += 1
        return None, "no game block with that gamePk in the answer"


def probables(block: dict) -> dict:
    """{side: the probablePitcher object or None}, read at teams.{home,away}.probablePitcher."""
    teams = block.get("teams") or {}
    return {side: ((teams.get(side) or {}).get("probablePitcher") or None) for side in ("home", "away")}


def named(p) -> bool:
    return isinstance(p, dict) and bool(p.get("fullName")) and p.get("id") is not None


def time_keys(obj, prefix="") -> list[str]:
    """Every key, at any depth, whose name speaks of a time or a date, with its value."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}{k}"
            if any(w in k.lower() for w in TIME_WORDS) and not isinstance(v, (dict, list)):
                out.append(f"{path}={v!r}")
            out += time_keys(v, path + ".")
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:3]):
            out += time_keys(v, f"{prefix}[{i}].")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="addendum 67 item 2: MLB pitcher coverage, read-only")
    ap.add_argument("--db", default=None)
    ap.add_argument("--seasons", default=",".join(DEFAULT_SEASONS))
    ap.add_argument("--sample", type=int, default=SAMPLE)
    ap.add_argument("--no-network", action="store_true", help="the database part only (P1/P2 are not asked)")
    a = ap.parse_args(argv)
    seasons = [s.strip() for s in a.seasons.split(",") if s.strip()]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    print(f"MLB PITCHER PROBE · {now:%Y-%m-%d %H:%M}Z · read-only, nothing written")

    p = db_path(a.db)
    con, form = open_read(p)
    print(f"\nD0 database {p} · opened via {form}")
    found = tables(con)
    for t, cols in found.items():
        print(f"  table {t}: {', '.join(cols)}")
    use_app = APPEARANCES in found and {"match_id", "source_game_id", "team_source_id", "is_starter"} <= set(found[APPEARANCES])
    use_par = PARTICIPANTS in found and {"match_id", "team_id", "role", "kind"} <= set(found[PARTICIPANTS])
    print(f"  READ: {APPEARANCES} (match_id, source_game_id, team_source_id, is_starter = 1)"
          + ("" if use_app else " — NOT PRESENT with those columns: starters are not read"))
    print(f"  READ, second: {PARTICIPANTS} (match_id, team_id, role = 'starting_pitcher', kind)"
          + ("" if use_par else " — NOT PRESENT with those columns"))
    src = source_name()
    print(f"  the statsapi game id: matches.external_ids['{src}'] (MLBStatsAPIAdapter.source_name)")
    stored = dict(con.execute("SELECT m.season, COUNT(*) FROM matches m JOIN competitions c ON c.id = m.competition_id "
                              "WHERE c.code = ? GROUP BY m.season ORDER BY m.season", (COMPETITION,)).fetchall())
    print(f"  competition {COMPETITION}: games by stored season {stored or 'none'}")

    prov = None if a.no_network else Provider()
    if prov:
        print(f"  provider: {prov.base}/schedule?sportId=1&gamePk=<id>&hydrate=probablePitcher (the adapter's call "
              "and pace)")
        print("  keys read: dates[].games[].gamePk · games[].teams.{home,away}.probablePitcher.{id,fullName}")
    summary = []
    all_games = {}
    for season in seasons:
        games = season_games(con, season)
        all_games[season] = games
        fin = [g for g in games if g["status"] == FINISHED]
        print(f"\nD1 season {season}: {len(games)} games stored · by status "
              f"{dict(sorted(Counter(g['status'] for g in games).items()))} · finished {len(fin)}")
        both = one = neither = None
        if use_app:
            sides = starters(con, fin)
            both = sum(1 for g in fin if sides.get(g["id"], 0) >= 2)
            one = sum(1 for g in fin if sides.get(g["id"], 0) == 1)
            neither = sum(1 for g in fin if sides.get(g["id"], 0) == 0)
            print(f"  {APPEARANCES}: starters for both sides {both}/{len(fin)} · one side only {one} · neither "
                  f"{neither}")
        if use_par:
            pc = participants(con, fin)
            print(f"  {PARTICIPANTS} (second read): " + (" · ".join(
                f"kind {k!r}: both sides {pc[(k, 2)]}, one side {pc[(k, 1)]}"
                for k in sorted({k for k, _ in pc})) or "none on the finished games"))
        z, n = None, 0
        if prov:
            picks = sample(fin, a.sample)
            n = len(picks)
            z = 0
            print(f"P1 season {season}: {n} finished game(s) sampled of {sum(1 for g in fin if g['game_pk'])} "
                  f"carrying a statsapi id (of {len(fin)} finished)")
            for g in picks:
                block, why = prov.game_block(g["game_pk"])
                if block is None:
                    print(f"  match {g['id']} gamePk {g['game_pk']} {g['kickoff']}: ✗ {why}")
                    continue
                pp = probables(block)
                ok = all(named(x) for x in pp.values())
                z += ok
                keys = sorted({k for x in pp.values() if isinstance(x, dict) for k in x})
                print(f"  match {g['id']} gamePk {g['game_pk']} {g['kickoff']}: home "
                      f"{(pp['home'] or {}).get('fullName') if named(pp['home']) else 'not named'} · away "
                      f"{(pp['away'] or {}).get('fullName') if named(pp['away']) else 'not named'} · "
                      f"probablePitcher keys {keys or 'none'}")
        summary.append((season, both, len(fin), z, n))

    if prov:
        nxt = con.execute(
            "SELECT m.id, m.utc_date, m.status, m.external_ids FROM matches m JOIN competitions c "
            "ON c.id = m.competition_id WHERE c.code = ? AND m.status != ? AND m.utc_date > ? "
            "ORDER BY m.utc_date, m.id", (COMPETITION, FINISHED, now.strftime("%Y-%m-%d %H:%M:%S"))).fetchall()
        nxt = [r for r in nxt if (json.loads(r[3]) if isinstance(r[3], str) else (r[3] or {})).get(src) is not None]
        if not nxt:
            print("\nP2 the next unplayed game: none stored after now with a statsapi id")
        else:
            mid, kick, status, ext = nxt[0]
            gpk = str((json.loads(ext) if isinstance(ext, str) else ext).get(src))
            block, why = prov.game_block(gpk)
            print(f"\nP2 the next unplayed game: match {mid} gamePk {gpk} {kick} (stored status {status})")
            if block is None:
                print(f"  ✗ {why}")
            else:
                pp = probables(block)
                for side, x in pp.items():
                    print(f"  {side}: {'named ' + repr(x.get('fullName')) if named(x) else 'not named now'}"
                          + (f" · probablePitcher keys {sorted(x)}" if isinstance(x, dict) else ""))
                tk = time_keys({"game": {k: v for k, v in block.items() if k != "teams"},
                                "probablePitcher": {s: x for s, x in pp.items() if isinstance(x, dict)}})
                print(f"  game block keys: {sorted(block)}")
                print("  keys speaking of a time or a date: " + ("; ".join(tk) if tk else "none"))
                hour = [k for k in tk if k.startswith("probablePitcher.")]
                print("  the hour the probables appeared: " + ("; ".join(hour) if hour else
                                                               "THE PAYLOAD DOES NOT SAY (no time key on a "
                                                               "probablePitcher block)"))
        print(f"\ncalls: {prov.calls} · failed {prov.failed}")

    print("\nSUMMARY")
    for season, both, fin, z, n in summary:
        print(f"  {season}: starters recorded {both if both is not None else 'not read'}/{fin} · probables "
              f"available on the sample {z if z is not None else 'not asked'}/{n if z is not None else a.sample}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
