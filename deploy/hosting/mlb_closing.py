#!/usr/bin/env python3
"""MLB CLOSING-RUN AUTOPILOT (ARCHITECT 2026-10-08, addendum 13 item 3, Q2, RULED). LAPTOP ONLY: "the host cannot
reach the MLB feed."

    mlb_closing.py run   [--first-pitch ISO] [--dry-run]     (= python cli.py mlb-closing-run)
    mlb_closing.py watch [--dry-run]                         (= python cli.py mlb-closing-watch; the 5-minute tick)

run (A1-A4): refusals first, each receipted, exit 2: a backup folder under data/ (R5, checked before anything
else), the laptop-only rule, SP_EXPORTS_MIRROR_REMOTE unset (M1), a malformed --first-pitch (R4), nothing to close
(A4). Then, under the chain lock (sp_common.db_lock) from the backup check until the receipt line is written (R3): a
.backup dated today in the operator's backup folder (taken through the .backup API and opened when none exists),
then the ten steps of CHAINS["mlb-closing"] (chains.py: the mlb-preslate steps, the export with --date and --desk),
{today} = the first pitch's America/New_York date. Stops at the first failed step; after a failure nothing is
exported, pushed or notified. When the steps have finished, ONE started test (R1): a game is started when its stored
status is then LIVE or FINISHED, or its first pitch is at or before that moment; a started target fails the run. The
prices are checked (R2): every summary game's book rows and Kalshi quote, where the export shows them, were captured
at or after the run's start. On success: one summary block per unstarted game whose first pitch is within 90 minutes,
the exports mirror pushed as role laptop, label closing, and one notification per game. A run that fails its own
checks (stale prices, a game missing from the export, a started target) moves its export out of exports/ into logs/
(R6). One receipt line (kind "mlb_closing") either way; a watch-started run that does not succeed posts one
notification (best effort).

watch (A5-A6): no network to decide. From the stored schedule, the MLB games not started whose first pitch is 5 to
65 minutes away. A first-pitch time with no successful closing receipt and fewer than three attempts starts one run,
after checking the MLB feed answers; an unreachable feed runs nothing, notifies and records a miss
(kind "mlb_closing_miss"). Otherwise exit 0, silent.

The autopilot places nothing and never opens Kalshi's trading API. --dry-run (A9) touches nothing on either command:
no step, no backup, no receipt, no push, no notification, no network.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
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
import sp_run  # noqa: E402

CHAIN = "mlb-closing"
NY = ZoneInfo("America/New_York")
SUMMARY_WINDOW_MIN = 90                    # A1: a summary block per game whose first pitch is within 90 minutes
WATCH_MIN, WATCH_MAX = 5, 65               # A5: first pitch 5 to 65 minutes away
MAX_ATTEMPTS = 3                           # A6: at most three attempts for one first-pitch time
MIRROR_TIMEOUT_S = 90
# A6: "the MLB feed" is the statsapi base the MLB adapter uses (src/adapters/mlb_stats_api.py _BASE_URL; a test pins
# the two together). "Answers" = HTTP 200 from one tiny GET (/sports/1). The host gets a 406 from it (the ASN).
FEED_BASE = "https://statsapi.mlb.com/api/v1"
FEED_PROBE = FEED_BASE + "/sports/1"
FEED_TIMEOUT_S = 8
FEED_MISS_TEXT = "MLB feed unreachable: VPN on, Tailscale off"
NOTIFY_TITLE = "MLB closing"
# A7: THE OPERATOR HOLD OF 2026-10-07. One row per hold; lifting a hold is deleting its row (a one-line PR).
# A PLAY whose exec edge is under the bar, or unknown (law 4), carries the text on its notification and order line.
CLOSING_HOLDS = (
    {"call": "PLAY", "exec_edge_under_pp": 4.0, "text": "paste to the architect before placing", "since": "2026-10-07"},
)
VOID = ("CANCELLED", "POSTPONED", "STALE_ORPHAN")      # never a game in any window
STARTED_STATUSES = ("LIVE", "FINISHED")
MIRROR_SETTING = "SP_EXPORTS_MIRROR_REMOTE"            # M1: a closing run pushes the mirror or it is not a success
# R6: the failures of the run's own checks. Their export leaves exports/ (moved into logs/, named with the run id),
# so no call is left behind; a failed push or a failed notification leaves the export in place.
OWN_CHECK_FAILURES = ("stale prices", "missing from export", "target started")


# ------------------------------------------------------------------------------------------------- time --

def utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_utc(s: str) -> datetime:
    """A stored utc_date ('2026-10-08 23:05:00.000000') or an ISO string ('...T23:05:00Z') as aware UTC."""
    s = str(s).strip().replace("Z", "+00:00")
    d = datetime.fromisoformat(s if "+" in s[10:] else s[:19])
    return utc(d).astimezone(timezone.utc)


def iso_z(dt: datetime) -> str:
    return utc(dt).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ny_date(dt: datetime) -> date:
    """A1: the first pitch's date in America/New_York (the feed's own date), never the UTC date."""
    return utc(dt).astimezone(NY).date()


def et(dt: datetime) -> str:
    return utc(dt).astimezone(NY).strftime("%Y-%m-%d %H:%M ET")


# --------------------------------------------------------------------------------------------- schedule --

def schedule(now: datetime, hours: int = 6) -> list[dict]:
    """The stored MLB schedule around `now`, read-only (mode=ro). No network. Status is the stored enum name."""
    lo, hi = (utc(now) - timedelta(hours=hours)), (utc(now) + timedelta(hours=hours))
    fmt = "%Y-%m-%d %H:%M:%S"
    con = c.ro_connect(c.db_path())
    try:
        rows = con.execute(
            "SELECT m.id, m.utc_date, m.status, ht.name, at.name FROM matches m "
            "JOIN competitions co ON co.id = m.competition_id "
            "LEFT JOIN teams ht ON ht.id = m.home_team_id LEFT JOIN teams at ON at.id = m.away_team_id "
            "WHERE co.code = 'MLB' AND m.utc_date >= ? AND m.utc_date < ? ORDER BY m.utc_date, m.id",
            (lo.strftime(fmt), hi.strftime(fmt))).fetchall()
    finally:
        con.close()
    return [{"match_id": i, "first_pitch": parse_utc(d), "status": str(s or "").upper(), "home": h, "away": a}
            for i, d, s, h, a in rows if str(s or "").upper() not in VOID]


def started(g: dict, now: datetime) -> bool:
    return g["status"] in STARTED_STATUSES or g["first_pitch"] <= utc(now)


def minutes_to(g: dict, now: datetime) -> float:
    return (g["first_pitch"] - utc(now)).total_seconds() / 60


def watch_window(games: list[dict], now: datetime) -> list[dict]:
    """A5: the MLB games not started whose first pitch is 5 to 65 minutes away."""
    return [g for g in games if not started(g, now) and WATCH_MIN <= minutes_to(g, now) <= WATCH_MAX]


def run_window(games: list[dict], now: datetime) -> list[dict]:
    """The run's window: games whose first pitch is within 90 minutes of now, either side (A4 checks it)."""
    return [g for g in games if abs(minutes_to(g, now)) <= SUMMARY_WINDOW_MIN]


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


def closing_state(first_pitch: str) -> dict:
    """A5/A6 for one first-pitch time: a successful closing receipt? how many run attempts? (refusals are not runs)"""
    runs = [r for r in receipts(("mlb_closing",)) if r.get("first_pitch") == first_pitch and not r.get("refused")]
    misses = [r for r in receipts(("mlb_closing_miss",)) if r.get("first_pitch") == first_pitch]
    return {"success": any(r.get("exit") == 0 for r in runs), "attempts": len(runs), "misses": len(misses)}


# --------------------------------------------------------------------------------------- side effects --
# Each is a module-level function so tests replace it; none is reached by --dry-run.

def feed_answers() -> tuple[bool, str]:
    """A6: one GET to the MLB feed. Answers = HTTP 200."""
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


def notify(body: str, title: str = NOTIFY_TITLE) -> dict:
    """A macOS notification via osascript. Off macOS nothing is posted and the line says so."""
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


def push_mirror() -> dict:
    """A1: the exports mirror pushed as role laptop, label closing (docs/specs/exports-mirror.md, laptop step)."""
    argv = [sys.executable, str(Path(__file__).resolve().parent / "exports_mirror.py"), "push",
            "--role", "laptop", "--label", "closing"]
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


# A step that REPORTS a failure on its console but exits 0 (Codex on #370). The shared commands keep their exit
# behaviour (host chains depend on it); the closing run reads the console instead. Every failure message the
# command prints, read from cli.py (law 1):
#   sync-kalshi  "✗ Kalshi sync failed: <exception>"  (sync_kalshi_mlb raised: network / DNS / API)
#                "Kalshi sync: <reason>"              (sync_kalshi_mlb returned ok False: no open markets,
#                                                      market fetch failed, series not resolved, competition missing)
# Both are followed by at most two lines before the command returns, so they are inside sp_run's 5-line tail.
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


def take_backup(folder: Path, day: date) -> dict:
    """The .backup API (Connection.backup, the sqlite3 CLI's .backup), then the copy is OPENED and checked
    (PRAGMA integrity_check). Never cp; never under data/ (law 5); never overwrites. Caller holds the lock."""
    dest = folder / f"sports_{day.isoformat()}.db"
    if dest.exists():
        dest = folder / f"sports_{day.isoformat()}_closing_{c.utc_now():%H%M%S}.db"
    tmp = dest.with_suffix(".db.partial")
    rec = {"file": str(dest), "taken": True, "opens": False, "integrity": None}
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
        os.chmod(tmp, 0o600)
        rec["integrity"] = c.integrity(tmp)              # opens the copy read-only
        if rec["integrity"] != "ok":
            raise RuntimeError(f"integrity_check: {rec['integrity']}")
        tmp.rename(dest)
        con = c.ro_connect(dest)
        try:
            con.execute("SELECT count(*) FROM sqlite_master").fetchone()
        finally:
            con.close()
        rec["opens"] = True
        rec["sha256"] = c.sha256_file(dest)
        dest.with_name(dest.name + ".sha256").write_text(f"{rec['sha256']}  {dest.name}\n")
    except (Exception, SystemExit) as e:  # noqa: BLE001 - receipted (a law-5 refusal too), then the run fails
        rec["error"] = c.redact(f"{type(e).__name__}: {e}")
        if tmp.parent.exists():
            tmp.unlink(missing_ok=True)
    return rec


# ----------------------------------------------------------------------------------------------- summary --

def hold_for(d: dict) -> str | None:
    """A7: the hold text a Desk row carries, from CLOSING_HOLDS (an unknown exec edge is under the bar)."""
    e = ((d.get("exec") or {}).get("edge_pp"))
    for h in CLOSING_HOLDS:
        if d.get("call") == h["call"] and (e is None or e < h["exec_edge_under_pp"]):
            return h["text"]
    return None


def _pp(x) -> str:
    return "n/a" if x is None else f"{x:+.1f}pp"


def _r2(x):
    return None if x is None else round(x, 2)


def _units(x) -> str:
    return f"{(x or 0):g}u"


def pick_team(row: dict, d: dict) -> str:
    p = d.get("pick")
    return {"HOME": row.get("home_team"), "AWAY": row.get("away_team")}.get(p) or (p or "-")


def desk_rows(doc: dict, now: datetime, done: datetime | None = None, started_ids=frozenset()) -> list[dict]:
    """The export's Desk rows whose first pitch is within 90 minutes of the run's start `now`, less the games the
    ONE started test (R1, ARCHITECT 2026-10-08) calls started at `done`, the moment the steps finished: a stored
    status then LIVE or FINISHED (`started_ids`) or a first pitch at or before `done`. A started game has no summary
    block and no notification (the Desk's started rule already makes its row PASS)."""
    out = []
    for r in doc.get("predictions") or []:
        d = r.get("desk")
        if not d or not r.get("utc_date"):
            continue
        fp = parse_utc(r["utc_date"])
        m = (fp - utc(now)).total_seconds() / 60
        if not 0 < m <= SUMMARY_WINDOW_MIN:
            continue
        if r.get("match_id") in started_ids or fp <= utc(done or now):
            continue
        out.append({"match_id": r.get("match_id"), "first_pitch": iso_z(fp), "first_pitch_et": et(fp),
                    "minutes": round(m), "away": r.get("away_team"), "home": r.get("home_team"),
                    "call": d.get("call"), "pick": pick_team(r, d), "units": d.get("units") or 0,
                    "edge_pp": _r2(d.get("edge_pp")), "exec_edge_pp": _r2((d.get("exec") or {}).get("edge_pp")),
                    "order": (d.get("order") or {}).get("text"), "order_why": (d.get("order") or {}).get("why"),
                    "reason": d.get("reason"), "pass_kind": d.get("pass_kind"),
                    "kalshi_only_hold": d.get("kalshi_only_hold"), "hold": hold_for(d)})
    return sorted(out, key=lambda x: (x["first_pitch"], x["match_id"] or 0))


def missing_from_export(doc: dict, now: datetime, done: datetime | None = None,
                        games: list[dict] | None = None) -> list[dict]:
    """Codex on #370: every MLB game in the STORED schedule (re-read after the steps synced it) whose first pitch is
    within 90 minutes of the run's start and that is NOT started at `done` (R1: the one started test, taken when the
    steps have finished) must have a Desk row in the export. Returns the ones that do not. A started game is not
    required."""
    have = {r.get("match_id") for r in doc.get("predictions") or [] if r.get("desk")}
    games = schedule(now) if games is None else games
    need = [g for g in games if 0 < minutes_to(g, now) <= SUMMARY_WINDOW_MIN and not started(g, done or now)]
    return [{"match_id": g["match_id"], "first_pitch": iso_z(g["first_pitch"]), "first_pitch_et": et(g["first_pitch"]),
             "away": g["away"], "home": g["home"], "reason": "missing from export"}
            for g in need if g["match_id"] not in have]


def target_started(games: list[dict], first_pitch: datetime, done: datetime) -> str | None:
    """R1: the target first pitch has started when that moment is at or before `done`, or when every stored game at
    that first pitch has a stored status (re-read after the steps) of LIVE or FINISHED. Returns why, else None."""
    if utc(first_pitch) <= utc(done):
        return f"first pitch {iso_z(first_pitch)} at or before {iso_z(done)}, when the steps finished"
    tg = [g for g in games if g["first_pitch"] == utc(first_pitch)]
    if tg and all(g["status"] in STARTED_STATUSES for g in tg):
        return "stored status " + "/".join(sorted({g["status"] for g in tg})) + " when the steps finished"
    return None


# ------------------------------------------------------------------------------------------------ prices --
# R2 (ARCHITECT 2026-10-08, #370 READ): "The run checks its prices, not a step's console." The capture times are read
# from the stored rows the export read (src/walters/export.py _collect_rows / _summarize_market, law 1), read-only:
#   books   table `odds`: the match's market '1X2' rows with captured_at strictly before the first pitch, reduced to
#           the LAST CAPTURE SESSION by src/walters/close.py last_capture (the one close contract the export's market
#           block uses). Capture time = the earliest captured_at among those rows (every row the export read).
#   Kalshi  table `odds_snapshots`, source 'kalshi': per selection the latest row with captured_at strictly before
#           the first pitch (the export's in-game guard, first-wins per selection). Capture time = the earliest of
#           those per-selection latest captures (the quote the export shows is built from all of them).

def _close_contract():
    root = str(Path(__file__).resolve().parents[2])
    if root not in sys.path:
        sys.path.insert(0, root)
    from src.walters.close import last_capture
    return last_capture


def price_captures(con: sqlite3.Connection, match_id, first_pitch: datetime) -> dict:
    """{"books": datetime|None, "kalshi": datetime|None}: the capture times of the stored rows the export read."""
    fp = utc(first_pitch)
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
            "kalshi": min(latest.values(), default=None)}


def shows_books(r: dict) -> bool:
    """The export row shows books: its market block priced at least one complete book (bookmaker_count > 0)."""
    return bool(((r.get("market") or {}).get("bookmaker_count") or 0) > 0)


def shows_kalshi(r: dict) -> bool:
    """The export row shows a Kalshi quote: the HOME contract's bid/ask, any captured leg, or a kalshi market block."""
    return (r.get("kalshi_bid") is not None or r.get("kalshi_ask") is not None or bool(r.get("kalshi_legs"))
            or bool((r.get("market") or {}).get("kalshi")))


def stale_prices(doc: dict, rows: list[dict], run_start: datetime) -> list[dict]:
    """R2: for every game in the summary, a price the export shows that was captured before the run's start. A game
    with no books, or with no Kalshi quote, is not stale on that count (the Desk already rules on it). A price the
    export shows with no stored capture time is stale too (law 4: never a guessed freshness)."""
    by_id = {r.get("match_id"): r for r in doc.get("predictions") or []}
    start = utc(run_start)
    out = []
    con = c.ro_connect(c.db_path())
    try:
        for x in rows:
            r = by_id.get(x["match_id"]) or {}
            caps = price_captures(con, x["match_id"], parse_utc(x["first_pitch"]))
            for kind, shown in (("books", shows_books(r)), ("kalshi", shows_kalshi(r))):
                if not shown:
                    continue
                at = caps[kind]
                if at is None or at < start:
                    out.append({"match_id": x["match_id"], "game": f"{x['away']} @ {x['home']}",
                                "first_pitch_et": x["first_pitch_et"], "price": kind,
                                "captured_at": iso_z(at) if at else None, "run_start": iso_z(start)})
    finally:
        con.close()
    return out


def summary_block(x: dict) -> str:
    lines = [f"── {x['first_pitch_et']} (T-{x['minutes']}m) · {x['away']} @ {x['home']}  [match {x['match_id']}]",
             f"   call   {x['call']} · pick {x['pick']} · {_units(x['units'])} · edge {_pp(x['edge_pp'])} "
             f"· exec edge {_pp(x['exec_edge_pp'])}"]
    if x["call"] in ("PLAY", "LADDER"):
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
    return "\n".join(lines)


def notification_text(x: dict) -> str:
    """A7: first pitch, the call, the pick, units and exec edge (+ the hold)."""
    t = (f"{x['first_pitch_et'][11:]} {x['away']} @ {x['home']}: {x['call']} {x['pick']} {_units(x['units'])} "
         f"exec {_pp(x['exec_edge_pp'])}")
    return t + (f" · {x['hold']}" if x["hold"] else "")


# ---------------------------------------------------------------------------------------------------- run --

def _laptop_refusal() -> str | None:
    skip = {s.strip().upper() for s in (c.setting("SP_SKIP_FAMILIES") or "").split(",") if s.strip()}
    if "MLB" in skip:
        return "laptop only: SP_SKIP_FAMILIES names MLB here (the host cannot reach the MLB feed)"
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
    """M1 (ARCHITECT 2026-10-08): "A closing run pushes the mirror or it is not a success. If SP_EXPORTS_MIRROR_REMOTE
    is not set, mlb-closing-run refuses before the first step, receipted, naming the setting." """
    if not (c.setting(MIRROR_SETTING) or "").strip():
        return (f"{MIRROR_SETTING} is not set (environment, host.env, the checkout's .env): a closing run pushes the "
                "exports mirror or it is not a success")
    return None


def _first_pitch_refusal(first_pitch: str | None) -> str | None:
    """R4 (ARCHITECT 2026-10-08): a malformed --first-pitch is "a receipted refusal, exit 2, like the other
    refusals"."""
    if first_pitch is None:
        return None
    try:
        parse_utc(first_pitch)
    except (TypeError, ValueError) as e:
        return f"malformed --first-pitch {first_pitch!r} (ISO UTC expected, e.g. 2026-10-08T23:05:00Z): {e}"[:300]
    return None


def plan(now: datetime, first_pitch: str | None) -> dict:
    """Target first pitch, NY date and steps, from the stored schedule (read-only). `refused` when A4 says so."""
    games = schedule(now)
    win = run_window(games, now)
    live = [g for g in win if not started(g, now)]
    if not live:
        why = ("every game in the window has started" if win else
               f"no MLB game with first pitch within {SUMMARY_WINDOW_MIN} minutes")
        return {"refused": f"A4: {why} — nothing to close", "window": win}
    if first_pitch:
        fp = parse_utc(first_pitch)
        if not any(g["first_pitch"] == fp for g in live):
            return {"refused": f"no unstarted MLB game at first pitch {iso_z(fp)} in the window", "window": win}
    else:
        fp = live[0]["first_pitch"]
    day = ny_date(fp)
    steps = sp_run.resolve(CHAIN, {}, day)
    return {"first_pitch": iso_z(fp), "first_pitch_et": et(fp), "date_ny": day.isoformat(), "steps": steps,
            "window": win, "export": f"exports/mlb_MLB_{day.isoformat()}.json"}


# --------------------------------------------------------------------------------- failed-run notification --
# ARCHITECT 2026-10-08 (#370 READ): "Silence must never mean a closing that did not happen. Every watch-started run
# that does not succeed posts one notification: the first pitch, what failed or why it refused, and for a failed
# attempt its number out of three. The third says no further attempt will run for that first pitch. A manual run
# prints to the console, as now. These notifications are best effort: one that cannot be posted is recorded in the
# receipt and changes nothing else."

def _fp_label(first_pitch: str | None) -> str:
    try:
        return et(parse_utc(first_pitch)) if first_pitch else "no first pitch"
    except (TypeError, ValueError):
        return f"first pitch {first_pitch!r}"


def failure_text(first_pitch: str | None, failed: str | None = None, refused: str | None = None,
                 attempt: int | None = None) -> str:
    head = f"Closing {_fp_label(first_pitch)}: "
    if refused:
        return head + f"REFUSED: {refused}"
    t = head + f"FAILED: {failed} · attempt {attempt}/{MAX_ATTEMPTS}"
    if attempt is not None and attempt >= MAX_ATTEMPTS:
        t += " · no further attempt will run for this first pitch"
    return t


def notify_failure(text: str) -> dict:
    """Best effort: the result is recorded in the receipt and changes nothing else."""
    try:
        res = notify(text, title=NOTIFY_TITLE)
    except Exception as e:  # noqa: BLE001
        res = {"posted": False, "text": text, "error": f"{type(e).__name__}: {e}"[:200]}
    return {"text": text, "posted": res.get("posted"),
            **({"skipped": res["skipped"]} if res.get("skipped") else {}),
            **({"error": res["error"]} if res.get("error") else {})}


def _refuse(why: str, first_pitch: str | None, base: dict, trigger: str, dry_run: bool, code: int = 2) -> int:
    print(("DRY RUN mlb-closing-run: would REFUSE: " if dry_run else "✗ mlb-closing-run REFUSED: ") + why)
    if dry_run:
        return code
    rec = {**base, "first_pitch": first_pitch, "exit": 2, "refused": why, "steps": [], "export": None,
           "desk_rows": [], "push": None}
    if trigger == "watch":
        rec["failure_notification"] = notify_failure(failure_text(first_pitch, refused=why))
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


def _closing(rec: dict, p: dict, folder: Path, today_ny: date, now: datetime, t0: float, run_id: str) -> None:
    """The run's body. The caller holds the chain lock (R3) and writes the receipt line afterwards, still under it."""
    have = todays_backup(folder, today_ny)
    if have:
        rec["backup"] = {"file": str(have), "taken": False}
        print(f"· backup dated {today_ny}: {have}")
    else:
        rec["backup"] = take_backup(folder, today_ny)
        print(f"· backup taken: {rec['backup']['file']} opens={rec['backup']['opens']} "
              f"integrity={rec['backup']['integrity']}")
    if rec["backup"].get("taken") and not rec["backup"].get("opens"):
        rec["failed"] = "backup"
        print(f"✗ backup failed: {rec['backup'].get('error')} — no step runs")
        return
    for i, st in enumerate(p["steps"], 1):
        line = f"python cli.py {' '.join(st)}"
        print(f"\n=== [{CHAIN} {i}/{len(p['steps'])}] {line}", flush=True)
        rc, tail, dur = run_step(st, run_id)
        srec = {"step": i, "command": line, "exit": rc, "seconds": round(dur, 1)}
        said = reported_failure(st, tail) if rc == 0 else None
        if said:                      # exit 0, but the step said it failed (Codex on #370)
            srec["detected_failure"] = said
        rec["steps"].append(srec)
        if rc != 0 or said:
            rec["failed"] = f"step {i}" + (" (reported failure, exit 0)" if said else "")
            return
    ex = c.REPO / p["export"]
    if not ex.is_file() or ex.stat().st_mtime < t0:
        rec["failed"] = "export not written"
        return
    rec["export"] = p["export"]
    doc = json.loads(ex.read_text())
    if not doc.get("desk_meta"):
        rec["failed"] = "export carries no desk calls"
        return
    # R1 (ARCHITECT 2026-10-08): ONE started test, taken when the steps have finished, on the stored schedule re-read
    # now (the steps synced it). The 90-minute window is still counted from the run's start.
    done = now + timedelta(seconds=time.time() - t0)
    rec["completed_at"] = iso_z(done)
    games = schedule(now)
    started_ids = {g["match_id"] for g in games if started(g, done)}
    rows = desk_rows(doc, now, done, started_ids)
    why = target_started(games, parse_utc(p["first_pitch"]), done)
    if why:
        rec["failed"] = "target started"
        rec["started"] = why
        print(f"✗ the target first pitch {p['first_pitch_et']} has started ({why}) — no closing for it; a started "
              "game is never retried")
        return
    missing = missing_from_export(doc, now, done, games)
    if missing:                       # Codex on #370: an omitted imminent game is never a success
        rec["failed"] = "missing from export"
        rec["missing"] = missing
        print("✗ missing from export: " + ", ".join(
            f"match {m['match_id']} ({m['first_pitch_et']} {m['away']} @ {m['home']})" for m in missing))
        return
    stale = stale_prices(doc, rows, now)
    if stale:                         # R2: the run checks its prices, not a step's console
        rec["failed"] = "stale prices"
        rec["stale"] = stale
        for s_ in stale:
            print(f"✗ stale prices: match {s_['match_id']} ({s_['first_pitch_et']} {s_['game']}): {s_['price']} "
                  f"captured {s_['captured_at'] or 'never (no stored row)'}, before the run's start {s_['run_start']}")
        return
    rec["desk_rows"] = [{k: x[k] for k in ("match_id", "first_pitch", "call", "pick", "units", "exec_edge_pp",
                                           "hold")} for x in rows]
    print(f"\n=== MLB closing summary · {len(rows)} game(s) with first pitch within {SUMMARY_WINDOW_MIN} minutes")
    for x in rows:
        print(summary_block(x))
    rec["push"] = push_mirror()
    print(f"· exports mirror (laptop, closing): exit {rec['push']['exit']} {' | '.join(rec['push']['tail'])}")
    if rec["push"].get("exit") != 0:  # Codex on #370: a failed / timed-out push fails the run, so the watch
        rec["failed"] = "push"        # retries it (R6: the export stays in place)
        return
    # Codex round 2 on #370: every notification's result is recorded and validated BEFORE exit 0. On macOS a
    # notification that was not posted (osascript nonzero / timeout / an exception) fails the run, so the watch
    # retries it. Off macOS nothing is expected to post: that is not a failure.
    rec["notifications"] = []
    for x in rows:
        text = notification_text(x)
        try:
            res = notify(text)
        except Exception as e:  # noqa: BLE001
            res = {"posted": False, "text": text, "error": f"{type(e).__name__}: {e}"[:200]}
        rec["notifications"].append({"match_id": x["match_id"], "posted": res.get("posted"),
                                     **({"skipped": res["skipped"]} if res.get("skipped") else {}),
                                     **({"error": res["error"]} if res.get("error") else {})})
    if any(n["posted"] is not True and not n.get("skipped") for n in rec["notifications"]):
        rec["failed"] = "notify"
    else:
        rec["exit"] = 0


def _finish(rec: dict, trigger: str, run_id: str, t0: float) -> None:
    """R6, the failed-run notification and THE receipt line. Called with the chain lock held (R3)."""
    if rec.get("failed") in OWN_CHECK_FAILURES:
        _move_export(rec, run_id)
    if rec["exit"] != 0 and trigger == "watch":
        rec["failure_notification"] = notify_failure(
            failure_text(rec.get("first_pitch"), failed=rec.get("failed"), attempt=rec.get("attempt")))
    rec["seconds"] = round(time.time() - t0, 1)
    c.append_receipt(rec)


def run(first_pitch: str | None = None, dry_run: bool = False, trigger: str = "operator",
        now: datetime | None = None) -> int:
    now = utc(now or c.utc_now())
    run_id = f"{now:%Y%m%dT%H%M%SZ}-{CHAIN}"
    base = {"kind": "mlb_closing", "run_id": run_id, "trigger": trigger}
    folder = backup_folder()
    # The refusals, each receipted (exit 2). R5 first: "The backup folder is checked before anything else."
    for check in (lambda: _backup_folder_refusal(folder), _laptop_refusal, _mirror_refusal,
                  lambda: _first_pitch_refusal(first_pitch)):
        why = check()
        if why:
            return _refuse(why, first_pitch, base, trigger, dry_run)
    try:
        p = plan(now, first_pitch)
    except (FileNotFoundError, sqlite3.Error) as e:
        p = {"refused": f"no stored schedule readable ({type(e).__name__})", "window": []}
    today_ny = ny_date(now)
    if dry_run:
        print("DRY RUN mlb-closing-run (touches nothing: no step, no backup, no receipt, no push, no notification)")
        if p.get("refused"):
            print(f"  would REFUSE: {p['refused']}")
            return 0
        have = todays_backup(folder, today_ny)
        print(f"  first pitch {p['first_pitch_et']} ({p['first_pitch']}) · steps take date {p['date_ny']} "
              f"(America/New_York)")
        print(f"  lock: {c.lock_path()} (held from the backup check until the receipt line is written)")
        print(f"  backup: " + (f"exists {have}" if have else
                               f"none dated {today_ny} in {folder} → would take sports_{today_ny}.db (.backup API) "
                               f"and open it"))
        for i, st in enumerate(p["steps"], 1):
            print(f"  {i}. python cli.py {' '.join(st)}")
        print(f"  export: {p['export']} · prices checked against the run's start · summary + one notification per "
              f"unstarted game with first pitch within {SUMMARY_WINDOW_MIN}m · push: exports_mirror.py push --role "
              f"laptop --label closing")
        return 0
    if p.get("refused"):
        return _refuse(p["refused"], first_pitch, base, trigger, dry_run=False)
    rec = {**base, "first_pitch": p["first_pitch"], "first_pitch_et": p["first_pitch_et"], "date_ny": p["date_ny"],
           "attempt": closing_state(p["first_pitch"])["attempts"] + 1, "run_start": iso_z(now), "backup": None,
           "steps": [], "export": None, "desk_rows": [], "push": None, "exit": 1}
    print(f"=== mlb-closing-run · first pitch {p['first_pitch_et']} · date {p['date_ny']} (America/New_York) "
          f"· attempt {rec['attempt']}", flush=True)
    t0 = time.time()
    written = False
    try:
        # R3 (ARCHITECT 2026-10-08): "The chain lock is held from the backup check until the receipt line is written."
        with c.db_lock():
            try:
                _closing(rec, p, folder, today_ny, now, t0, run_id)
            except Exception as e:  # noqa: BLE001 - the receipt line is written either way (A2)
                rec["failed"] = rec.get("failed") or "error"
                rec["error"] = c.redact(f"{type(e).__name__}: {e}")[:300]
            written = True
            _finish(rec, trigger, run_id, t0)
    except Exception as e:  # noqa: BLE001 - the lock itself (or the receipt write) failed
        if written:
            raise
        rec["failed"] = rec.get("failed") or "lock"
        rec["error"] = c.redact(f"{type(e).__name__}: {e}")[:300]
        _finish(rec, trigger, run_id, t0)
    if rec["exit"] != 0:
        print(f"✗ mlb-closing-run FAILED ({rec.get('failed')}{': ' + rec['error'] if rec.get('error') else ''}) — "
              + {"push": "nothing notified; the export stays on disk",
                 "notify": "the export was pushed; a notification was not posted, the watch retries",
                 "target started": "nothing pushed or notified; the export was moved into logs/",
                 "missing from export": "nothing pushed or notified; the export was moved into logs/",
                 "stale prices": "nothing pushed or notified; the export was moved into logs/"}.get(
                  rec.get("failed"), "nothing exported, pushed or notified after the failure"))
    else:
        print(f"✓ mlb-closing-run: {len(rec['steps'])}/{len(p['steps'])} steps · {rec['export']} · "
              f"{len(rec['desk_rows'])} Desk row(s) · push exit {rec['push']['exit']}")
    return rec["exit"] if rec["exit"] == 0 else 1


# -------------------------------------------------------------------------------------------------- watch --

def lock_free() -> bool:
    """True when no chain holds the lock right now (a closing run in progress makes the tick silent)."""
    p = c.lock_path()
    if not p.exists():
        return True
    with open(p, "a+") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        fcntl.flock(f, fcntl.LOCK_UN)
    return True


def watch(dry_run: bool = False, now: datetime | None = None) -> int:
    now = utc(now or c.utc_now())
    if _laptop_refusal():
        if dry_run:
            print(f"DRY RUN mlb-closing-watch: would do nothing ({_laptop_refusal()})")
        return 0
    try:
        games = schedule(now)
    except (FileNotFoundError, sqlite3.Error) as e:
        if dry_run:
            print(f"DRY RUN mlb-closing-watch: no stored schedule ({type(e).__name__}) — would do nothing")
        return 0
    win = watch_window(games, now)
    pending = []
    for fp in sorted({g["first_pitch"] for g in win}):
        st = closing_state(iso_z(fp))
        if not st["success"] and st["attempts"] < MAX_ATTEMPTS:
            pending.append((fp, st))
    if dry_run:
        print(f"DRY RUN mlb-closing-watch at {iso_z(now)} (no network, no step, no backup, no receipt, no push, "
              "no notification)")
        for g in games:
            m = minutes_to(g, now)
            tag = ("started" if started(g, now) else
                   "IN window" if WATCH_MIN <= m <= WATCH_MAX else f"out (not {WATCH_MIN}-{WATCH_MAX} min)")
            tm = f"T-{m:.0f}m" if m > 0 else f"T+{-m:.0f}m"
            print(f"  match {g['match_id']}  {et(g['first_pitch'])}  {tm}  {g['away']} @ {g['home']}  "
                  f"[{g['status']}]  → {tag}")
        for fp in sorted({g["first_pitch"] for g in win}):
            st = closing_state(iso_z(fp))
            print(f"  first pitch {iso_z(fp)}: success receipt {'yes' if st['success'] else 'no'} · attempts "
                  f"{st['attempts']}/{MAX_ATTEMPTS} · misses {st['misses']}")
        if pending:
            print(f"  would check the MLB feed ({FEED_PROBE}), then start mlb-closing-run --first-pitch "
                  f"{iso_z(pending[0][0])} once")
        else:
            print("  would do nothing (exit 0, silent)")
        return 0
    if not pending or not lock_free():
        return 0
    fp = iso_z(pending[0][0])
    ok, detail = feed_answers()
    if not ok:
        notify(FEED_MISS_TEXT)
        c.append_receipt({"kind": "mlb_closing_miss", "first_pitch": fp, "reason": "feed unreachable",
                          "detail": detail, "notified": FEED_MISS_TEXT})
        print(f"✗ {FEED_MISS_TEXT} ({detail}) — nothing run; miss recorded for first pitch {fp}; next tick retries")
        return 0
    return run(first_pitch=fp, trigger="watch", now=now)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="MLB closing-run autopilot (laptop only).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--first-pitch", default=None, help="ISO UTC first pitch to close (default: the next one "
                   "within 90 minutes)")
    r.add_argument("--dry-run", action="store_true")
    w = sub.add_parser("watch")
    w.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        return run(first_pitch=a.first_pitch, dry_run=a.dry_run)
    return watch(dry_run=a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
