"""CUP LINEUP HISTORY (ARCHITECT 2026-10-15, addendum 74 item 1; addendum 71's Step B; #106): sync-lineups-history.

Every test runs on a throwaway DB of its own (fresh_db: the engine AND the mode=ro reader point at tmp_path) and the
real APIFootballAdapter parser (list_lineup_confirmed) behind a fake HTTP session: no network, no key, no data/.

THE KEPT ANSWERS (ARCHITECT 2026-10-16, addendum 83 item 5(c)): seven real /fixtures/lineups answers of 2026-10-16
13:19Z, byte for byte, are in tests/fixtures/lineups_history/ (its README). Six have lineups (CL 2025/26 x3, EFL 2026/27
x3), and one is the empty FAC answer, kept deliberately. The tests on them run the real parser over every kept side. The
synthetic payload below stays only for the shapes no kept answer holds: nameless slots, short sides, an unmapped side,
refusals and the cap."""
import hashlib
import json
from datetime import datetime
from pathlib import Path

import pytest
from click.testing import CliRunner
from sqlalchemy import func, inspect, select, text

SEASON = "2091/92"
HOME_SID, AWAY_SID = "9101", "9102"


def side(team_id, name, n_start=11, n_bench=7, nameless=0):
    xi = [{"player": {"id": 1000 + i, "name": f"{name} S{i}", "number": i + 1, "pos": "M", "grid": "1:1"}}
          for i in range(n_start)]
    xi += [{"player": {"id": None, "name": None, "number": None, "pos": None, "grid": None}} for _ in range(nameless)]
    bench = [{"player": {"id": 2000 + i, "name": f"{name} B{i}", "number": 30 + i, "pos": "D", "grid": None}}
             for i in range(n_bench)]
    return {"team": {"id": int(team_id), "name": name, "logo": "x", "colors": None},
            "coach": {"id": 5, "name": f"{name} Coach", "photo": "x"},
            "formation": "4-3-3", "startXI": xi, "substitutes": bench}


def payload(fixture_id, *sides):
    return {"get": "fixtures/lineups", "parameters": {"fixture": str(fixture_id)}, "errors": [],
            "results": len(sides), "paging": {"current": 1, "total": 1}, "response": list(sides)}


class Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body

    def raise_for_status(self):
        import requests
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)


def adapter_with(answers):
    """The real adapter (parser, _get, errors check) with its HTTP session answering from `answers`:
    {fixture id: payload dict | (status, body)}; every request is logged in .asked."""
    from src.adapters.api_football import APIFootballAdapter
    ad = APIFootballAdapter(api_key="k")
    ad._throttle = lambda: None
    ad.asked = []

    def get(url, params=None, timeout=None):
        fid = str((params or {}).get("fixture"))
        ad.asked.append(fid)
        a = answers[fid]
        return Resp(*a) if isinstance(a, tuple) else Resp(200, a)
    ad._session.get = get
    return ad


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """A throwaway DB of its own: the app's engine and the mode=ro reader both point at it."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db
    from src.walters import venue_quote_age
    path = tmp_path / "fresh.db"
    eng = create_engine(f"sqlite:///{path}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                         expire_on_commit=False))
    monkeypatch.setattr(venue_quote_age, "db_file_path", lambda: path)
    db.init_db()
    return eng


def seed(code="CL", n=1, season=SEASON, fixture_ids=None, home_ext=None, away_ext=None):
    """One competition, two teams, n FINISHED fixtures (match ids returned)."""
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus, Sport, Team
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == code)).scalar_one_or_none()
        if comp is None:
            comp = Competition(sport=Sport.SOCCER, code=code, name=code, area="EU", type="CUP")
            s.add(comp)
        h = Team(sport=Sport.SOCCER, name=f"{code} Home", external_ids=home_ext or {"api_football": HOME_SID})
        a = Team(sport=Sport.SOCCER, name=f"{code} Away", external_ids=away_ext or {"api_football": AWAY_SID})
        s.add_all([h, a])
        s.flush()
        ids = []
        for i in range(n):
            fid = (fixture_ids or [f"77{i}"])[i] if fixture_ids is not False else None
            m = Match(sport=Sport.SOCCER, competition_id=comp.id, season=season, utc_date=datetime(2091, 9, 1 + i, 19),
                      status=MatchStatus.FINISHED, home_team_id=h.id, away_team_id=a.id, home_score=1, away_score=0,
                      external_ids={"api_football": fid} if fid else {})
            s.add(m)
            s.flush()
            ids.append(m.id)
        return ids, h.id, a.id


def rows(eng, kind="history"):
    with eng.connect() as c:
        return c.execute(text("SELECT match_id, team_id, kind, is_starter, player_name, source FROM lineups "
                              "WHERE kind = :k ORDER BY id"), {"k": kind}).all()


def counts(eng):
    with eng.connect() as c:
        return {t: c.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar() for t in inspect(eng).get_table_names()}


def run(ad, *a, **k):
    from src.ingestion.lineups_history import run_lineups_history
    out = []
    r = run_lineups_history(*a, echo=out.append, adapter=ad, **k)
    return r, out


def test_the_payload_carries_every_key_the_adapter_reads():
    from src.ingestion.lineups_history import KEYS
    p = payload(770, side(HOME_SID, "H"), side(AWAY_SID, "A"))
    assert KEYS["response"] in p and KEYS["errors"] in p
    for b in p[KEYS["response"]]:
        assert KEYS["team_id"] in b[KEYS["team"]] and KEYS["formation"] in b
        for slot in b[KEYS["starters"]] + b[KEYS["bench"]]:
            assert {KEYS["name"], KEYS["pos"], KEYS["number"]} <= set(slot[KEYS["player"]])


def test_a_run_stores_both_elevens_and_the_bench_as_history_and_a_rerun_asks_nothing(fresh_db):
    (mid,), hid, aid = seed()
    ad = adapter_with({"770": payload(770, side(HOME_SID, "H"), side(AWAY_SID, "A", n_bench=5))})
    r, out = run(ad, "CL", SEASON, max_calls=5)
    stored = rows(fresh_db)
    assert len(stored) == 11 + 7 + 11 + 5 and {x.kind for x in stored} == {"history"}
    assert {x.source for x in stored} == {"api_football"} and {x.match_id for x in stored} == {mid}
    assert sum(1 for x in stored if x.team_id == hid and x.is_starter) == 11
    assert sum(1 for x in stored if x.team_id == aid and not x.is_starter) == 5
    assert rows(fresh_db, "confirmed") == []                    # never confirmed: the live factor reads that kind
    assert (f"  COVERAGE CL {SEASON}: fixtures with both elevens 1 / fixtures 1 · one 0 · none 0 · failed 0 · "
            "not asked 0 · no fixture id 0") in out
    assert "  stored: 34 row(s) on 2 side(s) of 1 fixture(s) written · both elevens already stored (skipped, no " \
           "call) 0" in out
    assert "  calls 1 of 5 · HTTP requests 200 ×1" in out
    assert any("rows carry the ingest time only (refreshed_at)" in o for o in out)
    before = counts(fresh_db)
    r2, out2 = run(adapter_with({}), "CL", SEASON, max_calls=5)    # idempotent: the stored fixture is skipped
    assert (r2.calls, r2.already, counts(fresh_db)) == (0, 1, before)
    assert any(o.startswith(f"  COVERAGE CL {SEASON}: fixtures with both elevens 1 / fixtures 1") for o in out2)


def test_a_dry_run_writes_nothing_and_says_what_would_be_stored(fresh_db):
    seed()
    before = counts(fresh_db)
    ad = adapter_with({"770": payload(770, side(HOME_SID, "H"), side(AWAY_SID, "A"))})
    r, out = run(ad, "CL", SEASON, dry_run=True, max_calls=5)
    assert counts(fresh_db) == before and r.calls == 1
    assert out[0].endswith("DRY RUN: nothing is written · max calls 5")
    assert any(o.startswith("  plan (no call yet): finished fixtures 1 · no fixture id 0 · both elevens already "
                            "stored 0 · to ask 1 · calls a whole run needs 1") for o in out)
    assert any(o.startswith("  would be stored: 36 row(s) on 2 side(s)") for o in out)
    assert any("fixtures with both elevens 1 / fixtures 1" in o and "(a dry run: the table plus what would be "
               "stored)" in o for o in out)


def test_a_dry_run_reads_without_a_lineups_table_and_a_real_run_refuses(fresh_db):
    from src.ingestion.lineups_history import Refused
    seed()
    with fresh_db.begin() as c:
        c.execute(text("DROP TABLE lineups"))                   # the test's own throwaway DB
    r, _ = run(adapter_with({"770": payload(770, side(HOME_SID, "H"), side(AWAY_SID, "A"))}), "CL", SEASON,
               dry_run=True)
    assert r.both == 1 and not inspect(fresh_db).has_table("lineups")
    with pytest.raises(Refused, match="no lineups table"):
        run(adapter_with({}), "CL", SEASON)


def test_the_cap_stops_cleanly_between_fixtures_and_the_next_run_finishes(fresh_db):
    ids, _, _ = seed(n=3, fixture_ids=["770", "771", "772"])
    answers = {f: payload(f, side(HOME_SID, "H"), side(AWAY_SID, "A")) for f in ("770", "771", "772")}
    r, out = run(adapter_with(answers), "CL", SEASON, max_calls=2)
    assert r.calls == 2 and {x.match_id for x in rows(fresh_db)} == set(ids[:2])
    assert out[-1] == (f"  STOPPED at the cap (2 calls) before match {ids[2]} (fixture 772); 1 fixture(s) not asked: "
                       "the next run asks them and skips the stored ones")
    assert any("fixtures with both elevens 2 / fixtures 3 · one 0 · none 0 · failed 0 · not asked 1" in o for o in out)
    ad = adapter_with(answers)
    r2, _ = run(ad, "CL", SEASON, max_calls=2)
    assert ad.asked == ["772"] and r2.already == 2 and r2.both == 1


def test_an_empty_answer_and_nameless_blocks_are_none_and_asked_again(fresh_db):
    seed(n=2, fixture_ids=["770", "771"])
    answers = {"770": payload(770), "771": payload(771, side(HOME_SID, "H", 0, 0, nameless=11),
                                                    side(AWAY_SID, "A", 0, 0, nameless=11))}
    r, out = run(adapter_with(answers), "CL", SEASON)
    assert rows(fresh_db) == [] and sum(r.none.values()) == 2
    assert "    none, by why: an empty answer 1 · team blocks with no named slot 1" in out
    ad = adapter_with(answers)
    run(ad, "CL", SEASON)
    assert ad.asked == ["770", "771"]                           # nothing records an answer that stored nothing


def test_a_nameless_answer_never_replaces_a_stored_eleven_and_is_counted_and_listed(fresh_db):
    """ARCHITECT 2026-10-16, addendum 98 item 1: a later NAMELESS answer for a side never replaces an eleven stored
    from an earlier named answer; the receipt counts such sides and lists the fixture ids; completeness reads from the
    stored rows. A side with no stored rows that answers nameless stays unstored."""
    ids, home, away = seed(n=1, fixture_ids=["770"])
    first, out = run(adapter_with({"770": payload(770, side(HOME_SID, "H"), side(AWAY_SID, "A", 0, 0, nameless=11))}),
                     "CL", SEASON)
    assert first.one == 1 and "  answered nameless, earlier eleven kept: 0" in out    # the away side: never stored

    def table():
        with fresh_db.connect() as c:
            return c.execute(text("SELECT * FROM lineups ORDER BY id")).all()
    before = table()
    assert len(before) == 18 and {r.team_id for r in rows(fresh_db)} == {home}
    again, out = run(adapter_with({"770": payload(770, side(HOME_SID, "H", 0, 0, nameless=11),
                                                  side(AWAY_SID, "A", 0, 0, nameless=11))}), "CL", SEASON)
    assert table() == before                                     # every row as it was: ids and ingest time included
    assert (again.both, again.one, dict(again.none), again.rows) == (0, 1, {}, 0)   # still one: the stored eleven
    assert "  answered nameless, earlier eleven kept: 1 · fixture ids 770" in out
    assert f"    match {ids[0]} (fixture 770): team {home} kept its stored eleven; the answer's block for it had no " \
           "named slot" in out
    assert [(f.fixture_id, tid) for f, tid in again.nameless_kept] == [("770", home)]


def test_one_side_short_of_eleven_is_one_and_an_unmapped_side_is_never_matched_by_name(fresh_db):
    ids, _, _ = seed(n=2, fixture_ids=["770", "771"])
    answers = {"770": payload(770, side(HOME_SID, "H"), side(AWAY_SID, "A", n_start=10)),
               "771": payload(771, side("5555", "Elsewhere"), side("5556", "Nowhere"))}
    r, out = run(adapter_with(answers), "CL", SEASON)
    assert (r.both, r.one, dict(r.none)) == (0, 1, {"a side that maps to neither team": 1})
    assert {x.match_id for x in rows(fresh_db)} == {ids[0]}


def test_a_merged_teams_recorded_id_maps_its_side(fresh_db):
    """#467: a team row answers to the provider ids a merge recorded on it (team_merge.source_ids)."""
    seed(home_ext={"api_football": "1", "api_football_also": [HOME_SID]})
    r, _ = run(adapter_with({"770": payload(770, side(HOME_SID, "H"), side(AWAY_SID, "A"))}), "CL", SEASON)
    assert r.both == 1


def test_a_payload_error_stops_the_run_and_a_server_error_is_listed_and_passed(fresh_db):
    ids, _, _ = seed(n=4, fixture_ids=["770", "771", "772", "773"])
    answers = {"770": payload(770, side(HOME_SID, "H"), side(AWAY_SID, "A")),
               "771": (500, {}),
               "772": {"errors": {"requests": "You have reached the request limit for the day"}, "response": []},
               "773": payload(773, side(HOME_SID, "H"), side(AWAY_SID, "A"))}
    ad = adapter_with(answers)
    r, out = run(ad, "CL", SEASON)
    assert ad.asked == ["770", "771", "772"] and {x.match_id for x in rows(fresh_db)} == {ids[0]}
    assert (r.both, len(r.failed), r.not_asked) == (1, 2, 1)
    assert f"  ✗ match {ids[1]} (fixture 771): status 500" in out
    assert out[-1].startswith(f"  STOPPED at a payload error on match {ids[2]} (fixture 772): API-Football error:")
    assert out[-1].endswith("1 fixture(s) not asked: the next run asks them and skips the stored ones")
    assert "  calls 3 of 100 · HTTP requests 200 ×2 · 500 ×1" in out


def test_other_kinds_on_the_same_match_are_never_touched(fresh_db):
    from src.db.database import session_scope
    from src.db.schema import Lineup
    (mid,), hid, _ = seed()
    with session_scope() as s:
        s.add(Lineup(match_id=mid, team_id=hid, kind="confirmed", player_name="Kept Player", is_starter=True))
        s.add(Lineup(match_id=mid, team_id=hid, kind="history", player_name="Stale", is_starter=True))
    run(adapter_with({"770": payload(770, side(HOME_SID, "H"), side(AWAY_SID, "A"))}), "CL", SEASON)
    assert [x.player_name for x in rows(fresh_db, "confirmed")] == ["Kept Player"]
    assert "Stale" not in {x.player_name for x in rows(fresh_db)}  # the side's history rows are rewritten whole


def test_a_bare_start_year_reads_as_the_stored_season(fresh_db):
    seed(season="2091/92")
    r, out = run(adapter_with({"770": payload(770, side(HOME_SID, "H"), side(AWAY_SID, "A"))}), "CL", "2091")
    assert r.season == "2091/92" and "(--season 2091 read as '2091/92', the adapter's rule)" in out[0]


def test_the_refusals_come_before_any_call(fresh_db):
    from src.ingestion.lineups_history import Refused
    seed(code="CL", season="2090/91")
    with pytest.raises(Refused, match="not one of CL, UEL, EFL, FAC"):
        run(adapter_with({}), "PL", SEASON)
    with pytest.raises(Refused, match=r"CL holds no finished fixture under season '2091/92' \(finished fixtures by "
                                      r"stored season: 2090/91 1\)"):
        run(adapter_with({}), "CL", SEASON)
    with pytest.raises(Refused, match="competition FAC is not in the DB"):
        run(adapter_with({}), "FAC", SEASON)
    seed(code="EL", season=SEASON)                              # the Europa League stored under EL
    with pytest.raises(Refused, match="EL holds 1 finished fixture"):
        run(adapter_with({}), "UEL", SEASON)


def test_save_keeps_each_answer_whole_and_never_under_data(fresh_db, tmp_path):
    from src.ingestion.lineups_history import Refused
    seed()
    p = payload(770, side(HOME_SID, "H"), side(AWAY_SID, "A"))
    run(adapter_with({"770": p}), "CL", SEASON, dry_run=True, save=str(tmp_path / "kept"))
    assert json.loads((tmp_path / "kept" / "770.json").read_text()) == p
    from src.walters.unl_ladders import data_dir
    with pytest.raises(Refused, match="reaches data/"):
        run(adapter_with({}), "CL", SEASON, dry_run=True, save=str(data_dir() / "kept"))
    assert not (data_dir() / "kept").exists()


def test_save_keeps_a_payload_error_answer_whole_before_the_run_stops(fresh_db, tmp_path):
    """Codex on #538: a 200 whose errors block is set (a quota or plan refusal) makes the adapter raise before it
    returns; --save still keeps that answer whole, and the run still stops on it."""
    ids, _, _ = seed(n=2, fixture_ids=["770", "771"])
    refusal = {"get": "fixtures/lineups", "parameters": {"fixture": "770"}, "response": [], "results": 0,
               "errors": {"plan": "Free plans do not have access to this season, try from 2022 to 2024."}}
    r, out = run(adapter_with({"770": refusal, "771": payload(771, side(HOME_SID, "H"), side(AWAY_SID, "A"))}),
                 "CL", SEASON, dry_run=True, save=str(tmp_path / "kept"))
    assert json.loads((tmp_path / "kept" / "770.json").read_text()) == refusal
    assert not (tmp_path / "kept" / "771.json").exists() and r.not_asked == 1         # the run stopped on it
    assert out[-1].startswith(f"  STOPPED at a payload error on match {ids[0]} (fixture 770): API-Football error:")


def test_save_keeps_an_http_error_answers_body_whether_the_run_stops_or_moves_on(fresh_db, tmp_path, monkeypatch):
    """#565 (Codex on #538, round 2): a 401, 403, 429 or 5xx answer's decoded body is kept under --save, in the
    HTTPError branch, before the run stops (429 after the adapter's own retry) or moves on (5xx)."""
    import src.adapters.api_football as af
    monkeypatch.setattr(af.time, "sleep", lambda s: None)             # the adapter's 60 s wait before its 429 retry
    ids, _, _ = seed(n=3, fixture_ids=["770", "771", "772"])
    down = {"message": "upstream timeout", "errors": {"server": "try again later"}}
    limited = {"message": "Too many requests. Your rate limit is 10 requests per minute."}
    p772 = payload(772, side(HOME_SID, "H"), side(AWAY_SID, "A"))
    ad = adapter_with({"770": (500, down), "771": (429, limited), "772": p772})
    r, out = run(ad, "CL", SEASON, dry_run=True, save=str(tmp_path / "kept"))
    assert json.loads((tmp_path / "kept" / "770.json").read_text()) == down        # listed, and the run moved on
    assert json.loads((tmp_path / "kept" / "771.json").read_text()) == limited     # kept before the run stopped
    assert not (tmp_path / "kept" / "772.json").exists() and r.not_asked == 1
    assert ad.asked == ["770", "771", "771"]                                      # the adapter's one 429 retry
    assert out[-1].startswith(f"  STOPPED at status 429 on match {ids[1]} (fixture 771)")
    assert "  calls 2 of 100 · HTTP requests 429 ×2 · 500 ×1" in out


def test_each_fixtures_rows_carry_the_time_they_were_stored(fresh_db, monkeypatch):
    """#565 (Codex on #538, round 2): refreshed_at is taken per fixture, just before its store, never once for the
    whole run."""
    from datetime import timedelta

    import src.timeutil as tu
    ids, _, _ = seed(n=2, fixture_ids=["770", "771"])
    t0, n = datetime(2091, 10, 1, 12), {"calls": 0}

    def tick():
        n["calls"] += 1
        return t0 + timedelta(minutes=n["calls"])
    monkeypatch.setattr(tu, "utc_now_naive", tick)
    run(adapter_with({"770": payload(770, side(HOME_SID, "H"), side(AWAY_SID, "A")),
                      "771": payload(771, side(HOME_SID, "H"), side(AWAY_SID, "A"))}), "CL", SEASON)
    with fresh_db.connect() as c:
        got = c.execute(text("SELECT match_id, COUNT(DISTINCT refreshed_at), MAX(refreshed_at) FROM lineups "
                             "WHERE kind = 'history' GROUP BY match_id ORDER BY match_id")).all()
    assert [(m, k) for m, k, _ in got] == [(ids[0], 1), (ids[1], 1)]  # one time per fixture, on every row of it
    assert got[0][2] < got[1][2]                                      # the second fixture's time is its own, later


def test_save_refuses_a_symlink_into_data_and_allows_a_sibling_named_like_it(fresh_db, tmp_path, monkeypatch):
    """The review on #538: a path reaching data/ through a symlink is refused by file identity; a directory whose
    name merely starts with 'data' is not data/. data_dir() is pointed at a stand-in under tmp_path (the test never
    touches the real data/)."""
    import src.walters.unl_ladders as ul
    from src.ingestion.lineups_history import Refused, refuse_save_dir
    fake = tmp_path / "repo" / "data"
    fake.mkdir(parents=True)
    monkeypatch.setattr(ul, "data_dir", lambda: fake.resolve())
    (tmp_path / "link").symlink_to(fake)
    with pytest.raises(Refused, match="reaches data/"):
        refuse_save_dir(str(tmp_path / "link" / "kept"))
    with pytest.raises(Refused, match="reaches data/"):
        refuse_save_dir(str(fake))
    refuse_save_dir(str(tmp_path / "repo" / "data-kept"))         # a sibling: allowed
    assert not (fake / "kept").exists()


def test_the_cli_command_refuses_with_exit_2_and_names_the_four(fresh_db):
    import cli
    res = CliRunner().invoke(cli.cli, ["sync-lineups-history", "--competition", "PL", "--season", SEASON])
    assert res.exit_code == 2 and "'CL', 'UEL', 'EFL', 'FAC'" in res.output
    res = CliRunner().invoke(cli.cli, ["sync-lineups-history", "--competition", "FAC", "--season", SEASON])
    assert res.exit_code == 2 and res.output.startswith("REFUSED: competition FAC is not in the DB")


def test_only_the_lineups_table_changes(fresh_db):
    seed()
    before = counts(fresh_db)
    run(adapter_with({"770": payload(770, side(HOME_SID, "H"), side(AWAY_SID, "A"))}), "CL", SEASON)
    after = counts(fresh_db)
    assert {t for t in after if after[t] != before[t]} == {"lineups"}
    with fresh_db.connect() as c:
        assert c.execute(select(func.count()).select_from(text("lineups"))).scalar() == 36


# --- --since (ARCHITECT 2026-10-16 09:22 ET, addendum 83 item 5(b)) ---------------------------------------------------
# "#538 takes `--since YYYY-MM-DD` (fixtures on or after the date) and FAC 2025/26 is pulled --since 2025-11-01 (the
# First Round Proper); the receipt prints the fixtures left out by it."

def test_since_asks_only_the_fixtures_on_or_after_it_and_lists_every_one_left_out(fresh_db):
    from datetime import date
    mids, hid, aid = seed(code="FAC", n=4, fixture_ids=["770", "771", "772", "773"])    # 2091-09-01 .. 09-04, 19:00Z
    ad = adapter_with({f: payload(int(f), side(HOME_SID, "H"), side(AWAY_SID, "A")) for f in ("772", "773")})
    r, out = run(ad, "FAC", SEASON, max_calls=10, since=date(2091, 9, 3))
    assert ad.asked == ["772", "773"] and r.calls == 2                   # the two before it are never asked
    assert {x.match_id for x in rows(fresh_db)} == set(mids[2:])
    assert out[0].endswith("· --since 2091-09-03: fixtures on or after it only")
    assert ("  --since 2091-09-03: finished fixtures 4 · on or after it 2 · left out 2 (never asked, never counted "
            "below; every one is listed at the end of the receipt)") in out
    assert (f"  COVERAGE FAC {SEASON}: fixtures with both elevens 2 / fixtures 2 · one 0 · none 0 · failed 0 · "
            "not asked 0 · no fixture id 0") in out
    i = out.index("  LEFT OUT by --since 2091-09-03: 2 finished fixture(s) before it, never asked")
    assert out[i + 1:] == [f"    match {mids[0]} (fixture 770, 2091-09-01) · teams {hid} v {aid}",
                           f"    match {mids[1]} (fixture 771, 2091-09-02) · teams {hid} v {aid}"]


def test_since_is_on_or_after_the_kickoffs_utc_date_and_an_unknown_kickoff_is_left_out():
    from datetime import date

    from src.ingestion.lineups_history import Fixture, split_since
    fx = [Fixture(1, "1", datetime(2025, 10, 31, 23, 59), 1, 2, {}),
          Fixture(2, "2", datetime(2025, 11, 1, 0, 0), 1, 2, {}),
          Fixture(3, "3", None, 1, 2, {}),
          Fixture(4, "4", datetime(2025, 11, 2, 15), 1, 2, {})]
    keep, out = split_since(fx, date(2025, 11, 1))
    assert [f.match_id for f in keep] == [2, 4] and [f.match_id for f in out] == [1, 3]
    assert split_since(fx, None) == (fx, [])


def test_without_since_nothing_is_left_out_and_the_receipt_says_nothing_of_it(fresh_db):
    seed(n=2, fixture_ids=["770", "771"])
    ad = adapter_with({f: payload(int(f), side(HOME_SID, "H"), side(AWAY_SID, "A")) for f in ("770", "771")})
    r, out = run(ad, "CL", SEASON, max_calls=10)
    assert r.calls == 2 and r.left_out == [] and not any("since" in o.lower() for o in out)


def test_the_cli_reads_since_as_a_date_and_refuses_another_shape(fresh_db, monkeypatch):
    import cli
    from src.ingestion import lineups_history as lh
    seen = {}

    def fake(code, season, **k):
        seen.update(k)
    monkeypatch.setattr(lh, "run_lineups_history", fake)
    res = CliRunner().invoke(cli.cli, ["sync-lineups-history", "--competition", "FAC", "--season", "2025",
                                       "--since", "2025-11-01", "--dry-run"])
    assert res.exit_code == 0, res.output
    from datetime import date
    assert seen["since"] == date(2025, 11, 1)
    res = CliRunner().invoke(cli.cli, ["sync-lineups-history", "--competition", "FAC", "--season", "2025",
                                       "--since", "01/11/2025"])
    assert res.exit_code == 2 and "--since" in res.output


# --- the kept answers (ARCHITECT 2026-10-16, addendum 83 item 5(c); tests/fixtures/lineups_history/README.md) ----------

FIX = Path(__file__).parent / "fixtures" / "lineups_history"
KEPT = {"1383422": ("CL", "1165", "691"), "1383423": ("CL", "3502", "375"), "1383424": ("CL", "3684", "579"),
        "1554097": ("EFL", "1381", "1339"), "1554098": ("EFL", "1828", "1362"), "1567390": ("EFL", "56", "1342")}
EMPTY = "1419290"                                                   # FAC 2025/26, kept deliberately
SHA256 = {"1383422": "e9e0091464ed4304d75020f21ea531c5fc7b4e16e430ebb4d646455a26d55491",
          "1383423": "05aa094db0d47de521525a842d4c2241e0e906f44f0a7c50f81e8aad5d2c22c8",
          "1383424": "1301e5fc131337087e697e5d2233e7f549f4d5d6ddfba532673fc948584d9755",
          "1554097": "f344111122772e8bdb663c672c7f7c23e5cbb0eb7543d88aff08970a269e6e28",
          "1554098": "c6ceaca714494a4e4aba99c14fbfd48745075fb14f78373c622d9ee1a1fe426a",
          "1567390": "5a5d47df558d93d77768b98a93cdde3326d77673965e15c877f7f11545ba09a4",
          "1419290": "93cd7347f373b5f90c06f80a54fa7d4ab3c8de16f48e6002ebd0ed9d0c03874a"}


def kept(fid):
    return json.loads((FIX / f"{fid}.json").read_text())


def test_the_kept_answers_are_the_operators_bytes_and_carry_every_key_the_adapter_reads():
    from src.ingestion.lineups_history import ELEVEN, KEYS
    assert sorted(p.stem for p in FIX.glob("*.json")) == sorted([*KEPT, EMPTY])
    for fid, sha in SHA256.items():                     # byte for byte the operator's kept files (df877e3)
        assert hashlib.sha256((FIX / f"{fid}.json").read_bytes()).hexdigest() == sha, fid
    for fid, (_code, h, a) in KEPT.items():
        p = kept(fid)
        assert p[KEYS["errors"]] == [] and p["parameters"] == {"fixture": fid}
        assert [str(b[KEYS["team"]][KEYS["team_id"]]) for b in p[KEYS["response"]]] == [h, a]
        for b in p[KEYS["response"]]:
            assert KEYS["formation"] in b and len(b[KEYS["starters"]]) == ELEVEN and b[KEYS["bench"]]
            for slot in b[KEYS["starters"]] + b[KEYS["bench"]]:
                assert {KEYS["name"], KEYS["pos"], KEYS["number"]} <= set(slot[KEYS["player"]])
                assert slot[KEYS["player"]][KEYS["name"]].strip()               # every kept slot is named
    assert sum(b[KEYS["formation"]] is None for fid in KEPT for b in kept(fid)[KEYS["response"]]) == 3
    e = kept(EMPTY)
    assert (e[KEYS["response"]], e["results"], e[KEYS["errors"]]) == ([], 0, [])


def test_the_kept_answers_store_both_elevens_and_every_bench_and_a_null_formation_stays_null(fresh_db):
    seeded = {}
    for fid, (code, h, a) in KEPT.items():
        (mid,), hid, aid = seed(code, fixture_ids=[fid], home_ext={"api_football": h}, away_ext={"api_football": a})
        seeded[fid] = (mid, {h: hid, a: aid})
    answers = {fid: kept(fid) for fid in KEPT}
    for code, rows_, sides in (("CL", 37 + 46 + 45, 6), ("EFL", 38 + 40 + 40, 6)):
        r, out = run(adapter_with(answers), code, SEASON, max_calls=10)
        assert (f"  COVERAGE {code} {SEASON}: fixtures with both elevens 3 / fixtures 3 · one 0 · none 0 · failed 0 "
                "· not asked 0 · no fixture id 0") in out, out
        assert (f"  stored: {rows_} row(s) on {sides} side(s) of 3 fixture(s) written · both elevens already stored "
                "(skipped, no call) 0") in out, out
    with fresh_db.connect() as c:
        stored = c.execute(text("SELECT match_id, team_id, is_starter, formation, player_position, player_name "
                                "FROM lineups WHERE kind = 'history'")).all()
    for fid, (mid, by_provider) in seeded.items():
        for b in kept(fid)["response"]:
            tid = by_provider[str(b["team"]["id"])]
            mine = [x for x in stored if x.match_id == mid and x.team_id == tid]
            assert sum(1 for x in mine if x.is_starter) == 11 and len(mine) == 11 + len(b["substitutes"]), fid
            assert {x.formation for x in mine} == {b["formation"]}, fid          # a null formation stays null
            names = {s["player"]["name"] for s in b["startXI"] + b["substitutes"]}
            assert {x.player_name for x in mine} == names, fid
    assert sum(1 for x in stored if x.formation is None) == (11 + 11) + (11 + 9) + (11 + 9)   # 579, 1828, 1362
    assert sum(1 for x in stored if x.player_position is None) == 6


def test_the_kept_empty_answer_is_none_an_empty_answer_and_stores_nothing(fresh_db):
    seed("FAC", fixture_ids=[EMPTY])
    before = counts(fresh_db)
    r, out = run(adapter_with({EMPTY: kept(EMPTY)}), "FAC", SEASON, max_calls=5)
    assert counts(fresh_db) == before and r.calls == 1
    assert (f"  COVERAGE FAC {SEASON}: fixtures with both elevens 0 / fixtures 1 · one 0 · none 1 · failed 0 · "
            "not asked 0 · no fixture id 0") in out
    assert "    none, by why: an empty answer 1" in out
