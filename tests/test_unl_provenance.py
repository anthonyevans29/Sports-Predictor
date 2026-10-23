"""ARCHITECT 2026-10-23, addendum 159 item 2 (#336): the UNL venue-input provenance receipt; addendum 160 item 3: the
read reported both ways. On a throwaway DB of its own, the registry, cohort and stream monkeypatched: the input
snapshot per cohort fixture (result, stored and provider flags, the flag's ingest time, the file); a fixture whose
stored flag changed after its pre-kickoff file is replayed against the saved probability; a missing file is listed;
the read on the provider's flags differs exactly where an override moves a flag; nothing is written."""
import json
from datetime import datetime, timedelta

import pytest

from src.ingestion import intl_venues as iv
from src.walters import intl_elo as ie
from src.walters import intl_provenance as ip
from src.walters import intl_shadow as sh

KO = datetime(2026, 10, 9, 18, 45)
E = {"confirmation_plan": {"n_games": 3, "bar": 1.0986}}


@pytest.fixture
def world(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db
    from src.db.schema import Competition, IntlMatchVenue, Match, MatchStatus, Sport, Team

    eng = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                         expire_on_commit=False))
    db.init_db()
    ids, flag_at = {}, datetime(2026, 10, 9, 12, 0)                   # the override applied at noon on match day
    with db.session_scope() as s:
        c = Competition(sport=Sport.SOCCER, code="UNL", name="UNL", area="I", type="INTL")
        t = {n: Team(sport=Sport.SOCCER, name=n, area=n) for n in ("Andorra", "Latvia", "Moldova", "Wales")}
        s.add_all([c, *t.values()])
        s.flush()
        for i, (key, h, a, vid, vc, flag) in enumerate((("and", "Andorra", "Latvia", 2618, "Spain", False),
                                                        ("wal", "Wales", "Moldova", 77, "Wales", False),
                                                        ("nofile", "Latvia", "Wales", 78, "Latvia", False))):
            m = Match(sport=Sport.SOCCER, competition_id=c.id, season="2026/27", utc_date=KO + timedelta(days=i),
                      status=MatchStatus.FINISHED, status_raw="FT", home_team_id=t[h].id, away_team_id=t[a].id,
                      home_score=2, away_score=1)
            s.add(m)
            s.flush()
            ids[key] = m.id
            ids[f"t_{h}"], ids[f"t_{a}"] = t[h].id, t[a].id
            s.add(IntlMatchVenue(match_id=m.id, venue_id=vid, venue_country=vc, home_country=h, neutral_v3=flag,
                                 rule=iv.NEUTRAL_V3_RULE, derived_at=flag_at if key == "and" else KO - timedelta(days=9)))
    train = [ie.Game(-i, "UEFA_EURO_Q", "2023", datetime(2023, 3, 1) + timedelta(days=7 * i), ids["t_Andorra"] if i % 2
                     else ids["t_Wales"], ids["t_Latvia"], 1 + i % 2, i % 3, i % 3 == 0) for i in range(1, 12)]
    stored = [ie.Game(ids[k], "UNL", "2026/27", KO + timedelta(days=i), ids[h], ids[a], 2, 1, False)
              for i, (k, h, a) in enumerate((("and", "t_Andorra", "t_Latvia"), ("wal", "t_Wales", "t_Moldova"),
                                             ("nofile", "t_Latvia", "t_Wales")))]
    monkeypatch.setattr(sh, "frozen", lambda: (E, 1.0, 1.0))
    monkeypatch.setattr(sh, "cohort", lambda e, s: {"state": "frozen", "ids": [ids["and"], ids["wal"], ids["nofile"]],
                                                    "n_games": 3, "eligible_stored": 3})
    monkeypatch.setattr(sh, "eligible_fixtures", lambda s, e: [])
    monkeypatch.setattr(ie, "load", lambda s, rule="v3": (train + stored, {}))
    ex = tmp_path / "ex"
    ex.mkdir()
    rows = [{"match_id": ids["and"], "utc_date": KO.isoformat(),
             "prediction": {"home_win_prob": 0.30, "draw_prob": 0.30, "away_win_prob": 0.40, "neutral_v3": True}},
            {"match_id": ids["wal"], "utc_date": (KO + timedelta(days=1)).isoformat(),
             "prediction": {"home_win_prob": 0.5, "draw_prob": 0.3, "away_win_prob": 0.2, "neutral_v3": False}}]
    (ex / "unl_shadow_2026-10-09_0900.json").write_text(json.dumps({
        "engine": sh.ENGINE, "exported_at": datetime(2026, 10, 9, 9, 0).isoformat(), "predictions": rows}))
    return ids, ex, train


def test_the_snapshot_the_changed_fixture_replayed_and_the_missing_file(world):
    ids, ex, train = world
    r = ip.receipt(str(ex))
    snap = {x["id"]: x for x in r["snapshot"]}
    a = snap[ids["and"]]
    assert (a["result"], a["flag"], a["provider_flag"], a["saved_flag"]) == ("H", False, True, True)
    assert r["moved_by_override"] == [ids["and"]] and r["missing"] == [ids["nofile"]]
    assert [x["id"] for x in r["changed"]] == [ids["and"]]                  # the Wales row priced its stored flag
    mu = sum(g.hg + g.ag for g in train) / (2 * len(train))
    m = ie.IntlElo(mu=mu, c_mult=1.0, k_mult=1.0)
    for g in train:
        m.update(g)
    want = m.probs(ie.Game(ids["and"], "UNL", "2026/27", KO, ids["t_Andorra"], ids["t_Latvia"], 0, 0, False))
    assert a["replay"]["replayed"] == want and a["replay"]["saved"] == (0.30, 0.30, 0.40)
    assert r["material"] == 1
    text = "\n".join(ip.lines(r))
    assert f"{ids['nofile']} · " in text and "shadow file MISSING" in text and "[provider's neutral]" in text
    assert "TO THE ARCHITECT: 1 material difference" in text and "flag at 2026-10-09 12:00Z" in text


def test_the_read_is_reported_both_ways(world):
    ids, ex, train = world
    stored = sh.confirmation_read(now=KO + timedelta(days=5))
    provider = sh.confirmation_read(now=KO + timedelta(days=5), flags="provider")
    assert stored["n"] == provider["n"] == 3 and stored["flags"] == "stored" and provider["flags"] == "provider"
    assert stored["log_loss"] != provider["log_loss"]                       # the Andorra fixture's flag moves it
    with pytest.raises(ValueError):
        sh.confirmation_read(flags="other")


def test_nothing_is_written_and_the_script_refuses_a_missing_db(world, tmp_path, monkeypatch):
    import importlib.util

    from sqlalchemy import text

    import src.db.database as db
    ids, ex, _ = world
    with db._engine.connect() as conn:
        before = conn.execute(text("SELECT match_id, neutral_v3, derived_at FROM intl_match_venue ORDER BY 1")).all()
    ip.receipt(str(ex))
    with db._engine.connect() as conn:
        assert conn.execute(text("SELECT match_id, neutral_v3, derived_at FROM intl_match_venue ORDER BY 1")).all() \
            == before
    spec = importlib.util.spec_from_file_location("unl_prov", "scripts/unl_provenance_receipt.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'absent.db'}")
    with pytest.raises(SystemExit, match="never creates one"):
        mod.main([])
    assert not (tmp_path / "absent.db").exists()


def test_intl_elo_confirm_prints_the_read_both_ways(world):
    from click.testing import CliRunner

    from cli import cli
    res = CliRunner().invoke(cli, ["intl-elo-confirm"])
    assert res.exit_code == 0, res.output
    lines = res.output.splitlines()
    so_far = next(x for x in lines if x.startswith("  so far: log-loss"))
    both = next(x for x in lines if x.startswith("  the same read on the provider's flags"))
    assert "the verdict is taken on the stored, corrected flags" in both and "3/3 labelled" in both
    stored_ll = so_far.split("log-loss ")[1].split()[0]
    provider_ll = both.split("labelled · log-loss ")[1].split()[0]
    assert stored_ll != provider_ll and "identical to the stored-flag read" not in both
