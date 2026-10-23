"""
MLB PITCHER SEASON RECEIPT (ARCHITECT 2026-10-23, addendum 162 item 1) — read-only.

Item 1: "the live predictor's pitcher lookup takes no season, so a pitcher with two stored seasons gets whichever row
the query yields last." (a) the operator's receipt tonight: rows per season, pitchers with more than one season,
tonight's two starters' rows. (b) the PR body's receipt: for every MLB prediction row still on disk this postseason,
the (player, season) the old read would have used vs the new, counts only, and whether any live probability changes.

  D0  the database               opened mode=ro (a copy that refuses it: the plain path with PRAGMA query_only = ON,
                                 the form printed, #421); never created
  S1  pitcher_season_stats       rows and distinct pitchers per season, as stored
  S2  more than one season       pitchers (player_source_id) holding rows for two or more seasons, and the season sets
  S3  the day's starters         every MLB game whose start falls in the --date window (10:00Z that day to 10:00Z the
                                 next, so an evening ET game counts on its own day): each side's starting_pitcher
                                 (match_participants), every pitcher_season_stats row it holds, and the row the new
                                 read takes
  S4  the postseason predictions every predictions row of an MLB game of --season whose stage is a postseason gameType
                                 (F, D, L, W, the export's MLB_POSTSEASON_GAME_TYPES): per side, counted by what the
                                 old read could take and did take (below) against the new read. A prediction's live
                                 probability changes only where a side's row changes; the games are named only then.

THE OLD READ (training.py before addendum 162): every row of the pitcher with era not null and innings_pitched > 0,
in the order the query yields them, the last one kept (a dict keyed by player_source_id alone). With no ORDER BY that
order is the query planner's: pitcher_season_stats carries an index on player_source_id and a unique one on
(player_source_id, season), and which one a query walks decides which season comes last. It is not reproduced here
(a replay could pick the other index). What the old read DID take is read from the prediction itself: the starter
detail it stored (factor_breakdown home_/away_starter_detail: raw_era, ip, gs) against the pitcher's rows.
THE NEW READ: the row of the game's own season (matches.season as stored), with the same era / innings filter; none
is "no stats".

Per side, one of:
  no starter listed                            the game stores no starting_pitcher for the side
  no usable row                                neither read finds one: unchanged
  only the game's season                       the one usable row is the game's season: unchanged
  another season only: now no stats            the old read took another season's row, the new finds none: CHANGED
  two seasons: the old read took the game's    the stored detail equals the game's-season row: unchanged
  two seasons: the old read took another       the stored detail equals another season's row: CHANGED
  two seasons: undetermined                    the stored detail equals no row now (a later refresh, or no detail
                                               stored): named, not counted as either

The starters are the ones stored now (match_participants); a prediction made before a later starter change was made
on that earlier listing, so S4 reads the current listing, not the history. Nothing is re-predicted: a changed row is
named, and the size of the change is a re-predict, not this receipt.

Run (from the repo root):  python3 scripts/mlb_pitcher_season_receipt.py [--db PATH] [--date YYYY-MM-DD]
                           [--season 2026] [--competition MLB]
Stdlib only, so the operator can run it from a fetched copy before the PR merges. Paste the whole output.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

COMPETITION = "MLB"
POSTSEASON = ("F", "D", "L", "W")       # src.walters.export.MLB_POSTSEASON_GAME_TYPES (pinned by the test)
ROLE = "starting_pitcher"
DAY_START_HOUR = 10                     # the --date window opens at 10:00Z and closes 24 hours later


def db_path(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    url = os.getenv("DATABASE_URL")
    if not url and Path(".env").is_file():
        for line in Path(".env").read_text().splitlines():
            if line.strip().startswith("DATABASE_URL="):
                url = line.split("=", 1)[1].strip().strip('"').strip("'")
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
        con.execute("SELECT 1 FROM pitcher_season_stats LIMIT 1")
        return con, "mode=ro URI"
    except sqlite3.OperationalError:
        con = sqlite3.connect(str(p), timeout=60)
        con.execute("PRAGMA query_only = ON")
        con.execute("SELECT 1 FROM pitcher_season_stats LIMIT 1")
        return con, "plain path with PRAGMA query_only = ON (mode=ro refused)"


def usable_rows(con, sid: str) -> list[tuple]:
    """(id, season, era, innings_pitched, games_started) of every row of the pitcher, by season then id."""
    return con.execute("SELECT id, season, era, innings_pitched, games_started FROM pitcher_season_stats "
                       "WHERE player_source_id = ? ORDER BY season, id", (sid,)).fetchall()


def usable(rows: list[tuple]) -> list[tuple]:
    return [r for r in rows if r[2] is not None and (r[3] or 0) > 0]


def new_read(rows: list[tuple], season: str) -> tuple | None:
    """The new read: the usable row of the game's own season; none is "no stats"."""
    for r in usable(rows):
        if r[1] == season:
            return r
    return None


def matches_detail(r: tuple, detail: dict | None) -> bool:
    """True when the row is the one the stored starter detail was made from (training.py rounds era to 2 places and
    innings to 1)."""
    if not detail:
        return False
    return (detail.get("raw_era") == round(r[2], 2) and detail.get("ip") == round(r[3], 1)
            and detail.get("gs") == (r[4] or 0))


def fmt(r: tuple | None) -> str:
    if r is None:
        return "none"
    return f"row {r[0]} season {r[1]} (era {r[2]}, ip {r[3]}, gs {r[4]})"


def starters(con, match_id: int) -> dict[int, tuple[str, str | None]]:
    """{team_id: (player_name, player_source_id)} of the game's stored starting_pitcher rows."""
    return {t: (n, sid) for t, n, sid in con.execute(
        "SELECT team_id, player_name, player_source_id FROM match_participants WHERE match_id = ? AND role = ?",
        (match_id, ROLE))}


UNCHANGED = ("no starter listed", "no usable row", "only the game's season", "two seasons: the old read took the game's")
CHANGED = ("another season only: now no stats", "two seasons: the old read took another")
UNDETERMINED = "two seasons: undetermined"
KINDS = UNCHANGED[:3] + (CHANGED[0], UNCHANGED[3], CHANGED[1], UNDETERMINED)


def classify(rows: list[tuple] | None, season: str, detail: dict | None = None) -> tuple[str, tuple | None]:
    """(kind, the row the old read took when known)."""
    if rows is None:
        return "no starter listed", None
    use = usable(rows)
    if not use:
        return "no usable row", None
    mine = new_read(rows, season)
    others = [r for r in use if r[1] != season]
    if not others:
        return "only the game's season", mine
    if mine is None:
        took = [r for r in others if matches_detail(r, detail)]
        return "another season only: now no stats", (took[0] if took else others[-1] if len(others) == 1 else None)
    if matches_detail(mine, detail):
        return "two seasons: the old read took the game's", mine
    took = [r for r in others if matches_detail(r, detail)]
    if took:
        return "two seasons: the old read took another", took[0]
    return UNDETERMINED, None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="addendum 162 item 1: MLB pitcher rows by season, read-only")
    ap.add_argument("--db", default=None)
    ap.add_argument("--date", default=None, help="the day whose starters S3 lists (YYYY-MM-DD; default today UTC)")
    ap.add_argument("--season", default="2026", help="the season S4 reads (as stored)")
    ap.add_argument("--competition", default=COMPETITION, help="the competition code (default MLB)")
    a = ap.parse_args(argv)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    print(f"MLB PITCHER SEASON RECEIPT · {now:%Y-%m-%d %H:%M}Z · addendum 162 item 1 · read-only, nothing written")

    p = db_path(a.db)
    con, form = open_read(p)
    print(f"\nD0 database {p} · opened via {form}")
    print("  READ: pitcher_season_stats (id, player_source_id, season, era, innings_pitched, games_started); "
          "match_participants (match_id, team_id, role = 'starting_pitcher', player_name, player_source_id); "
          "matches (id, season, stage, utc_date); predictions (id, match_id, model_version, computed_at)")

    print("\nS1 pitcher_season_stats per season")
    for season, n, d in con.execute("SELECT season, COUNT(*), COUNT(DISTINCT player_source_id) "
                                    "FROM pitcher_season_stats GROUP BY season ORDER BY season"):
        print(f"  {season}: {n} rows · {d} pitchers")

    multi = con.execute("SELECT player_source_id, GROUP_CONCAT(season, ',') FROM "
                        "(SELECT DISTINCT player_source_id, season FROM pitcher_season_stats ORDER BY season) "
                        "GROUP BY player_source_id HAVING COUNT(*) > 1").fetchall()
    sets = Counter(s for _, s in multi)
    print(f"\nS2 pitchers with more than one season stored: {len(multi)}")
    for s, n in sorted(sets.items()):
        print(f"  seasons {s}: {n}")

    day = datetime.strptime(a.date, "%Y-%m-%d") if a.date else now.replace(hour=0, minute=0, second=0,
                                                                            microsecond=0)
    lo = day.replace(hour=DAY_START_HOUR)
    hi = lo + timedelta(days=1)
    games = con.execute(
        "SELECT m.id, m.season, m.stage, m.utc_date, m.home_team_id, m.away_team_id FROM matches m "
        "JOIN competitions c ON c.id = m.competition_id WHERE c.code = ? AND m.utc_date >= ? AND m.utc_date < ? "
        "ORDER BY m.utc_date", (a.competition, lo.isoformat(sep=" "), hi.isoformat(sep=" "))).fetchall()
    print(f"\nS3 the day's starters ({lo:%Y-%m-%d %H:%M}Z .. {hi:%Y-%m-%d %H:%M}Z): {len(games)} game(s)")
    for mid, season, stage, at, home, away in games:
        st = starters(con, mid)
        print(f"  match {mid} · season {season} · stage {stage} · {at}")
        for side, team in (("home", home), ("away", away)):
            if team not in st:
                print(f"    {side}: no starter listed")
                continue
            name, sid = st[team]
            if not sid:
                print(f"    {side}: {name} · no source id (no stats)")
                continue
            rows = usable_rows(con, sid)
            print(f"    {side}: {name} ({sid}) · {len(rows)} row(s) stored")
            for r in rows:
                print(f"      {fmt(r)}")
            others = [r for r in usable(rows) if r[1] != season]
            print(f"      NEW read: {fmt(new_read(rows, season))}"
                  + (f" · the old read could take {len(others)} other season row(s) (planner order)" if others else ""))

    preds = con.execute(
        "SELECT p.id, p.match_id, m.season, m.home_team_id, m.away_team_id, p.factor_breakdown FROM predictions p "
        "JOIN matches m ON m.id = p.match_id JOIN competitions c ON c.id = m.competition_id "
        f"WHERE c.code = ? AND m.season = ? AND m.stage IN ({','.join('?' * len(POSTSEASON))}) ORDER BY p.id",
        (a.competition, a.season, *POSTSEASON)).fetchall()
    sides: Counter = Counter()
    changed: dict[int, list[str]] = {}
    undetermined: dict[int, list[str]] = {}
    for pid, mid, season, home, away, fb_raw in preds:
        try:
            fb = json.loads(fb_raw) if isinstance(fb_raw, str) else (fb_raw or {})
        except ValueError:
            fb = {}
        st = starters(con, mid)
        for side, team in (("home", home), ("away", away)):
            sid = st[team][1] if team in st else None
            rows = usable_rows(con, sid) if sid else None
            kind, took = classify(rows, season, (fb or {}).get(f"{side}_starter_detail"))
            sides[kind] += 1
            line = f"prediction {pid} {side}: {fmt(took)} -> {fmt(new_read(rows, season) if rows else None)}"
            if kind in CHANGED:
                changed.setdefault(mid, []).append(line)
            elif kind == UNDETERMINED:
                undetermined.setdefault(mid, []).append(line)
    games_n = len({p[1] for p in preds})
    print(f"\nS4 postseason predictions, season {a.season} (stage in {', '.join(POSTSEASON)}): {len(preds)} row(s) "
          f"on {games_n} game(s) · {2 * len(preds)} side(s)")
    for kind in KINDS:
        print(f"  {kind}: {sides.get(kind, 0)}" + ("  (CHANGED)" if kind in CHANGED else ""))
    if changed:
        print(f"  LIVE PROBABILITY CHANGES on {len(changed)} game(s) (a side's row changes; the size is a re-predict):")
        for mid in sorted(changed):
            print(f"    match {mid}: " + "; ".join(changed[mid]))
    else:
        print("  live probability changes: none (no side's row changes)")
    if undetermined:
        print(f"  UNDETERMINED on {len(undetermined)} game(s) (two seasons stored; the stored detail matches no row "
              "now):")
        for mid in sorted(undetermined):
            print(f"    match {mid}: " + "; ".join(undetermined[mid]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
