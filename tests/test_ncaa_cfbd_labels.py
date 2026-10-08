"""NCAA CFBD label lane (ARCHITECT 2026-10-07, data lane): the join (same /
swapped, exact before substring, ambiguity refused), the neutral flag carried,
score-reversed rows taking the source's scores with a listed reason, the pinned
alias map (exact wins, 0 / >1 targets refused, unmatched counted), the matches
table untouched, --dry-run writes nothing, the key never printed, the payload
under the save dir, and the stream read (side table where present, matches row
otherwise, uncovered share per season). Synthetic CFBD-shaped records only;
the API is never reached."""
import dataclasses
import json
from datetime import datetime
from types import SimpleNamespace

import pytest
from click.testing import CliRunner
from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, NCAACFBDLabel, Sport, Team
from src.ingestion import ncaa_cfbd as nc
from src.walters import ncaa_backtest as nb

SENTINEL = "SENTINEL-CFBD-KEY-8c1f0e"


def rec(gid, home, away, hp, ap, start, neutral=False, hc="fbs", ac="fbs", **kw):
    return {"id": gid, "season": 2083, "seasonType": "regular", "startDate": start, "completed": True,
            "neutralSite": neutral, "homeTeam": home, "homeClassification": hc, "homePoints": hp,
            "awayTeam": away, "awayClassification": ac, "awayPoints": ap, **kw}


TEAMS = ("Cfbd A", "Cfbd B", "Cfbd C", "Cfbd D", "Cfbd E", "Cfbd F", "Cfbd G", "Cfbd H",
         "Cfbd Twin", "Cfbd Twin.", "Cfbd K")

RECS = [
    rec(9001, "Cfbd A", "Cfbd B", 31, 10, "2083-09-06T19:00:00.000Z"),                  # same, agree
    rec(9002, "Cfbd D", "Cfbd C", 28, 14, "2083-09-06T23:00:00.000Z", neutral=True),     # swapped, neutral
    rec(9003, "Cfbd E", "Cfbd F", 20, 17, "2083-09-13T19:00:00.000Z"),                  # ours 17-20: reversed
    rec(9004, "Gee State", "Cfbd H", 30, 3, "2083-09-13T23:00:00.000Z"),                # via alias -> Cfbd G
    rec(9005, "Nowhere U", "Cfbd A", 7, 3, "2083-09-20T19:00:00.000Z"),                 # unmatched
    rec(9006, "Cfbd Twin", "Cfbd K", 21, 7, "2083-09-20T19:00:00.000Z"),                # 2 of ours fit: refused
    rec(9007, "Cfbd A", "FCS Team", 50, 0, "2083-09-27T19:00:00.000Z", ac="fcs"),       # not both FBS
    rec(9008, "Cfbd B", "Cfbd E", None, None, "2083-12-01T19:00:00.000Z", completed=False),
]
ALIASES = {"Gee State": "Cfbd G",          # usable
           "Zero Tech": "Nobody At All",   # 0 targets -> refused
           "Twin U": "Cfbd Twin",          # 2 targets ('Cfbd Twin' / 'Cfbd Twin.') -> refused
           "Cfbd A": "Cfbd B"}             # shadowed: exact match exists -> refused, never applied


def world() -> dict:
    """Our NCAA matches for 2083 (idempotent across tests: built once)."""
    init_db()
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == "NCAA")).scalars().first()
        if comp is None:
            comp = Competition(sport=Sport.NFL, code="NCAA", name="NCAA", area="USA", type="LEAGUE")
            s.add(comp)
            s.flush()
        existing = {t.name: t for t in s.execute(select(Team).where(Team.name.in_(TEAMS))).scalars()}
        if len(existing) == len(TEAMS):
            ids = {m.utc_date: m.id for m in s.execute(select(Match).where(Match.season == "2083")).scalars()}
            return {"teams": {n: t.id for n, t in existing.items()}, "matches": ids}
        t = {}
        for n in TEAMS:
            t[n] = Team(sport=Sport.NFL, name=n)
            s.add(t[n])
        s.flush()

        def mk(h, a, d, hs, as_):
            m = Match(sport=Sport.NFL, competition_id=comp.id, season="2083", utc_date=d,
                      status=MatchStatus.FINISHED, home_team_id=t[h].id, away_team_id=t[a].id,
                      home_score=hs, away_score=as_, stage="Regular Season")
            s.add(m)
            return m

        ms = [mk("Cfbd A", "Cfbd B", datetime(2083, 9, 6, 19), 31, 10),
              mk("Cfbd C", "Cfbd D", datetime(2083, 9, 6, 23), 14, 28),
              mk("Cfbd E", "Cfbd F", datetime(2083, 9, 13, 19), 17, 20),
              mk("Cfbd G", "Cfbd H", datetime(2083, 9, 13, 23), 30, 3),
              mk("Cfbd Twin", "Cfbd K", datetime(2083, 9, 20, 19), 21, 7),
              mk("Cfbd Twin.", "Cfbd K", datetime(2083, 9, 20, 20), 21, 7)]
        s.flush()
        return {"teams": {n: x.id for n, x in t.items()}, "matches": {m.utc_date: m.id for m in ms}}


def _match_snapshot(ids):
    cols = [c.name for c in Match.__table__.columns]
    with session_scope() as s:
        rows = s.execute(select(Match).where(Match.id.in_(ids))).scalars().all()
        return {m.id: tuple(getattr(m, c) for c in cols) for m in rows}


def _labels(ids):
    with session_scope() as s:
        return {r.match_id: {c.name: getattr(r, c.name) for c in NCAACFBDLabel.__table__.columns}
                for r in s.execute(select(NCAACFBDLabel).where(NCAACFBDLabel.match_id.in_(ids))).scalars()}


@pytest.fixture
def pinned(tmp_path, monkeypatch):
    p = tmp_path / "aliases.json"
    p.write_text(json.dumps({"aliases": ALIASES}))
    monkeypatch.setattr(nc, "ALIAS_FILE", p)
    return p


def _build():
    w = world()
    keys, missing = nc.discover(RECS[0])
    assert missing == []
    with session_scope() as s:
        teams = nc.ncaa_teams(s)
        ours = nc.load_ours(s, datetime(2083, 9, 1), datetime(2083, 12, 31), teams)
        r = nc.build_labels(RECS, keys, ours, teams, ALIASES, 2083, "fbs")
        s.rollback()
    return w, r


# --- the join ------------------------------------------------------------------

def test_join_orientation_neutral_scores_aliases_and_refusals():
    w, r = _build()
    c = r.counts
    mid = w["matches"]
    by = {row["match_id"]: row for row in r.rows}
    assert c["records"] == 8 and c["completed_in_scope"] == 6
    assert c["source_not_completed"] == 1 and c["source_not_both_fbs"] == 1
    assert (c["joined"], c["joined_same"], c["joined_swapped"]) == (4, 3, 1)
    assert (c["unmatched"], c["ambiguous_refused"]) == (1, 1)
    # same orientation, scores agree, not neutral; exact match wins over the shadowing alias
    a = by[mid[datetime(2083, 9, 6, 19)]]
    assert (a["orientation"], a["neutral"], a["home_score"], a["away_score"], a["join_via"]) == \
        ("same", False, 31, 10, "exact")
    assert a["correction_reason"] is None and a["source_game_id"] == 9001 and a["season"] == "2083"
    # swapped: stored scores are the SOURCE's in OUR orientation (our home C scored 14)
    b = by[mid[datetime(2083, 9, 6, 23)]]
    assert (b["orientation"], b["neutral"], b["home_score"], b["away_score"]) == ("swapped", True, 14, 28)
    assert b["source_home_team"] == "Cfbd D" and c["neutral"] == 1
    # score-reversed: the side table carries CFBD's scores and the row is listed with its reason
    e = by[mid[datetime(2083, 9, 13, 19)]]
    assert (e["home_score"], e["away_score"]) == (20, 17)
    assert e["correction_reason"].startswith("score-reversed: provider home/away scores swapped vs CFBD")
    assert c["score_reversed"] == 1 and len(r.corrections) == 1 and str(e["match_id"]) in r.corrections[0]
    # alias
    g = by[mid[datetime(2083, 9, 13, 23)]]
    assert g["join_via"] == "alias" and g["orientation"] == "same" and c["join_via_alias"] == 1
    # the refused aliases, each with its reason
    why = {src: reason for src, _, reason in r.alias_refused}
    assert r.aliases_usable == 1
    assert why["Zero Tech"] == "target names 0 of our NCAA teams"
    assert why["Twin U"].startswith("target names 2 of our NCAA teams")
    assert why["Cfbd A"].startswith("shadowed")
    # ambiguity refused (two of ours fit), never guessed; the twins get no row
    assert mid[datetime(2083, 9, 20, 19)] not in by and mid[datetime(2083, 9, 20, 20)] not in by
    assert "refused, never guessed" in r.ambiguous[0]
    # unmatched counted, the unknown name listed (the known one is not)
    assert r.unmatched_names == {"Nowhere U": 1}
    lines = "\n".join(nc.receipt_lines(r))
    assert "both-FBS completed 6 · joined 4" in lines and "unmatched 1 · ambiguous-refused 1" in lines
    assert "score-reversed 1" in lines and "REFUSED alias 'Zero Tech'" in lines and "Nowhere U" in lines


def test_two_source_games_on_one_match_are_both_refused():
    w = world()
    keys, _ = nc.discover(RECS[0])
    dup = [RECS[0], dict(RECS[0], id=9101, startDate="2083-09-06T20:00:00.000Z")]
    with session_scope() as s:
        teams = nc.ncaa_teams(s)
        ours = nc.load_ours(s, datetime(2083, 9, 1), datetime(2083, 9, 30), teams)
        r = nc.build_labels(dup, keys, ours, teams, {}, 2083, "fbs")
        s.rollback()
    assert r.rows == [] and r.counts["duplicate_target_refused"] == 2 and r.counts["joined"] == 0


# --- the ingest command ----------------------------------------------------------

def test_dry_run_writes_nothing_then_ingest_upserts_and_never_touches_matches(tmp_path, pinned):
    import migrate_ncaa_cfbd_labels as mig
    from cli import cli

    w = world()
    assert mig.main() == 0                                         # the marker the ingest requires
    ids = list(w["matches"].values())
    f = tmp_path / "payload.json"
    f.write_text(json.dumps(RECS))
    save = tmp_path / "saves"
    before = _match_snapshot(ids)
    with session_scope() as s:                                     # a clean slate for these ids
        for r_ in s.execute(select(NCAACFBDLabel).where(NCAACFBDLabel.match_id.in_(ids))).scalars():
            s.delete(r_)

    runner = CliRunner()
    res = runner.invoke(cli, ["ncaa-cfbd-labels", "--year", "2083", "--from-file", str(f), "--dry-run",
                              "--save-dir", str(save)])
    assert res.exit_code == 0, res.output
    assert "DRY RUN: nothing written" in res.output and "joined 4" in res.output
    assert _labels(ids) == {} and not save.exists()

    res = runner.invoke(cli, ["ncaa-cfbd-labels", "--year", "2083", "--from-file", str(f)])
    assert res.exit_code == 0, res.output
    assert "WRITTEN ncaa_cfbd_labels: inserted 4 · updated 0 · unchanged 0" in res.output
    assert "SCORE-CORRECTED rows (1" in res.output and "score-reversed: provider home/away" in res.output
    got = _labels(ids)
    assert len(got) == 4
    rev = got[w["matches"][datetime(2083, 9, 13, 19)]]
    assert (rev["home_score"], rev["away_score"], rev["source"]) == (20, 17, "cfbd")
    assert rev["payload_file"] and rev["fetched_at"] is not None
    assert _match_snapshot(ids) == before                         # matches never rewritten

    again = runner.invoke(cli, ["ncaa-cfbd-labels", "--year", "2083", "--from-file", str(f)])
    assert "inserted 0 · updated 0 · unchanged 4" in again.output
    assert _match_snapshot(ids) == before


def test_refuses_without_table_unless_dry_run(tmp_path, pinned, monkeypatch, capsys):
    world()
    f = tmp_path / "payload.json"
    f.write_text(json.dumps(RECS))
    monkeypatch.setattr(nc, "migrated", lambda s: False)
    with pytest.raises(nc.CFBDError, match="migrate_ncaa_cfbd_labels.py"):
        nc.run([2083], from_file=str(f))
    assert nc.run([2083], from_file=str(f), dry_run=True) == 0


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """A throwaway DB of its own (the shared test DB may already carry the marker)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db

    eng = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                         expire_on_commit=False))
    return eng


def test_init_db_alone_does_not_satisfy_the_guard_migration_does(tmp_path, pinned, fresh_db, capsys):
    """Codex on #333: create_all makes ncaa_cfbd_labels (it is in Base.metadata), so the
    table's existence is not the migration. Only the migration's marker unlocks writes."""
    from sqlalchemy import inspect

    import migrate_ncaa_cfbd_labels as mig
    from src.db.database import init_db as fresh_init, session_scope as fresh_scope

    fresh_init()                                                   # what scheduled commands do
    assert inspect(fresh_db).has_table("ncaa_cfbd_labels")         # the incidental table exists ...
    assert not inspect(fresh_db).has_table(nc.MIGRATION_MARKER)    # ... the marker does not
    with fresh_scope() as s:
        assert nc.has_table(s) and not nc.migrated(s)
    f = tmp_path / "payload.json"
    f.write_text(json.dumps(RECS))
    lines = []
    with pytest.raises(nc.CFBDError, match="not migrated"):
        nc.run([2083], from_file=str(f), out=lines.append)
    assert nc.run([2083], from_file=str(f), dry_run=True, out=lines.append) == 0     # dry run still works

    assert mig.main() == 0                                         # keeps the table, writes the marker
    assert "+ Wrote migration marker" in capsys.readouterr().out
    assert mig.main() == 0 and "· Kept migration marker" in capsys.readouterr().out   # idempotent
    with fresh_scope() as s:
        assert nc.migrated(s)
    lines = []
    assert nc.run([2083], from_file=str(f), out=lines.append) == 0
    assert any(x.startswith("  WRITTEN ncaa_cfbd_labels:") for x in lines)



def test_forced_reset_drops_the_marker_so_the_guard_refuses_again(tmp_path, pinned, fresh_db):
    """Codex on #333: drop_all() drops only mapped tables, so `init-db --force` left the
    unmapped marker behind while init_db() recreated an empty ncaa_cfbd_labels: the guard
    read "migrated" for a table the migration never made. drop_db() now drops the marker."""
    from sqlalchemy import inspect

    import migrate_ncaa_cfbd_labels as mig
    from src.db.database import drop_db, init_db as fresh_init, session_scope as fresh_scope

    fresh_init()
    assert mig.main() == 0
    with fresh_scope() as s:
        assert nc.migrated(s)
    drop_db()                                                      # the init-db --force path ...
    fresh_init()                                                   # ... drop, then recreate
    assert inspect(fresh_db).has_table("ncaa_cfbd_labels")
    assert not inspect(fresh_db).has_table(nc.MIGRATION_MARKER)
    with fresh_scope() as s:
        assert not nc.migrated(s)
    f = tmp_path / "payload.json"
    f.write_text(json.dumps(RECS))
    with pytest.raises(nc.CFBDError, match="not migrated"):
        nc.run([2083], from_file=str(f), out=lambda *_: None)
    assert mig.main() == 0                                         # re-migrating unlocks it again
    with fresh_scope() as s:
        assert nc.migrated(s)


def test_init_db_force_cli_drops_the_marker(fresh_db):
    from sqlalchemy import inspect

    import migrate_ncaa_cfbd_labels as mig
    from cli import cli
    from src.db.database import init_db as fresh_init

    fresh_init()
    assert mig.main() == 0 and inspect(fresh_db).has_table(nc.MIGRATION_MARKER)
    res = CliRunner().invoke(cli, ["init-db", "--force"], input="y\n")
    assert res.exit_code == 0, res.output
    assert not inspect(fresh_db).has_table(nc.MIGRATION_MARKER)
    assert inspect(fresh_db).has_table("ncaa_cfbd_labels")

def test_blank_division_omits_classification_from_the_query(monkeypatch):
    """Codex on #333: `--division ''` (all) must not send classification=fbs."""
    import urllib.parse

    sent = []

    class Resp:
        status, headers = 200, {"X-RateLimit-Remaining": "9"}

        def read(self):
            return b"[]"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        sent.append(dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(req.full_url).query)))
        assert SENTINEL not in req.full_url                       # the key stays in the header
        return Resp()

    monkeypatch.setattr(nc.urllib.request, "urlopen", fake_urlopen)
    for division in ("", None, "fbs", "fcs"):
        assert nc.fetch(2083, SENTINEL, "https://stub.invalid", division)[0] == 200
    assert sent[0] == sent[1] == {"year": "2083", "seasonType": "both"}
    assert sent[2]["classification"] == "fbs" and sent[3]["classification"] == "fcs"


def test_run_passes_blank_division_through_to_fetch(tmp_path, pinned, monkeypatch):
    import config

    world()
    monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, cfbd_api_key=SENTINEL))
    got = []

    def fake_fetch(year, key, base=nc.BASE, division="fbs"):
        got.append(division)
        return 200, RECS, {}

    monkeypatch.setattr(nc, "fetch", fake_fetch)
    lines = []
    assert nc.run([2083], dry_run=True, division="", out=lines.append) == 0
    assert nc.run([2083], dry_run=True, division="fbs", out=lines.append) == 0
    assert got == ["", "fbs"]
    assert any("division all" in x for x in lines)


def test_several_years_need_a_year_placeholder(tmp_path, pinned):
    f = tmp_path / "payload.json"
    f.write_text(json.dumps(RECS))
    with pytest.raises(nc.CFBDError, match="must contain"):
        nc.run([2082, 2083], from_file=str(f), dry_run=True, out=lambda *_: None)


def test_unmatched_names_flag_lists_every_name(tmp_path, pinned):
    from cli import cli

    world()
    many = [rec(9200 + i, f"Lost College {i}", "Cfbd A", 1, 0, "2083-10-04T19:00:00.000Z") for i in range(20)]
    f = tmp_path / "p.json"
    f.write_text(json.dumps(many))
    short = CliRunner().invoke(cli, ["ncaa-cfbd-labels", "--year", "2083", "--from-file", str(f), "--dry-run"])
    assert "--unmatched-names lists all" in short.output and "Lost College 19" not in short.output.split(
        "UNMATCHED SOURCE NAMES")[1]
    full = CliRunner().invoke(cli, ["ncaa-cfbd-labels", "--year", "2083", "--from-file", str(f), "--dry-run",
                                    "--unmatched-names"])
    tail = full.output.split("UNMATCHED SOURCE NAMES")[1]
    assert all(f"Lost College {i}" in tail for i in range(20))


def test_api_mode_key_never_printed_and_payload_saved_under_save_dir(tmp_path, pinned, monkeypatch):
    import config
    import migrate_ncaa_cfbd_labels as mig
    from cli import cli

    world()
    assert mig.main() == 0                                         # the marker the ingest requires
    monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, cfbd_api_key=SENTINEL))
    seen = {}

    def fake_fetch(year, key, base=nc.BASE, division="fbs"):
        seen["key"] = key
        return 200, RECS, {"x-ratelimit-remaining": "99"}

    monkeypatch.setattr(nc, "fetch", fake_fetch)
    save = tmp_path / "exports" / "cfbd"
    res = CliRunner().invoke(cli, ["ncaa-cfbd-labels", "--year", "2083", "--save-dir", str(save), "--dry-run"])
    assert res.exit_code == 0 and seen["key"] == SENTINEL and SENTINEL not in res.output
    assert not save.exists()                                       # dry run: no payload either

    res = CliRunner().invoke(cli, ["ncaa-cfbd-labels", "--year", "2083", "--save-dir", str(save)])
    assert res.exit_code == 0, res.output
    assert SENTINEL not in res.output and "payload saved" in res.output
    files = list(save.glob("cfbd_games_2083_*.json"))
    assert len(files) == 1 and json.loads(files[0].read_text()) == RECS
    assert SENTINEL not in files[0].read_text()
    ids = list(world()["matches"].values())
    assert all(SENTINEL not in json.dumps(v, default=str) for v in _labels(ids).values())

    def boom(year, key, base=nc.BASE, division="fbs"):
        raise RuntimeError(f"upstream said no to {key}")

    monkeypatch.setattr(nc, "fetch", boom)
    res = CliRunner().invoke(cli, ["ncaa-cfbd-labels", "--year", "2083", "--save-dir", str(save)])
    assert res.exit_code == 1 and SENTINEL not in res.output and "[REDACTED]" in res.output


def test_no_key_refuses_and_data_dir_refused(monkeypatch, pinned):
    import config
    from cli import cli

    monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, cfbd_api_key=""))
    res = CliRunner().invoke(cli, ["ncaa-cfbd-labels", "--year", "2083"])
    assert res.exit_code == 2 and "no CFBD_API_KEY" in res.output
    with pytest.raises(nc.CFBDError, match="never write under data/"):
        nc.save_payload([], 2083, nc.ROOT / "data" / "cfbd")
    assert not (nc.ROOT / "data" / "cfbd").exists()


def test_payload_path_is_timestamped_and_exports_is_gitignored(tmp_path):
    p = nc.save_payload([{"x": 1}], 2025, tmp_path, now=datetime(2026, 10, 7, 12, 0, 0))
    assert p.name == "cfbd_games_2025_20261007T120000Z.json" and p.parent == tmp_path
    assert nc.DEFAULT_SAVE_DIR == nc.ROOT / "exports" / "cfbd"
    gi = (nc.ROOT / ".gitignore").read_text().splitlines()
    assert "exports/" in gi


def test_save_dir_inside_repo_only_under_exports(tmp_path, pinned):
    """Codex on #333: a licensed raw payload never lands on a tracked repo path.
    In the repo only exports/ (gitignored) is accepted; outside the repo is the
    operator's own; data/ stays refused; symlinks are resolved first."""
    import shutil
    import uuid

    src_dir = nc.ROOT / "src" / f"cfbd_codex_{uuid.uuid4().hex[:8]}"
    with pytest.raises(nc.CFBDError, match="under exports/ only"):
        nc.save_payload([{"x": 1}], 2083, src_dir)
    assert not src_dir.exists()
    for bad in (nc.ROOT, nc.ROOT / "docs", nc.ROOT / "exportsX"):
        with pytest.raises(nc.CFBDError, match="under exports/ only"):
            nc.refuse_save_path(bad)
    with pytest.raises(nc.CFBDError, match="never write under data/"):
        nc.refuse_save_path(nc.ROOT / "data")
    link = tmp_path / "into_src"                    # outside by name, inside by real path
    link.symlink_to(nc.ROOT / "src", target_is_directory=True)
    with pytest.raises(nc.CFBDError, match="under exports/ only"):
        nc.save_payload([{"x": 1}], 2083, link / "cfbd")
    f = tmp_path / "payload.json"
    f.write_text(json.dumps(RECS))
    with pytest.raises(nc.CFBDError, match="under exports/ only"):     # refused before any work
        nc.run([2083], from_file=str(f), dry_run=True, save_dir=str(src_dir), out=lambda *_: None)
    assert not src_dir.exists()

    ok = nc.ROOT / "exports" / f"cfbd_codex_{uuid.uuid4().hex[:8]}"
    try:
        p = nc.save_payload([{"x": 1}], 2083, ok / "sub")
        assert p.parent == ok / "sub" and p.exists()
    finally:
        shutil.rmtree(ok, ignore_errors=True)
    p = nc.save_payload([{"x": 1}], 2083, tmp_path / "outside")        # outside the repo: accepted
    assert p.exists()


def test_probe_save_follows_the_same_rule(tmp_path, capsys):
    import importlib.util

    spec = importlib.util.spec_from_file_location("ncaa_source_probe",
                                                  nc.ROOT / "scripts" / "ncaa_source_probe.py")
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    target = nc.ROOT / "src" / "cfbd_{year}.json"
    assert probe.main(["--year", "2083", "--from-file", str(tmp_path / "x.json"),
                       "--save", str(target)]) == 2
    assert "under exports/ only" in capsys.readouterr().out
    assert probe.main(["--year", "2083", "--save", str(nc.ROOT / "data" / "x.json")]) == 2
    assert "never write under data/" in capsys.readouterr().out


def test_shipped_alias_map_holds_exactly_the_j3_pins():
    """ARCHITECT 2026-10-08, J3: the four pinned aliases, CFBD name -> OUR name (the file's own format)."""
    assert nc.load_aliases(nc.ALIAS_FILE) == {"App State": "Appalachian State", "Massachusetts": "UMass",
                                              "Buffalo": "Buffalo State", "Rice": "Rice Owls"}


# --- the stream read -----------------------------------------------------------

def _m(mid, h, a, hs, as_, season="2025"):
    return SimpleNamespace(id=mid, home_team_id=h, away_team_id=a, season=season,
                           utc_date=datetime(int(season), 9, 6), home_score=hs, away_score=as_, stage="Regular")


def _l(orient, hs, as_, neutral):
    return SimpleNamespace(orientation=orient, home_score=hs, away_score=as_, neutral=neutral)


def test_game_from_rows_side_table_then_fallback():
    g = nb.game_from_rows(_m(1, 10, 20, 14, 28), _l("swapped", 14, 28, True))
    assert (g.home_id, g.away_id, g.home_score, g.away_score) == (20, 10, 28, 14)       # CFBD's home is our away
    assert (g.label_source, g.orientation, g.neutral, g.score_corrected) == ("cfbd", "swapped", True, False)
    g = nb.game_from_rows(_m(2, 10, 20, 17, 20), _l("same", 20, 17, False))
    assert (g.home_id, g.home_score, g.away_score, g.score_corrected) == (10, 20, 17, True)
    g = nb.game_from_rows(_m(3, 10, 20, 3, 0))
    assert (g.home_id, g.home_score, g.label_source, g.neutral) == (10, 3, "matches", None)
    g = nb.game_from_rows(_m(4, 10, 20, 3, 0), _l("sideways", 0, 3, False))                # unknown vocab: unused
    assert (g.label_source, g.home_score) == ("matches", 3)


def test_coverage_per_season_and_the_95_condition():
    games = [nb.game_from_rows(_m(i, 100 + i, 200 + i, 21, 7), _l("same", 21, 7, False)) for i in range(19)]
    games.append(nb.game_from_rows(_m(19, 119, 219, 3, 10)))                             # uncovered
    games += [nb.game_from_rows(_m(100 + i, 300 + i, 400 + i, 10, 3, season="2026"),
                                _l("swapped", 10, 3, i == 0)) for i in range(3)]
    games.append(nb.game_from_rows(_m(200, 500, 600, 3, 0, season="2026")))
    st = nb.build_stream(games)
    cov = nb.label_coverage(st)
    assert (cov["2025"]["n"], cov["2025"]["covered"], cov["2025"]["uncovered_share"]) == (20, 19, 0.05)
    assert cov["2025"]["home_rate_nonneutral"] == 1.0
    assert cov["2025"]["home_rate_all"] == 0.95 and cov["2025"]["home_rate_uncovered"] == 0.0
    assert (cov["2026"]["covered"], cov["2026"]["swapped"], cov["2026"]["neutral"]) == (3, 3, 1)
    assert "coverage_ok" not in cov["2025"]           # SCOPE 2026-10-08: the 95% condition is no longer this ratio
    fbs = {"2025": {"season": "2025", "payload": "p25", "reason": None, "unlabelled": [], **nc.fbs_coverage(20, 19)},
           "2026": {"season": "2026", "payload": "p26", "reason": None, "unlabelled": ["CFBD 7 · x"],
                    **nc.fbs_coverage(4, 3)}}
    lines = []
    nb.coverage_report(st, out=lines.append, fbs=fbs)
    text = "\n".join(lines)
    assert ">= 95%: YES" in text and ">= 95%: NO" in text and "CFBD 7 · x" in text
    assert "coverage condition in ALL THREE seasons (2024, 2025, 2026): DOES NOT HOLD" in text
    assert "SUSPENDED-PENDING-DATA" in text and "architect" in text
    rep = []
    nb.report(st, nb.baselines(st), out=rep.append)
    assert "2025 labels: CFBD side table covers 19/20 (95.0%) · UNCOVERED share 5.0%" in "\n".join(rep)
    assert nb.GATE_STATUS == "SUSPENDED-PENDING-DATA"                                     # unchanged


def test_load_games_reads_side_table_and_falls_back(monkeypatch):
    from cli import cli

    init_db()
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == "NCAA")).scalars().first()
        if comp is None:
            comp = Competition(sport=Sport.NFL, code="NCAA", name="NCAA", area="USA", type="LEAGUE")
            s.add(comp)
            s.flush()
        a, b = Team(sport=Sport.NFL, name="Cfbd Stream A"), Team(sport=Sport.NFL, name="Cfbd Stream B")
        s.add_all([a, b])
        s.flush()
        m1 = Match(sport=Sport.NFL, competition_id=comp.id, season="2025", utc_date=datetime(2025, 9, 6, 3, 17),
                   status=MatchStatus.FINISHED, home_team_id=a.id, away_team_id=b.id, home_score=10, away_score=24,
                   stage="Regular Season")
        m2 = Match(sport=Sport.NFL, competition_id=comp.id, season="2025", utc_date=datetime(2025, 9, 13, 3, 17),
                   status=MatchStatus.FINISHED, home_team_id=a.id, away_team_id=b.id, home_score=7, away_score=3,
                   stage="Regular Season")
        s.add_all([m1, m2])
        s.flush()
        s.add(NCAACFBDLabel(match_id=m1.id, source="cfbd", source_game_id=1, season="2025", orientation="swapped",
                            neutral=False, home_score=10, away_score=24, fetched_at=datetime(2026, 10, 7)))
        ids = (m1.id, m2.id)
    before = _match_snapshot(ids)
    by = {g.match_id: g for g in nb.load_games() if g.match_id in ids}
    g1, g2 = by[ids[0]], by[ids[1]]
    assert (g1.label_source, g1.home_score, g1.away_score, g1.home_win, g1.neutral) == ("cfbd", 24, 10, 1, False)
    assert g1.home_id != g2.home_id                                   # the swapped game flips its teams
    assert (g2.label_source, g2.home_score, g2.away_score, g2.neutral) == ("matches", 7, 3, None)
    res = CliRunner().invoke(cli, ["ncaa-cfbd-coverage"])
    assert res.exit_code == 0, res.output
    assert "coverage condition in ALL THREE seasons" in res.output and "SUSPENDED-PENDING-DATA" in res.output
    assert _match_snapshot(ids) == before


def test_migration_is_additive_and_idempotent(capsys):
    import migrate_ncaa_cfbd_labels as mig

    init_db()
    assert mig.main() == 0 and mig.main() == 0
    out = capsys.readouterr().out
    assert "ncaa_cfbd_labels already exists" in out and "rows by season" in out
