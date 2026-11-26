"""503's PR 2, THE STALE PREDICTION AT A CLOSING (ARCHITECT 2026-11-24, addendum 502 item 2 Q2: "R2 reaches the
prediction: a closing row whose prediction was computed before the run's start is stale exactly as a stale price
is"; addendum 503 item 1 Q1-Q2; ARCHITECT 2026-11-26, addendum 563, the four questions ruled). On the closing runs'
box frame (tests/test_closing_runs.py: a throwaway DB under tmp_path, every side effect faked, no network), whose
export step stamps every MLB and SOCCER row's prediction.computed_at with the step's time (563 item 6); a test plants
its own value through `box.computed`. The switch ships OFF (563 item 2); the tests that pin it ON set it on here."""
import ast
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.test_closing_runs import (DROP_STAMP, MACHINE, NOW, at, box, c, call_pages, fake_clock,  # noqa: F401
                                     make_box, mc, no_channel, runs, slow_steps)

pytestmark = pytest.mark.usefixtures("nfl_market_only_off")

CLOSING = Path(__file__).resolve().parent.parent / "deploy" / "hosting" / "closing.py"
KEY = mc.STALE_PREDICTIONS_OFF_KEY
OLD = "2026-10-11T16:00:00"                            # naive, as export.py writes it: 25 minutes before the start
RUN_START = "2026-10-11T16:25:00Z"
OFF_HEAD = "· stale predictions (rule off, counted only: fails nothing): "
# (family, start in minutes from NOW, a covered match, its start ET and game)
FAMS = [("MLB", 30, 101, "2026-10-11 12:55 ET", "Underhill Visitors @ Underhill"),
        ("SOCCER", 35, 401, "2026-10-11 13:00 ET", "Arsenal Visitors @ Arsenal")]


@pytest.fixture
def on(monkeypatch):
    """The switch on, for this test only (563 item 2(b): only an addendum turns it on outside a test)."""
    monkeypatch.setitem(mc.STALE_PREDICTION_RULE, "on", True)


def entry(mid, start_et, game, cause, computed_at=None):
    return {"match_id": mid, "game": game, "start_et": start_et, "cause": cause, "computed_at": computed_at,
            "run_start": RUN_START}


def before(mid, start_et, game, computed_at=OLD + "Z"):
    return entry(mid, start_et, game, "computed before the run's start", computed_at)


def exports(box):
    return sorted(p.name for p in (box.repo / "exports").iterdir())


def closing_files(box):
    return sorted((box.repo / "exports").glob("closing_*.json"))


def lines_with(out, text):
    return [ln for ln in out.splitlines() if text in ln]


# =============================================================================================== the switch ==

def test_the_switch_ships_off_and_is_read_by_itself():
    """563 item 2: "OFF AT MERGE [...] behind its own closing-side switch"; (b) "The code ties the two switches to
    nothing: each is read by itself." Read from the file's own text (AST), not from a value a test may have set."""
    tree = ast.parse(CLOSING.read_text())
    found = [n for n in tree.body if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == "STALE_PREDICTION_RULE" for t in n.targets)]
    assert len(found) == 1 and ast.literal_eval(found[0].value) == {"on": False}
    assert ast.unparse(found[0]) == "STALE_PREDICTION_RULE = {'on': False}"
    assert mc.STALE_PREDICTION_RULE == {"on": False}
    # tied to nothing: no other assignment to it, and the Desk's switch is never named in code (a comment may say so)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert "STALE_PRICE_RULE" not in names
    stores = [n for n in ast.walk(tree) if isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign))
              and "STALE_PREDICTION_RULE" in ast.unparse(n).split("=")[0]]
    assert stores == found[:1]
    assert mc.STALE_PREDICTIONS_OFF_KEY == "stale_predictions_would_fail"


def test_closing_imports_no_desk():
    """C8: closing.py reads the export, never the Desk's code; 563 builds the check in closing.py alone."""
    tree = ast.parse(CLOSING.read_text())
    mods = [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    mods += [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert not [m for m in mods if "desk" in m.lower()], mods
    assert not re.search(r"^\s*(import|from)\s.*desk_policy", CLOSING.read_text(), re.M)


def test_the_families_that_carry_a_stamp_by_contract():
    """503 item 1 Q1: "WHERE THE EXPORT CARRIES ONE BY CONTRACT (the Premier League's rows and MLB's) [...] NFL rows
    carry none [...]; they are untouched." """
    assert {f: v["computed"] for f, v in mc.FAMILIES.items()} == {"MLB": True, "NFL": False, "SOCCER": True}
    assert "stale predictions" in mc.OWN_CHECK_FAILURES and "stale prices" in mc.OWN_CHECK_FAILURES


# ================================================================================= the check, by its words ==

def _doc(v, mid=1):
    pred = {"probabilities": {"home_win": 0.5}} if v is DROP_STAMP else {"probabilities": {}, "computed_at": v}
    return {"predictions": [{"match_id": mid, "prediction": pred}]}, [
        {"match_id": mid, "away": "A", "home": "H", "start_et": "2026-10-11 13:00 ET"}]


HELD_FRAC = datetime(2026, 10, 11, 16, 25, 0, 300000, tzinfo=timezone.utc)
HELD_WHOLE = datetime(2026, 10, 11, 16, 25, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("held", [HELD_FRAC, HELD_WHOLE], ids=["held-with-fraction", "held-whole-second"])
@pytest.mark.parametrize("stamp,stale", [
    ("2026-10-11T16:24:59", True), ("2026-10-11T16:24:59.999999", True),
    ("2026-10-11T16:25:00", True), ("2026-10-11T16:25:00.999999", True),        # in held's own second: stale
    ("2026-10-11 16:25:00.000000", True), ("2026-10-11T16:25:00.900000Z", True),
    ("2026-10-11T16:25:01", False), ("2026-10-11T16:25:01Z", False),            # one second after: fresh
    ("2026-10-11T12:25:01-04:00", False), ("2026-10-11T12:25:00.500000-04:00", True),
])
def test_the_one_second_boundary(held, stamp, stale):
    """563 item 1: "the comparison R2 makes, a stamp in the start's own second stale". Read with parse_utc as R2
    reads a capture; stale before the start or in its own second, whether or not the start carries a fraction."""
    doc, rows = _doc(stamp)
    got = mc.stale_predictions(doc, rows, held)
    assert bool(got) is stale
    if stale:
        assert got == [{"match_id": 1, "game": "A @ H", "start_et": "2026-10-11 13:00 ET",
                        "cause": "computed before the run's start", "computed_at": mc.iso_z(mc.parse_utc(stamp)),
                        "run_start": "2026-10-11T16:25:00Z"}]


def test_it_is_r2s_comparison_wherever_the_start_carries_a_fraction():
    """Where the run's start carries a fraction (every real run: held is taken from the clock under the lock), the
    rule is R2's own `parse_utc(stamp) < start` on the export's naive form, second for second across the boundary."""
    for us in (1, 300000, 999999):
        held = HELD_WHOLE.replace(microsecond=us)
        for sec in range(-3, 4):
            for frac in ("", ".000001", ".5", ".999999"):
                t = (HELD_WHOLE + timedelta(seconds=sec)).replace(tzinfo=None).isoformat() + frac
                doc, rows = _doc(t)
                assert bool(mc.stale_predictions(doc, rows, held)) is (mc.parse_utc(t) < held), (t, us)


@pytest.mark.parametrize("v,cause,text", [
    (DROP_STAMP, "no computed time", "prediction carries no computed time"),
    (None, "no computed time", "prediction carries no computed time"),
    ("garbage", "computed time unreadable", "prediction computed time unreadable"),
    ("", "computed time unreadable", "prediction computed time unreadable"),
    ("2026-13-45T99:00:00", "computed time unreadable", "prediction computed time unreadable"),
    (20261011, "computed time unreadable", "prediction computed time unreadable"),
    ("0001-01-01T00:00:00+05:00", "computed time unreadable", "prediction computed time unreadable"),
])
def test_missing_null_and_unreadable_are_stale_with_their_own_words(v, cause, text):
    """503 item 1 Q1 (law 4) and 563 item 4 (Q3): "With no stamp: "prediction carries no computed time". With a stamp
    that does not parse: "prediction computed time unreadable". Never "computed never"." """
    doc, rows = _doc(v)
    got = mc.stale_predictions(doc, rows, HELD_FRAC)
    assert got == [{"match_id": 1, "game": "A @ H", "start_et": "2026-10-11 13:00 ET", "cause": cause,
                    "computed_at": None, "run_start": "2026-10-11T16:25:00Z"}]
    assert mc.prediction_text(got[0]) == text and "never" not in text


def test_the_words_with_a_stamp():
    x = {"cause": "computed before the run's start", "computed_at": "2026-10-11T16:00:00Z",
         "run_start": "2026-10-11T16:25:00Z"}
    assert mc.prediction_text(x) == ("prediction computed 2026-10-11T16:00:00Z, before the run's start "
                                     "2026-10-11T16:25:00Z")


# ============================================================================= ON: its own failure (563 Q2) ==

@pytest.mark.parametrize("fam,start,mid,start_et,game", FAMS)
def test_on_a_stale_stamp_fails_the_closing_as_stale_predictions(box, on, capsys, fam, start, mid, start_et, game):
    """563 item 3 (Q2): "ITS OWN FAILURE, "stale predictions". A prediction is never put under R2's captured line."
    One of OWN_CHECK_FAILURES: the export kept in logs/, nothing pushed or paged, no closing file, exit 1 by hand."""
    box.computed[mid] = OLD
    assert mc.run(fam, start=at(start), now=NOW) == 1
    r = runs(fam)[-1]
    assert r["failed"] == "stale predictions" and r["stale_predictions"] == [before(mid, start_et, game)]
    assert "stale" not in r and KEY not in r and "stale_starters" not in r
    assert r["export"].startswith(f"logs/{r['run_id']}.") and exports(box) == []      # R6: never in exports/
    assert box.pushes == [] and box.pages == [] and r["push"] is None and r["desk_rows"] == []
    out = capsys.readouterr().out
    assert lines_with(out, "stale predictions") == [
        f"✗ stale predictions: match {mid} ({start_et} {game}): prediction computed 2026-10-11T16:00:00Z, before the "
        f"run's start {RUN_START}",
        f"✗ closing-run {fam} FAILED (stale predictions) — nothing pushed or paged; the export stays in logs/ "
        "(never in exports/)"]
    assert "captured" not in "".join(lines_with(out, "✗ stale"))


@pytest.mark.parametrize("fam,start,mid,start_et,game", FAMS)
@pytest.mark.parametrize("v,cause,words", [
    (DROP_STAMP, "no computed time", "prediction carries no computed time"),
    (None, "no computed time", "prediction carries no computed time"),
    ("not a time", "computed time unreadable", "prediction computed time unreadable"),
])
def test_on_missing_null_and_unreadable_fail_per_family(box, on, capsys, fam, start, mid, start_et, game, v, cause,
                                                        words):
    box.computed[mid] = v
    assert mc.run(fam, start=at(start), now=NOW) == 1
    r = runs(fam)[-1]
    assert r["failed"] == "stale predictions" and r["stale_predictions"] == [entry(mid, start_et, game, cause)]
    out = capsys.readouterr().out
    assert f"✗ stale predictions: match {mid} ({start_et} {game}): {words}" in out.splitlines()
    assert "computed never" not in out


def test_on_a_pass_row_is_checked_too(box, on):
    """563 item 1: "every row R2 checks" (the summary rows, PASS included)."""
    d = {r["match_id"]: r["desk"]["call"] for r in box.docs["MLB"]["predictions"] if r.get("desk")}
    assert d[105] == "PASS"
    box.computed[105] = OLD
    assert mc.run("MLB", start=at(30), now=NOW) == 1
    r = runs("MLB")[-1]
    assert r["failed"] == "stale predictions"
    assert r["stale_predictions"] == [before(105, "2026-10-11 13:00 ET", "Passville Visitors @ Passville")]


def test_on_the_boundary_through_a_run(box, on, monkeypatch):
    """The start is the moment the run holds the lock (380.4), printed whole seconds. A stamp in its own second is
    stale; one second after is fresh. The frozen clock makes the start a whole second (16:25:00.000000)."""
    fake_clock(monkeypatch)
    box.computed[401] = "2026-10-11T16:25:00.999999"
    assert mc.run("SOCCER", start=at(35), now=NOW) == 1
    r = runs("SOCCER")[-1]
    assert r["run_start"] == RUN_START and r["failed"] == "stale predictions"
    assert r["stale_predictions"] == [before(401, "2026-10-11 13:00 ET", "Arsenal Visitors @ Arsenal",
                                             "2026-10-11T16:25:00Z")]
    box.computed[401] = "2026-10-11T16:26:01"           # one second after the next run's start (16:26:00)
    assert mc.run("SOCCER", start=at(35), now=NOW + timedelta(minutes=1)) == 0
    assert "failed" not in runs("SOCCER")[-1]


def test_on_nfl_is_untouched(box, on, monkeypatch, capsys):
    """503 item 1 Q1: NFL rows "are untouched": no check, no line, no key, whatever an NFL row carries."""
    called = []
    real = mc.stale_predictions
    monkeypatch.setattr(mc, "stale_predictions", lambda *a, **k: called.append(a) or real(*a, **k))
    for i, r in enumerate(box.docs["NFL"]["predictions"]):
        if i % 2:
            r["prediction"]["computed_at"] = "2026-10-11T10:00:00"                      # planted old
    assert mc.run("NFL", start=at(35), now=NOW) == 0
    r = runs("NFL")[-1]
    assert "failed" not in r and "stale_predictions" not in r and KEY not in r and called == []
    assert "stale predictions" not in capsys.readouterr().out
    monkeypatch.setitem(mc.STALE_PREDICTION_RULE, "on", False)
    assert mc.run("NFL", start=at(35), now=NOW + timedelta(minutes=1)) == 0
    assert KEY not in runs("NFL")[-1] and called == [] and "stale predictions" not in capsys.readouterr().out


# ============================================================================================ 563 item 5, Q4 ==

@pytest.mark.parametrize("switch", [True, False], ids=["on", "off"])
def test_prices_come_first_and_the_run_returns_before_the_prediction_check(box, monkeypatch, capsys, switch):
    """563 item 5 (Q4): "prices, then predictions, then starters, each failing on its own as today. No pass that lists
    two failures." A run R2 fails returns before the prediction check: no rows, no line and no key, on or off."""
    monkeypatch.setitem(mc.STALE_PREDICTION_RULE, "on", switch)
    box.no_fresh = {"sync-odds"}
    box.computed[101] = OLD
    assert mc.run("MLB", start=at(30), now=NOW) == 1
    r = runs("MLB")[-1]
    assert r["failed"] == "stale prices" and r["stale"] and "stale_predictions" not in r and KEY not in r
    assert {x["price"] for x in r["stale"]} == {"books"}                                # R2's entries only
    assert "stale predictions" not in capsys.readouterr().out


def test_predictions_come_before_the_starters(box, on):
    box.stale_sides = {(101, "home")}
    box.computed[101] = OLD
    assert mc.run("MLB", start=at(30), now=NOW) == 1
    r = runs("MLB")[-1]
    assert r["failed"] == "stale predictions" and "stale_starters" not in r and "stale" not in r


def test_off_the_starters_still_fail_after_the_count(box, capsys):
    """Off, the check counts and the run goes on to the starters, which fail as today."""
    box.stale_sides = {(101, "home")}
    box.computed[101] = OLD
    assert mc.run("MLB", start=at(30), now=NOW) == 1
    r = runs("MLB")[-1]
    assert r["failed"] == "stale starters" and r["stale_starters"] and "stale_predictions" not in r
    assert r[KEY] == [before(101, "2026-10-11 12:55 ET", "Underhill Visitors @ Underhill")]
    out = capsys.readouterr().out
    assert out.index(OFF_HEAD) < out.index("✗ stale starters:")


# ================================================================================= ON: the watch's notice and exit ==

def test_on_the_watch_notices_and_exits_as_for_any_own_check(box, on):
    """The notice through failure_text, "FAILED: stale predictions · attempt k/3" (attempt 3 says no further attempt
    runs), the exit the watch's (_failed_exit): NOTIFIED where a channel took it."""
    box.computed[401] = OLD
    assert mc.run("SOCCER", start=at(35), trigger="watch", now=NOW) == mc.NOTIFIED
    r = runs("SOCCER")[-1]
    assert r["failed"] == "stale predictions" and r["attempt"] == 1
    assert box.notes[-1] == f"Closing SOCCER 2026-10-11 13:00 ET: FAILED: stale predictions · attempt 1/3\n{MACHINE}"
    assert r["failure_notification"]["channel"] and call_pages(box) == [] and box.pushes == []
    for k in (2, 3):
        assert mc.run("SOCCER", start=at(35), trigger="watch", now=NOW + timedelta(minutes=k - 1)) == mc.NOTIFIED
    assert runs("SOCCER")[-1]["attempt"] == 3
    assert box.notes[-1] == ("Closing SOCCER 2026-10-11 13:00 ET: FAILED: stale predictions · attempt 3/3 · no "
                             f"further attempt will run for this kickoff\n{MACHINE}")


def test_on_the_watch_exits_1_where_no_channel_took_the_notice(box, on, monkeypatch):
    no_channel(box, monkeypatch)
    box.computed[401] = None
    assert mc.run("SOCCER", start=at(35), trigger="watch", now=NOW) == 1
    r = runs("SOCCER")[-1]
    assert r["failed"] == "stale predictions" and r[mc.NOTICE_NOT_TAKEN] is True


# ============================================================================================= success, ON ==

@pytest.mark.parametrize("fam,start,mid,start_et,game", FAMS)
def test_on_success_is_unchanged(box, on, capsys, fam, start, mid, start_et, game):
    """Every stamp fresh (the frame's: the export step's own time): the run pages, writes its closing file with each
    row as the export gave it, and its receipt carries neither the failure's key nor the off key."""
    assert mc.run(fam, start=at(start), now=NOW) == 0
    r = runs(fam)[-1]
    assert "failed" not in r and "stale_predictions" not in r and KEY not in r
    assert len(call_pages(box)) == 1 and box.pushes == ["closing"]
    (f,) = closing_files(box)
    export = json.loads((box.repo / r["export_written"]["file"]).read_text())
    by_id = {x["match_id"]: x for x in export["predictions"]}
    for row in json.loads(f.read_text())["predictions"]:
        assert row == by_id[row["match_id"]] and row["prediction"]["computed_at"] == "2026-10-11T16:25:30"
    assert "stale predictions" not in capsys.readouterr().out


# ================================================================================ OFF: it counts, changes nothing ==

def _outcome(box, r):
    files = closing_files(box)
    doc = json.loads(files[0].read_text()) if files else None
    if doc:
        for row in doc["predictions"]:
            row["prediction"].pop("computed_at", None)       # the export's own value, as it gave it (pinned below)
    return {"failed": r.get("failed"), "exit": r["exit"], "pages": [(p["title"], p["body"]) for p in box.pages],
            "notes": list(box.notes), "pushes": list(box.pushes), "exports": exports(box),
            "closing_rows": doc and doc["predictions"], "desk_rows": r["desk_rows"],
            "keys": sorted(set(r) - {KEY, "ts", "seconds", "run_id", "run_start_wall", "export", "export_written",
                                     "closing_file", "page", "backup", "steps"})}


def _off_run(box, case, scenario):
    if scenario == "starters":
        box.stale_sides = {(102, "away")}
    if case == "stale":
        box.computed.update({101: OLD, 104: DROP_STAMP, 105: "yesterday"})
    code = mc.run("MLB", start=at(30), trigger="watch", now=NOW)
    r = runs("MLB")[-1]
    if scenario == "success":
        assert code == 0 and "failed" not in r and len(call_pages(box)) == 1
        assert not [n for n in box.notes if n.startswith("Closing ")]                   # no failure notice
        (f,) = closing_files(box)
        export = json.loads((box.repo / r["export_written"]["file"]).read_text())
        by_id = {x["match_id"]: x for x in export["predictions"]}
        assert all(row == by_id[row["match_id"]] for row in json.loads(f.read_text())["predictions"])
    else:
        assert code == mc.NOTIFIED and r["failed"] == "stale starters" and closing_files(box) == []
        assert box.notes == [f"Closing MLB 2026-10-11 12:55 ET: FAILED: stale starters · attempt 1/3\n{MACHINE}"]
    assert len(r[KEY]) == (3 if case == "stale" else 0)
    return _outcome(box, r)


@pytest.mark.parametrize("scenario", ["success", "starters"])
def test_off_changes_no_outcome(box, tmp_path_factory, monkeypatch, scenario):
    """563 item 2(a): "With the switch off the check runs, fails nothing, and changes no page, no file, no exit and no
    notice." The same watch-started MLB run, once with every stamp fresh and once, in a box of its own, with three
    stale (one before the start, one missing, one unreadable): the same exit, receipt failure, pages, notices, push,
    files and Desk rows; only the off key differs. `starters`: a run that fails later, as stale starters, its notice
    unchanged. Both runs sit in this one test, so the comparison is made on any selection of tests."""
    fresh = _off_run(box, "fresh", scenario)
    stale = _off_run(make_box(tmp_path_factory.mktemp("stale"), monkeypatch), "stale", scenario)
    assert stale == fresh


def test_the_start_is_the_moment_the_run_holds_its_lock(box, monkeypatch, on):
    """563 item 1: "the start the run holds its lock at", held, never the run's end. The steps here take a minute
    each, so the run ends minutes after it held the lock; a stamp ten seconds after held is fresh, and the receipt's
    run_start is held."""
    slow_steps(box, monkeypatch, 60)
    box.computed.update({101: (NOW + timedelta(seconds=10)).replace(tzinfo=None).isoformat()})
    assert mc.run("MLB", start=at(30), trigger="watch", now=NOW) == 0
    r = runs("MLB")[-1]
    assert "failed" not in r and "stale_predictions" not in r
    assert r["run_start"] == "2026-10-11T16:25:00Z" and r["completed_at"] > r["run_start"]


def test_off_the_line_and_the_key_name_the_rows_and_their_causes(box, capsys):
    """563 item 2(a): "It prints one line and writes one key on the run's receipt: the rows it would have failed, each
    with its cause". The receipt's failed and the exit are untouched (the run pages)."""
    box.computed.update({401: OLD, 402: DROP_STAMP})
    assert mc.run("SOCCER", start=at(35), now=NOW) == 0
    r = runs("SOCCER")[-1]
    assert "failed" not in r and "stale_predictions" not in r and len(call_pages(box)) == 1
    assert r[KEY] == [before(401, "2026-10-11 13:00 ET", "Arsenal Visitors @ Arsenal"),
                      entry(402, "2026-10-11 13:02 ET", "Fulham Visitors @ Fulham", "no computed time")]
    out = capsys.readouterr().out
    assert lines_with(out, "stale predictions") == [
        OFF_HEAD + "2 row(s) would fail: match 401 (2026-10-11 13:00 ET Arsenal Visitors @ Arsenal): prediction "
        "computed 2026-10-11T16:00:00Z, before the run's start 2026-10-11T16:25:00Z; match 402 (2026-10-11 13:02 ET "
        "Fulham Visitors @ Fulham): prediction carries no computed time"]
    assert "✗ stale predictions" not in out


@pytest.mark.parametrize("fam,start,mid,start_et,game", FAMS)
def test_off_the_line_and_the_key_say_none(box, capsys, fam, start, mid, start_et, game):
    """"[...] or that there are none": an empty list on the receipt and one line saying none."""
    assert mc.run(fam, start=at(start), now=NOW) == 0
    r = runs(fam)[-1]
    assert r[KEY] == [] and "failed" not in r
    assert lines_with(capsys.readouterr().out, "stale predictions") == [OFF_HEAD + "none would fail"]


def test_off_the_line_says_unreadable(box, capsys):
    box.computed[101] = "garbage"
    assert mc.run("MLB", start=at(30), now=NOW) == 0
    assert runs("MLB")[-1][KEY] == [entry(101, "2026-10-11 12:55 ET", "Underhill Visitors @ Underhill",
                                          "computed time unreadable")]
    assert lines_with(capsys.readouterr().out, "stale predictions") == [
        OFF_HEAD + "1 row(s) would fail: match 101 (2026-10-11 12:55 ET Underhill Visitors @ Underhill): prediction "
        "computed time unreadable"]


def test_the_dry_run_names_the_check_for_the_families_it_reaches(box, capsys):
    for fam, start in (("MLB", 30), ("SOCCER", 35), ("NFL", 35)):
        assert mc.run(fam, dry_run=True, start=at(start), now=NOW) == 0
        out = capsys.readouterr().out
        assert ("predictions (503 PR 2: rule off, counted only)" in out) is (fam != "NFL"), fam
    assert box.steps == [] and not c.receipts_path().exists()
