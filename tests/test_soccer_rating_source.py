"""A DEFAULT RATING IS LABELLED, AND IT GETS NO CALL (ARCHITECT 2026-10-10, addendum 36 item 2, RULED):
"Every soccer prediction says, for each side, where its rating came from: the model's table, or the default because
the team is not in the table. It is recorded per side as model or default, in the prediction's factor_breakdown and
in the export's input_quality. A row with a default on either side gets no Desk call and no value shadow: it is a
PASS, and its reason names the team. desk_meta says the rule is on. No probability changes."

The finding (addendum 36 item 1): the host's production soccer row was seeded from the laptop, keyed by the laptop's
team ids, so 16 of 20 PL slots read the default 1500.0 and 4 read another league's club."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, ModelVersion, Prediction, Sport, Team
from src.walters import desk_policy as dp
from src.walters.export import export_predictions
from src.walters.training import _generate_predictions_soccer

CODE, SEASON, MV = "RSL", "2091/92", "v-rs"
KICK = datetime(2091, 10, 20, 15, 0)


@pytest.fixture(scope="module")
def world():
    """A league with four clubs: Alpha, Beta and Gamma in the model's table, Delta not (the host's case)."""
    init_db()
    with session_scope() as s:
        comp = Competition(sport=Sport.SOCCER, code=CODE, name="Rating Source League", area="X", type="LEAGUE")
        s.add(comp)
        teams = [Team(sport=Sport.SOCCER, name=f"RS {n}") for n in ("Alpha", "Beta", "Gamma", "Delta")]
        s.add_all(teams)
        s.flush()
        a, b, g, d = (t.id for t in teams)
        t0 = datetime(2091, 8, 10, 15, 0)
        results = [(a, b, 2, 1), (g, d, 1, 1), (b, g, 0, 2), (d, a, 1, 3), (a, g, 1, 0), (b, d, 2, 2),
                   (g, a, 1, 1), (d, b, 0, 1), (b, a, 1, 1), (d, g, 2, 1), (g, b, 3, 0), (a, d, 2, 0)]
        for i, (h, aw, hs, as_) in enumerate(results):
            s.add(Match(sport=Sport.SOCCER, competition_id=comp.id, season=SEASON,
                        utc_date=t0 + timedelta(days=4 * i), status=MatchStatus.FINISHED,
                        home_team_id=h, away_team_id=aw, home_score=hs, away_score=as_))
        both = Match(sport=Sport.SOCCER, competition_id=comp.id, season=SEASON, utc_date=KICK,
                     status=MatchStatus.SCHEDULED, home_team_id=a, away_team_id=b)
        one = Match(sport=Sport.SOCCER, competition_id=comp.id, season=SEASON, utc_date=KICK + timedelta(hours=2),
                    status=MatchStatus.SCHEDULED, home_team_id=g, away_team_id=d)
        s.add_all([both, one])
        s.add(ModelVersion(
            sport=Sport.SOCCER, model_family="soccer_elo_poisson", version=MV, status="candidate",
            parameters={"elo": {"league": {"ratings": {a: 1610.0, b: 1540.0, g: 1580.0}},
                                "cup": {"ratings": {}}},
                        "team_to_league": {a: CODE, b: CODE, g: CODE}, "contexts": {}, "poisson": {}}))
        s.flush()
        return {"both": both.id, "one": one.id, "teams": {"a": a, "b": b, "g": g, "d": d}}


def test_report_rows_label_each_side(world):
    rows = {r["match_id"]: r for r in _generate_predictions_soccer(CODE, SEASON, model_version=MV,
                                                                    include_finished=True)}
    assert (rows[world["both"]]["home_rating_source"], rows[world["both"]]["away_rating_source"]) == ("model", "model")
    assert (rows[world["one"]]["home_rating_source"], rows[world["one"]]["away_rating_source"]) == ("model", "default")
    assert rows[world["one"]]["away_league_elo"] == 1500.0          # EloState.get's starting rating


def test_factor_breakdown_and_export_carry_the_label_and_the_desk_passes_the_default_row(world):
    n = _generate_predictions_soccer(CODE, SEASON, model_version=MV)
    assert n == 2
    with session_scope() as s:
        fb = {p.match_id: p.factor_breakdown for p in s.execute(
            select(Prediction).where(Prediction.match_id.in_([world["both"], world["one"]]))).scalars()}
    assert (fb[world["both"]]["home_rating_source"], fb[world["both"]]["away_rating_source"]) == ("model", "model")
    assert (fb[world["one"]]["home_rating_source"], fb[world["one"]]["away_rating_source"]) == ("model", "default")

    doc = json.loads(export_predictions(sport=Sport.SOCCER, start_date=KICK - timedelta(days=1),
                                        end_date=KICK + timedelta(days=1), competition_code=CODE,
                                        statuses=[MatchStatus.SCHEDULED], desk=True))
    rows = {r["match_id"]: r for r in doc["predictions"]}
    assert rows[world["both"]]["input_quality"]["rating_source"] == {"home": "model", "away": "model"}
    assert rows[world["one"]]["input_quality"]["rating_source"] == {"home": "model", "away": "default"}
    assert doc["desk_meta"]["default_rating_rule"] is True
    dk = rows[world["one"]]["desk"]
    assert (dk["call"], dk["units"], dk["pass_kind"]) == ("PASS", 0, "default_rating")
    assert "RS Delta" in dk["reason"] and "RS Gamma" not in dk["reason"]
    assert dk["order"] is None and dk["value_shadow"] is None and dk["exec"] is None
    assert rows[world["both"]]["desk"]["pass_kind"] != "default_rating"


# ---- the Desk rule on hand-built rows (the export shape) -------------------------------------------------------

NOW = datetime(2091, 10, 20, 9, 0, tzinfo=timezone.utc)


def pl(home, away, src, p_home=0.62, fair_h=0.48):
    r = {"home_team": home, "away_team": away, "utc_date": "2091-10-20T15:00:00", "competition": "PL",
         "prediction": {"probabilities": {"home_win": p_home, "draw": 0.2, "away_win": round(0.8 - p_home, 4)},
                        "tier": "lean"},
         "market": {"bookmaker_count": 9,
                    "selections": {"HOME": {"fair_prob": fair_h}, "DRAW": {"fair_prob": 0.27},
                                   "AWAY": {"fair_prob": round(0.73 - fair_h, 4)}}}}
    if src is not None:
        r["input_quality"] = {"rating_source": src}
    return r


def desk(*rows):
    doc = {"sport": "soccer", "predictions": list(rows)}
    dp.annotate(doc, now=NOW)
    return {r["home_team"]: r["desk"] for r in doc["predictions"]}, doc


def test_a_default_on_either_side_is_a_pass_naming_the_team():
    d, doc = desk(pl("Leeds", "Arsenal", {"home": "default", "away": "model"}),
                  pl("Fulham", "Ipswich", {"home": "model", "away": "default"}),
                  pl("Everton", "Hull", {"home": "default", "away": "default"}))
    for k in ("Leeds", "Fulham", "Everton"):
        assert (d[k]["call"], d[k]["units"], d[k]["pass_kind"]) == ("PASS", 0, "default_rating")
        assert d[k]["order"] is None and d[k]["value_shadow"] is None and d[k]["exec"] is None
    assert "Leeds" in d["Leeds"]["reason"] and "Arsenal" not in d["Leeds"]["reason"]
    assert "Ipswich" in d["Fulham"]["reason"] and "Fulham" not in d["Fulham"]["reason"]
    assert "Everton and Hull" in d["Everton"]["reason"]
    assert doc["desk_meta"]["default_rating_rule"] is True


def test_a_row_with_both_sides_in_the_table_is_unchanged():
    labelled, _ = desk(pl("Spurs", "United", {"home": "model", "away": "model"}))
    unlabelled, _ = desk(pl("Spurs", "United", None))
    with dp.default_rating_rule_off():
        off, _ = desk(pl("Spurs", "United", {"home": "model", "away": "model"}))
    assert labelled["Spurs"] == unlabelled["Spurs"] == off["Spurs"]
    assert labelled["Spurs"]["call"] != "PASS" or labelled["Spurs"]["pass_kind"] != "default_rating"


def test_the_rule_off_restores_the_call():
    with dp.default_rating_rule_off():
        off, doc = desk(pl("Leeds", "Arsenal", {"home": "default", "away": "model"}))
    on, _ = desk(pl("Leeds", "Arsenal", {"home": "model", "away": "model"}))
    assert off["Leeds"] == on["Leeds"]
    assert doc["desk_meta"]["default_rating_rule"] is False


def test_probabilities_are_untouched_by_the_label(world):
    rows = {r["match_id"]: r for r in _generate_predictions_soccer(CODE, SEASON, model_version=MV,
                                                                    include_finished=True)}
    r = rows[world["one"]]
    # the default row is priced exactly as before the label: the starting rating, nothing else moved
    assert r["away_league_elo"] == 1500.0 and abs(r["p_home"] + r["p_draw"] + r["p_away"] - 1) < 1e-9


def test_the_csv_export_carries_both_sides_rating_source(world):
    """Codex on #411: `export-predictions --format csv` keeps the label."""
    import csv
    import io
    _generate_predictions_soccer(CODE, SEASON, model_version=MV)
    out = export_predictions(sport=Sport.SOCCER, start_date=KICK - timedelta(days=1),
                             end_date=KICK + timedelta(days=1), competition_code=CODE,
                             statuses=[MatchStatus.SCHEDULED], output_format="csv")
    rows = {int(r["match_id"]): r for r in csv.DictReader(io.StringIO(out))}
    assert (rows[world["one"]]["home_rating_source"], rows[world["one"]]["away_rating_source"]) == ("model", "default")
    assert (rows[world["both"]]["home_rating_source"], rows[world["both"]]["away_rating_source"]) == ("model", "model")
