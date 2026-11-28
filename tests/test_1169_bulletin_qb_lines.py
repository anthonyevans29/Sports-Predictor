"""#1169 (ARCHITECT 2026-11-27 20:35 ET, addendum 583 item 1, RULED "YES, (i), (ii) AND (iii), AS YOU PROPOSE"): the
closing bulletin's QB lines name what they classify.

(a) THE CALL's and THE TEAMS' QB line read "QB tag on the Desk's call: none" or the tags (closing.qb_class, unchanged:
it reads the Desk row's tags alone), and, only when it is none and the chain's call is a PASS, the clause "(the Desk's
chain passed at KIND; QB tags are written only when it sizes a PLAY)", KIND read through its own classified field.
(b) The value shadow's own QB tag prints on a line of its own after summary_block's verbatim value shadow line, only
when the shadow carries it. (c) No cohort name on these lines. (d) The classifier, its two texts, the summary, the
would-be text and the cohort stay byte for byte; one helper serves both lines and a test holds them equal.

Synthetic only: invented teams and tickers, every row annotated by the Desk itself (desk_policy.annotate) so the tags
are the Desk's own, wrapped by closing.closing_doc in a throwaway repo under tmp_path. No DB, no network."""
import sys
from pathlib import Path

import pytest

from src.walters import desk_policy as dp

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))

import bulletin as b  # noqa: E402
import closing as cl  # noqa: E402

from tests.test_bulletin import NOW, closing_file, displayed, md_of, repo, row  # noqa: E402,F401

QB_LINE = "- QB tag on the Desk's call:"
CLAUSE = "(the Desk's chain passed at {}; QB tags are written only when it sizes a PLAY)"
VS_QB = "- value shadow's own QB tag: QB-flagged (a QB is listed on either side)"
K = {"comp": "NFL", "series": "KXTESTNFL"}


def nfl_rows(qb_away=True):
    """Three invented NFL games: 9311 a floor PASS whose value shadow is the dog (home edge -10pp, away +10pp), 9312 an
    edge the chain sizes as a PLAY (7pp), 9313 a quarantine (20pp). A QB listed on the away side unless qb_away is
    False."""
    rows = [row(9311, "Mu Owls", "Nu Hawks", 0.55, fair_h=0.65, bid=0.64, ask=0.65, **K),
            row(9312, "Xi Bears", "Omicron Rams", 0.62, fair_h=0.55, bid=0.54, ask=0.55, minutes=36, **K),
            row(9313, "Pi Jets", "Rho Colts", 0.75, fair_h=0.55, bid=0.54, ask=0.55, minutes=38, **K)]
    if qb_away:
        for r in rows:
            r["input_quality"]["injuries"]["away"]["qb_listed"] = ["Q. Passer"]
    return rows


def annotated(rows):
    return dp.annotate({"sport": "nfl", "exported_at": "2026-11-08T15:25:00Z", "predictions": rows}, now=NOW)


def desk(doc, mid):
    return next(r["desk"] for r in doc["predictions"] if r["match_id"] == mid)


def section(md: str, head: str) -> list[str]:
    lines = md.split("\n")
    i = lines.index(f"## {head}")
    j = next((k for k in range(i + 1, len(lines)) if lines[k].startswith("## ")), len(lines))
    return lines[i:j]


def qb_lines(md: str) -> tuple[str, str]:
    """THE CALL's QB line and THE TEAMS' QB line, one each, as displayed."""
    call = [ln for ln in section(md, "THE CALL") if ln.startswith(QB_LINE)]
    teams = [ln for ln in section(md, "THE TEAMS") if ln.startswith(QB_LINE)]
    assert len(call) == 1 and len(teams) == 1, (call, teams)
    return call[0], teams[0]


def rendered(repo, doc, mid) -> str:
    assert b.run(closing_file=str(closing_file(repo, doc, "NFL"))) == 0
    return displayed(md_of(repo, "NFL", mid))


# ------------------------------------------------------------------------------- (a) the floor PASS, 15206's shape --

def test_a_floor_pass_with_a_qb_listed_names_the_chain_and_its_kind(repo):
    """The symptom of #1169: a floor PASS whose inputs list a QB read "QB inputs clean" on both lines. Under NFL
    market-only (addendum 214, on) the chain's call and KIND are the hold's: would_call PASS, would_pass_kind floor,
    never the row's own pass_kind market_only."""
    doc = annotated(nfl_rows())
    d = desk(doc, 9311)
    assert d["call"] == "PASS" and d["pass_kind"] == dp.NFL_MARKET_ONLY_KIND
    assert d["market_only_hold"]["would_call"] == "PASS" and d["market_only_hold"]["would_pass_kind"] == "floor"
    assert cl.qb_class(d) == "QB inputs clean"                     # the classifier, unchanged, reads the tags alone
    assert "QB-flagged" in d["value_shadow"]["tags"]               # the value side takes its tag from the inputs
    md = rendered(repo, doc, 9311)
    want = f"{QB_LINE} none {CLAUSE.format('floor')}"
    assert qb_lines(md) == (want, want)
    assert "passed at market_only" not in md and "QB inputs clean" not in md
    assert "- QB: " not in md and "- QB class: " not in md


def test_b_the_value_shadow_prints_its_own_qb_line_right_after_the_verbatim_one(repo):
    """Addendum 583 item 1(b): a separate line after summary_block's line, which stays verbatim (321 item 4(c))."""
    doc = annotated(nfl_rows())
    md = rendered(repo, doc, 9311)
    lines = section(md, "THE CALL")
    i = next(k for k, ln in enumerate(lines) if ln.startswith("- value shadow "))
    assert lines[i] == "- value shadow Nu Hawks 0.25u · edge +10.0pp · exec +7.5pp · shadow, not staked"
    assert lines[i + 1] == VS_QB
    assert md.count(VS_QB) == 1
    x = cl.desk_rows(doc, {9311}, b.EPOCH, fam="NFL")[0]
    console = next(ln.strip() for ln in cl.summary_block(x).split("\n") if ln.strip().startswith("value shadow"))
    assert lines[i] == "- " + b._LABEL_GAP.sub(r"\1 ", console)   # the summary's own line, one space, else verbatim
    assert "QB" not in console                                     # 321 item 4(c): the summary's line is not touched


def test_b_no_value_shadow_qb_line_without_the_tag(repo):
    """The same floor PASS with no QB listed: the value shadow carries no QB tag and the line does not print; the call's
    line still names the chain's kind."""
    doc = annotated(nfl_rows(qb_away=False))
    assert "QB-flagged" not in desk(doc, 9311)["value_shadow"]["tags"]
    md = rendered(repo, doc, 9311)
    assert "value shadow's own QB tag" not in md and "- value shadow " in md
    want = f"{QB_LINE} none {CLAUSE.format('floor')}"
    assert qb_lines(md) == (want, want)


# --------------------------------------------------------------------------- the quarantine and the sized PLAY --

def test_a_quarantine_row_carrying_qb_flagged_prints_the_tag_and_no_clause(repo):
    doc = annotated(nfl_rows())
    d = desk(doc, 9313)
    assert d["call"] == "PASS" and "QB-flagged half units" in d["tags"] and "quarantine ≥ 15pp (shadow)" in d["tags"]
    md = rendered(repo, doc, 9313)
    assert qb_lines(md) == (f"{QB_LINE} QB-flagged",) * 2
    assert "chain passed" not in md


def test_a_quarantine_row_with_no_qb_listed_reads_the_holds_kind_as_the_row_gives_it(repo):
    """Ruled as written: none, and the chain's call (the hold's would_call) a PASS, so the clause prints; the chain's
    quarantine PASS carries no pass kind (desk_policy: a quarantine sets none), so KIND, the hold's would_pass_kind,
    prints "not stored" (law 4: never a default, never the row's market_only)."""
    doc = annotated(nfl_rows(qb_away=False))
    h = desk(doc, 9313)["market_only_hold"]
    assert h["would_call"] == "PASS" and h["would_pass_kind"] is None
    md = rendered(repo, doc, 9313)
    want = f"{QB_LINE} none {CLAUSE.format(b.NOT_STORED)}"
    assert qb_lines(md) == (want, want)


def test_a_sized_play_carrying_qb_flagged_prints_the_tag_and_no_clause(repo, monkeypatch):
    """With the NFL market-only rule off (the frozen golden's setting), the chain's PLAY is the row's call."""
    monkeypatch.setitem(dp.NFL_MARKET_ONLY_RULE, "on", False)
    doc = annotated(nfl_rows())
    d = desk(doc, 9312)
    assert d["call"] == "PLAY" and "QB-flagged half units" in d["tags"] and "market_only_hold" not in d
    md = rendered(repo, doc, 9312)
    assert qb_lines(md) == (f"{QB_LINE} QB-flagged",) * 2
    assert "chain passed" not in md


def test_market_only_off_a_floor_pass_reads_kind_from_the_rows_own_pass_kind(repo, monkeypatch):
    """No market-only hold on the row: the chain's call is the row's call and KIND its pass_kind (desk.pass_kind)."""
    monkeypatch.setitem(dp.NFL_MARKET_ONLY_RULE, "on", False)
    doc = annotated(nfl_rows())
    d = desk(doc, 9311)
    assert d["call"] == "PASS" and d["pass_kind"] == "floor" and "market_only_hold" not in d
    md = rendered(repo, doc, 9311)
    want = f"{QB_LINE} none {CLAUSE.format('floor')}"
    assert qb_lines(md) == (want, want)
    assert section(md, "THE CALL").index(VS_QB) > 0


# ------------------------------------------------------------------ market-only (214 on): the chain sized a PLAY --

def test_market_only_a_chain_play_with_qb_flagged_prints_the_tag_and_keeps_the_would_be_class(repo, monkeypatch):
    """The row's call is PASS market_only; the chain's (the hold's would_call) is PLAY, so no clause. The would-be line
    keeps the cohort's own class, verbatim (closing.would_be_text)."""
    monkeypatch.setattr(cl, "nfl_certification", lambda: ("uncertified", "test"))
    doc = annotated(nfl_rows())
    d = desk(doc, 9312)
    assert d["call"] == "PASS" and d["market_only_hold"]["would_call"] == "PLAY"
    md = rendered(repo, doc, 9312)
    assert qb_lines(md) == (f"{QB_LINE} QB-flagged",) * 2
    assert "chain passed" not in md
    x = cl.desk_rows(doc, {9312}, b.EPOCH, fam="NFL")[0]
    assert x["would_be"]["qb"] == "QB-flagged"
    assert "- " + " · ".join(cl.would_be_text(x["would_be"])) in section(md, "THE CALL")
    assert "- would-be PLAY (uncertified, unstaked) Xi Bears 0.5u · exec +5.2pp · QB-flagged · record only, not placed" \
        in section(md, "THE CALL")


def test_market_only_a_chain_play_with_no_qb_listed_reads_none_and_no_clause(repo):
    doc = annotated(nfl_rows(qb_away=False))
    d = desk(doc, 9312)
    assert d["market_only_hold"]["would_call"] == "PLAY" and d["market_only_hold"]["would_pass_kind"] is None
    md = rendered(repo, doc, 9312)
    assert qb_lines(md) == (f"{QB_LINE} none",) * 2


# ----------------------------------------------------------------------------------------------- (d) one helper --

@pytest.mark.parametrize("qb_away", [True, False])
@pytest.mark.parametrize("mid", [9311, 9312, 9313])
def test_d_the_teams_line_equals_the_call_line_from_one_helper(mid, qb_away):
    doc = annotated(nfl_rows(qb_away))
    r = next(x for x in doc["predictions"] if x["match_id"] == mid)
    d = r["desk"]
    call = [ln for ln in b.section_call(r, d, None, "NFL") if ln.startswith(QB_LINE)]
    teams = [ln for ln in b.section_teams(r, d, "NFL") if ln.startswith(QB_LINE)]
    assert call == teams == [b.qb_call_line(d)]


def test_d_soccer_and_mlb_print_no_qb_line():
    r = row(9401, "Alpha Owls", "Beta Hawks", 0.55, fair_h=0.45, fair_d=0.27, draw=0.25, bid=0.44, ask=0.45,
            comp="PL", series="KXTESTGAME")
    doc = dp.annotate({"sport": "soccer", "exported_at": "2026-11-08T15:25:00Z", "predictions": [r]}, now=NOW)
    r = doc["predictions"][0]
    out = b.section_call(r, r["desk"], None, "SOCCER") + b.section_teams(r, r["desk"], "SOCCER")
    assert not any("QB" in ln for ln in out)


def test_d_the_classifier_and_its_two_texts_stay_byte_for_byte():
    assert cl.QB_TEXT == {"QB-flagged half units": "QB-flagged", "QB unread half units": "QB list unread"}
    assert cl.qb_class({}) == b.QB_CLEAN == "QB inputs clean"
    assert cl.qb_class({"tags": list(cl.QB_TEXT)}) == "QB-flagged and QB list unread"
    both = {"call": "PASS", "pass_kind": "floor", "tags": list(cl.QB_TEXT)}
    assert b.display_text(b.qb_call_line(both)) == f"{QB_LINE} QB-flagged and QB list unread"   # tags: no clause


# ------------------------------------------------------------------------------- KIND through its own field --

def test_kind_is_read_through_its_own_classified_field_and_escaped():
    """Addendum 583 item 1(a): "KIND read through its own classified field". The hold's would_pass_kind is a field the
    bulletin did not print before, so it is classified (FREE_TEXT_FIELDS) and goes through fv() under its own name;
    the row's pass_kind keeps desk.pass_kind. A kind holding markup prints escaped."""
    assert "desk.market_only_hold.would_pass_kind" in b.FREE_TEXT_FIELDS
    tok = "q0<_*kind"
    d = {"call": "PASS", "pass_kind": "market_only", "tags": [],
         "market_only_hold": {"would_call": "PASS", "would_pass_kind": tok}}
    seen: list = []
    t = b._FIELDS.set(seen)
    try:
        line = b.qb_call_line(d)
    finally:
        b._FIELDS.reset(t)
    assert seen == [("desk.market_only_hold.would_pass_kind", tok)]
    assert tok not in line and b.md_escape(tok) in line and "<" not in line
    assert b.display_text(line) == f"{QB_LINE} none {CLAUSE.format(tok)}"
    seen.clear()
    t = b._FIELDS.set(seen)
    try:
        b.qb_call_line({"call": "PASS", "pass_kind": "floor", "tags": []})
    finally:
        b._FIELDS.reset(t)
    assert seen == [("desk.pass_kind", "floor")]
