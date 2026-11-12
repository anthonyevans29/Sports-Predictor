"""Addendum 305 item 2(d) / 306 item 2: the exec <= 0 receipt, a read-only script with --dir (default exports/)."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("exec_non_positive_receipt", ROOT / "scripts" / "exec_non_positive_receipt.py")
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)


def row(mid, call="PLAY", edge=1.5, cost=0.50, p=0.52, pass_kind=None, would=None, pick="HOME"):
    d = {"call": call, "pick": pick, "model_p": p, "exec": {"edge_pp": edge, "basis": "taker", "cost": cost}}
    if pass_kind:
        d["pass_kind"] = pass_kind
    if would:
        d["market_only_hold"] = {"would_call": would}
    return {"match_id": mid, "utc_date": "2026-10-12T17:00:00", "home_team": f"Home {mid}", "away_team": f"Away {mid}",
            "desk": d}


def write(path: Path, fam: str, rows, ids=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"predictions": rows, "closing": {"family": fam, "match_ids": ids or
                                                                 [r["match_id"] for r in rows]}}))


def test_flat_exports_layout_counts_exec_non_positive_plays_by_family(tmp_path, capsys):
    write(tmp_path / "closing_NFL_2026-10-12T1700Z.json", "NFL",
          [row(1, edge=-0.2, cost=0.734, p=0.732), row(2, edge=0.0), row(3, edge=0.1), row(4, edge=4.0)])
    write(tmp_path / "closing_MLB_2026-10-13T2300Z.json", "MLB", [row(5, edge=-1.0), row(6, call="PASS", edge=-3.0)])
    write(tmp_path / "closing_NFL_2026-10-12T1700Z_copy.json", "NFL", [row(9, edge=-5.0)])    # not a closing name
    assert rc.main(["--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "exports: 2 closing file(s), dates 2026-10-12 .. 2026-10-13, by family {'MLB': 1, 'NFL': 1}" in out
    assert "exec edge <= 0: 3 row(s) · by family {'MLB': 1, 'NFL': 2} · distinct games 3" in out
    assert ("NFL · match 1 · 2026-10-12 · kickoff 2026-10-12T17:00:00 · pick Home 1 · exec -0.20pp · all-in cost "
            "0.734 · model 0.732 · on page · closing_NFL_2026-10-12T1700Z.json") in out
    assert "match 2 " in out and "match 9 " not in out and "match 6 " not in out           # exactly 0 is the gap
    assert "SUMMARY: emitted PLAYs with exec <= 0: 3 row(s), 3 distinct game(s)" in out


def test_mirror_layout_skips_latest_and_links_and_dedupes_a_start(tmp_path, capsys):
    f = tmp_path / "host" / "2026-10-20" / "closing_SOCCER_2026-10-20T1400Z.json"
    write(f, "SOCCER", [row(11, edge=-0.5), row(11, edge=-0.5)])
    write(tmp_path / "host" / "latest" / "closing_SOCCER_2026-10-20T1400Z.json", "SOCCER", [row(12, edge=-9.0)])
    (tmp_path / "laptop").mkdir()
    (tmp_path / "laptop" / "2026-10-20").symlink_to(f.parent, target_is_directory=True)
    assert rc.main(["--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "host: 1 closing file(s)" in out and "laptop" not in out.split("files read")[0]
    assert "exec edge <= 0: 1 row(s) · by family {'SOCCER': 1} · distinct games 1" in out
    assert "match 12" not in out


def test_would_be_plays_are_their_own_block_and_never_emitted(tmp_path, capsys):
    write(tmp_path / "closing_NFL_2026-11-09T0120Z.json", "NFL",
          [row(15175, call="PASS", pass_kind="market_only", would="PLAY", edge=-0.21, cost=0.734, p=0.732)])
    assert rc.main(["--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "SUMMARY: emitted PLAYs with exec <= 0: 0 row(s), 0 distinct game(s); would-be PLAYs with exec <= 0: " \
           "1 row(s), 1 distinct game(s)" in out


def test_the_date_bounds_and_an_unstored_edge_is_never_zero(tmp_path, capsys):
    write(tmp_path / "closing_MLB_2026-10-05T2300Z.json", "MLB", [row(1, edge=-1.0)])
    write(tmp_path / "closing_MLB_2026-10-06T2300Z.json", "MLB", [row(2, edge=None)])
    write(tmp_path / "closing_MLB_2026-10-27T2300Z.json", "MLB", [row(3, edge=-1.0)])
    assert rc.main(["--dir", str(tmp_path), "--from", "2026-10-06", "--through", "2026-10-26"]) == 0
    out = capsys.readouterr().out
    assert "start dates 2026-10-06 .. 2026-10-26" in out and "exports: 1 closing file(s)" in out
    assert "no exec edge stored: 1" in out and "exec edge <= 0: 0 row(s)" in out.split("WOULD-BE")[0]


def test_it_writes_nothing_and_prints_no_order_or_count(tmp_path, capsys):
    r = row(1, edge=-0.2)
    r["desk"]["order"] = {"text": "BUY YES KXTEST @ 73 × 4", "contracts": 4}
    r["desk"]["exec"]["contracts"] = 4
    write(tmp_path / "closing_NFL_2026-10-12T1700Z.json", "NFL", [r])
    before = sorted((p, p.stat().st_mtime_ns) for p in tmp_path.rglob("*"))
    assert rc.main(["--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert sorted((p, p.stat().st_mtime_ns) for p in tmp_path.rglob("*")) == before
    assert "BUY" not in out and "×" not in out and "contracts" not in out and "$" not in out


@pytest.mark.parametrize("argv", [["--dir", "/nonexistent/exports"], ["--from", "2026-13-01"]])
def test_refusals_exit_2(tmp_path, argv, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "exports").mkdir()
    assert rc.main(argv) == 2


def test_a_non_object_file_is_unreadable_and_the_rest_is_still_counted(tmp_path, capsys):
    """Codex #903 P2: valid JSON that is not an object ([] or null) is listed UNREADABLE; the run goes on."""
    (tmp_path / "closing_NFL_2026-10-12T1700Z.json").write_text("[]")
    (tmp_path / "closing_NFL_2026-10-13T1700Z.json").write_text("null")
    write(tmp_path / "closing_MLB_2026-10-14T2300Z.json", "MLB", [row(5, edge=-1.0)])
    assert rc.main(["--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "UNREADABLE closing_NFL_2026-10-12T1700Z.json: top level is list, not an object" in out
    assert "UNREADABLE closing_NFL_2026-10-13T1700Z.json: top level is NoneType, not an object" in out
    assert "files read: 1" in out and "exec edge <= 0: 1 row(s) · by family {'MLB': 1}" in out


def test_the_newest_copy_of_a_re_paged_start_is_the_one_read(tmp_path, capsys):
    """Codex #903 P2: a start re-paged after a date boundary leaves a copy in each dated folder of the mirror; the
    newest (its exported_at, then its folder) is read, never the first in path order."""
    name = "closing_NFL_2026-10-13T0015Z.json"
    old, new = tmp_path / "host" / "2026-10-12" / name, tmp_path / "host" / "2026-10-13" / name
    write(old, "NFL", [row(7, edge=-0.4)])
    write(new, "NFL", [row(7, edge=2.0)])
    for f, at in ((old, "2026-10-12T23:40:00Z"), (new, "2026-10-13T00:05:00Z")):
        doc = json.loads(f.read_text())
        doc["exported_at"] = at
        f.write_text(json.dumps(doc))
    assert rc.main(["--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "exec edge <= 0: 0 row(s)" in out.split("WOULD-BE")[0] and "exec edge > 0: 1 row(s)" in out


@pytest.mark.parametrize("edge", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_edge_is_not_stored_never_a_figure(tmp_path, capsys, edge):
    """Codex #903 P2: NaN or an infinity is "no exec edge stored" (law 4), so the block totals reconcile."""
    (tmp_path / "closing_NFL_2026-10-12T1700Z.json").write_text(json.dumps(
        {"predictions": [row(1, edge=edge)], "closing": {"family": "NFL", "match_ids": [1]}}))
    assert rc.main(["--dir", str(tmp_path)]) == 0
    first = capsys.readouterr().out.split("WOULD-BE")[0]
    assert "no exec edge stored: 1" in first and "exec edge <= 0: 0 row(s)" in first and "exec edge > 0: 0 row(s)" in first


def test_the_header_says_it_reads_the_stored_gate_edge(tmp_path, capsys):
    """Addendum 309 item 1: "The receipt script reads the stored gate edge on the files that exist and says so in its
    header (one line)." exec.final_edge_pp is written from the next file on and is not read."""
    r = row(1, edge=0.05, cost=0.567, p=0.5675)
    r["desk"]["exec"].update(final_cost=0.568, final_edge_pp=-0.05, final_units=0.5)
    write(tmp_path / "closing_NFL_2026-11-10T1800Z.json", "NFL", [r])
    assert rc.main(["--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    head = out.splitlines()[:2]
    assert head[1] == rc.GATE_LINE and "GATE exec edge (desk.exec.edge_pp" in head[1]
    assert "from the next file on" in head[1] and sum(1 for x in out.splitlines() if "GATE" in x) == 1
    assert "exec edge <= 0: 0 row(s)" in out.split("WOULD-BE")[0]            # the gate's +0.05pp is what is read


@pytest.mark.parametrize("ids", [5, True, 1.0, "15", {"1": 1, "5": 5}, None, [[1], {"5": 5}]])
def test_a_match_ids_that_is_not_a_list_is_read_as_none(tmp_path, capsys, ids):
    """Codex P2 on #903: closing.match_ids that is not a list is none, so every row counts as outside the run's
    match_ids (a string or an object is never iterated into ids, a number never raises); a list's non-scalar elements
    are skipped."""
    rows = [row("1", edge=-0.5), row("5", edge=-0.6)]
    (tmp_path / "closing_NFL_2026-10-12T1700Z.json").write_text(json.dumps(
        {"predictions": rows, "closing": {"family": "NFL", "match_ids": ids}}))
    assert rc.main(["--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "EMITTED PLAYs (desk.call PLAY): 2 row(s) (0 on their run's page, 2 outside the run's match_ids)" in out
    assert "exec edge <= 0: 2 row(s)" in out.split("WOULD-BE")[0]


def test_a_list_of_match_ids_still_places_rows_on_the_page(tmp_path, capsys):
    rows = [row(1, edge=-0.5), row(5, edge=-0.6)]
    (tmp_path / "closing_NFL_2026-10-12T1700Z.json").write_text(json.dumps(
        {"predictions": rows, "closing": {"family": "NFL", "match_ids": [1, [5], True]}}))
    assert rc.main(["--dir", str(tmp_path)]) == 0
    assert "2 row(s) (1 on their run's page, 1 outside the run's match_ids)" in capsys.readouterr().out


# ---- #907 (Codex's third review of #903): three hardening items ------------------------------------------------------
@pytest.mark.parametrize("mid", [[1, 2], {"id": 7}])
def test_907_a_non_scalar_match_id_is_a_malformed_row_and_the_run_goes_on(tmp_path, capsys, mid):
    """Item 1: a list or object match_id made the dedupe key unhashable and stopped the receipt. It is now a malformed
    row on an UNREADABLE line; the file's other rows and every other file are still counted."""
    write(tmp_path / "closing_NFL_2026-10-12T1700Z.json", "NFL", [row(mid, edge=-0.3), row(2, edge=-0.4)], ids=[2])
    write(tmp_path / "closing_MLB_2026-10-13T2300Z.json", "MLB", [row(5, edge=-1.0)])
    assert rc.main(["--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert (f"UNREADABLE closing_NFL_2026-10-12T1700Z.json: prediction row 0: match_id is {type(mid).__name__}, not "
            "an id (row skipped)") in out
    assert "files read: 2" in out                                    # a malformed row does not unread its file
    assert "exec edge <= 0: 2 row(s) · by family {'MLB': 1, 'NFL': 1}" in out


@pytest.mark.parametrize("preds,why", [({"a": 1}, "predictions is dict"), (7, "predictions is int"),
                                       (None, "predictions is NoneType"), ("absent", "no predictions key")])
def test_907_a_predictions_that_is_not_a_list_makes_the_file_unreadable(tmp_path, capsys, preds, why):
    """Item 2: an object, scalar or null under predictions (or no key) read as zero rows and the file counted as read.
    It is now UNREADABLE, so an archived file cannot drop out of the count silently."""
    f = tmp_path / "closing_NFL_2026-10-12T1700Z.json"
    doc = {"closing": {"family": "NFL", "match_ids": [1]}}
    if preds != "absent":
        doc["predictions"] = preds
    f.write_text(json.dumps(doc))
    write(tmp_path / "closing_MLB_2026-10-13T2300Z.json", "MLB", [row(5, edge=-1.0)])
    assert rc.main(["--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert f"UNREADABLE closing_NFL_2026-10-12T1700Z.json: {why}, not a list" in out
    assert "files read: 1" in out


def test_907_a_superseded_copy_never_re_adds_a_game_the_newer_copy_dropped(tmp_path, capsys):
    """Item 3: a later copy of one start that omits a game (started or called off) left the older copy free to re-add
    its stale row. Only the newest copy per (family, start stamp) is read; the older is listed SUPERSEDED."""
    name = "closing_NFL_2026-10-13T0015Z.json"
    old, new = tmp_path / "host" / "2026-10-12" / name, tmp_path / "host" / "2026-10-13" / name
    write(old, "NFL", [row(7, edge=2.0), row(8, edge=-0.9)])        # game 8 later dropped from the start
    write(new, "NFL", [row(7, edge=2.0)])
    for f, at in ((old, "2026-10-12T23:40:00Z"), (new, "2026-10-13T00:05:00Z")):
        doc = json.loads(f.read_text())
        doc["exported_at"] = at
        f.write_text(json.dumps(doc))
    assert rc.main(["--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "match 8" not in out and "exec edge <= 0: 0 row(s)" in out.split("WOULD-BE")[0]
    assert f"SUPERSEDED host/2026-10-12/{name}: an older copy of a start a newer file holds; none of its rows read" in out
    assert "files read: 1 · superseded copies: 1" in out


def test_907_an_unreadable_newest_copy_is_never_stood_in_for_by_an_older_one(tmp_path, capsys):
    """Law 4: when the newest copy of a start is unreadable, the start is UNREADABLE; the older copy is superseded,
    not read in its place (it would be the stale record)."""
    name = "closing_NFL_2026-10-13T0015Z.json"
    old, new = tmp_path / "host" / "2026-10-12" / name, tmp_path / "host" / "2026-10-13" / name
    write(old, "NFL", [row(8, edge=-0.9)])
    old.write_text(json.dumps({**json.loads(old.read_text()), "exported_at": "2026-10-12T23:40:00Z"}))
    new.parent.mkdir(parents=True)
    new.write_text(json.dumps({"exported_at": "2026-10-13T00:05:00Z", "predictions": None,
                               "closing": {"family": "NFL", "match_ids": []}}))
    assert rc.main(["--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert f"UNREADABLE host/2026-10-13/{name}: predictions is NoneType, not a list" in out
    assert f"SUPERSEDED host/2026-10-12/{name}" in out and "match 8" not in out
    assert "files read: 0 · superseded copies: 1" in out


def _stamped(f, at):
    doc = json.loads(f.read_text())
    if at is None:
        doc.pop("exported_at", None)
    else:
        doc["exported_at"] = at
    f.write_text(json.dumps(doc))


@pytest.mark.parametrize("bad_text,why", [('{"predictions": [', "JSONDecodeError"),
                                          ("[1]", "top level is list, not an object")])
def test_907_review_a_newest_copy_that_will_not_parse_never_lets_an_older_copy_stand_in(tmp_path, capsys, bad_text,
                                                                                         why):
    """Pre-push review, case A/G: invalid JSON (or a top level that is not an object) in the NEWER copy was dropped
    before the per-start choice, so the older copy won the start and its stale row was counted."""
    name = "closing_NFL_2026-10-13T0015Z.json"
    old, new = tmp_path / "host" / "2026-10-12" / name, tmp_path / "host" / "2026-10-13" / name
    write(old, "NFL", [row(8, edge=-0.5)])
    _stamped(old, "2026-10-12T23:40:00Z")
    new.parent.mkdir(parents=True)
    new.write_text(bad_text)
    assert rc.main(["--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert f"UNREADABLE host/2026-10-13/{name}: {why}" in out and f"SUPERSEDED host/2026-10-12/{name}" in out
    assert "match 8" not in out and "files read: 0 · superseded copies: 1" in out


def test_907_review_a_copy_without_exported_at_is_never_ranked_oldest_for_it(tmp_path, capsys):
    """Case B: the newer folder's copy carries no exported_at; "" sorted lowest, so the older copy won and re-added
    its stale game. With a stamp missing on any copy the folder decides."""
    name = "closing_NFL_2026-10-13T0015Z.json"
    old, new = tmp_path / "host" / "2026-10-12" / name, tmp_path / "host" / "2026-10-13" / name
    write(old, "NFL", [row(7, edge=2.0), row(8, edge=-0.9)])
    _stamped(old, "2026-10-12T23:40:00Z")
    write(new, "NFL", [row(7, edge=2.0)])
    _stamped(new, None)
    assert rc.main(["--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "match 8" not in out and f"SUPERSEDED host/2026-10-12/{name}" in out


@pytest.mark.parametrize("old_family,new_family", [("nfl", "NFL"), (["NFL"], "NFL"), (5, 5)])
def test_907_review_the_start_is_its_file_name_never_closing_family(tmp_path, capsys, old_family, new_family):
    """Cases C, D, H: grouping by closing.family let mismatched copies escape supersession (a stale row counted), and a
    list or a number there crashed the run. The start (family, stamp) is read from the file name."""
    name = "closing_NFL_2026-10-13T0015Z.json"
    old, new = tmp_path / "host" / "2026-10-12" / name, tmp_path / "host" / "2026-10-13" / name
    for f, fam, rows, at in ((old, old_family, [row(8, edge=-0.9)], "2026-10-12T23:40:00Z"),
                             (new, new_family, [row(9, edge=3.0)], "2026-10-13T00:05:00Z")):   # a row, so the family is sorted
        f.parent.mkdir(parents=True)
        f.write_text(json.dumps({"exported_at": at, "predictions": rows, "closing": {"family": fam, "match_ids": []}}))
    write(tmp_path / "closing_MLB_2026-10-14T2300Z.json", "MLB", [row(5, edge=-1.0)])
    assert rc.main(["--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "match 8" not in out and "files read: 2 · superseded copies: 1" in out
    assert "exec edge <= 0: 1 row(s) · by family {'MLB': 1}" in out


@pytest.mark.parametrize("mid", [True, 1.0, None])
def test_907_review_a_bool_float_or_none_match_id_is_malformed_never_merged(tmp_path, capsys, mid):
    """Case E (pre-existing): True and 1.0 hash equal to 1 and two None rows merged, so rows were silently lost. Any
    match_id that is not an int or a string is a malformed row, as _match_ids already reads ids."""
    write(tmp_path / "closing_NFL_2026-10-12T1700Z.json", "NFL", [row(1, edge=-0.5), row(mid, edge=-0.5)], ids=[1])
    assert rc.main(["--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert (f"UNREADABLE closing_NFL_2026-10-12T1700Z.json: prediction row 1: match_id is {type(mid).__name__}, not "
            "an id (row skipped)") in out
    assert "exec edge <= 0: 1 row(s)" in out.split("WOULD-BE")[0]
