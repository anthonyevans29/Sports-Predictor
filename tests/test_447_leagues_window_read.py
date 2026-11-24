"""THE LEAGUES WINDOWS' ONE READ AS A COMMAND (ARCHITECT 2026-11-22 09:18 ET, addendum 447 items 1-2 and 4 PR 1;
src/walters/leagues_read.py, cli.py leagues-window-read, scripts/leagues_window.py --pages-digest).

On tests/test_leagues_window.py's synthetic SA window (a throwaway SQLite, a tmp registry: the real
docs/registry/experiments.json is never written), its .backup copy outside the checkout and outside data/, and its
pages in a folder outside the checkout. Pins:
  B2(c) the digest is sha256sum's (lines sorted by name bytewise; the sha256 of those lines), byte for byte against
        the system's sha256sum on a fixture, the script's --pages-digest prints the same with no database, and both
        print the page count and the first and last file;
  B2(b) an --exports folder inside the checkout (or a link into it) refuses; the folder is never written;
  B2(d) the read refuses until the UTC date after the 60th member's kickoff, and the preflight prints that date;
  B2(e) the run record accounts for every game the window's loop reached: the 60 members, and each game that took no
        slot with its cause, by id;
  C1    the run record writes the opening (the 60th member's kickoff and match id) before any verdict exists, in the
        window's own order (a tie on kickoff ordered by id);
  B1    the verdict is its own invocation, refused unless the run is recorded and the word equals the computed one;
  the refusals in order, nothing reserved before the fingerprint; the reservation before the score; a failure after it
  leaves the read spent, nothing recorded; one read stays one."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.db.schema import MatchStatus
from src.walters import leagues_read as lr
from src.walters import leagues_window as lw
from src.walters import registry as reg
from tests.test_leagues_window import (AT, NOW, _comps, _export, _game, _members, _priors, _teams, decl,  # noqa: F401
                                       ledger, script)
from tests.test_record_vs_close import iso_db  # noqa: F401  (a fixture: a throwaway SQLite, cwd = tmp_path)

pytestmark = pytest.mark.usefixtures("iso_db")

ROOT = Path(__file__).resolve().parent.parent
WORD = "ARCHITECT test word (tests only)"


def _entry(code="SA", **kw):
    base = {"test_set": f"{code} 2026/27 window (tests only)", "candidate": "v22 frozen (tests only)",
            "status": "declared", "run": None, "confirmation_plan": dict(lw.RULED_PLAN)}   # 448 item 2: as stored
    return decl(code, **{**base, **kw})


def _copy(tmp_path, name="copy") -> Path:
    """A .backup copy of the throwaway store, in a folder of its own outside the checkout and outside data/."""
    src = tmp_path / "iso.db"
    dst = tmp_path / name / "sports.db"
    dst.parent.mkdir(parents=True, exist_ok=True)
    a, b = sqlite3.connect(str(src)), sqlite3.connect(str(dst))
    try:
        a.backup(b)
    finally:
        b.close()
        a.close()
    return dst


@pytest.fixture
def world(ledger, tmp_path, monkeypatch):
    """A ready SA window: 40 priors, 60 members and a cancelled game kicking off among them, the pages written
    (into tmp_path/exports, then moved to a pulled folder outside the checkout), the copy taken; the registry and the
    reservation in tmp_path."""
    monkeypatch.setattr(reg, "IDS_DIR", str(tmp_path / "ids"))
    monkeypatch.setattr(lr, "RESERVATION_DIR", str(tmp_path))
    _comps()
    ledger(_entry())
    t = _teams("SA")
    _priors("SA", t)
    got = _members("SA", t, 60, 2000, AT + timedelta(hours=1))
    # reached and taking no slot: a cancelled game kicking off among the members (B2(e))
    _game(2900, "SA", AT + timedelta(hours=4), (t[2], t[3]), MatchStatus.CANCELLED)
    _export("SA")
    pulled = tmp_path / "pulled"
    shutil.copytree(tmp_path / "exports", pulled)
    copy = _copy(tmp_path)
    return {"copy": copy, "exports": pulled, "digest": lw.pages_digest(pulled)["digest"], "members": got,
            "tmp": tmp_path}


def _fp(lines):
    assert lines[-1].startswith("WINDOW FINGERPRINT "), lines[-1]
    return lines[-1].split()[2]


def _nothing(world):
    e = reg.get(lw.DECLARATION_IDS["SA"], reg.LEDGER)
    assert e["run"] is None and not e.get("verdict")
    assert not Path(lr.reservation_path(e["id"])).exists()


def _pre(world, **kw):
    a = {"code": "SA", "db": str(world["copy"]), "exports": str(world["exports"]), "pages_digest": world["digest"]}
    a.update(kw)
    return lr.preflight_lines(a["code"], a["db"], a["exports"], a["pages_digest"], now=kw.get("now", NOW))


def _run(world, fp, **kw):
    a = {"code": "SA", "db": str(world["copy"]), "exports": str(world["exports"]), "pages_digest": world["digest"],
         "word": WORD, "now": NOW}
    a.update(kw)
    return lr.run(a["code"], a["db"], a["exports"], a["pages_digest"], a["word"], fp, now=a["now"])


# ---------------------------------------------------------------------------------------------- B2(c) --

def _fixture_pages(d: Path) -> list[str]:
    d.mkdir(parents=True)
    names = ["soccer_expansion_shadow_2026-11-09_095007.json", "soccer_expansion_shadow_2026-11-06_140003.json",
             "soccer_expansion_shadow_2026-11-07_103000.json", "soccer_expansion_shadow_Zed.json",
             "soccer_expansion_shadow_alpha.json"]
    for i, n in enumerate(names):
        (d / n).write_text(json.dumps({"exported_at": f"2026-11-0{i}", "predictions": []}))
    (d / ".soccer_expansion_shadow_x.json.tmp").write_text("a dot-named leftover: never a page")
    (d / "other.json").write_text("{}")
    return names


def test_b2c_the_digest_is_sha256sums_lines_sorted_bytewise_hashed(tmp_path):
    """B2(c): one line per page, "<sha256 hex>  <name>\\n", sorted by name bytewise, the digest the sha256 of the
    lines; pinned against a hand-built blob and, where the system has it, against sha256sum itself under LC_ALL=C."""
    d = tmp_path / "pages"
    names = _fixture_pages(d)
    got = lw.pages_digest(d)
    order = sorted(names, key=os.fsencode)
    blob = b"".join(hashlib.sha256((d / n).read_bytes()).hexdigest().encode() + b"  " + n.encode() + b"\n"
                    for n in order)
    assert got == {"digest": hashlib.sha256(blob).hexdigest(), "pages": 5, "first": order[0], "last": order[-1]}
    assert order[0] == "soccer_expansion_shadow_2026-11-06_140003.json" and order[-1].endswith("_alpha.json")
    if shutil.which("sha256sum") and shutil.which("bash"):
        line = ("set -o pipefail; shopt -s nullglob; set -- soccer_expansion_shadow_*.json; "
                "sha256sum -- \"$@\" | sha256sum")
        out = subprocess.run(["bash", "-c", line], cwd=d, env={**os.environ, "LC_ALL": "C"}, capture_output=True,
                             text=True, check=True).stdout.split()[0]
        assert out == got["digest"]


def test_b2c_the_scripts_pages_digest_prints_the_same_with_no_database(tmp_path, monkeypatch, capsys):
    d = tmp_path / "pages"
    _fixture_pages(d)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'no-such.db'}")
    assert script.main(["--exports", str(d), "--pages-digest"]) == 0
    out = capsys.readouterr().out.splitlines()
    d_ = lw.pages_digest(d)
    assert out == [f"PAGES DIGEST {d_['digest']}", f"pages 5  first {d_['first']}  last {d_['last']}"]
    assert not (tmp_path / "no-such.db").exists()                      # no database opened, none created


def test_b2c_the_digest_refuses_a_missing_empty_or_unreadable_folder(tmp_path, capsys):
    with pytest.raises(lw.WindowRefused, match="not a folder"):
        lw.pages_digest(tmp_path / "none")
    (tmp_path / "empty").mkdir()
    with pytest.raises(lw.WindowRefused, match="no soccer_expansion_shadow_"):
        lw.pages_digest(tmp_path / "empty")
    (tmp_path / "dir" / "soccer_expansion_shadow_adir.json").mkdir(parents=True)
    with pytest.raises(lw.WindowRefused, match="not a regular file"):
        lw.pages_digest(tmp_path / "dir")
    assert script.main(["--exports", str(tmp_path / "empty"), "--pages-digest"]) == 2
    assert capsys.readouterr().out.startswith("REFUSED: ")


def test_1087_a_page_that_is_a_symbolic_link_is_refused_never_followed(tmp_path, capsys):
    """#1087 (ARCHITECT 2026-11-23, addendum 459 item 1(a), (c): "lstat in pages_digest"): a page that is a link, to a
    page of the folder's own or to a file elsewhere, refuses the digest; the folder with the link removed digests."""
    d = tmp_path / "pages"
    names = _fixture_pages(d)
    clean = lw.pages_digest(d)
    for target in (d / names[0], tmp_path / "elsewhere.json"):
        if not target.exists():
            target.write_text((d / names[0]).read_text())
        link = d / "soccer_expansion_shadow_2026-11-30_090000.json"
        link.symlink_to(target)
        with pytest.raises(lw.WindowRefused, match="is a symbolic link, not a page"):
            lw.pages_digest(d)
        assert script.main(["--exports", str(d), "--pages-digest"]) == 2
        assert "is a symbolic link" in capsys.readouterr().out
        link.unlink()
    assert lw.pages_digest(d) == clean


def test_1087_an_exports_path_under_a_file_or_with_a_refused_stat_is_refused_not_a_traceback(world, tmp_path,
                                                                                              monkeypatch):
    """#1087 (459 item 1(b), (c)): "NotADirectoryError as a missing folder and any other OSError a refusal". A path
    under a regular file reads as missing and the pages check refuses it as not a folder; a stat refused by
    permissions refuses by name. Both before the reservation: nothing is reserved, nothing written."""
    f = tmp_path / "a-file"
    f.write_text("x")
    assert lr.inside_checkout(f / "pages") is False
    with pytest.raises(lr.ReadRefused, match="not a folder"):
        _pre(world, exports=str(f / "pages"))
    real_stat = os.stat
    blocked = tmp_path / "blocked"

    def stat(p, *a, **k):
        if Path(p) == blocked:
            raise PermissionError(13, "Permission denied", str(p))
        return real_stat(p, *a, **k)
    monkeypatch.setattr(lr.os, "stat", stat)
    with pytest.raises(lr.ReadRefused, match="the folder cannot be checked .PermissionError"):
        _pre(world, exports=str(blocked / "pages"))
    # the read itself, not only the preflight: refused at the pages check, before the reservation
    for bad, why in ((f / "pages", "not a folder"), (blocked / "pages", "the folder cannot be checked")):
        with pytest.raises(lr.ReadRefused, match=why) as ex:
            _run(world, "f" * 64, exports=str(bad))
        assert type(ex.value) is lr.ReadRefused
        assert not os.path.lexists(lr.reservation_path("leagues-sa-v1"))


def test_1087_the_digest_refuses_a_folder_whose_stat_is_refused_or_a_link_loop_never_a_traceback(tmp_path,
                                                                                                   monkeypatch,
                                                                                                   capsys):
    """The host's --pages-digest reads pages_digest alone: a folder whose stat is refused (EACCES) or a name too long
    (ENAMETOOLONG) refuses by name and exit 2; a link loop refuses on both interpreters (the review on #1087)."""
    real_stat = os.stat
    blocked = tmp_path / "blocked"

    def stat(p, *a, **k):
        if Path(p) == blocked:
            raise PermissionError(13, "Permission denied", str(p))
        return real_stat(p, *a, **k)
    monkeypatch.setattr(os, "stat", stat)
    with pytest.raises(lw.WindowRefused, match="the folder cannot be read .PermissionError"):
        lw.pages_digest(blocked)
    assert script.main(["--exports", str(blocked), "--pages-digest"]) == 2
    assert capsys.readouterr().out.startswith("REFUSED: ")
    monkeypatch.setattr(os, "stat", real_stat)
    with pytest.raises(lw.WindowRefused, match="cannot be read|not a folder"):
        lw.pages_digest(tmp_path / ("a" * 300))
    loop = tmp_path / "loop"
    loop.symlink_to(loop)
    with pytest.raises(lw.WindowRefused):
        lw.pages_digest(loop)
    assert script.main(["--exports", str(loop / "pages"), "--pages-digest"]) == 2


def test_1087_a_page_swapped_for_a_link_after_the_lstat_is_refused_at_the_open(tmp_path, monkeypatch):
    d = tmp_path / "pages"
    names = _fixture_pages(d)
    (tmp_path / "other.json").write_text("OTHER")
    real_lstat, victim = os.lstat, d / names[0]

    def lstat(p, *a, **k):
        st = real_lstat(p, *a, **k)
        if Path(p) == victim and not victim.is_symlink():       # swap the page for a link right after its lstat
            victim.unlink()
            victim.symlink_to(tmp_path / "other.json")
        return st
    monkeypatch.setattr(os, "lstat", lstat)
    with pytest.raises(lw.WindowRefused, match="cannot be read"):
        lw.pages_digest(d)


# --------------------------------------------------------------------------------------- the preflight --

def test_the_preflight_prints_counts_the_first_allowed_date_and_the_fingerprint_and_writes_nothing(world,
                                                                                                  monkeypatch):
    monkeypatch.setattr(lw, "score", lambda *a, **k: pytest.fail("scored"))
    before = {p: p.stat().st_mtime_ns for p in world["exports"].iterdir()}
    L = _pre(world)
    ko60 = world["members"][-1][1]
    assert L[0].startswith("LEAGUES WINDOW READ · PREFLIGHT · SA")
    assert any(f"sha256 {lr.copy_state(world['copy'])[0]}" in x for x in L)
    assert any(f"digest {world['digest']} = the host's" in x for x in L)
    assert any("READY" in x for x in L)                                 # the reader's own counts print
    assert any(f"the read is allowed from {(ko60.date() + timedelta(days=1)).isoformat()}" in x for x in L)
    assert len(_fp(L)) == 64 and _fp(L) == _fp(_pre(world))            # the same window, the same fingerprint
    _nothing(world)
    assert {p: p.stat().st_mtime_ns for p in world["exports"].iterdir()} == before
    assert not any(n.endswith(("-wal", "-shm", "-journal")) for n in os.listdir(world["copy"].parent))


# ----------------------------------------------------------------------------------- the refusals, in order --

def test_arguments_refuse_before_anything_is_read(world, monkeypatch):
    monkeypatch.setattr(lr, "check_entry", lambda *a: pytest.fail("read"))
    for kw, why in (({"code": "PL"}, "not one of the five"), ({"db": None}, "--db is required"),
                    ({"exports": ""}, "--exports is required"), ({"pages_digest": None}, "--pages-digest is required"),
                    ({"pages_digest": "xyz"}, "not a sha256"), ({"word": " "}, "architect's word")):
        with pytest.raises(lr.ReadRefused, match=why):
            _run(world, "0" * 64, **kw)
    with pytest.raises(lr.ReadRefused, match="--window-fingerprint"):
        _run(world, None)


def test_the_entry_refuses_absent_run_ruled_or_reserved(world, ledger):
    ledger()
    with pytest.raises(lr.ReadRefused, match="no declared entry"):
        _pre(world)
    ledger(_entry(run={"run_at": "2026-12-01T00:00:00Z"}))
    with pytest.raises(lr.ReadRefused, match="a run is recorded"):
        _pre(world)
    ledger(_entry(verdict={"verdict": "PASS"}))
    with pytest.raises(lr.ReadRefused, match="a verdict is recorded"):
        _pre(world)
    ledger(_entry())
    Path(lr.reservation_path("leagues-sa-v1")).write_text(json.dumps({"started_at": "2026-12-01T00:00:00Z"}))
    with pytest.raises(lr.ReadRefused, match="it is spent"):
        _pre(world)


@pytest.mark.parametrize("plan", [None, {**lw.RULED_PLAN, "bar": 0.95}, {**lw.RULED_PLAN, "n_games": 60.0},
                                  {k: v for k, v in lw.RULED_PLAN.items() if k != "reference"}])
def test_448_2b_the_read_refuses_an_entry_whose_stored_plan_is_not_the_ruled_plan(world, ledger, tmp_path, plan):
    """ARCHITECT 2026-11-22, addendum 448 item 2(b) ("the leagues read refuses an entry whose stored plan is not the
    ruled plan, so a checkout without PR 2 cannot carry a null back to main"), the call placed by addendum 459 item
    2(a): the preflight and the read both refuse at the entry, before the copy is opened; nothing is reserved."""
    ledger(_entry(confirmation_plan=plan))
    with pytest.raises(lr.ReadRefused, match="not the ruled plan .* addendum 448 item 2"):
        _pre(world)
    with pytest.raises(lr.ReadRefused, match="not the ruled plan"):
        _run(world, "f" * 64)
    assert not os.path.lexists(lr.reservation_path("leagues-sa-v1"))
    ledger(_entry())                                                         # the ruled plan: the entry is taken
    assert lr.check_entry("SA")["confirmation_plan"] == lw.RULED_PLAN


def test_the_copy_fence_refuses_a_sidecar_and_a_missing_file(world):
    with pytest.raises(lr.ReadRefused, match="nothing read, nothing reserved"):
        _pre(world, db=str(world["tmp"] / "nope.db"))
    (world["copy"].parent / "sports.db-wal").write_bytes(b"")
    with pytest.raises(lr.ReadRefused, match="-wal sidecar"):
        _pre(world)


def test_b2b_an_exports_folder_inside_the_checkout_refuses(world, tmp_path):
    for inside in (ROOT / "exports", ROOT, ROOT / "tests"):
        with pytest.raises(lr.ReadRefused, match="inside the checkout"):
            _pre(world, exports=str(inside))
    link = tmp_path / "link"
    link.symlink_to(ROOT / "docs")
    with pytest.raises(lr.ReadRefused, match="inside the checkout"):
        _pre(world, exports=str(link))
    assert lr.inside_checkout(ROOT / "tests" / "no-such-subfolder") and not lr.inside_checkout(world["exports"])


def test_the_pages_refuse_a_digest_that_is_not_the_hosts(world):
    with pytest.raises(lr.ReadRefused, match="does not hold exactly the host's pages"):
        _pre(world, pages_digest="a" * 64)
    (world["exports"] / "soccer_expansion_shadow_late.json").write_text(json.dumps({"predictions": []}))
    with pytest.raises(lr.ReadRefused, match="not the host's"):        # a page the host did not digest
        _pre(world)


def test_a_window_that_is_not_ready_refuses_and_gives_no_fingerprint(world, tmp_path):
    from src.db.database import session_scope
    from src.db.schema import Match
    with session_scope() as s:                                          # the 59th member back to scheduled
        m = s.get(Match, world["members"][58][0])
        m.status, m.home_score, m.away_score, m.home_score_90, m.away_score_90 = (MatchStatus.SCHEDULED, None, None,
                                                                                   None, None)
    world["copy"].unlink()
    _copy(tmp_path)
    L = _pre(world)
    assert "NO fingerprint" in L[-1] and not any(x.startswith("WINDOW FINGERPRINT") for x in L)
    with pytest.raises(lr.ReadRefused, match="not ready"):
        _run(world, "0" * 64)
    _nothing(world)


def test_b2d_the_read_refuses_until_the_day_after_the_60th_members_kickoff(world):
    ko60 = world["members"][-1][1]
    fp = _fp(_pre(world))
    same_day = ko60.replace(hour=23, minute=59)
    L = _pre(world, now=same_day)
    assert any(f"NOT TODAY ({ko60.date().isoformat()})" in x for x in L)
    with pytest.raises(lr.ReadRefused, match=r"the day after \(addendum 447 item 2 B2\(d\)\)"):
        _run(world, _fp(L), now=same_day)
    _nothing(world)
    assert lr.first_allowed({lw.LAST_MEMBER: (1, ko60)}) == ko60.date() + timedelta(days=1)
    assert lr.first_allowed({lw.LAST_MEMBER: None}) is None
    assert fp


def test_a_fingerprint_that_is_not_this_windows_refuses_before_the_reservation(world, monkeypatch):
    monkeypatch.setattr(lr, "reserve", lambda *a, **k: pytest.fail("reserved"))
    with pytest.raises(lr.ReadRefused, match="is not this window's"):
        _run(world, "0" * 64)
    _nothing(world)


def test_the_fingerprint_covers_the_members_rows_ruled_list_copy_digest_and_constants(world):
    sha, pages, w, stored = lr.load("SA", reg.get("leagues-sa-v1", reg.LEDGER), world["copy"], world["exports"],
                                    world["digest"], NOW)
    base = lr.window_fingerprint("SA", w, stored, sha, pages["digest"])
    assert base == _fp(_pre(world))
    changed = [
        lr.window_fingerprint("SA", {**w, "members": w["members"][::-1]}, stored, sha, pages["digest"]),
        lr.window_fingerprint("SA", w, {**stored, w["members"][0]: {"x": 1}}, sha, pages["digest"]),
        lr.window_fingerprint("SA", {**w, "ruled_items_read": {1: {"match_id": 1}}}, stored, sha, pages["digest"]),
        lr.window_fingerprint("SA", w, stored, "b" * 64, pages["digest"]),
        lr.window_fingerprint("SA", w, stored, sha, "c" * 64),
        lr.window_fingerprint("SA", {**w, "constants": {**w["constants"], "rho": -0.2}}, stored, sha,
                              pages["digest"])]
    assert len({base, *changed}) == 7


# ------------------------------------------------------------------------------------------ THE ONE READ --

def test_the_one_read_reserves_before_it_scores_records_once_and_accounts_every_reached_game(world, monkeypatch):
    seen = []
    real = lw.score

    def spy(*a, **k):
        seen.append(Path(lr.reservation_path("leagues-sa-v1")).exists())
        return real(*a, **k)
    monkeypatch.setattr(lw, "score", spy)
    fp = _fp(_pre(world))
    res = _run(world, fp)
    assert seen == [True]
    ids = [mid for mid, _ in world["members"]]
    assert res["members_in_order"] == ids and res["n"] == 60
    assert res["verdict"] == lw.verdict_of(res["ll_candidate"], res["ll_close"])
    # C1: the opening, the 60th member's place, written by the read before any verdict exists
    assert res["confirmation_opens_after"] == {"kickoff": world["members"][-1][1].strftime("%Y-%m-%dT%H:%M:%SZ"),
                                               "match_id": ids[-1]}
    # B2(e): every game the loop reached took a slot or is named with its cause
    assert res["took_no_slot"] == [{"match_id": 2900, "kickoff": (AT + timedelta(hours=4)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"), "cause": "cancelled"}]
    assert res["copy_sha256"] == lr.copy_state(world["copy"])[0] and res["pages"]["digest"] == world["digest"]
    assert res["architect_word"] == WORD and res["window_fingerprint"] == fp and res["audit_lines"]
    json.dumps(res, allow_nan=False)
    held = json.loads(Path(lr.reservation_path("leagues-sa-v1")).read_text())
    assert held["window_fingerprint"] == fp and held["pages_digest"] == world["digest"]
    lines = lr.run_lines(res)
    assert lines[-1] == f"  VERDICT (computed; the architect rules, then --record-verdict): {res['verdict']}"
    assert any("reached and took no slot (447 B2(e)), by id in the run record: 1 — cancelled 1" in x for x in lines)
    e = lr.record("SA", res)
    assert e["status"] == "run" and e["run"]["result"] == res and e["run"]["n_scored"] == 60
    assert (Path(reg.IDS_DIR) / "leagues-sa-v1.txt").read_text().split() == [str(i) for i in sorted(ids)]
    with pytest.raises(lr.ReadRefused, match="a run is recorded"):
        _run(world, fp)
    assert not any(n.endswith(("-wal", "-shm", "-journal")) for n in os.listdir(world["copy"].parent))


def test_c1_the_opening_is_the_60th_members_place_in_the_windows_order_a_tie_ordered_by_id(ledger, tmp_path,
                                                                                         monkeypatch):
    """Two games kick off together at the 60th place: the lower id is the 60th member and the opening, the higher id
    is the first game later in the order (447 C1: "the same kickoff and a higher id")."""
    monkeypatch.setattr(reg, "IDS_DIR", str(tmp_path / "ids"))
    _comps()
    ledger(_entry())
    t = _teams("SA")
    _priors("SA", t)
    got = _members("SA", t, 59, 2000, AT + timedelta(hours=1))
    tie = got[-1][1] + timedelta(hours=6)
    for mid in (3001, 3000):
        _game(mid, "SA", tie, (t[4], t[5]) if mid == 3000 else (t[6], t[7]))
        from tests.test_leagues_window import _legs
        _legs(mid, tie)
    _export("SA")
    w = lw.read(("SA",), now=NOW)["SA"]
    assert w["state"] == "ready" and w["members"][-1] == 3000 and w[lw.LAST_MEMBER] == (3000, tie)
    assert 3001 not in w["members"] and not w[lw.TOOK_NO_SLOT]          # counting stopped at the 60th: not reached


def test_a_failure_after_the_reservation_leaves_the_read_spent_and_records_nothing(world, monkeypatch):
    fp = _fp(_pre(world))

    def boom(*a, **k):
        raise lw.WindowRefused("the window moved (tests only)")
    monkeypatch.setattr(lw, "score", boom)
    with pytest.raises(lr.SpentRefused, match="the reservation stands and the one read is spent"):
        _run(world, fp)
    assert Path(lr.reservation_path("leagues-sa-v1")).exists()
    assert reg.get("leagues-sa-v1", reg.LEDGER)["run"] is None
    monkeypatch.setattr(lw, "score", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("a database error")))
    Path(lr.reservation_path("leagues-sa-v1")).unlink()
    with pytest.raises(lr.SpentRefused, match="RuntimeError: a database error"):
        _run(world, fp)


def test_a_page_changing_during_the_read_leaves_it_spent(world, monkeypatch):
    fp = _fp(_pre(world))
    real = lw.score

    def score_then_touch(*a, **k):
        out = real(*a, **k)
        p = sorted(world["exports"].glob("soccer_expansion_shadow_*.json"))[0]
        p.write_text(p.read_text() + " ")
        return out
    monkeypatch.setattr(lw, "score", score_then_touch)
    with pytest.raises(lr.SpentRefused, match="the pages changed during the read"):
        _run(world, fp)
    assert reg.get("leagues-sa-v1", reg.LEDGER)["run"] is None


def test_a_failed_reservation_write_spends_nothing(world, monkeypatch):
    from src.walters import nfl_v2_gate as ng
    fp = _fp(_pre(world))
    monkeypatch.setattr(ng, "_write_all", lambda *a: (_ for _ in ()).throw(OSError("disk full (tests only)")))
    with pytest.raises(lr.ReadRefused, match="removed; nothing scored"):
        _run(world, fp)
    _nothing(world)


def test_the_cross_ref_guard_runs_before_the_reservation_and_a_refusal_reserves_nothing(world, monkeypatch):
    fp = _fp(_pre(world))
    calls = []

    def guard(eid, no_fetch=False, repo=None):
        calls.append((eid, no_fetch))
        raise reg.CrossRefRefused("held on another ref (tests only)")
    monkeypatch.setattr(reg, "cross_ref_guard", guard)
    with pytest.raises(lr.ReadRefused, match="held on another ref"):
        lr.run("SA", str(world["copy"]), str(world["exports"]), world["digest"], WORD, fp, now=NOW, no_fetch=True)
    assert calls == [("leagues-sa-v1", True)]
    _nothing(world)


# -------------------------------------------------------------------------------------------- B1 --

def test_b1_the_verdict_is_its_own_invocation_and_must_equal_the_computed_one(world):
    with pytest.raises(lr.ReadRefused, match="no run recorded"):
        lr.record_verdict("SA", "PASS", "a ruling (tests only)")
    res = _run(world, _fp(_pre(world)))
    lr.record("SA", res)
    other = "REJECT" if res["verdict"] == "PASS" else "PASS"
    with pytest.raises(lr.ReadRefused, match="the word equals the computed one"):
        lr.record_verdict("SA", other, "a ruling (tests only)")
    with pytest.raises(lr.ReadRefused, match="--ruling is required"):
        lr.record_verdict("SA", res["verdict"], "  ")
    with pytest.raises(lr.ReadRefused, match="PASS or REJECT"):
        lr.record_verdict("SA", "FAIL", "a ruling (tests only)")
    e = lr.record_verdict("SA", res["verdict"].lower(), "the architect's words (tests only)")
    assert e["verdict"]["verdict"] == res["verdict"] and e["verdict"]["ruling"] == "the architect's words (tests only)"
    assert e["status"] == ("confirming" if res["verdict"] == "PASS" else "closed")
    with pytest.raises(lr.ReadRefused, match="already recorded"):
        lr.record_verdict("SA", res["verdict"], "again")


def test_b1_a_run_not_recorded_by_this_command_refuses_the_verdict(world, ledger):
    ledger(_entry(run={"run_at": "2026-12-01T00:00:00Z", "result": {"verdict": "PASS"}}))
    with pytest.raises(lr.ReadRefused, match="carries no computed verdict"):
        lr.record_verdict("SA", "PASS", "a ruling")


# ------------------------------------------------------------------------------------------- the CLI --

def test_the_cli_prints_refused_and_exits_2_and_records_on_the_read(world):
    from click.testing import CliRunner

    import cli
    args = ["leagues-window-read", "--code", "SA", "--db", str(world["copy"]), "--exports", str(world["exports"]),
            "--pages-digest", world["digest"]]
    r = CliRunner().invoke(cli.cli, args + ["--architect-word", WORD])
    assert r.exit_code == 2 and "REFUSED: " in r.output and "--window-fingerprint" in r.output
    r = CliRunner().invoke(cli.cli, ["leagues-window-read", "--code", "SA", "--record-verdict", "PASS", "--ruling",
                                     "x", "--preflight"])
    assert r.exit_code == 2 and "its own invocation" in r.output
    assert reg.get("leagues-sa-v1", reg.LEDGER)["run"] is None


def test_no_prediction_output_changes_the_readers_print_is_the_same(world):
    """read() through a copy session prints exactly what read() on the app's database prints (the same store)."""
    from src.walters import mlb_pitchers_gate as mp
    plain = lw.read(("SA",), now=NOW, export_dir=str(world["exports"]))
    with mp.readonly_session(world["copy"]) as s:
        via = lw.read(("SA",), now=NOW, export_dir=str(world["exports"]), s=s)
    assert lw.lines(plain, NOW) == lw.lines(via, NOW)
    assert plain["SA"]["members"] == via["SA"]["members"]


# ------------------------------------------------------------- the review's findings, before the push --

def test_the_refusals_come_in_the_plans_order_when_two_faults_stand_together(world, ledger, tmp_path):
    """Two faults at once: the earlier step's refusal is the one named (arguments, entry, copy, pages, entry checks,
    window, the day after, the fingerprint)."""
    bad_copy = str(tmp_path / "nope.db")
    ledger()                                                            # entry absent AND a bad copy
    with pytest.raises(lr.ReadRefused, match="no declared entry"):
        _pre(world, db=bad_copy)
    ledger(_entry())                                                    # a bad copy AND pages inside the checkout
    with pytest.raises(lr.ReadRefused, match="nothing read, nothing reserved"):
        _pre(world, db=bad_copy, exports=str(ROOT / "exports"))
    ledger(_entry(frozen_constants={"production_version": "v22", "rho": -0.2, "elo_goal_coeff": 0.0008}))
    with pytest.raises(lr.ReadRefused, match="inside the checkout"):    # pages AND drifted constants
        _pre(world, exports=str(ROOT / "exports"))
    bad = world["exports"] / "soccer_expansion_shadow_zz_bad.json"
    bad.write_text("not json")                                          # a malformed page AND drifted constants
    with pytest.raises(lr.ReadRefused, match="zz_bad"):
        _pre(world, pages_digest=lw.pages_digest(world["exports"])["digest"])
    bad.unlink()
    ledger(_entry())
    ko60 = world["members"][-1][1]                                      # the day before AND a wrong fingerprint
    with pytest.raises(lr.ReadRefused, match=r"B2\(d\)"):
        _run(world, "0" * 64, now=ko60.replace(hour=23, minute=59))
    _nothing(world)


def test_bytes_that_change_between_the_digest_and_the_read_refuse_before_the_reservation(world, monkeypatch):
    fp = _fp(_pre(world))
    real = lr.check_pages

    def then_touch(exports, given):
        d = real(exports, given)
        p = sorted(Path(exports).glob("soccer_expansion_shadow_*.json"))[0]
        p.write_text(p.read_text() + "\n")                             # the same JSON, the same count, other bytes
        return d
    monkeypatch.setattr(lr, "check_pages", then_touch)
    monkeypatch.setattr(lr, "reserve", lambda *a, **k: pytest.fail("reserved"))
    with pytest.raises(lr.ReadRefused, match="the pages changed while the window was read; nothing reserved"):
        _run(world, fp)
    _nothing(world)


@pytest.mark.parametrize("how", ["copy", "sidecar"])
def test_the_copy_changing_or_a_sidecar_appearing_during_the_score_leaves_the_read_spent(world, monkeypatch, how):
    fp = _fp(_pre(world))
    real = lw.score

    def score_then(*a, **k):
        out = real(*a, **k)
        if how == "copy":
            with open(world["copy"], "ab") as f:
                f.write(b"\0" * 10)
        else:
            (world["copy"].parent / "sports.db-journal").write_bytes(b"")
        return out
    monkeypatch.setattr(lw, "score", score_then)
    with pytest.raises(lr.SpentRefused, match="the copy changed during the read" if how == "copy"
                       else "a sidecar appeared beside the copy"):
        _run(world, fp)
    assert Path(lr.reservation_path("leagues-sa-v1")).exists()
    assert reg.get("leagues-sa-v1", reg.LEDGER)["run"] is None


def test_b1_a_pass_word_on_a_computed_reject_refuses_and_a_reject_closes(world, ledger):
    run = {"run_at": "2026-12-21T00:00:00Z", "result": {"command": lr.COMMAND, "verdict": "REJECT"}}
    ledger(_entry(run=run))
    with pytest.raises(lr.ReadRefused, match="the word given is PASS, the computed verdict is REJECT"):
        lr.record_verdict("SA", "PASS", "a ruling (tests only)")
    e = lr.record_verdict("SA", "REJECT", "a ruling (tests only)")
    assert e["status"] == "closed" and e["verdict"]["verdict"] == "REJECT"


def test_the_cli_happy_path_prints_the_receipt_records_and_takes_the_verdict(world):
    from click.testing import CliRunner

    import cli
    base = ["leagues-window-read", "--code", "SA", "--db", str(world["copy"]), "--exports", str(world["exports"]),
            "--pages-digest", world["digest"]]
    r = CliRunner().invoke(cli.cli, base + ["--preflight", "--architect-word", "x"])
    assert r.exit_code == 2 and "takes no word" in r.output
    import src.walters.leagues_read as lr_
    pre = lr_.preflight_lines("SA", str(world["copy"]), str(world["exports"]), world["digest"])
    fp = _fp(pre)
    r = CliRunner().invoke(cli.cli, base + ["--architect-word", WORD, "--window-fingerprint", fp, "--no-fetch"])
    assert r.exit_code == 0, r.output
    out = r.output
    d = lw.pages_digest(world["exports"])
    assert f"sha256 {lr.copy_state(world['copy'])[0]}" in out
    assert f"--exports: {d['pages']} pages · first {d['first']} · last {d['last']} · digest {d['digest']}" in out
    assert out.index("--exports: ") < out.index("cross-ref guard") < out.index("VERDICT")   # the receipt first
    assert "found unchanged after the score" in out and "recorded: 60 ids" in out
    v = reg.get("leagues-sa-v1", reg.LEDGER)["run"]["result"]["verdict"]
    r = CliRunner().invoke(cli.cli, ["leagues-window-read", "--code", "SA", "--record-verdict", v, "--ruling",
                                     "the architect's words (tests only)"])
    assert r.exit_code == 0 and f"verdict {v}" in r.output


def test_b2b_the_main_checkout_of_a_worktree_is_inside_too(world, tmp_path, monkeypatch):
    from src.walters import mlb_pitchers_gate as mp
    main = tmp_path / "main-checkout"
    (main / "data").mkdir(parents=True)
    (main / "exports" / "host").mkdir(parents=True)
    monkeypatch.setattr(mp, "_main_checkout_data", lambda: main / "data")
    assert lr.inside_checkout(main / "exports" / "host") and not lr.inside_checkout(world["exports"])


def test_the_read_never_writes_into_the_exports_folder(world):
    before = {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in world["exports"].iterdir()}
    _run(world, _fp(_pre(world)))
    assert {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in world["exports"].iterdir()} == before

