"""THE LEAGUES' CONFIRMATION POLICY (ARCHITECT 2026-11-22, addendum 447 item 3 C1-C3 and item 4 PR 2; addendum 448
items 1(a), 1(b) and 2(a) as addendum 455 item 4 restates them; check_plan's part is #1080's, 449 item 6(b)).

On a tmp registry and a throwaway SQLite (tests/conftest.py); the real docs/registry/experiments.json is read, never
written. Pins:
  C2   while an entry is CONFIRMING its fence stays, cut at the opening's kickoff INCLUSIVE, one site (fence_cutoff);
       it lifts after a REJECT and once the confirmation is recorded, either way (448 item 1(b)); a confirming entry
       whose run record holds no opening keeps the window's own fence (law 4);
  C1(b) record_confirmation checks the first game against the opening's kickoff (not earlier), for an entry whose run
       record carries the opening; an entry without one keeps today's rule (after verdict.at);
  C3(a) the five leagues entries carry the one plan, taken by check_plan, and record_confirmation runs check_plan on
       the stored plan (448 item 2);
  C3(b) a leagues entry at status production changes no export and no Desk call;
  448 1(d) the opening's kickoff and the first game are compared as strings, each written to the second with the Z;
  448 2(a) each note keeps its words and gains the one sentence before the closing 223 item 2(d) sentence;
  448 2(b) the ruled plan is the one stored, and plan_refusal refuses any other stored plan."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.walters import leagues_window as lw
from src.walters import registry as reg
from src.walters import soccer_expansion as sx
from tests.test_record_vs_close import iso_db  # noqa: F401  (a fixture: a throwaway SQLite, cwd = tmp_path)

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
CONF = {"production": {"outcome": "CONFIRMED"}, "closed": {"outcome": "NOT_CONFIRMED"}}


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
    assert "its confirmation is not recorded" in why and "14:59:59" not in why   # its own wording, not the cut
    assert sx.guards_backtest("SA", SEASON) == why                      # every guard reads the one site
    assert sx.guards_backtest("SA", SEASON, through=cut) is None


@pytest.mark.parametrize("status, verdict", [
    ("closed", {"verdict": "REJECT", "ruling": "r", "at": "2026-12-07T12:00:00Z"}),     # after a REJECT
    ("production", PASS),                                                               # CONFIRMED
    ("closed", PASS),                                                                   # NOT_CONFIRMED
])
def test_c2_the_fence_lifts_after_a_reject_and_once_the_confirmation_is_recorded_either_way(ledger, status, verdict):
    ledger(_entry(status=status, verdict=verdict, confirmation=CONF.get(status) if verdict is PASS else None))
    assert lw.fence_cutoff("SA", SEASON) is None and lw.fence_refusal("SA", SEASON) is None


@pytest.mark.parametrize("status, conf", [("production", None), ("closed", None), ("declared", None),
                                          ("production", {"outcome": "SOMETHING"}), ("production", "CONFIRMED")])
def test_c2_a_pass_lifts_only_on_its_recorded_confirmation_never_on_a_status(ledger, status, conf):
    """Codex on #1086: the lift is read from the records (448 item 1(b): "AFTER THE CONFIRMATION IS RECORDED"),
    never inferred from a status; a PASS with no confirmation record, whatever its status, is still confirming."""
    ledger(_entry(status=status, verdict=PASS, confirmation=conf))
    assert lw.fence_cutoff("SA", SEASON) == OPEN_KO - timedelta(microseconds=1)
    assert "AT OR AFTER the opening" in lw.fence_refusal("SA", SEASON, through=OPEN_KO)


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
                                       ("2026-12-06T15:00:00", False), ("2026-12-06T15:00:00+00:00", False),
                                       ("2026-12-06T15:00:00.000001Z", False), ("2026-12-06T16:00:00Z", True)])
def test_c1b_the_first_game_is_checked_against_the_openings_kickoff_not_the_verdict(tmp_path, first, ok):
    """A game played before the verdict's stamp may enter (447 C1(c)): the opening is the bound, not verdict.at."""
    p = _confirming_file(tmp_path)
    if ok:
        e = reg.record_confirmation("x-v1", list(range(1, 61)), _res(first), "r", p, str(tmp_path / "ids"))
        assert e["confirmation"]["outcome"] == "CONFIRMED"
    else:
        with pytest.raises(reg.RegistryError, match="not start earlier than the opening"):
            reg.record_confirmation("x-v1", list(range(1, 61)), _res(first), "r", p, str(tmp_path / "ids"))


def test_448_1d_the_opening_and_the_first_game_are_compared_as_strings_written_to_the_second_with_the_z(tmp_path):
    """448 item 1(d): the opening's kickoff is written as the callers write theirs (to the second, with the Z), and the
    backstop compares the two strings. The callers' form is the registry's own stamp and strftime's; a bare instant
    sorts before its Z form as a string (the receipt on #322), so any other form refuses rather than being parsed."""
    assert reg.INSTANT_Z.fullmatch(reg._now())
    assert reg.INSTANT_Z.fullmatch(datetime(2026, 12, 6, 15, 0).strftime("%Y-%m-%dT%H:%M:%SZ")) and \
        OPENING["kickoff"] == "2026-12-06T15:00:00Z"
    assert not ("2026-12-06T15:00:00" >= "2026-12-06T15:00:00Z")      # why the form is held, not parsed
    assert "2026-12-06T15:00:00Z" >= "2026-12-06T15:00:00Z" and "2026-12-06T15:00:01Z" > "2026-12-06T15:00:00Z"
    for bad in ("2026-12-06T15:00:00", "2026-12-06 15:00:00Z", "2026-12-06T15:00:00+00:00", 1765033200):
        p = _confirming_file(tmp_path, opening={"kickoff": bad, "match_id": 16267})
        with pytest.raises(reg.RegistryError, match="not start earlier than the opening"):
            reg.record_confirmation("x-v1", list(range(1, 61)), _res("2026-12-08T00:00:00Z"), "r", p,
                                    str(tmp_path / "ids"))


def test_448_2_record_confirmation_runs_check_plan_on_the_stored_plan(tmp_path):
    """448 item 2: check_plan runs on the stored plan inside record_confirmation; a stored plan it refuses (a missing
    bar; a null bar without a named reference) refuses the confirmation before anything is written."""
    for broken in ({k: v for k, v in PLAN.items() if k != "bar"}, {**PLAN, "reference": ""},
                   {**PLAN, "must_beat_reference": False}, {**PLAN, "n_games": 0}):
        p = _confirming_file(tmp_path)
        data = json.loads(open(p).read())
        data[0]["confirmation_plan"] = broken
        open(p, "w").write(json.dumps(data))
        before = open(p).read()
        with pytest.raises(reg.RegistryError, match="confirmation_plan"):
            reg.record_confirmation("x-v1", list(range(1, 61)), _res("2026-12-08T00:00:00Z"), "r", p,
                                    str(tmp_path / "ids"))
        assert open(p).read() == before


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


def test_c3b_a_leagues_entry_at_production_changes_no_export_and_no_desk_call(ledger, monkeypatch):
    """447 C3(b): what decides a leagues call is code, never a status. At production: the shadow binding is the one it
    was at declared; the Desk's shadow set and predict's refusal stand; the fence is lifted (448 item 1(b))."""
    import cli
    from src.walters import desk_policy as dp
    ledger(_entry())
    before = sx.shadow_binding("SA")
    ledger(_entry(status="production", verdict=PASS, confirmation=CONF["production"]))
    after = sx.shadow_binding("SA")
    assert {k: after[k] for k in ("state", "candidate", "declared_at", "frozen_constants")} == {
        k: before[k] for k in ("state", "candidate", "declared_at", "frozen_constants")}
    assert "SA" in dp.SHADOW_VENUE_COMPS
    for cmd in ("predict", "export-predictions"):
        with pytest.raises(SystemExit) as ex:
            cli._refuse_shadow_league("SA", cmd)
        assert ex.value.code == 2
    monkeypatch.setitem(dp.HOST_FENCE_RULE, "on", False)               # the Desk's two shadow-league paths, as on a
    r = {"sport": "SA", "comp": "SA", "mkt": None, "utc": None, "fairAll": {}, "books": 0, "home": "h",  # laptop
         "away": "a", "marketOnly": True}
    call = dp._desk_call(r, 0)
    assert (call["call"], call["units"], call["passKind"]) == ("PASS", 0, dp.SHADOW_LEAGUE_KIND)
    ven = dp.venue_edge(r, 0)
    assert ven["eligible"] is False and ven["reason"].startswith("shadow league (SA, soccer-expansion-v1)")
    assert lw.fence_cutoff("SA", SEASON) is None


# ------------------------------------------------------------------------------ 448 item 2(a)-(b): the note, the refusal --

NOTE_448 = ("Superseded in two places (ARCHITECT 2026-11-22, addendum 447 item 3, C2 and C3(a)): this entry now holds its "
            "executable plan, check_plan admitting a reference-only bar, so this note's first sentence no longer "
            "describes it; and after a PASS the fence does not lift but stands from the 60th member's kickoff until the "
            "confirmation is recorded.")
D2D_SENTENCE = ("A PASS enters the confirmation of 60 more qualifying games at the same bar of addendum 158 item 2(a) "
                "(ARCHITECT 2026-11-02 18:05 ET, addendum 223 item 2(d), verbatim: \"220 item 3's PASS clause reads as "
                "\"the WINDOW step of the live needs is met\": the confirmation follows, and the Desk's calls are ruled "
                "in by their own addendum only after it.\").")
FIRST_SENTENCE = ("registry.check_plan holds one metric against a fixed number; this bar is the close's log-loss on the "
                  "same 60 games, so no executable plan is written and record_confirmation refuses this entry.")


@pytest.mark.parametrize("eid", sorted(lw.DECLARATION_IDS.values()))
def test_448_2a_each_note_keeps_its_words_and_gains_the_one_sentence_before_the_closing_223_2d_sentence(eid):
    """448 item 2(a): "Its words stay ... ONE SENTENCE is added, the same in all five, before the closing 223 item 2(d)
    sentence" (verbatim)."""
    note = {e["id"]: e for e in reg.load(str(ROOT / "docs" / "registry" / "experiments.json"))}[eid][
        "confirmation_plan_note"]
    assert note.startswith(FIRST_SENTENCE + " ") and note.count(NOTE_448) == 1
    assert note.endswith(" " + NOTE_448 + " " + D2D_SENTENCE)
    without = note.replace(" " + NOTE_448, "", 1)          # the words of 11-02, unchanged around it
    assert NOTE_448 not in without and without.endswith(" " + D2D_SENTENCE)


def test_448_2b_the_ruled_plan_is_the_one_stored_and_any_other_stored_plan_is_refused():
    real = {e["id"]: e for e in reg.load(str(ROOT / "docs" / "registry" / "experiments.json"))}
    assert lw.RULED_PLAN == PLAN
    for eid in lw.DECLARATION_IDS.values():
        assert lw.plan_refusal(real[eid]) is None
    e = dict(real["leagues-sa-v1"])
    for other in (None, {**PLAN, "bar": 0.0}, {**PLAN, "n_games": 60.0}, {**PLAN, "must_beat_reference": 1},
                  {**PLAN, "reference": "the close"}, {k: v for k, v in PLAN.items() if k != "bar"},
                  {**PLAN, "extra": 1}):
        e["confirmation_plan"] = other
        why = lw.plan_refusal(e)
        assert why and why.startswith("leagues-sa-v1: the stored confirmation_plan is ") and "448 item 2(b)" in why


@pytest.mark.parametrize("status, text", [
    ("confirming", "the confirmation is open: the fence holds from the opening, inclusive (448 item 1(a))"),
    ("production", "the fence is lifted"), ("closed", "the fence is lifted")])
def test_448_1c_the_print_names_the_fence_as_the_rule_has_it(iso_db, ledger, status, text):
    """448 item 1(c): the print is amended to the rule: while confirming the fence holds; recorded, it is lifted."""
    from src.db.database import session_scope
    from src.db.schema import Competition, Sport
    with session_scope() as s:
        s.add(Competition(sport=Sport.SOCCER, code="SA", name="SA", area="X", type="LEAGUE"))
    ledger(_entry(status=status, verdict=PASS, confirmation=CONF.get(status)))
    now = datetime(2026, 12, 8, 12, 0)
    out = lw.lines(lw.read(("SA",), now=now), now)
    line = next(x for x in out if "the verdict is recorded in leagues-sa-v1" in x)
    assert line.endswith(": " + text)


# ------------------------------------------------------------------- the review's cases (adversarial, pre-push) --

def test_c2_a_run_recorded_with_its_opening_but_no_verdict_keeps_the_declared_at_fence(ledger):
    """The one read writes the opening into the run record before any verdict: until the verdict is recorded the fence
    is the window's own, from declared_at, never the opening's (which would release the 60 members early)."""
    ledger(_entry(status="declared", run={"result": {"confirmation_opens_after": OPENING}}, verdict=None))
    assert lw.opening(lw.declaration("SA")) == (OPEN_KO, 4242)
    assert lw.fence_cutoff("SA", SEASON) == lw.parse_instant(AT)
    assert lw.fenced(lw.fence_cutoff("SA", SEASON), G(lw.parse_instant(AT) + timedelta(hours=1)))
    why = lw.fence_refusal("SA", SEASON, through=OPEN_KO - timedelta(seconds=1))
    assert why and "its verdict is not recorded" in why


@pytest.mark.parametrize("bad", [None, {"kickoff": "soon", "match_id": 1}, {"kickoff": "2026-12-06T15:00:00",
                                 "match_id": 1}, {"kickoff": "2026-12-06T15:00:00Z", "match_id": "4242"},
                                 {"kickoff": "2026-12-06T15:00:00Z", "match_id": None},
                                 {"kickoff": "2026-12-06T15:00:00Z", "match_id": True}])
def test_c2_law4_a_confirming_entry_with_no_readable_opening_says_so_in_the_refusal_and_the_print(iso_db, ledger, bad):
    from src.db.database import session_scope
    from src.db.schema import Competition, Sport
    with session_scope() as s:
        s.add(Competition(sport=Sport.SOCCER, code="SA", name="SA", area="X", type="LEAGUE"))
    ledger(_entry(status="confirming", verdict=PASS, opening=bad))
    assert lw.opening(lw.declaration("SA")) is None and lw.fence_cutoff("SA", SEASON) == lw.parse_instant(AT)
    why = lw.fence_refusal("SA", SEASON)
    assert "its run record holds no readable opening" in why and "cut at declared_at 2026-11-02T18:10:00Z" in why
    assert "its verdict is not recorded" not in why and "(law 4)" in why
    now = datetime(2026, 12, 8, 12, 0)
    line = next(x for x in lw.lines(lw.read(("SA",), now=now), now) if "the verdict is recorded in leagues-sa-v1" in x)
    assert line.endswith("the run record holds no readable opening: the window's own fence stands from declared_at "
                         "(law 4)")


@pytest.mark.parametrize("first", ["2026-12-07T00:00:00", "2026-12-07T00:00:00+00:00", "2026-12-07T00:00:00.5Z",
                                   "2026-12-07T00:00Z"])
def test_448_1d_a_first_game_later_than_the_opening_but_not_in_the_form_refuses(tmp_path, first):
    """Each of these sorts AFTER the opening as a string, so only the form check refuses it (not vacuous)."""
    assert first > OPENING["kickoff"]
    p = _confirming_file(tmp_path)
    with pytest.raises(reg.RegistryError, match="not start earlier than the opening"):
        reg.record_confirmation("x-v1", list(range(1, 61)), _res(first), "r", p, str(tmp_path / "ids"))


@pytest.mark.parametrize("mid", ["4242", None, True, 4242.0])
def test_448_1d_an_opening_without_an_integer_match_id_refuses_in_the_registry_as_the_window_reads_it(tmp_path, mid):
    """registry.record_confirmation and leagues_window.opening() read a run record's opening the same way: present
    but unreadable is refused, never a fall-back to verdict.at."""
    o = {"kickoff": OPENING["kickoff"], "match_id": mid}
    assert lw.opening({"run": {"result": {"confirmation_opens_after": o}}}) is None
    p = _confirming_file(tmp_path, opening=o)
    with pytest.raises(reg.RegistryError, match="not start earlier than the opening"):
        reg.record_confirmation("x-v1", list(range(1, 61)), _res("2026-12-08T00:00:00Z"), "r", p,
                                str(tmp_path / "ids"))


# ------------------------------------------------------------------------ Codex on #1086, round 1 (60136cfd) --

def test_a_calendar_invalid_opening_reads_as_none_in_the_window_and_refuses_in_the_registry(ledger, tmp_path):
    bad = {"kickoff": "2026-99-40T25:00:00Z", "match_id": 4242}          # INSTANT_Z's shape, no instant
    assert reg.INSTANT_Z.fullmatch(bad["kickoff"]) and not reg._instant_z(bad["kickoff"])
    ledger(_entry(status="confirming", verdict=PASS, opening=bad))
    assert lw.opening(lw.declaration("SA")) is None
    assert lw.fence_cutoff("SA", SEASON) == lw.parse_instant(AT)       # law 4: never a crash, never lifted
    assert "no readable opening" in lw.fence_refusal("SA", SEASON)
    p = _confirming_file(tmp_path, opening=bad)
    with pytest.raises(reg.RegistryError, match="not start earlier than the opening"):
        reg.record_confirmation("x-v1", list(range(1, 61)), _res("2026-12-08T00:00:00Z"), "r", p,
                                str(tmp_path / "ids"))
    p = _confirming_file(tmp_path)                                       # a first game with no calendar instant
    with pytest.raises(reg.RegistryError, match="not start earlier than the opening"):
        reg.record_confirmation("x-v1", list(range(1, 61)), _res("2026-12-99T00:00:00Z"), "r", p,
                                str(tmp_path / "ids2"))


def test_an_opening_stored_as_null_refuses_and_never_falls_back_to_verdict_at(tmp_path):
    p = tmp_path / "x.json"
    e = {"id": "x-v1", "status": "confirming", "confirmation_plan": dict(PLAN),
         "verdict": {"verdict": "PASS", "at": "2026-12-07T12:00:00Z"},
         "run": {"result": {"confirmation_opens_after": None}, "ids_file": None}}
    p.write_text(json.dumps([e]))
    before = p.read_text()
    with pytest.raises(reg.RegistryError, match="not start earlier than the opening"):
        reg.record_confirmation("x-v1", list(range(1, 61)), _res("2026-12-08T00:00:00Z"), "r", str(p),
                                str(tmp_path / "ids"))                  # after verdict.at: the old rule would admit
    assert p.read_text() == before


@pytest.mark.parametrize("verdict", [None, {"verdict": "REJECT", "at": "2026-12-07T12:00:00Z"}, {"at": "x"}, "PASS"])
def test_with_an_opening_a_confirmation_still_needs_a_recorded_pass(tmp_path, verdict):
    p = tmp_path / "x.json"
    e = {"id": "x-v1", "status": "confirming", "confirmation_plan": dict(PLAN), "verdict": verdict,
         "run": {"result": {"confirmation_opens_after": OPENING}, "ids_file": None}}
    p.write_text(json.dumps([e]))
    with pytest.raises(reg.RegistryError, match="needs a recorded PASS verdict"):
        reg.record_confirmation("x-v1", list(range(1, 61)), _res("2026-12-08T00:00:00Z"), "r", str(p),
                                str(tmp_path / "ids"))
