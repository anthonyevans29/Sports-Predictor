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
  Gate                             per season, the coverage gate (ARCHITECT 2026-10-27, addendum 170 item 2(a)): lines
                                   for both teams in at least 98% of the finished regular-season and postseason games.
                                   It decides 2023's centring (docs/specs/nfl-qb-term.md 3.2): run with 2022 in
                                   --seasons; 2022 MEETS -> option (a), absent or BELOW -> option (b).
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
import html
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

from src.adapters import api_american_football as aaf  # noqa: E402
from src.db.schema import MatchStatus  # noqa: E402

DEFAULT_SEASONS = [2023, 2024, 2025, 2026]
DEFAULT_SAVE = ROOT / "logs" / "nfl_qb_payloads"
GATE = 0.98                 # the coverage gate (addendum 170 item 2(a)); the 11-02 declaration rules the figure


class Capped(Exception):
    pass


class Fetch:
    """The provider read through the probe's get, with the payload cache and the call cap."""

    def __init__(self, save: Path, max_calls: int, get=None):
        self.save, self.max_calls, self.calls, self.cached = save, max_calls, 0, 0
        self.get = get or probe.get
        self.failed: list[str] = []
        self.empty: list[str] = []

    def __call__(self, kind: str, bucket, key, path: str, **params) -> list | None:
        """The rows; [] for an answer with no rows; None for a FAILED read (a transport error, a non-200 answer or
        API errors: Codex on #710), which the caller keeps out of every count and marks the gate INCOMPLETE."""
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
        if errs or code != 200:
            self.failed.append(f"{bucket} {kind} {key}: HTTP {code}" + (f" errors {errs}" if errs else ""))
            return None
        if not rows:
            self.empty.append(f"{bucket} {kind} {key}")
            return []
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows, sort_keys=True, default=str))
        tmp.replace(f)
        return rows


def _stage(row) -> str:
    g = probe._game(row)
    return str(g.get("stage")) if isinstance(g, dict) and g.get("stage") is not None else "(no stage)"


GATE_STAGES = {"regularseason", "postseason"}        # the provider's "Regular Season" / "Post Season", normalized


def _in_gate(stage: str) -> bool | None:
    """True for the regular season or the postseason, False for the preseason, None for a stage not identified
    (missing or novel): never counted in the gate, printed as indeterminate (Codex on #710)."""
    n = "".join(ch for ch in stage.lower() if ch.isalpha())
    return True if n in GATE_STAGES else False if n == "preseason" else None


def _dropped(row) -> str | None:
    """Why the adapter's parse dropped a listed row (ARCHITECT 2026-10-27 13:45 ET, #712 item 2): "finished" when
    the provider marks it finished (a short the adapter maps to FINISHED, or no status claim with both totals, the
    adapter's own score-presence rule) but the parse could not read it (no id, kickoff or team id), which the gate
    cannot check and so makes the gate line INCOMPLETE; the adapter's own exclusion reason for an all-star
    exhibition, by design, never counted; None otherwise (a game not finished)."""
    g = probe._game(row)
    t = (row.get("teams") or {}) if isinstance(row, dict) else {}
    why = aaf._non_competitive(g.get("week"), g.get("stage"),
                               team_names=tuple(html.unescape(str((t.get(s) or {}).get("name") or ""))
                                                for s in ("home", "away")))
    if why:
        return f"non-competitive, excluded by the adapter ({why})"
    short = probe.game_status(row)
    if aaf._STATUS.get(short) == MatchStatus.FINISHED or probe._no_status_both_totals(row):
        return "finished"
    return None


def _team_ids(row) -> tuple:
    t = (row.get("teams") or {}) if isinstance(row, dict) else {}
    return tuple((t.get(side) or {}).get("id") for side in ("home", "away"))


def _empty(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def season_receipt(season: int, fetch: Fetch) -> dict:
    out = {"season": season, "stages": defaultdict(Counter), "status": Counter(), "fields": Counter(),
           "field_missing": Counter(), "lines": 0, "no_attempts": 0, "join": Counter(), "join_top": Counter(),
           "left": [], "failed": [], "dropped": [], "excluded": Counter(), "teams": set()}
    try:
        games = fetch("games", season, "list", "games", league=probe.LEAGUE, season=season)
    except Capped as e:                                 # the cap reached at a season's boundary: stop cleanly (Codex)
        out["left"].append(str(e))
        return out
    if games is None:                                   # a failed read is not an empty season (Codex on #710)
        out["failed"].append("the games list")
        return out
    finished = []
    for r in games:
        p = probe.parsed(r)
        st = p[0].name if p else "(dropped by the adapter's parse)"
        sg = _stage(r)
        out["stages"][sg]["listed"] += 1
        out["status"][st] += 1
        if p is None:
            why = _dropped(r)
            if why == "finished":                       # #712 item 2: a finished game the gate cannot check
                out["stages"][sg]["finished, dropped by the parse"] += 1
                out["dropped"].append(probe.game_label(r))
            elif why:
                out["excluded"][why] += 1
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
        if teams is None:                               # failed: not "passing neither" (Codex on #710)
            out["stages"][sg]["statistics read failed"] += 1
            out["failed"].append(f"statistics of game {gid}")
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
        if rows is None:                                # failed: "no roster read for the team", never an empty roster
            out["failed"].append(f"roster of team {tid}")
            continue
        rosters[tid] = {probe.roster_player(x).get("id") for x in rows if isinstance(x, dict)
                        and isinstance(probe.roster_player(x), dict)}
        for pid in rosters[tid]:
            roster_of[pid].add(tid)
    for gid, (sg, sides) in lines_by_game.items():
        for tid, pl in sides.items():
            # the most-attempts quarterback among the lines whose attempts read (0 is a read); none readable: no pick.
            # A tie for the most names none (Codex on #710): the pick never rests on the provider's row order
            read = [(probe.attempts(st), i) for i, (_p, st) in enumerate(pl) if probe.attempts(st) is not None]
            most = max(a for a, _i in read) if read else None
            leaders = [i for a, i in read if a == most]
            top = leaders[0] if len(leaders) == 1 else None
            if not read:
                out["join_top"]["no attempts read (no most-attempts quarterback)"] += 1
            elif top is None:
                out["join_top"]["tied for the most attempts (no most-attempts quarterback)"] += 1
            for i, (player, stats) in enumerate(pl):
                pid = player.get("id") if isinstance(player, dict) else None
                k = ("no player id" if pid is None else "no roster read for the team" if tid not in rosters
                     else "same team" if pid in rosters[tid] else "another team's roster" if roster_of.get(pid)
                     else "no roster")
                out["join"][k] += 1
                if i == top:
                    out["join_top"][k] += 1
    return out


def lines(r: dict, fetch: Fetch, universe=None) -> list[str]:
    """The season's lines. `universe`: every passing field any season of the run sends (#712 item 1), so a field
    absent from this whole season is still on its F line, "on 0" and absent, never left off."""
    universe = sorted(set(universe or ()) | set(r["fields"]))
    # a whole-season absence is claimed only when every finished game's statistics were read (Codex on #713)
    partial = bool(r["left"] or r["failed"] or r["dropped"])
    s = r["season"]
    L = [f"\n== season {s}",
         "  G /games: by status " + " · ".join(f"{k} {v}" for k, v in sorted(r["status"].items()))]
    for sg, c in sorted(r["stages"].items()):
        L.append(f"    {sg}: listed {c['listed']} · finished {c['finished']} · passing both teams "
                 f"{c['passing both teams']} · one team {c['passing one team']} · neither {c['passing neither']}"
                 + (f" · statistics read failed {c['statistics read failed']}" if c["statistics read failed"] else ""))
    L.append(f"  F passing lines {r['lines']} (no attempts read {r['no_attempts']}) · fields: "
             + (" · ".join(f"{nm!r} on {r['lines'] - r['field_missing'][nm]}, missing/empty {r['field_missing'][nm]}"
                           if nm in r["fields"] else
                           (f"{nm!r} on 0 of the {r['lines']} lines read, UNKNOWN for the season (reads incomplete)"
                            if partial else f"{nm!r} on 0, ABSENT from the whole season ({r['lines']} lines)")
                           for nm in universe) or "none"))
    L.append("  R roster join, every passing line: " + (" · ".join(f"{k} {v}" for k, v in sorted(r["join"].items()))
                                                     or "none"))
    L.append("    the most-attempts quarterback per team-game (OUR READ): "
             + (" · ".join(f"{k} {v}" for k, v in sorted(r["join_top"].items())) or "none"))
    if r["dropped"]:
        L.append(f"  FINISHED BUT DROPPED by the adapter's parse {len(r['dropped'])} (no statistics read; the gate "
                 "cannot check them): " + "; ".join(r["dropped"][:10]) + (" …" if len(r["dropped"]) > 10 else ""))
    for why, n in sorted(r["excluded"].items()):
        L.append(f"  {why}: {n} (not in the gate)")
    if r["failed"]:
        L.append(f"  FAILED reads {len(r['failed'])} (kept out of every count; a re-run asks them again): "
                 + ", ".join(r["failed"][:10]) + (" …" if len(r["failed"]) > 10 else ""))
    if r["left"]:
        L.append(f"  LEFT at the call cap ({fetch.max_calls}): {len(r['left'])} read(s), first {r['left'][0]}; "
                 "a re-run resumes from the kept payloads")
    tot = Counter()
    for c in r["stages"].values():
        tot.update(c)
    # the coverage gate (ARCHITECT 2026-10-27, addendum 170 item 2(a)): lines for both teams in at least 98% of the
    # season's finished regular-season and postseason games (every game type but the preseason)
    gate, unknown = Counter(), Counter()
    for sg, c in r["stages"].items():
        k = _in_gate(sg)
        if k:
            gate.update(c)
        elif k is None:                                 # a stage not identified: never in the gate (Codex on #710)
            unknown.update(c)
    if unknown["finished"] or unknown["finished, dropped by the parse"]:
        L.append(f"  stages not identified (missing or novel; not in the gate): finished {unknown['finished']}"
                 + (f" · finished, dropped by the parse {unknown['finished, dropped by the parse']}"
                    if unknown["finished, dropped by the parse"] else ""))
    incomplete = [x for x, on in (("capped: a re-run completes it", r["left"]),
                                  (f"{len(r['failed'])} read(s) failed: a re-run asks them again", r["failed"]),
                                  (f"{unknown['finished'] + unknown['finished, dropped by the parse']} finished "
                                   "game(s) of a stage not identified",
                                   unknown["finished"] + unknown["finished, dropped by the parse"]),
                                  (f"{gate['finished, dropped by the parse']} finished game(s) dropped by the parse",
                                   gate["finished, dropped by the parse"])) if on]
    pct = gate["passing both teams"] / gate["finished"] if gate["finished"] else None
    L.append(f"  coverage gate {s} (regular season and postseason, both teams >= {GATE:.0%}): "
             f"{gate['passing both teams']}/{gate['finished']}"
             + (f" = {pct:.1%}" if pct is not None else "")
             + (f" · INCOMPLETE ({'; '.join(incomplete)})" if incomplete else
                f" · {'MEETS' if pct >= GATE else 'BELOW'}" if pct is not None else " · NO FINISHED GAME"))
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
    results = [season_receipt(s, fetch) for s in seasons]
    universe = set().union(*(r["fields"] for r in results)) if results else set()
    echo(f"field universe (#712 item 1): {len(universe)} passing field(s) sent by some season of this run; each "
         "season's F line lists every one. A field no season sends cannot be named here: sack yards are read from "
         "the fields listed.")
    for r in results:
        for ln in lines(r, fetch, universe):
            echo(ln)
    echo(f"\ncalls made {fetch.calls} · answers read from the kept payloads {fetch.cached} · failed {len(fetch.failed)}"
         f" · answered with no rows {len(fetch.empty)}")
    for f in fetch.failed[:40]:
        echo(f"  ✗ {f}")
    for f in fetch.empty[:20]:
        echo(f"  ∅ {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
