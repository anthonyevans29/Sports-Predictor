"""PR TWO of addendum 429 item 1(f): the confirmation read REPORTED BOTH WAYS and the UNL venue-input PROVENANCE RECEIPT,
built from #276 and #336 on current main (ARCHITECT 2026-11-19, addenda 426 item 5, 427 item 3, 429 item 1; the 10-23
branch claude/159-unl-provenance a reference, 287 item 3(B)).

160 item 3: "The read [...] is reported BOTH ways (stored flags; corrected flags); the verdict is taken on the corrected
inputs; the frozen method is untouched." 161 item 2: "'Stored' = the provider's flags as derived before any override
(provider_flag); 'corrected' = the flags after intl-venue-override --apply re-derives them [...] the verdict and
--record stand on the corrected flags." 429 item 1(a): "(A). Each line uses its own flags throughout, the naive rates
included [...] The read prints each line whole: log-loss, naive, reference (naive − 0.010), the bar, and its naive
rates." 427 item 3(d): "how many cohort fixtures are priced differently under the two and the largest single difference
in a probability." 429 item 1(d): "the guard that refuses --record while any row's neutral_v3 differs from derive()".
159 item 2: the input snapshot, the fixtures whose stored flag changed after their pre-kickoff file, replayed vs saved,
missing files listed. 429 item 1(c): --export-dir given more than once, flat or dated, never latest/.

The world, on a throwaway DB of its own: a training stream where Andorra's home game at venue 2618 (provider "Spain")
is home under the override and neutral on the provider's country alone, so the two lines' naive rates differ; a cohort of
three, one of them Andorra at home at 2618. The registry is monkeypatched; the real ledger is never touched."""
import sqlite3
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from src.ingestion import intl_venues as iv
from src.walters import intl_elo as ie
from src.walters import intl_provenance as ip
from src.walters import intl_shadow as us
from src.walters import registry as reg

NOW = datetime(2096, 3, 1)
ENTRY = {"id": "intl-elo-v2", "status": "confirming",
         "run": {"result": {"fit_c_mult": 1.5, "fit_k_mult": 1.0}},
         "verdict": {"verdict": "PASS", "at": "2096-01-01T00:00:00Z"},
         "confirmation_plan": {"n_games": 3, "metric": "log_loss", "bar": 1.0986, "must_beat_reference": True,
                               "reference": "naive - 0.010"}}
R = iv.NEUTRAL_V3_RULE


@pytest.fixture
def world(tmp_path, monkeypatch):
    """(ids, db file). Rows at 2618 are stored as --apply leaves them (the override's flag and rule)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db
    from src.db.schema import Competition, IntlMatchVenue, Match, MatchStatus, Sport, Team

    f = tmp_path / "w.db"
    eng = create_engine(f"sqlite:///{f}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                         expire_on_commit=False))
    db.init_db()
    ids = {}
    with db.session_scope() as s:
        unl = Competition(sport=Sport.SOCCER, code="UNL", name="UNL", area="I", type="INTL")
        s.add(unl)
        s.flush()
        t = {a: Team(sport=Sport.SOCCER, name=a, area=a) for a in ("Andorra", "Latvia", "Spain", "Malta")}
        s.add_all(t.values())
        s.flush()

        def game(key, home, away, when, hs, as_, vid, vc, season="2018/19", at=datetime(2026, 10, 2)):
            m = Match(sport=Sport.SOCCER, competition_id=unl.id, season=season, utc_date=when,
                      status=MatchStatus.FINISHED, status_raw="FT", home_team_id=t[home].id, away_team_id=t[away].id,
                      home_score=hs, away_score=as_)
            s.add(m)
            s.flush()
            flag, rule = iv.derive(vid, vc, home)                          # as --apply leaves it
            s.add(IntlMatchVenue(match_id=m.id, venue_id=vid, venue_country=vc, home_country=home, neutral_v3=flag,
                                 rule=rule, derived_at=at))
            ids[key] = m.id

        game("t1", "Andorra", "Latvia", datetime(2019, 6, 1), 0, 1, 2618, "Spain")        # home <-> neutral
        game("t2", "Spain", "Malta", datetime(2019, 6, 2), 2, 0, 501, "Spain")
        game("t3", "Latvia", "Malta", datetime(2019, 6, 3), 1, 1, 777, "Elsewhere")      # neutral both ways
        game("t4", "Malta", "Latvia", datetime(2019, 6, 4), 1, 1, 778, "Malta")
        game("c1", "Andorra", "Malta", datetime(2096, 2, 1, 18), 2, 1, 2618, "Spain", "2095/96", datetime(2096, 2, 5))
        game("c2", "Spain", "Latvia", datetime(2096, 2, 2, 18), 0, 0, 501, "Spain", "2095/96")
        game("c3", "Latvia", "Andorra", datetime(2096, 2, 3, 18), 1, 2, 778, "Latvia", "2095/96")
    cohort = [ids["c1"], ids["c2"], ids["c3"]]
    monkeypatch.setattr(reg, "get", lambda eid, path=None: ENTRY if eid == "intl-elo-v2" else None)
    monkeypatch.setattr(us, "cohort", lambda e, s: {"ids": list(cohort), "state": "frozen", "eligible_stored": 3,
                                                     "n_games": 3})
    monkeypatch.setattr(us, "eligible_fixtures", lambda s, e: [{"id": i, "status": "finished", "unscoreable": False}
                                                               for i in cohort])
    return ids, f


def _copy(src: Path, tmp_path) -> Path:
    dst = tmp_path / "copy" / "sports.db"
    dst.parent.mkdir()
    a, b = sqlite3.connect(str(src)), sqlite3.connect(str(dst))
    try:
        a.backup(b)
    finally:
        b.close()
        a.close()
    return dst


def _set_flag(mid, flag, rule=R):
    from src.db.database import session_scope
    from src.db.schema import IntlMatchVenue
    with session_scope() as s:
        v = s.get(IntlMatchVenue, mid)
        v.neutral_v3, v.rule = flag, rule


# ---- the read both ways ---------------------------------------------------------------------------------------------

def test_each_line_uses_its_own_flags_throughout_the_naive_rates_included(world):
    ids, _ = world
    r = us.confirmation_read(now=NOW)
    b = r["both"]
    assert r["n"] == 3 and r["complete"] and r["derive_mismatch"] == []
    c, p = b["corrected"], b["stored"]
    # the corrected line IS the read's own keys (the verdict and --record stand on it, 161 item 2)
    assert (c["log_loss"], c["naive_log_loss"], c["reference_log_loss"]) == (
        r["log_loss"], r["naive_log_loss"], r["reference_log_loss"])
    with __import__("src.db.database", fromlist=["x"]).session_scope() as s:
        games, _ = ie.load(s, rule="v3")
        s.rollback()
    train = [g for g in games if ie.TRAIN_FROM <= g.kickoff < ie.TRAIN_TO]
    prov = {ids["t1"]: True, ids["c1"]: True}                                    # the provider's Spain at 2618
    train_p = [replace(g, neutral=prov.get(g.id, g.neutral)) for g in train]
    assert c["naive_rates"] == us.naive_rates(ie.naive(train))
    assert p["naive_rates"] == us.naive_rates(ie.naive(train_p)) and p["naive_rates"] != c["naive_rates"]
    assert c["naive_rates"]["n_train_neutral"] == 1 and p["naive_rates"]["n_train_neutral"] == 2
    games_p = [replace(g, neutral=prov.get(g.id, g.neutral)) for g in games if g.kickoff < NOW]
    mu = sum(g.hg + g.ag for g in train) / (2 * len(train))
    w2 = us._walk(games_p, set(r["scored_ids"]), train_p, mu, 1.5, 1.0)          # the frozen method, own flags
    assert p["log_loss"] == w2["ll_m"] / 3 and p["naive_log_loss"] == w2["ll_n"] / 3
    assert p["log_loss"] != c["log_loss"] and p["bar"] == c["bar"] == 1.0986
    assert b["priced_differently"] >= 1 and b["priced_of"] == 3
    d, mid = b["max_diff"]
    assert d > 0 and mid in r["scored_ids"]


def test_the_lines_print_each_line_whole_and_the_guard(world):
    ids, _ = world
    r = us.confirmation_read(now=NOW)
    L = us.both_ways_lines(r)
    assert L[0].startswith("  BOTH WAYS (ARCHITECT 2026-10-23, addendum 160 item 3; 161 item 2; 429 item 1(a))")
    assert L[1].startswith("    corrected flags (neutral_v3 as stored, after intl-venue-override --apply): 3/3 labelled "
                           f"· log-loss {r['log_loss']:.4f} · naive {r['naive_log_loss']:.4f} · reference (naive − 0.010) "
                           f"{r['reference_log_loss']:.4f} · bar 1.0986 · naive rates: home H/D/A ")
    assert L[2].startswith("    stored flags (the provider's venue country alone, no override): 3/3 labelled · log-loss ")
    assert "neutral draw" in L[1] and "neutral draw" in L[2]
    assert L[3].startswith(f"    cohort fixtures priced differently by the two: {r['both']['priced_differently']} of 3 · "
                           "largest single difference in a probability: ")
    assert len(L) == 4                                                          # no row left unapplied
    _set_flag(ids["t1"], True)                                                  # the override not applied to one row
    r = us.confirmation_read(now=NOW)
    assert r["derive_mismatch"] == [ids["t1"]]
    assert us.both_ways_lines(r)[-1].startswith(f"  NOT APPLIED: 1 row(s) whose neutral_v3 differs from "
                                                f"intl-venue-override's derivation (the override not applied on this "
                                                f"store, or lapsed): {ids['t1']} — --record refuses")


def test_with_no_entry_in_the_table_and_every_row_agreeing_nothing_is_added():
    """426 item 5(c)'s empty-table pin is test_intl_shadow's 346 pins (console byte for byte); here the lines alone."""
    assert us.both_ways_lines({"derive_mismatch": []}) == []


def test_record_refuses_while_a_row_is_not_applied_and_records_nothing(monkeypatch):
    from click.testing import CliRunner

    from cli import cli
    r = {"n": 3, "n_games": 3, "bar": 1.0986, "scored_ids": [1, 2, 3], "first_game_at": "2096-02-01T18:00:00Z",
         "cohort_state": "frozen", "cohort_size": 3, "eligible_stored": 3, "pending": [], "release_due": 0,
         "complete": True, "log_loss": 0.9, "naive_log_loss": 1.0, "reference_log_loss": 0.99, "derive_mismatch": [7]}
    monkeypatch.setattr(us, "confirmation_read", lambda now=None, s=None: r)
    monkeypatch.setattr(us, "frozen", lambda: (ENTRY, 1.5, 1.0))
    called = []
    monkeypatch.setattr(reg, "record_confirmation", lambda *a, **k: called.append(a))
    out = CliRunner().invoke(cli, ["intl-elo-confirm", "--record", "--ruling", "ARCHITECT: x"])
    assert out.exit_code == 2 and called == []
    assert out.output.rstrip().endswith("REFUSED: 1 row(s)' neutral_v3 differ from intl-venue-override's derivation "
                                        "(the override not applied on this store, or lapsed): the verdict and --record "
                                        "stand on the corrected flags (addendum 161 item 2); run intl-venue-override "
                                        "--apply first; nothing recorded")


def test_both_lines_come_from_the_copy_in_one_session_equal_to_the_store(world, tmp_path):
    from src.walters import mlb_pitchers_gate as mp
    _, f = world
    copy = _copy(f, tmp_path)
    sha = us.copy_sha256(copy)
    app = us.confirmation_read(now=NOW)
    with mp.readonly_session(copy) as s:
        assert us.confirmation_read(now=NOW, s=s) == app
    assert us.copy_sha256(copy) == sha and not us.copy_sidecars(copy)


# ---- the provenance receipt ------------------------------------------------------------------------------------------

def _shadow(path: Path, at: str, rows):
    import json
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"engine": us.ENGINE, "exported_at": at, "predictions": [
        {"match_id": mid, "utc_date": ko, "prediction": {"neutral_v3": flag, "home_win_prob": 0.3333,
                                                         "draw_prob": 0.3333, "away_win_prob": 0.3334}}
        for mid, ko, flag in rows]}))


def _exports(tmp_path, ids):
    laptop, host = tmp_path / "laptop_exports", tmp_path / "mirror" / "host"
    # c1: priced on the provider's flag (neutral) before the override; c2 in the host's dated folder; c3 missing
    _shadow(laptop / "unl_shadow_2096-02-01_0900.json", "2096-02-01T09:00:00", [(ids["c1"], "2096-02-01T18:00:00", True)])
    _shadow(host / "2096-02-02" / "unl_shadow_2096-02-02_0900.json", "2096-02-02T09:00:00",
            [(ids["c2"], "2096-02-02T18:00:00", False)])
    _shadow(host / "latest" / "unl_shadow_2096-02-03_0900.json", "2096-02-03T09:00:00",
            [(ids["c3"], "2096-02-03T18:00:00", False)])                       # latest/: never read
    return laptop, host


def test_the_receipt_snapshot_changed_replayed_and_missing(world, tmp_path):
    ids, _ = world
    laptop, host = _exports(tmp_path, ids)
    from src.db.database import readonly_scope
    with readonly_scope() as s:
        r = ip.receipt(s, [str(laptop), str(host)])
    assert r["files"] == 2 and r["missing"] == [ids["c3"]]
    assert r["moved_by_override"] == [ids["c1"]]
    assert [x["id"] for x in r["changed"]] == [ids["c1"]]                     # saved neutral, stored home now
    c1 = r["changed"][0]
    assert c1["saved_flag"] is True and c1["flag"] is False and c1["diff"] is not None
    assert r["material"] == [c1] and c1["diff"] > ip.ROUNDING
    text = "\n".join(ip.lines(r))
    assert text.startswith(f"UNL VENUE-INPUT PROVENANCE ({ip.RULING}) · read-only · cohort FROZEN (3 of 3) · labelled "
                           "3 · with a venue row 3 · pre-kickoff shadow file 2 · MISSING 1")
    assert "neutral_v3 home [provider's neutral] · flag at 2096-02-05 00:00Z" in text
    assert "shadow file MISSING" in text and f"MISSING shadow files (1): {ids['c3']}" in text
    assert "CHANGED AFTER THE PRE-KICKOFF FILE: 1 · replayed vs saved: material (|diff| > 5e-05) 1" in text
    assert f"priced neutral · stored now home · ingested 2096-02-05 00:00Z · replayed " in text
    assert "TO THE ARCHITECT: 1 material difference(s)" in text
    assert "c_mult 1.5 · k_mult 1.0 (the registry's run record; never refit)" in text


def test_the_receipt_refuses_latest_and_a_missing_folder(world, tmp_path):
    ids, _ = world
    laptop, host = _exports(tmp_path, ids)
    from src.db.database import readonly_scope
    with readonly_scope() as s:
        with pytest.raises(us.ShadowRefused, match="latest/ is never read"):
            ip.receipt(s, [str(host / "latest")])
        with pytest.raises(us.ShadowRefused, match="not a directory"):
            ip.receipt(s, [str(tmp_path / "nowhere")])
        with pytest.raises(us.ShadowRefused, match="at least once"):
            ip.receipt(s, [])


def test_the_command_on_a_copy_and_on_the_store_writes_nothing(world, tmp_path):
    from click.testing import CliRunner

    from cli import cli
    ids, f = world
    laptop, host = _exports(tmp_path, ids)
    copy = _copy(f, tmp_path)
    sha_copy, sha_store = us.copy_sha256(copy), us.copy_sha256(f)
    args = ["unl-provenance-receipt", "--export-dir", str(laptop), "--export-dir", str(host)]
    on_copy = CliRunner().invoke(cli, args + ["--db", str(copy)])
    assert on_copy.exit_code == 0, on_copy.output
    head, rest = on_copy.output.split("\n", 1)
    assert head.startswith(f"--db {copy.resolve()} · sha256 {sha_copy} · a .backup copy, opened mode=ro&immutable=1")
    on_store = CliRunner().invoke(cli, args)
    assert on_store.exit_code == 0 and rest == on_store.output                 # the same receipt
    assert us.copy_sha256(copy) == sha_copy and us.copy_sha256(f) == sha_store
    out = CliRunner().invoke(cli, ["unl-provenance-receipt", "--export-dir", str(host / "latest")])
    assert out.exit_code == 2 and out.output.startswith(f"REFUSED: --export-dir {host / 'latest'}: a latest/ folder")
