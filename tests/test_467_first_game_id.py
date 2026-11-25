"""ARCHITECT 2026-11-23, addendum 467 item 1(a) (447's PR 3), verbatim in part: "registry.record_confirmation, for an
entry that holds an opening, refuses a first game AT the opening's kickoff whose id is not above the opening's match id.
A test for the tie on each side of the id." And registry.confirmation_refusal, the same checks read before a
reservation (record_confirmation's refusals before the metric, extracted as a pure refactor: tests/test_registry_212.py
and tests/test_447_leagues_policy.py pass unchanged but for the one tie case 467 amends and the held-opening fixtures
540 item 1 Q5 amends).

ARCHITECT 2026-11-25, addendum 540 item 1 Q5, ruled IN, each ONLY for an entry that holds an opening (every other entry
keeps today's rule, and a test says so for each): (a) "A missing ids file REFUSES the record. A file that is not there
is not an empty set (law 4)"; (b) "n_games EQUALS the plan's 60. '60 more' is a number, not a floor"; (c)
"first_game_id is one of the confirmation's ids". The held-opening fixtures here therefore carry a window-run ids file
(RUN_IDS) and score SCORED (60 ids holding 4243, the tie's id above the opening's, and 1, an id below it).

On throwaway ledgers under tmp_path; the real docs/registry/experiments.json is never written."""
from __future__ import annotations

import json
import os

import pytest

from src.walters import registry as reg

OPENING = {"kickoff": "2026-12-06T15:00:00Z", "match_id": 4242}
PLAN = {"n_games": 60, "metric": "log_loss", "bar": None, "must_beat_reference": True,
        "reference": "the close (the grader's close, on the same games)"}
PASS = {"verdict": "PASS", "ruling": "r", "at": "2026-12-07T12:00:00Z"}
RUN_IDS = (9001, 9002)                               # the window run's scored ids: none of them a confirmation game
SCORED = [1] + list(range(4243, 4302))               # 60 confirmation ids: 4243 (above the opening's 4242) and 1
assert len(SCORED) == 60 == len(set(SCORED))


def _file(tmp_path, opening=OPENING, run_ids=RUN_IDS, **kw):
    p = tmp_path / "x.json"
    run = {"result": ({"confirmation_opens_after": opening} if opening is not False else {}),
           "ids_file": "docs/registry/ids/x-v1.txt" if run_ids is not None else None}
    e = {"id": "x-v1", "status": "confirming", "confirmation_plan": dict(PLAN), "verdict": dict(PASS), "run": run}
    e.update(kw)
    p.write_text(json.dumps([e]))
    ids = tmp_path / "ids"
    if run_ids is not None:
        ids.mkdir(exist_ok=True)
        (ids / "x-v1.txt").write_text("\n".join(str(i) for i in run_ids) + "\n")
    return str(p), str(ids)


def _res(first="2026-12-06T15:00:00Z", **kw):
    return {"first_game_at": first, "log_loss": 0.98, "reference_log_loss": 0.99, **kw}


def _state(p, ids):
    files = sorted(os.listdir(ids)) if os.path.isdir(ids) else []
    return open(p).read(), {f: open(os.path.join(ids, f)).read() for f in files}


def test_467_at_the_tie_an_id_above_the_openings_match_is_confirmed(tmp_path):
    p, ids = _file(tmp_path)
    e = reg.record_confirmation("x-v1", SCORED, _res(first_game_id=4243), "r", p, ids)
    assert e["confirmation"]["outcome"] == "CONFIRMED" and e["status"] == "production"
    assert e["confirmation"]["result"]["first_game_id"] == 4243


@pytest.mark.parametrize("fid", [4242, 4241, 1, None, True, False, "4243", 4243.0, "missing"])
def test_467_at_the_tie_an_id_not_above_or_not_an_integer_refuses_and_writes_nothing(tmp_path, fid):
    p, ids = _file(tmp_path)
    before = _state(p, ids)
    res = _res() if fid == "missing" else _res(first_game_id=fid)
    with pytest.raises(reg.RegistryError, match=r"AT the opening's kickoff .* is not above the opening's match 4242 "
                                                r"\(addendum 467 item 1\(a\)\)"):
        reg.record_confirmation("x-v1", SCORED, res, "r", p, ids)
    assert _state(p, ids) == before and not os.path.exists(os.path.join(ids, "x-v1.confirm.txt"))
    assert reg.confirmation_refusal("x-v1", SCORED, res["first_game_at"], res.get("first_game_id"),
                                    path=p, ids_dir=ids).startswith("x-v1: the first game kicks off AT")


def test_467_a_later_kickoff_compares_no_id(tmp_path):
    p, ids = _file(tmp_path)
    e = reg.record_confirmation("x-v1", SCORED, _res("2026-12-06T15:00:01Z", first_game_id=1), "r", p,
                                ids)
    assert e["confirmation"]["outcome"] == "CONFIRMED"
    (tmp_path / "b").mkdir()
    p, ids = _file(tmp_path / "b")
    with pytest.raises(reg.RegistryError, match=r"first_game_id None is not one of the confirmation's ids"):
        reg.record_confirmation("x-v1", SCORED, _res("2026-12-08T00:00:00Z"), "r", p, ids)   # no id: 540 Q5(c)


def test_467_an_entry_without_the_opening_ignores_first_game_id(tmp_path):
    for fid in (1, None, True, "x"):
        d = tmp_path / str(fid)
        d.mkdir()
        p, ids = _file(d, opening=False)
        res = _res("2026-12-08T00:00:00Z", first_game_id=fid)
        e = reg.record_confirmation("x-v1", SCORED, res, "r", p, ids)
        assert e["confirmation"]["outcome"] == "CONFIRMED"
    p, ids = _file(tmp_path, opening=False)                  # today's rule stands: after verdict.at, whatever the id
    with pytest.raises(reg.RegistryError, match="must all start AFTER the verdict"):
        reg.record_confirmation("x-v1", SCORED, _res("2026-12-06T15:00:00Z", first_game_id=99999), "r", p,
                                ids)


# ------------------------------------------------------ confirmation_refusal: record_confirmation's own text --

CASES = {
    "not confirming": ({"status": "run"}, {}, None),
    "no plan": ({"confirmation_plan": None}, {}, None),
    "a plan check_plan refuses": ({"confirmation_plan": {**PLAN, "reference": ""}}, {}, None),
    "too few": ({}, {"ids": list(range(1, 60))}, None),
    "a frozen cohort that differs": ({"confirmation_cohort": {"n": 2, "ids_sha256": "0" * 64,
                                                              "ids_file": "docs/registry/ids/x-v1.cohort.txt"}}, {}, None),
    "no pass with the opening": ({"verdict": {"verdict": "REJECT", "at": "2026-12-07T12:00:00Z"}}, {}, None),
    "an unreadable opening": ({"run": {"result": {"confirmation_opens_after": {"kickoff": "soon", "match_id": 1}},
                                       "ids_file": None}}, {}, None),
    "earlier than the opening": ({}, {"first": "2026-12-06T14:59:59Z"}, None),
    "the tie at an id not above": ({}, {"fid": 4242}, None),
    "no opening, before the verdict": ({"run": {"result": {}, "ids_file": None}}, {"first": "2026-12-06T15:00:00Z"},
                                       None),
    "a game of the scored set": ({}, {"fid": 4243}, [1, 4242]),
    # ARCHITECT 2026-11-25, addendum 540 item 1 Q5 (an entry holding an opening only): (a), (b), (c)
    "540 Q5(a): the run's ids file missing": ({}, {}, None),
    "540 Q5(b): more than the plan's 60": ({}, {"ids": SCORED + [4400]}, RUN_IDS),
    "540 Q5(c): first_game_id not among the ids": ({}, {"fid": 4400}, RUN_IDS),
}


@pytest.mark.parametrize("case", sorted(CASES))
def test_confirmation_refusal_is_record_confirmations_text_for_every_refusal_and_writes_nothing(tmp_path, case):
    entry_kw, read_kw, run_ids = CASES[case]
    p, ids = _file(tmp_path, run_ids=run_ids, **entry_kw)
    scored = read_kw.get("ids", SCORED)
    first, fid = read_kw.get("first", OPENING["kickoff"]), read_kw.get("fid", 4243)
    before = _state(p, ids)
    why = reg.confirmation_refusal("x-v1", scored, first, fid, path=p, ids_dir=ids)
    assert why and _state(p, ids) == before
    with pytest.raises(reg.RegistryError) as ex:
        reg.record_confirmation("x-v1", scored, _res(first, first_game_id=fid), "r", p, ids)
    assert str(ex.value) == why and _state(p, ids) == before


def test_confirmation_refusal_is_none_where_record_confirmation_records(tmp_path):
    p, ids = _file(tmp_path)
    assert reg.confirmation_refusal("x-v1", SCORED, OPENING["kickoff"], 4243, path=p, ids_dir=ids) is None
    assert not os.path.exists(os.path.join(ids, "x-v1.confirm.txt"))          # it reads, it never writes
    assert reg.record_confirmation("x-v1", SCORED, _res(first_game_id=4243), "r", p, ids)["confirmation"]


# ------------------------------------------- ARCHITECT 2026-11-25, addendum 540 item 1 Q5: the three guards, both sides --

def test_540_q5a_an_entry_holding_an_opening_refuses_a_missing_run_ids_file_and_writes_nothing(tmp_path):
    for d, kw in (("no-file", {"run_ids": None}), ("named-not-there", {})):
        (tmp_path / d).mkdir()
        p, ids = _file(tmp_path / d, **kw)
        if kw == {}:
            os.remove(os.path.join(ids, "x-v1.txt"))               # named in the run, not on disk
        before = _state(p, ids)
        with pytest.raises(reg.RegistryError, match=r"ids file .* is missing: a file that is not there is not an "
                                                    r"empty set.*540 item 1 Q5\(a\)"):
            reg.record_confirmation("x-v1", SCORED, _res(first_game_id=4243), "r", p, ids)
        assert _state(p, ids) == before
        assert "540 item 1 Q5(a)" in reg.confirmation_refusal("x-v1", SCORED, OPENING["kickoff"], 4243, path=p,
                                                              ids_dir=ids)


def test_540_q5a_an_entry_without_the_opening_keeps_todays_rule_on_a_missing_ids_file(tmp_path):
    p, ids = _file(tmp_path, opening=False, run_ids=None)
    e = reg.record_confirmation("x-v1", SCORED, _res("2026-12-08T00:00:00Z"), "r", p, ids)
    assert e["confirmation"]["outcome"] == "CONFIRMED"           # today's rule: no file reads as no overlap


@pytest.mark.parametrize("n", [61, 75, 120])
def test_540_q5b_an_entry_holding_an_opening_refuses_a_count_above_the_plans_60(tmp_path, n):
    p, ids = _file(tmp_path)
    scored = SCORED + list(range(5000, 5000 + n - 60))
    before = _state(p, ids)
    with pytest.raises(reg.RegistryError, match=rf"scored {n} games, not the plan's 60: the number is exact, not a "
                                                r"floor \(addendum 540 item 1 Q5\(b\)\)"):
        reg.record_confirmation("x-v1", scored, _res(first_game_id=4243), "r", p, ids)
    assert _state(p, ids) == before
    with pytest.raises(reg.RegistryError, match="< the plan's 60"):          # below: the floor refuses, as before
        reg.record_confirmation("x-v1", SCORED[:59], _res(first_game_id=4243), "r", p, ids)


def test_540_q5b_an_entry_without_the_opening_keeps_todays_floor(tmp_path):
    p, ids = _file(tmp_path, opening=False)
    e = reg.record_confirmation("x-v1", SCORED + [5000, 5001], _res("2026-12-08T00:00:00Z"), "r", p, ids)
    assert e["confirmation"]["outcome"] == "CONFIRMED" and e["confirmation"]["n_scored"] == 62


@pytest.mark.parametrize("fid", [4400, 4242, None, True, "4243", 4243.0, "missing"])
def test_540_q5c_an_entry_holding_an_opening_refuses_a_first_game_id_not_among_the_ids(tmp_path, fid):
    p, ids = _file(tmp_path)
    later = "2026-12-06T16:00:00Z"                                 # a later kickoff: 467's tie check does not fire
    res = _res(later) if fid == "missing" else _res(later, first_game_id=fid)
    before = _state(p, ids)
    with pytest.raises(reg.RegistryError, match=r"is not one of the confirmation's ids \(addendum 540 item 1 "
                                                r"Q5\(c\)\)"):
        reg.record_confirmation("x-v1", SCORED, res, "r", p, ids)
    assert _state(p, ids) == before
    e = reg.record_confirmation("x-v1", SCORED, _res(later, first_game_id=4250), "r", p, ids)   # one of them: records
    assert e["confirmation"]["outcome"] == "CONFIRMED"


def test_540_q5c_an_entry_without_the_opening_keeps_todays_rule_on_first_game_id(tmp_path):
    for fid in (4400, None, "x"):
        d = tmp_path / str(fid)
        d.mkdir()
        p, ids = _file(d, opening=False)
        res = _res("2026-12-08T00:00:00Z", first_game_id=fid)
        assert reg.record_confirmation("x-v1", SCORED, res, "r", p, ids)["confirmation"]["outcome"] == "CONFIRMED"


@pytest.mark.parametrize("scored", ["dup", "bool"])
def test_540_q5b_the_count_is_on_the_list_as_given_never_after_a_set(tmp_path, scored):
    """Codex on #1153: 61 entries naming the 60 ids, one twice, are not 60 scored games, and a metric over them would
    be recorded against 60 ids; an entry that is a bool is not an id. Refused for an entry holding an opening; the
    ledger and ids are unchanged."""
    p, ids = _file(tmp_path)
    lst = SCORED + [SCORED[0]] if scored == "dup" else SCORED + [True]           # a 61st entry that is a bool
    before = _state(p, ids)
    with pytest.raises(reg.RegistryError, match=r"each game is scored once \(addendum 540 item 1 Q5\(b\)\)"):
        reg.record_confirmation("x-v1", lst, _res(first_game_id=4243), "r", p, ids)
    assert _state(p, ids) == before
    e = reg.record_confirmation("x-v1", SCORED, _res(first_game_id=4243), "r", p, ids)          # 60 once each: records
    assert e["confirmation"]["n_scored"] == 60


def test_540_q5b_an_entry_without_the_opening_keeps_todays_set_on_a_repeated_id(tmp_path):
    p, ids = _file(tmp_path, opening=False)
    e = reg.record_confirmation("x-v1", SCORED + [SCORED[0]], _res("2026-12-08T00:00:00Z"), "r", p, ids)
    assert e["confirmation"]["outcome"] == "CONFIRMED" and e["confirmation"]["n_scored"] == 60
