"""#458 (ARCHITECT 2026-10-17 10:40 ET, addendum 112 item 10), verbatim: "#458 — the window page keys QB news by team
and player name, so two same-name injured QBs collapse. RULED: key by provider player id, name as display only; the
test uses two same-name players."

Covers: the window pager keys a QB by his provider id (two same-name quarterbacks on one team, different ids, are two
players and a status change in either pages); an item with no provider id is keyed by team and name as before,
labelled, and never one overwriting another; a change of key (the state written before this change, read after it)
is not news; the american-football adapter carries the entry's own `player.id`; sync-injuries stores it once
migrate_injury_player_source_id.py has run (unmapped, guarded Core SQL) and writes its rows without it before; the
window card carries it as `player_id`; the migration is additive, idempotent, receipted, and refuses with no
database file."""
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from click.testing import CliRunner
from sqlalchemy import create_engine, inspect, text

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "deploy" / "hosting"))
import sp_window_page as page  # noqa: E402

THU, SUN = "2026-10-02T00:15:00", "2026-10-05T17:00:00"


def row(mid, home, away, utc, qbs=()):
    """A card row; each QB is (name, status) or (name, status, provider id)."""
    return {"match_id": mid, "home_team": home, "away_team": away, "home_short": home, "away_short": away,
            "sport": "nfl", "competition": "NFL", "utc_date": utc, "status": "scheduled", "market": None,
            "kalshi": None, "tier": None, "quarantine": False, "venue_flag": None, "edge_pp": None,
            "engine": "market_only", "model": None,
            "qb_news": [{"team_id": 9, "team": "CHI", "player": q[0], "status": q[1],
                         "player_id": q[2] if len(q) > 2 else None} for q in qbs]}


def card(*rows):
    return page.snapshot({"fixtures": list(rows)})


def qb(prev, cur):
    return [d for d in page.deltas(prev, cur, {}, {}) if d["cls"] == "qb_news"]


def heads(ds):
    return [page.line(d).split("\n")[0] for d in ds]


def old_format(state):
    """The state as the pager wrote it before #458: every QB keyed `<team_id>|<name>`, {team, player, status}."""
    return {mid: {**g, "qbs": {f"9|{q['player']}": {"team": q["team"], "player": q["player"], "status": q["status"]}
                               for q in g["qbs"].values()}}
            for mid, g in state.items()}


# --------------------------------------------------- the pager: the ruled test ----

def test_two_same_name_quarterbacks_on_one_team_are_two_players_and_a_change_in_either_pages():
    """The ruled test: two same-name players. Before #458 both items shared the key `9|John Smith`: one status
    overwrote the other, and a change in the hidden one paged nothing."""
    both = [("John Smith", "Questionable", "2"), ("John Smith", "Out", "3")]
    prev = card(row(1, "CHI", "GB", THU, both), row(2, "DET", "CHI", SUN, both))
    assert set(prev["1"]["qbs"]) == {"id:2", "id:3"}                         # both appear
    assert {k: q["status"] for k, q in prev["1"]["qbs"].items()} == {"id:2": "Questionable", "id:3": "Out"}
    # the first one changes (the one the old key hid: the last item overwrote it)
    first = [("John Smith", "Out", "2"), ("John Smith", "Out", "3")]
    ds = qb(prev, card(row(1, "CHI", "GB", THU, first), row(2, "DET", "CHI", SUN, first)))
    assert [d["id"] for d in ds] == ["id:2"]
    assert heads(ds) == ["QB NEWS CHI John Smith: Questionable -> Out · 2 game(s)"]   # the name, display only
    # the second one changes
    second = [("John Smith", "Questionable", "2"), ("John Smith", "Questionable", "3")]
    ds = qb(prev, card(row(1, "CHI", "GB", THU, second), row(2, "DET", "CHI", SUN, second)))
    assert [d["id"] for d in ds] == ["id:3"] and heads(ds) == ["QB NEWS CHI John Smith: Out -> Questionable · 2 game(s)"]
    # one leaves the list: that one pages, the other does not
    gone = [("John Smith", "Out", "3")]
    ds = qb(prev, card(row(1, "CHI", "GB", THU, gone), row(2, "DET", "CHI", SUN, gone)))
    assert [(d["id"], d["was"], d["now"]) for d in ds] == [("id:2", "Questionable", None)]
    # nothing changed: silent
    assert qb(prev, card(row(1, "CHI", "GB", THU, both), row(2, "DET", "CHI", SUN, both))) == []


# --------------------------------------------------- rows with no provider id ----

def test_an_item_with_no_provider_id_is_keyed_by_team_and_name_and_labelled():
    prev = card(row(1, "CHI", "GB", THU, [("C. Williams", "Questionable")]))
    assert list(prev["1"]["qbs"]) == ["9|C. Williams"]                       # the key every item had before
    ds = qb(prev, card(row(1, "CHI", "GB", THU, [("C. Williams", "Out")])))
    assert heads(ds) == ["QB NEWS CHI C. Williams (no provider id): Questionable -> Out · 1 game(s)"]


def test_items_with_no_provider_id_that_share_a_name_are_never_one_overwriting_the_other():
    """Law 4: a row with no id is never silently merged. One entry holds every status, sorted, and counts them, so a
    change in any of them pages, labelled."""
    prev = card(row(1, "CHI", "GB", THU, [("John Smith", "Out"), ("John Smith", "Questionable")]))
    q = prev["1"]["qbs"]["9|John Smith"]
    assert (q["status"], q["n"]) == ("Out / Questionable", 2)
    ds = qb(prev, card(row(1, "CHI", "GB", THU, [("John Smith", "Out"), ("John Smith", "Out")])))
    assert heads(ds) == ["QB NEWS CHI John Smith (no provider id, 2 entries): Out / Questionable -> Out / Out · 1 game(s)"]
    assert qb(prev, card(row(1, "CHI", "GB", THU, [("John Smith", "Questionable"), ("John Smith", "Out")]))) == []


def test_a_deploy_before_the_migration_pages_nothing_new():
    """The card carries player_id null until the migration and the next sync: the keys are the old ones."""
    before = old_format(card(row(1, "CHI", "GB", THU, [("C. Williams", "Out")])))
    after = card(row(1, "CHI", "GB", THU, [("C. Williams", "Out")]))
    assert qb(before, after) == [] and page.qb_rekey(before, after) == {"carried": 0, "baseline": []}



def test_a_deploy_before_the_migration_holds_an_id_less_same_name_pair_as_a_baseline():
    """The state written before this change held ONE entry for two id-less same-name QBs (the last item's status).
    Read against the entry that now holds both, under the same key, it is a change of format, not news: a baseline
    when its one status is among theirs. A status that is among neither still pages; from the next run both sides
    hold the pair and a change in either one pages."""
    before = old_format(card(row(1, "CHI", "GB", THU, [("John Smith", "Out")])))
    for pair in ([("John Smith", "Out"), ("John Smith", "Questionable")], [("John Smith", "Out"), ("John Smith", "Out")]):
        now = card(row(1, "CHI", "GB", THU, pair))
        assert qb(before, now) == []
        assert page.qb_rekey(before, now) == {"carried": 0, "baseline": ["9|John Smith"]}
    was_q = old_format(card(row(1, "CHI", "GB", THU, [("John Smith", "Questionable")])))
    now = card(row(1, "CHI", "GB", THU, [("John Smith", "Out"), ("John Smith", "Out")]))
    assert heads(qb(was_q, now)) == ["QB NEWS CHI John Smith (no provider id, 2 entries): Questionable -> Out / Out "
                                     "· 1 game(s)"]
    later = card(row(1, "CHI", "GB", THU, [("John Smith", "Out"), ("John Smith", "Doubtful")]))
    assert heads(qb(now, later)) == ["QB NEWS CHI John Smith (no provider id, 2 entries): Out / Out -> Doubtful / Out "
                                     "· 1 game(s)"]


def test_a_player_whose_row_loses_its_provider_id_keeps_the_label():
    """Carried from his id key to a row with no id (the feed listed him without one), his page line still says so."""
    before = card(row(1, "CHI", "GB", THU, [("C. Williams", "Out", "1001")]))
    now = card(row(1, "CHI", "GB", THU, [("C. Williams", "Questionable")]))
    assert heads(qb(before, now)) == ["QB NEWS CHI C. Williams (no provider id): Out -> Questionable · 1 game(s)"]


# --------------------------------------------------- the change of key ----

def test_the_first_run_with_ids_carries_each_player_to_his_id_and_pages_only_real_changes():
    before = old_format(card(row(1, "CHI", "GB", THU, [("C. Williams", "Out"), ("J. Fields", "Questionable")]),
                             row(2, "DET", "CHI", SUN, [("C. Williams", "Out"), ("J. Fields", "Questionable")])))
    assert set(before["1"]["qbs"]) == {"9|C. Williams", "9|J. Fields"}
    same = [("C. Williams", "Out", "1001"), ("J. Fields", "Questionable", "1002")]
    now = card(row(1, "CHI", "GB", THU, same), row(2, "DET", "CHI", SUN, same))
    assert qb(before, now) == []                                              # a key change is not news
    assert page.qb_rekey(before, now) == {"carried": 2, "baseline": []}
    moved = [("C. Williams", "Questionable", "1001"), ("J. Fields", "Questionable", "1002")]
    ds = qb(before, card(row(1, "CHI", "GB", THU, moved), row(2, "DET", "CHI", SUN, moved)))
    assert [d["id"] for d in ds] == ["id:1001"]
    assert heads(ds) == ["QB NEWS CHI C. Williams: Out -> Questionable · 2 game(s)"]
    # the other way (an entry that had an id is listed without one) is a key change too
    assert qb(now, card(row(1, "CHI", "GB", THU, [("C. Williams", "Out"), ("J. Fields", "Questionable", "1002")]),
                        row(2, "DET", "CHI", SUN, [("C. Williams", "Out"), ("J. Fields", "Questionable", "1002")]))) == []


def test_the_collapsed_pair_is_a_baseline_at_the_key_change_then_each_pages_by_his_own_id():
    """The old state held ONE entry for two same-name quarterbacks: it cannot be told which was which, so that name
    makes no delta on the run the ids arrive (receipted as a baseline); from the next run each is his own id."""
    before = old_format(card(row(1, "CHI", "GB", THU, [("John Smith", "Out")])))
    pair = [("John Smith", "Questionable", "2"), ("John Smith", "Out", "3")]
    now = card(row(1, "CHI", "GB", THU, pair))
    assert qb(before, now) == []
    assert page.qb_rekey(before, now) == {"carried": 0, "baseline": ["9|John Smith"]}
    nxt = card(row(1, "CHI", "GB", THU, [("John Smith", "Out", "2"), ("John Smith", "Out", "3")]))
    assert [d["id"] for d in qb(now, nxt)] == ["id:2"]


def test_the_run_receipts_the_key_change_and_pages_nothing_for_it(tmp_path, monkeypatch):
    monkeypatch.setenv("SP_RECEIPTS", str(tmp_path / "receipts.jsonl"))
    monkeypatch.setenv("SP_WINDOW_STATE", str(tmp_path / "ws.json"))
    sent = []
    import sp_notify
    monkeypatch.setattr(sp_notify, "deliver", lambda kind, title, body, extra=None, topic_var="NTFY_TOPIC",
                        priority="high": sent.append(body) or True)
    when = datetime(2026, 10, 4, 15, 30, tzinfo=timezone.utc)                  # 11:30 ET, not quiet
    p = tmp_path / "card.json"

    def run(qbs):
        p.write_text(json.dumps({"fixtures": [row(1, "CHI", "GB", THU, qbs)], "t90_signatures": {}}))
        sent.clear()
        return page.run(p, now_utc=when)
    run([("C. Williams", "Out")])                                              # baseline (+ digest), no ids yet
    rec = run([("C. Williams", "Out", "1001")])                                # the first sync after the migration
    assert rec["deltas"]["qb_news"] == 0 and rec["qb_rekey"] == {"carried": 1, "baseline": []} and sent == []
    assert list(json.loads((tmp_path / "ws.json").read_text())["games"]["1"]["qbs"]) == ["id:1001"]
    rec = run([("C. Williams", "Questionable", "1001")])
    assert rec["deltas"]["qb_news"] == 1 and rec["qb_rekey"] == {"carried": 0, "baseline": []}
    assert sent and sent[0].startswith("QB NEWS CHI C. Williams: Out -> Questionable · 1 game(s)")


# --------------------------------------------------- ingest ----

ROSTER = [{"id": 2, "name": "John Smith", "position": "QB"}, {"id": 3, "name": "John Smith", "position": "QB"},
          {"id": 7, "name": "Dee Receiver", "position": "WR"}]


def _feed(status3="Out"):
    """An api-sports american-football /injuries answer (player = id/name/image; the adapter reads
    response[].player.id): two same-name quarterbacks with different ids, a receiver, an entry with no id."""
    return [{"player": {"id": 2, "name": "John Smith", "image": "x"}, "status": "Questionable", "description": "ankle"},
            {"player": {"id": 3, "name": "John Smith", "image": "x"}, "status": status3, "description": "knee"},
            {"player": {"id": 7, "name": "Dee Receiver", "image": "x"}, "status": "Out", "description": "hamstring"},
            {"player": {"name": "No Id Here"}, "status": "Out", "description": "illness"}]


class Feed:
    def __init__(self):
        self.injuries = {"QBI-0": _feed(), "QBI-1": []}

    def get(self, path, params=None):
        params = params or {}
        if path == "players" and "id" in params:
            return {"response": []}                       # the position lookup: answers nothing
        if path == "players":
            return {"response": ROSTER if params["team"] == "QBI-0" else []}
        return {"response": self.injuries.get(params["team"], [])}


def test_the_adapter_carries_each_entrys_own_provider_id(monkeypatch):
    from src.adapters.api_american_football import APIAmericanFootballAdapter
    ad = APIAmericanFootballAdapter()
    monkeypatch.setattr(ad, "_get", Feed().get)
    out = ad.list_injuries("QBI-0", "2026")
    assert [(r["player_name"], r["player_position"], r["player_source_id"]) for r in out] == [
        ("John Smith", "QB", "2"), ("John Smith", "QB", "3"), ("Dee Receiver", "WR", "7"), ("No Id Here", None, None)]


def _fixture(code):
    from src.db.database import init_db, session_scope
    from src.db.schema import Competition, CompetitionTeam, Match, MatchStatus, Sport, Team
    init_db()
    ko = datetime(2079, 10, 2, 0, 15)
    with session_scope() as s:
        comp = Competition(sport=Sport.NFL, code=code, name=code, area="USA", type="LEAGUE")
        s.add(comp)
        s.flush()
        ts = []
        for i, tla in enumerate(("CHI", "GB")):
            t = Team(sport=Sport.NFL, name=f"{code} {tla}", tla=tla, external_ids={"api_american_football": f"QBI-{i}"})
            s.add(t)
            s.flush()
            s.add(CompetitionTeam(competition_id=comp.id, team_id=t.id, season="2026"))
            ts.append(t.id)
        m = Match(sport=Sport.NFL, competition_id=comp.id, season="2026", status=MatchStatus.SCHEDULED, utc_date=ko,
                  home_team_id=ts[0], away_team_id=ts[1])
        s.add(m)
        s.flush()
        return comp.code, m.id, ts, ko


def _sync(monkeypatch, feed, code, mid):
    import cli
    from src.adapters.api_american_football import APIAmericanFootballAdapter
    ad = APIAmericanFootballAdapter()
    monkeypatch.setattr(ad, "_get", feed.get)
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda c: ad)
    r = CliRunner().invoke(cli.cli, ["sync-injuries", "--competition", code, "--season", "2026",
                                     "--match-ids", str(mid)])
    assert r.exit_code == 0, r.output


def _stored(team_id):
    from src.db.database import read_injury_player_ids, session_scope
    from src.db.schema import Injury
    with session_scope() as s:
        rows = list(s.query(Injury).filter(Injury.team_id == team_id).order_by(Injury.id))
        ids = read_injury_player_ids(s, [r.id for r in rows])
        return [(r.player_name, r.type, ids.get(r.id)) for r in rows]


def _card_row(tmp_path, code, ko):
    from src.walters.window import build_card
    c = build_card(now=ko - timedelta(hours=2), export_dir=str(tmp_path))
    return c, next(x for x in c["fixtures"] if x["competition"] == code)


def test_before_the_migration_the_sync_writes_its_rows_and_no_id(tmp_path, monkeypatch):
    """A pull or a deploy before migrate_injury_player_source_id.py keeps working: the rows are written, no id is
    stored, the card carries player_id null and nothing raises. (The throwaway DB may hold the column already, from
    a test that ran the migration: the existence check is what decides, so it is answered "absent" here.)"""
    from src.db import database
    monkeypatch.setattr(database, "has_injury_player_id", lambda: False)
    code, mid, (home, _), ko = _fixture("QBIPRE")
    _sync(monkeypatch, Feed(), code, mid)
    assert _stored(home) == [("John Smith", "Questionable", None), ("John Smith", "Out", None),
                             ("Dee Receiver", "Out", None), ("No Id Here", "Out", None)]
    _, r = _card_row(tmp_path, code, ko)
    assert [(q["player"], q["player_id"], q["status"]) for q in r["qb_news"]] == [
        ("John Smith", None, "Questionable"), ("John Smith", None, "Out")]


def test_the_orm_never_names_the_column(tmp_path):
    """The ORDER LINE convention: unmapped, so an injuries INSERT and SELECT work on a DB without the column."""
    from sqlalchemy.orm import Session

    from src.db.schema import Base, Injury
    assert "player_source_id" not in Injury.__table__.columns
    eng = create_engine(f"sqlite:///{tmp_path / 'pre.db'}")
    Base.metadata.create_all(eng)
    assert "player_source_id" not in {c["name"] for c in inspect(eng).get_columns("injuries")}
    with Session(eng) as s:
        s.add(Injury(team_id=1, player_name="John Smith", player_position="QB", type="Out"))
        s.commit()
        assert [i.player_name for i in s.query(Injury)] == ["John Smith"]
    eng.dispose()


def test_after_the_migration_the_sync_stores_the_id_and_the_card_and_the_page_key_by_it(tmp_path, monkeypatch):
    import migrate_injury_player_source_id as mig
    from src.db.database import has_injury_player_id, init_db
    init_db()
    assert mig.main() == 0 and has_injury_player_id()                        # the throwaway DB, migrated
    code, mid, (home, _), ko = _fixture("QBIPOST")
    feed = Feed()
    _sync(monkeypatch, feed, code, mid)
    assert _stored(home) == [("John Smith", "Questionable", "2"), ("John Smith", "Out", "3"),
                             ("Dee Receiver", "Out", "7"), ("No Id Here", "Out", None)]
    c0, r = _card_row(tmp_path, code, ko)
    assert [(q["player"], q["player_id"], q["status"]) for q in r["qb_news"]] == [
        ("John Smith", "2", "Questionable"), ("John Smith", "3", "Out")]
    prev = page.snapshot(c0)
    assert {k: q["status"] for k, q in prev[str(mid)]["qbs"].items()} == {"id:2": "Questionable", "id:3": "Out"}
    feed.injuries["QBI-0"] = _feed(status3="Questionable")                   # the second John Smith changes
    _sync(monkeypatch, feed, code, mid)
    c1, _ = _card_row(tmp_path, code, ko)
    ds = qb(prev, page.snapshot(c1))
    assert [d["id"] for d in ds] == ["id:3"]
    assert heads(ds) == ["QB NEWS CHI John Smith: Out -> Questionable · 1 game(s)"]


# --------------------------------------------------- the migration ----

def test_migration_is_additive_idempotent_and_receipts(tmp_path, monkeypatch, capsys):
    import migrate_injury_player_source_id as mig
    from src.db.schema import Base
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    Base.metadata.create_all(eng)                                  # the pre-migration schema (the column is unmapped)
    with eng.begin() as c:
        c.execute(text("INSERT INTO injuries (id, team_id, player_name, source, refreshed_at) VALUES "
                       "(1, 5, 'John Smith', 'api_american_football', '2026-10-17 12:00:00'), "
                       "(2, 6, 'Some Keeper', 'api_football', '2026-10-17 12:00:00')"))
    monkeypatch.setattr(mig, "get_engine", lambda: eng)
    assert mig.main() == 0
    out = capsys.readouterr().out
    assert "+ Adding injuries.player_source_id..." in out
    with eng.connect() as c:                                       # data kept, no backfill
        assert c.execute(text("SELECT id, player_name, player_source_id FROM injuries ORDER BY id")).all() == [
            (1, "John Smith", None), (2, "Some Keeper", None)]
    with eng.begin() as c:                                         # a sync after migrating fills it
        c.execute(text("UPDATE injuries SET player_source_id = '2' WHERE id = 1"))
    assert mig.main() == 0                                         # the second run: a schema no-op
    out = capsys.readouterr().out
    assert "· injuries.player_source_id already exists." in out and "+ Adding" not in out
    receipt = {ln.split()[0]: ln.split()[1:4] for ln in out.splitlines() if ln.startswith("  api_")}
    assert receipt == {"api_american_football": ["1", "1", "0"], "api_football": ["1", "0", "1"]}
    with eng.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM injuries")).scalar_one() == 2
    eng.dispose()


def test_migration_refuses_without_the_table(tmp_path, monkeypatch, capsys):
    import migrate_injury_player_source_id as mig
    eng = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    eng.connect().close()                                          # an existing DB without the table
    monkeypatch.setattr(mig, "get_engine", lambda: eng)
    assert mig.main() == 1
    assert "nothing to migrate" in capsys.readouterr().out


def test_migration_refuses_when_the_database_file_is_absent(tmp_path):
    """The shared guard (#524, addendum 112 item 1), as tests/test_migrate_guard.py runs every migration: its own
    process, DATABASE_URL on a missing file in a missing directory; exit 1, the ruled line, nothing created."""
    missing = tmp_path / "nowhere" / "sports.db"
    r = subprocess.run([sys.executable, str(REPO / "migrate_injury_player_source_id.py")], cwd=str(REPO),
                       env={**os.environ, "DATABASE_URL": f"sqlite:///{missing}"}, capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 1, r.stdout + r.stderr
    assert r.stdout == f"no database at {missing.resolve()}; a migration never creates one — law 5\n"
    assert list(tmp_path.iterdir()) == []
