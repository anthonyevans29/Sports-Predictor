"""#176 NCAA source probe (read-only, row-level): discovery of the source's
field names (law 1; refusal when one is missing), the shared-matcher join in
both orientations, score comparison in OUR orientation, neutral games kept
separate, the key never printed, nothing written. Synthetic CFBD-shaped
records; the API is never reached."""
import json
import os
import sys
from datetime import datetime

from sqlalchemy import func, select

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import ncaa_source_probe as nsp  # noqa: E402
from src.db.database import init_db, session_scope  # noqa: E402
from src.db.schema import Competition, Match, MatchStatus, Sport, Team  # noqa: E402


def rec(home, away, hp, ap, start, neutral=False, hc="fbs", ac="fbs", **kw):
    return {"id": hash((home, away)) % 10**6, "season": 2077, "seasonType": "regular", "startDate": start,
            "completed": True, "neutralSite": neutral, "homeTeam": home, "homeClassification": hc,
            "homePoints": hp, "awayTeam": away, "awayClassification": ac, "awayPoints": ap, **kw}


def world():
    init_db()
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == "NCAA")).scalars().first()
        if comp is None:
            comp = Competition(sport=Sport.NFL, code="NCAA", name="NCAA", area="USA", type="LEAGUE")
            s.add(comp)
            s.flush()
        t = {}
        for n in ("Probe Aardvarks", "Probe Badgers", "Probe Condors", "Probe Dingos", "Probe Eagles", "Probe Foxes"):
            t[n] = Team(sport=Sport.NFL, name=n)
            s.add(t[n])
        s.flush()
        mk = lambda h, a, d, hs, as_: s.add(Match(sport=Sport.NFL, competition_id=comp.id, season="2077",
                                                  utc_date=d, status=MatchStatus.FINISHED, home_team_id=t[h].id,
                                                  away_team_id=t[a].id, home_score=hs, away_score=as_))
        mk("Probe Aardvarks", "Probe Badgers", datetime(2077, 9, 6, 19), 31, 10)    # same orientation, scores agree
        mk("Probe Condors", "Probe Dingos", datetime(2077, 9, 6, 23), 14, 28)        # ours swapped vs source
        mk("Probe Eagles", "Probe Foxes", datetime(2077, 9, 13, 19), 20, 17)         # score disagrees


RECS = [rec("Probe Aardvarks", "Probe Badgers", 31, 10, "2077-09-06T19:00:00.000Z"),
        rec("Probe Dingos", "Probe Condors", 28, 14, "2077-09-06T23:00:00.000Z", neutral=True),
        rec("Probe Eagles", "Probe Foxes", 21, 17, "2077-09-13T19:00:00.000Z"),
        rec("Probe Ghosts", "Probe Hawks", 7, 3, "2077-09-13T19:00:00.000Z"),                # not ours
        rec("Probe Aardvarks", "FCS Team", 50, 0, "2077-09-20T19:00:00.000Z", ac="fcs"),    # not both FBS
        rec("Probe Badgers", "Probe Eagles", None, None, "2077-12-01T19:00:00.000Z", completed=False)]


def test_discover_refuses_a_missing_required_field():
    keys, missing = nsp.discover(RECS[0])
    assert keys["home"] == "homeTeam" and keys["neutral"] == "neutralSite" and missing == []
    k2, m2 = nsp.discover({k: v for k, v in RECS[0].items() if k != "neutralSite"})
    assert m2 == ["neutral"]


def test_row_level_compare_same_swapped_scores_neutral(capsys, tmp_path):
    world()
    with session_scope() as s:
        before = s.execute(select(func.count(Match.id))).scalar()
        keys, _ = nsp.discover(RECS[0])
        r = nsp.compare(RECS, keys, s, "fbs")
        s.rollback()
    c = r["counts"]
    assert (c["joined_same"], c["joined_swapped"], c["unmatched"]) == (2, 1, 1)
    assert (c["score_agree"], c["score_disagree"]) == (2, 1)                   # swapped game: scores agree in OUR orientation
    assert c["source_not_completed"] == 1 and c["source_not_both_fbs"] == 1
    assert r["source"]["neutral"]["n"] == 1 and r["source"]["nonneutral"]["n"] == 3
    assert "(neutral)" in r["swapped_sample"][0] and "ours 20-17 source 21-17" in r["score_disagree_sample"][0]
    with session_scope() as s:
        assert s.execute(select(func.count(Match.id))).scalar() == before      # nothing written
    # the CLI from a saved file
    p = tmp_path / "cfbd.json"
    p.write_text(json.dumps(RECS))
    assert nsp.main(["--year", "2077", "--from-file", str(p)]) == 0
    out = capsys.readouterr().out
    assert "LABELS: same orientation 2 · swapped 1" in out and "SCORES (our orientation): agree 2/3" in out


def test_api_mode_without_key_refuses_and_never_writes_under_data(monkeypatch, capsys):
    monkeypatch.delenv("CFBD_API_KEY", raising=False)
    assert nsp.main(["--year", "2025"]) == 2 and "no CFBD_API_KEY" in capsys.readouterr().out
    assert nsp.main(["--year", "2025", "--save", os.path.join(nsp.ROOT, "data", "x.json")]) == 2


def test_2025_rate_and_margin_lines_print_n_and_the_withheld_notice_until_the_v1r_run(capsys, tmp_path, monkeypatch):
    """ARCHITECT 2026-10-08, addendum 15 item 1(b) (#368 fence, its one hole): "Until the run is recorded, for 2025
    its two rate-and-margin lines print n and the withheld notice in place of the rates and margins. The rest of
    its receipt stays." The same records under 2077 print the rates; under 2025 they do not; recorded, they return."""
    from src.walters import ncaa_backtest as nb

    recorded = nb.v1r_run_recorded
    monkeypatch.setattr(nb, "v1r_run_recorded", lambda *a: False)   # the fence as it stood before the run (addendum 24)
    world()
    p = tmp_path / "cfbd.json"
    p.write_text(json.dumps(RECS))
    assert nsp.main(["--year", "2025", "--from-file", str(p)]) == 0
    out = capsys.readouterr().out
    for b in ("nonneutral", "neutral"):
        line = next(l for l in out.splitlines() if l.startswith(f"  {b}: SOURCE n "))
        assert nb.FENCED_RATE in line and "home rate 0." not in line and "margin +" not in line, line
        assert " · OURS on joined n " in line
    assert "counts: " in out and "join rate: " in out and "ACCESS TERMS" in out     # the rest of the receipt stays
    assert nsp.main(["--year", "2077", "--from-file", str(p)]) == 0
    assert nb.FENCED_RATE not in capsys.readouterr().out                            # another year: unfenced
    monkeypatch.setattr(nb, "v1r_run_recorded", recorded)          # the committed registry records the run
    assert nsp.main(["--year", "2025", "--from-file", str(p)]) == 0
    out = capsys.readouterr().out
    assert nb.FENCED_RATE not in out and "nonneutral: SOURCE n 3 home rate " in out   # the run recorded: they return
