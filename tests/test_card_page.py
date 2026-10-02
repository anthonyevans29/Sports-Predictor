"""Card page content (architect 2026-10-01, F2 slice 1) and the NCAA label
finding: every page line / digest row carries competition · away @ home ·
kickoff ET · model pick prob (tier) · reference (books, or Kalshi if
kalshi-only) · edge · the Desk call when the file carries desk · flags;
market-only rows say so; "model updated" / "call changed" deltas; digest
lists calls first; lines near 100 chars."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy" / "hosting"))
import sp_window_page as page  # noqa: E402


def row(mid, comp, home, away, utc, *, sport="nfl", model=None, fair=None, tier=None, edge=None, **kw):
    r = {"match_id": mid, "home_team": f"{home} FullName", "away_team": f"{away} FullName",
         "home_short": home, "away_short": away, "sport": sport, "competition": comp, "utc_date": utc,
         "status": "scheduled", "market": {"fair_prob": fair} if fair else None, "kalshi": None,
         "tier": tier, "quarantine": False, "venue_flag": None, "edge_pp": edge,
         "engine": "model_edge" if model else "market_only", "model": model}
    r.update(kw)
    return r


def model(pick, p, tier, desk=None, mv="v1"):
    return {"top_pick": pick, "top_pick_prob": p, "tier": tier, "model_version": mv, "desk": desk}


PIT = row(1, "NFL", "CLE", "PIT", "2026-10-02T00:15:00", tier="toss-up",
          model=model("AWAY", 0.567, "toss-up", {"call": "PASS", "units": 0, "pass_kind": "noref",
                                                  "reference": None, "market_ref": None, "edge_pp": None}))
ATL = row(2, "MLB", "ATL", "PHI", "2026-10-02T00:00:00", sport="mlb", tier="lean", edge=4.5,
          fair={"HOME": 0.494, "AWAY": 0.506},
          model=model("HOME", 0.539, "lean", {"call": "PLAY", "units": 0.5, "pass_kind": None,
                                               "reference": "books", "market_ref": 0.494, "edge_pp": 4.5}))
GER = row(3, "UNL", "GER", "SRB", "2026-10-01T18:45:00", sport="soccer", fair={"HOME": 0.79, "DRAW": 0.13, "AWAY": 0.08})


def snap(*rows):
    return page.snapshot({"fixtures": list(rows)})


def test_the_three_ruled_examples_verbatim():
    s = snap(PIT, ATL, GER)
    assert page.row_text(s["1"]) == "Thu 8:15p NFL PIT @ CLE · model PIT 56.7% (toss-up) · books — · PASS no-ref"
    assert page.row_text(s["2"]) == "Thu 8:00p MLB PHI @ ATL · model ATL 53.9% (lean) · books 49.4% · +4.5pp · PLAY 0.5u"
    assert page.row_text(s["3"]) == "Thu 2:45p UNL SRB @ GER · market-only · books GER 79%"
    assert all(len(page.row_text(g)) <= 100 for g in s.values())


def test_competition_not_family_ncaa_and_kalshi_only_and_no_desk():
    ncaa = row(4, "NCAA", "BAMA", "UGA", "2026-10-03T23:30:00", tier="lean", edge=2.0, fair={"HOME": 0.6, "AWAY": 0.4},
               model=model("HOME", 0.62, "lean"))                                  # no desk on the file
    ko = row(5, "MLB", "NYY", "BOS", "2026-10-02T23:05:00", sport="mlb", tier="lean",
             model=model("HOME", 0.65, "lean", {"call": "PLAY", "units": 0.5, "pass_kind": None,
                                                 "reference": "kalshi_only", "market_ref": 0.56, "edge_pp": 9.0}))
    s = snap(ncaa, ko)
    assert page.row_text(s["4"]).startswith("Sat 7:30p NCAA UGA @ BAMA · model BAMA 62.0% (lean) · books 60.0% · +2.0pp")
    assert "NFL" not in page.row_text(s["4"]) and "PLAY" not in page.row_text(s["4"])       # no desk → no call
    assert page.row_text(s["5"]).endswith("· kalshi 56.0% · +9.0pp · PLAY 0.5u")
    k = snap(row(6, "NHL", "BOS", "TOR", "2026-10-02T23:00:00", sport="nhl", kalshi_home_norm=0.42))
    assert page.row_text(k["6"]).endswith("market-only · kalshi TOR 58%")
    assert page.row_text(snap(row(7, "CL", "A", "B", "2026-10-02T19:00:00", sport="soccer"))["7"]).endswith("unpriced")


def test_flags_and_delta_lines_stay_short():
    flagged = dict(ATL, venue_flag="STALE-BOOK?", time_flag="time unconfirmed (api-sports only)")
    t = page.row_text(snap(flagged)["2"])
    assert t.endswith("· STALE-BOOK? · ⚠ time unconfirmed")
    d = page.line({"cls": "tier", "id": "2", "g": snap(ATL)["2"], "was": "toss-up"})
    first, second = d.split("\n")
    assert first == page.row_text(snap(ATL)["2"]) and second == "  ↳ tier toss-up -> lean"
    assert len(first) <= 100 and len(second) <= 100


def test_model_updated_and_call_changed_deltas_and_upgrade_is_silent():
    old = snap(ATL)
    legacy = {k: {x: v for x, v in g.items() if x not in ("prob", "call")} for k, g in old.items()}   # pre-upgrade state
    assert [d["cls"] for d in page.deltas(legacy, old, {}, {})] == []                          # no flood on upgrade
    new_m = dict(ATL, model=model("HOME", 0.561, "lean", ATL["model"]["desk"], mv="v2"))
    ds = page.deltas(old, snap(new_m), {}, {})
    assert [d["cls"] for d in ds] == ["model"]
    assert page.line(ds[0]).split("\n")[1] == "  ↳ model updated: ATL 53.9% -> ATL 56.1%"
    new_c = dict(ATL, model=model("HOME", 0.539, "lean", dict(ATL["model"]["desk"], call="PASS", units=0,
                                                               pass_kind="floor")))
    ds = page.deltas(old, snap(new_c), {}, {})
    assert [d["cls"] for d in ds] == ["call"]
    assert page.line(ds[0]).split("\n")[1] == "  ↳ call changed: PLAY 0.5u -> PASS floor"


def test_digest_lists_calls_first():
    s = snap(GER, PIT, ATL)
    lines = page.digest(s).split("\n")
    assert "1 Desk call(s)" in lines[0]
    assert lines[1].startswith("Thu 8:00p MLB PHI @ ATL") and "PLAY 0.5u" in lines[1]    # the call, first
    assert lines[2].startswith("Thu 2:45p UNL") and lines[3].startswith("Thu 8:15p NFL")   # then by kickoff


def test_window_card_carries_short_names_and_the_desk(tmp_path):
    from datetime import datetime, timedelta
    from sqlalchemy import select
    from src.db.database import init_db, session_scope
    from src.db.schema import Competition, Match, MatchStatus, Sport, Team
    from src.walters.window import build_card, short_name
    assert short_name(Team(name="Boston Red Sox")) == "Red Sox" and short_name(Team(name="Atlanta Braves")) == "Braves"
    assert short_name(Team(name="X", tla="ATL")) == "ATL"
    init_db()
    ko = datetime(2077, 10, 2, 0, 0)
    with session_scope() as s:
        comp = Competition(sport=Sport.NFL, code="NCAA", name="NCAA FBS", area="USA", type="LEAGUE")
        h, a = Team(sport=Sport.NFL, name="Alabama Crimson Tide", tla="BAMA"), Team(sport=Sport.NFL, name="Georgia Bulldogs")
        s.add_all([comp, h, a])
        s.flush()
        m = Match(sport=Sport.NFL, competition_id=comp.id, season="2077", utc_date=ko, status=MatchStatus.SCHEDULED,
                  home_team_id=h.id, away_team_id=a.id)
        s.add(m)
        s.flush()
        mid = m.id
    (tmp_path / "ncaa.json").write_text(json.dumps({"exported_at": "2077-10-01T12:00:00Z", "predictions": [
        {"match_id": mid, "prediction": {"home_win_prob": 0.62, "top_pick": "home_win", "tier": "lean"},
         "desk": {"engine": "model_edge", "call": "PLAY", "units": 1, "pass_kind": None, "reference": "books",
                  "market_ref": 0.55, "edge_pp": 7.0}}]}))
    card = build_card(now=ko - timedelta(hours=3), hours=24, export_dir=str(tmp_path))
    r = next(x for x in card["fixtures"] if x["match_id"] == mid)
    assert (r["competition"], r["home_short"], r["away_short"]) == ("NCAA", "BAMA", "Bulldogs")
    assert r["model"]["desk"] == {"call": "PLAY", "units": 1, "pass_kind": None, "reference": "books",
                                  "market_ref": 0.55, "edge_pp": 7.0}
    t = page.row_text(page.snapshot({"fixtures": [r]})[str(mid)])
    assert t == "Fri 8:00p NCAA Bulldogs @ BAMA · model BAMA 62.0% (lean) · books 55.0% · +7.0pp · PLAY 1u"
