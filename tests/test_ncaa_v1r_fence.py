"""#368 RULED (ARCHITECT 2026-10-08, addendum 14 item 2). Pins:
- (a) the correction to D9 stands beside D9 (verbatim) in the spec, the ledger entry and the registry entry's
  prior_reads_note; the registry's prior reads of the test set stay empty;
- (b) the test-season fence: until the registry records the ncaa-elo-v1r run, ncaa-cfbd-coverage prints no 2025
  home win rate in either block (counts, coverage, census and neutral counts stay), ncaa-backtest and ncaa-audit
  refuse with exit 2 naming the ruling, and resync-diff's NCAA home-rate line is withheld when the listing includes
  2025; once the run is recorded every line and both commands return.
The run is recorded (ARCHITECT 2026-10-09, addendum 24; spliced from 130b481), so the fence on main is lifted
(addendum 24 item 2(e)): the fenced branch is exercised here with v1r_run_recorded patched False, and the committed
registry is pinned as recorded. ncaa-backtest no longer returns with the fence: it refuses for good (item 2(c))."""
import json
from datetime import datetime
from pathlib import Path

from click.testing import CliRunner

from src.walters import ncaa_backtest as nb
from src.walters import registry as reg

ROOT = Path(__file__).resolve().parent.parent
D9 = ("D9. Prior reads of this test set: none. The 2026-09-30 run of v1 (all divisions, scrambled 2025 labels, VOID "
      "by the 2026-10-01 ruling) scored 2026 games; the entry names it.")
CORRECTION = ("For 'Prior reads of this test set: none.' read 'No candidate has been scored on this test set. One "
              "outcome figure of the test season was read before this declaration: its non-neutral home win rate on "
              "the labels then held, 0.597 on 652 games (operator console, ingest of 2026-10-08 14:07Z; the label "
              "sanity check ordered on 2026-10-07, when 2025 was the warm-up season). D5 (2) compares the model with "
              "a figure of that kind and was declared with it known. D5 (1), (3) and (4) were not informed by it.'")
CORRECTION_IN_FORCE = "For 'Prior reads of this test set: none.' read: 'No candidate has been scored on this test set. The season's home win rate and mean home margin were read before this declaration, more than once. Under the provider's labels, since found scrambled: 0.489 in the void v1 run (2026-09-30); by stage and by month in ncaa-audit, FBS 0.404 with -6.05 points (2026-10-01); 0.489 at the source in resync-diff (2026-10-01); 0.445 with -2.67 points in the #176 probe (2026-10-07). Under CFBD's labels: 0.597 with +5.23 points on non-neutral games in the same probe, which also printed both figures for the season's 64 neutral-site games; and 0.597 on 652 labelled non-neutral games (operator console, 2026-10-08 14:07Z). Declared with these figures known: D1's neutral-site rule, D4, and D5's tests (2) and (3). Fixed before any of them was read: D1's constants, and the margin of 0.010, the rating range and the 500 games, which are #79's (frozen 2026-09-30, before any run).'"
LEVEL_RULING = "The fence covers figures across games: a rate, a margin, a count of wins. A single game listed with its score is how a defect is checked, in the join receipts and in D2's list alike. D2 orders such a game skipped, counted and listed, and the gate never scores it. Nothing is redacted."
FENCE = ("Until the one run of ncaa-elo-v1r is recorded, no command prints an outcome figure of the 2025 season. "
         "ncaa-cfbd-coverage prints no 2025 home win rate in either block; counts, coverage, the season_type census "
         "and the neutral counts stay. ncaa-backtest and ncaa-audit refuse, exit 2, naming this ruling: both print "
         "2025 rates, and the first scores a candidate. The join receipts keep listing single games with their "
         "scores; that is how a join is checked. After the run is recorded the lines and the two commands return.")


def _flat(path: Path) -> str:
    return " ".join(path.read_text().split())


def test_d9_correction_stands_beside_d9_verbatim_in_spec_ledger_and_registry():
    for path in (ROOT / "docs" / "specs" / "ncaa-elo-v1r.md",
                 ROOT / "docs" / "ledger" / "entries" / "2026-10-08-ncaa-v1r-declaration.md"):
        text_ = _flat(path)
        assert D9 in text_ and CORRECTION in text_ and FENCE in text_, path.name
        assert text_.index(D9) < text_.index(CORRECTION)
    e = reg.get(nb.V1R_EID)
    assert e["prior_reads_note"].startswith(D9) and CORRECTION in e["prior_reads_note"]
    assert e["run"]["n_scored"] == 762 and e["status"] == "closed"            # addendum 24: run recorded, FAIL
    assert reg.prior_reads(e["test_set"], None, before_id=nb.V1R_EID) == []     # no candidate scored before it
    assert nb.TEST_SEASON_FENCE == FENCE


def test_run_recorded_reads_only_the_registry(tmp_path):
    p = tmp_path / "experiments.json"
    p.write_text(json.dumps([{"id": nb.V1R_EID, "run": None}]))
    assert nb.v1r_run_recorded(str(p)) is False
    p.write_text(json.dumps([{"id": nb.V1R_EID, "run": {"run_at": "2026-10-10T00:00:00Z"}}]))
    assert nb.v1r_run_recorded(str(p)) is True
    assert nb.v1r_run_recorded() is True                   # the committed registry: run recorded (addendum 24 (e))


def _g(mid, season, hs, as_, neutral=False, st="regular"):
    return nb.Game(1 + mid % 3, 10 + mid % 3, season, datetime(int(season), 9, 1 + mid % 20), hs, as_,
                   neutral=neutral, label_source="cfbd", orientation="same", match_id=mid, season_type=st)


def _stream_and_v1r():
    games = [_g(i, s, 30, 10) for s in ("2024", "2025", "2026") for i in range(1, 5)] + [_g(50, "2025", 7, 21)]
    v = nb.V1RStream(games=games, merge=nb.team_merge({}))
    for g in games:
        v.census.setdefault(g.season, {}).setdefault("regular", 0)
        v.census[g.season]["regular"] += 1
    return nb.build_stream(games), v


def test_coverage_withholds_every_2025_home_rate_and_keeps_counts_until_the_run_is_recorded(monkeypatch):
    st, v = _stream_and_v1r()
    lifted = []
    nb.coverage_report(st, out=lifted.append, fbs=None, v1r=v)              # the committed registry: run recorded
    assert nb.FENCED_RATE not in "\n".join(lifted) and "home win rate non-neutral 0.800 (n 5)" in "\n".join(lifted)
    monkeypatch.setattr(nb, "v1r_run_recorded", lambda *a: False)
    fenced = []
    nb.coverage_report(st, out=fenced.append, fbs=None, v1r=v)              # registry: not run -> fenced
    text_ = "\n".join(fenced)
    l25 = [ln for ln in fenced if ln.startswith("  2025: walked ")]
    assert len(l25) == 1 and nb.FENCED_RATE in l25[0] and "walked 5" in l25[0] and "regular" in l25[0]
    assert "0.800" not in text_                                             # 2025 rate: 4 of 5
    assert "sanity read" not in text_
    assert [ln for ln in fenced if ln.startswith("    home win rate: ")][0].endswith(nb.FENCED_RATE)
    for season in ("2024", "2026"):                                        # only 2025 is fenced
        assert f"  {season}: walked 4" in text_ and "home win rate non-neutral 1.000 (n 4)" in text_
    assert "  2025: stream games" in text_                                  # #79's counts stay
    opened = []
    nb.coverage_report(st, out=opened.append, fbs=None, v1r=v, fenced=False)
    text_ = "\n".join(opened)
    assert nb.FENCED_RATE not in text_ and "home win rate non-neutral 0.800 (n 5)" in text_
    assert "2025 non-neutral home rate for the sanity read" in text_


def test_ncaa_backtest_and_ncaa_audit_refuse_exit_2_naming_the_ruling_before_reading(monkeypatch):
    """ncaa-audit under the fence (patched unlifted). ncaa-backtest's refusal is addendum 24 item 2(c)'s now
    (tests/test_ncaa_v1r_verdict.py); the fence no longer decides it."""
    from cli import cli
    from src.walters import ncaa_audit as na

    def boom(*a, **k):
        raise AssertionError("read before the fence")
    monkeypatch.setattr(nb, "load_games", boom)
    monkeypatch.setattr(na, "load", boom)
    monkeypatch.setattr(nb, "v1r_run_recorded", lambda *a: False)
    for cmd in (["ncaa-audit"], ["ncaa-audit", "--season", "2026"]):
        res = CliRunner().invoke(cli, cmd)
        assert res.exit_code == 2, (cmd, res.output)
        assert f"{cmd[0]} REFUSED (exit 2)" in res.output and nb.FENCE_RULING in res.output
        assert FENCE in res.output


def test_resync_diff_withholds_the_ncaa_home_rate_when_the_listing_includes_2025(monkeypatch):
    import cli
    from src.ingestion import resync_diff as rd

    monkeypatch.setattr(cli, "_adapter_for_competition", lambda code: None)
    monkeypatch.setattr(rd, "diff", lambda *a, **k: {"source": "x", "listing": 3, "counts": {}, "samples": {},
                                                    "home_rate": {"ours": ["0.612", 3], "provider": ["0.587", 3]}})
    monkeypatch.setattr(rd, "verdict", lambda c: "ok")
    monkeypatch.setattr(nb, "v1r_run_recorded", lambda *a: False)            # the fence as it stood before the run
    for args, withheld in ((["--season", "2025"], True), ([], True), (["--season", "2026"], False)):
        out = CliRunner().invoke(cli.cli, ["resync-diff", "--competition", "NCAA", *args]).output
        assert ("0.612" not in out and nb.FENCED_RATE in out) if withheld else ("ours 0.612" in out), (args, out)
    out = CliRunner().invoke(cli.cli, ["resync-diff", "--competition", "NFL", "--season", "2025"]).output
    assert "ours 0.612" in out                                              # another sport: unfenced
    monkeypatch.setattr(nb, "v1r_run_recorded", lambda *a: True)
    out = CliRunner().invoke(cli.cli, ["resync-diff", "--competition", "NCAA", "--season", "2025"]).output
    assert "ours 0.612" in out                                              # the run recorded: the line returns


def test_the_addendum_15_correction_in_force_stands_beside_d9_and_the_addendum_14_one_verbatim():
    """ARCHITECT 2026-10-08, addendum 15 item 1(a): D9 and the addendum 14 correction stay quoted as issued; this one
    stands beside them and is the one in force, in the spec, the ledger entry and prior_reads_note. Item 3 (the
    level-score ruling) is quoted in the spec and the ledger entry."""
    for path in (ROOT / "docs" / "specs" / "ncaa-elo-v1r.md",
                 ROOT / "docs" / "ledger" / "entries" / "2026-10-08-ncaa-v1r-declaration.md"):
        text_ = _flat(path)
        assert text_.index(D9) < text_.index(CORRECTION) < text_.index(CORRECTION_IN_FORCE), path.name
        assert LEVEL_RULING in text_, path.name
    note = reg.get(nb.V1R_EID)["prior_reads_note"]
    assert note.startswith(D9) and note.index(CORRECTION) < note.index(CORRECTION_IN_FORCE)
    assert "CORRECTION IN FORCE" in note
    assert reg.get(nb.V1R_EID)["run"]["n_scored"] == 762                   # addendum 24: the run is recorded
