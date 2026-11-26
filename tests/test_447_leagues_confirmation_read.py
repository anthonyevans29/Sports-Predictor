"""THE LEAGUES' CONFIRMATION READ AS A COMMAND (ARCHITECT 2026-11-22, addendum 447 item 3 C1 and item 4 PR 3; addendum
448 item 1(e)-(f); addendum 467 item 1(a); src/walters/leagues_confirm.py, cli.py leagues-confirmation-read).

On tests/test_447_leagues_window_read.py's synthetic SA world (a throwaway SQLite, a tmp registry: the real
docs/registry/experiments.json is never written; the copy and the pages outside the checkout and outside data/): the
window's one read is run, recorded, and its verdict recorded PASS (the computed verdict pinned to PASS, tests only);
the confirmation's games follow the opening, one tied at the opening's kickoff with a higher id. Pins the preflight,
the refusals in order, the reused fences, the place (447 C1), C1(d)'s findings, 448 1(e), Q3's default, B2(d) on the
confirmation, the fingerprint, the guard and the reservation (448 1(f)), the spent rule, the record and its outcome
(computed by the registry), the fence after it, the window's print unchanged, the CLI, and D6's label."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.db.schema import MatchStatus
from src.walters import leagues_confirm as lc
from src.walters import leagues_read as lr
from src.walters import leagues_window as lw
from src.walters import registry as reg
from src.walters import soccer_expansion as sx
from tests.test_447_leagues_window_read import WORD, _copy, _entry, _fp
from tests.test_leagues_window import (AT, AT_TEXT, NOW, _comps, _export, _game, _legs, _members, _priors,  # noqa: F401
                                       _teams, ledger)
from tests.test_record_vs_close import iso_db  # noqa: F401  (a fixture: a throwaway SQLite, cwd = tmp_path)

pytestmark = pytest.mark.usefixtures("iso_db")

ROOT = Path(__file__).resolve().parent.parent
EID = "leagues-sa-v1"
RULING = "ARCHITECT the confirmation's ruling (tests only)"
OPEN_KO = AT + timedelta(hours=1) + timedelta(hours=6 * 59)          # the window's 60th member's kickoff: the opening
OPEN_ID = 2059
TIE_ID = 3000                                                        # at the opening's kickoff, a higher id
SUB_59 = 2700                                  # conf_sub: the window's 59th member, in the opening's second, id > 2059
C60_KO = OPEN_KO + timedelta(hours=6 * 59)                           # the confirmation's 60th member (3059)
FINDINGS = "  - SA · not accounted for by the run record, in neither cohort (447 C1(d)): "   # 447 C1(d)'s head


def _iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _build(ledger, tmp_path, monkeypatch, sub=False, noslot_sub=False):
    """The fixtures' one world. `sub` (the sub-second window): before the window's read, 2058 is cancelled (it takes
    no slot), SUB_59 is a member at OPEN_KO + 200 ms and the 60th, 2059, is stored at OPEN_KO + 500 ms, so the window's
    59th member kicks off in the opening's second with an id above the opening's; the tie 3000 kicks off at OPEN_KO +
    700 ms (after the 60th in raw time, in the opening's second with a higher id: the confirmation's first)."""
    monkeypatch.setattr(reg, "IDS_DIR", str(tmp_path / "ids"))
    monkeypatch.setattr(lr, "RESERVATION_DIR", str(tmp_path))
    _comps()
    ledger(_entry())
    t = _teams("SA")
    _priors("SA", t)
    win = _members("SA", t, 60, 2000, AT + timedelta(hours=1))
    assert win[-1] == (OPEN_ID, OPEN_KO)
    _game(2900, "SA", AT + timedelta(hours=4), (t[2], t[3]), MatchStatus.CANCELLED)
    _game(2950, "SA", AT + timedelta(hours=5), (t[4], t[5]), MatchStatus.POSTPONED)
    tie_ko = OPEN_KO
    if sub:
        _db(2058, status=MatchStatus.CANCELLED)
        _game(SUB_59, "SA", OPEN_KO + timedelta(milliseconds=200), (t[8], t[9]))
        _legs(SUB_59, OPEN_KO + timedelta(milliseconds=200))
        _db(OPEN_ID, utc_date=OPEN_KO + timedelta(milliseconds=500))
        win = [x for x in win[:-2]] + [(SUB_59, OPEN_KO + timedelta(milliseconds=200)),
                                       (OPEN_ID, OPEN_KO + timedelta(milliseconds=500))]
        tie_ko = OPEN_KO + timedelta(milliseconds=700)
        if noslot_sub:                   # a game the window's loop reaches in the opening's second, taking no slot
            _game(NOSLOT_SUB, "SA", OPEN_KO + timedelta(milliseconds=300), (t[4], t[5]), MatchStatus.CANCELLED)
    _game(TIE_ID, "SA", tie_ko, (t[6], t[7]))
    _legs(TIE_ID, tie_ko)
    later = _members("SA", t, 64, 3001, OPEN_KO + timedelta(hours=6))
    _export("SA")
    pulled = tmp_path / "pulled"
    shutil.copytree(tmp_path / "exports", pulled)
    copy = _copy(tmp_path)
    digest = lw.pages_digest(pulled)["digest"]
    with monkeypatch.context() as m:                     # the window's one read, its computed verdict pinned to PASS
        m.setattr(lw, "verdict_of", lambda a, b: "PASS")
        pre = lr.preflight_lines("SA", str(copy), str(pulled), digest, now=NOW)
        res = lr.run("SA", str(copy), str(pulled), digest, WORD, _fp(pre), now=NOW)
    lr.record("SA", res)
    lr.record_verdict("SA", "PASS", "the architect's PASS (tests only)")
    assert reg.get(EID, reg.LEDGER)["status"] == "confirming"
    return {"copy": copy, "exports": pulled, "digest": digest, "window": win, "later": [(TIE_ID, tie_ko)] + later,
            "tmp": tmp_path, "teams": t, "window_res": res}


@pytest.fixture
def conf(ledger, tmp_path, monkeypatch):
    """A recorded PASS on the SA window (60 members 2000-2059, a cancelled 2900 and a postponed 2950 reached and taking
    no slot) and 65 confirmation games after the opening: 3000 at the opening's kickoff, 3001-3064 six hours apart;
    the pages written before every kickoff; the copy taken; the reservations and the ids in tmp_path."""
    return _build(ledger, tmp_path, monkeypatch)


NOSLOT_SUB = 2600    # above the opening's id (2059): in the opening's second, reached by the window's loop, no slot


@pytest.fixture
def conf_noslot(ledger, tmp_path, monkeypatch):
    """conf_sub plus NOSLOT_SUB, cancelled at OPEN_KO + 300 ms: before the 60th (+500 ms) in the window's raw order, so
    the window's loop reaches it and it takes no slot; to the second it is (OPEN_KO, 2600), above the opening."""
    return _build(ledger, tmp_path, monkeypatch, sub=True, noslot_sub=True)


@pytest.fixture
def conf_sub(ledger, tmp_path, monkeypatch):
    """_build's sub-second window: members 2000-2057, SUB_59 (OPEN_KO + 200 ms) and 2059 (OPEN_KO + 500 ms), the
    opening stored (OPEN_KO to the second, 2059); 2058 cancelled; 3000 at OPEN_KO + 700 ms."""
    return _build(ledger, tmp_path, monkeypatch, sub=True)


def _cfp(lines):
    assert lines[-1].startswith("CONFIRMATION FINGERPRINT "), lines[-1]
    return lines[-1].split()[2]


def _cpre(c, **kw):
    a = {"code": "SA", "db": str(c["copy"]), "exports": str(c["exports"]), "pages_digest": c["digest"], "now": NOW}
    a.update(kw)
    return lc.preflight_lines(a["code"], a["db"], a["exports"], a["pages_digest"], now=a["now"])


def _crun(c, fp, **kw):
    a = {"code": "SA", "db": str(c["copy"]), "exports": str(c["exports"]), "pages_digest": c["digest"], "word": WORD,
         "ruling": RULING, "now": NOW, "no_fetch": False}
    a.update(kw)
    return lc.run(a["code"], a["db"], a["exports"], a["pages_digest"], a["word"], fp, a["ruling"], now=a["now"],
                  no_fetch=a["no_fetch"])


def _recopy(c):
    """The store changed after the window's read: a fresh .backup copy (and the pages' digest again)."""
    c["copy"].unlink()
    _copy(c["tmp"])
    c["digest"] = lw.pages_digest(c["exports"])["digest"]


def _db(mid, **fields):
    from src.db.database import session_scope
    from src.db.schema import Match
    with session_scope() as s:
        m = s.get(Match, mid)
        for k, v in fields.items():
            setattr(m, k, v)


def _nothing(c):
    e = reg.get(EID, reg.LEDGER)
    assert not e.get("confirmation") and e["status"] == "confirming"
    assert not os.path.lexists(lc.reservation_path(EID))
    assert not (Path(reg.IDS_DIR) / f"{EID}.confirm.txt").exists()


# ------------------------------------------------------------------------------------------- 1. the preflight --

def test_1_the_preflight_prints_counts_the_opening_findings_first_date_and_fingerprint_and_writes_nothing(conf,
                                                                                                        monkeypatch):
    monkeypatch.setattr(lw, "score", lambda *a, **k: pytest.fail("scored"))
    led = Path(reg.LEDGER).read_bytes()
    ids = sorted(os.listdir(reg.IDS_DIR))
    L = _cpre(conf)
    assert L[0].startswith("LEAGUES CONFIRMATION READ · PREFLIGHT · SA")
    head = next(x for x in L if x.startswith("SA · confirmation of leagues-sa-v1"))
    assert f"opens after match {OPEN_ID} at {_iso(OPEN_KO)} (447 C1, the window's order" in head
    assert "members 60 of 60 · state ready" in head
    assert any("at or before the opening (in the window's order): final or never walked" in x for x in L)
    assert any(x.startswith(FINDINGS + "0") for x in L)
    assert any("took no slot in the window, re-dated, still at or before the opening: 0" in x for x in L)
    assert any("CONFIRMATION READY" in x for x in L)
    assert any(f"the first confirmation member: match {TIE_ID} at {_iso(OPEN_KO)}" in x for x in L)
    fa = (C60_KO.date() + timedelta(days=1)).isoformat()
    assert any(f"the read is allowed from {fa} (UTC)" in x for x in L)
    assert len(_cfp(L)) == 64 and _cfp(L) == _cfp(_cpre(conf))
    from tests.test_leagues_window import FORBIDDEN
    assert not any(FORBIDDEN.search(x) for x in L if not x.startswith("  leagues-sa-v1 · --db"))   # counts only (R2)
    assert Path(reg.LEDGER).read_bytes() == led and sorted(os.listdir(reg.IDS_DIR)) == ids
    _nothing(conf)


# ------------------------------------------------------------------------------- 2-4. the refusals, in order --

def test_2_the_arguments_refuse_before_anything_is_read(conf, monkeypatch):
    monkeypatch.setattr(lc, "check_entry", lambda *a: pytest.fail("read"))
    for kw, why in (({"code": "PL"}, "not one of the five"), ({"db": None}, "--db is required"),
                    ({"exports": ""}, "--exports is required"), ({"pages_digest": None}, "--pages-digest is required"),
                    ({"pages_digest": "xyz"}, "not a sha256"), ({"word": " "}, "architect's word"),
                    ({"ruling": ""}, "--ruling is required")):
        with pytest.raises(lr.ReadRefused, match=why):
            _crun(conf, "0" * 64, **kw)
    with pytest.raises(lr.ReadRefused, match="--confirmation-fingerprint"):
        _crun(conf, None)
    _nothing(conf)


def _set(ledger, e):
    ledger(e)
    return e


def test_3_every_entry_refusal_in_its_order_reserves_nothing(conf, ledger):
    good = reg.get(EID, reg.LEDGER)
    ids_file = Path(reg.IDS_DIR) / f"{EID}.txt"

    def with_(**kw):
        e = json.loads(json.dumps(good))
        e.update(kw)
        return e

    def res_(**kw):
        e = json.loads(json.dumps(good))
        e["run"]["result"].update(kw)
        return e
    cases = [
        (None, "no declared entry"),
        (_entry(), "no run recorded by leagues-window-read"),
        (res_(command="soccer-expansion-gate"), "no run recorded by leagues-window-read"),
        (with_(verdict={"verdict": "REJECT", "ruling": "r", "at": "x"}, status="closed"), "not a recorded PASS"),
        (with_(status="run"), "not 'confirming'"),
        (with_(confirmation={"outcome": "CONFIRMED"}), "a confirmation is recorded"),
        (res_(confirmation_opens_after=None), "no readable opening"),
        (res_(confirmation_opens_after={"kickoff": _iso(OPEN_KO)[:-1], "match_id": OPEN_ID}), "no readable opening"),
        (res_(confirmation_opens_after={"kickoff": reg.OPENING_MIN, "match_id": OPEN_ID}), "no readable opening"),
        (res_(confirmation_opens_after={"kickoff": _iso(OPEN_KO), "match_id": True}), "no readable opening"),
        (with_(confirmation_plan={**lw.RULED_PLAN, "bar": 0.9}), "not the ruled plan"),
        (res_(confirmation_opens_after={"kickoff": _iso(OPEN_KO), "match_id": 2000}), "does not hold together"),
        (res_(members_in_order=good["run"]["result"]["members_in_order"][:59]), "not a list of 60 distinct"),
        (res_(took_no_slot=[{"match_id": "2900", "kickoff": "x", "cause": "cancelled"}]), "took_no_slot is not a list"),
        (with_(run={**good["run"], "ids_sha256": "0" * 64}), "not the run record's 60 members or not its ids_sha256"),
    ]
    for e, why in cases:
        ledger() if e is None else ledger(e)
        with pytest.raises(lr.ReadRefused, match=why):
            _cpre(conf)
        with pytest.raises(lr.ReadRefused, match=why):
            _crun(conf, "f" * 64)
        assert not os.path.lexists(lc.reservation_path(EID))
    ledger(good)
    ids_file.rename(ids_file.with_suffix(".gone"))                      # the run's ids file missing: fails closed
    with pytest.raises(lr.ReadRefused, match="ids file .* is missing"):
        _cpre(conf)
    ids_file.with_suffix(".gone").rename(ids_file)
    Path(lc.reservation_path(EID)).write_text(json.dumps({"started_at": "2027-01-10T00:00:00Z"}))
    with pytest.raises(lr.ReadRefused, match="it is spent"):
        _cpre(conf)
    Path(lc.reservation_path(EID)).unlink()
    assert _cfp(_cpre(conf))                                            # the good entry reads


def test_3_the_plan_refusal_comes_before_the_run_checks(conf, ledger):
    """Two faults together: a stored plan that is not the ruled plan AND no run: the plan's refusal is named (448 2(b),
    the entry's second check)."""
    ledger(_entry(confirmation_plan=None))
    with pytest.raises(lr.ReadRefused, match="not the ruled plan"):
        _cpre(conf)


def test_4_the_reused_fences_a_sidecar_the_checkout_and_the_digest(conf):
    (conf["copy"].parent / "sports.db-wal").write_bytes(b"")
    with pytest.raises(lr.ReadRefused, match="-wal sidecar"):
        _cpre(conf)
    (conf["copy"].parent / "sports.db-wal").unlink()
    with pytest.raises(lr.ReadRefused, match="inside the checkout"):
        _cpre(conf, exports=str(ROOT / "exports"))
    with pytest.raises(lr.ReadRefused, match="does not hold exactly the host's pages"):
        _cpre(conf, pages_digest="a" * 64)
    with pytest.raises(lr.ReadRefused, match="does not hold exactly the host's pages"):
        _crun(conf, "f" * 64, pages_digest="a" * 64)
    _nothing(conf)


# ---------------------------------------------------------------------------------------------- 5. the place --

def test_5_the_cohort_is_the_first_60_later_than_the_opening_the_tie_first_by_id(conf):
    sha, pages, w, stored = lr.load("SA", reg.get(EID, reg.LEDGER), conf["copy"], conf["exports"], conf["digest"],
                                    NOW, confirmation=True)
    later = [mid for mid, _ in conf["later"]]
    assert w["state"] == "ready" and w["members"] == later[:60]
    assert w[lw.FIRST_MEMBER] == (TIE_ID, OPEN_KO) and w[lw.LAST_MEMBER] == (3059, C60_KO)
    window = {mid for mid, _ in conf["window"]}
    reached = set(w["members"]) | {i for i, _, _ in w[lw.TOOK_NO_SLOT]}
    assert not reached & window and OPEN_ID not in reached               # window members, the 60th too: never reached
    assert 3060 not in reached                                          # the 61st: not reached
    assert w["opening"] == (OPEN_KO, OPEN_ID) and w[lw.REDATED] == [] and w[lw.MEMBERS_AFTER] == []
    res = _crun(conf, _cfp(_cpre(conf)))
    assert res["first_game_id"] == TIE_ID and res["first_game_at"] == _iso(OPEN_KO) == res["opening"]["kickoff"]
    assert res["members_in_order"] == later[:60] and res["n"] == 60


# ------------------------------------------------------------------------------------ 6. 447 C1(d): findings --

def test_6_an_unaccounted_game_re_dated_into_the_range_is_a_named_finding_and_moves_the_fingerprint(conf):
    before = _cfp(_cpre(conf))
    t = conf["teams"]
    _game(3100, "SA", AT + timedelta(hours=10, minutes=30), (t[8], t[9]))   # final, in (declared_at, the opening]
    _recopy(conf)
    L = _cpre(conf)
    assert any(x.startswith(FINDINGS + "1") for x in L)
    assert any(f"FINDING match 3100 · kickoff {_iso(AT + timedelta(hours=10, minutes=30))} · status finished" in x
               for x in L)
    after = _cfp(L)
    assert after != before
    with pytest.raises(lr.ReadRefused, match="is not this confirmation's"):              # the stale one: refused
        _crun(conf, before)
    _nothing(conf)
    res = _crun(conf, after)
    assert res["redated_findings"] == [{"match_id": 3100, "kickoff": _iso(AT + timedelta(hours=10, minutes=30)),
                                        "status": "finished"}]
    assert 3100 not in res["members_in_order"]
    assert any(FINDINGS.split(" · ", 1)[1] + "1 finding(s)" in x for x in lc.run_lines(res))


def test_6_a_regular_finding_not_final_makes_the_read_wait(conf):
    t = conf["teams"]
    _game(3101, "SA", AT + timedelta(hours=11), (t[8], t[9]), MatchStatus.SCHEDULED)
    _recopy(conf)
    L = _cpre(conf)
    assert any("state waiting" in x for x in L) and any("CONFIRMATION WAITING" in x for x in L)
    assert "NO fingerprint" in L[-1]
    assert any("FINDING match 3101" in x for x in L)
    with pytest.raises(lr.ReadRefused, match="the read WAITS"):
        _crun(conf, "0" * 64)
    _nothing(conf)


def test_6_an_accounted_game_re_dated_inside_the_range_is_no_finding_and_is_printed_on_its_own_line(conf):
    """CRITIC 3: a took-no-slot game re-dated to a kickoff still at or before the opening is in neither cohort; it is
    no finding (the run record accounts for it) and is printed on its own informational line, never silent."""
    _db(2900, utc_date=AT + timedelta(hours=7))
    _recopy(conf)
    L = _cpre(conf)
    assert any(x.startswith(FINDINGS + "0") for x in L)
    assert any("took no slot in the window, re-dated, still at or before the opening: 1" in x for x in L)
    assert any(f"match 2900 · recorded {_iso(AT + timedelta(hours=4))} · now {_iso(AT + timedelta(hours=7))} · "
               "status cancelled" in x for x in L)
    res = _crun(conf, _cfp(L))
    assert res["redated_findings"] == [] and res["redated_no_slot"] == [
        {"match_id": 2900, "recorded_kickoff": _iso(AT + timedelta(hours=4)), "kickoff": _iso(AT + timedelta(hours=7)),
         "status": "cancelled"}]


def test_6_critic_2_an_unaccounted_game_tied_at_the_openings_kickoff_with_a_lower_id_is_a_finding(conf):
    t = conf["teams"]
    _game(1990, "SA", OPEN_KO, (t[8], t[9]))                            # (kickoff, id) <= the opening: before it
    _recopy(conf)
    sha, pages, w, stored = lr.load("SA", reg.get(EID, reg.LEDGER), conf["copy"], conf["exports"], conf["digest"],
                                    NOW, confirmation=True)
    assert [x[0] for x in w[lw.REDATED]] == [1990] and 1990 not in w["members"]


# ------------------------------------------------------------------------------- 7. 448 1(e), 8. Q3's default --

def test_7_a_not_placed_game_re_dated_after_the_opening_is_a_member_and_the_registry_takes_it(conf):
    assert {"match_id": 2950, "kickoff": _iso(AT + timedelta(hours=5)), "cause": "not_placed"} in \
        conf["window_res"]["took_no_slot"]
    ko = OPEN_KO + timedelta(hours=3)
    _db(2950, utc_date=ko, status=MatchStatus.FINISHED, home_score=2, away_score=1, home_score_90=2, away_score_90=1,
        status_raw="FT")
    _legs(2950, ko)
    _recopy(conf)
    L = _cpre(conf)
    res = _crun(conf, _cfp(L))
    assert res["members_in_order"][:2] == [TIE_ID, 2950] and 3059 not in res["members_in_order"]
    e = lc.record("SA", res, RULING)
    assert e["confirmation"]["outcome"] in lw.CONFIRMATION_OUTCOMES and 2950 in e["confirmation"]["result"][
        "members_in_order"]


def test_8_q3_a_window_member_re_dated_after_the_opening_refuses_before_the_reservation_named(conf):
    _db(2010, utc_date=OPEN_KO + timedelta(hours=1))
    _recopy(conf)
    L = _cpre(conf)
    assert any("window members now later than the opening: 1" in x for x in L)
    assert "the read REFUSES before the reservation" in L[-1] and "2010" in L[-1] and "NO fingerprint" in L[-1]
    with pytest.raises(lr.ReadRefused, match="2010") as ex:
        _crun(conf, "0" * 64)
    assert type(ex.value) is lr.ReadRefused and "nothing reserved" in str(ex.value)
    _nothing(conf)


def test_critic_5_a_sub_second_game_in_the_openings_second_with_a_lower_id_is_before_the_opening(conf):
    """The opening is stored to the second; a game kicking off half a second after it, with a lower id, is compared
    with it at that resolution (leagues_window.place: the kickoff cut to the whole second, then the id): (OPEN_KO, 1995)
    is at or before the opening, so it is no confirmation member (it would write the opening's own first_game_at with
    an id below the opening's, which record_confirmation refuses, 467 item 1(a)); unaccounted, it is a FINDING (447
    C1(d)), and the read is not refused on it."""
    t = conf["teams"]
    _db(TIE_ID, utc_date=OPEN_KO + timedelta(hours=2))
    sub = OPEN_KO + timedelta(milliseconds=500)
    _game(1995, "SA", sub, (t[8], t[9]))
    _legs(1995, sub)
    _export("SA", export_dir=str(conf["exports"]))                      # its row, before its kickoff
    _recopy(conf)
    sha, pages, w, stored = lr.load("SA", reg.get(EID, reg.LEDGER), conf["copy"], conf["exports"], conf["digest"],
                                    NOW, confirmation=True)
    assert 1995 not in w["members"] and [x[0] for x in w[lw.REDATED]] == [1995]
    assert w[lw.FIRST_MEMBER][0] != 1995 and lc.backstop(reg.get(EID, reg.LEDGER), w) is None
    res = _crun(conf, _cfp(_cpre(conf)))
    assert 1995 not in res["members_in_order"] and [x["match_id"] for x in res["redated_findings"]] == [1995]


def test_f1_the_windows_60th_member_at_a_sub_second_kickoff_is_the_opening_never_a_member_after_it(conf):
    """The reviewer's scenario (447's PR 3, P2): the window's 60th member kicks off at OPEN_KO + 500 ms. The window read
    writes the opening to the second (448 item 1(d): _iso(last_ko)), so the raw stored kickoff sorts after the stored
    opening. Compared at the opening's resolution it IS the opening: no refusal (not a window member now later than
    the opening), not a confirmation member, the cohort unchanged."""
    assert conf["window_res"]["confirmation_opens_after"] == {"kickoff": _iso(OPEN_KO), "match_id": OPEN_ID}
    sub = OPEN_KO + timedelta(milliseconds=500)
    _db(OPEN_ID, utc_date=sub)
    _recopy(conf)
    sha, pages, w, stored = lr.load("SA", reg.get(EID, reg.LEDGER), conf["copy"], conf["exports"], conf["digest"],
                                    NOW, confirmation=True)
    later = [mid for mid, _ in conf["later"]]
    assert w[lw.MEMBERS_AFTER] == [] and w[lw.REDATED] == [] and OPEN_ID not in w["members"]
    assert w["state"] == "ready" and w["members"] == later[:60] and w[lw.FIRST_MEMBER] == (TIE_ID, OPEN_KO)
    assert lc.backstop(reg.get(EID, reg.LEDGER), w) is None
    L = _cpre(conf)
    assert not any("window members now later than the opening" in x for x in L)
    res = _crun(conf, _cfp(L))
    assert res["members_in_order"] == later[:60] and OPEN_ID not in res["members_in_order"]


def test_f1_a_game_in_the_openings_second_with_a_higher_id_enters_first_even_before_a_sub_second_60th(conf):
    """A game in the opening's second with a higher id is AFTER the opening, whatever its sub-second part: 2500 at
    OPEN_KO + 200 ms precedes the window's 60th member (2059, re-stored at OPEN_KO + 500 ms) in raw time, yet it is the
    confirmation's first member (first_game_at the opening's second, first_game_id above the opening's: the registry
    takes it), and 2059 is the opening, never a member after it."""
    t = conf["teams"]
    _db(OPEN_ID, utc_date=OPEN_KO + timedelta(milliseconds=500))
    _db(TIE_ID, utc_date=OPEN_KO + timedelta(hours=2))
    sub = OPEN_KO + timedelta(milliseconds=200)
    _game(2500, "SA", sub, (t[8], t[9]))
    _legs(2500, sub)
    _export("SA", export_dir=str(conf["exports"]))
    _recopy(conf)
    sha, pages, w, stored = lr.load("SA", reg.get(EID, reg.LEDGER), conf["copy"], conf["exports"], conf["digest"],
                                    NOW, confirmation=True)
    assert w[lw.MEMBERS_AFTER] == [] and w[lw.REDATED] == [] and OPEN_ID not in w["members"]
    assert w["members"][0] == 2500 and w[lw.FIRST_MEMBER] == (2500, sub)
    assert lc.backstop(reg.get(EID, reg.LEDGER), w) is None
    res = _crun(conf, _cfp(_cpre(conf)))
    assert res["first_game_id"] == 2500 and res["first_game_at"] == _iso(OPEN_KO)
    assert lc.record("SA", res, RULING)["confirmation"]["outcome"] in lw.CONFIRMATION_OUTCOMES


def test_f3_a_re_dated_window_member_not_final_refuses_naming_it_never_waiting(conf):
    """540 item 1 Q3: "THE READ REFUSES BEFORE ITS RESERVATION, NAMING THE GAME". A window member re-dated past the
    opening that is not final (here SCHEDULED, un-ingested at the clock) would make the confirmation WAIT; the moved
    member is read first, so the read refuses naming it and the preflight prints that refusal, never 'waiting'."""
    _db(2010, utc_date=OPEN_KO + timedelta(hours=1), status=MatchStatus.SCHEDULED, home_score=None, away_score=None,
        home_score_90=None, away_score_90=None, status_raw=None)
    _recopy(conf)
    sha, pages, w, stored = lr.load("SA", reg.get(EID, reg.LEDGER), conf["copy"], conf["exports"], conf["digest"],
                                    NOW, confirmation=True)
    assert w["state"] == "waiting" and [x[0] for x in w[lw.MEMBERS_AFTER]] == [2010]
    L = _cpre(conf)
    assert "the read REFUSES before the reservation" in L[-1] and "match 2010" in L[-1] and "NO fingerprint" in L[-1]
    assert "540 item 1 Q3" in L[-1] and "not ready" not in L[-1]
    with pytest.raises(lr.ReadRefused) as ex:
        _crun(conf, "0" * 64)
    assert "match 2010" in str(ex.value) and "WAITS" not in str(ex.value) and "nothing reserved" in str(ex.value)
    _nothing(conf)


# --------------------------------------------------------------------------- 9. B2(d) on the confirmation --

def test_9_the_read_refuses_on_the_60th_confirmation_members_date_and_is_allowed_the_day_after(conf):
    same_day = C60_KO.replace(hour=23, minute=59)
    L = _cpre(conf, now=same_day)
    assert any(f"NOT TODAY ({C60_KO.date().isoformat()})" in x for x in L)
    with pytest.raises(lr.ReadRefused, match=r"the day after \(addendum 447 item 2 B2\(d\)\)"):
        _crun(conf, _cfp(L), now=same_day)
    _nothing(conf)
    next_day = datetime.combine(C60_KO.date() + timedelta(days=1), datetime.min.time())
    assert _crun(conf, _cfp(_cpre(conf, now=next_day)), now=next_day)["first_allowed_date"] == next_day.date().isoformat()


# ---------------------------------------------------------------------------------------- 10. the fingerprint --

def test_10_the_fingerprint_covers_each_part_and_its_tag_is_not_the_windows(conf):
    e = reg.get(EID, reg.LEDGER)
    sha, pages, w, stored = lr.load("SA", e, conf["copy"], conf["exports"], conf["digest"], NOW, confirmation=True)
    d = pages["digest"]
    base = lc.confirmation_fingerprint("SA", w, stored, sha, d)
    assert base == _cfp(_cpre(conf))
    assert lr.window_fingerprint("SA", w, stored, sha, d) != base       # the window's tag: never this one
    acc = w["accounted"]
    changed = [
        lc.confirmation_fingerprint("SA", {**w, "members": w["members"][::-1]}, stored, sha, d),
        lc.confirmation_fingerprint("SA", w, {**stored, w["members"][0]: {"x": 1}}, sha, d),
        lc.confirmation_fingerprint("SA", {**w, "ruled_items_read": {1: {"match_id": 1}}}, stored, sha, d),
        lc.confirmation_fingerprint("SA", w, stored, "b" * 64, d),
        lc.confirmation_fingerprint("SA", w, stored, sha, "c" * 64),
        lc.confirmation_fingerprint("SA", {**w, "constants": {**w["constants"], "rho": -0.2}}, stored, sha, d),
        lc.confirmation_fingerprint("SA", {**w, "opening": (OPEN_KO + timedelta(seconds=1), OPEN_ID)}, stored, sha, d),
        lc.confirmation_fingerprint("SA", {**w, lw.REDATED: [(1, AT, "finished")]}, stored, sha, d),
        lc.confirmation_fingerprint("SA", {**w, "accounted": {**acc, "no_slot": {}}}, stored, sha, d)]
    assert len({base, *changed}) == len(changed) + 1
    with pytest.raises(lr.ReadRefused, match="is not this confirmation's"):
        _crun(conf, "0" * 64)
    _nothing(conf)


def test_10_15_the_window_fingerprints_body_is_unchanged_without_an_opening(conf):
    """The window's fingerprint is the sha256 of exactly the body PR 1 hashed (no key added without an opening)."""
    e = reg.get(EID, reg.LEDGER)
    sha, pages, w, stored = lr.load("SA", e, conf["copy"], conf["exports"], conf["digest"], NOW)
    assert w["opening"] is None and lw.REDATED not in w and "accounted" not in w
    body = {"tag": "leagues-window-read v1", "code": "SA", "id": EID, "members": list(w["members"]),
            "stored_rows": [stored.get(i) for i in w["members"]],
            "ruled": lr._jsonable(sorted(w.get("ruled_items_read", {}).items())),
            "copy_sha256": sha, "pages_digest": pages["digest"], "constants": dict(w["constants"])}
    blob = json.dumps(lr._jsonable(body), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False,
                      default=str)
    assert lr.window_fingerprint("SA", w, stored, sha, pages["digest"]) == hashlib.sha256(blob.encode()).hexdigest()
    assert not any("confirmation of" in x or "re-dated" in x for x in lw.lines({"SA": w}, NOW))


# ----------------------------------------------------------------- 11. the guard, 12. the reservation and spent --

def test_11_the_guard_runs_before_the_reservation_and_its_refusal_reserves_nothing(conf, monkeypatch):
    fp = _cfp(_cpre(conf))
    calls = []

    def guard(eid, no_fetch=False, repo=None):
        calls.append((eid, no_fetch))
        raise reg.CrossRefRefused("a confirmation record on another ref (tests only)")
    monkeypatch.setattr(reg, "cross_ref_guard", guard)
    with pytest.raises(lr.ReadRefused, match="a confirmation record on another ref"):
        _crun(conf, fp, no_fetch=True)
    assert calls == [(EID, True)]
    _nothing(conf)


def test_11_the_reservation_is_the_name_the_guard_reads(monkeypatch):
    monkeypatch.setattr(lr, "RESERVATION_DIR", None)
    monkeypatch.setattr(reg, "LEDGER", os.path.join(reg.ROOT, "docs", "registry", "experiments.json"))  # a path only
    for eid in lw.DECLARATION_IDS.values():
        rel = os.path.relpath(lc.reservation_path(eid), reg.ROOT).replace(os.sep, "/")
        assert rel == reg._guard_paths(eid)["confirmation reservation"] == f"docs/registry/{eid}.confirm.started.json"
        assert lc.reservation_path(eid) != lr.reservation_path(eid)        # never the window read's


def test_12_a_failed_reservation_write_spends_nothing(conf, monkeypatch):
    from src.walters import nfl_v2_gate as ng
    fp = _cfp(_cpre(conf))
    monkeypatch.setattr(ng, "_write_all", lambda *a: (_ for _ in ()).throw(OSError("disk full (tests only)")))
    with pytest.raises(lr.ReadRefused, match="removed; nothing scored"):
        _crun(conf, fp)
    _nothing(conf)


def test_12_a_failure_after_the_reservation_leaves_the_read_spent_and_records_nothing(conf, monkeypatch):
    fp = _cfp(_cpre(conf))
    seen = []
    real = lw.score

    def boom(*a, **k):
        seen.append(os.path.lexists(lc.reservation_path(EID)))
        raise lw.WindowRefused("the confirmation moved (tests only)")
    monkeypatch.setattr(lw, "score", boom)
    with pytest.raises(lr.SpentRefused, match="the reservation stands and the confirmation's one read is spent"):
        _crun(conf, fp)
    assert seen == [True] and os.path.lexists(lc.reservation_path(EID))
    assert not reg.get(EID, reg.LEDGER).get("confirmation")
    with pytest.raises(lr.ReadRefused, match="it is spent"):              # one read stays one
        _crun(conf, fp)
    Path(lc.reservation_path(EID)).unlink()

    def score_then_touch(*a, **k):
        out = real(*a, **k)
        p = sorted(conf["exports"].glob("soccer_expansion_shadow_*.json"))[0]
        p.write_text(p.read_text() + " ")
        return out
    monkeypatch.setattr(lw, "score", score_then_touch)
    with pytest.raises(lr.SpentRefused, match="the pages changed during the read"):
        _crun(conf, fp)
    assert not reg.get(EID, reg.LEDGER).get("confirmation")


def test_12_the_copy_changing_during_the_score_leaves_the_read_spent(conf, monkeypatch):
    fp = _cfp(_cpre(conf))
    real = lw.score

    def score_then(*a, **k):
        out = real(*a, **k)
        with open(conf["copy"], "ab") as f:
            f.write(b"\0" * 10)
        return out
    monkeypatch.setattr(lw, "score", score_then)
    with pytest.raises(lr.SpentRefused, match="the copy changed during the read"):
        _crun(conf, fp)
    assert os.path.lexists(lc.reservation_path(EID)) and not reg.get(EID, reg.LEDGER).get("confirmation")


# ------------------------------------------------------------------------------ 13-14. the record, the fence --

def _pin(monkeypatch, cand, close):
    real = lw.aggregate

    def agg(pairs):
        out = real(pairs)
        out.update(ll_candidate=cand, ll_close=close)
        return out
    monkeypatch.setattr(lw, "aggregate", agg)


@pytest.mark.parametrize("cand, close, outcome, status", [(0.9, 1.0, "CONFIRMED", "production"),
                                                         (1.0, 1.0, "NOT_CONFIRMED", "closed"),
                                                         (1.1, 1.0, "NOT_CONFIRMED", "closed")])
def test_13_14_the_record_computes_the_outcome_a_tie_fails_and_the_fence_lifts(conf, monkeypatch, cand, close,
                                                                               outcome, status):
    assert lw.fence_cutoff("SA", lw.SEASON) == OPEN_KO - timedelta(microseconds=1)
    _pin(monkeypatch, cand, close)
    fp = _cfp(_cpre(conf))
    res = _crun(conf, fp)
    for k in ("command", "code", "n", "log_loss", "reference_log_loss", "first_game_at", "first_game_id",
              "members_in_order", "opening", "took_no_slot", "redated_findings", "audit", "audit_lines",
              "frozen_constants", "ruled_exclusions", "copy_sha256", "pages", "architect_word",
              "confirmation_fingerprint", "read_clock", "first_allowed_date", "window_ids_sha256", "reservation"):
        assert k in res, k
    assert "calls_rule" not in res                                      # Q2's default: no key
    assert (res["log_loss"], res["reference_log_loss"]) == (cand, close) and res["command"] == lc.COMMAND
    assert res["window_ids_sha256"] == reg.get(EID, reg.LEDGER)["run"]["ids_sha256"]
    assert res["reservation"] == os.path.relpath(lc.reservation_path(EID), reg.ROOT)
    held = json.loads(Path(lc.reservation_path(EID)).read_text())
    assert held["confirmation_fingerprint"] == fp and held["opening"] == {"kickoff": _iso(OPEN_KO), "match_id": OPEN_ID}
    lines = lc.run_lines(res)
    assert any(f"candidate mean log-loss {cand!r} · the close's {close!r} · CONFIRMED iff the candidate's is strictly "
               "below the close's; a tie fails" in x for x in lines)
    e = lc.record("SA", res, RULING)
    assert e["confirmation"]["outcome"] == outcome and e["status"] == status and e["confirmation"]["ruling"] == RULING
    ids = (Path(reg.IDS_DIR) / f"{EID}.confirm.txt").read_text().split()
    assert ids == [str(i) for i in sorted(res["members_in_order"])] and len(ids) == 60
    assert lc.recorded_line(e) == (f"RECORDED: {outcome} · status {status} — commit docs/registry/ (experiments.json, "
                                   f"ids/{EID}.confirm.txt, {EID}.confirm.started.json) on "
                                   f"laptop/{EID}-confirmation-record")
    assert lw.fence_cutoff("SA", lw.SEASON) is None and lw.fence_refusal("SA", lw.SEASON) is None
    with pytest.raises(lr.ReadRefused):
        _crun(conf, fp)
    with pytest.raises(lr.ReadRefused, match="not 'confirming'"):
        _cpre(conf)


# ------------------------------------------------------------------------------------------- 16. the CLI --

def test_16_the_cli_refuses_with_exit_2_has_no_record_verdict_and_records_on_the_read(conf, monkeypatch):
    from click.testing import CliRunner

    import cli
    from src import timeutil
    monkeypatch.setattr(timeutil, "utc_now_naive", lambda: NOW)          # the read clock, after the 60th's day
    base = ["leagues-confirmation-read", "--code", "SA", "--db", str(conf["copy"]), "--exports", str(conf["exports"]),
            "--pages-digest", conf["digest"]]
    r = CliRunner().invoke(cli.cli, base + ["--architect-word", WORD, "--ruling", RULING])
    assert r.exit_code == 2 and "REFUSED: " in r.output and "--confirmation-fingerprint" in r.output
    r = CliRunner().invoke(cli.cli, base + ["--preflight", "--ruling", RULING])
    assert r.exit_code == 2 and "takes no word, no fingerprint and no ruling" in r.output
    r = CliRunner().invoke(cli.cli, base + ["--record-verdict", "PASS"])
    assert r.exit_code == 2 and "No such option" in r.output
    r = CliRunner().invoke(cli.cli, base + ["--preflight"])
    assert r.exit_code == 0, r.output
    fp = r.output.strip().splitlines()[-1].split()[2]
    _nothing(conf)
    r = CliRunner().invoke(cli.cli, base + ["--architect-word", WORD, "--confirmation-fingerprint", fp, "--ruling",
                                            RULING, "--no-fetch"])
    assert r.exit_code == 0, r.output
    out = r.output
    assert out.index("--exports: ") < out.index("cross-ref guard") < out.index("CONFIRMED iff") < out.index("RECORDED: ")
    e = reg.get(EID, reg.LEDGER)
    assert f"RECORDED: {e['confirmation']['outcome']} · status {e['status']}" in out
    r = CliRunner().invoke(cli.cli, base + ["--architect-word", WORD, "--confirmation-fingerprint", fp, "--ruling",
                                            RULING])
    assert r.exit_code == 2 and "REFUSED: " in r.output


# ------------------------------------------------------------------------ 17. the fence, 18. D6's label --

def test_17_while_confirming_the_fence_refuses_another_reader_but_not_the_confirmation_read(conf):
    why = lw.fence_refusal("SA", lw.SEASON)
    assert why and "AT OR AFTER the opening" in why and f"(match {OPEN_ID})" in why
    assert sx.guards_backtest("SA", lw.SEASON) == why
    assert _cfp(_cpre(conf))                                            # membership consults no fence


def test_18_a_confirming_entrys_shadow_binding_still_labels_rows_with_declared_at(conf):
    b = sx.shadow_binding("SA")
    assert b["candidate"] == EID and b["declared_at"] == AT_TEXT and b["state"] == sx.SHADOW_EXPORTING


def test_15_the_window_read_of_a_confirming_entry_prints_as_before(conf):
    """No opening is passed to the window's read: its print keeps the declared_at head and the verdict line."""
    w = lw.read(("SA",), now=NOW, export_dir=str(conf["exports"]))
    L = lw.lines(w, NOW)
    assert any(x.startswith(f"SA · declared_at {_iso(AT)} (leagues-sa-v1; frozen") for x in L)
    assert any("the confirmation is open: the fence holds from the opening, inclusive" in x for x in L)
    assert not any("CONFIRMATION READY" in x or "re-dated" in x for x in L)


# ============================================ ARCHITECT 2026-11-25, addendum 540 item 1: the five questions, ruled ==

def _tree(c):
    """Every byte the registry side holds: the ledger, the ids files, the reservations (the tmp registry's own)."""
    ids = Path(reg.IDS_DIR)
    return (Path(reg.LEDGER).read_bytes(), {f: (ids / f).read_bytes() for f in sorted(os.listdir(ids))},
            {f: (c["tmp"] / f).read_bytes() for f in sorted(os.listdir(c["tmp"])) if f.endswith(".json")})


OUTCOME_WORDS = ["CONFIRMED", "not_confirmed", "NOT_CONFIRMED", "Confirmed", "addendum 541 (2026-12-20): confirmed.",
                 "the read is NOT_CONFIRMED", "-CONFIRMED-"]


@pytest.mark.parametrize("flag", ["word", "ruling"])
@pytest.mark.parametrize("text", OUTCOME_WORDS)
def test_540_q1i_a_word_or_ruling_naming_an_outcome_refuses_before_any_load(conf, monkeypatch, flag, text):
    """Q1(i): "NO WORD OF MINE ABOUT THE OUTCOME IS TAKEN IN ADVANCE. The outcome is the computed one." A word or a
    ruling naming CONFIRMED or NOT_CONFIRMED (any case, as a word) refuses, before any load, nothing reserved."""
    fp = _cfp(_cpre(conf))
    before = _tree(conf)
    monkeypatch.setattr(lc, "check_entry", lambda *a: pytest.fail("loaded"))
    monkeypatch.setattr(lr, "check_copy", lambda *a: pytest.fail("loaded"))
    monkeypatch.setattr(lr, "load", lambda *a, **k: pytest.fail("loaded"))
    with pytest.raises(lr.ReadRefused, match=rf"--{'architect-word' if flag == 'word' else 'ruling'} names an "
                                             r"outcome .*addendum 540 item 1 Q1\(i\)\); nothing read"):
        _crun(conf, fp, **{flag: text})
    assert _tree(conf) == before
    _nothing(conf)


@pytest.mark.parametrize("text", ["ARCHITECT addendum 541, 2026-12-20: the confirmation read is ordered",
                                  "unconfirmed? no: the confirmation's one read", "CONFIRMEDX", "confirmations"])
def test_540_q1i_an_addendum_by_number_and_date_is_taken(text):
    assert lc.outcome_refusal(WORD, text) is None and lc.outcome_refusal(text, RULING) is None


def test_540_q1i_the_cli_names_the_ruling_as_the_addendum_and_refuses_an_outcome_with_exit_2(conf, monkeypatch):
    from click.testing import CliRunner

    import cli
    r = CliRunner().invoke(cli.cli, ["leagues-confirmation-read", "--help"])
    flat = " ".join(r.output.split())
    assert "The addendum that orders the read, by number and date (never an outcome)" in flat
    base = ["leagues-confirmation-read", "--code", "SA", "--db", str(conf["copy"]), "--exports", str(conf["exports"]),
            "--pages-digest", conf["digest"], "--confirmation-fingerprint", "0" * 64]
    monkeypatch.setattr(lc, "check_entry", lambda *a: pytest.fail("loaded"))
    for args in (["--architect-word", WORD, "--ruling", "CONFIRMED"],
                 ["--architect-word", "NOT_CONFIRMED", "--ruling", RULING]):
        r = CliRunner().invoke(cli.cli, base + args)
        assert r.exit_code == 2 and "REFUSED: " in r.output and "names an outcome" in r.output
    _nothing(conf)
    doc = (ROOT / "docs" / "CLI.md").read_text()
    assert "`--ruling` is the addendum that orders the read, by number and date (never an outcome)" in doc
    assert "the addendum that orders the read, by number and date (never an outcome)" in " ".join(lc.__doc__.split())


def test_540_q1ii_the_preflight_computes_no_figure_and_reserves_nothing(conf, monkeypatch):
    """Q1(ii): "A PREFLIGHT THAT COMPUTES NO FIGURE and reserves nothing: the refusals in order, the cohort's count,
    the pages digest, the first date the read is allowed." No score, no aggregate, no verdict, no audit; no log-loss
    of either arm in any line (the read's own figures, computed after, appear nowhere in it); no registry byte."""
    before = _tree(conf)
    with monkeypatch.context() as m:
        for name in ("score", "aggregate", "verdict_of", "audit"):
            m.setattr(lw, name, lambda *a, _n=name, **k: pytest.fail(f"the preflight called {_n}"))
        m.setattr(lr, "reserve", lambda *a, **k: pytest.fail("reserved"))
        m.setattr(reg, "cross_ref_guard", lambda *a, **k: pytest.fail("guarded"))
        L = _cpre(conf)
    assert _tree(conf) == before
    _nothing(conf)
    text = "\n".join(L)
    from tests.test_leagues_window import FORBIDDEN
    assert not any(FORBIDDEN.search(x) for x in L if not x.startswith("  leagues-sa-v1 · --db"))
    assert any("members 60 of 60" in x for x in L)                                       # the cohort's count
    assert any(f"digest {conf['digest']} = the host's" in x for x in L)                  # the pages digest
    fa = (C60_KO.date() + timedelta(days=1)).isoformat()
    assert any(f"the read is allowed from {fa} (UTC)" in x for x in L)                   # the first date allowed
    res = _crun(conf, _cfp(L))                                                           # the figures, after
    for v in (res["log_loss"], res["reference_log_loss"]):
        assert repr(v) not in text and f"{v:.4f}" not in text and f"{v:.3f}" not in text
    with pytest.raises(lr.ReadRefused, match="not a sha256"):                            # the refusals, as the read's
        _cpre(conf, pages_digest="xyz")


@pytest.mark.parametrize("cand, close, outcome", [(0.9, 1.0, "CONFIRMED"), (1.0, 1.0, "NOT_CONFIRMED"),
                                                  (1.1, 1.0, "NOT_CONFIRMED")])
def test_540_q2_a_confirmed_record_prints_one_console_line_stored_nowhere(conf, monkeypatch, cand, close, outcome):
    from click.testing import CliRunner

    import cli
    from src import timeutil
    monkeypatch.setattr(timeutil, "utc_now_naive", lambda: NOW)
    _pin(monkeypatch, cand, close)
    base = ["leagues-confirmation-read", "--code", "SA", "--db", str(conf["copy"]), "--exports", str(conf["exports"]),
            "--pages-digest", conf["digest"]]
    r = CliRunner().invoke(cli.cli, base + ["--preflight"])
    fp = r.output.strip().splitlines()[-1].split()[2]
    r = CliRunner().invoke(cli.cli, base + ["--architect-word", WORD, "--confirmation-fingerprint", fp, "--ruling",
                                            RULING, "--no-fetch"])
    assert r.exit_code == 0, r.output
    e = reg.get(EID, reg.LEDGER)
    assert e["confirmation"]["outcome"] == outcome
    lines = r.output.splitlines()
    noted = [x for x in lines if "turns on no call" in x]
    if outcome == "CONFIRMED":
        assert noted == [lc.CONFIRMED_NOTE] and lines[-1] == lc.CONFIRMED_NOTE
        assert "addendum 220 item 3" in lc.CONFIRMED_NOTE and "addendum 505 item 2(c)" in lc.CONFIRMED_NOTE
        assert lc.confirmed_note(e) == lc.CONFIRMED_NOTE
    else:
        assert noted == [] and lc.confirmed_note(e) is None
    stored = [Path(reg.LEDGER).read_text(), *((Path(reg.IDS_DIR) / f).read_text() for f in os.listdir(reg.IDS_DIR)),
              Path(lc.reservation_path(EID)).read_text()]
    for blob in stored:                                           # no result key, no ledger key, no file holds it
        assert "turns on no call" not in blob and "540 item 1 Q2" not in blob
    assert not any("call" in k for k in e["confirmation"]["result"]) and "calls_rule" not in e["confirmation"]


def _rule(eid_entry, mid, ko, cause="re-dated past the opening after the window's read (tests only)"):
    e = json.loads(json.dumps(eid_entry))
    e[lw.RULED_FIELD] = list(e.get(lw.RULED_FIELD) or []) + [
        {"match_id": mid, "kickoff": _iso(ko), "cause": cause, "ruling": "ARCHITECT addendum 9999 (tests only)"}]
    return e


def test_540_q3_a_moved_window_member_refuses_until_a_ruled_item_names_it_then_takes_no_slot(conf, ledger):
    """Q3: the read refuses before its reservation, naming the game; "It lifts only by my registry write naming the
    game (Q4's list); after that the game is out by its named cause and takes no slot.\""""
    moved = OPEN_KO + timedelta(hours=1)                      # between the tie (3000) and 3001: it would be reached
    _db(2010, utc_date=moved)
    _recopy(conf)
    L = _cpre(conf)
    assert "the read REFUSES before the reservation" in L[-1] and "2010" in L[-1]       # named
    with pytest.raises(lr.ReadRefused, match="2010 .*nothing reserved"):
        _crun(conf, "0" * 64)
    _nothing(conf)
    ledger(_rule(reg.get(EID, reg.LEDGER), 2010, moved))     # the architect's registry write (tests only)
    L = _cpre(conf)
    assert not any("window members now later than the opening" in x for x in L)
    assert any(x.startswith("  - SA · excluded by ruled cause (no slot): 1") for x in L)    # named on the print
    assert any(x.startswith(f"    - match 2010 · kickoff {_iso(moved)} · cause: re-dated past the opening") for x in L)
    sha, pages, w, stored = lr.load("SA", reg.get(EID, reg.LEDGER), conf["copy"], conf["exports"], conf["digest"],
                                    NOW, confirmation=True)
    assert w[lw.MEMBERS_AFTER] == [] and 2010 not in w["members"] and lc.backstop(reg.get(EID, reg.LEDGER), w) is None
    assert (2010, moved, lw.RULED) in w[lw.TOOK_NO_SLOT] and w["excluded"][lw.RULED] == 1
    assert w["members"] == [mid for mid, _ in conf["later"]][:60]                     # it took no slot
    res = _crun(conf, _cfp(L))
    assert {"match_id": 2010, "kickoff": _iso(moved), "cause": lw.RULED} in res["took_no_slot"]
    assert [it["match_id"] for it in res["audit"][lw.RULED]] == [2010]
    assert res["audit"][lw.RULED][0]["cause"].startswith("re-dated past the opening")
    assert 2010 not in res["members_in_order"] and res["n"] == 60
    assert lc.record("SA", res, RULING)["confirmation"]["outcome"] in lw.CONFIRMATION_OUTCOMES


def test_540_q3_the_lift_is_the_confirmations_only_the_windows_read_never_removes_a_member(conf, ledger):
    """Without an opening (the window's read) a listed game holding its stored row is a member the list never
    removes: the premise refusal (#803) stands, unchanged."""
    ko = AT + timedelta(hours=61, minutes=1)                             # 2010, a minute later: still a member
    _db(2010, utc_date=ko)
    _recopy(conf)
    ledger(_rule(reg.get(EID, reg.LEDGER), 2010, ko))
    w = lw.read(("SA",), now=NOW, export_dir=str(conf["exports"]))["SA"]
    assert "match 2010 holds its stored prospective row" in w["refused"]
    sha, pages, cw, stored = lr.load("SA", reg.get(EID, reg.LEDGER), conf["copy"], conf["exports"], conf["digest"],
                                     NOW, confirmation=True)                # before the opening: the list does nothing
    assert [x["match_id"] for x in cw["ruled_not_applied"]] == [2010] and cw[lw.RULED] == []
    assert cw["ruled_not_applied"][0]["why"].startswith("before the opening")


def _guard_reader(c):
    def read(rel):
        name = rel.split("/")[-1]
        if rel == "docs/registry/experiments.json":
            f = Path(reg.LEDGER)
        elif rel.startswith("docs/registry/ids/"):
            f = Path(reg.IDS_DIR) / name
        else:
            f = c["tmp"] / name
        return f.read_bytes() if f.is_file() else None
    return read


def test_540_q4_an_item_added_after_the_verdict_changes_nothing_the_fingerprint_or_a_guard_reads_again(conf, ledger):
    """Q4's condition: "an item added after the window's verdict must change nothing that the window's recorded
    fingerprint or any guard reads again". The guard's state (#329, all five kinds), the stored run record (its window
    fingerprint and opening), the run's ids file, the window's reservation, the fence and the registry's backstop read
    the same before and after the item."""
    e0 = reg.get(EID, reg.LEDGER)
    sha, pages, w, stored = lr.load("SA", e0, conf["copy"], conf["exports"], conf["digest"], NOW, confirmation=True)
    first = w[lw.FIRST_MEMBER]

    def reads():
        e = reg.get(EID, reg.LEDGER)
        return (reg._guard_state(EID, _guard_reader(conf)), json.dumps(e["run"], sort_keys=True),
                (Path(reg.IDS_DIR) / f"{EID}.txt").read_bytes(), Path(lr.reservation_path(EID)).read_bytes(),
                lw.fence_cutoff("SA", lw.SEASON), lw.opening(e), lw.confirmation_basis(e),
                reg.confirmation_refusal(EID, list(w["members"]), _iso(first[1]), first[0], path=reg.LEDGER,
                                         ids_dir=reg.IDS_DIR))
    before = reads()
    assert before[0]["run record"] is not None and before[0]["reservation"] is not None and before[-1] is None
    assert json.loads(before[1])["result"]["window_fingerprint"] == conf["window_res"]["window_fingerprint"]
    later = conf["later"][-1]                                      # a game the confirmation does not reach (3064)
    ledger(_rule(e0, later[0], later[1], cause="a ruled cause after the verdict (tests only)"))
    assert reg.get(EID, reg.LEDGER)[lw.RULED_FIELD] and reads() == before
    lc.check_entry("SA")                                           # the entry still reads


# --------------------------------------------- 540 item 1 Q5: the reader's backstop catches the three before the reservation

def test_540_q5_the_backstop_reads_the_three_guards_before_the_reservation(conf):
    e = reg.get(EID, reg.LEDGER)
    sha, pages, w, stored = lr.load("SA", e, conf["copy"], conf["exports"], conf["digest"], NOW, confirmation=True)
    assert lc.backstop(e, w) is None
    extra = {**w, "members": list(w["members"]) + [3060]}                           # (b) 61, not the plan's 60
    assert "540 item 1 Q5(b)" in lc.backstop(e, extra)
    stray = {**w, lw.FIRST_MEMBER: (987654, w[lw.FIRST_MEMBER][1] + timedelta(hours=1))}   # (c) not among the ids
    assert "540 item 1 Q5(c)" in lc.backstop(e, stray)
    ids_file = Path(reg.IDS_DIR) / f"{EID}.txt"
    ids_file.rename(ids_file.with_suffix(".gone"))                                   # (a) the run's ids file gone
    try:
        assert "540 item 1 Q5(a)" in lc.backstop(e, w)
        with pytest.raises(lr.ReadRefused, match="ids file .* is missing"):           # the reader refuses it first
            _crun(conf, "0" * 64)
    finally:
        ids_file.with_suffix(".gone").rename(ids_file)
    _nothing(conf)


# ------------------------------------------------- a window member in the opening's second (the remaining gap) --

def test_gap_a_window_member_in_the_openings_second_with_a_higher_id_stays_a_window_member(conf_sub):
    """The window's 59th member (2700, OPEN_KO + 200 ms) has an id above its 60th's (2059, OPEN_KO + 500 ms); the
    opening is stored (OPEN_KO to the second, 2059). Nobody re-dated 2700: it is still in the opening's second, so it
    is never 'after' the opening (leagues_window.after_opening: a member only in a LATER second), never in
    MEMBERS_AFTER, never refused, never a finding; the cohort is unchanged."""
    r = conf_sub["window_res"]
    assert r["members_in_order"][-2:] == [SUB_59, OPEN_ID] and 2058 not in r["members_in_order"]
    assert r["confirmation_opens_after"] == {"kickoff": _iso(OPEN_KO), "match_id": OPEN_ID}
    e = reg.get(EID, reg.LEDGER)
    sha, pages, w, stored = lr.load("SA", e, conf_sub["copy"], conf_sub["exports"], conf_sub["digest"], NOW,
                                    confirmation=True)
    later = [mid for mid, _ in conf_sub["later"]]
    assert w[lw.MEMBERS_AFTER] == [] and w[lw.REDATED] == [] and w[lw.REDATED_NO_SLOT] == []
    assert SUB_59 not in w["members"] and SUB_59 not in {i for i, _, _ in w[lw.TOOK_NO_SLOT]}
    assert w["state"] == "ready" and w["members"] == later[:60] and w[lw.FIRST_MEMBER][0] == TIE_ID
    assert lc.moved_refusal(e, w) is None and lc.backstop(e, w) is None
    L = _cpre(conf_sub)
    assert not any("window members now later than the opening" in x for x in L)
    res = _crun(conf_sub, _cfp(L))
    assert res["members_in_order"] == later[:60] and SUB_59 not in res["members_in_order"]
    assert res["first_game_id"] == TIE_ID and res["first_game_at"] == _iso(OPEN_KO)
    assert lc.record("SA", res, RULING)["confirmation"]["outcome"] in lw.CONFIRMATION_OUTCOMES


def test_gap_a_window_member_re_dated_to_a_later_second_refuses_and_lifts_by_an_item_written_to_the_second(
        conf_sub, ledger):
    """2700 re-dated to OPEN_KO + 1.3 s: a LATER second than the opening's, so it is after the opening and Q3 refuses
    naming it. The architect's item copies the refusal's kickoff (to the second, with the Z); in the confirmation's
    read the game's sub-second kickoff is cut to the second before it is compared, so the item matches and the lift
    works: 2700 out by its named cause, no slot, the cohort unchanged."""
    moved = OPEN_KO + timedelta(seconds=1, milliseconds=300)
    _db(SUB_59, utc_date=moved)
    _recopy(conf_sub)
    L = _cpre(conf_sub)
    assert any("window members now later than the opening: 1" in x for x in L)
    assert "the read REFUSES before the reservation" in L[-1] and f"match {SUB_59} at {_iso(moved)}" in L[-1]
    with pytest.raises(lr.ReadRefused, match=f"{SUB_59} .*nothing reserved"):
        _crun(conf_sub, "0" * 64)
    _nothing(conf_sub)
    ledger(_rule(reg.get(EID, reg.LEDGER), SUB_59, moved))      # the kickoff to the second, as the refusal prints it
    e = reg.get(EID, reg.LEDGER)
    assert e[lw.RULED_FIELD][-1]["kickoff"] == _iso(moved) != moved.isoformat()
    sha, pages, w, stored = lr.load("SA", e, conf_sub["copy"], conf_sub["exports"], conf_sub["digest"], NOW,
                                    confirmation=True)
    later = [mid for mid, _ in conf_sub["later"]]
    assert w[lw.MEMBERS_AFTER] == [] and (SUB_59, moved, lw.RULED) in w[lw.TOOK_NO_SLOT]
    assert w["members"] == later[:60] and lc.backstop(e, w) is None
    res = _crun(conf_sub, _cfp(_cpre(conf_sub)))
    assert [it["match_id"] for it in res["audit"][lw.RULED]] == [SUB_59] and SUB_59 not in res["members_in_order"]
    assert lc.record("SA", res, RULING)["confirmation"]["outcome"] in lw.CONFIRMATION_OUTCOMES


def test_gap_the_windows_ruled_kickoff_check_is_unchanged_exact():
    """The window's read (no opening) keeps its exact kickoff check (pre-existing): an item written to the second does
    not match a sub-second stored kickoff there; the confirmation's (cut) does."""
    class M:
        id, utc_date = 7, OPEN_KO + timedelta(milliseconds=300)
    item = {7: {"match_id": 7, "kickoff": OPEN_KO, "cause": "c", "ruling": "r"}}
    with pytest.raises(lw.WindowRefused, match="the ruling is for another kickoff"):
        lw.apply_ruled("SA", item, [M()], AT)
    lw.apply_ruled("SA", item, [M()], AT, cut=True)


def test_gap_the_finding_is_never_called_re_dated_as_a_fact(conf):
    """447 C1(d)'s finding is "a game before the opening in the window's order that the run record does not account
    for": re-dated, or (at sub-second precision) in the opening's second with an id not above the opening's. The
    console says so, on the preflight's lines and the read's, and never heads it 're-dated'."""
    t = conf["teams"]
    _db(TIE_ID, utc_date=OPEN_KO + timedelta(hours=2))
    sub = OPEN_KO + timedelta(milliseconds=500)
    _game(1995, "SA", sub, (t[8], t[9]))                            # never re-dated: in the opening's second, id < 2059
    _legs(1995, sub)
    _export("SA", export_dir=str(conf["exports"]))
    _recopy(conf)
    L = _cpre(conf)
    head = next(x for x in L if "(447 C1(d)): 1" in x)
    assert head.startswith(FINDINGS + "1") and "re-dated" not in head.split("(447 C1(d))")[0]
    assert ("game kicking off after declared_at and before the opening in the window's order that the run record "
            "does not account for: re-dated, or at sub-second precision in the opening's second with an id not above "
            "the opening's; a FINDING, never a member") in head
    assert any(x.startswith("    - FINDING match 1995 · kickoff") for x in L)
    op = next(x for x in L if x.startswith("  the opening (the run record's, 447 C1)"))
    assert "findings, not accounted for by the run record (447 C1(d)) 1" in op and "re-dated" not in op
    res = _crun(conf, _cfp(L))
    line = next(x for x in lc.run_lines(res) if "(447 C1(d))" in x)
    assert line.startswith("  not accounted for by the run record, in neither cohort (447 C1(d)): 1 finding(s)")
    assert "re-dated" not in line.split("·")[0]


def test_gap_a_no_slot_game_in_the_openings_second_is_never_reached_again(conf_noslot):
    """A game the window's loop reached and gave no slot (the run record's took_no_slot) is compared with the opening
    by the member rule too: in the opening's second it is before the opening, whatever its id, so the confirmation
    never reaches it again (never a member, never in its took-no-slot list, never a finding). Re-dated to a later
    second it is after the opening and may enter by its real kickoff (448 item 1(e))."""
    r = conf_noslot["window_res"]
    assert NOSLOT_SUB in {x["match_id"] for x in r["took_no_slot"]} and NOSLOT_SUB not in r["members_in_order"]
    e = reg.get(EID, reg.LEDGER)
    sha, pages, w, stored = lr.load("SA", e, conf_noslot["copy"], conf_noslot["exports"], conf_noslot["digest"], NOW,
                                    confirmation=True)
    assert NOSLOT_SUB not in w["members"]
    assert NOSLOT_SUB not in {x[0] for x in w[lw.TOOK_NO_SLOT]}
    assert w[lw.REDATED] == [] and w[lw.REDATED_NO_SLOT] == [] and w[lw.MEMBERS_AFTER] == []
    assert w["state"] == "ready" and w[lw.FIRST_MEMBER][0] == TIE_ID and lc.backstop(e, w) is None
    op = (OPEN_KO, OPEN_ID)
    assert not lw.after_opening(OPEN_KO + timedelta(milliseconds=300), NOSLOT_SUB, op, True)
    assert lw.after_opening(OPEN_KO + timedelta(milliseconds=1300), NOSLOT_SUB, op, True)


@pytest.mark.parametrize("cause", ["missing", "", "   ", 5, None])
def test_codex_a_no_slot_item_without_a_text_cause_refuses_the_basis(conf, cause):
    """Codex on #1153: the run record's took_no_slot is {match_id, kickoff, cause}; an item whose cause is absent,
    empty or not text is not a readable account, so the basis refuses (law 4), never trusting the id as accounted."""
    import copy
    e = copy.deepcopy(reg.get(EID, reg.LEDGER))
    item = e["run"]["result"]["took_no_slot"][0]
    if cause == "missing":
        item.pop("cause")
    else:
        item["cause"] = cause
    with pytest.raises(lw.WindowRefused, match=r"each cause present text"):
        lw.confirmation_basis(e)
    assert lw.confirmation_basis(reg.get(EID, reg.LEDGER))["no_slot"]                 # the stored record still reads


def test_556_a_whole_second_world_prints_a_subsecond_count_of_0(conf):
    """ARCHITECT 2026-11-26, addendum 556 item 2: "the preflight and the read each print how many games of the
    league's season carry a stored kickoff with a fraction of a second. A count, expected 0, refusing nothing." """
    L = _cpre(conf)
    assert any("games with a stored kickoff carrying a fraction of a second: 0 (addendum 556 item 2" in x for x in L)


def test_556_the_preflight_and_the_read_print_the_subsecond_count_and_store_it_nowhere(conf_sub):
    """The sub-second world (SUB_59 at +200 ms, 2059 at +500 ms, 3000 at +700 ms): the preflight and the read (its
    echo) print 3, the read is not refused by it, and neither the result nor the ledger holds it."""
    Ls = _cpre(conf_sub)
    assert any("games with a stored kickoff carrying a fraction of a second: 3 (addendum 556 item 2" in x for x in Ls)
    seen = []
    res = lc.run("SA", str(conf_sub["copy"]), str(conf_sub["exports"]), conf_sub["digest"], WORD, _cfp(Ls), RULING,
                 now=NOW, no_fetch=False, echo=seen.append)
    assert any("fraction of a second: 3 (addendum 556 item 2: expected 0, refusing nothing)" in x for x in seen)
    assert "subsecond" not in json.dumps(res) and "fraction of a second" not in json.dumps(res)
    rec = lc.record("SA", res, RULING)
    assert "subsecond" not in json.dumps(rec) and "fraction of a second" not in json.dumps(rec)
