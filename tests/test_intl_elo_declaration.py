"""#220 lane 2: the international Elo pre-commitment is declared in the live
registry BEFORE any run — frozen document present and RATIFIED (2026-10-02),
executable 60-game plan, unrun, no prior reads of its test set; the #234
rulings applied (CNL_Q K 40; v2 leave-one-out, home-and-away host sets)."""
import os

from src.walters import registry as reg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_intl_elo_v1_declared_unrun_with_an_executable_plan():
    e = reg.get("intl-elo-v1")
    # v1 RAN on the laptop (FAIL, ARCHITECT 2026-10-02): its record lands by splice
    assert e is not None and e["status"] in ("declared", "run", "closed")
    if e["run"] is not None:
        assert e["run"]["n_scored"] > 0 and len(e["run"]["ids_sha256"]) == 64
    assert reg.check_plan(e["confirmation_plan"])["n_games"] == 60
    assert e["confirmation_plan"]["must_beat_reference"] is True
    assert reg.prior_reads(e["test_set"], None, before_id="intl-elo-v1") == []          # v1 was the first read
    doc = open(os.path.join(ROOT, e["declaration"])).read()
    assert "Status: RATIFIED" in doc and "[RATIFY" not in doc and e.get("ratified")
    assert "| Nations League | UNL, CNL, CNL_Q" in doc and "at home even if that city" in doc and "intl-neutral-v3 (pre-declared)" in doc
    for frozen in ("+100", "friendlies | FRIENDLIES_INT | 20", "max(margin, 1)", "ρ = −0.10", "− 0.010",
                   "intl-neutral-v2"):
        assert frozen in doc


def test_known_limitation_is_declared_in_doc_and_registry():
    """ARCHITECT 2026-10-02: intl-elo-v1 runs under v2 as built, its known
    limitation DECLARED in the doc and the registry entry."""
    lim = ("home-and-away competition play-offs and finals at neutral venues are priced with the home edge; "
           "v2's 10% check is vacuous under the HOME ruling")
    e = reg.get("intl-elo-v1")
    assert lim in e["limitation"]
    doc = " ".join(open(os.path.join(ROOT, e["declaration"])).read().split())
    assert "DECLARED LIMITATION" in doc and lim in doc
