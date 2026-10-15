"""THE REPLAY INVENTORY (ARCHITECT 2026-10-15, addendum 79 item 3; #75): what the DB can replay, per sport, for the
graded games since 2026-09-20. A throwaway SQLite built here (never data/); predictions are inserted through Core so
the after_flush history hook adds nothing the test did not write."""
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, insert
from sqlalchemy.orm import Session

import scripts.replay_inventory_probe as rip
from src.db.schema import (Base, Competition, KalshiSettledMarket, Match, MatchStatus, Odds, OddsSnapshot, Prediction,
                           PredictionHistory, PredictionOutcome, Sport, Team)

K = {i: datetime(2026, 10, i, 18, 0) for i in range(1, 12)}
H = lambda h: timedelta(hours=h)          # noqa: E731


def build(path: Path) -> dict:
    """1 NFL all four (a current row 2h before, history 50h/26h/2h before + one after, book sessions 48h/24h/1h before
    + one after, kalshi 30h/0.5h before, a board row, a closing file); 2 NFL current row computed 1h AFTER kickoff, book
    3h before only; 3 NFL scheduled; 4 NFL finished before since; 5 NCAA (sport NFL) no prediction, a NULL-source book
    session, kalshi; 6 PL current row + outcome, api_football 1X2 and kalshi 1X2 (source tells them apart), closing
    via predictions[]; 7 MLB TOTALS rows only (never book), kalshi ML, a settled-market row; 8 NHL finished, no
    scores."""
    eng = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(eng)
    ids = {}
    with Session(eng) as s:
        comps = {c: Competition(sport=sp, code=c, name=c, area="X", type="LEAGUE") for c, sp in
                 [("NFL", Sport.NFL), ("NCAA", Sport.NFL), ("PL", Sport.SOCCER), ("MLB", Sport.MLB), ("NHL", Sport.NHL)]}
        s.add_all(comps.values())
        s.flush()

        def m(n, code, ko, status=MatchStatus.FINISHED, scores=(1, 0)):
            sp = comps[code].sport
            h, a = Team(sport=sp, name=f"H{n}"), Team(sport=sp, name=f"A{n}")
            s.add_all([h, a])
            s.flush()
            x = Match(sport=sp, competition_id=comps[code].id, season="2026", utc_date=ko, status=status,
                      home_team_id=h.id, away_team_id=a.id, home_score=scores[0], away_score=scores[1])
            s.add(x)
            s.flush()
            ids[n] = x.id
            return x.id

        def pred(mid, at):
            return s.execute(insert(Prediction.__table__).values(
                match_id=mid, model_version="v", computed_at=at, home_win_prob=0.5, away_win_prob=0.5)).inserted_primary_key[0]

        def hist(mid, at):
            s.add(PredictionHistory(match_id=mid, model_version="v", computed_at=at, home_win_prob=0.5,
                                    away_win_prob=0.5))

        def snap(mid, at, source, market="1X2", sels=("HOME", "AWAY")):
            for sel in sels:
                s.add(OddsSnapshot(match_id=mid, market=market, selection=sel, devig_prob=0.5, line=None, n_books=2,
                                   captured_at=at, source=source))

        g1 = m(1, "NFL", K[1])
        pred(g1, K[1] - H(2))
        for h in (50, 26, 2, -1):
            hist(g1, K[1] - H(h))
        for h in (48, 24, 1, -0.5):
            snap(g1, K[1] - H(h), "api_american_football")
        for h in (30, 0.5):
            snap(g1, K[1] - H(h), "kalshi", market="ML")
        s.add(Odds(match_id=g1, bookmaker="b", market="1X2", selection="HOME", price_decimal=2.0,
                   captured_at=K[1] - H(1), source="api_american_football"))
        g2 = m(2, "NFL", K[2])
        pred(g2, K[2] + H(1))
        snap(g2, K[2] - H(3), "api_american_football")
        m(3, "NFL", K[3], status=MatchStatus.SCHEDULED, scores=(None, None))
        m(4, "NFL", datetime(2026, 9, 10, 18, 0))
        g5 = m(5, "NCAA", K[5])
        snap(g5, K[5] - H(5), None)
        snap(g5, K[5] - H(4), "kalshi", market="ML")
        g6 = m(6, "PL", K[6], scores=(1, 1))
        p6 = pred(g6, K[6] - H(3))
        s.add(PredictionOutcome(prediction_id=p6))
        snap(g6, K[6] - H(6), "api_football", sels=("HOME", "DRAW", "AWAY"))
        snap(g6, K[6] - H(2), "kalshi", sels=("HOME", "DRAW", "AWAY"))
        g7 = m(7, "MLB", K[7])
        snap(g7, K[7] - H(4), "api_baseball", market="TOTALS")
        snap(g7, K[7] - H(1), "kalshi", market="ML")
        s.add(KalshiSettledMarket(ticker="KXMLBGAME-X-H", series="KXMLBGAME", side="HOME", match_id=g7,
                                  source="historical", fetched_at=K[9]))
        m(8, "NHL", K[8], scores=(None, None))
        s.commit()
    eng.dispose()
    return ids


@pytest.fixture
def world(tmp_path):
    db = tmp_path / "throwaway.db"
    ids = build(db)
    ex = tmp_path / "exports"
    (ex / "host").mkdir(parents=True)
    (ex / "closing_NFL_2026-10-01T1800Z.json").write_text(json.dumps(
        {"predictions": [{"match_id": ids[1]}], "closing": {"family": "NFL", "match_ids": [ids[1]]}}))
    (ex / "closing_SOCCER_2026-10-06T1800Z.json").write_text(json.dumps({"predictions": [{"match_id": ids[6]}]}))
    (ex / "closing_MLB_bad.json").write_text("{not json")
    (ex / "host" / "closing_NFL_2026-10-02T1800Z.json").write_text(json.dumps({"closing": {"match_ids": [ids[2]]}}))
    return db, ex, ids


def run(world, capsys, *extra):
    db, ex, _ = world
    assert rip.main(["--db", str(db), "--exports", str(ex), "--until", "2026-10-12", *extra]) == 0
    return capsys.readouterr().out.splitlines()


def block(out, name):
    i = out.index(next(o for o in out if o.startswith(f"{name}: graded")))
    j = next((k for k in range(i + 1, len(out)) if not out[k].startswith("  ")), len(out))
    return out[i:j]


def test_the_header_names_the_keys_the_schema_and_the_closing_files(world, capsys):
    out = run(world, capsys)
    assert out[0].startswith("REPLAY INVENTORY PROBE (ARCHITECT 2026-10-15, addendum 79 item 3; #75): read-only · "
                             "mode=ro URI · graded games with kickoff in [2026-09-20, 2026-10-12) UTC: 5")
    assert out[1].startswith("keys: graded = matches.status FINISHED with home_score and away_score")
    assert "predictions is CURRENT-ONLY per match" in out[2] and "prediction_history is APPEND-ONLY" in out[2]
    assert "prediction_history here: 4 rows, first computed_at 2026-09-29 16:00 UTC" in out[2]
    assert out[3].endswith("closing_*.json 3 files, 2 match ids, unreadable 1 (closing_MLB_bad.json) · "
                           f"{world[1]}/host/closing_*.json 1 files, not matched (the host's match ids are its own)")
    assert [o.split(":")[0] for o in out if not o.startswith((" ", "REPLAY", "keys", "schema", "closing"))] == \
        ["MLB", "NCAA", "NFL", "SOCCER PL"]


def test_nfl_counts_versions_captures_and_all_four(world, capsys):
    b = block(run(world, capsys), "NFL")
    assert b[0] == "NFL: graded 2"                         # 3 is scheduled, 4 is before since
    assert b[1] == ("  stored prediction before kickoff: current row 1 · history 1 · either 1 · current row computed "
                    "at/after kickoff 1 · versions per game (history rows before kickoff) 3/3/3 (min/median/max over 1 "
                    "games) · games with a prediction_outcomes row 0")
    assert b[2] == ("  book history before kickoff: 2 games (2 with a complete session) · sessions per game 1/2/3 · first "
                    "capture 3.0/25.5/48.0h before kickoff · last capture 1.0/2.0/3.0h before kickoff (min/median/max) · "
                    "earliest 2026-09-29 18:00 UTC")
    assert b[3] == "    of it: odds_snapshots 2 games · the odds table 1 games (0 in the odds table only)"
    assert b[4] == ("  kalshi snapshots before kickoff: 1 games (1 with a complete session) · sessions per game 2/2/2 · "
                    "first capture 30.0/30.0/30.0h before kickoff · last capture 0.5/0.5/0.5h before kickoff "
                    "(min/median/max) · earliest 2026-09-30 12:00 UTC · mismatched legs, never read (addendum 37 item "
                    "3): 0 games")
    assert b[5] == "  kalshi_settled_markets rows: 0 games"
    assert b[6].endswith("/, by match id): 1 games")
    assert b[7] == "  all four (a stored prediction + book history + kalshi history + a closing file): 1"


def test_ncaa_rides_sport_nfl_and_a_null_source_is_book(world, capsys):
    b = block(run(world, capsys), "NCAA")
    assert b[0] == "NCAA: graded 1" and "current row 0 · history 0 · either 0" in b[1]
    assert b[2].startswith("  book history before kickoff: 1 games (1 with a complete session) · sessions per game 1/1/1 · "
                           "first capture 5.0/5.0/5.0h")
    assert b[4].startswith("  kalshi snapshots before kickoff: 1 games")
    assert b[7].endswith(": 0")


def test_soccer_splits_book_from_kalshi_by_source_and_reads_a_closing_file_by_its_rows(world, capsys):
    b = block(run(world, capsys), "SOCCER PL")
    assert "current row 1 · history 0 · either 1 · current row computed at/after kickoff 0" in b[1]
    assert b[1].endswith("games with a prediction_outcomes row 1")
    # the kalshi 1X2 session at 2h never reads as book (source alone tells them apart in soccer): one book session
    assert "sessions per game 1/1/1 · first capture 6.0/6.0/6.0h before kickoff · last capture 6.0/6.0/6.0h" in b[2]
    assert "first capture 2.0/2.0/2.0h" in b[4]
    assert b[6].endswith("/, by match id): 1 games") and b[7].endswith(": 1")


def test_mlb_totals_are_never_book_and_settled_markets_are_counted(world, capsys):
    b = block(run(world, capsys), "MLB")
    assert b[2] == "  book history before kickoff: 0 games"
    assert b[4].startswith("  kalshi snapshots before kickoff: 1 games")
    assert b[5] == "  kalshi_settled_markets rows: 1 games" and b[7].endswith(": 0")


def test_the_json_line_and_a_since_window(world, capsys):
    out = run(world, capsys, "--since", "2026-10-05")
    js = json.loads(out[-1].removeprefix("REPLAY-INVENTORY "))
    assert js["games"] == 3 and set(js["groups"]) == {"MLB", "NCAA", "SOCCER PL"}
    assert js["groups"]["SOCCER PL"]["all_four"] == 1 and js["closing_files"] == 3 and js["host_closing_files"] == 1
    assert js["groups"]["MLB"]["kalshi"] == {"games": 1, "complete": 1, "earliest": "2026-10-07 17:00"}


def test_an_older_database_without_the_newer_tables_says_so(world, capsys, tmp_path):
    import sqlite3
    db = world[0]
    con = sqlite3.connect(db)
    con.execute("DROP TABLE prediction_history")
    con.execute("DROP TABLE kalshi_settled_markets")
    con.commit()
    con.close()
    out = run(world, capsys)
    assert "prediction_history: NO such table in this database" in out[2]
    assert "  kalshi_settled_markets rows: NO such table in this database" in out
    assert "history 0" in block(out, "NFL")[1]


def test_the_probe_never_creates_a_database_and_writes_nothing(tmp_path, world):
    missing = tmp_path / "none.db"
    with pytest.raises(SystemExit, match="never creates one"):
        rip.main(["--db", str(missing)])
    assert not missing.exists()
    db = world[0]
    before = db.stat().st_mtime_ns, db.stat().st_size
    rip.main(["--db", str(db), "--exports", str(world[1]), "--until", "2026-10-12"])
    assert (db.stat().st_mtime_ns, db.stat().st_size) == before
    assert sorted(p.name for p in db.parent.iterdir() if p.name.startswith("throwaway")) == ["throwaway.db"]


def test_pre_167_soccer_book_history_lives_in_the_odds_table(tmp_path, capsys):
    """Before #167 (2026-10-01) the soccer sync APPENDED a full book set to the odds table on every run and wrote no
    snapshot; a finished game's rows are never deleted. Those games' book history is the odds table's: read, with its
    sessions and ages, and said to be the odds table's only."""
    db = tmp_path / "legacy.db"
    eng = create_engine(f"sqlite:///{db}")
    Base.metadata.create_all(eng)
    ko = datetime(2026, 9, 27, 14, 0)
    with Session(eng) as s:
        comp = Competition(sport=Sport.SOCCER, code="PL", name="PL", area="X", type="LEAGUE")
        h, a = Team(sport=Sport.SOCCER, name="H"), Team(sport=Sport.SOCCER, name="A")
        s.add_all([comp, h, a])
        s.flush()
        m = Match(sport=Sport.SOCCER, competition_id=comp.id, season="2026/27", utc_date=ko,
                  status=MatchStatus.FINISHED, home_team_id=h.id, away_team_id=a.id, home_score=2, away_score=1)
        s.add(m)
        s.flush()
        for hrs in (30, 20, 10, 2, 1):
            for bk in ("b1", "b2"):
                for sel in ("HOME", "DRAW", "AWAY"):
                    s.add(Odds(match_id=m.id, bookmaker=bk, market="1X2", selection=sel, price_decimal=3.0,
                               captured_at=ko - H(hrs), source="api_football"))
        s.add(Odds(match_id=m.id, bookmaker="fdcuk_close", market="1X2", selection="HOME", price_decimal=2.0,
                   captured_at=ko - H(40), is_closing=True, source="football-data-uk:2026-27"))  # never a session
        s.commit()
    eng.dispose()
    assert rip.main(["--db", str(db), "--exports", str(tmp_path / "none"), "--until", "2026-10-12"]) == 0
    b = block(capsys.readouterr().out.splitlines(), "SOCCER PL")
    assert b[2].startswith("  book history before kickoff: 1 games (1 with a complete session) · sessions per game 5/5/5 · "
                           "first capture 30.0/30.0/30.0h before kickoff · last capture 1.0/1.0/1.0h")
    assert b[3] == "    of it: odds_snapshots 0 games · the odds table 1 games (1 in the odds table only)"


def test_mismatched_kalshi_legs_are_never_read_as_kalshi_history(world, capsys):
    """Addendum 37 item 3: legs whose event sits on another game are read by no reader. The two NCAA games below carry
    the same event's legs (the market_ticker column added as migrate_kalshi_ticker.py adds it): neither counts as
    Kalshi history, both are counted apart, and neither reaches all four."""
    import sqlite3
    db, _, ids = world
    con = sqlite3.connect(db)
    con.execute("ALTER TABLE odds_snapshots ADD COLUMN market_ticker VARCHAR(128)")
    mid = con.execute("SELECT id FROM matches WHERE id = ?", (ids[5],)).fetchone()[0]
    con.execute("UPDATE odds_snapshots SET market_ticker = 'KXNCAAFGAME-26OCT05AB-' || selection "
                "WHERE source = 'kalshi' AND match_id = ?", (mid,))
    for sel in ("HOME", "AWAY"):           # the same event's legs on the NFL game 2 as well
        con.execute("INSERT INTO odds_snapshots (match_id, market, selection, devig_prob, n_books, captured_at, source, "
                    "market_ticker) VALUES (?, 'ML', ?, 0.5, 1, ?, 'kalshi', ?)",
                    (ids[2], sel, str(K[2] - H(2)), f"KXNCAAFGAME-26OCT05AB-{sel}"))
    con.commit()
    con.close()
    out = run(world, capsys)
    ncaa, nfl = block(out, "NCAA"), block(out, "NFL")
    assert ncaa[4] == ("  kalshi snapshots before kickoff: 0 games · mismatched legs, never read (addendum 37 item 3): "
                       "1 games")
    assert nfl[4].startswith("  kalshi snapshots before kickoff: 1 games") and nfl[4].endswith(": 1 games")
    assert "market_ticker: NOT in this database" not in out[2]


def test_an_incomplete_session_is_counted_but_never_complete(world, capsys):
    """A soccer Kalshi session missing its DRAW leg is a capture, never a price (close.py's rule): the game counts as
    having Kalshi snapshots, and not as having a complete session."""
    import sqlite3
    db, _, ids = world
    con = sqlite3.connect(db)
    con.execute("DELETE FROM odds_snapshots WHERE source = 'kalshi' AND match_id = ? AND selection = 'DRAW'", (ids[6],))
    con.commit()
    con.close()
    b = block(run(world, capsys), "SOCCER PL")
    assert b[4].startswith("  kalshi snapshots before kickoff: 1 games (0 with a complete session)")


def test_the_fallback_open_is_query_only(world, monkeypatch):
    """#421: a copy that refuses mode=ro is opened by its plain path with PRAGMA query_only = ON: a write refuses."""
    import sqlite3
    real = sqlite3.connect

    def refuse_uri(target, *a, **kw):
        if kw.get("uri"):
            raise sqlite3.OperationalError("unable to open database file")
        return real(target, *a, **kw)
    monkeypatch.setattr(rip.sqlite3, "connect", refuse_uri)
    con, form = rip.open_read(world[0])
    try:
        assert form == "plain path with PRAGMA query_only = ON (mode=ro refused)"
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            con.execute("CREATE TABLE x (i INTEGER)")
    finally:
        con.close()
