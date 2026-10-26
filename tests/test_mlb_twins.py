"""MLB TWINS DEDUPE (#569 RULED, ARCHITECT 2026-10-21, addendum 153 item 2): two live MLB rows holding one mlb_stats_api
id are one game. The world is synthetic, each class modelled on the 2026-10-21 read (the ids are the read's where it
names them): class 1 3940/3945 (824621), class 2 4390/5218 (823062), class 3 6782/6784 (778443), class 4 8347/8353
(776907, the earlier row holding two Kalshi settlements), and the refusals (different scores, a later class-4 row holding
references, three rows on one gamePk, two SCHEDULED rows). Each test has a throwaway DB of its own."""
from datetime import datetime, timedelta

import pytest
from click.testing import CliRunner
from sqlalchemy import create_engine, func, select

Z = datetime.fromisoformat
NOW = Z("2026-10-26T21:00")
# (id, gamePk, start UTC, status, home runs, away runs, season)
ROWS = [
    (3940, "824621", "2026-08-01T23:05", "FINISHED", 5, 2, "2026"),     # class 1: same minute, same score
    (3945, "824621", "2026-08-01T23:05", "FINISHED", 5, 2, "2026"),
    (4390, "823062", "2026-07-07T23:10", "FINISHED", 3, 4, "2026"),     # class 2: FINISHED + SCHEDULED copy
    (5218, "823062", "2026-07-07T23:10", "SCHEDULED", None, None, "2026"),
    (6782, "778443", "2025-04-05T17:05", "POSTPONED", None, None, "2025"),   # class 3: POSTPONED + make-up
    (6784, "778443", "2025-04-06T17:05", "FINISHED", 1, 0, "2025"),
    (8347, "776907", "2025-06-10T23:05", "FINISHED", 6, 3, "2025"),     # class 4: a day apart, Kalshi on the earlier
    (8353, "776907", "2025-06-11T23:05", "FINISHED", 6, 3, "2025"),
    (9001, "700001", "2025-05-01T23:05", "FINISHED", 2, 1, "2025"),     # refused: two scores
    (9002, "700001", "2025-05-01T23:05", "FINISHED", 1, 2, "2025"),
    (9011, "700002", "2025-05-02T23:05", "FINISHED", 4, 4, "2025"),     # refused: the later class-4 row holds odds
    (9012, "700002", "2025-05-03T23:05", "FINISHED", 4, 4, "2025"),
    (9021, "700003", "2025-05-04T23:05", "FINISHED", 3, 1, "2025"),     # refused: three rows
    (9022, "700003", "2025-05-04T23:05", "FINISHED", 3, 1, "2025"),
    (9023, "700003", "2025-05-04T23:05", "FINISHED", 3, 1, "2025"),
    (9031, "700004", "2025-05-05T23:05", "SCHEDULED", None, None, "2025"),   # refused: two SCHEDULED rows
    (9032, "700004", "2025-05-05T23:05", "SCHEDULED", None, None, "2025"),
    (9041, "700005", "2025-05-06T23:05", "FINISHED", 2, 0, "2025"),     # a pair already deduped: not a group
    (9042, "700005", "2025-05-06T23:05", "STALE_ORPHAN", 2, 0, "2025"),
    (9051, "700006", "2025-05-07T23:05", "FINISHED", 7, 1, "2025"),     # one row: not a group
]
PLANNED = ["776907", "778443", "823062", "824621"]


@pytest.fixture
def db(tmp_path, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    import src.db.database as dbm
    import src.timeutil as tu
    path = tmp_path / "fresh.db"
    eng = create_engine(f"sqlite:///{path}", future=True)
    monkeypatch.setattr(dbm, "_engine", eng)
    monkeypatch.setattr(dbm, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                          expire_on_commit=False))
    monkeypatch.setattr(tu, "utc_now_naive", lambda: NOW)
    dbm.init_db()
    seed()
    yield path
    eng.dispose()


def seed():
    from src.db.database import session_scope
    from src.db.schema import (Competition, KalshiSettledMarket, Match, MatchParticipant, MatchStatus, Odds,
                               PitcherAppearance, Prediction, PredictionHistory, Sport, Team)
    with session_scope() as s:
        comp = Competition(sport=Sport.MLB, code="MLB", name="Major League Baseball", area="USA", type="LEAGUE")
        h = Team(sport=Sport.MLB, name="Hawks", external_ids={"mlb_stats_api": "147"})
        a = Team(sport=Sport.MLB, name="Owls", external_ids={"mlb_stats_api": "111"})
        s.add_all([comp, h, a])
        s.flush()
        for i, pk, when, st, hr, ar, season in ROWS:
            s.add(Match(id=i, sport=Sport.MLB, competition_id=comp.id, season=season, stage="R", utc_date=Z(when),
                        status=MatchStatus[st], home_team_id=h.id, away_team_id=a.id, home_score=hr, away_score=ar,
                        status_raw={"FINISHED": "F"}.get(st),
                        external_ids={"mlb_stats_api": pk} if st != "STALE_ORPHAN" else {"mlb_stats_api_prev": [pk]}))
        s.flush()
        # class 1: the boxscore's appearance sits on 3945, and both rows carry a starter for the home side
        s.add(PitcherAppearance(match_id=3945, source_game_id="824621", game_date=Z("2026-08-01T23:05"),
                                team_source_id="147", pitcher_id="p1", outs=18, is_starter=True, earned_runs=2))
        for mid in (3940, 3945):
            s.add(MatchParticipant(match_id=mid, team_id=h.id, role="starting_pitcher", kind="confirmed",
                                   player_name="p1", player_source_id="p1"))
        # class 2: the SCHEDULED copy carries a prediction computed months after the game, and history rows (two here,
    # and the one the prediction's own insert writes)
        s.add(Prediction(match_id=5218, model_version="mlb-v2", computed_at=Z("2026-10-19T23:34"), home_win_prob=0.55,
                         away_win_prob=0.45, factor_breakdown={"k": 1}))
        for k in range(2):
            s.add(PredictionHistory(match_id=5218, model_version="mlb-v2",
                                    computed_at=Z("2026-10-19T23:34") - timedelta(days=k), home_win_prob=0.55,
                                    away_win_prob=0.45))
        # class 4: the earlier row holds the two Kalshi settlements
        for side in ("HOME", "AWAY"):
            s.add(KalshiSettledMarket(ticker=f"KXMLBGAME-25JUN10-{side}", series="KXMLBGAME", side=side, match_id=8347,
                                      source="historical", fetched_at=NOW))
        s.add(Odds(match_id=9012, bookmaker="b", market="ML", selection="HOME", price_decimal=1.9))


def run_cli(*args):
    import cli
    return CliRunner().invoke(cli.cli, ["dedupe-mlb-twins", *args])


def counts():
    from src.db.database import session_scope
    from src.db.schema import Match, MatchParticipant, PitcherAppearance, Prediction, PredictionHistory
    with session_scope() as s:
        return {t.__name__: s.execute(select(func.count()).select_from(t)).scalar()
                for t in (Match, MatchParticipant, PitcherAppearance, Prediction, PredictionHistory)} | {
            "orphans": s.execute(select(func.count()).select_from(Match).where(
                Match.status == "STALE_ORPHAN")).scalar()}


def test_the_dry_run_lists_every_group_with_its_class_kept_id_and_reason_and_writes_nothing(db):
    before = counts()
    r = run_cli()
    assert r.exit_code == 0, r.output
    out = r.output
    assert ("DRY RUN (nothing written) · gamePks held by two or more live MLB rows 8 · planned 4 (class 1 1 · class 2 1 "
            "· class 3 1 · class 4 1) · refused 4") in out
    assert ("[class 1] gamePk 824621 (same-minute twins): KEEPS 3940, RETIRES 3945 to STALE_ORPHAN · (a) class 1: "
            "neither holds references, the lower id (the first stored)") in out
    assert ("re-points: pitcher_appearances 1 · left on the retired row (the kept row holds its own): "
            "match_participants 1") in out
    assert "[class 2] gamePk 823062 (a FINISHED game and a SCHEDULED copy): KEEPS 4390, RETIRES 5218" in out
    assert ("(c) predictions of a game already played at the time: 1 prediction(s) (1 computed at or after the kept "
            "row's kickoff 2026-07-07T23:10) and 3 history row(s), re-pointed; each prediction marked dedupe_569") in out
    assert "[class 3] gamePk 778443 (a POSTPONED row and its make-up): KEEPS 6784, RETIRES 6782 to STALE_ORPHAN · (d) class 3: the make-up is the game" in out
    assert ("[class 4] gamePk 776907 (two FINISHED rows, two kickoffs): KEEPS 8347, RETIRES 8353 to STALE_ORPHAN · (b) "
            "class 4: the earlier row is kept (it holds the references) and takes the later row's date") in out
    assert "the kept row takes: utc_date 2025-06-10T23:05 -> 2025-06-11T23:05" in out
    assert "[REFUSED] gamePk 700001: two FINISHED rows with different scores (2-1, 1-2)" in out
    assert ("[REFUSED] gamePk 700002 (class 4, two FINISHED rows, two kickoffs): (b) keeps the earlier row, but the "
            "later row holds the references") in out
    assert "[REFUSED] gamePk 700003: 3 rows hold one gamePk: a pair only" in out
    assert "[REFUSED] gamePk 700004: statuses SCHEDULED twice: no class of the ruling" in out
    assert "700005" not in out and "700006" not in out
    assert "(c) the record: 1 prediction(s) and 3 history row(s) of a game already played at the time" in out
    # FINISHED: 2026 3940, 3945, 4390; 2025 6784, 8347, 8353, 9001, 9002, 9011, 9012, 9021-9023, 9041, 9051
    assert "the training set's FINISHED MLB rows per season, before -> after: 2025 12 -> 11 · 2026 3 -> 2" in out
    assert "--apply --backup PATH --gamepks 776907,778443,823062,824621" in out
    assert counts() == before


def test_the_apply_retires_the_named_rows_re_points_and_marks_and_deletes_nothing(db, tmp_path, monkeypatch):
    import cli
    from src.db.database import session_scope
    from src.db.schema import KalshiSettledMarket, Match, MatchParticipant, MatchStatus, PitcherAppearance, Prediction
    from src.ingestion import mlb_twins as mt
    monkeypatch.setattr(cli, "_verify_backup", lambda path, table, model: path)
    before = counts()
    r = run_cli("--apply", "--backup", str(tmp_path / "b.db"), "--gamepks", ",".join(PLANNED + ["700001"]))
    assert r.exit_code == 0, r.output
    assert "REFUSED gamePk 700001: two FINISHED rows with different scores (2-1, 1-2): no class of the ruling" in r.output
    assert "merged 4 · refused 1" in r.output
    after = counts()
    assert {k: v for k, v in after.items() if k != "orphans"} == {k: v for k, v in before.items() if k != "orphans"}
    assert after["orphans"] == before["orphans"] + 4
    with session_scope() as s:
        m = {i: s.get(Match, i) for i in (3940, 3945, 4390, 5218, 6782, 6784, 8347, 8353)}
        for kept, other in ((3940, 3945), (4390, 5218), (6784, 6782), (8347, 8353)):
            assert m[other].status == MatchStatus.STALE_ORPHAN and m[kept].status == MatchStatus.FINISHED
            assert "mlb_stats_api" not in m[other].external_ids
            assert m[other].external_ids["mlb_stats_api_prev"] == [m[kept].external_ids["mlb_stats_api"]]
            assert m[other].external_ids["mlb_stats_api_merged_into"] == kept
            assert m[kept].external_ids["mlb_stats_api_merged_from"] == [other]
        assert m[8347].utc_date == Z("2025-06-11T23:05")
        assert s.execute(select(PitcherAppearance.match_id)).scalars().all() == [3940]
        assert sorted(s.execute(select(MatchParticipant.match_id)).scalars().all()) == [3940, 3945]
        assert set(s.execute(select(KalshiSettledMarket.match_id)).scalars().all()) == {8347}
        p = s.execute(select(Prediction)).scalars().one()
        assert p.match_id == 4390 and p.factor_breakdown["k"] == 1
        assert p.factor_breakdown["dedupe_569"]["from_match"] == 5218
        assert mt.groups(s).keys() == {"700001", "700002", "700003", "700004"}


def test_a_marked_prediction_is_never_graded_as_a_call(db, tmp_path, monkeypatch):
    import cli
    from src.db.database import session_scope
    from src.db.schema import Prediction, PredictionOutcome, Sport
    from src.walters.training import evaluate_finished
    monkeypatch.setattr(cli, "_verify_backup", lambda path, table, model: path)
    assert run_cli("--apply", "--backup", str(tmp_path / "b.db"), "--gamepks", "823062").exit_code == 0
    with session_scope() as s:
        s.add(Prediction(match_id=6784, model_version="mlb-v2", computed_at=Z("2025-04-06T12:00"), home_win_prob=0.6,
                         away_win_prob=0.4))
    assert evaluate_finished(sport=Sport.MLB) == 1             # 6784's pregame call is graded; 4390's re-pointed one not
    with session_scope() as s:
        graded = s.execute(select(Prediction.match_id).join(PredictionOutcome,
                                                             PredictionOutcome.prediction_id == Prediction.id)).all()
        assert [g[0] for g in graded] == [6784]


def test_the_refusals_of_the_command(db, tmp_path):
    r = run_cli("--gamepks", "824621")
    assert r.exit_code == 2 and "is read only with --apply" in r.output
    r = run_cli("--apply", "--backup", str(tmp_path / "b.db"))
    assert r.exit_code == 2 and "--apply without --gamepks" in r.output
    r = run_cli("--apply", "--gamepks", "x1")
    assert r.exit_code == 2 and "--gamepks takes comma-separated gamePks" in r.output
    r = run_cli("--apply", "--gamepks", "824621")
    assert r.exit_code == 2                                    # the backup check: no --backup given
    assert counts()["orphans"] == 1


def test_a_missing_db_is_refused_and_never_created(tmp_path, monkeypatch):
    import src.db.database as dbm
    path = tmp_path / "absent.db"
    monkeypatch.setattr(dbm, "_engine", create_engine(f"sqlite:///{path}", future=True))
    r = run_cli()
    assert r.exit_code == 2
    assert not path.exists()
