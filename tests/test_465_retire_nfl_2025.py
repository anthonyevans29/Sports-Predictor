"""ARCHITECT 2026-11-23 13:55 ET, addendum 465 item 4(b), verbatim: "NFL 2025 IS RETIRED AS A TEST SEASON: read by v1's
gate run and its re-runs, the four R-track variants and v2's run; 215 item 2 said it is read once. DEV 2: it is keyed
into registry.RETIRED_TEST_SETS under BOTH stored test_set strings, v1's and v2's, as #901 did for college 2026, with a
test that a declaration naming either refuses. One small PR, gate-class, a reviewable head by Friday 2026-12-11. 2024
is not retired: it was never a test set, and it stays training data."

Both strings are the committed entries' test_set exactly (the key is exact, 358 item 6(2): no fuzzy key). declare() and
record_run() refuse any later candidate naming either, naming addendum 465 item 4(b); nfl-elo-v1 and nfl-elo-v2 stay the
last candidates on their own strings. The refusal names no season to declare instead: 465 item 4(a) rules the
candidate's test season by its own gate-class addendum. Every registry write goes to tmp_path; the committed ledger is
only read."""
import json
from pathlib import Path

import pytest

from src.walters import registry as reg

ROOT = Path(__file__).resolve().parent.parent
V1 = "NFL 2025 regular season + postseason (nfl-backtest's scored window; warm-up 2024, preseason excluded)"
V2 = ("NFL 2025 regular season + postseason (285 games on the corrected stream, #775; warm-up 2024 complete, 285; "
      "preseason excluded)")
SETS = {"nfl-elo-v1": V1, "nfl-elo-v2": V2}
RULING = "ARCHITECT 2026-11-23, addendum 465 item 4(b)"


def _decl(eid, test_set):
    return {"id": eid, "sport": "nfl", "lane": "#780", "candidate": "c", "declaration": "d", "training_cutoff": "t",
            "test_set": test_set, "gate": "g", "confirmation_window": "w",
            "confirmation_plan": {"n_games": 60, "metric": "log_loss", "bar": 0.6931, "must_beat_reference": True,
                                  "reference": "baseline"}}


@pytest.mark.parametrize("last, test_set", sorted(SETS.items()))
def test_nfl_2025_is_retired_under_each_stored_string_with_its_entry_the_last_candidate(last, test_set):
    assert reg.RETIRED_TEST_SETS[test_set] == (last, reg.NFL_INSTEAD) and reg.RETIRED_BY[test_set] == RULING
    e = reg.get(last)                                              # the committed ledger, read only
    assert e["test_set"] == test_set                               # the key is the entry's test set, exactly
    assert reg._retired_refusal(test_set, last) is None            # its own last candidate is not refused


@pytest.mark.parametrize("test_set", [V1, V2])
def test_a_declaration_naming_either_string_refuses_and_nothing_is_written(tmp_path, test_set):
    path = tmp_path / "x.json"
    with pytest.raises(reg.RegistryError, match="RETIRED as a test set") as ex:
        reg.declare(_decl("nfl-elo-v3", test_set), path=str(path))
    msg = str(ex.value)
    assert RULING in msg and reg.NFL_INSTEAD in msg and "was its last candidate" in msg
    assert not path.exists()


@pytest.mark.parametrize("test_set", [V1, V2])
def test_an_entry_on_either_string_already_in_a_ledger_is_refused_its_run(tmp_path, test_set):
    path, ids = tmp_path / "x.json", tmp_path / "ids"
    entry = {**_decl("nfl-elo-v3", test_set), "declared_at": "2026-11-24T00:00:00Z", "status": "declared", "run": None,
             "verdict": None}
    reg.save([entry], str(path))
    before = path.read_bytes()
    with pytest.raises(reg.RegistryError, match="RETIRED") as ex:
        reg.record_run("nfl-elo-v3", [1, 2, 3], {"log_loss": 0.6}, path=str(path), ids_dir=str(ids))
    assert RULING in str(ex.value)
    assert path.read_bytes() == before and not ids.exists()


def test_the_refusal_sends_a_candidate_to_no_season_and_2024_is_not_retired(tmp_path):
    """465 item 4(a): the candidate's test season is ruled by its own addendum, so the refusal names none (358 item
    6(1): a refusal that sends a candidate to a retired season is wrong on its face). 2024 "was never a test set"."""
    assert "never 2025" in reg.NFL_INSTEAD and "465 item 4(a)" in reg.NFL_INSTEAD
    assert not any(k.startswith("NFL 2024") for k in reg.RETIRED_TEST_SETS)
    path = str(tmp_path / "x.json")
    reg.declare(_decl("nfl-elo-v3", "NFL 2027 regular season as it accrues (tests only)"), path=path)
    assert [e["id"] for e in json.loads(Path(path).read_text())] == ["nfl-elo-v3"]
