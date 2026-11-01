"""THE GRADED EXPORT ON A RESULTS ROW (#755; ARCHITECT 2026-11-01, addendum 196 item 4(i), built by addendum 200
item 2), verbatim: "each graded results row carries the graded export's run_id and exported_at; read-side naming only;
no grade, threshold or Desk rule moves; the tests pin the two keys on a closing row and on a slate row of one game."

One game (50548, Tampa Bay Rays @ Cleveland Guardians, now 2026-10-18 21:00Z) graded on a throwaway SQLite
(tests/test_record_vs_close.py's iso_db): its slate file (mlb_MLB_2026-10-18.json, Desk-annotated as export-predictions
--desk writes it) and its closing file (closing.closing_doc / closing_name, as a closing run writes it). The closing
row stands over the slate row (#632's rule), whatever the files' order or times; the grade is the database's, the same
either way."""
import json
from datetime import datetime

from src.walters import desk_policy as dp
from src.walters import graded_export as ge
from src.walters import redated as rd
from tests.test_desk_kickoff_clock import mil_lad, tb_cle_tonight
from tests.test_record_vs_close import iso_db  # noqa: F401  (a fixture: a throwaway SQLite, cwd = tmp_path)
from tests.test_void_redated import (LABEL, NEW_START, OLD_START, _closing, _mlb_export, _mlb_world,
                                     fresh_50548)

SLATE_AT = "2026-10-18T14:05:00.123456Z"            # the slate's export, the morning of the game
CLOSE_AT = "2026-10-18T20:25:31.654321Z"            # the closing run's export, T-35
RUN_ID = "20261018T202500Z-mlb-closing"              # closing.py: f"{now:%Y%m%dT%H%M%SZ}-{chain}"
SLATE = "mlb_MLB_2026-10-18.json"
CLOSE = "closing_MLB_2026-10-18T2100Z.json"
NONE = {"kind": None, "file": None, "run_id": None, "exported_at": None}


def _export_doc(rows, at):
    """An export-predictions --desk document: the export's own keys, then the Desk's blocks and desk_meta."""
    doc = {"exported_at": at, "git_sha": "abc1234", "sport": "mlb", "start_date": "2026-10-18T08:00:00",
           "end_date": "2026-10-19T08:00:00", "competition_code": "MLB", "count": len(rows),
           "predictions": [dict(r) for r in rows]}
    return dp.annotate(doc, now=datetime(2026, 10, 18, 14, 5))


def write_slate(ex, rows, at=SLATE_AT, name=SLATE):
    ex.mkdir(parents=True, exist_ok=True)
    (ex / name).write_text(json.dumps(_export_doc(rows, at)))
    return ex / name


def write_close(ex, start, rows, at=CLOSE_AT, run_id=RUN_ID):
    cl = _closing()
    ex.mkdir(parents=True, exist_ok=True)
    doc = cl.closing_doc(_export_doc(rows, at), "MLB", start, run_id, [r["match_id"] for r in rows], [])
    p = ex / cl.closing_name("MLB", start)
    p.write_text(json.dumps(doc))
    return p


def _rows(doc):
    return {r["match_id"]: r for r in doc["results"]}


def _grade(r):
    return {k: r[k] for k in ("predicted", "actual", "graded")}


def test_the_two_keys_on_a_slate_row_then_the_closing_row_of_one_game_wins_named(iso_db, tmp_path):
    _mlb_world()
    ex = tmp_path / "ex"
    write_slate(ex, [fresh_50548(), mil_lad()])
    slate = _mlb_export(ex)
    r = _rows(slate)[50548]
    assert r["graded_export"] == {"kind": "slate", "file": SLATE, "run_id": None, "exported_at": SLATE_AT}
    assert _rows(slate)[50547]["graded_export"]["kind"] == "slate"
    assert slate["graded_exports"] == {"closing": 0, "slate": 2, "none": 0, "closing_files": 0, "slate_files": 1,
                                       "unreadable": []}
    p = write_close(ex, NEW_START, [fresh_50548()])
    assert p.name == CLOSE and json.loads(p.read_text())["closing"]["run_id"] == RUN_ID
    closing = _mlb_export(ex)
    r2 = _rows(closing)[50548]
    assert r2["graded_export"] == {"kind": "closing", "file": CLOSE, "run_id": RUN_ID, "exported_at": CLOSE_AT}
    assert _rows(closing)[50547]["graded_export"]["kind"] == "slate"           # no closing names it: its slate stands
    assert (closing["graded_exports"]["closing"], closing["graded_exports"]["slate"]) == (1, 1)
    # read-side naming only: the grade, the record and every other field are the database's, unchanged
    assert _grade(r) == _grade(r2)
    assert {k: v for k, v in r.items() if k != "graded_export"} == {k: v for k, v in r2.items() if k != "graded_export"}
    assert slate["record"] == closing["record"] and slate["totals_pulse"] == closing["totals_pulse"]


def test_the_closing_row_wins_by_kind_never_by_time_or_order(iso_db, tmp_path):
    """#632 R1, verbatim: "the closing file's row stands over any slate row for its games [...] A rule by kind, never
    by the listing's order." A slate re-exported after the closing still loses."""
    _mlb_world()
    ex = tmp_path / "ex"
    write_close(ex, NEW_START, [fresh_50548()])
    write_slate(ex, [fresh_50548()], at="2026-10-18T22:30:00Z", name="mlb_MLB_2026-10-18_to_2026-10-19.json")
    r = _rows(_mlb_export(ex))[50548]
    assert r["graded_export"] == {"kind": "closing", "file": CLOSE, "run_id": RUN_ID, "exported_at": CLOSE_AT}


def test_no_export_names_the_game_every_key_null(iso_db, tmp_path):
    _mlb_world()
    doc = _mlb_export(tmp_path / "none")
    assert all(r["graded_export"] == NONE for r in doc["results"])
    assert doc["graded_exports"] == {"closing": 0, "slate": 0, "none": 2, "closing_files": 0, "slate_files": 0,
                                     "unreadable": []}


def test_the_newest_slate_holding_the_game_stands_and_only_a_desk_slate_counts(iso_db, tmp_path):
    _mlb_world()
    ex = tmp_path / "ex"
    write_slate(ex, [fresh_50548()], at="2026-10-17T13:00:00Z", name="mlb_MLB_2026-10-17.json")
    write_slate(ex, [fresh_50548()])                                            # the newer: stands
    no_desk = {k: v for k, v in _export_doc([fresh_50548()], "2026-10-18T19:00:00Z").items() if k != "desk_meta"}
    (ex / "mlb_MLB_2026-10-18_nodesk.json").write_text(json.dumps(no_desk))    # no desk calls: never a slate
    (ex / "mlb_MLB_results_2026-10-17.json").write_text(json.dumps({"exported_at": "2026-10-18T23:00:00Z",
                                                                    "sport": "mlb", "results": []}))
    (ex / "mlb_MLB_2026-10-19.json").write_text("{not json")                    # unreadable: counted, named
    write_slate(ex / "host", [fresh_50548()], at="2026-10-18T23:59:00Z")       # the host's copy: never read
    doc = _mlb_export(ex)
    r = _rows(doc)[50548]
    assert r["graded_export"] == {"kind": "slate", "file": SLATE, "run_id": None, "exported_at": SLATE_AT}
    assert doc["graded_exports"]["slate_files"] == 2
    assert doc["graded_exports"]["unreadable"] == ["mlb_MLB_2026-10-19.json"]
    assert _rows(doc)[50547]["graded_export"] == NONE                          # no slate file holds 50547


def test_a_re_dated_game_names_the_fresh_closing_and_a_void_one_the_row_its_label_reads(iso_db, tmp_path):
    """The void rule's own selection (redated.void_label; exec_cohorts.tally): the fresh closing on the new date is the
    graded row; with only the old one, the row is void and names the closing its label reads."""
    _mlb_world()
    ex = tmp_path / "ex"
    write_close(ex, OLD_START, [tb_cle_tonight()], at="2026-10-16T23:25:00Z", run_id="20261016T232500Z-mlb-closing")
    doc = _mlb_export(ex)
    r = _rows(doc)[50548]
    assert r["redated"] == LABEL
    assert r["graded_export"] == {"kind": "closing", "file": "closing_MLB_2026-10-17T0000Z.json",
                                  "run_id": "20261016T232500Z-mlb-closing", "exported_at": "2026-10-16T23:25:00Z"}
    write_close(ex, NEW_START, [fresh_50548()])
    r = _rows(_mlb_export(ex))[50548]
    assert "redated" not in r
    assert r["graded_export"] == {"kind": "closing", "file": CLOSE, "run_id": RUN_ID, "exported_at": CLOSE_AT}


def test_closing_rows_exports_are_aligned_with_its_rows(tmp_path):
    ex = tmp_path / "ex"
    write_close(ex, NEW_START, [fresh_50548()])
    write_close(ex, OLD_START, [tb_cle_tonight()], at="2026-10-16T23:25:00Z", run_id="R-OLD")
    (ex / "closing_MLB_bad.json").write_text("[1]")
    cr = rd.closing_rows(ex)
    assert [run for run, _, _ in cr["rows"][50548]] == [OLD_START, NEW_START]
    assert cr["exports"][50548] == [
        {"file": "closing_MLB_2026-10-17T0000Z.json", "run_id": "R-OLD", "exported_at": "2026-10-16T23:25:00Z"},
        {"file": CLOSE, "run_id": RUN_ID, "exported_at": CLOSE_AT}]
    assert cr["unreadable"] == ["closing_MLB_bad.json"] and set(cr["exports"]) == set(cr["rows"])


def test_the_console_counts_the_rows_by_the_export_they_name(iso_db, tmp_path):
    from click.testing import CliRunner

    import cli
    _mlb_world()
    write_slate(tmp_path / "exports", [mil_lad()])
    write_close(tmp_path / "exports", NEW_START, [fresh_50548()])
    (tmp_path / "exports" / "closing_MLB_bad.json").write_text("{not json")
    res = CliRunner().invoke(cli.cli, ["export-results", "--sport", "mlb", "--competition", "MLB", "--date",
                                       "2026-10-18", "--out", str(tmp_path / "m.json")])
    assert res.exit_code == 0, res.output
    assert ("  graded export: closing 1 · slate 0 · none 0 (unreadable, never read: closing_MLB_bad.json)"
            in res.output.splitlines())
    row = json.load(open(tmp_path / "m.json"))["results"][0]
    assert row["match_id"] == 50548 and row["graded_export"]["run_id"] == RUN_ID


def test_counts_line():
    c = {"closing": 3, "slate": 1, "none": 2, "unreadable": []}
    assert ge.counts_line(c) == "graded export: closing 3 · slate 1 · none 2"


# ---- the selection within the clock drift (review on #755: "the newest, always" must fail) ----------------------

LATE_RUN = datetime(2026, 10, 18, 21, 5)             # a later closing run whose row recorded a stale start (OLD_START)


def test_the_older_closing_within_the_drift_stands_over_a_newer_one_whose_row_is_off_the_start(iso_db, tmp_path):
    """exec_cohorts.tally's selection: the newest run's row within DESK_CLOCK_DRIFT of the current start, NOT the
    newest run. Run A (older) recorded the game's current start; run B (newer) recorded a start 45 h off."""
    _mlb_world()
    ex = tmp_path / "ex"
    write_close(ex, NEW_START, [fresh_50548()])                                          # A: utc_date = NEW_START
    b = write_close(ex, LATE_RUN, [tb_cle_tonight()], at="2026-10-18T21:05:40Z", run_id="20261018T210500Z-mlb-closing")
    assert rd.closing_rows(ex)["exports"][50548][-1]["file"] == b.name                  # B is the newest run
    r = _rows(_mlb_export(ex))[50548]
    assert r["graded_export"] == {"kind": "closing", "file": CLOSE, "run_id": RUN_ID, "exported_at": CLOSE_AT}


def test_the_older_slate_within_the_drift_stands_over_a_newer_one_whose_row_is_off_the_start(iso_db, tmp_path):
    _mlb_world()
    ex = tmp_path / "ex"
    write_slate(ex, [fresh_50548()])                                                    # older: utc_date = NEW_START
    write_slate(ex, [tb_cle_tonight()], at="2026-10-18T19:00:00Z", name="mlb_MLB_2026-10-18_late.json")   # newer, 45 h off
    r = _rows(_mlb_export(ex))[50548]
    assert r["graded_export"] == {"kind": "slate", "file": SLATE, "run_id": None, "exported_at": SLATE_AT}


# ---- NFL: export-nfl-results names the graded export too (review on #755) ----------------------------------------

def test_the_nfl_results_file_names_the_closing_row_and_counts_it(iso_db, tmp_path):
    from src.walters.nfl_predict import export_nfl_results
    from tests.test_void_redated import _nfl_world
    _nfl_world(tmp_path)                       # one NFL closing file (run_id "run-10181700"), both games in it
    ex = tmp_path / "ex"
    doc = json.load(open(export_nfl_results(out_dir=str(ex))))
    rows = {r["match_id"]: r for r in doc["results"]}
    name = "closing_NFL_2026-10-18T1700Z.json"
    assert (ex / name).exists()
    held = json.loads((ex / name).read_text())
    want = {"kind": "closing", "file": name, "run_id": "run-10181700", "exported_at": held.get("exported_at")}
    assert rows[70002]["graded_export"] == want                 # graded, named
    assert rows[70001]["graded_export"] == want                 # void (re-dated): names the row its label reads
    assert doc["graded_exports"] == {"closing": 2, "slate": 0, "none": 0, "closing_files": 1, "slate_files": 0,
                                     "unreadable": []}
