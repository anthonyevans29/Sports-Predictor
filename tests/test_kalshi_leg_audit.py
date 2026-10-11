"""ARCHITECT 2026-10-10, addendum 37 item 4: the read-only Kalshi leg audit. A throwaway SQLite file with the
tables it reads (minimal columns), never the app DB."""
import sqlite3

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import kalshi_leg_audit as la  # noqa: E402

P = "KXNCAAFGAME-26OCT10"


def _db(tmp_path, ticker_column=True):
    p = tmp_path / "audit.db"
    con = sqlite3.connect(p)
    con.executescript("""
        CREATE TABLE teams (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE matches (id INTEGER PRIMARY KEY, utc_date TEXT, home_team_id INT, away_team_id INT);
        CREATE TABLE predictions (id INTEGER PRIMARY KEY, match_id INT);
        CREATE TABLE prediction_outcomes (id INTEGER PRIMARY KEY, prediction_id INT);
    """)
    con.execute("CREATE TABLE odds_snapshots (id INTEGER PRIMARY KEY, match_id INT, selection TEXT, source TEXT, "
                "captured_at TEXT" + (", market_ticker TEXT)" if ticker_column else ")"))
    teams = ["Northern Iowa", "North Dakota", "UNLV", "North Dakota State", "Boston College", "Stanford",
             "Tulane", "Rice"]
    con.executemany("INSERT INTO teams VALUES (?, ?)", list(enumerate(teams, 1)))
    con.executemany("INSERT INTO matches VALUES (?, ?, ?, ?)", [
        (32812, "2026-10-10 21:00:00.000000", 1, 2), (32820, "2026-10-10 23:00:00.000000", 3, 4),
        (40, "2026-10-10 19:00:00.000000", 5, 6), (41, "2026-10-10 18:00:00.000000", 7, 8)])
    snaps = [  # (match, selection, captured_at, ticker)
        (32812, "HOME", "2026-10-08 21:56:38.000000", f"{P}UNDUNI-UNI"),
        (32812, "AWAY", "2026-10-08 21:56:38.000000", f"{P}NDSUUNLV-NDSU"),
        (32820, "HOME", "2026-10-09 22:09:52.000000", f"{P}NDSUUNLV-UNLV"),
        (32812, "AWAY", "2026-10-09 22:09:52.000000", f"{P}NDSUUNLV-NDSU"),
        (40, "HOME", "2026-10-09 22:09:52.000000", f"{P}STANBC-BC"),
        (40, "AWAY", "2026-10-09 22:09:52.000000", f"{P}STANBC-STAN"),
        (41, "HOME", "2026-10-09 22:09:52.000000", None),
        (41, "AWAY", "2026-10-09 22:09:52.000000", None),
    ]
    for i, (mid, sel, cap, tic) in enumerate(snaps, 1):
        if ticker_column:
            con.execute("INSERT INTO odds_snapshots VALUES (?, ?, ?, 'kalshi', ?, ?)", (i, mid, sel, cap, tic))
        else:
            con.execute("INSERT INTO odds_snapshots VALUES (?, ?, ?, 'kalshi', ?)", (i, mid, sel, cap))
    con.execute("INSERT INTO predictions VALUES (1, 32812)")
    con.execute("INSERT INTO prediction_outcomes VALUES (1, 1)")
    con.commit()
    con.close()
    return p


def test_two_event_games_and_split_events_by_series_and_day(tmp_path):
    con, form = la.open_read(_db(tmp_path))
    r = la.audit(con)
    assert form == "mode=ro URI"
    assert [(g["match_id"], g["day"]) for g in r["two_event_games"]] == [(32812, "2026-10-08")]
    assert sorted(r["two_event_games"][0]["legs"]) == [f"{P}NDSUUNLV", f"{P}UNDUNI"]
    assert [(e["event"], e["day"], [g["match_id"] for g in e["games"]]) for e in r["split_events"]] == \
        [(f"{P}NDSUUNLV", "2026-10-09", [32812, 32820])]
    assert r["first_day"] == {"KXNCAAFGAME": "2026-10-08"}
    assert [g["match_id"] for g in r["graded"]] == [32812]
    assert (r["kalshi_snapshots"], r["tickered"], r["untickered"]) == (8, 6, 2)
    lines = []
    la.report(r, echo=lines.append)
    assert lines[-1].strip() == "KALSHI-LEG-AUDIT two_event_games=1 split_events=1 graded=1 untickered=2 tickered=6 orphans=0"
    assert any("32812 North Dakota @ Northern Iowa" in x for x in lines)


def test_since_and_the_clean_and_untickered_games_are_never_listed(tmp_path):
    con, _ = la.open_read(_db(tmp_path))
    r = la.audit(con, since="2026-10-09")
    assert r["two_event_games"] == [] and len(r["split_events"]) == 1
    listed = {g["match_id"] for e in r["split_events"] for g in e["games"]}
    assert 40 not in listed and 41 not in listed


def test_before_the_ticker_column_nothing_can_be_checked_and_it_says_so(tmp_path):
    con, _ = la.open_read(_db(tmp_path, ticker_column=False))
    r = la.audit(con)
    assert r["ticker_column"] is False and r["untickered"] == 8
    lines = []
    la.report(r, echo=lines.append)
    assert any("does not exist" in x for x in lines)
    assert lines[-1].strip() == ("KALSHI-LEG-AUDIT two_event_games=0 split_events=0 graded=0 untickered=8 "
                                 "tickered=0 orphans=0 ticker_column=absent")


def test_read_only_the_file_is_unchanged(tmp_path):
    p = _db(tmp_path)
    before = p.read_bytes()
    assert la.main(["--db", str(p)]) == 0
    assert p.read_bytes() == before


# ---- #419 (Codex on #416) and #421 ------------------------------------------------------------------------------

def test_orphan_snapshots_are_counted_on_their_own_line_not_as_tickered(tmp_path, capsys):
    p = _db(tmp_path)
    con = sqlite3.connect(p)
    con.execute("INSERT INTO odds_snapshots VALUES (99, 7777, 'HOME', 'kalshi', '2026-10-09 22:09:52.000000', "
                "'KXNCAAFGAME-26OCT10GONE-X')")                       # its match row is gone
    con.commit()
    con.close()
    c, _ = la.open_read(p)
    r = la.audit(c)
    assert (r["kalshi_snapshots"], r["tickered"], r["untickered"], r["orphans"]) == (9, 6, 2, 1)       # #438: the tickered orphan is not tickered
    la.report(r)
    out = capsys.readouterr().out
    assert "with no match row (orphans; their legs are not placed on any game): 1" in out
    assert out.strip().splitlines()[-1].endswith("orphans=1")


@pytest.mark.parametrize("bad", ["2026-10-1", "garbage", "2026-13-01", "10/09/2026"])
def test_a_malformed_since_refuses_exit_2(tmp_path, bad, capsys):
    assert la.main(["--db", str(_db(tmp_path)), "--since", bad]) == 2
    assert "REFUSED: --since" in capsys.readouterr().out


def test_a_graded_query_that_fails_is_not_checked_and_exits_nonzero(tmp_path, capsys):
    p = _db(tmp_path)
    con = sqlite3.connect(p)
    con.execute("DROP TABLE prediction_outcomes")
    con.commit()
    con.close()
    assert la.main(["--db", str(p)]) == 1
    out = capsys.readouterr().out
    assert "LISTED GAMES WITH A GRADED PREDICTION: NOT CHECKED (OperationalError" in out
    assert "graded=NOT_CHECKED" in out.strip().splitlines()[-1]


def test_421_a_copy_that_refuses_mode_ro_opens_query_only_and_a_write_fails(tmp_path, monkeypatch):
    p = _db(tmp_path)
    real = sqlite3.connect

    def refuse_uri(path, *a, **k):
        if k.get("uri"):
            raise sqlite3.OperationalError("unable to open database file")
        return real(path, *a, **k)
    monkeypatch.setattr(la.sqlite3, "connect", refuse_uri)
    con, form = la.open_read(p)
    assert form == "plain path with PRAGMA query_only = ON (mode=ro refused)"
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        con.execute("DELETE FROM odds_snapshots")
