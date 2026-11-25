"""
THE CLOSING BOOK-GAP RECEIPT (ARCHITECT 2026-11-25 10:47 ET, addendum 532 item 4, its plan ruled by addendum 534
item 3; 477 item 4(b); Refs #348), READ-ONLY.

ITEM 4, verbatim: "THE COST RECEIPT (477 item 4(b)), read-only, its own PR, AFTER the quarterback receipt: a
reviewable head by Tuesday 2026-12-22 12:00 ET. scripts/closing_book_gap_receipt.py and its tests, on the pattern of
scripts/pl_closing_book_age_receipt.py, for SOCCER and NFL: per closing row, the absolute gap between the books' fair
price and Kalshi's on the same page, by the stamp-age bucket of the books' session; and for each staked row the bucket
of its reference. It reads --exports DIR and --db COPY (mode=ro, immutable=1), no network, nothing written. It never
reads an order, a unit, a contract count or any amount; it prints counts and gaps in percentage points, and judges
nothing." Its ten, as 532 item 4 answers them: (1) the closing page's own call, the latest page of a start; LADDER
rows counted apart; (2) the age taken at exported_at; (3) the HOME leg on every row with both sides priced, and the
pick on a staked row; (5) the buckets under 1 h, 1 to 2, 2 to 3, 3 to 6, 6 to 12, 12 to 24, 24 h or more, no stamp;
(6) a re-paged start counts once, by its latest page, the earlier pages labelled and out; (7) each family from its
first stamped row in the record, which the receipt prints; (8) files only; (10) Kalshi's capture is our own clock.
534 item 3, the plan's five: Q1 PLAY in the staked line, LADDER in a line of its own; Q2 Kalshi's normalised
probability, three legs or two, a row missing a leg has no gap, counted; Q3 a staked row whose reference is not the
books is "reference not the books", counted apart, no bucket; Q4 "stamp after the export", a cause of its own,
counted apart; Q5 rows before the family's first stamped row out, counted once, and a row AFTER it with no stamp in
the "no stamp" bucket with its gap. 539 item 2: "A row whose books' session is not found on the copy is a line of
its own, counted by cause, beside the eight buckets, and is not folded into 'no stamp'." 540 item 2 amends 539's last
sentence: "(a) NFL's SESSION IS TAKEN BY CAPTURE TIME: the latest complete session at or before the page's export ...
The four-place agreement is COUNTED beside it, agree and differ, and decides nothing ... (c) SOCCER stays as built, by
value: its snapshot is written from the close's own fair. (d) The NFL lines say what their stamp is: the oldest over
every row of the fetch, one-sided books among them, a lower bound on the stamp of the rows the page priced." And: "The
stamp from the copy, as #1077 reads it, is the right source until F4 is
on main, and it stays the source after: the receipt reads the season, and old files will never carry F4."

WHAT IT READS (law 1: every key below was read from the code at origin/main c53a6a60):
- THE PAGES: --exports, the directory of closing_*.json and its dated folders <YYYY-MM-DD>/, never latest/, by
  pl_closing_book_age_receipt's own closing_dirs and refusals (that file is loaded by path and its fence reused). A
  page's family is its closing block's (closing.closing_doc, closing.py:1704-1735), else the name's segment
  (redated._FAMILY); FAMILIES "SOCCER" and "NFL" are read, any other counted. Its run start is closing.start, else the
  name's stamp (redated._STAMP); exported_at and git_sha are the file's top-level keys (export.py:85-86,
  nfl_predict.py:401-402), exported_at parsed by redated.as_utc. SOCCER rows are those with competition "PL" and
  season "2026/27" (export.py:334-335; closing.py:132 holds SOCCER to PL); every row of an NFL page is read
  (nfl_predict's rows are nfl_scoped and carry neither key).
- THE LATEST PAGE OF A START (item 6): an exports directory holds one page per start, and a re-page keeps the earlier
  file as logs/<run id>.<name> (closing.py:1738-1778), so a second page of a start reaches this read only from another
  dated folder. Pages are grouped by (family, run start). A page whose run id and exported_at equal an earlier page's
  is that page's COPY: printed, labelled, never counted. Of the rest, the page with the latest exported_at COUNTS; the
  others are labelled "an earlier page of this start" and are out. Where the latest cannot be told (an exported_at
  unreadable, or two pages at the latest exported_at), no page of that start counts: labelled and counted (law 4,
  never guessed). Copies are found first, over every page of a family and run start, an unknown start included. A
  page with no run start is otherwise its own start, labelled, as pl_closing_book_age_receipt keeps it.
- FROM EACH ROW, these keys and no others: match_id, utc_date, home_team, away_team (competition and season on SOCCER);
  the books' fair: SOCCER market.selections.<leg>.fair_prob (export.py:739-745), NFL market.fair_prob.<leg> with
  market.fair_source "1X2" (nfl_predict.py:268-275); Kalshi's: SOCCER market.kalshi.prob.<leg> where
  market.kalshi.normalized is true (export.py:767-826: prob is null on a soccer set missing a leg, raw where a
  two-way set is one-sided, so normalized decides), market.kalshi.status "mismatched" (export.py:474-478) a cause;
  NFL kalshi_prob, the HOME probability normalised over HOME and AWAY, null where a leg is missing
  (nfl_predict.py:352, venue.kalshi_home_prob), input_quality.kalshi "mismatched" (nfl_predict.py:371-375) a cause.
  The receipt computes |fair - kalshi| itself, in pp; it never reads market.kalshi.vs_book_pp or venue_gap_pp.
- THE DESK, these keys of row.desk and no others (DESK_READS): call ("PLAY", "PASS", "LADDER"; desk_policy.py:1407,
  closing.STAKED_CALLS holds PLAY and LADDER, closing.py:232), pick, reference ("books" or "kalshi_only",
  desk_policy.py:2113-2114) and market_ref (the books' fair on the pick, desk_policy.py:483-485). NEVER READ, and never
  read through a whole-dict walk: desk.units, desk.shadow_units, desk.order, desk.exec, desk.ladder_exec,
  desk.value_shadow, desk.market_only_hold, desk.kalshi_only_hold, desk.venue, desk_meta (its unit block), and the
  row's kalshi_bid / kalshi_ask / away_bid / away_ask, exec_cost_*, fee_*, fee_order_contracts, k_track and
  kalshi_legs (NEVER_READ below). Nor any bookmaker name or best price: market.selections.<leg> is read for fair_prob
  alone.
- THE COPY: --db COPY, REQUIRED, behind #688's fence exactly as pl_closing_book_age_receipt applies it (check_copy,
  probe_copy, open_db: mlb_pitchers_gate's mode=ro + immutable=1; addendum 198 item 6(ii)). matches, teams and
  odds_snapshots (match_id, market, selection, devig_prob, captured_at, source, and source_updated_at only where the
  copy has the column: unmapped, found by PRAGMA table_info). The rows read: market "1X2", source "api_football" for
  SOCCER (api_football.py:202) and "api_american_football" for NFL (api_american_football.py:145; its 1X2 snapshots
  are written by service.sync_odds_nfl, service.py:3019-3047, one captured_at per fetch, the session's stamp
  oldest_source_time over the 1X2 rows used).
- THE MATCH: pl_closing_book_age_receipt.find_match (the page's id where the copy agrees on teams by name and
  kickoff, else the one stored match with both names and the kickoff, else not found with the cause).
- THE BOOKS' SESSION: one captured_at; complete when every leg of the family is present, numeric and single-valued.
  SOCCER, BY VALUE (540 item 2(c)): the latest complete session at or before exported_at whose legs rounded to 4
  places equal the page's fair, else the latest earlier one that does (labelled), else "no stored session matches the
  page" (law 4: never forced); its snapshot is written from close_1x2's own fair (service.py:1559-1566), so the page's
  fair equals it. NFL, BY CAPTURE TIME (540 item 2(a)): the latest complete session at or before exported_at. NFL's
  snapshot de-vig is POOLED over every 1X2 offer (MarketSnapshot.average_implied over the summed implied,
  service.py:3019-3036, value.py:71-79), the page's is close_1x2's, de-vigged per complete book and then averaged
  (close.py:105-121, nfl_predict.py:268-275), so the two can part at the fourth place on one fetch; a match by value
  could give a row an earlier session's stamp and bucket. On both, the latest session's four-place agreement with the
  page is COUNTED, agree and differ, and decides nothing. The page's own line_move.venues.book.to_at (inside T-3h only)
  is a cross-check, counted, never the decider. Its STAMP is source_updated_at, the oldest over its rows, unknown when
  the column is absent or any row is NULL (oldest_source_time's rule, #1077's read; F4 is not read, 534 item 3). On
  NFL that is the oldest over every 1X2 row of the fetch, one-sided books among them (service.py:3029-3030): a lower
  bound on the stamp of the rows the page priced (540 item 2(d)), and the NFL lines say so.

THE MEASURES:
- THE STAMP AGE: exported_at minus the session's stamp, in hours: "from the provider's stamp to our closing capture,
  and it is a LOWER bound" (532 item 3). Bucketed half-open [lo, hi). A negative age is "stamp after the export",
  counted apart, no bucket (534 Q4). An unknown stamp is the "no stamp" bucket (534 Q5), its cause printed.
- THE FIRST STAMPED ROW (item 7): per family, the counted row with the earliest exported_at whose session's stamp is
  known (ties by kickoff, then match id), printed. A row exported before it is out, counted once (534 Q5); a row
  whose exported_at is unreadable cannot be placed and is counted under its own cause.
- THE HOME GAP (item 3): on every row in the window with the books' HOME and Kalshi's HOME both priced:
  |fair HOME - Kalshi HOME| x 100, in pp, set in the bucket of the books' session. A row whose books' session is not
  found on the copy is a line of its own, "books' session not found", counted by cause beside the eight buckets, and
  is not folded into "no stamp", which holds a session found without the source's stamp (539 item 2: "two different
  unknowns"). A row with no gap is counted by cause.
- THE STAKED ROWS (item 3, 534 Q1, Q3): desk.call PLAY in the staked line, LADDER in a line of its own: the pick's
  gap |fair pick - Kalshi pick| (NFL's AWAY is 1 - kalshi_prob: the pair is normalised), and the bucket of its
  reference: the books' session's where desk.reference is "books"; "reference not the books" where it is not
  (counted apart, no bucket); desk.market_ref is checked against the page's fair on the pick at 4 places, agree or
  differ counted, never dropped.

Counts and gaps in pp only: no threshold, no verdict, no bookmaker name, no amount (532 item 4).
No provider call, no network, nothing written (the copy is opened immutable=1; no bytecode is written).

Run:  python3 scripts/closing_book_gap_receipt.py --exports DIR --db COPY [--from INSTANT] [--through INSTANT]
Exit 0 done; 2 refused, nothing read. The last line is CLOSING-BOOK-GAP-RECEIPT {json}.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True      # nothing written: no __pycache__ for this file or what it loads

import argparse  # noqa: E402
import importlib.util  # noqa: E402
import json  # noqa: E402
from collections import Counter  # noqa: E402
from datetime import datetime  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.walters import redated  # noqa: E402   (imports no src.db module)

TAG = "CLOSING-BOOK-GAP-RECEIPT"
MARKET = "1X2"
DP = 4                                       # export.py:742 and nfl_predict.py:273: fair_prob rounded to 4 places
SOCCER_COMPETITION, SOCCER_SEASON = "PL", "2026/27"
FAMILIES = {
    # match: how the books' session is taken (540 item 2, amending 539 item 2's last sentence). SOCCER "validated", by
    # value: its snapshot is written from close_1x2's own fair (service.py:1559-1566), the page's fair (export.py:739-
    # 745). NFL "capture", BY CAPTURE TIME: its snapshot's de-vig is POOLED over every 1X2 offer
    # (MarketSnapshot.average_implied over the summed implied, service.py:3019-3036, value.py:71-79), the page's is
    # close_1x2's, de-vigged per complete book and averaged (close.py:105-121, nfl_predict.py:268-275); the two can part
    # at the fourth place on one fetch, and a match by value could give a row an earlier session's stamp and bucket
    "SOCCER": {"source": "api_football", "legs": ("HOME", "DRAW", "AWAY"), "match": "validated"},
    "NFL": {"source": "api_american_football", "legs": ("HOME", "AWAY"), "match": "capture"},
}
VALIDATED = "agrees with the page at 4 places"
UNVALIDATED = "differs from the page at 4 places"
NFL_STAMP = ("THE NFL STAMP (540 item 2(d)): the oldest source_updated_at over every 1X2 row of the fetch, one-sided "
             "books among them (service.py:3029-3030, oldest_source_time over the rows used): a LOWER BOUND on the stamp "
             "of the rows the page priced (close.book_stamp reads the complete books only)")
STAKED = (("PLAY", "PLAY (the staked line)"), ("LADDER", "LADDER (a line of its own)"))
DESK_READS = ("call", "pick", "reference", "market_ref")
NEVER_READ = ("desk.units", "desk.shadow_units", "desk.order", "desk.exec", "desk.ladder_exec", "desk.value_shadow",
              "desk.market_only_hold", "desk.kalshi_only_hold", "desk.venue", "desk_meta", "kalshi_bid", "kalshi_ask",
              "away_bid", "away_ask", "exec_cost_*", "fee_*", "fee_order_contracts", "k_track", "kalshi_legs",
              "market.selections.<leg>.best_bookmaker", "market.selections.<leg>.best_price")
BUCKETS = ((0.0, 1.0, "under 1 h"), (1.0, 2.0, "1-2 h"), (2.0, 3.0, "2-3 h"), (3.0, 6.0, "3-6 h"),
           (6.0, 12.0, "6-12 h"), (12.0, 24.0, "12-24 h"), (24.0, None, "24 h or more"))
NO_STAMP = "no stamp"
AFTER = "stamp after the export"
NOT_FOUND_SESSION = "books' session not found"
NO_COLUMN = "odds_snapshots.source_updated_at absent on this copy"
UNSTAMPED = "the session's rows unstamped (NULL)"
PARTLY = "the session's rows partly stamped"
NO_EXPORTED = "the page has no readable exported_at"
NO_SESSION = "no complete stored session at or before the export"
NO_MATCH = "no stored session matches the page"
EARLIER = "page matches an earlier session"
BEFORE_FIRST = "exported before the family's first stamped row"
NOT_BOOKS = "reference not the books"
READS = {"matches": {"id", "home_team_id", "away_team_id", "utc_date"},
         "teams": {"id", "name"},
         "odds_snapshots": {"match_id", "market", "selection", "devig_prob", "captured_at", "source"}}
STAMP_TEXT = ("the newest that any quote in the answer can be; a quote may be older; never the time of a quote. "
              "NULL = unknown, never fresh")    # schema.py (addendum 32 items 3-4), as pl_closing_book_age_receipt

DEFINITIONS = (
    "THE BOOKS' SESSION: a 1X2 snapshot session (one captured_at = one fetch; api_football for SOCCER, "
    "api_american_football for NFL). SOCCER, by value: the latest complete one at or before the page's exported_at "
    "whose legs rounded to 4 places equal the page's fair; else the latest earlier one that does (labelled); else 'no "
    "stored session matches the page' (counted, never forced). NFL, by capture time (540 item 2(a)): the latest "
    "complete one at or before exported_at (its snapshot de-vig is pooled over every offer, the page's averaged per "
    "complete book). On both, the latest session's four-place agreement with the page is counted and decides nothing. "
    "Its stamp: source_updated_at, the oldest over its rows, unknown if any row is (\"" + STAMP_TEXT + "\"); on NFL "
    "over every 1X2 row of the fetch, one-sided books among them: a lower bound (540 item 2(d)). A row with no session "
    "found is a line of its own, never 'no stamp' (539 item 2).",
    "THE STAMP AGE: exported_at minus the session's stamp, in hours, from the provider's stamp to our closing capture: "
    "a LOWER bound (532 item 3). Buckets half-open: under 1 h · 1-2 · 2-3 · 3-6 · 6-12 · 12-24 · 24 h or more · no "
    "stamp (532 item 4 #5); a negative age is 'stamp after the export', counted apart, no bucket (534 Q4).",
    "THE HOME GAP: |books' fair HOME - Kalshi's HOME| x 100, in pp, on every row with both priced: SOCCER "
    "market.selections.HOME.fair_prob against market.kalshi.prob.HOME where market.kalshi.normalized; NFL "
    "market.fair_prob.HOME (fair_source 1X2) against kalshi_prob (normalised over HOME and AWAY). Kalshi's price is "
    "our own capture (532 item 4 #10).",
    "THE WINDOW: per family, from its first stamped row (532 item 4 #7): rows exported before it are out, counted once; "
    "after it, a row with no stamp is in the 'no stamp' bucket with its gap (534 Q5).",
    "THE STAKED ROWS: desk.call PLAY in the staked line, LADDER in a line of its own (534 Q1): the pick's gap, and the "
    "bucket of its reference (the books' session where desk.reference is 'books'; 'reference not the books' counted "
    "apart, 534 Q3). Only desk.call, pick, reference and market_ref are read.",
    "THE LATEST PAGE OF A START (532 item 4 #6): one page per (family, run start) counts, the latest by exported_at; "
    "earlier pages and copies are printed, labelled and out.")


class Refused(Exception):
    """A refused read: exit 2, nothing read."""


_MODS: dict = {}


def _plr():
    """scripts/pl_closing_book_age_receipt.py by path: its fence (check_copy, probe_copy, open_db, columns), its pages'
    folders (closing_dirs, bounds) and find_match; stdlib and redated only at its module import."""
    if "plr" not in _MODS:
        spec = importlib.util.spec_from_file_location("pl_closing_book_age_receipt_for_532",
                                                      Path(__file__).resolve().parent / "pl_closing_book_age_receipt.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _MODS["plr"] = mod
    return _MODS["plr"]


def _call(fn, *a):
    """A pl_closing_book_age_receipt refusal is this receipt's: exit 2, nothing read."""
    plr = _plr()
    try:
        return fn(*a)
    except plr.Refused as e:
        raise Refused(str(e)) from None


def _d(v) -> dict:
    return v if isinstance(v, dict) else {}


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf") \
        else None


def _family(doc_block: dict, name: str):
    fam = doc_block.get("family")
    if not isinstance(fam, str) or not fam:
        named = redated._FAMILY.match(name)
        fam = named.group(1) if named else None
    return fam


def _is_row(fam: str, r) -> bool:
    if not isinstance(r, dict):
        return False
    if fam == "SOCCER":
        return r.get("competition") == SOCCER_COMPETITION and r.get("season") == SOCCER_SEASON
    return True


# ---- the pages --------------------------------------------------------------------------------------------------

def read_pages(exports: Path, lo=None, hi=None) -> dict:
    """Every SOCCER and NFL closing page of the folders closing_dirs names, in the bound, with its rows; then the
    latest page of each (family, run start) marked as the one that counts (item 6)."""
    plr = _plr()
    if not exports.is_dir():
        raise Refused(f"REFUSED: --exports {exports}: not a directory; nothing read")
    if "latest" in (exports.name, exports.resolve().name):
        raise Refused(f"REFUSED: --exports {exports}: a latest/ folder (resolves to {exports.resolve()}); latest/ is "
                      "never read (its files are copies of a dated folder's newest); pass its parent; nothing read")
    dirs = plr.closing_dirs(exports)
    for sub, _pre in dirs[1:]:
        if sub.resolve().name == "latest":
            raise Refused(f"REFUSED: --exports {exports}: the dated folder {sub.name}/ resolves to {sub.resolve()}, a "
                          "latest/ folder; latest/ is never read; nothing read")
    qb = plr._qb()
    pages, bad = [], []
    n = Counter()
    for sub, pre in dirs:
        for p in sorted(sub.glob(redated.CLOSING_GLOB)):
            try:
                doc = json.loads(p.read_text())
                if not isinstance(doc, dict):
                    raise TypeError("page not an object")
                block = doc.get("closing") or {}
                if not isinstance(block, dict):
                    raise TypeError("closing block not an object")
                preds = doc.get("predictions") or []
                if not isinstance(preds, list):
                    raise TypeError("predictions not a list")
            except (OSError, ValueError, AttributeError, TypeError, RecursionError):
                bad.append(pre + p.name)
                continue
            n["files"] += 1
            run = redated.as_utc(block.get("start"))
            stamp = redated._STAMP.search(p.name)
            bad_stamp = None
            if run is None and stamp:
                try:
                    run = datetime.strptime(stamp.group(1), "%Y-%m-%dT%H%M")
                except ValueError:
                    bad_stamp = stamp.group(1)
                    n["stamp_invalid"] += 1
            fam = _family(block, p.name)
            if fam not in FAMILIES:
                n["other_family"] += 1
                continue
            inb = qb.in_bound(run, lo, hi)
            if inb is not True:
                n[("outside" if inb is False else "run_unknown") + ":" + fam] += 1
                continue
            rows = [r for r in preds if _is_row(fam, r)]
            n["other_rows:" + fam] += sum(1 for r in preds if not _is_row(fam, r))
            exp_raw = doc.get("exported_at")
            pages.append({"file": pre + p.name, "family": fam, "run": run, "run_id": block.get("run_id"),
                          "exported_raw": exp_raw if isinstance(exp_raw, str) else None,
                          "exported_at": redated.as_utc(exp_raw) if isinstance(exp_raw, str) else None,
                          "git_sha": doc.get("git_sha") if isinstance(doc.get("git_sha"), str) else None,
                          "rows": rows, "copy_of": None, "counts": False, "label": "", "bad_stamp": bad_stamp,
                          "seq": len(pages)})
    # read order breaks a tie: the directory itself before its dated folders, then the folders in name order
    pages.sort(key=lambda g: (g["family"], g["run"] or datetime.min, g["exported_at"] or datetime.min, g["seq"]))
    # COPIES first, over every page of a family and its run start (an unknown start included, as
    # pl_closing_book_age_receipt groups them): same run id and exported_at, both read, is one page twice
    seen: dict = {}
    for g in pages:
        if g["run_id"] is None or g["exported_raw"] is None:
            continue
        twin = seen.get((g["family"], g["run"], json.dumps(g["run_id"], sort_keys=True, default=str),
                         g["exported_raw"]))
        if twin is not None:
            g["copy_of"] = twin["file"]
            g["label"] = f"a COPY of {twin['file']} (same run id and exported_at): printed, not counted"
        else:
            seen[(g["family"], g["run"], json.dumps(g["run_id"], sort_keys=True, default=str),
                  g["exported_raw"])] = g
    groups: dict = {}
    for i, g in enumerate(pages):
        if g["copy_of"] is not None:
            continue
        key = (g["family"], g["run"]) if g["run"] is not None else (g["family"], None, i)
        groups.setdefault(key, []).append(g)
    for key, originals in groups.items():
        if len(originals) == 1:
            originals[0]["counts"] = True
            if key[1] is None:
                originals[0]["label"] = "RUN START UNKNOWN: counted as a start of its own"
            continue
        exps = [g["exported_at"] for g in originals]
        if any(e is None for e in exps) or exps.count(max(exps)) > 1:
            n["undecided_starts:" + key[0]] += 1
            for g in originals:
                g["label"] = (f"RE-PAGED START, {len(originals)} pages, THE LATEST CANNOT BE TOLD (an exported_at "
                              "unreadable, or two pages at the latest exported_at): no page of this start counts")
            continue
        latest = max(originals, key=lambda g: g["exported_at"])
        for g in originals:
            if g is latest:
                g["counts"] = True
                g["label"] = f"RE-PAGED START: the latest of {len(originals)} pages, the one that counts"
            else:
                g["label"] = f"RE-PAGED START: an earlier page of {len(originals)}, labelled and out"
    for g in pages:
        if g["bad_stamp"]:
            g["label"] += (" · RUN START UNKNOWN: no readable closing.start, and the name's stamp "
                           f"{g['bad_stamp']} is not a valid date/time")
    return {"pages": pages, "unreadable": bad, "counts": dict(n), "dir": exports.resolve(), "dated": len(dirs) - 1,
            "lo": lo, "hi": hi}


# ---- the copy ---------------------------------------------------------------------------------------------------

def check_schema(s) -> bool:
    """The READS tables and columns, a missing one refused (law 1); whether odds_snapshots has source_updated_at."""
    plr = _plr()
    for t, cols in READS.items():
        got = plr.columns(s, t)
        if not got:
            raise Refused(f"REFUSED: table {t} not in the database (law 1); nothing read")
        if cols - got:
            raise Refused(f"REFUSED: columns {', '.join(sorted(cols - got))} not in {t} (law 1); nothing read")
    return "source_updated_at" in plr.columns(s, "odds_snapshots")


def read_sessions(s, mid: int, fam: str, has_stamp: bool) -> dict:
    """The game's 1X2 snapshot sessions of the family's books source, oldest first."""
    from sqlalchemy import text
    legs = FAMILIES[fam]["legs"]
    cols = "captured_at, selection, devig_prob" + (", source_updated_at" if has_stamp else "")
    q = text(f"SELECT {cols} FROM odds_snapshots WHERE match_id = :m AND source = :src AND market = :mk "
             "ORDER BY captured_at, id")
    by: dict = {}
    unreadable = 0
    for row in s.execute(q, {"m": mid, "src": FAMILIES[fam]["source"], "mk": MARKET}):
        at = redated.as_utc(row[0])
        if at is None:
            unreadable += 1
            continue
        g = by.setdefault(at, {"at": at, "legs": {}, "conflict": False, "stamps": []})
        sel, val = row[1], row[2]
        if sel in g["legs"] and g["legs"][sel] != val:
            g["conflict"] = True
        g["legs"][sel] = val
        g["stamps"].append(redated.as_utc(row[3]) if has_stamp else None)
    out = []
    for at in sorted(by):
        g = by[at]
        vals = [_num(g["legs"].get(k)) for k in legs]
        g["complete"] = set(legs) <= set(g["legs"]) and all(v is not None for v in vals) and not g["conflict"]
        g["fair4"] = tuple(round(v, DP) for v in vals) if g["complete"] else None
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


# ---- one row ----------------------------------------------------------------------------------------------------

def page_fair(fam: str, r: dict) -> tuple[dict | None, str | None]:
    """({leg: fair} over the family's legs, None) or (None, the cause)."""
    m = r.get("market")
    if not isinstance(m, dict):
        return None, "no books' market on the row"
    legs = FAMILIES[fam]["legs"]
    if fam == "SOCCER":
        sel = _d(m.get("selections"))
        got = {k: _num(_d(sel.get(k)).get("fair_prob")) for k in legs}
    else:
        if m.get("fair_source") != "1X2":
            return None, f"the books' fair is not the 1X2 consensus (fair_source {m.get('fair_source')!r})"
        fp = _d(m.get("fair_prob"))
        got = {k: _num(fp.get(k)) for k in legs}
    if any(v is None for v in got.values()):
        return None, "the books' fair not priced on every leg"
    return got, None


def page_kalshi(fam: str, r: dict) -> tuple[dict | None, str | None]:
    """({leg: Kalshi's normalised probability}, None) or (None, the cause). NFL's AWAY is 1 - kalshi_prob."""
    if fam == "SOCCER":
        k = _d(r.get("market")).get("kalshi")
        if not isinstance(k, dict):
            return None, "no Kalshi price on the row"
        if k.get("status") == "mismatched":
            return None, "Kalshi's legs mismatched (no price)"
        if k.get("normalized") is not True:
            return None, "Kalshi not priced on every leg (not normalised)"
        prob = _d(k.get("prob"))
        got = {leg: _num(prob.get(leg)) for leg in FAMILIES[fam]["legs"]}
        if any(v is None for v in got.values()):
            return None, "Kalshi's normalised price not a number on a leg"
        return got, None
    if _d(r.get("input_quality")).get("kalshi") == "mismatched":
        return None, "Kalshi's legs mismatched (no price)"
    h = _num(r.get("kalshi_prob"))
    if h is None:
        return None, ("Kalshi not priced on both legs (kalshi_prob null)" if r.get("kalshi_prob") is None else
                      "kalshi_prob not a number")
    return {"HOME": h, "AWAY": 1.0 - h}, None


def read_desk(r: dict) -> dict | None:
    """Only DESK_READS of row.desk, each by name: nothing else of the block is touched."""
    d = r.get("desk")
    if not isinstance(d, dict):
        return None
    return {k: d.get(k) for k in DESK_READS}


def bucket(h: float | None) -> str:
    if h is None:
        return NO_STAMP
    if h < 0:
        return AFTER
    for lo, hi, name in BUCKETS:
        if h >= lo and (hi is None or h < hi):
            return name
    raise ValueError(h)


def measure(page: dict, r: dict, s, has_stamp: bool) -> dict:
    """One row: its books' session and stamp age, its HOME gap and its Desk call (or the cause of each none)."""
    fam = page["family"]
    mid, how = _plr().find_match(s, r)
    x = {"family": fam, "page": page["file"], "exported_at": page["exported_at"], "match_id": r.get("match_id"),
         "kickoff": redated.as_utc(r.get("utc_date")), "home": r.get("home_team"), "away": r.get("away_team"),
         "how": how, "session": None, "session_why": None, "label": None, "stamp": None, "stamp_why": None,
         "age_h": None, "bucket": None, "gap": None, "gap_why": None, "fair": None, "kalshi": None, "desk": None,
         "unreadable": 0, "match": None, "line_move": "absent", "run": page["run"]}
    x["fair"], fair_why = page_fair(fam, r)
    x["kalshi"], kal_why = page_kalshi(fam, r)
    x["desk"] = read_desk(r)
    if x["fair"] is not None and x["kalshi"] is not None:
        x["gap"] = round(abs(x["fair"]["HOME"] - x["kalshi"]["HOME"]) * 100, 4)   # 4-place inputs: exact in pp
    else:
        x["gap_why"] = fair_why or kal_why
    exp = page["exported_at"]
    if mid is None:
        x["session_why"] = how
    elif exp is None:
        x["session_why"] = NO_EXPORTED
    elif x["fair"] is None:
        x["session_why"] = fair_why
    else:
        ss = read_sessions(s, mid, fam, has_stamp)
        x["unreadable"] = ss["unreadable"]
        legs = FAMILIES[fam]["legs"]
        want = tuple(x["fair"][k] for k in legs)
        upto = [g for g in ss["sessions"] if g["complete"] and g["at"] <= exp]
        idx = None
        if not upto:
            x["session_why"] = NO_SESSION
        else:
            # beside the session, counted and deciding nothing: whether the latest complete session at or before the
            # export equals the page at 4 places (540 item 2(a): agree and differ, counted)
            x["match"] = VALIDATED if upto[-1]["fair4"] == want else UNVALIDATED
            if FAMILIES[fam]["match"] == "capture":       # NFL, 540 item 2(a): the latest complete session
                idx = len(upto) - 1
                x["label"] = "the latest complete session at or before the export, by capture time (540 item 2(a))"
            else:                                         # SOCCER, by value (540 item 2(c))
                idx = next((i for i in range(len(upto) - 1, -1, -1) if upto[i]["fair4"] == want), None)
                if idx is None:
                    x["session_why"] = NO_MATCH
                else:
                    x["label"] = "the latest complete session" if idx == len(upto) - 1 else \
                        f"{EARLIER} (captured {upto[idx]['at']:%Y-%m-%d %H:%M:%S}Z)"
        if idx is not None:
            p = upto[idx]
            x["session"] = p["at"]
            x["stamp"], x["stamp_why"] = p["stamp"], p["stamp_why"]
            if p["stamp"] is not None:
                x["age_h"] = (exp - p["stamp"]).total_seconds() / 3600
            x["bucket"] = bucket(x["age_h"])
            x["line_move"] = line_move_check(r, p["at"])
    return x


def line_move_check(r: dict, at: datetime) -> str:
    """The page's own line_move.venues.book.to_at (the latest book snapshot the export saw, inside T-3h only;
    line_move.py:90-112) against the session the receipt took: a cross-check, never the decider."""
    book = _d(_d(_d(r.get("line_move")).get("venues")).get("book"))
    raw = book.get("to_at")
    if not isinstance(raw, str):
        return "absent"
    return "agree" if redated.as_utc(raw) == at else "differ"


def pick_line(x: dict) -> dict:
    """A staked row's pick: its gap, its reference's bucket, and the market_ref check."""
    d = x["desk"] or {}
    pick = d.get("pick")
    out = {"call": d.get("call"), "pick": pick, "gap": None, "gap_why": None, "ref": None, "ref_check": None}
    legs = FAMILIES[x["family"]]["legs"]
    if pick not in legs:
        out["gap_why"] = f"the pick {pick!r} is not a leg of the board"
    elif x["fair"] is None or x["kalshi"] is None:
        out["gap_why"] = x["gap_why"]
    else:
        out["gap"] = round(abs(x["fair"][pick] - x["kalshi"][pick]) * 100, 4)
    ref = d.get("reference")
    if ref != "books":
        out["ref"] = NOT_BOOKS if ref is not None else NOT_BOOKS + " (desk.reference null)"
    elif x["bucket"] is None:
        out["ref"] = f"{NOT_FOUND_SESSION} ({x['session_why']})"
    else:
        out["ref"] = x["bucket"]
    mr = _num(d.get("market_ref"))
    if ref != "books":
        out["ref_check"] = "not checked (reference not the books)"
    elif mr is None:
        out["ref_check"] = "desk.market_ref absent"
    elif x["fair"] is None or pick not in legs:
        out["ref_check"] = "no page fair on the pick"
    else:
        out["ref_check"] = "agree" if round(mr, DP) == round(x["fair"][pick], DP) else "differ"
    return out


# ---- the console ------------------------------------------------------------------------------------------------

def dist(xs: list) -> dict:
    from src.walters.venue_quote_age import pct
    d = {"n": len(xs)}
    if xs:
        d.update(min=min(xs), max=max(xs), **{k: pct(xs, q) for k, q in _plr()._bsa().QS})
    return d


def _dist_text(d: dict) -> str:
    if not d["n"]:
        return "n 0"
    return (f"n {d['n']} · min {d['min']:.2f} · " + " · ".join(f"{k} {d[k]:.2f}" for k, _ in _plr()._bsa().QS)
            + f" · max {d['max']:.2f} (pp)")


def _t(d: datetime | None) -> str:
    return f"{d:%Y-%m-%d %H:%M:%S}Z" if d else "—"


def _order(x: dict):
    return (x["exported_at"], x["kickoff"] or datetime.max, str(x["match_id"]))


def window(rows: list) -> tuple[dict | None, list, list]:
    """(the family's first stamped row, the rows in the window, the rows before it). A row is placed by its page's
    exported_at; a row whose exported_at is unreadable is placed by its page's run start against the first stamped
    row's, and stays in where neither can say (counted under its cause, never dropped)."""
    stamped = [x for x in rows if x["stamp"] is not None and x["exported_at"] is not None]
    if not stamped:
        return None, [], list(rows)
    first = min(stamped, key=_order)

    def is_before(x):
        if x["exported_at"] is not None:
            return x["exported_at"] < first["exported_at"]
        return x["run"] is not None and first["run"] is not None and x["run"] < first["run"]
    return first, [x for x in rows if not is_before(x)], [x for x in rows if is_before(x)]


def family_report(fam: str, rows: list, L: list) -> dict:
    first, inside, before = window(rows)
    L.append(f"\n==== {fam} ====")
    if first is None:
        L.append(f"FIRST STAMPED ROW: none on the {len(rows)} counted row(s): no row's books' session carries a "
                 "stamp, so no row enters the window (532 item 4 #7); every row is counted out")
        L.append(f"ROWS: counted {len(rows)} · out, no stamped row in the record {len(rows)}")
        return {"rows": len(rows), "before_first": 0, "in_window": 0, "first": None,
                "out_no_stamped_row": len(rows)}
    out = {"rows": len(rows), "before_first": len(before), "in_window": len(inside)}
    L.append(f"FIRST STAMPED ROW (532 item 4 #7): page {first['page']} · exported_at {_t(first['exported_at'])} · "
             f"kickoff {_t(first['kickoff'])} · match {first['match_id']} · stamp {_t(first['stamp'])}")
    out["first"] = {"page": first["page"], "exported_at": _t(first["exported_at"]), "kickoff": _t(first["kickoff"]),
                    "match_id": first["match_id"], "stamp": _t(first["stamp"])}
    games = Counter(json.dumps(x["match_id"], default=str) for x in inside)
    out["games_on_more_than_one_page"] = sum(1 for v in games.values() if v > 1)
    unplaced = sum(1 for x in inside if x["exported_at"] is None and (x["run"] is None or first["run"] is None))
    out["unplaced"] = unplaced
    L.append(f"ROWS: counted {len(rows)} · {BEFORE_FIRST} {len(before)} (out, counted once) · in the window "
             f"{len(inside)} (of which neither exported_at nor run start could place {unplaced}, kept) · games on "
             f"more than one counted page {out['games_on_more_than_one_page']} (each row counted: one closing row "
             "each)")
    m = Counter(x["match"] for x in inside if x["match"] is not None)
    out["session_match"] = dict(m)
    if FAMILIES[fam]["match"] == "capture":
        L.append("THE BOOKS' SESSION, taken by capture time (540 item 2(a)): the latest complete session at or before "
                 "the export, against the page's fair (counted, deciding nothing): "
                 + (" · ".join(f"{k} {v}" for k, v in sorted(m.items())) or "none"))
        L.append(NFL_STAMP)
    else:
        L.append("THE BOOKS' SESSION, matched by value at 4 places (540 item 2(c)); beside it, the latest complete "
                 "session at or before the export against the page's fair (counted, deciding nothing): "
                 + (" · ".join(f"{k} {v}" for k, v in sorted(m.items())) or "none"))
    lm = Counter(x["line_move"] for x in inside if x["session"] is not None)
    out["line_move"] = dict(lm)
    L.append("LINE_MOVE CROSS-CHECK (the page's line_move.venues.book.to_at, inside T-3h only, against the session "
             "taken): " + (" · ".join(f"{k} {v}" for k, v in sorted(lm.items())) or "none"))
    names = [b[2] for b in BUCKETS] + [NO_STAMP]
    gapped = [x for x in inside if x["gap"] is not None]
    nogap = Counter(x["gap_why"] for x in inside if x["gap"] is None)
    L.append(f"THE HOME GAP |books' fair - Kalshi| (pp), by the stamp-age bucket of the books' session: rows with a "
             f"gap {len(gapped)} of {len(inside)}")
    by_b = {}
    for name in names:
        by_b[name] = dist([x["gap"] for x in gapped if x["bucket"] == name])
        L.append(f"    {name}: {_dist_text(by_b[name])}")
    by_b[AFTER] = dist([x["gap"] for x in gapped if x["bucket"] == AFTER])
    L.append(f"    {AFTER} (counted apart, no bucket): {_dist_text(by_b[AFTER])}")
    nf = [x for x in gapped if x["bucket"] is None]
    nf_why = Counter(x["session_why"] for x in nf)
    by_b[NOT_FOUND_SESSION] = {**dist([x["gap"] for x in nf]), "why": dict(nf_why)}
    L.append(f"    {NOT_FOUND_SESSION} (a line of its own, beside the buckets; 539 item 2, 540 item 2(e)): "
             f"{_dist_text(by_b[NOT_FOUND_SESSION])}"
             + (" · " + "; ".join(f"{w} {v}" for w, v in sorted(nf_why.items())) if nf_why else ""))
    ns_why = Counter(x["stamp_why"] for x in gapped if x["bucket"] == NO_STAMP)
    L.append(f"    {NO_STAMP}, by cause: " + ("; ".join(f"{w} {v}" for w, v in sorted(ns_why.items())) or "none"))
    L.append("    rows with no gap, by cause: " + ("; ".join(f"{w} {v}" for w, v in sorted(nogap.items())) or "none"))
    all_b = Counter(x["bucket"] if x["bucket"] is not None else NOT_FOUND_SESSION for x in inside)
    L.append("    every row in the window, by bucket (gap or none): " + " · ".join(
        f"{name} {all_b.get(name, 0)}" for name in names + [AFTER, NOT_FOUND_SESSION]))
    out.update(home_gap=by_b, no_gap=dict(nogap), no_stamp_why=dict(ns_why), by_bucket_all=dict(all_b))
    staked = {}
    for call, title in STAKED:
        xs = [x for x in inside if (x["desk"] or {}).get("call") == call]
        picks = [(x, pick_line(x)) for x in xs]
        L.append(f"{title}: rows {len(xs)}")
        refs = Counter(pl["ref"] for _x, pl in picks)
        chk = Counter(pl["ref_check"] for _x, pl in picks)
        why = Counter(pl["gap_why"] for _x, pl in picks if pl["gap"] is None)
        per = {}
        for name in names + [AFTER]:
            g = [pl["gap"] for _x, pl in picks if pl["ref"] == name and pl["gap"] is not None]
            per[name] = {"rows": refs.get(name, 0), **dist(g)}
            L.append(f"    reference in {name}" + (" (counted apart, no bucket)" if name == AFTER else "")
                     + f": rows {refs.get(name, 0)} · the pick's gap {_dist_text(per[name])}")
        rest = {k: v for k, v in refs.items() if k not in per}
        for k in sorted(rest):
            g = [pl["gap"] for _x, pl in picks if pl["ref"] == k and pl["gap"] is not None]
            per[k] = {"rows": rest[k], **dist(g)}
            L.append(f"    {k} (counted apart, no bucket): rows {rest[k]} · the pick's gap {_dist_text(per[k])}")
        L.append("    the pick's gap absent, by cause: " + ("; ".join(f"{w} {v}" for w, v in sorted(why.items()))
                                                          or "none"))
        L.append("    desk.market_ref against the page's fair on the pick (4 places): "
                 + ("; ".join(f"{w} {v}" for w, v in sorted(chk.items())) or "none"))
        staked[call] = {"rows": len(xs), "by_reference": per, "no_gap": dict(why), "market_ref": dict(chk)}
    out["staked"] = staked
    calls = Counter(str((x["desk"] or {}).get("call")) if x["desk"] is not None else "(no desk block)"
                    for x in inside)
    L.append("CALLS in the window (desk.call): " + " · ".join(f"{k} {v}" for k, v in sorted(calls.items())))
    out["calls"] = dict(calls)
    return out


def report(pop: dict, s, has_stamp: bool, hdr: dict) -> tuple[list[str], dict]:
    qb = _plr()._qb()
    L = [f"CLOSING BOOK-GAP RECEIPT (ARCHITECT 2026-11-25 10:47 ET, addendum 532 item 4, ruled by 534 item 3; Refs "
         f"#348) · READ-ONLY · no provider call, no network, nothing written · database {hdr['db']} · closing pages "
         f"{pop['dir']} (--exports {hdr['exports']}; closing_*.json there and in its dated folders <YYYY-MM-DD>/ "
         f"{pop['dated']}, never latest/; families SOCCER ({SOCCER_COMPETITION} {SOCCER_SEASON}) and NFL) · this run: "
         f"{qb.run_label(pop['lo'], pop['hi'])[1]} · --from {qb._z(pop['lo']) if pop['lo'] else '—'} · --through "
         f"{qb._z(pop['hi']) if pop['hi'] else '—'}",
         "odds_snapshots.source_updated_at: " + ("present on this copy" if has_stamp else
                                                 f"ABSENT ({NO_COLUMN}): every stamp is unknown, so no family has a "
                                                 "first stamped row and every row is counted out (532 item 4 #7)"),
         "NEVER READ: " + ", ".join(NEVER_READ) + " (no order, unit, contract count or amount; 532 item 4)",
         *DEFINITIONS]
    c = pop["counts"]
    L.append(f"FILES: closing files read {c.get('files', 0)} · unreadable {len(pop['unreadable'])}"
             + (f" ({', '.join(pop['unreadable'])})" if pop["unreadable"] else "")
             + f" · name stamps not a valid date/time {c.get('stamp_invalid', 0)} · another family's "
             f"{c.get('other_family', 0)} · "
             + " · ".join(f"{fam}: outside the bound {c.get('outside:' + fam, 0)}, run start unknown under a bound "
                          f"{c.get('run_unknown:' + fam, 0)}, other rows {c.get('other_rows:' + fam, 0)}, re-paged "
                          f"starts whose latest page cannot be told {c.get('undecided_starts:' + fam, 0)}"
                          for fam in FAMILIES))
    rows = {fam: [] for fam in FAMILIES}
    for g in pop["pages"]:
        L.append(f"\n== {g['family']} page {g['file']} · run start {_t(g['run'])} · exported_at {g['exported_raw']} · "
                 f"git_sha {g['git_sha'][:8] if g['git_sha'] else '—'} · rows {len(g['rows'])} · "
                 + ("COUNTED" if g["counts"] else "NOT COUNTED") + (f" · {g['label']}" if g["label"] else ""))
        if not g["counts"]:
            continue
        for r in g["rows"]:
            x = measure(g, r, s, has_stamp)
            rows[g["family"]].append(x)
            d = x["desk"]
            L.append(f"  {_t(x['kickoff'])} · match {x['match_id']} {x['home']} v {x['away']} · on the copy: "
                     f"{x['how']}")
            L.append("    books' session " + (f"captured {_t(x['session'])} ({x['label']}) · stamp "
                                              + (_t(x["stamp"]) if x["stamp"] else f"unknown ({x['stamp_why']})")
                                              + (f" · age {x['age_h']:.2f} h" if x["age_h"] is not None else "")
                                              + f" · bucket {x['bucket']}"
                                              + (f" · {x['match']}" if x["match"] else "")
                                              + f" · line_move book to_at {x['line_move']}"
                                              if x["session"] else f"not found: {x['session_why']}"
                                              + (f" · {x['match']}" if x["match"] else ""))
                     + (f" · snapshot rows with an unreadable captured_at {x['unreadable']}" if x["unreadable"]
                        else ""))
            L.append("    HOME gap " + (f"{x['gap']:.2f} pp" if x["gap"] is not None else f"none ({x['gap_why']})")
                     + " · desk " + ("(no desk block)" if d is None else
                                     f"call {d['call']} · pick {d['pick']} · reference {d['reference']}"))
    fams = {}
    for fam in FAMILIES:
        fams[fam] = family_report(fam, rows[fam], L)
    summary = {"families": fams, "stamp_column": has_stamp, "files": c, "unreadable": pop["unreadable"],
               "pages": {fam: {"read": sum(1 for g in pop["pages"] if g["family"] == fam),
                               "counted": sum(1 for g in pop["pages"] if g["family"] == fam and g["counts"]),
                               "copies": sum(1 for g in pop["pages"] if g["family"] == fam and g["copy_of"])}
                         for fam in FAMILIES},
               "exports_dir": str(pop["dir"]), "db": hdr["db"],
               "from": qb._z(pop["lo"]) if pop["lo"] else None, "through": qb._z(pop["hi"]) if pop["hi"] else None}
    L.append(TAG + " " + json.dumps(summary, sort_keys=True, default=str))
    return L, summary


def main(argv=None, echo=print) -> int:
    ap = argparse.ArgumentParser(description="addendum 532 item 4 (Refs #348): the closing book-gap receipt")
    ap.add_argument("--exports", required=True,
                    help="the closing pages: a directory of closing_*.json and its dated folders <YYYY-MM-DD>/; "
                         "latest/ never read")
    ap.add_argument("--db", default=None,
                    help="REQUIRED: a .backup copy OUTSIDE data/, opened mode=ro + immutable=1 (addendum 198 item "
                         "6(ii)); without it, exit 2, nothing read")
    ap.add_argument("--from", dest="from_", default=None, metavar="INSTANT",
                    help="bound the closing run's start, INCLUSIVE, a UTC instant YYYY-MM-DDTHH:MM:SSZ")
    ap.add_argument("--through", default=None, metavar="INSTANT",
                    help="bound the closing run's start, EXCLUSIVE, a UTC instant YYYY-MM-DDTHH:MM:SSZ")
    a = ap.parse_args(argv)
    try:
        plr = _plr()
        path = _call(plr.check_copy, a.db)            # first: without a copy nothing is read
        lo, hi = _call(plr.bounds, a.from_, a.through)
        _call(plr.probe_copy, path)
        pop = read_pages(Path(a.exports), lo, hi)
        with plr.open_db(path) as (s, label):
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
