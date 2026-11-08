"""
THE NFL RESULTS BY TEAM RECEIPT (ARCHITECT 2026-11-08 10:05 ET, addendum 295 item 5(d); #885). READ-ONLY.

The ruling, verbatim: "(d) A READ-ONLY receipt script (no write): NFL 2026 FINISHED rows' scores by team against the
nflverse results feed #841 already pulls daily (unmetered) — the mismatch list, printed, is the check I declined to buy
with metered calls in 292 item 3(h)."

WHAT #841 PULLS (law 1, read 2026-11-08 at origin/main 19715787): src/availability/nflverse.py fetches ONE nflverse
file, the DEPTH CHARTS release (RELEASE_URL, release tag depth_charts; columns dt, team, player_name, ... pos_rank), and
keeps its payloads under logs/availability/nflverse_depth_charts/. That file carries NO game and NO score. The results
are nflverse's SCHEDULES file (github.com/nflverse/nflverse-data, release tag schedules, `games.csv`), which nothing in
the repo fetches or caches. So this receipt adds NO network path: it reads that file from a local path the operator
names (--games-file), as #841's own `--file PATH` reads a hand-carried depth-chart file. Whether a fetch of it is wanted
is the architect's (an OPEN ITEM on #885's PR).

THE FILE (law 1: the header read 2026-11-08 from the release file itself; csv.DictReader, every column by NAME; a
missing column REFUSES the file, naming it): game_id, season, game_type, gameday (the US Eastern date), gametime,
away_team, away_score, home_team, home_score, location ("Home" / "Neutral"). A score is an integer or blank (a game not
yet final in nflverse: counted, never compared).

OUR ROWS: the NFL competition's (code NFL) rows of the season (string, int-style "2026") whose status is FINISHED, read
from a .backup COPY outside data/ opened mode=ro&immutable=1 (src/walters/mlb_pitchers_gate.check_db / open_ro, the
receipts' guards; a copy with a -wal / -shm / -journal sidecar is refused: immutable=1 would read a stale file). The
team codes: the existing NFL team mapping #841 uses (src/availability/nflverse.team_map: teams.tla, the
api-american-football code sync-teams stores, held by exactly one NFL competition team; a tla held twice is unmapped,
never a guess).

THE PAIRING (each reading the conservative one, law 4): a stored row and an nflverse game PAIR when they hold the same
TWO team codes (either order: the orientation is what is checked, not assumed) and the game's gameday is within one day
of our kickoff's US Eastern date. None: "not in the file"; more than one: AMBIGUOUS (listed, never compared). A row
whose team does not map: UNMAPPED (listed). Paired, the scores are compared BY TEAM: our home team's score against
nflverse's score for that same team, and the mirror. Any difference, or a score we hold as NULL, is a MISMATCH. The
orientation each pair reads (our home is nflverse's home: same; our home is nflverse's away: reversed) is counted and
printed beside it, with nflverse's location, since a reversed pair is where a by-position write went wrong.

Exit: 0 every stored row read and no mismatch; 1 at least one MISMATCH (the list printed); 2 REFUSED (a --db that is
not a fresh copy outside data/, a --games-file that is missing or lacks a column). Last line:
NFL-RESULTS-BY-TEAM-RECEIPT {json} (counts and match ids only). Writes nothing; no network.

    python3 scripts/nfl_results_by_team_receipt.py --db /path/to/backup-copy.db --games-file /path/to/games.csv
        [--season 2026]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OK, MISMATCHED, REFUSED = 0, 1, 2
COMPETITION = "NFL"
DEFAULT_SEASON = "2026"
SIDECARS = ("-wal", "-shm", "-journal")
TAIL = "NFL-RESULTS-BY-TEAM-RECEIPT"
ET = ZoneInfo("America/New_York")
DAY_TOLERANCE = 1                      # nflverse's gameday (US Eastern) vs our kickoff's Eastern date
COLUMNS = ("game_id", "season", "game_type", "gameday", "gametime", "away_team", "away_score", "home_team",
           "home_score", "location")


class Refused(RuntimeError):
    pass


def _score(text):
    t = (text or "").strip()
    if not t:
        return None
    try:
        return int(t)
    except ValueError:
        raise Refused(f"a score {text!r} is neither an integer nor blank") from None


def read_games(path: str, season: str) -> list[dict]:
    """The file's games of `season`, every column by name; REFUSED (never guessed) on a missing file or column."""
    p = Path(path)
    if not p.is_file():
        raise Refused(f"--games-file {path}: not a file")
    with p.open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        missing = [c for c in COLUMNS if c not in (rd.fieldnames or [])]
        if missing:
            raise Refused(f"--games-file {path}: the header lacks {', '.join(missing)} (nflverse's schedules "
                          f"games.csv carries {', '.join(COLUMNS)})")
        out = []
        for n, r in enumerate(rd, start=2):
            if (r.get("season") or "").strip() != str(season):
                continue
            try:
                day = date.fromisoformat((r.get("gameday") or "").strip())
            except ValueError:
                raise Refused(f"--games-file {path} line {n}: gameday {r.get('gameday')!r} is not a date") from None
            try:
                hs, as_ = _score(r.get("home_score")), _score(r.get("away_score"))
            except Refused as e:
                raise Refused(f"--games-file {path} line {n}: {e}") from None
            out.append({"game_id": r["game_id"].strip(), "gameday": day, "game_type": (r.get("game_type") or "").strip(),
                        "home": r["home_team"].strip(), "away": r["away_team"].strip(), "home_score": hs,
                        "away_score": as_, "location": (r.get("location") or "").strip()})
    return out


def stored_rows(session, season: str) -> tuple[list[dict], dict, set]:
    """Our NFL FINISHED rows of the season, and the team code map (#841's nflverse.team_map)."""
    from sqlalchemy import select

    from src.availability.nflverse import team_map
    from src.db.schema import Competition, Match, MatchStatus

    tmap, ambiguous = team_map(session)
    rows = session.execute(select(Match.id, Match.utc_date, Match.home_team_id, Match.away_team_id,
                                  Match.home_score, Match.away_score)
                           .join(Competition, Competition.id == Match.competition_id)
                           .where(Competition.code == COMPETITION, Match.season == str(season),
                                  Match.status == MatchStatus.FINISHED)
                           .order_by(Match.utc_date, Match.id)).all()
    out = [{"match_id": r[0], "utc": r[1], "home_id": r[2], "away_id": r[3], "home_score": r[4], "away_score": r[5]}
           for r in rows]
    return out, tmap, ambiguous


def eastern_date(utc: datetime) -> date:
    return utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(ET).date()


def compare(ours: list[dict], tmap: dict, games: list[dict]) -> dict:
    """The pairing and the by-team comparison (module doc). Pure: no database, no file."""
    code_of = {tid: code for code, tid in tmap.items()}
    by_pair: dict = {}
    for g in games:
        by_pair.setdefault(frozenset((g["home"], g["away"])), []).append(g)
    res = {"checked": [], "mismatch": [], "unmapped": [], "not_in_file": [], "ambiguous": [], "unscored": [],
           "orientation": Counter(), "paired_game_ids": set()}
    for o in ours:
        hc, ac = code_of.get(o["home_id"]), code_of.get(o["away_id"])
        if hc is None or ac is None:
            res["unmapped"].append({"match_id": o["match_id"], "home_team_id": o["home_id"],
                                    "away_team_id": o["away_id"], "home_code": hc, "away_code": ac})
            continue
        ed = eastern_date(o["utc"])
        cands = [g for g in by_pair.get(frozenset((hc, ac)), [])
                 if abs((g["gameday"] - ed).days) <= DAY_TOLERANCE]
        if not cands:
            res["not_in_file"].append({"match_id": o["match_id"], "home": hc, "away": ac, "eastern_date": str(ed)})
            continue
        if len(cands) > 1:
            res["ambiguous"].append({"match_id": o["match_id"], "home": hc, "away": ac,
                                     "game_ids": [g["game_id"] for g in cands]})
            continue
        g = cands[0]
        res["paired_game_ids"].add(g["game_id"])
        if g["home_score"] is None or g["away_score"] is None:
            res["unscored"].append({"match_id": o["match_id"], "game_id": g["game_id"]})
            continue
        nv = {g["home"]: g["home_score"], g["away"]: g["away_score"]}
        ori = "same" if g["home"] == hc else "reversed"
        res["orientation"][ori] += 1
        line = {"match_id": o["match_id"], "game_id": g["game_id"], "orientation": ori, "location": g["location"],
                "ours": {"home": hc, "home_score": o["home_score"], "away": ac, "away_score": o["away_score"]},
                "nflverse": {"home": g["home"], "home_score": g["home_score"], "away": g["away"],
                             "away_score": g["away_score"]}}
        res["checked"].append(line)
        if (o["home_score"], o["away_score"]) != (nv[hc], nv[ac]):
            res["mismatch"].append(line)
    return res


def _side(x: dict) -> str:
    return f"{x['away']} {x['away_score']} @ {x['home']} {x['home_score']}"


def report(res: dict, games: list[dict], n_ours: int, ambiguous_tla: set, season: str, say) -> dict:
    scored = [g for g in games if g["home_score"] is not None and g["away_score"] is not None]
    unpaired = [g for g in scored if g["game_id"] not in res["paired_game_ids"]]
    o = res["orientation"]
    say(f"  stored {COMPETITION} {season} FINISHED rows: {n_ours} · nflverse {season} games in the file: {len(games)} "
        f"(scored {len(scored)})")
    say(f"  compared by team: {len(res['checked'])} (orientation vs nflverse: same {o.get('same', 0)} · reversed "
        f"{o.get('reversed', 0)}) · MISMATCH {len(res['mismatch'])} · unmapped {len(res['unmapped'])} · not in the "
        f"file {len(res['not_in_file'])} · ambiguous {len(res['ambiguous'])} · nflverse unscored "
        f"{len(res['unscored'])}")
    if ambiguous_tla:
        say(f"  team codes held by more than one NFL team (unmapped, never a guess): {', '.join(sorted(ambiguous_tla))}")
    say(f"\nMISMATCH LIST ({len(res['mismatch'])}): our home/away and scores by team, then nflverse's")
    for x in res["mismatch"]:
        say(f"  ✗ match {x['match_id']} ({x['orientation']}, nflverse location {x['location'] or '?'}): ours "
            f"{_side(x['ours'])} · nflverse {x['game_id']} {_side(x['nflverse'])}")
    if not res["mismatch"]:
        say("  none")
    rev = [x for x in res["checked"] if x["orientation"] == "reversed"]
    if rev:
        say(f"\nREVERSED vs nflverse ({len(rev)}; scores compared by team above):")
        for x in rev:
            say(f"  ↔ match {x['match_id']} ({'MISMATCH' if x in res['mismatch'] else 'agrees by team'}, nflverse "
                f"location {x['location'] or '?'}): ours {_side(x['ours'])} · nflverse {x['game_id']} "
                f"{_side(x['nflverse'])}")
    for key, label in (("unmapped", "UNMAPPED (a team code not held by exactly one NFL team)"),
                       ("not_in_file", "NOT IN THE FILE (no game of the two codes within a day)"),
                       ("ambiguous", "AMBIGUOUS (more than one game: never compared)"),
                       ("unscored", "NFLVERSE UNSCORED (not compared)")):
        if res[key]:
            say(f"\n{label} ({len(res[key])}):")
            for x in res[key]:
                say("  " + json.dumps(x, default=str, sort_keys=True))
    if unpaired:
        say(f"\nnflverse scored games paired to no stored FINISHED row ({len(unpaired)}): "
            + ", ".join(g["game_id"] for g in unpaired))
    return {"season": season, "stored_finished": n_ours, "file_games": len(games), "file_scored": len(scored),
            "compared": len(res["checked"]), "same": o.get("same", 0), "reversed": o.get("reversed", 0),
            "mismatch": [x["match_id"] for x in res["mismatch"]],
            "reversed_ids": [x["match_id"] for x in rev],
            "unmapped": [x["match_id"] for x in res["unmapped"]],
            "not_in_file": [x["match_id"] for x in res["not_in_file"]],
            "ambiguous": [x["match_id"] for x in res["ambiguous"]],
            "unscored": [x["match_id"] for x in res["unscored"]], "file_unpaired": len(unpaired)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="NFL results by team vs nflverse (addendum 295 item 5(d)); read-only")
    ap.add_argument("--db", default=None, help="a .backup copy of the database outside data/ (opened read-only)")
    ap.add_argument("--games-file", default=None, help="nflverse's schedules games.csv, a local file (no network)")
    ap.add_argument("--season", default=DEFAULT_SEASON)
    a = ap.parse_args(argv)

    def say(x=""):
        print(x, flush=True)

    out: dict = {"season": a.season}
    code = REFUSED
    try:
        from src.walters import mlb_pitchers_gate as mp
        try:
            path = mp.check_db(a.db)
            for sc in SIDECARS:
                if path.with_name(path.name + sc).exists():
                    raise mp.GateRefused(f"--db {a.db} has a {sc} sidecar ({path.name + sc}): not a fresh .backup "
                                         "copy; immutable=1 would ignore it and read a stale file")
            mp.open_ro(path).close()
        except mp.GateRefused as e:
            raise Refused(str(e)) from None
        if not a.games_file:
            raise Refused("--games-file PATH is required: nflverse's schedules games.csv, a local file")
        games = read_games(a.games_file, a.season)
        say(f"NFL RESULTS BY TEAM (addendum 295 item 5(d)) · --db {path} (opened "
            f"{mp.COPY_URI_QUERY.lstrip('?')}) · --games-file {a.games_file} · season {a.season} · no network, no "
            "write")
        from sqlalchemy.exc import SQLAlchemyError
        try:
            with mp.readonly_session(path) as s:
                ours, tmap, amb = stored_rows(s, a.season)
        except SQLAlchemyError as e:
            raise Refused(f"--db {path}: cannot be read as the schema the receipt needs ({type(e).__name__})") from None
        res = compare(ours, tmap, games)
        out = report(res, games, len(ours), amb, a.season, say)
        code = MISMATCHED if out["mismatch"] else OK
    except Refused as e:
        say(f"REFUSED: {e}; nothing compared")
        out["refused"] = str(e)
    print(f"{TAIL} " + json.dumps({"exit": code, **out}, default=str, sort_keys=True), flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
