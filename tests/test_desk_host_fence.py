"""THE HOST FENCE (ARCHITECT 2026-10-17 10:15 ET, addendum 109 item 3, RULED; #410), verbatim: "when the
writer-of-record role is host, every soccer model_edge row is PASS, pass_kind "host_fence", reason "host: ratings keyed
to the laptop's team ids (#410); the cutover replaces this database". rating_source is untouched; the row's model
numbers stay in the file for the compare. The host pager never sees a soccer PLAY from the host. Test: a
two-mis-keyed-clubs fixture under role host → PASS host_fence; under role laptop → unchanged. The fence lifts with the
cutover (the ruling that cuts over names it). No re-keying on the host (addendum 36 stands)."
The role read (built pending the architect's confirmation on #410): the machine's SP_EXPORTS_MIRROR_ROLE, from its
own host.env first, then the process environment; exactly "host"; unset or any other value leaves the row as it is.
The switch: desk_policy.HOST_FENCE_RULE. tests/conftest.py points SP_HOST_ENV at a file that does not exist."""
import copy
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.walters import desk_policy as dp
from src.walters import window

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy" / "hosting"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import sp_window_page as page  # noqa: E402

REASON = "host: ratings keyed to the laptop's team ids (#410); the cutover replaces this database"   # the ruled words
NOW = datetime(2026, 10, 17, 15, 0, tzinfo=timezone.utc)


def pl(mid, home, away, leagues, probs, fair, legs=None, src=("model", "model"), comp="PL",
       utc="2026-10-18T15:30:00"):
    """A host PL export row between two mis-keyed clubs (#410's receipt: each host id reads a laptop club of another
    league, rating_source model on both sides)."""
    p = dict(zip(("home_win", "draw", "away_win"), probs))
    top = max(p, key=p.get)
    r = {"match_id": mid, "home_team": home, "away_team": away, "utc_date": utc, "competition": comp,
         "season": "2026/27",
         "prediction": {"probabilities": p, "tier": "lean", "top_pick": top, "top_pick_prob": p[top],
                        "model_version": "v22",
                        "factor_breakdown": {"home_rating_source": src[0], "away_rating_source": src[1],
                                             "home_league": leagues[0], "away_league": leagues[1]}},
         "market": {"bookmaker_count": 9,
                    "selections": {k: {"fair_prob": v} for k, v in zip(("HOME", "DRAW", "AWAY"), fair)}},
         "input_quality": {"rating_source": {"home": src[0], "away": src[1]}}}
    if legs:
        r["kalshi_legs"] = legs
    return r


def mun_ful():
    """Manchester United (host id reads GRE, 1677.5) v Fulham (reads CZE, 1544.9): a 6pp edge on HOME that clears
    the exec gate, a full-unit PLAY with an order line on the laptop."""
    return pl(410001, "Manchester United", "Fulham", ("GRE", "CZE"), (0.56, 0.24, 0.20), (0.50, 0.27, 0.23),
              legs={"HOME": {"ticker": "KXEPLGAME-26OCT18MUNFUL-MUN", "bid": 0.44, "ask": 0.45}})


def cov_mci_value():
    """Coventry (reads SA) v Manchester City (reads BEL): the pick is below the floor, the draw carries a value shadow."""
    return pl(410002, "Coventry", "Manchester City", ("SA", "BEL"), (0.45, 0.30, 0.25), (0.46, 0.24, 0.30))


def cov_mci_ladder():
    """The same pair, a 12pp away edge on a three-way board: a LADDER (double chance) on the laptop."""
    return pl(410003, "Coventry", "Manchester City", ("SA", "BEL"), (0.28, 0.22, 0.50), (0.38, 0.24, 0.38))


def annotate(*rows, sport="soccer"):
    doc = {"sport": sport, "predictions": [copy.deepcopy(r) for r in rows]}
    dp.annotate(doc, now=NOW)
    return {r["match_id"]: r["desk"] for r in doc["predictions"]}, doc


@pytest.fixture
def role(monkeypatch):
    def set_role(v):
        if v is None:
            monkeypatch.delenv(dp.ROLE_ENV, raising=False)
        else:
            monkeypatch.setenv(dp.ROLE_ENV, v)
    set_role(None)
    return set_role


def test_the_rule_its_kind_and_its_reason():
    assert dp.HOST_FENCE_RULE["on"] is True and dp.HOST_FENCE_KIND == "host_fence"
    assert dp.HOST_FENCE_KIND in dp.NO_CALL_KINDS and dp.HOST_FENCE_REASON == REASON
    assert dp.ROLE_ENV == "SP_EXPORTS_MIRROR_ROLE"          # addendum 45 P1's setting, not SP_WRITER_OF_RECORD
    src = (Path(__file__).resolve().parents[1] / "deploy" / "hosting" / "closing.py").read_text()
    assert 'ROLE_SETTING = "SP_EXPORTS_MIRROR_ROLE"' in src  # the closing watch reads the same setting


def test_two_mis_keyed_clubs_under_role_host_are_pass_host_fence(role):
    """The ruled test: under role host, PASS host_fence with the ruled reason; rating_source and every model number
    stay as they are; no order, no exec block, no value shadow, no shadow units."""
    role("laptop")
    lap, _ = annotate(mun_ful())
    assert lap[410001]["call"] == "PLAY" and lap[410001]["units"] == 1 and lap[410001]["order"]["text"]
    role("host")
    rows = [mun_ful()]
    before = copy.deepcopy(rows[0])
    desk, doc = annotate(*rows)
    d = desk[410001]
    assert (d["call"], d["units"], d["pass_kind"], d["reason"]) == ("PASS", 0, "host_fence", REASON)
    assert d["reasons"] == [REASON] and d["tags"] == ["host_fence"] and d["edge_pp"] is None
    assert d["order"] is None and d["exec"] is None and d["value_shadow"] is None and d["shadow_units"] == 0
    assert d["engine"] == "model_edge" and d["model_p"] == 0.56 == lap[410001]["model_p"]   # the model number stays
    out = {k: v for k, v in doc["predictions"][0].items() if k != "desk"}
    assert out == before                                     # rating_source, probabilities, factor_breakdown untouched
    assert out["input_quality"]["rating_source"] == {"home": "model", "away": "model"}
    assert doc["desk_meta"]["host_fence_rule"] is True and dp.machine_role() == "host"
    assert "machine_role" not in doc["desk_meta"]          # the role would part every laptop/host desk file


def test_under_role_laptop_and_role_unset_the_row_is_unchanged(role):
    role(None)
    unset, doc_unset = annotate(mun_ful(), cov_mci_value(), cov_mci_ladder())
    role("laptop")
    lap, doc_lap = annotate(mun_ful(), cov_mci_value(), cov_mci_ladder())
    with dp.host_fence_rule_off():
        role("host")
        off, _ = annotate(mun_ful(), cov_mci_value(), cov_mci_ladder())
    assert unset == lap == off
    assert lap[410001]["call"] == "PLAY" and lap[410003]["call"] == "LADDER"
    assert lap[410002]["call"] == "PASS" and lap[410002]["value_shadow"]["side"] == "DRAW"
    assert all(d["pass_kind"] != "host_fence" for d in lap.values())
    assert doc_unset["desk_meta"] == doc_lap["desk_meta"]       # the same file on either machine
    assert dp.machine_role() == "host" and dp.machine_role({}) is None
    assert dp.machine_role({dp.ROLE_ENV: "laptop"}) == "laptop"


@pytest.mark.parametrize("value", ["", "HOST", "Host", "hosts", "writer", "laptop-host", "1"])
def test_a_role_that_is_not_exactly_host_does_not_fence(role, value):
    """Unset or invalid: no fence (the reading posted on #410). Case and spelling are not guessed; surrounding
    whitespace is stripped, as closing.mirror_role() strips it."""
    role("laptop")
    lap, _ = annotate(mun_ful())
    role(value)
    desk, doc = annotate(mun_ful())
    assert desk == lap and dp.machine_role() is None
    role("  host\n")
    desk, _ = annotate(mun_ful())
    assert desk[410001]["pass_kind"] == "host_fence"


def test_host_env_is_read_first_so_a_hand_run_on_the_host_is_fenced(role, tmp_path, monkeypatch):
    """#410 review (P1): a closing-run typed by hand on the host (the P8 rehearsal, under sudo) has no EnvironmentFile.
    closing.mirror_role() finds host in host.env (sp_common.setting: the environment, then host.env) and signs its page
    "machine: host", while its export step's environment carries no role, or the laptop's role from the checkout's
    .env (install --replace copies the laptop's; config.py's load_dotenv reads it). The Desk reads host.env first, so
    that export is fenced too."""
    import closing
    host_env = tmp_path / "host.env"
    host_env.write_text("SP_WRITER_OF_RECORD=laptop\nSP_EXPORTS_MIRROR_ROLE=host\n")
    monkeypatch.setenv("SP_HOST_ENV", str(host_env))
    monkeypatch.setattr(closing.c, "HOST_ENV", host_env)
    role(None)
    assert closing.mirror_role() == "host" and closing.machine_line() == "machine: host"
    assert dp.machine_role() == "host"
    desk, _ = annotate(mun_ful())
    assert (desk[410001]["call"], desk[410001]["pass_kind"], desk[410001]["reason"]) == ("PASS", "host_fence", REASON)
    role("laptop")                                           # the checkout's .env, copied from the laptop
    desk, _ = annotate(mun_ful())
    assert dp.machine_role() == "host" and desk[410001]["pass_kind"] == "host_fence"
    env = {k: v for k, v in os.environ.items() if k != dp.ROLE_ENV}      # sp_run.run_step's child: {**os.environ}
    out = subprocess.run([sys.executable, "-c", "from src.walters import desk_policy as dp; print(dp.machine_role())"],
                         cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "host"


def test_without_a_role_in_host_env_the_environment_decides(role, tmp_path, monkeypatch):
    """A host.env with no role line, or one that is not host or laptop, does not decide: the environment does. A
    machine with no host.env (the laptop, CI: conftest's SP_HOST_ENV names no file) reads the environment alone."""
    role("laptop")
    lap, _ = annotate(mun_ful())
    host_env = tmp_path / "host.env"
    monkeypatch.setenv("SP_HOST_ENV", str(host_env))
    for text in ("SP_WRITER_OF_RECORD=laptop\n", "SP_EXPORTS_MIRROR_ROLE=HOST\n", "SP_EXPORTS_MIRROR_ROLE=\n"):
        host_env.write_text(text)
        role("laptop")
        desk, _ = annotate(mun_ful())
        assert desk == lap and dp.machine_role() == "laptop", text
        role("host")
        desk, _ = annotate(mun_ful())
        assert desk[410001]["pass_kind"] == "host_fence" and dp.machine_role() == "host", text
        role(None)
        assert dp.machine_role() is None, text
    host_env.write_text("SP_EXPORTS_MIRROR_ROLE=laptop\n")   # host.env's own word wins over the environment
    role("host")
    assert dp.machine_role() == "laptop" and annotate(mun_ful())[0] == lap


def test_the_switch_off_under_role_host_restores_the_call(role):
    role("laptop")
    lap, _ = annotate(mun_ful())
    role("host")
    with dp.host_fence_rule_off():
        off, doc = annotate(mun_ful())
    assert off == lap and off[410001]["call"] == "PLAY"
    assert doc["desk_meta"]["host_fence_rule"] is False and dp.machine_role() == "host"
    assert dp.HOST_FENCE_RULE["on"] is True


def test_the_fence_comes_first_and_overrides_every_call_and_every_other_kind(role):
    """A LADDER, a value shadow, a default rating, a shadow league and a started game: under role host each soccer
    model row is host_fence (checked first), with no order, exec block or value shadow."""
    rows = [mun_ful(), cov_mci_value(), cov_mci_ladder(),
            pl(410004, "Leeds", "Arsenal", (None, "PL"), (0.56, 0.24, 0.20), (0.50, 0.27, 0.23),
               src=("default", "model")),
            pl(410005, "Sevilla", "Betis", ("PD", "PD"), (0.56, 0.24, 0.20), (0.50, 0.27, 0.23), comp="PD"),
            pl(410006, "Everton", "Brentford", ("PL", "PL"), (0.56, 0.24, 0.20), (0.50, 0.27, 0.23),
               utc="2026-10-17T14:00:00")]
    role("laptop")
    lap, _ = annotate(*rows)
    assert [lap[m]["pass_kind"] for m in (410004, 410005, 410006)] == ["default_rating", "shadow_league", "started"]
    role("host")
    desk, doc = annotate(*rows)
    for mid, d in desk.items():
        assert (d["call"], d["units"], d["pass_kind"], d["reason"]) == ("PASS", 0, "host_fence", REASON), mid
        assert d["order"] is None and d["exec"] is None and d["value_shadow"] is None and d["shadow_units"] == 0
    parlays = dp.parlays_doc([("soccer.json", {"sport": "soccer", "predictions": copy.deepcopy(rows)})], now=NOW)
    assert parlays["live_legs"] == 0 and parlays["tickets"] == []           # never a parlay leg


def test_other_sports_and_market_only_rows_are_untouched_under_role_host(role):
    """Only soccer model rows are fenced: an MLB and an NFL model row, and a soccer market-only fixtures file (the
    venue engine, not model_edge), read the same under role host as under role laptop."""
    mlb = {"match_id": 501, "home_team": "Cleveland Guardians", "away_team": "Tampa Bay Rays",
           "utc_date": "2026-10-18T00:00:00", "competition": "MLB", "stage": "postseason",
           "prediction": {"probabilities": {"home_win": 0.61, "draw": None, "away_win": 0.39}, "tier": "lean"},
           "market": {"bookmaker_count": 9, "fair_prob": {"HOME": 0.56, "AWAY": 0.44}}}
    nfl = {"match_id": 601, "home_team": "Kansas City Chiefs", "away_team": "Buffalo Bills",
           "utc_date": "2026-10-18T20:25:00", "competition": "NFL",
           "prediction": {"home_win_prob": 0.62, "tier": "lean"},
           "market": {"bookmaker_count": 9, "fair_prob": {"HOME": 0.56, "AWAY": 0.44}}}
    fixtures = {"sport": "soccer", "competition": "EFL", "fixtures": [
        {"match_id": 701, "home_team": "Wrexham", "away_team": "Stoke", "utc_date": "2026-10-18T14:00:00",
         "status": "scheduled",
         "market": {"bookmaker_count": 6, "captured_at": "2026-10-17T14:30:00",
                    "fair_prob": {"HOME": 0.45, "DRAW": 0.28, "AWAY": 0.27}},
         "kalshi": {"status": "two_sided", "prob": {"HOME": 0.38, "DRAW": 0.30, "AWAY": 0.32}}}]}
    out = {}
    for who in ("laptop", "host"):
        role(who)
        m, _ = annotate(mlb, sport="mlb")
        n, _ = annotate(nfl, sport="nfl")
        f = copy.deepcopy(fixtures)
        dp.annotate(f, now=NOW)
        out[who] = (m, n, f["fixtures"][0]["desk"])
    assert out["host"] == out["laptop"]
    assert out["host"][0][501]["call"] == "PLAY" and out["host"][1][601]["call"] == "PLAY"
    assert out["host"][2]["engine"] == "venue_edge" and out["host"][2]["pass_kind"] != "host_fence"


def test_the_window_card_copies_the_fence_and_the_pager_reads_pass(role, tmp_path):
    """The card copies each row's Desk call from the export on disk (window.canonical_models); the pager's row reads
    it. A fenced row is PASS 0u there: no staked call reaches the host pager. The model numbers ride along."""
    texts = {}
    for who in ("laptop", "host"):
        role(who)
        d = tmp_path / who
        d.mkdir()
        doc = {"sport": "soccer", "exported_at": "2026-10-17T15:00:00", "predictions": [mun_ful()]}
        dp.annotate(doc, now=NOW)
        (d / "soccer_PL_2026-10-17_to_2026-10-24.json").write_text(json.dumps(doc))
        m = window.canonical_models(d)[410001]
        assert m["p"]["HOME"] == 0.56 and m["rating_source"] == {"home": "model", "away": "model"}
        card_row = {"match_id": 410001, "home_team": "Manchester United", "away_team": "Fulham",
                    "home_short": "MUN", "away_short": "FUL", "sport": "soccer", "competition": "PL",
                    "utc_date": "2026-10-18T15:30:00", "status": "scheduled",
                    "market": {"fair_prob": {"HOME": 0.50, "DRAW": 0.27, "AWAY": 0.23}}, "kalshi": None,
                    "tier": m["tier"], "quarantine": False, "venue_flag": None, "edge_pp": 6.0,
                    "engine": "model_edge", "model": m}
        g = page.snapshot({"fixtures": [card_row]})["410001"]
        texts[who] = (m["desk"], page.row_text(g))
    lap_desk, lap_text = texts["laptop"]
    host_desk, host_text = texts["host"]
    assert lap_desk["call"] == "PLAY" and "PLAY 1u" in lap_text
    assert (host_desk["call"], host_desk["units"], host_desk["pass_kind"]) == ("PASS", 0, "host_fence")
    assert "PASS" in host_text and "PLAY" not in host_text and "model MUN 56.0%" in host_text


def test_the_frozen_golden_holds_under_role_host(role):
    """base_v11() holds the fence off, so the golden battery (tests/test_desk_golden.py) passes whatever the
    machine's role; it runs with the role unset in CI."""
    import desk_battery as b
    role("host")
    results = b.check_against_golden()
    assert results and all(n > 0 and not bad for _, n, bad in results)
    assert dp.HOST_FENCE_RULE["on"] is True
