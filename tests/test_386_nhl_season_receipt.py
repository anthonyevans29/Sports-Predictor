"""ARCHITECT 2026-11-15, addendum 386 item 2: `nhl-goalie-coverage --db COPY`, the counts-only season receipt.

"--db COPY through the shared fence, opened mode=ro with immutable=1, with NO init_db() on that path; the command
without --db is unchanged ... counts only, by season (2023-24, 2024-25, 2025-26, and 2026-27 so far): (a) the finished
regular-season games we hold (game type 2 where the row says it, and how many rows do not say); (b) of them, the games
with BOTH starters flagged by the boxscore, with exactly one, with none; (c) the appearances with no linked match
(match_id NULL), regular season only, and how many distinct games they stand for; (d) the share of games in which a
goalie other than the flagged starter also appeared ...; (e) for 2026-27, the latest game date an appearance is stored
for ... No goalie's name and no figure of any model."

Every row below is synthetic (game ids 9xxxxxxxxx, goalie ids 8xxx, the name "SYN GOALIE"), written to a throwaway
file under tmp_path, never under data/.
"""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime

import pytest
from click.testing import CliRunner
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.db.schema import Base, NHLGoalieAppearance

NAME = "SYN GOALIE"


def _row(gid, start, gtype, side, goalie, starter, toi, match_id=None):
    return NHLGoalieAppearance(nhl_game_id=gid, match_id=match_id, game_start=start, game_type=gtype, side=side,
                               team_abbrev="SYN", goalie_id=goalie, goalie_name=NAME, is_starter=starter,
                               toi_seconds=toi, captured_at=datetime(2026, 11, 15))


def _rows():
    t23, t24, t26 = datetime(2023, 11, 1, 0, 30), datetime(2024, 12, 1, 0, 30), datetime(2026, 10, 10, 23, 0)
    return [
        # 2023-24 (no match rows: the warm-up season sits outside matches, so match_id is NULL)
        # g1: regular, both flagged, a home relief goalie played (TOI > 0), the away backup did not (TOI 0)
        _row(9023000001, t23, 2, "home", 8001, True, 2400), _row(9023000001, t23, 2, "home", 8002, False, 1200),
        _row(9023000001, t23, 2, "away", 8101, True, 3600), _row(9023000001, t23, 2, "away", 8102, False, 0),
        # g2: regular, only the home starter flagged (the away flag was not found: NULL)
        _row(9023000002, t23, 2, "home", 8001, True, 3600), _row(9023000002, t23, 2, "away", 8103, None, 3600),
        # g3: no row states the game type
        _row(9023000003, t23, None, "home", 8001, True, 3600), _row(9023000003, t23, None, "away", 8101, True, 3600),
        # g4: a playoff game in the same season (May), out of the regular-season counts
        _row(9023000004, datetime(2024, 5, 1), 3, "home", 8001, True, 3600),
        _row(9023000004, datetime(2024, 5, 1), 3, "away", 8101, True, 3600),
        # 2024-25
        # g5: both flagged, linked to our match, backup at TOI 0: no relief
        _row(9024000005, t24, 2, "home", 8001, True, 3600, 501), _row(9024000005, t24, 2, "away", 8101, True, 3600, 501),
        _row(9024000005, t24, 2, "home", 8002, False, 0, 501),
        # g6: none flagged
        _row(9024000006, t24, 2, "home", 8001, False, 3600), _row(9024000006, t24, 2, "away", 8101, None, 3600),
        # g7: both flagged; a non-starter whose TOI was not stored: relief unknown, never guessed
        _row(9024000007, t24, 2, "home", 8001, True, 3600), _row(9024000007, t24, 2, "away", 8101, True, 3600),
        _row(9024000007, t24, 2, "away", 8102, False, None),
        # g8: the home side has two rows flagged (not "flagged": exactly one is); the away side one -> exactly one
        _row(9024000008, t24, 2, "home", 8001, True, 3600), _row(9024000008, t24, 2, "home", 8002, True, 0),
        _row(9024000008, t24, 2, "away", 8101, True, 3600),
        # 2025-26: nothing stored
        # 2026-27
        # g9: both flagged, linked
        _row(9026000009, t26, 2, "home", 8001, True, 3600, 909), _row(9026000009, t26, 2, "away", 8101, True, 3600, 909),
        # g10: both flagged, unlinked, an away relief goalie played; the latest regular-season game
        _row(9026000010, datetime(2026, 11, 13, 0, 30), 2, "home", 8001, True, 3600),
        _row(9026000010, datetime(2026, 11, 13, 0, 30), 2, "away", 8101, True, 1800),
        _row(9026000010, datetime(2026, 11, 13, 0, 30), 2, "away", 8102, False, 1800),
        # g11: a game type the regular season excludes, stored latest: (e) is "an appearance", any game type
        _row(9026000011, datetime(2026, 11, 14, 1, 0), 1, "home", 8001, True, 3600),
    ]


@pytest.fixture
def copy(tmp_path):
    """A synthetic .backup-shaped copy: WAL mode, no sidecars, outside data/."""
    path = tmp_path / "copy" / "sports.db"
    path.parent.mkdir()
    eng = create_engine(f"sqlite:///{path}", future=True)
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add_all(_rows())
        s.commit()
    eng.dispose()
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.close()
    assert sorted(p.name for p in path.parent.iterdir()) == ["sports.db"]
    return path


def _cli(*args):
    return CliRunner().invoke(__import__("cli").cli, ["nhl-goalie-coverage", *args])


def _sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_386_2_the_season_receipt_counts_a_through_e_on_a_copy(copy, monkeypatch):
    import src.db.database as db

    def _no(*_a, **_k):
        raise AssertionError("init_db() on the --db path (386 item 2: NO init_db() on that path)")
    monkeypatch.setattr(db, "init_db", _no)
    before = _sha(copy)
    r = _cli("--db", str(copy))
    assert r.exit_code == 0, r.output
    out = r.output
    assert "NHL-GOALIE SEASON RECEIPT (addendum 386 item 2)" in out and "mode=ro + immutable=1" in out
    assert "27 appearance rows" in out
    # 2023-24
    assert "  2023-24: (a) finished regular-season games 2 · game type not stated: 2 rows · games where no row states it 1" in out
    assert "(b) both starters flagged 1 · exactly one 1 · none 0 · sides with more than one flagged 0" in out
    assert "(c) appearances with no linked match 6 · the distinct games they stand for 2" in out
    assert "(d) relief (a goalie other than the flagged starter with TOI > 0): 1 of 1 both-flagged games = 100.0% · " \
           "TOI not stored 0" in out
    # 2024-25
    assert "  2024-25: (a) finished regular-season games 4 · game type not stated: 0 rows · games where no row states it 0" in out
    assert "(b) both starters flagged 2 · exactly one 1 · none 1 · sides with more than one flagged 1" in out
    assert "(c) appearances with no linked match 8 · the distinct games they stand for 3" in out
    assert "0 of 2 both-flagged games = 0.0% · TOI not stored 1" in out
    # 2025-26: named, held at nothing
    assert "  2025-26: (a) finished regular-season games 0 · game type not stated: 0 rows · games where no row states it 0" in out
    # 2026-27
    assert "  2026-27: (a) finished regular-season games 2 ·" in out
    assert "(c) appearances with no linked match 3 · the distinct games they stand for 1" in out
    assert "1 of 2 both-flagged games = 50.0%" in out
    assert "(e) latest game date an appearance is stored for: 2026-11-14 (UTC; any game type) · the latest " \
           "regular-season game: 2026-11-13" in out
    assert "games with no stored start (season unknown): 0" in out
    # counts only: no goalie's name, no goalie id
    assert NAME not in out and "8001" not in out
    # the copy is read, never written: the same bytes, no sidecar
    assert _sha(copy) == before and sorted(p.name for p in copy.parent.iterdir()) == ["sports.db"]


def test_386_2_the_fence_refuses_and_nothing_is_created(tmp_path, monkeypatch):
    import src.db.database as db
    monkeypatch.setattr(db, "init_db", lambda *a, **k: (_ for _ in ()).throw(AssertionError("init_db")))
    missing = tmp_path / "nowhere" / "copy.db"
    r = _cli("--db", str(missing))
    assert r.exit_code == 2 and "NHL-GOALIE COVERAGE REFUSED" in r.output and "no file at" in r.output, r.output
    assert not missing.exists() and not missing.parent.exists()


def test_386_2_a_copy_without_the_table_refuses_by_name(tmp_path):
    path = tmp_path / "old" / "sports.db"
    path.parent.mkdir()
    sqlite3.connect(path).execute("CREATE TABLE matches (id INTEGER PRIMARY KEY)").connection.close()
    r = _cli("--db", str(path))
    assert r.exit_code == 2 and "nhl_goalie_appearances" in r.output and "REFUSED" in r.output, r.output
