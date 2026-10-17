"""THE 2026 FENCE IN THE WEB APP (ARCHITECT 2026-10-16, addendum 99 item 2(2); the match page, addendum 100 item 1), verbatim: "the web app's hand-typed
`/?league=NCAA` standings show 2026 wins and losses — RULED: fence it, one line, in the next small docs/ops PR (a
league=NCAA view answers "withheld until the ncaa-elo-v2 run is recorded" until then)". And #560's line (addendum 99
item 5: "#560's mkdir line rides with it"). On the throwaway test DB."""
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Sport, Team
from src.walters import ncaa_backtest as nb
from src.web.app import app

ROOT = Path(__file__).resolve().parent.parent
SEASON = "2999"      # above any season another test stores for NCAA, so the view shows it; the fence's season below


@pytest.fixture
def client(tmp_path, monkeypatch):
    """The app, with its preferences file in tmp_path: the home route auto-pins a focus team into
    data/preferences.json when one is stored, and a test never writes under data/ (law 5)."""
    from src.web import preferences
    monkeypatch.setattr(preferences, "_PREFS_PATH", tmp_path / "preferences.json")
    return TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))


def _ncaa_games():
    """Two finished NCAA games of SEASON between two teams named for this test."""
    init_db()
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == "NCAA")).scalars().first()
        if comp is None:
            comp = Competition(sport=Sport.NFL, code="NCAA", name="NCAA", area="USA", type="LEAGUE")
            s.add(comp)
            s.flush()
        h, a = Team(sport=Sport.NFL, name="Fence Owls"), Team(sport=Sport.NFL, name="Fence Hawks")
        s.add_all([h, a])
        s.flush()
        for d, hs, as_ in ((1, 31, 10), (8, 14, 21)):
            s.add(Match(sport=Sport.NFL, competition_id=comp.id, season=SEASON, utc_date=datetime(2999, 9, d, 19),
                        status=MatchStatus.FINISHED, home_team_id=h.id, away_team_id=a.id, home_score=hs,
                        away_score=as_))


def test_the_view_helper_withholds_ncaa_2026_alone_until_the_run_is_recorded(monkeypatch):
    assert nb.v2_fence_view("NCAA", "2026") == nb.V2_FENCED_RATE
    assert "withheld until the ncaa-elo-v2 run is recorded" in nb.V2_FENCED_RATE           # the ruled words
    assert nb.v2_fence_view("ncaa", 2026) == nb.V2_FENCED_RATE
    assert nb.v2_fence_view("NCAA", "2025") is None and nb.v2_fence_view("NFL", "2026") is None
    assert nb.v2_fence_view("PL", "2026") is None and nb.v2_fence_view("NCAA", None) is None
    monkeypatch.setattr(nb, "v2_run_recorded", lambda *a: True)
    assert nb.v2_fence_view("NCAA", "2026") is None                                        # the run recorded


def test_the_league_ncaa_view_answers_withheld_in_place_of_the_table(client, monkeypatch):
    """The league view shows the season it stores last (SEASON here, the fence's season patched to it): the table's
    wins and losses are withheld; the single games of the results list stay (the level ruling)."""
    data_before = (ROOT / "data").exists()
    _ncaa_games()
    with session_scope() as s:                                  # a focus team stored: the route's auto-pin fires
        s.add(Team(sport=Sport.SOCCER, name="Arsenal"))
    monkeypatch.setattr(nb, "V2_TEST", SEASON)
    html = client.get("/?league=NCAA").text
    assert nb.V2_FENCED_RATE in html
    assert "Fence Owls" in html                                       # the recent results: single games stay
    table = html.split("League table", 1)[1].split("Recent results", 1)[0]
    assert "Fence Owls" not in table and nb.V2_FENCED_RATE in table   # no standings row, the notice in its place
    monkeypatch.setattr(nb, "v2_run_recorded", lambda *a: True)       # the run recorded: the table returns
    html = client.get("/?league=NCAA").text
    assert nb.V2_FENCED_RATE not in html
    assert "Fence Owls" in html.split("League table", 1)[1].split("Recent results", 1)[0]
    assert (ROOT / "data").exists() == data_before                     # nothing written under data/ (law 5)


def test_the_ncaa_2026_match_page_withholds_record_form_and_head_to_head_and_keeps_the_games(client, monkeypatch):
    """ARCHITECT 2026-10-16, addendum 100 item 1 (#567, Codex's P1 on #566): "in `/matches/<id>` for an NCAA fixture of
    season 2026, while the ncaa-elo-v2 run is unrecorded, the per-team record (W-D-L, points), the form strip and
    the head-to-head aggregate are replaced by the same withheld notice the league view shows; the fixture's own
    score, the two teams' names and the single-game lists stay (the level ruling)". Any other league untouched; the
    run recorded lifts it."""
    _ncaa_games()
    monkeypatch.setattr(nb, "V2_TEST", SEASON)
    with session_scope() as s:
        mid = s.execute(select(Match.id).join(Team, Team.id == Match.home_team_id).where(
            Team.name == "Fence Owls", Match.season == SEASON).order_by(Match.utc_date.desc())).scalars().first()
    html = client.get(f"/matches/{mid}").text
    assert html.count(nb.V2_FENCED_RATE) == 3                          # each side's record and form, and the h2h line
    assert "W–" not in html and " pts" not in html and "Last 5" not in html and "Draws" not in html
    assert "Fence Owls" in html and "Fence Hawks" in html              # the two teams
    assert "14" in html and "21" in html and "31" in html and "10" in html   # the fixture's and the listed games' scores
    assert "Head-to-head" in html                                      # the meetings list stays
    monkeypatch.setattr(nb, "v2_run_recorded", lambda *a: True)        # the run recorded: every figure returns
    html = client.get(f"/matches/{mid}").text
    assert nb.V2_FENCED_RATE not in html and "W–" in html and "Last 5" in html and "Draws" in html


def test_another_leagues_match_page_is_untouched(client, monkeypatch):
    """The same season and teams under another competition: no notice, every figure shown."""
    monkeypatch.setattr(nb, "V2_TEST", SEASON)
    init_db()
    with session_scope() as s:
        comp = Competition(sport=Sport.SOCCER, code="FNCX", name="Fence control", area="X", type="LEAGUE")
        h, a = Team(sport=Sport.SOCCER, name="Control Owls"), Team(sport=Sport.SOCCER, name="Control Hawks")
        s.add_all([comp, h, a])
        s.flush()
        m = Match(sport=Sport.SOCCER, competition_id=comp.id, season=SEASON, utc_date=datetime(2999, 9, 2, 19),
                  status=MatchStatus.FINISHED, home_team_id=h.id, away_team_id=a.id, home_score=2, away_score=1)
        s.add(m)
        s.flush()
        mid = m.id
    html = client.get(f"/matches/{mid}").text
    assert nb.V2_FENCED_RATE not in html and "W–" in html


def test_the_release_notes_step_makes_logs_first():
    """#560 (Codex on #558, round 2): a fresh or cleaned checkout has no logs/, so step 2 makes it first."""
    text = (ROOT / "docs" / "RELEASES.md").read_text()
    assert "mkdir -p logs && python3 scripts/release_notes.py --to <sha> > logs/release_notes_vX.Y.Z.txt" in text
