"""
THE QUARTERBACK AGREEMENT RECEIPT (lane nfl-qb, #427; the roadmap step of 2026-12-15; ARCHITECT 2026-11-16 12:55 ET,
addendum 415 item 4(a); 465 items 3 Q6 and 5; built by DEV 4, Lane D, on 529 item 4; ruled by 530 items 4 to 6).
READ-ONLY: a .backup copy of the database and the kept provider payloads; no network, no write.

415 item 4(a), the step, verbatim: "the quarterback agreement receipt, read-only, on the availability record: for every
2026 NFL game that kicked off after the feed's first load on our clock, the depth chart's first quarterback as of 24 h
before kickoff and as of kickoff, each beside the game's starter read post hoc (the most pass attempts, the QB probe's
rule), with the counts of agree, differ and no row; and the same two reads on nflverse's own load times for the 2025
season, labelled as the source's clock. It prints counts and judges nothing; no threshold exists and none is to be
suggested".

THE NAMES IT READS (law 1; each from the code, never copied as a guess):
- THE GAMES: matches selected through nfl_backtest.nfl_scoped (Sport.NFL and Competition.code "NFL": college stays
  out), season "2026" and "2025"; the preseason out by nfl_backtest.is_preseason (a stage containing "pre"; 530 Q5);
  the regular season and the postseason in. A side is paired only on a FINISHED game; the others are counted by
  status. The kickoff is matches.utc_date (stored naive UTC).
- THE CHART'S FIRST QUARTERBACK: record.as_of (src/availability/record.py, "the one read path") at the instant, kind
  depth_rank, team = our team id, on the RECORDED clock for 2026 and the SOURCE clock (nflverse's own dt) for 2025;
  the facts of source nflverse_depth_charts whose attrs.pos_abb is "QB"; the first quarterback is the one player whose
  attrs.pos_rank is "1" (src/availability/nflverse.py: the attrs columns, strings). Two players at rank 1 in force at
  once (different groups or slots) is "QB1 ambiguous", counted, never chosen (530 Q3; law 4).
- THE 2026 WINDOW (530 Q2): it opens at the first observation of the 2026 depth chart, the earliest fetched_at of an
  asserting (complete or partial) observation of source nflverse_depth_charts whose endpoint is
  nflverse.release_url(2026); read from the copy and printed. A 2026 game is read when it kicked off after it. A game
  that kicked off less than 24 hours after it has no T-24h row on our clock: a no-row cause of its own. A hand-carried
  file's observations (endpoint "file:...") are counted and printed, never the window's start.
- THE STARTER, post hoc (530 Q1; 465 Q6): from the payloads scripts/nfl_qb_coverage.py keeps under --payloads DIR,
  <DIR>/<season>/players_<provider game id>.json, read exactly as that script reads them (its cache file names; the
  probe's passing_lines and attempts). The provider game is the match's external_ids["api_american_football"], looked
  up within its season only (#906); the side's block is the one whose team.id is the team's
  external_ids["api_american_football"]. The starter is the passer with the most attempts; no readable attempts, or a
  tie for the most, names none (the coverage script's rule). A game with no kept payload is "no starter payload",
  counted apart, and never fetched: this receipt makes no call.
- THE PAIRING (465 item 5; 530 Q4 and item 5): within one game and one team. "Paired by id" needs an id both sources
  carry; the chart carries espn_id and gsis_id and the provider its own id, so no common id exists and that class
  reads 0, said as such. "Paired by name within the team" uses one normalisation on both sides (norm, below):
    AGREE    the chart's first quarterback and the starter normalise to one name;
    DIFFER   the names differ and at least one of them is found on the other side: the chart's first quarterback
             among that team's passers of the game, or the starter at another rank of that team's chart at that
             instant; every DIFFER is also counted by the starter's place on the chart: second, third or lower, or
             not on the chart (a count, not a judgment);
    NO PAIR  the names differ and neither is found on the other side; and wherever two players of one team in one game
             normalise to one name, on either side (never chosen, 530 Q4).
- THE NORMALISATION (465 item 5: "written in the PR body before the first run"; 530 Q4): Unicode NFKD, combining marks
  dropped; casefold; every character that is not a letter, a digit or a space removed; whitespace collapsed; one
  trailing suffix Jr, Sr, II, III or IV dropped.

PRINTED, per season and read (2026 T-24h and T-0 on our clock; 2025 T-24h and T-0 labelled as the source's clock):
the sides read; agree, differ (and differ by the starter's place on the chart) and no pair, each in its pair class;
the sides with no row, by the chart side's cause and by the starter side's cause; the games by status. Then the
attribution the record requires ("Depth charts: nflverse (CC BY 4.0)", record.attributions). COUNTS ONLY: no player's
name, no id, no row (530 item 6); no threshold, no verdict (415 item 4(a)); no model output and no figure of any
candidate (465 item 4(a); 529 item 4).

--db COPY: a .backup copy outside any data/ directory (mlb_pitchers_gate.check_db, and any path part named data, case
ignored), refused beside a -wal, -shm or -journal file, each table the read touches probed, opened mode=ro +
immutable=1 (198 item 6(ii)); its sha256 printed before the read and checked again after it. --payloads DIR: a folder,
never under a data/ directory, only read. Nothing is written anywhere (sys.dont_write_bytecode: no __pycache__).
EXIT 0 when the read reached its end; 2 on a refusal, nothing reported. The last line: NFL-QB-AGREEMENT-RECEIPT {json}.

    python3 scripts/nfl_qb_agreement_receipt.py --db COPY --payloads DIR

The run is the architect's block on a copy of the host's backup (OPERATOR ONLY), after this is on main (530 item 6).
Python 3.10 is the floor (CONTRIBUTING.md).
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True      # "nothing written": no __pycache__ of the repo's code (as nhl_cohort_count)

import argparse  # noqa: E402
import errno  # noqa: E402
import json  # noqa: E402
import sqlite3  # noqa: E402
import unicodedata  # noqa: E402
from collections import Counter, defaultdict  # noqa: E402
from datetime import datetime, timedelta  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Callable  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TAIL = "NFL-QB-AGREEMENT-RECEIPT"
PROVIDER = "api_american_football"           # the adapter's source_name (external_ids key for matches and teams)
SOURCE = "nflverse_depth_charts"             # nflverse.SOURCE
KIND = "depth_rank"                          # nflverse.KIND
QB, FIRST = "QB", "1"                        # attrs.pos_abb, attrs.pos_rank (strings, as the feed stores them)
SUFFIXES = ("jr", "sr", "ii", "iii", "iv")
READS = (("T-24h", timedelta(hours=24)), ("T-0", timedelta(0)))
SEASONS = (("2026", "recorded"), ("2025", "source"))
COPY_TABLES = ("competitions", "matches", "teams", "availability_observations", "availability_assertions")
NO_COMMON_ID = ("paired by id: 0 (no id is carried by both sources: the chart carries espn_id and gsis_id, the provider "
                "its own player id; 465 item 5)")


class ReceiptRefused(RuntimeError):
    """A refused read: exit 2, nothing reported."""


# --------------------------------------------------------------------------
# The normalisation (530 Q4)
# --------------------------------------------------------------------------


def norm(name) -> str | None:
    """One name as both sides compare it: NFKD with combining marks dropped, casefold, only letters, digits and spaces
    kept, whitespace collapsed, one trailing Jr / Sr / II / III / IV dropped. None for no name."""
    if not isinstance(name, str):
        return None
    t = "".join(ch for ch in unicodedata.normalize("NFKD", name) if not unicodedata.combining(ch)).casefold()
    t = "".join(ch for ch in t if ch.isalnum() or ch.isspace())
    words = t.split()
    if len(words) > 1 and words[-1] in SUFFIXES:
        words = words[:-1]
    out = " ".join(words)
    return out or None


# --------------------------------------------------------------------------
# The copy
# --------------------------------------------------------------------------


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
    """soccer_expansion.check_copy's fence with this read's tables."""
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
        finally:
            con.close()
    except mp.GateRefused as err:
        raise ReceiptRefused("{}; nothing read".format(err))
    return path


def check_payloads(d) -> Path:
    if d is None or not str(d).strip():
        raise ReceiptRefused("--payloads DIR is required: the folder scripts/nfl_qb_coverage.py keeps (530 Q1)")
    why = _named_data(d)
    if why:
        raise ReceiptRefused("--payloads " + why + "; nothing read")
    p = Path(str(d)).expanduser()
    if not p.is_dir():
        raise ReceiptRefused("--payloads {}: not a folder; nothing read".format(d))
    return p


def on_copy(copy: Path, read):
    """(sha256 before, read(s)) on the copy's mode=ro + immutable=1 session, refused when the copy changed during the
    read or a sidecar appeared (soccer_expansion.on_copy's two checks); any failure by its class alone."""
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
    except Exception as err:      # by its class alone: never a traceback that could carry a stored value or a name
        raise ReceiptRefused("--db {}: the read failed ({}); nothing reported".format(copy, type(err).__name__))
    if sides_after:
        raise ReceiptRefused("--db {} changed during the read: {} appeared beside it; nothing reported".format(
            copy, ", ".join(sides_after)))
    if sha_after != sha_before:
        raise ReceiptRefused("--db {} changed during the read (sha256 {}... before, {}... after); nothing "
                             "reported".format(copy, sha_before[:16], sha_after[:16]))
    return sha_before, out


# --------------------------------------------------------------------------
# The starter side (the kept payloads)
# --------------------------------------------------------------------------


def _probe():
    import importlib.util
    spec = importlib.util.spec_from_file_location("nfl_qb_probe_for_427", ROOT / "scripts" / "nfl_qb_probe.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def starter_side(payloads: Path, season: str, gid, team_pid, probe) -> tuple:
    """(cause, starter's normalised name, {normalised passer names}) for one side; cause None when a starter is named.
    Read as scripts/nfl_qb_coverage.py keeps and reads them; never fetched."""
    if gid is None:
        return "the match carries no provider game id", None, set()
    f = payloads / season / "players_{}.json".format(gid)
    if not f.is_file():
        return "no starter payload", None, set()
    try:
        teams = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "the starter payload cannot be read", None, set()
    if not isinstance(teams, list):
        return "the starter payload cannot be read", None, set()
    if team_pid is None:
        return "the team carries no provider id", None, set()
    block = [tb for tb in teams if isinstance(tb, dict) and isinstance(tb.get("team"), dict)
             and str(tb["team"].get("id")) == str(team_pid)]
    if len(block) != 1:
        return ("no block for the side in the payload" if not block else "two blocks for the side"), None, set()
    lines = probe.passing_lines(block[0])
    if not lines:
        return "no passing line for the side", None, set()
    names = [norm(p.get("name")) if isinstance(p, dict) else None for p, _st in lines]
    read = [(probe.attempts(st), i) for i, (_p, st) in enumerate(lines) if probe.attempts(st) is not None]
    if not read:
        return "no attempts read", None, set(n for n in names if n)
    most = max(a for a, _i in read)
    leaders = [i for a, i in read if a == most]
    if len(leaders) != 1:
        return "tied for the most attempts", None, set(n for n in names if n)
    top = leaders[0]
    if names[top] is None:
        return "the starter has no name", None, set(n for n in names if n)
    # two passers of one team in one game whose names normalise to one string: never chosen (530 Q4)
    if sum(1 for n in names if n == names[top]) > 1:
        return "two passers' names normalise to one", None, set(n for n in names if n)
    return None, names[top], set(n for n in names if n)


# --------------------------------------------------------------------------
# The chart side (the availability record)
# --------------------------------------------------------------------------


def chart_side(s, instant: datetime, clock: str, team_id: int) -> tuple:
    """(cause, QB1's normalised name, {normalised name: lowest rank}) for one team at one instant, through
    record.as_of (the one read path); cause None when one QB1 is named."""
    from src.availability import record as rec
    from src.db.schema import Sport
    facts = rec.as_of(s, Sport.NFL, instant, clock=clock, team=str(team_id), kind=KIND)
    qbs = []                                     # (player key, normalised name, rank text)
    for f in facts:
        r = f.interval.last
        if r.source != SOURCE:
            continue
        at = r.attrs or {}
        if str(at.get("pos_abb")) != QB:
            continue
        qbs.append((rec.player_key(r), norm(r.player_name), str(at.get("pos_rank"))))
    if not qbs:
        return "no quarterback in force", None, {}
    ranks: dict = {}
    for _k, n, rk in qbs:
        if n is None:
            continue
        r = int(rk) if rk.isdigit() else None
        if r is not None and (n not in ranks or r < ranks[n]):
            ranks[n] = r
    firsts = {(k, n) for k, n, rk in qbs if rk == FIRST}
    if not firsts:
        return "no first quarterback in force", None, ranks
    if len({k for k, _n in firsts}) > 1:
        return "QB1 ambiguous", None, ranks
    n1 = next(iter(firsts))[1]
    if n1 is None:
        return "the first quarterback has no name", None, ranks
    if len({k for k, n, _rk in qbs if n == n1}) > 1:
        return "two chart names normalise to one", None, ranks
    return None, n1, ranks


# --------------------------------------------------------------------------
# The read
# --------------------------------------------------------------------------


def first_2026_load(s) -> tuple:
    """(the earliest fetched_at of an asserting observation of release_url(2026), the count of hand-carried file
    observations of the source)."""
    from sqlalchemy import func, select

    from src.availability import nflverse as nv
    from src.availability import record as rec
    from src.db.schema import AvailabilityObservation as O
    first = s.execute(select(func.min(O.fetched_at)).where(
        O.source == SOURCE, O.endpoint == nv.release_url(2026), O.status.in_(rec.ASSERTING))).scalar()
    files = s.execute(select(func.count()).select_from(O).where(
        O.source == SOURCE, O.endpoint.like("file:%"))).scalar()
    if isinstance(first, str):
        first = datetime.fromisoformat(first)
    return first, int(files or 0)


def read_counts(s, payloads: Path) -> dict:
    from sqlalchemy import select

    from src.db.schema import Match, MatchStatus, Team
    from src.walters import nfl_backtest as nb
    probe = _probe()
    first26, file_obs = first_2026_load(s)
    team_pid = {tid: (ext or {}).get(PROVIDER) for tid, ext in s.execute(select(Team.id, Team.external_ids))}
    out = {"first_2026_load": first26.isoformat() + "Z" if first26 else None, "file_observations": file_obs,
           "seasons": []}
    for season, clock in SEASONS:
        q = nb.nfl_scoped(select(Match.id, Match.utc_date, Match.status, Match.stage, Match.home_team_id,
                                 Match.away_team_id, Match.external_ids).where(Match.season == season))
        games = [r for r in s.execute(q) if not nb.is_preseason(r[3])]
        status = Counter(r[2].name for r in games)
        if season == "2026":
            window = [r for r in games if first26 is not None and r[1] > first26]
            before = len(games) - len(window)
        else:
            window, before = games, 0
        finished = [r for r in window if r[2] == MatchStatus.FINISHED]
        reads = []
        for label, back in READS:
            c = {"read": label, "clock": clock, "sides": 0, "agree": 0, "differ": 0, "no_pair": 0,
                 "differ_by_place": Counter(), "no_pair_by": Counter(), "chart_cause": Counter(),
                 "starter_cause": Counter(), "no_row": 0}
            for mid, kick, _st, _sg, home, away, ext in finished:
                gid = (ext or {}).get(PROVIDER)
                instant = kick - back
                for tid in (home, away):
                    c["sides"] += 1
                    if season == "2026" and clock == "recorded" and first26 is not None and instant < first26:
                        ccause, q1, ranks = "no T-24h row on our clock (kickoff less than 24 h after the first load)", \
                            None, {}
                    else:
                        ccause, q1, ranks = chart_side(s, instant, clock, tid)
                    scause, st, passers = starter_side(payloads, season, gid, team_pid.get(tid), probe)
                    if ccause or scause:
                        c["no_row"] += 1
                        if ccause:
                            c["chart_cause"][ccause] += 1
                        if scause:
                            c["starter_cause"][scause] += 1
                        continue
                    if q1 == st:
                        c["agree"] += 1
                    elif q1 in passers or st in ranks:
                        c["differ"] += 1
                        rk = ranks.get(st)
                        c["differ_by_place"]["not on the chart" if rk is None else "second" if rk == 2
                                             else "third or lower" if rk >= 3 else "first at another slot"] += 1
                    else:
                        c["no_pair"] += 1
                        c["no_pair_by"]["neither name found on the other side"] += 1
            reads.append(c)
        out["seasons"].append({"season": season, "clock": clock, "games": len(games), "status": dict(status),
                               "before_window": before, "finished_in_window": len(finished), "reads": reads})
    return out


# --------------------------------------------------------------------------
# Printing
# --------------------------------------------------------------------------


def _counts(d) -> str:
    return " · ".join("{} {}".format(k, v) for k, v in sorted(dict(d).items())) or "none"


def render(c: dict, out: Callable[[str], None]) -> None:
    from src.availability import record as rec
    out("RULES: games = NFL (code NFL), preseason out (nfl_backtest.is_preseason), paired on FINISHED games; the chart "
        "= record.as_of, depth_rank, pos_abb QB, rank 1 the first; the starter = the most attempts in the kept "
        "payload, a tie names none; names compared after one normalisation (NFKD, marks dropped, casefold, letters "
        "digits and spaces, one trailing Jr/Sr/II/III/IV dropped); counts only, no name, no id, no threshold")
    out("THE 2026 WINDOW: the first observation of the 2026 depth chart on our clock: {} (hand-carried file "
        "observations, never the window's start: {})".format(c["first_2026_load"] or "NONE STORED", c["file_observations"]))
    for sea in c["seasons"]:
        lab = "our clock" if sea["clock"] == "recorded" else "THE SOURCE'S CLOCK (nflverse's own load times)"
        out("SEASON {} ({}): games {} by status {}; before the window {}; finished in the window {}".format(
            sea["season"], lab, sea["games"], _counts(sea["status"]), sea["before_window"], sea["finished_in_window"]))
        for r in sea["reads"]:
            out("  {} [{}]: sides {} · agree {} · differ {} · no pair {} · no row {}".format(
                r["read"], lab, r["sides"], r["agree"], r["differ"], r["no_pair"], r["no_row"]))
            out("    pair classes: {}; paired by name within the team: {}".format(
                NO_COMMON_ID, r["agree"] + r["differ"]))
            out("    differ, by the starter's place on the chart: {}".format(_counts(r["differ_by_place"])))
            out("    no row, the chart side: {}".format(_counts(r["chart_cause"])))
            out("    no row, the starter side: {} (a side missing both is counted under each)".format(
                _counts(r["starter_cause"])))
    for line in rec.attributions([SOURCE]):
        out(line)


def _json(c: dict) -> str:
    return json.dumps(c, sort_keys=True, default=str)


def main(argv: list | None = None, out: Callable[[str], None] = print) -> int:
    ap = argparse.ArgumentParser(prog="nfl_qb_agreement_receipt.py",
                                 description="Read-only quarterback agreement counts (lane nfl-qb, #427).")
    ap.add_argument("--db", required=True, metavar="COPY", help="a .backup copy of the database (mode=ro + "
                    "immutable=1; never under data/, never the configured database)")
    ap.add_argument("--payloads", required=True, metavar="DIR", help="the folder scripts/nfl_qb_coverage.py keeps "
                    "(<DIR>/<season>/players_<game id>.json); only read")
    args = ap.parse_args(argv)
    out("THE QUARTERBACK AGREEMENT RECEIPT (read-only; counts only; no name, no id, no threshold; no network; "
        "nothing written)")
    try:
        payloads = check_payloads(args.payloads)
        copy = check_copy(args.db)
        sha, counts = on_copy(copy, lambda s: read_counts(s, payloads))
    except ReceiptRefused as e:
        out("REFUSED: {}".format(e))
        return 2
    out("--db {} · sha256 {} (the same after the read; no sidecar) · --payloads {}".format(copy, sha, payloads))
    render(counts, out)
    out("{} {}".format(TAIL, _json(counts)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
