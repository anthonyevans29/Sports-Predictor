"""#493 (ARCHITECT 2026-10-16, addendum 81 item 3; 2026-10-17, addendum 112 item 4), verbatim: "the rule fires where it
was meant to — a row whose provider status is ABSENT (None at the source) and whose two scores are present is FINISHED;
a row whose provider status is anything else keeps it (law 4: a status the provider stated is never overridden by
scores)." and "make the check run on the provider's raw status before the NS default is applied; the rule stays
"conservative unknowns": no score → not FINISHED. Tests with the raw payloads from tests/fixtures."

The rows are tests/fixtures/api_sports_status (provider-shaped, written: no kept answer exists for these adapters; its
README says so). The provider is faked (no network); the DB is the throwaway one (tests/conftest.py)."""
import json
from datetime import datetime
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


def _world(code, sport, source, rows):
    """A competition with stored 2024 rows: (provider id or None, status, home score, away score, kickoff)."""
    from src.db.database import init_db, session_scope
    from src.db.schema import Competition, Match, Team
    init_db()
    with session_scope() as s:
        comp = Competition(sport=sport, code=code, name=code, area="USA", type="LEAGUE")
        h = Team(sport=sport, name=f"{code} Home")
        a = Team(sport=sport, name=f"{code} Away")
        s.add_all([comp, h, a])
        s.flush()
        ids = {}
        for pid, status, hs, as_, ko in rows:
            m = Match(sport=sport, competition_id=comp.id, season="2024", utc_date=ko, status=status,
                      home_team_id=h.id, away_team_id=a.id, home_score=hs, away_score=as_, stage="Regular Season",
                      external_ids=({source: str(pid)} if pid is not None else {}))
            s.add(m)
            s.flush()
            ids[pid] = m.id
        return ids


def _statuses(ids):
    from src.db.database import session_scope
    from src.db.schema import Match
    with session_scope() as s:
        return {pid: (m.status, m.utc_date, m.home_score, m.away_score)
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
        (9109, S, 20, 17, _af_ko()),          # a stated NS with both scores: left
        (9110, S, 20, 17, _af_ko(6)),         # FT, stored SCHEDULED a day off: the sync's own change + a kickoff
        (None, S, 7, 3, _af_ko()),            # no provider id: not in the listing, left
    ])
    before = _statuses(ids)
    calls, out = [], []
    ad = _faked(APIAmericanFootballAdapter(), _payload("american_football_games.json"), calls)
    rc = sp.run(["ZSPF"], ["2024"], lambda c: ad, out=out.append)
    assert rc == 0
    assert calls == [("games", {"league": 1, "season": 2024})]                  # one season read, no date
    assert _statuses(ids) == before                                              # writes nothing
    text = "\n".join(out)
    assert out[0].startswith("SCORE-PRESENCE DRY RUN (#493")
    assert "ZSPF 2024 · source api_american_football · listing 12 games · stored 7 rows" in out
    assert ("  THE RULE CHANGES 2 stored row(s) at the next sync of ZSPF 2024 · listed with both scores and no status "
            "stated 5 · listed with both scores and the text 'None' 2 · already as the fixed parse reads 2 · not "
            "stored 3") in out
    assert (f"    match {ids[9101]} · provider 9101 · 2024-09-07 17:00:00Z · Regular Season · absent · SCHEDULED → "
            "FINISHED") in out
    assert (f"    match {ids[9105]} · provider 9105 · 2024-09-07 17:00:00Z · Regular Season · text 'None' · FINISHED → "
            "SCHEDULED") in out
    assert f"    already: match {ids[9102]} · provider 9102 · 2024-09-07 17:00:00Z · Regular Season · absent · " \
           "FINISHED" in out
    assert "    not stored: provider 9103 · 2024-09-07 17:00:00Z · absent · no stored row holds this id; the sync " \
           "writes it FINISHED (created, or re-keyed onto a stored row, if both teams are stored)" in out
    assert "  stored SCHEDULED with both scores: 5 · the rule changes 1 · the rule leaves 4" in out
    assert f"    left: match {ids[9106]} · provider 9106 · 2024-09-07 17:00:00Z · Regular Season · the provider " \
           "states 'None' (a stated status the map lacks: stays SCHEDULED, law 4)" in out
    assert f"    left: match {ids[9109]} · provider 9109 · 2024-09-07 17:00:00Z · Regular Season · the provider " \
           "states 'NS' (the sync writes SCHEDULED)" in out
    assert f"    left: match {ids[9110]} · provider 9110 · 2024-09-06 17:00:00Z · Regular Season · the provider " \
           "states 'FT' (the sync writes FINISHED)" in out
    assert f"    left: match {ids[None]} · provider — · 2024-09-07 17:00:00Z · Regular Season · not in the listing " \
           "(the sync does not touch it)" in out
    assert ("  THE SAME WHOLE-SEASON SYNC ALSO WRITES (not the rule's): status 1 · kickoff 1 · scores 0 (values not "
            "printed)") in out
    assert (f"    status: match {ids[9110]} · provider 9110 · 2024-09-06 17:00:00Z · Regular Season · SCHEDULED → "
            "FINISHED (the provider states 'FT')") in out
    assert f"    kickoff: match {ids[9110]} · provider 9110 · 2024-09-06 17:00:00Z → 2024-09-07 17:00:00Z" in out
    assert "20-17" not in text and "17-20" not in text                           # no score is printed
    tail = json.loads(out[-1].split(" ", 1)[1])
    assert out[-1].startswith("SCORE-PRESENCE-DRY-RUN {")
    assert tail["changes_total"] == 2 and tail["written"] == 0 and tail["unread"] == []
    assert tail["by_competition_season"]["ZSPF 2024"] == {
        "listing": 12, "stored": 7, "changes": 2, "listed_absent_both_scores": 5, "listed_none_text_both_scores": 2,
        "already": 2, "not_stored": 3, "sched_both_scores": 5, "left": 4, "also_status": 1, "also_kickoff": 1,
        "also_scores": 0}


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
