"""ARCHITECT 2026-10-05: nfl_NFL_results_2026-10-05 lacked match 15073 (GB–ATL, Week 3 TNF) that the 10-02
file had. Cause: a ROLLING 8-day window (the game aged out; no filter changed). Fix: season to date by
default, with the window and the season record in the file, so a lifetime record reconciles."""
import json
from datetime import timedelta

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Prediction, Sport, Team
from src.timeutil import utc_now_naive


def test_season_to_date_keeps_a_game_the_rolling_window_dropped(tmp_path):
    init_db()
    now = utc_now_naive()
    with session_scope() as s:
        c = s.query(Competition).filter_by(code="NFL").one_or_none()
        if c is None:
            c = Competition(sport=Sport.NFL, code="NFL", name="NFL", area="US", type="LEAGUE")
            s.add(c)
            s.flush()
        gb, atl, kc, buf = (Team(sport=Sport.NFL, name=f"WinT {n}") for n in ("GB", "ATL", "KC", "BUF"))
        s.add_all([gb, atl, kc, buf])
        s.flush()
        old = Match(sport=Sport.NFL, competition_id=c.id, season="2091", matchday=3,
                    utc_date=now - timedelta(days=10), status=MatchStatus.FINISHED,
                    home_team_id=atl.id, away_team_id=gb.id, home_score=20, away_score=24)
        new = Match(sport=Sport.NFL, competition_id=c.id, season="2091", matchday=4,
                    utc_date=now - timedelta(days=2), status=MatchStatus.FINISHED,
                    home_team_id=kc.id, away_team_id=buf.id, home_score=27, away_score=17)
        s.add_all([old, new])
        s.flush()
        for m, p in ((old, 0.40), (new, 0.62)):
            s.add(Prediction(match_id=m.id, model_version="nfl_elo_v1", home_win_prob=p, away_win_prob=1 - p))
        ids = (old.id, new.id)
    from src.walters.nfl_predict import export_nfl_results
    doc = json.load(open(export_nfl_results(out_dir=str(tmp_path / "a"))))
    got = {r["match_id"] for r in doc["results"]}
    assert set(ids) <= got                                     # the 10-day-old game is still in the file
    assert doc["window"] == {"kind": "season_to_date", "season": "2091"}
    assert doc["record"]["by_week"]["3"]["games"] >= 1 and doc["record"]["games"] == doc["count"]
    rolling = json.load(open(export_nfl_results(days_back=8, out_dir=str(tmp_path / "b"))))
    assert ids[0] not in {r["match_id"] for r in rolling["results"]}    # the old behaviour: aged out
    assert ids[1] in {r["match_id"] for r in rolling["results"]} and rolling["window"]["kind"] == "rolling"


def test_a_finished_row_without_scores_is_skipped_not_a_crash(tmp_path):
    """Codex on #278 (P1, verified): a FINISHED NFL match whose scores have not arrived raised TypeError on
    `home_score > away_score` and aborted the season-to-date export. Unscored rows are now out of scope."""
    init_db()
    now = utc_now_naive()
    with session_scope() as s:
        c = s.query(Competition).filter_by(code="NFL").one_or_none()
        if c is None:
            c = Competition(sport=Sport.NFL, code="NFL", name="NFL", area="US", type="LEAGUE")
            s.add(c)
            s.flush()
        h, a = Team(sport=Sport.NFL, name="NoScore H"), Team(sport=Sport.NFL, name="NoScore A")
        s.add_all([h, a])
        s.flush()
        m = Match(sport=Sport.NFL, competition_id=c.id, season="2091", matchday=5,
                  utc_date=now - timedelta(days=1), status=MatchStatus.FINISHED,
                  home_team_id=h.id, away_team_id=a.id, home_score=None, away_score=None)
        s.add(m)
        s.flush()
        s.add(Prediction(match_id=m.id, model_version="nfl_elo_v1", home_win_prob=0.55, away_win_prob=0.45))
        mid = m.id
    from src.walters.nfl_predict import export_nfl_results
    doc = json.load(open(export_nfl_results(out_dir=str(tmp_path / "c"))))     # no TypeError
    assert mid not in {r["match_id"] for r in doc["results"]}
    assert doc["record"]["games"] == doc["count"]
