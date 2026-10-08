"""MLB CLOSING-RUN AUTOPILOT (ARCHITECT 2026-10-08, addendum 13 item 3, Q2, RULED). "Laptop only: the host cannot
reach the MLB feed." A1-A9 against a SCRATCH schedule in a throwaway DB under tmp_path. No real cli step, MLB feed,
Kalshi, mirror push or notification is ever reached: every side effect is replaced, and the network is blocked."""
import json
import shutil
import socket
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HOSTING = ROOT / "deploy" / "hosting"
sys.path.insert(0, str(HOSTING))

import chains  # noqa: E402
import mlb_closing as mc  # noqa: E402
import sp_common as c  # noqa: E402
import sp_run  # noqa: E402

from src.walters import desk_policy as dp  # noqa: E402

NOW = datetime(2026, 10, 8, 22, 0, tzinfo=timezone.utc)          # 18:00 ET
HOLD = "paste to the architect before placing"
OFFSETS = {"T-70": 70, "T-62": 62, "T-30": 30, "T-3": 3}


# ------------------------------------------------------------------------------------------------ helpers --

def make_db(path: Path, games: list[tuple]) -> None:
    """games: (match_id, utc datetime, STATUS, away, home). The stored shape: enum NAMES, naive UTC text."""
    con = sqlite3.connect(path)
    con.executescript(
        "CREATE TABLE competitions(id INTEGER PRIMARY KEY, code TEXT);"
        "CREATE TABLE teams(id INTEGER PRIMARY KEY, name TEXT);"
        "CREATE TABLE matches(id INTEGER PRIMARY KEY, competition_id INT, utc_date DATETIME, status TEXT,"
        " home_team_id INT, away_team_id INT);"
        "INSERT INTO competitions VALUES (1, 'MLB'), (2, 'NFL');")
    tid = 0
    for mid, when, status, away, home in games:
        con.execute("INSERT INTO teams VALUES (?, ?)", (tid + 1, home))
        con.execute("INSERT INTO teams VALUES (?, ?)", (tid + 2, away))
        con.execute("INSERT INTO matches VALUES (?, 1, ?, ?, ?, ?)",
                    (mid, when.strftime("%Y-%m-%d %H:%M:%S.000000"), status, tid + 1, tid + 2))
        tid += 2
    # an NFL game in the window is never an MLB closing game
    con.execute("INSERT INTO matches VALUES (999, 2, ?, 'SCHEDULED', 1, 2)",
                ((NOW + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S.000000"),))
    con.commit()
    con.close()


def scratch_games(now=NOW):
    g = [(100 + i, now + timedelta(minutes=m), "SCHEDULED", f"Away{k[2:]}", f"Home{k[2:]}")
         for i, (k, m) in enumerate(OFFSETS.items())]
    g.append((200, now - timedelta(minutes=20), "LIVE", "AwayStarted", "HomeStarted"))
    return g


def desk_row(mid, home, p_home, *, fair_h=None, bid=0.49, ask=0.50, minutes=30, now=NOW):
    mk = {"bookmaker_count": 9 if fair_h is not None else 0}
    if fair_h is not None:
        mk["fair_prob"] = {"HOME": fair_h, "AWAY": round(1 - fair_h, 4)}
    return {"match_id": mid, "home_team": home, "away_team": f"{home} Visitors", "competition": "MLB",
            "stage": "regular", "utc_date": (now + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S"),
            "prediction": {"probabilities": {"home_win": p_home, "draw": None, "away_win": round(1 - p_home, 4)},
                           "tier": "lean"},
            "market": mk, "kalshi_bid": bid, "kalshi_ask": ask,
            "kalshi_legs": {"HOME": {"ticker": f"KXMLBGAME-26OCT08-{home[:3].upper()}H", "bid": bid, "ask": ask},
                            "AWAY": {"ticker": f"KXMLBGAME-26OCT08-{home[:3].upper()}A", "bid": round(1 - ask, 2),
                                     "ask": round(1 - bid, 2)}}}


def four_kinds_doc(now=NOW):
    """The four summary shapes from the REAL Desk (desk_policy.annotate): a PASS, a PLAY that clears 4.0pp exec,
    a PLAY under 4.0pp exec, and an MLB kalshi-only hold (Q3, #369). Plus a started game and one 2h out."""
    rows = [desk_row(1, "Passville", 0.52, fair_h=0.51, bid=0.50, ask=0.51, minutes=20, now=now),
            desk_row(2, "Clearwater", 0.60, fair_h=0.53, bid=0.51, ask=0.52, minutes=30, now=now),
            desk_row(3, "Underhill", 0.58, fair_h=0.535, bid=0.54, ask=0.55, minutes=45, now=now),
            desk_row(4, "Kalshiburg", 0.56, minutes=60, now=now),
            desk_row(5, "Startedton", 0.60, fair_h=0.53, bid=0.51, ask=0.52, minutes=-15, now=now),
            desk_row(6, "Laterton", 0.60, fair_h=0.53, bid=0.51, ask=0.52, minutes=120, now=now)]
    doc = {"sport": "mlb", "predictions": rows}
    dp.annotate(doc, now=now)
    return doc


def receipts():
    p = c.receipts_path()
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


class Box:
    def __init__(self):
        self.steps, self.notes, self.pushes, self.feed_calls = [], [], [], 0
        self.fail_at = None            # step number that exits 1
        self.feed = (True, "HTTP 200")
        self.doc = None                # the export the export step "writes"
        self.lock_seen = []


@pytest.fixture
def box(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "exports").mkdir(parents=True)
    monkeypatch.setattr(c, "REPO", repo)
    monkeypatch.setattr(c, "HOST_ENV", tmp_path / "no-host.env")
    monkeypatch.setattr(c, "_DOTENV_CACHE", None)
    for k in ("SP_SKIP_FAMILIES", "NTFY_TOPIC", "SP_EXPORTS_MIRROR_REMOTE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SP_RECEIPTS", str(tmp_path / "logs" / "receipts.jsonl"))
    monkeypatch.setenv("SP_LOCK", str(tmp_path / "logs" / "db.lock"))
    monkeypatch.setenv("SP_BACKUP_DIR", str(tmp_path / "backups"))
    db = tmp_path / "scratch" / "sports.db"
    db.parent.mkdir()
    make_db(db, scratch_games())
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    b = Box()
    b.tmp, b.db = tmp_path, db
    b.doc = four_kinds_doc()

    def fake_step(argv, run_id):
        b.steps.append(list(argv))
        b.lock_seen.append(mc.lock_free())
        n = len(b.steps)
        if b.fail_at == n:
            return 1, 0.1
        if argv[0] == "export-predictions":
            day = argv[argv.index("--date") + 1]
            (repo / "exports" / f"mlb_MLB_{day}.json").write_text(json.dumps(b.doc))
        return 0, 0.1

    def fake_feed():
        b.feed_calls += 1
        return b.feed

    monkeypatch.setattr(mc, "run_step", fake_step)
    monkeypatch.setattr(mc, "feed_answers", fake_feed)
    monkeypatch.setattr(mc, "notify", lambda body, title=mc.NOTIFY_TITLE: b.notes.append(body) or {"posted": True})
    monkeypatch.setattr(mc, "push_mirror", lambda: b.pushes.append(1) or {"exit": 0, "tail": ["EXPORTS-MIRROR laptop: pushed"]})

    def no_net(*a, **k):
        raise AssertionError("network used")
    monkeypatch.setattr(socket, "create_connection", no_net)
    monkeypatch.setattr(socket.socket, "connect", no_net)
    return b


# ------------------------------------------------------------------------------------------------ chains --

def test_a1_the_closing_chain_is_mlb_preslate_with_the_desk_export():
    pre, clo = chains.CHAINS["mlb-preslate"]["steps"], chains.CHAINS["mlb-closing"]["steps"]
    assert len(pre) == len(clo) == 10
    assert clo[:9] == pre[:9]                                   # the nine non-export steps, verbatim
    assert clo[9] == [*pre[9], "--date", "{today}", "--desk"]   # the export carries the Desk's call, the NY date
    assert pre[9] == ["export-predictions", "--sport", "mlb", "--competition", "MLB"]   # preslate itself unchanged


def test_sp_run_refuses_the_laptop_only_closing_chain(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "HOST_ENV", tmp_path / "no-host.env")
    monkeypatch.setenv("SP_RECEIPTS", str(tmp_path / "r.jsonl"))
    for k in ("NTFY_TOPIC", "NTFY_CARD_TOPIC"):
        monkeypatch.delenv(k, raising=False)
    assert sp_run.main(["mlb-closing"]) == 2
    assert json.loads((tmp_path / "r.jsonl").read_text().splitlines()[-1])["refused"] == "laptop_only"


def test_feed_is_the_mlb_adapters_base_url():
    from src.adapters import mlb_stats_api
    assert mc.FEED_BASE == mlb_stats_api._BASE_URL


def test_the_hold_table_is_one_small_table():
    assert mc.CLOSING_HOLDS == ({"call": "PLAY", "exec_edge_under_pp": 4.0, "text": HOLD, "since": "2026-10-07"},)


def test_the_autopilot_never_opens_kalshis_trading_api():
    src = (HOSTING / "mlb_closing.py").read_text().lower()
    for bad in ("trade-api", "/portfolio", "/orders", "kalshi.com", "create_order"):
        assert bad not in src


# -------------------------------------------------------------------------------------------- A5 window --

def test_a5_watch_window_is_5_to_65_minutes_not_started(box):
    games = mc.schedule(NOW)
    assert {g["match_id"] for g in games} == {100, 101, 102, 103, 200}        # MLB only (the NFL game is not)
    win = mc.watch_window(games, NOW)
    assert sorted(g["match_id"] for g in win) == [101, 102]                   # T-62 in, T-30 in
    out = {g["match_id"] for g in games} - {g["match_id"] for g in win}
    assert out == {100, 103, 200}                                             # T-70, T-3, started


def test_a5_success_then_silent_and_no_network_to_decide(box, capsys):
    assert mc.watch(now=NOW) == 0                     # T-30 first
    assert box.feed_calls == 1 and len(box.steps) == 10
    assert mc.watch(now=NOW) == 0                     # T-62 next
    assert box.feed_calls == 2 and len(box.steps) == 20
    capsys.readouterr()
    assert mc.watch(now=NOW) == 0                     # both closed: nothing
    assert box.feed_calls == 2 and len(box.steps) == 20
    assert capsys.readouterr().out == ""
    runs = [r for r in receipts() if r["kind"] == "mlb_closing"]
    assert [r["first_pitch"] for r in runs] == ["2026-10-08T22:30:00Z", "2026-10-08T23:02:00Z"]
    assert all(r["exit"] == 0 and r["trigger"] == "watch" for r in runs)


def test_a5_nothing_in_window_is_silent_without_the_feed(box, capsys):
    assert mc.watch(now=NOW - timedelta(hours=3)) == 0
    assert box.feed_calls == 0 and box.steps == [] and capsys.readouterr().out == "" and receipts() == []


# -------------------------------------------------------------------------------------------- A6 feed --

def test_a6_feed_unreachable_runs_nothing_notifies_records_and_retries(box):
    box.feed = (False, "URLError: <urlopen error [Errno 8] nodename nor servname provided>")
    assert mc.watch(now=NOW) == 0
    assert box.steps == [] and box.pushes == []
    assert box.notes == ["MLB feed unreachable: VPN on, Tailscale off"]
    miss = receipts()
    assert [r["kind"] for r in miss] == ["mlb_closing_miss"]
    assert miss[0]["first_pitch"] == "2026-10-08T22:30:00Z" and miss[0]["reason"] == "feed unreachable"
    assert not (box.tmp / "backups").exists()                       # no backup either
    assert mc.watch(now=NOW + timedelta(minutes=5)) == 0             # the next tick tries again
    assert box.feed_calls == 2 and len(box.notes) == 2
    box.feed = (True, "HTTP 200")
    assert mc.watch(now=NOW + timedelta(minutes=10)) == 0            # the feed is back: the run starts
    assert len(box.steps) == 10
    assert mc.closing_state("2026-10-08T22:30:00Z") == {"success": True, "attempts": 1, "misses": 2}


def test_a6_at_most_three_attempts_per_first_pitch(box, monkeypatch):
    one = box.tmp / "one.db"
    make_db(one, [(1, NOW + timedelta(minutes=30), "SCHEDULED", "A", "H")])
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{one}")
    for i in range(5):                                  # every run fails at its first step
        box.fail_at = len(box.steps) + 1
        assert mc.watch(now=NOW + timedelta(minutes=i)) == 1 if i < 3 else mc.watch(now=NOW) == 0
    runs = [r for r in receipts() if r["kind"] == "mlb_closing"]
    assert len(runs) == 3 and all(r["exit"] == 1 for r in runs)
    assert [r["attempt"] for r in runs] == [1, 2, 3]
    assert box.feed_calls == 3 and box.pushes == [] and box.notes == []


# ---------------------------------------------------------------------------------------------- A1-A4 run --

def test_a2_lock_taken_and_receipt_on_success(box):
    assert mc.run(now=NOW) == 0
    assert box.lock_seen == [False] * 10                           # every step ran under the chain lock
    r = receipts()[-1]
    assert r["kind"] == "mlb_closing" and r["exit"] == 0
    assert r["first_pitch"] == "2026-10-08T22:03:00Z" and r["date_ny"] == "2026-10-08"
    assert [s["exit"] for s in r["steps"]] == [0] * 10 and all("seconds" in s for s in r["steps"])
    assert r["export"] == "exports/mlb_MLB_2026-10-08.json"
    assert [d["match_id"] for d in r["desk_rows"]] == [1, 2, 3, 4]     # within 90 min; started + 2h out left out
    assert r["push"]["exit"] == 0 and box.pushes == [1]
    assert box.steps[-1] == ["export-predictions", "--sport", "mlb", "--competition", "MLB",
                             "--date", "2026-10-08", "--desk"]


def test_a2_stops_at_the_first_failure_and_exports_pushes_nothing(box):
    box.fail_at = 3
    assert mc.run(now=NOW) == 1
    assert len(box.steps) == 3 and box.pushes == [] and box.notes == []
    assert not list((c.REPO / "exports").glob("*.json"))
    r = receipts()[-1]
    assert r["exit"] == 1 and r["failed"] == "step 3" and [s["exit"] for s in r["steps"]] == [0, 0, 1]
    assert r["export"] is None and r["desk_rows"] == [] and r["push"] is None
    assert r["first_pitch"] == "2026-10-08T22:03:00Z"                  # manual: the next unstarted (T-3)


def test_a2_export_step_failing_pushes_nothing(box):
    box.fail_at = 10
    assert mc.run(now=NOW) == 1
    assert box.pushes == [] and box.notes == [] and receipts()[-1]["failed"] == "step 10"


def test_a3_backup_taken_through_the_backup_api_and_opened(box, monkeypatch):
    for fn in ("copy", "copy2", "copyfile", "copytree"):
        monkeypatch.setattr(shutil, fn, lambda *a, **k: (_ for _ in ()).throw(AssertionError("copied")))
    assert mc.run(now=NOW) == 0
    b = receipts()[-1]["backup"]
    f = Path(b["file"])
    assert b["taken"] and b["opens"] and b["integrity"] == "ok" and f.name == "sports_2026-10-08.db"
    con = sqlite3.connect(f"file:{f}?mode=ro", uri=True)
    assert con.execute("SELECT count(*) FROM matches WHERE competition_id = 1").fetchone()[0] == 5
    con.close()
    assert (f.parent / (f.name + ".sha256")).read_text().split()[0] == b["sha256"]
    # a second run the same day finds it: no new backup
    assert mc.run(now=NOW + timedelta(minutes=1)) == 0
    assert receipts()[-1]["backup"] == {"file": str(f), "taken": False}
    assert sorted(p.name for p in f.parent.iterdir()) == ["sports_2026-10-08.db", "sports_2026-10-08.db.sha256"]


def test_a3_an_operator_backup_dated_today_counts(box):
    (box.tmp / "backups").mkdir()
    own = box.tmp / "backups" / "sports_2026-10-08.db"
    own.write_bytes(b"SQLite format 3\x00 operator line")
    assert mc.run(now=NOW) == 0
    assert receipts()[-1]["backup"] == {"file": str(own), "taken": False}


def test_a3_backup_never_under_data_and_no_step_after_a_failed_backup(box, monkeypatch):
    monkeypatch.setenv("SP_BACKUP_DIR", str(c.REPO / "data" / "bk"))
    assert mc.run(now=NOW) == 1
    r = receipts()[-1]
    assert r["failed"] == "backup" and "REFUSED" in r["backup"]["error"] and box.steps == []
    assert not (c.REPO / "data").exists()


def test_a4_refuses_when_every_game_in_its_window_has_started(box, monkeypatch):
    db = box.tmp / "started.db"
    make_db(db, [(1, NOW - timedelta(minutes=20), "LIVE", "A", "H"),
                 (2, NOW - timedelta(minutes=80), "FINISHED", "B", "I"),
                 (3, NOW - timedelta(minutes=1), "SCHEDULED", "C", "J")])   # first pitch passed: started
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    assert mc.run(now=NOW) == 2
    assert box.steps == [] and box.pushes == [] and box.notes == []
    r = receipts()[-1]
    assert r["exit"] == 2 and r["refused"].startswith("A4: every game in the window has started")
    assert not (box.tmp / "backups").exists()


def test_a4_never_a_call_for_a_started_game(box):
    assert mc.run(now=NOW) == 0
    started_row = next(p for p in box.doc["predictions"] if p["match_id"] == 5)
    assert started_row["desk"]["call"] == "PASS" and started_row["desk"]["pass_kind"] == "started"
    assert 5 not in [d["match_id"] for d in receipts()[-1]["desk_rows"]]
    assert not any("Startedton" in n for n in box.notes)


def test_a1_ny_date_not_utc(box, monkeypatch):
    """A 23:10 ET first pitch is 03:10Z the next UTC day: the steps take the NY date."""
    now = datetime(2026, 10, 9, 2, 30, tzinfo=timezone.utc)                 # 22:30 ET on 10-08
    db = box.tmp / "late.db"
    make_db(db, [(7, datetime(2026, 10, 9, 3, 10, tzinfo=timezone.utc), "SCHEDULED", "Dodgers", "Giants")])
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    box.doc = {"sport": "mlb", "predictions": [desk_row(7, "Giants", 0.52, fair_h=0.51, minutes=40, now=now)]}
    dp.annotate(box.doc, now=now)
    p = mc.plan(now, None)
    assert p["first_pitch"] == "2026-10-09T03:10:00Z" and p["date_ny"] == "2026-10-08"
    assert ["sync-matches", "--competition", "MLB", "--season", "2026", "--date-from", "2026-10-08",
            "--date-to", "2026-10-08"] == p["steps"][0]
    assert p["steps"][-1][-3:] == ["--date", "2026-10-08", "--desk"]
    assert mc.run(now=now) == 0
    assert receipts()[-1]["export"] == "exports/mlb_MLB_2026-10-08.json"
    assert Path(receipts()[-1]["backup"]["file"]).name == "sports_2026-10-08.db"   # dated today in NY, not 10-09


def test_laptop_only_refusal_on_a_host(box, monkeypatch):
    monkeypatch.setenv("SP_SKIP_FAMILIES", "MLB")
    assert mc.run(now=NOW) == 2 and box.steps == []
    assert mc.watch(now=NOW) == 0 and box.feed_calls == 0


# ------------------------------------------------------------------------------------------- A7 summary --

def test_a7_summary_blocks_and_notifications(box, capsys):
    assert mc.run(now=NOW) == 0
    out = capsys.readouterr().out
    blocks = out.split("=== MLB closing summary")[1]
    p = blocks.split("── ")
    pas, clear, under, ko = p[1], p[2], p[3], p[4]
    assert "call   PASS" in pas and "order  none (PASS:" in pas and HOLD not in pas
    assert "call   PLAY · pick Clearwater · 1u" in clear and "exec edge +7.1pp" in clear
    assert "order  BUY YES KXMLBGAME-26OCT08-CLEH @ 0.52 × 10" in clear and "HOLD" not in clear
    order_line = next(x for x in under.splitlines() if x.strip().startswith("order"))
    assert order_line.endswith(f"× 5 · HOLD: {HOLD}") and "exec edge +2.2pp" in under
    assert "pass_kind" not in ko and "kalshi-only hold (record only, not a call): mid 0.495" in ko
    assert "would PLAY 0.5u" in ko and "kalshi-only suspended for MLB" in ko
    assert len(box.notes) == 4
    assert box.notes[1] == "18:30 ET Clearwater Visitors @ Clearwater: PLAY Clearwater 1u exec +7.1pp"
    assert box.notes[2] == f"18:45 ET Underhill Visitors @ Underhill: PLAY Underhill 0.5u exec +2.2pp · {HOLD}"
    assert [d["hold"] for d in receipts()[-1]["desk_rows"]] == [None, None, HOLD, None]


def test_a7_hold_rule():
    assert mc.hold_for({"call": "PLAY", "exec": {"edge_pp": 3.99}}) == HOLD
    assert mc.hold_for({"call": "PLAY", "exec": {"edge_pp": 4.0}}) is None
    assert mc.hold_for({"call": "PLAY", "exec": None}) == HOLD                 # unknown exec edge: held (law 4)
    assert mc.hold_for({"call": "PASS", "exec": {"edge_pp": 1.0}}) is None


def test_notify_off_macos_posts_nothing(monkeypatch, capsys):
    real = mc                                         # the real notify (no fixture stub here)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("osascript")))
    assert real.notify("x")["posted"] is False
    assert "not macOS, not posted" in capsys.readouterr().out


def test_notify_on_macos_uses_osascript_quoted(monkeypatch):
    real = mc
    seen = []
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(real.subprocess, "run", lambda argv, **k: seen.append(argv) or
                        subprocess.CompletedProcess(argv, 0, "", ""))
    assert real.notify('a "b"')["posted"] is True
    assert seen == [["osascript", "-e", 'display notification "a \\"b\\"" with title "MLB closing"']]


# --------------------------------------------------------------------------------------------- A9 dry run --

def test_a9_dry_run_touches_nothing_on_both_commands(box, capsys):
    assert mc.watch(dry_run=True, now=NOW) == 0
    w = capsys.readouterr().out
    assert mc.run(dry_run=True, now=NOW) == 0
    r = capsys.readouterr().out
    assert box.steps == [] and box.notes == [] and box.pushes == [] and box.feed_calls == 0
    assert not c.receipts_path().exists() and not (box.tmp / "backups").exists()
    assert not c.lock_path().exists()
    assert "would check the MLB feed" in w and "--first-pitch 2026-10-08T22:30:00Z" in w
    assert "10. python cli.py export-predictions --sport mlb --competition MLB --date 2026-10-08 --desk" in r
    assert "would take sports_2026-10-08.db" in r


# ------------------------------------------------------------------------------------------ A8 setup script --

def test_a8_setup_script_syntax_pattern_and_uninstall(tmp_path):
    sh = ROOT / "scripts" / "setup_mlb_closing_watch.sh"
    assert subprocess.run(["bash", "-n", str(sh)]).returncode == 0
    t = sh.read_text()
    assert "<key>StartInterval</key>" in t and "INTERVAL_S=300" in t and "mlb-closing-watch" in t
    assert "${LOG_DIR}/mlb_closing_watch.log" in t and '"--uninstall"' in t
    home, bindir = tmp_path / "home", tmp_path / "bin"
    plist = home / "Library" / "LaunchAgents" / "com.sportspredictor.mlbclosingwatch.plist"
    plist.parent.mkdir(parents=True)
    plist.write_text("x")
    bindir.mkdir()
    (bindir / "launchctl").write_text("#!/bin/sh\necho \"launchctl $*\" >> \"$HOME/calls\"\n")
    (bindir / "launchctl").chmod(0o755)
    r = subprocess.run(["bash", str(sh), "--uninstall"], capture_output=True, text=True,
                       env={"HOME": str(home), "PATH": f"{bindir}:/usr/bin:/bin"})
    assert r.returncode == 0 and "uninstalled" in r.stdout and not plist.exists()
    assert (home / "calls").read_text().strip() == f"launchctl unload {plist}"
    # nothing in the repo installs it: only docs name the script
    hits = subprocess.run(["git", "-C", str(ROOT), "grep", "-l", "setup_mlb_closing_watch"],
                          capture_output=True, text=True).stdout.split()
    assert all(h.endswith(".md") or h in ("scripts/setup_mlb_closing_watch.sh",
                                          "tests/test_mlb_closing_autopilot.py",
                                          "cli.py") for h in hits), hits


FAKE_CLI = '''import os, sys
a = sys.argv[1:]
print("ran", " ".join(a))
if a[0] == "export-predictions":
    day = a[a.index("--date") + 1]
    open(f"exports/mlb_MLB_{day}.json", "w").write(open(os.environ["T_DOC"]).read())
if a[0] == os.environ.get("T_FAIL"):
    sys.exit(4)
'''


def test_real_step_runner_against_a_fake_cli(box, monkeypatch):
    """The real sp_run.run_step path (subprocess `python cli.py ...` in the checkout) against a FAKE cli.py in a
    tmp checkout: never the real one, never a real DB."""
    monkeypatch.setattr(mc, "run_step", lambda argv, run_id: (lambda r: (r[0], r[2]))(sp_run.run_step(argv, run_id)))
    (c.REPO / "cli.py").write_text(FAKE_CLI)
    doc = box.tmp / "doc.json"
    doc.write_text(json.dumps(box.doc))
    monkeypatch.setenv("T_DOC", str(doc))
    assert mc.run(now=NOW) == 0
    r = receipts()[-1]
    assert [s["exit"] for s in r["steps"]] == [0] * 10 and len(r["desk_rows"]) == 4
    monkeypatch.setenv("T_FAIL", "predict")
    assert mc.run(now=NOW) == 1
    r = receipts()[-1]
    assert [s["exit"] for s in r["steps"]] == [0] * 6 + [4] and r["push"] is None
