"""The quarterback agreement receipt (lane nfl-qb, #427; 415 item 4(a); 465 items 3 Q6 and 5; 530 items 4 to 6;
DEV 4, Lane D): read-only counts on a .backup copy and kept payloads. Every test builds its own SQLite file and payload
folder under tmp_path with synthetic rows; nothing under data/ is created or opened; no name and no id is printed."""
import hashlib
import importlib.util
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "nfl_qb_agreement_receipt.py"
spec = importlib.util.spec_from_file_location("nfl_qb_agreement_receipt", SCRIPT)
qr = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = qr
spec.loader.exec_module(qr)

FIRST26 = datetime(2026, 11, 9, 14, 20)           # the first 2026 load on our clock
SECRET = "Zqxsecret Passer"                       # a player's name: never printed


class Store:
    """A throwaway copy: the schema by create_all, rows written in the order the record's insert guards require."""

    def __init__(self, path):
        from sqlalchemy import create_engine

        from src.db.schema import Base
        self.path = path
        self.eng = create_engine("sqlite:///{}".format(path))
        Base.metadata.create_all(self.eng)

    def session(self):
        from sqlalchemy.orm import Session
        return Session(self.eng)

    def load(self, season, fetched, dt, rows, endpoint=None):
        """One depth-chart load: rows = [(team_id, tla, espn_id, name, pos_grp, pos_slot, pos_rank)]."""
        from src.availability import nflverse as nv
        from src.db.schema import AvailabilityAssertion, AvailabilityObservation, Sport
        with self.session() as s:
            o = AvailabilityObservation(sport=Sport.NFL, source="nflverse_depth_charts",
                                        endpoint=endpoint or nv.release_url(season), match_id=None, kickoff_at=None,
                                        poll_label=None, scheduled_at=None, fetched_at=fetched, http_status=200,
                                        payload_sha256=hashlib.sha256(repr((season, fetched)).encode()).hexdigest(),
                                        status="complete", late=False, rows_asserted=len(rows))
            s.add(o)
            s.flush()
            for tid, tla, espn, name, grp, slot, rank in rows:
                attrs = {"pos_grp": grp, "pos_abb": "QB", "pos_slot": slot, "pos_rank": rank,
                         "dt_raw": dt.isoformat(), "espn_id": espn, "gsis_id": None}
                s.add(AvailabilityAssertion(observation_id=o.id, sport=Sport.NFL, kind="depth_rank", player_id=None,
                                            source_player_id=espn, player_name=name, team_id=tid, source_team=tla,
                                            match_id=None, attrs=attrs, source_stamp=dt, recorded_at=fetched))
            s.commit()

    def close(self):
        self.eng.dispose()


def _passing(tid, players):
    """A players payload team block as the provider sends it: players = [(id, name, attempts)]."""
    return {"team": {"id": tid}, "groups": [{"name": "Passing", "players": [
        {"player": {"id": pid, "name": nm}, "statistics": [{"name": "comp att", "value": "10/{}".format(att)}]}
        for pid, nm, att in players]}]}


def _world(tmp_path, folder="copy"):
    from src.db.schema import Competition, Match, MatchStatus, Sport, Team
    path = tmp_path / folder / "sports.db"
    path.parent.mkdir(parents=True)
    pay = tmp_path / "payloads"
    st = Store(path)
    F, S = MatchStatus.FINISHED, MatchStatus.SCHEDULED
    with st.session() as s:
        nfl = Competition(sport=Sport.NFL, code="NFL", name="NFL", area="USA", type="LEAGUE")
        ncaa = Competition(sport=Sport.NFL, code="NCAA", name="NCAA", area="USA", type="LEAGUE")
        s.add_all([nfl, ncaa])
        s.flush()
        teams = [Team(sport=Sport.NFL, name=("Team {}".format(i)), tla="T{}".format(i),
                      external_ids={"api_american_football": str(100 + i)}) for i in range(8)]
        s.add_all(teams)
        s.flush()
        T = [t.id for t in teams]
        games = {}

        def g(key, when, status, home, away, season="2026", gid=None, stage="Regular Season", comp=nfl):
            m = Match(sport=Sport.NFL, competition_id=comp.id, season=season, utc_date=when, status=status,
                      home_team_id=T[home], away_team_id=T[away], home_score=21 if status == F else None,
                      away_score=17 if status == F else None, stage=stage,
                      external_ids={"api_american_football": str(gid)} if gid else {})
            s.add(m)
            s.flush()
            games[key] = (m.id, gid)
        g("G1", datetime(2026, 11, 15, 18), F, 0, 1, gid=9001)          # agree; differ (second)
        g("G2", datetime(2026, 11, 16, 18), F, 2, 3, gid=9002)          # agree by suffix; no pair
        g("G3", datetime(2026, 11, 9, 20), F, 4, 5, gid=9003)           # within 24 h of the first load
        g("G4", datetime(2026, 11, 17, 18), F, 0, 2, gid=9004)          # no starter payload
        g("G5", datetime(2026, 11, 18, 18), F, 1, 3, gid=9005)          # a tie; differ (third or lower)
        g("G6", datetime(2026, 11, 19, 18), F, 6, 7, gid=9006)          # QB1 ambiguous; differ, not on the chart
        g("OLD", datetime(2026, 11, 1, 18), F, 0, 1, gid=9007)          # before the window
        g("NEXT", datetime(2026, 11, 30, 18), S, 0, 1, gid=9008)        # in the window, not finished
        g("PRE", datetime(2026, 11, 20, 18), F, 0, 1, gid=9009, stage="Pre Season")
        g("COL", datetime(2026, 11, 20, 18), F, 0, 1, gid=9010, comp=ncaa)
        g("Y25", datetime(2025, 9, 7, 17), F, 0, 1, season="2025", gid=8001)
        s.commit()
    # 2025, the source clock: a load stamped 2025-09-01, fetched on 2026-11-09 (backfilled)
    st.load(2025, datetime(2026, 11, 9, 14, 12), datetime(2025, 9, 1), [
        (T[0], "T0", "e1", "Josh Allen", "OFF", "QB", "1"),
        (T[1], "T1", "e2", "Tom Brady", "OFF", "QB", "1")])
    rows26 = [
        (T[0], "T0", "e1", "Josh Allen", "OFF", "QB", "1"),
        (T[1], "T1", "e2", "Tom Brady", "OFF", "QB", "1"),
        (T[1], "T1", "e3", "Mac Jones", "OFF", "QB", "2"),
        (T[1], "T1", "e9", "Bailey Zappe", "OFF", "QB", "3"),
        (T[2], "T2", "e4", "Marvin Harrison Jr.", "OFF", "QB", "1"),
        (T[3], "T3", "e5", "Zach Wilson", "OFF", "QB", "1"),
        (T[4], "T4", "e6", "Joe Burrow", "OFF", "QB", "1"),
        (T[5], "T5", "e7", "Lamar Jackson", "OFF", "QB", "1"),
        (T[6], "T6", "e10", "Dak Prescott", "OFF", "QB", "1"),
        (T[6], "T6", "e11", "Cooper Rush", "SPEC", "QB", "1"),       # a second QB1 in another group
        (T[7], "T7", "e12", SECRET, "OFF", "QB", "1"),
    ]
    st.load(2026, FIRST26, datetime(2026, 11, 9, 12), rows26)
    st.close()
    for k in ("-wal", "-shm", "-journal"):
        assert not path.with_name(path.name + k).exists()

    def players(season, gid, blocks):
        d = pay / season
        d.mkdir(parents=True, exist_ok=True)
        (d / "players_{}.json".format(gid)).write_text(json.dumps(blocks), encoding="utf-8")
    players("2026", 9001, [_passing(100, [(1, "Josh Allen", 31)]), _passing(101, [(3, "Mac Jones", 30)])])
    players("2026", 9002, [_passing(102, [(4, "Marvin Harrison", 25)]), _passing(103, [(8, "Bo Nix", 28)])])
    players("2026", 9003, [_passing(104, [(6, "Joe Burrow", 33)]), _passing(105, [(7, "Lamar Jackson", 29)])])
    players("2026", 9005, [_passing(101, [(9, "Bailey Zappe", 22), (2, "Tom Brady", 5)]),
                           _passing(103, [(8, "Bo Nix", 20), (5, "Zach Wilson", 20)])])
    players("2026", 9006, [_passing(106, [(10, "Dak Prescott", 30)]),
                           _passing(107, [(12, SECRET, 3), (13, "Drew Lock", 27)])])
    players("2025", 8001, [_passing(100, [(1, "Josh Allen", 30)]), _passing(101, [(2, "Tom Brady", 35)])])
    return path, pay


def run(argv):
    lines = []
    code = qr.main(argv, out=lines.append)
    return code, "\n".join(lines)


def read_line(text, season, label):
    seen = False
    for ln in text.splitlines():
        if ln.startswith("SEASON {}".format(season)):
            seen = True
        elif seen and ln.strip().startswith(label + " ["):
            i = text.splitlines().index(ln)
            return "\n".join(text.splitlines()[i:i + 5])
    raise AssertionError("no read line {} {}".format(season, label))


def tail(text):
    last = text.splitlines()[-1]
    assert last.startswith(qr.TAIL + " ")
    return json.loads(last[len(qr.TAIL) + 1:])


# ---- the counts -----------------------------------------------------------------------------------------------------


def test_the_2026_reads(tmp_path):
    db, pay = _world(tmp_path)
    code, text = run(["--db", str(db), "--payloads", str(pay)])
    assert code == 0, text
    assert "the first observation of the 2026 depth chart on our clock: 2026-11-09T14:20:00Z" in text
    t = tail(text)
    s26 = t["seasons"][0]
    assert s26["season"] == "2026" and s26["clock"] == "recorded"
    assert s26["games"] == 8 and s26["before_window"] == 1 and s26["finished_in_window"] == 6
    assert s26["status"] == {"FINISHED": 7, "SCHEDULED": 1}
    t0 = s26["reads"][1]
    assert t0["read"] == "T-0" and t0["sides"] == 12
    # G1: T0 agree, T1 differ (second); G2: T2 agree (suffix), T3 no pair; G3: both agree;
    # G4: no payload (both sides); G5: T1 differ (third or lower), T3 tie; G6: T6 ambiguous, T7 differ (not on chart)
    assert t0["agree"] == 4 and t0["differ"] == 3 and t0["no_pair"] == 1 and t0["no_row"] == 4
    assert t0["differ_by_place"] == {"second": 1, "third or lower": 1, "not on the chart": 1}
    assert t0["chart_cause"] == {"QB1 ambiguous": 1}
    assert t0["no_pair_by"] == {"neither name found on the other side": 1}
    assert t0["starter_cause"] == {"no starter payload": 2, "tied for the most attempts": 1}
    t24 = s26["reads"][0]
    assert t24["chart_cause"]["no T-24h row on our clock (kickoff less than 24 h after the first load)"] == 2
    assert t24["agree"] == 2 and t24["no_row"] == 6


def test_the_2025_reads_are_the_sources_clock(tmp_path):
    db, pay = _world(tmp_path)
    code, text = run(["--db", str(db), "--payloads", str(pay)])
    assert code == 0
    s25 = tail(text)["seasons"][1]
    assert s25["season"] == "2025" and s25["clock"] == "source"
    for r in s25["reads"]:
        assert r["agree"] == 2 and r["differ"] == 0 and r["no_row"] == 0
    assert "SEASON 2025 (THE SOURCE'S CLOCK (nflverse's own load times))" in text
    assert "T-24h [THE SOURCE'S CLOCK" in text


def test_preseason_college_and_unfinished_games_are_out(tmp_path):
    db, pay = _world(tmp_path)
    code, text = run(["--db", str(db), "--payloads", str(pay)])
    s26 = tail(text)["seasons"][0]
    assert s26["games"] == 8                                  # PRE and the college game are not among them
    assert s26["reads"][0]["sides"] == 12                     # six finished games in the window, two sides each


def test_the_pair_classes_and_the_attribution_print(tmp_path):
    db, pay = _world(tmp_path)
    code, text = run(["--db", str(db), "--payloads", str(pay)])
    assert "paired by id: 0 (no id is carried by both sources" in text
    assert "Depth charts: nflverse (CC BY 4.0)" in text


def test_names_that_normalise_alike_are_never_chosen(tmp_path):
    db, pay = _world(tmp_path)
    (pay / "2026" / "players_9001.json").write_text(json.dumps(
        [_passing(100, [(1, "Josh Allen", 31), (99, "Josh  Allen", 2)]), _passing(101, [(3, "Mac Jones", 30)])]))
    code, text = run(["--db", str(db), "--payloads", str(pay)])
    t0 = tail(text)["seasons"][0]["reads"][1]
    assert t0["no_pair_by"]["two players of the team normalise to one name"] == 1     # NO PAIR, never chosen (530 Q4)
    assert t0["agree"] == 3 and "two passers' names normalise to one" not in t0["starter_cause"]


def test_the_normalisation():
    assert qr.norm("Marvin Harrison Jr.") == qr.norm("marvin  HARRISON") == "marvin harrison"
    assert qr.norm("José Núñez") == "jose nunez"
    assert qr.norm("A.J. Brown") == "aj brown" and qr.norm("Patrick Mahomes II") == "patrick mahomes"
    assert qr.norm("Jr") == "jr" and qr.norm("  ") is None and qr.norm(None) is None


def test_no_2026_load_says_so(tmp_path):
    db, pay = _world(tmp_path)
    con = sqlite3.connect(str(db))
    rows = con.execute("SELECT count(*) FROM availability_observations").fetchone()
    con.close()
    assert rows[0] == 2
    from src.availability import nflverse as nv
    # a copy whose 2026 observation is a hand-carried file: the window is never opened by it
    db2 = tmp_path / "other" / "sports.db"
    db2.parent.mkdir()
    st = Store(db2)
    st.load(2026, FIRST26, datetime(2026, 11, 9, 12), [(1, "T0", "e1", "A B", "OFF", "QB", "1")],
            endpoint="file:depth_charts_2026.csv")
    st.close()
    code, text = run(["--db", str(db2), "--payloads", str(pay)])
    assert code == 0 and "NONE STORED" in text and "hand-carried file observations, never the window's start: 1" in text
    assert nv.release_url(2026).endswith("depth_charts_2026.csv")


# ---- what it never prints and never does ----------------------------------------------------------------------------


def test_no_name_and_no_id_is_printed(tmp_path):
    db, pay = _world(tmp_path)
    code, text = run(["--db", str(db), "--payloads", str(pay)])
    assert code == 0
    # the copy's sha256 is printed by design, and a hex digest can hold "e12" or "9001" by chance (CI on #1139,
    # smoke-py310: 'e12' found inside 8e8e1272...): the digests are taken out before the ids are looked for
    import re
    assert re.search(r"\b[0-9a-f]{64}\b", text)
    scrubbed = re.sub(r"\b[0-9a-f]{64}\b", "<sha256>", text)
    for word in (SECRET, "Josh", "Allen", "Brady", "Mac Jones", "Bo Nix", "e12", "9001", "8001"):
        assert word not in scrubbed, word


def test_the_copy_and_the_payloads_are_unchanged(tmp_path):
    db, pay = _world(tmp_path)

    def snap():
        return sorted((str(p), p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest())
                      for p in tmp_path.rglob("*") if p.is_file())
    before = snap()
    code, text = run(["--db", str(db), "--payloads", str(pay)])
    assert code == 0 and snap() == before
    assert "sha256 {}".format(hashlib.sha256(db.read_bytes()).hexdigest()) in text


@pytest.mark.parametrize("name", ["data", "DATA"])
def test_a_copy_under_data_is_refused(tmp_path, name):
    db, pay = _world(tmp_path, folder=name)
    code, text = run(["--db", str(db), "--payloads", str(pay)])
    assert code == 2 and "REFUSED" in text and "SEASON" not in text


def test_payloads_under_data_or_missing_are_refused(tmp_path):
    db, pay = _world(tmp_path)
    code, text = run(["--db", str(db), "--payloads", str(tmp_path / "data" / "p")])
    assert code == 2 and "directory named data" in text
    code, text = run(["--db", str(db), "--payloads", str(tmp_path / "nope")])
    assert code == 2 and "not a folder" in text


@pytest.mark.parametrize("sfx", ["-wal", "-shm", "-journal"])
def test_a_sidecar_refuses(tmp_path, sfx):
    db, pay = _world(tmp_path)
    (db.parent / (db.name + sfx)).write_bytes(b"")
    code, text = run(["--db", str(db), "--payloads", str(pay)])
    assert code == 2 and "sidecar" in text


def test_a_copy_without_the_record_refuses(tmp_path):
    db, pay = _world(tmp_path)
    con = sqlite3.connect(str(db))
    con.execute("DROP TABLE availability_assertions")
    con.commit()
    con.close()
    code, text = run(["--db", str(db), "--payloads", str(pay)])
    assert code == 2 and "availability_assertions" in text


def test_the_checkout_data_dir_is_refused_and_never_created(tmp_path):
    target = ROOT / "data" / "no_such_copy_qb.db"
    existed = (ROOT / "data").exists()
    code, text = run(["--db", str(target), "--payloads", str(tmp_path)])
    assert code == 2 and not target.exists() and (ROOT / "data").exists() == existed


def test_no_bytecode_of_the_repo_is_written(tmp_path):
    import subprocess
    db, pay = _world(tmp_path)
    cache = tmp_path / "pycache"
    cache.mkdir()
    res = subprocess.run([sys.executable, "-X", "pycache_prefix={}".format(cache), str(SCRIPT), "--db", str(db),
                          "--payloads", str(pay)], capture_output=True, text=True, cwd=str(tmp_path), timeout=180)
    assert res.returncode == 0, res.stdout + res.stderr
    own = cache.joinpath(*ROOT.parts[1:])
    assert [p for d in ("src", "scripts") for p in (own / d).rglob("*.pyc")] + list(own.glob("config*.pyc")) == []


def test_it_makes_no_network_call(tmp_path, monkeypatch):
    import socket
    db, pay = _world(tmp_path)

    def refuse(*a, **k):
        raise AssertionError("a network call")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    code, text = run(["--db", str(db), "--payloads", str(pay)])
    assert code == 0


def test_python_310_floor_no_fstrings():
    import io
    import tokenize
    src = SCRIPT.read_text(encoding="utf-8")
    compile(src, str(SCRIPT), "exec")
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        assert tokenize.tok_name[tok.type] != "FSTRING_START", tok
        if tokenize.tok_name[tok.type] == "STRING":
            prefix = tok.string[: len(tok.string) - len(tok.string.lstrip("rRbBuUfF"))]
            assert "f" not in prefix.lower(), tok


# ---- the pre-PR review's findings, pinned ---------------------------------------------------------------------------


def _extra_load(db, fetched, rows, season=2026):
    st = Store(db)
    st.load(season, fetched, fetched - timedelta(hours=2), rows)
    st.close()


def _team_id(db, idx):
    con = sqlite3.connect(str(db))
    tid = con.execute("SELECT id FROM teams ORDER BY id LIMIT 1 OFFSET ?", (idx,)).fetchone()[0]
    con.close()
    return tid


def test_an_overlong_payloads_path_is_refused(tmp_path):
    db, pay = _world(tmp_path)
    code, text = run(["--db", str(db), "--payloads", str(pay / ("x" * 300))])
    assert code == 2 and "REFUSED" in text


def test_chart_twins_and_starter_twins_are_no_pair(tmp_path):
    db, pay = _world(tmp_path)
    t1 = _team_id(db, 1)
    # team 1 at 11-10: QB1 Tom Brady; "Mac Jones" at rank 2 and "Mac Jones Jr." at rank 3 (two players, one name)
    _extra_load(db, datetime(2026, 11, 10, 14), [(t1, "T1", "e2", "Tom Brady", "OFF", "QB", "1"),
                                                (t1, "T1", "e3", "Mac Jones", "OFF", "QB", "2"),
                                                (t1, "T1", "e33", "Mac Jones Jr.", "OFF", "QB", "3")])
    code, text = run(["--db", str(db), "--payloads", str(pay)])
    t0 = tail(text)["seasons"][0]["reads"][1]
    # G1's side T1 (starter Mac Jones) now rests on a shared name: NO PAIR, never a DIFFER at a chosen rank
    assert t0["no_pair_by"]["two players of the team normalise to one name"] == 1
    assert t0["differ_by_place"].get("second", 0) == 0


def test_one_player_at_rank_one_under_two_names_is_ambiguous_on_every_seed(tmp_path):
    import subprocess
    db, pay = _world(tmp_path)
    t0id = _team_id(db, 0)
    st = Store(db)
    st.load(2026, datetime(2026, 11, 9, 14, 21), datetime(2026, 11, 9, 12, 1), [
        (t0id, "T0", "e1", "Cam Ward", "OFF", "QB", "1"), (t0id, "T0", "e1", "Cam Ward", "SPEC", "QB", "1"),
        (t0id, "T0", "e2", "Two", "OFF", "QB", "2"), (t0id, "T0", "e3", "Three", "OFF", "QB", "3")])
    st.load(2026, datetime(2026, 11, 10, 14), datetime(2026, 11, 10, 12), [
        (t0id, "T0", "e1", "Cameron Ward", "OFF", "QB", "1")])
    st.close()
    outs = set()
    for seed in ("0", "1", "4", "5"):
        res = subprocess.run([sys.executable, str(SCRIPT), "--db", str(db), "--payloads", str(pay)],
                             capture_output=True, text=True, timeout=180, env={**__import__("os").environ,
                                                                                "PYTHONHASHSEED": seed})
        assert res.returncode == 0, res.stdout + res.stderr
        outs.add(res.stdout.splitlines()[-1])
    assert len(outs) == 1                                          # the same copy gives the same counts on every run
    assert "first at another slot" not in next(iter(outs))


def test_an_unmapped_team_is_named_as_such_and_counted(tmp_path):
    db, pay = _world(tmp_path)
    st = Store(db)
    st.load(2026, datetime(2026, 11, 10, 14), datetime(2026, 11, 10, 12), [(None, "LA", "e40", "X Y", "OFF", "QB", "1")])
    st.close()
    code, text = run(["--db", str(db), "--payloads", str(pay)])
    assert code == 0 and tail(text)["unmapped_qb_rows"] == 1
    assert "maps to no team of ours (never read for a side): 1" in text


@pytest.mark.parametrize("payload", ['[{"team": {"id": 100}, "groups": [{"name": "Passing", "players": [{"player": '
                                     '{"id": 1, "name": "Josh Allen"}, "statistics": [{"name": "attempts", "value": '
                                     'Infinity}]}]}]}]', "[" * 100000 + "]" * 100000])
def test_a_malformed_payload_is_a_cause_never_a_refusal(tmp_path, payload):
    db, pay = _world(tmp_path)
    (pay / "2026" / "players_9001.json").write_text(payload, encoding="utf-8")
    code, text = run(["--db", str(db), "--payloads", str(pay)])
    assert code == 0, text
    t0 = tail(text)["seasons"][0]["reads"][1]
    assert set(t0["starter_cause"]) & {"no attempts read", "the starter payload cannot be read"}


def test_a_non_ascii_digit_rank_is_unread_never_a_refusal(tmp_path):
    db, pay = _world(tmp_path)
    t1 = _team_id(db, 1)
    _extra_load(db, datetime(2026, 11, 9, 14, 30), [(t1, "T1", "e2", "Tom Brady", "OFF", "QB", "1"),
                                                    (t1, "T1", "e3", "Mac Jones", "OFF", "QB", "\u00b2"),
                                                    (t1, "T1", "e9", "Bailey Zappe", "OFF", "QB", "3")])
    code, text = run(["--db", str(db), "--payloads", str(pay)])
    assert code == 0, text


def test_a_payload_linked_into_data_is_never_opened(tmp_path):
    import os
    db, pay = _world(tmp_path)
    data = tmp_path / "data"
    data.mkdir()
    src = pay / "2026" / "players_9001.json"
    tgt = data / "players_9001.json"
    tgt.write_bytes(src.read_bytes())
    src.unlink()
    try:
        os.symlink(tgt, src)
    except (OSError, NotImplementedError):
        pytest.skip("no symlinks here")
    code, text = run(["--db", str(db), "--payloads", str(pay)])
    assert code == 0
    t0 = tail(text)["seasons"][0]["reads"][1]
    assert t0["starter_cause"]["the starter payload lies outside the payload folder"] == 2


def test_no_env_file_is_read_and_no_provider_client_is_built(tmp_path):
    import subprocess
    db, pay = _world(tmp_path)
    cwd = tmp_path / "envcwd"
    cwd.mkdir()
    (cwd / ".env").write_text("API_AMERICAN_FOOTBALL_RPM=abc\nZQX_SYNTH_KEY=not-a-key\n", encoding="utf-8")
    code = ("import runpy, sys, os; sys.argv=['x','--db',%r,'--payloads',%r]\n"
            "try:\n    runpy.run_path(%r, run_name='__main__')\nexcept SystemExit as e:\n    rc=e.code\n"
            "print('ENV', 'ZQX_SYNTH_KEY' in os.environ, 'requests' in sys.modules, rc)") % (
                str(db), str(pay), str(SCRIPT))
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(cwd), timeout=180)
    last = res.stdout.strip().splitlines()[-1]
    assert last.startswith("ENV False") and last.endswith(" 0"), res.stdout + res.stderr


def test_passing_lines_and_attempts_are_the_probes_own():
    spec2 = importlib.util.spec_from_file_location("nfl_qb_probe_pin", ROOT / "scripts" / "nfl_qb_probe.py")
    probe = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(probe)
    blocks = [_passing(1, [(1, "A", 30), (2, "B", 3)]), {"groups": "x"}, {"groups": [{"name": " PASSING "}]},
              {"groups": [{"name": "Rushing", "players": [{"player": {"id": 1}}]}]},
              {"groups": [{"name": "passing", "players": [{"player": "x", "statistics": [{"name": "Att", "value": "7"}]},
                                                           "bad", {"statistics": "x"}]}]}]
    for b in blocks:
        assert qr.passing_lines(b) == probe.passing_lines(b)
    for stats in ([("comp att", "20/31")], [("attempts", "12")], [("att", None)], [("c/att", "x/y")],
                  [("yards", 200)], [("passing attempts", 4)], [("comp/att", "3")]):
        assert qr.attempts(stats) == probe.attempts(stats)
