"""
NFL QUARTERBACK COVERAGE RECEIPT (ARCHITECT 2026-10-23, addendum 162 item 3(a); roadmap lane nfl-qb, #427): the QB
packet's coverage read, read-only. Verbatim: "The 11-02 QB ruling needs a design packet, Code's by 10-30, read-only:
full coverage by season and game type (games with player passing stats / games listed; missing fields; player ids that
join a roster), not the three-game sample". The design itself is docs/specs/nfl-qb-term.md.

It follows scripts/nfl_qb_probe.py (#489) and reuses its code: the request (`get`: throttled, never raises), the ids
from the adapter's own mapping (LEAGUE, DIRECT_BASE), the adapter's own parse of a game's status, the passing group
read verbatim (`passing_lines`) and the attempts read (`attempts`, "comp att"). The provider's coverage flags are a
claim; this counts what the answers hold.

Per season (default 2023..2026):
  G  /games?league&season          games listed, by game type (game.stage as sent) and by the adapter's status.
  P  per FINISHED game              /games/statistics/players?id: the game has a passing line for both teams, one, or
                                   none; per team side the quarterback with the most attempts (OUR READ, never the
                                   provider's word: it names no starter, #427's probe).
  F  the fields                     over every passing line of the season: each stat name seen, and the lines that
                                   lack it or send it null/empty ("missing fields"); a line with no attempts read.
  R  /players?team&season           each team's roster of the season: a passing line's player id joins the same
                                   team's roster, another team's roster of the season (a trade), or none.
  Summary                          per season and game type: games listed / finished / with passing stats for both
                                   teams, and the roster join of the most-attempts quarterbacks.

THE CACHE (--save DIR, default logs/nfl_qb_payloads): every answer is kept as JSON (season/<kind>_<id>.json); a re-run
reads a kept answer and makes no call for it, so a capped run resumes where it stopped. The kept payloads are the
estimate's input for the design's dry run. DIR is refused under data/ (law 5) and never committed (logs/ is
gitignored). A failed or empty answer is printed and not kept, so a re-run asks it again.
--max-calls N (default 2000) stops cleanly at N provider calls and prints what it left.

Run:  python3 scripts/nfl_qb_coverage.py [--seasons 2023,2024,2025,2026] [--save DIR] [--max-calls N]
Key: API_AMERICAN_FOOTBALL_KEY, else API_FOOTBALL_KEY (environment or .env); never printed. Opens no database.
Paste the whole output to the architect.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("nfl_qb_probe", ROOT / "scripts" / "nfl_qb_probe.py")
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)

from src.db.schema import MatchStatus  # noqa: E402

DEFAULT_SEASONS = [2023, 2024, 2025, 2026]
DEFAULT_SAVE = ROOT / "logs" / "nfl_qb_payloads"


class Capped(Exception):
    pass


class Fetch:
    """The provider read through the probe's get, with the payload cache and the call cap."""

    def __init__(self, save: Path, max_calls: int, get=None):
        self.save, self.max_calls, self.calls, self.cached = save, max_calls, 0, 0
        self.get = get or probe.get
        self.failed: list[str] = []

    def __call__(self, kind: str, bucket, key, path: str, **params) -> list:
        f = self.save / str(bucket) / f"{kind}_{key}.json"
        if f.is_file():
            try:
                self.cached += 1
                return json.loads(f.read_text())
            except ValueError:
                pass                                  # a torn file is asked again
        if self.calls >= self.max_calls:
            raise Capped(f"{kind} {key}")
        self.calls += 1
        code, errs, rows = self.get(path, **params)
        if errs or not rows:
            self.failed.append(f"{bucket} {kind} {key}: HTTP {code}" + (f" errors {errs}" if errs else " (no rows)"))
            return rows or []
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows, sort_keys=True, default=str))
        tmp.replace(f)
        return rows


def _stage(row) -> str:
    g = probe._game(row)
    return str(g.get("stage")) if isinstance(g, dict) and g.get("stage") is not None else "(no stage)"


def _team_ids(row) -> tuple:
    t = (row.get("teams") or {}) if isinstance(row, dict) else {}
    return tuple((t.get(side) or {}).get("id") for side in ("home", "away"))


def _empty(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def season_receipt(season: int, fetch: Fetch) -> dict:
    out = {"season": season, "stages": defaultdict(Counter), "status": Counter(), "fields": Counter(),
           "field_missing": Counter(), "lines": 0, "no_attempts": 0, "join": Counter(), "join_top": Counter(),
           "left": [], "teams": set()}
    games = fetch("games", season, "list", "games", league=probe.LEAGUE, season=season)
    finished = []
    for r in games:
        p = probe.parsed(r)
        st = p[0].name if p else "(dropped by the adapter's parse)"
        sg = _stage(r)
        out["stages"][sg]["listed"] += 1
        out["status"][st] += 1
        out["teams"].update(t for t in _team_ids(r) if t is not None)
        if p and p[0] == MatchStatus.FINISHED and probe.game_id(r) is not None:
            out["stages"][sg]["finished"] += 1
            finished.append(r)
    lines_by_game, seen = {}, []
    for r in finished:
        gid, sg = probe.game_id(r), _stage(r)
        try:
            teams = fetch("players", season, gid, "games/statistics/players", id=gid)
        except Capped as e:
            out["left"].append(str(e))
            continue
        sides = {}
        for tb in teams:
            if not isinstance(tb, dict):
                continue
            tid = (tb.get("team") or {}).get("id") if isinstance(tb.get("team"), dict) else None
            pl = probe.passing_lines(tb)
            if pl:
                sides[tid] = pl
        home, away = _team_ids(r)
        n = sum(1 for t in (home, away) if sides.get(t))
        out["stages"][sg][("passing both teams", "passing one team", "passing neither")[2 - n]] += 1
        lines_by_game[gid] = (sg, sides)
        for tid, pl in sides.items():
            for _player, stats in pl:
                out["lines"] += 1
                names = {nm: v for nm, v in stats if isinstance(nm, str)}
                out["fields"].update(names.keys())
                if probe.attempts(stats) is None:
                    out["no_attempts"] += 1
                for nm, v in names.items():
                    if _empty(v):
                        out["field_missing"][nm] += 1
                seen.append(set(names))
    for names in seen:                                  # a field another line sends, absent from this one
        for nm in out["fields"]:
            if nm not in names:
                out["field_missing"][nm] += 1
    rosters, roster_of = {}, defaultdict(set)
    for tid in sorted(out["teams"], key=str):
        try:
            rows = fetch("roster", season, tid, "players", team=tid, season=season)
        except Capped as e:
            out["left"].append(str(e))
            continue
        rosters[tid] = {probe.roster_player(x).get("id") for x in rows if isinstance(x, dict)
                        and isinstance(probe.roster_player(x), dict)}
        for pid in rosters[tid]:
            roster_of[pid].add(tid)
    for gid, (sg, sides) in lines_by_game.items():
        for tid, pl in sides.items():
            top = max(range(len(pl)), key=lambda i: probe.attempts(pl[i][1]) or -1)
            for i, (player, stats) in enumerate(pl):
                pid = player.get("id") if isinstance(player, dict) else None
                k = ("no player id" if pid is None else "no roster read for the team" if tid not in rosters
                     else "same team" if pid in rosters[tid] else "another team's roster" if roster_of.get(pid)
                     else "no roster")
                out["join"][k] += 1
                if i == top:
                    out["join_top"][k] += 1
    return out


def lines(r: dict, fetch: Fetch) -> list[str]:
    s = r["season"]
    L = [f"\n== season {s}",
         "  G /games: by status " + " · ".join(f"{k} {v}" for k, v in sorted(r["status"].items()))]
    for sg, c in sorted(r["stages"].items()):
        L.append(f"    {sg}: listed {c['listed']} · finished {c['finished']} · passing both teams "
                 f"{c['passing both teams']} · one team {c['passing one team']} · neither {c['passing neither']}")
    L.append(f"  F passing lines {r['lines']} (no attempts read {r['no_attempts']}) · fields: "
             + (" · ".join(f"{nm!r} on {r['lines'] - r['field_missing'][nm]}, missing/empty {r['field_missing'][nm]}"
                           for nm in sorted(r["fields"])) or "none"))
    L.append("  R roster join, every passing line: " + (" · ".join(f"{k} {v}" for k, v in sorted(r["join"].items()))
                                                     or "none"))
    L.append("    the most-attempts quarterback per team-game (OUR READ): "
             + (" · ".join(f"{k} {v}" for k, v in sorted(r["join_top"].items())) or "none"))
    if r["left"]:
        L.append(f"  LEFT at the call cap ({fetch.max_calls}): {len(r['left'])} read(s), first {r['left'][0]}; "
                 "a re-run resumes from the kept payloads")
    tot = Counter()
    for c in r["stages"].values():
        tot.update(c)
    L.append(f"  SUMMARY {s}: listed {tot['listed']} · finished {tot['finished']} · passing stats for both teams "
             f"{tot['passing both teams']}/{tot['finished']} · most-attempts QB joins its team's roster "
             f"{r['join_top']['same team']}/{sum(r['join_top'].values())}")
    return L


def main(argv=None, echo=print, get=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--seasons", default=",".join(map(str, DEFAULT_SEASONS)))
    ap.add_argument("--save", default=str(DEFAULT_SAVE), help="the payload cache (never under data/)")
    ap.add_argument("--max-calls", type=int, default=2000)
    a = ap.parse_args(argv)
    save = Path(a.save).expanduser().resolve()
    if (ROOT / "data").resolve() in (save, *save.parents):
        raise SystemExit(f"REFUSED: --save {save} is under data/ (law 5): the payloads never live there")
    if get is None and not probe.KEY:
        raise SystemExit("REFUSED: no API_AMERICAN_FOOTBALL_KEY / API_FOOTBALL_KEY (environment or .env)")
    fetch = Fetch(save, a.max_calls, get=get)
    seasons = [int(x) for x in a.seasons.split(",") if x.strip()]
    echo(f"NFL QB COVERAGE RECEIPT (addendum 162 item 3(a), #427) · read-only, opens no database · league "
         f"{probe.LEAGUE} · seasons {seasons} · payloads kept in {save} · call cap {a.max_calls}")
    for s in seasons:
        for ln in lines(season_receipt(s, fetch), fetch):
            echo(ln)
    echo(f"\ncalls made {fetch.calls} · answers read from the kept payloads {fetch.cached} · failed or empty "
         f"{len(fetch.failed)}")
    for f in fetch.failed[:40]:
        echo(f"  ✗ {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
