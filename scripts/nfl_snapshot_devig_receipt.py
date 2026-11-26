"""
THE NFL SNAPSHOT DE-VIG RECEIPT (ARCHITECT 2026-11-25 16:12 ET, addendum 544 item 2; its nine points ruled by addendum
545 item 3; Refs #1141), READ-ONLY. Counts and percentage points only.

ITEM 2, verbatim: "DEV 4 BUILDS IT: scripts/nfl_snapshot_devig_receipt.py and its tests, on the pattern of your two
receipts and behind the same fence (--db COPY, mode=ro with immutable=1, no network, nothing written, no bookmaker name,
no price of a book, counts and percentage points only). For NFL and for college, each apart, from the first stored
session on: (a) the 1X2 sessions of that source: all, complete, HOME-only, AWAY-only; and those holding a leg at exactly
1 or exactly 0; (b) the matches whose FIRST session is one-sided, by the side; (c) for each match's LAST session, where
the stored offers still allow it: the pooled value against the close's own fair re-derived from those offers. Agree at
four places, or differ, the differences in buckets of percentage points; and apart, the sessions written where no
complete book stood; (d) the line move as line_move.py computes it: the matches whose flag is set, and of them those
with a one-sided session at either end; (e) each count by calendar month. It judges nothing and proposes nothing."
545 item 3 rules the nine points of #1141 (comment 7175133325) as read, with: "P4. THE BELL FIRST, kickoff less one
microsecond, through the function itself. "EVER FLAGGED" IS WANTED TOO, beside it, because the pager acts inside the
window and not at the bell ... The book venue's own flag, with the combined flag and Kalshi's beside it; the hidden
AWAY-only end counted apart." and "P2, P3, P5 (the New York month), P6, P7 (said beside the count), P8 and P9: yes."

WHAT IT READS (law 1: every name read from the code at origin/main 66b4e86c):
- THE SESSIONS: odds_snapshots rows with source "api_american_football" (api_american_football.py:145) and market
  "1X2", grouped by captured_at: one fetch, one stamp (service.sync_odds_nfl, service.py:3059, :3120, :3126-3128). The
  writer POOLS every 1X2 offer: MarketSnapshot(...).average_implied() over the summed implied (service.py:3112-3128,
  value.py:71-79), a one-sided book and both of one book's bets ("Home/Away", "Moneyline": api_american_football.py:
  396-397) among them, so a fetch that prices one side alone is written as that leg alone at exactly 1.0. Kalshi rows
  share the table (source "kalshi") and are never a session here.
- THE MATCHES: Sport.NFL (Match.sport, schema.py:178, stored by member name, schema.py:57-59), told apart by Competition.code "NFL" and "NCAA"
  (nfl_backtest.nfl_scoped; ncaa_cfbd.py:18); any other code under Sport.NFL is counted apart (545 P6). A preseason game
  (nfl_backtest.is_preseason on the stage) is counted apart and printed. Every status is read: sessions are written only
  while a game is SCHEDULED (service.py:3018-3024).
- THE OFFERS, for (c) only: odds rows with that source and market "1X2". The odds rows are wiped and replaced per match on
  every fetch that returns rows (service.py:3090-3105), stamped with the fetch's captured_at, so only each match's LAST
  fetch keeps its offers (545 P1). odds.bookmaker and odds.price_decimal are read for the close's own fair and NEVER
  printed; close_1x2's "best" and "missing" (book names) are never echoed.
- THE LINE MOVE, for (d): src/walters/line_move.line_move itself, on the match's snapshots loaded as
  line_move_for_match loads them (attach_source_times, then kalshi_legs.guard_snaps; line_move.py:128-147).

THE MEASURES (545 item 3, P1 to P9):
- (a) A session is COMPLETE when HOME and AWAY are both stored (its own legs: per-book completeness is knowable only on
  the last fetch, P3); HOME-only and AWAY-only by the legs present; a session with another selection, or two values for
  one leg, is counted apart. "A leg at exactly 1" and "a leg at exactly 0" are counted by value, apart from the legs
  present. No 0 is expected: every implied value is above 0 (value.py:71-79), and a one-sided session's other leg is an
  absent row, not a 0. Sessions at exactly kickoff, and after it, are counted apart (P8).
- (b) A match's FIRST session is its first with captured_at strictly before kickoff (the closes' rule, P8;
  nfl_predict._book_anchor reads <=).
- (c) A match's LAST session is its last strictly before kickoff. It is compared only where the match's 1X2 odds rows
  exist and every one carries that session's captured_at; else one named cause, counted (P1), in this order: no 1X2
  odds stored (never written, or wiped by a later fetch that returned no 1X2 rows: the writer wipes every market of the
  match, service.py:3090-3091); a 1X2 odds row's captured_at unreadable; the odds stamped at a session at or after
  kickoff (545 P1's third cause, before the next); no session before kickoff; the odds stamped at a fetch that wrote no
  session, or at mixed stamps (the general path's unpriced close, or a pooled sum not above 0). On those rows: (i) the pooled
  value is re-derived as the writer does, over every stored 1X2 offer with a price, and checked against the stored
  devig_prob (agree to 1e-9, else counted apart from the causes, on the compared and the unpriced alike);
  (ii) the close's own fair is close.close_1x2(rows, kickoff, BINARY), as nfl_predict computes the page's
  (nfl_predict.py:265-275), with no stale-book switch. The stored pooled HOME leg (else AWAY) against the fair's same
  leg: AGREE when equal at 4 places; else |difference| in pp, bucketed (P2). "Written where no complete book stood" is
  close_1x2 unpriced while a session exists.
- (d) At the BELL, now = kickoff less 1 microsecond; and EVER FLAGGED, at each stored snapshot stamp inside
  [kickoff - 3 h, kickoff) (P4). The book venue's own alarm, the combined flag (the one the pager and the freshen
  read) and the Kalshi venue's alarm, each counted. Of the book-flagged matches, those with a one-sided session at
  either end of the book venue (from_at, to_at: the non-Kalshi 1X2 rows at that stamp). An AWAY-only session is skipped
  by line_move._series and is never an end, so the matches whose last pre-kickoff book stamp is AWAY-only (the hidden
  end) are counted apart. Only matches that kicked off before the copy's newest parsed snapshot stamp are in (c) and
  (d); the rest are counted apart (their record is not yet whole on this copy). (b) reads every match: a first
  session, once stored, never changes.
- (e) Months are America/New_York calendar months (P5): a session's by its captured_at, a match's by its kickoff.
- THE SECOND WRITER (P7): IngestionService.sync_odds (a manual sync-odds --competition NFL|NCAA) writes the same source
  string with close_1x2's own fair (service.py:1610-1663); no column tells it from the pooled writer, so its sessions,
  if any, are counted in, and the console says so.
- n_books is never used or printed (it counts offers on this writer, service.py:3121; P9); the ORM's load of the
  snapshot rows for line_move carries it with the row.

No provider call, no network, nothing written (immutable=1; no bytecode). No book name, no price, no amount.

Run:  python3 scripts/nfl_snapshot_devig_receipt.py --db COPY
Exit 0 done; 2 refused, nothing reported. The last line is NFL-SNAPSHOT-DEVIG-RECEIPT {json}.
Python 3.10 is the floor (CONTRIBUTING.md).
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True      # "nothing written": no __pycache__ of the repo's code

import argparse  # noqa: E402
import errno  # noqa: E402
import json  # noqa: E402
import sqlite3  # noqa: E402
from collections import Counter, defaultdict  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402
from pathlib import Path  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from typing import Callable  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TAIL = "NFL-SNAPSHOT-DEVIG-RECEIPT"
SOURCE = "api_american_football"
MARKET = "1X2"
LEGS = ("HOME", "AWAY")
FAMILIES = ("NFL", "NCAA")
DP = 4
REDERIVE_TOL = 1e-9
BELL = timedelta(microseconds=1)
TZ = "America/New_York"
COPY_TABLES = ("competitions", "matches", "odds", "odds_snapshots")
READS = {"competitions": {"id", "code"},
         "matches": {"id", "sport", "competition_id", "stage", "utc_date", "status"},
         "odds": {"id", "match_id", "bookmaker", "market", "selection", "price_decimal", "line", "captured_at",
                  "source"},
         "odds_snapshots": {"id", "match_id", "market", "selection", "devig_prob", "captured_at", "source"}}
DIFF_BUCKETS = ((0.0, 0.1, "under 0.1 pp"), (0.1, 0.5, "0.1-0.5 pp"), (0.5, 1.0, "0.5-1 pp"), (1.0, 2.0, "1-2 pp"),
                (2.0, 5.0, "2-5 pp"), (5.0, None, "5 pp or more"))
SESSION_KINDS = ("complete", "HOME-only", "AWAY-only", "other legs", "two values for one leg")
C_NO_ODDS = "no 1X2 odds stored (never written, or wiped by a later fetch that returned no 1X2 rows)"
C_ODDS_UNREADABLE = "a 1X2 odds row's captured_at unreadable"
C_NO_PRE = "no session before kickoff"
C_POST = "the odds stamped at a session at or after kickoff"
C_OTHER = ("the odds stamped at a fetch that wrote no session, or at mixed stamps (the general path's unpriced "
           "close, or a pooled sum not above 0)")
C_UNPRICED = "written where no complete book stood (close_1x2 unpriced)"
C_NOT_REDERIVED = "the stored devig_prob does not re-derive from the stored offers"
HIDDEN = "the hidden end (the last pre-kickoff book stamp holds no HOME leg, so line_move skips it)"
SECOND_WRITER = ("THE SECOND WRITER (545 P7): IngestionService.sync_odds, a manual sync-odds --competition NFL|NCAA, "
                 "writes the same source with close_1x2's own fair (service.py:1610-1663); no column tells its sessions "
                 "from the pooled writer's, so any it wrote are counted in here, unlabelled")


def _reads(t: str) -> set:
    """The columns this read needs of table t: READS, and for odds_snapshots every column the ORM's select of
    OddsSnapshot loads for line_move (schema.py's mapped columns)."""
    if t != "odds_snapshots":
        return READS[t]
    from src.db.schema import OddsSnapshot
    return READS[t] | {c.name for c in OddsSnapshot.__table__.columns}


class ReceiptRefused(RuntimeError):
    """A refused read: exit 2, nothing reported."""


# ---- the copy (nfl_qb_agreement_receipt's fence, with this read's tables) ------------------------------------------

def _named_data(p) -> str | None:
    try:
        q = Path(str(p)).expanduser()
        parts = list(q.parts) + list(q.resolve().parts)
    except (RuntimeError, OSError) as e:
        return "{} cannot be resolved ({})".format(p, type(e).__name__)
    if any(x.casefold() == "data" for x in parts):
        return "{} is under a directory named data (law 5)".format(p)
    return None


def check_copy(db) -> Path:
    """--db refused under any directory named data, by mlb_pitchers_gate.check_db, beside a sidecar, or where a table
    cannot be read; nothing read."""
    from src.walters import intl_shadow as us
    from src.walters import mlb_pitchers_gate as mp
    if db is not None and str(db).strip():
        why = _named_data(db)
        if why:
            raise ReceiptRefused("--db " + why + "; nothing read")
    try:
        path = mp.check_db(db)
        try:
            sides = us.copy_sidecars(path)
        except OSError as err:
            hint = "; take the copy under a shorter name" if err.errno == errno.ENAMETOOLONG else ""
            raise mp.GateRefused("--db {}: a sidecar beside it cannot be checked ({!r}){}".format(db, err, hint)) \
                from None
        for name in sides:
            raise mp.GateRefused("--db {} has a {} sidecar ({}): not a fresh .backup copy; immutable=1 would ignore "
                                 "it and read a stale store".format(db, name[len(path.name):], name))
        con = mp.open_ro(path)
        try:
            for t in COPY_TABLES:
                try:
                    con.execute("SELECT 1 FROM {} LIMIT 1".format(t))
                except sqlite3.Error as e:
                    raise mp.GateRefused("--db {}: the copy cannot be read for table {} ({})".format(db, t, e))
                got = {r[1] for r in con.execute("PRAGMA table_info({})".format(t))}
                miss = _reads(t) - got
                if miss:
                    raise mp.GateRefused("--db {}: columns {} not in {} (law 1)".format(
                        db, ", ".join(sorted(miss)), t))
        finally:
            con.close()
    except mp.GateRefused as err:
        raise ReceiptRefused("{}; nothing read".format(err))
    return path


def on_copy(copy: Path, read):
    """(sha256 before, read(s)) on the copy's mode=ro + immutable=1 session; refused when the copy changed during the
    read or a sidecar appeared; any failure by its class alone."""
    from sqlalchemy.exc import DBAPIError

    from src.walters import intl_shadow as us
    from src.walters import mlb_pitchers_gate as mp
    try:
        sha_before = us.copy_sha256(copy)
    except OSError as err:
        raise ReceiptRefused("--db {}: the copy could not be hashed ({}); nothing read".format(
            copy, type(err).__name__))
    try:
        with mp.readonly_session(copy) as s:
            out = read(s)
            try:
                sha_after = us.copy_sha256(copy)
                sides_after = us.copy_sidecars(copy)
            except OSError as err:
                raise ReceiptRefused("--db {}: the copy could not be re-read after the read ({}); nothing "
                                     "reported".format(copy, type(err).__name__)) from None
    except DBAPIError as err:
        raise ReceiptRefused("--db {}: the copy could not be read ({}); nothing reported".format(
            copy, type(err.orig).__name__))
    except ReceiptRefused:
        raise
    except Exception as err:      # by its class alone: never a traceback that could carry a book name or a price
        raise ReceiptRefused("the read failed ({}); nothing reported".format(type(err).__name__))
    if sides_after:
        raise ReceiptRefused("--db {} changed during the read: {} appeared beside it; nothing reported".format(
            copy, ", ".join(sides_after)))
    if sha_after != sha_before:
        raise ReceiptRefused("--db {} changed during the read (sha256 {}... before, {}... after); nothing "
                             "reported".format(copy, sha_before[:16], sha_after[:16]))
    return sha_before, out


# ---- small helpers ------------------------------------------------------------------------------------------------

def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf") \
        else None


def _month(d: datetime | None) -> str:
    """The America/New_York calendar month of a naive-UTC instant (545 P5)."""
    if d is None:
        return "(no date)"
    from zoneinfo import ZoneInfo
    return d.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(TZ)).strftime("%Y-%m")


def diff_bucket(pp: float) -> str:
    for lo, hi, name in DIFF_BUCKETS:
        if pp >= lo and (hi is None or pp < hi):
            return name
    raise ValueError(pp)


def classify(legs: dict) -> str:
    """One session by its own stored legs: {selection: [devig_prob, ...]}."""
    if any(len(set(v)) > 1 for v in legs.values()):
        return "two values for one leg"
    sels = set(legs)
    if sels == {"HOME", "AWAY"}:
        return "complete"
    if sels == {"HOME"}:
        return "HOME-only"
    if sels == {"AWAY"}:
        return "AWAY-only"
    return "other legs"


# ---- the read -----------------------------------------------------------------------------------------------------

def read_counts(s) -> dict:
    from sqlalchemy import text

    from src.db.schema import Sport
    from src.walters import redated
    from src.walters.nfl_backtest import is_preseason

    matches = {}
    for mid, ko, stage, status, code in s.execute(text(
            "SELECT m.id, m.utc_date, m.stage, m.status, c.code FROM matches m LEFT JOIN competitions c "
            "ON c.id = m.competition_id WHERE m.sport = :sp"), {"sp": Sport.NFL.name}):
        matches[mid] = {"id": mid, "kickoff": redated.as_utc(ko), "stage": stage, "status": status, "code": code,
                        "unreadable": 0,
                        "sessions": defaultdict(lambda: defaultdict(list))}
    unreadable_snap, outside = 0, 0
    newest = None
    for mid, at, sel, val in s.execute(text(
            "SELECT match_id, captured_at, selection, devig_prob FROM odds_snapshots WHERE source = :src AND "
            "market = :mk ORDER BY captured_at, id"), {"src": SOURCE, "mk": MARKET}):
        t = redated.as_utc(at)
        if t is None:
            unreadable_snap += 1
            if mid in matches:      # its family's own count, month "(no date)"; outside the families it stays global
                matches[mid]["unreadable"] += 1
            continue
        if mid not in matches:
            outside += 1
            continue
        matches[mid]["sessions"][t][sel].append(val)
    unreadable_any = 0
    for (at,) in s.execute(text("SELECT DISTINCT captured_at FROM odds_snapshots")):
        t = redated.as_utc(at)
        if t is None:
            unreadable_any += 1
        elif newest is None or t > newest:
            newest = t
    offers = defaultdict(list)
    odds_unreadable = 0
    for oid, mid, bk, sel, px, line, at in s.execute(text(
            "SELECT id, match_id, bookmaker, selection, price_decimal, line, captured_at FROM odds WHERE "
            "source = :src AND market = :mk ORDER BY id"), {"src": SOURCE, "mk": MARKET}):
        if mid in matches:
            offers[mid].append(SimpleNamespace(id=oid, match_id=mid, bookmaker=bk, selection=sel, market=MARKET,
                                               price_decimal=px, line=line, captured_at=redated.as_utc(at)))
            if redated.as_utc(at) is None:
                odds_unreadable += 1
    fams = {f: new_family() for f in FAMILIES}
    apart = {"other_codes": Counter(), "preseason": Counter(), "by_month": defaultdict(Counter)}
    for m in sorted(matches.values(), key=lambda x: x["id"]):
        if m["code"] in FAMILIES and m["unreadable"] and not is_preseason(m["stage"]):
            fams[m["code"]]["a"]["unreadable_stamp"] += m["unreadable"]
            fams[m["code"]]["a"]["by_month"]["(no date)"]["unreadable stamp"] += m["unreadable"]
        if not m["sessions"]:
            continue
        code = m["code"]
        if code not in FAMILIES:
            apart["other_codes"][str(code)] += 1
            apart["by_month"][_month(m["kickoff"])]["other code " + str(code)] += 1
            continue
        if is_preseason(m["stage"]):
            apart["preseason"][code] += 1
            apart["by_month"][_month(m["kickoff"])]["preseason " + code] += 1
            continue
        measure_match(s, m, offers.get(m["id"], []), newest, fams[code])
    for f in fams.values():
        finish_family(f)
    return {"families": fams, "apart": {"other_codes": dict(apart["other_codes"]),
                                        "preseason": dict(apart["preseason"]),
                                        "by_month": {mo: dict(c) for mo, c in sorted(apart["by_month"].items())}},
            "snapshot_rows_unreadable_stamp": unreadable_snap, "snapshot_rows_outside_sport_nfl": outside,
            "snapshot_stamps_unreadable_any_source": unreadable_any, "odds_rows_unreadable_stamp": odds_unreadable,
            "copy_newest_snapshot": newest.strftime("%Y-%m-%dT%H:%M:%SZ") if newest else None}


def new_family() -> dict:
    return {"first_session": None, "statuses": Counter(),
            "a": {"all": 0, **{k: 0 for k in SESSION_KINDS}, "leg_exactly_1": 0, "leg_exactly_0": 0,
                  "unreadable_stamp": 0,
                  "at_kickoff": 0, "after_kickoff": 0, "by_month": defaultdict(Counter)},
            "matches": 0, "not_kicked_off_on_copy": 0, "no_kickoff": 0, "by_month": defaultdict(Counter),
            "b": {"with_a_first_session": 0, "first": Counter(), "by_month": defaultdict(Counter)},
            "c": {"cause": Counter(), "compared": 0, "agree": 0, "differ": Counter(), "differ_pp": [],
                  "not_rederived": Counter(), "by_month": defaultdict(Counter)},
            "d": {"evaluated": 0, "bell": Counter(), "ever": Counter(), "book_flag_end": Counter(),
                  "ever_book_flag_end": Counter(),
                  "hidden_end": 0, "hidden_end_book_flagged": 0, "by_month": defaultdict(Counter)}}


def measure_match(s, m: dict, rows: list, newest, f: dict) -> None:
    ko = m["kickoff"]
    f["matches"] += 1
    f["statuses"][str(m["status"])] += 1
    sessions = m["sessions"]
    stamps = sorted(sessions)
    if f["first_session"] is None or stamps[0] < f["first_session"]:
        f["first_session"] = stamps[0]
    kinds = {}
    for t in stamps:
        legs = sessions[t]
        kind = classify(legs)
        kinds[t] = kind
        a = f["a"]
        a["all"] += 1
        a[kind] += 1
        mo = a["by_month"][_month(t)]
        mo["all"] += 1
        mo[kind] += 1
        vals = [v for vs in legs.values() for v in vs]
        if any(_num(v) == 1.0 for v in vals):
            a["leg_exactly_1"] += 1
            mo["leg_exactly_1"] += 1
        if any(_num(v) == 0.0 for v in vals):
            a["leg_exactly_0"] += 1
            mo["leg_exactly_0"] += 1
        if ko is not None and t == ko:
            a["at_kickoff"] += 1
            mo["at_kickoff"] += 1
        elif ko is not None and t > ko:
            a["after_kickoff"] += 1
            mo["after_kickoff"] += 1
    kmo = _month(ko)
    f["by_month"][kmo]["matches"] += 1
    if ko is None:
        f["no_kickoff"] += 1
        f["by_month"][kmo]["no kickoff"] += 1
        return
    pre = [t for t in stamps if t < ko]
    # (b) the first session strictly before kickoff: fixed once stored (sessions are appended, never earlier), so
    # every match is read here, kicked off or not on this copy
    if pre:
        f["b"]["with_a_first_session"] += 1
        f["b"]["first"][kinds[pre[0]]] += 1
        f["b"]["by_month"][kmo][kinds[pre[0]]] += 1
    if newest is None or ko > newest:
        f["not_kicked_off_on_copy"] += 1
        f["by_month"][kmo]["not kicked off on this copy"] += 1
        return
    # (c) the last session strictly before kickoff, against the offers that remain
    cause, res = compare_last(sessions, pre, rows, ko)
    c = f["c"]
    if cause is not None:
        c["cause"][cause] += 1
        c["by_month"][kmo][cause] += 1
    else:
        c["compared"] += 1
        if res["agree"]:
            c["agree"] += 1
            c["by_month"][kmo]["agree"] += 1
        else:
            b = diff_bucket(res["pp"])
            c["differ"][b] += 1
            c["differ_pp"].append(res["pp"])
            c["by_month"][kmo]["differ " + b] += 1
    if res is not None and res.get("rederived") is False:      # apart from the causes (545 P2), compared or unpriced
        where = "compared" if cause is None else "unpriced"
        c["not_rederived"][where] += 1
        c["by_month"][kmo]["not re-derived (" + where + ")"] += 1
    # (d) the line move, at the bell and ever inside the window
    line_moves(s, m, ko, f["d"], kmo)


def compare_last(sessions: dict, pre: list, rows: list, ko: datetime):
    """(cause, None) or (None, {agree, pp, rederived}) for the match's last pre-kickoff session."""
    from src.walters.close import BINARY, close_1x2, priced
    from src.walters.value import MarketSnapshot
    if not rows:
        return C_NO_ODDS, None
    stamps = {r.captured_at for r in rows}
    if None in stamps:
        return C_ODDS_UNREADABLE, None
    only = next(iter(stamps)) if len(stamps) == 1 else None
    if only is not None and only >= ko and only in sessions:
        return C_POST, None                                 # 545 P1's third cause, before "no session before kickoff"
    if not pre:
        return C_NO_PRE, None
    last = pre[-1]
    if stamps != {last}:
        return C_OTHER, None
    legs = sessions[last]
    if any(len(set(v)) > 1 for v in legs.values()):
        return "the last session holds two values for one leg", None
    stored = {k: _num(v[0]) for k, v in legs.items()}
    # (i) the pooled value as the writer forms it (service.py:3112-3128): every stored 1X2 offer with a price,
    # unfiltered as the writer pools them (a price of 0 cannot be stored: 1/0 raises in the writer's own pass)
    by_sel = defaultdict(list)
    for r in rows:
        if isinstance(r.price_decimal, (int, float)) and not isinstance(r.price_decimal, bool) \
                and r.price_decimal != 0:
            by_sel[r.selection].append((r.bookmaker, r.price_decimal))
    implied = MarketSnapshot(market=MARKET, by_selection=dict(by_sel)).average_implied() if by_sel else {}
    over = sum(implied.values())
    pooled = {k: v / over for k, v in implied.items()} if over > 0 else {}
    rederived = set(pooled) == set(stored) and all(
        stored[k] is not None and abs(pooled[k] - stored[k]) <= REDERIVE_TOL for k in stored)
    # (ii) the close's own fair, as the page computes it (nfl_predict.py:265-275)
    cl = close_1x2(rows, ko, BINARY)
    if not priced(cl):
        return C_UNPRICED, {"rederived": rederived}
    leg = "HOME" if stored.get("HOME") is not None else "AWAY"
    if stored.get(leg) is None:
        return "the last session holds no number", None
    fair = cl["fair"][leg]
    agree = round(stored[leg], DP) == round(fair, DP)
    return None, {"agree": agree, "pp": round(abs(stored[leg] - fair) * 100, 6), "rederived": rederived}


def _book_rows_at(snaps, t):
    return [x for x in snaps if x.captured_at == t and x.source != "kalshi" and x.market == MARKET]


def line_moves(s, m: dict, ko: datetime, d: dict, kmo: str) -> None:
    """(d): line_move itself, on the snapshots as line_move_for_match loads them, at the bell and at each stamp in the
    window."""
    from sqlalchemy import select

    from src.db.database import attach_source_times
    from src.db.schema import OddsSnapshot
    from src.walters import line_move as lmv
    from src.walters.kalshi_legs import guard_snaps
    snaps = attach_source_times(s, s.execute(select(OddsSnapshot).where(OddsSnapshot.match_id == m["id"])).scalars())
    snaps, _ = guard_snaps(snaps, s)
    d["evaluated"] += 1
    d["by_month"][kmo]["evaluated"] += 1
    bell = lmv.line_move(snaps, ko, ko - BELL)
    marks = flags(bell)
    for k in marks:
        d["bell"][k] += 1
        d["by_month"][kmo]["bell " + k] += 1
    book_stamps = sorted({x.captured_at for x in snaps if x.captured_at is not None and x.captured_at < ko
                          and x.source != "kalshi" and x.market == MARKET})
    hidden = bool(book_stamps) and "HOME" not in {x.selection for x in _book_rows_at(snaps, book_stamps[-1])}
    if hidden:
        d["hidden_end"] += 1
        d["by_month"][kmo]["hidden end"] += 1
    if "book" in marks:
        if hidden:
            d["hidden_end_book_flagged"] += 1
            d["by_month"][kmo]["hidden end, book-flagged"] += 1
        end = end_label(one_sided_ends(snaps, bell))
        d["book_flag_end"][end] += 1
        d["by_month"][kmo]["book-flagged, " + end] += 1
    start = ko - timedelta(hours=lmv.LINE_MOVE_WINDOW_H)
    ever = set()
    ever_ends = set()          # the ends found one-sided at ANY stamp whose book alarm is set (the ever cohort)
    for t, upto in ever_inputs(snaps, start, ko):
        lm = lmv.line_move(upto, ko, t)
        got = flags(lm)
        ever |= got
        if "book" in got:
            ever_ends |= set(one_sided_ends(snaps, lm))
    for k in ever:
        d["ever"][k] += 1
        d["by_month"][kmo]["ever " + k] += 1
    if "book" in ever:
        end = end_label(sorted(ever_ends, key=("from_at", "to_at").index))
        d["ever_book_flag_end"][end] += 1
        d["by_month"][kmo]["ever book-flagged, " + end] += 1


def one_sided_ends(snaps, lm: dict) -> list:
    """The ends (from_at, to_at) of a line_move result's book venue whose session is not both legs: the non-Kalshi 1X2
    rows at that stamp, as line_move._series reads them."""
    bk = lm["venues"]["book"]
    ends = []
    for side in ("from_at", "to_at"):
        sels = {x.selection for x in _book_rows_at(snaps, datetime.fromisoformat(bk[side]))}
        if sels != {"HOME", "AWAY"}:
            ends.append(side)
    return ends


def end_label(ends: list) -> str:
    return "one-sided at " + (" and ".join(ends) if ends else "neither end")


def ever_inputs(snaps, start: datetime, ko: datetime):
    """(t, the rows captured at or before t) for each stored stamp t in [start, ko). line_move reads no row after its
    now (_series keeps captured_at <= now; the book's source times are read at its ref and cur stamps, both <= now), so
    the rows after t are dropped before the call: the same result, a smaller input (the receipt's cost is line_move
    called at each stamp, 545 P4)."""
    dated = sorted((x for x in snaps if x.captured_at is not None), key=lambda x: x.captured_at)
    stamps = sorted({x.captured_at for x in dated if start <= x.captured_at < ko})
    i = 0
    for t in stamps:
        while i < len(dated) and dated[i].captured_at <= t:
            i += 1
        yield t, dated[:i]


def flags(lm: dict | None) -> set:
    """The flags one line_move result sets: the book venue's alarm, Kalshi's, and the combined flag."""
    out = set()
    if not lm:
        return out
    v = lm.get("venues") or {}
    if (v.get("book") or {}).get("alarm"):
        out.add("book")
    if (v.get("kalshi") or {}).get("alarm"):
        out.add("kalshi")
    if lm.get("flag"):
        out.add("combined")
    return out


def finish_family(f: dict) -> None:
    from src.walters.venue_quote_age import pct
    f["first_session"] = f["first_session"].strftime("%Y-%m-%dT%H:%M:%SZ") if f["first_session"] else None
    xs = f["c"].pop("differ_pp")
    f["c"]["differ_pp_dist"] = ({"n": len(xs), "min": min(xs), "median": pct(xs, 0.5), "max": max(xs)} if xs
                                else {"n": 0})
    f["statuses"] = dict(f["statuses"])
    f["by_month"] = {mo: dict(c) for mo, c in sorted(f["by_month"].items())}
    for part in ("a", "b", "c", "d"):
        for k, v in list(f[part].items()):
            if isinstance(v, defaultdict):
                f[part][k] = {mo: dict(c) for mo, c in sorted(v.items())}
            elif isinstance(v, Counter):
                f[part][k] = dict(v)


# ---- the console --------------------------------------------------------------------------------------------------

def _kv(d: dict) -> str:
    return " · ".join("{} {}".format(k, v) for k, v in sorted(d.items())) or "none"


def render(c: dict, out) -> None:
    out("RULES: sessions = odds_snapshots, source {}, market {}, one captured_at one session; families by "
        "Competition.code (NFL, NCAA) under Sport.NFL; months in {} (545 P5), sessions by captured_at, matches by "
        "kickoff; (c) and (d) on matches kicked off before the copy's newest parsed snapshot stamp ({}), the rest "
        "counted apart".format(SOURCE, MARKET, TZ, c["copy_newest_snapshot"]))
    out(SECOND_WRITER)
    out("APART: other competition codes under Sport.NFL {} · preseason (nfl_backtest.is_preseason) {} · snapshot rows "
        "of the source with an unreadable captured_at {} · snapshot stamps of any source unreadable {} (never the "
        "copy's newest) · 1X2 odds rows with an unreadable captured_at {} · rows of the source on matches outside "
        "Sport.NFL {}".format(_kv(c["apart"]["other_codes"]), _kv(c["apart"]["preseason"]),
                              c["snapshot_rows_unreadable_stamp"], c["snapshot_stamps_unreadable_any_source"],
                              c["odds_rows_unreadable_stamp"], c["snapshot_rows_outside_sport_nfl"]))
    for mo, cnt in c["apart"]["by_month"].items():
        out("    apart, {} (by kickoff): {}".format(mo, _kv(cnt)))
    for name in FAMILIES:
        f = c["families"][name]
        a, b, cc, d = f["a"], f["b"], f["c"], f["d"]
        out("")
        out("==== {} · from the first stored session on: {} · matches with a session {} (by status: {}) · not "
            "kicked off on this copy {} · no kickoff {}".format(name, f["first_session"], f["matches"],
                                                                 _kv(f["statuses"]), f["not_kicked_off_on_copy"],
                                                                 f["no_kickoff"]))
        out("(a) SESSIONS: all {} · {} · a leg at exactly 1: {} · a leg at exactly 0: {} (none expected: every "
            "implied value is above 0, and a one-sided session's other leg is an absent row) · at exactly kickoff "
            "{} · after kickoff {} · rows with an unreadable captured_at {} (in no session)".format(
                a["all"], " · ".join("{} {}".format(k, a[k]) for k in SESSION_KINDS), a["leg_exactly_1"],
                a["leg_exactly_0"], a["at_kickoff"], a["after_kickoff"], a["unreadable_stamp"]))
        out("(b) FIRST SESSION before kickoff: matches {} · {}".format(b["with_a_first_session"], _kv(b["first"])))
        dd = cc["differ_pp_dist"]
        out("(c) LAST SESSION before kickoff, against the close's own fair from the offers that remain: compared {} · "
            "agree at 4 places {} · differ {} ({}){}".format(
                cc["compared"], cc["agree"], sum(cc["differ"].values()),
                " · ".join("{} {}".format(n, cc["differ"].get(n, 0)) for _lo, _hi, n in DIFF_BUCKETS),
                " · the differences: min {:.4f} · median {:.4f} · max {:.4f} pp".format(dd["min"], dd["median"],
                                                                                       dd["max"]) if dd["n"] else ""))
        out("    not compared, by cause: " + _kv(cc["cause"]))
        out("    apart from both (545 P2): {}, of the compared {} · of the unpriced {}".format(
            C_NOT_REDERIVED, cc["not_rederived"].get("compared", 0), cc["not_rederived"].get("unpriced", 0)))
        out("(d) LINE MOVE (line_move.line_move): matches {} · AT THE BELL (kickoff less 1 microsecond): {} · EVER "
            "FLAGGED (at each stored stamp in [kickoff - 3 h, kickoff)): {}".format(
                d["evaluated"], _kv(d["bell"]), _kv(d["ever"])))
        out("    of the book-flagged at the bell, by a one-sided session at an end of the book venue: {} · of the ever "
            "book-flagged, by the ends found one-sided at any stamp whose book alarm is set: {} · {}: {} (of them "
            "book-flagged at the bell {})".format(_kv(d["book_flag_end"]), _kv(d["ever_book_flag_end"]), HIDDEN,
                                                  d["hidden_end"], d["hidden_end_book_flagged"]))
        out("(e) BY MONTH ({}):".format(TZ))
        months = sorted(set(a["by_month"]) | set(b["by_month"]) | set(cc["by_month"]) | set(d["by_month"])
                        | set(f["by_month"]))
        for mo in months:
            out("    {} · matches {} · (a) {} · (b) {} · (c) {} · (d) {}".format(
                mo, _kv(f["by_month"].get(mo, {})), _kv(a["by_month"].get(mo, {})), _kv(b["by_month"].get(mo, {})),
                _kv(cc["by_month"].get(mo, {})), _kv(d["by_month"].get(mo, {}))))


def main(argv: list | None = None, out: Callable[[str], None] = print) -> int:
    ap = argparse.ArgumentParser(prog="nfl_snapshot_devig_receipt.py",
                                 description="Read-only counts of the NFL and college 1X2 snapshot de-vig (#1141).")
    ap.add_argument("--db", required=True, metavar="COPY", help="a .backup copy of the database (mode=ro + "
                    "immutable=1; never under data/, never the configured database)")
    args = ap.parse_args(argv)
    out("THE NFL SNAPSHOT DE-VIG RECEIPT (addendum 544 item 2, ruled by 545 item 3; read-only; counts and pp only; "
        "no book name, no price; no network; nothing written)")
    try:
        copy = check_copy(args.db)
        sha, counts = on_copy(copy, read_counts)
    except ReceiptRefused as e:
        out("REFUSED: {}".format(e))
        return 2
    out("--db {} · sha256 {} (the same after the read; no sidecar)".format(copy, sha))
    render(counts, out)
    out("{} {}".format(TAIL, json.dumps(counts, sort_keys=True, default=str)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
