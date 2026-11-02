"""#794 (ARCHITECT 2026-11-02 15:55 ET, addendum 221 item 1, RULED): ncaa-gate's reserve() writes the reservation
whole or not at all, the shape #784 got for nfl-v2-gate. A harness fix, not a criterion: the bar, the stream and the
reservation's semantics (path, contents, exclusive create, when it is written, what refuses) are unchanged.

Pins, for BOTH declarations the gate serves (ncaa-elo-v1r, ncaa-elo-v2): a body that cannot be serialised creates no
file; a partial write, a failed write, fsync, close or directory fsync each leave no file and refuse ("nothing scored,
the read is not spent"), and a later reserve writes the whole file; a failed removal refuses with INSPECT THE FILE; a
KeyboardInterrupt is cleaned up and re-raised; the bytes written on success equal the pre-fix implementation's (copied
below as the reference); a CLI run (`ncaa-gate --id ...`) whose reservation write fails exits 2 with nothing recorded,
then succeeds; and `ncaa-gate --preflight`'s output is BYTE-IDENTICAL to the pre-fix module's (PRE_FIX_PREFLIGHT,
captured from origin/main 212398ea's src/walters/ncaa_v1r_gate.py on these synthetic streams).

Synthetic data only: the registry is a tmp copy, the reservations go to tmp, no test reads data/."""
import errno
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner

from src.walters import ncaa_backtest as nb
from src.walters import ncaa_v1r_gate as vg
from src.walters import registry as reg

ROOT = Path(__file__).resolve().parent.parent
AT = datetime(2026, 10, 16, 12)
WORD = "Run it. ARCHITECT 2026-11-09 — the one run"
SPECS = (vg.V1R, vg.V2)
IDS = [s_.eid for s_ in SPECS]


def G(mid, h, a, season, at, hs, as_, neutral=False, st="regular", week=None):
    return nb.Game(h, a, season, at, hs, as_, "FBS (Division I-A)", neutral=neutral, label_source="cfbd",
                   orientation="same", match_id=mid, season_type=st, cfbd_id=mid + 10_000, cfbd_season=season,
                   label_fetched_at=AT, week=week)


def main_games():
    """2024 and 2025: 10 'regular' non-neutral games each, 6 home wins; 2025 also 520 'regular' games (v1r's test set);
    2026: 520 'regular' games (v2's test set); one neutral and one postseason game."""
    games, mid = [], 0
    for season, t, n in (("2024", datetime(2024, 9, 1), 10), ("2025", datetime(2025, 9, 1), 530),
                         ("2026", datetime(2026, 9, 1), 520)):
        for i in range(n):
            mid += 1
            win = (i < 6) if i < 10 else (mid % 2 == 0)
            games.append(G(mid, 1 + i % 4, 1 + (i + 1) % 4, season, t + timedelta(hours=mid), 21 if win else 7, 14,
                           neutral=(i == 11)))
    mid += 1
    games.append(G(mid, 2, 1, "2025", datetime(2026, 1, 5), 30, 20, st="postseason"))
    return games


def second_games():
    """2023: 40 'regular' games in weeks 1-4 (30 home wins), 520 from week 5, one postseason game."""
    games, mid, t = [], 50_000, datetime(2023, 8, 26)
    for i in range(40):
        mid += 1
        games.append(G(mid, 1 + i % 4, 1 + (i + 1) % 4, "2023", t + timedelta(hours=i), 21 if i < 30 else 7, 14,
                       week=1 + i % 4))
    for i in range(520):
        mid += 1
        games.append(G(mid, 1 + i % 4, 1 + (i + 3) % 4, "2023", t + timedelta(days=30, hours=i),
                       24 if mid % 3 else 6, 13, week=5 + i // 60))
    games.append(G(mid + 1, 2, 1, "2023", datetime(2024, 1, 1), 31, 30, st="postseason", week=1))
    return games


def _v(games, seasons):
    return nb.v1r_stream(games, {}, {s_: AT for s_ in ("2023", "2024", "2025", "2026")}, seasons)


def _cov(s=None, seasons=("2023", "2024", "2025", "2026")):
    from src.ingestion import ncaa_cfbd as nc
    return {s_: {"season": s_, "payload": f"p{s_}", "reason": None, "unlabelled": [], "fetched_at": AT,
                 "current": 100, **nc.fbs_coverage(100, 100)} for s_ in seasons}


def _fp(spec):
    if spec.second is None:
        return vg.stream_fingerprint(_v(main_games(), spec.seasons).games)[0]
    return vg.stream_fingerprint(_v(main_games(), spec.seasons).games, spec,
                                 _v(second_games(), spec.second_seasons).games)[0]


def world(monkeypatch, tmp_path, mod=vg):
    """A tmp copy of the real registry with both NCAA entries declared and unrun (v2's s frozen at 300.0, its fit
    naming today's synthetic training stream), the reservations in tmp, the streams and the coverage synthetic. The
    loaders are patched where both the module under test and the pre-fix reference read them (ncaa_backtest,
    ncaa_cfbd), so the two see the same world."""
    from src.ingestion import ncaa_cfbd as nc
    p = tmp_path / "experiments.json"
    entries = json.loads((ROOT / "docs" / "registry" / "experiments.json").read_text())
    for e in entries:
        if e["id"] in IDS:
            e.update({"status": "declared", "run": None, "verdict": None})
        if e["id"] == vg.V2.eid:
            tfp = vg.training_fingerprint(_v(main_games(), vg.V2.seasons).games, vg.V2)[0]
            e[vg.SCALE_KEY] = {"s": 300.0, "fit": {"training_fingerprint": tfp}}
    p.write_text(json.dumps(entries, indent=2))
    monkeypatch.setattr(reg, "LEDGER", str(p))
    monkeypatch.setattr(reg, "IDS_DIR", str(tmp_path / "ids"))
    monkeypatch.setattr(mod, "RESERVATION", None)
    monkeypatch.setattr(mod, "RESERVATION_DIR", str(tmp_path))
    monkeypatch.setattr(reg, "cross_ref_guard", lambda eid, no_fetch=False, repo=None: f"guard {eid}: stub")
    monkeypatch.setattr(nc, "stored_coverage", lambda s, seasons: _cov(s, tuple(seasons)))
    monkeypatch.setattr(nb, "load_v1r_stream", lambda *a, **k: _v(main_games(), vg.V1R.seasons))
    monkeypatch.setattr(nb, "load_v1r_streams", lambda pairs: (_v(main_games(), pairs[0]),
                                                               _v(second_games(), pairs[1])))
    return p


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    return world(monkeypatch, tmp_path)


# ------------------------------------------------------------------- the pre-fix reserve(), verbatim (the reference) --

def old_reserve(meta: dict | None = None, no_fetch: bool = False, echo=None, spec=vg.V1R) -> str:
    """origin/main 212398ea's reserve(), copied whole (module names qualified): the bytes the fix must reproduce."""
    p = vg.reservation_path(spec)
    if os.path.exists(p):
        raise vg.GateRefused(vg._reserved_why(p, spec.eid))
    try:
        receipt = reg.cross_ref_guard(spec.eid, no_fetch=no_fetch)
    except reg.RegistryError as e:
        raise vg.GateRefused(str(e))
    if echo:
        echo(receipt)
    try:
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise vg.GateRefused(vg._reserved_why(p, spec.eid))
    with os.fdopen(fd, "w") as f:
        json.dump({"id": spec.eid, "started_at": vg._iso(vg.utc_now_naive()), "guard": receipt, **(meta or {})}, f)
        f.write("\n")
    return p


@pytest.mark.parametrize("eid", IDS)
def test_the_bytes_written_on_success_equal_the_pre_fix_implementations(ledger, monkeypatch, tmp_path, eid):
    spec = vg.spec_of(eid)
    monkeypatch.setattr(vg, "utc_now_naive", lambda: datetime(2026, 11, 9, 16, 18, 32))   # both read it
    meta = {"architect_word": WORD, "stream_fingerprint": "ab" * 32, "stream_games": 1061, "scored_set_n": 520,
            "coverage": {"2024": 1.0, "2025": 0.987654321, "2026": None}, "logistic_scale": 279.14222651259433,
            "second_read": {"covered": True, "coverage": {"2023": 1.0}, "scored_set_n": 520,
                            "baseline_defined": False}, "note": "naïve 1e-7 → \t tab \"quoted\" \\ back"}
    new_dir, old_dir = tmp_path / "new", tmp_path / "old"
    new_dir.mkdir()
    old_dir.mkdir()
    monkeypatch.setattr(vg, "RESERVATION_DIR", str(new_dir))
    p_new = vg.reserve(meta, no_fetch=True, spec=spec)
    monkeypatch.setattr(vg, "RESERVATION_DIR", str(old_dir))
    p_old = old_reserve(meta, no_fetch=True, spec=spec)
    assert Path(p_new).name == Path(p_old).name == f"{eid}.started.json"
    new, old = Path(p_new).read_bytes(), Path(p_old).read_bytes()
    assert new == old, (new, old)
    assert new.endswith(b"}\n") and new.isascii()
    assert json.loads(new)["started_at"] == "2026-11-09T16:18:32Z" and json.loads(new)["note"] == meta["note"]
    for empty in (None, {}):                                   # no meta at all: the same bytes too
        os.remove(p_new)
        os.remove(p_old)
        monkeypatch.setattr(vg, "RESERVATION_DIR", str(new_dir))
        vg.reserve(empty, no_fetch=True, spec=spec)
        monkeypatch.setattr(vg, "RESERVATION_DIR", str(old_dir))
        old_reserve(empty, no_fetch=True, spec=spec)
        assert Path(p_new).read_bytes() == Path(p_old).read_bytes()


# ------------------------------------------------------------------------- whole or absent (the #784 fault cases) --

@pytest.mark.parametrize("eid", IDS)
def test_a_reservation_that_cannot_be_serialised_creates_nothing(ledger, monkeypatch, eid):
    spec = vg.spec_of(eid)
    opened = []
    real_open = os.open
    monkeypatch.setattr(vg.os, "open", lambda *a, **k: opened.append(a[0]) or real_open(*a, **k))
    with pytest.raises(vg.GateRefused, match=f"{eid}: the reservation could not be serialised \\(TypeError.*nothing "
                                             "written, nothing scored, the read is not spent"):
        vg.reserve({"architect_word": WORD, "bad": object()}, no_fetch=True, spec=spec)
    assert not opened and not os.path.exists(vg.reservation_path(spec))
    p = vg.reserve({"architect_word": WORD}, no_fetch=True, spec=spec)          # nothing spent: a later one is whole
    assert json.loads(Path(p).read_text())["architect_word"] == WORD


@pytest.mark.parametrize("eid", IDS)
@pytest.mark.parametrize("fault", ["partial write", "write", "fsync", "close", "directory fsync"])
def test_a_reservation_write_failure_leaves_no_file_and_a_later_reserve_succeeds(ledger, monkeypatch, fault, eid):
    spec = vg.spec_of(eid)
    real_write, real_close, real_fsync = os.write, os.close, os.fsync
    calls, closed, synced = [], [], []

    def bad_write(fd, data):
        calls.append(1)
        if fault == "partial write" and len(calls) == 1:
            return real_write(fd, bytes(data[:10]))           # some bytes land, then the disk fills
        raise OSError(errno.ENOSPC, "No space left on device")

    def bad(*a, **k):
        raise OSError(errno.EIO, "Input/output error")

    def bad_close(fd):                                        # Linux: the fd is released even when close fails
        real_close(fd)
        if not closed:
            closed.append(fd)
            raise OSError(errno.EIO, "Input/output error")

    def dir_bad(fd):                                          # the file's fsync passes; the directory's fails
        synced.append(fd)
        if len(synced) == 2:
            raise OSError(errno.EIO, "Input/output error")
        return real_fsync(fd)
    with monkeypatch.context() as m:
        m.setattr(vg.os, *{"partial write": ("write", bad_write), "write": ("write", bad_write),
                           "fsync": ("fsync", bad), "directory fsync": ("fsync", dir_bad),
                           "close": ("close", bad_close)}[fault])
        with pytest.raises(vg.GateRefused) as ei:
            vg.reserve({"architect_word": WORD}, no_fetch=True, spec=spec)
    msg = str(ei.value)
    assert msg.startswith(f"{eid}: the reservation ") and "could not be written (OSError" in msg
    if fault == "fsync":                                      # every fsync fails: the removal's directory fsync too
        assert "removed, but the removal could not be made durable (OSError" in msg, msg
        assert msg.endswith("is absent before the run: nothing scored"), msg      # never "the read is not spent"
    else:
        assert msg.endswith("removed: nothing scored, the read is not spent"), msg
    assert not os.path.exists(vg.reservation_path(spec))
    if fault == "partial write":
        assert len(calls) == 2                                # the loop asked for the rest
    if fault == "directory fsync":
        assert len(synced) == 3                               # the file, its directory (fails), the removal's directory
    # nothing spent: the gate's own checks pass again, and the one reservation is written whole
    vg.declared_unrun(spec)
    p = vg.reserve({"architect_word": WORD}, no_fetch=True, spec=spec)
    saved = json.loads(Path(p).read_text())
    assert saved["id"] == eid and saved["architect_word"] == WORD and saved["guard"] == f"guard {eid}: stub"
    assert Path(p).read_text().endswith("}\n")


def test_a_short_write_is_completed_by_the_loop(ledger, monkeypatch):
    """os.write may write less than asked without failing: the loop writes the rest, and the file is whole."""
    real_write = os.write
    monkeypatch.setattr(vg.os, "write", lambda fd, data: real_write(fd, bytes(data[:7])))
    p = vg.reserve({"architect_word": WORD}, no_fetch=True, spec=vg.V2)
    assert json.loads(Path(p).read_text())["architect_word"] == WORD


def test_the_reservation_fsyncs_its_directory_after_the_file(ledger, monkeypatch):
    import stat
    real_fsync, seen = os.fsync, []

    def spy(fd):
        seen.append(stat.S_ISDIR(os.fstat(fd).st_mode))
        return real_fsync(fd)
    monkeypatch.setattr(vg.os, "fsync", spy)
    p = vg.reserve({"architect_word": WORD}, no_fetch=True, spec=vg.V2)
    assert seen == [False, True]                              # the file, then its directory
    assert json.loads(Path(p).read_text())["architect_word"] == WORD


@pytest.mark.parametrize("eid", IDS)
def test_a_write_failure_whose_removal_also_fails_says_inspect_the_file(ledger, monkeypatch, eid):
    spec = vg.spec_of(eid)

    def bad(*a, **k):
        raise OSError(errno.EIO, "Input/output error")
    with monkeypatch.context() as m:
        m.setattr(vg.os, "fsync", bad)
        m.setattr(vg.os, "unlink", lambda p: (_ for _ in ()).throw(PermissionError(errno.EACCES, "denied")))
        with pytest.raises(vg.GateRefused, match=f"{eid}: .*could not be written \\(OSError.*could not be removed "
                                                 "\\(PermissionError.*INSPECT THE FILE"):
            vg.reserve({"architect_word": WORD}, no_fetch=True, spec=spec)
    assert os.path.exists(vg.reservation_path(spec))          # left for the operator to inspect, as the refusal says
    os.remove(vg.reservation_path(spec))


def test_a_keyboard_interrupt_mid_write_is_cleaned_up_and_re_raised(ledger, monkeypatch):
    def interrupt(fd, data):
        os.write(fd, data[:5])
        raise KeyboardInterrupt
    with monkeypatch.context() as m:
        m.setattr(vg, "_write_all", interrupt)
        with pytest.raises(KeyboardInterrupt):
            vg.reserve({"architect_word": WORD}, no_fetch=True, spec=vg.V2)
    assert not os.path.exists(vg.reservation_path(vg.V2))
    assert json.loads(Path(vg.reserve({}, no_fetch=True, spec=vg.V2)).read_text())["id"] == vg.V2.eid


def test_a_concurrent_reservation_is_never_removed(ledger, monkeypatch):
    """A reservation that appears between the exists check and the create (a second run racing this one) refuses at
    the exclusive create, before the guard's cleanup can reach it: the other run's file stands, byte for byte."""
    first = '{"id": "ncaa-elo-v2", "started_at": "2026-11-09T16:00:00Z"}\n'

    def race(eid, no_fetch=False, repo=None):
        Path(vg.reservation_path(vg.V2)).write_text(first)
        return "stub"
    monkeypatch.setattr(reg, "cross_ref_guard", race)
    with pytest.raises(vg.GateRefused, match="the one run, recorded or not"):
        vg.reserve({"architect_word": "second"}, no_fetch=True, spec=vg.V2)
    assert Path(vg.reservation_path(vg.V2)).read_text() == first


# ------------------------------------------------------------------------------------------------- the CLI run --

@pytest.mark.parametrize("eid", IDS)
def test_a_run_whose_reservation_cannot_be_written_records_nothing_and_a_later_run_succeeds(ledger, monkeypatch,
                                                                                           eid):
    import cli
    spec = vg.spec_of(eid)
    before = Path(ledger).read_bytes()
    real = vg.run_gate
    args = ["ncaa-gate", "--id", eid, "--architect-word", WORD, "--stream-fingerprint", _fp(spec), "--no-fetch"]

    def no(*a, **k):
        raise AssertionError("a game was scored without a whole reservation")
    with monkeypatch.context() as m:
        m.setattr(vg, "_write_all", lambda fd, data: (_ for _ in ()).throw(OSError(28, "No space left on device")))
        m.setattr(vg, "run_gate", no)
        res = CliRunner().invoke(cli.cli, args)
    assert res.exit_code == 2, res.output
    assert "REFUSED" in res.output and "could not be written (OSError" in res.output
    assert "removed: nothing scored, the read is not spent" in res.output
    assert not os.path.exists(vg.reservation_path(spec))
    assert Path(ledger).read_bytes() == before and not os.path.exists(reg.IDS_DIR)
    assert reg.get(eid, str(ledger))["run"] is None and vg.run_gate is real
    res = CliRunner().invoke(cli.cli, args)                   # the read is not spent: the one run proceeds
    assert res.exit_code == 0, res.output
    assert "recorded: " in res.output and reg.get(eid, str(ledger))["status"] == "run"
    saved = json.loads(Path(vg.reservation_path(spec)).read_text())
    assert saved["architect_word"] == WORD and saved["stream_fingerprint"] == _fp(spec)


# ------------------------------------------------------------------------------- --preflight, byte-identical --

def preflight_output(eid) -> str:
    import cli
    res = CliRunner().invoke(cli.cli, ["ncaa-gate", "--id", eid, "--preflight"])
    assert res.exit_code == 0, res.output
    return res.output


# Captured from origin/main 212398ea's src/walters/ncaa_v1r_gate.py (the pre-fix module, loaded by importlib from a
# tmp file in place of src.walters.ncaa_v1r_gate) in world() above, through `ncaa-gate --id <id> --preflight`.
PRE_FIX_PREFLIGHT = {
    'ncaa-elo-v1r': "\n".join([
        ('NCAA-ELO-V1R · PREFLIGHT (D6: scores nothing) · warm-up 2024 (update only) · test 2025 '
         "season_type exactly 'regular' (predict, then update) · no 2026 game scored"),
        ('  2024 (warm-up): stream 10 · by season_type regular 10 · neutral 0 · no neutral flag 0 '
         '(non-neutral, D1) · level scores skipped 0'),
        ('    coverage: 2024: labelled 100 / CFBD completed both-FBS 100 = 100.0% · >= 95%: YES · current '
         'labels 100 · record fetched_at 2026-10-16 12:00:00 · payload p2024'),
        ('  2025 (test (regular) + walked): stream 531 · by season_type postseason 1, regular 530 · '
         'neutral 1 · no neutral flag 0 (non-neutral, D1) · level scores skipped 0'),
        ('    coverage: 2025: labelled 100 / CFBD completed both-FBS 100 = 100.0% · >= 95%: YES · current '
         'labels 100 · record fetched_at 2026-10-16 12:00:00 · payload p2025'),
        ('  2026 (never scored by the gate): stream 520 · by season_type regular 520 · neutral 1 · no '
         'neutral flag 0 (non-neutral, D1) · level scores skipped 0'),
        ('    coverage: 2026: labelled 100 / CFBD completed both-FBS 100 = 100.0% · >= 95%: YES · current '
         'labels 100 · record fetched_at 2026-10-16 12:00:00 · payload p2026'),
        ("  D4 baseline (frozen before any test game is scored): 2024 non-neutral 'regular' home win rate "
         '0.600000 (n 10) · 0.5 at a neutral site'),
        ("  test set if run now: 530 2025 'regular' games (addendum 17 item 2: under 500 the run refuses "
         'before the reservation and records nothing)'),
        '  coverage: gate (2024, 2025) COVERED · confirmation (2024, 2025, 2026) COVERED',
        ('  not walked: stale labels 0 · current labels outside the seasons 0 · unlabelled or stale by '
         'season 0 · J2 merge groups 0'),
        'PREFLIGHT only: nothing scored, nothing reserved, nothing recorded.',
        ('STREAM FINGERPRINT 7f46ecc278860942c3c10bdd5a4d9ca57067290f57facb3b8f7839f24ae06700 (541 games: '
         'the 2024 and 2025 stream as the gate walks it; the run takes it as --stream-fingerprint)'),
    ]) + "\n",
    'ncaa-elo-v2': "\n".join([
        ('NCAA-ELO-V2 · PREFLIGHT (D6: scores nothing) · training and warm-up 2024 and 2025 (update only; '
         "the fit of s, D1) · test 2026 season_type exactly 'regular' (predict, then update) · second "
         'read 2023 (D10: a cold start, scored from week 5)'),
        ('  2024 (training + warm-up): stream 10 · by season_type regular 10 · neutral 0 · no neutral '
         'flag 0 (non-neutral, D1) · level scores skipped 0'),
        ('    coverage: 2024: labelled 100 / CFBD completed both-FBS 100 = 100.0% · >= 95%: YES · current '
         'labels 100 · record fetched_at 2026-10-16 12:00:00 · payload p2024'),
        ('  2025 (training + warm-up): stream 531 · by season_type postseason 1, regular 530 · neutral 1 '
         '· no neutral flag 0 (non-neutral, D1) · level scores skipped 0'),
        ('    coverage: 2025: labelled 100 / CFBD completed both-FBS 100 = 100.0% · >= 95%: YES · current '
         'labels 100 · record fetched_at 2026-10-16 12:00:00 · payload p2025'),
        ('  2026 (test (regular) + walked): stream 520 · by season_type regular 520 · neutral 1 · no '
         'neutral flag 0 (non-neutral, D1) · level scores skipped 0'),
        ('    coverage: 2026: labelled 100 / CFBD completed both-FBS 100 = 100.0% · >= 95%: YES · current '
         'labels 100 · record fetched_at 2026-10-16 12:00:00 · payload p2026'),
        ("  D4 baseline (frozen before any test game is scored): 2024 and 2025 non-neutral 'regular' home "
         'win rate 0.502783 (n 539) · 0.5 at a neutral site'),
        ('  logistic scale s (D1): 300.0 FROZEN · the fit read training stream '
         "866ceb5419ad6d2d19b1ddce652e6454cd8a750cc557f18d35e53cae91ada44e · today's training stream "
         '866ceb5419ad6d2d19b1ddce652e6454cd8a750cc557f18d35e53cae91ada44e (541 games): SAME'),
        ("  test set if run now: 520 2026 'regular' games (addendum 17 item 2: under 500 the run refuses "
         'before the reservation and records nothing)'),
        '  coverage: gate (2024, 2025, 2026) COVERED · confirmation (2024, 2025, 2026) COVERED',
        ('  not walked: stale labels 0 · current labels outside the seasons 0 · unlabelled or stale by '
         'season 0 · J2 merge groups 0'),
        ('  SECOND READ (D10; it can only block): 2023, a cold start (every team at the default rating), '
         "the frozen s applied; scored: 2023 'regular' games from week 5; its coverage is a precondition "
         'of the second read, not of the gate'),
        ('  2023 (second read: walked; scored from week 5): stream 561 · by season_type postseason 1, '
         'regular 560 · neutral 0 · no neutral flag 0 (non-neutral, D1) · level scores skipped 0'),
        ('    coverage: 2023: labelled 100 / CFBD completed both-FBS 100 = 100.0% · >= 95%: YES · current '
         'labels 100 · record fetched_at 2026-10-16 12:00:00 · payload p2023'),
        ("    'regular' games by CFBD week: 1 10, 2 10, 3 10, 4 10, 5 60, 6 60, 7 60, 8 60, 9 60, 10 60, "
         '11 60, 12 60, 13 40'),
        ("  D4 baseline of the second read: 2023 non-neutral 'regular' (weeks before 5) home win rate "
         '0.750000 (n 40) · 0.5 at a neutral site'),
        ("  second read if run now: 520 2023 'regular' games from week 5 (D10: under 500 the second read "
         'is INVALID and the architect rules again) · coverage (2023) COVERED'),
        'PREFLIGHT only: nothing scored, nothing reserved, nothing recorded.',
        ('STREAM FINGERPRINT 553d2b0d7451aef9e8f53f6eb048db476ebcb59b518d407306b4220739d123e8 (1622 '
         'games: the 2024-2026 stream and the 2023 second-read stream as the run walks them; the run '
         'takes it as --stream-fingerprint)'),
    ]) + "\n",
}


@pytest.mark.parametrize("eid", IDS)
def test_preflight_output_is_byte_identical_to_the_pre_fix_module(ledger, eid):
    """Addendum 221 item 1 (verbatim, in part): "`ncaa-gate --preflight`'s output stays byte-identical (a test pins
    it)." The whole console, every line, against the pre-fix module's on the same synthetic world."""
    assert preflight_output(eid) == PRE_FIX_PREFLIGHT[eid]
    assert not os.path.exists(vg.reservation_path(vg.spec_of(eid)))


# --------------------------------------------------------------------------------- review on #797 (round 1, P2s) --

@pytest.mark.parametrize("eid", IDS)
@pytest.mark.parametrize("exc", [OSError(errno.ENOSPC, "No space left on device"),
                                 PermissionError(errno.EACCES, "Permission denied"),
                                 OSError(errno.EIO, "Input/output error")])
def test_a_create_that_fails_for_another_reason_refuses_and_creates_nothing(ledger, monkeypatch, eid, exc):
    """Not only FileExistsError: ENOSPC, EACCES or EIO at the exclusive create refuse (exit 2 at the CLI), nothing
    created, the read not spent; a later reserve is whole."""
    spec = vg.spec_of(eid)

    def bad_open(*a, **k):
        raise exc
    with monkeypatch.context() as m:
        m.setattr(vg.os, "open", bad_open)
        with pytest.raises(vg.GateRefused, match=rf"{eid}: the reservation .*could not be created \({type(exc).__name__}"
                                                 ".*nothing written, nothing scored, the read is not spent"):
            vg.reserve({"architect_word": WORD}, no_fetch=True, spec=spec)
    assert not os.path.exists(vg.reservation_path(spec))
    vg.declared_unrun(spec)
    assert json.loads(Path(vg.reserve({"architect_word": WORD}, no_fetch=True, spec=spec)).read_text())["id"] == eid


def test_a_removal_is_followed_by_an_fsync_of_its_directory(ledger, monkeypatch):
    """After a failed write the removal is made durable: unlink, then the directory's fsync, in that order."""
    import stat
    events, real_unlink, real_fsync = [], os.unlink, os.fsync

    def bad_write(fd, data):
        raise OSError(errno.ENOSPC, "No space left on device")

    def spy_unlink(p):
        events.append("unlink")
        return real_unlink(p)

    def spy_fsync(fd):
        events.append("fsync dir" if stat.S_ISDIR(os.fstat(fd).st_mode) else "fsync file")
        return real_fsync(fd)
    with monkeypatch.context() as m:
        m.setattr(vg.os, "write", bad_write)
        m.setattr(vg.os, "unlink", spy_unlink)
        m.setattr(vg.os, "fsync", spy_fsync)
        with pytest.raises(vg.GateRefused, match="removed: nothing scored, the read is not spent"):
            vg.reserve({"architect_word": WORD}, no_fetch=True, spec=vg.V2)
    assert events == ["unlink", "fsync dir"]
    assert not os.path.exists(vg.reservation_path(vg.V2))


def test_the_newline_is_the_platforms_as_the_old_text_mode_wrote_it(ledger, monkeypatch):
    """The pre-fix text-mode file turned "\\n" into os.linesep (CRLF on Windows): the bytes follow os.linesep."""
    monkeypatch.setattr(vg.os, "linesep", "\r\n")
    p = vg.reserve({"architect_word": WORD}, no_fetch=True, spec=vg.V2)
    raw = Path(p).read_bytes()
    assert raw.endswith(b"}\r\n") and raw.count(b"\n") == 1
    assert json.loads(raw)["architect_word"] == WORD


# ----------------------------------------------------------------- review on #797 round 2 (addendum 222 item 1) --

@pytest.mark.parametrize("dir_sync_fails", [False, True])
def test_a_reservation_another_process_already_removed_is_made_durable_too(ledger, monkeypatch, dir_sync_fails):
    """The write fails and, before our cleanup, another process removes the file: the directory is still fsynced
    (that other unlink may not be flushed). If that fsync fails the refusal says so and never claims the read
    unspent (addendum 222 item 1: the round-two P2 rides #797)."""
    import stat
    events, real_unlink, real_fsync = [], os.unlink, os.fsync

    def bad_write(fd, data):
        real_unlink(vg.reservation_path(vg.V2))               # another process removes it mid-failure
        raise OSError(errno.ENOSPC, "No space left on device")

    def spy_unlink(p):
        events.append("unlink")
        return real_unlink(p)                                 # raises FileNotFoundError: already gone

    def spy_fsync(fd):
        is_dir = stat.S_ISDIR(os.fstat(fd).st_mode)
        events.append("fsync dir" if is_dir else "fsync file")
        if is_dir and dir_sync_fails:
            raise OSError(errno.EIO, "Input/output error")
        return real_fsync(fd)
    with monkeypatch.context() as m:
        m.setattr(vg.os, "write", bad_write)
        m.setattr(vg.os, "unlink", spy_unlink)
        m.setattr(vg.os, "fsync", spy_fsync)
        with pytest.raises(vg.GateRefused) as ei:
            vg.reserve({"architect_word": WORD}, no_fetch=True, spec=vg.V2)
    msg = str(ei.value)
    assert events == ["unlink", "fsync dir"]
    if dir_sync_fails:
        assert "already gone, but the removal could not be made durable (OSError" in msg, msg
        assert msg.endswith("is absent before the run: nothing scored"), msg
    else:
        assert msg.endswith("already gone: nothing scored, the read is not spent"), msg
    assert not os.path.exists(vg.reservation_path(vg.V2))
