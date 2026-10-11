"""THE CUTOVER PL CHECK (#420 RULED, ARCHITECT 2026-10-11, addendum 38; #422 RULED, addendum 40 item 9):
compare_exports.py --ignore-keys (the keys read off the clock, printed) and --require-predictions (the count of rows
with a prediction and its probabilities on each side; none is NO-COVERAGE). Both off by default."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))
import compare_exports as ce  # noqa: E402

KEYS = "desk,desk_meta,line_move,late_news_flag"
F = "soccer_PL_2026-10-17_to_2026-10-20.json"


def row(home, p, *, desk_call="PASS", line_move=None, late=False, pred=True):
    return {"match_id": 1, "utc_date": "2026-10-18T14:00:00", "home_team": home, "away_team": f"{home} B",
            "prediction": ({"probabilities": {"home_win": p, "draw": 0.25, "away_win": round(0.75 - p, 4)}}
                           if pred else None),
            "desk": {"call": desk_call}, "line_move": line_move, "late_news_flag": late}


def doc(rows, as_of="2026-10-17T08:00:00Z"):
    return {"sport": "soccer", "count": len(rows), "desk_meta": {"as_of": as_of, "started_rule": True},
            "predictions": rows}


def run(tmp_path, a, b, *extra):
    la, ho = tmp_path / "ref", tmp_path / "host"
    la.mkdir()
    ho.mkdir()
    (la / F).write_text(json.dumps(a))
    (ho / F).write_text(json.dumps(b))
    return ce.main([str(la), str(ho), "--since", "0", *extra])


def test_clock_read_fields_are_left_out_and_named_db_fields_still_compared(tmp_path, capsys):
    a = doc([row("Arsenal", 0.55, desk_call="PLAY"), row("Leeds", 0.40)])
    b = doc([row("Arsenal", 0.55, desk_call="PASS", line_move={"pp": 4.1}, late=True), row("Leeds", 0.40)],
            as_of="2026-10-17T13:30:00Z")
    b["desk_meta"]["started_rule"] = False
    assert run(tmp_path, a, b) == ce.EXIT_DIVERGENT                      # without the flag: as before
    capsys.readouterr()
    (tmp_path / "x").mkdir()
    assert run(tmp_path / "x", a, b, "--ignore-keys", KEYS, "--require-predictions") == ce.EXIT_CLEAN
    out = capsys.readouterr().out
    assert "left out of the comparison (--ignore-keys, read off the clock): desk, desk_meta, late_news_flag, line_move" in out
    assert "predictions compared (rows with a prediction and its probabilities): laptop 2 · host 2" in out
    assert out.strip().splitlines()[-1] == "VERDICT: CLEAN"
    b2 = doc([row("Arsenal", 0.56), row("Leeds", 0.40)])                 # a number from the database differs
    (tmp_path / "y").mkdir()
    assert run(tmp_path / "y", a, b2, "--ignore-keys", KEYS, "--require-predictions") == ce.EXIT_DIVERGENT


def test_a_file_with_no_predictions_is_no_coverage_never_clean(tmp_path, capsys):
    a = doc([row("Arsenal", 0.55, pred=False)])
    assert run(tmp_path, a, a) == ce.EXIT_CLEAN                          # without the flag: two empty files CLEAN
    capsys.readouterr()
    (tmp_path / "x").mkdir()
    assert run(tmp_path / "x", a, a, "--ignore-keys", KEYS, "--require-predictions") == ce.EXIT_NO_COVERAGE
    out = capsys.readouterr().out
    assert "laptop 0 · host 0" in out and out.strip().splitlines()[-1].startswith("VERDICT: NO-COVERAGE")
    (tmp_path / "y").mkdir()
    assert run(tmp_path / "y", doc([]), doc([]), "--require-predictions") == ce.EXIT_NO_COVERAGE


def test_ignore_keys_reaches_every_depth_and_nothing_else():
    a = {"predictions": [{"home_team": "A", "away_team": "B", "utc_date": "x", "desk": 1, "p": 1}]}
    b = {"predictions": [{"home_team": "A", "away_team": "B", "utc_date": "x", "desk": 2, "p": 2}]}
    assert ce.diff(a, b, ignore=frozenset({"desk"})) == ["$.predictions[B @ A x].p: '1' vs '2'"]
    assert len(ce.diff(a, b)) == 2


# ---- Codex on #439 -----------------------------------------------------------------------------------------------

def test_the_cutover_mode_compares_database_timestamps_the_generic_mask_would_hide(tmp_path, capsys):
    a = doc([{**row("Arsenal", 0.55), "computed_at": "2026-10-17T07:00:00",
              "market": {"captured_at": "2026-10-17T06:00:00"}}])
    b = doc([{**row("Arsenal", 0.55), "computed_at": "2026-10-17T07:05:00",
              "market": {"captured_at": "2026-10-17T06:00:00"}}])
    assert run(tmp_path, a, b) == ce.EXIT_CLEAN                          # the generic mask: as before
    capsys.readouterr()
    (tmp_path / "x").mkdir()
    assert run(tmp_path / "x", a, b, "--ignore-keys", KEYS, "--require-predictions") == ce.EXIT_DIVERGENT
    out = capsys.readouterr().out
    assert "computed_at: '2026-10-17T07:00:00' vs '2026-10-17T07:05:00'" in out
    assert "the timestamp mask is off" in out
    b["predictions"][0]["computed_at"] = "2026-10-17T07:00:00"
    b["predictions"][0]["match_id"] = 2                                  # match_id is read from the database too
    (tmp_path / "y").mkdir()
    assert run(tmp_path / "y", a, b, "--ignore-keys", KEYS, "--require-predictions") == ce.EXIT_DIVERGENT
    b["predictions"][0]["match_id"] = 1
    a["exported_at"], b["exported_at"], a["git_sha"], b["git_sha"] = "t1", "t2", "abc", "def"
    (tmp_path / "z").mkdir()
    assert run(tmp_path / "z", a, b, "--ignore-keys", KEYS + ",exported_at", "--require-predictions") == ce.EXIT_CLEAN


def test_a_missing_host_file_is_no_coverage_not_divergent(tmp_path, capsys):
    la, ho = tmp_path / "ref", tmp_path / "host"
    la.mkdir()
    ho.mkdir()
    (la / F).write_text(json.dumps(doc([row("Arsenal", 0.55)])))
    assert ce.main([str(la), str(ho), "--since", "0"]) == ce.EXIT_DIVERGENT     # without the flag: as before
    capsys.readouterr()
    assert ce.main([str(la), str(ho), "--since", "0", "--ignore-keys", KEYS,
                    "--require-predictions"]) == ce.EXIT_NO_COVERAGE
    assert capsys.readouterr().out.strip().splitlines()[-1] == "VERDICT: NO-COVERAGE (0 compared) — not a data verdict"
