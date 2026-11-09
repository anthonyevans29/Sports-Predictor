"""ARCHITECT 2026-11-09 09:45 ET, addendum 303 (BL1 IS DECLARED), item 3's records, and ARCHITECT 2026-11-09 09:55 ET,
addendum 304 item 2 (THE DEPLOY RECORD of v1.6.5), on the tracked files. The quoted texts are the architect's, verbatim
(their line breaks as the addenda carry them; docs/RELEASES.md wraps them, so its checks read it flattened)."""
from __future__ import annotations

import json
from pathlib import Path

from src import roadmap as rm
from src.walters import leagues_window as lw
from src.walters import registry as reg
from src.walters import soccer_expansion as sx

ROOT = Path(__file__).resolve().parent.parent
REAL = {e["id"]: e for e in reg.load(reg.LEDGER)}
FOUR = ("leagues-pd-v1", "leagues-sa-v1", "leagues-fl1-v1", "leagues-elc-v1")

# addendum 303 item 1, verbatim
ITEM1 = ('1. THE DECLARATION (the fifth league, on the terms of the four — addendum 220 items 3 and 5, by '
     'reference, nothing re-stated and nothing changed): registry id `leagues-bl1-v1`; the candidate '
     "soccer_elo_poisson's current constants, trained to 2025/26, frozen (no retuning on 2026/27), the "
     "expansion gate's own walk run prospectively (soccer_expansion: a cold start per league-season, F3 "
     'regular rounds only, F5 same-kickoff batching, the production rho and Elo coefficient, nothing '
     "fitted; the one predicate of 181 item 2); declared_at 2026-11-09T14:45:00Z — the window's start, "
     'THIS STAMP; the window the first 60 FINISHED 2026/27 BL1 games with a three-way close whose '
     'kickoff is after declared_at, at the bar of 220 item 3; the confirmation criterion as declared for '
     'the four (60 more qualifying games at the same bar, independently per league). The pre-declaration '
     "fence (cut 2026-10-30T15:00:00Z, 181 item 1(b)) is REPLACED by the entry's declared_at from that "
     "instant: the 18 fenced games, finished between the cut and now, are the cohort reader's alone and "
     'never in the window (178 R8). The shadow stays a shadow: no Desk call, no stake, no page beyond '
     "the shadow export's own (D8's rule as the four have it).")
# addendum 303 item 3's CLAUDE.md sentence, verbatim
CLAUDE_SENTENCE = ('The five expansion leagues (PD, SA, FL1, ELC declared 2026-11-02T18:10:00Z, addendum 220; BL1 '
     "declared 2026-11-09T14:45:00Z, addendum 303) run as shadows on soccer-expansion-v1's frozen "
     'constants toward independent 60-game windows; market-only on the Desk.')
# addendum 304 item 2's seven lines, verbatim
DEPLOY = [
    ('13:47Z deploy: v1.6.4 (284c5758) → v1.6.5 (5f9cf13d), 126 files; receipt row `deploy 0 · v1.6.4 -> '
      'v1.6.5 (5f9cf13d)`; the deploy named one new migration and the three shipped timers not in '
      'timers.enabled.'),
    ('13:49Z the migration command, verbatim as printed, one lock: `backup:daily 0 · '
      'sports_2026-11-09_134946.db integrity=ok · f2c52596cf5d`; `migrations 0`; '
      'migrate_availability_record.py created availability_observations and availability_assertions, 7 '
      'triggers, 10 of 10 declared indexes, and wrote the marker availability_record_migration '
      '(migrated_at 2026-11-09 13:49:58Z).'),
    ("14:12Z the availability 2025 read FIRST (T11's watermark rule): AVAILABILITY-NFLVERSE observation "
      '#1 · complete · depth_charts_2025.csv · HTTP 200 · rows read 554,215 · loads 221 · rows asserted '
      '554,215 · one partial team group (LAC, 2025-12-18, 8 of 72 rows) · payload sha256 f5a4aa3fa70150e8 '
      '· exit 0.'),
    ('14:14Z the NBA first load on the host (bootstrap order): sync-competitions basketball created 1; '
      'sync-teams NBA 2026 created 30; sync-matches NBA 2026 created 1,266 (orientation_reversed 0 · '
      'teams_mismatch_refused 0); sync-kalshi-nba KXNBAGAME 64 markets · matched 28 · 28 prices stored · '
      "unmatched 36 (outside the run's window) · ambiguous 0 · in-play 0."),
    ('14:16Z the unit files: `install.sh` installed 34 unit files (host.env untouched, nothing enabled '
      'by it); then `systemctl enable --now sp-nba-daily.timer sp-availability-daily.timer` exit 0; both '
      'active, next runs Tue 06:47Z and Tue 08:45Z; sp-tennis-daily.timer installed, disabled, inactive; '
      'timers.enabled 20 names, no duplicate. MY MISS, recorded as such: my first timer block ran '
      '`enable` before `install.sh` ("Unit file sp-nba-daily.timer does not exist") and, reading the '
      "pipeline's exit from `tail`, appended the two names to timers.enabled anyway; the fix block put "
      "the units in place and enabled both; the file's end state is right. RELEASES.md step 5 gains one "
      'line for the next tag: "when the tag ships a new unit file, `sudo bash deploy/hosting/install.sh` '
      '(idempotent; enables nothing) before the enable".'),
    ('The receipts since the deploy: 0 failing.'),
    ('The compare of the day, as 300 item 0 reads it; the one failing row since v1.6.4 explained there.'),
]
STEP5 = ('when the tag ships a new unit file, `sudo bash deploy/hosting/install.sh` (idempotent; enables '
     'nothing) before the enable')


def _flat(x: str) -> str:
    return " ".join(x.split())


def test_303_bl1s_entry_on_the_four_shape_and_terms():
    e = REAL["leagues-bl1-v1"]
    sa = REAL["leagues-sa-v1"]
    assert set(sa) <= set(e) and set(e) - set(sa) == {"parity_receipt"}          # every key of the four's shape
    assert all(e.get(k) for k in reg.DECLARE_FIELDS)
    assert (e["sport"], e["competition"], e["status"], e["run"], e["verdict"], e["n"]) == (
        "soccer", "BL1", "declared", None, None, 60)
    assert e["declared_at"] == "2026-11-09T14:45:00Z"
    for k in ("candidate", "training_cutoff", "gate", "confirmation_window", "confirmation_plan",
              "frozen_constants"):                                                # by reference: the four's, unchanged
        assert all(e[k] == REAL[i][k] for i in FOUR), k
    assert all(e["confirmation_plan_note"] == REAL[i]["confirmation_plan_note"] for i in FOUR[1:])   # PD's names PD
    assert e["frozen_constants"] == {k: REAL[sx.EID]["run"]["result"][k] for k in lw.CONSTANTS}
    assert e["declarations_ruling"] == ITEM1
    assert "the #322 comment 6742654029" in e["parity_receipt"] and "UNEQUAL 0" in e["parity_receipt"]
    assert e["test_set"].startswith("BL1 (Bundesliga) 2026/27, PROSPECTIVE (addendum 303 item 1, verbatim): ")
    assert len({REAL[i]["test_set"] for i in (*FOUR, "leagues-bl1-v1")}) == 5      # one window per league
    assert '"declared (5 of 5)" by addendum 303 item 3' in e["lane"]


def test_303_the_cohort_reader_and_the_fence_read_bl1s_entry():
    """The code reads the entry with no change: DECLARATION_IDS already named leagues-bl1-v1 (addendum 181 item 6);
    the fence's cut moves from PRE_DECLARATION_CUT to the entry's declared_at (addendum 303 item 1: "The
    pre-declaration fence ... is REPLACED by the entry's declared_at from that instant")."""
    from datetime import datetime
    e = lw.declaration("BL1")
    assert e is not None and e["id"] == "leagues-bl1-v1"
    assert lw.fence_cutoff("BL1", "2026/27") == datetime(2026, 11, 9, 14, 45) != lw.PRE_DECLARATION_CUT


def _leagues():
    doc = json.loads((ROOT / "docs" / "roadmap.json").read_text(encoding="utf-8"))
    assert rm.validate(doc) == []
    return next(ln for ln in doc["lanes"] if ln["lane"] == "leagues")


def test_303_the_leagues_lane_bl1_done_and_its_window_step():
    ln = _leagues()
    bl1 = next(st for st in ln["steps"] if st["what"].startswith("BL1's declaration"))
    assert bl1["done"] == {"date": "2026-11-09", "receipt": "#322 comment 6742654029"}
    w = ln["steps"][-1]
    assert (w["owner"], w["due"], w["done"]) == ("calendar", "2027-01-13", None)
    assert w["what"].startswith("BL1's 60th qualifying close (ARCHITECT 2026-11-09 09:45 ET, addendum 303 items 1-3; "
                                "the lane reads \"declared (5 of 5)\"")
    # the receipt's PROJECTION line for BL1, as the operator pasted it (addendum 306 item 4), and its caveat
    assert ("kickoff 2027-01-13 19:30Z (UTC date 2027-01-13; match 18549) · 225 stored after the start" in w["what"])
    assert '"every other game assumed to get a three-way close"' in w["what"]
    # ARCHITECT 2026-11-09 12:50 ET, addendum 309 item 3(7), verbatim in part: "303 item 2's MEASURED figure (26 of 81,
    # 32%) is the record"; 306 item 4's estimate is WITHDRAWN: "the step carries 32%", and the withdrawn figure nowhere
    assert ("BL1's close coverage this season is 26 of 81 finished, 32%: addendum 303 item 2's MEASURED "
            "figure") in w["what"]
    assert "addendum 309 item 3(7)" in w["what"]
    assert "45%" not in w["what"]
    assert ("\"so the 60th QUALIFYING game lands later than the 60th stored fixture; the roadmap step takes the "
            "projected date as written, and the lane's text names the caveat.\"") in w["what"]
    assert "the window counts from 2026-11-09T14:45:00Z" in w["what"]
    assert ln["state"] == "declared" and ln["earliest_live"] is None and len(ln["moved"]) == 1   # no date moved
    assert ln["steps"][-2]["due"] == "2026-12-06" and rm.next_step(ln)[1] is ln["steps"][-2]


def test_303_claude_md_soccer_paragraph_gains_the_sentence():
    cm = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    soccer = cm[cm.index("- **Soccer**"):cm.index("- **NFL**")]
    assert _flat(CLAUDE_SENTENCE) in _flat(soccer) and _flat(cm).count(_flat(CLAUDE_SENTENCE)) == 1


def test_304_item_2_the_v1_6_5_deploy_record_and_step_5():
    rel = (ROOT / "docs" / "RELEASES.md").read_text(encoding="utf-8")
    sec = _flat(rel[rel.index("- **v1.6.5**"):rel.index("## Hotfix path")])
    for line in DEPLOY:
        assert _flat(f'"{line}"') in sec, line[:60]
    assert "NOT YET REPORTED" not in sec and "the migration command the deploy prints" not in sec
    ritual = _flat(rel[rel.index("## Promotion ritual"):rel.index("## Release record")])
    step5 = ritual[ritual.index("5. **Deploy on the host**"):]
    assert f'verbatim: "{STEP5}"' in step5
