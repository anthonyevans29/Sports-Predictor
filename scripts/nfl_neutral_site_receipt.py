"""
NFL NEUTRAL-SITE RECEIPT (#608; ARCHITECT 2026-10-27 16:10 ET, addendum 171 item 2), READ-ONLY. The ruling, verbatim:

"2. #608, the NFL neutral-site receipt.
   (a) The venue: APPROVED as proposed — a labelled, read-only derivation on intl_history.NEUTRAL_RULE's pattern: the
   venue read from /games as served (keys printed from a real response first); a team's home venue is the venue of the
   majority of its home games that season; either side missing reads UNKNOWN, never "home". Source: the coverage
   receipt's cached games_list.json where the operator's run has made it, else one call per season through
   nfl_qb_probe.get. Nothing stored. If the provider serves no venue, the receipt says so and stops, and that is the
   finding.
   (b) 2023: the span is 2024 to date. 2023 is listed from the provider read only, flagged "not stored, not walked".
   No 2023 NFL sync from this receipt: whether the QB candidate's warm-up reads the DB (2024 on) or the provider
   payloads (2023 on) is a question for the 11-02 declaration, and I will answer it there.
   (c) Both classifications printed: "neither team's home" and "outside the home team's stadium", each row labelled
   with which it meets.
   (d) "The home advantage v1 gave": recomputed read-only as proposed — _expected_home with and without the 48 on the
   same walk state, the update left as v1's — and REPORTED, never gated. A neutral rule is a model-logic change: it
   reaches production only as its own candidate through its own gate (law 3), never inside nfl_elo_qb_v1, whose arms
   stay identical in every component but the term. The receipt's count (likely a handful of games a season) says
   whether such a candidate is worth declaring; none is declared from it."

The earlier request texts: "extend the receipt to every 2024–2026 NFL game played outside the home team's stadium
(provider venue vs the home team's venue), how each was priced and its graded outcome" (10-26) and "every game whose
venue is neither team's home, 2023 to date, with the home advantage v1 gave; the Paris and Wembley cases named".

WHAT IT READS (law 1: read 2026-10-27):
  P  the provider's /games list per season (--seasons, default 2023 to the current NFL season): first the coverage
     receipt's kept answer <--games-cache>/<season>/games_list.json (scripts/nfl_qb_coverage.py's layout, default
     logs/nfl_qb_payloads), else this receipt's own kept answer <--save>/<season>/games_list.json, else ONE call
     (/games?league&season through nfl_qb_probe.get: throttled, never raises), kept under --save (refused under data/;
     logs/ is gitignored). A failed read (transport error, non-200, API errors) is FAILED: counted, named, its season
     never measured; an answer with no rows is EMPTY; --max-calls stops cleanly and the season reads INCOMPLETE. The
     keys of the first real game row, its game member and its venue member are printed before any venue field is read.
     No row with a served venue: "the provider serves no venue", exit 0, nothing classified (the finding), but ONLY
     when every season asked was read (none FAILED or INCOMPLETE) and at least one row in the provider's shape was
     read. Otherwise the venue is NOT MEASURED (the FAILED / INCOMPLETE / empty seasons named, venue_served null,
     exit 2): a read that did not happen is never the provider's answer (law 4).
  V  THE VENUE RULE (VENUE_RULE below; labelled, never a provider fact): the game's venue is game.venue.name as served
     (game.venue, else a top-level venue member; a string venue is its own name), normalized by casefold and whitespace
     only; the city is printed beside, never the key (a name or city that is not a string is a malformed venue:
     UNKNOWN, counted). A team's home venue for a season is the venue of the MAJORITY (more than half) of ALL its
     listed home games that season, the preseason left out (v1's own filter): a game with no venue served counts in
     the denominator, never for a venue; a tie, no majority or too few venues served: UNKNOWN. Per game: "neither
     team's home" (venue != the home team's home venue AND != the away team's, all three known) and "outside the
     home team's stadium" (venue != the home team's home venue, both known); any side missing: UNKNOWN, never "home"
     (law 4).
  D  the database, READ-ONLY (src.db.database.readonly_scope: a mode=ro open, a missing file refused and never
     created; or --db PATH opened the same mode=ro way): the NFL matches (nfl_scoped) by season, matches.venue /
     teams.venue filled (the adapter stores none), and the provider game joined to its stored match by
     matches.external_ids["api_american_football"] (the adapter's own key), else a previous id of a re-keyed match
     (external_ids["api_american_football_prev"]), else season + both teams + kickoff date (labelled). More than one
     candidate at any step (a provider id on two stored matches, a previous id on two, two matches on one key) is
     AMBIGUOUS and refused, never a guess (the ingestion's own rule, service.py).
  W  v1's walk, recomputed: the stored finished NFL games (preseason dropped), in stored order (utc_date, id), with
     nfl_backtest's own pure functions (NFLEloConfig, _State, _expected_home, _update; never run_backtest or
     _current_ratings, which open session_scope). Per game BEFORE its update: p_with = _expected_home(cfg, ...) and
     p_without = _expected_home(replace(cfg, home_advantage=0.0), ...) on the same state; the update stays v1's (48 in
     it). "walk recompute, counterfactual, no call". REPORTED, never gated: no verdict is printed.
  S  how it was priced, where stored: the match's Prediction row (home_win_prob, model_version, computed_at; the
     live era is nfl_predict.NFL_LIVE_SINCE, an earlier row is pre-live, never pooled); the close as grade_nfl reads it
     (close_1x2 over the 1X2 odds, then stale_book_close); the result (a tie is a PUSH), the stored pick's hit, its
     log-loss on the frozen convention (tie = home loss) and its CLV (pick p minus the close on the pick's side).
     --exports DIR (optional): the closing files (redated.closing_rows; host/ never read) give the newest run's desk
     row (home_adv_applied, prediction, market, desk call) and the void rule (redated.void_label); not given: void
     and desk read "not read", and a grade printed on such a row is marked "void unread".
2023 (any season before 2024): listed from the provider read only, flagged "not stored, not walked" (ruling (b)).
The two named cases: Wembley (Houston Texans at Jacksonville Jaguars, 2026-10-18) and Paris (Pittsburgh Steelers at
New Orleans Saints, 2026-10-25), each with its classification under both definitions.

Run:  python3 scripts/nfl_neutral_site_receipt.py [--seasons 2023,2024,2025,2026] [--games-cache DIR] [--save DIR]
                                                  [--max-calls N] [--exports DIR] [--db PATH]
Key (only when a season has no kept answer): API_AMERICAN_FOOTBALL_KEY, else API_FOOTBALL_KEY; never printed.
Writes nothing but the kept payloads. Exit 2 on a refused read (no DB file, no key for a needed call, --save under
data/) and on a venue NOT MEASURED (no venue served on the rows read while a season FAILED, was capped or none
read). The last line is "NFL-NEUTRAL-SITE-RECEIPT {json}". Paste the whole output to the architect.
"""
from __future__ import annotations

import argparse
import dataclasses
import html
import importlib.util
import json
import math
import sys
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("nfl_qb_coverage", ROOT / "scripts" / "nfl_qb_coverage.py")
cov = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cov)
probe = cov.probe                                   # scripts/nfl_qb_probe.py, as the coverage receipt loads it

SOURCE = "api_american_football"                   # APIAmericanFootballAdapter.source_name: the external_ids key
DEFAULT_GAMES_CACHE = ROOT / "logs" / "nfl_qb_payloads"
DEFAULT_SAVE = ROOT / "logs" / "nfl_neutral_site_payloads"
FIRST_STORED = 2024                                 # ruling (b): the span is 2024 to date
WALK_LABEL = "walk recompute, counterfactual, no call"
VENUE_RULE = ("nfl-neutral-site-receipt (ARCHITECT 2026-10-27, addendum 171 item 2(a)), on intl_history.NEUTRAL_RULE's "
              "pattern: venue = /games game.venue.name as served, norm = casefold + whitespace collapsed (the city "
              "printed beside, never the key; a name or city not a string -> malformed, UNKNOWN); a team's home venue "
              "for a season = the venue of more than half of ALL its listed home games that season (preseason left "
              "out; a game with no venue served counts in the denominator); a tie, no majority or no venue -> "
              "UNKNOWN. 'neither team's home' = venue != home team's home venue AND != away team's home venue; "
              "'outside the home team's stadium' = venue != home team's home venue; any side missing -> UNKNOWN, never "
              "home. Derived by us, nothing stored - never a provider fact.")
VOID_UNREAD = "not read (no --exports)"
NAMED = (("Wembley", date(2026, 10, 18), "houston", "jacksonville"),
         ("Paris", date(2026, 10, 25), "pittsburgh", "new orleans"))


def current_season(now: datetime | None = None) -> int:
    """The NFL season now, as cli.py's sync-matches counts it: the year, less one before July."""
    if now is None:
        from src.timeutil import utc_now_naive
        now = utc_now_naive()
    return now.year - 1 if now.month < 7 else now.year


def norm(v) -> str | None:
    if v is None:
        return None
    s = " ".join(html.unescape(str(v)).split()).casefold()
    return s or None


def _under_data(p: Path) -> bool:
    return (ROOT / "data").resolve() in (p, *p.parents)


# --------------------------------------------------------------------------------------------------------------- P
def read_season(season: int, games_cache: Path, fetch) -> dict:
    """{"rows": list | None, "source": text, "state": ok | empty | FAILED | INCOMPLETE}."""
    f = games_cache / str(season) / "games_list.json"
    if f.is_file():
        try:
            rows = json.loads(f.read_text())
        except (OSError, ValueError):
            rows = None
        if isinstance(rows, list):
            fetch.from_cache += 1
            return {"rows": rows, "source": f"the coverage receipt's kept answer {f}",
                    "state": "ok" if rows else "empty"}
        fetch.unreadable_cache.append(str(f))
    kept = fetch.save / str(season) / "games_list.json"
    had = kept.is_file()
    try:
        rows = fetch("games", season, "list", "games", league=probe.LEAGUE, season=season)
    except cov.Capped as e:
        return {"rows": None, "source": f"not read: the call cap ({fetch.max_calls}) reached at {e}",
                "state": "INCOMPLETE"}
    if rows is None:
        return {"rows": None, "source": f"one call: FAILED ({fetch.failed[-1]})", "state": "FAILED"}
    if not isinstance(rows, list):
        fetch.failed.append(f"{season} games list: the kept answer is not a list")
        return {"rows": None, "source": f"this receipt's kept answer {kept}: not a list (FAILED)", "state": "FAILED"}
    src = f"this receipt's kept answer {kept}" if had else "one call (/games?league&season)"
    return {"rows": rows, "source": src, "state": "ok" if rows else "empty"}


def venue_of(row) -> tuple[str, str | None, str | None]:
    """(where, name, city) of a row's venue member as served: where = "game.venue" | "venue" | "none" |
    "malformed" (a member neither an object nor a string)."""
    g = probe._game(row)
    if isinstance(g, dict) and "venue" in g and g is not row:
        v, where = g.get("venue"), "game.venue"
    elif isinstance(row, dict) and "venue" in row:
        v, where = row.get("venue"), "venue"
    else:
        return "none", None, None
    if v is None:
        return where, None, None
    if isinstance(v, str):
        return where, v, None
    if isinstance(v, dict):
        n, c = v.get("name"), v.get("city")
        if (n is not None and not isinstance(n, str)) or (c is not None and not isinstance(c, str)):
            return "malformed", None, None              # a name or city not a string: never a served venue key
        return where, n, c
    return "malformed", None, None


def _keys(v) -> str:
    return json.dumps(sorted(v)) if isinstance(v, dict) else f"(not an object: {type(v).__name__} {str(v)[:60]!r})"


def key_lines(rows) -> list[str]:
    """Law 1: the keys of the first real game row, its game member and its venue member, before any field is read."""
    first = next((r for r in rows if not cov._malformed(r)), None)
    if first is None:
        return ["  KEYS: no row in the provider's shape to print"]
    g = probe._game(first)
    L = [f"  KEYS of the first real game row (game {probe.game_id(first)}): {_keys(first)}",
         f"       its game member: {_keys(g) if g is not first else '(no game member: the row is flat)'}"]
    if isinstance(g, dict) and "venue" in g and g is not first:
        L.append(f"       its venue member (game.venue): {_keys(g['venue']) if isinstance(g['venue'], dict) else repr(g['venue'])}")
    elif "venue" in first:
        L.append(f"       its venue member (top-level venue): "
                 f"{_keys(first['venue']) if isinstance(first['venue'], dict) else repr(first['venue'])}")
    else:
        L.append("       its venue member: NONE (no venue key in the row or its game member)")
    return L


def _team(row, side):
    t = (row.get("teams") or {}) if isinstance(row, dict) else {}
    m = t.get(side) if isinstance(t, dict) else None
    m = m if isinstance(m, dict) else {}
    return m.get("id"), html.unescape(str(m.get("name") or "")) or None


def _scores(row):
    sc = row.get("scores") if isinstance(row, dict) else None
    sc = sc if isinstance(sc, dict) else {}
    out = []
    for side in ("home", "away"):
        v = sc.get(side)
        out.append(v.get("total") if isinstance(v, dict) else v)
    return tuple(out)


def _scalar_id(v) -> bool:
    return isinstance(v, (str, int)) and not isinstance(v, bool)


def classify(season: int, rows: list) -> dict:
    """The season's games, each with its venue and both classifications (VENUE_RULE)."""
    out = {"games": [], "malformed": [], "dropped": [], "venue_malformed": 0, "venue_served": 0}
    games = []
    for r in rows:
        if cov._malformed(r):
            out["malformed"].append(json.dumps(r, sort_keys=True, default=str)[:120])
            continue
        p = probe.parsed(r)
        if p is None:                                   # the adapter's parse drops it (non-competitive, no id/kickoff)
            out["dropped"].append(probe.game_label(r))
            continue
        (hid, hname), (aid, aname) = _team(r, "home"), _team(r, "away")
        if not (_scalar_id(hid) and _scalar_id(aid)):      # an id the parse took but no key can hold (#715 item 2)
            out["malformed"].append("team id not a string or an integer: "
                                    + json.dumps(r, sort_keys=True, default=str)[:90])
            continue
        where, name, city = venue_of(r)
        if where == "malformed":
            out["venue_malformed"] += 1
        if norm(name):
            out["venue_served"] += 1
        stage = str(probe._game(r).get("stage") or "")
        games.append({"season": season, "gid": probe.game_id(r), "status": p[0].name, "kickoff": p[1],
                      "stage": stage or None, "week": probe._game(r).get("week"), "pre": "pre" in stage.lower(),
                      "home_id": hid, "home": hname, "away_id": aid, "away": aname, "venue": name, "city": city,
                      "key": norm(name), "scores": _scores(r)})
    homes: dict = {}
    for g in games:
        if not g["pre"] and g["home_id"] is not None:
            homes.setdefault(g["home_id"], []).append(g)
    home_venue = {}
    for tid, gs in homes.items():
        known = [g for g in gs if g["key"]]
        c = Counter(g["key"] for g in known)
        top = c.most_common(2)
        if top and top[0][1] * 2 > len(gs):           # more than half of ALL its listed home games (ruling (a))
            cities = Counter(norm(g["city"]) for g in known if g["key"] == top[0][0] and norm(g["city"]))
            name = next(g["venue"] for g in known if g["key"] == top[0][0])
            home_venue[tid] = {"key": top[0][0], "name": name, "n": top[0][1], "of": len(known), "home": len(gs),
                               "city": cities.most_common(1)[0][0] if cities else None}
        else:
            home_venue[tid] = {"key": None, "name": None, "n": top[0][1] if top else 0, "of": len(known),
                               "home": len(gs), "city": None,
                               "why": ("no venue served on its home games" if not known else
                                       f"venue served on only {len(known)} of {len(gs)} home games"
                                       if len(known) * 2 <= len(gs) else
                                       "a tie for the most" if len(top) > 1 and top[0][1] == top[1][1] else
                                       f"no venue on more than half (the most {top[0][1]} of {len(gs)})")}
    for g in games:
        hv = home_venue.get(g["home_id"]) or {"key": None, "why": "no regular-season or postseason home game listed"}
        av = home_venue.get(g["away_id"]) or {"key": None, "why": "no regular-season or postseason home game listed"}
        g["home_venue"], g["away_venue"] = hv, av
        v = g["key"]
        g["outside"] = None if v is None or hv["key"] is None else v != hv["key"]
        g["neither"] = (None if v is None or hv["key"] is None or av["key"] is None
                        else v != hv["key"] and v != av["key"])
        g["same_city"] = (g["outside"] is True and hv.get("city") is not None and norm(g["city"]) == hv["city"])
    out["games"] = games
    out["home_venue"] = home_venue
    return out


# --------------------------------------------------------------------------------------------------------------- D
@contextmanager
def ro_session(db: str | None):
    """readonly_scope, or --db PATH opened the same mode=ro way (a missing file refused, never created)."""
    from src.db import database
    if db is None:
        with database.readonly_scope() as s:
            yield s
        return
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    path = Path(db).expanduser().resolve()
    if not path.is_file():
        raise database.ReadOnlyRefused(f"REFUSED: no DB file at --db {db!r}: a read-only read never creates one")
    eng = create_engine(f"sqlite:///file:{path.as_posix()}?mode=ro&uri=true",
                        connect_args={"uri": True, "check_same_thread": False})
    s = Session(eng, autoflush=False, expire_on_commit=False)
    try:
        yield s
    finally:
        s.close()
        eng.dispose()


def db_counts(s) -> dict:
    from sqlalchemy import select

    from src.db.schema import Match
    from src.walters.nfl_backtest import nfl_scoped
    ms = list(s.execute(nfl_scoped(select(Match))).scalars())
    by = Counter(str(m.season) for m in ms)
    fin = Counter(str(m.season) for m in ms if m.status.name == "FINISHED")
    team_ids = {t for m in ms for t in (m.home_team_id, m.away_team_id)}
    from src.db.schema import Team
    teams = list(s.execute(select(Team).where(Team.id.in_(team_ids))).scalars()) if team_ids else []
    return {"seasons": dict(sorted(by.items())), "finished": dict(sorted(fin.items())), "matches": len(ms),
            "match_venue": sum(1 for m in ms if m.venue), "teams": len(teams),
            "team_venue": sum(1 for t in teams if t.venue)}


def walk(s) -> tuple[dict, list]:
    """v1's walk over the stored finished NFL games (preseason dropped), in stored order: {match id: (p_with,
    p_without)} before each update; the update is v1's own."""
    from sqlalchemy import select

    from src.db.schema import Match, MatchStatus
    from src.walters.nfl_backtest import NFLEloConfig, _expected_home, _State, _update, nfl_scoped
    cfg = NFLEloConfig()
    cfg0 = dataclasses.replace(cfg, home_advantage=0.0)
    st = _State()
    games = list(s.execute(nfl_scoped(select(Match)).where(
        Match.status == MatchStatus.FINISHED, Match.home_score.is_not(None), Match.away_score.is_not(None),
    ).order_by(Match.utc_date, Match.id)).scalars())
    games = [m for m in games if "pre" not in (m.stage or "").lower()]
    out = {}
    for m in games:
        h, a = m.home_team_id, m.away_team_id
        out[m.id] = (_expected_home(cfg, st, h, a), _expected_home(cfg0, st, h, a))
        _update(cfg, st, h, a, m.season, m.home_score, m.away_score)
    return out, games


def join_index(s) -> dict:
    from sqlalchemy import select

    from src.db.schema import Match
    from src.walters.nfl_backtest import nfl_scoped
    by_id, by_prev, by_key = {}, {}, {}
    for m in s.execute(nfl_scoped(select(Match))).scalars():
        ext = m.external_ids or {}
        if ext.get(SOURCE) is not None:
            by_id.setdefault(str(ext[SOURCE]), []).append(m)
        for old in ext.get(f"{SOURCE}_prev") or []:
            by_prev.setdefault(str(old), []).append(m)
        hx = (m.home_team.external_ids or {}).get(SOURCE) if m.home_team else None
        ax = (m.away_team.external_ids or {}).get(SOURCE) if m.away_team else None
        if m.utc_date is not None:
            by_key.setdefault((str(m.season), str(hx), str(ax), m.utc_date.date()), []).append(m)
            by_key.setdefault((str(m.season), norm(m.home_team.name if m.home_team else None),
                               norm(m.away_team.name if m.away_team else None), m.utc_date.date()), []).append(m)
    return {"id": by_id, "prev": by_prev, "key": by_key}


def join(idx, g):
    """(match | None, how). More than one candidate at any step is AMBIGUOUS and refused, never a guess."""
    if g["gid"] is not None:
        got = idx["id"].get(str(g["gid"])) or []
        if len(got) == 1:
            return got[0], "by the provider game id (external_ids)"
        if len(got) > 1:
            return None, (f"AMBIGUOUS by the provider game id: matches {sorted(m.id for m in got)} (refused, never "
                          "a guess)")
        prev = idx["prev"].get(str(g["gid"])) or []
        if len(prev) == 1:
            return prev[0], "by a previous provider id (a re-keyed match)"
        if len(prev) > 1:
            return None, (f"AMBIGUOUS by a previous provider id: matches {sorted(m.id for m in prev)} (refused, "
                          "never a guess)")
    d = g["kickoff"].date() if g["kickoff"] else None
    for k, how in (((str(g["season"]), str(g["home_id"]), str(g["away_id"]), d),
                    "by season + both teams' provider ids + kickoff date (no stored game id; labelled)"),
                   ((str(g["season"]), norm(g["home"]), norm(g["away"]), d),
                    "by season + both team names + kickoff date (no stored game id; labelled)")):
        got = {m.id: m for m in idx["key"].get(k) or []}
        if len(got) == 1:
            return next(iter(got.values())), how
        if len(got) > 1:
            return None, f"AMBIGUOUS {how.split(' (')[0]}: matches {sorted(got)} (refused, never a guess)"
    return None, "no stored match (not stored)"


def priced_detail(s, m, closing, desk_rows) -> dict:
    """How the stored match was priced and graded, as grade_nfl reads it (read-only)."""
    from sqlalchemy import select

    from src.db.schema import Odds, Prediction
    from src.walters.close import close_1x2, outcomes_for, priced, stale_book_close
    from src.walters.nfl_predict import _is_pre_live
    from src.walters.redated import void_label
    d = {"status": m.status.name, "pre_live": _is_pre_live(m)}
    preds = sorted(s.execute(select(Prediction).where(Prediction.match_id == m.id)).scalars(),
                   key=lambda p: (p.computed_at or datetime.min, p.id))
    pr = preds[-1] if preds else None
    d["prediction"] = None if pr is None else {
        "model_version": pr.model_version, "home_win_prob": pr.home_win_prob,
        "computed_at": f"{pr.computed_at:%Y-%m-%dT%H:%M:%S}" if pr.computed_at else None, "rows": len(preds)}
    d["void"] = (void_label(closing.get(m.id), m.utc_date) if closing is not None else VOID_UNREAD)
    if m.status.name != "FINISHED" or m.home_score is None or m.away_score is None:
        d["result"] = None
    else:
        tie = m.home_score == m.away_score
        d["result"] = {"home_score": m.home_score, "away_score": m.away_score,
                       "result": "PUSH" if tie else ("H" if m.home_score > m.away_score else "A")}
        odds = list(s.execute(select(Odds).where(Odds.match_id == m.id, Odds.market == "1X2")).scalars())
        cl = close_1x2(odds, m.utc_date, outcomes_for(m.sport))
        cl = stale_book_close(s, m, cl)
        if priced(cl):
            age = cl.get("book_stamp_age_h")
            d["close"] = {"home": round(cl["fair"]["HOME"], 4), "reference": cl.get("reference", "books"),
                          "book_stamp_age_h": round(age, 2) if age is not None else None}
        else:
            d["close"] = None
            d["close_why"] = ("no 1X2 odds stored" if not odds else "no pre-kickoff capture" if cl is None else
                              cl.get("stale_book") or "unpriced (no complete book)")
        if pr is not None and d["void"] in (None, VOID_UNREAD):    # a read void is out of every tally
            p = pr.home_win_prob
            y = 1 if m.home_score > m.away_score else 0
            pick_home = p >= 0.5
            d["hit"] = None if tie else ((pick_home and y == 1) or (not pick_home and y == 0))
            d["log_loss"] = round(-(y * math.log(max(p, 1e-12)) + (1 - y) * math.log(max(1 - p, 1e-12))), 4)
            if d["close"] is not None:
                ch = d["close"]["home"]
                d["clv"] = round((p if pick_home else 1 - p) - (ch if pick_home else 1 - ch), 4)
    if desk_rows is None:
        d["desk"] = "not read (no --exports)"
    else:
        rows = desk_rows.get(m.id) or []
        if not rows:
            d["desk"] = "no closing row on file"
        else:
            run, _fam, r = rows[-1]
            hn, an = (m.home_team.name if m.home_team else None), (m.away_team.name if m.away_team else None)
            if (r.get("home_team"), r.get("away_team")) != (hn, an):
                d["desk"] = f"no closing row (teams differ: {r.get('away_team')} @ {r.get('home_team')})"
            else:
                pred = r.get("prediction") if isinstance(r.get("prediction"), dict) else {}
                mk = r.get("market") if isinstance(r.get("market"), dict) else {}
                fair = mk.get("fair_prob") if isinstance(mk.get("fair_prob"), dict) else {}
                desk = r.get("desk") if isinstance(r.get("desk"), dict) else {}
                d["desk"] = {"run": f"{run:%Y-%m-%dT%H:%MZ}" if run else None,
                             "home_adv_applied": r.get("home_adv_applied"),
                             "home_win_prob": pred.get("home_win_prob"), "market_home": fair.get("HOME"),
                             "call": desk.get("call"), "pick": desk.get("pick"), "units": desk.get("units")}
    return d


# --------------------------------------------------------------------------------------------------------------- out
def _yn(v) -> str:
    return "UNKNOWN" if v is None else ("YES" if v else "no")


def _hv(v) -> str:
    if v.get("key") is None:
        return f"UNKNOWN ({v.get('why', 'not derived')})"
    return f"{v['name']!r} ({v['n']} of {v['home']} home games listed; a venue served on {v['of']})"


def _p(v) -> str:
    return "—" if v is None else f"{v:.4f}"


def game_lines(g) -> list[str]:
    meets = [x for x, on in (("neither team's home", g["neither"]), ("outside the home team's stadium", g["outside"]))
             if on]
    ko = f"{g['kickoff']:%Y-%m-%d %H:%MZ}" if g["kickoff"] else "?"
    L = [f"  [{g['season']}] game {g['gid']} · {ko} · {g['stage'] or '(no stage)'} week {g['week']!r} · "
         f"{g['away']} @ {g['home']} · MEETS: {' + '.join(meets) or 'neither definition'}",
         f"      venue {g['venue']!r} ({g['city'] or 'city not served'}) · home team's home venue {_hv(g['home_venue'])}"
         f" · away team's home venue {_hv(g['away_venue'])} · neither team's home {_yn(g['neither'])} · outside the "
         f"home team's stadium {_yn(g['outside'])}"
         + (" · SAME CITY as the home venue (a naming variant? check)" if g.get("same_city") else "")]
    if g["pre"]:
        L.append("      preseason: not in v1's stream (v1 drops it), not walked")
    if g["season"] < FIRST_STORED:
        L.append("      not stored, not walked (ruling (b): the span is 2024 to date)")
        return L
    L.append(f"      DB: {g.get('join_how')}" + (f" · match {g['match_id']}" if g.get("match_id") else ""))
    w = g.get("walk")
    if w:
        L.append(f"      v1 (home_adv_applied 48.0): p_with {w[0]:.4f} · p_without {w[1]:.4f} · delta "
                 f"{(w[1] - w[0]) * 100:+.2f}pp ({WALK_LABEL})")
    elif g.get("match_id"):
        L.append(f"      v1: not walked ({g.get('walk_why')})")
    d = g.get("detail")
    if not d:
        return L
    pr = d["prediction"]
    if pr:
        diff = f" · walk minus stored {(w[0] - pr['home_win_prob']) * 100:+.2f}pp" if w else ""
        L.append(f"      stored: {pr['model_version']} home_win_prob {pr['home_win_prob']:.4f} (computed_at "
                 f"{pr['computed_at']}){diff}" + (" · PRE-LIVE (never pooled)" if d["pre_live"] else ""))
    else:
        L.append("      stored: no prediction stored")
    if d["void"] == VOID_UNREAD:
        L.append(f"      void: {VOID_UNREAD}: any grade below is void unread")
    elif d["void"]:
        L.append(f"      VOID: {d['void']} (out of every tally)")
    if d["result"]:
        r = d["result"]
        c = d.get("close")
        L.append(f"      result {r['away_score']}-{r['home_score']} (away-home) {r['result']}"
                 + (f" · stored pick {'PUSH' if d.get('hit') is None else 'HIT' if d['hit'] else 'miss'} · log-loss "
                    f"{d['log_loss']}" + (" (void unread)" if d["void"] == VOID_UNREAD else "")
                    if "log_loss" in d else "")
                 + (f" · close HOME {c['home']:.4f} ({c['reference']}, book stamp age "
                    f"{c['book_stamp_age_h'] if c['book_stamp_age_h'] is not None else 'unknown'} h)" if c else
                    f" · close: none ({d.get('close_why')})")
                 + (f" · clv {d['clv']:+.4f}" if "clv" in d else ""))
    desk = d["desk"]
    if isinstance(desk, dict):
        x = {k: ("not on the row" if v is None else v) for k, v in desk.items()}
        L.append(f"      closing row (run {x['run']}): home_adv_applied {x['home_adv_applied']} · home_win_prob "
                 f"{x['home_win_prob']} · market HOME {x['market_home']} · desk call {x['call']} · pick {x['pick']} · "
                 f"units {x['units']}")
    else:
        L.append(f"      closing row: {desk}")
    return L


def _named(games) -> dict:
    out = {}
    for label, d, away, home in NAMED:
        hits = [g for g in games if g["kickoff"] and g["kickoff"].date() == d and away in (norm(g["away"]) or "")
                and home in (norm(g["home"]) or "")]
        out[label] = hits[0] if len(hits) == 1 else None if not hits else "AMBIGUOUS"
    return out


def _brief(g) -> dict:
    return {"season": g["season"], "game_id": g["gid"], "kickoff": f"{g['kickoff']:%Y-%m-%dT%H:%M}" if g["kickoff"]
            else None, "home": g["home"], "away": g["away"], "venue": g["venue"], "city": g["city"],
            "home_venue": g["home_venue"].get("name"), "away_venue": g["away_venue"].get("name"),
            "neither": g["neither"], "outside": g["outside"], "preseason": g["pre"],
            "match_id": g.get("match_id"), "join": g.get("join_how"),
            "p_with": round(g["walk"][0], 4) if g.get("walk") else None,
            "p_without": round(g["walk"][1], 4) if g.get("walk") else None,
            "stored_p": ((g.get("detail") or {}).get("prediction") or {}).get("home_win_prob"),
            "result": ((g.get("detail") or {}).get("result") or {}).get("result"),
            "close_home": ((g.get("detail") or {}).get("close") or {}).get("home"),
            "void": (g.get("detail") or {}).get("void"),
            "flag": "not stored, not walked" if g["season"] < FIRST_STORED else None}


def main(argv=None, echo=print, get=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--seasons", default=None, help="default: 2023 to the current NFL season")
    ap.add_argument("--games-cache", default=str(DEFAULT_GAMES_CACHE),
                    help="the coverage receipt's payload directory (read only)")
    ap.add_argument("--save", default=str(DEFAULT_SAVE), help="this receipt's payload cache (never under data/)")
    ap.add_argument("--max-calls", type=int, default=10)
    ap.add_argument("--exports", default=None, help="the closing files' directory (optional; read only)")
    ap.add_argument("--db", default=None, help="a DB file opened mode=ro (default: the app's, through readonly_scope)")
    a = ap.parse_args(argv)
    save = Path(a.save).expanduser().resolve()
    if _under_data(save):
        echo(f"REFUSED: --save {save} is under data/ (law 5): the payloads never live there")
        return 2
    seasons = ([int(x) for x in a.seasons.split(",") if x.strip()] if a.seasons
               else list(range(2023, current_season() + 1)))
    games_cache = Path(a.games_cache).expanduser().resolve()
    fetch = cov.Fetch(save, a.max_calls, get=get)
    fetch.from_cache, fetch.unreadable_cache = 0, []

    echo("NFL NEUTRAL-SITE RECEIPT (#608; ARCHITECT 2026-10-27 16:10 ET, addendum 171 item 2) · READ-ONLY · reported, "
         "never gated: no verdict; a neutral rule is its own candidate through its own gate (law 3)")
    echo(f"rule: {VENUE_RULE}")
    from src.db.database import ReadOnlyRefused
    try:
        with ro_session(a.db) as s:                    # the refusal before any call; one short read
            dbc = db_counts(s)
    except ReadOnlyRefused as e:
        echo(str(e))
        return 2
    echo(f"D the database (mode=ro{', --db ' + a.db if a.db else ', readonly_scope'}): NFL matches by season "
         + (" · ".join(f"{k} {v} (finished {dbc['finished'].get(k, 0)})" for k, v in dbc["seasons"].items()) or "none")
         + f" · matches.venue filled {dbc['match_venue']} of {dbc['matches']} · teams.venue filled {dbc['team_venue']}"
           f" of {dbc['teams']} (the adapter stores no venue)")

    need = [y for y in seasons if not (games_cache / str(y) / "games_list.json").is_file()
            and not (save / str(y) / "games_list.json").is_file()]
    if need and get is None and not probe.KEY:
        echo(f"REFUSED: seasons {need} have no kept answer and no API_AMERICAN_FOOTBALL_KEY / API_FOOTBALL_KEY is set")
        return 2
    reads = {y: read_season(y, games_cache, fetch) for y in seasons}
    echo(f"P the provider's /games list, per season (league {probe.LEAGUE}; call cap {a.max_calls}):")
    for y, r in reads.items():
        echo(f"  {y}: {r['state']} · {r['source']}" + (f" · rows {len(r['rows'])}" if r["rows"] is not None else ""))
    for f in fetch.unreadable_cache:
        echo(f"  the coverage receipt's kept answer {f} is not a JSON list: not read (asked of this receipt's source)")
    echo(f"  calls made {fetch.calls} · answers read from the coverage receipt's cache {fetch.from_cache} · from this "
         f"receipt's kept payloads {fetch.cached} · failed {len(fetch.failed)} · answered with no rows "
         f"{len(fetch.empty)}")
    for f in fetch.failed:
        echo(f"  FAILED {f}")
    all_rows = [x for r in reads.values() if r["rows"] for x in r["rows"]]
    for ln in key_lines(all_rows):
        echo(ln)
    served = sum(1 for x in all_rows if not cov._malformed(x) and norm(venue_of(x)[1]))
    base = {"seasons": seasons, "calls": fetch.calls, "from_coverage_cache": fetch.from_cache,
            "from_kept": fetch.cached, "failed": fetch.failed, "empty": fetch.empty,
            "reads": {str(y): r["state"] for y, r in reads.items()}, "db": dbc}
    if not served:
        shaped = sum(1 for x in all_rows if not cov._malformed(x))
        unread = {st: [y for y, r in reads.items() if r["state"] == st] for st in ("FAILED", "INCOMPLETE", "empty")}
        if shaped and not unread["FAILED"] and not unread["INCOMPLETE"]:
            echo(f"the provider serves no venue (no venue name on any of {shaped} rows read; every season asked was "
                 "read): nothing is classified; that is the finding (ruling (a)).")
            echo("NFL-NEUTRAL-SITE-RECEIPT " + json.dumps({**base, "venue_served": False}, sort_keys=True,
                                                          default=str))
            return 0
        # law 4: a read that did not happen is never the provider's answer, so the finding is not made
        echo("venue NOT MEASURED: " + " · ".join(f"{st} {ys}" for st, ys in unread.items() if ys)
             + f" · no venue name on the {shaped} rows read in the provider's shape · the seasons not read were never "
               "measured, so 'the provider serves no venue' is NOT the finding; nothing is classified (exit 2)")
        echo("NFL-NEUTRAL-SITE-RECEIPT " + json.dumps({**base, "venue_served": None, "venue": "NOT MEASURED"},
                                                      sort_keys=True, default=str))
        return 2

    cls = {y: classify(y, r["rows"]) for y, r in reads.items() if r["rows"]}
    games = [g for c in cls.values() for g in c["games"]]
    exports = Path(a.exports).expanduser().resolve() if a.exports else None
    closing = desk_rows = None
    if exports is not None:
        from src.walters.redated import closing_rows
        cr = closing_rows(exports)
        desk_rows = cr["rows"]
        closing = {mid: [(run, r.get("utc_date")) for run, _f, r in v] for mid, v in desk_rows.items()}
        echo(f"S closing files {exports}/closing_*.json (redated.closing_rows; host/ never read): {cr['files']} read · "
             f"unreadable {len(cr['unreadable'])}" + (f" ({', '.join(cr['unreadable'])})" if cr["unreadable"] else "")
             + (f" · runs {cr['runs'][0]:%Y-%m-%d} .. {cr['runs'][1]:%Y-%m-%d}" if cr["runs"] else " · runs none"))
    else:
        echo("S closing files: not read (no --exports): void labels and desk rows read 'not read'")
    with ro_session(a.db) as s:
        wk, walked = walk(s)
        idx = join_index(s)
        stored_seasons = {str(m.season) for m in walked}
        echo(f"W v1's walk over the stored finished games (preseason dropped, stored order): {len(walked)} games, "
             f"seasons {sorted(stored_seasons)} · NFLEloConfig home_advantage 48.0 · p_with / p_without before each "
             f"update, the update v1's own ({WALK_LABEL})")
        for g in games:
            if g["season"] < FIRST_STORED or not (g["neither"] or g["outside"]):
                continue
            m, how = join(idx, g)
            g["join_how"] = how
            if m is None:
                continue
            g["match_id"] = m.id
            g["walk"] = wk.get(m.id)
            if g["walk"] is None:
                g["walk_why"] = ("preseason" if "pre" in (m.stage or "").lower() else
                                 f"stored {m.status.name}, not a finished scored game")
            g["detail"] = priced_detail(s, m, closing, desk_rows)

    echo(f"G the games meeting either definition ({len([g for g in games if g['neither'] or g['outside']])}), by "
         "kickoff:")
    for g in sorted((g for g in games if g["neither"] or g["outside"]),
                    key=lambda g: (g["kickoff"] or datetime.min, str(g["gid"]))):
        for ln in game_lines(g):
            echo(ln)
    counts = {}
    echo("C per season (each definition: YES / no / UNKNOWN; preseason counted apart):")
    for y in seasons:
        r = reads[y]
        if y not in cls:
            echo(f"  {y}: {r['state']} - nothing classified" + (" (its rows never measured)" if r["state"] != "empty"
                                                                 else " (the provider answered no rows)"))
            counts[str(y)] = {"state": r["state"]}
            continue
        c = cls[y]
        gs = c["games"]
        reg = [g for g in gs if not g["pre"]]
        k = {"state": r["state"], "listed": len(r["rows"]), "classified": len(gs), "preseason": len(gs) - len(reg),
             "venue_served": c["venue_served"], "malformed": len(c["malformed"]), "dropped": len(c["dropped"]),
             "venue_malformed": c["venue_malformed"]}
        for name, key in (("neither", "neither"), ("outside", "outside")):
            k[name] = {"yes": sum(1 for g in reg if g[key] is True), "no": sum(1 for g in reg if g[key] is False),
                       "unknown": sum(1 for g in reg if g[key] is None),
                       "preseason_yes": sum(1 for g in gs if g["pre"] and g[key] is True)}
        unk_teams = sorted(((t, v) for t, v in c["home_venue"].items() if v["key"] is None), key=lambda x: str(x[0]))
        unk_home = [str(t) for t, _v in unk_teams]
        k["home_venue_unknown"] = unk_home
        counts[str(y)] = k
        flag = " · not stored, not walked (ruling (b))" if y < FIRST_STORED else ""
        echo(f"  {y}: listed {k['listed']} · read {k['classified']} (preseason {k['preseason']}) · venue served "
             f"{k['venue_served']} · neither team's home YES {k['neither']['yes']} / no {k['neither']['no']} / UNKNOWN "
             f"{k['neither']['unknown']} (preseason YES {k['neither']['preseason_yes']}) · outside the home team's "
             f"stadium YES {k['outside']['yes']} / no {k['outside']['no']} / UNKNOWN {k['outside']['unknown']} "
             f"(preseason YES {k['outside']['preseason_yes']}){flag}")
        if unk_home:
            echo(f"      home venue UNKNOWN for team id(s) {', '.join(unk_home)}: "
                 + "; ".join(f"{t}: {v['why']}" for t, v in unk_teams[:8]))
        if c["malformed"]:
            echo(f"      NOT THE PROVIDER'S ROW SHAPE {len(c['malformed'])} (counted, never classified): "
                 + "; ".join(c["malformed"][:5]))
        if c["dropped"]:
            echo(f"      dropped by the adapter's parse {len(c['dropped'])} (non-competitive or unreadable; never "
                 "classified): " + "; ".join(c["dropped"][:5]))
        if c["venue_malformed"]:
            echo(f"      venue member malformed (neither an object nor a string, or a name or city not a string): "
                 f"{c['venue_malformed']} (venue UNKNOWN, counted)")
        unk = [g for g in reg if g["outside"] is None or g["neither"] is None]
        if unk:
            echo(f"      UNKNOWN under a definition {len(unk)} (never home): "
                 + "; ".join(f"game {g['gid']} {g['away']} @ {g['home']}" for g in unk[:10])
                 + (" …" if len(unk) > 10 else ""))
    named = _named(games)
    echo("N the named cases:")
    for label, d, away, home in NAMED:
        g = named[label]
        if g is None:
            y = current_season(datetime(d.year, d.month, d.day))
            st = reads[y]["state"] if y in reads else None
            named[label] = (f"not read: {y} is not in --seasons" if st is None else
                            f"not read: the {y} /games read {st}" if st in ("FAILED", "INCOMPLETE") else
                            f"not in the provider read (the {y} read {st})")
            echo(f"  {label} ({away} at {home}, {d}): {named[label]}")
        elif g == "AMBIGUOUS":
            echo(f"  {label} ({away} at {home}, {d}): AMBIGUOUS (more than one listed game)")
        else:
            echo(f"  {label}: game {g['gid']} {g['away']} @ {g['home']} · venue {g['venue']!r} ({g['city']}) · "
                 f"neither team's home {_yn(g['neither'])} · outside the home team's stadium {_yn(g['outside'])}"
                 + (f" · match {g.get('match_id')}" if g.get("match_id") else "")
                 + (f" · p_with {g['walk'][0]:.4f} p_without {g['walk'][1]:.4f}" if g.get("walk") else ""))
    rows = [_brief(g) for g in sorted((g for g in games if g["neither"] or g["outside"]),
                                      key=lambda g: (g["kickoff"] or datetime.min, str(g["gid"])))]
    echo("NFL-NEUTRAL-SITE-RECEIPT " + json.dumps({
        **base, "venue_served": True, "walked": len(walked), "counts": counts, "rows": rows,
        "named": {k: (_brief(v) if isinstance(v, dict) else v) for k, v in named.items()},
        "exports": str(exports) if exports else None}, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
