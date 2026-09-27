"""Pro Bowl / all-star exclusion at the NFL adapter (architect ruling
2026-09-27, H1a compare: +1 game/season and 34 teams on the fresh host).
Every excluded row is printed as a receipt; competitive games are untouched."""
from src.adapters.api_american_football import APIAmericanFootballAdapter


def _game(gid, home, away, week="Week 5", stage="Regular Season"):
    return {"game": {"id": gid, "date": {"timestamp": 1790000000}, "week": week,
                     "stage": stage, "status": {"short": "FT"}},
            "teams": {"home": {"id": gid * 10, "name": home},
                      "away": {"id": gid * 10 + 1, "name": away}},
            "scores": {"home": {"total": 24}, "away": {"total": 17}}}


def test_pro_bowl_and_all_star_rows_excluded_and_printed(monkeypatch, capsys):
    rows = [_game(1, "Kansas City Chiefs", "Buffalo Bills"),
            _game(2, "AFC", "NFC", week="Pro Bowl", stage="Post Season"),
            _game(3, "NFC", "AFC", week="Week 18"),                       # names alone
            _game(4, "East All-Stars", "West All-Stars", week="Bowl"),    # all-star marker
            _game(5, "Green Bay Packers", "Detroit Lions", stage="Post Season")]
    a = APIAmericanFootballAdapter()
    monkeypatch.setattr(a, "_get", lambda path, params=None: {"response": rows})
    out = a.list_matches("NFL", season="2025")
    assert [m.source_id for m in out] == ["1", "5"]  # playoffs stay; exhibitions go
    printed = capsys.readouterr().out
    assert printed.count("excluded non-competitive game:") == 3
    assert "'AFC' v 'NFC'" in printed and "week='Pro Bowl'" in printed


def test_conference_teams_not_registered(monkeypatch, capsys):
    teams = [{"team": {"id": 1, "name": "Kansas City Chiefs", "code": "KC"}},
             {"team": {"id": 99, "name": "AFC"}}, {"team": {"id": 98, "name": "NFC"}}]
    a = APIAmericanFootballAdapter()
    monkeypatch.setattr(a, "_get", lambda path, params=None: {"response": teams})
    out = a.list_teams("NFL", season="2025")
    assert [t.name for t in out] == ["Kansas City Chiefs"]
    assert capsys.readouterr().out.count("excluded non-competitive team:") == 2
