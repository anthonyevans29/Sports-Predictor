"""#1009, THE SEASON A ONE-GAME ANSWER SERVES (ARCHITECT 2026-11-15 08:01 ET, addendum 385 item 2), verbatim in part:
"the single-game answer carries its season at response[0].league.season, A STRING OF THE YEAR. #1009's PR: get_game
reads the season from that field and hands it to _parse_games in place of ""; an answer with no league block, or a
season that is not a year, keeps today's behaviour and is never guessed (law 4); the test's answer is synthetic in this
shape."

The answers below are synthetic, in the shape the architect recorded on the laptop (GET /games?id=, 2026-11-15 12:59Z,
key names and types only): top-level keys errors, get, parameters, response, results; response a list of one game with
game, league, teams and scores blocks; league {id: int, name: str, season: str, logo: str, country: {...}}. No network:
the adapter's `_get` is stubbed. The throwaway test DB, never data/.

Before this change get_game parsed every answer with season "", so each test below that expects a season failed."""
import calendar
from datetime import timedelta

import pytest

from src.adapters.api_american_football import APIAmericanFootballAdapter, served_season
from src.ingestion import match_dedupe as md
from src.ingestion.service import season_year
from tests.test_dedupe_orphans import CODE, NOW, FakeProvider, world  # noqa: F401  (the OR1 world fixture)

PAST = NOW - timedelta(days=1)
SID = "23500"                     # the OR1 world's stale live row: teams 11 v 10, kickoff PAST, season "2026"


def _answer(sid=SID, home="OR1t11", away="OR1t10", when=PAST, season="2025", league=True, status="NS"):
    game = {"id": int(sid), "stage": "Regular Season", "week": "10",
            "date": {"timezone": "UTC", "date": when.strftime("%Y-%m-%d"), "time": when.strftime("%H:%M"),
                     "timestamp": calendar.timegm(when.timetuple())},
            "venue": {"name": None, "city": None},
            "status": {"short": status, "long": "Not Started", "timer": None}}
    one = {"game": game,
           "teams": {"home": {"id": home, "name": "Home", "logo": ""}, "away": {"id": away, "name": "Away", "logo": ""}},
           "scores": {"home": {"total": None}, "away": {"total": None}}}
    if league:
        one["league"] = {"id": 2, "name": "NCAA", "season": season, "logo": "",
                         "country": {"name": "USA", "code": "US", "flag": ""}}
    return {"errors": [], "get": "games", "parameters": {"id": sid}, "response": [one], "results": 1}


def _adapter(answers: dict):
    a = APIAmericanFootballAdapter.__new__(APIAmericanFootballAdapter)
    a._get = lambda path, params=None: answers.get(str((params or {}).get("id")), {"response": []})
    return a


def test_1009_get_game_reads_the_season_the_answer_serves():
    """The recorded field: response[0].league.season, '2025' for id 20141 and '2023' for id 10948."""
    for sid, season in (("20141", "2025"), ("10948", "2023")):
        exists, nm = _adapter({sid: _answer(sid=sid, season=season)}).get_game(sid, "NCAA")
        assert exists and nm is not None and nm.season == season, (sid, nm and nm.season)


@pytest.mark.parametrize("season", [None, "", "2025/26", "2025-26", "25", "20251", " 2025", "2025 ", "abcd",
                                    2025, 2025.0, True, ["2025"], {"y": "2025"}])
def test_1009_a_season_that_is_not_a_year_keeps_today_s_behaviour(season):
    """Law 4: only a string of four digits, as recorded, is read; anything else is today's "" (never guessed, never
    coerced: an int was never recorded)."""
    exists, nm = _adapter({SID: _answer(season=season)}).get_game(SID, "NCAA")
    assert exists and nm is not None and nm.season == ""


def test_1009_an_answer_with_no_league_block_keeps_today_s_behaviour():
    exists, nm = _adapter({SID: _answer(league=False)}).get_game(SID, "NCAA")
    assert exists and nm is not None and nm.season == ""
    ans = _answer()
    ans["response"][0]["league"] = None
    assert _adapter({SID: ans}).get_game(SID, "NCAA")[1].season == ""


def test_1009_served_season_reads_the_first_game_only_and_never_raises_on_a_malformed_answer():
    assert served_season(_answer(season="2024")) == "2024"
    for bad in ({}, {"response": None}, {"response": []}, {"response": [None]}, {"response": ["x"]},
                {"response": [{"league": "NCAA"}]}, {"response": {"league": {"season": "2025"}}}, None, []):
        assert served_season(bad) == ""


def test_1009_the_season_compares_year_to_year_with_the_stored_ncaa_row():
    """385 item 2's question, settled from the code: list_matches stores the --season it read as str(int(...)) ("2026",
    the int-style NCAA season), and the season check compares season_year on both sides (match_dedupe.served_diff,
    the upsert's own key, addendum 312 item 1). The served '2025' and a stored '2025' read one year; '2026' another."""
    assert season_year("2025") == season_year("2025") == 2025
    assert season_year("2026") != season_year("2025")
    assert season_year("") is None                    # today's "": the check stays silent, as before


class _ByIdProvider(FakeProvider):
    """The OR1 world's provider, its by-id answer for SID read through the REAL get_game over a synthetic answer."""
    def __init__(self, base, answer):
        super().__init__(base.games, base.broken)
        self.real = _adapter({SID: answer})

    def get_game(self, sid, code):
        if sid == SID:
            self.calls.append(("id", sid))
            return self.real.get_game(sid, code)
        return super().get_game(sid, code)


def test_1009_the_dry_run_reads_another_season_only_on_a_real_difference(world):
    """End to end through dedupe-matches --orphans (383 item 4(a)'s label): the stored row is season "2026". Served
    '2025', the same pair is "live, the id serves another game" with "the same pair, season 2026 -> 2025"; served
    '2026', it reads `live` (nothing to do); with no league block, `live` as before."""
    ids, prov = world
    plan = lambda p: next(x for x in md.orphans(CODE, p, now=NOW)["plan"] if x["id"] == ids["resync"])  # noqa: E731
    p = plan(_ByIdProvider(prov, _answer(season="2025")))
    assert p["action"] == "live_other_game" and p["game"] == "the same pair, season 2026 -> 2025", p
    p = plan(_ByIdProvider(prov, _answer(season="2026")))
    assert p["action"] == "live" and "game" not in p and "differs" not in p, p
    p = plan(_ByIdProvider(prov, _answer(league=False)))
    assert p["action"] == "live" and "game" not in p, p
