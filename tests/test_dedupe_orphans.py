"""ARCHITECT 2026-10-03: `dedupe-matches --orphans` — each stale/twinned SCHEDULED row's id resolved at the
provider: NOT FOUND + a live twin within 48h -> merge (whichever row is older keeps the references);
NOT FOUND + no twin -> relink to the provider's live id for the pair, else STALE_ORPHAN (never deleted);
lookup errors UNRESOLVED (never read as absent); swapped pairs refused. Dry-run writes nothing; the
apply summary reports state (re-keyed rows, provenance) — the "merged 0" reporting fix. The fixtures
export drops STALE_ORPHAN rows (counted)."""
import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from src.adapters.normalized import NormalizedMatch
from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Odds, Sport, Team
from src.ingestion import match_dedupe as md
from src.timeutil import utc_now_naive

SRC = "api_american_football"
CODE = "OR1"
NOW = utc_now_naive().replace(microsecond=0)


@pytest.fixture(autouse=True, scope="module")
def _cleanup():
    yield
    with session_scope() as s:
        cids = [c.id for c in s.execute(select(Competition).where(Competition.code.in_((CODE, "OR2")))).scalars()]
        mids = [m.id for m in s.execute(select(Match).where(Match.competition_id.in_(cids))).scalars()]
        s.query(Odds).filter(Odds.match_id.in_(mids)).delete(synchronize_session=False)
        s.query(Match).filter(Match.id.in_(mids)).delete(synchronize_session=False)


def _nm(h, a, sid, when, status=MatchStatus.SCHEDULED):
    return NormalizedMatch(sport=Sport.NFL, competition_code=CODE, season="2026", utc_date=when, status=status,
                           home_team_source_id=f"{CODE}t{h}", away_team_source_id=f"{CODE}t{a}", source=SRC,
                           source_id=sid, status_raw="NS")


class FakeProvider:
    def __init__(self, games, broken=()):
        self.games, self.broken, self.calls = games, set(broken), []

    def get_game(self, sid, code):
        self.calls.append(("id", sid))
        if sid in self.broken:
            raise RuntimeError("HTTP 500")
        hit = [g for g in self.games if g.source_id == sid]
        return (True, hit[0]) if hit else (False, None)

    def list_matches(self, code, season=None, date_from=None, date_to=None):
        self.calls.append(("date", date_from))
        return [g for g in self.games if g.utc_date.strftime("%Y-%m-%d") == date_from]


def _world():
    init_db()
    with session_scope() as s:
        c = Competition(sport=Sport.NFL, code=CODE, name=CODE, area="US", type="LEAGUE")
        ts = [Team(sport=Sport.NFL, name=f"{CODE} T{i}", external_ids={SRC: f"{CODE}t{i}"}) for i in range(16)]
        s.add(c)
        s.add_all(ts)
        s.flush()
        cid, t = c.id, [x.id for x in ts]
        ids = {}

        def m(key, h, a, sid, when):
            row = Match(sport=Sport.NFL, competition_id=cid, season="2026", utc_date=when,
                        status=MatchStatus.SCHEDULED, home_team_id=t[h], away_team_id=t[a], external_ids={SRC: sid})
            s.add(row)
            s.flush()
            ids[key] = row.id

        past = NOW - timedelta(days=1)
        m("relink", 1, 0, "22194", past)                         # Georgia@Alabama: retired id, no twin in DB
        m("twin_old", 3, 2, "22100", NOW + timedelta(days=2))    # stale id is the OLDER row; twin +30h
        m("twin_new", 3, 2, "23100", NOW + timedelta(days=2, hours=30))
        m("live_old", 5, 4, "23200", NOW + timedelta(days=3))    # live id is the OLDER row; stale twin newer
        m("stale_new", 5, 4, "22200", NOW + timedelta(days=3, hours=-20))
        m("orphan", 7, 6, "22300", past)                         # retired, no twin, provider has nothing
        m("broken", 9, 8, "22400", past)                         # lookup error -> unresolved
        m("resync", 11, 10, "23500", past)                       # live id, result not yet synced
        m("swapped", 13, 12, "22600", past)                      # provider holds the pair swapped
        for key in ("twin_new", "stale_new"):
            s.add(Odds(match_id=ids[key], bookmaker="b", market="ML", selection="HOME", price_decimal=1.8))
    games = [_nm(1, 0, "23194", past + timedelta(hours=3)),
             _nm(3, 2, "23100", NOW + timedelta(days=2, hours=30)),
             _nm(5, 4, "23200", NOW + timedelta(days=3)),
             _nm(11, 10, "23500", past),
             _nm(12, 13, "23600", past)]                          # the swapped pair
    return cid, ids, FakeProvider(games, broken={"22400"})


def _row(mid):
    with session_scope() as s:
        m = s.get(Match, mid)
        return None if m is None else {"status": m.status, "ext": dict(m.external_ids or {}), "utc": m.utc_date}


def test_orphans_dry_run_plans_every_case_and_writes_nothing():
    ids, prov = IDS, PROV
    r = md.orphans(CODE, prov, now=NOW)
    act = {p["id"]: p["action"] for p in r["plan"]}
    assert act[ids["relink"]] == "relink" and act[ids["orphan"]] == "orphan"
    assert act[ids["twin_old"]] == "merge" and ids["twin_new"] not in act          # handled as the twin
    assert act[ids["stale_new"]] == "merge" and act[ids["live_old"]] == "live"
    assert act[ids["broken"]] == "unresolved" and act[ids["resync"]] == "live_resync"
    assert act[ids["swapped"]] == "refused"
    rl = next(p for p in r["plan"] if p["id"] == ids["relink"])
    assert rl["live_sid"] == "23194"
    assert r["applied_counts"] == {} and r["after"] == r["before"]
    assert _row(ids["orphan"])["status"] == MatchStatus.SCHEDULED and _row(ids["twin_new"]) is not None
    assert _row(ids["relink"])["ext"] == {SRC: "22194"}


def test_orphans_apply_merges_relinks_marks_and_never_deletes_an_orphan():
    r = md.orphans(CODE, PROV, apply=True, now=NOW)
    assert r["applied_counts"] == {"merge": 2, "relink": 1, "orphan": 1}, r
    rl = _row(IDS["relink"])                                      # Georgia@Alabama -> its live id
    assert rl["ext"][SRC] == "23194" and rl["ext"][f"{SRC}_prev"] == ["22194"]
    assert rl["ext"][f"{SRC}_rekeys"][0]["via"] == "orphan-relink"
    assert rl["utc"] == (NOW - timedelta(days=1) + timedelta(hours=3))
    keep = _row(IDS["twin_old"])                                  # stale was the older row: takes the live id
    assert keep["ext"][SRC] == "23100" and "22100" in keep["ext"][f"{SRC}_prev"]
    assert _row(IDS["twin_new"]) is None
    live = _row(IDS["live_old"])                                  # stale was the newer row: live keeps its own
    assert live["ext"][SRC] == "23200" and "22200" in live["ext"][f"{SRC}_prev"]
    assert live["utc"] == NOW + timedelta(days=3) and _row(IDS["stale_new"]) is None
    with session_scope() as s:                                    # odds re-pointed, never deleted
        assert s.execute(select(func.count()).select_from(Odds).where(
            Odds.match_id.in_([IDS["twin_old"], IDS["live_old"]]))).scalar() == 2
    orph = _row(IDS["orphan"])
    assert orph["status"] == MatchStatus.STALE_ORPHAN and f"{SRC}_orphaned_at" in orph["ext"]
    for k in ("broken", "resync", "swapped"):
        assert _row(IDS[k])["status"] == MatchStatus.SCHEDULED
    b, a = r["before"], r["after"]
    assert a["rows"] == b["rows"] - 2 and a["stale_orphans"] == 1 and a["carry_prev"] == b["carry_prev"] + 3
    assert a["rekeys_by_via"] == {"orphan-relink": 1, "orphan-merge": 1}


def test_apply_summary_reports_state_when_nothing_is_left_to_merge(capsys):
    from cli import _dedupe_state_lines
    r = md.run(CODE, apply=False)
    assert r["pairs"] == 0 and r["before"]["carry_prev"] >= 3
    _dedupe_state_lines(r, SRC)
    out = capsys.readouterr().out
    assert "re-keyed in place (carry api_american_football_prev)" in out
    assert "nothing to merge" in out and "already carry api_american_football_prev" in out


def test_fixtures_export_drops_stale_orphans(tmp_path):
    from src.walters.export import export_fixtures
    rc = {}
    doc = json.loads(open(export_fixtures(CODE, out_dir=str(tmp_path), receipts=rc,
                                          start=(NOW - timedelta(days=2)).strftime("%Y-%m-%d"),
                                          end=(NOW + timedelta(days=5)).strftime("%Y-%m-%d"))).read())
    assert IDS["orphan"] not in [f["match_id"] for f in doc["fixtures"]]
    assert rc["stale_orphans_excluded"] == 1


IDS: dict = {}
PROV = None


@pytest.fixture(autouse=True, scope="module")
def _shared():
    global PROV
    _, ids, prov = _world_once()
    IDS.update(ids)
    PROV = prov
    yield


_ONCE: dict = {}


def _world_once():
    if not _ONCE:
        _ONCE["w"] = _world()
    return _ONCE["w"]


def test_cli_orphans_dry_run_prints_the_receipt(monkeypatch):
    from click.testing import CliRunner

    import src.adapters.api_american_football as aaf
    from cli import cli
    monkeypatch.setattr(aaf, "APIAmericanFootballAdapter", lambda: PROV)
    monkeypatch.setenv("SP_ODDS_FOOTBALL_RPM", "600000")
    res = CliRunner().invoke(cli, ["dedupe-matches", "--competition", CODE, "--orphans"])
    assert res.exit_code == 0, res.output
    out = res.output
    assert "DEDUPE-MATCHES --orphans OR1" in out and "DRY-RUN (nothing written)" in out
    assert "plan: merge" in out and "[unresolved] id" in out and "[refused] id" in out
    assert "state before: rows" in out


def test_two_stale_rows_never_claim_one_live_id_or_one_twin():
    """Two retired rows of one pair 3 days apart (±2d search windows overlap) never both relink to the
    one live game; the second is refused."""
    init_db()
    with session_scope() as s:
        c = Competition(sport=Sport.NFL, code="OR3", name="OR3", area="US", type="LEAGUE")
        ts = [Team(sport=Sport.NFL, name=f"OR3 T{i}", external_ids={SRC: f"OR3t{i}"}) for i in range(2)]
        s.add(c)
        s.add_all(ts)
        s.flush()
        for sid, d in (("1", 5), ("2", 3)):
            s.add(Match(sport=Sport.NFL, competition_id=c.id, season="2026", utc_date=NOW - timedelta(days=d),
                        status=MatchStatus.SCHEDULED, home_team_id=ts[1].id, away_team_id=ts[0].id,
                        external_ids={SRC: sid}))
    live = NormalizedMatch(sport=Sport.NFL, competition_code="OR3", season="2026", utc_date=NOW - timedelta(days=4),
                           status=MatchStatus.FINISHED, home_team_source_id="OR3t1", away_team_source_id="OR3t0",
                           source=SRC, source_id="9", status_raw="FT")
    r = md.orphans("OR3", FakeProvider([live]), now=NOW)
    acts = sorted(p["action"] for p in r["plan"])
    assert acts == ["refused", "relink"], r["plan"]
    assert "already taken by another relink" in next(p for p in r["plan"] if p["action"] == "refused")["why"]
    with session_scope() as s:
        cid = s.execute(select(Competition.id).where(Competition.code == "OR3")).scalar()
        s.query(Match).filter(Match.competition_id == cid).delete(synchronize_session=False)
