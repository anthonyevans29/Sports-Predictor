#!/usr/bin/env python3
"""CLOSING RUNS FOR EVERY MODEL FAMILY, PAGED BY T-30 (ARCHITECT 2026-10-09, addendum 21 item 3, C1-C10, and
addendum 22: #380 rulings 380.1-380.5, the strict-mode rule, the schedule read, reading 7). Built on #370's MLB
closing autopilot (addendum 13 item 3, addendum 16 item 2), which it replaces.

    closing.py run   --family MLB|NFL|SOCCER [--start ISO] [--dry-run]   (= python cli.py closing-run)
    closing.py watch [--family F] [--dry-run]                          (= python cli.py closing-watch; every minute)
    closing.py preflight [--shell-set NAMES]     the setup script's checks (380.2): the run's own refusals
    closing.py test-page                         one test page through the card topic (380.2, M2)
    closing.py install-push                      one exports-mirror push, label install (addendum 23 D1)

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

Refusals (receipted, exit 2), in order: R5 a backup folder under data/ (before anything else); SP_SKIP_FAMILIES
naming the family (MLB: laptop only); M1 SP_EXPORTS_MIRROR_REMOTE unset; C6 NTFY_CARD_TOPIC unset; R4 a malformed
--start; nothing to close (A4).

Receipts: kind "closing" (one line per run, success, failure, refusal or superseded) and kind "closing_miss" (the MLB
feed unreachable; the lock held into T-5; a due start time first seen inside T-5), once per start time and reason. The autopilot places nothing and
never opens Kalshi's trading API. --dry-run touches nothing: no step, no backup, no receipt, no push, no page, no
network.
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
CLOSING_HOLDS = (
    {"call": "PLAY", "exec_edge_under_pp": 4.0, "text": "paste to the architect before placing", "since": "2026-10-07",
     "families": ("MLB", "NFL")},
)
VOID = ("CANCELLED", "POSTPONED", "STALE_ORPHAN")      # never a game in any window
STARTED_STATUSES = ("LIVE", "FINISHED")
MIRROR_SETTING = "SP_EXPORTS_MIRROR_REMOTE"            # M1
CARD_TOPIC = "NTFY_CARD_TOPIC"                         # C6
REQUIRED_SETTINGS = (MIRROR_SETTING, CARD_TOPIC)       # 380.2: read where the launched job finds them
STAKED_CALLS = ("PLAY", "LADDER")                      # a call that stakes units (LADDER: soccer's double chance)
# R6 (+ 380.1): the failures of the run's own checks. Their export leaves exports/ (moved into logs/, named with the
# run id), so no call is left behind; a failed push or a failed page leaves the export in place.
# C (addendum 23): a run left with no game by the schedule read is "start moved".
OWN_CHECK_FAILURES = ("stale prices", "stale starters", "missing from export", "target started", "start moved")
# B2 (ARCHITECT 2026-10-09, addendum 23): "The phone page is the page. It is tried three times, ten seconds apart,
# before the run fails as 'page'. A screen notification that is not posted is recorded and changes nothing."
PAGE_TRIES = 3
PAGE_RETRY_S = 10
TEST_PAGE_TITLE = "Closing watch"
TEST_PAGE_BODY = "Test: the closing watch is installed (MLB, NFL, SOCCER). Pages arrive here by T-30."


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

def schedule(fam: str, now: datetime, hours: int = 6) -> list[dict]:
    """The family's stored schedule around `now`, read-only (mode=ro). No network. Status is the stored enum name."""
    lo, hi = (utc(now) - timedelta(hours=hours)), (utc(now) + timedelta(hours=hours))
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


def covered_ids(fam: str) -> set:
    """The games a closing has finished with: covered by a start time that has a success, or three attempts. C
    (addendum 23): a game that left a run because its start moved is a new start time for the watch, never finished
    with at the old one (a run's `covers` are the games left in it; `moved` names the ones that left)."""
    by_start: dict = {}
    for r in _attempts(fam):
        by_start.setdefault(r.get("start"), []).append(r)
    out = set()
    for rs in by_start.values():
        if any(r.get("exit") == 0 for r in rs) or len(rs) >= MAX_ATTEMPTS:
            for r in rs:              # a game an attempt found moved is not finished with at this start (C)
                gone = {x.get("match_id") for x in r.get("moved") or []}
                out.update(x.get("match_id") for x in r.get("covers") or [] if x.get("match_id") not in gone)
    return out


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


def page_sleep(seconds: float) -> None:
    """B2: the wait between phone page tries (tests replace it)."""
    time.sleep(seconds)


def push_mirror(label: str = "closing") -> dict:
    """M1: the exports mirror pushed as role laptop, label closing (docs/specs/exports-mirror.md, laptop step). D1
    (addendum 23): the setup script's one push at install uses label install."""
    argv = [sys.executable, str(Path(__file__).resolve().parent / "exports_mirror.py"), "push",
            "--role", "laptop", "--label", label]
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
        rec["integrity"] = c.integrity(tmp)              # opens the copy read-only
        if rec["integrity"] != "ok":
            raise RuntimeError(f"integrity_check: {rec['integrity']}")
        os.replace(tmp, dest)
        con = c.ro_connect(dest)
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
    for h in CLOSING_HOLDS:
        if fam in h["families"] and d.get("call") == h["call"] and (e is None or e < h["exec_edge_under_pp"]):
            return h["text"]
    return None


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
    return {"books": min((o.captured_at for o in sess), default=None),
            "kalshi": min(latest.values(), default=None), "kalshi_legs": latest}


def shows_books(r: dict) -> bool:
    """The export row shows books: its market block priced at least one complete book (bookmaker_count > 0)."""
    return bool(((r.get("market") or {}).get("bookmaker_count") or 0) > 0)


def shows_kalshi(r: dict) -> bool:
    """The export row shows a Kalshi quote: the HOME contract's bid/ask, any captured leg, or a kalshi market block."""
    return (r.get("kalshi_bid") is not None or r.get("kalshi_ask") is not None or bool(r.get("kalshi_legs"))
            or bool((r.get("market") or {}).get("kalshi")))


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


def page_text(fam: str, start: datetime, at: datetime, rows: list[dict], prev: dict) -> tuple[str, str, bool]:
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
    reading 7 as amended by addendum 25 2(iii): "C5's was and B3 read this."). Returns (title, body, high)."""
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
    n_pass = sum(1 for x in rows if x["call"] == "PASS")
    lines.append(f"PASS: {n_pass} game{'s' if n_pass != 1 else ''}")
    title = f"{fam} closing {utc(start).astimezone(NY):%H:%M} ET"
    return title, "\n".join(lines), bool(plays) or bool(dropped)


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


def _writer_receipt(fam: str, sha: str, recs: list[dict]) -> dict | None:
    """The newest closing receipt of the family that names `sha` as the export it wrote and carries the last calls it
    found (a receipt without them cannot be followed)."""
    hit = [r for r in recs if r.get("family") == fam and (r.get("export_written") or {}).get("sha256") == sha
           and isinstance(r.get("last_calls"), dict)]
    return hit[-1] if hit else None


def last_calls(fam: str, at: datetime) -> dict:
    """The last call of every game of the family found, read before the first step (the run's own export overwrites
    the file): {match_id: {"call": call text, "start": ISO, "source": where it was shown}}. The family's files in
    exports/, newest first: a file no closing receipt names supplies its calls (the file's call stands) for the games
    not yet found, and the walk goes on to older files; a file a closing run wrote (its receipt names its sha256)
    supplies the calls on that run's page, when its page went out, and, for every other game, the last calls that
    receipt recorded; the walk ends there (the receipt's calls already read every older file). A game whose start is
    more than LAST_CALL_KEEP_H hours before `at` is left out. A game nothing found has no last call (no 'was')."""
    keep = utc(at) - timedelta(hours=LAST_CALL_KEEP_H)
    ex = c.REPO / "exports"
    files = sorted(ex.glob(FAMILIES[fam]["export_glob"]), key=lambda p: p.stat().st_mtime,
                   reverse=True) if ex.is_dir() else []
    recs = receipts(("closing",))
    out: dict = {}

    def kept(start) -> bool:
        try:
            return parse_utc(start) >= keep
        except (TypeError, ValueError):
            return False
    for p in files:
        try:
            raw = p.read_bytes()
            doc = json.loads(raw)
        except (OSError, ValueError):
            continue
        calls = {}
        for r in doc.get("predictions") or []:
            mid, d = r.get("match_id"), r.get("desk")
            if mid is None or not d or not d.get("call") or not kept(r.get("utc_date")):
                continue
            calls.setdefault(mid, {"call": call_text(r, d), "start": iso_z(parse_utc(r["utc_date"]))})
        w = _writer_receipt(fam, hashlib.sha256(raw).hexdigest(), recs)
        if w is None:                 # not a closing run's export, or the chain cannot be followed: the file's call
            for mid, v in calls.items():
                out.setdefault(mid, {**v, "source": p.name})
            continue
        paged = {x.get("match_id") for x in w.get("desk_rows") or []} if _paged(w) else set()
        for mid in paged & set(calls):                 # the call on that run's page
            out.setdefault(mid, {**calls[mid], "source": f"page {w.get('run_id')}"})
        for k, v in w["last_calls"].items():           # every other game: the last call that run found
            mid = int(k) if str(k).lstrip("-").isdigit() else k
            if isinstance(v, dict) and v.get("call") and kept(v.get("start")):
                out.setdefault(mid, v)
        break
    return out


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
    return [lambda: _backup_folder_refusal(folder), lambda: _family_refusal(fam), _mirror_refusal,
            _card_topic_refusal, lambda: _start_refusal(start)]


def export_candidates(fam: str, start: datetime, at: datetime) -> list[str]:
    """The file the family's export step writes. MLB: exports/mlb_MLB_<first pitch's NY date>.json (--date). NFL /
    SOCCER: the export's own name, stamped with the UTC date the export runs (src/walters/nfl_predict.py; cli.py
    export-predictions with no --date): today's and tomorrow's, the run picks the one written by its own step."""
    if fam == "MLB":
        return [f"exports/mlb_MLB_{ny_date(start).isoformat()}.json"]
    stem = {"NFL": "nfl_predictions_", "SOCCER": "soccer_PL_"}[fam]
    d = utc(at).date()
    return [f"exports/{stem}{x.isoformat()}.json" for x in (d, d + timedelta(days=1))]


def resolve_steps(fam: str, start: datetime, covers: list[dict], run_start: datetime) -> list[list[str]]:
    """The family's closing chain with its run-time values. MLB: {today} = the first pitch's NY date (A1 of #370),
    {match_ids} = the covered games (A1 of addendum 23: the schedule read names them). NFL / SOCCER (C3):
    {match_ids} = the covered games (the odds and the injuries steps); the schedule read (A1 as amended, addendum 25
    2(i): NFL takes the SOCCER form): {start_day}/{end_day} = the UTC dates of the first and last covered start (one
    read per UTC day; an identical second read is dropped), {start_day_ids}/{end_day_ids} = that day's covered
    games."""
    chain = FAMILIES[fam]["chain"]
    ids = ",".join(str(g["match_id"]) for g in sorted(covers, key=lambda g: g["match_id"]))
    if fam == "MLB":                  # A1: the schedule read names the covered games
        return sp_run.resolve(chain, {"match_ids": ids}, ny_date(start))
    last = max(g["start"] for g in covers)

    def day_ids(day):                 # A1: each by-date read names that UTC day's covered games
        return ",".join(str(g["match_id"]) for g in sorted(covers, key=lambda g: g["match_id"])
                        if utc(g["start"]).date() == day)
    v = {"start_day": utc(start).date().isoformat(), "end_day": last.date().isoformat(), "match_ids": ids,
         "start_day_ids": day_ids(utc(start).date()), "end_day_ids": day_ids(last.date())}
    out: list[list[str]] = []
    for st in sp_run.resolve(chain, v, utc(start).date()):
        if not out or st != out[-1]:
            out.append(st)
    return out


def plan(fam: str, now: datetime, start: str | None) -> dict:
    """The target start time and the games it covers, from the stored schedule (read-only). `refused` when there is
    nothing to close. A manual run with no --start targets the next unstarted start within 90 minutes (#370, accepted
    as built); a watch-started run passes its start time."""
    games = schedule(fam, now)
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


def notify_failure(text: str, fam: str = "") -> dict:
    """Best effort, both channels: the result is recorded in the receipt and changes nothing else."""
    title = f"{fam} closing".strip()
    try:
        res = notify(text, title=title)
    except Exception as e:  # noqa: BLE001
        res = {"posted": False, "text": text, "error": f"{type(e).__name__}: {e}"[:200]}
    try:
        ph = page_phone(title, text, "high") if not _card_topic_refusal() else {"accepted": False,
                                                                                 "skipped": f"{CARD_TOPIC} unset"}
    except Exception as e:  # noqa: BLE001
        ph = {"accepted": False, "error": type(e).__name__}
    return {"text": text, "posted": res.get("posted"),
            **({"skipped": res["skipped"]} if res.get("skipped") else {}),
            **({"error": res["error"]} if res.get("error") else {}), "phone": ph}


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
    src = c.REPO / rec["export"]
    if not src.is_file():
        return
    dest = c.REPO / "logs" / f"{run_id}.{src.name}"
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
    moved = start_moved(covers, s)
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
        written = [p for p in export_candidates(fam, s, held)
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
    steps = resolve_steps(fam, s, covers, held)
    rec["planned_steps"] = len(steps)
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
    cands = export_candidates(fam, s, held)
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
    cover_ids = {g["match_id"] for g in covers}
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
    rec["desk_rows"] = [{k: x[k] for k in ("match_id", "start", "call", "pick", "units", "exec_edge_pp", "hold",
                                           "value_shadow", "quarantine_shadow", "starters_listed",
                                           "unresolved_injuries")} for x in rows]
    print(f"\n=== {fam} closing summary · {len(rows)} game(s) starting {et(s)} to "
          f"{utc(s + timedelta(minutes=COVER_MIN)).astimezone(NY):%H:%M} ET")
    for x in rows:
        print(summary_block(x))
    # B1 (ARCHITECT 2026-10-09, addendum 23): "The page goes out as soon as the run's own checks have passed. The
    # mirror push follows. A closing whose page went out is not run again for a failed push: the failure is receipted
    # and notified, and the next push from this machine carries the file." C5/C6 + B2: ONE page per run, on the phone
    # (ntfy card topic, three tries ten seconds apart), then the laptop's screen (recorded, changes nothing).
    at = held + timedelta(seconds=time.time() - t0)
    title, body, high = page_text(fam, s, at, rows, prev)
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
                   "phone": ph, "tries": len(tries)}
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
    rec["push"] = push_mirror()
    print(f"· exports mirror (laptop, closing): exit {rec['push']['exit']} {' | '.join(rec['push']['tail'])}")
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
            return 1
    games = schedule(fam, held)
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
        return 1
    wall0 = _WALL() - 1.0     # the export must be written by this run's own step (1s: coarse filesystem mtimes)
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
              + {"page": f"ntfy did not accept the page in {PAGE_TRIES} tries; nothing pushed, the export stays on "
                         "disk, the watch retries",
                 **{k: "nothing pushed or paged; the export was moved into logs/" for k in OWN_CHECK_FAILURES},
                 "start moved": "no further step ran after the schedule read; nothing exported, pushed or paged"}.get(
                  rec.get("failed"), "nothing exported, pushed or paged after the failure"))
        return 1
    print(f"✓ closing-run {fam}: {len(rec['steps'])}/{rec.get('planned_steps')} steps · {rec['export']} · "
          f"{len(rec['desk_rows'])} Desk row(s) · page accepted · push exit {rec['push']['exit']}"
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
        for i, st in enumerate(resolve_steps(fam, s, p["covers"], now), 1):
            print(f"  {i}. python cli.py {' '.join(st)}")
        print(f"  export: {' or '.join(export_candidates(fam, s, now))} · checks: started (R1), start moved (C), "
              "missing, prices (R2, A5 legs)"
              + (", starters (380.1)" if FAMILIES[fam]["starters"] else "")
              + " · page: ntfy card topic (3 tries) + screen · then push: exports_mirror.py push --role laptop "
                "--label closing")
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
        return 1
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
        return 1


# -------------------------------------------------------------------------------------------------- watch --

def due(fam: str, now: datetime) -> dict:
    """The watch's view of one family at `now` (no network): its start times (C2 groups), and which is due."""
    games = schedule(fam, now)
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
    `now` (tests) fixes the tick's time for every run; else each queued run reads clock() when it starts (Codex on
    #385: the time spent running earlier closings in the same tick counts toward the next run's T-5 / started
    checks and its T-minus)."""
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
        return 0
    rc = 0
    inside_why = "inside T-5 when the watch saw it: no attempt starts inside T-5"
    for fam, d in plans:              # a start time first found inside T-5 with no closing: a miss, once
        if _family_refusal(fam):
            continue                  # its refusal is receipted when a start time is due, not as a miss
        for g in d["inside"]:
            start = iso_z(g["start"])
            record_miss(fam, start, inside_why)        # B6: once per start time and reason
    todo = sorted(((g["start"], fam) for fam, d in plans for g in d["due"]))
    for s, fam in todo:
        start = iso_z(s)
        if FAMILIES[fam]["feed"] and not _family_refusal(fam):
            ok, detail = feed_answers()
            if not ok:                # B6: one miss per first pitch; later ticks keep trying, silently
                if record_miss(fam, start, "feed unreachable", detail=detail, text=FEED_MISS_TEXT):
                    print(f"✗ {FEED_MISS_TEXT} ({detail}) — nothing run; miss recorded for {fam} {start}; the "
                          "watch keeps trying")
                continue
        r = run(family=fam, start=start, trigger="watch", now=clock() if fixed_now is None else utc(fixed_now))
        rc = rc or (0 if r == 0 else r)
    return rc


# ---------------------------------------------------------------------------------- setup checks (380.2) --

def preflight(shell_set: tuple[str, ...] = (), families: tuple[str, ...] | None = None) -> list[str]:
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
    folder = backup_folder()
    for fam in families or tuple(FAMILIES):
        for check in refusal_checks(fam, folder):
            why = check()
            if why and why not in out:
                out.append(why)
    return out


def test_page() -> dict:
    """M2 for the phone (380.2): "At install the script sends one test page through the card topic and says what the
    operator should have seen on his phone." """
    return page_phone(TEST_PAGE_TITLE, TEST_PAGE_BODY, "default")


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
    sub.add_parser("test-page")
    sub.add_parser("install-push")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        return run(family=a.family, start=a.start, dry_run=a.dry_run)
    if a.cmd == "watch":
        return watch(dry_run=a.dry_run, families=tuple(a.family) if a.family else None)
    if a.cmd == "preflight":
        bad = preflight(tuple(x.strip() for x in a.shell_set.split(",") if x.strip()))
        for b in bad:
            print(f"✗ REFUSED: {b}")
        if not bad:
            print(f"✓ preflight: every closing refusal check passes in this environment ({', '.join(FAMILIES)})")
        return 2 if bad else 0
    if a.cmd == "install-push":       # D1 (addendum 23): "M1 at install: [...] one mirror push [...] label install"
        res = push_mirror("install")
        print(f"install push (exports mirror, laptop, label install): exit {res['exit']} "
              + " | ".join(res.get("tail") or []))
        return 0 if res.get("exit") == 0 else 1
    res = test_page()
    print("test page: " + ("accepted by ntfy" if res.get("accepted") else
                           f"NOT accepted ({res.get('http') or res.get('error')})"))
    return 0 if res.get("accepted") else 1


if __name__ == "__main__":
    sys.exit(main())
