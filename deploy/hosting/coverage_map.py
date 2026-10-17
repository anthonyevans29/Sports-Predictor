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

    closing.py's own pieces, never re-implemented: a game's day is its America/New_York date (closing.ny_date, the
    date A1 gives a first pitch); VOID statuses are no game (closing.VOID); the closing groups are closing.groups() on
    closing.due()'s own inputs (the stored games plus the unpaged called-off ones, closing.with_called_off, less the
    games a closing has finished with, closing.covered_ids from the watch's receipts), over the family's games of the
    day at `now` (C2: the earliest unstarted start time, the games within the 10 minutes after it, then the next);
    each group is ahead, due now, or inside T-5 (a miss: no attempt, no file) by due()'s own thresholds; the run time
    is the start time less closing.RUN_LEAD_MIN; the file is exports/closing.closing_name() (addendum 40 item 2). A
    family this machine refuses (closing._family_refusal: SP_SKIP_FAMILIES, as the watch and closing-run read it)
    shows the refusal in place of its groups.

    The model status, per competition:
      LIVE         a closing family covers it (closing.FAMILIES[fam]["comps"]; the families are chains.CLOSING_FAMILIES,
                   C1: "A closing run exists for every family whose calls come from a live model [...] A league joins
                   when its model is CONFIRMED and the Desk calls it"): neither the registry nor the roadmap names a
                   live competition, the three live models predate both. Also the roadmap lane named for it in state
                   live, its registry entry (if the lane names one) in production.
      SHADOW       the roadmap lane named for the competition in state confirming, its registry entry (if the lane names
                   one) confirming (a gate PASS in its declared confirmation window: a shadow, never a call).
      MARKET-ONLY  a roadmap lane named for the competition in any other state (to declare, declared, blocked,
                   closed), its registry entry (if it names one) not past its gate.
      UNKNOWN      law 4, with the reason: no closing family covers it and no roadmap lane is named for it (a lane is
                   named for a competition when its id is the competition's code: "unl", "pd", "ncaa", "nhl"; the
                   lanes "leagues" and "cups" name theirs in prose only); the lane and its registry entry disagree; the
                   lane names a registry id the registry does not hold; or a file cannot be read.

    The gaps (capitals): a LIVE competition with a game that has no prediction row. Zero rows names the slate chain
    whose model step writes them ("— soccer-prematch has not run"), derived from chains.py: the closing chain's step
    whose command writes prediction rows (PREDICT_COMMANDS), found word for word in a chain that is neither a closing
    nor a freshen chain; no chain found, no hint. No chain runs a predict step for a SHADOW or MARKET-ONLY competition
    (its shadow, if any, prices in its own export), so no row is expected and no gap is claimed. A LIVE competition
    whose family this machine refuses (MLB on the host: a laptop duty) claims no gap either; its line shows the
    refusal. UNKNOWN competitions are named once, in capitals, with no gap judged for them.

Read-only: the DB is opened mode=ro (sp_common.ro_connect: a missing file is refused, never created), plus
docs/roadmap.json, docs/registry/experiments.json, the watch's receipts (read as closing.covered_ids reads them; no file
is no receipt) and the settings _family_refusal reads. No row, no export, no receipt is written; no provider call.
SQLite itself may leave its -wal/-shm sidecars beside a WAL file, as for every ro_connect reader. Exit 0 whatever the
gaps (it never stops a chain); a date that is not real or a DB that cannot be read exits 2.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import closing as cl  # noqa: E402
import sp_common as c  # noqa: E402
from chains import CHAINS, CLOSING_FAMILIES, FRESHEN_FAMILY  # noqa: E402

STATUSES = ("LIVE", "SHADOW", "MARKET-ONLY", "UNKNOWN")       # the order the lines are printed in
NO_ROWS_EXPECTED = ("SHADOW", "MARKET-ONLY")
# The two cli commands whose code writes prediction rows (law 1, read 2026-10-17: Prediction rows are constructed only
# in src/walters/training.py, reached by `predict`, and src/walters/nfl_predict.py, reached by `predict-nfl`; a test
# pins both. The web UI's per-match refresh and admin predict job reach training.generate_predictions too; no chain
# runs them).
PREDICT_COMMANDS = ("predict", "predict-nfl")
# roadmap lane state -> status; registry entry status -> status (src/roadmap.py STATES; registry.py's statuses)
LANE_STATUS = {"live": "LIVE", "confirming": "SHADOW", "to declare": "MARKET-ONLY", "declared": "MARKET-ONLY",
               "blocked": "MARKET-ONLY", "closed": "MARKET-ONLY"}
REGISTRY_STATUS = {"production": "LIVE", "confirming": "SHADOW", "declared": "MARKET-ONLY", "run": "MARKET-ONLY",
                   "closed": "MARKET-ONLY"}
_IN_CHUNK = 500              # ids per IN (...) list: under SQLite's variable limit


class Refused(RuntimeError):
    """Nothing could be read: the message says why (exit 2)."""


# ------------------------------------------------------------------------------------------------ the day --

def day_bounds(day: date) -> tuple[datetime, datetime]:
    """[lo, hi) in UTC: midnight to midnight in America/New_York (23 or 25 hours on a clock change)."""
    lo = datetime.combine(day, time(0), tzinfo=cl.NY).astimezone(timezone.utc)
    hi = datetime.combine(day + timedelta(days=1), time(0), tzinfo=cl.NY).astimezone(timezone.utc)
    return lo, hi


def read_day(day: date) -> tuple[list[dict], dict]:
    """The day's stored games (every competition, closing.schedule's shape plus `comp`; VOID ones included, marked)
    and {match_id: [(model_version, computed_at)]} for them. One read-only connection; nothing else is read."""
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
    except sqlite3.Error as e:
        raise Refused(f"the DB at {p} cannot be read: {type(e).__name__}: {e}") from None
    finally:
        con.close()
    return games, preds


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


def model_status(code: str, lanes: list[dict], entries: dict, unread: str | None = None) -> tuple[str, str]:
    """(LIVE | SHADOW | MARKET-ONLY | UNKNOWN, where it was read). The table is the module docstring's."""
    fam = family_of(code)
    if fam:
        return "LIVE", f"closing family {fam}"
    if unread:
        return "UNKNOWN", unread
    ln = next((x for x in lanes if str(x.get("lane", "")).upper() == code.upper()), None)
    if ln is None:
        return "UNKNOWN", f"no closing family covers {code} and no roadmap lane is named {code.lower()}"
    by_lane = LANE_STATUS.get(ln["state"])
    src = f"roadmap lane {ln['lane']}: {ln['state']}"
    rid = ln.get("registry_id")
    if rid:
        e = entries.get(rid)
        if e is None:
            return "UNKNOWN", f"{src}; registry id {rid} is not in the registry"
        by_reg = REGISTRY_STATUS.get(e.get("status"))
        src += f"; registry {rid}: {e.get('status')}"
        if by_reg != by_lane:
            return "UNKNOWN", f"{src} (the lane and the registry disagree)"
    if by_lane is None:
        return "UNKNOWN", f"{src} (a state with no status)"
    return by_lane, src


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
    """The family's closing groups of the day as the watch forms them: closing.groups() on closing.due()'s own inputs
    (the stored games plus the unpaged called-off ones, less the games a closing has finished with, read from the
    watch's receipts), the day standing in for schedule()'s window. Each group's state at `now` is due()'s: ahead
    (before T-35), due (T-35 to T-5: the watch runs it now) or inside (inside T-5: a miss, no attempt, no file).
    {"groups", "finished": the ids a closing has finished with, "unread": why the receipts could not be read}."""
    comps = cl.FAMILIES[fam]["comps"]
    comp_of = {g["match_id"]: g["comp"] for g in games}
    fam_games = [g for g in games if g["comp"] in comps and not g["void"]]
    try:
        covered = cl.covered_ids(fam)
        fam_games = [g for g in cl.with_called_off(fam, fam_games, now) if cl.ny_date(g["start"]) == day]
    except (OSError, sqlite3.Error) as e:
        return {"groups": [], "finished": set(), "unread": f"the watch's receipts cannot be read: {type(e).__name__}"}
    out = []
    for gr in cl.groups(fam_games, now, covered):
        m = cl.minutes_to(gr["start"], now)
        state = "ahead" if m > cl.RUN_LEAD_MIN else "due" if m >= cl.NO_ATTEMPT_INSIDE_MIN else "inside"
        out.append({"start": gr["start"], "run_at": gr["start"] - timedelta(minutes=cl.RUN_LEAD_MIN),
                    "match_ids": [g["match_id"] for g in gr["games"]], "state": state,
                    # a called-off game no longer stored on the day is its family's (one competition) or no one's
                    "comps": sorted({comp_of.get(g["match_id"], comps[0] if len(comps) == 1 else None)
                                     for g in gr["games"]} - {None}),
                    "file": None if state == "inside" else
                    f"{cl.CLOSING_FILE_DIR}/{cl.closing_name(fam, gr['start'])}"})
    return {"groups": out, "finished": covered, "unread": None}


def coverage(day: date | None = None, now: datetime | None = None, roadmap_path=None, registry_path=None) -> dict:
    """The day's coverage map: what the lines print, as data (the morning page's source). Refused when the DB
    cannot be read."""
    now = cl.utc(now or cl.clock())
    day = day or cl.ny_date(now)
    games, preds = read_day(day)
    lanes, entries, unread = read_ledgers(roadmap_path, registry_path)
    views: dict = {}                  # family -> watch_groups(), read once per family
    comps: list[dict] = []
    for code in sorted({g["comp"] for g in games}):
        mine = [g for g in games if g["comp"] == code and not g["void"]]
        void = [g for g in games if g["comp"] == code and g["void"]]
        status, src = model_status(code, lanes, entries, unread)
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
            finished = [g["match_id"] for g in mine if g["match_id"] in v["finished"] and not cl.started(g, now)]
            closing_unread = v["unread"]
        comps.append({"code": code, "games": [g["match_id"] for g in mine], "void": [(g["match_id"], g["status"])
                                                                                   for g in void],
                      "status": status, "status_from": src, "family": fam, "refused": refused,
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


def _computed(m: dict) -> str:
    """A model's computed_at in ET: the range when its rows differ (an old row is never hidden behind a fresh one)."""
    if not m["latest"]:
        return ""
    if m["earliest"] != m["latest"]:
        return f" (computed {cl.et(m['earliest'])} to {cl.et(m['latest'])})"
    return f" (latest {cl.et(m['latest'])})"


def comp_line(x: dict, day: date) -> str:
    """One competition's line."""
    parts = [x["code"], _n(len(x["games"]), "game")
             + (f" (+{len(x['void'])} void, not counted: " + ", ".join(f"{m} {s}" for m, s in x["void"]) + ")"
                if x["void"] else ""),
             f"{x['status']} ({x['status_from']})"]
    if x["rows"]:
        parts.append("rows: " + ", ".join(f"{m['model_version']} {m['rows']}" + _computed(m) for m in x["rows"]))
    else:
        parts.append(f"rows: none (none expected: {x['status']})" if x["status"] in NO_ROWS_EXPECTED else
                     "rows: none")
    if x["rows"] or x["status"] not in NO_ROWS_EXPECTED:
        parts.append("without rows: " + (", ".join(map(str, x["without_rows"])) or "none"))
    if not x["family"]:
        parts.append(f"closing: none (no closing family covers {x['code']})")
    elif x["refused"]:
        parts.append(f"closing: refused here ({x['refused']})")
    elif x["closing_unread"]:
        parts.append(f"closing: not shown ({x['closing_unread']})")
    else:
        runs = []
        for g in x["groups"]:
            head = f"T-{cl.RUN_LEAD_MIN} {_run_time(g['start'], day)} [{', '.join(map(str, g['match_ids']))}]"
            runs.append(f"{head} inside T-5: no attempt, no file (the watch records a miss)" if g["state"] == "inside"
                        else f"{head} → {g['file']}" + (" (due now)" if g["state"] == "due" else ""))
        runs = runs or ["none left to run"]
        if x["finished"]:
            runs.insert(0, f"a closing finished with {', '.join(map(str, x['finished']))}")
        if x["started"]:
            runs.insert(0, f"started {', '.join(map(str, x['started']))}")
        parts.append("closing: " + "; ".join(runs))
    return " · ".join(parts)


def lines(cov: dict) -> list[str]:
    day, comps = cov["date"], cov["competitions"]
    n = sum(len(x["games"]) for x in comps)
    out = [f"COVERAGE {day.isoformat()} ET · {_n(len(comps), 'competition')} · {_n(n, 'game')} · now "
           f"{cl.et(cov['now'])} · read-only (the DB mode=ro, the closing-watch schedule and receipts): no row "
           "written, no export written, no provider call"]
    if not comps:
        out.append("no stored game that day")
    out += [comp_line(x, day) for x in comps]
    out += ["GAPS:", *cov["gaps"]] if cov["gaps"] else ["GAPS: none"]
    return out


def run(date_s: str | None = None, echo=print, now: datetime | None = None) -> int:
    """The command: the lines, exit 0; a date that is not real, or a DB that cannot be read, exits 2."""
    from src import roadmap as rm
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
    for line in lines(cov):
        echo(line)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="coverage_map.py", description="The day's coverage (= python cli.py coverage)")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD, by each game's US Eastern date (default: today, ET)")
    a = ap.parse_args(argv)
    if str(c.REPO) not in sys.path:
        sys.path.insert(0, str(c.REPO))
    return run(a.date)


if __name__ == "__main__":
    raise SystemExit(main())
