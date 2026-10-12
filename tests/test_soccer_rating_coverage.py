"""ARCHITECT 2026-10-10, addendum 36 item 4: the read-only rating coverage receipt. Throwaway SQLite file."""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import soccer_rating_coverage as rc  # noqa: E402


def _db(tmp_path, production_rows=1, legacy=False):
    p = tmp_path / "rc.db"
    con = sqlite3.connect(p)
    con.executescript("""
        CREATE TABLE competitions (id INTEGER PRIMARY KEY, sport TEXT, code TEXT);
        CREATE TABLE teams (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE matches (id INTEGER PRIMARY KEY, competition_id INT, season TEXT, home_team_id INT,
                              away_team_id INT);
        CREATE TABLE model_versions (id INTEGER PRIMARY KEY, sport TEXT, model_family TEXT, version TEXT,
                                     status TEXT, parameters TEXT);
    """)
    con.execute("INSERT INTO competitions VALUES (1, 'SOCCER', 'PL'), (2, 'SOCCER', 'CZE'), (3, 'NFL', 'NFL')")
    con.executemany("INSERT INTO teams VALUES (?, ?)",
                    [(10, "Arsenal"), (11, "Leeds"), (12, "Ipswich"), (13, "Fulham"), (99, "Slavia")])
    con.executemany("INSERT INTO matches VALUES (?, ?, ?, ?, ?)",
                    [(1, 1, "2026/27", 10, 11), (2, 1, "2026/27", 13, 12), (3, 1, "2025/26", 99, 10),
                     (4, 2, "2026/27", 99, 12)])
    ratings = {"10": 1705.5, "12": 1544.9}           # Leeds and Fulham MISSING; Ipswich's id holds another club's
    t2l = {"10": "PL", "12": "CZE"}
    elo = {"ratings": ratings} if legacy else {"league": {"ratings": ratings}, "cup": {"ratings": {}}}
    for i in range(production_rows):
        con.execute("INSERT INTO model_versions VALUES (?, 'SOCCER', 'soccer_elo_poisson', ?, 'production', ?)",
                    (i + 1, f"v2{i}", json.dumps({"elo": elo, "team_to_league": t2l})))
    con.execute("INSERT INTO model_versions VALUES (9, 'SOCCER', 'soccer_elo_poisson', 'v9', 'candidate', '{}')")
    con.commit()
    con.close()
    return p


def test_each_team_its_rating_or_missing_and_its_team_to_league(tmp_path):
    con, form = rc.open_read(_db(tmp_path))
    c = rc.coverage(con, "PL", "2026/27")
    assert form == "mode=ro URI" and c["model_version"] == "v20"
    by = {r["name"]: r for r in c["rows"]}
    assert set(by) == {"Arsenal", "Leeds", "Ipswich", "Fulham"}            # this competition and season only
    assert (by["Arsenal"]["rating"], by["Arsenal"]["team_to_league"]) == (1705.5, "PL")
    assert by["Leeds"]["rating"] is None and by["Fulham"]["team_to_league"] is None
    assert (by["Ipswich"]["rating"], by["Ipswich"]["team_to_league"]) == (1544.9, "CZE")
    assert (c["teams"], c["in_table"], c["missing"]) == (4, 2, 2)
    assert (c["league_matches"], c["league_other"], c["league_absent"]) == (1, 1, 2)
    lines = []
    rc.report(c, echo=lines.append)
    assert any("Leeds" in x and "MISSING" in x for x in lines)
    assert any(x.startswith("TOTALS teams 4 · in the table 2 · MISSING 2") for x in lines)


def test_the_legacy_single_state_shape_is_read_as_training_reads_it(tmp_path):
    con, _ = rc.open_read(_db(tmp_path, legacy=True))
    assert rc.coverage(con, "PL", "2026/27")["in_table"] == 2


def test_not_exactly_one_production_row_refuses(tmp_path):
    for n in (0, 2):
        d = tmp_path / str(n)
        d.mkdir()
        assert rc.main(["--competition", "PL", "--season", "2026/27", "--db", str(_db(d, production_rows=n))]) == 2


def test_read_only_the_file_is_unchanged(tmp_path):
    p = _db(tmp_path)
    before = p.read_bytes()
    assert rc.main(["--competition", "PL", "--season", "2026/27", "--db", str(p)]) == 0
    assert p.read_bytes() == before


def test_a_match_side_id_without_a_team_row_stays_visible(tmp_path):
    p = _db(tmp_path)
    con = sqlite3.connect(p)
    con.execute("INSERT INTO matches VALUES (9, 1, '2026/27', 10, 77)")       # 77: no team row
    con.commit()
    con.close()
    con, _ = rc.open_read(p)
    c = rc.coverage(con, "PL", "2026/27")
    row = next(r for r in c["rows"] if r["id"] == 77)
    assert row["name"] == "(no team row)" and row["rating"] is None and c["teams"] == 5


# ---- #422 item 5 and #421 ----------------------------------------------------------------------------------------

def test_422_5_the_competition_is_looked_up_as_soccer_and_an_unplaceable_code_refuses(tmp_path, capsys):
    p = _db(tmp_path)
    assert rc.main(["--competition", "NFL", "--season", "2026", "--db", str(p)]) == 2       # not soccer
    assert "REFUSED: 0 soccer competitions with code NFL" in capsys.readouterr().out
    con = sqlite3.connect(p)
    con.execute("INSERT INTO competitions VALUES (4, 'soccer', 'PL')")                    # a second PL row
    con.commit()
    con.close()
    assert rc.main(["--competition", "PL", "--season", "2026/27", "--db", str(p)]) == 2
    assert "REFUSED: 2 soccer competitions with code PL" in capsys.readouterr().out


def test_421_a_copy_that_refuses_mode_ro_opens_query_only_and_a_write_fails(tmp_path, monkeypatch):
    p = _db(tmp_path)
    real = sqlite3.connect

    def refuse_uri(path, *a, **k):
        if k.get("uri"):
            raise sqlite3.OperationalError("unable to open database file")
        return real(path, *a, **k)
    monkeypatch.setattr(rc.sqlite3, "connect", refuse_uri)
    con, form = rc.open_read(p)
    assert form == "plain path with PRAGMA query_only = ON (mode=ro refused)"
    import pytest
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        con.execute("DELETE FROM model_versions")
    assert rc.coverage(con, "PL", "2026/27")["teams"] == 4                                # reads still work
