#!/usr/bin/env python3
"""THE DAY'S COVERAGE (ARCHITECT 2026-10-17 09:30 ET, addendum 107 item C7), verbatim:

"`python cli.py coverage [--date YYYY-MM-DD]` (default today, ET): for each competition with games that day — count of
games; whether a model is LIVE, MARKET-ONLY or SHADOW for it (from the registry/roadmap, not hard-coded strings); which
stored prediction rows exist for those games (model, computed_at) and which games have none; the closing groups the
watch will run (T-35 times, match ids) from the closing-watch schedule; and the export file each lands in
(exports/<name> by the existing naming). One line per competition, then the gaps in capitals ("PL: 4 GAMES, 0
PREDICTION ROWS — soccer-prematch has not run"). Reads the DB and the schedule only; writes nothing; no provider call.
It becomes the first step of every morning block and the source of the morning page's coverage map. Tests on the
throwaway DB: a day with rows, a day with a gap, a market-only sport."

THE AMENDMENT (ARCHITECT 2026-10-17 10:35 ET, addendum 111 items 1-2, #575), verbatim:
"1. Receipts are part of "the schedule". Yes: the watch's own receipt log (logs/receipts.jsonl), read-only, is exactly
how coverage knows a run is already done, and a run that has run is a fact of the day, not a guess. Print it as "done
(run <run_id>, <exit>)". Nothing else is read beyond the DB, the registry/roadmap, the watch's schedule inputs and that
log."
"2. UNKNOWN for competitions the lanes name only in prose — ruled: add the field, and derive MARKET-ONLY from code, so
UNKNOWN is rare. [...] Status derivation, in this order: LIVE if the competition has a closing family and a live model
in the registry (MLB, PL, NFL); SHADOW if a roadmap lane naming it is "confirming" or "declared" with a shadow export
(NHL v7, UNL, PD); MARKET-ONLY if the code already treats it so (the market-only competitions of docs/CLI.md /
`_refuse_shadow_league`, EXPANSION, KALSHI_CAPTURE_ONLY: NHL, NCAA, CL, EFL, UEL, UNL and the five expansion leagues);
UNKNOWN only when none applies. A competition can be both SHADOW and MARKET-ONLY (NHL): print "MARKET-ONLY · shadow
v7"."

    closing.py's own pieces, never re-implemented: a game's day is its America/New_York date (closing.ny_date, the
    date A1 gives a first pitch); VOID statuses are no game (closing.VOID); the closing groups are closing.groups() on
    closing.due()'s own inputs (the stored games plus the unpaged called-off ones, closing.with_called_off, less the
    games a closing has finished with, closing.covered_ids from the watch's receipts), over the family's games of the
    day at `now` (C2: the earliest unstarted start time, the games within the 10 minutes after it, then the next);
    each group is ahead, due now, or inside T-5 (a miss: no attempt, no file) by due()'s own thresholds; the run time
    is the start time less closing.RUN_LEAD_MIN; the file is exports/closing.closing_name() (addendum 40 item 2). A
    family this machine refuses (closing._family_refusal: SP_SKIP_FAMILIES, as the watch and closing-run read it)
    shows the refusal in place of its groups.

    A RUN DONE (item 1): a start time of the day for which the watch's receipt log holds a closing run (closing.
    _attempts: kind closing, neither a refusal nor a superseded run, 380.4) prints as `done (run <run_id>, <exit>)`,
    the ruling's words, the receipt's own `run_id` and `exit` (closing.run's receipt line), its match ids the run's own
    covers. Several runs for one start time: the latest success where there is one (closing.closing_state: any exit 0;
    a later failed run, an operator's re-run, never hides it), else the latest run, the log being append-only. A start
    time printed done is never printed as due. Where the watch still forms a group at it (closing.groups: games no
    closing has finished with), the done line says what the watch does with it, as the watch decides: inside T-5 a
    miss, no attempt (closing.due's "inside", closing.watch); ahead or due, superseded when the start time has a
    success or three attempts (closing.closing_state, as closing._under_lock reads it), else `(attempt N of 3: the
    watch tries again)`; and it names the group's games the run's covers do not hold. Then the export file the run
    landed in, the receipt's own `closing_file` (addendum 40 item 2; C7's "the export file each lands in"): `closing
    file exports/<name>`, or, where closing.py's write failed after the page went out (`closing_file_failed`, or an
    error in `closing_file`: the run is exit 0 and never run again), `closing file NOT written (exports/<name>):
    receipted and notified, not run again`, closing.py's own words. Only the receipt is read, nothing under exports/.
    A game a closing finished with whose run is no done line of the day (its run started the day before) keeps its
    line, `a closing finished with …`.

    The model status, per competition, in the ruled order, each read from data and code (no competition named here):
      LIVE         a closing family covers it (closing.FAMILIES[fam]["comps"]; the families are chains.CLOSING_FAMILIES,
                   C1) and the model its closing chain's predict step writes with resolves: `predict --sport S` the one
                   production row of S's model family in the DB's model_versions (training.MODEL_FAMILIES, as
                   _current_production_version reads it), `predict-nfl` nfl_predict.MODEL_VERSION (no model_versions
                   row; the predict path writes that constant). The registry holds no live model (the three predate
                   it): the model of record is what the predict path resolves. No production row (or more than one):
                   not LIVE, the reason kept on the line, and the derivation goes on.
      SHADOW       a roadmap lane whose `competitions` names it (addendum 111 item 2; never its prose) and (a) the lane
                   is confirming and its registry entry is confirming (a gate PASS in its declared confirmation window:
                   a shadow, never a call), or (b) in any other state, a chain in chains.py runs a shadow export for it
                   (a step whose command is one of SHADOW_EXPORTS, in a chain whose steps before it name the competition; an
                   operator-only chain is no schedule). (b) is how NHL qualifies (its lane is "to declare", and
                   nhl-daily runs export-nhl-predictions, v7, every day: the ruling's own example) and how a declared
                   lane would (NCAA's has no shadow export scheduled: CLAUDE.md "No college shadow ... until then").
                   The tag is the vN token of the shadow's id as the code names it (the registry id in (a), the shadow
                   module's model id in (b)), the full id where it has none. A chain outside its season gate on the
                   day runs nothing (sp_run.active_from: its active_from_env setting, else chains.py's date; sp_run
                   skips it, or fails it on a malformed setting): no schedule that day, the gate named on the line.
      MARKET-ONLY  the code's own market-only sets, imported (market_only_sets): desk_policy.SHADOW_VENUE_COMPS (the set
                   cli._refuse_shadow_league refuses), chains.EXPANSION_CODES, chains.KALSHI_CAPTURE_ONLY,
                   export._MARKET_ONLY_REASON (the market-only fixtures file's NHL, NCAA, UNL) and cup_coeff.EXAM_COMPS
                   (the cup track's competitions, market-only until its gate passes; EL is the adapter's alias for
                   UEL). SHADOW and MARKET-ONLY both: `MARKET-ONLY · shadow <tag>`.
      UNKNOWN      none applies (law 4), with every reason: no closing family or no live model, no lane names it or
                   none qualifies, in none of the market-only sets. A roadmap or registry that cannot be read judges no
                   shadow (MARKET-ONLY still holds from code, the line says the shadow was not judged).

    The gaps (capitals): a LIVE competition with a game that has no prediction row. Zero rows names the slate chain
    whose model step writes them ("— soccer-prematch has not run"), derived from chains.py: the closing chain's step
    whose command writes prediction rows (PREDICT_COMMANDS), found word for word in a chain that is neither a closing
    nor a freshen chain; no chain found, no hint. No chain runs a predict step for a SHADOW or MARKET-ONLY competition
    (its shadow, if any, prices in its own export), so no row is expected and no gap is claimed. A LIVE competition
    whose family this machine refuses (MLB on the host: a laptop duty) claims no gap either; its line shows the
    refusal. UNKNOWN competitions are named once, in capitals, with no gap judged for them.

THE SLATE LINE (ARCHITECT 2026-10-18, addendum 126 item 2(b), #590), verbatim: "`coverage` gains a SLATE line per LIVE
competition: the newest exports file of that family's slate kind that covers EVERY game of the day by match id, with
its exported_at and its PLAY/PASS counts; else "NO SLATE FILE — slate run due HH:MM ET" (or, where the watch is not
the machine, "— run block"). Its gap line in capitals: "NFL: 12 GAMES, ROWS 12, NO SLATE FILE". `coverage --json`
carries it; the Today tab shows it first."
    This module builds the line and returns it from coverage() as each competition's `slate`; the --json file (the Today
    tab's, #589, below) writes coverage()'s dict generically (every datetime ISO-8601 Z), so `slate` rides in it.
    The slate kind is the family's export_glob (closing.FAMILIES: mlb_MLB_*.json, nfl_predictions_*.json,
    soccer_PL_*.json, the names the slate stage and the prematch chains write; a closing file never matches). A file
    counts when it carries the Desk's calls (desk_meta), a row for at least one game of the day, a desk row for every
    game of the day (the competition's games, VOID ones aside) unstarted at its exported_at (item 4 below), and was
    exported on the ET day (item 5 below); of those, the one holding the most of the day's games stands, then the
    newest by its own exported_at (a re-export after a kickoff leaves the started game out, and the morning file still
    holds it). A row of a VOID game of the day is no game, and not beyond the day. A file that cannot be parsed, or one with no desk
    calls, is skipped with its reason on the line, never counted (law 4). ARCHITECT 2026-10-18, addendum 133 item 3(b):
    "A file of the glob with no `predictions` list is another kind: not a candidate, never listed as skipped (last_calls
    reads the same glob and passes such a file in silence). `skipped` is for a predictions export that cannot be parsed
    or has no desk calls, as built" (the results exports, mlb_MLB_results_<date>.json and soccer_PL_results_<date>.json,
    share the family globs and sit in exports/ every day). A file whose name dates it more than
    SLATE_SCAN_BACK_DAYS before the day, or after the day after, cannot hold the day and is not read.
    THE SLATE LINE'S FOLLOW-UP (ARCHITECT 2026-10-18, addendum 133 item 4; #602), verbatim:
    item 4: "(a), the follow-up PR: the SLATE line counts a file that holds every game of the day UNSTARTED at its
    exported_at, and names the ones left out on the line (`· started before it: <ids>`); no gap is claimed for a
    started game (nothing can run for it); the page's own LATE line is the record of the miss." A game counts as
    unstarted at a file's exported_at when its stored kickoff is after it (its status now is no reading of then: a
    game finished since was unstarted when an earlier file was written).
    item 5: "the day's SLATE file is a file EXPORTED ON THE ET DAY. An older file never stands as the day's slate,
    whatever it covers — the operator's rule is a sync on game day, and Saturday's window file on Sunday, or Sunday's
    NFL file on Monday night, is last sync's. With only such a file the line reads `NO SLATE FILE — slate run due HH:MM
    ET (newest exports/<file> exported <ET>, not today's)` and the gap is claimed." `older` is the newest file that
    would count but for its export day (the same tests: desk calls, every game of the day unstarted at its exported_at);
    it is named on every NO SLATE FILE line, first in its brackets.
    item 8: "N, PLAY and PASS count the DAY's games (rows whose match id is a game of the ET day); rows beyond the day
    follow as `· +<k> beyond the day` when k > 0 (the NFL 36-hour window, the soccer round). LADDER by name and `no
    desk call <n>` stand as built." The counts are closing.slate_calls over the competition's games of the day, as the
    slate page counts them (every call kind by name over the same rows); `beyond` is k.
    No file: the slate stage's due time (closing.slate_due);
    where this machine refuses the family (closing._family_refusal), the block to run (closing.slate_block). The gap is
    claimed for every LIVE competition with no slate file, a refused family's included: that is the operator's alert
    to run it by hand (item 1). coverage() carries it as `slate` on the competition. exports/ is read, never written.
    Item 2(c), "the morning page reads them as it reads the closing lines": with no file, the line reads the watch's
    slate receipts (kind slate and slate_miss, as closing.slate_state reads them). Where the watch runs no slate that
    day (a success, three attempts, or every game started: the every-game-started miss counts only while no game of
    the day is still unstarted, since a game re-dated later into the day is slated on the watch's next tick) the line
    names the block, "— run block <block> (<why>: the watch runs it no more)"; else the due time, with a failed attempt
    ("attempt k of 3 failed (<failed>): the watch tries again"), a miss ("missed (<reason>): the watch keeps trying")
    or a hold, when the day's newest slate receipt is the hold and the closing it names is one the watch will still run
    (closing.closing_open: a hold for a closing done, started, inside T-5 or out of attempts is stale and not shown)
    ("held since HH:MM ET (<the closing it waits for>): the slate runs after it"), in brackets.

THE JSON FILE (ARCHITECT 2026-10-18 08:20 ET, addendum 125 item 2(a), #589), verbatim:
"`python cli.py coverage --json [--out PATH]` writes the dict `deploy/hosting/coverage_map.coverage()` already returns
(date, now, competitions[], gaps[]; datetimes ISO-8601 Z), under `kind: "coverage_v1"`, plus `roadmap`: the lanes of
docs/roadmap.json with their competitions, status and dated ETAs, read as `cli.py roadmap` reads them (no new source of
truth; if a lane carries no date it prints "no ETA"). Default --out exports/coverage_<date>.json; the morning block's
existing `coverage` line gains `--json`; the mirror carries it (laptop/latest/coverage.json, host/latest after the
cutover). Read-only as today: mode=ro, no provider call, exit 0 whatever the gaps."
    document() is that dict, generically made JSON-ready (_plain: a field coverage() gains later rides along), plus
    the line's own words for what a reader must not compute (the Cockpit's Today tab: viewer, not engine) and the
    roadmap's lanes from src/roadmap.lanes_data (roadmap.load() and the print's own lane_lines(), on the coverage day;
    a lane whose earliest_live is null reads "no ETA"); a roadmap that cannot be read gives `roadmap: null` and
    `roadmap_unread` (law 4). The date in the default name is the coverage day; the file is written whole (beside its
    name, then moved into place), never under data/. The printed lines are the same, the header saying the one file
    was written, and one line after the gaps names it. Without --json the output is unchanged, byte for byte.

THE PAPER LINE (ARCHITECT 2026-10-20, addendum 146 item 5(a)), verbatim: "5. PAPER LANE for market-only competitions
(ruled 08:20 ET today, on the operator's "track them as if live"). No model number means no pick; nothing from this
lane enters the ledger, the P&L or the Cockpit positions; the Desk's call stays PASS noref. Two read-only pieces,
small, one PR after item 3 or riding (v): (a) coverage's SLATE line for a market-only competition carries, per game,
the Kalshi mid (two-way, or the three-way mids) and, where a shadow export exists for the day, the shadow's pick and
value side with their divergence against the mid, labelled PAPER and never a call. NHL today has a shadow (v7, FAILED
gate); CL and NCAA have none and show the market line only."
    As built (no competition is named here: the scope is the status): every competition whose status is MARKET-ONLY
    (the label MARKET-ONLY or MARKET-ONLY · shadow <tag>) with a game of the day that is not VOID gets a SLATE header,
    "<CODE> SLATE · PAPER, never a call (...)", and one PAPER line per game, in game order; LIVE, SHADOW-only and
    UNKNOWN competitions get none, nor does an all-void day. `slate` stays None for them, so no gap is claimed: PAPER
    never claims a gap. The board is read from the stored Kalshi market (src/walters/paper.py board_of: ML two-way,
    1X2 three-way). Two-way: the mid is close.close_from_kalshi's own (the HOME leg's last two-sided quote before
    kickoff, its mid, AWAY = 1 - mid, the 2c cap; an older quote is never substituted). Three-way: each leg's raw
    mid under the same filters, never normalized, with their sum: display only, never a close or a reference. A game
    whose legs are mismatched (kalshi_legs.mismatched, addendum 37 item 3) shows no mid. A started game shows its last
    pre-kickoff quote, tagged (started). The shadow is the last row any shadow export wrote before kickoff (each shadow
    module's own last_calls over exports/, the grade's semantics), with its exported_at; a row whose teams are not the
    game's, a row recorded for another kickoff (its utc_date more than desk_policy.DESK_CLOCK_DRIFT from the game's
    current start: redated.redated_label, the re-dated rule) or with a kickoff that cannot be read, or a game two
    shadow exports hold, is not shown; a shadow module whose files cannot be read hides only its own competitions'
    shadows (paper.shadow_comps), never another module's rows (Codex round 1 on #640). The value side is the side with the largest model p - mid
    above zero (the pick's own side eligible; judged at the printed precision, so a side under 0.05pp above its mid is
    none, said so; on a three-way prediction judged only with all three legs priced; a prediction whose legs are not
    the board's is never judged and carries no divergence); a divergence is (model p - mid) x 100 in pp. A game left
    with no mid by a stored capture time that cannot be parsed says so. coverage() carries it as `paper` on the
    competition, and the --json file adds `paper_lines`; `slate_line` is the header.

Read-only: the DB is opened mode=ro (sp_common.ro_connect: a missing file is refused, never created), plus
docs/roadmap.json, docs/registry/experiments.json, the watch's schedule inputs (chains.py, closing.py) and its receipt
log (sp_common.receipts_path(): SP_RECEIPTS or logs/receipts.jsonl, read as closing.receipts reads it; no file is no
receipt) and the settings _family_refusal and sp_run.active_from read. The PAPER line reads the stored Kalshi quotes
(odds_snapshots) on a second mode=ro connection, once per run and only when a MARKET-ONLY competition has games; the
legs guard's PRAGMA table_info(odds_snapshots) is its one statement that is not a SELECT, and it reads only. It reads
the shadow exports in exports/ through each shadow module's last_calls. No row and no receipt is written, and no export
but the --json file; no provider call; the family slate files in exports/ are read (the SLATE line), never written.
SQLite itself may leave its -wal/-shm sidecars beside a WAL file, as for every ro_connect reader. Exit 0 whatever the
gaps (it never stops a chain); a date that is not real, a DB that cannot be read, an --out without --json, an --out
under data/ or a --json file that cannot be written exits 2, and writes no file.
"""
from __future__ import annotations

import argparse
import importlib
import json
import re
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import closing as cl  # noqa: E402
import sp_common as c  # noqa: E402
from chains import CHAINS, CLOSING_FAMILIES, EXPANSION_CODES, FRESHEN_FAMILY, KALSHI_CAPTURE_ONLY  # noqa: E402

STATUSES = ("LIVE", "SHADOW", "MARKET-ONLY", "UNKNOWN")       # the order the lines are printed in
NO_ROWS_EXPECTED = ("SHADOW", "MARKET-ONLY")
# The two cli commands whose code writes prediction rows (law 1, read 2026-10-17: Prediction rows are constructed only
# in src/walters/training.py, reached by `predict`, and src/walters/nfl_predict.py, reached by `predict-nfl`; a test
# pins both. The web UI's per-match refresh and admin predict job reach training.generate_predictions too; no chain
# runs them).
PREDICT_COMMANDS = ("predict", "predict-nfl")
# The cli commands that write a shadow export (their rows carry engine model_shadow, the module's ENGINE) and the
# code's own name for each one's model: {command: (module, attribute)}. A test pins the four to the cli and to every
# module whose ENGINE is model_shadow.
SHADOW_EXPORTS = {
    "export-nhl-predictions": ("src.walters.nhl_shadow", "MODEL_VERSION"),
    "export-unl-predictions": ("src.walters.intl_shadow", "MODEL_VERSION"),
    "export-ncaa-predictions": ("src.walters.ncaa_shadow", "MODEL_VERSION"),
    "export-soccer-expansion-shadow": ("src.walters.soccer_expansion", "EID"),
}
_IN_CHUNK = 500              # ids per IN (...) list: under SQLite's variable limit


class Refused(RuntimeError):
    """Nothing could be read: the message says why (exit 2)."""


# ------------------------------------------------------------------------------------------------ the day --

def day_bounds(day: date) -> tuple[datetime, datetime]:
    """[lo, hi) in UTC: midnight to midnight in America/New_York (23 or 25 hours on a clock change): closing.day_bounds,
    the day the slate stage reads."""
    return cl.day_bounds(day)


def read_day(day: date) -> tuple[list[dict], dict, dict | str]:
    """The day's stored games (every competition, closing.schedule's shape plus `comp`; VOID ones included, marked),
    {match_id: [(model_version, computed_at)]} for them, and the production model rows {(sport, model_family):
    [version]} (or why model_versions could not be read). One read-only connection; nothing else is read."""
    lo, hi = day_bounds(day)
    fmt = "%Y-%m-%d %H:%M:%S"
    try:
        p = c.db_path()
    except ValueError as e:
        raise Refused(f"{e}: the coverage map reads a SQLite DB only") from None
    try:
        con = c.ro_connect(p)
    except FileNotFoundError:
        raise Refused(f"no database at {p}: nothing is created (the DB is opened read-only)") from None
    except sqlite3.Error as e:
        raise Refused(f"the DB at {p} cannot be read: {type(e).__name__}: {e}") from None
    try:
        rows = con.execute(
            "SELECT m.id, m.utc_date, m.status, co.code, ht.name, at.name FROM matches m "
            "JOIN competitions co ON co.id = m.competition_id "
            "LEFT JOIN teams ht ON ht.id = m.home_team_id LEFT JOIN teams at ON at.id = m.away_team_id "
            "WHERE m.utc_date >= ? AND m.utc_date < ? ORDER BY m.utc_date, m.id",
            (lo.strftime(fmt), hi.strftime(fmt))).fetchall()
        games = []
        for i, d, s, code, h, a in rows:
            try:
                start = cl.parse_utc(d)
            except (TypeError, ValueError):
                continue              # law 4: an unreadable start is no game of any day
            if cl.ny_date(start) != day:
                continue
            st = str(s or "").upper()
            games.append({"match_id": i, "start": start, "status": st, "home": h, "away": a, "comp": code,
                          "void": st in cl.VOID})
        ids = [g["match_id"] for g in games]
        preds: dict = {}
        for k in range(0, len(ids), _IN_CHUNK):
            part = ids[k:k + _IN_CHUNK]
            for mid, mv, at in con.execute(
                    f"SELECT match_id, model_version, computed_at FROM predictions WHERE match_id IN "
                    f"({','.join('?' * len(part))})", part).fetchall():
                preds.setdefault(mid, []).append((mv, at))
        prod: dict | str = {}
        try:                          # the sport column holds the enum's name: compared lower-cased, as its readers do
            for sp, fam, ver in con.execute("SELECT lower(sport), model_family, version FROM model_versions "
                                            "WHERE status = 'production' ORDER BY id").fetchall():
                prod.setdefault((sp, fam), []).append(ver)
        except sqlite3.Error as e:    # law 4: no live model is read from a table that cannot be read
            prod = f"model_versions cannot be read ({type(e).__name__}: {e})"
    except sqlite3.Error as e:
        raise Refused(f"the DB at {p} cannot be read: {type(e).__name__}: {e}") from None
    finally:
        con.close()
    return games, preds, prod


# ------------------------------------------------------------------------------------------- the status --

def family_of(code: str) -> str | None:
    """The closing family that covers the competition (closing.FAMILIES comps), or None."""
    return next((f for f, d in cl.FAMILIES.items() if code in d["comps"]), None)


def read_ledgers(roadmap_path=None, registry_path=None) -> tuple[list[dict], dict, str | None]:
    """(roadmap lanes, {registry id: entry}, why they could not be read or None). Read-only."""
    from src import roadmap as rm
    from src.walters import registry as reg
    try:
        lanes = rm.load(roadmap_path)["lanes"]
    except rm.RoadmapError as e:
        return [], {}, f"the roadmap cannot be read: {e}"
    try:
        entries = {e["id"]: e for e in reg.load(registry_path or reg.LEDGER)}
    except (OSError, ValueError, KeyError, TypeError) as e:
        return [], {}, f"the registry cannot be read: {type(e).__name__}"
    return lanes, entries, None


def _predict_model(step: list[str], prod) -> tuple[str | None, str]:
    """`predict --sport S`: generate_predictions resolves the production row of S's model family
    (training._current_production_version: model_versions, status production, model_family MODEL_FAMILIES[S])."""
    from src.db.schema import Sport
    from src.walters.training import MODEL_FAMILIES
    try:
        sport = Sport(step[step.index("--sport") + 1])
        mf = MODEL_FAMILIES[sport]
    except (ValueError, IndexError, KeyError):
        return None, f"its predict step names no sport with a model family ({' '.join(step)})"
    if isinstance(prod, str):
        return None, prod
    vs = prod.get((sport.value, mf), [])
    if len(vs) == 1:
        return vs[0], f"production {mf} {vs[0]}"
    return None, (f"no production {mf} row in model_versions" if not vs else
                  f"{len(vs)} production {mf} rows in model_versions (the predict path resolves exactly one)")


def _predict_nfl_model(step: list[str], prod) -> tuple[str | None, str]:
    """`predict-nfl` writes nfl_predict.MODEL_VERSION on every row; it has no model_versions row."""
    from src.walters.nfl_predict import MODEL_VERSION
    return MODEL_VERSION, f"predict-nfl writes nfl_predict.MODEL_VERSION {MODEL_VERSION}"


PREDICT_MODEL = {"predict": _predict_model, "predict-nfl": _predict_nfl_model}   # one per PREDICT_COMMANDS


def live_model(fam: str, prod) -> tuple[str | None, str]:
    """The model a closing family's calls come from, as its closing chain's predict step resolves it: (model, where it
    was read), or (None, why there is none)."""
    chain = CLOSING_FAMILIES[fam]
    steps = [s for s in CHAINS[chain]["steps"] if s and s[0] in PREDICT_COMMANDS]
    if not steps:
        return None, f"closing chain {chain} has no predict step"
    return PREDICT_MODEL[steps[0][0]](steps[0], prod)


def market_only_sets() -> list[tuple[str, frozenset]]:
    """The code's own market-only sets (addendum 111 item 2), imported, never copied: [(where, codes)]."""
    from src.walters.cup_coeff import EXAM_COMPS
    from src.walters.desk_policy import SHADOW_VENUE_COMPS
    from src.walters.export import _MARKET_ONLY_REASON
    return [("SHADOW_VENUE_COMPS (_refuse_shadow_league)", frozenset(SHADOW_VENUE_COMPS)),
            ("chains.EXPANSION_CODES", frozenset(EXPANSION_CODES)),
            ("chains.KALSHI_CAPTURE_ONLY", frozenset(KALSHI_CAPTURE_ONLY)),
            ("export._MARKET_ONLY_REASON", frozenset(_MARKET_ONLY_REASON)),
            ("cup_coeff.EXAM_COMPS", frozenset(EXAM_COMPS))]


def scheduled_shadows() -> list[dict]:
    """The shadow exports a chain runs (chains.py), each {chain, command, model: the code's id for its model, comps:
    the competitions the chain's steps before the export name}. An operator-only chain has no timer: no schedule."""
    out = []
    for name, ch in CHAINS.items():
        if ch.get("operator_only"):
            continue
        steps = [s for s in ch.get("steps") or [] if s]
        for j, s in enumerate(steps):
            if s[0] in SHADOW_EXPORTS:
                # the competitions the steps BEFORE the export name: the reads that feed it (#707: intl-daily's cup
                # schedule reads come after export-unl-predictions and are no shadow of the cups)
                comps = {x[i + 1] for x in steps[:j] for i, a in enumerate(x[:-1]) if a == "--competition"}
                mod, attr = SHADOW_EXPORTS[s[0]]
                out.append({"chain": name, "command": s[0], "model": getattr(importlib.import_module(mod), attr),
                            "comps": comps})
    return out


def chain_inactive(name: str, day: date) -> str | None:
    """sp_run's own season gate (sp_run.active_from: the chain's active_from_env setting, else chains.py's ruled date):
    why the chain runs nothing on `day`, or None. A malformed setting fails the chain in sp_run: it runs nothing."""
    import sp_run
    try:
        gate = sp_run.active_from(name)
    except SystemExit as e:
        return f"{name} runs nothing ({e})"
    if gate and day.isoformat() < gate["date"]:
        return f"{name} inactive until {gate['date']} [{gate['source']}]"
    return None


def shadow_tag(model_id: str) -> str:
    """The vN token of a shadow's id as the code names it (nhl_elo_v7_xg_margin_no_na v7, intl-elo-v2 v2,
    soccer-expansion-v1 v1); the full id where it has none (ncaa_elo_v1r)."""
    return next((t for t in re.split(r"[-_]", model_id) if re.fullmatch(r"v[0-9]+", t)), model_id)


def shadow_of(code: str, lanes: list[dict], entries: dict, day: date) -> tuple[str | None, str]:
    """(the shadow's tag, where it was read) when a lane naming the competition makes it SHADOW, else (None, why not).
    The module docstring's rule: a confirming lane whose registry entry is confirming, or a lane in any state whose
    competition a chain runs a shadow export for on `day` (a chain outside its season gate runs nothing)."""
    naming = [ln for ln in lanes if code in (ln.get("competitions") or [])]
    if not naming:
        return None, f"no roadmap lane names {code}"
    runs = [r for r in scheduled_shadows() if code in r["comps"]]
    off = {r["chain"]: chain_inactive(r["chain"], day) for r in runs}     # sp_run's season gate, on the day
    gated = "; ".join(sorted({v for v in off.values() if v}))
    runs = [r for r in runs if not off[r["chain"]]]
    whys = []
    for ln in naming:
        src = f"roadmap lane {ln['lane']}: {ln['state']}"
        rid = ln.get("registry_id")
        if ln["state"] == "confirming" and rid:
            e = entries.get(rid)
            if e is None:
                whys.append(f"{src}; registry id {rid} is not in the registry")
                continue
            if e.get("status") != "confirming":
                whys.append(f"{src}; registry {rid}: {e.get('status')} (the lane and the registry disagree)")
                continue
            return shadow_tag(rid), f"{src}; registry {rid}: confirming"
        if runs:
            r = runs[0]
            return shadow_tag(r["model"]), f"{src}; chain {r['chain']} runs {r['command']} ({r['model']})"
        whys.append(f"{src}, no shadow export scheduled for {code} (chains.py{': ' + gated if gated else ''})")
    return None, "; ".join(whys)


def model_status(code: str, lanes: list[dict], entries: dict, prod, unread: str | None = None,
                 day: date | None = None) -> dict:
    """{status: LIVE | SHADOW | MARKET-ONLY | UNKNOWN, label: as printed, from: where it was read, shadow: the shadow's
    tag or None}, in the ruled order (addendum 111 item 2), on `day` (default today, ET). The table is the module
    docstring's."""
    fam = family_of(code)
    if fam:
        model, src = live_model(fam, prod)
        if model:
            return {"status": "LIVE", "label": "LIVE", "from": f"closing family {fam}; {src}", "shadow": None}
        why_not_live = f"closing family {fam}, but {src}"     # not LIVE: the derivation goes on, the reason kept
    else:
        why_not_live = f"no closing family covers {code}"
    market = [where for where, codes in market_only_sets() if code in codes]
    day = day or cl.ny_date(cl.clock())
    tag, why = (None, f"shadow not judged: {unread}") if unread else shadow_of(code, lanes, entries, day)
    if tag and market:                # the ruling's both: "MARKET-ONLY · shadow v7"
        return {"status": "MARKET-ONLY", "label": f"MARKET-ONLY · shadow {tag}",
                "from": "; ".join(([why_not_live] if fam else []) + [", ".join(market), why]), "shadow": tag}
    if tag:
        return {"status": "SHADOW", "label": f"SHADOW {tag}",
                "from": "; ".join(([why_not_live] if fam else []) + [why]), "shadow": tag}
    if market:
        return {"status": "MARKET-ONLY", "label": "MARKET-ONLY",
                "from": "; ".join(([why_not_live] if fam else []) + [", ".join(market), why]), "shadow": None}
    return {"status": "UNKNOWN", "label": "UNKNOWN",
            "from": "; ".join([why_not_live, why, "in none of the code's market-only sets"]), "shadow": None}


def writer_chains(fam: str) -> list[str]:
    """The chains whose model step writes the family's prediction rows, from chains.py: the closing chain's step whose
    command is in PREDICT_COMMANDS, word for word in a chain that is neither a closing chain nor a freshen chain
    (sp_run names those freshen:<family>). MLB: mlb-preslate. SOCCER and NFL: none since ARCHITECT 2026-10-25,
    addendum 166 item 6(B) retired soccer-prematch's and nfl-predict's predict steps (the closing watch's slate stage
    runs them), so their gap line carries no hint; it was soccer-prematch and nfl-predict."""
    model = [s for s in CHAINS[CLOSING_FAMILIES[fam]]["steps"] if s and s[0] in PREDICT_COMMANDS]
    skip = set(CLOSING_FAMILIES.values()) | {f"freshen:{f}" for f in FRESHEN_FAMILY.values()}
    return [name for name, ch in CHAINS.items()
            if name not in skip and any(s in model for s in ch.get("steps") or [])]


# ------------------------------------------------------------------------------- the PAPER line (5(a)) --
# ARCHITECT 2026-10-20, addendum 146 item 5(a): per game of a MARKET-ONLY competition, the Kalshi mid and the shadow's
# pick and value side with their divergence against it, labelled PAPER and never a call (the module docstring).

TWO_SHADOWS = "two shadow exports hold it"
# What a stored value of the wrong kind raises inside one game's PAPER read: that game's part reads "cannot be read
# (<Error>): not shown" and the rest of coverage prints whole (law 4; coverage never stops a chain)
_UNREADABLE = (TypeError, ValueError, AttributeError, KeyError, IndexError)


def read_paper(ids) -> dict:
    """The stored Kalshi quotes of the games `ids`, on a second mode=ro connection (as read_day opens it), closed in
    finally: {"rows": {match_id: [SimpleNamespace(id, source, market, selection, captured_at (aware UTC), yes_bid,
    yes_ask, bad_time)]}, "mismatched": {match_id: [events]} (kalshi_legs.mismatched on this connection, the one
    helper), "legs": (tickers, current, homes) for paper.close_row_mismatched on the row(s) a mid reads (#641 item 1:
    each stored row's market_ticker by row id, each game's newest legs, kalshi_legs.homes_of over all their events;
    ({}, {}, {}) with the legs guard off or no ticker column, as kalshi_legs reads it), "unread": None, or why nothing
    could be read (law 4)}. A stored capture time that cannot be parsed is kept
    as captured_at None with bad_time True: no quote before any kickoff, and a game left with no mid by it says so
    (_paper_kalshi). No table: "the DB has no odds_snapshots table", and nothing else runs (no PRAGMA)."""
    from src.walters import kalshi_legs
    out: dict = {"rows": {}, "mismatched": {}, "legs": ({}, {}, {}), "unread": None}
    ids = sorted({int(i) for i in ids})
    try:
        con = c.ro_connect(c.db_path())
    except (ValueError, FileNotFoundError, sqlite3.Error) as e:
        out["unread"] = f"odds_snapshots cannot be read ({type(e).__name__}: {e})"
        return out
    try:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'odds_snapshots'").fetchone():
            out["unread"] = "the DB has no odds_snapshots table"
            return out
        legs_on = kalshi_legs.GUARD["on"] and kalshi_legs.has_tickers(con)
        tic = "market_ticker" if legs_on else "NULL"
        tickers: dict = {}
        for k in range(0, len(ids), _IN_CHUNK):
            part = ids[k:k + _IN_CHUNK]
            for rid, mid, market, sel, at, bid, ask, ticker in con.execute(
                    f"SELECT id, match_id, market, selection, captured_at, yes_bid, yes_ask, {tic} FROM odds_snapshots "
                    f"WHERE source = 'kalshi' AND match_id IN ({','.join('?' * len(part))})", part).fetchall():
                if ticker is not None:
                    tickers[rid] = ticker
                bad = False
                try:
                    cap = cl.parse_utc(at) if at is not None else None
                except (TypeError, ValueError):
                    cap, bad = None, True     # law 4: an unreadable capture time is no quote before any kickoff
                out["rows"].setdefault(mid, []).append(SimpleNamespace(
                    id=rid, source="kalshi", market=market, selection=sel, captured_at=cap, yes_bid=bid, yes_ask=ask,
                    bad_time=bad))
        out["mismatched"] = kalshi_legs.mismatched(con, ids)
        if legs_on and ids:                  # the rows a mid reads, judged with each side's newest legs (#641 item 1)
            current = kalshi_legs.current_tickers(con, ids)
            events = {kalshi_legs.event_of(x) for x in tickers.values()}
            events |= {kalshi_legs.event_of(x) for legs in current.values() for ts in legs.values() for x in ts}
            out["legs"] = (tickers, current, kalshi_legs.homes_of(con, events))
    except sqlite3.Error as e:
        out.update(rows={}, mismatched={}, legs=({}, {}, {}), unread=f"odds_snapshots cannot be read ({type(e).__name__}: {e})")
    finally:
        con.close()
    return out


def shadow_rows() -> tuple[dict, dict]:
    """({match_id: the last shadow row written before its kickoff, or None where two shadow exports hold it},
    {module: "<name>: <Error>"} for each shadow module whose files could not be read): each shadow module's own
    last_calls over exports/ (SHADOW_EXPORTS' modules, each once). A module that fails is tracked on its own (Codex
    round 1 P2 on #640): it hides its own competitions' shadows only (paper_view), never another module's rows.
    Read-only."""
    out: dict = {}
    held: dict = {}
    failed: dict = {}
    for mod in dict.fromkeys(m for m, _ in SHADOW_EXPORTS.values()):
        try:
            calls = importlib.import_module(mod).last_calls(str(c.REPO / cl.SLATE_DIR))
        except (OSError, ValueError, AttributeError, TypeError, KeyError) as e:
            failed[mod] = f"{mod.rsplit('.', 1)[1]}: {type(e).__name__}"
            continue
        for mid, r in calls.items():
            held.setdefault(mid, []).append(mod)
            out[mid] = r
    for mid, mods in held.items():
        if len(mods) > 1:
            out[mid] = None           # not shown: two shadow exports hold it
    return out, failed


def shadow_unread(code: str, failed: dict) -> str | None:
    """Why the competition's shadows are not read: the failures of the modules whose competitions hold it
    (paper.shadow_comps, from each module's own code), "; "-joined; a failed module whose competitions are not known
    hides every competition's (law 4: never a false "none"). None when every module of the competition was read."""
    from src.walters import paper
    comps = paper.shadow_comps()
    why = [w for mod, w in failed.items() if mod not in comps or code in comps[mod]]
    return "; ".join(why) if why else None


def _paper_kalshi(rows: list, mism, start: datetime, legs: tuple = ({}, {}, {}),
                  match_id=None) -> tuple[str | None, dict | None, str | None]:
    """(board, the Kalshi part, why there is none) for one game. Mismatched legs show no mid: each side's newest legs
    (`mism`, kalshi_legs.mismatched), then the row(s) the mid reads judged with them (paper.close_row_mismatched on
    `legs`, read_paper's; kalshi_close_read on a two-way board, leg_mids_read on a three-way one), RULED (ARCHITECT
    2026-10-21, addendum 152 item 4(a), #641 item 1): "judge the rows a PAPER mid reads with close_row_mismatched; a
    hit prints "mismatched legs ... no mid"."""
    from src.walters import paper
    nomatch = "mismatched legs ({}): no mid (addendum 37 item 3)"
    if mism:
        return paper.board_of(rows), None, nomatch.format(", ".join(mism))
    board = paper.board_of(rows)
    if board is None:
        return None, None, "no quote stored"
    if board == "mixed":
        return board, None, "ML and 1X2 rows both stored: not read"
    nomid = "no mid (no two-sided pre-kickoff quote within the 2c cap)"
    # a stored quote whose time cannot be read: its own reason, only for a row the mid reads (two-way: the HOME leg)
    if any(getattr(r, "bad_time", False) and (board != "two-way" or r.selection == "HOME") for r in rows):
        nomid = "cannot be read (a capture time cannot be read): not shown"
    tickers, current, homes = legs
    read = paper.kalshi_close_read(rows, start) if board == "two-way" else paper.leg_mids_read(rows, start)
    bad = paper.close_row_mismatched(read, tickers, current.get(match_id), match_id, homes)
    if bad:
        return board, None, nomatch.format(", ".join(bad))
    if board == "two-way":
        k = paper.two_way_mid(rows, start)
        if k is None:
            return board, None, nomid
        q = k["kalshi"]
        return board, {"fair": dict(k["fair"]), "bid": q["bid"], "ask": q["ask"], "spread_c": q["spread_c"],
                       "captured_at": k["captured_at"]}, None
    legs = paper.leg_mids(rows, start)
    if not any(legs.values()):
        return board, None, nomid
    mids = [v["mid"] for v in legs.values() if v]
    return board, {"legs": legs, "sum": sum(mids) if all(legs.values()) else None}, None


def _paper_shadow(r: dict | None, g: dict, kalshi: dict | None) -> tuple[dict | None, str | None]:
    """(the shadow part, why there is none) for one game's shadow row."""
    from src.walters import paper, redated
    if (r.get("home_team"), r.get("away_team")) != (g["home"], g["away"]):
        return None, f"row names {r.get('away_team')} @ {r.get('home_team')}, not this game: not shown"
    # the row's recorded kickoff against the game's current start, by the re-dated rule (redated.redated_label: more
    # than desk_policy.DESK_CLOCK_DRIFT apart; Codex round 1 P2 on #640, R17): a row for another kickoff is not shown
    if redated.as_utc(r.get("utc_date")) is None:
        return None, "the row's kickoff cannot be read: not shown"
    if redated.redated_label(r.get("utc_date"), g["start"]):
        return None, "the row is for another kickoff (re-dated): not shown"
    try:
        at = cl.parse_utc(r["exported_at"])
    except (KeyError, TypeError, ValueError):
        return None, "its exported_at cannot be read: not shown"
    # last_calls keeps a row written before its RECORDED kickoff; within the re-dated rule's hour that can be after the
    # game's CURRENT start (Codex round 2 P2 on #640): a row exported at or after it is an in-play row, compared as UTC
    if redated.as_utc(at) >= redated.as_utc(g["start"]):
        return None, "exported at or after the current kickoff (an in-play row): not shown"
    pred = r.get("prediction")
    pred = {} if pred is None else pred
    if paper.unreadable(pred):
        return None, "the row cannot be read: not shown"
    fair = None
    if kalshi and "fair" in kalshi:
        fair = kalshi["fair"]
    elif kalshi and "legs" in kalshi:
        fair = {k: (v["mid"] if v else None) for k, v in kalshi["legs"].items()}    # every leg of the board named
    v = paper.shadow_view(pred, fair)
    if v["pick"] is None or v["pick_p"] is None:
        return None, "the row carries no pick: not shown"
    return {"model_version": r.get("model_version"), "gate_verdict": r.get("gate_verdict"), "exported_at": at,
            **v}, None


def paper_view(x: dict, by_id: dict, kal: dict, shadows: tuple, now: datetime) -> dict:
    """The PAPER data of one MARKET-ONLY competition (the module docstring's rule): {label, ruling, kalshi_unread,
    shadow_unread, games: [{match_id, away, home, start, started, board, kalshi, kalshi_why, mismatched, shadow,
    shadow_why}]}. Every datetime aware UTC; no raw shadow or export row is copied in."""
    from src.walters import paper
    rows_by, failed = shadows
    unread = shadow_unread(x["code"], failed)          # only this competition's modules (Codex round 1 on #640)
    out = {"label": paper.PAPER_LABEL, "ruling": paper.PAPER_RULING, "kalshi_unread": kal["unread"],
           "shadow_unread": unread, "games": []}
    for mid in x["games"]:
        g = by_id[mid]
        d = {"match_id": mid, "away": g["away"], "home": g["home"], "start": g["start"], "started": cl.started(g, now),
             "board": None, "kalshi": None, "kalshi_why": None, "mismatched": None, "shadow": None, "shadow_why": None}
        if kal["unread"]:
            d["kalshi_why"] = f"not read ({kal['unread']})"
        else:
            d["mismatched"] = kal["mismatched"].get(mid) or None
            try:
                d["board"], d["kalshi"], d["kalshi_why"] = _paper_kalshi(kal["rows"].get(mid, []), d["mismatched"],
                                                                         g["start"], kal.get("legs", ({}, {}, {})),
                                                                         mid)
            except _UNREADABLE as e:
                d["board"], d["kalshi"], d["kalshi_why"] = None, None, f"cannot be read ({type(e).__name__}): not shown"
        if unread:
            d["shadow_why"] = f"not read ({unread})"
        elif mid not in rows_by:
            d["shadow_why"] = f"none (no shadow row before kickoff in {cl.SLATE_DIR}/)"
        elif rows_by[mid] is None:
            d["shadow_why"] = f"{TWO_SHADOWS}: not shown"
        else:
            try:
                d["shadow"], d["shadow_why"] = _paper_shadow(rows_by[mid], g, d["kalshi"])
            except _UNREADABLE as e:
                d["shadow"], d["shadow_why"] = None, f"cannot be read ({type(e).__name__}): not shown"
        out["games"].append(d)
    return out


def _priced(d: dict) -> bool:
    """A game with a Kalshi mid: two-way with its mid, or three-way with all three leg mids."""
    k = d["kalshi"]
    return bool(k) and ("fair" in k or all(k["legs"].values()))


def paper_header(x: dict) -> str:
    """The MARKET-ONLY competition's SLATE header (addendum 146 item 5(a))."""
    p = x["paper"]
    n = len(p["games"])
    kal = (f"Kalshi not read ({p['kalshi_unread']})" if p["kalshi_unread"]
           else f"Kalshi mid {sum(1 for d in p['games'] if _priced(d))} of {n}")
    sh = (f"shadow not read ({p['shadow_unread']})" if p["shadow_unread"]
          else f"shadow {sum(1 for d in p['games'] if d['shadow'])} of {n}")
    return (f"{x['code']} SLATE · {p['label']} (market-only: no ledger, no P&L, no position; {p['ruling']}) · "
            f"{_n(n, 'game')} · {kal} · {sh}")


def _f3(v) -> str:
    return "—" if v is None else f"{v:.3f}"


def _kalshi_text(d: dict) -> str:
    k = d["kalshi"]
    if not k:
        return f"Kalshi: {d['kalshi_why']}"
    if "fair" in k:
        m = k["fair"]["HOME"]
        return (f"Kalshi mid HOME {m:.3f} / AWAY {1 - m:.3f} (bid {k['bid']:.2f}, ask {k['ask']:.2f}, "
                f"{k['spread_c']:g}c; captured {cl.et(k['captured_at'])})")
    legs = k["legs"]
    caps = sorted(v["captured_at"] for v in legs.values() if v)
    when = cl.et(caps[0]) + (f" to {cl.et(caps[-1])}" if caps[-1] != caps[0] else "")
    s = f"sum {k['sum']:.3f}" if k["sum"] is not None else "sum —"
    return ("Kalshi mids " + " / ".join(f"{sel} {_f3((legs.get(sel) or {}).get('mid'))}" for sel in legs)
            + f" (raw per leg, not normalized, display only; {s}; captured {when})")


def _shadow_text(d: dict) -> str:
    from src.walters import paper
    v = d["shadow"]
    if not v:
        return f"shadow: {d['shadow_why']}"
    head = f"shadow {v['model_version']} ({v['gate_verdict']}; exported {cl.et(v['exported_at'])}): "
    differ = paper.board_differs(v["value_why"])             # the prediction is not the board's shape: not judged
    div = (f"({v['pick_div_pp']:+.1f}pp vs mid)" if v["pick_div_pp"] is not None
           else f"({v['value_why']}: no divergence)" if differ else "(no mid: no divergence)")
    pick = f"pick {v['pick']} {v['pick_p']:.3f} {div}"
    if v["value_side"]:
        val = f"value side {v['value_side']} ({v['value_div_pp']:+.1f}pp)"
    elif v["value_why"] in ("no mid", "a leg has no mid") or differ:
        val = f"value side not judged ({v['value_why']})"
    else:
        val = f"value side none ({v['value_why']})"
    return f"{head}{pick}; {val}"


def paper_lines(x: dict) -> list[str]:
    """The MARKET-ONLY competition's PAPER lines, one per game in game order ([] for any other competition)."""
    p = x.get("paper")
    if not p:
        return []
    return [f"{x['code']} SLATE · PAPER · {d['match_id']} {d['away']} @ {d['home']} {cl.et(d['start'])[11:]}"
            + (" (started)" if d["started"] else "") + f" · {_kalshi_text(d)} · {_shadow_text(d)}"
            for d in p["games"]]


# ------------------------------------------------------------------------------------------- the report --

def _n(k: int, word: str) -> str:
    return f"{k} {word}" + ("" if k == 1 else "S" if word.isupper() else "s")


def _run_time(start: datetime, day: date) -> str:
    """The run's time (T-35) in ET, written HH:MM ET; with its date when that is not the day's."""
    t = cl.utc(start) - timedelta(minutes=cl.RUN_LEAD_MIN)
    return cl.et(t)[11:] if cl.ny_date(t) == day else cl.et(t)


def watch_groups(fam: str, games: list[dict], day: date, now: datetime) -> dict:
    """The family's closing groups of the day: the runs done (the watch's receipt log, addendum 111 item 1), then the
    groups the watch will run, as it forms them: closing.groups() on closing.due()'s own inputs (the stored games plus
    the unpaged called-off ones, less the games a closing has finished with, read from the watch's receipts), the day
    standing in for schedule()'s window. A done group is the run shown for its start time (state done, its run_id and
    exit, its `file` the receipt's closing_file and `file_failed` whether closing.py failed to write it): the latest
    success where there is one, else the latest run. A group the watch still forms at a done start time is no second
    group: the done one carries what the watch does with it (`next`: "miss" inside T-5, "superseded" with a success or
    three attempts, "again" otherwise; `open` when again) and the group's games its covers do not hold (`left`). Each
    other group's state at `now` is due()'s: ahead (before T-35), due (T-35 to T-5: the watch runs it now) or inside
    (inside T-5: a miss, no attempt, no file). {"groups" by start time, "finished": the ids a closing has finished with,
    "unread": why the receipts could not be read}."""
    comps = cl.FAMILIES[fam]["comps"]
    comp_of = {g["match_id"]: g["comp"] for g in games}
    fam_games = [g for g in games if g["comp"] in comps and not g["void"]]

    def comps_of(ids) -> list[str]:
        # a called-off game no longer stored on the day is its family's (one competition) or no one's
        return sorted({comp_of.get(i, comps[0] if len(comps) == 1 else None) for i in ids} - {None})
    try:
        covered = cl.covered_ids(fam)
        runs = cl._attempts(fam)      # the closing runs: refusals and superseded runs are neither (380.4)
        fam_games = [g for g in cl.with_called_off(fam, fam_games, now) if cl.ny_date(g["start"]) == day]
    except (OSError, sqlite3.Error) as e:
        return {"groups": [], "finished": set(), "unread": f"the watch's receipts cannot be read: {type(e).__name__}"}
    done: dict = {}                   # start -> the run shown: the latest success, else the latest run (append-only)
    attempts: dict = {}
    for r in runs:
        try:
            s = cl.parse_utc(r["start"])
        except (KeyError, TypeError, ValueError):
            continue                  # law 4: a run with no readable start time is no group of any day
        if cl.ny_date(s) == day:
            if r.get("exit") == 0 or done.get(s, {}).get("exit") != 0:
                done[s] = r           # a later failed run never hides a success (closing_state: any exit 0)
            attempts[s] = attempts.get(s, 0) + 1
    out = [{"start": s, "run_at": s - timedelta(minutes=cl.RUN_LEAD_MIN), "state": "done",
            "match_ids": [x.get("match_id") for x in r.get("covers") or []], "run_id": r.get("run_id"),
            "exit": r.get("exit"), "attempts": attempts[s], "open": False, "next": None, "why": None, "left": [],
            # a run that recorded no covers is still a run of the day: its family's, where it has one competition
            "comps": comps_of(x.get("match_id") for x in r.get("covers") or [])
            or (list(comps) if len(comps) == 1 else []),
            "file": (r.get("closing_file") or {}).get("file"),
            # closing.py's write that failed after the page went out: exit 0, never run again (_closing)
            "file_failed": bool(r.get("closing_file_failed") or (r.get("closing_file") or {}).get("error"))}
           for s, r in done.items()]
    try:
        for gr in cl.groups(fam_games, now, covered):
            m = cl.minutes_to(gr["start"], now)
            state = "ahead" if m > cl.RUN_LEAD_MIN else "due" if m >= cl.NO_ATTEMPT_INSIDE_MIN else "inside"
            if gr["start"] in done:   # a done start time is never printed as due (addendum 111 item 1)
                d = next(x for x in out if x["start"] == gr["start"])
                st = cl.closing_state(fam, cl.iso_z(gr["start"]))      # what closing._under_lock reads
                # what the watch does with it: inside T-5 closing.watch() records a miss and makes no attempt; ahead
                # or due, _under_lock supersedes a start time with a success or three attempts; else it runs again
                d["next"] = ("miss" if state == "inside" else "superseded"
                             if st["success"] or st["attempts"] >= cl.MAX_ATTEMPTS else "again")
                if d["next"] == "superseded":                           # _under_lock's own words
                    d["why"] = "a successful closing" if st["success"] else f"{st['attempts']} attempts"
                d["open"] = d["next"] == "again"
                d["left"] = [g["match_id"] for g in gr["games"] if g["match_id"] not in d["match_ids"]]
                d["comps"] = sorted(set(d["comps"]) | set(comps_of(d["left"])))
                continue
            out.append({"start": gr["start"], "run_at": gr["start"] - timedelta(minutes=cl.RUN_LEAD_MIN),
                        "match_ids": [g["match_id"] for g in gr["games"]], "state": state,
                        "comps": comps_of(g["match_id"] for g in gr["games"]),
                        "file": None if state == "inside" else
                        f"{cl.CLOSING_FILE_DIR}/{cl.closing_name(fam, gr['start'])}"})
    except OSError as e:              # closing_state reads the log again
        return {"groups": [], "finished": set(), "unread": f"the watch's receipts cannot be read: {type(e).__name__}"}
    out.sort(key=lambda g: g["start"])
    return {"groups": out, "finished": covered, "unread": None}


SLATE_SCAN_BACK_DAYS = 8      # export-nfl-predictions --week looks 8 days ahead: an older name cannot hold the day
_NAME_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def slate_view(fam: str, games: list[dict], day: date, refused: str | None, exports=None,
               now: datetime | None = None, void=frozenset()) -> dict:
    """The SLATE line's data for one LIVE competition (addendum 126 item 2(b), the module docstring's rule): {family,
    file: exports/<name> or None, exported_at, rows, calls, beyond (rows beyond the day), started_before (the day's
    games the file leaves out, started before its exported_at), older ({file, exported_at}: the newest file that would
    count but was exported before the ET day, or None; None when a file stands), due, block, refused, skipped: [(name,
    why)]}, and what the watch's slate receipts say (slate_receipts; `now` judges a game unstarted). `void`: the match
    ids of the competition's games of the day called off (a row of one is no game, and not beyond the day). Read-only."""
    ex = Path(exports) if exports is not None else c.REPO / cl.SLATE_DIR
    ids = {g["match_id"] for g in games}
    out = {"family": fam, "file": None, "exported_at": None, "rows": None, "calls": None, "beyond": None,
           "started_before": [], "older": None,
           "due": cl.slate_due(min(g["start"] for g in games), day), "block": cl.slate_block(fam, day),
           "refused": refused, "skipped": []}
    try:
        paths = sorted(ex.glob(cl.FAMILIES[fam]["export_glob"])) if ex.is_dir() else []
    except OSError as e:
        out["skipped"].append((f"{cl.SLATE_DIR}/", f"cannot be listed: {type(e).__name__}"))
        paths = []
    best = None
    for p in paths:
        m = _NAME_DATE.search(p.name)
        try:
            named = date.fromisoformat(m.group(0)) if m else None
        except ValueError:
            named = None
        if named and not day - timedelta(days=SLATE_SCAN_BACK_DAYS) <= named <= day + timedelta(days=1):
            continue                  # named for another week: it cannot hold the day
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(doc, dict) and not isinstance(doc.get("predictions"), list):
                continue              # another kind (a results export): no candidate, never skipped (addendum 133 3(b))
            at = cl.parse_utc(doc["exported_at"])
            have = {r.get("match_id") for r in doc["predictions"] if r.get("desk")}
            held = {r.get("match_id") for r in doc["predictions"]}
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
            out["skipped"].append((p.name, f"cannot be parsed: {type(e).__name__}"))
            continue                  # law 4: never counted
        if not doc.get("desk_meta"):
            out["skipped"].append((p.name, "no desk calls"))
            continue
        # item 4: every game of the day unstarted at the file's exported_at (its kickoff after it) has a desk row; a
        # file with no row for any game of the day holds none of its slate (a file exported after every kickoff that
        # holds only tomorrow's games, say), whatever that test says
        if not ids & held or not {g["match_id"] for g in games if g["start"] > at} <= have:
            continue
        if cl.ny_date(at) > day:      # exported after the ET day: no slate of it, and no older file of it either
            continue
        if cl.ny_date(at) < day:      # item 5: exported before the ET day, it never stands as the day's slate
            if out["older"] is None or (at, p.name) > (out["older"]["exported_at"], Path(out["older"]["file"]).name):
                out["older"] = {"file": f"{cl.SLATE_DIR}/{p.name}", "exported_at": at}
            continue
        # the file that holds the most of the day's games stands (a re-export after a kickoff leaves the started game
        # out: the morning file still holds it); of the same reach, the newest
        key = (len(ids & held), at, p.name)
        if best is None or key > best[0]:
            best = (key, p, doc, held)
    if best:
        out["exported_at"], out["file"] = best[0][1], f"{cl.SLATE_DIR}/{best[1].name}"
        out["rows"], out["calls"] = cl.slate_calls(best[2], ids)      # item 8: the day's games
        out["beyond"] = cl.beyond_day(best[2], ids, void)
        out["started_before"] = sorted(ids - best[3])                 # item 4: no row in it, started before it
        out["older"] = None           # named on NO SLATE FILE lines only
    out.update(slate_receipts(fam, day, games, now))
    return out


def _hold_open(rec: dict, now: datetime | None) -> bool:
    """A slate's hold receipt still says what the slate waits for at `now`: the closing it names (`closing`: family,
    start) is one the watch will still run (closing.closing_open, closing_ahead's own test: its start more than five
    minutes off, no success, under three attempts). A hold for a closing done, started, inside T-5 or out of attempts
    is stale (the #590 review's feed-down note: "the slate runs after it" about a closing long done). Without `now`,
    or with a closing that cannot be read (law 4), as the receipt says."""
    clo = rec.get("closing") or {}
    if now is None:
        return True
    try:
        return cl.closing_open(clo["family"], cl.parse_utc(clo["start"]), now)
    except (KeyError, TypeError, ValueError, OSError):
        return True


def slate_receipts(fam: str, day: date, games: list[dict] | None = None, now: datetime | None = None) -> dict:
    """What the watch's slate receipts say of the family's day (addendum 126 item 2(c): "the morning page reads them as
    it reads the closing lines"), read as closing.slate_state reads them: {attempts, success, last_failed (the newest
    failed attempt's `failed`), succeeded ({file, at} of the newest success), misses (the day's slate_miss reasons, in
    order), held ({why, at} when the day's newest slate receipt is a hold whose closing the watch will still run at
    `now`: the slate waits for it; _hold_open), done (the watch runs no slate that day: a success, three attempts, or
    every game started), unread}. The every-game-started miss is done only while no game of `games` is unstarted at
    `now` (the watch decides from the schedule, not from the miss: a game re-dated later into the day is slated on its
    next tick); without them, as the miss says."""
    out = {"attempts": 0, "success": False, "last_failed": None, "succeeded": None, "misses": [], "held": None,
           "done": False, "unread": None}
    day_s = day.isoformat()
    try:
        runs = cl._slate_attempts(fam, day_s)
        mine = [r for r in cl.receipts((cl.SLATE_KIND, cl.SLATE_MISS_KIND))
                if r.get("family") == fam and r.get("date") == day_s]
        misses = [r.get("reason") for r in mine if r.get("kind") == cl.SLATE_MISS_KIND and r.get("reason")]
    except OSError as e:
        out["unread"] = f"the watch's receipts cannot be read: {type(e).__name__}"
        return out
    ok = [r for r in runs if r.get("exit") == 0]
    out["attempts"], out["success"] = len(runs), bool(ok)
    out["last_failed"] = next((r.get("failed") or "error" for r in reversed(runs) if r.get("exit") != 0), None)
    if ok:
        try:
            at = cl.parse_utc(ok[-1].get("completed_at") or ok[-1].get("ran_at"))
        except (TypeError, ValueError):
            at = None                 # law 4: an unreadable time is shown as none
        out["succeeded"] = {"file": ok[-1].get("file"), "at": at}
    out["misses"] = list(dict.fromkeys(misses))
    if (mine and mine[-1].get("kind") == cl.SLATE_KIND and mine[-1].get("held")
            and _hold_open(mine[-1], now)):
        try:
            at = cl.parse_utc(mine[-1].get("queued_at"))
        except (TypeError, ValueError):
            at = None                 # law 4: an unreadable time is shown as none
        out["held"] = {"why": mine[-1]["held"], "at": at}
    unstarted = games is not None and now is not None and any(not cl.started(g, now) for g in games)
    out["done"] = (bool(ok) or len(runs) >= cl.MAX_ATTEMPTS
                   or (cl.SLATE_ALL_STARTED in out["misses"] and not unstarted))
    return out


def coverage(day: date | None = None, now: datetime | None = None, roadmap_path=None, registry_path=None) -> dict:
    """The day's coverage map: what the lines print, as data (the morning page's source). Refused when the DB
    cannot be read."""
    now = cl.utc(now or cl.clock())
    day = day or cl.ny_date(now)
    games, preds, prod = read_day(day)
    lanes, entries, unread = read_ledgers(roadmap_path, registry_path)
    views: dict = {}                  # family -> watch_groups(), read once per family
    comps: list[dict] = []
    for code in sorted({g["comp"] for g in games}):
        mine = [g for g in games if g["comp"] == code and not g["void"]]
        void = [g for g in games if g["comp"] == code and g["void"]]
        st = model_status(code, lanes, entries, prod, unread, day)
        by_model: dict = {}
        for g in mine:
            for mv, at in preds.get(g["match_id"], []):
                m = by_model.setdefault(mv, {"model_version": mv, "rows": 0, "earliest": None, "latest": None,
                                             "computed": {}})       # computed: {match_id: its row's computed_at}
                m["rows"] += 1
                try:
                    t = cl.parse_utc(at)
                except (TypeError, ValueError):
                    m["computed"].setdefault(g["match_id"], None)
                    continue          # an unreadable computed_at is counted, never dated
                if m["computed"].get(g["match_id"]) is None or t > m["computed"][g["match_id"]]:
                    m["computed"][g["match_id"]] = t
                m["earliest"] = t if m["earliest"] is None or t < m["earliest"] else m["earliest"]
                m["latest"] = t if m["latest"] is None or t > m["latest"] else m["latest"]
        fam = family_of(code)
        refused = cl._family_refusal(fam) if fam else None
        groups, started, finished, closing_unread = [], [], [], None
        if fam:
            started = [g["match_id"] for g in mine if cl.started(g, now)]      # past their closing: no group
        if fam and not refused:
            if fam not in views:
                views[fam] = watch_groups(fam, games, day, now)
            v = views[fam]
            groups = [gr for gr in v["groups"] if code in gr["comps"]]
            shown = {i for gr in groups if gr["state"] == "done" for i in gr["match_ids"]}
            finished = [g["match_id"] for g in mine if g["match_id"] in v["finished"] and not cl.started(g, now)
                        and g["match_id"] not in shown]    # its run is no done line of the day
            closing_unread = v["unread"]
        slate = (slate_view(fam, mine, day, refused, now=now, void={g["match_id"] for g in void})
                 if fam and st["status"] == "LIVE" and mine else None)
        comps.append({"code": code, "games": [g["match_id"] for g in mine], "void": [(g["match_id"], g["status"])
                                                                                   for g in void],
                      "status": st["status"], "status_label": st["label"], "status_from": st["from"],
                      "shadow": st["shadow"], "family": fam, "refused": refused,
                      "rows": sorted(by_model.values(), key=lambda m: m["model_version"]),
                      "without_rows": [g["match_id"] for g in mine if not preds.get(g["match_id"])],
                      "writers": writer_chains(fam) if fam else [], "groups": groups, "started": started,
                      "finished": finished, "closing_unread": closing_unread, "slate": slate})
    comps.sort(key=lambda x: (STATUSES.index(x["status"]), x["code"]))
    # THE PAPER LINE (addendum 146 item 5(a)): every MARKET-ONLY competition with games; read once, only then
    paper_comps = [x for x in comps if x["status"] == "MARKET-ONLY" and x["games"]]
    kal = shadows = None
    if paper_comps:
        kal = read_paper([i for x in paper_comps for i in x["games"]])
        shadows = shadow_rows()
    by_id = {g["match_id"]: g for g in games}
    paper_codes = {x["code"] for x in paper_comps}
    for x in comps:
        x["paper"] = paper_view(x, by_id, kal, shadows, now) if x["code"] in paper_codes else None
    return {"date": day, "now": now, "competitions": comps, "gaps": gap_lines(comps)}


def gap_lines(comps: list[dict]) -> list[str]:
    """The gaps, in capitals (the spec's example: "PL: 4 GAMES, 0 PREDICTION ROWS — soccer-prematch has not run")."""
    out = []
    for x in comps:
        rows = sum(m["rows"] for m in x["rows"])
        # refused here: its line names the refusal, the rows are another machine's
        if x["status"] == "LIVE" and not x.get("refused") and x["without_rows"]:
            line = f"{x['code']}: {_n(len(x['games']), 'GAME')}, {_n(rows, 'PREDICTION ROW')}"
            if len(x["without_rows"]) < len(x["games"]):
                line += f", NONE FOR {', '.join(map(str, x['without_rows']))}"
            elif x["writers"]:
                line += f" — {' or '.join(x['writers'])} has not run"
            out.append(line)
        if x.get("slate") and not x["slate"]["file"]:    # addendum 126 item 2(b), a refused family's too (item 1)
            out.append(f"{x['code']}: {_n(len(x['games']), 'GAME')}, ROWS {rows}, NO SLATE FILE")
    unknown = [x["code"] for x in comps if x["status"] == "UNKNOWN"]
    if unknown:
        one = len(unknown) == 1
        out.append(f"MODEL STATUS UNKNOWN: {', '.join(unknown)} — no gap is judged for {'it' if one else 'them'} "
                   f"({'its line gives' if one else 'each line gives'} the reason)")
    return out


def _computed_text(m: dict) -> str:
    """A model's computed_at in ET: the range when its rows differ (an old row is never hidden behind a fresh one);
    "" when no row's computed_at could be read."""
    if not m["latest"]:
        return ""
    if m["earliest"] != m["latest"]:
        return f"computed {cl.et(m['earliest'])} to {cl.et(m['latest'])}"
    return f"latest {cl.et(m['latest'])}"


def _computed(m: dict) -> str:
    t = _computed_text(m)
    return f" ({t})" if t else ""


def _group_text(g: dict, day: date) -> str:
    """One closing group: done (addendum 111 item 1: "done (run <run_id>, <exit>)", then what the watch does with the
    start time, if it still forms a group there, then the closing file the run's receipt names, or NOT written), due
    now, ahead, or a miss."""
    head = f"T-{cl.RUN_LEAD_MIN} {_run_time(g['start'], day)} [{', '.join(map(str, g['match_ids']))}]"
    if g["state"] == "done":
        tail = {"again": f" (attempt {g['attempts']} of {cl.MAX_ATTEMPTS}: the watch tries again)",
                "miss": " (inside T-5: no further attempt, the watch records a miss)",
                "superseded": f" ({g['why']}: the watch runs it no more)"}.get(g["next"], "")
        if g["left"]:
            tail += f"; not in its covers: {', '.join(map(str, g['left']))}"
        if g["file_failed"]:          # closing.py's own words: the page went out, the file did not (addendum 40 item 2)
            tail += f"; closing file NOT written ({g['file']}): receipted and notified, not run again"
        elif g["file"]:
            tail += f"; closing file {g['file']}"
        return f"{head} done (run {g['run_id']}, {g['exit']}){tail}"
    if g["state"] == "inside":
        return f"{head} inside T-5: no attempt, no file (the watch records a miss)"
    return f"{head} → {g['file']}" + (" (due now)" if g["state"] == "due" else "")


def _slate_done_why(s: dict) -> str:
    """Why the watch runs no slate today, from its receipts (closing._slate_under_lock's own words)."""
    if s["success"]:
        ok = s["succeeded"] or {}
        at = f" at {cl.et(ok['at'])[11:]}" if ok.get("at") else ""
        return f"a successful slate{at} ({ok.get('file')}), but no file of the day holds every game of the day"
    if s["attempts"] >= cl.MAX_ATTEMPTS:
        return f"{s['attempts']} attempts, the last failed ({s['last_failed']})"
    return f"missed: {cl.SLATE_ALL_STARTED}"


def slate_line(x: dict) -> str | None:
    """The competition's SLATE line (addendum 126 item 2(b)); a MARKET-ONLY competition's PAPER header (addendum 146
    item 5(a)); or None (neither LIVE nor MARKET-ONLY)."""
    if x.get("paper"):
        return paper_header(x)
    s = x.get("slate")
    if not s:
        return None
    old = s.get("older")              # addendum 133 item 4, item 5: the newest file of an earlier ET day, named
    older = (f"newest {old['file']} exported {cl.et(old['exported_at'])}, not today's" if old else None)
    if s["file"]:
        t = (f"{s['file']} · exported {cl.et(s['exported_at'])} · {cl.calls_text(s['calls'])}"
             f"{cl.beyond_text(s.get('beyond'))}")
        if s.get("started_before"):   # item 4: counted without them; no gap is claimed for a started game
            t += f" · started before it: {', '.join(map(str, s['started_before']))}"
    elif s["refused"]:
        t = f"NO SLATE FILE — run block {s['block']}" + (f" ({older})" if older else "")
    elif s.get("done"):               # the watch runs no slate today: the block is the operator's (item 2(b))
        t = (f"NO SLATE FILE — run block {s['block']} (" + (f"{older}; " if older else "")
             + f"{_slate_done_why(s)}: the watch runs it no more)")
    else:
        t = f"NO SLATE FILE — slate run due {cl.et(s['due'])[11:]}"
        notes = [older] if older else []
        if s.get("attempts"):
            notes.append(f"attempt {s['attempts']} of {cl.MAX_ATTEMPTS} failed ({s['last_failed']}): the watch tries "
                         "again")
        if s.get("misses"):
            notes.append(f"missed ({', '.join(s['misses'])}): the watch keeps trying")
        if s.get("held"):
            at = f" since {cl.et(s['held']['at'])[11:]}" if s["held"].get("at") else ""
            notes.append(f"held{at} ({s['held']['why']}): the slate runs after it")
        if s.get("unread"):
            notes.append(s["unread"])
        if notes:
            t += f" ({'; '.join(notes)})"
    if s["skipped"]:
        t += " · skipped: " + "; ".join(f"{n} ({why})" for n, why in s["skipped"])
    return f"{x['code']} SLATE · {t}"


def _games_text(x: dict) -> str:
    """The games clause: the count, and the void games named (not counted)."""
    return _n(len(x["games"]), "game") + (
        f" (+{len(x['void'])} void, not counted: " + ", ".join(f"{m} {s}" for m, s in x["void"]) + ")"
        if x["void"] else "")


def _rows_clauses(x: dict) -> tuple[str, str | None]:
    """The rows clause and the without-rows clause (None where the line leaves it out: no row and none expected)."""
    if x["rows"]:
        rows = "rows: " + ", ".join(f"{m['model_version']} {m['rows']}" + _computed(m) for m in x["rows"])
    else:
        rows = f"rows: none (none expected: {x['status']})" if x["status"] in NO_ROWS_EXPECTED else "rows: none"
    if x["rows"] or x["status"] not in NO_ROWS_EXPECTED:
        return rows, "without rows: " + (", ".join(map(str, x["without_rows"])) or "none")
    return rows, None


def _closing_tail(x: dict) -> str | None:
    """The closing clause's last words, outside any group's text: "none left to run" where the day's groups leave the
    watch nothing to run or record (left to run: a group the watch will run or record a miss for; a done one: tried
    again, or a miss), None where the clause says no such thing (no family, refused here, not shown, or a group left
    to run). One function for the line and the coverage_v1 file (`closing_tail`), so the Cockpit renders the file's
    words without deriving them (#589, F1c)."""
    if not x["family"] or x["refused"] or x["closing_unread"]:
        return None
    if any(g["state"] != "done" or g["next"] in ("again", "miss") for g in x["groups"]):
        return None
    return "none left to run"


def _closing_clause(x: dict, day: date) -> str:
    """The closing clause: no family, refused here, not shown, or the day's groups."""
    if not x["family"]:
        return f"closing: none (no closing family covers {x['code']})"
    if x["refused"]:
        return f"closing: refused here ({x['refused']})"
    if x["closing_unread"]:
        return f"closing: not shown ({x['closing_unread']})"
    runs = [_group_text(g, day) for g in x["groups"]]
    tail = _closing_tail(x)
    if tail:
        runs.append(tail)
    if x["finished"]:
        runs.insert(0, f"a closing finished with {', '.join(map(str, x['finished']))}")
    if x["started"]:
        runs.insert(0, f"started {', '.join(map(str, x['started']))}")
    return "closing: " + "; ".join(runs)


def comp_line(x: dict, day: date) -> str:
    """One competition's line."""
    rows, without = _rows_clauses(x)
    parts = [x["code"], _games_text(x), f"{x['status_label']} ({x['status_from']})", rows]
    if without is not None:
        parts.append(without)
    parts.append(_closing_clause(x, day))
    return " · ".join(parts)


def lines(cov: dict, wrote: str | None = None) -> list[str]:
    """The printed lines. `wrote`: the one file `--json` wrote (its header says so); None, the text output as ever."""
    day, comps = cov["date"], cov["competitions"]
    n = sum(len(x["games"]) for x in comps)
    out = [f"COVERAGE {day.isoformat()} ET · {_n(len(comps), 'competition')} · {_n(n, 'game')} · now "
           f"{cl.et(cov['now'])} · read-only (the DB mode=ro, the closing-watch schedule and receipts, the slate "
           "and shadow files in exports/): no row written, " + ("no export written" if wrote is None else
                                                                f"one export written ({wrote}, --json)")
           + ", no provider call"]
    if not comps:
        out.append("no stored game that day")
    for x in comps:
        out.append(comp_line(x, day))
        if slate_line(x):
            out.append(slate_line(x))
        out += paper_lines(x)
    out += ["GAPS:", *cov["gaps"]] if cov["gaps"] else ["GAPS: none"]
    return out


# --------------------------------------------------------------------------------------- the JSON file --
# ARCHITECT 2026-10-18, addendum 125 item 2(a), #589: `coverage --json [--out PATH]` writes the dict coverage()
# returns under kind coverage_v1, every datetime ISO-8601 Z, plus the roadmap's lanes as `cli.py roadmap` reads them.

KIND = "coverage_v1"


def default_out(day: date) -> str:
    """exports/coverage_<date>.json, the coverage day's date (the exports mirror maps its kind to latest/coverage.json:
    exports_mirror.kind_of strips the date)."""
    return f"{cl.CLOSING_FILE_DIR}/coverage_{day.isoformat()}.json"


def _plain(v):
    """JSON-ready, generically (a field coverage() gains later rides along): a datetime is ISO-8601 Z (closing.iso_z),
    a date YYYY-MM-DD, a tuple a list, a set a sorted list, a dict's keys text (a match id key becomes "401")."""
    if isinstance(v, datetime):
        return cl.iso_z(v)
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    if isinstance(v, (set, frozenset)):
        return [_plain(x) for x in sorted(v, key=str)]
    return v


def document(cov: dict, roadmap_path=None) -> dict:
    """The coverage_v1 document: {"kind": "coverage_v1", **coverage() with every datetime ISO-8601 Z}, plus what the
    printed lines say in the line's own words, so a reader shows it without computing it (the Cockpit's Today tab,
    F1c: viewer, not engine): `now_et`; per competition `line` (its printed line), `games_text`, `rows_text`,
    `without_rows_text` (null where the line leaves it out), `closing_text` (its clauses), `closing_tail` (the
    clause's words outside any group's text: "none left to run", or null where the clause has none), `slate_line`
    (its SLATE line as printed, `<CODE> SLATE · …`, or null where it has none: neither LIVE nor MARKET-ONLY; #606
    item 2, the Today tile shows it first; a MARKET-ONLY competition's is its PAPER header, addendum 146 item 5(a))
    and `paper_lines` (its PAPER lines as printed, one per game; [] where it has none); per prediction
    model `computed_et` (its computed_at in ET, as the line prints it; null when none could be read); per closing group
    `run_lead` ("T-35"), `run_at_et` (the run time in ET, with its date when not the day's) and `text` (the group as
    the line prints it). Then `roadmap`: lanes_data() on the coverage day (roadmap.load() and the print's own lines;
    "no ETA" where a lane's earliest_live is null), or null with `roadmap_unread` saying why (law 4: never a guessed
    lane)."""
    from src import roadmap as rm
    day = cov["date"]
    doc = {"kind": KIND, **_plain(cov), "now_et": cl.et(cov["now"])}
    for xd, x in zip(doc["competitions"], cov["competitions"]):
        rows, without = _rows_clauses(x)
        xd.update(line=comp_line(x, day), games_text=_games_text(x), rows_text=rows, without_rows_text=without,
                  closing_text=_closing_clause(x, day), closing_tail=_closing_tail(x), slate_line=slate_line(x),
                  paper_lines=paper_lines(x))
        for md, m in zip(xd["rows"], x["rows"]):
            md["computed_et"] = _computed_text(m) or None
        for gd, g in zip(xd["groups"], x["groups"]):
            gd.update(run_lead=f"T-{cl.RUN_LEAD_MIN}", run_at_et=_run_time(g["start"], day), text=_group_text(g, day))
    try:
        doc["roadmap"], doc["roadmap_unread"] = rm.lanes_data(day, roadmap_path), None
    except rm.RoadmapError as e:
        doc["roadmap"], doc["roadmap_unread"] = None, f"the roadmap cannot be read: {e}"
    return doc


def _out_refusal(p: Path) -> str | None:
    """Law 5: nothing is ever created under data/ (the checkout's, or the working directory's). And a file at the top
    of exports/ (the checkout's, or the working directory's), which the exports mirror pushes, must be named as kind
    `coverage` (exports_mirror.kind_of): the compare lists that kind as machine state and never compares it (#592,
    addendum 128 item 3), so a coverage_v1 document under another kind's name would be compared and read DIVERGENT.
    #597 (the #595 follow-up): a path that names no file (`.`, `/`) is refused, never a traceback (item 1); and each
    rule is checked on the lexical path as well as the resolved one (item 2): the write replaces a symlink already at
    the name with a regular file there, so a link that resolves outside data/ or exports/ never gets the file past
    either rule."""
    import os
    import exports_mirror as em
    if p.name in ("", ".", ".."):
        return f"--out {p} names no file"
    targets = {Path(os.path.abspath(p)), p.resolve()}      # where the file lands, and where a link there points
    bases = (c.REPO, Path.cwd())
    for t in targets:
        for data in {d for b in bases for d in (Path(os.path.abspath(b / "data")), (b / "data").resolve())}:
            if t == data or data in t.parents:
                return f"--out {p} is under {data} (law 5: nothing is created under data/)"
        for ex in {e for b in bases for e in (Path(os.path.abspath(b / "exports")), (b / "exports").resolve())}:
            if t.parent == ex and t.name.endswith(em.SUFFIXES) and em.kind_of(t.name) != "coverage":
                return (f"--out {p} is a top-level exports/ file the mirror pushes as kind {em.kind_of(t.name)!r}, "
                        f"not 'coverage' (#592: only kind coverage is machine state, never compared): name it "
                        f"coverage_<date>.json, or write it outside exports/")
    return None


def write_document(doc: dict, out: Path) -> None:
    """The one file: written beside its final name, then moved into place (never a half-written file under exports/,
    which the mirror pushes). OSError when it cannot be written."""
    import json
    import os
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f".{out.name}.{os.getpid()}.tmp")    # hidden, and not *.json: the mirror never takes it
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, out)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def run(date_s: str | None = None, echo=print, now: datetime | None = None, as_json: bool = False,
        out: str | None = None) -> int:
    """The command: the lines, exit 0; a date that is not real, or a DB that cannot be read, exits 2. `as_json`
    (--json) also writes the coverage_v1 document to `out` (--out; default exports/coverage_<date>.json), the lines
    then saying so; an --out without --json, an --out under data/ or a file that cannot be written exits 2, and on a
    refusal no file is written. The gaps never change the exit."""
    from src import roadmap as rm
    if out is not None and not as_json:
        echo("COVERAGE REFUSED: --out needs --json (the text output writes no file)")
        return 2
    day = None
    if date_s is not None:
        day = rm.real_date(date_s)
        if day is None:
            echo(f"COVERAGE REFUSED: --date {date_s!r} is not a real date (YYYY-MM-DD)")
            return 2
    try:
        cov = coverage(day, now)
    except Refused as e:
        echo(f"COVERAGE REFUSED: {e}")
        return 2
    wrote = None
    if as_json:
        wrote = out or default_out(cov["date"])
        why = _out_refusal(Path(wrote))
        if why:
            echo(f"COVERAGE REFUSED: {why}")
            return 2
        doc = document(cov)
        try:
            write_document(doc, Path(wrote))
        except OSError as e:
            echo(f"COVERAGE REFUSED: --out {wrote} cannot be written ({type(e).__name__}: {e})")
            return 2
    for line in lines(cov, wrote):
        echo(line)
    if as_json:
        road = (f"roadmap {len(doc['roadmap'])} lanes" if doc["roadmap"] is not None
                else f"roadmap null ({doc['roadmap_unread']})")
        echo(f"COVERAGE JSON: {wrote} written (kind {KIND}: the map above as data, "
             f"{_n(len(doc['competitions']), 'competition')}, {_n(len(doc['gaps']), 'gap line')}, {road})")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="coverage_map.py", description="The day's coverage (= python cli.py coverage)")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD, by each game's US Eastern date (default: today, ET)")
    ap.add_argument("--json", action="store_true", dest="as_json",
                    help="also write the map as a coverage_v1 document (addendum 125 item 2(a))")
    ap.add_argument("--out", default=None, help="with --json: the file (default exports/coverage_<date>.json)")
    a = ap.parse_args(argv)
    if str(c.REPO) not in sys.path:
        sys.path.insert(0, str(c.REPO))
    return run(a.date, as_json=a.as_json, out=a.out)


if __name__ == "__main__":
    raise SystemExit(main())
