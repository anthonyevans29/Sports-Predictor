"""#945 (ARCHITECT 2026-11-12, addendum 348 item 2; addendum 354 item 4): the NCAA "live, resync needed" rows.
(1) The dry run of `dedupe-matches --orphans` says, for every live id, what the provider serves (status, status code,
score, kickoff), from the by-id answer it already read: no further call, nothing written. (2) scripts/
ncaa_live_resync_rows.py lists the stale orphan candidates on a .backup copy with their CFBD labels, read-only."""
import json
import sqlite3
from datetime import datetime, timedelta

from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, NCAACFBDLabel, Sport, Team
from src.ingestion import match_dedupe as md
from tests.test_dedupe_orphans import CODE, NOW, _nm, world  # noqa: F401  (the OR1 world fixture)


def test_945_a_live_resync_row_carries_what_the_provider_serves_and_nothing_is_written(world):
    """Cause A (a final score our row lacks) and cause B (a status our map keeps SCHEDULED, by law 4) both read off
    the plan's line; a filtered game says so. The by-id answer is the one the plan already read: no extra call."""
    ids, prov = world
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
    assert r["after"] == r["before"]                                                  # a dry run writes nothing

    held = _nm(11, 10, "23500", past)                                                 # cause B: an unmapped code
    held.status_raw = "XQ"
    prov.games = [g for g in prov.games if g.source_id != "23500"] + [held]
    resync = next(p for p in md.orphans(CODE, prov, now=NOW)["plan"] if p["id"] == ids["resync"])
    assert resync["served"] == {"status": "SCHEDULED", "status_raw": "XQ", "score": None, "utc": past.isoformat()}

    get0 = prov.get_game
    prov.get_game = lambda sid, code: (True, None) if sid == "23500" else get0(sid, code)    # filtered by the adapter
    resync = next(p for p in md.orphans(CODE, prov, now=NOW)["plan"] if p["id"] == ids["resync"])
    assert resync["action"] == "live_resync" and resync["served"].startswith("filtered by the adapter")


def test_945_the_dry_run_console_prints_the_served_answer_on_each_live_resync_line(world, monkeypatch, capsys):
    ids, prov = world
    final = _nm(11, 10, "23500", NOW - timedelta(days=1), status=MatchStatus.FINISHED)
    final.status_raw, final.home_score, final.away_score = "FT", 31, 24
    prov.games = [g for g in prov.games if g.source_id != "23500"] + [final]
    import cli
    import src.adapters.api_american_football as aaf
    monkeypatch.setattr(aaf, "APIAmericanFootballAdapter", lambda: prov)
    monkeypatch.setenv("SP_ODDS_FOOTBALL_RPM", "1000000")
    monkeypatch.setattr(md, "utc_now_naive", lambda: NOW, raising=False)
    cli._dedupe_orphans(CODE, "api_american_football", False, 30)
    line = next(ln for ln in capsys.readouterr().out.splitlines() if f"[live_resync] id {ids['resync']} " in ln)
    assert "'served': {'status': 'FINISHED', 'status_raw': 'FT', 'score': '31-24'" in line


# ---- (2) the listing ----------------------------------------------------------------------------------------------
LNOW = datetime(2026, 11, 12, 12, 0, 0)
T0 = datetime(2026, 11, 5, 9, 0, 0)          # a label stamp: the season's latest ingest record's fetched_at
SIDS = ("945001", "945002", "945003", "945004", "945005")


def _listing_world():
    """Five NCAA rows: three stale candidates (a current label, a stale label, no label), one FINISHED row and one
    candidate without a provider id; the last two are not listed. Returns {key: match id}."""
    init_db()
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == "NCAA")).scalar_one_or_none()
        if comp is None:
            comp = Competition(sport=Sport.NFL, code="NCAA", name="NCAA", area="US", type="LEAGUE")
            s.add(comp)
        ts = [Team(sport=Sport.NFL, name=f"L945 T{i}", external_ids={}) for i in range(10)]
        s.add_all(ts)
        s.flush()
        ids = {}

        def m(key, i, sid, when, status=MatchStatus.SCHEDULED, score=None):
            row = Match(sport=Sport.NFL, competition_id=comp.id, season=str(when.year), utc_date=when, status=status,
                        home_team_id=ts[2 * i].id, away_team_id=ts[2 * i + 1].id, status_raw="NS",
                        home_score=score, away_score=score,
                        external_ids={"api_american_football": sid} if sid else {})
            s.add(row)
            s.flush()
            ids[key] = row.id

        m("current", 0, SIDS[0], datetime(2024, 9, 7, 19, 0))
        m("stale", 1, SIDS[1], datetime(2025, 10, 4, 19, 0))
        m("none", 2, SIDS[2], datetime(2025, 11, 1, 19, 0))
        m("finished", 3, SIDS[3], datetime(2025, 11, 8, 19, 0), status=MatchStatus.FINISHED, score=7)
        m("nosid", 4, None, datetime(2025, 11, 15, 19, 0))
        s.add(NCAACFBDLabel(match_id=ids["current"], season="2024", orientation="same", home_score=28, away_score=17,
                            season_type="regular", fetched_at=T0))
        s.add(NCAACFBDLabel(match_id=ids["stale"], season="2025", orientation="same", home_score=10, away_score=13,
                            season_type="regular", fetched_at=T0 - timedelta(days=30)))
    return ids


def _script():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "scripts" / "ncaa_live_resync_rows.py"
    spec = importlib.util.spec_from_file_location("ncaa_live_resync_rows", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _backup(tmp_path):
    from src.db.database import get_engine
    src = sqlite3.connect(str(get_engine().url.database))
    dst = sqlite3.connect(str(tmp_path / "copy.db"))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return tmp_path / "copy.db"


def test_945_the_listing_names_the_stale_candidates_with_their_labels_read_only(tmp_path, monkeypatch, capsys):
    lr = _script()
    from src.ingestion import ncaa_cfbd
    ids = _listing_world()
    monkeypatch.setattr(ncaa_cfbd, "latest_record_stamps", lambda s, seasons=None: {"2024": T0, "2025": T0})
    copy = _backup(tmp_path)
    before = copy.read_bytes()
    assert lr.main(["--db", str(copy), "--now", LNOW.isoformat()]) == 0
    out = capsys.readouterr().out
    lines = {k: next((ln for ln in out.splitlines() if f"  id {ids[k]} " in ln), None) for k in ids}
    assert f"sid {SIDS[0]}" in lines["current"] and "CFBD label season 2024 regular 28-17" in lines["current"]
    assert "CURRENT (walked)" in lines["current"]
    assert "STALE (kept, never walked)" in lines["stale"] and "no CFBD label (never walked)" in lines["none"]
    assert lines["finished"] is None and lines["nosid"] is None                      # not candidates
    tail = json.loads(out.strip().splitlines()[-1].split(" ", 1)[1])
    assert {ids["current"], ids["stale"], ids["none"]} <= set(tail["ids"])
    assert ids["finished"] not in tail["ids"] and ids["nosid"] not in tail["ids"]
    assert copy.read_bytes() == before                                               # read-only
    assert not any(copy.with_name(copy.name + x).exists() for x in lr.SIDECARS)


def test_945_the_listing_refuses_a_copy_it_cannot_trust_and_reads_nothing(tmp_path, capsys):
    lr = _script()
    assert lr.main([]) == lr.REFUSED                                                  # no --db
    assert "REFUSED" in capsys.readouterr().out
    copy = _backup(tmp_path)
    (tmp_path / "copy.db-wal").write_bytes(b"")
    assert lr.main(["--db", str(copy)]) == lr.REFUSED
    assert "-wal sidecar" in capsys.readouterr().out
    assert lr.main(["--db", str(copy), "--now", "not-a-date"]) == lr.REFUSED
    assert lr.main(["--db", str(copy), "--now", "2026-11-12T12:00:00+00:00"]) == lr.REFUSED
