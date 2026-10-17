"""#570 (ARCHITECT 2026-10-17, addendum 106 item 3; addendum 107 item A1), verbatim: "When date_from ≠ date_to, one line
before the fetch: "RANGE A..B is not supported by this provider: reading and writing the whole <season> listing" and the
receipt's STRICT label says the same." No behaviour change: the same call is made and the same listing written. The
provider is faked (no network); the DB is the throwaway one (tests/conftest.py)."""
from datetime import datetime, timezone

import pytest
from click.testing import CliRunner
from sqlalchemy import select

RULED = "RANGE 2024-08-25..2024-11-16 is not supported by this provider: reading and writing the whole 2024 listing"


def _adapter(listing, calls, printed=None):
    """The real adapter with its HTTP call faked: `calls` records each request's params, and `printed` (capsys) is read
    at the moment of the call, so a test can tell the note came before the fetch."""
    from src.adapters.api_american_football import APIAmericanFootballAdapter
    ad = APIAmericanFootballAdapter()

    def fake_get(path, params=None):
        calls.append((path, dict(params or {}), printed.readouterr().out if printed else None))
        return {"response": listing}
    ad._get = fake_get
    return ad


def _game(gid, ts, h, a, short="FT", hs=21, as_=14):
    return {"game": {"id": gid, "date": {"timestamp": int(ts.timestamp())}, "status": {"short": short},
                     "week": "Regular Season - 2", "stage": "Regular Season"},
            "teams": {"home": {"id": h, "name": f"T{h}"}, "away": {"id": a, "name": f"T{a}"}},
            "scores": {"home": {"total": hs}, "away": {"total": as_}}}


def test_the_note_reads_as_ruled_and_only_for_a_range():
    from src.adapters.api_american_football import APIAmericanFootballAdapter
    ad = APIAmericanFootballAdapter()
    assert ad.range_note("2024", "2024-08-25", "2024-11-16") == RULED
    assert ad.range_note("2024/25", "2024-08-25", "2024-11-16") == RULED            # the adapter's own season read
    assert ad.range_note("2024", "2024-10-05", "2024-10-05") is None                 # one day: sent as `date`
    assert ad.range_note("2024", None, None) is None                                 # a season read, as asked
    assert ad.range_note("2024", "2024-08-25", None) == ("RANGE 2024-08-25.. is not supported by this provider: "
                                                         "reading and writing the whole 2024 listing")
    assert ad.range_note(None, "2026-10-17", "2026-10-18").endswith("the whole listing (no --season given)")
    ad.listing_writes = False
    assert ad.range_note("2024", "2024-08-25", "2024-11-16") == RULED.replace("reading and writing", "reading")


def test_the_line_prints_before_the_fetch_and_the_call_is_unchanged(capsys):
    calls = []
    ad = _adapter([], calls, printed=capsys)
    ad.list_matches("NCAA", "2024", "2024-08-25", "2024-11-16")
    (path, params, before), = calls
    assert path == "games" and params == {"league": 2, "season": 2024}               # the same call as before #570
    assert before.strip() == RULED                                                   # printed before the fetch
    calls.clear()
    ad.list_matches("NCAA", "2025", "2025-10-04", "2025-10-04")
    (path, params, before), = calls
    assert params == {"league": 2, "season": 2025, "date": "2025-10-04"} and before == ""


@pytest.fixture
def ncaa_world():
    """A competition of the american-football family with two teams and one stored 2024 game (provider id 1001)."""
    from src.db.database import init_db, session_scope
    from src.db.schema import Competition, Match, MatchStatus, Sport, Team
    init_db()
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == "ZRN")).scalar_one_or_none()
        if comp is None:
            comp = Competition(sport=Sport.NFL, code="ZRN", name="ZRN", area="USA", type="LEAGUE")
            s.add(comp)
            s.flush()
        h = Team(sport=Sport.NFL, name="Range Owls", external_ids={"api_american_football": "97001"})
        a = Team(sport=Sport.NFL, name="Range Hawks", external_ids={"api_american_football": "97002"})
        s.add_all([h, a])
        s.flush()
        m = Match(sport=Sport.NFL, competition_id=comp.id, season="2024", utc_date=datetime(2024, 9, 7, 17),
                  status=MatchStatus.SCHEDULED, home_team_id=h.id, away_team_id=a.id,
                  external_ids={"api_american_football": "971001"})
        s.add(m)
        s.flush()
        return m.id


def test_the_strict_label_carries_the_same_words(monkeypatch, ncaa_world):
    """The Issue's faked-provider receipt (#570), through sync-matches: a range line names what it read."""
    import cli
    listing = [_game(971001, datetime(2024, 9, 7, 17, tzinfo=timezone.utc), 97001, 97002)]
    calls = []
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda c: _adapter(listing, calls))
    monkeypatch.setattr(cli, "_mlb_fallback", lambda c: False)
    rng = ["sync-matches", "--competition", "ZRN", "--season", "2024", "--date-from", "2024-08-25",
           "--date-to", "2024-11-16"]
    res = CliRunner().invoke(cli.cli, [*rng, "--match-ids", str(ncaa_world)])
    assert res.exit_code == 0, res.output
    assert RULED in res.output.splitlines()                                          # the line before the fetch
    assert f"✓ the provider's answer held all 1 named game(s) ({RULED})" in res.output
    res = CliRunner().invoke(cli.cli, [*rng, "--match-ids", f"{ncaa_world},999999999"])
    assert res.exit_code == 1
    assert (f"✗ STRICT: 1 of 2 named game(s) not in the provider's answer (ZRN 2024-08-25..2024-11-16: {RULED}): "
            "match 999999999") in res.output
    day = ["sync-matches", "--competition", "ZRN", "--season", "2024", "--date-from", "2024-09-07",
           "--date-to", "2024-09-07", "--match-ids", f"{ncaa_world},999999999"]
    res = CliRunner().invoke(cli.cli, day)                                           # one day: no note anywhere
    assert res.exit_code == 1 and "RANGE" not in res.output
    assert "(ZRN 2024-09-07..2024-09-07): match 999999999" in res.output


def test_resync_diff_says_reading(capsys, ncaa_world):
    from src.ingestion import resync_diff as rd
    calls = []
    rd.diff(_adapter([], calls), "ZRN", "2024", "2024-08-25", "2024-11-16")
    assert capsys.readouterr().out.strip().splitlines()[0] == RULED.replace("reading and writing", "reading")
