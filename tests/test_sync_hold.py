"""SP_SYNC_HOLD (#921). ARCHITECT 2026-11-10 18:55 ET, addendum 332 item 3, verbatim: "THE DURABLE ANSWER is a
per-competition sync hold the step itself honors: SP_SYNC_HOLD, a list of competition codes read by sync-teams and
sync-matches, which print "HELD <code> (SP_SYNC_HOLD)" and exit 0 for a listed code, every chain and timer unchanged,
the window and fullseason plans unchanged; a receipt line counts the held steps." Addendum 333 item 3(iii), verbatim:
"SP_SYNC_HOLD (#921) honors the same path: its design covers intl-sync, or says in its body why not."

Synthetic throughout: fake adapters on throwaway SQLite files, a fake cli.py in a tmp checkout for sp_run; no network,
never data/."""
import inspect
import json
import sys
from datetime import date
from pathlib import Path

import pytest
from click.testing import CliRunner
from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))

import sp_common as c  # noqa: E402
import sp_receipts  # noqa: E402
import sp_run  # noqa: E402

from src.ingestion import sync_hold  # noqa: E402
from tests.test_765_weekly_sync_teams import _Cup, _cli, cup_db  # noqa: E402,F401  (FAC on a throwaway DB)
from tests.test_hosting_pack import receipts, sandbox  # noqa: E402,F401  (the sp_run sandbox)


# ------------------------------------------------------------------ the setting

def test_the_setting_is_a_list_of_codes_any_case_commas_or_blanks():
    assert sync_hold.held_codes({}) == frozenset()
    assert sync_hold.held_codes({"SP_SYNC_HOLD": "  "}) == frozenset()
    assert sync_hold.held_codes({"SP_SYNC_HOLD": "ncaa, PL  unl"}) == {"NCAA", "PL", "UNL"}
    assert sync_hold.is_held("ncaa", {"SP_SYNC_HOLD": "NCAA"}) and not sync_hold.is_held("NFL", {"SP_SYNC_HOLD": "NCAA"})
    assert not sync_hold.is_held(None, {"SP_SYNC_HOLD": "NCAA"})
    assert sync_hold.held_line("ncaa") == "HELD NCAA (SP_SYNC_HOLD)"            # 332 item 3's words


# ------------------------------------------------------------------ the steps

def _no_adapter(monkeypatch):
    import cli
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda code: pytest.fail(f"a held {code} built an adapter"))
    monkeypatch.setattr(cli, "IngestionService", lambda *a, **k: pytest.fail("a held step reached the service"))
    monkeypatch.setattr(cli, "_mlb_fallback_run", lambda *a, **k: pytest.fail("a held MLB step ran the fallback"))
    return cli


@pytest.mark.parametrize("argv", [
    ["sync-teams", "--competition", "PL", "--season", "2026/27"],
    ["sync-matches", "--competition", "PL", "--season", "2026/27"],
    ["sync-matches", "--competition", "pl", "--season", "2026/27", "--date-from", "2026-11-11",
     "--date-to", "2026-11-11", "--match-ids", "1,2"],                                # the closing run's read too
    ["sync-matches", "--competition", "PL", "--seasons", "3"],
    ["sync-teams", "--competition", "MLB", "--season", "2026"],                      # before the api-sports fallback
    ["sync-matches", "--competition", "MLB", "--season", "2026"],
    ["sync-matches", "--competition", "ATP", "--date-from", "2026-11-10", "--date-to", "2026-11-12"],  # tennis
    ["refresh-by-id", "--competition", "NCAA"],                                      # the write path (333 3(iii))
])
def test_a_held_code_prints_the_line_builds_nothing_and_exits_0(argv, monkeypatch, tmp_path):
    cli = _no_adapter(monkeypatch)
    monkeypatch.setenv("SP_LOCK", str(tmp_path / "db.lock"))
    monkeypatch.delenv(c.HELD_ENV, raising=False)
    monkeypatch.setenv("SP_SKIP_FAMILIES", "MLB")
    monkeypatch.setenv("SP_SYNC_HOLD", "PL,MLB, atp NCAA")
    import src.ingestion.refresh_by_id as rbi
    monkeypatch.setattr(rbi, "refresh", lambda *a, **k: pytest.fail("a held refresh-by-id refreshed"))
    r = CliRunner().invoke(cli.cli, argv)
    assert r.exit_code == 0, r.output
    code = argv[argv.index("--competition") + 1].upper()
    assert r.output.strip().splitlines() == [f"HELD {code} (SP_SYNC_HOLD)"]


def test_a_held_code_writes_no_row_and_an_unlisted_code_is_unaffected(cup_db, monkeypatch):
    from src.db.database import session_scope
    from src.db.schema import Match, Team
    monkeypatch.setenv("SP_SYNC_HOLD", "FAC")

    def counts():
        with session_scope() as s:
            return s.execute(select(func.count(Team.id))).scalar(), s.execute(select(func.count(Match.id))).scalar()
    for verb in ("sync-teams", "sync-matches"):
        r = _cli(monkeypatch, _Cup([10, 11]), verb, "--competition", "FAC", "--season", "2026/27")
        assert r.exit_code == 0 and r.output.strip() == "HELD FAC (SP_SYNC_HOLD)", r.output
    assert counts() == (0, 0)
    monkeypatch.setenv("SP_SYNC_HOLD", "PL, NCAA")                                  # FAC no longer listed
    r = _cli(monkeypatch, _Cup([10, 11]), "sync-teams", "--competition", "FAC", "--season", "2026/27")
    assert r.exit_code == 0 and "HELD" not in r.output and "✓ Teams (FAC): created=2" in r.output, r.output
    r = _cli(monkeypatch, _Cup([10, 11]), "sync-matches", "--competition", "FAC", "--season", "2026/27")
    assert r.exit_code == 0 and "HELD" not in r.output and "✓ Matches (FAC): created=1" in r.output, r.output
    assert counts() == (2, 1)
    monkeypatch.delenv("SP_SYNC_HOLD")
    r = _cli(monkeypatch, _Cup([10, 11]), "sync-teams", "--competition", "FAC", "--season", "2026/27")
    assert r.exit_code == 0 and "HELD" not in r.output


# ------------------------------------------------------------------ intl-sync (333 item 3(iii))

def test_intl_sync_writes_nothing_for_a_held_code_and_says_so(tmp_path, monkeypatch):
    from src.db.database import init_db, session_scope
    from src.db.schema import Competition, Match
    from src.ingestion import intl_history as ih
    from tests.test_intl_history import GROUNDS, fx, league
    init_db()
    d = tmp_path / "unl"
    d.mkdir()
    json.dump({"response": [league(5, "UEFA Nations League", 2075)]}, open(d / "leagues.json", "w"))
    json.dump({"response": [fx(9907501, 880001, 880002, 2, 1, "Probe City", when="2075-06-07T18:45:00+00:00",
                               league_season=2075)]}, open(d / "fixtures_5_2075.json", "w"))
    json.dump({"response": GROUNDS}, open(d / "teams_5_2075.json", "w"))

    def snapshot():
        with session_scope() as s:
            return (s.execute(select(func.count(Competition.id))).scalar(),
                    s.execute(select(func.count(Match.id))).scalar(),
                    s.execute(select(Match.id).where(Match.external_ids["api_football"].as_string() == "9907501"))
                    .scalar_one_or_none())
    before = snapshot()
    with session_scope() as s:                       # no team of the listing is written either
        from src.db.schema import Team
        teams_before = s.execute(select(func.count(Team.id))).scalar()
    monkeypatch.setenv("SP_SYNC_HOLD", "unl")
    r = ih.ingest(ih.Source(from_dir=str(d)), date(2018, 1, 1))
    assert r["held"] == ["UNL"] and r["per_cs"][("UNL", 2075)]["skipped"] == "HELD"
    assert snapshot() == before and before[2] is None                               # nothing written for UNL
    with session_scope() as s:
        from src.db.schema import Team
        assert s.execute(select(func.count(Team.id))).scalar() == teams_before
    import cli
    out = CliRunner().invoke(cli.cli, ["intl-sync", "--from-dir", str(d)]).output
    assert "HELD UNL (SP_SYNC_HOLD)" in out.splitlines(), out
    assert snapshot() == before
    r = ih.ingest(ih.Source(from_dir=str(d)), date(2018, 1, 1), dry_run=True, held=())   # unheld: the code writes
    assert r["held"] == [] and r["per_cs"][("UNL", 2075)].get("stored") == 1


# ------------------------------------------------------------------ the receipt line, the plans unchanged

FAKE_HELD_CLI = '''import sys
a = sys.argv[1:]
if "--competition" not in a:
    print("ran", " ".join(a))
    sys.exit(0)
code = a[a.index("--competition") + 1]
if code == "PL":
    print("HELD PL (SP_SYNC_HOLD)")
    sys.exit(0)
if a[0] == "sync-teams":
    print("✓ Teams (%s): created=0 updated=30 skipped=0" % code)
else:
    print("✓ Matches (%s): created=0 updated=10 skipped=0" % code)
'''


def test_the_chain_receipt_counts_the_held_steps(sandbox, monkeypatch, capsys):
    (c.REPO / "cli.py").write_text(FAKE_HELD_CLI)
    lst = sandbox / "fs.list"
    lst.write_text("PL|2026/27\nFAC|2026/27\n")
    monkeypatch.setenv("SP_FULLSEASON_LIST", str(lst))
    capsys.readouterr()
    assert sp_run.main(["weekly-fullseason"]) == 0
    out = capsys.readouterr().out.rstrip("\n").split("\n")
    rs = receipts(sandbox)
    steps = [r for r in rs if r["kind"] == "step"]
    assert [s["exit"] for s in steps] == [0] * 5
    assert steps[0]["sync"] == {"held": ["PL"]} and steps[1]["sync"] == {"held": ["PL"]}
    chain = rs[-1]
    assert chain["sync_held"] == {"n": 2, "steps": [
        {"step": 1, "command": "python cli.py sync-teams --competition PL --season 2026/27", "codes": ["PL"]},
        {"step": 2, "command": "python cli.py sync-matches --competition PL --season 2026/27", "codes": ["PL"]}]}
    assert chain["competitions"][0]["teams_held"] is True and chain["competitions"][0]["matches_held"] is True
    assert "teams_held" not in chain["competitions"][1] and "matches_held" not in chain["competitions"][1]
    assert "  · PL 2026/27: sync-teams HELD (SP_SYNC_HOLD) · sync-matches HELD (SP_SYNC_HOLD)" in out
    assert "  · FAC 2026/27: sync-teams created 0 · updated 30 · sync-matches skipped 0" in out
    summary = next(x for x in out if x.startswith("✓ weekly-fullseason: exit=0 steps 5/5"))
    assert " · held steps (SP_SYNC_HOLD) 2: step 1 PL, step 2 PL · running " in summary
    assert "; held steps (SP_SYNC_HOLD) 2" in sp_receipts.key_line(chain)


def test_a_run_with_nothing_held_says_zero_in_the_receipt_and_nothing_on_the_line(sandbox, monkeypatch, capsys):
    (c.REPO / "cli.py").write_text(FAKE_HELD_CLI)
    lst = sandbox / "fs.list"
    lst.write_text("FAC|2026/27\n")
    monkeypatch.setenv("SP_FULLSEASON_LIST", str(lst))
    capsys.readouterr()
    assert sp_run.main(["weekly-fullseason"]) == 0
    out = capsys.readouterr().out
    chain = receipts(sandbox)[-1]
    assert chain["sync_held"] == {"n": 0, "steps": []}
    assert "held steps" not in out and "held steps" not in sp_receipts.key_line(chain)


def test_an_intl_sync_step_holding_two_codes_counts_once():
    sync = [(3, ["intl-sync", "--since", "2026-11-11"],
             sp_run.sync_counts(["HELD UNL (SP_SYNC_HOLD)", "HELD WCQ_EU (SP_SYNC_HOLD)", "HELD UNL (SP_SYNC_HOLD)"]),
             0)]
    assert sp_run.held_totals(sync) == {"n": 1, "steps": [
        {"step": 3, "command": "python cli.py intl-sync --since 2026-11-11", "codes": ["UNL", "WCQ_EU"]}]}
    assert sp_run.held_steps_text(sp_run.held_totals(sync)) == " · held steps (SP_SYNC_HOLD) 1: step 3 UNL/WCQ_EU"
    assert not sp_run.HELD_LINE.match("HELD UNL (SP_SYNC_HOLD) extra") and not sp_run.HELD_LINE.match("held UNL")


def test_the_plans_and_chains_are_unchanged_by_the_setting(sandbox, monkeypatch):
    lst = sandbox / "fs.list"
    lst.write_text("PL|2026/27\nNCAA|2026\n")
    monkeypatch.setenv("SP_FULLSEASON_LIST", str(lst))
    monkeypatch.delenv("SP_SYNC_HOLD", raising=False)
    import chains
    base = {name: sp_run.resolve(name, {}, date(2026, 11, 1)) for name in ("weekly-fullseason", "ncaa-market",
                                                                            "ncaa-schedule", "intl-daily")}
    monkeypatch.setenv("SP_SYNC_HOLD", "PL,NCAA,UNL")
    assert {name: sp_run.resolve(name, {}, date(2026, 11, 1)) for name in base} == base
    for fn in (sp_run.window_plan, sp_run.fullseason_resolve, sp_run.resolve):          # the plans never read it
        assert "SP_SYNC_HOLD" not in inspect.getsource(fn) and "sync_hold" not in inspect.getsource(fn)
    assert "SP_SYNC_HOLD" not in (ROOT / "deploy" / "hosting" / "chains.py").read_text()
    assert chains.CHAINS["weekly-fullseason"].get("fullseason") is True


def test_the_admin_ui_sync_jobs_honor_the_hold(monkeypatch):
    """The write path, not the step's name (333 item 3(iii)): the admin UI's two sync jobs build no adapter for a
    held code and return the HELD line as the job's result."""
    from src.web.routes import admin
    monkeypatch.setattr(admin, "_adapter_for_competition", lambda code: pytest.fail("a held job built an adapter"))
    monkeypatch.setenv("SP_SYNC_HOLD", "PL")
    assert admin._job_sync_teams(competition_code="PL", season="2026/27") == "HELD PL (SP_SYNC_HOLD)"
    assert admin._job_sync_matches(competition_code="pl", season="2026/27", seasons=0) == "HELD PL (SP_SYNC_HOLD)"


# ------------------------------------------------------------------ review round (before the push)

def test_the_setting_is_read_from_host_env_and_dotenv_too_a_code_in_any_is_held(tmp_path, monkeypatch):
    """A run by hand outside a unit, and a long-running process, see a hold set in a file after they started."""
    host = tmp_path / "host.env"
    monkeypatch.setenv("SP_HOST_ENV", str(host))
    monkeypatch.delenv("SP_SYNC_HOLD", raising=False)
    monkeypatch.setattr(sync_hold, "REPO", tmp_path)                              # the checkout's .env
    assert sync_hold.held_codes() == frozenset()
    host.write_text("# host\nSP_SKIP_FAMILIES=MLB\nexport SP_SYNC_HOLD=\"ncaa, PL\"\n")
    assert sync_hold.held_codes() == {"NCAA", "PL"}                               # re-read on each check
    (tmp_path / ".env").write_text("SP_SYNC_HOLD=unl\n")
    monkeypatch.setenv("SP_SYNC_HOLD", "NFL")
    assert sync_hold.held_codes() == {"NCAA", "PL", "UNL", "NFL"}                 # the union of the three
    assert sync_hold.sources() == {"environment": {"NFL"}, str(host): {"NCAA", "PL"},
                                   str(tmp_path / ".env"): {"UNL"}}
    host.write_text("SP_SYNC_HOLD=\n")
    monkeypatch.delenv("SP_SYNC_HOLD")
    assert sync_hold.held_codes() == {"UNL"}                                       # lifted where it was removed


def test_bad_arguments_still_fail_under_a_hold(monkeypatch, tmp_path):
    cli = _no_adapter(monkeypatch)
    monkeypatch.setenv("SP_LOCK", str(tmp_path / "db.lock"))
    monkeypatch.delenv(c.HELD_ENV, raising=False)
    monkeypatch.setenv("SP_SYNC_HOLD", "PL")
    r = CliRunner().invoke(cli.cli, ["sync-matches", "--competition", "PL", "--seasons", "2", "--match-ids", "1"])
    assert r.exit_code == 2 and "HELD" not in r.output, r.output


def test_a_closing_runs_held_schedule_read_is_receipted_and_said(monkeypatch, capsys):
    """Review (P2): a held --match-ids read exits 0 (332 item 3, as built); the closing receipt records it and the
    console says the run went on with the stored schedule. Whether it should fail the run instead is put to the
    architect on the PR."""
    import closing
    src = inspect.getsource(closing)
    assert 'srec["held"] = held_codes' in src and 'rec.setdefault("sync_held"' in src
    assert "the run goes on with the STORED schedule" in src
    assert sp_run.sync_counts(["ran x", "HELD PL (SP_SYNC_HOLD)"]) == {"held": ["PL"]}


def test_a_freshen_and_a_chain_receipt_carry_the_hold(sandbox, monkeypatch, capsys, tmp_path):
    (c.REPO / "cli.py").write_text(FAKE_HELD_CLI)
    lst = sandbox / "fs.list"
    lst.write_text("PL|2026/27\n")
    monkeypatch.setenv("SP_FULLSEASON_LIST", str(lst))
    monkeypatch.setenv("SP_HOST_ENV", str(tmp_path / "none.env"))
    monkeypatch.setenv("SP_SYNC_HOLD", "pl")
    capsys.readouterr()
    assert sp_run.main(["weekly-fullseason"]) == 0
    out = capsys.readouterr().out
    chain = receipts(sandbox)[-1]
    assert chain["sync_hold"]["environment"] == ["PL"]
    assert " · SP_SYNC_HOLD PL" in next(x for x in out.splitlines() if x.startswith("✓ weekly-fullseason"))
    assert "sync_held" in inspect.getsource(sp_run.run_freshens)                      # a freshen counts its own


# ------------------------------------------------------------------ Codex on #925 (round 1): checks before the hold

@pytest.mark.parametrize("argv,needle", [
    (["refresh-by-id", "--competition", "PL"], "is not one of its competitions"),
    (["sync-teams", "--competition", "MLB"], "needs --season"),
    (["sync-matches", "--competition", "MLB", "--season", "2026", "--match-ids", "1"], "--match-ids is not supported"),
    (["sync-matches", "--competition", "MLB", "--seasons", "2"], "takes --season"),
    (["sync-matches", "--competition", "MLB"], "needs --season"),
    (["sync-matches", "--competition", "ATP"], "--date-from and --date-to are required"),
    (["sync-matches", "--competition", "ATP", "--date-from", "2026-11-01", "--date-to", "2026-11-30"], "day(s); 1 to"),
    (["sync-matches", "--competition", "WTA", "--date-from", "2026-11-10", "--date-to", "2026-11-11",
      "--season", "2026/27"], "--season is int-style"),
    (["sync-matches", "--competition", "ATP", "--seasons", "2"], "--seasons is refused"),
])
def test_a_bad_call_fails_under_a_hold_exactly_as_without_one(argv, needle, monkeypatch, tmp_path):
    cli = _no_adapter(monkeypatch)
    monkeypatch.setenv("SP_LOCK", str(tmp_path / "db.lock"))
    monkeypatch.delenv(c.HELD_ENV, raising=False)
    monkeypatch.setenv("SP_SKIP_FAMILIES", "MLB")
    monkeypatch.setenv("SP_HOST_ENV", str(tmp_path / "none.env"))
    for hold in ("PL,MLB,ATP,WTA", ""):
        monkeypatch.setenv("SP_SYNC_HOLD", hold)
        r = CliRunner().invoke(cli.cli, argv)
        assert r.exit_code == 2 and needle in r.output and "HELD" not in r.output, (hold, r.output)
