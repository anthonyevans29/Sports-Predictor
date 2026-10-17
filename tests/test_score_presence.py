"""#493 (ARCHITECT 2026-10-16, addendum 81 item 3; 2026-10-17, addendum 112 item 4), verbatim: "the rule fires where it
was meant to — a row whose provider status is ABSENT (None at the source) and whose two scores are present is FINISHED;
a row whose provider status is anything else keeps it (law 4: a status the provider stated is never overridden by
scores)." and "make the check run on the provider's raw status before the NS default is applied; the rule stays
"conservative unknowns": no score → not FINISHED. Tests with the raw payloads from tests/fixtures."

The rows are tests/fixtures/api_sports_status (provider-shaped, written: no kept answer exists for these adapters; its
README says so). The provider is faked (no network); the DB is the throwaway one (tests/conftest.py)."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner
from sqlalchemy import select

from src.adapters.api_american_football import APIAmericanFootballAdapter
from src.adapters.api_hockey import APIHockeyAdapter
from src.adapters.api_sports_status import game_status, provider_short
from src.db.schema import MatchStatus

FIX = Path(__file__).parent / "fixtures" / "api_sports_status"
S, F, L = MatchStatus.SCHEDULED, MatchStatus.FINISHED, MatchStatus.LIVE

AF_EXPECTED = {9101: F, 9102: F, 9103: F, 9104: F, 9105: S, 9106: S, 9107: F, 9108: S, 9109: S, 9110: F, 9111: L,
               9112: S}
HK_EXPECTED = {9201: F, 9202: F, 9203: F, 9204: F, 9205: S, 9206: S, 9207: F, 9208: S, 9209: S, 9210: F, 9211: F,
               9212: L, 9213: F, 9214: S}


def _payload(name):
    return json.loads((FIX / name).read_text())


def _faked(adapter, payload, calls=None):
    def fake_get(path, params=None):
        if calls is not None:
            calls.append((path, dict(params or {})))
        return payload
    adapter._get = fake_get
    return adapter


# --- the adapters, on the fixture rows ---

def test_american_football_parses_every_shape_on_the_raw_status():
    got = {int(m.source_id): m for m in
           _faked(APIAmericanFootballAdapter(), _payload("american_football_games.json")).list_matches("NFL", "2024")}
    assert {k: m.status for k, m in got.items()} == AF_EXPECTED
    assert (got[9101].home_score, got[9101].away_score) == (20, 17)          # the scores are stored as before


def test_hockey_parses_every_shape_on_the_raw_status_and_keeps_the_raw_code():
    got = {int(m.source_id): m for m in
           _faked(APIHockeyAdapter(), _payload("hockey_games.json")).list_matches("NHL", season="2024")}
    assert {k: m.status for k, m in got.items()} == HK_EXPECTED
    absent = {9201, 9202, 9203, 9204, 9207, 9208, 9213}
    assert {k for k, m in got.items() if m.status_raw is None} == absent         # no status stated: null, never "NS"
    assert got[9205].status_raw == got[9206].status_raw == "None"               # a stated text is kept verbatim
    assert (got[9210].status_raw, got[9211].status_raw, got[9209].status_raw) == ("FT", "AOT", "NS")
    assert (got[9213].home_score, got[9213].away_score) == (0, 2)               # a shutout's 0 is a score
    assert {m.season for m in got.values()} == {"2024"}                          # the moved parse keeps the season


def test_the_issue_receipt_table_now_reads_as_ruled():
    """#493's receipt: one row, home total 20 and away total 17, through APIAmericanFootballAdapter._parse_games."""
    def one(status):
        row = {"game": {"id": 1, "date": {"timestamp": 1725728400}, "status": status},
               "teams": {"home": {"id": 10}, "away": {"id": 11}},
               "scores": {"home": {"total": 20}, "away": {"total": 17}}}
        return APIAmericanFootballAdapter()._parse_games({"response": [row]}, "NFL", "2024")[0].status
    # before #493: SCHEDULED, SCHEDULED, SCHEDULED, FINISHED, FINISHED
    assert [one(x) for x in (None, {}, {"short": None}, "None", {"short": "None"})] == [F, F, F, S, S]


def test_a_stated_status_is_never_overridden_by_scores():
    from src.adapters.api_american_football import _STATUS
    for short, want in (("NS", S), ("Q2", L), ("POST", MatchStatus.POSTPONED), ("CANC", MatchStatus.CANCELLED),
                        ("None", S), ("anything", S)):
        assert game_status(short, _STATUS, 20, 17) == want, short


def test_absent_with_a_score_missing_is_not_finished():
    from src.adapters.api_hockey import _STATUS
    assert game_status(None, _STATUS, 3, None) == S
    assert game_status(None, _STATUS, None, 2) == S
    assert game_status(None, _STATUS, None, None) == S
    assert game_status(None, _STATUS, 0, 0) == F                                 # 0-0 is two scores


def test_provider_short_reads_the_status_as_sent():
    assert [provider_short(x) for x in (None, {}, "", [], {"short": None}, {"short": ""}, {"long": "Finished"})] \
        == [None] * 7
    assert provider_short({"short": "FT"}) == "FT"
    assert provider_short("FT") == "FT"                                          # a bare text block
    assert provider_short("None") == provider_short({"short": "None"}) == "None"


def test_raw_shorts_is_opt_in_and_names_each_parsed_game():
    data = _payload("american_football_games.json")
    a = APIAmericanFootballAdapter()
    plain = a._parse_games(data, "NFL", "2024")
    shorts = {}
    kept = a._parse_games(data, "NFL", "2024", raw_shorts=shorts)
    assert [(m.source_id, m.status) for m in plain] == [(m.source_id, m.status) for m in kept]
    assert shorts["9101"] is None and shorts["9105"] == "None" and shorts["9110"] == "FT"
    assert set(shorts) == {m.source_id for m in kept}
    hshorts = {}
    APIHockeyAdapter()._parse_games(_payload("hockey_games.json"), "2024", raw_shorts=hshorts)
    assert hshorts["9213"] is None and hshorts["9211"] == "AOT"


# --- the dry run ---

def test_fix_class_is_the_two_changed_classes_only():
    from src.ingestion import score_presence as sp
    assert sp.fix_class(None, 20, 17) == sp.ABSENT
    assert sp.fix_class("None", 20, 17) == sp.NONE_TEXT
    assert sp.fix_class(None, None, 17) is None and sp.fix_class("None", 20, None) is None
    assert sp.fix_class("NS", 20, 17) is None and sp.fix_class("FT", 20, 17) is None


def _world(code, sport, source, rows, teams=(), key=str):
    """A competition with stored 2024 rows: (provider id or None, status, home score, away score, kickoff[, Match
    fields]). A row's two teams carry the listing's team ids, home key(pid)+"0" and away key(pid)+"1" (the fixtures'
    9101 → 91010, 91011); a row with no provider id gets a pair of its own. `teams` stores the pairs of listed games
    that have no stored row, the same way (a listed game whose teams are not stored is skipped by the sync)."""
    from src.db.database import init_db, session_scope
    from src.db.schema import Competition, Match, Team
    init_db()
    with session_scope() as s:
        comp = Competition(sport=sport, code=code, name=code, area="USA", type="LEAGUE")
        s.add(comp)
        s.flush()

        def pair(pid):
            k = key(pid) if pid is not None else f"{code}-none"
            ts = [Team(sport=sport, name=f"{code} {k} {side}", external_ids={source: f"{k}{n}"})
                  for n, side in ((0, "Home"), (1, "Away"))]
            s.add_all(ts)
            s.flush()
            return ts
        for pid in teams:
            pair(pid)
        ids = {}
        for pid, status, hs, as_, ko, *more in rows:
            h, a = pair(pid)
            m = Match(**{"sport": sport, "competition_id": comp.id, "season": "2024", "utc_date": ko, "status": status,
                         "home_team_id": h.id, "away_team_id": a.id, "home_score": hs, "away_score": as_,
                         "stage": "Regular Season", "matchday": 1,
                         "external_ids": ({source: str(pid)} if pid is not None else {}), **(more[0] if more else {})})
            s.add(m)
            s.flush()
            ids[pid] = m.id
        return ids


def _statuses(ids):
    from src.db.database import session_scope
    from src.db.schema import Match
    with session_scope() as s:
        return {pid: (m.status, m.utc_date, m.home_score, m.away_score, m.stage, m.matchday, m.external_ids)
                for pid, mid in ids.items() for m in [s.get(Match, mid)]}


def _af_ko(day=7):
    return datetime(2024, 9, day, 17)


def test_the_dry_run_lists_every_change_with_its_id_and_writes_nothing():
    from src.db.schema import Sport
    from src.ingestion import score_presence as sp
    ids = _world("ZSPF", Sport.NFL, "api_american_football", [
        (9101, S, 20, 17, _af_ko()),          # absent + both scores, stored SCHEDULED: THE RULE CHANGES IT
        (9102, F, 20, 17, _af_ko()),          # absent + both scores, already FINISHED
        (9105, F, 20, 17, _af_ko()),          # the text "None", stored FINISHED: back to SCHEDULED (stated, unmapped)
        (9106, S, 20, 17, _af_ko()),          # the text "None", stored SCHEDULED: stays (left)
        (9107, S, None, None, _af_ko()),      # absent + both scores, stored SCHEDULED WITHOUT scores: a change, not
                                              # one of the stored SCHEDULED rows with both scores
        (9109, S, 20, 17, _af_ko()),          # a stated NS with both scores: left
        (9110, S, 20, 17, _af_ko(6)),         # FT, stored SCHEDULED a day off: the sync's own change + a kickoff
        (9112, S, 20, 17, _af_ko(), {"stage": "Pre Season", "matchday": None}),   # XYZ: the sync's stage + matchday
        (None, S, 7, 3, _af_ko()),            # no provider id: not in the listing, left
    ], teams=(9103, 9108, 9111))              # 9104's teams are not stored: the sync skips it
    before = _statuses(ids)
    calls, out = [], []
    ad = _faked(APIAmericanFootballAdapter(), _payload("american_football_games.json"), calls)
    rc = sp.run(["ZSPF"], ["2024"], lambda c: ad, out=out.append)
    assert rc == 0
    assert calls == [("games", {"league": 1, "season": 2024})]                  # one season read, no date
    assert _statuses(ids) == before                                              # writes nothing
    text = "\n".join(out)
    assert out[0].startswith("SCORE-PRESENCE DRY RUN (#493")
    assert "ZSPF 2024 · source api_american_football · listing 12 games · stored 9 rows" in out
    assert ("  THE SYNC'S RESOLUTION (each listed game as sync_matches resolves it): onto a stored row 8 (re-keyed 0) "
            "· creates 3 · refuses 0 · skips 1 (a team not stored)") in out
    assert ("  THE RULE CHANGES 3 stored row(s) at the next sync of ZSPF 2024 · listed with both scores and no status "
            "stated 5 · listed with both scores and the text 'None' 2 · already as the fixed parse reads 2 · not "
            "stored 2") in out
    assert (f"    match {ids[9101]} · provider 9101 · 2024-09-07 17:00:00Z · Regular Season · absent · SCHEDULED → "
            "FINISHED") in out
    assert (f"    match {ids[9105]} · provider 9105 · 2024-09-07 17:00:00Z · Regular Season · text 'None' · FINISHED → "
            "SCHEDULED") in out
    assert (f"    match {ids[9107]} · provider 9107 · 2024-09-07 17:00:00Z · Regular Season · absent · SCHEDULED → "
            "FINISHED") in out
    assert f"    already: match {ids[9102]} · provider 9102 · 2024-09-07 17:00:00Z · Regular Season · absent · " \
           "FINISHED" in out
    assert "    not stored: provider 9103 · 2024-09-07 17:00:00Z · absent · the sync creates it FINISHED" in out
    assert "    not stored: provider 9104 · 2024-09-07 17:00:00Z · absent · the sync skips it: a team is not " \
           "stored" in out
    # X + Y = N: 9107 is a change but holds no stored scores, so it is not among the 6
    assert "  stored SCHEDULED with both scores: 6 · the rule changes 1 · the rule leaves 5" in out
    assert f"    left: match {ids[9106]} · provider 9106 · 2024-09-07 17:00:00Z · Regular Season · the provider " \
           "states 'None' (a stated status the map lacks: stays SCHEDULED, law 4)" in out
    assert f"    left: match {ids[9109]} · provider 9109 · 2024-09-07 17:00:00Z · Regular Season · the provider " \
           "states 'NS' (the sync writes SCHEDULED)" in out
    assert f"    left: match {ids[9110]} · provider 9110 · 2024-09-06 17:00:00Z · Regular Season · the provider " \
           "states 'FT' (the sync writes FINISHED)" in out
    assert f"    left: match {ids[9112]} · provider 9112 · 2024-09-07 17:00:00Z · Pre Season · the provider " \
           "states 'XYZ' (the sync writes SCHEDULED)" in out
    assert f"    left: match {ids[None]} · provider — · 2024-09-07 17:00:00Z · Regular Season · not in the listing " \
           "(the sync does not touch it)" in out
    assert ("  THE SAME WHOLE-SEASON SYNC ALSO WRITES (not the rule's): status 1 · kickoff 1 · scores 1 (values not "
            "printed) · stage, matchday, season, status code 1 · provider id (re-key) 0 · listed games it creates "
            "2") in out
    assert (f"    status: match {ids[9110]} · provider 9110 · 2024-09-06 17:00:00Z · Regular Season · SCHEDULED → "
            "FINISHED (the provider states 'FT')") in out
    assert f"    kickoff: match {ids[9110]} · provider 9110 · 2024-09-06 17:00:00Z → 2024-09-07 17:00:00Z" in out
    assert f"    scores: match {ids[9107]} · provider 9107 · 2024-09-07 17:00:00Z · Regular Season" in out
    assert (f"    fields: match {ids[9112]} · provider 9112 · 2024-09-07 17:00:00Z · Pre Season · stage Pre Season → "
            "Regular Season · matchday — → 1") in out
    assert "    creates: provider 9108 · 2024-09-07 17:00:00Z · SCHEDULED" in out
    assert "    creates: provider 9111 · 2024-09-07 17:00:00Z · LIVE" in out
    assert "  THE SYNC WRITES NOTHING FOR: refused 0 · skipped 1 (a team not stored)" in out
    assert "    skipped (a team not stored): provider 9104" in out
    assert "20-17" not in text and "17-20" not in text                           # no score is printed
    tail = json.loads(out[-1].split(" ", 1)[1])
    assert out[-1].startswith("SCORE-PRESENCE-DRY-RUN {")
    assert tail["changes_total"] == 3 and tail["written"] == 0 and tail["unread"] == []
    assert tail["by_competition_season"]["ZSPF 2024"] == {
        "listing": 12, "stored": 9, "changes": 3, "listed_absent_both_scores": 5, "listed_none_text_both_scores": 2,
        "already": 2, "not_stored": 2, "sched_both_scores": 6, "sched_both_changed": 1, "left": 5,
        "onto_stored": 8, "rekeyed": 0, "created": 3, "refused": 0, "skipped": 1,
        "also_status": 1, "also_kickoff": 1, "also_scores": 1, "also_fields": 1, "also_created": 2}


def _af_game(gid, home, away, when, totals=(20, 17), short=None):
    """One american-football /games row in the fixtures' shape; no `status` key when `short` is None."""
    game = {"id": gid, "date": {"timestamp": int(when.replace(tzinfo=timezone.utc).timestamp())},
            "stage": "Regular Season", "week": "Week 1"}
    if short is not None:
        game["status"] = {"short": short}
    return {"game": game, "league": {"id": 1, "season": "2024"},
            "teams": {"home": {"id": home, "name": f"Home {gid}"}, "away": {"id": away, "name": f"Away {gid}"}},
            "scores": {"home": {"total": totals[0]}, "away": {"total": totals[1]}}}


def test_a_game_the_sync_re_keys_onto_a_stored_row_is_the_rule_s_change():
    """A stored row the next sync re-keys (the same pair within 12 hours, under a new provider id) is resolved as the
    sync resolves it: the rule's change, its kickoff and its re-key are on the receipt, and the sync then does it."""
    from src.db.database import session_scope
    from src.db.schema import Match, Sport
    from src.ingestion import score_presence as sp
    from src.ingestion.service import IngestionService
    key = "ZSPK{}".format
    ids = _world("ZSPK", Sport.NFL, "api_american_football", [(111, S, 20, 17, _af_ko())], key=key)
    before = _statuses(ids)
    payload = {"response": [_af_game(222, "ZSPK1110", "ZSPK1111", datetime(2024, 9, 7, 18))]}
    out = []
    ad = _faked(APIAmericanFootballAdapter(), payload)
    assert sp.run(["ZSPK"], ["2024"], lambda c: ad, out=out.append) == 0
    assert _statuses(ids) == before                                              # writes nothing
    assert ("  THE SYNC'S RESOLUTION (each listed game as sync_matches resolves it): onto a stored row 1 (re-keyed 1) "
            "· creates 0 · refuses 0 · skips 0 (a team not stored)") in out
    assert ("  THE RULE CHANGES 1 stored row(s) at the next sync of ZSPK 2024 · listed with both scores and no status "
            "stated 1 · listed with both scores and the text 'None' 0 · already as the fixed parse reads 0 · not "
            "stored 0") in out
    assert (f"    match {ids[111]} · provider 111 → 222 (re-keyed) · 2024-09-07 17:00:00Z · Regular Season · absent · "
            "SCHEDULED → FINISHED") in out
    assert "  stored SCHEDULED with both scores: 1 · the rule changes 1 · the rule leaves 0" in out
    assert not [ln for ln in out if ln.startswith("    left:")]
    assert ("  THE SAME WHOLE-SEASON SYNC ALSO WRITES (not the rule's): status 0 · kickoff 1 · scores 0 (values not "
            "printed) · stage, matchday, season, status code 0 · provider id (re-key) 1 · listed games it creates "
            "0") in out
    assert (f"    kickoff: match {ids[111]} · provider 111 → 222 (re-keyed) · 2024-09-07 17:00:00Z → "
            "2024-09-07 18:00:00Z") in out
    assert f"    re-key: match {ids[111]} · provider 111 → 222 (re-keyed) · 2024-09-07 17:00:00Z · Regular Season" in out
    # the sync, on the same answer, does what the receipt says
    res = IngestionService(ad).sync_matches("ZSPK", "2024")
    assert (res.rekeyed, res.created) == (1, 0)
    with session_scope() as s:
        m = s.get(Match, ids[111])
        assert (m.status, m.utc_date, m.external_ids["api_american_football"]) == \
            (F, datetime(2024, 9, 7, 18), "222")
        assert m.external_ids["api_american_football_prev"] == ["111"]


def test_a_re_key_by_the_row_s_history_and_a_refusal_are_resolved_as_the_sync_resolves_them():
    from src.db.schema import Sport
    from src.ingestion import score_presence as sp
    key = "ZSPP{}".format
    ids = _world("ZSPP", Sport.NFL, "api_american_football", [
        # the provider used 222 for this row before: a week away, only its `_prev` history finds it
        (333, S, 20, 17, _af_ko(), {"external_ids": {"api_american_football": "333",
                                                     "api_american_football_prev": ["222"]}}),
        (555, S, 20, 17, _af_ko()),           # still listed: a second id for its pair within 12 hours is refused
    ], key=key)
    before = _statuses(ids)
    payload = {"response": [_af_game(222, "ZSPP3330", "ZSPP3331", datetime(2024, 9, 14, 17)),
                            _af_game(555, "ZSPP5550", "ZSPP5551", _af_ko(), short="FT"),
                            _af_game(444, "ZSPP5550", "ZSPP5551", datetime(2024, 9, 7, 18))]}
    out = []
    ad = _faked(APIAmericanFootballAdapter(), payload)
    assert sp.run(["ZSPP"], ["2024"], lambda c: ad, out=out.append) == 0
    assert _statuses(ids) == before
    assert ("  THE SYNC'S RESOLUTION (each listed game as sync_matches resolves it): onto a stored row 2 (re-keyed 1) "
            "· creates 0 · refuses 1 · skips 0 (a team not stored)") in out
    assert (f"    match {ids[333]} · provider 333 → 222 (re-keyed) · 2024-09-07 17:00:00Z · Regular Season · absent · "
            "SCHEDULED → FINISHED") in out
    assert (f"    kickoff: match {ids[333]} · provider 333 → 222 (re-keyed) · 2024-09-07 17:00:00Z → "
            "2024-09-14 17:00:00Z") in out
    assert (f"    not stored: provider 444 · 2024-09-07 18:00:00Z · absent · the sync refuses it, creating nothing: "
            f"stored row {ids[555]} holds its natural key but its id 555 is still in this listing (the provider lists "
            f"both 555 and 444) — not created") in out
    assert "  THE SYNC WRITES NOTHING FOR: refused 1 · skipped 0 (a team not stored)" in out
    assert (f"    refused: provider 444 · 2024-09-07 18:00:00Z · stored row {ids[555]} holds its natural key but its id "
            f"555 is still in this listing (the provider lists both 555 and 444) — not created") in out
    assert "  stored SCHEDULED with both scores: 2 · the rule changes 1 · the rule leaves 1" in out
    assert f"    left: match {ids[555]} · provider 555 · 2024-09-07 17:00:00Z · Regular Season · the provider " \
           "states 'FT' (the sync writes FINISHED)" in out


def test_changed_and_left_add_up_to_the_stored_scheduled_rows_with_both_scores():
    """Pure: two stored rows holding one provider id; the sync writes the listed game to the last (its cache). The
    other is left, with why, so the rule's X and the left Y still add up to N."""
    from src.adapters.normalized import NormalizedMatch
    from src.db.schema import Sport
    from src.ingestion import score_presence as sp
    ko = _af_ko()
    rows = [{"id": i, "pid": "501", "season": "2024", "utc_date": ko, "stage": None, "matchday": None,
             "status": "SCHEDULED", "status_raw": None, "home_score": 20, "away_score": 17} for i in (1, 2)]
    nm = NormalizedMatch(sport=Sport.NFL, competition_code="NFL", season="2024", utc_date=ko, status=F,
                         home_team_source_id="h", away_team_source_id="a", source="api_american_football",
                         source_id="501", home_score=20, away_score=17)
    r = sp.compare([nm], {"501": None}, rows, {"501": {"row": rows[1], "rekey": None}})
    assert (r["sched_both"], r["sched_both_changed"], len(r["left"])) == (2, 1, 1)
    assert [x["id"] for x in r["changes"]] == [2]
    assert r["left"][0]["why"] == "its provider id is listed, but the sync writes that game to match 2 (it does not " \
                                  "touch this row)"


def test_the_dry_run_reads_hockey_and_every_stored_season_by_default():
    from src.db.schema import Sport
    from src.ingestion import score_presence as sp
    ko = datetime(2024, 10, 8, 23)
    ids = _world("ZSPH", Sport.NHL, "api_hockey", [(9213, S, 0, 2, ko), (9208, S, 3, 2, ko)])
    calls, out = [], []
    ad = _faked(APIHockeyAdapter(), _payload("hockey_games.json"), calls)
    assert sp.run(["ZSPH"], [], lambda c: ad, out=out.append) == 0
    assert calls == [("games", {"league": 57, "season": 2024})]
    assert f"    match {ids[9213]} · provider 9213 · 2024-10-08 23:00:00Z · Regular Season · absent · SCHEDULED → " \
           "FINISHED" in out
    assert f"    left: match {ids[9208]} · provider 9208 · 2024-10-08 23:00:00Z · Regular Season · no status stated " \
           "and a score missing in the listing: stays SCHEDULED (no score, not FINISHED)" in out
    assert ("  THE SYNC'S RESOLUTION (each listed game as sync_matches resolves it): onto a stored row 2 (re-keyed 0) "
            "· creates 0 · refuses 0 · skips 12 (a team not stored)") in out


def test_a_listing_that_cannot_be_read_is_named_and_exits_1(capsys):
    from src.db.schema import Sport
    from src.ingestion import score_presence as sp
    _world("ZSPE", Sport.NFL, "api_american_football", [(1, S, 1, 0, _af_ko())])
    ad = APIAmericanFootballAdapter()

    def boom(path, params=None):
        raise RuntimeError("api_american_football games: rate limited")
    ad._get = boom
    out = []
    assert sp.run(["ZSPE", "ZSPNOTHERE"], [], lambda c: ad, out=out.append) == 1
    assert ("✗ ZSPE 2024: the listing could not be read (RuntimeError: api_american_football games: rate limited) · "
            "nothing compared") in out
    assert "ZSPNOTHERE: not in the DB · nothing stored, nothing to change" in out
    assert json.loads(out[-1].split(" ", 1)[1])["unread"] == ["ZSPE 2024"]


def test_no_database_file_refuses_before_anything_is_opened(tmp_path, monkeypatch):
    from sqlalchemy import create_engine

    import src.db.database as db
    from src.ingestion import score_presence as sp
    gone = tmp_path / "data" / "nope.db"
    monkeypatch.setattr(db, "get_engine", lambda: create_engine(f"sqlite:///{gone}"))
    out = []
    assert sp.run(["NFL"], [], lambda c: pytest.fail("no adapter is made"), out=out.append) == 2
    assert out == [f"✗ no database at {gone.resolve()}; the dry run never creates one (law 5) · nothing read"]
    assert not gone.exists() and not gone.parent.exists()


def test_the_cli_command_runs_the_dry_run(monkeypatch):
    import cli
    from src.db.database import init_db, session_scope
    from src.db.schema import Competition, Sport
    init_db()
    with session_scope() as s:
        if s.execute(select(Competition).where(Competition.code == "NHL")).scalar_one_or_none() is None:
            s.add(Competition(sport=Sport.NHL, code="NHL", name="NHL", area="USA", type="LEAGUE"))
    calls = []
    monkeypatch.setattr(cli, "_adapter_for_competition",
                        lambda c: _faked(APIHockeyAdapter(), _payload("hockey_games.json"), calls))
    res = CliRunner().invoke(cli.cli, ["score-presence-dry-run", "--competition", "nhl", "--season", "1999"])
    assert res.exit_code == 0, res.output
    assert calls == [("games", {"league": 57, "season": 1999})]
    assert "NHL 1999 · source api_hockey · listing 14 games · stored 0 rows" in res.output
    assert '"written": 0' in res.output
    res = CliRunner().invoke(cli.cli, ["score-presence-dry-run", "--competition", "MLB"])
    assert res.exit_code == 2                                                    # only the three competitions
