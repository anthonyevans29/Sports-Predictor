"""
MLB-PITCHERS-V1 — THE PITCHER-LAYER TEST (ARCHITECT 2026-10-31 11:45 ET, addendum 190; lane mlb-pitchers, #507;
GATE-CLASS). The ruling, verbatim, the harness and Code's readings: docs/specs/mlb-pitchers-v1.md. Registry id
`mlb-pitchers-v1` (docs/registry/experiments.json).

    mlb-pitchers-freeze --db COPY   writes the frozen test cohort BEFORE the run: the 2026 regular-season games with
                                    both sides reconstructed on a live path (src/walters/mlb_pitcher_asof.py, the
                                    receipt's classification), exactly COHORT_N ids, to
                                    docs/registry/ids/mlb-pitchers-v1.cohort.txt and the entry's `test_cohort`
                                    {n, ids_sha256, ids_file, frozen_at, basis}. Reads no outcome.
    mlb-pitchers-gate --db COPY     the ONE run: the pre-checks (declared and unrun, unreserved, the test cohort's
                                    file matching its sha and count, the copy's own re-classification reproducing the
                                    same COHORT_N ids, the copy's production config), then the reservation, then ONE
                                    walk (src/walters/backtest.run_backtest(pitcher_layer=True), sealed_read) pricing
                                    each cohort game OFF and ON, then the metric and the verdict, recorded with
                                    registry.record_run.

- THE ARMS (190 item 1): ON = mlb v2 with the pitcher layer fed the as-of reconstruction (pitcher_stats_asof, the live
  _resolve_pitcher's construction on the as-of sums, then the live missing-starter shrink); OFF = the same walk's
  pitcher-less call (today's backtest). One walk: the same history, profiles and production config (MLB has no Elo;
  Code's reading (f)). Raw p_home, pre any blend; park factor and the market blend in neither arm.
- THE SCORED SET: the frozen cohort exactly. A cohort game either arm cannot price (warm-up under 40 games, a missing
  profile, not FINISHED with both scores) makes the run INVALID: printed with the ids and the count, recorded, never
  scored on a subset (Code's reading (c)).
- THE METRIC AND THE BAR (190 item 3): mean home-side log-loss, ll = -(y ln p + (1 - y) ln(1 - p)), p floored at 1e-12
  as evaluation.score_winner floors it, both arms over the cohort, unrounded. PASS iff (OFF - ON) >= BAR (the text's
  >=, literally: exactly 0.0050 passes, a tie of the arms rejects; Code's reading (e)); else REJECT. Brier and the per
  UTC month lines print for the record and gate nothing.
- THE FENCE (190 item 3): run_backtest(pitcher_layer=True) on MLB with season 2026 (or every season) is refused while
  the entry is declared and unrun, and while it is absent (fails closed); lifted once its run is recorded. The gate's
  own walk passes sealed_read after its reservation. OFF (the default walk) is never fenced by it.
- --db: required; an existing SQLite file, never created, never under the repo's data/ (law 5) and never the app's
  configured database; opened mode=ro (a URI) by both the sqlite3 as-of loader and the SQLAlchemy session the walk
  reads through.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import subprocess
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

from src.timeutil import utc_now_naive
from src.walters.ncaa_backtest import FenceRefused

EID = "mlb-pitchers-v1"
SEASON = "2026"
COMPETITION = "MLB"
COHORT_N = 1553
BAR = 0.0050
LL_FLOOR = 1e-12                                  # evaluation._log_loss_one's floor
COHORT_KEY = "test_cohort"                        # never `confirmation_cohort` (the confirmation machinery's key)
COHORT_FILE = f"{EID}.cohort.txt"
RULING = "ARCHITECT 2026-10-31 11:45 ET, addendum 190"
COHORT_RULE = ("the 2026 regular-season games with BOTH sides reconstructed on a live path (addendum 190 item 2): per "
               "game, both sides' P label in the receipt's PATHS (blend: starter and bullpen; starter, league bullpen; "
               "bullpen half-weighted, starter unknown; neutral (no data)), classified by "
               "src/walters/mlb_pitcher_asof.classify (the #702 receipt's per-side classification, #703's pregame "
               "identity and complete ERAs) on the --db copy")
# 190 item 3's fence sentence, verbatim (quoted in every refusal)
FENCE_TEXT = ("One read (law 3): the registry entry mlb-pitchers-v1 is DECLARED at this addendum's instant "
              "(2026-10-31T15:45:00Z) with the plan (arms, cohort sha, metric, bar) frozen in it; the MLB backtest with "
              "the pitcher layer on is fenced on 2026 while the entry is declared and unrun, the gate's run excepted "
              "— the expansion fence's precedent.")

RESERVATION = None                  # None = docs/registry/<EID>.started.json beside the ledger (tests: a tmp path)
DATA_DIR = None                     # None = the repo's data/ (tests point it at a tmp dir)


class GateRefused(RuntimeError):
    """A refusal of mlb-pitchers-freeze / mlb-pitchers-gate: the CLI prints REFUSED and exits 2."""


class PitcherFenceRefused(FenceRefused):
    """run_backtest(pitcher_layer=True) refused by the 2026 fence (a FenceRefused, so every caller that maps the NCAA
    fence to REFUSED / exit 2 maps this one too)."""


def _reg():
    from src.walters import registry as reg
    return reg


def _iso(d) -> str | None:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ") if d else None


# ------------------------------------------------------------------------------------------------ the fence --

def _entry() -> dict | None:
    """The registry entry (None when absent). An unreadable registry (a corrupt or truncated experiments.json, an OSError)
    raises GateRefused naming it, never a raw traceback."""
    reg = _reg()
    try:
        return reg.get(EID, reg.LEDGER)
    except (OSError, ValueError) as x:
        raise GateRefused(f"the registry {reg.LEDGER} cannot be read ({type(x).__name__}: {x}); nothing read, "
                          "nothing written")


def run_recorded() -> bool:
    """True once the registry records mlb-pitchers-v1's one run (`run` set). An absent entry reads as not recorded;
    an unreadable registry raises GateRefused."""
    e = _entry()
    return bool(e and e.get("run"))


def fence_walk(competition_code, season) -> str | None:
    """The 2026 fence on run_backtest(pitcher_layer=True): MLB with season 2026, or every season (None or blank), is
    refused while the run is unrecorded (the entry declared and unrun, or absent: fails closed). None = allowed. Only
    the pitcher-layer walk asks; the default walk never does."""
    if (competition_code or "").strip().upper() != COMPETITION:
        return None
    s_ = "" if season is None else str(season).strip()
    if s_ not in ("", SEASON):
        return None
    try:
        e = _entry()
    except GateRefused as x:                         # an unreadable registry: the fence fails closed, by name
        return (f"{COMPETITION} {s_ or '(every season)'} with the pitcher layer on: {x} (fails closed). {RULING} "
                f"item 3, verbatim: \"{FENCE_TEXT}\"")
    if e and e.get("run"):
        return None
    state = "absent from the registry (fails closed)" if e is None else f"{e.get('status')} and unrun"
    return (f"{COMPETITION} {s_ or '(every season)'} with the pitcher layer on: {EID} is {state}; its one read is "
            f"mlb-pitchers-gate (docs/specs/mlb-pitchers-v1.md). {RULING} item 3, verbatim: \"{FENCE_TEXT}\"")



def sealed_refusal(competition_code, season) -> str | None:
    """The gate's own exception to the fence, checked (Codex on #748, P1): `sealed_read` suppresses the fence only
    when the gate's reservation exists (its one run has begun). A sealed read with the fence standing and no
    reservation is refused like the fenced walk itself, so no caller reaches the 2026 ON arm by the flag alone."""
    why = fence_walk(competition_code, season)
    if why is None or os.path.exists(reservation_path()):
        return None
    return f"sealed_read without the gate's reservation ({os.path.relpath(reservation_path())} absent): {why}"

# ------------------------------------------------------------------------------------------------ the copy --

def _data_dir() -> Path:
    return Path(DATA_DIR).resolve() if DATA_DIR else (Path(_reg().ROOT) / "data").resolve()


def _main_checkout_data() -> Path | None:
    """The MAIN checkout's data/ when this code runs from a git worktree (Code sessions do): the parent of git's
    common dir, joined with data/. None outside a git checkout, or when it is the code checkout's own data/."""
    try:
        out = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=_reg().ROOT,
                             capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    return (Path(out.stdout.strip()).resolve().parent / "data").resolve()


def _data_dirs() -> list[Path]:
    """Every data/ the fence keys on: the code checkout's own (or DATA_DIR) and, from a worktree, the main
    checkout's."""
    dirs = [_data_dir()]
    main = _main_checkout_data()
    if main is not None and main not in dirs:
        dirs.append(main)
    return dirs


def _same_file(a: Path, b: Path) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def _app_db() -> Path | None:
    """The app's configured SQLite file (settings.database_url), resolved; None for another backend."""
    try:
        from config import settings
        url = settings.database_url
    except Exception:                               # noqa: BLE001 - no settings: nothing to compare against
        return None
    if not url or not url.startswith("sqlite:///"):
        return None
    return Path(url.replace("sqlite:///", "", 1)).expanduser().resolve()


def check_db(db) -> Path:
    """--db: required; refused (never created) unless an existing file outside the repo's data/ (law 5, by resolved
    path, so a symlink or a relative path cannot slip by; from a git worktree the main checkout's data/ too; and by
    identity, so a hard link to a file directly under a data/ cannot slip by) that is not the app's configured
    database."""
    if db is None or not str(db).strip():
        raise GateRefused("--db PATH is required: a .backup copy of the database outside data/ (law 5); the gate never "
                          "reads the live database")
    tgt = Path(str(db)).expanduser().resolve()
    for data in _data_dirs():
        if tgt == data or data in tgt.parents:
            raise GateRefused(f"--db {db} resolves under the repo's data/ ({data}): law 5, the database is never "
                              "touched casually; take a .backup copy outside data/ and pass that")
        try:                                         # by identity too: a hard link to a data/ file is that file
            near = [data / n for n in os.listdir(data)]
        except OSError:
            near = []
        for f in near:
            if f.is_file() and _same_file(tgt, f):
                raise GateRefused(f"--db {db} is the same file as {f} (a hard link into the repo's data/): law 5; "
                                  "take a .backup copy outside data/ and pass that")
    app = _app_db()
    if app is not None and (tgt == app or _same_file(tgt, app)):
        raise GateRefused(f"--db {db} is the app's configured database ({app}): the gate reads a .backup copy only")
    if not tgt.is_file():
        raise GateRefused(f"--db {db}: no file at {tgt}; the gate never creates one")
    return tgt


def open_ro(path: Path):
    """sqlite3 on the copy through a mode=ro URI (never created, never written; SQLite refuses a write)."""
    try:
        con = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        con.execute("SELECT 1 FROM matches LIMIT 1")
    except sqlite3.Error as e:
        raise GateRefused(f"--db {path}: cannot be read through a mode=ro URI ({e}); nothing read")
    return con


@contextmanager
def readonly_session(path: Path):
    """A SQLAlchemy session on the copy through a mode=ro URI (database.readonly_scope's pattern, bound to the --db
    file): no connect hook, no pragma, no commit; closed, never committed. The URI is open_ro's percent-encoded
    path.as_uri() handed to sqlite3 directly, so a '#' or '?' in the path cannot cut the filename or drop mode=ro."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import NullPool

    uri = path.as_uri() + "?mode=ro"                 # percent-encoded: a '#' or '?' in the path cannot drop mode=ro
    eng = create_engine("sqlite://", poolclass=NullPool,
                        creator=lambda: sqlite3.connect(uri, uri=True, check_same_thread=False))
    session = Session(eng, autoflush=False, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        eng.dispose()


def classify_copy(path: Path) -> dict:
    """The receipt's classification of the 2026 season on the copy (read-only). A missing column (law 1) or a twin
    game id (#569) refuses, in the receipt's words."""
    from src.walters import mlb_pitcher_asof as asof
    con = open_ro(path)
    try:
        asof.check_columns(con)
        d = asof.load(con, SEASON)
    except SystemExit as e:
        raise GateRefused(str(e))
    finally:
        con.close()
    return asof.classify(d, SEASON)


FINGERPRINT_RULING = "ARCHITECT 2026-10-31 13:15 ET, addendum 193 item 1"
FINGERPRINT_RULE = (
    "the freeze records a fingerprint of the rows the run reads, and the run refuses before its reservation unless the "
    "copy it is given reproduces it (" + FINGERPRINT_RULING + "). Parts, each the sha256 of its rows as sorted JSON "
    "lines: games, every 2026 MLB match row the walk and the reconstruction read (id, kickoff, status, stage, teams, "
    "final scores, the statsapi id; it holds the cohort games' ids, kickoffs and final scores); appearances, the "
    "pitcher_appearances rows the as-of reconstruction attributes to the season's games (game, side, pitcher, outs, "
    "starter, earned runs); starters, the starting_pitcher rows it reads (game, side, kind, source id, source, "
    "refreshed at, rows held); config, the production config the arms run with (version, baseball_config). A mismatch "
    "is a finding on #507 (the copy is not the frozen one), never a re-freeze and never a run on the other copy")


def _lines_sha(rows) -> dict:
    lines = sorted(json.dumps(r, sort_keys=True, default=str) for r in rows)
    return {"n": len(lines), "sha256": hashlib.sha256("\n".join(lines).encode()).hexdigest()}


def fingerprint(path: Path, version: str, cfg) -> dict:
    """The copy's fingerprint (addendum 193 item 1): the rows the run reads, per part {n, sha256}, and one sha256 over
    the parts. Read-only, through the same mode=ro reader and the same as-of load the classification uses."""
    from src.walters import mlb_pitcher_asof as asof
    con = open_ro(path)
    try:
        asof.check_columns(con)
        d = asof.load(con, SEASON)
        games = [list(r) for r in con.execute(
            "SELECT m.id, m.utc_date, m.status, m.stage, m.home_team_id, m.away_team_id, m.home_score, m.away_score, "
            "m.external_ids FROM matches m JOIN competitions c ON c.id = m.competition_id "
            "WHERE c.code = ? AND m.season = ?", (COMPETITION, SEASON))]
    except SystemExit as e:
        raise GateRefused(str(e))
    except sqlite3.Error as x:
        raise GateRefused(f"the copy cannot be read for its fingerprint ({x}); nothing written, nothing reserved")
    finally:
        con.close()
    apps = [[mid, a["side"], a["pid"], a["outs"], a["starter"], a["er"]] for mid, rows in d["apps"].items()
            for a in rows]
    starters = [[mid, side, p["kind"], p["psid"], p["source"], _iso(p["at"]), p["n"]]
                for mid, sides in d["parts"].items() for side, p in sides.items()]
    config = [[version, cfg.as_dict()]]
    parts = {"games": _lines_sha(games), "appearances": _lines_sha(apps), "starters": _lines_sha(starters),
             "config": _lines_sha(config)}
    whole = hashlib.sha256(json.dumps({k: v["sha256"] for k, v in parts.items()}, sort_keys=True).encode()).hexdigest()
    return {"sha256": whole, "parts": parts, "rule": FINGERPRINT_RULE}


def fingerprint_mismatch(frozen: dict | None, now: dict) -> str | None:
    """None when the copy reproduces the frozen fingerprint; else the refusal, naming each part that differs."""
    if not frozen or not frozen.get("sha256"):
        return (f"the frozen {COHORT_KEY} carries no fingerprint ({FINGERPRINT_RULING}): the copy cannot be checked; "
                "nothing reserved, nothing read, the architect rules")
    if frozen["sha256"] == now["sha256"]:
        return None
    diff = [f"{k} (n {frozen['parts'].get(k, {}).get('n')} -> {v['n']})" for k, v in now["parts"].items()
            if frozen.get("parts", {}).get(k, {}).get("sha256") != v["sha256"]]
    return (f"the copy is not the frozen one: its fingerprint {now['sha256'][:12]}… is not the frozen "
            f"{frozen['sha256'][:12]}… (parts differ: {', '.join(diff) or 'the whole'}). A finding on #507, never a "
            f"re-freeze and never a run on the other copy ({FINGERPRINT_RULING}); nothing reserved, nothing read")


def production_config(s):
    """(version, BaseballConfig) of the copy's production MLB model: the live family's (training._family_for) one
    production row, which must also be the row the walk reads (backtest._load_production_config: the newest
    production MLB row of any family). Refused when there is none, or it carries no
    baseball_config that builds (the walk would silently fall back to the defaults: law 4, never faked)."""
    from sqlalchemy import select

    from src.db.schema import ModelVersion, Sport
    from src.models.baseball import BaseballConfig
    from src.walters import backtest as bt

    from sqlalchemy.exc import SQLAlchemyError

    from src.walters.training import _family_for

    family = _family_for(Sport.MLB)                 # the live path's family (training._resolve_model_version)
    try:
        lives = list(s.execute(select(ModelVersion).where(ModelVersion.sport == Sport.MLB,
                                                          ModelVersion.model_family == family,
                                                          ModelVersion.status == "production")).scalars())
        walk = s.execute(select(ModelVersion).where(ModelVersion.sport == Sport.MLB,
                                                    ModelVersion.status == "production")
                         .order_by(ModelVersion.id.desc())).scalars().first()
    except SQLAlchemyError as x:
        raise GateRefused(f"the copy's model_versions cannot be read through the mode=ro session ({x}); nothing "
                          "reserved, nothing read")
    if len(lives) > 1:
        raise GateRefused(f"the copy holds {len(lives)} production rows of the live MLB family {family}: the live "
                          "model is not one row (law 4); nothing reserved, nothing read")
    mv = lives[0] if lives else None
    # Codex on #748 (P1): the walk (backtest._load_production_config, today's query, kept so OFF is today's backtest)
    # reads the NEWEST production MLB row of any family; the arms must run on the live family's row, so the two rows
    # must be the same row.
    if mv is not None and walk is not None and walk.id != mv.id:
        raise GateRefused(f"the walk's production MLB row (id {walk.id}, family {walk.model_family}) is not the live "
                          f"family's ({family}, id {mv.id}, {mv.version}): the arms would run on another family's "
                          "config; nothing reserved, nothing read")
    if mv is None or not mv.parameters or "baseball_config" not in mv.parameters:
        raise GateRefused(f"the copy holds no production MLB model of the live family {family} with a "
                          "baseball_config: the arms would run on the "
                          "defaults, which is not mlb v2 (law 4); nothing reserved, nothing read")
    try:
        cfg = BaseballConfig(**mv.parameters["baseball_config"])
    except Exception as e:                          # noqa: BLE001
        raise GateRefused(f"the copy's production MLB baseball_config ({mv.version}) does not build ({e}); nothing "
                          "reserved, nothing read")
    if bt._load_production_config(s) != cfg:        # the walk reads this same row
        raise GateRefused("the walk's production config differs from the copy's production row; nothing reserved")
    return mv.version, cfg


# ------------------------------------------------------------------------------------------------ the registry --

def reservation_path() -> str:
    return RESERVATION or os.path.join(os.path.dirname(_reg().LEDGER), f"{EID}.started.json")


def _reserved_why(p: str) -> str:
    try:
        with open(p) as f:
            at = json.load(f).get("started_at", "?")
    except (OSError, ValueError):
        at = "?"
    return (f"{EID}: a run was started at {at} ({os.path.relpath(p)}) and the test cohort may have been read; it is the "
            "one run, recorded or not. Nothing reruns without an architect ruling")


def declared_unrun() -> dict:
    """The registry entry, refusing unless declared and unrun (the cohort is read once) and unreserved."""
    e = _entry()
    if e is None or e.get("status") != "declared" or e.get("run") is not None:
        raise GateRefused(f"{EID} must be declared and unrun in the registry (status "
                          f"{e.get('status') if e else 'absent'}): the test cohort is read once")
    if os.path.exists(reservation_path()):
        raise GateRefused(_reserved_why(reservation_path()))
    return e


def reserve(meta: dict | None = None, no_fetch: bool = False, echo=None) -> str:
    """The exclusive create of docs/registry/mlb-pitchers-v1.started.json, after the cross-ref guard (#329 RULED
    2026-10-08; soccer_expansion.reserve is the precedent): a cohort, run record or reservation of this experiment on
    any ref the clone knows that this tree does not hold identically refuses, naming the ref and the commit."""
    reg = _reg()
    p = reservation_path()
    if os.path.exists(p):
        raise GateRefused(_reserved_why(p))
    try:
        receipt = reg.cross_ref_guard(EID, no_fetch=no_fetch)
    except reg.RegistryError as e:
        raise GateRefused(str(e))
    if echo:
        echo(receipt)
    try:
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise GateRefused(_reserved_why(p))
    try:
        with os.fdopen(fd, "w") as f:
            json.dump({"id": EID, "started_at": _iso(utc_now_naive()), "guard": receipt, **(meta or {})}, f)
            f.write("\n")
    except (OSError, TypeError, ValueError) as x:  # #749 item 1 (addendum 194 item 2): a failed write spends nothing
        try:
            os.remove(p)
        except OSError:
            pass
        raise GateRefused(f"the reservation {os.path.relpath(p)} could not be written ({type(x).__name__}: {x}); the "
                          "file is removed: the one run is not spent, nothing read")
    return p


def frozen_ids(e: dict) -> list[int]:
    """The entry's frozen test cohort, its file verified against its sha256 and count (registry._frozen_base on the
    test_cohort dict) and against COHORT_N."""
    reg = _reg()
    tc = e.get(COHORT_KEY)
    if not tc:
        raise GateRefused(f"{EID} has no frozen {COHORT_KEY}: run mlb-pitchers-freeze --db COPY first and commit "
                          "docs/registry/ in a PR (docs/specs/mlb-pitchers-v1.md)")
    try:
        ids = reg._frozen_base(e, tc, reg.IDS_DIR)
    except reg.RegistryError as x:
        raise GateRefused(str(x))
    except ValueError as x:                         # #749 item 2: a token that is not an id refuses, by name
        raise GateRefused(f"{EID}: the frozen cohort file {tc.get('ids_file')} holds a token that is not an id ({x}); "
                          "nothing reserved, nothing read")
    if len(ids) != COHORT_N or tc.get("n") != COHORT_N:
        raise GateRefused(f"{EID}: the frozen {COHORT_KEY} holds {len(ids)} ids, not the declared {COHORT_N}")
    return ids


# ------------------------------------------------------------------------------------------------ the freeze --

def _month(d) -> str:
    return f"{d:%Y-%m}"


def cohort_basis(cls: dict, ids: list[int]) -> dict:
    """What the freeze records beside the ids: the rule, the cohort by UTC month, its first and last kickoff, the
    games by sides on a path (both / one / neither), and the receipt's per-side P counts on the same read."""
    from src.walters import mlb_pitcher_asof as asof
    games = cls["games"]
    by_sides = Counter(asof.on_path_sides(g) for g in games.values())
    kicks = sorted(games[i]["kick"] for i in ids)
    c = cls["counts"]
    return {"rule": COHORT_RULE, "season": SEASON, "regular_games": len(games),
            "games_by_sides_on_a_path": {"both": by_sides[2], "one": by_sides[1], "neither": by_sides[0]},
            "by_month": dict(sorted(Counter(_month(games[i]["kick"]) for i in ids).items())),
            "first_kickoff": _iso(kicks[0]) if kicks else None, "last_kickoff": _iso(kicks[-1]) if kicks else None,
            "p_counts_per_side": {k[2:]: v for k, v in sorted(c.items()) if k.startswith("P ")}}


def freeze(db, no_fetch: bool = False, echo=None) -> dict:
    """Freeze the test cohort (190 item 2), before the run. Refused, with nothing written, unless the entry is declared
    and unrun with no test_cohort, no cohort file and no reservation; then the cross-ref guard (before any write);
    then the copy's classification must give exactly COHORT_N ids (else REFUSED naming the count: the DB moved).
    Writes docs/registry/ids/mlb-pitchers-v1.cohort.txt (sorted ids, one per line, a trailing newline) and the
    entry's test_cohort {n, ids_sha256 (registry._ids_sha), ids_file, frozen_at, basis, fingerprint (addendum 193 item
    1: the rows the run reads, read from the same copy)}. Never confirmation_cohort."""
    from src.walters import mlb_pitcher_asof as asof

    reg = _reg()
    e = declared_unrun()
    if e.get(COHORT_KEY):
        raise GateRefused(f"{EID}: the test cohort is already frozen ({e[COHORT_KEY].get('ids_sha256', '?')[:12]}…) "
                          "— a frozen cohort never changes")
    fpath = os.path.join(reg.IDS_DIR, COHORT_FILE)
    if os.path.exists(fpath):
        raise GateRefused(f"{EID}: {COHORT_FILE} already exists without a frozen {COHORT_KEY} in the entry: never "
                          "overwritten; the architect rules")
    path = check_db(db)
    try:
        receipt = reg.cross_ref_guard(EID, no_fetch=no_fetch)       # #329: before any write
    except reg.RegistryError as x:
        raise GateRefused(str(x))
    if echo:
        echo(receipt)
    cls = classify_copy(path)
    ids = asof.cohort_ids(cls)
    if len(ids) != COHORT_N:
        raise GateRefused(f"the copy's classification gives {len(ids)} cohort games, not the declared {COHORT_N} "
                          "(190 item 2: the 10-31 console's count): the database moved; nothing written, the "
                          "architect rules")
    basis = cohort_basis(cls, ids)
    basis["selected_at"] = reg._now()
    with readonly_session(path) as s:               # the config the arms will run with (refused when none)
        version, cfg = production_config(s)
    fp = fingerprint(path, version, cfg)            # addendum 193 item 1: which data, beside which games
    # #749 item 3 (addendum 194 item 2): ONE rollback around the whole sequence (the file's create and write, the
    # ledger's reload and save). Any failure removes the file this call created and puts the ledger's bytes back
    # (registry.save truncates before it writes), so a failed freeze leaves nothing and the next freeze is not blocked.
    created, ledger_before = False, None
    try:
        with open(reg.LEDGER, "rb") as f:
            ledger_before = f.read()
        os.makedirs(reg.IDS_DIR, exist_ok=True)
        with open(fpath, "x") as f:
            created = True
            f.write("\n".join(str(i) for i in ids) + "\n")
        entries = reg.load(reg.LEDGER)
        entry = next(x for x in entries if x["id"] == EID)
        entry[COHORT_KEY] = {"n": len(ids), "ids_sha256": reg._ids_sha(ids),
                             "ids_file": f"docs/registry/ids/{COHORT_FILE}", "frozen_at": reg._now(), "basis": basis,
                             "fingerprint": fp}
        reg.save(entries, reg.LEDGER)
    except (OSError, ValueError, TypeError, KeyError, StopIteration) as x:
        undone = []
        if created:
            try:
                os.remove(fpath)
                undone.append("the cohort file is removed")
            except OSError as y:
                undone.append(f"the cohort file could NOT be removed ({y}): remove {fpath} by hand")
        if ledger_before is not None:
            try:
                with open(reg.LEDGER, "rb") as f:
                    same = f.read() == ledger_before
                if not same:
                    with open(reg.LEDGER, "wb") as f:
                        f.write(ledger_before)
                undone.append("the ledger is as it was")
            except OSError as y:
                undone.append(f"the ledger could NOT be restored ({y}): restore docs/registry/experiments.json from git")
        raise GateRefused(f"the freeze could not be completed ({type(x).__name__}: {x}); " + "; ".join(undone)
                          + f"; {COHORT_KEY} stays null: nothing frozen")
    return {"entry": entry, "ids": ids, "guard": receipt, "db": str(path)}


def freeze_lines(r: dict) -> list[str]:
    tc = r["entry"][COHORT_KEY]
    b = tc["basis"]
    s = b["games_by_sides_on_a_path"]
    return [f"MLB-PITCHERS-V1 · FREEZE THE TEST COHORT ({RULING} item 2) · database {r['db']} (mode=ro)",
            f"  {r['guard']}",
            f"  {SEASON} regular-season games read {b['regular_games']}: both sides on a live path {s['both']} · one "
            f"side {s['one']} · neither {s['neither']}",
            "  P per side: " + " · ".join(f"{k} {v}" for k, v in b["p_counts_per_side"].items()),
            f"  cohort {tc['n']} (declared {COHORT_N}) · first kickoff {b['first_kickoff']} · last {b['last_kickoff']}",
            "  by month: " + " · ".join(f"{k} {v}" for k, v in b["by_month"].items()),
            f"  frozen: {tc['ids_file']} · sha256 {tc['ids_sha256']} · {COHORT_KEY} written into the entry",
            f"  fingerprint {tc['fingerprint']['sha256']} ({FINGERPRINT_RULING}): "
            + " · ".join(f"{k} {v['n']} rows {v['sha256'][:12]}…" for k, v in tc["fingerprint"]["parts"].items()),
            "  NOTHING SCORED. Commit docs/registry/ (the entry and the cohort file) in a PR before mlb-pitchers-gate."]


# ------------------------------------------------------------------------------------------------ the run --

def ll_home(p: float, y: bool) -> float:
    """Home-side log-loss, -(y ln p + (1 - y) ln(1 - p)), the realised side's probability floored at 1e-12 as
    evaluation._log_loss_one floors it."""
    return -math.log(max(p, LL_FLOOR)) if y else -math.log(max(1.0 - p, LL_FLOOR))


def brier_home(p: float, y: bool) -> float:
    return (p - (1.0 if y else 0.0)) ** 2


def verdict(ll_off: float, ll_on: float) -> str:
    """190 item 3: PASS only if OFF - ON >= 0.0050, on unrounded values; less, or a tie, REJECTS."""
    return "PASS" if (ll_off - ll_on) >= BAR else "REJECT"


def score(rows, cohort: list[int]) -> dict:
    """The cohort's rows -> the result. Every cohort id must be priced by both arms (one row each); otherwise INVALID,
    with the unpriced ids, and no figure of either arm (never scored on a subset)."""
    want = set(cohort)
    by = {}
    for r in rows or ():
        if r[0] in want:
            by[r[0]] = r
    missing = sorted(want - set(by))
    if missing:
        return {"verdict": "INVALID", "n_cohort": len(want), "n_priced": len(by), "unpriced_n": len(missing),
                "unpriced_ids": missing,
                "why": "a cohort game neither arm could price (warm-up under 40 games, a missing run profile, or not "
                       "FINISHED with both scores): the scored set is the cohort exactly, never a subset"}
    ordered = [by[i] for i in sorted(by)]
    n = len(ordered)
    ll_off = math.fsum(ll_home(r[3], r[2]) for r in ordered) / n
    ll_on = math.fsum(ll_home(r[4], r[2]) for r in ordered) / n
    br_off = math.fsum(brier_home(r[3], r[2]) for r in ordered) / n
    br_on = math.fsum(brier_home(r[4], r[2]) for r in ordered) / n
    months = {}
    for m in sorted({_month(r[1]) for r in ordered}):
        rs = [r for r in ordered if _month(r[1]) == m]
        k = len(rs)
        months[m] = {"n": k, "ll_off": math.fsum(ll_home(r[3], r[2]) for r in rs) / k,
                     "ll_on": math.fsum(ll_home(r[4], r[2]) for r in rs) / k,
                     "brier_off": math.fsum(brier_home(r[3], r[2]) for r in rs) / k,
                     "brier_on": math.fsum(brier_home(r[4], r[2]) for r in rs) / k}
    return {"verdict": verdict(ll_off, ll_on), "n": n, "ll_off": ll_off, "ll_on": ll_on, "delta": ll_off - ll_on,
            "bar": BAR, "brier_off": br_off, "brier_on": br_on, "by_month": months,
            "home_win_rate": sum(1 for r in ordered if r[2]) / n}


def run(db, no_fetch: bool = False, echo=None) -> dict:
    """The ONE run. Before any outcome read, each refusal exit 2 with nothing written: declared and unrun; no
    reservation; the frozen test_cohort present and its file matching its sha and count; the --db copy (check_db);
    the copy's own re-classification exactly COHORT_N ids and the same set as the file; the copy's production config;
    the copy's fingerprint equal to the frozen one (addendum 193 item 1).
    Then the reservation (after the cross-ref guard), then the walk (sealed_read), then the score. The caller records
    it (record)."""
    from src.walters import backtest as bt
    from src.walters import mlb_pitcher_asof as asof

    e = declared_unrun()
    frozen = frozen_ids(e)
    path = check_db(db)
    cls = classify_copy(path)
    ids = asof.cohort_ids(cls)
    if len(ids) != COHORT_N:
        raise GateRefused(f"the copy's re-classification gives {len(ids)} cohort games, not {COHORT_N} (190 item 2: "
                          "the run refuses unless it reproduces 1553 and the same ids); nothing reserved, nothing read")
    if set(ids) != set(frozen):
        raise GateRefused(f"the copy's re-classification is not the frozen cohort: {len(set(frozen) - set(ids))} "
                          f"frozen id(s) missing, {len(set(ids) - set(frozen))} not frozen (190 item 2); nothing "
                          "reserved, nothing read")
    with readonly_session(path) as s:
        version, cfg = production_config(s)
        fp = fingerprint(path, version, cfg)
        fp_now = fp["sha256"]
        why = fingerprint_mismatch(e[COHORT_KEY].get("fingerprint"), fp)
        if why:                                     # addendum 193 item 1: the frozen copy, or no run
            raise GateRefused(why)
        inputs = {mid: (asof.pitcher_stats_asof(cls["games"][mid]["home"], cfg),
                        asof.pitcher_stats_asof(cls["games"][mid]["away"], cfg)) for mid in ids}
        reg = _reg()
        meta = {"db": str(path), "cohort_n": len(ids), "cohort_sha256": reg._ids_sha(ids),
                "production_version": version}
        reserve(meta, no_fetch=no_fetch, echo=echo)
        # from here on, the one run is spent
        rows = bt.run_backtest(season=SEASON, competition_code=COMPETITION, pitcher_layer=True,
                               pitcher_inputs=inputs, session=s, sealed_read=True)
    r = score(rows, ids)
    r.update(cohort_ids=ids, cohort_sha256=reg._ids_sha(ids), production_version=version, fingerprint_sha256=fp_now,
             baseball_config=cfg.as_dict(), db=str(path),
             paths=dict(Counter(f"{cls['games'][m]['home']['label'][2:]} / {cls['games'][m]['away']['label'][2:]}"
                                for m in ids)))
    return r


def result_record(r: dict) -> dict:
    """The run's result as recorded (registry.record_run): every figure unrounded; the ids are the sidecar's."""
    keep = ("verdict", "n", "ll_off", "ll_on", "delta", "bar", "brier_off", "brier_on", "by_month", "home_win_rate",
            "n_cohort", "n_priced", "unpriced_n", "unpriced_ids", "why", "cohort_sha256", "fingerprint_sha256",
            "production_version",
            "baseball_config", "paths")
    out = {k: r[k] for k in keep if k in r}
    out["metric"] = "mean home-side log-loss, -(y ln p + (1 - y) ln(1 - p)), p floored at 1e-12; Brier (p - y)^2"
    out["ruling"] = f"{RULING} (pre-run, frozen; docs/specs/mlb-pitchers-v1.md)"
    return out


def record(r: dict) -> dict:
    """registry.record_run(EID, the cohort ids, the result): ids/mlb-pitchers-v1.txt and the run block; status run.
    The verdict itself is recorded by Code's PR on the architect's ruling."""
    reg = _reg()
    return reg.record_run(EID, list(r["cohort_ids"]), result_record(r), reg.LEDGER, reg.IDS_DIR)


def run_lines(r: dict) -> list[str]:
    L = [f"  production config: {r['production_version']} · {json.dumps(r['baseball_config'], sort_keys=True)}",
         f"  cohort {len(r['cohort_ids'])} · sha256 {r['cohort_sha256']} (the frozen file, re-classified on this copy)",
         f"  fingerprint {r['fingerprint_sha256']}: the frozen copy's ({FINGERPRINT_RULING})",
         "  paths (home / away): " + " · ".join(f"{k} {v}" for k, v in sorted(r["paths"].items()))]
    if r["verdict"] == "INVALID":
        L.append(f"  INVALID: {r['unpriced_n']} of {r['n_cohort']} cohort games unpriced by the walk ({r['why']}); "
                 "no figure of either arm is printed")
        L.append("  unpriced ids: " + ", ".join(str(i) for i in r["unpriced_ids"]))
        L.append("  VERDICT (computed; the architect rules): INVALID")
        return L
    L += [f"  scored {r['n']} (the cohort exactly) · home win rate {r['home_win_rate']!r}",
          f"  log-loss OFF {r['ll_off']!r}",
          f"  log-loss ON  {r['ll_on']!r}",
          f"  OFF - ON     {r['delta']!r} against the bar {BAR!r} (>=: PASS; less, or a tie, REJECTS)",
          f"  REPORTED, NOT GATED: Brier OFF {r['brier_off']!r} · Brier ON {r['brier_on']!r}",
          "  REPORTED, NOT GATED, per UTC month: n · LL off · LL on · Brier off · Brier on"]
    for m, v in r["by_month"].items():
        L.append(f"    {m}: n {v['n']} · {v['ll_off']!r} · {v['ll_on']!r} · {v['brier_off']!r} · {v['brier_on']!r}")
    L.append(f"  VERDICT (computed; the architect rules): {r['verdict']}")
    return L
