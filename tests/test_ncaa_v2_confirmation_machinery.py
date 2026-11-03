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


def _pin_registry(monkeypatch, path):
    """The export reads `path` (ncaa_shadow.frozen with that registry), whatever the committed registry says."""
    real = sh.frozen
    monkeypatch.setattr(sh, "frozen", lambda registry_path=None, eid=sh.EID: real(path, eid=eid))


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
    r = sh.confirmation_counter(eid=sh.EID, registry_path=reg, export_dir=str(tmp_path))
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
    # the neutral flag before kickoff, its rule stated: D8's, never a provider fact
    assert p["neutral"] is None and p["neutral_flag"] == "unknown before the game"
    assert p["neutral_rule"] == sh.NEUTRAL_PREGAME_RULE and "Never a provider fact" in p["neutral_rule"]
    assert "Until then the shadow prices an upcoming game with the listed home's advantage" in p["neutral_rule"]
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
        r = v2()
        assert r["graded"] == 1 and set(r["vs_kalshi_close"]) == {"ncaa_elo_v2"}     # each name on its own
        assert r["vs_kalshi_close"]["ncaa_elo_v2"] == block([(p, 0.71)])            # home won: the HOME mid
        assert r["kalshi_close_excluded"] == {"identity_mismatch": 0, "fenced_2023": 0, "fenced_2026": 0,
                                              "three_way": 0, "no_result": 0, "tie": 0, "mismatched": 0,
                                              "no_close": 0}
        assert "kalshi_close_H=0.710" in r["lines"][0] and "books not read" in r["kalshi_close_rule"]
        with session_scope() as s:                                    # the record's own function, the same close
            m = s.get(Match, up)
            cl, why = paper.guarded_two_way_close(m, paper._kalshi_snaps(s, [up])[up], {}, {}, None, {})
            assert why is None and cl["fair"]["HOME"] == pytest.approx(0.71)
            s.rollback()
        # mismatched legs: left out, never priced
        monkeypatch.setattr(kalshi_legs, "mismatched", lambda conn, ids: {up: ["KXNCAAFGAME-A", "KXNCAAFGAME-B"]})
        r = v2()
        assert r["vs_kalshi_close"]["ncaa_elo_v2"]["games"] == 0 and r["kalshi_close_excluded"]["mismatched"] == 1
        assert "kalshi_close_H=— (mismatched)" in r["lines"][0]
        monkeypatch.setattr(kalshi_legs, "mismatched", lambda conn, ids: {})
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


def test_the_counter_is_dormant_until_a_pass_then_counts_without_a_figure(tmp_path, monkeypatch):
    from src.walters import ncaa_v1r_gate as g

    for verdict, what in ((None, "no verdict"), ("FAIL", "the verdict FAIL")):
        r = sh.confirmation_counter(registry_path=_reg_file(tmp_path, verdict), export_dir=str(tmp_path))
        assert r == {"state": "dormant", "why": sh.dormant_reason("ncaa-elo-v2", verdict)}
        assert sh.counter_line(r, "ncaa-elo-v2") == (f"confirmation counter ncaa-elo-v2: DORMANT — the registry "
                                                     f"records {what} for ncaa-elo-v2: dormant while the verdict is "
                                                     "null or FAIL (ARCHITECT 2026-11-03, addendum 230 item 1(b))")
    passed = _reg_file(tmp_path, "PASS")
    monkeypatch.setattr(g, "confirmation_count", lambda spec: (_ for _ in ()).throw(g.GateRefused("no run record")))
    assert sh.confirmation_counter(registry_path=passed, export_dir=str(tmp_path)) == {"state": "refused",
                                                                                         "why": "no run record"}
    count = {"n": 2, "scored_ids": [11, 12], "cohort_ids": [11, 12, 13, 14], "n_games": 100, "bar": 0.6931,
             "cohort_state": "frozen", "cohort_size": 4, "eligible_stored": 120, "release_due": 0, "complete": False,
             "pending": [{"id": 13, "status": "scheduled"}, {"id": 14, "status": "finished"}]}
    monkeypatch.setattr(g, "confirmation_count", lambda spec: dict(count))
    ex = tmp_path / "ex"
    ex.mkdir()
    (ex / "ncaa_shadow_2034-06-01_120000.json").write_text(json.dumps({
        "engine": "model_shadow", "competition": "NCAA", "registry_id": "ncaa-elo-v2",
        "exported_at": "2034-06-01T12:00:00",
        "predictions": [{"match_id": 12, "utc_date": "2034-06-01T18:00:00"},
                        {"match_id": 13, "utc_date": "2034-06-01T19:00:00"},
                        {"match_id": 99, "utc_date": "2034-06-01T19:00:00"}]}))
    r = sh.confirmation_counter(registry_path=passed, export_dir=str(ex))
    assert (r["state"], r["n"], r["shadow_rows"], r["shadow_rows_scored"]) == ("counting", 2, 2, 1)
    line = sh.counter_line(r, "ncaa-elo-v2")
    assert line.startswith("confirmation counter ncaa-elo-v2: 2/100 scored · cohort FROZEN (4/100 fixtures; 120 "
                           "eligible stored) · pending 2 {'scheduled': 1, 'finished': 1}")
    assert "shadow row before kickoff: 2 of the cohort, 1 of the scored" in line and line.endswith("not a verdict")
    assert "log-loss" not in line and "0.6931" not in line and "CONFIRMED" not in line


def test_the_grade_cli_prints_the_kalshi_record_and_the_counter(tmp_path, monkeypatch):
    from cli import cli
    from src.walters import registry as reg

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(reg, "LEDGER", _reg_file(tmp_path, None))
    res = CliRunner().invoke(cli, ["ncaa-shadow-grade", "--id", "ncaa-elo-v2"])
    assert res.exit_code == 0, res.output
    out = res.output.splitlines()
    assert any(x.startswith("  ── the record against the Kalshi close (the close record's two-way rule") for x in out)
    assert "     ncaa_elo_v2: vs close: no decided game with a close" in out
    assert out[-1] == ("  ── confirmation counter ncaa-elo-v2: DORMANT — the registry records no verdict for "
                       "ncaa-elo-v2: dormant while the verdict is null or FAIL (ARCHITECT 2026-11-03, addendum 230 "
                       "item 1(b))")
