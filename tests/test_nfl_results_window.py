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


def test_an_unscored_opener_of_a_new_season_does_not_republish_the_old_season(tmp_path):
    """Codex on #289 (P2, verified): the season is chosen from every FINISHED predicted game before unscored
    rows are dropped, so a new season whose only finished game has no scores yet exports as that season
    (empty), not as the previous season's results."""
    init_db()
    now = utc_now_naive()
    with session_scope() as s:
        c = s.query(Competition).filter_by(code="NFL").one_or_none()
        if c is None:
            c = Competition(sport=Sport.NFL, code="NFL", name="NFL", area="US", type="LEAGUE")
            s.add(c)
            s.flush()
        h, a = Team(sport=Sport.NFL, name="Opener H"), Team(sport=Sport.NFL, name="Opener A")
        s.add_all([h, a])
        s.flush()
        m = Match(sport=Sport.NFL, competition_id=c.id, season="2099", matchday=1,
                  utc_date=now - timedelta(hours=3), status=MatchStatus.FINISHED,
                  home_team_id=h.id, away_team_id=a.id, home_score=None, away_score=None)
        s.add(m)
        s.flush()
        s.add(Prediction(match_id=m.id, model_version="nfl_elo_v1", home_win_prob=0.5, away_win_prob=0.5))
        mid = m.id
    from src.walters.nfl_predict import export_nfl_results
    doc = json.load(open(export_nfl_results(out_dir=str(tmp_path / "o"))))
    assert doc["window"] == {"kind": "season_to_date", "season": "2099"}
    assert doc["count"] == 0 and doc["results"] == []
    with session_scope() as s:
        s.query(Prediction).filter(Prediction.match_id == mid).delete(synchronize_session=False)
        s.query(Match).filter(Match.id == mid).delete(synchronize_session=False)


def test_ties_are_pushes_and_pre_live_rows_are_never_pooled(tmp_path):
    """ARCHITECT 2026-10-05 (#278 escalations): a TIE is a PUSH in the season record (neither hit nor miss,
    out of the hit denominator, counted separately; the frozen gate's tie convention, and so log loss, is
    untouched). PRESEASON is excluded: the record starts at live_since (Week 3); earlier rows sit under
    "pre_live", never pooled."""
    from datetime import datetime

    from src.walters.nfl_predict import NFL_LIVE_SINCE, export_nfl_results
    init_db()
    now = utc_now_naive()
    with session_scope() as s:
        c = s.query(Competition).filter_by(code="NFL").one_or_none()
        if c is None:
            c = Competition(sport=Sport.NFL, code="NFL", name="NFL", area="US", type="LEAGUE")
            s.add(c)
            s.flush()
        ts = [Team(sport=Sport.NFL, name=f"PushT {i}") for i in range(8)]
        s.add_all(ts)
        s.flush()

        def game(i, when, hs, as_, p, stage=None, week=6):
            m = Match(sport=Sport.NFL, competition_id=c.id, season="2093", matchday=week, stage=stage,
                      utc_date=when, status=MatchStatus.FINISHED, home_team_id=ts[2 * i].id,
                      away_team_id=ts[2 * i + 1].id, home_score=hs, away_score=as_)
            s.add(m)
            s.flush()
            s.add(Prediction(match_id=m.id, model_version="nfl_elo_v1", home_win_prob=p, away_win_prob=1 - p))
            return m.id

        tie = game(0, now - timedelta(days=1), 20, 20, 0.40)                 # away pick, tied: a PUSH, not a hit
        win = game(1, now - timedelta(days=1), 27, 10, 0.70)                 # home pick, home win: a hit
        pre = game(2, NFL_LIVE_SINCE - timedelta(days=9), 24, 3, 0.60, week=1)            # rehearsal Week 1
        pres = game(3, datetime(2093, 8, 20), 13, 17, 0.55, stage="PRESEASON", week=2)    # preseason stage
    doc = json.load(open(export_nfl_results(out_dir=str(tmp_path / "p"))))
    live = {r["match_id"]: r for r in doc["results"]}
    assert tie in live and win in live and pre not in live and pres not in live
    t = live[tie]
    assert t["graded"]["push"] is True and t["graded"]["top_pick_hit"] is None and t["actual"]["result"] == "T"
    assert t["graded"]["log_loss"] == round(-__import__("math").log(0.6), 4)  # gate convention: tie = home loss
    w6 = doc["record"]["by_week"]["6"]
    assert w6 == {"games": 2, "decided": 1, "hits": 1, "pushes": 1}
    assert doc["record"]["live_since"] == f"{NFL_LIVE_SINCE:%Y-%m-%d}" and doc["count"] == len(doc["results"])
    assert doc["record"]["games"] == doc["count"]
    assert {r["match_id"] for r in doc["pre_live"]["results"]} == {pre, pres}
    assert doc["pre_live"]["record"]["games"] == 2 and doc["pre_live"]["count"] == 2
    assert not any("_pre_live" in r for r in doc["results"] + doc["pre_live"]["results"])


def test_cli_receipt_uses_decided_and_finds_pre_live_matches(tmp_path, monkeypatch):
    """Codex on #290 (verified): the export-nfl-results receipt printed hits/games (a push counted as a miss)
    and looked for --match ids in `results` only, so a pre-live match read NOT in the file."""
    from click.testing import CliRunner

    import cli
    from src.walters import nfl_predict
    doc = {"window": {"kind": "season_to_date", "season": "2093"},
           "record": {"live_since": "2026-09-22", "games": 2, "decided": 1, "hits": 1, "pushes": 1,
                      "by_week": {"6": {"games": 2, "decided": 1, "hits": 1, "pushes": 1}}},
           "results": [{"match_id": 11}], "count": 1,
           "pre_live": {"count": 1, "record": {"games": 1, "decided": 1, "hits": 0, "pushes": 0},
                        "results": [{"match_id": 22}]}}
    path = tmp_path / "r.json"
    path.write_text(json.dumps(doc))
    monkeypatch.setattr(nfl_predict, "export_nfl_results", lambda days_back=None: str(path))
    res = CliRunner().invoke(cli.cli, ["export-nfl-results", "--match", "11", "--match", "22", "--match", "33"])
    assert res.exit_code == 0, res.output
    assert "top-pick hits 1/1 decided · pushes 1" in res.output and "W6 1/1 +1P" in res.output
    assert "match 11: IN the file (season record)" in res.output
    assert "match 22: IN the file (pre-live, not in the season record)" in res.output
    assert "match 33: NOT in the file" in res.output and "pre-live (never pooled): games 1" in res.output


def test_nfl_grade_and_results_md_state_the_one_record_definition(tmp_path):
    """ARCHITECT 2026-10-06: nfl-grade, the RESULTS.md NFL section and the season-to-date results file use ONE
    definition — live_since onward, ties as pushes outside the hit denominator, pre-live rows under their own
    heading. Before: grade_nfl counted a tie as a hit for an away pick and pooled Weeks 1-2."""
    from datetime import datetime

    from src.walters.export import results_tally
    from src.walters.nfl_predict import NFL_LIVE_SINCE, grade_nfl
    init_db()
    now = utc_now_naive()
    with session_scope() as s:
        c = s.query(Competition).filter_by(code="NFL").one_or_none()
        if c is None:
            c = Competition(sport=Sport.NFL, code="NFL", name="NFL", area="US", type="LEAGUE")
            s.add(c)
            s.flush()
        ts = [Team(sport=Sport.NFL, name=f"OneDef {i}") for i in range(10)]
        s.add_all(ts)
        s.flush()
        ids = []

        def game(i, when, hs, as_, p, stage=None, week=6):
            m = Match(sport=Sport.NFL, competition_id=c.id, season="2095", matchday=week, stage=stage,
                      utc_date=when, status=MatchStatus.FINISHED, home_team_id=ts[2 * i].id,
                      away_team_id=ts[2 * i + 1].id, home_score=hs, away_score=as_)
            s.add(m)
            s.flush()
            s.add(Prediction(match_id=m.id, model_version="nfl_elo_v1", home_win_prob=p, away_win_prob=1 - p))
            ids.append(m.id)

        game(0, now - timedelta(days=1), 20, 20, 0.40)                      # away pick, tied: PUSH (was a hit)
        game(1, now - timedelta(days=1), 27, 10, 0.70)                      # home pick, home win: hit
        game(2, now - timedelta(days=2), 10, 27, 0.65)                      # home pick, away win: miss
        game(3, NFL_LIVE_SINCE - timedelta(days=9), 24, 3, 0.60, week=1)    # rehearsal Week 1: pre-live
        game(4, datetime(2095, 8, 20), 13, 17, 0.55, stage="PRESEASON", week=2)
    try:
        lines = []
        r = grade_nfl(days_back=None, progress=lines.append)
        assert (r["games"], r["decided"], r["hits"], r["pushes"]) == (3, 2, 1, 1)
        assert r["pre_live"] == {"games": 2, "decided": 2, "hits": 1, "pushes": 0}
        assert any("PUSH" in x and "OneDef 1" in x for x in lines)
        assert any("sides 1/2 decided (+1 push)" in x for x in lines)
        assert any("pre-live (before" in x and "never pooled" in x for x in lines)
        # the rolling read applies the same definition (the pre-live rows are simply outside it)
        rlines = []
        rr = grade_nfl(days_back=3, progress=rlines.append)
        assert rr["games"] == rr["decided"] + rr["pushes"] and rr["pushes"] >= 1
        assert "PUSH" in next(x for x in rlines if "OneDef 1" in x)
        out = tmp_path / "RESULTS.md"
        results_tally(days=30, out_path=str(out))
        txt = out.read_text()
        assert "## NFL (live since Week 3, 2026-09-22)\n\n- Sides: **1/2** (50.0%) · pushes 1" in txt
        assert "### NFL pre-live (before 2026-09-22; never pooled)\n\n- Sides: 1/2 · pushes 0" in txt
    finally:
        with session_scope() as s:
            s.query(Prediction).filter(Prediction.match_id.in_(ids)).delete(synchronize_session=False)
            s.query(Match).filter(Match.id.in_(ids)).delete(synchronize_session=False)
