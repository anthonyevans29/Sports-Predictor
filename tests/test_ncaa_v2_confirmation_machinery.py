"""ncaa-elo-v2's CONFIRMATION MACHINERY (ARCHITECT 2026-11-03, addendum 230 item 1(b), verbatim: "the college shadow
export on the ncaa-schedule chain (the NHL shadow's shape: the entry's probabilities per fixture, market-only, never a
call), its grade against the Kalshi close (the close record's KXNCAAFGAME rule), the neutral flag on each row before
kickoff with its rule stated (never a provider fact), the confirmation counter to 100; dormant while the verdict is
null or FAIL."). Pins:
- the chain's step (`--id ncaa-elo-v2 --dormant-ok`) is DORMANT on a null and on a FAIL verdict: the reason printed,
  no file, exit 0; without the flag the operator's command still exits 2; every other refusal exits 2 either way;
- on a synthetic PASS registry it writes rows carrying the entry's probabilities, engine model_shadow, no call, the
  neutral flag before kickoff and its rule;
- the grade scores the shadow against the Kalshi close by the close record's own function (paper.guarded_two_way_close),
  per name, its exclusions counted (mismatched legs, no close, the record's 2026 fence);
- the counter to 100 counts, never a figure of the games: dormant on a null or FAIL verdict, counting after a PASS;
- the Kalshi exclusions follow the record's order (the fence before the result) and add up to the window's calls;
- v1r's verdict refusal is never dormant (its own ruling, addendum 24 item 2(d))."""
import json
from datetime import timedelta

import pytest
from click.testing import CliRunner

from src.db.database import session_scope
from src.db.schema import Match, MatchStatus, NCAACFBDLabel, OddsSnapshot
from src.walters import ncaa_backtest as nb
from src.walters import ncaa_shadow as sh
from src.walters import paper
from tests.test_ncaa_shadow import NOW, mine, world  # noqa: F401  (fixtures: the shadow's synthetic world)
from tests.test_ncaa_v2_shadow import _v2_registry

STEP = ["export-ncaa-predictions", "--id", "ncaa-elo-v2", "--dormant-ok"]


@pytest.fixture(autouse=True)
def _host(monkeypatch):
    """The chain step is the host's (ARCHITECT 2026-11-03, addendum 236 item 3(5): "the command refuses on any machine
    but the host"); conftest pins laptop, so this file runs as the host unless a test says otherwise."""
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "host")


def _pin_registry(monkeypatch, path):
    """The export reads `path`, whatever the committed registry says: registry.LEDGER, the one source frozen() reads
    at call time (ARCHITECT 2026-11-03, addendum 236 item 3(7))."""
    from src.walters import registry as reg
    monkeypatch.setattr(reg, "LEDGER", path)


def _files(d):
    return sorted((d / "exports").glob("ncaa_shadow_*.json")) if (d / "exports").exists() else []


@pytest.mark.parametrize("verdict,what", [(None, "no verdict"), ("FAIL", "the verdict FAIL")])
def test_the_chain_step_is_dormant_on_a_null_or_fail_verdict(verdict, what, tmp_path, monkeypatch):
    from cli import cli

    monkeypatch.chdir(tmp_path)
    _pin_registry(monkeypatch, _v2_registry(tmp_path, verdict=verdict))
    res = CliRunner().invoke(cli, STEP)
    assert res.exit_code == 0, res.output
    assert res.output.startswith(f"DORMANT: the registry records {what} for ncaa-elo-v2: dormant while the verdict "
                                 "is null or FAIL (ARCHITECT 2026-11-03, addendum 230 item 1(b))")
    assert "nothing was written" in res.output and _files(tmp_path) == []
    bare = CliRunner().invoke(cli, STEP[:-1])                         # the operator's command: exit 2 as before
    assert bare.exit_code == 2 and "REFUSED (exit 2)" in bare.output and _files(tmp_path) == []


def test_dormant_is_the_verdict_alone_every_other_refusal_still_exits_2(tmp_path, monkeypatch):
    """A PASS whose registry freezes another s is not dormant: refused, exit 2, nothing written, the chain fails."""
    from cli import cli

    with pytest.raises(sh.ShadowDormant) as e:                       # the verdict refusal is the dormant one
        sh.frozen(_v2_registry(tmp_path, verdict="FAIL", name="f.json"), eid=sh.V2_EID)
    assert (e.value.eid, e.value.verdict) == ("ncaa-elo-v2", "FAIL") and isinstance(e.value, sh.ShadowRefused)
    monkeypatch.chdir(tmp_path)
    _pin_registry(monkeypatch, _v2_registry(tmp_path, s=280.0))
    res = CliRunner().invoke(cli, STEP)
    assert res.exit_code == 2 and "not the ruled 279.14222651259433" in res.output and "DORMANT" not in res.output
    assert _files(tmp_path) == []


def test_v1rs_verdict_refusal_is_never_dormant(mine, tmp_path, monkeypatch):
    """230 item 1(b)'s dormancy is ncaa-elo-v2's: v1r's FAIL refusal stays its own ruling's (addendum 24 item 2(d):
    exit 2 naming it), with or without --dormant-ok, and the counter for v1r never says dormant."""
    from cli import cli
    from tests.test_ncaa_shadow import _registry

    reg = _registry(tmp_path, neutral_site_rule="no_home_advantage_at_neutral",
                    verdict={"verdict": "FAIL", "ruling": "x"})
    with pytest.raises(sh.ShadowRefused) as e:
        sh.frozen(reg)
    assert not isinstance(e.value, sh.ShadowDormant) and "ARCHITECT 2026-10-09, addendum 24 item 2(d)" in str(e.value)
    monkeypatch.chdir(tmp_path)
    _pin_registry(monkeypatch, reg)
    res = CliRunner().invoke(cli, ["export-ncaa-predictions", "--dormant-ok"])
    assert res.exit_code == 2 and "addendum 24 item 2(d)" in res.output and "DORMANT" not in res.output
    assert "230" not in res.output and _files(tmp_path) == []
    r = sh.confirmation_counter(eid=sh.EID, export_dir=str(tmp_path))       # registry.LEDGER: pinned above
    assert r["state"] == "refused" and "230" not in r["why"] and "addendum 24 item 2(d)" in r["why"]


def test_on_a_pass_the_step_writes_the_entrys_probabilities_never_a_call(mine, tmp_path, monkeypatch):
    path, doc = sh.export(now=NOW, out_dir=str(tmp_path / "ex"), registry_path=_v2_registry(tmp_path),
                          eid=sh.V2_EID)
    assert (doc["engine"], doc["registry_id"], doc["gate_verdict"], doc["contains_predictions"]) == (
        "model_shadow", "ncaa-elo-v2", "PASS", False)
    (r,) = doc["predictions"]
    p = r["prediction"]
    assert r["engine"] == "model_shadow" and r["model_version"] == "ncaa_elo_v2"
    assert 0 < p["home_win_prob"] < 1 and p["away_win_prob"] == round(1 - p["home_win_prob"], 4)
    assert not {"call", "desk", "stake", "units", "order"} & (set(r) | set(p))     # never a call
    assert r["market"]["fair_prob"]["HOME"] > 0.5                                     # market-only, beside it
    # the neutral flag before kickoff, its rule stated in the ruled form (addendum 236 item 3(1)); no pregame row for
    # this fixture: absent, unknown (D8), the listed home's advantage
    assert p["neutral"] is None and p["neutral_flag"] == "absent: unknown, D8"
    assert p["neutral_rule"] == ("neutral per CFBD's pregame field, read 2034-06-01T12:00:00; absent: unknown, D8")
    assert p["home_adv_applied"] == 55.0                                              # the listed home's, unchanged
    # the chain's own command on the same PASS registry writes its file and exits 0
    from cli import cli

    monkeypatch.chdir(tmp_path)
    _pin_registry(monkeypatch, _v2_registry(tmp_path, name="pass.json"))
    res = CliRunner().invoke(cli, STEP)
    assert res.exit_code == 0, res.output
    (f,) = _files(tmp_path)
    assert json.loads(f.read_text())["registry_id"] == "ncaa-elo-v2" and "DORMANT" not in res.output


def _kalshi(s, mid, bid, ask, at):
    s.add(OddsSnapshot(match_id=mid, market="ML", selection="HOME", devig_prob=(bid + ask) / 2, n_books=0,
                       captured_at=at, source="kalshi", yes_bid=bid, yes_ask=ask))


def test_the_grade_against_the_kalshi_close_is_the_close_records_rule_per_name(mine, tmp_path, monkeypatch):
    from src.walters import kalshi_legs
    from src.walters.vs_close import block

    ex = tmp_path / "ex"
    _, doc = sh.export(now=NOW, out_dir=str(ex), registry_path=_v2_registry(tmp_path), eid=sh.V2_EID)
    p = doc["predictions"][0]["prediction"]["home_win_prob"]
    up = mine["up"]
    with session_scope() as s:
        m = s.get(Match, up)
        when = m.utc_date
        m.status, m.home_score, m.away_score = MatchStatus.FINISHED, 31, 13
        s.add(NCAACFBDLabel(match_id=up, source="cfbd", source_game_id=up, season="2026", orientation="same",
                            neutral=False, home_score=31, away_score=13, fetched_at=NOW))
        _kalshi(s, up, 0.70, 0.72, NOW + timedelta(hours=4))          # the last two-sided pre-kickoff HOME quote
        _kalshi(s, up, 0.40, 0.41, NOW + timedelta(hours=6))          # after kickoff: never read
    v2 = lambda: sh.grade(days=3650, export_dir=str(ex), now=NOW + timedelta(days=1), eid=sh.V2_EID)  # noqa: E731
    try:
        monkeypatch.setattr(nb, "v2_run_recorded", lambda *a, **k: True)
        monkeypatch.setattr(sh, "v2_verdict_recorded", lambda: True)    # 236 item 3(2): the run AND its verdict
        monkeypatch.setattr(sh, "d4_rate", lambda eid: (None, "no run record (test)"))
        r = v2()
        assert r["graded"] == 1 and set(r["vs_kalshi_close"]) == {"ncaa_elo_v2"}     # each name on its own
        assert r["vs_kalshi_close"]["ncaa_elo_v2"] == block([(p, 0.71)])            # home won: the HOME mid
        assert r["kalshi_close_excluded"] == {"identity_mismatch": 0, "fenced_2023": 0, "fenced_2026": 0,
                                              "three_way": 0, "no_result": 0, "tie": 0,
                                              "legs_before_2026_10_13": 0, "mismatched": 0, "no_close": 0}
        assert "kalshi_close_H=0.710" in r["lines"][0] and "books not read" in r["kalshi_close_rule"]
        with session_scope() as s:                                    # the record's own function, the same close
            m = s.get(Match, up)
            cl, why = paper.guarded_two_way_close(m, paper._kalshi_snaps(s, [up])[up], {}, {}, None, {})
            assert why is None and cl["fair"]["HOME"] == pytest.approx(0.71)
            s.rollback()
        # mismatched legs: left out, never priced
        monkeypatch.setattr(kalshi_legs, "mismatched", lambda conn, ids, *a: {up: ["KXNCAAFGAME-A", "KXNCAAFGAME-B"]})
        r = v2()
        assert r["vs_kalshi_close"]["ncaa_elo_v2"]["games"] == 0 and r["kalshi_close_excluded"]["mismatched"] == 1
        assert "kalshi_close_H=— (mismatched)" in r["lines"][0]
        monkeypatch.setattr(kalshi_legs, "mismatched", lambda conn, ids, *a: {})
        # the last two-sided quote wider than the 2c cap: no close (an older, tighter one is never substituted)
        with session_scope() as s:
            _kalshi(s, up, 0.60, 0.70, NOW + timedelta(hours=4, minutes=30))
        r = v2()
        assert r["vs_kalshi_close"]["ncaa_elo_v2"]["games"] == 0 and r["kalshi_close_excluded"]["no_close"] == 1
        # the record's 2026 fence: until ncaa-elo-v2's run is recorded, a 2026 game is fenced, never scored
        monkeypatch.setattr(nb, "v2_run_recorded", lambda *a, **k: False)
        r = v2()
        assert r["kalshi_close_excluded"]["fenced_2026"] == 1 and r["vs_kalshi_close"]["ncaa_elo_v2"]["games"] == 0
        # the record's ORDER: the fence before the result, as paper.close_record tests it; a fenced tie is fenced
        with session_scope() as s:
            m, lab = s.get(Match, up), s.get(NCAACFBDLabel, up)
            m.home_score = m.away_score = lab.home_score = lab.away_score = 21
        r = v2()
        assert (r["ties_skipped"], r["kalshi_close_excluded"]["tie"], r["kalshi_close_excluded"]["fenced_2026"]) == (
            1, 0, 1)
        monkeypatch.setattr(nb, "v2_run_recorded", lambda *a, **k: True)      # unfenced: the tie is the tie
        r = v2()
        assert (r["kalshi_close_excluded"]["tie"], r["kalshi_close_excluded"]["fenced_2026"]) == (1, 0)
        # the shadow's own identity guard is counted first, so every finished call lands in exactly one
        with session_scope() as s:
            s.get(Match, up).utc_date += timedelta(minutes=5)
        r = v2()
        x = r["kalshi_close_excluded"]
        assert x["identity_mismatch"] == 1 and r["vs_kalshi_close"]["ncaa_elo_v2"]["games"] + sum(x.values()) == 1
    finally:
        with session_scope() as s:
            s.query(OddsSnapshot).filter(OddsSnapshot.match_id == up).delete(synchronize_session=False)
            lab = s.get(NCAACFBDLabel, up)
            if lab is not None:
                s.delete(lab)
            m = s.get(Match, up)
            m.status, m.home_score, m.away_score = MatchStatus.SCHEDULED, None, None
            m.utc_date = when


def _reg_file(tmp_path, verdict):
    p = tmp_path / f"reg_{verdict}.json"
    p.write_text(json.dumps([{"id": sh.V2_EID, "status": "declared",
                              "verdict": None if verdict is None else {"verdict": verdict, "ruling": "x"}}]))
    return str(p)


def _row(s, mid, **over):
    """A shadow row carrying stored match `mid`'s own teams and kickoff (same_fixture's identity), `over` replacing."""
    m = s.get(Match, mid)
    return {"match_id": mid, "home_team": m.home_team.name, "away_team": m.away_team.name,
            "utc_date": m.utc_date.isoformat(), **over}


def _shadow_file(d, rows, at="2034-01-02T00:00:00"):
    d.mkdir(exist_ok=True)
    (d / "ncaa_shadow_2034-01-02_000000.json").write_text(json.dumps({
        "engine": "model_shadow", "competition": "NCAA", "registry_id": "ncaa-elo-v2", "exported_at": at,
        "predictions": rows}))
    return str(d)


def test_the_counter_is_dormant_until_a_pass_then_counts_without_a_figure(mine, tmp_path, monkeypatch):
    from src.walters import ncaa_v1r_gate as g

    for verdict, what in ((None, "no verdict"), ("FAIL", "the verdict FAIL")):
        _pin_registry(monkeypatch, _reg_file(tmp_path, verdict))
        r = sh.confirmation_counter(export_dir=str(tmp_path))
        assert r == {"state": "dormant", "why": sh.dormant_reason("ncaa-elo-v2", verdict)}
        assert sh.counter_line(r, "ncaa-elo-v2") == (f"confirmation counter ncaa-elo-v2: DORMANT — the registry "
                                                     f"records {what} for ncaa-elo-v2: dormant while the verdict is "
                                                     "null or FAIL (ARCHITECT 2026-11-03, addendum 230 item 1(b))")
    passed = _reg_file(tmp_path, "PASS")
    _pin_registry(monkeypatch, passed)
    monkeypatch.setattr(g, "confirmation_count",
                        lambda spec, path=None: (_ for _ in ()).throw(g.GateRefused("no run record")))
    assert sh.confirmation_counter(export_dir=str(tmp_path)) == {"state": "refused", "why": "no run record"}
    a, b = mine["finished"][-2:]                                      # two stored fixtures, scored
    c, d = mine["up"], mine["far"]                                    # two stored fixtures, pending
    count = {"n": 2, "scored_ids": [a, b], "cohort_ids": [a, b, c, d], "n_games": 100, "bar": 0.6931,
             "cohort_state": "frozen", "cohort_size": 4, "eligible_stored": 120, "release_due": 0, "complete": False,
             "pending": [{"id": c, "status": "scheduled"}, {"id": d, "status": "finished"}]}
    monkeypatch.setattr(g, "confirmation_count", lambda spec, path=None: dict(count))
    with session_scope() as s:
        rows = [_row(s, b), _row(s, c), _row(s, c, match_id=10 ** 9)]     # the last: no cohort fixture
    r = sh.confirmation_counter(export_dir=_shadow_file(tmp_path / "ex", rows))
    assert (r["state"], r["n"], r["shadow_rows"], r["shadow_rows_scored"], r["shadow_identity_mismatch"]) == (
        "counting", 2, 2, 1, 0)
    line = sh.counter_line(r, "ncaa-elo-v2")
    assert line.startswith("confirmation counter ncaa-elo-v2: 2/100 scored · cohort FROZEN (4/100 fixtures; 120 "
                           "eligible stored) · pending 2 {'scheduled': 1, 'finished': 1}")
    assert ("shadow row before kickoff: 2 of the cohort, 1 of the scored (0 not the fixture's teams and kickoff, "
            "never counted)") in line and line.endswith("not a verdict")
    assert "log-loss" not in line and "0.6931" not in line and "CONFIRMED" not in line


def test_the_grade_cli_prints_the_kalshi_record_and_the_counter(tmp_path, monkeypatch):
    from cli import cli
    from src.walters import registry as reg

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(reg, "LEDGER", _reg_file(tmp_path, None))
    res = CliRunner().invoke(cli, ["ncaa-shadow-grade", "--id", "ncaa-elo-v2"])
    assert res.exit_code == 0, res.output
    out = res.output.splitlines()
    assert any(x.startswith("  ── the record against THE close, Kalshi (THE close for college (KXNCAAFGAME") for x in out)
    assert "     ncaa_elo_v2: vs close: no decided game with a close" in out
    # 236 item 3(2): the headline's pick-vs-close and value-side are the book close's, labelled as the reference
    head = next(x for x in out if x.startswith("  ── NCAA shadow ncaa-elo-v2"))
    assert "· reference (book close, never THE close): mean pick-vs-close " in head and "· value-side " in head
    assert head.index("reference (book close") < head.index("mean pick-vs-close")
    assert out[-1] == ("  ── confirmation counter ncaa-elo-v2: DORMANT — the registry records no verdict for "
                       "ncaa-elo-v2: dormant while the verdict is null or FAIL (ARCHITECT 2026-11-03, addendum 230 "
                       "item 1(b))")


# ------------------------------------------------------------------------- Codex round 1 on #816 --

def test_the_counter_refuses_a_registry_without_the_declaration_never_dormant(tmp_path, monkeypatch):
    """Codex on #816 (4459156514): a registry holding no ncaa-elo-v2 entry is the export's refusal (not declared),
    never DORMANT (230 item 1(b)'s dormancy is a null or FAIL verdict on a declared entry)."""
    empty = tmp_path / "empty.json"
    empty.write_text("[]")
    with pytest.raises(sh.ShadowRefused) as e:                        # the export's refusal: not dormant
        sh.frozen(str(empty), eid=sh.V2_EID)
    assert not isinstance(e.value, sh.ShadowDormant) and str(e.value) == f"REFUSED: {sh.not_declared(sh.V2_EID)}"
    for eid in (sh.V2_EID, sh.EID):
        _pin_registry(monkeypatch, str(empty))
        r = sh.confirmation_counter(eid=eid, export_dir=str(tmp_path))
        assert r == {"state": "refused", "why": sh.not_declared(eid)}
        line = sh.counter_line(r, eid)
        assert line.startswith(f"confirmation counter {eid}: REFUSED — {eid} is not declared in docs/registry")
        assert "DORMANT" not in line and "230" not in line


def test_the_counter_reads_one_registry_for_the_verdict_and_the_count(tmp_path, monkeypatch):
    """Codex on #816 (4459156501), then addendum 236 item 3(7): the counter reads ONE registry, registry.LEDGER at
    call time, for the verdict AND for the count's confirming(); it takes no path, so there is no second source."""
    import inspect

    from src.walters import ncaa_v1r_gate as g

    assert "registry_path" not in inspect.signature(sh.confirmation_counter).parameters
    assert "registry_path" not in inspect.signature(sh.confirmation_record).parameters
    # PASS on LEDGER, whose entry has no run record: the count refuses on THAT entry ("no run record")
    no_run = _reg_file(tmp_path, "PASS")
    _pin_registry(monkeypatch, no_run)
    r = sh.confirmation_counter(export_dir=str(tmp_path))
    assert r["state"] == "refused" and "has no run record" in r["why"] and "no PASS verdict" not in r["why"]
    seen = []
    monkeypatch.setattr(g, "confirmation_count", lambda spec, path=None: seen.append(path) or (_ for _ in ()).throw(
        g.GateRefused("stop")))
    sh.confirmation_counter(export_dir=str(tmp_path))
    run = {"run_at": "2026-10-19T00:00:00Z", "n_scored": 0, "ids_file": None, "result": {"baseline_home_rate": 0.6}}
    failed = tmp_path / "failed.json"                                  # FAIL, with its run record: dormant, unread
    failed.write_text(json.dumps([{"id": sh.V2_EID, "verdict": {"verdict": "FAIL", "ruling": "x"}, "run": run}]))
    _pin_registry(monkeypatch, str(failed))
    assert sh.confirmation_counter(export_dir=str(tmp_path))["state"] == "dormant"
    assert seen == [no_run]                                            # the count read LEDGER's path as it stood


def test_the_counter_counts_a_shadow_row_only_when_it_is_the_fixtures(mine, tmp_path, monkeypatch, capsys):
    """Codex on #816 (4459156509): ids are machine-local (last_calls); a stale file whose id is reused for another
    fixture (other teams, or another kickoff) is never the cohort fixture's shadow row: grade()'s identity guard
    (same_fixture), counted apart and printed."""
    from src.walters import ncaa_v1r_gate as g

    a, b = mine["finished"][-2:]
    c, d = mine["up"], mine["far"]
    count = {"n": 2, "scored_ids": [a, b], "cohort_ids": [a, b, c, d], "n_games": 100, "bar": 0.6931,
             "cohort_state": "provisional", "cohort_size": 4, "eligible_stored": 4, "release_due": 0,
             "complete": False, "pending": [{"id": c, "status": "scheduled"}, {"id": d, "status": "scheduled"}]}
    monkeypatch.setattr(g, "confirmation_count", lambda spec, path=None: dict(count))
    with session_scope() as s:
        rows = [_row(s, a),                                            # a's own: counted (scored)
                _row(s, b, home_team="NSH Team 4"),                    # b's id, another fixture's teams: not b's
                _row(s, c),                                            # c's own: counted
                _row(s, d, utc_date=(s.get(Match, d).utc_date + timedelta(days=1)).isoformat())]  # another kickoff
    _pin_registry(monkeypatch, _reg_file(tmp_path, "PASS"))
    r = sh.confirmation_counter(export_dir=_shadow_file(tmp_path / "stale", rows))
    assert (r["shadow_rows"], r["shadow_rows_scored"], r["shadow_identity_mismatch"]) == (2, 1, 2)
    line = sh.counter_line(r, "ncaa-elo-v2")
    assert ("shadow row before kickoff: 2 of the cohort, 1 of the scored (2 not the fixture's teams and kickoff, "
            "never counted)") in line
    # the same guard as grade()'s: a row it refuses is one grade() never grades
    with session_scope() as s:
        assert [sh.same_fixture(x, s.get(Match, x["match_id"])) for x in rows] == [True, False, True, False]
        assert sh.same_fixture(rows[0], None) is False
