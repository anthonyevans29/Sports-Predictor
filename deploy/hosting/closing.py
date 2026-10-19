#!/usr/bin/env python3
"""CLOSING RUNS FOR EVERY MODEL FAMILY, PAGED BY T-30 (ARCHITECT 2026-10-09, addendum 21 item 3, C1-C10, and
addendum 22: #380 rulings 380.1-380.5, the strict-mode rule, the schedule read, reading 7). Built on #370's MLB
closing autopilot (addendum 13 item 3, addendum 16 item 2), which it replaces.

    closing.py run   --family MLB|NFL|SOCCER [--start ISO] [--dry-run]   (= python cli.py closing-run)
    closing.py watch [--family F] [--dry-run]                          (= python cli.py closing-watch; every minute)
    closing.py preflight [--shell-set NAMES] [--family F]   the setup script's checks (380.2): the run's own refusals
    closing.py test-page [--family F]            one test page through the card topic (380.2, M2)
    closing.py install-push                      one exports-mirror push, label install (addendum 23 D1)

Addendum 45 (ARCHITECT 2026-10-12, #405 and #408, P1-P8; C7 stands, everything shipped and held): P1 the mirror
push's role is SP_EXPORTS_MIRROR_ROLE (host | laptop, no default; unset or neither refuses the run before any step);
P2 the host's watch runs for NFL and SOCCER by name and preflight takes the same families; P3 the host's own units
(deploy/hosting/systemd/sp-closing-watch.service + .timer, not enabled) and the watch's exit: 0 success, 2 a refusal,
3 (NOTIFIED) a failure or miss already receipted and notified, 1 what the process could not report itself; P5 the
laptop's setup script takes the families. Every closing page, failure notification and the test page end with a line
naming the machine by role.

C1 (families): MLB, NFL and SOCCER (PL) today: chains.CLOSING_FAMILIES. A shadow has no closing run and is never
paged as a pick.
C2 (timing): "The watch ticks every minute. A run starts when the earliest unstarted start time of a family is 35
minutes away, and it covers every game of that family starting within the 10 minutes after that time. The page is
out by T-30 on a clean run. A failed attempt is retried, at most three attempts for one start time, and no attempt
starts inside T-5. A run that finds the chain lock held starts when it is free." A run's summary and page hold its
own games only.
C3 (chains): MLB = chains.CHAINS["mlb-closing"] (#370's); NFL / SOCCER = nfl-closing / soccer-closing, derived from
freshen:NFL / freshen:SOCCER, opening with the schedule read and pricing the covered games only.
C4 (checks): every ruling of addendum 16 item 2 for every family (R1 started test, R2 prices, R3 lock, the refusals,
R6 moved export, M1 mirror push, the failed-run notification), plus 380.1 (MLB starters) and strict mode (injuries).
C5/C6 (the page): one page per run, on the phone through sp_notify's ntfy card topic (NTFY_CARD_TOPIC) and on the
laptop's screen (macOS). NTFY_CARD_TOPIC unset refuses the run. The topic's value is never printed.
Addendum 23 (ARCHITECT 2026-10-09, item 3): A1 the schedule read names the covered games (sync-matches --match-ids;
NFL by date in the SOCCER form since addendum 25 2(i)) and fails the run when it did not answer; A2 NFL's roster read under strict mode;
A5 the Kalshi legs the Desk read; B1 the page first, then the push (a failed push after the page is receipted and
notified, never rerun); B2 the phone page tried three times ten seconds apart, the screen recorded only; B3 a PLAY or
LADDER now PASS has its own line and makes the page high priority; B4 every line but the head and the PASS count
names its game; B5 the 2026-10-07 hold names MLB and NFL; B6 a miss once per start time and reason; B7 an NFL PLAY
beside unresolved injured positions says so; C a covered game whose start moved leaves the run ("start moved" when
none is left); D1 the setup script's install push (`install-push`).
380.3 backup, 380.4 decide under the lock (superseded / miss / attempt number / run start), reading 7 (a refusal is
receipted and notified once per start time and reason).
Addendum 25 (ARCHITECT 2026-10-09, item 2): (i) A1 amended, NFL's schedule read by date (chains.py); (ii) a covered
game the schedule read moved leaves the run as soon as the read has run (Codex 4232307577), and an order names its
Kalshi leg only by its own ticker (Codex 4232307584); (iii) THE LAST CALL (reading 7 amended, `last_calls`): "The
last call of a game is the call the operator was last shown for it: its call on the last closing page that covered
it or, when no page has covered it, its call in the newest export that no closing run wrote. An export a closing run
wrote never supplies the last call of a game that run did not page. C5's was and B3 read this."

Addendum 40 (ARCHITECT 2026-10-11, item 2, ONE CLOSING, ONE PAGE, ONE FILE): "For a game of a closing family the
close is its closing page. [...] A closing run whose page went out writes exports/closing_<FAMILY>_<start>.json: the
games on its page and no other, each row as the run's export gave it, and a closing block naming the family, the start
time, the run id and the match ids. A run whose page did not go out writes no such file. A closing run does not write,
replace or move the family's slate file." The export step writes logs/<run id>.<slate name> (--out {export_out}); the
receipt records both files and their sha256 (export_written, closing_file); the page's time is page.at. last_calls
reads slate files (export_glob) and receipts, as before: a closing file is never read as a slate file.
Addendum 41 item 3 (THE FILE OF A SECOND PAGE): a start time paged a second time: the later page is its close, its
file replaces the earlier one, the earlier is kept as logs/<its run id>.<name>, and the later receipt names it
(closing_file.replaced: file, sha256, run_id, kept_as). An earlier file that cannot be moved: the write is refused
(closing_file_failed) and the earlier stands.

Refusals (receipted, exit 2), in order: R5 a backup folder under data/ (before anything else); SP_SKIP_FAMILIES
naming the family (MLB: laptop only); M1 SP_EXPORTS_MIRROR_REMOTE unset; P1 SP_EXPORTS_MIRROR_ROLE unset or neither
host nor laptop; C6 NTFY_CARD_TOPIC unset; R4 a malformed --start; nothing to close (A4); under the lock, before any
step, an export path that already exists (#442: nothing a run kept is opened for writing a second time).

Receipts: kind "closing" (one line per run, success, failure, refusal or superseded) and kind "closing_miss" (the MLB
feed unreachable; the lock held into T-5; a due start time first seen inside T-5), once per start time and reason. The autopilot places nothing and
never opens Kalshi's trading API. --dry-run touches nothing: no step, no backup, no receipt, no push, no page, no
network.

THE SLATE RUN (ARCHITECT 2026-10-18, addendum 126 item 2(a), #590; the section "slate" below): after its closings, each
tick runs a SLATE stage per family for the tick's ET day: due at the day's first kickoff minus 150 minutes, or at the
first tick after 06:00 ET when that is later; one run per family per day (a success, or three attempts), decided from
its own receipts (kind "slate"; misses kind "slate_miss"), which no closing reader reads. It runs the closing chain's
steps as resolve_steps resolves them for the day's games, its export kept under logs/ as a closing's is and linked into
the family's slate file in exports/ once its checks pass (addendum 133 item 3(a): a failure at a step, a check or
the link leaves nothing in exports/; a push or a page that fails comes after the link, and the file stands), then
the mirror push, then one page: "SLATE <FAMILY> <YYYY-MM-DD>: <N> row(s) · PLAY <p> · PASS <q> · exports/<file>". A
failure pages "SLATE <FAMILY> FAILED: <step command> — RUN BY HAND: block_<MMDD>_<family>_slate.txt · attempt k/3".
The closings, their groups, steps and files are unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_common as c  # noqa: E402
_WALL = time.time            # file mtimes are compared with the wall clock, whatever clock the run reads
import sp_run  # noqa: E402
from chains import CHAINS, CLOSING_FAMILIES  # noqa: E402

NY = ZoneInfo("America/New_York")
# C1: the families with a closing run. comps = the competition codes whose games it covers; export_glob = the files
# its export step writes (the "last file" a call is compared with, C5); noun = what the start time is called.
FAMILIES = {
    "MLB": {"chain": CLOSING_FAMILIES["MLB"], "comps": ("MLB",), "export_glob": "mlb_MLB_*.json",
            "noun": "first pitch", "feed": True, "starters": True},
    "NFL": {"chain": CLOSING_FAMILIES["NFL"], "comps": ("NFL",), "export_glob": "nfl_predictions_*.json",
            "noun": "kickoff", "feed": False, "starters": False},
    "SOCCER": {"chain": CLOSING_FAMILIES["SOCCER"], "comps": ("PL",), "export_glob": "soccer_PL_*.json",
               "noun": "kickoff", "feed": False, "starters": False},
}
RUN_LEAD_MIN = 35            # C2: a run starts when the earliest unstarted start time is 35 minutes away
COVER_MIN = 10               # C2: it covers every game starting within the 10 minutes after that time
PAGE_BY_MIN = 30             # C2: the page is out by T-30 on a clean run
NO_ATTEMPT_INSIDE_MIN = 5    # C2: no attempt starts inside T-5
MAX_ATTEMPTS = 3             # C2 / A6: at most three attempts for one start time
MANUAL_WINDOW_MIN = 90       # #370, accepted as built: a manual run targets the next unstarted start within 90 min
PAGE_MAX_CHARS = 100         # C5: no line over 100 characters
MIRROR_TIMEOUT_S = 90
# A6 (MLB only): "the MLB feed" is the statsapi base the MLB adapter uses (a test pins the two together).
FEED_BASE = "https://statsapi.mlb.com/api/v1"
FEED_PROBE = FEED_BASE + "/sports/1"
FEED_TIMEOUT_S = 8
FEED_MISS_TEXT = "MLB feed unreachable: VPN on, Tailscale off"
# A7: THE OPERATOR HOLD OF 2026-10-07. One row per hold; lifting a hold is deleting its row (a one-line PR). C8:
# nothing in the Desk moves. B5 (ARCHITECT 2026-10-09, addendum 23, reading 8 RULED): "The hold of 2026-10-07 is the
# operator's, and it names MLB and NFL. It is not extended to PL here: its row gains its families and nothing else
# about it changes."
# THE HOLD OF 2026-10-11 (ARCHITECT, addendum 40 item 4; NFL only): "an NFL PLAY that is QB-flagged, or sized by this
# rule, says on its page line "QB: paste to the architect before placing". [...] The Desk's call and the file do not
# change. The hold stands until the model has a quarterback term that has passed its gate" (#427). Read from the
# Desk's own tags: "QB-flagged half units" (v1.1's QB rule) or "QB unread half units" (the empty-list rule).
CLOSING_HOLDS = (
    {"call": "PLAY", "exec_edge_under_pp": 4.0, "text": "paste to the architect before placing", "since": "2026-10-07",
     "families": ("MLB", "NFL")},
    {"call": "PLAY", "tags_any": ("QB-flagged half units", "QB unread half units"),
     "text": "QB: paste to the architect before placing", "since": "2026-10-11", "families": ("NFL",)},
)
VOID = ("CANCELLED", "POSTPONED", "STALE_ORPHAN")      # never a game in any window
STARTED_STATUSES = ("LIVE", "FINISHED")
MIRROR_SETTING = "SP_EXPORTS_MIRROR_REMOTE"            # M1
ROLE_SETTING = "SP_EXPORTS_MIRROR_ROLE"                # addendum 45 P1: the machine's role, no default
ROLES = ("host", "laptop")
CARD_TOPIC = "NTFY_CARD_TOPIC"                         # C6
REQUIRED_SETTINGS = (MIRROR_SETTING, ROLE_SETTING, CARD_TOPIC)   # 380.2: read where the launched job finds them
NOTIFIED = 3                 # addendum 45 P3: the watch's exit for what it already receipted and notified
STAKED_CALLS = ("PLAY", "LADDER")                      # a call that stakes units (LADDER: soccer's double chance)
# R6 (+ 380.1): the failures of the run's own checks. Their export never sits in exports/: since addendum 40 item 2
# the export step writes it under logs/, named with the run id, so no call is left behind (a receipt older than that
# names an export R6 moved there).
# C (addendum 23): a run left with no game by the schedule read is "start moved".
OWN_CHECK_FAILURES = ("stale prices", "stale starters", "missing from export", "target started", "start moved")
# B2 (ARCHITECT 2026-10-09, addendum 23): "The phone page is the page. It is tried three times, ten seconds apart,
# before the run fails as 'page'. A screen notification that is not posted is recorded and changes nothing."
PAGE_TRIES = 3
PAGE_RETRY_S = 10
TEST_PAGE_TITLE = "Closing watch"
TEST_PAGE_BODY = "Test: the closing watch is installed ({families}). Pages arrive here by T-30."


# ------------------------------------------------------------------------------------------------- time --

def utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


_OFFSET = re.compile(r"[+-]\d{2}(:?\d{2}(:?\d{2}(\.\d+)?)?)?$")


def parse_utc(s: str) -> datetime:
    """A stored utc_date ('2026-10-08 23:05:00.000000', naive = UTC) or an ISO string ('...T23:05:00Z', or any
    explicit offset such as '...T13:00:00-04:00', converted to UTC) as aware UTC. Codex on #385: a '-hh:mm' offset
    was truncated and the local time read as UTC."""
    s = str(s).strip().replace("Z", "+00:00")
    d = datetime.fromisoformat(s if _OFFSET.search(s[10:]) else s[:19])
    return utc(d).astimezone(timezone.utc)


def iso_z(dt: datetime) -> str:
    return utc(dt).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ny_date(dt: datetime) -> date:
    """A1: the first pitch's date in America/New_York (the feed's own date), never the UTC date."""
    return utc(dt).astimezone(NY).date()


def et(dt: datetime) -> str:
    return utc(dt).astimezone(NY).strftime("%Y-%m-%d %H:%M ET")


def clock() -> datetime:
    return c.utc_now()


# --------------------------------------------------------------------------------------------- schedule --

SCHEDULE_HOURS = 6           # schedule()'s window: the stored games within 6 hours either side of `now`


def schedule_window(now: datetime, hours: int = SCHEDULE_HOURS) -> tuple[datetime, datetime]:
    """[lo, hi): the window schedule() reads (#390 item 7: unpaged_called_off is bounded to it too)."""
    return utc(now) - timedelta(hours=hours), utc(now) + timedelta(hours=hours)


def schedule(fam: str, now: datetime, hours: int = SCHEDULE_HOURS) -> list[dict]:
    """The family's stored schedule around `now`, read-only (mode=ro). No network. Status is the stored enum name."""
    lo, hi = schedule_window(now, hours)
    return _stored_games(fam, lo, hi)


def day_bounds(day: date) -> tuple[datetime, datetime]:
    """[lo, hi) in UTC: midnight to midnight in America/New_York (23 or 25 hours on a clock change)."""
    nxt = day + timedelta(days=1)
    return (datetime(day.year, day.month, day.day, tzinfo=NY).astimezone(timezone.utc),
            datetime(nxt.year, nxt.month, nxt.day, tzinfo=NY).astimezone(timezone.utc))


def day_games(fam: str, day: date) -> list[dict]:
    """The family's stored games of one US Eastern day (ny_date, as A1 dates a first pitch), schedule()'s shape,
    read-only. VOID statuses are no game."""
    lo, hi = day_bounds(day)
    return [g for g in _stored_games(fam, lo, hi) if ny_date(g["start"]) == day]


def _stored_games(fam: str, lo: datetime, hi: datetime) -> list[dict]:
    """The family's stored games starting in [lo, hi), read-only (mode=ro), VOID ones dropped."""
    fmt = "%Y-%m-%d %H:%M:%S"
    comps = FAMILIES[fam]["comps"]
    con = c.ro_connect(c.db_path())
    try:
        rows = con.execute(
            "SELECT m.id, m.utc_date, m.status, ht.name, at.name, m.home_team_id, m.away_team_id FROM matches m "
            "JOIN competitions co ON co.id = m.competition_id "
            "LEFT JOIN teams ht ON ht.id = m.home_team_id LEFT JOIN teams at ON at.id = m.away_team_id "
            f"WHERE co.code IN ({','.join('?' * len(comps))}) AND m.utc_date >= ? AND m.utc_date < ? "
            "ORDER BY m.utc_date, m.id",
            (*comps, lo.strftime(fmt), hi.strftime(fmt))).fetchall()
    finally:
        con.close()
    return [{"match_id": i, "start": parse_utc(d), "status": str(s or "").upper(), "home": h, "away": a,
             "home_team_id": hid, "away_team_id": aid}
            for i, d, s, h, a, hid, aid in rows if str(s or "").upper() not in VOID]


def started(g: dict, now: datetime) -> bool:
    return g["status"] in STARTED_STATUSES or g["start"] <= utc(now)


def minutes_to(start: datetime, now: datetime) -> float:
    return (utc(start) - utc(now)).total_seconds() / 60


def cover(games: list[dict], start: datetime, now: datetime) -> list[dict]:
    """C2: the games a run for `start` covers: every game of the family starting within the 10 minutes after that
    time (start <= game <= start + 10), not started at `now`."""
    s = utc(start)
    return [g for g in games if s <= g["start"] <= s + timedelta(minutes=COVER_MIN) and not started(g, now)]


def groups(games: list[dict], now: datetime, covered: set) -> list[dict]:
    """C2, the watch's start times: the unstarted games no closing has finished with (`covered`: a success, or three
    attempts), earliest first. The earliest is a start time; it covers the games within the 10 minutes after it; the
    next start time is the first game after those 10 minutes; and so on."""
    cands = sorted((g for g in games if not started(g, now) and g["match_id"] not in covered),
                   key=lambda g: (g["start"], g["match_id"]))
    out, i = [], 0
    while i < len(cands):
        s = cands[i]["start"]
        hi = s + timedelta(minutes=COVER_MIN)
        grp = [g for g in cands if s <= g["start"] <= hi]
        out.append({"start": s, "games": grp})
        while i < len(cands) and cands[i]["start"] <= hi:
            i += 1
    return out


# --------------------------------------------------------------------------------------------- receipts --

def receipts(kinds: tuple[str, ...]) -> list[dict]:
    p = c.receipts_path()
    out = []
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("kind") in kinds:
                    out.append(r)
    except FileNotFoundError:
        pass
    return out


def _attempts(fam: str, start: str | None = None) -> list[dict]:
    """The run attempts: refusals and superseded runs are neither (380.4)."""
    return [r for r in receipts(("closing",)) if r.get("family") == fam
            and (start is None or r.get("start") == start) and not r.get("refused") and not r.get("superseded")]


def closing_state(fam: str, start: str) -> dict:
    """For one start time of a family: a successful closing? how many attempts? how many misses?"""
    runs = _attempts(fam, start)
    misses = [r for r in receipts(("closing_miss",)) if r.get("family") == fam and r.get("start") == start]
    return {"success": any(r.get("exit") == 0 for r in runs), "attempts": len(runs), "misses": len(misses)}


def stored_starts(ids) -> dict:
    """{match_id: its stored start (aware UTC)}, read-only by match id, any window, any status. A game no longer
    stored is absent."""
    ids = sorted({i for i in ids if i is not None})
    if not ids:
        return {}
    con = c.ro_connect(c.db_path())
    try:
        rows = con.execute(f"SELECT id, utc_date FROM matches WHERE id IN ({','.join('?' * len(ids))})",
                           ids).fetchall()
    finally:
        con.close()
    out = {}
    for i, d in rows:
        try:
            out[i] = parse_utc(d)
        except (TypeError, ValueError):
            continue                  # law 4: an unreadable start is no start a receipt covered
    return out


def covered_ids(fam: str) -> set:
    """The games a closing has finished with. Codex 4232719331 (ARCHITECT 2026-10-09, addendum 26 item 2(a)): "A game
    is finished with at a start time when a successful attempt for that start time covered it, or when the start time
    has had three attempts and the last of them covered it. An earlier attempt's covers count for nothing on their
    own." C (addendum 23): a game that left a run because its start moved is a new start time for the watch, never
    finished with at the old one (a run's `covers` are the games left in it; `moved` names the ones that left).
    #390 item 6 (ARCHITECT 2026-10-09, addendum 28 item 2, RULED): "A game is finished with at the start time it was
    covered at, and at no other. When its stored start is no longer the start a receipt covered it at, that receipt
    says nothing about it: it is a new start time for the watch, whether the receipt was a success or the last of
    three attempts. A game paged as cancelled or postponed and later stored as scheduled at another start is such a
    game." So a finishing receipt finishes a game at the start its cover recorded (`covers[].start`), and the game is
    returned only while its stored start (re-read by match id) is still that start. A cover with no readable start,
    or a game no longer stored, is finished with nowhere (law 4)."""
    by_start: dict = {}
    for r in _attempts(fam):
        by_start.setdefault(r.get("start"), []).append(r)

    def left_in(r: dict) -> set:
        gone = {x.get("match_id") for x in r.get("moved") or []}
        out_ = set()
        for x in r.get("covers") or []:
            if x.get("match_id") in gone:
                continue
            try:
                out_.add((x.get("match_id"), parse_utc(x["start"])))
            except (KeyError, TypeError, ValueError):
                continue
        return out_
    done = set()
    for rs in by_start.values():
        for r in rs:                  # a successful attempt's covers
            if r.get("exit") == 0:
                done |= left_in(r)
        if len(rs) >= MAX_ATTEMPTS:   # three attempts: the last one's covers, and only its
            done |= left_in(rs[-1])
    now_at = stored_starts(mid for mid, _ in done)
    return {mid for mid, at in done if mid in now_at and now_at[mid] == at}


def unpaged_called_off(fam: str, now: datetime, hours: int = SCHEDULE_HOURS) -> list[dict]:
    """Codex 4233123800 (#392): a covered game an attempt found cancelled or postponed (`called_off`) leaves
    schedule(), which drops every VOID status, so the watch would never page its line if that attempt failed. It stays
    a game of its start time, in the schedule's shape at the start it was covered at, until that start time has a
    successful attempt (whose page carried its line) or three attempts. #390 item 7 (addendum 28 item 2): bounded to
    the window schedule() reads at `now` (covered_start in [now - hours, now + hours)), so a start time that ended
    with one or two failed attempts is not added to the watch's games for good."""
    lo, hi = schedule_window(now, hours)
    by_start: dict = {}
    for r in _attempts(fam):
        by_start.setdefault(r.get("start"), []).append(r)
    out: dict = {}
    for rs in by_start.values():
        if any(r.get("exit") == 0 for r in rs) or len(rs) >= MAX_ATTEMPTS:
            continue
        for r in rs:
            for x in r.get("called_off") or []:
                try:
                    st = parse_utc(x["covered_start"])
                    if not (lo <= st < hi):
                        continue
                    out.setdefault(x["match_id"], {
                        "match_id": x["match_id"], "start": st,
                        "status": str(x.get("status") or "").upper(), "home": x.get("home"), "away": x.get("away"),
                        "home_team_id": None, "away_team_id": None})
                except (KeyError, TypeError, ValueError):
                    continue
    return list(out.values())


def with_called_off(fam: str, games: list[dict], now: datetime) -> list[dict]:
    """The stored schedule at `now` plus the unpaged called-off games of the family in the same window (not already
    in it): what the watch, the plan and the run's covers read. The run's own checks (missing from export, started)
    keep reading schedule()."""
    have = {g["match_id"] for g in games}
    extra = [g for g in unpaged_called_off(fam, now) if g["match_id"] not in have]
    return sorted(games + extra, key=lambda g: (g["start"], g["match_id"])) if extra else games


# --------------------------------------------------------------------------------------- side effects --
# Each is a module-level function so tests replace it; none is reached by --dry-run.

def feed_answers() -> tuple[bool, str]:
    """A6 (MLB): one GET to the MLB feed. Answers = HTTP 200."""
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(urllib.request.Request(FEED_PROBE, headers={"User-Agent": "sp-closing-watch"}),
                                    timeout=FEED_TIMEOUT_S) as r:
            return r.status == 200, f"HTTP {r.status}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001 - any failure to answer is "unreachable"
        return False, f"{type(e).__name__}: {e}"[:200]


def _osa(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def notify(body: str, title: str = "Closing") -> dict:
    """The laptop's screen: a macOS notification via osascript. Off macOS nothing is posted and the line says so."""
    if sys.platform != "darwin":
        print(f"· notification (not macOS, not posted): {title}: {body}", flush=True)
        return {"posted": False, "text": body, "skipped": "not macOS"}
    try:
        r = subprocess.run(["osascript", "-e", f'display notification "{_osa(body)}" with title "{_osa(title)}"'],
                           capture_output=True, text=True, timeout=15)
        return {"posted": r.returncode == 0, "text": body,
                **({} if r.returncode == 0 else {"error": f"osascript exit {r.returncode}"})}
    except (OSError, subprocess.SubprocessError) as e:
        return {"posted": False, "text": body, "error": f"{type(e).__name__}"}


def page_phone(title: str, body: str, priority: str = "default") -> dict:
    """C5/C6: the operator's phone through sp_notify's ntfy CARD topic (NTFY_CARD_TOPIC). Accepted = HTTP 2xx. The
    topic (the URL) is never printed and never recorded: only the status or the exception's type."""
    import urllib.error
    import urllib.request
    import sp_notify
    url = sp_notify.ntfy_url(CARD_TOPIC)
    if not url:
        return {"accepted": False, "error": f"{CARD_TOPIC} unset or invalid"}
    try:
        req = urllib.request.Request(url, data=body.encode("utf-8"), method="POST",
                                     headers={"Title": title[:200], "Priority": priority})
        with urllib.request.urlopen(req, timeout=20) as r:
            return {"accepted": 200 <= r.status < 300, "http": r.status}
    except urllib.error.HTTPError as e:
        return {"accepted": False, "http": e.code}
    except Exception as e:  # noqa: BLE001 - never the URL, never the message (it can carry the host/topic)
        return {"accepted": False, "error": type(e).__name__}


def page_operator(title: str, body: str) -> dict:
    """Addendum 47 item 7(a): the operator topic (sp_notify's NTFY_TOPIC, the unit failure pages' channel), for a
    notice neither the screen nor the card topic took. Accepted = HTTP 2xx; the topic is never printed or
    recorded."""
    import urllib.error
    import urllib.request
    import sp_notify
    url = sp_notify.ntfy_url("NTFY_TOPIC")
    if not url:
        return {"accepted": False, "error": "NTFY_TOPIC unset or invalid"}
    try:
        req = urllib.request.Request(url, data=body.encode("utf-8")[:4000], method="POST",
                                     headers={"Title": title[:200], "Priority": "high"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return {"accepted": 200 <= r.status < 300, "http": r.status}
    except urllib.error.HTTPError as e:
        return {"accepted": False, "http": e.code}
    except Exception as e:  # noqa: BLE001 - never the URL, never the message
        return {"accepted": False, "error": type(e).__name__}


def page_sleep(seconds: float) -> None:
    """B2: the wait between phone page tries (tests replace it)."""
    time.sleep(seconds)


def mirror_role() -> str | None:
    """Addendum 45 P1 (ARCHITECT 2026-10-12): "The role is a setting on both machines. push_mirror and install-push
    take it from SP_EXPORTS_MIRROR_ROLE, as the chains' hook does. Unset, or neither host nor laptop: the run is
    refused before any step, as M1 is, and preflight says so. There is no default." None when it is not one of
    ROLES."""
    role = (c.setting(ROLE_SETTING) or "").strip()
    return role if role in ROLES else None


def machine_line() -> str:
    """Addendum 45: "Every closing page ends with one line naming the machine by role (host/laptop). Test page
    too." """
    role = mirror_role()
    return f"machine: {role}" if role else f"machine: role unknown ({ROLE_SETTING} unset or invalid)"


def push_mirror(label: str = "closing") -> dict:
    """M1: the exports mirror pushed with this machine's role (P1, SP_EXPORTS_MIRROR_ROLE), label closing
    (docs/specs/exports-mirror.md). D1 (addendum 23): the setup script's one push at install uses label install.
    No role: nothing is pushed (the run refused before any step; install-push refuses)."""
    role = mirror_role()
    if not role:
        return {"exit": None, "tail": [_role_refusal() or "no role"]}
    argv = [sys.executable, str(Path(__file__).resolve().parent / "exports_mirror.py"), "push",
            "--role", role, "--label", label]
    try:
        r = subprocess.run(argv, cwd=c.REPO, capture_output=True, text=True, timeout=MIRROR_TIMEOUT_S)
        tail = [c.redact(x) for x in ((r.stdout or "") + (r.stderr or "")).strip().splitlines()[-2:]]
        return {"exit": r.returncode, "tail": tail}
    except subprocess.TimeoutExpired:
        return {"exit": None, "tail": [f"timed out after {MIRROR_TIMEOUT_S}s"]}
    except OSError as e:
        return {"exit": None, "tail": [f"{type(e).__name__}: {e}"]}


def run_step(argv: list[str], run_id: str) -> tuple[int, list[str], float]:
    """(exit, the last console lines, seconds): sp_run's own step runner (`python cli.py <argv>` in the checkout)."""
    return sp_run.run_step(argv, run_id)


def acquire_lock(timeout_s: float | None):
    """R3 / C2 / 380.4: the chain lock. A run that finds it held waits until it is free (a watch-started run, until
    T-5 at the latest: TimeoutError then)."""
    return c.db_lock() if timeout_s is None else c.db_lock(timeout_s=timeout_s)


# A step that REPORTS a failure on its console but exits 0 (Codex on #370). R2: "The sync-kalshi marker table stays
# as built." Read from cli.py (law 1):
#   sync-kalshi  "✗ Kalshi sync failed: <exception>"  /  "Kalshi sync: <reason>"
STEP_FAILURE_MARKERS = {
    "sync-kalshi": ("✗ Kalshi sync failed:", "Kalshi sync: "),
}


EMPTY_ANSWER_MARK = "EMPTY-ANSWER"          # cli.py _print_empty_answers (a test pins the two together)


def empty_answers(argv: list[str], tail: list[str]) -> list[str]:
    """Addendum 40 item 4: the teams a sync-injuries step named as answering empty (its EMPTY-ANSWER line)."""
    if not argv or argv[0] != "sync-injuries":
        return []
    out: list[str] = []
    for ln in tail:
        if ln.startswith(EMPTY_ANSWER_MARK) and "): " in ln:
            out += [t.strip() for t in ln.split("(read as unread): ", 1)[-1].split(";")
                    if t.strip() and t.strip() not in out]
    return out


NO_BOOK_ODDS_MARK = "NO-BOOK-ODDS"          # cli.py _print_no_book_odds (a test pins the two together)
# ARCHITECT 2026-10-16, addendum 97 item 2(a): a covered MLB game whose row shows no book and whose run's sync step
# named no answer for it. Not a guess at the provider's answer (law 4).
BOOKS_NO_ANSWER = "the sync step named no answer for the game"
RUN_KEY = "run"                              # no_book_odds: the run-level answer, for every row with no game's own


def no_book_odds(argv: list[str], tail: list[str]) -> dict:
    """Addendum 97 item 2(a) (#550/#514): {match id: the provider's answer} from an MLB sync-odds step's NO-BOOK-ODDS
    line, the step's own answer for each game it left with no book odds ("provider listed the game, no odds", ...).
    The run-level answer (the fallback never ran: "run [<answer>]") is kept under RUN_KEY."""
    if not argv or argv[0] != "sync-odds":
        return {}
    out: dict = {}
    for ln in tail:
        if ln.startswith(NO_BOOK_ODDS_MARK):
            for mid, why in re.findall(r"match (\d+) \[([^\]]+)\]", ln):
                out[int(mid)] = why
            run = re.search(r": run \[([^\]]+)\]$", ln)
            if run:
                out[RUN_KEY] = run.group(1)
    return out


def reported_failure(argv: list[str], tail: list[str]) -> str | None:
    for line in tail:
        s = line.strip()
        for m in STEP_FAILURE_MARKERS.get(argv[0], ()):
            if s.startswith(m):
                return s[:200]
    return None


# ------------------------------------------------------------------------------------------------ backup --

def backup_folder() -> Path:
    """A3: the operator's backup folder: SP_BACKUP_DIR when set, else ~/backups, where the documented backup line
    writes (`sqlite3 data/sports.db ".backup ~/backups/sports_$(date +%F).db"`, docs/CLI.md)."""
    return Path(c.setting("SP_BACKUP_DIR") or Path.home() / "backups").expanduser()


def todays_backup(folder: Path, day: date) -> Path | None:
    """A .backup dated `day` (sports_<day>*.db, non-empty), whoever took it."""
    if not folder.is_dir():
        return None
    for p in sorted(folder.glob(f"sports_{day.isoformat()}*.db")):
        if p.is_file() and p.stat().st_size > 0:
            return p
    return None


def _set_aside(paths: list[Path], stamp: str) -> list[str]:
    """380.3: "A finished copy it left is renamed aside, never deleted, so that no later run counts it as today's
    backup." The new name ends in .failed-<stamp>, which todays_backup's sports_<day>*.db never matches."""
    out = []
    for p in paths:
        try:
            if p.exists():
                q = p.with_name(f"{p.name}.failed-{stamp}")
                os.replace(p, q)
                out.append(str(q))
        except OSError as e:
            out.append(f"NOT set aside: {p.name} ({type(e).__name__})")
    return out


def take_backup(folder: Path, day: date) -> dict:
    """380.3 (ARCHITECT): "A backup the run takes is a backup only when every part of taking it succeeded: the copy,
    the integrity check, the open, the hash and the hash file. Any error fails the run as a backup failure, before the
    first step." The .backup API (Connection.backup), then PRAGMA integrity_check on the copy, the rename into place,
    an open, the sha256, the .sha256 file. Never cp; never under data/ (law 5); never overwrites; never deletes.
    `ok` is true only when every part succeeded. Caller holds the lock."""
    dest = folder / f"sports_{day.isoformat()}.db"
    if dest.exists():
        dest = folder / f"sports_{day.isoformat()}_closing_{c.utc_now():%H%M%S}.db"
    tmp = dest.with_suffix(".db.partial")
    hashf = dest.with_name(dest.name + ".sha256")
    rec = {"file": str(dest), "taken": True, "copied": False, "integrity": None, "opens": False,
           "sha256": None, "hash_file": None, "ok": False}
    try:
        c.refuse_under_data(folder)
        folder.mkdir(parents=True, exist_ok=True)
        s = c.ro_connect(c.db_path())
        d = sqlite3.connect(tmp)
        try:
            s.backup(d)
        finally:
            d.close()
            s.close()
        rec["copied"] = True
        os.chmod(tmp, 0o600)
        rec["integrity"] = c.copy_integrity(tmp)         # the copy, immutable: nothing beside it (addendum 73 item 4)
        if rec["integrity"] != "ok":
            raise RuntimeError(f"integrity_check: {rec['integrity']}")
        os.replace(tmp, dest)
        con = c.copy_connect(dest)                       # the finished copy, immutable likewise (addendum 73 item 4)
        try:
            con.execute("SELECT count(*) FROM sqlite_master").fetchone()
        finally:
            con.close()
        rec["opens"] = True
        rec["sha256"] = c.sha256_file(dest)
        hashf.write_text(f"{rec['sha256']}  {dest.name}\n")
        rec["hash_file"] = str(hashf)
        rec["ok"] = True
    except (Exception, SystemExit) as e:  # noqa: BLE001 - receipted (a law-5 refusal too), then the run fails
        rec["error"] = c.redact(f"{type(e).__name__}: {e}")
        if folder.is_dir() and not str(rec["error"]).startswith("SystemExit"):
            rec["set_aside"] = _set_aside([tmp, dest, hashf], c.utc_now().strftime("%Y%m%dT%H%M%SZ"))
    return rec


# ----------------------------------------------------------------------------------------------- summary --

def hold_for(d: dict, fam: str) -> str | None:
    """A7: the hold text a Desk row carries, from CLOSING_HOLDS (an unknown exec edge is under the bar), for the
    families the hold names (B5)."""
    e = ((d.get("exec") or {}).get("edge_pp"))
    tags = set(d.get("tags") or [])
    out = []
    for h in CLOSING_HOLDS:
        if fam not in h["families"] or d.get("call") != h["call"]:
            continue
        if "exec_edge_under_pp" in h and not (e is None or e < h["exec_edge_under_pp"]):
            continue
        if "tags_any" in h and not tags & set(h["tags_any"]):
            continue
        out.append(h["text"])
    return " · ".join(out) or None


def _pp(x) -> str:
    return "n/a" if x is None else f"{x:+.1f}pp"


def _r2(x):
    return None if x is None else round(x, 2)


def _units(x) -> str:
    return f"{(x or 0):g}u"


def side_team(row: dict, side: str | None) -> str:
    return {"HOME": row.get("home_team"), "AWAY": row.get("away_team"), "DRAW": "Draw"}.get(side) or (side or "-")


def call_text(row: dict, d: dict) -> str:
    """A call as the page names it: 'PASS', or '<CALL> <pick> <units>u' for a staked call."""
    if d.get("call") in STAKED_CALLS:
        return f"{d['call']} {side_team(row, d.get('pick'))} {_units(d.get('units'))}"
    return str(d.get("call") or "-")


def is_quarantine_shadow(d: dict) -> bool:
    """desk_policy.is_quarantine_shadow on the export's desk block: PASS, shadow units > 0, a quarantine tag."""
    return bool(d.get("call") == "PASS" and (d.get("shadow_units") or 0) > 0
                and any(str(t).startswith("quarantine") and str(t).endswith("(shadow)") for t in d.get("tags") or []))


def unresolved_injuries(r: dict) -> int | None:
    """B7: the injured players whose position did not resolve, both sides (nfl_predict.py's
    input_quality.injuries.<side>.positions_unresolved: "an empty qb_listed beside these is NOT 'no QB out'").
    None when the row carries no such field."""
    inj = (r.get("input_quality") or {}).get("injuries") or {}
    got = [(inj.get(s) or {}).get("positions_unresolved") for s in ("home", "away")]
    if all(g is None for g in got):
        return None
    return sum(len(g or []) for g in got)


def injuries_empty(r: dict) -> list[str]:
    """Addendum 40 item 4: the teams whose stored injury list is empty (input_quality.injuries.<side>.count 0): "a list
    we could not read, not a team with nobody hurt". A side without a count is not listed."""
    inj = (r.get("input_quality") or {}).get("injuries") or {}
    return [r.get("home_team") if s == "home" else r.get("away_team") for s in ("home", "away")
            if isinstance(inj.get(s), dict) and inj[s].get("count") == 0]


def desk_rows(doc: dict, cover_ids: set, done: datetime, started_ids=frozenset(), fam: str = "") -> list[dict]:
    """The export's Desk rows for the run's own games (C2), less the games the ONE started test (R1) calls started
    at `done`, the moment the steps finished: a stored status then LIVE or FINISHED (`started_ids`) or a start time
    at or before `done`."""
    out = []
    for r in doc.get("predictions") or []:
        d = r.get("desk")
        if not d or not r.get("utc_date") or r.get("match_id") not in cover_ids:
            continue
        st = parse_utc(r["utc_date"])
        if r.get("match_id") in started_ids or st <= utc(done):
            continue
        vs = d.get("value_shadow") or None
        out.append({"match_id": r.get("match_id"), "start": iso_z(st), "start_et": et(st),
                    "away": r.get("away_team"), "home": r.get("home_team"),
                    "call": d.get("call"), "call_text": call_text(r, d), "pick": side_team(r, d.get("pick")),
                    "units": d.get("units") or 0, "edge_pp": _r2(d.get("edge_pp")),
                    "exec_edge_pp": _r2((d.get("exec") or {}).get("edge_pp")),
                    "order": (d.get("order") or {}).get("text"), "order_why": (d.get("order") or {}).get("why"),
                    "reason": d.get("reason"), "pass_kind": d.get("pass_kind"),
                    "kalshi_only_hold": d.get("kalshi_only_hold"), "hold": hold_for(d, fam),
                    "unresolved_injuries": unresolved_injuries(r) if fam == "NFL" else None,
                    "injuries_empty": injuries_empty(r) if fam == "NFL" else [],
                    "quarantine_shadow": ({"pick": side_team(r, d.get("pick")), "units": d.get("shadow_units"),
                                           "edge_pp": _r2(d.get("edge_pp")),
                                           "exec_edge_pp": _r2((d.get("exec") or {}).get("edge_pp"))}
                                          if is_quarantine_shadow(d) else None),
                    "value_shadow": ({"side": side_team(r, vs.get("side")), "units": vs.get("units"),
                                      "edge_pp": _r2(vs.get("edge_pp")),
                                      "exec_edge_pp": _r2((vs.get("exec") or {}).get("edge_pp"))}
                                     if vs else None),
                    "starters_listed": ({k: (r.get("pitchers") or {}).get(k) is not None for k in ("home", "away")}
                                        if "pitchers" in r else None)})
    return sorted(out, key=lambda x: (x["start"], x["match_id"] or 0))


def missing_from_export(doc: dict, covers: list[dict], done: datetime, games: list[dict]) -> list[dict]:
    """Codex on #370, per run (C2): every covered game in the STORED schedule (re-read after the steps synced it)
    that is NOT started at `done` (R1) must have a Desk row in the export. Returns the ones that do not."""
    have = {r.get("match_id") for r in doc.get("predictions") or [] if r.get("desk")}
    ids = {g["match_id"] for g in covers}
    need = [g for g in games if g["match_id"] in ids and not started(g, done)]
    return [{"match_id": g["match_id"], "start": iso_z(g["start"]), "start_et": et(g["start"]),
             "away": g["away"], "home": g["home"], "reason": "missing from export"}
            for g in need if g["match_id"] not in have]


def target_started(games: list[dict], start: datetime, done: datetime) -> str | None:
    """R1: the target start time has started when that moment is at or before `done`, or when every stored game at
    that time has a stored status (re-read after the steps) of LIVE or FINISHED. Returns why, else None."""
    if utc(start) <= utc(done):
        return f"start {iso_z(start)} at or before {iso_z(done)}, when the steps finished"
    tg = [g for g in games if g["start"] == utc(start)]
    if tg and all(g["status"] in STARTED_STATUSES for g in tg):
        return "stored status " + "/".join(sorted({g["status"] for g in tg})) + " when the steps finished"
    return None


def start_moved(covers: list[dict], start: datetime) -> list[dict]:
    """C (ARCHITECT 2026-10-09, addendum 23, the 15:08Z P1): "If the schedule read moves a covered game off the run's
    start time, that game leaves the run: it is not paged under the old time, and it is a new start time for the
    watch. A run left with no game ends as a failed attempt, 'start moved', nothing pushed or paged." The covered
    games whose stored start time (re-read by match id after the steps, any window, any status) is no longer the
    start the run covered them at. A game no longer stored is moved too (law 4)."""
    ids = [g["match_id"] for g in covers]
    if not ids:
        return []
    con = c.ro_connect(c.db_path())
    try:
        now_at = {i: d for i, d in con.execute(
            f"SELECT id, utc_date FROM matches WHERE id IN ({','.join('?' * len(ids))})", ids).fetchall()}
    finally:
        con.close()
    out = []
    for g in covers:
        d = now_at.get(g["match_id"])
        new = parse_utc(d) if d else None
        if new is None or new != utc(g["start"]):
            out.append({"match_id": g["match_id"], "game": f"{g['away']} @ {g['home']}",
                        "target": iso_z(start), "covered_start": iso_z(g["start"]),
                        "stored_start": iso_z(new) if new else None})
    return out


CALLED_OFF = ("CANCELLED", "POSTPONED")                # addendum 25 item 3: a covered game's line of its own


def called_off(covers: list[dict]) -> list[dict]:
    """Addendum 25 item 3 (#390 item 4): the covered games whose stored status, re-read by match id after the schedule
    read, is CANCELLED or POSTPONED: {match_id, game, away, home, covered_start, status}."""
    ids = [g["match_id"] for g in covers]
    if not ids:
        return []
    con = c.ro_connect(c.db_path())
    try:
        st = {i: str(x or "").upper() for i, x in con.execute(
            f"SELECT id, status FROM matches WHERE id IN ({','.join('?' * len(ids))})", ids).fetchall()}
    finally:
        con.close()
    return [{"match_id": g["match_id"], "game": f"{g['away']} @ {g['home']}", "away": g["away"], "home": g["home"],
             "covered_start": iso_z(g["start"]), "status": st[g["match_id"]]}
            for g in covers if st.get(g["match_id"]) in CALLED_OFF]


# ------------------------------------------------------------------------------------------------ prices --
# R2 (ARCHITECT 2026-10-08), for every family (C4): the capture times are read from the stored rows the export read,
# read-only: books = table `odds`, the match's '1X2' rows before the start, reduced to the LAST CAPTURE SESSION by
# src/walters/close.py last_capture (the close contract every export's market block uses); Kalshi = table
# `odds_snapshots`, source 'kalshi', per selection the latest row before the start (the in-game guard).

def _close_contract():
    root = str(Path(__file__).resolve().parents[2])
    if root not in sys.path:
        sys.path.insert(0, root)
    from src.walters.close import last_capture
    return last_capture


def _kalshi_mismatched(con: sqlite3.Connection, match_id) -> list | None:
    """addendum 37 item 3 (ARCHITECT 2026-10-10): the one helper, src/walters/kalshi_legs.mismatched, on this
    read-only connection: the events of a game whose Kalshi legs name two events or sit on another game."""
    _close_contract()                                  # puts the repo root on sys.path
    from src.walters.kalshi_legs import mismatched
    return mismatched(con, [match_id]).get(match_id)


def price_captures(con: sqlite3.Connection, match_id, start: datetime) -> dict:
    """{"books": datetime|None, "kalshi": datetime|None}: the capture times of the stored rows the export read."""
    fp = utc(start)
    rows = []
    for bk, sel, line, cap in con.execute(
            "SELECT bookmaker, selection, line, captured_at FROM odds "
            "WHERE match_id = ? AND market = '1X2' AND captured_at IS NOT NULL", (match_id,)):
        rows.append(SimpleNamespace(bookmaker=bk, selection=sel, line=line, market="1X2", captured_at=parse_utc(cap)))
    sess = _close_contract()(rows, fp)
    latest: dict = {}
    for sel, cap in con.execute(
            "SELECT selection, captured_at FROM odds_snapshots "
            "WHERE match_id = ? AND source = 'kalshi' AND captured_at IS NOT NULL", (match_id,)):
        t = parse_utc(cap)
        if t < fp and (sel not in latest or t > latest[sel]):
            latest[sel] = t
    if _kalshi_mismatched(con, match_id):      # addendum 37 item 3: mismatched legs are never read
        latest = {}
    return {"books": min((o.captured_at for o in sess), default=None),
            "kalshi": min(latest.values(), default=None), "kalshi_legs": latest}


def shows_books(r: dict) -> bool:
    """The export row shows books: its market block priced at least one complete book (bookmaker_count > 0)."""
    return bool(((r.get("market") or {}).get("bookmaker_count") or 0) > 0)


def shows_kalshi(r: dict) -> bool:
    """The export row shows a Kalshi quote: the HOME contract's bid/ask, any captured leg, or a kalshi market block."""
    k = (r.get("market") or {}).get("kalshi")
    # addendum 37 item 3: a mismatched block ({status: mismatched, events}) carries no price and is not a quote
    return (r.get("kalshi_bid") is not None or r.get("kalshi_ask") is not None or bool(r.get("kalshi_legs"))
            or bool(k and k.get("status") != "mismatched"))


# A5 (ARCHITECT 2026-10-09, addendum 23): "Where a market has more than one Kalshi leg, the legs that must be fresh
# are the legs the Desk read for that row: the leg behind each exec block and order line the row carries, the call's
# and a value shadow's, and every leg where the row's reference is Kalshi. A stale leg the Desk did not read does not
# fail the run; it is listed in the receipt." The legs are named from src/walters/desk_policy.py's own selection,
# read here from the export row (C8: closing.py reads the export, never the Desk's code; a test pins the two):
#   desk_block "exec" = call_exec_block -> exec_block(r, pick) -> side_quotes(r, pick): the pick's own leg when it
#     carries a ticker; else, two-way, the opponent's ticketed leg (NO); else the pick's leg when its ask is
#     captured; else k_side, the HOME contract's quotes (kalshi_bid / kalshi_ask: HOME YES, or a two-way AWAY's NO).
#   desk_block "value_shadow.exec" = exec_block(r, value side) -> side_quotes(r, value side): the same selection.
#   desk_block "order" = order_line(r, pick, units, ladder): LADDER = NO on the HOME leg; else the pick's ticketed
#     leg; else, two-way, the opponent's ticketed leg (NO). Named by the order's own ticker, and only by it (addendum
#     25 2(ii)): an order with no ticker is no order written, and no leg read.
#   desk_block "reference" == "kalshi_only" (kalshi_only_ref, the HOME contract's mid; two-way only): every leg.
def _three_way(r: dict) -> bool:
    """desk_policy.normalize's threeWay: a DRAW in the market's fair prices or in the model's probabilities."""
    mk = r.get("market") or {}
    sel = mk.get("selections")
    fair = ({k: (v or {}).get("fair_prob") for k, v in sel.items()} if sel is not None else (mk.get("fair_prob") or {}))
    return fair.get("DRAW") is not None or ((r.get("prediction") or {}).get("probabilities") or {}).get("draw") is not None


def _side_leg(r: dict, side: str | None) -> str | None:
    """The leg desk_policy.side_quotes reads for `side` (see above). None: no Kalshi contract read."""
    if side not in ("HOME", "DRAW", "AWAY"):
        return None
    legs = r.get("kalshi_legs") or {}
    leg = legs.get(side) or {}
    if leg.get("ticker"):
        return side
    opp = {"HOME": "AWAY", "AWAY": "HOME"}.get(side)
    if not _three_way(r) and opp and (legs.get(opp) or {}).get("ticker"):
        return opp
    if leg.get("ask") is not None:
        return side
    if side == "HOME" or (side == "AWAY" and not _three_way(r)):
        return "HOME"                     # k_side: the HOME contract's quotes
    return None


def _order_leg(r: dict, d: dict) -> str | None:
    """The leg desk_policy.order_line writes the order on (see above). Codex 4232307584 (ARCHITECT 2026-10-09,
    addendum 25 item 2(ii): "Name a leg only when the order carries its ticker."): order_line writes no order without
    a ticker (its `ticker` None + `why`), so the Desk read no leg for it; the leg is the one whose ticker the order
    carries, and none otherwise (a ladder with no HOME ticker read no HOME leg)."""
    o = d.get("order")
    if not o or d.get("call") not in STAKED_CALLS or not o.get("ticker"):
        return None
    for sel, leg in (r.get("kalshi_legs") or {}).items():
        if (leg or {}).get("ticker") == o["ticker"]:
            return sel
    return None


def desk_read_legs(r: dict) -> set | None:
    """A5: the Kalshi legs the Desk read for the export row `r`. None = every leg (the reference is Kalshi)."""
    d = r.get("desk") or {}
    if d.get("reference") == "kalshi_only":
        return None
    out = set()
    if d.get("exec") is not None:
        out.add(_side_leg(r, d.get("pick")))
    out.add(_order_leg(r, d))
    vs = d.get("value_shadow") or {}
    if vs and vs.get("exec") is not None:
        out.add(_side_leg(r, vs.get("side")))
    out.discard(None)
    return out


def stale_prices(doc: dict, rows: list[dict], run_start: datetime, unread: list | None = None) -> list[dict]:
    """R2: for every game in the summary, a price the export shows that was captured before the run's start (380.4:
    the moment the run held the lock). A shown price with no stored capture time is stale too (law 4). Kalshi, A5:
    where the game has more than one Kalshi leg, the legs the Desk read (desk_read_legs) must be fresh; a stale leg
    it did not read is appended to `unread` and fails nothing. One leg: as before, the leg is checked."""
    by_id = {r.get("match_id"): r for r in doc.get("predictions") or []}
    s0 = utc(run_start)
    out = []
    con = c.ro_connect(c.db_path())
    try:
        for x in rows:
            r = by_id.get(x["match_id"]) or {}
            caps = price_captures(con, x["match_id"], parse_utc(x["start"]))

            def line(kind, at, **extra):
                return {"match_id": x["match_id"], "game": f"{x['away']} @ {x['home']}", "start_et": x["start_et"],
                        "price": kind, **extra, "captured_at": iso_z(at) if at else None, "run_start": iso_z(s0)}
            if shows_books(r):
                at = caps["books"]
                if at is None or at < s0:
                    out.append(line("books", at))
            if not shows_kalshi(r):
                continue
            legs = caps["kalshi_legs"]
            every = set(legs) | set((r.get("kalshi_legs") or {}))
            if len(every) <= 1:
                at = caps["kalshi"]
                if at is None or at < s0:
                    out.append(line("kalshi", at))
                continue
            read = desk_read_legs(r)
            read = every if read is None else read
            for sel in sorted(every | read):      # a read leg with no stored capture is stale (law 4)
                at = legs.get(sel)
                if at is None or at < s0:
                    if sel in read:
                        out.append(line("kalshi", at, leg=sel))
                    elif unread is not None:
                        unread.append(line("kalshi", at, leg=sel, read_by_desk=False))
    finally:
        con.close()
    return out


def stale_starters(doc: dict, rows: list[dict], games: list[dict], run_start: datetime) -> list[dict]:
    """380.1 (ARCHITECT): "The run checks its starters, not a step's console. For every game in the summary: where the
    export row lists a starter, the stored starter row for that side was refreshed at or after the run's start. A
    starter refreshed earlier fails the run as stale starters, naming the game, the side and both times [...] A side
    with no starter listed is not stale." The stored row: match_participants (role 'starting_pitcher', the side's
    team), its refreshed_at, which sync_pitchers stamps on every row it writes (src/ingestion/service.py, law 1).
    Listed with no stored row, or no stored time, is stale too (law 4)."""
    by_id = {r.get("match_id"): r for r in doc.get("predictions") or []}
    teams = {g["match_id"]: g for g in games}
    s0 = utc(run_start)
    out = []
    con = c.ro_connect(c.db_path())
    try:
        for x in rows:
            r, g = by_id.get(x["match_id"]) or {}, teams.get(x["match_id"]) or {}
            for side in ("home", "away"):
                if (r.get("pitchers") or {}).get(side) is None:
                    continue                                   # not listed: the model already shrinks for it
                row = con.execute(
                    "SELECT refreshed_at FROM match_participants WHERE match_id = ? AND team_id = ? "
                    "AND role = 'starting_pitcher' ORDER BY refreshed_at DESC LIMIT 1",
                    (x["match_id"], g.get(f"{side}_team_id"))).fetchone()
                at = parse_utc(row[0]) if row and row[0] else None
                if at is None or at < s0:
                    out.append({"match_id": x["match_id"], "game": f"{x['away']} @ {x['home']}",
                                "start_et": x["start_et"], "side": side,
                                "team": x["home"] if side == "home" else x["away"],
                                "refreshed_at": iso_z(at) if at else None, "run_start": iso_z(s0)})
    finally:
        con.close()
    return out


def summary_block(x: dict) -> str:
    lines = [f"── {x['start_et']} · {x['away']} @ {x['home']}  [match {x['match_id']}]",
             f"   call   {x['call']} · pick {x['pick']} · {_units(x['units'])} · edge {_pp(x['edge_pp'])} "
             f"· exec edge {_pp(x['exec_edge_pp'])}"]
    if x["call"] in STAKED_CALLS:
        order = x["order"] or f"no order: {x['order_why'] or 'none written'}"
        lines.append(f"   order  {order}" + (f" · HOLD: {x['hold']}" if x["hold"] else ""))
    else:
        lines.append(f"   order  none ({x['call']}: {x['reason'] or x['pass_kind'] or '-'})")
    k = x.get("kalshi_only_hold")
    if k:
        lines.append(f"   kalshi-only hold (record only, not a call): mid {k.get('mid')} (bid {k.get('bid')} / ask "
                     f"{k.get('ask')}, {k.get('spread_c')}c) · raw {_pp(k.get('raw_edge_pp'))} · equal footing "
                     f"{_pp(k.get('equal_footing_edge_pp'))} · would {k.get('would_call')} "
                     f"{_units(k.get('would_units'))}")
    for kind in ("value_shadow", "quarantine_shadow"):
        v = x.get(kind)
        if v:
            lines.append(f"   {kind.replace('_', ' ')}  {v.get('side') or v.get('pick')} {_units(v.get('units'))} · "
                         f"edge {_pp(v.get('edge_pp'))} · exec {_pp(v.get('exec_edge_pp'))} · shadow, not staked")
    return "\n".join(lines)


# -------------------------------------------------------------------------------------------------- page --

def wrap(parts: list[str], limit: int = PAGE_MAX_CHARS, indent: str = "  ") -> list[str]:
    """C5: "No line over 100 characters." One entry is one line when it fits; else it continues on indented lines,
    broken between its ' · ' fields, never inside one (a single field longer than a line is cut at the limit)."""
    out, cur = [], ""
    for p in parts:
        cand = p if not cur else f"{cur} · {p}"
        if len(cand) <= limit:
            cur = cand
            continue
        if cur:
            out.append(cur)
            cur = f"{indent}{p}"
        else:
            cur = (indent if out else "") + p
        while len(cur) > limit:
            out.append(cur[:limit])
            cur = indent + cur[limit:]
    if cur:
        out.append(cur)
    return out


def game_of(x: dict) -> str:
    return f"{x['away']} @ {x['home']}"


def page_text(fam: str, start: datetime, at: datetime, rows: list[dict], prev: dict,
              off: list[dict] | None = None) -> tuple[str, str, bool]:
    """C5 (ARCHITECT): "In this order: the family, the start time in ET and the minutes to it; one line for each
    PLAY (pick, units, the order line as the export prints it, exec edge, and the hold text where a hold applies);
    one line for each value shadow and each quarantine shadow, ending 'shadow, not staked'; the number of PASS games.
    Where the call differs from the last file's call for the same game, the line ends 'was' and the earlier call.
    High priority when it carries a PLAY. No line over 100 characters." 380.1: a game with a side with no starter
    listed says so on a line of its own under its call.
    Addendum 23: B3 "A game whose last call was a PLAY or a LADDER and is now PASS has a line of its own: the game,
    PASS, 'was' and the earlier call. It makes the page high priority: an order may be working on the earlier call."
    B4 "Every line except the head and the PASS count names its game." B7 "An NFL PLAY on a game with injured players
    whose position did not resolve says so on its line, with the count." `prev`: each game's last call (last_calls,
    reading 7 as amended by addendum 25 2(iii): "C5's was and B3 read this."). Addendum 25 item 3 (#390 item 4), `off`
    (called_off): "A covered game the schedule read finds cancelled or postponed has a line of its own: the game and
    its status, and was with the earlier call when that call was a PLAY or a LADDER. With such a call the page is high
    priority. It is not counted as a PASS." Returns (title, body, high)."""
    head = f"{fam} {utc(start).astimezone(NY):%H:%M} ET · T-{max(0, round(minutes_to(start, at)))}m"
    lines = [head]
    starter_note = {}
    for x in rows:
        sl = x.get("starters_listed")
        if sl and not all(sl.values()):
            miss = [x["home"] if s == "home" else x["away"] for s in ("home", "away") if not sl[s]]
            starter_note[x["match_id"]] = [f"{x['away']} @ {x['home']} ({x['call_text']})",
                                           f"no starter listed for {' and '.join(miss)}", "the model shrinks for it"]
    plays = [x for x in rows if x["call"] in STAKED_CALLS]
    for x in plays:
        parts = [game_of(x), x["call_text"], x["order"] or f"no order: {x['order_why'] or 'none written'}",
                 f"exec {_pp(x['exec_edge_pp'])}"]
        if x.get("unresolved_injuries"):                # B7
            parts.append(f"{x['unresolved_injuries']} injured, position unresolved")
        if x.get("injuries_empty"):                     # addendum 40 item 4, beside B7's count
            parts.append(f"injury list empty: {' and '.join(x['injuries_empty'])}")
        if x["hold"]:
            parts.append(x["hold"])
        was = prev.get(x["match_id"])
        if was and was != x["call_text"]:
            parts.append(f"was {was}")
        lines += wrap(parts)
        if x["match_id"] in starter_note:
            lines += wrap(starter_note.pop(x["match_id"]))
    for x in rows:
        v = x.get("value_shadow")
        if v:
            lines += wrap([game_of(x), f"value shadow {v['side']} {_units(v['units'])}", f"edge {_pp(v['edge_pp'])}",
                           f"exec {_pp(v['exec_edge_pp'])}", "shadow, not staked"])
    for x in rows:
        q = x.get("quarantine_shadow")
        if q:
            lines += wrap([game_of(x), f"quarantine shadow {q['pick']} {_units(q['units'])}",
                           f"edge {_pp(q['edge_pp'])}",
                           f"exec {_pp(q['exec_edge_pp'])}", "shadow, not staked"])
    dropped = [x for x in rows if x["call"] == "PASS"
               and str(prev.get(x["match_id"]) or "").split(" ")[0] in STAKED_CALLS]
    for x in dropped:                                # B3: was PLAY / LADDER, now PASS
        lines += wrap([game_of(x), "PASS", f"was {prev[x['match_id']]}"])
        if x["match_id"] in starter_note:
            lines += wrap(starter_note.pop(x["match_id"]))
    for mid, note in starter_note.items():           # 380.1 for a game with no call line of its own
        lines += wrap(note)
    off_staked = False
    for x in off or []:                              # addendum 25 item 3: cancelled or postponed, its own line
        was = prev.get(x["match_id"])
        staked = str(was or "").split(" ")[0] in STAKED_CALLS
        off_staked = off_staked or staked
        lines += wrap([f"{x['away']} @ {x['home']}", x["status"]] + ([f"was {was}"] if staked else []))
    n_pass = sum(1 for x in rows if x["call"] == "PASS")
    lines.append(f"PASS: {n_pass} game{'s' if n_pass != 1 else ''}")
    lines.append(machine_line())                     # addendum 45: the last line names the machine by role
    title = f"{fam} closing {utc(start).astimezone(NY):%H:%M} ET"
    return title, "\n".join(lines), bool(plays) or bool(dropped) or off_staked


# THE LAST CALL (ARCHITECT 2026-10-09, addendum 25 item 2(iii); reading 7 amended): "The last call of a game is the
# call the operator was last shown for it: its call on the last closing page that covered it or, when no page has
# covered it, its call in the newest export that no closing run wrote. An export a closing run wrote never supplies
# the last call of a game that run did not page. C5's was and B3 read this." Built from the receipts: "A closing
# receipt records the sha256 of the export it wrote and the last calls it found before its first step, for every game
# of the family it found one for. A later run that finds the newest file to be a closing run's export takes, for the
# games that run did not page, the last calls in that receipt. Where the chain cannot be followed (no receipt names
# the file), the file's call stands, as today."
LAST_CALL_KEEP_H = 24        # a call for a game whose start is more than a day before the run is not carried


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _paged(r: dict) -> bool:
    """The run's page went out: the phone accepted it (B2). An attempt whose page was not accepted paged no one."""
    return ((r.get("page") or {}).get("phone") or {}).get("accepted") is True


def _paged_calls(w: dict) -> dict:
    """Addendum 26 item 2(b): "The receipt carries what it paged, so the page's calls do not depend on the file being
    there." The calls on a closing run's page, when its page went out: {match_id: {call, start, source}}, from the
    receipt's Desk rows (`call_text`). A receipt written before the rows carried their call text falls back to the
    export it names, when that file is still in exports/ with the same bytes (else those rows add nothing)."""
    if not _paged(w):
        return {}
    rows = w.get("desk_rows") or []
    file_calls: dict | None = None
    out = {}
    for x in rows:
        mid, text = x.get("match_id"), x.get("call_text")
        if text is None:
            if file_calls is None:
                file_calls = {}
                ew = w.get("export_written") or {}
                f = c.REPO / str(ew.get("file") or "")
                try:
                    if ew.get("file") and f.is_file() and _sha256(f) == ew.get("sha256"):
                        for r in json.loads(f.read_text()).get("predictions") or []:
                            if r.get("desk") and r["desk"].get("call"):
                                file_calls[r.get("match_id")] = call_text(r, r["desk"])
                except (OSError, ValueError):
                    pass
            text = file_calls.get(mid)
        if mid is not None and text:
            out[mid] = {"call": text, "start": x.get("start"), "source": f"page {w.get('run_id')}"}
    return out


def _wall_start(w: dict) -> float:
    """The wall-clock moment the run started (file mtimes are compared with it); a receipt without it: its run_start."""
    try:
        return float(w["run_start_wall"])
    except (KeyError, TypeError, ValueError):
        return parse_utc(w["run_start"]).timestamp()


def last_calls(fam: str, at: datetime) -> dict:
    """The last call of every game of the family found, read before the first step (the run's own export overwrites
    the file): {match_id: {"call": call text, "start": ISO, "source": where it was shown}}. Addendum 26 item 2(b)
    (ARCHITECT 2026-10-09): "The chain of last calls runs through the receipts, not the files. The last calls are those
    of the newest closing receipt of the family that carries them, with the calls that run paged when its page went
    out, whether its export is still in exports/ or R6 moved it. Only an export that no closing run wrote, written
    after that run started, comes before it." So: the newest closing receipt of the family carrying `last_calls` (a
    receipt without them cannot be followed) gives the base, its own page's calls over it; then the family's files in
    exports/ that no closing receipt names (by sha256) and that were written after that run started, newest first,
    supply the call for the games they hold. With no such receipt, every file in exports/, newest first (the chain cannot
    be followed: the file's call stands). A game whose start is more than LAST_CALL_KEEP_H hours before `at` is left
    out. A game nothing found has no last call (no 'was')."""
    keep = utc(at) - timedelta(hours=LAST_CALL_KEEP_H)
    ex = c.REPO / "exports"
    files = sorted(ex.glob(FAMILIES[fam]["export_glob"]), key=lambda p: p.stat().st_mtime,
                   reverse=True) if ex.is_dir() else []
    recs = [r for r in receipts(("closing",)) if r.get("family") == fam]
    written = {(r.get("export_written") or {}).get("sha256") for r in recs} - {None}
    carriers = [r for r in recs if isinstance(r.get("last_calls"), dict)]
    w = carriers[-1] if carriers else None

    def kept(start) -> bool:
        try:
            return parse_utc(start) >= keep
        except (TypeError, ValueError):
            return False
    base: dict = {}
    since = None
    if w is not None:
        for k, v in w["last_calls"].items():           # the last calls that run found
            mid = int(k) if str(k).lstrip("-").isdigit() else k
            if isinstance(v, dict) and v.get("call") and kept(v.get("start")):
                base[mid] = v
        base.update({k: v for k, v in _paged_calls(w).items() if kept(v["start"])})   # its page's calls
        since = _wall_start(w)
    newer: dict = {}
    for p in files:
        try:
            if since is not None and p.stat().st_mtime < since:
                break                 # written before that run started: its last calls already read it
            raw = p.read_bytes()
            doc = json.loads(raw)
        except (OSError, ValueError):
            continue
        if w is not None and hashlib.sha256(raw).hexdigest() in written:
            continue                  # a closing run's export: its calls reach the chain through its receipt
        for r in doc.get("predictions") or []:
            mid, d = r.get("match_id"), r.get("desk")
            if mid is None or not d or not d.get("call") or not kept(r.get("utc_date")):
                continue
            newer.setdefault(mid, {"call": call_text(r, d), "start": iso_z(parse_utc(r["utc_date"])),
                                   "source": p.name})
    base.update(newer)
    return base


# ---------------------------------------------------------------------------------------------------- run --

def _family_refusal(fam: str) -> str | None:
    skip = {s.strip().upper() for s in (c.setting("SP_SKIP_FAMILIES") or "").split(",") if s.strip()}
    if fam in skip:
        if fam == "MLB":
            return "laptop only: SP_SKIP_FAMILIES names MLB here (the host cannot reach the MLB feed)"
        return f"SP_SKIP_FAMILIES names {fam} here"
    return None


def _backup_folder_refusal(folder: Path) -> str | None:
    """R5 (ARCHITECT 2026-10-08): "The backup folder is checked before anything else. A folder under data/ refuses
    the run, receipted, whether or not a backup already sits there." """
    try:
        c.refuse_under_data(folder)
    except SystemExit as e:
        return f"backup folder under data/ (law 5): {str(e).lstrip('✗ ').strip()}"
    return None


def _mirror_refusal() -> str | None:
    """M1 (ARCHITECT 2026-10-08): "A closing run pushes the mirror or it is not a success." """
    if not (c.setting(MIRROR_SETTING) or "").strip():
        return (f"{MIRROR_SETTING} is not set (environment, host.env, the checkout's .env): a closing run pushes the "
                "exports mirror or it is not a success")
    return None


def _role_refusal() -> str | None:
    """Addendum 45 P1: unset, or neither host nor laptop, refuses the run before any step, as M1 does. The value is
    a role, not a secret: an invalid one is shown (cut to 20 characters)."""
    raw = (c.setting(ROLE_SETTING) or "").strip()
    if mirror_role():
        return None
    if not raw:
        return (f"{ROLE_SETTING} is not set (environment, host.env, the checkout's .env): a closing run pushes the "
                "exports mirror as this machine's role, host or laptop; there is no default")
    return f"{ROLE_SETTING} is {raw[:20]!r}, neither host nor laptop: there is no default"


def _card_topic_refusal() -> str | None:
    """C6 (ARCHITECT): "A closing run that cannot page is not a success. NTFY_CARD_TOPIC unset, read through
    sp_common.setting, refuses the run before its first step, receipted, naming the setting [...] The topic's value
    is never printed." A topic with whitespace pages a different topic, or none (sp_notify): refused the same way."""
    raw = c.setting(CARD_TOPIC) or ""
    if not raw.strip():
        return (f"{CARD_TOPIC} is not set (environment, host.env, the checkout's .env): a closing run that cannot "
                "page is not a success")
    if any(ch.isspace() for ch in raw):
        return (f"{CARD_TOPIC} contains whitespace ({len(raw)} chars; value not shown): ntfy would page a different "
                "topic, or none")
    return None


def _start_refusal(start: str | None) -> str | None:
    """R4 (ARCHITECT 2026-10-08): a malformed start time is "a receipted refusal, exit 2, like the other refusals"."""
    if start is None:
        return None
    try:
        parse_utc(start)
    except (TypeError, ValueError) as e:
        return f"malformed --start {start!r} (ISO UTC expected, e.g. 2026-10-08T23:05:00Z): {e}"[:300]
    return None


def refusal_checks(fam: str, folder: Path, start: str | None = None) -> list:
    """The run's own refusals, in their order (R5 first). The setup script runs the same list (380.2)."""
    return [lambda: _backup_folder_refusal(folder), lambda: _family_refusal(fam), _mirror_refusal, _role_refusal,
            _card_topic_refusal, lambda: _start_refusal(start)]


def slate_name(fam: str, start: datetime, at: datetime) -> str:
    """The family's slate file name (what its slate chain writes into exports/): MLB mlb_MLB_<first pitch's NY
    date>.json; NFL / SOCCER the export's own name for the UTC date the run starts."""
    if fam == "MLB":
        return f"mlb_MLB_{ny_date(start).isoformat()}.json"
    return {"NFL": "nfl_predictions_", "SOCCER": "soccer_PL_"}[fam] + f"{utc(at).date().isoformat()}.json"


def export_candidates(fam: str, start: datetime, at: datetime, run_id: str) -> list[str]:
    """The file the run's export step writes (its `--out {export_out}`). Addendum 40 item 2 (ARCHITECT 2026-10-11):
    "A closing run does not write, replace or move the family's slate file. [...] The run's export step writes
    outside exports/. [...] The full export is kept under logs/ with the run id, as R6 names a moved export today":
    logs/<run id>.<the slate file's name>."""
    return [f"logs/{run_id}.{slate_name(fam, start, at)}"]


def _export_path_refusal(fam: str, start: datetime, at: datetime, run_id: str) -> str | None:
    """#442 (ARCHITECT 2026-10-12, addendum 44 item 8): "A run whose export path already exists does not start: a
    receipted refusal before any step, as R4 and R5 are. Nothing a run kept is opened for writing a second time."
    Two runs of one family entering in one UTC second share a run id, so the second would overwrite the first's kept
    export. Read under the lock, with the run's own start (the path names it), before the backup and every step."""
    out_ = export_candidates(fam, start, at, run_id)[0]
    path = c.REPO / out_
    if path.exists() or path.is_symlink():
        return (f"the export path {out_} already exists (a run of this family entered in the same second, run id "
                f"{run_id}): nothing a run kept is opened for writing a second time")
    return None


CLOSING_FILE_DIR = "exports"


def closing_name(fam: str, start: datetime) -> str:
    """Addendum 40 item 2: exports/closing_<FAMILY>_<start>.json, <start> the run's start time in UTC written
    2026-10-11T1700Z (no colon: the mirror's kind is then closing_<FAMILY>)."""
    return f"closing_{fam}_{utc(start):%Y-%m-%dT%H%MZ}.json"


def closing_doc(doc: dict, fam: str, start: datetime, run_id: str, page_ids: list, called: list[dict],
                books_why: dict | None = None) -> dict:
    """ONE CLOSING, ONE PAGE, ONE FILE (ARCHITECT 2026-10-11, addendum 40 item 2): "the games on its page and no
    other, each row as the run's export gave it, and a closing block naming the family, the start time, the run id
    and the match ids." The games on its page are the run's Desk rows, the PASS games included; a called-off game is
    named in the closing block and has no row. "Everything else in the document is the export's own (exported_at,
    git_sha, desk_meta); count is the rows kept." Pure.

    THE MLB BOOKS LINE (ARCHITECT 2026-10-16, addendum 97 item 2(a), #550/#514): "the closing file's MLB books line
    says WHY when n is 0: "books: provider listed the game, no odds" (from the sync step's own answer, which the run
    already has) rather than a bare count; the closing-file schema gains that string field (null when books exist)".
    For MLB, given the run's answers (`books_why`, {match id: answer}), the closing block's `books` holds one entry a
    row: {match_id, n (the row's market.bookmaker_count), why}; why is null when n > 0, else the sync step's answer
    for the game, else its run-level answer (RUN_KEY: the fallback never ran), else BOOKS_NO_ANSWER. The rows stay as
    the export gave them."""
    keep = set(page_ids)
    rows = [r for r in doc.get("predictions") or [] if r.get("match_id") in keep]
    out = {k: v for k, v in doc.items() if k != "predictions"}
    out["count"] = len(rows)
    out["predictions"] = rows
    out["closing"] = {"family": fam, "start": iso_z(start), "run_id": run_id,
                      "match_ids": [r.get("match_id") for r in rows],
                      "called_off": [{"match_id": x["match_id"], "status": x["status"]} for x in called]}
    if fam == "MLB" and books_why is not None:
        books = []
        for r in rows:
            n = int((r.get("market") or {}).get("bookmaker_count") or 0)
            books.append({"match_id": r.get("match_id"), "n": n,
                          "why": None if n > 0 else (books_why.get(r.get("match_id"))
                                                     or books_why.get(RUN_KEY) or BOOKS_NO_ANSWER)})
        out["closing"]["books"] = books
    return out


def write_closing_file(doc: dict, name: str, mtime: float | None = None) -> dict:
    """Write exports/<name> atomically (a temporary name beside it, then a rename). {file, sha256[, replaced]} or
    {file, error}.

    THE FILE OF A SECOND PAGE (ARCHITECT 2026-10-11, addendum 41 item 3): "Where a start time is paged a second time,
    the later page is its close. Its file replaces the earlier one. The earlier file is kept under logs/, named with
    its run id as the run's export is, and the later receipt names the file it replaced and its sha256." "Where the
    earlier file cannot be moved, the write is refused and receipted as today (closing_file_failed) and the earlier
    file stands." The earlier file is kept by a hard link at logs/<its run id>.<name> made BEFORE the rename, so the
    earlier bytes are never without a name; a kept name already taken, or an earlier file that names no run id, is a
    refusal (nothing is overwritten)."""
    rel = f"{CLOSING_FILE_DIR}/{name}"
    dest = c.REPO / CLOSING_FILE_DIR / name
    tmp = dest.with_name(f".{name}.tmp")
    replaced, kept = None, None
    try:
        c.refuse_under_data(dest.parent)
        if dest.exists() or dest.is_symlink():
            try:
                old_run = (json.loads(dest.read_text()).get("closing") or {}).get("run_id")
            except (OSError, ValueError, AttributeError):
                old_run = None
            if not old_run or not re.fullmatch(r"[A-Za-z0-9_.:-]+", str(old_run)) or dest.is_symlink():
                return {"file": rel, "error": "exists: the earlier closing file names no run id it can be kept "
                                              "under; it cannot be moved and stands"}
            kept = c.REPO / "logs" / f"{old_run}.{name}"
            c.refuse_under_data(kept.parent)
            if kept.exists() or kept.is_symlink():
                return {"file": rel, "error": f"exists: logs/{kept.name} is already taken; the earlier closing "
                                              "file cannot be moved and stands"}
            replaced = {"file": rel, "sha256": _sha256(dest), "run_id": old_run, "kept_as": f"logs/{kept.name}"}

        def fill(t: Path) -> None:
            t.write_text(json.dumps(doc, indent=2))
            if mtime is not None:
                os.utime(t, (mtime, mtime))
        place_file(dest, fill, kept)
        return {"file": rel, "sha256": _sha256(dest), **({"replaced": replaced} if replaced else {})}
    except (OSError, SystemExit, TypeError, ValueError) as e:
        try:
            tmp.unlink()
        except OSError:
            pass
        return {"file": rel, "error": c.redact(f"{type(e).__name__}: {e}")[:300]}


def place_file(dest: Path, fill, kept: Path | None = None) -> None:
    """The closing file's write (addendum 40 item 2; addendum 41 item 3), the one path the slate's file takes too
    (addendum 133 item 3(a): "the way the closing writes its closing file (a hard link, then the rename over the
    name)"): the new file takes a temporary name beside `dest` (`fill(tmp)` puts it there: the closing writes its
    document, the slate hard-links its kept export), the earlier file, where `kept` names where, is kept first by a
    hard link, then the rename over the name. Raises on any failure, the temporary name removed by the caller."""
    tmp = dest.with_name(f".{dest.name}.tmp")
    dest.parent.mkdir(parents=True, exist_ok=True)
    fill(tmp)
    if kept is not None:
        kept.parent.mkdir(parents=True, exist_ok=True)
        os.link(dest, kept)                   # refuses an existing name: the earlier file is never overwritten
        try:
            os.replace(tmp, dest)
        except OSError:
            kept.unlink()                     # the earlier file still stands at its own name
            raise
    else:
        os.replace(tmp, dest)


def resolve_steps(fam: str, start: datetime, covers: list[dict], run_start: datetime,
                  run_id: str = "RUN") -> list[list[str]]:
    """The family's closing chain with its run-time values. MLB: {today} = the first pitch's NY date (A1 of #370),
    {match_ids} = the covered games (A1 of addendum 23: the schedule read names them). NFL / SOCCER (C3):
    {match_ids} = the covered games (the odds and the injuries steps); the schedule read (A1 as amended, addendum 25
    2(i): NFL takes the SOCCER form): {start_day}/{end_day} = the UTC dates of the first and last covered start (one
    read per UTC day; an identical second read is dropped), {start_day_ids}/{end_day_ids} = that day's covered
    games. {export_out} (addendum 40 item 2): the export step's file, logs/<run id>.<the slate file's name>."""
    chain = FAMILIES[fam]["chain"]
    ids = ",".join(str(g["match_id"]) for g in sorted(covers, key=lambda g: g["match_id"]))
    out_ = export_candidates(fam, start, run_start, run_id)[0]
    if fam == "MLB":                  # A1: the schedule read names the covered games
        return sp_run.resolve(chain, {"match_ids": ids, "export_out": out_}, ny_date(start))
    last = max(g["start"] for g in covers)

    def day_ids(day):                 # A1: each by-date read names that UTC day's covered games
        return ",".join(str(g["match_id"]) for g in sorted(covers, key=lambda g: g["match_id"])
                        if utc(g["start"]).date() == day)
    v = {"start_day": utc(start).date().isoformat(), "end_day": last.date().isoformat(), "match_ids": ids,
         "start_day_ids": day_ids(utc(start).date()), "end_day_ids": day_ids(last.date()), "export_out": out_}
    out: list[list[str]] = []
    for st in sp_run.resolve(chain, v, utc(start).date()):
        if not out or st != out[-1]:
            out.append(st)
    return out


def plan(fam: str, now: datetime, start: str | None) -> dict:
    """The target start time and the games it covers, from the stored schedule (read-only). `refused` when there is
    nothing to close. A manual run with no --start targets the next unstarted start within 90 minutes (#370, accepted
    as built); a watch-started run passes its start time."""
    games = with_called_off(fam, schedule(fam, now), now)      # Codex 4233123800
    if start:
        s = parse_utc(start)
        if not any(g["start"] == s and not started(g, now) for g in games):
            return {"refused": f"no unstarted {fam} game at {FAMILIES[fam]['noun']} {iso_z(s)} — nothing to close",
                    "games": games}
    else:
        win = [g for g in games if abs(minutes_to(g["start"], now)) <= MANUAL_WINDOW_MIN]
        live = [g for g in win if not started(g, now)]
        if not live:
            why = ("every game in the window has started" if win else
                   f"no {fam} game starting within {MANUAL_WINDOW_MIN} minutes")
            return {"refused": f"A4: {why} — nothing to close", "games": games}
        s = live[0]["start"]
    covers = cover(games, s, now)
    return {"start": iso_z(s), "start_et": et(s), "covers": covers, "games": games}


def _covers_rec(covers: list[dict]) -> list[dict]:
    return [{"match_id": g["match_id"], "start": iso_z(g["start"]), "game": f"{g['away']} @ {g['home']}"}
            for g in covers]


# --------------------------------------------------------------------------------- failed-run notification --
# ARCHITECT 2026-10-08 (#370 READ): "Silence must never mean a closing that did not happen. Every watch-started run
# that does not succeed posts one notification: the first pitch, what failed or why it refused, and for a failed
# attempt its number out of three. The third says no further attempt will run for that first pitch. A manual run
# prints to the console, as now. These notifications are best effort [...]" For every family (C4); on the laptop's
# screen and, where the card topic is set, the phone.

def _start_label(fam: str, start: str | None) -> str:
    try:
        return f"{fam} {et(parse_utc(start))}" if start else f"{fam} (no start time)"
    except (TypeError, ValueError):
        return f"{fam} start {start!r}"


def failure_text(fam: str, start: str | None, failed: str | None = None, refused: str | None = None,
                 attempt: int | None = None) -> str:
    head = f"Closing {_start_label(fam, start)}: "
    if refused:
        return head + f"REFUSED: {refused}"
    t = head + f"FAILED: {failed} · attempt {attempt}/{MAX_ATTEMPTS}"
    if attempt is not None and attempt >= MAX_ATTEMPTS:
        t += f" · no further attempt will run for this {FAMILIES.get(fam, {}).get('noun', 'start')}"
    return t


def notify_failure(text: str, fam: str = "", title: str | None = None) -> dict:
    """Best effort, both channels: the result is recorded in the receipt and changes nothing else.
    ARCHITECT 2026-10-12, addendum 47 item 7(a): "A failure, a miss or a refusal that neither the screen nor the card
    topic took goes once through the operator topic, as sp_notify's page does, and its receipt names the channel
    that took it. The watch's exit status does not change." On the host the screen posts nothing (not macOS), so an
    unset or malformed card topic, or a card page ntfy did not accept, would otherwise reach nobody. `channel`: the
    channel(s) that took it ("card", "screen", "card+screen", "operator"), or None. `title`: the slate stage's
    notices pass "<FAMILY> slate"; every closing notice keeps "<FAMILY> closing"."""
    title = title or f"{fam} closing".strip()
    text = f"{text}\n{machine_line()}"           # addendum 45: every closing page ends naming the machine
    try:
        res = notify(text, title=title)
    except Exception as e:  # noqa: BLE001
        res = {"posted": False, "text": text, "error": f"{type(e).__name__}: {e}"[:200]}
    try:
        ph = page_phone(title, text, "high") if not _card_topic_refusal() else {"accepted": False,
                                                                                 "skipped": f"{CARD_TOPIC} unset"}
    except Exception as e:  # noqa: BLE001
        ph = {"accepted": False, "error": type(e).__name__}
    took = [ch for ch, ok in (("card", ph.get("accepted") is True), ("screen", res.get("posted") is True)) if ok]
    op = None
    if not took:                      # addendum 47 item 7(a): the operator topic, once, when neither channel took it
        try:
            op = page_operator(title, text)
        except Exception as e:  # noqa: BLE001
            op = {"accepted": False, "error": type(e).__name__}
        if op.get("accepted") is True:
            took = ["operator"]
    return {"text": text, "posted": res.get("posted"),
            **({"skipped": res["skipped"]} if res.get("skipped") else {}),
            **({"error": res["error"]} if res.get("error") else {}), "phone": ph,
            **({"operator": op} if op is not None else {}), "channel": "+".join(took) or None}


def _refuse(why: str, fam: str, start: str | None, base: dict, trigger: str, dry_run: bool) -> int:
    """A receipted refusal (exit 2). Reading 7 (ARCHITECT, addendum 22 item 4): "A refusal is receipted and notified
    once for a first pitch and a reason. The same refusal on a later tick for that first pitch writes nothing and
    posts nothing." """
    print(("DRY RUN closing-run: would REFUSE: " if dry_run else f"✗ closing-run {fam} REFUSED: ") + why)
    if dry_run:
        return 2
    if trigger == "watch" and any(r.get("family") == fam and r.get("start") == start and r.get("refused") == why
                                  for r in receipts(("closing",))):
        return 2                      # reading 7: already receipted and notified for this start time and reason
    rec = {**base, "start": start, "exit": 2, "refused": why, "steps": [], "export": None, "desk_rows": [],
           "push": None}
    if trigger == "watch":
        rec["failure_notification"] = notify_failure(failure_text(fam, start, refused=why), fam)
    c.append_receipt(rec)
    return 2


def _move_export(rec: dict, run_id: str) -> None:
    """R6: "the export it wrote is moved out of exports/ into logs/, named with the run id, and the receipt says
    where." """
    if not rec.get("export"):
        return
    if not str(rec["export"]).startswith("exports/"):      # addendum 40 item 2: written under logs/, never exports/
        print(f"· export kept in logs/: {rec['export']} (never in exports/: no call left behind)")
        return
    src = c.REPO / rec["export"]
    if not src.is_file():
        return
    dest = c.REPO / "logs" / f"{run_id}.{src.name}"
    if dest.exists() or dest.is_symlink():             # #442: nothing a run kept is written a second time
        rec["export_move_error"] = f"logs/{dest.name} already exists: kept, not replaced; the export stays at {rec['export']}"
        print(f"✗ export NOT moved: {rec['export_move_error']}")
        return
    try:
        c.refuse_under_data(dest.parent)
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(src, dest)
        rec["export_moved_to"] = str(dest.relative_to(c.REPO))
        print(f"· export moved out of exports/: {rec['export_moved_to']} (no call left behind)")
    except (OSError, SystemExit) as e:
        rec["export_move_error"] = c.redact(f"{type(e).__name__}: {e}")[:300]
        print(f"✗ export NOT moved: {rec['export_move_error']}")


def record_miss(fam: str, start: str, reason: str, detail: str | None = None, text: str | None = None) -> dict | None:
    """kind closing_miss: a closing that did not run. Notified (both channels, best effort) and receipted. B6
    (ARCHITECT 2026-10-09, addendum 23, reading 17 RULED): "A miss is receipted and notified once for a start time and
    a reason, as a refusal is. An unreachable MLB feed is one miss for that first pitch, not one a minute. The watch
    keeps trying, silently." A miss already receipted for this start time and reason: nothing written or posted
    (None)."""
    if any(r.get("family") == fam and r.get("start") == start and r.get("reason") == reason
           for r in receipts(("closing_miss",))):
        return None
    text = text or f"Closing {_start_label(fam, start)}: MISSED: {reason}"
    res = notify_failure(text, fam)
    return c.append_receipt({"kind": "closing_miss", "family": fam, "start": start, "reason": reason,
                             **({"detail": detail} if detail else {}), "notified": res})


def schedule_reads(steps: list[list[str]]) -> int:
    """How many of the resolved steps are the schedule read (A1): the leading `sync-matches ... --match-ids` calls."""
    n = 0
    while n < len(steps) and steps[n][0] == "sync-matches" and "--match-ids" in steps[n]:
        n += 1
    return n


def leave_moved(rec: dict, covers: list[dict], s: datetime) -> list[dict]:
    """C (addendum 23): a covered game the schedule read moved off the run's start leaves the run, receipted with both
    times (`moved`; `covers` = the games left). Codex 4232307577 (addendum 25 2(ii)): taken as soon as the schedule
    read has run, before a later step can fail, so a failed attempt's receipt never counts a moved game as covered
    (three such attempts would close its new start time for good). Returns the games left."""
    off = called_off(covers)          # addendum 25 item 3: a cancelled or postponed game stays, on a line of its own
    if off:
        rec["called_off"] = off
        for x in off:
            print(f"· {x['status'].lower()}: match {x['match_id']} ({x['game']}): on the page with its status")
    gone_off = {x["match_id"] for x in off}
    moved = start_moved([g for g in covers if g["match_id"] not in gone_off], s)
    if moved:
        rec["moved"] = moved
        gone = {m["match_id"] for m in moved}
        for m in moved:
            print(f"· start moved: match {m['match_id']} ({m['game']}) left the run: covered at {m['covered_start']} "
                  f"(run start {m['target']}), stored start now {m['stored_start'] or 'none (no stored row)'}")
        covers = [g for g in covers if g["match_id"] not in gone]
        rec["covers"] = _covers_rec(covers)
    return covers


def note_export(rec: dict, fam: str, s: datetime, held: datetime, wall0: float) -> None:
    """Addendum 25 2(iii): "A closing receipt records the sha256 of the export it wrote". Whatever the outcome: the
    family's export file this run's own step wrote (mtime at or after the run's start), before R6 can move it."""
    try:
        written = [p for p in export_candidates(fam, s, held, rec["run_id"])
                   if (c.REPO / p).is_file() and (c.REPO / p).stat().st_mtime >= wall0]
        if written:
            rec["export_written"] = {"file": written[-1], "sha256": _sha256(c.REPO / written[-1])}
    except OSError as e:
        rec["export_written"] = {"error": f"{type(e).__name__}"}


def _closing(rec: dict, fam: str, s: datetime, covers: list[dict], folder: Path, held: datetime, t0: float,
             run_id: str, prev: dict, wall0: float | None = None) -> None:
    """The run's body. The caller holds the chain lock (R3) and writes the receipt line afterwards, still under it.
    `held` is the run's start (380.4: the moment it holds the lock)."""
    if wall0 is None:         # the export must be written by this run's own step (1s: coarse filesystem mtimes)
        wall0 = _WALL() - 1.0
    today_ny = ny_date(held)
    have = todays_backup(folder, today_ny)
    if have:
        rec["backup"] = {"file": str(have), "taken": False}
        print(f"· backup dated {today_ny}: {have}")
    else:
        rec["backup"] = take_backup(folder, today_ny)
        b = rec["backup"]
        print(f"· backup taken: {b['file']} copied={b['copied']} integrity={b['integrity']} opens={b['opens']} "
              f"hash={'yes' if b['hash_file'] else 'no'}")
    if rec["backup"].get("taken") and not rec["backup"].get("ok"):
        rec["failed"] = "backup"                  # 380.3: any part failing fails the run before the first step
        print(f"✗ backup failed: {rec['backup'].get('error')} — no step runs"
              + (f"; set aside: {', '.join(rec['backup']['set_aside'])}" if rec["backup"].get("set_aside") else ""))
        return
    steps = resolve_steps(fam, s, covers, held, run_id)
    rec["planned_steps"] = len(steps)
    logs = c.REPO / "logs"            # addendum 40 item 2: the export step writes here, never into exports/
    c.refuse_under_data(logs)
    logs.mkdir(parents=True, exist_ok=True)
    chain = FAMILIES[fam]["chain"]
    reads = schedule_reads(steps)
    for i, st in enumerate(steps, 1):
        line = f"python cli.py {' '.join(st)}"
        print(f"\n=== [{chain} {i}/{len(steps)}] {line}", flush=True)
        rc, tail, dur = run_step(st, run_id)
        srec = {"step": i, "command": line, "exit": rc, "seconds": round(dur, 1)}
        said = reported_failure(st, tail) if rc == 0 else None
        if said:                      # exit 0, but the step said it failed (Codex on #370)
            srec["detected_failure"] = said
        nob = no_book_odds(st, tail)
        if nob:                       # addendum 97 item 2(a): the provider's answer, for the closing file's books
            srec["no_book_odds"] = {str(k): v for k, v in sorted(nob.items(), key=lambda kv: str(kv[0]))}
            rec.setdefault("books_why", {}).update(nob)
        empty = empty_answers(st, tail)
        if empty:                     # addendum 40 item 4: "in its console and in the run's receipt"
            srec["empty_answers"] = empty
            rec["injury_lists_empty"] = sorted(set(rec.get("injury_lists_empty", [])) | set(empty))
            print(f"· injury read answered empty (stored empty, read as unread): {'; '.join(empty)}")
        if rc != 0:
            srec["tail"] = tail[-3:]  # e.g. strict mode's "✗ STRICT: ..." lines (addendum 22)
        rec["steps"].append(srec)
        if i <= reads and (i == reads or rc != 0 or said):
            covers = leave_moved(rec, covers, s)       # Codex 4232307577: right after the schedule read
        if rc != 0 or said:
            rec["failed"] = f"step {i}" + (" (reported failure, exit 0)" if said else "")
            if st[0] == "sync-injuries" and "--strict" in st and rc != 0:
                rec["failed"] += " (strict: a read it needed failed)"
            elif i <= reads and rc != 0:
                rec["failed"] += " (schedule read: a covered game the provider did not answer, A1)"
            return
        if i == reads and not covers:
            rec["failed"] = "start moved"
            print("✗ start moved: no game is left in the run — no further step, nothing pushed or paged")
            return
    cands = export_candidates(fam, s, held, run_id)
    written = [p for p in cands if (c.REPO / p).is_file() and (c.REPO / p).stat().st_mtime >= wall0]
    if not written:
        rec["failed"] = "export not written"
        return
    rec["export"] = written[-1]
    doc = json.loads((c.REPO / rec["export"]).read_text())
    if not doc.get("desk_meta"):
        rec["failed"] = "export carries no desk calls"
        return
    # R1: ONE started test, taken when the steps have finished, on the stored schedule re-read now (the schedule read
    # step synced it).
    done = held + timedelta(seconds=time.time() - t0)
    rec["completed_at"] = iso_z(done)
    games = schedule(fam, held)
    started_ids = {g["match_id"] for g in games if started(g, done)}
    why = target_started(games, s, done)
    if why:
        rec["failed"] = "target started"
        rec["started"] = why
        print(f"✗ the target {FAMILIES[fam]['noun']} {et(s)} has started ({why}) — no closing for it; a started "
              "game is never retried")
        return
    off = rec.get("called_off") or []
    cover_ids = {g["match_id"] for g in covers} - {x["match_id"] for x in off}
    rows = desk_rows(doc, cover_ids, done, started_ids, fam)
    missing = missing_from_export(doc, covers, done, games)
    if missing:
        rec["failed"] = "missing from export"
        rec["missing"] = missing
        print("✗ missing from export: " + ", ".join(
            f"match {m['match_id']} ({m['start_et']} {m['away']} @ {m['home']})" for m in missing))
        return
    unread: list = []
    stale = stale_prices(doc, rows, held, unread)
    if unread:                        # A5: listed in the receipt, fails nothing
        rec["stale_legs_not_read"] = unread
        for u in unread:
            print(f"· stale Kalshi leg the Desk did not read (listed, not a failure): match {u['match_id']} "
                  f"({u['game']}) {u['leg']} captured {u['captured_at'] or 'never'}")
    if stale:                         # R2: the run checks its prices, not a step's console
        rec["failed"] = "stale prices"
        rec["stale"] = stale
        for s_ in stale:
            print(f"✗ stale prices: match {s_['match_id']} ({s_['start_et']} {s_['game']}): {s_['price']} "
                  f"captured {s_['captured_at'] or 'never (no stored row)'}, before the run's start {s_['run_start']}")
        return
    if FAMILIES[fam]["starters"]:
        st_ = stale_starters(doc, rows, games, held)
        if st_:                       # 380.1: a failed attempt, retried like stale prices; not a refusal
            rec["failed"] = "stale starters"
            rec["stale_starters"] = st_
            for x in st_:
                print(f"✗ stale starters: match {x['match_id']} ({x['start_et']} {x['game']}): {x['side']} starter "
                      f"({x['team']}) refreshed {x['refreshed_at'] or 'never (no stored row)'}, before the run's "
                      f"start {x['run_start']}")
            return
    rec["desk_rows"] = [{k: x[k] for k in ("match_id", "start", "call", "call_text", "pick", "units", "exec_edge_pp",
                                           "hold", "value_shadow", "quarantine_shadow", "starters_listed",
                                           "unresolved_injuries", "injuries_empty")}
                       for x in rows]   # call_text: 26 2(b); injuries_empty: addendum 40 item 4
    print(f"\n=== {fam} closing summary · {len(rows)} game(s) starting {et(s)} to "
          f"{utc(s + timedelta(minutes=COVER_MIN)).astimezone(NY):%H:%M} ET")
    for x in rows:
        print(summary_block(x))
    # B1 (ARCHITECT 2026-10-09, addendum 23): "The page goes out as soon as the run's own checks have passed. The
    # mirror push follows. A closing whose page went out is not run again for a failed push: the failure is receipted
    # and notified, and the next push from this machine carries the file." C5/C6 + B2: ONE page per run, on the phone
    # (ntfy card topic, three tries ten seconds apart), then the laptop's screen (recorded, changes nothing).
    at = held + timedelta(seconds=time.time() - t0)
    title, body, high = page_text(fam, s, at, rows, prev, off)
    priority = "high" if high else "default"
    print(f"\n--- page ({priority}) ---\n{body}\n---")
    tries = []
    for n in range(1, PAGE_TRIES + 1):
        try:
            ph = page_phone(title, body, priority)
        except Exception as e:  # noqa: BLE001
            ph = {"accepted": False, "error": type(e).__name__}
        tries.append(ph)
        if ph.get("accepted") is True:
            break
        if n < PAGE_TRIES:
            page_sleep(PAGE_RETRY_S)
    rec["page"] = {"title": title, "priority": priority, "lines": body.count("\n") + 1, "text": body,
                   "phone": ph, "tries": len(tries), "at": iso_z(held + timedelta(seconds=time.time() - t0))}
    if ph.get("accepted") is not True:
        rec["page"]["phone_tries"] = tries
        rec["failed"] = "page"        # nothing pushed: the watch retries the closing
        return
    try:
        scr = notify(body, title=title)
    except Exception as e:  # noqa: BLE001
        scr = {"posted": False, "text": body, "error": f"{type(e).__name__}: {e}"[:200]}
    rec["page"]["screen"] = {"posted": scr.get("posted"),
                             **({"skipped": scr["skipped"]} if scr.get("skipped") else {}),
                             **({"error": scr["error"]} if scr.get("error") else {})}
    rec["exit"] = 0                   # the page went out: the closing happened, whatever the push does
    # ONE CLOSING, ONE PAGE, ONE FILE (ARCHITECT 2026-10-11, addendum 40 item 2): "It is written when the phone has
    # accepted the page and before the push, so the push carries it. A write that fails is receipted and notified as a
    # failed push is, and the closing is not run again."
    name = closing_name(fam, s)
    try:
        cdoc = closing_doc(doc, fam, s, run_id, [x["match_id"] for x in rows], off,
                           books_why=rec.get("books_why", {}) if fam == "MLB" else None)
        cf = write_closing_file(cdoc, name)
    except Exception as e:  # noqa: BLE001 - receipted and notified, never a retry (the page went out)
        cf = {"file": f"{CLOSING_FILE_DIR}/{name}", "error": c.redact(f"{type(e).__name__}: {e}")[:300]}
    rec["closing_file"] = cf
    if cf.get("error"):
        rec["closing_file_failed"] = True
        rec["closing_file_failure_notification"] = notify_failure(
            f"Closing {_start_label(fam, rec.get('start'))}: PAGED; closing file NOT written ({cf['file']}) "
            "· not run again", fam)
        print(f"✗ closing file NOT written: {cf['error']} — receipted and notified; the closing is not run again")
    else:
        print(f"· closing file: {cf['file']} ({len(rows)} row(s), sha256 {cf['sha256'][:12]})")
        if cf.get("replaced"):
            r = cf["replaced"]
            print(f"· a second page for this start time: it replaced {r['file']} of run {r['run_id']} (sha256 "
                  f"{r['sha256'][:12]}), kept as {r['kept_as']}")
    rec["push"] = push_mirror()
    print(f"· exports mirror ({mirror_role()}, closing): exit {rec['push']['exit']} "
          f"{' | '.join(rec['push']['tail'])}")
    if rec["push"].get("exit") != 0:  # B1: receipted and notified; never a retry (the page went out)
        rec["push_failed"] = True
        rec["push_failure_notification"] = notify_failure(
            f"Closing {_start_label(fam, rec.get('start'))}: PAGED; mirror push FAILED (exit {rec['push']['exit']}) "
            "· not run again · the next push from this machine carries the file", fam)
        print("✗ mirror push failed after the page went out: receipted and notified; the closing is not run again "
              "(the next push from this machine carries the file)")


def _finish(rec: dict, fam: str, trigger: str, run_id: str, t0: float) -> None:
    """R6, the failed-run notification and THE receipt line. Called with the chain lock held (R3)."""
    if rec.get("failed") in OWN_CHECK_FAILURES:
        _move_export(rec, run_id)
    if rec["exit"] != 0 and trigger == "watch":
        rec["failure_notification"] = notify_failure(
            failure_text(fam, rec.get("start"), failed=rec.get("failed"), attempt=rec.get("attempt")), fam)
    rec["seconds"] = round(time.time() - t0, 1)
    c.append_receipt(rec)


def _failed_exit(trigger: str) -> int:
    """Addendum 45 P3 (ARCHITECT 2026-10-12): "What the watch has already receipted and notified leaves with a status
    of its own; the unit counts that status and a refusal's as success, and its failure path is for what the process
    could not report itself." A watch-started run that failed or missed, once its receipt line is written and its
    notification posted (best effort), exits NOTIFIED (3). A run by hand notifies nothing and keeps exit 1."""
    return NOTIFIED if trigger == "watch" else 1


def _under_lock(fam: str, p: dict, base: dict, folder: Path, held: datetime, trigger: str, run_id: str) -> int:
    """380.4 (ARCHITECT): "A run decides under the lock. Once it holds the chain lock it reads the clock and its
    receipts again. A watch-started run whose start time by then has a successful closing, or three attempts, ends
    there: no step, no push, no page. It is receipted as superseded, which is neither an attempt nor a refusal, and
    it posts nothing. A watch-started run that gets the lock inside T-5 does not start: receipted and notified as a
    miss. The attempt number is taken under the lock. The run's start, for the price check and the starter check, is
    the moment it holds the lock." """
    start = p["start"]
    s = parse_utc(start)
    if trigger == "watch":
        st = closing_state(fam, start)
        if st["success"] or st["attempts"] >= MAX_ATTEMPTS:
            c.append_receipt({**base, "start": start, "superseded": True, "exit": 0, "lock_at": iso_z(held),
                              "why": "a successful closing" if st["success"] else f"{st['attempts']} attempts"})
            print(f"· superseded: {fam} {et(s)} already has "
                  + ("a successful closing" if st["success"] else f"{st['attempts']} attempts") + " — nothing run")
            return 0
        if minutes_to(s, held) < NO_ATTEMPT_INSIDE_MIN:
            record_miss(fam, start, "the lock came inside T-5", detail=f"lock held at {iso_z(held)}")
            print(f"✗ {fam} {et(s)}: the lock came inside T-5 — no attempt; miss recorded")
            return NOTIFIED
    why = _export_path_refusal(fam, s, held, run_id)
    if why:                           # #442 (addendum 44 item 8): before any step, as R4 and R5 are
        return _refuse(why, fam, start, base, trigger, dry_run=False)
    games = with_called_off(fam, schedule(fam, held), held)     # Codex 4233123800
    covers = cover(games, s, held)
    rec = {**base, "start": start, "start_et": et(s), "covers": _covers_rec(covers or p["covers"]),
           "attempt": closing_state(fam, start)["attempts"] + 1, "queued_at": base["queued_at"],
           "run_start": iso_z(held), "backup": None, "steps": [], "export": None, "desk_rows": [], "push": None,
           "exit": 1}
    if fam == "MLB":
        rec["date_ny"] = ny_date(s).isoformat()
    print(f"=== closing-run {fam} · {FAMILIES[fam]['noun']} {et(s)} · covers {len(rec['covers'])} game(s) · attempt "
          f"{rec['attempt']}", flush=True)
    t0 = time.time()
    if not any(g["start"] == s for g in covers):     # the target started while the run waited for the lock (R1)
        rec["failed"] = "target started"
        rec["started"] = f"no unstarted game at {iso_z(s)} when the run held the lock ({iso_z(held)})"
        _finish(rec, fam, trigger, run_id, t0)
        print(f"✗ closing-run {fam} FAILED (target started)")
        return _failed_exit(trigger)
    rec["run_start_wall"] = _WALL()   # addendum 26 2(b): an export written after this moment comes before its calls
    wall0 = rec["run_start_wall"] - 1.0   # the export must be written by this run's own step (1s: coarse mtimes)
    try:                      # addendum 25 2(iii): the last calls found before the first step, every game found
        lc = last_calls(fam, held)
        rec["last_calls"] = {str(k): v for k, v in sorted(lc.items(), key=lambda kv: str(kv[0]))}
    except Exception as e:  # noqa: BLE001 - unreadable: no 'was', and the receipt says so (its chain is not followed)
        lc = {}
        rec["last_calls_error"] = c.redact(f"{type(e).__name__}: {e}")[:200]
    prev = {k: v["call"] for k, v in lc.items()}
    try:
        _closing(rec, fam, s, covers, folder, held, t0, run_id, prev, wall0)
    except Exception as e:  # noqa: BLE001 - the receipt line is written either way (A2)
        rec["failed"] = rec.get("failed") or "error"
        rec["error"] = c.redact(f"{type(e).__name__}: {e}")[:300]
    note_export(rec, fam, s, held, wall0)
    _finish(rec, fam, trigger, run_id, t0)
    if rec["exit"] != 0:
        print(f"✗ closing-run {fam} FAILED ({rec.get('failed')}{': ' + rec['error'] if rec.get('error') else ''}) — "
              + {"page": f"ntfy did not accept the page in {PAGE_TRIES} tries; nothing pushed, the export stays "
                         "under logs/, the watch retries",
                 **{k: "nothing pushed or paged; the export stays in logs/ (never in exports/)"
                    for k in OWN_CHECK_FAILURES},
                 "start moved": "no further step ran after the schedule read; nothing exported, pushed or paged"}.get(
                  rec.get("failed"), "nothing exported, pushed or paged after the failure"))
        return _failed_exit(trigger)
    print(f"✓ closing-run {fam}: {len(rec['steps'])}/{rec.get('planned_steps')} steps · {rec['export']} · "
          f"{len(rec['desk_rows'])} Desk row(s) · page accepted · closing file "
          + ("NOT written (receipted and notified)" if rec.get("closing_file_failed") else
             (rec.get("closing_file") or {}).get("file", "?"))
          + f" · push exit {rec['push']['exit']}"
          + (" (FAILED: receipted and notified)" if rec.get("push_failed") else ""))
    return 0


def run(family: str = "MLB", start: str | None = None, dry_run: bool = False, trigger: str = "operator",
        now: datetime | None = None) -> int:
    fam = family.upper()
    if fam not in FAMILIES:
        print(f"✗ no closing run for {family!r}: the families are {', '.join(FAMILIES)} (C1)")
        return 2
    now = utc(now or clock())
    t_entry = time.time()
    chain = FAMILIES[fam]["chain"]
    run_id = f"{now:%Y%m%dT%H%M%SZ}-{chain}"
    base = {"kind": "closing", "family": fam, "run_id": run_id, "trigger": trigger, "queued_at": iso_z(now)}
    folder = backup_folder()
    for check in refusal_checks(fam, folder, start):
        why = check()
        if why:
            return _refuse(why, fam, start, base, trigger, dry_run)
    try:
        p = plan(fam, now, start)
    except (FileNotFoundError, sqlite3.Error) as e:
        p = {"refused": f"no stored schedule readable ({type(e).__name__})", "covers": []}
    if dry_run:
        print(f"DRY RUN closing-run {fam} (touches nothing: no step, no backup, no receipt, no push, no page)")
        if p.get("refused"):
            print(f"  would REFUSE: {p['refused']}")
            return 0
        s = parse_utc(p["start"])
        today_ny = ny_date(now)
        have = todays_backup(folder, today_ny)
        print(f"  {FAMILIES[fam]['noun']} {p['start_et']} ({p['start']}) · T-{minutes_to(s, now):.0f}m · covers "
              f"{len(p['covers'])} game(s) starting within {COVER_MIN} minutes after it:")
        for g in p["covers"]:
            print(f"    match {g['match_id']}  {et(g['start'])}  {g['away']} @ {g['home']}  [{g['status']}]")
        print(f"  lock: {c.lock_path()} (waits while held; held from the backup check until the receipt line)")
        print("  backup: " + (f"exists {have}" if have else
                              f"none dated {today_ny} in {folder} → would take sports_{today_ny}.db (.backup API), "
                              "check integrity, open, hash, hash file"))
        why = _export_path_refusal(fam, s, now, run_id)
        if why:
            print(f"  would REFUSE: {why}")
            return 0
        for i, st in enumerate(resolve_steps(fam, s, p["covers"], now, run_id), 1):
            print(f"  {i}. python cli.py {' '.join(st)}")
        print(f"  export: {' or '.join(export_candidates(fam, s, now, run_id))} · then, once the page is accepted, "
              f"{CLOSING_FILE_DIR}/{closing_name(fam, s)} · checks: started (R1), start moved (C), "
              "missing, prices (R2, A5 legs)"
              + (", starters (380.1)" if FAMILIES[fam]["starters"] else "")
              + " · page: ntfy card topic (3 tries) + screen · then push: exports_mirror.py push --role "
                f"{mirror_role()} --label closing")
        return 0
    if p.get("refused"):
        return _refuse(p["refused"], fam, start, base, trigger, dry_run=False)
    timeout = None
    if trigger == "watch":            # C2: waits while the lock is held, until T-5 at the latest (380.4)
        timeout = max(0.0, (parse_utc(p["start"]) - timedelta(minutes=NO_ATTEMPT_INSIDE_MIN) - now).total_seconds())
    entered = False
    try:
        with acquire_lock(timeout):
            entered = True
            held = now + timedelta(seconds=time.time() - t_entry)
            return _under_lock(fam, p, base, folder, held, trigger, run_id)
    except TimeoutError:
        if entered:
            raise
        record_miss(fam, p["start"], "the lock was held until inside T-5")
        print(f"✗ {fam} {p['start_et']}: the chain lock was held until inside T-5 — no attempt; miss recorded")
        return NOTIFIED
    except Exception as e:  # noqa: BLE001 - Codex round 2 on #385: a lock that cannot be taken is a failed run, receipted
        if entered:
            raise
        rec = {**base, "start": p["start"], "start_et": p["start_et"], "covers": _covers_rec(p["covers"]),
               "attempt": closing_state(fam, p["start"])["attempts"] + 1, "backup": None, "steps": [],
               "export": None, "desk_rows": [], "push": None, "exit": 1, "failed": "lock",
               "error": c.redact(f"{type(e).__name__}: {e}")[:300]}
        print(f"✗ closing-run {fam} FAILED (lock: {rec['error']}) — no step ran")
        try:
            _finish(rec, fam, trigger, run_id, time.time())
        except Exception as e2:  # noqa: BLE001 - the receipt store itself is not writable: the console says so
            print(f"✗ the failed run could not be receipted either: {type(e2).__name__}")
            return 1                  # P3: not reported by the process, so the unit's failure path reports it
        return _failed_exit(trigger)


# -------------------------------------------------------------------------------------------------- watch --

def due(fam: str, now: datetime) -> dict:
    """The watch's view of one family at `now` (no network): its start times (C2 groups), and which is due."""
    games = with_called_off(fam, schedule(fam, now), now)      # Codex 4233123800
    gr = groups(games, now, covered_ids(fam))
    out = {"games": games, "groups": gr, "due": [], "inside": []}
    for g in gr:
        m = minutes_to(g["start"], now)
        if NO_ATTEMPT_INSIDE_MIN <= m <= RUN_LEAD_MIN:
            out["due"].append(g)
        elif 0 < m < NO_ATTEMPT_INSIDE_MIN:
            out["inside"].append(g)
    return out


def watch(dry_run: bool = False, now: datetime | None = None, families: tuple[str, ...] | None = None) -> int:
    """C2: the tick, every minute, for every family. Decides from the stored schedule and the receipts, no network;
    each due start time starts one run (earliest first), MLB's after checking its feed answers (A6). A start time
    first found inside T-5 with no closing is a miss (receipted and notified once). Otherwise exit 0, silent.
    Addendum 45 P3, the exit: 0 success or nothing due; 2 a refusal; NOTIFIED (3) a failed run or a miss, receipted
    and notified; 1 what the process could not report itself (an unhandled error also ends it non-zero).
    `now` (tests) fixes the tick's time for every run; else each queued run reads clock() when it starts (Codex on
    #385: the time spent running earlier closings in the same tick counts toward the next run's T-5 / started
    checks and its T-minus). Then the slate stage of every family (slate_watch, addendum 126 item 2(a)); its exit
    joins the tick's by worse()."""
    fixed_now = now
    now = utc(now or clock())
    fams = tuple(f.upper() for f in (families or tuple(FAMILIES)))
    plans = []
    for fam in fams:
        # Codex round 2 on #385: a family SP_SKIP_FAMILIES names is still planned; its due start times go through
        # run(), whose refusal is receipted and notified once per start time and reason (reading 7). No feed check.
        if _family_refusal(fam) and dry_run:
            print(f"DRY RUN closing-watch {fam}: a due start time would be REFUSED ({_family_refusal(fam)})")
        try:
            plans.append((fam, due(fam, now)))
        except (FileNotFoundError, sqlite3.Error) as e:
            if dry_run:
                print(f"DRY RUN closing-watch {fam}: no stored schedule ({type(e).__name__}) — would do nothing")
    if dry_run:
        print(f"DRY RUN closing-watch at {iso_z(now)} (no network, no step, no backup, no receipt, no push, no page)")
        for fam, d in plans:
            print(f"  {fam}:")
            for g in d["games"]:
                m = minutes_to(g["start"], now)
                tm = f"T-{m:.0f}m" if m > 0 else f"T+{-m:.0f}m"
                print(f"    match {g['match_id']}  {et(g['start'])}  {tm}  {g['away']} @ {g['home']}  [{g['status']}]"
                      + ("  started" if started(g, now) else ""))
            for g in d["groups"]:
                st = closing_state(fam, iso_z(g["start"]))
                m = minutes_to(g["start"], now)
                tag = ("DUE" if g in d["due"] else "inside T-5" if g in d["inside"] else
                       f"due at T-{RUN_LEAD_MIN} ({et(g['start'] - timedelta(minutes=RUN_LEAD_MIN))[11:]})")
                print(f"    start {iso_z(g['start'])} (T-{m:.0f}m) covers {[x['match_id'] for x in g['games']]} · "
                      f"success {'yes' if st['success'] else 'no'} · attempts {st['attempts']}/{MAX_ATTEMPTS} · "
                      f"misses {st['misses']} → {tag}")
        todo = sorted(((d_["start"], fam) for fam, d in plans for d_ in d["due"]))
        for s, fam in todo:
            print(f"  would " + (f"check the MLB feed ({FEED_PROBE}), then " if FAMILIES[fam]["feed"] else "")
                  + f"start closing-run --family {fam} --start {iso_z(s)}")
        if not todo:
            print("  would do nothing (exit 0, silent)")
        slate_tick: dict = {}         # at most one slate RUN per tick (addendum 134 item 1(ii)), in the plan too
        for fam in fams:              # the slate stage (addendum 126 item 2(a)): its plan, nothing run; the closings
            slate_watch(fam, now, dry_run=True, families=fams,     # this tick runs first hold nothing in it
                        planned=frozenset((f, s) for s, f in todo), tick=slate_tick)
        return 0
    rc = 0
    inside_why = "inside T-5 when the watch saw it: no attempt starts inside T-5"
    for fam, d in plans:              # a start time first found inside T-5 with no closing: a miss, once
        if _family_refusal(fam):
            continue                  # its refusal is receipted when a start time is due, not as a miss
        for g in d["inside"]:
            start = iso_z(g["start"])
            record_miss(fam, start, inside_why)        # B6: once per start time and reason
            rc = worse(rc, NOTIFIED)
    todo = sorted(((g["start"], fam) for fam, d in plans for g in d["due"]))
    feed_probe: dict = {}             # this tick's MLB feed answer, kept for its slate stage (_tick_feed)
    for s, fam in todo:
        start = iso_z(s)
        if FAMILIES[fam]["feed"] and not _family_refusal(fam):
            ok, detail = feed_answers()
            feed_probe.update(ok=ok, detail=detail)
            if not ok:                # B6: one miss per first pitch; later ticks keep trying, silently
                if record_miss(fam, start, "feed unreachable", detail=detail, text=FEED_MISS_TEXT):
                    print(f"✗ {FEED_MISS_TEXT} ({detail}) — nothing run; miss recorded for {fam} {start}; the "
                          "watch keeps trying")
                rc = worse(rc, NOTIFIED)
                continue
        r = run(family=fam, start=start, trigger="watch", now=clock() if fixed_now is None else utc(fixed_now))
        rc = worse(rc, r)
    # THE SLATE RUN (ARCHITECT 2026-10-18, addendum 126 item 2(a)): after the tick's closings, which keep their T-35
    # (a closing is the row that counts; the slate is the morning file). `now` is the tick's time, which judges a
    # late run; each slate run reads the clock when it starts, as each closing does, and does not start while a
    # closing of any of the tick's families is due or about to be (closing_ahead, SLATE_GUARD_MIN). The slate stage
    # probes the MLB feed at most once a tick, none when this tick's closings already did (feed_probe). At most ONE
    # slate RUN per tick (ARCHITECT 2026-10-18, addendum 134 item 1(ii), #606 item 1: "a slate that holds, misses or is
    # superseded does not count; the next family's slate runs on the next tick, a minute later"), so a tick is bounded
    # as before plus one chain (the host unit's TimeoutStartSec=45min does not move): slate_tick names the family whose
    # slate ran.
    slate_tick: dict = {}
    for fam in fams:
        rc = worse(rc, slate_watch(fam, now, clock() if fixed_now is None else utc(fixed_now), families=fams,
                                   feed_probe=feed_probe, tick=slate_tick))
    return rc


# Addendum 45 P3: the tick's exit is its worst run's. 1 (what the process could not report: the unit's failure path)
# outranks NOTIFIED (3, a failure or miss already receipted and notified), which outranks a refusal (2, receipted and
# notified once per start time and reason), which outranks success (0). The unit counts 2 and 3 as success.
_EXIT_RANK = {0: 0, 2: 1, NOTIFIED: 2}


def worse(a: int, b: int) -> int:
    return max((a, b), key=lambda x: _EXIT_RANK.get(x, 3))


# -------------------------------------------------------------------------------------------------- slate --
# THE SLATE RUN (ARCHITECT 2026-10-18, addendum 126 items 1-2; #590). Item 1, the operator's rule (verbatim): "We
# need predictions generated ahead of the first game of every game day with a sync, no matter whether it's on the host
# or laptop. If it's not on the HOST, you need to alert me to run these things manually." Item 2(a) (verbatim): "The
# closing watch [...] gains a SLATE stage per closing family per ET game day: due at the first kickoff of the day minus
# 150 minutes, or at the watch's first tick after 06:00 ET when that is later; one run per family per day; it runs the
# family's prematch steps exactly as the closing run resolves them (sync-matches for the day's ids, odds,
# injuries/pitchers/lineups as the family has them, Kalshi, predict, then the slate export WITH --desk to the family's
# slate file in exports/ [...] never the closing's logs/ path), pushes the mirror, and PAGES, card and phone [...] A
# failed step pages "SLATE NFL FAILED: <step> — RUN BY HAND: block …" the way a closing failure pages today, attempts 3
# like the closing. The closing runs at T-35 are unchanged; the slate is the morning file, the closing is the row that
# counts".
#   - Decided from the receipts (kind "slate"), never from memory: one success, or three attempts, ends the day for the
#     family. A refusal and a superseded run are neither (380.4, as for a closing).
#   - The steps are the closing chain's own, resolved by resolve_steps for the day's games not started (a closing's
#     covers stand in), word for word: the export step keeps the closing's own `--out logs/<run id>.<slate file
#     name>` (addendum 133 item 3(a); SOCCER adds the window its prematch chain prices, `--start`/`--end`, and nothing
#     else). The chain lock is the closing's (acquire_lock): a slate and a closing never run at once.
#   - After the steps: the kept file written by this run, carrying the Desk's calls, with a row for every game of the
#     day not started when the steps finished; then the kept file linked into exports/<slate file> the way the closing
#     writes its closing file (place_file: a hard link, then the rename over the name; `slate_file` {file, sha256};
#     the logs/ copy stays); then the mirror push; then one page. Any of them failing is a failed attempt, paged with
#     the RUN BY HAND line. STAGING (ARCHITECT 2026-10-18, addendum 133 item 3(a), the closing's doctrine of addendum
#     40 item 2, "a failed run leaves no call behind"): "A failed attempt leaves nothing in exports/ and nothing
#     reaches the mirror; an earlier good file of the same name (Saturday's soccer window file, on Sunday) is never
#     replaced by a half-synced one. A page that fails after the push: the file stands (it passed) and the attempt is
#     failed as built (the retry re-runs the steps and replaces it again)." As built in the ruled order (the link,
#     THEN the push, THEN the page), "leaves nothing in exports/" holds for a failure at a step, a check or the link.
#     A push that fails comes after the link, so its checked file stands in exports/ as a page failure's does; the
#     ruling names only the page, and whether a failed push must restore exports/ is open for the architect (#600's
#     ledger entry; nothing is built for it).
#   - The closings first (item 2(a): "The closing runs at T-35 are unchanged"): a slate does not start while a closing
#     the watch will still run, for any family of the tick, has its T-35 within SLATE_GUARD_MIN minutes or already
#     past (closing_ahead), and its wait for the chain lock ends SLATE_GUARD_MIN minutes before that T-35. So held, it
#     runs on a later tick, after the closing; each closing it waits for is receipted once (kind "slate", `held`, the
#     closing named: neither an attempt nor a refusal), so the day's newest hold names the closing it waits for now.
#     One watch process runs one thing at a time: a slate started inside that window would keep the closing's tick
#     from starting until it finished. A closing that cannot start holds no slate: while the MLB feed does not
#     answer, an MLB closing is a miss on every tick, never a run (A6), so when an MLB closing would hold a slate the
#     feed's answer is read and, unanswered, the guard reads the other families' closings only (slate_ahead). The
#     slate's own feed (an MLB slate's) is checked before the guard, so a feed that does not answer pages its RUN BY
#     HAND miss at once; but a closing due by the next tick holds the slate first, with no probe, where a probe could
#     not release it or could cost that closing its T-35 (_hold_unprobed: a closing with no feed; an MLB closing the
#     tick's answer says starts; with no answer, a closing with no feed due by the next tick too, or one probe that
#     could reach the first tick that could start that closing, the first of this machine's ticks after the probe's
#     start at or after its T-35: the host's whole minutes, the laptop's launchd phase, next_tick). An MLB closing with
#     no answer otherwise gets the one probe, so with the feed down it holds nothing (a hold for it lost a slate a
#     kickoff at c789cc1, and on the laptop's phase at f04460b). The slate stage probes the feed at most once a tick,
#     and not at all when the tick's closings already did: their answer is the tick's (_tick_feed).
#   - Late (ARCHITECT 2026-10-18, addendum 133 item 4, item 3): "`LATE <m> min: due HH:MM ET, first tick HH:MM ET, run
#     HH:MM ET`, where <m> counts from the due time to the run's start (ran_at) — the operator reads how late the FILE
#     is — and the line prints whenever the run's start is more than one cadence after the due time, whatever held it;
#     `first tick` says whether the laptop slept." The first tick is the earliest queued_at of the day's slate and
#     slate_miss receipts (a hold's, a miss's and a refusal's included; item 2(d)).
#   - The HELD page (addendum 133 item 4, item 2): "`SLATE <FAMILY> <date> HELD for <closing> — RUN BY HAND: <block>`,
#     once per family and day, when a slate is still held with no SLATE_GUARD_MIN window left before its family's first
#     UNSTARTED kickoff" (record_slate_hold).
#   - The counts (addendum 133 item 4, item 8): "N, PLAY and PASS count the DAY's games (rows whose match id is a game
#     of the ET day); rows beyond the day follow as `· +<k> beyond the day` when k > 0".
#   - At most ONE slate RUN per tick (ARCHITECT 2026-10-18, addendum 134 item 1(ii), #606 item 1): "a slate that holds,
#     misses or is superseded does not count; the next family's slate runs on the next tick, a minute later), so a tick
#     is bounded as before plus one chain; the bound itself does not move" (the host unit's TimeoutStartSec=45min). A
#     slate due after the tick's run is receipted once a day as a hold (record_slate_deferred).
#   - Misses (kind "slate_miss", once per family, day and reason, notified; not an attempt): the MLB feed unreachable
#     (A6, as the watch checks it before a closing; the watch keeps trying), the chain lock held through the wait
#     (the watch keeps trying), and a day whose every game had started before a slate ran (nothing left to slate).
#   - The family refusal (SP_SKIP_FAMILIES, MLB on the host) is receipted once per family, day and reason when the
#     watch is run for that family (bare, or with --family naming it), and pages nothing (#590 (d)): that machine is
#     not the slate's, and `coverage` names the block to run. The host's unit runs --family NFL --family SOCCER, so no
#     MLB slate receipt is written there; coverage's MLB SLATE line is the alert. The other refusals
#     are receipted and notified once per family, day and reason (reading 7, as for a closing).
SLATE_KIND = "slate"
SLATE_MISS_KIND = "slate_miss"
SLATE_LEAD_MIN = 150                 # item 2(a): due at the first kickoff of the day minus 150 minutes
SLATE_NOT_BEFORE_ET = (6, 0)         # item 2(a): "or at the watch's first tick after 06:00 ET when that is later"
WATCH_CADENCE_S = 60                 # the watch's tick (launchd INTERVAL_S=60; the host timer, every minute)
FEED_PROBE_MAX_S = FEED_TIMEOUT_S + 2   # the longest one MLB feed probe is allowed for: its timeout, plus 2 s
SLATE_LOCK_WAIT_S = 5 * 60           # a slate waits this long for the chain lock, then misses (the watch keeps trying)
# No slate starts with a closing's T-35 this close: more than twice the longest any chain has held the chain lock
# ("In twelve days no chain held the lock, or waited for it, longer than seven minutes", addendum 45 P6), so a slate
# that starts outside it has finished before the closing's tick is due.
SLATE_GUARD_MIN = 15
SLATE_DIR = "exports"
NO_DESK_CALL = "no desk call"        # a row the Desk gave no call (the export's rows with no probabilities)
SLATE_SHOWN_CALLS = ("PLAY", "PASS")  # always on the page; any other call kind follows only when it occurs
SLATE_ALL_STARTED = "every game of the day had started"     # the miss after which the watch runs no slate that day


def slate_due(first: datetime, day: date) -> datetime:
    """Item 2(a): the first kickoff of the day minus 150 minutes, or 06:00 ET when that is later."""
    floor = datetime(day.year, day.month, day.day, *SLATE_NOT_BEFORE_ET, tzinfo=NY).astimezone(timezone.utc)
    return max(utc(first) - timedelta(minutes=SLATE_LEAD_MIN), floor)


def slate_block(fam: str, day: date) -> str:
    """The operator's block for the day's slate by hand (addendum 126 item 1: block_1018_nfl_slate.txt)."""
    return f"block_{day:%m%d}_{fam.lower()}_slate.txt"


def soccer_window(day: date) -> tuple[str, str]:
    """The window soccer-prematch's export prices (`--start {sat} --end {sat_plus3}`, sp_run.date_vars), for the round
    holding `day`: a Saturday to Tuesday day is the round of the Saturday on or before it (the Friday and Saturday run's
    own window, soccer_PL_2026-10-17_to_2026-10-20.json for 10-17 to 10-20); a Wednesday to Friday day takes the
    midweek override's form, `--set sat=<day> --set sat_plus3=<day + 3>` (chains.py)."""
    back = (day.weekday() - 5) % 7    # days since the Saturday on or before the day
    if back <= 3:
        v = sp_run.date_vars(day - timedelta(days=back))
    else:
        v = {"sat": day.isoformat(), "sat_plus3": (day + timedelta(days=3)).isoformat()}
    return v["sat"], v["sat_plus3"]


def slate_file(fam: str, day: date) -> str:
    """The family's slate file in exports/, the name its prematch chain's export writes (the family's export_glob, so
    last_calls and coverage read it as the slate kind): MLB mlb_MLB_<day>.json (export-predictions --date <day>), NFL
    nfl_predictions_<day>.json, SOCCER soccer_PL_<start>_to_<end>.json (soccer_window)."""
    stamp = "{}_to_{}".format(*soccer_window(day)) if fam == "SOCCER" else day.isoformat()
    return FAMILIES[fam]["export_glob"].replace("*", stamp)


def slate_steps(fam: str, day: date, covers: list[dict], run_start: datetime, run_id: str) -> list[list[str]]:
    """Item 2(a): "the family's prematch steps exactly as the closing run resolves them": resolve_steps for the day's
    games (`covers`), word for word. Addendum 133 item 3(a): "The slate's export step keeps the closing's own `--out
    logs/<run id>.<slate file name>` exactly as resolve_steps gives it (SOCCER still gains its `--start`/`--end`
    window; nothing else is inserted)": SOCCER's export adds the window its prematch chain prices, before its --out."""
    first = min(g["start"] for g in covers)
    steps = [list(s) for s in resolve_steps(fam, first, covers, run_start, run_id)]
    if fam == "SOCCER":
        exp = steps[-1]
        i = exp.index("--out")
        s, e = soccer_window(day)
        exp[i:i] = ["--start", s, "--end", e]
    return steps


def link_slate_file(kept: str, name: str) -> dict:
    """Addendum 133 item 3(a): once the checks pass, "the run links the kept file into `exports/<slate file>` the way
    the closing writes its closing file (a hard link, then the rename over the name; receipted `slate_file` {file,
    sha256}; the logs/ copy stays)". place_file, the closing file's own write: the kept export (`kept`, the export
    step's logs/<run id>.<name>) hard-linked to the temporary name beside exports/<name>, then the rename over the name
    (an earlier file of that name is replaced whole, never written into). {file, sha256} or {file, error}; on an error
    exports/ is as it was."""
    rel = f"{SLATE_DIR}/{name}"
    dest = c.REPO / SLATE_DIR / name
    tmp = dest.with_name(f".{name}.tmp")
    src = c.REPO / kept

    def fill(t: Path) -> None:
        if t.exists() or t.is_symlink():
            t.unlink()                        # a temporary name a crashed run left: never this run's file
        os.link(src, t)
    try:
        c.refuse_under_data(dest.parent)
        place_file(dest, fill)
        return {"file": rel, "sha256": _sha256(dest)}
    except (OSError, SystemExit) as e:
        try:
            tmp.unlink()
        except OSError:
            pass
        return {"file": rel, "error": c.redact(f"{type(e).__name__}: {e}")[:300]}


def rows_text(n) -> str:
    """Addendum 133 item 3(c): "The declared text is `<N> row(s)` by count": 1 row, 2 rows."""
    return f"{n} row" + ("" if n == 1 else "s")


def slate_calls(doc: dict, ids=None) -> tuple[int, dict]:
    """(rows, {call: count}) of an export: every row counted once, by its desk block's call (PLAY, PASS, and any other
    kind the Desk gives, e.g. soccer's LADDER), a row with no desk block under NO_DESK_CALL. PLAY and PASS are always
    present. `ids` (ARCHITECT 2026-10-18, addendum 133 item 4, item 8: "N, PLAY and PASS count the DAY's games (rows
    whose match id is a game of the ET day)"): only the rows of those match ids are counted; beyond_day counts the
    others. None: every row."""
    rows = [r for r in doc.get("predictions") or [] if ids is None or r.get("match_id") in ids]
    calls = {k: 0 for k in SLATE_SHOWN_CALLS}
    for r in rows:
        k = str((r.get("desk") or {}).get("call") or NO_DESK_CALL)
        calls[k] = calls.get(k, 0) + 1
    return len(rows), calls


def beyond_day(doc: dict, ids) -> int:
    """Item 8: the export's rows whose match id is no game of the ET day (`ids`): the NFL 36-hour window, the soccer
    round. They follow the counts as `· +<k> beyond the day` when k > 0 (beyond_text)."""
    return sum(1 for r in doc.get("predictions") or [] if r.get("match_id") not in ids)


def beyond_text(k) -> str:
    """Item 8's declared text, `· +<k> beyond the day`, when k > 0; "" otherwise (no k, or none beyond)."""
    return f" · +{k} beyond the day" if k else ""


def calls_text(calls: dict) -> str:
    """"PLAY p · PASS q", then each other kind with a count, by name: a LADDER is never folded into PLAY or PASS."""
    return " · ".join([f"{k} {calls.get(k, 0)}" for k in SLATE_SHOWN_CALLS]
                      + [f"{k} {n}" for k, n in sorted(calls.items()) if k not in SLATE_SHOWN_CALLS and n])


def slate_page_text(fam: str, day: date, rows: int, calls: dict, file: str, late: dict | None,
                    beyond: int = 0) -> tuple[str, str]:
    """Item 2(a)'s page, the declared text: "SLATE <FAMILY> <YYYY-MM-DD>: <N> row(s) · PLAY <p> · PASS <q> ·
    exports/<file>" (addendum 133 item 3(c): `1 row` on a one-game day, rows_text). N and the calls count the ET day's
    games (addendum 133 item 4, item 8), and the rows beyond the day follow the counts, `· +<k> beyond the day` when
    k > 0 (`beyond`, beyond_text). A late run (_slate_late: the run's start more than one cadence after the due time,
    whatever held it) says so on the next line, the declared text of addendum 133 item 4, item 3: `LATE <m> min: due
    HH:MM ET, first tick HH:MM ET, run HH:MM ET` (the first tick: the earliest queued_at of the day's slate and
    slate_miss receipts, which says whether the laptop slept); the machine's line last (addendum 45).
    Returns (title, body)."""
    lines = [f"SLATE {fam} {day.isoformat()}: {rows_text(rows)} · {calls_text(calls)}{beyond_text(beyond)} · {file}"]
    if late:
        lines.append(f"LATE {late['minutes']} min: due {et(late['due'])[11:]}, first tick {et(late['tick'])[11:]}, "
                     f"run {et(late['run'])[11:]}")
    lines.append(machine_line())
    return f"{fam} slate {day.isoformat()}", "\n".join(lines)


def slate_failure_text(fam: str, day: date, what: str, attempt: int) -> str:
    """The closing failure notice's shape (failure_text): what failed, the attempt out of three, and on the third that
    no further attempt runs; notify_failure adds the machine's line."""
    t = f"SLATE {fam} FAILED: {what} — RUN BY HAND: {slate_block(fam, day)} · attempt {attempt}/{MAX_ATTEMPTS}"
    return t + (" · no further attempt will run today" if attempt >= MAX_ATTEMPTS else "")


def _slate_attempts(fam: str, day_s: str) -> list[dict]:
    """The slate runs of a family's day: refusals, superseded runs and holds are none (380.4, as _attempts)."""
    return [r for r in receipts((SLATE_KIND,)) if r.get("family") == fam and r.get("date") == day_s
            and not r.get("refused") and not r.get("superseded") and not r.get("held")]


def slate_state(fam: str, day_s: str) -> dict:
    """For one family and ET day, from the receipts: a successful slate? how many attempts?"""
    runs = _slate_attempts(fam, day_s)
    return {"success": any(r.get("exit") == 0 for r in runs), "attempts": len(runs)}


def record_slate_miss(fam: str, day: date, reason: str, detail: str | None = None,
                      text: str | None = None, queued_at: datetime | None = None,
                      due_at: datetime | None = None) -> dict | None:
    """kind slate_miss: a slate that did not run, receipted and notified once per family, day and reason (B6's rule
    for a closing miss). Not an attempt. Already receipted: nothing written or posted (None). `queued_at` (the tick
    that found it) and `due`: the first miss of a reason is the first tick that saw it, which judges late."""
    if any(r.get("family") == fam and r.get("date") == day.isoformat() and r.get("reason") == reason
           for r in receipts((SLATE_MISS_KIND,))):
        return None
    text = text or f"SLATE {fam} {day.isoformat()} MISSED: {reason} — RUN BY HAND: {slate_block(fam, day)}"
    res = notify_failure(text, fam, title=f"{fam} slate")
    return c.append_receipt({"kind": SLATE_MISS_KIND, "family": fam, "date": day.isoformat(), "reason": reason,
                             **({"detail": detail} if detail else {}),
                             **({"queued_at": iso_z(queued_at)} if queued_at else {}),
                             **({"due": iso_z(due_at)} if due_at else {}), "notified": res})


def closing_open(fam: str, start: datetime, now: datetime) -> bool:
    """A closing the watch will still run at `now` (closing_ahead's test; coverage reads it for a slate's hold): its
    start more than NO_ATTEMPT_INSIDE_MIN away (inside T-5 or started, no attempt starts: a miss, no chain) and no
    success or three attempts (superseded under the lock: no chain). Reads the receipts; no network."""
    if minutes_to(start, now) < NO_ATTEMPT_INSIDE_MIN:
        return False
    st = closing_state(fam, iso_z(start))
    return not (st["success"] or st["attempts"] >= MAX_ATTEMPTS)


def closing_ahead(fams: tuple[str, ...], now: datetime, skip: frozenset = frozenset()) -> dict | None:
    """The closing the watch will run next among `fams` (due()'s groups, as watch() forms them): the earliest group
    still open (closing_open: its start more than NO_ATTEMPT_INSIDE_MIN away, no success or three attempts), its T-35
    (`run_at`) possibly already past. A family this machine refuses is none (its closing is refused at once, no
    chain), nor one whose schedule cannot be read. `skip`: (family, start) pairs left out (the dry run's: the closings
    the tick itself runs before its slates). {family, start, run_at} or None. No network."""
    best = None
    for f in fams:
        if _family_refusal(f):
            continue
        try:
            gr = due(f, now)["groups"]
            for g in gr:
                if (f, g["start"]) in skip:
                    continue              # the tick runs it first (dry run)
                if not closing_open(f, g["start"], now):
                    continue              # inside T-5 or started (a miss), or superseded under the lock: no chain
                run_at = g["start"] - timedelta(minutes=RUN_LEAD_MIN)
                if best is None or run_at < best["run_at"]:
                    best = {"family": f, "start": g["start"], "run_at": run_at}
        except (FileNotFoundError, sqlite3.Error):
            continue
    return best


def _tick_feed(feed_probe: dict | None) -> tuple[bool, str]:
    """The MLB feed's answer for the slate stage: the tick's own when it has one (`feed_probe`, watch()'s per-tick
    {ok, detail}: its closings' probe, or an earlier slate's this tick), else one probe, kept there for the rest of the
    tick. None (a direct call): one probe, kept nowhere. (answers?, detail)"""
    if feed_probe is not None and "ok" in feed_probe:
        return feed_probe["ok"], feed_probe.get("detail", "")
    ok, detail = feed_answers()
    if feed_probe is not None:
        feed_probe.update(ok=ok, detail=detail)
    return ok, detail


def next_tick(tick_at: datetime, now: datetime, at: datetime | None = None) -> datetime:
    """The first tick of this machine's watch after `now` that could start a closing whose T-35 is `at` (None: the
    first tick after `now`): the first firing after `now` at or after `at`, on this machine's cadence (mirror_role).
    The host's timer fires every minute at :00; the laptop's launchd job a whole number of cadences after this tick's
    start `tick_at` (StartInterval keeps the phase it was loaded with, and a firing while the watch runs is missed:
    launchd.plist(5)). A firing before `at` cannot start that closing, so a probe that costs the watch that firing
    does not delay the closing (the #590 review at f04460b: the next firing of either cadence, the whole minute
    included, held a slate on the laptop where no probe could delay the closing, and a feed-down slate lost a kickoff
    that cb1261d caught). A machine with no role refuses every run before its steps (_role_refusal) and is read as the
    laptop. The tests' ticks start on the minute, where the two cadences are one."""
    cad = timedelta(seconds=WATCH_CADENCE_S)
    origin = now.replace(second=0, microsecond=0) if mirror_role() == "host" else tick_at
    k = (now - origin) // cad + 1                   # the first firing after `now`
    if at is not None:
        k = max(k, -((origin - at) // cad))         # and at or after `at` (the ceiling of its cadences from origin)
    return origin + k * cad


def _hold_unprobed(near: dict, fams: tuple[str, ...], tick_at: datetime, now: datetime, known: bool | None) -> bool:
    """Whether `near`, a closing due by the next tick (its T-35 within WATCH_CADENCE_S of `now`), holds the slate with
    no probe of the slate stage's own. Two #590 review findings bound it: a probe after the tick's closings could carry
    the next tick past that closing's T-35 (c789cc1); and a hold for an MLB closing the feed cannot start costs the
    slate a tick, perhaps a kickoff (cb1261d probed there, and caught it). Held when the closing starts whatever the
    feed says (a family with no feed), or the tick's answer (`known`: its closings' probe or an earlier slate's) says
    it starts; not when that answer says it cannot (a miss: it holds nothing, slate_ahead). With no answer: held when
    a closing of a family with no feed is due by the next tick too (the slate is held whatever a probe says), or when
    one probe (FEED_PROBE_MAX_S) could reach the first tick that could start `near` (next_tick: this machine's first
    firing after `now` at or after `near`'s T-35; a probe that costs the watch an earlier firing costs that closing
    nothing); else the slate stage probes once (_tick_feed) and the guard reads that answer. No network."""
    if not FAMILIES[near["family"]]["feed"]:
        return True
    if known is not None:
        return bool(known)
    other = closing_ahead(tuple(f for f in fams if not FAMILIES[f]["feed"]), now)
    return bool((other and other["run_at"] <= now + timedelta(seconds=WATCH_CADENCE_S))
                or now + timedelta(seconds=FEED_PROBE_MAX_S) >= next_tick(tick_at, now, near["run_at"]))


def slate_ahead(fams: tuple[str, ...], now: datetime, feed: bool | None = None,
                feed_probe: dict | None = None) -> dict | None:
    """The closing a slate waits for (closing_ahead), leaving out the closings that cannot start: while the MLB feed
    does not answer, a feed family's closing is a miss on every tick, never a run (watch(), A6), so it holds no slate.
    The feed's answer is read only when such a closing would hold the slate (its T-35 within SLATE_GUARD_MIN or past):
    `feed`, this tick's answer when the slate already has one (an MLB slate's own check), else the tick's
    (_tick_feed: no probe when the tick already made one)."""
    ahead = closing_ahead(fams, now)
    if (ahead and FAMILIES[ahead["family"]]["feed"]
            and ahead["run_at"] <= now + timedelta(minutes=SLATE_GUARD_MIN)):
        if feed is None:
            feed, _ = _tick_feed(feed_probe)
        if not feed:
            ahead = closing_ahead(tuple(f for f in fams if not FAMILIES[f]["feed"]), now)
    return ahead


def _closing_text(ahead: dict) -> str:
    """The closing a slate waits for, by its start and its T-35 in ET: `closing NFL 20:15 ET (T-35 19:40 ET)`."""
    return f"closing {ahead['family']} {et(ahead['start'])[11:]} (T-{RUN_LEAD_MIN} {et(ahead['run_at'])[11:]})"


def _hold_why(ahead: dict, lock: bool = False) -> str:
    """Why a slate is held: the closing ahead, by its start and its T-35 in ET."""
    clo = _closing_text(ahead)
    return (f"the chain lock was held into the {SLATE_GUARD_MIN}-minute guard before {clo}" if lock
            else f"{clo} is inside the {SLATE_GUARD_MIN}-minute guard")


def held_page_text(fam: str, day: date, ahead: dict) -> str:
    """ARCHITECT 2026-10-18, addendum 133 item 4, item 2, the declared text: `SLATE <FAMILY> <date> HELD for <closing>
    — RUN BY HAND: <block>` (<closing>: _closing_text)."""
    return f"SLATE {fam} {day.isoformat()} HELD for {_closing_text(ahead)} — RUN BY HAND: {slate_block(fam, day)}"


def record_slate_hold(fam: str, day: date, base: dict, ahead: dict, why: str | None = None,
                      games: list[dict] | None = None, now: datetime | None = None) -> int:
    """A slate held for a closing (no step; neither an attempt nor a refusal): receipted (kind slate, `held`) once per
    family, day and closing it waits for (that closing's family and start), so the day's newest hold names the
    closing the slate waits for now (coverage's SLATE line reads it); later holds for the same closing write nothing.
    Late is unchanged: _slate_late takes the earliest queued_at of the day's lines.
    THE HELD PAGE (ARCHITECT 2026-10-18, addendum 133 item 4, item 2): "`SLATE <FAMILY> <date> HELD for <closing> — RUN
    BY HAND: <block>`, once per family and day, when a slate is still held with no SLATE_GUARD_MIN window left before
    its family's first UNSTARTED kickoff": the family's first game of the day (`games`) not started at `now` kicks off
    within SLATE_GUARD_MIN, so no slate can run before it. Notified (card and phone, as a miss) and receipted on the
    hold's line (`held_page`: the text and the notification), written then even when the hold for that closing is
    already receipted. Exit NOTIFIED when the page goes out, else 0."""
    day_s = day.isoformat()
    mine = [r for r in receipts((SLATE_KIND,)) if r.get("family") == fam and r.get("date") == day_s]
    key = (ahead["family"], iso_z(ahead["start"]))
    seen = any(r.get("held") and ((r.get("closing") or {}).get("family"), (r.get("closing") or {}).get("start")) == key
               for r in mine)
    page = None
    if games is not None and now is not None and not any(r.get("held_page") for r in mine):
        live = [g["start"] for g in games if not started(g, now)]
        if live and min(live) <= utc(now) + timedelta(minutes=SLATE_GUARD_MIN):
            page = held_page_text(fam, day, ahead)
    if seen and not page:
        return 0
    why = why or _hold_why(ahead)
    print(f"· slate {fam} {day_s} held: {why} (the slate runs after it)")
    rec = {**base, "held": why, "closing": {"family": ahead["family"], "start": iso_z(ahead["start"]),
                                            "run_at": iso_z(ahead["run_at"])},
           "steps": [], "file": None, "rows": None, "calls": None, "push": None, "exit": 0}
    if page:
        rec["held_page"] = {"text": page, "notified": notify_failure(page, fam, title=f"{fam} slate")}
        print(f"✗ {page}")
    c.append_receipt(rec)
    return NOTIFIED if page else 0


def record_slate_deferred(fam: str, day: date, base: dict, ran: str) -> int:
    """A slate due on a tick whose one slate run another family's slate took (ARCHITECT 2026-10-18, addendum 134 item
    1(ii): "at most ONE slate RUN per tick [...] the next family's slate runs on the next tick, a minute later"): no
    step, neither an attempt nor a refusal. Receipted once per family and day as a hold (`held`, with `deferred`: the
    family that ran), so the LATE line's first tick is the tick that first found the slate due (_slate_late) and
    coverage's SLATE line shows the wait. Exit 0."""
    day_s = day.isoformat()
    why = f"one slate run per tick: the {ran} slate ran this tick (the next tick runs it)"
    print(f"· slate {fam} {day_s} held: {why}")
    if any(r.get("family") == fam and r.get("date") == day_s and r.get("deferred")
           for r in receipts((SLATE_KIND,))):
        return 0
    c.append_receipt({**base, "held": why, "deferred": ran, "steps": [], "file": None, "rows": None, "calls": None,
                      "push": None, "exit": 0})
    return 0


def _slate_late(fam: str, day_s: str, tick_at: datetime, due_at: datetime,
                ran_at: datetime) -> tuple[float, dict | None]:
    """ARCHITECT 2026-10-18, addendum 133 item 4, item 3: "<m> counts from the due time to the run's start (ran_at) —
    the operator reads how late the FILE is — and the line prints whenever the run's start is more than one cadence
    after the due time, whatever held it; `first tick` says whether the laptop slept." The run's start is read in
    whole seconds, as its receipt's ran_at keeps it (a tick one cadence after the due time is on time). The first tick:
    the earliest queued_at of the day's slate and slate_miss receipts, or this tick (item 2(d)).
    (seconds after the due time, {minutes, due, tick, run} or None)."""
    run = parse_utc(iso_z(ran_at))
    first = utc(tick_at)
    for r in receipts((SLATE_KIND, SLATE_MISS_KIND)):
        if r.get("family") != fam or r.get("date") != day_s:
            continue
        try:
            first = min(first, parse_utc(r["queued_at"]))
        except (KeyError, TypeError, ValueError):
            continue
    late_s = (run - utc(due_at)).total_seconds()
    return late_s, ({"minutes": int(late_s // 60), "due": utc(due_at), "tick": first, "run": run}
                    if late_s > WATCH_CADENCE_S else None)


def _slate_rec(base: dict, fam: str, day: date, attempt: int, at: datetime, tick_at: datetime, due_at: datetime,
               covers: list[dict]) -> tuple[dict, dict | None]:
    """An attempt's receipt line before it runs, every declared key present (item 2(c): family, date, rows, calls,
    file, exit), exit 1 until it succeeds; and its late (or None)."""
    late_s, late = _slate_late(fam, day.isoformat(), tick_at, due_at, at)
    return ({**base, "ran_at": iso_z(at), "late_minutes": max(0, int(late_s // 60)), "late": late is not None,
             "attempt": attempt, "covers": _covers_rec(covers), "file": f"{SLATE_DIR}/{slate_file(fam, day)}",
             "export": None, "rows": None, "calls": None, "beyond_day": None, "backup": None, "steps": [], "push": None,
             "exit": 1}, late)


def _slate_refuse(why: str, fam: str, day: date, base: dict) -> int:
    """A receipted refusal (exit 2), once per family, day and reason. The family refusal pages nothing (#590 (d));
    every other refusal is notified, as a closing's is (reading 7)."""
    if any(r.get("family") == fam and r.get("date") == day.isoformat() and r.get("refused") == why
           for r in receipts((SLATE_KIND,))):
        return 2
    rec = {**base, "exit": 2, "refused": why, "steps": [], "file": None, "rows": None, "calls": None, "push": None}
    if why != _family_refusal(fam):
        rec["failure_notification"] = notify_failure(
            f"SLATE {fam} {day.isoformat()} REFUSED: {why} — RUN BY HAND: {slate_block(fam, day)}", fam,
            title=f"{fam} slate")
    print(f"✗ slate {fam} {day.isoformat()} REFUSED: {why}")
    c.append_receipt(rec)
    return 2


def _slate_what(rec: dict) -> str:
    """The failure notice's <step command>: the failing step's command line as the receipt records it, else what
    failed after the steps."""
    f = rec.get("failed")
    if rec.get("step"):
        return rec["step"]
    return {"backup": f"backup ({(rec.get('backup') or {}).get('error') or 'not taken'})",
            "export not written": f"export not written ({rec.get('export')})",
            "export carries no desk calls": f"{rec.get('export')} carries no desk calls",
            "missing from export": f"missing from export ({rec.get('export')}): match "
                                   + ", ".join(str(m["match_id"]) for m in rec.get("missing") or []),
            "slate file": f"{rec.get('file')} not linked ("
                          + str((rec.get("slate_file") or {}).get("error") or "?").split(":")[0] + ")",
            "push": f"mirror push (exit {(rec.get('push') or {}).get('exit')})",
            "page": f"page (ntfy did not accept it in {PAGE_TRIES} tries)"}.get(
        f, f"{f}" + (f" ({rec['error']})" if rec.get("error") else ""))


def _slate(rec: dict, fam: str, day: date, covers: list[dict], folder: Path, held: datetime, t0: float,
           wall0: float, late: dict | None) -> None:
    """The slate run's body. The caller holds the chain lock and writes the receipt line afterwards, still under it."""
    today_ny = ny_date(held)
    have = todays_backup(folder, today_ny)
    if have:
        rec["backup"] = {"file": str(have), "taken": False}
        print(f"· backup dated {today_ny}: {have}")
    else:
        rec["backup"] = take_backup(folder, today_ny)
    if rec["backup"].get("taken") and not rec["backup"].get("ok"):
        rec["failed"] = "backup"                  # 380.3, as a closing: no step runs
        print(f"✗ backup failed: {rec['backup'].get('error')} — no step runs")
        return
    steps = slate_steps(fam, day, covers, held, rec["run_id"])
    rec["planned_steps"] = len(steps)
    # addendum 133 item 3(a): the export step writes resolve_steps' own --out, logs/<run id>.<name> (the closing's
    # export_candidates); nothing reaches exports/ until the checks below pass
    rec["export"] = steps[-1][steps[-1].index("--out") + 1]
    logs = c.REPO / "logs"
    c.refuse_under_data(logs)
    logs.mkdir(parents=True, exist_ok=True)
    for i, st in enumerate(steps, 1):
        line = f"python cli.py {' '.join(st)}"
        print(f"\n=== [{fam} slate {i}/{len(steps)}] {line}", flush=True)
        rc, tail, dur = run_step(st, rec["run_id"])
        srec = {"step": i, "command": line, "exit": rc, "seconds": round(dur, 1)}
        said = reported_failure(st, tail) if rc == 0 else None
        if said:                      # exit 0, but the step said it failed (Codex on #370)
            srec["detected_failure"] = said
        empty = empty_answers(st, tail)
        if empty:                     # addendum 40 item 4
            srec["empty_answers"] = empty
        if rc != 0:
            srec["tail"] = tail[-3:]
        rec["steps"].append(srec)
        if rc != 0 or said:
            rec["failed"] = f"step {i}" + (" (reported failure, exit 0)" if said else "")
            rec["step"] = line
            return
    path = c.REPO / rec["export"]
    if not (path.is_file() and path.stat().st_mtime >= wall0):
        rec["failed"] = "export not written"
        return
    raw = path.read_bytes()
    rec["export_written"] = {"file": rec["export"], "sha256": hashlib.sha256(raw).hexdigest()}
    doc = json.loads(raw)
    if not doc.get("desk_meta"):
        rec["failed"] = "export carries no desk calls"
        return
    done = held + timedelta(seconds=time.time() - t0)
    rec["completed_at"] = iso_z(done)
    # every game of the day, re-read (the steps synced the schedule): a game the sync added to the day is required too
    # (item 2(b): "covers EVERY game of the day by match id"; Codex on #600), and the next attempt's steps name it
    games = day_games(fam, day)
    missing = missing_from_export(doc, games, done, games)
    if missing:
        rec["failed"] = "missing from export"
        rec["missing"] = missing
        return
    ids = {g["match_id"] for g in games}      # item 8: the counts are the ET day's games; the rest follow as +k
    rec["rows"], rec["calls"] = slate_calls(doc, ids)
    rec["beyond_day"] = beyond_day(doc, ids)
    # addendum 133 item 3(a): the checks passed: the kept file is linked into exports/<slate file> (the closing file's
    # write: a hard link, then the rename over the name), THEN the push, THEN the page
    rec["slate_file"] = link_slate_file(rec["export"], Path(rec["file"]).name)
    if rec["slate_file"].get("error"):
        rec["failed"] = "slate file"
        print(f"✗ slate file NOT linked: {rec['slate_file']['error']} — nothing pushed or paged; exports/ as it "
              "was")
        return
    print(f"· slate file: {rec['file']} (linked from {rec['export']}, sha256 {rec['slate_file']['sha256'][:12]})")
    rec["push"] = push_mirror("slate")
    print(f"· exports mirror ({mirror_role()}, slate): exit {rec['push']['exit']} {' | '.join(rec['push']['tail'])}")
    if rec["push"].get("exit") != 0:
        rec["failed"] = "push"
        return
    title, body = slate_page_text(fam, day, rec["rows"], rec["calls"], rec["file"], late, rec["beyond_day"])
    print(f"\n--- page ---\n{body}\n---")
    tries = []
    for n in range(1, PAGE_TRIES + 1):
        try:
            ph = page_phone(title, body, "default")
        except Exception as e:  # noqa: BLE001
            ph = {"accepted": False, "error": type(e).__name__}
        tries.append(ph)
        if ph.get("accepted") is True:
            break
        if n < PAGE_TRIES:
            page_sleep(PAGE_RETRY_S)
    rec["page"] = {"title": title, "priority": "default", "text": body, "phone": ph, "tries": len(tries),
                   "at": iso_z(held + timedelta(seconds=time.time() - t0))}
    if ph.get("accepted") is not True:
        rec["page"]["phone_tries"] = tries
        rec["failed"] = "page"
        return
    try:
        scr = notify(body, title=title)
    except Exception as e:  # noqa: BLE001
        scr = {"posted": False, "error": f"{type(e).__name__}: {e}"[:200]}
    rec["page"]["screen"] = {"posted": scr.get("posted"),
                             **({"skipped": scr["skipped"]} if scr.get("skipped") else {}),
                             **({"error": scr["error"]} if scr.get("error") else {})}
    rec["exit"] = 0


def _slate_under_lock(fam: str, day: date, base: dict, folder: Path, held: datetime, tick_at: datetime,
                      due_at: datetime, tick: dict | None = None) -> int:
    """380.4 for the slate: under the lock the receipts are read again (a success or three attempts by then: superseded,
    neither an attempt nor a refusal, nothing run or posted), the day's games re-read, and the attempt numbered. An
    attempt is the tick's one slate run (`tick`, watch()'s: addendum 134 item 1(ii)); a supersession, the every-game-
    started miss and the #442 refusal are none."""
    day_s = day.isoformat()
    st = slate_state(fam, day_s)
    if st["success"] or st["attempts"] >= MAX_ATTEMPTS:
        c.append_receipt({**base, "superseded": True, "file": None, "rows": None, "calls": None, "exit": 0,
                          "lock_at": iso_z(held),
                          "why": "a successful slate" if st["success"] else f"{st['attempts']} attempts"})
        return 0
    covers = [g for g in day_games(fam, day) if not started(g, held)]
    if not covers:
        record_slate_miss(fam, day, SLATE_ALL_STARTED,
                          text=f"SLATE {fam} {day_s} MISSED: {SLATE_ALL_STARTED} — no slate run",
                          queued_at=tick_at, due_at=due_at)
        return NOTIFIED
    # #442 (addendum 44 item 8): "A run whose export path already exists does not start: a receipted refusal before
    # any step [...] Nothing a run kept is opened for writing a second time." The slate's export is the closing's own
    # kept path (addendum 133 item 3(a)), the same name slate_steps gives it; two watch processes entering in one UTC
    # second share the run id, and the second would write in place into the first's kept file (after a link, the
    # exports/ file too). Under the lock, before the backup and every step; a refusal, no attempt.
    why = _export_path_refusal(fam, min(g["start"] for g in covers), held, base["run_id"])
    if why:
        return _slate_refuse(why, fam, day, base)
    # late runs from the due time to this run's start; the first tick is the earliest that found the slate due
    rec, late = _slate_rec(base, fam, day, st["attempts"] + 1, held, tick_at, due_at, covers)
    if tick is not None:
        tick["ran"] = fam             # this tick's one slate run (addendum 134 item 1(ii))
    print(f"=== slate {fam} {day_s} · due {et(due_at)} · {len(covers)} game(s) · attempt {rec['attempt']}"
          + (f" · LATE {late['minutes']} min" if late else ""), flush=True)
    t0 = time.time()
    wall0 = _WALL() - 1.0             # the file must be written by this run's own step (1s: coarse mtimes)
    try:
        _slate(rec, fam, day, covers, folder, held, t0, wall0, late)
    except Exception as e:  # noqa: BLE001 - the receipt line is written either way
        rec["failed"] = rec.get("failed") or "error"
        rec["error"] = c.redact(f"{type(e).__name__}: {e}")[:300]
    if rec["exit"] != 0:
        rec["failure_notification"] = notify_failure(
            slate_failure_text(fam, day, _slate_what(rec), rec["attempt"]), fam, title=f"{fam} slate")
        print(f"✗ slate {fam} {day_s} FAILED ({rec.get('failed')}) — attempt {rec['attempt']}/{MAX_ATTEMPTS}")
    else:
        print(f"✓ slate {fam} {day_s}: {rec['file']} · {rows_text(rec['rows'])} · {calls_text(rec['calls'])}"
              f"{beyond_text(rec.get('beyond_day'))} · pushed · page accepted")
    rec["seconds"] = round(time.time() - t0, 1)
    c.append_receipt(rec)
    return 0 if rec["exit"] == 0 else NOTIFIED


def slate_watch(fam: str, tick_at: datetime, now: datetime | None = None, dry_run: bool = False,
                families: tuple[str, ...] | None = None, planned: frozenset = frozenset(),
                feed_probe: dict | None = None, tick: dict | None = None) -> int:
    """The slate stage of one family at the watch's tick `tick_at` (item 2(a)). Decides from the stored schedule and
    the receipts, no network but the MLB feed probe (A6: an MLB slate's own, or an MLB closing's that would hold it):
    the family's games of the tick's ET day; due at slate_due(); nothing before it, nothing after a success or three
    attempts. Exit as a closing's (0, 2 a refusal, NOTIFIED a failure or miss). `now`: when the run starts (the watch
    reads the clock for each run); a run is late when the first tick that found it due came more than one cadence
    after the due time (_slate_late). `families`: the tick's families, whose closings a slate never delays
    (slate_ahead: held inside SLATE_GUARD_MIN of the T-35 of a closing that can start, its lock wait ending there;
    held with no probe by a closing due by the next tick where a probe could not release it or could cost it its T-35,
    _hold_unprobed). `feed_probe`: the tick's MLB feed answer ({ok, detail}, watch()'s, shared by the tick's slates:
    _tick_feed); None, one probe of its own when it needs one. `tick`: watch()'s per-tick record of its one slate run
    (ARCHITECT 2026-10-18, addendum 134 item 1(ii): "at most ONE slate RUN per tick (a slate that holds, misses or is
    superseded does not count; the next family's slate runs on the next tick, a minute later)"): once a slate of the
    tick has run (`ran`, its family), a slate that would start waits for the next tick, nothing receipted (its holds,
    misses and refusals still read this tick); None (a direct call), no bound.
    --dry-run prints the plan and touches nothing (no network: an MLB closing ahead is shown both ways); `planned`:
    the (family, start) closings the dry run's tick runs first, which hold no slate in the plan, though one after them
    may (`would RUN if they end before HH:MM ET, else held: …`); after closings with no MLB feed answer, an MLB
    closing ahead adds when it holds with no probe (`(held with no probe if they end within N s before a tick at or
    after HH:MM ET)`, that closing's T-35: _hold_unprobed's bound, next_tick)."""
    tick_at = utc(tick_at)
    now = utc(now or tick_at)
    fams = tuple(families or (fam,))
    day = ny_date(tick_at)
    head = f"  SLATE {fam} {day.isoformat()}"
    try:
        games = day_games(fam, day)
    except (FileNotFoundError, sqlite3.Error) as e:
        if dry_run:
            print(f"{head}: no stored schedule ({type(e).__name__}) — would do nothing")
        return 0
    if not games:
        if dry_run:
            print(f"{head}: no game that day — nothing to run")
        return 0
    first = min(g["start"] for g in games)
    due_at = slate_due(first, day)
    st = slate_state(fam, day.isoformat())
    folder = backup_folder()
    guard = timedelta(minutes=SLATE_GUARD_MIN)
    if dry_run:
        why = next((w for w in (chk() for chk in refusal_checks(fam, folder)) if w), None)
        live = [g for g in games if not started(g, tick_at)]
        ahead = closing_ahead(fams, tick_at, skip=planned)    # the tick's own closings run first: they hold nothing
        near = bool(ahead and ahead["run_at"] <= tick_at + guard)
        cad = timedelta(seconds=WATCH_CADENCE_S)
        # a closing due by the next tick holds the slate with no probe where a probe could not release it or could cost
        # that closing its T-35 (_hold_unprobed, as below); a tick with no closing of its own has no feed answer, and
        # is judged at its own time
        quiet = bool(not planned and ahead and ahead["run_at"] <= tick_at + cad
                     and _hold_unprobed(ahead, fams, tick_at, tick_at, None))
        # the tick's own closings answer for the feed when one is an MLB closing (watch() probes before it); else the
        # slate stage has no answer when they end, and an MLB closing due by the next tick then holds the slate with no
        # probe if they end inside FEED_PROBE_MAX_S before a tick that could start it, one at or after its T-35
        # (next_tick: the first such tick on this machine's cadence)
        answered = any(FAMILIES[f]["feed"] and not _family_refusal(f) for f, _ in planned)
        edge = (f" (held with no probe if they end within {FEED_PROBE_MAX_S} s before a tick at or after "
                f"{et(ahead['run_at'])[11:]})"
                if planned and not answered and ahead and FAMILIES[ahead["family"]]["feed"] else "")
        # the tick's own closings take time, up to SLATE_GUARD_MIN each (the guard's bound on a chain's hold of the
        # lock): a closing whose T-35 is inside the guard when they end holds the slate then, so no plain RUN
        later = bool(planned and ahead and not near and ahead["run_at"] <= tick_at + guard * (1 + len(planned)))
        if quiet:
            hold = f"held: {_hold_why(ahead)}"
        elif near and FAMILIES[ahead["family"]]["feed"]:      # no network here: both ways (slate_ahead)
            alt = closing_ahead(tuple(f for f in fams if not FAMILIES[f]["feed"]), tick_at, skip=planned)
            hold = (f"held if the MLB feed answers: {_hold_why(ahead)}; if it does not, "
                    + (f"held: {_hold_why(alt)}" if alt and alt["run_at"] <= tick_at + guard else
                       ("MISSED (the feed)" if FAMILIES[fam]["feed"] else "would RUN") + edge))
        elif later:
            hold = (f"would RUN if they end before {et(ahead['run_at'] - guard)[11:]}, else held"
                    + (" if the MLB feed answers" + edge if FAMILIES[ahead["family"]]["feed"] else "")
                    + f": {_hold_why(ahead)}")
        else:
            hold = f"held: {_hold_why(ahead)}" if near else None
        pre = ("would check the MLB feed, then " if FAMILIES[fam]["feed"] and not quiet   # the slate's own feed first
               else "")
        tag = ("done (a successful slate)" if st["success"] else
               f"done ({st['attempts']} attempts)" if st["attempts"] >= MAX_ATTEMPTS else
               f"not yet (due {et(due_at)[11:]})" if tick_at < due_at else
               f"would be REFUSED ({why})" if why else
               "every game has started: a miss" if not live else
               ("after this tick's closings: " if planned else "") + pre + (hold or "would RUN"))
        if "would RUN" in tag and tick is not None:   # one slate run per tick (addendum 134 item 1(ii))
            if tick.get("ran"):
                tag += f" on the next tick (one slate run per tick: {tick['ran']}'s first)"
            else:
                tick["ran"] = fam
        print(f"{head}: first kickoff {et(first)[11:]} · due {et(due_at)[11:]} · success "
              f"{'yes' if st['success'] else 'no'} · attempts {st['attempts']}/{MAX_ATTEMPTS} → {tag}")
        if live and "would RUN" in tag:
            steps = slate_steps(fam, day, live, tick_at, "RUN")
            for i, s in enumerate(steps, 1):
                print(f"    {i}. python cli.py {' '.join(s)}")
            # the run's order after the steps (addendum 133 item 3(a)): the plan names the exports/ file the kept
            # export is linked into (SOCCER's is the round's window file, not the kept name), as the closing's names
            # its closing file
            print(f"    then, once its checks pass: {steps[-1][steps[-1].index('--out') + 1]} linked into "
                  f"{SLATE_DIR}/{slate_file(fam, day)} · then the mirror push (--label slate) · then the page")
        return 0
    if tick_at < due_at or st["success"] or st["attempts"] >= MAX_ATTEMPTS:
        return 0
    base = {"kind": SLATE_KIND, "family": fam, "date": day.isoformat(),
            "run_id": f"{now:%Y%m%dT%H%M%SZ}-{fam.lower()}-slate", "trigger": "watch", "due": iso_z(due_at),
            "queued_at": iso_z(tick_at)}
    for check in refusal_checks(fam, folder):
        why = check()
        if why:
            return _slate_refuse(why, fam, day, base)
    if not any(not started(g, now) for g in games):
        record_slate_miss(fam, day, SLATE_ALL_STARTED,
                          text=f"SLATE {fam} {day.isoformat()} MISSED: {SLATE_ALL_STARTED} — no slate run",
                          queued_at=tick_at, due_at=due_at)
        return NOTIFIED
    # A closing due by the next tick holds the slate with no probe of the slate's own where the probe could not release
    # it or could cost that closing its T-35 (_hold_unprobed: the #590 review's probe-delay finding at cb1261d). An MLB
    # closing the tick has no feed answer for is otherwise probed for once here, below (an MLB slate's own check, or the
    # guard's): with the feed down it starts nothing and holds nothing (the feed-down finding at c789cc1, where a held
    # slate lost a kickoff).
    near = closing_ahead(fams, now)
    if (near and near["run_at"] <= now + timedelta(seconds=WATCH_CADENCE_S)
            and _hold_unprobed(near, fams, tick_at, now, (feed_probe or {}).get("ok"))):
        return record_slate_hold(fam, day, base, near, games=games, now=now)
    feed = None
    if FAMILIES[fam]["feed"]:         # A6, as the watch checks it before a closing: one miss a day, then silence.
        feed, detail = _tick_feed(feed_probe)   # Before the guard: unanswered, it pages RUN BY HAND at once
        if not feed:
            record_slate_miss(fam, day, "feed unreachable", detail=detail,
                              text=f"SLATE {fam} {day.isoformat()} MISSED: {FEED_MISS_TEXT} — RUN BY HAND: "
                                   f"{slate_block(fam, day)} · the watch keeps trying", queued_at=tick_at,
                              due_at=due_at)
            return NOTIFIED
    # The closings first (item 2(a): "The closing runs at T-35 are unchanged"): one watch process runs one thing at a
    # time, so a slate started inside SLATE_GUARD_MIN of a closing's T-35 would keep that closing's tick from starting.
    # A closing that cannot start (an MLB closing while the feed does not answer) holds nothing (slate_ahead).
    ahead = slate_ahead(fams, now, feed, feed_probe)
    if ahead and ahead["run_at"] <= now + guard:
        return record_slate_hold(fam, day, base, ahead, games=games, now=now)
    # at most one slate RUN per tick (addendum 134 item 1(ii)): after the tick's one, the next waits for the next tick
    if tick is not None and tick.get("ran"):
        return record_slate_deferred(fam, day, base, tick["ran"])
    # the wait for the lock ends SLATE_GUARD_MIN before the next closing's T-35: a slate that gets the lock then has
    # finished before that closing is due (a waiting slate never takes the lock ahead of a due closing)
    wait = float(SLATE_LOCK_WAIT_S)
    if ahead:
        wait = min(wait, (ahead["run_at"] - guard - now).total_seconds())
    t_entry = time.time()
    entered = False
    try:
        with acquire_lock(wait):
            entered = True
            held = now + timedelta(seconds=time.time() - t_entry)
            return _slate_under_lock(fam, day, base, folder, held, tick_at, due_at, tick)
    except TimeoutError:
        if entered:
            raise
        if wait < SLATE_LOCK_WAIT_S:  # the wait ended for the closing, not the full five minutes: a hold, no miss
            at = now + timedelta(seconds=time.time() - t_entry)
            return record_slate_hold(fam, day, base, ahead, why=_hold_why(ahead, lock=True), games=games, now=at)
        record_slate_miss(fam, day, "the chain lock was held", detail=f"waited {SLATE_LOCK_WAIT_S}s",
                          text=f"SLATE {fam} {day.isoformat()} MISSED: the chain lock was held through the "
                               f"{SLATE_LOCK_WAIT_S / 60:g}-minute wait — RUN BY HAND: {slate_block(fam, day)} · the "
                               "watch keeps trying", queued_at=tick_at, due_at=due_at)
        return NOTIFIED
    except Exception as e:  # noqa: BLE001 - a lock that cannot be taken is a failed attempt, receipted (as a closing)
        if entered:
            raise
        try:
            at = now + timedelta(seconds=time.time() - t_entry)
            rec, _ = _slate_rec(base, fam, day, st["attempts"] + 1, at, tick_at, due_at,
                                [g for g in games if not started(g, at)])
            rec.update({"failed": "lock", "error": c.redact(f"{type(e).__name__}: {e}")[:300]})
            rec["failure_notification"] = notify_failure(
                slate_failure_text(fam, day, f"the chain lock ({rec['error']})", rec["attempt"]), fam,
                title=f"{fam} slate")
            c.append_receipt(rec)
        except Exception as e2:  # noqa: BLE001 - the receipt store itself is not writable: the console says so
            print(f"✗ the failed slate could not be receipted either: {type(e2).__name__}")
            return 1                  # P3: not reported by the process, so the unit's failure path reports it
        return NOTIFIED


# ---------------------------------------------------------------------------------- setup checks (380.2) --

def preflight(shell_set: tuple[str, ...] = (), families: tuple[str, ...] | None = None,
              expect_role: str | None = None) -> list[str]:
    """380.2 (ARCHITECT): "The setup script reads each required setting where the launched job will find it: the
    checkout's .env or host.env, never the installing shell. A setting present only in the shell refuses the
    install, naming it. [...] The script proves it: it runs the run's own refusal checks in the environment the
    launched job will have, and refuses to install on any refusal." `shell_set`: the required settings the installing
    shell had set (names only). Run under the launched job's environment (the setup script uses env -i). Returns
    the refusals; no value is ever printed."""
    out = []
    for name in REQUIRED_SETTINGS:
        in_files = (c.parse_env_file(c.HOST_ENV).get(name) or c._dotenv().get(name) or "").strip()
        if name in shell_set and not in_files:
            out.append(f"{name} is set only in the installing shell: the launched job reads the checkout's .env "
                       "or host.env, never the shell")
    role = mirror_role()
    if expect_role and role and role != expect_role:   # Codex on #449: the laptop's installer takes the laptop's role
        out.append(f"{ROLE_SETTING} is {role!r} here; this machine is the {expect_role}: a push as {role} "
                   f"would write into the mirror's {role}/ side")
    folder = backup_folder()
    for fam in families or tuple(FAMILIES):
        for check in refusal_checks(fam, folder):
            why = check()
            if why and why not in out:
                out.append(why)
    return out


def test_page_body(families: tuple[str, ...] | None = None) -> str:
    """The test page's text: the families the watch is installed for (addendum 45 P5), then the machine's line."""
    return TEST_PAGE_BODY.format(families=", ".join(families or tuple(FAMILIES))) + "\n" + machine_line()


def test_page(families: tuple[str, ...] | None = None) -> dict:
    """M2 for the phone (380.2): "At install the script sends one test page through the card topic and says what the
    operator should have seen on his phone." Addendum 45: it names the families and ends with the machine's role."""
    return page_phone(TEST_PAGE_TITLE, test_page_body(families), "default")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Closing runs for every model family (MLB, NFL, SOCCER).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--family", required=True, type=str.upper, choices=tuple(FAMILIES))
    r.add_argument("--start", "--first-pitch", dest="start", default=None,
                   help="ISO UTC start time to close (default: the next unstarted one within 90 minutes)")
    r.add_argument("--dry-run", action="store_true")
    w = sub.add_parser("watch")
    w.add_argument("--family", action="append", type=str.upper, choices=tuple(FAMILIES), default=None)
    w.add_argument("--dry-run", action="store_true")
    pf = sub.add_parser("preflight")
    pf.add_argument("--shell-set", default="", help="comma-separated names the installing shell had set")
    pf.add_argument("--family", action="append", type=str.upper, choices=tuple(FAMILIES), default=None,
                    help="the families the watch will run for (addendum 45 P2/P5; repeatable; default all three)")
    pf.add_argument("--expect-role", choices=ROLES, default=None,
                    help="refuse unless SP_EXPORTS_MIRROR_ROLE is this role (the laptop's setup script: laptop)")
    tp = sub.add_parser("test-page")
    tp.add_argument("--family", action="append", type=str.upper, choices=tuple(FAMILIES), default=None)
    sub.add_parser("install-push")
    a = ap.parse_args(argv)
    fams = tuple(dict.fromkeys(a.family)) if a.cmd != "run" and getattr(a, "family", None) else None
    if a.cmd == "run":
        return run(family=a.family, start=a.start, dry_run=a.dry_run)
    if a.cmd == "watch":
        return watch(dry_run=a.dry_run, families=fams)
    if a.cmd == "preflight":
        bad = preflight(tuple(x.strip() for x in a.shell_set.split(",") if x.strip()), fams, a.expect_role)
        for b in bad:
            print(f"✗ REFUSED: {b}")
        if not bad:
            print(f"✓ preflight: every closing refusal check passes in this environment "
                  f"({', '.join(fams or tuple(FAMILIES))}; role {mirror_role()})")
        return 2 if bad else 0
    if a.cmd == "install-push":       # D1 (addendum 23): "M1 at install: [...] one mirror push [...] label install"
        why = _role_refusal()         # addendum 45 P1: no role, no push
        if why:
            print(f"✗ REFUSED: {why}")
            return 2
        res = push_mirror("install")
        print(f"install push (exports mirror, {mirror_role()}, label install): exit {res['exit']} "
              + " | ".join(res.get("tail") or []))
        return 0 if res.get("exit") == 0 else 1
    res = test_page(fams)
    print("test page: " + ("accepted by ntfy" if res.get("accepted") else
                           f"NOT accepted ({res.get('http') or res.get('error')})"))
    return 0 if res.get("accepted") else 1


if __name__ == "__main__":
    sys.exit(main())
