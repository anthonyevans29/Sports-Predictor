"""The nhl-v6 run record (from the laptop, 2026-10-02) and its FAIL verdict
(ARCHITECT, verbatim): the ids sidecar matches the recorded sha256 and count,
the verdict is FAIL, the entry is closed, production is refused; with v7's
record (also FAIL) the NHL 2025 test set carries 7 reads."""
import hashlib
import os

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
    assert len(reg.prior_reads(e["test_set"], None)) == 7
