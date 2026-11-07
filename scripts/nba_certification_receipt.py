"""
THE NBA DATA CERTIFICATION RECEIPT (ARCHITECT 2026-11-05, addendum 261 items 0 and 1(b); 2026-11-06, addendum 271 item
3(e)-(f) and addendum 272 item 3; lane basketball-market-only, #839). Read-only. Two phases, run in this order on the
laptop:

  1. SERVED (the default; the provider only, opens NO database): BEFORE the first `sync-matches --competition NBA`
     writes a mapped row. 272 item 3, verbatim: "the CERTIFICATION RECEIPT (the wiring PR's) breaks the CANC rows down
     by date, stage, week and whether an FT twin (same two teams, same UTC day) exists, and prints the counts BEFORE
     the map is written; a CANC row with an FT twin is kept as served and EXCLUDED from the game counts by the
     provider's own ids (never deduplicated by guess, never deleted); the coverage page's totals count SCHEDULED +
     FINISHED + POSTPONED, not CANCELLED." 271 item 3(e): "THE 70 CANC GAMES in the NBA's 2026-27 listing are READ
     before anything is mapped: the certification receipt lists their dates, stage/week fields and teams."
  2. STORED (--db COPY, no network): after sync-competitions → sync-teams → sync-matches for each season, on a .backup
     copy outside data/ opened mode=ro&immutable=1 (kalshi_pair_receipt's guards): counts per season by stored
     status, the status mapping as stored, true-zero nulls (261 item 0: "counts per season, status mapping, true-zero
     nulls — the NHL/NCAA form"), the FT-twin CANCELLED ids excluded from the game counts.

Seasons: ours, int-style (261 item 1(b)): 2026 (2026-27 to date) plus 2024 and 2025 as history. Each provider season is
picked by the adapter's rule (271 item 3(b)): the served season that STARTS with our year, read on /leagues; none
served REFUSES that season (never computed). Calls (271 item 3(f)): /leagues once, then /teams and /games per season
(7 for three seasons); every call line prints x-ratelimit-requests-remaining as served, and the footer prints the
run's call count and the last value. The key: API_BASKETBALL_KEY, else API_FOOTBALL_KEY (271 item 2); the NAME is
printed, never the value.

THE SERVED PHASE, per season, in this order (the CANC breakdown before the map):
  STATUS AS SERVED (short | long: n) · STAGE and WEEK AS SERVED (each value verbatim, null as null, by short) ·
  THE CANC BREAKDOWN (by UTC date, stage, week, twin class; then every CANC row) · THE MAP (271 item 3(c)): the
  projection by our status, the codes it leaves SCHEDULED counted (law 4) · GAME COUNTS (the FT-twin CANC ids excluded;
  the coverage basis SCHEDULED + FINISHED + POSTPONED) · NULLS · INTEGRITY.

THE FT TWIN, as read here (the strictest reading of 272 item 3's words; anything wider is the architect's): another
listing of the SAME two provider team ids (either order: "same two teams"; the order is counted on its own line) on
the SAME UTC day of the served kickoff (271 item 3(d): the timestamp, never the provider's date string) whose served
short code is 'FT'. An AOT twin and any other same-day twin are counted on their own lines and NOT excluded.

Exit: 0 every read answered; 1 a call failed; 2 a read REFUSED (no key, a season not served, a league whose served
name does not match, a --db that is not a fresh copy outside data/). Last line: NBA-CERTIFICATION-RECEIPT {json} (counts
and provider ids only). Writes nothing.

    python3 scripts/nba_certification_receipt.py [--season 2026 --season 2025 ...]
    python3 scripts/nba_certification_receipt.py --db /path/to/backup-copy.db
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# requests, the adapter contract and the schema's enums only: nothing here opens the database
from src.adapters.api_basketball import (  # noqa: E402
    _STATUS, KEY_NAMES, LEAGUES, REMAINING_HEADER, APIBasketballAdapter, Refused, kickoff_utc, map_status,
    served_short, side_total,
)
from src.db.schema import MatchStatus  # noqa: E402

OK, FAILED, REFUSED = 0, 1, 2
COMPETITION = "NBA"
DEFAULT_SEASONS = ("2026", "2025", "2024")
TWIN_SHORT = "FT"                  # 272 item 3: "an FT twin"
COVERAGE_BASIS = ("SCHEDULED", "FINISHED", "POSTPONED")     # 272 item 3: "not CANCELLED"
SIDECARS = ("-wal", "-shm", "-journal")
TAIL = "NBA-CERTIFICATION-RECEIPT"


def v(x) -> str:
    """A served value verbatim: JSON's spelling (null for None, strings quoted)."""
    return json.dumps(x, default=str)


def counts(c: Counter) -> str:
    return " · ".join(f"{k}: {n}" for k, n in sorted(c.items(), key=lambda kv: (-kv[1], str(kv[0])))) or "none"


def game_row(g: dict) -> dict:
    """One /games item read by field name as served (271 item 3(d): the kickoff from the timestamp)."""
    game = g.get("game") if isinstance(g.get("game"), dict) else g
    teams = g.get("teams") if isinstance(g.get("teams"), dict) else {}
    scores = g.get("scores") if isinstance(g.get("scores"), dict) else {}
    home = teams.get("home") if isinstance(teams.get("home"), dict) else {}
    away = teams.get("away") if isinstance(teams.get("away"), dict) else {}
    st = game.get("status")
    lg = g.get("league") if isinstance(g.get("league"), dict) else {}
    utc = kickoff_utc(g)
    d = game.get("date")
    raw_date = d.get("date") if isinstance(d, dict) else d
    by_string = kickoff_utc({"date": raw_date}) if raw_date else None
    return {"id": game.get("id"), "utc": utc, "day": utc.date().isoformat() if utc else None,
            "date_served": raw_date, "date_utc": by_string,
            "stage": game.get("stage"), "week": game.get("week"),
            "short": served_short(g), "long": st.get("long") if isinstance(st, dict) else None,
            "home_id": home.get("id"), "away_id": away.get("id"),
            "home": home.get("name"), "away": away.get("name"),
            "home_total": side_total(scores, "home"), "away_total": side_total(scores, "away"),
            "league_season": lg.get("season", "<not served>")}


def twin_class(r: dict, by_day: dict) -> tuple[str, list[dict]]:
    """(class, the twins) of one CANC row: 'FT twin' / 'AOT twin' / 'other same-day twin' / 'no same-day twin'."""
    if r["day"] is None or r["home_id"] is None or r["away_id"] is None:
        return "no same-day twin", []
    pair = {r["home_id"], r["away_id"]}
    tw = [o for o in by_day.get(r["day"], []) if o is not r and {o["home_id"], o["away_id"]} == pair]
    for cls, code in (("FT twin", TWIN_SHORT), ("AOT twin", "AOT")):
        hit = [o for o in tw if o["short"] == code]
        if hit:
            return cls, hit
    return ("other same-day twin", tw) if tw else ("no same-day twin", [])


def season_report(ours: str, served, team_items: list, game_items: list, say, now: datetime) -> dict:
    rows = [game_row(g) for g in game_items if isinstance(g, dict)]
    not_objects = sum(1 for g in game_items if not isinstance(g, dict))
    team_ids = {t.get("id") for t in (x.get("team") if isinstance(x.get("team"), dict) else x
                                      for x in team_items if isinstance(x, dict)) if t.get("id") is not None}
    say(f"\nNBA {ours} = provider {v(served)} · /games {len(game_items)} items · /teams {len(team_items)} items")

    # 1. STATUS AS SERVED -----------------------------------------------------------------------------------------
    say("  STATUS AS SERVED (short | long: n; the map keys on the short code)")
    for (s, lo), n in sorted(Counter((r["short"], r["long"]) for r in rows).items(), key=lambda kv: str(kv[0])):
        say(f"    {s if s is not None else '<absent>'} | {lo if lo is not None else '<absent>'}: {n}")

    # 2. STAGE and WEEK AS SERVED ----------------------------------------------------------------------------------
    for field in ("stage", "week"):
        say(f"  {field.upper()} AS SERVED (value verbatim: n · by short)")
        by = defaultdict(Counter)
        for r in rows:
            by[v(r[field])][r["short"] if r["short"] is not None else "<absent>"] += 1
        for val, c in sorted(by.items(), key=lambda kv: -sum(kv[1].values())):
            say(f"    {val}: {sum(c.values())} · {counts(c)}")

    # 3. THE CANC BREAKDOWN, before the map -------------------------------------------------------------------------
    by_day: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r["day"] is not None:
            by_day[r["day"]].append(r)
    canc = [r for r in rows if r["short"] == "CANC"]
    say(f"  THE CANC BREAKDOWN (addendum 272 item 3; read before the map): {len(canc)} CANC listing(s)")
    say(f"    by UTC day (the served timestamp): {counts(Counter(r['day'] or '<no kickoff>' for r in canc))}")
    say(f"    by stage: {counts(Counter(v(r['stage']) for r in canc))}")
    say(f"    by week: {counts(Counter(v(r['week']) for r in canc))}")
    say(f"    by long form: {counts(Counter(r['long'] if r['long'] is not None else '<absent>' for r in canc))}")
    classes: Counter = Counter()
    order: Counter = Counter()
    excluded: list = []
    detail = []
    for r in canc:
        cls, tw = twin_class(r, by_day)
        classes[cls] += 1
        if cls == "FT twin":
            excluded.append(r["id"])
            for o in tw:
                order["same home/away" if o["home_id"] == r["home_id"] else "home/away reversed"] += 1
        detail.append((r, cls, tw))
    say(f"    by twin (same two provider team ids, same UTC day): {counts(classes)}")
    if order:
        say(f"    FT twins by order: {counts(order)}")
    say("    every CANC listing: provider id · UTC kickoff · stage · week · away (id) @ home (id) · long · twin")
    for r, cls, tw in sorted(detail, key=lambda t: (t[0]["utc"] or datetime.max, str(t[0]["id"]))):
        twins = ", ".join(f"#{o['id']} {o['short']}" for o in tw) or "-"
        kick = r["utc"].isoformat(sep=" ", timespec="minutes") + "Z" if r["utc"] else "<no kickoff>"
        say(f"      #{r['id']} · {kick}"
            f" · stage {v(r['stage'])} · week {v(r['week'])} · {r['away']} ({r['away_id']}) @ {r['home']} "
            f"({r['home_id']}) · {r['long']!r} · {cls}: {twins}")

    # 4. THE MAP (271 item 3(c)) -----------------------------------------------------------------------------------
    say("  THE MAP (addendum 271 item 3(c), by short code): "
        + " · ".join(f"{k} -> {s.name}" for k, s in _STATUS.items())
        + " · every other code SCHEDULED (law 4) · no live code mapped")
    mapped = Counter(map_status(r["short"]).name for r in rows)
    fin = Counter(r["short"] for r in rows if map_status(r["short"]) == MatchStatus.FINISHED)
    say(f"    projected: {counts(mapped)}" + (f" (FINISHED: {counts(fin)}; AOT = the overtime flag)" if fin else ""))
    unmapped = Counter(r["short"] for r in rows if r["short"] is not None and r["short"] not in _STATUS)
    absent = sum(1 for r in rows if r["short"] is None)
    say(f"    UNMAPPED (stay SCHEDULED, counted): {counts(unmapped)} · status absent: {absent}")

    # 5. GAME COUNTS ------------------------------------------------------------------------------------------------
    gone = set(excluded)
    keep = [r for r in rows if r["id"] not in gone]
    by_status = Counter(map_status(r["short"]).name for r in keep)
    basis = sum(by_status.get(k, 0) for k in COVERAGE_BASIS)
    say("  GAME COUNTS (272 item 3: FT-twin CANC listings kept as served, excluded from the counts by provider id)")
    say(f"    listing {len(rows)} · FT-twin CANC excluded {len(excluded)}"
        + (f": {', '.join(str(i) for i in sorted(excluded, key=str))}" if excluded else ""))
    say(f"    games {len(keep)}: {counts(by_status)}")
    say(f"    coverage basis SCHEDULED + FINISHED + POSTPONED = {basis} (CANCELLED not counted)")

    # 6. NULLS ------------------------------------------------------------------------------------------------------
    fin_null = [r["id"] for r in rows if map_status(r["short"]) == MatchStatus.FINISHED
                and (r["home_total"] is None or r["away_total"] is None)]
    ns_scored = [r["id"] for r in rows if r["short"] == "NS"
                 and r["home_total"] is not None and r["away_total"] is not None]
    absent_scored = [r["id"] for r in rows if r["short"] is None
                     and r["home_total"] is not None and r["away_total"] is not None]
    ns_past = [r["id"] for r in rows if r["short"] == "NS" and r["utc"] is not None and r["utc"] < now]
    say("  NULLS")
    say(f"    FT/AOT with a null total: {len(fin_null)} (must read 0: TRUE ZERO)"
        + (f": {', '.join(map(str, fin_null))}" if fin_null else ""))
    say(f"    NS carrying both totals: {len(ns_scored)} · status absent carrying both totals: {len(absent_scored)} "
        "(each left SCHEDULED: no score-presence inference)")
    say(f"    NS with a kickoff before this run: {len(ns_past)}")

    # 7. INTEGRITY --------------------------------------------------------------------------------------------------
    no_id = sum(1 for r in rows if r["id"] is None)
    no_team = [r["id"] for r in rows if r["id"] is not None and (r["home_id"] is None or r["away_id"] is None)]
    no_kick = [r["id"] for r in rows if r["id"] is not None and r["utc"] is None]
    season_off = Counter(v(r["league_season"]) for r in rows if r["league_season"] != served)
    ts_off = [r["id"] for r in rows if r["utc"] is not None and r["date_utc"] is not None and r["utc"] != r["date_utc"]]
    off_list = sorted({r["id"] for r in rows if r["home_id"] is not None and r["away_id"] is not None
                       and (r["home_id"] not in team_ids or r["away_id"] not in team_ids)}, key=str)
    say("  INTEGRITY")
    say(f"    league.season other than {v(served)}: {counts(season_off)}")
    say(f"    timestamp and date string name different instants: {len(ts_off)}"
        + (f": {', '.join(map(str, ts_off))}" if ts_off else ""))
    say(f"    a side not in this season's /teams (sync-matches would skip it): {len(off_list)}"
        + (f": {', '.join(map(str, off_list))}" if off_list else ""))
    say(f"    not read by the adapter: not an object {not_objects} · no id {no_id} · no team id {len(no_team)} · "
        f"no readable kickoff {len(no_kick)}")
    return {"served": served, "listing": len(rows), "teams": len(team_ids), "status_served": dict(
        Counter(r["short"] if r["short"] is not None else "<absent>" for r in rows)),
        "canc": len(canc), "canc_twins": dict(classes), "ft_twin_excluded": sorted(excluded, key=str),
        "games": len(keep), "games_by_status": dict(by_status), "coverage_basis": basis,
        "unmapped": dict(unmapped), "status_absent": absent, "finished_null_totals": len(fin_null),
        "off_teams": len(off_list), "team_ids": sorted(team_ids, key=str)}


def served_phase(seasons: list[str], adapter, say) -> tuple[int, dict]:
    say(f"NBA DATA CERTIFICATION RECEIPT · SERVED (addendum 271 item 3(e)-(f), 272 item 3; #839) · read-only · "
        f"opens no database · {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    say("  run BEFORE the first `sync-matches --competition NBA`: the CANC breakdown is read before the map writes a row")
    if adapter.key_name is None:
        say(f"REFUSED: no key: {' and '.join(KEY_NAMES)} are both unset; no call made")
        return REFUSED, {"refused": "no key"}
    say(f"  key used: {adapter.key_name} (the value is never printed)")
    # the provider's requests, counted by the adapter's own _get (a 429 and its retry are two), never the reads here
    calls_before = adapter.calls
    worst, out = OK, {"seasons": {}}
    lid = LEAGUES[COMPETITION][0]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        served_list = adapter.served_seasons(COMPETITION)
        say(f"  /leagues: league {lid} {LEAGUES[COMPETITION][1]!r}, every season as served: "
            + ", ".join(v(s) for s in served_list))
    except Refused as e:
        say(str(e))
        return REFUSED, {"refused": str(e)}
    except Exception as e:                       # noqa: BLE001 - a failed read is reported, never raised
        say(f"FAILED: /leagues: {type(e).__name__}: {e}")
        return FAILED, {"failed": "/leagues"}
    for ours in seasons:
        try:
            served = adapter.provider_season(COMPETITION, ours)
        except Refused as e:
            say(f"\nNBA {ours}: {e}")
            worst = max(worst, REFUSED)
            out["seasons"][ours] = {"refused": str(e)}
            continue
        try:
            teams = adapter._get("teams", {"league": lid, "season": served}).get("response") or []
            games = adapter._get("games", {"league": lid, "season": served}).get("response") or []
        except Exception as e:                   # noqa: BLE001
            say(f"\nNBA {ours} = provider {v(served)}: FAILED: {type(e).__name__}: {e}")
            worst = max(worst, FAILED)
            out["seasons"][ours] = {"failed": f"{type(e).__name__}"}
            continue
        out["seasons"][ours] = season_report(ours, served, list(teams), list(games), say, now)
    ids = {k: set(r.get("team_ids") or []) for k, r in out["seasons"].items() if "team_ids" in r}
    if len(ids) > 1:
        every = set.intersection(*ids.values())
        say("\nTEAM IDS ACROSS SEASONS: " + " · ".join(f"{k}: {len(s)} ({len(s - every)} not in every season)"
                                                    for k, s in ids.items()))
    rem = adapter.requests_remaining
    n_calls = adapter.calls - calls_before
    say(f"\nCALLS: {n_calls} this run · {REMAINING_HEADER} {rem if rem is not None else 'not served'} (last served)")
    out.update(calls=n_calls, remaining=rem)
    return worst, out


def stored_phase(db: str, seasons: list[str], say) -> tuple[int, dict]:
    import sqlite3

    from src.walters import mlb_pitchers_gate as mp
    try:
        path = mp.check_db(db)
        for sc in SIDECARS:
            if path.with_name(path.name + sc).exists():
                raise mp.GateRefused(f"--db {db} has a {sc} sidecar ({path.name + sc}): not a fresh .backup copy; "
                                     "immutable=1 would ignore it and read a stale file; take a fresh .backup copy")
        con = mp.open_ro(path)
    except mp.GateRefused as e:
        say(f"REFUSED: {e}; nothing read")
        return REFUSED, {"refused": str(e)}
    say(f"NBA DATA CERTIFICATION RECEIPT · STORED (addendum 261 item 0: counts per season, status mapping, true-zero "
        f"nulls) · --db {path} (a .backup copy, opened {mp.COPY_URI_QUERY.lstrip('?')}) · no network")
    names = {s.name for s in MatchStatus}
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        rows = con.execute(
            "SELECT m.id, m.season, m.status, m.status_raw, m.utc_date, m.home_team_id, m.away_team_id, "
            "m.home_score, m.away_score, m.external_ids, c.sport FROM matches m JOIN competitions c "
            "ON c.id = m.competition_id WHERE c.code = ?", (COMPETITION,)).fetchall()
        team_rows = con.execute(
            "SELECT ct.season, COUNT(*) FROM competition_teams ct JOIN competitions c ON c.id = ct.competition_id "
            "WHERE c.code = ? GROUP BY ct.season", (COMPETITION,)).fetchall()
    except sqlite3.Error as e:
        say(f"REFUSED: --db {path}: cannot be read as the schema the receipt needs ({type(e).__name__}: {e})")
        return REFUSED, {"refused": "schema"}
    finally:
        con.close()
    teams = {str(s): n for s, n in team_rows}
    say(f"  stored sport values for {COMPETITION}: {counts(Counter(r[10] for r in rows))} · stored status values are "
        f"the MatchStatus NAMES ({', '.join(sorted(names))}); any other spelling is printed, never counted as one")
    by_season: dict[str, list] = defaultdict(list)
    for r in rows:
        by_season[str(r[1])].append(r)
    others = sorted(set(by_season) - set(seasons))
    if others:
        say(f"  other stored seasons (not certified here): {', '.join(f'{s} ({len(by_season[s])})' for s in others)}")
    out = {"seasons": {}}
    for ours in seasons:
        rs = by_season.get(ours, [])
        st = Counter(r[2] for r in rs)
        odd = {k: n for k, n in st.items() if k not in names}
        say(f"\nNBA {ours} (stored): {len(rs)} rows · teams linked {teams.get(ours, 0)}")
        say(f"  by status: {counts(Counter({k: n for k, n in st.items() if k in names}))}"
            + (f" · UNRECOGNISED stored values: {counts(Counter(odd))}" if odd else ""))
        say(f"  status_raw (the served code kept): {counts(Counter(r[3] if r[3] is not None else '<none>' for r in rs))}")
        fin_null = [r[0] for r in rs if r[2] == MatchStatus.FINISHED.name and (r[7] is None or r[8] is None)]
        say(f"  FINISHED with a null score: {len(fin_null)} (must read 0: TRUE ZERO)"
            + (f": match {', '.join(map(str, fin_null))}" if fin_null else ""))

        def utc(x):
            return datetime.fromisoformat(str(x)[:19]) if x else None
        past = [r[0] for r in rs if r[2] == MatchStatus.SCHEDULED.name and utc(r[4]) and utc(r[4]) < now]
        say(f"  SCHEDULED with a kickoff before this run: {len(past)}")
        ft_by_day: dict = defaultdict(list)
        for r in rs:
            if r[2] == MatchStatus.FINISHED.name and r[3] == TWIN_SHORT and r[4]:
                ft_by_day[(str(r[4])[:10], frozenset((r[5], r[6])))].append(r[0])
        excl = []
        for r in rs:
            if r[2] == MatchStatus.CANCELLED.name and r[4] and ft_by_day.get((str(r[4])[:10], frozenset((r[5], r[6])))):
                ext = json.loads(r[9]) if isinstance(r[9], str) else (r[9] or {})
                excl.append(str(ext.get("api_basketball", f"match {r[0]}")))
        kept = Counter(r[2] for r in rs) - Counter({MatchStatus.CANCELLED.name: len(excl)})
        basis = sum(kept.get(k, 0) for k in COVERAGE_BASIS)
        say(f"  FT-twin CANCELLED excluded from the counts (kept as stored): {len(excl)}"
            + (f": provider {', '.join(sorted(excl))}" if excl else ""))
        say(f"  games {len(rs) - len(excl)}: {counts(kept)} · coverage basis SCHEDULED + FINISHED + POSTPONED = {basis}")
        out["seasons"][ours] = {"rows": len(rs), "teams": teams.get(ours, 0), "by_status": dict(st),
                                "finished_null": len(fin_null), "ft_twin_excluded": sorted(excl),
                                "games": len(rs) - len(excl), "coverage_basis": basis}
    return OK, out


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(ROOT / ".env")


def main(argv=None, adapter=None) -> int:
    ap = argparse.ArgumentParser(description="NBA data certification receipt (addenda 271 item 3, 272 item 3)")
    ap.add_argument("--season", action="append", default=None,
                    help="our int-style season (repeatable; default 2026, 2025, 2024)")
    ap.add_argument("--db", default=None, help="STORED phase: a .backup copy outside data/ (no network)")
    a = ap.parse_args(argv)
    seasons = a.season or list(DEFAULT_SEASONS)
    lines: list[str] = []

    def say(line: str = "") -> None:
        lines.append(str(line))
        print(line, flush=True)

    if a.db is not None:
        code, out = stored_phase(a.db, seasons, say)
        phase = "stored"
    else:
        if adapter is None:
            _load_env()
            adapter = APIBasketballAdapter()
        code, out = served_phase(seasons, adapter, say)
        phase = "served"
    for r in (out.get("seasons") or {}).values():
        r.pop("team_ids", None)
    print(f"{TAIL} " + json.dumps({"phase": phase, "exit": code, **out}, default=str, sort_keys=True), flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
