"""#901 (ARCHITECT 2026-11-09 12:50 ET, addendum 309 item 6, verbatim): "#901 (2026 not in `registry.RETIRED_TEST_SETS`):
a small src PR of its own, after #903 and #894 — the entry with 302 item 3's sentence quoted, a test that a 2026 college
candidate is refused; Refs #79." Addendum 302 item 3's sentence, verbatim: "2026 is RETIRED as a college test season;
NCAA is MARKET-ONLY; the 2027 candidate declares in the off-season."

The 2026 college test set is keyed on ncaa-elo-v2's `test_set` exactly (as the 2025 set is on v1r's). declare() and
record_run() refuse any later candidate on it, naming addendum 302 and what to declare instead; ncaa-elo-v2 stays the
last one allowed; the 2027 season is open. Every registry write goes to tmp_path; the committed ledger is only read."""
import json
from pathlib import Path

import pytest

from src.walters import registry as reg

ROOT = Path(__file__).resolve().parent.parent
TEST_SET = "NCAA FBS 2026 regular season as it accrues (CFBD both-FBS labels; training and warm-up 2024 and 2025)"
INSTEAD = ("the NCAA FBS 2027 regular season as it accrues (2024-2026 training; declared in the off-season with its "
           "spread pre-check)")
SENTENCE = ("2026 is RETIRED as a college test season; NCAA is MARKET-ONLY; the 2027 candidate declares in the "
            "off-season.")


def _decl(eid, test_set):
    return {"id": eid, "sport": "ncaa", "lane": "#79", "candidate": "c", "declaration": "d", "training_cutoff": "t",
            "test_set": test_set, "gate": "g", "confirmation_window": "w",
            "confirmation_plan": {"n_games": 100, "metric": "log_loss", "bar": 0.6931, "must_beat_reference": True,
                                  "reference": "baseline"}}


def _refusal_names_the_ruling(err):
    msg = str(err.value)
    assert "RETIRED as a test set" in msg and "ARCHITECT 2026-11-09, addendum 302" in msg, msg
    assert "ncaa-elo-v2 was its last candidate" in msg and INSTEAD in msg, msg


def test_the_2026_college_test_set_is_retired_with_v2_its_last_candidate():
    assert reg.RETIRED_TEST_SETS[TEST_SET] == ("ncaa-elo-v2", INSTEAD)
    assert reg.RETIRED_BY[TEST_SET] == "ARCHITECT 2026-11-09, addendum 302"
    v2 = reg.get("ncaa-elo-v2")                                  # the committed ledger, read only
    assert v2["test_set"] == TEST_SET                            # the key is the entry's test set, exactly
    assert v2["run"] and v2["verdict"]                           # the one run is spent and its verdict recorded
    assert reg._retired_refusal(TEST_SET, "ncaa-elo-v2") is None


def test_a_later_2026_college_candidate_is_refused_at_declare_and_nothing_is_written(tmp_path):
    path = tmp_path / "x.json"
    with pytest.raises(reg.RegistryError, match="RETIRED") as ex:
        reg.declare(_decl("ncaa-elo-v3", TEST_SET), path=str(path))
    _refusal_names_the_ruling(ex)
    assert not path.exists()


def test_a_2026_college_entry_already_in_a_ledger_is_refused_at_record_run(tmp_path):
    """An entry on the set that reached a ledger some other way (written before this PR, say) is refused its run, and
    no ids file is written."""
    path, ids = tmp_path / "x.json", tmp_path / "ids"
    entry = {**{k: v for k, v in _decl("ncaa-elo-v3", TEST_SET).items()}, "declared_at": "2026-11-10T00:00:00Z",
             "status": "declared", "run": None, "verdict": None}
    reg.save([entry], str(path))
    before = path.read_bytes()
    with pytest.raises(reg.RegistryError, match="RETIRED") as ex:
        reg.record_run("ncaa-elo-v3", [1, 2, 3], {"log_loss": 0.6}, path=str(path), ids_dir=str(ids))
    _refusal_names_the_ruling(ex)
    assert path.read_bytes() == before and not ids.exists()


def test_the_2027_season_is_open_and_the_2025_set_still_refuses(tmp_path):
    path = str(tmp_path / "x.json")
    reg.declare(_decl("ncaa-elo-v3", INSTEAD), path=path)                  # the season to declare instead
    assert [e["id"] for e in json.loads(Path(path).read_text())] == ["ncaa-elo-v3"]
    with pytest.raises(reg.RegistryError, match="addendum 24"):            # the 2025 retirement is unchanged
        reg.declare(_decl("ncaa-elo-v4", "NCAA FBS 2025 regular season (CFBD both-FBS labels; warm-up 2024)"),
                    path=path)


def test_358_the_2025_sets_refusal_names_2027_and_no_longer_2026(tmp_path):
    """ARCHITECT 2026-11-12, addendum 358 item 6(1): "the 2025 set's "declare instead" points on to 2027: a refusal
    that sends a candidate to a retired season is wrong on its face." Both college sets now send a candidate to the
    same season, in the 2026 entry's own words; no refusal names 2026."""
    t25 = "NCAA FBS 2025 regular season (CFBD both-FBS labels; warm-up 2024)"
    assert reg.RETIRED_TEST_SETS[t25] == ("ncaa-elo-v1r", INSTEAD)
    with pytest.raises(reg.RegistryError, match="addendum 24") as ex:
        reg.declare(_decl("ncaa-elo-v4", t25), path=str(tmp_path / "x.json"))
    assert "2027 regular season" in str(ex.value) and "2026 regular season" not in str(ex.value)
    for ts, (_, instead) in reg.RETIRED_TEST_SETS.items():           # no refusal points to a retired set's season
        season = instead.removeprefix("the ").split(" as it accrues")[0].split(" (")[0]   # e.g. "NCAA FBS 2027 regular season"
        assert not any(k.startswith(season) for k in reg.RETIRED_TEST_SETS), (ts, season)
    doc = (ROOT / "docs" / "REGISTRY.md").read_text(encoding="utf-8")
    row = next(ln for ln in doc.splitlines() if ln.startswith(f"| {t25} |"))
    assert INSTEAD in row and "addendum 358 item 6(1)" in row
    assert "a new set's wording is ruled at its declaration" in doc and "No fuzzy key." in doc


def test_the_sentence_is_quoted_beside_the_entry_and_in_the_doctrine():
    src = (ROOT / "src" / "walters" / "registry.py").read_text(encoding="utf-8")
    assert f'addendum 302 (ncaa-elo-v2 FAIL), item 3, verbatim: "{SENTENCE}"' in src.replace("\n# ", " ")
    doc = (ROOT / "docs" / "REGISTRY.md").read_text(encoding="utf-8").replace("\n  ", " ")
    assert SENTENCE in doc
    assert f"| {TEST_SET} | `ncaa-elo-v2`, once (ARCHITECT 2026-11-09, addendum 302) | `ncaa-elo-v2` | {INSTEAD} |" in doc
