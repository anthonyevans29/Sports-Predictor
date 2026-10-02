"""#220 lane 2: the international Elo pre-commitment is declared in the live
registry BEFORE any run — frozen document present, executable 60-game plan,
unrun, no prior reads of its test set, and the open choices still marked for
ratification (nothing silently decided)."""
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
    assert "AWAITING RATIFICATION" in doc and doc.count("[RATIFY") == 5
    for frozen in ("+100", "friendlies | FRIENDLIES_INT | 20", "ln(|margin| + 1)", "ρ = −0.10", "− 0.010"):
        assert frozen in doc
