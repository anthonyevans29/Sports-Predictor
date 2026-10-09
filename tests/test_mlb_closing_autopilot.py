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
REAL_NOTIFY = mc.notify                                           # before any fixture replaces it
HOLD = "paste to the architect before placing"
OFFSETS = {"T-70": 70, "T-62": 62, "T-30": 30, "T-3": 3}
# the scratch schedule's home teams, one per summary shape (the export's rows carry the same match ids)
HOMES = {"T-70": "Clearwater", "T-62": "Underhill", "T-30": "Kalshiburg", "T-3": "Passville"}


# ------------------------------------------------------------------------------------------------ helpers --

def make_db(path: Path, games: list[tuple]) -> None:
    """games: (match_id, utc datetime, STATUS, away, home). The stored shape: enum NAMES, naive UTC text."""
    con = sqlite3.connect(path)
    con.executescript(
        "CREATE TABLE competitions(id INTEGER PRIMARY KEY, code TEXT);"
        "CREATE TABLE teams(id INTEGER PRIMARY KEY, name TEXT);"
        "CREATE TABLE matches(id INTEGER PRIMARY KEY, competition_id INT, utc_date DATETIME, status TEXT,"
        " home_team_id INT, away_team_id INT);"
        "INSERT INTO competitions VALUES (1, 'MLB'), (2, 'NFL');"
        # the stored price tables the export reads (src/db/schema.py Odds / OddsSnapshot: the columns R2 reads)
        "CREATE TABLE odds(id INTEGER PRIMARY KEY, match_id INT, bookmaker TEXT, market TEXT, selection TEXT,"
        " price_decimal REAL, line REAL, captured_at DATETIME, source TEXT);"
        "CREATE TABLE odds_snapshots(id INTEGER PRIMARY KEY, match_id INT, market TEXT, selection TEXT,"
        " devig_prob REAL, line REAL, captured_at DATETIME, source TEXT, yes_bid REAL, yes_ask REAL);")
    tid = 0
    for mid, when, status, away, home in games:
        con.execute("INSERT INTO teams VALUES (?, ?)", (tid + 1, home))
        con.execute("INSERT INTO teams VALUES (?, ?)", (tid + 2, away))
        con.execute("INSERT INTO matches VALUES (?, 1, ?, ?, ?, ?)",
                    (mid, when.strftime("%Y-%m-%d %H:%M:%S.000000"), status, tid + 1, tid + 2))
        tid += 2
    write_prices(con, NOW - timedelta(hours=3))           # every game carries prices from the morning: stale here
    # an NFL game in the window is never an MLB closing game
    con.execute("INSERT INTO matches VALUES (999, 2, ?, 'SCHEDULED', 1, 2)",
                ((NOW + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S.000000"),))
    con.commit()
    con.close()


def _ts(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S.000000")


def write_prices(con, at, kinds=("books", "kalshi")):
    """What sync-odds / sync-kalshi store, at capture time `at`, for every MLB game not started at `at`: the
    api_baseball 1X2 board replaced (one capture stamp, src/ingestion/service.py _mlb_store_odds) and a Kalshi
    HOME/AWAY snapshot appended (source 'kalshi', src/ingestion/kalshi_sync.py)."""
    for (mid,) in con.execute("SELECT id FROM matches WHERE competition_id = 1 AND utc_date > ?", (_ts(at),)).fetchall():
        if "books" in kinds:
            con.execute("DELETE FROM odds WHERE match_id = ? AND source = 'api_baseball'", (mid,))
            for bk in ("bk1", "bk2"):
                for sel, px in (("HOME", 1.9), ("AWAY", 1.95)):
                    con.execute("INSERT INTO odds(match_id, bookmaker, market, selection, price_decimal, captured_at,"
                                " source) VALUES (?, ?, '1X2', ?, ?, ?, 'api_baseball')", (mid, bk, sel, px, _ts(at)))
        if "kalshi" in kinds:
            for sel in ("HOME", "AWAY"):
                con.execute("INSERT INTO odds_snapshots(match_id, market, selection, devig_prob, captured_at, source,"
                            " yes_bid, yes_ask) VALUES (?, 'ML', ?, 0.5, ?, 'kalshi', 0.49, 0.5)", (mid, sel, _ts(at)))
    con.commit()


def run_start_of(run_id):
    return datetime.strptime(run_id[:16], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)


def scratch_games(now=NOW):
    g = [(100 + i, now + timedelta(minutes=m), "SCHEDULED", f"{HOMES[k]} Visitors", HOMES[k])
         for i, (k, m) in enumerate(OFFSETS.items())]
    g.append((200, now - timedelta(minutes=20), "LIVE", "Startedton Visitors", "Startedton"))
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
    rows = [desk_row(103, "Passville", 0.52, fair_h=0.51, bid=0.50, ask=0.51, minutes=3, now=now),
            desk_row(100, "Clearwater", 0.60, fair_h=0.53, bid=0.51, ask=0.52, minutes=70, now=now),
            desk_row(101, "Underhill", 0.58, fair_h=0.535, bid=0.54, ask=0.55, minutes=62, now=now),
            desk_row(102, "Kalshiburg", 0.56, minutes=30, now=now),   # kalshi-only applies inside T-60
            desk_row(200, "Startedton", 0.60, fair_h=0.53, bid=0.51, ask=0.52, minutes=-20, now=now),
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
        self.tails = {}                # command -> the console tail it "prints" (exit 0)
        self.no_fresh = set()          # sync steps that store no fresh prices (a failed sync: R2)
        self.receipt_locks = []        # lock_free() seen at each receipt write (R3)


@pytest.fixture
def box(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "exports").mkdir(parents=True)
    monkeypatch.setattr(c, "REPO", repo)
    monkeypatch.setattr(c, "HOST_ENV", tmp_path / "no-host.env")
    monkeypatch.setattr(c, "_DOTENV_CACHE", None)
    for k in ("SP_SKIP_FAMILIES", "NTFY_TOPIC", "SP_EXPORTS_MIRROR_REMOTE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SP_EXPORTS_MIRROR_REMOTE", "git@example.invalid:scratch/exports.git")   # M1 (push faked)
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
            return 1, ["boom"], 0.1
        kind = {"sync-odds": "books", "sync-kalshi": "kalshi"}.get(argv[0])
        if kind and argv[0] not in b.no_fresh:
            con = sqlite3.connect(c.db_path())
            write_prices(con, run_start_of(run_id) + timedelta(seconds=30), (kind,))
            con.close()
        if argv[0] == "export-predictions":
            day = argv[argv.index("--date") + 1]
            (repo / "exports" / f"mlb_MLB_{day}.json").write_text(json.dumps(b.doc))
        return 0, list(b.tails.get(argv[0], ["ok"])), 0.1

    def fake_feed():
        b.feed_calls += 1
        return b.feed

    b.fake_step = fake_step
    monkeypatch.setattr(mc, "run_step", fake_step)
    monkeypatch.setattr(mc, "feed_answers", fake_feed)
    monkeypatch.setattr(mc, "notify", lambda body, title=mc.NOTIFY_TITLE: b.notes.append(body) or {"posted": True})
    monkeypatch.setattr(mc, "push_mirror", lambda: b.pushes.append(1) or {"exit": 0, "tail": ["EXPORTS-MIRROR laptop: pushed"]})

    real_append = c.append_receipt

    def watched_append(rec):
        b.receipt_locks.append(mc.lock_free())
        return real_append(rec)
    monkeypatch.setattr(c, "append_receipt", watched_append)

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
    assert box.feed_calls == 3 and box.pushes == []
    assert len(box.notes) == 3                          # one failed-run notification per watch-started attempt


# ---------------------------------------------------------------------------------------------- A1-A4 run --

def test_a2_lock_taken_and_receipt_on_success(box):
    assert mc.run(now=NOW) == 0
    assert box.lock_seen == [False] * 10                           # every step ran under the chain lock
    r = receipts()[-1]
    assert r["kind"] == "mlb_closing" and r["exit"] == 0
    assert r["first_pitch"] == "2026-10-08T22:03:00Z" and r["date_ny"] == "2026-10-08"
    assert [s["exit"] for s in r["steps"]] == [0] * 10 and all("seconds" in s for s in r["steps"])
    assert r["export"] == "exports/mlb_MLB_2026-10-08.json"
    assert [d["match_id"] for d in r["desk_rows"]] == [103, 102, 101, 100]     # within 90 min; started + 2h out left out
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


def test_a3_no_step_after_a_failed_backup(box, monkeypatch):
    monkeypatch.setattr(mc, "take_backup", lambda folder, day: {"file": str(folder / "x.db"), "taken": True,
                                                                "opens": False, "integrity": "malformed",
                                                                "error": "RuntimeError: integrity_check"})
    assert mc.run(now=NOW) == 1
    r = receipts()[-1]
    assert r["failed"] == "backup" and r["backup"]["opens"] is False and box.steps == [] and box.pushes == []


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
    started_row = next(p for p in box.doc["predictions"] if p["match_id"] == 200)
    assert started_row["desk"]["call"] == "PASS" and started_row["desk"]["pass_kind"] == "started"
    assert 200 not in [d["match_id"] for d in receipts()[-1]["desk_rows"]]
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
    pas, ko, under, clear = p[1], p[2], p[3], p[4]
    assert "call   PASS" in pas and "order  none (PASS:" in pas and HOLD not in pas
    assert "call   PLAY · pick Clearwater · 1u" in clear and "exec edge +7.1pp" in clear
    assert "order  BUY YES KXMLBGAME-26OCT08-CLEH @ 0.52 × 10" in clear and "HOLD" not in clear
    order_line = next(x for x in under.splitlines() if x.strip().startswith("order"))
    assert order_line.endswith(f"× 5 · HOLD: {HOLD}") and "exec edge +2.2pp" in under
    assert "pass_kind" not in ko and "kalshi-only hold (record only, not a call): mid 0.495" in ko
    assert "would PLAY 0.5u" in ko and "kalshi-only suspended for MLB" in ko
    assert len(box.notes) == 4
    assert box.notes[3] == "19:10 ET Clearwater Visitors @ Clearwater: PLAY Clearwater 1u exec +7.1pp"
    assert box.notes[2] == f"19:02 ET Underhill Visitors @ Underhill: PLAY Underhill 0.5u exec +2.2pp · {HOLD}"
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


FAKE_CLI = '''import os, sqlite3, sys
a = sys.argv[1:]
print("ran", " ".join(a))
if a[0] in ("sync-odds", "sync-kalshi"):            # fresh prices, captured at T_CAPTURE (after the run's start)
    con = sqlite3.connect(os.environ["DATABASE_URL"][len("sqlite:///"):])
    for (mid,) in con.execute("SELECT id FROM matches WHERE competition_id = 1").fetchall():
        for sel in ("HOME", "AWAY"):
            if a[0] == "sync-odds":
                con.execute("INSERT INTO odds(match_id, bookmaker, market, selection, price_decimal, captured_at, "
                            "source) VALUES (?, 'bk1', '1X2', ?, 1.9, ?, 'api_baseball')", (mid, sel, os.environ["T_CAPTURE"]))
            else:
                con.execute("INSERT INTO odds_snapshots(match_id, market, selection, devig_prob, captured_at, source) "
                            "VALUES (?, 'ML', ?, 0.5, ?, 'kalshi')", (mid, sel, os.environ["T_CAPTURE"]))
    con.commit()
if a[0] == "export-predictions":
    day = a[a.index("--date") + 1]
    open(f"exports/mlb_MLB_{day}.json", "w").write(open(os.environ["T_DOC"]).read())
if a[0] == os.environ.get("T_FAIL"):
    sys.exit(4)
'''


def test_real_step_runner_against_a_fake_cli(box, monkeypatch):
    """The real sp_run.run_step path (subprocess `python cli.py ...` in the checkout) against a FAKE cli.py in a
    tmp checkout: never the real one, never a real DB."""
    monkeypatch.setattr(mc, "run_step", sp_run.run_step)
    (c.REPO / "cli.py").write_text(FAKE_CLI)
    doc = box.tmp / "doc.json"
    doc.write_text(json.dumps(box.doc))
    monkeypatch.setenv("T_DOC", str(doc))
    monkeypatch.setenv("T_CAPTURE", "2026-10-08 22:00:30.000000")
    assert mc.run(now=NOW) == 0
    r = receipts()[-1]
    assert [s["exit"] for s in r["steps"]] == [0] * 10 and len(r["desk_rows"]) == 4
    monkeypatch.setenv("T_FAIL", "predict")
    assert mc.run(now=NOW) == 1
    r = receipts()[-1]
    assert [s["exit"] for s in r["steps"]] == [0] * 6 + [4] and r["push"] is None


# ---------------------------------------------------------------------------------- review round 1 (#370) --

@pytest.mark.parametrize("push", [{"exit": 1, "tail": ["EXPORTS-MIRROR laptop: not pushed — push rejected 3x"]},
                                  {"exit": None, "tail": ["timed out after 90s"]}])
def test_p1a_a_failed_or_timed_out_push_fails_the_run_and_the_watch_retries(box, monkeypatch, push):
    monkeypatch.setattr(mc, "push_mirror", lambda: box.pushes.append(1) or push)
    assert mc.watch(now=NOW) == 1
    r = receipts()[-1]
    assert r["exit"] == 1 and r["failed"] == "push" and r["push"] == push
    assert r["export"] == "exports/mlb_MLB_2026-10-08.json" and (c.REPO / r["export"]).is_file()   # kept on disk
    assert "export_moved_to" not in r                                       # R6: a failed push leaves it in place
    assert box.notes == ["Closing 2026-10-08 18:30 ET: FAILED: push · attempt 1/3"]   # no call notified
    box.notes.clear()
    assert mc.closing_state("2026-10-08T22:30:00Z") == {"success": False, "attempts": 1, "misses": 0}
    monkeypatch.setattr(mc, "push_mirror", lambda: box.pushes.append(1) or {"exit": 0, "tail": ["pushed"]})
    assert mc.watch(now=NOW + timedelta(minutes=5)) == 0                    # the next tick retries: success
    r = receipts()[-1]
    assert r["first_pitch"] == "2026-10-08T22:30:00Z" and r["exit"] == 0 and r["attempt"] == 2
    assert len(box.pushes) == 2 and len(box.notes) == 3          # T-3 has started by now: no row for it


def test_p1b_a_game_missing_from_the_export_fails_the_run_and_is_listed(box):
    box.doc["predictions"] = [p for p in box.doc["predictions"] if p["match_id"] != 101]    # Underhill dropped
    assert mc.run(now=NOW) == 1
    r = receipts()[-1]
    assert r["failed"] == "missing from export" and r["exit"] == 1
    assert r["missing"] == [{"match_id": 101, "first_pitch": "2026-10-08T23:02:00Z",
                             "first_pitch_et": "2026-10-08 19:02 ET", "away": "Underhill Visitors",
                             "home": "Underhill", "reason": "missing from export"}]
    assert box.pushes == [] and box.notes == [] and r["push"] is None and r["desk_rows"] == []


def test_p1b_started_and_later_games_are_not_required(box):
    box.doc["predictions"] = [p for p in box.doc["predictions"] if p["match_id"] not in (200, 6)]
    assert mc.run(now=NOW) == 0


@pytest.mark.parametrize("said", ["✗ Kalshi sync failed: HTTPSConnectionPool(host='api.elections.kalshi.com'): "
                                  "Max retries exceeded",
                                  "Kalshi sync: market fetch failed: 503 Server Error"])
def test_p1c_a_step_that_reports_failure_with_exit_0_stops_the_run(box, said):
    box.tails["sync-kalshi"] = ["Checking Kalshi status…", said,
                                "If this is a network/DNS error, Kalshi's API host may need to be reachable"]
    assert mc.run(now=NOW) == 1
    assert box.steps[-1][0] == "sync-kalshi" and len(box.steps) == 6       # predict / export never ran
    r = receipts()[-1]
    assert r["failed"] == "step 6 (reported failure, exit 0)"
    assert r["steps"][-1]["exit"] == 0 and r["steps"][-1]["detected_failure"] == said[:200]
    assert r["export"] is None and r["push"] is None and box.pushes == [] and box.notes == []


def test_p1c_markers_are_the_strings_cli_prints():
    src = (ROOT / "cli.py").read_text()
    start = src.index('@cli.command("sync-kalshi")')
    body = src[start:src.index("@cli.command", start + 10)]
    assert 'f"[red]✗ Kalshi sync failed: {e}[/red]"' in body
    assert "f\"[yellow]Kalshi sync: {r.get('reason')}[/yellow]\"" in body
    assert body.count("console.print(") == 7   # progress, failed + hint, not-ok + series, stored + stats: enumerated
    assert mc.STEP_FAILURE_MARKERS == {"sync-kalshi": ("✗ Kalshi sync failed:", "Kalshi sync: ")}
    assert mc.reported_failure(["sync-kalshi"], ["✓ Kalshi: 14 prices stored", "  series KXMLBGAME"]) is None


def test_p2b_laptop_only_refusal_writes_a_refused_receipt_but_not_on_dry_run(box, monkeypatch):
    monkeypatch.setenv("SP_SKIP_FAMILIES", "NFL,MLB")
    assert mc.run(dry_run=True, now=NOW) == 2
    assert not c.receipts_path().exists()
    assert mc.run(now=NOW) == 2
    r = receipts()[-1]
    assert r["kind"] == "mlb_closing" and r["exit"] == 2 and r["refused"].startswith("laptop only")
    assert box.steps == [] and not (box.tmp / "backups").exists()


# ---------------------------------------------------------------------------------- review round 2 (#370) --

def _mac_osascript(monkeypatch, outcome):
    """Real notify() on 'macOS' with osascript replaced: 'ok', 'nonzero', 'timeout' or 'raise' (an unexpected error)."""
    monkeypatch.setattr(sys, "platform", "darwin")

    real_run = subprocess.run

    def fake_run(argv, **k):
        if argv[0] != "osascript":                    # receipts' git lookups pass through
            return real_run(argv, **k)
        if outcome == "timeout":
            raise subprocess.TimeoutExpired(argv, 15)
        if outcome == "raise":
            raise RuntimeError("notification centre unavailable")
        return subprocess.CompletedProcess(argv, 0 if outcome == "ok" else 1, "", "")
    monkeypatch.setattr(mc.subprocess, "run", fake_run)


@pytest.mark.parametrize("outcome", ["nonzero", "timeout", "raise"])
def test_p1d_a_notification_not_posted_on_macos_fails_the_run_and_the_watch_retries(box, monkeypatch, outcome):
    monkeypatch.setattr(mc, "notify", REAL_NOTIFY)               # the real notify, osascript replaced below
    _mac_osascript(monkeypatch, outcome)
    assert mc.watch(now=NOW) == 1
    r = receipts()[-1]
    assert r["exit"] == 1 and r["failed"] == "notify" and len(r["notifications"]) == 4
    assert all(n["posted"] is False and n["error"] for n in r["notifications"])
    assert mc.closing_state("2026-10-08T22:30:00Z")["success"] is False
    _mac_osascript(monkeypatch, "ok")                            # the next tick retries and posts
    assert mc.watch(now=NOW + timedelta(minutes=1)) == 0
    r = receipts()[-1]
    assert r["exit"] == 0 and r["attempt"] == 2 and all(n["posted"] is True for n in r["notifications"])


def test_p1d_off_macos_not_posting_is_not_a_failure(box, monkeypatch):
    monkeypatch.setattr(mc, "notify", lambda body, title=mc.NOTIFY_TITLE: {"posted": False, "text": body,
                                                                         "skipped": "not macOS"})
    assert mc.run(now=NOW) == 0
    assert all(n == {"match_id": n["match_id"], "posted": False, "skipped": "not macOS"}
               for n in receipts()[-1]["notifications"])


def test_p1e_target_first_pitch_elapsed_during_the_run_is_a_failure_and_never_retried(box, monkeypatch):
    db = box.tmp / "edge.db"
    make_db(db, [(102, NOW + timedelta(minutes=6), "SCHEDULED", "Kalshiburg Visitors", "Kalshiburg")])
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    box.doc = {"sport": "mlb", "predictions": [desk_row(102, "Kalshiburg", 0.60, fair_h=0.53, bid=0.51, ask=0.52,
                                                        minutes=6)]}
    dp.annotate(box.doc, now=NOW)
    clock = {"t": __import__("time").time()}
    monkeypatch.setattr(mc, "time", type("T", (), {"time": staticmethod(lambda: clock["t"])}))
    inner = box.fake_step

    def slow_step(argv, run_id):                                 # each step takes 1 minute: 10 minutes in all
        out = inner(argv, run_id)
        clock["t"] += 60
        return out
    monkeypatch.setattr(mc, "run_step", slow_step)
    assert mc.watch(now=NOW) == 1                               # T-6: in the window, started
    r = receipts()[-1]
    assert r["exit"] == 1 and r["failed"] == "target started" and r["started"].startswith("first pitch")
    assert r["completed_at"] == "2026-10-08T22:10:00Z" and r["push"] is None
    assert box.pushes == [] and box.notes == ["Closing 2026-10-08 18:06 ET: FAILED: target started · attempt 1/3"]
    n = len(box.steps)
    assert mc.watch(now=NOW + timedelta(minutes=10)) == 0       # first pitch passed: never retried
    assert len(box.steps) == n and box.feed_calls == 1


def _slow_steps(box, monkeypatch, seconds_each, on_step=None):
    clock = {"t": __import__("time").time()}
    monkeypatch.setattr(mc, "time", type("T", (), {"time": staticmethod(lambda: clock["t"])}))
    inner = box.fake_step

    def slow_step(argv, run_id):
        out = inner(argv, run_id)
        clock["t"] += seconds_each
        if on_step:
            on_step(argv)
        return out
    monkeypatch.setattr(mc, "run_step", slow_step)


def _set_status(db, mid, status):
    con = sqlite3.connect(db)
    con.execute("UPDATE matches SET status = ? WHERE id = ?", (status, mid))
    con.commit()
    con.close()


# ------------------------------------------------------------------------------ ADDENDUM 16 item 2 (#370 READ) --

def test_r1_one_started_test_when_the_steps_have_finished(box, monkeypatch):
    """R1: a game is started when its stored status is LIVE or FINISHED when the steps have finished, or its first
    pitch is at or before that moment. A started game has no summary block, no notification, and the export is not
    required to carry it; the run still succeeds when the target has not started."""
    def sync_live(argv):                                         # the schedule sync stores 101 as LIVE (early start)
        if argv[0] == "sync-matches":
            _set_status(box.db, 101, "LIVE")
    _slow_steps(box, monkeypatch, 30, sync_live)                 # 5 minutes in all: T-3 (103) starts mid-run
    box.doc["predictions"] = [p for p in box.doc["predictions"] if p["match_id"] not in (101, 103)]
    assert mc.run(first_pitch="2026-10-08T22:30:00Z", now=NOW) == 0          # neither is required in the export
    r = receipts()[-1]
    assert r["completed_at"] == "2026-10-08T22:05:00Z"
    assert [d["match_id"] for d in r["desk_rows"]] == [102, 100]             # no block for 101 (LIVE) or 103
    assert len(box.notes) == 2 and not any("Underhill" in n or "Passville" in n for n in box.notes)


def test_r1_a_target_whose_stored_status_is_live_fails_the_run(box, monkeypatch):
    def sync_live(argv):
        if argv[0] == "sync-matches":
            _set_status(box.db, 102, "LIVE")                     # the target, 30 minutes out, stored LIVE
    _slow_steps(box, monkeypatch, 1, sync_live)
    assert mc.run(first_pitch="2026-10-08T22:30:00Z", now=NOW) == 1
    r = receipts()[-1]
    assert r["failed"] == "target started" and r["started"] == "stored status LIVE when the steps finished"
    assert box.pushes == [] and box.notes == [] and r["desk_rows"] == []


def test_r2_a_failed_book_sync_fails_the_run_as_stale_prices(box, capsys):
    """R2: the run checks its prices, not a step's console. sync-odds 'succeeds' but stores nothing fresh: every
    summary game that shows books names its book capture time and the run's start. Nothing pushed, no call
    notified. The kalshi-only game (no books) is not stale on books."""
    box.no_fresh = {"sync-odds"}
    assert mc.run(now=NOW) == 1
    r = receipts()[-1]
    assert r["failed"] == "stale prices" and r["push"] is None and box.pushes == [] and box.notes == []
    assert [(x["match_id"], x["price"]) for x in r["stale"]] == [(103, "books"), (101, "books"), (100, "books")]
    assert r["stale"][0] == {"match_id": 103, "game": "Passville Visitors @ Passville",
                             "first_pitch_et": "2026-10-08 18:03 ET", "price": "books",
                             "captured_at": "2026-10-08T19:00:00Z", "run_start": "2026-10-08T22:00:00Z"}
    out = capsys.readouterr().out
    assert ("✗ stale prices: match 101 (2026-10-08 19:02 ET Underhill Visitors @ Underhill): books captured "
            "2026-10-08T19:00:00Z, before the run's start 2026-10-08T22:00:00Z") in out


def test_r2_a_stale_kalshi_quote_fails_and_no_books_or_no_quote_is_not_stale(box):
    box.no_fresh = {"sync-kalshi"}
    assert mc.run(now=NOW) == 1
    r = receipts()[-1]
    assert r["failed"] == "stale prices" and {x["price"] for x in r["stale"]} == {"kalshi"}
    assert [x["match_id"] for x in r["stale"]] == [103, 102, 101, 100]
    # a row with no books and no Kalshi quote is never stale, whatever the stored rows say
    bare = {"predictions": [{"match_id": 103, "market": {"bookmaker_count": 0}, "kalshi_bid": None,
                             "kalshi_ask": None, "kalshi_legs": None}]}
    x = {"match_id": 103, "first_pitch": "2026-10-08T22:03:00Z", "first_pitch_et": "", "away": "A", "home": "H"}
    assert mc.stale_prices(bare, [x], NOW) == []
    # the capture times are the stored rows the export read: the last book session, the latest Kalshi per side
    con = sqlite3.connect(box.db)
    mc_caps = mc.price_captures(con, 103, mc.parse_utc("2026-10-08T22:03:00Z"))
    con.close()
    assert mc_caps["kalshi"] == datetime(2026, 10, 8, 19, 0, tzinfo=timezone.utc)
    assert mc_caps["books"] == datetime(2026, 10, 8, 22, 0, 30, tzinfo=timezone.utc)


def test_r3_the_lock_is_held_from_the_backup_check_until_the_receipt_line(box, monkeypatch):
    seen = {}
    real_backup = mc.todays_backup
    monkeypatch.setattr(mc, "todays_backup", lambda f, d: seen.setdefault("backup", mc.lock_free()) and None
                        or real_backup(f, d))
    monkeypatch.setattr(mc, "push_mirror", lambda: seen.setdefault("push", mc.lock_free()) or {"exit": 0, "tail": []})
    assert mc.run(now=NOW) == 0
    assert seen == {"backup": False, "push": False}               # held at the backup check and at the push
    assert box.receipt_locks == [False]                           # and while the receipt line was written
    assert mc.lock_free()                                         # released after it


def test_r4_a_malformed_first_pitch_is_a_receipted_refusal_exit_2(box):
    assert mc.run(first_pitch="tonight 7pm", now=NOW) == 2
    r = receipts()[-1]
    assert r["kind"] == "mlb_closing" and r["exit"] == 2 and r["refused"].startswith("malformed --first-pitch")
    assert r["first_pitch"] == "tonight 7pm" and box.steps == [] and not (box.tmp / "backups").exists()
    assert mc.main(["run", "--first-pitch", "2026-13-45T99:00Z"]) == 2


def test_r5_a_backup_folder_under_data_refuses_before_anything_else(box, monkeypatch):
    """R5: checked before anything else; refused, receipted, whether or not a backup already sits there (the
    folder is never looked into: no file is ever created under data/, not even in the scratch checkout)."""
    monkeypatch.setenv("SP_BACKUP_DIR", str(c.REPO / "data" / "bk"))
    monkeypatch.setenv("SP_SKIP_FAMILIES", "MLB")                 # checked AFTER the folder
    monkeypatch.delenv("SP_EXPORTS_MIRROR_REMOTE")                # checked after the folder too
    looked = []
    monkeypatch.setattr(mc, "todays_backup", lambda f, d: looked.append(f) or (f / "sports_2026-10-08.db"))
    assert mc.run(now=NOW) == 2
    r = receipts()[-1]
    assert r["exit"] == 2 and r["refused"].startswith("backup folder under data/") and "law 5" in r["refused"]
    assert looked == [] and box.steps == [] and box.pushes == [] and not (c.REPO / "data").exists()


def test_r6_a_closing_that_fails_its_own_checks_leaves_no_calls_behind(box):
    box.doc["predictions"] = [p for p in box.doc["predictions"] if p["match_id"] != 101]    # missing from export
    assert mc.run(now=NOW) == 1
    r = receipts()[-1]
    run_id = r["run_id"]
    assert r["failed"] == "missing from export"
    assert r["export_moved_to"] == f"logs/{run_id}.mlb_MLB_2026-10-08.json"
    assert not (c.REPO / "exports" / "mlb_MLB_2026-10-08.json").exists()
    assert json.loads((c.REPO / r["export_moved_to"]).read_text())["predictions"]           # the file, moved whole
    box.doc = four_kinds_doc()
    box.no_fresh = {"sync-odds"}                                                            # stale prices: moved
    assert mc.run(now=NOW + timedelta(minutes=1)) == 1
    assert receipts()[-1]["failed"] == "stale prices" and receipts()[-1]["export_moved_to"].startswith("logs/")
    assert not list((c.REPO / "exports").glob("*.json"))


def test_failed_run_notifications_from_the_watch_best_effort(box, monkeypatch, capsys):
    """Every watch-started run that does not succeed posts one notification: the first pitch, what failed or why it
    refused, the attempt out of three; the third says no further attempt. A manual run prints only. A notification
    that cannot be posted is recorded in the receipt and changes nothing else."""
    one = box.tmp / "one.db"
    make_db(one, [(1, NOW + timedelta(minutes=30), "SCHEDULED", "A", "H")])
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{one}")
    for i in range(3):
        box.fail_at = len(box.steps) + 1
        assert mc.watch(now=NOW + timedelta(minutes=i)) == 1
    assert box.notes == ["Closing 2026-10-08 18:30 ET: FAILED: step 1 · attempt 1/3",
                         "Closing 2026-10-08 18:30 ET: FAILED: step 1 · attempt 2/3",
                         "Closing 2026-10-08 18:30 ET: FAILED: step 1 · attempt 3/3 · no further attempt will run "
                         "for this first pitch"]
    assert receipts()[-1]["failure_notification"]["posted"] is True
    box.notes.clear()
    box.fail_at = len(box.steps) + 1
    assert mc.run(now=NOW) == 1 and box.notes == []                     # a manual run prints to the console only
    # a watch-started refusal posts why it refused
    monkeypatch.setenv("SP_EXPORTS_MIRROR_REMOTE", "")
    assert mc.run(first_pitch="2026-10-08T22:30:00Z", trigger="watch", now=NOW) == 2
    assert box.notes == ["Closing 2026-10-08 18:30 ET: REFUSED: SP_EXPORTS_MIRROR_REMOTE is not set (environment, "
                         "host.env, the checkout's .env): a closing run pushes the exports mirror or it is not a "
                         "success"]
    # best effort: a notification that raises is recorded, and the run's result is unchanged
    monkeypatch.setattr(mc, "notify", lambda body, title=mc.NOTIFY_TITLE: (_ for _ in ()).throw(OSError("nc down")))
    assert mc.run(first_pitch="2026-10-08T22:30:00Z", trigger="watch", now=NOW) == 2
    assert receipts()[-1]["failure_notification"] == {"text": box.notes[0], "posted": False,
                                                      "error": "OSError: nc down"}


def test_m1_no_mirror_remote_refuses_before_the_first_step(box, monkeypatch):
    monkeypatch.delenv("SP_EXPORTS_MIRROR_REMOTE")
    assert mc.run(now=NOW) == 2
    r = receipts()[-1]
    assert r["exit"] == 2 and "SP_EXPORTS_MIRROR_REMOTE" in r["refused"]
    assert box.steps == [] and box.pushes == [] and not (box.tmp / "backups").exists()


def _setup_sandbox(tmp_path, env_line):
    """A scratch checkout for the setup script: the script, sp_common (how the run reads settings), a venv python
    that is this interpreter, fake launchctl/osascript that record their calls. Never the real checkout's .env."""
    repo, home, bindir = tmp_path / "repo", tmp_path / "home", tmp_path / "bin"
    (repo / "scripts").mkdir(parents=True)
    (repo / "deploy" / "hosting").mkdir(parents=True)
    (repo / "venv" / "bin").mkdir(parents=True)
    shutil.copy2(ROOT / "scripts" / "setup_mlb_closing_watch.sh", repo / "scripts")
    shutil.copy2(HOSTING / "sp_common.py", repo / "deploy" / "hosting")
    py = repo / "venv" / "bin" / "python"
    py.write_text(f"#!/bin/sh\nexec {sys.executable} \"$@\"\n")
    py.chmod(0o755)
    (repo / ".env").write_text(env_line)
    home.mkdir()
    bindir.mkdir()
    for tool in ("launchctl", "osascript"):
        (bindir / tool).write_text(f"#!/bin/sh\necho \"{tool} $*\" >> \"$HOME/calls\"\n")
        (bindir / tool).chmod(0o755)
    env = {"HOME": str(home), "PATH": f"{bindir}:/usr/bin:/bin", "SP_HOST_ENV": str(tmp_path / "no-host.env")}
    return repo, home, env


def test_m1_the_setup_script_refuses_to_install_without_the_mirror_remote(tmp_path):
    repo, home, env = _setup_sandbox(tmp_path, "# no mirror remote here\n")
    r = subprocess.run(["bash", str(repo / "scripts" / "setup_mlb_closing_watch.sh")], capture_output=True,
                       text=True, env=env)
    assert r.returncode == 2 and "REFUSED: SP_EXPORTS_MIRROR_REMOTE is not set" in r.stdout
    assert not (home / "Library" / "LaunchAgents" / "com.sportspredictor.mlbclosingwatch.plist").exists()
    assert not (home / "calls").exists()                          # no launchctl, no notification


def test_m2_the_setup_script_posts_a_test_notification_and_prints_what_the_watch_needs(tmp_path):
    repo, home, env = _setup_sandbox(tmp_path, "SP_EXPORTS_MIRROR_REMOTE=git@example.invalid:x/exports.git\n")
    r = subprocess.run(["bash", str(repo / "scripts" / "setup_mlb_closing_watch.sh")], capture_output=True,
                       text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    calls = (home / "calls").read_text().splitlines()
    assert calls[-1] == ('osascript -e display notification "Test: the MLB closing watch is installed" with title '
                         '"MLB closing"')
    assert any(x.startswith("launchctl load ") for x in calls)
    out = r.stdout
    assert "Test notification: posted." in out
    assert 'You should have seen a notification titled "MLB closing"' in out
    assert "System Settings → Notifications → Script Editor" in out
    assert "The laptop awake" in out and "VPN on, Tailscale off" in out
