"""The NBA data certification receipt (scripts/nba_certification_receipt.py; ARCHITECT 2026-11-06, addendum 271 item
3(e)-(f) and addendum 272 item 3; #839). SYNTHETIC payloads only (tests/test_basketball_wiring.py's shapes, the fields
#839's receipt names as served); the provider is never called; the stored phase reads a copy built under tmp_path,
never data/."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from scripts import nba_certification_receipt as R
from src.adapters.api_basketball import APIBasketballAdapter
from tests.test_basketball_wiring import T0, FakeProvider, adapter_with, game, league, team

DAY = 86400
ROOT = Path(__file__).resolve().parents[1]


def season_games():
    """One synthetic season: every twin class the breakdown names, an unseen code, an absent status, a POST."""
    return [
        game(1, "FT", "Game Finished", 101, 102, T0, hs=110, as_=100),
        game(2, "CANC", "Cancelled", 101, 102, T0 + 600, stage="Synthetic Stage", week="w1"),     # FT twin, same order
        game(3, "CANC", "Game Cancelled", 102, 101, T0 + 1200),                                    # FT twin, reversed
        game(4, "AOT", "After Over Time", 103, 104, T0, hs=120, as_=118),
        game(5, "CANC", "Cancelled", 104, 103, T0 + 60),                                           # AOT twin: kept
        game(6, "CANC", "Cancelled", 101, 103, T0 + 2 * DAY),                                      # no twin
        game(7, "FT", "Game Finished", 105, 106, T0 + 3 * DAY, hs=99, as_=98),
        game(8, "CANC", "Cancelled", 105, 106, T0 + 4 * DAY),                                      # FT on another day
        game(9, "NS", "Not Started", 101, 104, T0 + 5 * DAY),
        game(10, "SYNTH", "an unseen code", 102, 103, T0 + 5 * DAY),
        game(11, status=False, home=104, away=105, ts=T0 + 6 * DAY, hs=88, as_=87),               # absent, scored
        game(12, "POST", "Game Postponed", 103, 101, T0 + 6 * DAY),
        game(13, "NS", "Not Started", 101, 777, T0 + 7 * DAY),                                     # 777: not on /teams
    ]


def provider(seasons=("2026-2027", "2025-2026", "2024-2025")):
    teams = [team(i) for i in range(101, 107)]
    return FakeProvider(leagues=[league(seasons=seasons)],
                        teams={s: teams for s in seasons},
                        games={s: (season_games() if s == "2026-2027" else
                                   [game(50, "FT", "Game Finished", 101, 102, T0 - 365 * DAY, hs=1, as_=0, season=s)])
                               for s in seasons})


def run(capsys, argv=(), fake=None):
    fake = fake or provider()
    code = R.main(list(argv), adapter=adapter_with(fake))
    out = capsys.readouterr().out
    return code, out, fake


def section(out: str, season: str) -> str:
    start = out.index(f"\nNBA {season} = provider")
    nxt = out.find("\nNBA ", start + 1)
    return out[start: nxt if nxt != -1 else len(out)]


def test_the_canc_breakdown_names_every_twin_class_and_excludes_only_ft_twins_by_provider_id(capsys):
    code, out, _ = run(capsys, ["--season", "2026"])
    assert code == R.OK, out
    s = section(out, "2026")
    assert "THE CANC BREAKDOWN (addendum 272 item 3; read before the map): 5 CANC listing(s)" in s
    assert ("by twin (same two provider team ids, same UTC day): FT twin: 2 · no same-day twin: 2 · AOT twin: 1"
            in s)
    assert "FT twins by order: home/away reversed: 1 · same home/away: 1" in s
    assert 'by stage: null: 4 · "Synthetic Stage": 1' in s and 'by week: null: 4 · "w1": 1' in s
    assert "by long form: Cancelled: 4 · Game Cancelled: 1" in s
    assert "#5 · " in s and "AOT twin: #4 AOT" in s and "#8 · " in s
    assert "listing 13 · FT-twin CANC excluded 2: 2, 3" in s
    assert "games 11: SCHEDULED: 4 · CANCELLED: 3 · FINISHED: 3 · POSTPONED: 1" in s
    assert "coverage basis SCHEDULED + FINISHED + POSTPONED = 8 (CANCELLED not counted)" in s
    tail = json.loads(out.strip().splitlines()[-1].split(" ", 1)[1])
    assert tail["seasons"]["2026"]["ft_twin_excluded"] == [2, 3]
    assert tail["seasons"]["2026"]["canc_twins"] == {"FT twin": 2, "AOT twin": 1, "no same-day twin": 2}


def test_the_breakdown_is_printed_before_the_map_in_every_season(capsys):
    code, out, _ = run(capsys)
    for season in ("2026", "2025", "2024"):
        s = section(out, season)
        order = [s.index(h) for h in ("STATUS AS SERVED", "STAGE AS SERVED", "WEEK AS SERVED", "THE CANC BREAKDOWN",
                                      "THE MAP (addendum 271 item 3(c)", "GAME COUNTS", "NULLS", "INTEGRITY")]
        assert order == sorted(order), season


def test_the_map_projection_counts_every_unmapped_code_and_infers_nothing_from_scores(capsys):
    _, out, _ = run(capsys, ["--season", "2026"])
    s = section(out, "2026")
    assert "NS -> SCHEDULED · FT -> FINISHED · AOT -> FINISHED · CANC -> CANCELLED · POST -> POSTPONED" in s
    assert "projected: CANCELLED: 5 · SCHEDULED: 4 · FINISHED: 3 · POSTPONED: 1" in s
    assert "UNMAPPED (stay SCHEDULED, counted): SYNTH: 1 · status absent: 1" in s
    assert "status absent carrying both totals: 1" in s                     # counted, left SCHEDULED
    assert "FT/AOT with a null total: 0 (must read 0: TRUE ZERO)" in s
    assert "a side not in this season's /teams (sync-matches would skip it): 1: 13" in s


def test_metering_seven_calls_and_the_remaining_requests(capsys):
    code, out, fake = run(capsys)
    assert code == R.OK
    assert [c[0] for c in fake.calls] == ["leagues"] + ["teams", "games"] * 3
    assert all(c[1].get("season") in ("2026-2027", "2025-2026", "2024-2025") for c in fake.calls[1:])
    assert all("date" not in c[1] for c in fake.calls)                     # whole seasons, one call each
    assert "CALLS: 7 this run · x-ratelimit-requests-remaining 7483 (last served)" in out


def test_the_calls_footer_counts_every_provider_request_a_429_retry_included(capsys, monkeypatch):
    """The footer and the tail JSON count the provider's requests (the adapter's own `calls`), not the receipt's
    reads: a /teams answered once with HTTP 429 and retried is two requests, so one season reads 4, not 3."""
    import src.adapters.api_basketball as ab

    class Resp:
        def __init__(self, code, body):
            self.status_code, self._b = code, body
            self.headers = {"x-ratelimit-requests-remaining": "7000"}

        def json(self):
            return self._b

        def raise_for_status(self):
            pass

    sent, limited = [], []

    def get(url, headers=None, params=None, timeout=None):
        sent.append(url)
        if url.endswith("/leagues"):
            return Resp(200, {"errors": [], "response": [league(seasons=("2026-2027",))]})
        if url.endswith("/teams") and not limited:
            limited.append(url)
            return Resp(429, {})
        return Resp(200, {"errors": [], "response": []})

    monkeypatch.setattr(ab.requests, "get", get)
    monkeypatch.setattr(ab.time, "sleep", lambda s: None)
    monkeypatch.setenv("API_FOOTBALL_KEY", "synthetic")
    code = R.main(["--season", "2026"], adapter=APIBasketballAdapter())
    out = capsys.readouterr().out
    assert code == R.OK and len(sent) == 4, out
    assert "CALLS: 4 this run · x-ratelimit-requests-remaining 7000 (last served)" in out
    assert json.loads(out.strip().splitlines()[-1].split(" ", 1)[1])["calls"] == 4
    assert "HTTP 429" in out


def test_a_season_not_served_is_refused_and_the_others_are_still_read(capsys):
    code, out, fake = run(capsys, fake=provider(seasons=("2026-2027", "2025-2026")))
    assert code == R.REFUSED
    assert "NBA 2024: REFUSED: no served season starts with '2024'" in out
    assert "NBA 2026 = provider \"2026-2027\"" in out and "NBA 2025 = provider \"2025-2026\"" in out
    assert [c for c in fake.calls if c[1].get("season") not in (None, "2026-2027", "2025-2026")] == []
    assert json.loads(out.strip().splitlines()[-1].split(" ", 1)[1])["exit"] == R.REFUSED


def test_no_key_refuses_before_any_call(capsys, monkeypatch):
    monkeypatch.delenv("API_BASKETBALL_KEY", raising=False)
    monkeypatch.delenv("API_FOOTBALL_KEY", raising=False)
    code, out, fake = run(capsys)
    assert code == R.REFUSED and fake.calls == []
    assert "REFUSED: no key: API_BASKETBALL_KEY and API_FOOTBALL_KEY are both unset; no call made" in out


def test_the_key_name_is_printed_and_its_value_never(capsys, monkeypatch):
    monkeypatch.setenv("API_BASKETBALL_KEY", "synthetic-secret-value-0001")
    code, out, _ = run(capsys)
    assert "key used: API_BASKETBALL_KEY (the value is never printed)" in out
    assert "synthetic-secret-value-0001" not in out


def test_a_league_season_disagreeing_and_a_timestamp_disagreeing_with_its_date_are_counted(capsys):
    fake = provider(seasons=("2026-2027",))
    fake.games["2026-2027"] = [game(60, season="2025-2026"),
                               game(61, ts=T0, date="2026-11-09T00:00:00+00:00")]
    _, out, _ = run(capsys, ["--season", "2026"], fake=fake)
    assert 'league.season other than "2026-2027": "2025-2026": 1' in out
    assert "timestamp and date string name different instants: 1: 61" in out


def test_the_served_phase_imports_nothing_that_opens_the_database(tmp_path):
    """Run in a fresh interpreter whose DATABASE_URL names a folder that does not exist: after a served run with a fake
    provider, the database module was never imported and the folder was never made."""
    db_dir = tmp_path / "never"
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "from scripts import nba_certification_receipt as R\n"
        "from tests.test_basketball_wiring import adapter_with\n"
        "from tests.test_nba_certification_receipt import provider\n"
        "rc = R.main(['--season', '2026'], adapter=adapter_with(provider()))\n"
        "print('DBMOD', 'src.db.database' in sys.modules, rc)\n" % str(ROOT))
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_dir / 'x.db'}", "API_FOOTBALL_KEY": "synthetic"}
    res = subprocess.run([sys.executable, "-c", code], cwd=str(tmp_path), env=env, capture_output=True, text=True,
                         timeout=120)
    assert "DBMOD False 0" in res.stdout, res.stdout + res.stderr
    assert not db_dir.exists()


# ---- the stored phase ------------------------------------------------------------------------------------------------

def _copy(tmp_path) -> Path:
    """A synthetic stored NBA season in its own SQLite file (never the app's database, never under data/)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from src.db.schema import Base, Competition, CompetitionTeam, Match, MatchStatus, Sport, Team
    path = tmp_path / "copy.db"
    eng = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        comp = Competition(sport=Sport.BASKETBALL, code="NBA", name="x", area="x", type="LEAGUE",
                           external_ids={"api_basketball": "12"})
        ts = [Team(sport=Sport.BASKETBALL, name=f"Synthetic {i}", external_ids={"api_basketball": str(i)})
              for i in range(4)]
        s.add_all([comp, *ts])
        s.flush()
        s.add_all([CompetitionTeam(competition_id=comp.id, team_id=t.id, season="2026") for t in ts])
        k = datetime(2026, 11, 5, 0, 30)

        def m(sid, st, raw, h, a, when=k, hs=None, as_=None):
            return Match(sport=Sport.BASKETBALL, competition_id=comp.id, season="2026", utc_date=when, status=st,
                         status_raw=raw, home_team_id=ts[h].id, away_team_id=ts[a].id, home_score=hs, away_score=as_,
                         external_ids={"api_basketball": sid})
        s.add_all([m("901", MatchStatus.FINISHED, "FT", 0, 1, hs=0, as_=100),
                   m("902", MatchStatus.CANCELLED, "CANC", 1, 0),                       # an FT twin, reversed
                   m("903", MatchStatus.FINISHED, "AOT", 2, 3, hs=110, as_=109),
                   m("904", MatchStatus.CANCELLED, "CANC", 2, 3),                       # an AOT twin: kept
                   m("905", MatchStatus.FINISHED, "FT", 0, 2, k.replace(day=6), hs=None, as_=90),
                   m("906", MatchStatus.SCHEDULED, "NS", 1, 3, datetime(2026, 11, 20)),
                   m("907", MatchStatus.POSTPONED, "POST", 3, 0, datetime(2026, 11, 21))])
        s.commit()
    eng.dispose()
    return path


def test_the_stored_phase_counts_per_season_true_zero_nulls_and_the_ft_twin_exclusion(tmp_path, capsys):
    path = _copy(tmp_path)
    code = R.main(["--db", str(path), "--season", "2026", "--season", "2025"])
    out = capsys.readouterr().out
    assert code == R.OK, out
    assert "stored sport values for NBA: BASKETBALL: 7" in out
    assert "NBA 2026 (stored): 7 rows · teams linked 4" in out
    assert "by status: FINISHED: 3 · CANCELLED: 2 · POSTPONED: 1 · SCHEDULED: 1" in out
    assert "FINISHED with a null score: 1 (must read 0: TRUE ZERO): match " in out       # the one planted
    assert "FT-twin CANCELLED excluded from the counts (kept as stored): 1: provider 902" in out
    assert "games 6: FINISHED: 3 · CANCELLED: 1 · POSTPONED: 1 · SCHEDULED: 1 · coverage basis SCHEDULED + " \
           "FINISHED + POSTPONED = 5" in out
    assert "NBA 2025 (stored): 0 rows" in out
    tail = json.loads(out.strip().splitlines()[-1].split(" ", 1)[1])
    assert tail["phase"] == "stored" and tail["seasons"]["2026"]["ft_twin_excluded"] == ["902"]


def test_the_stored_phase_refuses_a_copy_with_a_sidecar_and_reads_nothing(tmp_path, capsys):
    path = _copy(tmp_path)
    path.with_name(path.name + "-wal").write_text("")
    assert R.main(["--db", str(path)]) == R.REFUSED
    out = capsys.readouterr().out
    assert "REFUSED: --db" in out and "-wal sidecar" in out and "NBA 2026 (stored)" not in out


@pytest.mark.parametrize("bad", ["", "does/not/exist.db"])
def test_the_stored_phase_refuses_a_missing_copy(tmp_path, capsys, bad):
    assert R.main(["--db", str(tmp_path / bad) if bad else ""]) == R.REFUSED
    assert "REFUSED" in capsys.readouterr().out


def test_the_receipt_reads_the_adapters_own_map_and_season_rule():
    """One map and one season rule: the receipt projects with the adapter's own (never a copy that could drift)."""
    from src.adapters import api_basketball as ab
    assert R._STATUS is ab._STATUS and R.map_status is ab.map_status and R.APIBasketballAdapter is APIBasketballAdapter
