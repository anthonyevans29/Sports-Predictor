"""ARCHITECT 2026-10-05 (#286): a read-only UNL ladder receipt (match, legs, bid/ask, spread, two-sided,
capture time, series) and the FROZEN favorite-skew test (docs/specs/unl-venue-skew-test.md): the first 30
fresh two-sided KXUEFANLGAME boards after the cutoff; gap = Kalshi (3-leg normalized mids) − book on the
book favorite; STRUCTURAL when the bootstrap 95% CI excludes 0. One-sided boards never count."""
from datetime import datetime, timedelta

from src.db import database
from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, OddsSnapshot, Sport, Team
from src.walters import unl_ladders as U

CUT = datetime(2094, 10, 5, 17, 0)
NOW = CUT + timedelta(days=3)


def _setup(monkeypatch):
    """The ticker column is unmapped and migration-added; the shared test DB is left
    untouched (another test pins its absence), so stored tickers are served by a stub."""
    init_db()
    tickers: dict = {}
    monkeypatch.setattr(database, "read_kalshi_tickers",
                        lambda s, ids: {i: tickers[i] for i in ids if i in tickers})
    with session_scope() as s:
        c = s.query(Competition).filter_by(code="UNL").one_or_none()
        if c is None:
            c = Competition(sport=Sport.SOCCER, code="UNL", name="UEFA Nations League", area="EU", type="INTL")
            s.add(c)
            s.flush()
        ids = {}

        def game(tag, ko, board=None, book=True, series="KXUEFANLGAME", cap_dt=timedelta(hours=1)):
            h, a = Team(sport=Sport.SOCCER, name=f"Rcpt {tag} H"), Team(sport=Sport.SOCCER, name=f"Rcpt {tag} A")
            s.add_all([h, a])
            s.flush()
            m = Match(sport=Sport.SOCCER, competition_id=c.id, season="2094/95", utc_date=ko,
                      status=MatchStatus.FINISHED, home_team_id=h.id, away_team_id=a.id, home_score=1, away_score=0)
            s.add(m)
            s.flush()
            at = ko - cap_dt
            pairs = []
            for sel, (bid, ask) in (board or {}).items():
                x = OddsSnapshot(match_id=m.id, market="1X2", selection=sel, devig_prob=ask, n_books=1,
                                 captured_at=at, source="kalshi", yes_bid=bid, yes_ask=ask)
                s.add(x)
                s.flush()
                pairs.append((x.id, f"{series}-94OCT{tag}-{sel[:3]}"))
            tickers.update(pairs)
            if book:
                for sel, p in (("HOME", 0.62), ("DRAW", 0.23), ("AWAY", 0.15)):
                    s.add(OddsSnapshot(match_id=m.id, market="1X2", selection=sel, devig_prob=p, n_books=5,
                                       captured_at=ko - timedelta(hours=2), source="odds_api"))
            ids[tag] = m.id

        good = {"HOME": (0.65, 0.66), "DRAW": (0.21, 0.22), "AWAY": (0.13, 0.14)}
        game("pre", CUT - timedelta(hours=1), good)                               # kicked off before the cutoff
        game("ok", CUT + timedelta(days=1), good)
        game("one", CUT + timedelta(days=1, hours=1), {**good, "AWAY": (None, 0.14)})   # one-sided board
        game("old", CUT + timedelta(hours=2), good, cap_dt=timedelta(hours=3))   # capture before the cutoff
        game("ser", CUT + timedelta(days=1, hours=2), good, series="KXCONCACAFNLGAME")
        game("nob", CUT + timedelta(days=1, hours=3), good, book=False)
        cid = c.id
    return ids, cid


def _drop(cid):
    with session_scope() as s:
        mids = [m.id for m in s.query(Match).filter(Match.competition_id == cid, Match.season == "2094/95")]
        s.query(OddsSnapshot).filter(OddsSnapshot.match_id.in_(mids)).delete(synchronize_session=False)
        s.query(Match).filter(Match.id.in_(mids)).delete(synchronize_session=False)


def test_receipt_rows_sample_and_every_exclusion_reason(monkeypatch):
    ids, cid = _setup(monkeypatch)
    with session_scope() as s:
        r = U.receipt(s, since=CUT, n=30, now=NOW)
    rows = {x["match_id"]: x for x in r["rows"]}
    assert ids["pre"] not in rows                                          # before the cutoff: not listed
    ok = rows[ids["ok"]]
    assert ok["qualifies"] and ok["series"] == "KXUEFANLGAME" and ok["two_sided"] and ok["favorite"] == "HOME"
    assert ok["legs"]["HOME"] == {"bid": 0.65, "ask": 0.66, "spread_c": 1.0, "two_sided": True,
                                  "ticker": "KXUEFANLGAME-94OCTok-HOM"}
    kn = 0.655 / (0.655 + 0.215 + 0.135)                                  # three-leg normalized mid
    assert abs(ok["gap_pp"] - (kn - 0.62) * 100) < 1e-12                   # full precision, never rounded
    assert rows[ids["one"]]["reason"] == "one-sided board (ruling 2)" and not rows[ids["one"]]["two_sided"]
    assert rows[ids["old"]]["reason"] == "last Kalshi capture not after the freeze cutoff"
    assert rows[ids["ser"]]["reason"].startswith("series KXCONCACAFNLGAME is not KXUEFANLGAME")
    assert rows[ids["nob"]]["reason"] == "no complete pre-kickoff book session"
    assert [x["match_id"] for x in r["sample"]] == [ids["ok"]] and not r["complete"]
    txt = U.format_receipt(r, with_test=True)
    assert "SAMPLE: 1/30 (incomplete)" in txt and "SKEW TEST: not run" in txt and "excluded: one-sided" in txt
    _drop(cid)


def test_frozen_skew_test_is_deterministic_and_reads_the_ci():
    flat = [3.0 + 0.1 * (i % 5) for i in range(30)]                       # Kalshi consistently above book
    t = U.skew_test(flat)
    assert t["verdict"] == "STRUCTURAL" and t["ci95"][0] > 0 and t["sign"] == "Kalshi above book on the favorite"
    assert U.skew_test(flat) == t                                          # seed 20261005: reproducible
    sym = [(-1) ** i * 2.0 for i in range(30)]
    s2 = U.skew_test(sym)
    assert s2["verdict"] == "NOT STRUCTURAL" and s2["ci95"][0] < 0 < s2["ci95"][1] and s2["sign"] is None
    assert U.skew_test([])["verdict"] is None


def test_cli_writes_the_receipt_and_refuses_data(tmp_path, monkeypatch):
    from click.testing import CliRunner

    import cli
    ids, cid = _setup(monkeypatch)
    out = tmp_path / "receipts" / "unl.txt"
    res = CliRunner().invoke(cli.cli, ["unl-ladder-receipt", "--since", CUT.isoformat(), "--out", str(out)])
    assert res.exit_code == 0, res.output
    assert out.exists() and "UNL ladder receipt" in out.read_text()
    bad = CliRunner().invoke(cli.cli, ["unl-ladder-receipt", "--out", "data/x.txt"])
    assert bad.exit_code == 2 and "REFUSED" in bad.output
    _drop(cid)


def test_review_fixes_partial_tickers_offsets_missing_comp_and_frozen_refusal(monkeypatch, tmp_path):
    """Codex on #291 (verified): a leg without a stored ticker makes the series UNKNOWN; an offset-bearing
    --since is normalized to naive UTC; a DB without UNL refuses cleanly; --skew-test refuses overrides."""
    from types import SimpleNamespace as NS

    from click.testing import CliRunner

    import cli
    ko = CUT + timedelta(days=1)
    m = NS(id=1, utc_date=ko, status=MatchStatus.FINISHED, home_team=None, away_team=None)
    legs = [NS(id=i, source="kalshi", market="1X2", selection=k, captured_at=ko - timedelta(hours=1),
               yes_bid=0.3, yes_ask=0.31) for i, k in enumerate(U.LEGS)]
    book = [NS(id=10 + i, source="odds_api", market="1X2", selection=k, captured_at=ko - timedelta(hours=2),
               devig_prob=p, n_books=5) for i, (k, p) in enumerate(zip(U.LEGS, (0.5, 0.3, 0.2)))]
    row = U.game_row(m, legs + book, {0: "KXUEFANLGAME-X-H", 1: "KXUEFANLGAME-X-D"}, CUT)   # AWAY untickered
    assert row["series"] is None and not row["qualifies"] and "UNKNOWN" in row["reason"]
    assert U.to_naive_utc(datetime.fromisoformat("2026-10-05T19:00:00+02:00")) == datetime(2026, 10, 5, 17, 0)
    assert U.format_receipt({"competition": "UNL", "error": "competition UNL not in DB", "rows": []}, True) \
        == "UNL ladder receipt · REFUSED: competition UNL not in DB"
    r = CliRunner().invoke(cli.cli, ["unl-ladder-receipt", "--skew-test", "--n", "1"])
    assert r.exit_code == 2 and "frozen cohort" in r.output
    r = CliRunner().invoke(cli.cli, ["unl-ladder-receipt", "--since", "2026-10-05T17:00:00+00:00", "--skew-test"])
    assert r.exit_code == 0, r.output                                      # the frozen cutoff, offset form


def test_second_review_fixes_boundary_n_and_ci_precision():
    """Codex on #291, round 2 (verified): a capture AT the cutoff is not after it; --n must be positive; the
    reported CI carries the exact bounds the verdict was decided on."""
    from types import SimpleNamespace as NS

    from click.testing import CliRunner

    import cli
    ko = CUT + timedelta(days=1)
    m = NS(id=1, utc_date=ko, status=MatchStatus.FINISHED, home_team=None, away_team=None)
    legs = [NS(id=i, source="kalshi", market="1X2", selection=k, captured_at=CUT, yes_bid=0.3, yes_ask=0.31)
            for i, k in enumerate(U.LEGS)]
    row = U.game_row(m, legs, {i: f"KXUEFANLGAME-X-{i}" for i in range(3)}, CUT)
    assert not row["qualifies"] and row["reason"] == "last Kalshi capture not after the freeze cutoff"
    assert CliRunner().invoke(cli.cli, ["unl-ladder-receipt", "--n", "0"]).exit_code == 2
    t = U.skew_test([0.0001 + 0.000001 * i for i in range(30)])          # bounds just above zero
    assert t["verdict"] == "STRUCTURAL" and t["ci95"][0] > 0 and round(t["ci95"][0], 3) == 0.0


def test_third_review_fixes_precision_seconds_and_resolved_data_guard(tmp_path, monkeypatch):
    """Codex on #291, round 3 (verified): the bootstrap gets UNROUNDED gaps; receipt timestamps keep
    seconds; the data/ guard resolves the target, so a symlink or a cwd inside data/ cannot bypass it."""
    from types import SimpleNamespace as NS

    from click.testing import CliRunner

    import cli
    ko = CUT + timedelta(days=1)
    m = NS(id=7, utc_date=ko, status=MatchStatus.FINISHED, home_team=None, away_team=None)
    at = CUT + timedelta(seconds=30)
    legs = [NS(id=i, source="kalshi", market="1X2", selection=k, captured_at=at, yes_bid=b, yes_ask=b + 0.01)
            for i, (k, b) in enumerate(zip(U.LEGS, (0.5, 0.29, 0.19)))]
    book = [NS(id=10 + i, source="odds_api", market="1X2", selection=k, captured_at=at - timedelta(hours=1),
               devig_prob=p, n_books=5) for i, (k, p) in enumerate(zip(U.LEGS, (0.505, 0.3, 0.195)))]
    row = U.game_row(m, legs + book, {i: f"KXUEFANLGAME-X-{i}" for i in range(3)}, CUT)
    assert row["qualifies"] and row["gap_pp"] != round(row["gap_pp"], 3)    # carried unrounded
    txt = U.format_receipt({"competition": "UNL", "since": CUT, "n": 30, "rows": [row], "sample": [row],
                            "complete": False}, with_test=False)
    assert "capture 2094-10-05T17:00:30Z" in txt                            # seconds kept
    data = tmp_path / "data"                     # a stand-in: the real data/ is never touched (law 5)
    data.mkdir()
    monkeypatch.setattr(U, "data_dir", lambda: data.resolve())
    link = tmp_path / "current"
    link.symlink_to(data, target_is_directory=True)
    r = CliRunner().invoke(cli.cli, ["unl-ladder-receipt", "--out", str(link / "x.txt")])
    assert r.exit_code == 2 and "REFUSED" in r.output and not (data / "x.txt").exists()
    monkeypatch.chdir(data)
    r = CliRunner().invoke(cli.cli, ["unl-ladder-receipt", "--out", "y.txt"])
    assert r.exit_code == 2 and not (data / "y.txt").exists()


def test_malformed_since_is_a_usage_error():
    """Codex on #291, round 4 (verified): a malformed --since exits 2 with a usage message, not a traceback."""
    from click.testing import CliRunner

    import cli
    r = CliRunner().invoke(cli.cli, ["unl-ladder-receipt", "--since", "2026-13-40"])
    assert r.exit_code == 2 and "--since" in r.output and "not an ISO date-time" in r.output
