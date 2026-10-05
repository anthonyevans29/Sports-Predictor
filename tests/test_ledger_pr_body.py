"""LEDGER rule 5, enforced (operator review on #273/#274, 2026-10-05). GitHub
closes an Issue named after a closing keyword anywhere in a PR body, even after
a "not": #273, #274 and #275 closed #85, #211 and #276 on merge. The PR-body
lint rejects a closing keyword + ref outside a declared closure line."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ledger", ROOT / "scripts" / "ledger.py")
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)

# the original description lines, verbatim
ORIGINAL = {
    273: "Ledger: refs #85. It does **not** close #85, because #85 is the decision itself and this PR "
         "only builds the readout.",
    274: "Ledger: refs #211. **It does not close #211.** Two parts of #211 are still open: load-order "
         "invariance (resolve by as_of) and the ticket-product \"independence estimate\" label.",
    275: "Ledger: refs #220 and #276 (the declared \"57% unflagged venues\" limitation). It does not "
         "close #276: that closes on a ruling on the operator's receipt.",
}
CORRECTED = {
    273: "Ledger: refs #85. Outstanding work remains on #85: it is the decision itself and this PR only "
         "builds the readout.",
    274: "Ledger: refs #211. Outstanding work remains on #211. Two parts of #211 are still open: "
         "load-order invariance (by as_of) and the ticket-product \"independence estimate\" label.",
    275: "Ledger: refs #220 and #276 (the declared \"57% unflagged venues\" limitation). Outstanding "
         "work remains on #276: it stays open until a ruling on the operator's receipt.",
}


@pytest.mark.parametrize("pr", sorted(ORIGINAL))
def test_original_negated_descriptions_are_rejected(pr):
    stray = L.stray_closing_refs("## What & why\n\n" + ORIGINAL[pr])
    assert stray and all(s.startswith("line 3:") for s in stray)


@pytest.mark.parametrize("pr", sorted(CORRECTED))
def test_corrected_descriptions_are_accepted(pr):
    assert L.stray_closing_refs("## What & why\n\n" + CORRECTED[pr]) == []
    assert L.closes_refs(CORRECTED[pr]) == []


@pytest.mark.parametrize("body,refs", [
    ("Closes #12", [12]),
    ("Ledger: Closes #12, #13 and #14", [12, 13, 14]),
    ("- Fixes #7\n* resolves: #8", [7, 8]),
    ("Closes #276\nResolves limitation", [276]),
    ("Fixed in #279 (a review reply)", []),
    ("No closing refs at all.", []),
])
def test_declared_closure_lines_pass(body, refs):
    assert L.stray_closing_refs(body) == []
    assert L.closes_refs(body) == refs


@pytest.mark.parametrize("body", [
    "...which closes #111 under the wrong PR",                # the #116 incident
    "This won't fix #5 yet.",
    "Closes #12; does not close #13.",                       # a second ref on a closure line
    "Not closing: see closes owner/repo#9",
    "it never resolves https://github.com/o/r/issues/4",
])
def test_stray_closing_refs_are_rejected(body):
    assert L.stray_closing_refs(body)


def test_check_body_mode_exit_codes(monkeypatch, capsys):
    monkeypatch.setenv("PR_BODY", ORIGINAL[274])
    assert L.main(["check-body"]) == 1
    assert "REFUSED" in capsys.readouterr().out
    monkeypatch.setenv("PR_BODY", CORRECTED[274] + "\nCloses #300")
    assert L.main(["check-body"]) == 0
    assert "[300]" in capsys.readouterr().out
