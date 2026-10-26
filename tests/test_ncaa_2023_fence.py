"""THE 2023 FENCE (ARCHITECT 2026-10-23, addendum 161 item 1): the 2026 fence's mechanism, extended to the D10 second
read's scored set (2023 'regular' games from week 5). Pins:
- the ruling verbatim in the code; the scope (week 5 on; a week or season_type unknown fenced; weeks 1-4 and the
  postseason readable); lifted only by the registry recording the ncaa-elo-v2 run;
- the ingest receipt keeps its counts and withholds every score in the lines of a fenced game, never of a week 1-4
  game, and says how many; nothing is masked once the run is recorded or for another season;
- resync-diff's fenced 2023 ids come from the labels (no label = fenced) and its home-rate line for 2023 is withheld;
- ncaa-audit refuses 2023 among its seasons; the generic walks refuse NCAA 2023; the web views withhold 2023;
- the source probe withholds 2023's rate-and-margin lines and masks the scores of a fenced game's sample line."""
from datetime import datetime

from click.testing import CliRunner

from src.ingestion import ncaa_cfbd as nc
from src.walters import ncaa_backtest as nb

RULING = ("A 2023 FENCE: YES. Once the 2023 games and labels are stored, the second read's scored set (2023 "
          "regular-season games from week 5, D10) is unread until the one run on 11-09, exactly as 2026's scored set "
          "is. The 2026 fence's mechanism extends to 2023 week-5-onward regular games: ncaa-cfbd-coverage, resync-diff "
          "--season 2023 and every other read-only command that would print a home win rate, a result tally or a "
          "score-bearing line on them refuses or masks them under the same guard, with the same wording and the 2023 "
          "scope named. Weeks 1–4 of 2023 (the cold-start warm-up, walked and never scored) stay readable. One small "
          "PR on top of the week branch, before the operator's 2023 block runs.")


def test_the_ruling_verbatim_the_scope_and_the_lift():
    assert nb.V2_2023_FENCE == RULING and nb.V2_SECOND == "2023" and nb.V2_SECOND_MIN_WEEK == 5
    for args, want in ((("2023", "regular", 5), True), (("2023", "regular", 12), True), (("2023", "regular", None), True),
                       (("2023", None, None), True), (("2023", "regular", 4), False), (("2023", "regular", 0), False),
                       (("2023", "postseason", None), False), (("2024", "regular", 9), False),
                       # Codex on #697: only a recognized postseason value, or 'regular' with a week before 5, is read
                       (("2023", None, 3), True), (("2023", "", 3), True), (("2023", "Regular", 3), True),
                       (("2023", "Postseason", None), True), (("2023", "bowl", 2), True)):
        assert nb.fenced_2023(*args, recorded=False) is want, args
    assert nb.fenced_2023("2023", "regular", 9, recorded=True) is False          # the recorded run lifts it
    assert nb.fenced_2023("2023", "regular", 9) is True                         # the committed registry: unrun
    assert nb.mask_scores("2023-09-06 A @ B · ours 21-14, CFBD 14-21 · offset +1.0h") == \
        "2023-09-06 A @ B · ours [score withheld], CFBD [score withheld] · offset +1.0h"
    # Codex on #697: a partial pair (resync-diff prints a missing side as None) is masked too
    assert nb.mask_scores("2023-10-07 match 9 ours 1 @ 2 7-None · provider 11@12 None-21") == \
        "2023-10-07 match 9 ours 1 @ 2 [score withheld] · provider 11@12 [score withheld]"


def _labels(year, recorded, monkeypatch, row_season=None):
    monkeypatch.setattr(nb, "v2_run_recorded", lambda *a, **k: recorded)
    teams = {1: "F A", 2: "F B", 3: "F C", 4: "F D"}

    def ours(mid, h, a, at, hs, as_):
        return nc.Ours(mid, at, str(year), h, a, nc.our_norm(teams[h]), nc.our_norm(teams[a]), hs, as_)
    ours_list = [ours(10, 1, 2, datetime(year, 9, 2, 19), 10, 31),          # week 1: ours reversed vs CFBD
                 ours(11, 3, 4, datetime(year, 10, 7, 19), 14, 28)]         # week 6: ours reversed vs CFBD
    recs = [{"id": 501, "season": year, "seasonType": "regular", "week": 1, "startDate": f"{year}-09-02T19:00:00Z",
             "completed": True, "neutralSite": False, "homeTeam": "F A", "homeClassification": "fbs", "homePoints": 31,
             "awayTeam": "F B", "awayClassification": "fbs", "awayPoints": 10},
            {"id": 502, "season": year, "seasonType": "regular", "week": 6, "startDate": f"{year}-10-07T19:00:00Z",
             "completed": True, "neutralSite": False, "homeTeam": "F C", "homeClassification": "fbs", "homePoints": 28,
             "awayTeam": "F D", "awayClassification": "fbs", "awayPoints": 14},
            {"id": 503, "season": year, "seasonType": "regular", "week": 7, "startDate": f"{year}-10-14T19:00:00Z",
             "completed": True, "neutralSite": False, "homeTeam": "Nowhere", "homeClassification": "fbs",
             "homePoints": 3, "awayTeam": "F D", "awayClassification": "fbs", "awayPoints": 0}]
    if row_season is not None:                                     # a saved payload replayed under another --year
        for r_ in recs:
            r_["season"] = row_season
    keys, _ = nc.discover(recs[0])
    return nc.build_labels(recs, keys, ours_list, teams, {}, year, "fbs")


def test_the_ingest_receipt_masks_scores_on_fenced_games_and_keeps_the_counts(monkeypatch):
    r = _labels(2023, False, monkeypatch)
    assert r.counts["fenced_2023"] == 2 and r.counts["joined"] == 2 and r.counts["score_reversed"] == 2
    week1, week6 = sorted(r.corrections)
    assert "ours 10-31" in week1 and "31-10" in week1                           # weeks 1-4 stay readable
    assert "[score withheld]" in week6 and "14-28" not in week6 and "28-14" not in week6
    assert {x["home_score"] for x in r.rows} == {31, 28}                          # the side table keeps the scores
    text = "\n".join(nc.receipt_lines(r))
    assert "2023 FENCE (ARCHITECT 2026-10-23, addendum 161 item 1): every score withheld" in text and \
        "on 2 in-scope game(s)" in text


def test_nothing_is_masked_once_the_run_is_recorded_or_for_another_season(monkeypatch):
    for year, recorded in ((2023, True), (2024, False)):
        r = _labels(year, recorded, monkeypatch)
        assert r.counts["fenced_2023"] == 0 and not any("[score withheld]" in x for x in r.corrections)
        assert "2023 FENCE" not in "\n".join(nc.receipt_lines(r))


def test_resync_diff_reads_the_fenced_ids_from_the_labels(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db
    from src.db.schema import Competition, Match, MatchStatus, NCAACFBDLabel, Sport, Team
    from src.ingestion import resync_diff as rd

    eng = create_engine(f"sqlite:///{tmp_path / 'f.db'}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                         expire_on_commit=False))
    db.init_db()
    with db.session_scope() as s:
        c = Competition(sport=Sport.NFL, code="NCAA", name="NCAA", area="USA", type="LEAGUE")
        t1, t2 = Team(sport=Sport.NFL, name="R1"), Team(sport=Sport.NFL, name="R2")
        s.add_all([c, t1, t2])
        s.flush()
        ms = {}
        for key, season, wk in (("w2", "2023", 2), ("w8", "2023", 8), ("nolabel", "2023", None), ("y24", "2024", 8)):
            m = Match(sport=Sport.NFL, competition_id=c.id, season=season, utc_date=datetime(int(season), 9, 9),
                      status=MatchStatus.FINISHED, home_team_id=t1.id, away_team_id=t2.id, home_score=7, away_score=3)
            s.add(m)
            s.flush()
            ms[key] = m
            if key != "nolabel":
                s.add(NCAACFBDLabel(match_id=m.id, source="cfbd", source_game_id=m.id, season=season,
                                    orientation="same", home_score=7, away_score=3, season_type="regular", week=wk,
                                    fetched_at=datetime(2026, 10, 24)))
        s.flush()
        got = rd._fenced_2023_ids(s, "NCAA", list(ms.values()))
        assert got == {ms["w8"].id, ms["nolabel"].id}
        assert rd._fenced_2023_ids(s, "NFL", list(ms.values())) == set()
        monkeypatch.setattr(nb, "v2_run_recorded", lambda *a, **k: True)
        assert rd._fenced_2023_ids(s, "NCAA", list(ms.values())) == set()
        s.rollback()


def test_audit_walks_and_web_views_are_fenced_for_2023():
    from cli import cli
    res = CliRunner().invoke(cli, ["ncaa-audit", "--season", "2023"])
    assert res.exit_code == 2 and "ncaa-audit REFUSED (exit 2): 2023 is among its seasons" in res.output
    assert "addendum 161 item 1" in res.output and RULING in res.output
    why = nb.v2_fence_walk("NCAA", "2023")
    assert why and "2023 'regular' games from week 5" in why and RULING in why
    assert nb.v2_fence_walk("NCAA", "2022") is None and nb.v2_fence_walk("NFL", "2023") is None
    assert nb.v2_fence_view("NCAA", "2023") == nb.V2_2023_FENCED and nb.v2_fence_view("NCAA", "2022") is None


def test_the_source_probe_fences_2023(monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("probe", "scripts/ncaa_source_probe.py")
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    assert probe.fenced(2023) and probe.fenced_notice(2023) == nb.V2_2023_FENCED
    assert probe.fenced_year(2099, [{"season": 2023}]) == "2023"
    # Codex on #697: a row whose season is null or empty reads the requested year, so its sample stays masked
    for rec in ({"season": None}, {"season": ""}, {}):
        assert probe.row_season(rec, 2023) == "2023"
    assert probe.row_season({"season": 2024}, 2023) == "2024"
    monkeypatch.setattr(nb, "v2_run_recorded", lambda *a, **k: True)
    assert not probe.fenced(2023)



def test_architect_1026_export_fixtures_refuses_a_range_touching_fenced_2023_games(tmp_path, monkeypatch):
    """ARCHITECT 2026-10-26 15:15 ET: "export-fixtures REFUSES a date range touching fenced 2023 games (format
    untouched)". A range with only week 1-4 games, or another competition, or the recorded run, exports as before."""
    import os

    import pytest
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db
    from cli import cli
    from src.db.schema import Competition, Match, MatchStatus, NCAACFBDLabel, Sport, Team
    from src.walters.export import export_fixtures

    eng = create_engine(f"sqlite:///{tmp_path / 'x.db'}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                         expire_on_commit=False))
    db.init_db()
    monkeypatch.setattr(nb, "v2_run_recorded", lambda *a, **k: False)
    with db.session_scope() as s:
        c = Competition(sport=Sport.NFL, code="NCAA", name="NCAA", area="USA", type="LEAGUE")
        t1, t2 = Team(sport=Sport.NFL, name="X1"), Team(sport=Sport.NFL, name="X2")
        s.add_all([c, t1, t2])
        s.flush()
        for day, wk in ((2, 1), (30, 6)):                           # 2023-09-02 week 1; 2023-09-30 week 6
            m = Match(sport=Sport.NFL, competition_id=c.id, season="2023", utc_date=datetime(2023, 9, day, 18),
                      status=MatchStatus.FINISHED, home_team_id=t1.id, away_team_id=t2.id, home_score=21, away_score=7)
            s.add(m)
            s.flush()
            s.add(NCAACFBDLabel(match_id=m.id, source="cfbd", source_game_id=m.id, season="2023", orientation="same",
                                home_score=21, away_score=7, season_type="regular", week=wk,
                                fetched_at=datetime(2026, 10, 24)))
    out = tmp_path / "ex"
    with pytest.raises(nb.FenceRefused, match="export-fixtures --competition NCAA REFUSED"):
        export_fixtures("NCAA", start="2023-09-01", end="2023-10-01", out_dir=str(out))
    assert not out.exists()                                          # nothing written
    assert os.path.basename(export_fixtures("NCAA", start="2023-09-01", end="2023-09-03", out_dir=str(out))) \
        == "fixtures_NCAA_2023-09-01_to_2023-09-03.json"            # weeks 1-4 only: exported as before
    res = CliRunner().invoke(cli, ["export-fixtures", "--competition", "NCAA", "--start", "2023-09-01",
                                   "--end", "2023-10-01"])
    assert res.exit_code == 2 and "1 fenced game(s)" in res.output
    monkeypatch.setattr(nb, "v2_run_recorded", lambda *a, **k: True)
    export_fixtures("NCAA", start="2023-09-01", end="2023-10-01", out_dir=str(out))


def test_architect_1026_the_ingest_keys_the_fence_on_the_rows_season(monkeypatch):
    """ARCHITECT 2026-10-26 15:15 ET: "the cross-year replay BLOCKS — key the fence on the row's season". 2023 rows
    replayed under --year 2024 are fenced as 2023's; a row with no season reads the requested year."""
    r = _labels(2024, False, monkeypatch, row_season=2023)
    assert r.counts["fenced_2023"] == 2
    assert any("[score withheld]" in x for x in r.corrections)
    r = _labels(2023, False, monkeypatch, row_season="")              # no row season: the requested year
    assert r.counts["fenced_2023"] == 2
