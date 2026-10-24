"""THE GAME'S SEASON (ARCHITECT 2026-10-23, addendum 162 item 1(b)): the live MLB pitcher lookup selects the row of
the game's season (Match.season as stored), explicitly; a pitcher with no row for that season is "no stats" and takes
the existing missing-starter shrink, never another season's row. The export's pitcher block reads the same row.
The receipt script (scripts/mlb_pitcher_season_receipt.py) names the old read's row against the new one.
Throwaway DB only (tests/conftest.py)."""
import importlib.util
import re
from datetime import datetime, timedelta

COMP = "MLBPS"
SEASON = "2094"
PRIOR = "2093"
KO = datetime(2094, 7, 1, 23, 5)
VERSION = "ps-season-test"


def _build():
    """60 finished games, two scheduled. TWO: the home starter holds a 2094 row (era 2.00) stored BEFORE a 2093 row
    (era 9.00), so the old read (the last row yielded) took 2093. ONLY_PRIOR: the home starter holds a 2093 row
    only. Both away starters hold a 2094 row. {tag: match_id}."""
    from src.db.database import init_db, session_scope
    from src.db.schema import (Competition, Match, MatchParticipant, MatchStatus, ModelVersion, PitcherSeasonStats,
                               Sport, Team)

    init_db()
    with session_scope() as s:
        c = s.query(Competition).filter_by(code=COMP).one_or_none()
        if c is not None:
            ms = s.query(Match).filter(Match.competition_id == c.id, Match.status == MatchStatus.SCHEDULED).all()
            return {m.external_ids["ps"]: m.id for m in ms}
        c = Competition(sport=Sport.MLB, code=COMP, name="PS fixture", area="US", type="LEAGUE")
        s.add(c)
        s.flush()
        teams = [Team(sport=Sport.MLB, name=f"PS T{i}") for i in range(4)]
        s.add_all(teams)
        s.flush()
        t0 = KO - timedelta(days=70)
        for g in range(60):
            hi, ai = g % 4, (g + 1 + g // 4) % 4
            if hi == ai:
                ai = (ai + 1) % 4
            s.add(Match(sport=Sport.MLB, competition_id=c.id, season=SEASON, utc_date=t0 + timedelta(days=g),
                        status=MatchStatus.FINISHED, home_team_id=teams[hi].id, away_team_id=teams[ai].id,
                        home_score=1 + hi + g % 2, away_score=1 + ai + g % 3))

        def row(sid, season, era):
            s.add(PitcherSeasonStats(player_source_id=sid, player_name=f"P{sid}", season=season, games=10,
                                     games_started=10, innings_pitched=60.0, era=era))
            s.flush()

        row("ps-1", SEASON, 2.00)          # stored first: the old read's dict was overwritten by the 2093 row
        row("ps-1", PRIOR, 9.00)
        row("ps-2", PRIOR, 9.00)           # no 2094 row: no stats this season
        row("ps-3", SEASON, 4.00)
        row("ps-4", SEASON, 4.00)
        out = {}
        for i, (tag, home_sid, away_sid) in enumerate((("TWO", "ps-1", "ps-3"), ("ONLY_PRIOR", "ps-2", "ps-4"))):
            m = Match(sport=Sport.MLB, competition_id=c.id, season=SEASON, utc_date=KO + timedelta(hours=i),
                      status=MatchStatus.SCHEDULED, home_team_id=teams[2 * i].id, away_team_id=teams[2 * i + 1].id,
                      stage="W", external_ids={"ps": tag})
            s.add(m)
            s.flush()
            out[tag] = m.id
            for team, sid in ((m.home_team_id, home_sid), (m.away_team_id, away_sid)):
                s.add(MatchParticipant(match_id=m.id, team_id=team, role="starting_pitcher", kind="probable",
                                       player_source_id=sid, player_name=f"P{sid}"))
        s.add(ModelVersion(sport=Sport.MLB, model_family="mlb_pythag_negbin", version=VERSION, status="candidate",
                           parameters={"baseball_config": {"market_blend_enabled": False}}))
    return out


def _predict():
    from src.db.database import session_scope
    from src.db.schema import Prediction
    from src.walters.training import _generate_predictions_mlb

    ids = _build()
    _generate_predictions_mlb(COMP, SEASON, model_version=VERSION)
    with session_scope() as s:
        return {tag: dict(s.query(Prediction).filter_by(match_id=mid).one().factor_breakdown or {})
                for tag, mid in ids.items()}, ids


def test_the_live_lookup_reads_the_games_season_row():
    fb, _ = _predict()
    two = fb["TWO"]
    assert two["home_starter_known"] is True and two["home_starter_detail"]["raw_era"] == 2.00   # 2094, not 9.00
    assert two["away_starter_detail"]["raw_era"] == 4.00 and two["missing_starter_shrink"] is None


def test_no_row_for_the_games_season_is_no_stats_and_takes_the_shrink():
    fb, _ = _predict()
    only = fb["ONLY_PRIOR"]
    assert only["home_starter_detail"] is None and only["home_starter_known"] is False     # never the 2093 row
    assert only["away_starter_known"] is True and only["missing_starter_shrink"] == 0.88


def test_the_export_pitcher_block_reads_the_same_row():
    from src.db.schema import Sport
    from src.walters.export import _collect_rows

    _, ids = _predict()
    rows = {r["match_id"]: r for r in _collect_rows(sport=Sport.MLB, start_date=KO - timedelta(days=1),
                                                    end_date=KO + timedelta(days=1), competition_code=COMP,
                                                    statuses=None)}
    assert rows[ids["TWO"]]["pitchers"]["home"]["era"] == 2.00
    assert rows[ids["ONLY_PRIOR"]]["pitchers"]["home"]["era"] is None
    assert rows[ids["ONLY_PRIOR"]]["pitchers"]["away"]["era"] == 4.00


def _receipt():
    spec = importlib.util.spec_from_file_location("ps_receipt", "scripts/mlb_pitcher_season_receipt.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _set_detail(match_id, side, era, name=None):
    """Stand in for a prediction the old read made: its stored starter detail (None: no detail) and starter name."""
    from src.db.database import session_scope
    from src.db.schema import Prediction

    with session_scope() as s:
        p = s.query(Prediction).filter_by(match_id=match_id).one()
        fb = dict(p.factor_breakdown or {})
        fb[f"{side}_starter_detail"] = None if era is None else {"raw_era": era, "ip": 60.0, "gs": 10}
        if name is not None:
            fb[f"{side}_pitcher"] = name
        p.factor_breakdown = fb


def _sql(stmt, **params):
    from sqlalchemy import text

    from src.db.database import session_scope

    with session_scope() as s:
        s.execute(text(stmt), params)


def _run_receipt(capsys):
    import os

    mod = _receipt()
    db = os.environ["DATABASE_URL"].replace("sqlite:///", "")
    assert mod.main(["--db", db, "--date", f"{KO:%Y-%m-%d}", "--season", SEASON, "--competition", COMP]) == 0
    return capsys.readouterr().out


def test_the_receipt_reads_what_the_old_read_took_from_the_stored_detail(capsys):
    from src.walters.export import MLB_POSTSEASON_GAME_TYPES

    assert set(_receipt().POSTSEASON) == set(MLB_POSTSEASON_GAME_TYPES)
    _, ids = _predict()
    _set_detail(ids["TWO"], "home", 9.0)            # the old read took the 2093 row
    _set_detail(ids["ONLY_PRIOR"], "home", 9.0)     # the old read took the only (2093) row
    out = _run_receipt(capsys)
    assert "S2 pitchers with more than one season stored: " in out and "seasons 2093,2094: " in out
    assert re.search(r"NEW read: row \d+ season 2094 \(era 2\.0.* the old read could take 1 other season row", out)
    assert "NEW read: none · the old read could take 1 other season row(s)" in out
    s4 = out.split("S4 ")[1]
    assert "2 row(s) on 2 game(s) · 4 side(s)" in s4
    assert "  only the game's season: 2" in s4
    assert "  two seasons: the old read took another: 1  (CHANGED)" in s4
    assert "  another season only: now no stats: 1  (CHANGED)" in s4
    assert "LIVE PROBABILITY CHANGES on 2 game(s)" in s4
    assert re.search(rf"match {ids['TWO']}: prediction \d+ home: row \d+ season 2093 .* -> row \d+ season 2094", s4)
    assert re.search(rf"match {ids['ONLY_PRIOR']}: prediction \d+ home: row \d+ season 2093 .* -> none", s4)

    _set_detail(ids["TWO"], "home", 2.0)            # the old read took the game's season: unchanged
    _set_detail(ids["ONLY_PRIOR"], "home", None)    # no starter component then (opener or no row), none now
    s4 = _run_receipt(capsys).split("S4 ")[1]
    assert "  two seasons: the old read took the game's: 1" in s4 and "  no starter stats then or now: 1" in s4
    assert "live probability changes: none" in s4


def test_the_receipt_never_infers_a_row_it_cannot_place(capsys):
    _, ids = _predict()
    _set_detail(ids["TWO"], "home", 5.5)            # equals no row now (a refresh, a later row): undetermined
    _set_detail(ids["ONLY_PRIOR"], "home", 5.5)     # the one other row does not match: never inferred from it
    s4 = _run_receipt(capsys).split("S4 ")[1]
    assert "  undetermined: 2" in s4 and "live probability changes: none" in s4
    assert s4.count("the stored detail equals no row now") == 2

    _sql("UPDATE pitcher_season_stats SET era = 2.0 WHERE player_source_id = 'ps-1' AND season = :s", s=PRIOR)
    try:                                            # both seasons round to the stored detail: ambiguous
        _set_detail(ids["TWO"], "home", 2.0)
        s4 = _run_receipt(capsys).split("S4 ")[1]
        assert "the stored detail equals rows of two seasons" in s4
    finally:
        _sql("UPDATE pitcher_season_stats SET era = 9.0 WHERE player_source_id = 'ps-1' AND season = :s", s=PRIOR)

    _set_detail(ids["TWO"], "home", 9.0, name="Someone Else")   # the listing was overwritten since
    s4 = _run_receipt(capsys).split("S4 ")[1]
    assert "the stored starter Someone Else is not the one listed now (Pps-1)" in s4
    _set_detail(ids["TWO"], "home", 9.0, name="Pps-1")

    _sql("UPDATE match_participants SET player_source_id = '' WHERE match_id = :m AND player_source_id = 'ps-4'",
         m=ids["ONLY_PRIOR"])
    try:                                            # listed, no source id: its own count, not "no starter listed"
        s4 = _run_receipt(capsys).split("S4 ")[1]
        assert "  listed without a source id: 1" in s4 and "  no starter listed: 0" in s4
    finally:
        _sql("UPDATE match_participants SET player_source_id = 'ps-4' WHERE match_id = :m AND player_source_id = ''",
             m=ids["ONLY_PRIOR"])


def test_the_export_shows_no_stats_where_the_model_had_none():
    from src.db.schema import Sport
    from src.walters.export import _collect_rows

    _, ids = _predict()
    _sql("UPDATE pitcher_season_stats SET innings_pitched = 0 WHERE player_source_id = 'ps-3'")
    try:                                            # the model's filter (era set, innings > 0) applies to the export
        rows = {r["match_id"]: r for r in _collect_rows(sport=Sport.MLB, start_date=KO - timedelta(days=1),
                                                        end_date=KO + timedelta(days=1), competition_code=COMP,
                                                        statuses=None)}
        assert rows[ids["TWO"]]["pitchers"]["away"]["era"] is None
        assert rows[ids["TWO"]]["pitchers"]["home"]["era"] == 2.00
    finally:
        _sql("UPDATE pitcher_season_stats SET innings_pitched = 60.0 WHERE player_source_id = 'ps-3'")
