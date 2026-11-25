"""
THE NHL COHORT COUNT (DEV 4, Lane D; ARCHITECT 2026-11-24 19:21 ET, addendum 523 item 2; Refs #105), READ-ONLY.

WHAT IT IS. Item (f) of DEV 3's feasibility read on #105 (comment 7146331897), built as a command so that the
architect's block runs one tested line and no SQL of his: the 2026-27 regular season's games stored, played and to
come, as counts, and nothing else. No model, no rating, no figure of any candidate, no row printed (523 item 2(e)).

THE COPY (523 item 2(a); addendum 198 item 6(ii)): `--db COPY` is required. It is fenced by
mlb_pitchers_gate.check_db (an existing file, never created; never under the repo's data/ by resolved path or by
identity; never the app's configured database), and refused under ANY directory named data, case ignored, as given
or resolved (521 item 6 Q1's rule). It is refused beside a -wal, -shm or -journal file (intl_shadow.copy_sidecars),
and each table the read touches (COPY_TABLES) is probed. The whole read runs on mlb_pitchers_gate.readonly_session
(mode=ro + immutable=1). The copy's sha256 prints before the read and is checked again after it, with no sidecar
beside it; a difference refuses. Nothing is written anywhere.

THE NAMES IT USES, each read from the schema and the code first (law 1; 523 item 2(d)):
- the cohort: matches joined to competitions on competition_id, Match.sport == Sport.NHL and Competition.code ==
  "NHL" (the filter of src/walters/nhl_backtest.py:418-424 and src/walters/nhl_shadow.py, "4 Nations etc. stay out";
  the row src/adapters/api_hockey.py:107-111 writes); season "2026" (api_hockey.py:5-6, "2026 = the 26-27 season";
  stored by :143 and :197).
- the statuses: schema.MatchStatus, every member, stored as the member NAME (schema.py:68-98); status_raw is the
  provider's code verbatim (schema.py:186-190; the hockey map at api_hockey.py:46-61), NULL until a re-sync.
- the stage: the provider's string verbatim, NULL when empty (api_hockey.py:204). No code names the NHL's stage
  vocabulary, so the read assumes none: it prints the stored values (Q0) and counts by them; it never filters on a
  stage name. Preseason is the shadow's own rule, nhl_backtest.preseason_reason with nhl_shadow's season starts (a
  stage containing "pre", or a game before the 2026 opener 2026-09-29, nhl_shadow.py:67-68).
- played: FINISHED with both scores (nhl_backtest.load_games, nhl_backtest.py:420-426); to come: SCHEDULED.
- the goalie table's game type: nhl_goalie_appearances.game_type, the API's gameType, 2 regular, 3 playoffs
  (schema.py:511; nhl_goalies.KEEP_GAME_TYPES {2, 3}; a NULL type is kept, nhl_goalies.py:292-297); linked by
  match_id (schema.py:509).
- a season for the goalie and shot tables, which carry no season column: the game's stored start (UTC), 1 July to
  30 June (nhl_goalies.season_label, nhl_goalies.py:475-480), "2026-27" and "2023-24".
- the shot events: nhl_shot_events (schema.py:550), one row per event, nhl_game_id, game_start, game_type, match_id.
- dates: every month and every --after date is the America/New_York date of the stored UTC start (stored naive UTC).

THE SIX INTERNATIONAL GAMES (523 item 2(b), "found as 445 item 3(b) finds them"). 445 item 3(b) found them by their
attributes: four clubs, added to the NHL's 2026 teams, with no NHL game before 2027-02-01 (addendum 452 item 4(a));
six games among those four, all at 2027-02-05 21:00Z. The ids differ between the machines (addendum 453 item 5), so
none is named here. The read finds the clubs as the teams of the cohort with no game in it before 2027-02-01 (UTC),
and the six as the cohort's games between two of them. Only when that finds exactly four clubs and six games, every
one at 2027-02-05 21:00Z, are they FOUND, counted apart and kept out of Q2 to Q5. Otherwise the read says which
attribute differs, counts nothing for them, and keeps every game in Q2 to Q5, labelled (523 item 2(d)).

WHAT IT PRINTS: DEV 3's Q0 to Q6, counts only.
- Q0: stage by status.
- Q1: the six, apart.
- Q2: month by status, played and to come, status_raw beside.
- Q3: the played games against the goalie table's game type.
- Q4: the 2026-27 shot events by month.
- Q5: for each --after DATE, the games to come after it, by stored stage, with the note that a game to come is
  unverified until played.
- Q6: the 2023-24 shot games.

EXIT 0 when the read reached its end; 2 on a refusal (the copy, an option), nothing read or nothing reported.

Python 3.10 is the floor (CONTRIBUTING.md).
"""
from __future__ import annotations

import argparse
import errno
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

COMPETITION_CODE = "NHL"                    # api_hockey.py:107-111; nhl_backtest.py:418-424
SEASON = "2026"                             # api_hockey.py:5-6: "2026 = the 26-27 season"
SHOT_SEASON = "2026-27"                     # nhl_goalies.season_label of a 2026-27 start
HISTORY_SEASON = "2023-24"                  # DEV 3's Q6
REGULAR_TYPE = 2                            # schema.py:511; nhl_goalies.REGULAR
INTL_NO_GAME_BEFORE = datetime(2027, 2, 1)  # addendum 452 item 4(a): "no NHL game before 2027-02-01"
INTL_KICKOFF = datetime(2027, 2, 5, 21, 0)  # addendum 445 item 3(b): "all 2027-02-05 21:00Z"
INTL_CLUBS, INTL_GAMES = 4, 6               # 445 item 3(b): "among Canada (3604), Finland (3605), Sweden (3606) and USA"
COPY_TABLES = ("competitions", "matches", "teams", "nhl_goalie_appearances", "nhl_shot_events")
UNVERIFIED = "a game to come is unverified until played: its date, its stage and its being played are the stored listing's"


class CohortRefused(RuntimeError):
    """A refused read: exit 2, nothing reported."""


def _et():
    from zoneinfo import ZoneInfo
    return ZoneInfo("America/New_York")


def et_date(utc_naive: datetime) -> date:
    """The America/New_York date of a stored naive-UTC start (kalshi_match.et_day's rule)."""
    return utc_naive.replace(tzinfo=timezone.utc).astimezone(_et()).date()


def et_month(utc_naive: datetime) -> str:
    return et_date(utc_naive).strftime("%Y-%m")


# --------------------------------------------------------------------------
# The copy
# --------------------------------------------------------------------------


def _named_data(db) -> str | None:
    try:
        p = Path(str(db)).expanduser()
        parts = list(p.parts) + list(p.resolve().parts)
    except (RuntimeError, OSError) as e:
        return "--db {} cannot be resolved ({})".format(db, type(e).__name__)
    if any(x.casefold() == "data" for x in parts):
        return "--db {} is under a directory named data (law 5); take the copy outside it".format(db)
    return None


def check_copy(db) -> Path:
    """The fence of soccer_expansion.check_copy and intl_shadow.check_copy, with this read's tables; a refusal reads
    nothing and writes nothing."""
    from src.walters import intl_shadow as us
    from src.walters import mlb_pitchers_gate as mp
    if db is not None and str(db).strip():
        why = _named_data(db)
        if why:
            raise CohortRefused(why + "; nothing read")
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
                                 "it and read a stale store; take a fresh .backup copy".format(
                                     db, name[len(path.name):], name))
        con = mp.open_ro(path)
        try:
            for t in COPY_TABLES:
                try:
                    con.execute("SELECT 1 FROM {} LIMIT 1".format(t))
                except sqlite3.Error as e:
                    raise mp.GateRefused("--db {}: the copy cannot be read for table {} ({})".format(db, t, e))
        finally:
            con.close()
    except mp.GateRefused as err:
        raise CohortRefused("{}; nothing read".format(err))
    return path


def on_copy(copy: Path, read):
    """(sha256 before, read(s), sha256 after) on the copy's mode=ro + immutable=1 session; refused when the copy
    changed during the read or a sidecar appeared beside it (soccer_expansion.on_copy's two checks)."""
    from sqlalchemy.exc import DBAPIError

    from src.walters import intl_shadow as us
    from src.walters import mlb_pitchers_gate as mp
    try:
        sha_before = us.copy_sha256(copy)
    except OSError as err:
        raise CohortRefused("--db {}: the copy could not be hashed ({!r}); nothing read".format(copy, err))
    try:
        with mp.readonly_session(copy) as s:
            out = read(s)
            try:
                sha_after = us.copy_sha256(copy)
                sides_after = us.copy_sidecars(copy)
            except OSError as err:
                raise CohortRefused("--db {}: the copy could not be re-read after the read ({!r}); nothing "
                                    "reported".format(copy, err)) from None
    except DBAPIError as err:
        raise CohortRefused("--db {}: the copy could not be read ({!r}); nothing reported".format(copy, err.orig))
    if sides_after:
        raise CohortRefused("--db {} changed during the read: {} appeared beside it; nothing reported".format(
            copy, ", ".join(sides_after)))
    if sha_after != sha_before:
        raise CohortRefused("--db {} changed during the read (sha256 {}... before, {}... after); nothing "
                            "reported".format(copy, sha_before[:16], sha_after[:16]))
    return sha_before, out


# --------------------------------------------------------------------------
# The read (counts only)
# --------------------------------------------------------------------------


def _stage(v) -> str:
    return "(none)" if v is None or not str(v).strip() else str(v)


def read_counts(s, afters: list) -> dict:
    """Every count the receipt prints, from the session `s` (the copy's). No row leaves this function."""
    from sqlalchemy import select

    from src.db.schema import Competition, Match, MatchStatus, NHLGoalieAppearance, NHLShotEvent, Sport
    from src.ingestion.nhl_goalies import season_label
    from src.walters import nhl_backtest as nb
    from src.walters import nhl_shadow as ns

    starts = ns._season_starts()
    q = (select(Match.id, Match.utc_date, Match.status, Match.status_raw, Match.stage, Match.home_team_id,
                Match.away_team_id, Match.home_score, Match.away_score)
         .join(Competition, Match.competition_id == Competition.id)
         .where(Match.sport == Sport.NHL, Competition.code == COMPETITION_CODE, Match.season == SEASON))
    games = [dict(id=r[0], utc=r[1], status=r[2], raw=r[3], stage=r[4], home=r[5], away=r[6], hs=r[7], as_=r[8])
             for r in s.execute(q)]
    c: dict = {"n": len(games), "statuses": [m.name for m in MatchStatus], "starts": str(starts.get(SEASON))}

    # Q0: stage by status, the shadow's preseason rule beside
    q0 = defaultdict(Counter)
    pre = Counter()
    for g in games:
        q0[_stage(g["stage"])][g["status"].name] += 1
        why = nb.preseason_reason(nb.Game(g["home"], g["away"], SEASON, g["utc"], 0, 0, g["stage"] or ""), starts)
        g["pre"] = why
        if why:
            pre[why] += 1
    c["q0"] = {k: dict(v) for k, v in sorted(q0.items())}
    c["preseason"] = dict(pre)

    # Q1: the six, as 445 item 3(b) finds them
    first = {}
    for g in games:
        for t in (g["home"], g["away"]):
            if t not in first or g["utc"] < first[t]:
                first[t] = g["utc"]
    clubs = {t for t, d in first.items() if d >= INTL_NO_GAME_BEFORE}
    six = [g for g in games if g["home"] in clubs and g["away"] in clubs]
    differs = []
    if len(clubs) != INTL_CLUBS:
        differs.append("{} clubs with no game before {} (445 item 3(b): {})".format(
            len(clubs), INTL_NO_GAME_BEFORE.date(), INTL_CLUBS))
    if len(six) != INTL_GAMES:
        differs.append("{} games between them (445 item 3(b): {})".format(len(six), INTL_GAMES))
    off_time = sum(1 for g in six if g["utc"] != INTL_KICKOFF)
    if off_time:
        differs.append("{} of them not at {}Z".format(off_time, INTL_KICKOFF.isoformat()))
    touching = sum(1 for g in games if (g["home"] in clubs) != (g["away"] in clubs))
    if touching:
        differs.append("{} games between one of them and another club".format(touching))
    found = not differs
    c["q1"] = {"found": found, "differs": differs, "clubs": len(clubs), "games": len(six),
               "at_kickoff": len(six) - off_time,
               "status": dict(Counter(g["status"].name for g in six)),
               "raw": dict(Counter(g["raw"] or "(none)" for g in six))}
    apart = {g["id"] for g in six} if found else set()

    league = [g for g in games if g["id"] not in apart and not g["pre"]]

    # Q2: month by status, played and to come, status_raw beside
    q2 = defaultdict(lambda: {"status": Counter(), "raw": defaultdict(Counter), "played": 0, "finished_no_score": 0,
                              "to_come": 0})
    for g in league:
        b = q2[et_month(g["utc"])]
        st = g["status"].name
        b["status"][st] += 1
        b["raw"][st][g["raw"] or "(none)"] += 1
        if g["status"] == MatchStatus.FINISHED:
            if g["hs"] is not None and g["as_"] is not None:
                b["played"] += 1
            else:
                b["finished_no_score"] += 1
        elif g["status"] == MatchStatus.SCHEDULED:
            b["to_come"] += 1
    c["q2"] = {m: {"status": dict(b["status"]), "raw": {k: dict(v) for k, v in b["raw"].items()},
                   "played": b["played"], "finished_no_score": b["finished_no_score"], "to_come": b["to_come"]}
               for m, b in sorted(q2.items())}

    # Q3: the played games against the goalie table's game type
    played_ids = {g["id"] for g in league if g["status"] == MatchStatus.FINISHED and g["hs"] is not None
                  and g["as_"] is not None}
    types = defaultdict(set)
    goalie_games = {}                              # nhl_game_id -> (types seen, match ids seen, start)
    for nid, mid, start, gt in s.execute(select(NHLGoalieAppearance.nhl_game_id, NHLGoalieAppearance.match_id,
                                                NHLGoalieAppearance.game_start, NHLGoalieAppearance.game_type)):
        if mid is not None:
            types[mid].add(gt)
        e = goalie_games.setdefault(nid, [set(), set(), start])
        e[0].add(gt)
        if mid is not None:
            e[1].add(mid)
    q3 = Counter()
    for mid in played_ids:
        seen = types.get(mid)
        if not seen:
            q3["no goalie row linked"] += 1
        elif seen == {REGULAR_TYPE}:
            q3["game type 2"] += 1
        elif seen == {3}:
            q3["game type 3"] += 1
        elif seen == {None}:
            q3["game type not stated"] += 1
        else:
            q3["game types disagree"] += 1
    cohort_ids = {g["id"] for g in games}
    unlinked = Counter()
    for nid, (gts, mids, start) in goalie_games.items():
        if season_label(start) != SHOT_SEASON or gts != {REGULAR_TYPE}:
            continue
        if not mids:
            unlinked["no match_id"] += 1
        elif not (mids & played_ids):
            unlinked["linked outside the played set" if mids & cohort_ids else "linked outside the cohort"] += 1
    c["q3"] = {"played": len(played_ids), "by_type": dict(q3), "goalie_type2_not_played": dict(unlinked)}

    # Q4 and Q6: the shot events, by the season of their game's start
    q4 = defaultdict(lambda: {"events": 0, "per_game": defaultdict(set), "unlinked": set()})
    q6 = {"events": 0, "per_game": defaultdict(set), "unlinked": set()}
    for nid, mid, start, gt in s.execute(select(NHLShotEvent.nhl_game_id, NHLShotEvent.match_id,
                                                NHLShotEvent.game_start, NHLShotEvent.game_type)):
        lab = season_label(start)
        if lab == SHOT_SEASON:
            b = q4[et_month(start)]
        elif lab == HISTORY_SEASON:
            b = q6
        else:
            continue
        b["events"] += 1
        b["per_game"][nid].add(gt)
        if mid is None:
            b["unlinked"].add(nid)

    def shots(b) -> dict:
        return {"events": b["events"], "games": len(b["per_game"]),
                "games_by_type": dict(Counter(_type_label(g) for g in b["per_game"].values())),
                "games_no_match_id": len(b["unlinked"])}
    c["q4"] = {m: shots(b) for m, b in sorted(q4.items())}
    c["q6"] = shots(q6)

    # Q5: for each --after DATE, the games to come after it, by stored stage
    c["q5"] = []
    for d in afters:
        by = Counter(_stage(g["stage"]) for g in league
                     if g["status"] == MatchStatus.SCHEDULED and et_date(g["utc"]) > d)
        c["q5"].append({"after": d.isoformat(), "to_come": sum(by.values()), "by_stage": dict(sorted(by.items()))})
    return c


def _type_label(gts: set) -> str:
    if gts == {REGULAR_TYPE}:
        return "type 2"
    if gts == {3}:
        return "type 3"
    if gts == {None}:
        return "type not stated"
    return "types disagree"


# --------------------------------------------------------------------------
# Printing
# --------------------------------------------------------------------------


def _counts(d: dict) -> str:
    return " · ".join("{} {}".format(k, v) for k, v in sorted(d.items())) or "none"


def render(c: dict, out: Callable[[str], None]) -> None:
    out("RULES: cohort = matches of competition code {!r}, sport NHL, season {!r} ({} games stored); statuses as "
        "stored ({}); played = FINISHED with both scores; to come = SCHEDULED; preseason = the shadow's rule (a stage "
        "containing 'pre', or a game before the opener {}); months and dates are America/New_York; the goalie and "
        "shot tables' season is the game start's, 1 July to 30 June; counts only, no row".format(
            COMPETITION_CODE, SEASON, c["n"], ", ".join(c["statuses"]), c["starts"]))
    out("Q0 STAGE BY STATUS (stage as stored; '(none)' = NULL or empty):")
    for stage, by in c["q0"].items():
        out("  {!r}: {}".format(stage, _counts(by)))
    out("  preseason by the shadow's rule: {} (kept out of Q2, Q3 and Q5)".format(_counts(c["preseason"])))
    q1 = c["q1"]
    out("Q1 THE SIX INTERNATIONAL GAMES (445 item 3(b)):")
    if q1["found"]:
        out("  FOUND as 445 item 3(b) finds them: {} clubs with no game before {}, {} games between them, all at "
            "{}Z; status {}; status_raw {}; counted apart and kept out of Q2 to Q5".format(
                q1["clubs"], INTL_NO_GAME_BEFORE.date(), q1["games"], INTL_KICKOFF.isoformat(), _counts(q1["status"]),
                _counts(q1["raw"])))
    else:
        out("  NOT FOUND as 445 item 3(b) finds them: {}. Nothing is counted for them and nothing is set apart: Q2 "
            "to Q5 include every non-preseason game of the cohort".format("; ".join(q1["differs"])))
    out("Q2 MONTH BY STATUS (league games; played and to come; status_raw beside):")
    for m, b in c["q2"].items():
        raw = " | ".join("{}: {}".format(st, _counts(r)) for st, r in sorted(b["raw"].items()))
        out("  {}: {} · played {} · to come {}{} · status_raw [{}]".format(
            m, _counts(b["status"]), b["played"], b["to_come"],
            " · FINISHED without both scores {}".format(b["finished_no_score"]) if b["finished_no_score"] else "",
            raw))
    tot = Counter()
    for b in c["q2"].values():
        tot.update(b["status"])
    out("  total: {} · played {} · to come {}".format(_counts(dict(tot)), sum(b["played"] for b in c["q2"].values()),
                                                     sum(b["to_come"] for b in c["q2"].values())))
    q3 = c["q3"]
    out("Q3 PLAYED AGAINST THE GOALIE TABLE'S GAME TYPE (by match_id): played {} · {}".format(
        q3["played"], _counts(q3["by_type"])))
    out("  goalie-table games of {} with game type 2 and no played cohort game: {}".format(
        SHOT_SEASON, _counts(q3["goalie_type2_not_played"])))
    out("Q4 SHOT EVENTS OF {} BY MONTH (by the game's start):".format(SHOT_SEASON))
    if not c["q4"]:
        out("  none stored")
    for m, b in c["q4"].items():
        out("  {}: events {} · games {} ({}) · games with no match_id {}".format(
            m, b["events"], b["games"], _counts(b["games_by_type"]), b["games_no_match_id"]))
    out("Q5 TO COME AFTER EACH --after DATE (SCHEDULED league games whose America/New_York date is later; by stored "
        "stage; {}):".format(UNVERIFIED))
    if not c["q5"]:
        out("  no --after date given")
    for r in c["q5"]:
        out("  after {}: {} to come · by stage {}".format(r["after"], r["to_come"], _counts(r["by_stage"])))
    q6 = c["q6"]
    out("Q6 THE {} SHOT GAMES: games {} ({}) · events {} · games with no match_id {}".format(
        HISTORY_SEASON, q6["games"], _counts(q6["games_by_type"]), q6["events"], q6["games_no_match_id"]))


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def _parse_date(s: str) -> date:
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise argparse.ArgumentTypeError("not a YYYY-MM-DD date: {!r}".format(s))


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="nhl_cohort_count.py",
                                 description="Read-only NHL 2026-27 cohort counts on a .backup copy (addendum 523).")
    ap.add_argument("--db", required=True, metavar="COPY",
                    help="a .backup copy of the database (mode=ro + immutable=1; never under data/, never the "
                         "configured database)")
    ap.add_argument("--after", action="append", default=[], type=_parse_date, metavar="YYYY-MM-DD",
                    help="print the regular-season games to come after this date (repeatable)")
    return ap


def main(argv: list | None = None, out: Callable[[str], None] = print) -> int:
    args = _parser().parse_args(argv)
    out("THE NHL COHORT COUNT (read-only; counts only; no row, no model, no figure; nothing written)")
    try:
        copy = check_copy(args.db)
        sha, counts = on_copy(copy, lambda s: read_counts(s, args.after))
    except CohortRefused as e:
        out("REFUSED: {}".format(e))
        return 2
    out("--db {} · sha256 {} (the same after the read; no sidecar)".format(copy, sha))
    render(counts, out)
    out("END: exit 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
