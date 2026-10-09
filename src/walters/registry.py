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


# ARCHITECT 2026-10-02: "unscoreable is the criterion, not the status label;
# record the raw code as reason." A release needs evidence that the fixture
# can NEVER be scored: stored as cancelled, or finished without a scoreable
# result. A postponed / scheduled / live fixture is never released.
# "stale_orphan": ARCHITECT 2026-10-08, addendum 16 item 1 (#373, 4223907740, verbatim): a cohort fixture that later
# becomes STALE_ORPHAN "will never have a result. It is released and replaced like a cancelled fixture, reason
# STALE_ORPHAN." Only soccer-expansion-confirm offers such a release; intl-elo-v2's rule never yields one.
RELEASABLE_STATUSES = ("cancelled", "finished", "stale_orphan")


def frozen_cohort(e: dict, ids_dir: str | None = None) -> list[int] | None:
    """The FROZEN confirmation cohort's EFFECTIVE ids: the frozen file
    (verified against its sha256) with every recorded substitution applied
    (released out, replacement in). None when no cohort was frozen. A
    tampered or missing file refuses."""
    c = e.get("confirmation_cohort")
    if not c:
        return None
    ids = set(_frozen_base(e, c, ids_dir))
    for sub in c.get("substitutions") or []:
        ids.discard(int(sub["released"]))
        ids.add(int(sub["replacement"]))
    return sorted(ids)


def _frozen_base(e: dict, c: dict, ids_dir: str | None) -> list[int]:
    ids_dir = ids_dir or IDS_DIR
    p = os.path.join(ids_dir, os.path.basename(c["ids_file"]))
    if not os.path.exists(p):
        raise RegistryError(f"{e['id']}: frozen cohort file {c['ids_file']} is missing")
    with open(p) as fh:
        ids = sorted(int(x) for x in fh.read().split())
    if _ids_sha(ids) != c["ids_sha256"] or len(ids) != c["n"]:
        raise RegistryError(f"{e['id']}: frozen cohort file does not match its sha256/count — refused")
    return ids


def substitute_cohort_fixture(eid: str, released: int, replacement: int, reason: str, evidence: dict,
                              path: str = LEDGER, ids_dir: str = IDS_DIR) -> dict:
    """ARCHITECT 2026-10-02: "CANCELLED/ABANDONED games in the frozen 60 are
    RELEASED and replaced by the next eligible fixture after the cohort (61st,
    62nd …), recorded as a substitution with reason; a merely postponed game
    stays in the cohort until it is played or cancelled; never a swap of a
    scheduled-but-unplayed game." And: "AWD/WO (forfeit, walkover) games are
    RELEASED and substituted exactly like cancelled/abandoned — unscoreable is
    the criterion, not the status label; record the raw code as reason." The
    registry checks the bookkeeping (the released id is in the effective
    cohort, the replacement is new, never released before and not from the
    test set; the reason is the provider's raw code; the evidence shows a
    cancelled or finished fixture marked unscoreable); the caller
    (intl-elo-confirm --substitute) checks the stored rows and picks the
    replacement in order."""
    entries = load(path)
    e = next((x for x in entries if x["id"] == eid), None)
    if e is None or e.get("status") != "confirming":
        raise RegistryError(f"{eid} is not in a confirmation window (needs a PASS verdict)")
    c = e.get("confirmation_cohort")
    if not c:
        raise RegistryError(f"{eid}: no frozen cohort to substitute in — freeze it first")
    if not evidence or not evidence.get("status"):
        raise RegistryError(f"{eid}: a substitution records its evidence (the stored status)")
    if evidence["status"] not in RELEASABLE_STATUSES or evidence.get("unscoreable") is not True:
        raise RegistryError(f"{eid}: a cohort fixture is released only when it can never be scored (cancelled, or "
                            f"finished without a scoreable result); got status {evidence['status']!r} — a postponed "
                            "or unplayed game stays")
    if not reason or not str(reason).strip():
        raise RegistryError(f"{eid}: the reason is the provider's raw status code")
    released, replacement = int(released), int(replacement)
    effective = set(frozen_cohort(e, ids_dir))
    ever_out = {int(s["released"]) for s in c.get("substitutions") or []}
    if released not in effective:
        raise RegistryError(f"{eid}: fixture {released} is not in the effective cohort")
    if replacement in effective or replacement in ever_out:
        raise RegistryError(f"{eid}: fixture {replacement} is already in the cohort or was released from it")
    if replacement in (_ids_of(e, ids_dir) or set()):
        raise RegistryError(f"{eid}: fixture {replacement} was in the scored test set — not a future game")
    c.setdefault("substitutions", []).append({"released": released, "replacement": replacement,
                                              "reason": reason, "evidence": evidence, "at": _now()})
    save(entries, path)
    return e


def freeze_confirmation_cohort(eid: str, cohort_ids: list[int], basis: dict,
                               path: str = LEDGER, ids_dir: str = IDS_DIR, no_fetch: bool = False,
                               echo=None) -> dict:
    """FREEZE the confirmation cohort (review on #248, 2026-10-02): the first
    n_games ELIGIBLE fixture ids, chosen independently of result availability,
    fixed once. A later confirmation must score exactly this set; a pending or
    missing label leaves it incomplete, never admits a replacement. Refused
    outside a window, when already frozen, unless exactly n_games distinct ids,
    or when any id was in the scored test set, and (#329 RULED 2026-10-08) when the cross-ref guard finds a
    cohort, run record or reservation for `eid` on any ref the clone knows that this tree does not hold."""
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
    receipt = cross_ref_guard(eid, no_fetch=no_fetch)       # #329 RULED 2026-10-08: before any write
    if echo:
        echo(receipt)
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


# ----------------------------------------------------------------- cross-ref guard --
# #329 RULED (ARCHITECT 2026-10-08, addendum 11, item 5): "build the guard as proposed, parts 1 and 2, as one shared
# function. Every cohort freeze and every one-run reservation calls it: a cohort, a run record or a reservation for
# the experiment on any ref the clone knows refuses, naming the ref and the commit. --no-fetch stays, and the receipt
# then prints that other clones were not checked." The finding (#329): a registry write that lives only on an
# unmerged laptop branch is invisible to the next freeze, which is how a second intl-elo-v2 cohort was accepted.
#   part 2: fetch origin's laptop/* branches first (a failed fetch refuses unless --no-fetch);
#   part 1: scan every ref the clone knows (git for-each-ref refs/heads refs/remotes) for a cohort, a run record or a
#           reservation of the experiment that this working tree does not hold identically, and refuse naming each
#           ref and commit. Never overwrites; part 1 needs no network.

REG_REL = "docs/registry"
GUARD_REMOTE = "origin"
GUARD_FETCH_REFSPEC = "+refs/heads/laptop/*:refs/remotes/origin/laptop/*"
NOT_CHECKED = "other clones not checked"
GUARD_KINDS = ("cohort", "run record", "reservation")


class CrossRefRefused(RegistryError):
    pass


def _git(repo: str, *args: str, inp: bytes | None = None):
    import subprocess
    return subprocess.run(["git", "-C", repo, *args], input=inp, capture_output=True)


def _guard_paths(eid: str) -> dict:
    return {"ledger": f"{REG_REL}/experiments.json", "cohort": f"{REG_REL}/ids/{eid}.cohort.txt",
            "run": f"{REG_REL}/ids/{eid}.txt", "reservation": f"{REG_REL}/{eid}.started.json"}


def _guard_state(eid: str, read) -> dict:
    """{kind: comparable value or None} for one tree; `read(relpath)` -> bytes | None. A kind is held when the
    ledger entry carries it (confirmation_cohort / run) or its file exists; the value is both, so a tree holds it
    "identically" only when the entry field and the file bytes both match."""
    p = _guard_paths(eid)
    entry = None
    raw = read(p["ledger"])
    if raw is not None:
        try:
            entry = next((e for e in json.loads(raw) if isinstance(e, dict) and e.get("id") == eid), None)
        except (ValueError, TypeError):
            entry = None
    entry = entry or {}

    def val(field, f):
        fld, blob = (entry.get(field) if field else None), read(p[f])
        if not fld and blob is None:
            return None
        return (json.dumps(fld, sort_keys=True) if fld else None, blob)
    return {"cohort": val("confirmation_cohort", "cohort"), "run record": val("run", "run"),
            "reservation": val(None, "reservation")}


def _worktree_reader(repo: str):
    def read(rel):
        f = os.path.join(repo, rel)
        if not os.path.isfile(f):
            return None
        with open(f, "rb") as fh:
            return fh.read()
    return read


def _blobs_at(repo: str, specs: list[str]) -> dict:
    """`<commit>:<path>` -> bytes | None for every spec, read in one `git cat-file --batch`."""
    if not specs:
        return {}
    r = _git(repo, "cat-file", "--batch", inp=("\n".join(specs) + "\n").encode())
    if r.returncode != 0:
        raise CrossRefRefused(f"cross-ref guard: git cat-file failed ({r.stderr.decode().strip()}) — refused")
    out, buf, i = {}, r.stdout, 0
    for spec in specs:
        nl = buf.index(b"\n", i)
        head = buf[i:nl].split()
        i = nl + 1
        if len(head) == 3 and head[1] in (b"blob", b"tree", b"commit", b"tag"):
            size = int(head[2])
            out[spec] = buf[i:i + size] if head[1] == b"blob" else None
            i += size + 1
        else:                                    # "<spec> missing" / ambiguous
            out[spec] = None
    return out


def cross_ref_guard(eid: str, no_fetch: bool = False, repo: str | None = None) -> str:
    """THE shared guard (#329 RULED 2026-10-08): every cohort freeze and every one-run reservation calls it BEFORE
    it writes. Fetches origin's laptop/* branches (unless no_fetch; a failed fetch refuses), then scans every ref
    the clone knows (refs/heads, refs/remotes; symbolic refs skipped) for a cohort, a run record or a reservation
    of `eid` that this working tree does not hold identically, and refuses (CrossRefRefused, a RegistryError: the
    CLI exits 2) naming every such ref and its commit. Returns the receipt line; with no_fetch it says that other
    clones were not checked. A clone git cannot read refuses (fails closed)."""
    repo = repo or ROOT
    if no_fetch:
        scope = f"--no-fetch: {NOT_CHECKED}"
    else:
        r = _git(repo, "fetch", "--quiet", GUARD_REMOTE, GUARD_FETCH_REFSPEC)
        if r.returncode != 0:
            raise CrossRefRefused(
                f"{eid}: the cross-ref guard could not fetch {GUARD_REMOTE} laptop/* "
                f"({' '.join(r.stderr.decode().split()) or f'exit {r.returncode}'}) — other clones cannot be checked; refused. "
                f"--no-fetch checks only the refs this clone knows (the receipt then says {NOT_CHECKED})")
        scope = f"fetched {GUARD_REMOTE} laptop/*"
    r = _git(repo, "for-each-ref", "--format=%(refname)%09%(objectname)%09%(symref)", "refs/heads", "refs/remotes")
    if r.returncode != 0:
        raise CrossRefRefused(f"{eid}: the cross-ref guard cannot list this clone's refs "
                              f"({r.stderr.decode().strip()}) — refused")
    refs = []
    for line in r.stdout.decode().splitlines():
        name, sha, sym = (line.split("\t") + ["", ""])[:3]
        if name and sha and not sym:
            refs.append((name, sha))
    here = _guard_state(eid, _worktree_reader(repo))
    paths = list(_guard_paths(eid).values())
    blobs = _blobs_at(repo, [f"{sha}:{p}" for _, sha in refs for p in paths])
    hits = []
    for name, sha in refs:
        theirs = _guard_state(eid, lambda rel, sha=sha: blobs.get(f"{sha}:{rel}"))
        for kind in GUARD_KINDS:
            if theirs[kind] is not None and theirs[kind] != here[kind]:
                fld = json.loads(theirs[kind][0]) if theirs[kind][0] else None
                detail = f", sha256 {fld['ids_sha256'][:16]}…" if isinstance(fld, dict) and fld.get("ids_sha256") else ""
                hits.append(f"a {kind} on ref {name.removeprefix('refs/')} at commit {sha}{detail}")
    if hits:
        raise CrossRefRefused(f"{eid}: the cross-ref guard (#329) found " + "; ".join(hits)
                              + " — not held identically by this tree. A cohort is frozen once and the one run is "
                              "reserved once, never overwritten: splice that ref or get a ruling first")
    return (f"cross-ref guard: {scope} · {len(refs)} ref(s) scanned · none holds a cohort, run record or reservation "
            f"for {eid} that this tree does not hold identically")
