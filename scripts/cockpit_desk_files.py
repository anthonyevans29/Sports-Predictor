"""
F1c (#191) helper for the headless Cockpit verifies: the Cockpit renders
ONLY files that carry `desk` blocks (export --desk) and refuses the rest. A
verify that used to load synthetic LEGACY files now writes them through the
Python Desk first — the same pinned clock and graded counts the Cockpit's
ledger is seeded with — plus the desk_parlays file, exactly as the host
emits them. The policy itself is checked against the deleted JS's frozen
outputs by tests/test_desk_golden.py; these verifies keep checking what the
Cockpit SHOWS and LOGS.

#87 v1.1 ADDENDUM (2026-10-06): the verifies predate it and pin pre-addendum fixtures (join-bid, maker basis,
"informational only", the frozen render golden), so files are written under dp.base_v11() by default;
base=False writes them under the addendum (scripts/cockpit_exec_addendum_verify.py).
"""
import contextlib
import json
import os
import sys
from datetime import timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.walters import desk_policy as dp  # noqa: E402


def desk_files(docs: dict, now, counts: dict | None = None, parlays: bool = True, base: bool = True) -> dict:
    """{name: doc} -> the same docs annotated (desk + desk_meta) in load order,
    plus desk_parlays.json (unless parlays=False). model_shadow docs, window
    cards and desk_parlays docs pass through unchanged."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    with (dp.base_v11() if base else contextlib.nullcontext()):
        return _desk_files(docs, now, counts, parlays)


def _desk_files(docs, now, counts, parlays):
    out, named = {}, []
    for n, d in docs.items():
        d = json.loads(json.dumps(d))
        if d.get("engine") == "model_shadow" or d.get("kind") == "desk_parlays_v1" or "window" in d:
            out[n] = d
            continue
        out[n] = dp.annotate(d, now=now, counts=counts, counts_source="verify")
        named.append((n, out[n]))
    if parlays and named:
        out["desk_parlays.json"] = dp.parlays_doc(named, now=now, counts=counts, counts_source="verify")
    return out


def write(tmp: str, docs: dict) -> list[str]:
    paths = []
    for n, d in docs.items():
        paths.append(os.path.join(tmp, n))
        with open(paths[-1], "w") as f:
            json.dump(d, f)
    return paths


def upload(page, paths, now=None, parlays: bool = True, base: bool = True):
    """Drop-in for page.set_input_files("#predFile", paths) in the verifies:
    annotates every prediction/fixtures file in place through the Python Desk
    (clock = `now` or the browser's Date.now(); counts = the page's own
    ledgerSummary(), exactly the operator flow), adds desk_parlays.json
    beside them unless one is already loaded, then uploads."""
    with (dp.base_v11() if base else contextlib.nullcontext()):
        return _upload(page, paths, now, parlays)


def _upload(page, paths, now, parlays):
    import tempfile
    from datetime import datetime

    if isinstance(paths, str):
        paths = [paths]
    if now is None:
        now = datetime.fromtimestamp(page.evaluate("Date.now()") / 1000.0, tz=timezone.utc)
    summ = page.evaluate("typeof ledgerSummary==='function'?ledgerSummary():null")
    counts = None
    if summ:
        fd, sp = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump(summ, f)
        counts, _ = dp.read_ledger_summary(sp)
    named, has_parlays = [], False
    for p in paths:
        with open(p) as f:
            d = json.load(f)
        if d.get("kind") == "desk_parlays_v1":
            has_parlays = True
            continue
        if d.get("engine") == "model_shadow" or "window" in d:
            continue
        if d.get("predictions") is None and d.get("fixtures") is None:
            continue
        # always (re)annotate from the page's CURRENT ledger: new counts = a fresh export
        for row in (d.get("predictions") or d.get("fixtures") or []):
            if isinstance(row, dict):
                row.pop("desk", None)
        d.pop("desk_meta", None)
        d = dp.annotate(d, now=now, counts=counts, counts_source="verify (ledgerSummary)")
        with open(p, "w") as f:
            json.dump(d, f)
        named.append((os.path.basename(p), d))
    out = list(paths)
    if parlays and named and not has_parlays:
        pp = os.path.join(os.path.dirname(paths[0]), "desk_parlays.json")
        with open(pp, "w") as f:
            json.dump(dp.parlays_doc(named, now=now, counts=counts, counts_source="verify (ledgerSummary)"), f)
        out.append(pp)
    page.set_input_files("#predFile", out)
    return out
