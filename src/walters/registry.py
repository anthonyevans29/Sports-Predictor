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
  CONFIRM   the window's READ, executed against the declaration's
            confirmation_plan: >= n_games future games (after the verdict,
            none from the test set), the plan's metric (and the reference's),
            the outcome COMPUTED, never stated (review on #222, 2026-10-02).

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


PLAN_METRICS = ("log_loss",)

# RETIRED TEST SETS (DOCTRINE, ARCHITECT 2026-10-02, from the external review,
# binding): "the 2025 test season has been read 7 times. After v8 it is
# RETIRED as a test set; any later NHL candidate declares 2026-27 (as it
# accrues, >=600 games) as its test season." test_set -> (the LAST id allowed
# on it, what to declare instead). declare() and record_run() refuse anything
# else on a retired test set.
RETIRED_TEST_SETS = {
    "NHL 2025 (2025-26 regular season; nhl_backtest TEST_SEASON, train 2024)":
        ("nhl-v8", "NHL 2026-27 regular season as it accrues (>= 600 games)"),
}


def _retired_refusal(test_set: str, eid: str) -> str | None:
    last = RETIRED_TEST_SETS.get(test_set)
    if last and eid != last[0]:
        return (f"{test_set!r} is RETIRED as a test set (doctrine 2026-10-02; {last[0]} was its last candidate): "
                f"declare {last[1]} instead")
    return None


def check_plan(plan) -> dict:
    """The EXECUTABLE confirmation plan (review on #222, 2026-10-02): the window
    is not prose. Required: n_games (> 0) future games scored after the
    verdict, the metric (lower is better), the bar the metric must meet, and
    whether it must also beat a named reference scored on the SAME games."""
    if not isinstance(plan, dict):
        raise RegistryError("confirmation_plan must be a dict {n_games, metric, bar, must_beat_reference, reference}")
    n, metric, bar = plan.get("n_games"), plan.get("metric"), plan.get("bar")
    if not isinstance(n, int) or isinstance(n, bool) or n <= 0:
        raise RegistryError("confirmation_plan.n_games must be a positive integer")
    if metric not in PLAN_METRICS:
        raise RegistryError(f"confirmation_plan.metric must be one of {PLAN_METRICS}")
    if not isinstance(bar, (int, float)) or isinstance(bar, bool):
        raise RegistryError("confirmation_plan.bar must be a number")
    beat = plan.get("must_beat_reference")
    if not isinstance(beat, bool):
        raise RegistryError("confirmation_plan.must_beat_reference must be true or false")
    if beat and not plan.get("reference"):
        raise RegistryError("confirmation_plan.reference must name the reference model")
    return {"n_games": n, "metric": metric, "bar": float(bar), "must_beat_reference": beat,
            "reference": plan.get("reference")}


def declare(entry: dict, path: str = LEDGER) -> dict:
    """Record a candidate BEFORE its run. Every DECLARE_FIELDS key is
    required; the confirmation window is required by doctrine, as prose AND
    as an executable confirmation_plan (check_plan)."""
    missing = [k for k in DECLARE_FIELDS if not entry.get(k)]
    if missing:
        raise RegistryError(f"declaration incomplete: {', '.join(missing)}")
    plan = check_plan(entry.get("confirmation_plan"))
    why = _retired_refusal(entry["test_set"], entry["id"])
    if why:
        raise RegistryError(why)
    entries = load(path)
    if any(e["id"] == entry["id"] for e in entries):
        raise RegistryError(f"{entry['id']} is already declared")
    e = {**{k: entry[k] for k in DECLARE_FIELDS}, "confirmation_plan": plan,
         "declared_at": entry.get("declared_at") or _now(),
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
    why = _retired_refusal(e["test_set"], eid)
    if why:
        raise RegistryError(why)
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
    if c.get("outcome") == "CONFIRMED" and not (c.get("n_scored") and c.get("ids_sha256") and c.get("result")):
        return False, "confirmation record incomplete (no scored ids / result)"
    return (c["outcome"] == "CONFIRMED"), f"confirmation {c['outcome']}"


def frozen_cohort(e: dict, ids_dir: str | None = None) -> list[int] | None:
    """The FROZEN confirmation cohort's ids (verified against its sha256), or
    None when no cohort was frozen. A tampered or missing file refuses."""
    c = e.get("confirmation_cohort")
    if not c:
        return None
    ids_dir = ids_dir or IDS_DIR
    p = os.path.join(ids_dir, os.path.basename(c["ids_file"]))
    if not os.path.exists(p):
        raise RegistryError(f"{e['id']}: frozen cohort file {c['ids_file']} is missing")
    with open(p) as fh:
        ids = sorted(int(x) for x in fh.read().split())
    if _ids_sha(ids) != c["ids_sha256"] or len(ids) != c["n"]:
        raise RegistryError(f"{e['id']}: frozen cohort file does not match its sha256/count — refused")
    return ids


def freeze_confirmation_cohort(eid: str, cohort_ids: list[int], basis: dict,
                               path: str = LEDGER, ids_dir: str = IDS_DIR) -> dict:
    """FREEZE the confirmation cohort (review on #248, 2026-10-02): the first
    n_games ELIGIBLE fixture ids, chosen independently of result availability,
    fixed once. A later confirmation must score exactly this set; a pending or
    missing label leaves it incomplete, never admits a replacement. Refused
    outside a window, when already frozen, unless exactly n_games distinct ids,
    or when any id was in the scored test set."""
    entries = load(path)
    e = next((x for x in entries if x["id"] == eid), None)
    if e is None or e.get("status") != "confirming":
        raise RegistryError(f"{eid} is not in a confirmation window (needs a PASS verdict)")
    plan = e.get("confirmation_plan")
    if not plan:
        raise RegistryError(f"{eid} has no executable confirmation_plan")
    if e.get("confirmation_cohort"):
        raise RegistryError(f"{eid}: the confirmation cohort is already frozen ({e['confirmation_cohort']['ids_sha256'][:12]}…)"
                            " — a frozen cohort never changes")
    ids = sorted(set(int(i) for i in cohort_ids))
    if len(ids) != plan["n_games"] or len(ids) != len(cohort_ids):
        raise RegistryError(f"{eid}: a cohort is exactly {plan['n_games']} distinct fixtures (got {len(cohort_ids)}, "
                            f"{len(ids)} distinct)")
    overlap = len((_ids_of(e, ids_dir) or set()) & set(ids))
    if overlap:
        raise RegistryError(f"{eid}: {overlap} cohort fixture(s) were in the scored test set — not future games")
    os.makedirs(ids_dir, exist_ok=True)
    fname = f"{eid}.cohort.txt"
    with open(os.path.join(ids_dir, fname), "w") as f:
        f.write("\n".join(str(i) for i in ids) + "\n")
    e["confirmation_cohort"] = {"n": len(ids), "ids_sha256": _ids_sha(ids), "ids_file": f"docs/registry/ids/{fname}",
                                "frozen_at": _now(), "basis": basis}
    save(entries, path)
    return e


def record_confirmation(eid: str, scored_ids: list[int], result: dict, ruling: str,
                        path: str = LEDGER, ids_dir: str = IDS_DIR) -> dict:
    """The confirmation READ, executed against the declared plan (never a
    stated outcome). Refused unless the entry is `confirming` (a PASS), the
    read scores >= plan.n_games games, every game started AFTER the verdict
    (`result["first_game_at"]`, ISO UTC), none of them was in the scored test
    set, and the result carries the plan's metric (and the reference's when
    the plan requires beating it). The outcome is COMPUTED: CONFIRMED iff
    metric <= bar and, when required, metric < reference (a tie fails)."""
    entries = load(path)
    e = next((x for x in entries if x["id"] == eid), None)
    if e is None or e.get("status") != "confirming":
        raise RegistryError(f"{eid} is not in a confirmation window (needs a PASS verdict)")
    plan = e.get("confirmation_plan")
    if not plan:
        raise RegistryError(f"{eid} has no executable confirmation_plan: it cannot be confirmed")
    ids = sorted(set(int(i) for i in scored_ids))
    cohort = frozen_cohort(e, ids_dir)
    if cohort is not None and ids != cohort:
        missing, extra = len(set(cohort) - set(ids)), len(set(ids) - set(cohort))
        raise RegistryError(f"{eid}: the read must score exactly the frozen cohort ({missing} cohort fixture(s) "
                            f"unscored, {extra} outside it) — incomplete, never a replacement")
    if len(ids) < plan["n_games"]:
        raise RegistryError(f"{eid}: confirmation scored {len(ids)} games < the plan's {plan['n_games']} — incomplete")
    first = result.get("first_game_at")
    verdict_at = (e.get("verdict") or {}).get("at")
    if not first or not verdict_at or str(first) <= str(verdict_at):
        raise RegistryError(f"{eid}: confirmation games must all start AFTER the verdict ({verdict_at}); "
                            f"first_game_at {first!r}")
    seen = _ids_of(e, ids_dir) or set()
    overlap = len(seen & set(ids))
    if overlap:
        raise RegistryError(f"{eid}: {overlap} confirmation game(s) were in the scored test set — not future games")
    metric = result.get(plan["metric"])
    if not isinstance(metric, (int, float)):
        raise RegistryError(f"{eid}: result lacks the plan's metric {plan['metric']!r}")
    ref = result.get("reference_" + plan["metric"])
    if plan["must_beat_reference"] and not isinstance(ref, (int, float)):
        raise RegistryError(f"{eid}: the plan requires beating {plan['reference']}; result lacks "
                            f"'reference_{plan['metric']}'")
    ok = metric <= plan["bar"] and (not plan["must_beat_reference"] or metric < ref)
    outcome = "CONFIRMED" if ok else "NOT_CONFIRMED"
    os.makedirs(ids_dir, exist_ok=True)
    fname = f"{eid}.confirm.txt"
    with open(os.path.join(ids_dir, fname), "w") as f:
        f.write("\n".join(str(i) for i in ids) + "\n")
    e["confirmation"] = {"outcome": outcome, "ruling": ruling, "at": _now(), "n_scored": len(ids),
                         "ids_sha256": _ids_sha(ids), "ids_file": f"docs/registry/ids/{fname}",
                         "result": result, "plan": plan}
    e["status"] = "production" if ok else "closed"
    save(entries, path)
    return e
