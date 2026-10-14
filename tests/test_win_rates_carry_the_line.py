"""ARCHITECT 2026-10-13 (addendum 64 items 2 and 3).

Item 2 (#510), verbatim: "A win rate of the model's own picks carries the line against the close. A hit rate of the
calls staked carries the calls' own record against the close, which is the ledger's mean CLV over the same calls, and
nothing more. A frequency per band is calibration, not a record, and carries nothing. A receipt with a frozen format is
not changed; a receipt written from now on carries the line where it prints a win rate." Here: calibration's overall
hit rate and the web dashboard's top_pick_accuracy (ncaa-shadow-grade's is in tests/test_ncaa_shadow.py).

Item 3 (#511), verbatim: "The RESULTS.md section headed Soccer (PL) reads PL rows and no other: its query filters by the
competition it names. export-results with a competition code it does not know refuses, exit 2, naming the code; it never
falls back to every row."

Each on its own throwaway SQLite file (tests/test_record_vs_close.py's iso_db and game helpers)."""
import json
from datetime import timedelta

import pytest

from src.db.schema import Sport
from src.walters import vs_close as vc
from tests.test_record_vs_close import FAIR_A, FAIR_H, _comp, _game, iso_db  # noqa: F401  (iso_db is a fixture)


def _mlb(now):
    from src.db.database import session_scope
    with session_scope() as s:
        c = _comp(s, Sport.MLB, "MLB")
        d = now - timedelta(days=1)
        _game(s, c, Sport.MLB, "c1", d, 5, 2, 0.62)                                 # home pick, home won
        _game(s, c, Sport.MLB, "c2", d + timedelta(hours=1), 1, 4, 0.55)            # home pick, away won
        _game(s, c, Sport.MLB, "c3", d + timedelta(hours=2), 3, 2, 0.58, priced=False)   # no close: not fed
    return vc.block([(0.62, FAIR_H), (0.45, FAIR_A)])


def test_calibration_hit_rate_carries_the_line_over_the_same_games(iso_db):
    from src.timeutil import utc_now_naive
    from src.walters.calibration import compute_calibration
    want = _mlb(utc_now_naive())
    r = compute_calibration(sport=Sport.MLB, with_vs_close=True)
    assert r.total == 3 and round(r.overall_hit_rate, 4) == round(2 / 3, 4)
    assert {k: v for k, v in r.vs_close.items() if k != "kalshi_only_closes"} == want
    assert compute_calibration(sport=Sport.MLB).vs_close is None          # only when asked (the CLI asks)
    for b in r.bins:                                                        # a frequency per band carries nothing
        assert not hasattr(b, "vs_close")


def test_the_calibration_command_prints_the_line_under_the_hit_rate(iso_db):
    from click.testing import CliRunner

    import cli
    from src.timeutil import utc_now_naive
    _mlb(utc_now_naive())
    res = CliRunner().invoke(cli.cli, ["calibration", "--sport", "mlb"])
    assert res.exit_code == 0, res.output
    out = res.output.splitlines()
    i = next(k for k, x in enumerate(out) if "Overall hit rate:" in x)
    assert out[i + 1].strip().startswith("vs close: 2 games · model ")


def test_the_web_dashboard_shows_the_line_beside_top_pick_accuracy(iso_db):
    from fastapi.testclient import TestClient

    from src.db.database import session_scope
    from src.db.schema import ModelVersion
    from src.timeutil import utc_now_naive
    from src.web.app import app
    want = _mlb(utc_now_naive())
    with session_scope() as s:
        s.add(ModelVersion(sport=Sport.MLB, model_family="vc", version="vc-probe", status="production"))
    client = TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
    r = client.get("/predictions?sport=baseball")
    assert r.status_code == 200, r.text[:500]
    assert "Against the close" in r.text
    assert vc.line(want) in r.text                                   # beside the top-pick accuracy, the same games


def test_the_pl_section_reads_pl_rows_and_no_other(iso_db, tmp_path):
    from src.db.database import session_scope
    from src.timeutil import utc_now_naive
    from src.walters.export import results_tally
    now = utc_now_naive()
    with session_scope() as s:
        pl, other = _comp(s, Sport.SOCCER, "PL"), _comp(s, Sport.SOCCER, "ELC")
        _game(s, pl, Sport.SOCCER, "pl", now - timedelta(days=1), 2, 0, None, three=(0.5, 0.3, 0.2), season="2026/27")
        _game(s, other, Sport.SOCCER, "elc", now - timedelta(days=1), 0, 3, None, three=(0.5, 0.3, 0.2),
              season="2026/27")                                             # a graded row of another competition
    out = tmp_path / "RESULTS.md"
    results_tally(days=30, out_path=str(out))
    txt = out.read_text()
    sec = txt.split("## Soccer (PL)\n\n", 1)[1].split("\n## ", 1)[0]
    assert sec.startswith("- Sides: **1/1** (100.0%)\n")                    # the ELC miss stays out
    assert "- vs close: 1 game · " in sec                                   # and out of its record against the close


def test_export_results_refuses_an_unknown_competition_code(iso_db, tmp_path):
    from click.testing import CliRunner

    import cli
    from src.timeutil import utc_now_naive
    from src.walters.export import UnknownCompetition, export_results
    _mlb(utc_now_naive())
    with pytest.raises(UnknownCompetition) as e:
        export_results(sport=Sport.MLB, start_date=utc_now_naive() - timedelta(days=3), end_date=utc_now_naive(),
                       competition_code="NOPE")
    assert e.value.code == "NOPE"
    res = CliRunner().invoke(cli.cli, ["export-results", "--sport", "mlb", "--competition", "NOPE",
                                       "--out", str(tmp_path / "x.json")])
    assert res.exit_code == 2, res.output
    assert "REFUSED: unknown competition code 'NOPE'" in res.output and "never falls back to every row" in res.output
    assert not (tmp_path / "x.json").exists()                              # nothing written
    # review of the PR: an empty code is a code it does not know, never "every row"
    blank = CliRunner().invoke(cli.cli, ["export-results", "--sport", "mlb", "--competition", "",
                                         "--out", str(tmp_path / "y.json")])
    assert blank.exit_code == 2 and "REFUSED: unknown competition code ''" in blank.output, blank.output
    assert not (tmp_path / "y.json").exists()
    doc = json.loads(export_results(sport=Sport.MLB, start_date=utc_now_naive() - timedelta(days=3),
                                    end_date=utc_now_naive(), competition_code="MLB"))
    assert doc["count"] == 3                                                # a known code reads as before
