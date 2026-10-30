"""ARCHITECT 2026-10-30 09:30 ET, addendum 178 (R1-R4, R8; PR ORDER item 2): the leagues' cohort reader
(src/walters/leagues_window.py, scripts/leagues_window.py) and its window fence, on a throwaway SQLite file
(tests/test_record_vs_close.py iso_db) and a tmp registry (registry.LEDGER monkeypatched: the real
docs/registry/experiments.json is never written). Pins every membership branch, the strict-after instant, the order by
actual kickoff, the 60-stop, accruing / waiting / ready, NOT DECLARED, the refusals, the counts-only print, the scoring
path (strict, unrounded, a tie rejects; the audit of stored rows) and the fence on every other reader."""
from __future__ import annotations

import importlib.util
import itertools
import json
import math
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.db.schema import MatchStatus, Sport
from src.walters import leagues_window as lw
from src.walters import paper
from src.walters import registry as reg
from src.walters import soccer_expansion as sx
from tests.test_close_record_paper import _kal
from tests.test_close_record_three_way import A
from tests.test_record_vs_close import iso_db  # noqa: F401  (a fixture: a throwaway SQLite, cwd = tmp_path)

pytestmark = pytest.mark.usefixtures("iso_db")

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("leagues_window_script", ROOT / "scripts" / "leagues_window.py")
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)

SEASON = "2026/27"
AT = datetime(2026, 11, 6, 14, 30)                    # the declaration's instant (R3), naive UTC
AT_TEXT = "2026-11-06T14:30:00Z"
NOW = datetime(2026, 12, 20, 12, 0)                   # the read clock
FROZEN = {"production_version": "v22", "rho": -0.1, "elo_goal_coeff": 0.0008}
RUN = {"id": sx.EID, "run": {"result": dict(FROZEN)}, "verdict": {"verdict": "PASS"}}
REG = "Regular Season - 1"
FORBIDDEN = re.compile(r"log-loss|log loss|logloss|probab|\bhits?\b|%", re.IGNORECASE)


# ------------------------------------------------------------------------------------------- fixtures --

@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """write(*entries): a tmp registry holding the soccer-expansion-v1 run record and the given entries."""
    path = tmp_path / "experiments.json"

    def write(*entries, run=RUN):
        path.write_text(json.dumps([run, *entries]))
    monkeypatch.setattr(reg, "LEDGER", str(path))
    write()
    return write


def decl(code, at=AT_TEXT, constants=FROZEN, **kw):
    e = {"id": lw.DECLARATION_IDS[code], "competition": code, "declared_at": at, "frozen_constants": constants,
         "verdict": None}
    e.update(kw)
    return e


def _comps():
    from src.db.database import session_scope
    from src.db.schema import Competition
    with session_scope() as s:
        for code in paper.LEAGUES:
            s.add(Competition(sport=Sport.SOCCER, code=code, name=code, area="X", type="LEAGUE"))


def _teams(code, n=10, tag=""):
    from src.db.database import session_scope
    from src.db.schema import Team
    with session_scope() as s:
        ts = [Team(sport=Sport.SOCCER, name=f"{code}{tag} T{i}") for i in range(n)]
        s.add_all(ts)
        s.flush()
        return [t.id for t in ts]


def _game(mid, code, ko, teams, status=MatchStatus.FINISHED, hs=1, as_=0, raw="FT", s90=True, stage=REG,
          season=SEASON):
    from src.db.database import session_scope
    from src.db.schema import Competition, Match
    fin = status == MatchStatus.FINISHED
    with session_scope() as s:
        c = s.query(Competition).filter_by(code=code).one()
        s.add(Match(id=mid, sport=Sport.SOCCER, competition_id=c.id, season=season, utc_date=ko, status=status,
                    stage=stage, home_team_id=teams[0], away_team_id=teams[1],
                    home_score=hs if fin else None, away_score=as_ if fin else None,
                    home_score_90=hs if fin and s90 else None, away_score_90=as_ if fin and s90 else None,
                    status_raw=raw if fin else None))


def _legs(mid, ko, quotes=A):
    for sel, (bid, ask) in quotes.items():
        _kal(mid, sel, bid, ask, ko - timedelta(minutes=30), market="1X2")


def _priors(code, teams, n=40, base=1000, start=datetime(2026, 8, 15, 15, 0)):
    """n finished regular-round games before the instant, each ordered pair of the clubs once, varied scores."""
    pairs = [p for p in itertools.permutations(teams, 2)]
    for i in range(n):
        _game(base + i, code, start + timedelta(hours=12 * i), pairs[i], hs=i % 3, as_=(i // 3) % 2)
    return pairs[n:]


def _members(code, teams, n, base, start, legs=True, pairs=None):
    """n finished games after the instant with a close, each a member when priors exist; kickoffs 6 hours apart."""
    pairs = pairs or [p for p in itertools.permutations(teams, 2)]
    out = []
    for i in range(n):
        ko = start + timedelta(hours=6 * i)
        _game(base + i, code, ko, pairs[i % len(pairs)], hs=(i * 7) % 3, as_=(i * 5) % 2)
        if legs:
            _legs(base + i, ko)
        out.append((base + i, ko))
    return out


def _read(code):
    return lw.read((code,), now=NOW)[code]


# --------------------------------------------------------------------------------------- the declaration --

def test_no_entry_reads_not_declared_and_prints_only_that(ledger):
    _comps()
    res = lw.read(paper.LEAGUES, now=NOW)
    assert all(not w["declared"] for w in res.values())
    out = lw.lines(res, NOW)
    assert out[1:] == [f"{c} · NOT DECLARED (no registry entry {lw.DECLARATION_IDS[c]}): no window"
                       for c in paper.LEAGUES]
    assert lw.DECLARATION_IDS == {"SA": "leagues-sa-v1", "BL1": "leagues-bl1-v1", "FL1": "leagues-fl1-v1",
                                  "ELC": "leagues-elc-v1"}


def test_the_real_registry_holds_no_league_declaration_yet():
    """Today: NOT DECLARED everywhere, so the PRE-DECLARATION fence stands at its constant cut (addendum 181 item
    1(b)); every other competition and every other season is never fenced."""
    assert lw.PRE_DECLARATION_CUT == datetime(2026, 10, 30, 15, 0)
    for code in paper.LEAGUES:
        assert reg.get(lw.DECLARATION_IDS[code]) is None
        assert lw.fence_cutoff(code, SEASON) == lw.PRE_DECLARATION_CUT
        assert lw.fence_cutoff(code, None) == lw.PRE_DECLARATION_CUT
        assert lw.fence_cutoff(code, "2025/26") is None
    for code in ("PL", "PD", "NFL", "CL", "UNL", None):
        assert lw.fence_cutoff(code, SEASON) is None and lw.fence_cutoff(code) is None


@pytest.mark.parametrize("entry, why", [
    (decl("SA", at=None), "no declared_at as a UTC instant"),
    (decl("SA", at="2026-11-06"), "a date is never the instant"),
    (decl("SA", at="2026-11-06T09:30:00"), "no declared_at as a UTC instant"),            # no zone stated
    (decl("SA", at="2026-11-06T09:30:00-05:00"), "no declared_at as a UTC instant"),      # ET, not UTC
    (decl("SA", constants=None), "holds no frozen_constants"),
    (decl("SA", constants={"production_version": "v22", "rho": -0.1}), "holds no frozen_constants"),
    (decl("SA", constants={**FROZEN, "rho": -0.09}), "differ from the soccer-expansion-v1 run record's"),
    (decl("SA", constants={**FROZEN, "elo_goal_coeff": 0.00081}), "differ from the soccer-expansion-v1 run"),
    (decl("SA", constants={**FROZEN, "production_version": "v23"}), "differ from the soccer-expansion-v1 run"),
])
def test_a_declaration_without_its_instant_or_its_frozen_constants_is_refused(ledger, tmp_path, monkeypatch, capsys,
                                                                              entry, why):
    _comps()
    ledger(entry)
    w = _read("SA")
    assert why in w["refused"]
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'iso.db'}")
    assert script.main([]) == 2
    out = capsys.readouterr().out
    assert "SA · REFUSED (leagues-sa-v1): " in out and "BL1 · NOT DECLARED" in out


def test_a_run_record_without_its_constants_refuses_every_declared_league(ledger):
    _comps()
    ledger(decl("BL1"), run={"id": sx.EID, "run": None})
    assert "has no run record holding" in _read("BL1")["refused"]
    assert not _read("SA")["declared"]


def test_the_constants_are_the_run_records_never_the_production_models(ledger, monkeypatch):
    from src.walters import leagues_candidate as lc
    monkeypatch.setattr(lc, "production_poisson", lambda: ("v99", -0.2, 0.002))
    assert lw.run_record_constants() == FROZEN


def test_an_unplaceable_stage_label_refuses_as_parity_does(ledger):
    _comps()
    ledger(decl("FL1"))
    t = _teams("FL1")
    _game(1, "FL1", AT - timedelta(days=3), (t[0], t[1]), stage="Group A")
    assert "cannot place, kicking off at or before the read clock (F3" in _read("FL1")["refused"]


def test_an_unplaceable_label_refuses_only_at_or_before_the_60th_as_unplaced_through_reads_it(ledger):
    """La Liga's precedent (soccer_expansion.unplaced_through): a label further ahead than the read clock while
    accruing, or than the 60th member once 60 are in, is read when the window reaches it; one at or before refuses."""
    _comps()
    ledger(decl("SA"))
    t = _teams("SA")
    _priors("SA", t)
    got = _members("SA", t, 60, 2000, AT + timedelta(hours=1))
    _game(2950, "SA", NOW + timedelta(days=30), (t[0], t[1]), MatchStatus.SCHEDULED, stage="Group A")
    w = _read("SA")
    assert w["state"] == "ready" and "refused" not in w
    _game(2951, "SA", got[59][1] - timedelta(minutes=1), (t[2], t[3]), MatchStatus.SCHEDULED, stage="Group B")
    assert "kicking off at or before the 60th member (F3" in _read("SA")["refused"]


# ---------------------------------------------------------------------------------------- membership --

def test_every_membership_branch_is_counted_by_cause(ledger):
    _comps()
    ledger(decl("SA"))
    t = _teams("SA")
    rest = _priors("SA", t)
    new = _teams("SA", 2, tag="new")
    ko = AT + timedelta(days=1)

    def at(h):
        return ko + timedelta(hours=h)
    _game(100, "SA", AT, rest[0])                                   # kickoff == the instant: out (strictly after)
    _legs(100, AT)
    _game(101, "SA", AT - timedelta(hours=2), rest[1])               # same day, earlier: out
    _legs(101, AT - timedelta(hours=2))
    _game(110, "SA", at(0), rest[2])
    _legs(110, at(0))                                               # MEMBER
    _game(111, "SA", at(1), rest[3], MatchStatus.CANCELLED)
    _game(112, "SA", at(2), rest[4], MatchStatus.STALE_ORPHAN, stage=None)
    _game(113, "SA", at(3), rest[5], MatchStatus.POSTPONED)
    _game(114, "SA", at(4), rest[6], stage="Promotion Play-offs - Semi-finals")
    _legs(114, at(4))
    _game(115, "SA", at(5), rest[7], raw="AWD", hs=3, as_=0)
    _legs(115, at(5))
    _game(116, "SA", at(6), rest[8])                                # no capture
    _game(117, "SA", at(7), rest[9])
    _legs(117, at(7), {"HOME": (0.45, 0.46), "AWAY": (0.27, 0.28)})  # a leg missing
    _game(118, "SA", at(8), rest[10], raw="AET", s90=False)          # finished, no 90-minute result
    _legs(118, at(8))
    _game(119, "SA", at(9), rest[11], MatchStatus.LIVE)
    _game(120, "SA", at(10), rest[12], MatchStatus.SCHEDULED)        # kickoff past at the clock: un-ingested
    _game(121, "SA", at(11), (new[0], new[1]))                       # two clubs never seen: no strength
    _legs(121, at(11))
    _game(122, "SA", NOW + timedelta(days=1), rest[13], MatchStatus.SCHEDULED)   # to come
    w = _read("SA")
    assert w["members"] == [110] and w["n"] == 1 and w["state"] == "accruing"
    assert w["at_or_before"] == 42                                   # 40 priors + the two at / before the instant
    assert dict(w["excluded"]) == {"cancelled": 1, "stale_orphan": 1, "not_regular": 1, "awarded": 1,
                                   "unpriced_none": 1, "unpriced_incomplete": 1, "no_strength": 1}
    assert dict(w["pending"]) == {"no_result_90": 1, "live": 1, "uningested": 1}
    assert (w["to_come"], w["not_placed"]) == (1, 1)
    assert (w["stored_present"], w["stored_missing"]) == (0, 1)


def test_below_min_prior_is_excluded_and_takes_no_slot(ledger):
    _comps()
    ledger(decl("BL1"))
    t = _teams("BL1")
    _priors("BL1", t, n=5)
    _members("BL1", t, 2, 200, AT + timedelta(days=1))
    w = _read("BL1")
    assert w["n"] == 0 and dict(w["excluded"]) == {"below_min_prior": 2}


def test_mismatched_legs_are_excluded_by_cause(ledger, monkeypatch):
    _comps()
    ledger(decl("SA"))
    t = _teams("SA")
    _priors("SA", t)
    _members("SA", t, 2, 300, AT + timedelta(days=1))
    from src.walters import kalshi_legs
    monkeypatch.setattr(kalshi_legs, "mismatched", lambda conn, ids: {300: ["E1", "E2"]})
    w = _read("SA")
    assert w["members"] == [301] and dict(w["excluded"]) == {"mismatched": 1}


def test_order_is_the_actual_stored_kickoff_then_id_with_a_redated_game(ledger):
    """302 was first set before the instant and re-dated after it: it counts by its ACTUAL kickoff; 301 was re-dated
    from after the instant to before it: out. Equal kickoffs order by id."""
    _comps()
    ledger(decl("ELC"))
    t = _teams("ELC")
    rest = _priors("ELC", t)
    k = AT + timedelta(days=2)
    _game(305, "ELC", k + timedelta(hours=3), rest[0])
    _game(302, "ELC", k + timedelta(hours=5), rest[1])               # re-dated: its stored kickoff is the latest
    _game(301, "ELC", AT - timedelta(days=1), rest[2])               # re-dated to before the instant
    _game(309, "ELC", k, rest[3])
    _game(308, "ELC", k, rest[4])                                    # the same kickoff as 309: id first
    for mid, ko in ((305, k + timedelta(hours=3)), (302, k + timedelta(hours=5)), (301, AT - timedelta(days=1)),
                    (309, k), (308, k)):
        _legs(mid, ko)
    assert _read("ELC")["members"] == [308, 309, 305, 302]


def test_counting_stops_at_the_60th_member_and_the_window_is_ready(ledger):
    _comps()
    ledger(decl("SA"))
    t = _teams("SA")
    _priors("SA", t)
    got = _members("SA", t, 63, 2000, AT + timedelta(hours=1))
    _game(2999, "SA", NOW - timedelta(hours=1), (t[0], t[1]), MatchStatus.SCHEDULED)   # after the 60th: uncounted
    w = _read("SA")
    assert w["members"] == [mid for mid, _ in got[:60]] and w["n"] == 60 and w["state"] == "ready"
    assert not w["pending"] and not w["excluded"] and w["to_come"] == 0


@pytest.mark.parametrize("status, kind", [(MatchStatus.SCHEDULED, "uningested"), (MatchStatus.LIVE, "live")])
def test_a_game_before_the_60th_not_final_makes_the_read_wait(ledger, status, kind):
    _comps()
    ledger(decl("SA"))
    t = _teams("SA")
    _priors("SA", t)
    got = _members("SA", t, 60, 2000, AT + timedelta(hours=1))
    _game(2900, "SA", got[10][1] + timedelta(minutes=1), (t[2], t[5]), status)
    w = _read("SA")
    assert w["n"] == 60 and w["state"] == "waiting" and dict(w["pending"]) == {kind: 1}
    assert any("WAITING" in x for x in lw.lines({"SA": w}, NOW))


@pytest.mark.parametrize("status", [MatchStatus.LIVE, MatchStatus.SCHEDULED, MatchStatus.FINISHED])
def test_a_game_at_or_before_the_instant_not_final_makes_the_read_wait(ledger, status):
    """R1 + R4: a regular-round game just before the instant is never a member, but every member's walk reads it once
    final: LIVE, SCHEDULED past its kickoff, or FINISHED with no score stored, it is PENDING and the read waits."""
    from src.db.database import session_scope
    from src.db.schema import Match
    _comps()
    ledger(decl("SA"))
    t = _teams("SA")
    _priors("SA", t)
    _members("SA", t, 60, 2000, AT + timedelta(hours=1))
    _game(2902, "SA", AT - timedelta(hours=1), (t[2], t[5]), status)
    if status == MatchStatus.FINISHED:
        with session_scope() as s:
            m = s.get(Match, 2902)
            m.home_score = m.away_score = m.home_score_90 = m.away_score_90 = None
    w = _read("SA")
    assert w["n"] == 60 and w["state"] == "waiting" and dict(w["pending"]) == {"before_instant": 1}
    assert w["at_or_before"] == 40
    out = lw.lines({"SA": w}, NOW)
    assert any("not final 1 (pending, below)" in x for x in out) and any("WAITING" in x for x in out)


def test_a_postponed_game_at_or_before_the_instant_is_never_called_out_of_the_window(ledger):
    """R4: a postponed game is placed by its ACTUAL kickoff, so one stored at or before the instant is counted apart,
    never as "never in the window"; a play-off game before the instant is never walked and never blocks."""
    _comps()
    ledger(decl("SA"))
    t = _teams("SA")
    _priors("SA", t)
    _members("SA", t, 60, 2000, AT + timedelta(hours=1))
    _game(2903, "SA", AT - timedelta(days=2), (t[2], t[5]), MatchStatus.POSTPONED)
    _game(2904, "SA", AT - timedelta(hours=3), (t[3], t[6]), MatchStatus.LIVE, stage="Relegation Play-offs - Final")
    w = _read("SA")
    assert (w["at_or_before"], w["postponed_before"], w["state"]) == (41, 1, "ready") and not w["pending"]
    head = next(x for x in lw.lines({"SA": w}, NOW) if "at or before the instant" in x)
    assert "never walked 41 (never in the window) · postponed 1 (postponed: placed by its actual kickoff" in head


def test_181_3_a_finished_row_with_no_raw_code_and_both_scores_is_a_member_scored_on_its_stored_score(ledger):
    """Addendum 181 item 3: C1 wins. A FINISHED row with no raw status code and both scores stored is a MEMBER, scored
    on its stored score, listed as C2 lists it; `no_raw_code` is no longer a PENDING kind."""
    from src.db.database import session_scope
    from src.db.schema import Match
    assert "no_raw_code" not in {k for k, _ in lw.PENDING}
    _comps()
    ledger(decl("SA"))
    t = _teams("SA")
    _priors("SA", t)
    _members("SA", t, 2, 2000, AT + timedelta(hours=1))
    _game(2905, "SA", AT + timedelta(hours=2), (t[2], t[5]), raw=None, s90=False, hs=0, as_=2)
    _legs(2905, AT + timedelta(hours=2))
    w = _read("SA")
    assert 2905 in w["members"] and not w["pending"] and w["n"] == 3
    assert len(w["no_raw_code_members"]) == 1 and w["no_raw_code_members"][0].startswith("2905 · ")
    assert "raw NULL · score 0-2 · 90' not stored" in w["no_raw_code_members"][0]
    out = lw.lines({"SA": w}, NOW)
    assert any("members with no raw status code 1 (scored on the stored score, C1" in x for x in out)
    assert any(x.startswith("    - 2905 · ") for x in out)
    assert not FORBIDDEN.search("\n".join(out))
    with session_scope() as s:
        assert lw.result_of(s.get(Match, 2905)) == "A"                 # its stored score is its result
        s.rollback()


def test_181_3_pending_is_a_finished_row_with_no_usable_result_only(ledger):
    """R4's PENDING (181 item 3): no scores stored, or a non-FT code with no 90-minute score; the read waits."""
    from src.db.database import session_scope
    from src.db.schema import Match
    _comps()
    ledger(decl("SA"))
    t = _teams("SA")
    _priors("SA", t)
    _members("SA", t, 2, 2000, AT + timedelta(hours=1))
    _game(2910, "SA", AT + timedelta(hours=2), (t[2], t[5]), raw=None, s90=False)
    _game(2911, "SA", AT + timedelta(hours=3), (t[3], t[6]), raw="PEN", s90=False)
    _game(2912, "SA", AT + timedelta(hours=4), (t[4], t[7]), raw="AET", hs=2, as_=1)   # a 90' score stored: member
    for mid, h in ((2910, 2), (2911, 3), (2912, 4)):
        _legs(mid, AT + timedelta(hours=h))
    with session_scope() as s:
        m = s.get(Match, 2910)
        m.home_score = m.away_score = None                              # no score stored, no raw code
    w = _read("SA")
    assert dict(w["pending"]) == {"no_result_90": 2} and 2912 in w["members"]
    assert 2910 not in w["members"] and 2911 not in w["members"]


def test_181_2_an_awarded_row_is_neither_walked_nor_scored_and_is_listed_as_released(ledger):
    """Addendum 181 item 2: La Liga's ONE predicate (soccer_expansion.unscoreable) governs the whole path. An AWD /
    WO row is excluded as a member and RELEASED from every member's walk (no Elo or prior update, whatever scores it
    carries): predict_as_of equals the walk with the row absent; it is counted and listed (`awarded_released`)."""
    from src.db.database import session_scope
    from src.db.schema import Match
    from src.walters import leagues_candidate as lc
    _comps()
    ledger(decl("SA"))
    t = _teams("SA")
    _priors("SA", t)
    _game(2906, "SA", AT - timedelta(hours=2), (t[2], t[5]), raw="AWD", hs=3, as_=0)       # a prior, awarded
    _game(2907, "SA", AT + timedelta(minutes=30), (t[3], t[6]), raw="WO", hs=3, as_=0)    # a window game, awarded
    _legs(2907, AT + timedelta(minutes=30))
    got = _members("SA", t, 2, 2000, AT + timedelta(hours=1))
    w = _read("SA")
    assert dict(w["excluded"]) == {"awarded": 1} and w["n"] == 2 and not w["pending"]
    assert [x.split(" · ")[0] for x in w["awarded_released"]] == ["2906", "2907"]
    assert "AWD · score 3-0" in w["awarded_released"][0]
    out = lw.lines({"SA": w}, NOW)
    assert any("AWD / WO rows released from the members' walk 2 (neither scored nor walked" in x for x in out)
    with session_scope() as s:
        rows = lc._season_rows(s, "SA", SEASON)
        m = s.get(Match, got[1][0])
        with_awd, _ = lc.predict_as_of(rows, m, -0.1, 0.0008)
        without, _ = lc.predict_as_of([r for r in rows if r.id not in (2906, 2907)], m, -0.1, 0.0008)
        s.rollback()
    assert (with_awd.p_home, with_awd.p_draw, with_awd.p_away) == (without.p_home, without.p_draw, without.p_away)


def test_181_2_a_non_ft_prior_with_a_90_minute_score_is_walked_on_it(ledger):
    """The one predicate: an AET / PEN prior with a stored 90-minute score is walked on the 90-minute score, never
    the after-extra-time one: predict_as_of equals the walk with that row stored as FT at its 90-minute score."""
    from src.db.database import session_scope
    from src.db.schema import Match
    from src.walters import leagues_candidate as lc
    _comps()
    ledger(decl("SA"))
    t = _teams("SA")
    _priors("SA", t)
    _game(2908, "SA", AT - timedelta(hours=2), (t[2], t[5]), raw="AET", hs=1, as_=1)
    with session_scope() as s:
        s.get(Match, 2908).home_score = 3                               # after extra time 3-1; 90 minutes 1-1
    got = _members("SA", t, 2, 2000, AT + timedelta(hours=1))
    assert _read("SA")["state"] == "accruing" and not _read("SA")["pending"]

    def p():
        with session_scope() as s:
            rows = lc._season_rows(s, "SA", SEASON)
            q, _ = lc.predict_as_of(rows, s.get(Match, got[1][0]), -0.1, 0.0008)
            s.rollback()
        return q.p_home, q.p_draw, q.p_away
    aet = p()
    with session_scope() as s:
        m = s.get(Match, 2908)
        m.home_score, m.status_raw = 1, "FT"
    assert aet == p()


def test_181_2_parity_is_the_confirmation_walk_and_equal_with_released_rows(ledger):
    """158 item 2(a)'s "the gate's walk" is the confirmation walk with the predicate (181 item 2): with an AWD prior
    and an AET prior that has a 90-minute score, the shadow path and the gate path agree row for row, and the AWD
    row is priced by neither (counted `released`)."""
    from src.db.database import session_scope
    from src.db.schema import Match
    from src.walters import leagues_candidate as lc
    _comps()
    ledger(decl("SA", verdict={"verdict": "PASS"}))                    # no fence: every game compared
    t = _teams("SA")
    _priors("SA", t, n=45)
    _game(2920, "SA", datetime(2026, 9, 20, 15, 0), (t[2], t[5]), raw="AWD", hs=3, as_=0)
    _game(2921, "SA", datetime(2026, 9, 21, 15, 0), (t[3], t[6]), raw="AET", hs=1, as_=1)
    with session_scope() as s:
        s.get(Match, 2921).home_score = 2
    _members("SA", t, 5, 2000, AT + timedelta(hours=1))
    p = lc.parity("SA", -0.1, 0.0008, season=SEASON, now=NOW)
    assert p["unequal"] == 0 and not p["shadow_only"] and not p["gate_only"] and p["released"] == 1
    ids = {r["match_id"] for r in p["rows"]}
    assert 2920 not in ids and 2921 in ids and {2000, 2004} <= ids
    assert "released 1 (the one predicate" in lc.parity_lines(p, rows=False)[0]


def test_the_pending_line_carries_r2s_list_scheduled_live_un_ingested(ledger):
    _comps()
    ledger(decl("SA"))
    t = _teams("SA")
    rest = _priors("SA", t)
    _game(2907, "SA", AT + timedelta(hours=1), rest[0], MatchStatus.LIVE)
    _game(2908, "SA", NOW + timedelta(days=2), rest[1], MatchStatus.SCHEDULED)
    _game(2909, "SA", NOW + timedelta(days=3), rest[2], MatchStatus.SCHEDULED)
    line = next(x for x in lw.lines({"SA": _read("SA")}, NOW) if "pending (the read waits" in x)
    assert line.endswith("pending (the read waits for them): scheduled 2 · LIVE 1 · un-ingested 0")


def test_the_reader_opens_the_database_read_only(ledger, monkeypatch):
    """read() and score() use readonly_scope (mode=ro, no connect hook, no commit), never session_scope."""
    from src.db import database
    _comps()
    ledger(decl("SA"))
    t = _teams("SA")
    _priors("SA", t)
    _members("SA", t, 60, 2000, AT + timedelta(hours=1))
    monkeypatch.setattr(database, "session_scope", lambda: pytest.fail("a writable session"))
    w = _read("SA")
    assert w["state"] == "ready"
    assert lw.score(w)["n"] == 60


def test_a_finished_game_with_no_90_minute_result_before_the_60th_makes_the_read_wait(ledger):
    _comps()
    ledger(decl("SA"))
    t = _teams("SA")
    _priors("SA", t)
    got = _members("SA", t, 60, 2000, AT + timedelta(hours=1))
    _game(2901, "SA", got[3][1] + timedelta(minutes=1), (t[1], t[7]), raw="PEN", s90=False)
    _legs(2901, got[3][1] + timedelta(minutes=1))
    w = _read("SA")
    assert w["state"] == "waiting" and dict(w["pending"]) == {"no_result_90": 1}


# ------------------------------------------------------------------------------------ the counts-only print --

def test_the_print_is_counts_only_at_every_state_and_ready_says_the_read_is_item_5s(ledger, tmp_path, monkeypatch,
                                                                                   capsys):
    _comps()
    ledger(decl("SA"), decl("BL1"))
    t = _teams("SA")
    _priors("SA", t)
    _members("SA", t, 60, 2000, AT + timedelta(hours=1))
    tb = _teams("BL1")
    _priors("BL1", tb, base=5000)
    _members("BL1", tb, 5, 4000, AT + timedelta(hours=1))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'iso.db'}")
    assert script.main([]) == 0
    out = capsys.readouterr().out
    assert not FORBIDDEN.search(out), FORBIDDEN.search(out)
    assert ("SA · declared_at 2026-11-06T14:30:00Z (leagues-sa-v1; frozen v22, rho -0.1, Elo goal coefficient 0.0008, "
            "the run record's) · members 60 of 60 · state ready") in out
    assert "The one read is addendum 178 PR ORDER item 5's PR; nothing is scored here" in out
    assert "BL1 · declared_at 2026-11-06T14:30:00Z" in out and "members 5 of 60 · state accruing" in out
    assert "present 0 · missing 5 (no stored rows: the export that writes them is a later PR)" in out
    assert "SA · NOT DECLARED" not in out
    assert "FL1 · NOT DECLARED (no registry entry leagues-fl1-v1): no window" in out


def test_the_script_refuses_a_missing_database_and_never_creates_one(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'absent.db'}")
    assert script.main([]) == 2
    assert "never creates one" in capsys.readouterr().out
    assert not (tmp_path / "absent.db").exists()


def test_the_reader_never_calls_the_scoring_path(ledger, tmp_path, monkeypatch):
    _comps()
    ledger(decl("SA"))
    t = _teams("SA")
    _priors("SA", t)
    _members("SA", t, 60, 2000, AT + timedelta(hours=1))
    monkeypatch.setattr(lw, "score", lambda *a, **k: pytest.fail("the reader scored"))
    monkeypatch.setattr(lw, "aggregate", lambda *a, **k: pytest.fail("the reader scored"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'iso.db'}")
    assert script.main([]) == 0


# ----------------------------------------------------------------------------------------- the scoring path --

def test_verdict_strict_less_passes_and_an_exact_tie_rejects_unrounded():
    assert lw.verdict_of(0.95, 0.96) == "PASS"
    assert lw.verdict_of(0.96, 0.96) == "REJECT"                     # a tie is a rejection
    assert lw.verdict_of(0.97, 0.96) == "REJECT"
    assert lw.verdict_of(1.0 - 1e-15, 1.0) == "PASS"                 # unrounded: no tolerance
    tie = lw.aggregate([(0.5, 0.5), (0.25, 0.25)])
    assert tie["verdict"] == "REJECT" and tie["ll_candidate"] == tie["ll_close"]
    a = lw.aggregate([(0.5000001, 0.5), (0.25, 0.25)])
    assert a["verdict"] == "PASS" and a["ll_close"] - a["ll_candidate"] < 1e-7
    assert a["ll_candidate"] == (-math.log(0.5000001) - math.log(0.25)) / 2       # unrounded, exactly
    with pytest.raises(lw.WindowRefused):
        lw.aggregate([])


def test_score_recomputes_both_arms_on_the_60_and_refuses_before_ready(ledger):
    from src.db.database import session_scope
    from src.db.schema import Match
    from src.walters import leagues_candidate as lc
    from src.walters.intl_shadow import OUTCOME_SIDE, result_90
    from src.walters.vs_close import log_loss
    _comps()
    ledger(decl("SA"))
    t = _teams("SA")
    _priors("SA", t)
    _members("SA", t, 60, 2000, AT + timedelta(hours=1))
    w = _read("SA")
    r = lw.score(w)
    cand, close = [], []
    with session_scope() as s:
        rows = lc._season_rows(s, "SA", SEASON)
        snaps = paper._kalshi_snaps(s, w["members"])
        for i in w["members"]:
            m = s.get(Match, i)
            p, _ = lc.predict_as_of(rows, m, -0.1, 0.0008)
            res = result_90(m)
            cand.append(log_loss({"H": p.p_home, "D": p.p_draw, "A": p.p_away}[res]))
            close.append(log_loss(paper.three_way_close(snaps[i], m.utc_date)["fair"][OUTCOME_SIDE[res]]))
        s.rollback()
    assert r["n"] == 60 and r["ll_candidate"] == sum(cand) / 60 and r["ll_close"] == sum(close) / 60
    assert r["verdict"] == lw.verdict_of(r["ll_candidate"], r["ll_close"])
    assert r["audit"] == {"present": 0, "missing": 60, "differ": [], "unreadable": []}
    assert lw.audit_lines("SA", r["audit"]) == ["  - SA · stored prospective rows: none (no stored rows; 60 members "
                                                "without one)"]
    with pytest.raises(lw.WindowRefused, match="the one read is at the 60th member"):
        lw.score({**w, "state": "waiting"})
    with pytest.raises(lw.WindowRefused):
        lw.score({**w, "members": w["members"][:59]})


def test_the_audit_counts_a_stored_row_that_differs_from_the_recompute(ledger, tmp_path):
    from src.db.database import session_scope
    from src.db.schema import Match
    from src.walters import leagues_candidate as lc
    _comps()
    ledger(decl("SA"))
    t = _teams("SA")
    _priors("SA", t)
    got = _members("SA", t, 60, 2000, AT + timedelta(hours=1))
    w = _read("SA")
    with session_scope() as s:
        rows = lc._season_rows(s, "SA", SEASON)
        p0, _ = lc.predict_as_of(rows, s.get(Match, got[0][0]), -0.1, 0.0008)
        p1, _ = lc.predict_as_of(rows, s.get(Match, got[1][0]), -0.1, 0.0008)
        s.rollback()

    def row(mid, ko, p, label=AT_TEXT):
        return {"match_id": mid, "utc_date": ko.isoformat(), "competition": "SA", "declared_at": label,
                "prediction": {"home_win_prob": p[0], "draw_prob": p[1], "away_win_prob": p[2]}}
    same = (round(p0.p_home, 4), round(p0.p_draw, 4), round(p0.p_away, 4))       # the export's rounding: no finding
    off = (p1.p_home + 0.01, p1.p_draw - 0.01, p1.p_away)
    doc = {"exported_at": (AT + timedelta(minutes=5)).isoformat(),
           "predictions": [row(got[0][0], got[0][1], same), row(got[1][0], got[1][1], off),
                           row(got[2][0], got[2][1], (0.9, 0.05, 0.05), label=None)]}   # unlabelled: not read
    (tmp_path / "exports").mkdir()
    (tmp_path / "exports" / "soccer_expansion_shadow_2026-11-06_1435.json").write_text(json.dumps(doc))
    assert _read("SA")["stored_present"] == 2
    a = lw.score(w, export_dir=str(tmp_path / "exports"))["audit"]
    assert a["present"] == 2 and a["missing"] == 58 and [f["match_id"] for f in a["differ"]] == [got[1][0]]
    L = lw.audit_lines("SA", a)
    assert L[0].startswith("  - SA · stored prospective rows: present 2 · missing 58 · differ from the recompute 1 "
                           "(FINDINGS, R1: never resolved either way)")
    assert L[1].startswith(f"    FINDING match {got[1][0]} · stored ")


# ------------------------------------------------------------------------------------------------ the fence --

def test_guards_backtest_refuses_a_declared_leagues_window_and_leaves_the_rest(ledger):
    ledger(decl("SA"), decl("FL1", verdict={"verdict": "PASS"}))
    why = sx.guards_backtest("SA", SEASON)
    assert why and "the window's outcomes have one reader, scripts/leagues_window.py" in why and "R8" in why
    assert sx.guards_backtest("sa") and sx.guards_backtest("SA", None)            # every season: fenced
    assert sx.guards_backtest("SA", "2024/25") is None                            # another season: not the window
    assert sx.guards_backtest("SA", SEASON, through=AT) is None                   # cut at the instant
    assert sx.guards_backtest("SA", SEASON, through=AT + timedelta(seconds=1))
    assert sx.guards_backtest("FL1", SEASON) is None                              # the verdict recorded: lifted
    why = sx.guards_backtest("BL1", SEASON)                                       # undeclared: the pre-declaration
    assert why and "not declared yet" in why and "2026-10-30T15:00:00Z" in why    # fence (addendum 181 item 1(b))
    assert sx.guards_backtest("BL1", SEASON, through=lw.PRE_DECLARATION_CUT) is None
    assert sx.guards_backtest("PL", SEASON) is None and sx.guards_backtest("PD", SEASON) is None


def test_an_unreadable_declared_at_fences_the_whole_season(ledger):
    ledger(decl("ELC", at="2026-11-06"))
    assert lw.fence_cutoff("ELC", SEASON) == datetime.min
    assert "unreadable declared_at" in sx.guards_backtest("ELC", SEASON)


def test_soccer_backtest_and_the_walk_refuse_the_window_and_the_cut_walk_reads_only_before(ledger):
    import cli
    from click.testing import CliRunner

    from src.walters.soccer_backtest import run_soccer_backtest
    _comps()
    ledger(decl("SA"))
    t = _teams("SA")
    _priors("SA", t, n=45)
    got = _members("SA", t, 5, 2000, AT + timedelta(hours=1))
    r = CliRunner().invoke(cli.cli, ["soccer-backtest", "--competition", "SA", "--season", SEASON])
    assert r.exit_code == 2 and "one reader, scripts/leagues_window.py" in r.output
    with pytest.raises(sx.ExpansionRefused, match="one reader"):
        run_soccer_backtest("SA", SEASON)
    with pytest.raises(sx.ExpansionRefused, match="one reader"):
        run_soccer_backtest("SA", None)
    cut = run_soccer_backtest("SA", SEASON, through=AT)
    assert cut and not {x["match_id"] for x in cut} & {mid for mid, _ in got}
    from src.walters.backtest import run_backtest
    with pytest.raises(sx.ExpansionRefused, match="one reader"):
        run_backtest(SEASON, "SA")


def test_the_cut_walk_is_the_full_walks_head_once_the_verdict_is_recorded(ledger):
    from src.walters.soccer_backtest import run_soccer_backtest
    _comps()
    ledger(decl("SA", verdict={"verdict": "PASS"}))                               # the fence lifted
    t = _teams("SA")
    _priors("SA", t, n=45)
    _members("SA", t, 5, 2000, AT + timedelta(hours=1))
    full = run_soccer_backtest("SA", SEASON)
    cut = run_soccer_backtest("SA", SEASON, through=AT)
    assert len(full) == len(cut) + 5 and full[:len(cut)] == cut                  # the cut walk is the full walk's head


def test_the_leagues_receipt_close_part_and_parity_read_only_games_at_or_before_the_instant(ledger):
    from src.walters import leagues_candidate as lc
    from src.walters.paper import close_record_line
    _comps()
    ledger(decl("SA"))
    t = _teams("SA")
    _priors("SA", t, n=45)
    _legs(1044, datetime(2026, 8, 15, 15, 0) + timedelta(hours=12 * 44))         # a prior with a close: scored
    _members("SA", t, 3, 2000, AT + timedelta(hours=1))
    r = paper.leagues_season(("SA",), SEASON, AT.date(), now=NOW)["SA"]["record"]
    assert r["n"] == 1 and r["fenced_window"] == 3 and r["finished"] == 48
    assert "fenced 3 (a league's window" in close_record_line("SA", r)
    p = lc.parity("SA", -0.1, 0.0008, season=SEASON, now=NOW)
    assert p["fenced"] == 3 and not {x["match_id"] for x in p["rows"]} & {2000, 2001, 2002}
    assert p["unequal"] == 0 and not p["shadow_only"] and not p["gate_only"] and p["rows"]
    assert "fenced 3 (finished after the cut" in lc.parity_lines(p, rows=False)[0]
    ledger(decl("SA", verdict={"verdict": "PASS"}))                               # the verdict recorded: lifted
    r = paper.leagues_season(("SA",), SEASON, AT.date(), now=NOW)["SA"]["record"]
    assert r["n"] == 4 and r["fenced_window"] == 0
    assert "fenced" not in close_record_line("SA", r) and lc.parity("SA", -0.1, 0.0008, season=SEASON)["fenced"] == 0


def test_results_tallys_close_record_fences_the_window(ledger):
    _comps()
    ledger(decl("BL1"))
    t = _teams("BL1")
    before, after = AT - timedelta(days=1), AT + timedelta(days=1)
    _game(10, "BL1", before, (t[0], t[1]))
    _legs(10, before)
    _game(11, "BL1", after, (t[1], t[0]))
    _legs(11, after)
    r = paper.close_record(60, now=NOW)["BL1"]
    assert r["n"] == 1 and r["fenced_window"] == 1
    ledger(decl("BL1", verdict={"verdict": "PASS"}))
    r = paper.close_record(60, now=NOW)["BL1"]
    assert r["n"] == 2 and r["fenced_window"] == 0


def test_the_shadow_grade_counts_the_window_and_grades_the_rest(ledger, tmp_path):
    _comps()
    ledger(decl("FL1"), decl("ELC", verdict={"verdict": "PASS"}))
    t = _teams("FL1")
    tb = _teams("ELC")
    _game(20, "FL1", AT + timedelta(days=1), (t[0], t[1]))
    _game(21, "ELC", AT + timedelta(days=1), (tb[0], tb[1]))
    rows = [{"match_id": mid, "utc_date": (AT + timedelta(days=1)).isoformat(), "competition": code,
             "prediction": {"top_pick": "home_win", "top_pick_prob": 0.5}} for mid, code in ((20, "FL1"), (21, "ELC"))]
    (tmp_path / "exports").mkdir()
    (tmp_path / "exports" / "soccer_expansion_shadow_2026-11-07_0900.json").write_text(json.dumps(
        {"engine": sx.ENGINE, "exported_at": (AT + timedelta(hours=2)).isoformat(), "predictions": rows}))
    g = sx.shadow_grade(days=60, export_dir=str(tmp_path / "exports"), now=NOW)
    assert g["per_league"]["FL1"] == {"graded": 0, "priced": 0, "fenced": 1, "mean_clv_pp": None}
    assert g["per_league"]["ELC"]["graded"] == 1 and len(g["lines"]) == 1


# ----------------------------------------------------------------------------- Codex on #733, round 1 --

def test_codex_733_a_declaration_on_a_surviving_league_is_refused(ledger):
    """The soccer-expansion-v1 confirmation reads its surviving leagues' results outside the cohort reader, so a
    window is never declared on one of them (P1, fenced before any confirmation path)."""
    _comps()
    ledger(decl("SA"), run={**RUN, "run": {"result": {**FROZEN, "surviving": ["SA"]}}})
    assert "in the soccer-expansion-v1 surviving set" in _read("SA")["refused"]


def test_codex_733_an_extra_frozen_constant_is_refused_never_dropped(ledger):
    _comps()
    ledger(decl("SA", constants={**FROZEN, "min_prior": 40}))
    assert "not exactly ['production_version', 'rho', 'elo_goal_coeff']" in _read("SA")["refused"]


def test_codex_733_a_run_record_with_a_constant_that_is_not_a_number_refuses_never_a_traceback(ledger):
    _comps()
    ledger(decl("SA"), run={**RUN, "run": {"result": {**FROZEN, "rho": "minus a tenth"}}})
    assert "constants that are not numbers" in _read("SA")["refused"]


def test_codex_733_a_cancelled_or_postponed_row_with_an_unplaced_label_never_refuses_the_league(ledger):
    _comps()
    ledger(decl("SA"))
    t = _teams("SA")
    rest = _priors("SA", t)
    _members("SA", t, 5, 2000, AT + timedelta(hours=1))
    _game(2950, "SA", AT + timedelta(hours=2), rest[0], MatchStatus.CANCELLED, stage=None)
    _game(2951, "SA", AT + timedelta(hours=3), rest[1], MatchStatus.POSTPONED, stage="")
    w = _read("SA")
    assert "refused" not in w and w["excluded"]["cancelled"] == 1 and w["not_placed"] == 1
    _game(2952, "SA", AT + timedelta(hours=4), rest[2], MatchStatus.SCHEDULED, stage=None)
    assert "cannot place" in _read("SA")["refused"]                    # a row that could take a slot still refuses


def test_codex_733_a_prior_with_no_90_minute_result_before_the_instant_makes_the_read_wait(ledger):
    """An AET / PEN row before the instant is FINISHED with full-time scores but no 90-minute result: the members'
    walk would read its after-extra-time score, so it waits like a member would (P1)."""
    _comps()
    ledger(decl("SA"))
    t = _teams("SA")
    rest = _priors("SA", t)
    _members("SA", t, 60, 2000, AT + timedelta(hours=1))
    _game(2960, "SA", AT - timedelta(days=1), rest[0], raw="AET", s90=False)
    w = _read("SA")
    assert w["state"] == "waiting" and w["pending"]["before_instant"] == 1


def test_codex_733_score_re_derives_the_cohort_and_refuses_when_it_moved(ledger):
    """A game ingested after the read and ordered before the 60th member: score() re-derives membership in its own
    transaction and refuses rather than scoring games 2-61 (P1)."""
    _comps()
    ledger(decl("SA"))
    t = _teams("SA")
    rest = _priors("SA", t)
    got = _members("SA", t, 60, 2000, AT + timedelta(hours=1))
    w = _read("SA")
    assert w["state"] == "ready" and lw.score(w, now=NOW)["n"] == 60
    ko = got[0][1] + timedelta(minutes=30)
    _game(2970, "SA", ko, rest[0])
    _legs(2970, ko)
    with pytest.raises(lw.WindowRefused, match="the window moved between the read and the score"):
        lw.score(w, now=NOW)


# ------------------------------------------------------------------- Codex round 2 + addendum 181 --

def test_181_1b_the_pre_declaration_fence_cuts_every_receipt_at_the_constant_without_an_entry(ledger, tmp_path):
    """Addendum 181 item 1(b): for a league of DECLARATION_IDS with NO entry the fence stands exactly as for a
    declared league, cut at PRE_DECLARATION_CUT. Every walk is refused unless cut at or before it; the close record,
    the leagues receipt, parity and the shadow grade read only the games at or before it and count the rest."""
    from src.walters import leagues_candidate as lc
    from src.walters.soccer_backtest import run_soccer_backtest
    cut = lw.PRE_DECLARATION_CUT
    _comps()
    t = _teams("SA")
    _priors("SA", t, n=45)
    before, between = cut - timedelta(hours=1), cut + timedelta(days=3)          # `between`: before AT
    _game(3000, "SA", before, (t[0], t[9]))
    _legs(3000, before)
    _game(3001, "SA", between, (t[9], t[0]))
    _legs(3001, between)
    _members("SA", t, 2, 2000, AT + timedelta(hours=1))
    assert lw.declaration("SA") is None and lw.fence_cutoff("SA", SEASON) == cut
    # the walks
    for season in (SEASON, None):
        with pytest.raises(sx.ExpansionRefused, match="pre-declaration fence stands, cut at 2026-10-30T15:00:00Z"):
            run_soccer_backtest("SA", season)
    assert run_soccer_backtest("SA", SEASON, through=cut)
    with pytest.raises(sx.ExpansionRefused):
        run_soccer_backtest("SA", SEASON, through=cut + timedelta(seconds=1))
    assert run_soccer_backtest("SA", "2025/26") is None                          # another season: not fenced
    # the receipts
    rec = paper.close_record(60, now=NOW)["SA"]
    assert (rec["n"], rec["fenced_window"]) == (1, 3)
    r = paper.leagues_season(("SA",), SEASON, AT.date(), now=NOW)["SA"]["record"]
    assert (r["n"], r["fenced_window"]) == (1, 3)
    p = lc.parity("SA", -0.1, 0.0008, season=SEASON, now=NOW)
    assert p["fenced"] == 3 and not {x["match_id"] for x in p["rows"]} & {3001, 2000, 2001}
    assert 3000 in {x["match_id"] for x in p["rows"]} and p["unequal"] == 0
    rows = [{"match_id": mid, "utc_date": ko.isoformat(), "competition": "SA",
             "prediction": {"top_pick": "home_win", "top_pick_prob": 0.5}} for mid, ko in ((3000, before),
                                                                                         (3001, between))]
    (tmp_path / "exports").mkdir()
    (tmp_path / "exports" / "soccer_expansion_shadow_2026-10-30_1000.json").write_text(json.dumps(
        {"engine": sx.ENGINE, "exported_at": (before - timedelta(hours=2)).isoformat(), "predictions": rows}))
    g = sx.shadow_grade(days=60, export_dir=str(tmp_path / "exports"), now=NOW)["per_league"]["SA"]
    assert (g["graded"], g["fenced"]) == (1, 1)


def test_181_1b_with_an_entry_the_cut_becomes_its_declared_at_and_a_verdict_lifts_it(ledger):
    """When the entry lands the cut becomes its declared_at (later by construction: a game between the two was never
    a window game and is released to the receipts); a verdict recorded lifts the fence. PL and PD: never fenced."""
    cut = lw.PRE_DECLARATION_CUT
    _comps()
    t = _teams("SA")
    _game(3001, "SA", cut + timedelta(days=3), (t[9], t[0]))
    _legs(3001, cut + timedelta(days=3))
    _game(3002, "SA", AT + timedelta(days=1), (t[0], t[9]))
    _legs(3002, AT + timedelta(days=1))
    assert paper.close_record(60, now=NOW)["SA"]["fenced_window"] == 2
    ledger(decl("SA"))
    assert lw.fence_cutoff("SA", SEASON) == AT
    rec = paper.close_record(60, now=NOW)["SA"]
    assert (rec["n"], rec["fenced_window"]) == (1, 1)
    assert sx.guards_backtest("SA", SEASON, through=AT) is None and sx.guards_backtest("SA", SEASON)
    ledger(decl("SA", verdict={"verdict": "REJECT"}))
    assert lw.fence_cutoff("SA", SEASON) is None and sx.guards_backtest("SA", SEASON) is None
    rec = paper.close_record(60, now=NOW)["SA"]
    assert (rec["n"], rec["fenced_window"]) == (2, 0)
    for code in ("PL", "PD"):
        assert lw.fence_cutoff(code, SEASON) is None and lw.fence_refusal(code, None) is None


def test_181_6_an_entry_whose_league_field_is_not_its_code_is_refused(ledger):
    """Addendum 181 item 6: the reader refuses an entry whose league field (LEAGUE_FIELD, "competition") is not the
    code it was looked up under; a missing field is not the code either."""
    assert lw.LEAGUE_FIELD == "competition"
    _comps()
    ledger(decl("SA", competition="BL1"), {**decl("FL1"), "competition": None})
    assert "the entry's competition is 'BL1', not 'SA'" in _read("SA")["refused"]
    assert "the entry's competition is None, not 'FL1'" in _read("FL1")["refused"]
    assert lw.fence_cutoff("SA", SEASON) == AT                          # the fence stays up (conservative)


def test_181_5_the_audit_compares_the_recompute_rounded_by_the_exports_own_function(ledger, tmp_path, monkeypatch):
    """Addendum 181 item 5: no tolerance. A stored value equal to the recompute rounded by soccer_expansion.
    shadow_prob (the function shadow_row writes with) is no finding; a stored value within the retired 5e-5 but not
    equal to it IS one."""
    assert not hasattr(lw, "AUDIT_TOL")
    rec = {1: (0.123456, 0.345678, 0.530866), 2: (0.123456, 0.345678, 0.530866)}
    stored = {1: {"prediction": {"home_win_prob": 0.1235, "draw_prob": 0.3457, "away_win_prob": 0.5309}},
              2: {"prediction": {"home_win_prob": 0.12346, "draw_prob": 0.3457, "away_win_prob": 0.5309}}}
    a = lw.audit(stored, rec)
    assert [f["match_id"] for f in a["differ"]] == [2] and a["differ"][0]["rounded"] == (0.1235, 0.3457, 0.5309)
    assert abs(a["differ"][0]["diff"]) < 5e-5                           # inside the retired tolerance: still a finding
    assert "(rounded by the export's function 0.1235/0.3457/0.5309)" in lw.audit_lines("SA", a)[1]
    from types import SimpleNamespace
    row = sx.shadow_row({}, SimpleNamespace(p_home=0.123456, p_draw=0.345678, p_away=0.530866), "v22", "x", "SA")
    assert row["prediction"]["home_win_prob"] == sx.shadow_prob(0.123456) == 0.1235      # one function
    monkeypatch.setattr(sx, "shadow_prob", lambda p: -1.0)
    assert sx.shadow_row({}, SimpleNamespace(p_home=0.1, p_draw=0.2, p_away=0.7), "v22", "x",
                         "SA")["prediction"]["draw_prob"] == -1.0
    assert lw.audit(stored, rec)["differ"][0]["rounded"] == (-1.0, -1.0, -1.0)


@pytest.mark.parametrize("args", [["dixon-coles-sweep", "--competition", "SA", "--season", SEASON],
                                  ["elo-coeff-sweep", "--competition", "SA", "--season", SEASON, "--rho", "-0.1"]])
def test_181_8_the_sweeps_print_refused_and_exit_2_on_the_fence(ledger, args):
    """Addendum 181 item 8 (round-2 P2): the two sweeps catch the fence's refusal as soccer-backtest does: REFUSED,
    exit 2, never a traceback."""
    import cli
    from click.testing import CliRunner
    _comps()
    r = CliRunner().invoke(cli.cli, args)
    assert r.exit_code == 2 and "REFUSED" in r.output and "pre-declaration fence" in r.output
    assert not isinstance(r.exception, sx.ExpansionRefused)


def test_181_2_an_awarded_row_with_no_stored_score_is_final_released_and_listed_on_either_side_of_the_instant(ledger):
    """Addendum 181 item 2: an AWD / WO game is neither scored nor walked "whatever scores its row carries", so no
    member's walk ever reads it: before the instant it is final (never `before_instant`, never blocking) and the
    window reaches ready; after it, it is excluded by cause. Either way it is RELEASED and listed, with or without a
    stored score (the season's rows, not the walk's)."""
    _comps()
    ledger(decl("SA"))
    t = _teams("SA")
    _priors("SA", t)
    got = _members("SA", t, 60, 2000, AT + timedelta(hours=1))
    _game(2920, "SA", AT - timedelta(days=1), (t[2], t[5]), raw="AWD", hs=None, as_=None, s90=False)
    _game(2921, "SA", got[5][1] + timedelta(minutes=1), (t[3], t[6]), raw="WO", hs=None, as_=None, s90=False)
    w = _read("SA")
    assert (w["n"], w["state"], w["blocking"]) == (60, "ready", 0) and not w["pending"]
    assert w["at_or_before"] == 41 and dict(w["excluded"]) == {"awarded": 1}
    assert [x.split(" · ")[0] for x in w["awarded_released"]] == ["2920", "2921"]
    assert "AWD · score None-None · 90' not stored" in w["awarded_released"][0]


def test_181_2_result_of_reads_the_raw_code_as_the_one_predicate_does(ledger):
    """result_of is derived from soccer_expansion.unscoreable and reads the raw code as it does (stripped): a
    FINISHED 'FT ' row with both scores and no 90-minute score is final on its stored score, as the confirmation walk
    walks it, before the instant and as a member; never PENDING."""
    from src.db.database import session_scope
    from src.db.schema import Match
    from src.walters import soccer_backtest as sb
    _comps()
    ledger(decl("SA"))
    t = _teams("SA")
    _priors("SA", t)
    _members("SA", t, 2, 2000, AT + timedelta(hours=1))
    _game(2930, "SA", AT - timedelta(hours=2), (t[2], t[5]), raw="FT ", s90=False, hs=2, as_=0)   # a prior
    _game(2931, "SA", AT + timedelta(hours=2), (t[3], t[6]), raw=" ft", s90=False, hs=0, as_=1)   # a window game
    _legs(2931, AT + timedelta(hours=2))
    w = _read("SA")
    assert not w["pending"] and w["blocking"] == 0 and 2931 in w["members"] and w["at_or_before"] == 41
    with session_scope() as s:
        a, b = s.get(Match, 2930), s.get(Match, 2931)
        assert (lw.result_of(a), lw.result_of(b)) == ("H", "A")
        assert not sx.unscoreable(a) and sb._confirmation_rows([a]) == [a]       # the walk reads it as stored
        for raw, h90, want in (("AWD", None, None), ("WO", 1, None), ("PEN", None, None), ("AET", 1, "D"),
                               (None, 2, "H")):
            a.status_raw, a.home_score_90, a.away_score_90 = raw, h90, (1 if h90 is not None else None)
            assert lw.result_of(a) == want, raw
            assert (lw.result_of(a) is None) == (sx.unscoreable(a) or raw in sx.AWARDED), raw
        s.rollback()
