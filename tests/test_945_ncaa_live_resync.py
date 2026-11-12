"""#945 (ARCHITECT 2026-11-12, addendum 348 item 2; addendum 354 item 4): the NCAA "live, resync needed" rows.
(1) The dry run of `dedupe-matches --orphans` says, for every live id, what the provider serves (status, status code,
score, kickoff), from the by-id answer it already read: no further call, nothing written. (2) scripts/
ncaa_live_resync_rows.py lists the stale orphan candidates on a .backup copy with their CFBD labels, read-only.
The listing's world is built in its own SQLite file under tmp_path: the shared test database is never written."""
import json
import sqlite3
from datetime import datetime, timedelta

from src.db.database import session_scope
from src.db.schema import Match, MatchStatus
from src.ingestion import match_dedupe as md
from tests.test_dedupe_orphans import CODE, NOW, _nm, world  # noqa: F401  (the OR1 world fixture, dropped after)


def _stored(mid):
    with session_scope() as s:
        m = s.get(Match, mid)
        return m.status, dict(m.external_ids or {}), m.home_score, m.away_score


def test_945_a_live_resync_row_carries_what_the_provider_serves_and_nothing_is_written(world):
    """Cause A (a final score our row lacks) and cause B (a status our map keeps SCHEDULED, by law 4) both read off
    the plan's line; an id that answers with no game the adapter keeps says so. The by-id answer is the one the plan
    already read: no extra call. A dry run writes nothing (the row read back from a fresh session)."""
    ids, prov = world
    before = _stored(ids["resync"])
    past = NOW - timedelta(days=1)
    final = _nm(11, 10, "23500", past, status=MatchStatus.FINISHED)
    final.status_raw, final.home_score, final.away_score = "FT", 31, 24
    prov.games = [g for g in prov.games if g.source_id != "23500"] + [final]
    r = md.orphans(CODE, prov, now=NOW)
    resync = next(p for p in r["plan"] if p["id"] == ids["resync"])
    assert resync["action"] == "live_resync"
    assert resync["served"] == {"status": "FINISHED", "status_raw": "FT", "score": "31-24", "utc": past.isoformat()}
    assert [c for c in prov.calls if c == ("id", "23500")] == [("id", "23500")]       # read once, by the plan
    live = next(p for p in r["plan"] if p["id"] == ids["twin_new"])                  # a live (not stale) row too
    assert live["action"] == "live" and live["served"]["status"] == "SCHEDULED" and live["served"]["score"] is None
    assert _stored(ids["resync"]) == before == (MatchStatus.SCHEDULED, {"api_american_football": "23500"}, None, None)

    held = _nm(11, 10, "23500", past)                                                 # cause B: an unmapped code
    held.status_raw = "XQ"
    prov.games = [g for g in prov.games if g.source_id != "23500"] + [held]
    resync = next(p for p in md.orphans(CODE, prov, now=NOW)["plan"] if p["id"] == ids["resync"])
    assert resync["served"] == {"status": "SCHEDULED", "status_raw": "XQ", "score": None, "utc": past.isoformat()}

    get0 = prov.get_game
    prov.get_game = lambda sid, code: (True, None) if sid == "23500" else get0(sid, code)    # no game kept
    resync = next(p for p in md.orphans(CODE, prov, now=NOW)["plan"] if p["id"] == ids["resync"])
    assert resync["action"] == "live_resync"
    assert resync["served"] == "the id answers; the adapter kept no game (non-competitive, or no date or team ids)"


def test_945_the_dry_run_console_prints_the_served_answer_on_each_live_resync_line(world, monkeypatch, capsys):
    ids, prov = world
    final = _nm(11, 10, "23500", NOW - timedelta(days=1), status=MatchStatus.FINISHED)
    final.status_raw, final.home_score, final.away_score = "FT", 31, 24
    prov.games = [g for g in prov.games if g.source_id != "23500"] + [final]
    import cli
    import src.adapters.api_american_football as aaf
    monkeypatch.setattr(aaf, "APIAmericanFootballAdapter", lambda: prov)
    monkeypatch.setenv("SP_ODDS_FOOTBALL_RPM", "1000000")
    cli._dedupe_orphans(CODE, "api_american_football", False, 30)
    line = next(ln for ln in capsys.readouterr().out.splitlines() if f"[live_resync] id {ids['resync']} " in ln)
    assert "'served': {'status': 'FINISHED', 'status_raw': 'FT', 'score': '31-24'" in line


# ---- (2) the listing ----------------------------------------------------------------------------------------------
LNOW = datetime(2026, 11, 12, 12, 0, 0)
T0 = datetime(2026, 11, 5, 9, 0, 0)          # a label stamp: the season's latest ingest record's fetched_at
SIDS = ("945001", "945002", "945003", "945004", "945005", "945006")


def _script():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "scripts" / "ncaa_live_resync_rows.py"
    spec = importlib.util.spec_from_file_location("ncaa_live_resync_rows", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _listing_copy(tmp_path, name="copy.db"):
    """A fresh SQLite file under tmp_path holding the schema and six NCAA rows: four stale candidates (a current label,
    a current level label, a stale label, no label), one FINISHED row and one candidate without a provider id (the
    last two not listed). The shared test database is never opened for writing. Returns (path, {key: match id})."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from src.db.schema import Base, Competition, NCAACFBDLabel, Sport, Team
    path = tmp_path / name
    eng = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(eng)
    ids = {}
    with Session(eng) as s:
        comp = Competition(sport=Sport.NFL, code="NCAA", name="NCAA", area="US", type="LEAGUE")
        s.add(comp)
        ts = [Team(sport=Sport.NFL, name=f"L945 T{i}", external_ids={}) for i in range(12)]
        s.add_all(ts)
        s.flush()

        def m(key, i, sid, when, status=MatchStatus.SCHEDULED, score=None):
            row = Match(sport=Sport.NFL, competition_id=comp.id, season=str(when.year), utc_date=when, status=status,
                        home_team_id=ts[2 * i].id, away_team_id=ts[2 * i + 1].id, status_raw="NS",
                        home_score=score, away_score=score,
                        external_ids={"api_american_football": sid} if sid else {})
            s.add(row)
            s.flush()
            ids[key] = row.id

        m("current", 0, SIDS[0], datetime(2024, 9, 7, 19, 0))
        m("level", 1, SIDS[1], datetime(2024, 9, 14, 19, 0))
        m("stale", 2, SIDS[2], datetime(2025, 10, 4, 19, 0))
        m("none", 3, SIDS[3], datetime(2025, 11, 1, 19, 0))
        m("finished", 4, SIDS[4], datetime(2025, 11, 8, 19, 0), status=MatchStatus.FINISHED, score=7)
        m("nosid", 5, None, datetime(2025, 11, 15, 19, 0))
        for key, season, h, a, at in (("current", "2024", 28, 17, T0), ("level", "2024", 21, 21, T0),
                                      ("stale", "2025", 10, 13, T0 - timedelta(days=30))):
            s.add(NCAACFBDLabel(match_id=ids[key], season=season, orientation="same", home_score=h, away_score=a,
                                season_type="regular", fetched_at=at))
        s.commit()
    eng.dispose()
    assert not any(path.with_name(path.name + x).exists() for x in ("-wal", "-shm", "-journal"))
    return path, ids


def _run(lr, args, capsys):
    rc = lr.main(args)
    return rc, capsys.readouterr().out


def test_945_the_listing_names_the_stale_candidates_with_their_labels_read_only(tmp_path, monkeypatch, capsys):
    lr = _script()
    from src.ingestion import ncaa_cfbd
    copy, ids = _listing_copy(tmp_path)
    monkeypatch.setattr(ncaa_cfbd, "latest_record_stamps", lambda s, seasons=None: {"2024": T0, "2025": T0})
    before = copy.read_bytes()
    rc, out = _run(lr, ["--db", str(copy), "--now", LNOW.isoformat()], capsys)
    assert rc == 0, out
    lines = {k: next((ln for ln in out.splitlines() if f"  id {ids[k]} " in ln), None) for k in ids}
    assert f"sid {SIDS[0]}" in lines["current"] and "CFBD label season 2024 regular 28-17" in lines["current"]
    assert "CURRENT (L3)" in lines["current"] and "level score" not in lines["current"]
    assert "CURRENT (L3) · level score: listed by v1r_stream, not walked" in lines["level"]
    assert "STALE (kept, never walked)" in lines["stale"] and "no CFBD label (never walked)" in lines["none"]
    assert lines["finished"] is None and lines["nosid"] is None                      # not candidates
    tail = json.loads(out.strip().splitlines()[-1].split(" ", 1)[1])
    assert sorted(tail["ids"]) == sorted([ids["current"], ids["level"], ids["stale"], ids["none"]])
    assert tail["current_labels_by_season"] == {"2024": 2} and tail["current_level_by_season"] == {"2024": 1}
    assert tail["stale_labels_by_season"] == {"2025": 1} and tail["no_label"] == 1
    assert tail["by_kickoff_year"] == {"2024": 2, "2025": 2}
    assert copy.read_bytes() == before                                               # read-only
    assert not any(copy.with_name(copy.name + x).exists() for x in lr.SIDECARS)


def test_945_the_listing_reads_a_copy_that_predates_the_week_and_season_type_migrations(tmp_path, monkeypatch, capsys):
    """Review P2: the labels are read with ncaa_cfbd.label_load_options, as the D2 reader is, so a copy whose
    ncaa_cfbd_labels lacks the J4 (season_type) or D10 (week) column is read, never refused."""
    lr = _script()
    from src.ingestion import ncaa_cfbd
    copy, ids = _listing_copy(tmp_path)
    con = sqlite3.connect(str(copy))
    con.execute("ALTER TABLE ncaa_cfbd_labels DROP COLUMN week")
    con.execute("ALTER TABLE ncaa_cfbd_labels DROP COLUMN season_type")
    con.commit()
    con.close()
    monkeypatch.setattr(ncaa_cfbd, "latest_record_stamps", lambda s, seasons=None: {"2024": T0, "2025": T0})
    rc, out = _run(lr, ["--db", str(copy), "--now", LNOW.isoformat()], capsys)
    assert rc == 0, out
    line = next(ln for ln in out.splitlines() if f"  id {ids['current']} " in ln)
    assert "CFBD label season 2024 (no type) 28-17" in line and "CURRENT (L3)" in line


def test_945_the_listing_refuses_what_it_cannot_trust_and_reads_nothing(tmp_path, capsys):
    lr = _script()
    rc, out = _run(lr, [], capsys)                                                    # no --db
    assert rc == lr.REFUSED and out.startswith("REFUSED")
    copy, _ = _listing_copy(tmp_path)
    rc, out = _run(lr, ["--db", str(copy), "--now", "not-a-date"], capsys)            # each refusal on a clean copy
    assert rc == lr.REFUSED and "is not an ISO timestamp" in out
    rc, out = _run(lr, ["--db", str(copy), "--now", "2026-11-12T12:00:00+00:00"], capsys)
    assert rc == lr.REFUSED and "carries a UTC offset" in out
    (tmp_path / "copy.db-wal").write_bytes(b"")
    rc, out = _run(lr, ["--db", str(copy), "--now", LNOW.isoformat()], capsys)
    assert rc == lr.REFUSED and "-wal sidecar" in out
