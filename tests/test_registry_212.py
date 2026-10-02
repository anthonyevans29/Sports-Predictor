"""#212 EXPERIMENT REGISTRY + CONFIRMATION DOCTRINE: declare before any run,
one run per id, prior reads computed, PASS -> confirmation window before
production. Uses a throwaway ledger (tmp_path); the repo ledger is only read."""
import json

import pytest
from click.testing import CliRunner

from src.walters import registry as reg

DECL = {"id": "nhl-v6", "sport": "nhl", "lane": "#153", "candidate": "v1 Elo updated on xG margin",
        "declaration": "docs/specs/nhl-xg-v6.md", "training_cutoff": "xG fit 2023-24; Elo train 2024",
        "test_set": "T", "gate": "<= 0.6866", "confirmation_window": "first 4 weeks of 2026-27",
        "confirmation_plan": {"n_games": 150, "metric": "log_loss", "bar": 0.6866, "must_beat_reference": True,
                              "reference": "v1 on the same games"}}


def paths(tmp_path):
    return {"path": str(tmp_path / "x.json")}, str(tmp_path / "ids")


def test_declare_requires_every_field_including_the_window(tmp_path):
    kw, _ = paths(tmp_path)
    with pytest.raises(reg.RegistryError, match="confirmation_window"):
        reg.declare({**DECL, "confirmation_window": ""}, **kw)
    reg.declare(DECL, **kw)
    with pytest.raises(reg.RegistryError, match="already declared"):
        reg.declare(DECL, **kw)


def test_run_once_prior_reads_and_ids_sidecar(tmp_path):
    kw, ids = paths(tmp_path)
    with pytest.raises(reg.RegistryError, match="never declared"):
        reg.record_run("nhl-v6", [1, 2], {}, ids_dir=ids, **kw)
    reg.declare({**DECL, "id": "a", "test_set": "T"}, **kw)
    reg.record_run("a", [3, 1, 2, 2], {"log_loss": 0.69}, ids_dir=ids, **kw)
    reg.declare({**DECL, "id": "b", "test_set": "OTHER"}, **kw)
    reg.declare(DECL, **kw)
    reg.record_run("b", [2, 9], {}, ids_dir=ids, **kw)                       # overlaps a's ids
    e = reg.record_run("nhl-v6", [1, 2, 3], {"log_loss": 0.685}, ids_dir=ids, **kw)
    assert e["run"]["n_scored"] == 3 and len(e["run"]["ids_sha256"]) == 64
    assert {p["id"]: p["why"] for p in e["run"]["prior_reads"]} == {"a": "same test set", "b": "overlapping scored ids"}
    assert open(f"{ids}/nhl-v6.txt").read().split() == ["1", "2", "3"]
    with pytest.raises(reg.RegistryError, match="evaluated once"):
        reg.record_run("nhl-v6", [1, 2, 3], {}, ids_dir=ids, **kw)


def _passed(tmp_path):
    kw, ids = paths(tmp_path)
    reg.declare(DECL, **kw)
    reg.record_run("nhl-v6", [1, 2, 3], {}, ids_dir=ids, **kw)
    reg.record_verdict("nhl-v6", "PASS", "ARCHITECT: v6 PASS", **kw)
    return kw, ids


AFTER = "2999-01-01T00:00:00Z"
GOOD = {"first_game_at": AFTER, "log_loss": 0.6800, "reference_log_loss": 0.6900}


def test_declare_requires_an_executable_confirmation_plan(tmp_path):
    kw, _ = paths(tmp_path)
    with pytest.raises(reg.RegistryError, match="confirmation_plan must be a dict"):
        reg.declare({**DECL, "confirmation_plan": None}, **kw)
    for bad, msg in (({"n_games": 0}, "n_games"), ({"metric": "vibes"}, "metric"), ({"bar": "x"}, "bar"),
                     ({"must_beat_reference": "yes"}, "must_beat_reference"), ({"reference": ""}, "reference")):
        with pytest.raises(reg.RegistryError, match=msg):
            reg.declare({**DECL, "confirmation_plan": {**DECL["confirmation_plan"], **bad}}, **kw)


def test_immediate_confirmation_after_pass_is_refused(tmp_path):
    """The review's reproduction (#222, 2026-10-02): declare -> run -> PASS ->
    CONFIRMED in one second with no confirmation games or metrics. Refused."""
    kw, ids = _passed(tmp_path)
    with pytest.raises(reg.RegistryError, match="incomplete"):
        reg.record_confirmation("nhl-v6", [], {}, "ARCHITECT: confirmed", ids_dir=ids, **kw)
    assert reg.production_allowed("nhl-v6", **kw)[0] is False
    assert reg.get("nhl-v6", **kw)["status"] == "confirming"


def test_early_overlapping_or_metricless_confirmation_is_refused(tmp_path):
    kw, ids = _passed(tmp_path)
    fut = list(range(1000, 1150))
    with pytest.raises(reg.RegistryError, match="incomplete"):
        reg.record_confirmation("nhl-v6", fut[:149], GOOD, "r", ids_dir=ids, **kw)
    with pytest.raises(reg.RegistryError, match="AFTER the verdict"):
        reg.record_confirmation("nhl-v6", fut, {**GOOD, "first_game_at": "2000-01-01T00:00:00Z"}, "r", ids_dir=ids, **kw)
    with pytest.raises(reg.RegistryError, match="in the scored test set"):
        reg.record_confirmation("nhl-v6", fut[:149] + [2], GOOD, "r", ids_dir=ids, **kw)
    with pytest.raises(reg.RegistryError, match="lacks the plan's metric"):
        reg.record_confirmation("nhl-v6", fut, {"first_game_at": AFTER}, "r", ids_dir=ids, **kw)
    with pytest.raises(reg.RegistryError, match="reference_log_loss"):
        reg.record_confirmation("nhl-v6", fut, {"first_game_at": AFTER, "log_loss": 0.68}, "r", ids_dir=ids, **kw)
    assert reg.production_allowed("nhl-v6", **kw)[0] is False


def test_outcome_is_computed_from_the_plan_not_stated(tmp_path):
    kw, ids = _passed(tmp_path)
    fut = list(range(1000, 1150))
    e = reg.record_confirmation("nhl-v6", fut, {**GOOD, "reference_log_loss": 0.6800}, "r", ids_dir=ids, **kw)
    assert e["confirmation"]["outcome"] == "NOT_CONFIRMED" and e["status"] == "closed"     # tie with v1 fails
    assert reg.production_allowed("nhl-v6", **kw) == (False, "no PASS verdict") or \
        reg.production_allowed("nhl-v6", **kw)[0] is False


def test_pass_then_a_complete_confirmation_allows_production(tmp_path):
    kw, ids = _passed(tmp_path)
    ok, why = reg.production_allowed("nhl-v6", **kw)
    assert not ok and "confirmation window open (first 4 weeks of 2026-27)" in why
    e = reg.record_confirmation("nhl-v6", list(range(1000, 1150)), GOOD, "ARCHITECT: confirmed", ids_dir=ids, **kw)
    assert e["confirmation"]["n_scored"] == 150 and len(e["confirmation"]["ids_sha256"]) == 64
    assert open(f"{ids}/nhl-v6.confirm.txt").read().split()[0] == "1000"
    assert reg.production_allowed("nhl-v6", **kw) == (True, "confirmation CONFIRMED")


def test_repo_ledger_seeds_are_unchanged_verdicts_and_nhl_test_set_has_five_reads():
    entries = [e for e in reg.load() if (e.get("run") or {}).get("note", "").startswith("pre-registry")]
    by = {e["id"]: e for e in entries}
    assert len(entries) == 9
    assert [by[f"nhl-v{i}"]["run"]["result"]["log_loss"] for i in range(1, 6)] == [0.6909, 0.6921, 0.6952, 0.6907, 0.6912]
    assert all(e["verdict"]["verdict"] in ("FAIL", "REJECT") for e in entries)
    assert all(e["run"]["ids_file"] is None for e in entries)                        # ids never reconstructed
    assert len(reg.prior_reads(by["nhl-v1"]["test_set"], None, before_id="nhl-v6")) == 5   # the five seeds
    assert len(reg.prior_reads(by["nhl-v1"]["test_set"], None)) == 8                       # + v6, v7, v8: RETIRED


def test_cli_lists_the_ledger():
    import cli
    out = CliRunner().invoke(cli.cli, ["registry"]).output
    assert "EXPERIMENT REGISTRY · " in out and "nhl-v5" in out


def test_frozen_cohort_is_exact_once_and_binds_the_read(tmp_path):
    """Review on #248 (2026-10-02): the cohort is the first n ELIGIBLE fixture
    ids, frozen once; the read must score exactly that set — a pending label
    leaves it incomplete, never admits a replacement."""
    kw, ids = _passed(tmp_path)
    plan_n = DECL["confirmation_plan"]["n_games"]
    cohort = list(range(1000, 1000 + plan_n))
    with pytest.raises(reg.RegistryError, match="exactly 150 distinct"):
        reg.freeze_confirmation_cohort("nhl-v6", cohort[:-1], {}, ids_dir=ids, **kw)
    with pytest.raises(reg.RegistryError, match="exactly 150 distinct"):
        reg.freeze_confirmation_cohort("nhl-v6", cohort[:-1] + [1000], {}, ids_dir=ids, **kw)
    with pytest.raises(reg.RegistryError, match="test set"):
        reg.freeze_confirmation_cohort("nhl-v6", [1] + cohort[1:], {}, ids_dir=ids, **kw)
    e = reg.freeze_confirmation_cohort("nhl-v6", cohort, {"rule": "r"}, ids_dir=ids, **kw)
    assert e["confirmation_cohort"]["n"] == plan_n and reg.frozen_cohort(e, ids) == cohort
    with pytest.raises(reg.RegistryError, match="never changes"):
        reg.freeze_confirmation_cohort("nhl-v6", cohort, {}, ids_dir=ids, **kw)
    # game 151 replacing a pending cohort fixture: refused, the entry stays confirming
    swapped = cohort[:-1] + [9999]
    with pytest.raises(reg.RegistryError, match="exactly the frozen cohort"):
        reg.record_confirmation("nhl-v6", swapped, GOOD, "ARCHITECT: confirmed", ids_dir=ids, **kw)
    assert reg.get("nhl-v6", **kw)["status"] == "confirming"
    e = reg.record_confirmation("nhl-v6", cohort, GOOD, "ARCHITECT: confirmed", ids_dir=ids, **kw)
    assert e["confirmation"]["outcome"] == "CONFIRMED"


def test_a_tampered_cohort_file_refuses(tmp_path):
    kw, ids = _passed(tmp_path)
    cohort = list(range(1000, 1150))
    e = reg.freeze_confirmation_cohort("nhl-v6", cohort, {}, ids_dir=ids, **kw)
    with open(f"{ids}/nhl-v6.cohort.txt", "w") as f:
        f.write("\n".join(str(i) for i in cohort[:-1] + [9999]) + "\n")
    with pytest.raises(reg.RegistryError, match="does not match"):
        reg.frozen_cohort(e, ids)


def test_cancelled_or_abandoned_cohort_fixtures_are_substituted_with_reason(tmp_path):
    """ARCHITECT 2026-10-02 (2): CANCELLED/ABANDONED games in the frozen cohort
    are RELEASED and replaced, recorded as a substitution with reason; a
    postponed or unplayed game is never swapped."""
    kw, ids = _passed(tmp_path)
    cohort = list(range(1000, 1150))
    reg.freeze_confirmation_cohort("nhl-v6", cohort, {}, ids_dir=ids, **kw)
    ev = {"status": "cancelled", "status_raw": "ABD"}
    for bad, msg in ((("1000", 2000, "postponed", ev), "postponed or unplayed game stays"),
                     ((1000, 2000, "cancelled", {}), "evidence"),
                     ((5, 2000, "cancelled", ev), "not in the effective cohort"),
                     ((1000, 1001, "cancelled", ev), "already in the cohort"),
                     ((1000, 2, "cancelled", ev), "test set")):
        with pytest.raises(reg.RegistryError, match=msg):
            reg.substitute_cohort_fixture("nhl-v6", *bad, ids_dir=ids, **kw)
    e = reg.substitute_cohort_fixture("nhl-v6", 1000, 2000, "abandoned", ev, ids_dir=ids, **kw)
    eff = reg.frozen_cohort(e, ids)
    assert 1000 not in eff and 2000 in eff and len(eff) == 150
    assert e["confirmation_cohort"]["substitutions"][0]["reason"] == "abandoned"
    assert e["confirmation_cohort"]["ids_sha256"] == reg._ids_sha(cohort)          # the frozen file never changes
    with pytest.raises(reg.RegistryError, match="released from it"):           # a released id never returns
        reg.substitute_cohort_fixture("nhl-v6", 2000, 1000, "cancelled", ev, ids_dir=ids, **kw)
    with pytest.raises(reg.RegistryError, match="exactly the frozen cohort"):  # the pre-substitution set no longer reads
        reg.record_confirmation("nhl-v6", cohort, GOOD, "ARCHITECT: confirmed", ids_dir=ids, **kw)
    assert reg.record_confirmation("nhl-v6", eff, GOOD, "ARCHITECT: confirmed", ids_dir=ids,
                                   **kw)["confirmation"]["outcome"] == "CONFIRMED"
