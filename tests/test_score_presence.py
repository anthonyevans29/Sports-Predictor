"""#493 (ARCHITECT 2026-10-16, addendum 81 item 3; 2026-10-17, addendum 112 item 4 and addendum 116 item 4), verbatim:
"the rule fires where it was meant to — a row whose provider status is ABSENT (None at the source) and whose two
scores are present is FINISHED; a row whose provider status is anything else keeps it (law 4: a status the provider
stated is never overridden by scores)." and "make the check run on the provider's raw status before the NS default is
applied; the rule stays "conservative unknowns": no score → not FINISHED. Tests with the raw payloads from
tests/fixtures." Addendum 116 item 4: (1) a status-only apply, the fingerprint printed before and after on the test DB;
(2) NFL regular-season rows held; (3) the kickoff-age condition; (4) the literal text "None" is NO status.

The rows are tests/fixtures/api_sports_status (provider-shaped, written: no kept answer exists for these adapters; its
README says so). The provider is faked (no network); the DB is the throwaway one (tests/conftest.py), or a fresh file
under tmp_path for the tests that need a competition coded NFL or NCAA of their own."""
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner
from sqlalchemy import select

from src.adapters import api_sports_status as ass
from src.adapters.api_american_football import APIAmericanFootballAdapter
from src.adapters.api_hockey import APIHockeyAdapter
from src.adapters.api_sports_status import game_status, no_status, provider_short
from src.db.schema import MatchStatus

FIX = Path(__file__).parent / "fixtures" / "api_sports_status"
S, F, L = MatchStatus.SCHEDULED, MatchStatus.FINISHED, MatchStatus.LIVE
NOW = datetime(2026, 10, 17, 17, 15)          # the rule's clock in these tests (the fixtures' games are in 2024)
HELD = "not preseason (held: regular season or postseason, nfl_elo_v1's walk reads it; needs a gate verdict; own Issue)"
PRE = "preseason (applied with the rest)"
HELD_NFL = ("NFL not preseason, regular season and postseason: the rows nfl_elo_v1's walk reads (nfl_predict.is_preseason "
            "false); they change its ratings and need a gate verdict (addendum 116 item 4 (2)); their own Issue, the NFL "
            "re-declaration lane")
HELD_REKEY = ("re-keyed: the sync answers this game under a new provider id; a status-only write cannot carry the re-key "
              "(the row keeps its old provider id and kickoff), and where the sync matched it through the NCAA placeholder "
              "window (SCHEDULED rows only) the next sync no longer finds it once FINISHED and creates a twin; for the "
              "architect")
NEEDS = ("  NEEDS SCORES (held for the architect: the rule reads FINISHED, but the stored scores are missing or differ from "
         "the listing's totals; a status-only write cannot complete the row, addendum 116 item 4 (1) and addendum 112 item "
         "4; not on the APPLY line, score-presence-apply refuses them; scores not printed): ")
TEXT_NONE = ("  THE TEXT 'None' CHANGES (not on the APPLY line: addendum 116 item 4 (4) expects none; the architect's word "
             "whether these ids are applied; score-presence-apply accepts them when named): match ids ")

AF_EXPECTED = {9101: F, 9102: F, 9103: F, 9104: F, 9105: F, 9106: F, 9107: F, 9108: S, 9109: S, 9110: F, 9111: L,
               9112: S}
HK_EXPECTED = {9201: F, 9202: F, 9203: F, 9204: F, 9205: F, 9206: F, 9207: F, 9208: S, 9209: S, 9210: F, 9211: F,
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
    absent = {9201, 9202, 9203, 9204, 9205, 9206, 9207, 9208, 9213}
    assert {k for k, m in got.items() if m.status_raw is None} == absent         # no status: null, never "NS", and
    assert (got[9210].status_raw, got[9211].status_raw, got[9209].status_raw) == ("FT", "AOT", "NS")  # never "None"
    assert (got[9213].home_score, got[9213].away_score) == (0, 2)               # a shutout's 0 is a score
    assert {m.season for m in got.values()} == {"2024"}                          # the moved parse keeps the season


def test_the_issue_receipt_table_now_reads_as_ruled():
    """#493's receipt: one row, home total 20 and away total 17, through APIAmericanFootballAdapter._parse_games.
    Addendum 116 item 4 (4): the text "None" (the last two) is no status, the same as absent."""
    def one(status):
        row = {"game": {"id": 1, "date": {"timestamp": 1725728400}, "status": status},
               "teams": {"home": {"id": 10}, "away": {"id": 11}},
               "scores": {"home": {"total": 20}, "away": {"total": 17}}}
        return APIAmericanFootballAdapter()._parse_games({"response": [row]}, "NFL", "2024")[0].status
    # before #493: SCHEDULED, SCHEDULED, SCHEDULED, FINISHED, FINISHED
    assert [one(x) for x in (None, {}, {"short": None}, "None", {"short": "None"})] == [F, F, F, F, F]


def test_a_stated_status_is_never_overridden_by_scores():
    from src.adapters.api_american_football import _STATUS
    ko = datetime(2024, 9, 7, 17)
    for short, want in (("NS", S), ("Q2", L), ("POST", MatchStatus.POSTPONED), ("CANC", MatchStatus.CANCELLED),
                        ("anything", S), ("none", S)):                       # only the exact text "None" is no status
        assert game_status(short, _STATUS, 20, 17, ko, "NFL", NOW) == want, short


def test_no_status_with_a_score_missing_is_not_finished_whenever():
    from src.adapters.api_hockey import _STATUS
    ko = datetime(2024, 10, 8, 23)
    for short in (None, "None"):
        assert game_status(short, _STATUS, 3, None, ko, "NHL", NOW) == S
        assert game_status(short, _STATUS, None, 2, ko, "NHL", NOW) == S
        assert game_status(short, _STATUS, None, None, ko, "NHL", NOW) == S
        assert game_status(short, _STATUS, None, None, ko, "NHL", ko) == S       # before the threshold too: not None
        assert game_status(short, _STATUS, 0, 0, ko, "NHL", NOW) == F            # 0-0 is two scores


def test_provider_short_reads_the_status_as_sent_and_none_text_is_no_status():
    assert [provider_short(x) for x in (None, {}, "", [], {"short": None}, {"short": ""}, {"long": "Finished"})] \
        == [None] * 7
    assert provider_short({"short": "FT"}) == "FT"
    assert provider_short("FT") == "FT"                                          # a bare text block
    assert provider_short("None") == provider_short({"short": "None"}) == "None"  # read verbatim (the dry run lists it)
    assert no_status(None) and no_status("None")                                 # addendum 116 item 4 (4)
    assert not no_status("NS") and not no_status("FT") and not no_status("none")


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
    assert hshorts["9213"] is None and hshorts["9211"] == "AOT" and hshorts["9206"] == "None"


# --- (3) the kickoff-age condition ---

def test_the_longest_game_constants_are_as_ruled_and_named():
    assert ass.LONGEST_GAME_H == {"SOCCER": 3, "NHL": 4, "NFL": 5, "NCAA": 5, "MLB": 6}
    assert ass.longest_game_text() == "SOCCER 3h · NHL 4h · NFL 5h · NCAA 5h · MLB 6h"
    assert [ass.sport_key(c) for c in ("NFL", "NCAA", "NHL", "ncaa", None, "ZSPF")] == \
        ["NFL", "NCAA", "NHL", "NCAA", "NFL", "NFL"]
    from src.db.schema import Sport
    assert ass.sport_key("ZSPH", Sport.NHL) == "NHL" and ass.sport_key("ZSPF", Sport.NFL) == "NFL"


_NO_KEY = object()


def _parse_one(code, ko, status, totals=(20, 17), now=None):
    """One game of `code` (NFL / NCAA: american football; NHL: hockey) kicking off at `ko`, parsed at `now`."""
    if code == "NHL":
        row = {"id": 1, "date": ko.replace(tzinfo=timezone.utc).isoformat(), "teams": {"home": {"id": 10},
               "away": {"id": 11}}, "scores": {"home": totals[0], "away": totals[1]}}
        if status is not _NO_KEY:
            row["status"] = status
        return APIHockeyAdapter()._parse_games({"response": [row]}, "2026", now=now)[0]
    game = {"id": 1, "date": {"timestamp": int(ko.replace(tzinfo=timezone.utc).timestamp())}}
    if status is not _NO_KEY:
        game["status"] = status
    row = {"game": game, "teams": {"home": {"id": 10}, "away": {"id": 11}},
           "scores": {"home": {"total": totals[0]}, "away": {"total": totals[1]}}}
    return APIAmericanFootballAdapter()._parse_games({"response": [row]}, code, "2026", now=now)[0]


@pytest.mark.parametrize("code,hours", [("NFL", 5), ("NCAA", 5), ("NHL", 4)])
@pytest.mark.parametrize("status", [_NO_KEY, None, {}, {"short": None}, {"short": ""}, "None", {"short": "None"}])
def test_the_kickoff_age_condition_on_both_sides_of_the_threshold(code, hours, status):
    """Addendum 116 item 4 (3): no status with both totals reads FINISHED only when now >= kickoff + the sport's longest
    game; before that the parse carries NO status for the game (None: the stored one is left alone). A game in play
    with running totals never reads FINISHED. (4): the text "None" is the same as absent."""
    ko = datetime(2026, 10, 18, 17)
    edge = ko + timedelta(hours=hours)
    assert _parse_one(code, ko, status, now=ko + timedelta(minutes=50)).status is None      # in play, running totals
    assert _parse_one(code, ko, status, now=edge - timedelta(seconds=1)).status is None
    assert _parse_one(code, ko, status, now=edge).status == F
    assert _parse_one(code, ko, status, now=edge + timedelta(days=300)).status == F
    assert _parse_one(code, ko, status, totals=(None, None), now=edge - timedelta(hours=1)).status == S   # no score
    assert _parse_one(code, ko, status, totals=(20, None), now=edge + timedelta(days=1)).status == S
    live = {"short": "P2" if code == "NHL" else "Q3"}
    assert _parse_one(code, ko, live, now=ko + timedelta(minutes=50)).status == L          # a stated status keeps it


def test_the_parse_reads_utc_now_once_when_no_clock_is_given(monkeypatch):
    ko = datetime(2026, 10, 18, 17)
    clock = [ko + timedelta(hours=1)]
    monkeypatch.setattr(ass, "utc_now_naive", lambda: clock[0])
    assert _parse_one("NFL", ko, _NO_KEY).status is None
    clock[0] = ko + timedelta(hours=5)
    assert _parse_one("NFL", ko, _NO_KEY).status == F
    assert _parse_one("NHL", ko - timedelta(hours=1), "None").status == F                  # 6h after its kickoff


def _team_world(code, sport, source, games):
    """A competition `code` with, per game, its two teams (provider ids '<code><gid>0' / '<code><gid>1') and, when
    `stored` is not None, a stored row: games = [(gid, stored status or None, ko, status_raw)]. Returns {gid: id}."""
    from src.db.database import init_db, session_scope
    from src.db.schema import Competition, Match, Team
    init_db()
    ids = {}
    with session_scope() as s:
        comp = Competition(sport=sport, code=code, name=code, area="USA", type="LEAGUE")
        s.add(comp)
        s.flush()
        for gid, stored, ko, raw in games:
            h, a = (Team(sport=sport, name=f"{code} {gid} {side}", external_ids={source: f"{code}{gid}{n}"})
                    for n, side in ((0, "Home"), (1, "Away")))
            s.add_all([h, a])
            s.flush()
            if stored is not None:
                m = Match(sport=sport, competition_id=comp.id, season="2026", utc_date=ko, status=stored,
                          status_raw=raw, home_team_id=h.id, away_team_id=a.id, home_score=7, away_score=3,
                          stage="Regular Season", external_ids={source: str(gid)})
                s.add(m)
                s.flush()
                ids[gid] = m.id
    return ids


def _rows_of(code):
    from src.db.database import session_scope
    from src.db.schema import Competition, Match
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == code)).scalar_one()
        return {m.external_ids[next(iter(m.external_ids))]: (m.status, m.status_raw, m.home_score, m.away_score,
                                                              m.utc_date)
                for m in s.execute(select(Match).where(Match.competition_id == comp.id)).scalars()}


def test_the_sync_leaves_a_stored_status_alone_before_the_threshold_and_creates_scheduled(monkeypatch):
    """Parse -> IngestionService: a listing with no status (absent, {}, the text "None") and running totals before
    kickoff + 5h writes the scores as the sync always has but never the status: a stored FINISHED, LIVE or SCHEDULED row
    keeps it, and a new game is created SCHEDULED. At kickoff + 5h the same listing reads FINISHED."""
    from src.db.schema import Sport
    from src.ingestion.service import IngestionService
    code, src = "ZSPA", "api_american_football"
    ko = datetime(2026, 10, 18, 17)
    _team_world(code, Sport.NFL, src, [(7001, F, ko, None), (7002, L, ko, None), (7003, S, ko, None),
                                       (7004, None, ko, None), (7005, S, ko, None)])

    def game(gid, status=_NO_KEY, totals=(21, 17)):
        g = {"id": gid, "date": {"timestamp": int(ko.replace(tzinfo=timezone.utc).timestamp())}}
        if status is not _NO_KEY:
            g["status"] = status
        return {"game": g, "teams": {"home": {"id": f"{code}{gid}0"}, "away": {"id": f"{code}{gid}1"}},
                "scores": {"home": {"total": totals[0]}, "away": {"total": totals[1]}}}
    payload = {"response": [game(7001), game(7002, "None"), game(7003, {}), game(7004),
                            game(7005, totals=(None, None))]}
    clock = [ko + timedelta(hours=1)]
    monkeypatch.setattr(ass, "utc_now_naive", lambda: clock[0])
    ad = _faked(APIAmericanFootballAdapter(), payload)
    res = IngestionService(ad).sync_matches(code, "2026")
    assert (res.created, res.updated) == (1, 4)
    got = _rows_of(code)
    assert {k: v[0] for k, v in got.items()} == {"7001": F, "7002": L, "7003": S, "7004": S, "7005": S}
    assert got["7001"][2:4] == (21, 17) and got["7005"][2:4] == (7, 3)          # scores: the sync's, as always
    clock[0] = ko + timedelta(hours=5) - timedelta(seconds=1)
    IngestionService(ad).sync_matches(code, "2026")
    assert {k: v[0] for k, v in _rows_of(code).items()} == {"7001": F, "7002": L, "7003": S, "7004": S, "7005": S}
    clock[0] = ko + timedelta(hours=5)
    IngestionService(ad).sync_matches(code, "2026")
    assert {k: v[0] for k, v in _rows_of(code).items()} == {"7001": F, "7002": F, "7003": F, "7004": F, "7005": S}


def test_the_hockey_sync_keeps_a_live_row_and_its_code_until_kickoff_plus_4h(monkeypatch):
    from src.db.schema import Sport
    from src.ingestion.service import IngestionService
    code = "ZSPL"
    ko = datetime(2026, 10, 18, 23)
    _team_world(code, Sport.NHL, "api_hockey", [(7101, L, ko, "P2"), (7102, F, ko, "FT")])
    payload = {"response": [{"id": gid, "date": ko.replace(tzinfo=timezone.utc).isoformat(), "status": st,
                             "teams": {"home": {"id": f"{code}{gid}0"}, "away": {"id": f"{code}{gid}1"}},
                             "scores": {"home": 2, "away": 1}} for gid, st in ((7101, None), (7102, {"short": "None"}))]}
    ad = _faked(APIHockeyAdapter(), payload)
    clock = [ko + timedelta(hours=4) - timedelta(seconds=1)]
    monkeypatch.setattr(ass, "utc_now_naive", lambda: clock[0])
    IngestionService(ad).sync_matches(code, "2026")
    got = _rows_of(code)
    assert (got["7101"][:2], got["7102"][:2]) == ((L, "P2"), (F, "FT"))        # status and code both left alone
    clock[0] = ko + timedelta(hours=4)
    IngestionService(ad).sync_matches(code, "2026")
    assert {k: v[0] for k, v in _rows_of(code).items()} == {"7101": F, "7102": F}


# --- the dry run ---

def test_fix_class_is_the_rule_s_two_no_status_classes_only():
    from src.ingestion import score_presence as sp
    assert sp.fix_class(None, 20, 17) == sp.NO_STATUS
    assert sp.fix_class("None", 20, 17) == sp.NONE_TEXT
    assert sp.fix_class(None, None, 17) is None and sp.fix_class("None", 20, None) is None
    assert sp.fix_class("NS", 20, 17) is None and sp.fix_class("FT", 20, 17) is None


def _world(code, sport, source, rows, teams=(), key=str, season="2024"):
    """A competition with stored rows of `season`: (provider id or None, status, home score, away score, kickoff[,
    Match fields]). A row's two teams carry the listing's team ids, home key(pid)+"0" and away key(pid)+"1" (the
    fixtures' 9101 → 91010, 91011); a row with no provider id gets a pair of its own. `teams` stores the pairs of listed
    games that have no stored row, the same way (a listed game whose teams are not stored is skipped by the sync)."""
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
            m = Match(**{"sport": sport, "competition_id": comp.id, "season": season, "utc_date": ko,
                         "status": status, "home_team_id": h.id, "away_team_id": a.id, "home_score": hs,
                         "away_score": as_, "stage": "Regular Season", "matchday": 1,
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


HEADER = [
    "  the rule: no provider status (none sent, or the text 'None') with both scores is FINISHED once now >= kickoff + "
    "the sport's longest game, and before that the stored status is left alone; no status with a score missing is "
    "SCHEDULED; a status the provider stated keeps its mapping (an unknown code SCHEDULED)",
    "  longest game (addendum 116 item 4 (3)): SOCCER 3h · NHL 4h · NFL 5h · NCAA 5h · MLB 6h · now 2026-10-17 17:15:00Z",
    "  the age clock (api_sports_status.age_until, the rule's and this receipt's): from the kickoff; an NCAA kickoff at the "
    "provider's TBD placeholder (04:00:00Z) from the end of its game day (kickoff + 24h, src/ingestion/placeholder.py); a "
    "kickoff sent as a date with no time from the end of that UTC date; a row whose clock moved says so"]


def test_the_dry_run_lists_every_change_with_its_id_and_writes_nothing():
    from src.db.schema import Sport
    from src.ingestion import score_presence as sp
    ids = _world("ZSPF", Sport.NFL, "api_american_football", [
        (9101, S, 20, 17, _af_ko()),          # no status sent + both scores, stored SCHEDULED: THE RULE CHANGES IT
        (9102, F, 20, 17, _af_ko()),          # no status sent + both scores, already FINISHED
        (9105, F, 20, 17, _af_ko()),          # the text "None", stored FINISHED: stays FINISHED (for the record)
        (9106, S, 20, 17, _af_ko()),          # the text "None", stored SCHEDULED: no status, the same as absent: a change,
                                              # off the APPLY line (item 4 (4) expects none: the architect's word)
        (9107, S, None, None, _af_ko()),      # no status sent + both scores, stored SCHEDULED WITHOUT scores: NEEDS SCORES
                                              # (a status-only write cannot complete it), not a stored row with both
        (9109, S, 20, 17, _af_ko()),          # a stated NS with both scores: left
        (9110, S, 20, 17, _af_ko(6)),         # FT, stored SCHEDULED a day off: a sync's change + a kickoff (info only)
        (9112, S, 20, 17, _af_ko(), {"stage": "Pre Season", "matchday": None}),   # XYZ: a sync's stage + matchday
        (None, S, 7, 3, _af_ko()),            # no provider id: not in the listing, left
    ], teams=(9103, 9108, 9111))              # 9104's teams are not stored: the sync skips it
    before = _statuses(ids)
    calls, out = [], []
    ad = _faked(APIAmericanFootballAdapter(), _payload("american_football_games.json"), calls)
    rc = sp.run(["ZSPF"], ["2024"], lambda c: ad, out=out.append, now=NOW)
    assert rc == 0
    assert calls == [("games", {"league": 1, "season": 2024})]                  # one season read, no date
    assert _statuses(ids) == before                                              # writes nothing
    text = "\n".join(out)
    assert out[0] == ("SCORE-PRESENCE DRY RUN (#493; ARCHITECT 2026-10-16 addendum 81 item 3, 2026-10-17 addendum 112 "
                      "item 4 and addendum 116 item 4) · READ-ONLY, writes nothing")
    assert out[1:4] == HEADER
    assert "ZSPF 2024 · source api_american_football · listing 12 games · stored 9 rows" in out
    assert ("  THE SYNC'S RESOLUTION (each listed game as sync_matches resolves it): onto a stored row 8 (re-keyed 0) "
            "· creates 3 · refuses 0 · skips 1 (a team not stored)") in out
    assert ("  THE RULE CHANGES 2 stored row(s) of ZSPF 2024 (status only, score-presence-apply): no status sent 1 · "
            "the text 'None' 1") in out
    assert ("  NO STATUS SENT, both scores: listed 5 · changes 1 · needs scores 1 · already as the rule reads 1 · left "
            "alone until the age clock (kickoff + 5h) 0 · not stored 2") in out
    assert (f"    match {ids[9101]} · provider 9101 · 2024-09-07 17:00:00Z · Regular Season · no status sent · "
            "SCHEDULED → FINISHED") in out
    # 9107 holds no stored score: the rule reads FINISHED, but a status-only write cannot complete it (P1, #493 review)
    assert NEEDS + f"1 · match ids {ids[9107]}" in out
    assert (f"    match {ids[9107]} · provider 9107 · 2024-09-07 17:00:00Z · Regular Season · no status sent · stored "
            "SCHEDULED → FINISHED · stored scores missing") in out
    assert not [ln for ln in out if ln.startswith(f"    match {ids[9107]}") and ln.endswith("SCHEDULED → FINISHED")]
    assert f"    already: match {ids[9102]} · provider 9102 · 2024-09-07 17:00:00Z · Regular Season · no status " \
           "sent · FINISHED" in out
    assert "    not stored: provider 9103 · 2024-09-07 17:00:00Z · no status sent · the sync creates it FINISHED" in out
    assert "    not stored: provider 9104 · 2024-09-07 17:00:00Z · no status sent · the sync skips it: a team is not " \
           "stored" in out
    # (4): the text "None" in its own section, for the record: the stored FINISHED one does not flip
    assert ("  THE TEXT 'None', both scores (no status, the same as absent: addendum 116 item 4 (4); for the record): "
            "listed 2 · stored as the rule reads, nothing flips 1 · changes 1 · needs scores 0 · left alone until the "
            "age clock (kickoff + 5h) 0 · not stored 0") in out
    assert (f"    match {ids[9105]} · provider 9105 · 2024-09-07 17:00:00Z · Regular Season · stored FINISHED → "
            "FINISHED (unchanged)") in out
    assert (f"    match {ids[9106]} · provider 9106 · 2024-09-07 17:00:00Z · Regular Season · stored SCHEDULED → "
            "FINISHED (a change)") in out
    assert not [ln for ln in out if ln.startswith("  NFL STAGE")]                # ZSPF is not nfl_elo_v1's competition
    # X + Y = N: 9107 is a change but holds no stored scores, so it is not among the 6
    assert "  stored SCHEDULED with both scores: 6 · the rule changes 2 · the rule leaves 4" in out
    assert f"    left: match {ids[9109]} · provider 9109 · 2024-09-07 17:00:00Z · Regular Season · the provider " \
           "states 'NS' (a sync would write SCHEDULED; not the rule's)" in out
    assert f"    left: match {ids[9110]} · provider 9110 · 2024-09-06 17:00:00Z · Regular Season · the provider " \
           "states 'FT' (a sync would write FINISHED; not the rule's)" in out
    assert f"    left: match {ids[9112]} · provider 9112 · 2024-09-07 17:00:00Z · Pre Season · the provider " \
           "states 'XYZ' (a sync would write SCHEDULED; not the rule's)" in out
    assert f"    left: match {ids[None]} · provider — · 2024-09-07 17:00:00Z · Regular Season · not in the listing " \
           "(the rule does not touch it)" in out
    # the APPLY line: 9101 alone; the text "None" change 9106 on its own line (P2, #493 review); 9107 on no apply line
    assert ("  APPLY (status only; on the architect's word, after a fresh .backup): python cli.py score-presence-apply "
            f"--competition ZSPF --season 2024 --match-ids {ids[9101]} --backup <PATH>") in out
    assert TEXT_NONE + str(ids[9106]) in out
    assert not [ln for ln in out if ln.startswith("  HELD")]
    assert "  AGE CLOCK MOVED (listed games of the rule's class counted from later than the kickoff sent, each row says " \
           "so): the NCAA TBD placeholder 0 · a date with no time 0" in out
    assert ("  A WHOLE-SEASON SYNC WOULD ALSO WRITE (information only: it is not the vehicle, addendum 116 item 4 (1); "
            "score-presence-apply writes status alone): status 1 · kickoff 1 · scores 1 (values not printed) · stage, "
            "matchday, season, status code 1 · provider id (re-key) 0 · listed games it creates 2") in out
    assert (f"    status: match {ids[9110]} · provider 9110 · 2024-09-06 17:00:00Z · Regular Season · SCHEDULED → "
            "FINISHED (the provider states 'FT')") in out
    assert f"    kickoff: match {ids[9110]} · provider 9110 · 2024-09-06 17:00:00Z → 2024-09-07 17:00:00Z" in out
    assert f"    scores: match {ids[9107]} · provider 9107 · 2024-09-07 17:00:00Z · Regular Season" in out
    assert (f"    fields: match {ids[9112]} · provider 9112 · 2024-09-07 17:00:00Z · Pre Season · stage Pre Season → "
            "Regular Season · matchday — → 1") in out
    assert "    creates: provider 9108 · 2024-09-07 17:00:00Z · SCHEDULED" in out
    assert "    creates: provider 9111 · 2024-09-07 17:00:00Z · LIVE" in out
    assert "  A WHOLE-SEASON SYNC WOULD WRITE NOTHING FOR: refused 0 · skipped 1 (a team not stored)" in out
    assert "    skipped (a team not stored): provider 9104" in out
    assert "20-17" not in text and "17-20" not in text                           # no score is printed
    tail = json.loads(out[-1].split(" ", 1)[1])
    assert out[-1].startswith("SCORE-PRESENCE-DRY-RUN {")
    assert tail["changes_total"] == 2 and tail["written"] == 0 and tail["unread"] == []
    assert tail["now"] == "2026-10-17 17:15:00Z" and tail["longest_game_h"]["NFL"] == 5
    assert tail["by_competition_season"]["ZSPF 2024"] == {
        "listing": 12, "stored": 9, "changes": 2, "changes_no_status": 1, "changes_none_text": 1,
        "listed_no_status_both_scores": 5, "listed_none_text_both_scores": 2, "already": 1, "none_text_unchanged": 1,
        "left_alone_until_kickoff_age": 0, "not_stored": 2, "sched_both_scores": 6, "sched_both_changed": 2,
        "left": 4, "needs_scores": 1, "needs_scores_ids": [ids[9107]], "apply_ids": [ids[9101]],
        "held_nfl_not_preseason_ids": [], "held_rekeyed_ids": [], "none_text_change_ids": [ids[9106]],
        "clock_moved": {"placeholder": 0, "date only": 0},
        "onto_stored": 8, "rekeyed": 0, "created": 3, "refused": 0, "skipped": 1,
        "also_status": 1, "also_kickoff": 1, "also_scores": 1, "also_fields": 1, "also_created": 2}


def test_the_dry_run_lists_a_game_in_play_as_left_alone_never_finished():
    """(3) on the current season: a stored LIVE row and a stored SCHEDULED row whose listed games carry no status (one
    the text "None") and running totals, an hour after kickoff: listed, left alone, never changed."""
    from src.db.schema import Sport
    from src.ingestion import score_presence as sp
    ko = datetime(2026, 10, 17, 16, 15)
    ids = _world("ZSPI", Sport.NFL, "api_american_football", [(801, L, 7, 3, ko), (802, S, None, None, ko)],
                 key="ZSPI{}".format, season="2026")
    payload = {"response": [_af_game(801, "ZSPI8010", "ZSPI8011", ko, totals=(14, 10)),
                            _af_game(802, "ZSPI8020", "ZSPI8021", ko, totals=(3, 0), short="None")]}
    out = []
    assert sp.run(["ZSPI"], ["2026"], lambda c: _faked(APIAmericanFootballAdapter(), payload), out=out.append,
                  now=NOW) == 0
    assert ("  THE RULE CHANGES 0 stored row(s) of ZSPI 2026 (status only, score-presence-apply): no status sent 0 · "
            "the text 'None' 0") in out
    assert (f"    left alone: match {ids[801]} · provider 801 · 2026-10-17 16:15:00Z · Regular Season · no status sent "
            "· stored LIVE kept (kickoff + 5h = 2026-10-17 21:15:00Z is after now)") in out
    assert (f"    left alone: match {ids[802]} · provider 802 · 2026-10-17 16:15:00Z · Regular Season · stored "
            "SCHEDULED kept (kickoff + 5h = 2026-10-17 21:15:00Z is after now)") in out
    assert "  APPLY: nothing to apply for ZSPI 2026" in out
    assert json.loads(out[-1].split(" ", 1)[1])["by_competition_season"]["ZSPI 2026"][
        "left_alone_until_kickoff_age"] == 2


def _af_game(gid, home, away, when, totals=(20, 17), short=None, stage="Regular Season"):
    """One american-football /games row in the fixtures' shape; no `status` key when `short` is None."""
    game = {"id": gid, "date": {"timestamp": int(when.replace(tzinfo=timezone.utc).timestamp())},
            "stage": stage, "week": "Week 1"}
    if short is not None:
        game["status"] = {"short": short}
    return {"game": game, "league": {"id": 1, "season": "2024"},
            "teams": {"home": {"id": home, "name": f"Home {gid}"}, "away": {"id": away, "name": f"Away {gid}"}},
            "scores": {"home": {"total": totals[0]}, "away": {"total": totals[1]}}}


def test_a_game_the_sync_re_keys_onto_a_stored_row_is_the_rule_s_change_held_off_the_apply_line(fresh):
    """A stored row the next sync re-keys (the same pair within 12 hours, under a new provider id) is resolved as the
    sync resolves it: the rule's change, its kickoff and its re-key are on the receipt, and the sync then does it. A
    status-only write cannot carry the re-key: the change is HELD off the APPLY line and the apply refuses it (#493
    review, P1)."""
    from src.db.database import session_scope
    from src.db.schema import Match, Sport
    from src.ingestion import score_presence as sp
    from src.ingestion.service import IngestionService
    key = "ZSPK{}".format
    ids = _world("NCAA", Sport.NFL, "api_american_football", [(111, S, 20, 17, _af_ko())], key=key)
    before = _statuses(ids)
    payload = {"response": [_af_game(222, "ZSPK1110", "ZSPK1111", datetime(2024, 9, 7, 18))]}
    out = []
    ad = _faked(APIAmericanFootballAdapter(), payload)
    assert sp.run(["NCAA"], ["2024"], lambda c: ad, out=out.append, now=NOW) == 0
    assert _statuses(ids) == before                                              # writes nothing
    assert ("  THE SYNC'S RESOLUTION (each listed game as sync_matches resolves it): onto a stored row 1 (re-keyed 1) "
            "· creates 0 · refuses 0 · skips 0 (a team not stored)") in out
    assert ("  NO STATUS SENT, both scores: listed 1 · changes 1 · needs scores 0 · already as the rule reads 0 · left "
            "alone until the age clock (kickoff + 5h) 0 · not stored 0") in out
    assert (f"    match {ids[111]} · provider 111 → 222 (re-keyed) · 2024-09-07 17:00:00Z · Regular Season · no status "
            "sent · SCHEDULED → FINISHED") in out
    assert "  stored SCHEDULED with both scores: 1 · the rule changes 1 · the rule leaves 0" in out
    assert "  APPLY: nothing to apply for NCAA 2024" in out
    assert f"  HELD ({HELD_REKEY}): match ids {ids[111]}" in out
    rc_out = []
    assert sp.apply("NCAA", "2024", [ids[111]], lambda c: ad, out=rc_out.append, now=NOW) == 1
    assert f"    match {ids[111]}: HELD ({HELD_REKEY}) · provider 111 → 222" in rc_out
    assert _statuses(ids) == before                                              # the apply wrote nothing
    assert not [ln for ln in out if ln.startswith("    left:")]
    assert (f"    kickoff: match {ids[111]} · provider 111 → 222 (re-keyed) · 2024-09-07 17:00:00Z → "
            "2024-09-07 18:00:00Z") in out
    assert f"    re-key: match {ids[111]} · provider 111 → 222 (re-keyed) · 2024-09-07 17:00:00Z · Regular Season" in out
    # the sync, on the same answer, does what the receipt says
    res = IngestionService(ad).sync_matches("NCAA", "2024")
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
    assert sp.run(["ZSPP"], ["2024"], lambda c: ad, out=out.append, now=NOW) == 0
    assert _statuses(ids) == before
    assert ("  THE SYNC'S RESOLUTION (each listed game as sync_matches resolves it): onto a stored row 2 (re-keyed 1) "
            "· creates 0 · refuses 1 · skips 0 (a team not stored)") in out
    assert (f"    match {ids[333]} · provider 333 → 222 (re-keyed) · 2024-09-07 17:00:00Z · Regular Season · no status "
            "sent · SCHEDULED → FINISHED") in out
    assert (f"    kickoff: match {ids[333]} · provider 333 → 222 (re-keyed) · 2024-09-07 17:00:00Z → "
            "2024-09-14 17:00:00Z") in out
    assert (f"    not stored: provider 444 · 2024-09-07 18:00:00Z · no status sent · the sync refuses it, creating "
            f"nothing: stored row {ids[555]} holds its natural key but its id 555 is still in this listing (the "
            f"provider lists both 555 and 444) — not created") in out
    assert "  A WHOLE-SEASON SYNC WOULD WRITE NOTHING FOR: refused 1 · skipped 0 (a team not stored)" in out
    assert (f"    refused: provider 444 · 2024-09-07 18:00:00Z · stored row {ids[555]} holds its natural key but its id "
            f"555 is still in this listing (the provider lists both 555 and 444) — not created") in out
    assert "  stored SCHEDULED with both scores: 2 · the rule changes 1 · the rule leaves 1" in out
    assert f"    left: match {ids[555]} · provider 555 · 2024-09-07 17:00:00Z · Regular Season · the provider " \
           "states 'FT' (a sync would write FINISHED; not the rule's)" in out


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
    r = sp.compare("ZSPX", [nm], {"501": None}, rows, {"501": {"row": rows[1], "rekey": None}})
    assert (r["sched_both"], r["sched_both_changed"], len(r["left"])) == (2, 1, 1)
    assert [x["id"] for x in r["changes"]] == [2]
    assert r["left"][0]["why"] == "its provider id is listed, but the sync resolves that game to match 2 (the rule " \
                                  "does not touch this row)"


def test_the_dry_run_reads_hockey_and_every_stored_season_by_default():
    from src.db.schema import Sport
    from src.ingestion import score_presence as sp
    ko = datetime(2024, 10, 8, 23)
    ids = _world("ZSPH", Sport.NHL, "api_hockey", [(9213, S, 0, 2, ko), (9208, S, 3, 2, ko), (9206, F, 3, 2, ko)])
    calls, out = [], []
    ad = _faked(APIHockeyAdapter(), _payload("hockey_games.json"), calls)
    assert sp.run(["ZSPH"], [], lambda c: ad, out=out.append, now=NOW) == 0
    assert calls == [("games", {"league": 57, "season": 2024})]
    assert f"    match {ids[9213]} · provider 9213 · 2024-10-08 23:00:00Z · Regular Season · no status sent · " \
           "SCHEDULED → FINISHED" in out
    assert f"    left: match {ids[9208]} · provider 9208 · 2024-10-08 23:00:00Z · Regular Season · no status (none " \
           "sent, or the text 'None') and a score missing in the listing: stays SCHEDULED (no score, not FINISHED)" in out
    assert (f"    match {ids[9206]} · provider 9206 · 2024-10-08 23:00:00Z · Regular Season · stored FINISHED → FINISHED "
            "(unchanged)") in out
    assert ("  THE SYNC'S RESOLUTION (each listed game as sync_matches resolves it): onto a stored row 3 (re-keyed 0) "
            "· creates 0 · refuses 0 · skips 11 (a team not stored)") in out
    assert ("  NO STATUS SENT, both scores: listed 6 · changes 1 · needs scores 0 · already as the rule reads 0 · left "
            "alone until the age clock (kickoff + 4h) 0 · not stored 5") in out


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
    out = []
    assert sp.apply("NFL", "2024", [1], lambda c: pytest.fail("no adapter is made"), out=out.append) == 2
    assert out == [f"✗ no database at {gone.resolve()}; the apply never creates one (law 5) · nothing written"]
    import cli
    res = CliRunner().invoke(cli.cli, ["score-presence-apply", "--competition", "NFL", "--season", "2024",
                                       "--match-ids", "1", "--backup", str(tmp_path / "b.db")])
    assert res.exit_code == 2 and "the apply never creates one (law 5) · nothing written" in res.output
    assert "backup verified" not in res.output
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
    assert "longest game (addendum 116 item 4 (3)): SOCCER 3h · NHL 4h · NFL 5h · NCAA 5h · MLB 6h · now " \
        in res.output
    assert '"written": 0' in res.output
    res = CliRunner().invoke(cli.cli, ["score-presence-dry-run", "--competition", "MLB"])
    assert res.exit_code == 2                                                    # only the three competitions


# --- (1) + (2): the status-only apply, on a fresh DB of its own (competitions coded NFL and NCAA) ---

@pytest.fixture
def fresh(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db
    path = tmp_path / "sp.db"
    eng = create_engine(f"sqlite:///{path}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                         expire_on_commit=False))
    db.init_db()
    return path


def _dump(path):
    """Every row of every table in the file, read with sqlite3 (no ORM): {table: [row, ...]} ordered by rowid."""
    con = sqlite3.connect(str(path))
    try:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
        cols = {t: [r[1] for r in con.execute(f"PRAGMA table_info({t})")] for t in tables}
        return cols, {t: con.execute(f"SELECT * FROM {t} ORDER BY rowid").fetchall() for t in tables}
    finally:
        con.close()


def _only_status_changed(before, after, ids, old="SCHEDULED", new="FINISHED"):
    """Every column of every row of every table is as it was, except matches.status on `ids` (`old` -> `new`)."""
    (cols, b), (_, a) = before, after
    assert set(a) == set(b)
    for t in b:
        assert len(a[t]) == len(b[t]), t                                         # no row created or deleted
        if t != "matches":
            assert a[t] == b[t], t
    i_id, i_st = cols["matches"].index("id"), cols["matches"].index("status")
    for rb, ra in zip(b["matches"], a["matches"]):
        assert rb[i_id] == ra[i_id]
        for i, c in enumerate(cols["matches"]):
            if c == "status" and rb[i_id] in ids:
                assert (rb[i], ra[i]) == (old, new), rb[i_id]
            else:
                assert rb[i] == ra[i], (rb[i_id], c)
    return True


def _nfl_world():
    """NFL (nfl_elo_v1's competition) 2024: stored rows and the listing's games for them."""
    from src.db.schema import Sport
    return _world("NFL", Sport.NFL, "api_american_football", [
        (501, S, 20, 17, _af_ko(), {"stage": "Pre Season"}),     # no status sent: a change, preseason (applied)
        (502, S, 20, 17, _af_ko()),                              # no status sent: a change, regular season (held)
        (503, F, 20, 17, _af_ko()),                              # the text "None", stored FINISHED: stays FINISHED
        (504, S, 20, 17, _af_ko()),                              # the text "None", stored SCHEDULED: a change, held
        (505, S, 20, 17, _af_ko()),                              # FT: not the rule's
    ], key="N{}".format)


NFL_PAYLOAD = {"response": [_af_game(501, "N5010", "N5011", _af_ko(), stage="Pre Season"),
                            _af_game(502, "N5020", "N5021", _af_ko()),
                            _af_game(503, "N5030", "N5031", _af_ko(), short="None"),
                            _af_game(504, "N5040", "N5041", _af_ko(), short="None"),
                            _af_game(505, "N5050", "N5051", _af_ko(), short="FT")]}


def test_the_dry_run_names_each_nfl_change_s_stage_class(fresh):
    """Addendum 116 item 4 (2): each NFL change carries nfl_elo_v1's own preseason test on its stored stage; the
    summary counts each class; the apply line names the preseason ids only, the held ones are listed for their Issue.
    The held class is every row the walk reads, regular season AND postseason: labelled "not preseason" (#493 review)."""
    from src.ingestion import score_presence as sp
    assert [sp.nfl_class("NFL", st) for st in ("Pre Season", "Regular Season", "Post Season", None)] == \
        [PRE, HELD, HELD, HELD]
    assert sp.nfl_class("NCAA", "Post Season") is None
    ids = _nfl_world()
    out = []
    assert sp.run(["NFL"], ["2024"], lambda c: _faked(APIAmericanFootballAdapter(), NFL_PAYLOAD), out=out.append,
                  now=NOW) == 0
    assert ("  THE RULE CHANGES 3 stored row(s) of NFL 2024 (status only, score-presence-apply): no status sent 2 · "
            "the text 'None' 1") in out
    assert (f"    match {ids[501]} · provider 501 · 2024-09-07 17:00:00Z · Pre Season · no status sent · SCHEDULED → "
            f"FINISHED · {PRE}") in out
    assert (f"    match {ids[502]} · provider 502 · 2024-09-07 17:00:00Z · Regular Season · no status sent · SCHEDULED "
            f"→ FINISHED · {HELD}") in out
    assert (f"    match {ids[503]} · provider 503 · 2024-09-07 17:00:00Z · Regular Season · stored FINISHED → FINISHED "
            "(unchanged)") in out
    assert (f"    match {ids[504]} · provider 504 · 2024-09-07 17:00:00Z · Regular Season · stored SCHEDULED → FINISHED "
            f"(a change · {HELD})") in out
    assert ("  NFL STAGE (nfl_elo_v1's preseason test, nfl_predict.is_preseason, on the stored stage; the apply writes no "
            f"stage): of the rule's 3 change(s), {PRE} 1 · {HELD} 2") in out
    assert "  stored SCHEDULED with both scores: 4 · the rule changes 3 · the rule leaves 1" in out
    assert ("  APPLY (status only; on the architect's word, after a fresh .backup): python cli.py score-presence-apply "
            f"--competition NFL --season 2024 --match-ids {ids[501]} --backup <PATH>") in out
    assert f"  HELD ({HELD_NFL}): match ids {ids[502]},{ids[504]}" in out
    assert not [ln for ln in out if ln.startswith("  THE TEXT 'None' CHANGES")]  # 504 is held, never "on the word"
    tail = json.loads(out[-1].split(" ", 1)[1])["by_competition_season"]["NFL 2024"]
    assert (tail["apply_ids"], tail["held_nfl_not_preseason_ids"], tail["none_text_change_ids"]) == \
        ([ids[501]], [ids[502], ids[504]], [])


def test_the_apply_refuses_as_a_whole_and_writes_only_status_on_what_it_accepts(fresh):
    from src.ingestion import score_presence as sp
    ids = _nfl_world()
    ad = _faked(APIAmericanFootballAdapter(), NFL_PAYLOAD)

    def apply(*named):
        out = []
        return sp.apply("NFL", "2024", list(named), lambda c: ad, out=out.append, now=NOW), out
    before = _dump(fresh)
    # an NFL regular-season id beside an accepted one: refused as a whole, nothing written
    rc, out = apply(ids[501], ids[502], ids[504])
    assert rc == 1 and _dump(fresh) == before
    assert out[0] == ("SCORE-PRESENCE APPLY (#493; ARCHITECT 2026-10-16 addendum 81 item 3, 2026-10-17 addendum 112 "
                      "item 4 and addendum 116 item 4) · writes Match.status ONLY, on named rows of the rule's change "
                      "set; refuses as a whole")
    assert out[1:4] == HEADER
    assert out[4] == (f"NFL 2024 · source api_american_football · listing 5 games · stored 5 rows · the rule's change set "
                      f"3 · named 3: {ids[501]},{ids[502]},{ids[504]}")
    assert out[5] == "  REFUSED as a whole · nothing written · 2 of 3 named id(s) refused:"
    assert out[6] == f"    match {ids[502]}: HELD ({HELD_NFL}) · stored stage 'Regular Season'"
    assert json.loads(out[-1].split(" ", 1)[1])["applied"] == 0
    # ids not in the change set: refused as a whole, each reason named
    rc, out = apply(ids[501], ids[503], ids[505], 999999)
    assert rc == 1 and _dump(fresh) == before
    assert f"    match {ids[503]}: not in the rule's change set for NFL 2024: already FINISHED as the rule reads " \
           "(text 'None')" in out
    assert f"    match {ids[505]}: not in the rule's change set for NFL 2024: not the rule's: the provider states " \
           "'FT'" in out
    assert "    match 999999: not in the rule's change set for NFL 2024: not a stored row of NFL 2024" in out
    # the preseason id alone: applied, status only
    rc, out = apply(ids[501])
    assert rc == 0, out
    assert _only_status_changed(before, _dump(fresh), {ids[501]})
    assert out[5:8] == [
        "  APPLIED · Match.status only · 1 row(s):",
        f"    match {ids[501]} · provider 501 · 2024-09-07 17:00:00Z · Pre Season · no status sent · SCHEDULED → "
        f"FINISHED · {PRE}",
        "  count 1 · written: status only (no kickoff, score, stage, season, status code or provider id; no row created "
        "or deleted)"]
    tail = json.loads(out[-1].split(" ", 1)[1])
    assert (tail["applied"], tail["ids"], tail["written_columns"], tail["fingerprints"]) == \
        (1, [ids[501]], ["status"], {})
    # again: it is no longer in the change set (already as the rule reads)
    rc, out = apply(ids[501])
    assert rc == 1 and f"    match {ids[501]}: not in the rule's change set for NFL 2024: already FINISHED as the " \
                       "rule reads (no status sent)" in out


def test_the_apply_refuses_a_row_left_alone_by_the_kickoff_age_condition(fresh):
    """A stored LIVE row whose scores are the listing's (the sync writes scores as it always has): refused before
    kickoff + 4h, applied at it."""
    from src.db.schema import Sport
    from src.ingestion import score_presence as sp
    ko = datetime(2026, 10, 17, 16, 15)
    ids = _world("NHL", Sport.NHL, "api_hockey", [(901, L, 2, 1, ko)], key="H{}".format, season="2026")
    payload = {"response": [{"id": 901, "date": ko.replace(tzinfo=timezone.utc).isoformat(),
                             "teams": {"home": {"id": "H9010"}, "away": {"id": "H9011"}},
                             "scores": {"home": 2, "away": 1}}]}
    before = _dump(fresh)
    out = []
    assert sp.apply("NHL", "2026", [ids[901]], lambda c: _faked(APIHockeyAdapter(), payload), out=out.append,
                    now=NOW) == 1
    assert _dump(fresh) == before
    assert (f"    match {ids[901]}: not in the rule's change set for NHL 2026: the rule leaves it alone (no status sent, "
            "both scores, but kickoff + 4h = 2026-10-17 20:15:00Z is after now)") in out
    out = []
    assert sp.apply("NHL", "2026", [ids[901]], lambda c: _faked(APIHockeyAdapter(), payload), out=out.append,
                    now=ko + timedelta(hours=4)) == 0
    assert _only_status_changed(before, _dump(fresh), {ids[901]}, old="LIVE")
    assert f"    match {ids[901]} · provider 901 · 2026-10-17 16:15:00Z · Regular Season · no status sent · LIVE → " \
           "FINISHED" in out


AT = datetime(2026, 10, 16, 12)


def _ncaa_world():
    """NCAA 2024 and 2025 (eight games each) and 2026 (four), each carrying a current CFBD label (the ncaa-elo-v2 stream
    walks them to the last 2026 game); in 2024 games 0-3 are stored SCHEDULED with both scores (addendum 81's 120), the
    rest FINISHED."""
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, NCAACFBDIngestRecord, NCAACFBDLabel, Sport, Team
    src = "api_american_football"
    ids = {}
    with session_scope() as s:
        comp = Competition(sport=Sport.NFL, code="NCAA", name="NCAA", area="USA", type="LEAGUE")
        t = [Team(sport=Sport.NFL, name=f"College {n}", external_ids={src: f"C{n}"}) for n in range(6)]
        s.add_all([comp, *t])
        s.flush()
        for season, start, n in (("2024", datetime(2024, 9, 1, 17), 8), ("2025", datetime(2025, 9, 1, 17), 8),
                                 ("2026", datetime(2026, 9, 5, 17), 4)):
            for i in range(n):
                gid = int(season) * 100 + i
                m = Match(sport=Sport.NFL, competition_id=comp.id, season=season, utc_date=start + timedelta(days=i),
                          status=S if (season == "2024" and i < 4) else F, home_team_id=t[i % 6].id,
                          away_team_id=t[(i + 1) % 6].id, stage="FBS (Division I-A)", home_score=21 + i % 3,
                          away_score=14, external_ids={src: str(gid)})
                s.add(m)
                s.flush()
                s.add(NCAACFBDLabel(match_id=m.id, source="cfbd", source_game_id=gid, season=season,
                                    orientation="same", neutral=False, home_score=21 + i % 3, away_score=14,
                                    fetched_at=AT, season_type="regular"))
                ids[gid] = m.id
        for season in ("2024", "2025", "2026"):
            s.add(NCAACFBDIngestRecord(season=season, division="fbs", fetched_at=AT, payload_file="p.json",
                                       records=8, in_scope=8, joined=8, unlabelled=[]))
    payload = {"response": [_af_game(202400 + i, f"C{i % 6}", f"C{(i + 1) % 6}", datetime(2024, 9, 1 + i, 17),
                                     totals=(21 + i % 3, 14), short=None if i < 6 else "FT", stage="FBS (Division I-A)")
                            for i in range(8)]}
    return ids, payload


def test_the_ncaa_apply_writes_only_status_and_prints_the_fingerprints_unchanged(fresh):
    """Addendum 116 item 4 (1): "The fingerprint is untouched by construction; the PR proves it with the fingerprint
    printed before and after on the test DB." ncaa-elo-v2's stream and training fingerprints, by its own functions,
    before and after the apply: SAME; and no column but matches.status moved, on no row but the accepted ones."""
    from src.ingestion import score_presence as sp
    from src.walters import ncaa_v1r_gate as vg
    ids, payload = _ncaa_world()
    fp0 = sp.ncaa_fingerprints()
    assert fp0["stream"][1] == 20 and fp0["training"][1] == 16                  # a real stream: 2024-2026 walked
    v, second = vg.load_streams(vg.V2)                                           # the very functions --preflight uses
    assert fp0["stream"] == vg.stream_fingerprint(v.games, vg.V2, second.games)
    assert fp0["training"] == vg.training_fingerprint(v.games, vg.V2)
    before = _dump(fresh)
    dry = []
    assert sp.run(["NCAA"], ["2024"], lambda c: _faked(APIAmericanFootballAdapter(), payload), out=dry.append,
                  now=NOW) == 0
    changes = [ids[202400 + i] for i in range(4)]                                # 4, 5: FINISHED already; 6, 7: FT
    assert json.loads(dry[-1].split(" ", 1)[1])["by_competition_season"]["NCAA 2024"]["apply_ids"] == changes
    out = []
    rc = sp.apply("NCAA", "2024", changes, lambda c: _faked(APIAmericanFootballAdapter(), payload), out=out.append,
                  now=NOW)
    assert rc == 0, out
    assert _only_status_changed(before, _dump(fresh), set(changes))
    stream, training = fp0["stream"][0], fp0["training"][0]
    assert f"  ncaa-elo-v2 stream fingerprint (both streams): before {stream} (20 games) · after {stream} (20 games) · " \
           "SAME" in out
    assert f"  ncaa-elo-v2 training fingerprint: before {training} (16 games) · after {training} (16 games) · SAME" in out
    assert sp.ncaa_fingerprints() == fp0
    tail = json.loads(out[-1].split(" ", 1)[1])
    assert tail["fingerprints_same"] is True and tail["applied"] == 4
    assert tail["fingerprints"]["before"] == tail["fingerprints"]["after"] == \
        {"stream": [stream, 20], "training": [training, 16]}


def test_a_status_that_moved_since_the_read_rolls_the_whole_write_back(fresh, monkeypatch):
    from src.db.database import session_scope
    from src.db.schema import Match
    from src.ingestion import score_presence as sp
    ids, payload = _ncaa_world()
    changes = [ids[202400 + i] for i in range(4)]
    real = sp.write_status

    def moved(rows):                                    # another writer finishes the third row between read and write
        with session_scope() as s:
            s.get(Match, changes[2]).status = F
        return real(rows)
    monkeypatch.setattr(sp, "write_status", moved)
    out = []
    assert sp.apply("NCAA", "2024", changes, lambda c: _faked(APIAmericanFootballAdapter(), payload), out=out.append,
                    now=NOW) == 1
    assert f"  REFUSED as a whole · nothing written (rolled back): match {changes[2]}: its stored status is no longer " \
           "SCHEDULED (it moved since the read)" in out
    with session_scope() as s:
        assert [s.get(Match, i).status for i in changes] == [S, S, F, S]       # the first two were rolled back


def test_the_apply_cli_verifies_the_backup_then_applies(fresh, tmp_path, monkeypatch):
    import cli
    ids = _nfl_world()
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda c: _faked(APIAmericanFootballAdapter(), NFL_PAYLOAD))
    res = CliRunner().invoke(cli.cli, ["score-presence-apply", "--competition", "nfl", "--season", "2024",
                                       "--match-ids", str(ids[501])])
    assert res.exit_code == 2 and "REFUSED [check: --backup given]" in res.output       # no backup: nothing read
    bk = tmp_path / "before.backup"
    src_con, dst = sqlite3.connect(str(fresh)), sqlite3.connect(str(bk))
    src_con.backup(dst)
    src_con.close()
    dst.close()
    before = _dump(fresh)
    res = CliRunner().invoke(cli.cli, ["score-presence-apply", "--competition", "nfl", "--season", "2024",
                                       "--match-ids", f"{ids[501]},{ids[502]}", "--backup", str(bk)])
    assert res.exit_code == 1 and "REFUSED as a whole · nothing written" in res.output and _dump(fresh) == before
    res = CliRunner().invoke(cli.cli, ["score-presence-apply", "--competition", "nfl", "--season", "2024",
                                       "--match-ids", str(ids[501]), "--backup", str(bk)])
    assert res.exit_code == 0, res.output
    assert res.output.startswith(f"backup verified: {bk.resolve()}")
    assert "  APPLIED · Match.status only · 1 row(s):" in res.output
    assert _only_status_changed(before, _dump(fresh), {ids[501]})


# --- #493 review: what a status-only write cannot complete, re-keys, the text "None" and the age clock ---

def _hockey_game(gid, ko, totals, status=_NO_KEY, key="H{}".format):
    row = {"id": gid, "date": ko.replace(tzinfo=timezone.utc).isoformat(),
           "teams": {"home": {"id": f"{key(gid)}0"}, "away": {"id": f"{key(gid)}1"}},
           "scores": {"home": totals[0], "away": totals[1]}}
    if status is not _NO_KEY:
        row["status"] = status
    return row


def _nhl_world():
    """NHL 2026: four stored rows whose listed games carry no status (one the text "None") and both totals, long past
    kickoff + 4h."""
    from src.db.schema import Sport
    ko = datetime(2026, 10, 8, 23)
    ids = _world("NHL", Sport.NHL, "api_hockey", [
        (911, S, None, None, ko),     # stored with no score, listed 3-2: NEEDS SCORES (missing)
        (912, L, 1, 0, ko),           # stored LIVE at a running 1-0, listed final 2-1: NEEDS SCORES (they differ)
        (913, S, 2, 1, ko),           # stored the listing's 2-1: a change, on the APPLY line
        (914, S, 4, 1, ko),           # the text "None", stored the listing's 4-1: a change, on its own line
    ], key="H{}".format, season="2026")
    payload = {"response": [_hockey_game(911, ko, (3, 2)), _hockey_game(912, ko, (2, 1)),
                            _hockey_game(913, ko, (2, 1)), _hockey_game(914, ko, (4, 1), {"short": "None"})]}
    return ids, payload


def test_a_row_whose_stored_scores_are_missing_or_differ_needs_scores_and_the_apply_refuses_it(fresh):
    """#493 review (P1): a status-only write never puts FINISHED on a row whose stored scores are missing (a FINISHED
    row with no score) or differ from the listing's totals (an in-play score read as the final). Such a row is NEEDS
    SCORES: listed with its id (never a score), off the APPLY and HELD lines, counted, and refused by the apply."""
    from src.ingestion import score_presence as sp
    ids, payload = _nhl_world()
    ad = lambda c: _faked(APIHockeyAdapter(), payload)                          # noqa: E731
    # the apply refuses each, as a whole, and writes nothing (before the fix: FINISHED with no score / a stale score)
    before = _dump(fresh)
    for named in ([ids[911]], [ids[912], ids[913]]):
        res = []
        assert sp.apply("NHL", "2026", named, ad, out=res.append, now=NOW) == 1
        assert _dump(fresh) == before
    res = []
    assert sp.apply("NHL", "2026", [ids[911], ids[912]], ad, out=res.append, now=NOW) == 1
    assert (f"    match {ids[911]}: NEEDS SCORES (held): the rule reads FINISHED, but the stored scores are missing: a "
            "status-only write cannot complete the row (addendum 116 item 4 (1): never scores; addendum 112 item 4: no "
            "score, not FINISHED); held for the architect") in res
    assert (f"    match {ids[912]}: NEEDS SCORES (held): the rule reads FINISHED, but the stored scores are different from "
            "the listing's totals: a status-only write cannot complete the row (addendum 116 item 4 (1): never scores; "
            "addendum 112 item 4: no score, not FINISHED); held for the architect") in res
    assert _dump(fresh) == before
    # the dry run: listed with ids, off the APPLY and HELD lines, counted
    out = []
    assert sp.run(["NHL"], ["2026"], ad, out=out.append, now=NOW) == 0
    text = "\n".join(out)
    assert NEEDS + f"2 · match ids {ids[911]},{ids[912]}" in out
    assert (f"    match {ids[911]} · provider 911 · 2026-10-08 23:00:00Z · Regular Season · no status sent · stored "
            "SCHEDULED → FINISHED · stored scores missing") in out
    assert (f"    match {ids[912]} · provider 912 · 2026-10-08 23:00:00Z · Regular Season · no status sent · stored LIVE "
            "→ FINISHED · stored scores different from the listing's totals") in out
    assert ("  THE RULE CHANGES 2 stored row(s) of NHL 2026 (status only, score-presence-apply): no status sent 1 · the "
            "text 'None' 1") in out
    assert ("  NO STATUS SENT, both scores: listed 3 · changes 1 · needs scores 2 · already as the rule reads 0 · left "
            "alone until the age clock (kickoff + 4h) 0 · not stored 0") in out
    apply_line = [ln for ln in out if ln.startswith("  APPLY")]
    assert apply_line == ["  APPLY (status only; on the architect's word, after a fresh .backup): python cli.py "
                          f"score-presence-apply --competition NHL --season 2026 --match-ids {ids[913]} --backup <PATH>"]
    assert not [ln for ln in out if ln.startswith("  HELD")]
    assert [ln for ln in out if ln.startswith("  THE TEXT 'None' CHANGES")] == [TEXT_NONE + str(ids[914])]
    assert "3-2" not in text and "1-0" not in text and "(3, 2)" not in text           # no score is printed
    tail = json.loads(out[-1].split(" ", 1)[1])["by_competition_season"]["NHL 2026"]
    assert (tail["needs_scores"], tail["needs_scores_ids"], tail["apply_ids"], tail["changes"]) == \
        (2, [ids[911], ids[912]], [ids[913]], 2)
    # the one row a status-only write completes
    assert sp.apply("NHL", "2026", [ids[913]], ad, out=[].append, now=NOW) == 0
    assert _only_status_changed(before, _dump(fresh), {ids[913]})


def test_a_text_none_change_is_off_the_apply_line_and_applied_only_when_named(fresh):
    """#493 review (P2): addendum 116 item 4 (4) expects no text "None" change; one the receipt shows is on its own line,
    never on the APPLY line, and counted. The architect's word is carried out by naming it: the apply accepts it."""
    from src.ingestion import score_presence as sp
    ids, payload = _nhl_world()
    ad = lambda c: _faked(APIHockeyAdapter(), payload)                          # noqa: E731
    out = []
    assert sp.run(["NHL"], ["2026"], ad, out=out.append, now=NOW) == 0
    assert TEXT_NONE + str(ids[914]) in out
    assert (f"    match {ids[914]} · provider 914 · 2026-10-08 23:00:00Z · Regular Season · stored SCHEDULED → FINISHED (a "
            "change)") in out
    assert [ln for ln in out if ln.startswith("  APPLY")][0].endswith(f"--match-ids {ids[913]} --backup <PATH>")
    tail = json.loads(out[-1].split(" ", 1)[1])["by_competition_season"]["NHL 2026"]
    assert (tail["none_text_change_ids"], tail["changes_none_text"]) == ([ids[914]], 1)
    before = _dump(fresh)
    res = []
    assert sp.apply("NHL", "2026", [ids[914]], ad, out=res.append, now=NOW) == 0, res
    assert f"    match {ids[914]} · provider 914 · 2026-10-08 23:00:00Z · Regular Season · text 'None' · SCHEDULED → " \
           "FINISHED" in res
    assert _only_status_changed(before, _dump(fresh), {ids[914]})


def _rows_ncaa():
    from src.db.database import session_scope
    from src.db.schema import Competition, Match
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == "NCAA")).scalar_one()
        return sorted((m.id, m.status, m.utc_date, m.external_ids.get("api_american_football"))
                      for m in s.execute(select(Match).where(Match.competition_id == comp.id)).scalars())


def test_a_placeholder_re_key_is_held_and_the_apply_cannot_make_a_twin(fresh):
    """#493 review (P1): a stored SCHEDULED NCAA row at the provider's TBD placeholder (04:00Z), listed under a new id at
    a real kickoff 16h later (outside 12 hours: only the placeholder window finds it). Before the fix the dry run put it
    on the APPLY line, the apply wrote FINISHED, and the next sync (the placeholder window reads SCHEDULED rows only)
    created a twin. Now it is HELD, the apply refuses it, and the sync re-keys the row in place."""
    from src.db.schema import Sport
    from src.ingestion import score_presence as sp
    from src.ingestion.service import IngestionService
    placeholder, real = datetime(2024, 9, 7, 4), datetime(2024, 9, 7, 20)
    ids = _world("NCAA", Sport.NFL, "api_american_football", [(7001, S, 21, 14, placeholder)], key="P{}".format)
    payload = {"response": [_af_game(7999, "P70010", "P70011", real, totals=(21, 14))]}
    ad = _faked(APIAmericanFootballAdapter(), payload)
    out = []
    assert sp.run(["NCAA"], ["2024"], lambda c: ad, out=out.append, now=NOW) == 0
    before = _dump(fresh)
    res = []
    assert sp.apply("NCAA", "2024", [ids[7001]], lambda c: ad, out=res.append, now=NOW) == 1
    assert f"    match {ids[7001]}: HELD ({HELD_REKEY}) · provider 7001 → 7999" in res
    assert _dump(fresh) == before                                                # nothing written
    assert (f"    match {ids[7001]} · provider 7001 → 7999 (re-keyed) · 2024-09-07 04:00:00Z · Regular Season · no status "
            "sent · SCHEDULED → FINISHED") in out
    assert "  APPLY: nothing to apply for NCAA 2024" in out
    assert f"  HELD ({HELD_REKEY}): match ids {ids[7001]}" in out
    assert json.loads(out[-1].split(" ", 1)[1])["by_competition_season"]["NCAA 2024"]["held_rekeyed_ids"] == [ids[7001]]
    # the next sync: the row re-keyed in place, no twin
    r = IngestionService(ad).sync_matches("NCAA", "2024")
    assert (r.created, r.rekeyed) == (0, 1)
    assert _rows_ncaa() == [(ids[7001], F, real, "7999")]


def test_the_age_clock_helper_moves_for_the_tbd_placeholder_and_a_date_with_no_time():
    from src.ingestion.placeholder import PLACEHOLDER_RESOLVE_H, is_placeholder_kickoff
    ph = datetime(2026, 10, 24, 4)
    assert is_placeholder_kickoff(ph) and PLACEHOLDER_RESOLVE_H == 24
    assert ass.age_start(ph, "NCAA") == (ph + timedelta(hours=24), ass.CLOCK_PLACEHOLDER)
    assert ass.age_until(ph, "NCAA") == datetime(2026, 10, 25, 9)                # the end of its game day + 5h
    assert ass.age_start(ph, "NFL") == (ph, None)                                # NFL: no placeholder receipt
    assert ass.age_until(ph, "NFL") == datetime(2026, 10, 24, 9)
    day = datetime(2026, 10, 18)
    assert ass.age_start(day, "NFL", date_only=True) == (datetime(2026, 10, 19), ass.CLOCK_DATE_ONLY)
    assert ass.age_until(day, "NHL", date_only=True) == datetime(2026, 10, 19, 4)
    assert ass.age_until(datetime(2026, 10, 18, 17), "NFL") == datetime(2026, 10, 18, 22)
    assert ass.age_start(None, "NCAA") == (None, None) and ass.age_until(None, "NCAA") is None
    assert [ass.is_date_only(x) for x in ("2026-10-18", "2026-10-18T17:00:00+00:00", "2026-10-18 17:00", "")] == \
        [True, False, False, False]


def test_an_ncaa_game_at_the_tbd_placeholder_in_play_never_reads_finished(fresh, monkeypatch):
    """#493 review (P2): an NCAA game listed at the provider's TBD placeholder (04:00Z) with no status and running
    totals at 20:20Z on game day: before the fix 20:20 >= 04:00 + 5h read FINISHED mid-game. The age clock counts from
    the end of that game day (placeholder + 24h) before the 5h: None (the stored status left alone) until then."""
    from src.db.schema import Sport
    from src.ingestion.service import IngestionService
    ph = datetime(2026, 10, 24, 4)
    in_play = datetime(2026, 10, 24, 20, 20)
    edge = ph + timedelta(hours=24 + 5)
    assert _parse_one("NCAA", ph, _NO_KEY, totals=(14, 7), now=in_play).status is None
    assert _parse_one("NCAA", ph, "None", totals=(14, 7), now=edge - timedelta(seconds=1)).status is None
    assert _parse_one("NCAA", ph, _NO_KEY, totals=(14, 7), now=edge).status == F
    assert _parse_one("NFL", ph, _NO_KEY, now=ph + timedelta(hours=5)).status == F    # NFL: kickoff + 5h, as ruled
    # through the sync: a stored LIVE and a stored SCHEDULED row at the placeholder keep their status in play
    _team_world("NCAA", Sport.NFL, "api_american_football", [(6101, L, ph, None), (6102, S, ph, None)])
    payload = {"response": [{"game": {"id": gid, "date": {"timestamp": int(ph.replace(tzinfo=timezone.utc).timestamp())}},
                             "teams": {"home": {"id": f"NCAA{gid}0"}, "away": {"id": f"NCAA{gid}1"}},
                             "scores": {"home": {"total": 14}, "away": {"total": 7}}} for gid in (6101, 6102)]}
    clock = [in_play]
    monkeypatch.setattr(ass, "utc_now_naive", lambda: clock[0])
    IngestionService(_faked(APIAmericanFootballAdapter(), payload)).sync_matches("NCAA", "2026")
    assert {k: v[0] for k, v in _rows_of("NCAA").items()} == {"6101": L, "6102": S}
    clock[0] = edge
    IngestionService(_faked(APIAmericanFootballAdapter(), payload)).sync_matches("NCAA", "2026")
    assert {k: v[0] for k, v in _rows_of("NCAA").items()} == {"6101": F, "6102": F}


@pytest.mark.parametrize("block", [{"date": "2026-10-18", "time": "17:00"}, {"date": "2026-10-18"}, "2026-10-18"])
def test_a_kickoff_sent_as_a_date_with_no_time_counts_from_the_end_of_that_date(block):
    """#493 review (P2): with no timestamp the american-football parse reads the date alone (the time is dropped), so
    the kickoff parses as midnight UTC. Before the fix a 17:00Z game in play at 17:50Z read FINISHED (00:00 + 5h). The
    kickoff time is unknown: the age clock counts from the end of that UTC date. The stored kickoff is unchanged."""
    def one(now, code="NFL"):
        row = {"game": {"id": 1, "date": block}, "teams": {"home": {"id": 10}, "away": {"id": 11}},
               "scores": {"home": {"total": 14}, "away": {"total": 7}}}
        return APIAmericanFootballAdapter()._parse_games({"response": [row]}, code, "2026", now=now)[0]
    got = one(datetime(2026, 10, 18, 17, 50))
    assert got.status is None and got.utc_date == datetime(2026, 10, 18)        # in play: not FINISHED
    assert got.kickoff_date_only is True
    assert one(datetime(2026, 10, 19, 5) - timedelta(seconds=1)).status is None
    assert one(datetime(2026, 10, 19, 5)).status == F
    assert one(datetime(2026, 10, 19, 5), "NCAA").status == F                    # midnight is no TBD placeholder
    # the hockey parse reads the same fallback: a date with no time, NHL's 4h from the end of the date
    if isinstance(block, str):
        row = {"id": 1, "date": block, "teams": {"home": {"id": 10}, "away": {"id": 11}},
               "scores": {"home": 2, "away": 1}}
        hk = APIHockeyAdapter()._parse_games({"response": [row]}, "2026", now=datetime(2026, 10, 18, 23, 50))[0]
        assert (hk.status, hk.kickoff_date_only) == (None, True)
        assert APIHockeyAdapter()._parse_games({"response": [row]}, "2026",
                                               now=datetime(2026, 10, 19, 4))[0].status == F
    # a timestamp: the kickoff is known, nothing moves
    assert _parse_one("NFL", datetime(2026, 10, 18, 17), _NO_KEY, now=datetime(2026, 10, 18, 22)).kickoff_date_only \
        is False


def test_the_receipt_says_when_a_row_s_age_clock_moved(fresh):
    """#493 review (P2): the receipt reads the rule's own helper (age_until), so it says what the parse did: a row whose
    clock starts at the end of the TBD placeholder's game day, or the end of a date sent with no time, says so."""
    from src.db.schema import Sport
    from src.ingestion import score_presence as sp
    ph, day = datetime(2026, 10, 24, 4), datetime(2026, 10, 24)
    ids = _world("NCAA", Sport.NFL, "api_american_football", [(6201, S, 14, 7, ph), (6202, S, 21, 3, day)],
                 key="Q{}".format, season="2026")
    dated = _af_game(6202, "Q62020", "Q62021", day, totals=(21, 3))
    dated["game"]["date"] = {"date": "2026-10-24", "time": "19:30"}             # no timestamp
    payload = {"response": [_af_game(6201, "Q62010", "Q62011", ph, totals=(14, 7)), dated]}

    def dry(now):
        out = []
        assert sp.run(["NCAA"], ["2026"], lambda c: _faked(APIAmericanFootballAdapter(), payload), out=out.append,
                      now=now) == 0
        return out
    out = dry(datetime(2026, 10, 24, 20, 20))
    assert (f"    left alone: match {ids[6201]} · provider 6201 · 2026-10-24 04:00:00Z · Regular Season · no status sent · "
            "stored SCHEDULED kept (kickoff + 24h (the end of the TBD placeholder's game day) + 5h = 2026-10-25 "
            "09:00:00Z is after now)") in out
    assert (f"    left alone: match {ids[6202]} · provider 6202 · 2026-10-24 00:00:00Z · Regular Season · no status sent · "
            "stored SCHEDULED kept (the end of the kickoff's UTC date (no kickoff time sent) + 5h = 2026-10-25 "
            "05:00:00Z is after now)") in out
    assert "  AGE CLOCK MOVED (listed games of the rule's class counted from later than the kickoff sent, each row says " \
           "so): the NCAA TBD placeholder 1 · a date with no time 1" in out
    assert "  APPLY: nothing to apply for NCAA 2026" in out
    out = dry(datetime(2026, 10, 25, 9))
    assert (f"    match {ids[6201]} · provider 6201 · 2026-10-24 04:00:00Z · Regular Season · no status sent · SCHEDULED "
            "→ FINISHED · age clock from kickoff + 24h (the end of the TBD placeholder's game day)") in out
    assert (f"    match {ids[6202]} · provider 6202 · 2026-10-24 00:00:00Z · Regular Season · no status sent · SCHEDULED "
            "→ FINISHED · age clock from the end of the kickoff's UTC date (no kickoff time sent)") in out
    assert json.loads(out[-1].split(" ", 1)[1])["by_competition_season"]["NCAA 2026"]["clock_moved"] == \
        {"placeholder": 1, "date only": 1}
