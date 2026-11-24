"""THE TRUE-STARTER CEILING, A PROBE, ONE RUN (ARCHITECT 2026-11-24 08:05 ET, addendum 491; GATE-CLASS; lane nhl, #105).

Item 1, verbatim: "DECLARED: THE TRUE-STARTER CEILING, A PROBE, ONE RUN. It is not a candidate. It registers nothing,
promotes nothing, sets no status and runs no shadow. Every line below is frozen now, before any figure of it exists,
and none moves after one does."

What this module does, in item 9(b)'s words, "runs items 3 to 7 in that order and writes nothing: no registry entry, no
export, no row":
  3  the stream, UNCHANGED (nhl_backtest's own: warm-up 2024, scored 2025, preseason cut by its rule, predict then
     update), and BEFORE ANY LOG-LOSS IS COMPUTED three checks that refuse with no figure printed (INVALID, not a run):
     (a) the scored games number 1,394 and the sha256 of their match ids is the one nhl-v6, nhl-v7 and nhl-v8 recorded;
     (b) both starters known on every scored game; a warm-up side with no known starter prices at zero, counted;
     (c) v1 on this stream reads 0.6909 to four places, and the home-rate baseline less 0.010 reads 0.6866.
  4  the model form, UNCHANGED: NHLEloV5 with v1's constants, the goalie term inside the expected score in predict and
     in update. Only the tracker changes (nhl_goalie.HindsightTracker, the game's match id passed for leave-one-out).
  5  the hindsight rate (HindsightTracker), leave-one-out, per goalie per season, from the appearances linked to the
     stream's games of that season.
  6  the verdict line: beats_margin(the leave-one-out log-loss, the home-rate baseline), the gate's function unchanged.
  7  printed beside it, deciding nothing: v1 and v5 (as-of); the leave-one-out figure less v1's; the LEAKED line (the
     game's own appearance left in); the eight prior reads of 2025 as the registry holds them.

The --db is a COPY (198 item 6(ii)): mlb_pitchers_gate.check_db's fence (required, an existing file, never under data/,
never the configured database), no sidecar, opened mode=ro + immutable=1; the app's database is never opened. The copy's
path and sha256 print first, and the sha256 and the sidecars are read again after the walks: a copy that changed is a
refusal, not a run. The registry is only read (registry.get / prior_reads): NHL 2025 stays retired (record_run and
declare refuse every id but nhl-v8 on it), and this module calls neither."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from src.models import nhl_goalie as ng
from src.models.nhl_elo import NHLEloConfig, NHLEloV1, NHLEloV5, home_advantage_from_rate
from src.walters import nhl_backtest as nb

ADDENDUM = "ARCHITECT 2026-11-24 08:05 ET, addendum 491"
TEST_SET = "NHL 2025 (2025-26 regular season; nhl_backtest TEST_SEASON, train 2024)"
RECORDED_RUNS = ("nhl-v6", "nhl-v7", "nhl-v8")                       # 491 item 3(a): the three that recorded the ids
EXPECTED_N = 1394
EXPECTED_SHA = "ab890242fe22077580cdb7495e90f58c519a2ddae96445de508f04b99b4de229"
# The set the stream must equal. It is (EXPECTED_N, EXPECTED_SHA) and nothing else on any run; it is its own name only
# so the tests can stand a synthetic stream in for it. The registry check reads EXPECTED_N / EXPECTED_SHA directly.
IDENTITY = (EXPECTED_N, EXPECTED_SHA)
EXPECTED_V1 = "0.6909"                                                # 491 item 3(c), to four places
EXPECTED_BAR = "0.6866"
COPY_QUERY = "mode=ro&immutable=1&uri=true"
SIDECARS = ("-wal", "-shm", "-journal")

VERDICT_FALSE = ("FALSE: THE GOALIE TERM IN THIS FORM IS CLOSED (491 item 6(a)): v5's term (saves above the league rate "
                 "per shot, shrunk by 2,000 shots, through the Pythagorean slope) on this Elo; the true starter, rated "
                 "on his own whole season, did not carry it to the bar")
VERDICT_TRUE = ("TRUE: THE ROUTE STAYS OPEN, AND NOTHING ELSE FOLLOWS FROM IT (491 item 6(b)): no model is promoted or "
                "shadowed; a goalie candidate would be declared by its own addendum, with an as-of rate, on 2026-27 as "
                "it accrues (600 games or more), at the unchanged gate")


class CeilingRefused(Exception):
    """A refusal before the verdict line: not a run (491 item 8). Its text prints no log-loss."""


class NHLEloHindsight(NHLEloV5):
    """NHLEloV5 exactly (491 item 4: "the goalie term inside the expected score in predict and in update, as v5 ran"),
    the tracker a HindsightTracker: the one difference is that the game's match id and season reach elo_adjustment,
    which leave-one-out needs. predict, update and the unknown-starter count are v5's own."""
    name = "nhl_elo_v5_hindsight_probe"

    def _goalie_diff(self, g) -> float:
        self.tracker.advance_to(g.utc_date)
        h = self.tracker.elo_adjustment(getattr(g, "home_goalie", None), g.utc_date, match_id=g.match_id,
                                        season=g.season)
        a = self.tracker.elo_adjustment(getattr(g, "away_goalie", None), g.utc_date, match_id=g.match_id,
                                        season=g.season)
        return h - a


# ---- the copy -------------------------------------------------------------------------------------------------------

def _sidecars(path: Path) -> list[str]:
    from src.walters.intl_shadow import copy_sidecars
    try:
        return copy_sidecars(path)
    except OSError as err:
        raise CeilingRefused(f"--db {path}: its sidecars cannot be checked ({type(err).__name__}: {err}); nothing "
                             "read") from err


def open_copy(db) -> tuple[Path, str]:
    """The fence, then the copy's sha256, hashed before anything is read. Returns (path, sha256)."""
    from src.walters.intl_shadow import copy_sha256
    from src.walters.mlb_pitchers_gate import GateRefused, check_db
    try:
        path = check_db(db)
    except GateRefused as err:
        raise CeilingRefused(str(err)) from None
    if any(c in str(path) for c in "?#%"):
        raise CeilingRefused(f"--db {db}: a path holding '?', '#' or '%' cannot be opened through a URI safely; copy "
                             "it to a plain path; nothing read")
    side = _sidecars(path)
    if side:
        raise CeilingRefused(f"--db {path}: a sidecar is beside the copy ({', '.join(side)}): a .backup copy has none; "
                             "nothing read")
    try:
        return path, copy_sha256(path)
    except OSError as err:
        raise CeilingRefused(f"--db {path}: cannot be hashed ({type(err).__name__}: {err}); nothing read") from err


@contextmanager
def copy_binding(path: Path):
    """Every session of the block on the copy, mode=ro + immutable=1: database's engine and SessionLocal rebound for the
    block and restored on exit (cup_perfect_xi.copy_binding's pattern), so nhl_backtest's own loaders read the copy
    unchanged (491 item 3: "THE STREAM, UNCHANGED")."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool

    import src.db.database as database
    eng = create_engine(f"sqlite:///file:{path.as_posix()}?{COPY_QUERY}", poolclass=NullPool,
                        connect_args={"uri": True, "check_same_thread": False})
    try:
        with eng.connect() as c:
            c.execute(text("SELECT 1 FROM matches LIMIT 1"))
            c.execute(text("SELECT 1 FROM nhl_goalie_appearances LIMIT 1"))
    except Exception as err:  # noqa: BLE001 - an unreadable copy is a refusal, nothing read
        eng.dispose()
        raise CeilingRefused(f"--db {path}: cannot be read through a mode=ro + immutable=1 URI "
                             f"({type(err).__name__}); nothing read") from None
    saved = (database._engine, database.SessionLocal)
    database._engine = eng
    database.SessionLocal = sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True,
                                         expire_on_commit=False)
    try:
        yield path
    finally:
        database._engine, database.SessionLocal = saved
        eng.dispose()


# ---- item 5's inputs ------------------------------------------------------------------------------------------------

def season_appearances(stream: nb.Stream) -> list[ng.SeasonAppearance]:
    """Every stored appearance (shots and saves known, relief included, as v5 counted them) whose linked match is one of
    the stream's games, carrying that game's season. 2023-24's appearances are linked to no stream game, so they enter
    nothing (491 item 5(d)); a playoff game of the stream is a stream game."""
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import NHLGoalieAppearance

    season_of = {g.match_id: g.season for g in (*stream.train, *stream.test) if g.match_id is not None}
    out = []
    with session_scope() as s:
        rows = s.execute(select(NHLGoalieAppearance.match_id, NHLGoalieAppearance.side, NHLGoalieAppearance.goalie_id,
                                NHLGoalieAppearance.shots_against, NHLGoalieAppearance.saves)
                         .where(NHLGoalieAppearance.match_id.is_not(None),
                                NHLGoalieAppearance.shots_against.is_not(None),
                                NHLGoalieAppearance.saves.is_not(None))
                         .order_by(NHLGoalieAppearance.match_id, NHLGoalieAppearance.side,
                                   NHLGoalieAppearance.goalie_id)).all()
    for mid, side, gid, shots, saves in rows:
        if mid in season_of:
            out.append(ng.SeasonAppearance(mid, season_of[mid], side, gid, shots, saves))
    return out


def unknown_sides(games) -> int:
    return sum((g.home_goalie is None) + (g.away_goalie is None) for g in games)


# ---- the run --------------------------------------------------------------------------------------------------------

def prior_reads() -> list[tuple[str, float | None]]:
    """The eight prior reads of NHL 2025 as the registry holds them (491 item 7): (id, its recorded log-loss)."""
    from src.walters import registry as reg
    out = []
    for p in reg.prior_reads(TEST_SET, None):
        e = reg.get(p["id"]) or {}
        res = ((e.get("run") or {}).get("result") or {}) if isinstance(e.get("run"), dict) else {}
        ll = res.get("log_loss") if isinstance(res, dict) else None
        out.append((p["id"], ll if isinstance(ll, (int, float)) else None))
    return out


def check_identity(stream: nb.Stream) -> list[str]:
    """491 item 3(a). Refuses unless the scored games and their ids are the set nhl-v6/v7/v8 recorded; the recorded
    sha256 is also read from those three entries and must be 491's. Returns its console lines."""
    from src.walters import registry as reg
    ids = [g.match_id for g in stream.test]
    for eid in RECORDED_RUNS:
        run = (reg.get(eid) or {}).get("run") or {}
        if run.get("ids_sha256") != EXPECTED_SHA or run.get("n_scored") != EXPECTED_N:
            raise CeilingRefused(f"INVALID (491 item 3(a)): the registry's {eid} does not hold n_scored {EXPECTED_N} "
                                 f"and ids sha256 {EXPECTED_SHA}; nothing scored, no figure printed, not a run")
    if any(i is None for i in ids):
        raise CeilingRefused("INVALID (491 item 3(a)): a scored game carries no match id; nothing scored, no figure "
                             "printed, not a run")
    sha = reg._ids_sha(ids)
    n_want, sha_want = IDENTITY
    if len(ids) != n_want or len(set(ids)) != len(ids) or sha != sha_want:
        raise CeilingRefused(f"INVALID (491 item 3(a)): the scored games number {len(ids)} with ids sha256 {sha}, not "
                             f"{n_want} with {sha_want} (as {', '.join(RECORDED_RUNS)} recorded); nothing scored, no "
                             "figure printed, not a run")
    return [f"  (a) scored games {len(ids)} · ids sha256 {sha} · the set {', '.join(RECORDED_RUNS)} recorded: OK"]


def check_starters(stream: nb.Stream) -> list[str]:
    """491 item 3(b): both starters known on every scored game; the warm-up's unknown sides price at zero, counted."""
    both, n = nb.starter_coverage(stream.test)
    if both != n:
        raise CeilingRefused(f"INVALID (491 item 3(b)): both starters are known on {both} of {n} scored games, not "
                             "every one; nothing scored, no figure printed, not a run")
    return [f"  (b) both starters known on every scored game: {both} of {n} · warm-up sides with no known starter "
            f"(priced at zero, as in v5): {unknown_sides(stream.train)}"]


def check_reference(stream: nb.Stream, base: nb.GateResult, cfg: NHLEloConfig) -> tuple[list[str], nb.GateResult]:
    """491 item 3(c): v1 on this stream reads 0.6909 to four places, and the home-rate baseline less 0.010 reads 0.6866.
    Refuses without printing either figure; returns v1's result for item 7."""
    v1 = nb.run_gate(stream, NHLEloV1(cfg))
    bar = base.ll_home - nb.LL_MARGIN
    if v1.ll_model is None or f"{v1.ll_model:.4f}" != EXPECTED_V1 or f"{bar:.4f}" != EXPECTED_BAR:
        raise CeilingRefused(f"INVALID (491 item 3(c)): v1 on this stream does not read {EXPECTED_V1}, or the home-rate "
                             f"baseline less {nb.LL_MARGIN:.3f} does not read {EXPECTED_BAR}, to four places; no figure "
                             "printed, not a run")
    return [f"  (c) v1 on this stream reads {EXPECTED_V1} and the home-rate baseline less {nb.LL_MARGIN:.3f} reads "
            f"{EXPECTED_BAR}, to four places: OK"], v1


def walk(out: Callable[[str], None] = print) -> dict:
    """Items 3 to 7 on whatever database the session binding points at (copy_binding). Returns the figures; prints the
    checks as they pass. A CeilingRefused before the walks prints no log-loss."""
    games = nb.attach_goalies(nb.load_games())
    stream = nb.build_stream(games, dict(nb.SEASON_STARTS))
    base = nb.baselines(stream)
    if base.verdict.startswith("INVALID"):
        raise CeilingRefused(f"INVALID (491 item 3): {base.verdict}; no figure printed, not a run")
    out(f"ITEM 3 · THE STREAM, UNCHANGED (nhl_backtest's own: warm-up {nb.TRAIN_SEASON} {len(stream.train)} games, "
        f"scored {nb.TEST_SEASON} {len(stream.test)}, preseason cut by its rule, predict then update)")
    lines = check_identity(stream) + check_starters(stream)
    apps = season_appearances(stream)
    by_season = {s_: sum(1 for a in apps if a.season == s_) for s_ in (nb.TRAIN_SEASON, nb.TEST_SEASON)}
    try:                                     # item 5's inputs, checked before any figure of a model is computed
        loo_tr = ng.HindsightTracker(apps, leave_one_out=True)
        leak_tr = ng.HindsightTracker(apps, leave_one_out=False)
        for s_ in by_season:
            loo_tr.league(s_)
    except (ValueError, KeyError) as err:
        raise CeilingRefused(f"INVALID (491 item 5): the appearances cannot be summed as declared ({err}); no figure "
                             "printed, not a run") from None
    cfg = NHLEloConfig(home_advantage=home_advantage_from_rate(base.home_rate))
    ref, v1 = check_reference(stream, base, cfg)
    for line in lines + ref:
        out(line)
    loo_model = NHLEloHindsight(cfg, tracker=loo_tr)
    loo = nb.run_gate(stream, loo_model)
    leaked = nb.run_gate(stream, NHLEloHindsight(cfg, tracker=leak_tr))
    v5_model = NHLEloV5(cfg, tracker=ng.GoalieTracker(nb.load_goalie_appearances()))
    v5 = nb.run_gate(stream, v5_model)
    return {"stream": stream, "base": base, "cfg": cfg, "v1": v1, "loo": loo, "leaked": leaked, "v5": v5,
            "apps": by_season, "league": {s_: loo_tr.league(s_) for s_ in by_season if by_season[s_]},
            "loo_unknown": loo_model.unknown_starters, "v5_unknown": v5_model.unknown_starters}


def lines(r: dict) -> list[str]:
    """Items 4 to 7, printed after the walks (and after the copy is read again)."""
    base, loo = r["base"], r["loo"]
    L = [f"ITEM 4 · THE MODEL FORM, UNCHANGED: NHLEloV5 with v1's constants (k {r['cfg'].k_factor:g}, mov_base "
         f"{r['cfg'].mov_base:g}, regression {r['cfg'].season_regression:g}, home advantage "
         f"{r['cfg'].home_advantage:.1f} from the {nb.TRAIN_SEASON} home rate {base.home_rate:.4f}); only the tracker "
         "changes",
         f"ITEM 5 · THE HINDSIGHT RATE, leave-one-out, no decay, PRIOR_SHOTS {ng.PRIOR_SHOTS:g}, whole-season league "
         "figures, no boot prior; 2023-24 enters nothing"]
    for s_, n in r["apps"].items():
        lg = r["league"].get(s_)
        L.append(f"  {s_}: appearances linked to the stream's games {n}" + (
            f" · league save rate m {lg[0]:.4f} · shots per team-game {lg[1]:.2f} · goals per team-game {lg[2]:.3f}"
            if lg else ""))
    L.append(f"  scored sides priced with an unknown starter: {r['loo_unknown']}")
    verdict = nb.beats_margin(loo.ll_model, base.ll_home)
    L += [f"ITEM 6 · THE VERDICT LINE: beats_margin(leave-one-out log-loss {loo.ll_model:.4f}, home-rate baseline "
          f"{base.ll_home:.4f}) = {'TRUE' if verdict else 'FALSE'} (need <= {base.ll_home - nb.LL_MARGIN:.4f})",
          f"  {VERDICT_TRUE if verdict else VERDICT_FALSE}",
          "  calibration bands and rating spread, printed, deciding nothing:"]
    for b in loo.bands:
        tag = ("within ±5pp" if b["ok"] else "outside ±5pp") if b["gated"] else "(n < 100)"
        L.append(f"     {b['band'] * 10:>2}-{b['band'] * 10 + 10}%: n={b['n']:<4} stated {b['stated']:.3f} realized "
                 f"{b['realized']:.3f} gap {b['gap'] * 100:+.1f}pp {tag}")
    L.append(f"     final ratings {loo.rating_min:.0f}-{loo.rating_max:.0f} (bound {nb.RATING_MIN:.0f}-"
             f"{nb.RATING_MAX:.0f})" + (f" outliers {len(loo.outliers)}" if loo.outliers else ""))
    L += ["ITEM 7 · PRINTED BESIDE IT, DECIDING NOTHING",
          f"  v1 on the same stream: log-loss {r['v1'].ll_model:.4f}",
          f"  v5 (as-of) on the same stream: log-loss {r['v5'].ll_model:.4f} (sides with an unknown starter "
          f"{r['v5_unknown']})",
          f"  leave-one-out less v1: {loo.ll_model - r['v1'].ll_model:+.4f}",
          f"  LEAKED (the game's own appearance left in; it holds the game's own result): log-loss "
          f"{r['leaked'].ll_model:.4f}",
          "  the prior reads of NHL 2025, as the registry holds them:"]
    for eid, ll in prior_reads():
        L.append(f"    {eid}: log-loss " + (f"{ll:.4f}" if ll is not None else "not recorded"))
    L.append(f"ONE RUN (491 item 8): this console is the result. Nothing was written: no registry entry, no export, no "
             "row.")
    return L


def run(db, out: Callable[[str], None] = print) -> int:
    """The command's body: 0 when the console reaches the verdict line, 2 on a refusal (not a run)."""
    from src.walters.intl_shadow import copy_sha256
    try:
        path, sha = open_copy(db)
        out(f"NHL TRUE-STARTER CEILING · {ADDENDUM} · a probe, one run, never a candidate")
        out(f"--db {path} · sha256 {sha} · a .backup copy, opened {COPY_QUERY.rsplit('&uri', 1)[0]} (the app's "
            "database is not read)")
        with copy_binding(path):
            r = walk(out)
        if _sidecars(path):
            raise CeilingRefused(f"--db {path}: a sidecar appeared during the read; the copy is not the one hashed; "
                                 "not a run")
        if copy_sha256(path) != sha:
            raise CeilingRefused(f"--db {path}: its sha256 changed during the read; not a run")
    except CeilingRefused as err:
        out(f"REFUSED: {err}")
        return 2
    except OSError as err:
        out(f"REFUSED: --db {db}: {type(err).__name__}: {err}; not a run")
        return 2
    except Exception as err:  # noqa: BLE001 - sqlalchemy's DBAPIError (a table or column the copy lacks): not a run
        from sqlalchemy.exc import DBAPIError
        if not isinstance(err, DBAPIError):
            raise
        out(f"REFUSED: --db {db}: the copy cannot be read ({type(err).__name__}); not a run")
        return 2
    for line in lines(r):
        out(line)
    return 0

