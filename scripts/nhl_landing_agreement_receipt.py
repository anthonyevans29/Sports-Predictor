"""
THE NHL LANDING AGREEMENT RECEIPT (ARCHITECT 2026-11-13 11:20 ET, addendum 370 item 1; lane nhl, #105). READ-ONLY:
a .backup copy of the database, no network, no write.

370 item 1, verbatim: "THE GOALIE AGREEMENT RECEIPT (read-only; lane nhl, #105; wanted by 11-19). The landing watch now
stores, for every game, what the league's page showed at each poll and who started. The operator's sourcing decision
turns on one question the store can answer: HOW OFTEN, AND HOW EARLY, DOES THE PAGE NAME THE EVENTUAL STARTER?
`scripts/nhl_landing_agreement_receipt.py --db COPY` (a .backup copy outside data/, mode=ro + immutable=1; no network;
no write): per poll label T-120 … T-0, over the sides that have both a projected_starter at that label and an
eventual_starter for the game, the count and share whose source_player_id is the same; the same by day; the sides left
out and why (no eventual, a missed poll, a partial); the first label from which a side's projection never changed
again, as a distribution. It prints counts and shares and JUDGES NOTHING — no threshold exists and none is to be
suggested. Run by my block on the host's own backup copy."

WHAT IT READS (law 1: the names are the feed's own, src/availability/nhl_landing.py, imported, never copied): the
observations of source `nhl_api_landing` that carry a poll_label, and their projected_starter / eventual_starter
assertions. The game is the NHL gameId in the observation's endpoint (nhl_landing.game_url: /v1/gamecenter/<id>/<landing
or boxscore>). The labels are nhl_landing.PREGAME (T-120 .. T-0) and nhl_landing.EVENTUAL (T+20). The day is the game's
NHL day (nhl_landing.nhl_day: [date 10:00Z, date+1 10:00Z)) of its stored kickoff.

A SIDE is (gameId, attrs.side: away or home). Its PROJECTION at a label is the source_player_id of the one
projected_starter that label's observation asserted for the side. There is none when:
  - the store holds no observation of the game at that label (`no row`);
  - the observation is missed, failed or empty (`missed poll`, `failed poll`, `empty landing`);
  - the observation is partial (`partial poll`: a team or the match left unmapped, 254 item 2(7); left out, as 370
    item 1 names it);
  - the observation is complete but asserted nothing for the side (`side not asserted`: the receipt's leader0 found no
    leaders[0] for it, or the schedule named no team);
  - or it asserted more than one for the side (`two projections`, never chosen).
Its EVENTUAL is the source_player_id of the one eventual_starter the game's T+20 observation asserted for the side,
read as the leaders receipt reads it. There is none when:
  - there is no T+20 row (`no T+20 row`);
  - the T+20 row is missed, failed or empty (`T+20 missed` / `T+20 failed` / `T+20 empty`);
  - it is partial (`T+20 partial`);
  - the side has no goalie above zero toi (`no goalie above zero toi read for the side`);
  - two or more goalies are above zero (`two in net`, counted, never chosen);
  - or one is above zero beside a goalie whose toi the ingest could not read (`toi unread`, law 4: that goalie may be
    a second in net).
A GAME WITH MORE THAN ONE SERIES (a label written twice, or stored kickoffs SERIES_SCOPE or more apart: a
postponement, addendum 343 item 1) is left out whole, its id printed: which series' polls belong to which start is not
read here.

PRINTED:
  - per label, n = the sides with both a projection at the label and an eventual; agree = those whose two
    source_player_ids are the same; the share, agree / n, to four places;
  - the same per NHL day;
  - the sides left out per label, each counted once under its two reasons (projection, eventual);
  - the observations per label by status, and the late ones among the answered;
  - the FIRST STABLE LABEL per side, OBSERVED: walking back from T-0, the earliest label from which every label named
    the T-0 playerId, every one of them answered; as a distribution, split by whether that projection is the eventual
    (agree), is not (differ), or the eventual is unread. A run broken by a label with no projection is counted apart
    (stable from the label after the gap at the latest; whether it changed across the gap is not observed), and so are
    the sides with no T-0 projection: a stable run is never claimed across a label the store did not see;
  - the observations at a label that is not the feed's (in no count), by id.
Counts and shares only: no threshold, no verdict, no judgement (370 item 1).

--db: a .backup copy outside the repo's data/ (mlb_pitchers_gate.check_db), refused with a -wal / -shm / -journal beside
it (immutable=1 would ignore it), opened mode=ro&immutable=1. Refusals exit 2, nothing read; a copy without the
availability tables is refused the same way. Exit 0 otherwise. The last line: NHL-LANDING-AGREEMENT-RECEIPT {json}.

    python3 scripts/nhl_landing_agreement_receipt.py --db /path/to/backup-copy.db
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.availability import nhl_landing as nl  # noqa: E402  (the feed's own labels, series scope and NHL day)

REFUSED = 2
SIDECARS = ("-wal", "-shm", "-journal")      # immutable=1 would ignore each of them
TAIL = "NHL-LANDING-AGREEMENT-RECEIPT"
PREGAME = tuple(label for label, _ in nl.PREGAME)
EVENTUAL = nl.EVENTUAL[0]
SIDES = nl.SIDES
GAME_OF = re.compile(r"/v1/gamecenter/(\d+)/(" + nl.LANDING + "|" + nl.BOXSCORE + r")$")
READ = "read"


def collect(s) -> dict:
    """{gameId: {"rows": [observation dict, ...]}} for every polled observation of the source, with its two kinds of
    assertion attached to its observation. Nothing is written; the session is rolled back."""
    from sqlalchemy import select

    from src.db.schema import AvailabilityAssertion, AvailabilityObservation
    games: dict = defaultdict(lambda: {"rows": []})
    unparsed = []
    obs = {}
    for o in s.execute(select(AvailabilityObservation)
                       .where(AvailabilityObservation.source == nl.SOURCE,
                              AvailabilityObservation.poll_label.is_not(None))
                       .order_by(AvailabilityObservation.id)).scalars():
        m = GAME_OF.search(o.endpoint or "")
        if m is None:
            unparsed.append(o.id)
            continue
        row = {"id": o.id, "game": m.group(1), "endpoint": m.group(2), "label": o.poll_label, "status": o.status,
               "kickoff": o.kickoff_at, "late": bool(o.late), "asserted": []}
        obs[o.id] = row
        games[row["game"]]["rows"].append(row)
    kinds = ("projected_starter", "eventual_starter")
    # this source's two kinds only (the join): another source's rows are never loaded
    for a in s.execute(select(AvailabilityAssertion)
                       .join(AvailabilityObservation, AvailabilityAssertion.observation_id == AvailabilityObservation.id)
                       .where(AvailabilityObservation.source == nl.SOURCE, AvailabilityAssertion.kind.in_(kinds))
                       .order_by(AvailabilityAssertion.id)).scalars():
        row = obs.get(a.observation_id)
        if row is None:
            continue
        attrs = a.attrs if a.attrs is not None else {}
        if not isinstance(attrs, dict):
            raise ValueError(f"assertion {a.id}: attrs is not an object ({type(attrs).__name__}), not as the feed "
                             "writes it")
        row["asserted"].append({"kind": a.kind, "pid": a.source_player_id, "name": a.player_name,
                                "side": attrs.get("side"), "toi_unread": attrs.get("toi_unread") or 0})
    s.rollback()
    return {"games": dict(games), "unparsed": unparsed}


def _series_trouble(rows: list[dict]) -> str | None:
    """Why the game cannot be read as one series, or None."""
    seen = Counter(r["label"] for r in rows)
    twice = sorted(label for label, n in seen.items() if n > 1)
    if twice:
        return f"a label written more than once ({', '.join(twice)})"
    starts = sorted(r["kickoff"] for r in rows if r["kickoff"] is not None)
    if starts and starts[-1] - starts[0] >= nl.SERIES_SCOPE:
        return f"stored kickoffs {nl.SERIES_SCOPE} or more apart ({starts[0].isoformat()} .. {starts[-1].isoformat()})"
    return None


def _projection(row: dict | None, side: str) -> tuple[str | None, str]:
    if row is None:
        return None, "no row"
    if row["status"] in ("missed", "failed"):
        return None, f"{row['status']} poll"
    if row["status"] == "empty":
        return None, "empty landing"
    if row["status"] == "partial":
        return None, "partial poll"
    mine = [a for a in row["asserted"] if a["kind"] == "projected_starter" and a["side"] == side]
    if not mine:
        return None, "side not asserted"
    if len(mine) > 1:
        return None, "two projections"
    return mine[0]["pid"], READ


def _eventual(row: dict | None, side: str) -> tuple[str | None, str | None, str]:
    if row is None:
        return None, None, "no T+20 row"
    if row["status"] in ("missed", "failed", "empty", "partial"):
        return None, None, f"T+20 {row['status']}"
    mine = [a for a in row["asserted"] if a["kind"] == "eventual_starter" and a["side"] == side]
    if not mine:
        return None, None, "no goalie above zero toi read for the side"
    if len(mine) > 1:
        return None, None, "two in net"
    if mine[0]["toi_unread"]:
        return None, None, "toi unread"
    return mine[0]["pid"], mine[0]["name"], READ


def _share(a: int, n: int) -> str:
    return f"{a / n:.4f}" if n else "n/a"


def compute(data: dict) -> dict:
    per_label = {label: {"n": 0, "agree": 0} for label in PREGAME}
    by_day: dict = defaultdict(lambda: {label: {"n": 0, "agree": 0} for label in PREGAME})
    left: dict = {label: Counter() for label in PREGAME}
    status: dict = {label: Counter() for label in PREGAME + (EVENTUAL,)}
    late: Counter = Counter()
    stable: Counter = Counter()
    stable_split: dict = defaultdict(Counter)
    gapped: Counter = Counter()
    gapped_split: dict = defaultdict(Counter)
    no_projection = 0
    no_t0 = 0
    off_label = []
    series_out = []
    sides = []
    games_read = 0
    def first_kickoff(rows):
        ks = [r["kickoff"] for r in rows if r["kickoff"] is not None]
        return min(ks) if ks else None

    def order_key(kv):
        k = first_kickoff(kv[1]["rows"])
        return (k is None, k or datetime.min, kv[0])

    order = sorted(data["games"].items(), key=order_key)
    for gid, g in order:
        rows = g["rows"]
        why = _series_trouble(rows)
        if why:
            series_out.append({"game": gid, "why": why})
            continue
        games_read += 1
        at = {r["label"]: r for r in rows}
        off_label += [r["id"] for r in rows if r["label"] not in PREGAME + (EVENTUAL,)]
        for label in PREGAME + (EVENTUAL,):
            r = at.get(label)
            status[label][r["status"] if r else "no row"] += 1
            if r is not None and r["late"] and r["status"] in ("complete", "partial", "empty", "failed"):
                late[label] += 1
        # the game's start as the watch last knew it: the kickoff of its newest observation that carries one (the
        # series check above holds every stored kickoff of the game within SERIES_SCOPE)
        kick = next((r["kickoff"] for r in sorted(rows, key=lambda r: r["id"], reverse=True)
                     if r["kickoff"] is not None), None)
        day = nl.nhl_day(kick).isoformat() if kick is not None else "no kickoff"
        for side in SIDES:
            by_day[day]                                   # every read day is shown, 0/0 where no side reached n
            ev, ev_name, ev_why = _eventual(at.get(EVENTUAL), side)
            line = {"game": gid, "side": side, "day": day, "eventual": ev, "eventual_name": ev_name,
                    "eventual_why": ev_why, "labels": {}}
            proj = {}
            for label in PREGAME:
                pid, why = _projection(at.get(label), side)
                proj[label] = pid
                line["labels"][label] = pid if pid is not None else f"({why})"
                if pid is not None and ev is not None:
                    hit = int(pid == ev)
                    per_label[label]["n"] += 1
                    per_label[label]["agree"] += hit
                    by_day[day][label]["n"] += 1
                    by_day[day][label]["agree"] += hit
                else:
                    left[label][(f"projection: {why}", f"eventual: {ev_why}")] += 1
            # THE FIRST STABLE LABEL, observed: walking back from T-0 while every label names the T-0 playerId. The
            # walk stops at a label naming another (the change: the label after it is the first stable one), at T-120
            # (stable throughout), or at a label with no projection (a gap: the side named the same from the label
            # after the gap at the latest, but whether it changed across the gap is not observed, so it is counted
            # apart). A side with no T-0 projection has no observable run at all (counted apart too).
            last = proj[PREGAME[-1]]
            if all(proj[label] is None for label in PREGAME):
                no_projection += 1
                line["stable"] = "(no projection)"
            elif last is None:
                no_t0 += 1
                line["stable"] = "(no T-0 projection: not observed)"
            else:
                first, gap = PREGAME[-1], False
                for label in reversed(PREGAME[:-1]):
                    if proj[label] is None:
                        gap = True
                        break
                    if proj[label] != last:
                        break
                    first = label
                split = "eventual unread" if ev is None else ("agree" if last == ev else "differ")
                if gap:
                    gapped[first] += 1
                    gapped_split[first][split] += 1
                    line["stable"] = f"{first} at the latest (a label with no projection before it)"
                else:
                    stable[first] += 1
                    stable_split[first][split] += 1
                    line["stable"] = first
            sides.append(line)
    return {"per_label": per_label, "by_day": {d: by_day[d] for d in sorted(by_day)}, "left": left,
            "status": status, "late": late, "stable": stable, "stable_split": stable_split, "gapped": gapped,
            "gapped_split": gapped_split, "no_projection": no_projection, "no_t0": no_t0, "off_label": off_label,
            "series_out": series_out, "sides": sides, "games_read": games_read, "games_stored": len(data["games"]),
            "unparsed": data["unparsed"]}


def report(r: dict, db_text: str, echo=print) -> dict:
    echo(f"NHL LANDING AGREEMENT RECEIPT · {db_text} · source {nl.SOURCE} · addendum 370 item 1 · counts and shares "
         "only, no threshold, no verdict")
    echo(f"games stored {r['games_stored']} · read {r['games_read']} · left out whole (more than one series) "
         f"{len(r['series_out'])} · sides read {len(r['sides'])} · endpoints not read as a game "
         f"{len(r['unparsed'])}{' ' + str(r['unparsed']) if r['unparsed'] else ''} · observations at a label not "
         f"the feed's (in no count) {len(r['off_label'])}{' ' + str(r['off_label']) if r['off_label'] else ''}")
    for x in r["series_out"]:
        echo(f"  left out whole: game {x['game']}: {x['why']}")
    echo("")
    echo("PER SIDE (projection's source_player_id at each label, or why none; the eventual from T+20):")
    for x in r["sides"]:
        labels = " ".join(f"{label}={x['labels'][label]}" for label in PREGAME)
        ev = (f"{x['eventual']} ({x['eventual_name']})" if x["eventual"] is not None
              else f"({x['eventual_why']})")
        echo(f"  {x['day']} game {x['game']} {x['side']}: {labels} · eventual {ev} · first stable {x['stable']}")
    echo("")
    echo("AGREEMENT PER LABEL (n = sides with a projection at the label and an eventual; agree = the same "
         "source_player_id):")
    for label in PREGAME:
        c = r["per_label"][label]
        echo(f"  {label:>5}: agree {c['agree']} of {c['n']} · share {_share(c['agree'], c['n'])}")
    echo("")
    echo("BY NHL DAY (agree/n=share per label; every day with a side read, 0/0 where none reached n):")
    echo("  day        " + " ".join(f"{label:>13}" for label in PREGAME))
    for day, cells in r["by_day"].items():
        echo(f"  {day:<10} " + " ".join(
            f"{str(cells[label]['agree']) + '/' + str(cells[label]['n']) + '=' + _share(cells[label]['agree'], cells[label]['n']):>13}"
            for label in PREGAME))
    echo("")
    echo("SIDES LEFT OUT PER LABEL (each side once, by its two reasons):")
    for label in PREGAME:
        total = sum(r["left"][label].values())
        echo(f"  {label:>5}: {total}")
        for (p, e), n in sorted(r["left"][label].items(), key=lambda kv: (-kv[1], kv[0])):
            echo(f"         {n:>4} · {p} · {e}")
    echo("")
    echo("OBSERVATIONS PER LABEL BY STATUS (games read; `no row` = no observation of the game at the label), and the "
         "late among the answered:")
    for label in PREGAME + (EVENTUAL,):
        st = ", ".join(f"{k} {v}" for k, v in sorted(r["status"][label].items()))
        echo(f"  {label:>5}: {st} · late {r['late'][label]}")
    echo("")
    echo("FIRST STABLE LABEL, OBSERVED (walking back from T-0: the earliest label from which every label named the "
         "T-0 playerId, every one of them answered), split by whether that projection is the eventual:")
    for label in PREGAME:
        sp = r["stable_split"][label]
        echo(f"  {label:>5}: {r['stable'][label]} · agree {sp['agree']} · differ {sp['differ']} · eventual unread "
             f"{sp['eventual unread']}")
    echo("A GAP IN THE RUN (the same playerId from this label to T-0, a label with no projection before it: stable "
         "from this label at the latest, the earlier labels not observed):")
    for label in PREGAME:
        sp = r["gapped_split"][label]
        echo(f"  {label:>5}: {r['gapped'][label]} · agree {sp['agree']} · differ {sp['differ']} · eventual unread "
             f"{sp['eventual unread']}")
    echo(f"  sides with no T-0 projection (no run observed): {r['no_t0']} · sides with no projection at any label: "
         f"{r['no_projection']}")
    tail = {"games_stored": r["games_stored"], "games_read": r["games_read"], "sides": len(r["sides"]),
            "series_left_out": [x["game"] for x in r["series_out"]], "unparsed": r["unparsed"],
            "per_label": {label: [r["per_label"][label]["agree"], r["per_label"][label]["n"]] for label in PREGAME},
            "left_out": {label: sum(r["left"][label].values()) for label in PREGAME},
            "first_stable": {label: r["stable"][label] for label in PREGAME},
            "first_stable_gap": {label: r["gapped"][label] for label in PREGAME},
            "no_projection": r["no_projection"], "no_t0": r["no_t0"], "off_label": r["off_label"]}
    echo(f"{TAIL} {json.dumps(tail, sort_keys=True)}")
    return tail


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="addendum 370 item 1: how often and how early the NHL landing page names "
                                             "the eventual starter, read-only from a .backup copy")
    ap.add_argument("--db", default=None, help="a .backup copy of the database outside the repo's data/, opened "
                                               "mode=ro&immutable=1 (required)")
    a = ap.parse_args(argv)
    from src.walters import mlb_pitchers_gate as mp
    try:
        path = mp.check_db(a.db)
        for sc in SIDECARS:
            if path.with_name(path.name + sc).exists():
                raise mp.GateRefused(f"--db {a.db} has a {sc} sidecar ({path.name + sc}): not a fresh .backup copy; "
                                     "immutable=1 would ignore it and read a stale file; take a fresh .backup copy")
        mp.open_ro(path).close()
    except mp.GateRefused as err:
        text = str(err)
        print(f"REFUSED: {text}" + ("" if "nothing read" in text else "; nothing read"))
        return REFUSED
    import sqlite3

    from sqlalchemy.exc import SQLAlchemyError
    db_text = f"--db {path} (a .backup copy, opened {mp.COPY_URI_QUERY.lstrip('?')})"
    lines: list[str] = []
    try:
        with mp.readonly_session(path) as s:
            report(compute(collect(s)), db_text, echo=lines.append)
    except (SQLAlchemyError, sqlite3.Error, ValueError, LookupError, AttributeError, TypeError) as err:
        # a copy without the availability tables, or holding rows not as the feed writes them
        why = (str(err).strip().splitlines() or [""])[0]
        print(f"REFUSED: --db {path}: cannot be read as the availability record's schema, or holds a row not as the "
              f"feed writes it ({type(err).__name__}: {why}); nothing read")
        return REFUSED
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
