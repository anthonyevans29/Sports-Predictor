"""
LEAGUES CLOSE RECEIPT (ARCHITECT 2026-10-23, addendum 155 item 4(a); addendum 156 item 1; roadmap lane leagues, #322)
— read-only.

155 item 4(a), verbatim: "(a) by 2026-10-30 (code): a read-only receipt per league of the 2026/27 games FINISHED with a
three-way close under addendum 150's rule, and the close's own log-loss on them — the bar's denominator; the same read
for the games still to come this season that already hold a capture."

156 item 1, verbatim in part: "Receipt 4(a) computes it per league: the kickoff date of the 60th 2026/27 fixture of that
league scheduled on or after 2026-11-06 (every game assumed to get a three-way close); the earliest of the four is the
step's date, the other three named in the step's text."

Per league (SA, BL1, FL1, ELC; the season as the DB stores it, "2026/27" by default), from paper.leagues_season:
  - the FINISHED games scored against addendum 150's three-way Kalshi close exactly as results-tally's close record
    scores a three-way competition (paper._score_three; the same line, paper.close_record_line, and the unpriced line
    by cause): n with a close and the close's log-loss on them, the bar's denominator;
  - the games still to come (SCHEDULED, kickoff after the receipt's clock; not FINISHED, not LIVE, not cancelled /
    postponed / stale_orphan), read for the capture they hold now (stored before the clock): a capture that forms a
    close by three_way_close's rule behind the finished score's mismatched-legs guard, or the cause it does not
    (mismatched legs, or UNPRICED's), or none; LIVE games and SCHEDULED games past their kickoff are named and
    counted apart, never in the cohort;
  - the projection (SUPERSEDED by THE RECOUNT below, addendum 220 item 5: the receipt no longer projects from one
    date for every league): the season's stored fixtures (cancelled / postponed / stale_orphan left out) whose
    kickoff's UTC date is on or after the declaration date (2026-11-06), in kickoff order; the 60th's kickoff UTC date,
    every game assumed to get a three-way close. Fewer than 60 stored: no date, the count printed (law 4).
  - the capture quality per league and kickoff weekday (158 item 2(b)), the controlling capture's age printed with it,
    and every qualifying close more than 6 hours old at kickoff named (match, kickoff, capture time, age), counted in
    the close record all the same (ARCHITECT 2026-10-24, addendum 164 item 2(c): "a close more than 6 hours old is
    counted but named");
Then step (c)'s date as 156 item 1 rules it: the earliest of the four, the other three named.

THE RECOUNT (ARCHITECT 2026-11-02 13:10 ET, addendum 220 item 5, verbatim in part: "the calendar step of 12-06 (step
(c): the 60th fixture per league, ELC first) RECOUNTED from this stamp by Code from the stored schedule and written as
the projection it is"): the receipt's projection and its STEP (c) line are now counted per league from that league's
own start (paper.window_projection), PD included (PD, SA, FL1 and ELC declared at 2026-11-02T18:10:00Z, addendum 220
item 4): a declared league from its registry entry's declared_at (R3: a kickoff strictly after the instant; the ids
are window_ids() below, the cohort reader's DECLARATION_IDS, PD's leagues-pd-v1 among them by ARCHITECT 2026-11-02
16:35 ET, addendum 222 item 4(b)), or every league from --from INSTANT
when given (a UTC instant, "...Z"); a league with no entry (BL1 until its declaration, moved to 2026-11-09 by addendum
220 item 4) from the date --declared (default 2026-11-09), its UTC day on, and labelled so. It reads the schedule only
(a kickoff, a status, its raw code, the round label, an id; an AWD/WO row and a play-off-round row get no slot, as the
cohort reader gives them none): no score, no capture, no price, so it reads no figure of either arm on any game. A
projection: every other game is assumed to get a three-way close AND a stored prospective row; the window games the
cohort reader excludes for having no row (addendum 222 item 4(a), "no prospective row: the entry was not on the host's
tag") are named and counted by the reader (scripts/leagues_window.py) and its audit receipt, never here, and each one
moves a league's 60th one fixture later. An entry
whose declared_at is not a UTC instant, or whose competition is not the league's, is REFUSED (exit 2) for that league;
the others still print.

--db PATH (ADDENDUM 198 item 6(ii), ARCHITECT 2026-11-01 10:05 ET: "every `--db` on a copy opens it with
`immutable=1` beside `mode=ro`"): a .backup copy, read through a mode=ro + immutable=1 URI instead of the DATABASE_URL
file. Refused (exit 2), never created, when it is missing, under the repo's data/ (law 5), the app's configured
database, or has a -wal / -shm / -journal file beside it (immutable=1 would read the main file alone; a fresh .backup
copy has none): mlb_pitchers_gate.check_db, the standing --db fence, and nfl_v2_gate's sidecar rule.

The DB is the one DATABASE_URL names (else ./data/sports.db). A path with no file is refused before any import that
could open it: the receipt never creates a database. READ-ONLY for real (read_only below): before anything is read,
the app's sessions and its engine are rebound, for the receipt's run only, to an engine of their own on a mode=ro URI
of that file (sp_cutover's shot-gate idiom), so the app engine's connect hooks (PRAGMA journal_mode=WAL, the data/
mkdir) never run and SQLite itself refuses any write: no row is written and no file is created by the receipt. What
mode=ro does NOT promise: the app runs the DB in WAL mode (src/db/database.py), and SQLite opening a WAL database even
read-only may create or touch its -wal and -shm sidecar files beside it (a probe on SQLite 3.45.1 left an empty -wal
and a 32 KB -shm next to a cleanly closed WAL file); the database's contents are untouched. No machine role is read
and none refuses:
the receipt runs on the laptop or the host alike, and imports nothing from deploy/hosting (ARCHITECT 2026-10-30 12:45
ET, addendum 185 D5, verbatim: "THE PARITY RECEIPT for the PR body: the operator runs the branch's parity script
READ-ONLY on the laptop (its read-only scope; a row-for-row arithmetic check on the laptop's data, stale is fine) — my
block when Code names the script and its arguments; the host receipt after v1.6.2's deploy is my block too and goes on
#322. The PR body says which machine produced its receipt.").

Then the parity receipt (158 item 2(a)) per league, PD first (159 item 6(a); PD is fenced as the four are from its
leagues-pd-v1 declared_at, ARCHITECT 2026-11-02 16:35 ET, addendum 222 item 4(b)), then the four,
at the soccer-expansion-v1 RUN RECORD's frozen constants (leagues_window.run_record_constants: the constants the
shadow export binds to, ARCHITECT 2026-10-24, addendum 164 item 3: "bound to the run record's frozen parameters,
never by price_upcoming"); the production model's are printed beside them as a reference line, never the parity's
input. The shadow side is the export's own function (soccer_expansion.shadow_entry, through leagues_candidate.
parity), so the receipt proves the export path. It REFUSES with exit status 2, as cli.py's soccer-expansion
commands do, when the run record holds no constants, and per league when the league-season stores a stage label
the code cannot place (the gate's F3 refusal); the close part above still prints. A league whose parity read is
not equal (a row unequal, or a game priced by one path only) prints a NOT EQUAL line and exits 1 unless a
refusal made it 2.

THE WINDOW FENCE (ARCHITECT 2026-10-30, addendum 178 R8, verbatim: "FENCED: after a declaration the window's outcomes
have one reader, the cohort reader; guards_backtest refuses any other read of them until the verdict is recorded (the
NCAA fence's precedent)."): for a league whose verdict is not recorded (src/walters/leagues_window.py), the close
part scores and reads for quality only the finished games kicking off at or before its cut (the others are counted
"fenced" on the record's line) and the parity part compares only those games (the others counted "fenced"); the cut
is the entry's declared_at, or with no entry PRE_DECLARATION_CUT, 2026-10-30T15:00:00Z (the pre-declaration fence,
ARCHITECT 2026-10-30 11:00 ET, addendum 181 item 1(b)). The cohort reader, scripts/leagues_window.py, is the
window's one reader.

Run:  python3 scripts/leagues_close_receipt.py [--db COPY] [--from 2026-11-02T18:10:00Z] [--season 2026/27]
                                              [--declared 2026-11-09] [--rows]
Paste the whole output on #322.
"""
from __future__ import annotations

import argparse
import os
import sys
from contextlib import contextmanager
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SEASON = "2026/27"
# 155 item 4(b) and 156 item 1 dated it 2026-11-06; addendum 220 item 4 declared PD, SA, FL1 and ELC at
# 2026-11-02T18:10:00Z (their entries' declared_at is their start) and moved BL1's declaration to 2026-11-09: the date
# a league with no entry is projected from.
DECLARED = date(2026, 11, 9)
SIDECARS = ("-wal", "-shm", "-journal")      # nfl_v2_gate.SIDECARS: a --db copy with one beside it is refused
REFUSED = 2                                  # the exit status of a refusal, as cli.py's soccer-expansion commands
DIVERGED = 1                                 # the exit status of a parity read that is not equal (a refusal outranks it)


def window_ids() -> dict:
    """{code: registry id} of the five declarations of addendum 220, PD first: leagues_window.DECLARATION_IDS, PD's
    leagues-pd-v1 in it since ARCHITECT 2026-11-02 16:35 ET, addendum 222 item 4(b) (the reader and the fence on the
    four's code path), and the four's ids (addendum 181 item 6)."""
    from src.walters import leagues_window as lw
    return dict(lw.DECLARATION_IDS)


def starts(frm=None, declared: date = DECLARED) -> tuple[dict, dict, dict]:
    """(start, source, refused) per league of window_ids(): `frm` (a naive UTC instant) for every league when given;
    else a declared league's entry declared_at (R3), a league with no entry `declared` (a date). An entry whose
    competition is not its league, or whose declared_at is not a UTC instant, is refused for that league (law 4)."""
    from src.walters import leagues_window as lw
    st, src, bad = {}, {}, {}
    for code, eid in window_ids().items():
        if frm is not None:
            st[code], src[code] = frm, "--from"
            continue
        e = lw._registry_get(eid)
        if not isinstance(e, dict) or e.get("id") != eid:
            st[code] = declared
            src[code] = f"not declared: no entry {eid}; the date {declared} (--declared), its UTC day on"
            continue
        at = lw.parse_instant(e.get("declared_at"))
        if e.get(lw.LEAGUE_FIELD) != code:
            bad[code] = (f"{eid}: its {lw.LEAGUE_FIELD} is {e.get(lw.LEAGUE_FIELD)!r}, not {code!r} (addendum 181 "
                         "item 6)")
        elif at is None:
            bad[code] = (f"{eid}: declared_at {e.get('declared_at')!r} is not a UTC instant (R3: a date is never the "
                         "instant)")
        else:
            st[code], src[code] = at, f"{eid} declared_at {e['declared_at']}"
    return st, src, bad


def projection_lines(proj: dict, src: dict, bad: dict, season: str) -> list[str]:
    """The recount's lines (addendum 220 item 5): one per league in window_ids() order, then STEP (c) as 156 item 1
    rules it, the earliest named first and the others after it."""
    from datetime import datetime as _dt

    from src.walters.paper import WINDOW_GAMES
    L = [f"PROJECTION — step (c) RECOUNTED (ARCHITECT 2026-11-02 13:10 ET, addendum 220 item 5; 156 item 1's rule): "
         f"the {WINDOW_GAMES}th stored {season} fixture per league from its own start (cancelled / postponed / "
         "stale_orphan left out; AWD/WO rows (status_raw) and play-off-round rows (stage) left out, as the cohort "
         "reader gives them no slot; every other game assumed to get a three-way close). The schedule only: no "
         "score, capture or price is read. A projection, never a result"]
    dated = []
    for code in window_ids():
        if code in bad:
            L.append(f"  - {code} · REFUSED: {bad[code]}")
            continue
        p = proj[code]
        start = p["start"]
        frm = (f"kicking off strictly after {start:%Y-%m-%dT%H:%M:%SZ}" if isinstance(start, _dt)
               else f"kicking off on or after {start} (its UTC day on)")
        ex = p.get("excluded") or {}
        left = ("" if not any(ex.values()) else
                f" ({ex.get('awarded', 0)} AWD/WO and {ex.get('not_regular', 0)} play-off-round rows left out)")
        if p["projected"]:
            q = p["projected"]
            dated.append((q["date"], code))
            ko = f"{q['kickoff']:%Y-%m-%d %H:%M}Z"
            L.append(f"  - {code} · the {WINDOW_GAMES}th fixture {frm} ({src[code]}): kickoff {ko} (UTC date "
                     f"{q['date']}; match {q['match_id']}) · {p['after']} stored after the start{left}")
        else:
            L.append(f"  - {code} · the {WINDOW_GAMES}th fixture {frm} ({src[code]}): not stored (only {p['after']} "
                     f"stored after the start{left}; {p['games']} stored games of {season}); no date")
    if dated:
        dated.sort()
        first = dated[0]
        rest = ", ".join(f"{c} {d}" for d, c in dated[1:])
        missing = [c for c in window_ids() if c not in {c for _, c in dated}]
        L.append(f"STEP (c) (156 item 1; recounted from each league's start, addendum 220 item 5): due {first[0]} "
                 f"({first[1]}, the earliest)" + (f"; the others: {rest}" if rest else "")
                 + (f"; no date for {', '.join(missing)}" if missing else ""))
    else:
        L.append(f"STEP (c) (156 item 1; recounted from each league's start, addendum 220 item 5): no date (no league "
                 f"stores {WINDOW_GAMES} fixtures after its start)")
    return L


def copy_file(db) -> Path:
    """--db (addendum 198 item 6(ii)): mlb_pitchers_gate.check_db (an existing file, never created; never under the
    repo's data/, by path or identity; never the app's configured database), then nfl_v2_gate's sidecar rule (a -wal,
    -shm or -journal beside it is refused: immutable=1 would read the main file alone); never the DATABASE_URL file
    this receipt reads without --db. GateRefused otherwise."""
    from src.walters import mlb_pitchers_gate as mp
    path = mp.check_db(db)
    try:
        live = db_file().expanduser().resolve()
    except SystemExit:                               # not a SQLite URL: there is no live file to compare against
        live = None
    if live is not None and live.is_file() and (path == live or mp._same_file(path, live)):
        raise mp.GateRefused(f"--db {db} is the receipt's own DATABASE_URL file ({live}): --db reads a .backup copy "
                             "only; the live file is read without --db")
    for s in SIDECARS:
        if path.with_name(path.name + s).exists():
            raise mp.GateRefused(f"--db {db} has a {s} sidecar ({path.name + s}): not a fresh .backup copy; "
                                 "immutable=1 would ignore it; take a fresh .backup copy")
    return path


def db_file() -> Path:
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


def copy_uri(f: Path) -> str:
    """The --db copy's URI (addendum 198 item 6(ii)): the resolved path percent-encoded by Path.as_uri, then
    mode=ro&immutable=1 (mlb_pitchers_gate.COPY_URI_QUERY)."""
    from src.walters.mlb_pitchers_gate import COPY_URI_QUERY
    return f.resolve().as_uri() + COPY_URI_QUERY


@contextmanager
def read_only(f: Path, immutable: bool = False):
    """For the block: src.db.database's SessionLocal and engine are an engine of their own on a mode=ro URI of `f`
    (no connect hook, no pragma, no mkdir; SQLite refuses a write; a WAL database's -wal / -shm sidecars may still be
    created or touched, the module docstring says so), restored afterwards. session_scope, readonly_scope
    (which reads the bound file after "file:") and the has_* column checks all read through it. `immutable` (a --db
    copy, addendum 198 item 6(ii)): mode=ro AND immutable=1, so no sidecar is created or read; that URI is copy_uri's,
    percent-encoded (Path.as_uri) and handed to sqlite3 directly (mlb_pitchers_gate.readonly_session's pattern), so a
    '#' or '?' in the copy's path cannot cut the filename or drop mode=ro (a raw "file:" URL did both: SQLite opened,
    and created, the path up to that character). readonly_scope has no file to name on that engine and refuses
    (ReadOnlyRefused), never reads elsewhere; the receipt's path does not call it."""
    import sqlite3

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool

    from src.db import database
    if immutable:
        uri = copy_uri(f)
        eng = create_engine("sqlite://", poolclass=NullPool, future=True,
                            creator=lambda: sqlite3.connect(uri, uri=True, check_same_thread=False))
    else:
        eng = create_engine(f"sqlite:///file:{f.resolve().as_posix()}?mode=ro&uri=true",
                            connect_args={"uri": True, "check_same_thread": False}, future=True)
    saved = database.SessionLocal, database._engine
    database.SessionLocal = sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True,
                                         expire_on_commit=False)
    database._engine = eng
    try:
        yield eng
    finally:
        database.SessionLocal, database._engine = saved
        eng.dispose()


def come_line(code: str, c: dict) -> str:
    from src.walters.paper import MISMATCHED, UNPRICED
    causes = " · ".join(([f"mismatched legs {c[MISMATCHED]}"] if c[MISMATCHED] else [])
                        + [f"{text.split(' {k}')[0]} {c[key]}" for key, text in UNPRICED if c[key]])
    apart = " · ".join(f"{label} {c[key]}" for key, label in (("live", "live"),
                                                               ("past_kickoff", "past kickoff, not finished")) if c[key])
    return (f"  - {code} · to come {c['n']} · a capture forming a close now {c['close']}"
            + (f" · no close: {causes}" if causes else "")
            + (f" · not in the cohort: {apart}" if apart else ""))


def lines(res: dict, season: str, declared: date, recount: list[str] | None = None) -> list[str]:
    """The close part per league; then the projection: `recount` (projection_lines, addendum 220 item 5) in place of
    the date projection and its STEP (c) line when given, else the date projection from `declared` (156 item 1)."""
    from src.walters.paper import WINDOW_GAMES, close_record_line, quality_lines
    # with the recount, `declared` is only the start of a league with no registry entry (BL1 until 11-09): the header
    # names where each start comes from, never one declaration date for every league (addendum 220 item 4)
    starts_from = (f"each league's projection from its own start, named on its line (a declared league's registry "
                   f"declared_at; every league --from when given; a league with no entry from {declared}, --declared)"
                   if recount is not None else f"declaration {declared}")
    L = [f"LEAGUES CLOSE RECEIPT (ARCHITECT 2026-10-23, addendum 155 item 4(a); 156 item 1; #322) · read-only · "
         f"season {season} · {starts_from}"]
    dated = []
    for code, r in res.items():
        if not r["games"]:
            L.append(f"- {code} · no stored game of {season}; seasons stored: {', '.join(r['seasons_stored']) or 'none'}")
            continue
        L.append(f"{code} {season} · stored games {r['games']} (cancelled / postponed / stale_orphan {r['not_games']})")
        L.append(close_record_line(code, r["record"]))
        L += quality_lines(code, r["quality"])
        L.append(come_line(code, r["to_come"]))
        if recount is not None:
            continue
        if r["projected"]:
            p = r["projected"]
            dated.append((p["date"], code))
            L.append(f"  - {code} · the {WINDOW_GAMES}th fixture on or after {declared}: kickoff {p['date']} (UTC date; "
                     f"match {p['match_id']}) · {r['from_declared']} stored on or after {declared}")
        else:
            L.append(f"  - {code} · the {WINDOW_GAMES}th fixture on or after {declared}: not stored (only "
                     f"{r['from_declared']} on or after it); no date")
    if recount is not None:
        return L + recount
    if dated:
        dated.sort()
        first = dated[0]
        rest = ", ".join(f"{c} {d}" for d, c in dated[1:])
        missing = [c for c in res if c not in {c for _, c in dated}]
        L.append(f"STEP (c) (156 item 1): due {first[0]} ({first[1]}, the earliest)" + (f"; the others: {rest}" if rest
                                                                                         else "")
                 + (f"; no date for {', '.join(missing)} (fewer than {WINDOW_GAMES} stored)" if missing else ""))
    else:
        L.append(f"STEP (c) (156 item 1): no date (no league stores {WINDOW_GAMES} fixtures on or after {declared})")
    return L


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--season", default=SEASON, help="the season as the DB stores it (default 2026/27)")
    ap.add_argument("--declared", default=DECLARED.isoformat(),
                    help="the date a league with no registry entry is projected from (default 2026-11-09, BL1's "
                         "declaration by addendum 220 item 4's moved line)")
    ap.add_argument("--from", dest="frm", default=None,
                    help="a UTC instant (YYYY-MM-DDTHH:MM:SSZ) every league's projection counts from, strictly after "
                         "it (default: each declared league's registry declared_at, addendum 220 item 5)")
    ap.add_argument("--db", default=None,
                    help="a .backup copy outside data/, read mode=ro + immutable=1 (addendum 198 item 6(ii)); "
                         "default the DATABASE_URL file, mode=ro")
    ap.add_argument("--rows", action="store_true", help="print every parity row (default: the per-league lines only)")
    a = ap.parse_args(argv)
    declared = date.fromisoformat(a.declared)
    frm = None
    if a.frm is not None:
        from src.walters.leagues_window import parse_instant
        frm = parse_instant(a.frm)
        if frm is None:
            print(f"REFUSED: --from {a.frm!r} is not a UTC instant (YYYY-MM-DDTHH:MM:SSZ; R3: a date is never the "
                  "instant)")
            return REFUSED
    if a.db is not None:
        from src.walters.mlb_pitchers_gate import GateRefused
        try:
            f = copy_file(a.db)
        except GateRefused as e:
            print(f"REFUSED: {e}; nothing read")
            return REFUSED
    else:
        f = db_file()
        if not f.is_file():
            raise SystemExit(f"no database at {f}: the receipt never creates one")
    a.frm_instant = frm
    with read_only(f, immutable=a.db is not None):
        print(f"database: {f.resolve()} ({'--db copy, mode=ro + immutable=1' if a.db is not None else 'mode=ro'}; "
              "this machine's receipt: say which machine produced it, addendum 185 D5)")
        from src.walters.leagues_window import WindowRefused
        try:
            return _receipt(a, declared)
        except WindowRefused as e:           # Codex on #741: an unreadable registry (the fence's read included) is a
            print(f"REFUSED: {e}; the receipt is not read")   # refusal, exit 2, never a traceback
            return REFUSED


def _receipt(a, declared) -> int:
    from src.walters.paper import LEAGUES, leagues_season, window_projection
    st, src, bad = starts(getattr(a, "frm_instant", None), declared)
    recount = projection_lines(window_projection(st, a.season), src, bad, a.season)
    for ln in lines(leagues_season(LEAGUES, a.season, declared), a.season, declared, recount):
        print(ln)
    rc0 = REFUSED if bad else 0
    from src.walters import leagues_candidate as lc
    from src.walters import leagues_window as lw
    try:
        frozen = lw.run_record_constants()
    except lw.WindowRefused as e:    # as the soccer-expansion commands refuse (cli.py): exit 2, never a pass
        print(f"PARITY (158 item 2(a)): REFUSED: {e}; the receipt is incomplete without its parity part")
        return REFUSED
    print(f"PARITY (158 item 2(a)): the soccer-expansion-v1 run record's frozen constants {frozen['production_version']}"
          f" (rho {frozen['rho']}, Elo goal coefficient {frozen['elo_goal_coeff']}), the shadow export's binding (164 "
          "item 3); the shadow path is soccer_expansion.shadow_entry (leagues_candidate.predict_as_of), the gate path "
          "run_soccer_backtest")
    prod = lc.production_poisson()
    print("  - reference only, never the parity's input: the production soccer model "
          + (f"{prod[0]} (rho {prod[1]}, Elo goal coefficient {prod[2]}); "
             + ("equal to the frozen constants today" if (str(prod[0]), float(prod[1]), float(prod[2])) == (
                 frozen["production_version"], frozen["rho"], frozen["elo_goal_coeff"]) else
                "NOT equal to the frozen constants (the export never reads it)")
             if prod is not None else "not resolved"))
    from src.walters.soccer_expansion import ExpansionRefused
    rc = rc0
    for code in ("PD", *LEAGUES):
        try:
            p = lc.parity(code, frozen["rho"], frozen["elo_goal_coeff"], season=a.season)
        except ExpansionRefused as e:   # F3: an unplaceable stage label refuses, as the gate's run does
            print(f"{code} {a.season} · PARITY (158 item 2(a)) · REFUSED: {e}")
            rc = REFUSED
            continue
        for ln in lc.parity_lines(p, rows=a.rows):
            print(ln)
        if p["unequal"] or p["shadow_only"] or p["gate_only"]:   # Codex P1 on #663: a divergence is never a 0
            print(f"{code} {a.season} · PARITY (158 item 2(a)) · NOT EQUAL: unequal {p['unequal']} · priced by the "
                  f"shadow only {len(p['shadow_only'])} · by the gate only {len(p['gate_only'])}; the shadow path is "
                  f"not the gate's walk on this league-season")
            rc = max(rc, DIVERGED)
    return rc


if __name__ == "__main__":
    sys.exit(main())
