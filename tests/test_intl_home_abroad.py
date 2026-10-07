"""ARCHITECT 2026-10-07 item 4 (c): the READ-ONLY "home-abroad" receipt. Pins:
the share is abroad / KNOWN neutral_v3 (unknown venues are excluded from it and
counted, law 4); the --since filter; never-played statuses are left out and
counted; the venue-id coverage table covers CURRENT competition-seasons only;
--out writes a receipt, never under data/, never over an existing file. The
receipt produces no home-abroad list (the list is ruled by name)."""
from datetime import datetime

import pytest
from click.testing import CliRunner
from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, IntlMatchVenue, Match, MatchStatus, Sport, Team
from src.walters import intl_home_abroad as ha


@pytest.fixture(scope="module")
def world():
    init_db()
    with session_scope() as s:
        def comp(code):
            c = s.execute(select(Competition).where(Competition.code == code)).scalar_one_or_none()
            if c is None:
                c = Competition(sport=Sport.SOCCER, code=code, name=code, area="I", type="INTL")
                s.add(c)
                s.flush()
            return c
        unl, fr = comp("UNL"), comp("FRIENDLIES_INT")
        a, b, x = (Team(sport=Sport.SOCCER, name=n, area=ar) for n, ar in
                   (("HA Probe Abroadia", "Abroadia"), ("HA Probe Homeland", "Homeland"), ("HA Probe Visitor", "V")))
        s.add_all([a, b, x])
        s.flush()

        def m(c, home, when, season, status=MatchStatus.FINISHED, venue=None):
            g = Match(sport=Sport.SOCCER, competition_id=c.id, season=season, utc_date=when, status=status,
                      home_team_id=home.id, away_team_id=x.id)
            s.add(g)
            s.flush()
            if venue is not None:                           # (venue_id, venue_country, neutral_v3)
                vid, vc, flag = venue
                s.add(IntlMatchVenue(match_id=g.id, venue_id=vid, venue_country=vc, home_country=home.area,
                                     neutral_v3=flag, rule="r"))
            return g.id
        # team A, listed home
        m(fr, a, datetime(2021, 6, 1), "HA-F21", venue=(1, "Hungary", True))          # before since
        m(fr, a, datetime(2023, 3, 1), "HA-F23", venue=(1, "Hungary", True))          # abroad, played
        m(fr, a, datetime(2024, 3, 1), "HA-F23", venue=(2, "Abroadia", False))        # at home
        m(fr, a, datetime(2025, 3, 1), "HA-F23")                                       # no venue row
        m(fr, a, datetime(2025, 6, 1), "HA-F23", venue=(None, None, None))             # v3 NULL
        m(fr, a, datetime(2025, 9, 1), "HA-F23", status=MatchStatus.CANCELLED, venue=(1, "Hungary", True))
        m(unl, a, datetime(2096, 9, 1), "HA-26", status=MatchStatus.SCHEDULED, venue=(3, "Serbia", True))
        # team B: known home games (this one + the UNL HA-25 one below)
        m(fr, b, datetime(2024, 5, 1), "HA-F23", venue=(4, "Homeland", False))
        # coverage: UNL HA-26 is current (scheduled fixtures); UNL HA-25 is all finished
        m(unl, b, datetime(2096, 9, 2), "HA-26", status=MatchStatus.SCHEDULED, venue=(5, None, None))
        m(unl, b, datetime(2096, 8, 1), "HA-26")                                        # finished, no row
        m(unl, b, datetime(2025, 9, 1), "HA-25", venue=(4, "Homeland", False))
        return {"a": a.id, "b": b.id}


def _receipt(since=ha.DEFAULT_SINCE):
    with session_scope() as s:
        r = ha.receipt(s, since=since)
        s.rollback()
    return r


def _team(r, tid):
    return next(t for t in r["teams"] if t["team_id"] == tid)


def test_share_is_abroad_over_known_and_unknown_is_excluded_but_counted(world):
    r = _receipt()
    a = _team(r, world["a"])
    # since 2022: 2023 abroad, 2024 home, 2025 no row, 2025 NULL, 2096 abroad (upcoming); cancelled left out
    assert (a["listed_home"], a["known"], a["abroad"]) == (5, 3, 2)
    assert a["share"] == pytest.approx(2 / 3)
    assert (a["unknown"], a["unknown_null"], a["unknown_no_row"]) == (2, 1, 1)
    assert (a["abroad_finished"], a["abroad_upcoming"]) == (1, 1)
    assert a["venue_countries"] == {"Hungary": 1, "Serbia": 1} and a["country"] == "Abroadia"
    assert r["excluded_status"]["cancelled"] >= 1
    b = _team(r, world["b"])
    assert (b["known"], b["abroad"], b["share"]) == (2, 0, 0.0)          # 2024 friendly + 2025 UNL, both home
    # sorted by share desc: A before B
    ids = [t["team_id"] for t in r["teams"]]
    assert ids.index(world["a"]) < ids.index(world["b"])


def test_since_filter(world):
    a = _team(_receipt(datetime(2021, 1, 1)), world["a"])
    assert (a["listed_home"], a["known"], a["abroad"]) == (6, 4, 3)
    a = _team(_receipt(datetime(2024, 1, 1)), world["a"])
    assert (a["listed_home"], a["known"], a["abroad"]) == (4, 2, 1)


def test_coverage_is_current_competition_seasons_only(world):
    r = _receipt()
    cov = {(c["code"], c["season"]): c for c in r["coverage"]}
    assert ("UNL", "HA-25") not in cov and ("FRIENDLIES_INT", "HA-F23") not in cov
    c = cov[("UNL", "HA-26")]
    assert {k: c[k] for k in ("fixtures", "open", "with_venue_id", "known", "home", "neutral", "unknown",
                              "no_row")} == {"fixtures": 3, "open": 2, "with_venue_id": 2, "known": 1, "home": 0,
                                             "neutral": 1, "unknown": 1, "no_row": 1}
    text = ha.format_receipt(r)
    assert "HA Probe Abroadia" in text and "VENUE-ID COVERAGE" in text and "ruled by name" in text


def test_cli_writes_out_once_and_never_under_data(world, tmp_path):
    from cli import cli
    out = tmp_path / "receipts" / "home-abroad.md"
    res = CliRunner().invoke(cli, ["intl-home-abroad-receipt", "--out", str(out)])
    assert res.exit_code == 0, res.output
    assert "HA Probe Abroadia" in out.read_text()
    res = CliRunner().invoke(cli, ["intl-home-abroad-receipt", "--out", str(out)])
    assert res.exit_code == 2 and "never overwritten" in res.output
    from src.walters.unl_ladders import data_dir
    res = CliRunner().invoke(cli, ["intl-home-abroad-receipt", "--out", str(data_dir() / "x.md")])
    assert res.exit_code == 2 and "data/" in res.output
    assert not (data_dir() / "x.md").exists()
    res = CliRunner().invoke(cli, ["intl-home-abroad-receipt", "--since", "not-a-date"])
    assert res.exit_code == 2


def test_receipt_prints_full_team_names_for_the_ruled_list():
    """Codex on #325: the home-abroad list is ruled BY NAME and matched exactly; a long name is never truncated."""
    long = "Saint Vincent and the Grenadines National Team"
    r = {"since": datetime(2022, 1, 1), "coverage": [], "competitions": ["UNL"], "excluded_status": {},
         "totals": {k: 0 for k in ("listed_home", "known", "abroad", "unknown", "unknown_null", "unknown_no_row")},
         "teams": [{"team_id": 1, "team": long, "country": "SVG", "listed_home": 3, "known": 2, "abroad": 1,
                    "share": 0.5, "abroad_finished": 1, "abroad_upcoming": 0, "unknown": 1,
                    "venue_countries": {"Elsewhere": 1}}]}
    try:
        text = ha.format_receipt(r)
    except KeyError as e:                         # the pure formatter's own keys, read from its source
        raise AssertionError(f"fixture missing key {e}")
    assert long in text and f"{long} | SVG" in text           # the name's end is delimited (Codex on #325)
