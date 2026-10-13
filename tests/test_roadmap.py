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
    ("2026-10-14", "2026-10-13", "in 1 day"), ("2026-10-15", "2026-10-13", "in 2 days"),
    ("2026-10-20", "2026-10-13", "in 7 days"), ("2026-10-13", "2026-10-13", "today"),
    ("2026-10-12", "2026-10-13", "OVERDUE 1 day"), ("2026-10-11", "2026-10-13", "OVERDUE 2 days"),
    ("2026-10-08", "2026-10-13", "OVERDUE 5 days"),
])
def test_the_count_of_days(due, today, text):
    """5(e)'s forms "in N days", "today" or "OVERDUE N days"; addendum 61 item 5: "One day is singular: 'in 1 day',
    'OVERDUE 1 day'"."""
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


_MOVE = {"moved_on": "2026-10-20", "which": "steps[2].due", "was": "2026-10-20", "now": "2026-10-22",
         "why": "the declaration came two days late", "ruling": "addendum 60 item 1"}

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
    ("a lane id", lambda d: d["lanes"][1].__setitem__("lane", " "), "lane 2: no lane id"),
    ("a title", lambda d: _lane(d, "pd").__setitem__("title", ""), "lane 'pd': no title"),
    ("a registry id or null", lambda d: _lane(d, "pd").__setitem__("registry_id", ""),
     "lane 'pd': registry_id '' is neither null nor an id"),
    ("live_needs", lambda d: _lane(d, "pd").__setitem__("live_needs", " "), "lane 'pd': no live_needs"),
    ("text the print can write", lambda d: _lane(d, "pd").__setitem__("title", "\ud83d"), "lane 'pd': no title"),
    ("steps a list", lambda d: _lane(d, "pd").__setitem__("steps", "two"), "lane 'pd': steps is not a list"),
    ("a step an object", lambda d: _lane(d, "pd")["steps"].__setitem__(0, "x"), "lane 'pd' step 1: not an object"),
    ("a step keeps its keys", lambda d: _lane(d, "pd")["steps"][0].pop("due"), "lane 'pd' step 1: missing due"),
    ("a step's what", lambda d: _lane(d, "pd")["steps"][0].__setitem__("what", ""), "lane 'pd' step 1: no what"),
    ("a done step's receipt kept", lambda d: _lane(d, "cups")["steps"][0].__setitem__("done", {"date": "2026-10-14"}),
     "lane 'cups' step 1: done is neither null nor {date, receipt}"),
    ("a done step's receipt not blank",
     lambda d: _lane(d, "cups")["steps"][0].__setitem__("done", {"date": "2026-10-14", "receipt": " "}),
     "lane 'cups' step 1: done with no receipt"),
    ("moved a list", lambda d: _lane(d, "pd").__setitem__("moved", "none"), "lane 'pd': moved is not a list"),
    ("a moved line an object", lambda d: _lane(d, "pd")["moved"].append("x"), "lane 'pd' moved 1: not an object"),
    ("a confirming lane has a step left",
     lambda d: [st.__setitem__("done", {"date": "2026-11-12", "receipt": "r"}) for st in _lane(d, "unl")["steps"]],
     "lane 'unl': state 'confirming' and no step left to do"),
    ("a lane to declare has a step left",
     lambda d: [st.__setitem__("done", {"date": "2026-10-23", "receipt": "r"}) for st in _lane(d, "leagues")["steps"]],
     "lane 'leagues': state 'to declare' and no step left to do"),
    ("within a lane no two steps share a what (addendum 60 item 3)",
     lambda d: _lane(d, "ncaa")["steps"][3].__setitem__("what", _lane(d, "ncaa")["steps"][1]["what"]),
     "lane 'ncaa' step 4: what"),
    ("a cleared now only for earliest_live (addendum 61 item 4)",
     lambda d: _lane(d, "ncaa")["moved"].append({**_MOVE, "now": None}), "lane 'ncaa' moved 1: missing now"),
    ("was is always a real date (addendum 61 item 4)",
     lambda d: _lane(d, "ncaa")["moved"].append({**_MOVE, "which": "earliest_live", "was": None, "now": None}),
     "lane 'ncaa' moved 1: missing was"),
]

# (d): "the day it was moved, which date, what it was, what it is now, why, and the addendum and item"
SIX_PARTS = ("moved_on", "which", "was", "now", "why", "ruling")


def test_the_six_parts_are_the_ruled_six():
    assert tuple(rm.MOVED_PARTS) == SIX_PARTS


@pytest.mark.parametrize("part", SIX_PARTS)
def test_every_moved_line_has_its_six_parts_each_one(part):
    doc = _broken(lambda d: _lane(d, "ncaa")["moved"].append({k: v for k, v in _MOVE.items() if k != part}))
    assert any(e.startswith(f"lane 'ncaa' moved 1: missing {part}") for e in rm.validate(doc)), rm.validate(doc)


@pytest.mark.parametrize("part", ["moved_on", "was", "now"])
def test_each_date_of_a_moved_line_is_a_real_date(part):
    doc = _broken(lambda d: _lane(d, "ncaa")["moved"].append({**_MOVE, part: "2026-13-01"}))
    assert any(e.startswith(f"lane 'ncaa' moved 1: {part} '2026-13-01' is not a real date") for e in rm.validate(doc))


@pytest.mark.parametrize("state", ["live", "closed"])
def test_a_live_or_closed_lane_may_have_every_step_done(state):
    def edit(d):
        ln = _lane(d, "cups")
        ln["state"] = state
        for st in ln["steps"]:
            st["done"] = {"date": "2026-10-15", "receipt": "the ruling on the data"}
    assert rm.validate(_broken(edit)) == []


def test_two_steps_due_the_same_day_do_not_go_backwards():
    assert rm.validate(_broken(lambda d: _lane(d, "ncaa")["steps"][3].__setitem__("due", "2026-11-08"))) == []


def test_a_milestone_due_today_is_today_and_not_overdue(tmp_path, monkeypatch):
    monkeypatch.setattr(rm, "TAXONOMY_PATH", _write(tmp_path, {"milestones": [
        {"title": "M0", "due_on": "2026-10-13", "description": ""}]}, "t.json"))
    out = _cli("--today", "2026-10-13")
    lines = out.output.splitlines()
    assert out.exit_code == 0 and "  M0 · 2026-10-13 · today" in lines and lines[-1] == "overdue: 0"


def test_a_file_nested_past_the_parsers_depth_exits_2(tmp_path, monkeypatch):
    p = tmp_path / "r.json"
    p.write_text("[" * 200000)
    monkeypatch.setattr(rm, "ROADMAP_PATH", p)
    out = _cli("--today", "2026-10-13")
    assert out.exit_code == 2 and "cannot be read as JSON" in out.output


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


@pytest.mark.parametrize("bad", ["2026-W01-1", "2026-W42-5", "20261013xx", "2026111199", "20261016  ",
                                 "2026-10-13T00", " 2026-10-13", "２０２６-10-13"])
def test_only_a_calendar_date_written_yyyy_mm_dd_is_a_real_date(bad):
    """Codex on #488: date.fromisoformat reads the ISO week 2026-W01-1 as 2025-12-29; it is not a YYYY-MM-DD date."""
    assert rm.real_date(bad) is None
    assert rm.real_date("2026-10-13") == date(2026, 10, 13)
    doc = _broken(lambda d: _lane(d, "cups")["steps"][0].__setitem__("due", bad))
    assert any(e.startswith("lane 'cups' step 1: due") for e in rm.validate(doc))


def test_an_iso_week_today_exits_2():
    out = _cli("--today", "2026-W01-1")
    assert out.exit_code == 2 and "not a real date" in out.output


@pytest.mark.parametrize("tax, msg", [
    (["not", "an", "object"], "the taxonomy: not an object"),
    ({"milestones": "none"}, "the taxonomy: no 'milestones' list"),
    ({"milestones": ["bad"]}, "milestone 1: not an object"),
    ({"milestones": [{"due_on": "2026-10-30"}]}, "milestone 1: no title"),
    ({"milestones": [{"title": "Cutover ~Oct 8", "description": ""}]}, "milestone 'Cutover ~Oct 8': no due_on"),
    ({"milestones": [{"description": ""}]}, "milestone 1: no due_on"),
])
def test_a_taxonomy_of_the_wrong_shape_exits_2_and_names_the_entry(tax, msg, tmp_path, monkeypatch):
    """Codex on #488: a taxonomy of valid JSON in the wrong shape refuses (exit 2, naming it), never a traceback."""
    monkeypatch.setattr(rm, "TAXONOMY_PATH", _write(tmp_path, tax, "t.json"))
    out = _cli("--today", "2026-10-13")
    assert out.exit_code == 2 and msg in out.output, out.output


def test_the_ledger_guide_shows_the_moved_milestone_dates():
    """Codex on #488: docs/LEDGER.md's milestone table carries the same two dates as the taxonomy (item 6)."""
    guide = (rm.ROOT / "docs" / "LEDGER.md").read_text(encoding="utf-8")
    assert "| Cutover ~Oct 8 | due 2026-10-30" in guide
    assert "| Executable-edge ruling (2 wks of ladders) | due 2026-10-20" in guide


def test_a_milestone_date_that_is_not_real_exits_2_and_names_it(tmp_path, monkeypatch):
    monkeypatch.setattr(rm, "TAXONOMY_PATH", _write(tmp_path, {"milestones": [{"title": "Cutover ~Oct 8",
                                                                                "due_on": "2026-10-32"}]}, "t.json"))
    out = _cli("--today", "2026-10-13")
    assert out.exit_code == 2 and "milestone 'Cutover ~Oct 8': due_on '2026-10-32'" in out.output


# --- addendum 61 items 4 and 5 ---

def test_the_plural_tail_stays_plural_past_one(tmp_path, monkeypatch):
    doc = _real()
    tax = {"milestones": []}
    monkeypatch.setattr(rm, "ROADMAP_PATH", _write(tmp_path, doc))
    monkeypatch.setattr(rm, "TAXONOMY_PATH", _write(tmp_path, tax, "t.json"))
    lines, _ = rm.report(date(2026, 11, 9), path=tmp_path / "r.json", taxonomy_path=tmp_path / "t.json")
    ncaa = _lane(doc, "ncaa")
    late = rm.overdue_steps(ncaa, date(2026, 11, 9))
    assert len(late) >= 3
    assert any(ln.startswith(f"  next: {ncaa['steps'][0]['what']}") and
               ln.endswith(f"(+{len(late) - 1} more steps overdue)") for ln in lines), lines


def test_a_cleared_earliest_live_has_its_moved_line_with_now_null():
    """#492 RULED: "Clearing one is a move ... its moved line has which earliest_live, was the date, now null, and
    why. In a moved line now may be null where which is earliest_live; was is always a real date." """
    def edit(d):
        ln = _lane(d, "unl")
        ln["moved"].append({"moved_on": "2026-11-12", "which": "earliest_live", "was": ln["earliest_live"],
                            "now": None, "why": "the confirmation failed", "ruling": "addendum 70 item 1"})
        ln["earliest_live"] = None
    assert rm.validate(_broken(edit)) == []


def test_a_moved_line_must_carry_now_even_when_it_is_null():
    doc = _broken(lambda d: _lane(d, "unl")["moved"].append(
        {"moved_on": "2026-11-12", "which": "earliest_live", "was": "2026-11-12", "why": "w", "ruling": "r"}))
    assert any(e.startswith("lane 'unl' moved 1: missing now") for e in rm.validate(doc))


def test_the_real_taxonomy_writes_every_due_on_key():
    """#494 (addendum 61 item 5): every milestone of the tracked taxonomy carries the key."""
    tax = json.loads(rm.TAXONOMY_PATH.read_text(encoding="utf-8"))
    assert all("due_on" in m for m in tax["milestones"])


# --- the base check (addendum 60 item 3; addendum 61 item 4), #490 ---

def _base_head(edit):
    base = _real()
    head = copy.deepcopy(base)
    edit(head)
    return base, head


def _mv(which, was, now, **kw):
    return {"moved_on": "2026-10-20", "which": which, "was": was, "now": now, "why": "the ruling's why",
            "ruling": "addendum 62 item 1", **kw}


def test_an_unchanged_file_passes():
    base, head = _base_head(lambda d: None)
    assert rm.check_moves(base, head) == []


def test_a_due_moved_with_no_moved_line_fails_naming_the_lane_and_the_date():
    base, head = _base_head(lambda d: _lane(d, "cups")["steps"][0].__setitem__("due", "2026-10-13"))
    what = _lane(base, "cups")["steps"][0]["what"]
    old = _lane(base, "cups")["steps"][0]["due"]
    assert rm.check_moves(base, head) == [
        f"lane 'cups' step 1: due {old} -> 2026-10-13 has no moved line on the head "
        f"(which {what!r}, was {old!r}, now '2026-10-13')"]


def test_a_due_moved_with_its_moved_line_passes():
    def edit(d):
        st = _lane(d, "cups")["steps"][0]
        _lane(d, "cups")["moved"].append(_mv(st["what"], st["due"], "2026-10-13"))
        st["due"] = "2026-10-13"
    base, head = _base_head(edit)
    assert rm.validate(head) == [] and rm.check_moves(base, head) == []


@pytest.mark.parametrize("bad", ["which", "was", "now"])
def test_a_moved_line_that_does_not_match_the_move_fails(bad):
    def edit(d):
        st = _lane(d, "cups")["steps"][0]
        line = _mv(st["what"], st["due"], "2026-10-13")
        line[bad] = {"which": st["what"] + " ", "was": "2026-10-01", "now": "2026-10-12"}[bad]
        _lane(d, "cups")["moved"].append(line)
        st["due"] = "2026-10-13"
    base, head = _base_head(edit)
    errs = rm.check_moves(base, head)
    assert len(errs) == 1 and errs[0].startswith("lane 'cups' step 1: due "), errs


def test_an_earliest_live_moved_needs_its_line_and_passes_with_it():
    lane = _lane(_real(), "unl")
    base, head = _base_head(lambda d: _lane(d, "unl").__setitem__("earliest_live", "2026-11-20"))
    assert rm.check_moves(base, head) == [
        f"lane 'unl': earliest_live {lane['earliest_live']} -> 2026-11-20 has no moved line on the head "
        f"(which 'earliest_live', was {lane['earliest_live']!r}, now \"2026-11-20\")"]

    def edit(d):
        ln = _lane(d, "unl")
        ln["moved"].append(_mv("earliest_live", ln["earliest_live"], "2026-11-20"))
        ln["earliest_live"] = "2026-11-20"
    base, head = _base_head(edit)
    assert rm.validate(head) == [] and rm.check_moves(base, head) == []


def test_an_earliest_live_cleared_needs_its_line_with_now_null():
    """Addendum 61 item 4: "An earliest_live cleared needs its moved line, with now null." """
    was = _lane(_real(), "unl")["earliest_live"]
    base, head = _base_head(lambda d: _lane(d, "unl").__setitem__("earliest_live", None))
    assert rm.check_moves(base, head) == [
        f"lane 'unl': earliest_live {was} -> null (cleared) has no moved line on the head "
        f"(which 'earliest_live', was {was!r}, now null)"]

    def edit(d):
        ln = _lane(d, "unl")
        ln["moved"].append(_mv("earliest_live", ln["earliest_live"], None))
        ln["earliest_live"] = None
    base, head = _base_head(edit)
    assert rm.validate(head) == [] and rm.check_moves(base, head) == []


def test_a_first_earliest_live_set_needs_no_moved_line():
    """"Setting a first earliest_live is not a move and needs no moved line." """
    assert _lane(_real(), "leagues")["earliest_live"] is None
    base, head = _base_head(lambda d: _lane(d, "leagues").__setitem__("earliest_live", "2027-03-01"))
    assert rm.check_moves(base, head) == []


def test_a_lane_or_a_step_only_one_side_holds_needs_nothing():
    def edit(d):
        d["lanes"].append({**copy.deepcopy(_lane(d, "cups")), "lane": "new-lane"})
        d["lanes"] = [ln for ln in d["lanes"] if ln["lane"] != "pd"]
        _lane(d, "ncaa")["steps"][5]["what"] += " (renamed)"         # a step the base does not hold, word for word
        _lane(d, "ncaa")["steps"][5]["due"] = "2026-12-31"
    base, head = _base_head(edit)
    assert rm.check_moves(base, head) == []


def test_several_moves_each_named():
    def edit(d):
        _lane(d, "cups")["steps"][0]["due"] = "2026-10-13"
        _lane(d, "nhl")["earliest_live"] = "2027-02-01"
    base, head = _base_head(edit)
    errs = rm.check_moves(base, head)
    assert [e.split(":")[0] for e in errs] == ["lane 'nhl'", "lane 'cups' step 1"]     # in the file's order


def test_no_base_file_or_a_base_of_another_shape_needs_nothing():
    head = _real()
    assert rm.check_moves(None, head) == [] and rm.check_moves({"lanes": "x"}, head) == []


# --- the CI step: the working tree against a base commit, by git ---

@pytest.fixture(autouse=True)
def _plain_git(monkeypatch):
    """The test repositories never read the machine's git config (signing, hooks, templates)."""
    import os
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


def _g(root):
    return ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
            "-c", "tag.gpgsign=false", "-c", "core.hooksPath=/dev/null"]


def _repo(tmp_path, base_doc):
    import subprocess
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    g = _g(root)
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    if base_doc is not None:
        (root / "docs" / "roadmap.json").write_text(base_doc if isinstance(base_doc, str) else json.dumps(base_doc))
    (root / "README").write_text("x")
    subprocess.run(g + ["add", "-A"], check=True)
    subprocess.run(g + ["commit", "-q", "-m", "base"], check=True)
    subprocess.run(g + ["tag", "base"], check=True)
    return root


def _head(root, doc):
    (root / "docs" / "roadmap.json").write_text(json.dumps(doc))


def _check(root, ref="base"):
    out = []
    return rm.check_base(ref, root, echo=out.append), out


def _point(root, ref="base"):
    import subprocess
    sha = subprocess.run(["git", "-C", str(root), "rev-parse", ref], capture_output=True, text=True).stdout.strip()
    return f"{ref} (merge-base {sha[:7]})"


def test_the_ci_step_passes_an_unchanged_file(tmp_path):
    root = _repo(tmp_path, _real())
    rc, out = _check(root)
    assert rc == 0 and out == [f"✓ ROADMAP: docs/roadmap.json is unchanged against {_point(root)}"]


def test_the_ci_step_fails_a_move_without_its_line_and_never_rewrites_the_file(tmp_path):
    root = _repo(tmp_path, _real())
    head = _real()
    _lane(head, "cups")["steps"][0]["due"] = "2026-10-13"
    _head(root, head)
    before = (root / "docs" / "roadmap.json").read_bytes()
    rc, out = _check(root)
    assert rc == 1 and out[0].startswith("✗ ROADMAP: lane 'cups' step 1: due ") and "2026-10-13" in out[0]
    assert (root / "docs" / "roadmap.json").read_bytes() == before


def test_the_ci_step_passes_a_move_with_its_line(tmp_path):
    root = _repo(tmp_path, _real())
    head = _real()
    st = _lane(head, "cups")["steps"][0]
    _lane(head, "cups")["moved"].append(_mv(st["what"], st["due"], "2026-10-13"))
    st["due"] = "2026-10-13"
    _head(root, head)
    rc, out = _check(root)
    assert rc == 0 and out == [f"✓ ROADMAP: every date docs/roadmap.json moves against {_point(root)} has its moved line, "
                               "and every moved line the base holds is kept"]


def test_the_ci_step_on_a_base_with_no_roadmap_compares_nothing(tmp_path):
    root = _repo(tmp_path, None)
    _head(root, _real())
    rc, out = _check(root)
    assert rc == 0 and out == [f"✓ ROADMAP: docs/roadmap.json is not on the base {_point(root)}: nothing to compare"]


def test_the_ci_step_fails_a_head_that_does_not_validate(tmp_path):
    root = _repo(tmp_path, _real())
    head = _real()
    _lane(head, "ncaa")["steps"][3]["what"] = _lane(head, "ncaa")["steps"][1]["what"]
    _head(root, head)
    rc, out = _check(root)
    assert rc == 1 and out[0].startswith("✗ ROADMAP: the head's docs/roadmap.json does not validate: lane 'ncaa' step 4")


def test_the_ci_step_refuses_a_base_it_cannot_read(tmp_path):
    root = _repo(tmp_path, "{not json")
    _head(root, _real())
    rc, out = _check(root)
    assert rc == 2 and "cannot be read as JSON" in out[0]
    rc, out = _check(root, ref="no-such-ref")
    assert rc == 2 and out[0] == "✗ ROADMAP: the base 'no-such-ref' is not a commit here: nothing can be compared"


def test_ledger_py_runs_the_check_with_its_base(monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("ledger_cli", rm.ROOT / "scripts" / "ledger.py")
    ledger = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ledger)
    seen = []
    monkeypatch.setattr(rm, "check_base", lambda base, root: seen.append((base, root)) or 0)
    assert ledger.main(["check-roadmap", "--base", "origin/release-1"]) == 0     # not the fallback
    assert seen == [("origin/release-1", rm.ROOT)]
    assert ledger.main(["check-roadmap", "--base"]) == 2                          # a --base with no ref is refused
    assert ledger.main(["check-roadmap", "--base", "--pr"]) == 2
    assert seen == [("origin/release-1", rm.ROOT)]


def test_the_ci_job_that_reads_the_base_runs_the_check_beside_check_fragments():
    ci = (rm.ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    job = ci.split("\n  fragments:\n", 1)[1]
    assert "fetch-depth: 0" in job
    i, j = job.index("ledger.py check-fragments --base"), job.index("ledger.py check-roadmap --base")
    assert i < j and 'check-roadmap --base "origin/${{ github.base_ref }}"' in job


# --- the review of the first build (each fails on it) ---

def test_a_line_already_on_the_base_is_never_the_line_of_a_new_move():
    """A second failed run is written again: a clear the base already recorded does not cover this clear."""
    def prior(d):
        ln = _lane(d, "unl")
        ln["moved"].append(_mv("earliest_live", ln["earliest_live"], None, why="run 1 failed"))
    base = _broken(prior)                          # earliest_live was set again after run 1 (a set needs no line)
    assert rm.validate(base) == []
    head = copy.deepcopy(base)
    _lane(head, "unl")["earliest_live"] = None
    errs = rm.check_moves(base, head)
    assert len(errs) == 1 and errs[0].startswith("lane 'unl': earliest_live ") and "null (cleared)" in errs[0]
    _lane(head, "unl")["moved"].append(_mv("earliest_live", _lane(base, "unl")["earliest_live"], None,
                                           moved_on="2026-12-01", why="run 2 failed"))
    assert rm.validate(head) == [] and rm.check_moves(base, head) == []


def test_a_step_moved_back_needs_its_own_line_each_time():
    def prior(d):
        st = _lane(d, "cups")["steps"][0]
        _lane(d, "cups")["moved"] += [_mv(st["what"], st["due"], "2026-10-13"), _mv(st["what"], "2026-10-13", st["due"])]
    base = _broken(prior)
    head = copy.deepcopy(base)
    _lane(head, "cups")["steps"][0]["due"] = "2026-10-13"
    assert len(rm.check_moves(base, head)) == 1
    st = _lane(head, "cups")["steps"][0]
    _lane(head, "cups")["moved"].append(_mv(st["what"], _lane(base, "cups")["steps"][0]["due"], "2026-10-13",
                                            moved_on="2026-10-21"))
    assert rm.check_moves(base, head) == []


def test_a_due_the_base_never_had_needs_no_moved_line():
    """"A date set where the base had none needs no moved line." (a base step with no real due)"""
    base = _real()
    _lane(base, "cups")["steps"][0]["due"] = None
    head = _real()
    assert rm.check_moves(base, head) == []


def test_the_ci_step_reads_the_base_where_the_head_branched(tmp_path):
    """A date the base moved after the branch point is never charged to a pull request that left the file alone."""
    import subprocess
    root = _repo(tmp_path, _real())
    g = _g(root)
    subprocess.run(g + ["checkout", "-q", "-b", "pr"], check=True)
    (root / "README").write_text("the pull request's own change")
    subprocess.run(g + ["commit", "-q", "-am", "pr"], check=True)
    subprocess.run(g + ["checkout", "-q", "main"], check=True)
    moved = _real()
    st = _lane(moved, "cups")["steps"][0]
    _lane(moved, "cups")["moved"].append(_mv(st["what"], st["due"], "2026-10-13"))
    st["due"] = "2026-10-13"
    _head(root, moved)
    subprocess.run(g + ["commit", "-q", "-am", "main moves a date"], check=True)
    subprocess.run(g + ["checkout", "-q", "pr"], check=True)
    rc, out = _check(root, ref="main")
    assert rc == 0 and out[0].startswith("✓ ROADMAP: docs/roadmap.json is unchanged against main (merge-base "), out


def test_a_file_that_is_not_utf8_is_refused_by_name(tmp_path):
    root = _repo(tmp_path, _real())
    (root / "docs" / "roadmap.json").write_bytes(b'{"lanes": ["\xff"]}')
    rc, out = _check(root)
    assert rc == 1 and out[0].startswith("✗ ROADMAP: the head's docs/roadmap.json is not UTF-8")
    root2 = _repo(tmp_path / "b", '{"lanes": []}')
    import subprocess
    (root2 / "docs" / "roadmap.json").write_bytes(b'{"lanes": ["\xff"]}')
    subprocess.run(_g(root2) + ["commit", "-q", "-am", "a base that is not UTF-8"], check=True)
    subprocess.run(_g(root2) + ["tag", "-f", "base2"], check=True, capture_output=True)
    _head(root2, _real())
    rc, out = _check(root2, ref="base2")
    assert rc == 2 and "is not UTF-8" in out[0], out



def test_one_moved_line_records_one_move():
    """Codex on #503: a step whose what is the word earliest_live, moved from the same date to the same date as the
    lane's earliest_live, needs two lines; one line covers one move."""
    def edit(d):
        ln = _lane(d, "unl")
        ln["steps"][-1]["what"] = "earliest_live"
    base = _broken(edit)
    assert rm.validate(base) == []
    ln = _lane(base, "unl")
    old = ln["earliest_live"]
    ln["steps"][-1]["due"] = old                       # both dates read the same day on the base
    assert rm.validate(base) == []
    head = copy.deepcopy(base)
    hl = _lane(head, "unl")
    hl["earliest_live"] = "2026-11-20"
    hl["steps"][-1]["due"] = "2026-11-20"
    hl["moved"].append(_mv("earliest_live", old, "2026-11-20"))
    assert rm.validate(head) == []
    errs = rm.check_moves(base, head)
    assert len(errs) == 1 and errs[0].startswith("lane 'unl' step "), errs
    hl["moved"].append(_mv("earliest_live", old, "2026-11-20", why="the step's own line"))
    assert rm.check_moves(base, head) == []



# --- addendum 62 item 3 (#504): the base's moved lines stay on the head, word for word, in order ---

def _with_lines(lane_id, lines):
    def edit(d):
        _lane(d, lane_id)["moved"] += [dict(x) for x in lines]
    return _broken(edit)


def test_a_base_line_rewritten_to_cover_a_later_move_fails_and_names_the_line():
    """The base moved cups step 1 from 2026-10-14 to 2026-10-20; the head moves it on to 2026-10-27 and rewrites that
    line to cover the new move instead of appending one. The date check is satisfied; the record is not."""
    def prior(d):
        st = _lane(d, "cups")["steps"][0]
        _lane(d, "cups")["moved"].append(_mv(st["what"], st["due"], "2026-10-20"))
        st["due"] = "2026-10-20"
        _lane(d, "cups")["steps"][1]["due"] = "2026-10-21"
    base = _broken(prior)
    assert rm.validate(base) == []
    head = copy.deepcopy(base)
    st, line = _lane(head, "cups")["steps"][0], _lane(head, "cups")["moved"][0]
    line.update(was="2026-10-20", now="2026-10-27", moved_on="2026-10-21")
    st["due"] = "2026-10-27"
    _lane(head, "cups")["steps"][1]["due"] = "2026-10-28"
    errs = rm.check_moves(base, head)
    old = _lane(base, "cups")["moved"][0]
    assert any(e == (f"lane 'cups' moved 1: the base's line (moved_on {old['moved_on']!r}, which {old['which']!r}, "
                     f"was '{_lane(_real(), 'cups')['steps'][0]['due']}', now \"2026-10-20\") is changed or removed on "
                     "the head (every moved line the base holds stays, word for word)") for e in errs), errs


def test_a_base_line_removed_with_no_date_changed_fails():
    base = _with_lines("nhl", [_mv("earliest_live", "2027-01-15", "2027-01-22")])
    head = copy.deepcopy(base)
    _lane(head, "nhl")["moved"] = []
    errs = rm.check_moves(base, head)
    assert len(errs) == 1 and errs[0].startswith("lane 'nhl' moved 1: the base's line (moved_on '2026-10-20', "
                                                 "which 'earliest_live', was '2027-01-15', now \"2027-01-22\")")
    assert errs[0].endswith("is changed or removed on the head (every moved line the base holds stays, word for word)")


def test_a_line_appended_passes():
    base = _with_lines("nhl", [_mv("earliest_live", "2027-01-15", "2027-01-22")])
    head = copy.deepcopy(base)
    _lane(head, "nhl")["moved"].append(_mv("a note", "2026-10-01", "2026-10-02"))
    assert rm.check_moves(base, head) == []


def test_the_base_order_kept_and_the_heads_lines_after_it_passes():
    first, second = _mv("earliest_live", "2027-01-15", "2027-01-18"), _mv("earliest_live", "2027-01-18", "2027-01-22")
    base = _with_lines("nhl", [first, second])
    head = copy.deepcopy(base)
    st = _lane(head, "nhl")["steps"][0]
    _lane(head, "nhl")["moved"].append(_mv(st["what"], st["due"], "2026-10-31"))
    st["due"] = "2026-10-31"
    assert rm.validate(head) == [] and rm.check_moves(base, head) == []


def test_the_base_lines_out_of_order_fail_naming_each():
    first, second = _mv("earliest_live", "2027-01-15", "2027-01-18"), _mv("earliest_live", "2027-01-18", "2027-01-22")
    base = _with_lines("nhl", [first, second])
    head = copy.deepcopy(base)
    _lane(head, "nhl")["moved"].reverse()
    errs = rm.check_moves(base, head)
    assert [e.split(":")[0] for e in errs] == ["lane 'nhl' moved 1", "lane 'nhl' moved 2"]
    assert all("is on the head out of the base's order (the head only appends)" in e for e in errs)


def test_a_line_inserted_before_the_bases_lines_fails():
    base = _with_lines("nhl", [_mv("earliest_live", "2027-01-15", "2027-01-22")])
    head = copy.deepcopy(base)
    _lane(head, "nhl")["moved"].insert(0, _mv("a note", "2026-10-01", "2026-10-02"))
    errs = rm.check_moves(base, head)
    assert len(errs) == 1 and "out of the base's order" in errs[0]


def test_a_lane_only_one_side_holds_needs_nothing_from_the_kept_lines_rule():
    base = _with_lines("nhl", [_mv("earliest_live", "2027-01-15", "2027-01-22")])
    head = copy.deepcopy(base)
    head["lanes"] = [ln for ln in head["lanes"] if ln["lane"] != "nhl"]         # the lane is gone: the ruling carries it
    assert rm.check_moves(base, head) == []


def test_the_ci_step_fails_a_rewritten_base_line(tmp_path):
    base = _with_lines("nhl", [_mv("earliest_live", "2027-01-15", "2027-01-22")])
    root = _repo(tmp_path, base)
    head = copy.deepcopy(base)
    _lane(head, "nhl")["moved"][0]["why"] = "a different reason"
    _head(root, head)
    rc, out = _check(root)
    assert rc == 1 and out[0].startswith("✗ ROADMAP: lane 'nhl' moved 1: the base's line ")
    assert "addendum 62 item 3" in out[-1]


def test_the_real_roadmap_records_the_quarterback_probe_done():
    """Addendum 62 item 4: lane nfl-qb, its first step, done on 2026-10-13, receipt "PR #489 merged at 7e6e88c".
    No date moves; the print reads the lane's next step as the operator's run, due 2026-10-23."""
    lane = _lane(_real(), "nfl-qb")
    assert lane["steps"][0]["done"] == {"date": "2026-10-13", "receipt": "PR #489 merged at 7e6e88c"}
    assert [st["due"] for st in lane["steps"]] == ["2026-10-21", "2026-10-23", "2026-11-02"] and lane["moved"] == []
    nx = rm.next_step(lane)
    assert nx[0] == 2 and nx[1]["owner"] == "operator" and nx[1]["due"] == "2026-10-23"
    lines, _ = rm.report(date(2026, 10, 14))
    assert f"  next: {lane['steps'][1]['what']} · operator · due 2026-10-23 · in 9 days" in lines
