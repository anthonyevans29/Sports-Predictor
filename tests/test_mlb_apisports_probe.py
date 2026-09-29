"""MLB-PROBE (architect 2026-09-29): the probe's pairing/summary logic, on
synthetic provider payloads. The live run needs an API-Baseball key and the
laptop DB; these tests pin the rules it reports with."""
import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "mlb_apisports_probe", Path(__file__).resolve().parents[1] / "scripts" / "mlb_apisports_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

T = datetime(2025, 7, 4, 17, 5)


def g(pid, home, away, at, short="FT", hr=5, ar=3, **extra):
    return {"id": pid, "date": at.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
            "status": {"short": short, "long": {"FT": "Finished", "NS": "Not Started"}.get(short, short)},
            "teams": {"home": {"name": home}, "away": {"name": away}},
            "scores": {"home": {"total": hr}, "away": {"total": ar}}, **extra}


from src.db.schema import MatchStatus

FIN = MatchStatus.FINISHED.value   # "finished": the DB's vocabulary, read from the enum, never typed


def o(mid, home, away, at, status=FIN, stage="R", hs=5, as_=3):
    return {"id": mid, "utc": at, "home": home, "away": away, "status": status, "stage": stage,
            "home_score": hs, "away_score": as_}


def test_pairs_names_across_feeds_and_doubleheaders_by_nearest_start():
    prov = probe.provider_rows([
        g(1, "New York Yankees", "Boston Red Sox", T),
        g(2, "Chicago Cubs", "St.Louis Cardinals", T + timedelta(hours=1)),
        g(3, "Chicago Cubs", "St.Louis Cardinals", T + timedelta(hours=6), hr=1, ar=2),   # doubleheader game 2
        g(4, "Seattle Mariners", "Houston Astros", T, short="NS", hr=None, ar=None),       # provider-only
    ])
    ours = [o(10, "New York Yankees", "Boston Red Sox", T + timedelta(minutes=10)),
            o(11, "Chicago Cubs", "St. Louis Cardinals", T + timedelta(hours=1)),
            o(12, "Chicago Cubs", "St. Louis Cardinals", T + timedelta(hours=6, minutes=5), hs=1, as_=2),
            o(13, "Texas Rangers", "Oakland Athletics", T)]                                # ours-only
    r = probe.pair(ours, prov)
    got = {oo["id"]: p["id"] for oo, p in r["pairs"]}
    assert got == {10: 1, 11: 2, 12: 3}
    assert [x["id"] for x in r["ours_unmatched"]] == [13]
    assert [x["id"] for x in r["provider_unmatched"]] == [4]


def test_equidistant_doubleheader_is_ambiguous_never_guessed():
    prov = probe.provider_rows([g(1, "Chicago Cubs", "Miami Marlins", T - timedelta(hours=2)),
                                g(2, "Chicago Cubs", "Miami Marlins", T + timedelta(hours=2))])
    r = probe.pair([o(10, "Chicago Cubs", "Miami Marlins", T)], prov)
    assert r["pairs"] == [] and [x["id"] for x in r["ambiguous"]] == [10]


def test_summary_vocab_scores_postseason_and_odds_join():
    prov = probe.provider_rows([
        g(1, "New York Yankees", "Boston Red Sox", T, week="Regular Season"),
        g(2, "Los Angeles Dodgers", "San Diego Padres", T + timedelta(days=90), hr=4, ar=4,
          week="Division Series"),                                                          # score disagrees
    ])
    ours = [o(10, "New York Yankees", "Boston Red Sox", T),
            o(11, "Los Angeles Dodgers", "San Diego Padres", T + timedelta(days=90), stage="D", hs=4, as_=2),
            o(12, "Tampa Bay Rays", "Toronto Blue Jays", T + timedelta(days=91), stage="L")]
    s = probe.summarize("2025", ours, prov, odds_match_ids={10, 12})
    assert s["paired"] == 2 and s["coverage_pct"] == 66.67
    assert s["status_vocab"] == {"FT|Finished": 2}
    assert s["status_crosstab"] == {"finished <- FT": 2}
    assert s["finished_pairs_scored"] == 2 and s["score_agree"] == 1
    assert s["postseason_ours"] == 2 and s["postseason_paired"] == 1
    assert s["stage_vs_provider_fields"] == {'D | {"week": "Division Series"}': 1,
                                             'R | {"week": "Regular Season"}': 1}
    assert s["odds_joined_matches"] == 2 and s["odds_joined_paired"] == 1
    assert s["id_sample"][0] == {"provider_id": 1, "match_id": 10, "utc": T.isoformat()}
    v = probe.verdict(s)
    assert v[0].startswith("✗ coverage 2025: 2/3 (66.67%)")
    assert any(x.startswith("✗ scores 2025: 1/2") for x in v)
    assert any(x.startswith("✗ postseason 2025: 1/2") for x in v)
    assert any(x.startswith("✗ odds-join ids 2025: 1/2") for x in v)


def test_no_key_stops_cleanly(monkeypatch, capsys):
    monkeypatch.delenv("API_BASEBALL_KEY", raising=False)
    monkeypatch.delenv("API_FOOTBALL_KEY", raising=False)
    import dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    assert probe.main([]) == 1
    assert "No API-Baseball key" in capsys.readouterr().out


def test_finished_vocabulary_is_the_enum_value_so_scores_are_actually_compared():
    """Regression (receipt 2026-09-29): the first probe compared status to
    "FINISHED" while the DB stores "finished", so no pair was ever scored."""
    assert FIN == "finished" and probe._finished(FIN) and probe._finished(MatchStatus.FINISHED)
    assert not probe._finished(MatchStatus.SCHEDULED.value)
    prov = probe.provider_rows([g(1, "New York Yankees", "Boston Red Sox", T, hr=5, ar=3)])
    s = probe.summarize("2026", [o(10, "New York Yankees", "Boston Red Sox", T)], prov, set())
    assert s["finished_pairs_scored"] == 1 and s["score_agree"] == 1 and s["score_parity_pct"] == 100.0
    assert any(v.startswith("✓ scores 2026: 1/1 finished pairs agree (100.0%) — PHASE A gate >= 99.5%: PASS")
               for v in probe.verdict(s))


def test_parity_gate_fails_below_99_5_and_lists_disagreements():
    prov = probe.provider_rows([g(i, f"Team {i} Home", f"Team {i} Away", T + timedelta(days=i), hr=5, ar=3)
                                for i in range(1, 201)])
    ours = [o(1000 + i, f"Team {i} Home", f"Team {i} Away", T + timedelta(days=i),
              hs=(9 if i == 7 else 5)) for i in range(1, 201)]
    s = probe.summarize("2025", ours, prov, set())
    assert s["score_agree"] == 199 and s["score_parity_pct"] == 99.5          # exactly at the gate: PASS
    assert s["score_disagree_sample"] == [{"match_id": 1007, "provider_id": 7, "game": "Team 7 Away @ Team 7 Home",
                                           "utc": (T + timedelta(days=7)).isoformat(), "ours": "3-9",
                                           "provider": "3-5"}]
    ours[8]["home_score"] = 9                                                  # a second miss: 99.0%
    s = probe.summarize("2025", ours, prov, set())
    assert any("PHASE A gate >= 99.5%: FAIL" in v for v in probe.verdict(s))
    assert probe.verdict(probe.summarize("2025", [], prov, set()))[1].startswith(
        "✗ scores 2025: no finished pair scored")


def test_unpaired_finished_games_named_with_doubleheader_and_utc_boundary_reads():
    prov = probe.provider_rows([
        g(1, "Chicago Cubs", "Miami Marlins", T),                             # pairs with our game 1 of a DH
        g(2, "Seattle Mariners", "Houston Astros", T + timedelta(hours=20)),  # 20h off: outside ±12h
    ])
    ours = [o(10, "Chicago Cubs", "Miami Marlins", T),
            o(11, "Chicago Cubs", "Miami Marlins", T + timedelta(hours=5)),   # DH game 2: provider lists one
            o(12, "Seattle Mariners", "Houston Astros", T),
            o(13, "Texas Rangers", "Oakland Athletics", T, stage="W"),
            o(14, "Texas Rangers", "Los Angeles Angels", T, status=MatchStatus.SCHEDULED.value)]   # not finished
    s = probe.summarize("2025", ours, prov, set())
    u = {x["match_id"]: x for x in s["ours_unpaired_finished"]}
    assert set(u) == {11, 12, 13}                                              # the scheduled one is not listed
    assert u[11]["why"].startswith("DOUBLEHEADER suspect: provider #1") and "our match #10" in u[11]["why"]
    assert u[12]["why"].startswith("UTC-BOUNDARY/date suspect: provider #2") and "+20.0h" in u[12]["why"]
    assert u[13]["why"] == "no same-teams provider game within ±48h" and u[13]["stage"] == "W"
    assert u[13]["game"] == "Oakland Athletics @ Texas Rangers" and u[13]["utc"] == T.isoformat()
