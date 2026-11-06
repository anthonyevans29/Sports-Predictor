"""The soccer-v23 design's texts (ARCHITECT 2026-11-04, addendum 248 item 2(b); addendum 230 item 1(d); addendum 216
items 1-4; addendum 243 item 4; addendum 251 item 2): the rulings quoted verbatim in docs/specs/soccer-v23.md, THE BAR pinned by sha256 and
carried by the spec character for character, the roadmap lane appended as 216 item 3 dates it (every step open, no
earliest_live, no moved line), no registry entry, the command documented, and no market read in the two modules."""
from __future__ import annotations

import hashlib
import io
import json
import tokenize
from pathlib import Path

from src.walters import soccer_v23 as v

ROOT = Path(__file__).resolve().parent.parent
SPEC = (ROOT / "docs" / "specs" / "soccer-v23.md").read_text()

BAR_SHA256 = "15002742f71996b0d3422fcc7a0576bcb44ff6e6dd4833a91b2f8d42eec1feb5"   # 251 item 2's bar, repaired before any declaration (G0's precision role stated); addendum 254 item 3 (Q4 the day rule and the lag, Q20 the fallback, Q22 "v22 re-walked")

# the rulings, verbatim (each must appear in the spec exactly)
RULINGS = {
    "D1": '(b) 230 item 1(d), soccer-v23\'s DESIGN PR (#656; dated 11-13): the joint log-linear μ + h + α_i + δ_j + β·ΔE with per-team early-season continuity (216 item 3), its backtest harness walking it as production would, the frozen-bar text (the pot log-loss below v22\'s by ≥ 0.0050; a tie rejects — written as "below", so a tie IS a rejection here) written before any result; the availability term\'s inputs are the entry\'s fixture age and type verbatim (243/244\'s receipt is its evidence; no figure from it becomes a parameter without the bar). NO run before 11-20\'s declaration. Start today; merge when ready.',
    "D2": "(d) soccer-v23, THE DESIGN PR (lane soccer-v23, dated 11-13; #656) — START NOW, merge when ready: the joint log-linear μ + h + α_i + δ_j + β·ΔE with per-team early-season continuity (216 item 3), the backtest harness that walks it as production would, the frozen-bar text (the pot log-loss below v22's by ≥ 0.0050, a tie rejects) written before any result; NO run and NO declaration before 11-20 (a date is never a reason to run early); an early merge is a done-mark.",
    "D3": "1. THE NORMALISATION FINDING — CONFIRMED in the real code, not only in the review's reimplementation. src/walters/training.py builds the context per competition as g = total goals / (2 × matches) and b = home mean / g (clamped to [1.0, 1.30]); src/models/poisson.py estimate_strengths deflates HOME goals by b before averaging and divides BOTH averages by the undeflated g; the forecast is home λ = g·b·A_H·D_A·elo and away λ = g·A_A·D_H·elo. For a league of average teams the deflated per-team average is g·(3−b)/2, not g, so every average rating reads (3−b)/2 (0.925 at the default b = 1.15, before shrinkage), the forecast total reads g·(1+b)·((3−b)/2)² (about −8% at b = 1.15) and the home/away goal ratio the model expresses is b where the data's is b/(2−b) (1.15 against 1.35). The review's synthetic counterexample (3.000 in, 2.739 out) reproduces exactly from these lines. It is a structural bias toward fewer goals and away/draw mass, not a bug in a branch; it passed through v22's gate because the gate measures v22 against its bar, not its equations against themselves. RULED: (a) a FINDING Issue (model, finding, sport:soccer, M) with the equations above and the review cited; (b) Code's receipt PR, read-only: one test that drives the REAL estimate_strengths and the real forecast with the review's synthetic league and pins the −8.7% total (the review's script is the receipt's citation, not repository code — it reimplements the equations), plus a read-only line that evaluates the same expressions on the production model's stored PL context (g and b as stored) and prints the implied average-team rating, total and home/away ratio; posted on the Issue; (c) NO change to v22: the fix is a candidate through the frozen gate, never a patch to a live model.",
    "D4": "2. THE 30-MATCH SWITCH — CONFIRMED as a discontinuity (the current-season window drops the supplementary history at the league's 30th finished match regardless of a team's own games), and the soccer backtest's default skip of the first 40 matches means that boundary has never been evaluated. RULED: a LIMITATION Issue (model, limitation, sport:soccer, S) for the unevaluated boundary; the per-team continuity (a weight on each team's own usable exposure between its prior-season estimate and its current-season evidence, promoted clubs as a persistent prior) is a DESIGN ELEMENT of the successor candidate of item 3, not a change to v22 and not a reopening of the rejected time-decay experiment.",
    "D5": '3. THE SUCCESSOR — #656 is the vehicle, dated now (the model lanes come first; the PL is the only live model-edge family today, and v22 reads behind the close over the rolling 30): a jointly fitted log-linear model log λ_H = μ + h + α_H + δ_A + β·ΔE, log λ_A = μ + α_A + δ_H − β·ΔE, with identification constraints and regularisation, the Dixon–Coles correction kept, the per-team continuity of item 2 built in — the baseline, the home effect, attack, defence and Elo\'s increment estimated coherently so item 1\'s inconsistency cannot exist by construction. Roadmap lane "soccer-v23" (Issue #656): 11-13 code — the design PR (the fit, its constraints, the early-season treatment, the harness: one run at the frozen soccer gate on the frozen pot, the reservation pattern); 11-20 architect — the declaration with the bar written before any result: the pot\'s log-loss below v22\'s by at least 0.0050, a tie a rejection (the improve bar as it stands), with the early-season matches INCLUDED in the scored set (no 40-match skip for this candidate: its own declared window states the skip, and it is zero); 11-27 operator — the one run on my word, my block, on a .backup copy opened immutable=1; PASS → a 60-game prospective shadow on the host\'s PL pages beside v22 (the pl-availability pattern, its own window counted from its first host page), the read by me; earliest_live the day after that read. No date moves a bar.',
    "D6": "4. For the successor's design PR (230 item 1(d)): the availability term's inputs are the entry's fixture age (this fixture / an earlier fixture, N days) and its type, verbatim; the design states what it does with each and the receipt above is its evidence. No number from this receipt becomes a parameter without a frozen bar.",
    "D7": '4. BACKTEST-TO-PRODUCTION PARITY — ACCEPTED as a lane, not a build today: #425 already records the injury factor\'s absence from v22\'s gate; the review\'s inventory (the scoring context, the Elo state, the early-season history and the match factors differ between soccer_backtest and _generate_predictions_soccer) becomes a LIMITATION Issue (model, limitation, sport:soccer, M) with that table; the engineering direction — ONE prediction function taking a versioned, immutable input snapshot, invoked by replay and by live alike, "same model, same inputs at the same instant, same probabilities" as the acceptance test — is a lane (track:model, class:lane, size:L, no date) to be designed with the soccer-v23 harness so the successor is testable where v22 was not. Historical injuries are never manufactured; the sealed availability window is never read early.',
    "D8": ("2. 249 ITEM 1(a) — RULED. Code's finding is correct and verified in the source: soccer_backtest.py:200 walks every row under CompetitionScoringContext() (g 1.4, b 1.15) while production (training.py:514) reads the stored trained context of the competition (PL today g ≈ 1.49, b ≈ 1.17, as #786's receipt printed them). The reason the walk does NOT read the stored context is sound and is recorded with the finding: the stored context is fitted on the whole training pot — the same games the walk scores — so a walk that read it would leak the pot's own totals into every prior-only step. So \"production == the walk, row for row\" cannot hold on g and b by construction, and an xfail over the WHOLE parity test would blind the one test meant to catch a live/replay divergence. Three tests, then, in the one PR (249's two, reshaped, plus the gap's own pin):",
           "(a) THE PARITY TEST, with the context INJECTED: the walk gains an optional `context` parameter whose default is today's CompetitionScoringContext() (the default path byte-identical, pinned by the existing soccer-backtest golden on the fixture store — a changed default would re-measure every soccer record and is gate-class; this is not that); the test passes production's stored context to the walk and asserts production == the walk, row for row, on the synthetic store. It PASSES on v22 (the shared path — Elo, estimate_strengths, Poisson, Dixon-Coles — reproduces its gate) and fails the day a real divergence appears. No xfail.",
           "(b) THE CONTEXT-GAP PIN, strict xfail on v22: the walk's effective context on a competition equals production's stored context for it. It turns red (xpass) the day the two paths agree, which is the successor's obligation, and it carries the leak reason in its docstring so nobody \"fixes\" it by reading the stored context into the walk.",
           "(c) THE NORMALISATION PIN, 249 item 1(b), unchanged: strict xfail on v22 with its positive control.",
           "THE FINDING ISSUE (filed with the PR, `Refs #789`, `Refs #786`, never closing either): \"the soccer gate's walk scores under the default context (1.4 / 1.15); production runs the trained one; neither is as-of\" — its resolution is the successor's design, not a patch: soccer-v23's design PR (248 item 2(b)) must state how its harness and its production path define g and b IDENTICALLY (an as-of estimate from the prior finished games in both, or a frozen pre-pot context in both — the design chooses and says why), and must re-walk v22 under that same harness beside v23 so the comparison is like for like. v22's recorded gate figure STANDS as measured; nothing about v22 changes. THE BAR, so it never loosens: v23's pot log-loss must be at least 0.0050 below BOTH v22's recorded figure AND v22's figure re-walked on v23's harness; a tie on either is a rejection (the bar is written \"below\"). Option 2 (the default walk reads the stored context) is REJECTED: a leak and a gate-class re-measurement of every soccer record. Option 3 (the improve gate's holdout scorer) is REJECTED: not as-of. The parity harness Code committed locally (6be9b16a, built to 248) is the base; it reshapes to (a)–(c) and opens as 248 item 2(a)'s PR, due 11-20 as before."),
    "D9": '(d) THE SUCCESSOR\'S OBLIGATION, restated so #828 and the v23 design PR agree: 216 item 4\'s direction IS the requirement — ONE prediction function taking a versioned, immutable input snapshot, invoked by replay and by live alike ("same model, same inputs at the same instant, same probabilities"). The v23 design PR shows, for each of the five rows (the context, the Elo state, the early-season history, the match factors, simultaneous kickoffs), how replay and live become identical BY CONSTRUCTION, not by test; the as-of factor inputs come only from stored as-of data (the availability record of addendum 252 is the source going forward; where the record has nothing for an era, the term is off in BOTH paths for that era and the harness says so); v22 is re-walked under the same harness beside v23; the bar is 251 item 2\'s. v22 does not change.',
    "D10": 'THE TWO CLOCKS, ruled now so no term argues it later: `recorded_at` is OUR knowledge; `source_stamp` is the source\'s claim. A live-era record, a forward confirmation and a closing-time input use `recorded_at` only (what we had on our disk before the cut-off). A backfilled row (recorded_at later than source_stamp by more than the feed\'s cadence: nflverse\'s season file reaches back to its first load, so our first fetch records weeks of history at once) is usable ONLY in a backtest labelled "source-stamped" in its run record and its gate text, never in the live-era record; a term that wants it declares that in its bar. Both clocks are kept on every row so either reading can be audited.',
}


def test_the_rulings_are_quoted_verbatim_in_the_spec():
    for k, q in RULINGS.items():
        for para in (q if isinstance(q, tuple) else (q,)):           # D8 (251 item 2) is quoted paragraph by paragraph
            assert para in SPEC, k
    assert RULINGS["D1"].startswith("(b) 230 item 1(d), soccer-v23's DESIGN PR (#656; dated 11-13)")
    assert RULINGS["D2"].endswith("an early merge is a done-mark.")
    assert "No number from this receipt becomes a parameter without a frozen bar." in RULINGS["D6"]
    assert RULINGS["D9"].startswith("(d) THE SUCCESSOR'S OBLIGATION") and "BY CONSTRUCTION, not by test" in RULINGS["D9"]
    assert RULINGS["D10"].startswith("THE TWO CLOCKS") and "use `recorded_at` only" in RULINGS["D10"]


def test_the_five_rows_section_names_each_row_its_field_and_its_test():
    """253 item 2(d): the spec's §4b carries one table row per row, each naming the snapshot field that carries it and
    a test that exists in the harness tests; the five fields exist on the Snapshot; the rule for row 5 is stated."""
    import dataclasses
    assert "## 4b. The five rows, identical by construction (253 item 2(d))" in SPEC
    tests = (ROOT / "tests" / "test_soccer_v23_harness.py").read_text()
    fields = {f.name for f in dataclasses.fields(v.Snapshot)}
    for row, field_names in (("| (1) The context |", ("rows",)), ("| (2) The Elo state |", ("elo_pre", "elo_state")),
                             ("| (3) The early-season history |", ("rows",)),
                             ("| (4) The match factors |", ("availability",)),
                             ("| (5) Simultaneous kickoffs |", ("as_of", "visibility"))):
        line = next(ln for ln in SPEC.splitlines() if ln.startswith(row))
        for f in field_names:
            assert f"`{f}`" in line and f in fields, (row, f)
        names = [n for n in line.split("`") if n.startswith("test_253_row_")]
        assert names and all(f"def {n}(" in tests for n in names), row
    assert "Same-kickoff fixtures share one snapshot." in SPEC and v.SNAPSHOT_VERSION == "soccer-snapshot v2"
    assert "**v22's arm under this harness, per row:**" in SPEC and "v22 itself, its code and its production path do not change" in SPEC


def test_the_bar_is_pinned_and_the_spec_carries_it_character_for_character():
    assert hashlib.sha256(v.BAR_TEXT.encode("utf-8")).hexdigest() == BAR_SHA256
    assert v.BAR_TEXT in SPEC
    for must in ("at least 0.0050 BELOW BOTH v22's recorded figure AND v22's figure re-walked on soccer-v23's harness",
                 "a tie on EITHER is a rejection", "a difference of exactly 0.0050 passes that comparison",
                 "STANDS as measured and is never recomputed", "v22_recorded_log_loss", "v22_recorded_source",
                 "the same context definition", "in the harness and the production path alike",
                 "addendum 251 item 2", "INVALID, never a pass", "MIN_GATE_N = 30", "within-season skip is zero (no 40-match skip)",
                 "the market is a reference, never a feature, and gates nothing", "mode=ro&immutable=1",
                 "No date moves this bar.", "training.DEFAULT_PROMOTION_DELTA (0.005)",
                 # the review of the 251 follow-up: the recorded figure is read as measured, only the re-walked
                 # figures are soccer_calibration's; the no-visible-row default as CONTEXT_DEFINITION states it; a
                 # game visible only once its result is known
                 "The recorded figure is read from the slot as measured",
                 "the re-walked figures (soccer-v23's and v22's, on this harness) are computed by "
                 "soccer_backtest.soccer_calibration",
                 "the default context (g 1.4, b 1.15) only where the competition has no visible game",
                 # the review of the five rows: G0 is not only the first season's prior centre; it also sets that
                 # season's prior precision and beta's prior precision in every window (joint_poisson.py:92, :277)
                 "G0 and B0 as frozen constants, never pot figures: the first season's prior centre, G0 also setting "
                 "that season's prior precision (K_PRIOR·G0) and, in every window, beta's weak prior precision "
                 "(BETA_PRIOR_PRECISION = K_PRIOR·G0)",
                 f"a game visible only once its result is known, at its kickoff plus RESULT_LAG_HOURS = "
                 f"{v.RESULT_LAG_HOURS} hours",
                 # ARCHITECT 2026-11-04 15:45 ET, addendum 254 item 3: Q4 (the day rule; the lag the bound a result is
                 # known, frozen by the declaration), Q20 (the v22 arm's fallback is production's own, training.py:217;
                 # neither fallback a pot figure), Q22 ("v22 re-walked" is v22 on this harness; the ~3.7e-4 labelled
                 # as the synthetic probe's)
                 "under the day visibility rule (addendum 254 item 3 Q4",
                 "the bound a result is known, frozen by the declaration",
                 "for the v22 arm, the default context (g 1.4, b 1.15) only where the competition has no visible game, "
                 "which is production's own fallback (training.py:217), and for soccer-v23, G0 and B0 as frozen "
                 "constants",
                 "neither fallback is a pot figure",
                 "\"v22 re-walked\" is v22 on THIS harness, not live v22 reproduced",
                 "an AET or PEN league row at its 90-minute score where live v22 reads the full score",
                 "about 3.7e-4 in a probability on the design's synthetic one-row probe (a synthetic receipt, not a pot "
                 "figure; the run record counts the AET and PEN rows; addendum 254 item 3 Q22)"):
        assert must in v.BAR_TEXT, must
    assert "Each log-loss is computed by" not in v.BAR_TEXT          # the recorded figure is never recomputed
    assert "only as the first season's frozen prior centre" not in v.BAR_TEXT + v.CONTEXT_DEFINITION
    from src.models import joint_poisson as jp
    assert jp.BETA_PRIOR_PRECISION == jp.K_PRIOR * jp.G0               # what the bar's G0 clause states
    from src.models.poisson import CompetitionScoringContext
    d = CompetitionScoringContext()                                    # the default the bar names, as the code holds it
    assert f"(g {d.avg_goals_per_team_per_match}, b {d.home_field_goal_boost})" in v.BAR_TEXT
    assert "on the frozen pot" not in v.SLOT_VALUES["v22_recorded_log_loss"]
    assert v.WITHIN_SEASON_SKIP == 0


def test_addendum_254_item_3_is_marked_and_the_run_order_is_stated_accurately():
    """ARCHITECT 2026-11-04 15:45 ET, addendum 254 item 3: Q4, Q18, Q20, Q22, Q27 and 28 (the reservation order) RULED in
    §11, the rest left to the 11-05 addendum; the order "preflight → fingerprint → cross_ref_guard → reservation → walk
    → record" is the precedents', and run()'s docstring, §9 and docs/CLI.md say what holds ("before any outcome is
    scored or priced": the goals are loaded and fingerprinted before the reservation, as in both precedents), never
    "before any outcome is read"."""
    flat = " ".join(SPEC.split())
    assert "RULED by addendum 254 item 3 (ARCHITECT 2026-11-04 15:45 ET): 4, 18, 20, 22, 27 and 28" in flat
    assert '"ruled by a dedicated addendum on 11-05"' in flat
    sec11 = SPEC[SPEC.index("## 11. "):SPEC.index("## 12. ")]
    for q in ("4. **Visibility.**", "18. **v22's recorded figure", "20. **A competition's first fixture.**",
              "22. **The v22 arm on AET / PEN league rows.**", "27. **The facts' cut-off", "28. **The reservation"):
        start = sec11.index(q)
        nxt = sec11.find("\n" + str(int(q.split(".")[0]) + 1) + ". ", start)
        assert "RULED" in sec11[start:nxt if nxt > 0 else None], q
    for q in ("1. **Naming.**", "2. **Scope.**", "13. **Failure after the reservation.**", "19. **The re-walked"):
        start = sec11.index(q)
        nxt = sec11.find("\n" + str(int(q.split(".")[0]) + 1) + ". ", start)
        assert "RULED" not in sec11[start:nxt], q
    cli_row = next(ln for ln in (ROOT / "docs" / "CLI.md").read_text().splitlines()
                   if ln.startswith("| `soccer-v23-gate` "))
    for text in (v.run.__doc__.replace("\n    ", " "), SPEC[SPEC.index("## 9. "):SPEC.index("## 10. ")], cli_row):
        assert "before any outcome is read" not in text.replace("BEFORE", "before")
        assert "before any outcome is scored or priced" in text.replace("BEFORE", "before")
    assert "preflight → fingerprint → cross_ref_guard → reservation → walk → record" in v.run.__doc__


def test_the_ruled_questions_are_marked_where_they_are_named_and_q4_is_built_in_full():
    """addendum 254 item 3: every place that named Q4, Q22 or Q27 open or proposed now says ruled; Q4 is built in full
    (Codex on #832, round 3, P1): the visibility slot admits only "day", the rule BAR_TEXT names, and the texts no
    longer say it admits "kickoff" or call Q4 not fully built; the one sub-step where the run differed from both
    precedents (a MISSING fingerprint) now MATCHES them, refused before any load, and run()'s docstring, §9, §11 Q28
    and docs/CLI.md say so with the three file:lines (addendum 254 item 3: the run's order matches the
    precedents')."""
    flat = " ".join(SPEC.split())
    assert "Open question 22. **The tie order" not in flat                     # §4, the v22 arm's AET paragraph
    assert "a proposed constant, §8" not in flat                               # §4 Visibility, RESULT_LAG_HOURS
    assert "Open question 22, RULED AS BUILT by addendum 254 item 3 Q22 (a)" in flat
    vis_row = next(ln for ln in SPEC.splitlines() if ln.startswith("| `visibility` |"))
    assert "RULED by addendum 254 item 3" in vis_row and "the slot ADMITS ONLY \"day\"" in vis_row
    assert "STILL ADMITS" not in vis_row and "| \"day\" only " in vis_row
    sec11 = " ".join(SPEC[SPEC.index("## 11. "):SPEC.index("## 12. ")].split())
    q4 = sec11[sec11.index("4. **Visibility.**"):sec11.index("5. **Constants.**")]
    assert "NOT FULLY BUILT" not in q4 and "still admits" not in q4
    assert "BUILT IN FULL: the `visibility` slot admits only \"day\" (`SLOT_VALUES`)" in q4
    assert v.SLOT_VALUES["visibility"] == ("day",)                            # 254 item 3 Q4: the ruled rule only
    assert "still admits" not in " ".join(SPEC.split())
    assert "open question 4)" not in v.visible.__doc__ and "RULED by addendum 254 item 3 Q4" in v.visible.__doc__
    assert "still admits" not in v.visible.__doc__
    src = (ROOT / "src" / "walters" / "soccer_v23.py").read_text()
    assert "RULED AS BUILT by addendum 254 item 3 Q27 (b)" in src
    assert "#: (open question 27). A fact" not in src
    cli_row = next(ln for ln in (ROOT / "docs" / "CLI.md").read_text().splitlines()
                   if ln.startswith("| `soccer-v23-gate` "))
    for text in (" ".join(v.run.__doc__.split()), " ".join(SPEC[SPEC.index("## 9. "):SPEC.index("## 10. ")].split()),
                 sec11[sec11.index("28. **The reservation"):]):
        assert "nfl_v2_gate.py:642" in text and "ncaa_v1r_gate.py:792" in text, text[:80]
        assert "MATCH" in text and "named for the architect" not in text and "after `_load`" not in text, text[:80]
    line = next(i for i, ln in enumerate(src.splitlines(), 1)
                if ln.strip().startswith("if not fingerprint or not str(fingerprint).strip():"))
    word = next(i for i, ln in enumerate(src.splitlines(), 1) if "the run starts only on the architect's word" in ln)
    load = next(i for i, ln in enumerate(src.splitlines(), 1) if i > word and "= _load(db, slots)" in ln)
    assert word + 1 == line < load and f"soccer_v23.py:{line}" in cli_row
    for text in (" ".join(v.run.__doc__.split()), " ".join(SPEC[SPEC.index("## 9. "):SPEC.index("## 10. ")].split()),
                 sec11[sec11.index("28. **The reservation"):]):
        assert f"soccer_v23.py:{line}" in text, text[:80]
    assert "MATCHING nfl-v2-gate and ncaa-gate" in cli_row
    assert "a MISSING fingerprint is refused here, after the load" not in cli_row
    assert "AFTER THE RESERVATION" not in cli_row                              # Codex round 2: unruled, not built
    # the missing-fingerprint refusal moved ahead of _load, so "no order changed" is true only of the ruled steps
    # (the spec only: a fragment is deleted by the tag's compile, so no test reads one; test_ledger_text.py)
    flat_spec = " ".join(SPEC.split())
    assert "no order changed" not in flat_spec and "no ruled step's order changed" in flat_spec


def test_the_context_gap_section_carries_the_definition():
    """251 item 2: the spec's section names the chosen definition (as-of, in both) verbatim and says why, and the
    bar's section quotes the ruling's bar."""
    assert "## 5a. The context gap (251 item 2)" in SPEC
    assert v.CONTEXT_DEFINITION in SPEC and v.CONTEXT_DEFINITION.startswith("as-of (addendum 251 item 2)")
    for must in ("**Why as-of, not a frozen pre-pot context:**", "It cannot leak.", "It keeps early season honest.",
                 "needs a pre-pot window for every competition", "identical by construction",
                 "v22's recorded gate figure STANDS as measured and is never recomputed"):
        assert must in SPEC, must
    assert ("v23's pot log-loss must be at least 0.0050 below BOTH v22's recorded figure AND v22's figure re-walked on "
            "v23's harness; a tie on either is a rejection") in SPEC


def test_every_declaration_slot_is_in_the_spec_and_none_has_a_value_in_code():
    for k in v.SLOT_KEYS:
        assert f"| `{k}` |" in SPEC, k
    assert v.slots_state(None)[0] is None
    for k in v.code_constants():
        assert f"`{k}`" in SPEC, k


def test_the_lane_is_appended_as_216_item_3_dates_it():
    lanes = {ln["lane"]: ln for ln in json.loads((ROOT / "docs" / "roadmap.json").read_text())["lanes"]}
    ln = lanes["soccer-v23"]
    assert ln["issue"] == 656 and ln["registry_id"] is None and ln["state"] == "to declare"
    assert [(s["owner"], s["due"], s["done"]) for s in ln["steps"]] == [
        ("code", "2026-11-13", None), ("architect", "2026-11-20", None), ("operator", "2026-11-27", None)]
    assert ln["earliest_live"] is None and ln["moved"] == [] and ln["competitions"] == ["PL"]
    assert "earliest_live the day after that read. No date moves a bar." in ln["live_needs"]
    assert "the lane names its next candidate the same day" in ln["live_needs"]
    assert ln["vs_close"].startswith("not read.")
    names = list(lanes)                  # appended after availability-record; later lanes append after it (261)
    assert names.index("soccer-v23") == names.index("availability-record") + 1


def test_no_registry_entry_exists_before_the_declaration():
    entries = json.loads((ROOT / "docs" / "registry" / "experiments.json").read_text())
    assert v.EID not in {e["id"] for e in entries}
    assert not (ROOT / "docs" / "registry" / f"{v.EID}.started.json").exists()


def test_the_command_is_documented():
    rows = [ln for ln in (ROOT / "docs" / "CLI.md").read_text().splitlines() if ln.startswith("| `soccer-v23-gate` ")]
    assert len(rows) == 1 and "NEVER RUN BEFORE THE DECLARATION" in rows[0]


def _names(p: str) -> set[str]:
    src = (ROOT / p).read_text()
    return {t.string for t in tokenize.generate_tokens(io.StringIO(src).readline)
            if t.type in (tokenize.NAME, tokenize.STRING)}


def test_no_market_read_in_the_two_modules():
    """The market is a reference, never a model feature (doctrine): neither module names an odds table, a close or a
    market source in code (their docstrings say the market is never read)."""
    for p in ("src/models/joint_poisson.py", "src/walters/soccer_v23.py"):
        names = _names(p)
        for bad in ("Odds", "KalshiQuote", "market_comparison", "grading_close", "close_record"):
            assert bad not in names, (p, bad)
        assert "fdcuk_close" not in (ROOT / p).read_text()


def test_v22_is_untouched_by_the_design():
    """The design imports v22's functions and never assigns into their modules."""
    for p in ("src/models/joint_poisson.py", "src/walters/soccer_v23.py"):
        src = (ROOT / p).read_text()
        assert "setattr(" not in src and "\n    global " not in src
