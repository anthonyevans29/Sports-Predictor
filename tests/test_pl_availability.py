"""pl-availability-v1 (ARCHITECT 2026-11-01 10:05 ET, addendum 198 items 1-5; lane pl-availability, #754): the rule on
synthetic injury rows, the arm priced in v22's own pass on the host only, the PL rows' candidate keys (absent off the
host, never read by the Desk), the registry entry, the fence, the grader's second arm, the window reader (counts only,
refused while window_opens_at is null) and the one read. Throwaway SQLite files only (tests/test_record_vs_close.py
iso_db) and tmp registries (registry.LEDGER monkeypatched); the real docs/registry/experiments.json is read, never
written."""
from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.db.schema import MatchStatus, Sport
from src.models.factors import injury_adjustment
from src.walters import pl_availability as pa
from src.walters import registry as reg
from tests.test_record_vs_close import iso_db  # noqa: F401  (a fixture: a throwaway SQLite, cwd = tmp_path)

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "docs" / "specs" / "pl-availability-v1.md"
SEASON = "2026/27"
OPENS = datetime(2026, 11, 7, 12, 30)                 # a window_opens_at, naive UTC
OPENS_TEXT = "2026-11-07T12:30:00Z"
NOW = datetime(2027, 1, 20, 12, 0)                    # the read clock
FORBIDDEN = re.compile(r"log-loss|log loss|logloss|probab|\bhits?\b|%|0\.\d{3}", re.IGNORECASE)

_spec = importlib.util.spec_from_file_location("pl_availability_window", ROOT / "scripts" / "pl_availability_window.py")
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)


def inj(name, typ="Missing Fixture", fid="1001", pos="Attacker"):
    return SimpleNamespace(player_name=name, player_position=pos, type=typ, fixture_source_id=fid)


def match(fid="1001", prev=None):
    ext = {} if fid is None else {"api_football": fid}
    if prev:
        ext["api_football_prev"] = prev
    return SimpleNamespace(external_ids=ext)


@pytest.fixture
def host(monkeypatch):
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "host")


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """write(**entry fields) -> a tmp registry holding one pl-availability-v1 entry (or none with write(None))."""
    path = tmp_path / "experiments.json"

    def write(entry="default", **kw):
        if entry is None:
            path.write_text("[]")
            return
        e = {"id": pa.EID, "declared_at": pa.DECLARED_AT_TEXT, "window_opens_at": OPENS_TEXT, "verdict": None,
             "status": "declared", "run": None}
        e.update(kw)
        path.write_text(json.dumps([e]))
    monkeypatch.setattr(reg, "LEDGER", str(path))
    monkeypatch.setattr(pa, "RESERVATION", str(tmp_path / "started.json"))
    write()
    return write


# ===================================================================================================== the rule --

def test_an_earlier_fixture_missing_fixture_entry_counts_for_nothing():
    assert pa.rule_filter([inj("Doucoure", fid="999")], match()) == []


def test_a_this_fixture_questionable_entry_counts_for_nothing():
    assert pa.rule_filter([inj("James", typ="Questionable")], match()) == []


def test_a_this_fixture_missing_fixture_entry_counts():
    x = inj("Araujo")
    assert pa.rule_filter([x], match()) == [x]
    assert pa.counts(inj("A", fid=" 1001 "), "1001") and pa.counts(inj("A", fid=1001), "1001")   # str, stripped


@pytest.mark.parametrize("entry, m", [
    (inj("No fixture", fid=None), match()),                      # entries naming no fixture
    (inj("Blank", fid=""), match()),
    (inj("Later", fid="1002"), match()),                         # another (a later) fixture
    (inj("Lowercase", typ="missing fixture"), match()),          # the type exactly
    (inj("No type", typ=None), match()),
    (inj("No provider id"), match(fid=None)),                    # the match carries no provider id
    (inj("Previous id", fid="777"), match(prev=["777"])),        # api_football_prev is not THAT fixture's id
])
def test_everything_else_counts_for_nothing(entry, m):
    assert pa.rule_filter([entry], m) == []


def test_the_filter_keeps_the_model_list_order_and_objects():
    xs = [inj("a"), inj("b", typ="Questionable"), inj("c", fid="5"), inj("d", pos="Defender")]
    assert pa.rule_filter(xs, match()) == [xs[0], xs[3]]


def test_the_cap_holds_under_the_candidate():
    """The candidate calls the model's own injury_adjustment on the filtered list: the weights and the 25% cap."""
    six = [inj(f"F{i}") for i in range(6)]                     # 6 x 0.06 = 0.36 -> capped at 0.25
    noise = [inj(f"Q{i}", typ="Questionable") for i in range(5)] + [inj(f"E{i}", fid="9") for i in range(5)]
    f = injury_adjustment(home_injuries=pa.rule_filter(six + noise, match()), away_injuries=[])
    assert f.home_xg_multiplier == pytest.approx(0.75) and f.away_xg_multiplier == 1.0
    two = injury_adjustment(home_injuries=pa.rule_filter([inj("G", pos="Goalkeeper"), inj("M", pos="Midfielder")]
                                                         + noise, match()))
    assert two.home_xg_multiplier == pytest.approx(1 - 0.05 - 0.04)
    model = injury_adjustment(home_injuries=six + noise)       # the model's own read of the same list: capped too
    assert model.home_xg_multiplier == pytest.approx(0.75)


def test_the_rule_text_is_item_1_verbatim_and_the_spec_holds_the_ruling():
    spec = SPEC.read_text()
    for text in (pa.RULE_TEXT, pa.UNCHANGED_TEXT, pa.WINDOW_TEXT, pa.BAR_TEXT, pa.FENCE_TEXT, pa.VERDICT_TEXT):
        assert text in spec, text[:60]
    assert "ARCHITECT 2026-11-01 10:05 ET — addendum 198" in spec and "THE RECEIPTS, READ." in spec
    assert "6. TWO STANDING LINES" not in spec                   # item 6 is #759's, not quoted here


# ============================================================================== the arm, priced in v22's pass --

KICK = datetime(2026, 11, 8, 15, 0)


def _world(injuries, comp_code="PL", fid="1001"):
    """A PL world: 12 finished games, one scheduled fixture with provider id `fid`, a v22 model, the given injuries
    [(side, name, type, fixture id, position)]. Returns the fixture's id."""
    from src.db.database import session_scope
    from src.db.schema import Competition, Injury, Match, ModelVersion, Team
    with session_scope() as s:
        comp = Competition(sport=Sport.SOCCER, code=comp_code, name=comp_code, area="X", type="LEAGUE")
        s.add(comp)
        teams = [Team(sport=Sport.SOCCER, name=f"{comp_code} {n}") for n in ("Alpha", "Beta", "Gamma", "Delta")]
        s.add_all(teams)
        s.flush()
        a, b, g, d = (t.id for t in teams)
        t0 = datetime(2026, 8, 16, 15, 0)
        res = [(a, b, 2, 1), (g, d, 1, 1), (b, g, 0, 2), (d, a, 1, 3), (a, g, 1, 0), (b, d, 2, 2),
               (g, a, 1, 1), (d, b, 0, 1), (b, a, 1, 1), (d, g, 2, 1), (g, b, 3, 0), (a, d, 2, 0)]
        for i, (h, aw, hs, as_) in enumerate(res):
            s.add(Match(sport=Sport.SOCCER, competition_id=comp.id, season=SEASON, utc_date=t0 + timedelta(days=4 * i),
                        status=MatchStatus.FINISHED, home_team_id=h, away_team_id=aw, home_score=hs, away_score=as_))
        fx = Match(sport=Sport.SOCCER, competition_id=comp.id, season=SEASON, utc_date=KICK,
                   status=MatchStatus.SCHEDULED, home_team_id=a, away_team_id=b,
                   external_ids={"api_football": fid} if fid else {})
        s.add(fx)
        side = {"home": a, "away": b}
        for sd, name, typ, f, pos in injuries:
            s.add(Injury(team_id=side[sd], player_name=name, player_position=pos, type=typ, fixture_source_id=f,
                         source="t", refreshed_at=datetime(2026, 11, 7, 9, 0)))
        s.add(ModelVersion(sport=Sport.SOCCER, model_family="soccer_elo_poisson", version="v22", status="production",
                           parameters={"elo": {"league": {"ratings": {a: 1610.0, b: 1540.0, g: 1580.0, d: 1520.0}},
                                               "cup": {"ratings": {}}},
                                       "team_to_league": {a: comp_code, b: comp_code, g: comp_code, d: comp_code},
                                       "contexts": {}, "poisson": {"dixon_coles_rho": -0.1}}))
        s.flush()
        return fx.id


MIXED = [("home", "Araujo", "Missing Fixture", "1001", "Attacker"),        # this fixture: counts
         ("home", "Scott", "Missing Fixture", "1001", "Midfielder"),       # this fixture: counts
         ("home", "Doucoure", "Missing Fixture", "990", "Attacker"),       # an earlier fixture: nothing
         ("home", "James", "Questionable", "1001", "Defender"),            # questionable: nothing
         ("away", "Lerma", "Missing Fixture", "2002", "Midfielder"),       # another fixture: nothing
         ("away", "Nobody", "Missing Fixture", None, "Goalkeeper")]        # no fixture: nothing
PASSING = [x for x in MIXED if x[2] == "Missing Fixture" and x[3] == "1001"]


def _predict(code="PL"):
    from src.db.database import session_scope
    from src.db.schema import Prediction
    from src.walters.training import _generate_predictions_soccer
    _generate_predictions_soccer(code, SEASON, model_version="v22")
    with session_scope() as s:
        (p,) = s.query(Prediction).all()
        return {"p": (p.home_win_prob, p.draw_prob, p.away_win_prob), "fb": dict(p.factor_breakdown)}


def test_off_the_host_nothing_is_computed_or_stored(iso_db):
    _world(MIXED)
    got = _predict()
    assert pa.FB_KEY not in got["fb"] and got["fb"]["home_injuries_count"] == 4


def test_on_the_host_v22_is_unchanged_and_the_arm_rides_beside_it(iso_db, monkeypatch):
    """v22's probabilities and every factor_breakdown key are the laptop pass's; the arm is one extra key."""
    _world(MIXED)
    lap = _predict()
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "host")
    got = _predict()
    assert got["p"] == lap["p"]
    arm = got["fb"].pop(pa.FB_KEY)
    assert got["fb"] == lap["fb"]
    assert arm["version"] == pa.EID and arm["base_version"] == "v22"
    assert arm["missing"] == {"home": {"model": 4, "candidate": 2}, "away": {"model": 2, "candidate": 0}}
    assert (arm["p_home"], arm["p_draw"], arm["p_away"]) != got["p"]
    assert arm["p_home"] > got["p"][0]                            # fewer home absences: a stronger home side
    assert math.isclose(arm["p_home"] + arm["p_draw"] + arm["p_away"], 1.0, abs_tol=1e-9)


def test_the_arm_is_v22_on_the_filtered_list(iso_db, monkeypatch, tmp_path):
    """The same model on the same inputs: the host's arm equals v22 priced on a world holding only the entries the
    rule keeps; and with no entry dropped (the same list) the arm IS v22, number for number."""
    _world(MIXED)
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "host")
    arm = _predict()["fb"][pa.FB_KEY]
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "laptop")
    from src.db.database import session_scope
    from src.db.schema import Injury
    with session_scope() as s:
        for i in s.query(Injury).all():
            if not (i.type == "Missing Fixture" and i.fixture_source_id == "1001"):
                s.delete(i)
    only = _predict()
    assert (arm["p_home"], arm["p_draw"], arm["p_away"]) == only["p"]
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "host")
    same = _predict()                                              # every entry passes now: the same list
    assert (same["fb"][pa.FB_KEY]["p_home"], same["fb"][pa.FB_KEY]["p_draw"],
            same["fb"][pa.FB_KEY]["p_away"]) == same["p"]
    assert same["fb"][pa.FB_KEY]["missing"] == {"home": {"model": 2, "candidate": 2},
                                                "away": {"model": 0, "candidate": 0}}


def test_an_arm_that_fails_never_stops_v22s_row(iso_db, monkeypatch, caplog):
    _world(MIXED)
    lap = _predict()
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "host")

    def boom(*a, **k):
        raise RuntimeError("synthetic")
    monkeypatch.setattr(pa, "rule_filter", boom)
    got = _predict()
    assert got["p"] == lap["p"] and "no candidate arm for match" in caplog.text
    mark = got["fb"].pop(pa.FB_KEY)                                # the failure is stored as its cause, not lost
    assert got["fb"] == lap["fb"]                                  # v22's row otherwise the laptop's
    assert mark == {"version": pa.EID, "base_version": "v22", "error": "RuntimeError: synthetic"}
    pred = SimpleNamespace(factor_breakdown={pa.FB_KEY: mark})
    assert pa.arm_of(pred) is None and pa.arm_error(pred) == "RuntimeError: synthetic"
    (row,) = _export()["predictions"]
    assert row["candidate_probabilities"] is None and row["candidate_missing"] is None
    assert row["candidate_reason"].startswith("the candidate failed on the host for this fixture (RuntimeError: synth")
    assert pa.FB_KEY not in row["prediction"]["factor_breakdown"]
    m = SimpleNamespace(season="2025/26", utc_date=KICK, competition=SimpleNamespace(code="PL"))
    oc = SimpleNamespace(actual_result=SimpleNamespace(value="H"))
    assert pa.result_arm(None, pred, oc, m)["reason"] == "the candidate failed on the host for this fixture " \
                                                         "(RuntimeError: synthetic)"


def _squads(fx_id):
    """Lineups and player stats that make v22's lineup and XI factors bite on the fixture: the home side's regulars
    (a confirmed XI of an earlier game, with strong season stats) are not in the fixture's confirmed XI."""
    from src.db.database import session_scope
    from src.db.schema import Lineup, Match, Player, PlayerSeasonStats
    with session_scope() as s:
        fx = s.get(Match, fx_id)
        home = fx.home_team_id
        past = s.query(Match).filter(Match.home_team_id == home, Match.id != fx_id).order_by(Match.id).first()
        pos = ["Goalkeeper"] + ["Defender"] * 4 + ["Midfielder"] * 3 + ["Attacker"] * 3
        for i, ps in enumerate(pos):
            s.add(Lineup(match_id=past.id, team_id=home, kind="confirmed", is_starter=True, player_name=f"Reg{i}",
                         player_position=ps, refreshed_at=datetime(2026, 10, 1)))
            s.add(Lineup(match_id=fx_id, team_id=home, kind="confirmed", is_starter=True, player_name=f"Kid{i}",
                         player_position=ps, refreshed_at=datetime(2026, 11, 8, 14, 0)))
            for name, strong in ((f"Reg{i}", True), (f"Kid{i}", False)):   # scored XIs: the XI factor has full weight
                pl = Player(sport=Sport.SOCCER, name=name, position=ps, team_id=home)
                s.add(pl)
                s.flush()
                s.add(PlayerSeasonStats(player_id=pl.id, team_id=home, season=SEASON, competition_code="PL",
                                        appearances=30, lineups=30 if strong else 5, minutes=2700 if strong else 900,
                                        goals=(12 if ps == "Attacker" else 2) if strong else 0,
                                        assists=8 if strong else 0, shots=60 if strong else 2,
                                        shots_on_target=30 if strong else 0, key_passes=50 if strong else 1,
                                        pass_accuracy=0.88 if strong else 0.6))


def test_the_arm_is_v22_on_the_filtered_list_with_the_lineup_and_xi_factors_live(iso_db, monkeypatch):
    """Item 1's "one rule, one candidate": with v22's lineup and XI factors biting, the arm still equals v22 priced on
    a world holding only the entries the rule keeps, and with no entry dropped it IS v22 (a candidate that left the
    lineup or XI term out would differ here)."""
    fx = _world(MIXED)
    _squads(fx)
    lap = _predict()
    notes = " ".join(lap["fb"]["factor_notes"])
    assert "regular" in notes.lower() or "lineup" in notes.lower(), notes        # the lineup factor bites
    assert lap["fb"]["home_xi_attack"] is not None and lap["fb"]["home_baseline_attack"] is not None
    assert lap["fb"]["home_xi_attack"] < lap["fb"]["home_baseline_attack"] - 3    # the XI factor bites
    assert any("XI attack" in n for n in lap["fb"]["factor_notes"]), lap["fb"]["factor_notes"]
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "host")
    arm = _predict()["fb"][pa.FB_KEY]
    from src.db.database import session_scope
    from src.db.schema import Injury
    with session_scope() as s:
        for i in s.query(Injury).all():
            if not (i.type == "Missing Fixture" and i.fixture_source_id == "1001"):
                s.delete(i)
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "laptop")
    only = _predict()
    assert (arm["p_home"], arm["p_draw"], arm["p_away"]) == only["p"]
    with session_scope() as s:                                     # injuries out entirely: the lineup/XI terms alone
        s.query(Injury).delete()
    bare = _predict()
    assert bare["p"] != only["p"]                                  # the injuries still move the price under them
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "host")
    same = _predict()                                              # the same (empty) list: the arm IS v22
    a = same["fb"][pa.FB_KEY]
    assert (a["p_home"], a["p_draw"], a["p_away"]) == same["p"] == bare["p"]


def test_the_cap_holds_on_the_hosts_pricing_path(iso_db, monkeypatch):
    """The cap under the candidate, through the training pass: seven passing attackers (7 x 0.06 = 0.42) on one side
    price exactly as v22 priced on a world holding only them (the model's own 25% cap), and as five (0.30, capped
    too) do."""
    seven = [("home", f"Fwd{i}", "Missing Fixture", "1001", "Attacker") for i in range(7)]
    noise = [("home", "Q", "Questionable", "1001", "Attacker"), ("away", "E", "Missing Fixture", "77", "Attacker")]
    _world(seven + noise)
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "host")
    arm = _predict()["fb"][pa.FB_KEY]
    assert arm["missing"] == {"home": {"model": 8, "candidate": 7}, "away": {"model": 1, "candidate": 0}}
    from src.db.database import session_scope
    from src.db.schema import Injury
    with session_scope() as s:
        for i in s.query(Injury).all():
            if not (i.type == "Missing Fixture" and i.fixture_source_id == "1001"):
                s.delete(i)
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "laptop")
    only = _predict()
    assert (arm["p_home"], arm["p_draw"], arm["p_away"]) == only["p"]
    assert any("-25%" in n for n in only["fb"]["factor_notes"]), only["fb"]["factor_notes"]
    with session_scope() as s:
        for i in s.query(Injury).filter(Injury.player_name.in_(["Fwd5", "Fwd6"])).all():
            s.delete(i)
    five = _predict()
    assert five["p"] == only["p"]                                  # 0.30 and 0.42 both capped at 0.25


def test_another_competition_and_the_report_only_mode_carry_no_arm(iso_db, host):
    _world(MIXED, comp_code="ELX")
    assert pa.FB_KEY not in _predict("ELX")["fb"]
    from src.walters.training import _generate_predictions_soccer
    rows = _generate_predictions_soccer("ELX", SEASON, model_version="v22", include_finished=True)
    assert rows and all(pa.FB_KEY not in r for r in rows)
    assert pa.arm_off_reason("PL") is None and "PL only" in pa.arm_off_reason("SA")


@pytest.mark.parametrize("role, why", [("laptop", "this machine's role is laptop"), (None, "unset"),
                                       ("desk", "is not host or laptop")])
def test_the_arm_is_host_only_by_the_leagues_switchs_gate(monkeypatch, role, why):
    if role is None:
        monkeypatch.delenv("SP_EXPORTS_MIRROR_ROLE")
    else:
        monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", role)
    assert why in pa.arm_off_reason("PL")


# ======================================================================================= the rows, host only --

def _export(desk=False):
    from src.walters.export import export_predictions
    return json.loads(export_predictions(sport=Sport.SOCCER, start_date=KICK - timedelta(days=1),
                                         end_date=KICK + timedelta(days=1), competition_code="PL",
                                         statuses=[MatchStatus.SCHEDULED], desk=desk))


def test_host_rows_carry_the_candidate_keys_and_the_laptop_rows_do_not(iso_db, monkeypatch):
    _world(MIXED)
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "host")
    _predict()
    (row,) = _export()["predictions"]
    assert set(pa.ROW_KEYS) <= set(row)
    assert row["candidate_version"] == "pl-availability-v1" and row["candidate_reason"] is None
    assert set(row["candidate_probabilities"]) == {"home_win", "draw", "away_win"}
    assert row["candidate_probabilities"] != row["prediction"]["probabilities"]
    assert row["candidate_missing"] == {"home": {"model": 4, "candidate": 2}, "away": {"model": 2, "candidate": 0}}
    assert row["prediction"]["factor_breakdown"]["home_injuries_count"] == 4
    assert pa.FB_KEY not in row["prediction"]["factor_breakdown"]            # never inside the prediction block
    assert row["injuries"]["home_count"] == 4 and row["input_quality"]["injuries"]["home"]["count"] == 4   # unchanged
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "laptop")                    # the same DB read off the host
    (lap,) = _export()["predictions"]
    assert not set(pa.ROW_KEYS) & set(lap) and pa.FB_KEY not in lap["prediction"]["factor_breakdown"]
    assert {k: v for k, v in row.items() if k not in pa.ROW_KEYS} == lap      # nothing else differs


def test_a_host_row_without_an_arm_says_why(iso_db, monkeypatch):
    _world(MIXED)
    _predict()                                                    # predicted on the laptop: no arm stored
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "host")
    (row,) = _export()["predictions"]
    assert row["candidate_probabilities"] is None and row["candidate_missing"] is None
    assert row["candidate_reason"].startswith("the stored prediction carries no candidate arm")
    assert pa.export_fields(None, "PL")["candidate_reason"] == "no v22 prediction is stored for this fixture"
    assert pa.export_fields(None, "SA") is None


def test_a_finished_window_games_row_withholds_the_candidate_until_the_verdict(iso_db, ledger, monkeypatch):
    """The fence on the predictions export: a FINISHED window game's row carries the result beside the arm, so the
    candidate's figures are withheld before the verdict (result_arm withholds the same game) and shown after it."""
    from src.db.database import session_scope
    from src.db.schema import Match
    from src.walters.export import export_predictions
    fx = _world(MIXED)
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "host")
    _predict()
    (sched,) = _export()["predictions"]                           # the slate row: the arm, as item 2 orders
    assert sched["candidate_probabilities"] is not None
    with session_scope() as s:
        m = s.get(Match, fx)
        m.status, m.home_score, m.away_score, m.status_raw = MatchStatus.FINISHED, 2, 0, "FT"

    def fin():
        (r,) = json.loads(export_predictions(sport=Sport.SOCCER, start_date=KICK - timedelta(days=1),
                                             end_date=KICK + timedelta(days=1), competition_code="PL",
                                             statuses=[MatchStatus.FINISHED]))["predictions"]
        return r
    r = fin()
    assert r["status"] == "finished" and r["actual_home_score"] == 2
    assert r["candidate_probabilities"] is None and r["candidate_missing"] is None
    assert r["candidate_reason"].startswith("withheld: a window game before the verdict") and \
        pa.FENCE_TEXT in r["candidate_reason"]
    ledger(verdict={"verdict": "REJECT"})
    r = fin()
    assert r["candidate_probabilities"] == sched["candidate_probabilities"] and r["candidate_reason"] is None


def test_the_desk_reads_nothing_of_the_candidate_keys(iso_db, monkeypatch):
    """Item 2: "never a call, never a Desk input". The Desk's blocks and desk_meta are byte-identical with the keys and
    without them, on the host's own export."""
    from src.walters import desk_policy as dp
    _world(MIXED)
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "host")
    _predict()
    doc = _export()
    assert set(pa.ROW_KEYS) <= set(doc["predictions"][0])
    bare = json.loads(json.dumps(doc))
    for r in bare["predictions"]:
        for k in pa.ROW_KEYS:
            r.pop(k)
    # a row priced the other way round too: the keys carry a different pick than v22's
    loud = json.loads(json.dumps(doc))
    loud["predictions"][0]["candidate_probabilities"] = {"home_win": 0.98, "draw": 0.01, "away_win": 0.01}
    now = datetime(2026, 11, 8, 9, 0, tzinfo=timezone.utc)
    a, b, c = (dp.annotate(json.loads(json.dumps(x)), now=now) for x in (doc, bare, loud))
    for x in (a, c):
        assert json.dumps(x["desk_meta"], sort_keys=True) == json.dumps(b["desk_meta"], sort_keys=True)
        assert [json.dumps(r["desk"], sort_keys=True) for r in x["predictions"]] == \
               [json.dumps(r["desk"], sort_keys=True) for r in b["predictions"]]


# ===================================================================================================== registry --

def test_the_registry_entry_is_declared_with_the_frozen_rule():
    e = reg.get(pa.EID)
    assert e is not None
    assert (e["status"], e["run"], e["verdict"]) == ("declared", None, None)
    assert e["declared_at"] == "2026-11-01T15:05:00Z" and e["sport"] == "soccer" and e["competition"] == "PL"
    assert all(e.get(k) for k in reg.DECLARE_FIELDS)
    assert e["declaration"] == "docs/specs/pl-availability-v1.md" and (ROOT / e["declaration"]).is_file()
    assert e["rule"] == pa.RULE_TEXT and pa.RULE_TEXT in e["candidate"] and pa.UNCHANGED_TEXT in e["candidate"]
    assert pa.BAR_TEXT in e["gate"] and pa.FENCE_TEXT in e["gate"] and pa.VERDICT_TEXT in e["gate"]
    assert e["fence"] == pa.FENCE_TEXT and e["window"].endswith(pa.WINDOW_TEXT)
    assert e["window_opens_at"] is None and "Code's PR records it" in e["window_opens_at_note"]
    assert e["n"] == 60 == pa.WINDOW_GAMES and e["base_version"] == "v22" == pa.BASE_VERSION and pa.BAR == 0.0050
    assert e["live_needs"].startswith("WHAT THE VERDICT DOES (live_needs): PASS") and "#754" in e["live_needs"]
    assert e["confirmation_plan"] is None
    assert e["ratified"].startswith("ARCHITECT 2026-11-01 10:05 ET, addendum 198")
    assert reg._retired_refusal(e["test_set"], e["id"]) is None and reg.prior_reads(e["test_set"], None, pa.EID) == []
    assert pa.parse_instant(e["declared_at"]) == pa.DECLARED_AT
    raw = (ROOT / "docs" / "registry" / "experiments.json").read_text()
    assert raw == json.dumps(json.loads(raw), indent=2) + "\n"
    assert reg.load()[-1]["id"] == pa.EID
    assert hashlib.sha256(e["rule"].encode()).hexdigest() == hashlib.sha256(pa.RULE_TEXT.encode()).hexdigest()


def test_the_roadmap_lane_validates_and_is_declared():
    from src import roadmap as rm
    doc = rm.load()
    (ln,) = [x for x in doc["lanes"] if x["lane"] == "pl-availability"]
    assert rm.validate(doc) == []
    assert (ln["issue"], ln["registry_id"], ln["state"], ln["competitions"], ln["earliest_live"]) == \
           (754, "pl-availability-v1", "declared", ["PL"], None)
    steps = ln["steps"]
    assert [s["owner"] for s in steps] == ["code", "operator", "calendar", "architect"]
    assert steps[0]["due"] == "2026-11-05" and steps[0]["what"].startswith("the shadow PR")
    assert "the first host page on the tag after v1.6.2" in steps[1]["what"] and steps[1]["due"] == "2026-11-06"
    # addendum 199 item 3: the two later steps are projections, not floors; each date move has its moved line
    assert steps[2]["what"].startswith("the 60th window game is final") and steps[2]["due"] == "2026-12-20"
    assert "projection from the PL schedule, not a floor" in steps[2]["what"]
    assert steps[3]["what"].startswith("the one read and the verdict") and steps[3]["due"] == "2026-12-21"
    assert [(m["which"], m["was"], m["now"]) for m in ln["moved"]] == [
        (steps[2]["what"], "2026-11-06", "2026-12-20"), (steps[3]["what"], "2026-11-06", "2026-12-21")]
    assert all(m["ruling"].startswith("ARCHITECT 2026-11-01 12:05 ET, addendum 199 item 3") for m in ln["moved"])


def test_the_entry_records_the_one_entry_per_player_limitation():
    """Addendum 199 item 6: the known limitation is written into the registry entry (the ingest is not changed)."""
    e = pa._entry()
    assert e["limitation"].startswith("KNOWN LIMITATION (ARCHITECT 2026-11-01 12:05 ET, addendum 199 item 6)")
    assert "under-counts" in e["limitation"] and "the ingest is NOT changed" in e["limitation"]


# ===================================================================================================== the fence --

def test_the_real_registry_fences_pl_2026_27_from_the_declaration():
    """window_opens_at is null in the entry as declared: the cut is declared_at (no window game kicks off before it)."""
    assert pa.fence_cutoff(SEASON) == pa.DECLARED_AT == pa.fence_cutoff(None)
    assert pa.fence_cutoff("2025/26") is None
    why = pa.fence_refusal("PL", SEASON)
    assert why and pa.FENCE_TEXT in why and pa.READER in why and "2026-11-01T15:05:00Z" in why
    assert pa.fence_refusal("pl", None)                                     # every season: fenced
    assert pa.fence_refusal("PL", "2025/26") is None and pa.fence_refusal("SA", SEASON) is None
    assert pa.fence_refusal("PL", SEASON, through=pa.DECLARED_AT - timedelta(seconds=1)) is None
    assert pa.fence_refusal("PL", SEASON, through=pa.DECLARED_AT)
    from src.walters import soccer_expansion as sx
    assert sx.guards_backtest("PL", SEASON) is None                         # the leagues' fence is untouched


def test_the_cut_moves_to_window_opens_at_and_lifts_at_the_verdict(ledger, tmp_path):
    assert pa.fence_cutoff(SEASON) == OPENS
    assert pa.fence_refusal("PL", SEASON, through=OPENS - timedelta(minutes=1)) is None
    g = SimpleNamespace(season=SEASON, utc_date=OPENS)
    assert pa.fenced(OPENS, g) and not pa.fenced(OPENS, SimpleNamespace(season=SEASON, utc_date=OPENS - timedelta(1)))
    assert not pa.fenced(OPENS, SimpleNamespace(season="2025/26", utc_date=OPENS))
    ledger(verdict={"verdict": "REJECT"})
    assert pa.fence_cutoff(SEASON) is None and pa.fence_refusal("PL", SEASON) is None
    ledger(None)                                                            # no entry: the pre-declaration fence
    assert pa.fence_cutoff(SEASON) == pa.DECLARED_AT
    ledger(window_opens_at="2026-11-07")                                    # a date is never the instant
    assert pa.fence_cutoff(SEASON) == datetime.min
    Path(reg.LEDGER).write_text("{not json")                                # unreadable: the whole season
    assert pa.fence_cutoff(SEASON) == datetime.min and "the whole season" in pa.fence_refusal("PL", SEASON)


def test_the_walks_and_soccer_backtest_refuse_the_window(iso_db):
    from click.testing import CliRunner

    import cli
    from src.walters import backtest
    from src.walters.soccer_backtest import run_soccer_backtest
    with pytest.raises(pa.PLFenceRefused, match="addendum 198"):
        run_soccer_backtest("PL", SEASON)
    with pytest.raises(pa.PLFenceRefused):
        run_soccer_backtest("PL", None)
    with pytest.raises(pa.PLFenceRefused):
        backtest.run_backtest(season=SEASON, competition_code="PL")
    assert run_soccer_backtest("PL", "2025/26") in (None, [])               # another season: not the window
    assert run_soccer_backtest("PL", SEASON, through=pa.DECLARED_AT - timedelta(hours=1)) in (None, [])
    r = CliRunner().invoke(cli.cli, ["soccer-backtest", "--competition", "PL", "--season", SEASON])
    assert r.exit_code == 2 and r.output.startswith("REFUSED: PL 2026/27: pl-availability-v1 is declared")
    r = CliRunner().invoke(cli.cli, ["soccer-backtest", "--competition", "PL"])
    assert r.exit_code == 2 and "REFUSED" in r.output


# ======================================================================================= the window and the read --

def _pl():
    from src.db.database import session_scope
    from src.db.schema import Competition, Team
    with session_scope() as s:
        s.add(Competition(sport=Sport.SOCCER, code="PL", name="PL", area="X", type="LEAGUE"))
        ts = [Team(sport=Sport.SOCCER, name=f"PL T{i}") for i in range(8)]
        s.add_all(ts)
        s.flush()
        return [t.id for t in ts]


V22 = (0.5, 0.3, 0.2)
CAND = (0.6, 0.25, 0.15)


def _game(mid, ko, teams, status=MatchStatus.FINISHED, hs=1, as_=0, raw="FT", odds=True, pred=True, arm=True,
          version="v22", s90=None):
    """One PL game; finished ones carry two complete books one hour before kickoff (2.0 / 3.4 / 3.8) and, by
    default, a v22 prediction with the candidate's arm."""
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, Odds, Prediction
    fin = status == MatchStatus.FINISHED
    with session_scope() as s:
        c = s.query(Competition).filter_by(code="PL").one()
        s.add(Match(id=mid, sport=Sport.SOCCER, competition_id=c.id, season=SEASON, utc_date=ko, status=status,
                    home_team_id=teams[0], away_team_id=teams[1], home_score=hs if fin else None,
                    away_score=as_ if fin else None, status_raw=raw if fin else None,
                    home_score_90=(s90 or (hs, as_))[0] if fin else None,
                    away_score_90=(s90 or (hs, as_))[1] if fin else None,
                    external_ids={"api_football": str(5000 + mid)}))
        s.flush()
        if odds:
            for bk in ("bk1", "bk2"):
                for sel, px in (("HOME", 2.0), ("DRAW", 3.4), ("AWAY", 3.8)):
                    s.add(Odds(match_id=mid, bookmaker=bk, market="1X2", selection=sel, price_decimal=px,
                               captured_at=ko - timedelta(hours=1)))
        if pred:
            fb = {"home_injuries_count": 3, "away_injuries_count": 1}
            if arm:
                fb[pa.FB_KEY] = {"version": pa.EID, "base_version": "v22", "p_home": CAND[0], "p_draw": CAND[1],
                                 "p_away": CAND[2], "missing": {"home": {"model": 3, "candidate": 1},
                                                                "away": {"model": 1, "candidate": 0}}}
            s.add(Prediction(match_id=mid, model_version=version, home_win_prob=V22[0], draw_prob=V22[1],
                             away_win_prob=V22[2], factor_breakdown=fb, computed_at=ko - timedelta(hours=2)))


def _members(teams, n, base=100, start=OPENS):
    pairs = list(itertools.permutations(teams, 2))
    for i in range(n):
        _game(base + i, start + timedelta(hours=6 * i), pairs[i % len(pairs)])


def test_the_reader_refuses_while_window_opens_at_is_null(iso_db, ledger):
    ledger(window_opens_at=None)
    _pl()
    res = pa.read(now=NOW)
    assert "window_opens_at is null" in res["refused"]
    assert pa.lines(res, NOW)[-1].startswith("REFUSED: pl-availability-v1: window_opens_at is null")
    ledger(None)
    assert "no registry entry pl-availability-v1" in pa.read(now=NOW)["refused"]
    ledger(window_opens_at="2026-11-07")
    assert "is not a UTC instant" in pa.read(now=NOW)["refused"]
    ledger(window_opens_at="2026-10-31T12:00:00Z")
    assert "is not after declared_at" in pa.read(now=NOW)["refused"]


def test_the_real_entry_refuses_the_reader():
    res = pa.read(now=NOW)
    assert "window_opens_at is null" in res["refused"]


def test_membership_counts_by_cause_and_prints_counts_only(iso_db, ledger):
    t = _pl()
    _game(1, OPENS - timedelta(hours=1), t[:2])                              # before the window: never in it
    _game(2, OPENS, t[2:4])                                                  # the first kickoff: a member
    _game(3, OPENS + timedelta(hours=1), t[:2], status=MatchStatus.CANCELLED, pred=False, odds=False)
    _game(4, OPENS + timedelta(hours=2), t[:2], raw="AWD")
    _game(5, OPENS + timedelta(hours=3), t[:2], odds=False)                  # no close
    _game(6, OPENS + timedelta(hours=4), t[:2], pred=False)                  # no v22 prediction
    _game(7, OPENS + timedelta(hours=5), t[:2], arm=False)                   # no candidate arm
    _game(8, OPENS + timedelta(hours=6), t[:2], version="v21")               # another model's row
    _game(9, OPENS + timedelta(hours=7), t[:2], status=MatchStatus.POSTPONED, pred=False, odds=False)
    _game(10, OPENS + timedelta(hours=8), t[:2], s90=(0, 0))                 # FT scores disagree: pending
    _game(11, OPENS + timedelta(hours=9), t[:2], status=MatchStatus.LIVE, pred=False, odds=False)
    _game(12, OPENS + timedelta(hours=10), t[:2], status=MatchStatus.STALE_ORPHAN, pred=False, odds=False)
    _game(13, NOW - timedelta(hours=2), t[:2], status=MatchStatus.SCHEDULED, pred=False, odds=False)   # un-ingested
    _game(14, NOW + timedelta(days=2), t[:2], status=MatchStatus.SCHEDULED, pred=False, odds=False)    # to come
    res = pa.read(now=NOW)
    assert res["members"] == [2] and res["n"] == 1 and res["state"] == "accruing"
    assert res["before_window"] == 1 and res["stored_games"] == 14 and res["not_placed"] == 1
    assert dict(res["excluded"]) == {"cancelled": 1, "awarded": 1, "no_close": 1, "no_v22_prediction": 1,
                                     "no_candidate_arm": 1, "not_base_version": 1, "stale_orphan": 1}
    assert dict(res["pending"]) == {"score_disagreement": 1, "live": 1, "uningested": 1}
    assert res["to_come"] == 1 and res["blocking"] == 4
    out = pa.lines(res, NOW)
    assert "members 1 of 60 · state accruing" in out[1]
    assert not any(FORBIDDEN.search(ln) for ln in out), out


def test_the_60th_member_makes_it_ready_and_the_read_is_the_one_read(iso_db, ledger):
    t = _pl()
    _members(t, 61)
    res = pa.read(now=NOW)
    assert res["n"] == 60 and res["state"] == "ready" and res["members"] == list(range(100, 160))
    assert any("READY" in ln for ln in pa.lines(res, NOW)) and not any(FORBIDDEN.search(ln)
                                                                       for ln in pa.lines(res, NOW))
    out = pa.score(res, now=NOW)                                              # every member finished 1-0
    assert out["n"] == 60 and out["match_ids"] == res["members"]
    assert out["ll_v22"] == pytest.approx(-math.log(0.5)) and out["ll_candidate"] == pytest.approx(-math.log(0.6))
    assert out["verdict"] == "PASS" and out["diff"] >= pa.BAR
    fair_h = (1 / 2.0) / (1 / 2.0 + 1 / 3.4 + 1 / 3.8)
    assert out["ll_close"] == pytest.approx(-math.log(fair_h))
    assert out["brier_v22"] == pytest.approx(((0.5 - 1) ** 2 + 0.3 ** 2 + 0.2 ** 2) / 3)
    assert out["brier_candidate"] == pytest.approx(((0.6 - 1) ** 2 + 0.25 ** 2 + 0.15 ** 2) / 3)
    assert sum(c["games"] for c in out["clubs"].values()) == 120
    assert sum(c["model_missing"] for c in out["clubs"].values()) == 60 * 4
    assert sum(c["candidate_missing"] for c in out["clubs"].values()) == 60 * 1
    text = pa.read_lines(out)
    assert "VERDICT: PASS" in text[2] and "gating nothing" in text[3] and pa.VERDICT_TEXT in text[-1]


def test_waiting_with_a_game_before_the_60th_pending(iso_db, ledger):
    t = _pl()
    _members(t, 30)
    _game(500, OPENS + timedelta(hours=6 * 30), t[:2], status=MatchStatus.LIVE, pred=False, odds=False)
    _members(t, 30, base=200, start=OPENS + timedelta(hours=6 * 31))
    res = pa.read(now=NOW)
    assert res["n"] == 60 and res["state"] == "waiting"
    with pytest.raises(pa.WindowRefused, match="the one read is at the 60th member"):
        pa.score(res, now=NOW)


def test_the_bar_reads_at_least_and_a_tie_rejects():
    assert pa.verdict(0.7, 0.7) == "REJECT"                                  # a tie
    assert pa.verdict(0.7, 0.6951) == "REJECT"                               # 0.0049
    assert pa.verdict(0.7, 0.6949) == "PASS"
    assert pa.verdict(1.0, 0.995) == "PASS"
    assert (pa.BAR - 0.0) == pa.BAR and pa.verdict(pa.BAR, 0.0) == "PASS"  # exactly the bar passes: "by at least"
    assert pa.verdict(math.nextafter(pa.BAR, 0.0), 0.0) == "REJECT"          # a hair under it rejects
    assert pa.verdict(0.6, 0.7) == "REJECT"


def test_the_script_counts_then_reads_once(iso_db, ledger, monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'iso.db'}")
    t = _pl()
    _members(t, 59)
    assert script.main([]) == 0
    out = capsys.readouterr().out
    assert "members 59 of 60 · state accruing" in out and not FORBIDDEN.search(out)
    assert script.main(["--read"]) == 2 and "REFUSED: the one read is at the 60th" in capsys.readouterr().out
    _members(t, 1, base=300, start=OPENS + timedelta(hours=6 * 59))
    assert script.main(["--read"]) == 0
    out = capsys.readouterr().out
    assert "reserved:" in out and "VERDICT: PASS" in out
    assert script.main(["--read"]) == 2 and "the one read is spent" in capsys.readouterr().out
    ledger(window_opens_at=None)
    assert script.main([]) == 2
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'none.db'}")
    assert script.main([]) == 2 and "never creates one" in capsys.readouterr().out
    assert not (tmp_path / "none.db").exists()


# ============================================================================================ the grader's arm --

def _graded(mid, ko, teams):
    from src.db.database import session_scope
    from src.db.schema import Prediction, PredictionOutcome, Result
    _game(mid, ko, teams)
    with session_scope() as s:
        p = s.query(Prediction).filter_by(match_id=mid).one()
        s.add(PredictionOutcome(prediction_id=p.id, actual_result=Result.HOME, actual_home_score=1,
                                actual_away_score=0, top_pick_hit=True, log_loss=-math.log(0.5)))


def _results():
    from src.walters.export import export_results
    return json.loads(export_results(sport=Sport.SOCCER, start_date=datetime(2026, 10, 1),
                                     end_date=datetime(2027, 1, 1), competition_code="PL"))["results"]


def test_the_grader_arm_is_fenced_on_the_window_then_scored_after_the_verdict(iso_db, ledger, monkeypatch):
    t = _pl()
    _graded(1, OPENS - timedelta(hours=3), t[:2])                            # before the window
    _graded(2, OPENS + timedelta(hours=3), t[2:4])                           # a window game
    lap = {r["match_id"]: r for r in _results()}
    assert not any("candidate" in r for r in lap.values())                   # off the host: absent
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "host")
    rows = {r["match_id"]: r for r in _results()}
    assert {k: v for k, v in rows[2].items() if k != "candidate"} == lap[2]  # predicted / graded unchanged
    assert rows[2]["candidate"] == {"version": pa.EID, "fenced": rows[2]["candidate"]["fenced"]}
    assert pa.FENCE_TEXT in rows[2]["candidate"]["fenced"]
    one = rows[1]["candidate"]
    assert one["probabilities"] == {"home_win": 0.6, "draw": 0.25, "away_win": 0.15}
    assert one["log_loss"] == pytest.approx(-math.log(0.6))
    assert one["brier_score"] == pytest.approx(((0.6 - 1) ** 2 + 0.25 ** 2 + 0.15 ** 2) / 3)
    assert one["missing"] == {"home": {"model": 3, "candidate": 1}, "away": {"model": 1, "candidate": 0}}
    assert rows[1]["graded"]["log_loss"] == pytest.approx(-math.log(0.5))   # v22's own, unchanged
    ledger(verdict={"verdict": "PASS"})
    rows = {r["match_id"]: r for r in _results()}
    assert rows[2]["candidate"]["log_loss"] == pytest.approx(-math.log(0.6))
    ledger(window_opens_at=None)                                             # no window yet: cut at declared_at
    rows = {r["match_id"]: r for r in _results()}
    assert "fenced" in rows[1]["candidate"] and "fenced" in rows[2]["candidate"]


def test_the_grader_arm_is_pl_only_on_the_host(host):
    pred = SimpleNamespace(factor_breakdown={pa.FB_KEY: {"version": pa.EID, "base_version": "v22", "p_home": 0.5,
                                                         "p_draw": 0.3, "p_away": 0.2}})
    oc = SimpleNamespace(actual_result=SimpleNamespace(value="H"))
    for code in ("SA", "BL1", "ELC", None):
        m = SimpleNamespace(season="2025/26", utc_date=KICK, competition=SimpleNamespace(code=code))
        assert pa.result_arm(None, pred, oc, m) is None
    m = SimpleNamespace(season="2025/26", utc_date=KICK, competition=SimpleNamespace(code="PL"))
    assert pa.result_arm(None, pred, oc, m)["log_loss"] == pytest.approx(-math.log(0.5))


# ============================================================================================ the reservation --

def test_the_reservation_calls_the_cross_ref_guard_before_it_writes(ledger, monkeypatch):
    seen = []

    def guard(eid, no_fetch=False, repo=None):
        seen.append((eid, no_fetch, Path(pa.reservation_path()).exists()))
        return "cross-ref guard: stub"
    monkeypatch.setattr(reg, "cross_ref_guard", guard)
    p = pa.reserve(NOW, no_fetch=True, echo=seen.append)
    assert seen == [(pa.EID, True, False), "cross-ref guard: stub"]       # before the file exists; receipt echoed
    assert json.loads(Path(p).read_text()) == {"id": pa.EID, "started_at": "2027-01-20T12:00:00Z",
                                               "guard": "cross-ref guard: stub"}
    with pytest.raises(pa.WindowRefused, match="the one read is spent"):
        pa.reserve(NOW)


def test_a_reservation_held_on_another_ref_refuses_and_writes_nothing(ledger, monkeypatch):
    def refuse(eid, no_fetch=False, repo=None):
        raise reg.CrossRefRefused(f"{eid}: the cross-ref guard (#329) found a reservation on ref remotes/origin/"
                                  "laptop/x at commit abc")
    monkeypatch.setattr(reg, "cross_ref_guard", refuse)
    with pytest.raises(pa.WindowRefused, match="a reservation on ref remotes/origin/laptop/x"):
        pa.reserve(NOW)
    assert not Path(pa.reservation_path()).exists()


def test_a_failed_reservation_write_spends_nothing(ledger, monkeypatch):
    def boom(*a, **k):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(pa.json, "dump", boom)
    with pytest.raises(pa.WindowRefused, match="the file is removed: the one read is not spent"):
        pa.reserve(NOW)
    assert not Path(pa.reservation_path()).exists()
    monkeypatch.setattr(pa.os, "remove", lambda p: (_ for _ in ()).throw(OSError("read-only")))
    with pytest.raises(pa.WindowRefused, match="could NOT be removed"):
        pa.reserve(NOW)


def test_the_script_passes_no_fetch_to_the_reservation(iso_db, ledger, monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'iso.db'}")
    seen = []
    monkeypatch.setattr(reg, "cross_ref_guard", lambda eid, no_fetch=False, repo=None: seen.append(no_fetch) or "g")
    t = _pl()
    _members(t, 60)
    assert script.main(["--read", "--no-fetch"]) == 0 and seen == [True]
    assert "  g" in capsys.readouterr().out


def test_a_window_game_that_failed_its_candidate_is_excluded_by_its_own_cause(iso_db, ledger):
    from src.db.database import session_scope
    from src.db.schema import Prediction
    t = _pl()
    _game(1, OPENS, t[:2])
    _game(2, OPENS + timedelta(hours=1), t[:2], arm=False)
    with session_scope() as s:
        p = s.query(Prediction).filter_by(match_id=2).one()
        p.factor_breakdown = {**p.factor_breakdown, pa.FB_KEY: pa.failed_block("v22", RuntimeError("x"))}
    res = pa.read(now=NOW)
    assert res["members"] == [1] and dict(res["excluded"]) == {"candidate_failed": 1}
    assert "the candidate failed on the host (stored error) 1" in pa.lines(res, NOW)[3]


# ====================================================================== the #430 injury receipt, fenced --

def test_the_injury_factor_receipt_leaves_fenced_pl_games_out(iso_db, ledger):
    from src.db.database import session_scope
    spec = importlib.util.spec_from_file_location("sifr", ROOT / "scripts" / "soccer_injury_factor_receipt.py")
    rc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rc)
    t = _pl()
    _graded(1, OPENS - timedelta(hours=3), t[:2])                            # before the cut: read (then skipped)
    _graded(2, OPENS + timedelta(hours=3), t[2:4])                           # a window game: fenced, counted
    with session_scope() as s:
        rs, skipped = rc.rows(s, "PL")
    assert rs == [] and skipped[rc.FENCED] == 1 and skipped["no expected goals"] == 1
    ledger(verdict={"verdict": "REJECT"})                                    # the verdict lifts it
    with session_scope() as s:
        _, skipped = rc.rows(s, "PL")
    assert rc.FENCED not in skipped and skipped["no expected goals"] == 2
