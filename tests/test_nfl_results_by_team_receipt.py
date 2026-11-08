"""ADDENDUM 295 ITEM 5(d) (ARCHITECT 2026-11-08 10:05 ET; #885), verbatim: "A READ-ONLY receipt script (no write): NFL
2026 FINISHED rows' scores by team against the nflverse results feed #841 already pulls daily (unmetered) — the
mismatch list, printed, is the check I declined to buy with metered calls in 292 item 3(h)."

Synthetic throughout: a stored NFL season in its own SQLite file under tmp_path (never the app's database, never under
data/) and a games file in nflverse's schedules header (read 2026-11-08 from the release file); no network."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from scripts import nfl_results_by_team_receipt as R

HEADER = ("game_id,season,game_type,week,gameday,weekday,gametime,away_team,away_score,home_team,home_score,location,"
          "result,total,overtime,old_game_id,gsis,nfl_detail_id,pfr,pff,espn,ftn,away_rest,home_rest,away_moneyline,"
          "home_moneyline,spread_line,away_spread_odds,home_spread_odds,total_line,under_odds,over_odds,div_game,roof,"
          "surface,temp,wind,away_qb_id,home_qb_id,away_qb_name,home_qb_name,away_coach,home_coach,referee,"
          "stadium_id,stadium")
CODES = ("SEA", "NE", "LA", "SF", "KC", "BUF", "DAL", "BAL", "DUP1", "DUP2")


def _games(tmp_path, rows) -> Path:
    cols = HEADER.split(",")
    lines = [HEADER]
    for r in rows:
        lines.append(",".join(str(r.get(c, "")) for c in cols))
    p = tmp_path / "games.csv"
    p.write_text("\n".join(lines) + "\n")
    return p


def g(gid, day, away, as_, home, hs, location="Home", season=2026):
    return {"game_id": gid, "season": season, "game_type": "REG", "gameday": day, "gametime": "20:20",
            "away_team": away, "away_score": as_, "home_team": home, "home_score": hs, "location": location}


def _copy(tmp_path) -> tuple[Path, dict]:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from src.db.schema import Base, Competition, CompetitionTeam, Match, MatchStatus, Sport, Team
    path = tmp_path / "copy.db"
    eng = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(eng)
    ids = {}
    with Session(eng) as s:
        comp = Competition(sport=Sport.NFL, code="NFL", name="NFL", area="USA", type="LEAGUE")
        ts = {c: Team(sport=Sport.NFL, name=f"Synthetic {c}", tla=c.replace("DUP1", "DUP").replace("DUP2", "DUP"))
              for c in CODES}
        s.add_all([comp, *ts.values()])
        s.flush()
        s.add_all([CompetitionTeam(competition_id=comp.id, team_id=t.id, season="2026") for t in ts.values()])

        def m(key, home, away, when, hs, as_, st=MatchStatus.FINISHED, season="2026"):
            row = Match(sport=Sport.NFL, competition_id=comp.id, season=season, utc_date=when, status=st,
                        home_team_id=ts[home].id, away_team_id=ts[away].id, home_score=hs, away_score=as_)
            s.add(row)
            s.flush()
            ids[key] = row.id
        m("agree", "SEA", "NE", datetime(2026, 9, 10, 0, 20), 13, 10)        # Wed 20:20 ET = Thu 00:20Z
        m("rev_ok", "SF", "LA", datetime(2026, 9, 11, 0, 35), 27, 7)         # nflverse lists LA home (Neutral)
        m("rev_bad", "KC", "BUF", datetime(2026, 9, 14, 17, 0), 31, 20)      # reversed AND positional: wrong
        m("bad", "DAL", "BAL", datetime(2026, 9, 27, 20, 25), 34, 31)        # same pair, scores disagree
        m("null", "SEA", "SF", datetime(2026, 10, 4, 17, 0), None, 21)
        m("unmapped", "DUP1", "SEA", datetime(2026, 10, 11, 17, 0), 3, 0)
        m("absent", "NE", "KC", datetime(2026, 10, 18, 17, 0), 1, 2)
        m("unscored", "BUF", "DAL", datetime(2026, 10, 25, 17, 0), 9, 9)
        m("sched", "LA", "NE", datetime(2026, 11, 20, 18, 0), None, None, st=MatchStatus.SCHEDULED)
        m("old", "SEA", "NE", datetime(2025, 9, 10, 0, 20), 1, 0, season="2025")
        s.commit()
    eng.dispose()
    return path, ids


ROWS = [g("2026_01_NE_SEA", "2026-09-09", "NE", 10, "SEA", 13),
        g("2026_01_SF_LA", "2026-09-10", "SF", 27, "LA", 7, "Neutral"),
        g("2026_01_KC_BUF", "2026-09-14", "KC", 20, "BUF", 31),          # nflverse: KC away 20, BUF home 31
        g("2026_03_BAL_DAL", "2026-09-27", "BAL", 34, "DAL", 31, "Neutral"),
        g("2026_04_SF_SEA", "2026-10-04", "SF", 21, "SEA", 17),
        g("2026_07_DAL_BUF", "2026-10-25", "DAL", "", "BUF", ""),
        g("2026_08_X_Y", "2026-11-01", "LA", 3, "KC", 9),                  # in the file, no stored row
        g("2025_01_NE_SEA", "2025-09-10", "NE", 0, "SEA", 1, season=2025)]


def test_the_mismatch_list_compares_by_team_and_prints_both_sides(tmp_path, capsys):
    path, ids = _copy(tmp_path)
    code = R.main(["--db", str(path), "--games-file", str(_games(tmp_path, ROWS))])
    out = capsys.readouterr().out.splitlines()
    assert code == R.MISMATCHED
    tail = json.loads(out[-1].split(" ", 1)[1])
    assert out[-1].startswith(R.TAIL + " ")
    assert tail["mismatch"] == [ids["rev_bad"], ids["bad"], ids["null"]]
    assert tail["reversed_ids"] == [ids["rev_ok"], ids["rev_bad"]]
    assert (tail["compared"], tail["same"], tail["reversed"]) == (5, 3, 2)
    assert tail["unmapped"] == [ids["unmapped"]] and tail["not_in_file"] == [ids["absent"]]
    assert tail["unscored"] == [ids["unscored"]] and tail["stored_finished"] == 8 and tail["file_games"] == 7
    assert tail["file_unpaired"] == 1 and tail["exit"] == R.MISMATCHED
    text = "\n".join(out)
    assert (f"  ✗ match {ids['rev_bad']} (reversed, nflverse location Home): ours BUF 20 @ KC 31 · nflverse "
            "2026_01_KC_BUF KC 20 @ BUF 31") in out
    assert f"  ✗ match {ids['bad']} (same, nflverse location Neutral): ours BAL 31 @ DAL 34" in text
    assert f"  ↔ match {ids['rev_ok']} (agrees by team, nflverse location Neutral)" in text
    assert "team codes held by more than one NFL team (unmapped, never a guess): DUP" in text


def test_no_mismatch_exits_0(tmp_path, capsys):
    path, _ids = _copy(tmp_path)
    rows = [r for r in ROWS if r["game_id"] in ("2026_01_NE_SEA", "2026_01_SF_LA")]
    assert R.main(["--db", str(path), "--games-file", str(_games(tmp_path, rows))]) in (R.OK,)
    assert "MISMATCH LIST (0)" in capsys.readouterr().out


def test_two_games_of_the_pair_within_a_day_are_ambiguous_never_compared(tmp_path, capsys):
    path, ids = _copy(tmp_path)
    rows = [g("A", "2026-09-09", "NE", 10, "SEA", 13), g("B", "2026-09-10", "SEA", 1, "NE", 2)]
    R.main(["--db", str(path), "--games-file", str(_games(tmp_path, rows))])
    tail = json.loads(capsys.readouterr().out.splitlines()[-1].split(" ", 1)[1])
    assert tail["ambiguous"] == [ids["agree"]] and ids["agree"] not in tail["mismatch"]


def test_a_file_without_a_column_is_refused_and_nothing_compared(tmp_path, capsys):
    path, _ids = _copy(tmp_path)
    bad = tmp_path / "bad.csv"
    bad.write_text("game_id,season,home_team,away_team\nx,2026,SEA,NE\n")
    assert R.main(["--db", str(path), "--games-file", str(bad)]) == R.REFUSED
    out = capsys.readouterr().out
    assert "REFUSED: --games-file" in out and "lacks game_type, gameday" in out and "nothing compared" in out


def test_a_copy_with_a_sidecar_or_no_copy_is_refused(tmp_path, capsys):
    path, _ids = _copy(tmp_path)
    games = _games(tmp_path, ROWS)
    side = path.with_name(path.name + "-wal")
    side.write_text("")
    assert R.main(["--db", str(path), "--games-file", str(games)]) == R.REFUSED
    side.unlink()
    assert R.main(["--db", "", "--games-file", str(games)]) == R.REFUSED
    assert R.main(["--db", str(tmp_path / "missing.db"), "--games-file", str(games)]) == R.REFUSED
    assert R.main(["--db", str(path)]) == R.REFUSED
    assert capsys.readouterr().out.count("REFUSED:") == 4


def test_the_receipt_writes_nothing_to_the_copy(tmp_path, capsys):
    import hashlib
    path, _ids = _copy(tmp_path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    R.main(["--db", str(path), "--games-file", str(_games(tmp_path, ROWS))])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["copy.db", "games.csv"]       # no sidecar left behind
