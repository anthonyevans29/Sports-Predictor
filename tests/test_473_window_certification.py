"""THE WINDOW PAGE'S LABEL (ARCHITECT 2026-11-23, addendum 473 item 3; finding #1098).

(a) the label is READ, never written by hand: window.certification is registry.certification_of(the row's family, its
    model block's model_version), the way closing.nfl_certification reads it; a read that fails is "unread", prints
    "certification not read" and never blocks the card or the page (law 4).
(b) window_24h.json: each fixture's model block gains "certification" (certified / uncertified / unread). Additive:
    appended last, no field moves, none renamed.
(c) the phone row, when the certification is not "certified": "model (uncertified) SIDE PROB (TIER)"; "unread" (or a
    card with no field) prints "model (certification not read) SIDE PROB (TIER)"; a market_only PASS reads
    "PASS market-only".
(d) an NFL row cannot render without the label while the registry reads v1 uncertified; MLB and PL rows of a
    certified family render byte for byte as before 473 (the pinned strings below are the ones the page printed at
    e4fd1e8e, the window files unchanged since e7222838, for these same cards); the file's new field; the failed read.

Every card here is built by window.build_card on an isolated per-test SQLite file (_iso_db), from export files of
the real shapes (nfl_predict's row, export.py's MLB/soccer row, the Desk block the window copies). The registry is a
tmp file: the real ledger's own soccer-elo-poisson-v22 and nfl-elo-v1 entries, copied, plus (where a test says so)
an MLB entry that the real ledger does NOT hold (the real ledger reads MLB "unread" today; test_mlb_on_the_real_ledger_reads_unread).
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy" / "hosting"))
import sp_window_page as page  # noqa: E402

from src.db.database import init_db, session_scope  # noqa: E402
from src.db.schema import Competition, Match, MatchStatus, Odds, Sport, Team  # noqa: E402
from src.walters import registry, window  # noqa: E402

KO = datetime(2081, 6, 7, 23, 5)          # a Saturday evening UTC, far from every other test's dates
NOW = KO - timedelta(hours=3)
REAL = {e["id"]: e for e in registry.load(registry.LEDGER)}
MLB_FIXTURE = {"id": "mlb-fixture-certified", "sport": "mlb", "family": "MLB", "model_version": "v2",
               "certification": "PROMOTED (test fixture only: the real ledger holds no MLB entry)"}

# the page's rows for the MLB and PL cards below at e4fd1e8e (before 473; unchanged since e7222838), byte for byte
BEFORE = {
    "mlb_play": "Sat 7:05p MLB BOS @ NYY · model NYY 56.1% (lean) · books 51.2% · +4.9pp · PLAY 0.5u",
    "mlb_nodesk": "Sat 8:05p MLB TOR @ TB · model TOR 54.0% (lean) · books 50.0% · +4.0pp",
    "pl_play": "Sat 7:05p PL CHE @ ARS · model ARS 54.0% (lean) · books 48.0% · +6.0pp · PLAY 1u",
    "pl_floor": "Sat 8:05p PL TOT @ LIV · model LIV 47.0% (toss-up) · books 45.8% · +1.2pp · PASS floor",
}


def _ledger(tmp_path, monkeypatch, *, mlb=False, ids=("soccer-elo-poisson-v22", "nfl-elo-v1")):
    entries = [dict(REAL[i]) for i in ids] + ([dict(MLB_FIXTURE)] if mlb else [])
    p = tmp_path / "experiments.json"
    p.write_text(json.dumps(entries))
    monkeypatch.setattr(registry, "LEDGER", str(p))     # certification_of reads LEDGER at call time
    return p


_SEEDED: dict = {}


@pytest.fixture(autouse=True)
def _iso_db(tmp_path, monkeypatch):
    """Each test seeds its own isolated SQLite file (as tests/test_book_source_times_615.py's `iso` does): the PL, MLB
    and NFL competitions seeded here never reach the session's shared throwaway DB, where later modules create those
    codes themselves (tests/test_cup_coeff.py, tests/test_cup_exam.py)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from src.db import database
    eng = create_engine(f"sqlite:///{tmp_path / 'iso473.db'}", future=True)
    monkeypatch.setattr(database, "_engine", eng)
    monkeypatch.setattr(database, "SessionLocal",
                        sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True, expire_on_commit=False))
    _SEEDED.clear()
    yield
    _SEEDED.clear()
    eng.dispose()


def _seed():
    """One NFL, two MLB and two PL games (kickoff KO and KO+1h), seeded once per test into its isolated DB."""
    if _SEEDED:
        return _SEEDED
    init_db()
    with session_scope() as s:
        def comp(sport, code):
            c = s.query(Competition).filter_by(sport=sport, code=code).one_or_none()
            if c is None:
                c = Competition(sport=sport, code=code, name=code, area="X", type="LEAGUE")
                s.add(c)
                s.flush()
            return c

        def team(sport, name, tla):
            t = Team(sport=sport, name=name, tla=tla, external_ids={"w473": name})
            s.add(t)
            s.flush()
            return t

        def game(key, sport, code, home, away, ko, season):
            m = Match(sport=sport, competition_id=comp(sport, code).id, season=season, utc_date=ko,
                      status=MatchStatus.SCHEDULED, home_team_id=home.id, away_team_id=away.id,
                      external_ids={"w473": key})
            s.add(m)
            s.flush()
            _SEEDED[key] = m.id
            return m

        game("nfl", Sport.NFL, "NFL", team(Sport.NFL, "W473 Kansas City", "KC"),
             team(Sport.NFL, "W473 Buffalo", "BUF"), KO, "2081")
        game("mlb_play", Sport.MLB, "MLB", team(Sport.MLB, "W473 Yankees", "NYY"),
             team(Sport.MLB, "W473 Red Sox", "BOS"), KO, "2081")
        nodesk = game("mlb_nodesk", Sport.MLB, "MLB", team(Sport.MLB, "W473 Rays", "TB"),
                      team(Sport.MLB, "W473 Blue Jays", "TOR"), KO + timedelta(hours=1), "2081")
        game("pl_play", Sport.SOCCER, "PL", team(Sport.SOCCER, "W473 Arsenal", "ARS"),
             team(Sport.SOCCER, "W473 Chelsea", "CHE"), KO, "2081/82")
        game("pl_floor", Sport.SOCCER, "PL", team(Sport.SOCCER, "W473 Liverpool", "LIV"),
             team(Sport.SOCCER, "W473 Tottenham", "TOT"), KO + timedelta(hours=1), "2081/82")
        for bk in ("b1", "b2", "b3", "b4"):                # the no-desk MLB row's edge is against the card's books
            for sel, price in (("HOME", 2.0), ("AWAY", 2.0)):
                s.add(Odds(match_id=nodesk.id, bookmaker=bk, market="1X2", selection=sel, price_decimal=price,
                           captured_at=NOW - timedelta(hours=1)))
    return _SEEDED


def _desk(call, units, pass_kind, ref, edge, tags=()):
    """The export row's Desk block (desk_policy.annotate's keys the window copies, plus engine/tags/shadow_units)."""
    return {"engine": "model_edge", "call": call, "units": units, "pass_kind": pass_kind, "reference": "books",
            "market_ref": ref, "edge_pp": edge, "tags": list(tags), "shadow_units": 0}


def _soccer_pred(mv, h, d, a, tier):
    p = {"home_win": h, "draw": d, "away_win": a}
    top = max((k for k in p if p[k] is not None), key=p.get)     # export.py: the top of the non-null probabilities
    return {"model_version": mv, "computed_at": "2081-06-07T12:00:00", "probabilities": p, "top_pick": top,
            "top_pick_prob": p[top], "tier": tier}


def _exports(d: Path, *, nfl_mv="nfl_elo_v1", mlb_mv="v2", pl_mv="v22"):
    ids = _seed()
    d.mkdir(exist_ok=True)
    stamp = "2081-06-07T12:00:00Z"
    # nfl_predict.export_predictions' row (prediction.home_win_prob; the Desk's market-only PASS, addendum 214)
    (d / "nfl_predictions_2081-06-07.json").write_text(json.dumps({
        "exported_at": stamp, "sport": "nfl", "model_version": nfl_mv, "certification": "typed by hand, never read",
        "predictions": [{"match_id": ids["nfl"], "prediction": {
            "model_version": nfl_mv, "home_win_prob": 0.587, "away_win_prob": 0.413, "top_pick": "home_win",
            "tier": "lean"}, "quarantine": False, "market_divergence_pp": 4.1,
            "desk": _desk("PASS", 0, "market_only", 0.546, 4.1, ("market-only: nfl_elo_v1 uncertified "
                                                                 "(addendum 214)"))}]}))
    # export.py's MLB row (prediction.probabilities, draw None)
    (d / "mlb_MLB_2081-06-07.json").write_text(json.dumps({
        "exported_at": stamp, "sport": "mlb", "predictions": [
            {"match_id": ids["mlb_play"], "prediction": _soccer_pred(mlb_mv, 0.561, None, 0.439, "lean"),
             "quarantine": False, "market_divergence_pp": 4.9, "desk": _desk("PLAY", 0.5, None, 0.512, 4.9)},
            {"match_id": ids["mlb_nodesk"], "prediction": _soccer_pred(mlb_mv, 0.46, None, 0.54, "lean"),
             "quarantine": False, "market_divergence_pp": -4.0}]}))
    # export.py's soccer row (three-way probabilities, input_quality.rating_source)
    (d / "soccer_PL_2081-06-07_to_2081-06-14.json").write_text(json.dumps({
        "exported_at": stamp, "sport": "soccer", "predictions": [
            {"match_id": ids["pl_play"], "prediction": _soccer_pred(pl_mv, 0.54, 0.25, 0.21, "lean"),
             "quarantine": False, "market_divergence_pp": 6.0,
             "input_quality": {"rating_source": {"home": "model", "away": "model"}},
             "desk": _desk("PLAY", 1, None, 0.48, 6.0)},
            {"match_id": ids["pl_floor"], "prediction": _soccer_pred(pl_mv, 0.47, 0.27, 0.26, "toss-up"),
             "quarantine": False, "market_divergence_pp": 1.2,
             "input_quality": {"rating_source": {"home": "model", "away": "model"}},
             "desk": _desk("PASS", 0, "floor", 0.458, 1.2)}]}))
    return ids


def _card(tmp_path, **kw):
    ids = _exports(tmp_path / "exports", **kw)
    card = window.build_card(now=NOW, hours=24, export_dir=str(tmp_path / "exports"))
    rows = {k: next(r for r in card["fixtures"] if r["match_id"] == mid) for k, mid in ids.items()}
    snap = page.snapshot({"fixtures": list(rows.values())})
    texts = {k: page.row_text(snap[str(r["match_id"])]) for k, r in rows.items()}
    return card, rows, snap, texts


# ---------------------------------------------------------------- (d) the NFL row cannot render without the label

def test_the_ledger_copies_are_the_real_entries():
    """The tmp ledgers copy the real ledger's own entries: v1 reads uncertified and v22 certified there today."""
    assert registry.certification_of("NFL", "nfl_elo_v1") == ("uncertified", "nfl-elo-v1")
    assert registry.certification_of("SOCCER", "v22") == ("certified", "soccer-elo-poisson-v22")


def test_an_nfl_row_carries_the_label_while_the_registry_reads_v1_uncertified(tmp_path, monkeypatch):
    _ledger(tmp_path, monkeypatch)
    card, rows, snap, texts = _card(tmp_path)
    assert rows["nfl"]["model"]["certification"] == "uncertified"
    assert texts["nfl"] == ("Sat 7:05p NFL BUF @ KC · model (uncertified) KC 58.7% (lean) · books 54.6% · +4.1pp · "
                            "PASS market-only")
    g = snap[str(rows["nfl"]["match_id"])]
    # every place the page prints the row: the digest, a delta line, a QB-news game line
    assert "model (uncertified) KC 58.7% (lean)" in page.digest(snap)
    for cls in ("new_priced", "tier", "model", "call"):
        first = page.line({"cls": cls, "id": "x", "g": g, "was": {"pick": "HOME", "prob": 0.5, "call": "PASS",
                                                                  "units": 0, "pass_kind": "noref"}})
        assert first.split("\n")[0] == texts["nfl"], cls
    qb = page.line({"cls": "qb_news", "id": "k", "g": g, "player": "P", "team": "KC", "by_name": False, "n": 1,
                    "was": None, "now": "Out", "games": [g]})
    assert qb.split("\n")[1] == f"  ↳ {texts['nfl']}"


@pytest.mark.parametrize("cert", ["uncertified", "unread", None, "", "CERTIFIED", "certified (stale)", 1])
def test_only_the_word_certified_drops_the_label(cert):
    """Law 4 on the page: anything but the exact word the card writes for a certified read prints a label."""
    g = {"utc_date": "2081-06-07T23:05:00", "competition": "NFL", "home": "KC", "away": "BUF",
         "engine": "model_edge", "pick": "HOME", "prob": 0.587, "tier": "lean", "certification": cert,
         "ref_p": 0.546, "desk_edge": 4.1, "call": "PASS", "units": 0, "pass_kind": "market_only"}
    word = "uncertified" if cert == "uncertified" else "certification not read"
    assert page.row_text(g) == (f"Sat 7:05p NFL BUF @ KC · model ({word}) KC 58.7% (lean) · books 54.6% · +4.1pp · "
                                "PASS market-only")
    g.pop("certification")                              # a card written before 473 carries no field at all
    assert "model (certification not read) KC 58.7% (lean)" in page.row_text(g)
    assert page.row_text(dict(g, certification="certified")).startswith("Sat 7:05p NFL BUF @ KC · model KC 58.7%")


def test_a_market_only_pass_reads_pass_market_only_and_the_other_kinds_are_as_before():
    assert page._call_text({"call": "PASS", "pass_kind": "market_only"}) == "PASS market-only"
    assert page._call_text({"call": "PASS", "pass_kind": "noref"}) == "PASS no-ref"
    assert page._call_text({"call": "PASS", "pass_kind": "floor"}) == "PASS floor"
    assert page._call_text({"call": "PASS", "pass_kind": "host_fence"}) == "PASS"
    assert page._call_text({"call": "PASS", "pass_kind": None}) == "PASS"
    g = {"utc_date": "2081-06-07T23:05:00", "competition": "NFL", "home": "KC", "away": "BUF", "engine": "model_edge",
         "pick": "HOME", "prob": 0.587, "tier": "lean", "certification": "uncertified", "ref_p": 0.546,
         "desk_edge": 4.1, "call": "PASS", "units": 0, "pass_kind": "market_only"}
    d = page.line({"cls": "call", "id": "x", "g": g, "was": {"call": "PASS", "units": 0, "pass_kind": "noref"}})
    assert d.split("\n")[1] == "  ↳ call changed: PASS no-ref -> PASS market-only"


# ------------------------------------------------------- (d) a certified family's row renders byte for byte as before

def test_certified_family_rows_render_byte_for_byte_as_before(tmp_path, monkeypatch):
    """MLB and the PL, read certified (the real v22 entry; an MLB fixture entry, since the real ledger has none): the
    rows, the digest's rows and the delta lines are the strings the page printed at e4fd1e8e for these cards."""
    _ledger(tmp_path, monkeypatch, mlb=True)
    card, rows, snap, texts = _card(tmp_path)
    for k, want in BEFORE.items():
        assert texts[k] == want, k
        assert rows[k]["model"]["certification"] == "certified", k
    digest = page.digest(snap).split("\n")
    for k, want in BEFORE.items():
        assert want in digest, k
    g = snap[str(rows["pl_play"]["match_id"])]
    assert page.line({"cls": "tier", "id": "x", "g": g, "was": "toss-up"}) == (
        BEFORE["pl_play"] + "\n  ↳ tier toss-up -> lean")


# ----------------------------------------------------------------------------------------- (b) the file's new field

def test_the_file_model_block_gains_certification_last_and_nothing_moves(tmp_path, monkeypatch):
    _ledger(tmp_path, monkeypatch)                     # no MLB entry: the real ledger's state for MLB
    shared: dict = {}                                  # the very dicts build_card copies, held to see if it writes them
    real_models = window.canonical_models

    def spy(d):
        out = real_models(d)
        shared.update(out)
        return out
    monkeypatch.setattr(window, "canonical_models", spy)
    card, rows, snap, texts = _card(tmp_path)
    assert shared                                      # build_card read through the spy
    before = list(shared[rows["pl_play"]["match_id"]])
    for k, r in rows.items():
        keys = list(r["model"])
        assert keys[:-1] == before and keys[-1] == "certification", k     # appended; every prior key in its place
    assert {k: r["model"]["certification"] for k, r in rows.items()} == {
        "nfl": "uncertified", "mlb_play": "unread", "mlb_nodesk": "unread", "pl_play": "certified",
        "pl_floor": "certified"}
    # the canonical rows the card copied (the same objects build_card held) are never mutated
    assert all("certification" not in r for r in shared.values())
    # written and read back as the file the reader takes
    path = window.write_card(card, export_dir=str(tmp_path / "out"))
    back = {r["match_id"]: r for r in json.loads(Path(path).read_text())["fixtures"]}
    assert back[rows["nfl"]["match_id"]]["model"]["certification"] == "uncertified"
    # a market-only row (no model) gains nothing: its model stays null
    assert all(r["model"] is None for r in card["fixtures"] if r["engine"] == "market_only")


def test_mlb_with_no_registry_entry_reads_unread_and_prints_not_read(tmp_path, monkeypatch):
    """The real ledger holds no MLB entry (law 4: "a missing entry is not a certification"): an MLB row reads unread,
    and the page prints the label "certification not read" where "uncertified" would go."""
    _ledger(tmp_path, monkeypatch)
    _, rows, _, texts = _card(tmp_path)
    assert texts["mlb_play"] == ("Sat 7:05p MLB BOS @ NYY · model (certification not read) NYY 56.1% (lean) · "
                                 "books 51.2% · +4.9pp · PLAY 0.5u")


def test_mlb_on_the_real_ledger_reads_unread():
    """The live fact the PR body states: the committed ledger has no entry of family MLB."""
    state, why = registry.certification_of("MLB", "v2")
    assert state == "unread" and why == "no registry entry for MLB v2"
    assert window.certification("MLB", "v2") == "unread"


def test_family_and_version_both_key_the_read(tmp_path, monkeypatch):
    """Addendum 299 item 3(a): never the version alone. v22 under MLB, nfl_elo_v1 under NCAAF, no family, no version:
    each reads unread."""
    _ledger(tmp_path, monkeypatch)
    assert window.certification("SOCCER", "v22") == "certified"
    assert window.certification("NFL", "nfl_elo_v1") == "uncertified"
    assert window.certification("MLB", "v22") == "unread"
    assert window.certification("NCAAF", "nfl_elo_v1") == "unread"
    assert window.certification(None, "v22") == "unread"
    assert window.certification("SOCCER", None) == "unread"


def _seed_more():
    """A third PL game and a college game (Sport.NFL under competition NCAA: family NCAAF), at KO+2h."""
    ids = _seed()
    with session_scope() as s:
        def team(sport, name, tla):
            t = Team(sport=sport, name=name, tla=tla, external_ids={"w473": name})
            s.add(t)
            s.flush()
            return t

        def comp(sport, code):
            c = s.query(Competition).filter_by(sport=sport, code=code).one_or_none()
            if c is None:
                c = Competition(sport=sport, code=code, name=code, area="X", type="LEAGUE")
                s.add(c)
                s.flush()
            return c

        for key, sport, code, h, a, season in (
                ("pl_other", Sport.SOCCER, "PL", ("W473 Everton", "EVE"), ("W473 Fulham", "FUL"), "2081/82"),
                ("ncaa", Sport.NFL, "NCAA", ("W473 Alabama", "BAMA"), ("W473 Georgia", "UGA"), "2081")):
            m = Match(sport=sport, competition_id=comp(sport, code).id, season=season,
                      utc_date=KO + timedelta(hours=2), status=MatchStatus.SCHEDULED,
                      home_team_id=team(sport, *h).id, away_team_id=team(sport, *a).id, external_ids={"w473": key})
            s.add(m)
            s.flush()
            ids[key] = m.id
    return ids


def test_build_card_keys_each_row_by_its_own_family_and_version(tmp_path, monkeypatch):
    """Through build_card, not the bare function: two PL versions on one card (v22 certified, an unregistered one
    unread, so the read is the row's own version and the cache keys on family AND version), and a college row carrying
    nfl_elo_v1 (family NCAAF from the row, not the stored sport "nfl": unread, never NFL's "uncertified")."""
    _ledger(tmp_path, monkeypatch)
    _exports(tmp_path / "exports")
    ids = _seed_more()
    stamp = "2081-06-07T12:00:00Z"
    (tmp_path / "exports" / "soccer_PL_2081-06-08_to_2081-06-15.json").write_text(json.dumps({
        "exported_at": stamp, "sport": "soccer", "predictions": [
            {"match_id": ids["pl_other"], "prediction": _soccer_pred("v21-unregistered", 0.5, 0.26, 0.24, "lean"),
             "quarantine": False, "market_divergence_pp": 2.0}]}))
    (tmp_path / "exports" / "nfl_predictions_2081-06-08.json").write_text(json.dumps({
        "exported_at": stamp, "sport": "nfl", "predictions": [{"match_id": ids["ncaa"], "prediction": {
            "model_version": "nfl_elo_v1", "home_win_prob": 0.6, "away_win_prob": 0.4, "top_pick": "home_win",
            "tier": "lean"}, "quarantine": False}]}))
    card = window.build_card(now=NOW, hours=24, export_dir=str(tmp_path / "exports"))
    got = {r["match_id"]: r for r in card["fixtures"]}
    assert got[ids["ncaa"]]["family"] == "NCAAF" and got[ids["ncaa"]]["sport"] == "nfl"
    assert {k: got[ids[k]]["model"]["certification"] for k in ("pl_play", "pl_floor", "pl_other", "nfl", "ncaa")} == {
        "pl_play": "certified", "pl_floor": "certified", "pl_other": "unread", "nfl": "uncertified", "ncaa": "unread"}


def test_an_unhashable_version_reads_unread_and_never_blocks_the_card(tmp_path, monkeypatch):
    """A malformed export (prediction.model_version a list): canonical_models copies it unchecked; the card's
    (family, version) cache cannot hash it, and the row reads "unread" while the card builds (473 item 3(a))."""
    _ledger(tmp_path, monkeypatch)
    _exports(tmp_path / "exports", nfl_mv=["nfl_elo_v1"])
    card = window.build_card(now=NOW, hours=24, export_dir=str(tmp_path / "exports"))
    got = {r["match_id"]: r for r in card["fixtures"]}
    assert got[_SEEDED["nfl"]]["model"]["certification"] == "unread"
    assert got[_SEEDED["pl_play"]]["model"]["certification"] == "certified"


# ------------------------------------------------------------------------------------------------- the failed read

def _boom(*a, **k):
    raise RuntimeError("registry down")


@pytest.mark.parametrize("how", ["raises", "missing_file", "bad_json", "no_module"])
def test_a_failed_read_is_unread_prints_not_read_and_never_blocks(tmp_path, monkeypatch, how):
    p = _ledger(tmp_path, monkeypatch)
    if how == "raises":
        monkeypatch.setattr(registry, "certification_of", _boom)
    elif how == "missing_file":
        monkeypatch.setattr(registry, "LEDGER", str(tmp_path / "nowhere.json"))
    elif how == "bad_json":
        p.write_text("{not json")
    else:
        import src.walters as walters                  # the import itself fails: no attribute, no module
        monkeypatch.delattr(walters, "registry")
        monkeypatch.setitem(sys.modules, "src.walters.registry", None)
    card, rows, snap, texts = _card(tmp_path)
    assert card["count"] >= 5 and all(r["model"]["certification"] == "unread" for r in rows.values())
    assert texts["nfl"] == ("Sat 7:05p NFL BUF @ KC · model (certification not read) KC 58.7% (lean) · books 54.6% · "
                            "+4.1pp · PASS market-only")
    assert texts["pl_play"].startswith("Sat 7:05p PL CHE @ ARS · model (certification not read) ARS 54.0% (lean)")
    assert page.digest(snap)                            # the page still renders
