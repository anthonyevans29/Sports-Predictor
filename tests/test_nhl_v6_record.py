"""The nhl-v6 run record (from the laptop, 2026-10-02) and its FAIL verdict
(ARCHITECT, verbatim): the ids sidecar matches the recorded sha256 and count,
the verdict is FAIL, the entry is closed, production is refused; with v7's
record (also FAIL) the NHL 2025 test set carries 7 reads."""
import hashlib
import os

import pytest

from src.walters import registry as reg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_v6_record_is_complete_and_failed():
    e = reg.get("nhl-v6")
    assert e["status"] == "closed" and e["verdict"]["verdict"] == "FAIL"
    assert e["verdict"]["ruling"].startswith("ARCHITECT 2026-10-02: v6 VERDICT STANDS — FAIL 0.6886 vs 0.6866")
    run = e["run"]
    ids = [int(x) for x in open(os.path.join(ROOT, run["ids_file"])).read().split()]
    assert len(ids) == run["n_scored"] == 1394 == len(set(ids))
    assert hashlib.sha256(",".join(str(i) for i in sorted(ids)).encode()).hexdigest() == run["ids_sha256"]
    assert run["result"]["log_loss"] == 0.6886 and run["result"]["shot_information"] == 0.0023
    assert reg.production_allowed("nhl-v6") == (False, "no PASS verdict")
    assert len(reg.prior_reads(e["test_set"], None, before_id="nhl-v7")) == 6     # v1-v5 + v6


def test_v7_record_is_complete_and_failed_and_the_test_set_has_seven_reads():
    """ARCHITECT 2026-10-02: v7 FAIL 0.6885; "main must show prior reads = 7 once
    v6/v7 records are spliced". v7's own stored prior_read_count is 5 AS WRITTEN
    (the laptop's ledger lacked v6's run when v7 ran); it is spliced verbatim."""
    e = reg.get("nhl-v7")
    assert e["status"] == "closed" and e["verdict"]["verdict"] == "FAIL"
    assert e["verdict"]["ruling"].startswith("ARCHITECT 2026-10-02: v7 VERDICT STANDS — FAIL 0.6885 vs 0.6866")
    run = e["run"]
    ids = [int(x) for x in open(os.path.join(ROOT, run["ids_file"])).read().split()]
    assert len(ids) == run["n_scored"] == 1394 == len(set(ids))
    assert hashlib.sha256(",".join(str(i) for i in sorted(ids)).encode()).hexdigest() == run["ids_sha256"]
    assert run["result"]["log_loss"] == 0.6885 and run["prior_read_count"] == 5
    assert len(reg.prior_reads(e["test_set"], None, before_id="nhl-v8")) == 7


def _record_ok(e, n):
    run = e["run"]
    ids = [int(x) for x in open(os.path.join(ROOT, run["ids_file"])).read().split()]
    assert len(ids) == run["n_scored"] == n == len(set(ids))
    assert hashlib.sha256(",".join(str(i) for i in sorted(ids)).encode()).hexdigest() == run["ids_sha256"]
    assert e["status"] == "closed" and e["verdict"]["verdict"] == "FAIL"


def test_v8_record_failed_and_the_2025_test_set_is_retired_at_eight_reads():
    """ARCHITECT 2026-10-02: v8 FAIL 0.6963 (k=12 on the grid edge); NHL 2025 RETIRED (8 reads)."""
    e = reg.get("nhl-v8")
    _record_ok(e, 1394)
    assert e["verdict"]["ruling"].startswith("ARCHITECT 2026-10-02: v8 VERDICT STANDS — FAIL 0.6963")
    assert e["run"]["result"]["fit_k"] == 12.0 and e["run"]["prior_read_count"] == 7
    assert len(reg.prior_reads(e["test_set"], None)) == 8
    with pytest.raises(reg.RegistryError, match="RETIRED"):
        reg.declare({**{k: e[k] for k in reg.DECLARE_FIELDS}, "id": "nhl-v9", "confirmation_plan": e["confirmation_plan"]},
                    path=os.devnull + "-never-written")


def test_intl_elo_v1_record_failed_on_calibration_with_one_read():
    """ARCHITECT 2026-10-02: intl-elo-v1 FAIL on calibration (log-loss passed 0.8507 vs bar 1.0431)."""
    e = reg.get("intl-elo-v1")
    _record_ok(e, 392)
    r = e["run"]["result"]
    assert r["crit_ll"] is True and r["crit_bands"] is False and r["neutral_rule"] == "intl-neutral-v2"
    assert round(r["ll_model"], 4) == 0.8507 and round(r["bar"], 4) == 1.0431
    assert len(reg.prior_reads(e["test_set"], None, before_id="intl-elo-v2")) == 1


def test_v7_run_record_is_never_rewritten_and_carries_the_ledger_annotation():
    """ARCHITECT 2026-10-02: nhl-v7's recorded prior-reads=5 stays as written (never rewrite a run record);
    the annotation ledger_count_at_record: 6 explains the laptop/ledger lag; the live count is the ledger's."""
    e = reg.get("nhl-v7")
    assert e["run"]["prior_read_count"] == 5 and e["ledger_count_at_record"] == 6
    assert "never" in e["ledger_count_note"] and "rewritten" in e["ledger_count_note"]
    assert len(reg.prior_reads(e["test_set"], None, before_id="nhl-v7")) == 6
