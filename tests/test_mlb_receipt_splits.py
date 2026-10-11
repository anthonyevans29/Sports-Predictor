"""#354 (ARCHITECT 2026-10-09, addendum 31 item 2): the MLB actionable receipt's toss-up splits.
"The parent cohort is the toss-up tier of the regular season, included rows ... Two splits of that cohort and no
other: by the calendar month of the first pitch's date in America/New_York, and by pick side, HOME or AWAY."
Synthetic rows / throwaway DB only (season "2082" is this file's own)."""
from datetime import datetime, timedelta

from click.testing import CliRunner

from src.db.database import init_db, session_scope
from src.db.schema import (Competition, Match, MatchStatus, Odds, OddsSnapshot, Prediction, PredictionOutcome,
                           Result, Sport, Team)
from src.walters import mlb_actionable as MA

SEASON = "2082"
NO_CLOSE = "no close (no pre-first-pitch capture, or unpriced)"
KALSHI = "close is not a book close (reference=kalshi_only)"


def _comp(s):
    c = s.query(Competition).filter_by(code="MLB").one_or_none()
    if c is None:
        c = Competition(sport=Sport.MLB, code="MLB", name="MLB", area="US", type="LEAGUE")
        s.add(c)
        s.flush()
    return c


def _game(s, tag, *, ko, stage, p_home, home_won, fair_home=None, kalshi=False):
    c = _comp(s)
    h, a = Team(sport=Sport.MLB, name=f"RS {tag} H"), Team(sport=Sport.MLB, name=f"RS {tag} A")
    s.add_all([h, a])
    s.flush()
    m = Match(sport=Sport.MLB, competition_id=c.id, season=SEASON, stage=stage, utc_date=ko,
              status=MatchStatus.FINISHED, home_team_id=h.id, away_team_id=a.id,
              home_score=5 if home_won else 1, away_score=1 if home_won else 5)
    s.add(m)
    s.flush()
    p = Prediction(match_id=m.id, model_version="mlb_test_v2", computed_at=ko - timedelta(hours=3),
                   home_win_prob=p_home, draw_prob=None, away_win_prob=1 - p_home, factor_breakdown={})
    s.add(p)
    s.flush()
    top_home = p_home >= 1 - p_home
    s.add(PredictionOutcome(prediction_id=p.id, actual_result=Result.HOME if home_won else Result.AWAY,
                            top_pick_hit=(top_home == home_won)))
    if fair_home is not None:      # one complete zero-vig book: de-vig returns fair_home exactly
        for sel, f in (("HOME", fair_home), ("AWAY", 1 - fair_home)):
            s.add(Odds(match_id=m.id, bookmaker="bk1", market="1X2", selection=sel, price_decimal=1 / f,
                       captured_at=ko - timedelta(minutes=30)))
    if kalshi:
        s.add(OddsSnapshot(match_id=m.id, market="ML", selection="HOME", devig_prob=0.5, n_books=1,
                           captured_at=ko - timedelta(hours=1), source="kalshi", yes_bid=0.49, yes_ask=0.50))
    s.flush()


JUL, AUG = datetime(2082, 7, 10, 23, 5), datetime(2082, 8, 15, 23, 5)
ROLL = datetime(2082, 8, 1, 2, 10)          # 2082-08-01 02:10 UTC = 2082-07-31 22:10 ET: a July game


def _seed():
    init_db()
    with session_scope() as s:
        if s.query(Match).filter_by(season=SEASON).count():
            return
        _game(s, "jul-away-hit", ko=JUL, stage="R", p_home=0.48, home_won=False, fair_home=0.50)   # AWAY 0.52 W
        _game(s, "roll-home-hit", ko=ROLL, stage="R", p_home=0.51, home_won=True, fair_home=0.50)  # HOME 0.51 W
        _game(s, "aug-home-miss", ko=AUG, stage="R", p_home=0.52, home_won=False, fair_home=0.49)  # HOME 0.52 L
        _game(s, "aug-away-noclose", ko=AUG, stage="R", p_home=0.49, home_won=True)                # left out
        _game(s, "jul-home-kalshi", ko=JUL, stage="R", p_home=0.50, home_won=True, kalshi=True)    # left out
        _game(s, "aug-lean", ko=AUG, stage="R", p_home=0.58, home_won=True, fair_home=0.54)        # lean: not cohort
        _game(s, "post-hit", ko=AUG, stage="D", p_home=0.51, home_won=True, fair_home=0.50)        # postseason
        _game(s, "post-noclose", ko=AUG, stage="D", p_home=0.48, home_won=True)                    # postseason, out


def _rows():
    _seed()
    with session_scope() as s:
        return MA.collect(s, season=SEASON)


def _cells(split):
    return {k: c for k, c, _ in split["cells"]}


def _out(split):
    return {k: lo for k, _, lo in split["cells"]}


def test_month_split_by_the_first_pitchs_et_date():
    assert MA.month_et(ROLL) == "2082-07" and ROLL.strftime("%Y-%m") == "2082-08"     # ET, not UTC
    assert MA.month_et(None) == MA.NO_DATE
    res = MA.receipt(_rows(), b=200)
    sp = res["splits"]
    assert sp["parent"]["n"] == 3 and sp["parent"]["wins"] == 2
    reg = {(t, bk): c for t, bk, c in res["tables"]["regular"]["cells"]}
    assert sp["parent"]["n"] == reg[("toss-up", "all")]["n"]                  # the receipt's own toss-up row
    month = sp["month"]
    cells = _cells(month)
    assert list(cells) == ["2082-07", "2082-08", MA.NO_DATE]                  # no-date cell printed, empty here
    assert (cells["2082-07"]["n"], cells["2082-07"]["wins"]) == (2, 2)        # the rollover game is July's
    assert (cells["2082-08"]["n"], cells["2082-08"]["wins"]) == (1, 0)
    assert cells[MA.NO_DATE]["n"] == 0
    assert month["sum"] == {"n": 3, "wins": 2} and month["ok"]
    assert _out(month) == {"2082-07": {KALSHI: 1}, "2082-08": {NO_CLOSE: 1}, MA.NO_DATE: {}}
    assert sp["left_out"] == {KALSHI: 1, NO_CLOSE: 1}
    assert cells["2082-07"]["hit"] == 1.0 and cells["2082-07"]["fair_p"] == 0.5     # what a tier row prints


def test_pick_side_split_home_and_away():
    sp = MA.receipt(_rows(), b=200)["splits"]
    side = sp["side"]
    cells = _cells(side)
    assert list(cells) == ["HOME", "AWAY"]
    assert (cells["HOME"]["n"], cells["HOME"]["wins"]) == (2, 1)
    assert (cells["AWAY"]["n"], cells["AWAY"]["wins"]) == (1, 1)
    assert side["sum"] == {"n": 3, "wins": 2} and side["ok"] and sp["ok"]
    assert _out(side) == {"HOME": {KALSHI: 1}, "AWAY": {NO_CLOSE: 1}}


def test_a_row_with_no_first_pitch_date_is_a_cell_of_its_own_never_dropped():
    rows = _rows()
    close = {"fair": {"HOME": 0.5, "AWAY": 0.5}, "reference": "books", "source": "odds"}
    nd = MA.grade_row(match_id=-1, stage_raw="R", p_home=0.51, p_away=0.49, factor_breakdown={}, hit=True,
                      close=close)
    nd_out = MA.grade_row(match_id=-2, stage_raw="R", p_home=0.51, p_away=0.49, factor_breakdown={}, hit=False,
                          close=None)
    nd["first_pitch"] = nd_out["first_pitch"] = None
    sp = MA.receipt(rows + [nd, nd_out], b=200)["splits"]
    assert sp["parent"]["n"] == 4 and sp["parent"]["wins"] == 3
    c = _cells(sp["month"])[MA.NO_DATE]
    assert c["n"] == 1 and c["wins"] == 1
    assert _out(sp["month"])[MA.NO_DATE] == {NO_CLOSE: 1}
    assert sp["month"]["ok"] and sp["side"]["ok"]


def test_postseason_toss_up_rows_get_one_line_never_pooled():
    res = MA.receipt(_rows(), b=200)
    post = res["splits"]["postseason"]
    assert post["n"] == 1 and post["wins"] == 1 and post["left_out"] == {NO_CLOSE: 1}
    for name in ("month", "side"):                 # not in any cell
        assert sum(c["n"] for _, c, _ in res["splits"][name]["cells"]) == 3
    text = MA.format_receipt(res, season=SEASON, run_stamp="t")
    lines = [ln for ln in text.splitlines() if ln.startswith("| postseason toss-up |")]
    assert len(lines) == 1 and "| 1 | 1 |" in lines[0] and f"{NO_CLOSE}: 1" in lines[0]


def test_cli_prints_the_splits_and_the_sums_beside_the_parent(tmp_path):
    from cli import cli
    _seed()
    out = tmp_path / "r.md"
    res = CliRunner().invoke(cli, ["mlb-actionable-receipt", "--season", SEASON, "--out", str(out)])
    assert res.exit_code == 0, res.output
    txt = out.read_text()
    assert "## Toss-up, regular season, by calendar month of first pitch (America/New_York)" in txt
    assert "## Toss-up, regular season, by pick side" in txt
    assert "## Toss-up, postseason (one line, never pooled)" in txt
    assert txt.count("- Σ cells: games 3, wins 2 · parent: games 3, wins 2 · reconciled") == 2
    assert "| 2082-07 | 2 | 2 |" in txt and "| AWAY | 1 | 1 |" in txt
    assert f"| {MA.NO_DATE} | 0 | 0 |" in txt


def test_cli_refuses_when_the_cells_do_not_sum_to_the_parent(tmp_path, monkeypatch):
    from cli import cli
    _seed()
    monkeypatch.setattr(MA, "SIDES", ("HOME",))      # inject the mismatch: AWAY rows fall out of the side split
    out = tmp_path / "r.md"
    res = CliRunner().invoke(cli, ["mlb-actionable-receipt", "--season", SEASON, "--out", str(out)])
    assert res.exit_code != 0
    assert "- Σ cells: games 2, wins 1 · parent: games 3, wins 2 · DIFFERS" in res.output
    assert "REFUSED" in res.output and not out.exists()
