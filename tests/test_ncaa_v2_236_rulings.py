"""#816, THE SEVEN, RULED (ARCHITECT 2026-11-03, addendum 236 item 3). Pins, on the shadow's synthetic world and
synthetic payloads only (no real DB, no network):
(1) the neutral flag: CFBD's pregame field, read at the labels ingest (a not-completed both-FBS game joined by the exact
    name tier only; never a label, never coverage), on every row in the ruled form, and priced EXACTLY as the gate's
    walk prices it: a neutral fixture's shadow probability equals NeutralRuleElo at s walked over the stream, then the
    prediction with the flag True; a non-neutral one with the flag False; a stale or absent row is unknown (D8);
(2) the close: the Kalshi close is THE close, per name; the D4 baseline a second REFERENCE name on the same games
    (0.5 at a CFBD-neutral site), never a verdict's input; the book close a reference line; the 2023 / 2026 fences
    apply to the Kalshi block until the run and its verdict are recorded;
(3) the confirmation fixture: D7's count beside the 100; the record on the counted members holding a prospective
    row; every member without one named, unscored (another fixture's row, an early-tag kickoff);
(4) the order: ncaa-schedule's export runs after a failed refresh-by-id (exit the first failure's, the step named),
    a failed listing read still stops it; the rows carry the refresh they saw; a D6 drop after a PASS exits 2, never
    DORMANT;
(5) the host fence: refused (exit 2) before any read on a laptop, an unset or a bad role; --dry-run prints and
    writes nothing;
(6) legs captured before the boundary (2026-10-14T04:00:00Z, addendum 239 item 4) never enter the Kalshi
    grade, its legs guard included;
(7) one registry source: frozen(), the counter and coverage read registry.LEDGER at call time."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner

from src.db.database import session_scope
from src.db.schema import Match, MatchStatus, NCAACFBDLabel, NCAACFBDPregame, OddsSnapshot
from src.ingestion import ncaa_cfbd as nc
from src.walters import ncaa_backtest as nb
from src.walters import ncaa_shadow as sh
from src.walters import registry as reg
from tests.test_ncaa_cfbd_scope_join import KEYS, ours, rec
from tests.test_ncaa_shadow import NOW, _fbs, mine, world  # noqa: F401  (fixtures: the shadow's synthetic world)
from tests.test_ncaa_v2_shadow import _v2_registry
from tests.test_hosting_pack import receipts, sandbox  # noqa: E402,F401  (the sp_run sandbox: tmp receipts/lock)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))
STEP = ["export-ncaa-predictions", "--id", "ncaa-elo-v2", "--dormant-ok"]
RUN = {"run_at": "2026-11-09T12:00:00Z", "n_scored": 0, "ids_file": None, "result": {"baseline_home_rate": 0.6}}


def _registry(tmp_path, name="r.json", verdict="PASS", run=RUN):
    """A v2 registry the export accepts (PASS, s, rule, v1's constants), with the run record when `run`."""
    p = Path(_v2_registry(tmp_path, verdict=verdict, name=name))
    e = json.loads(p.read_text())
    if run is not None:
        e[0]["run"] = run
    p.write_text(json.dumps(e))
    return str(p)


@pytest.fixture
def host(monkeypatch):
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "host")


def _pregame(mid, neutral, at=NOW, orientation="same", season="2026"):
    with session_scope() as s:
        cur = s.get(NCAACFBDPregame, mid)
        if cur is not None:
            s.delete(cur)
            s.flush()
        s.add(NCAACFBDPregame(match_id=mid, source="cfbd", source_game_id=mid, season=season, orientation=orientation,
                              neutral=neutral, fetched_at=at))


@pytest.fixture
def clean(mine):
    yield mine
    with session_scope() as s:
        ids = [mine["up"], *mine["finished"]]
        s.query(NCAACFBDPregame).filter(NCAACFBDPregame.match_id.in_(ids)).delete(synchronize_session=False)
        s.query(OddsSnapshot).filter(OddsSnapshot.match_id.in_(ids), OddsSnapshot.source == "kalshi").delete(
            synchronize_session=False)


# ------------------------------------------------------------------------------------------------ (1) --

def _walk_price(neutral):
    """The gate's walk (ncaa_v1r_gate.model_for: NeutralRuleElo at the frozen s) over the stream before NOW, then the
    prediction of the upcoming fixture as a Game carrying `neutral` (the stream's field)."""
    m = nb.NeutralRuleElo(False, scale=sh.V2_FROZEN_S)
    sh.walk(m, nb.load_v1r_stream().games, NOW)
    return m


def test_1_a_neutral_fixtures_shadow_probability_equals_the_gate_walks(clean, tmp_path):
    t = clean["teams"]
    reg_ = _registry(tmp_path)
    prices = {}
    for flag in (True, False, None):
        if flag is None:
            with session_scope() as s:
                s.query(NCAACFBDPregame).filter(NCAACFBDPregame.match_id == clean["up"]).delete()
        else:
            _pregame(clean["up"], flag)
        _, doc = sh.export(now=NOW, out_dir=str(tmp_path / f"o{flag}"), registry_path=reg_, eid=sh.V2_EID)
        (r,) = doc["predictions"]
        p = r["prediction"]
        m = _walk_price(flag)
        want = m.predict(nb.Game(t[0], t[1], "2026", NOW + timedelta(hours=5), 0, 0, "Regular Season",
                                 neutral=flag))
        assert p["home_win_prob"] == round(want, 4)                      # exactly the walk's treatment of the field
        assert p["home_adv_applied"] == m.home_adv(nb.Game(1, 2, "2026", NOW, 0, 0, neutral=flag))
        assert p["neutral"] is flag
        assert p["neutral_rule"] == ("neutral per CFBD's pregame field, read 2034-06-01T12:00:00; "
                                     "absent: unknown, D8")               # the ruled form, every row
        prices[flag] = p["home_win_prob"]
        assert doc["fit"]["neutral_pregame"] == {True: {"neutral": 1}, False: {"not_neutral": 1},
                                                 None: {"unknown_no_row": 1}}[flag]
    assert prices[True] != prices[False] == prices[None]                  # only True moves the price (no more)
    with session_scope() as s:
        assert s.get(NCAACFBDLabel, clean["up"]) is None                  # never a label


def test_1_flag_labels_and_the_parity_receipt_pins_the_pregame_flag(clean, tmp_path):
    _pregame(clean["up"], True)
    p = sh.export(now=NOW, out_dir=str(tmp_path), registry_path=_registry(tmp_path), eid=sh.V2_EID)[1][
        "predictions"][0]["prediction"]
    assert (p["neutral_flag"], p["neutral_source"], p["home_adv_applied"]) == (
        "neutral (CFBD's pregame field)", "cfbd_pregame", 0.0)
    assert p["home_adv_basis"].startswith("home advantage 0: CFBD's pregame field says neutral")
    r = sh.parity(sh.synthetic_stream())
    assert r["neutral_scored"] > 0 and r["pregame_flag_unequal"] == 0 and r["pregame_flag_max_diff"] <= sh.PARITY_TOL


def test_1_a_stale_pregame_row_reads_unknown(clean, tmp_path):
    _pregame(clean["up"], True, at=NOW - timedelta(days=3))              # an earlier read: not the latest record's
    _, doc = sh.export(now=NOW, out_dir=str(tmp_path), registry_path=_registry(tmp_path), eid=sh.V2_EID)
    p = doc["predictions"][0]["prediction"]
    assert p["neutral"] is None and p["neutral_flag"] == "absent: unknown, D8" and p["home_adv_applied"] == 55.0
    assert doc["fit"]["neutral_pregame"] == {"unknown_stale_row": 1}


TEAMS = {1: "PG Alpha", 2: "PG Beta", 3: "PG Gamma", 4: "PG Delta", 5: "PG Epsilon State"}


def _pg_ours():
    return [ours(10, TEAMS, 1, 2, datetime(2084, 9, 6, 19), 31, 10),
            ours(11, TEAMS, 3, 4, datetime(2084, 10, 4, 19), None, None),
            ours(12, TEAMS, 5, 1, datetime(2084, 10, 11, 19), None, None),
            ours(13, TEAMS, 2, 3, datetime(2084, 10, 18, 19), None, None)]


def test_1_the_ingest_reads_the_pregame_field_exact_tier_only_never_a_label():
    done = rec(9601, "PG Alpha", "PG Beta", 31, 10, "2084-09-06T19:00:00Z")
    pre = [rec(9602, "PG Gamma", "PG Delta", None, None, "2084-10-04T19:00:00Z", neutral=True, completed=False),
           rec(9603, "PG Epsilon", "PG Alpha", None, None, "2084-10-11T19:00:00Z", completed=False),  # substring only
           rec(9604, "PG Gamma", "PG FCS", None, None, "2084-10-11T19:00:00Z", ac="fcs", completed=False),
           rec(9605, "PG Gamma", "PG Beta", None, None, "2084-10-18T19:00:00Z", neutral=None, completed=False)]
    our = sorted(_pg_ours(), key=lambda m: (m.utc_date, m.id))
    base = nc.build_labels([done], KEYS, our, TEAMS, {}, 2084, "fbs")
    r = nc.build_labels([done, *pre], KEYS, our, TEAMS, {}, 2084, "fbs")
    assert [x["match_id"] for x in r.rows] == [10] == [x["match_id"] for x in base.rows]     # labels unchanged
    assert (r.counts["completed_in_scope"], r.counts["joined"]) == (base.counts["completed_in_scope"],
                                                                    base.counts["joined"]) == (1, 1)
    assert r.unlabelled == base.unlabelled                                # the coverage fact is untouched
    got = {x["match_id"]: (x["neutral"], x["orientation"], x["join_via"]) for x in r.pregame_rows}
    assert got == {11: (True, "same", "exact"), 13: (None, "swapped", "exact")}
    c = r.counts
    assert (c["pregame_in_scope"], c["pregame_joined"], c["pregame_unmatched"], c["pregame_out_of_scope"]) == (
        3, 2, 1, 1)                                                       # the substring-only fit never joins
    assert (c["pregame_neutral"], c["pregame_neutral_unknown"], c["pregame_joined_swapped"]) == (1, 1, 1)
    assert any(x.startswith("    PREGAME NEUTRAL FLAG (addendum 236 item 3(1)") for x in nc.receipt_lines(r))


def test_1_the_migration_marker_gates_the_pregame_write_and_the_labels_still_write(tmp_path, monkeypatch, capsys):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import migrate_ncaa_cfbd_pregame as mig
    import migrate_ncaa_cfbd_week as mig_week
    import src.db.database as db
    from tests.test_ncaa_cfbd_week import RECS, _migrated_to_v2, _payload

    eng = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                         expire_on_commit=False))
    ms = _migrated_to_v2(eng)
    assert mig_week.main() == 0
    with session_scope() as s:
        fx = s.get(Match, ms["reg"])
        up = Match(sport=fx.sport, competition_id=fx.competition_id, season="2084", utc_date=datetime(2084, 10, 4, 19),
                   status=MatchStatus.SCHEDULED, home_team_id=fx.home_team_id, away_team_id=fx.away_team_id,
                   stage=fx.stage)
        s.add(up)
        s.flush()
        up_id = up.id
        assert not nc.pregame_migrated(s)                                 # init_db()'s table is not the migration
    homes = {r_["id"]: r_ for r_ in RECS}
    f = _payload(tmp_path, monkeypatch, RECS + [rec(9510, homes[9501]["homeTeam"], homes[9501]["awayTeam"], None,
                                                    None, "2084-10-04T19:00:00.000Z", neutral=True,
                                                    completed=False)])
    lines = []
    assert nc.run([2084], from_file=str(f), out=lines.append) == 0
    out = "\n".join(lines)
    assert "NOT WRITTEN ncaa_cfbd_pregame: no migration marker ncaa_cfbd_pregame_migration" in out
    assert "WRITTEN ncaa_cfbd_labels: inserted 2" in out                  # the labels are written as before
    with session_scope() as s:
        assert nc.pregame_flags(s, [up_id]) == {}
    capsys.readouterr()
    assert mig.main() == 0 and "+ Wrote migration marker ncaa_cfbd_pregame_migration" in capsys.readouterr().out
    assert mig.main() == 0 and "· Kept migration marker" in capsys.readouterr().out          # idempotent
    lines = []
    assert nc.run([2084], from_file=str(f), out=lines.append) == 0
    assert any("WRITTEN ncaa_cfbd_pregame: inserted 1" in x for x in lines)
    with session_scope() as s:
        flags = nc.pregame_flags(s, [up_id])
        assert flags[up_id]["neutral"] is True and flags[up_id]["current"] is True
        assert s.get(NCAACFBDLabel, up_id) is None                        # never a label
    db.drop_db()                                                          # init-db --force drops the marker too
    with eng.connect() as conn:
        from sqlalchemy import inspect
        assert not inspect(conn).has_table(nc.PREGAME_MIGRATION_MARKER)
    eng.dispose()


# ------------------------------------------------------------------------------------------- (2) (6) --

def _kalshi(s, mid, bid, ask, at):
    s.add(OddsSnapshot(match_id=mid, market="ML", selection="HOME", devig_prob=(bid + ask) / 2, n_books=0,
                       captured_at=at, source="kalshi", yes_bid=bid, yes_ask=ask))


@pytest.fixture
def finished_up(clean, tmp_path, monkeypatch):
    """The v2 file for `up` exported on a PASS registry with its run, then `up` finished (home won 31-13, labelled),
    a two-sided pre-kickoff Kalshi quote 0.70/0.72."""
    ex = tmp_path / "ex"
    reg_ = _registry(tmp_path)
    monkeypatch.setattr(reg, "LEDGER", reg_)
    _, doc = sh.export(now=NOW, out_dir=str(ex), eid=sh.V2_EID)
    up = clean["up"]
    with session_scope() as s:
        m = s.get(Match, up)
        m.status, m.home_score, m.away_score = MatchStatus.FINISHED, 31, 13
        s.add(NCAACFBDLabel(match_id=up, source="cfbd", source_game_id=up, season="2026", orientation="same",
                            neutral=False, home_score=31, away_score=13, fetched_at=NOW))
        _kalshi(s, up, 0.70, 0.72, NOW + timedelta(hours=4))
    yield {"ex": str(ex), "p": doc["predictions"][0]["prediction"]["home_win_prob"], "up": up, "reg": reg_}
    with session_scope() as s:
        lab = s.get(NCAACFBDLabel, up)
        if lab is not None:
            s.delete(lab)
        m = s.get(Match, up)
        m.status, m.home_score, m.away_score = MatchStatus.SCHEDULED, None, None


def _grade(x):
    return sh.grade(days=3650, export_dir=x["ex"], now=NOW + timedelta(days=1), eid=sh.V2_EID)


def test_2_the_kalshi_close_is_the_close_and_d4_a_reference_name_on_the_same_games(finished_up):
    from src.walters.vs_close import block

    r = _grade(finished_up)
    v = r["vs_kalshi_close"]
    assert set(v) == {"ncaa_elo_v2", sh.D4_REF_NAME}                      # per name, never pooled
    assert v["ncaa_elo_v2"] == block([(finished_up["p"], 0.71)])
    assert v[sh.D4_REF_NAME] == block([(0.6, 0.71)])                     # the run's frozen rate, non-neutral
    assert v["ncaa_elo_v2"]["games"] == v[sh.D4_REF_NAME]["games"] == 1
    assert v["ncaa_elo_v2"]["model_log_loss"] != v[sh.D4_REF_NAME]["model_log_loss"]
    assert "never a verdict's input" in r["references"][sh.D4_REF_NAME]
    assert r["references"]["book_close"].startswith("reference: the book close")
    assert "(THE close)" in r["lines"][0] and "reference book close_H=" in r["lines"][0]
    with session_scope() as s:                                            # a CFBD-neutral label: 0.5
        s.get(NCAACFBDLabel, finished_up["up"]).neutral = True
    assert _grade(finished_up)["vs_kalshi_close"][sh.D4_REF_NAME] == block([(0.5, 0.71)])


def test_2_the_fences_apply_to_both_kalshi_names_until_the_run_and_its_verdict(finished_up, tmp_path, monkeypatch):
    for name, verdict, run in (("norun.json", "PASS", None), ("noverdict.json", None, RUN)):
        monkeypatch.setattr(reg, "LEDGER", _registry(tmp_path, name=name, verdict=verdict, run=run))
        assert sh.kalshi_fenced() is True
        r = _grade(finished_up)
        assert r["kalshi_close_excluded"]["fenced_2026"] == 1
        assert r["vs_kalshi_close"]["ncaa_elo_v2"]["games"] == 0
        assert r["vs_kalshi_close"].get(sh.D4_REF_NAME, {"games": 0})["games"] == 0
    monkeypatch.setattr(reg, "LEDGER", finished_up["reg"])
    assert sh.kalshi_fenced() is False and _grade(finished_up)["kalshi_close_excluded"]["fenced_2026"] == 0


def test_2_the_d4_reference_never_feeds_a_verdict():
    """Nothing that records a verdict or a confirmation reads the shadow's grade or its reference name."""
    for mod in ("src/walters/ncaa_v1r_gate.py", "src/walters/registry.py"):
        src = (ROOT / mod).read_text()
        assert "vs_kalshi_close" not in src and "D4_REF_NAME" not in src and "d4_baseline (reference)" not in src
        assert "ncaa_shadow import grade" not in src and "confirmation_record" not in src


def test_6_legs_before_the_boundary_never_enter_the_kalshi_grade(finished_up):
    """Item 3(6), its boundary per addendum 239 item 4 (the repo record names no deploy instant for the tag carrying #475:
    2026-10-14T04:00:00Z). tests/test_ncaa_v2_239_rulings.py pins the second before and the instant."""
    up = finished_up["up"]
    with session_scope() as s:
        s.query(OddsSnapshot).filter(OddsSnapshot.match_id == up, OddsSnapshot.source == "kalshi").delete()
        _kalshi(s, up, 0.50, 0.52, datetime(2026, 10, 12, 23, 59))       # before #475's switch: never read
    r = _grade(finished_up)
    assert r["kalshi_close_excluded"][sh.LEGS_BEFORE] == 1 and r["vs_kalshi_close"]["ncaa_elo_v2"][
        "games"] == 0
    assert ("legs placed before 2026-10-14T04:00:00Z (2026-10-14 00:00 ET) were the old path's (#475's switch to the "
            "shared pair) and never enter it, the close nor its legs guard") in r["kalshi_close_rule"]
    with session_scope() as s:                                            # the old 00:00 ET floor: now before
        _kalshi(s, up, 0.55, 0.57, datetime(2026, 10, 13, 4, 0))
    r = _grade(finished_up)
    assert r["kalshi_close_excluded"][sh.LEGS_BEFORE] == 1
    assert sh.KALSHI_LEGS_FROM == datetime(2026, 10, 14, 4, 0)           # 2026-10-14 00:00 ET, naive UTC
    with session_scope() as s:
        _kalshi(s, up, 0.60, 0.62, datetime(2026, 10, 14, 4, 0))         # at the boundary: read
    r = _grade(finished_up)
    assert r["kalshi_close_excluded"][sh.LEGS_BEFORE] == 0
    assert "kalshi_close_H=0.610" in r["lines"][0]


def _ticker_column():
    from sqlalchemy import inspect as _inspect
    from sqlalchemy import text

    from src.db.database import get_engine

    eng = get_engine()
    if "market_ticker" not in {c["name"] for c in _inspect(eng).get_columns("odds_snapshots")}:
        with eng.begin() as conn:                                         # what migrate_kalshi_ticker.py does
            conn.execute(text("ALTER TABLE odds_snapshots ADD COLUMN market_ticker VARCHAR(64)"))


def _leg(s, mid, sel, bid, ask, at, ticker):
    from sqlalchemy import text

    x = OddsSnapshot(match_id=mid, market="ML", selection=sel, devig_prob=(bid + ask) / 2, n_books=0,
                     captured_at=at, source="kalshi", yes_bid=bid, yes_ask=ask)
    s.add(x)
    s.flush()
    s.execute(text("UPDATE odds_snapshots SET market_ticker = :t WHERE id = :i"), {"t": ticker, "i": x.id})


def test_6_legs_before_the_day_never_reach_the_legs_guard(finished_up, clean):
    """Item 3(6): earlier placements never enter the Kalshi grade, the legs guard included: a pre-switch leg on one
    side of the game itself (another event), and a pre-switch leg of the game's own event placed on another game
    (the #413 class), both leave a game whose post-switch legs are clean priced."""
    _ticker_column()
    up = finished_up["up"]
    ev = "KXNCAAFGAME-34JUN01AB"
    with session_scope() as s:
        s.query(OddsSnapshot).filter(OddsSnapshot.match_id == up, OddsSnapshot.source == "kalshi").delete()
        _leg(s, up, "HOME", 0.70, 0.72, NOW + timedelta(hours=4), ev + "-A")
    r = _grade(finished_up)
    assert r["vs_kalshi_close"]["ncaa_elo_v2"]["games"] == 1 and r["kalshi_close_excluded"]["mismatched"] == 0
    other = next(m for m in clean["finished"] if m != up)
    with session_scope() as s:
        _leg(s, up, "AWAY", 0.28, 0.30, datetime(2026, 10, 10, 12, 0), "KXNCAAFGAME-26OCT10OLDEVT-B")   # own, earlier
        ko = s.get(Match, other).utc_date
        _leg(s, other, "HOME", 0.50, 0.52, min(ko - timedelta(hours=1), datetime(2026, 10, 12, 12, 0)),
             ev + "-A")                                                   # this event on another game, earlier
    with session_scope() as s:                                            # the unfloored guard would exclude it
        from src.walters import kalshi_legs
        assert up in kalshi_legs.mismatched(s, [up])
        assert kalshi_legs.mismatched(s, [up], sh.KALSHI_LEGS_FROM) == {}
    r = _grade(finished_up)
    assert r["vs_kalshi_close"]["ncaa_elo_v2"]["games"] == 1, r["kalshi_close_excluded"]
    assert r["kalshi_close_excluded"]["mismatched"] == 0 and "kalshi_close_H=0.710" in r["lines"][0]
    with session_scope() as s:
        s.query(OddsSnapshot).filter(OddsSnapshot.match_id.in_([up, other]),
                                     OddsSnapshot.source == "kalshi").delete(synchronize_session=False)


# ------------------------------------------------------------------------------------------------ (3) --

def _file(d, at, rows, name):
    d.mkdir(exist_ok=True)
    (d / f"ncaa_shadow_{name}.json").write_text(json.dumps({
        "engine": "model_shadow", "competition": "NCAA", "registry_id": "ncaa-elo-v2", "exported_at": at,
        "predictions": rows}))


def test_3_the_record_is_on_counted_members_with_a_prospective_row_the_rest_named(clean, tmp_path, monkeypatch):
    from src.walters import ncaa_v1r_gate as g
    from src.walters.vs_close import block
    from tests.test_ncaa_v2_confirmation_machinery import _row

    monkeypatch.setattr(reg, "LEDGER", _registry(tmp_path))
    a, b, c, d = clean["finished"][-4:]                                   # 2026, labelled, 24-17 home wins
    e = clean["up"]                                                       # pending
    count = {"n": 4, "scored_ids": [a, b, c, d], "cohort_ids": [a, b, c, d, e], "n_games": 100, "bar": 0.69,
             "cohort_state": "provisional", "cohort_size": 5, "eligible_stored": 5, "release_due": 0,
             "complete": False, "pending": [{"id": e, "status": "scheduled"}]}
    monkeypatch.setattr(g, "confirmation_count", lambda spec, path=None: dict(count))
    ex = tmp_path / "ex"
    with session_scope() as s:
        pa = {**_row(s, a), "prediction": {"home_win_prob": 0.65}}
        pb = {**_row(s, b, home_team="NSH Team 4"), "prediction": {"home_win_prob": 0.6}}   # another fixture's row
        pc = {**_row(s, c), "prediction": {"home_win_prob": 0.6}}
        pd = {**_row(s, d), "prediction": {"home_win_prob": 0.55}}
        c_ko = s.get(Match, c).utc_date
        _kalshi(s, a, 0.60, 0.62, s.get(Match, a).utc_date - timedelta(hours=1))
    _file(ex, "2034-01-02T00:00:00", [pa, pb], "2034-01-02_000000")
    # the early tag: the file carrying c's row is written after c kicked off, so c has no prospective row
    _file(ex, (c_ko + timedelta(hours=12)).isoformat(), [pc, pd], "2034-02-02_120000")
    x = sh.confirmation_record(export_dir=str(ex))
    assert (x["count"], x["n_games"], x["counted_with_row"]) == (4, 100, 2)          # the COUNT stays D7's
    assert x["record"]["ncaa_elo_v2"] == block([(0.65, 0.61)])                       # a priced; d: no close
    assert x["record"][sh.D4_REF_NAME] == block([(0.6, 0.61)])
    assert x["record_excluded"]["no_close"] == 1
    named = {n["id"]: (n["why"], n["counted"]) for n in x["no_prospective_row"]}
    assert named == {b: ("no prospective row (a row of another fixture)", True), c: ("no prospective row", True),
                     e: ("no prospective row", False)}
    assert (x["no_prospective_row_counted"], x["no_prospective_row_pending"]) == (2, 1)
    L = sh.record_lines(x, sh.V2_EID)
    assert L[0].startswith("confirmation record ncaa-elo-v2 (ARCHITECT 2026-11-03, addendum 236 item 3(3)): count "
                           "4/100 (D7's) · record against THE close (Kalshi) on 2 counted members holding a "
                           "prospective row · no prospective row: 2 of the counted (unscored) and 1 pending")
    assert any(f"no prospective row: match {c} " in ln for ln in L) and L[0].endswith("a record, not a verdict")


# ------------------------------------------------------------------------------------------------ (4) --

FAKE_NCAA_CLI = """import sys
a = sys.argv[1:]
print("ran", " ".join(a))
if a[0] == "refresh-by-id" or (a[0] == "sync-matches" and "{fail}" == "listing"):
    print("RuntimeError: provider read failed")
    sys.exit(1)
"""


def test_4_the_export_runs_after_a_failed_refresh_and_the_exit_is_the_refreshs(sandbox, capsys):
    """Addendum 236 item 3(4): "the export runs whether or not refresh-by-id succeeded [...]; the refresh failure
    pages as now." The real ncaa-schedule chain on a fake cli.py: refresh-by-id exits 1, the export still runs, the
    chain exits 1 (OnFailure pages) and names the step; a failed listing read still stops the chain."""
    import sp_common as c
    import sp_run

    (c.REPO / "cli.py").write_text(FAKE_NCAA_CLI.replace("{fail}", "refresh"))
    assert sp_run.main(["ncaa-schedule"]) == 1                                    # the refresh's exit: it pages
    out = capsys.readouterr().out
    rs = receipts(sandbox)
    steps = [r for r in rs if r["kind"] == "step"]
    assert [s_["command"].split()[2] for s_ in steps][-2:] == ["refresh-by-id", "export-ncaa-predictions"]
    assert steps[-2]["exit"] == 1 and steps[-2]["continued"] == sp_run.CHAIN_GO_ON and steps[-1]["exit"] == 0
    chain = [r for r in rs if r["kind"] == "chain"][-1]
    assert chain["failed_steps"] == [{"step": 9, "command": "python cli.py refresh-by-id --competition NCAA --days 7",
                                      "exit": 1}] and chain["stopped_at"] is None
    assert "ran export-ncaa-predictions --id ncaa-elo-v2 --dormant-ok" in out
    assert "✗ step 9/10 exit=1: python cli.py refresh-by-id --competition NCAA --days 7" in out
    # a failed listing read (sync-matches) still stops the chain before the export: only refresh-by-id goes on
    (c.REPO / "cli.py").write_text(FAKE_NCAA_CLI.replace("{fail}", "listing"))
    assert sp_run.main(["ncaa-schedule"]) == 1
    chain = [r for r in receipts(sandbox) if r["kind"] == "chain"][-1]
    assert chain["stopped_at"] == 1 and "ran export-ncaa-predictions" not in capsys.readouterr().out
    # another chain without go_on: the same failing refresh stops it
    rep = {}
    (c.REPO / "cli.py").write_text(FAKE_NCAA_CLI.replace("{fail}", "refresh"))
    rc, ok = sp_run.run_steps([["refresh-by-id", "--competition", "NCAA"], ["export-ncaa-predictions"]], "t", "u",
                              "r", datetime(2026, 11, 3).date(), sp_run.new_quota(), report=rep)
    assert (rc, ok, rep["stopped_at"]) == (1, 0, 1)


def _receipt(tmp_path, *recs):
    p = tmp_path / "receipts.jsonl"
    p.write_text("".join(json.dumps(x) + "\n" for x in recs))
    return p


def test_4_the_rows_carry_the_refresh_they_saw(clean, tmp_path, monkeypatch):
    base = {"kind": "refresh_by_id", "competition": "NCAA", "now": "x", "selected": 9, "updated": 2,
            "not_found": [], "unresolved": [], "still_rate_limited": []}
    p = _receipt(tmp_path,
                 {**base, "ts": "2034-06-01T10:35:00Z"},
                 {**base, "competition": "NFL", "ts": "2034-06-01T11:00:00Z"},
                 {**base, "ts": "2034-06-01T11:35:00Z", "unresolved": [{"match_id": 1}]},
                 {**base, "ts": "2034-06-01T13:00:00Z"})                 # after the export: never seen
    monkeypatch.setenv("SP_RECEIPTS", str(p))
    _, doc = sh.export(now=NOW, out_dir=str(tmp_path / "o"), registry_path=_registry(tmp_path), eid=sh.V2_EID)
    seen = doc["predictions"][0]["refresh_seen"]
    assert seen == doc["refresh_seen"]
    assert (seen["state"], seen["ts"], seen["unresolved"], seen["age_hours"]) == ("failed", "2034-06-01T11:35:00Z",
                                                                                   1, 0.42)
    assert sh.refresh_seen(NOW - timedelta(hours=1, minutes=10), path=p)["state"] == "ok"
    none = sh.refresh_seen(NOW, path=tmp_path / "absent.jsonl")
    assert none["state"] == "none" and "no receipts log read" in none["why"]
    assert sh.refresh_seen_text(seen).startswith("refresh seen: FAILED at 2034-06-01T11:35:00Z")


def test_4_a_refresh_step_that_wrote_no_receipt_is_never_stamped_with_the_earlier_runs(tmp_path):
    """A refresh-by-id that raises before its receipt (a locked DB, the adapter) exits 1 with no refresh_by_id line;
    the chain's step receipt is then the refresh this export saw: FAILED, its exit and stamp, never the earlier OK."""
    base = {"kind": "refresh_by_id", "competition": "NCAA", "now": "x", "selected": 9, "updated": 2,
            "not_found": [], "unresolved": [], "still_rate_limited": []}
    cmd = "python cli.py refresh-by-id --competition NCAA --days 7"
    step = {"kind": "step", "unit": "ncaa-schedule", "run_id": "r", "step": 9, "command": cmd}
    p = _receipt(tmp_path,
                 {**base, "ts": "2034-06-01T00:35:00Z"},                        # the earlier run: OK
                 {**step, "ts": "2034-06-01T00:35:01Z", "exit": 0},
                 {**step, "command": "python cli.py refresh-by-id --competition NFL --days 7",
                  "ts": "2034-06-01T12:30:00Z", "exit": 1},                     # another competition: not read
                 {**step, "ts": "2034-06-01T12:35:00Z", "exit": 1})             # this run: no receipt written
    seen = sh.refresh_seen(NOW + timedelta(minutes=36), path=p)
    assert (seen["state"], seen["ts"], seen["step_exit"]) == ("failed", "2034-06-01T12:35:00Z", 1)
    assert "wrote no refresh_by_id receipt" in seen["why"]
    assert sh.refresh_seen_text(seen).startswith("refresh seen: FAILED at 2034-06-01T12:35:00Z (0.02h before")
    # before this run: the earlier run's receipt and its OK step
    early = sh.refresh_seen(NOW, path=p)
    assert (early["state"], early["ts"], early["step_exit"]) == ("ok", "2034-06-01T00:35:00Z", 0)
    # a receipt whose own step then failed reads failed
    (tmp_path / "q").mkdir()
    q = _receipt(tmp_path / "q", {**base, "ts": "2034-06-01T12:35:00Z"}, {**step, "ts": "2034-06-01T12:35:02Z",
                                                                          "exit": 1})
    assert sh.refresh_seen(NOW + timedelta(hours=1), path=q)["state"] == "failed"


def test_a_held_refresh_step_is_named_never_read_as_a_silent_no_receipt(tmp_path):
    """#928 (ARCHITECT 2026-11-11 09:35 ET, addendum 336 item 2: "ncaa_shadow.refresh_seen not naming the hold: the
    follow-up Issue"): a refresh-by-id step SP_SYNC_HOLD held (the HELD line, exit 0, no refresh_by_id receipt) is the
    refresh this export saw, NONE, with the hold named in `why` and `held`, and in the text; by `sync.held` or by the
    tail's HELD line alike. A step held for another code is not this competition's hold."""
    base = {"kind": "refresh_by_id", "competition": "NCAA", "now": "x", "selected": 9, "updated": 2,
            "not_found": [], "unresolved": [], "still_rate_limited": []}
    cmd = "python cli.py refresh-by-id --competition NCAA --days 7"
    step = {"kind": "step", "unit": "ncaa-schedule", "run_id": "r", "step": 9, "command": cmd, "exit": 0}
    for i, held in enumerate(({"sync": {"held": ["NCAA"]}}, {"tail": ["HELD NCAA (SP_SYNC_HOLD)"]})):
        (tmp_path / str(i)).mkdir()
        p = _receipt(tmp_path / str(i), {**base, "ts": "2034-06-01T00:35:00Z"},
                     {**step, "ts": "2034-06-01T00:35:01Z"},
                     {**step, "step": 8, "command": "python cli.py sync-matches --competition NCAA",
                      "ts": "2034-06-01T12:34:00Z"},
                     {**step, **held, "ts": "2034-06-01T12:35:00Z"})
        seen = sh.refresh_seen(NOW + timedelta(minutes=36), path=p)
        assert (seen["state"], seen["ts"], seen["held"]) == ("none", "2034-06-01T12:35:00Z", ["NCAA"]), seen
        assert seen["why"] == ("the refresh-by-id step was HELD (SP_SYNC_HOLD NCAA): it wrote nothing and no "
                               "refresh_by_id receipt")
        assert "HELD (SP_SYNC_HOLD NCAA)" in sh.refresh_seen_text(seen)
    (tmp_path / "x").mkdir()
    p = _receipt(tmp_path / "x", {**step, "tail": ["HELD NFL (SP_SYNC_HOLD)"], "ts": "2034-06-01T12:35:00Z"})
    other = sh.refresh_seen(NOW + timedelta(minutes=36), path=p)
    assert "held" not in other and "wrote no refresh_by_id receipt" in other["why"]


def test_4_the_real_chain_a_failed_refresh_without_a_receipt_reads_failed(sandbox):
    """The real ncaa-schedule chain on a fake cli.py whose refresh-by-id exits 1 and writes no receipt, after an
    earlier OK refresh_by_id receipt: what the export would stamp (refresh_seen on the chain's own receipts log) is
    FAILED, never the earlier run's OK."""
    import sp_common as c
    import sp_run

    c.append_receipt({"kind": "refresh_by_id", "competition": "NCAA", "now": "x", "selected": 9, "updated": 2,
                      "not_found": [], "unresolved": [], "still_rate_limited": []})
    (c.REPO / "cli.py").write_text(FAKE_NCAA_CLI.replace("{fail}", "refresh"))
    assert sp_run.main(["ncaa-schedule"]) == 1
    from src.timeutil import utc_now_naive

    seen = sh.refresh_seen(utc_now_naive() + timedelta(minutes=1), path=sandbox / "log" / "receipts.jsonl")
    assert seen["state"] == "failed" and seen["step_exit"] == 1 and "wrote no refresh_by_id receipt" in seen["why"]


def test_4_a_d6_drop_after_a_pass_refuses_exit_2_never_dormant(clean, tmp_path, monkeypatch, host):
    from cli import cli

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(reg, "LEDGER", _registry(tmp_path))
    monkeypatch.setattr(nc, "stored_coverage", lambda s, seasons, **k: _fbs(ok26=False))
    res = CliRunner().invoke(cli, STEP)
    assert res.exit_code == 2 and "labels less than 95%" in res.output and "DORMANT" not in res.output
    assert not (tmp_path / "exports").exists() or not list((tmp_path / "exports").glob("ncaa_shadow_*.json"))


# ------------------------------------------------------------------------------------------------ (5) --

@pytest.mark.parametrize("role,why", [("laptop", "this machine's role is laptop"),
                                      (None, "the role is unknown (SP_EXPORTS_MIRROR_ROLE unset)"),
                                      ("desk", "the role 'desk' is not host or laptop")])
def test_5_the_command_refuses_off_the_host_before_any_read(role, why, tmp_path, monkeypatch):
    from cli import cli

    if role is None:
        monkeypatch.delenv("SP_EXPORTS_MIRROR_ROLE", raising=False)
    else:
        monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", role)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sh, "frozen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("read")))
    for argv in (STEP, ["export-ncaa-predictions"]):
        res = CliRunner().invoke(cli, argv)
        assert res.exit_code == 2, res.output
        assert res.output.startswith("REFUSED: export-ncaa-predictions runs on the host only (ARCHITECT 2026-11-03, "
                                     "addendum 236 item 3(5); 178 R6's fence): " + why + ". Nothing was read or "
                                     "written")
    assert not (tmp_path / "exports").exists()


def test_5_dry_run_prints_the_rows_and_writes_nothing_on_the_laptop(clean, tmp_path, monkeypatch):
    from cli import cli

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(reg, "LEDGER", _registry(tmp_path))
    _pregame(clean["up"], True)
    real = sh.export
    monkeypatch.setattr(sh, "export", lambda **k: real(now=NOW, **k))
    res = CliRunner().invoke(cli, STEP + ["--dry-run"])                   # laptop (conftest's pin)
    assert res.exit_code == 0, res.output
    assert "DRY RUN (addendum 236 item 3(5)): 1 row(s) it would write · nothing written" in res.output
    assert "NSH Team 1 @ NSH Team 0" in res.output and "neutral (CFBD's pregame field)" in res.output
    assert "neutral per CFBD's pregame field, read 2034-06-01T12:00:00; absent: unknown, D8" in res.output
    assert not (tmp_path / "exports").exists()
    path, doc = real(now=NOW, out_dir=str(tmp_path / "x"), eid=sh.V2_EID, dry_run=True)
    assert path is None and doc["count"] == 1 and not (tmp_path / "x").exists()


# ------------------------------------------------------------------------------------------------ (7) --

def test_7_frozen_the_counter_and_coverage_read_registry_ledger_at_call_time(tmp_path, monkeypatch):
    import chains
    import coverage_map

    p = _registry(tmp_path, verdict=None)
    monkeypatch.setattr(reg, "LEDGER", p)
    seen = []
    real = reg.load
    monkeypatch.setattr(reg, "load", lambda path=reg.LEDGER: seen.append(path) or real(path))
    with pytest.raises(sh.ShadowDormant):
        sh.frozen(eid=sh.V2_EID)
    assert sh.confirmation_counter(sh.V2_EID, export_dir=str(tmp_path))["state"] == "dormant"
    assert coverage_map._ncaa_binds("NCAA", {}, chains.NCAA_SHADOW_STEP).startswith("dormant: the registry records no "
                                                                                    "verdict for ncaa-elo-v2")
    assert len(seen) >= 3 and set(seen) == {p}                            # every read: the patched path, none other
    assert reg.LEDGER != str(ROOT / "docs" / "registry" / "experiments.json")


def test_7_the_record_reads_the_same_one_registry_as_the_counter(tmp_path, monkeypatch):
    """The record's own reads (its counter, the D4 rate, the Kalshi fences) are the same registry.LEDGER read at call
    time: confirmation_record and confirmation_counter take no path, so no read in one call can take a second source."""
    import inspect

    from src.walters import ncaa_v1r_gate as g

    for f in (sh.confirmation_record, sh.confirmation_counter, sh.d4_rate, sh.kalshi_fenced, sh.v2_verdict_recorded):
        assert "registry_path" not in inspect.signature(f).parameters
    p = _registry(tmp_path)                                               # PASS, with its run
    monkeypatch.setattr(reg, "LEDGER", p)
    seen = []
    real = reg.load
    monkeypatch.setattr(reg, "load", lambda path=reg.LEDGER: seen.append(path) or real(path))
    count = {"n": 0, "scored_ids": [], "cohort_ids": [], "n_games": 100, "bar": 0.69, "cohort_state": "provisional",
             "cohort_size": 0, "eligible_stored": 0, "release_due": 0, "complete": False, "pending": []}
    monkeypatch.setattr(g, "confirmation_count", lambda spec, path=None: seen.append(path) or dict(count))
    x = sh.confirmation_record(export_dir=str(tmp_path))
    assert x["counter"]["state"] == "counting" and x["references"][sh.D4_REF_NAME] == sh.D4_REF_TEXT
    assert sh.kalshi_fenced() is False                                    # the run and the verdict: from p
    assert len(seen) >= 4 and set(seen) == {p}
