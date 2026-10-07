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


def test_walk_lists_every_path_with_types_and_truncates_lists():
    f = P.walk(SYNTH, max_items=2)
    assert f["response[].bookmakers"]["list_len"] == 6
    assert f["response[].bookmakers[].name"]["count"] == 2                  # descended 2 of 6
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
    bare = {"response": [{"bookmakers": [{"name": "B", "bets": []}]}]}
    assert "no time-like field present in this payload" in "\n".join(P.report(bare))


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
