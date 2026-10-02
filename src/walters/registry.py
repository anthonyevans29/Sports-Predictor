"""
EXPERIMENT REGISTRY + CONFIRMATION DOCTRINE (#212, ARCHITECT 2026-10-01,
external review): "experiment registry (candidate, training cutoff, scored
match ids, prior reads) + DOCTRINE: a gate pass is followed by a declared
future-confirmation window before production (NFL's two-week ratification
generalized). Existing verdicts unchanged." 2026-10-02: "the registry
records every candidate from here."

The ledger is docs/registry/experiments.json (git-tracked, reviewed in PRs;
never under data/). One entry per candidate:

  DECLARE   before any run: id, sport, lane, what it is, the declaration
            (the frozen pre-commitment doc), training cutoff, test set,
            gate, and — new doctrine — the confirmation window a pass
            must survive before production.
  RUN       once per id (a second run is REFUSED: the test set is
            evaluated once). Stores the scored match ids (a sidecar file
            under docs/registry/ids/, plus count + sha256) and the result,
            and computes PRIOR READS: every earlier run on the same test
            set or with overlapping scored ids, so a winner on a
            many-times-read test set says so.
  VERDICT   the architect's ruling, verbatim. A PASS enters the declared
            confirmation window; production follows only after it.

Pre-registry verdicts are seeded as recorded (ids "not recorded"); their
verdicts are unchanged and count as prior reads of their test sets.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LEDGER = os.path.join(ROOT, "docs", "registry", "experiments.json")
IDS_DIR = os.path.join(ROOT, "docs", "registry", "ids")
DECLARE_FIELDS = ("id", "sport", "lane", "candidate", "declaration", "training_cutoff", "test_set",
                  "gate", "confirmation_window")


class RegistryError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path: str = LEDGER) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def save(entries: list[dict], path: str = LEDGER) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(entries, f, indent=2, sort_keys=False)
        f.write("\n")


def get(eid: str, path: str = LEDGER) -> dict | None:
    return next((e for e in load(path) if e["id"] == eid), None)


def declare(entry: dict, path: str = LEDGER) -> dict:
    """Record a candidate BEFORE its run. Every DECLARE_FIELDS key is
    required; the confirmation window is required by doctrine."""
    missing = [k for k in DECLARE_FIELDS if not entry.get(k)]
    if missing:
        raise RegistryError(f"declaration incomplete: {', '.join(missing)}")
    entries = load(path)
    if any(e["id"] == entry["id"] for e in entries):
        raise RegistryError(f"{entry['id']} is already declared")
    e = {**{k: entry[k] for k in DECLARE_FIELDS}, "declared_at": entry.get("declared_at") or _now(),
         "status": "declared", "run": None, "verdict": None}
    entries.append(e)
    save(entries, path)
    return e


def _ids_sha(ids: list[int]) -> str:
    return hashlib.sha256(",".join(str(i) for i in sorted(ids)).encode()).hexdigest()


def _ids_of(e: dict, ids_dir: str) -> set[int] | None:
    run = e.get("run") or {}
    f = run.get("ids_file")
    if not f:
        return None
    p = os.path.join(ids_dir, os.path.basename(f))
    if not os.path.exists(p):
        return None
    with open(p) as fh:
        return {int(x) for x in fh.read().split()}


def prior_reads(test_set: str, scored_ids: list[int] | None, before_id: str | None = None,
                path: str = LEDGER, ids_dir: str = IDS_DIR) -> list[dict]:
    """Earlier RUN entries that read the same test set, or whose recorded
    scored ids overlap these. Each: id, candidate, run date, why, overlap."""
    want = set(scored_ids or ())
    out = []
    for e in load(path):
        if e["id"] == before_id:
            break
        if not e.get("run"):
            continue
        same = e.get("test_set") == test_set
        theirs = _ids_of(e, ids_dir)
        overlap = len(want & theirs) if (want and theirs) else None
        if same or overlap:
            out.append({"id": e["id"], "candidate": e["candidate"], "run_at": e["run"].get("run_at"),
                        "why": "same test set" if same else "overlapping scored ids",
                        "overlap": overlap})
    return out


def record_run(eid: str, scored_ids: list[int], result: dict, path: str = LEDGER,
               ids_dir: str = IDS_DIR) -> dict:
    """The ONE run of a declared candidate: scored ids + result + prior reads.
    A second run of the same id is refused (the test set is read once)."""
    entries = load(path)
    e = next((x for x in entries if x["id"] == eid), None)
    if e is None:
        raise RegistryError(f"{eid} was never declared: declare it (frozen) before any run")
    if e.get("run"):
        raise RegistryError(f"{eid} already ran at {e['run'].get('run_at')}: the test set is evaluated once")
    ids = sorted(set(int(i) for i in scored_ids))
    os.makedirs(ids_dir, exist_ok=True)
    fname = f"{eid}.txt"
    with open(os.path.join(ids_dir, fname), "w") as f:
        f.write("\n".join(str(i) for i in ids) + "\n")
    reads = prior_reads(e["test_set"], ids, before_id=eid, path=path, ids_dir=ids_dir)
    e["run"] = {"run_at": _now(), "n_scored": len(ids), "ids_sha256": _ids_sha(ids),
                "ids_file": f"docs/registry/ids/{fname}", "result": result,
                "prior_reads": reads, "prior_read_count": len(reads)}
    e["status"] = "run"
    save(entries, path)
    return e


def record_verdict(eid: str, verdict: str, ruling: str, path: str = LEDGER) -> dict:
    """The architect's verdict, verbatim. PASS -> status "confirming": the
    declared confirmation window runs before production (doctrine)."""
    v = verdict.upper()
    if v not in ("PASS", "FAIL", "REJECT", "WITHDRAWN"):
        raise RegistryError(f"unknown verdict {verdict!r}")
    entries = load(path)
    e = next((x for x in entries if x["id"] == eid), None)
    if e is None or not e.get("run"):
        raise RegistryError(f"{eid}: no run recorded — a verdict needs a run")
    e["verdict"] = {"verdict": v, "ruling": ruling, "at": _now()}
    e["status"] = "confirming" if v == "PASS" else "closed"
    save(entries, path)
    return e


def production_allowed(eid: str, path: str = LEDGER) -> tuple[bool, str]:
    """Doctrine check: production only after a PASS AND a completed
    confirmation (recorded with record_confirmation)."""
    e = get(eid, path)
    if e is None:
        return False, "not in the registry"
    if not e.get("verdict") or e["verdict"]["verdict"] != "PASS":
        return False, "no PASS verdict"
    c = e.get("confirmation")
    if not c:
        return False, f"PASS, confirmation window open ({e['confirmation_window']})"
    return (c["outcome"] == "CONFIRMED"), f"confirmation {c['outcome']}"


def record_confirmation(eid: str, outcome: str, ruling: str, path: str = LEDGER) -> dict:
    outcome = outcome.upper()
    if outcome not in ("CONFIRMED", "NOT_CONFIRMED"):
        raise RegistryError(f"unknown outcome {outcome!r}")
    entries = load(path)
    e = next((x for x in entries if x["id"] == eid), None)
    if e is None or e.get("status") != "confirming":
        raise RegistryError(f"{eid} is not in a confirmation window")
    e["confirmation"] = {"outcome": outcome, "ruling": ruling, "at": _now()}
    e["status"] = "production" if outcome == "CONFIRMED" else "closed"
    save(entries, path)
    return e
