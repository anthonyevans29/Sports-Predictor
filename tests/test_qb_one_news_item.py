"""#192 (ruling 2026-10-01): one injured QB is ONE news item. Half units stay
on every game his team plays (policy v1.1 unchanged); the pager emits ONE
page per player listing his games; the B-track shadow logs those games' QB
flags as a shared risk factor (no cap change)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy" / "hosting"))
import sp_window_page as page  # noqa: E402
from src.walters import desk_policy as dp  # noqa: E402


def row(mid, home, away, utc, qbs=()):
    return {"match_id": mid, "home_team": home, "away_team": away, "home_short": home, "away_short": away,
            "sport": "nfl", "competition": "NFL", "utc_date": utc, "status": "scheduled", "market": None,
            "kalshi": None, "tier": None, "quarantine": False, "venue_flag": None, "edge_pp": None,
            "engine": "market_only", "model": None,
            "qb_news": [{"team_id": 9, "team": "CHI", "player": n, "status": st} for n, st in qbs]}


THU, SUN, NEXT = "2026-10-02T00:15:00", "2026-10-05T17:00:00", "2026-10-09T00:15:00"


def card(*rows):
    return page.snapshot({"fixtures": list(rows)})


def test_one_page_per_player_across_his_games():
    prev = card(row(1, "CHI", "GB", THU, [("C. Williams", "Questionable")]),
                row(2, "DET", "CHI", SUN, [("C. Williams", "Questionable")]))
    cur = card(row(1, "CHI", "GB", THU, [("C. Williams", "Out")]),
               row(2, "DET", "CHI", SUN, [("C. Williams", "Out")]))
    ds = [d for d in page.deltas(prev, cur, {}, {}) if d["cls"] == "qb_news"]
    assert len(ds) == 1                                                    # ONE item, not two
    text = page.line(ds[0])
    assert text.startswith("QB NEWS CHI C. Williams: Questionable -> Out · 2 game(s)")
    assert text.count("\n  ↳ ") == 2 and "GB @ CHI" in text and "CHI @ DET" in text


def test_cleared_and_window_entry_and_upgrade():
    prev = card(row(1, "CHI", "GB", THU, [("C. Williams", "Out")]))
    cleared = page.deltas(prev, card(row(1, "CHI", "GB", THU)), {}, {})
    assert [page.line(d).split("\n")[0] for d in cleared if d["cls"] == "qb_news"] == [
        "QB NEWS CHI C. Williams: Out -> off the list · 1 game(s)"]
    # a game merely ENTERING the window with a listed QB is not news
    entered = page.deltas(card(row(1, "CHI", "GB", THU)),
                          card(row(1, "CHI", "GB", THU), row(3, "CHI", "MIN", NEXT, [("C. Williams", "Out")])), {}, {})
    assert not [d for d in entered if d["cls"] == "qb_news"]
    # upgrade: the previous state has no QB data -> silent
    legacy = {k: {x: v for x, v in g.items() if x != "qbs"} for k, g in prev.items()}
    assert not [d for d in page.deltas(legacy, card(row(1, "CHI", "GB", THU, [("C. Williams", "Questionable")])), {}, {})
                if d["cls"] == "qb_news"]


def _r(home, away, sport, qbs, utc):
    return {"home": home, "away": away, "sport": sport, "prob": 0.62, "mkt": 0.55, "pick": "HOME",
            "game": f"{away} @ {home}", "utc": utc, "qbs": list(qbs)}


def test_b_track_logs_the_shared_qb_risk_without_changing_anything():
    calls = [(_r("CHI", "GB", "NFL", ["C. Williams"], THU), {"call": "PLAY", "units": 0.5}),
             (_r("DET", "CHI", "NFL", ["C. Williams"], SUN), {"call": "PLAY", "units": 0.5}),
             (_r("NYY", "BOS", "MLB", [], THU), {"call": "PLAY", "units": 1}),
             (_r("MIN", "SEA", "NFL", ["S. Darnold"], SUN), {"call": "PASS", "units": 0})]
    sh = dp.b_track_shadow(calls)
    assert sh["qb_shared_risk"] == [{"player": "C. Williams",
                                     "games": [f"GB @ CHI|{THU}", f"CHI @ DET|{SUN}"],
                                     "straight_units": 1.0,
                                     "tickets_touching": sum(1 for t in dp.build_parlays(calls)
                                                             if any("CHI" in (l["home"], l["away"]) for l in t["legs"]))}]
    assert sh["applied"] is False and dp.B_TRACK["exposure_cap_units"] == 1.25          # no cap change


def test_window_card_rows_carry_qb_news(tmp_path):
    from datetime import datetime, timedelta
    from src.db.database import init_db, session_scope
    from src.db.schema import Competition, Injury, Match, MatchStatus, Sport, Team
    from src.walters.window import build_card
    init_db()
    ko = datetime(2078, 10, 2, 0, 15)
    with session_scope() as s:
        comp = Competition(sport=Sport.NFL, code="NFLQB", name="qb test", area="USA", type="LEAGUE")
        h, a = Team(sport=Sport.NFL, name="Chicago Bears", tla="CHI"), Team(sport=Sport.NFL, name="Green Bay Packers", tla="GB")
        s.add_all([comp, h, a])
        s.flush()
        s.add(Match(sport=Sport.NFL, competition_id=comp.id, season="2078", utc_date=ko, status=MatchStatus.SCHEDULED,
                    home_team_id=h.id, away_team_id=a.id))
        s.add(Injury(team_id=h.id, player_name="C. Williams", player_position="QB", type="Out"))
        s.add(Injury(team_id=h.id, player_name="D. Moore", player_position="WR", type="Out"))   # not a QB
        hid = h.id
    r = next(x for x in build_card(now=ko - timedelta(hours=2), export_dir=str(tmp_path))["fixtures"]
             if x["competition"] == "NFLQB")
    assert r["qb_news"] == [{"team_id": hid, "team": "CHI", "player": "C. Williams", "status": "Out"}]
