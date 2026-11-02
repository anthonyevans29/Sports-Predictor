"""#765 + #728, RULED as one lane (ARCHITECT 2026-11-01 14:00 ET, addendum 204 item 3), verbatim in part: "(a) the
weekly full-season chain runs `sync-teams --competition CODE --season SEASON` immediately before each `sync-matches`
line of SP_FULLSEASON_LIST, under the same DB lock, teams-before-matches per competition as the law says; its receipt
line per competition carries sync-teams' created/updated and sync-matches' skipped count. Read first (law 1) how
`sync-teams --competition MLB` routes on the host [...] and keep that routing. (b) intl-daily runs the same sync-teams
step before each cup's sync-matches (four calls a day [...]). (c) sync_matches' skipped-listings warning becomes a
line the chain prints in its own receipt (the journal digest shows it), never only a log warning: "skipped N
listing(s) of clubs not in the DB: <ids>", and a chain step with N > 0 says so in the chain's summary line. It stays
exit 0 (law 4: the listings are skipped, not faked), but it is never silent again."

Synthetic throughout: a fake adapter on a throwaway SQLite file, a fake cli.py in a tmp checkout for sp_run; no
network, never data/."""
import json
import sys
from datetime import date, datetime
from pathlib import Path

import pytest
from click.testing import CliRunner
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))

import chains  # noqa: E402
import sp_common as c  # noqa: E402
import sp_receipts  # noqa: E402
import sp_run  # noqa: E402

from tests.test_hosting_pack import receipts, sandbox  # noqa: E402,F401  (the sp_run sandbox: tmp receipts/lock)


# ------------------------------------------------------------------ (a) the weekly chain's steps

def test_the_weekly_chain_runs_sync_teams_immediately_before_each_sync_matches_line_in_order(sandbox, monkeypatch):
    lst = sandbox / "fs.list"
    lst.write_text("# the host's list\nPL|2026/27\nFAC|2026/27\n\nNFL|2026\nMLB|2026\n")
    monkeypatch.setenv("SP_FULLSEASON_LIST", str(lst))
    steps = sp_run.resolve("weekly-fullseason", {}, date(2026, 11, 1))
    assert steps == [[verb, "--competition", code, "--season", season]
                     for code, season in (("PL", "2026/27"), ("FAC", "2026/27"), ("NFL", "2026"), ("MLB", "2026"))
                     for verb in ("sync-teams", "sync-matches")]
    assert steps == sp_run.fullseason_steps()                     # the one path (resolve and the readout's)
    # the MLB line is the same two plain steps: no special case here; cli.py routes it (below)
    assert ["sync-teams", "--competition", "MLB", "--season", "2026"] in steps


def test_every_new_step_is_a_real_cli_command_and_option():
    """Law 1: the steps this lane adds name commands and options cli.py defines (test_hosting_pack checks the static
    chains; the full-season chain is DB/list-planned, so it is checked here)."""
    import cli
    for st in (["sync-teams", "--competition", "PL", "--season", "2026/27"],
               *chains.CHAINS["intl-daily"]["steps"][3:]):
        cmd = cli.cli.commands[st[0]]
        opts = {o for p in cmd.params for o in (*p.opts, *p.secondary_opts)}
        assert all(t in opts for t in st[1:] if t.startswith("--")), st


def test_the_readout_still_counts_one_competition_per_line(sandbox, monkeypatch):
    """cutover-readiness counts the list through sp_run.fullseason_resolve: two steps per line now, one competition."""
    import cutover_readiness as cr
    lst = sandbox / "fs.list"
    lst.write_text("PL|2026/27\nNFL|2026\n")
    st = cr.fullseason_state(str(lst), date(2026, 11, 1))
    assert st["state"] == "ok" and st["entries"] == ["PL|2026/27", "NFL|2026"]
    assert len(sp_run.fullseason_resolve(str(lst), sp_run.date_vars(date(2026, 11, 1)))) == 4


# ------------------------------------------------------------------ (b) intl-daily

def test_intl_daily_runs_sync_teams_before_each_cups_sync_matches_four_a_day():
    steps = chains.CHAINS["intl-daily"]["steps"]
    cups = steps[3:]
    assert [s[0] for s in cups] == ["sync-teams", "sync-matches"] * 4
    assert [s[2] for s in cups] == [code for code in chains.CUP_SCHEDULE for _ in range(2)]
    assert all(cups[k][1:] == cups[k + 1][1:] for k in range(0, 8, 2))       # same competition-season, teams first
    assert sum(s[0] == "sync-teams" for s in steps) == 4                      # "four calls a day"
    assert "sync-teams" not in chains.UNMETERED                              # a provider call: metered, as sync-matches


# ------------------------------------------------------------------ MLB keeps its routing

def test_sync_teams_mlb_keeps_the_api_sports_fallback_routing_on_the_host(monkeypatch, tmp_path):
    """Law 1 (cli.py): with SP_SKIP_FAMILIES naming MLB, `sync-teams --competition MLB` runs the api-sports fallback's
    own sync_teams (cli._mlb_fallback_run("teams", season)), never the IngestionService; elsewhere it does not."""
    import cli
    monkeypatch.setenv("SP_LOCK", str(tmp_path / "db.lock"))
    monkeypatch.delenv(c.HELD_ENV, raising=False)
    seen = []
    monkeypatch.setattr(cli, "_mlb_fallback_run", lambda kind, season, *a: seen.append((kind, season)))
    monkeypatch.setattr(cli, "IngestionService", lambda *a, **k: pytest.fail("the fallback host never reaches it"))
    monkeypatch.setenv("SP_SKIP_FAMILIES", "MLB")
    r = CliRunner().invoke(cli.cli, ["sync-teams", "--competition", "MLB", "--season", "2026"])
    assert r.exit_code == 0, r.output
    assert seen == [("teams", "2026")]
    monkeypatch.delenv("SP_SKIP_FAMILIES")
    assert not cli._mlb_fallback("MLB") and not cli._mlb_fallback("PL")


def test_the_fallback_teams_line_is_read_with_no_updated_count():
    """The fallback prints its own teams line (no `updated`): the receipt carries created and null, never a guess."""
    out = sp_run.sync_counts(["MLB via api-sports Baseball FALLBACK (SP_SKIP_FAMILIES names MLB; statsapi is the "
                              "laptop's path)",
                              "  teams 2026: provider 32 · created 0 · stamped 0 · existing 30 · linked 1 · non-club "
                              "skipped ['AL'] · ambiguous name []"])
    assert out["teams"]["created"] == 0 and out["teams"]["updated"] is None
    assert (out["teams"]["existing"], out["teams"]["linked"]) == (30, 1) and "fallback" in out["teams"]["via"]


# ------------------------------------------------------------------ (c) the printed line, real commands

class _Cup:
    """A fake soccer adapter: FAC's listing names clubs 10 and 11 (team-synced) and 12, 13 (never team-synced)."""
    source_name = "api_football"

    def __init__(self, team_ids):
        self.team_ids = team_ids

    def list_teams(self, code, season=None):
        from src.adapters.normalized import NormalizedTeam
        from src.db.schema import Sport
        return [NormalizedTeam(sport=Sport.SOCCER, name=f"Club {i}", source="api_football", source_id=str(i))
                for i in self.team_ids]

    def list_matches(self, code, season=None, date_from=None, date_to=None):
        from src.adapters.normalized import NormalizedMatch
        from src.db.schema import MatchStatus, Sport
        return [NormalizedMatch(sport=Sport.SOCCER, competition_code="FAC", season="2026/27",
                                utc_date=datetime(2026, 11, 7, 15), status=MatchStatus.SCHEDULED,
                                home_team_source_id=h, away_team_source_id=a, source="api_football",
                                source_id=sid)
                for sid, h, a in (("9001", "10", "11"), ("9002", "10", "12"), ("9003", "12", "13"))]


@pytest.fixture
def cup_db(tmp_path, monkeypatch):
    """A throwaway DB of its own holding competition FAC (tests/test_match_series_fields.py's fresh_db pattern)."""
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db
    from src.db.schema import Competition, Sport
    eng = create_engine(f"sqlite:///{tmp_path / 'cup.db'}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                         expire_on_commit=False))
    monkeypatch.delenv("SP_SKIP_FAMILIES", raising=False)
    monkeypatch.setenv("SP_LOCK", str(tmp_path / "db.lock"))
    monkeypatch.delenv(c.HELD_ENV, raising=False)
    db.init_db()
    with db.session_scope() as s:
        s.add(Competition(sport=Sport.SOCCER, code="FAC", name="FA Cup", area="England", type="CUP"))
    yield eng
    eng.dispose()


def _cli(monkeypatch, adapter, *argv):
    import cli
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda code: adapter)
    return CliRunner().invoke(cli.cli, list(argv))


def test_sync_matches_prints_the_ruled_line_with_the_ids_and_exits_0(cup_db, monkeypatch):
    r = _cli(monkeypatch, _Cup([10, 11]), "sync-teams", "--competition", "FAC", "--season", "2026/27")
    assert r.exit_code == 0, r.output
    teams = sp_run.sync_counts(r.output.splitlines())
    assert teams == {"teams": {"created": 2, "updated": 0, "skipped": 0}}
    r = _cli(monkeypatch, _Cup([10, 11]), "sync-matches", "--competition", "FAC", "--season", "2026/27")
    assert r.exit_code == 0, r.output                                        # law 4: skipped, not faked; exit 0
    lines = r.output.splitlines()
    assert "skipped 2 listing(s) of clubs not in the DB: 9002, 9003" in lines        # verbatim, its own line
    got = sp_run.sync_counts(lines)
    assert got["matches"] == {"created": 1, "updated": 0, "skipped": 2}
    assert got["not_in_db"] == {"n": 2, "ids": ["9002", "9003"]}
    # the next run, after a sync-teams that brings the new clubs: nothing skipped, and no line at all
    assert _cli(monkeypatch, _Cup([10, 11, 12, 13]), "sync-teams", "--competition", "FAC",
                "--season", "2026/27").exit_code == 0
    r = _cli(monkeypatch, _Cup([10, 11]), "sync-matches", "--competition", "FAC", "--season", "2026/27")
    assert r.exit_code == 0 and "listing(s) of clubs not in the DB" not in r.output, r.output
    assert sp_run.sync_counts(r.output.splitlines())["matches"] == {"created": 2, "updated": 1, "skipped": 0}


def test_the_service_records_the_ids_and_the_line_is_the_ruled_text(cup_db):
    from src.ingestion.service import IngestionService, skipped_listings_line
    svc = IngestionService(_Cup([10, 11]))
    svc.sync_teams("FAC", "2026/27")
    res = svc.sync_matches("FAC", season="2026/27")
    assert res.skipped_ids == ["9002", "9003"] and res.skipped == 2
    assert str(res) == "created=1 updated=0 skipped=2"                       # __str__ unchanged
    assert skipped_listings_line(res.skipped_ids) == "skipped 2 listing(s) of clubs not in the DB: 9002, 9003"


# ------------------------------------------------------------------ (a) + (c) through sp_run

FAKE_SYNC_CLI = '''import sys
a = sys.argv[1:]
code = a[a.index("--competition") + 1]
print("ran", " ".join(a))
if a[0] == "sync-teams":
    print("[log] sync_teams(%s): created=1 updated=30 skipped=0" % code)
    print("✓ Teams (%s): created=%d updated=30 skipped=0" % (code, 2 if code == "FAC" else 0))
    for k in range(8):                       # more lines than the receipt tail keeps: the count is read as it streams
        print("  names line", k)
elif a[0] == "sync-matches":
    if code == "FAC":
        print("✓ Matches (FAC): created=0 updated=40 skipped=23")   # 21 not in the DB + 2 re-key refusals
        print("skipped 21 listing(s) of clubs not in the DB: " + ", ".join(str(1200 + k) for k in range(21)))
    else:
        print("✓ Matches (%s): created=0 updated=10 skipped=0" % code)
'''


def test_the_chain_receipt_carries_each_competitions_line_and_the_summary_names_the_skipping_step(sandbox,
                                                                                                    monkeypatch,
                                                                                                    capsys):
    (c.REPO / "cli.py").write_text(FAKE_SYNC_CLI)
    lst = sandbox / "fs.list"
    lst.write_text("PL|2026/27\nFAC|2026/27\n")
    monkeypatch.setenv("SP_FULLSEASON_LIST", str(lst))
    capsys.readouterr()
    assert sp_run.main(["weekly-fullseason"]) == 0                            # exit 0: skipped, not faked
    out = capsys.readouterr().out.rstrip("\n").split("\n")
    rs = receipts(sandbox)
    steps = [r for r in rs if r["kind"] == "step"]
    assert [s["command"].split()[2] for s in steps] == ["sync-teams", "sync-matches"] * 2
    assert steps[2]["sync"] == {"teams": {"created": 2, "updated": 30, "skipped": 0}}
    assert steps[3]["sync"]["not_in_db"]["n"] == 21 and steps[3]["exit"] == 0
    chain = rs[-1]
    assert chain["kind"] == "chain" and chain["exit"] == 0 and chain["steps_ok"] == 4
    assert chain["competitions"] == [
        {"competition": "PL", "season": "2026/27", "teams_step": 1, "teams_exit": 0, "teams_created": 0,
         "teams_updated": 30, "matches_step": 2, "matches_exit": 0, "matches_skipped": 0, "not_in_db": 0},
        {"competition": "FAC", "season": "2026/27", "teams_step": 3, "teams_exit": 0, "teams_created": 2,
         "teams_updated": 30, "matches_step": 4, "matches_exit": 0, "matches_skipped": 23, "not_in_db": 21}]
    assert chain["listings_skipped"] == [{"step": 4, "command": "python cli.py sync-matches --competition FAC "
                                          "--season 2026/27", "n": 21, "ids": [str(1200 + k) for k in range(21)]}]
    text = "\n".join(out)
    assert "  · PL 2026/27: sync-teams created 0 · updated 30 · sync-matches skipped 0" in out
    assert ("  · FAC 2026/27: sync-teams created 2 · updated 30 · sync-matches skipped 23 (21 of clubs not in the DB)"
            in out)
    assert "⚠ step 4/4 skipped 21 listing(s) of clubs not in the DB (exit stays 0: skipped, not faked)" in text
    summary = next(x for x in out if x.startswith("✓ weekly-fullseason: exit=0 steps 4/4"))
    assert " · listings skipped (clubs not in the DB): step 4/4 FAC 21 · running " in summary
    assert out[-1].startswith("  ⚠ step 4/4 python cli.py sync-matches --competition FAC --season 2026/27: "
                              "skipped 21 listing(s) of clubs not in the DB: 1200, 1201, ")
    # the receipts table's chain key line says so too
    assert sp_receipts.key_line(chain).startswith("steps 4/4; exports 0; listings skipped (clubs not in the DB) 21 "
                                                  "in 1 step(s)")


def test_a_chain_with_nothing_skipped_says_nothing_extra(sandbox, monkeypatch, capsys):
    (c.REPO / "cli.py").write_text(FAKE_SYNC_CLI)
    lst = sandbox / "fs.list"
    lst.write_text("PL|2026/27\n")
    monkeypatch.setenv("SP_FULLSEASON_LIST", str(lst))
    capsys.readouterr()
    assert sp_run.main(["weekly-fullseason"]) == 0
    out = capsys.readouterr().out
    chain = receipts(sandbox)[-1]
    assert "listings_skipped" not in chain and len(chain["competitions"]) == 1
    assert "listings skipped" not in out and "⚠" not in out
    assert "listings skipped" not in sp_receipts.key_line(chain)


def test_a_chain_without_sync_steps_gets_no_competition_lines(sandbox, monkeypatch):
    from tests.test_hosting_pack import FAKE_CLI
    (c.REPO / "cli.py").write_text(FAKE_CLI)
    monkeypatch.setitem(chains.CHAINS, "t-plain-765", {"steps": [["one"], ["two"]]})
    assert sp_run.main(["t-plain-765"]) == 0
    chain = receipts(sandbox)[-1]
    assert "competitions" not in chain and "listings_skipped" not in chain
    assert not any("sync" in r for r in receipts(sandbox) if r["kind"] == "step")
    json.dumps(chain)                                                         # the receipt stays plain JSON



def test_a_competition_season_listed_twice_keeps_each_runs_receipt_line():
    """Codex on #774: a list line written twice runs twice (fullseason_entries keeps duplicates), so each sync-teams
    run keeps its own competition entry with its own sync-matches; the earlier run's skip count is never overwritten."""
    pl = ["--competition", "PL", "--season", "2026/27"]
    sync = [(1, ["sync-teams", *pl], {"teams": {"created": 1, "updated": 2}}, 0),
            (2, ["sync-matches", *pl], {"matches": {"created": 0, "updated": 5, "skipped": 3},
                                        "not_in_db": {"n": 3, "ids": ["1", "2", "3"]}}, 0),
            (3, ["sync-teams", *pl], {}, 1),
            (4, ["sync-matches", *pl], {"matches": {"created": 0, "updated": 5, "skipped": 0}}, 0)]
    first, second = sp_run.competition_lines(sync)
    assert (first["teams_step"], first["matches_step"], first["matches_skipped"], first["not_in_db"]) == (1, 2, 3, 3)
    assert (second["teams_step"], second["teams_exit"], second["matches_step"], second["matches_skipped"],
            second["not_in_db"]) == (3, 1, 4, 0, 0)
    assert "(3 of clubs not in the DB)" in sp_run.competition_text(first)
    assert "sync-teams failed (exit 1)" in sp_run.competition_text(second)

# A sync step that RAN but printed no recognised count (it failed first, or the MLB fallback's own matches line): the
# competition line reads '?' and the exit, never "did not run" (law 4). Through run_steps, never a hand-built list.
FAKE_NO_COUNT_CLI = '''import sys
a = sys.argv[1:]
code = a[a.index("--competition") + 1]
if a[0] == "sync-teams":
    if code == "UEL":
        print("Traceback (most recent call last):")
        print("RuntimeError: provider read failed")
        sys.exit(1)
    if code == "MLB":
        print("MLB via api-sports Baseball FALLBACK (SP_SKIP_FAMILIES names MLB; statsapi is the laptop's path)")
        print("  teams 2026: provider 32 · created 0 · stamped 0 · existing 30 · linked 1 · non-club skipped [] "
              "· ambiguous name []")
    else:
        print("✓ Teams (%s): created=0 updated=30 skipped=0" % code)
elif a[0] == "sync-matches":
    if code == "MLB":
        print("  matches 2026 window 2026-03-01..2026-11-30: provider 2430 · created 0 · updated 12 · linked to "
              "existing 0 · finished 2400 · ambiguous 0 · held near unkeyed 0 · team missing 0")
    elif code == "PL":
        print("Traceback (most recent call last):")
        print("RuntimeError: provider read failed")
        sys.exit(1)
'''


def test_a_sync_step_that_ran_but_printed_no_count_reads_unknown_and_its_exit_never_did_not_run(sandbox, monkeypatch,
                                                                                               capsys):
    (c.REPO / "cli.py").write_text(FAKE_NO_COUNT_CLI)
    monkeypatch.setitem(chains.CHAINS, "t-nocount-765", {"continue_on_sync_failure": True, "steps": [
        [v, "--competition", code, "--season", season]
        for code, season in (("MLB", "2026"), ("PL", "2026/27"), ("UEL", "2026/27"))
        for v in ("sync-teams", "sync-matches")]})
    capsys.readouterr()
    assert sp_run.main(["t-nocount-765"]) == 1                     # PL's sync-matches failed first (exit 1)
    out = capsys.readouterr().out.split("\n")
    chain = receipts(sandbox)[-1]
    mlb, pl, uel = chain["competitions"]
    # MLB: both steps ran and exited 0; the fallback's matches line has no skipped count: '?', never 0, never absent
    assert (mlb["teams_exit"], mlb["teams_created"], mlb["teams_updated"]) == (0, 0, None)
    assert (mlb["matches_step"], mlb["matches_exit"], mlb["matches_skipped"], mlb["not_in_db"]) == (2, 0, None, None)
    assert ("  · MLB 2026: sync-teams created 0 · updated ? · sync-matches skipped ? (no count printed)") in out
    # PL: sync-matches ran and failed before its ✓ line
    assert (pl["matches_step"], pl["matches_exit"], pl["matches_skipped"]) == (4, 1, None)
    assert "  · PL 2026/27: sync-teams created 0 · updated 30 · sync-matches failed (exit 1) skipped ?" in out
    # UEL: sync-teams failed before its ✓ line; its competition line is still there, with its exit
    assert (uel["teams_step"], uel["teams_exit"], uel["teams_created"], uel["matches_step"]) == (5, 1, None, 6)
    assert ("  · UEL 2026/27: sync-teams failed (exit 1) created ? · updated ? · sync-matches skipped ? "
            "(no count printed)") in out
    assert not any("did not run" in x for x in out)
    # precedence: on a continue_on_sync_failure chain addendum 84 item 2(b) carried UEL's failed sync-teams, so its
    # receipt and the summary never credit it to addendum 207 item 4
    steps = [r for r in receipts(sandbox) if r["kind"] == "step"]
    assert steps[4]["step"] == 5 and steps[4]["continued"] == "addendum 84 item 2(b): a sync step's failure does not stop the window chain"
    summary = next(x for x in out if x.startswith("✗ t-nocount-765:"))
    assert "addendum 207" not in summary and "sync-teams failed" not in summary


def test_did_not_run_is_only_a_sync_matches_step_never_reached_and_a_failed_sync_matches_still_stops(sandbox,
                                                                                                    monkeypatch,
                                                                                                    capsys):
    """A failed sync-matches still stops a chain without continue_on_sync_failure (exit semantics unchanged; addendum
    207 item 4 runs on past a failed sync-teams only): a later competition's sync-matches is never reached and its
    line says `did not run`."""
    (c.REPO / "cli.py").write_text(FAKE_NO_COUNT_CLI)
    monkeypatch.setitem(chains.CHAINS, "t-stop-765", {"steps": [
        ["sync-teams", "--competition", "MLB", "--season", "2026"],
        ["sync-teams", "--competition", "PL", "--season", "2026/27"],
        ["sync-matches", "--competition", "PL", "--season", "2026/27"],
        ["sync-matches", "--competition", "MLB", "--season", "2026"]]})
    capsys.readouterr()
    assert sp_run.main(["t-stop-765"]) == 1
    out = capsys.readouterr().out.split("\n")
    rs = receipts(sandbox)
    assert [r["step"] for r in rs if r["kind"] == "step"] == [1, 2, 3]            # step 4 never ran
    chain = rs[-1]
    assert chain["stopped_at"] == 3 and [f["step"] for f in chain["failed_steps"]] == [3]
    mlb, pl = chain["competitions"]
    assert (mlb["teams_exit"], mlb["matches_step"], mlb["matches_exit"]) == (0, None, None)
    assert "  · MLB 2026: sync-teams created 0 · updated ? · sync-matches did not run" in out
    assert (pl["matches_step"], pl["matches_exit"]) == (3, 1)
    assert "  ✗ stopped at step 3/4" in out
    assert not any("sync-teams failed" in x for x in out)


# ------------------------------------------------------------------ addendum 207 item 4: a failed sync-teams runs on

FAKE_INTL_CLI = '''import sys
a = sys.argv[1:]
if a[0] not in ("sync-teams", "sync-matches"):
    print("ran", " ".join(a))
    sys.exit(0)
code = a[a.index("--competition") + 1]
if a[0] == "sync-teams":
    if code in ("CL", "FAC"):
        print("Traceback (most recent call last):")
        print("RuntimeError: provider teams read failed")
        sys.exit(4 if code == "CL" else 5)
    print("✓ Teams (%s): created=0 updated=36 skipped=0" % code)
else:
    if code == "CL":
        print("✓ Matches (CL): created=0 updated=10 skipped=3")
        print("skipped 3 listing(s) of clubs not in the DB: 7001, 7002, 7003")
    else:
        print("✓ Matches (%s): created=0 updated=12 skipped=0" % code)
'''


def test_a_failed_sync_teams_runs_on_to_its_sync_matches_and_later_cups_with_the_first_failures_exit(sandbox,
                                                                                                      capsys):
    """ARCHITECT 2026-11-01 17:10 ET, addendum 207 item 4, verbatim: "A failed sync-teams does NOT stop the chain: the
    chain continues to that competition's sync-matches and to every later step, keeps the FIRST failure's exit code,
    and names the failed step in its summary line; sync-matches' skipped-listings line then says what the failed teams
    read cost (never silent). [...] One test: a sync-teams failure followed by a successful sync-matches and a later
    cup read; exit code the first failure's; the summary names the step." The real intl-daily chain (its own steps,
    continue_on_sync_failure unset): CL's sync-teams exits 4, FAC's (later) exits 5."""
    assert not chains.CHAINS["intl-daily"].get("continue_on_sync_failure")            # not the wider flag
    (c.REPO / "cli.py").write_text(FAKE_INTL_CLI)
    capsys.readouterr()
    assert sp_run.main(["intl-daily"]) == 4                                           # the FIRST failure's exit
    out = capsys.readouterr().out.rstrip("\n").split("\n")
    rs = receipts(sandbox)
    steps = [r for r in rs if r["kind"] == "step"]
    assert [s_["step"] for s_ in steps] == list(range(1, 12))                         # every step ran
    cmds = [s_["command"].split()[2:5:2] for s_ in steps[3:]]
    assert cmds == [[v, code] for code in ("EFL", "CL", "UEL", "FAC") for v in ("sync-teams", "sync-matches")]
    assert [s_["exit"] for s_ in steps] == [0, 0, 0, 0, 0, 4, 0, 0, 0, 5, 0]
    assert steps[5]["continued"] == sp_run.TEAMS_GO_ON and "sync" not in steps[5]     # no faked teams count
    assert all("continued" not in s_ for s_ in steps if not s_["exit"])
    # CL's sync-matches ran after its failed sync-teams, and its skipped-listings line is in the receipt
    assert steps[6]["sync"]["not_in_db"] == {"n": 3, "ids": ["7001", "7002", "7003"]} and steps[6]["exit"] == 0
    # the LATER cups' reads ran
    assert steps[8]["sync"]["matches"] == {"created": 0, "updated": 12, "skipped": 0}           # UEL
    assert steps[10]["exit"] == 0 and steps[10]["sync"]["matches"]["updated"] == 12          # FAC, past its own failure
    chain = rs[-1]
    assert chain["kind"] == "chain" and chain["exit"] == 4 and chain["steps_ok"] == 9
    assert chain["stopped_at"] is None and [f["step"] for f in chain["failed_steps"]] == [6, 10]
    assert chain["listings_skipped"] == [{"step": 7, "command": "python cli.py sync-matches --competition CL "
                                          "--season 2026/27", "n": 3, "ids": ["7001", "7002", "7003"]}]
    cl = next(r for r in chain["competitions"] if r["competition"] == "CL")
    assert cl == {"competition": "CL", "season": "2026/27", "teams_step": 6, "teams_exit": 4, "teams_created": None,
                  "teams_updated": None, "matches_step": 7, "matches_exit": 0, "matches_skipped": 3, "not_in_db": 3}
    assert ("  · CL 2026/27: sync-teams failed (exit 4) created ? · updated ? · sync-matches skipped 3 "
            "(3 of clubs not in the DB)") in out
    assert not any("did not run" in x for x in out)
    text = "\n".join(out)
    assert ("· sync-teams step 6/11 failed (exit 4): python cli.py sync-teams --competition CL --season 2026/27 — "
            "recorded; the chain runs on to its sync-matches and every later step (addendum 207 item 4)") in text
    summary = next(x for x in out if x.startswith("✗ intl-daily: exit=4 steps 9/11"))
    assert (" · sync-teams failed (the chain ran on, addendum 207 item 4): step 6/11 CL exit 4, step 10/11 FAC exit 5"
            " · listings skipped (clubs not in the DB): step 7/11 CL 3 · running ") in summary
    assert not any(x.startswith("  ✗ stopped at") for x in out)
