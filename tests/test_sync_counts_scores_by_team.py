"""ADDENDUM 295 ITEM 4 (ARCHITECT 2026-11-08 10:05 ET; #885), verbatim: "`sp_run.sync_counts` reads the new line so
chain summaries and the digest carry both counts — until then a reversed row on the host is only in the journal."

The new line is #884's (service.scores_by_team_line, printed by sync-matches always, zeros included):
"orientation_reversed N: <ids> · teams_mismatch_refused M: <ids>". Synthetic throughout: a fake cli.py in sp_run's
sandbox checkout (tests/test_hosting_pack), no network, never data/."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))

import sp_common as c  # noqa: E402
import sp_receipts  # noqa: E402
import sp_run  # noqa: E402

from tests.test_hosting_pack import receipts, sandbox  # noqa: E402,F401


def test_sync_counts_reads_both_counts_with_their_ids_and_zeros():
    got = sp_run.sync_counts(["✓ Matches (NCAA): created=0 updated=40 skipped=1",
                              "orientation_reversed 2: 36454, 36753 · teams_mismatch_refused 1: 501"])
    assert got["matches"] == {"created": 0, "updated": 40, "skipped": 1}
    assert got["scores_by_team"] == {"orientation_reversed": {"n": 2, "ids": ["36454", "36753"]},
                                     "teams_mismatch_refused": {"n": 1, "ids": ["501"]}}
    zero = sp_run.sync_counts(["orientation_reversed 0 · teams_mismatch_refused 0"])
    assert zero == {"scores_by_team": {"orientation_reversed": {"n": 0, "ids": []},
                                       "teams_mismatch_refused": {"n": 0, "ids": []}}}
    assert sp_run.sync_counts(["✓ Matches (PL): created=1 updated=2 skipped=0"]).get("scores_by_team") is None


def test_every_line_of_a_step_adds_so_no_season_or_re_read_is_dropped():
    """A --seasons run prints one line per season, the tennis path its re-read's too: each adds (the last line of the
    other kinds still counts alone)."""
    got = sp_run.sync_counts(["orientation_reversed 1: 7 · teams_mismatch_refused 0",
                              "orientation_reversed 0 · teams_mismatch_refused 2: 8, 9",
                              "  ATP re-read: orientation_reversed 1: 10 · teams_mismatch_refused 0"])
    assert got["scores_by_team"] == {"orientation_reversed": {"n": 2, "ids": ["7", "10"]},
                                     "teams_mismatch_refused": {"n": 2, "ids": ["8", "9"]}}


def test_the_line_is_one_of_the_lines_run_step_collects():
    assert any(r.match("orientation_reversed 1: 5 · teams_mismatch_refused 0") for r in sp_run._SYNC_LINES)
    assert not any(r.match("orientation reversed 1 · teams mismatch refused 0") for r in sp_run._SYNC_LINES)


FAKE_CLI = '''import sys
a = sys.argv[1:]
code = a[a.index("--competition") + 1]
print("ran", " ".join(a))
if a[0] == "sync-teams":
    print("✓ Teams (%s): created=0 updated=30 skipped=0" % code)
elif a[0] == "sync-matches":
    print("✓ Matches (%s): created=0 updated=10 skipped=%d" % (code, 1 if code == "NCAA" else 0))
    if code == "NCAA":
        print("orientation_reversed 2: 36454, 36753 · teams_mismatch_refused 1: 501")
    else:
        print("orientation_reversed 0 · teams_mismatch_refused 0")
'''


def test_the_chain_receipt_summary_and_receipts_table_carry_both_counts(sandbox, monkeypatch, capsys):
    (c.REPO / "cli.py").write_text(FAKE_CLI)
    import chains
    monkeypatch.setitem(chains.CHAINS, "t-sbt-295", {"steps": [
        [v, "--competition", code, "--season", season] for code, season in (("PL", "2026/27"), ("NCAA", "2026"))
        for v in ("sync-teams", "sync-matches")]})
    capsys.readouterr()
    assert sp_run.main(["t-sbt-295"]) == 0
    out = capsys.readouterr().out.rstrip("\n").split("\n")
    rs = receipts(sandbox)
    steps = [r for r in rs if r["kind"] == "step"]
    assert steps[3]["sync"]["scores_by_team"]["orientation_reversed"] == {"n": 2, "ids": ["36454", "36753"]}
    assert steps[1]["sync"]["scores_by_team"]["orientation_reversed"] == {"n": 0, "ids": []}
    chain = rs[-1]
    assert chain["scores_by_team"] == {
        "orientation_reversed": 2, "teams_mismatch_refused": 1,
        "steps": [{"step": 4, "command": "python cli.py sync-matches --competition NCAA --season 2026",
                   "orientation_reversed": {"n": 2, "ids": ["36454", "36753"]},
                   "teams_mismatch_refused": {"n": 1, "ids": ["501"]}}]}
    summary = next(x for x in out if x.startswith("✓ t-sbt-295: exit=0 steps 4/4"))
    assert " · orientation_reversed 2 · teams_mismatch_refused 1 · running " in summary
    assert ("  ⚠ step 4/4 python cli.py sync-matches --competition NCAA --season 2026: orientation_reversed 2: "
            "36454, 36753 · teams_mismatch_refused 1: 501") in out
    assert "orientation_reversed 2 · teams_mismatch_refused 1" in sp_receipts.key_line(chain)


def test_a_chain_whose_steps_print_zeros_carries_the_zeros_and_lists_no_step(sandbox, monkeypatch, capsys):
    (c.REPO / "cli.py").write_text(FAKE_CLI)
    import chains
    monkeypatch.setitem(chains.CHAINS, "t-sbt-295z", {"steps": [["sync-matches", "--competition", "PL",
                                                                  "--season", "2026/27"]]})
    capsys.readouterr()
    assert sp_run.main(["t-sbt-295z"]) == 0
    out = capsys.readouterr().out
    chain = receipts(sandbox)[-1]
    assert chain["scores_by_team"] == {"orientation_reversed": 0, "teams_mismatch_refused": 0, "steps": []}
    assert " · orientation_reversed 0 · teams_mismatch_refused 0 · running " in out
    assert "⚠" not in out
    assert sp_receipts.key_line(chain).endswith("; orientation_reversed 0 · teams_mismatch_refused 0")


def test_a_chain_without_the_line_says_nothing_about_it(sandbox, monkeypatch, capsys):
    from tests.test_hosting_pack import FAKE_CLI as PLAIN
    (c.REPO / "cli.py").write_text(PLAIN)
    import chains
    monkeypatch.setitem(chains.CHAINS, "t-sbt-295p", {"steps": [["one"], ["two"]]})
    capsys.readouterr()
    assert sp_run.main(["t-sbt-295p"]) == 0
    out = capsys.readouterr().out
    chain = receipts(sandbox)[-1]
    assert "scores_by_team" not in chain and "orientation_reversed" not in out
    assert "orientation_reversed" not in sp_receipts.key_line(chain)
