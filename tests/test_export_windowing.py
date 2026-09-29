"""Export windowing (architect 2026-09-28): prediction exports default to the
CURRENT SLATE — kickoffs in the next 36 hours — with --week (NFL) / --days N
as the explicit full look-ahead. Ruling 2026-09-28: MLB keeps its ONE
08:00-UTC slate-day (it plays daily; 36h would drag in tomorrow's games before
pitchers and lineups are confirmed). Prediction generation is unchanged: only the
file's rows are scoped. The receipt line prints the window."""
import json
from datetime import datetime, timedelta

import pytest
from click.testing import CliRunner
from sqlalchemy import func, select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Prediction, Sport, Team
from src.timeutil import utc_now_naive


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
    now = utc_now_naive().replace(microsecond=0)
    ids = {}
    with session_scope() as s:
        for sport, code, offsets in ((Sport.NFL, "NFL", {"h10": 10, "h30": 30, "h50": 50, "d7": 168}),
                                     (Sport.MLB, "EWMLB", {"h5": 5, "h30": 30, "h60": 60}),
                                     (Sport.SOCCER, "EWSOC", {"h5": 5, "h30": 30, "h60": 60})):
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
                ids[f"{code}:{key}:ko"] = m.utc_date
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
    mine = {k: v for k, v in games.items() if k.startswith("NFL:") and not k.endswith(":ko")}
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


def _ids(tmp_path, pattern):
    f = sorted((tmp_path / "exports").glob(pattern))[-1]
    return {r["match_id"] for r in json.loads(f.read_text())["predictions"]}


def _mine(games, code):
    return {k: v for k, v in games.items() if k.startswith(code + ":") and not k.endswith(":ko")}


def test_soccer_export_default_is_the_36h_slate(games, tmp_path, monkeypatch):
    mine = _mine(games, "EWSOC")
    before = _pred_count()
    base = ["export-predictions", "--sport", "soccer", "--competition", "EWSOC"]
    r = _run(tmp_path, monkeypatch, base)
    assert r.exit_code == 0, r.output
    assert _ids(tmp_path, "soccer_EWSOC_*.json") == {mine["EWSOC:h5"], mine["EWSOC:h30"]}
    assert "(36h · default: current slate" in " ".join(r.output.split())
    r = _run(tmp_path, monkeypatch, base + ["--days", "3"])
    assert _ids(tmp_path, "soccer_EWSOC_*.json") == set(mine.values())
    assert _pred_count() == before


def test_mlb_export_default_stays_one_slate_day(games, tmp_path, monkeypatch):
    """Ruling 2026-09-28: MLB's default is today's 08:00-UTC slate-day, not 36h."""
    mine = _mine(games, "EWMLB")
    before = _pred_count()
    base = ["export-predictions", "--sport", "mlb", "--competition", "EWMLB"]
    r = _run(tmp_path, monkeypatch, base)
    assert r.exit_code == 0, r.output
    lo = datetime.strptime(utc_now_naive().strftime("%Y-%m-%d"), "%Y-%m-%d").replace(hour=8)
    hi = lo + timedelta(days=1)
    want = {mine[k] for k in mine if lo <= games[k + ":ko"] < hi}
    assert _ids(tmp_path, "mlb_EWMLB_*.json") == want
    assert mine["EWMLB:h60"] not in want                          # never 2.5 days out
    out = " ".join(r.output.split())
    assert "(24h · default: MLB one slate-day" in out and "36h" not in out
    r = _run(tmp_path, monkeypatch, base + ["--days", "3"])
    assert _ids(tmp_path, "mlb_EWMLB_*.json") == set(mine.values())
    assert "(72h · --days 3)" in " ".join(r.output.split())
    # explicit dates keep their slate-day meaning (post-mortems, the soccer chains)
    today = utc_now_naive().strftime("%Y-%m-%d")
    r = _run(tmp_path, monkeypatch, base + ["--start", today, "--end", today])
    assert r.exit_code == 0 and f"--start {today} --end {today}" in " ".join(r.output.split())
    r = _run(tmp_path, monkeypatch, base + ["--days", "2", "--date", today])
    assert "exclusive" in r.output
    assert _pred_count() == before


def test_exports_carry_the_producing_git_sha(games, tmp_path, monkeypatch):
    """Exhibit 1 ruling: every export names its producing SHA (the
    comparator's code-version-skew guard)."""
    from src.walters import provenance
    provenance.git_sha.cache_clear()
    monkeypatch.setenv("SP_GIT_SHA", "abc1234")
    try:
        _run(tmp_path, monkeypatch, ["export-nfl-predictions", "--week"])
        f = sorted((tmp_path / "exports").glob("nfl_predictions_*.json"))[-1]
        assert json.loads(f.read_text())["git_sha"] == "abc1234"
        _run(tmp_path, monkeypatch, ["export-predictions", "--sport", "soccer", "--competition", "EWSOC"])
        f = sorted((tmp_path / "exports").glob("soccer_EWSOC_*.json"))[-1]
        assert json.loads(f.read_text())["git_sha"] == "abc1234"
    finally:
        provenance.git_sha.cache_clear()
