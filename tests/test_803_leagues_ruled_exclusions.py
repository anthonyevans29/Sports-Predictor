"""#803 (ARCHITECT 2026-11-02 18:05 ET, addendum 223 item 2(b); built by ARCHITECT 2026-11-21 12:17 ET, addendum 442
item 2(a)): the per-entry list of RULED exclusions the leagues reader honours. "The refusal is cleared only by a RULED
exclusion: [...] a per-entry list of ruled exclusions (match id, kickoff, the cause as the host's receipt established it,
the ruling's stamp) that the reader honours — excluded by ruled cause, no slot, on its own named line."

The Issue's three tests, on synthetic stores (223 item 2(b)'s own world: tests/test_leagues_declaration_220.py's SA
window of 62 members, a page whose binding carried the entry, games with no stored row after it):
  - a listed game is excluded and does not refuse (the read, and the score at the 60th);
  - an unlisted one refuses;
  - a malformed item refuses (no ruling, no cause, an extra key, a kickoff that is not an instant or not the game's, a
    game not in the window, a game listed twice, a field that is not a list).
And the list starts empty: an empty list (or none) leaves the reader's print and its window byte for byte as before.
Throwaway SQLite files and tmp registries only."""
from __future__ import annotations

import json
from datetime import timedelta

import pytest

from src.walters import leagues_window as lw
from tests.test_leagues_declaration_220 import _drop_rows, _page, _window_62
from tests.test_leagues_window import AT_TEXT as W_AT_TEXT
from tests.test_leagues_window import NOW as W_NOW
from tests.test_leagues_window import _export as w_export
from tests.test_leagues_window import decl, ledger  # noqa: F401  (ledger: a fixture)
from tests.test_record_vs_close import iso_db  # noqa: F401  (a fixture)

RULING = "ARCHITECT 2026-12-05 09:00 ET, addendum 999 item 1 (a test's stamp, never a ruling)"
CAUSE = "the host's receipt: the shadow export did not run on the host that day (a test's cause)"


def _item(game, **kw):
    mid, ko = game
    it = {"match_id": mid, "kickoff": f"{ko:%Y-%m-%dT%H:%M:%SZ}", "cause": CAUSE, "ruling": RULING}
    it.update(kw)
    return it


def _no_rows_after_the_page(ledger, ruled=None):
    """62 SA members; games 9 and 12 have no stored row and kick off after the page whose binding carried the entry
    (223 item 2(b)'s refusal, unless the list clears them)."""
    got = _window_62(ledger)
    w_export("SA")
    _drop_rows({got[9][0], got[12][0]})
    _page("p_carrying", (got[3][1] + timedelta(hours=1)).isoformat(),
          {"SA": {"state": "exporting", "candidate": "leagues-sa-v1", "declared_at": W_AT_TEXT}})
    if ruled is not None:
        ledger(decl("SA", ruled_exclusions=ruled))
    return got


@pytest.mark.usefixtures("iso_db")
def test_a_listed_game_is_excluded_by_ruled_cause_takes_no_slot_and_does_not_refuse(ledger):
    got = _no_rows_after_the_page(ledger)
    ledger(decl("SA", ruled_exclusions=[_item(got[9]), _item(got[12])]))
    w = lw.read(("SA",), now=W_NOW)["SA"]
    assert "refused" not in w and w["state"] == "ready" and w["n"] == 60
    assert got[9][0] not in w["members"] and got[12][0] not in w["members"]           # no slot
    assert w["excluded"][lw.RULED] == 2 and [i["match_id"] for i in w[lw.RULED]] == [got[9][0], got[12][0]]
    assert w[lw.NO_ROW] == [] and w["ruled_not_applied"] == []
    out = lw.lines({"SA": w}, W_NOW)
    i = out.index("  - SA · excluded by ruled cause (no slot): 2 (ARCHITECT 2026-11-02, addendum 223 item 2(b); the "
                  "entry's ruled_exclusions, #803)")
    assert out[i + 1] == f"    - match {got[9][0]} · kickoff {got[9][1]:%Y-%m-%dT%H:%M:%SZ} · cause: {CAUSE} · ruling: {RULING}"
    assert "excluded by ruled cause (each named with its cause and ruling below) 2 (listed below)" in "\n".join(out)
    res = lw.score(w, now=W_NOW)                                     # the score honours the list as the read does
    assert res["match_ids"] == w["members"] and [i["match_id"] for i in res["audit"][lw.RULED]] == [got[9][0],
                                                                                                    got[12][0]]
    assert any("excluded by ruled cause (no slot): 2" in x for x in lw.audit_lines("SA", res["audit"]))


@pytest.mark.usefixtures("iso_db")
def test_an_unlisted_game_still_refuses(ledger):
    got = _no_rows_after_the_page(ledger)
    ledger(decl("SA", ruled_exclusions=[_item(got[9])]))             # game 12 not listed
    r = lw.read(("SA",), now=W_NOW)["SA"]
    assert set(r) == {"code", "declared", "id", "refused"}
    assert f"match {got[12][0]} kickoff" in r["refused"] and f"match {got[9][0]} " not in r["refused"]
    assert "1 window game(s)" in r["refused"] and "addendum 223 item 2(b): it REFUSES" in r["refused"]


MALFORMED = {
    "no ruling": (lambda g: [_item(g, ruling="")], "no ruling"),
    "a ruling that is not text": (lambda g: [_item(g, ruling=None)], "no ruling"),
    "no cause": (lambda g: [_item(g, cause="  ")], "no cause"),
    "a missing key": (lambda g: [{k: v for k, v in _item(g).items() if k != "ruling"}], "is not exactly"),
    "an extra key": (lambda g: [_item(g, note="x")], "is not exactly"),
    "a kickoff that is not an instant": (lambda g: [_item(g, kickoff="2026-11-20")], "is not a UTC instant"),
    "a kickoff that is not the game's": (lambda g: [_item(g, kickoff="2027-01-01T15:00:00Z")], "another kickoff"),
    "a game not in the window": (lambda g: [_item(g, match_id=987654)], "not a game of the 2026/27 window"),
    "a match id that is not one": (lambda g: [_item(g, match_id="12")], "is not a match id"),
    "a game listed twice": (lambda g: [_item(g), _item(g)], "is listed twice"),
    "a field that is not a list": (lambda g: _item(g), "not a list of ruled exclusions"),
}


@pytest.mark.usefixtures("iso_db")
@pytest.mark.parametrize("case", list(MALFORMED))
def test_a_malformed_item_refuses_the_read_and_the_score(ledger, case):
    got = _no_rows_after_the_page(ledger)
    good = [_item(got[9]), _item(got[12])]
    ledger(decl("SA", ruled_exclusions=good))
    w = lw.read(("SA",), now=W_NOW)["SA"]
    assert w["state"] == "ready"                                     # well formed: read, then the list is spoiled
    make, why = MALFORMED[case]
    ledger(decl("SA", ruled_exclusions=make(got[9])))
    r = lw.read(("SA",), now=W_NOW)["SA"]
    assert set(r) == {"code", "declared", "id", "refused"} and why in r["refused"], r
    with pytest.raises(lw.WindowRefused, match=why):
        lw.score(w, now=W_NOW)


@pytest.mark.usefixtures("iso_db")
def test_a_listed_game_an_earlier_step_excludes_is_named_never_overriding_that_cause(ledger):
    """The list clears 223 item 2(b)'s refusal; it never takes a game another cause already excludes or holds."""
    got = _window_62(ledger)
    w_export("SA")
    from src.db.database import session_scope
    from src.db.schema import Match, MatchStatus
    with session_scope() as s:
        s.get(Match, got[5][0]).status = MatchStatus.CANCELLED
    ledger(decl("SA", ruled_exclusions=[_item(got[5])]))
    w = lw.read(("SA",), now=W_NOW)["SA"]
    assert w["excluded"]["cancelled"] == 1 and not w["excluded"].get(lw.RULED)
    assert [i["match_id"] for i in w["ruled_not_applied"]] == [got[5][0]]
    assert "  - SA · listed, not applied 1 (an earlier step excludes the game or holds it pending; the list never " \
           "overrides another cause):" in lw.lines({"SA": w}, W_NOW)


@pytest.mark.usefixtures("iso_db")
def test_the_list_starts_empty_and_an_empty_list_changes_nothing(ledger):
    """The registry's five entries carry ruled_exclusions [] (#803: "Nothing on the list exists"); an empty list and no
    field read byte for byte alike, the print included."""
    from pathlib import Path
    entries = json.loads((Path(__file__).resolve().parent.parent / "docs" / "registry" / "experiments.json").read_text())
    real = {e["id"]: e for e in entries}
    for eid in lw.DECLARATION_IDS.values():
        assert real[eid][lw.RULED_FIELD] == []
    got = _window_62(ledger)
    w_export("SA")
    a = lw.read(("SA",), now=W_NOW)["SA"]
    ledger(decl("SA", ruled_exclusions=[]))
    b = lw.read(("SA",), now=W_NOW)["SA"]
    assert lw.lines({"SA": a}, W_NOW) == lw.lines({"SA": b}, W_NOW) and a["members"] == b["members"]
    assert not any("ruled" in x for x in lw.lines({"SA": b}, W_NOW)) and got
    sa, sb = lw.score(a, now=W_NOW), lw.score(b, now=W_NOW)
    assert lw.RULED not in sb["audit"] and sa == sb
