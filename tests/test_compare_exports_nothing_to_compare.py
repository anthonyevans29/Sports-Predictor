"""NOTHING-TO-COMPARE (ARCHITECT 2026-11-11, addendum 334 item 3(a), verbatim): "a red status that means "nothing to
compare" is a false alarm — the verdict for zero compared files becomes NOTHING-TO-COMPARE (neutral, not failure),
DIVERGENT reserved for files that were compared and differ". The 11-11 mirror shape: the laptop pushed coverage and
MLB results, the host coverage, the UNL shadow and the window card; 0 JSON compared, 3 on one side only, read
DIVERGENT until now. The Action side (state pending) is pinned in test_exports_mirror.py."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))
import compare_exports as ce  # noqa: E402

DAY = "2026-11-11"
GAME = {"utc_date": "2026-11-11T00:00:00Z", "home_team": "Akron", "away_team": "Western Michigan", "p": 0.17}
COV = {"now": "2026-11-11T12:20:00Z", "due": [], "ahead": []}


def run(tmp_path, capsys, laptop: dict, host: dict):
    la, ho = tmp_path / "laptop", tmp_path / "host"
    for d, files in ((la, laptop), (ho, host)):
        d.mkdir(parents=True)
        for name, body in files.items():
            (d / name).write_text(body if isinstance(body, str) else json.dumps(body))
    rc = ce.main([str(la), str(ho), "--since", "0"])
    return rc, capsys.readouterr().out


def test_the_11_11_shape_is_nothing_to_compare_never_divergent(tmp_path, capsys):
    rc, out = run(tmp_path, capsys,
                  {f"coverage_{DAY}.json": COV, "mlb_MLB_results_2026-11-10.json": {"results": []}},
                  {f"coverage_{DAY}.json": COV, f"unl_shadow_{DAY}_0720.json": {"rows": []},
                   "window_24h.json": {"entries": []}})
    assert rc == ce.EXIT_NOTHING_TO_COMPARE == 3, out
    for name, side in (("mlb_MLB_results_2026-11-10.json", "laptop"), (f"unl_shadow_{DAY}_0720.json", "host"),
                       ("window_24h.json", "host")):
        assert f"· {name}: only on {side}" in out                    # still printed, still counted
    assert "coverage: 0 JSON file(s) compared (*.json) · 3 on one side only" in out
    assert "VERDICT: DIVERGENT" not in out and "DIVERGENT (" not in out and "VERDICT: CLEAN" not in out
    assert out.strip().splitlines()[-1] == (
        "VERDICT: NOTHING-TO-COMPARE (0 compared; 3 on one side only: mlb_MLB_results_2026-11-10.json, "
        f"unl_shadow_{DAY}_0720.json, window_24h.json) — not a data verdict")


def test_one_file_on_one_side_alone_is_nothing_to_compare(tmp_path, capsys):
    rc, out = run(tmp_path, capsys, {}, {"window_24h.json": {"entries": []}})
    assert rc == ce.EXIT_NOTHING_TO_COMPARE
    assert out.strip().splitlines()[-1].startswith("VERDICT: NOTHING-TO-COMPARE (0 compared; 1 on one side only: ")


def test_a_file_on_both_sides_that_does_not_parse_stays_divergent(tmp_path, capsys):
    """Not "nothing to compare": a file was there on both sides and could not be read."""
    rc, out = run(tmp_path, capsys, {f"bad_{DAY}.json": "{"}, {f"bad_{DAY}.json": "{"})
    assert rc == ce.EXIT_DIVERGENT
    assert f"✗ bad_{DAY}.json: unparseable" in out
    assert out.strip().splitlines()[-1] == "VERDICT: DIVERGENT"


def test_files_compared_and_one_sided_beside_them_read_as_before(tmp_path, capsys):
    """DIVERGENT is reserved for runs that compared files: one compared (equal) plus one on one side only is
    DIVERGENT as before (#680's summary line names the cause); one compared and different is DIVERGENT."""
    name = f"fixtures_NCAA_{DAY}.json"
    rc, out = run(tmp_path, capsys, {name: [GAME]}, {name: [GAME], "window_24h.json": {}})
    assert rc == ce.EXIT_DIVERGENT and out.strip().splitlines()[-1] == "VERDICT: DIVERGENT"
    assert f"DIVERGENT (1 compared; 1 on one side only: window_24h.json)" in out
    rc, out = run(tmp_path / "b", capsys, {name: [GAME]}, {name: [dict(GAME, p=0.2)]})
    assert rc == ce.EXIT_DIVERGENT and out.strip().splitlines()[-1] == "VERDICT: DIVERGENT"
    rc, out = run(tmp_path / "c", capsys, {name: [GAME]}, {name: [GAME]})
    assert rc == ce.EXIT_CLEAN and out.strip().splitlines()[-1] == "VERDICT: CLEAN"


def test_the_prediction_check_keeps_its_own_no_coverage_reading(tmp_path, capsys):
    """#422 item 4 (the cutover PL check, --require-predictions): a missing host file is NO-COVERAGE, as before."""
    la, ho = tmp_path / "laptop", tmp_path / "host"
    la.mkdir(), ho.mkdir()
    (la / "soccer_PL.json").write_text(json.dumps({"predictions": []}))
    rc = ce.main([str(la), str(ho), "--since", "0", "--require-predictions"])
    out = capsys.readouterr().out
    assert rc == ce.EXIT_NO_COVERAGE
    assert out.strip().splitlines()[-1] == "VERDICT: NO-COVERAGE (0 compared) — not a data verdict"


def test_as_built_one_identical_shared_file_beside_one_sided_files_is_divergent(tmp_path, capsys):
    """Pinned AS BUILT, open for the architect (needs-ruling on the PR): the 11-11 shape plus one identical shared
    file reads DIVERGENT, so adding a clean comparison turns NOTHING-TO-COMPARE red. Whichever way the ruling goes,
    this test is the line that changes."""
    lap = {"mlb_MLB_results_2026-11-10.json": {"results": []}, "window_24h.json": {"entries": []}}
    hos = {f"unl_shadow_{DAY}_0720.json": {"rows": []}, "window_24h.json": {"entries": []}}
    rc, out = run(tmp_path, capsys, lap, hos)
    assert rc == ce.EXIT_DIVERGENT
    assert "✓ window_24h.json" in out
    assert "DIVERGENT (1 compared; 2 on one side only: " in out
    assert out.strip().splitlines()[-1] == "VERDICT: DIVERGENT"
