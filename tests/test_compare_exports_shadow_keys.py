"""ARCHITECT 2026-11-01 12:05 ET, addendum 199 item 2: "THE COMPARE — option (b): a NAMED, COUNTED host-only class.
compare_exports treats every `candidate_*` key as "shadow-arm keys (host-only, pl-availability-v1)": never compared,
never printed, counted on its own line beside the unit-bearing count (#735's pattern), so a real v22 divergence in the
same file still prints inside the budget." #760 writes, on the host only, candidate_version, candidate_probabilities,
candidate_missing and candidate_reason on every PL slate and closing row, and the arm under `candidate` on a PL results
row. Synthetic figures only (FIXTURE_*)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))
import compare_exports as ce  # noqa: E402

DAY = "2026-11-08"
EID = "pl-availability-v1"
LINE = "shadow-arm keys (host-only, pl-availability-v1): "
FIXTURE_REASON = "FIXTURE-REASON-SHADOW"
FIXTURE_P = 0.123456                       # a candidate probability that must never print
FIXTURE_LL = 0.987654                      # a candidate log-loss that must never print
SECRETS = (FIXTURE_REASON, str(FIXTURE_P), str(FIXTURE_LL), EID + "'")


def pl_row(i, home_win=0.45):
    return {"match_id": 100 + i, "utc_date": f"{DAY}T15:00:00Z", "home_team": f"Home{i:02d}",
            "away_team": f"Away{i:02d}", "competition": "PL",
            "prediction": {"model_version": "v22",
                           "probabilities": {"home_win": home_win, "draw": 0.27, "away_win": round(0.73 - home_win, 4)}}}


def host_row(i, home_win=0.45):
    r = pl_row(i, home_win)
    r.update({"candidate_version": EID,
              "candidate_probabilities": {"home_win": FIXTURE_P, "draw": 0.3, "away_win": 0.5},
              "candidate_missing": {"home": {"model": 3, "candidate": 1}, "away": {"model": 2, "candidate": 2}},
              "candidate_reason": FIXTURE_REASON})
    return r


def slate(rows):
    return {"sport": "soccer", "git_sha": "abc", "predictions": rows}


def run(tmp_path, capsys, laptop, host, *extra, name=f"closing_PL_{DAY}.json"):
    la, ho = tmp_path / "laptop", tmp_path / "host"
    for d, body in ((la, laptop), (ho, host)):
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(json.dumps(body))
    rc = ce.main([str(la), str(ho), "--since", "0", *extra])
    return rc, capsys.readouterr().out


def divergence_pair():
    """Ten PL rows; the host's carry the four candidate_* keys; the LAST row in key order (Away09) has a real v22
    divergence, so 36 shadow lines would fill the diff budget before it if the mask were off."""
    laptop = slate([pl_row(i) for i in range(10)])
    host = slate([host_row(i, 0.46 if i == 9 else 0.45) for i in range(10)])
    return laptop, host


def test_the_shadow_keys_are_masked_counted_and_a_real_v22_divergence_still_prints(tmp_path, capsys):
    laptop, host = divergence_pair()
    rc, out = run(tmp_path, capsys, laptop, host)
    for s in SECRETS:
        assert s not in out, s
    assert "candidate_" not in out
    assert ".prediction.probabilities.home_win: '0.45' vs '0.46'" in out   # the real divergence, inside the budget
    assert "diffs=2 " in out              # home_win and away_win (0.73 - home_win) alone: no shadow key is a diff
    assert LINE + "40" in out                                              # 4 keys x 10 rows
    lines = out.splitlines()
    unit_i = next(i for i, x in enumerate(lines) if x.startswith("unit-bearing fields masked (policy v1.2): "))
    assert lines[unit_i + 1] == LINE + "40"                                # its own line, beside the unit-bearing one
    assert lines[unit_i] == "unit-bearing fields masked (policy v1.2): 0"
    assert lines[-1] == "VERDICT: DIVERGENT" and rc == ce.EXIT_DIVERGENT


def test_mutation_without_the_mask_the_divergence_is_lost_past_the_budget(tmp_path, capsys, monkeypatch):
    """The mutation check: with the shadow mask removed, the 40 host-only candidate_* lines fill the diff budget and
    the real v22 divergence never prints; the test above is what the mask buys."""
    monkeypatch.setattr(ce, "shadow_arm", lambda key, *values: False)
    laptop, host = divergence_pair()
    rc, out = run(tmp_path, capsys, laptop, host)
    assert ".prediction.probabilities.home_win" not in out
    assert "candidate_probabilities: only in host" in out
    assert LINE + "0" in out


def test_only_the_shadow_keys_differ_reads_clean_with_the_count(tmp_path, capsys):
    rc, out = run(tmp_path, capsys, slate([pl_row(i) for i in range(10)]), slate([host_row(i) for i in range(10)]))
    for s in SECRETS:
        assert s not in out, s
    assert LINE + "40" in out and "diffs=0 " in out
    assert out.rstrip().splitlines()[-1] == "VERDICT: CLEAN" and rc == ce.EXIT_CLEAN


def test_the_ignore_keys_mode_leaves_them_out_too(tmp_path, capsys):
    rc, out = run(tmp_path, capsys, slate([pl_row(i) for i in range(10)]), slate([host_row(i) for i in range(10)]),
                  "--ignore-keys", "desk,desk_meta,line_move,late_news_flag")
    assert "candidate_" not in out and LINE + "40" in out and rc == ce.EXIT_CLEAN


def test_the_results_row_arm_is_masked_and_counted_host_only(tmp_path, capsys):
    def res(i, arm):
        r = {"match_id": i, "date": f"{DAY}T15:00:00", "home_team": f"Home{i:02d}", "away_team": f"Away{i:02d}",
             "predicted": {"model_version": "v22", "home_win": 0.45}, "graded": {"log_loss": 1.01}}
        if arm is not None:
            r["candidate"] = arm
        return r
    arms = ({"version": EID, "probabilities": {"home_win": FIXTURE_P, "draw": 0.3, "away_win": 0.5},
             "missing": {"home": {"model": 1, "candidate": 0}}, "log_loss": FIXTURE_LL, "brier_score": 0.5,
             "reason": None},
            {"version": EID, "fenced": FIXTURE_REASON},
            {"version": EID, "probabilities": None, "missing": None, "log_loss": None, "brier_score": None,
             "reason": FIXTURE_REASON})
    laptop = {"results": [res(i, None) for i in range(3)]}
    host = {"results": [res(i, arms[i]) for i in range(3)]}
    rc, out = run(tmp_path, capsys, laptop, host, name=f"results_PL_{DAY}.json")
    for s in SECRETS:
        assert s not in out, s
    assert LINE + "3" in out
    assert out.rstrip().splitlines()[-1] == "VERDICT: CLEAN" and rc == ce.EXIT_CLEAN


def test_another_writers_candidate_key_is_still_compared():
    """leagues_candidate rows, soccer_expansion bindings, registry listings: a key named `candidate` holding a string
    (or a dict that is not the pl-availability-v1 arm) is compared and printed as before."""
    assert ce.diff({"r": {"candidate": "leagues-x"}}, {"r": {"candidate": "leagues-y"}}) == [
        "$.r.candidate: 'leagues-x' vs 'leagues-y'"]
    assert ce.diff({"r": {}}, {"r": {"candidate": None}}) == ["$.r.candidate: only in host"]
    assert ce.diff({"r": {"candidate": {"version": "other"}}}, {"r": {"candidate": {"version": "v2"}}}) == [
        "$.r.candidate.version: 'other' vs 'v2'"]
    assert ce.shadow_count({"r": {"candidate": "a"}}, {"r": {"candidate": "b"}}) == 0
    assert ce.shadow_arm("candidate", None, {"version": EID})
    assert not ce.shadow_arm("candidates") and not ce.shadow_arm("my_candidate_x")


def test_a_candidate_key_in_an_unrelated_block_is_masked_at_any_depth(tmp_path, capsys):
    a = {"meta": {"deep": {"x": 1}}, "rows": [{"k": 1}]}
    b = {"meta": {"deep": {"x": 1, "candidate_x": FIXTURE_REASON}}, "rows": [{"k": 1, "candidate_y": [FIXTURE_P]}]}
    rc, out = run(tmp_path, capsys, a, b, name="window_24h.json")
    for s in SECRETS:
        assert s not in out, s
    assert LINE + "2" in out and rc == ce.EXIT_CLEAN


def test_a_laptop_file_with_none_and_no_other_diff_reads_clean_with_the_count(tmp_path, capsys):
    rc, out = run(tmp_path, capsys, slate([pl_row(0)]), slate([host_row(0)]))
    assert LINE + "4" in out and "unit-bearing fields masked (policy v1.2): 0" in out
    assert out.rstrip().splitlines()[-1] == "VERDICT: CLEAN" and rc == ce.EXIT_CLEAN


def test_the_unit_bearing_count_is_unchanged_beside_them(tmp_path, capsys):
    def with_order(r, unit):
        r["desk"] = {"call": "PLAY", "order": {"unit": unit, "text": "FIXTURE-ORDER", "contracts": 10, "limit": 0.5}}
        return r
    plain_l, plain_h = slate([with_order(pl_row(0), "U-A")]), slate([with_order(pl_row(0), "U-B")])
    _, base = run(tmp_path / "base", capsys, plain_l, plain_h)
    rc, out = run(tmp_path / "shadow", capsys, slate([with_order(pl_row(0), "U-A")]),
                  slate([with_order(host_row(0), "U-B")]))
    assert "unit-bearing fields masked (policy v1.2): 3" in base and LINE + "0" in base
    assert "unit-bearing fields masked (policy v1.2): 3" in out and LINE + "4" in out and rc == ce.EXIT_CLEAN


def test_a_structural_mismatch_printed_whole_carries_no_candidate_value(tmp_path, capsys):
    a = {"extra": {"candidate_probabilities": {"home_win": FIXTURE_P}, "p": 1},
         "res": {"candidate": {"version": EID, "log_loss": FIXTURE_LL}}}
    b = {"extra": None, "res": None}
    rc, out = run(tmp_path, capsys, a, b, name="window_24h.json")
    for s in SECRETS:
        assert s not in out, s
    assert "$.extra: \"{'candidate_probabilities': '<masked>', 'p': 1}\" vs 'None'" in out
    assert "$.res: \"{'candidate': '<masked>'}\" vs 'None'" in out
    assert LINE + "2" in out and rc == ce.EXIT_DIVERGENT


def test_the_help_names_the_class(capsys):
    try:
        ce.main(["--help"])
    except SystemExit as e:
        assert e.code == 0
    out = capsys.readouterr().out
    assert "shadow-arm keys" in out and "pl-availability-v1" in out and "addendum 199 item 2" in out
