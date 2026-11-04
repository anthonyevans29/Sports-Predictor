"""THE SOCCER WALK'S DEFAULT PATH, PINNED (ARCHITECT 2026-11-04 11:50 ET, addendum 251 item 2(a)): "the walk gains an
optional `context` parameter whose default is today's CompetitionScoringContext() (the default path byte-identical,
pinned by the existing soccer-backtest golden on the fixture store — a changed default would re-measure every soccer
record and is gate-class; this is not that)".

No golden of run_soccer_backtest's output existed on a fixture store (tests/test_soccer_candidates.py compares the walk's
switches against each other, never against a pinned output), so this file adds one. Its digests were computed on the
walk BEFORE the `context` parameter existed and are unchanged after it (the PR's receipts paste both consoles).

THE FIXTURE STORE: a fresh tmp SQLite file (soccer_parity.fresh_store; never data/), eight teams, two seasons, each a
double round robin (56 FINISHED matches a season, 112 in all), integer scores drawn from random.Random(2512) around a
fixed quality ladder, so the ids, the order and every score are the same on every run.

WHAT IS PINNED, per call (CALLS): the row count, the match ids in order, and a sha256 over every key of every row
with each float written to 9 decimals. Nine decimals, not the float's last bit: Python 3.12's sum() of floats is
compensated where 3.11's is not, and numpy's pairwise sums can move with its version, so the last bits of the
deflated means are the interpreter's (tests/test_v22_normalisation_receipt.py says the same of its own figures); nine
decimals sits about seven orders above that noise and far below any change a context or a constant makes (the
non-vacuity test below moves the digest at the fourth decimal). The exact bits are pinned IN PROCESS instead: the
default call, `context=None` and `context=CompetitionScoringContext()` give equal rows (Python float equality, every
bit), and the receipt prints the exact float.hex digest of each call before and after the change.
"""
from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta

import pytest

import soccer_parity as P

CODE = "GLDW"
SEASONS = ("2091/92", "2092/93")

#: The calls pinned: the default call, soccer-backtest's plain report as the CLI calls it (min_prior 40, the
#: production row's rho and coefficient), plus detail=True so the additive xG/score keys are pinned too, and the
#: season-less walk with the decay and the batched kickoff switches on.
CALLS = {
    "default": dict(season=SEASONS[0]),
    "plain_report": dict(season=SEASONS[0], min_prior=40, dixon_coles_rho=-0.10, elo_goal_coeff=0.0008, detail=True),
    "all_seasons_decay_batched": dict(season=None, min_prior=40, dixon_coles_rho=-0.10, elo_goal_coeff=0.0008,
                                      decay_half_life_days=365.0, batch_same_kickoff=True, detail=True),
}

#: Computed on the walk before the `context` parameter existed (2026-11-04; Python 3.12.3 / numpy 2.5.4 and Python
#: 3.11.17 / numpy 2.4.6 agree at nine decimals).
GOLDEN = {
    "default": (16, "f897367cd40ce38929c16f699746cca7052f26e82b5e1512917b7297c064e798",
                "e20d3a61f00d1f481847ca85efe9f8ca0040408637c0d041eb9a051e5c26c967"),
    "plain_report": (16, "f897367cd40ce38929c16f699746cca7052f26e82b5e1512917b7297c064e798",
                     "8cdc9f571a1aee1484a2f55262d931ee6d3e04035c5a974ad75d8b81746d9ff0"),
    "all_seasons_decay_batched": (72, "58b35998362c6ef32b6a150e0e54a1dd56736d272c13168ef0447d58829141ec",
                                  "0d1bf9f7ccf13b5273e893a5b9c841364cb3425d9e33f18ee788a8b8968e8ff9"),
}


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:.9f}"
    return repr(v)


def digest(rows, exact: bool = False) -> str:
    """sha256 over every key of every row in order; floats to 9 decimals (or float.hex, exact=True)."""
    h = hashlib.sha256()
    for r in rows:
        for k in sorted(r):
            v = r[k]
            h.update(f"{k}={v.hex() if exact and isinstance(v, float) else _fmt(v)};".encode())
        h.update(b"|")
    return h.hexdigest()


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus, Sport, Team

    mp = pytest.MonkeyPatch()
    P.fresh_store(tmp_path_factory.mktemp("soccer-walk-golden") / "store.db", mp)
    rnd = random.Random(2512)
    with session_scope() as s:
        comp = Competition(sport=Sport.SOCCER, code=CODE, name="walk golden league", area="X", type="LEAGUE")
        teams = [Team(sport=Sport.SOCCER, name=f"Golden {i}") for i in range(8)]
        s.add(comp)
        s.add_all(teams)
        s.flush()
        ids = [t.id for t in teams]
        for si, season in enumerate(SEASONS):
            t0 = datetime(2091 + si, 8, 10, 15)
            for leg in range(2):
                for rd in range(7):
                    rot = ids[:1] + ids[1:][rd:] + ids[1:][:rd]
                    day = t0 + timedelta(days=7 * (leg * 7 + rd))
                    for i in range(4):
                        h, a = (rot[i], rot[7 - i]) if leg == 0 else (rot[7 - i], rot[i])
                        qh, qa = 1 + 0.4 * (ids.index(h) / 7 - 0.5), 1 + 0.4 * (ids.index(a) / 7 - 0.5)
                        hs = sum(1 for _ in range(10) if rnd.random() < 1.5 * qh / qa / 10)
                        as_ = sum(1 for _ in range(10) if rnd.random() < 1.15 * qa / qh / 10)
                        # two of the four games of a round share a kickoff, so the batched switch has groups to batch
                        s.add(Match(sport=Sport.SOCCER, competition_id=comp.id, season=season,
                                    utc_date=day + timedelta(hours=2 * (i // 2)), status=MatchStatus.FINISHED,
                                    home_team_id=h, away_team_id=a, home_score=hs, away_score=as_))
    yield CODE
    mp.undo()


def _run(code, **kw):
    from src.walters import soccer_backtest as sb
    kw = dict(kw)
    season = kw.pop("season")
    return sb.run_soccer_backtest(code, season, **kw)


@pytest.mark.parametrize("name", list(CALLS))
def test_the_walk_s_default_path_matches_its_golden(store, name):
    rows = _run(store, **CALLS[name])
    n, ids_digest, row_digest = GOLDEN[name]
    got_ids = hashlib.sha256(",".join(str(r["match_id"]) for r in rows).encode()).hexdigest()
    print(f"\nGOLDEN {name}: {len(rows)} rows; ids sha256 {got_ids}; rows sha256 (9 dp) {digest(rows)}; "
          f"rows sha256 (exact float.hex) {digest(rows, exact=True)}")
    assert len(rows) == n
    assert got_ids == ids_digest
    assert digest(rows) == row_digest


@pytest.mark.parametrize("name", list(CALLS))
def test_the_default_context_is_every_bit_the_walk_s_old_path(store, name):
    """In process, every bit: the call with no `context`, `context=None` and `context=CompetitionScoringContext()`
    give equal rows (Python float equality). The default the walk falls back to is the dataclass default, 1.4 / 1.15,
    never a stored context (addendum 251 item 2: option 2 REJECTED)."""
    from src.models.poisson import CompetitionScoringContext
    base = _run(store, **CALLS[name])
    assert _run(store, context=None, **CALLS[name]) == base
    assert _run(store, context=CompetitionScoringContext(), **CALLS[name]) == base
    assert digest(_run(store, context=None, **CALLS[name]), exact=True) == digest(base, exact=True)
    assert CompetitionScoringContext().as_dict() == {"avg_goals_per_team_per_match": 1.4,
                                                     "home_field_goal_boost": 1.15}


def test_an_injected_context_reaches_every_row_and_moves_the_digest(store):
    """Non-vacuity: a context other than the default changes the walk's output (so the golden would see a changed
    default), and the injected context is the one every row is deflated and priced with (the spy records it)."""
    from src.models.poisson import CompetitionScoringContext
    from src.walters import soccer_backtest as sb
    ctx = CompetitionScoringContext(avg_goals_per_team_per_match=1.5, home_field_goal_boost=1.2)
    base = _run(store, **CALLS["plain_report"])
    with P.recording(sb) as events:
        moved = _run(store, context=ctx, **CALLS["plain_report"])
    assert [r["match_id"] for r in moved] == [r["match_id"] for r in base]      # the same scored set
    assert digest(moved) != digest(base)
    assert max(abs(a["p_home"] - b["p_home"]) for a, b in zip(moved, base)) > 1e-4
    calls = P.paired(events)
    assert len(calls) == len(moved)
    assert {(i["deflation_g"], i["deflation_b"], i["forecast_g"], i["forecast_b"]) for i, _ in calls} == {
        (1.5, 1.2, 1.5, 1.2)}


def test_the_cli_offers_no_context_flag():
    """Addendum 251 item 2: the gate's walk stays the default; no flag invites option 2 (REJECTED). soccer-backtest's
    call sites pass no `context`, and the command takes no option naming one."""
    import inspect
    import re
    import cli
    src = inspect.getsource(cli)
    for m in re.finditer(r"run_soccer_backtest\(", src):
        depth, i = 0, m.end() - 1
        while True:
            depth += {"(": 1, ")": -1}.get(src[i], 0)
            if depth == 0:
                break
            i += 1
        assert "context" not in src[m.end():i], src[m.start():i + 1]
    assert not re.search(r"""["']--[a-z-]*context[a-z-]*["']""", src)
