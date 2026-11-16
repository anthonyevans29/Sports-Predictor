"""scripts/ncaa_listing_probe.py (ARCHITECT 2026-11-16, addendum 414 item 3; #1035): the provider's raw NCAA rows per
date, beside what our side would do with each. Every row here is invented (414 item 3(d)); no network call is made:
requests.get is replaced by a fake that answers from the test's own payloads."""
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ncaa_listing_probe as probe  # noqa: E402

KEY = "INVENTED-KEY-VALUE-7f3a"


def make_copy(path: Path, *, ncaa=True) -> Path:
    """A .backup-shaped copy on the real schema: one NCAA competition, five teams, three stored matches."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from src.db.schema import Base, Competition, Match, MatchStatus, Sport, Team
    eng = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        c = Competition(sport=Sport.NFL, code="NCAA" if ncaa else "NCAX", name="NCAA Football", area="USA",
                        type="LEAGUE")
        teams = [Team(sport=Sport.NFL, name=n, external_ids=e) for n, e in (
            ("Invented A", {"api_american_football": 101}), ("Invented B", {"api_american_football": 102}),
            ("Invented C", {"api_american_football": "103", "api_american_football_also": ["555"]}),
            ("Invented D", {"api_american_football": 104}), ("Invented E", {"api_american_football": 105}))]
        s.add_all([c, *teams])
        s.flush()
        a, b, cc, d, e = teams

        def m(home, away, season, ext, status=MatchStatus.SCHEDULED):
            return Match(sport=Sport.NFL, competition_id=c.id, season=season, utc_date=datetime(2091, 11, 21, 17),
                         status=status, home_team_id=home.id, away_team_id=away.id, external_ids=ext)
        s.add_all([m(a, b, "2026", {"api_american_football": "9001"}),
                   m(cc, d, "2025", {"api_american_football": "9007"}, MatchStatus.FINISHED),
                   m(d, e, "2026", {"api_american_football": "9100", "api_american_football_prev": ["9008"]})])
        s.commit()
    eng.dispose()
    return path


def row(gid, home, away, *, ts=1_700_000_000, date="2091-11-21", status="NS", week="Week 13", stage="Regular Season",
        hname="Invented Home", aname="Invented Away"):
    return {"game": {"id": gid, "stage": stage, "week": week,
                     "date": {"timezone": "UTC", "date": date, "time": "17:00", "timestamp": ts},
                     "status": {"short": status, "long": "Not Started"}},
            "teams": {"home": {"id": home, "name": hname}, "away": {"id": away, "name": aname}}}


class FakeResp:
    def __init__(self, code, payload):
        self.status_code, self._payload, self.headers = code, payload, {}

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"{self.status_code} invented failure")

    def json(self):
        return self._payload


@pytest.fixture
def net(monkeypatch):
    """The fake provider: answers per date from `pages`, records each call's params and headers."""
    import requests

    import src.adapters.api_american_football as aaf
    state = {"calls": [], "pages": {}, "codes": {}}

    def fake_get(url, headers=None, params=None, timeout=None):
        state["calls"].append({"url": url, "params": dict(params or {}), "headers": dict(headers or {})})
        d = (params or {}).get("date")
        codes = state["codes"].get(d) or []
        code = codes.pop(0) if codes else 200
        return FakeResp(code, {"get": "games", "parameters": params, "errors": [], "results": len(state["pages"].get(d, [])),
                               "response": state["pages"].get(d, [])})

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(aaf.time, "sleep", lambda s: None)
    monkeypatch.setenv("API_AMERICAN_FOOTBALL_KEY", KEY)
    monkeypatch.delenv("API_FOOTBALL_KEY", raising=False)
    import dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    return state


def run(argv):
    out = []
    code = probe.main(argv, echo=out.append)
    return code, "\n".join(out)


def test_rows_and_what_our_side_does(tmp_path, net):
    db = make_copy(tmp_path / "copy.db")
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    listing = set(os.listdir(tmp_path))
    net["pages"]["2091-11-21"] = [
        row(9001, 101, 102),                                         # stored
        row(9002, 101, 555),                                         # not stored; 555 is a merged id of team 103
        row(9003, 101, 102, ts=None, date=None),                     # #1
        row(9004, 101, None),                                        # #2
        row(9005, 101, 102, stage="All-Star Game"),                  # #3
        row(9006, 999, 102),                                         # #6
        row(9007, 103, 104),                                         # held by a 2025 row
        row(9008, 104, 105),                                         # a previous id
        row(None, 101, 102),                                         # #2, no game id
    ]
    code, out = run(["--date", "2091-11-21", "--db", str(db)])
    assert code == 0
    lines = out.splitlines()
    assert lines[0].startswith("NCAA-LISTING-PROBE: provider calls planned: 1 (one GET games per date: league 2, "
                               "season 2026")
    assert "key: API_AMERICAN_FOOTBALL_KEY (by name)" in lines[0]
    assert KEY not in out
    assert "NCAA competition id 1, 3 stored matches" in out
    assert "DATE 2091-11-21: GET games league=2 season=2026 date=2091-11-21: results=9 paging=None rows=9" in out
    by = {ln.split()[0]: ln for ln in lines if ln.startswith("  game=")}
    assert "-> stored as match 1 (season 2026, SCHEDULED, 2091-11-21 17:00:00" in by["game=9001"]
    assert by["game=9002"].endswith("-> NOT STORED")
    assert "-> DROPPED: no date (#1); NOT STORED" in by["game=9003"]
    assert "DROPPED: no team id (#2): no away team id" in by["game=9004"]
    assert "DROPPED: all-star or exhibition (#3): marker 'all-star'" in by["game=9005"]
    assert "team not in the copy (#6): home 999; NOT STORED" in by["game=9006"]
    assert "stored as match 2 (season 2025, another season, FINISHED" in by["game=9007"]
    assert by["game=9008"].endswith("-> NOT STORED (a previous id of match 3)")
    assert by["game=None"].endswith("-> DROPPED: no team id (#2): no game id")
    # the raw fields, before any parsing
    assert ("game=9001 date='2091-11-21' time='17:00' timestamp=1700000000 status='NS'/'Not Started' week='Week 13' "
            "stage='Regular Season' | home=101 'Invented Home' | away=102 'Invented Away'") in by["game=9001"]
    assert lines[-1] == "NCAA-LISTING-PROBE: dates read 1 of 1; provider calls made: 1 HTTP GET(s)"
    # one GET, the sync's own parameters, the key in the header only
    assert [c["params"] for c in net["calls"]] == [{"league": 2, "season": 2026, "date": "2091-11-21"}]
    assert net["calls"][0]["url"].endswith("/games")
    # nothing written, no file made
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    assert set(os.listdir(tmp_path)) == listing


def test_without_db_only_the_parse_side(net):
    net["pages"]["2091-11-27"] = [row(9001, 101, 102), row(9003, 101, 102, ts=None, date=None)]
    code, out = run(["--date", "2091-11-27"])
    assert code == 0
    assert "--db: none (no stored-side reads" in out
    assert "-> kept by the parse" in out
    assert "-> DROPPED: no date (#1)" in out
    assert "NOT STORED" not in out and "stored as" not in out


@pytest.mark.parametrize("argv,why", [
    ([], "no --date given"),
    ([x for d in range(1, 9) for x in ("--date", f"2091-11-0{d}")], "8 dates given; at most 7 a run"),
    (["--date", "2091-11-31"], "is not a date written YYYY-MM-DD"),
    (["--date", "21-11-2091"], "is not a date written YYYY-MM-DD"),
    (["--date", "2091-11-21", "--date", "2091-11-21"], "given twice"),
])
def test_dates_refused_before_any_call(net, argv, why):
    code, out = run(argv)
    assert code == 2 and why in out and "provider calls made: 0" in out
    assert net["calls"] == []


def test_no_key_refused_by_name(net, monkeypatch):
    monkeypatch.delenv("API_AMERICAN_FOOTBALL_KEY")
    code, out = run(["--date", "2091-11-21"])
    assert code == 2
    assert "no key in API_AMERICAN_FOOTBALL_KEY or API_FOOTBALL_KEY; provider calls made: 0" in out
    assert net["calls"] == []


def test_fallback_key_named(net, monkeypatch):
    monkeypatch.delenv("API_AMERICAN_FOOTBALL_KEY")
    monkeypatch.setenv("API_FOOTBALL_KEY", KEY)
    code, out = run(["--date", "2091-11-21"])
    assert code == 0 and "key: API_FOOTBALL_KEY (by name)" in out and KEY not in out


def test_provider_error_prints_after_what_was_read(net):
    net["pages"]["2091-11-21"] = [row(9001, 101, 102)]
    net["codes"]["2091-11-27"] = [500]
    code, out = run(["--date", "2091-11-21", "--date", "2091-11-27", "--date", "2091-11-28"])
    assert code == 1
    assert "game=9001" in out
    assert "DATE 2091-11-27: PROVIDER ERROR: HTTPError: 500 invented failure; no later date is called" in out
    assert out.splitlines()[-1] == ("NCAA-LISTING-PROBE: dates read 1 of 3; provider calls made: 2 HTTP GET(s); "
                                    "exit 1 (a provider error)")
    assert [c["params"]["date"] for c in net["calls"]] == ["2091-11-21", "2091-11-27"]


def test_a_429_retry_is_counted(net):
    net["codes"]["2091-11-21"] = [429]
    code, out = run(["--date", "2091-11-21"])
    assert code == 0
    assert out.splitlines()[-1] == "NCAA-LISTING-PROBE: dates read 1 of 1; provider calls made: 2 HTTP GET(s)"


@pytest.mark.parametrize("sidecar", ["-wal", "-shm", "-journal"])
def test_copy_with_a_sidecar_refused_before_any_call(tmp_path, net, sidecar):
    db = make_copy(tmp_path / "copy.db")
    (tmp_path / f"copy.db{sidecar}").write_bytes(b"")
    code, out = run(["--date", "2091-11-21", "--db", str(db)])
    assert code == 2 and f"copy.db{sidecar}" in out and "provider calls made: 0" in out
    assert net["calls"] == []


def test_copy_without_ncaa_refused(tmp_path, net):
    db = make_copy(tmp_path / "copy.db", ncaa=False)
    code, out = run(["--date", "2091-11-21", "--db", str(db)])
    assert code == 2 and "0 competitions coded NCAA in the copy, not one" in out
    assert net["calls"] == []


def test_missing_copy_refused_never_created(tmp_path, net):
    db = tmp_path / "absent.db"
    code, out = run(["--date", "2091-11-21", "--db", str(db)])
    assert code == 2 and "no file at" in out
    assert not db.exists() and net["calls"] == []


def test_fence_no_sync_rekey_or_repair_module_loaded(tmp_path):
    """In a fresh interpreter: the copy read and the per-row verdicts load no sync, re-key or repair module."""
    db = make_copy(tmp_path / "copy.db")
    code = (
        "import sys, json; sys.path.insert(0, 'scripts'); import ncaa_listing_probe as p\n"
        f"look, _ = p.read_copy({str(db)!r})\n"
        "f = p.raw_fields({'game': {'id': 1, 'date': {'timestamp': 1}}, 'teams': {'home': {'id': 101}, "
        "'away': {'id': 102}}})\n"
        "p.our_side(f, look)\n"
        "print(json.dumps(sorted(m for m in sys.modules if m.startswith('src.ingestion'))))\n")
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp_path / 'never.db'}"}
    res = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT, env=env, capture_output=True, text=True,
                         check=True)
    loaded = json.loads(res.stdout.strip().splitlines()[-1])
    assert loaded == ["src.ingestion", "src.ingestion.ncaa_cfbd"]
    assert not (tmp_path / "never.db").exists()


def test_a_malformed_key_never_printed_by_value(net, monkeypatch):
    """Pre-PR review (P1): requests puts a malformed header value in InvalidHeader's text; the probe prints the key's
    variable name in its place (414 item 3(c), the key by NAME only)."""
    import requests
    bad = KEY + "\n"
    monkeypatch.setenv("API_AMERICAN_FOOTBALL_KEY", bad)

    def preparing_get(url, headers=None, params=None, timeout=None):
        net["calls"].append({"url": url})
        requests.Request("GET", url, headers=headers, params=params).prepare()   # raises before anything is sent
        raise AssertionError("prepare() should have refused the header")

    monkeypatch.setattr(requests, "get", preparing_get)
    code, out = run(["--date", "2091-11-21"])
    assert code == 1
    assert KEY not in out and repr(bad)[1:-1] not in out
    assert "PROVIDER ERROR: InvalidHeader:" in out and "<API_AMERICAN_FOOTBALL_KEY>" in out


def test_redactor_forms():
    red = probe.redactor("K", {"K": " ab\r\n"})
    assert red("v=' ab\\r\\n' and ab and b' ab\\r\\n'") == "v='<K>' and <K> and b'<K>'"
    assert probe.redactor(None, {})("unchanged") == "unchanged"


def test_a_sidecar_check_that_cannot_stat_refuses(tmp_path, net):
    """Pre-PR review (P2): ENAMETOOLONG on '<name>-journal' (a 250-byte copy name) is a refusal, exit 2, never a
    traceback (intl_shadow.copy_sidecars leaves the wording to its caller)."""
    db = make_copy(tmp_path / "copy.db").rename(tmp_path / ("c" * 247 + ".db"))   # SQLite cannot create it there
    code, out = run(["--date", "2091-11-21", "--db", str(db)])
    assert code == 2
    assert "cannot check for a -wal, -shm or -journal beside the copy" in out and "provider calls made: 0" in out
    assert net["calls"] == []


def test_a_row_whose_verdict_fails_is_printed_and_the_run_goes_on(net):
    """Pre-PR review (P2): a row the verdict cannot be worked out for (a team name that is not text) is printed raw
    with VERDICT FAILED; the next rows and the closing count still print; exit 1."""
    net["pages"]["2091-11-21"] = [row(9001, 101, 102, hname=12345), row(9002, 101, 102)]
    code, out = run(["--date", "2091-11-21"])
    assert code == 1
    lines = out.splitlines()
    assert any(ln.startswith("  game=9001 ") and "home=101 12345" in ln and "VERDICT FAILED (TypeError" in ln
               for ln in lines)
    assert any(ln.startswith("  game=9002 ") and ln.endswith("-> kept by the parse") for ln in lines)
    assert lines[-1] == ("NCAA-LISTING-PROBE: dates read 1 of 1; provider calls made: 1 HTTP GET(s); 1 row(s) whose "
                         "verdict failed, each printed on its line; exit 1 (a row verdict failed)")


@pytest.mark.parametrize("argv", [["--dates", "2091-11-21"], ["--date"], ["--date", "2091-11-21", "--bogus"]])
def test_a_bad_command_line_is_a_refusal_with_the_count(net, argv):
    """Pre-PR review (nit): argparse's own errors print the REFUSED line with the call count, exit 2."""
    code, out = run(argv)
    assert code == 2 and out.startswith("NCAA-LISTING-PROBE REFUSED: ") and out.endswith("provider calls made: 0")
    assert net["calls"] == []


@pytest.mark.parametrize("season,label", [("2026", ""), ("2026/27", ""), ("2025", ", another season"),
                                          ("20261", ", season unknown"), ("", ", season unknown"),
                                          (None, ", season unknown")])
def test_the_stored_row_season_reads_as_season_year(season, label):
    look = {"teams": {"101": [(1, "A")], "102": [(2, "B")]},
            "holders": {"9": [{"id": 7, "season": season, "status": "SCHEDULED", "utc_date": "x"}]}, "prev": {}}
    f = probe.raw_fields(row(9, 101, 102))
    assert probe.our_side(f, look) == [f"stored as match 7 (season {season}{label}, SCHEDULED, x)"]
