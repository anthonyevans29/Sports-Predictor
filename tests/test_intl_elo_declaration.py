"""#220 lane 2: the international Elo pre-commitment is declared in the live
registry BEFORE any run — frozen document present and RATIFIED (2026-10-02),
executable 60-game plan, unrun, no prior reads of its test set, and the one
unruled choice (CNL_Q's K class) marked, not guessed."""
import os

from src.walters import registry as reg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_intl_elo_v1_declared_unrun_with_an_executable_plan():
    e = reg.get("intl-elo-v1")
    assert e is not None and e["status"] == "declared" and e["run"] is None and e["verdict"] is None
    assert reg.check_plan(e["confirmation_plan"])["n_games"] == 60
    assert e["confirmation_plan"]["must_beat_reference"] is True
    assert reg.prior_reads(e["test_set"], None, before_id="intl-elo-v1") == []
    doc = open(os.path.join(ROOT, e["declaration"])).read()
    assert "Status: RATIFIED" in doc and "[RATIFY" not in doc and e.get("ratified")
    assert "CNL_Q's K class is not ruled" in doc
    for frozen in ("+100", "friendlies | FRIENDLIES_INT | 20", "max(margin, 1)", "ρ = −0.10", "− 0.010",
                   "intl-neutral-v2"):
        assert frozen in doc
