"""Export windowing (architect 2026-09-28): prediction exports default to the
CURRENT SLATE — kickoffs in the next 36 hours — with --week (NFL) / --days N
as the explicit full look-ahead. Prediction generation is unchanged: only the
file's rows are scoped. The receipt line prints the window."""
import json
from datetime import datetime, timedelta

import pytest
from click.testing import CliRunner
from sqlalchemy import func, select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Prediction, Sport, Team


def _comp(s, sport, code):
    c = s.query(Competition).filter_by(sport=sport, code=code).one_or_none()
    if c is None:
        c = Competition(sport=sport, code=code, name=code, area="X", type="LEAGUE")
        s.add(c)
        s.flush()
    return c


@pytest.fixture(scope="module")
def games():
    init_db()
    now = datetime.utcnow().replace(microsecond=0)
    ids = {}
    with session_scope() as s:
        for sport, code, offsets in ((Sport.NFL, "NFL", {"h10": 10, "h30": 30, "h50": 50, "d7": 168}),
                                     (Sport.MLB, "EWMLB", {"h5": 5, "h30": 30, "h60": 60})):
            comp = _comp(s, sport, code)
            for key, h in offsets.items():
                a, b = (Team(sport=sport, name=f"EW-{code}-{key}-{x}", external_ids={"ew": f"{code}{key}{x}"})
                        for x in ("H", "A"))
                s.add_all([a, b])
                s.flush()
                m = Match(sport=sport, competition_id=comp.id, season="2026",
                          utc_date=now + timedelta(hours=h), status=MatchStatus.SCHEDULED,
                          home_team_id=a.id, away_team_id=b.id, external_ids={"ew": f"{code}{key}"})
                s.add(m)
                s.flush()
                s.add(Prediction(match_id=m.id, model_version="ew-test", home_win_prob=0.6,
                                 draw_prob=None, away_win_prob=0.4))
                ids[f"{code}:{key}"] = m.id
    return ids


def _run(tmp_path, monkeypatch, args):
    from cli import cli
    monkeypatch.chdir(tmp_path)
    return CliRunner().invoke(cli, args)


def _pred_count():
    with session_scope() as s:
        return s.execute(select(func.count(Prediction.id))).scalar_one()


def _nfl_ids(tmp_path):
    f = sorted((tmp_path / "exports").glob("nfl_predictions_*.json"))[-1]
    return {r["match_id"] for r in json.loads(f.read_text())["predictions"]}


def test_nfl_default_is_the_36h_slate_and_week_days_widen(games, tmp_path, monkeypatch):
    mine = {k: v for k, v in games.items() if k.startswith("NFL:")}
    before = _pred_count()
    r = _run(tmp_path, monkeypatch, ["export-nfl-predictions"])
    assert r.exit_code == 0, r.output
    got = _nfl_ids(tmp_path) & set(mine.values())
    assert got == {mine["NFL:h10"], mine["NFL:h30"]}              # the current slate only
    out = " ".join(r.output.split())
    assert "window:" in out and "(36h · default: current slate" in out
    r = _run(tmp_path, monkeypatch, ["export-nfl-predictions", "--week"])
    assert _nfl_ids(tmp_path) & set(mine.values()) == set(mine.values())
    assert "--week: full look-ahead" in " ".join(r.output.split())
    r = _run(tmp_path, monkeypatch, ["export-nfl-predictions", "--days", "3"])
    assert _nfl_ids(tmp_path) & set(mine.values()) == {mine["NFL:h10"], mine["NFL:h30"], mine["NFL:h50"]}
    assert "(72h · --days 3)" in " ".join(r.output.split())
    r = _run(tmp_path, monkeypatch, ["export-nfl-predictions", "--week", "--days", "2"])
    assert r.exit_code != 0 and "exclusive" in r.output
    assert _pred_count() == before                                # generation untouched


def _mlb_ids(tmp_path):
    f = sorted((tmp_path / "exports").glob("mlb_EWMLB_*.json"))[-1]
    return {r["match_id"] for r in json.loads(f.read_text())["predictions"]}


def test_mlb_soccer_export_default_is_the_36h_slate(games, tmp_path, monkeypatch):
    mine = {k: v for k, v in games.items() if k.startswith("EWMLB:")}
    before = _pred_count()
    base = ["export-predictions", "--sport", "mlb", "--competition", "EWMLB"]
    r = _run(tmp_path, monkeypatch, base)
    assert r.exit_code == 0, r.output
    assert _mlb_ids(tmp_path) == {mine["EWMLB:h5"], mine["EWMLB:h30"]}
    assert "(36h · default: current slate" in " ".join(r.output.split())
    r = _run(tmp_path, monkeypatch, base + ["--days", "3"])
    assert _mlb_ids(tmp_path) == set(mine.values())
    assert "(72h · --days 3)" in " ".join(r.output.split())
    # explicit dates keep their slate-day meaning (post-mortems, the soccer chains)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    r = _run(tmp_path, monkeypatch, base + ["--start", today, "--end", today])
    assert r.exit_code == 0 and f"--start {today} --end {today}" in " ".join(r.output.split())
    r = _run(tmp_path, monkeypatch, base + ["--days", "2", "--date", today])
    assert "exclusive" in r.output
    assert _pred_count() == before
