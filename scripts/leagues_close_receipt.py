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
  - the projection: the season's stored fixtures (cancelled / postponed / stale_orphan left out) whose kickoff's UTC
    date is on or after the declaration date (2026-11-06), in kickoff order; the 60th's kickoff UTC date, every game
    assumed to get a three-way close. Fewer than 60 stored: no date, the count printed (law 4).
  - the capture quality per league and kickoff weekday (158 item 2(b)), the controlling capture's age printed with it,
    and every qualifying close more than 6 hours old at kickoff named (match, kickoff, capture time, age), counted in
    the close record all the same (ARCHITECT 2026-10-24, addendum 164 item 2(c): "a close more than 6 hours old is
    counted but named");
Then step (c)'s date as 156 item 1 rules it: the earliest of the four, the other three named.

The DB is the one DATABASE_URL names (else ./data/sports.db). A path with no file is refused before any import that
could open it: the receipt never creates a database. READ-ONLY for real (read_only below): before anything is read,
the app's sessions and its engine are rebound, for the receipt's run only, to an engine of their own on a mode=ro URI
of that file (sp_cutover's shot-gate idiom), so the app engine's connect hooks (PRAGMA journal_mode=WAL, the data/
mkdir) never run, SQLite itself refuses any write, and nothing is written. No machine role is read and none refuses:
the receipt runs on the laptop or the host alike, and imports nothing from deploy/hosting (ARCHITECT 2026-10-30 12:45
ET, addendum 185 D5, verbatim: "THE PARITY RECEIPT for the PR body: the operator runs the branch's parity script
READ-ONLY on the laptop (its read-only scope; a row-for-row arithmetic check on the laptop's data, stale is fine) — my
block when Code names the script and its arguments; the host receipt after v1.6.2's deploy is my block too and goes on
#322. The PR body says which machine produced its receipt.").

Then the parity receipt (158 item 2(a)) per league, PD first (159 item 6(a); PD is never fenced), then the four,
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

Run:  python3 scripts/leagues_close_receipt.py [--season 2026/27] [--declared 2026-11-06] [--rows]
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
DECLARED = date(2026, 11, 6)                 # 155 item 4(b): the declaration; 156 item 1: "on or after 2026-11-06"
REFUSED = 2                                  # the exit status of a refusal, as cli.py's soccer-expansion commands
DIVERGED = 1                                 # the exit status of a parity read that is not equal (a refusal outranks it)


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


@contextmanager
def read_only(f: Path):
    """For the block: src.db.database's SessionLocal and engine are an engine of their own on a mode=ro URI of `f`
    (no connect hook, no pragma, no mkdir; SQLite refuses a write), restored afterwards. session_scope, readonly_scope
    (which reads the bound file after "file:") and the has_* column checks all read through it."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from src.db import database
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


def lines(res: dict, season: str, declared: date) -> list[str]:
    from src.walters.paper import WINDOW_GAMES, close_record_line, quality_lines
    L = [f"LEAGUES CLOSE RECEIPT (ARCHITECT 2026-10-23, addendum 155 item 4(a); 156 item 1; #322) · read-only · "
         f"season {season} · declaration {declared}"]
    dated = []
    for code, r in res.items():
        if not r["games"]:
            L.append(f"- {code} · no stored game of {season}; seasons stored: {', '.join(r['seasons_stored']) or 'none'}")
            continue
        L.append(f"{code} {season} · stored games {r['games']} (cancelled / postponed / stale_orphan {r['not_games']})")
        L.append(close_record_line(code, r["record"]))
        L += quality_lines(code, r["quality"])
        L.append(come_line(code, r["to_come"]))
        if r["projected"]:
            p = r["projected"]
            dated.append((p["date"], code))
            L.append(f"  - {code} · the {WINDOW_GAMES}th fixture on or after {declared}: kickoff {p['date']} (UTC date; "
                     f"match {p['match_id']}) · {r['from_declared']} stored on or after {declared}")
        else:
            L.append(f"  - {code} · the {WINDOW_GAMES}th fixture on or after {declared}: not stored (only "
                     f"{r['from_declared']} on or after it); no date")
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
    ap.add_argument("--declared", default=DECLARED.isoformat(), help="the declaration date (default 2026-11-06)")
    ap.add_argument("--rows", action="store_true", help="print every parity row (default: the per-league lines only)")
    a = ap.parse_args(argv)
    f = db_file()
    if not f.is_file():
        raise SystemExit(f"no database at {f}: the receipt never creates one")
    declared = date.fromisoformat(a.declared)
    with read_only(f):
        print(f"database: {f.resolve()} (mode=ro; this machine's receipt: say which machine produced it, addendum 185 "
              "D5)")
        return _receipt(a, declared)


def _receipt(a, declared) -> int:
    from src.walters.paper import LEAGUES, leagues_season
    for ln in lines(leagues_season(LEAGUES, a.season, declared), a.season, declared):
        print(ln)
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
    rc = 0
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
