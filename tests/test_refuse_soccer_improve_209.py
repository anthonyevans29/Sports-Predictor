"""P1-1 (#209, ARCHITECT 2026-10-01, external review): legacy
`improve --sport soccer` is refused BEFORE any write, with guidance to the
chronological harness and soccer-refresh."""
import pytest
from click.testing import CliRunner

from src.db.schema import Sport
from src.walters import training


def test_improve_soccer_refused_before_any_write(monkeypatch):
    calls = []
    for fn in ("evaluate_finished", "train_fresh"):
        monkeypatch.setattr(training, fn, lambda *a, _n=fn, **k: calls.append(_n))
    with pytest.raises(training.LegacySoccerImproveRefused) as ei:
        training.improve(sport=Sport.SOCCER)
    assert calls == []                                     # nothing evaluated, trained or promoted
    msg = str(ei.value)
    assert "soccer-backtest" in msg and "soccer-refresh" in msg and "Nothing was written" in msg


def test_cli_improve_soccer_exits_2_with_guidance(monkeypatch):
    import cli
    calls = []
    monkeypatch.setattr(training, "evaluate_finished", lambda *a, **k: calls.append("eval"))
    for args in (["improve", "--sport", "soccer"], ["improve"]):        # the default is soccer
        r = CliRunner().invoke(cli.cli, args)
        assert r.exit_code == 2 and "REFUSED" in r.output and "soccer-refresh" in r.output, r.output
    assert calls == []


def test_mlb_improve_is_not_refused(monkeypatch):
    monkeypatch.setattr(training, "evaluate_finished", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("reached")))
    with pytest.raises(RuntimeError, match="reached"):
        training.improve(sport=Sport.MLB)
