"""THE HOST FENCE (ARCHITECT 2026-10-17 10:15 ET, addendum 109 item 3, RULED; #410), verbatim: "when the
writer-of-record role is host, every soccer model_edge row is PASS, pass_kind "host_fence", reason "host: ratings keyed
to the laptop's team ids (#410); the cutover replaces this database". rating_source is untouched; the row's model
numbers stay in the file for the compare. The host pager never sees a soccer PLAY from the host. Test: a
two-mis-keyed-clubs fixture under role host → PASS host_fence; under role laptop → unchanged. The fence lifts with the
cutover (the ruling that cuts over names it). No re-keying on the host (addendum 36 stands)."
THE ROLE (addendum 110 item 1, RULED), verbatim: "#410 host fence — Code's reading is right and is the ruling: the
fence keys off the machine's own role, SP_EXPORTS_MIRROR_ROLE=host (addendum 45 P1), not SP_WRITER_OF_RECORD, which
reads laptop on both machines until the cutover flips it. Lift through a named switch the cutover PR turns off. ONE
FLIP (law 4, conservative unknowns): an unknown or missing role is FENCED, not open. A machine that cannot say it is the
laptop does not get to make a soccer call. Reason text for that case: "host fence: role unknown (SP_EXPORTS_MIRROR_ROLE
unset)". The laptop's .env carries the role line (the morning block checks it every day), so the laptop is never caught
by it. Tests: role host → PASS host_fence; role laptop → unchanged; role unset → PASS host_fence (role unknown)."
Addendum 111 item 4: "The fence tests: pinning the existing soccer Desk tests to role laptop and leaving the frozen
golden untouched is right; the three ruled cases are the only new behaviour."
Addendum 114 item 3: ""Lifted by the flip" (addendum 113) and "the named switch the cutover PR turns off" (addendum
110) are the same thing: the cutover PR does the flip and turns the switch off in the same change; the fence reads the
switch, never SP_WRITER_OF_RECORD. Code's reading is the ruling."
The role is read from the machine's host.env (SP_HOST_ENV), then the environment, then the checkout's .env
(desk_policy.DOTENV). The reason for a value that is neither host nor laptop is built pending the architect's word.
tests/conftest.py pins every test to role laptop in the environment, with both files at a path that does not exist."""
import copy
import io
import json
import os
import subprocess
import sys
import tokenize
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.walters import desk_policy as dp
from src.walters import window

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))
sys.path.insert(0, str(ROOT / "scripts"))
import sp_window_page as page  # noqa: E402

REASON = "host: ratings keyed to the laptop's team ids (#410); the cutover replaces this database"   # the ruled words
UNSET = "host fence: role unknown (SP_EXPORTS_MIRROR_ROLE unset)"                   # addendum 110 item 1, verbatim
NOW = datetime(2026, 10, 17, 15, 0, tzinfo=timezone.utc)


def unknown(value):
    """The reason for a value that is neither host nor laptop (built pending the architect's word)."""
    return f"host fence: role unknown (SP_EXPORTS_MIRROR_ROLE={value})"


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


def reason(desk, mid=410001):
    d = desk[mid]
    return d["reason"] if (d["call"], d["units"], d["pass_kind"]) == ("PASS", 0, "host_fence") else None


@pytest.fixture
def role(monkeypatch):
    """The environment's role (conftest pins laptop); None deletes it."""
    def set_role(v):
        if v is None:
            monkeypatch.delenv(dp.ROLE_ENV, raising=False)
        else:
            monkeypatch.setenv(dp.ROLE_ENV, v)
    return set_role


@pytest.fixture
def files(tmp_path, monkeypatch):
    """The machine's host.env (SP_HOST_ENV) and the checkout's .env (desk_policy.DOTENV); None: no such file."""
    def write(host_env=None, dotenv=None):
        for name, text in (("host.env", host_env), (".env", dotenv)):
            p = tmp_path / name
            p.unlink(missing_ok=True)
            if text is not None:
                p.write_text(text)
        monkeypatch.setenv("SP_HOST_ENV", str(tmp_path / "host.env"))
        monkeypatch.setattr(dp, "DOTENV", tmp_path / ".env")
    return write


def test_the_rule_its_kind_and_its_reasons():
    assert dp.HOST_FENCE_RULE["on"] is True and dp.HOST_FENCE_KIND == "host_fence"
    assert dp.HOST_FENCE_KIND in dp.NO_CALL_KINDS and dp.HOST_FENCE_REASON == REASON
    assert dp.HOST_FENCE_UNSET_REASON == UNSET
    assert dp.ROLE_ENV == "SP_EXPORTS_MIRROR_ROLE"          # addendum 45 P1's setting, not SP_WRITER_OF_RECORD
    src = (ROOT / "deploy" / "hosting" / "closing.py").read_text()
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


def test_under_role_laptop_the_row_is_unchanged(role):
    """The ruled test, second case: under role laptop each call is the call without the fence (a PLAY, a LADDER, a
    value shadow). desk_meta is the same on either machine."""
    role("laptop")
    lap, doc_lap = annotate(mun_ful(), cov_mci_value(), cov_mci_ladder())
    role("host")
    with dp.host_fence_rule_off():
        off, _ = annotate(mun_ful(), cov_mci_value(), cov_mci_ladder())
    _, doc_host = annotate(mun_ful(), cov_mci_value(), cov_mci_ladder())
    assert lap == off
    assert lap[410001]["call"] == "PLAY" and lap[410003]["call"] == "LADDER"
    assert lap[410002]["call"] == "PASS" and lap[410002]["value_shadow"]["side"] == "DRAW"
    assert all(d["pass_kind"] != "host_fence" for d in lap.values())
    assert doc_host["desk_meta"] == doc_lap["desk_meta"]      # the same desk_meta on either machine
    assert dp.machine_role() == "host" and dp.machine_role({dp.ROLE_ENV: "laptop"}) == "laptop"


@pytest.mark.parametrize("value", [None, "", "   ", "\n"])
def test_under_role_unset_every_soccer_model_row_is_pass_host_fence_role_unknown(role, value):
    """The ruled test, third case (addendum 110 item 1): "role unset → PASS host_fence (role unknown)", with the ruled
    reason. An empty value is unset. The row's other fields are unchanged; no order, exec block or value shadow."""
    role(value)
    rows = [mun_ful(), cov_mci_value(), cov_mci_ladder()]
    before = copy.deepcopy(rows)
    desk, doc = annotate(*rows)
    for mid, d in desk.items():
        assert (d["call"], d["units"], d["pass_kind"], d["reason"]) == ("PASS", 0, "host_fence", UNSET), mid
        assert d["reasons"] == [UNSET] and d["tags"] == ["host_fence"] and d["edge_pp"] is None
        assert d["order"] is None and d["exec"] is None and d["value_shadow"] is None and d["shadow_units"] == 0
    assert [{k: v for k, v in r.items() if k != "desk"} for r in doc["predictions"]] == before
    assert dp.role_reading() == (None, "") and dp.machine_role() is None


@pytest.mark.parametrize("value", ["HOST", "Host", "hosts", "writer", "laptop-host", "1", "Laptop", " LAPTOP\n"])
def test_a_role_that_is_neither_host_nor_laptop_is_pass_host_fence_naming_the_value(role, value):
    """Neither host nor laptop: the role is unknown, so the row is fenced (law 4). Case and spelling are not guessed.
    The reason names the value as read, stripped (built pending the architect's word)."""
    role(value)
    desk, _ = annotate(mun_ful())
    assert reason(desk) == unknown(value.strip()) and dp.role_reading() == (None, value.strip())


def test_surrounding_whitespace_is_stripped_as_closing_mirror_role_strips_it(role):
    role("laptop")
    lap, _ = annotate(mun_ful())
    role("  laptop\n")
    assert annotate(mun_ful())[0] == lap
    role("  host\n")
    assert reason(annotate(mun_ful())[0]) == REASON


def test_the_checkouts_env_alone_says_laptop_so_a_script_without_config_is_not_fenced(role, files):
    """Addendum 110 item 1: "The laptop's .env carries the role line [...] so the laptop is never caught by it." No
    role in the environment (a script that never imports config, so load_dotenv never ran) and no host.env: the .env
    decides. The environment comes before it."""
    role("laptop")
    lap, _ = annotate(mun_ful())
    role(None)
    files(dotenv="API_FOOTBALL_KEY=x\nSP_EXPORTS_MIRROR_ROLE=laptop\n")
    assert dp.role_reading() == ("laptop", "laptop") and annotate(mun_ful())[0] == lap
    files(dotenv="SP_EXPORTS_MIRROR_ROLE=host\n")
    assert reason(annotate(mun_ful())[0]) == REASON
    files(dotenv="SP_EXPORTS_MIRROR_ROLE=Laptop\n")
    assert reason(annotate(mun_ful())[0]) == unknown("Laptop")
    for text in ("SP_EXPORTS_MIRROR_ROLE=\n", "API_FOOTBALL_KEY=x\n", None):
        files(dotenv=text)
        assert reason(annotate(mun_ful())[0]) == UNSET, text
    files(dotenv="SP_EXPORTS_MIRROR_ROLE=host\n")             # the environment comes before the .env
    role("laptop")
    assert annotate(mun_ful())[0] == lap
    files(dotenv="SP_EXPORTS_MIRROR_ROLE=laptop\n")
    role("host")
    assert reason(annotate(mun_ful())[0]) == REASON


def test_an_unreadable_file_falls_through_to_the_next_source(role, files, monkeypatch):
    """A file that cannot be read (host.env is root:sp 0640) reads as empty: the next source decides."""
    import dotenv
    real = dotenv.dotenv_values

    def guarded(path):
        if str(path).endswith("host.env"):
            raise PermissionError(13, "Permission denied", str(path))
        return real(path)
    monkeypatch.setattr(dotenv, "dotenv_values", guarded)
    files(host_env="SP_EXPORTS_MIRROR_ROLE=host\n", dotenv="SP_EXPORTS_MIRROR_ROLE=laptop\n")
    role("host")
    assert dp.role_reading() == ("host", "host")
    role(None)
    assert dp.role_reading() == ("laptop", "laptop")
    files(host_env="SP_EXPORTS_MIRROR_ROLE=host\n")
    assert dp.role_reading() == (None, "") and reason(annotate(mun_ful())[0]) == UNSET


def test_host_env_is_read_first_so_a_hand_run_on_the_host_is_fenced(role, tmp_path, monkeypatch):
    """#410 review (P1): a closing-run typed by hand on the host (the P8 rehearsal, under sudo) has no EnvironmentFile.
    closing.mirror_role() finds host in host.env (sp_common.setting: the environment, then host.env) and signs its page
    "machine: host", while its export step's environment carries no role, or the laptop's role from the checkout's
    .env (install --replace copies the laptop's; config.py's load_dotenv reads it). The Desk reads host.env first, so
    that export is fenced too: host.env's host beats the environment's laptop."""
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
    assert dp.machine_role() == "host" and reason(desk) == REASON
    env = {k: v for k, v in os.environ.items() if k != dp.ROLE_ENV}      # sp_run.run_step's child: {**os.environ}
    out = subprocess.run([sys.executable, "-c", "from src.walters import desk_policy as dp; print(dp.machine_role())"],
                         cwd=ROOT, env=env, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "host"


def test_host_env_decides_when_it_holds_a_value_and_the_environment_when_it_does_not(role, files):
    """A host.env with no role line, or an empty one, does not decide: the environment does, then the .env. A value
    there decides, valid or not: one that is neither host nor laptop is unknown, never the environment's laptop."""
    role("laptop")
    lap, _ = annotate(mun_ful())
    for text in ("SP_WRITER_OF_RECORD=laptop\n", "SP_EXPORTS_MIRROR_ROLE=\n", "SP_EXPORTS_MIRROR_ROLE=  \n"):
        files(host_env=text)
        role("laptop")
        assert annotate(mun_ful())[0] == lap and dp.machine_role() == "laptop", text
        role("host")
        assert reason(annotate(mun_ful())[0]) == REASON and dp.machine_role() == "host", text
        role(None)
        assert reason(annotate(mun_ful())[0]) == UNSET and dp.machine_role() is None, text
    files(host_env="SP_EXPORTS_MIRROR_ROLE=HOST\n")
    role("laptop")
    assert reason(annotate(mun_ful())[0]) == unknown("HOST") and dp.machine_role() is None
    files(host_env="SP_EXPORTS_MIRROR_ROLE=laptop\n")         # host.env's own word wins over the environment
    role("host")
    assert dp.machine_role() == "laptop" and annotate(mun_ful())[0] == lap


@pytest.mark.parametrize("who", ["host", None, "", "HOST", "laptop", ".env laptop", "host.env host"])
def test_the_switch_off_leaves_every_row_unchanged_under_every_role(role, files, who):
    role("laptop")
    lap, _ = annotate(mun_ful(), cov_mci_value(), cov_mci_ladder())
    if who == ".env laptop":
        role(None)
        files(dotenv="SP_EXPORTS_MIRROR_ROLE=laptop\n")
    elif who == "host.env host":
        files(host_env="SP_EXPORTS_MIRROR_ROLE=host\n")
    else:
        role(who)
    with dp.host_fence_rule_off():
        off, doc = annotate(mun_ful(), cov_mci_value(), cov_mci_ladder())
    assert off == lap and off[410001]["call"] == "PLAY"
    assert doc["desk_meta"]["host_fence_rule"] is False
    assert dp.HOST_FENCE_RULE["on"] is True


def test_the_switch_the_cutover_pr_turns_off_is_the_one_the_fence_reads(role, files, monkeypatch):
    """Addendum 114 item 3: "the cutover PR does the flip and turns the switch off in the same change; the fence reads
    the switch, never SP_WRITER_OF_RECORD." The cutover PR's line, HOST_FENCE_RULE = {"on": False}, alone lifts the
    fence under role host and role unknown. SP_WRITER_OF_RECORD, laptop or host or unset, in host.env, the environment
    or the .env, and sp_common.writer_of_record() whatever it says, change nothing; desk_policy names it nowhere in
    its code (comments aside)."""
    import sp_common
    role("laptop")
    lap, _ = annotate(mun_ful())
    for who in ("host", None, "HOST"):
        role(who)
        assert annotate(mun_ful())[0][410001]["pass_kind"] == "host_fence", who
        monkeypatch.setitem(dp.HOST_FENCE_RULE, "on", False)      # the cutover PR's change
        off, doc = annotate(mun_ful())
        assert off == lap and doc["desk_meta"]["host_fence_rule"] is False, who
        monkeypatch.setitem(dp.HOST_FENCE_RULE, "on", True)
    for wor in ("laptop", "host", None):
        line = f"SP_WRITER_OF_RECORD={wor}\n" if wor else ""
        monkeypatch.setattr(sp_common, "writer_of_record", lambda w=wor: w)
        if wor:
            monkeypatch.setenv("SP_WRITER_OF_RECORD", wor)
        else:
            monkeypatch.delenv("SP_WRITER_OF_RECORD", raising=False)
        got = {}
        for who in ("host", "laptop", None):
            role(who)
            files(host_env=line or None, dotenv=line or None)
            got[who] = reason(annotate(mun_ful())[0])
        assert got == {"host": REASON, "laptop": None, None: UNSET}, wor
    toks = list(tokenize.generate_tokens(io.StringIO(Path(dp.__file__).read_text()).readline))
    assert not [t.string for t in toks if t.type == tokenize.NAME and t.string in ("sp_common", "writer_of_record")]
    assert not [t.string for t in toks if t.type == tokenize.STRING and "WRITER_OF_RECORD" in t.string.upper()]


def test_the_env_file_the_role_falls_back_to_is_the_one_config_loads():
    """desk_policy.DOTENV is config.py's PROJECT_ROOT / ".env" (the file its load_dotenv reads), the same file as
    sp_common's REPO / ".env". Read in a fresh process: conftest points it elsewhere in this one."""
    code = ("import sys; sys.path.insert(0, 'deploy/hosting'); import config, sp_common; "
            "from src.walters import desk_policy as dp; "
            "print(dp.DOTENV == (config.PROJECT_ROOT / '.env').resolve() == (sp_common.REPO / '.env').resolve())")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "True"


@pytest.mark.parametrize("who", ["host", None])
def test_the_fence_comes_first_and_overrides_every_call_and_every_other_kind(role, who):
    """A LADDER, a value shadow, a default rating, a shadow league and a started game: under role host, or an unknown
    role, each soccer model row is host_fence (checked first), with no order, exec block or value shadow."""
    rows = [mun_ful(), cov_mci_value(), cov_mci_ladder(),
            pl(410004, "Leeds", "Arsenal", (None, "PL"), (0.56, 0.24, 0.20), (0.50, 0.27, 0.23),
               src=("default", "model")),
            pl(410005, "Sevilla", "Betis", ("PD", "PD"), (0.56, 0.24, 0.20), (0.50, 0.27, 0.23), comp="PD"),
            pl(410006, "Everton", "Brentford", ("PL", "PL"), (0.56, 0.24, 0.20), (0.50, 0.27, 0.23),
               utc="2026-10-17T14:00:00")]
    role("laptop")
    lap, _ = annotate(*rows)
    assert [lap[m]["pass_kind"] for m in (410004, 410005, 410006)] == ["default_rating", "shadow_league", "started"]
    role(who)
    why = REASON if who == "host" else UNSET
    desk, doc = annotate(*rows)
    for mid, d in desk.items():
        assert (d["call"], d["units"], d["pass_kind"], d["reason"]) == ("PASS", 0, "host_fence", why), mid
        assert d["order"] is None and d["exec"] is None and d["value_shadow"] is None and d["shadow_units"] == 0
    parlays = dp.parlays_doc([("soccer.json", {"sport": "soccer", "predictions": copy.deepcopy(rows)})], now=NOW)
    assert parlays["live_legs"] == 0 and parlays["tickets"] == []           # never a parlay leg


def test_other_sports_and_market_only_rows_are_untouched_under_role_host_and_role_unknown(role):
    """Only soccer model rows are fenced: an MLB and an NFL model row, and a soccer market-only fixtures file (the
    venue engine, not model_edge), read the same under role host and an unknown role as under role laptop."""
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
    for who in ("laptop", "host", None):
        role(who)
        m, _ = annotate(mlb, sport="mlb")
        n, _ = annotate(nfl, sport="nfl")
        f = copy.deepcopy(fixtures)
        dp.annotate(f, now=NOW)
        out[who] = (m, n, f["fixtures"][0]["desk"])
    assert out["host"] == out["laptop"] == out[None]
    assert out["host"][0][501]["call"] == "PLAY" and out["host"][1][601]["call"] == "PLAY"
    assert out["host"][2]["engine"] == "venue_edge" and out["host"][2]["pass_kind"] != "host_fence"


def test_the_window_card_copies_the_fence_and_the_pager_reads_pass(role, tmp_path):
    """The card copies each row's Desk call from the export on disk (window.canonical_models); the pager's row reads
    it. A fenced row is PASS 0u there, under role host or an unknown role: no staked call reaches the host pager. The
    model numbers ride along."""
    texts = {}
    for who in ("laptop", "host", None):
        role(who)
        d = tmp_path / str(who)
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
    assert lap_desk["call"] == "PLAY" and "PLAY 1u" in lap_text
    for who in ("host", None):
        desk, text = texts[who]
        assert (desk["call"], desk["units"], desk["pass_kind"]) == ("PASS", 0, "host_fence"), who
        assert "PASS" in text and "PLAY" not in text and "model MUN 56.0%" in text, who


def laptop_desk_file():
    """A desk file the laptop published: mun_ful() a full-unit PLAY."""
    doc = {"sport": "soccer", "predictions": [mun_ful()]}
    dp.annotate(doc, now=NOW)
    assert doc["predictions"][0]["desk"]["call"] == "PLAY" and doc["predictions"][0]["desk"]["units"] == 1
    return doc


@pytest.mark.parametrize("who, why", [("host", REASON), (None, UNSET), ("HOST", unknown("HOST"))])
def test_desk_rescore_reports_a_fenced_play_as_host_fence_never_unchanged(role, who, why):
    """#410 review: the fence is on in both of desk-rescore's sides (addendum_off holds it), so a laptop PLAY
    re-scored on a machine whose role is host or unknown is 0u on both, and 0 = 0 read "unchanged". It is its own
    transition, as the quarantine and the kalshi-only suspension are, and it carries the fence's reason."""
    role("laptop")
    doc = laptop_desk_file()
    (x,) = dp.rescore(doc)
    assert (x["published_units"], x["v11_units"], x["addendum_units"], x["addendum_call"], x["verdict"]) == \
        (1, 1, 1, "PLAY", "unchanged") and x["pass_reason"] is None
    role(who)
    (x,) = dp.rescore(doc)
    assert (x["published_units"], x["v11_units"], x["addendum_units"], x["addendum_call"], x["verdict"]) == \
        (1, 0, 0, "PASS", "host fence") and x["pass_reason"] == why
    with dp.host_fence_rule_off():                             # the switch off: the laptop's line, whatever the role
        (x,) = dp.rescore(doc)
    assert (x["v11_units"], x["addendum_units"], x["verdict"]) == (1, 1, "unchanged")


@pytest.mark.parametrize("who, why", [("host", REASON), (None, UNSET)])
def test_desk_rescore_cli_prints_host_fence_and_its_count_not_unchanged(role, tmp_path, who, why):
    """The console and the receipt name the fence and its reason (not "no executable quote": the row had a Kalshi
    ask), count it on its own line, and never as halved. On the laptop neither appears."""
    from click.testing import CliRunner

    import cli
    role("laptop")
    p = tmp_path / "soccer.json"
    p.write_text(json.dumps(laptop_desk_file()))
    out = {}
    for w in ("laptop", who):
        role(w)
        res = CliRunner().invoke(cli.cli, ["desk-rescore", str(p), "--out", str(tmp_path / f"r-{w}.md")])
        assert res.exit_code == 0, (res.output, repr(res.exception))
        out[w] = res.output
    assert "UNCHANGED" in out["laptop"] and "HOST FENCE" not in out["laptop"] and "host fence" not in out["laptop"]
    line = next(l for l in out[who].splitlines() if "Fulham @ Manchester United" in l)
    assert f"exec — (not priced: {why})" in line and line.endswith("addendum 0 · HOST FENCE")
    assert "UNCHANGED" not in out[who] and "no executable quote" not in out[who]
    assert "0 would have been halved" in out[who]
    assert ("1 soccer PLAY(s) now PASS under the host fence (this machine's role is not laptop; #410) — not counted "
            "as halved") in out[who]
    receipt = (tmp_path / f"r-{who}.md").read_text()
    assert line in receipt and "under the host fence" in receipt


@pytest.mark.parametrize("who", ["host", None])
def test_the_frozen_golden_holds_under_role_host_and_role_unknown(role, who):
    """base_v11() holds the fence off, so the golden battery (tests/test_desk_golden.py, untouched) passes whatever
    the machine's role: under role host, and with the role unset."""
    import desk_battery as b
    role(who)
    results = b.check_against_golden()
    assert results and all(n > 0 and not bad for _, n, bad in results)
    assert dp.HOST_FENCE_RULE["on"] is True
