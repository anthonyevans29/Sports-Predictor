"""statsapi's pre-game 0-0 is not a score: S / P / PW rows carry null scores (ARCHITECT 2026-10-06, law 4)."""
from src.adapters.mlb_stats_api import MLBStatsAPIAdapter
from src.db.schema import MatchStatus


def _game(code):
    return {"gamePk": 813000, "gameDate": "2026-10-06T22:00:00Z", "season": "2026", "gameType": "D",
            "status": {"codedGameState": code},
            "teams": {"home": {"team": {"id": 144}, "score": 0}, "away": {"team": {"id": 119}, "score": 0}}}


def test_pregame_zero_zero_is_null_and_live_or_final_scores_pass_through():
    a = MLBStatsAPIAdapter.__new__(MLBStatsAPIAdapter)
    for code in ("S", "P", "PW"):
        m = a._parse_game(_game(code), "MLB")
        assert m.status == MatchStatus.SCHEDULED and m.home_score is None and m.away_score is None, code
    live = a._parse_game(_game("I"), "MLB")
    assert live.status == MatchStatus.LIVE and (live.home_score, live.away_score) == (0, 0)
    g = _game("F")
    g["teams"]["home"]["score"], g["teams"]["away"]["score"] = 4, 2
    fin = a._parse_game(g, "MLB")
    assert fin.status == MatchStatus.FINISHED and (fin.home_score, fin.away_score) == (4, 2)
