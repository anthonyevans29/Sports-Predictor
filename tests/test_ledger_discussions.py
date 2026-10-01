"""Discussions in the ledger workflow (ARCHITECT 2026-10-01): mode
"discussions" with LEDGER_PROJECT_TOKEN — list (the receipt), post a file from
docs/discussions/ into a NAMED category, reply by thread number. Nothing posts
without a dispatch naming the file; the default action is list; a refused
token prints the scope hint (never the token)."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ledger", ROOT / "scripts" / "ledger.py")
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)

CATS = [{"id": "C1", "name": "Q&A", "slug": "q-a", "isAnswerable": True, "description": "has anyone seen X"},
        {"id": "C4", "name": "Receipts", "slug": "receipts", "isAnswerable": False, "description": "verdicts"}]
THREADS = [{"id": "D1", "number": 197, "title": "NHL information floor", "url": "https://x/discussions/197",
            "category": {"name": "Q&A"}}]


class FakeGH:
    def __init__(self, refuse=False):
        self.calls, self.refuse = [], refuse

    def graphql(self, q, v=None):
        self.calls.append((q, v))
        if self.refuse:
            raise RuntimeError("GraphQL: [{'type': 'FORBIDDEN', 'message': 'Resource not accessible'}]")
        if q.startswith("query"):
            return {"repository": {"id": "R1", "hasDiscussionsEnabled": True,
                                   "discussionCategories": {"nodes": CATS}, "discussions": {"nodes": THREADS}}}
        if "createDiscussion" in q:
            return {"createDiscussion": {"discussion": {"number": 201, "url": "https://x/discussions/201"}}}
        return {"addDiscussionComment": {"comment": {"url": "https://x/discussions/197#c1"}}}


def post_file(tmp_name="t_post.md", text="# A receipt\n\nbody line\n"):
    p = L.DISCUSSIONS_DIR / tmp_name
    p.write_text(text)
    return p


def test_list_is_the_default_and_reads_metadata_only():
    gh, out = FakeGH(), []
    r = L.discussions(gh, "o/r", "", log=out.append)
    assert r["action"] == "list" and r["enabled"] and [c["name"] for c in r["categories"]] == ["Q&A", "Receipts"]
    assert r["threads"] == [{"number": 197, "title": "NHL information floor", "url": "https://x/discussions/197",
                             "category": "Q&A"}]
    assert len(gh.calls) == 1 and "body" not in gh.calls[0][0]                  # no thread body is read
    assert any("#197 [Q&A]" in x for x in out)


def test_post_refusals_and_post():
    p = post_file()
    try:
        rel = str(p.relative_to(ROOT))
        assert "not a markdown file under docs/discussions/" in L.discussions(FakeGH(), "o/r", "post", "README.md",
                                                                             "Receipts", log=lambda *_: 0)["error"]
        assert "not a markdown file" in L.discussions(FakeGH(), "o/r", "post", "docs/discussions/../../README.md",
                                                     "Receipts", log=lambda *_: 0)["error"]
        assert "no file named" in L.discussions(FakeGH(), "o/r", "post", "", "Receipts", log=lambda *_: 0)["error"]
        assert "category 'Ideas' not found" in L.discussions(FakeGH(), "o/r", "post", rel, "Ideas",
                                                             log=lambda *_: 0)["error"]
        gh = FakeGH()
        r = L.discussions(gh, "o/r", "post", rel, "receipts", sha="abcdef123", log=lambda *_: 0)
        assert r == {"action": "post", "number": 201, "url": "https://x/discussions/201", "category": "Receipts",
                     "file": rel}
        v = gh.calls[-1][1]
        assert (v["r"], v["c"], v["t"]) == ("R1", "C4", "A receipt")
        assert v["b"].startswith("body line") and f"from `{rel}` @ abcdef1" in v["b"]
        p.write_text("no title here\n")
        assert "no '# Title'" in L.discussions(FakeGH(), "o/r", "post", rel, "Receipts", log=lambda *_: 0)["error"]
        p.write_text("# NHL information floor\n\nagain\n")
        assert "already posted as #197" in L.discussions(FakeGH(), "o/r", "post", rel, "Q&A",
                                                        log=lambda *_: 0)["error"]
    finally:
        p.unlink()


def test_reply_by_thread_number_and_refusals():
    p = post_file(text="a reply body\n")
    try:
        rel = str(p.relative_to(ROOT))
        assert "thread '999' not found" in L.discussions(FakeGH(), "o/r", "reply", rel, thread="999",
                                                         log=lambda *_: 0)["error"]
        gh = FakeGH()
        r = L.discussions(gh, "o/r", "reply", rel, thread="197", log=lambda *_: 0)
        assert r["number"] == 197 and r["url"].endswith("#c1")
        assert gh.calls[-1][1]["d"] == "D1" and gh.calls[-1][1]["b"].startswith("a reply body")
    finally:
        p.unlink()


def test_token_refused_prints_the_scope_hint_never_a_token(monkeypatch, capsys):
    out = []
    r = L.discussions(FakeGH(refuse=True), "o/r", "list", log=out.append)
    assert r["error"] == "token refused" and any("write:discussion" in x for x in out)
    assert not L.discussions(FakeGH(), "o/r", "bogus", log=lambda *_: 0).get("number")
    # main(): no token -> refuses; the default dispatch is list
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    monkeypatch.delenv("LEDGER_PROJECT_TOKEN", raising=False)
    assert L.main(["discussions"]) == 1 and "LEDGER_PROJECT_TOKEN not set" in capsys.readouterr().out
    monkeypatch.setenv("LEDGER_PROJECT_TOKEN", "secret-token-value")
    monkeypatch.setattr(L, "GH", lambda tok, repo: FakeGH())
    assert L.main(["discussions"]) == 0
    printed = capsys.readouterr().out
    assert "LEDGER-DISCUSSIONS" in printed and '"action": "list"' in printed and "secret-token-value" not in printed


def test_workflow_dispatch_carries_the_inputs_as_env():
    wf = (ROOT / ".github" / "workflows" / "ledger.yml").read_text()
    for k in ("action:", "file:", "category:", "thread:", "LEDGER_D_ACTION: ${{ inputs.action }}",
              "LEDGER_D_FILE: ${{ inputs.file }}", "LEDGER_D_CATEGORY: ${{ inputs.category }}",
              "LEDGER_D_THREAD: ${{ inputs.thread }}", "default: list"):
        assert k in wf, k
