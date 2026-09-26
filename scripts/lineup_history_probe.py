"""
Lineup-history probe (2026-09-26) — read-only reconnaissance, zero wiring.

The cup model track is SUSPENDED at a rotation information floor; its
reopening condition is a rotation-aware candidate on AS-OF lineup data
(R-track). This probe is that track's first receipt. Question: what
historical soccer lineup data does API-Football hold PER MATCH — how far
back, and which fields?

League ids come from the adapter's own mapping (_CODE_TO_LEAGUE_ID), never
from memory (law 1). The provider's coverage flags are a CLAIM; the spot
checks are the receipt. The probe never stops on an error — a missing
payload is a finding.

  Q0  /status          plan + requests remaining
  Q1  declared depth   /leagues coverage flags per season: fixtures.lineups,
                       fixtures.statistics_players, players
  Q2  spot checks      per comp, sampled seasons (latest finished, middle,
                       earliest declared): one finished fixture ->
                       /fixtures/lineups (startXI / subs / formation / coach
                       / player id / pos / grid) and /fixtures/players
                       (per-player minutes / position / substitute flag)

Run:  python3 scripts/lineup_history_probe.py [--comps EFL,CL,UEL,...]
Default comps: the suspended cups + their domestic parents. Requests are
throttled to API_FOOTBALL_RPM (default 10, same as the adapter).
Writes nothing. Prints receipts — paste the whole output to the architect.
"""
import argparse
import os
import sys
import time

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.adapters.api_football import _CODE_TO_LEAGUE_ID, _HOST_RAPID  # noqa: E402

load_dotenv(".env")

KEY = os.getenv("API_FOOTBALL_KEY") or ""
HOST = os.getenv("API_FOOTBALL_HOST") or "v3.football.api-sports.io"
BASE = f"https://{HOST}/v3" if HOST == _HOST_RAPID else f"https://{HOST}"
HDRS = ({"x-rapidapi-key": KEY, "x-rapidapi-host": HOST} if HOST == _HOST_RAPID
        else {"x-apisports-key": KEY})
RPM = float(os.getenv("API_FOOTBALL_RPM", "10"))
DEFAULT_COMPS = ["EFL", "FAC", "CL", "UEL", "UECL", "PL", "ELC"]
LATEST_FINISHED_SEASON = 2025   # 2025/26; 2026/27 is in progress
FINISHED = ("FT", "AET", "PEN")

_last = [0.0]


def get(path, **params):
    """(status_code, api_errors, response_list). Never raises, never exits."""
    wait = 60.0 / RPM - (time.monotonic() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.monotonic()
    try:
        r = requests.get(f"{BASE}/{path}", headers=HDRS, params=params, timeout=30)
    except requests.RequestException as e:
        return None, {"request": str(e)}, []
    try:
        body = r.json()
    except ValueError:
        return r.status_code, {"body": r.text[:120]}, []
    errs = body.get("errors") or {}
    resp = body.get("response")
    if isinstance(resp, dict):
        resp = [resp]
    return r.status_code, errs, resp or []


def declared_coverage(league_row):
    """{season_year: (lineups, statistics_players, players)} from /leagues."""
    out = {}
    for s in league_row.get("seasons") or []:
        cov = s.get("coverage") or {}
        fx = cov.get("fixtures") or {}
        out[s.get("year")] = (fx.get("lineups"), fx.get("statistics_players"),
                              cov.get("players"))
    return out


def sample_seasons(coverage):
    """Latest finished, middle, earliest declared-lineups season (deduped)."""
    years = sorted(y for y, c in coverage.items()
                   if isinstance(y, int) and y <= LATEST_FINISHED_SEASON and c[0])
    if not years:
        return []
    picks = [years[-1], years[len(years) // 2], years[0]]
    return sorted(set(picks), reverse=True)


def summarize_lineups(rows):
    """One line of facts per team block of /fixtures/lineups."""
    out = []
    for b in rows:
        xi = b.get("startXI") or []
        subs = b.get("substitutes") or []
        players = [(s.get("player") or {}) for s in xi + subs]
        named = [p for p in players if p.get("name")]
        out.append({
            "team": (b.get("team") or {}).get("name"),
            "xi": len(xi), "subs": len(subs),
            "formation": b.get("formation"),
            "coach": bool((b.get("coach") or {}).get("name")),
            "player_id": sum(1 for p in named if p.get("id")),
            "pos": sum(1 for p in named if p.get("pos")),
            "grid": sum(1 for p in named if p.get("grid")),
            "named": len(named),
        })
    return out


def summarize_players(rows):
    """Per-player match stats (/fixtures/players): minutes/position/sub flag."""
    n = with_min = with_pos = with_sub = 0
    for team in rows:
        for p in team.get("players") or []:
            games = ((p.get("statistics") or [{}])[0] or {}).get("games") or {}
            n += 1
            with_min += games.get("minutes") is not None
            with_pos += bool(games.get("position"))
            with_sub += games.get("substitute") is not None
    return {"players": n, "minutes": with_min, "position": with_pos, "substitute": with_sub}


def first_finished_fixture(league_id, season):
    code, errs, rows = get("fixtures", league=league_id, season=season)
    done = [f for f in rows
            if ((f.get("fixture") or {}).get("status") or {}).get("short") in FINISHED]
    done.sort(key=lambda f: (f.get("fixture") or {}).get("timestamp") or 0)
    return (done[0] if done else None), len(rows), errs


def probe_comp(code):
    league_id = _CODE_TO_LEAGUE_ID[code]
    print(f"\n=== {code} (league {league_id}) ===")
    _, errs, rows = get("leagues", id=league_id)
    if not rows:
        print(f"  Q1 ✗ /leagues returned nothing (errors {errs}) — skipping")
        return
    cov = declared_coverage(rows[0])
    years = sorted(y for y in cov if isinstance(y, int))
    lineup_years = [y for y in years if cov[y][0]]
    print(f"  Q1 seasons listed: {years[0] if years else '-'}..{years[-1] if years else '-'} "
          f"({len(years)}) · declared lineups: "
          + (f"{lineup_years[0]}..{lineup_years[-1]} ({len(lineup_years)} seasons)"
             if lineup_years else "NONE"))
    gaps = [y for y in years if lineup_years and y >= lineup_years[0] and not cov[y][0]]
    if gaps:
        print(f"     declared-lineup GAPS after first coverage: {gaps}")
    print("     per season (lineups / statistics_players / players): "
          + ", ".join(f"{y}:{''.join('Y' if v else 'n' for v in cov[y])}" for y in years))

    for season in sample_seasons(cov):
        fx, n_fx, ferrs = first_finished_fixture(league_id, season)
        if not fx:
            print(f"  Q2 {season}: no finished fixture among {n_fx} listed (errors {ferrs})")
            continue
        fid = (fx.get("fixture") or {}).get("id")
        date = ((fx.get("fixture") or {}).get("date") or "")[:10]
        rnd = (fx.get("league") or {}).get("round")
        _, lerrs, lrows = get("fixtures/lineups", fixture=fid)
        _, perrs, prows = get("fixtures/players", fixture=fid)
        print(f"  Q2 {season} fixture {fid} ({date}, {rnd}) of {n_fx} listed")
        if not lrows:
            print(f"     /fixtures/lineups: NO ROWS" + (f" (errors {lerrs})" if lerrs else ""))
        for t in summarize_lineups(lrows):
            print(f"     lineups {t['team']}: XI {t['xi']} · subs {t['subs']} · formation "
                  f"{t['formation']} · coach {'Y' if t['coach'] else 'n'} · of {t['named']} named: "
                  f"id {t['player_id']} pos {t['pos']} grid {t['grid']}")
        ps = summarize_players(prows)
        print(f"     /fixtures/players: {ps['players']} players · minutes {ps['minutes']} · "
              f"position {ps['position']} · substitute-flag {ps['substitute']}"
              + (f" (errors {perrs})" if perrs else ""))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--comps", default=",".join(DEFAULT_COMPS),
                    help="comma list of adapter competition codes")
    args = ap.parse_args(argv)
    if not KEY:
        print("✗ No API key found (API_FOOTBALL_KEY). Stop.")
        return 1
    comps = [c.strip() for c in args.comps.split(",") if c.strip()]
    unknown = [c for c in comps if c not in _CODE_TO_LEAGUE_ID]
    if unknown:
        print(f"✗ Unknown codes {unknown}. Known: {sorted(_CODE_TO_LEAGUE_ID)}. Stop.")
        return 1
    print(f"Lineup-history probe · host {HOST} · comps {comps} · "
          f"~{1 + 10 * len(comps)} requests at {RPM:g}/min")

    print("\nQ0 — /status")
    code, errs, st = get("status")
    acct = st[0] if st else {}
    print(f"  HTTP {code} · subscription {acct.get('subscription')} · requests {acct.get('requests')}"
          + (f" · errors {errs}" if errs else ""))

    for c in comps:
        probe_comp(c)

    print("\n✓ Lineup-history probe complete — paste this whole output to the architect. "
          "Nothing was written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
