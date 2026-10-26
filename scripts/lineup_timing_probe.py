"""
LINEUP TIMING PROBE (ARCHITECT 2026-10-15 07:36 ET, addendum 71 item 2, Step A; roadmap lane cups, #106) — read-only.

Verbatim: "Step A (operator, Tuesday 2026-10-20, the CL matchday; receipt to me the same evening): a read-only timing
probe. Code writes scripts/lineup_timing_probe.py by Monday 2026-10-19: for the day's CL fixtures with a stored row,
poll the adapter's own lineup call (api_football.list_lineup_confirmed, the call sync-lineups uses) at T-120, T-90,
T-75, T-60, T-45, T-30 and T-15 minutes before kickoff, and print per fixture the first poll at which eleven starters
per side came back, the keys used, and the calls made. Nothing written. The block is mine; the operator keeps the
laptop awake 12:30pm to 3:00pm ET that day."

  D0  the database   opened mode=ro (a copy that refuses it: the plain path with PRAGMA query_only = ON, #421). The CL
                     competition's stored rows whose kickoff (matches.utc_date, UTC) falls on the day, each with its
                     id, kickoff, stored status, teams, and API-Football fixture id (matches.external_ids['api_football'],
                     APIFootballAdapter.source_name). Not polled, printed with the reason: a row with no fixture id, a
                     kickoff that cannot be read, or a stored status the matcher counts as not a game
                     (kalshi_match.NOT_GAMES: cancelled, postponed, stale_orphan).
  P   the polls      per fixture, at kickoff minus 120, 90, 75, 60, 45, 30 and 15 minutes, in time order:
                     APIFootballAdapter.list_lineup_confirmed(fixture id), the adapter's own call, pace and parse.
                     Each poll prints the starters and the bench per side; a side is a team id in the answer, named
                     home or away from the stored teams' ids. A poll's minute is the minute its answer was asked for
                     (the last HTTP request of the call: after the adapter's pace, and after its one retry of a 429).
                     A poll more than 5 minutes past its time, when its turn comes or when its answer is asked for
                     (the probe started late, the laptop slept, the pace or a 429 held it), is printed as missed and is
                     never counted under its label.
  Summary            per fixture: the first poll at which eleven starters per side came back, and the poll before it
                     that was answered without them (the lineup appeared between the two); the polls between them that
                     were not answered (missed or failed), where there are any, because the lineup may have been
                     readable at one of them; the polls answered, failed and missed. Then the fixtures counted by that
                     first poll, with a fixture whose earlier polls were not all answered counted apart. Then the calls
                     made (list_lineup_confirmed calls, HTTP requests by status, failures).

The keys: the ones the adapter reads (printed once), and, from each fixture's first answer that holds a team block,
every key that answer carries at those levels (the answer, its team blocks, a team, a startXI slot, a player).

"Eleven starters per side" is read as the adapter returns them: two team ids, each with exactly eleven starters. The
adapter drops a slot with no player name (a placeholder), so a side with a placeholder counts fewer than eleven.

It never stops on an error: a call that fails is printed and counted. It writes nothing: no row, no file.

STEP A EXTENDS (ARCHITECT 2026-10-15 12:00 ET, addendum 75 item 3(a)), verbatim in part: "The timing probe takes
--competition (CL default; UEL; EFL; the same polls), and runs on Thursday 2026-10-23 (the UEL matchday) and on the
next EFL round that has stored rows". Addendum 76 item 2: "choices CL|UEL|EL|EFL, and when the day holds no row
under the code asked, the "0 rows" line also says how many rows the other Europa League code holds that day (EL for UEL
and the reverse), so the operator re-runs with the right code; nothing is read as the other code silently." The UEL
run date is Thursday 2026-10-22: 2026-10-23 is a Friday, and UEL
matchday 3 is the Thursday (the roadmap step, #539, is dated 10-22; pass --date 2026-10-22, since --date defaults to
today in UTC). --competition names the stored competition code whose rows are polled (competitions.code); everything
else (the polls, the late rule, the summary) is the same for each.

ARCHITECT 2026-10-24 (addendum 163 item 4), verbatim: "NIT: scripts/lineup_timing_probe.py accepts --competition
CL|UEL|EL|EFL only; the PL probe for the record (Saturday PL kickoffs) needs PL in the choice list (and the stored
competition code it maps to). One line; next PL Saturday." PL is the stored code (competitions.code 'PL', the Premier
League; api_football league 39), read as every other choice is.

Run:  python3 scripts/lineup_timing_probe.py [--competition CL|UEL|EL|EFL|PL] [--db PATH] [--date YYYY-MM-DD] [--plan]
--competition is the stored code (default CL). --date is the day in UTC (default: today in UTC). --plan prints the
fixtures and their poll times and makes no call.
Start it before the first poll you want; it exits after its last poll (Ctrl-C prints the summary so far).
Paste the whole output to the architect.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

COMPETITIONS = ("CL", "UEL", "EL", "EFL", "PL")   # addendum 75 item 3(a), 76 item 2: CL default; UEL; EL; EFL; PL (163 item 4)
COMPETITION = COMPETITIONS[0]
# Addendum 76 item 2: the Europa League is stored under either code (api_football maps both to league 3); a day with no
# row under the code asked names how many the other holds, and is never read as it.
OTHER_EUROPA = {"UEL": "EL", "EL": "UEL"}
OFFSETS = (120, 90, 75, 60, 45, 30, 15)       # minutes before kickoff, the ruling's polls
LATE_LIMIT = timedelta(minutes=5)             # a poll later than this is missed, never counted under its label
ELEVEN = 11
NAP = 30.0                                    # the longest single sleep: the wall clock is read again after each
ADAPTER_KEYS = ("response[].team.id · response[].formation · response[].startXI[].player.{name, pos, number} · "
                "response[].substitutes[].player.{name, pos, number}")
# a poll's outcome
ELEVENS = "eleven per side"
SHORT = "answered without eleven per side"
FAILED = "failed"
MISSED = "missed"
CUT = "interrupted"


def db_path(arg: str | None) -> Path:
    if arg:
        return Path(arg)
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
        raise SystemExit(f"not a SQLite URL ({url.split(':')[0]}): the probe is SQLite-only")
    return Path(url.replace("sqlite:///", ""))


def open_read(p: Path):
    """(connection, form). mode=ro first; a copy that refuses it: the plain path with query_only set (#421). It opens
    the database no third way, and never creates one."""
    if not p.is_file():
        raise SystemExit(f"no database at {p}: the probe never creates one")
    try:
        con = sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True)
        con.execute("SELECT 1 FROM matches LIMIT 1")
        return con, "mode=ro URI"
    except sqlite3.OperationalError:
        con = sqlite3.connect(str(p), timeout=60)
        con.execute("PRAGMA query_only = ON")
        con.execute("SELECT 1 FROM matches LIMIT 1")
        return con, "plain path with PRAGMA query_only = ON (mode=ro refused)"


def source_name() -> str:
    from src.adapters.api_football import APIFootballAdapter
    return APIFootballAdapter.source_name


def _ext(v) -> dict:
    """A stored external_ids value as a dict; {} where it is not a JSON object (a malformed row has no ids)."""
    try:
        d = json.loads(v) if isinstance(v, str) else v
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def _kickoff(v) -> datetime | None:
    """matches.utc_date (naive UTC as stored) as an aware UTC datetime; None where it cannot be read."""
    try:
        k = datetime.fromisoformat(str(v))
    except ValueError:
        return None
    return k.replace(tzinfo=timezone.utc) if k.tzinfo is None else k.astimezone(timezone.utc)


def day_fixtures(con, day: date, src: str, competition: str = COMPETITION) -> list[dict]:
    """The competition's stored rows (competitions.code; CL by default) with a kickoff on the day (UTC), in kickoff
    order; each with why it is not polled, or None."""
    from src.ingestion.kalshi_match import NOT_GAMES
    from src.ingestion.team_merge import source_ids
    lo, hi = f"{day:%Y-%m-%d} 00:00:00", f"{day + timedelta(days=1):%Y-%m-%d} 00:00:00"
    rows = con.execute(
        "SELECT m.id, m.utc_date, m.status, m.external_ids, ht.name, ht.external_ids, at.name, at.external_ids "
        "FROM matches m JOIN competitions c ON c.id = m.competition_id "
        "LEFT JOIN teams ht ON ht.id = m.home_team_id LEFT JOIN teams at ON at.id = m.away_team_id "
        "WHERE c.code = ? AND m.utc_date >= ? AND m.utc_date < ? ORDER BY m.utc_date, m.id",
        (competition, lo, hi)).fetchall()
    out = []
    for mid, kick, status, ext, hname, hext, aname, aext in rows:
        fid = _ext(ext).get(src)
        f = {"id": mid, "kickoff": _kickoff(kick), "stored": kick, "status": status,
             "fid": str(fid) if fid not in (None, "") else None, "home": hname, "away": aname,
             "home_ids": source_ids(_ext(hext), src), "away_ids": source_ids(_ext(aext), src)}
        f["skip"] = ("no api_football fixture id" if not f["fid"] else
                     "the kickoff cannot be read" if not f["kickoff"] else
                     f"stored status {status}: not a game (kalshi_match.NOT_GAMES)"
                     if str(status or "").lower() in NOT_GAMES else None)
        out.append(f)
    return out


def day_count(con, day: date, competition: str) -> int:
    """How many stored rows of the competition code have a kickoff on the day (UTC); read only to name them."""
    lo, hi = f"{day:%Y-%m-%d} 00:00:00", f"{day + timedelta(days=1):%Y-%m-%d} 00:00:00"
    return con.execute(
        "SELECT COUNT(*) FROM matches m JOIN competitions c ON c.id = m.competition_id "
        "WHERE c.code = ? AND m.utc_date >= ? AND m.utc_date < ?", (competition, lo, hi)).fetchone()[0]


def plan(fixtures: list[dict]) -> list[tuple[datetime, int, int]]:
    """(poll time, fixture index, offset) for every poll, in time order (a tie in kickoff, then id, order)."""
    out = [(f["kickoff"] - timedelta(minutes=off), i, off)
           for i, f in enumerate(fixtures) if not f["skip"] for off in OFFSETS]
    return sorted(out, key=lambda x: (x[0], x[1]))


def sides(rows: list[dict], fx: dict) -> dict[str, dict]:
    """{team id: {side, starters, bench}} from the adapter's rows, in the answer's order."""
    out: dict[str, dict] = {}
    for r in rows:
        tid = str(r.get("team_source_id") or "")
        side = "home" if tid in fx["home_ids"] else "away" if tid in fx["away_ids"] else f"team {tid or '(no id)'}"
        s = out.setdefault(tid, {"side": side, "starters": 0, "bench": 0})
        s["starters" if r.get("is_starter") else "bench"] += 1
    return out


def eleven_per_side(sd: dict[str, dict]) -> bool:
    return len(sd) == 2 and all(s["starters"] == ELEVEN for s in sd.values())


def payload_keys(raw) -> dict[str, list[str]] | None:
    """Every key the answer carries at the levels the adapter reads; None where it holds no team block."""
    blocks = [b for b in (raw.get("response") or []) if isinstance(b, dict)] if isinstance(raw, dict) else []
    if not blocks:
        return None

    def union(objs):
        return sorted({k for o in objs if isinstance(o, dict) for k in o})
    slots = [s for b in blocks for s in (b.get("startXI") or []) if isinstance(s, dict)]
    return {"answer": union([raw]), "response[]": union(blocks), "response[].team": union(b.get("team") for b in blocks),
            "response[].startXI[]": union(slots), "response[].startXI[].player": union(s.get("player") for s in slots)}


def _clock() -> datetime:
    return datetime.now(timezone.utc)


class Provider:
    """The adapter's own call (list_lineup_confirmed), pace and parse; never raises an Exception. It counts each call
    and each HTTP request (the adapter asks once more after a 429) by status, notes when each request was sent, and
    keeps the answer's payload for its keys."""

    def __init__(self, adapter=None, clock=_clock):
        if adapter is None:
            from src.adapters.api_football import APIFootballAdapter
            adapter = APIFootballAdapter()
        self.adapter, self.clock = adapter, clock
        self.calls = self.failed = self.requests = 0
        self.statuses: Counter = Counter()
        self.raw = self.asked_at = None
        session_get, adapter_get = adapter._session.get, adapter._get

        def counted(*a, **kw):
            self.requests += 1
            self.asked_at = self.clock()
            try:
                r = session_get(*a, **kw)
            except BaseException:
                self.statuses["no answer"] += 1
                raise
            self.statuses[getattr(r, "status_code", None)] += 1
            return r

        def kept(path, params=None):
            data = adapter_get(path, params=params)
            self.raw = data
            return data
        adapter._session.get = counted
        adapter._get = kept

    def poll(self, fid: str):
        """(the adapter's rows or None, why it failed or None, the answer's payload or None, when the last HTTP
        request of the call was sent or None)."""
        self.calls += 1
        self.raw = self.asked_at = None
        try:
            rows = self.adapter.list_lineup_confirmed(fid)
        except Exception as e:  # noqa: BLE001 - printed and counted; the probe goes on
            self.failed += 1
            return None, f"{type(e).__name__}: {e}", self.raw, self.asked_at
        return rows, None, self.raw, self.asked_at


def _t(minutes: float) -> str:
    return f"T-{minutes:.1f}" if minutes >= 0 else f"T+{-minutes:.1f}"


def _offs(offs) -> str:
    return ", ".join(f"T-{o}" for o in offs)


def wait_until(when: datetime, clock, sleep) -> None:
    """Sleep until the wall clock reads `when`, in naps of at most NAP seconds (a laptop that slept is noticed)."""
    while True:
        left = (when - clock()).total_seconds()
        if left <= 0:
            return
        sleep(min(left, NAP))


def fixture_line(f: dict) -> str:
    head = f"match {f['id']} · {f['home'] or '?'} v {f['away'] or '?'} · kickoff "
    return head + (f"{f['kickoff']:%Y-%m-%d %H:%M}Z" if f["kickoff"] else f"UNREADABLE ({f['stored']!r})")


def verdict(polls: list[dict], cut: bool) -> tuple[str, str]:
    """(the fixture's summary text, its tally key) from its polls in time order."""
    first = next((i for i, p in enumerate(polls) if p["outcome"] == ELEVENS), None)
    answered = sum(p["outcome"] in (ELEVENS, SHORT) for p in polls)
    if first is None:
        if answered:
            text, key = f"no poll of the {answered} answered came back with eleven per side", "none"
        elif polls and any(p["outcome"] == FAILED for p in polls):
            text, key = "no poll answered", "no answer"
        else:
            text, key = "no poll made", "no poll made"
        if cut:
            text, key = text + " · cut off by the interrupt", "cut off by the interrupt"
        return text, key
    p = polls[first]
    prior = [q for q in polls[:first] if q["outcome"] == SHORT]
    lower = prior[-1] if prior else None
    gap = [q["off"] for q in polls[(polls.index(lower) + 1 if lower else 0):first]]  # neither answer bounds these
    text = f"first eleven per side at T-{p['off']} (asked at {_t(p['at'])})"
    if lower:
        text += f", the poll before answered without them at T-{lower['off']}"
    elif first == 0:
        text += ", the first poll"
    if gap:
        text += f" · {_offs(gap)} not answered between: it may have been readable earlier"
        return text, f"T-{p['off']}, earlier polls not answered"
    return text, f"T-{p['off']}"


def run(argv=None, clock=_clock, sleep=time.sleep, provider=None) -> int:
    ap = argparse.ArgumentParser(description="addendum 71 Step A (75 item 3): when a cup's lineups become readable, "
                                             "read-only")
    ap.add_argument("--competition", default=COMPETITION, choices=COMPETITIONS,
                    help="the stored competition code whose rows are polled (default CL)")
    ap.add_argument("--db", default=None)
    ap.add_argument("--date", default=None, help="the day in UTC, YYYY-MM-DD (default: today in UTC)")
    ap.add_argument("--plan", action="store_true", help="print the fixtures and the poll times; make no call")
    a = ap.parse_args(argv)
    start = clock()
    try:
        day = date.fromisoformat(a.date) if a.date else start.date()
    except ValueError:
        print(f"✗ --date {a.date!r} is not a real date (YYYY-MM-DD). Stop.")
        return 2
    print(f"LINEUP TIMING PROBE · {start:%Y-%m-%d %H:%M:%S}Z · day {day} (UTC) · competition {a.competition} · "
          "read-only, nothing written")
    print(f"  polls at {_offs(OFFSETS)} minutes · a poll more than {int(LATE_LIMIT.total_seconds() // 60)} minutes "
          "past its time is missed, never counted under its label")

    p = db_path(a.db)
    con, form = open_read(p)
    src = source_name()
    print(f"\nD0 database {p} · opened via {form}")
    print(f"  READ: matches (id, utc_date, status, external_ids['{src}']) of competitions.code = '{a.competition}', "
          "teams (name, external_ids) for the sides")
    fixtures = day_fixtures(con, day, src, a.competition)
    other = OTHER_EUROPA.get(a.competition)
    other_n = day_count(con, day, other) if other and not fixtures else None
    con.close()
    print(f"  {len(fixtures)} {a.competition} row(s) stored with a kickoff on {day}"
          + (f" · {other} holds {other_n} row(s) that day"
             + (f": the Europa League is stored under {other} here; re-run with --competition {other} (rows are never "
                "read as the other code)" if other_n else "") if other_n is not None else ""))
    for f in fixtures:
        print(f"  {fixture_line(f)} · stored status {f['status']} · fixture {f['fid'] or '-'}"
              + (f" · NOT POLLED: {f['skip']}" if f["skip"] else ""))
    polls = plan(fixtures)
    if not polls:
        print("\nNothing to poll: no stored row on the day to poll. No call made.")
        return 1

    if a.plan:
        print(f"\nPLAN ({len(polls)} polls; --plan: no call made)")
        for when, i, off in polls:
            past = " · already past" if start - when > LATE_LIMIT else ""
            print(f"  {when:%H:%M}Z T-{off} · match {fixtures[i]['id']}{past}")
        return 0

    if provider is None:
        try:
            provider = Provider(clock=clock)
        except ValueError as e:
            print(f"✗ {e} Stop.")
            return 1
    provider.clock = clock
    print("  provider: APIFootballAdapter.list_lineup_confirmed(fixture) → GET fixtures/lineups?fixture=<id> "
          "(the adapter's call, pace and parse)")
    print(f"  keys read (the adapter's): {ADAPTER_KEYS}")

    state = {i: {"polls": [], "keys": None} for i in range(len(fixtures))}
    print(f"\nP the polls ({len(polls)})")
    interrupted = None
    try:
        for when, i, off in polls:
            wait_until(when, clock, sleep)
            f, st = fixtures[i], state[i]
            now = clock()
            if now - when > LATE_LIMIT:
                st["polls"].append({"off": off, "outcome": MISSED})
                print(f"  {when:%H:%M}Z T-{off} · match {f['id']}: MISSED (its time passed "
                      f"{(now - when).total_seconds() / 60:.1f} min before its turn)")
                continue
            try:
                rows, err, raw, asked = provider.poll(f["fid"])
            except KeyboardInterrupt:
                st["polls"].append({"off": off, "outcome": CUT})
                print(f"  {when:%H:%M}Z T-{off} · match {f['id']}: INTERRUPTED during the call")
                raise
            asked = asked or now
            at = (f["kickoff"] - asked).total_seconds() / 60
            head = f"  {asked:%H:%M:%S}Z T-{off} (asked at {_t(at)}) · match {f['id']}"
            # a request sent past the limit is missed whatever came back, a failure included (Codex on #528)
            late = (f" · MISSED (asked {(asked - when).total_seconds() / 60:.1f} min past its time: not counted "
                    "under its label)") if asked - when > LATE_LIMIT else ""
            if err:
                st["polls"].append({"off": off, "outcome": MISSED} if late else {"off": off, "outcome": FAILED, "at": at})
                print(f"{head}: ✗ {err}{late}")
                continue
            if st["keys"] is None:
                st["keys"] = payload_keys(raw)
            sd = sides(rows, f)
            ok = eleven_per_side(sd)
            body = " · ".join(f"{s['side']} (team {tid or '-'}) {s['starters']} starters + {s['bench']} bench"
                              for tid, s in sd.items()) or "no lineup yet (an answer with no player)"
            if late:
                st["polls"].append({"off": off, "outcome": MISSED})
                print(f"{head}: {body}{late}")
                continue
            st["polls"].append({"off": off, "outcome": ELEVENS if ok else SHORT, "at": at})
            print(f"{head}: {body}" + (" · ELEVEN PER SIDE" if ok else ""))
    except KeyboardInterrupt:
        interrupted = clock()
        print(f"\nINTERRUPTED at {interrupted:%H:%M:%S}Z: the polls after it were not made")

    print("\nSUMMARY")
    tally: Counter = Counter()
    for i, f in enumerate(fixtures):
        if f["skip"]:
            print(f"  {fixture_line(f)}: not polled ({f['skip']})")
            tally["not polled"] += 1
            continue
        st = state[i]
        n = Counter(q["outcome"] for q in st["polls"])
        # cut off: a poll interrupted in its call (its last one included, Codex on #528), or polls never reached
        cut = n[CUT] > 0 or (bool(interrupted) and len(st["polls"]) < len(OFFSETS))
        text, key = verdict(st["polls"], cut)
        tally[key] += 1
        print(f"  {fixture_line(f)} · stored status {f['status']} · fixture {f['fid']}: {text} · polls answered "
              f"{n[ELEVENS] + n[SHORT]}, failed {n[FAILED]}, missed {n[MISSED]}"
              + (f", interrupted {n[CUT]}" if n[CUT] else ""))
        if st["keys"]:
            for level, keys in st["keys"].items():
                print(f"      keys sent, {level}: {', '.join(keys) or 'none'}")
        elif n[ELEVENS] + n[SHORT]:
            print("      keys sent: no answer held a team block")
    order = [f"T-{o}{s}" for o in OFFSETS for s in ("", ", earlier polls not answered")] + \
        ["none", "no answer", "no poll made", "cut off by the interrupt", "not polled"]
    print("  fixtures by the first poll with eleven per side: "
          + " · ".join(f"{k} {tally[k]}" for k in order if tally[k]) + f" (of {len(fixtures)})")
    print(f"  calls: list_lineup_confirmed {provider.calls} · HTTP requests {provider.requests} (by status "
          f"{dict(sorted(provider.statuses.items(), key=lambda kv: str(kv[0])))}) · failed {provider.failed}")
    if interrupted:
        print(f"  INTERRUPTED at {interrupted:%H:%M:%S}Z")
    return 0


def main(argv=None) -> int:
    return run(argv)


if __name__ == "__main__":
    sys.exit(main())
