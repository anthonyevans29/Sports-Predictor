"""THE WOULD-BE LINE (ARCHITECT 2026-11-02 11:20 ET, addendum 217 item 4), verbatim: "4. RULED, a follow-up PR (small,
after the v2 harness): #446's measurement keeps accruing on paper — exec_cohorts and the closing page's hold check gain
one cohort line for NFL while uncertified, "would-be PLAY (uncertified, unstaked)", reading the record-only would-be
call with the same QB-flag / unread-list classification, never pooled with PLAY, never a position. #446's read at
thirty rows counts those rows too, labelled. Not blocking #778."

Pins, on synthetic closing files (tests/test_void_redated.py write_closing) and a throwaway SQLite (iso_db): (1) a
would-be row lands on its own line with its QB classification, and the Desk blocks are desk_policy.annotate's own with
the market-only rule on (tests/test_nfl_market_only_214.py's battery), so the real shape is read; (2) the PLAY cells,
the n=30 counter and the pooled line are what they are without the would-be rows; (3) each row decides from what it
carries, so a later certification (a registry fixture) moves no count and keeps the line (only its head text follows the
registry); certified with neither a would-be row nor a #446 row, there is no line; an unread registry, a missing entry
and an empty registry are never judged certified, and the head names nfl_predict.MODEL_VERSION; (4) #446's thirty-row count is PLAY + would-be, each labelled; (5) the other families' lines
are byte-identical; (6) the closing summary block and the run receipt carry the line and the phone page's text does not
(ARCHITECT 2026-11-02 18:05 ET, addendum 223 item 3: "the per-game line comes OFF THE PHONE PAGE's text; it lives in
the summary block and the receipt only"; #778's pin, no PLAY on the NFL closing or slate page, stands byte for byte in
tests/test_nfl_market_only_214.py), the PASS count, the priority and every other family's rows unchanged, and a failed
certification read or import never blocks the page. Read-only: the tracked registry is read, never written."""
import json
import re
from datetime import timedelta
from pathlib import Path

import pytest

from src.db.schema import MatchStatus
from src.walters import desk_policy as dp
from src.walters import exec_cohorts as xc
from src.walters import registry as reg
from tests.test_exec_cohorts import (FAMILIES_TEXT, KO, LATE, _comps, _families, _match, _section, desk, row)
from tests.test_nfl_market_only_214 import NOW as MO_NOW, annotate, nfl_rows, pred
from tests.test_record_vs_close import iso_db  # noqa: F401  (a fixture: a throwaway SQLite, cwd = tmp_path)
from tests.test_void_redated import _closing, write_closing

pytestmark = pytest.mark.usefixtures("iso_db")

LABEL = "would-be PLAY (uncertified, unstaked)"           # the ruled label, written out (not imported)
HEAD = ("- NFL · would-be PLAY (uncertified, unstaked) (addendum 217 item 4: the Desk's record-only would-be call, "
        "desk.market_only_hold, {state}; notional at desk.exec.cost, never pooled with PLAY, never a position): ")
UNCERT = "while the registry reads nfl_elo_v1 uncertified (nfl-elo-v1)"
C446 = ("#446's thirty-row count (addendum 44 item 9: rows with a QB flag or an unread list, closing runs from the hold "
        "of 2026-10-11)")


@pytest.fixture
def certified(tmp_path, monkeypatch):
    """A registry fixture whose nfl-elo-v1 entry is certified (the state before addendum 214, and after a PASS read)."""
    entries = json.loads(Path(reg.LEDGER).read_text())
    for e in entries:
        if e.get("model_version") == "nfl_elo_v1":
            e["certification"] = "certified (fixture)"
    p = tmp_path / "experiments_certified.json"
    p.write_text(json.dumps(entries))
    monkeypatch.setattr(reg, "LEDGER", str(p))
    return p


def _mo():
    """desk_policy.annotate's own NFL desk blocks, the market-only rule on (production): {home: desk}."""
    return {r["home_team"]: r["desk"] for r in annotate("nfl", nfl_rows())["predictions"]}


KO2 = KO + timedelta(days=15)


def _seed():
    _comps()
    _match(2001, "NFL", "N1", "M1", hs=24, aw=17)
    _match(5001, "NFL", "Qb", "Qb away", ko=KO2, hs=21, aw=14)
    _match(5002, "NFL", "InjEmpty", "InjEmpty away", ko=KO2, hs=10, aw=13)
    _match(5003, "NFL", "Play", "Play away", ko=KO2, status=MatchStatus.SCHEDULED)
    _match(5004, "NFL", "Floor", "Floor away", ko=KO2, hs=30, aw=3)
    _match(1002, "MLB", "A2", "B2", ko=LATE + timedelta(hours=1), hs=1, aw=4)


def _world(tmp_path, with_would_be=True, seed=True):
    """NFL: one PLAY of main (before the rule, QB-flagged, 0-4, a hit) in a closing run of 10-18; and, in a run of 11-02,
    the market-only rows: Qb (QB-flagged, a hit), InjEmpty (QB unread, a miss), Play (clean, open) and Floor (its
    would-be call is PASS: not a would-be PLAY). MLB: one clean 0-4 PLAY (a miss) from the pre-registration on."""
    if seed:
        _seed()
    ex = tmp_path / "exports"
    mo = _mo()
    assert [mo[k]["market_only_hold"]["would_call"] for k in ("Qb", "InjEmpty", "Play", "Floor")] == \
        ["PLAY", "PLAY", "PLAY", "PASS"]
    write_closing(ex, KO - timedelta(minutes=30), [
        row(2001, "N1", "M1", desk(edge=3.0, cost=0.6, tags=("QB-flagged half units",)))], fam="NFL")
    ko2 = KO2
    rows = [row(5004, "Floor", "Floor away", mo["Floor"], ko=ko2)]
    if with_would_be:
        rows = [row(5001, "Qb", "Qb away", mo["Qb"], ko=ko2), row(5002, "InjEmpty", "InjEmpty away", mo["InjEmpty"],
                                                                     ko=ko2),
                row(5003, "Play", "Play away", mo["Play"], ko=ko2)] + rows
    write_closing(ex, ko2 - timedelta(minutes=35), rows, fam="NFL")
    write_closing(ex, LATE, [row(1002, "A2", "B2", desk(edge=2.0, cost=0.55), ko=LATE + timedelta(hours=1))],
                  fam="MLB")
    return ex, mo


def _lines(txt, prefix):
    return [x for x in txt.splitlines() if x.startswith(prefix)]


# ---- (1) its own line, the QB classification, the real shape ------------------------------------------------------

def test_a_would_be_row_lands_on_its_own_line_with_its_qb_classification(tmp_path):
    ex, mo = _world(tmp_path)
    t = xc.tally(ex)
    q, i, p = mo["Qb"], mo["InjEmpty"], mo["Play"]
    assert "QB-flagged half units" in q["tags"] and "QB unread half units" in i["tags"]
    assert not set(xc.QB_TAGS) & set(p["tags"])
    w = t["would_be"]["NFL"]
    assert (w[xc.QB_OUT]["plays"], w[xc.QB_OUT]["w"], w[xc.QB_OUT]["l"]) == (2, 1, 1)
    assert (w[xc.QB_CLEAN]["plays"], w[xc.QB_CLEAN]["open"]) == (1, 1)
    # notional at the would-be units, at the exec cost the chain sized (desk_policy.call_exec_block)
    won = q["market_only_hold"]["would_units"] * (1 / q["exec"]["cost"] - 1)
    lost = -i["market_only_hold"]["would_units"]
    assert w[xc.QB_OUT]["units_sum"] == pytest.approx(won + lost) and w[xc.QB_OUT]["priced"] == 2
    cells = {x: sum(1 for d in (q, i, p) if xc.cohort_of(d["exec"]["edge_pp"]) == x)
             for x in ("exec >= 4", "0 < exec < 4", "exec <= 0", "exec unknown")}
    assert w["exec"] == cells
    (line,) = _lines(_section(ex), f"- NFL · {LABEL}")
    assert line == (HEAD.format(state=UNCERT) + f"3 · QB-flagged or unread 2 · W-L-P 1-1-0 · {won + lost:+.2f}u · "
                    f"open 0 · void 0 · QB inputs clean 1 · W-L-P 0-0-0 · units — · open 1 · void 0 · by exec: "
                    + " · ".join(f"{k} {v}" for k, v in cells.items())
                    + f" · {C446}: PLAY 1 + {LABEL} 2 = 3 of 30")


def test_the_would_be_call_is_never_a_play_cell_and_never_a_position(tmp_path):
    ex, _ = _world(tmp_path)
    t = xc.tally(ex)
    nfl = {k: v for (f, k), v in t["cells"].items() if f == "NFL"}
    assert list(nfl) == ["0 < exec < 4, QB"] and nfl["0 < exec < 4, QB"]["plays"] == 1      # main's PLAY of 10-18 only
    txt = _section(ex)
    assert "- NFL · exec >= 4: PLAY 0\n" in txt and "- NFL · 0 < exec < 4, QB inputs clean (the pre-registered " \
        "cohort): PLAY 0\n" in txt
    assert "- NFL · left out: none\n" in txt                       # a would-be row is not left out: it is not a PLAY


# ---- (2) PLAY cells and the n=30 counter unchanged -----------------------------------------------------------------

def test_play_cells_the_n30_counter_and_the_pooled_line_are_unchanged(tmp_path):
    ex, _ = _world(tmp_path / "with")
    bare, _ = _world(tmp_path / "without", with_would_be=False, seed=False)
    a, b = xc.tally(ex), xc.tally(bare)
    for k in ("cells", "left_out", "floor_blocked", "cohort_graded", "cohort_before", "cohort_undated", "families"):
        assert a[k] == b[k], k
    assert a["cohort_graded"] == 1                                 # MLB's clean miss, from the pre-registration on
    sa = _section(ex).replace(str(ex), "EX").splitlines()
    sb = _section(bare).replace(str(bare), "EX").splitlines()
    keep = lambda lines: [x for x in lines if not x.startswith(f"- NFL · {LABEL}")]     # noqa: E731
    assert keep(sa) == keep(sb)                                    # every other line, the intro included, byte for byte
    assert sa[-1] == sb[-1] and sa[-1].startswith("- The pre-registered cohort") and "graded 1 of 30" in sa[-1]
    assert xc.console_line(a) == xc.console_line(b)
    (wb,) = _lines("\n".join(sb), f"- NFL · {LABEL}")
    assert wb.endswith(f"): 0 · {C446}: PLAY 1 + {LABEL} 0 = 1 of 30")


# ---- (3) certified: no line, byte-identical; unread: never judged certified ----------------------------------------

def test_rows_written_while_uncertified_count_the_same_after_a_certification(tmp_path, monkeypatch):
    """Each row decides from what it carries (pass_kind market_only, its market_only_hold), never from the registry's
    state today: the closing files written while NFL was uncertified are re-read on every results-tally run, and a
    later certification (a registry fixture) moves no count, drops no row from #446's thirty-row count and keeps the
    line; only the head's state text follows the registry."""
    ex, _ = _world(tmp_path)
    before = xc.tally(ex)
    line_before = _lines(_section(ex), f"- NFL · {LABEL}")
    entries = json.loads(Path(reg.LEDGER).read_text())
    for e in entries:
        if e.get("model_version") == "nfl_elo_v1":
            e["certification"] = "certified (fixture)"
    p = tmp_path / "experiments_certified.json"
    p.write_text(json.dumps(entries))
    monkeypatch.setattr(reg, "LEDGER", str(p))
    assert reg.certification_of("nfl_elo_v1") == ("certified", "nfl-elo-v1")
    after = xc.tally(ex)
    assert after["certification"] == ("certified", "nfl-elo-v1")
    for k in ("cells", "left_out", "floor_blocked", "cohort_graded", "cohort_before", "cohort_undated", "families",
              "would_be", "count_446"):
        assert after[k] == before[k], k
    assert after["count_446"] == {"NFL": {"play": 1, "would_be": 2, "before": 0, "undated": 0}}
    (line,) = _lines(_section(ex), f"- NFL · {LABEL}")
    certified_state = "rows recorded while uncertified; the registry now reads nfl_elo_v1 certified (nfl-elo-v1)"
    assert line == line_before[0].replace(UNCERT, certified_state)
    assert line.endswith(f"{C446}: PLAY 1 + {LABEL} 2 = 3 of 30")


def test_certified_the_whole_section_keeps_446s_count_and_only_the_head_text_moves(tmp_path, certified):
    """Main's families fixture carries a QB-flagged NFL PLAY of 10-18, a #446 row: certified, the line and its count
    still print (only the head's state text differs from the uncertified section); every other line is main's."""
    from tests.test_exec_cohorts import FAMILIES_TEXT_UNCERTIFIED
    ex = _families(tmp_path)
    assert xc.section(xc.tally(ex), ex) == FAMILIES_TEXT_UNCERTIFIED.format(ex=ex).replace(
        UNCERT, "rows recorded while uncertified; the registry now reads nfl_elo_v1 certified (nfl-elo-v1)")
    keep = [x for x in xc.section(xc.tally(ex), ex).splitlines() if not x.startswith(f"- NFL · {LABEL}")]
    assert keep == FAMILIES_TEXT.format(ex=ex).splitlines()


def test_certified_with_no_would_be_row_and_no_446_row_there_is_no_line(tmp_path, certified):
    """Certified, an NFL closing with a QB-clean PLAY only (no would-be row, no #446 row): no line, no #446 text, the
    section is main's."""
    _comps()
    ex = tmp_path / "exports"
    _match(2001, "NFL", "N1", "M1", hs=24, aw=17)
    write_closing(ex, KO - timedelta(minutes=30), [row(2001, "N1", "M1", desk(edge=3.0, cost=0.6))], fam="NFL")
    t = xc.tally(ex)
    assert t["would_be"] == {} and t["count_446"] == {} and xc._would_be_line("NFL", t) is None
    txt = _section(ex)
    assert LABEL not in txt and "#446" not in txt


def test_the_tracked_registry_reads_nfl_uncertified_and_an_unread_one_is_never_certified(tmp_path, monkeypatch):
    assert reg.certification_of("nfl_elo_v1") == ("uncertified", "nfl-elo-v1")
    assert reg.certification_of("nfl_elo_v1", str(tmp_path / "nope.json"))[0] == "unread"
    (tmp_path / "bad.json").write_text("{not json")
    assert reg.certification_of("nfl_elo_v1", str(tmp_path / "bad.json")) == \
        ("unread", "the registry cannot be read: JSONDecodeError")
    monkeypatch.setattr(reg, "LEDGER", str(tmp_path / "nope.json"))
    ex, _ = _world(tmp_path)
    (line,) = _lines(_section(ex), f"- NFL · {LABEL}")
    assert line.startswith(HEAD.format(
        state=f"certification not read for nfl_elo_v1: no registry file at {tmp_path / 'nope.json'}") + "3 · ")


def test_a_missing_entry_or_an_empty_registry_never_reads_certified(tmp_path):
    """Law 4 (and production_allowed's own rule: an id the registry lacks is not allowed): a model_version with no
    entry, and a registry that is an empty list, read "unread", never "certified"."""
    assert reg.certification_of("nfl_elo_v2") == ("unread", "no registry entry for nfl_elo_v2")
    (tmp_path / "empty.json").write_text("[]")
    assert reg.certification_of("nfl_elo_v1", str(tmp_path / "empty.json")) == \
        ("unread", "no registry entry for nfl_elo_v1")
    (tmp_path / "obj.json").write_text("{}")
    assert reg.certification_of("nfl_elo_v1", str(tmp_path / "obj.json"))[0] == "unread"
    assert reg.certification_of("", str(tmp_path / "empty.json"))[0] == "unread"


def test_the_line_names_the_model_the_registry_is_read_on(tmp_path, monkeypatch):
    """The head names nfl_predict.MODEL_VERSION, not a fixed nfl_elo_v1: a new id with no entry reads "certification
    not read for <id>", and an entry for that id is named by its own model_version beside its own entry id. The counts
    do not move (each row decides from what it carries)."""
    from src.walters import nfl_predict
    ex, _ = _world(tmp_path)
    base = xc.tally(ex)
    monkeypatch.setattr(nfl_predict, "MODEL_VERSION", "nfl_elo_v2")
    t = xc.tally(ex)
    assert (t["certification"], t["model_version"]) == (("unread", "no registry entry for nfl_elo_v2"), "nfl_elo_v2")
    assert (t["would_be"], t["count_446"]) == (base["would_be"], base["count_446"])
    (line,) = _lines(_section(ex), f"- NFL · {LABEL}")
    assert line.startswith(HEAD.format(state="certification not read for nfl_elo_v2: no registry entry for "
                                             "nfl_elo_v2") + "3 · ")
    assert "nfl_elo_v1" not in line
    entries = json.loads(Path(reg.LEDGER).read_text()) + [{"id": "nfl-elo-v2", "model_version": "nfl_elo_v2",
                                                      "certification": "UNCERTIFIED — fixture"}]
    p = tmp_path / "v2.json"
    p.write_text(json.dumps(entries))
    monkeypatch.setattr(reg, "LEDGER", str(p))
    (line,) = _lines(_section(ex), f"- NFL · {LABEL}")
    assert line.startswith(HEAD.format(state="while the registry reads nfl_elo_v2 uncertified (nfl-elo-v2)") + "3 · ")


def test_a_failed_certification_read_never_fails_the_section(tmp_path, monkeypatch):
    """results-tally's section degrades the same way: an exception from the registry read is "unread" (the line prints
    labelled "certification not read"), never the section's failure; the counts do not move."""
    ex, _ = _world(tmp_path)
    base = xc.tally(ex)

    def boom(*a, **k):
        raise TypeError("malformed entry")
    monkeypatch.setattr(reg, "certification_of", boom)
    t = xc.tally(ex)
    assert t["certification"] == ("unread", "TypeError")
    assert (t["would_be"], t["count_446"]) == (base["would_be"], base["count_446"])
    (line,) = _lines(_section(ex), f"- NFL · {LABEL}")
    assert line.startswith(HEAD.format(state="certification not read for nfl_elo_v1: TypeError") + "3 · ")


# ---- (4) #446's thirty-row count -----------------------------------------------------------------------------------

def test_446s_count_is_play_plus_would_be_labelled_and_reads_at_thirty():
    t = {"certification": ("uncertified", "nfl-elo-v1"), "would_be": {},
         "model_version": "nfl_elo_v1", "count_446": {"NFL": {"play": 12, "would_be": 18, "before": 2}}}
    assert xc._would_be_line("NFL", t).endswith(
        f"): 0 · {C446}: PLAY 12 + {LABEL} 18 = 30 n=30 reached — for the architect's read (no verdict is computed "
        "here) · before the hold, not counted 2")
    t["count_446"]["NFL"]["would_be"] = 17
    assert xc._would_be_line("NFL", t).endswith(f"= 29 of 30 · before the hold, not counted 2")
    t["count_446"]["NFL"]["undated"] = 1
    assert xc._would_be_line("NFL", t).endswith(f"= 29 of 30 · before the hold, not counted 2 · undated, not counted 1")
    assert xc.READ_446_AT_N == 30 and xc.HOLD_446_FROM.isoformat() == "2026-10-11T04:00:00"


def test_a_qb_tagged_play_before_the_hold_is_beside_the_count(tmp_path):
    _comps()
    ex = tmp_path / "exports"
    early = KO - timedelta(days=9)                                  # 2026-10-09: before the hold of 10-11
    _match(2101, "NFL", "E1", "F1", ko=early, hs=3, aw=7)
    write_closing(ex, early - timedelta(minutes=35), [
        row(2101, "E1", "F1", desk(edge=2.0, cost=0.5, tags=("QB unread half units",)), ko=early)], fam="NFL")
    (line,) = _lines(_section(ex), f"- NFL · {LABEL}")
    assert line.endswith(f"{C446}: PLAY 0 + {LABEL} 0 = 0 of 30 · before the hold, not counted 1")


def test_a_qb_tagged_row_with_no_run_start_is_undated_never_before_the_hold(tmp_path):
    """A closing file with no closing-block start and no stamp in its name (redated.closing_rows allows it) has no run
    start: its QB-tagged rows (a PLAY and a would-be PLAY) are not known to precede 2026-10-11, so they print as
    undated beside the count (the n=30 counter's own reading), never as "before the hold"."""
    _seed()
    ex = tmp_path / "exports"
    mo = _mo()
    p = write_closing(ex, KO2 - timedelta(minutes=35), [
        row(2001, "N1", "M1", desk(edge=3.0, cost=0.6, tags=("QB-flagged half units",))),
        row(5001, "Qb", "Qb away", mo["Qb"], ko=KO2)], fam="NFL")
    doc = json.loads(p.read_text())
    del doc["closing"]["start"]
    (ex / "closing_NFL_nostamp.json").write_text(json.dumps(doc))
    p.unlink()
    t = xc.tally(ex)
    assert t["count_446"] == {"NFL": {"play": 0, "would_be": 0, "before": 0, "undated": 2}}
    (line,) = _lines(_section(ex), f"- NFL · {LABEL}")
    assert line.endswith(f"{C446}: PLAY 0 + {LABEL} 0 = 0 of 30 · undated, not counted 2")
    assert "before the hold" not in line


# ---- (5) the other families --------------------------------------------------------------------------------------

def test_no_other_family_gets_the_line_whatever_its_rows_carry(tmp_path):
    _comps()
    ex = tmp_path / "exports"
    mo = _mo()
    _match(1101, "MLB", "Qb", "Qb away", hs=5, aw=1)
    write_closing(ex, KO - timedelta(minutes=35), [row(1101, "Qb", "Qb away", mo["Qb"])], fam="MLB")
    t = xc.tally(ex)
    assert t["would_be"] == {} and t["count_446"] == {}
    assert LABEL not in _section(ex) and xc._would_be_line("MLB", t) is None


def test_the_label_the_tags_and_the_kind_are_the_desks_and_the_closing_pages(tmp_path):
    cl = _closing()
    assert xc.WOULD_BE == cl.WOULD_BE == LABEL and LABEL in xc.RULING_217_4
    assert cl.MARKET_ONLY_KIND == dp.NFL_MARKET_ONLY_KIND
    assert next(h for h in cl.CLOSING_HOLDS if "tags_any" in h)["tags_any"] == xc.QB_TAGS == tuple(cl.QB_TEXT)
    assert xc.WOULD_BE_FAMILIES == cl.WOULD_BE_FAMILIES == dp.NFL_MARKET_ONLY_SPORTS


# ---- (6) the closing page's hold check -----------------------------------------------------------------------------

def _page_doc():
    ids = {"Qb": 1, "InjEmpty": 2, "Play": 3, "Floor": 4, "Quar": 5}
    rows = [pred(h, *a, match_id=ids[h], **kw) for h, a, kw in (
        ("Qb", (0.64, 0.55), {"input_quality": nfl_rows()[2]["input_quality"]}),
        ("InjEmpty", (0.64, 0.55), {"input_quality": nfl_rows()[3]["input_quality"]}),
        ("Play", (0.64, 0.55), {}), ("Floor", (0.56, 0.55), {}),
        ("Quar", (0.75, 0.55), {"market_divergence_pp": 20.0, "quarantine": True}))]
    return annotate("nfl", rows), set(ids.values())


def _page(fam="NFL"):
    cl = _closing()
    doc, ids = _page_doc()
    rows = cl.desk_rows(doc, ids, MO_NOW, fam=fam)
    title, body, high = cl.page_text(fam, MO_NOW + timedelta(minutes=300), MO_NOW, rows, {})
    return cl, rows, body, high


def test_the_would_be_line_is_off_the_phone_page_and_in_the_summary_block_with_the_qb_class():
    """Addendum 223 item 3: the per-game line is in the summary block (one per would-be game, its QB class) and never
    in the phone page's text, which carries no PLAY at all."""
    cl, rows, body, high = _page()
    by = {x["home"]: x for x in rows}
    assert {h for h, x in by.items() if "would_be" in x} == {"Qb", "InjEmpty", "Play"}
    assert [by[h]["would_be"]["qb"] for h in ("Qb", "InjEmpty", "Play")] == \
        ["QB-flagged", "QB list unread", "QB inputs clean"]
    assert all(x["call"] == "PASS" and x["units"] == 0 and x["hold"] is None and x["order"] is None for x in rows)
    lines = body.splitlines()
    q = by["Qb"]["would_be"]
    assert (q["units"], q["exec_edge_pp"]) == (0.5, 7.2)
    assert not any(LABEL in x or "would-be" in x or "record only, not placed" in x for x in lines), lines   # 223 item 3
    assert not any(re.search(r"\bPLAY\b", x) for x in lines), lines                 # #778's pin: no PLAY on the page
    assert all(len(x) <= cl.PAGE_MAX_CHARS for x in lines)
    assert not any("BUY " in x or "HOLD" in x or "paste to the architect" in x for x in lines)   # no order, no hold
    assert "PASS: 5 games" in lines and high is False                                           # never high priority
    assert f"   {LABEL} Qb {q['units']:g}u · exec {q['exec_edge_pp']:+.1f}pp · QB-flagged · record only, not placed" \
        in cl.summary_block(by["Qb"])
    assert [ln for h in ("Qb", "InjEmpty", "Play") for ln in cl.summary_block(by[h]).splitlines() if LABEL in ln] == [
        f"   {LABEL} Qb 0.5u · exec +7.2pp · QB-flagged · record only, not placed",
        f"   {LABEL} InjEmpty 0.5u · exec +7.2pp · QB list unread · record only, not placed",
        f"   {LABEL} Play 1u · exec +7.3pp · QB inputs clean · record only, not placed"]   # one line per would-be game
    assert "would-be" not in cl.summary_block(by["Floor"])


def test_the_closing_page_has_no_would_be_line_when_nfl_is_certified(certified):
    cl, rows, body, high = _page()
    assert not any("would_be" in x for x in rows) and "would-be" not in body and high is False


def test_another_familys_rows_never_carry_it():
    cl, rows, body, _ = _page(fam="MLB")
    assert not any("would_be" in x for x in rows) and "would-be" not in body


@pytest.mark.parametrize("how", ["read", "import"])
def test_a_failed_certification_read_never_blocks_the_page(monkeypatch, how):
    """The page is a money-path surface and the would-be line is the record only: an exception from the registry read
    (a TypeError from a malformed entry) or from the import (an ImportError) degrades to "unread" (the line still
    prints, the would-be rows keep it), and the page goes out as before."""
    import sys

    if how == "read":
        def boom(*a, **k):
            raise TypeError("malformed entry")
        monkeypatch.setattr(reg, "certification_of", boom)
        want = ("unread", "TypeError")
    else:
        monkeypatch.setitem(sys.modules, "src.walters.nfl_predict", None)      # import raises ImportError
        want = ("unread", "ModuleNotFoundError")              # an ImportError
    cl = _closing()
    assert cl.nfl_certification() == want
    cl2, rows, body, high = _page()
    by = {x["home"]: x for x in rows}
    assert {h for h, x in by.items() if "would_be" in x} == {"Qb", "InjEmpty", "Play"}
    assert all(by[h]["would_be"]["certification"] == "unread" for h in ("Qb", "InjEmpty", "Play"))
    assert "PASS: 5 games" in body.splitlines() and high is False
    assert not any(LABEL in x for x in body.splitlines())                       # never on the page (223 item 3)
    assert sum(1 for h in ("Qb", "InjEmpty", "Play") if LABEL in cl2.summary_block(by[h])) == 3


def test_the_closing_runs_receipt_and_summary_carry_it_only_on_the_would_be_row_and_the_page_does_not(box, capsys):
    from tests.test_closing_runs import NOW as C_NOW, at, mc, runs
    assert mc.run("NFL", start=at(35), now=C_NOW) == 0
    out = capsys.readouterr().out                                    # the run's console: the closing summary block
    assert [ln for ln in out.splitlines() if LABEL in ln] == [
        f"   {LABEL} Buffalo 1u · exec +5.3pp · QB inputs clean · record only, not placed"]
    assert not any(LABEL in x or re.search(r"\bPLAY\b", x) for x in box.pages[-1]["body"].splitlines())   # 223 item 3
    got = {x["match_id"]: x for x in runs("NFL")[-1]["desk_rows"]}
    assert got[301]["would_be"] == {"label": LABEL, "pick": "Buffalo", "units": 1, "exec_edge_pp": 5.3,
                                    "qb": "QB inputs clean", "staked": False, "certification": "uncertified"}
    assert [m for m, x in got.items() if "would_be" in x] == [301]
    assert all(x["call"] == "PASS" for x in got.values())


from tests.test_closing_runs import box  # noqa: E402,F401  (the closing-run frame's fixture)


def test_qb_class_reads_the_stable_tags_and_survives_the_hold_row_being_lifted(monkeypatch):
    """Codex P1 on #802: lifting the QB hold is deleting its row from CLOSING_HOLDS; the classification must not need
    that row (a bare next() raised StopIteration and failed the closing run). The two tags stay the hold's tags_any."""
    import deploy.hosting.closing as closing
    hold = next(h for h in closing.CLOSING_HOLDS if "tags_any" in h)
    assert tuple(closing.QB_TEXT) == hold["tags_any"]                  # the stable tags are the hold's own
    flagged = {"tags": ["QB-flagged half units"]}
    unread = {"tags": ["QB unread half units"]}
    both = {"tags": ["QB unread half units", "QB-flagged half units"]}
    clean = {"tags": ["something else"]}
    before = [closing.qb_class(d) for d in (flagged, unread, both, clean)]
    monkeypatch.setattr(closing, "CLOSING_HOLDS", tuple(h for h in closing.CLOSING_HOLDS if "tags_any" not in h))
    after = [closing.qb_class(d) for d in (flagged, unread, both, clean)]
    assert after == before == ["QB-flagged", "QB list unread", "QB-flagged and QB list unread", "QB inputs clean"]
