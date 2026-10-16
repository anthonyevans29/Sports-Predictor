"""THE 2026 FENCE (ARCHITECT 2026-10-16, addendum 86 item 3, Q2), in v1r's form. Pins:
- the ruling verbatim in the code (V2_FENCE) and the spec; the fence reads only the registry (ncaa-elo-v2's `run`), an
  absent entry reading as not recorded; the committed registry: not recorded, so the fence stands on main;
- ncaa-cfbd-coverage prints no 2026 home win rate in either block while it stands (counts, coverage, census and
  neutral counts stay), and every line returns once the run is recorded;
- ncaa-audit refuses (exit 2, naming the ruling, before anything is read) with 2026 among its seasons; its default
  seasons are 2025 alone until the run, both after it;
- resync-diff --competition NCAA withholds its home-rate line when the listing includes 2026 (no --season, or 2026),
  keeps it for 2025 and for every other competition; the single-game samples stay;
- scripts/ncaa_source_probe.py withholds 2026's rate-and-margin lines (n stays), with ncaa-elo-v2's notice, for
  --year 2026 and for a file whose records carry season 2026 under another --year;
- the generic walks (backtest; soccer-backtest and its two sweeps) refuse NCAA with 2026 among their seasons (review
  on #561: "no command prints an outcome figure of the 2026 season")."""
import json
from datetime import datetime
from pathlib import Path

from click.testing import CliRunner

from src.walters import ncaa_backtest as nb

ROOT = Path(__file__).resolve().parent.parent
Q2 = ("YES, a 2026 fence, in v1r's form, as a SEPARATE small PR after #553 merges and before 2026-11-09: until v2's "
      "one run is recorded, no command prints an outcome figure of the 2026 season (a rate, a margin, a count of "
      "wins). ncaa-cfbd-coverage prints no 2026 home win rate or margin in either block (counts, coverage, census and "
      "neutral counts stay); ncaa-audit with 2026 among its seasons refuses, exit 2, naming this ruling (its default "
      "seasons become 2025 alone until the run); resync-diff --competition NCAA and scripts/ncaa_source_probe.py keep "
      "their single-game listings (the level ruling: a game with its score is how a defect is checked) and drop any "
      "aggregate outcome line over 2026. D9 of v2 already records every 2026 read to date; the fence keeps that list "
      "from growing. Gates bind more under the income goal, never less.")


def test_the_ruling_verbatim_and_the_fence_reads_only_the_registry(tmp_path):
    assert nb.V2_FENCE == Q2 and nb.V2_TEST == "2026" and nb.V2_EID == "ncaa-elo-v2"
    assert Q2 in " ".join((ROOT / "docs" / "specs" / "ncaa-elo-v2.md").read_text().split())
    p = tmp_path / "experiments.json"
    p.write_text(json.dumps([]))
    assert nb.v2_run_recorded(str(p)) is False                                  # absent entry: fenced
    p.write_text(json.dumps([{"id": nb.V2_EID, "run": None}]))
    assert nb.v2_run_recorded(str(p)) is False
    p.write_text(json.dumps([{"id": nb.V2_EID, "run": {"run_at": "2026-11-09T00:00:00Z"}}]))
    assert nb.v2_run_recorded(str(p)) is True
    assert nb.v2_run_recorded() is False                   # the committed registry: declared, unrun -> the fence stands


def _g(mid, season, hs, as_):
    return nb.Game(1 + mid % 3, 10 + mid % 3, season, datetime(int(season), 9, 1 + mid % 20), hs, as_,
                   label_source="cfbd", orientation="same", match_id=mid, season_type="regular")


def _stream_and_v1r():
    games = [_g(i, s, 30, 10) for s in ("2024", "2025", "2026") for i in range(1, 5)] + [_g(50, "2026", 7, 21)]
    v = nb.V1RStream(games=games, merge=nb.team_merge({}))
    for g in games:
        v.census.setdefault(g.season, {}).setdefault("regular", 0)
        v.census[g.season]["regular"] += 1
    return nb.build_stream(games), v


def test_coverage_withholds_every_2026_home_rate_in_both_blocks_and_keeps_counts(monkeypatch):
    st, v = _stream_and_v1r()
    fenced = []
    nb.coverage_report(st, out=fenced.append, fbs=None, v1r=v)                 # the committed registry: fenced
    text_ = "\n".join(fenced)
    l26 = [ln for ln in fenced if ln.startswith("  2026: walked ")]
    assert len(l26) == 1 and nb.V2_FENCED_RATE in l26[0] and "walked 5" in l26[0] and "regular" in l26[0]
    assert "0.800" not in text_                                                 # 2026's rate: 4 of 5
    rates = [ln for ln in fenced if ln.startswith("    home win rate: ")]
    w79 = [ln for ln in rates if nb.V2_FENCED_RATE in ln]
    assert len(w79) == 1 and "  2026: stream games" in text_                    # #79's block too
    assert w79[0].endswith("(n non-neutral 0, uncovered n 0)")                  # its counts stay beside the notice
    assert "  2025: walked 4" in text_ and "home win rate non-neutral 1.000 (n 4)" in text_     # 2025: unfenced
    assert "2025 non-neutral home rate for the sanity read" in text_
    monkeypatch.setattr(nb, "v2_run_recorded", lambda *a: True)                 # the run recorded: lines return
    opened = []
    nb.coverage_report(st, out=opened.append, fbs=None, v1r=v)
    text_ = "\n".join(opened)
    assert nb.V2_FENCED_RATE not in text_ and "home win rate non-neutral 0.800 (n 5)" in text_
    assert not [ln for ln in opened if ln.startswith("    home win rate: withheld")]
    flag = []
    nb.coverage_report(st, out=flag.append, fbs=None, v1r=v, fenced_v2=True)   # the explicit flag still withholds
    assert nb.V2_FENCED_RATE in "\n".join(flag)


def test_ncaa_audit_refuses_2026_before_reading_and_defaults_to_2025_alone(monkeypatch):
    from cli import cli
    from src.walters import ncaa_audit as na

    def boom(*a, **k):
        raise AssertionError("read before the fence")
    monkeypatch.setattr(na, "load", boom)
    for cmd in (["ncaa-audit", "--season", "2026"], ["ncaa-audit", "--season", "2025", "--season", "2026"]):
        res = CliRunner().invoke(cli, cmd)
        assert res.exit_code == 2, (cmd, res.output)
        assert "ncaa-audit REFUSED (exit 2): 2026 is among its seasons" in res.output
        assert nb.V2_FENCE_RULING in res.output and Q2 in res.output
    seen = []
    monkeypatch.setattr(na, "load", lambda top=20: "data")
    monkeypatch.setattr(na, "report", lambda data, seasons, limit, out: seen.append(seasons))
    assert CliRunner().invoke(cli, ["ncaa-audit"]).exit_code == 0
    assert CliRunner().invoke(cli, ["ncaa-audit", "--season", "2025"]).exit_code == 0
    assert seen == [("2025",), ("2025",)]                                       # the default: 2025 alone
    monkeypatch.setattr(nb, "v2_run_recorded", lambda *a: True)                 # after the run: both, 2026 allowed
    assert CliRunner().invoke(cli, ["ncaa-audit"]).exit_code == 0
    assert CliRunner().invoke(cli, ["ncaa-audit", "--season", "2026"]).exit_code == 0
    assert seen[2:] == [na.AUDIT_SEASONS, ("2026",)] and na.AUDIT_SEASONS == ("2025", "2026")


def test_resync_diff_withholds_the_ncaa_home_rate_when_the_listing_includes_2026(monkeypatch):
    import cli
    from src.ingestion import resync_diff as rd

    monkeypatch.setattr(cli, "_adapter_for_competition", lambda code: None)
    monkeypatch.setattr(rd, "diff", lambda *a, **k: {
        "source": "x", "listing": 3, "counts": {}, "home_rate": {"ours": ["0.612", 3], "provider": ["0.587", 3]},
        "samples": {"scores_different": ["id 9 · A 21-14 B vs provider 21-17"]}})
    monkeypatch.setattr(rd, "verdict", lambda c: "ok")
    for args, withheld in ((["--season", "2026"], True), ([], True), (["--season", ""], True),
                           (["--season", "  "], True), (["--season", "2025"], False)):
        out = CliRunner().invoke(cli.cli, ["resync-diff", "--competition", "NCAA", *args]).output
        if withheld:
            assert "0.612" not in out and "0.587" not in out and nb.V2_FENCED_RATE in out, (args, out)
            assert "(n ours=3, provider=3)" in out                              # n stays
        else:
            assert "ours 0.612" in out and nb.V2_FENCED_RATE not in out, (args, out)
        assert "id 9 · A 21-14 B vs provider 21-17" in out                     # single-game listings stay
    out = CliRunner().invoke(cli.cli, ["resync-diff", "--competition", "NFL", "--season", "2026"]).output
    assert "ours 0.612" in out                                                  # another competition: unfenced
    monkeypatch.setattr(nb, "v2_run_recorded", lambda *a: True)
    out = CliRunner().invoke(cli.cli, ["resync-diff", "--competition", "NCAA", "--season", "2026"]).output
    assert "ours 0.612" in out                                                  # the run recorded: the line returns


def test_the_source_probe_withholds_2026s_rate_and_margin_lines(monkeypatch, tmp_path, capsys):
    from src.db.database import init_db
    from test_ncaa_source_probe import RECS, nsp            # not its world(): that file's first join test seeds it
    init_db()                                               # the tables only (the throwaway DB); no row is added
    assert nsp.fenced(2026) and nsp.fenced("2026")
    assert nsp.fenced_notice(2026) == nb.V2_FENCED_RATE and nsp.fenced_notice(2025) == nb.FENCED_RATE
    assert not nsp.fenced(2025) and not nsp.fenced(2024)                       # v1r's run is recorded
    p, p26 = tmp_path / "cfbd.json", tmp_path / "cfbd_2026.json"
    p.write_text(json.dumps(RECS))                                             # records of season 2077
    p26.write_text(json.dumps([dict(r, season=2026) for r in RECS]))           # the same, carrying season 2026

    def blocks(argv):
        assert nsp.main(argv) == 0
        out = capsys.readouterr().out
        assert "counts: " in out and "join rate: " in out                       # the rest of the receipt stays
        return [ln for ln in out.splitlines() if ln.startswith(("  nonneutral: SOURCE n ", "  neutral: SOURCE n "))]
    for argv in (["--year", "2026", "--from-file", str(p)],                     # --year 2026
                 ["--year", "2077", "--from-file", str(p26)],                   # a 2026 file under another --year
                 ["--year", "2026", "--year", "2025", "--from-file", str(p26)]):
        lines = blocks(argv)
        assert len(lines) == 2 * argv.count("--year"), (argv, lines)
        for ln in lines:
            assert nb.V2_FENCED_RATE in ln and " · OURS on joined n " in ln, (argv, ln)
            assert "home rate 0." not in ln and "home rate 1." not in ln and "margin +" not in ln, (argv, ln)
    assert all(nb.V2_FENCED_RATE not in ln for ln in blocks(["--year", "2077", "--from-file", str(p)]))
    monkeypatch.setattr(nb, "v2_run_recorded", lambda *a: True)                # the run recorded: the lines return
    assert not nsp.fenced(2026)
    lines = blocks(["--year", "2026", "--from-file", str(p26)])
    assert all(nb.V2_FENCED_RATE not in ln for ln in lines) and "nonneutral: SOURCE n 3 home rate " in lines[0]


def test_the_generic_walks_refuse_ncaa_with_2026_among_their_seasons(monkeypatch):
    """backtest and soccer-backtest (with the rho and coefficient sweeps) walk whatever competition they are given:
    NCAA with 2026 among its seasons (no --season: every season) is refused, exit 2, naming the ruling, before the
    walk reads a game. Every other competition and season passes, and the run recorded lifts it."""
    from cli import cli
    assert nb.v2_fence_walk("NCAA", "2026") and nb.v2_fence_walk("ncaa", " 2026 ") and nb.v2_fence_walk("NCAA", None)
    assert nb.v2_fence_walk("NCAA", "") and nb.V2_FENCE_RULING in nb.v2_fence_walk("NCAA", None)
    assert nb.v2_fence_walk("NCAA", "2025") is None and nb.v2_fence_walk("PL", "2026") is None
    assert nb.v2_fence_walk("NFL", None) is None and nb.v2_fence_walk("MLB", "2026") is None
    for cmd in (["backtest", "--competition", "NCAA", "--season", "2026"],
                ["soccer-backtest", "--competition", "NCAA", "--season", "2026"],
                ["soccer-backtest", "--competition", "NCAA"],
                ["dixon-coles-sweep", "--competition", "NCAA"],
                ["elo-coeff-sweep", "--competition", "NCAA", "--season", "2026"]):
        res = CliRunner().invoke(cli, cmd)
        assert res.exit_code == 2, (cmd, res.output)
        assert "REFUSED" in " ".join(res.output.split()) and "addendum 86" in " ".join(res.output.split()), cmd
    monkeypatch.setattr(nb, "v2_run_recorded", lambda *a: True)
    assert nb.v2_fence_walk("NCAA", "2026") is None and nb.v2_fence_walk("NCAA", None) is None
