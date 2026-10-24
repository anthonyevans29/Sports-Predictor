"""
NHL GSAx FEASIBILITY RECEIPT (ARCHITECT 2026-10-23, addendum 157 item 2(a); lane nhl, #105) — read-only, counts only.

Verbatim: "(a) GSAx feasibility: from the stored shot table (our own NHL API events; nothing external), per season
2023-24..2025-26: shots with a goalie_id by event type (blocked shots carry none by nature and are out), exclusions named
and counted (empty net, shootout, relief appearances: the goalie on ice is the one the event names), per-goalie exposure
(shots faced, xG faced, goals against) and the join to the stored starters (nhl_goalies.py); the numerator and the
denominator on the same event set. Counts only; no model."

What it reads (law 1: every name is the schema's own, src/db/schema.py):
- nhl_shot_events: nhl_game_id, game_start, game_type, event_type, period, period_type, side, owner_side, x, y,
  shot_type, situation_code, home_defending_side, goalie_id. The season is the NHL game id's own first four digits
  (2023020001 -> 2023, the 2023-24 season); game_type as stored (2 regular season, 3 playoffs).
- nhl_goalie_appearances (the stored starters, src/ingestion/nhl_goalies.py): nhl_game_id, goalie_id, goalie_name,
  side, is_starter (the API's own flag; NULL when it was not found), shots_against, goals_against.

The event set, per event, in this order (the first that applies decides; each reason counted):
  1. outside 2023-24..2025-26 by its game id, or a game type other than 2 or 3: not read.
  2. the frozen xG rules, src/models/nhl_xg.prepare, unchanged (R1 blocked, R1 not an unblocked attempt, R2 shootout,
     R3 no shooter side, R4 no situation code, R5 empty net, R6 missing coordinates, R7 no orientation).
  3. no goalie named (goalie_id NULL) on an event the rules keep: out, counted. The goalie on ice is the one the event
     names, never inferred.
  The GSAx event set is what is left: unblocked attempts, not a shootout, the defending goalie in net by the situation
  code, coordinates and orientation present, a goalie named. On that one set: shots faced (n), goals against (the
  goals in it), and xG faced (the sum of the frozen fit's xG). The numerator (xG faced - goals against) and the
  denominator (shots faced) are read from the same events; no other count is mixed in.

xG: v7's fit as nhl_shadow.live_xg builds it (nhl_xg.fit on the 2023-24 window, na_level=False), applied to every
event of the set. 2023-24 is the fit's own season, so its xG is in-sample there; the receipt says so on its line.

The join to the stored starters, per event of the set, by (nhl_game_id, goalie_id): no appearance row; an appearance
whose side is not the defending side (the shooter's opposite); is_starter True (the starter), False (a relief
appearance: the goalie on ice is the one the event names), NULL (the flag was not found). And per goalie-game, the
boxscore cross-check: the events naming that goalie whose type is shot-on-goal or goal, not a shootout, against the
appearance's shots_against, and the goals among them against its goals_against (agree / differ; the cross-check reads
the boxscore's own counts and is not part of the event set).

Per-goalie exposure, regular season (game type 2) per season, sorted by shots faced: goalie id, name (as stored on
the appearances), games with an event in the set, starts (is_starter True), shots faced, xG faced, goals against,
xG - goals against. Playoffs are counted in the season's lines and not tabled.

Opens the DB read-only (mode=ro URI; a copy that refuses mode=ro falls back to the plain path with PRAGMA query_only =
ON, #421); never creates one; writes nothing.

Run:  python3 scripts/nhl_gsax_feasibility.py [--db PATH] [--no-goalies]
--no-goalies leaves out the per-goalie tables (the season lines stay). Paste the whole output on #105.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SEASONS = (2023, 2024, 2025)               # 2023-24 .. 2025-26, by the game id's first four digits
GAME_TYPES = (2, 3)                         # regular season, playoffs (nhl_goalies.KEEP_GAME_TYPES)
REGULAR = 2
SOG = frozenset({"shot-on-goal", "goal"})   # the events a boxscore's shots against counts
NO_GOALIE = "no_goalie_named"
RULE_ORDER = ("blocked", "not_eligible", "shootout", "no_side", "no_situation", "empty_net", "missing_coords",
              "no_orientation", NO_GOALIE)
RULE_TEXT = {"blocked": "blocked shot (R1; carries no goalie by nature)",
             "not_eligible": "not an unblocked attempt (R1)",
             "shootout": "shootout (R2)",
             "no_side": "no shooter side (R3)",
             "no_situation": "no situation code (R4)",
             "empty_net": "empty net: the defending goalie digit 0 (R5)",
             "missing_coords": "missing coordinates (R6)",
             "no_orientation": "no orientation (R7)",
             NO_GOALIE: "kept by the rules but no goalie named (goalie_id NULL)"}


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
        con.execute("SELECT 1 FROM nhl_shot_events LIMIT 1")
        return con, "mode=ro URI"
    except sqlite3.OperationalError:
        con = sqlite3.connect(str(p), timeout=60)
        con.execute("PRAGMA query_only = ON")
        con.execute("SELECT 1 FROM nhl_shot_events LIMIT 1")
        return con, "plain path with PRAGMA query_only = ON (mode=ro refused)"


def season_of(nhl_game_id) -> int | None:
    """The NHL game id's season: its first four digits (2023020001 -> 2023). None for an id that is not ten digits."""
    try:
        g = int(nhl_game_id)
    except (TypeError, ValueError):
        return None
    return g // 1_000_000 if 1_000_000_000 <= g <= 9_999_999_999 else None


def label(season: int) -> str:
    return f"{season}-{(season + 1) % 100:02d}"


def _dt(v) -> datetime | None:
    try:
        return datetime.fromisoformat(str(v)) if v is not None else None
    except ValueError:
        return None


EVENT_COLS = ("nhl_game_id", "match_id", "game_start", "game_type", "event_type", "period", "period_type", "side",
              "owner_side", "x", "y", "shot_type", "situation_code", "home_defending_side", "goalie_id")


def load(con):
    """(events, appearances, why). Events as nhl_xg.Shot plus their goalie_id; appearances keyed (nhl_game_id,
    goalie_id), or None with the reason when the table cannot be read."""
    from src.models import nhl_xg as nx
    events = []
    for r in con.execute(f"SELECT {', '.join(EVENT_COLS)} FROM nhl_shot_events ORDER BY game_start, nhl_game_id"):
        d = dict(zip(EVENT_COLS, r))
        shot = nx.Shot(d["nhl_game_id"], d["match_id"], _dt(d["game_start"]), d["game_type"], d["event_type"] or "",
                       d["period"], d["period_type"], d["side"], d["owner_side"], d["x"], d["y"], d["shot_type"],
                       d["situation_code"], d["home_defending_side"])
        events.append((shot, d["goalie_id"]))
    apps = {}
    try:
        rows = con.execute("SELECT nhl_game_id, goalie_id, goalie_name, side, is_starter, shots_against, "
                           "goals_against FROM nhl_goalie_appearances").fetchall()
    except sqlite3.OperationalError as e:            # never read as "no appearance row" (#660 review)
        return events, None, f"nhl_goalie_appearances could not be read: {e}"
    for g, gid, name, side, st, sa, ga in rows:
        apps[(g, gid)] = {"name": name, "side": side, "is_starter": None if st is None else bool(st),
                          "shots_against": sa, "goals_against": ga}
    return events, apps, None


def xg_model(events):
    """v7's frozen fit (nhl_shadow.live_xg's own call), or (None, why)."""
    from src.models import nhl_xg as nx
    fit_set = [s for s, _ in events if s.game_start is not None and nx.FIT_FROM <= s.game_start < nx.FIT_TO]
    try:
        return nx.fit(fit_set, na_level=False), None
    except ValueError as e:
        return None, str(e)


def receipt(events, apps, model) -> dict:
    """{season: {type: tallies}} and the per-goalie exposure; pure (the tests read it)."""
    from src.models import nhl_xg as nx
    out: dict = {"outside": Counter(), "seasons": {}}
    for s, gid in events:
        season = season_of(s.nhl_game_id)
        if season not in SEASONS or s.game_type not in GAME_TYPES:
            out["outside"]["season" if season not in SEASONS else f"game type {s.game_type}"] += 1
            continue
        t = out["seasons"].setdefault(season, {}).setdefault(s.game_type, {
            "by_type": defaultdict(Counter), "excluded": Counter(), "en_with_goalie": 0,
            "n": 0, "goals": 0, "xg": 0.0, "join": Counter(), "relief_games": set(), "games": set(),
            "per_goalie": {}, "cross": defaultdict(lambda: [0, 0])})
        et = (s.event_type or "").lower()
        t["by_type"][et]["events"] += 1
        t["by_type"][et]["with goalie_id" if gid is not None else "no goalie_id"] += 1
        key = (s.nhl_game_id, gid)
        if gid is not None and not ((s.period_type or "").upper() == "SO"
                                    or (s.game_type == 2 and (s.period or 0) >= 5)):
            c = t["cross"][key]                  # the boxscore cross-check: every goalie-game an event names (a
            if et in SOG:                        # zero-SOG one compares as 0 and 0, #660 review); SOG and goals
                c[0] += 1
                c[1] += 1 if et == "goal" else 0
        p = nx.prepare(s)
        if p.excluded:
            t["excluded"][p.excluded] += 1
            if p.excluded == "empty_net" and gid is not None:
                t["en_with_goalie"] += 1
            continue
        if gid is None:
            t["excluded"][NO_GOALIE] += 1
            continue
        x = model.xg(p) if model is not None else 0.0
        t["n"] += 1
        t["goals"] += p.goal
        t["xg"] += x
        t["games"].add(s.nhl_game_id)
        a = apps.get(key) if apps is not None else None
        defending = "away" if p.side == "home" else "home"
        role = None                              # the defending goalie's role, only from a row on the defending side
        if apps is None:
            t["join"]["starter table unreadable"] += 1
        elif a is None:
            t["join"]["no appearance row"] += 1
        elif a["side"] != defending:             # exclusive: a shooting-side row establishes no role (#660 review)
            t["join"]["appearance side is not the defending side"] += 1
        else:
            role = a["is_starter"]
            t["join"][{True: "the starter", False: "a relief appearance", None: "starter flag NULL"}[role]] += 1
            if role is False:
                t["relief_games"].add(s.nhl_game_id)
        g = t["per_goalie"].setdefault(gid, {"games": set(), "starts": set(), "shots": 0, "xg": 0.0, "goals": 0,
                                             "name": None, "joined": False})
        if a is not None:
            g["joined"] = True
            g["name"] = g["name"] or a["name"]
        g["games"].add(s.nhl_game_id)
        if role:
            g["starts"].add(s.nhl_game_id)
        g["shots"] += 1
        g["xg"] += x
        g["goals"] += p.goal
    for season in out["seasons"].values():           # the boxscore cross-check against the stored appearances
        for t in season.values():
            agree = Counter()
            for key, (sog, goals) in t["cross"].items():
                if apps is None:
                    agree["starter table unreadable"] += 1
                    continue
                a = apps.get(key)
                if a is None:
                    agree["no appearance row"] += 1
                    continue
                for what, mine, theirs in (("shots against", sog, a["shots_against"]),
                                           ("goals against", goals, a["goals_against"])):
                    agree[f"{what}: " + ("boxscore NULL" if theirs is None else
                                         "agree" if mine == theirs else "differ")] += 1
            t["cross_tally"] = agree
    return out


def _fmt_types(t) -> str:
    return " · ".join(f"{et} {c['events']} (goalie_id {c['with goalie_id']}, none {c['no goalie_id']})"
                      for et, c in sorted(t["by_type"].items()))


def lines(out: dict, model, why: str | None, form: str, path: Path, goalies: bool = True,
          apps_why: str | None = None) -> list[str]:
    L = [f"NHL GSAx FEASIBILITY (ARCHITECT 2026-10-23, addendum 157 item 2(a); #105) · read-only, counts only · "
         f"DB {path.name} ({form})"]
    if apps_why:
        L.append(f"STARTERS: UNAVAILABLE ({apps_why}); the join and the boxscore cross-check read "
                 "'starter table unreadable', never 'no appearance row'")
    if model is None:
        L.append(f"xG: UNAVAILABLE ({why}); xG faced prints 0 and the shot and goal counts stand")
    else:
        L.append(f"xG: v7's frozen fit (nhl_xg.fit, 2023-24 window, no na level): {model.n_fit} attempts, "
                 f"{model.goals_fit} goals, last game {model.fit_last_game}; 2023-24's xG is in-sample (the fit's season)")
    if out["outside"]:
        L.append("not read: " + " · ".join(f"{k} {v}" for k, v in sorted(out["outside"].items())))
    for season in SEASONS:
        types = out["seasons"].get(season)
        if not types:
            L.append(f"{label(season)}: no stored event")
            continue
        for gt in GAME_TYPES:
            t = types.get(gt)
            if t is None:
                L.append(f"{label(season)} {'regular season' if gt == REGULAR else 'playoffs'} (type {gt}): no stored event")
                continue
            name = "regular season" if gt == REGULAR else "playoffs"
            L.append(f"{label(season)} {name} (type {gt}) · events by type: {_fmt_types(t)}")
            L.append(f"  excluded, in rule order: " + " · ".join(f"{RULE_TEXT[k]} {t['excluded'].get(k, 0)}"
                                                              for k in RULE_ORDER)
                     + f" · (empty-net events that name a goalie anyway: {t['en_with_goalie']})")
            L.append(f"  THE EVENT SET: shots faced {t['n']} · goals against {t['goals']} · xG faced {t['xg']:.2f} · "
                     f"xG - GA {t['xg'] - t['goals']:+.2f} · games {len(t['games'])} · goalies {len(t['per_goalie'])} "
                     f"(numerator and denominator on these {t['n']} events)")
            L.append("  join to the stored starters, per event: " + (" · ".join(
                f"{k} {v}" for k, v in sorted(t["join"].items())) or "none")
                     + f" · games with a relief appearance facing a shot {len(t['relief_games'])}")
            L.append("  boxscore cross-check, per goalie-game (shot-on-goal + goal naming the goalie, no shootout): "
                     + (" · ".join(f"{k} {v}" for k, v in sorted(t["cross_tally"].items())) or "none"))
            if gt != REGULAR or not t["per_goalie"]:
                continue
            shots = sorted((g["shots"] for g in t["per_goalie"].values()), reverse=True)
            L.append(f"  per goalie, shots faced: max {shots[0]} · median {statistics.median(shots):g} · min "
                     f"{shots[-1]} · >= 1000: {sum(x >= 1000 for x in shots)} · >= 500: {sum(x >= 500 for x in shots)}"
                     f" · < 100: {sum(x < 100 for x in shots)}")
            if not goalies:
                continue
            L.append("  goalie_id · name · games · starts · shots faced · xG faced · goals against · xG - GA")
            for gid, g in sorted(t["per_goalie"].items(), key=lambda kv: (-kv[1]["shots"], kv[0])):
                name = g["name"] or ("(name not stored)" if g["joined"] else "(no appearance row)")
                L.append(f"  {gid} · {name} · {len(g['games'])} · {len(g['starts'])} · "
                         f"{g['shots']} · {g['xg']:.2f} · {g['goals']} · {g['xg'] - g['goals']:+.2f}")
    return L


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", help="SQLite file (default: DATABASE_URL, else ./data/sports.db)")
    ap.add_argument("--no-goalies", action="store_true", help="leave out the per-goalie tables")
    a = ap.parse_args(argv)
    p = db_path(a.db)
    con, form = open_read(p)
    try:
        events, apps, apps_why = load(con)
    finally:
        con.close()
    model, why = xg_model(events)
    for ln in lines(receipt(events, apps, model), model, why, form, p, goalies=not a.no_goalies, apps_why=apps_why):
        print(ln)
    return 0


if __name__ == "__main__":
    sys.exit(main())
