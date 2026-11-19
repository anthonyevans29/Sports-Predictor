"""THE BY-ID VENUE RECEIPT (ARCHITECT 2026-11-19, addendum 433 item 4): "For every venue id stored on a copy (--db
COPY, 346's fence [...]): the provider's answer by id, one call each, the answers kept under logs/, a call cap,
resumable from the kept answers. It prints counts: ids whose by-id country agrees with the stored country, differs, or
is not served; and for each id that differs, its stored games by home country with the flag now and the flag under the
by-id country, the cohort fixtures among them named. It reads no score and no result, writes no row, and prints no
log-loss."

Pins, on a throwaway DB and a .backup copy of it (the provider faked; every id synthetic): the four counts; a differing
id's games by home country, the flag now and under the by-id country, a cohort fixture named; the answers kept before
use and replayed (no second call); the cap stops the run (exit 3) and a re-run continues; a failed call stops where it
failed and keeps what was kept; --plan calls nothing; the saved fixtures' own grounds (433 item 1(e)); data/ refused;
the copy byte for byte; the module reads no score and no result."""
import inspect
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from src.ingestion import intl_venue_by_id as vb


@pytest.fixture
def world(tmp_path, monkeypatch):
    """(copy, ids). Stored rows as intl-venue-sync's dictionary leaves them (433 item 1(d)'s shapes, synthetic ids)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db
    from src.db.schema import Competition, IntlMatchVenue, Match, MatchStatus, Sport, Team

    f = tmp_path / "w.db"
    eng = create_engine(f"sqlite:///{f}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True))
    db.init_db()
    ids = {}
    with db.session_scope() as s:
        c = Competition(sport=Sport.SOCCER, code="FRIENDLIES_INT", name="F", area="I", type="INTL")
        s.add(c)
        s.flush()
        teams = {}
        rows = [("cr1", "Costa Rica", 9392, "USA", True), ("cr2", "Costa Rica", 9392, "USA", True),
                ("chi", "Chile", 9316, "Spain", True),          # the cohort fixture, at a differing id
                ("esp", "Spain", 9501, "Spain", False),         # agrees
                ("ns", "Peru", 9777, "Peru", False),            # not served by id
                ("sev", "Peru", 9900, "Peru", False)]           # served under two countries by id
        for i, (key, home, vid, vc, flag) in enumerate(rows):
            for a in (home, "Away"):
                if a not in teams:
                    teams[a] = Team(sport=Sport.SOCCER, name=a, area=a)
                    s.add(teams[a])
            s.flush()
            m = Match(sport=Sport.SOCCER, competition_id=c.id, season="2026", utc_date=datetime(2026, 10, 1 + i),
                      status=MatchStatus.FINISHED, home_team_id=teams[home].id, away_team_id=teams["Away"].id,
                      home_score=1, away_score=0)
            s.add(m)
            s.flush()
            ids[key] = m.id
            s.add(IntlMatchVenue(match_id=m.id, venue_id=vid, venue_country=vc, home_country=home, neutral_v3=flag,
                                 rule="r"))
    copy = tmp_path / "copy" / "sports.db"
    copy.parent.mkdir()
    a, b = sqlite3.connect(str(f)), sqlite3.connect(str(copy))
    try:
        a.backup(b)
    finally:
        b.close()
        a.close()
    monkeypatch.setattr(vb, "cohort_ids", lambda: ({ids["chi"]}, "frozen (1 ids)"))
    return copy, ids


BY_ID = {9392: [{"id": 9392, "name": "G392", "city": "San Jose", "country": "Costa Rica", "capacity": 1}],
         9316: [{"id": 9316, "name": "G316", "city": "Santiago", "country": "Chile"}],
         9501: [{"id": 9501, "name": "G501", "city": "Madrid", "country": "Spain"}],
         9777: [],
         9900: [{"id": 9900, "name": "A", "city": "X", "country": "Peru"},
                {"id": 9900, "name": "B", "city": "Y", "country": "Chile"}]}


class Provider:
    calls: list = []

    def __init__(self, *a, **k):
        pass

    def _get(self, path, params):
        Provider.calls.append((path, params))
        if Provider.fail_on == params["id"]:
            raise RuntimeError("HTTP 500")
        return {"response": BY_ID[params["id"]]}


@pytest.fixture
def provider(monkeypatch):
    Provider.calls, Provider.fail_on = [], None
    monkeypatch.setattr(vb, "_client", Provider)
    return Provider


def _run(args):
    from click.testing import CliRunner

    from cli import cli
    return CliRunner().invoke(cli, ["intl-venue-by-id", *args])


def test_the_counts_the_differing_ids_and_the_copy_byte_for_byte(world, provider, tmp_path):
    from src.walters import intl_shadow as us
    copy, ids = world
    out_dir = tmp_path / "logs" / "venue_by_id"
    sha = us.copy_sha256(copy)
    out = _run(["--db", str(copy), "--out-dir", str(out_dir)])
    assert out.exit_code == 0, out.output
    L = out.output.splitlines()
    assert L[0].startswith(f"--db {copy.resolve()} · sha256 {sha} · a .backup copy, opened mode=ro&immutable=1")
    assert L[1] == (f"INTL-VENUE-BY-ID ({vb.RULING}) · read-only: no score, no result, no row written, no log-loss · "
                    "COMPLETE · the confirmation cohort: frozen (1 ids)")
    assert L[2] == (f"  stored venue ids on the copy 5 (rows with a venue id 6) · answers kept under {out_dir}: 0 "
                    "before this run · provider calls this run 5 (cap 700)")
    assert ("  by-id country: agrees 1 · differs 2 · stored country unknown 0 · served without a country 0 · not "
            "served 1 · served under more than one country 1 · not yet asked 0") in L
    assert "  keys served by id (law 1): capacity, city, country, id, name" in L
    assert (f"  games whose known flag flips under the by-id country: 3 · games whose unknown flag becomes known: 0 · "
            f"cohort fixtures at those ids: 1 — {ids['chi']}") in L
    assert "    venue 9392: stored USA -> by id Costa Rica (G392, San Jose) · 2 stored games" in L
    assert "      home Costa Rica: 2 · flag now neutral 2 · under the by-id country home 2" in L
    assert f"      home Chile: 1 · flag now neutral 1 · under the by-id country home 1 · COHORT {ids['chi']}" in L
    assert "  SERVED UNDER MORE THAN ONE COUNTRY (1): 9900 (Chile, Peru)" in L
    assert "  NOT SERVED BY ID (1): 9777" in L
    assert not any("log-loss " in x and "no log-loss" not in x for x in L)
    assert sorted(p.name for p in out_dir.iterdir()) == [f"venue_id_{v}.json" for v in (9316, 9392, 9501, 9777, 9900)]
    assert us.copy_sha256(copy) == sha and not us.copy_sidecars(copy)       # nothing written to the copy


def test_kept_answers_are_replayed_with_no_call(world, provider, tmp_path):
    copy, _ = world
    out_dir = tmp_path / "kept"
    first = _run(["--db", str(copy), "--out-dir", str(out_dir)])
    n = len(provider.calls)
    again = _run(["--db", str(copy), "--out-dir", str(out_dir)])
    assert again.exit_code == 0 and len(provider.calls) == n == 5
    assert ("answers kept under " + str(out_dir) + ": 5 before this run · provider calls this run 0") in again.output
    assert first.output.split("\n", 3)[3] == again.output.split("\n", 3)[3]          # the same receipt after the head


def test_the_cap_stops_the_run_and_a_re_run_continues(world, provider, tmp_path):
    copy, _ = world
    out_dir = tmp_path / "capped"
    out = _run(["--db", str(copy), "--out-dir", str(out_dir), "--max-calls", "2"])
    assert out.exit_code == 3 and "INCOMPLETE: 3 ids not yet asked" in out.output
    assert "  STOPPED: the call cap (2) reached; re-run to continue from the kept answers" in out.output.splitlines()
    assert len(provider.calls) == 2 and len(list(out_dir.iterdir())) == 2
    out = _run(["--db", str(copy), "--out-dir", str(out_dir)])
    assert out.exit_code == 0 and "COMPLETE" in out.output and len(provider.calls) == 5   # only the three left


def test_a_failed_call_stops_where_it_failed_and_keeps_what_was_kept(world, provider, tmp_path):
    copy, _ = world
    provider.fail_on = 9501
    out_dir = tmp_path / "failed"
    out = _run(["--db", str(copy), "--out-dir", str(out_dir)])
    assert out.exit_code == 3
    assert "  STOPPED: the call for venue 9501 failed (RuntimeError: HTTP 500); re-run to continue" in out.output
    assert sorted(p.name for p in out_dir.iterdir()) == ["venue_id_9316.json", "venue_id_9392.json"]


def test_plan_calls_nothing(world, provider, tmp_path):
    copy, _ = world
    out = _run(["--db", str(copy), "--out-dir", str(tmp_path / "p"), "--plan"])
    assert out.exit_code == 0 and provider.calls == [] and not (tmp_path / "p").exists()
    assert out.output.splitlines()[-1] == (f"INTL-VENUE-BY-ID ({vb.RULING}) · PLAN, nothing called · stored venue ids 5 "
                                           f"· answers kept under {tmp_path / 'p'} 0 · calls needed 5 (cap 700)")


def test_the_saved_fixtures_name_the_grounds_of_an_id(world, provider, tmp_path):
    """433 item 1(e): "in this endpoint an id is not always one ground"; the saved fixtures' own venue object shows it."""
    copy, _ = world
    save = tmp_path / "save"
    save.mkdir()
    (save / "fixtures_10_2026.json").write_text(json.dumps({"response": [
        {"fixture": {"id": 1, "venue": {"id": 9392, "name": "G392", "city": "San Jose"}}},
        {"fixture": {"id": 2, "venue": {"id": 9392, "name": "Other", "city": "Miami"}}},
        {"fixture": {"id": 3, "venue": {"id": 9316, "name": "G316", "city": "Santiago"}}}]}))
    out = _run(["--db", str(copy), "--out-dir", str(tmp_path / "f"), "--fixtures-dir", str(save)])
    assert out.exit_code == 0, out.output
    L = out.output.splitlines()
    assert "  saved fixtures read: 1 files, 3 fixtures with a venue id" in L
    assert "  stored ids the saved fixtures name under two or more grounds: 1 — 9392" in L
    assert "      the saved fixtures name it: G392, San Jose; Other, Miami" in L
    assert "      the saved fixtures name it: G316, Santiago" in L


def test_refusals_data_dir_and_missing_copy_nothing_called(world, provider, tmp_path):
    with pytest.raises(vb.ByIdRefused, match="under data/"):
        vb.check_out_dir(tmp_path / "data" / "x", data_dirs=[tmp_path / "data"])
    (tmp_path / "data").mkdir()
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "data" / "backups").symlink_to(tmp_path / "elsewhere")          # a folder data/ links to
    with pytest.raises(vb.ByIdRefused, match="a folder data/ links to"):
        vb.check_out_dir(tmp_path / "elsewhere" / "x", data_dirs=[tmp_path / "data"])
    assert vb.check_out_dir(tmp_path / "logs" / "x", data_dirs=[tmp_path / "data"]) == tmp_path / "logs" / "x"
    out = _run(["--db", str(tmp_path / "missing.db"), "--out-dir", str(tmp_path / "o")])
    assert out.exit_code == 2 and out.output.startswith("REFUSED:") and provider.calls == []
    assert not (tmp_path / "missing.db").exists()


def test_the_receipt_reads_no_score_and_no_result():
    src = inspect.getsource(vb)
    for word in ("home_score", "away_score", "score_90", "result_90", "outcome", "ll3", "log_loss"):
        assert word not in src, word
    assert "from src.db.schema import IntlMatchVenue" in src and "Match," not in src


def _classify(stored, answers, cohort=None):
    return vb.classify(stored, {"answers": answers, "not_asked": [], "calls": 0, "kept_before": 0, "stopped": None},
                       cohort)


def test_a_stored_country_unknown_is_its_own_count_never_a_disagreement():
    """Law 4: an id intl-venue-sync stored with no country (no /venues?country answer listed it) is labelled, never
    read as "differs"; its unknown flags becoming known are counted apart from known flags that flip (my review, P2)."""
    stored = {1: [(10, None, "Spain", None)], 2: [(20, "France", "France", False)],
              3: [(30, "USA", "Costa Rica", True)]}
    answers = {1: {"response": [{"id": 1, "country": "Spain"}]}, 2: {"response": [{"id": 2, "country": "France"}]},
               3: {"response": [{"id": 3, "country": "Costa Rica"}]}}
    r = _classify(stored, answers)
    assert r["agrees"] == [2] and [d["venue_id"] for d in r["differs"]] == [3]
    assert [d["venue_id"] for d in r["stored_unknown"]] == [1]
    assert r["games_flipping"] == 1 and r["games_unknown_to_known"] == 1
    text = "\n".join(vb.lines(r, {"kept_before": 0, "calls": 0, "stopped": None}, "o", 700, "frozen (0 ids)"))
    assert "differs 1 · stored country unknown 1 ·" in text
    assert "  STORED COUNTRY UNKNOWN (1; no /venues?country answer listed the id):" in text
    assert "    venue 1: stored unknown -> by id Spain" in text


def test_an_id_served_without_a_country_is_not_not_served():
    stored = {4: [(40, "Peru", "Peru", False)], 5: [(50, "Peru", "Peru", False)]}
    answers = {4: {"response": [{"id": 4, "country": None, "name": "X", "city": "Lima"}]}, 5: {"response": []}}
    r = _classify(stored, answers)
    assert r["served_no_country"] == [4] and r["not_served"] == [5]
    text = "\n".join(vb.lines(r, {"kept_before": 0, "calls": 0, "stopped": None}, "o", 700, "frozen (0 ids)"))
    assert "  SERVED BY ID WITHOUT A COUNTRY (1): 4" in text and "  NOT SERVED BY ID (1): 5" in text


def test_a_cohort_not_read_is_said_never_a_measured_zero():
    stored = {3: [(30, "USA", "Costa Rica", True)]}
    r = _classify(stored, {3: {"response": [{"id": 3, "country": "Costa Rica"}]}}, cohort=None)
    text = "\n".join(vb.lines(r, {"kept_before": 0, "calls": 0, "stopped": None}, "o", 700,
                              "not read: RegistryError: x"))
    assert "cohort fixtures at those ids: NOT READ (not read: RegistryError: x)" in text
    assert "cohort fixtures at those ids: 0" not in text


def test_a_wrong_fixtures_dir_is_refused_before_any_call(world, provider, tmp_path):
    copy, _ = world
    empty = tmp_path / "empty_save"
    empty.mkdir()
    for d, why in ((tmp_path / "nowhere", "not a directory"), (empty, "no fixtures_\\*.json")):
        out = _run(["--db", str(copy), "--out-dir", str(tmp_path / "o"), "--fixtures-dir", str(d)])
        assert out.exit_code == 2 and "REFUSED: --fixtures-dir" in out.output, out.output
    assert provider.calls == [] and not (tmp_path / "o").exists()


def test_a_zero_cap_asks_nothing_and_needs_no_provider(world, monkeypatch, tmp_path):
    """Codex on #1057 (P2): --max-calls 0 with ids to ask is an incomplete run (exit 3), never a refusal for want of a
    provider key; the client is not even constructed."""
    copy, _ = world

    def no_provider():
        raise ValueError("API_FOOTBALL_KEY is not set")

    monkeypatch.setattr(vb, "_client", no_provider)
    out = _run(["--db", str(copy), "--out-dir", str(tmp_path / "z"), "--max-calls", "0"])
    assert out.exit_code == 3, out.output
    assert "INCOMPLETE: 5 ids not yet asked" in out.output and "STOPPED: the call cap (0) reached" in out.output


def test_a_failed_write_leaves_no_partial_answer(world, provider, monkeypatch, tmp_path):
    """Codex on #1057 (P2): a write that fails part-way leaves nothing at the answer's path, so a re-run asks again."""
    copy, _ = world
    out_dir = tmp_path / "w"
    real = Path.write_text

    def half_then_fail(self, data, *a, **k):
        if self.name == "venue_id_9501.json.part":
            real(self, data[:5], *a, **k)                                      # a partial file on disk, then
            raise OSError(28, "No space left on device")                       # the disk fills
        return real(self, data, *a, **k)

    monkeypatch.setattr(Path, "write_text", half_then_fail)
    out = _run(["--db", str(copy), "--out-dir", str(out_dir)])
    assert out.exit_code == 3 and "the answer for venue 9501 could not be kept" in out.output
    assert sorted(p.name for p in out_dir.iterdir()) == ["venue_id_9316.json", "venue_id_9392.json"]
    monkeypatch.setattr(Path, "write_text", real)
    again = _run(["--db", str(copy), "--out-dir", str(out_dir)])
    assert again.exit_code == 0 and "COMPLETE" in again.output                 # 9501 asked again, nothing partial read
