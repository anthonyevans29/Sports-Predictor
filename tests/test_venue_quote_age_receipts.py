"""ARCHITECT 2026-10-07 (venue-edge quote age) build steps (3) and (4), READ-ONLY:
(3) venue-calls-receipt — every VENUE call on file (--desk fixtures exports + the ledger's venue_edge claims) with
the book consensus at the call and at each later pre-kickoff capture, and whether it ever moved at 4 dp;
(4) quote-age-report — MLB/NFL/PL rows decided against a book reference: capture age at decision and the
"unchanged since" age from our own captures (capture-based proxies, never quote age)."""
import json
from datetime import datetime, timedelta

import pytest

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
        {"match_id": ids["nfl"], "utc_date": _iso(KO), "home_team": f"VQA{ids['n']} nfl Home",
         "away_team": f"VQA{ids['n']} nfl Away",
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


def test_a_manual_claim_merges_by_position_identity_not_exact_as_of():
    # Codex on #340: a manual "Log today's calls" claim is stamped at the click (claim_at), never the file's
    # desk_meta.as_of; it is the same position, so it merges onto the latest file call at or before the click.
    t1, t2 = KO - timedelta(hours=20), KO - timedelta(hours=8)
    def fc(asof):
        return {"origin": "file", "files": ["f"], "in_ledger": False, "as_of": asof, "sport": "NHL",
                "match_id": None, "home": "H", "away": "A", "kickoff": KO, "side": "AWAY", "reprices": [],
                "claim_basis": None}
    files = [fc(t1), fc(t2)]
    click = KO - timedelta(hours=7, minutes=43, seconds=17)
    L = {"calls": [{"engine": "venue_edge", "sport": "NHL", "home": "H", "away": "A", "kickoff": _iso(KO),
                    "pick": "AWAY", "claim_at": _iso(click) + "Z",
                    "reprices": [{"at": _iso(click) + "Z"}, {"at": _iso(KO - timedelta(hours=1)) + "Z"}]}]}
    calls = VQ.merge_calls(files, VQ.ledger_venue_calls(L, SINCE))
    assert len(calls) == 2                                               # no extra ledger-only row
    assert [c["in_ledger"] for c in calls] == [False, True]              # the t2 file: latest at/before click
    assert "matched by position identity" in calls[1]["claim_basis"]
    assert calls[1]["reprices"] == [KO - timedelta(hours=1)]
    # a manual claim BEFORE any file call of that position is never guessed onto a later file: its own row
    early = {"calls": [dict(L["calls"][0], claim_at=_iso(t1 - timedelta(hours=1)) + "Z", reprices=[])]}
    calls = VQ.merge_calls([fc(t1)], VQ.ledger_venue_calls(early, SINCE))
    assert len(calls) == 2 and calls[1]["in_ledger"] is False and calls[0]["origin"] == "ledger"


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


# ---- Codex on #340 -------------------------------------------------------------------------------------------

def _doc(rows, asof, code="NHL"):
    return {"competition_code": code, "desk_meta": {"as_of": _iso(asof) + "Z"}, "fixtures": rows}


def test_relogged_ledger_position_anchors_at_the_frozen_claim_and_is_one_call():
    """upsertCalls() re-log: top-level claim_as_of / captured_at = the NEWEST file's; claim_at keeps the first
    claim; reprices[] lists every capture. The receipt anchors at claim_at and merges with the original export."""
    ids = _seed()
    n, asof, relog = ids["n"], KO - timedelta(hours=19), KO - timedelta(hours=9)
    dead = {"HOME": 0.4735, "AWAY": 0.5265}
    fc = VQ.file_venue_calls([("f.json", _doc([_venue_row(ids["dead"], "dead", 20, dead, n=n)], asof))], SINCE)
    L = {"calls": [{"engine": "venue_edge", "sport": "NHL", "home": f"VQA{n} dead Home", "away": f"VQA{n} dead Away",
                    "kickoff": _iso(KO), "pick": "AWAY", "units": 0.25,
                    "claim_at": asof.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    "claim_as_of": _iso(relog) + "Z", "captured_at": relog.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    "reprices": [{"at": asof.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "market_p": 0.455},
                                 {"at": relog.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "market_p": 0.46}]}]}
    lc = VQ.ledger_venue_calls(L, SINCE)
    assert lc[0]["as_of"] == asof and lc[0]["claim_basis"].startswith("claim_at")
    assert lc[0]["reprices"] == [relog]
    calls = VQ.merge_calls(fc, lc)
    assert len(calls) == 1 and calls[0]["in_ledger"] is True and calls[0]["reprices"] == [relog]
    with session_scope() as s:
        res = VQ.venue_receipt(s, calls)
    assert res["totals"]["calls"] == 1 and res["totals"]["reprices"] == 1
    assert res["rows"][0]["anchor"]["t"] == KO - timedelta(hours=20)
    txt = "\n".join(VQ.format_venue_receipt(res, SINCE, ["t"]))
    assert "re-logged 1 time(s) after the claim (one position, not extra calls)" in txt
    old = {**L["calls"][0]}
    del old["claim_at"]                                         # pre-timing position: unfrozen, labelled
    t, basis = VQ.claim_time(old)
    assert t == relog and "unfrozen" in basis


def test_a_colliding_local_match_id_naming_another_game_is_not_attached(tmp_path):
    ids = _seed()
    n, asof = ids["n"], KO - timedelta(hours=19)
    dead = {"HOME": 0.4735, "AWAY": 0.5265}
    wrong = _venue_row(ids["move"], "dead", 20, dead, n=n)                  # the id is ANOTHER game in this DB
    ghost = {**_venue_row(ids["move"], "ghost", 20, dead, n=n)}             # teams this DB does not know
    calls = VQ.file_venue_calls([("f.json", _doc([wrong, ghost], asof))], SINCE)
    with session_scope() as s:
        res = VQ.venue_receipt(s, calls)
        m, how = VQ.resolve_match(s, {**calls[0], "match_id": ids["dead"]})
    assert how == "match_id (verified: teams + kickoff)" and m.id == ids["dead"]
    by = {r["home"]: r for r in res["rows"]}
    w = by[f"VQA{n} dead Home"]
    assert w["match_id"] == ids["dead"] and w["export_match_id"] == ids["move"]   # resolved by identity
    assert "is a different game in this DB" in w["resolved_by"]
    g = by[f"VQA{n} ghost Home"]
    assert g["verdict"] == "NO DB MATCH" and g["match_id"] is None and "not guessed" in g["anchor_basis"]
    assert all(r["match_id"] != ids["move"] for r in res["rows"])


def test_a_mirrored_host_file_resolves_by_identity_never_by_its_foreign_id(tmp_path):
    ids = _seed()
    n, asof = ids["n"], KO - timedelta(hours=19)
    dead = {"HOME": 0.4735, "AWAY": 0.5265}
    ex = tmp_path / "exports"
    (ex / "host").mkdir(parents=True)
    host_rows = [_venue_row(ids["move"], "dead", 20, dead, n=n),           # host id collides with "move" here
                 _venue_row(10 ** 9, "last", 20, dead, n=n)]               # host id absent here
    (ex / "host" / "fixtures_NHL_2095-10-08.json").write_text(json.dumps(_doc(host_rows, asof)))
    docs, cnt = VQ.iter_desk_docs(str(ex))
    assert cnt["mirrored"] == [str(ex / "host" / "fixtures_NHL_2095-10-08.json")]
    calls = VQ.file_venue_calls(docs, SINCE, cnt["mirrored"])
    assert all(c["match_id"] is None and c["foreign_ids"] for c in calls)
    with session_scope() as s:
        res = VQ.venue_receipt(s, calls)
    got = {r["home"]: r["match_id"] for r in res["rows"]}
    assert got == {f"VQA{n} dead Home": ids["dead"], f"VQA{n} last Home": ids["last"]}
    assert all(r["resolved_by"].startswith("identity") for r in res["rows"])
    nfl = {"sport": "nfl", "desk_meta": {"as_of": _iso(KO - timedelta(hours=6)) + "Z"}, "predictions": [
        {"match_id": ids["dead"], "utc_date": _iso(KO), "home_team": f"VQA{n} nfl Home",
         "away_team": f"VQA{n} nfl Away", "market": {"fair_prob": {"HOME": 0.6, "AWAY": 0.4}, "fair_source": "1X2"},
         "desk": {"engine": "model_edge", "call": "PLAY", "reference": "books"}}]}
    (ex / "host" / "nfl_predictions_2095-10-08.json").write_text(json.dumps(nfl))
    docs, cnt = VQ.iter_desk_docs(str(ex))
    with session_scope() as s:
        rep = VQ.age_report(s, docs, SINCE, cnt["mirrored"])
    r = [x for x in rep["rows"] if x["sport"] == "NFL"][0]
    assert r["match_id"] == ids["nfl"] and r["foreign_ids"] == [ids["dead"]]
    assert r["excluded"].startswith("mirrored host export")          # resolved by identity, never measured locally


def test_age_statistics_measure_only_rows_whose_reference_session_is_verified(tmp_path):
    ids = _seed()
    n = ids["n"]
    ex = tmp_path / "exports"
    ex.mkdir()

    def row(fair, src="1X2"):
        return {"match_id": ids["nfl"], "utc_date": _iso(KO), "home_team": f"VQA{n} nfl Home",
                "away_team": f"VQA{n} nfl Away", "market": {"fair_prob": fair, "fair_source": src},
                "desk": {"engine": "model_edge", "call": "PLAY", "reference": "books"}}
    for h, r in ((6, row({"HOME": 0.6, "AWAY": 0.4})),                       # verified: capture age 2h
                 (5, row({"HOME": 0.7, "AWAY": 0.3})),                       # file != capture: unverified
                 (4, row({"HOME": 0.6, "AWAY": 0.4}, "spread_derived"))):    # no 1X2 fair: unverifiable
        doc = {"sport": "nfl", "desk_meta": {"as_of": _iso(KO - timedelta(hours=h)) + "Z"}, "predictions": [r]}
        (ex / f"nfl_predictions_{h}.json").write_text(json.dumps(doc))
    docs, _ = VQ.iter_desk_docs(str(ex))
    with session_scope() as s:
        rep = VQ.age_report(s, docs, SINCE)
    b = rep["by_sport"]["NFL"]
    assert (b["rows"], b["with_capture"], b["measured"], b["excluded"]) == (3, 3, 1, 2)
    assert (b["file_matches"], b["file_mismatch"], b["file_unverifiable"]) == (1, 1, 1)
    assert b["capture_age_h"] == {"median": 2.0, "p90": 2.0, "max": 2.0}     # the 3h / 4h rows never enter
    reasons = sorted(x["excluded"] for x in rep["rows"] if x["excluded"])
    assert reasons == ["session unverified: file fair != the selected capture at 4dp (snapshot mismatch; no stored "
                       "odds rows for that session to re-derive)",
                       "session unverified: the file carries no 1X2 fair to compare"]
    txt = "\n".join(VQ.format_age_report(rep, SINCE, ["t"]))
    assert "measured (verified) 1 · excluded 2" in txt and "EXCLUDED from the statistics: 2" in txt


def test_a_missing_exports_dir_and_a_damaged_ledger_are_refused(tmp_path):
    """Codex on #340: a path error or a damaged ledger is refused (exit 2), never reported as an empty audit."""
    from click.testing import CliRunner

    import cli
    from src.walters import venue_quote_age as VQ
    afile = tmp_path / "afile"
    afile.write_text("x")
    for root in (tmp_path / "exprots", afile):
        with pytest.raises(VQ.Refused, match="not a directory"):
            VQ.iter_desk_docs(str(root))
        for cmd in ("venue-calls-receipt", "quote-age-report"):
            r = CliRunner().invoke(cli.cli, [cmd, "--exports-dir", str(root)])
            assert r.exit_code == 2 and "not a directory" in " ".join(r.output.split()), r.output
    ex = tmp_path / "exports"
    ex.mkdir()
    assert VQ.ledger_refusal({"calls": [{"engine": "venue_edge"}]}) is None
    for L in ({"calls": [{"engine": "venue_edge"}, None, "x"]}, {"calls": [7]}):
        assert "non-object" in VQ.ledger_refusal(L)
    led = tmp_path / "ledger.json"
    led.write_text(json.dumps({"calls": [{"engine": "venue_edge"}, None]}))
    r = CliRunner().invoke(cli.cli, ["venue-calls-receipt", "--exports-dir", str(ex), "--ledger", str(led)])
    assert r.exit_code == 2 and "non-object entry (index 1)" in " ".join(r.output.split()), r.output


def test_a_legacy_post_kickoff_row_is_excluded_by_its_timestamps():
    """Codex on #340: a file older than the started-game rule has no pass_kind; a row decided at or after kickoff
    is still no decision, and never inflates the capture / unchanged ages."""
    def row(mid, kick):
        return {"match_id": mid, "home_team": "H", "away_team": "A", "utc_date": _iso(kick),
                "desk": {"engine": "model_edge", "reference": "books", "call": "PASS"}}
    asof = KO
    doc = {"competition_code": "NFL", "desk_meta": {"as_of": _iso(asof) + "Z"},
           "predictions": [row(1, KO - timedelta(hours=1)), row(2, KO), row(3, KO + timedelta(hours=2))]}
    rows = VQ.model_reference_rows([("legacy.json", doc)], SINCE)
    assert [r["match_id"] for r in rows] == [3]


def test_every_excluded_row_is_listed():
    """Codex on #340: the report says every excluded row is listed with its reason, so none is truncated."""
    rows = [{"sport": "MLB", "home": f"H{i}", "away": f"A{i}", "kickoff": KO, "as_of": KO - timedelta(hours=1),
             "excluded": "no capture at or before as_of"} for i in range(75)]
    txt = VQ.format_age_report({"by_sport": {}, "rows": rows}, SINCE, ["test"])
    assert "EXCLUDED from the statistics: 75" in txt
    assert sum(1 for line in txt if line.startswith("  MLB · A")) == 75 and not any("more" in x for x in txt[-3:])


def test_an_nfl_session_is_verified_from_its_odds_rows_with_the_exports_formula():
    """Codex on #340: sync-odds-football de-vigs the snapshot by average-then-normalise; the export's fair is per-book
    normalise-then-average (close_1x2). With books of different overround they differ at 4dp, so a mismatched
    snapshot is re-derived from the same session's odds rows with the export's formula before it is excluded."""
    from src.db.schema import Odds
    ids = _seed()
    t = KO - timedelta(hours=8)                                  # the nfl game's last pre-as_of session
    px = {"BookA": {"HOME": 1.50, "AWAY": 2.80}, "BookB": {"HOME": 1.60, "AWAY": 2.30}}
    per_book = [{k: (1 / p[k]) / sum(1 / v for v in p.values()) for k in p} for p in px.values()]
    file_fair = {k: round(sum(b[k] for b in per_book) / len(per_book), 4) for k in ("HOME", "AWAY")}
    imp = {k: sum(1 / p[k] for p in px.values()) / 2 for k in ("HOME", "AWAY")}
    snap_fair = {k: round(v / sum(imp.values()), 4) for k, v in imp.items()}
    assert snap_fair != file_fair                                 # the two formulas really differ here
    with session_scope() as s:
        for bk, p in px.items():
            for sel, d in p.items():
                s.add(Odds(match_id=ids["nfl"], bookmaker=bk, market="1X2", selection=sel, price_decimal=d,
                           captured_at=t, source="api_hockey"))
    n = ids["n"]

    def doc(fair):
        return {"sport": "nfl", "desk_meta": {"as_of": _iso(KO - timedelta(hours=6)) + "Z"}, "predictions": [
            {"match_id": ids["nfl"], "utc_date": _iso(KO), "home_team": f"VQA{n} nfl Home",
             "away_team": f"VQA{n} nfl Away",
             "market": {"bookmaker_count": 2, "fair_prob": fair, "fair_source": "1X2"},
             "desk": {"engine": "model_edge", "call": "PLAY", "reference": "books", "pass_kind": None}}]}
    with session_scope() as s:
        rep = VQ.age_report(s, [("nfl.json", doc(file_fair))], SINCE)
        bad = VQ.age_report(s, [("nfl.json", doc({"HOME": 0.7, "AWAY": 0.3}))], SINCE)
    r = rep["rows"][0]
    assert r["file_matches"] is True and r["excluded"] is None and "per-book de-vig" in r["verified_by"]
    assert rep["by_sport"]["NFL"]["measured"] == 1
    b = bad["rows"][0]
    assert b["file_matches"] is False and "AND on the session's odds rows" in b["excluded"]


def test_same_identity_files_with_different_market_numbers_are_not_merged():
    """Codex on #340: a laptop export and a mirrored host export with the same teams / kickoff / side / as_of are
    copies only when their market numbers agree; otherwise both calls are kept and flagged as conflicting."""
    asof = KO - timedelta(hours=19)
    a = _venue_row(1, "x", 20, {"HOME": 0.4735, "AWAY": 0.5265})
    b = _venue_row(1, "x", 20, {"HOME": 0.4800, "AWAY": 0.5200})
    same = VQ.file_venue_calls([("l.json", _doc([a], asof)), ("h/l.json", _doc([dict(a)], asof))], SINCE, ["h/l.json"])
    assert len(same) == 1 and same[0]["files"] == ["l.json", "h/l.json"] and not same[0]["conflicting_copies"]
    diff = VQ.file_venue_calls([("l.json", _doc([a], asof)), ("h/l.json", _doc([b], asof))], SINCE, ["h/l.json"])
    assert len(diff) == 2 and all(c["conflicting_copies"] for c in diff)
    assert sorted(c["file_fair"]["HOME"] for c in diff) == [0.4735, 0.48]
    init_db()
    with session_scope() as s:
        res = VQ.venue_receipt(s, diff)                          # unseeded names: NO DB MATCH, still listed
    assert sum("CONFLICT:" in x for x in VQ.format_venue_receipt(res, SINCE, ["t"])) == 2


def test_a_ledger_claim_picks_the_conflicting_row_it_names_or_none():
    """Codex on #340: with conflicting file rows kept, an exact-time ledger claim attaches to the row whose book p /
    Kalshi p / div it carries; if none or several fit, it is attached to none and both rows say so."""
    asof = KO - timedelta(hours=19)
    a = _venue_row(1, "x", 20, {"HOME": 0.4735, "AWAY": 0.5265})
    b = _venue_row(1, "x", 20, {"HOME": 0.4800, "AWAY": 0.5200})
    b["desk"] = dict(b["desk"], book_p=0.52, div_pp=6.5)

    def files():
        return VQ.file_venue_calls([("l.json", _doc([a], asof)), ("h/l.json", _doc([b], asof))], SINCE)

    def claim(**kw):
        return {"calls": [dict({"engine": "venue_edge", "sport": "NHL", "home": "VQA0 x Home", "away": "VQA0 x Away",
                                "kickoff": _iso(KO), "pick": "AWAY", "claim_at": _iso(asof) + "Z"}, **kw)]}
    calls = VQ.merge_calls(files(), VQ.ledger_venue_calls(claim(model_p=0.52, divergence_pp=6.5), SINCE))
    assert len(calls) == 2 and [c["file_fair"]["HOME"] for c in calls if c["in_ledger"]] == [0.48]
    calls = VQ.merge_calls(files(), VQ.ledger_venue_calls(claim(), SINCE))
    assert len(calls) == 2 and not any(c["in_ledger"] for c in calls)
    assert all("attached to none" in c["ledger_ambiguous"] for c in calls)


def test_conflicting_model_exports_are_both_kept_in_the_age_report():
    """Codex on #340: same match + as_of with a different book fair is two machines' references, not a copy."""
    def doc(fair):
        return {"sport": "nfl", "desk_meta": {"as_of": _iso(KO - timedelta(hours=6)) + "Z"}, "predictions": [
            {"match_id": 1, "utc_date": _iso(KO), "home_team": "H", "away_team": "A",
             "market": {"fair_prob": fair, "fair_source": "1X2"},
             "desk": {"engine": "model_edge", "call": "PLAY", "reference": "books"}}]}
    same = VQ.model_reference_rows([("a.json", doc({"HOME": 0.6, "AWAY": 0.4})),
                                    ("host/a.json", doc({"HOME": 0.6, "AWAY": 0.4}))], SINCE)
    assert len(same) == 1 and not same[0]["conflicting_copies"]
    rows = VQ.model_reference_rows([("a.json", doc({"HOME": 0.6, "AWAY": 0.4})),
                                    ("host/a.json", doc({"HOME": 0.62, "AWAY": 0.38}))], SINCE)
    assert len(rows) == 2 and all(r["conflicting_copies"] for r in rows)
    txt = VQ.format_age_report({"by_sport": {}, "rows": rows}, SINCE, ["t"])
    assert any(x.startswith("CONFLICTING COPIES") and x.endswith(": 2") for x in txt)


def test_an_export_with_an_unparseable_as_of_is_refused(tmp_path):
    """Codex on #340: a desk file whose desk_meta.as_of cannot be parsed is refused, never skipped silently."""
    ex = tmp_path / "exports"
    ex.mkdir()
    (ex / "ok.json").write_text(json.dumps({"desk_meta": {"as_of": "2095-10-08T00:00:00Z"}, "fixtures": []}))
    (ex / "bad.json").write_text(json.dumps({"desk_meta": {"as_of": "yesterday-ish"}, "fixtures": []}))
    with pytest.raises(VQ.Refused, match=r"1 desk export\(s\) with an unparseable desk_meta.as_of"):
        VQ.iter_desk_docs(str(ex))


def test_identity_resolution_is_sport_scoped():
    """Codex on #340: Team and Match are sport-scoped; same names at the same time in another sport never resolve
    (nor make the right one ambiguous)."""
    ids = _seed()
    n = ids["n"]
    with session_scope() as s:
        c = s.query(Competition).filter_by(code="VQA").one()
        h = Team(sport=Sport.MLB, name=f"VQA{n} dead Home")
        a = Team(sport=Sport.MLB, name=f"VQA{n} dead Away")
        s.add_all([h, a])
        s.flush()
        s.add(Match(sport=Sport.MLB, competition_id=c.id, season="2095", utc_date=KO, status=MatchStatus.SCHEDULED,
                    home_team_id=h.id, away_team_id=a.id))
    call = {"home": f"VQA{n} dead Home", "away": f"VQA{n} dead Away", "kickoff": KO}
    with session_scope() as s:
        m, how = VQ.resolve_match(s, dict(call, sport="NHL"))
        assert m is not None and m.id == ids["dead"] and "sport nhl" in how
        m, how = VQ.resolve_match(s, dict(call, sport="VQA"))                 # a competition code -> its sport
        assert m is not None and m.id == ids["dead"]
        m, how = VQ.resolve_match(s, dict(call, sport="?"))                   # unknown: unfiltered, ambiguous
        assert m is None and "2 DB matches" in how and "not filtered" in how


def test_an_export_with_a_non_object_row_is_refused(tmp_path):
    """Codex on #340: a null or string entry in fixtures / predictions is refused, never skipped or a traceback."""
    for bad in (None, "x"):
        ex = tmp_path / f"ex_{bad}"
        ex.mkdir()
        (ex / "f.json").write_text(json.dumps({"desk_meta": {"as_of": "2095-10-08T00:00:00Z"},
                                               "fixtures": [{"desk": {}}, bad]}))
        with pytest.raises(VQ.Refused, match="not a list of objects"):
            VQ.iter_desk_docs(str(ex))
    for bad in (None, {}, "x"):                       # Codex on #340: a container that is not a list
        ex = tmp_path / f"cont_{type(bad).__name__}"
        ex.mkdir()
        (ex / "p.json").write_text(json.dumps({"desk_meta": {"as_of": "2095-10-08T00:00:00Z"}, "predictions": bad}))
        with pytest.raises(VQ.Refused, match="not a list of objects"):
            VQ.iter_desk_docs(str(ex))


def test_a_capture_in_the_exports_own_second_is_the_reference():
    """Codex on #340: as_of is serialized to the second, captured_at keeps microseconds; a capture at 12:00:00.8
    precedes an export stamped 12:00:00 in that second, so it is the reference (age floored at 0)."""
    t = datetime(2095, 10, 8, 12, 0, 0)
    sess = [{"source": "s", "t": t - timedelta(hours=2), "fair4": {"HOME": 0.5, "AWAY": 0.5}},
            {"source": "s", "t": t.replace(microsecond=800000), "fair4": {"HOME": 0.6, "AWAY": 0.4}}]
    row = {"as_of": t, "kickoff": KO, "file_fair": {"HOME": 0.6, "AWAY": 0.4}}
    r = VQ.age_row(row, sess)
    assert r["ref"]["t"] == t.replace(microsecond=800000) and r["capture_age_h"] == 0.0 and r["file_matches"]
    call = {"as_of": t, "kickoff": KO, "file_captured_at": None, "file_fair": None}
    a, _ = VQ.anchor_for(sess, call)
    assert a["t"] == t.replace(microsecond=800000)


def test_the_host_mirror_as_root_is_still_mirrored_and_host_only_calls_are_not_measured(tmp_path):
    """Codex on #340: --exports-dir exports/host is the mirror itself; and a call only host files hold gets no
    movement verdict from this DB's (the laptop's) captures."""
    ids = _seed()
    host = tmp_path / "exports" / "host"
    host.mkdir(parents=True)
    asof = KO - timedelta(hours=19)
    dead = {"HOME": 0.4735, "AWAY": 0.5265}
    (host / "f.json").write_text(json.dumps(_doc([_venue_row(ids["dead"], "dead", 20, dead, n=ids["n"])], asof)))
    docs, cnt = VQ.iter_desk_docs(str(host))
    assert cnt["mirrored"] == [str(host / "f.json")]
    calls = VQ.file_venue_calls(docs, SINCE, cnt["mirrored"])
    assert calls[0]["host_only"] is True
    with session_scope() as s:
        res = VQ.venue_receipt(s, calls)
    r = res["rows"][0]
    assert r["match_id"] == ids["dead"] and r["verdict"] == "HOST: NOT MEASURED" and r["later"] == []
    assert res["totals"]["tested"] == 0 and res["totals"]["HOST: NOT MEASURED"] == 1
    assert "host-only, not measured 1" in "\n".join(VQ.format_venue_receipt(res, SINCE, ["t"]))
    local = tmp_path / "exports" / "f.json"
    local.write_text((host / "f.json").read_text())
    docs, cnt = VQ.iter_desk_docs(str(tmp_path / "exports"))
    calls = VQ.file_venue_calls(docs, SINCE, cnt["mirrored"])
    assert len(calls) == 1 and calls[0]["host_only"] is False          # a local copy: measured on local captures


def test_a_local_copy_found_after_the_host_copy_makes_the_row_local():
    """Codex on #340: dedupe keeps provenance; a local copy in a folder sorting after host/ (exports/laptop/) still
    makes the row local, so it is measured, never excluded as mirrored."""
    def doc():
        return {"sport": "nfl", "desk_meta": {"as_of": _iso(KO - timedelta(hours=6)) + "Z"}, "predictions": [
            {"match_id": 7, "utc_date": _iso(KO), "home_team": "H", "away_team": "A",
             "market": {"fair_prob": {"HOME": 0.6, "AWAY": 0.4}, "fair_source": "1X2"},
             "desk": {"engine": "model_edge", "call": "PLAY", "reference": "books"}}]}
    rows = VQ.model_reference_rows([("ex/host/a.json", doc()), ("ex/laptop/a.json", doc())], SINCE,
                                   ["ex/host/a.json"])
    assert len(rows) == 1 and rows[0]["mirrored"] is False and rows[0]["match_id"] == 7
    assert rows[0]["file"] == "ex/laptop/a.json" and not rows[0]["conflicting_copies"]


def test_a_spread_derived_venue_call_is_never_given_a_1x2_movement_verdict(tmp_path):
    """Codex on #340: an NCAA VENUE call whose fair is spread_derived has no 1X2 session behind it."""
    ids = _seed()
    asof = KO - timedelta(hours=19)
    row = _venue_row(ids["dead"], "dead", 20, {"HOME": 0.4735, "AWAY": 0.5265}, n=ids["n"])
    row["market"]["fair_source"] = "spread_derived"
    calls = VQ.file_venue_calls([("f.json", _doc([row], asof))], SINCE)
    with session_scope() as s:
        res = VQ.venue_receipt(s, calls)
    r = res["rows"][0]
    assert r["verdict"] == "NOT 1X2: NOT MEASURED" and r["anchor"] is None and r["later"] == []
    assert res["totals"]["tested"] == 0 and res["totals"]["NOT 1X2: NOT MEASURED"] == 1
    assert "non-1X2 reference, not measured 1" in "\n".join(VQ.format_venue_receipt(res, SINCE, ["t"]))


def test_a_relogged_claim_uses_the_frozen_claim_prices_never_the_latest_reprice():
    """Codex on #340: upsertCalls overwrites model_p / market_p / kalshi_p / divergence_pp on every re-log; the
    claim's own prices are claim_model_p / claim_market_p, and what was not frozen is unknown, never the latest."""
    t0, t1 = KO - timedelta(hours=19), KO - timedelta(hours=9)
    base = {"engine": "venue_edge", "sport": "NHL", "home": "H", "away": "A", "kickoff": _iso(KO), "pick": "AWAY",
            "claim_at": _iso(t0) + "Z", "model_p": 0.51, "market_p": 0.47, "divergence_pp": 4.0,
            "claim_model_p": 0.5265, "claim_market_p": 0.455}
    once = VQ.ledger_venue_calls({"calls": [dict(base, reprices=[{"at": _iso(t0) + "Z"}])]}, SINCE)[0]
    assert (once["book_p"], once["kalshi_p"], once["div_pp"]) == (0.51, 0.47, 4.0)
    rel = VQ.ledger_venue_calls({"calls": [dict(base, reprices=[{"at": _iso(t0) + "Z"}, {"at": _iso(t1) + "Z"}])]},
                                SINCE)[0]
    assert (rel["book_p"], rel["kalshi_p"], rel["div_pp"]) == (0.5265, 0.455, None)
    assert "unknown at the claim: div" in rel["price_basis"]
    exe = VQ.ledger_venue_calls({"calls": [dict(base, kalshi_p=0.46, claim_exec_cost=0.47,
                                                reprices=[{"at": _iso(t0) + "Z"}, {"at": _iso(t1) + "Z"}])]},
                                SINCE)[0]
    assert exe["kalshi_p"] is None and "Kalshi p" in exe["price_basis"]


def test_an_unreadable_export_file_is_refused_other_broken_json_is_counted(tmp_path):
    """Codex on #340: a truncated fixtures_* / *predictions* / desk_parlays_* / window_* file refuses the receipt;
    an unrelated broken JSON is only counted."""
    ex = tmp_path / "exports"
    ex.mkdir()
    (ex / "broken.json").write_text("{")
    docs, cnt = VQ.iter_desk_docs(str(ex))
    assert cnt["unreadable"] == 1
    for name in ("fixtures_NHL_2095-10-08.json", "nfl_predictions_2095-10-08.json", "window_24h.json"):
        (ex / name).write_text('{"desk_meta": {"as_of": "2095-')
        with pytest.raises(VQ.Refused, match="cannot be read as JSON"):
            VQ.iter_desk_docs(str(ex))
        (ex / name).unlink()


def test_a_desk_export_with_a_missing_as_of_is_refused(tmp_path):
    """Codex on #340: desk_meta present but as_of missing / null / empty (or desk_meta not an object) is refused."""
    for i, dm in enumerate(({}, {"as_of": None}, {"as_of": ""}, "x")):
        ex = tmp_path / f"ex{i}"
        ex.mkdir()
        (ex / "fixtures_NHL_x.json").write_text(json.dumps({"desk_meta": dm, "fixtures": []}))
        with pytest.raises(VQ.Refused, match="unparseable desk_meta.as_of"):
            VQ.iter_desk_docs(str(ex))


def test_a_ledger_with_damaged_venue_reprices_is_refused():
    """Codex on #340: reprices[] decides re-logged vs not; a damaged array refuses the ledger."""
    ok = {"engine": "venue_edge", "reprices": [{"at": "2095-10-08T00:00:00Z"}]}
    assert VQ.ledger_refusal({"calls": [ok, {"engine": "model_edge", "reprices": "junk"}]}) is None
    for rp in ("junk", [None], [{"at": "soon"}], [{}]):
        assert "damaged reprices" in VQ.ledger_refusal({"calls": [dict(ok, reprices=rp)]})


def test_a_same_second_relog_is_kept_and_frozen_prices_used():
    """Codex on #340: stampTiming() records ms; a re-log in the claim's own second is a real re-log."""
    t0 = datetime(2095, 10, 8, 5, 0, 0, 100000)
    c = {"engine": "venue_edge", "sport": "NHL", "home": "H", "away": "A", "kickoff": _iso(KO), "pick": "AWAY",
         "claim_at": t0.isoformat() + "Z", "model_p": 0.51, "claim_model_p": 0.5265,
         "reprices": [{"at": t0.isoformat() + "Z"}, {"at": t0.replace(microsecond=900000).isoformat() + "Z"}]}
    r = VQ.ledger_venue_calls({"calls": [c]}, SINCE)[0]
    assert len(r["reprices"]) == 1 and r["book_p"] == 0.5265


def test_ledger_only_claims_in_spread_sports_are_never_measured_on_1x2(tmp_path):
    """Codex on #340: the ledger keeps no fair_source; an NFL / NCAA ledger-only claim's source is unknown."""
    ids = _seed()
    n = ids["n"]
    claim = {"engine": "venue_edge", "home": f"VQA{n} nfl Home", "away": f"VQA{n} nfl Away", "kickoff": _iso(KO),
             "pick": "AWAY", "claim_at": _iso(KO - timedelta(hours=10)) + "Z"}
    nfl = VQ.ledger_venue_calls({"calls": [dict(claim, sport="NFL")]}, SINCE)
    assert nfl[0]["fair_source"] == VQ.LEDGER_UNKNOWN_SOURCE
    with session_scope() as s:
        res = VQ.venue_receipt(s, VQ.merge_calls([], nfl))
    assert res["rows"][0]["verdict"] == "NOT 1X2: NOT MEASURED" and res["totals"]["tested"] == 0
    assert VQ.ledger_venue_calls({"calls": [dict(claim, sport="NHL")]}, SINCE)[0]["fair_source"] is None


def test_an_unparseable_claim_at_refuses_the_ledger():
    """Codex on #340: a present but damaged claim_at never falls back to the mutable claim_as_of."""
    ok = {"engine": "venue_edge", "claim_at": "2095-10-08T00:00:00Z"}
    assert VQ.ledger_refusal({"calls": [ok, {"engine": "venue_edge"}]}) is None          # legacy: no claim_at
    assert "unparseable claim_at" in VQ.ledger_refusal({"calls": [dict(ok, claim_at="last tuesday")]})


def test_a_mismatched_anchor_gives_no_movement_verdict():
    """Codex on #340: a file call at 0.60 whose anchor session is 0.50 (fallback or a different same-time row) is not
    measured; 'NEVER MOVED' from a substitute session would be wrong."""
    t = datetime(2095, 10, 8, 4, 0)
    sess = [{"source": "s", "t": t - timedelta(hours=1), "fair4": {"HOME": 0.5, "AWAY": 0.5}, "books": 5},
            {"source": "s", "t": t + timedelta(hours=1), "fair4": {"HOME": 0.5, "AWAY": 0.5}, "books": 5}]
    call = {"as_of": t, "kickoff": KO, "file_captured_at": t, "file_fair": {"HOME": 0.6, "AWAY": 0.4}}
    r = VQ.receipt_row(call, sess)
    assert r["file_matches_anchor"] is False and r["verdict"] == "ANCHOR MISMATCH: NOT MEASURED" and r["later"] == []


def test_an_auto_claim_never_falls_back_to_an_older_file_by_position():
    """Codex on #340: an auto-claim's clock is its file's as_of; with that file gone it stays its own row."""
    t_old, t_claim = KO - timedelta(hours=30), KO - timedelta(hours=19)
    f = {"origin": "file", "files": ["old.json"], "in_ledger": False, "as_of": t_old, "sport": "NHL", "match_id": None,
         "home": "H", "away": "A", "kickoff": KO, "side": "AWAY", "reprices": [], "claim_basis": None}
    claim = {"engine": "venue_edge", "sport": "NHL", "home": "H", "away": "A", "kickoff": _iso(KO), "pick": "AWAY",
             "claim_at": _iso(t_claim) + "Z"}
    auto = VQ.merge_calls([dict(f)], VQ.ledger_venue_calls({"calls": [dict(claim, claim_source="auto")]}, SINCE))
    assert len(auto) == 2 and not auto[0]["in_ledger"] and auto[1]["origin"] == "ledger"
    manual = VQ.merge_calls([dict(f)], VQ.ledger_venue_calls({"calls": [claim]}, SINCE))
    assert len(manual) == 1 and manual[0]["in_ledger"]


def test_a_legacy_claim_keeps_its_frozen_kalshi_price_after_an_executable_relog():
    """Codex on #340: claim_exec_cost unset at the claim means claim_market_p IS the claim's Kalshi price, even when
    a later executable re-log added a top-level kalshi_p."""
    t0, t1 = KO - timedelta(hours=19), KO - timedelta(hours=9)
    c = {"engine": "venue_edge", "sport": "NHL", "home": "H", "away": "A", "kickoff": _iso(KO), "pick": "AWAY",
         "claim_at": _iso(t0) + "Z", "claim_model_p": 0.5265, "claim_market_p": 0.455, "kalshi_p": 0.46,
         "market_p": 0.47, "reprices": [{"at": _iso(t0) + "Z"}, {"at": _iso(t1) + "Z"}]}
    r = VQ.ledger_venue_calls({"calls": [c]}, SINCE)[0]
    assert r["kalshi_p"] == 0.455 and "Kalshi p" not in r["price_basis"]


def test_a_non_object_desk_block_is_refused(tmp_path):
    """Codex on #340: a row whose desk is a list / string is refused, never skipped or a traceback."""
    for i, desk in enumerate(([], "VENUE")):
        ex = tmp_path / f"d{i}"
        ex.mkdir()
        (ex / "fixtures_NHL_x.json").write_text(json.dumps({"desk_meta": {"as_of": "2095-10-08T00:00:00Z"},
                                                            "fixtures": [{"desk": desk}]}))
        with pytest.raises(VQ.Refused, match="desk block is not an object"):
            VQ.iter_desk_docs(str(ex))


def test_every_relog_is_listed():
    """Codex on #340: the receipt lists every re-log, never the first ten."""
    t0 = KO - timedelta(hours=21)
    reps = [{"at": _iso(t0) + "Z"}] + [{"at": _iso(KO - timedelta(hours=h)) + "Z"} for h in range(20, 5, -1)]
    c = {"engine": "venue_edge", "sport": "NHL", "home": "Nobody H", "away": "Nobody A", "kickoff": _iso(KO),
         "pick": "AWAY", "claim_at": _iso(t0) + "Z", "reprices": reps}
    init_db()
    with session_scope() as s:
        res = VQ.venue_receipt(s, VQ.merge_calls([], VQ.ledger_venue_calls({"calls": [c]}, SINCE)))
    line = next(x for x in VQ.format_venue_receipt(res, SINCE, ["t"]) if "re-logged" in x)
    assert "re-logged 15 time(s)" in line and line.count("Z") == 15 and "…" not in line
