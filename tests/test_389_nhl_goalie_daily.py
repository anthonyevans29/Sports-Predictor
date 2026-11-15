"""THE DAILY GOALIE STEP (ARCHITECT 2026-11-15 09:50 ET, addendum 389 item 3), verbatim in part: "(a) THE STEP:
["nhl-goalie-sync", "--start", "{yesterday}", "--end", "{today}"] in nhl-daily, after export-fixtures and before
nhl-shot-sync. (b) UNMETERED gains "nhl-goalie-sync", beside nhl-shot-sync [...] (c) nhl-daily's go_on names it: a failed
goalie step is receipted and paged as a sync-step failure and stops nothing after it. Its go_on_why cites this item.
(d) A FAILURE THAT READS AS ONE: nhl-goalie-sync exits non-zero when any schedule or boxscore request of the run answered
other than 200. It still prints its counts line and its coverage lines first, and what it parsed is still written (the
upsert is unchanged). No flag: it holds for a hand run and for --dry-run as for the chain. [...] (e) A REFUSAL IS NOT A
FAILURE: REFUSED games and "not in our DB" stay counted and printed, exit 0. [...] (g) No new placeholder, no wider
window in this PR."

Synthetic throughout: the NHL API is never reached (a fake fetch through the real sync), the DB is the tests' throwaway
file, sp_run runs a fake cli.py in a tmp checkout. Never data/."""
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))

import chains  # noqa: E402
import sp_common as c  # noqa: E402
import sp_run  # noqa: E402

from src.db.database import init_db, session_scope  # noqa: E402
from src.db.schema import NHLGoalieAppearance  # noqa: E402
from src.ingestion import nhl_goalies as ngs  # noqa: E402
from tests.test_hosting_pack import receipts, sandbox  # noqa: E402,F401  (the sp_run sandbox: tmp receipts/lock)
from tests.test_nhl_goalie import box, goalie, sched, sgame, side  # noqa: E402

STEP = ["nhl-goalie-sync", "--start", "{yesterday}", "--end", "{today}"]
DAY = date(2026, 11, 16)


# ------------------------------------------------------------------ (d), (e): which counters are failures

def test_failed_requests_are_every_code_but_200_and_never_a_refusal():
    counts = {"schedule_calls": 2, "schedule_http_200": 1, "schedule_http_0": 1, "boxscore_calls": 4,
              "boxscore_http_200": 1, "boxscore_http_404": 1, "boxscore_http_503": 2, "boxscore_http_301": 0,
              "refused_unsided": 3, "not_in_our_db": 5, "skipped_game_type_1": 2, "rows_written": 4}
    assert ngs.failed_requests(counts) == {"boxscore_http_404": 1, "boxscore_http_503": 2, "schedule_http_0": 1}
    assert ngs.failure_line(counts, dry_run=False) == (
        "✗ NHL-GOALIE-SYNC: 4 of 6 request(s) answered other than 200 (boxscore_http_404 1 · boxscore_http_503 2 · "
        "schedule_http_0 1); what was parsed is written; exit 1 (addendum 389 item 3(d))")
    assert "nothing written (dry run)" in ngs.failure_line(counts, dry_run=True)
    clean = {"schedule_calls": 1, "schedule_http_200": 1, "refused_unsided": 2, "not_in_our_db": 7}
    assert ngs.failed_requests(clean) == {} and ngs.failure_line(clean, dry_run=False) is None
    assert ngs.failed_requests({}) == {}                                        # a run that made no request
    assert ngs.PROVIDER_FAILURE_EXIT == 1


def test_the_failure_line_is_not_a_transient_class_so_sp_run_does_not_retry_it():
    """The line names no class sp_run retries (connection, timeout, 5xx Server Error, 429): the page is the catch (g)."""
    line = ngs.failure_line({"schedule_calls": 1, "boxscore_calls": 2, "schedule_http_0": 1,
                             "boxscore_http_503": 1, "boxscore_http_429": 1}, dry_run=False)
    assert sp_run.transient_class(1, ["NHL-GOALIE COVERAGE · 0 appearance rows", line]) is None


# ------------------------------------------------------------------ (d), (e): the command end to end

T0 = datetime(2025, 1, 10, 0, 0)                  # past: every game is finished by the code's 6-hour rule


def _week(*games):
    return sched(*[sgame(gid, T0 + timedelta(hours=i), side("NJD", "New Jersey", "Devils"),
                         side("NYR", "New York", "Rangers")) for i, gid in enumerate(games)])


def _run(monkeypatch, fetch, *args):
    real = ngs.sync
    monkeypatch.setattr(ngs, "sync", lambda *a, **k: real(*a, **{**k, "fetch": fetch}))
    import cli
    return CliRunner().invoke(cli.cli, ["nhl-goalie-sync", "--start", "2025-01-09", "--end", "2025-01-10",
                                        "--sleep", "0", *args])


def _fetch(week, boxes):
    def fetch(url):
        if "/schedule/" in url:
            return week
        return boxes[int(url.split("/gamecenter/")[1].split("/")[0])]
    return fetch


def _stored(*gids):
    with session_scope() as s:
        return sorted({a.nhl_game_id for a in s.execute(select(NHLGoalieAppearance).where(
            NHLGoalieAppearance.nhl_game_id.in_(gids))).scalars()})


def test_a_failed_boxscore_exits_1_last_after_counts_and_coverage_and_what_parsed_is_written(monkeypatch):
    init_db()
    ok = box([goalie(38911, "G", True, 20, 22)], [goalie(38912, "H", True, 25, 26)])
    r = _run(monkeypatch, _fetch((200, _week(38901, 38902)), {38901: (200, ok), 38902: (503, None)}))
    assert r.exit_code == 1, r.output
    out = r.output.splitlines()
    assert out[-1] == ("✗ NHL-GOALIE-SYNC: 1 of 3 request(s) answered other than 200 (boxscore_http_503 1); what was "
                       "parsed is written; exit 1 (addendum 389 item 3(d))")
    counts = next(i for i, x in enumerate(out) if x.startswith("  counts: "))
    cov = next(i for i, x in enumerate(out) if x.startswith("NHL-GOALIE COVERAGE · "))
    assert counts < cov < len(out) - 1                                          # counts, then coverage, then the line
    assert "boxscore_http_503 1" in out[counts] and "boxscore_http_200 1" in out[counts]
    assert "refused_unsided" not in out[counts] and "REFUSED game" not in r.output   # a failure is not a refusal (3(e))
    assert _stored(38901, 38902) == [38901]                                     # the parsed game is written (upsert)


class _Answer:
    """urlopen's answer, cut short: a 200 whose read() raises http.client.IncompleteRead (not an OSError)."""
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        import http.client
        raise http.client.IncompleteRead(b'{"playerByGameStats": ', 4096)


def test_sync_fetch_counts_an_answer_cut_short_as_no_usable_answer(monkeypatch):
    import http.client
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Answer())
    with pytest.raises(http.client.IncompleteRead):
        ngs.http_json("https://api-web.nhle.com/v1/gamecenter/1/boxscore")     # http_json as it is (#1018)
    assert ngs.sync_fetch("https://api-web.nhle.com/v1/gamecenter/1/boxscore") == (0, None)
    assert ngs.sync.__defaults__[0] is ngs.sync_fetch                           # the goalie sync's own default
    from src.ingestion import nhl_shots
    assert nhl_shots.sync.__defaults__[0] is ngs.http_json                      # the shot sync is untouched (#1018)


def test_an_answer_cut_short_still_prints_counts_and_coverage_and_the_window_goes_on(monkeypatch):
    """Through the command's own default fetch: the first boxscore is cut short (IncompleteRead), the second is read
    and written, and the run exits 1 with its counts, coverage and failure lines, no traceback."""
    import http.client
    init_db()
    ok = box([goalie(38991, "G", True, 20, 22)], [goalie(38992, "H", True, 25, 26)])
    week = _week(38981, 38982)

    def http_json(url, timeout=20):
        if "/schedule/" in url:
            return 200, week
        if "/gamecenter/38981/" in url:
            raise http.client.IncompleteRead(b"", 100)
        return 200, ok
    monkeypatch.setattr(ngs, "http_json", http_json)
    import cli
    r = CliRunner().invoke(cli.cli, ["nhl-goalie-sync", "--start", "2025-01-09", "--end", "2025-01-10", "--sleep", "0"])
    assert r.exit_code == 1 and isinstance(r.exception, SystemExit), r.output    # exit 1, not a traceback
    out = r.output.splitlines()
    assert any(x.startswith("  counts: ") and "boxscore_http_0 1" in x for x in out)
    assert any(x.startswith("NHL-GOALIE COVERAGE · ") for x in out)
    assert out[-1].startswith("✗ NHL-GOALIE-SYNC: 1 of 3 request(s) answered other than 200 (boxscore_http_0 1);")
    assert _stored(38981, 38982) == [38982]                                     # the game after it was still asked


def test_a_failed_schedule_read_exits_1_even_with_nothing_else_asked(monkeypatch):
    init_db()
    r = _run(monkeypatch, _fetch((0, None), {}))                                # no usable answer: code 0
    assert r.exit_code == 1, r.output
    assert r.output.splitlines()[-1].startswith("✗ NHL-GOALIE-SYNC: 1 of 1 request(s) answered other than 200 "
                                                "(schedule_http_0 1);")


def test_dry_run_exits_1_alike_and_writes_nothing(monkeypatch):
    init_db()
    ok = box([goalie(38931, "G", True, 20, 22)], [goalie(38932, "H", True, 25, 26)])
    r = _run(monkeypatch, _fetch((200, _week(38921, 38922)), {38921: (200, ok), 38922: (404, None)}), "--dry-run")
    assert r.exit_code == 1, r.output
    assert r.output.splitlines()[-1] == (
        "✗ NHL-GOALIE-SYNC: 1 of 3 request(s) answered other than 200 (boxscore_http_404 1); nothing written (dry run); "
        "exit 1 (addendum 389 item 3(d))")
    assert _stored(38921, 38922) == []


def test_a_refused_game_and_a_game_not_in_our_db_stay_exit_0(monkeypatch):
    """(e): the unsided boxscore is REFUSED (counted, printed) and no game maps to a match of ours: exit 0."""
    init_db()
    ok = box([goalie(38951, "G", True, 20, 22)], [goalie(38952, "H", True, 25, 26)])
    r = _run(monkeypatch, _fetch((200, _week(38941, 38942)), {38941: (200, ok), 38942: (200, {"goalies": []})}))
    assert r.exit_code == 0, r.output
    assert "refused_unsided 1" in r.output and "not_in_our_db 2" in r.output
    assert "  REFUSED game 38942: goalie lists ['goalies']" in r.output
    assert "✗ NHL-GOALIE-SYNC" not in r.output
    assert _stored(38941, 38942) == [38941]


def test_every_request_200_is_exit_0(monkeypatch):
    init_db()
    ok = box([goalie(38971, "G", True, 20, 22)], [goalie(38972, "H", True, 25, 26)])
    r = _run(monkeypatch, _fetch((200, _week(38961)), {38961: (200, ok)}))
    assert r.exit_code == 0, r.output
    assert "✗ NHL-GOALIE-SYNC" not in r.output
    out = r.output.splitlines()
    cov = next(i for i, x in enumerate(out) if x.startswith("NHL-GOALIE COVERAGE · "))
    assert all(x.startswith("  ") for x in out[cov + 1:])                        # the coverage block ends the run


# ------------------------------------------------------------------ (a), (b), (c), (g): the chain

def test_the_step_is_on_nhl_daily_once_after_export_fixtures_before_the_shot_sync():
    assert chains.NHL_GOALIE_STEP == STEP
    steps = chains.CHAINS["nhl-daily"]["steps"]
    cmds = [s[0] for s in steps]
    assert [s for s in steps if s[0] == "nhl-goalie-sync"] == [STEP]
    assert cmds.index("export-fixtures") + 1 == cmds.index("nhl-goalie-sync") == cmds.index("nhl-shot-sync") - 1
    assert cmds[-2:] == ["nhl-shot-sync", "export-nhl-predictions"]             # the shadow's tail, as it was
    # no other chain carries it, and no new placeholder or wider window: {yesterday}..{today}, the shot sync's own
    assert [n for n, x in chains.CHAINS.items() if any(s and s[0] == "nhl-goalie-sync" for s in x.get("steps") or [])] \
        == ["nhl-daily"]
    shot = next(s for s in steps if s[0] == "nhl-shot-sync")
    assert STEP[1:] == shot[1:5]
    resolved = sp_run.resolve("nhl-daily", {}, DAY)
    assert ["nhl-goalie-sync", "--start", "2026-11-15", "--end", "2026-11-16"] in resolved


def test_the_step_is_unmetered_beside_the_shot_sync(sandbox, monkeypatch):
    assert {"nhl-goalie-sync", "nhl-shot-sync"} <= chains.UNMETERED
    monkeypatch.setenv("SP_PARALLEL_MODE", "designated")
    monkeypatch.setenv("SP_DESIGNATED_DAYS", "Fri")
    assert not sp_run.metered_skip("nhl-goalie-sync", DAY)                      # a Monday not designated: still runs
    assert sp_run.metered_skip("sync-matches", DAY)                             # control: a metered step is skipped


def test_go_on_names_it_with_its_own_reason():
    ch = chains.CHAINS["nhl-daily"]
    assert ch["go_on"] == ("nhl-goalie-sync",) and ch["go_on_why"] == chains.NHL_GOALIE_GO_ON
    assert chains.NHL_GOALIE_GO_ON.startswith("addendum 389 item 3(c): ")
    assert not ch.get("continue_on_sync_failure")                                # not the wider flag


FAKE_CLI = """import sys
a = sys.argv[1:]
print("ran", " ".join(a))
if a[0] == "nhl-goalie-sync":
    print("✗ NHL-GOALIE-SYNC: 1 of 3 request(s) answered other than 200 (boxscore_http_503 1); what was parsed is "
          "written; exit 1 (addendum 389 item 3(d))")
    sys.exit(1)
if a[0] == "export-fixtures" and "{fail}" == "fixtures":
    print("export failed")
    sys.exit(1)
"""


@pytest.fixture
def at_1600(monkeypatch):
    monkeypatch.setattr(c, "utc_now", lambda: datetime(2026, 11, 16, 16, 0, tzinfo=timezone.utc))   # the timer's tick


def test_a_failed_goalie_step_is_receipted_pages_and_the_shadow_steps_still_run(sandbox, at_1600, capsys):
    (c.REPO / "cli.py").write_text(FAKE_CLI.replace("{fail}", "none"))
    capsys.readouterr()
    assert sp_run.main(["nhl-daily"]) == 1                                       # the chain's exit: OnFailure pages
    out = capsys.readouterr().out
    rs = receipts(sandbox)
    steps = [r for r in rs if r["kind"] == "step"]
    cmds = [s["command"].split()[2] for s in steps]
    assert cmds[-3:] == ["nhl-goalie-sync", "nhl-shot-sync", "export-nhl-predictions"]
    g = steps[cmds.index("nhl-goalie-sync")]
    assert g["exit"] == 1 and g["continued"] == chains.NHL_GOALIE_GO_ON
    assert g["tail"][-1].startswith("✗ NHL-GOALIE-SYNC: 1 of 3 request(s)")     # the receipt keeps the line
    assert "retried" not in g                                                   # not a transient class
    assert all("continued" not in s for s in steps if s is not g)
    assert steps[-1]["exit"] == 0 and steps[-2]["exit"] == 0                    # the shot sync and the shadow ran
    chain = rs[-1]
    assert chain["kind"] == "chain" and chain["exit"] == 1 and chain["stopped_at"] is None
    assert chain["steps_ok"] == len(steps) - 1
    n = cmds.index("nhl-goalie-sync") + 1
    assert chain["failed_steps"] == [{"step": n, "exit": 1, "command":
                                      "python cli.py nhl-goalie-sync --start 2026-11-15 --end 2026-11-16"}]
    assert (f"· step {n}/{len(steps)} failed (exit 1): python cli.py nhl-goalie-sync --start 2026-11-15 --end "
            "2026-11-16 — recorded; the chain runs on to every later step on the stored state, the exit stays the "
            "first failure's (addendum 389 item 3(c))") in out
    assert "stopped at step" not in out


def test_without_go_on_the_same_failure_would_stop_the_shadow_steps(sandbox, at_1600):
    """Control: run_steps without the chain's go_on stops at the goalie step, so the shadow would go dark."""
    (c.REPO / "cli.py").write_text(FAKE_CLI.replace("{fail}", "none"))
    rest = [["nhl-shot-sync", "--start", "2026-11-15", "--end", "2026-11-16"], ["export-nhl-predictions"]]
    rep = {}
    rc, ok = sp_run.run_steps([[*STEP[:2], "2026-11-15", STEP[3], "2026-11-16"], *rest], "t", "u", "r", DAY,
                              sp_run.new_quota(), report=rep)
    assert (rc, ok, rep["stopped_at"]) == (1, 0, 1)


def test_a_failed_step_before_it_still_stops_the_chain_as_before(sandbox, at_1600, capsys):
    """Only the goalie step goes on: a failed export-fixtures stops nhl-daily before it, as it did."""
    (c.REPO / "cli.py").write_text(FAKE_CLI.replace("{fail}", "fixtures"))
    assert sp_run.main(["nhl-daily"]) == 1
    chain = receipts(sandbox)[-1]
    assert chain["stopped_at"] is not None and "ran nhl-goalie-sync" not in capsys.readouterr().out
