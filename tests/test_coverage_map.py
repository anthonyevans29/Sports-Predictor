"""THE DAY'S COVERAGE (ARCHITECT 2026-10-17 09:30 ET, addendum 107 item C7): `python cli.py coverage [--date]`.
"Tests on the throwaway DB: a day with rows, a day with a gap, a market-only sport." Against a SCRATCH schedule under
tmp_path (the tables the command reads, src/db/schema.py names; one test on the real schema), with a scratch roadmap
and registry where the status rule is under test, and a scratch receipts file for the watch's. The clock is fixed; the
no-write test blocks the network."""
import hashlib
import inspect
import json
import re
import socket
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))

import closing as cl  # noqa: E402
import coverage_map as cm  # noqa: E402
import sp_common as c  # noqa: E402

from src import roadmap as rm  # noqa: E402
from src.walters import registry as reg  # noqa: E402

NOW = datetime(2026, 10, 17, 12, 10, tzinfo=timezone.utc)          # Saturday 08:10 ET
DAY = "2026-10-17"
COMPS = {"MLB": 1, "NFL": 2, "PL": 3, "NHL": 4, "UNL": 5, "NCAA": 6, "SA": 7, "CL": 8, "EL1": 9}


def _ts(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S.000000")


def utc(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def make_db(path: Path, games, preds=(), wal: bool = False) -> None:
    """games: (match_id, competition, UTC start 'YYYY-MM-DD HH:MM', status); preds: (match_id, model, UTC computed).
    wal: the file in WAL mode, as src/db/database.py leaves the real DB (the mode persists in the file)."""
    con = sqlite3.connect(path)
    if wal:
        con.execute("PRAGMA journal_mode=WAL")
    con.executescript(
        "CREATE TABLE competitions(id INTEGER PRIMARY KEY, code TEXT);"
        "CREATE TABLE teams(id INTEGER PRIMARY KEY, name TEXT);"
        "CREATE TABLE matches(id INTEGER PRIMARY KEY, competition_id INT, utc_date DATETIME, status TEXT,"
        " home_team_id INT, away_team_id INT);"
        "CREATE TABLE predictions(id INTEGER PRIMARY KEY, match_id INT, model_version TEXT, computed_at DATETIME);"
        "INSERT INTO teams VALUES (1, 'Home'), (2, 'Away');")
    con.executemany("INSERT INTO competitions VALUES (?, ?)", [(i, code) for code, i in COMPS.items()])
    for mid, comp, start, status in games:
        con.execute("INSERT INTO matches VALUES (?, ?, ?, ?, 1, 2)", (mid, COMPS[comp], _ts(utc(start)), status))
    for mid, mv, at in preds:
        con.execute("INSERT INTO predictions(match_id, model_version, computed_at) VALUES (?, ?, ?)",
                    (mid, mv, _ts(utc(at))))
    con.commit()
    con.close()


def lane(lid, state, registry_id=None):
    done = state in ("live", "closed")
    return {"lane": lid, "title": lid.upper(), "issue": 1, "registry_id": registry_id, "state": state,
            "steps": [{"what": "a step", "owner": "architect", "due": "2026-11-01",
                       "done": {"date": "2026-10-01", "receipt": "r"} if done else None}],
            "earliest_live": None, "live_needs": "a need", "vs_close": "not read", "moved": []}


LANES = [lane("nhl", "to declare"), lane("unl", "confirming", "intl-x"), lane("ncaa", "declared", "ncaa-x"),
         lane("cl", "confirming", "cl-x"), lane("el1", "declared", "ghost"), lane("leagues", "to declare")]
ENTRIES = [{"id": "intl-x", "status": "confirming"}, {"id": "ncaa-x", "status": "declared"},
           {"id": "cl-x", "status": "closed"}]


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A scratch DB, a scratch roadmap and registry, a scratch receipts file (none yet), no machine settings, and the
    fixed clock."""
    db = tmp_path / "scratch.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.setenv("SP_RECEIPTS", str(tmp_path / "receipts.jsonl"))
    monkeypatch.setattr(c, "HOST_ENV", tmp_path / "no-host.env")
    monkeypatch.setattr(c, "_DOTENV_CACHE", {})
    monkeypatch.delenv("SP_SKIP_FAMILIES", raising=False)
    road = tmp_path / "roadmap.json"
    road.write_text(json.dumps({"lanes": LANES}))
    assert rm.validate(json.loads(road.read_text())) == []          # the scratch file is a valid roadmap
    ledger = tmp_path / "experiments.json"
    ledger.write_text(json.dumps(ENTRIES))
    monkeypatch.setattr(rm, "ROADMAP_PATH", road)
    monkeypatch.setattr(reg, "LEDGER", str(ledger))
    monkeypatch.setattr(cl, "clock", lambda: NOW)
    return db


def run(*args):
    from cli import cli
    r = CliRunner().invoke(cli, ["coverage", *args])
    return r.exit_code, r.output.splitlines()


def line_of(out, code):
    got = [x for x in out if x.startswith(f"{code} · ")]
    assert len(got) == 1, out
    return got[0]


def gaps(out):
    return out[out.index("GAPS:") + 1:] if "GAPS:" in out else []


# ------------------------------------------------------------------------------------- the spec's three --

def test_a_day_with_rows(env):
    make_db(env, [(50548, "MLB", "2026-10-18 00:00", "SCHEDULED"), (50549, "MLB", "2026-10-17 20:05", "SCHEDULED")],
            [(50548, "mlb_v2", "2026-10-17 11:02"), (50549, "mlb_v2", "2026-10-17 11:30")])
    rc, out = run("--date", DAY)
    assert rc == 0
    assert out[0].startswith(f"COVERAGE {DAY} ET · 1 competition · 2 games · now 2026-10-17 08:10 ET")
    mlb = line_of(out, "MLB")
    assert "· 2 games ·" in mlb
    assert "· LIVE (closing family MLB) ·" in mlb
    assert "· rows: mlb_v2 2 (computed 2026-10-17 07:02 ET to 2026-10-17 07:30 ET) ·" in mlb    # computed_at in ET
    assert "· without rows: none ·" in mlb
    assert out[-1] == "GAPS: none"


def test_an_old_row_is_never_hidden_behind_a_fresh_one(env):
    """(model, computed_at): three rows computed this morning and one a week old print as a range, and the map holds
    each game's own computed_at. A stale row is no gap (the spec's gap is a game with no row)."""
    make_db(env, [(401, "PL", "2026-10-17 14:00", "SCHEDULED"), (402, "PL", "2026-10-17 14:00", "SCHEDULED"),
                  (403, "PL", "2026-10-17 16:30", "SCHEDULED"), (404, "PL", "2026-10-17 16:30", "SCHEDULED")],
            [(401, "v22", "2026-10-17 11:00"), (402, "v22", "2026-10-17 11:00"), (403, "v22", "2026-10-17 11:00"),
             (404, "v22", "2026-10-10 11:00")])
    rc, out = run("--date", DAY)
    assert rc == 0
    assert ("· rows: v22 4 (computed 2026-10-10 07:00 ET to 2026-10-17 07:00 ET) · without rows: none ·"
            in line_of(out, "PL"))
    assert out[-1] == "GAPS: none"
    m = cm.coverage(datetime(2026, 10, 17).date(), NOW)["competitions"][0]["rows"][0]
    assert (m["earliest"], m["latest"]) == (utc("2026-10-10 11:00"), utc("2026-10-17 11:00"))
    assert m["computed"] == {401: utc("2026-10-17 11:00"), 402: utc("2026-10-17 11:00"), 403: utc("2026-10-17 11:00"),
                             404: utc("2026-10-10 11:00")}


def test_a_day_with_a_gap(env):
    make_db(env, [(401, "PL", "2026-10-17 11:30", "SCHEDULED"), (402, "PL", "2026-10-17 14:00", "SCHEDULED"),
                  (403, "PL", "2026-10-17 14:00", "SCHEDULED"), (404, "PL", "2026-10-17 16:30", "SCHEDULED"),
                  (405, "PL", "2026-10-17 16:30", "POSTPONED"),            # void: not a game of the day
                  (50548, "MLB", "2026-10-18 00:00", "SCHEDULED"), (50549, "MLB", "2026-10-17 20:05", "SCHEDULED"),
                  (301, "NFL", "2026-10-17 17:00", "SCHEDULED")],
            [(50548, "mlb_v2", "2026-10-17 11:02")])
    rc, out = run("--date", DAY)
    assert rc == 0
    pl = line_of(out, "PL")
    assert "· 4 games (+1 void, not counted: 405 POSTPONED) ·" in pl
    assert "· rows: none · without rows: 401, 402, 403, 404 ·" in pl
    assert gaps(out) == [
        "MLB: 2 GAMES, 1 PREDICTION ROW, NONE FOR 50549",                   # partial: the games named, no hint
        "NFL: 1 GAME, 0 PREDICTION ROWS — nfl-predict has not run",
        "PL: 4 GAMES, 0 PREDICTION ROWS — soccer-prematch has not run",     # the spec's example, word for word
    ]


def test_a_market_only_sport(env):
    """MARKET-ONLY from the roadmap (the nhl lane, to declare) and from the roadmap with the registry (the ncaa lane and
    its entry, both declared): no prediction rows expected, so no gap is claimed for either."""
    make_db(env, [(501, "NHL", "2026-10-17 23:00", "SCHEDULED"), (502, "NHL", "2026-10-17 23:30", "SCHEDULED"),
                  (601, "NCAA", "2026-10-17 16:00", "SCHEDULED")])
    rc, out = run("--date", DAY)
    assert rc == 0
    nhl = line_of(out, "NHL")
    assert "· MARKET-ONLY (roadmap lane nhl: to declare) ·" in nhl
    assert "· rows: none (none expected: MARKET-ONLY) ·" in nhl
    assert "without rows" not in nhl
    assert nhl.endswith("· closing: none (no closing family covers NHL)")
    assert "· MARKET-ONLY (roadmap lane ncaa: declared; registry ncaa-x: declared) ·" in line_of(out, "NCAA")
    assert out[-1] == "GAPS: none"


# ----------------------------------------------------------------------------------------- the status rule --

def test_shadow_and_the_unknowns(env):
    make_db(env, [(701, "UNL", "2026-10-17 18:45", "SCHEDULED"), (702, "SA", "2026-10-17 13:00", "SCHEDULED"),
                  (703, "CL", "2026-10-17 19:00", "SCHEDULED"), (704, "EL1", "2026-10-17 14:00", "SCHEDULED")])
    rc, out = run("--date", DAY)
    assert rc == 0
    unl = line_of(out, "UNL")
    assert "· SHADOW (roadmap lane unl: confirming; registry intl-x: confirming) ·" in unl
    assert "· rows: none (none expected: SHADOW) ·" in unl
    assert "· UNKNOWN (no closing family covers SA and no roadmap lane is named sa) ·" in line_of(out, "SA")
    assert ("· UNKNOWN (roadmap lane cl: confirming; registry cl-x: closed (the lane and the registry disagree)) ·"
            in line_of(out, "CL"))
    assert "· UNKNOWN (roadmap lane el1: declared; registry id ghost is not in the registry) ·" in line_of(out, "EL1")
    assert "· without rows: 702 ·" in line_of(out, "SA")                    # unknown: the rows are still shown
    # one line, no gap judged; the competitions print in status order, then by code
    assert gaps(out) == ["MODEL STATUS UNKNOWN: CL, EL1, SA — no gap is judged for them (each line gives the reason)"]
    assert [x.split(" · ")[0] for x in out[1:-2]] == ["UNL", "CL", "EL1", "SA"]


def test_an_unreadable_roadmap_is_unknown_never_a_guess(env):
    rm.ROADMAP_PATH.write_text("{not json")
    make_db(env, [(501, "NHL", "2026-10-17 23:00", "SCHEDULED"), (401, "PL", "2026-10-17 14:00", "SCHEDULED")],
            [(401, "soccer_elo_poisson_v22", "2026-10-17 10:00")])
    rc, out = run("--date", DAY)
    assert rc == 0
    assert "· UNKNOWN (the roadmap cannot be read:" in line_of(out, "NHL")
    assert "· LIVE (closing family SOCCER) ·" in line_of(out, "PL")          # C1's families are not the roadmap's


def test_the_real_ledgers_derive_a_status():
    """On the tracked roadmap and registry: the closing families' competitions are LIVE, and every lane named for a
    competition code gives a status (none of them disagrees with its registry entry)."""
    lanes, entries, unread = cm.read_ledgers()
    assert unread is None
    for code in ("MLB", "NFL", "PL"):
        assert cm.model_status(code, lanes, entries)[0] == "LIVE"
    for ln in lanes:
        if ln["lane"].upper() in ("NHL", "NCAA", "UNL", "PD"):
            st, why = cm.model_status(ln["lane"].upper(), lanes, entries)
            assert st in ("LIVE", "SHADOW", "MARKET-ONLY"), why


# ------------------------------------------------------------------------------------- the closing groups --

def test_closing_groups_and_their_files_on_a_day_with_two_start_times(env):
    """C2 by closing.groups itself: the earliest start time covers the games within the 10 minutes after it (14:10 in,
    14:11 the next start time); T-35 in ET; the file closing_<FAMILY>_<start>.json under exports/."""
    make_db(env, [(401, "PL", "2026-10-17 14:00", "SCHEDULED"), (402, "PL", "2026-10-17 14:10", "SCHEDULED"),
                  (403, "PL", "2026-10-17 14:11", "SCHEDULED"), (404, "PL", "2026-10-17 16:30", "SCHEDULED")])
    rc, out = run("--date", DAY)
    assert rc == 0
    assert line_of(out, "PL").endswith(
        "· closing: T-35 09:25 ET [401, 402] → exports/closing_SOCCER_2026-10-17T1400Z.json; "
        "T-35 09:36 ET [403] → exports/closing_SOCCER_2026-10-17T1411Z.json; "
        "T-35 11:55 ET [404] → exports/closing_SOCCER_2026-10-17T1630Z.json")
    cov = cm.coverage(datetime(2026, 10, 17).date(), NOW)
    pl = cov["competitions"][0]
    assert [(g["start"], g["match_ids"]) for g in pl["groups"]] == [
        (utc("2026-10-17 14:00"), [401, 402]), (utc("2026-10-17 14:11"), [403]), (utc("2026-10-17 16:30"), [404])]
    assert pl["groups"][0]["run_at"] == utc("2026-10-17 13:25")
    assert pl["groups"][0]["file"] == f"exports/{cl.closing_name('SOCCER', utc('2026-10-17 14:00'))}"


def test_started_games_leave_the_closing_groups(env, monkeypatch):
    """The watch will not run a started game's closing: at 14:05Z the 14:00 game is started and the 14:10 game is the
    first start time left."""
    monkeypatch.setattr(cl, "clock", lambda: utc("2026-10-17 14:05"))
    make_db(env, [(401, "PL", "2026-10-17 14:00", "SCHEDULED"), (402, "PL", "2026-10-17 14:10", "SCHEDULED")],
            [(401, "v22", "2026-10-17 10:00"), (402, "v22", "2026-10-17 10:00")])
    rc, out = run()
    assert rc == 0
    assert "· rows: v22 2 (latest 2026-10-17 06:00 ET) ·" in line_of(out, "PL")     # one computed_at: no range
    assert line_of(out, "PL").endswith(                                    # T-5 <= 5 minutes <= T-35: due now
        "· closing: started 401; T-35 09:35 ET [402] → exports/closing_SOCCER_2026-10-17T1410Z.json (due now)")
    monkeypatch.setattr(cl, "clock", lambda: utc("2026-10-17 18:00"))
    assert line_of(run()[1], "PL").endswith("· closing: started 401, 402; none left to run")


def receipt(**rec) -> None:
    """One closing receipt in the scratch receipts file (the fields closing.covered_ids reads)."""
    with open(c.receipts_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps({"kind": "closing", **rec}) + "\n")


def test_the_closing_groups_are_the_watchs_own_after_a_closing(env, monkeypatch):
    """closing.due()'s own inputs, the watch's receipts included: the 17:05Z closing succeeded covering 1 and 2, so
    after first pitch the watch's next start time is 17:20Z [3, 4], never 2 re-anchored at 17:13Z (a file the watch
    never writes). Each group's state is due()'s: due now from T-35 to T-5; inside T-5 a miss, no file."""
    games = [(1, "MLB", "2026-09-20 17:05", "SCHEDULED"), (2, "MLB", "2026-09-20 17:13", "SCHEDULED"),
             (3, "MLB", "2026-09-20 17:20", "SCHEDULED"), (4, "MLB", "2026-09-20 17:27", "SCHEDULED")]
    make_db(env, games, [(m, "mlb_v2", "2026-09-20 11:00") for m, *_ in games])
    receipt(family="MLB", start="2026-09-20T17:05:00Z", exit=0,
            covers=[{"match_id": 1, "start": "2026-09-20T17:05:00Z"}, {"match_id": 2, "start": "2026-09-20T17:13:00Z"}])
    for at, state, tail in (
            ("2026-09-20 17:08", "due", "· closing: started 1; a closing finished with 2; T-35 12:45 ET [3, 4] → "
                                        "exports/closing_MLB_2026-09-20T1720Z.json (due now)"),
            ("2026-09-20 17:16", "inside", "· closing: started 1, 2; T-35 12:45 ET [3, 4] inside T-5: no attempt, no "
                                           "file (the watch records a miss)")):
        now = utc(at)
        watch = cl.due("MLB", now)
        mlb = cm.coverage(datetime(2026, 9, 20).date(), now)["competitions"][0]
        assert [(g["start"], g["match_ids"]) for g in mlb["groups"]] == [
            (g["start"], [x["match_id"] for x in g["games"]]) for g in watch["groups"]]
        assert [(g["start"], g["match_ids"]) for g in mlb["groups"]] == [(utc("2026-09-20 17:20"), [3, 4])]
        assert [g["state"] for g in mlb["groups"]] == [state] and watch[state] == watch["groups"]
        monkeypatch.setattr(cl, "clock", lambda now=now: now)
        assert line_of(run("--date", "2026-09-20")[1], "MLB").endswith(tail)
    assert mlb["groups"][0]["file"] is None


def test_a_family_this_machine_refuses_shows_the_refusal_and_claims_no_gap(env, monkeypatch):
    """The host (host.env: SP_SKIP_FAMILIES=MLB) runs no MLB chain and its watch refuses MLB's start times
    (closing._family_refusal): MLB's line names the refusal in place of its groups, and no gap sends the operator to a
    chain this machine never runs. A family not refused keeps its gap."""
    monkeypatch.setenv("SP_SKIP_FAMILIES", "MLB")
    make_db(env, [(50548, "MLB", "2026-10-18 00:00", "SCHEDULED"), (50549, "MLB", "2026-10-17 20:05", "SCHEDULED"),
                  (401, "PL", "2026-10-17 14:00", "SCHEDULED")])
    rc, out = run("--date", DAY)
    assert rc == 0
    mlb = line_of(out, "MLB")
    assert "· LIVE (closing family MLB) · rows: none · without rows: 50549, 50548 ·" in mlb
    assert mlb.endswith("· closing: refused here (laptop only: SP_SKIP_FAMILIES names MLB here (the host cannot reach "
                        "the MLB feed))")
    assert gaps(out) == ["PL: 1 GAME, 0 PREDICTION ROWS — soccer-prematch has not run"]
    assert cm.coverage(datetime(2026, 10, 17).date(), NOW)["competitions"][0]["groups"] == []


def test_receipts_that_cannot_be_read_show_no_groups(env, monkeypatch, tmp_path):
    """Law 4: the watch's receipts unreadable, the groups are not shown (never the groups with nothing finished)."""
    (tmp_path / "receipts-folder").mkdir()
    monkeypatch.setenv("SP_RECEIPTS", str(tmp_path / "receipts-folder"))
    make_db(env, [(401, "PL", "2026-10-17 14:00", "SCHEDULED")], [(401, "v22", "2026-10-17 10:00")])
    rc, out = run("--date", DAY)
    assert rc == 0
    assert line_of(out, "PL").endswith("· closing: not shown (the watch's receipts cannot be read: IsADirectoryError)")


# ------------------------------------------------------------------------------------------------ the day --

def test_the_default_date_is_today_in_et_across_the_utc_midnight(env, monkeypatch):
    """02:30Z on 10-18 is 22:30 ET on 10-17: the default day is 10-17, and a game belongs to the day by its ET date."""
    monkeypatch.setattr(cl, "clock", lambda: utc("2026-10-18 02:30"))
    make_db(env, [(1, "MLB", "2026-10-17 03:30", "FINISHED"),       # 10-16 23:30 ET
                  (2, "MLB", "2026-10-17 04:30", "FINISHED"),       # 10-17 00:30 ET
                  (3, "MLB", "2026-10-18 01:00", "LIVE"),           # 10-17 21:00 ET
                  (4, "MLB", "2026-10-18 04:30", "SCHEDULED")])     # 10-18 00:30 ET
    rc, out = run()
    assert rc == 0
    assert out[0].startswith("COVERAGE 2026-10-17 ET · 1 competition · 2 games · now 2026-10-17 22:30 ET")
    assert "· without rows: 2, 3 ·" in line_of(out, "MLB")
    assert line_of(out, "MLB").endswith("· closing: started 2, 3; none left to run")
    rc, out = run("--date", "2026-10-18")
    assert "· without rows: 4 ·" in line_of(out, "MLB")
    # its run time is on the day before its ET date: written with its date
    assert line_of(out, "MLB").endswith(
        "· closing: T-35 2026-10-17 23:55 ET [4] → exports/closing_MLB_2026-10-18T0430Z.json")
    assert cm.day_bounds(datetime(2026, 11, 1).date()) == (utc("2026-11-01 04:00"), utc("2026-11-02 05:00"))  # 25h


def test_no_game_that_day(env):
    make_db(env, [(1, "MLB", "2026-10-19 23:00", "SCHEDULED")])
    rc, out = run("--date", DAY)
    assert (rc, out) == (0, [out[0], "no stored game that day", "GAPS: none"])
    assert out[0].startswith(f"COVERAGE {DAY} ET · 0 competitions · 0 games")


# ------------------------------------------------------------------------------------------- read-only --

@pytest.mark.parametrize("wal", [False, True], ids=["rollback-journal", "wal"])
def test_it_opens_no_write_transaction_and_makes_no_provider_call(env, monkeypatch, wal):
    """On a rollback-journal file nothing new appears. On a WAL file (the real DB's mode) SQLite itself leaves its -wal
    and -shm sidecars beside the file, as for every ro_connect reader: the -wal is empty (no frame written) and the
    file's bytes are unchanged."""
    make_db(env, [(401, "PL", "2026-10-17 14:00", "SCHEDULED"), (501, "NHL", "2026-10-17 23:00", "SCHEDULED")],
            [(401, "v22", "2026-10-17 10:00")], wal=wal)
    before = hashlib.sha256(env.read_bytes()).hexdigest()
    listing = sorted(p.name for p in env.parent.iterdir())
    real, opened, statements = sqlite3.connect, [], []

    def watched(target, *a, **k):
        con = real(target, *a, **k)
        opened.append((str(target), k.get("uri")))
        con.set_trace_callback(statements.append)
        return con

    def no_net(*a, **k):
        raise AssertionError("coverage made a network call")

    def no_session(*a, **k):
        raise AssertionError("coverage opened an ORM session (a write path)")

    monkeypatch.setattr(sqlite3, "connect", watched)
    monkeypatch.setattr(socket, "create_connection", no_net)
    monkeypatch.setattr(socket.socket, "connect", no_net)
    import cli
    import src.db.database as dbm
    monkeypatch.setattr(cli, "session_scope", no_session)
    monkeypatch.setattr(dbm, "session_scope", no_session)
    rc, out = run("--date", DAY)
    assert rc == 0 and len(out) > 2
    assert opened and all(t.endswith("?mode=ro") and u is True for t, u in opened), opened
    assert statements and all(s.lstrip().upper().startswith("SELECT") for s in statements), statements
    assert hashlib.sha256(env.read_bytes()).hexdigest() == before
    new = {p.name for p in env.parent.iterdir()} - set(listing)
    assert new <= ({env.name + "-wal", env.name + "-shm"} if wal else set()), new     # no journal, no new file
    sidecar = env.parent / (env.name + "-wal")
    assert not sidecar.exists() or sidecar.stat().st_size == 0               # no WAL frame written


def test_a_missing_db_is_refused_and_never_created(env):
    rc, out = run("--date", DAY)
    assert rc == 2
    assert out == [f"COVERAGE REFUSED: no database at {env}: nothing is created (the DB is opened read-only)"]
    assert not env.exists()


def test_a_db_that_cannot_be_opened_is_refused_never_a_traceback(env, monkeypatch, tmp_path):
    """A DATABASE_URL naming a folder, or not SQLite at all: COVERAGE REFUSED and exit 2."""
    for url, why in ((f"sqlite:///{tmp_path}", f"the DB at {tmp_path} cannot be read: "),
                     ("postgresql://x/y",
                      "Not a SQLite URL: postgresql://…: the coverage map reads a SQLite DB only")):
        monkeypatch.setenv("DATABASE_URL", url)
        out = []
        assert cm.run(DAY, echo=out.append) == 2
        assert len(out) == 1 and out[0].startswith(f"COVERAGE REFUSED: {why}"), out


def test_a_date_that_is_not_real_is_refused(env):
    make_db(env, [])
    for bad in ("2026-02-30", "2026-1-5", "today"):
        rc, out = run("--date", bad)
        assert (rc, out) == (2, [f"COVERAGE REFUSED: --date {bad!r} is not a real date (YYYY-MM-DD)"])


def test_the_real_schema(tmp_path, monkeypatch):
    """The SELECTs against src/db/schema.py's own tables (law 1): an empty DB made by the ORM's metadata."""
    from sqlalchemy import create_engine
    from src.db.schema import Base
    db = tmp_path / "real.db"
    eng = create_engine(f"sqlite:///{db}")
    Base.metadata.create_all(eng)
    eng.dispose()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.setattr(cl, "clock", lambda: NOW)
    rc, out = run("--date", DAY)
    assert (rc, out[1:]) == (0, ["no stored game that day", "GAPS: none"])


# ------------------------------------------------------------------------------------------- the hint --

def test_the_hint_is_derived_from_chains_py():
    assert cm.writer_chains("SOCCER") == ["soccer-prematch"]
    assert cm.writer_chains("MLB") == ["mlb-preslate"]
    assert cm.writer_chains("NFL") == ["nfl-predict"]


def test_no_writer_found_no_hint(env, monkeypatch):
    monkeypatch.setattr(cm, "writer_chains", lambda fam: [])
    make_db(env, [(401, "PL", "2026-10-17 14:00", "SCHEDULED")])
    assert gaps(run("--date", DAY)[1]) == ["PL: 1 GAME, 0 PREDICTION ROWS"]


def test_the_predict_commands_are_the_writers_of_prediction_rows():
    """PREDICT_COMMANDS (law 1): Prediction rows are constructed only in training.py and nfl_predict.py, reached among
    the cli commands by `predict` and `predict-nfl` (the web UI's refresh and admin predict job reach
    training.generate_predictions too)."""
    import cli
    made = re.compile(r"(?<![\w.])(?<!class )Prediction\(")             # a constructed row, not the class itself
    files = [*(ROOT / "src").rglob("*.py"), ROOT / "cli.py", ROOT / "main.py"]
    writers = sorted(str(p.relative_to(ROOT)) for p in files if made.search(p.read_text(encoding="utf-8")))
    assert writers == ["src/walters/nfl_predict.py", "src/walters/training.py"]
    assert cm.PREDICT_COMMANDS == ("predict", "predict-nfl")
    assert "generate_predictions(" in inspect.getsource(cli.cli.commands["predict"].callback)
    assert "predict_nfl(" in inspect.getsource(cli.cli.commands["predict-nfl"].callback)
