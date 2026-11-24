"""SOCCER-V23'S DECLARATION (ARCHITECT 2026-11-23 08:05 ET, addendum 449; GATE-CLASS; lane soccer-v23, #656).

The real docs/registry/experiments.json, read only (never written here):
  item 1   declared_at 2026-11-23T13:05:00Z; the gate is BAR_TEXT as #1070 merged it, sha256 d4778a27...;
  item 2   the slots, as ruled, the two recorded figures in order with the one source verbatim;
  item 3   frozen_constants exactly the listed keys and values, equal to code_constants() on this checkout;
  item 4   the prose fields verbatim (the addendum's own text, its line breaks joined by one space);
  item 5   confirmation_window verbatim; confirmation_plan the reference-only bar;
  item 6   (a) appended after leagues-bl1-v1, status declared, run and verdict null; (c) constants_state,
           slots_state and bar_state read it clean and check_plan passes its plan;
  item 6(b) check_plan's reference-only bar (447 C3 (c1)): bar null admitted only with must_beat_reference true and
           a named reference; record_confirmation computes metric < reference alone, strict (a tie fails), with no
           TypeError; every other plan keeps today's rule.
Nothing of soccer-v23 runs on real data here."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.walters import registry as reg
from src.walters import soccer_v23 as v

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "docs" / "registry" / "experiments.json"
BAR_SHA = "d4778a276359f11cb89fe7b0694458ba7e01da6fa2a7971a320f5e90eb2371c4"   # 449 item 1, as the architect computed it

SOURCE = ("soccer-backtest with v22 in production (production's rho -0.1 and Elo goal coefficient 0.0008 since #142, "
          "min_prior 40, soccer_calibration): the operator's console of 2026-10-08 on the laptop at c3a3744, recorded "
          "that day in BACKLOG under READ (ARCHITECT, addendum 10, item 2): 340 predictions per season, log-loss 0.9956 "
          "(2024/25) and 1.0465 (2025/26). Named the record's figures by ARCHITECT 2026-11-21 18:57 ET, addendum 443 "
          "item 1(a).")
CONSTANTS = {"K_PRIOR": 5.0, "G0": 1.4, "B0": 1.15, "PROMOTED_ATTACK_MULT": 0.85, "PROMOTED_DEFENCE_MULT": 1.15,
             "CARRY": 1.0, "ELO_SCALE": 100.0, "MAX_ITER": 100, "MAX_HALVINGS": 60, "TOL": 1e-12,
             "PRECISION_FLOOR": 1e-12, "V22_MIN_MATCHES": 30, "V22_BACKFILL_LIMIT": 500, "WITHIN_SEASON_SKIP": 0,
             "RESULT_LAG_HOURS": 4, "BETA_PRIOR_MEAN": 0.0, "BETA_PRIOR_PRECISION": 7.0, "RELEGATED_ATTACK": 0.0,
             "RELEGATED_DEFENCE": 0.0, "PYRAMIDS": [["PL", "ELC", "EL1", "EL2"]], "SOURCE_CADENCE_HOURS": {}}
PLAN = {"n_games": 60, "metric": "log_loss", "bar": None, "must_beat_reference": True,
        "reference": "live v22: the production probabilities on the same stored row, on the same 60 games"}
PROSE = {
    "lane": "#656 (soccer-v23, v22's successor: ARCHITECT 2026-11-02 10:50 ET, addendum 216 item 3; roadmap lane "
            "soccer-v23; declared ARCHITECT 2026-11-23, addendum 449)",
    "candidate": "soccer_joint_poisson on v22 (addendum 216 item 3; addendum 263 item 1): the joint log-linear model "
                 "log lambda_H = mu + h + alpha_H + delta_A + beta*dE, log lambda_A = mu + alpha_A + delta_H - beta*dE, "
                 "fitted per competition window as docs/specs/soccer-v23.md states it, the Dixon-Coles correction kept "
                 "at v22's stored rho, the per-team early-season continuity built in. The code is "
                 "src/models/joint_poisson.py and src/walters/soccer_v23.py as on main at this entry's merge base; the "
                 "constants are frozen_constants; no ModelVersion is minted.",
    "declaration": "ARCHITECT 2026-11-23, addendum 449 (the slots, the constants, the test set, the confirmation); the "
                   "bar by addenda 216 item 3, 230 item 1(d), 248 item 2(b), 251 item 2 and 443 item 1(c); the "
                   "design's questions by addenda 254 item 3 and 263; docs/specs/soccer-v23.md",
    "training_cutoff": "nothing is fitted on the pot ahead of the walk: at each fixture soccer-v23's parameters are "
                       "estimated from the finished games visible before it under the day rule (a game visible at its "
                       "kickoff plus RESULT_LAG_HOURS), as BAR_TEXT states; the constants are frozen_constants and "
                       "none is selected by this candidate; v22's rho and Elo goal coefficient are read from the "
                       "copy's production row and bound in the run record (v22_params_sha256)",
    "test_set": "THE FROZEN POT (addendum 216 item 3; addendum 263 items 2, 3, 7 and 14): every regular-round match of "
                "the store's LEAGUE-type competitions that soccer-v23's harness scores under the declaration slots, "
                "kicking off at or before the cut 2026-10-30T15:00:00Z, each competition's first pot season scored "
                "under the weak prior, the within-season skip zero, a competition-season with no home or no away goal "
                "excluded by cause; read on the run's .backup copy and bound by the stream fingerprint. Its count is "
                "the run record's (CLAUDE.md's label, 16,546 matches / 24 competitions, is a label and never a pass "
                "condition). Within it, v22's two recorded sets: PL 2024/25 and PL 2025/26, 340 matches each, as "
                "soccer-backtest's own walk names them on the copy.",
    "prior_reads_note": "The pot has been read before, and BAR_TEXT says so (263 item 9): v22's rho and Elo goal "
                        "coefficient were selected on it, and S19, dc-fit, s14 and soccer-expansion-v1 read it. That "
                        "tilts toward the incumbent, the conservative direction, accepted, and a PASS is read against "
                        "it.",
    "ratified": "ARCHITECT 2026-11-23, addendum 449"}
WINDOW = (
    "ARCHITECT 2026-11-23, addendum 449 item 5: A PASS opens the 60-game prospective shadow of addendum 216 item 3 on "
    "the host's PL pages, beside live v22. THE WINDOW: PL 2026/27 games kicking off strictly after window_opens_at, "
    "the first PL kickoff strictly after the first host page that carries the v23_ keys, recorded from that page's "
    "receipt. THE COHORT: in kickoff order, then match id, the first 60 FINISHED games with a 90-minute result whose "
    "stored Prediction row on the host, last written before kickoff, carries both arms: v22's production "
    "probabilities and soccer-v23's shadow probabilities. A game whose row lacks the shadow arm, or carries its error, "
    "or was written at or after kickoff, takes no slot and is EXCLUDED BY CAUSE, named and counted; more than three "
    "such games before the 60th REFUSES the read, and the window is then the architect's to rule. A postponed game "
    "enters by its real kickoff. THE READ, ONE, by the architect, the day after the 60th game is final: each arm's "
    "mean three-way log-loss on the 60, by soccer_calibration, unrounded, both arms from the one stored row. "
    "CONFIRMED iff soccer-v23's is BELOW live v22's on the same 60 games; equal or above is NOT CONFIRMED. No fixed "
    "ceiling is added. The close's log-loss, Brier and RPS are printed beside both and gate nothing. Availability is "
    "OFF in the shadow (263 item 6). No other read of either arm on the window before the read. CONFIRMED does not "
    "switch the engine: soccer-v23 goes live by the architect's ruling and a version-bump PR, earliest the day after "
    "the read. NOT CONFIRMED: v22 stays, the entry closes, and the lane names its next candidate the same day. No date "
    "moves this.")


def _real() -> tuple[list, dict]:
    entries = json.loads(LEDGER.read_text())
    return entries, next(e for e in entries if e["id"] == v.EID)


# ------------------------------------------------------------------------------------------------ items 1-5 --

def test_449_items_1_and_6a_declared_at_the_stamp_appended_after_bl1_unrun():
    entries, e = _real()
    ids = [x["id"] for x in entries]
    assert ids.count(v.EID) == 1 and ids.index(v.EID) == ids.index("leagues-bl1-v1") + 1   # after BL1, found by id
    assert e["declared_at"] == "2026-11-23T13:05:00Z" and e["sport"] == "soccer"
    assert (e["status"], e["run"], e["verdict"]) == ("declared", None, None)
    assert LEDGER.read_text() == json.dumps(entries, indent=2) + "\n"            # the file's own form, unchanged


def test_449_item_1_the_gate_is_bar_text_character_for_character_at_the_architects_sha():
    _, e = _real()
    assert e["gate"] == v.BAR_TEXT
    assert hashlib.sha256(e["gate"].encode("utf-8")).hexdigest() == BAR_SHA
    assert v.bar_state(e) is None


def test_449_item_2_the_slots_as_ruled_and_the_two_recorded_figures_in_order():
    _, e = _real()
    assert e[v.SLOTS_KEY] == {
        "scope": "LEAGUE_REGULAR", "first_season": "score_under_prior", "visibility": "day",
        "cut": "2026-10-30T15:00:00Z", "availability_on": False,
        "v22_recorded": [{"competition": "PL", "season": "2024/25", "n": 340, "log_loss": 0.9956, "source": SOURCE},
                         {"competition": "PL", "season": "2025/26", "n": 340, "log_loss": 1.0465, "source": SOURCE}]}
    slots, why = v.slots_state(e)
    assert why is None and slots == e[v.SLOTS_KEY]


def test_449_item_3_frozen_constants_are_the_listed_keys_and_values_and_the_codes():
    _, e = _real()
    assert e["frozen_constants"] == CONSTANTS
    assert v.code_constants() == CONSTANTS                     # "stop and say so" if this ever reads otherwise
    assert v.constants_state(e) is None


def test_449_item_4_the_prose_fields_verbatim():
    _, e = _real()
    for k, text in PROSE.items():
        assert e[k] == text, k


def test_449_item_5_the_confirmation_window_and_plan():
    _, e = _real()
    assert e["confirmation_window"] == WINDOW
    assert e["confirmation_plan"] == PLAN
    assert reg.check_plan(e["confirmation_plan"]) == PLAN


def test_449_item_6c_the_three_states_read_the_real_entry_clean_and_the_gate_takes_it():
    """Item 6(c): constants_state, slots_state and bar_state each read the entry clean; the plan passes check_plan;
    the gate's own reader finds it declared and unrun. Nothing is run."""
    _, e = _real()
    assert v.constants_state(e) is None and v.slots_state(e)[1] is None and v.bar_state(e) is None
    assert v.declared_unrun() == e


# --------------------------------------------------------------------------- item 6(b): the reference-only bar --

def test_449_6b_check_plan_admits_a_null_bar_only_with_must_beat_reference_and_a_named_reference():
    assert reg.check_plan(dict(PLAN))["bar"] is None
    for bad in ({**PLAN, "must_beat_reference": False}, {**PLAN, "reference": None}, {**PLAN, "reference": "  "},
                {**PLAN, "reference": 3}, {k: x for k, x in PLAN.items() if k != "must_beat_reference"}):
        with pytest.raises(reg.RegistryError, match="null only with must_beat_reference true and a named reference"):
            reg.check_plan(bad)
    # a MISSING bar (or a misspelt key) is never read as a null one: refused as today, whatever the reference
    for absent in ({k: x for k, x in PLAN.items() if k != "bar"}, {**{k: x for k, x in PLAN.items() if k != "bar"},
                                                                    "bar_ll": 0.6931}):
        with pytest.raises(reg.RegistryError, match="the plan has no bar"):
            reg.check_plan(absent)


def test_449_6b_every_other_plan_keeps_todays_rule():
    ok = {"n_games": 60, "metric": "log_loss", "bar": 1.0, "must_beat_reference": True, "reference": "the close"}
    assert reg.check_plan(ok) == {**ok, "bar": 1.0}
    assert reg.check_plan({**ok, "bar": 1, "must_beat_reference": False})["bar"] == 1.0
    for bad in ("1.0", True, [1.0]):
        with pytest.raises(reg.RegistryError, match="must be a number"):
            reg.check_plan({**ok, "bar": bad})
    with pytest.raises(reg.RegistryError, match="must name the reference model"):
        reg.check_plan({**ok, "reference": None})
    with pytest.raises(reg.RegistryError, match="positive integer"):
        reg.check_plan({**ok, "n_games": 0})


def _confirming(tmp_path, plan) -> str:
    p = tmp_path / "experiments.json"
    p.write_text(json.dumps([{"id": "x-v1", "status": "confirming", "confirmation_plan": plan, "run": None,
                              "verdict": {"verdict": "PASS", "at": "2026-12-01T00:00:00Z"}}]))
    return str(p)


@pytest.mark.parametrize("metric, ref, want", [(0.98, 0.99, "CONFIRMED"), (0.99, 0.99, "NOT_CONFIRMED"),
                                               (1.00, 0.99, "NOT_CONFIRMED"), (5.0, 5.0000001, "CONFIRMED")])
def test_449_6b_record_confirmation_reads_metric_below_the_reference_alone_strict(tmp_path, metric, ref, want):
    """No TypeError (447's finding): the outcome is metric < reference alone; a tie fails; no fixed ceiling (a metric of
    5.0 below a reference of 5.0000001 is CONFIRMED)."""
    p = _confirming(tmp_path, dict(PLAN))
    e = reg.record_confirmation("x-v1", list(range(1, 61)), {"first_game_at": "2026-12-02T00:00:00Z",
                                                              "log_loss": metric, "reference_log_loss": ref},
                                "a ruling (tests only)", p, str(tmp_path / "ids"))
    assert e["confirmation"]["outcome"] == want
    assert e["status"] == ("production" if want == "CONFIRMED" else "closed")


def test_449_6b_record_confirmation_keeps_todays_rule_for_a_numeric_bar_and_refuses_a_bare_null(tmp_path):
    num = {"n_games": 60, "metric": "log_loss", "bar": 0.95, "must_beat_reference": True, "reference": "the close"}
    p = _confirming(tmp_path, num)
    e = reg.record_confirmation("x-v1", list(range(1, 61)), {"first_game_at": "2026-12-02T00:00:00Z",
                                                              "log_loss": 0.98, "reference_log_loss": 0.99},
                                "r", p, str(tmp_path / "ids"))
    assert e["confirmation"]["outcome"] == "NOT_CONFIRMED"                     # below the reference, above the bar
    bare = {"n_games": 60, "metric": "log_loss", "bar": None, "must_beat_reference": False, "reference": None}
    p = _confirming(tmp_path, bare)
    before = open(p).read()
    # ARCHITECT 2026-11-22, addendum 448 item 2: record_confirmation runs check_plan on the STORED plan, so a bare null
    # is refused there first, in check_plan's words (449 item 6(b)'s rule, unchanged), before anything is written
    with pytest.raises(reg.RegistryError, match="bar may be null only with must_beat_reference true"):
        reg.record_confirmation("x-v1", list(range(1, 61)), {"first_game_at": "2026-12-02T00:00:00Z",
                                                              "log_loss": 0.98}, "r", p, str(tmp_path / "ids2"))
    assert open(p).read() == before
