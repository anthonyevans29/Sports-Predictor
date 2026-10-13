"""THE ROADMAP (ARCHITECT 2026-10-13, addendum 59 item 5, #486): docs/roadmap.json and `python cli.py roadmap`.

(e), verbatim in part: "Validation, in code and as a test on the real file, so a bad file cannot merge: lane ids
unique; issue an integer; state and owner from their sets; every date a real date; a lane that is not live or closed
has a step not done; due dates never go backwards down a lane's steps; earliest_live, where set, is not before the last
step's due date; every moved line has its six parts." Read-only, no database, no network; exit 0 whatever is overdue,
2 (naming the entry) on a file that does not validate.
"""
from __future__ import annotations

import copy
import json
import socket
from datetime import date

import pytest
from click.testing import CliRunner

from src import roadmap as rm


def _real():
    return json.loads(rm.ROADMAP_PATH.read_text(encoding="utf-8"))


def _cli(*args):
    from cli import cli
    return CliRunner().invoke(cli, ["roadmap", *args])


# --- the real files: a bad one cannot merge ---

def test_the_real_roadmap_file_validates():
    assert rm.validate(_real()) == []
    assert rm.load()["lanes"]


def test_the_real_taxonomy_milestone_dates_validate():
    assert rm.validate_milestones(json.loads(rm.TAXONOMY_PATH.read_text(encoding="utf-8"))) == []


def test_the_file_lives_outside_data_and_is_tracked_json():
    assert rm.ROADMAP_PATH.relative_to(rm.ROOT).parts[0] == "docs"
    assert "data" not in rm.ROADMAP_PATH.relative_to(rm.ROOT).parts


def test_item_6_the_two_ledger_dates_are_moved():
    """Addendum 59 item 6: "Cutover ~Oct 8" 2026-10-08 -> 2026-10-30; "Executable-edge ruling (2 wks of ladders)"
    2026-10-13 -> 2026-10-20. The titles stay."""
    ms = {m["title"]: m["due_on"] for m in json.loads(rm.TAXONOMY_PATH.read_text(encoding="utf-8"))["milestones"]}
    assert ms["Cutover ~Oct 8"] == "2026-10-30"
    assert ms["Executable-edge ruling (2 wks of ladders)"] == "2026-10-20"


# --- the print ---

def test_the_print_on_the_ruled_day_lists_each_lane_in_order_with_its_next_step():
    out = _cli("--today", "2026-10-13")
    assert out.exit_code == 0, out.output
    lines = out.output.splitlines()
    titles = [ln["title"] for ln in _real()["lanes"]]
    heads = [ln for ln in lines if " · #" in ln and not ln.startswith(" ")]
    assert [h.split(" · #")[0] for h in heads] == titles
    first = _real()["lanes"][0]
    i = lines.index(next(h for h in heads if h.startswith(first["title"])))
    assert lines[i] == (f"{first['title']} · #{first['issue']} · {first['state']} · earliest live "
                        f"{first['earliest_live'] or 'not set'} · vs close: {first['vs_close']}")
    nxt = first["steps"][0]
    assert lines[i + 1] == f"  next: {nxt['what']} · {nxt['owner']} · due {nxt['due']} · in 29 days"
    assert "  Cutover ~Oct 8 · 2026-10-30 · in 17 days" in lines
    assert "  Executable-edge ruling (2 wks of ladders) · 2026-10-20 · in 7 days" in lines
    assert lines[-1] == "overdue: 0"


def test_overdue_steps_and_milestones_are_counted_and_the_exit_stays_0(tmp_path, monkeypatch):
    doc = _real()
    tax = {"milestones": [{"title": "M1", "due_on": "2026-10-15", "description": ""},
                          {"title": "M2", "due_on": None, "description": ""}]}
    (tmp_path / "r.json").write_text(json.dumps(doc))
    (tmp_path / "t.json").write_text(json.dumps(tax))
    monkeypatch.setattr(rm, "ROADMAP_PATH", tmp_path / "r.json")
    monkeypatch.setattr(rm, "TAXONOMY_PATH", tmp_path / "t.json")
    out = _cli("--today", "2026-10-17")
    assert out.exit_code == 0, out.output
    lines = out.output.splitlines()
    by = {ln["lane"]: ln for ln in doc["lanes"]}
    # ncaa: its first step (due 2026-10-16) is a day late; cups: both steps (10-14, 10-15) are late
    assert f"  next: {by['ncaa']['steps'][0]['what']} · architect · due 2026-10-16 · OVERDUE 1 day" in lines
    assert any(ln.startswith(f"  next: {by['cups']['steps'][0]['what']}") and
               ln.endswith("OVERDUE 3 days (+1 more step overdue)") for ln in lines)
    assert "  M1 · 2026-10-15 · OVERDUE 2 days" in lines and not any("M2" in ln for ln in lines)
    assert lines[-1] == "overdue: 4"                    # ncaa 1 + cups 2 + milestone M1


def test_a_done_step_is_not_next_and_not_overdue():
    doc = _real()
    lane = next(ln for ln in doc["lanes"] if ln["lane"] == "cups")
    lane["steps"][0]["done"] = {"date": "2026-10-14", "receipt": "the probe's console, pasted on #78"}
    assert rm.validate(doc) == []
    assert rm.next_step(lane)[0] == 2
    assert rm.overdue_steps(lane, date(2026, 10, 15)) == []
    assert rm.overdue_steps(lane, date(2026, 10, 16)) == [2]


@pytest.mark.parametrize("due, today, text", [
    ("2026-10-14", "2026-10-13", "in 1 day"), ("2026-10-20", "2026-10-13", "in 7 days"),
    ("2026-10-13", "2026-10-13", "today"),
    ("2026-10-12", "2026-10-13", "OVERDUE 1 day"), ("2026-10-08", "2026-10-13", "OVERDUE 5 days"),
])
def test_the_count_of_days(due, today, text):
    assert rm.when(date.fromisoformat(due), date.fromisoformat(today)) == text


def test_a_lane_with_no_step_left_prints_none(tmp_path, monkeypatch):
    doc = _real()
    doc["lanes"][0]["state"] = "live"
    for st in doc["lanes"][0]["steps"]:
        st["done"] = {"date": "2026-11-12", "receipt": "the confirmation record"}
    lines, n = rm.report(date(2026, 11, 13), path=_write(tmp_path, doc))
    assert lines[2] == "  next: none (live)"


def test_today_defaults_to_the_machines_local_date():
    out = _cli()
    assert out.exit_code == 0, out.output
    assert f"today {date.today().isoformat()}" in out.output.splitlines()[0]


def test_a_today_that_is_not_a_real_date_exits_2():
    out = _cli("--today", "2026-02-30")
    assert out.exit_code == 2 and "not a real date" in out.output


def test_the_command_opens_no_database_and_no_network(monkeypatch):
    import cli as climod
    from src.db import database

    def no(*a, **k):
        raise AssertionError("the roadmap touched the database or the network")
    monkeypatch.setattr(climod, "session_scope", no)
    monkeypatch.setattr(database, "session_scope", no)
    monkeypatch.setattr(database._engine, "connect", no)
    monkeypatch.setattr(socket, "create_connection", no)
    monkeypatch.setattr(socket.socket, "connect", no)
    out = _cli("--today", "2026-10-13")
    assert out.exit_code == 0, out.output


# --- the validation: each rule refuses, names the entry, and the command exits 2 ---

def _write(tmp_path, doc, name="r.json"):
    p = tmp_path / name
    p.write_text(json.dumps(doc))
    return p


def _broken(edit):
    doc = copy.deepcopy(_real())
    edit(doc)
    return doc


def _lane(doc, lane_id):
    return next(ln for ln in doc["lanes"] if ln["lane"] == lane_id)


BROKEN = [
    ("lane ids unique", lambda d: _lane(d, "pd").__setitem__("lane", "unl"), "lane 'unl': lane id not unique"),
    ("issue an integer", lambda d: _lane(d, "ncaa").__setitem__("issue", "79"), "lane 'ncaa': issue '79' is not an integer"),
    ("issue not a bool", lambda d: _lane(d, "ncaa").__setitem__("issue", True), "lane 'ncaa': issue True is not an integer"),
    ("state from its set", lambda d: _lane(d, "nhl").__setitem__("state", "paused"), "lane 'nhl': state 'paused' is not one of"),
    ("owner from its set", lambda d: _lane(d, "nhl")["steps"][1].__setitem__("owner", "schedule"),
     "lane 'nhl' step 2: owner 'schedule' is not one of"),
    ("a real due date", lambda d: _lane(d, "ncaa")["steps"][2].__setitem__("due", "2026-11-31"),
     "lane 'ncaa' step 3: due '2026-11-31' is not a real date"),
    ("a due date written YYYY-MM-DD", lambda d: _lane(d, "ncaa")["steps"][2].__setitem__("due", "2026-11-8"),
     "lane 'ncaa' step 3: due '2026-11-8' is not a real date"),
    ("a real done date", lambda d: _lane(d, "cups")["steps"][0].__setitem__("done", {"date": "yesterday", "receipt": "x"}),
     "lane 'cups' step 1: done date 'yesterday' is not a real date"),
    ("a done step carries its receipt", lambda d: _lane(d, "cups")["steps"][0].__setitem__("done", "2026-10-14"),
     "lane 'cups' step 1: done is neither null nor {date, receipt}"),
    ("a real earliest_live", lambda d: _lane(d, "unl").__setitem__("earliest_live", "2026-11-31"),
     "lane 'unl': earliest_live '2026-11-31' is not a real date"),
    ("a lane not live or closed has a step not done",
     lambda d: [st.__setitem__("done", {"date": "2026-10-14", "receipt": "r"}) for st in _lane(d, "cups")["steps"]],
     "lane 'cups': state 'blocked' and no step left to do"),
    ("due dates never go backwards", lambda d: _lane(d, "ncaa")["steps"][3].__setitem__("due", "2026-11-07"),
     "lane 'ncaa' step 4: due 2026-11-07 goes backwards from step 3's 2026-11-08"),
    ("earliest_live not before the last step's due", lambda d: _lane(d, "nhl").__setitem__("earliest_live", "2027-01-20"),
     "lane 'nhl': earliest_live 2027-01-20 is before the last step's due date 2027-01-21"),
    ("every moved line has its six parts",
     lambda d: _lane(d, "ncaa")["moved"].append({"moved_on": "2026-10-20", "which": "steps[2].due", "was": "2026-10-20",
                                                 "now": "2026-10-22", "why": "late"}),
     "lane 'ncaa' moved 1: missing ruling"),
    ("a moved line's dates are real",
     lambda d: _lane(d, "ncaa")["moved"].append({"moved_on": "2026-10-20", "which": "steps[2].due", "was": "2026-10-20",
                                                 "now": "soon", "why": "late", "ruling": "addendum 60 item 1"}),
     "lane 'ncaa' moved 1: now 'soon' is not a real date"),
    ("a lane keeps its keys", lambda d: _lane(d, "pd").pop("vs_close"), "lane 'pd': missing vs_close"),
]


@pytest.mark.parametrize("rule, edit, msg", BROKEN, ids=[b[0] for b in BROKEN])
def test_each_rule_refuses_and_names_the_entry(rule, edit, msg, tmp_path, monkeypatch):
    doc = _broken(edit)
    errs = rm.validate(doc)
    assert any(e.startswith(msg) for e in errs), errs
    monkeypatch.setattr(rm, "ROADMAP_PATH", _write(tmp_path, doc))
    out = _cli("--today", "2026-10-13")
    assert out.exit_code == 2, out.output
    assert out.output.startswith("ROADMAP REFUSED (does not validate):") and msg in out.output


def test_a_moved_line_with_its_six_parts_validates():
    doc = _broken(lambda d: _lane(d, "ncaa")["moved"].append(
        {"moved_on": "2026-10-20", "which": "steps[2].due", "was": "2026-10-20", "now": "2026-10-22",
         "why": "the declaration came two days late", "ruling": "addendum 60 item 1"}))
    assert rm.validate(doc) == []


def test_a_file_that_is_not_json_exits_2(tmp_path, monkeypatch):
    p = tmp_path / "r.json"
    p.write_text("{not json")
    monkeypatch.setattr(rm, "ROADMAP_PATH", p)
    out = _cli("--today", "2026-10-13")
    assert out.exit_code == 2 and "cannot be read as JSON" in out.output


def test_a_milestone_date_that_is_not_real_exits_2_and_names_it(tmp_path, monkeypatch):
    monkeypatch.setattr(rm, "TAXONOMY_PATH", _write(tmp_path, {"milestones": [{"title": "Cutover ~Oct 8",
                                                                                "due_on": "2026-10-32"}]}, "t.json"))
    out = _cli("--today", "2026-10-13")
    assert out.exit_code == 2 and "milestone 'Cutover ~Oct 8': due_on '2026-10-32'" in out.output
