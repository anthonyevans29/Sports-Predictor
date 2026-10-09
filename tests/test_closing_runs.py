"""CLOSING RUNS FOR EVERY MODEL FAMILY (ARCHITECT 2026-10-09, addendum 21 item 3, C1-C10; addendum 22: #380 rulings
380.1-380.5, strict mode, the schedule read, reading 7), on #370's frame and #370's test pattern (addendum 13 item 3,
addendum 16 item 2). Against a SCRATCH schedule in a throwaway DB under tmp_path. No real cli step, provider, MLB
feed, Kalshi, ntfy, mirror push or notification is ever reached: every side effect is replaced, and the network is
blocked (the setup-script tests run a fake ntfy on 127.0.0.1 in a subprocess sandbox)."""
import contextlib
import http.server
import json
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HOSTING = ROOT / "deploy" / "hosting"
sys.path.insert(0, str(HOSTING))

import chains  # noqa: E402
import closing as mc  # noqa: E402
import sp_common as c  # noqa: E402
import sp_run  # noqa: E402

from src.walters import desk_policy as dp  # noqa: E402

NOW = datetime(2026, 10, 11, 16, 25, tzinfo=timezone.utc)          # Sunday 12:25 ET
DAY = "2026-10-11"
REAL_NOTIFY = mc.notify                                            # before any fixture replaces it
REAL_PAGE = mc.page_phone
HOLD = "paste to the architect before placing"
TOPIC = "sp-card-topic-scratch-7f3k"                               # a scratch value: never printed, never paged
COMPS = {"MLB": 1, "NFL": 2, "PL": 3}
# (match_id, competition, minutes from NOW, stored status, home). Away = "<home> Visitors".
GAMES = [
    (101, "MLB", 30, "SCHEDULED", "Underhill"),     # PLAY, exec under 4.0pp: the hold          (covered)
    (104, "MLB", 33, "SCHEDULED", "Kalshiburg"),    # kalshi-only suspended for MLB: PASS        (covered)
    (105, "MLB", 35, "SCHEDULED", "Passville"),     # PASS                                       (covered)
    (102, "MLB", 38, "SCHEDULED", "Clearwater"),    # PLAY, exec clears                          (covered)
    (103, "MLB", 45, "SCHEDULED", "Laterton"),      # outside the 10 minutes: the next start time
    (200, "MLB", -20, "LIVE", "Startedton"),        # started
    (301, "NFL", 35, "SCHEDULED", "Buffalo"),       # PLAY                                       (covered)
    (304, "NFL", 36, "SCHEDULED", "Denver"),        # PASS                                       (covered)
    (302, "NFL", 38, "SCHEDULED", "Newark"),        # quarantine shadow (PASS)                   (covered)
    (303, "NFL", 40, "SCHEDULED", "Tampa"),         # value shadow (PASS)                        (covered)
    (305, "NFL", 50, "SCHEDULED", "Seattle"),       # the next start time
    (401, "PL", 35, "SCHEDULED", "Arsenal"),        # PLAY                                       (covered)
    (402, "PL", 37, "SCHEDULED", "Fulham"),         # PASS                                       (covered)
    (403, "PL", 60, "SCHEDULED", "Chelsea"),        # the next start time
]


# ------------------------------------------------------------------------------------------------ helpers --

def _ts(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S.000000")


def make_db(path: Path, games=GAMES, now=NOW) -> None:
    """The stored shape: enum NAMES, naive UTC text; the tables the closing run reads (src/db/schema.py names)."""
    con = sqlite3.connect(path)
    con.executescript(
        "CREATE TABLE competitions(id INTEGER PRIMARY KEY, code TEXT);"
        "CREATE TABLE teams(id INTEGER PRIMARY KEY, name TEXT);"
        "CREATE TABLE matches(id INTEGER PRIMARY KEY, competition_id INT, utc_date DATETIME, status TEXT,"
        " home_team_id INT, away_team_id INT);"
        "CREATE TABLE odds(id INTEGER PRIMARY KEY, match_id INT, bookmaker TEXT, market TEXT, selection TEXT,"
        " price_decimal REAL, line REAL, captured_at DATETIME, source TEXT);"
        "CREATE TABLE odds_snapshots(id INTEGER PRIMARY KEY, match_id INT, market TEXT, selection TEXT,"
        " devig_prob REAL, line REAL, captured_at DATETIME, source TEXT, yes_bid REAL, yes_ask REAL);"
        "CREATE TABLE match_participants(id INTEGER PRIMARY KEY, match_id INT, team_id INT, role TEXT, kind TEXT,"
        " player_source_id TEXT, player_name TEXT, source TEXT, refreshed_at DATETIME);"
        "INSERT INTO competitions VALUES (1, 'MLB'), (2, 'NFL'), (3, 'PL'), (4, 'NCAA');")
    tid = 0
    for mid, comp, minutes, status, home in games:
        con.execute("INSERT INTO teams VALUES (?, ?)", (tid + 1, home))
        con.execute("INSERT INTO teams VALUES (?, ?)", (tid + 2, f"{home} Visitors"))
        con.execute("INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?)",
                    (mid, COMPS[comp], _ts(now + timedelta(minutes=minutes)), status, tid + 1, tid + 2))
        if comp == "MLB":                           # probable starters, stored by a morning sync-pitchers
            for t in (tid + 1, tid + 2):
                con.execute("INSERT INTO match_participants(match_id, team_id, role, kind, player_name, source,"
                            " refreshed_at) VALUES (?, ?, 'starting_pitcher', 'confirmed', 'P', 'mlb_stats_api', ?)",
                            (mid, t, _ts(now - timedelta(hours=3))))
        tid += 2
    # an NCAA game in the window is never a closing game (market-only: C1)
    con.execute("INSERT INTO matches VALUES (999, 4, ?, 'SCHEDULED', 1, 2)", (_ts(now + timedelta(minutes=35)),))
    for comp in COMPS.values():
        write_prices(con, now - timedelta(hours=3), comp_id=comp)   # morning prices: stale for any run
    con.commit()
    con.close()


def write_prices(con, at, kinds=("books", "kalshi"), comp_id=1, ids=None):
    """What a book sync / a Kalshi sync stores at capture time `at`, for the competition's games not started at
    `at` (or only `ids`): the 1X2 board replaced at one stamp, a Kalshi snapshot per side appended."""
    for (mid,) in con.execute("SELECT id FROM matches WHERE competition_id = ? AND utc_date > ?",
                              (comp_id, _ts(at))).fetchall():
        if ids is not None and mid not in ids:
            continue
        sels = ("HOME", "DRAW", "AWAY") if comp_id == 3 else ("HOME", "AWAY")
        if "books" in kinds:
            con.execute("DELETE FROM odds WHERE match_id = ?", (mid,))
            for bk in ("bk1", "bk2"):
                for sel in sels:
                    con.execute("INSERT INTO odds(match_id, bookmaker, market, selection, price_decimal, captured_at,"
                                " source) VALUES (?, ?, '1X2', ?, 2.0, ?, 'books')", (mid, bk, sel, _ts(at)))
        if "kalshi" in kinds:
            for sel in sels:
                con.execute("INSERT INTO odds_snapshots(match_id, market, selection, devig_prob, captured_at, source,"
                            " yes_bid, yes_ask) VALUES (?, 'ML', ?, 0.5, ?, 'kalshi', 0.49, 0.5)", (mid, sel, _ts(at)))
    con.commit()


def run_start_of(run_id):
    return datetime.strptime(run_id[:16], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)


def row(mid, home, p_home, *, fair_h=None, bid=0.49, ask=0.50, minutes=35, comp="MLB", series="KXMLBGAME",
        draw=None, fair_d=None, now=NOW, pitchers=("home", "away")):
    mk = {"bookmaker_count": 9 if fair_h is not None else 0}
    if fair_h is not None:
        mk["fair_prob"] = ({"HOME": fair_h, "AWAY": round(1 - fair_h, 4)} if draw is None else
                           {"HOME": fair_h, "DRAW": fair_d, "AWAY": round(1 - fair_h - fair_d, 4)})
    tick = home[:3].upper()
    r = {"match_id": mid, "home_team": home, "away_team": f"{home} Visitors", "competition": comp, "stage": "regular",
         "utc_date": (now + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S"),
         "prediction": {"probabilities": {"home_win": p_home, "draw": draw,
                                          "away_win": round(1 - p_home - (draw or 0), 4)}, "tier": "lean"},
         "market": mk, "kalshi_bid": bid, "kalshi_ask": ask,
         "kalshi_legs": {"HOME": {"ticker": f"{series}-26OCT11-{tick}H", "bid": bid, "ask": ask},
                         "AWAY": {"ticker": f"{series}-26OCT11-{tick}A", "bid": round(1 - ask, 2),
                                  "ask": round(1 - bid, 2)}}}
    if comp == "MLB":
        r["pitchers"] = {s: ({"name": f"{s} starter", "kind": "confirmed"} if s in pitchers else None)
                         for s in ("home", "away")}
    if comp == "NFL" and fair_h is not None:
        r["market_divergence_pp"] = round((p_home - fair_h) * 100, 1)
        r["quarantine"] = abs(r["market_divergence_pp"]) >= 15
    if draw is not None:
        r["kalshi_legs"]["DRAW"] = {"ticker": f"{series}-26OCT11-TIE", "bid": 0.26, "ask": 0.27}
    return r


def mlb_doc(now=NOW):
    rows = [row(101, "Underhill", 0.58, fair_h=0.535, bid=0.54, ask=0.55, minutes=30, now=now),
            row(104, "Kalshiburg", 0.56, minutes=33, now=now),
            row(105, "Passville", 0.52, fair_h=0.51, bid=0.50, ask=0.51, minutes=35, now=now),
            row(102, "Clearwater", 0.60, fair_h=0.53, bid=0.51, ask=0.52, minutes=38, now=now),
            row(103, "Laterton", 0.60, fair_h=0.53, bid=0.51, ask=0.52, minutes=45, now=now),
            row(200, "Startedton", 0.60, fair_h=0.53, bid=0.51, ask=0.52, minutes=-20, now=now)]
    return dp.annotate({"sport": "mlb", "predictions": rows}, now=now)


def nfl_doc(now=NOW):
    k = {"comp": "NFL", "series": "KXNFLGAME", "now": now}
    rows = [row(301, "Buffalo", 0.62, fair_h=0.55, bid=0.54, ask=0.55, minutes=35, **k),
            row(304, "Denver", 0.52, fair_h=0.515, bid=0.51, ask=0.52, minutes=36, **k),
            row(302, "Newark", 0.75, fair_h=0.55, bid=0.54, ask=0.55, minutes=38, **k),
            row(303, "Tampa", 0.60, fair_h=0.70, bid=0.69, ask=0.70, minutes=40, **k),
            row(305, "Seattle", 0.52, fair_h=0.515, bid=0.51, ask=0.52, minutes=50, **k)]
    return dp.annotate({"sport": "nfl", "predictions": rows}, now=now)


def pl_doc(now=NOW):
    k = {"comp": "PL", "series": "KXEPLGAME", "now": now}
    rows = [row(401, "Arsenal", 0.55, fair_h=0.45, fair_d=0.27, draw=0.25, bid=0.44, ask=0.45, minutes=35, **k),
            row(402, "Fulham", 0.40, fair_h=0.39, fair_d=0.30, draw=0.30, bid=0.38, ask=0.39, minutes=37, **k),
            row(403, "Chelsea", 0.40, fair_h=0.39, fair_d=0.30, draw=0.30, bid=0.38, ask=0.39, minutes=60, **k)]
    return dp.annotate({"sport": "soccer", "predictions": rows}, now=now)


def receipts():
    p = c.receipts_path()
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def call_pages(box):
    """The run pages (C5), not the failed-run notices that also reach the phone."""
    return [p for p in box.pages if not p["body"].startswith("Closing ")]


def runs(fam=None):
    return [r for r in receipts() if r["kind"] == "closing" and (fam is None or r["family"] == fam)]


class Box:
    def __init__(self):
        self.steps, self.notes, self.pages, self.pushes, self.feed_calls = [], [], [], [], 0
        self.fail_at = None            # step number (counted over the whole test) that exits 1
        self.fail_cmd = {}             # command -> (exit, tail) it returns
        self.feed = (True, "HTTP 200")
        self.docs = {}
        self.lock_seen = []
        self.tails = {}
        self.no_fresh = set()          # sync commands that store nothing fresh (a failed sync: R2 / 380.1)
        self.stale_sides = set()       # (match_id, side) sync-pitchers does not refresh (380.1)
        self.page_ok = True
        self.receipt_locks = []


SYNC_PRICES = {"sync-odds": "books", "sync-odds-football": "books", "sync-kalshi": "kalshi",
               "sync-kalshi-nfl": "kalshi", "sync-kalshi-soccer": "kalshi"}


@pytest.fixture
def box(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "exports").mkdir(parents=True)
    monkeypatch.setattr(c, "REPO", repo)
    monkeypatch.setattr(c, "HOST_ENV", tmp_path / "no-host.env")
    monkeypatch.setattr(c, "_DOTENV_CACHE", None)
    for k in ("SP_SKIP_FAMILIES", "NTFY_TOPIC", "NTFY_CARD_TOPIC", "NTFY_SERVER", "SP_EXPORTS_MIRROR_REMOTE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SP_EXPORTS_MIRROR_REMOTE", "git@example.invalid:scratch/exports.git")   # M1 (push faked)
    monkeypatch.setenv("NTFY_CARD_TOPIC", TOPIC)                                                # C6 (page faked)
    monkeypatch.setenv("SP_RECEIPTS", str(tmp_path / "logs" / "receipts.jsonl"))
    monkeypatch.setenv("SP_LOCK", str(tmp_path / "logs" / "db.lock"))
    monkeypatch.setenv("SP_BACKUP_DIR", str(tmp_path / "backups"))
    db = tmp_path / "scratch" / "sports.db"
    db.parent.mkdir()
    make_db(db)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    b = Box()
    b.tmp, b.db, b.repo = tmp_path, db, repo
    b.docs = {"MLB": mlb_doc(), "NFL": nfl_doc(), "SOCCER": pl_doc()}

    def fake_step(argv, run_id):
        b.steps.append(list(argv))
        b.lock_seen.append(mc.lock_free() if hasattr(mc, "lock_free") else lock_free())
        if b.fail_at == len(b.steps):
            return 1, ["boom"], 0.1
        if argv[0] in b.fail_cmd:
            rc, tail = b.fail_cmd[argv[0]]
            return rc, tail, 0.1
        at = run_start_of(run_id) + timedelta(seconds=30)
        kind = SYNC_PRICES.get(argv[0])
        if kind and argv[0] not in b.no_fresh:
            comp = ("PL" if argv[0] == "sync-kalshi-soccer" else "NFL" if argv[0] in ("sync-odds-football",
                    "sync-kalshi-nfl") else "MLB" if argv[0] == "sync-kalshi" else argv[argv.index("--competition") + 1])
            ids = ({int(x) for x in argv[argv.index("--match-ids") + 1].split(",")} if "--match-ids" in argv
                   else None)
            con = sqlite3.connect(c.db_path())
            write_prices(con, at, (kind,), COMPS[comp], ids)
            con.close()
        if argv[0] == "sync-pitchers" and "sync-pitchers" not in b.no_fresh:
            con = sqlite3.connect(c.db_path())
            for mid, tid, home_id in con.execute(
                    "SELECT p.match_id, p.team_id, m.home_team_id FROM match_participants p JOIN matches m "
                    "ON m.id = p.match_id").fetchall():
                if (mid, "home" if tid == home_id else "away") not in b.stale_sides:
                    con.execute("UPDATE match_participants SET refreshed_at = ? WHERE match_id = ? AND team_id = ?",
                                (_ts(at), mid, tid))
            con.commit()
            con.close()
        day = run_start_of(run_id).date().isoformat()
        if argv[0] == "export-predictions" and "--date" in argv:
            (repo / "exports" / f"mlb_MLB_{argv[argv.index('--date') + 1]}.json").write_text(json.dumps(b.docs["MLB"]))
        elif argv[0] == "export-predictions":
            (repo / "exports" / f"soccer_PL_{day}.json").write_text(json.dumps(b.docs["SOCCER"]))
        elif argv[0] == "export-nfl-predictions":
            (repo / "exports" / f"nfl_predictions_{day}.json").write_text(json.dumps(b.docs["NFL"]))
        return 0, list(b.tails.get(argv[0], ["ok"])), 0.1

    def fake_feed():
        b.feed_calls += 1
        return b.feed

    def fake_page(title, body, priority="default"):
        b.pages.append({"title": title, "body": body, "priority": priority})
        return {"accepted": True, "http": 200} if b.page_ok else {"accepted": False, "http": 400}

    b.fake_step = fake_step
    monkeypatch.setattr(mc, "run_step", fake_step)
    monkeypatch.setattr(mc, "feed_answers", fake_feed)
    monkeypatch.setattr(mc, "notify", lambda body, title="Closing": b.notes.append(body) or {"posted": True})
    monkeypatch.setattr(mc, "page_phone", fake_page)
    monkeypatch.setattr(mc, "push_mirror", lambda: b.pushes.append(1) or {"exit": 0, "tail": ["pushed"]})
    real_append = c.append_receipt

    def watched_append(rec):
        b.receipt_locks.append(lock_free())
        return real_append(rec)
    monkeypatch.setattr(c, "append_receipt", watched_append)

    def no_net(*a, **k):
        raise AssertionError("network used")
    monkeypatch.setattr(socket, "create_connection", no_net)
    monkeypatch.setattr(socket.socket, "connect", no_net)
    return b


def lock_free() -> bool:
    import fcntl
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


@contextlib.contextmanager
def hold_lock():
    import fcntl
    p = c.lock_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def fake_clock(monkeypatch):
    clock = {"t": __import__("time").time()}
    monkeypatch.setattr(mc, "time", type("T", (), {"time": staticmethod(lambda: clock["t"])}))
    return clock


def slow_steps(box, monkeypatch, seconds_each, on_step=None):
    clock = fake_clock(monkeypatch)
    inner = box.fake_step

    def slow_step(argv, run_id):
        out = inner(argv, run_id)
        clock["t"] += seconds_each
        if on_step:
            on_step(argv)
        return out
    monkeypatch.setattr(mc, "run_step", slow_step)
    return clock


def set_status(db, mid, status):
    con = sqlite3.connect(db)
    con.execute("UPDATE matches SET status = ? WHERE id = ?", (status, mid))
    con.commit()
    con.close()


def at(minutes):
    return (NOW + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


# ============================================================================================ C1 families ==

def test_c1_a_closing_run_for_every_live_model_family_and_no_shadow():
    """C1: "A closing run exists for every family whose calls come from a live model: MLB, NFL and SOCCER (PL) today.
    [...] A shadow has no closing run and is never paged as a pick." """
    assert chains.CLOSING_FAMILIES == {"MLB": "mlb-closing", "NFL": "nfl-closing", "SOCCER": "soccer-closing"}
    assert set(mc.FAMILIES) == set(chains.CLOSING_FAMILIES)
    assert {f: v["comps"] for f, v in mc.FAMILIES.items()} == {"MLB": ("MLB",), "NFL": ("NFL",), "SOCCER": ("PL",)}
    never = {"NCAA", "NHL", "UNL", "CL", "UEL", "EFL", *chains.EXPANSION_CODES}       # market-only + shadows
    for fam, v in mc.FAMILIES.items():
        assert not never & set(v["comps"])
        for st in chains.CHAINS[v["chain"]]["steps"]:
            assert not never & set(st), (fam, st)
    assert set(chains.FRESHEN_FAMILY.values()) == set(mc.FAMILIES)                       # the live-model set


def test_c1_a_market_only_game_in_the_window_is_never_covered(box):
    for fam in mc.FAMILIES:
        assert 999 not in {g["match_id"] for g in mc.schedule(fam, NOW)}


# ============================================================================================== C3 chains ==

def test_c3_mlb_closing_chain_is_370s():
    pre, clo = chains.CHAINS["mlb-preslate"]["steps"], chains.CHAINS["mlb-closing"]["steps"]
    assert len(pre) == len(clo) == 10
    assert clo[:9] == pre[:9]                                   # opens with the schedule read (sync-matches MLB)
    assert clo[0][0] == "sync-matches"
    assert clo[9] == [*pre[9], "--date", "{today}", "--desk"]


@pytest.mark.parametrize("fam,freshen,comp,season", [("NFL", "freshen:NFL", "NFL", "2026"),
                                                      ("SOCCER", "freshen:SOCCER", "PL", "2026/27")])
def test_c3_nfl_and_soccer_closing_chains_are_their_freshen_chains_opening_with_the_schedule_read(
        fam, freshen, comp, season):
    """C3 + addendum 22: the freshen chain's steps in order, ending in the export that carries the Desk's call,
    opened by the schedule read (status and start time) for its games."""
    clo = chains.CHAINS[chains.CLOSING_FAMILIES[fam]]["steps"]
    fr = chains.CHAINS[freshen]["steps"]
    assert clo[0] == ["sync-matches", "--competition", comp, "--season", season,
                      "--date-from", "{start_day}", "--date-to", "{start_day}"]
    assert clo[1] == ["sync-matches", "--competition", comp, "--season", season,
                      "--date-from", "{end_day}", "--date-to", "{end_day}"]
    assert [s[:len(f)] for s, f in zip(clo[2:], fr)] == fr and len(clo) == len(fr) + 2   # derived, never copied
    assert clo[-1][-1] == "--desk" and clo[-1][0].startswith("export")
    inj = next(s for s in clo if s[0] == "sync-injuries")
    assert inj[-3:] == ["--kickoff-within-hours", "{within_h}", "--strict"]
    odds = next(s for s in clo if s[0] in ("sync-odds", "sync-odds-football"))
    assert odds[-2:] == ["--match-ids", "{match_ids}"]
    # freshen chains themselves unchanged (the window service runs them)
    assert chains.CHAINS["freshen:NFL"]["steps"][0] == ["sync-injuries", "--competition", "NFL", "--season", "2026"]


def test_c3_a_run_prices_the_games_it_covers_not_the_whole_league(box):
    games = mc.schedule("NFL", NOW)
    s = NOW + timedelta(minutes=35)
    cov = mc.cover(games, s, NOW)
    assert [g["match_id"] for g in cov] == [301, 304, 302, 303]
    steps = mc.resolve_steps("NFL", s, cov, NOW)
    assert steps[0] == ["sync-matches", "--competition", "NFL", "--season", "2026", "--date-from", DAY,
                        "--date-to", DAY]
    assert steps[1][0] == "sync-injuries"                  # the identical second schedule read is dropped
    assert steps[1][-3:] == ["--kickoff-within-hours", "0.67", "--strict"]   # 40 minutes, rounded up
    assert steps[2] == ["sync-odds-football", "--match-ids", "301,302,303,304"]
    assert steps[-1] == ["export-nfl-predictions", "--desk"]
    # a cover spanning UTC midnight reads both days
    late = [{**cov[0], "start": datetime(2026, 10, 11, 23, 58, tzinfo=timezone.utc)},
            {**cov[1], "start": datetime(2026, 10, 12, 0, 6, tzinfo=timezone.utc)}]
    st2 = mc.resolve_steps("SOCCER", late[0]["start"], late, datetime(2026, 10, 11, 23, 23, tzinfo=timezone.utc))
    assert [s_[-1] for s_ in st2[:2]] == ["2026-10-11", "2026-10-12"]
    assert st2[2] == ["sync-odds", "--competition", "PL", "--season", "2026/27", "--match-ids", "301,304"]


def test_c3_the_scoping_options_leave_each_commands_default_unchanged():
    import inspect

    import cli
    from src.ingestion import service
    for name, opt in (("sync-odds", "--match-ids"), ("sync-odds-football", "--match-ids"),
                      ("sync-injuries", "--strict")):
        p = next(x for x in cli.cli.commands[name].params if opt in x.opts)
        assert p.default in (None, False), name
    assert inspect.signature(service.sync_odds_nfl).parameters["match_ids"].default is None
    assert inspect.signature(service.IngestionService.sync_odds).parameters["match_ids"].default is None
    assert cli._match_ids_opt(None) is None and cli._match_ids_opt("3, 1") == {1, 3}


def test_c3_sync_odds_match_ids_prices_only_those_games(monkeypatch):
    """The soccer path with a fake adapter on the throwaway DB: --match-ids keeps the listed games only; without it,
    every upcoming game is a candidate, as before."""
    from src.db.database import init_db, session_scope
    from src.db.schema import Competition, Match, MatchStatus, Sport, Team
    from src.ingestion.service import IngestionService
    from src.timeutil import utc_now_naive
    init_db()
    with session_scope() as s:
        comp = Competition(sport=Sport.SOCCER, code="CLSX", name="closing scope", area="X", type="LEAGUE")
        s.add(comp)
        s.flush()
        t = [Team(sport=Sport.SOCCER, name=f"CLSX {i}") for i in range(4)]
        s.add_all(t)
        s.flush()
        ids = []
        for i in range(2):
            m = Match(sport=Sport.SOCCER, competition_id=comp.id, season="2093/94", status=MatchStatus.SCHEDULED,
                      utc_date=utc_now_naive() + timedelta(hours=1 + i), home_team_id=t[2 * i].id,
                      away_team_id=t[2 * i + 1].id, external_ids={"fake": str(i)})
            s.add(m)
            s.flush()
            ids.append(m.id)
    asked = []
    ad = type("A", (), {"source_name": "fake", "list_odds": lambda self, sid: asked.append(sid) or []})()
    IngestionService(ad).sync_odds("CLSX", season="2093/94", match_ids={ids[1]})
    assert asked == ["1"]
    asked.clear()
    IngestionService(ad).sync_odds("CLSX", season="2093/94")
    assert sorted(asked) == ["0", "1"]


# ============================================================================================== C2 timing ==

def test_c2_the_watch_starts_each_family_at_t35_covering_the_10_minutes_after(box):
    """C2: "A run starts when the earliest unstarted start time of a family is 35 minutes away, and it covers every
    game of that family starting within the 10 minutes after that time." """
    assert mc.watch(now=NOW - timedelta(minutes=1)) == 0          # MLB's +30 is now 31 away: due; NFL/PL 36: not
    assert [r["family"] for r in runs()] == ["MLB"]
    assert mc.watch(now=NOW) == 0                                 # NFL and SOCCER at T-35 (MLB closed: silent)
    got = {r["family"]: r for r in runs()}
    assert [r["family"] for r in runs()] == ["MLB", "NFL", "SOCCER"]
    assert all(r["exit"] == 0 and r["trigger"] == "watch" for r in runs())
    assert [x["match_id"] for x in got["MLB"]["covers"]] == [101, 104, 105, 102]   # +29..+39 at that tick; 103 out
    assert [x["match_id"] for x in got["NFL"]["covers"]] == [301, 304, 302, 303]   # +35..+45; 305 (+50) out
    assert [x["match_id"] for x in got["SOCCER"]["covers"]] == [401, 402]          # 403 (+60) out
    assert got["NFL"]["start"] == at(35) and got["SOCCER"]["start"] == at(35)


def test_c2_the_next_start_time_is_the_first_game_after_the_covered_10_minutes(box, capsys):
    assert mc.watch(now=NOW) == 0
    n = len(runs())
    capsys.readouterr()
    assert mc.watch(now=NOW + timedelta(minutes=9)) == 0          # MLB 103 (+45) is 36 away: not yet
    assert len(runs()) == n and capsys.readouterr().out == ""      # silent
    assert mc.watch(now=NOW + timedelta(minutes=10)) == 0         # 103 at T-35: its own run
    assert runs()[-1]["family"] == "MLB" and runs()[-1]["start"] == at(45)
    assert [x["match_id"] for x in runs()[-1]["covers"]] == [103]


def test_c2_summary_and_page_hold_the_runs_own_games_only(box, capsys):
    """C2: "This replaces #370's 5 to 65 minute window and its 90-minute summary: a run's summary and page hold its
    own games only." """
    assert mc.run("MLB", start=at(30), now=NOW) == 0
    out = capsys.readouterr().out
    summary = out.split("=== MLB closing summary")[1].split("--- page")[0]
    assert [d["match_id"] for d in runs()[-1]["desk_rows"]] == [101, 104, 105, 102]
    assert "Laterton" not in summary and "Startedton" not in summary              # 103 (+45) and the started game
    assert len(box.pages) == 1 and "Laterton" not in box.pages[0]["body"]
    assert "Clearwater" in box.pages[0]["body"]


def test_c2_at_most_three_attempts_and_none_inside_t5(box):
    box.fail_cmd["sync-matches"] = (1, ["boom"])
    for i in range(4):
        mc.watch(now=NOW + timedelta(minutes=i), families=("MLB",))
    att = runs("MLB")
    assert [r["attempt"] for r in att] == [1, 2, 3] and all(r["exit"] == 1 for r in att)
    assert box.notes[2].endswith("attempt 3/3 · no further attempt will run for this first pitch")
    # SOCCER: its start time first seen inside T-5 (the laptop slept): no attempt, a miss, notified once
    box.fail_cmd.clear()
    for m in (31, 32):
        assert mc.watch(now=NOW + timedelta(minutes=m), families=("SOCCER",)) == 0
    assert {x["match_id"] for r in runs("SOCCER") for x in r["covers"]} == {403}     # 401/402: no attempt
    miss = [r for r in receipts() if r["kind"] == "closing_miss" and r["family"] == "SOCCER"]
    assert len(miss) == 1 and miss[0]["reason"].startswith("inside T-5") and miss[0]["start"] == at(35)


def test_c2_a_run_that_finds_the_lock_held_starts_when_it_is_free(box, monkeypatch):
    import time as _t
    real_sleep = _t.sleep
    monkeypatch.setattr(c.time, "sleep", lambda s: real_sleep(0.02))
    release = threading.Event()
    held = threading.Event()

    def holder():
        with hold_lock():
            held.set()
            release.wait(5)
    th = threading.Thread(target=holder)
    th.start()
    held.wait(5)
    threading.Timer(0.3, release.set).start()
    assert mc.run("NFL", start=at(35), trigger="watch", now=NOW) == 0          # waited, then ran
    th.join()
    assert runs()[-1]["exit"] == 0 and len(box.steps) == 6


# ============================================================================================== C4 checks ==

@pytest.mark.parametrize("fam,start,sync", [("NFL", 35, "sync-odds-football"), ("SOCCER", 35, "sync-odds"),
                                            ("MLB", 30, "sync-odds")])
def test_c4_r2_stale_prices_fail_every_family_and_r6_moves_its_export(box, fam, start, sync):
    box.no_fresh = {sync}
    assert mc.run(fam, start=at(start), now=NOW) == 1
    r = runs(fam)[-1]
    assert r["failed"] == "stale prices" and {x["price"] for x in r["stale"]} == {"books"}
    assert r["stale"][0]["run_start"] == "2026-10-11T16:25:00Z" and r["stale"][0]["captured_at"] == "2026-10-11T13:25:00Z"
    assert r["export_moved_to"].startswith(f"logs/{r['run_id']}.")                     # R6
    assert box.pushes == [] and box.pages == [] and r["push"] is None


@pytest.mark.parametrize("fam,mid", [("NFL", 304), ("SOCCER", 402)])
def test_c4_r1_missing_and_started_for_nfl_and_soccer(box, monkeypatch, fam, mid):
    box.docs[fam]["predictions"] = [p for p in box.docs[fam]["predictions"] if p["match_id"] != mid]
    assert mc.run(fam, start=at(35), now=NOW) == 1
    assert runs(fam)[-1]["failed"] == "missing from export" and runs(fam)[-1]["missing"][0]["match_id"] == mid
    # R1: the same game stored LIVE by the schedule read: not required, no line; the run succeeds
    first = 301 if fam == "NFL" else 401

    def live(argv):
        if argv[0] == "sync-matches":
            set_status(box.db, mid, "LIVE")
    slow_steps(box, monkeypatch, 1, live)
    assert mc.run(fam, start=at(35), now=NOW + timedelta(seconds=5)) == 0
    assert mid not in [d["match_id"] for d in runs(fam)[-1]["desk_rows"]]
    set_status(box.db, first, "LIVE")                         # the target itself stored LIVE: nothing to close
    assert mc.run(fam, start=at(35), now=NOW + timedelta(seconds=9)) == 2
    assert runs(fam)[-1]["refused"].startswith(f"no unstarted {fam} game at kickoff {at(35)}")


@pytest.mark.parametrize("fam", ["NFL", "SOCCER"])
def test_c4_refusals_lock_push_and_failed_run_notice_for_every_family(box, monkeypatch, fam):
    monkeypatch.setenv("SP_SKIP_FAMILIES", fam)
    assert mc.run(fam, start=at(35), now=NOW) == 2 and runs(fam)[-1]["refused"] == f"SP_SKIP_FAMILIES names {fam} here"
    monkeypatch.delenv("SP_SKIP_FAMILIES")
    monkeypatch.setattr(mc, "push_mirror", lambda: {"exit": 1, "tail": ["rejected"]})
    assert mc.run(fam, start=at(35), trigger="watch", now=NOW) == 1
    r = runs(fam)[-1]
    assert r["failed"] == "push" and (box.repo / r["export"]).is_file() and call_pages(box) == []   # in place
    assert box.notes[-1] == f"Closing {fam} 2026-10-11 13:00 ET: FAILED: push · attempt 1/3"
    assert r["failure_notification"]["phone"]["accepted"] is True                   # phone too, best effort
    assert box.receipt_locks[-1] is False and box.lock_seen and not any(box.lock_seen)   # R3


# ================================================================================================ C5 page ==

def test_c5_the_page_format(box, capsys):
    """C5, the NFL run: header (family, start in ET, minutes to it); one line per PLAY (pick, units, the order line
    as the export prints it, exec edge); value and quarantine shadows ending 'shadow, not staked'; the PASS count;
    'was' where the call differs from the last file's; high priority with a PLAY; no line over 100 characters."""
    prev = nfl_doc()
    for p in prev["predictions"]:
        if p["match_id"] == 301:
            p["desk"]["call"], p["desk"]["units"] = "PASS", 0                       # the morning file: PASS
    (box.repo / "exports" / f"nfl_predictions_{DAY}.json").write_text(json.dumps(prev))
    assert mc.run("NFL", start=at(35), now=NOW) == 0
    pg = box.pages[-1]
    assert pg["priority"] == "high" and pg["title"] == "NFL closing 13:00 ET"
    assert pg["body"].splitlines() == [
        "NFL 13:00 ET · T-35m",
        "PLAY Buffalo 1u · BUY YES KXNFLGAME-26OCT11-BUFH @ 0.55 × 10 · exec +5.3pp · was PASS",
        "value shadow Tampa Visitors 0.25u · edge +10.0pp · exec +7.5pp · shadow, not staked",
        "quarantine shadow Newark 0.5u · edge +20.0pp · exec +18.2pp · shadow, not staked",
        "PASS: 3 games"]
    order = box.docs["NFL"]["predictions"][0]["desk"]["order"]["text"]
    assert order in pg["body"]                                                       # as the export prints it
    assert box.notes[-1] == pg["body"]                                               # the screen: the same page
    assert runs()[-1]["page"]["phone"] == {"accepted": True, "http": 200}


def test_c5_mlb_page_hold_wrap_and_no_play_is_default_priority(box):
    assert mc.run("MLB", start=at(30), now=NOW) == 0
    lines = box.pages[-1]["body"].splitlines()
    assert lines[0] == "MLB 12:55 ET · T-30m" and all(len(x) <= 100 for x in lines)
    assert lines[1] == "PLAY Underhill 0.5u · BUY YES KXMLBGAME-26OCT11-UNDH @ 0.55 × 5 · exec +2.2pp"
    assert lines[2] == f"  {HOLD}"                                                   # 104 chars: wrapped, never cut
    assert lines[3] == "PLAY Clearwater 1u · BUY YES KXMLBGAME-26OCT11-CLEH @ 0.52 × 10 · exec +7.1pp"
    assert lines[-1] == "PASS: 2 games" and box.pages[-1]["priority"] == "high"
    assert "Kalshiburg" not in box.pages[-1]["body"]          # the kalshi-only hold is a record, never a pick
    assert mc.run("SOCCER", start=at(35), now=NOW) == 0
    assert box.pages[-1]["body"].splitlines()[1].startswith("PLAY Arsenal 0.5u · BUY YES KXEPLGAME-26OCT11-ARSH")
    box.docs["SOCCER"]["predictions"] = [p for p in pl_doc()["predictions"]]
    for p in box.docs["SOCCER"]["predictions"]:
        p["desk"]["call"] = "PASS"
    assert mc.run("SOCCER", start=at(35), now=NOW + timedelta(minutes=1)) == 0
    assert box.pages[-1]["priority"] == "default" and box.pages[-1]["body"].splitlines()[-1] == "PASS: 2 games"


def test_c5_wrap_never_exceeds_100_and_keeps_the_ending():
    parts = ["PLAY A-very-long-team-name-from-somewhere 1u", "BUY YES " + "X" * 60 + " @ 0.55 × 10", "exec +5.3pp",
             HOLD, "was PASS"]
    lines = mc.wrap(parts)
    assert all(len(x) <= 100 for x in lines) and lines[-1].endswith("was PASS") and not lines[0].startswith(" ")
    assert mc.wrap(["y" * 230])[0] == "y" * 100 and all(len(x) <= 100 for x in mc.wrap(["y" * 230]))


# ================================================================================================ C6 phone ==

def test_c6_no_card_topic_refuses_before_the_first_step_and_never_prints_a_value(box, monkeypatch, capsys):
    monkeypatch.delenv("NTFY_CARD_TOPIC")
    assert mc.run("NFL", start=at(35), now=NOW) == 2
    r = runs()[-1]
    assert r["refused"].startswith("NTFY_CARD_TOPIC is not set") and box.steps == []
    assert not (box.tmp / "backups").exists()
    monkeypatch.setenv("NTFY_CARD_TOPIC", TOPIC + " ")                               # a pasted trailing space
    assert mc.run("NFL", start=at(35), now=NOW) == 2
    assert "contains whitespace" in runs()[-1]["refused"]
    assert TOPIC not in capsys.readouterr().out and TOPIC not in c.receipts_path().read_text()


def test_c6_a_page_ntfy_does_not_accept_fails_the_run_and_the_watch_retries(box):
    box.page_ok = False
    assert mc.watch(now=NOW, families=("NFL",)) == 1
    r = runs()[-1]
    assert r["failed"] == "page" and r["page"]["phone"] == {"accepted": False, "http": 400} and r["push"]["exit"] == 0
    box.page_ok = True
    assert mc.watch(now=NOW + timedelta(minutes=1), families=("NFL",)) == 0
    assert runs()[-1]["exit"] == 0 and runs()[-1]["attempt"] == 2


def test_c6_the_real_page_posts_to_the_card_topic_and_records_no_topic(monkeypatch):
    seen = []

    class R:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: seen.append(req) or R())
    monkeypatch.setenv("NTFY_CARD_TOPIC", TOPIC)
    monkeypatch.setenv("NTFY_SERVER", "https://ntfy.example.invalid")
    res = REAL_PAGE("NFL closing 13:00 ET", "NFL 13:00 ET · T-35m\nPASS: 1 game", "high")
    assert res == {"accepted": True, "http": 200} and TOPIC not in json.dumps(res)
    assert seen[0].full_url == f"https://ntfy.example.invalid/{TOPIC}" and seen[0].get_header("Priority") == "high"


# ================================================================================================ C7 where ==

def test_c7_one_launchd_watch_for_the_three_families_and_no_host_timer():
    sh = (ROOT / "scripts" / "setup_closing_watch.sh").read_text()
    assert "INTERVAL_S=60" in sh and "<string>closing-watch</string>" in sh and "--family" not in sh.split(
        "<array>")[1].split("</array>")[0]
    assert not (ROOT / "scripts" / "setup_mlb_closing_watch.sh").exists()
    units = " ".join(p.read_text() for p in (HOSTING / "systemd").glob("*"))
    assert "closing-run" not in units and "closing-watch" not in units and "-closing" not in units   # C7


# =============================================================================================== C8 policy ==

def test_c8_nothing_in_the_desk_moves():
    assert mc.CLOSING_HOLDS == ({"call": "PLAY", "exec_edge_under_pp": 4.0, "text": HOLD, "since": "2026-10-07"},)
    src = (HOSTING / "closing.py").read_text()
    assert "desk_policy" not in src.replace("desk_policy.is_quarantine_shadow", "")   # reads the export only
    for bad in ("trade-api", "/portfolio", "/orders", "kalshi.com", "create_order"):
        assert bad not in src.lower()
    d = {"call": "PASS", "shadow_units": 0.5, "tags": ["quarantine ≥ 15pp (shadow)"]}
    assert mc.is_quarantine_shadow(d) and dp.is_quarantine_shadow({"call": "PASS", "shadowUnits": 0.5,
                                                                    "tags": d["tags"]})


# ============================================================================================ C10 dry run ==

def test_c10_dry_run_prints_the_plan_and_touches_nothing(box, capsys):
    assert mc.watch(dry_run=True, now=NOW) == 0
    w = capsys.readouterr().out
    for fam in ("MLB", "NFL", "SOCCER"):
        assert mc.run(fam, dry_run=True, start=at(30 if fam == "MLB" else 35), now=NOW) == 0
    r = capsys.readouterr().out
    assert box.steps == box.notes == box.pages == box.pushes == [] and box.feed_calls == 0
    assert not c.receipts_path().exists() and not (box.tmp / "backups").exists() and not c.lock_path().exists()
    assert "would check the MLB feed" in w and f"closing-run --family NFL --start {at(35)}" in w
    assert "covers [301, 304, 302, 303]" in w and "→ DUE" in w
    assert "python cli.py sync-odds-football --match-ids 301,302,303,304" in r
    assert "python cli.py export-predictions --sport soccer --competition PL --status scheduled --desk" in r
    assert "10. python cli.py export-predictions --sport mlb --competition MLB --date 2026-10-11 --desk" in r


# ============================================================================================ 380.1 starters ==

def test_380_1_stale_starters_are_a_failed_attempt_retried_and_a_missing_starter_is_paged(box):
    """380.1: "where the export row lists a starter, the stored starter row for that side was refreshed at or after
    the run's start. A starter refreshed earlier fails the run as stale starters, naming the game, the side and both
    times; nothing is pushed, no call is paged, and the export is moved as R6 says. A side with no starter listed is
    not stale [...] On the page that game says so, on a line of its own under its call." A failed attempt, not a
    refusal."""
    box.stale_sides = {(102, "away")}
    assert mc.watch(now=NOW, families=("MLB",)) == 1
    r = runs()[-1]
    assert r["failed"] == "stale starters" and "refused" not in r and r["attempt"] == 1
    assert r["stale_starters"] == [{"match_id": 102, "game": "Clearwater Visitors @ Clearwater",
                                    "start_et": "2026-10-11 13:03 ET", "side": "away", "team": "Clearwater Visitors",
                                    "refreshed_at": "2026-10-11T13:25:00Z", "run_start": "2026-10-11T16:25:00Z"}]
    assert r["export_moved_to"].startswith("logs/") and box.pushes == [] and call_pages(box) == []
    # the operator's fix: that side not listed (the model shrinks); the retry succeeds and the page says so
    for p in box.docs["MLB"]["predictions"]:
        if p["match_id"] == 102:
            p["pitchers"]["away"] = None
    assert mc.watch(now=NOW + timedelta(minutes=1), families=("MLB",)) == 0
    lines = box.pages[-1]["body"].splitlines()
    i = next(n for n, x in enumerate(lines) if x.startswith("PLAY Clearwater"))
    assert lines[i + 1:i + 3] == ["Clearwater Visitors @ Clearwater (PLAY Clearwater 1u) · no starter listed for "
                                  "Clearwater Visitors", "  the model shrinks for it"]
    assert all(len(x) <= 100 for x in lines)
    assert runs()[-1]["attempt"] == 2


def test_380_1_the_column_is_refreshed_at_and_sync_pitchers_stamps_it():
    """Law 1: match_participants.refreshed_at exists, and sync_pitchers stamps it on the rows it updates and
    creates."""
    from src.db.schema import MatchParticipant
    assert "refreshed_at" in MatchParticipant.__table__.c and MatchParticipant.__tablename__ == "match_participants"
    import inspect

    from src.ingestion.service import IngestionService
    src = inspect.getsource(IngestionService.sync_pitchers)
    assert "existing.refreshed_at = now" in src and "refreshed_at=now," in src


# ======================================================================================= strict mode (22) ==

def test_strict_mode_injuries_exit_non_zero_on_a_failed_read_default_unchanged(monkeypatch):
    """Addendum 22: "Where they cannot [carry the time], the closing chain runs the step in a strict mode: the
    command exits non-zero when a read it needed failed, and the run fails at that step. The shared command's default
    behaviour does not change." """
    from click.testing import CliRunner

    import cli
    from src.db.database import init_db, session_scope
    from src.db.schema import Competition, CompetitionTeam, Sport, Team
    init_db()
    with session_scope() as s:
        if s.query(Competition).filter_by(code="STRX").one_or_none() is None:
            comp = Competition(sport=Sport.SOCCER, code="STRX", name="strict", area="X", type="LEAGUE")
            s.add(comp)
            s.flush()
            for i in range(2):
                t = Team(sport=Sport.SOCCER, name=f"STRX {i}", external_ids={"fake": str(i)})
                s.add(t)
                s.flush()
                s.add(CompetitionTeam(competition_id=comp.id, team_id=t.id, season="2093/94"))

    def boom(sid, season):
        if sid == "1":
            raise ConnectionError("provider down")
        return []
    ad = type("A", (), {"source_name": "fake", "list_injuries": lambda self, sid, season: boom(sid, season)})()
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda code: ad)
    ok = CliRunner().invoke(cli.cli, ["sync-injuries", "--competition", "STRX", "--season", "2093/94"])
    assert ok.exit_code == 0 and "STRICT" not in ok.output                       # default: unchanged
    bad = CliRunner().invoke(cli.cli, ["sync-injuries", "--competition", "STRX", "--season", "2093/94", "--strict"])
    assert bad.exit_code == 1 and "✗ STRICT: 1 injury read(s) failed (STRX)" in bad.output
    assert "fetch failed: ConnectionError" in bad.output


def test_strict_mode_fails_the_closing_run_at_that_step(box):
    box.fail_cmd["sync-injuries"] = (1, ["✗ STRICT: 1 injury read(s) failed (NFL):", "  ✗ team 7 (X): fetch failed"])
    assert mc.run("NFL", start=at(35), now=NOW) == 1
    r = runs()[-1]
    assert r["failed"] == "step 2 (strict: a read it needed failed)" and r["steps"][-1]["tail"][0].startswith("✗ STRICT")
    assert [s[0] for s in box.steps] == ["sync-matches", "sync-injuries"] and box.pages == []


# ============================================================================================= 380.2 setup ==

class _Ntfy(http.server.BaseHTTPRequestHandler):
    got: list = []

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        _Ntfy.got.append((self.path, self.headers.get("Title"), self.rfile.read(n).decode()))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *a):
        pass


@pytest.fixture
def ntfy():
    _Ntfy.got = []
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Ntfy)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    yield srv
    srv.shutdown()


def _setup_sandbox(tmp_path, env_text, shell_env=None):
    """A scratch checkout for the setup script: the script, the hosting modules it runs (closing.py preflight /
    test-page), a venv python that is this interpreter, fake launchctl/osascript recording their calls. Never the
    real checkout's .env."""
    repo, home, bindir = tmp_path / "repo", tmp_path / "home", tmp_path / "bin"
    (repo / "scripts").mkdir(parents=True)
    (repo / "venv" / "bin").mkdir(parents=True)
    shutil.copy2(ROOT / "scripts" / "setup_closing_watch.sh", repo / "scripts")
    shutil.copytree(HOSTING, repo / "deploy" / "hosting", ignore=shutil.ignore_patterns("__pycache__"))
    py = repo / "venv" / "bin" / "python"
    py.write_text(f"#!/bin/sh\nexec {sys.executable} \"$@\"\n")
    py.chmod(0o755)
    (repo / ".env").write_text(env_text)
    home.mkdir()
    bindir.mkdir()
    for tool in ("launchctl", "osascript"):
        (bindir / tool).write_text(f"#!/bin/sh\necho \"{tool} $*\" >> \"$HOME/calls\"\n")
        (bindir / tool).chmod(0o755)
    env = {"HOME": str(home), "PATH": f"{bindir}:/usr/bin:/bin", **(shell_env or {})}
    return repo, home, env


def _env_text(port, topic=True, mirror=True):
    return ((f"SP_EXPORTS_MIRROR_REMOTE=git@example.invalid:x/exports.git\n" if mirror else "")
            + (f"NTFY_CARD_TOPIC={TOPIC}\n" if topic else "") + f"NTFY_SERVER=http://127.0.0.1:{port}\n"
            + "SP_BACKUP_DIR=/tmp/sp-closing-test-backups\n")


def test_380_2_a_setting_only_in_the_installing_shell_refuses_the_install_naming_it(tmp_path, ntfy):
    repo, home, env = _setup_sandbox(tmp_path, _env_text(ntfy.server_port, topic=False),
                                     shell_env={"NTFY_CARD_TOPIC": TOPIC})
    r = subprocess.run(["bash", str(repo / "scripts" / "setup_closing_watch.sh")], capture_output=True, text=True,
                       env=env)
    assert r.returncode == 2
    assert "NTFY_CARD_TOPIC is set only in the installing shell" in r.stdout
    assert TOPIC not in r.stdout + r.stderr                                          # no value printed
    assert not (home / "Library" / "LaunchAgents" / "com.sportspredictor.closingwatch.plist").exists()
    assert not (home / "calls").exists() and _Ntfy.got == []                         # nothing loaded, no page


def test_380_2_the_run_refusals_run_in_the_launched_environment(tmp_path, ntfy):
    """A setting the shell does NOT have and the files do not have: the run's own refusal (M1) refuses the install;
    so does a backup folder under data/ (R5), read from .env as the job would."""
    repo, home, env = _setup_sandbox(tmp_path, _env_text(ntfy.server_port, mirror=False))
    r = subprocess.run(["bash", str(repo / "scripts" / "setup_closing_watch.sh")], capture_output=True, text=True,
                       env=env)
    assert r.returncode == 2 and "REFUSED: SP_EXPORTS_MIRROR_REMOTE is not set" in r.stdout
    (repo / ".env").write_text(_env_text(ntfy.server_port) + f"SP_BACKUP_DIR={repo}/data/bk\n")
    r = subprocess.run(["bash", str(repo / "scripts" / "setup_closing_watch.sh")], capture_output=True, text=True,
                       env=env)
    assert r.returncode == 2 and "backup folder under data/" in r.stdout and not (repo / "data").exists()


def test_380_2_install_sends_one_test_page_and_writes_no_value_into_the_plist(tmp_path, ntfy):
    repo, home, env = _setup_sandbox(tmp_path, _env_text(ntfy.server_port))
    r = subprocess.run(["bash", str(repo / "scripts" / "setup_closing_watch.sh")], capture_output=True, text=True,
                       env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert _Ntfy.got == [(f"/{TOPIC}", "Closing watch", mc.TEST_PAGE_BODY)]           # one page, the card topic
    plist = (home / "Library" / "LaunchAgents" / "com.sportspredictor.closingwatch.plist").read_text()
    assert TOPIC not in plist and "example.invalid" not in plist and "EnvironmentVariables" not in plist
    assert "<integer>60</integer>" in plist and "<string>closing-watch</string>" in plist
    assert TOPIC not in r.stdout + r.stderr
    assert "Test page (phone): accepted by ntfy." in r.stdout
    assert 'you should have seen a page titled\n  "Closing watch"' in r.stdout.replace("  \"Closing", "  \"Closing")
    calls = (home / "calls").read_text().splitlines()
    assert any(x.startswith("launchctl load ") for x in calls) and calls[-1].startswith("osascript")
    assert "The laptop awake" in r.stdout and "VPN on, Tailscale off" in r.stdout


def test_380_2_uninstall_removes_both_watches(tmp_path):
    repo, home, env = _setup_sandbox(tmp_path, "")
    la = home / "Library" / "LaunchAgents"
    la.mkdir(parents=True)
    for lb in ("closingwatch", "mlbclosingwatch"):
        (la / f"com.sportspredictor.{lb}.plist").write_text("x")
    r = subprocess.run(["bash", str(repo / "scripts" / "setup_closing_watch.sh"), "--uninstall"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0 and list(la.iterdir()) == [] and "uninstalled" in r.stdout
    hits = subprocess.run(["git", "-C", str(ROOT), "grep", "-l", "setup_closing_watch"],
                          capture_output=True, text=True).stdout.split()
    assert all(h.endswith(".md") or h in ("scripts/setup_closing_watch.sh", "tests/test_closing_runs.py",
                                          "cli.py") for h in hits), hits          # nothing installs itself


# ============================================================================================ 380.3 backup ==

def test_380_3_a_backup_is_a_backup_only_when_every_part_succeeded(box, monkeypatch):
    """380.3: "Any error fails the run as a backup failure, before the first step. A finished copy it left is
    renamed aside, never deleted, so that no later run counts it as today's backup." """
    real = c.sha256_file
    monkeypatch.setattr(c, "sha256_file", lambda p: (_ for _ in ()).throw(OSError("hash read failed")))
    assert mc.run("NFL", start=at(35), now=NOW) == 1
    r = runs()[-1]
    b = r["backup"]
    assert r["failed"] == "backup" and box.steps == [] and b["copied"] and b["opens"] and not b["ok"]
    folder = box.tmp / "backups"
    aside = [p.name for p in folder.iterdir()]
    assert aside == [f"sports_{DAY}.db.failed-" + b["set_aside"][0].rsplit("-", 1)[1]] and Path(b["set_aside"][0]).exists()
    assert mc.todays_backup(folder, NOW.date()) is None                              # not counted
    monkeypatch.setattr(c, "sha256_file", real)
    assert mc.run("NFL", start=at(35), now=NOW + timedelta(minutes=1)) == 0         # the next run takes its own
    assert runs()[-1]["backup"]["ok"] and (folder / f"sports_{DAY}.db.sha256").is_file()
    # the hash file failing is a failure too
    monkeypatch.setattr(Path, "write_text", lambda self, t, *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    rec = mc.take_backup(box.tmp / "b2", NOW.date())
    assert rec["ok"] is False and rec["sha256"] and rec["hash_file"] is None and rec["set_aside"]


# ============================================================================================== 380.4 lock ==

def _lock_then(fn):
    real = mc.acquire_lock

    @contextlib.contextmanager
    def lk(timeout):
        fn()
        with real(timeout):
            yield
    return lk


def test_380_4_superseded_under_the_lock_is_neither_an_attempt_nor_a_refusal(box, monkeypatch):
    def other_run_succeeded():
        c.append_receipt({"kind": "closing", "family": "NFL", "start": at(35), "exit": 0, "covers": []})
    monkeypatch.setattr(mc, "acquire_lock", _lock_then(other_run_succeeded))
    assert mc.run("NFL", start=at(35), trigger="watch", now=NOW) == 0
    r = runs()[-1]
    assert r["superseded"] is True and "refused" not in r and "attempt" not in r
    assert box.steps == box.pages == box.notes == box.pushes == []                  # no step, no push, no page
    assert mc.closing_state("NFL", at(35)) == {"success": True, "attempts": 1, "misses": 0}


def test_380_4_a_watch_run_that_gets_the_lock_inside_t5_is_a_miss(box, monkeypatch):
    clock = fake_clock(monkeypatch)
    monkeypatch.setattr(mc, "acquire_lock", _lock_then(lambda: clock.__setitem__("t", clock["t"] + 31 * 60)))
    assert mc.run("NFL", start=at(35), trigger="watch", now=NOW) == 1
    m = receipts()[-1]
    assert m["kind"] == "closing_miss" and m["reason"] == "the lock came inside T-5" and box.steps == []
    assert box.notes == [f"Closing NFL 2026-10-11 13:00 ET: MISSED: the lock came inside T-5"]
    assert runs() == []                                                              # not an attempt
    with hold_lock():                                                                # held until T-5: a miss too
        assert mc.run("NFL", start=at(35), trigger="watch", now=NOW + timedelta(minutes=30)) == 1
    assert receipts()[-1]["reason"] == "the lock was held until inside T-5"


def test_380_4_attempt_number_and_run_start_are_taken_under_the_lock(box, monkeypatch):
    """Two attempts land while this run waits: it is attempt 3. Its start is the moment it holds the lock, so a price
    another chain captured while it waited is stale."""
    clock = fake_clock(monkeypatch)

    def wait():
        for _ in range(2):
            c.append_receipt({"kind": "closing", "family": "NFL", "start": at(35), "exit": 1, "covers": []})
        con = sqlite3.connect(box.db)
        write_prices(con, NOW + timedelta(seconds=60), comp_id=2)                   # captured during the wait
        con.close()
        clock["t"] += 120
    monkeypatch.setattr(mc, "acquire_lock", _lock_then(wait))
    box.no_fresh = {"sync-odds-football", "sync-kalshi-nfl"}
    assert mc.run("NFL", start=at(35), trigger="watch", now=NOW) == 1
    r = runs()[-1]
    assert r["attempt"] == 3 and r["run_start"] == "2026-10-11T16:27:00Z" and r["queued_at"] == "2026-10-11T16:25:00Z"
    assert r["failed"] == "stale prices" and r["stale"][0]["captured_at"] == "2026-10-11T16:26:00Z"
    assert box.notes[-1].endswith("attempt 3/3 · no further attempt will run for this kickoff")


# ============================================================================================ reading 7 ==

def test_reading_7_a_refusal_is_receipted_and_notified_once_per_start_and_reason(box, monkeypatch):
    monkeypatch.delenv("SP_EXPORTS_MIRROR_REMOTE")
    for m in range(3):
        assert mc.watch(now=NOW + timedelta(minutes=m), families=("NFL",)) == 2
    ref = [r for r in runs() if r.get("refused")]
    assert len(ref) == 1 and len(box.notes) == 1 and box.notes[0].startswith("Closing NFL 2026-10-11 13:00 ET: REFUSED")
    monkeypatch.setenv("NTFY_CARD_TOPIC", "")                                        # another reason: once more
    monkeypatch.setenv("SP_EXPORTS_MIRROR_REMOTE", "git@example.invalid:x.git")
    mc.watch(now=NOW + timedelta(minutes=3), families=("NFL",))
    assert len([r for r in runs() if r.get("refused")]) == 2
    assert mc.run("NFL", start=at(35), now=NOW) == 2                                 # a manual run: receipted each time
    assert len([r for r in runs() if r.get("refused")]) == 3


# ========================================================================================= #370 as built ==

def test_sp_run_refuses_every_closing_chain(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "HOST_ENV", tmp_path / "no-host.env")
    monkeypatch.setenv("SP_RECEIPTS", str(tmp_path / "r.jsonl"))
    for k in ("NTFY_TOPIC", "NTFY_CARD_TOPIC"):
        monkeypatch.delenv(k, raising=False)
    assert sp_run.main(["mlb-closing"]) == 2
    assert sp_run.main(["nfl-closing"]) == 2 and sp_run.main(["soccer-closing", "--dry-run"]) == 2
    got = [json.loads(x)["refused"] for x in (tmp_path / "r.jsonl").read_text().splitlines()]
    assert got == ["laptop_only", "closing_only"]


def test_feed_is_the_mlb_adapters_base_url():
    from src.adapters import mlb_stats_api
    assert mc.FEED_BASE == mlb_stats_api._BASE_URL


def test_a6_feed_unreachable_runs_nothing_for_mlb_only(box):
    box.feed = (False, "URLError")
    assert mc.watch(now=NOW) == 0
    assert [r["family"] for r in runs()] == ["NFL", "SOCCER"]                       # NFL / PL need no feed
    miss = [r for r in receipts() if r["kind"] == "closing_miss"]
    assert [(m["family"], m["reason"]) for m in miss] == [("MLB", "feed unreachable")]
    assert mc.FEED_MISS_TEXT in box.notes


def test_a2_receipt_on_success_and_steps_under_the_lock(box):
    assert mc.run("MLB", start=at(30), now=NOW) == 0
    assert box.lock_seen == [False] * 10
    r = runs()[-1]
    assert r["exit"] == 0 and r["date_ny"] == DAY and r["export"] == f"exports/mlb_MLB_{DAY}.json"
    assert [s["exit"] for s in r["steps"]] == [0] * 10 and r["push"]["exit"] == 0
    assert box.steps[-1] == ["export-predictions", "--sport", "mlb", "--competition", "MLB", "--date", DAY, "--desk"]


def test_a3_backup_taken_through_the_backup_api_and_found_the_second_time(box, monkeypatch):
    for fn in ("copy", "copy2", "copyfile", "copytree"):
        monkeypatch.setattr(shutil, fn, lambda *a, **k: (_ for _ in ()).throw(AssertionError("copied")))
    assert mc.run("MLB", start=at(30), now=NOW) == 0
    b = runs()[-1]["backup"]
    assert b["ok"] and b["integrity"] == "ok" and Path(b["file"]).name == f"sports_{DAY}.db"
    assert mc.run("NFL", start=at(35), now=NOW) == 0
    assert runs()[-1]["backup"] == {"file": b["file"], "taken": False}


def test_a4_manual_run_refuses_with_nothing_to_close(box, monkeypatch):
    db = box.tmp / "started.db"
    make_db(db, [(1, "NFL", -20, "LIVE", "A"), (2, "NFL", -1, "SCHEDULED", "B")])
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    assert mc.run("NFL", now=NOW) == 2 and runs()[-1]["refused"].startswith("A4: every game in the window has started")
    assert mc.run("SOCCER", now=NOW) == 2 and "no SOCCER game starting within 90 minutes" in runs()[-1]["refused"]


def test_a1_ny_date_not_utc(box, monkeypatch):
    now = datetime(2026, 10, 9, 2, 30, tzinfo=timezone.utc)                         # 22:30 ET on 10-08
    db = box.tmp / "late.db"
    make_db(db, [(7, "MLB", 40, "SCHEDULED", "Giants")], now=now)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    box.docs["MLB"] = dp.annotate({"sport": "mlb", "predictions": [row(7, "Giants", 0.52, fair_h=0.51, minutes=40,
                                                                       now=now)]}, now=now)
    assert mc.resolve_steps("MLB", now + timedelta(minutes=40), [], now)[0][-1] == "2026-10-08"
    assert mc.run("MLB", now=now) == 0 and runs()[-1]["export"] == "exports/mlb_MLB_2026-10-08.json"


def test_laptop_only_refusal_for_mlb_and_the_watch_skips_it(box, monkeypatch):
    monkeypatch.setenv("SP_SKIP_FAMILIES", "MLB")
    assert mc.run("MLB", start=at(30), now=NOW) == 2 and runs()[-1]["refused"].startswith("laptop only")
    assert mc.watch(now=NOW) == 0 and box.feed_calls == 0
    assert [r["family"] for r in runs() if not r.get("refused")] == ["NFL", "SOCCER"]


@pytest.mark.parametrize("said", ["✗ Kalshi sync failed: Max retries exceeded", "Kalshi sync: market fetch failed"])
def test_p1c_the_sync_kalshi_marker_table_stays_as_built(box, said):
    box.tails["sync-kalshi"] = ["Checking Kalshi status…", said]
    assert mc.run("MLB", start=at(30), now=NOW) == 1
    assert runs()[-1]["failed"] == "step 6 (reported failure, exit 0)"
    assert mc.STEP_FAILURE_MARKERS == {"sync-kalshi": ("✗ Kalshi sync failed:", "Kalshi sync: ")}


def test_p1d_a_screen_notification_not_posted_on_macos_fails_and_off_macos_does_not(box, monkeypatch):
    monkeypatch.setattr(mc, "notify", lambda body, title="": {"posted": False, "error": "osascript exit 1"})
    assert mc.run("NFL", start=at(35), now=NOW) == 1 and runs()[-1]["failed"] == "notify"
    monkeypatch.setattr(mc, "notify", lambda body, title="": {"posted": False, "skipped": "not macOS"})
    assert mc.run("NFL", start=at(35), now=NOW + timedelta(minutes=1)) == 0


def test_notify_on_macos_uses_osascript_quoted(monkeypatch):
    seen = []
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(mc.subprocess, "run", lambda argv, **k: seen.append(argv) or
                        subprocess.CompletedProcess(argv, 0, "", ""))
    assert REAL_NOTIFY('a "b"', title="NFL closing")["posted"] is True
    assert seen == [["osascript", "-e", 'display notification "a \\"b\\"" with title "NFL closing"']]


def test_r1_a_target_that_starts_during_the_run_fails_and_is_never_retried(box, monkeypatch):
    slow_steps(box, monkeypatch, 60 * 6)                                             # 7 steps x 6 min
    assert mc.watch(now=NOW, families=("NFL",)) == 1
    r = runs()[-1]
    assert r["failed"] == "target started" and r["started"].startswith("start ")
    mc.watch(now=NOW + timedelta(minutes=36), families=("NFL",))
    assert len([x for x in runs("NFL") if x["start"] == at(35)]) == 1               # never retried


def test_r4_r5_m1_refusals_in_order(box, monkeypatch):
    assert mc.run("NFL", start="tonight", now=NOW) == 2 and runs()[-1]["refused"].startswith("malformed --start")
    monkeypatch.setenv("SP_BACKUP_DIR", str(c.REPO / "data" / "bk"))
    monkeypatch.delenv("SP_EXPORTS_MIRROR_REMOTE")
    assert mc.run("NFL", start=at(35), now=NOW) == 2
    assert runs()[-1]["refused"].startswith("backup folder under data/") and not (c.REPO / "data").exists()
    monkeypatch.setenv("SP_BACKUP_DIR", str(box.tmp / "backups"))
    assert mc.run("NFL", start=at(35), now=NOW) == 2 and "SP_EXPORTS_MIRROR_REMOTE" in runs()[-1]["refused"]


FAKE_CLI = '''import os, sqlite3, sys
a = sys.argv[1:]
print("ran", " ".join(a))
T = os.environ["T_CAPTURE"]
con = sqlite3.connect(os.environ["DATABASE_URL"][len("sqlite:///"):])
if a[0] in ("sync-odds-football", "sync-kalshi-nfl"):
    for (mid,) in con.execute("SELECT id FROM matches WHERE competition_id = 2").fetchall():
        for sel in ("HOME", "AWAY"):
            if a[0] == "sync-odds-football":
                con.execute("INSERT INTO odds(match_id, bookmaker, market, selection, price_decimal, captured_at, "
                            "source) VALUES (?, 'bk1', '1X2', ?, 1.9, ?, 'b')", (mid, sel, T))
            else:
                con.execute("INSERT INTO odds_snapshots(match_id, market, selection, devig_prob, captured_at, source) "
                            "VALUES (?, 'ML', ?, 0.5, ?, 'kalshi')", (mid, sel, T))
    con.commit()
if a[0] == "export-nfl-predictions":
    open(os.environ["T_OUT"], "w").write(open(os.environ["T_DOC"]).read())
if a[0] == os.environ.get("T_FAIL"):
    sys.exit(4)
'''


def test_real_step_runner_against_a_fake_cli(box, monkeypatch):
    """The real sp_run.run_step path against a FAKE cli.py in a tmp checkout: never the real one, never a real DB."""
    monkeypatch.setattr(mc, "run_step", sp_run.run_step)
    (c.REPO / "cli.py").write_text(FAKE_CLI)
    doc = box.tmp / "doc.json"
    doc.write_text(json.dumps(box.docs["NFL"]))
    monkeypatch.setenv("T_DOC", str(doc))
    monkeypatch.setenv("T_OUT", str(c.REPO / "exports" / f"nfl_predictions_{DAY}.json"))
    monkeypatch.setenv("T_CAPTURE", "2026-10-11 16:25:30.000000")
    assert mc.run("NFL", start=at(35), now=NOW) == 0
    assert [s["exit"] for s in runs()[-1]["steps"]] == [0] * 6
    monkeypatch.setenv("T_FAIL", "predict-nfl")
    assert mc.run("NFL", start=at(35), now=NOW) == 1
    assert [s["exit"] for s in runs()[-1]["steps"]] == [0] * 4 + [4]


# ================================================================================= Codex round 1 on #385 ==

def set_start(db, mid, minutes):
    con = sqlite3.connect(db)
    con.execute("UPDATE matches SET utc_date = ? WHERE id = ?", (_ts(NOW + timedelta(minutes=minutes)), mid))
    con.commit()
    con.close()


def move_on_first_schedule_read(box, monkeypatch, moves):
    """The run's opening schedule read (sync-matches) moves covered games to new kickoffs, leaving them SCHEDULED,
    the first time only. `moves`: {match_id: new minutes from NOW}."""
    done = []

    def mv(argv):
        if argv[0] == "sync-matches" and not done:
            done.append(1)
            for mid, m in moves.items():
                set_start(box.db, mid, m)
    slow_steps(box, monkeypatch, 0, mv)


def doc_start(box, fam, mid, minutes):
    for p in box.docs[fam]["predictions"]:
        if p["match_id"] == mid:
            p["utc_date"] = (NOW + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S")


def test_385_p1_every_covered_game_moved_fails_as_target_moved_and_the_new_start_runs(box, monkeypatch):
    """Codex P1 (closing.py target_started): the schedule read moves every covered game off the target start, still
    SCHEDULED. The run fails as "target moved" (an own check: export moved out, no push, no call page), naming each
    game with both times; the old start leaves no group, and the new start is its own key and closes at its T-35."""
    move_on_first_schedule_read(box, monkeypatch, {401: 95, 402: 97})
    assert mc.watch(now=NOW, families=("SOCCER",)) == 1
    r = runs("SOCCER")[-1]
    assert r["failed"] == "target moved" and r["start"] == at(35)
    assert [(m["match_id"], m["target"], m["covered_start"], m["stored_start"]) for m in r["moved"]] == [
        (401, at(35), at(35), at(95)), (402, at(35), at(37), at(97))]
    assert r["export_moved_to"].startswith(f"logs/{r['run_id']}.")
    assert box.pushes == [] and call_pages(box) == []
    assert box.notes[-1] == "Closing SOCCER 2026-10-11 13:00 ET: FAILED: target moved · attempt 1/3"
    mc.watch(now=NOW + timedelta(minutes=1), families=("SOCCER",))
    assert len(runs("SOCCER")) == 1                                    # nothing left at the old start: no retry
    doc_start(box, "SOCCER", 401, 95)
    doc_start(box, "SOCCER", 402, 97)
    assert mc.watch(now=NOW + timedelta(minutes=60), families=("SOCCER",)) == 0
    r2 = runs("SOCCER")[-1]
    assert r2["start"] == at(95) and r2["attempt"] == 1 and r2["exit"] == 0
    assert [x["match_id"] for x in r2["covers"]] == [401, 402] and len(call_pages(box)) == 1


def test_385_p1_one_covered_game_moved_fails_the_run_and_is_not_counted_closed_at_the_old_start(box, monkeypatch):
    """Reading (conservative): a partial move fails the run, naming the moved game only. The retry at the old start
    covers the games still there and succeeds; the moved game is not finished with by the old start's success
    (covered_ids), so its new start closes at its own T-35."""
    move_on_first_schedule_read(box, monkeypatch, {304: 95})
    assert mc.watch(now=NOW, families=("NFL",)) == 1
    r = runs("NFL")[-1]
    assert r["failed"] == "target moved" and [m["match_id"] for m in r["moved"]] == [304]
    assert r["moved"][0]["covered_start"] == at(36) and r["moved"][0]["stored_start"] == at(95)
    assert call_pages(box) == []
    assert mc.watch(now=NOW + timedelta(minutes=1), families=("NFL",)) == 0     # attempt 2, old start, 3 games
    r = runs("NFL")[-1]
    assert r["start"] == at(35) and r["attempt"] == 2 and r["exit"] == 0
    assert [x["match_id"] for x in r["covers"]] == [301, 302, 303]
    assert 304 not in mc.covered_ids("NFL")
    doc_start(box, "NFL", 304, 95)
    assert mc.watch(now=NOW + timedelta(minutes=60), families=("NFL",)) == 0
    r = runs("NFL")[-1]
    assert r["start"] == at(95) and r["exit"] == 0 and [x["match_id"] for x in r["covers"]] == [304]


def test_385_p1_watch_reads_the_clock_for_each_queued_run(box, monkeypatch):
    """Codex P1 (closing.py watch): NFL and SOCCER are due in one production tick (no `now`); NFL's closing takes 31
    minutes. SOCCER's run reads the clock when it starts: it is inside T-5, a miss, never a run on the tick's time."""
    off = {"d": timedelta(0)}
    monkeypatch.setattr(mc, "clock", lambda: NOW + off["d"])

    def slow_nfl(argv):
        if argv[0] == "export-nfl-predictions":
            off["d"] = timedelta(minutes=31)
    slow_steps(box, monkeypatch, 0, slow_nfl)
    assert mc.watch(families=("NFL", "SOCCER")) == 1
    assert [(r["family"], r["exit"]) for r in runs()] == [("NFL", 0)]
    miss = [r for r in receipts() if r["kind"] == "closing_miss"]
    assert [(m["family"], m["start"], m["reason"]) for m in miss] == [("SOCCER", at(35), "the lock came inside T-5")]
    assert len(call_pages(box)) == 1


def test_385_p2_parse_utc_reads_any_explicit_offset():
    """Codex P2 (closing.py parse_utc): '-04:00' was truncated and 13:00 read as UTC."""
    want = datetime(2026, 10, 11, 17, 0, tzinfo=timezone.utc)
    assert mc.parse_utc("2026-10-11T13:00:00-04:00") == want
    assert mc.parse_utc("2026-10-11T13:00:00-0400") == want
    assert mc.parse_utc("2026-10-11T19:00:00+02:00") == want
    assert mc.parse_utc("2026-10-11T17:00:00Z") == want
    assert mc.parse_utc("2026-10-11T17:00:00+00:00") == want
    assert mc.parse_utc("2026-10-11T17:00:00") == want                              # naive = UTC
    assert mc.parse_utc("2026-10-11 17:00:00.000000") == want                       # the stored format
    assert mc.parse_utc("2026-10-11 17:00:00.123456") == want                       # as before: to the second
    assert mc.iso_z(mc.parse_utc("2026-10-11T13:00:00-04:00")) == "2026-10-11T17:00:00Z"


def test_385_p2_strict_injuries_fail_on_a_missing_competition_inside_the_window(monkeypatch):
    """Codex P2 (cli.py sync-injuries): with --kickoff-within-hours, a competition not in the DB returned at the
    empty-window branch, exit 0, under --strict. Now a failed read; the default and an empty window are unchanged."""
    from click.testing import CliRunner

    import cli
    from src.db.database import init_db, session_scope
    from src.db.schema import Competition, Sport
    init_db()
    with session_scope() as s:
        if s.query(Competition).filter_by(code="STRY").one_or_none() is None:
            s.add(Competition(sport=Sport.SOCCER, code="STRY", name="strict empty", area="X", type="LEAGUE"))
    ad = type("A", (), {"source_name": "fake", "list_injuries": lambda self, sid, season: []})()
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda code: ad)
    args = ["sync-injuries", "--season", "2093/94", "--kickoff-within-hours", "1"]
    bad = CliRunner().invoke(cli.cli, [*args, "--competition", "NOPEX", "--strict"])
    assert bad.exit_code == 1 and "✗ STRICT: 1 injury read(s) failed (NOPEX):" in bad.output
    assert "✗ competition NOPEX not in DB" in bad.output
    ok = CliRunner().invoke(cli.cli, [*args, "--competition", "NOPEX"])
    assert ok.exit_code == 0 and "STRICT" not in ok.output                          # default: unchanged
    empty = CliRunner().invoke(cli.cli, [*args, "--competition", "STRY", "--strict"])
    assert empty.exit_code == 0 and "nothing inside the window" in empty.output     # no games: not a failed read
