"""THE BULLETIN HOOKS (ARCHITECT 2026-11-10 13:05 ET, addendum 321 item 2; ARCHITECT 2026-11-04, addendum 250 items 3
and 6(e); step 1c of the bulletins lane, #826), on the closing-run test frame (tests/test_closing_runs.py: a SCRATCH
schedule in a throwaway DB under tmp_path, every step, page, push and notification faked, the network blocked). The
frame fakes the render's subprocess; here box.bulletin_on() turns the REAL one on (`python cli.py bulletin` of this
checkout, run in the throwaway repo, writing under its exports/bulletins/) wherever a test says so.

Addendum 321 item 2, verbatim: "(i) in the closing run, between write_closing_file's success and push_mirror(); (ii) in
the slate stage, between link_slate_file's success and push_mirror("slate"); each a subprocess of the command under a
try; a failure or refusal receipted bulletin_failed / bulletin_refused and notified as a closing-file failure is;
rec["exit"] never changed; the push proceeds with or without the pair; the laptop's MLB closing takes the same hook
under laptop/bulletins/; test 6(e) with them; the console's URL lines unchanged."
Addendum 250 item 6(e), verbatim: "(e) the hooks — a closing run on the synthetic store writes the pair before the push
and a render failure leaves rec["exit"] 0 with bulletin_failed receipted"."""
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest

from tests.test_closing_runs import (  # noqa: F401  (box is a fixture)
    NOW, REAL_PUSH, at, box, c, call_pages, mc, receipts, runs)
from tests.test_slate_run import NFL_FILE, PAGE, et, slate_pages, slates, the_day, tick

pytestmark = pytest.mark.usefixtures("nfl_market_only_off")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))
import bulletin  # noqa: E402
import exports_mirror  # noqa: E402

NFL_CLOSING = "exports/closing_NFL_2026-10-11T1700Z.json"
MLB_CLOSING = "exports/closing_MLB_2026-10-11T1655Z.json"
NFL_PAIRS = sorted(f"{mid}_{home.lower()}-visitors_at_{home.lower()}_closing{sfx}"
                   for mid, home in ((301, "Buffalo"), (304, "Denver"), (302, "Newark"), (303, "Tampa"))
                   for sfx in (".md", ".png"))
HEAD = "Closing NFL 2026-10-11 13:00 ET: PAGED; bulletin"


@pytest.fixture
def real(box, monkeypatch, tmp_path):
    """The real render: `python cli.py bulletin` in a subprocess, the throwaway repo its cwd (the frame's receipts log,
    scratch DB and role are in its environment; no host.env read)."""
    monkeypatch.setenv("SP_HOST_ENV", str(tmp_path / "no-host.env"))
    box.bulletin_on()
    return box


def pairs(box, fam="NFL", day="2026-10-11"):
    d = box.repo / "exports" / "bulletins" / fam / day
    return sorted(p.name for p in d.iterdir()) if d.is_dir() else []


def bulletin_lines():
    return [r for r in receipts() if r["kind"] == "bulletin"]


def watch_push(box, monkeypatch, seen, fam="NFL"):
    """push_mirror, recording what exports/bulletins/<fam>/2026-10-11/ held when it was called."""
    def push(label="closing"):
        seen.append((label, pairs(box, fam)))
        box.pushes.append(label)
        return {"exit": 0, "tail": ["pushed"]}
    monkeypatch.setattr(mc, "push_mirror", push)


def test_the_hooks_write_where_the_mirror_reads():
    """The out dir the hook names is the renderer's default, the mirror's kept subtree (exports_mirror.BULLETINS)."""
    assert mc.BULLETIN_OUT_DIR == bulletin.OUT_DIR == f"exports/{exports_mirror.BULLETINS}"
    assert (mc.CODE_ROOT / "cli.py").is_file() and mc.CODE_ROOT == c.REPO


# ============================================================================= 6(e): the closing run, the pair ==

def test_6e_a_closing_run_writes_the_pair_before_the_push(real, monkeypatch, capsys):
    """Addendum 250 item 6(e): the real render on the synthetic store's closing file, between the closing file's write
    and the push: at the push every pair is on disk; rec["exit"] 0; the receipt's `bulletin` names the command and
    exit 0; the render's own receipt line (kind bulletin) is written too; the page text is untouched."""
    seen = []
    watch_push(real, monkeypatch, seen)
    assert mc.run("NFL", start=at(35), now=NOW) == 0
    r = runs("NFL")[-1]
    assert seen == [("closing", NFL_PAIRS)]                                  # the pair BEFORE the push
    assert r["exit"] == 0 and r["push"]["exit"] == 0 and "failed" not in r
    assert r["bulletin"]["exit"] == 0 and r["bulletin"]["command"] == (
        f"python cli.py bulletin --closing-file {NFL_CLOSING} --out-dir exports/bulletins")
    assert "bulletin_failed" not in r and "bulletin_refused" not in r and "bulletin_failure_notification" not in r
    (b,) = bulletin_lines()
    assert (b["stage"], b["family"], b["exit"], b["source"]) == ("closing", "NFL", 0, NFL_CLOSING)
    assert sorted(Path(p).name for p in b["written"]) == NFL_PAIRS
    assert len(call_pages(real)) == 1 and "bulletin" not in call_pages(real)[0]["body"]
    assert real.notes == [call_pages(real)[0]["body"]]                        # the screen: the page; no notice
    out = capsys.readouterr().out
    # the render's console is passed through as it printed it (its path and URL lines), then the push line, unchanged
    assert "  BULLETIN NFL closing: 8 file(s) written from closing_NFL_2026-10-11T1700Z.json" in out
    assert out.count("    no mirror URL: --out-dir is not the mirror's subtree") == 8   # the checkout is not this repo
    assert "· exports mirror (laptop, closing): exit 0 pushed" in out
    assert out.index("BULLETIN NFL closing") < out.index("· exports mirror (laptop, closing)")
    md = (real.repo / "exports" / "bulletins" / "NFL" / "2026-10-11" / NFL_PAIRS[0]).read_text()
    assert md.startswith("# ") and bulletin.FOOTER.split(".")[0] in bulletin.display_text(md)


def test_6e_a_render_failure_leaves_exit_0_receipts_bulletin_failed_notifies_and_pushes(real, monkeypatch):
    """Addendum 250 item 6(e): "a render failure leaves rec["exit"] 0 with bulletin_failed receipted". A real failure
    (exports/bulletins is a file, so nothing can be written under it: the render exits 1), on a watch-started run:
    receipted, notified as the closing-file failure is, the push proceeds; the closing is not run again."""
    (real.repo / "exports" / "bulletins").write_text("not a folder")
    assert mc.watch(now=NOW, families=("NFL",)) == 0
    r = runs("NFL")[-1]
    assert r["exit"] == 0 and "failed" not in r and r["bulletin_failed"] is True and "bulletin_refused" not in r
    assert r["bulletin"]["exit"] == 1 and r["bulletin"]["error"].startswith("BULLETIN FAILED: ")
    assert bulletin_lines()[-1]["exit"] == 1 and bulletin_lines()[-1]["bulletin_failed"]
    text = f"{HEAD} FAILED (exit 1, {NFL_CLOSING}) · not run again\nmachine: laptop"
    assert r["bulletin_failure_notification"]["text"] == text and real.notes[-1] == text
    assert r["bulletin_failure_notification"]["channel"] == "card+screen"
    assert [p["title"] for p in real.pages] == ["NFL closing 13:00 ET", "NFL closing"]   # the page, then the notice
    assert real.pushes == ["closing"] and r["push"]["exit"] == 0                          # the push proceeds
    assert r["closing_file"]["file"] == NFL_CLOSING and "closing_file_failed" not in r
    assert mc.watch(now=NOW + timedelta(minutes=1), families=("NFL",)) == 0
    assert len(runs("NFL")) == 1 and len(call_pages(real)) == 1 and len(bulletin_lines()) == 1   # not run again


def test_a_refusal_is_receipted_bulletin_refused_notified_and_the_push_proceeds(real, monkeypatch):
    """A real refusal (exit 2): a row whose desk reason carries a contract count; the guard writes nothing."""
    seen = []
    watch_push(real, monkeypatch, seen)
    row = next(p for p in real.docs["NFL"]["predictions"] if p["match_id"] == 301)
    row["desk"]["reason"] = "size 12 contracts"
    assert mc.run("NFL", start=at(35), now=NOW) == 0
    r = runs("NFL")[-1]
    assert r["exit"] == 0 and r["bulletin_refused"] is True and "bulletin_failed" not in r and "failed" not in r
    assert r["bulletin"]["exit"] == 2 and r["bulletin"]["error"].startswith("BULLETIN REFUSED NFL closing: ")
    assert {x["pattern"] for x in bulletin_lines()[-1]["bulletin_refused"]} == {"contract_count"}
    assert real.notes[-1] == f"{HEAD} REFUSED (exit 2, {NFL_CLOSING}) · not run again\nmachine: laptop"
    assert seen == [("closing", [])] and r["push"]["exit"] == 0               # nothing written; the push proceeds


def test_a_timeout_is_a_failure_and_the_push_proceeds(real, monkeypatch):
    """The bound (BULLETIN_TIMEOUT_S): a render still running then is killed and is bulletin_failed."""
    monkeypatch.setattr(mc, "BULLETIN_TIMEOUT_S", 0.01)
    assert mc.run("NFL", start=at(35), now=NOW) == 0
    r = runs("NFL")[-1]
    assert r["exit"] == 0 and r["bulletin_failed"] is True and r["bulletin"]["exit"] is None
    assert r["bulletin"]["error"] == "timed out after 0.01s (killed)"
    assert real.notes[-1] == (f"{HEAD} FAILED (timed out after 0.01s (killed), {NFL_CLOSING}) · not run again\n"
                              "machine: laptop")
    assert real.pushes == ["closing"] and r["push"]["exit"] == 0


def test_an_exception_at_the_boundary_never_reaches_the_run(box, monkeypatch):
    def boom(argv):
        raise OSError("no python here")
    monkeypatch.setattr(mc, "run_bulletin", boom)
    assert mc.run("NFL", start=at(35), now=NOW) == 0
    r = runs("NFL")[-1]
    assert r["exit"] == 0 and r["bulletin_failed"] is True and r["bulletin"]["error"] == "OSError: no python here"
    assert box.pushes == ["closing"] and box.notes[-1].startswith(f"{HEAD} FAILED (OSError: no python here, ")


def test_the_receipt_keeps_a_redacted_bounded_tail(box, monkeypatch):
    """The console's last lines, through sp_common.redact, BULLETIN_TAIL_LINES of them, each cut at 300."""
    monkeypatch.setattr(mc, "run_bulletin", lambda argv: (1, "\n".join(
        [f"line {i}" for i in range(9)] + ["api_key=abcdef123456", "x" * 400])))
    assert mc.run("NFL", start=at(35), now=NOW) == 0
    r = runs("NFL")[-1]
    tail = r["bulletin"]["tail"]
    assert len(tail) == mc.BULLETIN_TAIL_LINES and tail[-2] == "api_key=[REDACTED]" and tail[-1] == "x" * 300
    assert r["bulletin"]["error"] == "x" * 300 and "abcdef123456" not in c.receipts_path().read_text()


# ================================================================================== when the hook does not run ==

def test_a_closing_file_not_written_runs_no_hook(box, monkeypatch):
    """Item 2 (i): "between write_closing_file's SUCCESS and push_mirror()": a failed write renders nothing (the
    closing-file failure is receipted and notified as before) and the push still runs."""
    monkeypatch.setattr(mc, "write_closing_file", lambda doc, name, mtime=None: {
        "file": f"exports/{name}", "error": "OSError: disk full"})
    assert mc.run("NFL", start=at(35), now=NOW) == 0
    r = runs("NFL")[-1]
    assert box.bulletins == [] and "bulletin" not in r and r["closing_file_failed"] is True
    assert box.pushes == ["closing"]


def test_a_page_not_accepted_runs_no_hook(box):
    box.page_ok = False
    assert mc.run("NFL", start=at(35), now=NOW) == 1
    assert box.bulletins == [] and "bulletin" not in runs("NFL")[-1] and box.pushes == []


def test_the_hook_argv_is_the_command_on_the_kept_closing_file(box):
    assert mc.run("SOCCER", start=at(35), now=NOW) == 0
    assert box.bulletins == [["bulletin", "--closing-file", "exports/closing_SOCCER_2026-10-11T1700Z.json",
                              "--out-dir", "exports/bulletins"]]
    assert runs("SOCCER")[-1]["bulletin"] == {
        "command": "python cli.py bulletin --closing-file exports/closing_SOCCER_2026-10-11T1700Z.json --out-dir "
                   "exports/bulletins", "exit": 0, "tail": ["BULLETIN faked: 0 file(s) written"],
        "seconds": runs("SOCCER")[-1]["bulletin"]["seconds"]}


# ============================================================================== the laptop's MLB closing ==

def test_the_mlb_closing_takes_the_same_hook_and_its_push_lands_under_laptop_bulletins(real, monkeypatch):
    """Item 2: "the laptop's MLB closing takes the same hook under laptop/bulletins/": the same render before the push
    (closing-run --family MLB), and the push's role is the machine's (laptop here), so exports_mirror's kept subtree
    puts every pair at laptop/bulletins/MLB/<date>/."""
    seen = []
    watch_push(real, monkeypatch, seen, "MLB")
    assert mc.run("MLB", start=at(30), now=NOW) == 0
    r = runs("MLB")[-1]
    assert r["exit"] == 0 and r["bulletin"]["exit"] == 0 and r["closing_file"]["file"] == MLB_CLOSING
    assert r["bulletin"]["command"] == f"python cli.py bulletin --closing-file {MLB_CLOSING} --out-dir exports/bulletins"
    got = pairs(real, "MLB")
    assert got and all(n.endswith(("_closing.md", "_closing.png")) for n in got)
    assert seen == [("closing", got)]                                          # the pair BEFORE the push
    plan = exports_mirror.bulletin_plan(real.repo / "exports", mc.mirror_role())
    assert sorted(plan["kept"]) == [f"laptop/bulletins/MLB/2026-10-11/{n}" for n in got] and plan["skipped"] == []


def test_the_push_names_this_machines_role(box, monkeypatch):
    """push_mirror (the real one) runs exports_mirror.py push with --role from SP_EXPORTS_MIRROR_ROLE: laptop on the
    laptop, so the kept subtree goes to laptop/bulletins/ (exports_mirror.bulletin_plan's <role>/bulletins/<rel>)."""
    got = []
    monkeypatch.setattr(mc.subprocess, "run", lambda argv, **k: got.append(argv) or subprocess.CompletedProcess(
        argv, 0, "pushed\n", ""))
    assert REAL_PUSH()["exit"] == 0
    assert got[0][-4:] == ["--role", "laptop", "--label", "closing"]


# ===================================================================================== the slate stage ==

def test_the_slate_hook_runs_after_the_link_and_before_the_push(real, monkeypatch):
    """Item 2 (ii): the real render on the linked slate file, before push_mirror("slate"); the slate's own outcome
    stands (exit 0, its page)."""
    the_day(real, monkeypatch)
    seen = []

    def push(label="closing"):
        seen.append((label, pairs(real, "NFL", "2026-10-18"), (real.repo / NFL_FILE).is_file()))
        real.pushes.append(label)
        return {"exit": 0, "tail": ["pushed"]}
    monkeypatch.setattr(mc, "push_mirror", push)
    assert tick(et(7, 0)) == 0
    (s,) = slates()
    assert s["exit"] == 0 and s["bulletin"]["exit"] == 0 and "failed" not in s
    assert s["bulletin"]["command"] == f"python cli.py bulletin --slate-file {NFL_FILE} --out-dir exports/bulletins"
    want = sorted(f"{mid}_{h}-visitors_at_{h}_slate{sfx}" for mid, h in ((601, "london"), (602, "buffalo"))
                  for sfx in (".md", ".png"))
    assert seen == [("slate", want, True)]
    assert [p["body"] for p in slate_pages(real)] == [PAGE]
    (b,) = bulletin_lines()
    assert (b["stage"], b["family"], b["exit"], b["source"]) == ("slate", "NFL", 0, NFL_FILE)


@pytest.mark.parametrize("rc,word,key", [(1, "FAILED", "bulletin_failed"), (2, "REFUSED", "bulletin_refused")])
def test_a_slate_render_failure_leaves_the_slates_outcome_unchanged(box, monkeypatch, rc, word, key):
    """A failed or refused render in the slate stage: receipted on the slate's line, notified under the slate's
    notice title, and the slate goes on: pushed, paged, exit 0, a success that ends the day."""
    the_day(box, monkeypatch)
    monkeypatch.setattr(mc, "run_bulletin", lambda argv: box.bulletins.append(argv) or (rc, f"BULLETIN {word}: x"))
    assert tick(et(7, 0)) == 0
    (s,) = slates()
    assert s["exit"] == 0 and "failed" not in s and s[key] is True and s["bulletin"]["exit"] == rc
    text = f"SLATE NFL 2026-10-18: LINKED; bulletin {word} (exit {rc}, {NFL_FILE}) · not run again\nmachine: laptop"
    assert s["bulletin_failure_notification"]["text"] == text
    assert [(p["title"], p["body"]) for p in box.pages] == [("NFL slate", text), ("NFL slate 2026-10-18", PAGE)]
    assert box.pushes == ["slate"] and s["push"]["exit"] == 0 and s["page"]["phone"]["accepted"] is True
    assert mc.slate_state("NFL", "2026-10-18") == {"success": True, "attempts": 1}
    assert tick(et(7, 1)) == 0 and len(slates()) == 1 and len(box.bulletins) == 1      # not run again


def test_a_slate_that_fails_before_the_link_runs_no_hook(box, monkeypatch):
    the_day(box, monkeypatch)
    box.fail_cmd["export-nfl-predictions"] = (1, ["boom"])
    assert tick(et(7, 0)) == mc.NOTIFIED
    assert box.bulletins == [] and "bulletin" not in slates()[0]
