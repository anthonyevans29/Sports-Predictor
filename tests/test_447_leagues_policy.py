"""THE LEAGUES' CONFIRMATION POLICY (ARCHITECT 2026-11-22, addendum 447 item 3 C1-C3 and item 4 PR 2; addendum 448
items 1(a), 1(b) and 2(a) as addendum 455 item 4 restates them; check_plan's part is #1080's, 449 item 6(b)).

On a tmp registry and a throwaway SQLite (tests/conftest.py); the real docs/registry/experiments.json is read, never
written. Pins:
  C2   while an entry is CONFIRMING its fence stays, cut at the opening's kickoff INCLUSIVE, one site (fence_cutoff);
       it lifts after a REJECT and once the confirmation is recorded, either way (448 item 1(b)); a confirming entry
       whose run record holds no opening keeps the window's own fence (law 4);
  C1(b) record_confirmation checks the first game against the opening's kickoff (not earlier), for an entry whose run
       record carries the opening; an entry without one keeps today's rule (after verdict.at);
  C3(a) the five leagues entries carry the one plan, taken by check_plan;
  C3(b) a leagues entry at status production changes no export and no Desk call."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.walters import leagues_window as lw
from src.walters import registry as reg
from src.walters import soccer_expansion as sx

ROOT = Path(__file__).resolve().parent.parent
SEASON = lw.SEASON
AT = "2026-11-02T18:10:00Z"
OPEN_KO = datetime(2026, 12, 6, 15, 0)
OPENING = {"kickoff": "2026-12-06T15:00:00Z", "match_id": 4242}
PLAN = {"n_games": 60, "metric": "log_loss", "bar": None, "must_beat_reference": True,
        "reference": "the close (the grader's close, on the same games)"}


class G:                                     # a game, as fenced() reads one
    def __init__(self, ko, season=SEASON):
        self.utc_date, self.season = ko, season


def _entry(code="SA", status="declared", verdict=None, opening=OPENING, **kw):
    run = None if verdict is None else {"result": ({"confirmation_opens_after": opening} if opening else {})}
    e = {"id": lw.DECLARATION_IDS[code], "competition": code, "declared_at": AT, "status": status, "run": run,
         "verdict": verdict, "frozen_constants": {"production_version": "v22", "rho": -0.1, "elo_goal_coeff": 0.0008},
         "confirmation_plan": dict(PLAN)}
    e.update(kw)
    return e


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    p = tmp_path / "experiments.json"

    def write(*entries):
        real = {e["id"]: e for e in reg.load(str(ROOT / "docs" / "registry" / "experiments.json"))}
        p.write_text(json.dumps([real[sx.EID], *entries]))
    monkeypatch.setattr(reg, "LEDGER", str(p))
    monkeypatch.setattr(reg, "IDS_DIR", str(tmp_path / "ids"))
    write()
    return write


PASS = {"verdict": "PASS", "ruling": "r", "at": "2026-12-07T12:00:00Z"}


# ------------------------------------------------------------------------------------------- C2: the fence --

def test_c2_while_confirming_the_fence_is_cut_at_the_openings_kickoff_inclusive(ledger):
    ledger(_entry(status="confirming", verdict=PASS))
    cut = lw.fence_cutoff("SA", SEASON)
    assert cut == OPEN_KO - timedelta(microseconds=1) and lw.fence_cutoff("SA") == cut
    assert lw.fenced(cut, G(OPEN_KO))                                   # the opening's kickoff itself: fenced
    assert lw.fenced(cut, G(OPEN_KO + timedelta(hours=1)))              # later: fenced
    assert not lw.fenced(cut, G(OPEN_KO - timedelta(seconds=1)))        # earlier: readable
    assert not lw.fenced(cut, G(OPEN_KO, season="2025/26"))             # another season: never
    assert lw.fence_refusal("SA", SEASON, through=OPEN_KO - timedelta(seconds=1)) is None
    why = lw.fence_refusal("SA", SEASON, through=OPEN_KO)
    assert "AT OR AFTER the opening, the 60th member's kickoff 2026-12-06T15:00:00Z (match 4242)" in why
    assert "confirming" in why and "14:59:59" not in why                # its own wording, never the shifted cut
    assert sx.guards_backtest("SA", SEASON) == why                      # every guard reads the one site
    assert sx.guards_backtest("SA", SEASON, through=cut) is None


@pytest.mark.parametrize("status, verdict", [
    ("closed", {"verdict": "REJECT", "ruling": "r", "at": "2026-12-07T12:00:00Z"}),     # after a REJECT
    ("production", PASS),                                                               # CONFIRMED
    ("closed", PASS),                                                                   # NOT_CONFIRMED
])
def test_c2_the_fence_lifts_after_a_reject_and_once_the_confirmation_is_recorded_either_way(ledger, status, verdict):
    ledger(_entry(status=status, verdict=verdict))
    assert lw.fence_cutoff("SA", SEASON) is None and lw.fence_refusal("SA", SEASON) is None


def test_c2_a_confirming_entry_with_no_opening_keeps_the_windows_own_fence(ledger):
    ledger(_entry(status="confirming", verdict=PASS, opening=None))
    assert lw.fence_cutoff("SA", SEASON) == lw.parse_instant(AT)
    ledger(_entry(status="confirming", verdict=PASS, opening={"kickoff": "soon", "match_id": 1}))
    assert lw.fence_cutoff("SA", SEASON) == lw.parse_instant(AT)


def test_c2_without_a_verdict_nothing_changes(ledger):
    ledger(_entry())
    assert lw.fence_cutoff("SA", SEASON) == lw.parse_instant(AT)
    ledger()
    assert lw.fence_cutoff("SA", SEASON) == lw.PRE_DECLARATION_CUT


def test_c2_pd_soccer_expansion_record_is_no_longer_refused_once_the_leagues_verdict_is_recorded(ledger):
    """447 C2 on PD: soccer-expansion-v1's frozen PD cohort ends before any opening, so once leagues-pd-v1's verdict
    is recorded, PASS (confirming, its opening after the cohort) or REJECT, no cohort game is fenced: the
    confirmation's guard on its own cut reads clear."""
    cohort_last = datetime(2026, 11, 27, 20, 0)                         # 16267's stored kickoff (453 item 1(c))
    ledger(_entry("PD"))
    assert lw.fenced(lw.fence_cutoff("PD", SEASON), G(cohort_last))     # before the verdict: fenced
    for status, verdict in (("confirming", PASS), ("closed", {"verdict": "REJECT", "ruling": "r",
                                                               "at": "2026-12-07T12:00:00Z"})):
        ledger(_entry("PD", status=status, verdict=verdict))
        cut = lw.fence_cutoff("PD", SEASON)
        assert not lw.fenced(cut, G(cohort_last)) and lw.fence_refusal("PD", SEASON, through=cohort_last) is None


# ------------------------------------------------------------------------------ C1(b): record_confirmation --

def _confirming_file(tmp_path, opening=OPENING):
    p = tmp_path / "x.json"
    e = {"id": "x-v1", "status": "confirming", "confirmation_plan": dict(PLAN),
         "verdict": {"verdict": "PASS", "at": "2026-12-07T12:00:00Z"},
         "run": {"result": ({"confirmation_opens_after": opening} if opening else {}), "ids_file": None}}
    p.write_text(json.dumps([e]))
    return str(p)


def _res(first):
    return {"first_game_at": first, "log_loss": 0.98, "reference_log_loss": 0.99}


@pytest.mark.parametrize("first, ok", [("2026-12-06T14:59:59Z", False), ("2026-12-06T15:00:00Z", True),
                                       ("2026-12-06T15:00:00", True), ("2026-12-06T16:00:00Z", True)])
def test_c1b_the_first_game_is_checked_against_the_openings_kickoff_not_the_verdict(tmp_path, first, ok):
    """A game played before the verdict's stamp may enter (447 C1(c)): the opening is the bound, not verdict.at."""
    p = _confirming_file(tmp_path)
    if ok:
        e = reg.record_confirmation("x-v1", list(range(1, 61)), _res(first), "r", p, str(tmp_path / "ids"))
        assert e["confirmation"]["outcome"] == "CONFIRMED"
    else:
        with pytest.raises(reg.RegistryError, match="not start earlier than the opening"):
            reg.record_confirmation("x-v1", list(range(1, 61)), _res(first), "r", p, str(tmp_path / "ids"))


def test_c1b_an_entry_without_the_opening_keeps_todays_rule(tmp_path):
    p = _confirming_file(tmp_path, opening=None)
    with pytest.raises(reg.RegistryError, match="must all start AFTER the verdict"):
        reg.record_confirmation("x-v1", list(range(1, 61)), _res("2026-12-06T16:00:00Z"), "r", p,
                                str(tmp_path / "ids"))
    e = reg.record_confirmation("x-v1", list(range(1, 61)), _res("2026-12-08T00:00:00Z"), "r", p,
                                str(tmp_path / "ids2"))
    assert e["confirmation"]["outcome"] == "CONFIRMED"


def test_c1b_an_unreadable_first_game_refuses(tmp_path):
    p = _confirming_file(tmp_path)
    for bad in (None, "", "soon"):
        with pytest.raises(reg.RegistryError, match="opening"):
            reg.record_confirmation("x-v1", list(range(1, 61)), _res(bad), "r", p, str(tmp_path / "ids"))


# --------------------------------------------------------------------------------------- C3: the plans --

def test_c3a_the_five_entries_carry_the_one_plan_taken_by_check_plan():
    real = {e["id"]: e for e in reg.load(str(ROOT / "docs" / "registry" / "experiments.json"))}
    for eid in lw.DECLARATION_IDS.values():
        assert real[eid]["confirmation_plan"] == PLAN and reg.check_plan(real[eid]["confirmation_plan"]) == PLAN


def test_c3b_a_leagues_entry_at_production_changes_no_export_and_no_desk_call(ledger):
    """447 C3(b): what decides a leagues call is code, never a status. At production: the shadow binding is the one it
    was at declared; the Desk's shadow set and predict's refusal stand; the fence is lifted (448 item 1(b))."""
    import cli
    from src.walters import desk_policy as dp
    ledger(_entry())
    before = sx.shadow_binding("SA")
    ledger(_entry(status="production", verdict=PASS))
    after = sx.shadow_binding("SA")
    assert {k: after[k] for k in ("state", "candidate", "declared_at", "frozen_constants")} == {
        k: before[k] for k in ("state", "candidate", "declared_at", "frozen_constants")}
    assert "SA" in dp.SHADOW_VENUE_COMPS
    with pytest.raises(SystemExit) as ex:
        cli._refuse_shadow_league("SA", "predict")
    assert ex.value.code == 2
    assert lw.fence_cutoff("SA", SEASON) is None
