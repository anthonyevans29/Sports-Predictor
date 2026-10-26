"""#680 (ARCHITECT 2026-10-26, the cutover's section 2 compare, verbatim): "7 of 7 compared files diffs=0, same code on
each; three undated files only on the host; the tool's VERDICT read DIVERGENT with no divergent file — a verdict-line
nit (read-only), Code's Issue." A DIVERGENT run now names its cause on the summary line (files with diffs, unparseable,
on one side only); the VERDICT line and the exit code are unchanged."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))
import compare_exports as ce  # noqa: E402

DAY = "2026-10-26"
GAME = {"utc_date": "2026-10-26T19:00:00Z", "home_team": "Arsenal", "away_team": "Leeds", "p": 0.55}


def run(tmp_path, capsys, laptop: dict, host: dict):
    la, ho = tmp_path / "laptop", tmp_path / "host"
    for d, files in ((la, laptop), (ho, host)):
        d.mkdir(parents=True)
        for name, body in files.items():
            (d / name).write_text(body if isinstance(body, str) else json.dumps(body))
    rc = ce.main([str(la), str(ho), "--since", "0"])
    out = capsys.readouterr().out
    summary = [ln for ln in out.splitlines() if ln.startswith(("CLEAN (", "DIVERGENT ("))]
    assert len(summary) == 1, out
    return rc, out, summary[0]


def same(n):
    return {f"fixtures_C{i}_{DAY}.json": [GAME] for i in range(n)}


def test_one_sided_only_names_its_cause_and_keeps_the_verdict_and_exit(tmp_path, capsys):
    """The section 2 shape: 7 compared with diffs=0, three undated files on the host only."""
    extra = {"nfl_predictions.json": [GAME], "soccer_PL.json": [GAME], "unl_shadow.json": [GAME]}
    rc, out, line = run(tmp_path, capsys, same(7), {**same(7), **extra})
    assert line.startswith("DIVERGENT (7 compared; 3 on one side only: "
                           "nfl_predictions.json, soccer_PL.json, unl_shadow.json) — each divergence needs")
    assert out.rstrip().splitlines()[-1] == "VERDICT: DIVERGENT" and rc == ce.EXIT_DIVERGENT


def test_a_field_diff_names_its_file_and_no_other_cause(tmp_path, capsys):
    """Codex on #683: the files with field diffs are named, not only counted."""
    rc, out, line = run(tmp_path, capsys, same(2), {**same(2), f"fixtures_C1_{DAY}.json": [{**GAME, "p": 0.6}]})
    assert line.startswith(f"DIVERGENT (2 compared; 1 with field diffs: fixtures_C1_{DAY}.json) — ")
    assert "one side" not in line
    assert out.rstrip().splitlines()[-1] == "VERDICT: DIVERGENT" and rc == ce.EXIT_DIVERGENT


def test_rows_on_one_side_within_a_file_are_their_own_cause(tmp_path, capsys):
    """Codex on #683: a file whose shared rows agree but with a row on one side prints diffs=0 on its own line; the
    summary names it as rows on one side, never as field diffs."""
    other = {**GAME, "home_team": "Chelsea", "away_team": "Spurs"}
    name = f"fixtures_C0_{DAY}.json"
    rc, out, line = run(tmp_path, capsys, same(1), {name: [GAME, other]})
    assert f"✗ {name}: rows laptop=1 host=2 diffs=0" in out
    assert line.startswith(f"DIVERGENT (1 compared; 1 with rows on one side: {name}) — ")
    assert "field diffs" not in line and rc == ce.EXIT_DIVERGENT


def test_an_unparseable_file_is_named(tmp_path, capsys):
    rc, out, line = run(tmp_path, capsys, {**same(1), f"bad_{DAY}.json": "{"}, {**same(1), f"bad_{DAY}.json": "{"})
    assert line.startswith(f"DIVERGENT (1 compared; 1 unparseable: bad_{DAY}.json) — ") and rc == ce.EXIT_DIVERGENT


def test_a_clean_run_reads_as_before(tmp_path, capsys):
    rc, out, line = run(tmp_path, capsys, same(3), same(3))
    assert line.startswith("CLEAN (3 compared) — each divergence needs")
    assert out.rstrip().splitlines()[-1] == "VERDICT: CLEAN" and rc == ce.EXIT_CLEAN
