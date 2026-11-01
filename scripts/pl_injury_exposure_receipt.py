"""
THE PL INJURY EXPOSURE RECEIPT (ARCHITECT 2026-11-01 09:00 ET, addendum 196 item 2; the finding is #754), READ-ONLY.

THE RULING (ARCHITECT 2026-11-01 09:00 ET, addendum 196), verbatim:
"1. THE FINDING (from the operator's PL audit of 11-01, verified by the architect at main 0d3e84df): the soccer injury
input counts EVERY stored feed entry as a player missing for the fixture. The feed is api-football's fixture-history
injuries: `ingestion/service.py` keeps, per team, every entry whose fixture date is within 14 days past or in the
future, of BOTH types the feed emits ("Missing Fixture" and "Questionable"; the type is stored, never read),
wipe-and-replace per sync; `models/factors.injury_adjustment` then applies a position-weighted xG reduction per entry
(0.06 attacker, 0.04 midfielder, 0.025 defender, 0.05 goalkeeper, 0.03 default), capped at 25%, with no regard to the
entry's type or to WHICH fixture it names. So a player who missed a match ten days ago and is back, or who is
"Questionable" and starts, is scored as absent. Saturday's receipt: Bournemouth 9 entries (−25% xG) and Leeds 5 (−15%)
— the export's own name lists carried E. J. Kroupi (on Bournemouth's bench), D. James and N. Elvedi (started for
Leeds), A. Stach (bench) — and the model priced Bournemouth at 25.6% against the market's 45%. The same mechanism
touched Man City–Brighton, Spurs–Palace and Villa–Fulham. This is a candidate cause of the PL model's anti-predictive
divergence from the market (13/30, behind the close; the floor-blocked big-edge rows 3–6), not a proof. Logged
attributed in BACKLOG; an Issue (track:model, class:finding, sport:soccer, size:M).
2. THE RECEIPT (Code, read-only, before any change; two parts): (a) from the HOST DB's Injury table as it stands (my
block, read-only): per PL team, the stored entries by type (Missing Fixture / Questionable) and by the named fixture's
date relative to now (past / next / later), with the count the model would have scored as missing and the count a
type-and-fixture rule would score — the mechanism's exposure, every team; (b) for the four Saturday games the audit
names, the provider's lineups for those finished fixtures (four metered calls, ruled: one each) against the stored name
lists — per name: started, bench, absent. Code writes (a) as a block for the host and (b) as a laptop block
(api-football needs no VPN rule); the receipt goes on the finding's Issue. Nothing is changed in the model by the
receipt.
3. THE CANDIDATE's SHAPE (declared only after the receipt is read, by a later addendum; written here so Code builds
nothing else): the same v22 with ONE classification rule — an entry counts as missing for a fixture only if its type
is "Missing Fixture" AND the fixture it names is this fixture or a later one; "Questionable" entries and past-only
entries count for nothing. The position weights and the 25% cap stay exactly as they are (no retune; one candidate,
one rule). [...]"
Nothing of item 3 is built here: the rule is COUNTED, never applied to a price.

TWO SUBCOMMANDS (each run as a block from stdin in a checkout root, `python3 - <subcommand> [args] <<'PYEOF'`, or as a
file, `python3 scripts/pl_injury_exposure_receipt.py <subcommand> [args]`):

  exposure  (part (a), the HOST at tag v1.6.1, no network). Imports only what v1.6.1 holds: src.walters.redated (the
            closing files' one reader), src.db.database (readonly_scope, ReadOnlyRefused), src.db.schema,
            src.models.factors (injury_adjustment, CALLED, its weights never copied). The database is opened mode=ro:
            the configured file through database.readonly_scope(), or --db PATH (refused under data/ and when
            missing) through a mode=ro URI. Per PL team of --season (competition_teams), every stored injuries row,
            bucketed by the fixture it names (fixture_source_id joined to matches.external_ids["api_football"], and
            "api_football_prev", labelled) against --now and the team's next PL match (status scheduled or live; a
            future row of another status is passed over and printed): past / next / upcoming, before the next PL match
            / later / upcoming, no next PL match stored / no fixture id stored / fixture not stored / fixture id held by
            2+ stored matches / fixture held by a match the team is not in. MODEL = every stored row (the model's
            list, training.py: every Injury row of the team; export.py: injuries.<side>_count = len(rows)); RULE =
            type "Missing Fixture" (exact) AND the named fixture is the next PL match or a later one; UNDECIDABLE =
            type "Missing Fixture" whose fixture cannot be placed (counted apart, never folded into the rule). Then
            the Saturday games (--date) and the host's own closing rows for them (redated.closing_rows(--exports)),
            with the test of whether the stored list is the one the closing row consumed (#688's ruling 1(b) test).
  lineups   (part (b), the LAPTOP at main, api-football; FOUR metered calls at most, ruled one per game). The rows are
            the host's closing files pulled to the laptop (--exports, default exports/host: the host is the PL writer
            of record); the fixture id comes from --fixture KEY=ID or the laptop DB (mode=ro) by the row's exact team
            names and --date; the provider team ids from the DB teams. One /fixtures/lineups read per game through
            scripts/lineup_history_probe.py's get (throttled, never raises), its answer kept under --save (refused
            under data/; a kept answer makes no call). Per name on the row's list: started / bench / AMBIGUOUS / absent
            / unread, by scripts/pl_injury_classification_receipt.py's name_match (#688). Sides are told apart by the
            provider team id, never by name.

THE CONSERVATIVE UNKNOWNS (law 4): types are printed VERBATIM ("(no type stored)" for a null); a type that is not the
exact word "Missing Fixture" is never counted by the rule. A failed read is FAILED, an empty answer counted apart, a
member not the provider's shape counted and named, and a name not found on a side whose answer was not read in full (a
member malformed, an XI not eleven named starters, an empty bench) is "unread", never "absent"; a row's name-list member
that is not a name is counted, never classed. A missing count is UNKNOWN, never 0. --max-calls stops cleanly and says
INCOMPLETE.

Writes nothing but (b)'s kept payloads (and SQLite's own -wal/-shm sidecars, which a mode=ro open of a WAL file with no
live connection creates: the header's SIDECARS line). No verdict, no threshold, no model, Desk or export change.
Exit 0 on a completed read; 2 on a refusal. The key (API_FOOTBALL_KEY) is never printed.

Run:  python3 scripts/pl_injury_exposure_receipt.py exposure [--db PATH] [--season 2026/27] [--now ISO]
                                                             [--exports DIR] [--date 2026-10-31]
      python3 scripts/pl_injury_exposure_receipt.py lineups [--exports DIR] [--db PATH] [--date 2026-10-31]
                                                            [--fixture KEY=ID ...] [--save DIR] [--max-calls N]
Paste the whole output on #754.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

_FILE = globals().get("__file__")
# run as a file: the checkout above scripts/; run from stdin (`python3 - ...`, __file__ "<stdin>"): the working
# directory, which the block sets to the checkout root
ROOT = Path(_FILE).resolve().parents[1] if _FILE and Path(_FILE).is_file() else Path.cwd()
sys.path.insert(0, str(ROOT))

from src.walters import redated  # noqa: E402   (on v1.6.1; imports no src.db module)

TAG = "PL-INJURY-EXPOSURE-RECEIPT"
TAG_LINEUPS = "PL-INJURY-LINEUPS-RECEIPT"
SOURCE = "api_football"                       # the adapter's source_name; the external_ids key of matches and teams
FAMILY, COMPETITION = "SOCCER", "PL"
DEFAULT_SEASON = "2026/27"
DEFAULT_DATE = "2026-10-31"                   # the Saturday the audit names
MAX_CALLS = 4                                 # ruled: one call per game, four games
XI_SIZE = 11                                  # a listed XI: eleven named starters
ROW_NAMES_KEPT = 8                            # export.py: injuries.<side>_names is "[:8]  # first 8 only"
MISSING = "Missing Fixture"                   # the rule's type, exact (item 3)
NO_TYPE = "(no type stored)"
CAP = 0.25                                    # the cap as the factor states it; read here only to say "at the cap"

# the buckets (the named fixture against --now and the team's next PL match)
PAST, NEXT, BEFORE_NEXT, LATER, NO_NEXT = ("past", "next", "upcoming, before the next PL match", "later",
                                           "upcoming, no next PL match stored")
NO_FIX_ID, NOT_STORED, FIX_AMBIG = "no fixture id stored", "fixture not stored", "fixture id held by 2+ stored matches"
NOT_TEAMS = "fixture held by a match the team is not in"
BUCKETS = (PAST, NEXT, BEFORE_NEXT, LATER, NO_NEXT, NO_FIX_ID, NOT_STORED, FIX_AMBIG, NOT_TEAMS)
RULE_BUCKETS = (NEXT, LATER)
UNDECIDABLE_BUCKETS = (NO_FIX_ID, NOT_STORED, FIX_AMBIG, NO_NEXT, NOT_TEAMS)
# law 4: the team's NEXT PL match is taken only from rows that can still be played (a stale_orphan, cancelled or
# postponed row with a future date is never "next"; the rows passed over are printed)
NEXT_STATUSES = ("scheduled", "live")

MODEL_COUNTS = (
    "WHAT THE MODEL COUNTS (law 1, read at main 0d3e84df and at v1.6.1): every stored injuries row of the team "
    "(walters/training.py: injuries_by_team holds every Injury row; export.py: injuries.<side>_count = len(rows)), "
    "each a position-weighted xG reduction through models/factors.injury_adjustment (called here, never copied), "
    "capped at 25%; the row's type and the fixture it names are never read.")
RULE_TEXT = (
    "THE RULE BEING COUNTED (item 3, verbatim): \"an entry counts as missing for a fixture only if its type is "
    "\"Missing Fixture\" AND the fixture it names is this fixture or a later one; \"Questionable\" entries and "
    "past-only entries count for nothing.\" Counted against the team's NEXT PL match: RULE = type exactly "
    f"{MISSING!r} AND bucket next or later; UNDECIDABLE = type exactly {MISSING!r} AND the fixture cannot be placed "
    "(no fixture id stored / fixture not stored / fixture id held by 2+ stored matches / upcoming, no next PL match "
    "stored / fixture held by a match the team is not in), counted apart, never folded into the rule count. Any "
    "other type word (verbatim) is never counted by the rule.")
BUCKETS_TEXT = (
    "BUCKETS (the fixture an entry names, fixture_source_id joined to matches.external_ids[\"api_football\"], else "
    "\"api_football_prev\", labelled): past = kickoff before now · next = the team's next PL match (earliest PL match "
    "with kickoff >= now and status scheduled or live; a future row of another status is never next, and is printed) "
    "· upcoming, before the next PL match = now <= kickoff < the next PL kickoff, another match "
    "(a cup tie) · later = kickoff >= the next PL kickoff, not the next PL match · upcoming, no next PL match stored "
    "· no fixture id stored · fixture not stored · fixture id held by 2+ stored matches · fixture held by a match the "
    "team is not in (never bucketed by its kickoff).")
NOTHING_CHANGED = "Nothing is changed in the model by the receipt (addendum 196 item 2); no verdict, no threshold."
SIDECARS = ("SQLITE SIDECARS (a reading, not a write): the app runs the database in WAL mode, and SQLite's own mode=ro "
            "open of a WAL file with no live connection creates <file>-wal and <file>-shm beside it and leaves them "
            "(empty sidecars, no row written). database.readonly_scope (#706) opens the same way.")

# THE SATURDAY GAMES (item 1): keyed by the teams, never by match id (ids are machine-local)
ALIASES = {"bournemouth": ("bournemouth",), "leeds": ("leeds",), "man city": ("manchester city", "man city"),
           "brighton": ("brighton",), "spurs": ("tottenham", "spurs"), "palace": ("crystal palace", "palace"),
           "villa": ("aston villa", "villa"), "fulham": ("fulham",)}
GAMES = (("bou-lee", "Bournemouth–Leeds", "bournemouth", "leeds"),
         ("mci-bri", "Man City–Brighton", "man city", "brighton"),
         ("tot-cry", "Spurs–Palace", "spurs", "palace"),
         ("avl-ful", "Villa–Fulham", "villa", "fulham"))
GAME_KEYS = tuple(g[0] for g in GAMES)

STARTED, BENCH, ABSENT, AMBIG, UNREAD = "started", "bench", "absent", "AMBIGUOUS", "unread"
CLASSES = (STARTED, BENCH, ABSENT, AMBIG, UNREAD)
ABSENT_TEXT = "absent (no name in the side's XI or bench matches; a name form the match cannot see is possible)"


class Refused(Exception):
    """A refused read: exit 2, never read as empty."""


class Capped(Exception):
    pass


def _under_data(p: Path) -> bool:
    return (ROOT / "data").resolve() in (p, *p.parents)


def _d(v) -> dict:
    return v if isinstance(v, dict) else {}


def _int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def _when(v: str) -> datetime:
    d = redated.as_utc(v)
    if d is None:
        raise argparse.ArgumentTypeError(f"not a date-time (YYYY-MM-DDTHH:MM[:SS], UTC): {v!r}")
    return d


def _day(v: str) -> str:
    try:
        return datetime.strptime(v, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a date (YYYY-MM-DD): {v!r}")


def _fmt(d) -> str:
    d = redated.as_utc(d)
    return f"{d:%Y-%m-%d %H:%M}Z" if d else "no kickoff"


def _days(ko, now) -> str:
    ko = redated.as_utc(ko)
    return f"{(ko - now).total_seconds() / 86400:+.1f} d" if ko else "? d"


def _pct(x: float | None) -> str:
    return "?" if x is None else f"{x * 100:.1f}%"


def checkout_describe() -> str:
    """The checkout's tag (git describe), read-only; "unknown" when git cannot say."""
    try:
        r = subprocess.run(["git", "describe", "--tags", "--always", "--dirty"], cwd=str(ROOT), capture_output=True,
                           text=True, timeout=10)
        return r.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


# ---- the database (mode=ro; #688's open_db and check_schema, copied: that script is not on v1.6.1) ------------------

@contextmanager
def open_db(db: str | None):
    """(session, label): --db opened through a mode=ro URI (refused under data/, refused when missing), else the app's
    configured file through src.db.database.readonly_scope()."""
    if db:
        path = Path(db).expanduser().resolve()
        if _under_data(path):
            raise Refused(f"REFUSED: --db {path} is under data/ (law 5): --db is a .backup copy OUTSIDE data/; the "
                          "live file is read without --db")
        if not path.is_file():
            raise Refused(f"REFUSED: no DB file at {path}: a read-only read never creates one")
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        eng = create_engine(f"sqlite:///file:{path.as_posix()}?mode=ro&uri=true",
                            connect_args={"uri": True, "check_same_thread": False})
        s = Session(eng, autoflush=False, expire_on_commit=False)
        try:
            yield s, f"--db {path} (mode=ro URI)"
        finally:
            s.close()
            eng.dispose()
        return
    from src.db import database
    url = database.SessionLocal.kw["bind"].url
    try:
        with database.readonly_scope() as s:
            yield s, f"{url.database} (database.readonly_scope: mode=ro URI)"
    except database.ReadOnlyRefused as e:
        raise Refused(str(e)) from None


READS = {"matches": {"id", "home_team_id", "away_team_id", "utc_date", "status", "home_score", "away_score",
                     "competition_id", "external_ids", "sport"},
         "teams": {"id", "name", "external_ids", "sport"},
         "competitions": {"id", "code", "sport"},
         "competition_teams": {"competition_id", "team_id", "season"},
         "injuries": {"id", "team_id", "player_name", "player_position", "reason", "type", "fixture_source_id",
                      "refreshed_at"}}


def check_schema(s, reads=READS) -> None:
    from sqlalchemy import inspect
    ins = inspect(s.get_bind())
    have = set(ins.get_table_names())
    miss = sorted(t for t in reads if t not in have)
    if miss:
        raise Refused(f"REFUSED: table(s) {', '.join(miss)} not in the database (law 1)")
    for t, cols in reads.items():
        got = {c["name"] for c in ins.get_columns(t)}
        if cols - got:
            raise Refused(f"REFUSED: columns {', '.join(sorted(cols - got))} not in {t} (law 1)")


# ---- the Saturday games (both parts) --------------------------------------------------------------------------------

def _alias(team: str, name) -> bool:
    n = str(name or "").casefold()
    return any(a in n for a in ALIASES[team])


def pair_matches(a: str, b: str, home, away) -> bool:
    """One side's alias matches home and the other's away, either orientation."""
    return (_alias(a, home) and _alias(b, away)) or (_alias(b, home) and _alias(a, away))


# =====================================================================================================================
# PART (a): exposure
# =====================================================================================================================

def reduction(rows: list) -> float:
    """1 - the multiplier factors.injury_adjustment gives this list (the model's own arithmetic, called)."""
    from src.models.factors import injury_adjustment
    if not rows:
        return 0.0
    return 1.0 - injury_adjustment(home_injuries=[SimpleNamespace(player_position=e["position"],
                                                                  player_name=e["name"]) for e in rows]
                                   ).home_xg_multiplier


def read_world(s, season: str, now: datetime) -> dict:
    from sqlalchemy import select

    from src.db.schema import Competition, CompetitionTeam, Injury, Match, Sport, Team
    check_schema(s)
    comps = list(s.execute(select(Competition).where(Competition.code == COMPETITION,
                                                     Competition.sport == Sport.SOCCER)).scalars())
    if len(comps) != 1:
        raise Refused(f"REFUSED: {len(comps)} soccer competition(s) with code {COMPETITION} in the database (law 1)")
    pl = comps[0]
    codes = dict(s.execute(select(Competition.id, Competition.code)).all())
    team_ids = sorted({tid for (tid,) in s.execute(select(CompetitionTeam.team_id).where(
        CompetitionTeam.competition_id == pl.id, CompetitionTeam.season == season))})
    if not team_ids:
        raise Refused(f"REFUSED: no team in competition_teams for {COMPETITION} {season!r} (law 1: the season string "
                      "is what the DB stores)")
    names = {t.id: t.name for t in s.execute(select(Team)).scalars()}
    matches, by_fid, by_prev = {}, defaultdict(list), defaultdict(list)
    for m in s.execute(select(Match).where(Match.sport == Sport.SOCCER)).scalars():
        ext = m.external_ids if isinstance(m.external_ids, dict) else {}
        rec = {"id": m.id, "utc": redated.as_utc(m.utc_date), "code": codes.get(m.competition_id),
               "comp_id": m.competition_id, "home": m.home_team_id, "away": m.away_team_id,
               "status": getattr(m.status, "value", m.status), "score": (m.home_score, m.away_score),
               "fixture": str(ext[SOURCE]) if ext.get(SOURCE) is not None else None}
        matches[m.id] = rec
        if rec["fixture"] is not None:
            by_fid[rec["fixture"]].append(rec)
        prev = ext.get(f"{SOURCE}_prev")
        for old in prev if isinstance(prev, list) else []:
            by_prev[str(old)].append(rec)
    teams = []
    for tid in team_ids:
        ahead = sorted((m for m in matches.values() if m["comp_id"] == pl.id and tid in (m["home"], m["away"])
                        and m["utc"] is not None and m["utc"] >= now), key=lambda m: (m["utc"], m["id"]))
        pls = [m for m in ahead if m["status"] in NEXT_STATUSES]
        passed = [m for m in ahead if m["status"] not in NEXT_STATUSES and (not pls or m["utc"] <= pls[0]["utc"])]
        stored = [{"id": i.id, "name": i.player_name, "position": i.player_position, "reason": i.reason,
                   "type": i.type, "fixture": i.fixture_source_id, "refreshed_at": i.refreshed_at}
                  for i in s.execute(select(Injury).where(Injury.team_id == tid).order_by(Injury.id)).scalars()]
        teams.append({"id": tid, "name": names.get(tid), "next": pls[0] if pls else None, "passed": passed,
                      "stored": stored})
    return {"pl": pl.id, "teams": teams, "matches": matches, "by_fid": by_fid, "by_prev": by_prev, "names": names}


def bucket(e: dict, team: dict, w: dict, now: datetime) -> tuple[str, dict | None, str]:
    """(bucket, the named match or None, the label's tail)."""
    fid = e["fixture"]
    if fid is None or not str(fid).strip():
        return NO_FIX_ID, None, ""
    fid = str(fid).strip()
    hits, prev = w["by_fid"].get(fid, []), ""
    if not hits and w["by_prev"].get(fid):
        hits, prev = w["by_prev"][fid], " (a previous provider id of the match)"
    if not hits:
        return NOT_STORED, None, f" (provider fixture {fid})"
    if len(hits) > 1:
        return FIX_AMBIG, None, f" (provider fixture {fid}: matches {', '.join(str(h['id']) for h in hits)})"
    m = hits[0]
    st = "" if m["status"] in NEXT_STATUSES + ("finished",) else f", status {m['status']}"
    tail = f" ({m['code'] or 'competition ?'} match {m['id']} {_fmt(m['utc'])}, {_days(m['utc'], now)}{st}{prev})"
    if team["id"] not in (m["home"], m["away"]):
        return NOT_TEAMS, m, tail[:-1] + f"; provider fixture {fid})"
    if m["utc"] is None:
        return NOT_STORED, m, f" (provider fixture {fid}: match {m['id']} has no readable kickoff)"
    nxt = team["next"]
    if nxt is not None and m["id"] == nxt["id"]:
        return NEXT, m, tail
    if m["utc"] < now:
        return PAST, m, tail
    if nxt is None:
        return NO_NEXT, m, tail
    if m["utc"] < nxt["utc"]:
        return BEFORE_NEXT, m, tail
    return LATER, m, tail


def rule_of(e: dict) -> str:
    if e["type"] != MISSING:
        return "no"
    if e["bucket"] in RULE_BUCKETS:
        return "yes"
    if e["bucket"] in UNDECIDABLE_BUCKETS:
        return "undecidable"
    return "no"


def build_exposure(w: dict, now: datetime) -> dict:
    for t in w["teams"]:
        for e in t["stored"]:
            e["bucket"], e["match"], e["tail"] = bucket(e, t, w, now)
            e["rule"] = rule_of(e)
        rule = [e for e in t["stored"] if e["rule"] == "yes"]
        und = [e for e in t["stored"] if e["rule"] == "undecidable"]
        t["model_n"], t["model_r"] = len(t["stored"]), reduction(t["stored"])
        t["rule_n"], t["rule_r"] = len(rule), reduction(rule)
        t["und_n"], t["und_r"] = len(und), reduction(rule + und)
    return w


def team_lines(t: dict, w: dict, now: datetime) -> list[str]:
    nxt = t["next"]
    if nxt:
        opp = nxt["away"] if nxt["home"] == t["id"] else nxt["home"]
        ha = "home" if nxt["home"] == t["id"] else "away"
        nx = (f"match {nxt['id']} {ha} v {w['names'].get(opp)} {_fmt(nxt['utc'])} ({_days(nxt['utc'], now)}, "
              f"status {nxt['status']})")
    else:
        nx = "none stored (no PL match with kickoff >= now and status scheduled or live)"
    if t["passed"]:
        nx += (" · passed over (status not scheduled or live): " + "; ".join(
            f"match {m['id']} {_fmt(m['utc'])} status {m['status']}" for m in t["passed"]))
    stamps = sorted({redated.as_utc(e["refreshed_at"]) for e in t["stored"]}, key=lambda d: (d is None, d))
    L = [f"\n== {t['name']} (team {t['id']}) · stored {len(t['stored'])} · refreshed_at "
         + (", ".join(f"{d:%Y-%m-%dT%H:%M:%S}" if d else "none" for d in stamps) or "none")
         + f" · next PL match: {nx}"]
    if not t["stored"]:
        L.append("  no stored row for the team: MODEL 0 (0.0%) · RULE 0 (0.0%)")
        return L
    L.append(f"  MODEL {t['model_n']} (reduction {_pct(t['model_r'])}) · RULE {t['rule_n']} (reduction "
             f"{_pct(t['rule_r'])})" + (f" +{t['und_n']} undecidable (at most {t['rule_n'] + t['und_n']}, reduction "
                                        f"{_pct(t['und_r'])})" if t["und_n"] else " · undecidable 0"))
    grid = defaultdict(Counter)
    for e in t["stored"]:
        grid[e["type"] if e["type"] is not None else NO_TYPE][e["bucket"]] += 1
    L.append("  type x bucket: " + " | ".join(
        f"{typ!r}: " + " · ".join(f"{b} {grid[typ][b]}" for b in BUCKETS if grid[typ][b])
        for typ in sorted(grid, key=str)))
    for e in t["stored"]:
        typ = repr(e["type"]) if e["type"] is not None else NO_TYPE
        L.append(f"    {e['name']} · position {e['position'] if e['position'] else '(none)'} · type {typ} · reason "
                 f"{e['reason']!r} · {e['bucket']}{e['tail']} · model yes · rule {e['rule']}")
    return L


def saturday_lines(w: dict, day: str, exports: Path) -> tuple[list[str], dict]:
    L = [f"\nTHE SATURDAY GAMES ({day}, UTC; for the laptop block's cross-check). Every PL match stored on the date "
         "(law 1, names first):"]
    on = sorted((m for m in w["matches"].values() if m["comp_id"] == w["pl"] and m["utc"] is not None
                 and f"{m['utc']:%Y-%m-%d}" == day), key=lambda m: (m["utc"], m["id"]))
    for m in on:
        L.append(f"  match {m['id']} {w['names'].get(m['home'])} v {w['names'].get(m['away'])} {_fmt(m['utc'])} "
                 f"status {m['status']} score {m['score'][0]}-{m['score'][1]} · api_football fixture {m['fixture']}")
    if not on:
        L.append("  none")
    cr = None
    if not exports.is_dir():
        L.append(f"  closing files: the exports directory {exports} is missing on this checkout: no closing row read")
    else:
        cr = redated.closing_rows(exports)
        L.append(f"  closing files: {cr['files']} read from {exports}/{redated.CLOSING_GLOB}"
                 + (f" · unreadable {', '.join(cr['unreadable'])}" if cr["unreadable"] else ""))
    stored = {t["id"]: t for t in w["teams"]}
    out = {}
    for key, label, a, b in GAMES:
        hits = [m for m in on if pair_matches(a, b, w["names"].get(m["home"]), w["names"].get(m["away"]))]
        if not hits:
            L.append(f"  {label} ({key}): not found among the PL matches on {day}")
            out[key] = "not found"
            continue
        if len(hits) > 1:
            L.append(f"  {label} ({key}): AMBIGUOUS, {len(hits)} candidates: "
                     + "; ".join(f"match {m['id']} {w['names'].get(m['home'])} v {w['names'].get(m['away'])}"
                                 for m in hits))
            out[key] = "AMBIGUOUS"
            continue
        m = hits[0]
        hn, an = w["names"].get(m["home"]), w["names"].get(m["away"])
        L.append(f"  {label} ({key}): match {m['id']} home {hn} v away {an} {_fmt(m['utc'])} status {m['status']} "
                 f"score {m['score'][0]}-{m['score'][1]} · api_football fixture {m['fixture']}")
        out[key] = {"match": m["id"], "fixture": m["fixture"], "sides": {}}
        if cr is None:
            continue
        runs = [x for x in cr["rows"].get(m["id"], []) if x[1] == FAMILY and x[2].get("competition") == COMPETITION]
        if not runs:
            L.append(f"    no closing row for match {m['id']} in {exports}")
            continue
        run, _fam, r = runs[-1]
        L.append(f"    closing row: run {_fmt(run) if run else 'no run start'} (latest of {len(runs)}) · row "
                 f"{r.get('home_team')} v {r.get('away_team')} · kickoff {r.get('utc_date')}")
        if (r.get("home_team"), r.get("away_team")) != (hn, an):
            L.append("    the row's teams are not the stored match's: the row is not used (ids are machine-local)")
            continue
        inj = _d(r.get("injuries"))
        for side, tid in (("home", m["home"]), ("away", m["away"])):
            cnt = _int(inj.get(f"{side}_count"))
            names = inj.get(f"{side}_names")
            synced = _d(_d(_d(r.get("input_quality")).get("injuries")).get(side)).get("synced_at")
            t = stored.get(tid)
            rows = t["stored"] if t else None
            L.append(f"    {side.upper()} {r.get(f'{side}_team')}: injuries.{side}_count "
                     f"{cnt if cnt is not None else 'UNKNOWN'} · {side}_names {names} · synced_at {synced}")
            verdict = consumed(rows, cnt, synced)
            L.append(f"      {verdict}")
            out[key]["sides"][side] = verdict
    return L, out


def consumed(rows: list | None, cnt: int | None, synced) -> str:
    """#688's ruling 1(b) test: one stored refreshed_at equal to synced_at, and the counts equal."""
    if rows is None:
        return "the team is not in this season's PL teams: no stored list read"
    if cnt == 0 and not rows:
        return "empty as consumed (count 0) and no stored row now: nothing to compare"
    stamps = sorted({redated.as_utc(e["refreshed_at"]) for e in rows}, key=lambda d: (d is None, d))
    y = redated.as_utc(synced)
    x = (", ".join(f"{d:%Y-%m-%dT%H:%M:%S.%f}" if d else "none" for d in stamps) or "no stored row")
    if cnt is not None and len(stamps) == 1 and y is not None and stamps[0] == y and len(rows) == cnt:
        return "the stored list is the one the closing row consumed (the per-entry types above ARE Saturday's)"
    return (f"the stored list is a later (or different) sync: refreshed_at {x} vs consumed "
            f"{f'{y:%Y-%m-%dT%H:%M:%S.%f}' if y else 'none'}; count {len(rows)} vs "
            f"{cnt if cnt is not None else 'UNKNOWN'}")


def run_exposure(a, echo) -> int:
    now = a.now or datetime.now(timezone.utc).replace(tzinfo=None)
    exports = Path(a.exports).expanduser() if a.exports else ROOT / "exports"
    with open_db(a.db) as (s, label):
        w = build_exposure(read_world(s, a.season, now), now)
        sat, sat_out = saturday_lines(w, a.date, exports)
    teams = w["teams"]
    L = [f"PL INJURY EXPOSURE RECEIPT (ARCHITECT 2026-11-01, addendum 196 item 2(a); #754) · READ-ONLY · {TAG} · "
         f"checkout {checkout_describe()} · now {now:%Y-%m-%dT%H:%M:%S}Z · database {label} · {COMPETITION} "
         f"{a.season}: {len(teams)} team(s)",
         MODEL_COUNTS, RULE_TEXT, BUCKETS_TEXT, NOTHING_CHANGED, SIDECARS]
    allrows = [e for t in teams for e in t["stored"]]
    types = Counter(e["type"] if e["type"] is not None else NO_TYPE for e in allrows)
    bks = Counter(e["bucket"] for e in allrows)
    L.append("CENSUS (every stored row of the PL teams; types verbatim): "
             + (" · ".join(f"{k!r} {types[k]}" for k in sorted(types, key=str)) or "no stored row")
             + " || buckets: " + (" · ".join(f"{b} {bks[b]}" for b in BUCKETS if bks[b]) or "none"))
    for t in teams:
        L += team_lines(t, w, now)
    model_cap = [t["name"] for t in teams if t["model_r"] >= CAP - 1e-9]
    rule_cap = [t["name"] for t in teams if t["rule_r"] >= CAP - 1e-9]
    L.append(f"\nTOTALS: teams {len(teams)} · entries {len(allrows)} · model count {sum(t['model_n'] for t in teams)} "
             f"· rule count {sum(t['rule_n'] for t in teams)} · undecidable {sum(t['und_n'] for t in teams)}")
    L.append(f"  at the 25% cap under the model {len(model_cap)}: {', '.join(map(str, model_cap)) or 'none'} · under "
             f"the rule {len(rule_cap)}: {', '.join(map(str, rule_cap)) or 'none'}")
    L.append("  reduction difference per team (model - rule), largest first:")
    for t in sorted(teams, key=lambda t: (-(t["model_r"] - t["rule_r"]), str(t["name"]))):
        L.append(f"    {t['name']}: {(t['model_r'] - t['rule_r']) * 100:+.1f} pp (model {_pct(t['model_r'])} "
                 f"[{t['model_n']}] · rule {_pct(t['rule_r'])} [{t['rule_n']}]"
                 + (f" · +{t['und_n']} undecidable, at most {_pct(t['und_r'])}" if t["und_n"] else "") + ")")
    L += sat
    summary = {"now": f"{now:%Y-%m-%dT%H:%M:%S}", "season": a.season, "teams": len(teams), "entries": len(allrows),
               "model": sum(t["model_n"] for t in teams), "rule": sum(t["rule_n"] for t in teams),
               "undecidable": sum(t["und_n"] for t in teams), "types": dict(types), "buckets": dict(bks),
               "at_cap_model": len(model_cap), "at_cap_rule": len(rule_cap),
               "per_team": {str(t["name"]): {"model": t["model_n"], "model_reduction": round(t["model_r"], 4),
                                             "rule": t["rule_n"], "rule_reduction": round(t["rule_r"], 4),
                                             "undecidable": t["und_n"]} for t in teams},
               "saturday": sat_out}
    L.append(TAG + " " + json.dumps(summary, sort_keys=True, default=str))
    for ln in L:
        echo(ln)
    return 0


# =====================================================================================================================
# PART (b): lineups
# =====================================================================================================================

class Fetch:
    """The provider read through lineup_history_probe's get, with the payload cache and the call cap (#688's)."""

    def __init__(self, save: Path, max_calls: int, get):
        self.save, self.max_calls, self.calls, self.cached = save, max_calls, 0, 0
        self.get = get
        self.failed: list[str] = []
        self.empty: list[str] = []

    def cached_answer(self, kind: str, fx) -> list | None:
        f = self.save / str(fx) / f"{kind}.json"
        if not f.is_file():
            return None
        try:
            rows = json.loads(f.read_text())
        except (OSError, ValueError):
            return None
        return rows if isinstance(rows, list) and rows else None   # a torn, empty or not-a-list file is asked again

    def __call__(self, kind: str, fx, path: str, **params) -> list | None:
        """The answer's rows; [] for an answer with no rows; None for a FAILED read. Raises Capped at the cap."""
        rows = self.cached_answer(kind, fx)
        if rows is not None:
            self.cached += 1
            return rows
        if self.calls >= self.max_calls:
            raise Capped(f"{kind} {fx}")
        self.calls += 1
        try:
            code, errs, rows = self.get(path, **params)
        except Exception as e:                         # lineup_history_probe.get raises on a JSON body not an object
            self.failed.append(f"fixture {fx} {kind}: the provider body was not readable ({type(e).__name__}: "
                               f"{str(e)[:80]})")
            return None
        if errs or code != 200:
            self.failed.append(f"fixture {fx} {kind}: HTTP {code}" + (f" errors {errs}" if errs else ""))
            return None
        if not isinstance(rows, list):
            self.failed.append(f"fixture {fx} {kind}: the response is a {type(rows).__name__}, not a list")
            return None
        if not rows:
            self.empty.append(f"fixture {fx} {kind}")
            return []
        f = self.save / str(fx) / f"{kind}.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows, sort_keys=True, default=str))
        tmp.replace(f)
        return rows


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _probe_get():
    """lineup_history_probe's get and its key (the lineup_history_probe pattern)."""
    mod = _load("lineup_history_probe")
    return mod.get, mod.KEY


def _name_match():
    """#688's name_match (scripts/pl_injury_classification_receipt.py), the one name rule."""
    return _load("pl_injury_classification_receipt").name_match


def _fixture_arg(v: str) -> tuple[str, str]:
    k, sep, i = v.partition("=")
    k, i = k.strip(), i.strip()
    if not sep or k not in GAME_KEYS or not i:
        raise argparse.ArgumentTypeError(f"--fixture takes KEY=ID with KEY one of {', '.join(GAME_KEYS)}: {v!r}")
    return k, i


def closing_games(exports: Path, day: str) -> tuple[dict, dict]:
    cr = redated.closing_rows(exports)
    out = {}
    for key, label, a, b in GAMES:
        found = {}
        for mid, runs in cr["rows"].items():
            keep = [x for x in runs if x[1] == FAMILY and x[2].get("competition") == COMPETITION
                    and (redated.as_utc(x[2].get("utc_date")) or datetime.min).strftime("%Y-%m-%d") == day
                    and pair_matches(a, b, x[2].get("home_team"), x[2].get("away_team"))]
            if keep:
                found[mid] = (keep[-1], len(keep))
        out[key] = found
    return out, cr


def db_lookup(s, row: dict, day: str) -> dict:
    """The laptop DB's match (by the row's exact team names and --date) and both sides' provider team ids."""
    from sqlalchemy import select

    from src.db.schema import Match, Sport, Team
    from src.ingestion.team_merge import source_ids
    res = {"fixture": None, "fixture_why": None, "ids": {}, "ids_why": {}, "team_ids": {}}
    for side in ("home", "away"):
        ts = list(s.execute(select(Team).where(Team.sport == Sport.SOCCER,
                                               Team.name == row.get(f"{side}_team"))).scalars())
        if len(ts) != 1:
            res["ids_why"][side] = (f"{len(ts)} soccer teams named {row.get(f'{side}_team')!r} in the laptop DB"
                                    if ts else f"no soccer team named {row.get(f'{side}_team')!r} in the laptop DB")
            res["ids"][side] = set()
            continue
        t = ts[0]
        ext = t.external_ids if isinstance(t.external_ids, dict) else {}
        prev = ext.get(f"{SOURCE}_prev")
        ids = source_ids(ext, SOURCE) | {str(x) for x in (prev if isinstance(prev, list) else [])}
        res["ids"][side], res["team_ids"][side] = ids, t.id
        if not ids:
            res["ids_why"][side] = f"team {t.id} {t.name!r} stores no {SOURCE} id"
    if len(res["team_ids"]) == 2:
        cands = [m for m in s.execute(select(Match).where(Match.sport == Sport.SOCCER,
                                                          Match.home_team_id == res["team_ids"]["home"],
                                                          Match.away_team_id == res["team_ids"]["away"])).scalars()
                 if redated.as_utc(m.utc_date) and f"{redated.as_utc(m.utc_date):%Y-%m-%d}" == day]
        if len(cands) == 1:
            ext = cands[0].external_ids if isinstance(cands[0].external_ids, dict) else {}
            if ext.get(SOURCE) is not None:
                res["fixture"] = str(ext[SOURCE])
                res["fixture_why"] = f"the laptop DB (match {cands[0].id}, external_ids[{SOURCE!r}])"
            else:
                res["fixture_why"] = f"the laptop DB's match {cands[0].id} stores no {SOURCE} id"
        else:
            res["fixture_why"] = (f"{len(cands)} laptop DB matches {row.get('home_team')} v {row.get('away_team')} on "
                                  f"{day}" if cands else
                                  f"no laptop DB match {row.get('home_team')} v {row.get('away_team')} on {day}")
    else:
        res["fixture_why"] = "the teams are not both in the laptop DB by exact name"
    return res


def keys_lines(rows: list) -> list[str]:
    """Law 1: the keys of the first real answer, printed before any field of it is read."""
    first = next((b for b in rows if isinstance(b, dict)), None)
    if first is None:
        return ["  the first answer holds no object row; no key to print"]
    xi = first.get("startXI")
    slot = xi[0] if isinstance(xi, list) and xi else None
    return [f"  response[0] keys {sorted(first)}",
            f"  startXI[0] keys {sorted(_d(slot))}",
            f"  startXI[0][\"player\"] keys {sorted(_d(_d(slot).get('player')))}"]


def read_sides(ans: list, ids: dict, label: str, malformed: list) -> tuple[dict, list]:
    """{side: {"read": bool, "full": bool, "xi": [names], "bench": [names], "cands": [...]}} by provider team id."""
    out = {s: {"blocks": 0, "full": True, "xi": [], "bench": [], "cands": []} for s in ("home", "away")}
    seen = []
    for i, b in enumerate(ans):
        if not isinstance(b, dict):
            malformed.append(f"{label} row {i}: not an object")
            continue
        team = _d(b.get("team"))
        tid = team.get("id")
        seen.append(f"{team.get('name')} (team id {tid})")
        side = next((sd for sd in ("home", "away") if tid is not None and str(tid) in ids.get(sd, set())), None)
        if side is None:
            continue
        o = out[side]
        o["blocks"] += 1
        if o["blocks"] > 1:
            malformed.append(f"{label} {side}: a second block for the side (team id {tid})")
            o["full"] = False
        for key, role in (("startXI", "xi"), ("substitutes", "bench")):
            slots = b.get(key)
            if not isinstance(slots, list):
                malformed.append(f"{label} {side} {key}: " + ("missing" if slots is None else "not a list"))
                o["full"] = False
                continue
            named = 0
            for j, sl in enumerate(slots):
                p = sl.get("player") if isinstance(sl, dict) else None
                nm = p.get("name") if isinstance(p, dict) else None
                if not (isinstance(nm, str) and nm.strip()):
                    malformed.append(f"{label} {side} {key}[{j}]: not a slot with a named player")
                    o["full"] = False
                    continue
                named += 1
                o[role].append(nm.strip())
                o["cands"].append({"names": [nm.strip()], "slot": role, "id": p.get("id")})
            # law 4: an XI that is not eleven named starters, or an empty bench, is a side not listed in full (a
            # lineup the provider did not post, or posted in part): a name not found there is unread, never absent
            if role == "xi" and named != XI_SIZE:
                malformed.append(f"{label} {side} startXI: {named} named starter(s), not {XI_SIZE}")
                o["full"] = False
            if role == "bench" and not slots:
                malformed.append(f"{label} {side} substitutes: empty")
                o["full"] = False
    return out, seen


def classify(name: str, sd: dict | None, why: str | None, name_match) -> tuple[str, str]:
    if sd is None or not sd["blocks"]:
        return UNREAD, why or "no answer read for the side"
    how, cs = name_match(name, sd["cands"])
    if how == "ambiguous":
        return AMBIG, "AMBIGUOUS: " + " | ".join(f"{c['names'][0]} ({c['slot']})" for c in cs)
    if how == "unmatched":
        if sd["full"]:
            return ABSENT, ABSENT_TEXT[len(ABSENT) + 2:-1]
        return UNREAD, ("not found, and the side is not listed in full (a member missing or not the provider's shape, "
                        f"an XI not {XI_SIZE} named starters, or an empty bench): it may hide him")
    c = cs[0]
    return (STARTED if c["slot"] == "xi" else BENCH), f"{c['names'][0]} ({how}; provider id {c.get('id')})"


def run_lineups(a, echo, get) -> int:
    if a.max_calls > MAX_CALLS or a.max_calls < 0:
        raise Refused(f"REFUSED: --max-calls {a.max_calls}: the ruled budget is one call per game, {MAX_CALLS} at most")
    save = Path(a.save).expanduser().resolve() if a.save else (ROOT / "logs" / f"pl_injury_lineups_{a.date}").resolve()
    if _under_data(save):
        raise Refused(f"REFUSED: --save {save} is under data/ (law 5): the payloads never live there")
    exports = Path(a.exports).expanduser() if a.exports else ROOT / "exports" / "host"
    overrides = dict(a.fixture or [])
    found, cr = closing_games(exports, a.date)
    games = []
    with open_db(a.db) as (s, label):
        check_schema(s, {k: READS[k] for k in ("matches", "teams")})
        for key, glabel, _a, _b in GAMES:
            g = {"key": key, "label": glabel, "row": None, "fixture": None}
            hits = found[key]
            if not hits:
                g["skip"] = f"no closing row in {exports}"
            elif len(hits) > 1:
                g["skip"] = ("AMBIGUOUS: " + "; ".join(f"match {mid} {x[0][2].get('home_team')} v "
                                                       f"{x[0][2].get('away_team')}" for mid, x in sorted(hits.items())))
            else:
                mid, ((run, _f, r), nruns) = next(iter(hits.items()))
                g.update({"match": mid, "run": run, "runs": nruns, "row": r})
                look = db_lookup(s, r, a.date)
                g["ids"], g["ids_why"] = look["ids"], look["ids_why"]
                if key in overrides:
                    g["fixture"], g["fixture_src"] = overrides[key], "--fixture"
                elif look["fixture"]:
                    g["fixture"], g["fixture_src"] = look["fixture"], look["fixture_why"]
                else:
                    g["skip_call"] = (f"fixture id unread: re-run with --fixture {key}=ID (the host block prints it); "
                                      f"{look['fixture_why']}")
            games.append(g)
    fetch = None
    need = [g for g in games if g.get("fixture")]
    if get is None and any(Fetch(save, 0, None).cached_answer("lineups", g["fixture"]) is None for g in need):
        get, key = _probe_get()
        if not key:
            raise Refused("REFUSED: no API_FOOTBALL_KEY (environment or .env)")
    fetch = Fetch(save, a.max_calls, get)
    name_match = _name_match()
    keys, malformed, capped = [], [], []
    for g in games:
        if not g.get("fixture"):
            continue
        fid = g["fixture"]
        try:
            ans = fetch("lineups", fid, "fixtures/lineups", fixture=fid)
        except Capped:
            capped.append(f"{g['label']} (fixture {fid})")
            g["why"] = "capped (the call cap stopped the read)"
            continue
        if ans is None:
            g["why"] = "the read FAILED"
            continue
        if not ans:
            g["why"] = "answered with no rows"
            continue
        if not keys:
            keys = [f"  first real answer: fixture {fid} ({g['label']})"] + keys_lines(ans)
        g["sides"], g["seen"] = read_sides(ans, g["ids"], f"{g['label']} (fixture {fid})", malformed)
    total, hidden_total, hidden_unknown = Counter(), 0, 0
    body = []
    for g in games:
        body.append(f"\n== {g['label']} ({g['key']})")
        if g.get("skip"):
            body.append(f"  {g['skip']}: no call")
            continue
        r = g["row"]
        body.append(f"  closing row: match {g['match']} (host id) {r.get('home_team')} v {r.get('away_team')} · "
                    f"kickoff {r.get('utc_date')} · run {_fmt(g['run']) if g['run'] else 'no run start'} (latest of "
                    f"{g['runs']})")
        if g.get("skip_call"):
            body.append(f"  {g['skip_call']}: no call")
        else:
            body.append(f"  provider fixture {g['fixture']} (from {g['fixture_src']}) · read: "
                        + ("read" if g.get("sides") else g.get("why", "not read")))
        if g.get("seen") is not None:
            body.append(f"  the answer's teams: {', '.join(g['seen']) or 'none'}")
        fb = _d(_d(r.get("prediction")).get("factor_breakdown"))
        if "factor_notes" in fb:
            body.append(f"  factor_notes (prediction.factor_breakdown.factor_notes, verbatim): {fb['factor_notes']!r}")
        else:
            body.append("  factor_notes: the row carries no prediction.factor_breakdown.factor_notes")
        gc, g_hidden, g_unknown = Counter(), 0, 0
        inj = _d(r.get("injuries"))
        for side in ("home", "away"):
            raw = inj.get(f"{side}_names")
            raw = raw if isinstance(raw, list) else []
            names = [n.strip() for n in raw if isinstance(n, str) and n.strip()]
            for j, n in enumerate(raw):
                if not (isinstance(n, str) and n.strip()):
                    malformed.append(f"{g['label']} closing row injuries.{side}_names[{j}]: {n!r} is not a name "
                                     "(never classed)")
            cnt = _int(inj.get(f"{side}_count"))
            ids = (g.get("ids") or {}).get(side) or set()
            sd = (g.get("sides") or {}).get(side)
            why = g.get("why") or g.get("skip_call")
            if not ids:
                why = f"no provider team id ({(g.get('ids_why') or {}).get(side, 'not looked up')})"
            elif g.get("sides") is not None and (sd is None or not sd["blocks"]):
                why = f"the answer holds no block for the side's provider ids {sorted(ids)}"
            synced = _d(_d(_d(r.get("input_quality")).get("injuries")).get(side)).get("synced_at")
            body.append(f"  {side.upper()} {r.get(f'{side}_team')} (provider ids {sorted(ids) or 'none'}) · "
                        f"injuries.{side}_count {cnt if cnt is not None else 'UNKNOWN'} · synced_at {synced}")
            if cnt is None:
                body.append(f"    count UNKNOWN: entries the export does not name cannot be counted "
                            f"({len(names)} name(s) kept)")
                g_unknown += 1
            elif cnt > len(names):
                body.append(f"    {cnt - len(names)} entries the export does not name (count {cnt}, "
                            f"{ROW_NAMES_KEPT} names kept)")
                g_hidden += cnt - len(names)
            if sd is not None and sd["blocks"] and ids:
                body.append(f"    XI ({len(sd['xi'])}): {', '.join(sd['xi']) or 'none'}")
                body.append(f"    bench ({len(sd['bench'])}): {', '.join(sd['bench']) or 'none'}"
                            + ("" if sd["full"] else " · NOT READ IN FULL (a member missing or not the provider's "
                                                     f"shape, an XI not {XI_SIZE} named starters, or an empty bench)"))
            for n in names:
                cls, det = classify(n, sd if ids else None, why, name_match)
                body.append(f"    {n}: {cls} — {det}")
                gc[cls] += 1
        hid = f"entries the export does not name {g_hidden}" + (f" · sides with count UNKNOWN {g_unknown}"
                                                                 if g_unknown else "")
        body.append("  game totals: " + (" · ".join(f"{c} {gc[c]}" for c in CLASSES if gc[c]) or "no listed name")
                    + f" · {hid}")
        g["totals"], g["hidden"], g["hid_text"] = dict(gc), {"hidden": g_hidden, "count_unknown_sides": g_unknown}, hid
        total.update(gc)
        hidden_total += g_hidden
        hidden_unknown += g_unknown
    L = [f"PL INJURY LINEUPS RECEIPT (ARCHITECT 2026-11-01, addendum 196 item 2(b); #754) · READ-ONLY · {TAG_LINEUPS} · "
         f"checkout {checkout_describe()} · date {a.date} · closing files {exports}/{redated.CLOSING_GLOB} "
         f"({cr['files']} read; runs " + (f"first {_fmt(cr['runs'][0])}, last {_fmt(cr['runs'][1])}" if cr["runs"]
                                           else "none") + ") · laptop "
         f"database {label}",
         f"PROVIDER: calls made {fetch.calls} · cached answers {fetch.cached} · failed {len(fetch.failed)} · empty "
         f"{len(fetch.empty)} · call cap {fetch.max_calls} (ruled: one call per game) · payloads {save}"
         + (f" · INCOMPLETE: the cap stopped {len(capped)} read(s); a re-run resumes from the kept payloads"
            if capped else ""),
         "CLASSES: started (in startXI) · bench (in substitutes) · AMBIGUOUS (two or more candidates, printed) · "
         f"{ABSENT_TEXT}, only when the side's answer was read in full · unread (no read, a failed or capped read, no "
         "provider team id, or a not-found name on a side not read in full). Names by #688's name_match; sides by "
         "provider team id, never by name.",
         NOTHING_CHANGED, SIDECARS]
    if cr["unreadable"]:
        L.append(f"unreadable closing files {len(cr['unreadable'])}: {', '.join(cr['unreadable'])}")
    L.append("PROVIDER KEYS (law 1, printed from the first real answer before any field is read):")
    L += keys or ["  no answer read: no key printed, no field read"]
    L += body
    L.append("\nTOTALS: " + (" · ".join(f"{c} {total[c]}" for c in CLASSES if total[c]) or "no listed name")
             + f" · entries the exports do not name {hidden_total}"
             + (f" · sides with count UNKNOWN {hidden_unknown}" if hidden_unknown else ""))
    for g in games:
        if g.get("totals") is None:
            L.append(f"  {g['label']}: {g.get('skip') or 'no listed name'}")
            continue
        L.append(f"  {g['label']}: " + (" · ".join(f"{c} {g['totals'][c]}" for c in CLASSES if g["totals"].get(c))
                                         or "no listed name") + f" · {g['hid_text']}")
    if malformed:
        L.append(f"NOT THE PROVIDER'S SHAPE {len(malformed)} (counted, never read): " + "; ".join(malformed[:10])
                 + (" …" if len(malformed) > 10 else ""))
    for f in fetch.failed:
        L.append(f"  FAILED {f}")
    for f in fetch.empty:
        L.append(f"  NO ROWS {f}")
    if capped:
        L.append(f"INCOMPLETE: the call cap ({fetch.max_calls}) left {len(capped)} read(s) unread: {', '.join(capped)}")
    summary = {"date": a.date, "classes": dict(total), "hidden": hidden_total, "count_unknown_sides": hidden_unknown,
               "games": {g["key"]: {**g["totals"], **g["hidden"]} if g.get("totals") is not None
                         else (g.get("skip") or "no row") for g in games},
               "calls": {"made": fetch.calls, "cached": fetch.cached, "failed": len(fetch.failed),
                         "empty": len(fetch.empty), "cap": fetch.max_calls},
               "malformed": len(malformed), "incomplete": bool(capped)}
    L.append(TAG_LINEUPS + " " + json.dumps(summary, sort_keys=True, default=str))
    for ln in L:
        echo(ln)
    return 0


def main(argv=None, echo=print, get=None) -> int:
    ap = argparse.ArgumentParser(description="addendum 196 item 2 (#754): the PL injury exposure receipt")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("exposure", help="part (a): the host DB's stored injury rows per PL team (no network)")
    e.add_argument("--db", default=None, help="a .backup copy OUTSIDE data/, opened mode=ro (default: the app's "
                                              "configured database, opened mode=ro)")
    e.add_argument("--season", default=DEFAULT_SEASON)
    e.add_argument("--now", default=None, type=_when, help="UTC (default: the clock now)")
    e.add_argument("--exports", default=None, help="the host's own closing files (default <checkout>/exports)")
    e.add_argument("--date", default=DEFAULT_DATE, type=_day, help="the Saturday (UTC date)")
    li = sub.add_parser("lineups", help="part (b): the provider's lineups for the four Saturday games")
    li.add_argument("--exports", default=None, help="the host's closing files (default <checkout>/exports/host)")
    li.add_argument("--db", default=None, help="the laptop DB, opened mode=ro (a copy OUTSIDE data/, or the "
                                               "configured file)")
    li.add_argument("--date", default=DEFAULT_DATE, type=_day)
    li.add_argument("--fixture", action="append", type=_fixture_arg, help="KEY=ID, KEY one of " + ", ".join(GAME_KEYS))
    li.add_argument("--save", default=None, help="the payload cache (default <checkout>/logs/pl_injury_lineups_<date>; "
                                                 "never under data/)")
    li.add_argument("--max-calls", type=int, default=MAX_CALLS)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "exposure":
            return run_exposure(a, echo)
        return run_lineups(a, echo, get)
    except Refused as ex:
        echo(str(ex))
        return 2


if __name__ == "__main__":
    sys.exit(main())
