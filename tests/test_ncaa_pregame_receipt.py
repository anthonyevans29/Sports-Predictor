"""ARCHITECT 2026-10-23, addendum 158 item 1(c): the pregame metadata receipt, read-only, counts only. On a throwaway
DB of its own: the latest saved CFBD payload before kickoff is the pregame observation (by CFBD game id, its stamp the
observation time); neutral and CFBD-home agreement against the post-game label; our listing's orientation; Kalshi
quotes before kickoff and settled rows; upcoming fixtures counted; nothing written; no score printed."""
import json
from datetime import datetime, timedelta

import pytest

from src.walters import ncaa_pregame as npg

KO = datetime(2026, 10, 3, 19, 30)
NOW = datetime(2026, 10, 23, 12, 0)
REC_AT = datetime(2026, 10, 20, 9, 0)


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db

    eng = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                         expire_on_commit=False))
    db.init_db()
    return eng


def _world():
    from src.db.database import session_scope
    from src.db.schema import (Competition, Match, MatchStatus, NCAACFBDIngestRecord, NCAACFBDLabel, OddsSnapshot,
                               Sport, Team)
    ids = {}
    with session_scope() as s:
        c = Competition(sport=Sport.NFL, code="NCAA", name="NCAA", area="USA", type="LEAGUE")
        t = [Team(sport=Sport.NFL, name=f"PG {i}") for i in range(6)]
        s.add_all([c, *t])
        s.flush()

        def m(key, h, a, at, status=MatchStatus.FINISHED):
            x = Match(sport=Sport.NFL, competition_id=c.id, season="2026", utc_date=at, status=status,
                      home_team_id=t[h].id, away_team_id=t[a].id, home_score=None, away_score=None)
            s.add(x)
            s.flush()
            ids[key] = x.id
            return x

        def lab(x, gid, orient, neutral, home, st="regular"):
            s.add(NCAACFBDLabel(match_id=x.id, source="cfbd", source_game_id=gid, season="2026", orientation=orient,
                                neutral=neutral, home_score=1, away_score=0, source_home_team=home,
                                source_away_team="x", season_type=st, fetched_at=REC_AT))
        lab(m("agree", 0, 1, KO), 501, "same", True, "PG 0")              # pregame neutral too
        lab(m("differs", 2, 3, KO), 502, "swapped", False, "PG 3")        # pregame said neutral; CFBD home changed
        lab(m("no_pre", 4, 5, KO + timedelta(days=7)), 503, "same", False, "PG 4", st="postseason")
        m("upcoming", 0, 2, NOW + timedelta(days=2), status=MatchStatus.SCHEDULED)
        s.add(NCAACFBDIngestRecord(season="2026", division="fbs", fetched_at=REC_AT, payload_file=None, records=3,
                                   in_scope=3, joined=3, unlabelled=[]))
        for key, at in (("agree", KO - timedelta(hours=3)), ("no_pre", KO + timedelta(days=8)),
                        ("upcoming", NOW - timedelta(hours=1))):
            s.add(OddsSnapshot(match_id=ids[key], market="1X2", selection="HOME", devig_prob=0.5, captured_at=at,
                               source="kalshi"))
    return ids


def _payload(d, stamp, games):
    d.mkdir(exist_ok=True)
    recs = [{"id": gid, "homeTeam": h, "awayTeam": "x", "homePoints": None, "awayPoints": None, "neutralSite": nv,
             "startDate": "2026-10-03T19:30:00.000Z"} for gid, h, nv in games]
    (d / f"cfbd_games_2026_{stamp}.json").write_text(json.dumps(recs))


def test_the_latest_payload_before_kickoff_is_the_pregame_observation(fresh_db, tmp_path):
    _world()
    d = tmp_path / "cfbd"
    _payload(d, "20260920T120000Z", [(501, "PG 0", False), (502, "PG 2", True)])      # 13 days before: superseded
    _payload(d, "20261002T120000Z", [(501, "PG 0", True), (502, "PG 2", True)])       # 31.5h before: the observation
    _payload(d, "20261005T120000Z", [(501, "PG 0", False)])                            # after kickoff: never pregame
    _payload(d, "20261011T120000Z", [(503, "PG 4", False)])                            # after 503's kickoff (10-10)
    (d / "cfbd_games_2026_notastamp.json").write_text("[]")
    r = npg.receipt("2026", d, now=NOW, db_path=tmp_path / "fresh.db")
    reg = r["by_type"]["regular"]
    assert reg["games"] == 2 and reg["pregame_observed"] == 2 and reg["lead 1-3 days"] == 2
    assert reg["neutral agrees (neutral)"] == 1 and reg["neutral differs: pregame neutral, post-game home"] == 1
    assert reg["cfbd home unchanged"] == 1 and reg["cfbd home changed"] == 1
    assert (reg["listing_same"], reg["listing_swapped"]) == (1, 1)
    # Codex on #698: the orientation as known before kickoff (502's pregame home is neither of its label's teams)
    assert (reg["pregame_listing_same"], reg["pregame_listing_unknown"]) == (1, 1)
    assert reg["kalshi_quote_before_kickoff"] == 1
    post = r["by_type"]["postseason"]
    assert post["no_pregame_payload"] == 1 and post["kalshi_quote_before_kickoff"] == 0     # its quote came after
    assert r["counts"]["upcoming"] == 1 and r["counts"]["upcoming_kalshi_quote"] == 1
    text = "\n".join(npg.lines(r))
    assert "payloads read 4" in text and "notastamp" in text and "No score, result or rate" in text
    # Codex on #698: an init_db()-created table without its migration's marker is not a D11 source
    assert r["has_settled_table"] is False and "kalshi_settled_markets: not migrated here" in text


def test_it_writes_nothing_and_the_script_refuses_a_missing_db(fresh_db, tmp_path, monkeypatch):
    from sqlalchemy import text

    _world()
    with fresh_db.connect() as conn:
        before = {t: conn.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar()
                  for t in ("matches", "ncaa_cfbd_labels", "odds_snapshots")}
    npg.receipt("2026", tmp_path / "none", now=NOW, db_path=tmp_path / "fresh.db")
    with fresh_db.connect() as conn:
        assert before == {t: conn.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar() for t in before}
    import importlib.util
    spec = importlib.util.spec_from_file_location("pg_receipt", "scripts/ncaa_pregame_metadata_receipt.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'absent.db'}")
    with pytest.raises(SystemExit, match="never creates one"):
        mod.main([])
    assert not (tmp_path / "absent.db").exists()


def test_codex_698_the_receipt_opens_the_db_read_only_and_never_the_apps_session(fresh_db, tmp_path, monkeypatch):
    """Codex on #698 (P1): the receipt reads through a mode=ro engine on the named file, never the app's session_scope
    (whose connect hook sets PRAGMA journal_mode=WAL); a missing file is refused, never created."""
    import src.db.database as db
    _world()

    def forbidden(*a, **k):
        raise AssertionError("the app's writable session was opened")
    monkeypatch.setattr(db, "session_scope", forbidden)
    seen = []
    real = npg.readonly_session

    def spy(path):
        seen.append(str(path))
        return real(path)
    monkeypatch.setattr(npg, "readonly_session", spy)
    r = npg.receipt("2026", tmp_path / "none", now=NOW, db_path=tmp_path / "fresh.db")
    assert seen == [str(tmp_path / "fresh.db")] and r["stored"] == 4
    with pytest.raises(SystemExit, match="never creates one"):
        npg.receipt("2026", tmp_path / "none", now=NOW, db_path=tmp_path / "absent.db")
    assert not (tmp_path / "absent.db").exists()


def test_codex_698_a_migrated_settled_table_is_read_as_the_d11_source(fresh_db, tmp_path):
    from sqlalchemy import text

    from src.ingestion import kalshi_history
    _world()
    with fresh_db.begin() as conn:
        conn.execute(text(f"CREATE TABLE IF NOT EXISTS {kalshi_history.MIGRATION_MARKER} (id INTEGER PRIMARY KEY)"))
        conn.execute(text(f"INSERT INTO {kalshi_history.MIGRATION_MARKER} (id) VALUES (1)"))
    r = npg.receipt("2026", tmp_path / "none", now=NOW, db_path=tmp_path / "fresh.db")
    assert r["has_settled_table"] is True and "not migrated here" not in "\n".join(npg.lines(r))


def test_codex_698_the_pregame_orientation_follows_cfbds_home_before_kickoff():
    from types import SimpleNamespace as L
    lab = L(orientation="same", source_home_team="A", source_away_team="B")
    assert npg.pregame_orientation("A", lab) == "same"
    assert npg.pregame_orientation("B", lab) == "swapped"          # CFBD's home changed after kickoff
    assert npg.pregame_orientation("C", lab) == "unknown" and npg.pregame_orientation(None, lab) == "unknown"
    assert npg.pregame_orientation("A", L(orientation="swapped", source_home_team="A", source_away_team="B")) == \
        "swapped"
