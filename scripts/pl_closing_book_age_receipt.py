"""
THE PL CLOSING-PAGE BOOK AGE RECEIPT (ARCHITECT 2026-11-22 09:03 ET, addendum 446 item 2; Refs #348), READ-ONLY.

ITEM 2, verbatim:
"2. THE BOOKS' PRICES ON A CLOSING PAGE CAN BE THE SLATE'S, HOURS OLD. On 2026-11-21 the books' fair
   probabilities for all six games that kicked off at 12:30Z and 15:00Z are identical to four places
   on the 11:00Z slate and on their closing pages of 11:55Z and 14:25Z, home, draw and away. The
   17:30Z game's moved, and so did today's Hull City game between 11:30Z and 13:25Z. Kalshi's quotes
   on the same pages were captured at the closing run. #348 already says the close's age is our
   capture's and not the quote's; this is what that costs on a matchday: the close we grade against,
   and the reference the Desk's edge is taken from, stood about three and a half hours behind for
   five games.
   THE RECEIPT, read-only: from the code, what the closing chain asks the provider for books and what
   stamp of its own each answer carries; and from the host's stored odds, for each Premier League
   closing page of 2026/27, the age of the books' prices at the page's export by the provider's own
   stamp where one is stored, else by the last stored change. Then say what it would take to print
   the quote's own age beside the capture's on the page and in results-tally. No build until I rule."
The addendum's frame, verbatim in part: "Each is SIZED BEFORE ANYTHING CHANGES: a read-only receipt, no build beyond
it, no change to v22, to the injuries feed (434 item 4 stands) or to the Desk." The "from the code" half and "what it
would take" are prose for the PR body and #348; this script is the stored-odds half.

WHAT IT READS (law 1: every key below was read from the code at origin/main 841eba24):
- THE PAGES: --exports, a flat directory of closing_*.json or a tree of dated folders <YYYY-MM-DD>/ (the mirror's
  host/), read with the rules of scripts/pl_injury_classification_receipt.py (closing_dirs: the directory, then each
  dated folder in name order; latest/ and any other subfolder never; --exports at a latest/ folder, by name or
  resolved, or a dated-named folder resolving to one, refused). Each FILE is a page (closing.closing_doc: "ONE
  CLOSING, ONE PAGE, ONE FILE"). The page's family is its closing block's, else the file name's segment; its run
  start is closing.start, else the file name's stamp (redated.closing_rows' rule); a name whose stamp has the syntax
  but no valid date/time (closing_SOCCER_2026-13-40T2500Z.json) gives none: the run start is unknown, as for
  closing_rows' page without a start (kept with no bound, counted under one), counted on FILES and labelled on the
  page, never an abort; its exported_at and git_sha are the
  file's top-level keys (closing_doc keeps the export's own, export.py:85-86; exported_at is
  utc_now_naive().isoformat() + "Z", microseconds and a Z, parsed through redated.as_utc, never a bare fromisoformat:
  Python 3.10 refuses the Z). Every row of a SOCCER page whose competition is "PL" and season "2026/27"
  (export.py's row keys) is kept: unlike #688 there is no one-row-per-match cut, because the ask is per closing page.
  A closing file's name is its run start (closing_name), so a re-paged start leaves a second page only where an
  earlier file survives in another folder: each page is reported and labelled ("re-paged: page i of n for this run
  start"; pages whose run start is unknown are never called re-pages of each other); a file whose run id and
  exported_at equal an earlier page's is that page's copy, printed and labelled, never counted twice. --from / --through bound the run start (qb_hold_receipt's parse_instant / in_bound: --from
  inclusive, --through exclusive), the pages outside counted on the header.
  From each row: match_id, utc_date, home_team, away_team, market.selections.{HOME,DRAW,AWAY}.fair_prob (rounded to 4
  places, export.py:742), market.bookmaker_count, and line_move.venues.book.{to_at,to_source_updated_at} where present
  (line_move.py:90-112: inside T-3h only, the book venue's latest snapshot at the export's clock; a cross-check, never
  the decider).
- THE COPY: --db COPY, REQUIRED, a .backup copy outside data/, behind #688's fence exactly (addendum 198 item 6(ii)):
  check_copy (missing, under data/, mlb_pitchers_gate.check_db, a -wal/-shm/-journal sidecar: refused), probe_copy
  (mlb_pitchers_gate.open_ro), then mlb_pitchers_gate.readonly_session (mode=ro + immutable=1); refused, exit 2,
  nothing read. No src.db module is imported at module import, and the app's configured database is never opened.
  matches (id, home_team_id, away_team_id, utc_date), teams (id, name), odds_snapshots (match_id, market, selection,
  devig_prob, n_books, captured_at, source, and source_updated_at ONLY when the copy has the column: it is unmapped,
  schema.py:359-363, so it is found by PRAGMA table_info on the copy's own connection and read by Core SQL there,
  never through a helper that inspects the app's engine). The rows read: source 'api_football' (the adapter's
  source_name, api_football.py:202; the sync's snapshot source, service.py:434, :1397-1404), market '1X2', the match.
- THE MATCH: the page's match_id where the copy's row has the page's teams (by name) and kickoff; else the one stored
  match with both team names and the kickoff; else "not found" with the cause, counted (ids are machine-local).
- A SESSION: one book fetch is one captured_at on every snapshot row it appends (api_football.py:380, the answer's one
  clock; service.py:1397-1404 appends one row per selection at cl["captured_at"]), so the snapshots are grouped by
  captured_at. A session lacking HOME, DRAW or AWAY (or carrying two values for one) is INCOMPLETE: counted, skipped,
  never priced and never a link in a run. A snapshot row whose captured_at is NULL or unparseable belongs to no
  session: counted per row and on TOTALS, and such a row never prints "at least" (the game's first stored session is
  unknown; labelled). Its stamp is source_updated_at (service.py:415-428 writes the oldest over
  the rows the close priced, the answer's one response[].update): unknown when the column is absent, when the
  session's rows are unstamped (NULL), or partly stamped (oldest_source_time's rule: one unknown makes it unknown).

THE MEASURES (ages in minutes at the page's exported_at; the distributions in hours):
- THE PRICED SESSION: the latest complete session captured at or before exported_at, VALIDATED: each of its devig_prob
  rounded to 4 places equals the page's fair_prob. Else the latest earlier session that validates, labelled "page
  matches an earlier session" with its capture time; else "no stored session matches the page" (counted, law 4: never
  forced).
- CAPTURE AGE: exported_at - the priced session's captured_at (our fetch: #348's age).
- STAMP AGE: exported_at - the priced session's source_updated_at, the provider's own stamp, which addendum 32 item 3
  reads as "the newest that any quote in the answer can be; a quote may be older" (STAMP_TEXT): a LOWER BOUND on the
  quote's age. Unknown with its cause.
- LAST-CHANGE AGE: exported_at - the captured_at of the EARLIEST session of the unbroken trailing run of complete
  sessions (ending at the priced one) whose devig triple is identical as stored (unrounded). An incomplete session
  between two links whose present legs differ from the triple (or carry two values for one leg) ends the run there
  (law 4: the stored data shows the price moved; never counted through), and so does one EARLIER than the run's
  first link: the run is bounded there and is not "at least" (the price is known to have changed before the first
  link; labelled). Where that run reaches the first complete stored session for the game with no such earlier session
  and no unreadable snapshot row, the age is printed "at least" (a lower bound: the price may be older than our first
  capture). Beside it, separately, the same run read at 4 places, where it reaches further back (a move below the
  page's rounding).
- THE HEADLINE AGE: the stamp age where one is stored, else the last-change age (the architect's words), labelled.
- THE MECHANISM READ (the code map's M3 / M4): over the trailing identical run, "fresh" (a run of one: the price moved
  at this fetch), "M3" (the triple and the stamp both unchanged across the run's sessions), "M4" (the triple
  unchanged, the provider's stamp moved), or "stamp unknown in the run" (M3 and M4 not told apart). The count of the
  run's sessions is the count of fetches since the last change that carried the identical triple.

No provider call, no network, nothing written (the copy is opened immutable=1: no sidecar is created). No bookmaker
name is printed: only the page's own probabilities and stamps, our capture times and the provider's stamps.

Run:  python3 scripts/pl_closing_book_age_receipt.py --exports DIR|TREE --db COPY [--from INSTANT] [--through INSTANT]
Exit 0 done; 2 refused, nothing read. The last line is PL-CLOSING-BOOK-AGE-RECEIPT {json}.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections import Counter
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.walters import redated  # noqa: E402   (imports no src.db module)

TAG = "PL-CLOSING-BOOK-AGE-RECEIPT"
SOURCE = "api_football"                     # api_football.py:202, the adapter's source_name: the snapshots' source
MARKET = "1X2"
FAMILY, COMPETITION, SEASON = "SOCCER", "PL", "2026/27"
SELS = ("HOME", "DRAW", "AWAY")             # close.THREE_WAY: the soccer board
DP = 4                                      # export.py:742: "fair_prob": round(fair_prob, 4)
COPY_SIDECARS = ("-wal", "-shm", "-journal")
STAMP_TEXT = ("the newest that any quote in the answer can be; a quote may be older; never the time of a quote. "
              "NULL = unknown, never fresh")    # schema.py:310-311 (addendum 32 items 3-4), verbatim
BUCKETS = ((None, 0.0, "under 0 h (after the export)"), (0.0, 1.0, "0-1 h"), (1.0, 2.0, "1-2 h"),
           (2.0, 3.0, "2-3 h"), (3.0, 6.0, "3-6 h"), (6.0, 12.0, "6-12 h"), (12.0, None, "12 h or more"))
MEASURES = ("headline", "stamp", "last_change", "capture")
NO_COLUMN = "odds_snapshots.source_updated_at absent on this copy"
UNSTAMPED = "the priced session's rows unstamped (NULL)"
PARTLY = "the priced session's rows partly stamped"
NOT_FOUND = "match not found in the copy"
NO_FAIR = "the page shows no book fair (no complete H/D/A fair_prob)"
NO_EXPORTED = "the page has no readable exported_at"
NO_SESSION = "no complete stored session at or before the export"
NO_MATCH = "no stored session matches the page"
EARLIER = "page matches an earlier session"
LATEST = "the latest complete session at or before the export"
READS = {"matches": {"id", "home_team_id", "away_team_id", "utc_date"},
         "teams": {"id", "name"},
         "odds_snapshots": {"match_id", "market", "selection", "devig_prob", "n_books", "captured_at", "source"}}

DEFINITIONS = (
    "THE PRICED SESSION: the latest complete api_football 1X2 snapshot session (one captured_at = one fetch) at or "
    "before the page's exported_at, validated: each devig_prob rounded to 4 places equals the page's fair_prob; else "
    "the latest earlier session that validates (labelled 'page matches an earlier session'); else 'no stored session "
    "matches the page' (counted, never forced). An incomplete session (a leg missing) is counted and skipped; a "
    "snapshot row whose captured_at is unreadable is in no session, counted on its row and on TOTALS.",
    "CAPTURE AGE: exported_at minus the priced session's captured_at: our fetch time, #348's age.",
    "STAMP AGE: exported_at minus the priced session's source_updated_at, the provider's own stamp (schema.py, "
    "addendum 32 items 3-4: \"" + STAMP_TEXT + "\"): a LOWER BOUND on the quote's age. Unknown with its cause.",
    "LAST-CHANGE AGE: exported_at minus the captured_at of the earliest session of the unbroken trailing run of "
    "complete sessions, ending at the priced one, whose devig triple is identical as stored (unrounded); an "
    "incomplete session between two links whose present legs differ ends the run, and so does one earlier than the "
    "run's first link (bounded there, never 'at least'); 'at least' where the run reaches the game's first complete "
    "stored session with no such earlier session and no unreadable snapshot row (then the first stored session is "
    "unknown, labelled). The run at 4 places is printed beside it where it reaches further back.",
    "HEADLINE AGE: the stamp age where one is stored, else the last-change age (\"by the provider's own stamp where "
    "one is stored, else by the last stored change\", addendum 446 item 2), labelled with which.",
    "MECHANISM (the code map's M3/M4, over the trailing identical run): fresh (a run of one) · M3 (triple and stamp "
    "unchanged) · M4 (triple unchanged, the stamp moved) · stamp unknown in the run.")


class Refused(Exception):
    """A refused read: exit 2, nothing read."""


def _under_data(p: Path) -> bool:
    return (ROOT / "data").resolve() in (p, *p.parents)


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parent / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_MODS: dict = {}


def _qb():
    """scripts/qb_hold_receipt.py by path (parse_instant, in_bound, run_label, _z, DATED; stdlib imports only)."""
    if "qb" not in _MODS:
        _MODS["qb"] = _load("qb_hold_receipt_for_446", "qb_hold_receipt.py")
    return _MODS["qb"]


def _bsa():
    """scripts/book_stamp_age_receipt.py by path (slot, QS; stdlib imports only at module import)."""
    if "bsa" not in _MODS:
        _MODS["bsa"] = _load("book_stamp_age_receipt_for_446", "book_stamp_age_receipt.py")
    return _MODS["bsa"]


# ---- the pages --------------------------------------------------------------------------------------------------

def bounds(f, t):
    qb = _qb()
    try:
        lo = qb.parse_instant(f, "--from") if f is not None else None
        hi = qb.parse_instant(t, "--through") if t is not None else None
    except qb.Refused as e:
        raise Refused(f"REFUSED: {e}") from None
    if lo is not None and hi is not None and not lo < hi:
        raise Refused(f"REFUSED: --from {qb._z(lo)} is not before --through {qb._z(hi)}: the window holds no run "
                      "start; nothing read")
    return lo, hi


def closing_dirs(exports: Path) -> list[tuple[Path, str]]:
    """pl_injury_classification_receipt.closing_dirs' folders: the directory, then each dated folder <YYYY-MM-DD>/ in
    name order; latest/ and any other subfolder never."""
    dated = sorted(p for p in exports.iterdir() if p.is_dir() and re.fullmatch(_qb().DATED, p.name))
    return [(exports, "")] + [(p, f"{p.name}/") for p in dated]


def _d(v) -> dict:
    return v if isinstance(v, dict) else {}


def _is_row(r) -> bool:
    return isinstance(r, dict) and r.get("competition") == COMPETITION and r.get("season") == SEASON


def read_pages(exports: Path, lo=None, hi=None) -> dict:
    """Every SOCCER closing page (file) of the folders closing_dirs names, in the bound, with its PL 2026/27 rows."""
    if not exports.is_dir():
        raise Refused(f"REFUSED: --exports {exports}: not a directory; nothing read")
    if "latest" in (exports.name, exports.resolve().name):
        raise Refused(f"REFUSED: --exports {exports}: a latest/ folder (resolves to {exports.resolve()}); latest/ is "
                      "never read (its files are copies of a dated folder's newest); pass its parent; nothing read")
    dirs = closing_dirs(exports)
    for sub, _pre in dirs[1:]:
        if sub.resolve().name == "latest":
            raise Refused(f"REFUSED: --exports {exports}: the dated folder {sub.name}/ resolves to {sub.resolve()}, a "
                          "latest/ folder; latest/ is never read; nothing read")
    qb = _qb()
    pages, bad = [], []
    n = Counter()
    for sub, pre in dirs:
        for p in sorted(sub.glob(redated.CLOSING_GLOB)):
            try:
                doc = json.loads(p.read_text())
                block = doc.get("closing") or {}
                if not isinstance(block, dict):
                    raise TypeError("closing block not an object")
                preds = doc.get("predictions") or []
                if not isinstance(preds, list):
                    raise TypeError("predictions not a list")
            except (OSError, ValueError, AttributeError, TypeError):
                bad.append(pre + p.name)
                continue
            n["files"] += 1
            run = redated.as_utc(block.get("start"))
            stamp = redated._STAMP.search(p.name)
            bad_stamp = None
            if run is None and stamp:
                try:
                    run = datetime.strptime(stamp.group(1), "%Y-%m-%dT%H%M")
                except ValueError:      # the stamp's syntax, no valid date/time: the run start unknown, never an abort
                    bad_stamp = stamp.group(1)
                    n["stamp_invalid"] += 1
            fam = block.get("family")
            if not isinstance(fam, str) or not fam:
                named = redated._FAMILY.match(p.name)
                fam = named.group(1) if named else None
            if fam != FAMILY:
                n["other_family"] += 1
                continue
            inb = qb.in_bound(run, lo, hi)
            if inb is not True:
                n["outside" if inb is False else "run_unknown"] += 1
                continue
            rows = [r for r in preds if _is_row(r)]
            n["other_rows"] += sum(1 for r in preds if not _is_row(r))
            if not rows:
                n["no_pl_row"] += 1
                continue
            pages.append({"file": pre + p.name, "run": run, "run_id": block.get("run_id"),
                          "exported_raw": doc.get("exported_at"), "exported_at": redated.as_utc(doc.get("exported_at")),
                          "git_sha": doc.get("git_sha"), "rows": rows, "copy_of": None, "repaged": None,
                          "bad_stamp": bad_stamp})
    pages.sort(key=lambda g: (g["run"] or datetime.min, g["exported_at"] or datetime.min, g["file"]))
    by_run: dict = {}
    for g in pages:
        by_run.setdefault(g["run"], []).append(g)
    for run, gs in by_run.items():
        originals = []
        for g in gs:
            # a copy needs both stamps read and equal: two pages with neither are two pages, never one copy
            twin = None if g["run_id"] is None or g["exported_raw"] is None else next(
                (o for o in originals if (o["run_id"], o["exported_raw"]) == (g["run_id"], g["exported_raw"])), None)
            if twin is not None:
                g["copy_of"] = twin["file"]
            else:
                originals.append(g)
        if run is not None and len(originals) > 1:      # pages whose start is unknown are never re-pages of each other
            for i, g in enumerate(originals, 1):
                g["repaged"] = (i, len(originals))
    return {"pages": pages, "unreadable": bad, "counts": dict(n), "dir": exports.resolve(), "dated": len(dirs) - 1,
            "lo": lo, "hi": hi}


# ---- the copy (#688's fence, addendum 198 item 6(ii)) -----------------------------------------------------------

def check_copy(db: str | None) -> Path:
    """--db, REQUIRED and always a .backup copy, checked before anything is read (#688's check_copy): missing, under
    data/, mlb_pitchers_gate.check_db (a hard link into data/, the app's configured database, no file), a
    -wal/-shm/-journal sidecar (immutable=1 would ignore it). Refused, exit 2, nothing read."""
    if db is None or not str(db).strip():
        raise Refused("REFUSED: --db is required: a .backup copy outside data/ (the host's pulled backup), opened "
                      "mode=ro + immutable=1 (addendum 198 item 6(ii)); the app's configured database is never read; "
                      "nothing read")
    path = Path(db).expanduser().resolve()
    if _under_data(path):
        raise Refused(f"REFUSED: --db {path} is under data/ (law 5): the ruled --db is a .backup copy OUTSIDE data/; "
                      "nothing read")
    if not path.is_file():
        raise Refused(f"REFUSED: no DB file at {path}: a read-only read never creates one; nothing read")
    from src.walters import mlb_pitchers_gate as mp     # imports no src.db module
    try:
        path = mp.check_db(db)
    except mp.GateRefused as e:
        raise Refused(f"REFUSED: {e}; nothing read") from None
    for sc in COPY_SIDECARS:
        if path.with_name(path.name + sc).exists():
            raise Refused(f"REFUSED: --db {path} has a {sc} sidecar ({path.name + sc}): not a fresh .backup copy; "
                          "immutable=1 would ignore it and read a stale file; take a fresh .backup copy; nothing read")
    return path


def probe_copy(path: Path) -> None:
    """mlb_pitchers_gate.open_ro opened and closed before any read: a file that is not SQLite, or has no matches
    table, is refused, exit 2, nothing read."""
    from src.walters import mlb_pitchers_gate as mp
    try:
        mp.open_ro(path).close()
    except mp.GateRefused as e:
        raise Refused(f"REFUSED: {e}" + ("" if str(e).endswith("nothing read") else "; nothing read")) from None


@contextmanager
def open_db(path: Path):
    """(session, label) on the checked copy through mlb_pitchers_gate.readonly_session (mode=ro + immutable=1)."""
    from src.walters import mlb_pitchers_gate as mp
    with mp.readonly_session(path) as s:
        yield s, (f"--db {path} (mode=ro + immutable=1 URI, {mp.COPY_URI_QUERY.lstrip('?')}: a .backup copy nothing "
                  "else writes; no sidecar created)")


def columns(s, table: str) -> set:
    """PRAGMA table_info on the copy's own connection (the session's bind); table names are this file's constants."""
    from sqlalchemy import text
    return {r[1] for r in s.execute(text(f"PRAGMA table_info({table})"))}


def check_schema(s) -> bool:
    """The READS tables and columns, a missing one refused (law 1); returns whether odds_snapshots has
    source_updated_at (the unmapped stamp column: present only where migrate_odds_source_updated_at.py ran)."""
    for t, cols in READS.items():
        got = columns(s, t)
        if not got:
            raise Refused(f"REFUSED: table {t} not in the database (law 1); nothing read")
        if cols - got:
            raise Refused(f"REFUSED: columns {', '.join(sorted(cols - got))} not in {t} (law 1); nothing read")
    return "source_updated_at" in columns(s, "odds_snapshots")


_MATCH_SQL = ("SELECT m.id, m.utc_date, th.name, ta.name FROM matches m LEFT JOIN teams th ON th.id = m.home_team_id "
              "LEFT JOIN teams ta ON ta.id = m.away_team_id ")


def find_match(s, r: dict) -> tuple[int | None, str]:
    """The page row's match on the copy: the page's id where the copy has the page's teams and kickoff; else the one
    stored match with both team names and the kickoff; else None with the cause."""
    from sqlalchemy import text
    ko, h, a, mid = redated.as_utc(r.get("utc_date")), r.get("home_team"), r.get("away_team"), r.get("match_id")
    why = "the page has no match id"
    if isinstance(mid, int) and not isinstance(mid, bool):
        got = s.execute(text(_MATCH_SQL + "WHERE m.id = :i"), {"i": mid}).first()
        if got is None:
            why = f"the page's id {mid} is not in the copy"
        elif (got[2], got[3]) != (h, a):
            why = f"the page's id {mid} is {got[2]} v {got[3]} on the copy"
        elif ko is None or redated.as_utc(got[1]) != ko:
            why = f"the page's id {mid} kicks off {got[1]} on the copy, the page {r.get('utc_date')}"
        else:
            return mid, "by the page's match id (teams and kickoff agree)"
    if ko is None or h is None or a is None:
        return None, f"{NOT_FOUND} ({why}; no teams-and-kickoff lookup: the page's teams or kickoff missing)"
    found = [x[0] for x in s.execute(text(_MATCH_SQL + "WHERE th.name = :h AND ta.name = :a"), {"h": h, "a": a})
             if redated.as_utc(x[1]) == ko]
    if len(found) == 1:
        return found[0], f"by both team names and the kickoff ({why})"
    if not found:
        return None, f"{NOT_FOUND} ({why}; no stored match with both team names and the kickoff)"
    return None, f"{NOT_FOUND} ({why}; {len(found)} stored matches share the teams and kickoff, none used)"


def read_sessions(s, mid: int, has_stamp: bool) -> dict:
    """The game's api_football 1X2 snapshot sessions, oldest first: {"sessions": [...], "unreadable": n}."""
    from sqlalchemy import text
    cols = "captured_at, selection, devig_prob, n_books" + (", source_updated_at" if has_stamp else "")
    q = text(f"SELECT {cols} FROM odds_snapshots WHERE match_id = :m AND source = :src AND market = :mk "
             "ORDER BY captured_at, id")
    by: dict = {}
    unreadable = 0
    for row in s.execute(q, {"m": mid, "src": SOURCE, "mk": MARKET}):
        at = redated.as_utc(row[0])
        if at is None:
            unreadable += 1
            continue
        g = by.setdefault(at, {"at": at, "legs": {}, "conflict": False, "n_books": set(), "stamps": []})
        sel, val = row[1], row[2]
        if sel in g["legs"] and g["legs"][sel] != val:
            g["conflict"] = True
        g["legs"][sel] = val
        g["n_books"].add(row[3])
        g["stamps"].append(redated.as_utc(row[4]) if has_stamp else None)
    out = []
    for at in sorted(by):
        g = by[at]
        legs = g["legs"]
        num = all(isinstance(legs.get(k), (int, float)) and not isinstance(legs.get(k), bool) for k in SELS)
        g["complete"] = set(SELS) <= set(legs) and num and not g["conflict"]
        g["why"] = (None if g["complete"] else "two values for one leg" if g["conflict"] else
                    "missing " + "/".join(k for k in SELS if k not in legs) if not set(SELS) <= set(legs) else
                    "a leg not a number")
        g["triple"] = tuple(legs.get(k) for k in SELS)
        g["triple4"] = tuple(round(v, DP) for v in g["triple"]) if g["complete"] else None
        if not has_stamp:
            g["stamp"], g["stamp_why"] = None, NO_COLUMN
        elif all(x is None for x in g["stamps"]):
            g["stamp"], g["stamp_why"] = None, UNSTAMPED
        elif any(x is None for x in g["stamps"]):
            g["stamp"], g["stamp_why"] = None, PARTLY
        else:
            g["stamp"], g["stamp_why"] = min(g["stamps"]), None
        out.append(g)
    return {"sessions": out, "unreadable": unreadable}


# ---- the measures -----------------------------------------------------------------------------------------------

def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def page_fair(r: dict) -> tuple | None:
    sel = _d(_d(r.get("market")).get("selections"))
    t = tuple(_num(_d(sel.get(k)).get("fair_prob")) for k in SELS)
    return None if any(v is None for v in t) else t


def _min(a: datetime, b: datetime) -> float:
    return (a - b).total_seconds() / 60


def _differs(x: dict, ref: tuple, key: str) -> bool:
    """An incomplete session against the run's triple (`key` "triple" as stored, "triple4" at 4 places): any present
    leg that differs, or two values for one leg, says the price moved there (law 4: never counted through)."""
    if x["conflict"]:
        return True
    for k, v in x["legs"].items():
        if k in SELS:
            got = round(v, DP) if key == "triple4" and _num(v) is not None else v
            if got != ref[SELS.index(k)]:
                return True
    return False


def _run_start(upto: list, idx: int, key: str, sess: list | None = None) -> int:
    """The earliest index of the unbroken trailing run of identical `key` ending at upto[idx]; an incomplete session
    of `sess` between two links whose present legs differ from the run's triple ends the run there."""
    ref = upto[idx][key]
    gaps = [x for x in (sess or []) if not x["complete"]]
    j = idx
    while j > 0 and upto[j - 1][key] == ref:
        if any(upto[j - 1]["at"] < x["at"] < upto[j]["at"] and _differs(x, ref, key) for x in gaps):
            break
        j -= 1
    return j


def _bounded_before(sess: list, first: dict, ref: tuple, key: str) -> bool:
    """Whether an incomplete session earlier than the run's first link (`first`) differs from the run's triple by
    _differs: then the run is bounded there (the price is known to have changed before the first link), never 'at
    least', although no earlier COMPLETE session exists."""
    return any(not x["complete"] and x["at"] < first["at"] and _differs(x, ref, key) for x in sess)


def line_move_check(r: dict, priced: dict) -> str:
    book = _d(_d(_d(r.get("line_move")).get("venues")).get("book"))
    if not book:
        return "absent"
    to_at = redated.as_utc(book.get("to_at"))
    to_st = redated.as_utc(book.get("to_source_updated_at"))
    diffs = []
    if to_at != priced["at"]:
        diffs.append(f"to_at {book.get('to_at')} vs the priced session {priced['at'].isoformat()}")
    if to_st != priced["stamp"]:
        diffs.append(f"to_source_updated_at {book.get('to_source_updated_at')} vs the priced session's stamp "
                     f"{priced['stamp'].isoformat() if priced['stamp'] else None}")
    return "agree" if not diffs else "differ (" + "; ".join(diffs) + ")"


def measure(page: dict, r: dict, ss: dict | None, how: str) -> dict:
    """One row's priced session, its four ages, its run and its mechanism read (or the cause of none)."""
    out = {"match_id": r.get("match_id"), "kickoff": redated.as_utc(r.get("utc_date")), "how": how,
           "home": r.get("home_team"), "away": r.get("away_team"), "fair": page_fair(r),
           "books": _d(r.get("market")).get("bookmaker_count"), "status": None, "label": None, "priced": None,
           "ages": {k: None for k in MEASURES}, "why": {}, "at_least": False, "run": None, "run4": None,
           "mechanism": None, "line_move": "absent", "incomplete": 0, "after_export": 0, "sessions": 0,
           "headline_by": None, "headline_at_least": False, "run_note": "", "unreadable": 0}
    if ss is None:
        out["status"] = NOT_FOUND
        return out
    sess = ss["sessions"]
    out["sessions"] = len(sess)
    out["unreadable"] = ss["unreadable"]
    exp = page["exported_at"]
    if exp is None:
        out["status"] = NO_EXPORTED
        return out
    if out["fair"] is None:
        out["status"] = NO_FAIR
        return out
    out["incomplete"] = sum(1 for x in sess if not x["complete"] and x["at"] <= exp)
    ko = out["kickoff"]
    out["after_export"] = sum(1 for x in sess if x["at"] > exp and (ko is None or x["at"] < ko))
    upto = [x for x in sess if x["complete"] and x["at"] <= exp]
    if not upto:
        out["status"] = NO_SESSION
        return out
    fair = out["fair"]
    idx = next((i for i in range(len(upto) - 1, -1, -1) if upto[i]["triple4"] == fair), None)
    if idx is None:
        out["status"] = NO_MATCH
        return out
    p = upto[idx]
    out["status"] = "priced"
    out["label"] = LATEST if idx == len(upto) - 1 else f"{EARLIER} (captured {p['at']:%Y-%m-%d %H:%M:%S}Z)"
    out["priced"] = {"at": p["at"], "stamp": p["stamp"], "stamp_why": p["stamp_why"],
                     "n_books": sorted(x for x in p["n_books"] if x is not None)}
    a = out["ages"]
    a["capture"] = _min(exp, p["at"])
    if p["stamp"] is not None:
        a["stamp"] = _min(exp, p["stamp"])
    else:
        out["why"]["stamp"] = p["stamp_why"]
    j = _run_start(upto, idx, "triple", sess)
    j4 = _run_start(upto, idx, "triple4", sess)
    a["last_change"] = _min(exp, upto[j]["at"])
    unr = out["unreadable"]
    unknown_first = f"the first stored session unknown: {unr} snapshot row(s) with an unreadable captured_at"
    bounded = j == 0 and _bounded_before(sess, upto[0], p["triple"], "triple")
    out["at_least"] = j == 0 and not bounded and not unr
    if j == 0:
        out["run_note"] = ("an earlier incomplete session's legs differ: the run is bounded there" if bounded else
                           unknown_first if unr else "")
    bounded4 = j4 == 0 and _bounded_before(sess, upto[0], p["triple4"], "triple4")
    out["run"] = {"n": idx - j + 1, "from": upto[j]["at"]}
    out["run4"] = {"n": idx - j4 + 1, "from": upto[j4]["at"], "age": _min(exp, upto[j4]["at"]),
                   "at_least": j4 == 0 and not bounded4 and not unr,
                   "note": ("an earlier incomplete session differs at 4 places: the run is bounded there" if bounded4
                            else unknown_first if j4 == 0 and unr else "")}
    if p["stamp"] is not None:
        a["headline"], out["headline_by"] = a["stamp"], "stamp"
    else:
        a["headline"], out["headline_by"] = a["last_change"], "last change"
        out["headline_at_least"] = out["at_least"]
    stamps = [x["stamp"] for x in upto[j:idx + 1]]
    n = idx - j + 1
    if n == 1:
        out["mechanism"] = ("first stored session (no earlier capture to compare)" if out["at_least"] else
                            f"first readable session ({unr} snapshot row(s) with an unreadable captured_at: an "
                            "earlier capture may exist)" if j == 0 and not bounded else
                            "fresh (the triple moved at this fetch)")
    elif any(x is None for x in stamps):
        out["mechanism"] = f"stamp unknown in the run (M3 and M4 not told apart; {n} sessions, triple unchanged)"
    else:
        moved = sum(1 for x, y in zip(stamps, stamps[1:]) if x != y)
        out["mechanism"] = (f"M3 (triple and stamp unchanged across {n} sessions)" if not moved else
                            f"M4 (triple unchanged across {n} sessions, the provider stamp moved {moved} time(s))")
    out["line_move"] = line_move_check(r, out["priced"])
    return out


def mech_key(m: str | None) -> str:
    if m is None:
        return "(not priced)"
    for k in ("M3", "M4", "fresh", "first stored session", "first readable session", "stamp unknown"):
        if m.startswith(k):
            return k
    return m


# ---- the console ------------------------------------------------------------------------------------------------

def bucket(h: float) -> str:
    for lo, hi, name in BUCKETS:
        if (lo is None or h >= lo) and (hi is None or h < hi):
            return name
    raise ValueError(h)


def dist(hours: list) -> dict:
    from src.walters.venue_quote_age import pct
    d = {"n": len(hours)}
    if hours:
        d.update(min=min(hours), max=max(hours), **{k: pct(hours, q) for k, q in _bsa().QS})
    return d


def _dist_text(d: dict) -> str:
    if not d["n"]:
        return "n 0"
    return (f"n {d['n']} · min {d['min']:.2f} · " + " · ".join(f"{k} {d[k]:.2f}" for k, _ in _bsa().QS)
            + f" · max {d['max']:.2f} (hours before the page's export)")


def _mins(v) -> str:
    return f"{v:.0f} min" if v is not None else "unknown"


def _t(d: datetime | None) -> str:
    return f"{d:%Y-%m-%d %H:%M:%S}Z" if d else "—"


def _unknown_cause(x: dict, k: str) -> str:
    if x["status"] != "priced":
        return x["status"]
    return x["why"].get(k, "?")


def report(pop: dict, s, has_stamp: bool, hdr: dict) -> tuple[list[str], dict]:
    qb = _qb()
    L = [f"PL CLOSING-PAGE BOOK AGE RECEIPT (ARCHITECT 2026-11-22 09:03 ET, addendum 446 item 2; Refs #348) · "
         f"READ-ONLY · no provider call, no network, nothing written · database {hdr['db']} · closing pages "
         f"{pop['dir']} (--exports {hdr['exports']}; closing_*.json there and in its dated folders <YYYY-MM-DD>/ "
         f"{pop['dated']}, never latest/; family {FAMILY}, competition {COMPETITION}, season {SEASON}; every page "
         f"and every row kept) · this run: {qb.run_label(pop['lo'], pop['hi'])[1]} · --from "
         f"{qb._z(pop['lo']) if pop['lo'] else '—'} · --through {qb._z(pop['hi']) if pop['hi'] else '—'}",
         f"odds_snapshots.source_updated_at: " + ("present on this copy" if has_stamp else
                                                  f"ABSENT ({NO_COLUMN}): every stamp age is unknown and the "
                                                  "headline falls back to the last change"),
         *DEFINITIONS]
    c = pop["counts"]
    L.append(f"FILES: closing files read {c.get('files', 0)} · unreadable {len(pop['unreadable'])}"
             + (f" ({', '.join(pop['unreadable'])})" if pop["unreadable"] else "")
             + " · name stamps not a valid date/time (no readable closing.start) "
             + f"{c.get('stamp_invalid', 0)} (run start unknown)"
             + f" · another family's {c.get('other_family', 0)} · SOCCER pages outside the bound "
             f"{c.get('outside', 0)} · run start unknown under a bound {c.get('run_unknown', 0)} · SOCCER pages "
             f"with no PL {SEASON} row {c.get('no_pl_row', 0)} · other rows on the pages read (another competition "
             f"or season) {c.get('other_rows', 0)}")
    rows, page_sum = [], []
    for g in pop["pages"]:
        lab = ""
        if g["copy_of"]:
            lab = f" · a COPY of {g['copy_of']} (same run id and exported_at): printed, not counted again"
        elif g["repaged"]:
            lab = f" · RE-PAGED: page {g['repaged'][0]} of {g['repaged'][1]} for this run start"
        if g.get("bad_stamp"):
            lab += (" · RUN START UNKNOWN: no readable closing.start, and the name's stamp "
                    f"{g['bad_stamp']} is not a valid date/time")
        L.append(f"\n== page {g['file']} · run start {_t(g['run'])} · exported_at {g['exported_raw']} · git_sha "
                 f"{str(g['git_sha'])[:8] if g['git_sha'] else '—'} · rows {len(g['rows'])}{lab}")
        recs = []
        for r in g["rows"]:
            mid, how = find_match(s, r)
            ss = read_sessions(s, mid, has_stamp) if mid is not None else None
            x = measure(g, r, ss, how)
            x["page"], x["counted"] = g["file"], g["copy_of"] is None
            recs.append(x)
            f = x["fair"]
            L.append(f"  {_t(x['kickoff'])} · match {x['match_id']} {x['home']} v {x['away']} · page fair H/D/A "
                     + ("/".join(f"{v:.4f}" for v in f) if f else "—")
                     + f" · bookmaker_count {x['books']} · on the copy: {how}"
                     + (f" · snapshot rows with an unreadable captured_at {x['unreadable']} (in no session)"
                        if x["unreadable"] else ""))
            if x["status"] != "priced":
                L.append(f"    NOT PRICED: {x['status']} (sessions stored {x['sessions']}; incomplete at or before "
                         f"the export {x['incomplete']})")
                continue
            p, a = x["priced"], x["ages"]
            L.append(f"    priced session captured {_t(p['at'])} · stamp "
                     + (_t(p["stamp"]) if p["stamp"] else f"unknown ({p['stamp_why']})")
                     + f" · n_books {p['n_books']} · {x['label']}")
            r4 = x["run4"]
            four = (f" · at 4 places {'at least ' if r4['at_least'] else ''}{_mins(r4['age'])} ({r4['n']} sessions "
                    f"from {_t(r4['from'])}; a move below the page's rounding{'; ' + r4['note'] if r4.get('note') else ''})"
                    if r4["n"] > x["run"]["n"] else "")
            L.append(f"    capture age {_mins(a['capture'])} · stamp age "
                     + (f"{_mins(a['stamp'])} (a lower bound on the quote's age)" if a["stamp"] is not None else
                        f"unknown ({x['why']['stamp']})")
                     + f" · last-change age {'at least ' if x['at_least'] else ''}{_mins(a['last_change'])} "
                     f"(identical as stored across {x['run']['n']} session(s) from {_t(x['run']['from'])}"
                     f"{'; ' + x['run_note'] if x['run_note'] else ''}){four}")
            L.append(f"    HEADLINE {'at least ' if x['headline_at_least'] else ''}{_mins(a['headline'])} (by "
                     f"{'the stamp' if x['headline_by'] == 'stamp' else 'the last change'}) · {x['mechanism']} · "
                     f"incomplete sessions "
                     f"skipped {x['incomplete']} · sessions after the export, before kickoff {x['after_export']} · "
                     f"line_move book cross-check: {x['line_move']}")
        if g["copy_of"] is None:
            hs = [x["ages"]["headline"] / 60 for x in recs if x["ages"]["headline"] is not None]
            page_sum.append({"file": g["file"], "run": g["run"], "rows": len(recs),
                             "priced": sum(1 for x in recs if x["status"] == "priced"), **dist(hs)})
            rows += recs
    n = len(rows)
    st = Counter(x["status"] for x in rows)
    earlier = sum(1 for x in rows if (x["label"] or "").startswith(EARLIER))
    unr_rows, unr_snap = sum(1 for x in rows if x["unreadable"]), sum(x["unreadable"] for x in rows)
    L.append(f"\nTOTALS: pages {len(page_sum)} (copies not counted again "
             f"{sum(1 for g in pop['pages'] if g['copy_of'])}; re-paged run starts "
             f"{len({g['run'] for g in pop['pages'] if g['repaged']})}) · rows {n} · priced {st['priced']} (the "
             f"latest session {st['priced'] - earlier}, {EARLIER} {earlier}) · {NOT_FOUND} {st[NOT_FOUND]} · "
             f"{NO_MATCH} {st[NO_MATCH]} · {NO_SESSION} {st[NO_SESSION]} · {NO_FAIR} {st[NO_FAIR]} · {NO_EXPORTED} "
             f"{st[NO_EXPORTED]} · rows whose game has snapshot rows with an unreadable captured_at {unr_rows} "
             f"(snapshot rows {unr_snap}, summed over those rows; in no session, so no 'at least' on them)")
    summary = {"rows": n, "pages": len(page_sum), "copies": sum(1 for g in pop["pages"] if g["copy_of"]),
               "repaged_starts": len({g["run"] for g in pop["pages"] if g["repaged"]}), "status": dict(st),
               "earlier_session": earlier, "stamp_column": has_stamp,
               "unreadable_snapshots": {"rows": unr_rows, "snapshot_rows": unr_snap}, "files": c,
               "unreadable": pop["unreadable"],
               "exports_dir": str(pop["dir"]), "db": hdr["db"],
               "from": qb._z(pop["lo"]) if pop["lo"] else None, "through": qb._z(pop["hi"]) if pop["hi"] else None,
               "measures": {}}
    names = {"headline": "HEADLINE AGE (stamp where stored, else last change)", "stamp": "STAMP AGE (a lower bound "
             "on the quote's age)", "last_change": "LAST-CHANGE AGE", "capture": "CAPTURE AGE (ours, #348's)"}
    for k in MEASURES:
        hs = [x["ages"][k] / 60 for x in rows if x["ages"][k] is not None]
        unk = Counter(_unknown_cause(x, k) for x in rows if x["ages"][k] is None)
        d = dist(hs)
        L.append(f"{names[k]}: {_dist_text(d)} · unknown {sum(unk.values())} of {n}"
                 + (" (" + "; ".join(f"{w} {v}" for w, v in sorted(unk.items())) + ")" if unk else ""))
        bk = {name: sum(1 for h in hs if bucket(h) == name) for _lo, _hi, name in BUCKETS}
        L.append("    " + " · ".join(f"{name} {v}" for name, v in bk.items()) + f" (of {n}; unknowns in the "
                 "denominator)")
        extra = {}
        if k == "headline":
            by = Counter(x["headline_by"] + (" (at least)" if x["headline_at_least"] else "") for x in rows
                         if x["ages"][k] is not None)
            extra = {"by": dict(by)}
            L.append("    by: " + (" · ".join(f"{w} {v}" for w, v in sorted(by.items())) or "none"))
        if k == "last_change":
            extra = {"at_least": sum(1 for x in rows if x["at_least"])}
            L.append(f"    of which lower bounds ('at least': the run reaches the first stored session) "
                     f"{extra['at_least']}")
        summary["measures"][k] = {**d, "unknown": dict(unk), "buckets": bk, **extra}
    mech = Counter(mech_key(x["mechanism"]) for x in rows if x["status"] == "priced")
    lm = Counter(x["line_move"].split(" ")[0] for x in rows if x["status"] == "priced")
    L.append("MECHANISM (priced rows): " + (" · ".join(f"{k} {v}" for k, v in sorted(mech.items())) or "none"))
    L.append("LINE_MOVE CROSS-CHECK (priced rows; the page's line_move.venues.book to_at / to_source_updated_at "
             "against the priced session): " + (" · ".join(f"{k} {v}" for k, v in sorted(lm.items())) or "none"))
    L.append("BY PAGE (headline age, hours):")
    for p in page_sum:
        L.append(f"  {p['file']}: rows {p['rows']} · priced {p['priced']} · {_dist_text(p)}")
    L.append("BY KICKOFF SLOT (Europe/London, book_stamp_age_receipt.slot; headline age, hours):")
    slots: dict = {}
    for x in rows:
        slots.setdefault(_bsa().slot("PL", x["kickoff"]), []).append(x)
    by_slot = {}
    for name in sorted(slots):
        xs = slots[name]
        d = dist([x["ages"]["headline"] / 60 for x in xs if x["ages"]["headline"] is not None])
        by_slot[name] = {"rows": len(xs), "unknown": sum(1 for x in xs if x["ages"]["headline"] is None), **d}
        L.append(f"  {name}: rows {len(xs)} · unknown {by_slot[name]['unknown']} · {_dist_text(d)}")
    summary.update(mechanism=dict(mech), line_move=dict(lm),
                   by_page={p["file"]: {k: v for k, v in p.items() if k not in ("file",)} for p in page_sum},
                   by_slot=by_slot)
    L.append(TAG + " " + json.dumps(summary, sort_keys=True, default=str))
    return L, summary


def main(argv=None, echo=print) -> int:
    ap = argparse.ArgumentParser(description="addendum 446 item 2 (Refs #348): the PL closing-page book age receipt")
    ap.add_argument("--exports", required=True,
                    help="the closing pages: a flat directory of closing_*.json (exports/host/) or a tree of dated "
                         "folders <YYYY-MM-DD>/ (the mirror's host/); latest/ never read")
    ap.add_argument("--db", default=None,
                    help="REQUIRED: a .backup copy OUTSIDE data/ (the host's pulled backup), opened mode=ro + "
                         "immutable=1 (addendum 198 item 6(ii)); without it, exit 2, nothing read")
    ap.add_argument("--from", dest="from_", default=None, metavar="INSTANT",
                    help="bound the closing run's start, INCLUSIVE, a UTC instant YYYY-MM-DDTHH:MM:SSZ")
    ap.add_argument("--through", default=None, metavar="INSTANT",
                    help="bound the closing run's start, EXCLUSIVE, a UTC instant YYYY-MM-DDTHH:MM:SSZ")
    a = ap.parse_args(argv)
    try:
        path = check_copy(a.db)                       # first: without a copy nothing is read
        lo, hi = bounds(a.from_, a.through)
        probe_copy(path)
        pop = read_pages(Path(a.exports), lo, hi)
        with open_db(path) as (s, label):
            has_stamp = check_schema(s)
            out, _summary = report(pop, s, has_stamp, {"db": label, "exports": a.exports})
    except Refused as e:
        echo(str(e))
        return 2
    for ln in out:
        echo(ln)
    return 0


if __name__ == "__main__":
    sys.exit(main())
