"""Addendum 544 item 2, ruled by 545 item 3 (Refs #1141): the NFL snapshot de-vig receipt, read-only.

A throwaway SQLite copy under tmp_path (never data/), built through the ORM. Every value is synthetic. The pooled NFL
snapshot is written as service.sync_odds_nfl writes it (MarketSnapshot.average_implied over every offer, over the sum);
the close's own fair is close_1x2's. A sentinel book name and price must never reach the console."""
import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "nfl_snapshot_devig_receipt.py"
_spec = importlib.util.spec_from_file_location("nfl_snapshot_devig_receipt", SCRIPT)
rc = importlib.util.module_from_spec(_spec)
sys.modules["nfl_snapshot_devig_receipt"] = rc
_spec.loader.exec_module(rc)

SECRET_BOOK = "SecretBook"
SECRET_PRICE = 7.77777
D = "2026-11-22T"
KO = D + "18:00:00"
BOOKS = {"A": (1.50, 2.60), "B": (1.55, 2.40), "C": (1.45, 2.85)}       # three overrounds: the two de-vigs part
ONE_BOOK = {SECRET_BOOK: (1.70, 2.20)}                                 # one book: pooled = the close's own fair


def _dt(v):
    return datetime.fromisoformat(v)


def pooled(books):
    from src.walters.value import MarketSnapshot
    by = {}
    for bk, prices in books.items():
        for sel, px in zip(("HOME", "AWAY"), prices):
            if px is not None:
                by.setdefault(sel, []).append((bk, px))
    imp = MarketSnapshot(market="1X2", by_selection=by).average_implied()
    over = sum(imp.values())
    return {k: v / over for k, v in imp.items()}


# id: (code, stage, kickoff, [(captured_at, {sel: devig})], odds: (captured_at, books) or None, kalshi rows)
def games():
    p3 = pooled(BOOKS)
    p1 = pooled(ONE_BOOK)
    return {
        # first HOME-only, last pooled from three books (differs from the close at 4 places); book flag, from_at end
        1: ("NFL", "REGULAR", KO, [(D[:8] + "20T12:00:00", {"HOME": 1.0}), (D + "17:00:00", p3)],
            (D + "17:00:00", BOOKS), []),
        # one book: agree; Kalshi moves 10pp: the Kalshi flag and the combined flag, no book flag
        2: ("NFL", "REGULAR", KO, [(D + "12:00:00", {"HOME": 0.55, "AWAY": 0.45}), (D + "17:30:00", p1)],
            (D + "17:30:00", ONE_BOOK),
            [(D + "14:00:00", "HOME", 0.5), (D + "14:00:00", "AWAY", 0.5), (D + "17:00:00", "HOME", 0.6),
             (D + "17:00:00", "AWAY", 0.4)]),
        # first AWAY-only; no odds kept
        3: ("NFL", "REGULAR", KO, [(D[:8] + "21T10:00:00", {"AWAY": 1.0}), (D + "17:00:00", {"HOME": 0.5, "AWAY": 0.5})],
            None, []),
        # last HOME-only, one book quoting HOME alone: no complete book; book flag at the to_at end
        4: ("NFL", "REGULAR", KO, [(D + "11:00:00", {"HOME": 0.5, "AWAY": 0.5}), (D + "17:50:00", {"HOME": 1.0})],
            (D + "17:50:00", {"Z": (1.9, None)}), []),
        # the hidden end: a book flag at 16:00, then an AWAY-only last stamp line_move skips
        5: ("NFL", "REGULAR", KO, [(D + "14:00:00", {"HOME": 0.5, "AWAY": 0.5}),
                                   (D + "16:00:00", {"HOME": 0.58, "AWAY": 0.42}), (D + "17:30:00", {"AWAY": 1.0})],
            (D + "17:30:00", {"Z": (None, 1.9)}), []),
        # odds stamped at another time (no session at 17:20)
        6: ("NFL", "REGULAR", KO, [(D + "17:00:00", {"HOME": 0.5, "AWAY": 0.5})],
            (D + "17:20:00", {"Y": (SECRET_PRICE, 1.2)}), []),
        # sessions at kickoff and after it; the odds stamped at the one after
        7: ("NFL", "REGULAR", KO, [(D + "10:00:00", {"HOME": 0.5, "AWAY": 0.5}), (KO, {"HOME": 0.5, "AWAY": 0.5}),
                                   (D + "18:30:00", {"HOME": 0.5, "AWAY": 0.5})],
            (D + "18:30:00", {"Y": (1.9, 1.9)}), []),
        # kicks off after the copy's newest snapshot: counted apart
        8: ("NFL", "REGULAR", "2026-12-20T18:00:00", [(D + "10:00:00", {"HOME": 0.5, "AWAY": 0.5})], None, []),
        # ever flagged but not at the bell: 16:00 moves 8pp, 17:30 comes back to +2
        9: ("NFL", "REGULAR", KO, [(D + "14:00:00", {"HOME": 0.5, "AWAY": 0.5}),
                                   (D + "16:00:00", {"HOME": 0.58, "AWAY": 0.42}),
                                   (D + "17:30:00", {"HOME": 0.52, "AWAY": 0.48})], None, []),
        # preseason: counted apart
        10: ("NFL", "Preseason - Week 1", KO, [(D + "10:00:00", {"HOME": 0.5, "AWAY": 0.5})], None, []),
        # college: a leg at exactly 0 (the writer cannot write it; the count must still see it)
        20: ("NCAA", "REGULAR", KO, [(D + "10:00:00", {"HOME": 0.0, "AWAY": 1.0})], None, []),
        # college across a month's end in New York: 2026-12-01 01:00Z is 2026-11-30 in ET
        21: ("NCAA", "REGULAR", "2026-12-01T01:00:00", [("2026-12-01T00:30:00", {"HOME": 0.5, "AWAY": 0.5})], None,
             []),
        # another code under Sport.NFL
        30: ("UFL", "REGULAR", KO, [(D + "10:00:00", {"HOME": 0.5, "AWAY": 0.5})], None, []),
    }


def build_db(path: Path) -> None:
    from src.db.schema import Base, Competition, Match, MatchStatus, Odds, OddsSnapshot, Sport, Team
    eng = create_engine("sqlite:///{}".format(path))
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        comps = {c: Competition(sport=Sport.NFL, code=c, name=c, area="USA", type="LEAGUE")
                 for c in ("NFL", "NCAA", "UFL")}
        soccer = Competition(sport=Sport.SOCCER, code="PL", name="PL", area="England", type="LEAGUE")
        s.add_all(list(comps.values()) + [soccer])
        s.flush()
        for mid, (code, stage, ko, sessions, odds, kal) in games().items():
            h, a = Team(sport=Sport.NFL, name="H{}".format(mid)), Team(sport=Sport.NFL, name="A{}".format(mid))
            s.add_all([h, a])
            s.flush()
            s.add(Match(id=mid, sport=Sport.NFL, competition_id=comps[code].id, season="2026", stage=stage,
                        utc_date=_dt(ko), status=MatchStatus.FINISHED, home_team_id=h.id, away_team_id=a.id))
            s.flush()
            for at, legs in sessions:
                for sel, v in legs.items():
                    s.add(OddsSnapshot(match_id=mid, market="1X2", selection=sel, devig_prob=v, n_books=9,
                                       captured_at=_dt(at), source="api_american_football"))
            if odds:
                at, books = odds
                for bk, prices in books.items():
                    for sel, px in zip(("HOME", "AWAY"), prices):
                        if px is not None:
                            s.add(Odds(match_id=mid, bookmaker=bk, market="1X2", selection=sel, price_decimal=px,
                                       captured_at=_dt(at), source="api_american_football"))
                s.add(Odds(match_id=mid, bookmaker=SECRET_BOOK, market="SPREADS", selection="HOME",
                           price_decimal=SECRET_PRICE, line=-3.5, captured_at=_dt(at), source="api_american_football"))
            for at, sel, v in kal:
                s.add(OddsSnapshot(match_id=mid, market="ML", selection=sel, devig_prob=v, captured_at=_dt(at),
                                   source="kalshi"))
        # the copy's newest snapshot (a Kalshi row), and a row of the source on a soccer match: counted apart
        th, ta = Team(sport=Sport.SOCCER, name="X"), Team(sport=Sport.SOCCER, name="Y")
        s.add_all([th, ta])
        s.flush()
        s.add(Match(id=99, sport=Sport.SOCCER, competition_id=soccer.id, season="2026/27", utc_date=_dt(KO),
                    status=MatchStatus.FINISHED, home_team_id=th.id, away_team_id=ta.id))
        s.add(OddsSnapshot(match_id=99, market="1X2", selection="HOME", devig_prob=0.5,
                           captured_at=_dt(D + "10:00:00"), source="api_american_football"))
        s.add(OddsSnapshot(match_id=2, market="ML", selection="HOME", devig_prob=0.5,
                           captured_at=_dt("2026-12-02T12:00:00"), source="kalshi"))
        s.commit()
    eng.dispose()


@pytest.fixture
def world(tmp_path):
    db = tmp_path / "copy.db"
    build_db(db)
    return {"db": db, "tmp": tmp_path}


def run(db):
    out = []
    code = rc.main(["--db", str(db)], out=out.append)
    return code, out


def tail(out):
    assert out[-1].startswith(rc.TAIL + " ")
    return json.loads(out[-1][len(rc.TAIL) + 1:])


# ---- the premise and the buckets ----------------------------------------------------------------------------------

def test_the_premise_pooled_and_per_book_part_at_4_places():
    from types import SimpleNamespace as NS

    from src.walters.close import BINARY, close_1x2
    t = _dt(D + "17:00:00")
    rows = [NS(market="1X2", selection=sel, bookmaker=bk, price_decimal=px, captured_at=t, line=None)
            for bk, prices in BOOKS.items() for sel, px in zip(("HOME", "AWAY"), prices)]
    fair = close_1x2(rows, _dt(KO), BINARY)["fair"]
    assert round(fair["HOME"], 4) != round(pooled(BOOKS)["HOME"], 4)


def test_the_diff_buckets_are_half_open():
    assert rc.diff_bucket(0.0) == "under 0.1 pp"
    assert rc.diff_bucket(0.1) == "0.1-0.5 pp"
    assert rc.diff_bucket(0.5) == "0.5-1 pp"
    assert rc.diff_bucket(1.0) == "1-2 pp"
    assert rc.diff_bucket(2.0) == "2-5 pp"
    assert rc.diff_bucket(5.0) == "5 pp or more"


# ---- (a) and (b) --------------------------------------------------------------------------------------------------

def test_a_sessions_by_their_own_legs(world):
    code, out = run(world["db"])
    assert code == 0
    a = tail(out)["families"]["NFL"]["a"]
    assert a["complete"] == 15 and a["HOME-only"] == 2 and a["AWAY-only"] == 2
    assert a["all"] == 19                      # games 1 to 9 (10 is preseason, apart)
    assert a["leg_exactly_1"] == 4            # every one-sided session is written at exactly 1.0
    assert a["leg_exactly_0"] == 0
    assert a["at_kickoff"] == 1 and a["after_kickoff"] == 1
    ncaa = tail(out)["families"]["NCAA"]["a"]
    assert ncaa["leg_exactly_0"] == 1 and ncaa["leg_exactly_1"] == 1


def test_b_the_first_session_by_its_side(world):
    code, out = run(world["db"])
    b = tail(out)["families"]["NFL"]["b"]
    assert b["first"] == {"HOME-only": 1, "AWAY-only": 1, "complete": 6}
    assert b["with_a_first_session"] == 8


# ---- (c) ----------------------------------------------------------------------------------------------------------

def test_c_the_last_session_against_the_close(world):
    code, out = run(world["db"])
    c = tail(out)["families"]["NFL"]["c"]
    assert c["compared"] == 2 and c["agree"] == 1
    assert c["differ"] == {"under 0.1 pp": 1}                  # game 1: three books, pooled vs per book
    assert c["cause"] == {rc.C_NO_ODDS: 2, rc.C_UNPRICED: 2, rc.C_OTHER: 1, rc.C_POST: 1}
    assert c["differ_pp_dist"]["n"] == 1 and 0 < c["differ_pp_dist"]["max"] < 0.1


def test_c_the_stored_value_re_derives_from_the_stored_offers(world):
    code, out = run(world["db"])
    assert rc.C_NOT_REDERIVED not in tail(out)["families"]["NFL"]["c"]["cause"]


def test_c_a_session_that_does_not_re_derive_is_counted(tmp_path):
    db = tmp_path / "c.db"
    build_db(db)
    con = sqlite3.connect(str(db))
    con.execute("UPDATE odds_snapshots SET devig_prob = devig_prob + 0.001 WHERE match_id = 2 AND captured_at LIKE "
                "'2026-11-22 17:30%' AND source = 'api_american_football'")
    con.commit()
    con.close()
    code, out = run(db)
    assert tail(out)["families"]["NFL"]["c"]["cause"][rc.C_NOT_REDERIVED] == 1


# ---- (d) ----------------------------------------------------------------------------------------------------------

def test_d_the_bell_and_ever_flagged(world):
    code, out = run(world["db"])
    d = tail(out)["families"]["NFL"]["d"]
    assert d["evaluated"] == 8
    assert d["bell"] == {"book": 3, "kalshi": 1, "combined": 4}      # 1, 4, 5 by the book; 2 by Kalshi
    assert d["ever"] == {"book": 4, "kalshi": 1, "combined": 5}      # and 9, at 16:00 only
    assert d["book_flag_end"] == {"one-sided at from_at": 1, "one-sided at to_at": 1,
                                  "one-sided at neither end": 1}
    assert d["hidden_end"] == 1 and d["hidden_end_book_flagged"] == 1


def test_d_the_bell_is_line_move_for_match_at_kickoff_less_one_microsecond(world):
    from types import SimpleNamespace as NS

    from src.db.schema import Sport
    from src.walters import mlb_pitchers_gate as mp
    from src.walters.line_move import line_move_for_match
    code, out = run(world["db"])
    with mp.readonly_session(world["db"]) as s:
        lm = line_move_for_match(s, NS(id=1, utc_date=_dt(KO), sport=Sport.NFL), _dt(KO) - timedelta(microseconds=1))
    assert lm["venues"]["book"]["alarm"] is True
    assert lm["venues"]["book"]["from_at"] == "2026-11-20T12:00:00"


# ---- (e), scope -----------------------------------------------------------------------------------------------------

def test_e_months_are_new_york_months(world):
    code, out = run(world["db"])
    ncaa = tail(out)["families"]["NCAA"]
    assert set(ncaa["a"]["by_month"]) == {"2026-11"}            # 2026-12-01 00:30Z is the 30th in New York
    assert set(ncaa["b"]["by_month"]) == {"2026-11"}


def test_scope_counted_apart(world):
    code, out = run(world["db"])
    t = tail(out)
    assert t["apart"]["preseason"] == {"NFL": 1}
    assert t["apart"]["other_codes"] == {"UFL": 1}
    assert t["snapshot_rows_outside_sport_nfl"] == 1
    assert t["families"]["NFL"]["not_kicked_off_on_copy"] == 1
    assert any(ln.startswith("THE SECOND WRITER") for ln in out)


# ---- the fence --------------------------------------------------------------------------------------------------------

def test_no_book_name_and_no_price_is_printed(world):
    code, out = run(world["db"])
    text = "\n".join(out).replace(str(world["tmp"]), "<tmp>")
    for word in (SECRET_BOOK, "7.77777", "1.55", "2.85"):
        assert word not in text, word


def test_the_copy_is_unchanged_and_its_sha256_printed(world):
    before = hashlib.sha256(world["db"].read_bytes()).hexdigest()
    code, out = run(world["db"])
    assert code == 0
    assert hashlib.sha256(world["db"].read_bytes()).hexdigest() == before
    assert any(before in ln for ln in out)
    assert sorted(p.name for p in world["tmp"].iterdir()) == ["copy.db"]


def test_a_copy_under_a_data_directory_is_refused(tmp_path):
    for name in ("data", "DATA"):
        d = tmp_path / name
        d.mkdir()
        db = d / "copy.db"
        build_db(db)
        code, out = run(db)
        assert code == 2 and "under a directory named data" in out[-1]


def test_a_sidecar_is_refused(world):
    Path(str(world["db"]) + "-wal").write_bytes(b"")
    code, out = run(world["db"])
    assert code == 2 and "sidecar" in out[-1]


def test_a_missing_column_is_refused(tmp_path):
    db = tmp_path / "c.db"
    build_db(db)
    con = sqlite3.connect(str(db))
    con.execute("ALTER TABLE odds DROP COLUMN line")
    con.commit()
    con.close()
    code, out = run(db)
    assert code == 2 and "columns line not in odds (law 1)" in out[-1]


def test_no_bytecode_of_the_repo_is_written(world):
    cache = world["tmp"] / "pycache"
    cache.mkdir()
    res = subprocess.run([sys.executable, "-X", "pycache_prefix={}".format(cache), str(SCRIPT), "--db",
                          str(world["db"])], capture_output=True, text=True, cwd=str(world["tmp"]), timeout=180)
    assert res.returncode == 0, res.stdout + res.stderr
    own = cache.joinpath(*ROOT.parts[1:])
    assert [p for d in ("src", "scripts") for p in (own / d).rglob("*.pyc")] + list(own.glob("config*.pyc")) == []


def test_it_makes_no_network_call(world, monkeypatch):
    import socket

    def refuse(*a, **k):
        raise AssertionError("a network call")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    code, _out = run(world["db"])
    assert code == 0


def test_ever_flagged_trims_rows_after_each_stamp_with_the_same_result(world):
    """The rows after a stamp are dropped before line_move is called: the result equals the untrimmed call."""
    from sqlalchemy import select

    from src.db.database import attach_source_times
    from src.db.schema import OddsSnapshot
    from src.walters import mlb_pitchers_gate as mp
    from src.walters.kalshi_legs import guard_snaps
    from src.walters.line_move import line_move
    for mid in (1, 2, 4, 5, 9):
        with mp.readonly_session(world["db"]) as s:
            snaps = attach_source_times(s, s.execute(select(OddsSnapshot).where(
                OddsSnapshot.match_id == mid)).scalars())
            snaps, _ = guard_snaps(snaps, s)
            ko = _dt(KO)
            pairs = list(rc.ever_inputs(snaps, ko - timedelta(hours=3), ko))
            assert pairs
            for t, upto in pairs:
                assert line_move(upto, ko, t) == line_move(snaps, ko, t), (mid, t)
