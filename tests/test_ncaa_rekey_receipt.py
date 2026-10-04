"""ARCHITECT 2026-10-03: dedupe --apply found 0 pairs on a table that showed 962 at 07:51. The read-only
receipt must explain a 0 rather than assume one: mergeable / SAME-id / 3+ clusters counted apart,
re-keyed-in-place rows counted, stale orphans named, duplicates in the export window flagged. Runs
against the throwaway test DB (conftest), opened read-only."""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Odds, Sport, Team

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ncaa_rekey_receipt as rr  # noqa: E402

SRC = "api_american_football"
NOW = datetime(2092, 10, 3, 16, 48)


@pytest.fixture(autouse=True, scope="module")
def _cleanup():
    yield
    with session_scope() as s:
        cids = [c.id for c in s.execute(select(Competition).where(Competition.code == "RR1")).scalars()]
        mids = [m.id for m in s.execute(select(Match).where(Match.competition_id.in_(cids))).scalars()]
        s.query(Odds).filter(Odds.match_id.in_(mids)).delete(synchronize_session=False)
        s.query(Match).filter(Match.id.in_(mids)).delete(synchronize_session=False)


def test_receipt_explains_a_zero_and_flags_window_duplicates(capsys):
    init_db()
    with session_scope() as s:
        c = Competition(sport=Sport.NFL, code="RR1", name="RR1", area="US", type="LEAGUE")
        names = ["Georgia Bulldogs", "Alabama Crimson Tide", "Pitt", "Virginia Tech", "Tulsa", "UNT", "WKU", "NMSU"]
        ts = [Team(sport=Sport.NFL, name=n, external_ids={SRC: f"rr{i}"}) for i, n in enumerate(names)]
        s.add(c)
        s.add_all(ts)
        s.flush()
        t = [x.id for x in ts]

        def m(h, a, sid, when, status=MatchStatus.SCHEDULED, prev=None):
            ext = {SRC: sid, **({f"{SRC}_prev": prev} if prev else {})}
            row = Match(sport=Sport.NFL, competition_id=c.id, season="2092", utc_date=when, status=status,
                        home_team_id=t[h], away_team_id=t[a], external_ids=ext)
            s.add(row)
            s.flush()
            return row.id

        ko = NOW + timedelta(hours=3)
        old = m(1, 0, "22612", ko)                         # Georgia @ Alabama: old id + new id -> mergeable
        new = m(1, 0, "23612", ko + timedelta(hours=1))
        s.add(Odds(match_id=new, bookmaker="b", market="ML", selection="HOME", price_decimal=1.5))
        m(3, 2, "24001", ko, prev=["22001"])               # re-keyed in place: one row, no twin
        m(5, 4, "23500", ko)                               # SAME id twice -> the dedupe refuses it
        m(5, 4, "23500", ko + timedelta(hours=2))
        m(7, 6, "22777", NOW - timedelta(days=1))          # stale old-id orphan (kickoff past, still SCHEDULED)
        db = os.environ["DATABASE_URL"][len("sqlite:///"):]
    assert rr.main(["--competition", "RR1", "--db", db, "--now", NOW.isoformat(), "--ids", str(old), str(new),
                    "--game", "Georgia@Alabama"]) == 0
    out = capsys.readouterr().out
    assert "re-keyed in place (carry api_american_football_prev) 1" in out
    assert "mergeable (different ids) 1 · SAME id 1 · missing id 0 · 3+ rows 0" in out
    assert "SCHEDULED with kickoff >6h past (stale; orphan candidates): 1 by id class {'22xxx': 1}" in out
    assert "rows 5 · distinct games (home, away, date) 3" in out and "DUPLICATES IN WINDOW" in out
    assert "6. Georgia@Alabama: 2 row(s)" in out and "sid 22612" in out and "odds 1" in out
    assert f"id {old} · Georgia Bulldogs @ Alabama Crimson Tide" in out


def test_audit_merges_names_rekeyed_rows_with_a_competing_same_pair_row(capsys):
    """PR #270 review: provenance audit of the applied merges — a re-keyed row with another same-pair row
    within 48h is named for review; isolated re-keyed rows stand."""
    init_db()
    with session_scope() as s:
        c = Competition(sport=Sport.NFL, code="RR2", name="RR2", area="US", type="LEAGUE")
        ts = [Team(sport=Sport.NFL, name=f"RR2 T{i}", external_ids={SRC: f"rr2{i}"}) for i in range(4)]
        s.add(c)
        s.add_all(ts)
        s.flush()
        t = [x.id for x in ts]
        log = [{"from": "1", "to": "2", "via": "orphan-merge", "at": "2092-10-03T20:00:00"}]
        for h, a, sid, dh, ext in ((1, 0, "2", 0, {f"{SRC}_prev": ["1"], f"{SRC}_rekeys": log}),
                                   (1, 0, "9", 30, {}),                       # competing twin still there
                                   (3, 2, "5", 0, {f"{SRC}_prev": ["4"]})):   # isolated: stands (pre-log)
            s.add(Match(sport=Sport.NFL, competition_id=c.id, season="2092", utc_date=NOW + timedelta(hours=dh),
                        status=MatchStatus.SCHEDULED, home_team_id=t[h], away_team_id=t[a],
                        external_ids={SRC: sid, **ext}))
        cid = c.id
        db = os.environ["DATABASE_URL"][len("sqlite:///"):]
    assert rr.main(["--competition", "RR2", "--db", db, "--now", NOW.isoformat(), "--audit-merges"]) == 0
    out = capsys.readouterr().out
    assert "7. merge provenance audit: 2 re-keyed row(s) · provenance log {'orphan-merge': 1}" in out
    assert "with another same-pair row within 48h: 1 (REVIEW these)" in out and "near:" in out and "sid 9" in out
    with session_scope() as s:
        s.query(Match).filter(Match.competition_id == cid).delete(synchronize_session=False)
