"""sync-matches --refuse-unknown-teams: intl-daily's cup schedule read refuses and says (#728). ARCHITECT 2026-10-29
09:45 ET, verbatim: "intl-daily's first FAC 2026/27 read skipped 21 listings (clubs not team-synced); the operator runs
sync-teams FAC by hand today. The daily cup read should refuse-and-say, or be preceded by a sync-teams step for a
competition-season with no teams, so the next new season does not repeat it: small PR after #709."

Throwaway DB only (tests/conftest.py); the provider is a fake adapter, no network."""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner
from sqlalchemy import select

from src.adapters.normalized import NormalizedMatch
from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Sport, Team

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "deploy" / "hosting"))
import chains  # noqa: E402

SRC = "cup728_fake"
CODE = "C728"
SEASON = "2026/27"
WHEN = datetime(2026, 11, 3, 19, 45)


class FakeAdapter:
    source_name = SRC

    def __init__(self, listing):
        self.listing = list(listing)

    def list_matches(self, code, season=None, date_from=None, date_to=None):
        return list(self.listing)


def _nm(sid, h, a):
    return NormalizedMatch(sport=Sport.SOCCER, competition_code=CODE, season=SEASON, utc_date=WHEN,
                           status=MatchStatus.SCHEDULED, home_team_source_id=h, away_team_source_id=a,
                           source=SRC, source_id=sid)


@pytest.fixture
def cup(monkeypatch):
    """The cup and two known clubs; a club 'c728-new' is never team-synced. Rows written by a test are removed."""
    import cli
    init_db()
    with session_scope() as s:
        if s.execute(select(Competition).where(Competition.code == CODE)).scalar_one_or_none() is None:
            s.add(Competition(sport=Sport.SOCCER, code=CODE, name=CODE, area="England", type="CUP"))
        for tag in ("c728-a", "c728-b"):
            if s.execute(select(Team).where(Team.name == tag)).scalar_one_or_none() is None:
                s.add(Team(sport=Sport.SOCCER, name=tag, external_ids={SRC: tag}))
    monkeypatch.setattr(cli, "_mlb_fallback", lambda c: False)

    def run(listing, *extra):
        monkeypatch.setattr(cli, "_adapter_for_competition", lambda c: FakeAdapter(listing))
        return CliRunner().invoke(cli.cli, ["sync-matches", "--competition", CODE, "--season", SEASON, *extra])
    yield run
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == CODE)).scalar_one()
        s.query(Match).filter(Match.competition_id == comp.id).delete(synchronize_session=False)


def _stored():
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == CODE)).scalar_one()
        return sorted((m.external_ids or {}).get(SRC) for m in
                      s.execute(select(Match).where(Match.competition_id == comp.id)).scalars())


LISTING = [_nm("728001", "c728-a", "c728-b"), _nm("728002", "c728-new", "c728-a"), _nm("728003", "c728-b", "c728-new")]
REFUSAL = (f"✗ REFUSED: {CODE} {SEASON}: 2 listing(s) skipped, club(s) not in the DB (ids 728002..728003); "
           f"the known listings are written. Run: python cli.py sync-teams --competition {CODE} "
           f"--season {SEASON}")


def test_the_cup_read_refuses_and_says_after_writing_the_known_listings(cup):
    """A listing whose club is not in the DB: the known listing is written (nothing rolled back), then ONE line names
    the competition, the season, the count, the id range and the sync-teams command, and the exit is 1."""
    res = cup(LISTING, "--refuse-unknown-teams")
    assert res.exit_code == 1, res.output
    lines = [x for x in res.output.splitlines() if x.strip()]
    assert lines[-1] == REFUSAL and [x for x in lines if x.startswith("✗ REFUSED")] == [REFUSAL]
    assert _stored() == ["728001"]
    assert "created=1 updated=0 skipped=2" in res.output
    # whole under sp_run's 200-character cut of a failed step's last line, for a cup with 7-digit ids
    fac = REFUSAL.replace(CODE, "FAC").replace("728002", "1234567").replace("728003", "1234587")
    assert len(fac) <= 200


def test_the_cup_read_with_every_club_known_exits_0(cup):
    res = cup(LISTING[:1], "--refuse-unknown-teams")
    assert res.exit_code == 0 and "REFUSED" not in res.output, res.output
    assert _stored() == ["728001"]


def test_without_the_flag_the_skip_stays_a_warning_and_exit_0(cup, caplog):
    """Every other sync-matches (the full-season chains, MLB's statsapi listings with the recurring M12 skips, the
    window, a by-hand run) is unchanged: the skip is the service's one warning and the exit is 0."""
    import logging
    with caplog.at_level(logging.WARNING, logger="src.ingestion.service"):
        res = cup(LISTING)
    assert res.exit_code == 0 and "REFUSED" not in res.output, res.output
    assert _stored() == ["728001"]
    assert any(f"sync_matches({CODE}): skipped 2 listing(s) whose team(s) are not in DB (ids 728002..728003)"
               in r.getMessage() for r in caplog.records)


def test_the_flag_counts_only_the_unknown_club_skips(cup, monkeypatch):
    """Only _skipped_ids counts (a club not in the DB). A competition not in the DB skips every listing with no ids
    (the service's sync_competitions warning): not this refusal, exit 0."""
    import cli
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda c: FakeAdapter(LISTING))
    res = CliRunner().invoke(cli.cli, ["sync-matches", "--competition", "C728X", "--season", SEASON,
                                       "--refuse-unknown-teams"])
    assert res.exit_code == 0 and "skipped=3" in res.output and "REFUSED" not in res.output, res.output


def test_the_flag_is_one_read_only(cup):
    res = cup(LISTING, "--refuse-unknown-teams", "--seasons", "2")
    assert res.exit_code == 2 and "--refuse-unknown-teams checks one read; not with --seasons" in res.output


def test_intl_daily_cup_steps_carry_the_flag():
    steps = chains.CHAINS["intl-daily"]["steps"]
    cups = [st for st in steps if st[0] == "sync-matches"]
    assert [st[2] for st in cups] == list(chains.CUP_SCHEDULE) == ["EFL", "CL", "UEL", "FAC"]
    assert all(st[-1] == "--refuse-unknown-teams" for st in cups)
