"""SOCCER-V23'S RULED STAGE PLACEMENTS (ARCHITECT 2026-11-23 09:26 ET, addendum 456 items 4 and 5; GATE-CLASS;
lane soccer-v23, #656). Synthetic rows only; nothing of soccer-v23 runs on real data.

Item 5(e): each ruled pair; a ruled form in another competition refuses; an unruled form refuses; Scotland's first
season in scope on a synthetic store; item 5(b)'s pin (soccer_expansion.placement's answers for every label of item 4
are what they were). Also: the table is exactly items 4(a)-(d) (item 5(a)); it is not a model constant (item 5(c));
the preflight and run-record marks "by ruling 456" with counts (item 5(d))."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.walters import soccer_expansion as sx
from src.walters import soccer_v23 as v

ROOT = Path(__file__).resolve().parent.parent
SLOTS = {"scope": "LEAGUE_REGULAR", "first_season": "score_under_prior", "visibility": "day",
         "cut": "2026-10-30T15:00:00Z", "availability_on": False}

RULED = {("AUT", "Championship Group"): "playoff", ("BEL", "Championship Group"): "playoff",
         ("CZE", "Championship Group"): "playoff", ("GRE", "Championship Group"): "playoff",
         ("SCO", "Championship Group"): "playoff", ("SUI", "Championship Group"): "playoff",
         ("BEL", "Conference League Group"): "playoff", ("GRE", "Conference League Group"): "playoff",
         ("SCO", "1st Phase"): "regular", ("SCO", "2nd Phase"): "playoff"}


def test_456_5a_the_table_is_exactly_items_4a_to_4d_each_with_the_addendums_number():
    assert {k: pl for k, (pl, _) in v.RULED_PLACEMENTS.items()} == RULED
    items = {k: why for k, (_, why) in v.RULED_PLACEMENTS.items()}
    assert {items[(c, "Championship Group")] for c in ("AUT", "BEL", "CZE", "GRE", "SCO", "SUI")} == {
        "addendum 456 item 4(a)"}
    assert items[("BEL", "Conference League Group")] == items[("GRE", "Conference League Group")] == (
        "addendum 456 item 4(b)")
    assert items[("SCO", "1st Phase")] == "addendum 456 item 4(c)" and items[("SCO", "2nd Phase")] == (
        "addendum 456 item 4(d)")


@pytest.mark.parametrize("code, form", sorted(RULED))
def test_456_5e_each_ruled_pair_places_by_ruling(code, form):
    for n in (1, 10, 38):
        assert v.placement_with_source(code, f"{form} - {n}") == (RULED[(code, form)], True)


@pytest.mark.parametrize("code, label", [
    ("PL", "Championship Group - 1"), ("NED", "Championship Group - 2"), ("SCO", "Conference League Group - 1"),
    ("AUT", "Conference League Group - 1"), ("SUI", "1st Phase - 1"), ("AUT", "2nd Phase - 3"),
    ("PL", "1st Phase - 1"), (None, "1st Phase - 1")])
def test_456_4e_a_ruled_form_in_a_competition_not_named_beside_it_stays_unplaced(code, label):
    assert v.placement_with_source(code, label) == (None, False)


@pytest.mark.parametrize("label", ["3rd Phase - 1", "Championship Group", "1st Phase", "1st Phase - x",
                                   "Championship Group - 1 ", "Apertura - 3", "", None])
def test_456_4e_an_unruled_form_stays_unplaced(label):
    assert v.placement_with_source("SCO", label) == (None, False)


def test_456_5b_soccer_expansion_placement_answers_every_item_4_label_as_it_did():
    """soccer_expansion.py is not edited: its answers for every label of item 4 stand (the frozen experiments')."""
    was = {"Championship Group - 1": None, "Championship Group - 10": None, "Conference League Group - 1": None,
           "1st Phase - 1": None, "1st Phase - 33": None, "2nd Phase - 1": None, "Relegation Group - 1": "playoff",
           "Championship Round - 1": "playoff", "Relegation Round - 1": "playoff",
           "Conference League Play-off Group - 1": "playoff", "Regular Season - 1": "regular"}
    assert {k: sx.placement(k) for k in was} == was
    assert not any(n in (ROOT / "src" / "walters" / "soccer_expansion.py").read_text()
                   for n in ("RULED_PLACEMENTS", "addendum 456"))


def test_456_the_codes_answer_wins_where_it_gives_one():
    """The table is read only where soccer_expansion.placement returns nothing: its own answer is never overridden."""
    assert v.placement_with_source("SCO", "Relegation Group - 2") == ("playoff", False)
    assert v.placement_with_source("SCO", "Regular Season - 4") == ("regular", False)
    assert v.placement_with_source("BEL", "Conference League Play-off Group - 1") == ("playoff", False)


def _sco_rows():
    """Two Scottish seasons as 2024/25 and 2025/26 store them (33 '1st Phase' rounds, then the split), and 2026/27 as
    'Regular Season'; goals both ways in every season (263 item 14 is not in play)."""
    rows, i = [], 1
    t0 = {"2024/25": datetime(2024, 8, 3), "2025/26": datetime(2025, 8, 2), "2026/27": datetime(2026, 8, 1)}
    for season, labels in (("2024/25", [f"1st Phase - {n}" for n in range(1, 4)] + ["2nd Phase - 1"]),
                           ("2025/26", [f"1st Phase - {n}" for n in range(1, 4)]
                            + ["Championship Group - 34", "Relegation Group - 34"]),
                           ("2026/27", [f"Regular Season - {n}" for n in range(1, 3)])):
        for k, lab in enumerate(labels):
            rows.append(v.Row(i, "SCO", season, t0[season] + timedelta(days=7 * k), 1 + k % 2, 2 - k % 2,
                              1 + k % 2, k % 2, lab))
            i += 1
    return rows


def test_456_5e_scotlands_first_season_in_scope_is_2024_25_on_a_synthetic_store(monkeypatch):
    rows = _sco_rows()
    assert v.stage_refusals(rows, SLOTS) == []
    assert v.first_seasons(rows, "LEAGUE_REGULAR") == {"SCO": "2024/25"}
    kept = v.in_scope(rows, "LEAGUE_REGULAR")
    assert [r.stage for r in kept] == ["1st Phase - 1", "1st Phase - 2", "1st Phase - 3", "1st Phase - 1",
                                       "1st Phase - 2", "1st Phase - 3", "Regular Season - 1", "Regular Season - 2"]
    sc = v.scored_rows(rows, SLOTS)
    assert all(r.stage.startswith(("1st Phase", "Regular Season")) for r in sc) and len(sc) == 8   # all before the cut
    cen = v.stage_census(rows)
    assert cen[("SCO", "2024/25")]["ruled"] == {("1st Phase - 1", "regular"): 1, ("1st Phase - 2", "regular"): 1,
                                                 ("1st Phase - 3", "regular"): 1, ("2nd Phase - 1", "playoff"): 1}
    assert cen[("SCO", "2025/26")]["ruled"][("Championship Group - 34", "playoff")] == 1
    assert ("Relegation Group - 34", "playoff") not in cen[("SCO", "2025/26")]["ruled"]    # the code's own answer
    # without the ruling (the table empty) the labels refuse and no regular Scottish game counts before 2026/27
    monkeypatch.setattr(v, "RULED_PLACEMENTS", {})
    assert [x.split(":")[0] for x in v.stage_refusals(rows, SLOTS)] == ["SCO 2024/25", "SCO 2025/26"]
    with pytest.raises(v.GateRefused, match="cannot be placed"):
        v.in_scope(rows, "LEAGUE_REGULAR")
    assert v.first_seasons(rows, "LEAGUE_REGULAR") == {"SCO": "2026/27"}


def test_456_5d_the_preflight_and_the_record_mark_by_ruling_456_with_counts():
    rows = _sco_rows()
    census = v.ruled_placement_census(rows)
    assert census == [["SCO", "2024/25", "1st Phase - 1", "regular", 1], ["SCO", "2024/25", "1st Phase - 2", "regular", 1],
                      ["SCO", "2024/25", "1st Phase - 3", "regular", 1], ["SCO", "2024/25", "2nd Phase - 1", "playoff", 1],
                      ["SCO", "2025/26", "1st Phase - 1", "regular", 1], ["SCO", "2025/26", "1st Phase - 2", "regular", 1],
                      ["SCO", "2025/26", "1st Phase - 3", "regular", 1],
                      ["SCO", "2025/26", "Championship Group - 34", "playoff", 1]]
    L = v.ruled_placement_lines(rows)
    assert L[0] == ("  stage labels placed by ruling 456 (ARCHITECT 2026-11-23, addendum 456 items 4(a)-(d); the code "
                    "places the rest itself): 8 row(s)")
    assert L[1] == ("    stages SCO 2024/25, by ruling 456: '1st Phase - 1' regular 1; '1st Phase - 2' regular 1; "
                    "'1st Phase - 3' regular 1; '2nd Phase - 1' play-off 1")
    assert L[2].startswith("    stages SCO 2025/26, by ruling 456: ") and "'Championship Group - 34' play-off 1" in L[2]
    assert v.ruled_census_lines([])[0].endswith("0 row(s) (none in this store)")


def test_456_5c_the_table_is_not_a_model_constant_and_the_entry_is_untouched():
    entries = json.loads((ROOT / "docs" / "registry" / "experiments.json").read_text())
    e = next(x for x in entries if x["id"] == v.EID)
    assert "RULED_PLACEMENTS" not in v.code_constants() and v.constants_state(e) is None and v.bar_state(e) is None
    assert hashlib.sha256(v.BAR_TEXT.encode()).hexdigest() == (
        "d4778a276359f11cb89fe7b0694458ba7e01da6fa2a7971a320f5e90eb2371c4")
    rows = sorted([c, f, pl, why] for (c, f), (pl, why) in v.RULED_PLACEMENTS.items())
    assert v.ruled_placements_sha256() == hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


from tests.test_soccer_v23_harness import _fp, declared  # noqa: E402,F401  (a fixture: the declared synthetic store)


def _ruled_copy(declared) -> str:
    """A copy of the declared store on which the first PL 2025/26 row (a prior of soccer-backtest's walk, never one of
    its recorded rows) carries the label 'Championship Group - 1'. A throwaway file; never data/."""
    import shutil
    import sqlite3
    dst = declared["tmp"] / "ruled" / "copy.db"
    dst.parent.mkdir()
    shutil.copyfile(declared["copy"], dst)
    con = sqlite3.connect(str(dst))
    try:
        (mid,) = con.execute("SELECT m.id FROM matches m JOIN competitions c ON c.id = m.competition_id WHERE c.code = "
                             "'PL' AND m.season = '2025/26' ORDER BY m.utc_date, m.id LIMIT 1").fetchone()
        con.execute("UPDATE matches SET stage = 'Championship Group - 1' WHERE id = ?", (mid,))
        con.commit()
    finally:
        con.close()
    return str(dst)


def test_456_5d_the_marks_through_the_real_preflight_run_and_record(declared, monkeypatch):
    """Item 5(d) end to end, on the harness's synthetic store: the table (widened for this test only with a PL row, to
    exercise the wiring; the ruled table itself is pinned above) places the label; the preflight prints it "by ruling
    456" with its count and still gives a fingerprint; the run returns the census; the record carries it with the
    table's sha256, as JSON."""
    from src.walters import registry as reg
    monkeypatch.setattr(v, "RULED_PLACEMENTS", {**v.RULED_PLACEMENTS,
                                                ("PL", "Championship Group"): ("playoff", "tests only")})
    copy = _ruled_copy(declared)
    L = v.preflight_lines(reg.get(v.EID, reg.LEDGER), copy)
    assert ("  stage labels placed by ruling 456 (ARCHITECT 2026-11-23, addendum 456 items 4(a)-(d); the code places "
            "the rest itself): 1 row(s)") in L
    assert "    stages PL 2025/26, by ruling 456: 'Championship Group - 1' play-off 1" in L
    fp = _fp(L)
    r = v.run("ARCHITECT test word", fp, db=copy)
    want = [["PL", "2025/26", "Championship Group - 1", "playoff", 1]]
    assert r["ruled_placements"] == want
    assert "    stages PL 2025/26, by ruling 456: 'Championship Group - 1' play-off 1" in v.run_lines(r)
    e = v.record(r, "ARCHITECT test word")
    res = e["run"]["result"]
    assert res["placed_by_ruling_456"] == want and res["ruled_placements_sha256"] == v.ruled_placements_sha256()
    json.dumps(res, allow_nan=False)
