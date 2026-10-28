"""THE EXEC COHORTS (ARCHITECT 2026-10-20 09:59 ET, addendum 146 item 1(v)), verbatim: "(v) results-tally gains an
"exec cohorts" block per closing family: counts, record and units at the exec cost for exec >= 4, 0 < exec < 4,
exec <= 0, from the closing files on disk, read-only, so the n=30 read in (i) is automatic. Small; it may ride #431 or
its own PR."

The closing files are written as a closing run writes them (tests/test_void_redated.py write_closing, through
closing.closing_doc / closing_name); the Desk blocks are hand-written, plus one made by desk_policy.annotate
(tests/test_desk_kickoff_clock.py mil_lad) so the real shape is pinned. Each test runs on a throwaway SQLite file
(tests/test_record_vs_close.py iso_db)."""
import hashlib
import json
from datetime import datetime, timedelta

import pytest

from src.db.schema import MatchStatus, Result, Sport
from src.walters import desk_policy as dp
from src.walters import exec_cohorts as xc
from src.walters import redated as rd
from tests.test_desk_kickoff_clock import annotate, mil_lad, tb_cle_tonight
from tests.test_record_vs_close import iso_db  # noqa: F401  (a fixture: a throwaway SQLite, cwd = tmp_path)
from tests.test_void_redated import MIL_LAD_START, NEW_START, OLD_START, _closing, write_closing

pytestmark = pytest.mark.usefixtures("iso_db")

KO = datetime(2026, 10, 18, 23, 0)
CLEAN = "0 < exec < 4, QB inputs clean (the pre-registered cohort)"
QB = "0 < exec < 4, QB-flagged or unread (outside the cohort)"
LE0 = "exec <= 0 (no bet under the exec-hold rule of 2026-10-18; notional)"
UNK = "exec unknown (no exec edge on the row)"
POOL = ("- The pre-registered cohort, every family on this machine, closing runs from the pre-registration "
        "(2026-10-19 07:40 ET): graded")
BEFORE = "before pre-registration, not counted"
CONSOLE = ("exec cohorts ({n} closing files on disk): the pre-registered 0 < exec < 4 cohort, closing runs from the "
           "pre-registration (2026-10-19 07:40 ET), graded {k} of 30 ({tail}) · before pre-registration, not counted "
           "{b}")
LATE = datetime(2026, 10, 19, 11, 40)   # a closing run at the pre-registration (07:40 ET, naive UTC): counted (R41)


# ---- the pure pieces ----------------------------------------------------------------------------------------------

def test_the_cohort_is_the_desks_own_exec_clears():
    assert xc.cohort_of(None) == "exec unknown"
    assert xc.cohort_of(4.0) == xc.cohort_of(4.0 - 1e-10) == "exec >= 4"            # FEE_CLEAR_EPS, 1e-9
    assert xc.cohort_of(3.6900000000000044) == xc.cohort_of(1e-9) == "0 < exec < 4"
    assert xc.cohort_of(0.0) == xc.cohort_of(-2.1) == "exec <= 0"
    assert xc.READ_AT_N == 30 and xc.QB_TAGS == ("QB-flagged half units", "QB unread half units")


def test_units_at_the_exec_cost():
    assert round(xc.settle_units(0.5, "win", 0.458), 4) == 0.5917
    assert xc.settle_units(0.5, "loss", 0.458) == -0.5
    assert xc.settle_units(0.5, "push", 0.458) == 0.0 and xc.settle_units(0.5, "void", 0.458) == 0.0
    assert xc.settle_units(0.5, "open", 0.458) is None
    for cost in (None, 0, 1.0):
        assert xc.settle_units(0.5, "win", cost) is None
        assert xc.settle_units(0.5, "loss", cost) is None
        # a push or a void settles at 0 whatever the cost or the units: a known 0, never unpriced (law 4)
        assert xc.settle_units(0.5, "push", cost) == 0.0 and xc.settle_units("n/a", "void", cost) == 0.0


def test_an_edge_that_is_not_a_finite_number_is_exec_unknown():
    """Law 4: a stored edge of the wrong kind (text, NaN, which json writes by default, a bool) is never guessed into a
    cohort, and never raises (one bad row would blank the whole section)."""
    for bad in ("n/a", float("nan"), float("inf"), True, [1], {"x": 1}):
        assert xc.cohort_of(bad) == "exec unknown", bad
    assert xc.cohort_of("2.5") == "0 < exec < 4"                   # a number written as text still reads


def test_void_is_closings_own_set():
    assert tuple(s.name for s in xc.VOID) == _closing().VOID


# ---- the world ----------------------------------------------------------------------------------------------------

def _comps():
    from src.db.database import session_scope
    from src.db.schema import Competition
    with session_scope() as s:
        for sport, code in ((Sport.MLB, "MLB"), (Sport.NFL, "NFL"), (Sport.SOCCER, "PL")):
            s.add(Competition(sport=sport, code=code, name=code, area="X", type="LEAGUE"))


def _match(mid, code, home, away, ko=KO, status=MatchStatus.FINISHED, hs=None, aw=None, ftr=None):
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, Team
    with session_scope() as s:
        c = s.query(Competition).filter_by(code=code).one()
        h, a = Team(sport=c.sport, name=home), Team(sport=c.sport, name=away)
        s.add_all([h, a])
        s.flush()
        s.add(Match(id=mid, sport=c.sport, competition_id=c.id, season="2026", utc_date=ko, status=status,
                    home_team_id=h.id, away_team_id=a.id, home_score=hs, away_score=aw, full_time_result=ftr))


def desk(call="PLAY", pick="HOME", units=0.5, edge=5.0, cost=0.5, basis="taker", tags=(), exec_=True):
    return {"engine": "model_edge", "call": call, "units": units, "pick": pick, "tags": list(tags),
            "exec": ({"edge_pp": edge, "cost": cost, "basis": basis} if exec_ else None)}


def row(mid, home, away, d, ko=KO):
    return {"match_id": mid, "home_team": home, "away_team": away, "utc_date": ko.isoformat(), "desk": d}


def _section(ex):
    return xc.section(xc.tally(ex), ex)


def _families(tmp_path):
    """Case 4: one closing file per family."""
    _comps()
    ex = tmp_path / "exports"
    _match(1001, "MLB", "A1", "B1", hs=5, aw=2)
    _match(1002, "MLB", "A2", "B2", hs=1, aw=4)
    _match(1003, "MLB", "A3", "B3", hs=0, aw=3)
    _match(1004, "MLB", "A4", "B4", status=MatchStatus.SCHEDULED)
    _match(1005, "MLB", "A5", "B5", hs=2, aw=1)
    _match(1006, "MLB", "A6", "B6", hs=2, aw=1)
    write_closing(ex, KO - timedelta(minutes=35), [
        row(1001, "A1", "B1", desk(edge=5.0, cost=0.5)),                                 # >= 4, a hit: +0.50u
        row(1002, "A2", "B2", desk(edge=2.0, cost=0.55)),                                # 0-4 clean, a miss: -0.50u
        row(1003, "A3", "B3", desk(pick="AWAY", edge=-1.0, cost=0.62)),                  # <= 0, a hit: +0.31u
        row(1004, "A4", "B4", desk(exec_=False)),                                        # exec None, open
        row(1005, "A5", "B5", desk(call="LADDER", exec_=False)),                         # left out by design
        row(1006, "A6", "B6", desk(call="PASS", units=0, exec_=False))], fam="MLB")       # not a call
    _match(2001, "NFL", "N1", "M1", hs=24, aw=17)
    _match(2002, "NFL", "N2", "M2", hs=20, aw=20)
    write_closing(ex, KO - timedelta(minutes=30), [
        row(2001, "N1", "M1", desk(edge=3.0, cost=0.6, tags=("QB-flagged half units",))),   # outside the cohort
        row(2002, "N2", "M2", desk(edge=6.0, cost=0.5))], fam="NFL")                    # a tie: push, 0u
    _match(3001, "PL", "P1", "Q1", hs=1, aw=1, ftr=Result.DRAW)
    write_closing(ex, KO - timedelta(minutes=25), [row(3001, "P1", "Q1", desk(units=1.0, edge=4.5, cost=0.45))],
                  fam="SOCCER")
    return ex


FAMILIES_TEXT = (
    "## EXEC COHORTS — PLAY calls by exec edge, per closing family (ARCHITECT 2026-10-20, addendum 146 item 1(v))\n"
    "\n"
    "_Read-only, from this machine's closing files on disk ({ex}/closing_*.json, every file, not the rolling window; "
    "host/ is never read): 3 files, runs 2026-10-18 22:25Z to 2026-10-18 22:35Z. One PLAY row per game: the newest "
    "run's row within the hour of the game's current start. The cohort is desk.exec.edge_pp (the ask plus the taker "
    "fee, basis taker; exec >= 4 is the Desk's own exec_clears). Units are notional at desk.exec.cost: a hit wins units "
    "x (1/cost - 1), a miss loses the units, a push or a void 0. Never fills: the ledger holds those. The pre-registered "
    "0 < exec < 4 cohort (QB inputs clean) is READ at n=30 graded (ARCHITECT 2026-10-20, addendum 146 item 1(i)), never "
    "earlier._\n"
    "\n"
    "- MLB · exec >= 4: PLAY 1 · W-L-P 1-0-0 · +0.50u · open 0 · void 0\n"
    f"- MLB · {CLEAN}: PLAY 1 · W-L-P 0-1-0 · -0.50u · open 0 · void 0\n"
    f"- MLB · {LE0}: PLAY 1 · W-L-P 1-0-0 · +0.31u · open 0 · void 0\n"
    f"- MLB · {UNK}: PLAY 1 · W-L-P 0-0-0 · units — · open 1 · void 0\n"
    "- MLB · left out: LADDER 1 (no exec block by design)\n"
    "- MLB · LADDER, the ordered NO leg priced, ungraded (#689: desk.ladder_exec, notional, never pooled with PLAY; no "
    "call, units or floor reads it): 1 · priced 0: exec >= 4 0 · 0 < exec < 4 0 · exec <= 0 0; unpriced no ladder_exec "
    "block on the row 1\n"
    "- NFL · exec >= 4: PLAY 1 · W-L-P 0-0-1 · +0.00u · open 0 · void 0\n"
    f"- NFL · {CLEAN}: PLAY 0\n"
    f"- NFL · {QB}: PLAY 1 · W-L-P 1-0-0 · +0.33u · open 0 · void 0\n"
    f"- NFL · {LE0}: PLAY 0\n"
    f"- NFL · {UNK}: PLAY 0\n"
    "- NFL · left out: none\n"
    "- SOCCER · exec >= 4: PLAY 1 · W-L-P 0-1-0 · -1.00u · open 0 · void 0\n"
    f"- SOCCER · {CLEAN}: PLAY 0\n"
    f"- SOCCER · {LE0}: PLAY 0\n"
    f"- SOCCER · {UNK}: PLAY 0\n"
    "- SOCCER · left out: none\n"
    "- SOCCER · PASS by floor, exec >= 4 (#690: the pick's model p under the 0.50 probability floor, exec >= 4 at the "
    "close; notional 1u at desk.exec.cost, never pooled; the floor is frozen and this line is its receipt): 0\n"
    f"{POOL} 0 of 30 — not read before n=30 · {BEFORE} 1\n")


def test_one_file_per_family_the_whole_section(tmp_path):
    """MLB: a >= 4 hit (+0.5 x (1/0.5 - 1)), a clean 0-4 miss, a <= 0 hit on AWAY (+0.5 x (1/0.62 - 1) = +0.31), a PLAY
    with no exec edge (open: unknown; nothing settled, so its units read "units —", never a +0.00u breakeven), a LADDER
    (left out) and a PASS (not a call). NFL: a QB-flagged 0-4 hit (+0.5 x
    (1/0.6 - 1) = +0.33, outside the cohort line) and a 20-20 tie (a push, 0u, out of W+L). SOCCER: a HOME PLAY on a
    1-1 draw is a loss (-1.00u). Only the MLB clean miss is graded in the cohort; its run (2026-10-18 22:25Z) is before
    the pre-registration (R41 RULED, addendum 151 item 2): printed beside the counter, never counted."""
    ex = _families(tmp_path)
    t = xc.tally(ex)
    assert xc.section(t, ex) == FAMILIES_TEXT.format(ex=ex)
    assert (t["cohort_graded"], t["cohort_before"]) == (0, 1) and t["families"] == ["MLB", "NFL", "SOCCER"]
    assert xc.console_line(t) == CONSOLE.format(n=3, k=0, tail="not read before n=30", b=1)


def test_closing_starts_is_closing_rows_projection(tmp_path):
    ex = _families(tmp_path)
    (ex / "closing_MLB_2026-10-19T0000Z.json").write_text("{not json")
    cr, cs = rd.closing_rows(ex), rd.closing_starts(ex)
    assert cs == {"rows": {mid: [(run, r.get("utc_date")) for run, _, r in v] for mid, v in cr["rows"].items()},
                  "files": cr["files"], "unreadable": cr["unreadable"]}
    assert cr["files"] == 3 and cr["unreadable"] == ["closing_MLB_2026-10-19T0000Z.json"]
    assert cr["runs"] == (datetime(2026, 10, 18, 22, 25), datetime(2026, 10, 18, 22, 35))
    assert {f for v in cr["rows"].values() for _, f, _ in v} == {"MLB", "NFL", "SOCCER"}


def test_the_rulings_arithmetic_three_half_unit_misses_are_minus_one_and_a_half(tmp_path):
    """Addendum 146 item 1(b): "3 in the pre-registered 0-to-4 cohort (0 hits, 3 misses; -1.5u)"."""
    _comps()
    rows = []
    for i in range(3):
        _match(1100 + i, "MLB", f"H{i}", f"A{i}", hs=1, aw=4)
        rows.append(row(1100 + i, f"H{i}", f"A{i}", desk(edge=2.5, cost=0.52)))
    write_closing(tmp_path / "exports", KO - timedelta(minutes=35), rows)
    assert f"- MLB · {CLEAN}: PLAY 3 · W-L-P 0-3-0 · -1.50u · open 0 · void 0\n" in _section(tmp_path / "exports")


def test_the_desks_own_annotated_row_is_read(tmp_path):
    """A row the Desk annotated (mil_lad: a PLAY, exec edge 4.2pp at the taker cost 0.568, 0.5u): a LAD win is a hit at
    the exec cost, +0.5 x (1/0.568 - 1) = +0.38u, in exec >= 4."""
    _comps()
    desk_by, _ = annotate(mil_lad())
    d = desk_by[50547]
    assert (d["call"], d["units"], d["exec"]["basis"], round(d["exec"]["edge_pp"], 1), d["exec"]["cost"]) == \
        ("PLAY", 0.5, "taker", 4.2, 0.568)
    _match(50547, "MLB", "Los Angeles Dodgers", "Milwaukee Brewers", ko=MIL_LAD_START, hs=5, aw=2)
    write_closing(tmp_path / "exports", MIL_LAD_START - timedelta(minutes=35), [{**mil_lad(), "desk": d}])
    assert "- MLB · exec >= 4: PLAY 1 · W-L-P 1-0-0 · +0.38u · open 0 · void 0\n" in _section(tmp_path / "exports")


def test_a_game_in_two_files_counts_once_the_newest_runs_row(tmp_path):
    _comps()
    _match(1200, "MLB", "H", "A", hs=4, aw=1)
    ex = tmp_path / "exports"
    write_closing(ex, KO - timedelta(minutes=95), [row(1200, "H", "A", desk(edge=5.0))])     # run A
    write_closing(ex, KO - timedelta(minutes=35), [row(1200, "H", "A", desk(edge=2.0))])     # run B, newer
    txt = _section(ex)
    assert "- MLB · exec >= 4: PLAY 0\n" in txt
    assert f"- MLB · {CLEAN}: PLAY 1 · W-L-P 1-0-0 · +0.50u · open 0 · void 0\n" in txt
    assert "graded 0 of 30" in txt and f"{BEFORE} 1" in txt           # counted once; its run is before (R41)


def test_a_redated_game_is_left_out_and_named_and_the_fresh_row_is_graded(tmp_path):
    """50548 (tests/test_void_redated.py): recorded 2026-10-17 00:00Z, the match now at 2026-10-18 21:00Z."""
    _comps()
    _match(50548, "MLB", "Cleveland Guardians", "Tampa Bay Rays", ko=NEW_START, hs=5, aw=2)
    ex = tmp_path / "exports"
    write_closing(ex, OLD_START - timedelta(minutes=35), [{**tb_cle_tonight(), "desk": desk(edge=2.0)}])
    txt = _section(ex)
    assert "- MLB · no PLAY call in its closing files\n" not in txt
    assert f"- MLB · {CLEAN}: PLAY 0\n" in txt
    assert "- MLB · left out: void: re-dated 1 · placeholder kickoff 0\n" in txt
    assert ("- MLB · void: re-dated 1 · placeholder kickoff 0: match 50548 Tampa Bay Rays @ Cleveland Guardians: "
            "void: re-dated 2026-10-17 00:00Z → 2026-10-18 21:00Z\n") in txt
    write_closing(ex, NEW_START - timedelta(minutes=35),
                  [{**tb_cle_tonight(), "utc_date": "2026-10-18T21:00:00", "desk": desk(edge=2.0)}])
    txt = _section(ex)
    assert f"- MLB · {CLEAN}: PLAY 1 · W-L-P 1-0-0 · +0.50u · open 0 · void 0\n" in txt
    assert "- MLB · left out: none\n" in txt and "re-dated" not in txt.split("never earlier._")[1]


def test_a_missing_match_id_and_teams_that_differ_are_left_out_and_counted(tmp_path):
    _comps()
    _match(1300, "MLB", "Real Home", "Real Away", hs=3, aw=1)
    ex = tmp_path / "exports"
    write_closing(ex, KO - timedelta(minutes=35), [row(4242, "X", "Y", desk()),               # not in this DB
                                                   row(1300, "Other Home", "Real Away", desk()),
                                                   row(1301, "Z", "W", desk(call="PASS"))])   # a PASS: never counted
    txt = _section(ex)
    assert "- MLB · left out: not in this DB 1, teams differ 1\n" in txt
    assert "- MLB · exec >= 4: PLAY 0\n" in txt


def test_a_basis_other_than_taker_is_left_out_and_a_called_off_game_is_a_void(tmp_path):
    _comps()
    _match(1400, "MLB", "H0", "A0", hs=3, aw=1)
    _match(1401, "MLB", "H1", "A1", status=MatchStatus.POSTPONED)
    _match(1402, "MLB", "H2", "A2", status=MatchStatus.STALE_ORPHAN)
    ex = tmp_path / "exports"
    write_closing(ex, KO - timedelta(minutes=35), [row(1400, "H0", "A0", desk(basis="maker")),
                                                   row(1401, "H1", "A1", desk(edge=6.0)),
                                                   row(1402, "H2", "A2", desk(edge=6.0, cost=None))])
    txt = _section(ex)
    # 1402's void has no exec cost: its 0 does not depend on a price, so it is priced (a known 0, never unpriced)
    assert "- MLB · exec >= 4: PLAY 2 · W-L-P 0-0-0 · +0.00u · open 0 · void 2\n" in txt
    assert "- MLB · left out: exec basis not taker 1\n" in txt


def test_an_unknown_cell_with_no_priced_row_prints_no_units(tmp_path):
    _comps()
    _match(1500, "MLB", "H", "A", hs=3, aw=1)
    write_closing(tmp_path / "exports", KO - timedelta(minutes=35), [row(1500, "H", "A", desk(exec_=False))])
    assert f"- MLB · {UNK}: PLAY 1 · W-L-P 1-0-0 · units — (unpriced 1) · open 0 · void 0\n" in \
        _section(tmp_path / "exports")


def test_unreadable_files_are_named_and_hosts_copies_never_read(tmp_path):
    _comps()
    _match(1600, "MLB", "H", "A", hs=3, aw=1)
    ex = tmp_path / "exports"
    write_closing(ex / "host", KO - timedelta(minutes=35), [row(1600, "H", "A", desk())])
    (ex / "closing_MLB_bad.json").write_text("{not json")
    t = xc.tally(ex)
    assert (t["files"], t["unreadable"], t["cells"]) == (0, ["closing_MLB_bad.json"], {})
    assert xc.section(t, ex).splitlines()[2] == (f"No readable closing file in {ex}/ on this machine; unreadable 1: "
                                                 "closing_MLB_bad.json.")
    write_closing(ex, KO - timedelta(minutes=35), [row(1600, "H", "A", desk())])
    txt = _section(ex)
    assert "1 files, runs 2026-10-18 22:25Z to 2026-10-18 22:25Z; unreadable 1: closing_MLB_bad.json." in txt
    assert "- MLB · exec >= 4: PLAY 1 · W-L-P 1-0-0 · +0.50u · open 0 · void 0\n" in txt


def test_no_closing_file(tmp_path):
    ex = tmp_path / "none"
    assert _section(ex) == (
        "## EXEC COHORTS — PLAY calls by exec edge, per closing family (ARCHITECT 2026-10-20, addendum 146 item 1(v))"
        f"\n\nNo closing file in {ex}/ on this machine.\n\n"
        f"{POOL} 0 of 30 — not read before n=30 · {BEFORE} 0\n")


@pytest.mark.parametrize("n,line", [
    (29, f"{POOL} 29 of 30 — not read before n=30 · {BEFORE} 0\n"),
    (30, f"{POOL} 30: n=30 reached — for the architect's read (no verdict is computed here) · {BEFORE} 0\n")])
def test_the_n30_line(tmp_path, n, line):
    _comps()
    rows = []
    for i in range(n):
        _match(1700 + i, "MLB", f"H{i}", f"A{i}", hs=1 + (i % 2) * 3, aw=2)
        rows.append(row(1700 + i, f"H{i}", f"A{i}", desk(edge=1.5)))
    write_closing(tmp_path / "exports", LATE, rows)               # a run from the pre-registration on: counted
    t = xc.tally(tmp_path / "exports")
    assert xc.section(t, tmp_path / "exports").endswith(line)
    assert t["cohort_graded"] == n
    assert xc.console_line(t) == CONSOLE.format(
        n=1, k=n, tail="n=30 reached — for the architect's read" if n >= 30 else "not read before n=30", b=0)


# ---- the edges of the rules: one rule each (a bad row, a no-side pick, the stored result, the QB tags, a tie, the
# inclusive hour, the newest row, a LADDER, the family from the file's name) ------------------------------------------

def test_bad_rows_read_as_unknown_and_never_blank_the_section(tmp_path):
    """Law 4: a text edge, a NaN edge (json writes NaN by default) and a tags list holding a dict. Each row is read
    (exec unknown, or its cohort with the dict tag ignored); the block is never "Grade unavailable" and keeps its
    console line."""
    from src.walters.export import results_tally
    _comps()
    for i, (hs, aw) in enumerate(((3, 1), (3, 1), (1, 4))):
        _match(1800 + i, "MLB", f"H{i}", f"A{i}", hs=hs, aw=aw)
    ex = tmp_path / "exports"
    write_closing(ex, KO - timedelta(minutes=35), [row(1800, "H0", "A0", desk(edge="n/a")),
                                                   row(1801, "H1", "A1", desk(edge=float("nan"))),
                                                   row(1802, "H2", "A2", desk(edge=2.0, tags=({"x": 1},)))])
    txt = _section(ex)
    assert f"- MLB · {UNK}: PLAY 2 · W-L-P 2-0-0 · +1.00u · open 0 · void 0\n" in txt
    assert f"- MLB · {CLEAN}: PLAY 1 · W-L-P 0-1-0 · -0.50u · open 0 · void 0\n" in txt
    assert f"- MLB · {LE0}: PLAY 0\n" in txt                                # NaN is never "exec <= 0"
    out, said = tmp_path / "R.md", []
    results_tally(days=36500, out_path=str(out), report=said.append, exports_dir=str(ex))
    assert "## EXEC COHORTS — PLAY calls by exec edge, per closing family\n\nGrade unavailable." not in out.read_text()
    assert CONSOLE.format(n=1, k=0, tail="not read before n=30", b=1) in said      # its run is before (R41)


def test_a_void_with_no_exec_cost_settles_at_zero_never_unpriced(tmp_path):
    """A POSTPONED game's PLAY with edge 6.0 and exec.cost null: its void settles at 0 whatever the price."""
    _comps()
    _match(1850, "MLB", "H", "A", status=MatchStatus.POSTPONED)
    write_closing(tmp_path / "exports", KO - timedelta(minutes=35), [row(1850, "H", "A", desk(edge=6.0, cost=None))])
    assert "- MLB · exec >= 4: PLAY 1 · W-L-P 0-0-0 · +0.00u · open 0 · void 1\n" in _section(tmp_path / "exports")


def test_a_pick_naming_no_side_is_open_never_a_loss(tmp_path):
    _comps()
    _match(1900, "MLB", "H", "A", hs=3, aw=1)
    write_closing(tmp_path / "exports", KO - timedelta(minutes=35), [row(1900, "H", "A", desk(pick=None))])
    assert "- MLB · exec >= 4: PLAY 1 · W-L-P 0-0-0 · units — · open 1 · void 0\n" in _section(tmp_path / "exports")


def test_a_three_way_game_reads_its_stored_result_before_the_scores(tmp_path):
    """R10: soccer reads full_time_result, else the scores. A PL game stored HOME on a 1-1 score: pick HOME is a win
    (+1.0 x (1/0.45 - 1) = +1.22u)."""
    _comps()
    _match(3100, "PL", "P", "Q", hs=1, aw=1, ftr=Result.HOME)
    write_closing(tmp_path / "exports", KO - timedelta(minutes=25),
                  [row(3100, "P", "Q", desk(units=1.0, edge=4.5, cost=0.45))], fam="SOCCER")
    assert "- SOCCER · exec >= 4: PLAY 1 · W-L-P 1-0-0 · +1.22u · open 0 · void 0\n" in _section(tmp_path / "exports")


def test_the_qb_split_reads_both_qb_tags_and_only_inside_0_to_4(tmp_path):
    """A 0-4 PLAY tagged "QB unread half units" (desk_policy.INJURY_EMPTY_TAG) is on the QB line, outside the cohort; a
    QB-flagged exec >= 4 PLAY stays in exec >= 4 (the split is the 0-4 cohort's only)."""
    _comps()
    _match(2100, "NFL", "N1", "M1", hs=24, aw=17)
    _match(2101, "NFL", "N2", "M2", hs=24, aw=17)
    write_closing(tmp_path / "exports", KO - timedelta(minutes=30), [
        row(2100, "N1", "M1", desk(edge=3.0, cost=0.6, tags=(dp.INJURY_EMPTY_TAG,))),
        row(2101, "N2", "M2", desk(edge=5.0, cost=0.5, tags=("QB-flagged half units",)))], fam="NFL")
    t = xc.tally(tmp_path / "exports")
    txt = xc.section(t, tmp_path / "exports")
    assert "- NFL · exec >= 4: PLAY 1 · W-L-P 1-0-0 · +0.50u · open 0 · void 0\n" in txt
    assert f"- NFL · {CLEAN}: PLAY 0\n" in txt
    assert f"- NFL · {QB}: PLAY 1 · W-L-P 1-0-0 · +0.33u · open 0 · void 0\n" in txt
    assert t["cohort_graded"] == 0


def test_a_tie_in_the_cohort_is_a_push_and_not_graded(tmp_path):
    """An NFL 20-20 tie on a clean 0-4 PLAY: a push, 0u. As built, graded = W + L (a push is not graded; the value
    shadows' counter counts it, a reading for the architect in the PR body)."""
    _comps()
    _match(2150, "NFL", "N", "M", hs=20, aw=20)
    write_closing(tmp_path / "exports", KO - timedelta(minutes=30), [row(2150, "N", "M", desk(edge=2.0))], fam="NFL")
    t = xc.tally(tmp_path / "exports")
    assert f"- NFL · {CLEAN}: PLAY 1 · W-L-P 0-0-1 · +0.00u · open 0 · void 0\n" in xc.section(t, tmp_path / "exports")
    assert t["cohort_graded"] == 0


def test_a_row_exactly_the_hour_from_the_current_start_is_within_it(tmp_path):
    """Two runs: the older recorded at the current start (edge 5.0), the newer recorded exactly DESK_CLOCK_DRIFT away
    (edge 2.0). The hour is inclusive (desk_policy.DESK_CLOCK_DRIFT), so the newer row stands."""
    _comps()
    _match(1210, "MLB", "H", "A", hs=4, aw=1)
    ex = tmp_path / "exports"
    write_closing(ex, KO - timedelta(minutes=95), [row(1210, "H", "A", desk(edge=5.0))])
    write_closing(ex, KO - timedelta(minutes=35), [row(1210, "H", "A", desk(edge=2.0), ko=KO + dp.DESK_CLOCK_DRIFT)])
    txt = _section(ex)
    assert "- MLB · exec >= 4: PLAY 0\n" in txt
    assert f"- MLB · {CLEAN}: PLAY 1 · W-L-P 1-0-0 · +0.50u · open 0 · void 0\n" in txt


def test_the_newest_row_stands_for_a_void_game_and_for_a_match_this_db_lacks(tmp_path):
    """50548 re-dated with two old runs, the older a PASS and the newer a PLAY: the newest is the row void and named. A
    match id this DB lacks, the same two runs: the newest (a PLAY) is counted not in this DB."""
    _comps()
    _match(50548, "MLB", "Cleveland Guardians", "Tampa Bay Rays", ko=NEW_START, hs=5, aw=2)
    ex = tmp_path / "exports"
    passed = desk(call="PASS", units=0, exec_=False)
    write_closing(ex, OLD_START - timedelta(minutes=95),
                  [{**tb_cle_tonight(), "desk": passed}, row(4343, "X", "Y", passed)])
    write_closing(ex, OLD_START - timedelta(minutes=35), [{**tb_cle_tonight(), "desk": desk(edge=2.0)},
                                                         row(4343, "X", "Y", desk(edge=2.0))])
    txt = _section(ex)
    assert "- MLB · left out: not in this DB 1, void: re-dated 1 · placeholder kickoff 0\n" in txt
    assert ("- MLB · void: re-dated 1 · placeholder kickoff 0: match 50548 Tampa Bay Rays @ Cleveland Guardians: "
            "void: re-dated 2026-10-17 00:00Z → 2026-10-18 21:00Z\n") in txt


def test_a_ladder_is_counted_whether_or_not_this_db_holds_the_match(tmp_path):
    _comps()
    write_closing(tmp_path / "exports", KO - timedelta(minutes=35),
                  [row(4444, "X", "Y", desk(call="LADDER", exec_=False))])
    txt = _section(tmp_path / "exports")
    assert "- MLB · no PLAY call in its closing files\n- MLB · left out: LADDER 1 (no exec block by design)\n" in txt


def test_a_file_whose_block_names_no_family_takes_it_from_its_name(tmp_path):
    """A closing file whose closing block carries no family: closing_NFL_<start>.json reads as NFL."""
    _comps()
    _match(2200, "NFL", "N", "M", hs=24, aw=17)
    p = write_closing(tmp_path / "exports", KO - timedelta(minutes=30), [row(2200, "N", "M", desk())], fam="NFL")
    doc = json.loads(p.read_text())
    del doc["closing"]["family"]
    p.write_text(json.dumps(doc))
    assert p.name.startswith("closing_NFL_")
    t = xc.tally(tmp_path / "exports")
    assert t["families"] == ["NFL"]
    assert "- NFL · exec >= 4: PLAY 1 · W-L-P 1-0-0 · +0.50u · open 0 · void 0\n" in xc.section(t, tmp_path / "exports")


# ---- the n=30 counter starts at the PRE-REGISTRATION (R41 RULED, ARCHITECT 2026-10-20 19:54 ET, addendum 151 item 2)

def test_the_counter_counts_closing_runs_from_the_pre_registration_and_prints_the_earlier_ones_beside_it(tmp_path):
    """R41 RULED (addendum 151 item 2): "the PRE-REGISTRATION, addendum 136 item 5(iv), 2026-10-19 07:40 ET ... the rows
    before it ... print beside the counter as 'before pre-registration, not counted'". Four clean 0-4 PLAYs graded,
    their closing runs at 2026-10-18 04:00Z (the rule's own date, 10-18 00:00 ET: counted before the ruling, now not),
    2026-10-19 03:59Z, 2026-10-19 11:39Z (07:39 ET) and 11:40Z (07:40 ET). The counter counts the last only; the three
    earlier rows print beside it; the MLB line (the record) keeps all four."""
    _comps()
    ex = tmp_path / "exports"
    for mid, run in ((2300, datetime(2026, 10, 18, 4, 0)), (2301, datetime(2026, 10, 19, 3, 59)),
                     (2302, datetime(2026, 10, 19, 11, 39)), (2303, datetime(2026, 10, 19, 11, 40))):
        ko = run + timedelta(minutes=35)
        _match(mid, "MLB", f"H{mid}", f"A{mid}", ko=ko, hs=1, aw=4)
        write_closing(ex, run, [row(mid, f"H{mid}", f"A{mid}", desk(edge=2.0), ko=ko)])
    assert xc.COUNTED_FROM == datetime(2026, 10, 19, 11, 40)          # 2026-10-19 07:40 ET (EDT), naive UTC
    assert xc.RULING_R41.startswith("2. R41, the n=30 counter's start: the PRE-REGISTRATION, addendum 136 item 5(iv)")
    assert xc.RULING_RULE_OF_1018.startswith("The written exec-hold rule of 2026-10-18 stands verbatim: ")
    t = xc.tally(ex)
    assert (t["cohort_graded"], t["cohort_before"], t["cohort_undated"]) == (1, 3, 0)
    txt = xc.section(t, ex)
    assert f"- MLB · {CLEAN}: PLAY 4 · W-L-P 0-4-0 · -2.00u · open 0 · void 0\n" in txt
    assert txt.endswith(f"{POOL} 1 of 30 — not read before n=30 · {BEFORE} 3\n")
    assert xc.console_line(t) == CONSOLE.format(n=4, k=1, tail="not read before n=30", b=3)


def test_a_row_with_no_run_start_is_not_counted_and_named(tmp_path):
    """A closing file with no closing block start and no stamp in its name has no run start: its graded row is never
    counted toward n=30 (it cannot be shown to follow the rule) and is named beside the counter."""
    _comps()
    ex = tmp_path / "exports"
    _match(2310, "MLB", "H", "A", hs=1, aw=4)
    p = write_closing(ex, KO - timedelta(minutes=35), [row(2310, "H", "A", desk(edge=2.0))])
    doc = json.loads(p.read_text())
    del doc["closing"]["start"]
    (ex / "closing_MLB_nostamp.json").write_text(json.dumps(doc))
    p.unlink()
    t = xc.tally(ex)
    assert (t["cohort_graded"], t["cohort_before"], t["cohort_undated"], t["runs"]) == (0, 0, 1, None)
    assert xc.section(t, ex).endswith(f"{POOL} 0 of 30 — not read before n=30 · {BEFORE} 0 · not counted (no run "
                                      "start) 1\n")


def test_the_n30_reached_line_carries_the_earlier_rows_beside_it():
    """The pooled line's wording at n=30 carries the earlier rows too."""
    assert xc.pooled_line(30, 4) == (f"{POOL} 30: n=30 reached — for the architect's read (no verdict is computed "
                                     f"here) · {BEFORE} 4")


def test_n30_is_never_reached_on_rows_before_the_pre_registration():
    """1 counted + 29 before the pre-registration is 30 graded rows, but only 1 counts: never "n=30 reached" ("never earlier",
    146 1(i)), on the section's line and on the console."""
    assert xc.pooled_line(1, 29) == f"{POOL} 1 of 30 — not read before n=30 · {BEFORE} 29"
    t = {"files": 3, "cohort_graded": 1, "cohort_before": 29, "cohort_undated": 0}
    assert xc.console_line(t) == CONSOLE.format(n=3, k=1, tail="not read before n=30", b=29)


# ---- the second verify round's gaps: one rule each --------------------------------------------------------------

@pytest.mark.parametrize("units,cost,expect", [(float("nan"), 0.5, None), (float("inf"), 0.5, None), (True, 0.5, None),
                                               (0.5, True, None), (0.5, float("nan"), None), (0.5, "0.5", 0.5)],
                         ids=["nan-units", "inf-units", "bool-units", "bool-cost", "nan-cost", "text-cost-reads"])
def test_units_or_cost_that_is_not_a_finite_number_reads_unpriced(units, cost, expect):
    assert xc.settle_units(units, "win", cost) == expect
    assert xc.settle_units(units, "void", cost) == 0.0                 # a void is a known 0 whatever it holds


@pytest.mark.parametrize("units", [float("nan"), float("inf"), True], ids=["nan", "inf", "bool"])
def test_a_bad_units_row_is_counted_unpriced_never_summed(tmp_path, units):
    """json writes NaN and Infinity by default: such a row never prints "+nanu" or "-infu", and a bool is no 1u."""
    _comps()
    _match(2400, "MLB", "H0", "A0", hs=3, aw=1)
    _match(2401, "MLB", "H1", "A1", hs=1, aw=3)
    write_closing(tmp_path / "exports", KO - timedelta(minutes=35),
                  [row(2400, "H0", "A0", desk(units=units, edge=5.0, cost=0.5)),
                   row(2401, "H1", "A1", desk(units=0.5, edge=5.0, cost=0.5))])
    assert "- MLB · exec >= 4: PLAY 2 · W-L-P 1-1-0 · -0.50u (unpriced 1) · open 0 · void 0\n" in \
        _section(tmp_path / "exports")


def test_a_three_way_game_with_no_stored_result_reads_the_scores(tmp_path):
    """PL 2-1, full_time_result None: HOME by the scores, a HOME PLAY wins (+1.0 x (1/0.45 - 1) = +1.22u)."""
    _comps()
    _match(3200, "PL", "P", "Q", hs=2, aw=1, ftr=None)
    _match(3201, "PL", "R", "S", hs=0, aw=2, ftr=None)
    write_closing(tmp_path / "exports", KO - timedelta(minutes=25),
                  [row(3200, "P", "Q", desk(units=1.0, edge=4.5, cost=0.45)),
                   row(3201, "R", "S", desk(pick="AWAY", units=1.0, edge=4.5, cost=0.5))], fam="SOCCER")
    assert "- SOCCER · exec >= 4: PLAY 2 · W-L-P 2-0-0 · +2.22u · open 0 · void 0\n" in _section(tmp_path / "exports")


def test_a_game_not_finished_is_open_whatever_its_scores(tmp_path):
    _comps()
    _match(2500, "MLB", "H", "A", hs=3, aw=1, status=MatchStatus.LIVE)
    write_closing(tmp_path / "exports", KO - timedelta(minutes=35), [row(2500, "H", "A", desk(edge=2.0))])
    t = xc.tally(tmp_path / "exports")
    assert f"- MLB · {CLEAN}: PLAY 1 · W-L-P 0-0-0 · units — · open 1 · void 0\n" in xc.section(t, tmp_path / "exports")
    assert t["cohort_graded"] == 0


def test_an_away_team_that_differs_is_left_out(tmp_path):
    _comps()
    _match(2600, "MLB", "H", "A", hs=3, aw=1)
    write_closing(tmp_path / "exports", KO - timedelta(minutes=35), [row(2600, "H", "Other", desk(edge=2.0))])
    txt = _section(tmp_path / "exports")
    assert "- MLB · left out: teams differ 1\n" in txt and f"- MLB · {CLEAN}: PLAY 0\n" in txt


def test_the_hour_is_read_on_the_rows_recorded_start_never_its_run(tmp_path):
    """Run A at KO - 95 min records the game at KO (within the hour of its current start KO); run B, newer, at KO - 35
    min, recorded it at KO + 3h (a start since moved back). The row graded is A's: the hour is the recorded start's,
    never the run's (B's run is within the hour of KO, its recorded start is not)."""
    _comps()
    _match(2700, "MLB", "H", "A", hs=4, aw=1)
    ex = tmp_path / "exports"
    write_closing(ex, KO - timedelta(minutes=95), [row(2700, "H", "A", desk(edge=5.0))])
    write_closing(ex, KO - timedelta(minutes=35), [row(2700, "H", "A", desk(edge=2.0), ko=KO + timedelta(hours=3))])
    txt = _section(ex)
    assert "- MLB · exec >= 4: PLAY 1 · W-L-P 1-0-0 · +0.50u · open 0 · void 0\n" in txt
    assert f"- MLB · {CLEAN}: PLAY 0\n" in txt


def test_the_run_range_is_the_earliest_and_the_latest_run_whatever_the_file_names(tmp_path):
    """closing_MLB_... sorts before closing_NFL_... but runs later: the range is (NFL's run, MLB's run)."""
    _comps()
    ex = tmp_path / "exports"
    write_closing(ex, datetime(2026, 10, 19, 23, 0), [], fam="MLB")
    write_closing(ex, datetime(2026, 10, 18, 20, 0), [], fam="NFL")
    assert rd.closing_rows(ex)["runs"] == (datetime(2026, 10, 18, 20, 0), datetime(2026, 10, 19, 23, 0))
    assert "runs 2026-10-18 20:00Z to 2026-10-19 23:00Z" in _section(ex)


def test_a_family_whose_files_hold_no_row_is_named(tmp_path):
    """A closing file of a family with an empty predictions list: the family is named by its file, never dropped."""
    _comps()
    write_closing(tmp_path / "exports", KO - timedelta(minutes=35), [], fam="NHL")
    t = xc.tally(tmp_path / "exports")
    assert t["families"] == ["NHL"]
    assert "- NHL · no PLAY call in its closing files\n- NHL · left out: none\n" in xc.section(t, tmp_path / "exports")


# ---- results-tally ------------------------------------------------------------------------------------------------

def test_results_tally_places_the_section_after_nfl_and_before_the_nhl_shadow(tmp_path):
    from src.walters.export import results_tally
    from tests.test_void_redated import _nfl_world
    _nfl_world(tmp_path)                                  # an NFL section, and an NFL closing file (no desk: no PLAY)
    out, said = tmp_path / "RESULTS.md", []
    results_tally(days=36500, out_path=str(out), report=said.append, exports_dir=str(tmp_path / "ex"))
    txt = out.read_text()
    i_nfl, i_x, i_nhl = (txt.index("## NFL (live since Week 3"), txt.index("## EXEC COHORTS"),
                         txt.index("## NHL — REFERENCE MODEL"))
    assert i_nfl < i_x < i_nhl
    assert "- NFL · no PLAY call in its closing files\n- NFL · left out: none\n" in txt
    assert CONSOLE.format(n=1, k=0, tail="not read before n=30", b=0) in said


def test_results_tally_leaves_the_mlb_pl_and_nfl_sections_as_they_were(tmp_path):
    from src.walters.export import results_tally
    from tests.test_void_redated import _mlb_world
    _mlb_world()
    desk_by, _ = annotate(mil_lad())
    write_closing(tmp_path / "ex", MIL_LAD_START - timedelta(minutes=35), [{**mil_lad(), "desk": desk_by[50547]}])

    def head(ex):
        out = tmp_path / "R.md"
        results_tally(days=36500, out_path=str(out), exports_dir=str(ex))
        txt = out.read_text()
        return txt[txt.index("## MLB"):txt.index("## EXEC COHORTS")]
    assert head(tmp_path / "ex") == head(tmp_path / "none")
    assert "## MLB\n\n- Sides: **2/2**" in head(tmp_path / "ex")


def test_read_only_the_exports_and_the_db_are_untouched(tmp_path):
    ex = _families(tmp_path)
    db = tmp_path / "iso.db"
    snap = lambda: ({p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in sorted(ex.iterdir())},  # noqa: E731
                    hashlib.sha256(db.read_bytes()).hexdigest(), db.stat().st_mtime_ns)
    before = snap()
    _section(ex)
    assert snap() == before


def test_the_ladder_line_prices_the_no_leg_and_never_grades_or_pools_it(tmp_path):
    """#689: the LADDER rows by desk.ladder_exec.edge_pp (exec >= 4, 0 < exec < 4, exec <= 0), the mean NO-leg edge,
    the unpriced by why; no record, no units, and the PLAY cells are untouched."""
    _comps()

    def lad(edge, why=None, basis="taker"):
        d = desk(call="LADDER", pick="AWAY", exec_=False)
        d["ladder_exec"] = {"edge_pp": edge, "basis": basis if edge is not None else None, "why": why}
        return d
    write_closing(tmp_path / "exports", KO - timedelta(minutes=35),
                  [row(4501, "A", "B", lad(6.0)), row(4502, "C", "D", lad(2.0)), row(4503, "E", "F", lad(-1.0)),
                   row(4504, "G", "H", lad(None, why="double chance for a draw pick is 1X or X2: no single contract "
                                                      "to price")),
                   row(4505, "I", "J", desk(call="LADDER", pick="AWAY", exec_=False))])
    txt = _section(tmp_path / "exports")
    assert "- MLB · left out: LADDER 5 (no exec block by design)\n" in txt
    assert ("- MLB · LADDER, the ordered NO leg priced, ungraded (#689: desk.ladder_exec, notional, never pooled with "
            "PLAY; no call, units or floor reads it): 5 · priced 3: exec >= 4 1 · 0 < exec < 4 1 · exec <= 0 1 · mean "
            "NO-leg exec edge +2.3pp; unpriced double chance for a draw pick is 1X or X2: no single contract to price 1, "
            "no ladder_exec block on the row 1\n") in txt
    assert "PLAY 1" not in txt and "W-L-P" not in txt



# ---- #690 (ARCHITECT 2026-10-26 12:05 ET): "rows PASS by the 0.50 floor with exec >= 4 at the close [...] counted
# notionally as "PASS by floor, exec >= 4", W-L and notional units, never pooled; the floor is frozen and this line is
# its receipt." -------------------------------------------------------------------------------------------------------

def floor_desk(model_p=0.47, edge=8.6, cost=0.42, pick="HOME", basis="taker", kind="floor"):
    return {"engine": "model_edge", "call": "PASS", "units": 0, "pick": pick, "pass_kind": kind, "model_p": model_p,
            "tags": [], "exec": {"edge_pp": edge, "cost": cost, "basis": basis}}


def test_the_floor_blocked_line_counts_pass_by_the_probability_floor_with_exec_ge_4(tmp_path):
    """Newcastle (10-25: +8.6, won) as the row: model p 0.47 under 0.50, exec +8.6 at the close, a home win: W-L 1-0,
    +1u x (1/0.42 - 1). The edge floor (model p >= 0.50, pass_kind floor too), exec < 4, an unknown exec and a basis
    other than taker are not in it; nothing enters a PLAY cell; MLB (no probability floor) prints no such line."""
    _comps()
    for mid, (h, a) in enumerate([("Newcastle", "Spurs"), ("A", "B"), ("C", "D"), ("E", "F"), ("G", "H"),
                                  ("I", "J")], start=4601):
        _match(mid, "PL", h, a, hs=2, aw=0)
    write_closing(tmp_path / "exports", KO - timedelta(minutes=35), [
        row(4601, "Newcastle", "Spurs", floor_desk()),
        row(4602, "A", "B", floor_desk(model_p=0.55)),                 # the edge floor: never the probability floor
        row(4603, "C", "D", floor_desk(edge=3.0)),                     # exec < 4
        row(4604, "E", "F", floor_desk(edge=None)),                    # exec unknown: never read in
        row(4605, "G", "H", floor_desk(basis="maker")),                # not the taker basis
        row(4606, "I", "J", floor_desk(pick="AWAY")),                  # in the cohort: a loss
    ], fam="SOCCER")
    t = xc.tally(tmp_path / "exports")
    fb = t["floor_blocked"]["SOCCER"]
    assert (fb["plays"], fb["w"], fb["l"]) == (2, 1, 1)
    assert fb["units_sum"] == pytest.approx((1 / 0.42 - 1) - 1)
    txt = xc.section(t, tmp_path / "exports")
    assert ("- SOCCER · PASS by floor, exec >= 4 (#690: the pick's model p under the 0.50 probability floor, exec >= 4 "
            "at the close; notional 1u at desk.exec.cost, never pooled; the floor is frozen and this line is its "
            f"receipt): 2 · W-L-P 1-1-0 · {(1 / 0.42 - 1) - 1:+.2f}u · open 0 · void 0\n") in txt
    assert "PLAY 1" not in txt and "PLAY 2" not in txt
    assert "MLB · PASS by floor" not in txt


def test_a_family_without_a_probability_floor_has_no_floor_blocked_rows():
    assert not xc.floor_blocked(floor_desk(), "NFL") and not xc.floor_blocked(floor_desk(), "MLB")
    assert xc.floor_blocked(floor_desk(), "SOCCER") and xc.floor_blocked(floor_desk(), "INTL")
    assert not xc.floor_blocked({**floor_desk(), "model_p": True}, "SOCCER")      # a bool is not a probability
    assert not xc.floor_blocked({**floor_desk(), "call": "PLAY"}, "SOCCER")


def test_codex_round_1_on_717_intl_90_minutes_labels_kept_finite_p_and_the_model_engine(tmp_path):
    """Codex on #717: (1) an INTL floor row is graded on the 90-minute result, and an AET game without a 90-minute
    score stays open; (2) a re-dated and a placeholder-kickoff exclusion keep their own labels; (3) a non-finite
    model_p is never read in; and a venue-engine PASS is never the probability floor."""
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, Team
    _comps()
    with session_scope() as s:
        c = Competition(sport=Sport.SOCCER, code="UNL", name="UNL", area="I", type="INTL")
        s.add(c)
        s.flush()

        def m(mid, raw, ft, s90):
            h, a = Team(sport=Sport.SOCCER, name=f"H{mid}"), Team(sport=Sport.SOCCER, name=f"A{mid}")
            s.add_all([h, a])
            s.flush()
            s.add(Match(id=mid, sport=Sport.SOCCER, competition_id=c.id, season="2026/27", utc_date=KO,
                        status=MatchStatus.FINISHED, status_raw=raw, home_team_id=h.id, away_team_id=a.id,
                        home_score=ft[0], away_score=ft[1], home_score_90=s90[0] if s90 else None,
                        away_score_90=s90[1] if s90 else None, full_time_result=Result.HOME if ft[0] > ft[1] else
                        Result.AWAY if ft[0] < ft[1] else Result.DRAW))
        m(4701, "AET", (2, 1), (1, 1))          # a 90-minute draw, won in extra time: the HOME pick LOSES
        m(4702, "PEN", (1, 1), None)            # no 90-minute score: never graded
    write_closing(tmp_path / "ix", KO - timedelta(minutes=35),
                  [row(4701, "H4701", "A4701", floor_desk()), row(4702, "H4702", "A4702", floor_desk())], fam="INTL")
    fb = xc.tally(tmp_path / "ix")["floor_blocked"]["INTL"]
    assert (fb["plays"], fb["w"], fb["l"], fb["open"]) == (2, 0, 1, 1)
    # (2) labels: one row re-dated three days, one on the 04:00Z placeholder
    for mid, (h, a) in ((4801, ("R1", "R2")), (4802, ("P1", "P2"))):
        _match(mid, "PL", h, a, hs=1, aw=0)
    write_closing(tmp_path / "lx", KO - timedelta(days=3), [
        row(4801, "R1", "R2", floor_desk(), ko=KO - timedelta(days=3)),
        row(4802, "P1", "P2", floor_desk(), ko=datetime(KO.year, KO.month, KO.day, 4, 0))], fam="SOCCER")
    txt = _section(tmp_path / "lx")
    assert "left out: void: re-dated 1 · placeholder kickoff 1" in txt
    # (3) a non-finite probability and a venue-engine row
    assert not xc.floor_blocked({**floor_desk(), "model_p": float("-inf")}, "SOCCER")
    assert not xc.floor_blocked({**floor_desk(), "model_p": float("nan")}, "SOCCER")
    assert not xc.floor_blocked({**floor_desk(), "model_p": -0.1}, "SOCCER")      # #718: not a probability
    assert xc.floor_blocked({**floor_desk(), "model_p": 0.0}, "SOCCER")
    assert not xc.floor_blocked({**floor_desk(), "engine": "venue_edge"}, "SOCCER")
