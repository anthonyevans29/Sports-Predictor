"""STATUS_RAW ON THE AMERICAN-FOOTBALL PATH + THE SCORE-PRESENCE RULE (ARCHITECT 2026-11-01, addendum 202 item 3;
#763, #493), verbatim: "RULED: ONE small PR fixes both — status_raw = the provider's short verbatim, None when absent
(never "NS" for an absent block; the api_hockey rule), read before the default; #493's score-presence rule then fires
on an absent status as designed; the service's "never blank a stored code with an absent one" stands. Tests: an absent
status block, a "NS" block, a "FT" block, an unknown code."

The rows are synthetic, in the /games shape the adapter reads (tests/test_nfl_non_competitive.py's); no network. NFL
and NCAA share one parse (APIAmericanFootballAdapter._parse_games, competition_code "NFL" or "NCAA"), so every case
runs on both codes."""
from datetime import datetime

import pytest

from src.adapters.api_american_football import APIAmericanFootballAdapter
from src.db.schema import MatchStatus

CODES = ["NFL", "NCAA"]
_ABSENT = object()      # the "status" key left out of the game block altogether


def _row(status=_ABSENT, home_total=24, away_total=17, gid=7):
    game = {"id": gid, "date": {"timestamp": 1790000000}, "week": "Week 5", "stage": "Regular Season"}
    if status is not _ABSENT:
        game["status"] = status
    return {"game": game,
            "teams": {"home": {"id": 76370, "name": "Home Side"}, "away": {"id": 76371, "name": "Away Side"}},
            "scores": {"home": {"total": home_total}, "away": {"total": away_total}}}


def _parse(row, code):
    got = APIAmericanFootballAdapter.__new__(APIAmericanFootballAdapter)._parse_games({"response": [row]}, code, "2023")
    assert len(got) == 1
    assert got[0].competition_code == code
    return got[0]


# (1) an absent status block -------------------------------------------------------------------------------------

@pytest.mark.parametrize("code", CODES)
@pytest.mark.parametrize("status", [_ABSENT, None, {}, {"short": None}, {"short": ""}, {"long": "Finished"}],
                         ids=["no-key", "null", "empty-block", "null-short", "empty-short", "no-short"])
def test_an_absent_status_with_both_totals_is_finished_and_stores_no_code(status, code):
    """#493: the score-presence rule fires on an absent status; #763: status_raw stays None, never "NS"."""
    nm = _parse(_row(status), code)
    assert (nm.status, nm.status_raw, nm.home_score, nm.away_score) == (MatchStatus.FINISHED, None, 24, 17)


@pytest.mark.parametrize("code", CODES)
@pytest.mark.parametrize("totals", [(None, None), (24, None), (None, 17)], ids=["none", "home-only", "away-only"])
@pytest.mark.parametrize("status", [_ABSENT, None, {}, {"short": None}], ids=["no-key", "null", "empty-block",
                                                                            "null-short"])
def test_an_absent_status_without_both_totals_stays_scheduled(status, totals, code):
    nm = _parse(_row(status, *totals), code)
    assert (nm.status, nm.status_raw) == (MatchStatus.SCHEDULED, None)


@pytest.mark.parametrize("code", CODES)
@pytest.mark.parametrize("status", ["None", {"short": "None"}], ids=["bare", "short"])
def test_the_literal_none_text_is_absent_as_before(status, code):
    """The one absent form the old code already caught: still FINISHED with totals, and stored as no code."""
    nm = _parse(_row(status), code)
    assert (nm.status, nm.status_raw) == (MatchStatus.FINISHED, None)


# (2) an "NS" block ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("code", CODES)
@pytest.mark.parametrize("totals", [(24, 17), (None, None)], ids=["with-totals", "no-totals"])
def test_an_ns_block_is_scheduled_and_stored_even_with_totals(totals, code):
    """An explicit code is never overridden by the score-presence rule."""
    nm = _parse(_row({"short": "NS"}, *totals), code)
    assert (nm.status, nm.status_raw) == (MatchStatus.SCHEDULED, "NS")


# (3) an "FT" block ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("code", CODES)
def test_an_ft_block_is_finished_and_stored(code):
    nm = _parse(_row({"short": "FT"}), code)
    assert (nm.status, nm.status_raw, nm.home_score, nm.away_score) == (MatchStatus.FINISHED, "FT", 24, 17)


@pytest.mark.parametrize("code", CODES)
def test_a_bare_string_status_is_stored_verbatim(code):
    nm = _parse(_row("FT"), code)
    assert (nm.status, nm.status_raw) == (MatchStatus.FINISHED, "FT")


# (4) an unknown code --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("code", CODES)
@pytest.mark.parametrize("totals", [(24, 17), (None, None)], ids=["with-totals", "no-totals"])
def test_an_unknown_code_stays_scheduled_and_is_stored_verbatim(totals, code):
    """Law 4: the unchanged default (SCHEDULED), the code kept beside it, never remapped."""
    nm = _parse(_row({"short": "ZZ"}, *totals), code)
    assert (nm.status, nm.status_raw) == (MatchStatus.SCHEDULED, "ZZ")


# the mapping itself is unchanged ----------------------------------------------------------------------------------

@pytest.mark.parametrize("code", CODES)
def test_every_mapped_code_keeps_its_status_and_is_stored_verbatim(code):
    from src.adapters.api_american_football import _STATUS
    for short, status in _STATUS.items():
        nm = _parse(_row({"short": short}), code)
        assert (nm.status, nm.status_raw) == (status, short), short


# the service: a stored code is never blanked by a later absent one ------------------------------------------------

def test_a_stored_code_is_not_blanked_by_a_later_absent_status():
    """The adapter's output through IngestionService._upsert_match (service.py: "never blank a stored code with an
    absent one"); tests/test_status_raw.py::test_ingestion_persists_and_never_blanks_status_raw holds the same rule
    on a hand-built NormalizedMatch. The throwaway test DB (tests/conftest.py), never data/."""
    from src.db.database import init_db, session_scope
    from src.db.schema import Competition, Sport, Team
    from src.ingestion.service import IngestionService, SyncResult

    init_db()
    with session_scope() as s:
        comp = Competition(sport=Sport.NFL, code="AFRAW", name="x", area="x", type="LEAGUE")
        src_name = APIAmericanFootballAdapter.source_name
        h = Team(sport=Sport.NFL, name="Home Side AFRAW", external_ids={src_name: "76370"})
        a = Team(sport=Sport.NFL, name="Away Side AFRAW", external_ids={src_name: "76371"})
        s.add_all([comp, h, a])
        s.flush()
        svc = IngestionService.__new__(IngestionService)
        cache: dict = {}
        gid = 76301
        m = svc._upsert_match(s, _parse(_row({"short": "NS"}, None, None, gid=gid), "NCAA"), comp, SyncResult(),
                              cache)
        assert (m.status, m.status_raw) == (MatchStatus.SCHEDULED, "NS")
        svc._upsert_match(s, _parse(_row(None, 24, 17, gid=gid), "NCAA"), comp, SyncResult(), cache)
        assert (m.status, m.status_raw) == (MatchStatus.FINISHED, "NS")        # status follows, the code stays
        svc._upsert_match(s, _parse(_row({"short": "FT"}, 24, 17, gid=gid), "NCAA"), comp, SyncResult(), cache)
        assert (m.status, m.status_raw) == (MatchStatus.FINISHED, "FT")        # a present code overwrites
        assert m.utc_date == datetime(2026, 9, 21, 14, 13, 20)


# refresh-by-id: the second write path (the daily NCAA/NFL refresh by game id; src/ingestion/refresh_by_id.py) -----

def test_refresh_by_id_stores_the_code_and_never_blanks_it(monkeypatch):
    """refresh-by-id's own write (`if nm.status_raw: m.status_raw = nm.status_raw`) through the adapter's real
    get_game and _parse_games (its `_get` stubbed: no network). Before #763 the adapter never set status_raw, so this
    write never ran for NFL/NCAA. An NS answer stores "NS"; an answer with no status and no totals keeps it (never
    blanked); an answer with no status and both totals turns the row FINISHED and keeps "NS"; a later FT overwrites
    a stored "NS"; an empty answer (NOT FOUND) leaves the row untouched. The throwaway test DB, never data/."""
    from src.db.database import init_db, session_scope
    from src.db.schema import Competition, Match, Sport, Team
    from src.ingestion import refresh_by_id as rbi
    from src.ingestion import service as svc

    monkeypatch.setattr(svc, "_odds_sleep", lambda s: None)
    src_name = APIAmericanFootballAdapter.source_name
    kickoff = datetime(2026, 9, 21, 14, 13, 20)            # _row's timestamp 1790000000: the kickoff never moves
    now = datetime(2026, 9, 20, 12, 0)                      # the window: 2026-09-20 .. 2026-09-27 (UTC)
    init_db()
    with session_scope() as s:
        comp = Competition(sport=Sport.NFL, code="AFRBI", name="x", area="x", type="LEAGUE")
        h = Team(sport=Sport.NFL, name="Home Side AFRBI", external_ids={src_name: "76370"})
        a = Team(sport=Sport.NFL, name="Away Side AFRBI", external_ids={src_name: "76371"})
        s.add_all([comp, h, a])
        s.flush()
        ids = {}
        for sid in ("76401", "76402", "76403"):
            m = Match(sport=Sport.NFL, competition_id=comp.id, season="2026", utc_date=kickoff,
                      status=MatchStatus.SCHEDULED, home_team_id=h.id, away_team_id=a.id,
                      external_ids={src_name: sid})
            s.add(m)
            s.flush()
            ids[sid] = m.id

    answers: dict = {}
    adapter = APIAmericanFootballAdapter.__new__(APIAmericanFootballAdapter)
    adapter._get = lambda path, params=None: {"response": answers.get(str(params["id"]), [])}

    def state(sid):
        with session_scope() as s:
            m = s.get(Match, ids[sid])
            return m.status, m.status_raw, m.home_score, m.away_score

    def run(**by_sid):
        answers.clear()
        answers.update({sid: ([_row(st, *tot, gid=int(sid))] if st is not None else []) for sid, (st, tot)
                        in by_sid.items()})
        r = rbi.refresh("AFRBI", adapter, days=7, now=now)
        assert not r.get("error") and not r["unresolved"] and not r["refused"], r
        return r

    try:
        # step 1: an NS answer stores "NS" (all three rows)
        r = run(**{sid: ({"short": "NS"}, (None, None)) for sid in ids})
        assert [state(sid) for sid in ids] == [(MatchStatus.SCHEDULED, "NS", None, None)] * 3
        assert (r["updated"], r["unchanged"]) == (3, 0)          # a code-only write is an update (Codex on #775)
        r = run(**{"76402": ({"short": "NS"}, (None, None))})   # the same code again: nothing written, unchanged
        assert (r["updated"], r["unchanged"]) == (0, 1)
        # step 2: no status and no totals: the row stays SCHEDULED and the stored code is never blanked
        r = run(**{"76401": ({}, (None, None))})
        assert state("76401") == (MatchStatus.SCHEDULED, "NS", None, None)
        assert (r["updated"], r["unchanged"]) == (0, 1)
        # step 3: no status and both totals: FINISHED (#493's rule), the stored "NS" kept; FT overwrites "NS";
        # an empty answer (NOT FOUND) leaves its row untouched
        r = run(**{"76401": ({}, (24, 17)), "76402": ({"short": "FT"}, (24, 17)), "76403": (None, (None, None))})
        assert state("76401") == (MatchStatus.FINISHED, "NS", 24, 17)
        assert state("76402") == (MatchStatus.FINISHED, "FT", 24, 17)
        assert state("76403") == (MatchStatus.SCHEDULED, "NS", None, None)
        assert [x["match_id"] for x in r["not_found"]] == [ids["76403"]]
    finally:
        with session_scope() as s:
            s.query(Match).filter(Match.id.in_(list(ids.values()))).delete(synchronize_session=False)
