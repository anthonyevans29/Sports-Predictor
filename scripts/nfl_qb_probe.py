"""
NFL QUARTERBACK PROBE (ARCHITECT 2026-10-13, addendum 59 item 5(h); roadmap lane nfl-qb, #427) — read-only.

Verbatim: "The quarterback probe, a PR of its own after the roadmap's. It follows scripts/lineup_history_probe.py:
ids from the adapter's own mapping, never from memory; it never stops on an error; it writes nothing; the whole
output is pasted to me. Its questions, for the NFL seasons 2023 to 2026: per game and team, who started at
quarterback, and where the provider says so; each quarterback's passing line per game, and which fields; how far back
each holds; and whether a game not yet played names its starter."

The league id and the host come from src/adapters/api_american_football.py (_CODE_TO_LEAGUE, DIRECT_BASE). The game,
team and player ids come from the provider's own answers. The provider's coverage flags are a CLAIM; the spot checks
are the receipt. The probe never stops on an error: a missing payload is a finding, printed.

  Q0  /status                      plan + requests
  Q1  /leagues?id=<NFL>            the seasons listed and each season's coverage flags, verbatim
  Q2  per season (2023..2026)      /games?league&season: games listed, by status and stage. Three finished games
                                   (the first, the middle and the last by kickoff) -> /games/statistics/players?id:
                                   per team, the groups the provider sends; the passing group's players with every
                                   stat name and value verbatim (which fields); any key or stat name in the answer
                                   that says "start" (where the provider says so, or that it says nothing); and the
                                   player with the most passing attempts, labelled OUR READ, never the provider's word.
  Q3  a game not yet played        the season's next unplayed game -> /games?id and /games/statistics/players?id:
                                   does any answer name a player; and each team's roster (/players?team&season),
                                   its quarterbacks with every field verbatim: does the roster say who starts.
  Summary                          per season: games listed, the sampled games, passing lines found, a starter field.

Run:  python3 scripts/nfl_qb_probe.py [--seasons 2023,2024,2025,2026]
Key: API_AMERICAN_FOOTBALL_KEY, else API_FOOTBALL_KEY (environment or .env); never printed. Requests are throttled to
API_AMERICAN_FOOTBALL_RPM (default 10). Writes nothing, opens no database. Paste the whole output to the architect.
"""
import argparse
import json
import os
import sys
import time

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.adapters.api_american_football import _CODE_TO_LEAGUE, DIRECT_BASE, APIAmericanFootballAdapter  # noqa: E402
from src.db.schema import MatchStatus  # noqa: E402
from src.walters.qb_audit import QB_POSITIONS  # noqa: E402  the QB position names the QB audit reads

load_dotenv(".env")

KEY = os.getenv("API_AMERICAN_FOOTBALL_KEY") or os.getenv("API_FOOTBALL_KEY") or ""
LEAGUE = _CODE_TO_LEAGUE["NFL"]
RPM = float(os.getenv("API_AMERICAN_FOOTBALL_RPM", "10"))
DEFAULT_SEASONS = [2023, 2024, 2025, 2026]
# A game's status and kickoff are read by the adapter's own parse (_parse_games: _STATUS, an unknown status
# SCHEDULED, the score-presence rule, the non-competitive filter), never by a list of this probe's own.
_ADAPTER = APIAmericanFootballAdapter()      # its parse only: no request is made through it
PASSING = "passing"                 # the group name, compared lowercased and stripped

_last = [0.0]
_calls = [0]


def get(path, **params):
    """(status_code, api_errors, response_list). Never raises, never exits."""
    wait = 60.0 / RPM - (time.monotonic() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.monotonic()
    _calls[0] += 1
    try:
        r = requests.get(f"{DIRECT_BASE}/{path}", headers={"x-apisports-key": KEY}, params=params, timeout=30)
    except requests.RequestException as e:
        return None, {"request": type(e).__name__}, []
    try:
        body = r.json()
    except ValueError:
        return r.status_code, {"body": r.text[:120]}, []
    if not isinstance(body, dict):
        return r.status_code, {"body": "not a JSON object"}, []
    errs = body.get("errors") or {}
    resp = body.get("response")
    if isinstance(resp, dict):
        resp = [resp]
    return r.status_code, errs, resp if isinstance(resp, list) else []


def _err(errs):
    return f" (errors {errs})" if errs else ""


def _game(row):
    return (row.get("game") or row) if isinstance(row, dict) else {}


def game_id(row):
    return _game(row).get("id")


def game_status(row):
    st = _game(row).get("status")
    return (st.get("short") if isinstance(st, dict) else st) or None


def game_kickoff(row):
    d = _game(row).get("date")
    if isinstance(d, dict):
        return d.get("timestamp") or 0, f"{d.get('date') or ''} {d.get('time') or ''}".strip()
    return 0, str(d or "")


def game_label(row):
    g = _game(row)
    t = (row.get("teams") or {}) if isinstance(row, dict) else {}
    home, away = t.get("home") or {}, t.get("away") or {}
    return (f"game {g.get('id')} ({game_kickoff(row)[1]}, stage {g.get('stage')!r}, week {g.get('week')!r}) "
            f"{away.get('name')} @ {home.get('name')}")


def declared_coverage(league_row):
    """{season_year: the season's coverage block, verbatim}. A seasons value or a year of another shape is left
    out, never raised on (Codex on #489)."""
    seasons = league_row.get("seasons") if isinstance(league_row, dict) else None
    if not isinstance(seasons, list):
        return {}
    return {s["year"]: s.get("coverage") for s in seasons
            if isinstance(s, dict) and isinstance(s.get("year"), (int, str))}


def _no_status_both_totals(row):
    """No status claim (absent, {}, a null or "None" short) and both final totals present."""
    st = _game(row).get("status")
    short = st.get("short") if isinstance(st, dict) else st
    scores = row.get("scores") if isinstance(row, dict) else None
    scores = scores if isinstance(scores, dict) else {}
    totals = [(v.get("total") if isinstance(v, dict) else v) for v in (scores.get("home"), scores.get("away"))]
    return short in (None, "", "None") and all(t is not None for t in totals)


def parsed(row):
    """(status, naive-UTC kickoff) as the adapter's own parse reads the row; None when it drops the row (no id, a
    non-competitive game) or cannot read it. The adapter's documented score-presence rule ("a game with both totals
    and no status claim is finished") is applied here too: its code sets the short to NS first, so the rule never
    fires there for an absent status (#493)."""
    try:
        got = _ADAPTER._parse_games({"response": [row]}, "NFL", "")
    except Exception:
        return None
    if not got:
        return None
    status = got[0].status
    if status == MatchStatus.SCHEDULED and _no_status_both_totals(row):
        status = MatchStatus.FINISHED
    return status, got[0].utc_date


def _by_kickoff(rows, status):
    """The rows the adapter reads with `status`, by the adapter's kickoff."""
    keyed = [(p[1], i, r) for i, r in enumerate(rows) if (p := parsed(r)) is not None and p[0] == status]
    return [r for _, _, r in sorted(keyed, key=lambda x: (x[0], x[1]))]


def sample_finished(rows):
    """The first, the middle and the last finished game by kickoff (deduped)."""
    done = _by_kickoff(rows, MatchStatus.FINISHED)
    if not done:
        return []
    picks = [done[0], done[len(done) // 2], done[-1]]
    out, seen = [], set()
    for r in picks:
        if game_id(r) not in seen:
            seen.add(game_id(r))
            out.append(r)
    return out


def next_unplayed(rows):
    """The first game the adapter reads as scheduled (an unknown status included, as the adapter reads it)."""
    left = _by_kickoff(rows, MatchStatus.SCHEDULED)
    return left[0] if left else None


def roster_player(row):
    """A roster row's player object, flat or wrapped as {"player": {...}} (as qb_audit.roster_index reads it)."""
    return row.get("player") if isinstance(row.get("player"), dict) else row


def start_paths(obj, path=""):
    """Every key path, and every stat name (an entry with a name and a value), in the answer that says 'start'
    (case-insensitive): where the provider would say who started. A player's own name is never read ("A. Starter").
    [] = it says nothing."""
    found = []
    if isinstance(obj, dict):
        stat = "name" in obj and "value" in obj
        for k, v in obj.items():
            p = f"{path}.{k}" if path else str(k)
            if "start" in str(k).lower():
                found.append(f"{p}={json.dumps(v, default=str)[:60]}")
            if stat and k == "name" and isinstance(v, str) and "start" in v.lower():
                found.append(f"{p}={v!r} (value {obj.get('value')!r})")
            found += start_paths(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found += start_paths(v, f"{path}[{i}]")
    return found


def raw_shape(teams):
    """The answer's own shape: a team block's keys, a group's keys and names, and its first player entry verbatim."""
    tb = next((t for t in teams if isinstance(t, dict)), None)
    if tb is None:
        return f"no team block is an object: {json.dumps(teams, default=str)[:200]}"
    groups = tb.get("groups") if isinstance(tb.get("groups"), list) else []
    g = next((x for x in groups if isinstance(x, dict)), {})
    first = next((p for p in (g.get("players") or []) if isinstance(p, dict)), None) if isinstance(g, dict) else None
    return (f"team block keys {sorted(tb.keys())} · group keys {sorted(g.keys()) if g else []} · "
            f"first group {g.get('name')!r} · its first player entry {json.dumps(first, sort_keys=True, default=str)}")


def passing_lines(team_block):
    """[(player, [(stat name, value)])] of the team's passing group, verbatim."""
    out = []
    for grp in team_block.get("groups") or []:
        if str(grp.get("name") or "").strip().lower() != PASSING:
            continue
        for p in grp.get("players") or []:
            stats = [(s.get("name"), s.get("value")) for s in p.get("statistics") or [] if isinstance(s, dict)]
            out.append((p.get("player") or {}, stats))
    return out


def attempts(stats):
    """Passing attempts from the stat lines, as the provider writes them ("comp att" "20/31", or "attempts"); None
    when no stat gives them. OUR READ of the line, never the provider's word for a starter."""
    for name, value in stats:
        n = str(name or "").strip().lower()
        try:
            if n in ("comp att", "comp/att", "c/att") and "/" in str(value):
                return int(str(value).split("/")[1])
            if n in ("attempts", "att", "passing attempts"):
                return int(value)
        except (TypeError, ValueError):
            return None
    return None


def probe_game(row, echo=print):
    """Q2 for one finished game. Returns a summary dict."""
    gid = game_id(row)
    echo(f"  {game_label(row)}")
    code, errs, teams = get("games/statistics/players", id=gid)
    found = {"game": gid, "passing_players": 0, "teams_with_passing": 0, "start_fields": [], "fields": set()}
    if not teams:
        echo(f"    /games/statistics/players: NO ROWS (HTTP {code}){_err(errs)}")
        return found
    found["start_fields"] = start_paths(teams)
    echo(f"    raw shape (law 1: the answer as sent, whatever this probe expects): {raw_shape(teams)}")
    for tb in teams:
        if not isinstance(tb, dict):
            echo(f"    a team block that is not an object: {json.dumps(tb, default=str)[:80]}")
            continue
        team = tb.get("team") or {}
        groups = [str(g.get("name")) for g in (tb.get("groups") or []) if isinstance(g, dict)]
        lines = passing_lines(tb)
        echo(f"    team {team.get('id')} {team.get('name')}: groups {groups}")
        if not lines:
            echo("      passing: NO passing group or no players in it")
            continue
        found["teams_with_passing"] += 1
        found["passing_players"] += len(lines)
        names = [n for n, _ in lines[0][1]]
        echo(f"      passing fields ({len(names)}): {names} · a player object's keys: {sorted(lines[0][0].keys())}")
        for player, stats in lines:
            found["fields"].update(repr(n) if not isinstance(n, str) else n for n, _ in stats)
            echo(f"      {player.get('id')} {player.get('name')}: "
                 + " · ".join(f"{n}={v}" for n, v in stats))
        tops = [(attempts(s), p.get("name")) for p, s in lines]
        tops = [t for t in tops if t[0] is not None]
        if tops:
            n, who = max(tops)
            echo(f"      most attempts (OUR READ, not the provider's word): {who} ({n})")
        else:
            echo("      most attempts: no stat gives attempts")
    if found["start_fields"]:
        echo(f"    the provider says who started ({len(found['start_fields'])} key(s) or stat name(s) say 'start'):")
        for path in found["start_fields"]:                           # every one, never cut (Codex on #489)
            echo(f"      {path}")
    else:
        echo("    the provider says who started: NO key or stat name says 'start'")
    return found


def probe_unplayed(row, season, echo=print):
    """Q3: does a game not yet played name its starter?"""
    gid = game_id(row)
    echo(f"  Q3 {season} next unplayed: {game_label(row)}")
    code, errs, g = get("games", id=gid)
    echo(f"    /games?id: {len(g)} row(s) (HTTP {code}){_err(errs)} · 'start' in it: {start_paths(g) or 'nothing'}")
    for r in g:                                                      # the whole answer, verbatim (Codex on #489)
        echo("      " + json.dumps(r, sort_keys=True, default=str))
    code, errs, st = get("games/statistics/players", id=gid)
    try:                    # a malformed answer here never keeps the rosters from being asked (Codex on #489)
        named = [(((tb.get("team") or {}) if isinstance(tb.get("team"), dict) else {}).get("name"), gr.get("name"),
                  pl.get("player"))
                 for tb in st if isinstance(tb, dict) for gr in (tb.get("groups") or []) if isinstance(gr, dict)
                 for pl in (gr.get("players") or []) if isinstance(pl, dict)]
        echo(f"    /games/statistics/players: {len(st)} team block(s), {len(named)} player(s) named "
             f"(HTTP {code}){_err(errs)} · 'start' in it: {start_paths(st) or 'nothing'}")
        for team, group, pl in named:                                # every one named, never cut
            echo(f"      {team} · {group} · "
                 + (f"{pl.get('id')} {pl.get('name')}" if isinstance(pl, dict) else json.dumps(pl, default=str)))
    except Exception as e:
        echo(f"    /games/statistics/players: ✗ {type(e).__name__}: {e} — continuing to the rosters · raw "
             f"{json.dumps(st, default=str)}")
    teams = row.get("teams") or {}
    for side in ("away", "home"):
        t = teams.get(side) or {}
        if t.get("id") is None:
            echo(f"    roster {side}: no team id in the game row")
            continue
        try:
            code, errs, roster = get("players", team=t["id"], season=season)
            qbs = [r for r in roster if isinstance(r, dict) and isinstance(roster_player(r), dict)
                   and str((roster_player(r).get("position") or "")).strip().upper() in QB_POSITIONS]
            echo(f"    roster {side} {t.get('id')} {t.get('name')}: {len(roster)} player(s), {len(qbs)} at QB "
                 f"(HTTP {code}){_err(errs)}")
            for r in qbs:
                echo("      " + json.dumps(r, sort_keys=True, default=str))          # every field, never cut
                echo(f"        'start' in this quarterback's entry: {start_paths(r) or 'nothing'}")
        except Exception as e:
            echo(f"    roster {side}: ✗ {type(e).__name__}: {e} — continuing")


def probe_season(season, echo=print):
    echo(f"\n=== NFL {season} (league {LEAGUE}) ===")
    code, errs, rows = get("games", league=LEAGUE, season=season)
    if not rows:
        echo(f"  Q2 /games: NO ROWS (HTTP {code}){_err(errs)} — nothing to sample")
        return {"season": season, "games": 0, "sampled": [], "passing": 0, "start_fields": 0}
    by_status, by_stage = {}, {}
    for r in rows:
        by_status[game_status(r)] = by_status.get(game_status(r), 0) + 1
        by_stage[_game(r).get("stage")] = by_stage.get(_game(r).get("stage"), 0) + 1
    echo(f"  Q2 /games: {len(rows)} listed · by status {by_status} · by stage {by_stage}")
    out = {"season": season, "games": len(rows), "sampled": [], "passing": 0, "start_fields": 0, "fields": set()}
    for r in sample_finished(rows):
        try:
            f = probe_game(r, echo)
        except Exception as e:          # never stops: an answer of an unexpected shape is a finding
            echo(f"    ✗ {game_label(r)}: {type(e).__name__}: {e} — continuing")
            continue
        out["sampled"].append(f["game"])
        out["passing"] += f["passing_players"]
        out["start_fields"] += len(f["start_fields"])
        out["fields"] |= f["fields"]
    if not out["sampled"]:
        echo("  Q2: no finished game listed")
    nxt = next_unplayed(rows)
    if nxt is not None:
        try:
            probe_unplayed(nxt, season, echo)
        except Exception as e:
            echo(f"    ✗ Q3 {game_label(nxt)}: {type(e).__name__}: {e} — continuing")
    else:
        echo(f"  Q3 {season}: no unplayed game listed")
    return out


def main(argv=None, echo=print):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--seasons", default=",".join(str(s) for s in DEFAULT_SEASONS),
                    help="comma list of NFL seasons (league years)")
    args = ap.parse_args(argv)
    if not KEY:
        echo("✗ No API key found (API_AMERICAN_FOOTBALL_KEY or API_FOOTBALL_KEY). Stop.")
        return 1
    try:
        seasons = [int(s) for s in args.seasons.split(",") if s.strip()]
    except ValueError:
        echo(f"✗ --seasons {args.seasons!r} is not a comma list of years. Stop.")
        return 1
    echo(f"NFL quarterback probe · host {DIRECT_BASE} · league {LEAGUE} (the adapter's mapping) · seasons {seasons} "
         f"· ~{2 + 8 * len(seasons)} requests at {RPM:g}/min")

    echo("\nQ0 — /status")
    code, errs, st = get("status")
    acct = st[0] if st and isinstance(st[0], dict) else {}
    echo(f"  HTTP {code} · subscription {acct.get('subscription')} · requests {acct.get('requests')}{_err(errs)}")

    echo(f"\nQ1 — /leagues?id={LEAGUE}")
    code, errs, rows = get("leagues", id=LEAGUE)
    try:                    # an answer of an unexpected shape is a finding; the seasons are still probed
        if not rows or not isinstance(rows[0], dict):
            echo(f"  /leagues: NO ROWS (HTTP {code}){_err(errs)}")
        else:
            cov = declared_coverage(rows[0])
            years = sorted(y for y in cov if isinstance(y, int))
            echo(f"  seasons listed: {years[0] if years else '-'}..{years[-1] if years else '-'} ({len(years)})"
                 + ("" if cov else f" · the seasons as sent: {json.dumps(rows[0].get('seasons'), default=str)}"))
            for y in years:
                if y in seasons or not seasons:
                    echo(f"  {y} coverage: {json.dumps(cov[y], sort_keys=True, default=str)}")
    except Exception as e:
        echo(f"  ✗ Q1: {type(e).__name__}: {e} — continuing")

    summaries = []
    for s in seasons:
        try:
            summaries.append(probe_season(s, echo))
        except Exception as e:          # never stops: a payload of an unexpected shape is a finding
            echo(f"  ✗ season {s}: {type(e).__name__}: {e} — continuing")
            summaries.append({"season": s, "games": "?", "sampled": [], "passing": 0, "start_fields": 0,
                              "fields": set()})

    echo("\nSUMMARY (how far back each holds)")
    for x in summaries:
        echo(f"  {x['season']}: games listed {x['games']} · sampled {x['sampled']} · passing lines {x['passing']} · "
             f"'start' fields {x['start_fields']} · passing fields {sorted(x.get('fields') or [], key=str)}")
    echo(f"\n✓ NFL quarterback probe complete · {_calls[0]} requests — paste this whole output to the architect. "
         "Nothing was written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
