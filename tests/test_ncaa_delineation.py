"""DELINEATION (ARCHITECT 2026-10-07, daily-class): college football rides the
NFL code path (Sport.NFL family, competition NCAA). "Every export row and console
line names the competition. A college row carries competition NCAA and a family
field (NFL or NCAAF); nothing the operator reads labels a college game NFL."
Labels only: no probability, policy or grading logic is touched here."""
import json
import re
from datetime import datetime, timedelta

import pytest
from click.testing import CliRunner

from src.adapters.normalized import NormalizedOdds
from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Odds, OddsSnapshot, Sport, Team
from src.ingestion import service as svc
from src.timeutil import utc_now_naive

NOW = datetime(2032, 3, 3, 12, 0)   # far from other tests' dates


def _comp(s, code):
    c = s.query(Competition).filter_by(code=code).one_or_none()
    if c is None:
        c = Competition(sport=Sport.NFL, code=code, name=code, area="US", type="LEAGUE")
        s.add(c)
        s.flush()
    return c


def _game(s, code, tag, when, gid=None):
    h, a = Team(sport=Sport.NFL, name=f"DL {tag} H"), Team(sport=Sport.NFL, name=f"DL {tag} A")
    s.add_all([h, a])
    s.flush()
    m = Match(sport=Sport.NFL, competition_id=_comp(s, code).id, season="2026",
              status=MatchStatus.SCHEDULED, utc_date=when, home_team_id=h.id, away_team_id=a.id,
              external_ids={"api_american_football": gid} if gid else {"dltest": tag})
    s.add(m)
    s.flush()
    return m.id


def _cleanup(ids):
    with session_scope() as s:
        s.query(Odds).filter(Odds.match_id.in_(ids)).delete(synchronize_session=False)
        s.query(OddsSnapshot).filter(OddsSnapshot.match_id.in_(ids)).delete(synchronize_session=False)
        s.query(Match).filter(Match.id.in_(ids)).delete(synchronize_session=False)


# ------------------------------------------------------------ console lines --

@pytest.fixture
def football_window():
    init_db()
    with session_scope() as s:
        soon = utc_now_naive() + timedelta(days=3)
        ids = {"nfl": _game(s, "NFL", "pro", soon, "dl-nfl-1"),
               "ncaa": _game(s, "NCAA", "college", soon + timedelta(minutes=5), "dl-ncaa-1")}
    yield ids
    _cleanup(list(ids.values()))


def test_odds_sync_console_names_each_competition(football_window, monkeypatch):
    def list_odds(self, gid):
        if gid == "dl-ncaa-1":
            return []                                      # college board not posted yet
        return [NormalizedOdds(source="api_american_football", match_source_id=gid, market="1X2",
                               selection=sel, bookmaker="bk", price_decimal=px,
                               captured_at=utc_now_naive()) for sel, px in (("HOME", 1.8), ("AWAY", 2.1))]
    monkeypatch.setattr("src.adapters.api_american_football.APIAmericanFootballAdapter.list_odds", list_odds)
    monkeypatch.setattr(svc, "_odds_sleep", lambda x: None)
    msgs = []
    r = svc.sync_odds_nfl(progress=msgs.append)
    head = msgs[0]
    assert re.search(r"NCAA odds: \d+ upcoming games", head), head
    assert re.search(r"NFL odds: \d+ upcoming games", head), head
    # the per-game line for the college game names NCAA, never NFL
    assert any(m.strip() == "· NCAA: no odds yet for DL college A @ DL college H" for m in msgs), msgs
    assert r["games_by_competition"].get("NFL", 0) >= 1
    assert "NCAA" not in r["games_by_competition"]       # nothing priced for college this run


def test_cli_odds_summary_names_the_competitions_priced(monkeypatch):
    import cli
    monkeypatch.setattr(svc, "sync_odds_nfl", lambda progress=None: {
        "created": 8, "games": 3, "snapshots": 6, "games_by_competition": {"NCAA": 2, "NFL": 1}})
    res = CliRunner().invoke(cli.cli, ["sync-odds-football"])
    assert res.exit_code == 0, res.output
    assert "Football odds: created=8 across 3 games (NCAA 2 · NFL 1)" in res.output
    assert "NFL+NCAA" not in res.output


# -------------------------------------------------------------- export rows --

@pytest.fixture
def card_games():
    init_db()
    with session_scope() as s:
        ids = {"nfl": _game(s, "NFL", "cardpro", NOW + timedelta(hours=2)),
               "ncaa": _game(s, "NCAA", "cardcollege", NOW + timedelta(hours=3))}
    yield ids
    _cleanup(list(ids.values()))


def test_window_card_college_row_names_ncaa(card_games, tmp_path):
    from src.walters import window
    card = window.build_card(now=NOW, hours=24, export_dir=str(tmp_path))
    rows = {r["match_id"]: r for r in card["fixtures"]}
    college, pro = rows[card_games["ncaa"]], rows[card_games["nfl"]]
    assert college["competition"] == "NCAA" and college["family"] == "NCAAF"
    assert college["sport"] == "nfl"            # stored family value kept: sp_run keys freshen on it
    assert pro["competition"] == "NFL" and pro["family"] == "NFL" and pro["sport"] == "nfl"


def test_fixtures_export_rows_carry_competition_and_family(card_games, tmp_path):
    from src.walters.export import export_fixtures
    path = export_fixtures("NCAA", start=NOW.strftime("%Y-%m-%d"), end=NOW.strftime("%Y-%m-%d"),
                           out_dir=str(tmp_path))
    doc = json.loads(open(path).read())
    row = next(r for r in doc["fixtures"] if r["match_id"] == card_games["ncaa"])
    assert row["competition"] == "NCAA" and row["family"] == "NCAAF"
    assert "NCAA" in path


def test_window_card_cli_line_names_competitions(card_games, tmp_path, monkeypatch):
    import cli
    from src.walters import window
    real = window.build_card
    monkeypatch.setattr(window, "build_card", lambda hours=24: real(now=NOW, hours=hours,
                                                                    export_dir=str(tmp_path)))
    monkeypatch.setattr(window, "write_card", lambda card: str(tmp_path / "window_24h.json"))
    res = CliRunner().invoke(cli.cli, ["window-card"])
    assert res.exit_code == 0, res.output
    assert "games 2 (NCAA 1 · NFL 1)" in res.output, res.output


def test_the_cockpit_window_table_renders_family_before_sport():
    # Codex on #346: the repo Cockpit labels a college window row by family ("NCAAF · NCAA"), never "NFL"
    from pathlib import Path
    html = (Path(__file__).resolve().parents[1] / "tools" / "cockpit.html").read_text()
    assert 'String(r.f.family||r.f.sport||"").toUpperCase())} · ${esc(r.f.competition)}' in html
