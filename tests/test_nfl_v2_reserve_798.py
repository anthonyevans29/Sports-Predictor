"""#798 (ARCHITECT 2026-11-02 16:35 ET, addendum 222 item 2, RULED): nfl-v2-gate's reserve() gets the two edges #797
fixed for ncaa-gate, in #797's shape, so the two harnesses read the same. A harness fix, not a criterion: the bar,
the stream and the reservation's semantics (path, contents, exclusive create, when it is written, what refuses) are
unchanged.

Pins: a create that fails for any reason other than an existing file (ENOSPC, EACCES, EIO) refuses, nothing created,
the read not spent, and a later reserve is whole; a removal after a failed write is followed by an fsync of its
directory (unlink, then the directory); a file another process already removed gets the same fsync; a removal that
cannot be made durable is said and the refusal ends "nothing scored", never "the read is not spent"; the bytes written
on success equal the pre-fix implementation's (origin/main 212398ea's reserve(), copied below as the reference; the
newline stays "\\n": nfl-v2-gate had no earlier text-mode version to match); `nfl-v2-gate --preflight`'s output is
BYTE-IDENTICAL to the pre-fix module's (PRE_FIX_PREFLIGHT, captured from origin/main 212398ea's
src/walters/nfl_v2_gate.py on the synthetic stream of tests/nfl_v2_world.py).

Synthetic data only: every DB is a fresh SQLite file under tmp_path, the registry is a tmp copy, the reservation goes
to tmp; no test reads data/."""
import errno
import json
import os
import stat
from datetime import datetime
from pathlib import Path

import pytest
from click.testing import CliRunner

import nfl_v2_world as world
from src.walters import nfl_backtest as nb
from src.walters import nfl_v2_gate as g
from src.walters import registry as reg

ROOT = Path(__file__).resolve().parent.parent
EID = "nfl-elo-v2"
WORD = "Run it. ARCHITECT 2026-11-06"


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """A tmp copy of the real registry; every registry read/write goes there; the reservation to tmp; the #329
    guard a stub."""
    p = tmp_path / "experiments.json"
    p.write_text((ROOT / "docs" / "registry" / "experiments.json").read_text())
    monkeypatch.setattr(reg, "LEDGER", str(p))
    monkeypatch.setattr(reg, "IDS_DIR", str(tmp_path / "ids"))
    monkeypatch.setattr(g, "RESERVATION", str(tmp_path / f"{EID}.started.json"))
    monkeypatch.setattr(reg, "cross_ref_guard", lambda *a, **k: "stub")
    return p


@pytest.fixture
def db(tmp_path, monkeypatch):
    d = world.fresh(tmp_path / "nfl.db", monkeypatch)
    d.ids = world.build(d)
    return d


def _enospc(fd, data):
    raise OSError(errno.ENOSPC, "No space left on device")


def _spies(events, dir_sync_fails=False):
    real_unlink, real_fsync = os.unlink, os.fsync

    def spy_unlink(p):
        events.append("unlink")
        return real_unlink(p)

    def spy_fsync(fd):
        is_dir = stat.S_ISDIR(os.fstat(fd).st_mode)
        events.append("fsync dir" if is_dir else "fsync file")
        if is_dir and dir_sync_fails:
            raise OSError(errno.EIO, "Input/output error")
        return real_fsync(fd)
    return spy_unlink, spy_fsync


# ------------------------------------------------------------------- the pre-fix reserve(), verbatim (the reference) --

def old_reserve(meta: dict, no_fetch: bool = False, echo=None) -> str:
    """origin/main 212398ea's reserve(), copied whole (module names qualified): the bytes the fix must reproduce."""
    p = g.reservation_path()
    if os.path.exists(p):
        raise g.GateRefused(g._reserved_why(p))
    try:
        receipt = reg.cross_ref_guard(g.EID, no_fetch=no_fetch)
    except reg.RegistryError as e:
        raise g.GateRefused(str(e))
    if echo:
        echo(receipt)
    try:
        data = (json.dumps({"id": g.EID, "started_at": g._iso(g.utc_now_naive()), "guard": receipt, **meta})
                + "\n").encode("utf-8")
    except Exception as err:
        raise g.GateRefused(f"{g.EID}: the reservation could not be serialised ({type(err).__name__}: {err}); nothing "
                            "written, nothing scored, the read is not spent") from err
    try:
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise g.GateRefused(g._reserved_why(p))
    fd_open = True
    try:
        g._write_all(fd, data)
        fd_open = False
        os.close(fd)
        g._fsync_dir(p)
    except BaseException as err:
        if fd_open:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            os.unlink(p)
            removed = "removed"
        except FileNotFoundError:
            removed = "already gone"
        except OSError as uerr:
            raise g.GateRefused(f"{g.EID}: the reservation {os.path.relpath(p)} could not be written "
                                f"({type(err).__name__}: {err}) and could not be removed ({type(uerr).__name__}: "
                                f"{uerr}): INSPECT THE FILE before anything else; it may be empty or partial and reads "
                                "as a spent run while it stands. Nothing was scored") from err
        if not isinstance(err, Exception):
            raise
        raise g.GateRefused(f"{g.EID}: the reservation {os.path.relpath(p)} could not be written "
                            f"({type(err).__name__}: {err}); {removed}: nothing scored, the read is not spent") from err
    return p


def test_the_bytes_written_on_success_equal_the_pre_fix_implementations(ledger, monkeypatch, tmp_path):
    monkeypatch.setattr(g, "utc_now_naive", lambda: datetime(2026, 11, 6, 16, 18, 32))
    meta = {"architect_word": WORD, "stream_fingerprint": "ab" * 32, "warmup_fingerprint": "cd" * 32,
            "calibration_term": {"form": "shrink", "value": 0.9}, "database": "db --db /tmp/x.db (a .backup copy)",
            "note": "naïve 1e-7 → \t tab \"quoted\" \\ back"}
    new, old = tmp_path / "new.started.json", tmp_path / "old.started.json"
    monkeypatch.setattr(g, "RESERVATION", str(new))
    g.reserve(meta, no_fetch=True)
    monkeypatch.setattr(g, "RESERVATION", str(old))
    old_reserve(meta, no_fetch=True)
    assert new.read_bytes() == old.read_bytes(), (new.read_bytes(), old.read_bytes())
    raw = new.read_bytes()
    assert raw.endswith(b"}\n") and raw.count(b"\n") == 1 and b"\r" not in raw and raw.isascii()
    assert json.loads(raw)["started_at"] == "2026-11-06T16:18:32Z" and json.loads(raw)["note"] == meta["note"]
    new.unlink()
    old.unlink()
    monkeypatch.setattr(g, "RESERVATION", str(new))           # an empty meta: the same bytes too
    g.reserve({}, no_fetch=True)
    monkeypatch.setattr(g, "RESERVATION", str(old))
    old_reserve({}, no_fetch=True)
    assert new.read_bytes() == old.read_bytes()


def test_the_newline_stays_a_bare_lf_whatever_os_linesep_says(ledger, monkeypatch):
    """#797 moved ncaa-gate to os.linesep to match its old text-mode bytes; nfl-v2-gate never wrote through text mode,
    so its "\\n" stands (the task: do not change the newline)."""
    monkeypatch.setattr(g.os, "linesep", "\r\n")
    raw = Path(g.reserve({"architect_word": WORD}, no_fetch=True)).read_bytes()
    assert raw.endswith(b"}\n") and b"\r" not in raw


# ------------------------------------------------------------------------- edge 1: a create that fails otherwise --

@pytest.mark.parametrize("exc", [OSError(errno.ENOSPC, "No space left on device"),
                                 PermissionError(errno.EACCES, "Permission denied"),
                                 OSError(errno.EIO, "Input/output error")])
def test_a_create_that_fails_for_another_reason_refuses_and_creates_nothing(ledger, monkeypatch, exc):
    """Not only FileExistsError: ENOSPC, EACCES or EIO at the exclusive create refuse (exit 2 at the CLI), nothing
    created, the read not spent; a later reserve is whole."""
    def bad_open(*a, **k):
        raise exc
    with monkeypatch.context() as m:
        m.setattr(g.os, "open", bad_open)
        with pytest.raises(g.GateRefused, match=rf"{EID}: the reservation .*could not be created \({type(exc).__name__}"
                                                ".*nothing written, nothing scored, the read is not spent$"):
            g.reserve({"architect_word": WORD}, no_fetch=True)
    assert not os.path.exists(g.reservation_path())
    g.declared_unrun()
    saved = json.loads(Path(g.reserve({"architect_word": WORD}, no_fetch=True)).read_text())
    assert saved["id"] == EID and saved["architect_word"] == WORD and saved["guard"] == "stub"


def test_an_existing_file_at_the_create_still_refuses_as_the_one_run(ledger, monkeypatch):
    """The FileExistsError branch is unchanged and comes first: a racing reservation reads as the one run."""
    def exists(*a, **k):
        raise FileExistsError(errno.EEXIST, "File exists")
    monkeypatch.setattr(g.os, "open", exists)
    with pytest.raises(g.GateRefused, match="the one run, recorded or not"):
        g.reserve({"architect_word": WORD}, no_fetch=True)


# --------------------------------------------------------------------------- edge 2: the removal made durable --

def test_a_removal_is_followed_by_an_fsync_of_its_directory(ledger, monkeypatch):
    """After a failed write the removal is made durable: unlink, then the directory's fsync, in that order."""
    events = []
    spy_unlink, spy_fsync = _spies(events)
    with monkeypatch.context() as m:
        m.setattr(g.os, "write", _enospc)
        m.setattr(g.os, "unlink", spy_unlink)
        m.setattr(g.os, "fsync", spy_fsync)
        with pytest.raises(g.GateRefused) as ei:
            g.reserve({"architect_word": WORD}, no_fetch=True)
    assert events == ["unlink", "fsync dir"]
    assert str(ei.value).endswith("removed: nothing scored, the read is not spent"), str(ei.value)
    assert not os.path.exists(g.reservation_path())


def test_a_removal_whose_directory_fsync_fails_is_said_and_does_not_claim_the_read_unspent(ledger, monkeypatch):
    events = []
    spy_unlink, spy_fsync = _spies(events, dir_sync_fails=True)
    with monkeypatch.context() as m:
        m.setattr(g.os, "write", _enospc)
        m.setattr(g.os, "unlink", spy_unlink)
        m.setattr(g.os, "fsync", spy_fsync)
        with pytest.raises(g.GateRefused) as ei:
            g.reserve({"architect_word": WORD}, no_fetch=True)
    msg = str(ei.value)
    assert events == ["unlink", "fsync dir"]
    assert msg.startswith(f"{EID}: the reservation ") and "could not be written (OSError" in msg
    assert "removed, but the removal could not be made durable (OSError: [Errno 5] Input/output error)" in msg, msg
    assert f"check that {os.path.relpath(g.reservation_path())} is absent before the run" in msg, msg
    assert msg.endswith("is absent before the run: nothing scored"), msg
    assert "the read is not spent" not in msg
    assert not os.path.exists(g.reservation_path())


@pytest.mark.parametrize("dir_sync_fails", [False, True])
def test_a_reservation_another_process_already_removed_is_made_durable_too(ledger, monkeypatch, dir_sync_fails):
    """The write fails and, before our cleanup, another process removes the file: the directory is still fsynced
    (that other unlink may not be flushed). If that fsync fails the refusal says so and never claims the read
    unspent (addendum 222 item 1's already-gone branch, in #797's shape)."""
    events = []
    real_unlink = os.unlink
    spy_unlink, spy_fsync = _spies(events, dir_sync_fails=dir_sync_fails)

    def bad_write(fd, data):
        real_unlink(g.reservation_path())                     # another process removes it mid-failure
        raise OSError(errno.ENOSPC, "No space left on device")
    with monkeypatch.context() as m:
        m.setattr(g.os, "write", bad_write)
        m.setattr(g.os, "unlink", spy_unlink)                 # raises FileNotFoundError: already gone
        m.setattr(g.os, "fsync", spy_fsync)
        with pytest.raises(g.GateRefused) as ei:
            g.reserve({"architect_word": WORD}, no_fetch=True)
    msg = str(ei.value)
    assert events == ["unlink", "fsync dir"]
    if dir_sync_fails:
        assert "already gone, but the removal could not be made durable (OSError" in msg, msg
        assert msg.endswith("is absent before the run: nothing scored"), msg
        assert "the read is not spent" not in msg
    else:
        assert msg.endswith("already gone: nothing scored, the read is not spent"), msg
    assert not os.path.exists(g.reservation_path())
    p = g.reserve({"architect_word": WORD}, no_fetch=True)   # a later reserve is whole
    assert json.loads(Path(p).read_text())["architect_word"] == WORD


def test_every_fsync_failing_ends_nothing_scored(ledger, monkeypatch):
    """The file's fsync fails, then the removal's directory fsync fails too: the refusal says the removal could not
    be made durable and ends "nothing scored"; a later reserve is whole."""
    seen = []

    def bad(fd):
        seen.append(stat.S_ISDIR(os.fstat(fd).st_mode))
        raise OSError(errno.EIO, "Input/output error")
    with monkeypatch.context() as m:
        m.setattr(g.os, "fsync", bad)
        with pytest.raises(g.GateRefused) as ei:
            g.reserve({"architect_word": WORD}, no_fetch=True)
    msg = str(ei.value)
    assert seen == [False, True]                              # the file's fsync, then the removal's directory
    assert "could not be written (OSError" in msg and "removed, but the removal could not be made durable" in msg
    assert msg.endswith("is absent before the run: nothing scored"), msg
    assert not os.path.exists(g.reservation_path())
    p = g.reserve({"architect_word": WORD}, no_fetch=True)
    assert json.loads(Path(p).read_text())["architect_word"] == WORD


def test_a_keyboard_interrupt_mid_write_is_cleaned_up_durably_and_re_raised(ledger, monkeypatch):
    events = []
    spy_unlink, spy_fsync = _spies(events)

    def interrupt(fd, data):
        os.write(fd, data[:5])
        raise KeyboardInterrupt
    with monkeypatch.context() as m:
        m.setattr(g, "_write_all", interrupt)
        m.setattr(g.os, "unlink", spy_unlink)
        m.setattr(g.os, "fsync", spy_fsync)
        with pytest.raises(KeyboardInterrupt):
            g.reserve({"architect_word": WORD}, no_fetch=True)
    assert events == ["unlink", "fsync dir"]
    assert not os.path.exists(g.reservation_path())


# ------------------------------------------------------------------------------- --preflight, byte-identical --

AUTO = object()


def _declare(ledger, shrink=None, home_advantage=None, fit=AUTO):
    if fit is AUTO:
        fit = {"method": "test", "warmup_fingerprint": g.warmup_fingerprint(nb.split(nb.load_stream())[0])[0]}
    entries = json.loads(Path(ledger).read_text())
    e = next(x for x in entries if x["id"] == EID)
    e["calibration_term"].update({"shrink": shrink, "home_advantage": home_advantage, "fit": fit})
    Path(ledger).write_text(json.dumps(entries, indent=2) + "\n")


CASES = {"undeclared": {}, "shrink 0.9, bound fit": {"shrink": 0.9},
         "home advantage 40.0, stale fit": {"home_advantage": 40.0, "fit": {"warmup_fingerprint": "e" * 64}}}


def preflight_output(ledger, case) -> str:
    import cli
    if CASES[case]:
        _declare(ledger, **CASES[case])
    else:                                       # the undeclared term (the real entry's before addendum 245)
        _declare(ledger, fit=None)
    res = CliRunner().invoke(cli.cli, ["nfl-v2-gate", "--preflight"])
    assert res.exit_code == 0, res.output
    return res.output


# Captured from origin/main 212398ea's src/walters/nfl_v2_gate.py (before this PR's edit) through
# `nfl-v2-gate --preflight` on the synthetic stream above (tests/nfl_v2_world.py), the tmp ledger declared per case.
PRE_FIX_PREFLIGHT = {
    'undeclared': "\n".join([
        ('NFL-ELO-V2 · PREFLIGHT (scores nothing) · warm-up 2024 complete (update only) · scored 2025 regular '
         '+ post (predict, then update) · preseason excluded · ARCHITECT 2026-11-02 10:35 ET, addendum 215 '
         'items 2-3'),
        ("  scope[nfl-v2-gate]: teams=32, games=603, competitions={NFL} · db DATABASE_URL (the app's "
         'configured database)'),
        ('  warm-up 2024: 301 games (addendum 215 item 2 names 285: DIFFERS by +16 — the architect reads this '
         'line) · by stage Post Season 13, Regular Season 288'),
        ('  scored 2025: 301 games (addendum 215 item 2 names 285: DIFFERS by +16 — the architect reads this '
         'line) · by stage Post Season 13, Regular Season 288 (counts only: no 2025 outcome is read)'),
        '  preseason excluded: 2024 4, 2025 4 · other seasons, never walked: 2026 1',
        "  baseline (the frozen protocol: the warm-up's realized home rate): 0.564784 (301 games)",
        ('  calibration term: NOT DECLARED — the run refuses: the calibration term is not declared '
         '(calibration_term.shrink and calibration_term.home_advantage are both null): the form and its '
         "2024-fitted value are ruled by the architect's declaration of 2026-11-05 (addendum 215 item 3) and "
         'written into the entry before the run'),
        ("  constants: the entry's frozen {'k_factor': 20.0, 'home_advantage': 48.0, 'season_regression': "
         "0.25, 'mov_base': 2.2, 'default_rating': 1500.0} · NFLEloConfig()'s {'k_factor': 20.0, "
         "'home_advantage': 48.0, 'season_regression': 0.25, 'mov_base': 2.2, 'default_rating': 1500.0} · "
         'SAME: the run walks the declared constants (Codex P1 on #784)'),
        ('  warm-up fingerprint 1e4023312d6e5c378612dd1f059811d29ca0ba889fbe06dd6bb1fa295967ec56 (301 games; '
         "nfl-v2-fit-warmup prints it) · the fit's, as the entry records it: — · fit NOT RECORDED "
         '(calibration_term.fit null or without warmup_fingerprint): the run refuses (addendum 219 item 4)'),
        'PREFLIGHT only: nothing scored, nothing reserved, nothing recorded.',
        ('STREAM FINGERPRINT f5cedef5b456b6ff1d7e4ed0b52a7c1776748b87d54f178fca42523b20919a0e (602 games: the '
         '2024 and 2025 stream as the gate walks it, and the calibration term NOT DECLARED: this fingerprint '
         "binds the undeclared term and the run refuses; the declaration's term changes it; v2, addendum 219 "
         'item 4; the run takes it as --stream-fingerprint)'),
    ]) + "\n",
    'shrink 0.9, bound fit': "\n".join([
        ('NFL-ELO-V2 · PREFLIGHT (scores nothing) · warm-up 2024 complete (update only) · scored 2025 regular '
         '+ post (predict, then update) · preseason excluded · ARCHITECT 2026-11-02 10:35 ET, addendum 215 '
         'items 2-3'),
        ("  scope[nfl-v2-gate]: teams=32, games=603, competitions={NFL} · db DATABASE_URL (the app's "
         'configured database)'),
        ('  warm-up 2024: 301 games (addendum 215 item 2 names 285: DIFFERS by +16 — the architect reads this '
         'line) · by stage Post Season 13, Regular Season 288'),
        ('  scored 2025: 301 games (addendum 215 item 2 names 285: DIFFERS by +16 — the architect reads this '
         'line) · by stage Post Season 13, Regular Season 288 (counts only: no 2025 outcome is read)'),
        '  preseason excluded: 2024 4, 2025 4 · other seasons, never walked: 2026 1',
        "  baseline (the frozen protocol: the warm-up's realized home rate): 0.564784 (301 games)",
        "  calibration term: shrink s = 0.9: p' = 0.5 + s·(p − 0.5), price only (ratings and updates v1's)",
        ("  constants: the entry's frozen {'k_factor': 20.0, 'home_advantage': 48.0, 'season_regression': "
         "0.25, 'mov_base': 2.2, 'default_rating': 1500.0} · NFLEloConfig()'s {'k_factor': 20.0, "
         "'home_advantage': 48.0, 'season_regression': 0.25, 'mov_base': 2.2, 'default_rating': 1500.0} · "
         'SAME: the run walks the declared constants (Codex P1 on #784)'),
        ('  warm-up fingerprint 1e4023312d6e5c378612dd1f059811d29ca0ba889fbe06dd6bb1fa295967ec56 (301 games; '
         "nfl-v2-fit-warmup prints it) · the fit's, as the entry records it: "
         '1e4023312d6e5c378612dd1f059811d29ca0ba889fbe06dd6bb1fa295967ec56 · SAME: the fit is bound to these '
         '2024 rows (addendum 219 item 4)'),
        'PREFLIGHT only: nothing scored, nothing reserved, nothing recorded.',
        ('STREAM FINGERPRINT 1e8df71a18dcb1ca1e254a014922b7ff31175798d1faa71bde2295b5006b3c02 (602 games: the '
         "2024 and 2025 stream as the gate walks it, and the calibration term as declared (shrink s = 0.9: p' "
         "= 0.5 + s·(p − 0.5), price only (ratings and updates v1's)); v2, addendum 219 item 4; the run takes "
         'it as --stream-fingerprint)'),
    ]) + "\n",
    'home advantage 40.0, stale fit': "\n".join([
        ('NFL-ELO-V2 · PREFLIGHT (scores nothing) · warm-up 2024 complete (update only) · scored 2025 regular '
         '+ post (predict, then update) · preseason excluded · ARCHITECT 2026-11-02 10:35 ET, addendum 215 '
         'items 2-3'),
        ("  scope[nfl-v2-gate]: teams=32, games=603, competitions={NFL} · db DATABASE_URL (the app's "
         'configured database)'),
        ('  warm-up 2024: 301 games (addendum 215 item 2 names 285: DIFFERS by +16 — the architect reads this '
         'line) · by stage Post Season 13, Regular Season 288'),
        ('  scored 2025: 301 games (addendum 215 item 2 names 285: DIFFERS by +16 — the architect reads this '
         'line) · by stage Post Season 13, Regular Season 288 (counts only: no 2025 outcome is read)'),
        '  preseason excluded: 2024 4, 2025 4 · other seasons, never walked: 2026 1',
        "  baseline (the frozen protocol: the warm-up's realized home rate): 0.564784 (301 games)",
        '  calibration term: home advantage 40.0 Elo points (v1: 48.0), the whole walk (price and update)',
        ("  constants: the entry's frozen {'k_factor': 20.0, 'home_advantage': 48.0, 'season_regression': "
         "0.25, 'mov_base': 2.2, 'default_rating': 1500.0} · NFLEloConfig()'s {'k_factor': 20.0, "
         "'home_advantage': 48.0, 'season_regression': 0.25, 'mov_base': 2.2, 'default_rating': 1500.0} · "
         'SAME: the run walks the declared constants (Codex P1 on #784)'),
        ('  warm-up fingerprint 1e4023312d6e5c378612dd1f059811d29ca0ba889fbe06dd6bb1fa295967ec56 (301 games; '
         "nfl-v2-fit-warmup prints it) · the fit's, as the entry records it: "
         'eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee · CHANGED since the fit: the run '
         'refuses (the architect reads this line) (addendum 219 item 4)'),
        'PREFLIGHT only: nothing scored, nothing reserved, nothing recorded.',
        ('STREAM FINGERPRINT 5e846e661cde09598227c8f6ad2278c71d498e8a79c353ef7df730422cc6ce3e (602 games: the '
         '2024 and 2025 stream as the gate walks it, and the calibration term as declared (home advantage '
         '40.0 Elo points (v1: 48.0), the whole walk (price and update)); v2, addendum 219 item 4; the run '
         'takes it as --stream-fingerprint)'),
    ]) + "\n",
}


@pytest.mark.parametrize("case", list(CASES))
def test_preflight_output_is_byte_identical_to_the_pre_fix_module(db, ledger, case):
    """The whole console, every line, against the pre-fix module's on the same synthetic world; nothing reserved."""
    assert preflight_output(ledger, case) == PRE_FIX_PREFLIGHT[case]
    assert not os.path.exists(g.reservation_path())
