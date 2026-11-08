"""THE BULLETIN RENDERER (ARCHITECT 2026-11-04 11:20 ET, addendum 250 items 1-4 and 6(a)-(c); addendum 289 item 4;
lane #826, step 1b): deploy/hosting/bulletin.py and `cli.py bulletin`.

Pinned here: the clean pair at the ruled path (exports/bulletins/<FAMILY>/<ET date>/<match>_<away>_at_<home>_<stage>
.md + .png); the card 1080 px wide, portrait; the call-line parity of 6(a) (closing.call_text and closing
.would_be_text, verbatim); THE WRITER-SIDE GUARD of item 2, one test per forbidden field or pattern (desk.order text,
desk.exec.contracts, fee_order_contracts, a contract count, a dollar figure, desk_meta.unit.fraction, half_fraction,
the pool, the account id, the #817 row and header, the API key through sp_common.redact): a refused run writes
nothing and its receipt names the pattern and the intended path, never the line; the positive control of 6(b); the
"not stored" rule of 6(c); no JSON ever written under bulletins; the mirror URL printed with the owner/repo parsed and
the remote's value never printed.

Synthetic only (item 6: "The fixtures carry invented teams and invented tickers; no real closing row goes into
tests/fixtures/"): every row is built here, annotated by the Desk itself (desk_policy.annotate) and wrapped by
closing.closing_doc, in a throwaway repo under tmp_path. No DB but a scratch copy, no network, no mirror push."""
import json
import sqlite3
import struct
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HOSTING = ROOT / "deploy" / "hosting"
sys.path.insert(0, str(HOSTING))

import bulletin as b  # noqa: E402
import closing as cl  # noqa: E402
import sp_common as c  # noqa: E402

from src import privacy_patterns as pv  # noqa: E402
from src.walters import desk_policy as dp  # noqa: E402

NOW = datetime(2026, 11, 8, 16, 0, tzinfo=timezone.utc)            # Sunday 11:00 ET
RUN_ID = "20261108T160000Z-closing-test"
REMOTE = "git@github.com:owner-x/repo-y.git"                       # invented: parsed, never printed whole
_Z = "-".join("0" * n for n in (8, 4, 4, 4, 12))                     # an all-zero UUID, built at run time


def row(mid, home, away, p_home, *, fair_h, bid, ask, comp, series, draw=None, fair_d=None, minutes=35):
    """An invented export row in the exports' own shape (src/walters/export.py, nfl_predict.py field names)."""
    sels = ("HOME", "DRAW", "AWAY") if draw is not None else ("HOME", "AWAY")
    fair = ({"HOME": fair_h, "AWAY": round(1 - fair_h, 4)} if draw is None else
            {"HOME": fair_h, "DRAW": fair_d, "AWAY": round(1 - fair_h - fair_d, 4)})
    probs = {"home_win": p_home, "draw": draw, "away_win": round(1 - p_home - (draw or 0), 4)}
    tick = home[:3].upper()
    legs = {"HOME": {"ticker": f"{series}-26NOV08{tick}-H", "bid": bid, "ask": ask},
            "AWAY": {"ticker": f"{series}-26NOV08{tick}-A", "bid": round(1 - ask, 2), "ask": round(1 - bid, 2)}}
    if draw is not None:
        legs["DRAW"] = {"ticker": f"{series}-26NOV08{tick}-TIE", "bid": 0.26, "ask": 0.27}
    r = {"match_id": mid, "home_team": home, "away_team": away, "competition": comp,
         "utc_date": (NOW + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S"), "stage": "regular",
         "prediction": {"model_version": "test-model-v0", "computed_at": "2026-11-08T09:00:00",
                        "probabilities": probs, "tier": "lean", "top_pick": "home_win", "top_pick_prob": p_home,
                        "expected_home": 1.6, "expected_away": 1.1,
                        "factor_breakdown": {"home_elo": 1612.0, "away_elo": 1544.5, "home_attack": 1.12,
                                             "home_defense": 0.91, "away_attack": 0.98, "away_defense": 1.04,
                                             "most_likely_score": [1, 1],
                                             "factor_notes": ["home missing 2 (-6% xG)"]}},
         "market": {"selections": {s: {"best_price": 2.1, "best_bookmaker": "bookA", "fair_prob": fair[s],
                                       "model_prob": None, "edge_pp": 1.0} for s in sels},
                    "fair_prob": fair, "bookmaker_count": 9, "bookmaker_count_quoted": 9, "overround_pct": 4.1,
                    "kalshi": {"raw_yes_prob": {s: fair[s] for s in sels}, "raw_sum": 1.0,
                               "prob": {s: fair[s] for s in sels}, "normalized": True,
                               "captured_at": (NOW - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S"),
                               "vs_book_pp": {s: 0.0 for s in sels}}},
         "kalshi_bid": bid, "kalshi_ask": ask, "kalshi_legs": legs,
         "fee_series": series, "fee_m_taker": 1.0, "fee_order_contracts": 10,
         "line_move": None,
         "home_form": {"last_5": "WWDLW", "wins": 3, "draws": 1, "losses": 1, "goals_scored": 8, "goals_conceded": 5},
         "away_form": {"last_5": "LDWLL", "wins": 1, "draws": 1, "losses": 3, "goals_scored": 4, "goals_conceded": 9},
         "injuries": {"home_count": 2, "away_count": 1, "home_names": ["A. Keeper", "B. Back"],
                      "away_names": ["C. Wing"]},
         "input_quality": {"rating_source": {"home": "model", "away": "model"},
                           "strengths_source": {"home": "matches", "away": "matches"},
                           "strengths_backfilled": False, "current_season_matches": 10,
                           "injuries_synced_at": "2026-11-08T08:00:00",
                           "injuries": {"home": {"count": 2, "synced_at": "2026-11-08T08:00:00"},
                                        "away": {"count": 1, "synced_at": "2026-11-08T08:00:00"}}}}
    if comp == "NFL":
        r["week"] = 10
        r["market_divergence_pp"] = round((p_home - fair_h) * 100, 1)
        r["quarantine"] = abs(r["market_divergence_pp"]) >= 15
        r["prediction"] = {"model_version": "nfl_elo_v1", "home_win_prob": p_home,
                           "away_win_prob": round(1 - p_home, 4), "top_pick": "home_win", "tier": "lean"}
        r["market"] = {"bookmaker_count": 9, "fair_prob": fair, "fair_source": "1X2"}
        r["input_quality"] = {"book_odds": 9, "injuries": {
            s: {"count": 1, "qb_listed": [], "positions_unresolved": [], "synced_at": "2026-11-08T08:00:00"}
            for s in ("home", "away")}}
        r["elo_home"], r["elo_away"], r["elo_gap"], r["home_adv_applied"] = 1580.0, 1500.0, 80.0, 48
        r["kalshi_prob"], r["kalshi_captured_at"] = fair_h, "2026-11-08T15:55:00"
        r["venue_gap_pp"], r["venue_flag"] = 0.0, None
        r.pop("injuries")
    return r


def soccer_doc():
    k = {"comp": "PL", "series": "KXTESTGAME"}
    rows = [row(9401, "Alpha Owls", "Beta Hawks", 0.55, fair_h=0.45, fair_d=0.27, draw=0.25, bid=0.44, ask=0.45, **k),
            row(9402, "Gamma FC", "Delta United", 0.40, fair_h=0.39, fair_d=0.30, draw=0.30, bid=0.38, ask=0.39, **k)]
    return dp.annotate({"sport": "soccer", "exported_at": "2026-11-08T15:25:00Z", "predictions": rows}, now=NOW)


def nfl_doc():
    k = {"comp": "NFL", "series": "KXTESTNFL"}
    rows = [row(9301, "Epsilon Bears", "Zeta Rams", 0.62, fair_h=0.55, bid=0.54, ask=0.55, **k),
            row(9302, "Eta Jets", "Theta Colts", 0.75, fair_h=0.55, bid=0.54, ask=0.55, minutes=38, **k)]
    return dp.annotate({"sport": "nfl", "exported_at": "2026-11-08T15:25:00Z", "predictions": rows}, now=NOW)


def mlb_doc():
    k = {"comp": "MLB", "series": "KXTESTMLB"}
    r = row(9101, "Iota Sox", "Kappa Cubs", 0.60, fair_h=0.53, bid=0.51, ask=0.52, **k)
    r["pitchers"] = {"home": {"name": "H. Arm", "kind": "confirmed", "era": 3.1},
                     "away": {"name": "A. Arm", "kind": "probable", "era": 4.2}}
    r["market"]["bookmaker_count"] = 0
    return dp.annotate({"sport": "mlb", "exported_at": "2026-11-08T15:25:00Z", "predictions": [r]}, now=NOW)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    rp = tmp_path / "repo"
    (rp / "exports").mkdir(parents=True)
    monkeypatch.setattr(c, "REPO", rp)
    monkeypatch.setattr(c, "HOST_ENV", tmp_path / "no-host.env")
    monkeypatch.setattr(c, "_DOTENV_CACHE", {})
    monkeypatch.setenv("SP_RECEIPTS", str(tmp_path / "logs" / "receipts.jsonl"))
    monkeypatch.setenv("SP_EXPORTS_MIRROR_REMOTE", REMOTE)
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "host")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'no-such.db'}")    # never created: read mode=ro
    return rp


def closing_file(repo: Path, doc: dict, fam: str, ids=None, books_why=None) -> Path:
    ids = ids or [r["match_id"] for r in doc["predictions"]]
    out = cl.closing_doc(doc, fam, NOW + timedelta(minutes=35), RUN_ID, ids, [], books_why)
    p = repo / "exports" / cl.closing_name(fam, NOW + timedelta(minutes=35))
    p.write_text(json.dumps(out, indent=2))
    return p


def receipts():
    p = c.receipts_path()
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def files_under(p: Path) -> list[Path]:
    return sorted(x for x in p.rglob("*") if x.is_file()) if p.exists() else []


def png_size(p: Path) -> tuple[int, int]:
    data = p.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR"
    return struct.unpack(">II", data[16:24])


def md_of(repo, fam, mid, stage="closing") -> str:
    hits = [p for p in files_under(repo / "exports" / "bulletins") if p.name.startswith(f"{mid}_")
            and p.name.endswith(f"_{stage}.md") and f"/{fam}/" in p.as_posix()]
    assert len(hits) == 1, hits
    return hits[0].read_text()


# ------------------------------------------------------------------------------------------- the clean pair --

def test_a_clean_closing_file_writes_md_and_png_at_the_ruled_paths(repo, capsys):
    src = closing_file(repo, soccer_doc(), "SOCCER")
    assert b.run(closing_file=str(src)) == 0
    got = [p.relative_to(repo).as_posix() for p in files_under(repo / "exports" / "bulletins")]
    assert got == ["exports/bulletins/SOCCER/2026-11-08/9401_beta-hawks_at_alpha-owls_closing.md",
                   "exports/bulletins/SOCCER/2026-11-08/9401_beta-hawks_at_alpha-owls_closing.png",
                   "exports/bulletins/SOCCER/2026-11-08/9402_delta-united_at_gamma-fc_closing.md",
                   "exports/bulletins/SOCCER/2026-11-08/9402_delta-united_at_gamma-fc_closing.png"]
    rec = receipts()[-1]
    assert rec["kind"] == "bulletin" and rec["exit"] == 0 and rec["stage"] == "closing" and rec["family"] == "SOCCER"
    assert rec["written"] == got and "bulletin_refused" not in rec
    md = md_of(repo, "SOCCER", 9401)
    heads = [ln for ln in md.splitlines() if ln.startswith("## ")]
    assert heads == ["## THE CALL", "## THE PREDICTION", "## THE TEAMS", "## THE MARKET", "## THE MATHS",
                     "## WHAT CHANGED SINCE THE SLATE"]                       # item 1's order, every one present
    assert md.rstrip().endswith(b.FOOTER) and md.count(b.FOOTER) == 1
    assert f"- run id: {RUN_ID}" in md and "- stage: closing page, T-35" in md
    assert "- kickoff: 2026-11-08 11:35 ET (2026-11-08T16:35:00Z)" in md


def test_the_card_is_1080_px_wide_portrait_and_a_png(repo):
    src = closing_file(repo, soccer_doc(), "SOCCER")
    assert b.run(closing_file=str(src)) == 0
    pngs = [p for p in files_under(repo / "exports" / "bulletins") if p.suffix == ".png"]
    assert len(pngs) == 2
    for p in pngs:
        w, h = png_size(p)
        assert w == b.CARD_WIDTH_PX == 1080 and h >= b.CARD_MIN_HEIGHT_PX and h > w


def test_the_card_draws_with_matplotlibs_bundled_dejavu_sans_by_file():
    import matplotlib
    font = b._fonts()
    fp = font(12)
    assert Path(fp.get_file()).name == "DejaVuSans.ttf"
    assert Path(fp.get_file()).resolve().is_relative_to(Path(matplotlib.get_data_path()).resolve())


def test_slugs_are_lower_cased_ascii_folded_hyphenated():
    assert b.slug("Atlético Ñandú & Co.") == "atletico-nandu-co"
    assert b.slug("Brighton & Hove Albion") == "brighton-hove-albion"
    assert b.slug("") == "team"


# --------------------------------------------------------------------------------- 6(a): the call-line parity --

def _call_line(md: str) -> str:
    lines = md.splitlines()
    i = lines.index("## THE CALL")
    assert lines[i + 2].startswith("# ")
    return lines[i + 2][2:]


@pytest.mark.parametrize("fam,doc_fn,mid", [("SOCCER", soccer_doc, 9401), ("SOCCER", soccer_doc, 9402),
                                            ("NFL", nfl_doc, 9301), ("MLB", mlb_doc, 9101)])
def test_the_call_line_is_closing_call_text_verbatim(repo, fam, doc_fn, mid):
    doc = doc_fn()
    src = closing_file(repo, doc, fam, books_why={mid: "provider listed the game, no odds"} if fam == "MLB" else None)
    assert b.run(closing_file=str(src)) == 0
    r = next(x for x in doc["predictions"] if x["match_id"] == mid)
    md = md_of(repo, fam, mid)
    assert _call_line(md) == cl.call_text(r, r["desk"])
    if r["desk"]["call"] == "PASS":
        assert f"**WHY THERE IS NO BET:** {r['desk']['reason']}" in md
        assert md.index("WHY THERE IS NO BET") < md.index("## THE PREDICTION")


def test_a_soccer_play_and_a_soccer_pass_with_the_floor_reason(repo):
    doc = soccer_doc()
    play, pas = doc["predictions"]
    assert play["desk"]["call"] == "PLAY" and pas["desk"]["call"] == "PASS" and pas["desk"]["pass_kind"] == "floor"
    assert b.run(closing_file=str(closing_file(repo, doc, "SOCCER"))) == 0
    md = md_of(repo, "SOCCER", 9401)
    assert "- order: YES on Kalshi, limit 45c" in md                          # side, venue, limit in cents
    assert "WHY THERE IS NO BET" not in md


def test_an_nfl_pass_carries_the_would_be_line_verbatim_labelled_record_only(repo):
    doc = nfl_doc()
    assert b.run(closing_file=str(closing_file(repo, doc, "NFL"))) == 0
    r = doc["predictions"][0]
    x = cl.desk_rows({"predictions": [r]}, {r["match_id"]}, b.EPOCH, fam="NFL")[0]
    assert x.get("would_be"), "the fixture's NFL row must carry a would-be PLAY (addendum 217 item 4)"
    line = " · ".join(cl.would_be_text(x["would_be"]))
    md = md_of(repo, "NFL", 9301)
    assert f"- {line}" in md and line.endswith(b.RECORD_ONLY)
    assert "- matchweek: 10" in md                                            # NFL: the row's week
    assert "UNCERTIFIED (registry nfl-elo-v1): market-only, the would-be call below is a record" in md


def test_a_quarantine_shadow_row_prints_summary_blocks_line(repo, nfl_market_only_off):
    doc = nfl_doc()
    r = doc["predictions"][1]
    assert cl.is_quarantine_shadow(r["desk"])
    assert b.run(closing_file=str(closing_file(repo, doc, "NFL"))) == 0
    x = cl.desk_rows({"predictions": [r]}, {r["match_id"]}, b.EPOCH, fam="NFL")[0]
    want = next(ln.strip() for ln in cl.summary_block(x).split("\n") if ln.strip().startswith("quarantine shadow"))
    md = md_of(repo, "NFL", 9302)
    assert f"- {want}" in md and want.endswith("shadow, not staked")


def test_an_mlb_row_carries_the_books_why_line(repo):
    doc = mlb_doc()
    src = closing_file(repo, doc, "MLB", books_why={9101: "provider listed the game, no odds"})
    assert b.run(closing_file=str(src)) == 0
    md = md_of(repo, "MLB", 9101)
    assert "- books: provider listed the game, no odds" in md
    assert "- starter: H. Arm (confirmed, ERA 3.1)" in md
    assert "- matchweek: not stored" in md


# ------------------------------------------------------------------------ item 2: the fields never printed --

def test_the_forbidden_fields_on_the_row_are_never_printed(repo):
    """The rows carry desk.order.text (BUY ... × n), desk.order.contracts, desk.exec.contracts, the row's
    fee_order_contracts and desk_meta.unit (label, fraction, half_fraction): none of them reaches either file."""
    doc = soccer_doc()
    d = doc["predictions"][0]["desk"]
    assert d["order"]["text"] and d["order"]["contracts"] and d["exec"]["contracts"]
    assert doc["desk_meta"]["unit"]["fraction"] and doc["desk_meta"]["unit"]["half_fraction"]
    assert b.run(closing_file=str(closing_file(repo, doc, "SOCCER"))) == 0
    md = md_of(repo, "SOCCER", 9401)
    for forbidden in (d["order"]["text"], d["order"]["unit"], "×", "BUY", "contract", "fraction",
                      "fee_order_contracts", "pool"):
        assert forbidden not in md
    assert pv.bulletin_offence(md) is None


# ----------------------------------------------------------- item 2: THE GUARD, one test per field / pattern --

_T = "KX" + "TESTGAME-26NOV08ALP-H"
_S = "$"
PLANTED = [
    ("desk.order text", f"BUY YES {_T} @ 0.45 " + "× 5", "order_text"),
    ("desk.exec.contracts", "exec contracts 7 at the ask", "contract_count"),
    ("fee_order_contracts", "fee_order_contracts: priced", "field_name"),
    ("a contract count", "size 12 contracts", "contract_count"),
    ("a dollar figure", f"stake {_S}25 today", "dollar"),
    ("desk_meta.unit.fraction", "unit fraction 0.08 of the pool", "fraction"),
    ("desk_meta.unit.half_fraction", "half_fraction applies", "fraction"),
    ("the pool", "pool 250 read today", "pool"),
    ("the account id", f"account {_Z}", "uuid"),
    ("a raw Kalshi row (#817 i)", f"{_Z},trade,{_T},yes", "uuid_beside_ticker"),
    ("the CSV header (#817 ii)", "a,quantity" "_fp,entry_price" "_dollars,realized_pnl_with_fees" "_dollars",
     "csv_header"),
    ("the unit label", "sized at 1u = ten", "unit_label"),
]


@pytest.mark.parametrize("what,text,pattern", PLANTED, ids=[p[0] for p in PLANTED])
def test_the_guard_refuses_each_forbidden_field_and_writes_nothing(repo, capsys, what, text, pattern):
    doc = soccer_doc()
    doc["predictions"][1]["desk"]["reason"] = f"edge below the floor · {text}"     # a printed field carries it
    src = closing_file(repo, doc, "SOCCER")
    assert b.run(closing_file=str(src)) == 2
    assert files_under(repo / "exports" / "bulletins") == []                  # nothing written, of either game
    rec = receipts()[-1]
    assert rec["exit"] == 2 and rec["written"] == []
    names = {r["pattern"] for r in rec["bulletin_refused"]}
    assert names == {pattern}
    paths = {r["path"] for r in rec["bulletin_refused"]}
    assert paths == {"exports/bulletins/SOCCER/2026-11-08/9402_delta-united_at_gamma-fc_closing.md",
                     "exports/bulletins/SOCCER/2026-11-08/9402_delta-united_at_gamma-fc_closing.png"}
    raw = c.receipts_path().read_text()
    out = capsys.readouterr().out
    assert text not in raw and text not in out                                # the name and path, never the line


def test_every_bulletin_pattern_has_a_planted_test():
    assert {p for _, _, p in PLANTED} == set(pv.PATTERN_NAMES)


def test_6b_the_positive_control_refuses_a_page_with_a_count_a_dollar_and_a_uuid_beside_a_ticker(repo):
    doc = soccer_doc()
    doc["predictions"][0]["desk"]["reasons"] = ["12 contracts", f"net {_S}4.56", f"{_Z} {_T}"]
    assert b.run(closing_file=str(closing_file(repo, doc, "SOCCER"))) == 2
    assert files_under(repo / "exports" / "bulletins") == [] and not (repo / "exports" / "bulletins").exists()
    assert receipts()[-1]["bulletin_refused"][0]["pattern"] in pv.PATTERN_NAMES


def test_the_card_text_is_guarded_too(repo):
    """The card draws the team names: a forbidden text there refuses the .png (and the .md that carries it)."""
    doc = soccer_doc()
    doc["predictions"][0]["home_team"] = "Pool 9 Rovers"
    assert b.run(closing_file=str(closing_file(repo, doc, "SOCCER"))) == 2
    refused = receipts()[-1]["bulletin_refused"]
    assert {r["pattern"] for r in refused} == {"pool"}
    assert any(r["path"].endswith(".png") for r in refused)
    assert files_under(repo / "exports" / "bulletins") == []


def test_an_api_key_is_redacted_by_sp_common_redact_on_every_line(repo, monkeypatch):
    key = "kk-" + "secret-value-7f3k9q"
    monkeypatch.setenv("ODDS_API_KEY", key)
    doc = soccer_doc()
    doc["predictions"][1]["desk"]["reason"] = f"edge below the floor · {key} · api_key=abcdef123"
    assert b.run(closing_file=str(closing_file(repo, doc, "SOCCER"))) == 0
    md = md_of(repo, "SOCCER", 9402)
    assert key not in md and "abcdef123" not in md and "[REDACTED]" in md
    assert key not in c.receipts_path().read_text()


# ------------------------------------------------------------------------------ 6(c): the "not stored" rule --

def test_a_row_without_its_injuries_block_prints_not_stored_and_no_warning(repo):
    doc = soccer_doc()
    r = doc["predictions"][0]
    r.pop("injuries")
    r["input_quality"].pop("injuries")
    assert b.run(closing_file=str(closing_file(repo, doc, "SOCCER"))) == 0
    md = md_of(repo, "SOCCER", 9401)
    assert "- injuries: not stored" in md and "WARNING" not in md
    assert b.EMPTY_LIST_WARNING not in md


def test_an_empty_injury_list_names_the_side_with_the_warning(repo):
    doc = soccer_doc()
    doc["predictions"][0]["input_quality"]["injuries"]["away"]["count"] = 0
    assert b.run(closing_file=str(closing_file(repo, doc, "SOCCER"))) == 0
    md = md_of(repo, "SOCCER", 9401)
    assert md.count("WARNING") == 1 and f"- WARNING Beta Hawks: an empty injury list, {b.EMPTY_LIST_WARNING}" in md


def test_a_missing_field_is_not_stored_never_a_default():
    assert b.v(None) == "not stored" and b.pp(None) == "not stored" and b.cents(None) == "not stored"


# --------------------------------------------------------------------------- (g): what changed since the slate --

def test_the_closing_bulletin_reads_the_days_slate_row_then_now(repo):
    slate = soccer_doc()
    slate["predictions"][0]["injuries"]["home_names"] = ["A. Keeper", "Z. Gone"]
    (repo / "exports" / "soccer_PL_2026-11-07_to_2026-11-10.json").write_text(json.dumps(slate))
    assert b.run(closing_file=str(closing_file(repo, soccer_doc(), "SOCCER"))) == 0
    md = md_of(repo, "SOCCER", 9401)
    assert "- the slate row: exports/soccer_PL_2026-11-07_to_2026-11-10.json" in md
    assert "- call: PLAY Alpha Owls 0.5u → PLAY Alpha Owls 0.5u" in md
    assert "- injuries Alpha Owls: added B. Back · removed Z. Gone" in md


def test_no_slate_row_says_first_sight_at_the_closing(repo):
    assert b.run(closing_file=str(closing_file(repo, soccer_doc(), "SOCCER"))) == 0
    assert f"- {b.NO_SLATE_ROW}" in md_of(repo, "SOCCER", 9401)


def test_a_slate_file_renders_slate_pairs_with_the_slate_stage(repo):
    p = repo / "exports" / "soccer_PL_2026-11-07_to_2026-11-10.json"
    p.write_text(json.dumps(soccer_doc()))
    assert b.run(slate_file=str(p)) == 0
    names = [x.name for x in files_under(repo / "exports" / "bulletins")]
    assert names == ["9401_beta-hawks_at_alpha-owls_slate.md", "9401_beta-hawks_at_alpha-owls_slate.png",
                     "9402_delta-united_at_gamma-fc_slate.md", "9402_delta-united_at_gamma-fc_slate.png"]
    md = md_of(repo, "SOCCER", 9401, "slate")
    assert f"- {b.SLATE_CHANGE}" in md and "- stage: slate, 2026-11-08 10:25 ET" in md
    assert "- run id: not stored" in md


# ------------------------------------------------------------------------------- item 4: never a JSON there --

def test_the_writer_refuses_a_json_and_any_other_suffix(repo):
    for name in ("x.json", "x.txt", "x"):
        with pytest.raises(b.Refused):
            b.write_file(repo / "exports" / "bulletins" / "SOCCER" / name, b"{}")
    assert files_under(repo / "exports" / "bulletins") == []


def test_no_json_is_ever_written_under_bulletins(repo):
    for fam, fn in (("SOCCER", soccer_doc), ("NFL", nfl_doc), ("MLB", mlb_doc)):
        assert b.run(closing_file=str(closing_file(repo, fn(), fam))) == 0
    got = files_under(repo / "exports" / "bulletins")
    assert got and {p.suffix for p in got} == {".md", ".png"}


# -------------------------------------------------------------------------------- item 4: the mirror's links --

def test_the_console_prints_each_files_mirror_url_never_the_remotes_value(repo, capsys):
    assert b.run(closing_file=str(closing_file(repo, soccer_doc(), "SOCCER"))) == 0
    out = capsys.readouterr().out
    assert ("https://github.com/owner-x/repo-y/blob/main/host/bulletins/SOCCER/2026-11-08/"
            "9401_beta-hawks_at_alpha-owls_closing.png") in out
    assert out.count("https://github.com/owner-x/repo-y/blob/main/host/bulletins/") == 4
    assert REMOTE not in out and "git@" not in out


@pytest.mark.parametrize("remote", ["https://github.com/owner-x/repo-y.git", "ssh://git@github.com/owner-x/repo-y.git"])
def test_the_remotes_other_forms_parse(repo, monkeypatch, remote):
    monkeypatch.setenv("SP_EXPORTS_MIRROR_REMOTE", remote)
    url = b.mirror_url("SOCCER/2026-11-08/x.md", repo / "exports" / "bulletins")
    assert url == "https://github.com/owner-x/repo-y/blob/main/host/bulletins/SOCCER/2026-11-08/x.md"


def test_an_unparseable_or_unset_remote_prints_why_and_never_the_value(repo, monkeypatch, capsys):
    odd = "git@example.invalid:scratch/private-path-9q.git"
    monkeypatch.setenv("SP_EXPORTS_MIRROR_REMOTE", odd)
    assert b.run(closing_file=str(closing_file(repo, soccer_doc(), "SOCCER"))) == 0
    out = capsys.readouterr().out
    assert odd not in out and "private-path-9q" not in out and "does not name a github.com owner/repo" in out
    monkeypatch.delenv("SP_EXPORTS_MIRROR_REMOTE")
    assert b.mirror_url("x.md", repo / "exports" / "bulletins") == "no mirror URL: SP_EXPORTS_MIRROR_REMOTE unset"
    monkeypatch.setenv("SP_EXPORTS_MIRROR_REMOTE", REMOTE)
    assert b.mirror_url("x.md", repo / "elsewhere").startswith("no mirror URL: --out-dir is not")


# -------------------------------------------------------------------------------------- refusals, DB, CLI --

def test_the_refusals(repo, tmp_path):
    assert b.run() == 2
    assert b.run(closing_file="a", slate_file="b") == 2
    no_block = repo / "exports" / "closing_SOCCER_2026-11-08T1635Z.json"
    no_block.write_text(json.dumps(soccer_doc()))
    assert b.run(closing_file=str(no_block)) == 2                              # no closing block: not a closing file
    named = repo / "exports" / "something_else.json"
    named.write_text(json.dumps(soccer_doc()))
    assert b.run(slate_file=str(named)) == 2                                   # no family's export_glob
    real = closing_file(repo, soccer_doc(), "SOCCER")
    assert b.run(slate_file=str(real)) == 2                                    # a closing file is never a slate file
    assert b.run(closing_file=str(real), out_dir=str(repo / "data" / "bulletins")) == 2      # law 5
    assert b.run(closing_file=str(real), db=str(tmp_path / "missing.db")) == 2              # the --db fence
    assert files_under(repo / "exports" / "bulletins") == [] and not (repo / "data").exists()


def test_pl_matchday_is_read_from_a_db_copy_mode_ro(repo, tmp_path):
    db = tmp_path / "copy" / "sports.db"
    db.parent.mkdir()
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE matches(id INTEGER PRIMARY KEY, matchday INT)")
    con.execute("INSERT INTO matches VALUES (9401, 11)")
    con.commit()
    con.close()
    before = db.read_bytes()
    assert b.run(closing_file=str(closing_file(repo, soccer_doc(), "SOCCER")), db=str(db)) == 0
    assert "- matchweek: 11" in md_of(repo, "SOCCER", 9401)
    assert "- matchweek: not stored" in md_of(repo, "SOCCER", 9402)
    assert db.read_bytes() == before and not list(db.parent.glob("*-wal")) and not list(db.parent.glob("*-shm"))


def test_without_a_readable_db_the_matchday_is_not_stored_and_none_is_created(repo, tmp_path):
    assert b.run(closing_file=str(closing_file(repo, soccer_doc(), "SOCCER"))) == 0
    assert "- matchweek: not stored (the DB cannot be read: FileNotFoundError)" in md_of(repo, "SOCCER", 9401)
    assert not (tmp_path / "no-such.db").exists()


def test_the_cli_command(repo):
    from click.testing import CliRunner

    import cli
    src = closing_file(repo, soccer_doc(), "SOCCER")
    res = CliRunner().invoke(cli.cli, ["bulletin", "--closing-file", str(src)])
    assert res.exit_code == 0, res.output
    assert "BULLETIN SOCCER closing: 4 file(s) written" in res.output
    res = CliRunner().invoke(cli.cli, ["bulletin"])
    assert res.exit_code == 2 and "BULLETIN REFUSED" in res.output


# ------------------------------------------------------------------------------ one definition, dependency --

def test_the_817_patterns_have_one_definition():
    import test_no_raw_kalshi_rows as t
    assert t.UUID is pv.UUID and t.TICKER is pv.TICKER and t.DOLLAR is pv.DOLLAR and t.CSV_RUN is pv.CSV_RUN
    assert t._is_row is pv.is_row and t._is_header is pv.is_header


def test_matplotlib_is_the_one_new_dependency():
    lines = [ln.split("#")[0].strip() for ln in (ROOT / "requirements.txt").read_text().splitlines()]
    assert "matplotlib>=3.8" in lines
