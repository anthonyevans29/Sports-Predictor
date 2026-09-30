"""LINE-MOVE ALARM (architect ruling 2026-09-29, after the MNF QB audit:
the injury feed lagged, the market did not). From stored snapshots only, a
move of >= 6pp on book or Kalshi inside T-3h marks the row "late-news?" in
the window card and the NFL export, pages on the card topic, and requests
freshen:<family>."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS

from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, OddsSnapshot, Prediction, Sport, Team
from src.walters.line_move import LATE_NEWS_FLAG, describe, line_move

KO = datetime(2026, 10, 4, 17, 0)


def snap(sel, p, at, source="api_american_football", market="1X2"):
    return NS(selection=sel, devig_prob=p, captured_at=at, source=source, market=market)


def book(home, at):
    return [snap("HOME", home, at), snap("AWAY", 1 - home, at)]


def test_book_move_inside_t3h_flags_late_news():
    snaps = (book(0.489, KO - timedelta(hours=5)) + book(0.49, KO - timedelta(hours=3, minutes=5))
             + book(0.56, KO - timedelta(minutes=50)))
    lm = line_move(snaps, KO, KO - timedelta(minutes=30))
    b = lm["venues"]["book"]
    assert lm["flag"] == LATE_NEWS_FLAG and b["alarm"] and b["move_pp"] == 7.0      # ref = last at/before T-3h
    assert b["from_at"] == (KO - timedelta(hours=3, minutes=5)).isoformat()
    assert describe(lm) == "book 0.490→0.560 (+7.0pp)"


def test_kalshi_sides_captured_separately_and_threshold_edges():
    t0, t1 = KO - timedelta(hours=2, minutes=30), KO - timedelta(minutes=40)
    k = [snap("HOME", 0.40, t0, "kalshi", "ML"), snap("AWAY", 0.58, t0 + timedelta(seconds=5), "kalshi", "ML"),
         snap("HOME", 0.33, t1, "kalshi", "ML"), snap("AWAY", 0.66, t1, "kalshi", "ML")]
    lm = line_move(k, KO, KO - timedelta(minutes=20))
    kv = lm["venues"]["kalshi"]
    # no Kalshi capture by T-3h -> reference = first two-sided point inside it (0.40/0.98)
    assert kv["from"] == round(0.40 / 0.98, 4) and kv["move_pp"] == -7.5 and lm["flag"] == LATE_NEWS_FLAG
    # a 5.9pp book move is not an alarm
    lm = line_move(book(0.50, KO - timedelta(hours=4)) + book(0.559, KO - timedelta(hours=1)), KO,
                   KO - timedelta(minutes=10))
    assert lm["flag"] is None and lm["venues"]["book"]["move_pp"] == 5.9
    # exactly 6.0pp is an alarm (>=)
    lm = line_move(book(0.50, KO - timedelta(hours=4)) + book(0.56, KO - timedelta(hours=1)), KO,
                   KO - timedelta(minutes=10))
    assert lm["flag"] == LATE_NEWS_FLAG


def test_outside_window_inplay_and_single_point():
    snaps = book(0.40, KO - timedelta(hours=4)) + book(0.60, KO + timedelta(minutes=5))    # in-play never counts
    assert line_move(snaps, KO, KO - timedelta(hours=4)) is None                 # before T-3h: not evaluated
    assert line_move(snaps, KO, KO + timedelta(minutes=1)) is None               # after kickoff: not evaluated
    lm = line_move(snaps, KO, KO - timedelta(minutes=5))
    assert lm["venues"] == {} and lm["flag"] is None                             # one pre-KO point: no move
    # Kalshi rows never leak into the book series and vice versa
    mixed = book(0.50, KO - timedelta(hours=4)) + [snap("HOME", 0.90, KO - timedelta(hours=1), "kalshi", "ML")]
    lm = line_move(mixed, KO, KO - timedelta(minutes=5))
    assert lm["venues"] == {}


def _nfl_game(s, tag, kickoff):
    comp = s.execute(select(Competition).where(Competition.sport == Sport.NFL,
                                               Competition.code == "NFL")).scalars().first()
    if comp is None:
        comp = Competition(sport=Sport.NFL, code="NFL", name="NFL", area="USA", type="LEAGUE")
        s.add(comp)
        s.flush()
    h = Team(sport=Sport.NFL, name=f"LM {tag} Home", external_ids={"lm": f"{tag}h"})
    a = Team(sport=Sport.NFL, name=f"LM {tag} Away", external_ids={"lm": f"{tag}a"})
    s.add_all([h, a])
    s.flush()
    m = Match(sport=Sport.NFL, competition_id=comp.id, season="2026", utc_date=kickoff,
              status=MatchStatus.SCHEDULED, home_team_id=h.id, away_team_id=a.id,
              external_ids={"lm": tag})
    s.add(m)
    s.flush()
    return m


def test_window_card_and_nfl_export_carry_the_flag(tmp_path):
    from src.walters.nfl_predict import export_nfl_predictions
    from src.walters.window import build_card
    init_db()
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    ko = now + timedelta(hours=2)
    with session_scope() as s:
        moved = _nfl_game(s, "moved", ko)
        calm = _nfl_game(s, "calm", ko)
        for m, late in ((moved, 0.58), (calm, 0.52)):
            s.add(Prediction(match_id=m.id, model_version="t", home_win_prob=0.5, away_win_prob=0.5))
            for sel, p in (("HOME", 0.50), ("AWAY", 0.50)):
                s.add(OddsSnapshot(match_id=m.id, market="1X2", selection=sel, devig_prob=p, n_books=5,
                                   captured_at=ko - timedelta(hours=4), source="api_american_football"))
            for sel, p in (("HOME", late), ("AWAY", 1 - late)):
                s.add(OddsSnapshot(match_id=m.id, market="1X2", selection=sel, devig_prob=p, n_books=5,
                                   captured_at=now - timedelta(minutes=5), source="api_american_football"))
        ids = {moved.id: "moved", calm.id: "calm"}
    card = build_card(now=now, hours=24, export_dir=str(tmp_path))
    rows = {ids[r["match_id"]]: r for r in card["fixtures"] if r["match_id"] in ids}
    assert rows["moved"]["late_news_flag"] == LATE_NEWS_FLAG
    assert rows["moved"]["line_move"]["venues"]["book"]["move_pp"] == 8.0
    assert rows["calm"]["late_news_flag"] is None and rows["calm"]["line_move"]["venues"]["book"]["move_pp"] == 2.0
    assert card["receipts"]["late_news"] >= 1
    path = export_nfl_predictions(out_dir=str(tmp_path), hours_ahead=36)
    ex = {r["match_id"]: r for r in json.load(open(path))["predictions"]}
    assert ex[[k for k, v in ids.items() if v == "moved"][0]]["late_news_flag"] == LATE_NEWS_FLAG
    assert ex[[k for k, v in ids.items() if v == "calm"][0]]["late_news_flag"] is None


# ---------------------------------------------------- pager + freshen ----

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy" / "hosting"))
import sp_window_page  # noqa: E402


def _card(flag, move=None):
    lm = ({"flag": flag, "venues": {"book": {"from": 0.49, "to": 0.56, "move_pp": 7.0, "alarm": True}}}
          if flag else None)
    return {"fixtures": [{"match_id": 7, "home_team": "Chicago Bears", "away_team": "Philadelphia Eagles",
                          "sport": "nfl", "competition": "NFL", "utc_date": "2026-10-04T17:00:00",
                          "status": "scheduled", "market": {"fair_prob": {"HOME": 0.56}}, "kalshi": None,
                          "tier": "lean", "quarantine": False, "venue_flag": None, "edge_pp": 1.0,
                          "engine": "model_edge", "late_news_flag": flag, "line_move": lm}],
            "t90_signatures": {}}


def test_pager_pages_line_move_once_and_requests_freshen(tmp_path, monkeypatch):
    monkeypatch.setenv("SP_RECEIPTS", str(tmp_path / "receipts.jsonl"))
    monkeypatch.setenv("SP_WINDOW_STATE", str(tmp_path / "ws.json"))
    sent = []
    import sp_notify
    monkeypatch.setattr(sp_notify, "deliver", lambda kind, title, body, extra=None, topic_var="NTFY_TOPIC",
                        priority="high": sent.append((topic_var, body)) or True)
    when = datetime(2026, 10, 4, 15, 30, tzinfo=timezone.utc)                  # 11:30 ET, not quiet
    p = tmp_path / "card.json"

    def page(card):
        p.write_text(json.dumps(card))
        sent.clear()
        return sp_window_page.run(p, now_utc=when)
    page(_card(None))                                                          # baseline (+ digest)
    rec = page(_card(LATE_NEWS_FLAG))
    assert rec["deltas"]["line_move"] == 1
    assert rec["freshen_needed"] == [{"id": "7", "sport": "nfl", "competition": "NFL", "reason": "line_move"}]
    assert [t for t, _ in sent] == ["NTFY_CARD_TOPIC"]
    assert "LINE MOVE inside T-3h: book 0.490->0.560 (+7.0pp): late-news? freshen triggered" in sent[0][1]
    rec = page(_card(LATE_NEWS_FLAG))                                          # still flagged: no repeat
    assert rec["deltas"]["line_move"] == 0 and rec["freshen_needed"] == [] and sent == []


def test_freshen_receipt_names_the_reason(tmp_path, monkeypatch):
    import sp_common as c
    import sp_run
    monkeypatch.setenv("SP_RECEIPTS", str(tmp_path / "receipts.jsonl"))
    monkeypatch.setenv("SP_LOCK", str(tmp_path / "db.lock"))
    monkeypatch.setattr(sp_run, "run_steps", lambda *a, **k: (0, 5))
    out = sp_run.run_freshens([{"id": "7", "sport": "nfl", "competition": "NFL", "reason": "line_move"},
                               {"id": "8", "sport": "nfl", "competition": "NFL"}],
                              "win-1", datetime(2026, 10, 4, 15, 30), datetime(2026, 10, 4).date())
    assert out[0]["chain"] == "freshen:NFL" and out[0]["ran"]
    assert out[0]["reasons"] == ["line_move", "t90_news"] and out[0]["games"] == ["7", "8"]


def test_t90_signature_tracks_injury_content_not_refresh_time():
    """Ruling 2026-09-29 on #65: the imminent tier re-syncs injuries every run
    (wipe + re-insert); the signature must change only when the CONTENT does."""
    from src.db.schema import Injury
    from src.walters.window import t90_signatures
    init_db()
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    with session_scope() as s:
        m = _nfl_game(s, "sig", now + timedelta(minutes=60))
        mid, tid = m.id, m.home_team_id
        s.add(Injury(team_id=tid, player_name="Caleb Williams", player_position="QB", type="Questionable",
                     refreshed_at=now - timedelta(hours=2)))
    sig0 = t90_signatures([mid], now=now)[str(mid)]
    with session_scope() as s:                                              # same content, new refresh
        s.query(Injury).filter(Injury.team_id == tid).delete()
        s.add(Injury(team_id=tid, player_name="Caleb Williams", player_position="QB", type="Questionable",
                     refreshed_at=now))
    assert t90_signatures([mid], now=now)[str(mid)] == sig0
    with session_scope() as s:                                              # news: status changes
        s.query(Injury).filter(Injury.team_id == tid).update({"type": "Out"})
    assert t90_signatures([mid], now=now)[str(mid)] != sig0


def test_mlb_and_soccer_prediction_exports_carry_the_flag():
    from src.walters.export import _collect_rows
    init_db()
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    ko = now + timedelta(hours=2)
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == "LMSOC")).scalars().first()
        if comp is None:
            comp = Competition(sport=Sport.SOCCER, code="LMSOC", name="LMSOC", area="X", type="LEAGUE")
            s.add(comp)
            s.flush()
        h = Team(sport=Sport.SOCCER, name="LM Soc Home", external_ids={"lm": "sh"})
        a = Team(sport=Sport.SOCCER, name="LM Soc Away", external_ids={"lm": "sa"})
        s.add_all([h, a])
        s.flush()
        m = Match(sport=Sport.SOCCER, competition_id=comp.id, season="2026/27", utc_date=ko,
                  status=MatchStatus.SCHEDULED, home_team_id=h.id, away_team_id=a.id, external_ids={"lm": "soc"})
        s.add(m)
        s.flush()
        # soccer = a 1X2 set: the move is P(home) over HOME+DRAW+AWAY (#117, 2026-09-30)
        for t, home in ((ko - timedelta(hours=4), 0.40), (now - timedelta(minutes=5), 0.47)):
            for sel, p in (("HOME", home), ("DRAW", 0.25), ("AWAY", 0.75 - home)):
                s.add(OddsSnapshot(match_id=m.id, market="ML", selection=sel, devig_prob=p,
                                   captured_at=t, source="kalshi"))
        mid = m.id
        # the same moves WITHOUT the TIE leg: incomplete -> no Kalshi series, no flag
        m2 = Match(sport=Sport.SOCCER, competition_id=comp.id, season="2026/27", utc_date=ko,
                   status=MatchStatus.SCHEDULED, home_team_id=h.id, away_team_id=a.id,
                   external_ids={"lm": "soc-notie"})
        s.add(m2)
        s.flush()
        for t, home in ((ko - timedelta(hours=4), 0.40), (now - timedelta(minutes=5), 0.47)):
            for sel, p in (("HOME", home), ("AWAY", 0.75 - home)):
                s.add(OddsSnapshot(match_id=m2.id, market="ML", selection=sel, devig_prob=p,
                                   captured_at=t, source="kalshi"))
        mid2 = m2.id
    rows = _collect_rows(sport=Sport.SOCCER, start_date=now, end_date=now + timedelta(hours=6),
                         competition_code="LMSOC", statuses=None)
    row = next(r for r in rows if r["match_id"] == mid)
    assert row["late_news_flag"] == LATE_NEWS_FLAG and row["line_move"]["venues"]["kalshi"]["move_pp"] == 7.0
    row2 = next(r for r in rows if r["match_id"] == mid2)
    assert row2["late_news_flag"] is None and "kalshi" not in row2["line_move"]["venues"]
    # the pre-#117 read of that pair, H/(H+A): 0.40/0.75 -> 0.47/0.75, a +9.3pp "move" that was not real


def test_sync_injuries_kickoff_scope_calls_only_imminent_teams(monkeypatch):
    import cli as cli_mod
    from click.testing import CliRunner
    init_db()
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    with session_scope() as s:
        soon = _nfl_game(s, "scope1", now + timedelta(minutes=80))
        later = _nfl_game(s, "scope2", now + timedelta(hours=5))
        want = {soon.home_team_id, soon.away_team_id}
        other = {later.home_team_id, later.away_team_id}
    calls = []
    monkeypatch.setattr(cli_mod, "_adapter_for_competition", lambda code: NS(source_name="fake"))
    monkeypatch.setattr(cli_mod.IngestionService, "sync_injuries_for_teams",
                        lambda self, ids, season: calls.append(set(ids)) or "ok")
    monkeypatch.setattr(cli_mod.IngestionService, "sync_injuries",
                        lambda self, *a, **k: calls.append("FULL") or "ok")
    r = CliRunner().invoke(cli_mod.cli, ["sync-injuries", "--competition", "NFL", "--season", "2026",
                                         "--kickoff-within-hours", "2"])
    assert r.exit_code == 0, r.output
    assert len(calls) == 1 and want <= calls[0] and not (other & calls[0])     # scoped, never the full sweep
    assert "kicking off within 2h" in r.output
    calls.clear()
    r = CliRunner().invoke(cli_mod.cli, ["sync-injuries", "--competition", "NFL", "--season", "2026",
                                         "--kickoff-within-hours", "0.01"])
    assert r.exit_code == 0 and calls == [] and "no provider call" in r.output
