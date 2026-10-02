"""scripts/kickoff_receipt.py (ARCHITECT 2026-10-02, NCAA WKU@NMSU / UNT@Tulsa): read-only receipt of
the stored kickoff vs the in-play test's inputs in every export carrying the match. No provider call."""
import json
import os
import sys
from datetime import datetime

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Sport, Team

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import kickoff_receipt as kr  # noqa: E402


def test_receipt_prints_stored_and_recomputes_in_play_per_export(tmp_path, capsys):
    init_db()
    with session_scope() as s:
        c = Competition(sport=Sport.NFL, code="KRNCAA", name="KR", area="US", type="LEAGUE")
        h, a = Team(sport=Sport.NFL, name="KR New Mexico St"), Team(sport=Sport.NFL, name="KR Western Ky")
        s.add_all([c, h, a])
        s.flush()
        m = Match(sport=Sport.NFL, competition_id=c.id, season="2093", utc_date=datetime(2093, 10, 3, 0, 0),
                  status=MatchStatus.SCHEDULED, home_team_id=h.id, away_team_id=a.id,
                  external_ids={"api_american_football": "999"})
        s.add(m)
        s.flush()
        mid = m.id
    for name, as_of in (("fixtures_early.json", "2093-10-02T21:21:00Z"), ("fixtures_late.json", "2093-10-03T00:30:00Z")):
        (tmp_path / name).write_text(json.dumps({"exported_at": as_of, "desk_meta": {"as_of": as_of}, "fixtures": [
            {"match_id": mid, "utc_date": "2093-10-03T00:00:00", "status": "scheduled",
             "desk": {"reason": "x"}}]}))
    assert kr.main(["--id", str(mid), "--exports", str(tmp_path), "--no-provider"]) == 0
    out = capsys.readouterr().out
    assert "STORED    utc_date 2093-10-03T00:00:00" in out and "PROVIDER  skipped" in out
    assert "fixtures_early.json" in out and "recomputed in-play False" in out
    assert "fixtures_late.json" in out and "recomputed in-play True" in out
    assert kr.main(["--find", "KR New Mexico", "--date", "2093-10-02", "--exports", str(tmp_path), "--no-provider"]) == 0
    assert f"== {mid} KR Western Ky @ KR New Mexico St" in capsys.readouterr().out
