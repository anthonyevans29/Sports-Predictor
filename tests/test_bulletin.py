"""THE BULLETIN RENDERER (ARCHITECT 2026-11-04 11:20 ET, addendum 250 items 1-4 and 6(a)-(c); addendum 289 item 4;
lane #826, step 1b): deploy/hosting/bulletin.py and `cli.py bulletin`.

Pinned here: the clean pair at the ruled path (exports/bulletins/<FAMILY>/<ET date>/<match>_<away>_at_<home>_<stage>
.md + .png); the card 1080 px wide, portrait; the call-line parity of 6(a) (closing.call_text and closing
.would_be_text, verbatim); THE WRITER-SIDE GUARD of item 2, one test per forbidden field or pattern (desk.order text,
desk.exec.contracts, fee_order_contracts, a contract count, a dollar figure, desk_meta.unit.fraction, half_fraction,
the pool, the account id, the #817 row and header, the API key, refused once sp_common.redact marks it, 298 B 5):
a refused run writes
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
    assert "(registry nfl-elo-v1): market-only, the would-be call below is a record, not a pick" in md


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
    ("a dollar figure in words", "stake 25 USD", "usd_word"),
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
    assert paths == {f"exports/bulletins/SOCCER/2026-11-08/9402_….md (file name withheld: matched {pattern})",
                     f"exports/bulletins/SOCCER/2026-11-08/9402_….png (file name withheld: matched {pattern})"}
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
    assert any(".png (file name withheld: matched pool)" in r["path"] for r in refused)   # the name is the value
    assert files_under(repo / "exports" / "bulletins") == []


def test_a_refused_team_name_is_not_named_by_its_own_path(repo, capsys):
    """Codex #894 P2: the file name embeds slug(team), so a UUID in a team name would reach the receipt and the
    console through the refused path. The path's file name is withheld; the folder, the match id and the pattern stay."""
    doc = soccer_doc()
    doc["predictions"][0]["home_team"] = f"Owls {_Z}"
    assert b.run(closing_file=str(closing_file(repo, doc, "SOCCER"))) == 2
    refused = receipts()[-1]["bulletin_refused"]
    assert {r["pattern"] for r in refused} == {"uuid"}
    assert {r["path"] for r in refused} == {
        "exports/bulletins/SOCCER/2026-11-08/9401_….md (file name withheld: matched uuid)",
        "exports/bulletins/SOCCER/2026-11-08/9401_….png (file name withheld: matched uuid)"}
    raw, out = c.receipts_path().read_text(), capsys.readouterr().out
    assert _Z not in raw and _Z not in out
    assert files_under(repo / "exports" / "bulletins") == []


def test_a_refused_team_name_joined_by_hyphens_is_withheld_too(repo):
    """slug() joins a name's words with "-": "Pool 9 Rovers" is pool-9-rovers in the path, still withheld."""
    doc = soccer_doc()
    doc["predictions"][0]["home_team"] = "Pool 9 Rovers"
    assert b.run(closing_file=str(closing_file(repo, doc, "SOCCER"))) == 2
    paths = {r["path"] for r in receipts()[-1]["bulletin_refused"]}
    assert paths and all("withheld" in p and "rovers" not in p for p in paths)


def test_every_refusal_withholds_the_file_name_and_names_the_pattern_and_the_game(repo):
    """Addendum 299 item 1: "withhold the file name on EVERY refusal — the receipt names the pattern and the game id
    only". A refused reason (not a team name) withholds it too; the team slugs never reach the receipt."""
    doc = soccer_doc()
    doc["predictions"][1]["desk"]["reason"] = "size 12 contracts"
    assert b.run(closing_file=str(closing_file(repo, doc, "SOCCER"))) == 2
    assert {r["path"] for r in receipts()[-1]["bulletin_refused"]} == {
        "exports/bulletins/SOCCER/2026-11-08/9402_….md (file name withheld: matched contract_count)",
        "exports/bulletins/SOCCER/2026-11-08/9402_….png (file name withheld: matched contract_count)"}
    assert "delta-united" not in c.receipts_path().read_text()


@pytest.mark.parametrize("team,pattern", [("Owls $25", "dollar"), ("Owls 12 contracts", "contract_count")])
def test_a_refused_value_in_a_team_name_never_reaches_the_receipt_through_its_slug(repo, capsys, team, pattern):
    """Codex #894 round 4: slug() turns "Owls $25" into owls-25, which no reading of the path finds."""
    doc = soccer_doc()
    doc["predictions"][0]["home_team"] = team
    assert b.run(closing_file=str(closing_file(repo, doc, "SOCCER"))) == 2
    rec = receipts()[-1]
    assert {r["pattern"] for r in rec["bulletin_refused"]} == {pattern}
    raw, out = c.receipts_path().read_text(), capsys.readouterr().out
    for leak in (b.slug(team), "owls"):
        assert leak not in raw and leak not in out


@pytest.mark.parametrize("secret", ["api\u200b_key=abcdef123", "api_key\uff1dabcdef123", "to\u200dken: abcdef123"],
                         ids=["zero-width space", "fullwidth equals", "zero-width joiner"])
def test_a_credential_written_with_an_invisible_or_fullwidth_character_is_refused(repo, capsys, secret):
    """Addendum 299 item 1 (Codex #894 round 4, P1): the key rule also reads the guard's normalized text."""
    assert sp_redact_misses(secret)                                           # the raw reading alone misses it
    doc = soccer_doc()
    doc["predictions"][1]["desk"]["reason"] = f"edge below the floor · {secret}"
    assert b.run(closing_file=str(closing_file(repo, doc, "SOCCER"))) == 2
    assert {r["pattern"] for r in receipts()[-1]["bulletin_refused"]} == {b.SECRET_PATTERN}
    raw, out = c.receipts_path().read_text(), capsys.readouterr().out
    assert "abcdef123" not in raw and "abcdef123" not in out
    assert files_under(repo / "exports" / "bulletins") == []


def sp_redact_misses(text):
    return c.redact(text) == text and pv.bulletin_offence(text) is None


@pytest.mark.parametrize("text", ["contract count: 5", "contract count = 12", "Contracts-Count 3", "contract_count=7"])
def test_the_contract_count_pattern_takes_the_count_label(text):
    """Addendum 299 item 1: "the contract-count pattern accepts the `count` label" (it tightens 298 B.4's set)."""
    assert pv.bulletin_offence(text) == "contract_count"



@pytest.mark.parametrize("what", ["an env key", "a key=value"])
def test_a_secret_in_the_source_refuses_the_run_never_redacted_into_a_file(repo, monkeypatch, capsys, what):
    """Addendum 298 B item 5: "A secret in the source: REFUSE, do not redact". The run writes nothing, the receipt
    names the pattern `secret` and the paths, and neither the key nor the line reaches the receipt or the console."""
    key = "kk-" + "secret-value-7f3k9q"
    monkeypatch.setenv("ODDS_API_KEY", key)
    secret = key if what == "an env key" else "api_key=abcdef123"
    doc = soccer_doc()
    doc["predictions"][1]["desk"]["reason"] = f"edge below the floor · {secret}"
    assert b.run(closing_file=str(closing_file(repo, doc, "SOCCER"))) == 2
    assert files_under(repo / "exports" / "bulletins") == []
    rec = receipts()[-1]
    assert rec["exit"] == 2 and {r["pattern"] for r in rec["bulletin_refused"]} == {b.SECRET_PATTERN}
    assert {r["path"] for r in rec["bulletin_refused"]} == {                   # a secret always withholds the name
        "exports/bulletins/SOCCER/2026-11-08/9402_….md (file name withheld: matched secret)",
        "exports/bulletins/SOCCER/2026-11-08/9402_….png (file name withheld: matched secret)"}
    raw, out = c.receipts_path().read_text(), capsys.readouterr().out
    for leak in (key, "abcdef123", "edge below the floor"):
        assert leak not in raw and leak not in out


@pytest.mark.parametrize("team", ["Owls api_key=abcdef123", "Owls token: abcdef123"])
def test_a_secret_in_a_team_name_never_reaches_the_receipt_through_the_slugged_path(repo, capsys, team):
    """Codex #894 round 3, P1: slug() turns api_key=abcdef123 into api-key-abcdef123, which neither the redaction nor
    the guard reads; the refused path withholds the file name, so the value is in neither the receipt nor the console."""
    doc = soccer_doc()
    doc["predictions"][0]["home_team"] = team
    assert b.run(closing_file=str(closing_file(repo, doc, "SOCCER"))) == 2
    rec = receipts()[-1]
    assert {r["pattern"] for r in rec["bulletin_refused"]} == {b.SECRET_PATTERN}
    assert all("file name withheld: matched secret" in r["path"] for r in rec["bulletin_refused"])
    raw, out = c.receipts_path().read_text(), capsys.readouterr().out
    assert "abcdef123" not in raw and "abcdef123" not in out
    assert files_under(repo / "exports" / "bulletins") == []


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


# ------------------------------------------------------------- the fixer's round (verifiers' findings, pinned) --

_NL_PLANTED = [
    ("a dollar split by a newline", "stake " + _S + "\n12 and 12\ncontracts"),
    ("a count split by a newline", "size 12\ncontracts"),
    ("a count split by a carriage return", "size 12\rcontracts"),
    ("a dollar split by a vertical tab", "stake " + _S + "\v12"),
]


@pytest.mark.parametrize("what,text", _NL_PLANTED, ids=[p[0] for p in _NL_PLANTED])
def test_a_value_split_across_lines_is_still_refused(repo, what, text):
    """A row value with a line break in it: the card's textwrap and GitHub's list continuation join it on one line,
    so the guard reads it joined too."""
    doc = soccer_doc()
    doc["predictions"][1]["desk"]["reason"] = f"edge below the floor · {text}"
    assert b.run(closing_file=str(closing_file(repo, doc, "SOCCER"))) == 2
    assert files_under(repo / "exports" / "bulletins") == []


def test_no_row_value_spans_two_lines_of_the_markdown(repo):
    doc = soccer_doc()
    doc["predictions"][1]["desk"]["reason"] = "edge below the floor\nsecond line\r\nthird\u2028fourth"
    assert b.run(closing_file=str(closing_file(repo, doc, "SOCCER"))) == 0
    md = md_of(repo, "SOCCER", 9402)
    assert "- reason: edge below the floor second line third fourth" in md      # a run of breaks: one space
    assert "\r" not in md and "\u2028" not in md


def _json_forms(d=None):
    """Built at test time (the Desk's unit pin is conftest's autouse fixture, so the order block only carries its
    count inside a test)."""
    d = d or {"exec": {}, "order": {}}
    return [("the exec block as JSON", json.dumps(d["exec"])),
            ("the order block as JSON", json.dumps(d["order"])),
            ("the exec block as a dict", str(d["exec"])),
            ("a JSON contracts key", '{"contracts": 5}'),
            ("a dict contracts key", "{'contracts': 5}"),
            ("maker_contracts", "maker_contracts 5"),
            ("n_contracts", "n_contracts=5"),
            ("pool_usd", "pool_usd: 250.0"),
            ("balance_dollars", '"balance_dollars": 250'),
            ("market_exposure_dollars", "market_exposure_dollars 40"),
            ("unit_fraction", "unit_fraction 0.08"),
            ("a JSON fraction key", '"fraction": 0.08')]


@pytest.mark.parametrize("what", [p[0] for p in _json_forms()])
def test_the_forbidden_fields_in_the_exports_own_shape_are_refused(repo, what):
    doc = soccer_doc()
    d = doc["predictions"][0]["desk"]
    assert d["order"]["contracts"] and d["exec"]["contracts"]               # the counts are on the blocks planted
    text = dict(_json_forms(d))[what]
    doc["predictions"][1]["desk"]["reason"] = f"edge below the floor · {text}"
    assert b.run(closing_file=str(closing_file(repo, doc, "SOCCER"))) == 2
    assert files_under(repo / "exports" / "bulletins") == []


_USD_FORMS = [("12 USD", "12 USD"), ("USD 12", "USD 12"), ("12 dollars", "12 dollars"), ("12$", "12" + _S),
              ("fullwidth sign and digits", "\uff04\uff11\uff12"), ("a zero-width space", _S + "\u200b12"),
              ("an HTML entity", "&#36;12"), ("a named HTML entity", "&dollar;12"), ("a tag between", _S + "<b></b>12"),
              ("emphasis between", _S + "**1**2")]


@pytest.mark.parametrize("what,text", _USD_FORMS, ids=[p[0] for p in _USD_FORMS])
def test_dollar_figures_without_a_plain_sign_and_lookalikes_are_refused(repo, what, text):
    doc = soccer_doc()
    doc["predictions"][1]["desk"]["reason"] = f"edge below the floor · stake {text}"
    assert b.run(closing_file=str(closing_file(repo, doc, "SOCCER"))) == 2
    assert files_under(repo / "exports" / "bulletins") == []


@pytest.mark.parametrize("text", ["@ 0.45 x 3", "x 3 at 45c", "fill x3 today", "@ 45c x 3"])
def test_an_ascii_x_count_is_order_text(text):
    assert pv.bulletin_offence(f"edge below the floor · {text}") == "order_text"


def test_a_team_name_in_dollar_math_is_drawn_literally_and_escaped_in_the_markdown(repo):
    """An unbalanced $...$ in a team name: the card draws it as text (no mathtext, no ParseException) and the
    Markdown escapes the $, so GitHub never renders it as math."""
    doc = soccer_doc()
    doc["predictions"][0]["home_team"] = "Mu$\\alpha{$ Owls"
    assert b.run(closing_file=str(closing_file(repo, doc, "SOCCER"))) == 0
    md = md_of(repo, "SOCCER", 9401)
    assert "Mu\\$\\alpha{\\$ Owls" in md and "Mu$" not in md


def test_tick_labels_are_never_mathtext(repo, monkeypatch):
    from matplotlib.axes import Axes
    seen = []
    real = Axes.set_xticklabels

    def spy(self, labels, *a, **k):
        seen.append(k.get("parse_math"))
        return real(self, labels, *a, **k)
    monkeypatch.setattr(Axes, "set_xticklabels", spy)
    assert b.run(closing_file=str(closing_file(repo, soccer_doc(), "SOCCER"))) == 0
    assert seen and all(x is False for x in seen)


def test_a_failed_render_never_receipts_row_text_the_guard_would_refuse(repo, capsys):
    doc = soccer_doc()
    doc["predictions"][0]["prediction"]["probabilities"]["home_win"] = f"{_S}12 · 7 contracts"
    assert b.run(closing_file=str(closing_file(repo, doc, "SOCCER"))) == 1
    rec = receipts()[-1]
    raw, out = c.receipts_path().read_text(), capsys.readouterr().out
    assert rec["exit"] == 1 and rec["bulletin_failed"].startswith("ValueError (message withheld: matched ")
    for leak in (f"{_S}12", "7 contracts"):
        assert leak not in raw and leak not in out
    assert files_under(repo / "exports" / "bulletins") == []


def test_a_render_that_throws_on_a_secret_never_receipts_it(repo, capsys):
    """Addendum 301 item 1 (Codex #894, P1): a probability holding a credential with a fullwidth '=' makes pct() raise;
    the failure text passes the same guard (the secret reading too): bulletin_failed withholds it, pattern named."""
    doc = soccer_doc()
    doc["predictions"][0]["prediction"]["probabilities"]["home_win"] = "api_key\uff1dabcdef123"
    assert b.run(closing_file=str(closing_file(repo, doc, "SOCCER"))) == 1
    rec = receipts()[-1]
    assert rec["exit"] == 1 and rec["bulletin_failed"].endswith(f"(message withheld: matched {b.SECRET_PATTERN})")
    raw, out = c.receipts_path().read_text(), capsys.readouterr().out
    assert "abcdef123" not in raw and "abcdef123" not in out
    assert files_under(repo / "exports" / "bulletins") == []


@pytest.mark.parametrize("text", ["25 remains in the pool", "1,200 left in the pool", "pool: 25"])
def test_the_pool_pattern_takes_the_amount_before_the_label(text):
    """Addendum 301 item 1: the amount-before-label form, a tightening."""
    assert pv.bulletin_offence(text) == "pool"


@pytest.mark.parametrize("text,pattern", [
    ("[api_key](https://example.test)=abcdef123", "secret"), ("\\$[25](https://example.test)", "dollar"),
    ("[12](https://example.test) contracts", "contract_count"), ("![12](x.png) contracts", "contract_count"),
    ("[12][ref] contracts", "contract_count"),
    ("[api_key](https://example.test/a(b))=abcdef123", "secret")],
    ids=["link-secret", "link-dollar", "link-count", "image", "ref-link", "link-nested-parens"])
def test_markdown_link_syntax_is_read_as_github_shows_it(repo, capsys, text, pattern):
    """Addendum 304 item 1 (Codex #894, P1): rendered() collapses link and image syntax to the visible label before any
    pattern runs, so a value broken by link syntax is refused like the plain one."""
    doc = soccer_doc()
    doc["predictions"][1]["desk"]["reason"] = f"edge below the floor · {text}"
    assert b.run(closing_file=str(closing_file(repo, doc, "SOCCER"))) == 2
    assert {r["pattern"] for r in receipts()[-1]["bulletin_refused"]} == {pattern}
    raw, out = c.receipts_path().read_text(), capsys.readouterr().out
    assert "abcdef123" not in raw and "abcdef123" not in out
    assert files_under(repo / "exports" / "bulletins") == []


def test_collapse_links_keeps_plain_text_and_shows_autolinks():
    assert pv.collapse_links("see <https://example.test/x> and [the page](u)") == "see https://example.test/x and the page"
    assert pv.collapse_links("edge 4.1pp [a](b) [c](d)") == "edge 4.1pp a c"


@pytest.mark.parametrize("text,shown", [
    ("[api_key](https://example.test/a(b))=abcdef123", "api_key=abcdef123"),       # 306 item 1(a), the reproduced case
    ("[x](a(b(c)d)e)y", "xy"),                                                      # nesting deeper than one level
    ("[12](<u(>) USD", "12 USD"),                                                   # an angle-bracket destination
    ('[12](u "t(") USD', "12 USD"),                                                 # a quoted title holding a '('
    ("[a [b] c](u)!", "a [b] c!"),                                                  # balanced brackets in the label
    ("[l1]([l2](u))", "l1"),                                                        # a link as the destination
    ("[12](u((a)) USD", "[12](u((a)) USD"),                                         # never closes: not a link, kept
    ("\\[12](u) USD", "\\[12](u) USD"),                                         # an escaped bracket: not a link
])
def test_collapse_links_reads_balanced_parentheses_as_github_does(text, shown):
    """Addendum 306 item 1(a) (Codex #894, P1): a small scanner, not a longer regex, reads a link target's balanced
    parentheses, so a link GitHub shows collapses to its label before the patterns run."""
    assert pv.collapse_links(text) == shown


def test_a_nested_parenthesis_link_secret_is_refused_as_secret():
    assert b.secret_offence("[api_key](https://example.test/a(b))=abcdef123") == "secret"


def test_the_maths_prints_per_contract_prices_in_cents(repo):
    """Addendum 306 item 1(b): THE MATHS prints taker cost, maker cost, join price and the exec line's cost in cents,
    as the order and quote lines do; the guard's dollar pattern is unchanged."""
    doc = soccer_doc()
    ex = doc["predictions"][0]["desk"]["exec"]
    ex.update({"cost": 0.734, "taker_cost": 0.46, "maker_cost": 0.45, "join_price": 0.44})
    assert b.run(closing_file=str(closing_file(repo, doc, "SOCCER"))) == 0
    maths = md_of(repo, "SOCCER", doc["predictions"][0]["match_id"]).split("## THE MATHS", 1)[1].split("\n## ", 1)[0]
    assert "− 73.4c →" in maths
    assert "taker cost 46c · maker cost 45c · join price 44c" in maths
    lines = [ln for ln in maths.splitlines() if ln.startswith(("- exec edge", "- cost:"))]
    assert len(lines) == 2
    for raw in ("0.734", "0.46", "0.45", "0.44"):                  # the prices, never as stored decimals
        assert all(raw not in ln for ln in lines), raw


@pytest.mark.parametrize("text", ["the pool is 25", "pool balance: 25", "pool now contains 25"])
def test_the_pool_pattern_takes_words_between_the_label_and_the_figure(text):
    """Addendum 304 item 1: the label-first direction allows a few words before the figure (a tightening)."""
    assert pv.bulletin_offence(text) == "pool"


def test_a_failed_write_leaves_no_half_pair_and_nothing_staged(repo, monkeypatch):
    """Addendum 304 item 1: the set is staged complete; a later write's failure leaves the earlier files OUT."""
    doc = soccer_doc()
    real, calls = b._write_all, []
    def fail_on_png(fd, data):                    # the run stages .md, .png per game: the second write is a .png
        calls.append(fd)
        if len(calls) == 2:
            raise OSError(28, "No space left on device")
        return real(fd, data)
    monkeypatch.setattr(b, "_write_all", fail_on_png)
    assert b.run(closing_file=str(closing_file(repo, doc, "SOCCER"))) == 1
    root = repo / "exports" / "bulletins"
    left = [p for p in root.rglob("*") if p.is_file()] if root.exists() else []
    assert left == [], left                                   # no .md without its .png, no staged leftovers
    assert receipts()[-1]["written"] == []


def test_a_by_hand_run_reads_host_env_for_the_redaction(repo, tmp_path, monkeypatch):
    key = "hk-" + "host-only-value-4r8t"
    henv = tmp_path / "host.env"
    henv.write_text(f"ODDS_API_KEY={key}\n")
    monkeypatch.setattr(c, "HOST_ENV", henv)
    monkeypatch.setenv("ODDS_API_KEY", "placeholder")
    monkeypatch.delenv("ODDS_API_KEY")                 # registered for restore, then unset: host.env is the only copy
    doc = soccer_doc()
    doc["predictions"][1]["desk"]["reason"] = f"edge below the floor · {key}"
    assert b.run(closing_file=str(closing_file(repo, doc, "SOCCER"))) == 2     # host.env's key is read: refused
    assert {r["pattern"] for r in receipts()[-1]["bulletin_refused"]} == {b.SECRET_PATTERN}
    assert key not in c.receipts_path().read_text()
    assert files_under(repo / "exports" / "bulletins") == []


def test_a_refusal_under_another_out_dir_names_that_path(repo, tmp_path):
    doc = soccer_doc()
    doc["predictions"][1]["desk"]["reason"] = "size 12 contracts"
    other = tmp_path / "elsewhere"
    assert b.run(closing_file=str(closing_file(repo, doc, "SOCCER")), out_dir=str(other)) == 2
    paths = {r["path"] for r in receipts()[-1]["bulletin_refused"]}
    assert paths == {f"{other / 'SOCCER' / '2026-11-08'}/9402_….md (file name withheld: matched contract_count)",
                     f"{other / 'SOCCER' / '2026-11-08'}/9402_….png (file name withheld: matched contract_count)"}
    assert not other.exists()


@pytest.mark.parametrize("mid", ["../../escape", "9401/x", True, 94.01, None])
def test_a_match_id_that_is_not_an_integer_is_skipped_never_a_path(repo, mid):
    doc = soccer_doc()
    doc["predictions"][0]["match_id"] = mid
    src = closing_file(repo, doc, "SOCCER", ids=[9402])
    raw = json.loads(src.read_text())
    raw["predictions"].insert(0, doc["predictions"][0])          # the odd row rides the file as written
    src.write_text(json.dumps(raw))
    assert b.run(closing_file=str(src)) == 0
    rec = receipts()[-1]
    assert {"match_id": None, "why": "match_id not an integer"} in rec["skipped"]
    assert all("/9402_" in p for p in rec["written"]) and len(rec["written"]) == 2
    assert not (repo / "escape").exists() and not (repo / "exports" / "escape").exists()


def test_an_order_under_one_contract_prints_no_side_or_limit(repo):
    doc = soccer_doc()
    o = doc["predictions"][0]["desk"]["order"]
    assert o["text"] and o["side"] and o["limit"] is not None
    o["text"], o["why"] = None, "0.5u at the unit's basis is under one contract at 0.45"
    assert b.run(closing_file=str(closing_file(repo, doc, "SOCCER"))) == 0
    md = md_of(repo, "SOCCER", 9401)
    assert "- order: none written (the reason is on the closing page)" in md
    assert "limit 45c" not in md and "YES on Kalshi" not in md


def test_the_certification_line_never_infers_a_state(repo):
    """SOCCER/MLB with no registry entry: "certification not read", labelled (registry.certification_of's unread
    reason), never "live". NFL: the withholding entry's own certification text, verbatim."""
    assert b.run(closing_file=str(closing_file(repo, soccer_doc(), "SOCCER"))) == 0
    md = md_of(repo, "SOCCER", 9401)
    assert ("- certification: test-model-v0 — certification not read (no registry entry for test-model-v0)" in md)
    assert "would-be" not in md.split("## THE CALL")[0]
    assert b.run(closing_file=str(closing_file(repo, nfl_doc(), "NFL"))) == 0
    from src.walters import registry
    entry = next(e for e in registry.load(registry.LEDGER) if e.get("id") == "nfl-elo-v1")
    md = md_of(repo, "NFL", 9301)
    assert (f"- certification: nfl_elo_v1 — {entry['certification']} (registry nfl-elo-v1): market-only, the "
            "would-be call below is a record, not a pick") in md


def test_a_matplotlibrc_cannot_change_the_cards_width(repo):
    import matplotlib
    with matplotlib.rc_context({"savefig.bbox": "tight", "figure.dpi": 50, "savefig.dpi": 300}):
        assert b.run(closing_file=str(closing_file(repo, soccer_doc(), "SOCCER"))) == 0
    for p in [p for p in files_under(repo / "exports" / "bulletins") if p.suffix == ".png"]:
        w, h = png_size(p)
        assert w == 1080 and h >= b.CARD_MIN_HEIGHT_PX


def test_mlb_and_nfl_print_the_injury_names_line_not_stored(repo):
    doc = mlb_doc()
    doc["predictions"][0].pop("injuries")                       # an MLB row carries no injuries block (export.py)
    assert b.run(closing_file=str(closing_file(repo, doc, "MLB"))) == 0
    assert md_of(repo, "MLB", 9101).count("- injuries: not stored") == 2           # one per side
    doc = nfl_doc()
    doc["predictions"][0]["market"]["consensus_home_spread"] = -3.5
    assert b.run(closing_file=str(closing_file(repo, doc, "NFL"))) == 0
    md = md_of(repo, "NFL", 9301)
    assert "- injured by name: not stored" in md
    assert "- margin line (consensus home spread): -3.5 · total line: not stored" in md
    assert "- margin line (consensus home spread): not stored · total line: not stored" in md_of(repo, "NFL", 9302)


def test_a_slate_with_no_exported_at_says_not_stored_on_the_card_too(repo):
    doc = soccer_doc()
    doc.pop("exported_at")
    files, _ = b.plan(doc, "SOCCER", "slate", repo / "exports" / "soccer_PL_x.json", repo / "exports" / "bulletins",
                      None)
    md = files[0][2]
    card = files[1][1]
    assert "- stage: slate, not stored" in md
    assert any("slate, not stored" in t for t in card["head"])


def test_the_role_is_stripped_as_closing_strips_it(repo, monkeypatch):
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", " host \n")
    assert b.mirror_url("x.md", repo / "exports" / "bulletins").startswith("https://github.com/owner-x/repo-y/")


def test_the_card_and_both_games_never_carry_the_forbidden_fields(repo):
    doc = soccer_doc()
    files, _ = b.plan(cl.closing_doc(doc, "SOCCER", NOW + timedelta(minutes=35), RUN_ID,
                                     [r["match_id"] for r in doc["predictions"]], [], None), "SOCCER", "closing",
                      repo / "exports" / "closing_x.json", repo / "exports" / "bulletins", None)
    d = doc["predictions"][0]["desk"]
    texts = [t for _, _, t in files]
    assert len(texts) == 4
    for t in texts:
        assert pv.bulletin_offence(t) is None
        for forbidden in (d["order"]["text"], d["order"]["unit"], "\u00d7", "BUY", "contract", "fraction",
                          "fee_order_contracts", "pool"):
            assert forbidden not in t


def test_the_817_patterns_keep_their_escapes_and_their_reach():
    src = (ROOT / "src" / "privacy_patterns.py").read_text(encoding="utf-8")
    code = [ln for ln in src.splitlines() if "re.compile(" in ln or "re.split(" in ln or "_KEY_TAIL =" in ln
            or ln.lstrip().startswith(('"', 'r"'))]
    assert len(code) >= 12
    for ch in ("\u241f", "\uff04", "\ufe69", "\u2212", "\u00a0", "\u00d7"):
        assert not any(ch in ln for ln in code), f"U+{ord(ch):04X} must be spelled as an escape in the patterns"
    assert pv.DOLLAR.search(_S + "\u00a012") and pv.DOLLAR.search(_S + "\u221212") and pv.DOLLAR.search("\uff0412")
    assert pv.is_header("a\u241fquantity" "_fp\u241fentry_price" "_dollars\u241frealized_pnl_with_fees" "_dollars")


# ------------------------------------------------------------- addendum 309 item 2: one push on the guard --
# ARCHITECT 2026-11-09 12:50 ET, addendum 309 item 2 (P1): "the bulletin's own secret check reads credential labels
# with internal whitespace and mixed case on the normalized text — `api key`, `secret key`, `access token`, `private
# key`, `client secret`, `auth token`, `bearer` — refusing as `secret`; tests on `api key = abcdef123`, `API Key:
# abcdef123`, `secret key=abcdef123`, `access token abcdef123`; `sp_common.redact` unchanged (shared)."

LABELLED = ["api key = abcdef123", "API Key: abcdef123", "secret key=abcdef123", "access token abcdef123"]


@pytest.mark.parametrize("secret", LABELLED)
def test_a_credential_label_with_internal_whitespace_refuses_the_run_as_secret(repo, capsys, secret):
    """Each refuses the run under `secret`, writes nothing, and the value is in neither the receipt nor the console;
    sp_common.redact alone misses every one (the bulletin's own check reads them)."""
    assert c.redact(secret) == secret                                        # the shared redaction is unchanged
    doc = soccer_doc()
    doc["predictions"][1]["desk"]["reason"] = f"edge below the floor · {secret}"
    assert b.run(closing_file=str(closing_file(repo, doc, "SOCCER"))) == 2
    rec = receipts()[-1]
    assert rec["exit"] == 2 and {r["pattern"] for r in rec["bulletin_refused"]} == {b.SECRET_PATTERN}
    raw, out = c.receipts_path().read_text(), capsys.readouterr().out
    assert "abcdef123" not in raw and "abcdef123" not in out
    assert files_under(repo / "exports" / "bulletins") == []


@pytest.mark.parametrize("text", ["private key: abcdef123", "Client Secret abcdef123", "AUTH\tTOKEN = abcdef123",
                                  "Bearer abcdef123", "bearer: eyJhbGciOiJIUzI1NiJ9", "api_key abcdef123",
                                  "access\u200btoken abcdef123", "Access  Token\nabcdef123", "ＡＰＩ ＫＥＹ: abcdef123"])
def test_every_ruled_label_is_read_on_the_normalized_text(text):
    assert b.secret_offence(text) == b.SECRET_PATTERN


@pytest.mark.parametrize("text", ["the key match of the round", "Bearer of bad news", "Bearers 12 points",
                                  "the private key players are out", "a secret key to the 3-0 win",
                                  "the access token is gone", "auth tokens", "edge below the floor"])
def test_ordinary_bulletin_prose_is_not_a_credential(text):
    """"bearer" needs a token-shaped value after it; a label followed by a plain word is prose."""
    assert b.secret_offence(text) is None and not b.CREDENTIAL.search(text)


# The internal review of 54447764: the label forms the four ruled inputs do not cover (a quoted or bracketed value, a
# dash or an arrow between label and value, a U+2010/U+2011 hyphen inside the label, a tag that rendered() drops).
@pytest.mark.parametrize("text", ['api key "abcdef123"', "api key (abcdef123)", "auth token «abc123def»",
                                  "api key — abcdef123", "api key – abcdef123", "api key -> abcdef123",
                                  "api key → abcdef123", "api‐key abcdef123", "api‑key abcdef123",
                                  "client—secret abcdef123", "api key<b>abcdef123</b>", "Bearer <abcdef123>"])
def test_a_label_with_a_quoted_dashed_or_tag_joined_value_is_refused(text):
    assert b.secret_offence(text) == b.SECRET_PATTERN


# ARCHITECT 2026-11-10 08:50 ET, addendum 318 item 2 (Codex #894 P1, privacy_patterns.py:130): a credential or a
# figure split by an HTML comment or tag longer than _TAG's 200 characters renders contiguous on GitHub; the rendered
# reading strips comments and tags of any length (strip_html), so both offence checks read it.
_LONG = {"a 210-character": 210, "a 4,000-character": 4000}


@pytest.mark.parametrize("size", list(_LONG.values()), ids=list(_LONG))
@pytest.mark.parametrize("form", ["comment", "span title"])
def test_a_long_comment_or_tag_splitting_a_value_is_read_as_rendered(form, size):
    def split(left, right):
        if form == "comment":
            return left + "<!--" + "x" * size + "-->" + right
        return left + "<span title='" + "x" * size + "'>" + right
    assert len(split("", "")) > 200                                          # longer than _TAG's cap
    assert b.secret_offence(split("api key", "abcdef123")) == b.SECRET_PATTERN
    assert pv.bulletin_offence(split(_S, "25")) == "dollar"
    assert pv.rendered(split("api key", "abcdef123")) == "api keyabcdef123"


def test_an_unterminated_comment_hides_to_the_end_of_the_text_and_the_raw_reading_still_sees_it():
    text = "edge below the floor <!-- " + _S + "25 · api key: abcdef123"
    assert pv.rendered(text) == "edge below the floor "                      # hidden to the end, as GitHub hides it
    assert pv.bulletin_offence(text) == "dollar"                             # the line as written still carries it
    assert b.secret_offence("edge below the floor <!-- api key: abcdef123") == b.SECRET_PATTERN


def test_strip_html_keeps_text_that_is_not_markup():
    """A `<` that opens neither a comment nor a tag is text: a comparison, an autolink, an entity-written opener."""
    assert pv.strip_html("x < 5 and y > 3") == "x < 5 and y > 3"
    assert pv.strip_html("<https://example.com/a>") == "<https://example.com/a>"
    assert pv.strip_html("&lt;!-- shown") == "&lt;!-- shown"
    assert pv.strip_html("a<span\ntitle='q>r'\n>b</span>c<!-->d<!--->e") == "abcde"


@pytest.mark.parametrize("text", ["api keys are rotated", "the private keyholders", "Bearer Rovers 2-1",
                                  "a secret key — the press", "auth token -> gone"])
def test_the_widened_separators_leave_prose_alone(text):
    assert b.secret_offence(text) is None and not b.CREDENTIAL.search(text)


def test_a_written_file_keeps_write_bytes_mode(repo):
    """The exclusive create passes 0o666 (Path.write_bytes's mode), so the umask decides the mode as it did before."""
    old = b.os.umask(0o002)                       # a group-writable umask, where 0o644 and 0o666 differ
    try:
        assert b.run(closing_file=str(closing_file(repo, soccer_doc(), "SOCCER"))) == 0
    finally:
        b.os.umask(old)
    assert (_first_md(repo).stat().st_mode & 0o777) == 0o664


def test_a_team_named_bearer_and_a_key_match_reason_write_a_clean_pair(repo):
    doc = soccer_doc()
    doc["predictions"][0]["home_team"] = "Bearer Rovers"
    doc["predictions"][1]["desk"]["reason"] = "the key match: edge below the floor"
    assert b.run(closing_file=str(closing_file(repo, doc, "SOCCER"))) == 0
    assert receipts()[-1]["exit"] == 0 and len(receipts()[-1]["written"]) == 4


def test_no_fixture_family_refuses_under_the_credential_labels(repo):
    for fam, fn in (("SOCCER", soccer_doc), ("NFL", nfl_doc), ("MLB", mlb_doc)):
        assert b.run(closing_file=str(closing_file(repo, fn(), fam))) == 0, fam
    for p in files_under(repo / "exports" / "bulletins"):
        if p.suffix == ".md":
            assert not b.CREDENTIAL.search(pv.rendered(p.read_text())), p.name


# (P2, law 5) "the staging write: create `.<name>.tmp` with O_CREAT | O_EXCL | O_NOFOLLOW after unlinking a stale
# non-link temp, refuse when the temp path is a link, and judge the staging parent as the resolved path; a test with a
# planted link."

def _first_md(repo) -> Path:
    return repo / "exports" / "bulletins" / "SOCCER" / "2026-11-08" / "9401_beta-hawks_at_alpha-owls_closing.md"


@pytest.mark.parametrize("dangling", [False, True], ids=["to a file", "dangling"])
def test_a_planted_link_at_the_staging_temp_refuses_the_run_and_writes_nothing_through_it(repo, tmp_path, dangling):
    target = tmp_path / "elsewhere" / "target.txt"
    target.parent.mkdir()
    if not dangling:
        target.write_bytes(b"untouched")
    md = _first_md(repo)
    md.parent.mkdir(parents=True)
    link = md.with_name(f".{md.name}.tmp")
    link.symlink_to(target)
    assert b.run(closing_file=str(closing_file(repo, soccer_doc(), "SOCCER"))) == 2
    rec = receipts()[-1]
    assert rec["exit"] == 2 and rec["written"] == [] and "link" in rec["error"]
    assert link.is_symlink() and Path(b.os.readlink(link)) == target            # left as it is
    if dangling:
        assert not target.exists()                                            # nothing created through it
    else:
        assert target.read_bytes() == b"untouched"                            # nothing written through it
    left = [p for p in (repo / "exports" / "bulletins").rglob("*") if not p.is_symlink()]
    assert all(p.is_dir() for p in left), left                                # no file of the run, nothing staged


def test_a_stale_regular_temp_is_unlinked_then_created_exclusively(repo):
    md = _first_md(repo)
    md.parent.mkdir(parents=True)
    stale = md.with_name(f".{md.name}.tmp")
    stale.write_bytes(b"a stopped run's leftover")
    assert b.run(closing_file=str(closing_file(repo, soccer_doc(), "SOCCER"))) == 0
    assert md.exists() and b"leftover" not in md.read_bytes() and not stale.exists()


def test_a_staging_temp_that_is_a_directory_is_refused(repo):
    md = _first_md(repo)
    md.with_name(f".{md.name}.tmp").mkdir(parents=True)
    with pytest.raises(b.Refused):
        b.stage_file(md, b"x")
    assert not md.exists()


def test_the_staging_parent_is_judged_as_its_resolved_path(repo, tmp_path):
    """A parent that is a link into data/ is refused (Refused, never a bare SystemExit past run's receipt)."""
    inside = repo / "data" / "soc"
    inside.mkdir(parents=True)
    fam = repo / "exports" / "bulletins" / "SOCCER"
    fam.parent.mkdir(parents=True)
    fam.symlink_to(inside, target_is_directory=True)
    with pytest.raises(b.Refused):
        b.stage_file(fam / "2026-11-08" / "x.md", b"x")
    with pytest.raises(b.Refused):
        b.stage_file(fam / "x.md", b"x")
    assert list(inside.rglob("*")) == []


def test_write_file_takes_the_same_staging_path(repo, tmp_path):
    p = repo / "exports" / "bulletins" / "SOCCER" / "x.md"
    p.parent.mkdir(parents=True)
    target = tmp_path / "t.txt"
    target.write_bytes(b"untouched")
    p.with_name(".x.md.tmp").symlink_to(target)
    with pytest.raises(b.Refused):
        b.write_file(p, b"x")
    assert target.read_bytes() == b"untouched" and not p.exists()


# (P2) "THE MATHS exec line in ONE unit: `55c − 46c → +9.0pp` (the model's price as cents of the payout beside the
# cost in cents); a test."

def test_the_maths_exec_line_speaks_one_unit(repo):
    doc = soccer_doc()
    d = doc["predictions"][0]["desk"]
    d["model_p"] = 0.55
    d["exec"].update({"cost": 0.46, "edge_pp": 9.0})
    assert b.run(closing_file=str(closing_file(repo, doc, "SOCCER"))) == 0
    maths = md_of(repo, "SOCCER", 9401).split("## THE MATHS", 1)[1].split("\n## ", 1)[0]
    line = next(ln for ln in maths.splitlines() if ln.startswith("- exec edge"))
    assert line.startswith("- exec edge = model_p − cost = 55c − 46c → +9.00pp"), line
    assert "0.55" not in line
