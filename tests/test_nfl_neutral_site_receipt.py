"""NFL NEUTRAL-SITE RECEIPT (#608; ARCHITECT 2026-10-27, addendum 171 item 2): offline runs on a fake provider and a
throwaway SQLite file (opened mode=ro by the receipt), the payload caches in tmp_path; no network, nothing under data/."""
import dataclasses
import hashlib
import importlib.util
import json
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.timeutil import utc_naive_fromtimestamp

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("nsr", ROOT / "scripts" / "nfl_neutral_site_receipt.py")
nsr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nsr)

TEAMS = {1: "Jacksonville Jaguars", 2: "Houston Texans", 3: "New Orleans Saints", 4: "Pittsburgh Steelers",
         5: "Tie Team"}
EVERBANK, NRG, DOME, ACRISURE = ("EverBank Stadium", "Jacksonville"), ("NRG Stadium", "Houston"), \
    ("Caesars Superdome", "New Orleans"), ("Acrisure Stadium", "Pittsburgh")


def _ts(s):
    return int(datetime.fromisoformat(s + "+00:00").timestamp())


def _row(gid, ko, home, away, venue, *, status="FT", stage="Regular Season", score=(24, 17), venue_raw=None):
    g = {"id": gid, "stage": stage, "week": "Week 1", "status": {"short": status},
         "date": {"timestamp": _ts(ko), "date": ko[:10], "time": ko[11:16]}}
    if venue_raw is not None:
        g["venue"] = venue_raw
    elif venue is not None:
        g["venue"] = {"name": venue[0], "city": venue[1]}
    else:
        g["venue"] = {"name": None, "city": None}
    return {"game": g, "teams": {"home": {"id": home, "name": TEAMS[home]}, "away": {"id": away, "name": TEAMS[away]}},
            "scores": {"home": {"total": score[0] if status == "FT" else None},
                       "away": {"total": score[1] if status == "FT" else None}}}


G26 = [_row(101, "2026-09-13T17:00", 1, 4, EVERBANK), _row(102, "2026-09-20T17:00", 1, 3, EVERBANK),
       _row(103, "2026-09-13T17:00", 2, 1, NRG), _row(104, "2026-09-20T17:00", 2, 3, NRG),
       _row(105, "2026-09-27T17:00", 3, 2, DOME), _row(106, "2026-10-04T17:00", 3, 1, DOME),
       _row(107, "2026-09-27T17:00", 4, 2, ACRISURE), _row(108, "2026-10-04T17:00", 4, 3, ACRISURE),
       _row(120, "2026-10-18T13:30", 1, 2, ("Wembley Stadium", "London"), score=(31, 34)),        # Wembley
       _row(121, "2026-10-25T13:30", 3, 4, ("Stade de France", "Paris"), score=(10, 16)),         # Paris
       _row(122, "2026-10-11T17:00", 2, 4, ACRISURE),            # a home game moved to the away team's stadium
       _row(123, "2026-10-11T20:00", 4, 1, None),                # no venue served: UNKNOWN, never home
       _row(130, "2026-10-12T17:00", 5, 1, ("A Field", "X")), _row(131, "2026-10-19T17:00", 5, 3, ("B Field", "Y")),
       _row(140, "2026-08-06T00:00", 1, 3, ("Tom Benson Hall of Fame Stadium", "Canton"), stage="Pre Season"),
       _row(150, "2026-11-01T17:00", 4, 1, ("Estadio Azteca", "Mexico City"), status="NS"),       # scheduled
       "junk", {"game": {"id": 160}, "teams": "not an object"},
       _row(109, "2026-10-08T17:00", 4, 3, ACRISURE)]              # listed, not stored: team 4's home is 3 of 5
G24 = [_row(201, "2024-09-08T17:00", 1, 2, EVERBANK), _row(202, "2024-09-15T17:00", 1, 3, EVERBANK),
       _row(203, "2024-10-13T13:30", 1, 3, ("Tottenham Hotspur Stadium", "London"), score=(20, 27)),  # no stored id
       _row(204, "2024-11-17T17:00", 2, 4, NRG), _row(205, "2024-11-24T17:00", 2, 1, NRG),
       _row(206, "2024-12-01T17:00", 2, 3, ("Arena Corinthians", "Sao Paulo"))]                    # not stored
G23 = [_row(301, "2023-09-10T17:00", 3, 4, DOME), _row(302, "2023-09-17T17:00", 3, 1, DOME),
       _row(303, "2023-10-01T13:30", 3, 2, ("Wembley Stadium", "London"))]


def fake(calls, answers=None):
    answers = answers or {2026: (200, {}, G26), 2024: (200, {}, G24), 2023: (200, {}, G23)}

    def get(path, **p):
        calls.append((path, p))
        assert path == "games"
        return answers.get(p["season"], (200, {}, []))
    return get


@pytest.fixture
def iso(tmp_path, monkeypatch):
    from src.db import database
    from src.db.schema import Base, Competition, Match, MatchStatus, Odds, Prediction, Sport, Team
    db = tmp_path / "iso.db"
    eng = create_engine(f"sqlite:///{db}", future=True)
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True, expire_on_commit=False)
    monkeypatch.setattr(database, "SessionLocal", S)
    monkeypatch.setattr(database, "_engine", eng)
    monkeypatch.chdir(tmp_path)
    ids = {}
    with S() as s:
        c = Competition(sport=Sport.NFL, code="NFL", name="NFL", area="USA", type="LEAGUE")
        s.add(c)
        s.flush()
        tm = {}
        for pid, name in TEAMS.items():
            t = Team(sport=Sport.NFL, name=name, area="USA", external_ids={"api_american_football": str(pid)})
            s.add(t)
            s.flush()
            tm[pid] = t.id

        def add(r, season, ext=True):
            g = r["game"]
            ko = utc_naive_fromtimestamp(g["date"]["timestamp"])
            fin = g["status"]["short"] == "FT"
            m = Match(sport=Sport.NFL, competition_id=c.id, season=season, utc_date=ko, stage=g["stage"],
                      status=MatchStatus.FINISHED if fin else MatchStatus.SCHEDULED,
                      home_team_id=tm[r["teams"]["home"]["id"]], away_team_id=tm[r["teams"]["away"]["id"]],
                      home_score=r["scores"]["home"]["total"], away_score=r["scores"]["away"]["total"],
                      external_ids={"api_american_football": str(g["id"])} if ext else {})
            s.add(m)
            s.flush()
            ids[g["id"]] = m.id
            return m
        for r in G24[:5]:
            add(r, "2024", ext=r["game"]["id"] != 203)
        for r in G26[:16]:
            add(r, "2026")
        wem = ids[120]
        s.add(Prediction(match_id=wem, model_version="nfl_elo_v1", home_win_prob=0.6889, away_win_prob=0.3111,
                         computed_at=datetime(2026, 10, 18, 12, 55)))
        for sel, px in (("HOME", 1.70), ("AWAY", 2.25)):
            s.add(Odds(match_id=wem, bookmaker="bk1", market="1X2", selection=sel, price_decimal=px,
                       captured_at=datetime(2026, 10, 18, 12, 50)))
        s.commit()
    yield {"tmp": tmp_path, "db": db, "ids": ids}
    eng.dispose()


def run(iso, *args, calls=None, get=None, seasons="2023,2024,2026", code=0):
    out = []
    calls = [] if calls is None else calls
    argv = ["--seasons", seasons, "--save", str(iso["tmp"] / "pay"), "--games-cache", str(iso["tmp"] / "cov"), *args]
    assert nsr.main(argv, echo=out.append, get=get or fake(calls)) == code
    return "\n".join(out), calls


def _json(out):
    line = [x for x in out.splitlines() if x.startswith("NFL-NEUTRAL-SITE-RECEIPT ")][-1]
    return json.loads(line.split(" ", 1)[1])


def test_the_happy_path_names_wembley_and_paris_under_both_definitions(iso):
    out, calls = run(iso)
    assert len(calls) == 3                                        # one /games call per season
    assert "calls made 3 · answers read from the coverage receipt's cache 0" in out
    assert "rule: nfl-neutral-site-receipt (ARCHITECT 2026-10-27, addendum 171 item 2(a))" in out
    assert "N the named cases:" in out
    wem = [x for x in out.splitlines() if x.startswith("  Wembley:")][0]
    par = [x for x in out.splitlines() if x.startswith("  Paris:")][0]
    for line in (wem, par):
        assert "neither team's home YES · outside the home team's stadium YES" in line
    assert "'Wembley Stadium' (London)" in wem and "'Stade de France' (Paris)" in par
    # the home venue is the majority venue of the team's home games that season
    assert "home team's home venue 'EverBank Stadium' (2 of 3 home games listed; a venue served on 3)" in out
    assert "'Acrisure Stadium' (3 of 5 home games listed; a venue served on 4)" in out   # game 123: no venue
    j = _json(out)
    assert j["venue_served"] is True and j["named"]["Wembley"]["match_id"] == iso["ids"][120]
    assert j["counts"]["2026"]["neither"]["yes"] == 3 and j["counts"]["2026"]["outside"]["yes"] == 4


def test_law_1_the_keys_are_printed_before_any_venue_field(iso):
    out, _ = run(iso)
    k = out.index("KEYS of the first real game row (game 301)")
    assert '"game", "scores", "teams"' in out
    assert "its venue member (game.venue): [\"city\", \"name\"]" in out
    assert k < out.index("G the games meeting either definition") < out.index("C per season")


def test_item_c_each_row_says_which_definition_it_meets(iso):
    out, _ = run(iso)
    moved = [x for x in out.splitlines() if "game 122 " in x][0]
    assert moved.endswith("MEETS: outside the home team's stadium")    # the away team's stadium: not "neither"
    wem = [x for x in out.splitlines() if "game 120 " in x][0]
    assert wem.endswith("MEETS: neither team's home + outside the home team's stadium")
    assert "neither team's home no · outside the home team's stadium YES" in out


def test_law_4_a_missing_venue_or_home_venue_is_unknown_never_home(iso):
    out, _ = run(iso)
    assert "game 123 " not in out.split("C per season")[0]        # never listed as a neutral or an outside game
    unk = [x for x in out.splitlines() if "UNKNOWN under a definition" in x and "game 123" in x]
    assert unk and "game 130 Jacksonville Jaguars @ Tie Team" in unk[0]          # a tie for the most: UNKNOWN
    assert "home venue UNKNOWN for team id(s) 5: 5: a tie for the most" in out
    j = _json(out)
    assert j["counts"]["2026"]["neither"]["unknown"] == 3 and j["counts"]["2026"]["outside"]["unknown"] == 3


def test_item_b_2023_is_listed_from_the_provider_only_not_stored_not_walked(iso):
    out, _ = run(iso)
    block = out.split("game 303 ")[1].split("\n  [")[0]
    assert "not stored, not walked (ruling (b): the span is 2024 to date)" in block
    assert "DB:" not in block and "p_with" not in block
    assert "2023: listed 3" in out and "not stored, not walked (ruling (b))" in out
    assert [r for r in _json(out)["rows"] if r["season"] == 2023][0]["flag"] == "not stored, not walked"


def test_item_d_the_48_with_and_without_on_the_same_walk_state_reported_never_gated(iso):
    from src.walters.nfl_backtest import NFLEloConfig, _expected_home, _State, _update
    out, _ = run(iso)
    # the walk recomputed here over the same stored finished stream (preseason dropped), in stored order
    from src.db.database import readonly_scope
    from src.db.schema import Match
    from sqlalchemy import select
    with readonly_scope() as s:
        ms = sorted((m for m in s.execute(select(Match)).scalars() if m.status.name == "FINISHED"
                     and "pre" not in (m.stage or "").lower()), key=lambda m: (m.utc_date, m.id))
        cfg, st = NFLEloConfig(), _State()
        want = None
        for m in ms:
            if m.id == iso["ids"][120]:
                want = (_expected_home(cfg, st, m.home_team_id, m.away_team_id),
                        _expected_home(dataclasses.replace(cfg, home_advantage=0.0), st, m.home_team_id,
                                       m.away_team_id))
            _update(cfg, st, m.home_team_id, m.away_team_id, m.season, m.home_score, m.away_score)
    assert want[0] > want[1]
    line = [x for x in out.split("game 120 ")[1].splitlines() if "p_with" in x][0]
    assert f"p_with {want[0]:.4f} · p_without {want[1]:.4f} · delta {(want[1] - want[0]) * 100:+.2f}pp" in line
    assert "home_adv_applied 48.0" in line and "(walk recompute, counterfactual, no call)" in line
    assert "reported, never gated" in out and "PASS" not in out and "FAIL" not in out.replace("FAILED", "")


def test_how_it_was_priced_stored_prediction_close_and_result(iso):
    out, _ = run(iso)
    block = out.split("game 120 ")[1].split("\n  [")[0]
    assert "DB: by the provider game id (external_ids) · match" in block
    assert "stored: nfl_elo_v1 home_win_prob 0.6889 (computed_at 2026-10-18T12:55:00)" in block
    fair = (1 / 1.70) / (1 / 1.70 + 1 / 2.25)
    assert f"close HOME {fair:.4f} (books, book stamp age unknown h)" in block
    assert "result 34-31 (away-home) A · stored pick miss" in block
    assert "closing row: not read (no --exports)" in block
    paris = out.split("game 121 ")[1].split("\n  [")[0]
    assert "stored: no prediction stored" in paris and "close: none (no 1X2 odds stored)" in paris


def test_the_join_falls_back_to_season_teams_and_date_labelled_and_an_unstored_game_says_so(iso):
    out, _ = run(iso)
    b203 = out.split("game 203 ")[1].split("\n  [")[0]
    assert "by season + both teams' provider ids + kickoff date (no stored game id; labelled)" in b203
    assert "p_with" in b203
    b206 = out.split("game 206 ")[1].split("\n  [")[0]
    assert "DB: no stored match (not stored)" in b206 and "p_with" not in b206
    sched = out.split("game 150 ")[1].split("\n  [")[0]
    assert "v1: not walked (stored SCHEDULED, not a finished scored game)" in sched
    pre = out.split("game 140 ")[1].split("\n  [")[0]
    assert "preseason: not in v1's stream" in pre and "v1: not walked (preseason)" in pre


def test_exports_give_the_desk_row_and_the_void_rule(iso):
    ex = iso["tmp"] / "exports"
    ex.mkdir()
    row = {"match_id": iso["ids"][120], "utc_date": "2026-10-18T13:30:00", "home_team": TEAMS[1],
           "away_team": TEAMS[2], "home_adv_applied": 48.0,
           "prediction": {"model_version": "nfl_elo_v1", "home_win_prob": 0.6889},
           "market": {"fair_prob": {"HOME": 0.5697, "AWAY": 0.4303}},
           "desk": {"call": "PLAY", "pick": "HOME", "units": 0.5}}
    moved = {"match_id": iso["ids"][121], "utc_date": "2026-10-24T13:30:00", "home_team": TEAMS[3],
             "away_team": TEAMS[4]}
    (ex / "closing_NFL_2026-10-18T1330Z.json").write_text(json.dumps(
        {"closing": {"family": "NFL", "start": "2026-10-18T13:30:00"}, "predictions": [row]}))
    (ex / "closing_NFL_2026-10-24T1330Z.json").write_text(json.dumps(
        {"closing": {"family": "NFL", "start": "2026-10-24T13:30:00"}, "predictions": [moved]}))
    out, _ = run(iso, "--exports", str(ex))
    assert "S closing files" in out and "2 read · unreadable 0" in out
    assert ("closing row (run 2026-10-18T13:30Z): home_adv_applied 48.0 · home_win_prob 0.6889 · market HOME 0.5697 "
            "· desk call PLAY · pick HOME · units 0.5") in out
    assert "home_adv_applied not on the row · home_win_prob not on the row" in out
    assert "VOID: void: re-dated 2026-10-24 13:30Z → 2026-10-25 13:30Z" in out


def test_a_failed_read_is_failed_and_an_empty_answer_is_empty(iso):
    calls = []
    get = fake(calls, {2026: (200, {}, G26), 2024: (500, {}, []), 2023: (200, {}, [])})
    out, _ = run(iso, get=get)
    assert "2024: FAILED · one call: FAILED (2024 games list: HTTP 500)" in out
    assert "2023: empty · one call" in out
    assert "2024: FAILED - nothing classified (its rows never measured)" in out
    assert "2023: empty - nothing classified (the provider answered no rows)" in out
    assert "failed 1 · answered with no rows 1" in out
    j = _json(out)
    assert j["reads"] == {"2023": "empty", "2024": "FAILED", "2026": "ok"}
    assert j["counts"]["2024"] == {"state": "FAILED"} and j["counts"]["2023"] == {"state": "empty"}


def test_api_errors_are_a_failed_read_and_the_venue_is_not_measured_never_the_finding(iso):
    out, _ = run(iso, get=fake([], {2026: (200, {"token": "bad"}, G26)}), seasons="2026", code=2)
    assert "2026: FAILED" in out and "venue NOT MEASURED: FAILED [2026]" in out
    assert "that is the finding" not in out and "the provider serves no venue (" not in out
    j = _json(out)
    assert j["venue_served"] is None and j["venue"] == "NOT MEASURED" and j["reads"] == {"2026": "FAILED"}


def test_ruling_a_a_capped_or_all_empty_run_is_not_measured(iso):
    out, calls = run(iso, "--max-calls", "0", code=2)
    assert calls == [] and "venue NOT MEASURED: INCOMPLETE [2023, 2024, 2026]" in out
    assert "that is the finding" not in out and _json(out)["venue_served"] is None
    out, _ = run(iso, "--save", str(iso["tmp"] / "pay2"), get=fake([], {1999: (200, {}, [])}), code=2)  # all: no rows
    assert "venue NOT MEASURED: empty [2023, 2024, 2026]" in out and "that is the finding" not in out


def test_ruling_a_a_season_read_without_venue_does_not_speak_for_a_failed_season(iso):
    bare = [{**r, "game": {k: v for k, v in r["game"].items() if k != "venue"}} for r in G23]
    out, _ = run(iso, get=fake([], {2023: (200, {}, bare), 2024: (500, {}, []), 2026: (200, {"x": "quota"}, [])}),
                 code=2)
    assert "venue NOT MEASURED: FAILED [2024, 2026]" in out and "no venue name on the 3 rows read" in out
    assert "that is the finding" not in out and _json(out)["venue_served"] is None


def test_malformed_rows_are_counted_never_a_traceback(iso):
    out, _ = run(iso)
    assert "NOT THE PROVIDER'S ROW SHAPE 2 (counted, never classified)" in out
    assert _json(out)["counts"]["2026"]["malformed"] == 2
    bad = [_row(1, "2026-09-13T17:00", 1, 2, None, venue_raw=["a list"])] + G26[:9]
    out, _ = run(iso, "--save", str(iso["tmp"] / "pay2"), get=fake([], {2026: (200, {}, bad)}), seasons="2026")
    assert "venue member malformed (neither an object nor a string, or a name or city not a string): 1" in out


def test_the_call_cap_stops_cleanly_and_says_incomplete(iso):
    out, calls = run(iso, "--max-calls", "1")
    assert len(calls) == 1
    assert "2024: INCOMPLETE · not read: the call cap (1) reached" in out
    assert "2026: INCOMPLETE" in out and "2024: INCOMPLETE - nothing classified (its rows never measured)" in out


def test_a_rerun_reads_the_kept_payloads_and_the_coverage_cache_first(iso):
    run(iso)
    out, calls = run(iso, calls=[])
    assert calls == [] and "calls made 0 · answers read from the coverage receipt's cache 0 · from this receipt's " \
                           "kept payloads 3" in out
    cov = iso["tmp"] / "cov" / "2026"
    cov.mkdir(parents=True)
    (cov / "games_list.json").write_text(json.dumps(G26))
    out, calls = run(iso, calls=[], seasons="2026")
    assert calls == [] and "2026: ok · the coverage receipt's kept answer" in out
    assert "answers read from the coverage receipt's cache 1 · from this receipt's kept payloads 0" in out


def test_the_payload_cache_is_refused_under_data(iso, monkeypatch):
    monkeypatch.setattr(nsr, "ROOT", iso["tmp"])           # the repo's real data/ is never a possible write target
    target = iso["tmp"] / "data" / "nfl_neutral_site_payloads_test"
    out, calls = [], []
    assert nsr.main(["--save", str(target), "--seasons", "2026", "--games-cache", str(iso["tmp"] / "cov")],
                    echo=out.append, get=fake(calls)) == 2
    assert "REFUSED" in out[0] and "under data/" in out[0]
    assert calls == [] and not (iso["tmp"] / "data").exists()


def test_the_db_is_opened_read_only_and_a_missing_file_is_refused(iso, monkeypatch):
    before = hashlib.sha256(iso["db"].read_bytes()).hexdigest()
    run(iso)
    assert hashlib.sha256(iso["db"].read_bytes()).hexdigest() == before
    # --db: the same mode=ro open on a named file
    out, _ = run(iso, "--db", str(iso["db"]))
    assert "(mode=ro, --db" in out
    assert hashlib.sha256(iso["db"].read_bytes()).hexdigest() == before
    missing = iso["tmp"] / "nope.db"
    calls = []
    out, _ = run(iso, "--db", str(missing), calls=calls, code=2)
    assert "REFUSED: no DB file" in out and calls == [] and not missing.exists()
    from src.db import database
    monkeypatch.setattr(database, "SessionLocal",
                        sessionmaker(bind=create_engine(f"sqlite:///{missing}", future=True), future=True))
    out, _ = run(iso, calls=calls, code=2)
    assert "REFUSED" in out and calls == [] and not missing.exists()


def test_no_key_for_a_needed_call_is_refused(iso, monkeypatch):
    monkeypatch.setattr(nsr.probe, "KEY", "")

    def no_network(*a, **k):
        raise AssertionError("network")
    monkeypatch.setattr(nsr.probe, "get", no_network)        # a regression fails here, never calls out
    out = []
    assert nsr.main(["--seasons", "2026", "--save", str(iso["tmp"] / "pay"), "--games-cache",
                     str(iso["tmp"] / "cov")], echo=out.append) == 2
    assert any("REFUSED: seasons [2026] have no kept answer" in x for x in out)


def test_a_provider_with_no_venue_says_so_and_stops(iso):
    rows = [{**r, "game": {k: v for k, v in r["game"].items() if k != "venue"}} for r in G26[:10]]
    out, _ = run(iso, get=fake([], {2026: (200, {}, rows)}), seasons="2026")
    assert "its venue member: NONE (no venue key in the row or its game member)" in out
    assert ("the provider serves no venue (no venue name on any of 10 rows read; every season asked was read): "
            "nothing is classified; that is the finding (ruling (a))") in out
    assert "G the games" not in out and _json(out)["venue_served"] is False


# ------------------------------------------------------------------ review round: the majority, the join, the grade
def _team_row(gid, day, home, away, venue):
    return _row(gid, f"2026-{day}T17:00", home, away, venue)


def test_ruling_a_majority_is_over_all_listed_home_games_never_the_ones_with_a_venue(iso):
    wem = ("Wembley Stadium", "London")
    rows = [_team_row(500 + i, f"09-{10 + i:02d}", 1, 2, None) for i in range(7)] + \
        [_team_row(510, "10-18", 1, 2, wem)]                                  # 1 venue served of 8 home games
    c = nsr.classify(2026, rows + [_team_row(520, "09-01", 2, 1, NRG), _team_row(521, "09-02", 2, 1, NRG)])
    assert c["home_venue"][1]["key"] is None
    assert c["home_venue"][1]["why"] == "venue served on only 1 of 8 home games"
    g = [x for x in c["games"] if x["gid"] == 510][0]
    assert g["outside"] is None and g["neither"] is None                       # UNKNOWN, never "home"


def test_ruling_a_a_plurality_is_not_a_majority(iso):
    a, b, c_, d = ("A Field", "X"), ("B Field", "Y"), ("C Field", "Z"), ("D Field", "W")
    rows = [_team_row(600, "09-01", 5, 1, a), _team_row(601, "09-08", 5, 1, a), _team_row(602, "09-15", 5, 2, b),
            _team_row(603, "09-22", 5, 3, c_), _team_row(604, "09-29", 5, 4, d),
            # a majority with a venue-less game in the denominator: 3 of 5 holds
            _team_row(610, "09-01", 4, 1, ACRISURE), _team_row(611, "09-08", 4, 2, ACRISURE),
            _team_row(612, "09-15", 4, 3, ACRISURE), _team_row(613, "09-22", 4, 1, None),
            _team_row(614, "09-29", 4, 2, ("Estadio Azteca", "Mexico City"))]
    c = nsr.classify(2026, rows)
    assert c["home_venue"][5]["key"] is None
    assert c["home_venue"][5]["why"] == "no venue on more than half (the most 2 of 5)"
    assert all(g["outside"] is None and g["neither"] is None for g in c["games"] if g["home_id"] == 5)
    assert c["home_venue"][4]["key"] == "acrisure stadium" and c["home_venue"][4]["n"] == 3
    assert [g["outside"] for g in c["games"] if g["gid"] == 614] == [True]


def test_a_non_scalar_team_id_and_a_non_string_venue_are_counted_never_a_traceback(iso):
    bad_id = _row(700, "2026-09-13T17:00", 1, 2, EVERBANK)
    bad_id["teams"]["home"]["id"] = {"a": 1}
    bad_venue = _row(701, "2026-09-14T17:00", 1, 2, None, venue_raw={"name": {"en": "X"}, "city": ["c"]})
    assert nsr.venue_of(bad_venue) == ("malformed", None, None)
    out, _ = run(iso, get=fake([], {2026: (200, {}, [bad_id, bad_venue] + G26[:9])}), seasons="2026")
    assert "NOT THE PROVIDER'S ROW SHAPE 1" in out and "team id not a string or an integer" in out
    assert "venue member malformed (neither an object nor a string, or a name or city not a string): 1" in out
    k = _json(out)["counts"]["2026"]
    assert k["malformed"] == 1 and k["venue_malformed"] == 1
    assert "game 701 " not in out.split("C per season")[0]                    # UNKNOWN, never classified "home"


def _store(home, away, ko, ext, season="2024"):
    from src.db import database
    from src.db.schema import Competition, Match, MatchStatus, Sport, Team
    with database.SessionLocal() as s:
        tm = {t.name: t.id for t in s.query(Team)}
        c = s.query(Competition).one()
        m = Match(sport=Sport.NFL, competition_id=c.id, season=season, utc_date=datetime.fromisoformat(ko),
                  stage="Regular Season", status=MatchStatus.FINISHED, home_team_id=tm[TEAMS[home]],
                  away_team_id=tm[TEAMS[away]], home_score=24, away_score=17, external_ids=ext)
        s.add(m)
        s.commit()
        return m.id


def _block(out, gid):
    return out.split(f"game {gid} ")[1].split("\n  [")[0]


def _row_json(out, gid):
    return [r for r in _json(out)["rows"] if r["game_id"] == gid][0]


def test_the_join_refuses_two_matches_on_one_key(iso):
    a, b = _store(2, 3, "2024-12-01T17:00", {}), _store(2, 3, "2024-12-01T20:00", {})
    out, _ = run(iso)
    assert (f"DB: AMBIGUOUS by season + both teams' provider ids + kickoff date: matches {sorted([a, b])} (refused, "
            "never a guess)") in _block(out, 206)
    r = _row_json(out, 206)
    assert r["match_id"] is None and r["p_with"] is None


def test_the_join_refuses_a_provider_id_held_by_two_matches(iso):
    a = _store(2, 3, "2024-12-01T17:00", {"api_american_football": "206"})
    b = _store(2, 3, "2024-11-01T17:00", {"api_american_football": "206"})
    out, _ = run(iso)
    assert f"DB: AMBIGUOUS by the provider game id: matches {sorted([a, b])} (refused, never a guess)" in out
    assert _row_json(out, 206)["match_id"] is None


def test_the_join_by_a_previous_id_and_a_previous_id_on_two_matches_is_refused(iso):
    one = _store(2, 3, "2024-12-01T17:00", {"api_american_football": "9206", "api_american_football_prev": ["206"]})
    out, _ = run(iso)
    assert f"DB: by a previous provider id (a re-keyed match) · match {one}" in _block(out, 206)
    assert _row_json(out, 206)["p_with"] is not None
    # a second holder of the old id on another date: the key join alone would find `one` (no fall-through)
    two = _store(2, 3, "2024-11-01T17:00", {"api_american_football": "9207", "api_american_football_prev": ["206"]})
    out, _ = run(iso)
    assert (f"DB: AMBIGUOUS by a previous provider id: matches {sorted([one, two])} (refused, never a guess)"
            in _block(out, 206))
    assert _row_json(out, 206)["match_id"] is None


def test_the_join_falls_back_to_team_names_labelled(iso):
    from src.db import database
    from src.db.schema import Team
    with database.SessionLocal() as s:
        t = s.query(Team).filter(Team.name == TEAMS[3]).one()
        t.external_ids = {}
        s.commit()
    mid = _store(2, 3, "2024-12-01T17:00", {})
    out, _ = run(iso)
    assert (f"DB: by season + both team names + kickoff date (no stored game id; labelled) · match {mid}"
            in _block(out, 206))


def _predict(mid, p, at):
    from src.db import database
    from src.db.schema import Prediction
    with database.SessionLocal() as s:
        s.add(Prediction(match_id=mid, model_version="nfl_elo_v1", home_win_prob=p, away_win_prob=1 - p,
                         computed_at=at))
        s.commit()


def test_the_grade_log_loss_clv_and_void_unread_without_exports(iso):
    out, _ = run(iso)
    fair = round((1 / 1.70) / (1 / 1.70 + 1 / 2.25), 4)
    b = _block(out, 120)
    assert "void: not read (no --exports): any grade below is void unread" in b
    assert "stored pick miss · log-loss 1.1676 (void unread)" in b
    assert f"clv {round(0.6889 - fair, 4):+.4f}" in b
    assert "PRE-LIVE" not in b
    assert _row_json(out, 120)["void"] == "not read (no --exports)"           # never null, which reads "not void"


def test_a_pre_live_prediction_is_labelled_and_a_tie_is_a_push(iso):
    from src.db import database
    from src.db.schema import Match
    _predict(iso["ids"][203], 0.55, datetime(2024, 10, 12, 12, 0))
    with database.SessionLocal() as s:
        m = s.get(Match, iso["ids"][120])
        m.home_score, m.away_score = 24, 24
        s.commit()
    out, _ = run(iso)
    assert "stored: nfl_elo_v1 home_win_prob 0.5500 (computed_at 2024-10-12T12:00:00) · walk minus stored" in out
    assert "· PRE-LIVE (never pooled)" in _block(out, 203)
    assert "result 24-24 (away-home) PUSH · stored pick PUSH · log-loss 1.1676" in _block(out, 120)


def test_a_read_void_takes_the_game_out_of_the_grade(iso):
    _predict(iso["ids"][121], 0.6, datetime(2026, 10, 24, 12, 0))
    ex = iso["tmp"] / "exports"
    ex.mkdir()
    moved = {"match_id": iso["ids"][121], "utc_date": "2026-10-24T13:30:00", "home_team": TEAMS[3],
             "away_team": TEAMS[4]}
    (ex / "closing_NFL_2026-10-24T1330Z.json").write_text(json.dumps(
        {"closing": {"family": "NFL", "start": "2026-10-24T13:30:00"}, "predictions": [moved]}))
    out, _ = run(iso, "--exports", str(ex))
    paris = _block(out, 121)
    assert "VOID: void: re-dated" in paris and "stored: nfl_elo_v1 home_win_prob 0.6000" in paris
    assert "log-loss" not in paris and "clv" not in paris
    wem = _block(out, 120)
    assert "log-loss 1.1676 ·" in wem and "void unread" not in wem and _row_json(out, 120)["void"] is None


def test_a_named_case_whose_season_was_not_read_says_not_read(iso):
    out, _ = run(iso, get=fake([], {2024: (200, {}, G24), 2026: (500, {}, [])}), seasons="2024,2026")
    assert "Wembley (houston at jacksonville, 2026-10-18): not read: the 2026 /games read FAILED" in out
    assert _json(out)["named"]["Paris"] == "not read: the 2026 /games read FAILED"
    out, _ = run(iso, "--save", str(iso["tmp"] / "pay2"), seasons="2024")
    assert "Wembley (houston at jacksonville, 2026-10-18): not read: 2026 is not in --seasons" in out


def test_db_is_honoured_and_opened_mode_ro(iso, monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    from src.db import database
    from src.db.schema import Base
    other = iso["tmp"] / "other.db"
    eng = create_engine(f"sqlite:///{other}", future=True)
    Base.metadata.create_all(eng)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=eng, future=True))
    out, _ = run(iso)
    assert "NFL matches by season none" in out                                 # the app's (other) file
    before = hashlib.sha256(iso["db"].read_bytes()).hexdigest()
    out, _ = run(iso, "--db", str(iso["db"]), "--save", str(iso["tmp"] / "pay2"))
    assert "NFL matches by season 2024 5 (finished 5) · 2026 16 (finished 15)" in out   # the --db file's counts
    assert _row_json(out, 120)["match_id"] == iso["ids"][120]
    assert hashlib.sha256(iso["db"].read_bytes()).hexdigest() == before
    with nsr.ro_session(str(iso["db"])) as s:
        with pytest.raises(OperationalError, match="readonly database"):
            s.execute(text("CREATE TABLE x (a)"))
    assert hashlib.sha256(iso["db"].read_bytes()).hexdigest() == before
    eng.dispose()
