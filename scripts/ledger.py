"""
THE LEDGER (architect, 2026-09-29): GitHub Issues are the STATE ledger,
BACKLOG.md stays the append-only HISTORY, and ONE Project (v2) is the queue's
single source of ORDER. Taxonomy: .github/ledger/taxonomy.json (fixed set,
prefixed, no ad-hoc labels). Rules: docs/LEDGER.md.

Run by .github/workflows/ledger.yml:

    python scripts/ledger.py bootstrap     # workflow_dispatch: idempotent
    python scripts/ledger.py event         # issues / pull_request events

bootstrap: ensure the taxonomy's labels and milestones, open every
.github/ledger/backfill.json item as an Issue (idempotent: each body carries
<!-- ledger:KEY -->), and, when LEDGER_PROJECT_TOKEN is set, ensure the board
(Status columns, Track / Class / Sport / Reopening condition / Due date
fields) and add the items in manifest order. A user-owned Project cannot be
reached with the workflow's GITHUB_TOKEN; without the token the board steps
are skipped and say so. Saved views cannot be created by the API: the six are
specified in docs/LEDGER.md.

event:
  issues.opened          label lint (exactly one track: / class: / sport: /
                         size:; unknown labels) -> a bot comment, never a block;
                         the card joins Queue, or Waiting on condition for
                         class:limitation.
  issues.labeled/...     board fields follow the labels; class:limitation
                         routes a Queue card to Waiting on condition.
  issues.closed          closed by a PR or commit -> Done, EXCEPT a
                         class:limitation Issue whose closing PR body lacks
                         "Resolves limitation" (reopened, Waiting). Closed by
                         hand -> reopened, unless its last comment quotes an
                         ARCHITECT ruling (rule 2).
  pull_request.opened... title prefix "[K2] ..." -> track:K on the PR;
                         "Closes #N" -> card N moves to In progress.

Standard library only (no dependency for a CI job).
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAXONOMY = ROOT / ".github" / "ledger" / "taxonomy.json"
BACKFILL = ROOT / ".github" / "ledger" / "backfill.json"
DIMENSIONS = ("track", "class", "sport", "size")
# "Closes #N" LINES only (ruling 2026-09-30): the keyword starts the line (after
# optional whitespace, a list marker, or the PR template's "Ledger:"), then one
# or more refs ("Closes #1, #2 and #3"). Prose like "...which closes #111..."
# never counts: #116's own description did that and closed #111 under the
# wrong PR's name.
CLOSES = re.compile(r"^[ \t]*(?:[-*][ \t]+)?(?:ledger:[ \t]*)?(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)"
                    r"[ \t]*:?[ \t]+((?:#\d+\b(?:[ \t]*(?:,|and)[ \t]*)?)+)", re.I | re.M)
RESOLVES_LIMITATION = re.compile(r"\bresolves\s+limitation\b", re.I)
# GitHub's OWN closing-keyword detection (LEDGER rule 5): a keyword then an Issue
# ref ANYWHERE in a PR body, even after a "not". #273, #274 and #275 each wrote
# a negated "does not <keyword> #N" and GitHub closed #85, #211 and #276 on merge
# (2026-10-05). Only refs inside a declared closure line (CLOSES) may follow one.
GH_CLOSING = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b[ \t]*:?[ \t]*"
                        r"(?:https?://github\.com/[\w.-]+/[\w.-]+/issues/\d+|(?:[\w.-]+/[\w.-]+)?#\d+)", re.I)
ARCHITECT_QUOTE = re.compile(r"\bARCHITECT\b")
MARKER = "<!-- ledger:{} -->"


def load(path=TAXONOMY) -> dict:
    return json.loads(Path(path).read_text())


# ------------------------------------------------------------- pure rules --

def labels_of(tax: dict) -> dict:
    """Every ruled label -> (color, description)."""
    out = {}
    for dim, spec in tax["dimensions"].items():
        for v, desc in spec["values"].items():
            out[f"{dim}:{v}"] = (spec["color"], desc)
    for name, spec in tax["flags"].items():
        out[name] = (spec["color"], spec["description"])
    return out


def lint(labels: list[str], tax: dict) -> list[str]:
    """Hygiene: exactly one of each dimension; nothing outside the fixed set."""
    ruled = labels_of(tax)
    problems = []
    for dim in DIMENSIONS:
        got = sorted(x for x in labels if x.startswith(f"{dim}:"))
        if len(got) != 1:
            problems.append(f"needs exactly one `{dim}:` label (has {len(got)}"
                            + (f": {', '.join(got)}" if got else "") + ")")
    ad_hoc = sorted(x for x in labels if x not in ruled)
    if ad_hoc:
        problems.append(f"labels outside the fixed set: {', '.join(ad_hoc)}")
    return problems


def prefix_labels(title: str, tax: dict) -> list[str]:
    """A PR title prefix like "[K2] ..." or "[ops] ..." -> its track label."""
    m = re.match(r"\s*\[([A-Za-z]+)\d*[a-z]?\]", title or "")
    if not m:
        return []
    lab = tax["title_prefix"].get(m.group(1).upper())
    return [lab] if lab else []


def closes_refs(body: str) -> list[int]:
    return sorted({int(n) for refs in CLOSES.findall(body or "") for n in re.findall(r"#(\d+)", refs)})


def stray_closing_refs(body: str) -> list[str]:
    """PR-body lint (operator review, 2026-10-05): every closing keyword + Issue
    ref that is NOT part of a declared closure line ("Closes #N" starting the
    line). GitHub would close those Issues on merge; mention them as `Refs #N`."""
    body = body or ""
    declared = set()
    for m in CLOSES.finditer(body):
        lead = GH_CLOSING.search(body, m.start(), m.end())
        if lead:
            declared.add(lead.start())
    return [f"line {body.count(chr(10), 0, m.start()) + 1}: {m.group(0)!r}"
            for m in GH_CLOSING.finditer(body) if m.start() not in declared]


def resolves_limitation(body: str) -> bool:
    return bool(RESOLVES_LIMITATION.search(body or ""))


def reopening_condition(body: str) -> str | None:
    m = re.search(r"^## Reopening condition\s*\n(.*?)(?=^## |\Z)", body or "", re.M | re.S)
    return m.group(1).strip() if m else None


def item_labels(it: dict) -> list[str]:
    return [f"track:{it['track']}", f"class:{it['cls']}", f"sport:{it['sport']}", f"size:{it['size']}",
            *it.get("flags", [])]


def issue_body(it: dict, repo: str) -> str:
    b = it["backlog"]
    link = f"https://github.com/{repo}/blob/{b['commit']}/BACKLOG.md#L{b['line']}"
    parts = [MARKER.format(it["key"]),
             f"**Class:** {it['cls']} · **Track:** {it['track']} · **Sport:** {it['sport']} · **Size:** {it['size']}",
             "", it["summary"], ""]
    if it.get("reopening"):
        parts += ["## Reopening condition", it["reopening"], ""]
    if it.get("due"):
        parts += [f"**Due:** {it['due']}", ""]
    parts += ["## BACKLOG entry", f"[{b['heading']}]({link}) (commit `{b['commit'][:7]}`, line {b['line']})", "",
              "_Opened by the ledger bootstrap (architect ruling 2026-09-29: Issues are the state ledger, "
              "BACKLOG.md the history)._"]
    return "\n".join(parts)


def initial_status(labels: list[str]) -> str:
    return "Waiting on condition" if "class:limitation" in labels else "Queue"


def closed_verdict(labels: list[str], closer: dict | None, last_comment: str | None) -> tuple[str, str]:
    """What an issues.closed event means. closer: {"type": "PullRequest"|"Commit"|..., "body": str}.
    Returns (action, reason): action in {"done", "reopen"}."""
    kind = (closer or {}).get("type")
    if kind in ("PullRequest", "Commit"):
        if "class:limitation" in labels and not resolves_limitation((closer or {}).get("body")):
            return "reopen", ("a merged change touched this limitation without \"Resolves limitation\" in its "
                              "description, so the Issue stays open (ledger rule)")
        return "done", "closed by a linked change"
    if ARCHITECT_QUOTE.search(last_comment or ""):
        return "done", "closed with an architect ruling quoted"
    return "reopen", ("an Issue never closes by hand without a linked PR or an architect ruling quoted in the "
                      "closing comment (ledger rule 2)")


# --------------------------------------------------------------- the wire --

class GH:
    def __init__(self, token: str, repo: str, api: str = "https://api.github.com"):
        self.token, self.repo, self.api = token, repo, api.rstrip("/")

    def _req(self, method: str, url: str, body=None):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "sports-predictor-ledger"})
        try:
            with urllib.request.urlopen(r, timeout=30) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{method} {url}: HTTP {e.code} {e.read()[:300]!r}") from e
        return json.loads(raw) if raw else None

    def rest(self, method: str, path: str, body=None):
        return self._req(method, f"{self.api}/{path.lstrip('/')}", body)

    def paged(self, path: str) -> list:
        out, page = [], 1
        while True:
            sep = "&" if "?" in path else "?"
            got = self.rest("GET", f"{path}{sep}per_page=100&page={page}") or []
            out += got
            if len(got) < 100:
                return out
            page += 1

    def graphql(self, query: str, variables: dict | None = None) -> dict:
        r = self._req("POST", f"{self.api}/graphql", {"query": query, "variables": variables or {}})
        if r.get("errors"):
            raise RuntimeError(f"GraphQL: {r['errors']}")
        return r["data"]


class Project:
    """The one board. All GraphQL lives here (tests fake this class)."""

    def __init__(self, gh: GH, owner: str, title: str):
        self.gh, self.owner, self.title = gh, owner, title
        self.id = None
        self.fields: dict = {}

    def ensure(self, repo_node_id: str, tax: dict) -> bool:
        d = self.gh.graphql("query($l:String!){user(login:$l){id projectsV2(first:100){nodes{id title}}}}",
                            {"l": self.owner})["user"]
        hit = [p for p in d["projectsV2"]["nodes"] if p["title"] == self.title]
        created = not hit
        if hit:
            self.id = hit[0]["id"]
        else:
            self.id = self.gh.graphql(
                "mutation($o:ID!,$t:String!,$r:ID!){createProjectV2(input:{ownerId:$o,title:$t,repositoryId:$r})"
                "{projectV2{id}}}", {"o": d["id"], "t": self.title, "r": repo_node_id}
            )["createProjectV2"]["projectV2"]["id"]
        self._fields()
        p = tax["project"]
        want = {p["status_field"]: p["statuses"], **p["single_select"]}
        for name, options in want.items():
            f = self.fields.get(name)
            opts = [{"name": o, "color": "GRAY", "description": ""} for o in options]
            if f is None:
                self.gh.graphql("mutation($p:ID!,$n:String!,$o:[ProjectV2SingleSelectFieldOptionInput!]){"
                                "createProjectV2Field(input:{projectId:$p,dataType:SINGLE_SELECT,name:$n,"
                                "singleSelectOptions:$o}){projectV2Field{... on ProjectV2SingleSelectField{id}}}}",
                                {"p": self.id, "n": name, "o": opts})
            elif [o["name"] for o in f.get("options", [])] != options:
                self.gh.graphql("mutation($f:ID!,$o:[ProjectV2SingleSelectFieldOptionInput!]){"
                                "updateProjectV2Field(input:{fieldId:$f,singleSelectOptions:$o})"
                                "{projectV2Field{... on ProjectV2SingleSelectField{id}}}}", {"f": f["id"], "o": opts})
        for kind, names in (("TEXT", p["text"]), ("DATE", p["date"])):
            for name in names:
                if name not in self.fields:
                    self.gh.graphql("mutation($p:ID!,$n:String!,$k:ProjectV2CustomFieldType!){createProjectV2Field("
                                    "input:{projectId:$p,dataType:$k,name:$n}){projectV2Field{... on ProjectV2Field{id}}}}",
                                    {"p": self.id, "n": name, "k": kind})
        self._fields()
        return created

    def _fields(self):
        nodes = self.gh.graphql(
            "query($p:ID!){node(id:$p){... on ProjectV2{fields(first:50){nodes{"
            "... on ProjectV2FieldCommon{id name} ... on ProjectV2SingleSelectField{id name options{id name}}}}}}}",
            {"p": self.id})["node"]["fields"]["nodes"]
        self.fields = {n["name"]: n for n in nodes if n}

    def find(self, content_id: str) -> tuple[str | None, str | None]:
        """(item id, Status) of an Issue/PR on this board, else (None, None)."""
        nodes = self.gh.graphql(
            "query($c:ID!){node(id:$c){... on Issue{projectItems(first:20){nodes{id project{id} "
            "fieldValueByName(name:\"Status\"){... on ProjectV2ItemFieldSingleSelectValue{name}}}}}}}",
            {"c": content_id})["node"]["projectItems"]["nodes"]
        for n in nodes:
            if n["project"]["id"] == self.id:
                return n["id"], (n.get("fieldValueByName") or {}).get("name")
        return None, None

    def add(self, content_id: str) -> str:
        return self.gh.graphql("mutation($p:ID!,$c:ID!){addProjectV2ItemById(input:{projectId:$p,contentId:$c})"
                               "{item{id}}}", {"p": self.id, "c": content_id})["addProjectV2ItemById"]["item"]["id"]

    def set(self, item: str, field: str, value) -> None:
        f = self.fields[field]
        if "options" in f:
            opt = next(o["id"] for o in f["options"] if o["name"] == value)
            v = {"singleSelectOptionId": opt}
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value)):
            v = {"date": value}
        else:
            v = {"text": value}
        self.gh.graphql("mutation($p:ID!,$i:ID!,$f:ID!,$v:ProjectV2FieldValue!){updateProjectV2ItemFieldValue("
                        "input:{projectId:$p,itemId:$i,fieldId:$f,value:$v}){projectV2Item{id}}}",
                        {"p": self.id, "i": item, "f": f["id"], "v": v})

    def after(self, item: str, prev: str | None) -> None:
        self.gh.graphql("mutation($p:ID!,$i:ID!,$a:ID){updateProjectV2ItemPosition(input:{projectId:$p,itemId:$i,"
                        "afterId:$a}){items(first:1){nodes{id}}}}", {"p": self.id, "i": item, "a": prev})


def sync_fields(proj: Project, item: str, labels: list[str], body: str | None) -> None:
    for dim, field in (("track", "Track"), ("class", "Class"), ("sport", "Sport")):
        vals = [x.split(":", 1)[1] for x in labels if x.startswith(f"{dim}:")]
        if len(vals) == 1 and field in proj.fields:
            proj.set(item, field, vals[0])
    rc = reopening_condition(body)
    if rc and "Reopening condition" in proj.fields:
        proj.set(item, "Reopening condition", rc[:1000])
    due = re.search(r"^\*\*Due:\*\* (\d{4}-\d{2}-\d{2})", body or "", re.M)
    if due and "Due date" in proj.fields:
        proj.set(item, "Due date", due.group(1))


# ---------------------------------------------------------------- bootstrap --

def bootstrap(gh: GH, proj: Project | None, tax: dict, items: list[dict], log=print) -> dict:
    repo = gh.repo
    have = {x["name"]: x for x in gh.paged(f"repos/{repo}/labels")}
    for name, (color, desc) in labels_of(tax).items():
        if name not in have:
            gh.rest("POST", f"repos/{repo}/labels", {"name": name, "color": color, "description": desc})
            log(f"+ label {name}")
        elif have[name].get("color") != color or (have[name].get("description") or "") != desc:
            gh.rest("PATCH", f"repos/{repo}/labels/{name.replace(':', '%3A')}", {"color": color, "description": desc})
    ad_hoc = sorted(set(have) - set(labels_of(tax)))
    if ad_hoc:
        log(f"· labels outside the fixed set (left alone, not deleted): {ad_hoc}")
    ms = {m["title"]: m["number"] for m in gh.paged(f"repos/{repo}/milestones?state=all")}
    for m in tax["milestones"]:
        if m["title"] not in ms:
            body = {"title": m["title"], "description": m["description"]}
            if m.get("due_on"):
                body["due_on"] = f"{m['due_on']}T23:59:59Z"
            ms[m["title"]] = gh.rest("POST", f"repos/{repo}/milestones", body)["number"]
            log(f"+ milestone {m['title']}")
    existing = {}
    for x in gh.paged(f"repos/{repo}/issues?state=all"):
        if "pull_request" in x:
            continue
        k = re.search(r"<!-- ledger:([\w.-]+) -->", x.get("body") or "")
        if k:
            existing[k.group(1)] = x
    issues, created = [], 0
    for it in items:
        problems = lint(item_labels(it), tax)
        if problems:
            raise SystemExit(f"✗ manifest item {it['key']}: {problems}")
        x = existing.get(it["key"])
        if x is None:
            body = {"title": it["title"], "body": issue_body(it, repo), "labels": item_labels(it)}
            if it.get("milestone"):
                body["milestone"] = ms[it["milestone"]]
            x = gh.rest("POST", f"repos/{repo}/issues", body)
            created += 1
            log(f"+ #{x['number']} {it['title']}")
        issues.append((it, x))
    board = {"project": None, "added": 0}
    if proj is None:
        log("· LEDGER_PROJECT_TOKEN not set: board steps skipped (a user-owned Project needs a project-scoped "
            "token; see docs/LEDGER.md)")
        return {"issues": [x["number"] for _, x in issues], "created": created, "milestones": ms, "board": board}
    repo_id = gh.graphql("query($o:String!,$n:String!){repository(owner:$o,name:$n){id}}",
                         dict(zip(("o", "n"), repo.split("/"))))["repository"]["id"]
    board["project"] = "created" if proj.ensure(repo_id, tax) else "existing"
    prev = None
    for it, x in issues:
        item, status = proj.find(x["node_id"])
        if item is None:
            item = proj.add(x["node_id"])
            proj.after(item, prev)                      # manifest order = the backfilled queue order
            board["added"] += 1
        if status is None:
            proj.set(item, "Status", initial_status(item_labels(it)))
        sync_fields(proj, item, item_labels(it), issue_body(it, repo))
        prev = item
    return {"issues": [x["number"] for _, x in issues], "created": created, "milestones": ms, "board": board}


# ------------------------------------------------------------------- events --

def handle(gh: GH, proj: Project | None, tax: dict, name: str, ev: dict, log=print) -> list[str]:
    done = []
    repo = gh.repo
    if name == "issues":
        iss = ev["issue"]
        labels = [x["name"] for x in iss.get("labels", [])]
        action = ev.get("action")
        if action == "opened":
            problems = lint(labels, tax)
            if problems:
                gh.rest("POST", f"repos/{repo}/issues/{iss['number']}/comments", {"body": (
                    "Ledger label lint (not a block):\n" + "\n".join(f"- {p}" for p in problems)
                    + "\n\nEvery Issue carries exactly one `track:`, one `class:`, one `sport:` and one `size:` "
                      "label from the fixed set (docs/LEDGER.md).\n\n---\n_ledger bot_")})
                done.append("lint-comment")
        if action == "closed":
            q = gh.graphql(
                "query($o:String!,$n:String!,$i:Int!){repository(owner:$o,name:$n){issue(number:$i){"
                "timelineItems(last:1,itemTypes:[CLOSED_EVENT]){nodes{... on ClosedEvent{closer{__typename "
                "... on PullRequest{body}}}}} comments(last:1){nodes{body}}}}}",
                {"o": repo.split("/")[0], "n": repo.split("/")[1], "i": iss["number"]})["repository"]["issue"]
            ev_nodes = q["timelineItems"]["nodes"]
            closer = (ev_nodes[-1].get("closer") if ev_nodes else None) or {}
            closer = {"type": closer.get("__typename"), "body": closer.get("body")} if closer else None
            last = (q["comments"]["nodes"] or [{}])[-1].get("body")
            verdict, reason = closed_verdict(labels, closer, last)
            if verdict == "reopen":
                gh.rest("PATCH", f"repos/{repo}/issues/{iss['number']}", {"state": "open"})
                gh.rest("POST", f"repos/{repo}/issues/{iss['number']}/comments",
                        {"body": f"Reopened: {reason}.\n\n---\n_ledger bot_"})
                done.append("reopened")
            if proj is not None:
                item, _ = proj.find(iss["node_id"])
                if item is not None:
                    proj.set(item, "Status", "Done" if verdict == "done" else initial_status(labels))
                    done.append(f"status:{'Done' if verdict == 'done' else initial_status(labels)}")
            return done
        if proj is not None and action in ("opened", "labeled", "unlabeled", "reopened", "edited"):
            item, status = proj.find(iss["node_id"])
            if item is None:
                item = proj.add(iss["node_id"])
                status = None
            if status is None or (status == "Queue" and "class:limitation" in labels):
                proj.set(item, "Status", initial_status(labels))
                done.append(f"status:{initial_status(labels)}")
            sync_fields(proj, item, labels, iss.get("body"))
    elif name == "pull_request":
        pr = ev["pull_request"]
        if ev.get("action") == "closed" and pr.get("merged"):
            return close_on_merge(gh, proj, repo, pr)
        if ev.get("action") in ("opened", "edited", "reopened"):
            want = prefix_labels(pr.get("title"), tax)
            have = {x["name"] for x in pr.get("labels", [])}
            if want and not set(want) <= have:
                gh.rest("POST", f"repos/{repo}/issues/{pr['number']}/labels", {"labels": want})
                done.append(f"labels:{','.join(want)}")
            if proj is not None:
                for n in closes_refs(pr.get("body")):
                    iss = gh.rest("GET", f"repos/{repo}/issues/{n}")
                    if "pull_request" in iss or iss.get("state") != "open":
                        continue
                    item, status = proj.find(iss["node_id"])
                    if item is None:
                        item = proj.add(iss["node_id"])
                    if status != "Done":
                        proj.set(item, "Status", "In progress")
                        done.append(f"#{n}:In progress")
    return done


def _board(proj):
    if proj is None:
        return None
    d = proj.gh.graphql("query($l:String!){user(login:$l){projectsV2(first:100){nodes{id title}}}}",
                        {"l": proj.owner})["user"]["projectsV2"]["nodes"]
    hit = [p["id"] for p in d if p["title"] == proj.title]
    if not hit:
        print("· board not bootstrapped yet: board steps skipped")
        return None
    proj.id = hit[0]
    proj._fields()
    return proj


def close_on_merge(gh: GH, proj: "Project | None", repo: str, pr: dict) -> list[str]:
    """AUTO-CLOSE (architect ruling 2026-09-30): GitHub did not register the
    "Closes #N" links of PRs opened through the Claude connection (#110, #114),
    so the bot closes them itself when the PR MERGES. An ordinary Issue closes
    (completed) and its card goes to Done. A class:limitation Issue closes only
    when the PR body says "Resolves limitation"; otherwise it stays open and
    Waiting. The bot's own close uses GITHUB_TOKEN, which starts no workflow,
    so the manual-close guard (issues.closed) is untouched for human closes."""
    done = []
    body = pr.get("body") or ""
    for n in closes_refs(body):
        iss = gh.rest("GET", f"repos/{repo}/issues/{n}")
        if "pull_request" in iss:
            continue
        labels = [x["name"] for x in iss.get("labels", [])]
        if iss.get("state") != "open":
            done.append(f"#{n}:already closed")
            continue
        if "class:limitation" in labels and not resolves_limitation(body):
            gh.rest("POST", f"repos/{repo}/issues/{n}/comments", {"body": (
                f"#{pr['number']} merged and references this limitation, but its description does not say "
                "\"Resolves limitation\", so it stays open (ledger rule).\n\n---\n_ledger bot_")})
            done.append(f"#{n}:limitation kept open")
            continue
        gh.rest("POST", f"repos/{repo}/issues/{n}/comments", {"body": (
            f"Closed by #{pr['number']} (merged{' as ' + pr['merge_commit_sha'][:7] if pr.get('merge_commit_sha') else ''}).\n\n---\n_ledger bot_")})
        gh.rest("PATCH", f"repos/{repo}/issues/{n}", {"state": "closed", "state_reason": "completed"})
        done.append(f"#{n}:closed")
        if proj is not None:
            item, _ = proj.find(iss["node_id"])
            if item is not None:
                proj.set(item, "Status", "Done")
                done.append(f"#{n}:Done")
    return done


# ----------------------------------------------------------- discussions --
# ARCHITECT 2026-10-01: Discussions posting runs INSIDE the ledger workflow,
# with the LEDGER_PROJECT_TOKEN secret (classic PAT; repo scope, plus
# write:discussion if a call is refused: the operator edits the token's
# scopes and never pastes it). workflow_dispatch mode "discussions":
#   list   the categories (the receipt) + the threads' number/title/url/category
#          (metadata only: the fence holds, a thread's BODY is never read here)
#   post   a thread from ONE markdown file under docs/discussions/ ("# Title"
#          first line, the rest is the body) into a NAMED existing category
#   reply  to a thread by NUMBER, the body from a file under docs/discussions/
# Nothing posts without a dispatch that names the file (and the category or the
# thread). The default action is list. Threads are input, never rulings.

DISCUSSIONS_DIR = ROOT / "docs" / "discussions"
SCOPE_HINT = ("the token was refused: add the write:discussion scope to the LEDGER_PROJECT_TOKEN classic PAT "
              "(the operator edits the token's scopes in GitHub settings; never paste the token anywhere)")


def discussion_file(path: str) -> tuple[str, str, str]:
    """(relative path, title, body) of a post file. Refuses anything outside
    docs/discussions/, non-markdown, or without a '# Title' first line."""
    if not path:
        raise ValueError("no file named: a post/reply dispatch must name a file under docs/discussions/")
    f = (ROOT / path).resolve()
    if DISCUSSIONS_DIR.resolve() not in f.parents or f.suffix != ".md" or not f.is_file():
        raise ValueError(f"refused: {path!r} is not a markdown file under docs/discussions/")
    text = f.read_text()
    first, _, rest = text.lstrip("\n").partition("\n")
    if first.startswith("# "):
        return str(f.relative_to(ROOT)), first[2:].strip(), rest.strip()
    return str(f.relative_to(ROOT)), "", text.strip()          # no title: the whole file is the body


def _repo_discussions(gh, repo: str) -> dict:
    owner, name = repo.split("/")
    return gh.graphql("query($o:String!,$n:String!){repository(owner:$o,name:$n){id hasDiscussionsEnabled "
                      "discussionCategories(first:50){nodes{id name slug isAnswerable description}} "
                      "discussions(first:100,orderBy:{field:CREATED_AT,direction:ASC}){nodes{id number title url "
                      "category{name}}}}}", {"o": owner, "n": name})["repository"]


def discussions(gh, repo: str, action: str, path: str = "", category: str = "", thread: str = "",
                sha: str = "", log=print) -> dict:
    action = (action or "list").strip().lower()
    try:
        r = _repo_discussions(gh, repo)
    except RuntimeError as e:
        log(f"✗ {e}")
        log(f"✗ {SCOPE_HINT}")
        return {"action": action, "error": "token refused"}
    cats = r["discussionCategories"]["nodes"]
    threads = r["discussions"]["nodes"]
    if action == "list":
        out = {"action": "list", "enabled": r["hasDiscussionsEnabled"],
               "categories": [{"name": c["name"], "slug": c["slug"], "answerable": c["isAnswerable"],
                               "description": c["description"]} for c in cats],
               "threads": [{"number": t["number"], "title": t["title"], "url": t["url"],
                            "category": (t.get("category") or {}).get("name")} for t in threads]}
        for c in out["categories"]:
            log(f"  category {c['name']!r} ({c['slug']}{', Q&A' if c['answerable'] else ''}): {c['description']}")
        for t in out["threads"]:
            log(f"  #{t['number']} [{t['category']}] {t['title']} — {t['url']}")
        return out
    try:
        rel, title, body = discussion_file(path)
    except ValueError as e:
        log(f"✗ {e}")
        return {"action": action, "error": str(e)}
    prov = f"\n\n---\n_Posted by the ledger workflow from `{rel}`" + (f" @ {sha[:7]}" if sha else "") + "._"
    if action == "post":
        cat = next((c for c in cats if c["name"].lower() == (category or "").strip().lower()), None)
        if cat is None:
            msg = f"refused: category {category!r} not found (have: {', '.join(c['name'] for c in cats) or 'none'})"
            log(f"✗ {msg}")
            return {"action": "post", "error": msg}
        if not title:
            msg = f"refused: {rel} has no '# Title' first line"
            log(f"✗ {msg}")
            return {"action": "post", "error": msg}
        dup = next((t for t in threads if t["title"] == title and (t.get("category") or {}).get("name") == cat["name"]),
                   None)
        if dup:
            msg = f"refused: already posted as #{dup['number']} ({dup['url']})"
            log(f"✗ {msg}")
            return {"action": "post", "error": msg}
        try:
            d = gh.graphql("mutation($r:ID!,$c:ID!,$t:String!,$b:String!){createDiscussion(input:{repositoryId:$r,"
                           "categoryId:$c,title:$t,body:$b}){discussion{number url}}}",
                           {"r": r["id"], "c": cat["id"], "t": title, "b": body + prov})["createDiscussion"]["discussion"]
        except RuntimeError as e:
            log(f"✗ {e}")
            log(f"✗ {SCOPE_HINT}")
            return {"action": "post", "error": "token refused"}
        log(f"✓ posted #{d['number']} [{cat['name']}] {title} — {d['url']}")
        return {"action": "post", "number": d["number"], "url": d["url"], "category": cat["name"], "file": rel}
    if action == "reply":
        t = next((t for t in threads if str(t["number"]) == str(thread).strip()), None) if str(thread).strip() else None
        if t is None:
            msg = f"refused: thread {thread!r} not found"
            log(f"✗ {msg}")
            return {"action": "reply", "error": msg}
        text = (f"# {title}\n\n" if title else "") + body
        try:
            c = gh.graphql("mutation($d:ID!,$b:String!){addDiscussionComment(input:{discussionId:$d,body:$b})"
                           "{comment{url}}}", {"d": t["id"], "b": text + prov})["addDiscussionComment"]["comment"]
        except RuntimeError as e:
            log(f"✗ {e}")
            log(f"✗ {SCOPE_HINT}")
            return {"action": "reply", "error": "token refused"}
        log(f"✓ replied on #{t['number']} — {c['url']}")
        return {"action": "reply", "number": t["number"], "url": c["url"], "file": rel}
    msg = f"refused: unknown action {action!r} (list | post | reply)"
    log(f"✗ {msg}")
    return {"action": action, "error": msg}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    mode = argv[0] if argv else "event"
    if mode in ("compile", "check-fragments", "pending"):   # ARCHITECT-RULE 2026-10-02: per-PR fragments
        sys.path.insert(0, str(Path(__file__).resolve().parent))   # local and offline: no token needed
        import ledger_fragments
        return ledger_fragments.main(argv)
    if mode == "check-body":                     # LEDGER rule 5, enforced: offline, body via env
        stray = stray_closing_refs(os.environ.get("PR_BODY", ""))
        if stray:
            print("✗ REFUSED: closing keyword + Issue ref outside a declared closure line. GitHub closes "
                  "these on merge even after a \"not\" (LEDGER rule 5). Mention a still-open Issue as "
                  "`Refs #N` (e.g. \"Outstanding work remains on #N\"); declare a real close on its own "
                  "line starting `Closes #N`.")
            for x in stray:
                print(f"  {x}")
            return 1
        print(f"✓ PR body: closing refs only on declared closure lines {closes_refs(os.environ.get('PR_BODY', ''))}")
        return 0
    tax = load()
    repo = os.environ["GITHUB_REPOSITORY"]
    gh = GH(os.environ["GITHUB_TOKEN"], repo)
    ptok = os.environ.get("LEDGER_PROJECT_TOKEN")
    proj = Project(GH(ptok, repo), repo.split("/")[0], tax["project"]["title"]) if ptok else None
    if mode == "close-merged":                  # replay: python scripts/ledger.py close-merged <PR>
        pr = gh.rest("GET", f"repos/{repo}/pulls/{int(argv[1])}")
        if not pr.get("merged"):
            print(f"✗ PR #{argv[1]} is not merged: nothing closed")
            return 1
        proj = _board(proj)
        print("LEDGER-CLOSE-MERGED", close_on_merge(gh, proj, repo, pr))
        return 0
    if mode == "discussions":                    # ARCHITECT 2026-10-01: the Discussions channel
        if not ptok:
            print("✗ LEDGER_PROJECT_TOKEN not set: the discussions mode needs it (classic PAT, repo scope)")
            return 1
        e = os.environ
        r = discussions(GH(ptok, repo), repo, e.get("LEDGER_D_ACTION", "list"), e.get("LEDGER_D_FILE", ""),
                        e.get("LEDGER_D_CATEGORY", ""), e.get("LEDGER_D_THREAD", ""), e.get("GITHUB_SHA", ""))
        print(f"LEDGER-DISCUSSIONS {json.dumps(r, sort_keys=True)}")
        return 1 if r.get("error") else 0
    if mode == "bootstrap":
        items = json.loads(BACKFILL.read_text())["items"]
        r = bootstrap(gh, proj, tax, items)
        print(f"LEDGER-BOOTSTRAP {json.dumps(r, sort_keys=True)}")
        return 0
    proj = _board(proj)
    ev = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    print("LEDGER-EVENT", handle(gh, proj, tax, os.environ["GITHUB_EVENT_NAME"], ev))
    return 0


if __name__ == "__main__":
    sys.exit(main())
