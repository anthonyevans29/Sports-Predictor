"""ONE CLOSING, ONE PAGE, ONE FILE (ARCHITECT 2026-10-11, addendum 40 item 2, #428; finding #423), on the closing-run
test frame (tests/test_closing_runs.py: a SCRATCH schedule in a throwaway DB under tmp_path, every side effect faked,
the network blocked).

"A closing run whose page went out writes exports/closing_<FAMILY>_<start>.json: the games on its page and no other,
each row as the run's export gave it, and a closing block naming the family, the start time, the run id and the match
ids. A run whose page did not go out writes no such file. A closing run does not write, replace or move the family's
slate file." The receipt finding: the 12:55Z NFL run covered one game and wrote 14 rows into the slate file."""
import hashlib
import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest

from tests.test_closing_runs import (  # noqa: F401  (box is a fixture)
    DAY, NOW, at, box, call_pages, mc, c, nfl_doc, mlb_doc, runs, status_on_next_schedule_read, _set_call)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))
import exports_mirror  # noqa: E402

BACKFILL = ROOT / "scripts" / "closing_file_backfill.py"

PAGE = {"NFL": [301, 304, 302, 303], "SOCCER": [401, 402], "MLB": [101, 104, 105, 102]}
START = {"NFL": 35, "SOCCER": 35, "MLB": 30}
SLATE = {"NFL": f"nfl_predictions_{DAY}.json", "SOCCER": f"soccer_PL_{DAY}.json", "MLB": f"mlb_MLB_{DAY}.json"}


def _closing(box, fam):
    name = f"closing_{fam}_{mc.utc(mc.parse_utc(at(START[fam]))):%Y-%m-%dT%H%MZ}.json"
    return box.repo / "exports" / name


@pytest.mark.parametrize("fam", ["NFL", "SOCCER", "MLB"])
def test_the_closing_file_holds_the_pages_games_and_no_other(box, fam):
    """The file finding #423 asked for: the run's page games only (PASS games included), each row as the export gave
    it, a closing block, count = the rows kept; the slate file is neither written nor replaced."""
    assert mc.run(fam, start=at(START[fam]), now=NOW) == 0
    r = runs(fam)[-1]
    f = _closing(box, fam)
    assert f.name == f"closing_{fam}_2026-10-11T{'1700' if START[fam] == 35 else '1655'}Z.json"
    doc = json.loads(f.read_text())
    paged = [x["match_id"] for x in r["desk_rows"]]
    assert sorted(paged) == sorted(PAGE[fam])
    assert [p["match_id"] for p in doc["predictions"]] == [
        p["match_id"] for p in box.docs[fam]["predictions"] if p["match_id"] in paged]   # the export's order
    exported = {p["match_id"]: p for p in box.docs[fam]["predictions"]}
    assert all(p == exported[p["match_id"]] for p in doc["predictions"])                  # each row as given
    assert doc["count"] == len(paged) < len(box.docs[fam]["predictions"])                 # no other game
    assert doc["closing"] == {"family": fam, "start": at(START[fam]), "run_id": r["run_id"],
                              "match_ids": [p["match_id"] for p in doc["predictions"]], "called_off": []}
    assert doc["desk_meta"] == box.docs[fam]["desk_meta"] and doc["sport"] == box.docs[fam]["sport"]
    # the receipt records both files and their sha256
    assert r["closing_file"] == {"file": f"exports/{f.name}", "sha256": hashlib.sha256(f.read_bytes()).hexdigest()}
    assert r["export"] == f"logs/{r['run_id']}.{SLATE[fam]}" and r["export_written"]["file"] == r["export"]
    assert r["export_written"]["sha256"] == hashlib.sha256((box.repo / r["export"]).read_bytes()).hexdigest()
    assert sorted(p.name for p in (box.repo / "exports").iterdir()) == [f.name]           # no slate file written
    assert r["page"]["at"] >= r["completed_at"]


def test_the_slate_file_is_never_replaced(box):
    """"A closing run does not write, replace or move the family's slate file. The slate chains write it." """
    slate = box.repo / "exports" / SLATE["NFL"]
    slate.write_text(json.dumps(nfl_doc()))
    before = slate.read_bytes(), slate.stat().st_mtime
    box.docs["NFL"] = _set_call(nfl_doc(), 301)
    assert mc.run("NFL", start=at(35), now=NOW) == 0
    assert (slate.read_bytes(), slate.stat().st_mtime) == before
    assert json.loads(_closing(box, "NFL").read_text())["predictions"][0]["desk"]["call"] == "PASS"


def test_a_page_not_accepted_writes_no_closing_file(box):
    box.page_ok = False
    assert mc.run("NFL", start=at(35), now=NOW) == 1
    assert runs()[-1]["failed"] == "page" and "closing_file" not in runs()[-1]
    assert not _closing(box, "NFL").exists() and not any((box.repo / "exports").iterdir())


def test_an_own_check_failure_writes_no_closing_file(box):
    box.no_fresh = {"sync-odds-football"}
    assert mc.run("NFL", start=at(35), now=NOW) == 1
    assert runs()[-1]["failed"] == "stale prices" and not any((box.repo / "exports").iterdir())


def test_the_file_is_written_after_the_page_and_before_the_push(box, monkeypatch):
    seen = []
    monkeypatch.setattr(mc, "push_mirror", lambda label="closing": seen.append(
        (_closing(box, "NFL").exists(), len(call_pages(box)))) or {"exit": 0, "tail": ["pushed"]})
    assert mc.run("NFL", start=at(35), now=NOW) == 0
    assert seen == [(True, 1)]


def test_a_failed_write_is_receipted_and_notified_and_the_closing_is_not_run_again(box, monkeypatch):
    """"A write that fails is receipted and notified as a failed push is, and the closing is not run again." """
    monkeypatch.setattr(mc, "write_closing_file", lambda doc, name, mtime=None: {
        "file": f"exports/{name}", "error": "OSError: disk full"})
    assert mc.watch(now=NOW, families=("NFL",)) == 0
    r = runs()[-1]
    assert r["exit"] == 0 and r["closing_file_failed"] is True and r["closing_file"]["error"] == "OSError: disk full"
    assert box.notes[-1].startswith("Closing NFL 2026-10-11 13:00 ET: PAGED; closing file NOT written")
    assert box.pushes == ["closing"]                                                      # the push still runs
    assert mc.watch(now=NOW + timedelta(minutes=1), families=("NFL",)) == 0
    assert len(runs("NFL")) == 1 and len(call_pages(box)) == 1                            # not run again


def test_a_called_off_game_is_named_in_the_closing_block_and_has_no_row(box, monkeypatch):
    status_on_next_schedule_read(box, monkeypatch, {301: "POSTPONED"})
    assert mc.run("NFL", start=at(35), now=NOW) == 0
    doc = json.loads(_closing(box, "NFL").read_text())
    assert 301 not in [p["match_id"] for p in doc["predictions"]] and doc["count"] == 3
    assert doc["closing"]["called_off"] == [{"match_id": 301, "status": "POSTPONED"}]
    assert "Buffalo Visitors @ Buffalo · POSTPONED" in call_pages(box)[-1]["body"]          # its line on the page


def test_a_closing_file_is_never_read_as_a_slate_file(box):
    """"last_calls reads slate files and receipts, as now. A closing file is never read as a slate file." """
    (box.repo / "exports" / "closing_MLB_2026-10-11T1700Z.json").write_text(json.dumps(_set_call(mlb_doc(), 103)))
    (box.repo / "exports" / SLATE["MLB"]).write_text(json.dumps(mlb_doc()))
    assert mc.last_calls("MLB", NOW)[103]["call"] == "PLAY Laterton 1u"
    for fam, f in mc.FAMILIES.items():
        assert not Path(_closing(box, fam).name).match(f["export_glob"])


def test_the_mirror_kind_is_closing_family_and_latest_holds_the_newest():
    """"<start> is the run's start time in UTC, written 2026-10-11T1700Z. exports_mirror's kind is then closing_NFL,
    and latest/ holds the newest of each family with no change there." """
    assert exports_mirror.kind_of("closing_NFL_2026-10-11T1700Z.json") == "closing_NFL"
    assert exports_mirror.kind_of("closing_SOCCER_2026-10-11T1255Z.json") == "closing_SOCCER"
    pl = exports_mirror.plan([("closing_NFL_2026-10-11T1300Z.json", 1_791_730_000.0),
                              ("closing_NFL_2026-10-11T1700Z.json", 1_791_744_000.0),
                              (f"nfl_predictions_{DAY}.json", 1_791_700_000.0)], "laptop", mc.date(2026, 10, 11))
    assert pl["latest"]["laptop/latest/closing_NFL.json"] == "closing_NFL_2026-10-11T1700Z.json"
    assert pl["latest"]["laptop/latest/nfl_predictions.json"] == f"nfl_predictions_{DAY}.json"


def test_closing_doc_is_pure_and_keeps_the_exports_own_fields():
    doc = {"exported_at": "2026-10-11T16:25:49Z", "git_sha": "081d9fa", "sport": "nfl", "count": 3,
           "desk_meta": {"as_of": "x"}, "predictions": [{"match_id": 1}, {"match_id": 2}, {"match_id": 3}]}
    snap = json.dumps(doc)
    out = mc.closing_doc(doc, "NFL", mc.parse_utc("2026-10-11T17:00:00Z"), "RID", [3, 1],
                         [{"match_id": 9, "status": "CANCELLED", "game": "x"}])
    assert json.dumps(doc) == snap
    assert out == {"exported_at": "2026-10-11T16:25:49Z", "git_sha": "081d9fa", "sport": "nfl", "count": 2,
                   "desk_meta": {"as_of": "x"}, "predictions": [{"match_id": 1}, {"match_id": 3}],
                   "closing": {"family": "NFL", "start": "2026-10-11T17:00:00Z", "run_id": "RID",
                               "match_ids": [1, 3], "called_off": [{"match_id": 9, "status": "CANCELLED"}]}}


def test_the_dry_run_names_both_files(box, capsys):
    assert mc.run("NFL", start=at(35), dry_run=True, now=NOW) == 0
    out = capsys.readouterr().out
    assert f".{SLATE['NFL']} · then, once the page is accepted, exports/closing_NFL_2026-10-11T1700Z.json" in out
    assert "--out logs/" in out and not any((box.repo / "exports").iterdir())


# ------------------------------------------------------------------------------------------------ the backfill --

def _git(repo, *a):
    p = subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return p.stdout


def _mirror(tmp_path, files_by_commit):
    m = tmp_path / "mirror"
    m.mkdir()
    _git(m, "init", "-q")
    _git(m, "config", "user.email", "t@t")
    _git(m, "config", "user.name", "t")
    for files in files_by_commit:
        for rel, data in files.items():
            (m / rel).parent.mkdir(parents=True, exist_ok=True)
            (m / rel).write_bytes(data)
        _git(m, "add", "-f", "-A", ".")
        _git(m, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "push")
    return m


def _receipt(run_id, sha, rows, start="2026-10-11T12:55:00Z", fam="NFL", **extra):
    return {"kind": "closing", "family": fam, "run_id": run_id, "start": start, "exit": 0,
            "export_written": {"file": f"exports/nfl_predictions_{DAY}.json", "sha256": sha},
            "desk_rows": [{"match_id": m} for m in rows], "completed_at": "2026-10-11T12:57:30Z",
            "page": {"phone": {"accepted": True}}, **extra}


def test_the_backfill_rebuilds_each_paged_run_from_the_mirrors_history_by_sha256(tmp_path, monkeypatch, capsys):
    """The 12:55Z case: the export held 5 rows, the page one game (301). The file is rebuilt with that game only,
    named by the start, its mtime the run's page time. A run whose bytes are gone is listed, nothing rebuilt; an
    unpaged run is not a closing; the database is never opened."""
    import sqlite3
    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: (_ for _ in ()).throw(AssertionError("DB opened")))
    first = json.dumps(nfl_doc()).encode()
    second = json.dumps(_set_call(nfl_doc(), 304, "PLAY")).encode()   # the 16:25Z run overwrote the same name
    m = _mirror(tmp_path, [{f"laptop/{DAY}/nfl_predictions_{DAY}.json": first},
                           {f"laptop/{DAY}/nfl_predictions_{DAY}.json": second}])
    sha = lambda b: hashlib.sha256(b).hexdigest()                     # noqa: E731
    rec = tmp_path / "receipts.jsonl"
    rec.write_text("\n".join(json.dumps(x) for x in [
        _receipt("A", sha(first), [301]),
        _receipt("B", sha(second), [303, 304], start="2026-10-11T17:00:00Z",
                 page={"phone": {"accepted": True}, "at": "2026-10-11T16:31:02Z"},
                 called_off=[{"match_id": 302, "status": "POSTPONED", "game": "x"}]),
        _receipt("C", "0" * 64, [301], start="2026-10-11T20:25:00Z"),
        _receipt("D", sha(first), [301], start="2026-10-11T23:45:00Z", page={"phone": {"accepted": False}}),
        {"kind": "closing_miss", "family": "NFL"}]) + "\n")
    ex = tmp_path / "exports"
    import scripts.closing_file_backfill as bf
    argv = ["--mirror", str(m), "--receipts", str(rec), "--exports", str(ex)]
    assert bf.main(argv + ["--dry-run"]) == 0
    assert not ex.exists()
    assert bf.main(argv) == 0
    out = capsys.readouterr().out.splitlines()
    a = json.loads((ex / "closing_NFL_2026-10-11T1255Z.json").read_text())
    assert [p["match_id"] for p in a["predictions"]] == [301] and a["count"] == 1
    assert a["closing"] == {"family": "NFL", "start": "2026-10-11T12:55:00Z", "run_id": "A", "match_ids": [301],
                            "called_off": []}
    assert (ex / "closing_NFL_2026-10-11T1255Z.json").stat().st_mtime == mc.parse_utc("2026-10-11T12:57:30Z").timestamp()
    b = json.loads((ex / "closing_NFL_2026-10-11T1700Z.json").read_text())
    assert [p["match_id"] for p in b["predictions"]] == [304, 303]                        # the export's order
    assert b["predictions"][0]["desk"]["call"] == "PLAY"                                  # B's own bytes
    assert b["closing"]["called_off"] == [{"match_id": 302, "status": "POSTPONED"}]
    assert (ex / "closing_NFL_2026-10-11T1700Z.json").stat().st_mtime == mc.parse_utc("2026-10-11T16:31:02Z").timestamp()
    assert sorted(p.name for p in ex.iterdir()) == ["closing_NFL_2026-10-11T1255Z.json",
                                                    "closing_NFL_2026-10-11T1700Z.json"]
    assert any(x.startswith("NOT FOUND   NFL 2026-10-11T20:25:00Z · run C") for x in out)
    assert not any("run D" in x for x in out)                                             # its page did not go out
    assert out[-1] == 'CLOSING-BACKFILL {"NOT FOUND": 1, "WRITTEN": 2, "runs": 3}'
    assert bf.main(argv) == 0                                                              # once is enough
    assert capsys.readouterr().out.splitlines()[-1] == 'CLOSING-BACKFILL {"NOT FOUND": 1, "UNCHANGED": 2, "runs": 3}'


def test_codex_a_second_run_for_the_same_start_never_replaces_the_first_file(box):
    """Codex on #433 (P2): a manual rerun of a closed start pages again, but its file write is refused (receipted
    and notified); the first run's file and its sha256 stand."""
    assert mc.run("NFL", start=at(35), now=NOW) == 0
    f = _closing(box, "NFL")
    first = f.read_bytes()
    box.docs["NFL"] = _set_call(nfl_doc(), 301)
    assert mc.run("NFL", start=at(35), now=NOW + timedelta(minutes=1)) == 0
    r = runs()[-1]
    assert r["closing_file_failed"] is True and r["closing_file"]["error"].startswith("exists")
    assert f.read_bytes() == first and runs()[-2]["closing_file"]["sha256"] == hashlib.sha256(first).hexdigest()


@pytest.mark.parametrize("target", ["data/sports.db", "data/x/out.json"])
def test_codex_export_nfl_out_never_writes_under_data_or_onto_the_database(tmp_path, monkeypatch, target):
    """Codex on #433 (P1): --out is refused before anything is opened when it resolves under data/ or onto the
    configured database."""
    from src.walters import nfl_predict as npx
    with pytest.raises(ValueError, match="law 5"):
        npx.refuse_out_path(str(ROOT / target))
    db = tmp_path / "live.db"
    db.write_bytes(b"x")
    alias = tmp_path / "alias.json"
    alias.symlink_to(db)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    with pytest.raises(ValueError, match="law 5"):
        npx.refuse_out_path(str(alias))
    hard = tmp_path / "hard.json"                                                       # Codex round 2
    os.link(db, hard)
    for bad in (hard, Path(str(db) + "-wal"), Path(str(db) + "-shm"), Path(str(db) + "-journal")):
        with pytest.raises(ValueError, match="law 5"):
            npx.refuse_out_path(str(bad))
    npx.refuse_out_path(str(tmp_path / "logs" / "ok.json"))                              # anywhere else: fine
    assert db.read_bytes() == b"x"
