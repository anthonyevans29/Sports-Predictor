"""ARCHITECT 2026-11-02 13:10 ET, addendum 220 (lane leagues, #322): the leagues declarations. The registry entries
for PD, SA, FL1 and ELC (declared_at 2026-11-02T18:10:00Z, the bar of item 3 verbatim), BL1 undeclared (no entry; its
moved line, 11-09), the roadmap's leagues lane, the fence lifting for SA/FL1/ELC with the entries while BL1's stays at
the pre-declaration cut (synthetic data on a throwaway SQLite, tests/test_record_vs_close.py iso_db; a tmp registry
holding the REAL entries as written), and the receipt's recount of step (c) from each league's own start (paper.
window_projection, scripts/leagues_close_receipt.py; --from, --db mode=ro + immutable=1)."""
from __future__ import annotations

import importlib.util
import json
import sqlite3
from datetime import date, datetime, timedelta
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

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("leagues_close_receipt_220",
                                              ROOT / "scripts" / "leagues_close_receipt.py")
lr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lr)

SEASON = "2026/27"
STAMP_TEXT = "2026-11-02T18:10:00Z"
STAMP = datetime(2026, 11, 2, 18, 10)
FROZEN = {"production_version": "v22", "rho": -0.1, "elo_goal_coeff": 0.0008}
DECLARED_IDS = ("leagues-pd-v1", "leagues-sa-v1", "leagues-fl1-v1", "leagues-elc-v1")
REAL = {e["id"]: e for e in reg.load(reg.LEDGER)}          # read before any monkeypatch: the tracked file

# addendum 220, verbatim (the architect's text; items 1-3 and item 4's MOVED LINE)
ITEM1 = ("THE CANDIDATE, per league, identical in form: soccer_elo_poisson's CURRENT constants, trained to "
         '2025/26 and FROZEN (no retuning on 2026/27, no parameter of any kind moved for the league), as the '
         'export switch already runs it; the arm the export writes is the arm that is judged.')
ITEM2 = ('THE WINDOW, per league: the first 60 FINISHED 2026/27 games of that league with a three-way close, '
         "in kickoff order, counted from this declaration's stamp — 2026-11-02T18:10:00Z — with the fence's "
         'own rule (addendum 181: a game before the declaration is never a member; an AWD/WO game is '
         'unscoreable and consumes no slot; a FT/90-minute score disagreement is PENDING until resolved). '
         'Nothing already played counts.')
ITEM3 = ('THE BAR, written before any result and the same for every league (addendum 158 item 2(c), verbatim '
         "as the roadmap carries it): the candidate's mean three-way log-loss on the window BELOW the close's "
         'on the same 60 games; a tie is a rejection; no partial read, no intermediate read, the one read by '
         "me the day after the 60th game is final, per league. PASS → that league's live_needs are met and "
         "the Desk's calls for it are ruled in by their own addendum (market-first discipline applies as in "
         'the PL); FAIL → the league stays SHADOW through 2026/27 and the successor lane (#656) carries it.')
MOVED = ("BL1's declaration moves from 2026-11-06 to 2026-11-09: the parity receipt with rows is read after "
         'the Bundesliga round of 11-06/07 (my laptop block, Monday 11-09 morning), and the declaration '
         "follows it the same day; no bar moves; the other four leagues' declarations stand at 11-02.")

# ------------------------------------------------------------------------------------------ the registry --

def test_220_the_four_entries_close_the_file_in_declared_at_order_and_the_file_keeps_its_format():
    text = Path(reg.LEDGER).read_text()
    entries = json.loads(text)
    assert text == json.dumps(entries, indent=2) + "\n"            # json.dumps(indent=2), ensure_ascii, a newline
    assert [e["id"] for e in entries[-4:]] == list(DECLARED_IDS)
    before = [lw.parse_instant(e.get("declared_at")) for e in entries[:-4]]
    assert all(t is None or t <= STAMP for t in before)            # appended at the end, in declared-at order


@pytest.mark.parametrize("eid, code", list(zip(DECLARED_IDS, ("PD", "SA", "FL1", "ELC"))))
def test_220_each_entry_carries_items_1_to_3_verbatim_and_the_run_records_constants(eid, code):
    e = REAL[eid]
    assert all(e.get(k) for k in reg.DECLARE_FIELDS), [k for k in reg.DECLARE_FIELDS if not e.get(k)]
    assert e["sport"] == "soccer" and e["competition"] == code
    assert e["declared_at"] == STAMP_TEXT and lw.parse_instant(e["declared_at"]) == STAMP
    assert e["status"] == "declared" and e["run"] is None and e["verdict"] is None
    assert e["candidate"] == ITEM1                                  # item 1, verbatim
    assert ITEM2 in e["test_set"] and e["test_set"].startswith(f"{code} (")   # item 2, verbatim, per league
    assert e["gate"] == ITEM3                                       # THE BAR: not a character differs
    assert ITEM3[ITEM3.index("PASS →"):] in e["confirmation_window"]
    assert e["frozen_constants"] == FROZEN
    assert e["frozen_constants"] == {k: REAL[sx.EID]["run"]["result"][k] for k in lw.CONSTANTS}
    assert e["confirmation_plan"] is None and e["n"] == 60


def test_220_bl1_has_no_entry_and_no_status_was_invented():
    """Item 4: "BL1 NOT declared today". registry.py has no undeclared status (declared, run, confirming, closed,
    production), and an entry under leagues-bl1-v1 would read as a declaration (leagues_window.declaration), so BL1
    holds none: its state is the roadmap lane's BL1 step and moved line."""
    assert "leagues-bl1-v1" not in REAL and not any(e.get("competition") == "BL1" for e in REAL.values())
    assert {e["status"] for e in REAL.values()} <= {"declared", "run", "confirming", "closed", "production"}


def test_220_the_test_set_strings_differ_so_no_league_is_a_prior_read_of_another():
    """registry.prior_reads counts an earlier run on the SAME test_set string: one window per league, one string."""
    assert len({REAL[i]["test_set"] for i in DECLARED_IDS}) == 4


@pytest.mark.parametrize("eid, code", list(zip(DECLARED_IDS, ("PD", "SA", "FL1", "ELC"))))
def test_220_each_entrys_note_names_the_reader_the_code_runs_for_its_league(eid, code):
    """A frozen record states only a reader that exists for its league: all four are the cohort reader's
    (DECLARATION_IDS; leagues_window.read and .score), PD since ARCHITECT 2026-11-02 16:35 ET, addendum 222 item 4(b)
    ("PD gets the window reader and the fence in the SAME PR, on the same code path and the same stamp"): checked()
    reads its entry though PD is the soccer-expansion-v1 surviving set, and PD's note says so and names the collision."""
    note = REAL[eid]["confirmation_plan_note"]
    assert lw.DECLARATION_IDS[code] == eid and callable(lw.read) and callable(lw.score)
    assert "The one read is the cohort reader's scoring path (leagues_window.score;" in note
    if code == "PD":
        assert lw.surviving() == ["PD"] and "PD" in lw.SURVIVING_RULED
        assert "NO reader" not in note and lw.RULING_222_4B.split("verbatim: ", 1)[1] in note
        assert "open for the architect" in note and "no reader" not in REAL[eid]["pd_note"].lower()


# -------------------------------------------------------------------------------------------- the roadmap --

def _leagues():
    doc = json.loads((ROOT / "docs" / "roadmap.json").read_text(encoding="utf-8"))
    return next(ln for ln in doc["lanes"] if ln["lane"] == "leagues")


def test_220_the_leagues_lane_the_11_06_step_done_bl1_moved_and_step_c_a_projection():
    from src import roadmap as rm
    ln = _leagues()
    assert ln["state"] == "declared" and "declared (4 of 5)" in json.dumps(ln)   # roadmap.STATES: no "(4 of 5)"
    assert ln["registry_id"] is None and ln["competitions"] == ["SA", "BL1", "FL1", "ELC"]
    decl = next(st for st in ln["steps"] if st["what"].startswith("the candidate declared per league"))
    assert decl["due"] == "2026-11-06" and decl["done"] == {"date": "2026-11-02", "receipt": "addendum 220"}
    bl1 = next(st for st in ln["steps"] if st["what"].startswith("BL1's declaration"))
    assert (bl1["owner"], bl1["due"], bl1["done"]) == ("architect", "2026-11-09", None)
    assert ln["moved"] == [{"moved_on": "2026-11-02", "which": bl1["what"], "was": "2026-11-06", "now": "2026-11-09",
                            "why": MOVED, "ruling": "ARCHITECT 2026-11-02 13:10 ET, addendum 220 item 4 (MOVED "
                                                    "LINE, verbatim in why)"}]
    c = ln["steps"][-1]
    assert (c["owner"], c["due"], c["done"]) == ("calendar", "2026-12-06", None)
    assert "RECOUNTED from the declarations' stamp 2026-11-02T18:10:00Z" in c["what"]
    assert "A PROJECTION pending its receipt" in c["what"] and "named here when it lands" in c["what"]
    # the first page is the first shadow-export file on a tag carrying the entries (the host deploys tags; the export
    # binds from the tag's own registry), never the v1.6.2 page of 11-03, which holds no row labelled with the stamp
    assert "written on a release tag carrying the declaration entries" in c["what"]
    assert "carries no row labelled 2026-11-02T18:10:00Z" in c["what"]
    # addendum 222 item 4(a): those games are excluded by cause, the window still counting from the stamp
    assert ("is EXCLUDED BY CAUSE, \"no prospective row: the entry was not on the host's tag\", named and counted by "
            "the cohort reader and its receipt, consuming no slot (addendum 222 item 4(a)") in c["what"]
    assert rm.next_step(ln)[1] is bl1
    assert ln["earliest_live"] is None


# ------------------------------------------------------------------------------------------- the fence --

@pytest.fixture
def real_ledger(tmp_path, monkeypatch):
    """A tmp registry holding the soccer-expansion-v1 run record and the four entries EXACTLY as the tracked file
    holds them (never a hand-made copy): the fence reads what was written."""
    path = tmp_path / "experiments.json"
    path.write_text(json.dumps([REAL[sx.EID], *(REAL[i] for i in DECLARED_IDS)]))
    monkeypatch.setattr(reg, "LEDGER", str(path))
    return path


def _comps(codes=("PD", *paper.LEAGUES)):
    from src.db.database import session_scope
    from src.db.schema import Competition
    with session_scope() as s:
        for code in codes:
            s.add(Competition(sport=Sport.SOCCER, code=code, name=code, area="X", type="LEAGUE"))


def _game(mid, code, ko, status=MatchStatus.FINISHED, hs=1, as_=0, stage="Regular Season - 1", raw=None):
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, Team
    fin = status == MatchStatus.FINISHED
    with session_scope() as s:
        c = s.query(Competition).filter_by(code=code).one()
        h, a = Team(sport=Sport.SOCCER, name=f"H{mid}"), Team(sport=Sport.SOCCER, name=f"A{mid}")
        s.add_all([h, a])
        s.flush()
        s.add(Match(id=mid, sport=Sport.SOCCER, competition_id=c.id, season=SEASON, utc_date=ko, status=status,
                    stage=stage, home_team_id=h.id, away_team_id=a.id, home_score=hs if fin else None,
                    away_score=as_ if fin else None, home_score_90=hs if fin else None,
                    away_score_90=as_ if fin else None, status_raw=raw or ("FT" if fin else None)))


BETWEEN = datetime(2026, 11, 1, 15, 0)       # after the pre-declaration cut (10-30 15:00Z), before the stamp
AFTER = datetime(2026, 11, 3, 19, 0)         # a window game


@pytest.mark.usefixtures("iso_db")
def test_220_the_fence_lifts_to_the_stamp_for_sa_fl1_elc_and_stays_at_the_pre_declaration_cut_for_bl1(real_ledger):
    """Item 5: "The cohort reader's fail-closed fence for SA/FL1/ELC lifts with the entries; BL1's stays closed until
    11-09." Lifts: a read cut at a time between the pre-declaration cut and the stamp is refused before the entries
    and allowed with them; the window (after the stamp) stays fenced until the verdict. BL1: refused as before. PD
    (ARCHITECT 2026-11-02 16:35 ET, addendum 222 item 4(b)): the same fence at the same stamp."""
    for code in ("PD", "SA", "FL1", "ELC"):
        assert lw.fence_cutoff(code, SEASON) == STAMP
        assert sx.guards_backtest(code, SEASON, through=BETWEEN) is None          # lifted: 11-01 is readable
        assert sx.guards_backtest(code, SEASON, through=STAMP) is None
        why = sx.guards_backtest(code, SEASON, through=AFTER)                     # the window: still fenced
        assert why and f"is declared ({lw.DECLARATION_IDS[code]}, declared_at 2026-11-02T18:10:00Z)" in why
        assert sx.guards_backtest(code, SEASON) is not None                       # an uncut walk: refused
    assert lw.fence_cutoff("BL1", SEASON) == lw.PRE_DECLARATION_CUT
    why = sx.guards_backtest("BL1", SEASON, through=BETWEEN)                      # BL1: closed at 10-30 15:00Z
    assert why and "is not declared yet" in why and "2026-10-30T15:00:00Z" in why
    assert sx.guards_backtest("PL", SEASON) is None and lw.fence_cutoff("PL", SEASON) is None   # PL: never here


@pytest.mark.usefixtures("iso_db")
def test_220_the_close_record_reads_the_games_before_the_stamp_and_fences_the_window_and_bl1(real_ledger):
    """paper.leagues_season on synthetic data: an SA / FL1 / ELC game between the two cuts is now scored (a close
    record's figure on a game that is never a window member); the game after the stamp is fenced; BL1's game between
    the cuts stays fenced (the cohort reader's alone)."""
    _comps()
    mid = 100
    for code in ("SA", "FL1", "ELC", "BL1"):
        for ko in (BETWEEN, AFTER):
            _game(mid, code, ko)
            for sel, (bid, ask) in A.items():
                _kal(mid, sel, bid, ask, ko - timedelta(minutes=30), market="1X2")
            mid += 1
    res = paper.leagues_season(("SA", "FL1", "ELC", "BL1"), SEASON, date(2026, 11, 9), now=datetime(2026, 11, 4))
    for code in ("SA", "FL1", "ELC"):
        rec = res[code]["record"]
        assert (rec["n"], rec["fenced_window"]) == (1, 1), (code, rec)
    assert (res["BL1"]["record"]["n"], res["BL1"]["record"]["fenced_window"]) == (0, 2)


@pytest.mark.usefixtures("iso_db")
def test_220_the_cohort_reader_reads_the_entries_as_written(real_ledger):
    """The reader needs no change to read them: SA declared at the stamp with the run record's constants, the game
    between the cuts at or before the instant, the one after it pending in the window; BL1 NOT DECLARED; PD one of the
    reader's leagues, its entry read as the four's are (addendum 222 item 4(b))."""
    _comps()
    _game(1, "SA", BETWEEN)
    _game(2, "SA", AFTER, status=MatchStatus.SCHEDULED)
    res = lw.read(now=datetime(2026, 11, 2, 20, 0))
    sa = res["SA"]
    assert sa["declared"] and "refused" not in sa and sa["declared_at"] == STAMP and sa["constants"] == FROZEN
    assert (sa["at_or_before"], sa["to_come"], sa["n"], sa["state"]) == (1, 1, 0, "accruing")
    assert res["FL1"]["declared"] and res["ELC"]["declared"] and not res["BL1"]["declared"]
    assert list(res) == ["PD", "SA", "BL1", "FL1", "ELC"]
    pd = res["PD"]
    assert pd["declared"] and "refused" not in pd and pd["id"] == "leagues-pd-v1" and pd["declared_at"] == STAMP
    assert pd["constants"] == FROZEN and pd["n"] == 0
    out = lw.lines(res, datetime(2026, 11, 2, 20, 0))
    assert "BL1 · NOT DECLARED (no registry entry leagues-bl1-v1): no window" in out
    assert any(x.startswith("SA · declared_at 2026-11-02T18:10:00Z (leagues-sa-v1;") for x in out)


@pytest.mark.usefixtures("iso_db")
def test_220_the_export_binds_pd_sa_fl1_elc_at_the_stamp_and_pd_without_its_entry_on_soccer_expansion_v1(real_ledger):
    """ARCHITECT 2026-11-02 16:35 ET, addendum 222 item 4(b): PD on the same code path and the same stamp, so its rows
    carry leagues-pd-v1's label (the rows the cohort reader's stored_rows reads for PD's window). A registry without
    that entry (a tag from before addendum 220) keeps PD's soccer-expansion-v1 binding (D1, addendum 185)."""
    b = sx.shadow_bindings()
    for code in ("PD", "SA", "FL1", "ELC"):
        assert b[code]["state"] == sx.SHADOW_EXPORTING and b[code]["declared_at"] == STAMP_TEXT
        assert b[code]["window_opens_at"] == STAMP_TEXT and b[code]["candidate"] == lw.DECLARATION_IDS[code]
        assert b[code]["opens_at"] == STAMP and b[code]["frozen_constants"] == FROZEN
        assert b[code]["gate_verdict"] == f"{lw.DECLARATION_IDS[code]} · declared {STAMP_TEXT}"
    assert b["BL1"]["state"] == sx.SHADOW_NOT_DECLARED
    doc = [e for e in json.loads(real_ledger.read_text()) if e["id"] != "leagues-pd-v1"]
    real_ledger.write_text(json.dumps(doc))
    pd = sx.shadow_binding("PD")
    assert pd["state"] == sx.SHADOW_EXPORTING and pd["candidate"] == sx.EID
    assert pd["declared_at"] == REAL[sx.EID]["declared_at"] and pd["window_opens_at"] == REAL[sx.EID]["verdict"]["at"]


# --------------------------------------------------------------------------------------- the recount --

def _fixtures(code, start, n, base, step_h=12, status=MatchStatus.SCHEDULED):
    for i in range(n):
        _game(base + i, code, start + timedelta(hours=step_h * i), status=status)


@pytest.mark.usefixtures("iso_db")
def test_220_window_projection_counts_strictly_after_the_instant_and_reads_the_schedule_only():
    """R3: a kickoff exactly at the instant is not after it; cancelled / postponed / stale_orphan are not games; the
    60th's kickoff names the step; fewer than 60 stored: no date. A date start counts its UTC day on."""
    _comps()
    _game(1, "ELC", STAMP)                                              # AT the instant: never counted
    _game(2, "ELC", STAMP + timedelta(hours=1), status=MatchStatus.POSTPONED)
    _fixtures("ELC", STAMP + timedelta(hours=2), 60, 1000)               # the 60th at +2 h + 59 * 12 h
    _fixtures("SA", STAMP + timedelta(hours=2), 59, 2000)
    _fixtures("BL1", datetime(2026, 11, 9, 0, 0), 60, 3000)
    _game(9, "BL1", datetime(2026, 11, 8, 23, 59))                        # the day before the date: never counted
    got = paper.window_projection({"ELC": STAMP, "SA": STAMP, "BL1": date(2026, 11, 9)}, SEASON)
    nth = STAMP + timedelta(hours=2 + 59 * 12)
    assert got["ELC"]["projected"] == {"date": nth.date(), "kickoff": nth, "match_id": 1059}
    assert got["ELC"]["after"] == 60 and got["ELC"]["games"] == 62
    assert got["SA"]["projected"] is None and got["SA"]["after"] == 59
    assert got["BL1"]["projected"]["match_id"] == 3059 and got["BL1"]["after"] == 60


@pytest.mark.usefixtures("iso_db")
def test_220_window_projection_gives_no_slot_to_an_awd_wo_row_or_a_play_off_round_row():
    """Addendum 220 item 2: "an AWD/WO game is unscoreable and consumes no slot"; the cohort reader leaves a play-off
    round out (F3, excluded not_regular). The projection reads the status_raw and the stage (never a score) and leaves
    both out as the reader does, so the 60th is pushed one fixture later for each; an unplaceable label is counted."""
    _comps()
    _fixtures("ELC", STAMP + timedelta(hours=2), 60, 1000)                # the plain 60th: match 1059
    _game(7, "ELC", STAMP + timedelta(hours=3), raw="AWD")                 # awarded: no slot, whatever its scores
    _game(8, "ELC", STAMP + timedelta(hours=4), raw="wo")                  # walkover, read case-blind as the reader does
    _game(9, "ELC", STAMP + timedelta(hours=5), status=MatchStatus.SCHEDULED, stage="Play-offs - Semi-finals")
    _game(10, "ELC", STAMP + timedelta(hours=6), stage="Regular Season - 2", raw="AET")   # a non-AWD raw code: a slot
    _game(11, "ELC", STAMP + timedelta(hours=7), status=MatchStatus.SCHEDULED, stage=None)  # unplaceable: counted
    got = paper.window_projection({"ELC": STAMP}, SEASON)["ELC"]
    assert got["excluded"] == {"awarded": 2, "not_regular": 1}
    assert got["after"] == 62 and got["games"] == 65
    nth = STAMP + timedelta(hours=2 + 57 * 12)                              # 2 kept extras before: the 58th fixture
    assert got["projected"] == {"date": nth.date(), "kickoff": nth, "match_id": 1057}
    proj = paper.window_projection({c: STAMP for c in lr.window_ids()}, SEASON)
    lines = lr.projection_lines(proj, {c: "x" for c in proj}, {}, SEASON)
    assert any("· 62 stored after the start (2 AWD/WO and 1 play-off-round rows left out)" in x for x in lines)


@pytest.mark.usefixtures("iso_db")
def test_220_starts_read_each_entrys_declared_at_bl1_its_date_and_from_overrides(real_ledger):
    st, src, bad = lr.starts(None, date(2026, 11, 9))
    assert list(st) == ["PD", "SA", "BL1", "FL1", "ELC"] and not bad
    assert all(st[c] == STAMP for c in ("PD", "SA", "FL1", "ELC")) and st["BL1"] == date(2026, 11, 9)
    assert src["PD"] == "leagues-pd-v1 declared_at 2026-11-02T18:10:00Z"
    assert src["BL1"].startswith("not declared: no entry leagues-bl1-v1; the date 2026-11-09 (--declared)")
    frm = datetime(2026, 11, 5, 0, 0)
    st, src, bad = lr.starts(frm, date(2026, 11, 9))
    assert set(st.values()) == {frm} and set(src.values()) == {"--from"}


@pytest.mark.usefixtures("iso_db")
@pytest.mark.parametrize("edit, why", [({"declared_at": "2026-11-02"}, "is not a UTC instant"),
                                       ({"competition": "PL"}, "its competition is 'PL', not 'SA'")])
def test_220_an_entry_without_its_instant_or_its_league_refuses_its_projection(real_ledger, edit, why):
    doc = json.loads(real_ledger.read_text())
    for e in doc:
        if e["id"] == "leagues-sa-v1":
            e.update(edit)
    real_ledger.write_text(json.dumps(doc))
    st, src, bad = lr.starts(None, date(2026, 11, 9))
    assert why in bad["SA"] and "SA" not in st and set(st) == {"PD", "BL1", "FL1", "ELC"}
    lines = lr.projection_lines(paper.window_projection(st, SEASON), src, bad, SEASON)
    assert any(x.startswith("  - SA · REFUSED: leagues-sa-v1: ") for x in lines)


def _copy(tmp_path) -> Path:
    """A .backup copy of the throwaway DB outside data/ (the operator's --db)."""
    dst = tmp_path / "copies" / "sports_copy.db"
    dst.parent.mkdir()
    src = sqlite3.connect(tmp_path / "iso.db")
    out = sqlite3.connect(dst)
    src.backup(out)
    out.close()
    src.close()
    return dst


@pytest.mark.usefixtures("iso_db")
def test_220_the_script_recounts_from_the_entries_on_a_db_copy_read_mode_ro_immutable(tmp_path, monkeypatch, capsys,
                                                                                      real_ledger):
    """The operator's command: --db COPY (mode=ro + immutable=1, no sidecar created); the projection per league from
    its own start, PD included, the earliest named first as 156 item 1 rules it; the close part unchanged."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'iso.db'}")
    _comps()
    _fixtures("ELC", STAMP + timedelta(hours=1), 60, 1000, step_h=8)
    _fixtures("PD", STAMP + timedelta(hours=1), 60, 2000, step_h=10)
    _fixtures("SA", STAMP + timedelta(hours=1), 60, 3000, step_h=12)
    _fixtures("BL1", datetime(2026, 11, 9, 14, 0), 60, 4000, step_h=12)
    cp = _copy(tmp_path)
    urls = []
    real = lr.copy_uri

    def spy(f):
        urls.append(real(f))
        return urls[-1]
    monkeypatch.setattr(lr, "copy_uri", spy)
    assert lr.main(["--db", str(cp)]) == 0
    out = capsys.readouterr().out
    assert urls == [cp.resolve().as_uri() + "?mode=ro&immutable=1"]
    assert sorted(p.name for p in cp.parent.iterdir()) == ["sports_copy.db"]          # no sidecar created
    assert out.startswith(f"database: {cp.resolve()} (--db copy, mode=ro + immutable=1;")
    head = out.splitlines()[1]                                       # the header names each league's start's source
    assert head == ("LEAGUES CLOSE RECEIPT (ARCHITECT 2026-10-23, addendum 155 item 4(a); 156 item 1; #322) · read-only "
                    "· season 2026/27 · each league's projection from its own start, named on its line (a declared "
                    "league's registry declared_at; every league --from when given; a league with no entry from "
                    "2026-11-09, --declared)")
    assert "declaration 2026-11-09" not in out
    assert "AWD/WO rows (status_raw) and play-off-round rows (stage) left out, as the cohort reader" in out
    assert "counted as slots" not in out
    elc = STAMP + timedelta(hours=1 + 59 * 8)
    pd = STAMP + timedelta(hours=1 + 59 * 10)
    sa = STAMP + timedelta(hours=1 + 59 * 12)
    bl1 = datetime(2026, 11, 9, 14, 0) + timedelta(hours=59 * 12)
    assert (f"  - ELC · the 60th fixture kicking off strictly after 2026-11-02T18:10:00Z (leagues-elc-v1 declared_at "
            f"2026-11-02T18:10:00Z): kickoff {elc:%Y-%m-%d %H:%M}Z (UTC date {elc.date()}; match 1059) · 60 stored "
            "after the start") in out
    assert "  - BL1 · the 60th fixture kicking off on or after 2026-11-09 (its UTC day on) (not declared: " in out
    assert (f"STEP (c) (156 item 1; recounted from each league's start, addendum 220 item 5): due {elc.date()} (ELC, "
            f"the earliest); the others: PD {pd.date()}, SA {sa.date()}, BL1 {bl1.date()}; no date for FL1") in out
    assert "STEP (c) (156 item 1): due" not in out                                   # the date projection replaced
    assert "60th fixture on or after 2026-11-09" not in out


@pytest.mark.usefixtures("iso_db")
@pytest.mark.parametrize("folder", ["sp ace#1", "q?x"])
def test_220_a_db_copy_whose_path_holds_a_hash_or_a_question_mark_is_read_and_nothing_is_created(
        tmp_path, monkeypatch, capsys, real_ledger, folder):
    """addendum 198 item 6(ii): the copy's URI is percent-encoded (Path.as_uri), so a '#' or '?' in its path cannot cut
    the filename (a raw "file:" URL made SQLite open, and create, the path up to that character, read-write) or drop
    mode=ro + immutable=1: the copy itself is read, no stray file appears, the copy is not written."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'iso.db'}")
    _comps()
    _fixtures("ELC", STAMP + timedelta(hours=1), 60, 1000, step_h=8)
    cp0 = _copy(tmp_path)
    d = tmp_path / folder
    d.mkdir()
    cp = d / "c.db"
    cp0.rename(cp)
    before = sorted(x.name for x in tmp_path.iterdir())
    raw = cp.read_bytes()
    assert lr.main(["--db", str(cp)]) == 0
    out = capsys.readouterr().out
    assert "  - ELC · the 60th fixture kicking off strictly after 2026-11-02T18:10:00Z" in out and "match 1059" in out
    assert sorted(x.name for x in tmp_path.iterdir()) == before                     # no stray file cut at '#' / '?'
    assert sorted(x.name for x in d.iterdir()) == ["c.db"] and cp.read_bytes() == raw


@pytest.mark.usefixtures("iso_db")
def test_220_the_script_refuses_a_bad_from_and_a_db_it_must_not_read(tmp_path, monkeypatch, capsys, real_ledger):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'iso.db'}")
    assert lr.main(["--from", "2026-11-02"]) == lr.REFUSED == 2
    assert "REFUSED: --from '2026-11-02' is not a UTC instant" in capsys.readouterr().out
    assert lr.main(["--from", "2026-11-02T13:10:00-05:00"]) == 2                       # ET, not UTC
    capsys.readouterr()
    missing = tmp_path / "nope.db"
    assert lr.main(["--db", str(missing)]) == 2 and not missing.exists()               # never created
    assert "REFUSED: --db" in capsys.readouterr().out
    assert lr.main(["--db", str(tmp_path / "iso.db")]) == 2                            # the receipt's own database
    assert "is the receipt's own DATABASE_URL file" in capsys.readouterr().out
    cp = _copy(tmp_path)
    cp.with_name(cp.name + "-wal").write_bytes(b"")
    assert lr.main(["--db", str(cp)]) == 2
    assert "has a -wal sidecar" in capsys.readouterr().out


@pytest.mark.usefixtures("iso_db")
def test_220_the_script_recounts_from_from_for_every_league(tmp_path, monkeypatch, capsys, real_ledger):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'iso.db'}")
    _comps()
    assert lr.main(["--from", "2026-11-05T00:00:00Z"]) == 0
    out = capsys.readouterr().out
    assert "  - PD · the 60th fixture kicking off strictly after 2026-11-05T00:00:00Z (--from): not stored" in out


# ------------------------------------------------------------------ addendum 222 item 4: the ruled questions --
# ARCHITECT 2026-11-02 16:35 ET, addendum 222 item 4 (THE LEAGUES PR), (a) and (b) verbatim in leagues_window.
# RULING_222_4A / RULING_222_4B; the synthetic window below is tests/test_leagues_window.py's (declared_at
# 2026-11-06T14:30:00Z, read clock 2026-12-20), its rows written by that module's _export.

from tests.test_leagues_window import AT as W_AT  # noqa: E402
from tests.test_leagues_window import AT_TEXT as W_AT_TEXT  # noqa: E402
from tests.test_leagues_window import NOW as W_NOW  # noqa: E402
from tests.test_leagues_window import _comps as w_comps  # noqa: E402
from tests.test_leagues_window import _export as w_export  # noqa: E402
from tests.test_leagues_window import _members, _priors, _teams, decl, ledger  # noqa: E402,F401  (ledger: a fixture)

NO_ROW_LINE = ("excluded by cause (no slot): no prospective row: the entry was not on the host's tag {n} (ARCHITECT "
               "2026-11-02, addendum 222 item 4(a); a window game with no stored prospective row in the read's export "
               "directory, kicking off before the first page there whose tag carried the entry, or with no such page)")
FINDING_LINE = ("FINDING · no prospective row on a page whose tag carried the entry {n} (excluded, no slot, as item "
                "4(a)'s games are until the architect rules it; the first page carrying the entry in the read's export "
                "directory: {first})")


def _drop_rows(ids, export_dir="exports"):
    """The host's tag carried no entry when these games' page was written: their rows are not in the files."""
    for f in Path(export_dir).glob(f"{lw.EXPORT_PREFIX}*.json"):
        doc = json.loads(f.read_text())
        doc["predictions"] = [r for r in doc["predictions"] if r["match_id"] not in ids]
        f.write_text(json.dumps(doc))


def test_222_4a_the_ruling_and_the_cause_text_are_verbatim():
    assert lw.NO_ROW_TEXT == "no prospective row: the entry was not on the host's tag"
    assert f'"{lw.NO_ROW_TEXT}"' in lw.RULING_222_4A
    assert lw.RULING_222_4A.startswith("ARCHITECT 2026-11-02 16:35 ET, addendum 222 item 4(a), verbatim: \"the window "
                                       "of each league counts from the declaration stamp, 2026-11-02T18:10:00Z")
    assert lw.RULING_222_4A.endswith("the 60 are the first 60 SCOREABLE members in kickoff order.\"")


@pytest.mark.usefixtures("iso_db")
def test_222_4a_a_window_game_with_no_stored_row_is_excluded_by_cause_named_counted_and_takes_no_slot(ledger):
    """Two window games with no stored row (the 4th and the 10th by kickoff) are EXCLUDED BY CAUSE, named (match,
    kickoff) and counted on their own line, and take no slot: the 60 are the first 60 scoreable members, so the 60th
    moves two games later. The members with rows are the same games in the same order. A game without a row that
    another cause already excludes (no close) keeps its own cause, as built."""
    w_comps()
    ledger(decl("SA"))
    t = _teams("SA")
    _priors("SA", t)
    got = _members("SA", t, 62, 2000, W_AT + timedelta(hours=1))
    noclose = _members("SA", t, 1, 2900, W_AT + timedelta(hours=2, minutes=30), legs=False)[0]
    w_export("SA")
    full = lw.read(("SA",), now=W_NOW)["SA"]
    assert full["members"] == [m for m, _ in got[:60]] and full[lw.NO_ROW] == [] and full["state"] == "ready"
    drop = [got[3], got[9]]
    _drop_rows({got[3][0], got[9][0], noclose[0]})
    w = lw.read(("SA",), now=W_NOW)["SA"]
    kept = [m for m, _ in got if m not in {got[3][0], got[9][0]}]
    assert w["members"] == kept[:60] and w["members"][-1] == got[61][0] and w["n"] == 60 and w["state"] == "ready"
    assert [m for m in full["members"] if m not in {got[3][0], got[9][0]}] == w["members"][:58]   # unaffected
    assert w[lw.NO_ROW] == drop and w["excluded"][lw.NO_ROW] == 2
    assert w["excluded"]["unpriced_none"] == 1 and noclose[0] not in {m for m, _ in w[lw.NO_ROW]}
    assert (w["stored_present"], w["stored_missing"]) == (60, 0)
    out = lw.lines({"SA": w}, W_NOW)
    i = out.index("  - SA · " + NO_ROW_LINE.format(n=2))                          # its own line, counted
    assert out[i + 1:i + 4] == [f"    - match {m} · kickoff {ko:%Y-%m-%dT%H:%M:%SZ}" for m, ko in drop] + [
        "  - SA · " + FINDING_LINE.format(n=0, first="none")]                    # the finding beside it, 0 counted
    # the summary accounts for the cause (never "none" above a counted no-row line)
    assert f"  - excluded (no slot): no close: no capture 1 · {lw.NO_ROW_TEXT} 2 (listed below)" in out
    r = lw.score(w, now=W_NOW)                                                    # the receipt (R1's audit)
    assert r["n"] == 60 and r["match_ids"] == w["members"]
    a = r["audit"]
    assert a[lw.NO_ROW] == drop and (a["present"], a["missing"]) == (60, 0)
    L = lw.audit_lines("SA", a)
    assert L[-4:] == ["  - SA · " + NO_ROW_LINE.format(n=2)] + [
        f"    - match {m} · kickoff {ko:%Y-%m-%dT%H:%M:%SZ}" for m, ko in drop] + [
        "  - SA · " + FINDING_LINE.format(n=0, first="none")]


@pytest.mark.usefixtures("iso_db")
def test_222_4a_a_read_with_no_rows_at_all_excludes_every_game_and_says_where_it_read(ledger, tmp_path):
    """The reader cannot see the tag: a read whose --exports holds none of the rows (another machine, another
    directory) excludes every otherwise-member under the cause, names each, and prints the directory it read."""
    w_comps()
    ledger(decl("SA"))
    t = _teams("SA")
    _priors("SA", t)
    got = _members("SA", t, 3, 2000, W_AT + timedelta(hours=1))
    w = lw.read(("SA",), now=W_NOW, export_dir=str(tmp_path / "elsewhere"))["SA"]
    assert w["n"] == 0 and w[lw.NO_ROW] == [(m, ko) for m, ko in got] and w["state"] == "accruing"
    out = lw.lines({"SA": w}, W_NOW)
    assert "  - SA · " + NO_ROW_LINE.format(n=3) in out
    assert any(x.startswith(f"  - stored prospective rows (R1's audit receipt): members holding one 0 · read from "
                            f"{tmp_path / 'elsewhere'} (none found there;") for x in out)


def _window_62(ledger):
    """The synthetic SA window of the test above: 62 members 6 hours apart from W_AT + 1h, each with its row."""
    w_comps()
    ledger(decl("SA"))
    t = _teams("SA")
    _priors("SA", t)
    got = _members("SA", t, 62, 2000, W_AT + timedelta(hours=1))
    return got


def _page(name, exported_at, bindings, export_dir="exports"):
    d = Path(export_dir)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{lw.EXPORT_PREFIX}{name}.json").write_text(json.dumps(
        {"exported_at": exported_at, "bindings": bindings, "predictions": []}))


@pytest.mark.usefixtures("iso_db")
def test_222_4a_a_no_row_game_after_a_page_whose_tag_carried_the_entry_is_a_finding_never_the_rulings_text(ledger):
    """Item 4(a)'s text says WHY a game has no row ("the host's tag carried no entry for the league when its page was
    written"). A no-row game kicking off after the first page in the read's directory whose header binding carried
    the entry (candidate = the entry's id, declared_at = its text) is not labelled with that text (law 4): it is a
    FINDING, counted and named apart, on the reader's print and the audit receipt. Its slot treatment is item 4(a)'s
    (excluded, no slot) until the architect rules it, so the members are exactly the test above's. A page whose
    binding carried another label (soccer-expansion-v1's, another declared_at) carries nothing."""
    got = _window_62(ledger)
    w_export("SA")
    _drop_rows({got[3][0], got[9][0]})
    first = (got[3][1] + timedelta(hours=1)).isoformat()            # after got[3]'s kickoff, before got[9]'s
    _page("p1_other_label", (got[0][1] - timedelta(hours=1)).isoformat(),
          {"SA": {"state": "exporting", "candidate": "soccer-expansion-v1", "declared_at": "2026-10-07T15:17:38Z"}})
    _page("p2_other_stamp", (got[1][1] - timedelta(hours=1)).isoformat(),
          {"SA": {"state": "exporting", "candidate": "leagues-sa-v1", "declared_at": "2026-11-02T18:10:00Z"}})
    _page("p3_carrying", first, {"SA": {"state": "exporting", "candidate": "leagues-sa-v1", "declared_at": W_AT_TEXT}})
    _page("p4_later", (got[20][1]).isoformat(),
          {"SA": {"state": "exporting", "candidate": "leagues-sa-v1", "declared_at": W_AT_TEXT}})
    w = lw.read(("SA",), now=W_NOW)["SA"]
    kept = [m for m, _ in got if m not in {got[3][0], got[9][0]}]
    assert w["members"] == kept[:60] and w["n"] == 60 and w["state"] == "ready"          # slots as item 4(a)'s
    assert w[lw.NO_ROW] == [got[3]] and w[lw.NO_ROW_ON_TAG] == [got[9]]
    assert (w["excluded"][lw.NO_ROW], w["excluded"][lw.NO_ROW_ON_TAG]) == (1, 1)
    assert w["first_carrying_page"] == first and w["first_carrying_file"] == f"{lw.EXPORT_PREFIX}p3_carrying.json"
    out = lw.lines({"SA": w}, W_NOW)
    assert (f"  - excluded (no slot): {lw.NO_ROW_TEXT} 1 (listed below) · {lw.NO_ROW_ON_TAG_TEXT} 1 (listed below)"
            in out)
    i = out.index("  - SA · " + NO_ROW_LINE.format(n=1))
    assert out[i + 1:i + 4] == [f"    - match {got[3][0]} · kickoff {got[3][1]:%Y-%m-%dT%H:%M:%SZ}",
                                "  - SA · " + FINDING_LINE.format(n=1, first=f"exported_at {first}"),
                                f"    - match {got[9][0]} · kickoff {got[9][1]:%Y-%m-%dT%H:%M:%SZ}"]
    assert not any(str(got[9][0]) in x for x in out[:i + 2])          # never under item 4(a)'s text
    a = lw.score(w, now=W_NOW)["audit"]
    assert a[lw.NO_ROW] == [got[3]] and a[lw.NO_ROW_ON_TAG] == [got[9]] and a["first_carrying_page"] == first
    assert lw.audit_lines("SA", a)[-4:] == out[i:i + 4]               # the receipt carries the same lines


@pytest.mark.usefixtures("iso_db")
@pytest.mark.parametrize("damage", ["truncated", "no_predictions", "not_an_object"])
def test_222_4a_an_export_file_that_cannot_be_read_refuses_the_read_and_the_score_never_a_no_row_exclusion(
        ledger, damage):
    """The rows decide the members (item 4(a)), so a file that cannot be read never drops its games under a cause the
    reader never established (law 4): read() refuses the league naming the file, score() raises naming it, and
    nothing is added to the no-row cause."""
    got = _window_62(ledger)
    w_export("SA")
    w = lw.read(("SA",), now=W_NOW)["SA"]
    assert w["state"] == "ready" and w[lw.NO_ROW] == []
    (f,) = Path("exports").glob(f"{lw.EXPORT_PREFIX}*.json")
    if damage == "truncated":
        f.write_bytes(f.read_bytes()[:-20])
    elif damage == "no_predictions":
        f.write_text(json.dumps({"exported_at": "2026-01-01T00:00:00", "rows": []}))
    else:
        f.write_text(json.dumps([{"match_id": got[0][0]}]))
    r = lw.read(("SA",), now=W_NOW)["SA"]
    assert "refused" in r and str(f) in r["refused"] and "cannot be read" in r["refused"]
    assert lw.NO_ROW not in r and "members" not in r
    assert any(x.startswith("SA · REFUSED (leagues-sa-v1): export files that cannot be read")
               for x in lw.lines({"SA": r}, W_NOW))
    with pytest.raises(lw.WindowRefused, match="cannot be read") as err:
        lw.score(w, now=W_NOW)
    assert str(f) in str(err.value)


@pytest.mark.usefixtures("iso_db")
def test_222_4a_score_with_no_export_dir_re_derives_the_cohort_on_the_reads_own_directory(ledger, tmp_path):
    """score() with no export_dir reads the rows from the directory the read was given (window["export_dir"]), never
    the default exports/: the same 60, every member's row present on the audit."""
    got = _window_62(ledger)
    host = tmp_path / "host_exports"
    w_export("SA", export_dir=str(host))
    assert not Path("exports").exists()
    w = lw.read(("SA",), now=W_NOW, export_dir=str(host))["SA"]
    assert w["state"] == "ready" and w["members"] == [m for m, _ in got[:60]] and w["export_dir"] == str(host)
    r = lw.score(w, now=W_NOW)
    assert r["n"] == 60 and r["match_ids"] == w["members"]
    assert (r["audit"]["present"], r["audit"]["missing"], r["audit"][lw.NO_ROW]) == (60, 0, [])


@pytest.mark.usefixtures("iso_db")
def test_222_4b_pd_is_read_checked_and_fenced_on_the_fours_path_at_the_stamp(real_ledger):
    """Item 4(b): PD in DECLARATION_IDS; checked() reads leagues-pd-v1 as written though PD is the surviving set (any
    other surviving league is still refused); guards_backtest's fence covers PD's 2026/27 games after the stamp, a
    walk cut at or before it allowed; the receipts that can be cut count PD's window as fenced."""
    assert lw.DECLARATION_IDS["PD"] == "leagues-pd-v1" and lw.READ_CODES[0] == "PD"
    assert lw.checked("PD", REAL["leagues-pd-v1"]) == (STAMP, FROZEN)
    other = {**REAL["leagues-sa-v1"]}
    from unittest import mock
    with mock.patch.object(lw, "surviving", lambda: ["PD", "SA"]):
        with pytest.raises(lw.WindowRefused, match=r"surviving set.*\(R8\)"):
            lw.checked("SA", other)                                    # not ruled: still refused
    assert lw.fence_cutoff("PD", SEASON) == STAMP and lw.fence_cutoff("PD", "2025/26") is None
    assert sx.guards_backtest("PD", SEASON, through=STAMP) is None
    why = sx.guards_backtest("PD", SEASON)
    assert why and "PD 2026/27 is declared (leagues-pd-v1, declared_at 2026-11-02T18:10:00Z)" in why
    _comps()
    for i, ko in enumerate((BETWEEN, AFTER)):
        _game(700 + i, "PD", ko)
        for sel, (bid, ask) in A.items():
            _kal(700 + i, sel, bid, ask, ko - timedelta(minutes=30), market="1X2")
    rec = paper.close_record(30, now=datetime(2026, 11, 4))["PD"]
    assert (rec["n"], rec["fenced_window"]) == (1, 1)


def _pd_confirming(path, verdict_at, *extra):
    """The soccer-expansion-v1 record confirming PD (no frozen cohort: the provisional first 60), with `extra`."""
    sxe = {k: v for k, v in REAL[sx.EID].items() if k != "confirmation_cohort"}
    sxe["run"] = {**sxe["run"], "ids_file": None}
    sxe["verdict"] = {**sxe["verdict"], "at": verdict_at}
    path.write_text(json.dumps([sxe, *extra]))


@pytest.mark.usefixtures("iso_db")
def test_222_4b_the_soccer_expansion_confirmation_walks_pd_through_the_cut_and_leaves_the_window_fenced(
        real_ledger, monkeypatch, tmp_path):
    """The collision, built as the fence and left for the architect: soccer-expansion-v1's confirmation reads no PD
    figure after leagues-pd-v1's stamp. Its walk is cut at the stamp (the rows before it equal the uncut walk's), its
    cohort fixtures after the stamp stay pending as `fenced` and are listed, the read is not complete (--record
    refuses), the cohort itself is unchanged; with leagues-pd-v1's verdict recorded the fence lifts and they score."""
    from src.walters.soccer_backtest import run_soccer_backtest
    monkeypatch.setattr(reg, "IDS_DIR", str(tmp_path / "ids"))
    _comps()
    verdict = datetime(2026, 10, 20, 12, 0)
    import random
    rng = random.Random(222)
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, Team
    with session_scope() as s:
        c = s.query(Competition).filter_by(code="PD").one()
        ts = [Team(sport=Sport.SOCCER, name=f"PD222 {i}") for i in range(6)]
        s.add_all(ts)
        s.flush()
        kos = ([datetime(2026, 8, 15, 15, 0) + timedelta(days=k) for k in range(45)]
               + [verdict + timedelta(hours=18 * k) for k in range(1, 31)])
        for n, ko in enumerate(kos):
            h, a = rng.sample(range(6), 2)
            hs, as_ = rng.randint(0, 3), rng.randint(0, 3)
            s.add(Match(id=8000 + n, sport=Sport.SOCCER, competition_id=c.id, season=SEASON, utc_date=ko,
                        status=MatchStatus.FINISHED, stage=f"Regular Season - {n + 1}", home_team_id=ts[h].id,
                        away_team_id=ts[a].id, home_score=hs, away_score=as_, home_score_90=hs, away_score_90=as_,
                        status_raw="FT"))
    cohort = [(8000 + n, ko) for n, ko in enumerate(kos) if ko > verdict]
    after = [m for m, ko in cohort if ko > STAMP]
    before = [m for m, ko in cohort if ko <= STAMP]
    assert (len(before), len(after)) == (17, 13)
    _pd_confirming(real_ledger, verdict.strftime("%Y-%m-%dT%H:%M:%SZ"), REAL["leagues-pd-v1"])
    r = sx.confirmation_read()
    assert [x["id"] for x in r["fenced_window"]] == after and "addendum 222 item 4(b)" in r["fence_note"]
    assert r["scored_ids"] == before and r["n"] == 17 and not r["complete"] and r["cohort_size"] == 30
    assert {x["id"]: x["status"] for x in r["pending"]} == {m: "fenced" for m in after}
    from click.testing import CliRunner

    import cli
    res = CliRunner().invoke(cli.cli, ["soccer-expansion-confirm"])
    assert res.exit_code == 0, res.output
    assert "  FENCED 13 cohort fixture(s), never scored here (fenced: a window game of the league's" in res.output
    assert f"PD {after[0]} {cohort[17][1]:%Y-%m-%dT%H:%MZ}" in res.output and "pending 13: {'fenced': 13}" in res.output
    res = CliRunner().invoke(cli.cli, ["soccer-expansion-confirm", "--record", "--ruling", "x"])
    assert res.exit_code == 2 and "REFUSED: the read is incomplete" in res.output     # never recorded over a fence
    # with leagues-pd-v1's verdict recorded the fence lifts (R8): the same cohort, all 30 scored
    _pd_confirming(real_ledger, verdict.strftime("%Y-%m-%dT%H:%M:%SZ"),
                   {**REAL["leagues-pd-v1"], "verdict": {"verdict": "REJECT"}})
    assert lw.fence_cutoff("PD", SEASON) is None
    full = sx.confirmation_read()
    assert full["fenced_window"] == [] and full["n"] == 30 and full["fence_note"] is None
    rows = {x["match_id"]: x for x in run_soccer_backtest("PD", SEASON, sx.MIN_PRIOR, dixon_coles_rho=-0.1,
                                                          elo_goal_coeff=0.0008, stage_filter=sx.is_regular,
                                                          batch_same_kickoff=sx.BATCH_SAME_KICKOFF,
                                                          confirmation_scoring=True)}
    key = {"H": "p_home", "D": "p_draw", "A": "p_away"}
    pre = [sx.ll3(rows[m][key[rows[m]["actual"]]]) for m in before]
    assert r["log_loss"] == sum(pre) / len(pre)                     # the cut walk's figures are the uncut walk's
