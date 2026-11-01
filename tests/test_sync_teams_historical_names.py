"""#764 RULED (ARCHITECT 2026-11-01 14:00 ET, addendum 204 item 2), verbatim: "build as proposed, with one change to
the comparison. A listing's season is compared with the team's NEWEST stored membership season across every
competition of the same sport, by the leading four-digit year of the stored string ("2026/27" and "2026" both read
2026; a string with no leading year reads unknown). OLDER than the newest: external_ids and the membership are
written, the name is kept, and the SyncResult carries and prints "names kept: N (a historical-season listing)".
EQUAL, NEWER, unknown, no membership yet, or a call with no season: renames as today."

The receipt behind it (#79, addendum 203): the 2023 NCAA listing renamed 1385 "Hawai'i" -> "Hawaii". Every test runs
a fake provider through the real IngestionService.sync_teams on a throwaway DB; synthetic names and ids only."""
import pytest
from click.testing import CliRunner
from sqlalchemy import select

from src.adapters.normalized import NormalizedTeam
from src.db.schema import Competition, CompetitionTeam, Sport, Team
from src.ingestion.service import IngestionService, SyncResult, names_kept_line, season_year
from tests.test_match_series_fields import fresh_db  # noqa: F401

SRC = "fake_provider"


class _Fake:
    source_name = SRC

    def __init__(self, listing):
        self.listing = listing          # {season: [(source_id, name, short_name), ...]}
        self.asked = []

    def list_teams(self, code, season):
        self.asked.append((code, season))
        rows = self.listing.get(season, self.listing.get("*", []))
        return [NormalizedTeam(sport=self.sport, name=n, source=SRC, source_id=sid, short_name=sh)
                for sid, n, sh in rows]


def _fake(listing, sport=Sport.NFL):
    f = _Fake(listing)
    f.sport = sport
    return f


def _comp(s, code, sport=Sport.NFL):
    c = Competition(sport=sport, code=code, name=code, area="USA", type="LEAGUE", external_ids={})
    s.add(c)
    s.flush()
    return c


def _team(s, name, sid, sport=Sport.NFL, short=None, memberships=()):
    """A stored team with provider id `sid` and its memberships [(competition, season), ...]."""
    t = Team(sport=sport, name=name, short_name=short, external_ids={SRC: sid})
    s.add(t)
    s.flush()
    for comp, season in memberships:
        s.add(CompetitionTeam(competition_id=comp.id, team_id=t.id, season=season))
    s.flush()
    return t.id


def _setup(memberships_of=lambda c: [(c["NCAA"], "2026")], sport=Sport.NFL, codes=("NCAA",), name="Hawai'i",
           short="Hawai'i"):
    from src.db.database import session_scope
    with session_scope() as s:
        comps = {code: _comp(s, code, sport) for code in codes}
        tid = _team(s, name, "1385", sport=sport, short=short, memberships=memberships_of(comps))
        return tid, {k: v.id for k, v in comps.items()}


def _row(tid):
    from src.db.database import session_scope
    with session_scope() as s:
        t = s.get(Team, tid)
        ms = sorted((m.competition_id, m.season) for m in s.execute(
            select(CompetitionTeam).where(CompetitionTeam.team_id == tid)).scalars())
        return t.name, t.short_name, dict(t.external_ids or {}), ms


def _sync(code, season, listing, sport=Sport.NFL) -> SyncResult:
    return IngestionService(_fake(listing, sport)).sync_teams(code, season)


# ------------------------------------------------------------------------------------------ season_year --

@pytest.mark.parametrize("s, want", [("2026/27", 2026), ("2026", 2026), ("2026-27", 2026), (2026, 2026),
                                     ("2023/24", 2023), ("abc", None), (None, None), ("", None), ("26/27", None),
                                     ("20261", None)])
def test_season_year_reads_the_leading_four_digit_year_or_unknown(s, want):
    assert season_year(s) == want


def test_the_names_kept_line_is_the_ruled_text():
    assert names_kept_line(3) == "names kept: 3 (a historical-season listing)"


# ------------------------------------------------------------------------------------------ the rule ------

def test_a_2023_listing_after_a_2026_membership_keeps_the_name_and_records_the_id(fresh_db):
    tid, comps = _setup()
    r = _sync("NCAA", "2023", {"2023": [("1385", "Hawaii", "Hawaii")]})
    name, short, ext, ms = _row(tid)
    assert (name, short) == ("Hawai'i", "Hawai'i")
    assert ext[SRC] == "1385"
    assert ms == [(comps["NCAA"], "2023"), (comps["NCAA"], "2026")]          # the membership is written
    assert r.updated == 1 and r.created == 0
    assert r.names_kept == [(tid, "Hawai'i [short: Hawai'i]", "Hawaii [short: Hawaii]")]
    assert "names kept" not in str(r)            # the CLI prints its own line, once (never twice for one sync)


def test_the_service_log_line_carries_the_names_kept_line(fresh_db, caplog):
    import logging
    _setup()
    with caplog.at_level(logging.INFO, logger="src.ingestion.service"):
        _sync("NCAA", "2023", {"2023": [("1385", "Hawaii", None)]})
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("sync_teams(NCAA)")]
    assert lines == ["sync_teams(NCAA): created=0 updated=1 skipped=0 names kept: 1 (a historical-season listing)"]


def test_an_older_listing_writes_the_provider_id_on_the_kept_row(fresh_db):
    """The ruling's "external_ids ... are written" on the kept-name path: a row that holds the listed id only as a
    merged id (no own id yet) takes it as its own id from a 2023 listing, and keeps its name."""
    from src.db.database import session_scope
    tid, _ = _setup()
    with session_scope() as s:
        s.get(Team, tid).external_ids = {f"{SRC}_also": ["9001"]}
    r = _sync("NCAA", "2023", {"2023": [("9001", "Hawaii", None)]})
    name, _, ext, _ = _row(tid)
    assert name == "Hawai'i" and ext[SRC] == "9001" and ext[f"{SRC}_also"] == ["9001"]
    assert r.names_kept == [(tid, "Hawai'i", "Hawaii")] and r.created == 0


def test_an_older_listing_found_by_a_merged_id_keeps_the_rows_own_id(fresh_db):
    """The #465 rule, untouched on the kept-name path: a row found by an id a merge recorded keeps its own id (the
    listed id is not written over it), and keeps its name."""
    from src.db.database import session_scope
    tid, comps = _setup()
    with session_scope() as s:
        s.get(Team, tid).external_ids = {SRC: "1385", f"{SRC}_also": ["9001"]}
    r = _sync("NCAA", "2023", {"2023": [("9001", "Hawaii", None)]})
    name, _, ext, _ = _row(tid)
    assert name == "Hawai'i" and ext[SRC] == "1385" and ext[f"{SRC}_also"] == ["9001"]
    assert r.names_kept == [(tid, "Hawai'i", "Hawaii")]


def test_a_listing_of_the_newest_season_renames(fresh_db):
    tid, _ = _setup()
    r = _sync("NCAA", "2026", {"2026": [("1385", "Hawaii", "Hawaii")]})
    assert _row(tid)[:2] == ("Hawaii", "Hawaii")
    assert r.names_kept == [] and "names kept" not in str(r)


def test_a_newer_listing_renames(fresh_db):
    tid, _ = _setup()
    _sync("NCAA", "2027", {"2027": [("1385", "Hawaii", None)]})
    assert _row(tid)[0] == "Hawaii"


def test_a_brand_new_team_takes_the_listings_name(fresh_db):
    tid, comps = _setup()
    r = _sync("NCAA", "2023", {"2023": [("1385", "Hawai'i", None), ("7777", "Kings College (PA)", None)]})
    from src.db.database import session_scope
    with session_scope() as s:
        new = [t for t in s.execute(select(Team)).scalars() if t.id != tid]
        assert [(t.name, t.external_ids) for t in new] == [("Kings College (PA)", {SRC: "7777"})]
    assert r.created == 1 and r.names_kept == []


def test_a_team_with_no_membership_yet_renames(fresh_db):
    tid, _ = _setup(memberships_of=lambda c: [])
    _sync("NCAA", "2023", {"2023": [("1385", "Hawaii", None)]})
    assert _row(tid)[0] == "Hawaii"


def test_a_call_with_no_season_renames(fresh_db):
    tid, _ = _setup()
    fake = _fake({"*": [("1385", "Hawaii", None)]})
    r = IngestionService(fake).sync_teams("NCAA")
    assert fake.asked == [("NCAA", None)]
    assert _row(tid)[0] == "Hawaii" and r.names_kept == []


def test_an_unknown_listing_season_renames(fresh_db):
    tid, _ = _setup()
    _sync("NCAA", "abc", {"abc": [("1385", "Hawaii", None)]})
    assert _row(tid)[0] == "Hawaii"


def test_an_unknown_stored_season_is_no_newest(fresh_db):
    """A stored membership whose season reads unknown is no newest: the team has no known membership, renames."""
    tid, _ = _setup(memberships_of=lambda c: [(c["NCAA"], "abc")])
    _sync("NCAA", "2023", {"2023": [("1385", "Hawaii", None)]})
    assert _row(tid)[0] == "Hawaii"


def test_an_older_listing_with_the_same_name_counts_no_kept_name(fresh_db):
    """Only a withheld rename is counted: a 2023 listing reading the stored spelling keeps nothing."""
    tid, _ = _setup()
    r = _sync("NCAA", "2023", {"2023": [("1385", "Hawai'i", None)]})
    assert r.names_kept == [] and r.updated == 1 and _row(tid)[0] == "Hawai'i"


def test_a_soccer_2023_24_listing_after_a_2026_27_membership_keeps_the_name(fresh_db):
    tid, comps = _setup(memberships_of=lambda c: [(c["PL"], "2026/27")], sport=Sport.SOCCER, codes=("PL",),
                        name="Brighton & Hove Albion", short="Brighton")
    r = _sync("PL", "2023/24", {"2023/24": [("1385", "Brighton and Hove Albion", "Brighton Hove")]}, Sport.SOCCER)
    name, short, _, ms = _row(tid)
    assert (name, short) == ("Brighton & Hove Albion", "Brighton")
    assert ms == [(comps["PL"], "2023/24"), (comps["PL"], "2026/27")]
    assert len(r.names_kept) == 1


def test_a_short_name_change_alone_is_kept_and_counted(fresh_db):
    tid, _ = _setup()
    r = _sync("NCAA", "2023", {"2023": [("1385", "Hawai'i", "HAW")]})
    assert _row(tid)[:2] == ("Hawai'i", "Hawai'i")
    assert r.names_kept == [(tid, "Hawai'i [short: Hawai'i]", "Hawai'i [short: HAW]")]


def test_memberships_across_two_competitions_of_the_same_sport_count(fresh_db):
    """NCAA and NFL rows are both Sport.NFL: a 2026 NFL membership makes an NCAA 2025 listing historical."""
    tid, comps = _setup(memberships_of=lambda c: [(c["NCAA"], "2023"), (c["NFL"], "2026")], codes=("NCAA", "NFL"))
    r = _sync("NCAA", "2025", {"2025": [("1385", "Hawaii", None)]})
    assert _row(tid)[0] == "Hawai'i" and len(r.names_kept) == 1


def test_another_sports_memberships_do_not_count(fresh_db):
    """A 2026 membership in a competition of another sport is not the team's newest."""
    from src.db.database import session_scope
    tid, comps = _setup(memberships_of=lambda c: [(c["NCAA"], "2023")])
    with session_scope() as s:
        other = _comp(s, "PLX", Sport.SOCCER)
        s.add(CompetitionTeam(competition_id=other.id, team_id=tid, season="2026/27"))
    _sync("NCAA", "2025", {"2025": [("1385", "Hawaii", None)]})
    assert _row(tid)[0] == "Hawaii"


def test_the_newest_map_is_read_once_per_sync(fresh_db, monkeypatch):
    """The per-sync prefetch pattern: one read of the newest years, never one per team. The listed teams are
    EXISTING teams with a newer membership, so every one reaches the historical check (a per-team read would show
    as one call per team)."""
    import src.ingestion.service as svc
    from src.db.database import session_scope
    n = 20
    with session_scope() as s:
        c = _comp(s, "NCAA")
        for i in range(n):
            _team(s, f"Old {i}", str(i), memberships=[(c, "2026")])
    calls = []
    real = svc.newest_membership_years
    monkeypatch.setattr(svc, "newest_membership_years", lambda *a, **k: calls.append(a) or real(*a, **k))
    r = _sync("NCAA", "2023", {"2023": [(str(i), f"New {i}", None) for i in range(n)]})
    assert len(calls) == 1
    assert len(r.names_kept) == n and r.updated == n and r.created == 0


def test_a_direct_upsert_with_a_season_reads_the_teams_own_newest(fresh_db):
    """_upsert_team called without sync_teams' map (a direct caller) applies the same rule."""
    from src.db.database import session_scope
    tid, _ = _setup()
    with session_scope() as s:
        svc = IngestionService(_fake({}))
        nt = NormalizedTeam(sport=Sport.NFL, name="Hawaii", source=SRC, source_id="1385")
        res = SyncResult()
        svc._upsert_team(s, nt, res, season="2023")
        assert s.get(Team, tid).name == "Hawai'i" and len(res.names_kept) == 1
        svc._upsert_team(s, nt, SyncResult())                      # no season: renames as today
        assert s.get(Team, tid).name == "Hawaii"


# ------------------------------------------------------------------------------------------ the command ---

def test_sync_teams_prints_the_names_kept_line_and_the_pairs(fresh_db, monkeypatch):
    import cli
    tid, _ = _setup()
    fake = _fake({"2023": [("1385", "Hawaii", None)]})
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda code: fake)
    r = CliRunner().invoke(cli.cli, ["sync-teams", "--competition", "NCAA", "--season", "2023"])
    assert r.exit_code == 0, r.output
    assert r.output.count("names kept:") == 1          # once per sync, on its own unwrapped line
    assert "  names kept: 1 (a historical-season listing)" in r.output.splitlines()
    assert f"team #{tid}: kept \"Hawai'i\" (the 2023 listing reads 'Hawaii')" in r.output


def test_sync_teams_caps_the_pairs_it_lists(fresh_db, monkeypatch):
    import cli
    from src.db.database import session_scope
    with session_scope() as s:
        c = _comp(s, "NCAA")
        for i in range(cli.NAMES_KEPT_SHOWN + 3):
            _team(s, f"Old {i}", str(i), memberships=[(c, "2026")])
    fake = _fake({"2023": [(str(i), f"New {i}", None) for i in range(cli.NAMES_KEPT_SHOWN + 3)]})
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda code: fake)
    r = CliRunner().invoke(cli.cli, ["sync-teams", "--competition", "NCAA", "--season", "2023"])
    assert r.exit_code == 0, r.output
    assert f"names kept: {cli.NAMES_KEPT_SHOWN + 3} (a historical-season listing)" in r.output
    assert r.output.count(": kept ") == cli.NAMES_KEPT_SHOWN and "... and 3 more" in r.output


def test_sync_teams_prints_no_line_when_nothing_is_kept(fresh_db, monkeypatch):
    import cli
    _setup()
    fake = _fake({"2026": [("1385", "Hawaii", None)]})
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda code: fake)
    r = CliRunner().invoke(cli.cli, ["sync-teams", "--competition", "NCAA", "--season", "2026"])
    assert r.exit_code == 0 and "names kept" not in r.output, r.output


def test_the_admin_job_says_so_too(fresh_db, monkeypatch):
    from src.web.routes import admin
    _setup()
    fake = _fake({"2023": [("1385", "Hawaii", None)]})
    monkeypatch.setattr(admin, "_adapter_for_competition", lambda code: fake)
    out = admin._job_sync_teams(competition_code="NCAA", season="2023")
    assert out.endswith("names kept: 1 (a historical-season listing)")
