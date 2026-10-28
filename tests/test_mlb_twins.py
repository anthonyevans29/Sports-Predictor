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
    r = run_cli("--apply", "--backup", str(tmp_path / "b.db"), "--gamepks", ",".join(PLANNED + ["700001", "824621"]))
    assert r.exit_code == 0, r.output
    assert r.output.count("MERGED gamePk 824621") == 1                  # named twice, merged once
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


def test_the_apply_reads_back_the_training_set_it_leaves(db, tmp_path, monkeypatch):
    """A subset named: the after count is the committed state's (one 2026 FINISHED twin retired), not the plan's."""
    import cli
    monkeypatch.setattr(cli, "_verify_backup", lambda path, table, model: path)
    r = run_cli("--apply", "--backup", str(tmp_path / "b.db"), "--gamepks", "824621")
    assert r.exit_code == 0, r.output
    assert "before -> after: 2025 12 -> 11 · 2026 3 -> 2" in r.output        # the plan, every group
    assert "after this apply (read back): 2025 12 -> 12 · 2026 3 -> 2" in r.output


def test_the_host_fallback_id_moves_to_the_kept_row(db, tmp_path, monkeypatch):
    """Addendum 169 item 3(c): the host runs the dedupe too, and its api-sports fallback looks a game up by
    api_baseball: the retired row hands its id to the kept row (which held none) and keeps it only as history."""
    import cli
    from src.db.database import session_scope
    from src.db.schema import Match
    monkeypatch.setattr(cli, "_verify_backup", lambda path, table, model: path)
    with session_scope() as s:
        m = s.get(Match, 3945)
        m.external_ids = {**m.external_ids, "api_baseball": "41"}
    assert run_cli("--apply", "--backup", str(tmp_path / "b.db"), "--gamepks", "824621").exit_code == 0
    with session_scope() as s:
        kept, other = s.get(Match, 3940), s.get(Match, 3945)
        assert kept.external_ids["api_baseball"] == "41"
        assert "api_baseball" not in other.external_ids and other.external_ids["api_baseball_prev"] == ["41"]


def test_a_marked_prediction_is_never_the_game_s_prediction_in_an_export(db, tmp_path, monkeypatch):
    """ARCHITECT 2026-10-27 09:05 ET (#704 read): "Push the exports-skip line". After the merge, 4390 holds only the
    re-pointed post-game prediction of its SCHEDULED copy: the export shows the game with no prediction."""
    import cli
    from src.db.schema import Sport
    from src.walters.export import _collect_rows
    monkeypatch.setattr(cli, "_verify_backup", lambda path, table, model: path)
    assert run_cli("--apply", "--backup", str(tmp_path / "b.db"), "--gamepks", "823062").exit_code == 0
    rows = {r["match_id"]: r for r in _collect_rows(sport=Sport.MLB, start_date=Z("2026-07-07T00:00"),
                                                     end_date=Z("2026-07-08T00:00"), competition_code="MLB",
                                                     statuses=None)}
    assert 4390 in rows and rows[4390]["prediction"] is None
    assert 5218 not in rows or rows[5218]["prediction"] is None


def test_a_kept_postponed_row_counts_with_the_finished_state_it_takes(db, tmp_path, monkeypatch):
    """#709 item 1 (Codex on #704): a class-3 POSTPONED row holding references is kept by (a) and takes the make-up's
    FINISHED state, so the training set's count does not change. The dry run projects from both rows' status before
    and after, and its projection is the apply's read-back."""
    import cli
    from src.db.database import session_scope
    from src.db.schema import Match, MatchStatus, Odds
    monkeypatch.setattr(cli, "_verify_backup", lambda path, table, model: path)
    with session_scope() as s:
        s.add(Odds(match_id=6782, bookmaker="b", market="ML", selection="HOME", price_decimal=2.1))
    r = run_cli()
    assert r.exit_code == 0, r.output
    assert "[class 3] gamePk 778443 (a POSTPONED row and its make-up): KEEPS 6782, RETIRES 6784" in r.output
    assert "the kept row takes: utc_date 2025-04-05T17:05 -> 2025-04-06T17:05, status POSTPONED -> FINISHED" in r.output
    assert "before -> after: 2025 12 -> 11 · 2026 3 -> 2" in r.output          # class 4's retired row only, in 2025
    r = run_cli("--apply", "--backup", str(tmp_path / "b.db"), "--gamepks", ",".join(PLANNED))
    assert r.exit_code == 0, r.output
    assert "after this apply (read back): 2025 12 -> 11 · 2026 3 -> 2" in r.output
    with session_scope() as s:
        assert s.get(Match, 6782).status == MatchStatus.FINISHED
        assert s.get(Match, 6784).status == MatchStatus.STALE_ORPHAN


def test_a_child_row_moves_unless_the_kept_row_holds_one_of_its_key(db, tmp_path, monkeypatch):
    """#709 item 2 (Codex on #704): both class-1 rows carry the home starter, and the retired row also carries the away
    starter, both sides' stats and a projected home lineup next to the confirmed one both hold. The keys are the
    schema's and the writers': match_participants (team, role), match_stats (team), lineups (team, kind). The rows the
    kept row lacks move; only the colliding ones stay on the retired row. Nothing is deleted."""
    import cli
    from src.db.database import session_scope
    from src.db.schema import Lineup, Match, MatchParticipant, MatchStats
    monkeypatch.setattr(cli, "_verify_backup", lambda path, table, model: path)
    with session_scope() as s:
        h, a = s.get(Match, 3940).home_team_id, s.get(Match, 3940).away_team_id
        s.add(MatchParticipant(match_id=3945, team_id=a, role="starting_pitcher", kind="confirmed", player_name="p2",
                               player_source_id="p2"))
        s.add_all([MatchStats(match_id=3940, team_id=h), MatchStats(match_id=3945, team_id=h),
                   MatchStats(match_id=3945, team_id=a)])
        s.add_all([Lineup(match_id=3940, team_id=h, kind="confirmed", player_name="x1"),
                   Lineup(match_id=3945, team_id=h, kind="confirmed", player_name="x1"),
                   Lineup(match_id=3945, team_id=h, kind="projected", player_name="x2")])
    before = counts()
    r = run_cli()
    assert r.exit_code == 0, r.output
    assert ("re-points: lineups 1, match_participants 1, match_stats 1, pitcher_appearances 1 · left on the retired row "
            "(the kept row holds its own): lineups 1, match_participants 1, match_stats 1") in r.output
    r = run_cli("--apply", "--backup", str(tmp_path / "b.db"), "--gamepks", "824621")
    assert r.exit_code == 0, r.output
    assert ("MERGED gamePk 824621: kept 3940, 3945 STALE_ORPHAN · re-pointed lineups 1, match_participants 1, "
            "match_stats 1, pitcher_appearances 1") in r.output
    assert {k: v for k, v in counts().items() if k != "orphans"} == {k: v for k, v in before.items() if k != "orphans"}
    with session_scope() as s:
        def on(model, *cols):
            return sorted(tuple(r) for r in s.execute(select(model.match_id, *cols)))
        assert on(MatchParticipant, MatchParticipant.team_id) == [(3940, h), (3940, a), (3945, h)]
        assert on(MatchStats, MatchStats.team_id) == [(3940, h), (3940, a), (3945, h)]
        assert on(Lineup, Lineup.kind) == [(3940, "confirmed"), (3940, "projected"), (3945, "confirmed")]


def test_the_dry_run_counts_a_class_2_prediction_computed_before_the_kickoff(db):
    """#709 item 3 (Codex on #704, a ledger question): the dry run already prints, per class-2 group, how many of the
    copy's predictions were computed at or after the kept row's kickoff, so a pre-kickoff one shows in the receipt for
    the architect. No policy change: the apply marks every re-pointed class-2 prediction, as ruling (c) reads."""
    from src.db.database import session_scope
    from src.db.schema import Prediction
    with session_scope() as s:
        s.add(Prediction(match_id=5218, model_version="mlb-v1", computed_at=Z("2026-07-07T18:00"), home_win_prob=0.5,
                         away_win_prob=0.5))
    r = run_cli()
    assert r.exit_code == 0, r.output
    assert ("(c) predictions of a game already played at the time: 2 prediction(s) (1 computed at or after the kept "
            "row's kickoff 2026-07-07T23:10)") in r.output


def lock_taken():
    """(this thread's db_lock depth, the flock taken: another open file description of SP_LOCK cannot take it). The
    #709 item 4 receipt, shared by the lock tests of dedupe-matches and retire-orphans."""
    import fcntl
    import os
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "deploy" / "hosting"))
    import sp_common as c
    with open(os.environ["SP_LOCK"], "a+") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return getattr(c._HELD, "depth", 0), True
        fcntl.flock(f, fcntl.LOCK_UN)
        return getattr(c._HELD, "depth", 0), False


def spy_db_lock(monkeypatch) -> list:
    """Each db_lock taken (sp_common.sync_lock's), counted; the real lock is taken."""
    import sp_common as c
    real, taken = c.db_lock, []

    def spy(**k):
        taken.append(k)
        return real(**k)
    monkeypatch.setattr(c, "db_lock", spy)
    return taken


def test_the_apply_holds_the_lock_from_the_backup_check_through_the_merge(db, tmp_path, monkeypatch):
    """#709 item 4 (Codex on #704): the command takes the chains' DB lock before _verify_backup and holds it through
    the plan and the merge, so no chain commits between the backup check and the merge. mt.run's own lock is a no-op
    under it (one lock taken); a dry run takes none."""
    import cli
    from src.ingestion import mlb_twins as mt
    monkeypatch.setenv("SP_LOCK", str(tmp_path / "db.lock"))
    lock_taken()
    taken, seen = spy_db_lock(monkeypatch), []
    monkeypatch.setattr(cli, "_verify_backup", lambda path, table, model: seen.append(("backup", lock_taken())) or path)
    real_plan, real_merge = mt.plan, mt.merge
    monkeypatch.setattr(mt, "plan", lambda s: seen.append(("plan", lock_taken())) or real_plan(s))
    monkeypatch.setattr(mt, "merge", lambda *a: seen.append(("merge", lock_taken())) or real_merge(*a))
    r = run_cli()
    assert r.exit_code == 0, r.output
    assert seen == [("plan", (0, False))] and taken == []
    seen.clear()
    r = run_cli("--apply", "--backup", str(tmp_path / "b.db"), "--gamepks", "824621")
    assert r.exit_code == 0, r.output
    assert "MERGED gamePk 824621" in r.output
    assert seen == [("backup", (1, True)), ("plan", (1, True)), ("merge", (1, True))]
    assert len(taken) == 1 and lock_taken() == (0, False)                     # one lock, released after


@pytest.mark.parametrize("scores", [((None, None), (None, None)), ((5, None), (5, None)), ((None, 2), (None, 2)),
                                    ((5, 2), (5, None))])
def test_a_finished_pair_without_a_complete_score_is_refused(db, tmp_path, monkeypatch, scores):
    """#709 item 5 (Codex on #704): classify compared the two scores for equality, so two FINISHED rows both (None,
    None), or both (5, None), passed as class 1. A FINISHED pair is classed only with both scores on both rows; else it
    is REFUSED and listed as any pair of no class, and an apply naming it leaves it."""
    import cli
    from src.db.database import session_scope
    from src.db.schema import Match
    monkeypatch.setattr(cli, "_verify_backup", lambda path, table, model: path)
    with session_scope() as s:
        for mid, (h, a) in zip((3940, 3945), scores):
            s.get(Match, mid).home_score, s.get(Match, mid).away_score = h, a
    shown = ", ".join(f"{h}-{a}" for h, a in scores)
    r = run_cli()
    assert r.exit_code == 0, r.output
    assert "planned 3 (class 2 1 · class 3 1 · class 4 1) · refused 5" in r.output
    assert (f"[REFUSED] gamePk 824621: two FINISHED rows without a complete score ({shown}): no class of the ruling · "
            "listed for the architect, nothing written") in r.output
    r = run_cli("--apply", "--backup", str(tmp_path / "b.db"), "--gamepks", "824621")
    assert r.exit_code == 0, r.output
    assert f"REFUSED gamePk 824621: two FINISHED rows without a complete score ({shown})" in r.output
    assert "merged 0 · refused 1" in r.output and counts()["orphans"] == 1


def test_a_db_without_prediction_history_plans_and_applies_class_2(db, tmp_path, monkeypatch):
    """#709 item 6 (Codex on #704): the class-2 history count queried prediction_history unguarded, where _fk_tables
    skips a table the live DB lacks. The count is skipped the same way: the table is named absent, no history row is
    counted, and the apply merges (the throwaway DB's table dropped)."""
    import cli
    from sqlalchemy import text

    from src.db.database import get_engine, session_scope
    from src.db.schema import Match, MatchStatus, Prediction
    monkeypatch.setattr(cli, "_verify_backup", lambda path, table, model: path)
    with get_engine().begin() as con:
        con.execute(text("DROP TABLE prediction_history"))
    r = run_cli()
    assert r.exit_code == 0, r.output
    assert "reference tables absent from the live DB, skipped (they hold no references): prediction_history" in r.output
    assert ("(c) predictions of a game already played at the time: 1 prediction(s) (1 computed at or after the kept "
            "row's kickoff 2026-07-07T23:10) and 0 history row(s)") in r.output
    r = run_cli("--apply", "--backup", str(tmp_path / "b.db"), "--gamepks", "823062")
    assert r.exit_code == 0, r.output
    assert "MERGED gamePk 823062: kept 4390, 5218 STALE_ORPHAN · re-pointed predictions 1" in r.output
    with session_scope() as s:
        assert s.get(Match, 5218).status == MatchStatus.STALE_ORPHAN
        assert s.execute(select(Prediction.match_id)).scalars().all() == [4390]
