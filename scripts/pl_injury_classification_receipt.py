"""
THE PL INJURY CLASSIFICATION RECEIPT (ARCHITECT 2026-10-27 16:10 ET, addendum 171 item 1; #688), READ-ONLY.

THE ISSUE (#688), verbatim: "for every PL closing row since #615's stamping began, join the row's injury list (both
sides, as consumed: names, status, stamp) to the stored post-match lineups and substitutes for that fixture. Per row:
listed-as-missing players who started, who came on, who did not appear; and, where the squad is known, players who did
not appear and were not listed. Aggregate by status label the provider gives and by stamp age. 10-25's four cases
(Isak; João Pedro; Porro and Kulusevski; Calvert-Lewin, Stach, Okafor) are the worked examples. The receipt says what
the count the guard reads actually counts."

THE RULING (ARCHITECT 2026-10-27 16:10 ET, addendum 171 item 1), verbatim:
"1. #688, the PL injury classification receipt.
   (a) The lineups: APPROVED as proposed — a write-nothing provider read of /fixtures/lineups and /fixtures/players for
   the fixtures (the starting eleven, minutes, substitute), payloads kept under logs/ (never data/), on the
   lineup_history_probe pattern, keys printed from a real response before any field is read (law 1). No stored PL
   lineup ingest now: that is a DB write and an R-track question; it goes on the leagues declaration (10-30..11-06) as a
   line, not into this receipt. The call count is printed in the receipt's header.
   (b) The injury lists: read mode=ro from the LAPTOP's database. Since the cutover no PL sync runs on the laptop (the
   standing routine, #708), so the rows each weekend closing consumed are still there and stay there; the host's copy is
   the one Friday's soccer-prematch overwrites. The receipt runs on the laptop, this week, before anything else is asked
   of it. The --db option on a .backup copy OUTSIDE data/ (the ~/sp569 pattern) is approved for the same read; the live
   file is opened mode=ro only. A side is recoverable only on the exact test proposed (stored refreshed_at equals the
   closing row's input_quality.injuries.<side>.synced_at and the counts match); anything else prints "not
   recoverable", and today's list is never substituted.
   (c) The status buckets: the stored `type` printed VERBATIM, with a census line first (every distinct type and its
   count across the fixtures read). No bucket but the exact word: "Missing Fixture" stays "Missing Fixture". Out /
   doubtful / questionable are the NFL feed's words, not this one's, and the receipt says so.
   (d) Stamp age: APPROVED — beside our sync clock (one bucket, ~T-35), the entry's own fixture age from
   fixture_source_id: this fixture / an earlier fixture N days before / not stored.
   (e) What the guard counts: stated in the receipt's header, as scouted (every stored row for the team within 14 days
   of the sync, any type, one per name).
   (f) The four cases span 10-24 and 10-25; a player on no list with no appearance record is "not listed, did not
   appear" only once (a) has read the fixture, else "not listed, appearance unread"."

WHAT IT READS (law 1: every key below was read from the code on 2026-10-27; the provider's keys are printed from the
first real answer of each kind before any field of it is read):
- THE ROWS: <exports>/closing_*.json through src/walters/redated.closing_rows (the one reader; host/ is never read):
  closing family SOCCER, row competition "PL", closing run start (the closing block's start) at or after --since
  (default 2026-10-20T18:42:00, the #629 merge: #615's stamping). One row per match: the last run's, printed with its
  file and git_sha (the file's own key), the earlier runs counted. From the row: match_id, utc_date, home_team,
  away_team, injuries.{home,away}_count and {home,away}_names (the export keeps the first 8 names only),
  input_quality.injuries.{home,away}.{count,synced_at} (the guard's count and our sync clock),
  prediction.factor_breakdown.{home,away}_injuries_count / factor_notes / lineup_kind, desk.call / desk.pick.
- THE DATABASE, mode=ro: the configured file through src.db.database.readonly_scope(), or --db PATH (a .backup copy
  OUTSIDE data/, refused under data/) opened the same way (a mode=ro URI; a missing file is refused, never created).
  matches (id, home_team_id, away_team_id, utc_date, status, home_score, away_score, competition_id, external_ids:
  "api_football" is the provider's fixture id), teams (name, external_ids "api_football", with ids recorded by a merge),
  competitions (code), injuries (id, team_id, player_name, player_position, reason, type, fixture_source_id, source,
  refreshed_at; the unmapped player_source_id is never read: soccer stores none), lineups (kind, team_id, is_starter:
  printed as the stored count, expected 0 for PL). A DB match whose teams are not the row's is never used for it (ids
  are machine-local); the match is then looked up by both team names and the row's kickoff, else "not in the database".
- THE RECOVERABLE TEST (ruling 1(b), exact): a side's stored list is the consumed one only when every stored row of the
  team carries one refreshed_at equal to the row's input_quality.injuries.<side>.synced_at AND the stored count equals
  the row's count. Anything else prints "not recoverable" with why; the row's own names (at most 8) are then the only
  names classified, with type "(not recoverable)", and the hidden count is printed. Today's list is never substituted.
  As a cross-check (never the decider) the row's names are looked up in the stored list.
- THE FIXTURE AGE (ruling 1(d)): each stored entry's fixture_source_id joined to matches.external_ids["api_football"]
  (and "api_football_prev", labelled): this fixture / an earlier fixture N days before / a later fixture / fixture not
  stored / no fixture id stored / an id more than one stored match holds.
- THE APPEARANCES (ruling 1(a)): per fixture a write-nothing provider read of /fixtures/lineups?fixture=<id> (startXI,
  substitutes) and /fixtures/players?fixture=<id> (players[].statistics[0].games.minutes / .substitute), through
  scripts/lineup_history_probe.py's get (throttled, never raises). Sides are told apart by the provider team id against
  the DB team's api_football ids, never by name. Each listed name is classed: started (in startXI; else minutes > 0 and
  substitute false), came on (minutes > 0 and substitute true), did not appear (in the squad answer with no minutes;
  or absent from the side's answers read), appearance unread (a read that failed, had no rows, was capped, or no
  provider fixture id; or a name not found where a member of the side's answer was missing or not the provider's
  shape, which may hide him). AMBIGUOUS and UNMATCHED names are printed as such, never guessed. A minutes value
  neither an int nor null, or a player id neither an int nor a string, is counted as not the provider's shape.
- NAME MATCHING (soccer injuries store no provider player id): a normalized name (casefold, accents stripped, dots,
  hyphens and apostrophes dropped) equal to one candidate's; else the "Initial. Surname" form against a full name (the
  surname tokens equal, each initial the start of the given name in its place), in either direction. Two or more
  candidates: AMBIGUOUS. None: absent from the answer, which may also be a name form the match cannot see.
- NOT LISTED (ruling 1(f)): squad-answer players with no minutes whom no listed name matches: "not listed, did not
  appear" only for a side whose /fixtures/players block was read in full (minutes are in that answer only); a side
  read through /fixtures/lineups alone, or whose players block has a member not the provider's shape, is "not listed,
  appearance unread", with its unlisted names whose minutes were not read. On a side whose list is not recoverable
  and was cut at 8 names (or whose count is missing), listed or not is UNKNOWN: those players are counted apart, never
  in the did-not-appear total. A player outside the matchday answer and on no list cannot be seen (no squad is
  stored or read). A worked case with no closing row in the population is printed as missing.

THE CONSERVATIVE UNKNOWNS (law 4): a failed read (non-200, transport error, API errors) is FAILED, counted and named,
its rows never classified; an answer with no rows is counted apart; a row of an answer that is not an object (or a
member that is not one) is counted and named, never a traceback; --max-calls stops cleanly and the receipt says
INCOMPLETE. A missing count, stamp or type is printed as missing, never 0.

THE PAYLOADS (--save, default logs/pl_injury_payloads; refused under data/): each answer with rows is kept as
<fixture id>/<lineups|players>.json; a re-run reads them and makes no call for them. A failed or empty answer is not
kept, so a re-run asks it again. The header prints: calls made, answers read from the kept payloads, failed, answered
with no rows.

No verdict, no threshold, no model or Desk change. Writes nothing but the kept payloads (and SQLite's own -wal/-shm
sidecars, which a mode=ro open of a WAL file with no live connection creates: the header's SIDECARS line).

Run:  python3 scripts/pl_injury_classification_receipt.py [--exports DIR] [--since 2026-10-20T18:42:00] [--db PATH]
                                                          [--save DIR] [--max-calls N]
Key: API_FOOTBALL_KEY (environment or .env); never printed. Paste the whole output to the architect.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.walters import redated  # noqa: E402   (imports no src.db module)
from deploy.hosting import sp_common  # noqa: E402   (the role setting, as closing.mirror_role reads it)

TAG = "PL-INJURY-CLASSIFICATION-RECEIPT"
SOURCE = "api_football"                       # the adapter's source_name; the external_ids key of matches and teams
FAMILY, COMPETITION = "SOCCER", "PL"
DEFAULT_SINCE = "2026-10-20T18:42:00"         # the #629 merge (fb722251, 2026-10-20 14:42 -0400): #615's stamping
DEFAULT_SAVE = ROOT / "logs" / "pl_injury_payloads"
DEFAULT_MAX_CALLS = 100                       # two calls per fixture; ten rows read so far
ROW_NAMES_KEPT = 8                            # export.py: injuries.<side>_names is "[:8]  # first 8 only"

GUARD_COUNTS = (
    "WHAT THE GUARD COUNTS (ruling 1(e), as scouted): the one-sided guard (desk_policy.one_sided_injuries) reads "
    "input_quality.injuries.<side>.count, which is len() of every injuries row stored for the team when the export "
    "ran (export.py: no filter on type, reason, fixture or stamp). Those rows are the team's season /injuries history "
    "cut to one row per player name (the adapter keeps each name's latest entry), dropped only when that entry's "
    "fixture date is more than 14 days before the sync (service._sync_injuries_for_team; an entry with no date or one "
    "that will not parse is kept). So: every stored row for the team within 14 days of the sync, any type, one per "
    "name, any competition's fixture. It is not a count of players missing this fixture. The model's injury factor "
    "counts the same rows and never reads type.")
SIDECARS = ("SQLITE SIDECARS (a reading, not a write): the app runs the database in WAL mode, and SQLite's own mode=ro "
            "open of a WAL file with no live connection creates <file>-wal and <file>-shm beside it and leaves them "
            "(empty sidecars, no row written). On the live file that is two files under data/; --db on a .backup "
            "copy outside data/ keeps them beside the copy. database.readonly_scope (#706) opens the same way.")
LABELS_NOTE = ("STATUS LABELS (ruling 1(c)): the stored `type` is printed verbatim, the provider's own word; no bucket "
               "but the exact word. Out / doubtful / questionable are the NFL feed's words, not this one's.")

STARTED, CAME_ON = "started", "came on"
DNP_SQUAD = "did not appear (in the squad answer, no minutes)"
DNP_ABSENT = "did not appear (absent from the side's answers read)"
PLAYED = "played (start or came on not read)"
AMBIGUOUS = "AMBIGUOUS name"
UNREAD = "appearance unread"
CLASSES = (STARTED, CAME_ON, PLAYED, DNP_SQUAD, DNP_ABSENT, AMBIGUOUS, UNREAD)
NOT_LISTED_DNP, NOT_LISTED_UNREAD = "not listed, did not appear", "not listed, appearance unread"
NOT_RECOVERABLE = "(not recoverable)"
NO_TYPE = "(no type stored)"
THIS, EARLIER, LATER = "this fixture", "an earlier fixture", "a later fixture"
NOT_STORED, NO_FIX_ID, FIX_AMBIG = "fixture not stored", "no fixture id stored", "fixture id held by 2+ stored matches"
STAMP_BUCKETS = ((1.0, "under 1 h"), (6.0, "1 h to 6 h"), (24.0, "6 h to 24 h"), (None, "24 h or more"))

# THE WORKED CASES (#688; ruling 1(f): "The four cases span 10-24 and 10-25"): keyed by teams and kickoff date, never
# by match id (ids are machine-local).
WORKED = (
    ("1 Isak", "Liverpool", "Brighton", "2026-10-25", "home", "A. Isak"),
    ("2 João Pedro", "Chelsea", "Tottenham", "2026-10-24", "home", "João Pedro"),
    ("3 Porro", "Chelsea", "Tottenham", "2026-10-24", "away", "P. Porro"),
    ("3 Kulusevski", "Chelsea", "Tottenham", "2026-10-24", "away", "D. Kulusevski"),
    ("4 Calvert-Lewin", "Sunderland", "Leeds", "2026-10-25", "away", "D. Calvert-Lewin"),
    ("4 Stach", "Sunderland", "Leeds", "2026-10-25", "away", "A. Stach"),
    ("4 Okafor", "Sunderland", "Leeds", "2026-10-25", "away", "N. Okafor"),
)


class Refused(Exception):
    """A refused read: exit 2, never read as empty."""


class Capped(Exception):
    pass


def _under_data(p: Path) -> bool:
    return (ROOT / "data").resolve() in (p, *p.parents)


# ---- the payload cache (scripts/nfl_qb_coverage.py's Fetch) ---------------------------------------------------------

class Fetch:
    """The provider read through lineup_history_probe's get, with the payload cache and the call cap."""

    def __init__(self, save: Path, max_calls: int, get):
        self.save, self.max_calls, self.calls, self.cached = save, max_calls, 0, 0
        self.get = get
        self.failed: list[str] = []
        self.empty: list[str] = []

    def __call__(self, kind: str, fx, path: str, **params) -> list | None:
        """The answer's rows; [] for an answer with no rows; None for a FAILED read (transport error, non-200, API
        errors). Raises Capped at the call cap."""
        f = self.save / str(fx) / f"{kind}.json"
        if f.is_file():
            try:
                rows = json.loads(f.read_text())
            except (OSError, ValueError):
                rows = None
            if isinstance(rows, list) and rows:
                self.cached += 1
                return rows                            # a torn, empty or not-a-list file is asked again
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
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows, sort_keys=True, default=str))
        tmp.replace(f)
        return rows


def _probe_get():
    """lineup_history_probe's get (the lineup_history_probe pattern, ruling 1(a)) and its key."""
    spec = importlib.util.spec_from_file_location("lineup_history_probe", ROOT / "scripts" / "lineup_history_probe.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.get, mod.KEY


# ---- names ----------------------------------------------------------------------------------------------------------

def tokens(name) -> tuple[str, ...]:
    """A name normalized: accents stripped, casefolded, dots and hyphens to spaces, apostrophes dropped."""
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    s = re.sub(r"['’`]", "", s)
    s = re.sub(r"[.\-]", " ", s)
    return tuple(s.split())


def _initial_form(a: tuple, b: tuple) -> bool:
    """`a` in the "Initial. Surname" form ("a isak", "e j kroupi") naming `b` ("alexander isak")."""
    ini = []
    for t in a:
        if len(t) == 1:
            ini.append(t)
        else:
            break
    sur = a[len(ini):]
    if not ini or not sur or len(b) <= len(sur) or b[-len(sur):] != sur:
        return False
    given = b[:-len(sur)]
    if len(ini) > len(given):          # Codex on #722: "A. X. Smith" never names "Adam Smith" (an initial unmatched)
        return False
    return all(given[i].startswith(c) for i, c in enumerate(ini))


def name_match(name, cands: list[dict]) -> tuple[str, list[dict]]:
    """("exact" | "initial form" | "ambiguous" | "unmatched", the candidates). Never a guess: two or more candidates
    by either rule (an exact name beside another player the initial form names included) is AMBIGUOUS."""
    t = tokens(name)
    if not t:
        return "unmatched", []
    exact = [c for c in cands if any(tokens(n) == t for n in c["names"])]
    form = [c for c in cands if c not in exact and any(_initial_form(t, tokens(n)) or _initial_form(tokens(n), t)
                                                        for n in c["names"])]
    both = exact + form
    if len(both) > 1:
        return "ambiguous", both
    if both:
        return ("exact" if exact else "initial form"), both
    return "unmatched", []


# ---- the rows -------------------------------------------------------------------------------------------------------

def _since(v: str) -> datetime:
    try:
        d = redated.as_utc(v) or datetime.fromisoformat(v)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a date-time (YYYY-MM-DDTHH:MM[:SS]): {v!r}")
    return d


def file_index(exports: Path) -> dict:
    """{(match id, run start): (file name, git_sha)}, the run start computed as redated.closing_rows computes it."""
    out = {}
    for p in sorted(exports.glob(redated.CLOSING_GLOB)) if exports.is_dir() else []:
        try:
            doc = json.loads(p.read_text())
            run = redated.as_utc((doc.get("closing") or {}).get("start"))
            preds = [r for r in doc.get("predictions") or [] if isinstance(r, dict)]
        except (OSError, ValueError, AttributeError, TypeError):
            continue
        stamp = redated._STAMP.search(p.name)
        if run is None and stamp:
            run = datetime.strptime(stamp.group(1), "%Y-%m-%dT%H%M")
        for r in preds:
            out[(r.get("match_id"), run)] = (p.name, doc.get("git_sha"))
    return out


def _d(v) -> dict:
    return v if isinstance(v, dict) else {}


def population(exports: Path, since: datetime) -> dict:
    cr = redated.closing_rows(exports)
    idx = file_index(exports)
    rows, no_run = [], []
    for mid, runs in sorted(cr["rows"].items()):
        keep = [x for x in runs if x[1] == FAMILY and x[2].get("competition") == COMPETITION]
        no_run += [mid for x in keep if x[0] is None]
        keep = [x for x in keep if x[0] is not None and x[0] >= since]
        if not keep:
            continue
        run, _fam, r = keep[-1]
        name, sha = idx.get((mid, run), (None, None))
        rows.append({"match_id": mid, "run": run, "earlier_runs": len(keep) - 1, "file": name, "git_sha": sha,
                     "row": r})
    rows.sort(key=lambda x: (x["run"], x["match_id"]))
    return {"rows": rows, "files": cr["files"], "unreadable": cr["unreadable"], "no_run": sorted(set(no_run))}


def row_side(r: dict, side: str) -> dict:
    iq = _d(_d(r.get("input_quality")).get("injuries")).get(side)
    inj = _d(r.get("injuries"))
    count = _d(iq).get("count")
    names = inj.get(f"{side}_names")
    return {"team": r.get(f"{side}_team"),
            "count": count if isinstance(count, int) and not isinstance(count, bool) else None,
            "count_block": inj.get(f"{side}_count"),
            "names": [str(n) for n in names] if isinstance(names, list) else None,
            "synced_at": _d(iq).get("synced_at")}


# ---- the database (mode=ro) -----------------------------------------------------------------------------------------

@contextmanager
def open_db(db: str | None):
    """(session, label): --db opened through a mode=ro URI (refused under data/, refused when missing), else the app's
    configured file through src.db.database.readonly_scope()."""
    if db:
        path = Path(db).expanduser().resolve()
        if _under_data(path):
            raise Refused(f"REFUSED: --db {path} is under data/ (law 5): the ruled --db is a .backup copy OUTSIDE "
                          "data/; the live file is read without --db")
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
         "teams": {"id", "name", "external_ids"},
         "competitions": {"id", "code"},
         "injuries": {"id", "team_id", "player_name", "player_position", "reason", "type", "fixture_source_id",
                      "source", "refreshed_at"},
         "lineups": {"match_id", "team_id", "kind", "is_starter"}}


def check_schema(s) -> None:
    from sqlalchemy import inspect
    ins = inspect(s.get_bind())
    have = set(ins.get_table_names())
    miss = sorted(t for t in READS if t not in have)
    if miss:
        raise Refused(f"REFUSED: table(s) {', '.join(miss)} not in the database (law 1)")
    for t, cols in READS.items():
        got = {c["name"] for c in ins.get_columns(t)}
        if cols - got:
            raise Refused(f"REFUSED: columns {', '.join(sorted(cols - got))} not in {t} (law 1)")


def _hours(a, b) -> float | None:
    a, b = redated.as_utc(a), redated.as_utc(b)
    return None if a is None or b is None else (a - b).total_seconds() / 3600


def read_db(s, rows: list[dict]) -> None:
    """Fills each row's "db" and each side's stored list, in place."""
    from sqlalchemy import select

    from src.db.schema import Competition, Injury, Lineup, Match, Sport, Team
    from src.ingestion.team_merge import source_ids
    check_schema(s)
    codes = dict(s.execute(select(Competition.id, Competition.code)).all())
    by_fid, by_prev = defaultdict(list), defaultdict(list)
    for mid, utc, cid, ext in s.execute(select(Match.id, Match.utc_date, Match.competition_id, Match.external_ids)
                                        .where(Match.sport == Sport.SOCCER)).all():
        ext = ext if isinstance(ext, dict) else {}
        if ext.get(SOURCE) is not None:
            by_fid[str(ext[SOURCE])].append((mid, utc, codes.get(cid)))
        for old in ext.get(f"{SOURCE}_prev") or []:
            by_prev[str(old)].append((mid, utc, codes.get(cid)))
    team_name = {}

    def tname(tid):
        if tid not in team_name:
            t = s.get(Team, tid)
            team_name[tid] = (t.name if t else None, source_ids(t.external_ids if t else None, SOURCE))
        return team_name[tid]

    for x in rows:
        r = x["row"]
        m, how = s.get(Match, x["match_id"]), "by match id"
        ko = redated.as_utc(r.get("utc_date"))
        # Codex on #722: the id is machine-local; it stands only for the row's teams AND its kickoff (the same two
        # clubs meet twice a season), else the teams-and-kickoff lookup below decides
        if m is not None and ((tname(m.home_team_id)[0], tname(m.away_team_id)[0]) != (r.get("home_team"),
                                                                                       r.get("away_team"))
                              or ko is None or m.utc_date != ko):
            m = None
        if m is None:
            found = [c for c in s.execute(select(Match).where(Match.utc_date == ko)).scalars()
                     if (tname(c.home_team_id)[0], tname(c.away_team_id)[0]) == (r.get("home_team"),
                                                                                r.get("away_team"))] if ko else []
            m, how = (found[0], "by both team names and the row's kickoff (the match id is another game's)") \
                if len(found) == 1 else (None, "not in the database" if not found else
                                         f"{len(found)} stored matches share the teams and kickoff (none used)")
        db = {"how": how, "match": None}
        x["db"] = db
        if m is None:
            continue
        ext = m.external_ids if isinstance(m.external_ids, dict) else {}
        db.update({"match": m.id, "status": getattr(m.status, "value", m.status), "score": (m.home_score, m.away_score),
                   "fixture": str(ext[SOURCE]) if ext.get(SOURCE) is not None else None,
                   "utc": m.utc_date,
                   "lineups": Counter(k for (k,) in s.execute(select(Lineup.kind).where(Lineup.match_id == m.id)))})
        for side, tid in (("home", m.home_team_id), ("away", m.away_team_id)):
            sd = x["sides"][side]
            sd["team_id"], sd["provider_ids"] = tid, tname(tid)[1]
            sd["stored"] = [{"id": i.id, "name": i.player_name, "position": i.player_position, "reason": i.reason,
                             "type": i.type, "fixture": i.fixture_source_id, "source": i.source,
                             "refreshed_at": i.refreshed_at}
                            for i in s.execute(select(Injury).where(Injury.team_id == tid)
                                               .order_by(Injury.id)).scalars()]
            for e in sd["stored"]:
                e["age"], e["age_text"] = fixture_age(e["fixture"], db, by_fid, by_prev, r.get("utc_date"))


def fixture_age(fid, db: dict, by_fid, by_prev, row_utc) -> tuple[str, str]:
    """Ruling 1(d): the entry's own fixture against this one."""
    if not fid:
        return NO_FIX_ID, NO_FIX_ID
    hits, prev = by_fid.get(str(fid), []), ""
    if not hits and by_prev.get(str(fid)):
        hits, prev = by_prev[str(fid)], " (a previous provider id of the match)"
    if not hits:
        return NOT_STORED, f"{NOT_STORED} (provider fixture {fid})"
    if len(hits) > 1:
        return FIX_AMBIG, f"{FIX_AMBIG} ({', '.join(str(h[0]) for h in hits)})"
    mid, utc, code = hits[0]
    if mid == db.get("match") or str(fid) == db.get("fixture"):
        return THIS, THIS + prev
    here = redated.as_utc(db.get("utc")) or redated.as_utc(row_utc)
    d = _hours(here, utc)
    if d is None:
        return NOT_STORED, f"fixture {fid}: match {mid} has no readable kickoff"
    if d >= 0:
        return EARLIER, f"{EARLIER} {d / 24:.1f} d before ({code or 'competition ?'}, match {mid}){prev}"
    return LATER, f"{LATER} {-d / 24:.1f} d after ({code or 'competition ?'}, match {mid}){prev}"


def recoverable(sd: dict) -> tuple[bool | None, str]:
    """Ruling 1(b), the exact test. None: the row's list was empty (nothing to recover)."""
    if sd["count"] is None:
        return False, "not recoverable (the row carries no input_quality count)"
    if sd["count"] == 0:
        return None, "empty as consumed (count 0): nothing to classify"
    if sd.get("stored") is None:
        return False, "not recoverable (the match is not in the database)"
    synced = redated.as_utc(sd["synced_at"])
    if synced is None:
        return False, "not recoverable (the row carries no synced_at)"
    if not sd["stored"]:
        return False, "not recoverable (no row stored for the team now)"
    stamps = sorted({redated.as_utc(e["refreshed_at"]) for e in sd["stored"]}, key=lambda d: (d is None, d))
    if len(stamps) > 1:
        return False, f"not recoverable (the stored rows carry {len(stamps)} stamps)"
    if stamps[0] != synced:
        return False, (f"not recoverable (overwritten at {stamps[0]:%Y-%m-%dT%H:%M:%S.%f})" if stamps[0] and
                       stamps[0] > synced else f"not recoverable (stored stamp {stamps[0]} is not the row's)")
    if len(sd["stored"]) != sd["count"]:
        return False, f"not recoverable (stored count {len(sd['stored'])}, row count {sd['count']})"
    return True, "recoverable (stored refreshed_at equals synced_at; counts match)"


# ---- the appearances ------------------------------------------------------------------------------------------------

def keys_lines(kind: str, rows: list) -> list[str]:
    """Law 1: the keys of the first real answer of a kind, printed before any field of it is read."""
    first = next((b for b in rows if isinstance(b, dict)), None)
    if first is None:
        return [f"  {kind}: the first answer holds no object row; no key to print"]
    L = [f"  {kind}: answer row keys {sorted(first)}",
         f"    team keys {sorted(_d(first.get('team')))}"]
    if kind == "lineups":
        slots = [x for k in ("startXI", "substitutes") if isinstance(first.get(k), list) for x in first[k]
                 if isinstance(x, dict)]
        slot = slots[0] if slots else None
        L.append(f"    a startXI/substitutes slot's keys {sorted(_d(slot))} · its player keys "
                 f"{sorted(_d(_d(slot).get('player')))}")
    else:
        ents = [x for x in first["players"] if isinstance(x, dict)] if isinstance(first.get("players"), list) else []
        ent = ents[0] if ents else None
        st = _d(ent).get("statistics")
        st0 = st[0] if isinstance(st, list) and st else None
        L.append(f"    a players[] entry's keys {sorted(_d(ent))} · its player keys {sorted(_d(_d(ent).get('player')))}"
                 f" · statistics[0] keys {sorted(_d(st0))} · games keys {sorted(_d(_d(st0).get('games')))}")
    return L


def _int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def squad(lineups, players, home_ids: set, away_ids: set, label: str, malformed: list) -> dict:
    """{side: {"lineups": read?, "players": read?, "partial": [kind], "cands": [candidate]}} from the two answers;
    candidates keyed by the provider player id (by name where none is sent). A kind is read for a side only when every
    member of its block was the provider's shape (lineups: startXI and substitutes both lists of slots holding a player
    object; players: a list of entries holding a player object and a statistics[0].games object whose minutes is an int
    or null). A block with any member missing or malformed puts the kind in "partial": its well-formed members still
    give candidates, but a name it may hide is never classed absent. Rows not the provider's shape are counted and
    named."""
    out = {s: {"lineups": False, "players": False, "partial": [], "cands": {}} for s in ("home", "away")}
    unmapped = []

    def side_of(block, kind, i):
        team = block.get("team")
        tid = _d(team).get("id")
        if tid is not None and str(tid) in home_ids:
            return "home"
        if tid is not None and str(tid) in away_ids:
            return "away"
        unmapped.append(f"{label} {kind} block {i} (team id {tid})")
        return None

    def cand(side, p, where):
        """The candidate for a player object, or None (counted) for an id that is not an int or a string, or a player
        with neither id nor name."""
        pid, nm = p.get("id"), p.get("name")
        if pid is not None and not (isinstance(pid, str) or _int(pid) is not None):
            malformed.append(f"{where}: player id is a {type(pid).__name__}, not the provider's shape")
            return None
        if pid is None and not (isinstance(nm, str) and nm.strip()):
            malformed.append(f"{where}: a player with neither id nor name")
            return None
        key = ("id", str(pid)) if pid is not None else ("name", nm.strip())
        c = out[side]["cands"].setdefault(key, {"names": set(), "id": pid})
        if isinstance(nm, str) and nm.strip():
            c["names"].add(nm.strip())
        return c

    def done(side, kind, ok):
        if ok:
            out[side][kind] = True
        elif kind not in out[side]["partial"]:
            out[side]["partial"].append(kind)

    for i, b in enumerate(lineups or []):
        if not isinstance(b, dict):
            malformed.append(f"{label} lineups row {i}: not an object")
            continue
        side = side_of(b, "lineups", i)
        if side is None:
            continue
        ok = True
        for key, role in (("startXI", "xi"), ("substitutes", "bench")):
            slots = b.get(key)
            if not isinstance(slots, list):
                malformed.append(f"{label} lineups {side} {key}: " + ("missing" if slots is None else "not a list"))
                ok = False
                continue
            for j, sl in enumerate(slots):
                p = sl.get("player") if isinstance(sl, dict) else None
                if not isinstance(p, dict):
                    malformed.append(f"{label} lineups {side} {key}[{j}]: not a slot with a player object")
                    ok = False
                    continue
                c = cand(side, p, f"{label} lineups {side} {key}[{j}]")
                if c is None:
                    ok = False
                    continue
                c[role] = True
        done(side, "lineups", ok)
    for i, b in enumerate(players or []):
        if not isinstance(b, dict):
            malformed.append(f"{label} players row {i}: not an object")
            continue
        side = side_of(b, "players", i)
        if side is None:
            continue
        ents = b.get("players")
        if not isinstance(ents, list):
            malformed.append(f"{label} players {side}: players is " + ("missing" if ents is None else "not a list"))
            done(side, "players", False)
            continue
        ok = True
        for j, e in enumerate(ents):
            p = e.get("player") if isinstance(e, dict) else None
            if not isinstance(p, dict):
                malformed.append(f"{label} players {side}[{j}]: not an entry with a player object")
                ok = False
                continue
            c = cand(side, p, f"{label} players {side}[{j}]")
            if c is None:
                ok = False
                continue
            c["in_players"] = True
            st = e.get("statistics")
            g = st[0].get("games") if isinstance(st, list) and st and isinstance(st[0], dict) else None
            if not isinstance(g, dict):
                malformed.append(f"{label} players {side}[{j}]: no statistics[0].games object")
                ok = False
                continue
            mins = g.get("minutes")
            if mins is not None and _int(mins) is None:
                malformed.append(f"{label} players {side}[{j}]: games.minutes {mins!r} is not an int or null")
                c["minutes_bad"] = repr(mins)
                ok = False
                continue
            c["games_read"] = True
            c["minutes"], c["substitute"] = mins, g.get("substitute")
        done(side, "players", ok)
    for s in out.values():
        s["cands"] = list(s["cands"].values())
    out["unmapped"] = unmapped
    return out


def appearance(c: dict) -> str:
    """One provider player's class (ruling 1(a))."""
    if c.get("xi"):
        return STARTED
    if c.get("minutes_bad"):
        return f"{UNREAD} (minutes {c['minutes_bad']} not the provider's shape)"
    m = _int(c.get("minutes"))
    if c.get("games_read"):
        if m and m > 0:
            sub = c.get("substitute")
            return CAME_ON if sub is True or (sub is None and c.get("bench")) else STARTED if sub is False else PLAYED
        return DNP_SQUAD
    return f"{UNREAD} (on the bench; minutes not read)" if c.get("bench") else f"{UNREAD} (minutes not read)"


def classify(name: str, sq: dict | None, unread_why: str | None) -> tuple[str, str]:
    """(class, detail) for one listed name against its side's answers."""
    if sq is None or not (sq["lineups"] or sq["players"] or sq["partial"]):
        return UNREAD, unread_why or "no answer read"
    how, cs = name_match(name, sq["cands"])
    if how == "ambiguous":
        return AMBIGUOUS, "AMBIGUOUS: " + " | ".join(sorted("/".join(sorted(c["names"])) for c in cs))
    if how == "unmatched" and sq["partial"]:
        return UNREAD, (f"not found, and a missing or malformed member of the side's {' and '.join(sq['partial'])} "
                        "answer may hide him" + (f"; {unread_why}" if unread_why else ""))
    if how == "unmatched":
        read = " and ".join(k for k in ("lineups", "players") if sq[k])
        return DNP_ABSENT, f"UNMATCHED in the {read} answer{'s' if ' and ' in read else ''}: absent, or a name form the " \
            "match cannot see"
    c = cs[0]
    cls = appearance(c)
    det = (f"{'/'.join(sorted(c['names']))} ({how}; provider id {c.get('id')}; minutes {c.get('minutes')}, "
           f"substitute {c.get('substitute')})")
    return (UNREAD if cls.startswith(UNREAD) else cls), det if not cls.startswith(UNREAD) else f"{cls}: {det}"


# ---- the receipt ----------------------------------------------------------------------------------------------------

def stamp_bucket(h: float | None) -> str:
    if h is None:
        return "no stamp"
    if h < 0:
        return "stamp after the run's start"
    for top, lab in STAMP_BUCKETS:
        if top is None or h < top:
            return lab
    return STAMP_BUCKETS[-1][1]


def build(pop: dict, s, fetch: Fetch) -> dict:
    rows = pop["rows"]
    for x in rows:
        x["sides"] = {side: row_side(x["row"], side) for side in ("home", "away")}
    read_db(s, rows)
    keys, malformed, capped = [], [], []
    seen_kind = set()
    for x in rows:
        db, label = x["db"], f"match {x['match_id']}"
        fid = db.get("fixture")
        ans, why = {}, {}
        if fid is None:
            why = {k: "no provider fixture id (the match is not in the database, or has no api_football id)"
                   for k in ("lineups", "players")}
        else:
            for kind in ("lineups", "players"):
                try:
                    a = fetch(kind, fid, f"fixtures/{kind}", fixture=fid)
                except Capped:
                    capped.append(f"{label} {kind}")
                    why[kind] = "capped (the call cap stopped the reads)"
                    continue
                if a is None:
                    why[kind] = "the read FAILED"
                elif not a:
                    why[kind] = "answered with no rows"
                else:
                    if kind not in seen_kind:
                        seen_kind.add(kind)
                        keys += [f"  first real answer: fixture {fid} ({label})"] + keys_lines(kind, a)
                    ans[kind] = a
        x["reads"] = {k: ("read" if k in ans else why.get(k)) for k in ("lineups", "players")}
        sides = x["sides"]
        sq = squad(ans.get("lineups"), ans.get("players"), sides["home"].get("provider_ids") or set(),
                   sides["away"].get("provider_ids") or set(), f"{label} (fixture {fid})", malformed) \
            if ans else None
        x["unmapped"] = sq["unmapped"] if sq else []
        unread_why = "; ".join(f"{k} {v}" for k, v in why.items()) if why else None
        for side, sd in sides.items():
            ssq = sq[side] if sq else None
            side_why = unread_why
            if ssq is not None and not (ssq["lineups"] or ssq["players"] or ssq["partial"]):   # none for this team
                side_why = "; ".join(x for x in (unread_why, "the answers read hold no block for the team (its "
                                                 f"provider ids {sorted(sd.get('provider_ids') or []) or 'none'})")
                                     if x)
            ok, sd["why"] = recoverable(sd)
            sd["recoverable"] = ok
            sd["stamp_h"] = _hours(x["run"], sd["synced_at"])
            sd["bucket"] = stamp_bucket(sd["stamp_h"])
            if ok:
                sd["listed"] = [{"name": e["name"], "type": e["type"] if e["type"] is not None else NO_TYPE,
                                 "reason": e["reason"], "position": e["position"], "age": e["age"],
                                 "age_text": e["age_text"]} for e in sd["stored"]]
                stored = Counter(e["name"] for e in sd["stored"])
                sd["cross"] = [n for n in (sd["names"] or []) if not stored[n]]
                sd["hidden"] = 0
            else:
                sd["listed"] = [{"name": n, "type": NOT_RECOVERABLE, "reason": None, "position": None,
                                 "age": NOT_RECOVERABLE, "age_text": NOT_RECOVERABLE} for n in (sd["names"] or [])] \
                    if ok is False else []
                sd["cross"] = None
                # None: the row carries no count, so how many names the 8-name cut hid is UNKNOWN (never 0)
                sd["hidden"] = (None if sd["count"] is None else max(0, sd["count"] - len(sd["names"] or []))) \
                    if ok is False else 0
            # the listed set is incomplete: names were cut (or how many is unknown) and the list is not recoverable
            sd["list_cut"] = ok is False and (sd["hidden"] is None or sd["hidden"] > 0)
            for e in sd["listed"]:
                e["class"], e["detail"] = classify(e["name"], ssq, side_why)
            # ruling 1(f): the not-listed class. "did not appear" needs the side's minutes read in full: only the
            # players answer carries them, so a side read through lineups alone (or a players block with a member not
            # the provider's shape) is "not listed, appearance unread", never a measured 0.
            sd["fixture_read"] = bool(ssq and (ssq["lineups"] or ssq["players"] or ssq["partial"]))
            listed = [e["name"] for e in sd["listed"]]

            def unlisted(c):
                return not any(name_match(n, [c])[0] != "unmatched" for n in listed)

            def nm(c):
                return "/".join(sorted(c["names"])) or f"id {c.get('id')}"
            if ssq and ssq["players"] and "players" not in ssq["partial"]:
                sd["not_listed"] = sorted(nm(c) for c in ssq["cands"] if appearance(c) == DNP_SQUAD and unlisted(c))
                sd["not_listed_why"] = None
                # Codex on #722: a member of /fixtures/lineups the players block does not hold (a bench name with no
                # minutes entry) is unread, beside the measured count, never dropped from both lists
                sd["not_listed_unread"] = sorted(nm(c) for c in ssq["cands"]
                                                 if appearance(c).startswith(UNREAD) and unlisted(c))
            else:
                sd["not_listed"] = None
                if not sd["fixture_read"]:
                    sd["not_listed_why"] = "the fixture was not read for this side"
                elif ssq["players"] or "players" in ssq["partial"]:
                    sd["not_listed_why"] = ("minutes not all read: a member of the side's players answer is missing or "
                                            "not the provider's shape")
                else:
                    pr = x["reads"]["players"]
                    sd["not_listed_why"] = "minutes not read: /fixtures/players " + (
                        "holds no block for the team" if pr == "read" else str(pr))
                sd["not_listed_unread"] = sorted(nm(c) for c in (ssq["cands"] if ssq else [])
                                                 if appearance(c).startswith(UNREAD) and unlisted(c))
            sd["squad"] = ssq
        x["worked"] = worked(x)
    found = {lab for x in rows for lab, _t in x["worked"]}
    missing = [(lab, f"no PL closing row for {home} v {away} on {date} in the population")
               for lab, home, away, date, _side, _name in WORKED if lab not in found]
    return {"rows": rows, "keys": keys, "malformed": malformed, "capped": capped, "worked_missing": missing}


def worked(x: dict) -> list[tuple[str, str]]:
    r, out = x["row"], []
    day = (redated.as_utc(r.get("utc_date")) or datetime.min).strftime("%Y-%m-%d")
    for lab, home, away, date, side, name in WORKED:
        if (r.get("home_team"), r.get("away_team"), day) != (home, away, date):
            continue
        sd = x["sides"][side]
        on = [e for e in sd["listed"] if name_match(name, [{"names": {e["name"]}}])[0] != "unmatched"]
        if on:
            e = on[0]
            out.append((lab, f"{name} ({side}, listed as {e['name']!r}, type {e['type']!r}, fixture age "
                             f"{e['age_text']}): {e['class']} — {e['detail']}"))
            continue
        if sd["list_cut"]:
            # listed or not is unknown: the appearance class alone, never a "not listed" label
            hid = f"{sd['hidden']} hidden by the 8-name cut" if sd["hidden"] else "the listed count unknown"
            pre = f"{name} ({side}): on none of the {len(sd['listed'])} names shown ({hid} and the list not " \
                  "recoverable): listed or not is UNKNOWN; appearance: "
            if not sd["fixture_read"]:
                out.append((lab, pre + UNREAD))
            else:
                cls, det = classify(name, sd["squad"], None)
                out.append((lab, pre + f"{cls} — {det}"))
            continue
        pre = f"{name} ({side}): on no list; "
        if not sd["fixture_read"]:
            out.append((lab, pre + NOT_LISTED_UNREAD))
            continue
        cls, det = classify(name, sd["squad"], None)
        tail = {DNP_SQUAD: NOT_LISTED_DNP, DNP_ABSENT: f"{NOT_LISTED_DNP} (absent from the side's answers read)"}
        out.append((lab, pre + tail.get(cls, f"not listed, {cls}") + f" — {det}"))
    return out


def _cnt(c: Counter) -> str:
    return " · ".join(f"{k} {c[k]}" for k in CLASSES if c.get(k)) or "none"


def _machine_role() -> str | None:
    """SP_EXPORTS_MIRROR_ROLE as closing.mirror_role reads it (sp_common.setting: the environment, else host.env, else
    the checkout's .env): host or laptop, else None. Not the Desk fence's reader (desk_policy.role_reading), which no
    script references (tests/test_host_watch_after_flip.py)."""
    role = (sp_common.setting("SP_EXPORTS_MIRROR_ROLE") or "").strip()
    return role if role in ("host", "laptop") else None


def lines(res: dict, pop: dict, hdr: dict, fetch: Fetch) -> tuple[list[str], dict]:
    rows = res["rows"]
    L = [f"PL INJURY CLASSIFICATION RECEIPT (ARCHITECT 2026-10-27, addendum 171 item 1; #688) · READ-ONLY · "
         f"database {hdr['db']} · closing files {hdr['exports']}/closing_*.json (family {FAMILY}, competition "
         f"{COMPETITION}, run start >= {hdr['since']:%Y-%m-%dT%H:%M:%S}: the #629 merge, #615's stamping) · rows "
         f"{len(rows)} of {pop['files']} closing file(s) read · machine role "
         f"{_machine_role() or 'unknown'} (ruling 1(b) reads the LAPTOP's database, or a .backup "
         "copy of it through --db)",
         f"PROVIDER (ruling 1(a)): calls made {fetch.calls} · answers read from the kept payloads {fetch.cached} · "
         f"failed {len(fetch.failed)} · answered with no rows {len(fetch.empty)} · call cap {fetch.max_calls} · "
         f"payloads {fetch.save}" + (f" · INCOMPLETE: the cap stopped {len(res['capped'])} read(s); a re-run resumes "
                                     "from the kept payloads" if res["capped"] else ""),
         GUARD_COUNTS, LABELS_NOTE,
         "STAMP AGE (ruling 1(d)): our sync clock is the closing run's start minus input_quality.injuries.<side>."
         "synced_at (one stamp per sync, both sides); the entry's own age is its fixture_source_id's stored match.",
         "NAMES: soccer injuries store no provider player id; a name is matched normalized (accents, case, dots, "
         "hyphens, apostrophes) or in the 'Initial. Surname' form; AMBIGUOUS and UNMATCHED are printed as such. "
         "UNMATCHED reads 'did not appear (absent)', which may also be a name form the match cannot see.",
         SIDECARS]
    if pop["unreadable"]:
        L.append(f"unreadable closing files {len(pop['unreadable'])}: {', '.join(pop['unreadable'])}")
    if pop["no_run"]:
        L.append(f"PL rows with no run start (left out): matches {pop['no_run']}")
    census = Counter()
    for x in rows:
        for sd in x["sides"].values():
            if sd["recoverable"]:
                census.update(e["type"] for e in sd["listed"])
    sides = [sd for x in rows for sd in x["sides"].values()]
    L.append(f"CENSUS (ruling 1(c)), every stored type over the recoverable sides read, verbatim: "
             + (" · ".join(f"{k!r} {v}" for k, v in sorted(census.items())) or "none")
             + f" · sides recoverable {sum(1 for d in sides if d['recoverable'])} · not recoverable "
               f"{sum(1 for d in sides if d['recoverable'] is False)} · empty as consumed "
               f"{sum(1 for d in sides if d['recoverable'] is None)}")
    L.append("PROVIDER KEYS (law 1, printed from the first real answer of each kind before any field is read):")
    L += res["keys"] or ["  no answer read: no key printed, no field read"]
    by_type, by_stamp, by_age = defaultdict(Counter), defaultdict(Counter), defaultdict(Counter)
    nl_dnp, nl_unread, nl_cut, nl_unread_read = 0, 0, 0, 0
    unmatched = ambiguous = 0
    for x in rows:
        r, db = x["row"], x["db"]
        desk = _d(r.get("desk"))
        fb = _d(_d(r.get("prediction")).get("factor_breakdown"))
        L.append(f"\n== match {x['match_id']} {r.get('home_team')} v {r.get('away_team')} · kickoff {r.get('utc_date')} "
                 f"· run {x['run']:%Y-%m-%dT%H:%MZ} ({x['file']}, git_sha {x['git_sha']}; earlier runs "
                 f"{x['earlier_runs']}) · desk {desk.get('call')} {desk.get('pick')}")
        L.append(f"  DB: {db['how']}" + (f" · match {db['match']} status {db['status']} score {db['score'][0]}-"
                                         f"{db['score'][1]} · provider fixture {db['fixture']} · stored lineups "
                                         f"{sum(db['lineups'].values())}"
                                         + (f" ({dict(db['lineups'])})" if db["lineups"] else "")
                                         if db["match"] else ""))
        L.append(f"  provider reads: lineups {x['reads']['lineups']} · players {x['reads']['players']}"
                 + (f" · team blocks not mapped to a side: {'; '.join(x['unmapped'])}" if x["unmapped"] else ""))
        L.append(f"  factor_breakdown: home {fb.get('home_injuries_count')} · away {fb.get('away_injuries_count')} · "
                 f"notes {fb.get('factor_notes')} · lineup_kind {fb.get('lineup_kind')}")
        for side in ("home", "away"):
            sd = x["sides"][side]
            L.append(f"  {side.upper()} {sd['team']}: count {sd['count']} (injuries.{side}_count {sd['count_block']}) "
                     f"· synced_at {sd['synced_at']} · stamp age "
                     + (f"{sd['stamp_h'] * 60:.0f} min" if sd["stamp_h"] is not None else "none")
                     + f" ({sd['bucket']}) · {sd['why']}"
                     + (f" · {sd['hidden']} listed name(s) hidden by the 8-name cut" if sd["hidden"] else
                        " · listed names hidden by the 8-name cut UNKNOWN (no input_quality count; "
                        f"injuries.{side}_count above is printed, not used)" if sd["list_cut"] else ""))
            if sd["cross"]:
                L.append(f"    CROSS-CHECK: row name(s) not in the stored list: {sd['cross']}")
            elif sd["cross"] == [] and sd["recoverable"]:
                L.append(f"    cross-check: the row's {len(sd['names'] or [])} name(s) are all in the stored list")
            for e in sd["listed"]:
                L.append(f"    {e['name']} · type {e['type']!r} · reason {e['reason']!r} · {e['age_text']} · "
                         f"{e['class']} — {e['detail']}")
                by_type[e["type"]][e["class"]] += 1
                by_stamp[sd["bucket"]][e["class"]] += 1
                by_age[e["age"]][e["class"]] += 1
                unmatched += e["detail"].startswith("UNMATCHED")
                ambiguous += e["class"] == AMBIGUOUS
            if sd["not_listed"] is not None:
                if sd["list_cut"]:                     # some may be listed: kept out of the did-not-appear total
                    nl_cut += len(sd["not_listed"])
                    cut = (f" ({sd['hidden']} listed name(s) hidden by the cut" if sd["hidden"] else
                           " (the listed count unknown") + ": some may be among these; counted apart)"
                else:
                    nl_dnp += len(sd["not_listed"])
                    cut = ""
                L.append(f"    {NOT_LISTED_DNP} {len(sd['not_listed'])}{cut}: {', '.join(sd['not_listed']) or 'none'}")
                if sd["not_listed_unread"]:
                    nl_unread_read += len(sd["not_listed_unread"])
                    L.append(f"    {NOT_LISTED_UNREAD} {len(sd['not_listed_unread'])} (in /fixtures/lineups, no minutes "
                             f"entry in the players answer): {', '.join(sd['not_listed_unread'])}")
            else:
                nl_unread += 1
                L.append(f"    {NOT_LISTED_UNREAD} ({sd['not_listed_why']})"
                         + (f": unlisted, minutes not read: {', '.join(sd['not_listed_unread'])}"
                            if sd["not_listed_unread"] else ""))
        for lab, txt in x["worked"]:
            L.append(f"  WORKED CASE {lab}: {txt}")
    for lab, txt in res["worked_missing"]:
        L.append(f"WORKED CASE {lab}: {txt}")
    L.append("\nBY TYPE (verbatim; ruling 1(c)):")
    for t in sorted(by_type, key=str):
        L.append(f"  {t!r}: {_cnt(by_type[t])}")
    L.append("BY STAMP AGE (our sync clock; ruling 1(d)):")
    for b in sorted(by_stamp):
        L.append(f"  {b}: {_cnt(by_stamp[b])}")
    L.append("BY THE ENTRY'S FIXTURE AGE (fixture_source_id; ruling 1(d)):")
    for b in sorted(by_age):
        L.append(f"  {b}: {_cnt(by_age[b])}")
    L.append(f"NOT LISTED (ruling 1(f)): {NOT_LISTED_DNP} {nl_dnp} · sides '{NOT_LISTED_UNREAD}' {nl_unread} · "
             f"on a side whose list was cut and is not recoverable (listed or not UNKNOWN, counted apart) {nl_cut} · "
             f"on a side read in full, in the lineups with no minutes entry (unread, counted apart) {nl_unread_read}")
    if res["malformed"]:
        L.append(f"NOT THE PROVIDER'S SHAPE {len(res['malformed'])} (counted, never read): "
                 + "; ".join(res["malformed"][:10]) + (" …" if len(res["malformed"]) > 10 else ""))
    for f in fetch.failed:
        L.append(f"  FAILED {f}")
    for f in fetch.empty:
        L.append(f"  NO ROWS {f}")
    if res["capped"]:
        L.append(f"INCOMPLETE: the call cap ({fetch.max_calls}) left {len(res['capped'])} read(s) unread: "
                 + ", ".join(res["capped"]))
    summary = {
        "rows": len(rows), "closing_files": pop["files"], "since": f"{hdr['since']:%Y-%m-%dT%H:%M:%S}",
        "matches": [x["match_id"] for x in rows],
        "sides_recoverable": sum(1 for d in sides if d["recoverable"]),
        "sides_not_recoverable": sum(1 for d in sides if d["recoverable"] is False),
        "sides_empty": sum(1 for d in sides if d["recoverable"] is None),
        "census": dict(census), "by_type": {str(k): dict(v) for k, v in by_type.items()},
        "by_stamp_age": {k: dict(v) for k, v in by_stamp.items()},
        "by_fixture_age": {k: dict(v) for k, v in by_age.items()},
        "not_listed_did_not_appear": nl_dnp, "not_listed_unread_sides": nl_unread, "not_listed_side_list_cut": nl_cut,
        "not_listed_unread_on_read_sides": nl_unread_read,
        "unmatched": unmatched, "ambiguous": ambiguous, "malformed": len(res["malformed"]),
        "calls": {"made": fetch.calls, "cached": fetch.cached, "failed": len(fetch.failed), "empty": len(fetch.empty),
                  "cap": fetch.max_calls},
        "incomplete": bool(res["capped"]),
        "worked": {**{lab: txt for x in rows for lab, txt in x["worked"]}, **dict(res["worked_missing"])}}
    L.append(TAG + " " + json.dumps(summary, sort_keys=True, default=str))
    return L, summary


def main(argv=None, echo=print, get=None) -> int:
    ap = argparse.ArgumentParser(description="addendum 171 item 1 (#688): the PL injury classification receipt")
    ap.add_argument("--exports", default="exports", help="the exports directory (default exports)")
    ap.add_argument("--since", default=DEFAULT_SINCE, type=_since,
                    help="closing run start from (UTC; default the #629 merge, #615's stamping)")
    ap.add_argument("--db", default=None, help="a .backup copy OUTSIDE data/, opened mode=ro (default: the app's "
                                               "configured database, opened mode=ro)")
    ap.add_argument("--save", default=str(DEFAULT_SAVE), help="the payload cache (never under data/)")
    ap.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS)
    a = ap.parse_args(argv)
    try:
        save = Path(a.save).expanduser().resolve()
        if _under_data(save):
            raise Refused(f"REFUSED: --save {save} is under data/ (law 5): the payloads never live there")
        if get is None:
            get, key = _probe_get()
            if not key:
                raise Refused("REFUSED: no API_FOOTBALL_KEY (environment or .env)")
        fetch = Fetch(save, a.max_calls, get)
        pop = population(Path(a.exports), a.since)
        with open_db(a.db) as (s, label):
            res = build(pop, s, fetch)
        out, _summary = lines(res, pop, {"db": label, "exports": a.exports, "since": a.since}, fetch)
    except Refused as e:
        echo(str(e))
        return 2
    for ln in out:
        echo(ln)
    return 0


if __name__ == "__main__":
    sys.exit(main())
