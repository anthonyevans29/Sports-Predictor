"""ARCHITECT 2026-10-07 (venue-edge quote age) build steps (3) and (4), READ-ONLY:
(3) venue-calls-receipt — every VENUE call on file (--desk fixtures exports + the ledger's venue_edge claims) with
the book consensus at the call and at each later pre-kickoff capture, and whether it ever moved at 4 dp;
(4) quote-age-report — MLB/NFL/PL rows decided against a book reference: capture age at decision and the
"unchanged since" age from our own captures (capture-based proxies, never quote age)."""
import json
from datetime import datetime, timedelta

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, OddsSnapshot, Sport, Team
from src.walters import venue_quote_age as VQ

KO = datetime(2095, 10, 9, 0, 0)
SINCE = datetime(2095, 10, 2)


def _iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%S")


_N = [0]


def _seed():
    """Each call seeds its own teams (unique names, so a by-name ledger lookup is never ambiguous across tests).
    NHL-like matches with BOOK capture sessions (source api_hockey) and kalshi rows (never a consensus)."""
    init_db()
    with session_scope() as s:
        c = s.query(Competition).filter_by(code="VQA").one_or_none()
        if c is None:
            c = Competition(sport=Sport.NHL, code="VQA", name="Quote-age test league", area="X", type="LEAGUE")
            s.add(c)
            s.flush()
        ids = {}
        _N[0] += 1
        ids["n"] = n = _N[0]

        def game(tag, sessions, sport=Sport.NHL, comp=c, ko=KO):
            h = Team(sport=sport, name=f"VQA{n} {tag} Home")
            a = Team(sport=sport, name=f"VQA{n} {tag} Away")
            s.add_all([h, a])
            s.flush()
            m = Match(sport=sport, competition_id=comp.id, season="2095", utc_date=ko,
                      status=MatchStatus.SCHEDULED, home_team_id=h.id, away_team_id=a.id)
            s.add(m)
            s.flush()
            for hours_before, fair, books in sessions:
                t = ko - timedelta(hours=hours_before)
                for sel, p in fair.items():
                    s.add(OddsSnapshot(match_id=m.id, market="1X2", selection=sel, devig_prob=p, n_books=books,
                                       captured_at=t, source="api_hockey" if sport != Sport.SOCCER else "api_football"))
            s.add(OddsSnapshot(match_id=m.id, market="ML", selection="HOME", devig_prob=0.545, n_books=1,
                               captured_at=ko - timedelta(hours=5), source="kalshi"))
            ids[tag] = m.id
            return m

        dead = {"HOME": 0.4735, "AWAY": 0.5265}
        game("dead", [(30, dead, 5), (26, dead, 5), (20, dead, 5), (10, dead, 5), (2, dead, 5), (-1, {"HOME": 0.6, "AWAY": 0.4}, 5)])
        game("move", [(20, dead, 5), (10, dead, 5), (2, {"HOME": 0.4736, "AWAY": 0.5264}, 6)])
        game("last", [(24, {"HOME": 0.50, "AWAY": 0.50}, 4), (20, dead, 5)])
        game("nfl", [(30, {"HOME": 0.61, "AWAY": 0.39}, 7), (12, {"HOME": 0.6, "AWAY": 0.4}, 7),
                     (8, {"HOME": 0.6, "AWAY": 0.4}, 8)], sport=Sport.NFL)
    return ids


def _venue_row(mid, tag, cap_h, fair, call="VENUE", side="AWAY", n=0):
    return {"match_id": mid, "utc_date": _iso(KO), "status": "scheduled", "home_team": f"VQA{n} {tag} Home",
            "away_team": f"VQA{n} {tag} Away",
            "market": {"bookmaker_count": 5, "fair_prob": fair, "fair_source": "1X2",
                       "captured_at": _iso(KO - timedelta(hours=cap_h))},
            "desk": {"engine": "venue_edge", "call": call, "units": 0.25 if call == "VENUE" else 0, "side": side,
                     "div_pp": 7.15, "book_p": 0.5265, "kalshi_p": 0.455}}


def _exports(tmp_path, ids):
    ex = tmp_path / "exports"
    (ex / "host").mkdir(parents=True)
    dead = {"HOME": 0.4735, "AWAY": 0.5265}
    asof = _iso(KO - timedelta(hours=19)) + "Z"
    doc = {"competition_code": "NHL", "desk_meta": {"as_of": asof}, "fixtures": [
        _venue_row(ids["dead"], "dead", 20, dead, n=ids["n"]), _venue_row(ids["move"], "move", 20, dead, n=ids["n"]),
        _venue_row(ids["last"], "last", 20, dead, n=ids["n"]),
        _venue_row(ids["dead"], "dead", 20, dead, call="PASS", n=ids["n"])]}
    (ex / "fixtures_NHL_2095-10-08.json").write_text(json.dumps(doc))
    (ex / "host" / "fixtures_NHL_2095-10-08.json").write_text(json.dumps(doc))      # a copy: same calls
    old = {**doc, "desk_meta": {"as_of": "2095-09-30T12:00:00Z"}}
    (ex / "fixtures_NHL_2095-09-30.json").write_text(json.dumps(old))              # before --since
    (ex / "broken.json").write_text("{")
    nfl = {"sport": "nfl", "desk_meta": {"as_of": _iso(KO - timedelta(hours=6)) + "Z"}, "predictions": [
        {"match_id": ids["nfl"], "utc_date": _iso(KO), "home_team": "VQA nfl Home", "away_team": "VQA nfl Away",
         "market": {"bookmaker_count": 8, "fair_prob": {"HOME": 0.6, "AWAY": 0.4}, "fair_source": "1X2"},
         "desk": {"engine": "model_edge", "call": "PLAY", "reference": "books", "pass_kind": None}},
        {"match_id": ids["nfl"] + 99999, "utc_date": _iso(KO),
         "desk": {"engine": "model_edge", "call": "PASS", "reference": None, "pass_kind": "noref"}}]}
    (ex / "nfl_predictions_2095-10-08.json").write_text(json.dumps(nfl))
    return ex


def test_venue_receipt_consensus_at_the_call_later_captures_and_verdicts(tmp_path):
    ids = _seed()
    ex = _exports(tmp_path, ids)
    docs, cnt = VQ.iter_desk_docs(str(ex))
    assert cnt["unreadable"] == 1 and cnt["desk_files"] == 4
    calls = VQ.file_venue_calls(docs, SINCE)
    assert len(calls) == 3                                                    # PASS row, old file: not calls
    assert all(len(c["files"]) == 2 for c in calls)                          # the host copy is the same call
    with session_scope() as s:
        res = VQ.venue_receipt(s, calls)
    by = {r["match_id"]: r for r in res["rows"]}
    d = by[ids["dead"]]
    assert d["verdict"] == "NEVER MOVED" and d["file_matches_anchor"] is True
    assert d["anchor"]["t"] == KO - timedelta(hours=20) and d["anchor_basis"].startswith("the capture at")
    assert [x["t"] for x in d["later"]] == [KO - timedelta(hours=10), KO - timedelta(hours=2)]   # never post-KO
    assert d["unchanged_since"] == KO - timedelta(hours=30) and d["run_n"] == 3 and d["run_censored"] is True
    m = by[ids["move"]]
    assert m["verdict"] == "MOVED" and [x["moved"] for x in m["later"]] == [False, True]
    lst = by[ids["last"]]
    assert lst["verdict"] == "NO LATER CAPTURE" and lst["moved"] is None
    assert lst["unchanged_since"] == KO - timedelta(hours=20) and lst["run_censored"] is False
    t = res["totals"]
    assert (t["calls"], t["tested"], t["NEVER MOVED"], t["MOVED"], t["NO LATER CAPTURE"]) == (3, 2, 1, 1, 1)
    assert t["never_moved_share_of_tested"] == 0.5
    txt = "\n".join(VQ.format_venue_receipt(res, SINCE, ["test"]))
    assert "AT THE CALL (file): HOME 0.4735 / AWAY 0.5265 · books 5" in txt
    assert "TOTALS · calls 3 · tested (>= 1 later pre-kickoff capture) 2 · NEVER MOVED 1 (50.0% of tested" in txt


def test_ledger_claims_merge_with_file_calls_or_stand_alone():
    ids = _seed()
    asof, n = KO - timedelta(hours=19), ids["n"]
    file_call = {"origin": "file", "files": ["f"], "in_ledger": False, "as_of": asof, "sport": "NHL",
                 "match_id": ids["dead"], "home": f"VQA{n} dead Home", "away": f"VQA{n} dead Away", "kickoff": KO,
                 "side": "AWAY", "units": 0.25, "div_pp": 7.15, "book_p": 0.5265, "kalshi_p": 0.455,
                 "file_fair": {"HOME": 0.4735, "AWAY": 0.5265}, "file_books": 5,
                 "file_captured_at": KO - timedelta(hours=20), "fair_source": "1X2"}
    L = {"calls": [
        {"engine": "venue_edge", "sport": "NHL", "home": f"VQA{n} dead Home", "away": f"VQA{n} dead Away",
         "kickoff": _iso(KO), "pick": "AWAY", "units": 0.25, "claim_as_of": _iso(asof) + "Z", "model_p": 0.5265},
        {"engine": "venue_edge", "sport": "NHL", "home": f"VQA{n} move Home", "away": f"VQA{n} move Away",
         "kickoff": _iso(KO), "pick": "AWAY", "units": 0.25, "claim_as_of": _iso(KO - timedelta(hours=9)) + "Z"},
        {"engine": "model_edge", "sport": "NFL", "claim_as_of": _iso(asof) + "Z"},
        {"engine": "venue_edge", "sport": "NHL", "claim_as_of": "2095-09-01T00:00:00Z"}]}
    lc = VQ.ledger_venue_calls(L, SINCE)
    assert len(lc) == 2
    calls = VQ.merge_calls([file_call], lc)
    assert len(calls) == 2 and calls[0]["in_ledger"] is True
    with session_scope() as s:
        res = VQ.venue_receipt(s, calls)
    ledger_only = [r for r in res["rows"] if r["origin"] == "ledger"][0]
    assert ledger_only["match_id"] == ids["move"]                                       # resolved by names ±12h
    assert ledger_only["anchor"]["t"] == KO - timedelta(hours=10)                     # last capture <= claim time
    assert ledger_only["anchor_basis"].startswith("last capture at or before the call time")
    assert ledger_only["verdict"] == "MOVED"
    with session_scope() as s:
        m, why = VQ.resolve_match(s, {"home": "Nobody", "away": f"VQA{n} move Away", "kickoff": KO})
    assert m is None and "not guessed" in why


def test_age_report_capture_age_and_unchanged_age_are_proxies(tmp_path):
    ids = _seed()
    ex = _exports(tmp_path, ids)
    docs, _ = VQ.iter_desk_docs(str(ex))
    rows = VQ.model_reference_rows(docs, SINCE)
    assert [r["match_id"] for r in rows] == [ids["nfl"]]                       # noref row: no book reference
    with session_scope() as s:
        rep = VQ.age_report(s, docs, SINCE)
    b = rep["by_sport"]["NFL"]
    assert (b["rows"], b["with_capture"], b["file_matches"]) == (1, 1, 1)
    assert b["capture_age_h"]["median"] == 2.0                                 # as_of KO-6h − capture KO-8h
    assert b["unchanged_age_h"]["max"] == 6.0 and b["censored"] == 0          # identical since KO-12h
    assert b["unchanged_ge_3h"] == 1
    assert rep["by_sport"]["MLB"]["rows"] == 0 and rep["by_sport"]["PL"]["capture_age_h"]["median"] is None
    txt = "\n".join(VQ.format_age_report(rep, SINCE, ["test"]))
    assert "NOT quote age" in txt and "capture age   median 2.00h" in txt


def test_sessions_need_every_outcome_and_ignore_kalshi():
    class X:
        def __init__(self, sel, p, t, src="api_football", market="1X2"):
            self.selection, self.devig_prob, self.captured_at, self.source, self.market = sel, p, t, src, market
            self.n_books = 3
    t = datetime(2095, 1, 1)
    snaps = [X("HOME", 0.5, t), X("AWAY", 0.3, t),                                  # no DRAW: not a price
             X("HOME", 0.5, t + timedelta(hours=1)), X("DRAW", 0.25, t + timedelta(hours=1)),
             X("AWAY", 0.25, t + timedelta(hours=1)), X("HOME", 0.9, t, src="kalshi")]
    ss = VQ.sessions_from_snapshots(snaps, ("HOME", "DRAW", "AWAY"))
    assert len(ss) == 1 and ss[0]["fair4"] == {"HOME": 0.5, "DRAW": 0.25, "AWAY": 0.25}
    assert VQ.pct([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 0.9) == 9 and VQ.pct([], 0.5) is None


def test_cli_commands_run_read_only_and_refuse_data(tmp_path, monkeypatch):
    from click.testing import CliRunner

    import cli
    from src.walters import unl_ladders as U
    ids = _seed()
    ex = _exports(tmp_path, ids)
    out = tmp_path / "receipts" / "v.txt"
    r = CliRunner().invoke(cli.cli, ["venue-calls-receipt", "--since", "2095-10-02", "--exports-dir", str(ex),
                                     "--out", str(out)])
    assert r.exit_code == 0, r.output
    assert "VENUE CALLS RECEIPT" in out.read_text() and "ledger: not read" in r.output
    r = CliRunner().invoke(cli.cli, ["quote-age-report", "--since", "2095-10-02", "--exports-dir", str(ex)])
    assert r.exit_code == 0 and "MODEL-SPORT REFERENCE AGE" in r.output, r.output
    bad = tmp_path / "x.json"
    bad.write_text("[]")
    assert CliRunner().invoke(cli.cli, ["venue-calls-receipt", "--exports-dir", str(ex), "--ledger",
                                        str(bad)]).exit_code == 2
    assert CliRunner().invoke(cli.cli, ["quote-age-report", "--since", "nope"]).exit_code == 2
    data = tmp_path / "data"                                                   # a stand-in (law 5)
    data.mkdir()
    monkeypatch.setattr(U, "data_dir", lambda: data.resolve())
    for cmd in ("venue-calls-receipt", "quote-age-report"):
        r = CliRunner().invoke(cli.cli, [cmd, "--exports-dir", str(ex), "--out", str(data / "r.txt")])
        assert r.exit_code == 2 and "REFUSED" in r.output and not (data / "r.txt").exists()
