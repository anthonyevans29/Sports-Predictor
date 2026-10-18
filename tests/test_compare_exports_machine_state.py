"""THE MACHINE-STATE KIND RULE (#592 RULED, ARCHITECT 2026-10-18 10:00 ET, addendum 128 item 3, verbatim): "a coverage
file is MACHINE STATE by nature — each machine's own view of the day, with `now`, `due` vs `ahead`, `started` — and can
never be a divergence. Option 1, as a KIND rule: the compare treats kind `coverage` as "machine state": listed by presence
on each side (one side, both sides, neither), never compared for content, never DIVERGENT, never counted toward or against
criterion (a). Printed as its own line ("machine-state files: coverage laptop yes / host no"). [...] the compare's test
adds the one-side and both-sides cases. Dated and latest copies both travel (option 3 declined: the dated file is the
day's record)."

compare_exports.py: kind `coverage` (the dated coverage_<date>.json and the latest copy coverage.json) is listed by
presence on its own line, never read, never a `·` or `✗` line, and out of the compared and one-side tallies.
Criterion (a)'s side (cutover_readiness.compare_day) is in tests/test_cutover_readiness.py; the mirror carrying both
copies and the shipped Action in tests/test_exports_mirror.py."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))
import compare_exports as ce  # noqa: E402

DAY = "2026-10-19"
COV = f"coverage_{DAY}.json"
FIX = f"fixtures_PL_{DAY}.json"
GAME = {"utc_date": "2026-10-19T19:00:00Z", "home_team": "Arsenal", "away_team": "Leeds", "p": 0.55}


def coverage_doc(now, state, started):
    """A coverage_v1 file as two machines write it on one DB at different times (the #592 receipt's differences:
    now, now_et, a group due vs ahead, the games started)."""
    return {"kind": "coverage_v1", "date": DAY, "now": now, "now_et": now.replace("Z", "-04:00"),
            "competitions": [{"code": "PL", "games": 2, "status": "LIVE", "started": started,
                              "groups": [{"start": "2026-10-19T19:00:00Z", "run_at": "2026-10-19T18:25:00Z",
                                          "state": state, "text": f"T-35 14:25 ET [50546] {state}"}]}],
            "gaps": [], "roadmap": None, "roadmap_unread": "test"}


LAPTOP_COV = coverage_doc("2026-10-19T12:00:00Z", "ahead", [])
HOST_COV = coverage_doc("2026-10-19T18:40:00Z", "due", [50546, 50547])


def sides(tmp_path, laptop: dict, host: dict):
    """Two side folders: {name: doc or raw text} each."""
    la, ho = tmp_path / "laptop", tmp_path / "host"
    for d, files in ((la, laptop), (ho, host)):
        d.mkdir(parents=True)
        for name, body in files.items():
            (d / name).write_text(body if isinstance(body, str) else json.dumps(body))
    return la, ho


def run(tmp_path, capsys, laptop, host, *extra):
    la, ho = sides(tmp_path, laptop, host)
    rc = ce.main([str(la), str(ho), "--since", "0", *extra])
    return rc, capsys.readouterr().out


def ms_lines(out):
    return [ln for ln in out.splitlines() if ln.startswith("machine-state files:")]


def test_one_side_is_listed_by_presence_never_divergent(tmp_path, capsys):
    """The #592 receipt's first case: the coverage file on the laptop only read `· …: only on laptop` and DIVERGENT."""
    rc, out = run(tmp_path, capsys, {FIX: [GAME], COV: LAPTOP_COV}, {FIX: [GAME]})
    assert rc == ce.EXIT_CLEAN, out
    assert ms_lines(out) == ["machine-state files: coverage laptop yes / host no"]
    assert f"{COV}: only on" not in out and "✗" not in out
    assert "coverage: 1 JSON file(s) compared (*.json) · 0 on one side only" in out
    assert out.strip().endswith("VERDICT: CLEAN")
    rc, out = run(tmp_path / "h", capsys, {FIX: [GAME]}, {FIX: [GAME], COV: HOST_COV})
    assert rc == ce.EXIT_CLEAN and ms_lines(out) == ["machine-state files: coverage laptop no / host yes"]
    assert "0 on one side only" in out


def test_both_sides_with_different_content_is_never_compared_never_divergent(tmp_path, capsys):
    """The #592 receipt's second case: both sides carry it, written at different times on the same DB (`$.now`,
    `$.now_et`, a group `ahead vs due`, `started: length 0 vs 2`): `✗ … diffs=7`, DIVERGENT. Now: never read."""
    assert ce.diff(LAPTOP_COV, HOST_COV)                       # the content does differ, past the timestamp mask
    rc, out = run(tmp_path, capsys, {FIX: [GAME], COV: LAPTOP_COV}, {FIX: [GAME], COV: HOST_COV})
    assert rc == ce.EXIT_CLEAN, out
    assert ms_lines(out) == ["machine-state files: coverage laptop yes / host yes"]
    assert COV not in out and "$.now" not in out and "ahead" not in out and "diffs=" in out
    assert "coverage: 1 JSON file(s) compared (*.json) · 0 on one side only" in out
    assert out.strip().endswith("VERDICT: CLEAN")


def test_neither_side_prints_the_line_and_changes_nothing(tmp_path, capsys):
    rc, out = run(tmp_path, capsys, {FIX: [GAME]}, {FIX: [GAME]})
    assert rc == ce.EXIT_CLEAN and ms_lines(out) == ["machine-state files: coverage laptop no / host no"]
    assert "coverage: 1 JSON file(s) compared (*.json) · 0 on one side only" in out


def test_a_real_divergence_beside_a_coverage_file_is_still_divergent(tmp_path, capsys):
    """The kind rule takes out kind coverage and nothing else: a data file's divergence and a data file on one side
    only still read DIVERGENT, counted as before."""
    other = dict(GAME, p=0.6)
    rc, out = run(tmp_path, capsys, {FIX: [GAME], COV: LAPTOP_COV, "window_24h.json": {}},
                  {FIX: [other], COV: HOST_COV})
    assert rc == ce.EXIT_DIVERGENT
    assert f"✗ {FIX}" in out and "· window_24h.json: only on laptop" in out
    assert ms_lines(out) == ["machine-state files: coverage laptop yes / host yes"]
    assert "coverage: 1 JSON file(s) compared (*.json) · 1 on one side only" in out
    assert out.strip().endswith("VERDICT: DIVERGENT")


def test_coverage_files_alone_are_no_coverage_never_clean(tmp_path, capsys):
    """Never counted TOWARD (a) either: a day whose only JSON is the coverage file compared nothing."""
    rc, out = run(tmp_path, capsys, {COV: LAPTOP_COV}, {COV: HOST_COV})
    assert rc == ce.EXIT_NO_COVERAGE, out
    assert ms_lines(out) == ["machine-state files: coverage laptop yes / host yes"]
    assert "coverage: 0 JSON file(s) compared" in out
    assert out.strip().endswith("VERDICT: NO-COVERAGE (0 compared) — not a data verdict")


def test_the_latest_copy_is_kind_coverage_too_and_is_never_read(tmp_path, capsys):
    """laptop/latest vs host/latest: the latest copy (coverage.json) is the same kind; an unparseable one is
    presence only, never an `unparseable` line."""
    rc, out = run(tmp_path, capsys, {"fixtures_PL.json": [GAME], "coverage.json": "{not json"},
                  {"fixtures_PL.json": [GAME], "coverage.json": HOST_COV})
    assert rc == ce.EXIT_CLEAN, out
    assert ms_lines(out) == ["machine-state files: coverage laptop yes / host yes"]
    assert "unparseable" not in out


def test_the_line_comes_before_the_tally_and_the_window_still_applies(tmp_path, capsys):
    """Printed as its own line, after the file lines and before the coverage tally. Under --since a dated coverage
    file outside the window is settled like any dated file (counted on the header line, not listed)."""
    la, ho = sides(tmp_path, {FIX: [GAME], "coverage_2026-10-10.json": LAPTOP_COV}, {FIX: [GAME]})
    assert ce.main([str(la), str(ho), "--today", DAY]) == ce.EXIT_CLEAN
    out = capsys.readouterr().out.splitlines()
    i = out.index("machine-state files: coverage laptop no / host no")
    assert out[i - 1].startswith(f"✓ {FIX}") and out[i + 2].startswith("coverage: 1 JSON file(s) compared")
    assert any("1 settled file(s) earlier not re-printed" in ln for ln in out)


def test_the_kind_is_the_mirrors_kind():
    """compare_exports ships alone (tools/compare_exports.py, no sp_common, no exports_mirror), so it carries its own
    copy of the mirror's kind rule; this pins the copy to exports_mirror.kind_of. The dated file and the latest copy
    are kind coverage; no other export is."""
    import coverage_map as cm
    import exports_mirror as em
    from datetime import date
    names = [COV, "coverage.json", Path(cm.default_out(date(2026, 10, 3))).name, "fixtures_NCAA_2026-10-03.json",
             "unl_shadow_2026-10-03_1200.json", "fixtures_EFL_2026-10-01_to_2026-10-07.json", "window_24h.json",
             "closing_SOCCER_2026-10-11T1700Z.json", "ncaa_cfbd_coverage_2026-10-03.json", "coverage_map.json",
             "morning_receipt_2026-10-03.md", "soccer_PL_2026-10-17_to_2026-10-20.json"]
    assert ce._STAMP.pattern == em.STAMP.pattern
    for n in names:
        assert ce.kind_of(n) == em.kind_of(n), n
    assert [n for n in names if ce.machine_state_kind(n)] == [COV, "coverage.json", "coverage_2026-10-03.json"]
    assert ce.MACHINE_STATE_KINDS == ("coverage",)


def test_the_docs_name_the_dated_copy_for_the_daily_compare():
    """#589 review: the mirror's Action compares the newest dated folder both writers hold (`laptop/$d` vs `host/$d`)
    and never latest/, so the daily compare lists the dated copy only; the latest copy is the same kind and is listed
    the same way when latest/ folders are compared by hand. The docs had said the daily compare lists both copies."""
    action = (ROOT / "deploy" / "exports-mirror" / "compare.yml").read_text()
    assert 'python tools/compare_exports.py "laptop/$d" "host/$d" --since 0' in action
    assert "grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'" in action and "/latest" not in action
    cli, spec = (" ".join((ROOT / "docs" / f).read_text().split()) for f in ("CLI.md", "specs/exports-mirror.md"))
    assert "the daily compare lists both copies" not in cli
    assert "each is listed on that one line" not in spec
    for doc in (cli, spec):
        assert "lists the dated copy" in doc
        assert "listed the same way when latest/ folders are compared by hand" in doc


def test_presence_is_read_among_the_files_the_glob_and_the_window_select(tmp_path, capsys):
    """Pins the line's scope AS BUILT (#589 review; open for the architect in the ledger entry: presence read from the
    whole side folder, or the line labelled with its scope). The line names presence among the files the compare
    selects: a coverage file the --glob or the --since window leaves out reads `no` there and is counted on the tally
    (not matched) or the header (settled) instead. The Action's flags (*.json, --since 0) select the whole folder."""
    lap = {FIX: [GAME], COV: LAPTOP_COV, "coverage_2026-10-12.json": LAPTOP_COV}
    rc, out = run(tmp_path, capsys, lap, {FIX: [GAME]}, "--glob", "fixtures*")
    assert rc == ce.EXIT_CLEAN and ms_lines(out) == ["machine-state files: coverage laptop no / host no"]
    assert "not matched by fixtures*: laptop 2, host 0 (e.g. coverage_2026-10-12.json, coverage_2026-10-19.json)" in out
    la, ho = sides(tmp_path / "w", lap, {FIX: [GAME]})
    assert ce.main([str(la), str(ho), "--today", "2026-10-25"]) == ce.EXIT_NO_COVERAGE
    out = capsys.readouterr().out
    assert ms_lines(out) == ["machine-state files: coverage laptop no / host no"] and "3 outside the window" in out
    rc, out = run(tmp_path / "a", capsys, lap, {FIX: [GAME]})
    assert rc == ce.EXIT_CLEAN and ms_lines(out) == ["machine-state files: coverage laptop yes / host no"]
