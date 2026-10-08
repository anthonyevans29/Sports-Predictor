"""Q3 K6 (ARCHITECT 2026-10-08, addendum 13 item 2): a fixed MLB predict input, shared by
tests/test_mlb_kalshi_only_suspended.py and the identical-probabilities receipt. Throwaway DB only
(tests/conftest.py, or a DATABASE_URL the caller sets before importing): never data/.

Three scheduled games, run under two model versions (market blend ON at w 0.5, and OFF):
  BLEND   a priced book close (two complete books)        -> blended when the blend is on
  NOBOOK  no 1X2 odds at all                              -> the model alone
  UNPRICD a 1X2 capture with no complete book (HOME only) -> the model alone (close unpriced)
"""
from datetime import datetime, timedelta

COMP = "MLBK6"
SEASON = "2093"
KO = datetime(2093, 7, 1, 23, 5)
V_ON, V_OFF = "k6-blend-on", "k6-blend-off"
GAMES = ("BLEND", "NOBOOK", "UNPRICD")


def build():
    """Create the fixture once (idempotent). Returns {game: match_id}."""
    from src.db.database import init_db, session_scope
    from src.db.schema import Competition, Match, MatchStatus, ModelVersion, Odds, Sport, Team

    init_db()
    with session_scope() as s:
        c = s.query(Competition).filter_by(code=COMP).one_or_none()
        if c is not None:
            ms = s.query(Match).filter(Match.competition_id == c.id, Match.status == MatchStatus.SCHEDULED).all()
            return {m.external_ids["k6"]: m.id for m in ms}
        c = Competition(sport=Sport.MLB, code=COMP, name="K6 fixture", area="US", type="LEAGUE")
        s.add(c)
        s.flush()
        teams = [Team(sport=Sport.MLB, name=f"K6 T{i}") for i in range(6)]
        s.add_all(teams)
        s.flush()
        # 60 finished games, deterministic scores: team i scores ~1 + i runs, so profiles differ
        t0 = KO - timedelta(days=70)
        for g in range(60):
            hi, ai = g % 6, (g + 1 + g // 6) % 6
            if hi == ai:
                ai = (ai + 1) % 6
            s.add(Match(sport=Sport.MLB, competition_id=c.id, season=SEASON, utc_date=t0 + timedelta(days=g),
                        status=MatchStatus.FINISHED, home_team_id=teams[hi].id, away_team_id=teams[ai].id,
                        home_score=1 + hi + g % 2, away_score=1 + ai + g % 3))
        out = {}
        for i, tag in enumerate(GAMES):
            m = Match(sport=Sport.MLB, competition_id=c.id, season=SEASON, utc_date=KO + timedelta(hours=i),
                      status=MatchStatus.SCHEDULED, home_team_id=teams[2 * i].id, away_team_id=teams[2 * i + 1].id,
                      external_ids={"k6": tag})
            s.add(m)
            s.flush()
            out[tag] = m.id
            at = m.utc_date - timedelta(hours=2)
            if tag == "BLEND":
                for bk, ph, pa in (("bk1", 1.62, 2.40), ("bk2", 1.65, 2.30)):
                    s.add(Odds(match_id=m.id, bookmaker=bk, market="1X2", selection="HOME", price_decimal=ph,
                               captured_at=at, source="k6"))
                    s.add(Odds(match_id=m.id, bookmaker=bk, market="1X2", selection="AWAY", price_decimal=pa,
                               captured_at=at, source="k6"))
            elif tag == "UNPRICD":
                s.add(Odds(match_id=m.id, bookmaker="bk1", market="1X2", selection="HOME", price_decimal=1.80,
                           captured_at=at, source="k6"))
        for v, on in ((V_ON, True), (V_OFF, False)):
            s.add(ModelVersion(sport=Sport.MLB, model_family="mlb_pythag_negbin", version=v, status="candidate",
                               parameters={"baseball_config": {"market_blend_enabled": on, "market_blend_w": 0.5}}))
    return out


def run(version):
    """Predict the fixture under `version`; {game: (p_home, p_away, factor_breakdown)}."""
    from src.db.database import session_scope
    from src.db.schema import Prediction
    from src.walters.training import _generate_predictions_mlb

    ids = build()
    _generate_predictions_mlb(COMP, SEASON, model_version=version)
    with session_scope() as s:
        out = {}
        for tag, mid in ids.items():
            p = s.query(Prediction).filter_by(match_id=mid).one()
            out[tag] = (p.home_win_prob, p.away_win_prob, dict(p.factor_breakdown or {}))
    return out
