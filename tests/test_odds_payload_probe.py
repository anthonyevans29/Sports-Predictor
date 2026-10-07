"""scripts/odds_payload_probe.py (ARCHITECT 2026-10-07, venue-edge quote age, step 1): read-only. Every field of
the odds response is listed, time-like keys are named from the keys PRESENT, the adapter's dropped paths are
listed, and --out writes under exports/ only. The payload here is SYNTHETIC (shaped like what list_odds reads,
plus invented extra keys) — it is not a claim about the provider's payload; the operator's live run is."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("odds_payload_probe", ROOT / "scripts" / "odds_payload_probe.py")
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)

SYNTH = {
    "get": "odds", "parameters": {"game": "123"}, "errors": [], "results": 1,
    "response": [{
        "game": {"id": 123}, "league": {"id": 57, "season": 2026},
        "synthetic_refreshed": "2026-10-06T17:02:11+00:00",          # a date-time VALUE under a non-time name
        "bookmakers": [
            {"id": i, "name": f"Book{i}", "lastUpdate": "2026-10-06T16:00:00Z",   # invented time-like NAME
             "bets": [{"id": 1, "name": "Home/Away",
                       "values": [{"value": "Home", "odd": "2.10"}, {"value": "Away", "odd": "1.75"}]}]}
            for i in range(6)],
    }],
}


def test_walk_lists_every_path_with_types_and_scans_every_element():
    f = P.walk(SYNTH, max_items=2)
    assert f["response[].bookmakers"]["list_len"] == 6
    assert f["response[].bookmakers[].name"]["count"] == 6                  # EVERY element scanned (Codex #340)
    assert len(f["response[].bookmakers[].name"]["samples"]) == 2           # max_items caps the printed samples
    assert f["response[].bookmakers[].bets[].values[].odd"]["types"] == {"str"}
    assert f["results"]["types"] == {"int"} and f["errors"]["types"] == {"list"}
    assert "response[].league.season" in f and "parameters.game" in f


def test_time_fields_are_named_from_the_keys_present_and_values_that_look_like_dates():
    tf = P.time_fields(P.walk(SYNTH))
    assert tf["by_name"] == ["response[].bookmakers[].lastUpdate"]
    assert set(tf["by_value"]) == {"response[].bookmakers[].lastUpdate", "response[].synthetic_refreshed"}
    assert P.time_fields(P.walk({"response": [{"bookmakers": []}]})) == {"by_name": [], "by_value": []}


def test_dropped_paths_are_the_ones_list_odds_never_reads():
    dr = P.dropped(P.walk(SYNTH))
    assert "response[].bookmakers[].lastUpdate" in dr and "response[].synthetic_refreshed" in dr
    assert "response[].bookmakers[].bets[].values[].odd" not in dr and "response[].bookmakers[].name" not in dr
    assert "response[].bookmakers[].bets[].id" in dr


def test_report_verdict_names_a_dropped_time_field_or_says_none():
    text = "\n".join(P.report(SYNTH))
    assert "VERDICT (this payload): a time-like field is present and dropped" in text
    assert "response[].bookmakers[].lastUpdate" in text
    bare = {"response": [{"bookmakers": [{"name": "B", "bets": [{"name": "Home/Away",
                                                                  "values": [{"value": "Home", "odd": "2.1"}]}]}]}]}
    assert "no time-like field present in this payload" in "\n".join(P.report(bare))


def test_an_empty_odds_response_is_inconclusive_never_a_no_field_verdict():
    # Codex on #340: odds not yet published ({"results": 0, "response": []}) or bookmakers with no bet values say
    # nothing about the schema
    for empty in ({"errors": [], "results": 0, "response": []},
                  {"response": [{"bookmakers": [{"name": "B", "bets": []}]}]}):
        text = "\n".join(P.report(empty))
        assert "VERDICT (this payload): INCONCLUSIVE" in text and "no time-like field present" not in text


def test_camel_case_ts_keys_are_time_like_but_bets_is_not():
    # Codex on #340: quoteTs / oddsTs are timestamps (often numeric, so the value check misses them)
    payload = {"response": [{"bookmakers": [{"name": "B", "quoteTs": 1759766400, "bets": [
        {"name": "Home/Away", "values": [{"value": "Home", "odd": "2.1"}]}]}], "results": 1}]}
    tf = P.time_fields(P.walk(payload, 3))
    assert "response[].bookmakers[].quoteTs" in tf["by_name"]
    assert not any(p.endswith(("bets", "results")) for p in tf["by_name"])
    assert "dropped by the adapter: response[].bookmakers[].quoteTs" in "\n".join(P.report(payload))


def test_from_file_mode_prints_and_out_is_confined_to_exports(tmp_path, monkeypatch, capsys):
    src = tmp_path / "payload.json"
    src.write_text(json.dumps(SYNTH))
    assert P.main(["--from-file", str(src)]) == 0
    assert "TIME-LIKE KEY NAMES" in capsys.readouterr().out
    assert P.main(["--from-file", str(src), "--out", str(P.DATA / "probe.json")]) == 2
    assert "never write under data/" in capsys.readouterr().out
    assert P.main(["--from-file", str(src), "--out", str(tmp_path / "x.json")]) == 2
    assert "must be under exports/" in capsys.readouterr().out
    monkeypatch.setattr(P, "EXPORTS", tmp_path / "exports")                 # a stand-in exports/ for the write
    out = tmp_path / "exports" / "probe_nhl.json"
    assert P.main(["--from-file", str(src), "--out", str(out)]) == 0
    assert json.loads(out.read_text()) == SYNTH


def test_live_mode_needs_sport_and_game(capsys):
    assert P.main(["--sport", "nhl"]) == 2
    assert "REFUSED" in capsys.readouterr().out


def test_redact_hides_the_key():
    assert P.redact("x-apisports-key: abcdef123", "abcdef123") == "x-apisports-key: [REDACTED]"


@pytest.mark.parametrize("sport,mod", [("nhl", "src.adapters.api_hockey"),
                                       ("ncaa", "src.adapters.api_american_football")])
def test_the_probe_targets_the_adapter_the_sync_uses(sport, mod):
    import importlib
    m = importlib.import_module(mod)
    assert P.SPORTS[sport][0] == mod and hasattr(m, P.SPORTS[sport][1]) and m.DIRECT_BASE.startswith("https://")


# ---- Codex on #340 -------------------------------------------------------------------------------------------

LATE = {"errors": [], "response": [{"bookmakers": [
    {"id": i, "name": f"Book{i}", "bets": [{"name": "Home/Away", "values": [
        {"value": "Home", "odd": "2.10"}, {"value": "Away", "odd": "1.75",
                                          **({"stamp_late": "2026-10-06T16:00:00Z"} if i == 5 else {})}]}],
     **({"lastRefresh": "2026-10-06T16:00:00Z"} if i == 5 else {})}
    for i in range(6)]}]}


def test_a_time_field_only_in_a_late_list_item_is_found_with_max_items_1():
    f = P.walk(LATE, max_items=1)
    assert "response[].bookmakers[].lastRefresh" in f and "response[].bookmakers[].bets[].values[].stamp_late" in f
    tf = P.time_fields(f)
    assert tf["by_name"] == ["response[].bookmakers[].bets[].values[].stamp_late",
                             "response[].bookmakers[].lastRefresh"]
    assert set(tf["by_value"]) == set(tf["by_name"])
    text = "\n".join(P.report(LATE, max_items=1))
    assert "a time-like field is present and dropped" in text and "lastRefresh" in text
    assert "no time-like field present" not in text


def test_a_date_value_after_the_sample_cap_is_still_seen():
    doc = {"response": [{"tag": "a"}, {"tag": "b"}, {"tag": "c"}, {"tag": "2026-10-06T16:00:00Z"}]}
    f = P.walk(doc, max_items=2)
    assert f["response[].tag"]["samples"] == ["a", "b"] and P.time_fields(f)["by_value"] == ["response[].tag"]


class _Resp:
    def __init__(self, status, body=None, raw=False):
        self.status_code, self._body, self._raw, self.headers = status, body, raw, {}

    def json(self):
        if self._raw:
            raise ValueError("not json")
        return self._body


@pytest.mark.parametrize("resp,needle", [
    (_Resp(401, {"message": "Invalid key abcdef123"}), "HTTP 401"),
    (_Resp(429, {"message": "Too many requests"}), "HTTP 429"),
    (_Resp(503, raw=True), "HTTP 503"),
    (_Resp(200, raw=True), "not JSON"),
    (_Resp(200, {"errors": {"token": "Error/Missing application key"}, "response": []}), "returned errors"),
    (_Resp(200, {"errors": ["rate limit"], "response": []}), "returned errors"),
    (_Resp(200, ["not", "an", "object"]), "not a JSON object"),
])
def test_unsuccessful_responses_are_refused_by_the_adapters_checks(resp, needle):
    with pytest.raises(P.Refused) as e:
        P.check_response(resp, "abcdef123")
    assert needle in str(e.value) and "abcdef123" not in str(e.value)


def test_a_successful_response_passes():
    assert P.check_response(_Resp(200, SYNTH)) == SYNTH
    assert P.check_response(_Resp(200, {"errors": {}, "response": []})) == {"errors": {}, "response": []}


def test_live_refusal_exits_2_with_reason_and_no_verdict(monkeypatch, capsys):
    def boom(sport, game):
        raise P.Refused("REFUSED: HTTP 401 — an unsuccessful response; no verdict")
    monkeypatch.setattr(P, "fetch", boom)
    assert P.main(["--sport", "nhl", "--game", "1"]) == 2
    out = capsys.readouterr().out
    assert "HTTP 401" in out and "VERDICT" not in out and "FIELDS" not in out


def test_from_file_with_errors_is_refused_without_a_verdict(tmp_path, capsys):
    src = tmp_path / "err.json"
    src.write_text(json.dumps({"errors": {"requests": "You have reached the request limit"}, "response": []}))
    assert P.main(["--from-file", str(src)]) == 2
    out = capsys.readouterr().out
    assert "returned errors" in out and "VERDICT" not in out


def test_preflight_and_missing_key_refusals_exit_2(monkeypatch, capsys):
    # Codex on #340: SystemExit(str) exits 1; every refusal goes through Refused -> exit 2.
    def no_match(sport, match_id):
        raise P.Refused(f"REFUSED: match {match_id} not in the DB")
    monkeypatch.setattr(P, "game_for_match", no_match)
    assert P.main(["--sport", "nhl", "--match-id", "999999"]) == 2
    assert "REFUSED: match 999999 not in the DB" in capsys.readouterr().out

    def no_key(sport, game):
        raise P.Refused("REFUSED: no provider key in env/.env for this adapter — nothing fetched")
    monkeypatch.setattr(P, "fetch", no_key)
    assert P.main(["--sport", "nhl", "--game", "1"]) == 2
    out = capsys.readouterr().out
    assert "no provider key" in out and "VERDICT" not in out


def test_no_bare_systemexit_refusals_remain():
    src = Path(P.__file__).read_text()
    assert "raise SystemExit" not in src


def test_an_unreadable_from_file_is_a_refusal(tmp_path, capsys):
    # Codex on #340: a missing or truncated --from-file exits 2 with the reason, never a traceback / exit 1.
    trunc = tmp_path / "t.json"
    trunc.write_text('{"response": [')
    for path in (tmp_path / "missing.json", trunc):
        assert P.main(["--from-file", str(path)]) == 2
        out = capsys.readouterr().out
        assert "REFUSED: cannot read --from-file" in out and "VERDICT" not in out


def test_a_transport_failure_is_a_refusal(monkeypatch, capsys):
    # Codex on #340: DNS / TLS / connection / timeout errors raise before check_response; they exit 2, key redacted.
    import sys
    import types

    import requests
    fake = types.ModuleType("fake_probe_adapter")
    fake.DIRECT_BASE = "https://example.invalid"

    class Ad:
        _headers = {"x-apisports-key": "SECRETKEY123"}
    fake.Ad = Ad
    monkeypatch.setitem(sys.modules, "fake_probe_adapter", fake)
    monkeypatch.setitem(P.SPORTS, "nhl", ("fake_probe_adapter", "Ad", "sync-odds --competition NHL", "api_hockey"))

    def down(*a, **k):
        raise requests.ConnectionError("cannot reach host with key SECRETKEY123")
    monkeypatch.setattr(requests, "get", down)
    with pytest.raises(P.Refused) as e:
        P.fetch("nhl", "1")
    assert "ConnectionError" in str(e.value) and "SECRETKEY123" not in str(e.value)
    assert P.main(["--sport", "nhl", "--game", "1"]) == 2
    out = capsys.readouterr().out
    assert "REFUSED: the request to https://example.invalid/odds failed" in out and "VERDICT" not in out
    assert "SECRETKEY123" not in out
