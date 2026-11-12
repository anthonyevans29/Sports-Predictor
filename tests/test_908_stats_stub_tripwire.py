"""#908's tripwire (ARCHITECT 2026-11-12 14:25 ET, addendum 358 item 7, verbatim): "#908 — RULED (b), WITH A
TRIPWIRE. The write is latent while api_american_football's get_match_stats is a stub, and no guard is built against
a stub. The fix rides the PR that wires american-football stats, with the teams check and the by-id date check in its
acceptance, as you wrote them. One small test PR now: a test that fails, naming #908 and 312 item 4, the day that
adapter's get_match_stats returns anything but the empty stub — so the wiring cannot land without meeting the
limitation."

The limitation (ARCHITECT 2026-11-09 14:55 ET, addendum 312 item 4): `sync-match-stats` on a row whose provider id
the provider reused would fetch the OTHER season's stats; the fix verifies the fetched game's date and teams against
the row before writing and refuses a mismatch (`stats_game_mismatch_refused`).

The adapter is handed a provider that would answer with a full stats payload, and requests is closed, so the test
makes no network call whatever the method does. Only the PR that wires the stats (and meets #908) changes this test."""
import pytest

from src.adapters import api_american_football as aaf

TRIPWIRE = ("#908 TRIPWIRE (ARCHITECT 2026-11-12, addendum 358 item 7; the limitation: addendum 312 item 4): "
            "api_american_football.get_match_stats no longer returns the empty stub. A provider id the provider "
            "reused (18216, 18240 on #902) would fetch the OTHER season's stats. The PR that wires these stats must "
            "carry #908's fix in its acceptance: before writing, verify the fetched game's teams (the stats' team ids "
            "are the row's two teams' provider ids) and its date (a by-id read, get_game) against the row, and refuse a "
            "mismatch, counted as stats_game_mismatch_refused. That PR replaces this test with the fix's own tests and "
            "closes #908.")

# what api-sports answers for a game's team statistics: two teams, each with a block of figures
_PAYLOAD = {"response": [
    {"team": {"id": 1, "name": "Home U"}, "statistics": {"first_downs": {"total": 21}, "yards": {"total": 402},
                                                          "passing": {"total": 250}, "rushings": {"total": 152},
                                                          "turnovers": {"total": 1}, "posession": {"total": "31:10"}}},
    {"team": {"id": 2, "name": "Away State"}, "statistics": {"first_downs": {"total": 17}, "yards": {"total": 318},
                                                              "passing": {"total": 201}, "rushings": {"total": 117},
                                                              "turnovers": {"total": 2},
                                                              "posession": {"total": "28:50"}}},
], "results": 2, "errors": []}


def test_908_the_american_football_stats_stub_is_still_a_stub(monkeypatch):
    def closed(*a, **k):
        raise AssertionError("no network call from this test")
    monkeypatch.setattr(aaf.requests, "get", closed)
    ad = aaf.APIAmericanFootballAdapter()
    asked: list = []
    monkeypatch.setattr(ad, "_get", lambda path, params=None: asked.append((path, params)) or _PAYLOAD)
    try:
        got = ad.get_match_stats("18216")
    except Exception as e:                                  # noqa: BLE001 - any change of behaviour trips the wire
        pytest.fail(f"{TRIPWIRE} (it raised {type(e).__name__}: {e})")
    assert got == [] and asked == [], f"{TRIPWIRE} (it returned {got!r}; it asked {asked!r})"
