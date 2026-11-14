"""#945, the label split (ARCHITECT, addendum 365 item 3(b), relayed in addendum 379 item 6), verbatim: ""live, resync
needed" must mean the provider serves something our row lacks. The planner splits it: a live row whose served status,
status_raw, score and kickoff equal the stored ones is counted `live` (nothing to do) and printed only under --sample;
`live, resync needed` is kept for a served score, status or kickoff that differs, with the differing fields named."

Each kept shape below is a stale SCHEDULED row with no score whose id the provider answers. They are the twenty's three
served forms (status_raw NS, no status word, PST), then a final score, a moved kickoff, a new status code, and an
answer with no game kept. "Differs" is what a resync would write, as the upsert writes it
(IngestionService._apply_match_updates): status and kickoff always; a status code only when one is served; a score
side only when served. On the code before this change every stale live row read `live_resync`, so the three stale
`live` shapes fail there, and so do the resync and console shapes (each names `differs`). The not-stale shape and the
no-write check pass on both: they pin what did not change."""
from datetime import timedelta

from src.db.database import session_scope
from src.db.schema import Match, MatchStatus
from src.ingestion import match_dedupe as md
from tests.test_dedupe_orphans import CODE, NOW, _nm, world  # noqa: F401  (the OR1 world fixture, dropped after)

PAST = NOW - timedelta(days=1)
SID = "23500"                     # the OR1 world's stale live row ("resync": teams 11 v 10, kickoff PAST)


def _store(mid, status_raw):
    with session_scope() as s:
        s.get(Match, mid).status_raw = status_raw


def _serve(prov, *, status=MatchStatus.SCHEDULED, status_raw="NS", when=PAST, score=None):
    g = _nm(11, 10, SID, when, status=status)
    g.status_raw = status_raw
    if score:
        g.home_score, g.away_score = score
    prov.games = [x for x in prov.games if x.source_id != SID] + [g]


def _plan_row(prov, mid):
    return next(p for p in md.orphans(CODE, prov, now=NOW)["plan"] if p["id"] == mid)


def _stored(mid):
    with session_scope() as s:
        m = s.get(Match, mid)
        return m.status, m.status_raw, m.home_score, m.away_score, m.utc_date, dict(m.external_ids or {})


def test_945_served_equal_to_stored_is_live_nothing_to_do(world):
    """status_raw NS on both sides, no score, the same kickoff: `live`, no `differs` (was `live_resync`)."""
    ids, prov = world
    _store(ids["resync"], "NS")
    _serve(prov)
    p = _plan_row(prov, ids["resync"])
    assert p["action"] == "live" and "differs" not in p and p["stale"] is True


def test_945_no_status_word_served_is_live_an_absent_code_never_blanks_a_stored_one(world):
    """The provider serves no status word; the upsert keeps the stored code, so a resync writes nothing: `live`."""
    ids, prov = world
    _store(ids["resync"], "NS")
    _serve(prov, status_raw=None)
    assert _plan_row(prov, ids["resync"])["action"] == "live"


def test_945_pst_served_as_stored_is_live(world):
    """PST is unmapped, so it stays SCHEDULED by law 4. Stored PST and served PST: `live`."""
    ids, prov = world
    _store(ids["resync"], "PST")
    _serve(prov, status_raw="PST")
    assert _plan_row(prov, ids["resync"])["action"] == "live"


def test_945_a_not_stale_live_row_stays_live_as_before(world):
    """Only the stale rows are split: a twin's live row (kickoff ahead) reads `live` whatever it serves."""
    ids, prov = world
    p = _plan_row(prov, ids["twin_new"])
    assert p["action"] == "live" and p["stale"] is False and "differs" not in p


def test_945_a_final_score_served_is_resync_needed_with_status_and_score_named(world):
    ids, prov = world
    _store(ids["resync"], "NS")
    _serve(prov, status=MatchStatus.FINISHED, status_raw="FT", score=(31, 24))
    p = _plan_row(prov, ids["resync"])
    assert p["action"] == "live_resync"
    assert p["differs"] == {"status": "SCHEDULED -> FINISHED", "home_score": "None -> 31", "away_score": "None -> 24"}
    assert p["annotation"] == {"status_raw": "NS -> FT"}            # 382 item 4(b): named, never counted


def test_945_a_moved_kickoff_is_resync_needed_with_the_kickoff_named(world):
    ids, prov = world
    _store(ids["resync"], "NS")
    _serve(prov, when=PAST + timedelta(hours=3))
    p = _plan_row(prov, ids["resync"])
    assert p["action"] == "live_resync"
    assert p["differs"] == {"kickoff": f"{PAST.isoformat()} -> {(PAST + timedelta(hours=3)).isoformat()}"}


def test_1001_a_new_status_code_alone_is_live_with_the_code_named_as_an_annotation(world):
    """382 item 4(b): status_raw is an annotation of a state we already hold; a row that differs only in it reads
    `live`, the code named ("annotation"). Was `live_resync` under #997 (fail-first on 151aadae)."""
    ids, prov = world
    _store(ids["resync"], "NS")
    _serve(prov, status_raw="XQ")
    p = _plan_row(prov, ids["resync"])
    assert p["action"] == "live" and "differs" not in p and p["annotation"] == {"status_raw": "NS -> XQ"}


def test_945_an_answer_with_no_game_kept_is_never_read_as_equal(world):
    """Nothing to compare (the adapter kept no game): kept as `live_resync`, never counted as nothing to do (law 4)."""
    ids, prov = world
    get0 = prov.get_game
    prov.get_game = lambda sid, code: (True, None) if sid == SID else get0(sid, code)
    p = _plan_row(prov, ids["resync"])
    assert p["action"] == "live_resync"
    assert p["differs"] == {"served": "unknown: the id answers and the adapter kept no game"}


def test_1001_a_stored_code_absent_and_one_served_is_live_its_annotation_named(world):
    """Question 6, ruled (382 item 4(b)): "a difference in status_raw alone reads `live`". Stored NULL, served NS."""
    ids, prov = world
    _serve(prov)                                     # the world stores no status_raw on the resync row
    p = _plan_row(prov, ids["resync"])
    assert p["action"] == "live" and p["annotation"] == {"status_raw": "None -> NS"}


def test_1001_a_reversed_final_is_resync_needed_with_the_key_status_and_scores_named_in_stored_orientation(world):
    """382 item 4(c): the REVERSED pair "is the same game, and it follows (a)": a reversal not yet recorded is a
    provider_orientation key a resync would write, named; its served scores are compared in the stored orientation
    (the provider's home 10 scored 31: our row's away). Was `teams` alone (fail-first on 151aadae)."""
    ids, prov = world
    _store(ids["resync"], "NS")
    g = _nm(10, 11, SID, PAST, status=MatchStatus.FINISHED)          # the stored 11 v 10, served 10 v 11
    g.status_raw, g.home_score, g.away_score = "FT", 31, 24
    prov.games = [x for x in prov.games if x.source_id != SID] + [g]
    p = _plan_row(prov, ids["resync"])
    assert p["action"] == "live_resync"
    assert p["differs"] == {"provider_orientation": "None -> reversed", "status": "SCHEDULED -> FINISHED",
                            "home_score": "None -> 24", "away_score": "None -> 31"}
    assert p["annotation"] == {"status_raw": "NS -> FT"}


def test_1001_an_id_that_serves_another_pair_has_its_own_label_with_both_pairs(world):
    """382 item 4(c): "neither `live` nor `live, resync needed`. It gets ITS OWN LABEL AND ITS OWN COUNT [...] with the
    stored pair and the served pair by team id, whether or not the row already records the mismatch." Was
    `live_resync` (fail-first on 151aadae)."""
    ids, prov = world
    _store(ids["resync"], "NS")
    prov.games = [x for x in prov.games if x.source_id != SID] + [_nm(14, 15, SID, PAST)]
    p = _plan_row(prov, ids["resync"])
    assert p["action"] == "live_other_pair" and "differs" not in p
    assert p["pair"].startswith(f"stored teams {p['home']} v {p['away']} -> served provider teams ")
    assert p["recorded"] == "the mismatch is not recorded"
    with session_scope() as s:                                       # the mismatch already recorded: the same label
        m = s.get(Match, ids["resync"])
        m.external_ids = {**(m.external_ids or {}), "provider_orientation": "mismatch"}
    p = _plan_row(prov, ids["resync"])
    assert p["action"] == "live_other_pair" and p["recorded"] == "provider_orientation = mismatch"


def test_945_a_stored_orientation_key_on_the_same_pair_is_resync_needed_with_the_key_named(world):
    """#997 (Codex P2): the row carries provider_orientation from an earlier listing; the provider now serves the
    stored pair with everything else equal. The upsert's SAME verdict removes the key, which the odds writers read,
    so a resync would write: `live_resync`, the key named."""
    ids, prov = world
    _store(ids["resync"], "NS")
    with session_scope() as s:
        m = s.get(Match, ids["resync"])
        m.external_ids = {**(m.external_ids or {}), "provider_orientation": "reversed"}
    _serve(prov)
    p = _plan_row(prov, ids["resync"])
    assert p["action"] == "live_resync"
    assert p["differs"] == {"provider_orientation": "reversed -> (removed: the served pair is the stored one)"}


def test_945_the_split_writes_nothing(world):
    ids, prov = world
    _store(ids["resync"], "NS")
    _serve(prov, status=MatchStatus.FINISHED, status_raw="FT", score=(31, 24))
    before = _stored(ids["resync"])
    md.orphans(CODE, prov, now=NOW)
    assert _stored(ids["resync"]) == before


def _console(monkeypatch, capsys, prov, sample):
    import cli
    import src.adapters.api_american_football as aaf
    monkeypatch.setattr(aaf, "APIAmericanFootballAdapter", lambda: prov)
    monkeypatch.setenv("SP_ODDS_FOOTBALL_RPM", "1000000")
    cli._dedupe_orphans(CODE, "api_american_football", False, sample)
    return capsys.readouterr().out.splitlines()


def test_945_console_counts_the_split_and_lists_live_rows_only_under_sample(world, monkeypatch, capsys):
    ids, prov = world
    _store(ids["resync"], "NS")
    _serve(prov)
    out = _console(monkeypatch, capsys, prov, None)                 # no --sample given
    plan = next(ln for ln in out if ln.startswith("  plan: "))
    assert "live, resync needed 0" in plan and "live 3 " in plan    # resync + the two live twins
    assert not any(ln.startswith("  [live] ") for ln in out)
    out = _console(monkeypatch, capsys, prov, 30)                   # --sample 30
    assert any(ln.startswith(f"  [live] id {ids['resync']} ") for ln in out)


def test_945_console_names_the_differing_fields_on_a_resync_line(world, monkeypatch, capsys):
    ids, prov = world
    _store(ids["resync"], "NS")
    _serve(prov, status=MatchStatus.FINISHED, status_raw="FT", score=(31, 24))
    out = _console(monkeypatch, capsys, prov, None)
    line = next(ln for ln in out if ln.startswith(f"  [live_resync] id {ids['resync']} "))
    assert "'differs': {'status': 'SCHEDULED -> FINISHED'" in line and "'home_score': 'None -> 31'" in line


# ---- #1001 (ARCHITECT 2026-11-14 13:38 ET, addendum 382 item 4): state against annotation; the id that serves another
# pair ----------------------------------------------------------------------------------------------------------------

def test_1001_a_reversal_already_recorded_with_everything_equal_is_live(world):
    """382 item 4(c): "one already recorded reads `live`". The key held `reversed`, the provider serves the reversed
    pair, SCHEDULED, no score, the stored kickoff: a resync writes nothing. Fail-first: on 151aadae `live_resync`."""
    ids, prov = world
    _store(ids["resync"], "NS")
    with session_scope() as s:
        m = s.get(Match, ids["resync"])
        m.external_ids = {**(m.external_ids or {}), "provider_orientation": "reversed"}
    prov.games = [x for x in prov.games if x.source_id != SID] + [_nm(10, 11, SID, PAST)]
    p = _plan_row(prov, ids["resync"])
    assert p["action"] == "live" and "differs" not in p and "annotation" not in p


def test_1001_matchday_and_stage_alone_read_live_and_are_named_as_annotations(world):
    """Question 4, ruled (382 item 4(b)): "matchday and stage do not count". Fail-first: on 151aadae neither was even
    named (the row read `live` with nothing said)."""
    ids, prov = world
    _store(ids["resync"], "NS")
    with session_scope() as s:
        m = s.get(Match, ids["resync"])
        m.matchday, m.stage = 3, "Regular Season"
    g = _nm(11, 10, SID, PAST)
    g.matchday, g.stage = 4, "Post Season"
    prov.games = [x for x in prov.games if x.source_id != SID] + [g]
    p = _plan_row(prov, ids["resync"])
    assert p["action"] == "live" and p["annotation"] == {"matchday": "3 -> 4", "stage": "Regular Season -> Post Season"}


def test_1001_a_not_stale_id_that_serves_another_pair_has_the_label_too(world):
    """382 item 4(c) names no staleness: "the id that answers with ANOTHER pair [...] is neither `live` nor `live,
    resync needed`". A twin's live row (kickoff ahead) whose id now serves two other teams reads the label."""
    ids, prov = world
    with session_scope() as s:
        sid = (s.get(Match, ids["twin_new"]).external_ids or {}).get(md_src())
    g = next(x for x in prov.games if x.source_id == sid)
    prov.games = [x for x in prov.games if x.source_id != sid] + [_nm(14, 15, sid, g.utc_date)]
    p = _plan_row(prov, ids["twin_new"])
    assert p["action"] == "live_other_pair" and p["stale"] is False


def md_src():
    from tests.test_dedupe_orphans import SRC
    return SRC


def test_1001_console_counts_the_other_pair_always_and_names_annotations_only_under_sample(world, monkeypatch, capsys):
    """The plan line carries "live, the id serves another pair N", its rows print whole without --sample; a `live`
    row's annotation prints on its [live] line under --sample ("annotation")."""
    ids, prov = world
    _store(ids["resync"], "NS")
    prov.games = [x for x in prov.games if x.source_id != SID] + [_nm(14, 15, SID, PAST)]
    out = _console(monkeypatch, capsys, prov, None)
    plan = next(ln for ln in out if ln.startswith("  plan: "))
    assert "live, resync needed 0 · live, the id serves another pair 1 · " in plan
    line = next(ln for ln in out if ln.startswith(f"  [live_other_pair] id {ids['resync']} "))
    assert "'pair': 'stored teams " in line and "'recorded': 'the mismatch is not recorded'" in line
    _serve(prov, status_raw="XQ")
    out = _console(monkeypatch, capsys, prov, 30)
    line = next(ln for ln in out if ln.startswith(f"  [live] id {ids['resync']} "))
    assert "'annotation': {'status_raw': 'NS -> XQ'}" in line
