"""sync-odds-nfl -> sync-odds-football rename (2026-09-26): old name is an alias."""
from click.testing import CliRunner

import cli


def test_both_names_resolve_to_the_same_command(monkeypatch):
    calls = []
    import src.ingestion.service as svc
    monkeypatch.setattr(svc, "sync_odds_nfl",
                        lambda progress=None: calls.append(1) or {"created": 3, "games": 2})
    runner = CliRunner()
    for name in ("sync-odds-football", "sync-odds-nfl"):
        res = runner.invoke(cli.cli, [name])
        assert res.exit_code == 0, res.output
        assert "Football odds (NFL+NCAA): created=3 across 2 games" in res.output
    assert len(calls) == 2
    assert cli.cli.commands["sync-odds-nfl"] is cli.cli.commands["sync-odds-football"]
