"""THE LEDGER (architect 2026-09-29): Issues = state, BACKLOG.md = history, one
Project = order. Pins the fixed taxonomy, the label lint, the PR-title prefix,
"Closes #N" routing, the limitation rule, rule 2 (no closing by hand), the
bootstrap's idempotence and queue order, and the backfill manifest itself:
every item lints clean and its BACKLOG link resolves in git."""
import importlib.util
import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ledger", ROOT / "scripts" / "ledger.py")
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)
TAX = L.load()
ITEMS = json.loads(L.BACKFILL.read_text())["items"]


def test_taxonomy_is_the_ruled_fixed_set():
    labels = set(L.labels_of(TAX))
    assert {x for x in labels if x.startswith("track:")} == {f"track:{v}" for v in
                                                           ("K", "B", "T", "H", "R", "policy", "model", "ops")}
    assert {x for x in labels if x.startswith("class:")} == {f"class:{v}" for v in (
        "lane", "limitation", "finding", "doctrine", "operator-action", "probe")}
    assert {x for x in labels if x.startswith("sport:")} == {f"sport:{v}" for v in (
        "mlb", "nfl", "ncaa", "nhl", "soccer", "cups", "unl", "all")}
    assert {x for x in labels if x.startswith("size:")} == {"size:S", "size:M", "size:L"}
    assert labels - {x for x in labels if ":" in x} == {"needs-ruling", "needs-operator"}
    assert [m["title"] for m in TAX["milestones"]] == [
        "Cutover ~Oct 8", "Policy v1.2 promotion (30 value shadows)", "Executable-edge ruling (2 wks of ladders)",
        "Offseason decisions (MLB egress/provider)", "NHL reopening (goalie source)",
        "Cup reopening (rotation R-track)"]
    assert TAX["project"]["statuses"] == ["Queue", "In progress", "Waiting on condition", "Done"]
    assert [v["name"] for v in TAX["views"]] == ["Architect review", "Operator today", "Queue",
                                                  "Open limitations", "Cutover checklist", "By sport"]


def test_lint_and_prefix_and_refs():
    ok = ["track:K", "class:lane", "sport:all", "size:M", "needs-ruling"]
    assert L.lint(ok, TAX) == []
    p = L.lint(["track:K", "track:B", "class:lane", "bug"], TAX)
    assert any("track:" in x and "has 2" in x for x in p) and any("`sport:`" in x for x in p)
    assert any("`size:`" in x for x in p) and any("outside the fixed set: bug" in x for x in p)
    assert L.prefix_labels("[K2] exec edge", TAX) == ["track:K"]
    assert L.prefix_labels("[ops] timer", TAX) == ["track:ops"] and L.prefix_labels("MLB PHASE A", TAX) == []
    assert L.closes_refs("Closes #12\nfixes #3\n- resolves: #7\nSee #99") == [3, 7, 12]
    assert L.closes_refs("Ledger: Closes #111, #112 and #90") == [90, 111, 112]      # the PR template form
    # prose never counts (#116's description: "...which closes #111, #112...")
    assert L.closes_refs("After merge I replay #114, which closes #111, #112 and #90.") == []
    assert L.closes_refs("Closes #96. Resolves limitation.") == [96]
    assert L.resolves_limitation("... Resolves limitation #7") and not L.resolves_limitation("Closes #7")


def test_closed_verdicts_limitation_rule_and_rule_2():
    lim = ["class:limitation"]
    assert L.closed_verdict(["class:lane"], {"type": "PullRequest", "body": "Closes #4"}, None)[0] == "done"
    assert L.closed_verdict(lim, {"type": "PullRequest", "body": "Closes #4"}, None)[0] == "reopen"
    assert L.closed_verdict(lim, {"type": "PullRequest", "body": "Closes #4\nResolves limitation"}, None)[0] == "done"
    assert L.closed_verdict(["class:finding"], None, "done, thanks")[0] == "reopen"          # by hand: never
    assert L.closed_verdict(["class:finding"], None, "> ARCHITECT: closed, ruled moot")[0] == "done"


def test_backfill_manifest_lints_clean_and_links_resolve_in_git():
    keys = [it["key"] for it in ITEMS]
    assert len(keys) == len(set(keys))
    titles = {m["title"] for m in TAX["milestones"]}
    for it in ITEMS:
        assert L.lint(L.item_labels(it), TAX) == [], it["key"]
        assert it.get("milestone") in titles | {None}, it["key"]
        if it["cls"] == "limitation":
            assert it.get("reopening"), f"{it['key']}: a limitation needs its reopening condition or accepted limit"
        b = it["backlog"]
        assert re.fullmatch(r"[0-9a-f]{40}", b["commit"])
        try:
            text = subprocess.run(["git", "show", f"{b['commit']}:BACKLOG.md"], cwd=ROOT, capture_output=True,
                                  text=True, check=True).stdout
        except subprocess.CalledProcessError:
            pytest.skip("shallow clone: the linked commits are not all present")
        assert b["heading"] in text.splitlines()[b["line"] - 1], it["key"]
    # today's list (architect 2026-09-29) is all present
    for k in ("dh-game2", "mlb-laptop-only", "soccer-lm-kalshi", "mlb-lm-cadence", "injury-latency", "magicdns",
              "ncaa-spread-ref", "unresolved-positions"):
        assert k in keys


class FakeGH:
    repo = "o/r"

    def __init__(self, labels=(), issues=(), milestones=()):
        self.labels, self.issues, self.ms, self.calls = list(labels), list(issues), list(milestones), []

    def paged(self, path):
        if path.endswith("/labels"):
            return [{"name": n, "color": "x", "description": ""} for n in self.labels]
        if "/milestones" in path:
            return self.ms
        return self.issues

    def rest(self, method, path, body=None):
        self.calls.append((method, path, body))
        if method == "POST" and path.endswith("/issues"):
            n = 100 + len(self.issues)
            x = {"number": n, "node_id": f"I{n}", "body": body["body"], "labels": body["labels"]}
            self.issues.append(x)
            return x
        if method == "POST" and path.endswith("/milestones"):
            self.ms.append({"title": body["title"], "number": len(self.ms) + 1})
            return {"number": len(self.ms)}
        if method == "GET" and "/issues/" in path:
            n = int(path.rsplit("/", 1)[1])
            return {"number": n, "node_id": f"I{n}", "state": "open"}
        return {}

    def graphql(self, q, v=None):
        self.calls.append(("GQL", q[:40], v))
        if "repository(owner" in q and "issue(" in q:
            return {"repository": {"issue": self.closed}}
        return {"repository": {"id": "R1"}}


class FakeProject:
    def __init__(self):
        self.items, self.order, self.status, self.vals = {}, [], {}, {}
        self.fields = {n: {} for n in ("Status", "Track", "Class", "Sport", "Reopening condition", "Due date")}

    def ensure(self, repo_id, tax):
        return True

    def find(self, cid):
        it = self.items.get(cid)
        return (it, self.status.get(it)) if it else (None, None)

    def add(self, cid):
        self.items[cid] = f"item-{cid}"
        return self.items[cid]

    def set(self, item, field, value):
        (self.status if field == "Status" else self.vals.setdefault(item, {})).__setitem__(
            item if field == "Status" else field, value)

    def after(self, item, prev):
        self.order.insert(self.order.index(prev) + 1 if prev else 0, item)


def test_bootstrap_is_idempotent_and_keeps_queue_order():
    gh, proj = FakeGH(labels=["bug"]), FakeProject()
    log = []
    r = L.bootstrap(gh, proj, TAX, ITEMS, log=log.append)
    assert r["created"] == len(ITEMS) and r["board"]["added"] == len(ITEMS)
    made = {c[2]["name"] for c in gh.calls if c[0] == "POST" and c[1].endswith("/labels")}
    assert made == set(L.labels_of(TAX))                                     # exactly the fixed set
    assert any("outside the fixed set" in x and "bug" in x for x in log)     # reported, never deleted
    assert not any(c[0] == "DELETE" for c in gh.calls)
    assert len({c[2]["title"] for c in gh.calls if c[1].endswith("/milestones")}) == 6
    assert proj.order == [f"item-I{100 + i}" for i in range(len(ITEMS))]      # the manifest's order
    lim = next(i for i, it in enumerate(ITEMS) if it["cls"] == "limitation")
    assert proj.status[f"item-I{100 + lim}"] == "Waiting on condition"
    assert proj.status["item-I100"] == "Queue" and proj.vals["item-I100"]["Track"] == ITEMS[0]["track"]
    dh = next(i for i, it in enumerate(ITEMS) if it["key"] == "dh-game2")
    assert "statsapi" in proj.vals[f"item-I{100 + dh}"]["Reopening condition"]
    body = gh.issues[dh]["body"]
    assert "<!-- ledger:dh-game2 -->" in body and "## Reopening condition" in body
    assert re.search(r"\]\(https://github\.com/o/r/blob/[0-9a-f]{40}/BACKLOG\.md#L\d+\)", body)
    # re-run: nothing new, no status reset
    proj.status["item-I100"] = "In progress"
    r2 = L.bootstrap(gh, proj, TAX, ITEMS, log=log.append)
    assert r2["created"] == 0 and r2["board"]["added"] == 0 and proj.status["item-I100"] == "In progress"
    # without the project token the repo side still completes
    assert L.bootstrap(FakeGH(), None, TAX, ITEMS, log=log.append)["board"]["project"] is None


def _iss(n, labels, body=""):
    return {"number": n, "node_id": f"I{n}", "labels": [{"name": x} for x in labels], "body": body}


def test_events_lint_route_and_close_rules():
    gh, proj = FakeGH(), FakeProject()
    got = L.handle(gh, proj, TAX, "issues", {"action": "opened", "issue": _iss(5, ["class:limitation", "bug"],
                                                                               "x\n## Reopening condition\nwhen Y\n")})
    assert "lint-comment" in got and proj.status["item-I5"] == "Waiting on condition"
    assert proj.vals["item-I5"]["Reopening condition"] == "when Y"
    comment = next(c for c in gh.calls if c[1].endswith("/5/comments"))[2]["body"]
    assert "not a block" in comment and "outside the fixed set: bug" in comment
    # a PR: title prefix -> label; Closes #6 -> In progress
    L.handle(gh, proj, TAX, "issues", {"action": "opened", "issue": _iss(6, ["track:K", "class:lane", "sport:all",
                                                                           "size:M"])})
    assert proj.status["item-I6"] == "Queue"
    got = L.handle(gh, proj, TAX, "pull_request", {"action": "opened", "pull_request": {
        "number": 9, "title": "[K3] floors", "body": "Closes #6", "labels": []}})
    assert got == ["labels:track:K", "#6:In progress"] and proj.status["item-I6"] == "In progress"
    # merged PR closes the limitation without "Resolves limitation": reopened, back to Waiting
    gh.closed = {"timelineItems": {"nodes": [{"closer": {"__typename": "PullRequest", "body": "Closes #5"}}]},
                 "comments": {"nodes": []}}
    got = L.handle(gh, proj, TAX, "issues", {"action": "closed", "issue": _iss(5, ["class:limitation"])})
    assert "reopened" in got and proj.status["item-I5"] == "Waiting on condition"
    assert ("PATCH", "repos/o/r/issues/5", {"state": "open"}) in gh.calls
    # a lane closed by its PR -> Done
    got = L.handle(gh, proj, TAX, "issues", {"action": "closed", "issue": _iss(6, ["class:lane"])})
    assert got == ["status:Done"] and proj.status["item-I6"] == "Done"
    # closed by hand without an architect quote -> reopened (rule 2)
    gh.closed = {"timelineItems": {"nodes": [{"closer": None}]}, "comments": {"nodes": [{"body": "done"}]}}
    assert "reopened" in L.handle(gh, proj, TAX, "issues", {"action": "closed", "issue": _iss(6, ["class:lane"])})


def test_workflow_wires_the_script():
    wf = (ROOT / ".github" / "workflows" / "ledger.yml").read_text()
    assert "scripts/ledger.py" in wf and "LEDGER_PROJECT_TOKEN" in wf and "workflow_dispatch" in wf
    for ev in ("issues:", "pull_request:"):
        assert ev in wf


class MergeGH:
    """Issues with labels/state; records writes."""
    repo = "o/r"

    def __init__(self, issues):
        self.issues, self.calls = issues, []

    def rest(self, method, path, body=None):
        self.calls.append((method, path, body))
        if method == "GET" and "/issues/" in path:
            n = int(path.rsplit("/", 1)[1])
            x = self.issues[n]
            return {"number": n, "node_id": f"I{n}", "state": x["state"],
                    "labels": [{"name": lab} for lab in x["labels"]]}
        if method == "GET" and "/pulls/" in path:
            return self.pr
        return {}


def test_merged_pr_closes_its_refs_itself_limitation_rule_kept():
    gh = MergeGH({111: {"state": "open", "labels": ["class:lane"]},
                  90: {"state": "open", "labels": ["class:finding"]},
                  96: {"state": "open", "labels": ["class:limitation"]},
                  109: {"state": "closed", "labels": ["class:finding"]}})
    proj = FakeProject()
    for n in (111, 90, 96):
        proj.add(f"I{n}")
    pr = {"number": 114, "merged": True, "merge_commit_sha": "0128299abc",
          "body": "Closes #111\nCloses #90\nCloses #96\nCloses #109"}
    got = L.handle(gh, proj, TAX, "pull_request", {"action": "closed", "pull_request": pr})
    assert got == ["#90:closed", "#90:Done", "#96:limitation kept open", "#109:already closed",
                   "#111:closed", "#111:Done"], got                          # closes_refs sorts the refs
    assert {c[1] for c in gh.calls if c[0] == "PATCH"} == {"repos/o/r/issues/90", "repos/o/r/issues/111"}
    assert proj.status["item-I111"] == "Done" and "item-I96" not in proj.status
    close = next(c for c in gh.calls if c[1] == "repos/o/r/issues/111" and c[0] == "PATCH")[2]
    assert close == {"state": "closed", "state_reason": "completed"}
    note = next(c[2]["body"] for c in gh.calls if c[1] == "repos/o/r/issues/111/comments")
    assert "Closed by #114 (merged as 0128299)" in note
def test_limitation_needs_the_phrase_and_unmerged_prs_close_nothing():
    gh = MergeGH({96: {"state": "open", "labels": ["class:limitation"]}})
    got = L.handle(gh, None, TAX, "pull_request", {"action": "closed", "pull_request": {
        "number": 5, "merged": True, "body": "Closes #96"}})
    assert got == ["#96:limitation kept open"] and not any(c[0] == "PATCH" for c in gh.calls)
    assert "Resolves limitation" in next(c[2]["body"] for c in gh.calls if c[0] == "POST")
    gh2 = MergeGH({96: {"state": "open", "labels": ["class:limitation"]}})
    got = L.handle(gh2, None, TAX, "pull_request", {"action": "closed", "pull_request": {
        "number": 6, "merged": True, "body": "Closes #96. Resolves limitation."}})
    assert got == ["#96:closed"]
    gh3 = MergeGH({111: {"state": "open", "labels": ["class:lane"]}})
    assert L.handle(gh3, None, TAX, "pull_request", {"action": "closed", "pull_request": {
        "number": 7, "merged": False, "body": "Closes #111"}}) == [] and gh3.calls == []


def test_close_merged_replay_refuses_an_unmerged_pr(monkeypatch, capsys):
    gh = MergeGH({})
    gh.pr = {"number": 8, "merged": False, "body": "Closes #1"}
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.delenv("LEDGER_PROJECT_TOKEN", raising=False)
    monkeypatch.setattr(L, "GH", lambda token, repo: gh)
    assert L.main(["close-merged", "8"]) == 1 and "not merged" in capsys.readouterr().out
    wf = (ROOT / ".github" / "workflows" / "ledger.yml").read_text()
    assert "closed]" in wf and '"$LEDGER_MODE" "$LEDGER_PR"' in wf and "${{ inputs.pr }}\n" not in wf.split("run:")[-1]
