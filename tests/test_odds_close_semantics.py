"""#167 (ARCHITECT-RULE 2026-10-01, priority): the close is the LAST
pre-kickoff capture session — never an average of every row the odds table
accumulated; sync_odds REPLACES per (match, source), keeps `line`, appends
history to odds_snapshots; the CLV restate is a dry-run unless --apply with a
verified .backup. Throwaway DB, fake adapter, private competition codes."""
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from click.testing import CliRunner
from sqlalchemy import select

from src.adapters.normalized import NormalizedOdds
from src.db.database import init_db, session_scope
from src.db.schema import (Competition, Match, MatchStatus, Odds, OddsSnapshot, Prediction,
                           PredictionOutcome, Sport, Team)
from src.walters import clv_restate as cr
from src.walters.close import close_1x2, last_capture

KO = datetime(2039, 3, 1, 15, 0)


def row(book, sel, price, at, market="1X2", line=None):
    return NS(bookmaker=book, selection=sel, price_decimal=price, captured_at=at, market=market, line=line)


def test_last_capture_session_rules():
    early, late = KO - timedelta(days=2), KO - timedelta(hours=1)
    rows = [row("a", "HOME", 2.0, early), row("b", "HOME", 2.2, early),               # old session
            row("a", "HOME", 1.8, late), row("a", "HOME", 1.7, late + timedelta(seconds=3)),
            row("c", "HOME", 1.9, late + timedelta(microseconds=7)),
            row("a", "HOME", 1.1, KO + timedelta(minutes=30))]                          # in-game
    got = {(o.bookmaker, o.price_decimal) for o in last_capture(rows, KO)}
    assert got == {("a", 1.7), ("c", 1.9)}            # book b (absent from the last session) contributes nothing
    assert {o.price_decimal for o in last_capture(rows, None)} == {1.1}   # no cutoff: the in-game run is last
    assert last_capture([row("a", "HOME", 2.0, None)], KO) == []          # no timestamp: excluded (law 4)


def test_close_1x2_is_the_last_session_not_the_average():
    early, late = KO - timedelta(days=2), KO - timedelta(hours=1)
    rows = [row("a", "HOME", 1.5, early), row("a", "AWAY", 3.0, early),
            row("a", "HOME", 2.5, late), row("a", "AWAY", 1.6, late)]
    cl = close_1x2(rows, KO)
    assert cl["fair"]["HOME"] == pytest.approx((1 / 2.5) / (1 / 2.5 + 1 / 1.6))
    legacy = cr.legacy_fair(rows)
    assert abs(legacy["HOME"] - cl["fair"]["HOME"]) > 0.05      # the averaging bug, measured
    assert cl["best"]["HOME"] == ("a", 2.5) and cl["books"] == 1


def _world(code):
    init_db()
    with session_scope() as s:
        comp = Competition(sport=Sport.SOCCER, code=code, name=code, area="X", type="LEAGUE")
        h, a = Team(sport=Sport.SOCCER, name=f"{code} H"), Team(sport=Sport.SOCCER, name=f"{code} A")
        s.add_all([comp, h, a])
        s.flush()
        m = Match(sport=Sport.SOCCER, competition_id=comp.id, season="2038/39", utc_date=KO,
                  status=MatchStatus.SCHEDULED, home_team_id=h.id, away_team_id=a.id,
                  external_ids={"fakeodds": "g1"})
        s.add(m)
        s.flush()
        return m.id


class FakeOddsAdapter:
    source_name = "fakeodds"

    def __init__(self):
        self.batches = []

    def list_odds(self, source_id):
        return self.batches.pop(0)


def test_sync_odds_replaces_keeps_line_and_appends_history(monkeypatch):
    from src.ingestion import service as svc
    mid = _world("OCS1")
    monkeypatch.setattr(svc, "utc_now_naive", lambda: KO - timedelta(days=3))
    ad = FakeOddsAdapter()
    t1, t2 = KO - timedelta(days=2), KO - timedelta(hours=2)
    no = lambda sel, px, at, market="1X2", line=None: NormalizedOdds(
        match_source_id="g1", source="fakeodds", bookmaker="bk", market=market, selection=sel,
        price_decimal=px, captured_at=at, line=line)
    ad.batches = [[no("HOME", 2.0, t1), no("DRAW", 3.4, t1), no("AWAY", 4.0, t1),
                   no("OVER", 1.9, t1, "TOTALS", 2.5)],
                  [no("HOME", 2.4, t2), no("DRAW", 3.3, t2), no("AWAY", 3.1, t2),
                   no("OVER", 2.0, t2, "TOTALS", 2.75)],
                  []]                                                  # an empty fetch: never wipes
    service = svc.IngestionService(ad)
    for _ in range(3):
        service.sync_odds("OCS1")
    with session_scope() as s:
        rows = list(s.execute(select(Odds).where(Odds.match_id == mid)).scalars())
        snaps = list(s.execute(select(OddsSnapshot).where(OddsSnapshot.match_id == mid)).scalars())
    assert {o.captured_at for o in rows} == {t2} and len(rows) == 4          # replaced, not appended
    assert next(o.line for o in rows if o.market == "TOTALS") == 2.75        # line kept
    assert sorted({x.captured_at for x in snaps}) == [t1, t2]                # history appended
    assert {x.source for x in snaps} == {"fakeodds"} and len(snaps) == 6


def test_restate_dry_run_then_apply_and_unpriceable_left_as_stored():
    mid = _world("OCS2")
    mid2 = _world("OCS3")
    early, late = KO - timedelta(days=2), KO - timedelta(hours=1)
    with session_scope() as s:
        m = s.get(Match, mid)
        m.status, m.home_score, m.away_score = MatchStatus.FINISHED, 2, 0
        for sel, e, l in (("HOME", 1.5, 2.5), ("DRAW", 4.0, 3.4), ("AWAY", 6.0, 2.9)):
            s.add(Odds(match_id=mid, bookmaker="bk", market="1X2", selection=sel, price_decimal=e,
                       captured_at=early, source="fakeodds"))
            s.add(Odds(match_id=mid, bookmaker="bk", market="1X2", selection=sel, price_decimal=l,
                       captured_at=late, source="fakeodds"))
        p = Prediction(match_id=mid, model_version="t", home_win_prob=0.55, draw_prob=0.25, away_win_prob=0.20)
        s.add(p)
        s.flush()
        legacy = cr.legacy_fair(list(s.execute(select(Odds).where(Odds.match_id == mid)).scalars()))
        s.add(PredictionOutcome(prediction_id=p.id, clv=0.55 - legacy["HOME"], closing_price=2.5,
                                closing_bookmaker="bk", top_pick_hit=True))
        # a second, unpriceable grade: only an in-game row exists for its match
        m2 = s.get(Match, mid2)
        m2.status, m2.home_score, m2.away_score = MatchStatus.FINISHED, 1, 1
        s.add(Odds(match_id=mid2, bookmaker="bk", market="1X2", selection="HOME", price_decimal=2.0,
                   captured_at=KO + timedelta(minutes=20), source="fakeodds"))
        p2 = Prediction(match_id=mid2, model_version="t", home_win_prob=0.5, draw_prob=0.3, away_win_prob=0.2)
        s.add(p2)
        s.flush()
        s.add(PredictionOutcome(prediction_id=p2.id, clv=0.04, top_pick_hit=False))
    dry = cr.restate()
    a = dry["by_scope"]["soccer/OCS2"]
    assert a["changed"] == 1 and a["mean_delta_pp"] > 0 and not dry["applied"]   # last session prices HOME longer than the average
    assert dry["by_scope"]["soccer/OCS3"]["became_null"] == 1
    with session_scope() as s:                                   # dry-run wrote nothing
        assert s.execute(select(PredictionOutcome.clv).join(Prediction).where(
            Prediction.match_id == mid)).scalar_one() == pytest.approx(0.55 - legacy["HOME"])
    cr.restate(apply=True)
    with session_scope() as s:
        fair = (1 / 2.5) / (1 / 2.5 + 1 / 3.4 + 1 / 2.9)
        assert s.execute(select(PredictionOutcome.clv).join(Prediction).where(
            Prediction.match_id == mid)).scalar_one() == pytest.approx(0.55 - fair)
        assert s.execute(select(PredictionOutcome.clv).join(Prediction).where(
            Prediction.match_id == mid2)).scalar_one() == pytest.approx(0.04)   # left as stored


def test_cli_audit_and_restate_backup_gate(tmp_path):
    import cli
    _world("OCS4")
    out = CliRunner().invoke(cli.cli, ["odds-audit"]).output
    assert "ODDS-AUDIT VERDICT:" in out
    assert "--backup" in CliRunner().invoke(cli.cli, ["clv-restate", "--apply"]).output
    live = Path(os.environ["DATABASE_URL"][len("sqlite:///"):])
    bk = tmp_path / "sports_test.db"
    src, dst = sqlite3.connect(live), sqlite3.connect(bk)
    src.backup(dst)
    src.close()
    dst.close()
    ok = CliRunner().invoke(cli.cli, ["clv-restate", "--apply", "--backup", str(bk)])
    assert "backup verified" in ok.output and "APPLIED" in ok.output, ok.output
    stale = tmp_path / "stale.db"
    live_n = sqlite3.connect(live).execute("SELECT COUNT(*) FROM prediction_outcomes").fetchone()[0]
    con = sqlite3.connect(stale)
    con.execute("CREATE TABLE prediction_outcomes(id INTEGER)")
    con.executemany("INSERT INTO prediction_outcomes VALUES (?)", [(i,) for i in range(live_n + 1)])
    con.commit()
    con.close()
    assert "REFUSED" in CliRunner().invoke(cli.cli, ["clv-restate", "--apply", "--backup", str(stale)]).output
