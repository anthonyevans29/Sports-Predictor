"""ncaa-elo-v1r DECLARATION (ARCHITECT 2026-10-08, addendum 11, item 3, PR A steps (b) and (c)). Pins:
- the registry entry: status declared, run/verdict null, test_set, gate (D5 verbatim), confirmation window (D7
  verbatim) and plan (D7's numbers), the keys the shadow reads (neutral_site_rule, constants), the D9 note;
- the spec quotes D1-D9 and the architect's D5 note verbatim and cites the design receipt;
- the shadow refuses unless 2024, 2025 and 2026 are covered (D6), naming each missing season;
- the shadow walks D2's stream: current labels only, seasons 2024-2026 by the label's season, kickoff then match
  id, postseason included, level scores skipped / counted / listed; neutral games priced and updated with home
  advantage 0 (D1), a label without a neutral flag non-neutral and counted;
- `ncaa-cfbd-coverage` prints the three seasons."""
import json
import math
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.models.ncaa_elo import NCAAEloConfig, NCAAEloV1
from src.walters import ncaa_backtest as nb
from src.walters import ncaa_shadow as sh
from src.walters import registry as reg

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "docs" / "specs" / "ncaa-elo-v1r.md"
LEDGER = ROOT / "docs" / "ledger" / "entries" / "2026-10-08-ncaa-v1r-declaration.md"

D = {
    "D1": "D1. Candidate: NCAAEloV1 with its constants untouched: k_factor 24, home_advantage 55, mov_base 2.2, "
          "season_regression 0.25, default_rating 1500. neutral_site_rule is no_home_advantage_at_neutral: a game "
          "whose label says neutral is priced and updated with home advantage 0. A label without a neutral flag is "
          "treated as non-neutral and counted.",
    "D2": "D2. Stream: stored NCAA games that carry a current CFBD both-FBS label, seasons 2024, 2025 and 2026, in "
          "order of stored kickoff then match id. Home and away, the scores and the neutral flag come from the "
          "label; team ids are merged as J2 rules. Every such game is walked, postseason included. A game with "
          "level scores is a data defect: skipped, counted and listed.",
    "D3": "D3. Split: 2024 is warm-up, update only. The test set is the 2025 games whose season_type is exactly "
          "'regular': predict, then update. A 2025 game with any other season_type, or none, is walked and never "
          "scored. The gate scores no 2026 game.",
    "D4": "D4. Baseline: one number, frozen before any test game is scored: the home win rate of the stream's 2024 "
          "non-neutral games whose season_type is 'regular'. It is the baseline's home probability in every "
          "non-neutral test game; at a neutral site the baseline is 0.5.",
    "D5": "D5. Gate. Under 500 scored games the run is INVALID. PASS iff all four hold on the scored games. (1) "
          "Margin: model log-loss < baseline log-loss - 0.010, unrounded; ties reject. (2) Level: the mean of the "
          "model's home probabilities and the realized home win rate differ by no more than 5pp. (3) Spread: the "
          "calibration slope b lies within 0.20 of 1, where b is the slope of the maximum-likelihood logistic fit "
          "of the result on the model's log-odds, logit P(home win) = a + b * logit(p), with p clipped to "
          "[0.000001, 0.999999]; a fit that does not converge fails. (4) Range: every rating after the last 2025 "
          "game walked lies within 1000 to 2000. Reported, never gated: #79's 10pp bands, the constant-0.5 "
          "log-loss, Brier, the intercept a, cold starts (a team's first game in the stream), and the log-loss "
          "split neutral and non-neutral.",
    "D6": "D6. Preconditions, in code. The gate run refuses unless 2024 and 2025 are covered as L2 and L3 rule; "
          "the shadow and the confirmation read refuse unless 2024, 2025 and 2026 are. If a season misses, nothing "
          "in this declaration bends to fit it: I rule again. The run is one run: a reservation written before the "
          "first read, the scored ids recorded, and it starts only on my word. --preflight scores nothing and "
          "prints, per season, the stream by season_type, the neutral count, the coverage and the D4 baseline. I "
          "confirm the season_type census before the run.",
    "D7": "D7. Confirmation: the first 100 stored NCAA fixtures, by kickoff then id, that kick off after the "
          "verdict and whose two teams, as merged ids, both carry a current label at the freeze; any status; frozen "
          "once by fixture id with the intl-elo-v2 machinery. A cancelled fixture is released and replaced by the "
          "next eligible one. A finished fixture without a label is pending, never replaced. Scored by the same "
          "replay as the gate, the label's flags applied, every cohort fixture whatever its season_type. CONFIRMED "
          "iff log-loss <= 0.6931 and < the D4 baseline's log-loss - 0.010 on the same games. confirmation_plan: "
          "n_games 100, metric log_loss, bar 0.6931, must_beat_reference true, reference the D4 baseline on the "
          "same games minus 0.010.",
    "D8": "D8. What a pass does not do. PASS and CONFIRMED do not make college football a call. The Desk stays "
          "market-only for NCAA until a separate policy ruling, and that ruling needs the neutral flag before "
          "kickoff and the shadow's record against the close. Until then the shadow prices an upcoming game with "
          "the listed home's advantage and says on the row that the neutral flag is unknown.",
    "D9": "D9. Prior reads of this test set: none. The 2026-09-30 run of v1 (all divisions, scrambled 2025 labels, "
          "VOID by the 2026-10-01 ruling) scored 2026 games; the entry names it.",
}
D5_NOTE = ("Tests (2) and (3) replace #79's band rule for this declaration only, before any v1r number exists. #79's "
           "own declaration is untouched, and my sentence in addendum 10 that its acceptance numbers do not move "
           "stands for #79. For v1r the margin, the rating range and the 500 games are #79's; the calibration test "
           "is D5's.")
TEST_SET = "NCAA FBS 2025 regular season (CFBD both-FBS labels; warm-up 2024)"


# --- (b) the registry entry and the spec -------------------------------------------------------------------------

def test_registry_entry_is_declared_with_the_verbatim_gate_window_and_plan():
    e = reg.get(sh.EID)
    assert e is not None, "ncaa-elo-v1r must be declared in docs/registry/experiments.json"
    assert (e["status"], e["run"], e["verdict"]) == ("declared", None, None)
    assert e["sport"] == "ncaa" and e["declaration"] == "docs/specs/ncaa-elo-v1r.md"
    assert e["test_set"] == TEST_SET
    assert e["gate"] == D["D5"].removeprefix("D5. Gate. ")
    assert e["confirmation_window"] == D["D7"].removeprefix("D7. Confirmation: ")
    assert e["confirmation_plan"] == {"n_games": 100, "metric": "log_loss", "bar": 0.6931,
                                      "must_beat_reference": True,
                                      "reference": "the D4 baseline on the same games minus 0.010"}
    assert reg.check_plan(e["confirmation_plan"]) == e["confirmation_plan"]
    assert all(e.get(k) for k in reg.DECLARE_FIELDS) and e["declared_at"].startswith("2026-10-08")
    # the keys the shadow already requires (frozen()): the neutral rule and v1's untouched constants
    assert e["neutral_site_rule"] == "no_home_advantage_at_neutral"
    d = NCAAEloConfig()
    assert e["constants"] == {k: getattr(d, k) for k in sh.CONSTANT_KEYS}
    entry, neutral_ha, rule = sh.frozen()
    assert (neutral_ha, rule, sh.gate_label(entry)) == (False, "no_home_advantage_at_neutral", sh.UNGATED)
    # D9: the VOID 2026-09-30 v1 run named; no prior read of this test set
    assert e["prior_reads_note"] == D["D9"]
    assert reg.prior_reads(e["test_set"], None, before_id=sh.EID) == []
    assert e["design_receipt"].startswith("docs/receipts/ncaa-v1r-design-2026-10-08.md")
    assert (ROOT / "docs" / "receipts" / "ncaa-v1r-design-2026-10-08.md").exists()


def test_spec_and_ledger_quote_d1_to_d9_and_the_d5_note_verbatim():
    for path in (SPEC, LEDGER):
        text_ = " ".join(path.read_text().split())          # line wrapping never changes a word
        for k, v in D.items():
            assert v in text_, f"{path.name}: {k} not verbatim"
        assert D5_NOTE in text_, f"{path.name}: the D5 note not verbatim"
        assert "docs/receipts/ncaa-v1r-design-2026-10-08.md" in text_
        assert TEST_SET in text_


# --- (c) the shadow: D6 coverage for three seasons ---------------------------------------------------------------

def _cov(ok=("2024", "2025", "2026"), present=("2024", "2025", "2026")):
    from src.ingestion import ncaa_cfbd as nc

    return {s_: {"season": s_, "payload": f"p{s_}", "reason": None, "unlabelled": [],
                 **nc.fbs_coverage(100, 100 if s_ in ok else 80)} for s_ in present}


def test_shadow_refuses_unless_2024_2025_and_2026_are_covered_naming_each_missing_season():
    assert sh.coverage_guard(_cov()) is not None
    with pytest.raises(sh.ShadowRefused, match=r"in 2024 \(not computed\) — "):
        sh.coverage_guard(_cov(present=("2025", "2026")))               # before D6: 2024 was never asked
    with pytest.raises(sh.ShadowRefused, match=r"in 2024 80\.0% \(80/100\) — "):
        sh.coverage_guard(_cov(ok=("2025", "2026")))
    with pytest.raises(sh.ShadowRefused) as ex:
        sh.coverage_guard(_cov(ok=(), present=("2025",)))
    msg = str(ex.value)
    assert "2024 (not computed)" in msg and "2025 80.0% (80/100)" in msg and "2026 (not computed)" in msg


def test_fit_reads_coverage_for_the_three_seasons(monkeypatch):
    from src.ingestion import ncaa_cfbd as nc

    asked = []
    monkeypatch.setattr(nc, "stored_coverage", lambda s, seasons, **k: (asked.append(tuple(seasons)), _cov())[1])
    monkeypatch.setattr(nc, "latest_record_stamps", lambda s, seasons=None: {})
    monkeypatch.setattr(nc, "ncaa_teams", lambda s: {})
    sh.fit(datetime(2030, 1, 1), False, games=[])
    assert asked == [("2024", "2025", "2026")]


# --- (c) the shadow: D2's stream, D1's neutral rule ----------------------------------------------------------------

AT, OLD = datetime(2026, 10, 9, 12), datetime(2026, 10, 7, 12)
STAMPS = {"2023": AT, "2024": AT, "2025": AT, "2026": AT}


def G(mid, h, a, season, at, hs, as_, neutral=False, st="regular", stage="FBS (Division I-A)", fetched=None,
      match_season=None, labelled=True):
    if not labelled:
        return nb.Game(h, a, match_season or season, at, hs, as_, stage, match_id=mid)
    return nb.Game(h, a, match_season or season, at, hs, as_, stage, neutral=neutral, label_source="cfbd",
                   orientation="same", match_id=mid, season_type=st, cfbd_id=mid + 1000, cfbd_season=season,
                   label_fetched_at=fetched or AT)


def _games():
    t = datetime(2024, 9, 1)
    return [
        G(5, 1, 2, "2024", t, 28, 21, neutral=True),                                   # neutral: HA 0
        G(4, 3, 4, "2024", t, 17, 10),                                                 # same kickoff, lower id
        G(6, 1, 3, "2024", t + timedelta(days=7), 24, 24),                             # level: skipped, listed
        G(7, 2, 4, "2024", t + timedelta(days=120), 31, 3, st="postseason", stage="Post Season"),   # walked
        G(8, 1, 4, "2025", datetime(2025, 9, 6), 20, 10, neutral=None),                # no flag: non-neutral
        G(9, 2, 3, "2025", datetime(2025, 9, 13), 14, 7, fetched=OLD),                 # stale: never walked
        G(10, 3, 1, "2025", datetime(2025, 9, 20), 35, 0, labelled=False),             # unlabelled: never
        G(11, 3, 2, "2023", datetime(2023, 9, 2), 21, 14),                             # outside D2's seasons
        G(12, 4, 2, "2026", datetime(2026, 9, 5), 10, 3, st=None),
        G(13, 4, 3, "2025", datetime(2026, 1, 2), 27, 20, st="postseason", match_season="2026"),  # label season
    ]


def test_v1r_stream_is_d2s_current_labels_three_seasons_kickoff_then_id_level_scores_listed():
    v = nb.v1r_stream(_games(), {i: f"Team {i}" for i in range(1, 5)}, STAMPS)
    assert [g.match_id for g in v.games] == [4, 5, 7, 8, 13, 12]          # kickoff then match id; postseason in
    assert [g.season for g in v.games] == ["2024", "2024", "2024", "2025", "2025", "2026"]   # the label's season
    assert v.level == [f"match 6 · CFBD 1006 · CFBD season 2024 · {datetime(2024, 9, 8)} · 24-24"]
    assert dict(v.level_by_season) == {"2024": 1}
    assert dict(v.outside) == {"2023": 1}                                 # current, outside 2024-2026: not walked
    assert len(v.stale) == 1 and v.stale[0].startswith("match 9 · CFBD 1009")
    assert dict(v.unlabelled) == {"2025": 2}                              # the stale label and the unlabelled game
    assert v.census == {"2024": {"regular": 2, "postseason": 1}, "2025": {"regular": 1, "postseason": 1},
                        "2026": {"(none)": 1}}
    assert dict(v.neutral) == {"2024": 1} and dict(v.unflagged) == {"2025": 1}
    text_ = "\n".join(v.lines())
    assert "LEVEL SCORES (D2: a data defect; skipped, counted, listed): 1" in text_ and "24-24" in text_
    for season in nb.V1R_SEASONS:
        assert f"  {season}: walked " in text_


def test_shadow_walk_prices_and_updates_a_neutral_game_with_home_advantage_zero(monkeypatch):
    from src.ingestion import ncaa_cfbd as nc

    monkeypatch.setattr(nc, "latest_record_stamps", lambda s, seasons=None: STAMPS)
    monkeypatch.setattr(nc, "ncaa_teams", lambda s: {})
    games = _games()
    model, rc, _ = sh.fit(datetime(2030, 1, 1), False, games=games, fbs=_cov())
    # the replay by hand: NCAAEloV1 untouched, home advantage 0 on the one neutral game only
    ref = NCAAEloV1()
    for g in nb.v1r_stream(games, {}, STAMPS).games:
        if g.neutral is True:
            ref.cfg = NCAAEloConfig(home_advantage=0.0)
        ref.update(g)
        ref.cfg = NCAAEloConfig()
    assert model.m.ratings() == ref.ratings()
    first = 1500 + 24 * math.log(8) * 0.5                                 # 28-21 neutral: expectation 0.5, gap 0
    assert model.cfg == NCAAEloConfig() and model.m.cfg == NCAAEloConfig()        # restored after each call
    assert rc["games_used"] == 6 and rc["neutral_updates"] == 1 and rc["neutral_unflagged"] == 1
    assert rc["walked_by_season"] == {"2024": 3, "2025": 2, "2026": 1}
    assert rc["level_scores_skipped"] == 1 and "24-24" in rc["level_scores_listed"][0]
    assert rc["outside_seasons_not_walked"] == {"2023": 1}
    one = NCAAEloV1()
    one.cfg = NCAAEloConfig(home_advantage=0.0)
    one.update(games[0])
    assert abs(one.rating(1) - first) < 1e-9


def test_coverage_cli_prints_the_three_seasons(tmp_path, monkeypatch):
    from click.testing import CliRunner
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db
    from cli import cli

    eng = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                         expire_on_commit=False))
    db.init_db()
    res = CliRunner().invoke(cli, ["ncaa-cfbd-coverage"])
    assert res.exit_code == 0, res.output
    for season in ("2024", "2025", "2026"):
        assert f"  {season}: labelled 0 / CFBD completed both-FBS 0" in res.output
    assert "coverage condition in ALL THREE seasons (2024, 2025, 2026): DOES NOT HOLD" in res.output


def _fresh(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db

    eng = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                         expire_on_commit=False))
    db.init_db()
    return db


def test_a_current_label_on_our_unscored_scheduled_row_is_walked_with_the_labels_scores(tmp_path, monkeypatch):
    """Codex on #365 (P1), D2 as worded: "Home and away, the scores and the neutral flag come from the label". The
    ingest joins exact fits on our unscored rows and stores CFBD's scores; that label counts toward the coverage
    fact, so the stream walks it whatever our local status. The coverage count and the stream count agree."""
    from src.db.schema import (Competition, Match, MatchStatus, NCAACFBDIngestRecord, NCAACFBDLabel, Sport,
                               Team)
    from src.ingestion import ncaa_cfbd as nc

    db = _fresh(tmp_path, monkeypatch)
    with db.session_scope() as s:
        comp = Competition(sport=Sport.NFL, code="NCAA", name="NCAA", area="USA", type="LEAGUE")
        t = [Team(sport=Sport.NFL, name=f"Lbl {i}") for i in range(3)]
        s.add_all([comp, *t])
        s.flush()

        def match(h, a, day, status, hs=None, as_=None):
            m = Match(sport=Sport.NFL, competition_id=comp.id, season="2025", utc_date=datetime(2025, 9, day, 19),
                      status=status, home_team_id=t[h].id, away_team_id=t[a].id, home_score=hs, away_score=as_,
                      stage="FBS (Division I-A)")
            s.add(m)
            s.flush()
            return m.id

        sched = match(0, 1, 6, MatchStatus.SCHEDULED)                       # ours: never scored
        fin = match(1, 2, 13, MatchStatus.FINISHED, 10, 3)
        bare = match(2, 0, 20, MatchStatus.FINISHED, 35, 7)                 # no label: counted, never walked
        for mid, (hs, as_), gid in ((sched, (24, 17), 1), (fin, (10, 3), 2)):
            s.add(NCAACFBDLabel(match_id=mid, source="cfbd", source_game_id=gid, season="2025", orientation="same",
                                neutral=False, home_score=hs, away_score=as_, fetched_at=AT, season_type="regular"))
        s.add(NCAACFBDIngestRecord(season="2025", division="fbs", fetched_at=AT, payload_file="p.json", records=2,
                                   in_scope=2, joined=2, unlabelled=[]))
    with db.session_scope() as s:
        cov = nc.stored_coverage(s, ["2025"])["2025"]
    v = nb.load_v1r_stream()
    assert (cov["current"], cov["labelled"], cov["ok"]) == (2, 2, True)
    assert v.labelled["2025"] == cov["current"] == len(v.by_season("2025"))       # coverage and stream agree
    by = {g.match_id: g for g in v.games}
    assert set(by) == {sched, fin}
    assert (by[sched].home_score, by[sched].away_score, by[sched].label_source) == (24, 17, "cfbd")
    assert dict(v.unlabelled) == {"2025": 1} and bare not in by
