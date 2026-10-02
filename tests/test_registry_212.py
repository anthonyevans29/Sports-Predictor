"""#212 EXPERIMENT REGISTRY + CONFIRMATION DOCTRINE: declare before any run,
one run per id, prior reads computed, PASS -> confirmation window before
production. Uses a throwaway ledger (tmp_path); the repo ledger is only read."""
import json

import pytest
from click.testing import CliRunner

from src.walters import registry as reg

DECL = {"id": "nhl-v6", "sport": "nhl", "lane": "#153", "candidate": "v1 Elo updated on xG margin",
        "declaration": "docs/specs/nhl-xg-v6.md", "training_cutoff": "xG fit 2023-24; Elo train 2024",
        "test_set": "T", "gate": "<= 0.6866", "confirmation_window": "first 4 weeks of 2026-27"}


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


def test_pass_needs_a_confirmed_window_before_production(tmp_path):
    kw, ids = paths(tmp_path)
    reg.declare(DECL, **kw)
    with pytest.raises(reg.RegistryError, match="needs a run"):
        reg.record_verdict("nhl-v6", "PASS", "x", **kw)
    reg.record_run("nhl-v6", [1], {}, ids_dir=ids, **kw)
    reg.record_verdict("nhl-v6", "PASS", "ARCHITECT: v6 PASS", **kw)
    ok, why = reg.production_allowed("nhl-v6", **kw)
    assert not ok and "confirmation window open (first 4 weeks of 2026-27)" in why
    reg.record_confirmation("nhl-v6", "CONFIRMED", "ARCHITECT: confirmed", **kw)
    assert reg.production_allowed("nhl-v6", **kw) == (True, "confirmation CONFIRMED")


def test_repo_ledger_seeds_are_unchanged_verdicts_and_nhl_test_set_has_five_reads():
    entries = reg.load()
    by = {e["id"]: e for e in entries}
    assert [by[f"nhl-v{i}"]["run"]["result"]["log_loss"] for i in range(1, 6)] == [0.6909, 0.6921, 0.6952, 0.6907, 0.6912]
    assert all(e["verdict"]["verdict"] in ("FAIL", "REJECT") for e in entries)
    assert all(e["run"]["note"].startswith("pre-registry") for e in entries)       # ids never reconstructed
    assert len(reg.prior_reads(by["nhl-v1"]["test_set"], None)) == 5


def test_cli_lists_the_ledger():
    import cli
    out = CliRunner().invoke(cli.cli, ["registry"]).output
    assert "EXPERIMENT REGISTRY · 9 entries" in out and "nhl-v5" in out
