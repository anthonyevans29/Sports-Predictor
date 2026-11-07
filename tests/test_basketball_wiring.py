"""The basketball wiring, NBA only (ARCHITECT 2026-11-06, addendum 271 item 3(a)-(d),(g); addendum 272 item 5; lane
basketball-market-only, #839): Sport.BASKETBALL, the api_basketball adapter cloned from api_hockey, its registry entry,
the NBA competition, and the three syncs.

Every payload here is SYNTHETIC, shaped like the fields #839's receipt names as served (a flat /games item: id, date,
timestamp, timezone, time, stage, week, venue, status{short,long,timer}, league{id,name,season,type,logo}, country,
teams.home/away{id,name,logo}, scores.home/away{quarter_1..4, over_time, total}; /teams items: country, id, logo,
name, nationnal); no real row is copied. The provider is never called: the adapter's _get is replaced. Throwaway DB
only (tests/conftest.py)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner

from src.adapters import api_basketball as ab
from src.adapters.api_basketball import APIBasketballAdapter, Refused, pick_season
from src.adapters.base import DataAdapter
from src.db.schema import MatchStatus, Sport

ROOT = Path(__file__).resolve().parent.parent
SERVED = ("2013-2014", "2026-2027", "2012-2013", "2025-2026", "2024-2025")     # unsorted, as /leagues serves them
T0 = int(datetime(2026, 11, 5, 0, 30, tzinfo=timezone.utc).timestamp())       # a synthetic UTC kickoff


def league(lid=12, name="NBA", seasons=SERVED, nested=False, scalar=False):
    ss = list(seasons) if scalar else [{"season": s, "start": None, "end": None} for s in seasons]
    lg = {"id": lid, "name": name, "type": "League", "logo": "synthetic"}
    if nested:
        return {"league": lg, "country": {"id": 1, "name": "Synthland"}, "seasons": ss}
    return {**lg, "country": {"id": 1, "name": "Synthland"}, "seasons": ss}


def team(tid, name=None, country="Synthland"):
    return {"id": tid, "name": name or f"Synthetic Team {tid}", "logo": "synthetic", "nationnal": False,
            "country": {"id": 1, "name": country, "code": "SY", "flag": None}}


def side(total, q=(1, 2, 3, 4), ot=None):
    return {"quarter_1": q[0], "quarter_2": q[1], "quarter_3": q[2], "quarter_4": q[3], "over_time": ot,
            "total": total}


def game(gid, short="NS", long="Not Started", home=101, away=102, ts=T0, hs=None, as_=None, stage=None, week=None,
         season="2026-2027", date=None, status=True):
    g = {"id": gid, "date": date if date is not None else (
            datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts is not None else None),
         "time": "00:30", "timestamp": ts, "timezone": "UTC", "stage": stage, "week": week, "venue": None,
         "league": {"id": 12, "name": "NBA", "type": "League", "season": season, "logo": "synthetic"},
         "country": {"id": 1, "name": "Synthland", "code": "SY", "flag": None},
         "teams": {"home": {"id": home, "name": f"Synthetic Team {home}", "logo": "synthetic"},
                   "away": {"id": away, "name": f"Synthetic Team {away}", "logo": "synthetic"}},
         "scores": {"home": side(hs) if hs is not None else side(None, (None,) * 4),
                    "away": side(as_) if as_ is not None else side(None, (None,) * 4)}}
    if status:
        g["status"] = {"short": short, "long": long, "timer": None}
    return g


class FakeProvider:
    """Answers /leagues, /teams and /games from synthetic payloads; records every call (path, params)."""

    def __init__(self, leagues=None, teams=None, games=None, remaining=7490):
        self.leagues = leagues if leagues is not None else [league(), league(17, "NBA - Synthetic Summer", [2026])]
        self.teams = teams or {}          # served season -> items
        self.games = games or {}          # served season -> items
        self.remaining = remaining
        self.calls: list[tuple[str, dict]] = []
        self.adapter = None

    def __call__(self, path, params=None):
        p = dict(params or {})
        self.calls.append((path, p))
        if self.adapter is not None:                       # what the adapter's own _get keeps, per request
            self.adapter._requests_remaining = self.remaining - len(self.calls)
            self.adapter.calls += 1
        if path == "leagues":
            return {"errors": [], "response": self.leagues}
        if path == "teams":
            return {"errors": [], "response": self.teams.get(p.get("season"), [])}
        if path == "games":
            items = self.games.get(p.get("season"), [])
            if "date" in p:
                items = [g for g in items if g.get("timestamp") is not None and datetime.fromtimestamp(
                    g["timestamp"], tz=timezone.utc).date().isoformat() == p["date"]]
            return {"errors": [], "response": items}
        raise AssertionError(f"unexpected path {path}")


def adapter_with(fake: FakeProvider) -> APIBasketballAdapter:
    a = APIBasketballAdapter()
    a._get = fake
    fake.adapter = a
    return a


# ---- (b) the season: the served season that STARTS with our year; none served -> refuse ---------------------------

def test_the_season_is_the_one_served_that_starts_with_our_year_from_an_unsorted_mixed_list():
    for nested in (False, True):
        for scalar in (False, True):
            fake = FakeProvider(leagues=[league(nested=nested, scalar=scalar)])
            a = adapter_with(fake)
            assert a.provider_season("NBA", "2026") == "2026-2027"
            assert a.provider_season("NBA", "2024") == "2024-2025"
            assert a.provider_season("NBA", "2012") == "2012-2013"
            assert [c[0] for c in fake.calls] == ["leagues"]          # /leagues once per instance, no parameter
            assert fake.calls[0][1] == {}
    assert pick_season([2025, 2026], "2026") == 2026                  # an int season as served, sent as served
    assert pick_season(["2026-2027"], "2026") == "2026-2027"


def test_no_served_season_refuses_and_nothing_is_computed():
    fake = FakeProvider(leagues=[league(seasons=("2025-2026", "2026-2027"))])
    a = adapter_with(fake)
    with pytest.raises(Refused) as e:
        a.list_matches("NBA", season="2024")
    msg = str(e.value)
    assert msg.startswith("REFUSED: no served season starts with '2024'") and "never computes" in msg
    assert "'2025-2026', '2026-2027'" in msg                          # the served list, named
    assert [c[0] for c in fake.calls] == ["leagues"]                  # no /games call was made
    with pytest.raises(Refused, match="no served season starts with '2027'"):
        pick_season(["20271-2028", "2026-2027"], "2027")              # a longer year is not our year
    with pytest.raises(Refused, match="2 served seasons start with '2026'"):
        pick_season(["2026-2027", "2026"], "2026")


@pytest.mark.parametrize("season", [None, "", "2026/27", "26", "2026-2027"])
def test_a_missing_or_non_int_style_season_refuses_before_any_call(season):
    fake = FakeProvider()
    a = adapter_with(fake)
    for read in (lambda: a.list_teams("NBA", season), lambda: a.list_matches("NBA", season=season)):
        with pytest.raises(Refused, match="REFUSED"):
            read()
    assert fake.calls == []


def test_only_the_nba_is_served_and_league_12_must_be_named_exactly_nba():
    fake = FakeProvider()
    a = adapter_with(fake)
    for code in ("NCAAMB", "NCAA", "NHL", "WNBA"):
        with pytest.raises(Refused, match=f"competition '{code}' is not served by api_basketball"):
            a.list_matches(code, season="2026")
    assert fake.calls == []
    renamed = adapter_with(FakeProvider(leagues=[league(name="NBA - G League")]))
    with pytest.raises(Refused, match="names league 12 'NBA - G League', not 'NBA'"):
        renamed.provider_season("NBA", "2026")
    twice = adapter_with(FakeProvider(leagues=[league(), league()]))
    with pytest.raises(Refused, match="2 leagues with id 12"):
        twice.provider_season("NBA", "2026")


def test_the_served_season_string_is_sent_and_a_date_only_when_from_equals_to(capsys):
    fake = FakeProvider(teams={"2026-2027": [team(101), team(102)]},
                        games={"2026-2027": [game(1, ts=T0), game(2, ts=T0 + 86400)]})
    a = adapter_with(fake)
    assert len(a.list_teams("NBA", "2026")) == 2
    day = datetime.fromtimestamp(T0, tz=timezone.utc).date().isoformat()
    assert [m.source_id for m in a.list_matches("NBA", "2026", day, day)] == ["1"]
    capsys.readouterr()
    assert len(a.list_matches("NBA", "2026", day, "2026-11-07")) == 2      # a range: the whole season, said first
    assert f"RANGE {day}..2026-11-07 is not supported by this provider" in capsys.readouterr().out
    assert fake.calls[1:] == [("teams", {"league": 12, "season": "2026-2027"}),
                              ("games", {"league": 12, "season": "2026-2027", "date": day}),
                              ("games", {"league": 12, "season": "2026-2027"})]


# ---- (c) the status map, by short code ------------------------------------------------------------------------------

@pytest.mark.parametrize("short,long,want", [
    ("NS", "Not Started", MatchStatus.SCHEDULED),
    ("FT", "Game Finished", MatchStatus.FINISHED),
    ("AOT", "After Over Time", MatchStatus.FINISHED),
    ("CANC", "Cancelled", MatchStatus.CANCELLED),
    ("CANC", "Game Cancelled", MatchStatus.CANCELLED),            # both long forms: the map keys on the short
    ("POST", "Game Postponed", MatchStatus.POSTPONED),
    # every other code stays SCHEDULED, its code kept (law 4); no live code is mapped; hockey's extras do not carry
    ("Q1", "Quarter 1", MatchStatus.SCHEDULED), ("HT", "Halftime", MatchStatus.SCHEDULED),
    ("OT", "Over Time", MatchStatus.SCHEDULED), ("BT", "Break Time", MatchStatus.SCHEDULED),
    ("P1", "x", MatchStatus.SCHEDULED), ("PST", "x", MatchStatus.SCHEDULED), ("ASO", "x", MatchStatus.SCHEDULED),
    ("AP", "x", MatchStatus.SCHEDULED), ("SYNTH", "an unseen code", MatchStatus.SCHEDULED),
])
def test_the_status_map_table(short, long, want):
    a = adapter_with(FakeProvider(games={"2026-2027": [game(7, short, long, hs=100, as_=99)]}))
    (m,) = a.list_matches("NBA", "2026")
    assert m.status == want and m.status_raw == short


def test_the_map_holds_the_five_ruled_codes_only_and_an_absent_status_is_not_inferred_from_scores():
    assert set(ab._STATUS) == {"NS", "FT", "AOT", "CANC", "POST"}
    assert MatchStatus.LIVE not in ab._STATUS.values()
    a = adapter_with(FakeProvider(games={"2026-2027": [game(8, status=False, hs=101, as_=100)]}))
    (m,) = a.list_matches("NBA", "2026")
    assert m.status == MatchStatus.SCHEDULED and m.status_raw is None      # no score-presence inference (3(c))


def test_aot_is_finished_with_the_overtime_flag_as_hockey_keeps_it():
    g = game(9, "AOT", "After Over Time", hs=120, as_=118)
    g["scores"]["home"]["over_time"], g["scores"]["away"]["over_time"] = 12, 10
    (m,) = adapter_with(FakeProvider(games={"2026-2027": [g]})).list_matches("NBA", "2026")
    assert (m.status, m.status_raw) == (MatchStatus.FINISHED, "AOT")     # the flag = status_raw, no new field
    assert (m.home_score, m.away_score) == (120, 118)                    # the served totals, overtime included
    assert m.raw["scores"]["home"]["over_time"] == 12


# ---- (d) the kickoff in UTC from the served timestamp ---------------------------------------------------------------

def test_the_kickoff_is_utc_from_the_timestamp_then_the_offset_date(capsys):
    games = [
        game(10, ts=T0, date="2026-11-04T20:30:00-04:00"),                 # the same instant both ways
        game(11, ts=T0, date="2026-11-09T00:00:00+00:00"),                 # disagreeing: the timestamp wins
        game(12, ts=None, date="2026-11-04T19:30:00-05:00"),               # no timestamp: the offset date
        game(13, ts=None, date="2026-11-05T00:30:00"),                     # no offset: never given a zone
        game(14, ts=None, date=""),
    ]
    a = adapter_with(FakeProvider(games={"2026-2027": games}))
    got = {m.source_id: m.utc_date for m in a.list_matches("NBA", "2026")}
    assert got == {"10": datetime(2026, 11, 5, 0, 30), "11": datetime(2026, 11, 5, 0, 30),
                   "12": datetime(2026, 11, 5, 0, 30)}
    assert all(d.tzinfo is None for d in got.values())
    assert "api_basketball /games: 2 listing(s) not read (no readable kickoff 2): 13, 14" in capsys.readouterr().out
    assert a.last_dropped == {"no readable kickoff": [13, 14]}


# ---- (g) totals stored; the quarters NOT KEPT (274 item 2(10)) -------------------------------------------------------

def test_totals_are_read_with_no_falsy_default_and_the_quarters_are_not_kept():
    """ARCHITECT 2026-11-06, addendum 274 item 2(10): "the transient reading STANDS; nothing is kept, no file under
    exports/, no column"; 271 item 3(g) CORRECTED to "not persisted". The served item rides the normalized record for
    the sync's life only (nothing reads it); no column, no field named for a quarter, and the records say NOT KEPT."""
    import re as _re
    g = game(15, "FT", "Game Finished", hs=0, as_=97)
    (m,) = adapter_with(FakeProvider(games={"2026-2027": [g]})).list_matches("NBA", "2026")
    assert (m.home_score, m.away_score) == (0, 97)                         # a 0 stays 0
    assert m.raw is g and m.raw["scores"]["away"]["quarter_4"] == 4       # transient: the served item, as served
    from src.adapters.normalized import NormalizedMatch
    from src.db.schema import Match
    assert not [f for f in NormalizedMatch.__dataclass_fields__ if "quarter" in f or "over_time" in f]
    assert not [c.name for c in Match.__table__.columns if "quarter" in c.name or "raw" == c.name]
    # nothing on any path reads the field (274 item 2(10): "nothing on any path reads a quarter")
    readers = []
    for f in [*ROOT.joinpath("src").rglob("*.py"), *ROOT.joinpath("deploy").rglob("*.py"),
              *ROOT.joinpath("scripts").rglob("*.py"), ROOT / "cli.py"]:
        for i, ln in enumerate(f.read_text().splitlines(), 1):
            if _re.search(r"(?<!NormalizedMatch)\.raw\b(?!_)", ln) and "self.raw" not in ln:
                readers.append(f"{f.relative_to(ROOT)}:{i}")
    assert readers == [], readers
    # the wording: NOT KEPT / not persisted, never "the raw payload"
    adapter_src = (ROOT / "src" / "adapters" / "api_basketball.py").read_text()
    norm_src = (ROOT / "src" / "adapters" / "normalized.py").read_text()
    for src in (adapter_src, norm_src):
        assert "addendum 274 item 2(10)" in src and "NOT KEPT" in src
        assert "raw payload" not in src.lower() and "live here only" not in src
    assert "not persisted" in norm_src


def test_stage_and_week_are_kept_as_served_and_a_week_is_never_digit_mined():
    games = [game(16, stage="Synthetic Stage", week="Synthetic 3"), game(17, stage=None, week=5),
             game(18, week="12"), game(19, stage="", week=True)]
    got = {m.source_id: (m.stage, m.matchday) for m in
           adapter_with(FakeProvider(games={"2026-2027": games})).list_matches("NBA", "2026")}
    assert got == {"16": ("Synthetic Stage", None), "17": (None, 5), "18": (None, 12), "19": (None, None)}


def test_the_stored_season_is_ours_never_the_providers():
    ms = adapter_with(FakeProvider(games={"2026-2027": [game(20)]})).list_matches("NBA", "2026")
    assert [m.season for m in ms] == ["2026"]


def test_listings_without_an_id_or_a_team_id_are_counted_never_silent(capsys):
    no_team = game(22)
    no_team["teams"]["away"] = {"name": "x"}
    no_id = game(21)
    no_id["id"] = None
    a = adapter_with(FakeProvider(games={"2026-2027": [no_id, no_team, game(23)]}))
    assert [m.source_id for m in a.list_matches("NBA", "2026")] == ["23"]
    assert "2 listing(s) not read (no id 1 · no team id 1): 22" in capsys.readouterr().out


def test_teams_area_is_the_served_country_and_codes_are_read_if_served():
    fake = FakeProvider(teams={"2026-2027": [team(101, country="Synthland"), team(102, country="Othersynth"),
                                             {"id": 103}]})
    ts = adapter_with(fake).list_teams("NBA", "2026")
    assert [(t.source_id, t.area, t.tla, t.sport) for t in ts] == [
        ("101", "Synthland", None, Sport.BASKETBALL), ("102", "Othersynth", None, Sport.BASKETBALL)]


# ---- (a) the key, the header, metering, the errors check -------------------------------------------------------------

def test_the_key_is_api_basketball_key_then_api_football_key(monkeypatch):
    monkeypatch.setenv("API_BASKETBALL_KEY", "synthetic-basketball")
    monkeypatch.setenv("API_FOOTBALL_KEY", "synthetic-shared")
    a = APIBasketballAdapter()
    assert (a.key_name, a._headers) == ("API_BASKETBALL_KEY", {"x-apisports-key": "synthetic-basketball"})
    monkeypatch.delenv("API_BASKETBALL_KEY")
    a = APIBasketballAdapter()
    assert (a.key_name, a._headers) == ("API_FOOTBALL_KEY", {"x-apisports-key": "synthetic-shared"})
    monkeypatch.delenv("API_FOOTBALL_KEY")
    assert APIBasketballAdapter().key_name is None


class _Resp:
    def __init__(self, body, status=200, remaining="7499"):
        self.status_code, self._body = status, body
        self.headers = {"x-ratelimit-requests-remaining": remaining} if remaining is not None else {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._body


def test_every_call_prints_the_remaining_requests_and_a_provider_error_raises(monkeypatch, capsys):
    seen = []

    def get(url, headers=None, params=None, timeout=None):
        seen.append((url, dict(headers), dict(params)))
        return _Resp({"errors": [], "response": [league()]})

    monkeypatch.setattr(ab.requests, "get", get)
    a = APIBasketballAdapter()
    assert a.provider_season("NBA", "2026") == "2026-2027"
    assert seen[0][0] == "https://v1.basketball.api-sports.io/leagues" and "x-apisports-key" in seen[0][1]
    out = capsys.readouterr().out
    assert "api_basketball /leagues {} · HTTP 200 · 1 items · x-ratelimit-requests-remaining 7499" in out
    assert a.requests_remaining == 7499 and a.calls == 1
    monkeypatch.setattr(ab.requests, "get", lambda *x, **k: _Resp({"errors": {"plan": "synthetic refusal"},
                                                                    "response": []}, remaining=None))
    with pytest.raises(RuntimeError, match="api_basketball games: .*synthetic refusal"):
        APIBasketballAdapter()._get("games", {"league": 12})
    assert "x-ratelimit-requests-remaining not served" in capsys.readouterr().out


def test_a_429_answer_is_counted_and_prints_its_own_metering_line(monkeypatch, capsys):
    """3(f), "the receipt still prints the day's x-ratelimit-requests-remaining as every API-Sports run does": the
    rate-limited answer is a provider request too, so it is counted in `calls` and prints its own line (status,
    remaining as served) before the one retry."""
    answers = [_Resp({}, status=429, remaining="7300"), _Resp({"errors": [], "response": [league()]}, remaining="7299")]
    monkeypatch.setattr(ab.requests, "get", lambda *x, **k: answers.pop(0))
    monkeypatch.setattr(ab.time, "sleep", lambda s: None)
    a = APIBasketballAdapter()
    a._get("leagues")
    out = capsys.readouterr().out
    assert a.calls == 2 and not answers
    assert "api_basketball /leagues {} · HTTP 429 · rate limited, one retry in 5s · x-ratelimit-requests-remaining 7300" in out
    assert "api_basketball /leagues {} · HTTP 200 · 1 items · x-ratelimit-requests-remaining 7299" in out


def test_no_odds_call_and_no_stats():
    assert APIBasketballAdapter.list_odds is DataAdapter.list_odds              # base: [] with no /odds call
    assert APIBasketballAdapter().list_odds("1") == [] and APIBasketballAdapter().get_match_stats("1") == []


# ---- registry, competition, routing ---------------------------------------------------------------------------------

def test_registry_competition_and_cli_routing():
    import cli
    from src.adapters.registry import DEFAULT_FOR_SPORT, get_adapter
    assert Sport("basketball") is Sport.BASKETBALL and Sport.BASKETBALL.name == "BASKETBALL"
    assert DEFAULT_FOR_SPORT["basketball"] == "api_basketball"
    assert isinstance(get_adapter(sport="basketball"), APIBasketballAdapter)
    assert isinstance(get_adapter(source="api_basketball"), APIBasketballAdapter)
    assert cli._sport_for_competition("NBA") == "basketball" and cli._sport_for_competition("nba") == "basketball"
    assert cli._sport_for_competition("NHL") == "nhl" and cli._sport_for_competition("PL") == "soccer"
    (c,) = APIBasketballAdapter().list_competitions(Sport.BASKETBALL)
    assert (c.code, c.source, c.source_id, c.sport) == ("NBA", "api_basketball", "12", Sport.BASKETBALL)
    assert APIBasketballAdapter().list_competitions(Sport.NHL) == []


def test_the_bootstrap_routes_basketball_after_every_existing_family():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy" / "hosting"))
    import bootstrap
    assert bootstrap.SPORT_CLI["BASKETBALL"] == "basketball"
    # TENNIS after it (addendum 261 item 2(c), lane tennis-market-only): basketball's place is unchanged
    assert bootstrap.FAMILY_ORDER == ["MLB", "NFL", "NHL", "SOCCER", "BASKETBALL", "TENNIS"]


def test_the_bootstrap_plans_the_nba_kalshi_sync_only_when_the_reference_holds_basketball():
    """The plan's Kalshi day-one block: a reference holding NBA rows takes its first NBA Kalshi market at bootstrap,
    as every other two-way sport the bootstrap routes does; a reference without basketball plans exactly the block
    it planned before (no existing bootstrap changes)."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy" / "hosting"))
    import bootstrap
    block = [["sync-kalshi"], ["sync-kalshi-soccer"], ["sync-kalshi-nfl"], ["sync-kalshi-nhl"], ["sync-kalshi-ncaa"]]
    nhl = [{"sport": "NHL", "comp": "NHL", "season": "2026", "status": "SCHEDULED"}]
    nba = [{"sport": "BASKETBALL", "comp": "NBA", "season": "2026", "status": "SCHEDULED"}]
    without = bootstrap.plan({"games": nhl})
    assert without[-5:] == block and ["sync-kalshi-nba"] not in without
    with_nba = bootstrap.plan({"games": nhl + nba})
    assert with_nba[-6:] == block + [["sync-kalshi-nba"]]
    assert with_nba.index(["sync-matches", "--competition", "NBA", "--season", "2026"]) < with_nba.index(
        ["sync-kalshi-nba"])


# ---- the three syncs, end to end through the CLI (throwaway DB) -----------------------------------------------------

@pytest.fixture
def nba_rows():
    """Removes every NBA / BASKETBALL row the test wrote (the throwaway DB is shared across the session)."""
    yield
    from src.db.database import session_scope
    from src.db.schema import Competition, CompetitionTeam, Match, Team
    with session_scope() as s:
        comp_ids = [c.id for c in s.query(Competition).filter(Competition.code == "NBA")]
        s.query(Match).filter(Match.competition_id.in_(comp_ids)).delete(synchronize_session=False)
        s.query(CompetitionTeam).filter(CompetitionTeam.competition_id.in_(comp_ids)).delete(synchronize_session=False)
        s.query(Team).filter(Team.sport == Sport.BASKETBALL).delete(synchronize_session=False)
        s.query(Competition).filter(Competition.code == "NBA").delete(synchronize_session=False)


def test_the_three_syncs_store_the_nba_with_our_season_the_ruled_map_and_the_totals(monkeypatch, nba_rows):
    import cli
    from sqlalchemy import text
    from src.db.database import init_db, session_scope
    init_db()
    games = [game(31, "FT", "Game Finished", 101, 102, T0, hs=0, as_=101),
             game(32, "AOT", "After Over Time", 103, 104, T0 + 3600, hs=120, as_=118),
             game(33, "CANC", "Cancelled", 101, 102, T0 + 1800),
             game(34, "SYNTH", "an unseen code", 103, 101, T0 + 86400),
             game(35, "NS", "Not Started", 101, 999, T0 + 86400)]           # 999: not on /teams, skipped
    fake = FakeProvider(teams={"2026-2027": [team(i) for i in (101, 102, 103, 104)]}, games={"2026-2027": games})
    monkeypatch.setattr(APIBasketballAdapter, "_get", lambda self, path, params=None: fake(path, params))
    monkeypatch.setattr(cli, "_mlb_fallback", lambda c: False)
    monkeypatch.setattr(cli, "utc_now_naive", lambda: datetime(2026, 11, 6, 12, 0))
    run = CliRunner()
    for args in (["sync-competitions", "--sport", "basketball"],
                 ["sync-teams", "--competition", "NBA", "--season", "2026"],
                 ["sync-matches", "--competition", "NBA", "--season", "2026"]):
        res = run.invoke(cli.cli, args)
        assert res.exit_code == 0, (args, res.output, res.exception)
    assert "skipped 1 listing(s) of clubs not in the DB: 35" in res.output
    res = run.invoke(cli.cli, ["sync-matches", "--competition", "NBA", "--seasons", "1"])    # the --seasons shape
    assert res.exit_code == 0 and "season 2026" in res.output and "2026/27" not in res.output, res.output
    assert ("games", {"league": 12, "season": "2026-2027"}) in fake.calls
    with session_scope() as s:
        comp = s.execute(text("SELECT sport, code, external_ids FROM competitions WHERE code = 'NBA'")).one()
        assert comp[0] == "BASKETBALL" and '"api_basketball": "12"' in comp[2]
        got = {r[0]: r[1:] for r in s.execute(text(
            "SELECT json_extract(m.external_ids, '$.api_basketball'), m.sport, m.season, m.status, m.status_raw, "
            "m.home_score, m.away_score FROM matches m JOIN competitions c ON c.id = m.competition_id "
            "WHERE c.code = 'NBA'"))}
        links = s.execute(text("SELECT DISTINCT ct.season FROM competition_teams ct JOIN competitions c "
                               "ON c.id = ct.competition_id WHERE c.code = 'NBA'")).scalars().all()
    assert got == {"31": ("BASKETBALL", "2026", "FINISHED", "FT", 0, 101),
                   "32": ("BASKETBALL", "2026", "FINISHED", "AOT", 120, 118),
                   "33": ("BASKETBALL", "2026", "CANCELLED", "CANC", None, None),
                   "34": ("BASKETBALL", "2026", "SCHEDULED", "SYNTH", None, None)}
    assert links == ["2026"]


def test_a_refused_season_stores_nothing(monkeypatch, nba_rows):
    import cli
    from src.db.database import init_db, session_scope
    from src.db.schema import Match
    init_db()
    fake = FakeProvider(leagues=[league(seasons=("2025-2026",))])
    monkeypatch.setattr(APIBasketballAdapter, "_get", lambda self, path, params=None: fake(path, params))
    monkeypatch.setattr(cli, "_mlb_fallback", lambda c: False)
    assert CliRunner().invoke(cli.cli, ["sync-competitions", "--sport", "basketball"]).exit_code == 0
    res = CliRunner().invoke(cli.cli, ["sync-matches", "--competition", "NBA", "--season", "2026"])
    assert res.exit_code != 0 and isinstance(res.exception, Refused)
    assert "no served season starts with '2026'" in str(res.exception)
    with session_scope() as s:
        assert s.query(Match).filter(Match.sport == Sport.BASKETBALL).count() == 0
    assert [c[0] for c in fake.calls] == ["leagues"]
