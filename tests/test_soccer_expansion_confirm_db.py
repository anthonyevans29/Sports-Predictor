"""soccer-expansion-confirm --db COPY (ARCHITECT 2026-11-23 08:54 ET, addendum 453 item 3(d), verbatim): "--db COPY on
soccer-expansion-confirm, the twin of what you built on intl-elo-confirm (346 item 1): the same fence (check_db, no
sidecar, mode=ro and immutable=1), the copy's path and sha256 printed first, serving the no-flag read, --record and, by
(b), --substitute; the registry writes land in the laptop checkout's docs/registry as before. With --substitute the
pick is printed before anything is written, and the evidence gains the copy's file name and sha256. Without --db
nothing changes, pinned byte for byte. --freeze-cohort with --db stays refused. intl-elo-confirm is not touched."

Modelled on intl-elo-confirm's --db tests (tests/test_intl_shadow.py, test_346_* and test_940_*, #938 and #948). The
world is synthetic rows in the throwaway test DB (season 2151/52) and every registry is a TMP one (reg.LEDGER,
reg.IDS_DIR and reg.get point at tmp_path): the real docs/registry/ is never written, data/ is never touched, and every
copy is a .backup-API copy of the test DB under tmp_path. The byte-for-byte pin of the command without --db runs
tests/soccer_expansion_confirm_scenario.py in a child process on its own fresh throwaway database and compares it with
tests/golden/soccer_expansion_confirm_no_db.json (Python 3.12 and later) or soccer_expansion_confirm_no_db_py310.json
(Python 3.10 and 3.11), each captured from origin/main 93ff8119's code before the change, on 3.12 and on 3.10: the
recorded log-loss differs in its last digit between the two (Python 3.12's sum() of floats is compensated), on main
as on this branch, so each interpreter is pinned to its own capture."""
import json
import os
import random
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner
from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Sport, Team
from src.walters import intl_shadow as us
from src.walters import registry as reg
from src.walters import soccer_expansion as sx

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "golden" / ("soccer_expansion_confirm_no_db.json" if sys.version_info >= (3, 12)
                            else "soccer_expansion_confirm_no_db_py310.json")
SEASON = "2151/52"
START = datetime(2151, 8, 1)
VERDICT_AT = START + timedelta(days=50)
NAIVES = {"PD": {"H": 0.46, "D": 0.26, "A": 0.28, "n": 380}, "BL1": {"H": 0.43, "D": 0.24, "A": 0.33, "n": 306}}
PLAN = {"n_games": 60, "metric": "log_loss", "bar": 1.0986, "must_beat_reference": True,
        "reference": "pooled naive (each surviving league's frozen 2023/24 H/D/A frequencies) on the same 60 games, "
                     "minus 0.010"}
STAMP = "2151-12-01T00:00:00Z"
_REG_GET0 = reg.get                     # the real function, before any test patches it


def _comp(s, code):
    c = s.execute(select(Competition).where(Competition.code == code)).scalar_one_or_none()
    if c is None:
        c = Competition(sport=Sport.SOCCER, code=code, name=code, area="x", type="LEAGUE")
        s.add(c)
        s.flush()
    return c


@pytest.fixture(scope="module")
def world():
    """PD and BL1 (surviving): 45 finished regular rows each before the verdict, then 35 FINISHED FT rows each after
    it, the two leagues sharing every kickoff; a test-set id after the verdict. `ids`: the eligible fixtures in
    (kickoff, id) order."""
    init_db()
    rng = random.Random(4531)
    out = {"eligible": []}
    with session_scope() as s:
        pre_existing = set(s.execute(select(Competition.code).where(
            Competition.code.in_(("PD", "BL1")))).scalars())
        teams = {}
        for code in ("PD", "BL1"):
            c = _comp(s, code)
            t = [Team(sport=Sport.SOCCER, name=f"SXDB {code} {i}") for i in range(6)]
            s.add_all(t)
            s.flush()
            teams[code] = (c, t)

        def add(code, when, stage):
            c, t = teams[code]
            h, a = rng.sample(range(6), 2)
            m = Match(sport=Sport.SOCCER, competition_id=c.id, season=SEASON, utc_date=when,
                      status=MatchStatus.FINISHED, status_raw="FT", home_team_id=t[h].id, away_team_id=t[a].id,
                      home_score=rng.randint(0, 3), away_score=rng.randint(0, 3), stage=stage)
            s.add(m)
            s.flush()
            return m
        for code in ("PD", "BL1"):
            for k in range(45):
                add(code, START + timedelta(days=k), f"Regular Season - {k + 1}")
        for k in range(35):
            for code in ("PD", "BL1"):
                m = add(code, VERDICT_AT + timedelta(days=1 + k, hours=15), f"Regular Season - {46 + k}")
                out["eligible"].append((m.utc_date, m.id))
        out["test_set"] = add("PD", VERDICT_AT + timedelta(hours=3), "Regular Season - 3").id
    out["eligible"].sort()
    out["ids"] = [i for _, i in out["eligible"]]
    yield out
    from sqlalchemy import delete
    with session_scope() as s:
        s.execute(delete(Match).where(Match.season == SEASON))
        s.execute(delete(Team).where(Team.name.like("SXDB %")))
        s.execute(delete(Competition).where(Competition.code.in_(("PD", "BL1")),
                                            Competition.code.notin_(pre_existing)))


def _entry():
    return {"id": sx.EID, "sport": "soccer", "test_set": "x", "confirmation_window": "w", "confirmation_plan": PLAN,
            "status": "confirming",
            "run": {"run_at": "2151-09-01T00:00:00Z", "ids_file": f"docs/registry/ids/{sx.EID}.txt",
                    "result": {"verdict": "PASS — surviving set PD, BL1", "surviving": ["PD", "BL1"],
                               "per_league": {c: {"naive_freq": NAIVES[c]} for c in NAIVES},
                               "production_version": "v22", "rho": -0.1, "elo_goal_coeff": 0.0008}},
            "verdict": {"verdict": "PASS", "ruling": "ARCHITECT: pass",
                        "at": VERDICT_AT.strftime("%Y-%m-%dT%H:%M:%SZ")}}


def _registry(world, monkeypatch, d: Path, frozen: bool = False) -> dict:
    """A TMP registry at `d` (experiments.json + ids/), and reg.LEDGER / reg.IDS_DIR / reg.get pointed at it. With
    `frozen`, the cohort is the first 60 eligible ids, frozen through the registry's own writer."""
    ids = d / "ids"
    ids.mkdir(parents=True)
    (ids / f"{sx.EID}.txt").write_text(f"{world['test_set']}\n")
    led = d / "experiments.json"
    led.write_text(json.dumps([_entry()]))
    _use(monkeypatch, d)
    if frozen:
        reg.freeze_confirmation_cohort(sx.EID, sorted(world["ids"][:60]), {"rule": sx.CONFIRM_RULE}, path=str(led),
                                       ids_dir=str(ids), no_fetch=True)
    return {"dir": d, "led": led, "ids": ids}


def _use(monkeypatch, d: Path):
    led = d / "experiments.json"
    monkeypatch.setattr(reg, "LEDGER", str(led))
    monkeypatch.setattr(reg, "IDS_DIR", str(d / "ids"))
    monkeypatch.setattr(reg, "get", lambda eid, path=None: _REG_GET0(eid, str(led)))
    monkeypatch.setattr(reg, "_now", lambda: STAMP)


def _files(d: Path) -> dict:
    return {str(p.relative_to(d)): p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file()}


def _app_db_path() -> Path:
    from src.db.database import get_engine
    return Path(get_engine().url.database).resolve()


def _copy(tmp_path, name="copy.db") -> Path:
    """A .backup-API copy of the test store outside data/ (law 5: never a file copy, never under data/)."""
    import sqlite3
    tmp_path.mkdir(parents=True, exist_ok=True)
    dst = tmp_path / name
    src, out = sqlite3.connect(str(_app_db_path())), sqlite3.connect(str(dst))
    try:
        src.backup(out)
    finally:
        out.close()
        src.close()
    assert not any(dst.with_name(dst.name + x).exists() for x in us.COPY_SIDECARS)
    return dst


def _cli(*args):
    import cli
    return CliRunner().invoke(cli.cli, ["soccer-expansion-confirm", *args])


def _head(copy: Path) -> str:
    return (f"--db {copy.resolve()} · sha256 {us.copy_sha256(copy)} · a .backup copy, opened mode=ro&immutable=1 "
            "(the app's database is not read)")


def _real_registry_shas() -> dict:
    root = Path(reg.ROOT) / "docs" / "registry"
    return {p: us.copy_sha256(p) for p in sorted(root.rglob("*")) if p.is_file()}


@contextmanager
def _shape_453(world):
    """Addendum 453 item 1's shape on this world's frozen first 60: cohort fixture ids[3] CANCELLED under the raw code
    ABD (its score cleared); the cohort's last, ids[59], moved one hour past ids[62]'s kickoff and SCHEDULED, so
    ids[60..63] (FINISHED, never in the cohort) kick off before the moved last and are passed over. Restored after."""
    ids = world["ids"]
    released, last = ids[3], ids[59]
    with session_scope() as s:
        old = {i: (lambda m: (m.status, m.status_raw, m.home_score, m.away_score, m.utc_date))(s.get(Match, i))
               for i in (released, last)}
        moved = s.get(Match, ids[62]).utc_date + timedelta(hours=1)
        m = s.get(Match, released)
        m.status, m.status_raw, m.home_score, m.away_score = MatchStatus.CANCELLED, "ABD", None, None
        m = s.get(Match, last)
        m.status, m.status_raw, m.home_score, m.away_score, m.utc_date = (MatchStatus.SCHEDULED, "NS", None, None,
                                                                           moved)
    try:
        yield {"released": released, "last": last, "moved": moved, "passed": ids[60:64], "replacement": ids[64]}
    finally:
        with session_scope() as s:
            for i, (st, raw, hs, as_, when) in old.items():
                m = s.get(Match, i)
                m.status, m.status_raw, m.home_score, m.away_score, m.utc_date = st, raw, hs, as_, when


def _iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------- the no-db pin --

def test_453_without_db_the_command_is_unchanged_byte_for_byte(tmp_path):
    """453 item 3(d): "Without --db nothing changes, pinned byte for byte." The scenario (provisional read, refused
    record, freeze, frozen read, an ABD release after the cohort's last moved, the substitution, the reads, the refused
    and the written record) runs in a child process on its own fresh throwaway database and a tmp registry; every
    step's exit code, console and registry bytes equal the capture taken from origin/main 93ff8119's code."""
    out = tmp_path / "now.json"
    env = {k: v for k, v in os.environ.items() if k not in ("KALSHI_API_KEY_ID", "KALSHI_PRIVATE_KEY_PATH")}
    env.update(DATABASE_URL=f"sqlite:///{tmp_path / 'golden.db'}", SP_LOCK=str(tmp_path / "db.lock"),
               SP_EXPORTS_MIRROR_ROLE="laptop", SP_HOST_ENV=str(tmp_path / "no-host.env"), OPEN_BROWSER="false",
               API_FOOTBALL_KEY="test-dummy")
    before = _real_registry_shas()
    import tempfile
    tmp_before = sorted(Path(tempfile.gettempdir()).glob("sx-golden-reg-*"))
    r = subprocess.run([sys.executable, str(HERE / "soccer_expansion_confirm_scenario.py"), str(HERE.parent),
                        str(out)], cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout + r.stderr
    # review nit: the scenario's registry lives under the child's cwd (tmp_path), never left in the system temp dir
    assert sorted(Path(tempfile.gettempdir()).glob("sx-golden-reg-*")) == tmp_before
    assert len(list(tmp_path.glob("sx-golden-reg-*"))) == 1
    golden = json.loads(GOLDEN.read_text())
    now = json.loads(out.read_text())
    assert len(now["steps"]) == len(golden["steps"]) == 13
    for g, n in zip(golden["steps"], now["steps"]):
        assert n == g, g["args"]
    assert now == golden
    assert out.read_bytes() == GOLDEN.read_bytes()
    assert _real_registry_shas() == before                    # the real docs/registry/ is never written


# --------------------------------------------------------------- the fence --

def test_453_the_fence_refuses_and_reads_nothing(world, monkeypatch, tmp_path):
    """The twin's fence (346 item 1): missing, under data/ (never created), the app's configured database, not SQLite,
    a -wal / -shm / -journal beside it, a table the read needs missing: REFUSED (exit 2), nothing read, nothing
    written, for the no-flag read, --record and --substitute alike."""
    import sqlite3
    r = _registry(world, monkeypatch, tmp_path / "reg", frozen=True)
    before = _files(r["dir"])
    reads = []
    monkeypatch.setattr(sx, "confirming", lambda: reads.append(1))
    data_dir = Path(reg.ROOT) / "data"
    sides = []
    for sfx in ("-wal", "-shm", "-journal"):
        side = _copy(tmp_path, f"side{sfx}.db")
        side.with_name(side.name + sfx).write_bytes(b"")
        sides.append((str(side), f"{sfx} sidecar"))
    junk = tmp_path / "junk.db"
    junk.write_text("not a database\n")
    bare = tmp_path / "bare.db"                               # has matches, lacks the rest of what the read needs
    con = sqlite3.connect(str(bare))
    con.execute("CREATE TABLE matches (id INTEGER)")
    con.commit()
    con.close()
    cases = [(str(tmp_path / "missing.db"), "no file at"),
             (str(data_dir / "never-created.db"), "resolves under the repo's data/"),
             (str(_app_db_path()), "the app's configured database"),
             *sides,
             (str(junk), "cannot be read through a mode=ro + immutable=1 URI"),
             (str(bare), "the copy cannot be read for table competitions")]
    for db, why in cases:
        for flags in ((), ("--record", "--ruling", "ARCHITECT: x"), ("--substitute",)):
            out = _cli(*flags, "--db", db)
            assert out.exit_code == 2 and out.output.startswith("REFUSED: ") and why in out.output, (db, out.output)
            assert "nothing read, nothing written" in out.output and "sha256" not in out.output
            assert "SOCCER-EXPANSION-V1" not in out.output and "PICK" not in out.output
    assert reads == [] and _files(r["dir"]) == before
    assert not (data_dir / "never-created.db").exists()                  # never created (law 5)


def test_453_the_hash_before_the_read_failing_refuses_and_reads_nothing(world, monkeypatch, tmp_path):
    """#940 item 3's twin: the first hash failing is a REFUSED line before the sha line, nothing read or written."""
    r = _registry(world, monkeypatch, tmp_path / "reg", frozen=True)
    before = _files(r["dir"])
    copy = _copy(tmp_path)
    reads = []
    monkeypatch.setattr(sx, "confirming", lambda: reads.append(1))

    def unreadable(path):
        raise PermissionError(13, "Permission denied", str(path))
    monkeypatch.setattr(us, "copy_sha256", unreadable)
    for flags in ((), ("--substitute",), ("--record", "--ruling", "ARCHITECT: x")):
        out = _cli(*flags, "--db", str(copy))
        assert out.exit_code == 2 and out.output.startswith("REFUSED: ") and "could not be hashed" in out.output
        assert "nothing read, nothing written" in out.output
    assert reads == [] and _files(r["dir"]) == before


def test_453_a_copy_that_cannot_be_read_mid_read_is_refused(world, monkeypatch, tmp_path):
    """A database error on the copy (here a copy whose tables exist but lack the columns the read selects) is a
    REFUSED line after the sha line, never a traceback; nothing recorded."""
    import sqlite3
    r = _registry(world, monkeypatch, tmp_path / "reg", frozen=True)
    before = _files(r["dir"])
    thin = tmp_path / "thin.db"
    con = sqlite3.connect(str(thin))
    for t in sx.COPY_TABLES:
        con.execute(f"CREATE TABLE {t} (id INTEGER)")
    con.commit()
    con.close()
    out = _cli("--record", "--ruling", "ARCHITECT: x", "--db", str(thin))
    assert out.exit_code == 2, out.output
    head, rest = out.output.split("\n", 1)
    assert head == _head(thin)
    assert rest.startswith(f"REFUSED: --db {thin.resolve()}: the copy could not be read (") and "nothing recorded" in rest
    assert _files(r["dir"]) == before


# --------------------------------------------------------- --freeze-cohort --

def test_453_freeze_cohort_with_db_is_refused_nothing_read_or_written(world, monkeypatch, tmp_path):
    """453 item 3(b): "--freeze-cohort stays refused on a copy: nothing needs it." Refused before the fence, the hash
    or the registry is read (the twin's refusal of its refused flags), exit 2, nothing written."""
    r = _registry(world, monkeypatch, tmp_path / "reg")
    before = _files(r["dir"])
    copy = _copy(tmp_path)
    called = []
    monkeypatch.setattr(sx, "confirming", lambda: called.append("confirming"))
    monkeypatch.setattr(sx, "open_copy", lambda db: called.append("open_copy"))
    for db in (str(copy), str(tmp_path / "missing.db")):
        out = _cli("--freeze-cohort", "--no-fetch", "--db", db)
        assert out.exit_code == 2
        assert out.output == ("REFUSED: --db reads a copy; --freeze-cohort is never run on a copy (addendum 346 item 1, "
                              "kept by addendum 453 item 3(b): \"--freeze-cohort stays refused on a copy: nothing "
                              "needs it.\"). Nothing was read or written.\n")
    assert called == [] and _files(r["dir"]) == before
    assert not (r["ids"] / f"{sx.EID}.cohort.txt").exists()


# ----------------------------------------------------------- the no-flag read --

def test_453_the_no_flag_read_on_a_copy_prints_path_and_sha_first_then_the_same_read(world, monkeypatch, tmp_path):
    """The copy's path and sha256 FIRST; then the console of the same read through the app's engine, line for line
    (provisional, then frozen); confirmation_read(s=copy) equals confirmation_read() on the same store."""
    from src.walters import mlb_pitchers_gate as mp
    _registry(world, monkeypatch, tmp_path / "reg")
    for frozen in (False, True):
        if frozen:
            _registry(world, monkeypatch, tmp_path / "reg2", frozen=True)
        copy = _copy(tmp_path, f"copy{int(frozen)}.db")
        app = _cli()
        out = _cli("--db", str(copy))
        assert app.exit_code == 0 and out.exit_code == 0, out.output
        head, rest = out.output.split("\n", 1)
        assert head == _head(copy) and rest == app.output
        assert ("cohort FROZEN (60/60" if frozen else "cohort PROVISIONAL (60/60") in rest
        rd_app = sx.confirmation_read()
        with mp.readonly_session(copy) as s:
            assert sx.confirmation_read(s=s) == rd_app
        assert not any(copy.with_name(copy.name + x).exists() for x in us.COPY_SIDECARS)


def test_453_the_read_on_a_copy_reads_the_copy_not_the_app_store(world, monkeypatch, tmp_path):
    """The app's store moves on after the copy is taken (a cohort fixture back to SCHEDULED): the copy's read still
    shows 60/60 labelled and the app's read 59/60; the walk is the copy's (run_soccer_backtest gets its session)."""
    import src.walters.soccer_backtest as sb
    _registry(world, monkeypatch, tmp_path / "reg", frozen=True)
    copy = _copy(tmp_path)
    mid = world["ids"][7]
    with session_scope() as s:
        m = s.get(Match, mid)
        old = (m.status, m.status_raw, m.home_score, m.away_score)
        m.status, m.status_raw, m.home_score, m.away_score = MatchStatus.SCHEDULED, "NS", None, None
    seen = []
    real = sb.run_soccer_backtest
    monkeypatch.setattr(sb, "run_soccer_backtest", lambda *a, **k: seen.append(k.get("session")) or real(*a, **k))
    try:
        out = _cli("--db", str(copy))
        assert out.exit_code == 0 and "60/60 labelled" in out.output, out.output
        assert len(seen) == 2 and all(x is not None for x in seen)
        seen.clear()
        app = _cli()
        assert "59/60 labelled" in app.output and seen == [None, None]
    finally:
        with session_scope() as s:
            m = s.get(Match, mid)
            m.status, m.status_raw, m.home_score, m.away_score = old


# ------------------------------------------------------------------- --record --

def test_453_record_on_a_copy_writes_the_same_registry_change_as_without_db(world, monkeypatch, tmp_path):
    """--record --db COPY writes exactly what --record writes without --db on the same data (the ledger and
    ids/<eid>.confirm.txt, byte for byte, into a tmp registry); the copy's bytes are the same before and after; the
    real docs/registry/ is never written."""
    real_before = _real_registry_shas()
    a = _registry(world, monkeypatch, tmp_path / "A", frozen=True)
    b_dir = tmp_path / "B"
    b_dir.mkdir()
    for rel, data in _files(a["dir"]).items():                        # the same frozen registry, twice
        (b_dir / rel).parent.mkdir(parents=True, exist_ok=True)
        (b_dir / rel).write_bytes(data)
    copy = _copy(tmp_path)
    sha = us.copy_sha256(copy)
    plain = _cli("--record", "--ruling", "ARCHITECT 2151: record it")
    assert plain.exit_code == 0 and "  RECORDED: " in plain.output, plain.output
    _use(monkeypatch, b_dir)
    out = _cli("--record", "--ruling", "ARCHITECT 2151: record it", "--db", str(copy))
    assert out.exit_code == 0, out.output
    head, rest = out.output.split("\n", 1)
    assert head == _head(copy) and rest == plain.output
    assert _files(b_dir) == _files(a["dir"])
    assert (b_dir / "ids" / f"{sx.EID}.confirm.txt").exists()
    assert us.copy_sha256(copy) == sha and not any(copy.with_name(copy.name + x).exists() for x in us.COPY_SIDECARS)
    assert _real_registry_shas() == real_before


def test_453_record_on_a_copy_still_refuses_an_incomplete_read(world, monkeypatch, tmp_path):
    """The record's refusals stand with --db: a provisional cohort, a pending fixture, no --ruling. Nothing written."""
    r = _registry(world, monkeypatch, tmp_path / "reg")
    copy = _copy(tmp_path)
    out = _cli("--record", "--ruling", "ARCHITECT: x", "--db", str(copy))
    assert out.exit_code == 2 and "REFUSED: the read is incomplete — the cohort is not frozen" in out.output
    r = _registry(world, monkeypatch, tmp_path / "reg2", frozen=True)
    before = _files(r["dir"])
    with _shape_453(world):
        copy = _copy(tmp_path, "shaped.db")
        out = _cli("--record", "--ruling", "ARCHITECT: x", "--db", str(copy))
        assert out.exit_code == 2 and "2 cohort fixture(s) lack a label" in out.output, out.output
        out = _cli("--record", "--db", str(copy))
        assert out.exit_code == 2 and "needs --ruling" in out.output
    assert _files(r["dir"]) == before


def test_453_a_copy_changed_during_the_read_is_refused_and_nothing_written(world, monkeypatch, tmp_path):
    """#938's Codex P2s, on this command: a copy deleted, given a -wal / -shm / -journal, or replaced during the read
    is REFUSED (exit 2) before --record or --substitute writes anything; never a traceback."""
    r = _registry(world, monkeypatch, tmp_path / "reg", frozen=True)
    before = _files(r["dir"])
    read0, due0 = sx.confirmation_read, sx.substitutions_due
    with _shape_453(world):
        for flags, nothing in ((("--record", "--ruling", "ARCHITECT: x"), "nothing recorded"),
                               (("--substitute",), "nothing substituted")):
            for i, (act, why) in enumerate([("delete", "could not be re-read after the read"),
                                            ("-wal", "-wal appeared beside it"), ("-shm", "-shm appeared beside it"),
                                            ("-journal", "-journal appeared beside it"),
                                            ("replace", "changed during the read (sha256 ")]):
                copy = _copy(tmp_path, f"c{flags[0][2:]}{i}.db")
                other = _different_copy(tmp_path / "other", f"o{flags[0][2:]}{i}.db")

                def act_on(copy=copy, act=act, other=other):
                    if act == "delete":
                        copy.unlink()
                    elif act == "replace":
                        os.replace(other, copy)
                    else:
                        copy.with_name(copy.name + act).write_bytes(b"")

                def during_read(s=None, act_on=act_on):
                    out = read0(s=s)
                    act_on()
                    return out

                def during_due(e, s, surv, act_on=act_on):
                    out = due0(e, s, surv)
                    act_on()
                    return out
                monkeypatch.setattr(sx, "confirmation_read", during_read)
                monkeypatch.setattr(sx, "substitutions_due", during_due)
                out = _cli(*flags, "--db", str(copy))
                assert out.exit_code == 2 and why in out.output and nothing in out.output, (flags, act, out.output)
                assert out.exception is None or isinstance(out.exception, SystemExit), out.exception
                assert "RECORDED" not in out.output and "SUBSTITUTED" not in out.output and "PICK" not in out.output
                assert _files(r["dir"]) == before


def _different_copy(d: Path, name: str) -> Path:
    """A second .backup copy with one scratch row written into IT (a different sha256 from the copy it will replace);
    the app's store is never written. Left in rollback-journal mode, closed, with no sidecar."""
    import sqlite3
    path = _copy(d, name)
    con = sqlite3.connect(str(path))
    try:
        con.execute("PRAGMA journal_mode=DELETE")
        con.execute("CREATE TABLE zz_scratch (x INTEGER)")
        con.execute("INSERT INTO zz_scratch VALUES (1)")
        con.commit()
    finally:
        con.close()
    assert not any(path.with_name(path.name + x).exists() for x in us.COPY_SIDECARS)
    return path


# --------------------------------------------------------------- --substitute --

def test_453_substitute_on_a_copy_prints_the_pick_before_anything_is_written(world, monkeypatch, tmp_path):
    """453 item 3(d): "With --substitute the pick is printed before anything is written, and the evidence gains the
    copy's file name and sha256." Every console line and every registry write is logged in order: the PICK line comes
    before the first write; the substitution written equals the one written without --db on the same data, plus
    copy_file and copy_sha256."""
    import click
    a = _registry(world, monkeypatch, tmp_path / "A", frozen=True)
    b_dir = tmp_path / "B"
    b_dir.mkdir()
    for rel, data in _files(a["dir"]).items():
        (b_dir / rel).parent.mkdir(parents=True, exist_ok=True)
        (b_dir / rel).write_bytes(data)
    with _shape_453(world) as sh:
        copy = _copy(tmp_path)
        sha = us.copy_sha256(copy)
        plain = _cli("--substitute")
        assert plain.exit_code == 0 and f"SUBSTITUTED: {sh['released']} (ABD" in plain.output, plain.output
        _use(monkeypatch, b_dir)
        events = []
        echo0, write0 = click.echo, reg.substitute_cohort_fixture
        monkeypatch.setattr(click, "echo", lambda msg=None, *a, **k: events.append(("echo", str(msg))) or echo0(
            msg, *a, **k))

        def write(*a, **k):
            events.append(("write", a[1]))
            return write0(*a, **k)
        monkeypatch.setattr(reg, "substitute_cohort_fixture", write)
        out = _cli("--substitute", "--db", str(copy))
    assert out.exit_code == 0, out.output
    lines = out.output.splitlines()
    assert lines[0] == _head(copy)
    pick = [i for i, (k, m) in enumerate(events) if k == "echo" and "PICK" in m]
    wrote = [i for i, (k, _) in enumerate(events) if k == "write"]
    assert len(pick) == 1 and len(wrote) == 1 and pick[0] < wrote[0]
    assert events[wrote[0]] == ("write", sh["released"])
    assert lines[1].startswith(f"  PICK (the rule as built, 453 item 2(b); nothing written yet): release "
                               f"{sh['released']} (raw ABD, cancelled, reason ABD")
    assert lines[2:] == plain.output.splitlines()                     # then exactly the console without --db
    sa = reg.get(sx.EID)                                               # B (patched get)
    sub_b = sa["confirmation_cohort"]["substitutions"]
    sub_a = json.loads((a["dir"] / "experiments.json").read_text())[0]["confirmation_cohort"]["substitutions"]
    assert len(sub_a) == len(sub_b) == 1
    ev = dict(sub_b[0]["evidence"])
    assert ev.pop("copy_file") == copy.name == "copy.db" and ev.pop("copy_sha256") == sha
    assert {**sub_b[0], "evidence": ev} == sub_a[0]
    assert _files(b_dir)["ids/" + f"{sx.EID}.cohort.txt"] == _files(a["dir"])["ids/" + f"{sx.EID}.cohort.txt"]
    assert us.copy_sha256(copy) == sha


def test_453_item_1_shape_the_pick_on_a_copy_is_the_rule_as_built(world, monkeypatch, tmp_path):
    """Addendum 453 item 1's shape: a cohort fixture CANCELLED under the raw code ABD; the cohort's last moved later;
    FINISHED fixtures outside the cohort kicking off before the moved last are passed over; the replacement is the
    first eligible fixture after the latest (kickoff, id) of the cohort (453 item 2(b): "AS BUILT IS THE RULE").
    substitutions_due on the copy's session equals it through the app's store; the console prints the released id,
    its raw code, the replacement and its kickoff, and the (kickoff, id) it was measured from, before the write."""
    from src.walters import mlb_pitchers_gate as mp
    _registry(world, monkeypatch, tmp_path / "reg", frozen=True)
    with _shape_453(world) as sh:
        copy = _copy(tmp_path)
        e, surv, _ = sx.confirming()
        with session_scope() as s:
            due_app = sx.substitutions_due(e, s, surv)
            s.rollback()
        with mp.readonly_session(copy) as s:
            due_copy = sx.substitutions_due(e, s, surv)
        assert due_copy == due_app
        (d,) = due_copy
        with session_scope() as s:
            kick = {i: s.get(Match, i).utc_date for i in (sh["released"], sh["replacement"], *sh["passed"])}
            code = {i: s.get(Match, i).competition.code for i in (sh["released"], sh["replacement"])}
        assert d["released"]["id"] == sh["released"] and d["released"]["status_raw"] == "ABD"
        assert d["released"]["status"] == "cancelled" and d["reason"] == "ABD"
        assert d["last"] == (sh["moved"], sh["last"])
        assert d["replacement"]["id"] == sh["replacement"]
        for p in sh["passed"]:                                          # FINISHED, before the moved last: passed over
            assert kick[p] < sh["moved"] and p not in world["ids"][:60]
        assert (kick[sh["replacement"]], sh["replacement"]) > d["last"]
        out = _cli("--substitute", "--db", str(copy))
    assert out.exit_code == 0, out.output
    rel, rep = sh["released"], sh["replacement"]
    assert out.output.splitlines()[1] == (
        f"  PICK (the rule as built, 453 item 2(b); nothing written yet): release {rel} (raw ABD, cancelled, reason "
        f"ABD, {code[rel]} {_iso(kick[rel])}) -> {rep} ({code[rep]}, kickoff {_iso(kick[rep])}), the first eligible "
        f"fixture after the latest (kickoff, id) in or ever in the cohort, ({_iso(sh['moved'])}, {sh['last']})")
    assert f"  SUBSTITUTED: {rel} (ABD, {code[rel]} {_iso(kick[rel])}) -> {rep} ({code[rep]} {_iso(kick[rep])})" \
        in out.output
    (sub,) = reg.get(sx.EID)["confirmation_cohort"]["substitutions"]
    assert (sub["released"], sub["replacement"], sub["reason"]) == (rel, rep, "ABD")
    assert sub["evidence"]["copy_file"] == copy.name and sub["evidence"]["copy_sha256"] == us.copy_sha256(copy)
    assert sub["evidence"]["replacement_kickoff"] == _iso(kick[rep]) and sub["evidence"]["status_raw"] == "ABD"


def test_453_substitute_on_a_copy_with_nothing_due_writes_nothing(world, monkeypatch, tmp_path):
    r = _registry(world, monkeypatch, tmp_path / "reg", frozen=True)
    before = _files(r["dir"])
    copy = _copy(tmp_path)
    out = _cli("--substitute", "--db", str(copy))
    assert out.exit_code == 0
    assert out.output == _head(copy) + "\nSUBSTITUTE: no unscoreable fixture in the cohort — nothing released\n"
    assert _files(r["dir"]) == before


# ------------------------------------------------------- intl-elo-confirm untouched --

def test_453_intl_elo_confirm_keeps_its_own_refusals():
    """453 item 3(d): "intl-elo-confirm is not touched": its --db still serves the no-flag read and --record only."""
    import cli
    params = {p.name for p in cli.cli.commands["intl-elo-confirm"].params}
    assert params == {"freeze_cohort", "substitute", "record", "ruling", "no_fetch", "db"}
    out = CliRunner().invoke(cli.cli, ["intl-elo-confirm", "--substitute", "--db", "/nonexistent/copy.db"])
    assert out.exit_code == 2 and out.output.startswith("REFUSED: --db reads a copy; --substitute is a registry "
                                                        "decision made on the writer of record's own store")


# ------------------------------------------------------------ the fix round (review of the uncommitted head) --

@contextmanager
def _prod_soccer(version, rho, coeff):
    """A production soccer ModelVersion `version` in the test store, any other production soccer row set aside while it
    stands (one production row per family: the NOTE's _resolve_model_version reads exactly one). Restored after."""
    from src.db.schema import ModelVersion
    from src.walters.training import _family_for
    fam = _family_for(Sport.SOCCER)
    with session_scope() as s:
        aside = [m.id for m in s.execute(select(ModelVersion).where(
            ModelVersion.sport == Sport.SOCCER, ModelVersion.model_family == fam,
            ModelVersion.status == "production")).scalars()]
        for i in aside:
            s.get(ModelVersion, i).status = "zz-aside-453"
        mv = ModelVersion(sport=Sport.SOCCER, model_family=fam, version=version, status="production",
                          parameters={"poisson": {"dixon_coles_rho": rho, "elo_goal_coeff": coeff}})
        s.add(mv)
        s.flush()
        mid = mv.id
    try:
        yield mid
    finally:
        with session_scope() as s:
            m = s.get(ModelVersion, mid)
            if m is not None:
                s.delete(m)
            for i in aside:
                s.get(ModelVersion, i).status = "production"


def _write_copy(copy: Path, *sql):
    """Statements run on the COPY only (rollback-journal mode first, so no sidecar is left); the app's store is never
    written."""
    import sqlite3
    con = sqlite3.connect(str(copy))
    try:
        con.execute("PRAGMA journal_mode=DELETE")
        for q in sql:
            con.execute(q)
        con.commit()
    finally:
        con.close()
    assert not any(copy.with_name(copy.name + x).exists() for x in us.COPY_SIDECARS)


def test_453_the_production_note_is_read_from_the_copy_not_the_app_store(world, monkeypatch, tmp_path):
    """The NOTE line under --db names the COPY's production soccer model: the copy holds vCOPY; after the copy is taken
    the app's store holds vAPP instead. The --db console names vCOPY and never vAPP; the app's console the reverse."""
    from src.db.schema import ModelVersion
    _registry(world, monkeypatch, tmp_path / "reg", frozen=True)
    with _prod_soccer("vCOPY", -0.05, 0.0007) as mid:
        copy = _copy(tmp_path)
        with session_scope() as s:
            s.get(ModelVersion, mid).status = "zz-aside-453"
        with _prod_soccer("vAPP", -0.02, 0.0006):
            out = _cli("--db", str(copy))
            app = _cli()
    assert out.exit_code == 0 and app.exit_code == 0, out.output
    note = "  NOTE: the current production soccer model is {} (rho {}, elo_goal_coeff {}), not the run record's"
    assert note.format("vCOPY", -0.05, 0.0007) in out.output and "vAPP" not in out.output
    assert note.format("vAPP", -0.02, 0.0006) in app.output and "vCOPY" not in app.output


def test_453_a_copy_whose_model_versions_cannot_be_read_is_refused_never_a_silent_note(world, monkeypatch, tmp_path):
    """Review P2 (the NOTE's read on the copy): a copy whose model_versions passes the fence's probe but lacks a column
    the ORM selects (a copy from an older or other schema) is REFUSED (exit 2, "the copy could not be read"), nothing
    recorded; never exit 0 with the NOTE line silently gone (law 4). The good copy of the same store prints the NOTE.
    Without --db, a store with no production soccer model still prints no NOTE (unchanged)."""
    r = _registry(world, monkeypatch, tmp_path / "reg", frozen=True)
    before = _files(r["dir"])
    with _prod_soccer("vREV", -0.05, 0.0007):
        good = _copy(tmp_path, "good.db")
        bad = _copy(tmp_path, "bad.db")
    _write_copy(bad, "ALTER TABLE model_versions RENAME COLUMN model_family TO model_family_old")
    out = _cli("--db", str(good))
    assert out.exit_code == 0 and "NOTE: the current production soccer model is vREV" in out.output, out.output
    for flags in ((), ("--record", "--ruling", "ARCHITECT: x")):
        out = _cli(*flags, "--db", str(bad))
        assert out.exit_code == 2, (flags, out.output)
        head, rest = out.output.split("\n", 1)
        assert head == _head(bad)
        assert rest.startswith(f"REFUSED: --db {bad.resolve()}: the copy could not be read (OperationalError(")
        assert "model_family" in rest and "nothing recorded" in rest
        assert "SOCCER-EXPANSION-V1" not in out.output and "RECORDED" not in out.output
    assert _files(r["dir"]) == before
    with _prod_soccer("vNONE", -0.05, 0.0007) as mid:                   # no production row on a copy: None, no NOTE
        from src.db.schema import ModelVersion
        with session_scope() as s:
            s.get(ModelVersion, mid).status = "candidate"
        none = _copy(tmp_path, "none.db")
    out = _cli("--db", str(none))
    assert out.exit_code == 0 and "NOTE" not in out.output, out.output


def test_453_the_whole_read_runs_on_the_copy_the_app_store_unreadable(world, monkeypatch, tmp_path):
    """Review P2: every read of the no-flag read, --record and --substitute goes through the copy's session (the cohort,
    the eligible set, the naives, the C2 census, the stale orphans, the walk and the NOTE), not only the walk: with
    every app-store session (session_scope, readonly_scope) raising, the --db runs succeed and equal the runs through
    the app's store taken before the patch."""
    import contextlib

    import cli
    import src.db.database as dbm
    import src.walters.soccer_backtest as sb
    import src.walters.training as tr
    a = _registry(world, monkeypatch, tmp_path / "A", frozen=True)
    b_dir = tmp_path / "B"
    b_dir.mkdir()
    for rel, data in _files(a["dir"]).items():
        (b_dir / rel).parent.mkdir(parents=True, exist_ok=True)
        (b_dir / rel).write_bytes(data)
    with _prod_soccer("vRO", -0.05, 0.0007), _shape_453(world) as sh:
        copy = _copy(tmp_path)
        plain_read = _cli()
        plain_sub = _cli("--substitute")
        assert plain_sub.exit_code == 0 and f"SUBSTITUTED: {sh['released']} (ABD" in plain_sub.output
        _use(monkeypatch, b_dir)

        @contextlib.contextmanager
        def app_store(*a, **k):
            raise AssertionError("the app's store was opened under --db")
            yield  # pragma: no cover
        for mod in (dbm, cli, sb, tr):
            for name in ("session_scope", "readonly_scope"):
                if hasattr(mod, name):
                    monkeypatch.setattr(mod, name, app_store)
        read = _cli("--db", str(copy))
        sub = _cli("--substitute", "--db", str(copy))
    assert read.exit_code == 0, read.output
    assert read.output.split("\n", 1)[1] == plain_read.output
    assert "NOTE: the current production soccer model is vRO" in read.output
    assert sub.exit_code == 0, sub.output
    assert sub.output.splitlines()[2:] == plain_sub.output.splitlines()
    rec = _cli("--record", "--ruling", "ARCHITECT: x", "--db", str(copy))     # still patched: the record's read too
    assert rec.exit_code == 2 and "lack a label" in rec.output and "AssertionError" not in rec.output, rec.output


# ---------------------------------------------- #940's four rules, mirrored on this command (review P2) --

def test_453_940_a_copy_name_too_long_for_its_sidecar_names_refuses_never_a_traceback(world, monkeypatch, tmp_path):
    """#940 item 1's twin: a copy name of 248 to 255 bytes makes "<name>-journal" too long (ENAMETOOLONG on the sidecar
    probe): REFUSED (exit 2) with the shorter-name advice, nothing read, nothing written, for every served flag."""
    r = _registry(world, monkeypatch, tmp_path / "reg", frozen=True)
    before = _files(r["dir"])
    short = _copy(tmp_path, "short.db")
    copy = tmp_path / ("x" * 250 + ".db")
    os.rename(short, copy)
    for flags in ((), ("--record", "--ruling", "ARCHITECT: x"), ("--substitute",)):
        out = _cli(*flags, "--db", str(copy))
        assert out.exit_code == 2 and out.output.startswith("REFUSED: "), (flags, out.output)
        assert "a sidecar beside it cannot be checked" in out.output
        assert "take the copy under a shorter name" in out.output and "nothing read, nothing written" in out.output
        assert "SOCCER-EXPANSION-V1" not in out.output and "sha256" not in out.output
    assert _files(r["dir"]) == before


def test_453_940_a_registry_read_error_during_the_read_is_not_blamed_on_the_copy(world, monkeypatch, tmp_path):
    """#940 item 2's twin: an OSError the read raises itself (a registry read) surfaces as without --db, never as
    "the copy could not be re-read" and never REFUSED; for the read (--record) and for --substitute."""
    r = _registry(world, monkeypatch, tmp_path / "reg", frozen=True)
    before = _files(r["dir"])
    copy = _copy(tmp_path)

    def registry_fault(*a, **k):
        raise PermissionError(13, "Permission denied", "docs/registry/experiments.json")
    monkeypatch.setattr(sx, "confirmation_read", registry_fault)
    monkeypatch.setattr(sx, "substitutions_due", registry_fault)
    for flags in (("--record", "--ruling", "ARCHITECT: x"), ("--substitute",)):
        for db in ([], ["--db", str(copy)]):
            out = _cli(*flags, *db)
            assert isinstance(out.exception, PermissionError), (flags, db, out.output)
            assert "could not be re-read" not in out.output and "REFUSED" not in out.output
    assert _files(r["dir"]) == before


def _sidecar_stat_fault(monkeypatch, when):
    """us.os.stat raising EACCES on the copy's -wal probe once `when()` is true (tests/test_intl_shadow.py's helper):
    only copy_sidecars uses os in intl_shadow, so mlb_pitchers_gate.check_db is untouched."""
    import types

    def stat(path, *a, **k):
        if str(path).endswith("-wal") and when():
            raise PermissionError(13, "Permission denied", str(path))
        return os.stat(path, *a, **k)
    monkeypatch.setattr(us, "os", types.SimpleNamespace(stat=stat))


def test_453_940_a_sidecar_that_cannot_be_checked_before_the_read_refuses_without_the_shorter_name_advice(
        world, monkeypatch, tmp_path):
    """#940 item 1 (pre-push review)'s twin: another OSError on the sidecar probe before the read REFUSES (exit 2,
    nothing read, nothing written) without the shorter-name advice."""
    r = _registry(world, monkeypatch, tmp_path / "reg", frozen=True)
    before = _files(r["dir"])
    copy = _copy(tmp_path)
    reads = []
    monkeypatch.setattr(sx, "confirming", lambda: reads.append(1))
    _sidecar_stat_fault(monkeypatch, lambda: True)
    for flags in ((), ("--record", "--ruling", "ARCHITECT: x"), ("--substitute",)):
        out = _cli(*flags, "--db", str(copy))
        assert out.exit_code == 2 and out.output.startswith("REFUSED: "), (flags, out.output)
        assert "a sidecar beside it cannot be checked" in out.output
        assert "PermissionError" in out.output and "nothing read, nothing written" in out.output
        assert "shorter name" not in out.output
    assert reads == [] and _files(r["dir"]) == before


def test_453_940_a_sidecar_that_cannot_be_checked_after_the_read_refuses_and_writes_nothing(
        world, monkeypatch, tmp_path):
    """#940 item 2 (pre-push review)'s twin: the sidecar probe failing AFTER the read: "the copy could not be re-read
    after the read" with "nothing recorded" (--record) or "nothing substituted" (--substitute, a release due), exit 2,
    never "nothing read" or the shorter-name advice; no PICK line, the registry unchanged."""
    r = _registry(world, monkeypatch, tmp_path / "reg", frozen=True)
    before = _files(r["dir"])
    read0, due0, done = sx.confirmation_read, sx.substitutions_due, []

    def read(s=None):
        out = read0(s=s)
        done.append("read")
        return out

    def due(e, s, surv):
        out = due0(e, s, surv)
        done.append("due")
        return out
    monkeypatch.setattr(sx, "confirmation_read", read)
    monkeypatch.setattr(sx, "substitutions_due", due)
    _sidecar_stat_fault(monkeypatch, lambda: bool(done))
    with _shape_453(world):
        for flags, kind, nothing in ((("--record", "--ruling", "ARCHITECT: x"), "read", "nothing recorded"),
                                     (("--substitute",), "due", "nothing substituted")):
            done.clear()
            copy = _copy(tmp_path, f"after-{kind}.db")
            out = _cli(*flags, "--db", str(copy))
            assert out.exit_code == 2 and done == [kind], (flags, out.output)
            assert "the copy could not be re-read after the read" in out.output and "PermissionError" in out.output
            assert nothing in out.output and "nothing read" not in out.output and "shorter name" not in out.output
            assert "PICK" not in out.output and "RECORDED" not in out.output and "SUBSTITUTED" not in out.output
    assert _files(r["dir"]) == before


# ------------------------------------------------- --substitute --db: F3 and WAITING (review P2) --

def test_453_substitute_on_a_copy_refuses_an_unplaced_label_before_the_replacement(world, monkeypatch, tmp_path):
    """F3 on the copy: a row the code cannot place (an unknown stage label, written into the COPY only) kicking off
    before the replacement's kickoff refuses the substitution (exit 2): no PICK line, nothing written. The app's store
    holds no such row, so the refusal is the copy's own read."""
    r = _registry(world, monkeypatch, tmp_path / "reg", frozen=True)
    before = _files(r["dir"])
    with _shape_453(world) as sh:
        copy = _copy(tmp_path)
        odd = sh["passed"][1]
        with session_scope() as s:
            m = s.get(Match, odd)
            when, code = m.utc_date, m.competition.code
        _write_copy(copy, f"UPDATE matches SET stage = 'Mystery Round' WHERE id = {odd}")
        out = _cli("--substitute", "--db", str(copy))
    assert out.exit_code == 2, out.output
    head, rest = out.output.split("\n", 1)
    assert head == _head(copy)
    assert rest == ("REFUSED: stage / round labels the code cannot place, or fixtures with no season, at or before a "
                    "replacement's kickoff (F3; never guessed, never skipped): "
                    f"{code} {odd} 'Mystery Round' {when:%Y-%m-%dT%H:%MZ}\n")
    assert _files(r["dir"]) == before


def test_453_substitute_on_a_copy_with_no_replacement_stored_prints_waiting_and_writes_nothing(
        world, monkeypatch, tmp_path):
    """A release due with no eligible fixture stored after the cohort: the PICK line reads "none stored yet (WAITING)"
    with the (kickoff, id) it was measured from, then the WAITING line; nothing is written."""
    r = _registry(world, monkeypatch, tmp_path / "reg", frozen=True)
    before = _files(r["dir"])
    ids = world["ids"]
    rel, last = ids[3], ids[59]
    with session_scope() as s:
        old = {i: (lambda m: (m.status, m.status_raw, m.home_score, m.away_score, m.utc_date))(s.get(Match, i))
               for i in (rel, last)}
        moved = max(s.get(Match, i).utc_date for i in ids) + timedelta(days=1)
        m = s.get(Match, rel)
        m.status, m.status_raw, m.home_score, m.away_score = MatchStatus.CANCELLED, "ABD", None, None
        m = s.get(Match, last)
        m.status, m.status_raw, m.home_score, m.away_score, m.utc_date = (MatchStatus.SCHEDULED, "NS", None, None,
                                                                           moved)
        kick, code = s.get(Match, rel).utc_date, s.get(Match, rel).competition.code
    try:
        copy = _copy(tmp_path)
    finally:
        with session_scope() as s:
            for i, (st, raw, hs, as_, when) in old.items():
                m = s.get(Match, i)
                m.status, m.status_raw, m.home_score, m.away_score, m.utc_date = st, raw, hs, as_, when
    out = _cli("--substitute", "--db", str(copy))
    assert out.exit_code == 0, out.output
    assert out.output.splitlines() == [
        _head(copy),
        f"  PICK (the rule as built, 453 item 2(b); nothing written yet): release {rel} (raw ABD, cancelled, reason "
        f"ABD, {code} {_iso(kick)}) -> none stored yet (WAITING), the first eligible fixture after the latest "
        f"(kickoff, id) in or ever in the cohort, ({_iso(moved)}, {last})",
        f"  WAITING: {rel} (ABD) — no eligible fixture after the cohort is stored yet; sync the schedule",
        "  commit docs/registry/ in a PR"]
    assert _files(r["dir"]) == before
