"""DEDUPE-MATCHES, A TRUTHFUL EXIT (ARCHITECT 2026-11-24 10:03 ET, addendum 497 item 2 step (1), Q1 and Q8; DEV 3's
map on #1102, row 8: "Failure: a provider lookup that raises ("UNRESOLVED, never absent")").

- A provider read that failed (a by-id lookup that raised, or one failed day of the date search) leaves its candidate
  set "unresolved": the run prints everything it printed before, plans and writes exactly what it did, then prints
  "dedupe-matches: N unresolved (provider read failed): <ids>" LAST and exits 1, dry run and --apply alike.
- Q8: "A dedupe-matches team with no provider id, planned "orphan", is a classification: exit 0, printed and counted."
- Q1: "A ROUTINE STATE EXITS 0 AND PRINTS ONE LINE THAT NAMES IT [...] The line's words are pinned by a test." The
  states the code has: no duplicate pairs (the pair path), no candidates and every candidate live (--orphans).

Synthetic worlds on the throwaway test DB (tests/conftest.py); the provider is a fake, no network."""
import ast
import re
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner
from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Odds, Sport, Team
from src.ingestion import match_dedupe as md
from tests.test_dedupe_orphans import (CODE, NOW, SRC, FakeProvider, GappyProvider, _drop_world, _nm,  # noqa: F401
                                       _world, world)

UNRESOLVED = "dedupe-matches: {n} unresolved (provider read failed): {ids}"
NO_TEAM_ID = "dedupe-matches: {n} stale_orphan planned for a team with no provider id (a classification, not a failure)"


def _cli(monkeypatch, prov, *args, code=CODE):
    import cli as climod
    import src.adapters.api_american_football as aaf
    monkeypatch.setattr(aaf, "APIAmericanFootballAdapter", lambda: prov)
    monkeypatch.setattr(climod, "_verify_backup", lambda *a, **k: "verified (test)")   # law 5's check: not under test
    monkeypatch.setenv("SP_ODDS_FOOTBALL_RPM", "6000000")
    return CliRunner().invoke(climod.cli, ["dedupe-matches", "--competition", code, *args])


def _by_key(ids):
    """Every row of the OR1 world by its key: (status, provider id, its _prev), or None when deleted."""
    out = {}
    with session_scope() as s:
        for k, mid in ids.items():
            m = s.get(Match, mid)
            out[k] = None if m is None else (m.status, (m.external_ids or {}).get(SRC),
                                             tuple((m.external_ids or {}).get(f"{SRC}_prev") or ()))
    return out


# ---- a small world of its own, for the search-day failure, the classification and the routine states -------------

def _drop_mini(code):
    with session_scope() as s:
        cids = [c.id for c in s.execute(select(Competition).where(Competition.code == code)).scalars()]
        mids = [m.id for m in s.execute(select(Match).where(Match.competition_id.in_(cids))).scalars()]
        s.query(Odds).filter(Odds.match_id.in_(mids)).delete(synchronize_session=False)
        s.query(Match).filter(Match.id.in_(mids)).delete(synchronize_session=False)
        s.query(Team).filter(Team.name.like(f"{code} T%")).delete(synchronize_session=False)
        s.query(Competition).filter(Competition.id.in_(cids)).delete(synchronize_session=False)


def _mini(code, rows, no_sid_teams=()):
    """rows: (key, home, away, provider id, kickoff). Teams 0..5; a team in no_sid_teams carries no provider id."""
    init_db()
    _drop_mini(code)
    ids = {}
    with session_scope() as s:
        c = Competition(sport=Sport.NFL, code=code, name=code, area="US", type="LEAGUE")
        ts = [Team(sport=Sport.NFL, name=f"{code} T{i}",
                   external_ids={} if i in no_sid_teams else {SRC: f"{code}t{i}"}) for i in range(6)]
        s.add(c)
        s.add_all(ts)
        s.flush()
        for key, h, a, sid, when in rows:
            m = Match(sport=Sport.NFL, competition_id=c.id, season="2026", utc_date=when,
                      status=MatchStatus.SCHEDULED, home_team_id=ts[h].id, away_team_id=ts[a].id,
                      external_ids={SRC: sid})
            s.add(m)
            s.flush()
            ids[key] = m.id
    return ids


def _game(code, h, a, sid, when, status=MatchStatus.SCHEDULED):
    from src.adapters.normalized import NormalizedMatch
    return NormalizedMatch(sport=Sport.NFL, competition_code=code, season="2026", utc_date=when, status=status,
                           home_team_source_id=f"{code}t{h}", away_team_source_id=f"{code}t{a}", source=SRC,
                           source_id=sid, status_raw=None)


@pytest.fixture
def mini():
    made = []

    def build(code, rows, no_sid_teams=()):
        made.append(code)
        return _mini(code, rows, no_sid_teams)
    yield build
    for code in made:
        _drop_mini(code)


# ---- the failure: a by-id lookup that raised ---------------------------------------------------------------------

def test_a_lookup_that_raises_is_unresolved_and_the_dry_run_exits_1_with_its_line_last(world, monkeypatch, capsys):
    import cli as climod
    ids, prov = world
    res = _cli(monkeypatch, prov, "--orphans")
    assert res.exit_code == 1, res.output
    lines = res.output.splitlines()
    assert lines[-1] == UNRESOLVED.format(n=1, ids=ids["broken"])
    assert lines[-2] == NO_TEAM_ID.format(n=0)                 # Q8's count, zero included, never a routine line
    # every line before the outcome lines is what the command printed before 497: _dedupe_orphans' own printing,
    # unchanged, run again on the same world (a dry run writes nothing)
    climod._dedupe_orphans(CODE, SRC, False, None)
    assert lines[:-2] == capsys.readouterr().out.splitlines()


def test_the_same_run_with_the_lookup_answered_plans_every_other_row_the_same_and_exits_0(world, monkeypatch):
    ids, prov = world
    failed = md.orphans(CODE, prov, now=NOW)
    ok_prov = FakeProvider(prov.games)                         # the same answers; the broken id now reads absent
    answered = md.orphans(CODE, ok_prov, now=NOW)
    others = lambda r: [p for p in r["plan"] if p["id"] != ids["broken"]]   # noqa: E731
    assert others(failed) == others(answered)                  # no other plan entry moves
    assert {p["id"]: p["action"] for p in failed["plan"]}[ids["broken"]] == "unresolved"
    assert {p["id"]: p["action"] for p in answered["plan"]}[ids["broken"]] == "orphan"
    assert md.unresolved_ids(failed) == [ids["broken"]] and md.unresolved_ids(answered) == []

    bad, good = _cli(monkeypatch, prov, "--orphans"), _cli(monkeypatch, ok_prov, "--orphans")
    assert (bad.exit_code, good.exit_code) == (1, 0), (bad.output, good.output)
    rows = lambda out: [ln for ln in out.splitlines()   # noqa: E731
                        if ln.startswith("  [") and f" id {ids['broken']} " not in ln]
    assert rows(bad.output) == rows(good.output)               # every other row's line, the same words
    assert "unresolved (provider read failed)" not in good.output
    assert good.output.splitlines()[-1] == NO_TEAM_ID.format(n=0)


# ---- the failure: a failed search day ----------------------------------------------------------------------------

def test_a_failed_search_day_leaves_its_set_unresolved_and_exits_1(mini, monkeypatch):
    past = NOW - timedelta(days=1)
    ids = mini("DX2", [("stale", 1, 0, "501", past), ("ok", 3, 2, "502", past)])
    gap = (past + timedelta(days=1)).strftime("%Y-%m-%d")
    prov = GappyProvider([], broken_dates={gap})                # every id absent; one day of the search fails
    r = md.orphans("DX2", prov, now=NOW)
    act = {p["id"]: (p["action"], p.get("why", "")) for p in r["plan"]}
    assert act[ids["stale"]][0] == "unresolved" and "provider search incomplete" in act[ids["stale"]][1]
    assert act[ids["ok"]][0] == "unresolved"                    # the cache shares the day: its search failed too
    res = _cli(monkeypatch, prov, "--orphans", code="DX2")
    assert res.exit_code == 1, res.output
    assert res.output.splitlines()[-1] == UNRESOLVED.format(n=2, ids=f"{ids['stale']}, {ids['ok']}")


def test_a_search_day_that_fails_for_one_set_only_leaves_the_other_set_planned(mini, monkeypatch):
    past = NOW - timedelta(days=1)
    far = NOW - timedelta(days=9)
    ids = mini("DX3", [("gap", 1, 0, "601", past), ("orphan", 3, 2, "602", far)])
    prov = GappyProvider([], broken_dates={past.strftime("%Y-%m-%d")})
    res = _cli(monkeypatch, prov, "--orphans", code="DX3")
    assert res.exit_code == 1, res.output
    assert res.output.splitlines()[-1] == UNRESOLVED.format(n=1, ids=ids["gap"])
    assert f"[orphan] id {ids['orphan']} " in res.output         # the other set's plan stands


# ---- --apply with an unresolved entry ----------------------------------------------------------------------------

def test_apply_writes_what_it_wrote_before_and_nothing_for_the_unresolved_then_exits_1(world, monkeypatch):
    ids, prov = world
    res = _cli(monkeypatch, prov, "--orphans", "--apply", "--backup", "x.backup")
    assert res.exit_code == 1, res.output
    lines = res.output.splitlines()
    assert lines[-1] == UNRESOLVED.format(n=1, ids=ids["broken"])
    applied = next(ln for ln in lines if ln.startswith("  applied "))
    counts, refused = applied[len("  applied "):].split(" · ")
    assert ast.literal_eval(counts) == {"merge": 2, "relink": 1, "orphan": 1} and refused == "refused at apply 0"
    by_cli = _by_key(ids)
    assert by_cli["broken"] == (MatchStatus.SCHEDULED, "22400", ())          # untouched
    # the same world applied by the module itself, as before 497: every row the same
    _drop_world()
    _, ids2, prov2 = _world()
    md.orphans(CODE, prov2, apply=True)
    assert _by_key(ids2) == by_cli


def test_apply_with_nothing_unresolved_exits_0(world, monkeypatch):
    ids, prov = world
    res = _cli(monkeypatch, FakeProvider(prov.games), "--orphans", "--apply", "--backup", "x.backup")
    assert res.exit_code == 0, res.output
    assert "unresolved (provider read failed)" not in res.output
    assert _by_key(ids)["broken"][0] == MatchStatus.STALE_ORPHAN


# ---- Q8: the classification ------------------------------------------------------------------------------------

@pytest.mark.parametrize("apply", [False, True], ids=["dry-run", "apply"])
def test_a_team_with_no_provider_id_planned_orphan_is_counted_and_exits_0(mini, monkeypatch, apply):
    past = NOW - timedelta(days=1)
    ids = mini("DX4", [("no_sid", 1, 0, "701", past), ("orphan", 3, 2, "702", past)], no_sid_teams=(1,))
    prov = FakeProvider([])
    res = _cli(monkeypatch, prov, "--orphans", *(["--apply", "--backup", "x.backup"] if apply else []), code="DX4")
    assert res.exit_code == 0, res.output
    lines = res.output.splitlines()
    assert lines[-1] == NO_TEAM_ID.format(n=1) + f": {ids['no_sid']}"      # counted, with its id; the true orphan not
    assert "stale_orphan 2 ·" in res.output                                # both still planned and counted as before
    assert f"[orphan] id {ids['no_sid']} " in res.output and f"[orphan] id {ids['orphan']} " in res.output
    r = md.orphans("DX4", prov, now=NOW)
    assert r["orphan_no_provider_team_id"] == ([] if apply else [ids["no_sid"]])   # applied: no longer a candidate


# ---- Q1: the routine states --------------------------------------------------------------------------------------

def test_the_pair_path_with_no_duplicate_pair_exits_0_and_names_it(mini, monkeypatch):
    mini("DX5", [("a", 1, 0, "801", NOW + timedelta(days=2)), ("b", 3, 2, "802", NOW + timedelta(days=2))])
    for args in ((), ("--apply", "--backup", "x.backup")):
        res = _cli(monkeypatch, FakeProvider([]), *args, code="DX5")
        assert res.exit_code == 0, res.output
        assert res.output.splitlines()[-1] == "dedupe-matches: nothing to merge (no duplicate pairs)"


def test_the_pair_path_with_a_pair_prints_no_routine_line(mini, monkeypatch):
    mini("DX6", [("k", 1, 0, "901", NOW + timedelta(days=2)), ("n", 1, 0, "9901", NOW + timedelta(days=2, hours=1))])
    res = _cli(monkeypatch, FakeProvider([]), code="DX6")
    assert res.exit_code == 0 and "duplicate pairs 1" in res.output, res.output
    assert "nothing to merge (no duplicate pairs)" not in res.output
    assert res.output.splitlines()[-1].strip().startswith("record rows on retired match ids")


def test_the_pair_path_with_a_cluster_refused_at_detection_prints_no_routine_line(mini, monkeypatch):
    """Three rows of one fixture within 12h: no mergeable pair, but a duplicate refused at detection and reported for
    review. That is not the routine "no duplicate pairs" state: no routine line, and the exit stays 0."""
    t = NOW + timedelta(days=2)
    mini("DX9", [("c1", 1, 0, "951", t), ("c2", 1, 0, "952", t + timedelta(hours=1)),
                 ("c3", 1, 0, "953", t + timedelta(hours=2))])
    for args in ((), ("--apply", "--backup", "x.backup")):
        res = _cli(monkeypatch, FakeProvider([]), *args, code="DX9")
        assert res.exit_code == 0, res.output
        assert "duplicate pairs 0 · {'refused_cluster_gt2': 1}" in res.output, res.output
        assert "nothing to merge (no duplicate pairs)" not in res.output
        assert res.output.splitlines()[-1].strip().startswith("record rows on retired match ids")


def test_orphans_with_no_candidate_exits_0_and_names_it(mini, monkeypatch):
    mini("DX7", [("future", 1, 0, "111", NOW + timedelta(days=2))])        # not stale, no twin: no candidate
    prov = FakeProvider([])
    res = _cli(monkeypatch, prov, "--orphans", code="DX7")
    assert res.exit_code == 0, res.output
    assert res.output.splitlines()[-2:] == [NO_TEAM_ID.format(n=0),
                                            "dedupe-matches --orphans: nothing to do (no candidates)"]
    assert prov.calls == []                                                 # nothing asked


def test_orphans_where_every_candidate_is_live_exits_0_and_names_it(mini, monkeypatch):
    past = NOW - timedelta(days=1)
    mini("DX8", [("a", 1, 0, "121", past), ("b", 3, 2, "122", past)])
    prov = FakeProvider([_game("DX8", 1, 0, "121", past), _game("DX8", 3, 2, "122", past)])   # served = stored
    res = _cli(monkeypatch, prov, "--orphans", code="DX8")
    assert res.exit_code == 0, res.output
    assert res.output.splitlines()[-1] == "dedupe-matches --orphans: nothing to do (every candidate live: 2)"


# ---- the lines themselves ----------------------------------------------------------------------------------------

def test_the_lines_words_are_pinned():
    assert md.unresolved_line([3, 41]) == "dedupe-matches: 2 unresolved (provider read failed): 3, 41"
    assert md.no_team_id_line([]) == NO_TEAM_ID.format(n=0)
    assert md.no_team_id_line([7]) == NO_TEAM_ID.format(n=1) + ": 7"
    assert md.NOTHING_TO_MERGE_LINE == "dedupe-matches: nothing to merge (no duplicate pairs)"
    assert md.NO_CANDIDATES_LINE == "dedupe-matches --orphans: nothing to do (no candidates)"
    assert md.every_live_line(4) == "dedupe-matches --orphans: nothing to do (every candidate live: 4)"
    assert md.EXIT_UNRESOLVED == 1


def test_no_new_line_is_read_by_a_runner_as_something_else():
    """No runner's reader takes a new line for another thing: sp_run's retry classifier and exception line, its count
    lines, the laptop routine's sync echo, and closing's failure markers (a 'refus' word would be a sync echo)."""
    hosting = Path(__file__).resolve().parents[1] / "deploy" / "hosting"
    sys.path.insert(0, str(hosting))
    import closing
    import laptop_routine
    import sp_run
    new = [md.unresolved_line([1, 2]), md.no_team_id_line([3]), md.no_team_id_line([]), md.NOTHING_TO_MERGE_LINE,
           md.NO_CANDIDATES_LINE, md.every_live_line(2)]
    counts = [v for k, v in vars(sp_run).items() if k.endswith("_LINE") and isinstance(v, re.Pattern)]
    for ln in new:
        assert not sp_run._TRANSIENT.search(ln) and not sp_run._EXC_LINE.match(ln), ln
        assert not laptop_routine.SYNC_ECHO.search(ln), ln
        assert not any(p.search(ln) for p in counts), ln
        assert not any(ln.startswith(m) for ms in closing.STEP_FAILURE_MARKERS.values() for m in ms), ln
