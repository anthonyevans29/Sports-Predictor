"""THE PRICE BELONGS TO THE TEAM (ARCHITECT 2026-11-08 10:05 ET, addendum 295 items 2, 4, 5 and 6; #885).

Item 5, verbatim in part: "(a) When the listed pair is the stored row's reverse, the upsert writes
`external_ids["provider_orientation"] = "reversed"`, and removes the key when the listing reads same; a mismatch writes
nothing (the row untouched, as now). [...] (b) `sync_odds`, `sync_odds_nfl` and the MLB fallback's odds path, if it has
one, swap HOME and AWAY selections into the stored orientation when the key is present, counted on the receipt with
the match ids; the 1X2 devig into odds_snapshots then follows the stored orientation. (c) Tests on both writers."

Fail-first (5(c)): a stored row with provider_orientation reversed receives the provider's HOME price as our AWAY
selection, on both writers: soccer 1X2 with a draw (sync_odds) and the NFL two-way (sync_odds_nfl).

Throwaway DB only (tests/conftest.py); fake adapters, no network. Every row a test creates is removed after it (the test
DB is shared across the session: the NFL odds window and the MLB fallback read every row of their sport)."""
import itertools
from datetime import datetime, timedelta

import pytest
from click.testing import CliRunner
from sqlalchemy import select

from src.adapters.normalized import NormalizedMatch, NormalizedOdds
from src.db.database import init_db, session_scope
from src.db.schema import (Competition, CompetitionTeam, Match, MatchNeutralDerived, MatchStatus, Odds, OddsSnapshot,
                           Result, Sport, Team)
from src.ingestion import service as svc
from src.ingestion.score_orientation import PROVIDER_ORIENTATION_KEY, provider_reversed, selection_by_team
from src.ingestion.service import IngestionService
from src.timeutil import utc_now_naive

AF = "api_american_football"
FAKE = "fakeodds295"
_seq = itertools.count(1)
KO = datetime(2042, 3, 1, 15, 0)


@pytest.fixture
def made():
    """Collects the ids a test creates; removes them (odds, snapshots, neutral rows, matches, links, teams, comps)."""
    init_db()
    got = {"matches": [], "teams": [], "comps": []}
    yield got
    with session_scope() as s:
        mids = got["matches"]
        if mids:
            for model in (Odds, OddsSnapshot, MatchNeutralDerived):
                s.query(model).filter(model.match_id.in_(mids)).delete(synchronize_session=False)
            s.query(Match).filter(Match.id.in_(mids)).delete(synchronize_session=False)
        if got["teams"]:
            s.query(CompetitionTeam).filter(CompetitionTeam.team_id.in_(got["teams"])).delete(
                synchronize_session=False)
            s.query(Team).filter(Team.id.in_(got["teams"])).delete(synchronize_session=False)
        if got["comps"]:
            s.query(Competition).filter(Competition.id.in_(got["comps"])).delete(synchronize_session=False)


def _world(made, sport, source, code, when=KO, n_teams=2, ext=None):
    """A private competition, n teams with provider ids, and one stored SCHEDULED row (teams 0 home, 1 away)."""
    with session_scope() as s:
        comp = Competition(sport=sport, code=code, name=code, area="X", type="LEAGUE")
        s.add(comp)
        ts = []
        for _ in range(n_teams):
            pid = f"o295-{next(_seq)}-{utc_now_naive():%H%M%S%f}"
            ts.append(Team(sport=sport, name=f"O295 {pid}", external_ids={source: pid}))
        s.add_all(ts)
        s.flush()
        sid = f"o295-g-{next(_seq)}"
        m = Match(sport=sport, competition_id=comp.id, season="2026", utc_date=when, status=MatchStatus.SCHEDULED,
                  home_team_id=ts[0].id, away_team_id=ts[1].id, external_ids={source: sid, **(ext or {})})
        s.add(m)
        s.flush()
        made["matches"].append(m.id)
        made["teams"] += [t.id for t in ts]
        made["comps"].append(comp.id)
        return m.id, sid, [(t.id, t.external_ids[source]) for t in ts]


def _odds(mid, source):
    with session_scope() as s:
        rows = list(s.execute(select(Odds).where(Odds.match_id == mid, Odds.source == source)).scalars())
        snaps = list(s.execute(select(OddsSnapshot).where(OddsSnapshot.match_id == mid,
                                                          OddsSnapshot.source == source)).scalars())
        return ({(o.market, o.selection, o.line): o.price_decimal for o in rows},
                {x.selection: x.devig_prob for x in snaps})


class FakeOdds:
    source_name = FAKE

    def __init__(self, rows):
        self.rows = rows

    def list_odds(self, source_id):
        return list(self.rows)


def _no(sel, px, market="1X2", line=None, source=FAKE):
    return NormalizedOdds(match_source_id="x", source=source, bookmaker="bk", market=market, selection=sel,
                          price_decimal=px, captured_at=KO - timedelta(days=1), line=line)


SOCCER_BOOK = [_no("HOME", 1.5), _no("DRAW", 4.0), _no("AWAY", 6.0), _no("OVER", 1.9, "OU_2.5"),
               _no("UNDER", 1.95, "OU_2.5")]


def _fair(*prices):
    inv = [1 / p for p in prices]
    return [x / sum(inv) for x in inv]


# ---------------------------------------------------------------------------------------------- the helper, pure

def test_the_selection_helper_swaps_home_and_away_only():
    assert [selection_by_team(x, True) for x in ("HOME", "AWAY", "DRAW", "OVER", "UNDER", "X")] == \
        ["AWAY", "HOME", "DRAW", "OVER", "UNDER", "X"]
    assert [selection_by_team(x, False) for x in ("HOME", "AWAY", "DRAW")] == ["HOME", "AWAY", "DRAW"]
    assert provider_reversed({PROVIDER_ORIENTATION_KEY: "reversed"}) and not provider_reversed({})
    assert not provider_reversed(None) and not provider_reversed({PROVIDER_ORIENTATION_KEY: "same"})


# ---------------------------------------------------------------------------------------------- sync_odds (soccer)

def test_sync_odds_a_reversed_row_takes_the_providers_home_price_as_our_away_and_the_draw_stays(made, monkeypatch):
    """5(c), fail-first: soccer 1X2 with a draw. The provider's HOME 1.5 is OUR AWAY team's price; the draw stays the
    draw; the totals stay as served; the devig into odds_snapshots follows the stored orientation; the id is listed."""
    mid, _sid, _ = _world(made, Sport.SOCCER, FAKE, "O295S", ext={PROVIDER_ORIENTATION_KEY: "reversed"})
    monkeypatch.setattr(svc, "utc_now_naive", lambda: KO - timedelta(days=3))
    res = IngestionService(FakeOdds(SOCCER_BOOK)).sync_odds("O295S")
    rows, snaps = _odds(mid, FAKE)
    assert rows[("1X2", "AWAY", None)] == 1.5 and rows[("1X2", "HOME", None)] == 6.0      # by team
    assert rows[("1X2", "DRAW", None)] == 4.0
    assert rows[("OU_2.5", "OVER", None)] == 1.9 and rows[("OU_2.5", "UNDER", None)] == 1.95
    h, d, a = _fair(6.0, 4.0, 1.5)
    assert snaps["HOME"] == pytest.approx(h) and snaps["AWAY"] == pytest.approx(a) and snaps["DRAW"] == pytest.approx(d)
    assert res.orientation_swapped == [mid] and res.created == 1


def test_sync_odds_a_same_row_keeps_todays_positions(made, monkeypatch):
    mid, _sid, _ = _world(made, Sport.SOCCER, FAKE, "O295T")
    monkeypatch.setattr(svc, "utc_now_naive", lambda: KO - timedelta(days=3))
    res = IngestionService(FakeOdds(SOCCER_BOOK)).sync_odds("O295T")
    rows, snaps = _odds(mid, FAKE)
    assert rows[("1X2", "HOME", None)] == 1.5 and rows[("1X2", "AWAY", None)] == 6.0
    assert snaps["HOME"] == pytest.approx(_fair(1.5, 4.0, 6.0)[0])
    assert res.orientation_swapped == []


def test_the_sync_odds_command_prints_the_swapped_ids_and_zero(made, monkeypatch):
    import cli
    mid, _sid, _ = _world(made, Sport.SOCCER, FAKE, "O295C", ext={PROVIDER_ORIENTATION_KEY: "reversed"})
    _world(made, Sport.SOCCER, FAKE, "O295Z")
    monkeypatch.setattr(svc, "utc_now_naive", lambda: KO - timedelta(days=3))
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda c: FakeOdds(SOCCER_BOOK))
    out = CliRunner().invoke(cli.cli, ["sync-odds", "--competition", "O295C"])
    assert out.exit_code == 0, out.output
    assert f"orientation_swapped 1: {mid}" in out.output.splitlines()
    out = CliRunner().invoke(cli.cli, ["sync-odds", "--competition", "O295Z"])
    assert "orientation_swapped 0" in out.output.splitlines(), out.output


# ---------------------------------------------------------------------------------------------- sync_odds_nfl

def _nfl_book(monkeypatch, book):
    monkeypatch.setattr("src.adapters.api_american_football.APIAmericanFootballAdapter.list_odds",
                        lambda self, gid: list(book))
    monkeypatch.setattr(svc, "_odds_sleep", lambda x: None)


NFL_BOOK = [_no("HOME", 1.4, source=AF), _no("AWAY", 3.0, source=AF),
            _no("HOME", 1.91, "SPREADS", -7.5, AF), _no("AWAY", 1.89, "SPREADS", 7.5, AF),
            _no("OVER", 1.9, "TOTALS", 45.5, AF), _no("UNDER", 1.9, "TOTALS", 45.5, AF)]


def test_sync_odds_nfl_a_reversed_row_takes_the_providers_home_price_as_our_away(made, monkeypatch):
    """5(c), fail-first: the NFL two-way. The provider's HOME moneyline 1.4 is OUR AWAY team's; its HOME spread -7.5
    @ 1.91 is OUR AWAY team's -7.5 (the line travels with its price); the totals as served; the snapshot follows."""
    mid, _sid, _ = _world(made, Sport.NFL, AF, "O295N", when=utc_now_naive() + timedelta(days=2),
                          ext={PROVIDER_ORIENTATION_KEY: "reversed"})
    _nfl_book(monkeypatch, NFL_BOOK)
    r = svc.sync_odds_nfl(match_ids={mid})
    rows, snaps = _odds(mid, AF)
    assert rows[("1X2", "AWAY", None)] == 1.4 and rows[("1X2", "HOME", None)] == 3.0
    assert rows[("SPREADS", "AWAY", -7.5)] == 1.91 and rows[("SPREADS", "HOME", 7.5)] == 1.89
    assert rows[("TOTALS", "OVER", 45.5)] == 1.9 and rows[("TOTALS", "UNDER", 45.5)] == 1.9
    h, a = _fair(3.0, 1.4)
    assert snaps == {"HOME": pytest.approx(h), "AWAY": pytest.approx(a)}
    assert r["orientation_swapped"] == [mid] and r["games"] == 1


def test_sync_odds_nfl_a_same_row_keeps_todays_positions(made, monkeypatch):
    mid, _sid, _ = _world(made, Sport.NFL, AF, "O295M", when=utc_now_naive() + timedelta(days=2))
    _nfl_book(monkeypatch, NFL_BOOK)
    r = svc.sync_odds_nfl(match_ids={mid})
    rows, snaps = _odds(mid, AF)
    assert rows[("1X2", "HOME", None)] == 1.4 and rows[("SPREADS", "HOME", -7.5)] == 1.91
    assert snaps["HOME"] == pytest.approx(_fair(1.4, 3.0)[0])
    assert r["orientation_swapped"] == []


def test_the_football_odds_command_prints_the_swapped_ids(monkeypatch):
    import cli
    monkeypatch.setattr(svc, "sync_odds_nfl", lambda progress=None: {"created": 6, "games": 1,
                                                                     "orientation_swapped": [41]})
    out = CliRunner().invoke(cli.cli, ["sync-odds-football"])
    assert out.exit_code == 0, out.output
    assert "orientation_swapped 1: 41" in out.output.splitlines()


# ---------------------------------------------------------------------------------------------- 5(a): the upsert

class Listing:
    def __init__(self, source, listing):
        self.source_name, self.listing = source, list(listing)

    def list_matches(self, code, season=None, date_from=None, date_to=None):
        return list(self.listing)


def _nm(code, sid, h, a, when, **kw):
    return NormalizedMatch(sport=Sport.NFL, competition_code=code, season="2026", utc_date=when,
                           status=MatchStatus.SCHEDULED, home_team_source_id=h, away_team_source_id=a, source=AF,
                           source_id=sid, **kw)


def _ext(mid):
    with session_scope() as s:
        return dict(s.get(Match, mid).external_ids or {})


def test_the_upsert_records_reversed_removes_it_on_same_and_writes_nothing_on_a_mismatch(made, monkeypatch):
    when = utc_now_naive() + timedelta(days=2)
    mid, sid, ((_h, hp), (_a, ap), (_x, xp)) = _world(made, Sport.NFL, AF, "O295U", when=when, n_teams=3)
    run = lambda *nm: IngestionService(Listing(AF, nm)).sync_matches("O295U", season="2026")   # noqa: E731
    res = run(_nm("O295U", sid, ap, hp, when))                                     # reversed
    assert _ext(mid) == {AF: sid, PROVIDER_ORIENTATION_KEY: "reversed"} and res.orientation_reversed == [mid]
    before = _ext(mid)
    res = run(_nm("O295U", sid, xp, hp, when))                                     # neither: nothing written
    assert _ext(mid) == before and res.teams_mismatch_refused == [mid]
    # the upsert's key, then the odds writer: the provider's HOME price lands on OUR AWAY selection
    _nfl_book(monkeypatch, NFL_BOOK)
    assert svc.sync_odds_nfl(match_ids={mid})["orientation_swapped"] == [mid]
    assert _odds(mid, AF)[0][("1X2", "AWAY", None)] == 1.4
    res = run(_nm("O295U", sid, hp, ap, when))                                     # same: the key removed
    assert _ext(mid) == {AF: sid} and res.orientation_reversed == []
    assert svc.sync_odds_nfl(match_ids={mid})["orientation_swapped"] == []
    assert _odds(mid, AF)[0][("1X2", "HOME", None)] == 1.4


# ---------------------------------------------------------------------------------------------- item 6: intl-sync

def test_intl_sync_writes_neutral_null_with_the_reason_on_a_reversed_row_and_derives_again_on_same(tmp_path, made):
    """Item 6: "on a row the upsert lists as reversed, `match_neutral_derived` is written NULL with the reason
    `orientation_reversed`". The listing's home (Testonia, ground Tëst Town) is our stored AWAY team: the derived flag
    would read neutral (Probe City != Tëst Town) for the stored home Probeland, who is at home. NULL instead."""
    import json
    from datetime import date
    from src.ingestion import intl_history as ih
    from tests.test_intl_history import GROUNDS, fx, league

    def write(d, home, away, hg, ag):
        d.mkdir()
        json.dump({"response": [league(5, "UEFA Nations League", 2074)]}, open(d / "leagues.json", "w"))
        json.dump({"response": [fx(9907401, home, away, hg, ag, "Probe City", when="2074-06-07T18:45:00+00:00",
                                   league_season=2074)]}, open(d / "fixtures_5_2074.json", "w"))
        json.dump({"response": GROUNDS}, open(d / "teams_5_2074.json", "w"))
    write(tmp_path / "first", 880001, 880002, 2, 1)
    write(tmp_path / "again", 880002, 880001, 1, 2)
    write(tmp_path / "third", 880001, 880002, 2, 1)
    ih.ingest(ih.Source(from_dir=str(tmp_path / "first")), date(2018, 1, 1))
    with session_scope() as s:
        mid = s.execute(select(Match.id).where(Match.external_ids["api_football"].as_string() == "9907401")).scalar_one()
    made["matches"].append(mid)

    def nd():
        with session_scope() as s:
            r = s.get(MatchNeutralDerived, mid)
            return r.neutral_derived, r.rule, r.venue_city, r.home_ground_city
    assert nd()[:2] == (False, ih.NEUTRAL_RULE)
    r = ih.ingest(ih.Source(from_dir=str(tmp_path / "again")), date(2018, 1, 1))
    assert r["orientation_reversed"] == [mid]
    flag, rule, vcity, _g = nd()
    assert flag is None and rule == ih.NEUTRAL_RULE_REVERSED and "orientation_reversed" in rule
    assert rule.startswith(ih.NEUTRAL_RULE) and len(rule) <= 512 and vcity == "Probe City"
    assert r["per_cs"][next(iter(r["per_cs"]))]["orientation_reversed"] == 1
    ih.ingest(ih.Source(from_dir=str(tmp_path / "third")), date(2018, 1, 1))
    assert nd()[:2] == (False, ih.NEUTRAL_RULE)                                   # the same pair: derived again
    assert PROVIDER_ORIENTATION_KEY not in _ext(mid)


# ---------------------------------------------------------------------------------------------- item 2: MLB fallback

class FakeClient:
    requests_remaining = 99

    def __init__(self, teams, games):
        self.teams, self.games = teams, games

    def list_teams(self, season):
        return self.teams

    def _get(self, path, params=None):
        return {"response": self.games}


def _g(gid, home, away, at, short="FT", hr=7, ar=2):
    return {"id": gid, "date": at.strftime("%Y-%m-%dT%H:%M:%S+00:00"), "week": "Regular Season",
            "status": {"short": short, "long": short},
            "teams": {"home": {"id": home[0], "name": home[1]}, "away": {"id": away[0], "name": away[1]}},
            "scores": {"home": {"total": hr}, "away": {"total": ar}}}


def test_the_mlb_fallback_writes_by_team_refuses_a_mismatch_and_keeps_a_missing_team_by_position(made):
    """Item 2: "a reversed pair writes swapped scores and result; a mismatch refuses the whole update for that game,
    counted on the fallback's receipt with the match id; a listing team missing from the DB keeps today's behaviour"."""
    from src.ingestion import mlb_apisports as fb
    U = datetime(2041, 7, 4, 17, 5)
    A, B, C, D = (295101, "Probe295 Alphas"), (295102, "Probe295 Betas"), (295103, "Probe295 Gammas"), \
        (295199, "Probe295 Unlisted")
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.sport == Sport.MLB,
                                                   Competition.code == "MLB")).scalars().first()
        if comp is None:
            comp = Competition(sport=Sport.MLB, code="MLB", name="Major League Baseball", area="USA", type="LEAGUE")
            s.add(comp)
            s.flush()
            made["comps"].append(comp.id)
        t = {}
        for tid, name in (A, B, C):
            t[tid] = Team(sport=Sport.MLB, name=name, external_ids={fb.SOURCE: str(tid)})
            s.add(t[tid])
        s.flush()
        made["teams"] += [x.id for x in t.values()]
        ids = {}
        for k, (gid, day) in enumerate((("2951", 0), ("2952", 1), ("2953", 2), ("2954", 3))):
            m = Match(sport=Sport.MLB, competition_id=comp.id, season="2041", utc_date=U + timedelta(days=day),
                      status=MatchStatus.SCHEDULED, home_team_id=t[A[0]].id, away_team_id=t[B[0]].id,
                      external_ids={fb.SOURCE: gid})
            s.add(m)
            s.flush()
            ids[gid] = m.id
            made["matches"].append(m.id)
        before = {gid: (m_.status, m_.home_score, m_.away_score, m_.utc_date, m_.status_raw)
                  for gid, m_ in ((g, s.get(Match, i)) for g, i in ids.items())}
    games = [_g(2951, B, A, U, hr=7, ar=2),                          # reversed: Betas (our away) 7, Alphas 2
             _g(2952, C, B, U + timedelta(days=1, hours=1), hr=5, ar=0),   # neither: refused whole
             _g(2953, D, B, U + timedelta(days=2), hr=3, ar=1),      # a listing team not in the DB: by position
             _g(2954, A, B, U + timedelta(days=3), hr=4, ar=6)]      # the same pair: today's writes
    clubs = [{"id": i, "name": n, "code": None} for i, n in (A, B, C)]
    r = fb.sync_matches(FakeClient(clubs, games), "2041")
    assert r["orientation_reversed"] == [ids["2951"]] and r["teams_mismatch_refused"] == [ids["2952"]]
    assert r["updated"] == 3 and r["finished"] == 3
    with session_scope() as s:
        def row(gid):
            m = s.get(Match, ids[gid])
            return m.status, m.home_score, m.away_score, m.full_time_result
        assert row("2951") == (MatchStatus.FINISHED, 2, 7, Result.AWAY)              # by team: Betas won, away
        m2 = s.get(Match, ids["2952"])
        assert (m2.status, m2.home_score, m2.away_score, m2.utc_date, m2.status_raw) == before["2952"]   # untouched
        assert row("2953") == (MatchStatus.FINISHED, 3, 1, Result.HOME)              # today's behaviour
        assert row("2954") == (MatchStatus.FINISHED, 4, 6, Result.AWAY)
        assert (s.get(Match, ids["2951"]).home_team_id, s.get(Match, ids["2951"]).away_team_id) == \
            (s.get(Match, ids["2954"]).home_team_id, s.get(Match, ids["2954"]).away_team_id)   # never flipped
        made["teams"] += [x.id for x in s.execute(select(Team).where(Team.name.like("Probe295 %"))).scalars()
                          if x.id not in made["teams"]]


def test_the_mlb_fallback_receipt_prints_the_scores_by_team_line(monkeypatch):
    import cli as climod
    from src.adapters import api_baseball
    from src.ingestion import mlb_apisports as fb
    monkeypatch.setattr(api_baseball.APIBaseballClient, "from_env", classmethod(lambda cls: FakeClient([], [])))
    monkeypatch.setattr(fb, "sync_matches", lambda *a, **k: {
        "season": "2041", "window": [None, None], "provider_games": 2, "created": 0, "updated": 1,
        "linked_existing": 0, "finished": 1, "ambiguous": 0, "held_near_unkeyed": 0, "team_missing": 0,
        "exhibition_skipped": 0, "downgrade_refused": 0, "stage_null_created": 0, "status_vocab": {},
        "unmapped_status": {}, "known_limitation": "x", "dh_marked": [], "time_kept_statsapi": 0,
        "time_conflicts": [], "orientation_reversed": [7], "teams_mismatch_refused": [8, 9]})
    monkeypatch.setenv("SP_SKIP_FAMILIES", "MLB")
    out = CliRunner().invoke(climod.cli, ["sync-matches", "--competition", "MLB", "--season", "2041"])
    assert out.exit_code == 0, out.output
    lines = out.output.splitlines()
    assert "orientation_reversed 1: 7 · teams_mismatch_refused 2: 8, 9" in lines
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy" / "hosting"))
    import sp_run
    assert sp_run.sync_counts(lines)["scores_by_team"] == {"orientation_reversed": {"n": 1, "ids": ["7"]},
                                                           "teams_mismatch_refused": {"n": 2, "ids": ["8", "9"]}}
