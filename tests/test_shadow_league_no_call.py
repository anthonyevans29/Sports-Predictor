"""S1 (ARCHITECT 2026-10-08, addendum 9 item 1, RULED): "Fix today in its own small PR, both halves, keyed on the one
set desk_policy.SHADOW_VENUE_COMPS. (a) predict and export-predictions refuse a competition in the set, exit 2, naming
export-soccer-expansion-shadow. (b) desk_call returns PASS for a model row whose competition is in the set: reason
'shadow league: never a call until CONFIRMED', no order, no value shadow." The Cockpit repo copy mirrors (b)."""
import os
import re
from datetime import datetime, timezone

import pytest
from click.testing import CliRunner

from src.walters import desk_policy as dp

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------- (a) the CLI refuses --

@pytest.mark.parametrize("code", sorted(dp.SHADOW_VENUE_COMPS) + ["pd"])
@pytest.mark.parametrize("cmd", [["predict", "--sport", "soccer", "--season", "2026/27", "--competition"],
                                 ["export-predictions", "--sport", "soccer", "--competition"]])
def test_predict_and_export_predictions_refuse_a_shadow_league(cmd, code):
    import cli
    r = CliRunner().invoke(cli.cli, cmd + [code])
    assert r.exit_code == 2, r.output
    out = " ".join(r.output.split())
    assert "REFUSED" in out and "export-soccer-expansion-shadow" in out and code.upper() in out
    assert "never a call until CONFIRMED" in out


def test_a_live_league_is_not_refused():
    import cli
    r = CliRunner().invoke(cli.cli, ["predict", "--sport", "soccer", "--competition", "PL", "--season", "1900/01"])
    assert r.exit_code != 2 and "export-soccer-expansion-shadow" not in r.output


# ---------------------------------------------------------------- (b) the Desk never calls --

def row(comp):
    """A soccer model row that, in a live league, is a PLAY (+10pp on HOME) with a DRAW value shadow (+10pp)."""
    return {"home_team": f"{comp} H", "away_team": f"{comp} A", "utc_date": "2026-10-10T17:00:00",
            "competition": comp,
            "prediction": {"probabilities": {"home_win": 0.55, "draw": 0.30, "away_win": 0.15}, "tier": "lean"},
            "market": {"bookmaker_count": 8, "fair_prob": {"HOME": 0.45, "DRAW": 0.20, "AWAY": 0.35}},
            "kalshi_legs": {"HOME": {"ticker": f"KXEPLGAME-26OCT10-{comp}H", "bid": 0.44, "ask": 0.45}}}


def desk(*comps):
    doc = {"sport": "soccer", "predictions": [row(c) for c in comps]}
    dp.annotate(doc, now=NOW)
    return {r["competition"]: r["desk"] for r in doc["predictions"]}


def test_desk_call_passes_a_shadow_league_model_row():
    d = desk("PL", *sorted(dp.SHADOW_VENUE_COMPS))
    assert d["PL"]["call"] == "PLAY" and d["PL"]["order"] is not None and d["PL"]["value_shadow"] is not None
    for c in dp.SHADOW_VENUE_COMPS:
        x = d[c]
        assert (x["call"], x["units"], x["pass_kind"], x["shadow_units"]) == ("PASS", 0, "shadow_league", 0), c
        assert x["reason"] == "shadow league: never a call until CONFIRMED"
        assert x["reasons"] == ["shadow league: never a call until CONFIRMED"] and x["tags"] == ["shadow league"]
        assert x["order"] is None and x["value_shadow"] is None and x["exec"] is None


def test_shadow_league_rows_are_never_parlay_legs_and_the_rule_precedes_started():
    doc = dp.parlays_doc([("soccer.json", {"sport": "soccer", "predictions": [row("PD"), row("SA"), row("PL")]})],
                         now=NOW)
    assert doc["live_legs"] == 1
    started = row("BL1")
    started["utc_date"] = "2026-10-10T11:00:00"                 # kicked off: still the shadow-league reason
    sdoc = {"sport": "soccer", "predictions": [started]}
    dp.annotate(sdoc, now=NOW)
    assert sdoc["predictions"][0]["desk"]["pass_kind"] == "shadow_league"


# ---------------------------------------------------------------- the Cockpit repo copy mirrors (b) --

def test_cockpit_renders_the_shadow_league_pass_kind():
    html = open(os.path.join(ROOT, "tools", "cockpit.html"), encoding="utf-8").read()
    tag = re.search(r"function passKindTag\(k\)\{(.*?)\n\}", html, re.S).group(1)
    assert 'k==="shadow_league"' in tag and "shadow league" in tag
    pol = re.search(r"function policy\(\)\{(.*?)\n\}", html, re.S).group(1)
    assert 'passKind==="shadow_league"' in pol
