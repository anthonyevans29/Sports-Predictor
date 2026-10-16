"""CUP LINEUP HISTORY (ARCHITECT 2026-10-15, addendum 74 item 1; addendum 71's Step B; #106): sync-lineups-history.

Every test runs on a throwaway DB of its own (fresh_db: the engine AND the mode=ro reader point at tmp_path) and the
real APIFootballAdapter parser (list_lineup_confirmed) behind a fake HTTP session: no network, no key, no data/.

THE PAYLOAD IS SYNTHETIC FOR NOW: no real /fixtures/lineups answer is kept in the repo (the 2026-10-14 probe kept
summaries only). Its shape is the adapter's keys (lineups_history.KEYS) in the envelope the Step A tests use. The kept
real answers the ruling asks for come from the operator's capped dry run with --save; they replace PAYLOAD under
tests/fixtures/lineups_history/ before this leaves draft."""
import json
from datetime import datetime

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
