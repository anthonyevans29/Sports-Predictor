"""ARCHITECT 2026-10-30 11:20 ET, addendum 182 item 4 (#732, Desk policy v1.2): "compare_exports masks the unit-bearing
fields — order.unit, order.text, order.contracts, desk_meta.unit (and the laptop-only pool field wherever it appears) —
compares the rest, and prints the masked count ("unit-bearing fields masked (policy v1.2): N"); a divergence in exec
figures from fee rounding is real and still prints (no dollar in it)." Synthetic figures only (FIXTURE_*): each machine
reads its own pool, so these fields differ by construction and are never printed."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))
import compare_exports as ce  # noqa: E402

DAY = "2026-11-08"
FIXTURE_LAPTOP_UNIT, FIXTURE_HOST_UNIT = "1u = $FIXTURE-A", "1u = $FIXTURE-B"
FIXTURE_LAPTOP_POOL, FIXTURE_HOST_POOL = "FIXTURE-POOL-A", "FIXTURE-POOL-B"


def doc(unit, contracts, pool, edge=4.1):
    order = {"unit": unit, "text": f"BUY YES T-FIX @ 0.55 × {contracts}", "contracts": contracts, "limit": 0.55}
    return {"desk_meta": {"policy_version": "v1.2", "unit": {"state": "read", "label": unit, "pool_usd": pool}},
            "predictions": [{"utc_date": f"{DAY}T18:00:00Z", "home_team": "Home FC", "away_team": "Away FC",
                             "desk": {"call": "PLAY", "units": 1, "order": order,
                                      "exec": {"edge_pp": edge, "contracts": contracts}}}]}


def run(tmp_path, capsys, laptop, host, *extra):
    la, ho = tmp_path / "laptop", tmp_path / "host"
    for d, body in ((la, laptop), (ho, host)):
        d.mkdir(parents=True)
        (d / f"closing_NFL_{DAY}.json").write_text(json.dumps(body))
    rc = ce.main([str(la), str(ho), "--since", "0", *extra])
    return rc, capsys.readouterr().out


def test_the_unit_bearing_fields_are_masked_counted_and_never_printed(tmp_path, capsys):
    rc, out = run(tmp_path, capsys, doc(FIXTURE_LAPTOP_UNIT, 11, FIXTURE_LAPTOP_POOL),
                  doc(FIXTURE_HOST_UNIT, 22, FIXTURE_HOST_POOL))
    for secret in (FIXTURE_LAPTOP_UNIT, FIXTURE_HOST_UNIT, FIXTURE_LAPTOP_POOL, FIXTURE_HOST_POOL, "BUY YES"):
        assert secret not in out, secret
    # masked: order.unit, order.text, order.contracts (3) + desk_meta.unit (1) = 4 (pool_usd sits inside desk_meta.unit)
    assert "unit-bearing fields masked (policy v1.2): 4" in out
    # the exec figures are compared: the fee basis's contract count differs, a real divergence with no dollar in it
    assert "$.predictions[" in out and ".desk.exec.contracts: '11' vs '22'" in out
    assert out.rstrip().splitlines()[-1] == "VERDICT: DIVERGENT" and rc == ce.EXIT_DIVERGENT


def test_only_the_unit_bearing_fields_differ_reads_clean(tmp_path, capsys):
    a, b = doc(FIXTURE_LAPTOP_UNIT, 11, FIXTURE_LAPTOP_POOL), doc(FIXTURE_HOST_UNIT, 22, FIXTURE_HOST_POOL)
    for d in (a, b):
        d["predictions"][0]["desk"]["exec"]["contracts"] = 10        # the same fee basis on both sides
    rc, out = run(tmp_path, capsys, a, b)
    assert "unit-bearing fields masked (policy v1.2): 4" in out
    assert out.rstrip().splitlines()[-1] == "VERDICT: CLEAN" and rc == ce.EXIT_CLEAN


def test_the_pool_field_is_masked_at_any_depth_and_in_the_ignore_keys_mode(tmp_path, capsys):
    a, b = doc(FIXTURE_LAPTOP_UNIT, 10, FIXTURE_LAPTOP_POOL), doc(FIXTURE_HOST_UNIT, 10, FIXTURE_HOST_POOL)
    a["predictions"][0]["pool_usd"], b["predictions"][0]["pool_usd"] = FIXTURE_LAPTOP_POOL, FIXTURE_HOST_POOL
    rc, out = run(tmp_path, capsys, a, b, "--ignore-keys", "utc_date")
    for secret in (FIXTURE_LAPTOP_UNIT, FIXTURE_HOST_UNIT, FIXTURE_LAPTOP_POOL, FIXTURE_HOST_POOL):
        assert secret not in out, secret
    assert "unit-bearing fields masked (policy v1.2): 5" in out


def test_a_v1_1_file_with_no_unit_fields_masks_nothing(tmp_path, capsys):
    plain = {"predictions": [{"utc_date": f"{DAY}T18:00:00Z", "home_team": "Home FC", "away_team": "Away FC", "p": 0.5}]}
    rc, out = run(tmp_path, capsys, plain, plain)
    assert "unit-bearing fields masked (policy v1.2): 0" in out and rc == ce.EXIT_CLEAN


def test_a_key_named_unit_or_text_elsewhere_is_still_compared():
    out = ce.diff({"x": {"unit": "a", "text": "b"}}, {"x": {"unit": "c", "text": "d"}})
    assert out == ["$.x.text: 'b' vs 'd'", "$.x.unit: 'a' vs 'c'"]


def test_an_order_against_null_is_printed_redacted(tmp_path, capsys):
    """Codex on #735 (P1): a PLAY on one side and a PASS (desk.order null, desk_meta null) on the other formats the
    whole object; its unit-bearing values are redacted first, and still counted."""
    a, b = doc(FIXTURE_LAPTOP_UNIT, 11, FIXTURE_LAPTOP_POOL), doc(FIXTURE_HOST_UNIT, 11, FIXTURE_HOST_POOL)
    b["predictions"][0]["desk"]["order"] = None
    a["desk_meta"] = {"unit": a["desk_meta"]["unit"]}
    b["desk_meta"] = None
    rc, out = run(tmp_path, capsys, a, b)
    for secret in (FIXTURE_LAPTOP_UNIT, FIXTURE_HOST_UNIT, FIXTURE_LAPTOP_POOL, FIXTURE_HOST_POOL, "BUY YES", "× 11"):
        assert secret not in out, secret
    assert ".desk.order: \"{'unit': '<masked>', 'text': '<masked>', 'contracts': '<mask" in out   # cut at 60
    assert "$.desk_meta: \"{'unit': '<masked>'}\" vs 'None'" in out
    assert "unit-bearing fields masked (policy v1.2): 4" in out and rc == ce.EXIT_DIVERGENT


def test_the_redaction_reaches_the_pool_field_at_any_depth():
    assert ce.redacted({"a": [{"pool_usd": "FIXTURE-POOL-A", "b": 1}]}) == {"a": [{"pool_usd": "<masked>", "b": 1}]}
    assert ce.diff({"x": {"pool_usd": "FIXTURE-POOL-A"}}, {"x": None}) == ["$.x: \"{'pool_usd': '<masked>'}\" vs 'None'"]


def test_the_count_reaches_past_the_diff_output_limit(tmp_path, capsys):
    """Codex on #735 (P2): 41 earlier differing keys fill the 40-line output before a later order is visited."""
    a, b = doc(FIXTURE_LAPTOP_UNIT, 10, FIXTURE_LAPTOP_POOL), doc(FIXTURE_HOST_UNIT, 10, FIXTURE_HOST_POOL)
    for i in range(41):
        a[f"a{i:02d}"], b[f"a{i:02d}"] = 0, 1
    a["zz"], b["zz"] = {"order": {"unit": FIXTURE_LAPTOP_UNIT}}, {"order": {"unit": FIXTURE_HOST_UNIT}}
    rc, out = run(tmp_path, capsys, a, b)
    assert "unit-bearing fields masked (policy v1.2): 5" in out and rc == ce.EXIT_DIVERGENT


def test_the_count_reaches_under_ignored_keys(tmp_path, capsys):
    """Codex on #735 (P2): the cutover's documented --ignore-keys desk,desk_meta,... prunes both subtrees; their
    unit-bearing fields are still counted (the count is the files', the same in both modes)."""
    a, b = doc(FIXTURE_LAPTOP_UNIT, 10, FIXTURE_LAPTOP_POOL), doc(FIXTURE_HOST_UNIT, 10, FIXTURE_HOST_POOL)
    rc, out = run(tmp_path, capsys, a, b, "--ignore-keys", "desk,desk_meta,line_move,late_news_flag")
    assert "unit-bearing fields masked (policy v1.2): 4" in out and rc == ce.EXIT_CLEAN


def test_rows_on_one_side_count_their_unit_fields_once_per_field():
    row = doc(FIXTURE_LAPTOP_UNIT, 10, FIXTURE_LAPTOP_POOL)["predictions"][0]
    other = {**row, "home_team": "Other FC"}
    assert ce.unit_count({"p": [row]}, {"p": [row, other]}) == 6
