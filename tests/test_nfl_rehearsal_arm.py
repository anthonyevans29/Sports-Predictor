"""nfl-elo-v2's REHEARSAL ARM (ARCHITECT 2026-11-03 09:00 ET, addendum 230 item 1(a), as ruled by ARCHITECT 2026-11-04
09:55 ET, addendum 247 items 2-3; src/walters/nfl_rehearsal.py, docs/specs/nfl-rehearsal-arm.md).

Pins: (1) THE STATE: the shape read is exactly status "rehearsal" + rehearsal_window {opens_at, closes_at} (two UTC
instants ending in Z) + the architect's verdict PASS; 247's ruled instants read on, the week-11 MNF (2026-11-24T01:15Z)
inside, opens_at included and closes_at excluded; the instants are read from the entry, never defaulted; every other
reading dormant with its reason (null / FAIL / REJECT verdict, PASS without the status, the window absent or
malformed, off the host, no entry, an unreadable registry, an undeclared term, drifted constants); the real registry
reads dormant and is never written; (2) dormant end to end: nothing stored, and the slate, closing and results files
equal the files with this module's writers stubbed out; (3) on: v1's rows unchanged; the arm is v1's live walk under
the declared term (h 33.0 on price AND update; a shrink, price only); the GAME'S KICKOFF opens the window (a row
written before the window for a game inside it carries the arm, a game outside never does); the rows carry the
rehearsal_* keys, labelled with the entry id, the term, the verdict stamp and "rehearsal — not a call"; (4) the
results export reads EVERY stored arm row, whatever the registry reads after the window (host only), with both arms'
log-loss (the gate's arithmetic, a tie a home loss), Brier (the same y), W-L-P and vs-close (a tie a push) per game
week, checked by hand; (5) THE PARITY: on the synthetic stream the arm's live walk's 2025 probabilities EQUAL the
gate's scored ones game for game (walked both ways), and game_log_loss reproduces walk_protocol's figure to the bit;
(6) THE DESK PIN: desk_meta, every desk block, closing.desk_rows (would_be_for), exec_cohorts.would_be_play and the phone
page are byte-identical bare / armed / loud, and no Desk code names the keys; the closing summary block and the run
receipt carry one arm line and the phone page none (223 item 3's placement); (7) the compare masks the keys under its
own line, beside the pl-availability line, which is unchanged; (8) the rulings verbatim in the spec and the entry;
(9) the synthetic page (printed with -s for the PR body).

Throwaway SQLite files only (tests/nfl_v2_world.fresh) and tmp registries (registry.LEDGER monkeypatched); the real
docs/registry/experiments.json is read, never written.
"""
from __future__ import annotations

import copy
import inspect
import json
import math
import re
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.walters import nfl_rehearsal as reh
from src.walters import registry as reg

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))

PASS = {"verdict": "PASS", "ruling": "ARCHITECT 2026-11-06 (synthetic)", "at": "2026-11-06T19:00:00Z"}
RULED_WINDOW = {"opens_at": "2026-11-12T00:00:00Z", "closes_at": "2026-11-24T06:00:00Z"}    # 247 item 2(1), verbatim
REAL_REGISTRY = str(ROOT / "docs" / "registry" / "experiments.json")                         # read, never written
LABEL = "rehearsal — not a call"                                                             # 247 item 3, written out
LINE = "rehearsal-arm keys (host-only, nfl-elo-v2): "
SHADOW = "shadow-arm keys (host-only, pl-availability-v1): "


@pytest.fixture
def host(monkeypatch, tmp_path):
    """This machine reads as the host (desk_policy.not_host_reason() is None)."""
    monkeypatch.setenv("SP_HOST_ENV", str(tmp_path / "no-host.env"))
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "host")


def real_entry() -> dict:
    return copy.deepcopy(reg.get(reh.EID, REAL_REGISTRY))


def entry(**kw) -> dict:
    """The real entry (declared, h 33.0 on main since #822) with the shape the verdict-record PR writes on PASS."""
    e = real_entry()
    e.update({"verdict": dict(PASS), "status": "rehearsal", "rehearsal_window": dict(RULED_WINDOW)})
    e.update(kw)
    return e


def z(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


# ============================================================================================ (1) the state --

def test_the_ruled_shape_reads_on_and_the_instants_are_247s():
    assert real_entry()["calibration_term"]["home_advantage"] == 33.0          # #822 on main: the declared term
    g = reh.state(entry())
    assert g.on and g.why is None
    assert g.stamp == "nfl-elo-v2 PASS 2026-11-06T19:00:00Z" and g.term == {"form": "home_advantage", "value": 33.0}
    assert (g.opens_at, g.closes_at) == (datetime(2026, 11, 12, 0, 0), datetime(2026, 11, 24, 6, 0))
    assert reh.STATUS == "rehearsal" and reh.WINDOW_KEY == "rehearsal_window"
    assert reh.WINDOW_FIELDS == ("opens_at", "closes_at")
    assert f'`status: "rehearsal"`' in reh.RULING_247_TEXT[1]
    assert f"`rehearsal_window: {json.dumps(RULED_WINDOW)}`" in reh.RULING_247_TEXT[1]


@pytest.mark.parametrize("kickoff,inside", [
    (datetime(2026, 11, 11, 23, 59, 59), False),          # a second before opens_at
    (datetime(2026, 11, 12, 0, 0), True),                 # opens_at: included
    (datetime(2026, 11, 13, 1, 15), True),                # week 10's TNF (11-12 ET)
    (datetime(2026, 11, 24, 1, 15), True),                # week 11's MNF (11-23 ET): its last game, INCLUDED
    (datetime(2026, 11, 24, 5, 59, 59), True),
    (datetime(2026, 11, 24, 6, 0), False),                # closes_at: excluded
    (datetime(2026, 11, 27, 1, 20), False),               # week 12: after
    (datetime(2026, 11, 24, 1, 15, tzinfo=timezone.utc), True),   # an aware kickoff reads as its UTC instant
    (None, False),
])
def test_the_games_kickoff_opens_the_window_opens_at_in_closes_at_out(kickoff, inside):
    assert reh.state(entry()).covers(kickoff) is inside


def test_the_instants_are_read_from_the_entry_never_defaulted():
    g = reh.state(entry(rehearsal_window={"opens_at": "2026-12-01T00:00:00Z", "closes_at": "2026-12-08T00:00:00Z"}))
    assert g.on and not g.covers(datetime(2026, 11, 24, 1, 15)) and g.covers(datetime(2026, 12, 3, 18, 0))
    e = entry()
    del e["rehearsal_window"]
    assert not reh.state(e).on                                                # no fallback window
    import ast
    tree = ast.parse((ROOT / "src" / "walters" / "nfl_rehearsal.py").read_text())
    consts = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert not any(c.strip() in RULED_WINDOW.values() for c in consts)       # quoted in prose only, never a value
    assert not any(isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", "")) == "datetime"
                   for n in ast.walk(tree))                                  # no instant built in code
    assert all(t in reh.RULING_247_TEXT[1] for t in RULED_WINDOW.values())


FAIL = {"verdict": "FAIL", "ruling": "x", "at": "2026-11-06T19:00:00Z"}


@pytest.mark.parametrize("kw,why", [
    ({"verdict": None}, "verdict reads null, not PASS"),
    ({"verdict": FAIL}, "verdict reads FAIL, not PASS"),
    ({"verdict": {**FAIL, "verdict": "REJECT"}}, "verdict reads REJECT"),
    ({"verdict": "PASS"}, "verdict reads null"),                                       # not the record's shape
    ({"verdict": {"verdict": "PASS", "ruling": "x"}}, "no verdict stamp"),
    ({"status": "confirming"}, "status reads 'confirming', not 'rehearsal'"),           # record_verdict's PASS status
    ({"status": "run"}, "status reads 'run'"),
    ({"status": "declared"}, "status reads 'declared'"),
    ({"rehearsal_window": None}, "is not exactly {opens_at, closes_at}"),
    ({"rehearsal_window": {"opens_at": "2026-11-12T00:00:00Z"}}, "is not exactly {opens_at, closes_at}"),
    ({"rehearsal_window": {**RULED_WINDOW, "note": "x"}}, "is not exactly {opens_at, closes_at}"),
    ({"rehearsal_window": {"opens_at": "2026-11-12", "closes_at": "2026-11-24"}}, "is not two UTC instants"),
    ({"rehearsal_window": {"opens_at": "2026-11-12T00:00:00", "closes_at": "2026-11-24T06:00:00Z"}},
     "is not two UTC instants"),
    ({"rehearsal_window": {"opens_at": "2026-11-12T00:00:00+00:00", "closes_at": "2026-11-24T06:00:00Z"}},
     "is not two UTC instants"),
    ({"rehearsal_window": {"opens_at": "2026-11-12T00:00:00-05:00Z", "closes_at": "2026-11-24T06:00:00Z"}},
     "is not two UTC instants"),
    ({"rehearsal_window": {"opens_at": 1, "closes_at": "2026-11-24T06:00:00Z"}}, "is not two UTC instants"),
    ({"rehearsal_window": {"opens_at": "2026-11-24T06:00:00Z", "closes_at": "2026-11-12T00:00:00Z"}},
     "opens at or after it closes"),
    ({"rehearsal_window": {"opens_at": "2026-11-24T06:00:00Z", "closes_at": "2026-11-24T06:00:00Z"}},
     "opens at or after it closes"),
])
def test_every_other_reading_is_dormant_with_its_reason(kw, why):
    g = reh.state(entry(**kw))
    assert not g.on and why in g.why
    assert not g.covers(datetime(2026, 11, 15, 18, 0)) and g.stamp is None and g.term is None


def test_off_the_host_no_entry_an_undeclared_term_or_drifted_constants_are_dormant():
    assert reh.state(entry(), "this machine's role is laptop").why == (
        "nfl-elo-v2's rehearsal arm runs on the host only: this machine's role is laptop")
    assert reh.state(None).why == "no nfl-elo-v2 entry in the registry"
    assert reh.state({**entry(), "id": "nfl-elo-v1"}).why == "no nfl-elo-v2 entry in the registry"
    e = entry()
    e["calibration_term"] = {**e["calibration_term"], "home_advantage": None}
    assert "the calibration term is not declared" in reh.state(e).why
    e = entry()
    e["constants"] = {**e["constants"], "k_factor": 21.0}
    assert "frozen constants differ" in reh.state(e).why


def test_a_fail_names_the_ruling_verbatim_and_leaves_every_line_dormant():
    g = reh.state(entry(verdict=FAIL, status="closed"))
    assert f'"{reh.DORMANT_TEXT}"' in g.why and reh.DORMANT_TEXT in reh.RULING_230_TEXT


def test_the_registry_read_never_raises_and_the_real_one_reads_dormant(tmp_path, monkeypatch, host):
    p = tmp_path / "experiments.json"
    p.write_text("[]")
    assert reh.read_gate(str(p)).why == "no nfl-elo-v2 entry in the registry"
    p.write_text("{not json")
    assert "cannot be read (JSONDecodeError)" in reh.read_gate(str(p)).why
    p.write_text("{}")
    assert "not a list of entries" in reh.read_gate(str(p)).why
    p.write_text(json.dumps([entry()]))
    assert reh.read_gate(str(p)).on
    # the real registry since 2026-11-06 (ARCHITECT 08:55 ET, addendum 265): the one run recorded and the verdict FAIL
    # (status closed); 265 item 3: "the rehearsal arm (#825) is DORMANT for the season — on FAIL nothing is written
    # (247 item 2(1)) and no window opens"
    g = reh.read_gate(REAL_REGISTRY)
    assert not g.on and "verdict reads FAIL, not PASS" in g.why and f'"{reh.DORMANT_TEXT}"' in g.why
    assert g.opens_at is None and g.closes_at is None and g.term is None
    e = real_entry()
    assert e["status"] == "closed" and e["verdict"]["verdict"] == "FAIL" and e["run"]["n_scored"] == 285
    assert reh.WINDOW_KEY not in e and e["status"] != reh.STATUS                # nothing of the PASS path is written

    def boom(*a, **k):
        raise RuntimeError("synthetic")
    monkeypatch.setattr(reg, "load", boom)
    assert reh.read_gate(str(p)).why.startswith("the gate could not be read (RuntimeError: synthetic)")


def test_off_the_host_the_real_and_a_passing_registry_read_dormant(tmp_path):
    p = tmp_path / "experiments.json"
    p.write_text(json.dumps([entry()]))
    for path in (str(p), REAL_REGISTRY):
        assert reh.read_gate(path).why.startswith("nfl-elo-v2's rehearsal arm runs on the host only")


def test_the_module_never_writes_the_registry():
    src = (ROOT / "src" / "walters" / "nfl_rehearsal.py").read_text()
    for w in ("record_verdict(", "record_run(", ".save(", "declare(", "open(", "write_text"):
        assert w not in src


# ======================================================================================= the world: tmp DB --

@pytest.fixture
def world(tmp_path, monkeypatch, host):
    """The v2 harness's synthetic stream (2024, 2025 + extras) in a tmp DB, and three SCHEDULED 2026 NFL games in the
    next days (weeks 10, 10, 11), each with two complete books an hour before kickoff. A tmp registry holding one
    nfl-elo-v2 entry; set(**kw) rewrites it (set(None): none). By default the window is relative to the wall clock
    (opens a day ago, closes in ten days), so every game's kickoff is inside."""
    from src.db.schema import Match, MatchStatus, Odds
    from src.timeutil import utc_now_naive
    from tests import nfl_v2_world as w
    db = w.fresh(tmp_path / "w.db", monkeypatch)
    w.build(db)
    now = utc_now_naive().replace(microsecond=0)
    games, kick = [], []
    for dd, h, a, wk in [(2, 4, 5, 10), (2.1, 6, 7, 10), (3, 8, 9, 11)]:
        mid = w.add_game(db, "2026", now + timedelta(days=dd), h, a, None, None, status=MatchStatus.SCHEDULED)
        with db.session_scope() as s:
            m = s.get(Match, mid)
            m.matchday = wk
            kick.append(m.utc_date)
            for bk in ("bk1", "bk2"):
                for sel, px in (("HOME", 1.8), ("AWAY", 2.1)):
                    s.add(Odds(match_id=mid, bookmaker=bk, market="1X2", selection=sel, price_decimal=px,
                               captured_at=m.utc_date - timedelta(hours=1)))
        games.append(mid)
    path = tmp_path / "experiments.json"
    monkeypatch.setattr(reg, "LEDGER", str(path))

    def setreg(e="on", **kw):
        if e is None:
            path.write_text("[]")
            return
        win = {"opens_at": z(now - timedelta(days=1)), "closes_at": z(now + timedelta(days=10))}
        x = entry(rehearsal_window=win) if e == "on" else e
        x.update(kw)
        path.write_text(json.dumps([x]))
    setreg()
    return SimpleNamespace(db=db, now=now, games=games, kick=kick, set=setreg, tmp=tmp_path, w=w)


def _predict():
    from src.walters.nfl_predict import predict_nfl
    lines = []
    predict_nfl(progress=lines.append)
    return lines


def _stored(world):
    from sqlalchemy import select

    from src.db.schema import Prediction
    with world.db.session_scope() as s:
        return {p.match_id: (p.home_win_prob, p.away_win_prob, p.model_version, dict(p.factor_breakdown or {}))
                for p in s.execute(select(Prediction).where(Prediction.match_id.in_(world.games))).scalars()}


def _export(world, name="slate", desk=False):
    from src.walters.nfl_predict import export_nfl_predictions
    p = export_nfl_predictions(days_ahead=8, out_dir=str(world.tmp / name), desk=desk)
    return json.loads(Path(p).read_text())


def _finish(world, scores=((27, 10), (10, 27), (20, 20))):
    from src.db.schema import Match, MatchStatus
    with world.db.session_scope() as s:
        for mid, (hs, as_) in zip(world.games, scores):
            m = s.get(Match, mid)
            m.status, m.home_score, m.away_score = MatchStatus.FINISHED, hs, as_


def _results(world, name="res"):
    from src.walters.nfl_predict import export_nfl_results
    return json.loads(Path(export_nfl_results(out_dir=str(world.tmp / name))).read_text())


def _bare(doc: dict) -> dict:
    """The doc without its clocks (exported_at; the Desk's as_of)."""
    d = json.loads(json.dumps(doc))
    d.pop("exported_at", None)
    (d.get("desk_meta") or {}).pop("as_of", None)
    return d


def _stubbed(monkeypatch):
    """The code before this module: its writers return nothing."""
    monkeypatch.setattr(reh, "export_fields", lambda *a, **k: None)
    monkeypatch.setattr(reh, "result_arm", lambda *a, **k: None)
    monkeypatch.setattr(reh, "record_block", lambda *a, **k: None)


def _hand_walk(world, cfg, price_cfg=None, floor=None):
    """An independent walk: every FINISHED NFL non-preseason game with both scores, by kickoff then id, by
    nfl_backtest._update under `cfg` (written here, not nfl_predict._current_ratings); priced under `price_cfg`.
    `floor`: games of an earlier season (an int-style year) left out (251 item 3(3), written here by hand)."""
    from sqlalchemy import select

    from src.db.schema import Competition, Match, MatchStatus
    from src.walters import nfl_backtest as nb
    st = nb._State()
    with world.db.session_scope() as s:
        gs = s.execute(select(Match).join(Competition, Competition.id == Match.competition_id)
                       .where(Competition.code == "NFL", Match.status == MatchStatus.FINISHED,
                              Match.home_score.is_not(None), Match.away_score.is_not(None))
                       .order_by(Match.utc_date, Match.id)).scalars().all()
        for m in gs:
            if "pre" not in (m.stage or "").lower() and (floor is None or int(m.season) >= int(floor)):
                nb._update(cfg, st, m.home_team_id, m.away_team_id, m.season, m.home_score, m.away_score)
        pairs = {mid: (s.get(Match, mid).home_team_id, s.get(Match, mid).away_team_id) for mid in world.games}
    return {mid: nb._expected_home(price_cfg or cfg, st, h, a) for mid, (h, a) in pairs.items()}


# ================================================================================ (2) dormant, end to end --

@pytest.mark.parametrize("case", ["null", "fail", "pass_no_status", "no_window", "malformed", "before", "after",
                                  "closed", "no_entry", "off_host"])
def test_dormant_writes_nothing_and_every_file_equals_the_stubbed_code(world, monkeypatch, case):
    now = world.now
    if case == "null":
        world.set(verdict=None, status="declared")
    elif case == "fail":
        world.set(verdict=FAIL, status="closed")
    elif case == "pass_no_status":
        world.set(status="confirming")
    elif case == "no_window":
        world.set(rehearsal_window=None)
    elif case == "malformed":
        world.set(rehearsal_window={"opens_at": z(now - timedelta(days=1))[:10], "closes_at": z(now)})
    elif case == "before":                          # every kickoff before the window
        world.set(rehearsal_window={"opens_at": z(now + timedelta(days=20)), "closes_at": z(now + timedelta(days=30))})
    elif case == "after":                           # every kickoff after the window
        world.set(rehearsal_window={"opens_at": z(now - timedelta(days=10)), "closes_at": z(now + timedelta(days=1))})
    elif case == "closed":                          # 247 item 2(4): the window has closed; the export stops writing
        world.set(rehearsal_window={"opens_at": z(now - timedelta(days=10)), "closes_at": z(now - timedelta(days=1))})
    elif case == "no_entry":
        world.set(None)
    else:
        monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "laptop")
    lines = _predict()
    st = _stored(world)
    assert len(st) == 3 and all(fb == {} for *_, fb in st.values())         # nothing stored beside v1's row
    arm_lines = [x for x in lines if "rehearsal arm" in x]
    if case in ("before", "after", "closed"):    # the state reads on, no kickoff covered: the receipt says 0 of 0
        assert len(arm_lines) == 1 and ": 0 of 0 covered rows priced" in arm_lines[0]
    else:
        assert arm_lines == []
    slate, closing = _export(world, "a"), _export(world, "c", desk=True)
    with monkeypatch.context() as mp:
        _stubbed(mp)
        slate0, closing0 = _export(world, "a0"), _export(world, "c0", desk=True)
    _finish(world)
    res = _results(world, "r1")
    with monkeypatch.context() as mp:
        _stubbed(mp)
        res0 = _results(world, "r0")
    assert _bare(slate) == _bare(slate0) and _bare(closing) == _bare(closing0) and _bare(res) == _bare(res0)
    for d in (slate, closing, res):
        assert reh.PREFIX not in json.dumps(d)
    assert slate["rehearsal"] is False and "rehearsal" not in res                  # the fossil, untouched both ways


# ============================================================================================= (3) the arm on --

def test_on_v1_is_unchanged_and_the_arm_is_v1s_live_walk_under_the_declared_term(world):
    from src.walters import nfl_backtest as nb
    from src.walters.nfl_backtest import NFLEloConfig
    world.set(verdict=None)
    _predict()
    v1_only = _stored(world)
    world.set()
    lines = _predict()
    st = _stored(world)
    hand2 = _hand_walk(world, replace(NFLEloConfig(), home_advantage=33.0))
    hand1 = _hand_walk(world, NFLEloConfig())
    upd48 = _hand_walk(world, NFLEloConfig(), replace(NFLEloConfig(), home_advantage=33.0))   # update at 48 only
    for mid in world.games:
        h, a, mv, fb = st[mid]
        assert (h, a, mv) == v1_only[mid][:3] and mv == "nfl_elo_v1" and h == round(hand1[mid], 4)   # v1, unchanged
        arm = fb[reh.FB_KEY]
        assert arm == {"version": "nfl-elo-v2", "model_version": "nfl_elo_v2", "p_home": hand2[mid],
                       "p_away": 1 - hand2[mid], "term": {"form": "home_advantage", "value": 33.0},
                       "verdict": "PASS", "verdict_at": PASS["at"]}                # FULL precision (Codex on #825)
        assert round(arm["p_home"], 4) != h and arm["p_home"] != upd48[mid]      # the term on price AND update
    assert lines[-1].startswith("rehearsal arm nfl-elo-v2 (nfl-elo-v2 PASS 2026-11-06T19:00:00Z, home_advantage "
                                "33.0): 3 of 3 covered rows priced")
    assert lines[-1].endswith(LABEL) and nb.NFLEloConfig().home_advantage == 48.0      # no constant moved


def test_on_a_shrink_term_prices_only(world):
    from src.walters.nfl_backtest import NFLEloConfig
    e = entry(rehearsal_window={"opens_at": z(world.now - timedelta(days=1)),
                                "closes_at": z(world.now + timedelta(days=10))})
    e["calibration_term"] = {**e["calibration_term"], "form": "shrink", "shrink": 0.8, "home_advantage": None}
    world.set(e)
    _predict()
    hand = _hand_walk(world, NFLEloConfig())
    for mid, (h, _, _, fb) in _stored(world).items():
        assert fb[reh.FB_KEY]["p_home"] == 0.5 + 0.8 * (hand[mid] - 0.5) and h == round(hand[mid], 4)


def test_a_row_written_before_the_window_for_a_game_inside_carries_the_arm_one_outside_never(world):
    """247 item 2(3): the GAME'S KICKOFF opens the window. The window opens after the predict run and the export (the
    clock) but before games 1-2's kickoffs and closes before game 3's: games 1-2 carry the arm, game 3 never."""
    g1, g2, g3 = world.games
    win = {"opens_at": z(world.now + timedelta(days=1)), "closes_at": z(world.kick[2] - timedelta(hours=1))}
    world.set(rehearsal_window=win)
    _predict()
    st = _stored(world)
    assert reh.FB_KEY in st[g1][3] and reh.FB_KEY in st[g2][3] and st[g3][3] == {}
    for doc in (_export(world, "a"), _export(world, "c", desk=True)):
        rows = {r["match_id"]: r for r in doc["predictions"]}
        assert rows[g1]["rehearsal_probabilities"] is not None and rows[g2]["rehearsal_reason"] is None
        assert not any(k.startswith(reh.PREFIX) for k in rows[g3])
    world.set(rehearsal_window={"opens_at": win["opens_at"], "closes_at": z(world.kick[2] + timedelta(hours=1))})
    rows = {r["match_id"]: r for r in _export(world, "b")["predictions"]}
    assert rows[g3]["rehearsal_probabilities"] is None and "carries no rehearsal arm" in rows[g3]["rehearsal_reason"]


def test_on_the_slate_and_closing_rows_carry_the_rehearsal_keys_beside_v1(world):
    world.set()
    _predict()
    st = _stored(world)
    for doc in (_export(world, "a"), _export(world, "c", desk=True)):
        assert doc["rehearsal"] is False and doc["model_version"] == "nfl_elo_v1" and len(doc["predictions"]) == 3
        for r in doc["predictions"]:
            fb = st[r["match_id"]][3][reh.FB_KEY]
            assert {k: r[k] for k in reh.ROW_KEYS} == {
                "rehearsal_version": "nfl-elo-v2",
                "rehearsal_probabilities": {"home_win": round(fb["p_home"], 4),        # presented at four places
                                            "away_win": round(fb["p_away"], 4)},
                "rehearsal_term": {"form": "home_advantage", "value": 33.0},
                "rehearsal_verdict_stamp": "nfl-elo-v2 PASS 2026-11-06T19:00:00Z",
                "rehearsal_label": LABEL, "rehearsal_reason": None}
            assert [k for k in r if k.startswith(reh.PREFIX)] == list(reh.ROW_KEYS)
            assert not any(k.startswith("candidate") for k in r)                 # never pl-availability-v1's keys
            assert r["prediction"]["model_version"] == "nfl_elo_v1" and r["prediction"]["home_win_prob"] == \
                st[r["match_id"]][0]
            assert reh.PREFIX not in json.dumps(r["prediction"]) and reh.FB_KEY not in json.dumps(r)


def test_on_a_missing_failed_or_restamped_arm_says_why_and_never_shows_a_probability(world, monkeypatch):
    world.set(verdict=None)
    _predict()                                                            # stored while dormant: no arm
    world.set()
    r = _export(world, "a")["predictions"][0]
    assert r["rehearsal_probabilities"] is None and r["rehearsal_reason"].startswith(
        "the stored prediction carries no rehearsal arm")
    from src.walters import nfl_predict as npd
    real = npd._current_ratings

    def boom(progress=None, cfg=None, floor=None, receipt=None):
        if cfg is not None:
            assert floor == reh.WALK_FLOOR and receipt == {}                  # the arm's walk, from the floor
            raise RuntimeError("synthetic walk failure")
        assert floor is None and receipt is None                            # v1's walk: no floor, as before
        return real(progress)
    monkeypatch.setattr(npd, "_current_ratings", boom)
    lines = _predict()
    st = _stored(world)
    assert all(fb[reh.FB_KEY]["error"] == "RuntimeError: synthetic walk failure" and h is not None
               for h, _, _, fb in st.values())                              # v1's rows written as always
    assert "0 of 3 covered rows priced" in lines[-1]
    assert "walk floor 2024; the stored games before it were not counted (the walk's read failed)" in lines[-1]
    r = _export(world, "b")["predictions"][0]
    assert r["rehearsal_probabilities"] is None and "the second walk failed" in r["rehearsal_reason"]
    monkeypatch.setattr(npd, "_current_ratings", real)
    _predict()
    world.set(verdict={**PASS, "at": "2026-11-07T10:00:00Z"})              # another stamp than the stored arm's
    r = _export(world, "c")["predictions"][0]
    assert r["rehearsal_probabilities"] is None and "another verdict stamp" in r["rehearsal_reason"]
    assert r["rehearsal_verdict_stamp"] == "nfl-elo-v2 PASS 2026-11-07T10:00:00Z"


# ======================================================================= (4) the grader's second arm, by hand --

def _ll(p, y):
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def test_the_results_rows_and_the_record_per_week_by_hand(world):
    from src.walters import vs_close as vc
    world.set()
    _predict()
    st = _stored(world)
    _finish(world)                                                          # week 10: home win, away win; 11: a tie
    doc = _results(world)
    rows = {r["match_id"]: r for r in doc["results"]}
    g1, g2, g3 = world.games
    p1 = {m: st[m][0] for m in world.games}
    p2 = {m: st[m][3][reh.FB_KEY]["p_home"] for m in world.games}
    y = {g1: 1, g2: 0, g3: 0}                                              # the gate's y: the tie a home loss
    for m in world.games:
        a = rows[m][reh.RESULT_KEY]
        assert a["p_home"] == p2[m] and a["home_win_prob"] == round(p2[m], 4)      # graded full, presented at four
        assert a["away_win_prob"] == round(1 - p2[m], 4) and p2[m] != round(p2[m], 4)
        assert a["verdict_stamp"] == "nfl-elo-v2 PASS 2026-11-06T19:00:00Z"
        assert a["label"] == LABEL and a["term"] == {"form": "home_advantage", "value": 33.0}
        assert a["log_loss"] == round(_ll(p2[m], y[m]), 4) and a["brier_score"] == round((p2[m] - y[m]) ** 2, 4)
        assert rows[m]["graded"]["log_loss"] == round(_ll(p1[m], y[m]), 4)    # v1's, the same convention
    assert rows[g3][reh.RESULT_KEY]["push"] is True and rows[g3][reh.RESULT_KEY]["top_pick_hit"] is None
    fair_h = (1 / 1.8) / (1 / 1.8 + 1 / 2.1)
    fh, fa = round(fair_h, 4), round(1 - fair_h, 4)
    rec = doc["record"][reh.RECORD_KEY]
    assert rec["version"] == "nfl-elo-v2" and rec["label"] == LABEL and rec["rules"] == reh.RULES
    assert rec["verdict_stamps"] == ["nfl-elo-v2 PASS 2026-11-06T19:00:00Z"] and rec["terms"] == ["home_advantage 33.0"]
    assert (rec["unpriced_arm_rows"], rec["redated_arm_rows"]) == (0, 0) and list(rec["by_week"]) == ["10", "11"]
    for arm, p in (("v1", p1), ("v2", p2)):
        wk10, wk11, tot = rec["by_week"]["10"][arm], rec["by_week"]["11"][arm], rec["total"][arm]
        assert wk10["log_loss"] == round((_ll(p[g1], 1) + _ll(p[g2], 0)) / 2, 4)
        assert wk11["log_loss"] == round(_ll(p[g3], 0), 4)                    # the tie: a home loss, as the gate
        assert tot["log_loss"] == round((_ll(p[g1], 1) + _ll(p[g2], 0) + _ll(p[g3], 0)) / 3, 4)
        assert wk10["brier_score"] == round(((p[g1] - 1) ** 2 + p[g2] ** 2) / 2, 4)
        assert wk11["brier_score"] == round(p[g3] ** 2, 4)
        hits = (p[g1] >= 0.5) + (p[g2] < 0.5)
        assert (wk10["w"], wk10["l"], wk10["p"]) == (hits, 2 - hits, 0) and (wk11["w"], wk11["l"], wk11["p"]) == \
            (0, 0, 1)                                                          # the tie: a push
        want = {**vc.block([(p[g1], fh), (1 - p[g2], fa)]), "kalshi_only_closes": 0}
        assert wk10["vs_close"] == want and tot["vs_close"] == want            # the tie is a push: out
        assert wk11["vs_close"]["games"] == 0
    assert rec["total"]["v1"]["model_version"] == "nfl_elo_v1" and rec["total"]["v2"]["model_version"] == "nfl_elo_v2"
    assert doc["record"]["vs_close"] == rec["total"]["v1"]["vs_close"]          # v1's own record on the same games


def test_the_results_keep_reading_every_stored_arm_after_the_window_whatever_the_registry_reads(world, monkeypatch):
    """247 item 2(4): written once, read for the record always. After the games, the registry moves on (the window
    closed, the status changed, the entry gone): the stored arms are read and the record is the same."""
    world.set()
    _predict()
    _finish(world)
    on = _results(world, "on")
    for k, kw in enumerate(({"rehearsal_window": {"opens_at": z(world.now - timedelta(days=30)),
                                                  "closes_at": z(world.now - timedelta(days=20))}},
                            {"status": "production"}, {"verdict": FAIL, "status": "closed"}, None)):
        world.set(None) if kw is None else world.set(**kw)
        later = _results(world, f"later{k}")
        assert later["record"][reh.RECORD_KEY] == on["record"][reh.RECORD_KEY]
        assert [r.get(reh.RESULT_KEY) for r in later["results"]] == [r.get(reh.RESULT_KEY) for r in on["results"]]
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "laptop")                 # host-only: off the host, nothing read
    off = _results(world, "off")
    assert reh.PREFIX not in json.dumps(off)


def test_the_results_keep_v1s_record_and_rows_as_the_stubbed_code_writes_them(world, monkeypatch):
    world.set()
    _predict()
    _finish(world)
    on = _results(world, "on")
    with monkeypatch.context() as mp:
        _stubbed(mp)
        off = _results(world, "off")
    rec = dict(on["record"])
    rec.pop(reh.RECORD_KEY)
    assert rec == off["record"]
    for a, b in zip(on["results"], off["results"]):
        a = dict(a)
        a.pop(reh.RESULT_KEY)
        assert {k: v for k, v in a.items() if k != "graded_export"} == \
            {k: v for k, v in b.items() if k != "graded_export"}


def test_a_failed_arm_row_is_read_counted_and_out_of_the_figures(world, monkeypatch):
    world.set()
    from src.walters import nfl_predict as npd
    real = npd._current_ratings
    monkeypatch.setattr(npd, "_current_ratings", lambda progress=None, cfg=None: (
        (_ for _ in ()).throw(RuntimeError("boom")) if cfg is not None else real(progress)))
    _predict()
    _finish(world)
    doc = _results(world)
    rec = doc["record"][reh.RECORD_KEY]
    assert rec["unpriced_arm_rows"] == 3 and rec["total"]["games"] == 0 and rec["by_week"] == {}
    assert all(r[reh.RESULT_KEY]["home_win_prob"] is None and r[reh.RESULT_KEY]["p_home"] is None
               and "the second walk failed" in r[reh.RESULT_KEY]["reason"]
               for r in doc["results"])


def test_the_arm_is_stored_and_graded_at_full_precision_and_presented_at_four_places():
    """Codex on #825: the stored copy is the one graded, so a probability that is not exactly four-decimal is stored
    as the walk gave it, and the results row's log-loss and Brier, and the record's, are the gate's arithmetic on
    THAT float, rounded only on output; the slate row and the results row's home_win_prob present it at four."""
    g = reh.state(entry())
    q = 0.612345678
    pred = SimpleNamespace(factor_breakdown=json.loads(json.dumps({reh.FB_KEY: reh.arm_block(g, q)})))
    assert pred.factor_breakdown[reh.FB_KEY]["p_home"] == q and pred.factor_breakdown[reh.FB_KEY]["p_away"] == 1 - q
    kick = datetime(2026, 11, 15, 18, 0)
    assert reh.export_fields(g, pred, kick)["rehearsal_probabilities"] == {"home_win": 0.6123, "away_win": 0.3877}
    a = reh.result_arm(pred, 10, 27, None)                                  # an away win: y = 0
    assert a["p_home"] == q and (a["home_win_prob"], a["away_win_prob"]) == (0.6123, 0.3877)
    assert a["log_loss"] == round(reh.game_log_loss(q, 0), 4) == 0.9476 != round(reh.game_log_loss(0.6123, 0), 4)
    assert a["brier_score"] == round(q ** 2, 4) == 0.375 != round(0.6123 ** 2, 4)
    row = {"week": 10, "predicted": {"model_version": "nfl_elo_v1", "home_win_prob": 0.6123},
           "actual": {"home_score": 10, "away_score": 27, "result": "A"}, "graded": {"push": False},
           reh.RESULT_KEY: a}
    rec = reh.record_block([row])
    for blk in (rec["total"], rec["by_week"]["10"]):
        assert blk["v2"]["log_loss"] == 0.9476 and blk["v2"]["brier_score"] == 0.375      # from q, unrounded
        assert blk["v1"]["log_loss"] == 0.9475 and blk["v1"]["brier_score"] == 0.3749     # v1's stored four places


# ================================================================================== (5) THE PARITY (247 (6)) --

def test_the_arms_2025_probabilities_equal_the_gates_scored_ones_game_for_game(tmp_path, monkeypatch):
    """247 item 2(6): v1's live walk with the declared term for the whole walk is the gate's walk continued: on the
    synthetic stream its 2025 pre-game probabilities EQUAL nfl_v2_gate's scored ones (nfl_backtest.walk_protocol on
    nfl_backtest.load_stream's rows with nfl_v2_gate.candidate's config), game for game, in the gate's order. Walked
    both ways: the gate's via walk_protocol's own price hook (identity for home_advantage), the live one by recording
    nfl_predict._current_ratings' pre-update expectation."""
    from src.walters import nfl_backtest as nb
    from src.walters import nfl_predict as npd
    from src.walters import nfl_v2_gate as g2
    from tests import nfl_v2_world as w
    db = w.fresh(tmp_path / "p.db", monkeypatch)
    w.build(db)
    g = reh.state(entry())
    cfg, price = g2.candidate(*g2.declared_term(entry()))
    assert price is None and cfg == g.cfg and cfg.home_advantage == 33.0
    gate_ps: list = []
    warmup, scored = nb.split(nb.load_stream("parity"))
    wp = nb.walk_protocol(warmup, scored, cfg, lambda p: gate_ps.append(p) or p)
    live: list = []
    real = npd._update

    def rec(c, st, h, a, season, hs, as_):
        live.append((season, reh.price(g, npd._expected_home(c, st, h, a)), hs, as_))
        return real(c, st, h, a, season, hs, as_)
    monkeypatch.setattr(npd, "_update", rec)
    npd._current_ratings(cfg=g.cfg, floor=reh.WALK_FLOOR)                 # the arm's walk, as predict-nfl runs it
    live25 = [p for s, p, *_ in live if s == "2025"]
    assert len(gate_ps) == wp["n_scored"] == len(scored) > 200
    assert live25 == gate_ps                                               # exact floats, game for game
    # ... and as STORED (Codex on #825): the block predict-nfl stores, through the JSON column, keeps the gate's float
    kept = [json.loads(json.dumps(reh.arm_block(g, p)))["p_home"] for p in live25]   # live25 is already priced
    assert kept == gate_ps and any(p != round(p, 4) for p in kept)
    assert [s for s, *_ in live][-1] == "2026"                            # the live walk continues into 2026
    # the rehearsal's log-loss is the gate's arithmetic, to the bit
    ys = [reh.gate_y(hs, as_) for s, _, hs, as_ in live if s == "2025"]
    assert reh.mean_as_the_gate(reh.game_log_loss(p, y) for p, y in zip(live25, ys)) == wp["ll_model"]
    assert reh.gate_y(20, 20) == 0 and reh.EPS == 1e-12


def test_the_tie_rule_of_the_log_loss_is_walk_protocols_line():
    """251 item 3(4), by TEXT: the test reads the frozen gate's source and asserts the expressions (the outcome, the
    per-game log-loss, the floor, and the band index parity reproduces); no refactor of the gate's code."""
    src = inspect.getsource(__import__("src.walters.nfl_backtest", fromlist=["walk_protocol"]).walk_protocol)
    assert "y = 1 if g.home_score > g.away_score else 0  # ties count as home loss for scoring" in src
    assert "ll_model += -(y * math.log(max(p, eps)) + (1 - y) * math.log(max(1 - p, eps)))" in src
    assert "eps = 1e-12" in src
    assert "band = int(min(max(p, 0.0), 0.9999) * 10)" in src                   # parity's band index (251 (1))
    assert "stated = sum(p for p, _ in obs) / len(obs)" in src and "realized = sum(y for _, y in obs) / len(obs)" in src
    body = inspect.getsource(reh.game_log_loss)
    assert "-(y * math.log(max(p_home, EPS)) + (1 - y) * math.log(max(1 - p_home, EPS)))" in body
    assert "return 1 if home_score > away_score else 0" in inspect.getsource(reh.gate_y)
    par = inspect.getsource(reh.parity)
    assert "int(min(max(p, 0.0), 0.9999) * 10)" in par and "sum(p for p, _ in o) / len(o)" in par


@pytest.mark.parametrize("hs,as_", [(20, 20), (0, 0), (27, 10), (10, 27)])
def test_the_tie_rule_by_value_is_the_gates_figure_on_a_tie_and_a_decided_game(hs, as_):
    """251 item 3(4), by VALUE: walk_protocol itself scores a one-game 2025 stream (a tie, a 0-0 tie, a home win, an
    away win) after a two-game warm-up; the rehearsal's game_log_loss on gate_y gives its ll_model to the bit, and on a
    tie y = 0 (a home loss: -ln(1 - p)) while the W-L-P calls it a push (RULES)."""
    from src.walters import nfl_backtest as nb
    warm = [nb.Game(1, datetime(2024, 9, 5), "2024", "Regular Season", 10, 11, 27, 10),
            nb.Game(2, datetime(2024, 9, 12), "2024", "Regular Season", 11, 10, 10, 27)]
    scored = [nb.Game(3, datetime(2025, 9, 4), "2025", "Regular Season", 10, 11, hs, as_)]
    ps: list = []
    w = nb.walk_protocol(warm, scored, nb.NFLEloConfig(), lambda p: ps.append(p) or p)
    (p,) = ps
    y = reh.gate_y(hs, as_)
    assert reh.game_log_loss(p, y) == w["ll_model"]                             # the gate's figure, to the bit
    assert y == (1 if hs > as_ else 0)
    if hs == as_:
        assert y == 0 and w["ll_model"] == -math.log(1 - p) and reh.brier(p, y) == p ** 2
        assert "a TIE COUNTS AS A HOME LOSS" in reh.RULES["log_loss"] and "a TIE IS A PUSH" in reh.RULES["wlp"]


# ============================================================================== (5b) THE WALK'S FLOOR (251 (3)) --

def test_the_floor_is_the_gates_warmup_season_and_reads_seasons_conservatively():
    from src.walters import nfl_backtest as nb
    assert reh.WALK_FLOOR is nb.WARMUP_SEASON and reh.WALK_FLOOR == "2024"
    src = (ROOT / "src" / "walters" / "nfl_rehearsal.py").read_text()
    assert "WALK_FLOOR = nb.WARMUP_SEASON" in src and not re.search(r"WALK_FLOOR\s*=\s*[\"']?2024", src)
    assert [reh.before_floor(s) for s in ("2023", "2024", "2025", "2026", 2023, "", None, "2023/24")] == [
        True, False, False, False, True, True, True, True]                     # a non-year is never walked silently
    games = [SimpleNamespace(season=s) for s in ("2022", "2023", "2024", "2025")]
    kept, n = reh.floor_split(games)
    assert [g.season for g in kept] == ["2024", "2025"] and n == 2
    assert reh.floor_line(1) == "walk floor 2024; 1 stored games before it, excluded"
    assert reh.floor_line(0) == "walk floor 2024; 0 stored games before it, excluded"
    assert reh.floor_line(None).startswith("walk floor 2024; ")


def test_a_stored_pre_2024_finished_game_never_enters_the_arms_walk_and_is_counted_v1_unchanged(world):
    """251 item 3(3): a FINISHED 2023 NFL game is stored. The arm's probabilities equal an independent walk from 2024
    (and differ from one that walks 2023), the predict run's arm line counts it "walk floor 2024; 1 stored games before
    it, excluded", and v1's own walk still walks it (v1 is not changed in this lane: its stored probabilities equal an
    independent walk over every stored game, 2023 included)."""
    from src.walters.nfl_backtest import NFLEloConfig
    lines0 = _predict()
    arm0 = {mid: fb[reh.FB_KEY]["p_home"] for mid, (*_, fb) in _stored(world).items()}
    v1_0 = {mid: h for mid, (h, *_) in _stored(world).items()}
    assert "; walk floor 2024; 0 stored games before it, excluded; " + LABEL in lines0[-1]
    world.w.add_game(world.db, "2023", datetime(2023, 12, 3, 18, 0), 4, 5, 45, 3)   # teams of the first upcoming game
    lines = _predict()
    st = _stored(world)
    v2 = replace(NFLEloConfig(), home_advantage=33.0)
    floored, walked = _hand_walk(world, v2, floor="2024"), _hand_walk(world, v2)
    v1_all, v1_floored = _hand_walk(world, NFLEloConfig()), _hand_walk(world, NFLEloConfig(), floor="2024")
    for mid in world.games:
        h, _, _, fb = st[mid]
        assert fb[reh.FB_KEY]["p_home"] == floored[mid] == arm0[mid]          # the 2023 game is not in the arm's walk
        assert h == round(v1_all[mid], 4)                                       # v1 walks every stored game, as before
    g1 = world.games[0]
    assert walked[g1] != floored[g1]                                            # teeth: the 2023 game moves a walk
    assert v1_0[g1] == round(v1_floored[g1], 4) != round(v1_all[g1], 4) == st[g1][0]   # v1 walked it (unchanged)
    assert lines[-1].endswith("closes_at excluded); walk floor 2024; 1 stored games before it, excluded; " + LABEL)
    assert lines[-1].startswith("rehearsal arm nfl-elo-v2 (nfl-elo-v2 PASS 2026-11-06T19:00:00Z, home_advantage "
                                "33.0): 3 of 3 covered rows priced")


def test_the_arms_pure_walk_is_the_live_walk_from_the_floor(tmp_path, monkeypatch):
    """`walk` (the pure walk parity re-runs) over nfl_backtest.load_stream's rows ends in the same state as
    nfl_predict._current_ratings(cfg=..., floor=WALK_FLOOR), the arm's DB walk, with a stored 2023 game counted and
    excluded by both; without the floor v1's walk keeps it."""
    from src.walters import nfl_backtest as nb
    from src.walters import nfl_predict as npd
    from tests import nfl_v2_world as w
    db = w.fresh(tmp_path / "f.db", monkeypatch)
    w.build(db)
    w.add_game(db, "2023", datetime(2023, 12, 3, 18, 0), 4, 5, 45, 3)
    g = reh.state(entry())
    rc: dict = {}
    live = npd._current_ratings(cfg=g.cfg, floor=reh.WALK_FLOOR, receipt=rc)
    pure, n = reh.walk(nb.load_stream("floor"), g.cfg, g.price)
    assert (pure.ratings, pure.last_season) == (live.ratings, live.last_season) and n == rc["before_floor"] == 1
    v1 = npd._current_ratings()                                                 # v1's walk: no floor, as before
    assert v1.ratings != npd._current_ratings(floor=reh.WALK_FLOOR).ratings     # the 2023 game is in v1's walk
    v1_pure, n23 = reh.walk(nb.load_stream("floor"), nb.NFLEloConfig(), floor="2023")
    assert (v1_pure.ratings, v1_pure.last_season) == (v1.ratings, v1.last_season) and n23 == 0


# ======================================================================= (5c) THE POST-FRIDAY PARITY (251 (1)) --

def _synthetic_record(tmp_path, monkeypatch, pre_floor=True):
    """The synthetic stream (plus a FINISHED 2023 game) in a tmp DB, run through the frozen gate's walk
    (walk_protocol on load_stream's split, nfl_v2_gate.candidate's config) and recorded by the real writers
    (nfl_v2_gate.result_record, registry.record_run: the sidecar and its sha256) into a tmp registry."""
    from src.walters import nfl_backtest as nb
    from src.walters import nfl_v2_gate as g2
    from tests import nfl_v2_world as w
    db = w.fresh(tmp_path / "r.db", monkeypatch)
    w.build(db)
    if pre_floor:
        w.add_game(db, "2023", datetime(2023, 12, 3, 18, 0), 4, 5, 45, 3)
    cfg, price = g2.candidate(*g2.declared_term(real_entry()))
    stream = nb.load_stream("parity")
    wp = nb.walk_protocol(*nb.split(stream), cfg, price)
    led, ids_dir = tmp_path / "experiments.json", tmp_path / "ids"
    # the real entry holds the one run and the FAIL since 2026-11-06 (addendum 265): the tmp copy is put back to
    # declared and unrun, so the real writers record the synthetic run as they recorded the real one (#393's precedent)
    led.write_text(json.dumps([{**real_entry(), "status": "declared", "run": None, "verdict": None}]))
    reg.record_run(reh.EID, list(wp["scored_ids"]), g2.result_record(wp, "synthetic word"), str(led), str(ids_dir))
    return SimpleNamespace(stream=stream, entry=reg.get(reh.EID, str(led)), ids_dir=str(ids_dir), cfg=cfg,
                           price=price, wp=wp)


def test_the_parity_reproduces_the_records_own_figures_on_the_synthetic_run(tmp_path, monkeypatch):
    """251 item 3(1), on the synthetic stream: the arm's live walk (`walk`, from the floor) over the sidecar's scored
    ids (sha256-checked) reproduces the record's log-loss (`ll_model`, stored at full precision) exactly and every
    band's n, stated and realized means to the record's six places; the 2023 game is excluded and counted."""
    r = _synthetic_record(tmp_path, monkeypatch)
    res = r.entry["run"]["result"]
    assert "ll_model" in res and "scored_ids" not in res and all(
        b["stated"] == round(b["stated"], 6) for b in res["bands"])               # result_record's shape, as written
    ids = reh.scored_ids(r.entry, r.ids_dir)
    assert len(ids) == r.entry["run"]["n_scored"] == r.wp["n_scored"] > 200
    out = reh.parity(r.stream, ids, res, r.cfg, r.price)
    assert out["ok"] and out["mismatches"] == [] and out["before_floor"] == 1 and out["n"] == len(ids)
    assert out["log_loss"] == res["ll_model"] == r.wp["ll_model"]               # the stored precision: every digit
    assert [(b["band"], b["n"]) for b in out["bands"]] == [(b["band"], b["n"]) for b in res["bands"]]
    assert len(res["bands"]) >= 3


def test_the_parity_has_teeth(tmp_path, monkeypatch):
    """A walk without the floor (the 2023 game walked), a record one unit off in its last stored place, a band off
    by 1e-6, a dropped scored id, and a sidecar that does not match its sha256: each is a named mismatch or refusal."""
    r = _synthetic_record(tmp_path, monkeypatch)
    res = r.entry["run"]["result"]
    ids = reh.scored_ids(r.entry, r.ids_dir)
    walked = reh.parity(r.stream, ids, res, r.cfg, r.price, floor="2023")       # the 2023 game inside the walk
    assert not walked["ok"] and any("ll_model" in m for m in walked["mismatches"]) and walked["before_floor"] == 0
    off = copy.deepcopy(res)
    off["ll_model"] = math.nextafter(res["ll_model"], 1.0)
    assert any("ll_model" in m for m in reh.parity(r.stream, ids, off, r.cfg, r.price)["mismatches"])
    off = copy.deepcopy(res)
    off["bands"][1]["stated"] = round(off["bands"][1]["stated"] + 1e-6, 6)
    assert any("stated" in m for m in reh.parity(r.stream, ids, off, r.cfg, r.price)["mismatches"])
    off = copy.deepcopy(res)
    off["bands"][1]["realized"] = round(off["bands"][1]["realized"] - 1e-6, 6)
    assert any("realized" in m for m in reh.parity(r.stream, ids, off, r.cfg, r.price)["mismatches"])
    short = reh.parity(r.stream, ids[:-1], res, r.cfg, r.price)
    assert not short["ok"] and any("ll_model" in m for m in short["mismatches"])
    side = Path(r.ids_dir) / Path(r.entry["run"]["ids_file"]).name
    side.write_text("\n".join(str(i) for i in ids[:-1]) + "\n")
    with pytest.raises(reh.ParityRefused, match="does not match the record's count and sha256"):
        reh.scored_ids(r.entry, r.ids_dir)
    side.unlink()
    with pytest.raises(reh.ParityRefused, match="does not exist"):
        reh.scored_ids(r.entry, r.ids_dir)
    assert reh.at_stored_precision(0.123457, 0.123457) and reh.at_stored_precision(0.12345678, 0.123457)
    assert not reh.at_stored_precision(0.1234562, 0.123457) and not reh.at_stored_precision(0.5, None)


def test_the_parity_skip_is_named_never_silent():
    """251 item 3(1): "skipped (named, with the reason) until the record exists; a skip is never silent". The two
    reasons, asserted by text."""
    e = real_entry()
    assert reh.parity_skip({**e, "run": None}, None) == reh.PARITY_SKIP_NO_RECORD
    assert reh.parity_skip({**e, "run": None}, "/tmp/copy.db") == reh.PARITY_SKIP_NO_RECORD
    assert reh.parity_skip(None, None) == reh.PARITY_SKIP_NO_RECORD
    assert reh.PARITY_SKIP_NO_RECORD == ("nfl-elo-v2's run record does not exist yet (Friday 11-06's one run; the "
                                         "verdict-record PR lands it) — addendum 251 item 3(1)")
    ran = {**e, "run": {"result": {"ll_model": 0.65}}}
    assert reh.parity_skip(ran, None) == reh.parity_skip(ran, "  ") == reh.PARITY_SKIP_NO_DB
    assert reh.PARITY_SKIP_NO_DB.startswith("nfl-elo-v2's run record exists but no database copy is given (CI has no "
                                            "database: set SP_REHEARSAL_PARITY_DB")
    assert reh.PARITY_SKIP_NO_DB.endswith("— addendum 251 item 3(1)") and reh.PARITY_DB_ENV == "SP_REHEARSAL_PARITY_DB"
    assert reh.parity_skip(ran, "/tmp/copy.db") is None
    # since 2026-11-06 (addendum 265 item 4) the real entry holds the run record: without a database copy its parity
    # test reaches the no-database reason (the sidecar and the shape checked first), with one it walks
    assert e.get("run") is not None
    assert reh.parity_skip(e, None) == reh.PARITY_SKIP_NO_DB and reh.parity_skip(e, "/tmp/copy.db") is None
    assert "the sidecar's count and sha256 and the record's shape were checked, the walk alone is skipped" in (
        reh.PARITY_SKIP_NO_DB)
    assert issubclass(reh.ParitySkipped, UserWarning)


def test_the_real_record_test_warns_its_skip_where_a_plain_q_run_shows_it():
    """251 item 3(1), "a skip is never silent", on CI's own path (`pytest -q tests`, no -rs: the skip reason is not in
    its report, the warnings summary is). The real-record test warns each named reason beside its pytest.skip, and on
    the no-database path it runs the sidecar and shape checks first (read by text from the test's own source)."""
    src = inspect.getsource(test_the_real_run_record_parity)
    assert src.count("warnings.warn(why, reh.ParitySkipped)") == 2
    assert src.count("pytest.skip(why)") == 2
    for k in (src.index("warnings.warn(why, reh.ParitySkipped)"), src.rindex("warnings.warn(why, reh.ParitySkipped)")):
        assert src[k:].lstrip().split("\n")[1].strip() == "pytest.skip(why)"
    nodb = src.rindex("warnings.warn(why, reh.ParitySkipped)")
    assert src.index("reh.scored_ids(e, reg.IDS_DIR)") < nodb and src.index("reh.record_shape(e) == []") < nodb
    assert src.index("why == reh.PARITY_SKIP_NO_RECORD") < src.index("reh.scored_ids(e, reg.IDS_DIR)")


def test_once_the_record_exists_ci_still_checks_the_sidecar_and_the_shape(tmp_path, monkeypatch):
    """251 item 3(1), by value: with a run record and no database copy (CI), the real-record test is not a bare skip.
    It reads the sidecar first: a sidecar off its sha256 FAILS (ParityRefused) instead of skipping; a sound one and a
    sound shape reach the no-database skip, named and warned (ParitySkipped). The synthetic record stands in for the
    real one (real_entry and registry.IDS_DIR pointed at it)."""
    r = _synthetic_record(tmp_path, monkeypatch)
    monkeypatch.delenv(reh.PARITY_DB_ENV, raising=False)
    monkeypatch.setattr(sys.modules[__name__], "real_entry", lambda: copy.deepcopy(r.entry))
    monkeypatch.setattr(reg, "IDS_DIR", r.ids_dir)
    with pytest.warns(reh.ParitySkipped, match="no database copy is given"):
        with pytest.raises(pytest.skip.Exception, match="the walk alone is skipped"):
            test_the_real_run_record_parity(monkeypatch)
    side = Path(r.ids_dir) / Path(r.entry["run"]["ids_file"]).name
    ids = side.read_text().split()
    side.write_text("\n".join(ids[:-1]) + "\n")
    with pytest.raises(reh.ParityRefused, match="does not match the record's count and sha256"):
        test_the_real_run_record_parity(monkeypatch)
    side.write_text("\n".join(ids) + "\n")
    bad = copy.deepcopy(r.entry)
    bad["run"]["result"]["bands"][0]["stated"] = 0.1234567
    monkeypatch.setattr(sys.modules[__name__], "real_entry", lambda: copy.deepcopy(bad))
    with pytest.raises(AssertionError):
        test_the_real_run_record_parity(monkeypatch)


def test_the_record_shape_needs_no_database(tmp_path, monkeypatch):
    """What runs without a database once the record exists (251 item 3(1)): result_record's shape, on the synthetic
    record the real writers make, and a named problem for each way off it."""
    r = _synthetic_record(tmp_path, monkeypatch)
    assert reh.record_shape(r.entry) == []
    for path, val, want in ((("ll_model",), None, "ll_model"), (("ll_model",), float("nan"), "ll_model"),
                            (("bands",), [], "bands"), (("bands", 0, "n"), 3.0, "n is not an int"),
                            (("bands", 0, "stated"), 0.1234567, "stated is not a number at 6 places"),
                            (("bands", 1, "realized"), None, "realized is not a number at 6 places")):
        e = copy.deepcopy(r.entry)
        tgt = e["run"]["result"]
        for k in path[:-1]:
            tgt = tgt[k]
        tgt[path[-1]] = val
        assert any(want in m for m in reh.record_shape(e)), (path, val)
    assert reh.record_shape({"run": None}) == ["the run record holds no result"]


def test_the_real_run_record_parity(monkeypatch):
    """251 item 3(1), on the REAL record: nfl-elo-v2's run.result in docs/registry/experiments.json, its sidecar under
    registry.IDS_DIR (sha256-checked), and the arm's live walk over the stream of a fresh .backup copy of the database
    the run read (SP_REHEARSAL_PARITY_DB; nfl_v2_gate.check_db's fence, opened read-only). Skipped with a named reason
    until the record exists (the verdict-record PR lands it). Once it exists, what needs no database runs everywhere,
    CI included: the sidecar's count and sha256 against the record (scored_ids) and the record's shape (record_shape);
    only the walk is skipped without a database copy. Every skip's reason is also warned (ParitySkipped), so the
    warnings summary of a plain `pytest -q` run names it (CI passes no -rs)."""
    import os
    import warnings

    from src.walters import nfl_backtest as nb
    from src.walters import nfl_v2_gate as g2
    e = real_entry()
    db = os.environ.get(reh.PARITY_DB_ENV)
    why = reh.parity_skip(e, db)
    if why == reh.PARITY_SKIP_NO_RECORD:
        warnings.warn(why, reh.ParitySkipped)
        pytest.skip(why)
    ids = reh.scored_ids(e, reg.IDS_DIR)                                      # no database needed: count and sha256
    assert reh.record_shape(e) == [] and len(ids) == e["run"]["n_scored"]       # no database needed: the shape
    if why is not None:
        warnings.warn(why, reh.ParitySkipped)
        pytest.skip(why)
    cfg, price = g2.candidate(*g2.declared_term(e))
    path = g2.check_db(db)
    with g2.db_session(path) as s:
        stream = nb.load_stream("rehearsal-parity", session=s)
    out = reh.parity(stream, ids, e["run"]["result"], cfg, price)
    assert out["ok"], out["mismatches"]
    print(f"parity: {out['n']} scored ids, log-loss {out['log_loss']!r}, {len(out['bands'])} bands; "
          f"{reh.floor_line(out['before_floor'])}")


# ===================================================================== (5d) THE PRECISION LINE (251 (3), P1) --

def test_the_weekly_comparison_names_the_precision_on_its_own_line():
    """251 item 3 (the Codex P1): the weekly comparison names the precision on its own line, verbatim, in the record
    block's `rules` (total and every week carry the rules once, beside the figures)."""
    want = ("v2 at full precision as stored; v1 at four places as stored; the difference is bounded at about 1e-4 of "
            "log-loss")
    assert reh.PRECISION_LINE == want and reh.RULES["precision"] == want
    assert f'("{want}")' in reh.RULING_251_TEXT[-1]
    g = reh.state(entry())
    pred = SimpleNamespace(factor_breakdown={reh.FB_KEY: reh.arm_block(g, 0.612345678)})
    a = reh.result_arm(pred, 10, 27, None)
    row = {"week": 10, "predicted": {"model_version": "nfl_elo_v1", "home_win_prob": 0.6123},
           "actual": {"home_score": 10, "away_score": 27, "result": "A"}, "graded": {"push": False}, reh.RESULT_KEY: a}
    rec = reh.record_block([row])
    assert rec["rules"]["precision"] == want and "\n" not in want
    assert sum(1 for v in rec["rules"].values() if v == want) == 1


# ========================================================================================== (6) THE DESK PIN --

def _annotated(doc, now):
    from src.walters import desk_policy as dp
    return dp.annotate(json.loads(json.dumps(doc)), now=now)


def _desk_reads(doc, now):
    """Everything the Desk and its readers produce from a doc, byte for byte: desk_meta, each row's desk block, the
    closing page's Desk rows (closing.desk_rows: would_be_for included), exec_cohorts.would_be_play and the phone
    page's text (closing.page_text)."""
    import closing as cl
    from src.walters import exec_cohorts as ec
    a = _annotated(doc, now)
    ids = {r.get("match_id") for r in a["predictions"]}
    rows = cl.desk_rows(a, ids, now - timedelta(hours=6), fam="NFL")
    page = cl.page_text("NFL", now + timedelta(minutes=35), now, rows, {})
    return json.dumps({"meta": a["desk_meta"], "desk": [r["desk"] for r in a["predictions"]], "rows": rows,
                       "would_be": [ec.would_be_play(r["desk"]) for r in a["predictions"]], "page": page},
                      sort_keys=True)


def _variants(doc):
    """(bare: no arm keys; loud: every row's arm flipped to the other side at the extremes)."""
    bare, loud = json.loads(json.dumps(doc)), json.loads(json.dumps(doc))
    for r in bare["predictions"]:
        for k in reh.ROW_KEYS:
            r.pop(k, None)
    for r in loud["predictions"]:
        r.update({"rehearsal_version": reh.EID, "rehearsal_probabilities": {"home_win": 0.01, "away_win": 0.99},
                  "rehearsal_reason": None, "rehearsal_label": LABEL})
    return bare, loud


def test_the_desk_reads_nothing_of_the_arm_on_the_export(world):
    world.set()
    _predict()
    doc = _export(world, "a")
    assert all(r["rehearsal_probabilities"] for r in doc["predictions"])
    bare, loud = _variants(doc)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    a, b, c = (_desk_reads(x, now) for x in (doc, bare, loud))
    assert a == b == c


def test_the_desk_reads_nothing_of_the_arm_on_the_market_only_battery():
    """The battery of tests/test_nfl_market_only_214.py (one row per path the Desk's chain can take, would-be PLAYs
    among them), each row given an arm that disagrees with v1, then flipped."""
    from tests.test_nfl_market_only_214 import NOW, nfl_rows
    rows = nfl_rows()
    for k, r in enumerate(rows):
        r["match_id"] = 900 + k
        h = round(1 - r["prediction"]["probabilities"]["home_win"], 4)
        r.update({"rehearsal_version": reh.EID, "rehearsal_probabilities": {"home_win": h, "away_win": round(1 - h, 4)},
                  "rehearsal_term": {"form": "home_advantage", "value": 33.0}, "rehearsal_verdict_stamp": "x",
                  "rehearsal_label": LABEL, "rehearsal_reason": None})
    doc = {"sport": "nfl", "predictions": rows}
    bare, loud = _variants(doc)
    a, b, c = (_desk_reads(x, NOW) for x in (doc, bare, loud))
    assert a == b == c
    assert '"would_call": "PLAY"' in a and '"would_be": {' in a              # the would-be is there, and unmoved


def test_no_desk_code_names_the_arm():
    import closing as cl
    pat = re.compile(re.escape(reh.PREFIX) + "|" + re.escape(reh.FB_KEY) + r"|nfl_rehearsal|nfl_elo_v2|rehearsal")
    for f in ("src/walters/desk_policy.py", "src/walters/exec_cohorts.py", "src/walters/desk_unit.py"):
        assert not pat.search((ROOT / f).read_text()), f
    for fn in (cl.desk_rows, cl.would_be_for, cl.page_text, cl.slate_page_text, cl.slate_calls, cl.call_text):
        assert not pat.search(inspect.getsource(fn)), fn.__name__
    src = (ROOT / "src" / "walters" / "desk_policy.py").read_text()
    body = re.search(r"^def normalize\(.*?(?=^def )", src, re.S | re.M).group(0)
    assert "rehearsal" not in body and "candidate" not in body


# ============================================================ (6b) the summary block and the receipt, not the page --

def test_the_closing_copy_of_the_keys_is_the_modules():
    import closing as cl
    assert cl.REHEARSAL_KEYS == reh.ROW_KEYS and cl.REHEARSAL_PREFIX == reh.PREFIX


def _arm_row(row: dict) -> dict:
    row = dict(row)
    row.update({"rehearsal_version": reh.EID, "rehearsal_probabilities": {"home_win": 0.6012, "away_win": 0.3988},
                "rehearsal_term": {"form": "home_advantage", "value": 33.0},
                "rehearsal_verdict_stamp": "nfl-elo-v2 PASS 2026-11-06T19:00:00Z", "rehearsal_label": LABEL,
                "rehearsal_reason": None})
    return row


def test_the_summary_block_carries_one_arm_line_and_the_phone_page_none():
    import closing as cl
    from tests.test_nfl_market_only_214 import NOW, nfl_rows
    rows = [dict(r, match_id=900 + k) for k, r in enumerate(nfl_rows())]
    doc = _annotated({"sport": "nfl", "predictions": [_arm_row(rows[0])] + rows[1:]}, NOW)
    ids = {r["match_id"] for r in doc["predictions"]}
    d_rows = cl.desk_rows(doc, ids, NOW - timedelta(hours=6), fam="NFL")
    arms = cl.rehearsal_arms(doc, [x["match_id"] for x in d_rows])
    assert list(arms) == [900] and arms[900] == {
        "version": "nfl-elo-v2", "probabilities": {"home_win": 0.6012, "away_win": 0.3988},
        "term": {"form": "home_advantage", "value": 33.0}, "verdict_stamp": "nfl-elo-v2 PASS 2026-11-06T19:00:00Z",
        "label": LABEL, "reason": None}
    x = next(r for r in d_rows if r["match_id"] == 900)
    blk = cl.summary_block(x, arms[900]).splitlines()
    want = (f"   rehearsal arm nfl-elo-v2 (home_advantage 33.0) · {x['home']} 0.6012 / {x['away']} 0.3988 · "
            f"nfl-elo-v2 PASS 2026-11-06T19:00:00Z · {LABEL}")
    assert [ln for ln in blk if "rehearsal" in ln] == [want]
    assert cl.summary_block(x).splitlines() == [ln for ln in blk if ln != want]   # the block, less the line
    _, body, high = cl.page_text("NFL", NOW + timedelta(minutes=35), NOW, d_rows, {})
    assert "rehearsal" not in body and "nfl-elo-v2" not in body and "0.6012" not in body
    nomiss = dict(arms[900], probabilities=None, reason="the second walk failed for this game (x)")
    assert "no probabilities: the second walk failed for this game (x)" in cl.summary_block(x, nomiss)


from tests.test_closing_runs import box  # noqa: E402,F401  (the closing-run frame's fixture)


def test_the_closing_runs_receipt_and_summary_carry_the_arm_and_the_page_does_not(box, capsys):
    from tests.test_closing_runs import NOW as C_NOW, at, mc, runs
    doc = box.docs["NFL"]
    doc["predictions"] = [_arm_row(r) if r["match_id"] == 301 else r for r in doc["predictions"]]
    assert mc.run("NFL", start=at(35), now=C_NOW) == 0
    out = capsys.readouterr().out
    assert [ln for ln in out.splitlines() if LABEL in ln] == [
        "   rehearsal arm nfl-elo-v2 (home_advantage 33.0) · Buffalo 0.6012 / Buffalo Visitors 0.3988 · "
        f"nfl-elo-v2 PASS 2026-11-06T19:00:00Z · {LABEL}"]
    assert not any("rehearsal" in x for x in box.pages[-1]["body"].splitlines())        # the phone page: none
    got = {x["match_id"]: x for x in runs("NFL")[-1]["desk_rows"]}
    assert [m for m, x in got.items() if "rehearsal_arm" in x] == [301]
    assert got[301]["rehearsal_arm"]["probabilities"] == {"home_win": 0.6012, "away_win": 0.3988}
    assert got[301]["rehearsal_arm"]["label"] == LABEL and got[301]["call"] == "PASS"


# ================================================================================ (7) the compare's own line --

def _cmp(tmp_path, capsys, laptop, host_, name):
    import compare_exports as ce
    la, ho = tmp_path / "laptop", tmp_path / "host"
    for d, body in ((la, laptop), (ho, host_)):
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(json.dumps(body))
    rc = ce.main([str(la), str(ho), "--since", "0", "--paired-kinds", "*"])   # the masks' test: the pre-335 rule
    return rc, capsys.readouterr().out


def _slate_row(i, p=0.61):
    return {"match_id": i, "utc_date": f"2026-11-15T18:{i:02d}:00", "home_team": f"H{i}", "away_team": f"A{i}",
            "week": 10, "prediction": {"model_version": "nfl_elo_v1", "home_win_prob": p}}


SECRET = 0.987654                                                           # an arm probability that must never print


def test_the_compare_masks_the_slate_keys_under_its_own_line_and_a_real_v1_divergence_still_prints(tmp_path, capsys):
    lap = {"sport": "nfl", "git_sha": "abc", "rehearsal": False, "predictions": [_slate_row(i) for i in range(10)]}
    host_ = json.loads(json.dumps(lap))
    for r in host_["predictions"]:
        r.update({k: {"home_win": SECRET} if k == "rehearsal_probabilities" else f"FIXTURE-{k}"
                  for k in reh.ROW_KEYS})
    rc, out = _cmp(tmp_path / "a", capsys, lap, host_, "nfl_predictions_2026-11-15.json")
    lines = out.splitlines()
    assert LINE + "60" in lines and SHADOW + "0" in lines and rc == 0 and lines[-1] == "VERDICT: CLEAN"
    i = lines.index(LINE + "60")
    assert lines[i - 1] == SHADOW + "0" and lines[i + 1].startswith("graded-export keys (machine-local): ")
    assert str(SECRET) not in out and "FIXTURE-" not in out
    host_["predictions"][9]["prediction"]["home_win_prob"] = 0.62             # the last row: a real v1 divergence
    rc, out = _cmp(tmp_path / "b", capsys, lap, host_, "nfl_predictions_2026-11-15.json")
    assert rc == 1 and "prediction.home_win_prob: '0.61' vs '0.62'" in out and str(SECRET) not in out


def test_the_compare_masks_the_results_arm_and_record_and_never_the_fossil_or_candidate_keys(tmp_path, capsys):
    import compare_exports as ce
    row = {"match_id": 1, "utc_date": "2026-11-15T18:00:00", "home_team": "H", "away_team": "A", "week": 10,
           "predicted": {"home_win_prob": 0.6}}
    lap = {"sport": "nfl", "record": {"games": 1}, "results": [row]}
    host_ = json.loads(json.dumps(lap))
    host_["results"][0][reh.RESULT_KEY] = {"version": reh.EID, "home_win_prob": SECRET}
    host_["record"][reh.RECORD_KEY] = {"version": reh.EID, "total": {"v2": {"log_loss": SECRET}}}
    rc, out = _cmp(tmp_path / "a", capsys, lap, host_, "nfl_NFL_results_2026-11-24.json")
    assert LINE + "2" in out.splitlines() and rc == 0 and str(SECRET) not in out
    assert not ce.rehearsal_arm_key("rehearsal") and ce.rehearsal_arm_key("rehearsal_arm")
    assert not ce.rehearsal_arm_key("candidate_version") and not ce.shadow_arm("rehearsal_version")
    a = {"sport": "nfl", "rehearsal": False, "predictions": [_slate_row(1)]}
    rc, out = _cmp(tmp_path / "b", capsys, a, dict(a, rehearsal=True), "nfl_predictions_2026-11-16.json")
    assert rc == 1 and "$.rehearsal: 'False' vs 'True'" in out              # the fossil is compared as before
    b = json.loads(json.dumps(a))
    b["predictions"][0]["candidate_version"] = "pl-availability-v1"
    rc, out = _cmp(tmp_path / "c", capsys, a, b, "nfl_predictions_2026-11-17.json")
    assert SHADOW + "1" in out.splitlines() and LINE + "0" in out.splitlines()   # each class on its own line
    assert ce.redacted({"x": {"rehearsal_probabilities": SECRET}}) == {"x": {"rehearsal_probabilities": "<masked>"}}


# ====================================================================================== (8) the rulings verbatim --

def _spec() -> str:
    from tests.ledger_text import flat
    return flat(" ".join(ln[2:] if ln.startswith("> ") else ln
                         for ln in (ROOT / "docs" / "specs" / "nfl-rehearsal-arm.md").read_text().splitlines()))


def test_the_rulings_are_quoted_verbatim_in_the_spec_and_the_entry():
    from tests.ledger_text import entry_text, flat
    txt = flat(entry_text("2026-11-04-230-1a-nfl-rehearsal-arm", "**2026-11-04 — BUILT (ARCHITECT 2026-11-03, "
                                                                 "addendum 230 item 1(a), as ruled by"))
    spec = _spec()
    for t in (reh.RULING_230_TEXT, *reh.RULING_247_TEXT, *reh.RULING_251_TEXT):
        assert flat(t) in txt and flat(t) in spec, t[:60]
    assert reh.RULING_251 == "ARCHITECT 2026-11-04 11:50 ET, addendum 251 item 3"
    assert '("walk floor 2024; N stored games before it, excluded")' in reh.RULING_251_TEXT[3]
    assert reh.LABEL == LABEL and f'"{LABEL}"' in reh.RULING_247_TEXT[-1]
    assert '"rehearsal-arm keys (host-only, nfl-elo-v2)"' in reh.RULING_247_TEXT[2]


# ===================================================================================== (9) the synthetic page --

def synthetic_page() -> dict:
    """One NFL slate row as the host's page would carry it in the window: v1's prediction (uncertified, a shadow), the
    Desk's market-only PASS with v1's record-only would-be (market_only_hold), and the rehearsal arm (v2: the entry
    id, the term, the verdict stamp, the label). Built from the market-only battery's would-be PLAY row by the real
    writers (export_fields on a stored arm_block, desk_policy.annotate); no database."""
    from tests.test_nfl_market_only_214 import NOW, pred
    g = reh.state(entry())
    p = SimpleNamespace(factor_breakdown={reh.FB_KEY: reh.arm_block(g, 0.6012)})
    kick = datetime(2026, 11, 15, 18, 0)
    r = pred("Buffalo", 0.64, 0.55, home_team="Buffalo", away_team="Miami", week=10,
             utc_date=kick.strftime("%Y-%m-%dT%H:%M:%S"), match_id=901)
    r["prediction"].update({"model_version": "nfl_elo_v1", "home_win_prob": 0.64, "away_win_prob": 0.36,
                            "top_pick": "home_win"})
    r.update(reh.export_fields(g, p, kick))
    now = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)
    assert NOW < now
    doc = _annotated({"sport": "nfl", "model_version": "nfl_elo_v1", "rehearsal": False, "predictions": [r]}, now)
    return doc["predictions"][0]


def printable(row: dict) -> dict:
    """The row as the PR body prints it: v1's prediction, the market, the Desk's call with its record-only would-be
    (no size field), and the rehearsal_* keys."""
    d = row["desk"]
    hold = {k: v for k, v in d["market_only_hold"].items() if "units" not in k}
    return {**{k: row[k] for k in ("week", "utc_date", "home_team", "away_team", "prediction", "market")},
            "desk": {"call": d["call"], "pass_kind": d["pass_kind"], "reason": d["reason"],
                     "market_only_hold": hold},
            **{k: row[k] for k in reh.ROW_KEYS}}


def test_the_synthetic_page_carries_both_arms_and_the_desk_passes(capsys):
    row = synthetic_page()
    assert row["desk"]["call"] == "PASS" and row["desk"]["units"] == 0
    assert row["desk"]["market_only_hold"]["would_call"] == "PLAY"
    assert row["prediction"]["home_win_prob"] == 0.64
    assert row["rehearsal_probabilities"] == {"home_win": 0.6012, "away_win": 0.3988}
    assert row["rehearsal_verdict_stamp"] == "nfl-elo-v2 PASS 2026-11-06T19:00:00Z"
    assert row["rehearsal_label"] == LABEL and row["rehearsal_term"] == {"form": "home_advantage", "value": 33.0}
    print(json.dumps(printable(row), indent=2, ensure_ascii=False))
