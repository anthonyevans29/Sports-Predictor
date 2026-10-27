"""
THE BOOK-STAMP AGE RECEIPT (#382; ARCHITECT 2026-10-26 11:55 ET item (2), and 2026-10-27 15:20 ET item 2), READ-ONLY.

The request, verbatim (2026-10-26 11:55 ET): "(2) #382 (book-stamp age at the close): extend the age receipt to the
full distribution of close_book_stamp_age_h on every NFL closing row since Week 3 and every PL row since #615's
stamping began, by kickoff slot; by book ONLY where bookmaker-level rows were retained — the stamp is the provider's
response time, not a quote time, and rows with no stamp count in the denominator as unknown, never backfilled. 10-25's
seven rows at 11–22 h, under the 24 h flag, are the observation that prompts it. A per-family STALE_BOOK_H is a ruling
after the receipt."
The lane, verbatim (2026-10-27 15:20 ET): "the book-stamp age distribution (per family, by book only where rows are
retained, unknowns in the denominator) [...] Read-only".

WHAT IT READS (the database, opened mode=ro through src.db.database.readonly_scope: no hook, no pragma, no commit; a
missing file, or one without the tables read, is refused, exit 2, never created). The database file is never written;
on a WAL-mode database (the app's default) SQLite itself may create the -wal / -shm sidecar files beside it, which a
read-only connection cannot remove. Nothing else is written.
- THE GAMES, one per match (a match's predictions are not counted twice):
  - NFL: every graded live game, as the NFL grader (nfl_predict.grade_nfl) reads it: an NFL-competition match
    (nfl_backtest.nfl_scoped) FINISHED with both scores and a prediction, not pre-live (nfl_predict._is_pre_live:
    kicked off on or after NFL_LIVE_SINCE, 2026-09-22, Week 3, and not a preseason stage).
  - PL: every graded PL game (a prediction with a scored prediction_outcomes row, as export_results reads it) whose
    kickoff is on or after --pl-since (default 2026-10-20 18:42Z, the merge of #629, the change that stamps soccer book
    odds: "#615's stamping"). When a machine pulled #629 is not in the code: the receipt prints the first stamped
    kickoff it finds and counts the unstamped games before it as unknown, never as fresh.
- THE CLOSE AND ITS AGE, through each family's own grading path, never re-derived:
  - NFL: close.close_1x2 over the odds table's 1X2 rows, then close.stale_book_close (as grade_nfl and the NFL results
    file do; no snapshot fallback, no kalshi_only path).
  - PL: close.grading_close (as export.result_row does: the odds table, else a book snapshot, else kalshi_only).
  - The age is close.stamp_age_hours: the stored kickoff (Match.utc_date) minus the book close's provider stamp
    (close.book_stamp: the oldest source_updated_at over the rows the close priced, close.priced_rows), in hours, the
    number the results rows carry as graded.close_book_stamp_age_h (unrounded here; never clamped, so a negative age
    prints as one). "The stamp is the provider's response time, not a quote time": the age is the provider-stamp age,
    a lower bound on how old a quote is.
- UNKNOWN, IN THE DENOMINATOR, NEVER BACKFILLED (each game in exactly one cause):
  - (a) the odds table has no source_updated_at column (migrate_odds_source_updated_at.py not run on this database);
  - (b) a priced book close whose rows carry no stamp (rows written before the migration or before #629);
  - (c) a priced book close whose rows are partly stamped (oldest_source_time reads any unknown row as unknown);
  - (d) no priced book close at all (no pre-kickoff book session, an incomplete outcome set, or a PL kalshi_only close).
  A game re-dated by the closing files (with --exports, redated.void_label) is listed and kept out of the distribution,
  counted; without --exports the receipt says re-dates are unlabelled.
- BY KICKOFF SLOT (no slot classifier exists in the code; this one is Code's, printed for the architect's approval):
  - NFL, in America/New_York: Thu 19:00 on "TNF", Thu before 19:00 "Thu day" (Thanksgiving), Mon "MNF", Sun before
    12:00 "Sun international", 12:00-14:59 "Sun early", 15:00-18:59 "Sun late", 19:00 on "SNF", any other day by its
    name.
  - PL, in Europe/London: the weekday and the local kickoff time ("Sat 15:00").
- BY BOOK, ONLY WHERE BOOKMAKER-LEVEL ROWS WERE RETAINED: the odds table keeps the per-book rows of the last pre-kickoff
  session (the session the close prices); a book snapshot keeps the consensus only (no bookmaker). Per book: the games
  whose close it priced, and the distribution of those games' stamp ages. The provider stamps one answer, not a book,
  so the receipt also counts the games whose priced rows carry more than one distinct stamp (measured, never assumed).

The thresholds printed beside the distribution are the code's (close.STALE_BOOK_H, 24 h, "more than" switches); a
per-family STALE_BOOK_H is the architect's ruling after this receipt. Nothing here moves a close, a grade or a call.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PL_SINCE = "2026-10-20T18:42:00"          # the merge of #629 (fb722251, 2026-10-20 14:42 ET): soccer book odds stamped
NY, UK = ZoneInfo("America/New_York"), ZoneInfo("Europe/London")
BUCKETS = ((None, 0.0, "under 0 h (stamp after the stored kickoff)"), (0.0, 6.0, "0-6 h"), (6.0, 12.0, "6-12 h"),
           (12.0, 24.0, "12-24 h"), (24.0, 48.0, "24-48 h"), (48.0, None, "48 h or more"))
UNKNOWN = {"a": "(a) no source_updated_at column on this database",
           "b": "(b) priced book close, its rows unstamped",
           "c": "(c) priced book close, its rows partly stamped",
           "d": "(d) no priced book close"}
NEEDED_TABLES = ("matches", "competitions", "predictions", "prediction_outcomes", "odds", "odds_snapshots")
QS = (("p10", 0.10), ("p25", 0.25), ("median", 0.50), ("p75", 0.75), ("p90", 0.90))


def slot(family: str, kickoff: datetime | None) -> str:
    """The kickoff slot (the receipt's own table, see the module doc), from the stored naive-UTC kickoff."""
    if kickoff is None:
        return "(no kickoff)"
    from datetime import timezone
    utc = kickoff.replace(tzinfo=timezone.utc) if kickoff.tzinfo is None else kickoff
    if family == "NFL":
        t = utc.astimezone(NY)
        day = t.strftime("%a")
        if day == "Thu":
            return "TNF (Thu 19:00 ET on)" if t.hour >= 19 else "Thu day (before 19:00 ET)"
        if day == "Mon":
            return "MNF (Mon)"
        if day == "Sun":
            return ("Sun international (before 12:00 ET)" if t.hour < 12 else "Sun early (12:00-14:59 ET)"
                    if t.hour < 15 else "Sun late (15:00-18:59 ET)" if t.hour < 19 else "SNF (Sun 19:00 ET on)")
        return f"{day} (ET)"
    t = utc.astimezone(UK)
    return f"{t:%a %H:%M} UK"


def bucket(age: float) -> str:
    for lo, hi, name in BUCKETS:
        if (lo is None or age >= lo) and (hi is None or age < hi):
            return name
    raise ValueError(age)


def _stamps(session, rows) -> list:
    """The priced rows' provider stamps, read through the one guarded helper (database.attach_source_times)."""
    from src.db.database import attach_source_times
    return [getattr(r, "source_updated_at", None) for r in attach_source_times(session, rows)]


def game_record(s, m, family: str, has_column: bool) -> dict:
    """One game: its close kind, its stamp age (or the unknown cause), and its per-book rows (odds-sourced closes)."""
    from sqlalchemy import select

    from src.db.schema import Odds
    from src.walters import close as C
    out = {"match_id": m.id, "kickoff": m.utc_date, "slot": slot(family, m.utc_date), "age": None, "unknown": None,
           "kind": None, "books": [], "distinct_stamps": 0,
           "teams": f"{m.away_team.name if m.away_team else '?'} @ {m.home_team.name if m.home_team else '?'}"}
    if family == "NFL":
        rows = list(s.execute(select(Odds).where(Odds.match_id == m.id, Odds.market == "1X2")).scalars())
        book = C.close_1x2(rows, m.utc_date, C.outcomes_for(m.sport))
        final = C.stale_book_close(s, m, book)            # the NFL grader's path; `book` keeps its rows on a switch
    else:
        final = C.grading_close(s, m)
        book = final
    if not C.priced(book) or (book or {}).get("source") in C.KALSHI_SOURCES:
        out["kind"] = (final or {}).get("source") if C.priced(final) else "unpriced"
        out["unknown"] = "d"
        return out
    out["kind"] = ("books, switched to kalshi" if (final or {}).get("reference") == "kalshi" else
                   "books, stale and unpriced" if (final or {}).get("stale_book") else
                   "books, stale and unswitched (three-way)" if (final or {}).get("stale_unswitched") else
                   f"books ({book.get('source') or 'odds'})")
    priced_rows = C.priced_rows(book)
    stamps = _stamps(s, priced_rows)
    out["distinct_stamps"] = len({x for x in stamps if x is not None})
    if book.get("stamp_rows") is None:                    # odds-table rows: bookmaker-level, retained
        out["books"] = sorted({r.bookmaker for r in priced_rows if getattr(r, "bookmaker", None)})
    else:
        out["books"] = None                               # a book snapshot: the consensus only, no bookmaker
    if not has_column:
        out["unknown"] = "a"
    elif not stamps or all(x is None for x in stamps):
        out["unknown"] = "b"
    elif any(x is None for x in stamps):
        out["unknown"] = "c"
    else:
        out["age"] = C.stamp_age_hours(min(stamps), m.utc_date)
    return out


def games(s, family: str, pl_since: datetime) -> list:
    """The graded games of a family, one per match, in kickoff order (see the module doc)."""
    from sqlalchemy import select

    from src.db.schema import Competition, Match, MatchStatus, Prediction, PredictionOutcome
    if family == "NFL":
        from src.walters.nfl_backtest import nfl_scoped
        from src.walters.nfl_predict import _is_pre_live
        q = (nfl_scoped(select(Match).join(Prediction, Prediction.match_id == Match.id))
             .where(Match.status == MatchStatus.FINISHED, Match.home_score.isnot(None), Match.away_score.isnot(None)))
        ms = [m for m in s.execute(q).scalars() if not _is_pre_live(m)]
    else:
        from src.db.schema import Sport
        q = (select(Match).join(Prediction, Prediction.match_id == Match.id)
             .join(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
             .join(Competition, Competition.id == Match.competition_id)
             .where(Match.sport == Sport.SOCCER, Competition.code == "PL", Match.utc_date >= pl_since,
                    PredictionOutcome.actual_home_score.isnot(None)))
        ms = list(s.execute(q).scalars())
    seen, out = set(), []
    for m in sorted(ms, key=lambda x: (x.utc_date or datetime.min, x.id)):
        if m.id not in seen:
            seen.add(m.id)
            out.append(m)
    return out


def dist(ages: list) -> dict:
    from src.walters.venue_quote_age import pct
    d = {"n": len(ages)}
    if ages:
        d.update(min=min(ages), max=max(ages), **{k: pct(ages, q) for k, q in QS})
    return d


def _dist_text(d: dict) -> str:
    if not d["n"]:
        return "n 0"
    return (f"n {d['n']} · min {d['min']:.2f} · " + " · ".join(f"{k} {d[k]:.2f}" for k, _ in QS)
            + f" · max {d['max']:.2f} (hours before the stored kickoff)")


def family_report(recs: list, family: str, void: list, echo) -> dict:
    from src.walters.close import STALE_BOOK_H
    n = len(recs) + len(void)
    stamped = [r for r in recs if r["age"] is not None]
    ages = [r["age"] for r in stamped]
    unk = {k: sum(1 for r in recs if r["unknown"] == k) for k in UNKNOWN}
    d = dist(ages)
    echo(f"\n== {family}: {n} graded game(s) · stamped {len(stamped)} · unknown {sum(unk.values())} · "
         f"re-dated (kept out) {len(void)}")
    for k, name in UNKNOWN.items():
        echo(f"  unknown {name}: {unk[k]}")
    for v in void:
        echo(f"  re-dated, kept out: {v}")
    first = min((r["kickoff"] for r in stamped), default=None)
    echo(f"  first stamped kickoff: {first:%Y-%m-%d %H:%M}Z" if first else "  first stamped kickoff: none")
    echo(f"  provider-stamp age (a lower bound on quote age): {_dist_text(d)}")
    den = len(recs)
    for _lo, _hi, name in BUCKETS:
        c = sum(1 for a in ages if bucket(a) == name)
        echo(f"    {name}: {c} of {den} (unknowns in the denominator)")
    over = sum(1 for a in ages if a > STALE_BOOK_H)
    echo(f"    more than STALE_BOOK_H ({STALE_BOOK_H} h, the code's switch): {over} of {den}")
    kinds: dict = {}
    for r in recs:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    echo("  close kinds: " + " · ".join(f"{k} {v}" for k, v in sorted(kinds.items(), key=lambda kv: str(kv[0]))))
    echo("  by kickoff slot (the receipt's own table; see the module doc):")
    slots: dict = {}
    for r in recs:
        slots.setdefault(r["slot"], []).append(r)
    by_slot = {}
    for name in sorted(slots):
        rs = slots[name]
        sd = dist([r["age"] for r in rs if r["age"] is not None])
        by_slot[name] = {"games": len(rs), "unknown": sum(1 for r in rs if r["age"] is None), **sd}
        echo(f"    {name}: games {len(rs)} · unknown {by_slot[name]['unknown']} · {_dist_text(sd)}")
    echo("  by book, only where bookmaker-level rows were retained (the odds table's last pre-kickoff session):")
    snap_only = sum(1 for r in recs if r["books"] is None)
    echo(f"    games whose close is a book snapshot (consensus only, no bookmaker): {snap_only}")
    books: dict = {}
    for r in recs:
        for b in r["books"] or ():
            books.setdefault(b, []).append(r)
    by_book = {}
    for b in sorted(books):
        rs = books[b]
        bd = dist([r["age"] for r in rs if r["age"] is not None])
        by_book[b] = {"games": len(rs), "unknown": sum(1 for r in rs if r["age"] is None), **bd}
        echo(f"    {b}: games {len(rs)} · unknown {by_book[b]['unknown']} · {_dist_text(bd)}")
    multi = sum(1 for r in recs if r["distinct_stamps"] > 1)
    echo(f"    games whose priced rows carry more than one distinct stamp: {multi} (the provider stamps an answer, "
         "not a book: a per-book age differs from the game's only where this is above 0)")
    return {"games": n, "stamped": len(stamped), "unknown": unk, "redated": len(void), "dist": d,
            "over_stale_book_h": over, "by_slot": by_slot, "by_book": by_book, "snapshot_only": snap_only,
            "multi_stamp_games": multi, "first_stamped_kickoff": first.isoformat() if first else None}


def report(pl_since: str = PL_SINCE, exports_dir: str | None = None, echo=print) -> dict:
    from src.db.database import ReadOnlyRefused, SessionLocal, has_source_time, readonly_scope
    since = _naive_utc(pl_since)
    url = SessionLocal.kw["bind"].url
    echo("BOOK-STAMP AGE RECEIPT (#382; ARCHITECT 2026-10-26 11:55 ET item (2), 2026-10-27 15:20 ET item 2): "
         "read-only, mode=ro, nothing written, no verdict")
    echo(f"database: {url.database} (this machine's receipt; the host and the laptop hold their own)")
    echo(f"PL from {since:%Y-%m-%d %H:%M}Z (--pl-since; the #629 merge by default) · NFL graded live games "
         "(Week 3, 2026-09-22, on)")
    closing, ex_files, ex_bad = None, 0, []
    if exports_dir:
        from src.walters.redated import closing_starts
        cs = closing_starts(exports_dir)
        ex_files, ex_bad = cs["files"], cs["unreadable"]
        if ex_files:
            closing = cs["rows"]
            echo(f"re-dates: labelled from the closing files in {exports_dir} (redated.void_label): files {ex_files} "
                 f"read · unreadable {len(ex_bad)}" + (f" ({', '.join(ex_bad)})" if ex_bad else ""))
        else:                                             # a missing or mistyped directory labels nothing
            echo(f"re-dates: UNLABELLED (no closing file read in {exports_dir}; unreadable {len(ex_bad)}): a re-dated "
                 "game's age reads against its current kickoff")
    else:
        echo("re-dates: unlabelled (no --exports): a re-dated game's age reads against its current kickoff")
    out = {}
    with readonly_scope() as s:
        from sqlalchemy import inspect
        ins = inspect(s.get_bind())
        missing = [t for t in NEEDED_TABLES if not ins.has_table(t)]
        if missing:
            raise ReadOnlyRefused(f"REFUSED: {url.database} has no {', '.join(missing)} table(s): not this app's "
                                  "database, nothing read")
        has_col = has_source_time("odds", s.get_bind())
        echo("odds.source_updated_at: " + ("present" if has_col else
                                           "ABSENT (every priced book close reads unknown (a); a game with no priced "
                                           "book close stays (d))"))
        for fam in ("NFL", "PL"):
            recs, void = [], []
            for m in games(s, fam, since):
                if closing is not None:
                    from src.walters.redated import void_label
                    lab = void_label(closing.get(m.id), m.utc_date)
                    if lab:
                        void.append(f"match {m.id} {m.away_team.name if m.away_team else '?'} @ "
                                    f"{m.home_team.name if m.home_team else '?'}: {lab}")
                        continue
                recs.append(game_record(s, m, fam, has_col))
            out[fam] = family_report(recs, fam, void, echo)
    echo("BOOK-STAMP-AGE-RECEIPT " + json.dumps({"pl_since": since.isoformat(), "exports": exports_dir,
                                                 "exports_files": ex_files, "exports_unreadable": ex_bad, **out},
                                                 sort_keys=True, default=str))
    return out


def _naive_utc(v) -> datetime:
    """--pl-since as the stored kickoffs are (naive UTC). A value with an offset is refused: the SQLite bind keeps the
    wall clock and drops the offset, so an ET time would silently read as UTC (review of #382)."""
    d = v if isinstance(v, datetime) else datetime.fromisoformat(v)
    if d.tzinfo is not None:
        raise ValueError(f"give the naive-UTC form (e.g. 2026-10-20T18:42:00), not an offset: {v!r}")
    return d


def _since(v: str) -> str:
    try:
        _naive_utc(v)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e) if "naive-UTC" in str(e) else f"not an ISO date-time (UTC): {v!r}")
    return v


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("--pl-since", default=PL_SINCE, type=_since,
                    help="PL games from this naive-UTC kickoff (default the #629 merge, 2026-10-20T18:42:00)")
    ap.add_argument("--exports", default=None,
                    help="the exports directory: re-dated games (redated.void_label) are listed and kept out")
    a = ap.parse_args(argv)
    from src.db.database import ReadOnlyRefused
    try:
        report(a.pl_since, a.exports)
    except ReadOnlyRefused as e:
        print(str(e))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
