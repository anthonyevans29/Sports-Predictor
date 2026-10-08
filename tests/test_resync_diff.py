"""RESYNC-DIFF (NCAA audit ruling 2026-10-01): a read-only comparison of the
provider's current listing with our stored rows — because sync-matches never
rewrites home/away on an existing row, a re-sync cannot answer (or repair)
"bad copy vs bad at source". Fake adapter + throwaway DB; writes nothing."""
from datetime import datetime, timedelta
from types import SimpleNamespace as NS

from click.testing import CliRunner
from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Sport, Team
from src.ingestion import resync_diff as rd

T0 = datetime(2038, 9, 6, 17, 0)


def nm(mid, h, a, hs, as_, when=T0):
    return NS(source="fakeprov", source_id=mid, home_team_source_id=h, away_team_source_id=a,
              home_score=hs, away_score=as_, utc_date=when)


def test_classify_row():
    ours = {"home_src": "1", "away_src": "2", "home_score": 21, "away_score": 14, "utc_date": T0}
    assert rd.classify_row(ours, nm("m", "1", "2", 21, 14)) == {"teams": "same", "scores": "same",
                                                                "date_moved": False}
    r = rd.classify_row(ours, nm("m", "2", "1", 14, 21, T0 + timedelta(hours=3)))
    assert r == {"teams": "swapped", "scores": "swapped", "date_moved": True}
    assert rd.classify_row(ours, nm("m", "1", "9", None, None))["teams"] == "different"
    assert rd.classify_row(ours, nm("m", "1", "2", None, None))["scores"] == "provider_missing"


def test_sync_never_rewrites_home_away_on_existing_rows():
    # the law-1 finding this tool exists for: pin it, so a future change is deliberate
    import inspect
    from src.ingestion.service import IngestionService
    src = inspect.getsource(IngestionService._apply_match_updates)
    assert "home_team_id" not in src and "away_team_id" not in src
    assert "match.home_score = nm.home_score" in src


class FakeAdapter:
    def __init__(self, rows):
        self.rows = rows

    def list_matches(self, code, season, date_from=None, date_to=None):
        return self.rows


def _world():
    init_db()
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == "RDT")).scalar_one_or_none()
        if comp:
            return comp.id
        comp = Competition(sport=Sport.NFL, code="RDT", name="resync diff test", area="X", type="LEAGUE")
        s.add(comp)
        teams = [Team(sport=Sport.NFL, name=f"RDT team {i}", external_ids={"fakeprov": f"t{i}"}) for i in range(4)]
        s.add_all(teams)
        s.flush()
        rows = [("g1", 0, 1, 21, 14), ("g2", 2, 3, 10, 3), ("g3", 0, 2, 7, 28), ("g4", 1, 3, 17, 17)]
        for gid, h, a, hs, as_ in rows:
            s.add(Match(sport=Sport.NFL, competition_id=comp.id, season="2038", utc_date=T0,
                        status=MatchStatus.FINISHED, home_team_id=teams[h].id, away_team_id=teams[a].id,
                        home_score=hs, away_score=as_, external_ids={"fakeprov": gid}))
        return comp.id


def test_diff_counts_home_rates_and_verdict():
    _world()
    listing = [nm("g1", "t0", "t1", 21, 14),          # same
               nm("g2", "t3", "t2", 3, 10),           # labels swapped at the provider
               nm("g3", "t0", "t2", 7, 28),           # same
               nm("g9", "t0", "t3", 1, 0)]            # provider-only
    r = rd.diff(FakeAdapter(listing), "RDT", "2038")
    c = r["counts"]
    assert (c["matched"], c["teams_same"], c["teams_swapped"], c["provider_only"],
            c["ours_not_in_listing"]) == (3, 2, 1, 1, 1)
    assert c["scores_same"] == 2 and c["scores_swapped"] == 1
    assert r["home_rate"]["ours"] == (round(2 / 3, 3), 3)      # g1 H, g2 H, g3 A (g4 tie, not in listing)
    assert r["home_rate"]["provider"] == (round(1 / 3, 3), 3)
    assert any("teams swapped" in k for k in r["samples"])
    assert rd.verdict(c).startswith("PROVIDER DIFFERS on 1 team label(s)")
    same = rd.diff(FakeAdapter([nm("g1", "t0", "t1", 21, 14)]), "RDT", "2038")
    assert rd.verdict(same["counts"]).startswith("PROVIDER MATCHES OUR ROWS")
    with session_scope() as s:   # nothing written
        g2 = s.execute(select(Match).where(Match.season == "2038", Match.home_score == 10)).scalar_one()
        assert g2.away_score == 3


def test_cli_resync_diff_and_ncaa_gate_banner(monkeypatch):
    import cli
    _world()
    monkeypatch.setattr(cli, "_adapter_for_competition",
                        lambda code: FakeAdapter([nm("g1", "t0", "t1", 21, 14)]))
    out = CliRunner().invoke(cli.cli, ["resync-diff", "--competition", "RDT", "--season", "2038"])
    assert out.exit_code == 0, out.output
    assert "RESYNC-DIFF VERDICT: PROVIDER MATCHES OUR ROWS" in out.output
    from src.walters import ncaa_backtest as nb
    monkeypatch.setattr(nb, "v1r_run_recorded", lambda *a: True)          # #368 fence lifted for the banner
    out = CliRunner().invoke(cli.cli, ["ncaa-backtest", "--baselines-only"])
    assert "NCAA GATE: SUSPENDED-PENDING-DATA" in out.output
