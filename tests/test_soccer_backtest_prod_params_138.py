"""#138 (ruled 2026-09-30): the PLAIN soccer-backtest report evaluates the
production model — BOTH its dixon_coles_rho and its elo_goal_coeff (0.0008),
not the dataclass default coefficient (0.0023)."""
from click.testing import CliRunner

import cli
from src.walters import soccer_backtest as sb


def _run(monkeypatch, prod, *args):
    seen = {}

    def fake(competition_code, season, min_prior, **kw):
        seen.update(kw)
        return []                                  # "No results" -> the command returns early

    monkeypatch.setattr(cli, "_soccer_prod_poisson", lambda: prod)
    monkeypatch.setattr(sb, "run_soccer_backtest", fake)
    out = CliRunner().invoke(cli.cli, ["soccer-backtest", *args]).output
    return seen, out


def test_plain_report_uses_production_rho_and_elo_goal_coeff(monkeypatch):
    seen, out = _run(monkeypatch, ("soccer_elo_poisson_v22", -0.10, 0.0008))
    assert seen == {"dixon_coles_rho": -0.10, "elo_goal_coeff": 0.0008}
    flat = " ".join(out.split())                   # the console wraps long lines
    assert "elo_goal_coeff = 0.0008 (production soccer_elo_poisson_v22)" in flat


def test_rho_override_keeps_the_production_coefficient(monkeypatch):
    seen, out = _run(monkeypatch, ("soccer_elo_poisson_v22", -0.10, 0.0008), "--rho", "0.0")
    assert seen == {"dixon_coles_rho": 0.0, "elo_goal_coeff": 0.0008}
    assert "dixon_coles_rho = 0.0 (override" in " ".join(out.split())


def test_no_production_model_falls_back_and_says_so(monkeypatch):
    seen, out = _run(monkeypatch, None)
    assert seen == {"dixon_coles_rho": 0.0, "elo_goal_coeff": None}
    assert "NO production model resolved" in " ".join(out.split())
