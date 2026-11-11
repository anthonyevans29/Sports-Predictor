"""NOTHING-TO-COMPARE (ARCHITECT 2026-11-11, addendum 334 item 3(a), verbatim): "a red status that means "nothing to
compare" is a false alarm — the verdict for zero compared files becomes NOTHING-TO-COMPARE (neutral, not failure),
DIVERGENT reserved for files that were compared and differ". Completed by THE PAIRED KINDS (ARCHITECT 2026-11-11 08:45
ET, addendum 335 item 4(c), verbatim): "CLEAN = at least one paired file compared with rows in the window, every
compared file identical, no paired kind missing on a side. DIVERGENT = a compared file differs, OR a paired kind is
present on one side and missing on the other for a date both machines pushed (a missing file is a finding), OR a pair
does not parse. NOTHING-TO-COMPARE = everything else, including a pair whose in-window rows are empty on both sides".
And 335 item 2, verbatim: "(1) a one-sided file beside a clean pair reading DIVERGENT — NOT the final rule, and not
fixed in #922: it is ruled in item 4(c) below and built with #924's PR; #922 merges with its test pinning today's
behavior, and that PR changes the test." This is that PR (#924's build). Corrected and completed by addendum 336 item 4
(ARCHITECT 2026-11-11 09:35 ET), verbatim: "(2) THE PUSH TIMING: a paired kind present on one side only reads DIVERGENT
only for a COMPLETE day. For the comparator's own UTC date (the run's "today") the file's absence on the other side is
"awaiting <role>" — NOTHING-TO-COMPARE, posted pending — because the other machine's export time may not have come; for
any earlier date it is DIVERGENT ("paired kind missing on <role>"), which is what a tag's hand run on D-1 reads (335
item 4(f))." And "(3) AN UNPAIRED KIND ON BOTH SIDES THAT DIFFERS: "never a cause of DIVERGENT" governs." The Action
side is pinned in test_exports_mirror.py; the window and the host-only columns in
test_compare_exports_paired_kinds.py. Every run here pins the comparator's clock (--today)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))
import compare_exports as ce  # noqa: E402

DAY = "2026-11-11"
GAME = {"utc_date": "2026-11-11T00:00:00Z", "home_team": "Akron", "away_team": "Western Michigan", "p": 0.17}
NHL = f"fixtures_NHL_{DAY}.json"
NHL_ROW = {"utc_date": "2026-11-11T00:00:00", "home_team": "Boston Bruins", "away_team": "Ottawa Senators",
           "status": "scheduled", "home_score": None, "away_score": None, "competition": "NHL"}
COV = {"now": "2026-11-11T12:20:00Z", "due": [], "ahead": []}


def nhl(rows):
    return {"competition_code": "NHL", "count": len(rows), "fixtures": rows}


NEXT_DAY = "2026-11-12"


def run(tmp_path, capsys, laptop: dict, host: dict, *extra, today: str = DAY):
    la, ho = tmp_path / "laptop", tmp_path / "host"
    for d, files in ((la, laptop), (ho, host)):
        d.mkdir(parents=True)
        for name, body in files.items():
            (d / name).write_text(body if isinstance(body, str) else json.dumps(body))
    rc = ce.main([str(la), str(ho), "--since", "0", "--today", today, *extra])
    return rc, capsys.readouterr().out


def test_the_11_11_shape_is_nothing_to_compare_never_divergent(tmp_path, capsys):
    rc, out = run(tmp_path, capsys,
                  {f"coverage_{DAY}.json": COV, "mlb_MLB_results_2026-11-10.json": {"results": []}},
                  {f"coverage_{DAY}.json": COV, f"unl_shadow_{DAY}_0720.json": {"rows": []},
                   "window_24h.json": {"entries": []}})
    assert rc == ce.EXIT_NOTHING_TO_COMPARE == 3, out
    for name, side, kind in (("mlb_MLB_results_2026-11-10.json", "laptop", "mlb_MLB_results"),
                             (f"unl_shadow_{DAY}_0720.json", "host", "unl_shadow"),
                             ("window_24h.json", "host", "window_24h")):
        assert f"· {name}: only on {side} (expected one-sided: {kind} is not a paired kind)" in out
    assert "coverage: 0 JSON file(s) compared (*.json) · 3 on one side only" in out
    assert "VERDICT: DIVERGENT" not in out and "DIVERGENT (" not in out and "VERDICT: CLEAN" not in out
    assert out.strip().splitlines()[-1] == (
        "VERDICT: NOTHING-TO-COMPARE (0 compared; 0 paired with rows in the window; 3 expected one-sided: "
        f"mlb_MLB_results_2026-11-10.json, unl_shadow_{DAY}_0720.json, window_24h.json) — not a data verdict")


def test_one_file_on_one_side_alone_is_nothing_to_compare(tmp_path, capsys):
    rc, out = run(tmp_path, capsys, {}, {"window_24h.json": {"entries": []}})
    assert rc == ce.EXIT_NOTHING_TO_COMPARE
    assert out.strip().splitlines()[-1].startswith("VERDICT: NOTHING-TO-COMPARE (0 compared; 0 paired with rows in "
                                                   "the window; 1 expected one-sided: window_24h.json)")


def test_a_file_on_both_sides_that_does_not_parse_stays_divergent(tmp_path, capsys):
    """335 item 2: "(2) an unparseable pair stays DIVERGENT with 0 compared — CONFIRMED (law 4)"."""
    rc, out = run(tmp_path, capsys, {f"bad_{DAY}.json": "{"}, {f"bad_{DAY}.json": "{"})   # an unpaired kind too
    assert rc == ce.EXIT_DIVERGENT
    assert f"✗ bad_{DAY}.json: unparseable" in out
    assert out.strip().splitlines()[-1] == "VERDICT: DIVERGENT"


def test_a_one_sided_file_beside_a_clean_paired_pair_is_clean(tmp_path, capsys):
    """335 item 2 (1), ruled by 4(c): the one-sided file of a kind not on the list is EXPECTED ONE-SIDED, never a
    cause; #922's as-built DIVERGENT reading of this shape is replaced (that test changed here)."""
    rc, out = run(tmp_path, capsys, {NHL: nhl([NHL_ROW]), "mlb_MLB_results_2026-11-10.json": {"results": []}},
                  {NHL: nhl([NHL_ROW]), "window_24h.json": {"entries": []}})
    assert rc == ce.EXIT_CLEAN, out
    assert out.strip().splitlines()[-1] == "VERDICT: CLEAN"
    assert f"CLEAN (1 compared; 1 paired with rows in the window: {NHL})" in out


def test_an_identical_unpaired_pair_beside_one_sided_files_is_nothing_to_compare(tmp_path, capsys):
    """#922 pinned this shape as DIVERGENT (335 item 2: "NOT the final rule"). An identical pair of a kind not on the
    list is read and counted, but only a paired file with rows in the window makes CLEAN (336 item 4(3))."""
    lap = {"mlb_MLB_results_2026-11-10.json": {"results": []}, "window_24h.json": {"entries": []}}
    hos = {f"unl_shadow_{DAY}_0720.json": {"rows": []}, "window_24h.json": {"entries": []}}
    rc, out = run(tmp_path, capsys, lap, hos)
    assert rc == ce.EXIT_NOTHING_TO_COMPARE, out
    assert "✓ window_24h.json" in out and "· unpaired, on both sides: identical" in out
    assert "unpaired, on both sides: 1 identical, 0 differ (not a verdict)" in out
    assert out.strip().splitlines()[-1].startswith("VERDICT: NOTHING-TO-COMPARE (1 compared; 0 paired with rows in "
                                                   "the window; 2 expected one-sided: ")


def test_an_unpaired_pair_that_differs_is_seen_and_never_a_verdict(tmp_path, capsys):
    """336 item 4(3), verbatim: "An unpaired kind found on both sides is printed and counted as "unpaired, on both
    sides: identical" or "unpaired, on both sides: DIFFERS (not a verdict; pair it by ruling if both machines should
    make it)", so the difference is seen and certifies nothing." Alone it reads NOTHING-TO-COMPARE; beside a clean
    paired pair, CLEAN; the difference is printed either way."""
    name = f"fixtures_NCAA_{DAY}.json"
    rc, out = run(tmp_path, capsys, {name: [GAME]}, {name: [dict(GAME, p=0.2)]})
    assert rc == ce.EXIT_NOTHING_TO_COMPARE, out
    assert (f"≠ {name}: rows laptop=1 host=1 diffs=1 · git_sha missing on laptop + host — code-version skew NOT "
            "claimable · unpaired, on both sides: DIFFERS (not a verdict; pair it by ruling if both machines should "
            "make it)") in out
    assert "].p: '0.17' vs '0.2'" in out                                                # the difference is seen
    assert "unpaired, on both sides: 0 identical, 1 differ (not a verdict)" in out
    assert out.strip().splitlines()[-1] == (
        f"VERDICT: NOTHING-TO-COMPARE (1 compared; 0 paired with rows in the window; unpaired, on both sides, differ "
        f"(not a verdict): {name}) — not a data verdict")
    rc, out = run(tmp_path / "b", capsys, {name: [GAME], NHL: nhl([NHL_ROW])},
                  {name: [dict(GAME, p=0.2)], NHL: nhl([NHL_ROW])})
    assert rc == ce.EXIT_CLEAN and out.strip().splitlines()[-1] == "VERDICT: CLEAN", out
    assert "].p: '0.17' vs '0.2'" in out and "1 differ (not a verdict)" in out
    assert not [ln for ln in out.splitlines() if ln.startswith("· ")]                # the Action's one-sided count


def test_a_paired_kind_missing_on_a_complete_day_is_divergent(tmp_path, capsys):
    """336 item 4(2): "for any earlier date it is DIVERGENT ("paired kind missing on <role>"), which is what a tag's
    hand run on D-1 reads (335 item 4(f))." The file is dated DAY; the run's own UTC day is the day after."""
    for lap, hos, missing_on in (({NHL: nhl([NHL_ROW])}, {"window_24h.json": {}}, "host"),
                                 ({}, {NHL: nhl([NHL_ROW])}, "laptop")):
        rc, out = run(tmp_path / missing_on, capsys, lap, hos, today=NEXT_DAY)
        assert rc == ce.EXIT_DIVERGENT, out
        assert f"PAIRED KIND fixtures_NHL missing on {missing_on} (a complete day)" in out
        assert f"1 paired kind missing on a side: {NHL}" in out


def test_a_paired_kind_on_one_side_on_the_runs_own_day_is_awaiting_never_divergent(tmp_path, capsys):
    """336 item 4(2): "For the comparator's own UTC date (the run's "today") the file's absence on the other side is
    "awaiting <role>" — NOTHING-TO-COMPARE, posted pending — because the other machine's export time may not have
    come". Both orientations; a later date than the run's own is not a complete day either."""
    for lap, hos, awaited in (({NHL: nhl([NHL_ROW])}, {"window_24h.json": {}}, "host"),
                              ({}, {NHL: nhl([NHL_ROW])}, "laptop")):
        rc, out = run(tmp_path / awaited, capsys, lap, hos)
        assert rc == ce.EXIT_NOTHING_TO_COMPARE, out
        assert f"PAIRED KIND fixtures_NHL awaiting {awaited} (the run's own UTC day, {DAY}: not a complete day)" in out
        assert "1 awaiting the other side (the run's own UTC day)" in out and "VERDICT: DIVERGENT" not in out
        assert out.strip().splitlines()[-1] == (
            f"VERDICT: NOTHING-TO-COMPARE (0 compared; awaiting {awaited}: {NHL}) — not a data verdict")
    rc, out = run(tmp_path / "early", capsys, {NHL: nhl([NHL_ROW])}, {}, today="2026-11-10")
    assert rc == ce.EXIT_NOTHING_TO_COMPARE and "awaiting host" in out, out


def test_awaiting_outranks_clean_and_a_difference_outranks_awaiting(tmp_path, capsys):
    """"So the laptop's 12:2xZ commit reads pending": a run that also holds yesterday's clean pair still reads
    awaiting (NOTHING-TO-COMPARE), never CLEAN; a paired file that differs is DIVERGENT whatever is awaited."""
    yday = "fixtures_NHL_2026-11-10.json"
    y_row = dict(NHL_ROW, utc_date="2026-11-10T00:00:00")
    rc, out = run(tmp_path, capsys, {yday: nhl([y_row]), NHL: nhl([NHL_ROW])}, {yday: nhl([y_row])})
    assert rc == ce.EXIT_NOTHING_TO_COMPARE, out
    assert out.strip().splitlines()[-1] == (
        f"VERDICT: NOTHING-TO-COMPARE (1 compared; awaiting host: {NHL}) — not a data verdict")
    rc, out = run(tmp_path / "b", capsys, {yday: nhl([y_row]), NHL: nhl([NHL_ROW])},
                  {yday: nhl([dict(y_row, status="finished")])})
    assert rc == ce.EXIT_DIVERGENT and out.strip().splitlines()[-1] == "VERDICT: DIVERGENT", out


def test_a_paired_pair_empty_in_the_window_is_nothing_to_compare(tmp_path, capsys):
    """"a pair whose in-window rows are empty on both sides" (218 item 1: an empty window is reported, never a pass);
    the 12-24 gap reads neutral. And (d): a 0-row pair of any kind never counts toward CLEAN."""
    rc, out = run(tmp_path, capsys, {NHL: nhl([]), "mlb_MLB_results_2026-11-10.json": {"results": []}},
                  {NHL: nhl([]), "mlb_MLB_results_2026-11-10.json": {"results": []}})
    assert rc == ce.EXIT_NOTHING_TO_COMPARE, out
    assert out.strip().splitlines()[-1] == (
        f"VERDICT: NOTHING-TO-COMPARE (2 compared; 0 paired with rows in the window; 1 paired empty in the window: "
        f"{NHL}) — not a data verdict")


def test_the_pre_335_rule_stays_available_by_flag(tmp_path, capsys):
    """--paired-kinds '*': every kind paired, as before 335 (one-sided beside a compared file is DIVERGENT)."""
    name = f"fixtures_NCAA_{DAY}.json"
    rc, out = run(tmp_path, capsys, {name: [GAME]}, {name: [GAME], "window_24h.json": {}}, "--paired-kinds", "*")
    assert rc == ce.EXIT_DIVERGENT and "DIVERGENT (1 compared; 1 on one side only: window_24h.json)" in out
    rc, out = run(tmp_path / "b", capsys, {name: [GAME]}, {name: [GAME]}, "--paired-kinds", "*")
    assert rc == ce.EXIT_CLEAN and out.strip().splitlines()[-1] == "VERDICT: CLEAN"


def test_the_prediction_check_keeps_its_own_no_coverage_reading(tmp_path, capsys):
    """#422 item 4 (the cutover PL check, --require-predictions): a missing host file is NO-COVERAGE, as before."""
    la, ho = tmp_path / "laptop", tmp_path / "host"
    la.mkdir(), ho.mkdir()
    (la / "soccer_PL.json").write_text(json.dumps({"predictions": []}))
    rc = ce.main([str(la), str(ho), "--since", "0", "--today", DAY, "--require-predictions"])
    out = capsys.readouterr().out
    assert rc == ce.EXIT_NO_COVERAGE
    assert out.strip().splitlines()[-1] == "VERDICT: NO-COVERAGE (0 compared) — not a data verdict"
