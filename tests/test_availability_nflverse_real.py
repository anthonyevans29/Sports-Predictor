"""THE NFLVERSE REAL-ROW TESTS (ARCHITECT 2026-11-07, addendum 284 item 1(a); lane availability-record): the two real
depth-chart release files read through the merged adapter (src/availability/nflverse.py, the ingest the command's
--file path runs: `python cli.py availability-nflverse --file PATH` calls nflverse.run(season, file) and prints its
receipt) into a throwaway SQLite file, 2025 first, then 2026 (the watermark is the source's, 259 item 2(c)).

Item 1(a), verbatim: "the PR reads the two real depth-chart files through the merged adapter under test, reproduces 259
item 2's counts (278 loads for 2026, 221 for 2025, 32 teams per load, the payload hash on every snapshot load), prints
each file's sha256, and retires the hand-carried excerpt fixture from the tests that no longer need it (kept if a test
still reads it); no production code change expected — a difference between the real rows and the adapter's reading is
a FINDING in the PR body, ruled before any fix."

THE FILES ARE NOT IN THE REPO (third-party data, CC BY 4.0, ~53 MB and ~72 MB) and NEVER DOWNLOADED BY A TEST. The
module reads them from the directory named by the environment variable NFLVERSE_REAL_DIR (depth_charts_2025.csv and
depth_charts_2026.csv, as nflverse publishes them under the release tag depth_charts) and is SKIPPED, naming the
variable, when it is unset or a file is missing. CI does not set it: these tests run where the operator (or a session)
has the files, e.g.

    curl -L -o DIR/depth_charts_2025.csv https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_2025.csv
    curl -L -o DIR/depth_charts_2026.csv https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_2026.csv
    NFLVERSE_REAL_DIR=DIR python -m pytest tests/test_availability_nflverse_real.py -s

and `-s` prints the receipt (per file: sha256, size, rows, loads, teams per load, payload-hash coverage, rows with no
espn_id, and the adapter's own receipt lines).

THE SHA256s READ 2026-11-07 are pinned below. 2025 is a CLOSED season: a 2025 file whose sha256 is not the pinned one
FAILS, with the reason (its counts are pinned exactly). 2026 is LIVE (nflverse adds loads twice a day): its sha256 as
read today is recorded; the counts pinned on today's whole file are SKIPPED, saying so, when the sha256 differs, while
259's counts are asserted on every read, cut at the newest load 259's read could have seen (THE CUT, below), since
growth only appends loads after it. THREE INVARIANTS run on every read of the whole 2026 file, whatever its sha256:
every load 32 teams, no row without an espn_id, the payload hash on every stored row. A later live load that breaks
one FAILS, with the message naming it a FINDING (to be ruled before any fix), never skips.

THE GUARD (259 item 2(b)) is worked out twice: by the adapter's ingest, and by this module from the csv rows alone
(_guard: each (dt, team) group in dt order, 2025 then 2026, partial when it holds fewer than HALF the team's previous
complete group, else it becomes the previous complete one; a group that lost a blank-espn_id row is partial and never a
previous complete group). The two must agree on both files; the dated pins below record today's result.

THE CUT (how 259's 2026 count is compared, from the repo record, not by fitting it): 262 item 5 recorded the 2026
file's rows at that read, 747,450 (src/availability/nflverse.py's docstring; #841's ledger entry); the file's rows
through load 2026-11-05T07:01:33Z sum to exactly 747,450, at the 278th load, and 259 item 1's "10 of 8,896 groups"
(278 loads x 32 teams) holds at the same cut. 259 was ruled 2026-11-05 10:10 ET (15:10 UTC), before the next load
(2026-11-05T15:23:13Z), so its read could not have seen a later one. The cut is asserted from the rows (the cumulative
count), not assumed.

TEAMS: the throwaway DB holds no NFL team, so every team would be UNMAPPED and the observation `partial`. The fixture
seeds the NFL competition and one SYNTHETIC team per code the 2025 and 2026 files hold (TLAS below, the files' own 32
codes, read today), as tests/test_availability_nflverse.py's _teams does (teams.tla, the code sync-teams stores).
Whether the host's stored codes equal nflverse's is the first host read's to show (#841's ledger entry), not this
module's.
"""
from __future__ import annotations

import csv
import hashlib
import os
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import text

ENV = "NFLVERSE_REAL_DIR"
NAMES = {2025: "depth_charts_2025.csv", 2026: "depth_charts_2026.csv"}
REPO = Path(__file__).resolve().parents[1]

# ---- read 2026-11-07 (the files fetched that day from the release tag depth_charts) ---------------------------------
READ_ON = "2026-11-07"
SHA256 = {2025: "f5a4aa3fa70150e810b2255200c8735a6c1cc8ff77361308ce39149345b39b4a",      # CLOSED: a mismatch fails
          2026: "3bcc0c01d04cc7bbf7062659bcaa2700c26985954de26e41f4414a21ddf51ae2"}      # LIVE: as read today
SIZE = {2025: 52_917_870, 2026: 72_339_114}
# today's whole 2026 file (pinned only while its sha256 is today's)
TODAY_2026 = {"rows": 759_077, "loads": 283, "newest": datetime(2026, 11, 7, 13, 54, 10)}
# 259 item 1 / 262 item 5, as recorded in the repo (nflverse.py's docstring; #841's ledger entry and spec section 3)
REC_2025 = {"rows": 554_215, "loads": 221, "groups": 221 * 32, "first": datetime(2025, 8, 3, 10, 9, 7),
            "newest": datetime(2026, 3, 14, 7, 32, 9)}
REC_2026 = {"rows": 747_450, "loads": 278, "groups": 8_896, "under_40": 10, "first": datetime(2026, 3, 22, 6, 38, 42)}
CUT_2026 = datetime(2026, 11, 5, 7, 1, 33)      # THE CUT (module docstring): 747,450 rows through it, at load 278
NEXT_AFTER_CUT = datetime(2026, 11, 5, 15, 23, 13)
TLAS = ("ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
        "LA", "LAC", "LV", "MIA", "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS")
# 259 item 2(b) on CAR's 2-row group (259 item 1 read it): found in the 2026 file by reading it, the guard's count
CAR_PARTIAL = datetime(2026, 4, 10, 8, 19, 31)
# the partial-group guard's groups (dt, team, rows, previous complete group's rows) as the adapter counts them, read
# today on both files in order (2025, then 2026; the previous complete group carried across the files). The rule is
# 259 item 2(b)'s (fewer than HALF the team's previous complete group), not 259 item 1's descriptive "fewer than 40
# rows": all ten of 2026's groups under 40 are here, and two more (SEA 49 of 99, ARI 42 of 100) are under half
GUARD_2025 = [(datetime(2025, 12, 18, 7, 18, 49), "LAC", 8, 72)]
GUARD_2026_THROUGH_CUT = [
    (datetime(2026, 3, 27, 7, 58, 0), "PHI", 18, 75), (datetime(2026, 3, 27, 7, 58, 0), "SEA", 32, 81),
    (datetime(2026, 4, 10, 8, 19, 31), "CAR", 2, 78), (datetime(2026, 5, 1, 8, 57, 27), "CAR", 9, 86),
    (datetime(2026, 5, 1, 8, 57, 27), "DEN", 16, 86), (datetime(2026, 5, 24, 9, 18, 5), "SEA", 49, 99),
    (datetime(2026, 6, 11, 11, 20, 22), "NO", 27, 100), (datetime(2026, 6, 15, 13, 9, 41), "CHI", 5, 99),
    (datetime(2026, 7, 15, 9, 6, 57), "TB", 31, 98), (datetime(2026, 7, 22, 9, 23, 35), "IND", 28, 99),
    (datetime(2026, 7, 24, 9, 16, 54), "ARI", 42, 100), (datetime(2026, 10, 10, 13, 32, 40), "LAC", 22, 74)]
# BAL's QB1 (pos_abb QB, pos_rank 1, the 3WR 1TE group's slot 9): the load where each holder starts, read in the files
# with csv; one interval across the two files while the holder is unchanged. Only the instants are pinned (derived
# facts); the holders' espn_ids are compared against the csv census at run time, never committed
BAL_QB1_THROUGH_CUT = [datetime(2025, 8, 3, 10, 9, 7), datetime(2026, 11, 2, 17, 1, 29),
                       datetime(2026, 11, 5, 7, 1, 33)]
BAL_QB1_TODAY_AFTER_CUT = [datetime(2026, 11, 7, 7, 2, 5)]     # today's file only (its sha256)
ATTRIBUTION = "Depth charts: nflverse (CC BY 4.0)"


def _dir() -> Path | None:
    d = os.environ.get(ENV)
    return Path(d) if d else None


def _skip_reason() -> str | None:
    d = _dir()
    if d is None:
        return (f"{ENV} is unset: set it to a directory holding nflverse's depth_charts_2025.csv and "
                f"depth_charts_2026.csv (addendum 284 item 1(a); never downloaded by a test)")
    missing = [n for n in NAMES.values() if not (d / n).is_file()]
    if missing:
        return f"{ENV}={d} holds no {', '.join(missing)} (addendum 284 item 1(a); never downloaded by a test)"
    return None


pytestmark = pytest.mark.skipif(_skip_reason() is not None, reason=_skip_reason() or "")


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _utc(s: str) -> datetime:
    from datetime import timezone
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)


def _census(p: Path) -> dict:
    """The file read with csv alone (not the adapter): the counts the adapter's reading is compared with."""
    groups: Counter = Counter()
    blank_groups: Counter = Counter()
    rows = blank = 0
    qb1: dict = defaultdict(list)
    with open(p, newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        header = list(r.fieldnames or [])
        for row in r:
            rows += 1
            dt = _utc(row["dt"])
            groups[(dt, row["team"])] += 1
            if not row["espn_id"].strip():
                blank += 1
                blank_groups[(dt, row["team"])] += 1
            if row["team"] == "BAL" and row["pos_abb"] == "QB" and row["pos_rank"] == "1":
                qb1[dt].append(row["espn_id"])
    teams_per_load: Counter = Counter(dt for dt, _ in groups)
    return {"header": header, "rows": rows, "blank_espn": blank, "groups": groups, "blank_groups": blank_groups,
            "teams_per_load": teams_per_load,
            "loads": sorted(teams_per_load), "teams": sorted({t for _, t in groups}), "bal_qb1": dict(qb1)}


def _guard(censuses) -> list:
    """259 item 2(b) worked out from the csv censuses alone (not record.guard_load): the censuses in order (2025, then
    2026; the previous complete group carried across), each (dt, team) group in dt order. A group that lost a row with
    no espn_id is partial (the adapter's no_espn_groups, not listed here) and never a previous complete group; any
    other is partial when its rows are fewer than HALF the team's previous complete group's, else it becomes that
    team's previous complete group. Returns, per census, [(dt, team, rows, previous complete rows)] sorted."""
    last: dict = {}
    out = []
    for c in censuses:
        got = []
        for (dt, team) in sorted(c["groups"]):
            if c["blank_groups"].get((dt, team)):
                continue
            n, prev = c["groups"][(dt, team)], last.get(team)
            if prev is not None and 2 * n < prev:
                got.append((dt, team, n, prev))
            else:
                last[team] = n
        out.append(sorted(got))
    return out


def _seed_teams(tlas):
    """SYNTHETIC NFL teams, one per code (tests/test_availability_nflverse.py's _teams)."""
    from src.db.database import session_scope
    from src.db.schema import Competition, CompetitionTeam, Sport, Team
    with session_scope() as s:
        comp = Competition(sport=Sport.NFL, code="NFL", name="National Football League", area="USA", type="LEAGUE")
        s.add(comp)
        s.flush()
        for tla in tlas:
            t = Team(sport=Sport.NFL, name=f"Synthetic {tla}", tla=tla)
            s.add(t)
            s.flush()
            s.add(CompetitionTeam(competition_id=comp.id, team_id=t.id, season="2026"))


@pytest.fixture(scope="module")
def real(tmp_path_factory):
    """Both files hashed and censused, then ingested through the adapter (2025, then 2026) into a throwaway DB under
    the module's tmp directory; the payload directory there too. Yields what the tests read; nothing under data/."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import migrate_availability_record as mig
    import src.db.database as db
    from src.availability import nflverse as nv
    d = _dir()
    paths = {y: d / n for y, n in NAMES.items()}
    out = {"path": paths, "sha": {y: _sha(p) for y, p in paths.items()},
           "size": {y: p.stat().st_size for y, p in paths.items()},
           "census": {y: _census(p) for y, p in paths.items()}}
    out["guard"] = dict(zip((2025, 2026), _guard([out["census"][2025], out["census"][2026]])))
    tmp = tmp_path_factory.mktemp("nflverse-real")
    repo_data_existed = (REPO / "data").exists()
    mp = pytest.MonkeyPatch()
    eng = create_engine(f"sqlite:///{tmp / 'real.db'}", future=True)
    try:
        mp.setattr(db, "_engine", eng)
        mp.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True, expire_on_commit=False))
        mp.chdir(tmp)
        mp.setattr(nv, "PAYLOAD_BASE", tmp)
        db.init_db()
        assert mig.main() == 0
        _seed_teams(TLAS)
        out["ingest"] = {}
        for y in (2025, 2026):                    # the watermark is the source's: 2025 FIRST (259 item 2(c))
            out["ingest"][y] = nv.run(file=str(paths[y]))
        with eng.connect() as c:
            out["obs"] = {y: dict(c.execute(text(
                "SELECT id, status, payload_sha256, payload_path, rows_asserted, endpoint FROM "
                "availability_observations WHERE id = :i"), {"i": out["ingest"][y].observation_id}).mappings().one())
                for y in (2025, 2026)}
            out["groups"] = {}
            for y in (2025, 2026):
                got = c.execute(text(
                    "SELECT a.source_stamp, COUNT(*), COUNT(DISTINCT a.source_team), SUM(a.team_id IS NULL), "
                    "SUM(o.payload_sha256 IS NULL) FROM availability_assertions a JOIN availability_observations o "
                    "ON o.id = a.observation_id WHERE a.observation_id = :i GROUP BY a.source_stamp "
                    "ORDER BY a.source_stamp"), {"i": out["ingest"][y].observation_id}).all()
                out["groups"][y] = [(st if isinstance(st, datetime) else datetime.fromisoformat(str(st)), n, t, un,
                                     nohash) for st, n, t, un, nohash in got]
            out["kinds"] = dict(c.execute(text(
                "SELECT a.kind, COUNT(*) FROM availability_assertions a JOIN availability_observations o ON "
                "o.id = a.observation_id WHERE o.source = :s GROUP BY a.kind"), {"s": nv.SOURCE}).all())
            out["no_hash_rows"] = c.execute(text(
                "SELECT COUNT(*) FROM availability_assertions a JOIN availability_observations o ON "
                "o.id = a.observation_id WHERE o.source = 'nflverse_depth_charts' AND o.payload_sha256 IS NULL")
            ).scalar()
            out["kept"] = {y: _sha(tmp / out["obs"][y]["payload_path"]) for y in (2025, 2026)}
        out["tmp"] = tmp
        yield out
    finally:
        eng.dispose()
        mp.undo()
    assert not list(tmp.rglob("data")), "nothing under data/"
    assert (REPO / "data").exists() == repo_data_existed, "the repo's data/ untouched"


def _ro():
    """A read-only session on the module's throwaway DB (the module fixture's engine, patched in until its teardown)."""
    from src.db.database import readonly_scope
    return readonly_scope()


def _today(real, year) -> bool:
    return real["sha"][year] == SHA256[year]


# ---- the receipt (law 2): run with -s ------------------------------------------------------------------------------

def test_the_receipt_prints_each_files_sha256_and_counts(real):
    for y in (2025, 2026):
        c, ing, obs, groups = real["census"][y], real["ingest"][y], real["obs"][y], real["groups"][y]
        dist = Counter(t for _, _, t, _, _ in groups)
        hashed = sum(n for _, n, _, _, nohash in groups if not nohash)
        total = sum(n for _, n, _, _, _ in groups)
        same = "the sha256 read " + READ_ON if _today(real, y) else ("NOT the sha256 read " + READ_ON + " ("
                                                                       + SHA256[y][:16] + ")")
        print("")
        print(f"NFLVERSE REAL FILE {NAMES[y]}")
        print(f"  sha256 {real['sha'][y]} ({same})")
        print(f"  size {real['size'][y]:,} bytes · rows {c['rows']:,} · loads {len(c['loads'])} "
              f"(first {c['loads'][0].isoformat()}Z, newest {c['loads'][-1].isoformat()}Z) · teams {len(c['teams'])}")
        print(f"  adapter: rows read {ing.rows_read:,} · loads {ing.loads} (new {ing.new_loads}) · rows asserted "
              f"{ing.rows_asserted:,} · status {ing.status} · observation #{ing.observation_id}")
        print(f"  stored loads (one observation, one source_stamp): {len(groups)} · teams per load: "
              + ", ".join(f"{k} teams x {v}" for k, v in sorted(dist.items())))
        print(f"  payload hash: {hashed:,} of {total:,} stored rows carry it (observation payload_sha256 "
              f"{(obs['payload_sha256'] or 'NONE')[:16]}; the kept copy hashes to {real['kept'][y][:16]})")
        print(f"  rows with no espn_id: census {c['blank_espn']} · adapter {ing.no_espn_rows}")
        print(f"  header (as written): {', '.join(c['header'])}")
        print(f"  the guard from the csv rows alone: {len(real['guard'][y])} partial group(s) · the adapter's: "
              f"{len(ing.partial_groups)} · agree: {real['guard'][y] == ing.partial_groups}")
        if y == 2026:
            through = [g for g in groups if g[0] <= CUT_2026]
            print(f"  through THE CUT {CUT_2026.isoformat()}Z: loads {len(through)}, rows "
                  f"{sum(n for _, n, _, _, _ in through):,}, groups {sum(t for _, _, t, _, _ in through):,} "
                  f"(259 item 1: 278 loads, 8,896 groups; 262 item 5: 747,450 rows)")
            by_date = Counter(g[0].date().isoformat() for g in groups if g[0] > CUT_2026)
            print("  loads after THE CUT by dt date: " + (", ".join(f"{k} x {v}" for k, v in sorted(by_date.items()))
                                                          or "none"))
        print("  the adapter's receipt:")
        for line in ing.lines():
            print("    " + line.replace("\n", "\n    "))
    assert real["sha"][2025] == SHA256[2025], (
        f"the 2025 file (a CLOSED season) is not the one read {READ_ON}: sha256 {real['sha'][2025]}, not "
        f"{SHA256[2025]}; its pinned counts no longer describe it (a FINDING: nflverse rewrote a closed season)")


# ---- 252 item 6(d) on real rows: every column by its name ----------------------------------------------------------

def test_6d_the_real_headers_are_the_twelve_and_a_reordered_real_header_reads_the_same(real, tmp_path):
    from src.availability import nflverse as nv
    for y in (2025, 2026):                     # the adapter's rule: the twelve by name, each once, order not read
        h = real["census"][y]["header"]
        assert nv.header_refusal(h) is None and len(h) == 12 and sorted(h) == sorted(nv.COLUMNS), (y, h)
    # the first 3,000 real 2025 rows, columns written in reverse order (a throwaway copy under tmp_path, never kept)
    src = real["path"][2025]
    with open(src, newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        rows = [row for _, row in zip(range(3000), r)]
    p = tmp_path / "reordered.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(reversed(nv.COLUMNS)))
        w.writeheader()
        w.writerows(rows)
    got = nv.read_file(p)
    assert [dict(row) for _, row in got.rows] == [dict(row) for row in rows]
    assert [dt for dt, _ in got.rows] == [_utc(row["dt"]) for row in rows]


# ---- 259 item 2's counts --------------------------------------------------------------------------------------------

def test_2025_reproduces_259s_counts_exactly(real):
    if real["sha"][2025] != SHA256[2025]:
        pytest.fail(f"the 2025 file is not the one read {READ_ON} (sha256 {real['sha'][2025][:16]}, not "
                    f"{SHA256[2025][:16]}): a closed season's file changed, a FINDING")
    c, ing, groups = real["census"][2025], real["ingest"][2025], real["groups"][2025]
    assert (c["rows"], len(c["loads"]), c["loads"][0], c["loads"][-1]) == (
        REC_2025["rows"], REC_2025["loads"], REC_2025["first"], REC_2025["newest"])
    assert (ing.rows_read, ing.loads, ing.new_loads, ing.rows_asserted, ing.old_rows) == (
        554_215, 221, 221, 554_215, 0)
    assert (ing.status, ing.unmapped_teams, ing.watermark, ing.refused) == ("complete", {}, None, None)
    assert len(groups) == 221 and sum(t for _, _, t, _, _ in groups) == REC_2025["groups"]
    assert {t for _, _, t, _, _ in groups} == {32}                       # 259 item 1: every load 32 teams
    assert sum(un for _, _, _, un, _ in groups) == 0                     # every team mapped (the seeded codes)
    assert c["teams"] == list(TLAS)


def test_2026_reproduces_259s_counts_through_the_cut(real):
    """259 item 1 / 262 item 5 at THE CUT (module docstring): asserted on every read, the live file's growth after it
    aside. The cut is checked from the rows: 747,450 rows through it, at the 278th load."""
    c, ing, groups = real["census"][2026], real["ingest"][2026], real["groups"][2026]
    through = [g for g in groups if g[0] <= CUT_2026]
    assert len(through) == REC_2026["loads"] and through[-1][0] == CUT_2026 and through[0][0] == REC_2026["first"]
    assert sum(n for _, n, _, _, _ in through) == REC_2026["rows"]           # 262 item 5's 747,450
    assert sum(t for _, _, t, _, _ in through) == REC_2026["groups"]         # 259 item 1's 8,896 groups
    under_40 = [(dt, team) for (dt, team), n in c["groups"].items() if dt <= CUT_2026 and n < 40]
    assert len(under_40) == REC_2026["under_40"]                               # "10 of 8,896 groups [...] fewer than 40"
    later = [g[0] for g in groups if g[0] > CUT_2026]
    assert not later or later[0] >= NEXT_AFTER_CUT                             # nothing between 259's read and the next
    # the adapter's reading of the whole file (whatever its growth): every row asserted after 2025's watermark
    assert (ing.rows_read, ing.loads, ing.new_loads, ing.rows_asserted, ing.old_rows) == (
        c["rows"], len(c["loads"]), len(c["loads"]), c["rows"], 0)
    assert ing.watermark == REC_2025["newest"] and (ing.status, ing.unmapped_teams) == ("complete", {})
    short = [(st.isoformat() + "Z", t) for st, _, t, _, _ in groups if t != 32]
    assert not short, f"FINDING (to be ruled before any fix): 2026 load(s) not 32 teams: {short}"   # every read
    assert sum(un for _, _, _, un, _ in groups) == 0 and c["teams"] == list(TLAS)


def test_2026_todays_whole_file(real):
    if not _today(real, 2026):
        pytest.skip(f"the 2026 file (LIVE) is not the one read {READ_ON} (sha256 {real['sha'][2026][:16]}, not "
                    f"{SHA256[2026][:16]}): today's whole-file counts not compared; 259's are, at THE CUT")
    c, ing = real["census"][2026], real["ingest"][2026]
    assert real["size"][2026] == SIZE[2026]
    assert (c["rows"], len(c["loads"]), c["loads"][-1]) == (TODAY_2026["rows"], TODAY_2026["loads"],
                                                            TODAY_2026["newest"])
    assert (ing.rows_read, ing.loads, ing.rows_asserted) == (TODAY_2026["rows"], TODAY_2026["loads"],
                                                             TODAY_2026["rows"])


# ---- the payload hash on every snapshot load -------------------------------------------------------------------------

def test_every_stored_load_carries_its_files_payload_hash(real):
    """One --file run, one observation (252 item 3(a)): its payload_sha256 is the file's sha256 and the kept copy
    hashes to it; every stored row of the source belongs to an observation that keeps it and is of the source's
    snapshot kind (record.SNAPSHOT_SOURCES), the two halves of record.snapshot_load's rule, so every (observation,
    source_stamp) group is a LOAD by it (262 item 1: the hash is the load's identity)."""
    from src.availability import nflverse as nv
    from src.availability import record as rec
    assert real["no_hash_rows"] == 0
    assert rec.SNAPSHOT_SOURCES.get(nv.SOURCE) == nv.KIND
    assert real["kinds"] == {nv.KIND: real["ingest"][2025].rows_asserted + real["ingest"][2026].rows_asserted}
    for y in (2025, 2026):
        obs = real["obs"][y]
        assert obs["payload_sha256"] == real["sha"][y] == real["kept"][y], y
        assert obs["endpoint"] == f"file:{NAMES[y]}" and obs["rows_asserted"] == real["ingest"][y].rows_asserted
        assert all(nohash == 0 for _, _, _, _, nohash in real["groups"][y]), y


def test_rows_with_no_espn_id_are_none_in_either_file(real):
    """262 item 5 recorded 0 blank espn_id in both files; the adapter's guard counts the same on today's files."""
    for y in (2025, 2026):
        ing = real["ingest"][y]
        assert real["census"][y]["blank_espn"] == ing.no_espn_rows == 0 and ing.no_espn_groups == [], (
            f"FINDING (to be ruled before any fix): {y} rows with no espn_id: census "
            f"{real['census'][y]['blank_espn']}, "
            f"adapter {ing.no_espn_rows}, groups {ing.no_espn_groups}")
        assert "  rows with no espn_id: 0, refused" in "\n".join(ing.lines())
    assert real["ingest"][2026].lines()[-1] == ATTRIBUTION


# ---- 259 item 2(b) on CAR's 2-row group ------------------------------------------------------------------------------

def test_259_2b_cars_2_row_group_is_counted_by_the_guard_and_closes_nothing(real):
    from src.availability import record as rec
    c, ing = real["census"][2026], real["ingest"][2026]
    assert c["groups"][(CAR_PARTIAL, "CAR")] == 2                               # found in the file, read with csv
    car = [g for g in ing.partial_groups if g[1] == "CAR" and g[0] == CAR_PARTIAL]
    assert len(car) == 1 and car[0][2] == 2, ing.partial_groups
    # the guard worked out from the csv rows alone (_guard) against the adapter's reading, both files
    for y in (2025, 2026):
        assert real["ingest"][y].partial_groups == real["guard"][y], (
            f"FINDING (to be ruled before any fix): {y} the adapter's partial groups differ from the csv rows' "
            f"half rule: adapter {real['ingest'][y].partial_groups}, csv {real['guard'][y]}")
    # the dated pins (read 2026-11-07)
    assert real["ingest"][2025].partial_groups == GUARD_2025
    assert [g for g in ing.partial_groups if g[0] <= CUT_2026] == GUARD_2026_THROUGH_CUT
    if _today(real, 2026):
        assert ing.partial_groups == GUARD_2026_THROUGH_CUT                     # none after THE CUT in today's file
    # 259 item 1's descriptive "fewer than 40 rows" groups through THE CUT are all among the guard's
    under_40 = {(dt, team) for (dt, team), k in c["groups"].items() if dt <= CUT_2026 and k < 40}
    assert len(under_40) == REC_2026["under_40"]
    assert under_40 <= {(dt, team) for dt, team, _, _ in ing.partial_groups}, under_40
    n = len(ing.partial_groups) + len(ing.no_espn_groups)                       # the adapter's own count (lines())
    assert f"  partial team groups: {n}, closing nothing" in "\n".join(ing.lines())
    loads = c["loads"]
    before, after = loads[loads.index(CAR_PARTIAL) - 1], loads[loads.index(CAR_PARTIAL) + 1]
    with _ro() as s:
        held = {f.interval.first.id for f in rec.as_of(s, "nfl", before, "source", team="CAR")}
        at = {f.interval.first.id for f in rec.as_of(s, "nfl", CAR_PARTIAL, "source", team="CAR")}
        nxt = rec.as_of(s, "nfl", after, "source", team="CAR")
    assert held and held <= at                                                  # the partial group closed nothing
    assert len(at - held) <= 2                                                  # at most its own 2 rows opened
    assert len(nxt) == c["groups"][(after, "CAR")]                              # the next complete load: its chart


# ---- 252 item 6(g) on real rows: BAL's QB1 flips ---------------------------------------------------------------------

def test_6g_bals_qb1_intervals_are_the_flips_the_file_shows(real):
    """BAL's QB1 (pos_abb QB, pos_rank 1) under the source clock: the derived intervals of that slot start exactly at
    the loads where the files (read with csv) change its holder, each held by that load's espn_id."""
    from src.availability import record as rec
    qb1 = {**real["census"][2025]["bal_qb1"], **real["census"][2026]["bal_qb1"]}
    assert all(len(v) == 1 for v in qb1.values())                               # one QB1 per load
    flips, prev = [], None
    for dt in sorted(qb1):
        if qb1[dt][0] != prev:
            flips.append((dt, qb1[dt][0]))
        prev = qb1[dt][0]
    newest = max(qb1)
    with _ro() as s:
        hist = rec.history(s, "nfl", newest, "source", team="BAL")
    ivs = {}
    for r, iv in hist:
        if r.attrs.get("pos_abb") == "QB" and str(r.attrs.get("pos_rank")) == "1":
            ivs[id(iv)] = iv
    got = sorted((iv.start, iv.first.source_player_id) for iv in ivs.values())
    assert got == flips
    ends = sorted((iv.start, iv.end) for iv in ivs.values())
    assert [e for _, e in ends[:-1]] == [st for st, _ in ends[1:]] and ends[-1][1] is None
    assert [dt for dt, _ in flips if dt <= CUT_2026] == BAL_QB1_THROUGH_CUT
    if _today(real, 2026):
        assert [dt for dt, _ in flips] == BAL_QB1_THROUGH_CUT + BAL_QB1_TODAY_AFTER_CUT
