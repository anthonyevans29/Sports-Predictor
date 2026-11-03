"""ARCHITECT 2026-11-03 07:55 ET, addendum 226 item 4(a) (the records PR, #322 / #754): the roadmap's records. Lane pd:
item 3's moved line (the confirmation record step and earliest_live 2026-11-23 -> 2026-12-22; the 11-22 calendar step
stays) and its live_needs rewritten as the union (addendum 223 item 2(a)). Lane leagues: PD into `competitions`, the
title naming La Liga, step (c)'s text of item 2 (due unchanged, no moved line). Lane pl-availability: addendum 224 item
3's two moved lines (12-20 -> 12-14; 12-21 -> 12-15), the #754 console's count in the step texts (224 items 1 and 4).
The quoted texts below are the architect's, verbatim."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from src import roadmap as rm

ROOT = Path(__file__).resolve().parent.parent

# addendum 226 item 3, the MOVED LINE (lane pd), verbatim
PD_LINE = ("the confirmation record step moves from 2026-11-23 to 2026-12-22, and earliest_live from 2026-11-23 to "
           "2026-12-22: the frozen cohort's fixtures after 2026-11-02T18:10:00Z are fenced by leagues-pd-v1's window "
           "(addendum 223 item 2(a): the confirmation waits, no exemption, no substitution); the record follows "
           "leagues-pd-v1's read the same morning, the day after PD's 60th window game — the recount of 11-03 (#322) "
           "puts the 60th scoreable member in the 12-18/21 round (stored kickoff 2026-12-20T16:00Z, match 16303), whose "
           "last day is Monday 12-21. If the TV selection makes the 60th final earlier in that round, both reads are the "
           "day after it and the steps are done-marked early (222 item 3(a)). No bar moves.")
# addendum 226 item 2, step (c)'s text, verbatim, with FL1's 60th as addendum 229 item 3 corrects it (ARCHITECT
# 2026-11-03 08:40 ET: "names FL1's 60th as match 19478 with one exclusion"; 226 item 2 wrote "FL1 2027-01-16 (match
# 19476)", read on the laptop's database, 229 item 1)
STEP_C = ("ELC 2026-12-06 (match 9834; 12 of the 11-03/04 round excluded by cause); then PD 2026-12-20 (match 16303; one "
          "game excluded), SA 2026-12-20 (match 17433; one excluded), BL1 2027-01-12 (match 18554, from an 11-09 "
          "declaration, pending it), FL1 2027-01-16 (match 19478; one excluded); PD's and SA's December rounds are "
          "stored at placeholder kickoffs and run to Monday 12-21; the reader's count is the count, and every game "
          "assumed to get a three-way close")
# addendum 229 item 3, the one sentence from item 2 the step carries, verbatim
CLOSE_SHARE = ("the close share since the hourly capture tier of 10-24 is 100% in each league on the host's copy (the "
               "11-03 read), which is what makes the 'every game gets a close' assumption honest; the reader's count is "
               "the count")
# addendum 229 item 3: the host-copy consoles (#322, 11-03)
HOST_CONSOLES = ("issuecomment-6604829516", "issuecomment-6605077150")
# addendum 224 item 3, the two MOVED LINES (lane pl-availability), verbatim
PL_LINE1 = ("the calendar step 'the 60th window game is final' moves from 2026-12-20 to 2026-12-14: the count from the "
            "stored schedule (#754, 2026-11-02) puts the 60th window game ninth in the 12-12 round, whose kickoffs are "
            "stored as placeholders pending TV selection; the step's date is that round's last day. No bar moves.")
PL_LINE2 = "the one read moves from 2026-12-21 to 2026-12-15, the day after. No bar moves."
# addendum 224 item 1, the count (#754 issuecomment-6590791400), verbatim
COUNT = ("380 stored PL 2026/27 games, 0 cancelled/postponed/stale, 89 before the window, 0 between the first host page "
         "(17:30:18Z) and the window; the first window game kicks off AT the window stamp (match 9247, "
         "2026-11-02T20:00:00Z); fixtures per UTC kickoff date up to the 60th: 11-02 1 · 11-06 1 · 11-07 4 · 11-08 5 · "
         "11-21 7 · 11-22 2 · 11-23 1 · 11-27 1 · 11-28 3 · 11-29 6 · 12-02 10 · 12-05 10 · 12-12 9; the 60th is the "
         "NINTH fixture of the 12-12 round (match 9315, stored kickoff 2026-12-12T15:00:00Z); every game assumed to "
         "finish with a three-way close — a projection, not a floor")


def _doc() -> dict:
    return json.loads((ROOT / "docs" / "roadmap.json").read_text(encoding="utf-8"))


def _lane(doc: dict, lid: str) -> dict:
    return next(ln for ln in doc["lanes"] if ln["lane"] == lid)


def test_226_the_file_validates():
    assert rm.validate(_doc()) == []


def test_226_lane_pd_the_record_step_and_earliest_live_moved_the_calendar_step_stays():
    ln = _lane(_doc(), "pd")
    assert (ln["registry_id"], ln["competitions"], ln["state"]) == ("soccer-expansion-v1", ["PD"], "confirming")
    cal, rec = ln["steps"]
    assert (cal["what"], cal["owner"], cal["due"], cal["done"]) == (
        "the 60th cohort fixture (kickoff 2026-11-22T16:00Z) is played", "calendar", "2026-11-22", None)  # a fact
    assert (rec["what"], rec["due"], rec["done"]) == ("the confirmation record step, in the morning block",
                                                      "2026-12-22", None)
    assert ln["earliest_live"] == "2026-12-22"
    # one line of the architect's moves two dates; the base check takes one moved line per move (Codex on #503: "one
    # line records one move"), so the line is entered once per date, its text verbatim in why each time
    assert [(m["moved_on"], m["which"], m["was"], m["now"], m["why"]) for m in ln["moved"]] == [
        ("2026-11-03", rec["what"], "2026-11-23", "2026-12-22", PD_LINE),
        ("2026-11-03", "earliest_live", "2026-11-23", "2026-12-22", PD_LINE)]
    assert all(m["ruling"].startswith("ARCHITECT 2026-11-03 07:55 ET, addendum 226 item 3") for m in ln["moved"])


def test_226_lane_pd_live_needs_are_the_union():
    """Addendum 223 item 2(a): the frozen cohort's confirmation AND the leagues path; a FAIL on either keeps PD SHADOW
    through 2026/27; both verdicts recorded whatever the other says."""
    needs = _lane(_doc(), "pd")["live_needs"]
    assert needs.startswith("THE UNION, the stricter governs (ARCHITECT 2026-11-02 18:05 ET, addendum 223 item 2(a)")
    for part in ("CONFIRMED on the frozen cohort of 60 against the naive, 185 D1", " AND the leagues path ",
                 "the 60-game window below the close, then 60 more at the same bar, 158 item 2(a)",
                 "A FAIL on either keeps PD SHADOW through 2026/27", "Both verdicts are recorded whatever the other says"):
        assert part in needs, part


def test_226_lane_leagues_pd_in_competitions_the_title_and_step_c_text():
    ln = _lane(_doc(), "leagues")
    assert ln["title"] == "La Liga, Serie A, Bundesliga, Ligue 1, Championship"
    assert ln["competitions"] == ["PD", "SA", "BL1", "FL1", "ELC"]
    c = ln["steps"][-1]
    assert (c["owner"], c["due"], c["done"]) == ("calendar", "2026-12-06", None)     # stands: no moved line
    assert c["what"].endswith(f'FL1\'s 60th corrected by 229 item 3: "{STEP_C}"; and 229 item 3\'s sentence, '
                              f'verbatim: "{CLOSE_SHARE}"')
    # addendum 229 items 1 and 3: the host-copy consoles cited, the laptop's earlier two named as the laptop's database;
    # FL1's laptop-read 60th (match 19476) is gone
    assert all("#322 host-copy consoles of 11-03" in c["what"] and cid in c["what"] for cid in HOST_CONSOLES)
    assert "the two earlier consoles of 11-03 read the laptop's database, addendum 229 item 1" in c["what"]
    assert "19476" not in c["what"]
    assert all(m["which"] != c["what"] for m in ln["moved"]) and len(ln["moved"]) == 1


def test_226_lane_pl_availability_the_two_moved_lines_and_the_count():
    ln = _lane(_doc(), "pl-availability")
    cal, read = ln["steps"][2], ln["steps"][3]
    assert (cal["due"], read["due"]) == ("2026-12-14", "2026-12-15")
    assert COUNT in cal["what"] and "six full rounds" not in cal["what"]
    assert "#754" in read["what"] and "ninth in the 12-12 round" in read["what"]
    assert [(m["moved_on"], m["which"], m["was"], m["now"], m["why"]) for m in ln["moved"][2:]] == [
        ("2026-11-02", cal["what"], "2026-12-20", "2026-12-14", PL_LINE1),
        ("2026-11-02", read["what"], "2026-12-21", "2026-12-15", PL_LINE2)]
    assert all("#754 issuecomment-6590791400" in m["ruling"] for m in ln["moved"][2:])


def test_226_the_base_check_passes_from_main_and_names_a_missing_pd_line():
    """check_moves on the head against a base rebuilt as main held it (lane pd's dates 2026-11-23, no moved line; lane
    pl-availability's steps as the base worded and dated them): [] . With lane pd's two lines dropped from the head,
    both of its moves are named."""
    head = _doc()
    base = copy.deepcopy(head)
    pd = _lane(base, "pd")
    pd["steps"][1]["due"], pd["earliest_live"], pd["moved"] = "2026-11-23", "2026-11-23", []
    pl = _lane(base, "pl-availability")
    pl["moved"] = pl["moved"][:2]
    pl["steps"][2]["what"], pl["steps"][2]["due"] = pl["moved"][0]["which"], "2026-12-20"
    pl["steps"][3]["what"], pl["steps"][3]["due"] = pl["moved"][1]["which"], "2026-12-21"
    assert rm.check_moves(base, head) == []
    bare = copy.deepcopy(head)
    _lane(bare, "pd")["moved"] = []
    errs = rm.check_moves(base, bare)
    assert len(errs) == 2 and errs[0].startswith("lane 'pd': earliest_live 2026-11-23 -> 2026-12-22 has no moved line")
    assert errs[1].startswith("lane 'pd' step 2: due 2026-11-23 -> 2026-12-22 has no moved line"), errs


# ARCHITECT 2026-11-03 08:20 ET, addendum 228 item 1 (the release record, in this records PR): docs/RELEASES.md's line
REL_ROW = ("| `v1.6.3` | 2026-11-03 12:59:11Z | `0c88f5cc4e9332bade5efd2043def40ab37a5def` | "
           "`7312627b5b39fc5f38e71718edb9d9cbd3f7be00` | #806 (step 1 as rewritten, #782) |")


def test_228_the_release_record_row_and_section():
    text = (ROOT / "docs" / "RELEASES.md").read_text(encoding="utf-8")
    table = [ln for ln in text.splitlines() if ln.startswith("| `v")]
    assert table[-2:] == [ln for ln in table if "`v1.6.2`" in ln or "`v1.6.3`" in ln] and table[-1] == REL_ROW
    sec = " ".join(text[text.index("- **v1.6.3**"):text.index("## Hotfix path")].split())
    for verbatim in (
            "tag v1.6.3: annotated, tag object 7312627b5b39fc5f38e71718edb9d9cbd3f7be00 on the fold commit "
            "0c88f5cc4e9332bade5efd2043def40ab37a5def (the ledger fold of main 6f6b9dac: 12 changelog fragments and 12 "
            "ledger entries folded), cut 2026-11-03T12:59:11Z by the operator's block, 12 headings kept, notes = the "
            "CHANGELOG slice since v1.6.2; CI success on the commit.",
            "deploy: receipt \"11-03 13:00 deploy exit 0 v1.6.2 -> v1.6.3 (0c88f5cc)\", 80 files, no migration, "
            "requirements unchanged",
            "PASS, addendum 227."):
        assert verbatim in sec, verbatim
    # git's v1.6.2..v1.6.3 holds twelve PRs; 228 item 1's list omits #774 (merged after v1.6.2's cut), and says so
    assert ("twelve PRs: #774, #775, #778, #779, #784, #785, #793, #796, #797, #799, #800, #801 (62 commits with the "
            "fold commit; 61 to 6f6b9dac)") in sec
    assert "Addendum 228 item 1's list" in sec and "omits #774" in sec
