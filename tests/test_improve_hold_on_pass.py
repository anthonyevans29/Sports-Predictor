"""H0-5 guard (2026-09-27): unattended `improve` may propose and reject, but a
PASS never auto-promotes under hold_on_pass — it is HELD, pages via an SP-PAGE
line, and only `ratify-candidate` promotes it (and only against an unchanged
baseline). The gate itself is stubbed here; only the promotion branch is tested."""
import pytest
from click.testing import CliRunner
from sqlalchemy import select

import src.walters.training as tr
from src.db.database import init_db, session_scope
from src.db.schema import ModelVersion, Sport


class _TR:
    def __init__(self, v):
        self.version = v


@pytest.fixture
def ledger(monkeypatch):
    """Fresh MLB model ledger: PROD in production; train_fresh mints CAND."""
    init_db()
    fam = tr._family_for(Sport.MLB)
    with session_scope() as s:
        s.query(ModelVersion).filter(ModelVersion.sport == Sport.MLB).delete()
        s.add(ModelVersion(sport=Sport.MLB, model_family=fam, version="hold-prod",
                           status="production", parameters={}))

    def fake_train(sport, notes=""):
        with session_scope() as s:
            s.add(ModelVersion(sport=sport, model_family=fam, version="hold-cand",
                               parent_version=tr._current_production_version(s, sport),
                               status="candidate", parameters={}))
        return _TR("hold-cand")

    monkeypatch.setattr(tr, "evaluate_finished", lambda sport: 0)
    monkeypatch.setattr(tr, "train_fresh", fake_train)
    monkeypatch.setattr(tr, "_load_holdout_matches", lambda s, sport, cutoff: [object()] * 40)
    monkeypatch.setattr(tr, "_update_candidate_holdout_stats", lambda *a, **k: None)
    return fam


def _status():
    with session_scope() as s:
        return {mv.version: mv.status for mv in s.execute(
            select(ModelVersion).where(ModelVersion.sport == Sport.MLB)).scalars()}


def _scores(monkeypatch, cand, prod):
    monkeypatch.setattr(tr, "_score_model_on_holdout",
                        lambda s, v, h, sport: cand if v == "hold-cand" else prod)


def test_pass_is_held_not_promoted(ledger, monkeypatch):
    _scores(monkeypatch, 0.680, 0.690)  # beats by 0.010 >= 0.005: a PASS
    r = tr.improve(sport=Sport.MLB, hold_on_pass=True)
    assert r.held and not r.promoted and "HELD" in r.reasoning
    assert _status() == {"hold-prod": "production", "hold-cand": "held"}


def test_default_behaviour_unchanged(ledger, monkeypatch):
    _scores(monkeypatch, 0.680, 0.690)
    r = tr.improve(sport=Sport.MLB)
    assert r.promoted and not r.held
    assert _status() == {"hold-prod": "shelved", "hold-cand": "production"}


def test_reject_is_unaffected_by_hold(ledger, monkeypatch):
    _scores(monkeypatch, 0.689, 0.690)  # 0.001 < 0.005
    r = tr.improve(sport=Sport.MLB, hold_on_pass=True)
    assert not r.held and not r.promoted
    assert _status()["hold-cand"] == "rejected"


def test_cli_pages_and_ratify_promotes(ledger, monkeypatch):
    import cli
    _scores(monkeypatch, 0.680, 0.690)
    runner = CliRunner()
    out = runner.invoke(cli.cli, ["improve", "--sport", "mlb"],
                        env={"SP_IMPROVE_HOLD_ON_PASS": "1"})
    assert out.exit_code == 0, out.output
    assert "SP-PAGE: improve --sport mlb PASS HELD" in out.output
    assert _status()["hold-cand"] == "held"
    # ratification must be explicit
    assert runner.invoke(cli.cli, ["ratify-candidate", "--sport", "mlb",
                                   "--version", "hold-cand"]).exit_code == 2
    ok = runner.invoke(cli.cli, ["ratify-candidate", "--sport", "mlb",
                                 "--version", "hold-cand", "--yes"])
    assert ok.exit_code == 0 and "RATIFIED" in ok.output
    assert _status() == {"hold-prod": "shelved", "hold-cand": "production"}


def test_ratify_refuses_stale_baseline_and_non_held(ledger, monkeypatch):
    _scores(monkeypatch, 0.680, 0.690)
    tr.improve(sport=Sport.MLB, hold_on_pass=True)
    with session_scope() as s:  # production moved after the hold
        s.execute(select(ModelVersion).where(ModelVersion.version == "hold-prod")
                  ).scalar_one().status = "shelved"
        s.add(ModelVersion(sport=Sport.MLB, model_family=ledger, version="hold-other",
                           status="production", parameters={}))
    with pytest.raises(ValueError, match="stale verdict"):
        tr.ratify_candidate(Sport.MLB, "hold-cand")
    with pytest.raises(ValueError, match="not 'held'"):
        tr.ratify_candidate(Sport.MLB, "hold-other")
    assert _status()["hold-cand"] == "held"
