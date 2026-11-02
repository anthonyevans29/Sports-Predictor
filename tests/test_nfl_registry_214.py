"""THE RECORDS of addendum 214 item 4(b) and (d), as amended by addendum 215 item 1 (ARCHITECT 2026-11-02).

214 item 4(b), verbatim: "THE REGISTRY: nfl_elo_v1's entry gets the regression line verbatim (stream 676, the 70–80% band
7.7pp, #775 issuecomment-6580087145) and the state "UNCERTIFIED — shadow, confirmation window (addendum 214 item 3)",
with the window's definition and bar written in."
214 item 4(d), verbatim in part: "docs/roadmap.json: a new lane "nfl-confirm" — 11-03 code: the policy PR; 11-04
operator: the tag carrying #775 and the policy, deployed (my blocks); [...] The nfl-qb lane's steps stand."
215 item 1, verbatim in part: "Code: 214 item 4(c)'s script and 4(d)'s lane carry this window and date instead of the
100-game one; nothing else in 214 changes." And: "on this path alone nfl_elo_v1 does not come back this season."
217 item 5, verbatim in part: "the records PR carries the entry (214 item 4(b)); the tile reads the registry."

The tracked registry and roadmap are read, never written; the refusals run on a tmp copy of the registry."""
import json
from pathlib import Path

import pytest

from src import roadmap as rm
from src.walters import nfl_predict
from src.walters import registry as reg

ROOT = Path(__file__).resolve().parent.parent
EID = "nfl-elo-v1"
STATE = "UNCERTIFIED — shadow, confirmation window (addendum 214 item 3)"
REGRESSION = "stream 676, the 70–80% band 7.7pp, #775 issuecomment-6580087145"


def _entry():
    e = reg.get(EID)
    assert e is not None, f"{EID} must be in docs/registry/experiments.json (addendum 214 item 4(b))"
    return e


def test_the_entry_carries_the_regression_line_and_the_state_verbatim():
    e = _entry()
    assert all(e.get(k) for k in reg.DECLARE_FIELDS)
    assert e["certification"] == STATE and reg.uncertified(e)
    assert e["regression"]["line"] == REGRESSION
    assert e["model_version"] == nfl_predict.MODEL_VERSION == "nfl_elo_v1"      # the id predict-nfl writes
    assert e["competitions"] == ["NFL"] and e["sport"] == "nfl"


def test_the_entry_carries_the_full_before_and_after_figures_of_214_item_1():
    r = _entry()["regression"]
    assert r["before"]["verdict"] == "PASS" and (r["before"]["log_loss"], r["before"]["baseline_log_loss"]) == \
        (0.6361, 0.6911) and r["before"]["need"] == "<= 0.6811" and "worst 6.6pp" in r["before"]["bands"]
    a = r["after"]
    assert a["verdict"] == "FAIL" and (a["log_loss"], a["baseline_log_loss"], a["need"], a["log_loss_criterion"]) == \
        (0.6366, 0.6913, "<= 0.6813", "PASS")
    assert a["failing_band"] == {"band": "70–80%", "n": 45, "stated": 0.744, "realized": 0.667, "gap_pp": 7.7,
                                 "bar_pp": 7.0}
    assert "the stream 676" in a["warm_up"] and "285 games" in a["warm_up"] and "334 FINISHED, 0 SCHEDULED" in \
        a["warm_up"]
    assert r["ruling"].startswith("ARCHITECT 2026-11-02 10:15 ET, addendum 214 item 1, verbatim: \"THE RECEIPT (#775 "
                                  "issuecomment-6580087145")


def test_the_window_and_bar_are_215_item_1s_never_the_100_game_window():
    e = _entry()
    w = e["confirmation_window"]
    assert w.startswith("ARCHITECT 2026-11-02 10:35 ET, addendum 215 item 1")
    for part in ("EVERY NFL regular-season and postseason game with a kickoff strictly after 2026-11-02 15:15Z that "
                 "reaches FINISHED with a stored close, through the Super Bowl (2027-02-08)",
                 "the model's mean log-loss <= the schedule-naive baseline's - 0.010",
                 "every 10pp band with n >= 30 within 7pp; a band that never reaches 30 is reported, not scored",
                 "ONE read, the architect's, after the Super Bowl (2027-02-08)",
                 "on this path alone nfl_elo_v1 does not come back in 2026"):
        assert part in w, part
    assert "first 100" not in w
    assert e["window_amended"].startswith("ARCHITECT 2026-11-02 10:35 ET, addendum 215 item 1, verbatim: \"THE "
                                          "AMENDMENT.")


def test_the_history_and_the_void_verdict():
    e = _entry()
    assert [h["on"] for h in e["history"]] == ["2026-09-09", "2026-09-22", "2026-11-02"]
    assert "LIVE from Week 3" in e["history"][1]["what"]
    assert e["verdict"]["verdict"] == "VOID" and e["verdict"]["was"]["verdict"] == "PASS"
    assert e["verdict"]["ruling"].startswith("ARCHITECT 2026-11-02 10:15 ET, addendum 214 item 2, verbatim: \"THE "
                                             "RULING.")
    assert "the 2026-09-09 run predates the registry" in e["run"]["note"]
    assert e["declared_at"] == "2026-11-02T15:15:00Z"            # 214's stamp: the confirmation declared, in ledger order


def test_production_is_not_allowed_and_no_confirmation_can_be_recorded(tmp_path):
    """An UNCERTIFIED certification refuses production whatever else the entry holds; with no executable plan the
    registry's confirmation write refuses (the read is 214 item 4(c)'s script's, the verdict the architect's)."""
    assert reg.production_allowed(EID) == (False, f"certification {STATE}")
    p = tmp_path / "experiments.json"
    p.write_text((ROOT / "docs" / "registry" / "experiments.json").read_text())
    passed = {**_entry(), "verdict": {"verdict": "PASS", "at": "2026-11-02T15:15:00Z"},
              "confirmation": {"outcome": "CONFIRMED", "n_scored": 1, "ids_sha256": "x", "result": {"log_loss": 0.6}}}
    entries = [x if x["id"] != EID else passed for x in reg.load(str(p))]
    reg.save(entries, str(p))
    assert reg.production_allowed(EID, path=str(p))[0] is False                   # still UNCERTIFIED: refused
    p.write_text((ROOT / "docs" / "registry" / "experiments.json").read_text())
    with pytest.raises(reg.RegistryError, match="no executable confirmation_plan"):
        reg.record_confirmation(EID, [1], {"first_game_at": "2026-11-03T00:00:00Z", "log_loss": 0.6}, "r",
                                path=str(p), ids_dir=str(tmp_path / "ids"))
    with pytest.raises(reg.RegistryError, match="no executable confirmation_plan"):
        reg.freeze_confirmation_cohort(EID, [1], {}, path=str(p), ids_dir=str(tmp_path / "ids"), no_fetch=True)
    assert not (tmp_path / "ids").exists()


def test_uncertified_live_names_the_entry_for_the_model_only():
    entries = reg.load()
    assert reg.uncertified_live("nfl_elo_v1", entries)["id"] == EID
    assert reg.uncertified_live("v22", entries) is None and reg.uncertified_live("", entries) is None
    assert reg.uncertified_live(None, entries) is None
    assert reg.uncertified({"certification": "certified"}) is False and reg.uncertified(None) is False


def test_the_ledger_stays_one_json_file_in_its_format():
    raw = (ROOT / "docs" / "registry" / "experiments.json").read_text()
    assert raw == json.dumps(json.loads(raw), indent=2) + "\n"
    ids = [x["id"] for x in reg.load()]
    assert ids.count(EID) == 1 and ids.index(EID) == ids.index("pl-availability-v1") + 1   # appended; later ones follow


# ------------------------------------------------------------------------------------------------- the lane --

def test_the_nfl_confirm_lane():
    doc = rm.load()
    assert rm.validate(doc) == []
    (ln,) = [x for x in doc["lanes"] if x["lane"] == "nfl-confirm"]
    assert (ln["issue"], ln["registry_id"], ln["state"], ln["competitions"], ln["earliest_live"], ln["moved"]) == \
           (780, EID, "confirming", ["NFL"], None, [])
    assert [(s["owner"], s["due"]) for s in ln["steps"]] == [("code", "2026-11-03"), ("operator", "2026-11-04"),
                                                             ("calendar", "2027-02-08"), ("architect", "2027-02-09")]
    assert ln["steps"][0]["done"] == {"date": "2026-11-02", "receipt": "#778 merged at 6b3bd076"}
    assert all(s["done"] is None for s in ln["steps"][1:])
    assert ln["steps"][1]["what"] == "the tag carrying #775 and the policy, deployed (the architect's blocks)"
    assert "the Super Bowl, the window's last game" in ln["steps"][2]["what"]
    assert "100" not in json.dumps(ln["steps"])                                   # 215 item 1: no 100-game step
    assert "does not come back this season" in ln["live_needs"]
    names = [x["lane"] for x in doc["lanes"]]
    assert names.index("nfl-confirm") > names.index("nfl-qb")      # its own lane; the harness PR's nfl-v2 may join it
    assert reg.get(ln["registry_id"])["status"] == "confirming"                   # the lane and the registry agree


def test_the_nfl_qb_lanes_steps_stand():
    """214 item 4(d): "The nfl-qb lane's steps stand.\""""
    ln = next(x for x in rm.load()["lanes"] if x["lane"] == "nfl-qb")
    assert [s["due"] for s in ln["steps"][:3]] == ["2026-10-21", "2026-10-23", "2026-11-02"] and ln["moved"] == []
