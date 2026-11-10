"""THE DECLARATION OF nfl_elo_v2 and nfl_elo_v1's RECORDED FAIL on the corrected stream (ARCHITECT 2026-11-04 08:20 ET,
addendum 245; the 11-04 console on #783, issuecomment-6631134603).

245 item 3, verbatim in part: "the fit written exactly as the tool printed it, a test pinning the entry against the
console's figures; NOTHING ELSE in the entry moves." 245 item 1, verbatim in part: "Code's PR writes it into
nfl-elo-v1's entry beside the VOID (the console quoted; the verdict stays VOID, the certification stays withdrawn)."

The tracked registry and roadmap are read, never written. The gate's entry readers are called on the real entry (pure
functions, no database); the preflight on a database and the one run are the architect's (245 item 4). The values the
other keys must keep are origin/main 488b4aa6's, digested here when this PR was written (no git ref is read)."""
import hashlib
import json
from pathlib import Path

import pytest

from src import roadmap as rm
from src.walters import nfl_backtest as nb
from src.walters import nfl_v2_gate as g
from src.walters import registry as reg

ROOT = Path(__file__).resolve().parent.parent
V1, V2 = "nfl-elo-v1", "nfl-elo-v2"
STAMP = "2026-11-04T14:03:09Z"           # the PR's stamp (245 item 3: "declared_at": "<the PR's stamp>")
WARMUP_FP = "d11ba700990b170ced875088144ad4885506d2cb11e0bd6177ff2a6d1a29c6f0"   # the console's, both tools
METHOD = ("the h minimizing the 2024 walk's mean log-loss re-run with home_advantage = h, grid 0.0..120.0 step 0.5, "
          "ties to the nearest 48.0")                    # 245 item 3's text (the ruling's wording, not the console's)

# 245 item 3, verbatim: the entry's calibration_term, with declared_at the PR's stamp
RULED = {"form": "home_advantage", "home_advantage": 33.0, "shrink": None,
         "fit": {"warmup_fingerprint": WARMUP_FP, "warmup_games": 285, "method": METHOD, "value": 33.0,
                 "log_loss_2024": 0.622175, "v1_log_loss_2024": 0.623122, "declared_at": STAMP,
                 "ruling": "addendum 245"}}

# The 11-04 console (#783 issuecomment-6631134603), section (4), nfl-backtest on the corrected stream, verbatim
CONSOLE_V1 = [
    "stream: 676 games (preseason excluded) — warm-up 285 (2024), scored 285 (2025)",
    "baseline home prob (2024 realized): 0.5474",
    "log-loss: model 0.6366 vs baseline 0.6913 (need <= 0.6813) -> PASS",
    "  band 40-50%: n=54 stated 0.451 realized 0.389 gap 6.2pp -> ok",
    "  band 50-60%: n=60 stated 0.549 realized 0.500 gap 4.9pp -> ok",
    "  band 60-70%: n=45 stated 0.644 realized 0.667 gap 2.2pp -> ok",
    "  band 70-80%: n=45 stated 0.744 realized 0.667 gap 7.7pp -> FAIL",
    "GATE VERDICT: FAIL — REGRESSION: the live model no longer clears its frozen gate; investigate before the next "
    "predict-nfl",
]
# The console's fit lines (section (5), nfl-v2-fit-warmup), the figures the entry's fit carries
CONSOLE_FIT_H = ("  FORM home advantage: h = 33.0 Elo points (v1 48.0) · method: the h minimizing the mean log-loss "
                 "of the 2024 walk re-run with home_advantage = h (price and update), grid 0.0..120.0 step 0.5, ties to "
                 "the nearest 48.0 · 2024 mean log-loss 0.622175 (v1 0.623122)")
CONSOLE_FP = (f"  warm-up fingerprint {WARMUP_FP} (the 2024 rows the fit read; the gate's --preflight compares it with "
              "the one the entry records)")


def _dg(o) -> str:
    return hashlib.sha256(json.dumps(o, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()


# origin/main 488b4aa6's nfl-elo-v2 keys other than calibration_term (245 item 3: "NOTHING ELSE in the entry moves")
V2_MAIN = {
    "lane": "6fc2891430974da174be1a61614746a80923f18cba590fd53ebd82d6c97f1ca0",
    "candidate": "6a8fc35bb1a14222bd785191aa516ad4f128f5f5b07071e89e9f80d73ca9a488",
    "declaration": "df4c592e79885fa2dd056265c9a2066f7a7049c975e5ef5ddfd16a2bd5d8c508",
    "training_cutoff": "3ff340e0dd6a0fd78a871b2571318b0aecff40ffabb44a8da8e11182cba3f135",
    "test_set": "5dbe6e2a75cf17bbced8169a15b2a004e219f2ef7651d4eec58f05f5a7e3799b",
    "gate": "6185398ed8983a3ff09ad00d1cac81f770904afb422d2df3dce0e232eb6f546b",
    "confirmation_window": "37d7f26a07049329bc101d148590e7af370bb40100c8291923490aaa7cfe8761",
    "confirmation_plan_note": "a4d2ecfffbee17a30156419d30715095f73510f386aeabb735905dc1e20138ce",
    "declared_at_note": "ea3f8a65ee538caba9b48a0e3a2a9a41d8a645c717b4b6cd96b3c4a40c63da74",
    "stream": "55b26d6882f903eeba5db54ccb07f9e05d95d377d55934fb101f167c5fffbab2",
    "run_date": "a63164f4de5127568c133d21310fc154de6b1b4ff9f1f30e8cac5fa0dc040045",
    "prior_reads_note": "1cd6996c84e21d0b1d04227f0440c0c6fc15eb938a052a1b59b50b8040471a5a",
    "ratified": "35978773834441ccc34ee6dbbc2766b7da9c6c3dc0d44e510b8f2c434c481b08",
}
V2_KEYS = ["id", "sport", "lane", "candidate", "declaration", "training_cutoff", "test_set", "gate",
           "confirmation_window", "confirmation_plan", "confirmation_plan_note", "declared_at", "status", "run",
           "verdict", "declared_at_note", "constants", "calibration_term", "stream", "run_date", "prior_reads_note",
           "ratified"]
# calibration_term's documentary keys kept from origin/main (the forms' text and bounds, the rule 215/219 quote)
FORMS_MAIN = "07ac06590c5dc2cba38db11d758756149d7d11aa03e328fffcb2dd511b0c64b6"
RULE_MAIN = "b848927f5f56e67e1e3f2235e5eb58237e6b62572a5cbdf0c76210b35d4b5f2f"
# origin/main 488b4aa6's nfl-elo-v1 entry whole (every key it had), and some of its keys one by one
V1_MAIN = "7f79adce0e28e934157b5c6d3f11643bf797ab1d4dd92193146f0a7b026ef4bf"
V1_MAIN_KEYS = {
    "verdict": "3c963e72f66a1a1c0588b365a2fc0717e034ae353ea05b44dedc2c5ba6129ad4",
    "regression": "1d4ef0c901f1add8e9f980d327ad1f8edb7d29f0545c51e98858b92e26f509d3",
    "certification": "d1b843a141bf3fb6dd10cc21393bc58d737519158cfa4cc863202503d117ede1",
    "history": "9680913163f5a6b76d175603e6953f269ac7d89514a98a5331e718e139406d18",
}


def _e(eid):
    e = reg.get(eid)
    assert e is not None, eid
    return e


# ===================================================================== nfl-elo-v2: the term, as 245 item 3 rules --

def test_the_v2_term_is_the_ruled_object_against_the_consoles_figures():
    t = _e(V2)["calibration_term"]
    assert {k: t[k] for k in RULED} == RULED
    # == cannot tell 33 from 33.0 or 285 from 285.0 (and the gate floats the value); the ruled types are pinned exactly
    assert json.dumps({k: t[k] for k in RULED}, sort_keys=True) == json.dumps(RULED, sort_keys=True)
    assert type(t["home_advantage"]) is float and type(t["fit"]["value"]) is float
    assert type(t["fit"]["log_loss_2024"]) is float and type(t["fit"]["v1_log_loss_2024"]) is float
    assert type(t["fit"]["warmup_games"]) is int
    assert t["shrink"] is None                                           # 245 item 2(a): NOT DECLARABLE
    assert (t["form"], t["home_advantage"], t["fit"]["value"]) == ("home_advantage", 33.0, 33.0)
    f = t["fit"]
    assert (f["warmup_games"], f["log_loss_2024"], f["v1_log_loss_2024"]) == (285, 0.622175, 0.623122)
    assert f["warmup_fingerprint"] == WARMUP_FP and f["declared_at"] == STAMP and f["ruling"] == "addendum 245"
    # the console printed each figure the fit carries
    assert "h = 33.0 Elo points" in CONSOLE_FIT_H and "2024 mean log-loss 0.622175 (v1 0.623122)" in CONSOLE_FIT_H
    assert WARMUP_FP in CONSOLE_FP


def test_the_method_is_the_rulings_text_which_words_the_consoles_line_differently():
    """245 item 3 writes the method in its own words; the console's line words the same grid and tie rule otherwise
    (and names "(price and update)"). The entry carries the ruling's text."""
    m = _e(V2)["calibration_term"]["fit"]["method"]
    assert m == METHOD
    assert m not in CONSOLE_FIT_H and "(price and update)" not in m
    assert "grid 0.0..120.0 step 0.5, ties to the nearest 48.0" in m
    assert "grid 0.0..120.0 step 0.5, ties to the nearest 48.0" in CONSOLE_FIT_H


def test_the_v2_terms_kept_keys_are_mains():
    t = _e(V2)["calibration_term"]
    assert list(t) == ["form", "shrink", "home_advantage", "fit", "forms", "rule"]
    assert (_dg(t["forms"]), _dg(t["rule"])) == (FORMS_MAIN, RULE_MAIN)


def test_nothing_else_in_the_v2_entry_moves():
    e = _e(V2)
    assert list(e) == V2_KEYS
    # ARCHITECT 2026-11-06 08:55 ET, addendum 265: the one run (the laptop's record, b2d4cd97) and the FAIL verdict are
    # recorded since (registry.record_run / record_verdict write status, run and verdict); every other key is 245's
    assert (e["id"], e["sport"], e["status"], e["run"]["n_scored"], e["verdict"]["verdict"], e["confirmation_plan"]) \
        == (V2, "nfl", "closed", 285, "FAIL", None)
    assert e["declared_at"] == "2026-11-02T15:35:00Z"                    # 215's stamp; the term carries 245's
    assert e["constants"] == {"k_factor": 20.0, "home_advantage": 48.0, "season_regression": 0.25, "mov_base": 2.2,
                              "default_rating": 1500.0}                  # v1's, unchanged (the term replaces h only)
    assert all(type(v) is float for v in e["constants"].values())        # 20.0 not 20 (== alone cannot tell)
    assert {k: _dg(e[k]) for k in V2_MAIN} == V2_MAIN


# ============================================================== nfl-elo-v2: the gate's reader accepts the entry --

def test_the_gate_reads_the_declared_term():
    e = _e(V2)
    assert g.term_state(e) == ("home_advantage", 33.0, None)            # declared, the form recognised, in bounds
    assert g.declared_term(e) == ("home_advantage", 33.0)
    assert g.bound_term(e) == ("home_advantage", 33.0)                  # the term the stream fingerprint binds
    assert 0 <= 33.0 < nb.NFLEloConfig().home_advantage == 48.0
    assert g.describe(*g.declared_term(e)) == ("home advantage 33.0 Elo points (v1: 48.0), the whole walk (price "
                                               "and update)")


def test_the_gate_reads_the_fit_binding_and_the_frozen_constants():
    e = _e(V2)
    assert g.fit_binding(e) == WARMUP_FP                                 # what --preflight and the run compare
    assert g._fit_state(g.fit_binding(e), WARMUP_FP) == "SAME: the fit is bound to these 2024 rows"
    assert g.constants_state(e) is None and g.declared_constants(e) == e["constants"]
    cfg, price = g.candidate(*g.declared_term(e))
    base = nb.NFLEloConfig()
    assert price is None and cfg.home_advantage == 33.0
    assert (cfg.k_factor, cfg.season_regression, cfg.mov_base, cfg.default_rating) == \
           (base.k_factor, base.season_regression, base.mov_base, base.default_rating)


def test_the_pure_preflight_reads_the_term_and_the_fit_and_the_fingerprint_binds_the_term():
    """preflight() over an empty stream (no database): the entry's term and fit as the preflight reads them; the
    stream fingerprint with the declared term is not the undeclared one's (219 item 4: the word names the term)."""
    e = _e(V2)
    pf = g.preflight([], e)
    assert (pf["form"], pf["value"], pf["term_why"], pf["constants_why"]) == ("home_advantage", 33.0, None, None)
    assert pf["fit_warmup_fingerprint"] == WARMUP_FP
    assert pf["fingerprint"] == g.stream_fingerprint([], [], ("home_advantage", 33.0))[0]
    assert pf["fingerprint"] != g.stream_fingerprint([], [], None)[0]


def test_the_run_reads_the_entry_as_declared_and_unrun():
    """declared_unrun() reads the real ledger only (status, run, the reservation's absence): 245 kept `declared` until
    the one run; since 2026-11-06 (addendum 265) the real entry is run and closed and the reservation is the record that
    the run was spent, so a second run is refused. The term 245 declared is the one the run walked."""
    assert g.reservation_path().endswith("nfl-elo-v2.started.json")
    assert Path(g.reservation_path()).exists()
    with pytest.raises(g.GateRefused, match=r"must be declared and unrun in the registry \(status closed\)"):
        g.declared_unrun()
    assert g.declared_term(_e(V2)) == ("home_advantage", 33.0)


# ================================================================ nfl-elo-v1: the RECORDED FAIL beside the VOID --

def test_the_v1_verdict_stays_void_and_the_certification_withdrawn():
    e = _e(V1)
    assert e["verdict"]["verdict"] == "VOID"
    assert e["certification"] == "UNCERTIFIED — shadow, confirmation window (addendum 214 item 3)"
    assert reg.uncertified(e) and reg.production_allowed(V1)[0] is False
    # addendum 299 item 3(a): the one key `family` (the closing family the lookup is keyed by) joined after 488b4aa6
    assert e["family"] == "NFL"
    rest = {k: v for k, v in e.items() if k not in ("recorded_fail_corrected_stream", "family")}
    assert _dg(rest) == V1_MAIN                                          # every other key is main's, unchanged
    assert {k: _dg(e[k]) for k in V1_MAIN_KEYS} == V1_MAIN_KEYS
    keys = list(e)
    assert keys[keys.index("verdict") + 1] == "recorded_fail_corrected_stream"   # beside the VOID


def test_the_v1_recorded_fail_quotes_the_console():
    r = _e(V1)["recorded_fail_corrected_stream"]
    assert (r["on"], r["verdict"]) == ("2026-11-04", "FAIL")
    assert "the laptop, main 26943179" in r["where"]
    assert r["receipt"].startswith("#783 issuecomment-6631134603")
    assert r["console"] == CONSOLE_V1
    assert r["console"][-1].startswith("GATE VERDICT: FAIL")
    bands = [x for x in r["console"] if x.lstrip().startswith("band ")]
    assert [(b.split()[1], b.split()[2], b.split("gap ")[1].split("pp")[0], b.split("-> ")[1]) for b in bands] == [
        ("40-50%:", "n=54", "6.2", "ok"), ("50-60%:", "n=60", "4.9", "ok"), ("60-70%:", "n=45", "2.2", "ok"),
        ("70-80%:", "n=45", "7.7", "FAIL")]
    assert "stated 0.744 realized 0.667" in bands[3]
    assert r["ruling"].startswith("ARCHITECT 2026-11-04 08:20 ET, addendum 245 item 1, verbatim: \"THE 11-04 STEP'S "
                                  "RECORD (the laptop, main 26943179)")
    assert "the verdict stays VOID, the certification stays withdrawn" in r["ruling"]
    assert "the verdict stays VOID" in r["note"] and "the certification stays withdrawn" in r["note"]


def test_the_ledger_stays_one_json_file_in_its_format():
    raw = (ROOT / "docs" / "registry" / "experiments.json").read_text()
    assert raw == json.dumps(json.loads(raw), indent=2) + "\n"
    # addendum 265 item 4: the reservation kept, as the laptop wrote it, beside the one run's record
    started = json.loads((ROOT / "docs" / "registry" / f"{V2}.started.json").read_text())
    assert (started["id"], started["started_at"]) == (V2, _e(V2)["run"]["run_at"])


# ========================================================================= the roadmap: done-marks, never moves --

def test_the_lane_nfl_v2s_steps_11_04_and_11_05_are_done_and_the_run_step_stands():
    doc = rm.load()
    assert rm.validate(doc) == []
    (ln,) = [x for x in doc["lanes"] if x["lane"] == "nfl-v2"]
    # no date the first four steps carry moves; the three on-PASS steps are cleared by addendum 265 item 4 (the FAIL)
    assert [(s["owner"], s["due"]) for s in ln["steps"]] == [
        ("code", "2026-11-03"), ("operator", "2026-11-04"), ("architect", "2026-11-05"), ("operator", "2026-11-06")]
    assert ln["steps"][1]["done"] == {"date": "2026-11-04", "receipt": "the 11-04 console #783 "
                                      "issuecomment-6631134603 (the laptop, main 26943179; its record: addendum 245 "
                                      "item 1)"}
    assert ln["steps"][2]["done"] == {"date": "2026-11-04", "receipt": "addendum 245 (ARCHITECT 2026-11-04 08:20 "
                                      "ET); the 11-04 console #783 issuecomment-6631134603"}
    assert ln["steps"][3]["what"] == "the ONE run on my word, my block, the verdict the same day"
    # addendum 265 item 4: the run step done 2026-11-06 with the console as its receipt (a done-mark, no moved line);
    # earliest_live 2026-11-26 cleared by its one moved line (now null); the lane closed. Addendum 245 advanced the lane
    # to "declared" with its declaration (Codex on #822); the FAIL ends that candidate's path
    assert ln["steps"][3]["done"]["date"] == "2026-11-06" and "the console on #783" in ln["steps"][3]["done"]["receipt"]
    assert [(m["which"], m["was"], m["now"]) for m in ln["moved"]] == [("earliest_live", "2026-11-26", None)]
    assert (ln["earliest_live"], ln["state"]) == (None, "closed")
