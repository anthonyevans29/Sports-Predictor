"""ARCHITECT 2026-11-01 15:45 ET, addendum 206 item 1: "#768 (#755, the results row names the export it graded) — RULED
option (a): a NAMED, COUNTED machine-local class in compare_exports, "graded-export keys (machine-local)": every key of
a results row's graded_export object and of the file-level graded_exports block, never compared, never printed as a
diff, counted once per file on its own line beside the unit-bearing (#735) and shadow-arm (#761) lines, so a real
grading divergence in the same file still prints inside the budget." #768 writes graded_export = {kind, file, run_id,
exported_at} on every results row and graded_exports = {closing, slate, none, closing_files, slate_files, unreadable}
on the file. #761's pattern on a synthetic results pair; synthetic figures only (FIXTURE_*)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))
import compare_exports as ce  # noqa: E402

DAY = "2026-11-01"
LINE = "graded-export keys (machine-local): "
SHADOW = "shadow-arm keys (host-only, pl-availability-v1): "
UNIT = "unit-bearing fields masked (policy v1.2): "
FIXTURE_SLATE = "FIXTURE-SLATE-mlb_MLB_2026-11-01.json"
FIXTURE_CLOSING = "FIXTURE-CLOSING-closing_MLB_2026-11-01.json"
FIXTURE_RUN = "FIXTURE-RUN-20261101T230000Z-close"
FIXTURE_UNREADABLE = "FIXTURE-UNREADABLE.json"
SECRETS = (FIXTURE_SLATE, FIXTURE_CLOSING, FIXTURE_RUN, FIXTURE_UNREADABLE)
# #768's receipt: the six keys that read DIVERGENT on a pair differing only in the new keys
RECEIPT_SIX = ("graded_exports.closing", "graded_exports.closing_files", "graded_exports.slate",
               ".graded_export.file", ".graded_export.kind", ".graded_export.run_id")


def res(i, kind, log_loss=1.01, hit=True):
    if kind == "closing":
        ge = {"kind": "closing", "file": FIXTURE_CLOSING, "run_id": FIXTURE_RUN, "exported_at": f"{DAY}T23:00:01Z"}
    elif kind == "slate":
        ge = {"kind": "slate", "file": FIXTURE_SLATE, "run_id": None, "exported_at": f"{DAY}T14:00:00Z"}
    else:
        ge = {"kind": None, "file": None, "run_id": None, "exported_at": None}
    return {"match_id": 500 + i, "date": f"{DAY}T19:05:00", "home_team": f"Home{i:02d}", "away_team": f"Away{i:02d}",
            "predicted": {"model_version": "v2", "home_win": 0.55},
            "graded": {"log_loss": log_loss, "hit": hit}, "graded_export": ge}


def block(kind, n, unreadable=()):
    """name_rows' counts: both machines read one slate file; only the host holds the closing file."""
    return {"closing": n if kind == "closing" else 0, "slate": n if kind == "slate" else 0,
            "none": n if kind == "none" else 0, "closing_files": 1 if kind == "closing" else 0, "slate_files": 1,
            "unreadable": list(unreadable)}


def results(kind, n, changed=None):
    rows = [res(i, kind, **((changed or {}) if i == n - 1 else {})) for i in range(n)]
    return {"sport": "baseball", "git_sha": "abc", "count": n, "results": rows, "graded_exports": block(kind, n)}


def pair(n=1, changed=None):
    """#768's receipt pair: the laptop graded from its slate file (no run_id), the host from its own closing file
    (+ run_id); the graded_exports counts differ (closing, closing_files, slate). `changed`: the host's last row in key
    order (Away<n-1>) carries a different graded figure."""
    return results("slate", n), results("closing", n, changed)


def nfl_results(kind):
    """export-nfl-results as #768 writes it: live rows under results, pre-live rows under pre_live.results (an object
    with its note, count and record), the file's graded_exports block: 4 + 4 + 6 = 14."""
    return {"sport": "nfl", "count": 1, "results": [res(0, kind)],
            "pre_live": {"note": "FIXTURE pre-live", "count": 1, "record": {}, "results": [res(1, kind)]},
            "graded_exports": block(kind, 2)}


def run(tmp_path, capsys, laptop, host, *extra, name=f"mlb_MLB_results_{DAY}.json"):
    la, ho = tmp_path / "laptop", tmp_path / "host"
    for d, body in ((la, laptop), (ho, host)):
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(json.dumps(body))
    rc = ce.main([str(la), str(ho), "--since", "0", *extra])
    return rc, capsys.readouterr().out


def test_the_receipt_pair_reads_clean_with_every_key_counted(tmp_path, capsys):
    """#768's receipt pair (one game): the six keys that read DIVERGENT there are masked, never printed; the count is
    every key of both objects, a key on either side once: the row's 4 + the block's 6 = 10."""
    rc, out = run(tmp_path, capsys, *pair())
    for s in SECRETS:
        assert s not in out, s
    for k in RECEIPT_SIX:
        assert k not in out, k
    assert "graded_export" not in out.replace(LINE, "")      # nothing of the class but its own line
    assert "diffs=0 " in out
    assert LINE + "10" in out.splitlines()
    assert out.rstrip().splitlines()[-1] == "VERDICT: CLEAN" and rc == ce.EXIT_CLEAN


def test_the_file_level_block_carries_its_six_keys():
    """The ruling's "the six keys counted": graded_exports carries six (closing, slate, none, closing_files,
    slate_files, unreadable), each counted once whatever its values; a results row's graded_export carries four."""
    lap, host = pair()
    assert ce.graded_count({"graded_exports": lap["graded_exports"]}, {"graded_exports": host["graded_exports"]}) == 6
    assert ce.graded_count({"graded_exports": lap["graded_exports"]}, {}) == 6           # one side only: still 6
    assert ce.graded_count({"r": res(0, "slate")}, {"r": res(0, "closing")}) == 4
    # the mirror: the class on the host side only counts the same
    assert ce.graded_count({}, {"graded_exports": host["graded_exports"]}) == 6
    assert ce.graded_count({"r": {}}, {"r": res(0, "closing")}) == 4
    # key sets that differ and overlap: the union, a key on either side once (not one side, not the larger side)
    assert ce.graded_count({"graded_export": {"kind": 1, "file": 2}}, {"graded_export": {"file": 2, "run_id": 3}}) == 3


def test_the_line_sums_across_the_files_of_one_folder(tmp_path, capsys):
    """The morning compare reads a whole dated folder: an MLB results pair (10) and an NFL results pair (14) in the
    same laptop/host dirs print one line, their sum."""
    run(tmp_path, capsys, *pair())
    rc, out = run(tmp_path, capsys, nfl_results("none"), nfl_results("closing"), name=f"nfl_NFL_results_{DAY}.json")
    assert "coverage: 2 JSON file(s) compared (*.json)" in out
    assert LINE + "24" in out.splitlines() and rc == ce.EXIT_CLEAN


def test_a_changed_graded_figure_in_the_same_pair_is_still_divergent(tmp_path, capsys):
    for changed, want in (({"log_loss": 1.37}, ".graded.log_loss: '1.01' vs '1.37'"),
                          ({"hit": False}, ".graded.hit: 'True' vs 'False'")):
        rc, out = run(tmp_path / str(len(want)), capsys, *pair(15, changed))
        for s in SECRETS:
            assert s not in out, s
        assert want in out and "diffs=1 " in out                   # the real divergence, inside the budget
        assert LINE + str(15 * 4 + 6) in out.splitlines()
        assert out.rstrip().splitlines()[-1] == "VERDICT: DIVERGENT" and rc == ce.EXIT_DIVERGENT


def test_mutation_without_the_mask_the_keys_diverge_and_bury_the_grade(tmp_path, capsys, monkeypatch):
    """The mutation check: with the class removed, #768's six keys read DIVERGENT on the receipt pair, and on fifteen
    rows (3 block lines + 3 per row) they fill the 40-line budget before the real grading divergence on the last row."""
    monkeypatch.setattr(ce, "graded_export_class", lambda key: False)
    rc, out = run(tmp_path / "one", capsys, *pair())
    for k in RECEIPT_SIX:
        assert k in out, k
    assert "diffs=6 " in out and LINE + "0" in out.splitlines() and rc == ce.EXIT_DIVERGENT
    rc, out = run(tmp_path / "fifteen", capsys, *pair(15, {"log_loss": 1.37}))
    assert ".graded.log_loss" not in out and "diffs=40 " in out


def test_the_ignore_keys_mode_leaves_them_out_too(tmp_path, capsys):
    rc, out = run(tmp_path, capsys, *pair(3), "--ignore-keys", "desk,desk_meta,line_move,late_news_flag")
    for s in SECRETS:
        assert s not in out, s
    assert "graded_export" not in out.replace(LINE, "") and LINE + str(3 * 4 + 6) in out.splitlines()
    assert out.rstrip().splitlines()[-1] == "VERDICT: CLEAN" and rc == ce.EXIT_CLEAN


def test_its_own_line_after_the_shadow_and_rehearsal_arm_lines_and_both_counts_unchanged(tmp_path, capsys):
    """Beside a results row carrying a desk order (unit-bearing) and the pl-availability-v1 arm (shadow-arm), the two
    earlier counts read exactly as on the same pair without the graded-export keys."""
    def extras(doc, unit):
        for r in doc["results"]:
            r["desk"] = {"order": {"unit": unit, "text": "FIXTURE-ORDER", "contracts": 3, "limit": 0.5}}
            r["candidate"] = {"version": "pl-availability-v1", "log_loss": 0.9}
        return doc
    lap, host = pair(2)
    lap, host = extras(lap, "U-A"), extras(host, "U-B")
    bare_l, bare_h = json.loads(json.dumps(lap)), json.loads(json.dumps(host))
    for d in (bare_l, bare_h):
        d.pop("graded_exports")
        for r in d["results"]:
            r.pop("graded_export")
    _, base = run(tmp_path / "base", capsys, bare_l, bare_h)
    rc, out = run(tmp_path / "graded", capsys, lap, host)
    for o in (base, out):
        assert UNIT + "6" in o.splitlines() and SHADOW + "2" in o.splitlines()
    assert LINE + "0" in base.splitlines()
    lines = out.splitlines()
    shadow_i = next(i for i, x in enumerate(lines) if x.startswith(SHADOW))
    # addendum 247 item 2(2): the rehearsal-arm line sits right after the shadow-arm line, beside it; then this one
    assert lines[shadow_i - 1].startswith(UNIT)
    assert lines[shadow_i + 1] == "rehearsal-arm keys (host-only, nfl-elo-v2): 0"
    assert lines[shadow_i + 2] == LINE + str(2 * 4 + 6)
    assert rc == ce.EXIT_CLEAN


def test_the_nfl_shape_rows_live_and_pre_live_are_masked_and_counted(tmp_path, capsys):
    """export-nfl-results: every row, live and pre-live, carries graded_export; the file carries graded_exports."""
    rc, out = run(tmp_path, capsys, nfl_results("none"), nfl_results("closing"), name=f"nfl_NFL_results_{DAY}.json")
    for s in SECRETS:
        assert s not in out, s
    assert LINE + "14" in out.splitlines() and rc == ce.EXIT_CLEAN


def test_a_structural_mismatch_printed_whole_carries_no_graded_export_value(tmp_path, capsys):
    a = {"res": {"graded_export": res(0, "closing")["graded_export"], "p": 1},
         "meta": {"graded_exports": block("closing", 1, (FIXTURE_UNREADABLE,))}}
    b = {"res": None, "meta": None}
    rc, out = run(tmp_path, capsys, a, b, name="window_24h.json")
    for s in SECRETS:
        assert s not in out, s
    assert "$.res: \"{'graded_export': '<masked>', 'p': 1}\" vs 'None'" in out
    assert "$.meta: \"{'graded_exports': '<masked>'}\" vs 'None'" in out
    assert LINE + "10" in out.splitlines() and rc == ce.EXIT_DIVERGENT


def test_only_the_two_parent_names_are_masked():
    """A key that only starts with either name, the results row's `graded` block, and a `kind` / `file` / `run_id`
    outside the two objects are compared and printed as before."""
    assert ce.diff({"r": {"graded_export_x": 1}}, {"r": {"graded_export_x": 2}}) == ["$.r.graded_export_x: '1' vs '2'"]
    assert ce.diff({"r": {"graded_exportsv2": 1}}, {"r": {}}) == ["$.r.graded_exportsv2: only in laptop"]
    assert ce.diff({"r": {"graded": {"hit": True}}}, {"r": {"graded": {"hit": False}}}) == [
        "$.r.graded.hit: 'True' vs 'False'"]
    assert ce.diff({"r": {"run_id": "a", "file": "x"}}, {"r": {"run_id": "b", "file": "x"}}) == ["$.r.run_id: 'a' vs 'b'"]
    assert ce.graded_count({"r": {"graded_export_x": 1, "graded": {"hit": 1}}}, {"r": {}}) == 0
    assert not ce.graded_export_class("graded_export_x") and not ce.graded_export_class("graded")
    assert ce.graded_export_class("graded_export") and ce.graded_export_class("graded_exports")


def test_a_parent_that_is_not_an_object_counts_one():
    assert ce.diff({"r": {"graded_export": None}}, {"r": {}}) == []
    assert ce.graded_count({"r": {"graded_export": None}}, {"r": {}}) == 1


def test_the_help_names_the_class(capsys):
    try:
        ce.main(["--help"])
    except SystemExit as e:
        assert e.code == 0
    out = capsys.readouterr().out
    assert "graded-export keys (machine-local)" in out and "addendum 206 item 1" in out
