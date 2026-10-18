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
                   (a step whose command is one of SHADOW_EXPORTS, in a chain whose steps name the competition; an
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

Read-only: the DB is opened mode=ro (sp_common.ro_connect: a missing file is refused, never created), plus
docs/roadmap.json, docs/registry/experiments.json, the watch's schedule inputs (chains.py, closing.py) and its receipt
log (sp_common.receipts_path(): SP_RECEIPTS or logs/receipts.jsonl, read as closing.receipts reads it; no file is no
receipt) and the settings _family_refusal and sp_run.active_from read. No row and no receipt is written, and no export
but the --json file; no provider call. SQLite itself may leave its -wal/-shm sidecars beside a WAL file, as for every
ro_connect reader. Exit 0 whatever the gaps (it never stops a chain); a date that is not real, a DB that cannot be read,
an --out without --json, an --out under data/ or a --json file that cannot be written exits 2, and writes no file.
"""
from __future__ import annotations

import argparse
import importlib
import re
import sqlite3
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

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
    """[lo, hi) in UTC: midnight to midnight in America/New_York (23 or 25 hours on a clock change)."""
    lo = datetime.combine(day, time(0), tzinfo=cl.NY).astimezone(timezone.utc)
    hi = datetime.combine(day + timedelta(days=1), time(0), tzinfo=cl.NY).astimezone(timezone.utc)
    return lo, hi


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
    the competitions the chain's steps name}. An operator-only chain has no timer: no schedule."""
    out = []
    for name, ch in CHAINS.items():
        if ch.get("operator_only"):
            continue
        steps = [s for s in ch.get("steps") or [] if s]
        comps = {s[i + 1] for s in steps for i, a in enumerate(s[:-1]) if a == "--competition"}
        for s in steps:
            if s[0] in SHADOW_EXPORTS:
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
    (sp_run names those freshen:<family>). SOCCER: soccer-prematch; MLB: mlb-preslate; NFL: nfl-predict."""
    model = [s for s in CHAINS[CLOSING_FAMILIES[fam]]["steps"] if s and s[0] in PREDICT_COMMANDS]
    skip = set(CLOSING_FAMILIES.values()) | {f"freshen:{f}" for f in FRESHEN_FAMILY.values()}
    return [name for name, ch in CHAINS.items()
            if name not in skip and any(s in model for s in ch.get("steps") or [])]


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
        comps.append({"code": code, "games": [g["match_id"] for g in mine], "void": [(g["match_id"], g["status"])
                                                                                   for g in void],
                      "status": st["status"], "status_label": st["label"], "status_from": st["from"],
                      "shadow": st["shadow"], "family": fam, "refused": refused,
                      "rows": sorted(by_model.values(), key=lambda m: m["model_version"]),
                      "without_rows": [g["match_id"] for g in mine if not preds.get(g["match_id"])],
                      "writers": writer_chains(fam) if fam else [], "groups": groups, "started": started,
                      "finished": finished, "closing_unread": closing_unread})
    comps.sort(key=lambda x: (STATUSES.index(x["status"]), x["code"]))
    return {"date": day, "now": now, "competitions": comps, "gaps": gap_lines(comps)}


def gap_lines(comps: list[dict]) -> list[str]:
    """The gaps, in capitals (the spec's example: "PL: 4 GAMES, 0 PREDICTION ROWS — soccer-prematch has not run")."""
    out = []
    for x in comps:
        if x["status"] != "LIVE" or x.get("refused") or not x["without_rows"]:
            continue                  # refused here: its line names the refusal, the rows are another machine's
        rows = sum(m["rows"] for m in x["rows"])
        line = f"{x['code']}: {_n(len(x['games']), 'GAME')}, {_n(rows, 'PREDICTION ROW')}"
        if len(x["without_rows"]) < len(x["games"]):
            line += f", NONE FOR {', '.join(map(str, x['without_rows']))}"
        elif x["writers"]:
            line += f" — {' or '.join(x['writers'])} has not run"
        out.append(line)
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
           f"{cl.et(cov['now'])} · read-only (the DB mode=ro, the closing-watch schedule and receipts): no row "
           "written, " + ("no export written" if wrote is None else f"one export written ({wrote}, --json)")
           + ", no provider call"]
    if not comps:
        out.append("no stored game that day")
    out += [comp_line(x, day) for x in comps]
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
    `without_rows_text` (null where the line leaves it out), `closing_text` (its clauses) and `closing_tail` (the
    clause's words outside any group's text: "none left to run", or null where the clause has none); per prediction
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
                  closing_text=_closing_clause(x, day), closing_tail=_closing_tail(x))
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
    addendum 128 item 3), so a coverage_v1 document under another kind's name would be compared and read DIVERGENT."""
    import exports_mirror as em
    t = p.resolve()
    for data in {(c.REPO / "data").resolve(), (Path.cwd() / "data").resolve()}:
        if t == data or data in t.parents:
            return f"--out {p} is under {data} (law 5: nothing is created under data/)"
    for ex in {(c.REPO / "exports").resolve(), (Path.cwd() / "exports").resolve()}:
        if t.parent == ex and t.name.endswith(em.SUFFIXES) and em.kind_of(t.name) != "coverage":
            return (f"--out {p} is a top-level exports/ file the mirror pushes as kind {em.kind_of(t.name)!r}, not "
                    f"'coverage' (#592: only kind coverage is machine state, never compared): name it "
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
