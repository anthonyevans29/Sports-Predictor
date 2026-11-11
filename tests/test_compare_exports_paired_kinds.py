"""THE PAIRED KINDS' compared rows (ARCHITECT 2026-11-11 08:45 ET, addendum 335 item 4(b), verbatim): "only rows whose
utc_date falls on the file's yesterday, today or tomorrow — the days BOTH machines synced that day; rows outside are
counted "outside the window", never compared (the laptop has no weekly full-season sync, so later kickoffs can
legitimately differ). The host-only columns (market, kalshi*, exec_cost*, fee*, k_track, kalshi_legs, input_quality,
desk, desk_meta) are masked AND COUNTED in #735's pattern, a new key in `_fixture_row` staying visible."
And 336 item 4(1) (ARCHITECT 2026-11-11 09:35 ET), verbatim: "`away_bid`, `away_ask` and `close_unpriced` are the same
class — columns only the market machine fills — and are masked and counted with 335 item 4(b)'s list. The rule behind
the list, pinned by a test: every key `_fixture_row` writes is either compared or on the declared mask, so a new key
fails the test until it is placed — never masked by a prefix, never silently."

A fixtures_NHL row with the host's full key set (read from the mirror's host/2026-11-10/fixtures_NHL_2026-11-10.json),
against the laptop's (no market, no Kalshi, no Desk)."""
import ast
import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))
import compare_exports as ce  # noqa: E402

DAY = "2026-11-11"
NAME = f"fixtures_NHL_{DAY}.json"
BASE = {"competition": "NHL", "family": "NHL", "status": "scheduled", "stage": None, "matchday": None,
        "home_score": None, "away_score": None}
HOST_ONLY = {"market": {"fair_prob": {"HOME": 0.55, "AWAY": 0.45}}, "kalshi": {"status": "two_sided"},
             "kalshi_bid": 0.53, "kalshi_ask": 0.56, "kalshi_legs": {"HOME": {"bid": 0.53}}, "away_bid": 0.44,
             "away_ask": 0.47, "exec_cost_taker": 0.57, "exec_cost_maker": 0.56, "exec_cost_taker_away": 0.48,
             "exec_cost_maker_away": 0.47, "fee_series": "KXNHLGAME", "fee_m_taker": 1.0, "fee_m_maker": 1.0,
             "fee_order_contracts": 10, "k_track": "on", "input_quality": {"kalshi": "fresh"}, "desk": {"call": "x"}}
LAPTOP_NULLS = {k: None for k in HOST_ONLY}


def row(day_hour: str, home: str, away: str, **kw):
    return {**BASE, "match_id": 1, "utc_date": day_hour, "home_team": home, "away_team": away, **kw}


def doc(rows, side):
    d = {"competition_code": "NHL", "contains_predictions": False, "note": "Market-only fixtures file",
         "count": len(rows), "fixtures": rows, "git_sha": "abc"}
    if side == "host":
        d["desk_meta"] = {"policy_version": "v1.2", "counts": {"postseason_graded": 0}}
    return d


def run(tmp_path, capsys, lap, hos, *extra):
    la, ho = tmp_path / "laptop", tmp_path / "host"
    la.mkdir(parents=True), ho.mkdir(parents=True)
    (la / NAME).write_text(json.dumps(lap))
    (ho / NAME).write_text(json.dumps(hos))
    rc = ce.main([str(la), str(ho), "--since", "0", *extra])
    return rc, capsys.readouterr().out


IN = [("2026-11-10T23:00:00", "Boston Bruins", "Ottawa Senators"), ("2026-11-11T00:00:00", "Utah", "Dallas Stars"),
      ("2026-11-12T02:30:00", "Seattle Kraken", "Vegas")]


def test_the_host_only_columns_are_masked_and_counted_and_the_pair_reads_clean(tmp_path, capsys):
    lap = doc([row(t, h, a, **LAPTOP_NULLS) for t, h, a in IN], "laptop")
    hos = doc([row(t, h, a, **HOST_ONLY) for t, h, a in IN], "host")
    rc, out = run(tmp_path, capsys, lap, hos)
    assert rc == ce.EXIT_CLEAN, out
    # 18 host-only columns per row on either side, 3 rows, plus the host's desk_meta block
    assert f"{ce.HOST_ONLY_LINE}: {18 * 3 + 1}" in out.splitlines(), out
    assert "in the window (yesterday, today, tomorrow) laptop=3 host=3; outside the window, never compared: laptop 0 · "\
           "host 0" in out
    assert "paired kinds (fixtures_NHL): 1 compared with rows in the window · 0 empty in the window · 0 missing on a " \
           "side · rows outside the window laptop 0 · host 0 · expected one-sided (not a paired kind): 0" in out


def test_rows_outside_the_window_are_counted_never_compared_and_count_is_left_out(tmp_path, capsys):
    """The laptop has no weekly full-season sync: its later kickoffs can legitimately differ from the host's."""
    later_l = [row("2026-11-15T00:00:00", "Utah", "Dallas Stars"), row("2026-11-16T00:00:00", "A", "B")]
    later_h = [row("2026-11-15T01:00:00", "Utah", "Dallas Stars")]                       # moved, and one fewer
    early = [row("2026-11-09T23:00:00", "C", "D")]                                       # D-2: outside too
    lap = doc([row(t, h, a) for t, h, a in IN] + later_l + early, "laptop")
    hos = doc([row(t, h, a) for t, h, a in IN] + later_h, "host")
    rc, out = run(tmp_path, capsys, lap, hos)
    assert rc == ce.EXIT_CLEAN, out
    assert "in the window (yesterday, today, tomorrow) laptop=3 host=3; outside the window, never compared: laptop 3 " \
           "· host 1" in out
    assert "count" not in "".join(ln for ln in out.splitlines() if ln.startswith("    $"))


def test_an_in_window_difference_is_divergent(tmp_path, capsys):
    lap = doc([row(t, h, a) for t, h, a in IN], "laptop")
    hos = doc([row(t, h, a, **({"status": "finished", "home_score": 3, "away_score": 2} if h == "Utah" else {}))
               for t, h, a in IN], "host")
    rc, out = run(tmp_path, capsys, lap, hos)
    assert rc == ce.EXIT_DIVERGENT, out
    assert "$.fixtures[Dallas Stars @ Utah 2026-11-11T00:00].status: 'scheduled' vs 'finished'" in out
    # a game in the window on one side only is a row on one side
    rc, out = run(tmp_path / "b", capsys, doc([row(t, h, a) for t, h, a in IN], "laptop"),
                  doc([row(t, h, a) for t, h, a in IN[:2]], "host"))
    assert rc == ce.EXIT_DIVERGENT and "only on laptop (1): Vegas @ Seattle Kraken 2026-11-12T02:30" in out


def test_a_new_key_in_the_row_stays_visible(tmp_path, capsys):
    """A key `_fixture_row` gains that is not host-only is compared: a one-sided new key reads as a field diff."""
    lap = doc([row(t, h, a) for t, h, a in IN], "laptop")
    hos = doc([row(t, h, a, venue="Delta Center") for t, h, a in IN], "host")
    rc, out = run(tmp_path, capsys, lap, hos)
    assert rc == ce.EXIT_DIVERGENT and ".venue: only in host" in out


def test_the_host_only_mask_is_for_paired_kinds_alone(tmp_path, capsys):
    """Another kind's market column is not masked (no 335 mask outside the paired kinds): its difference is printed,
    as an unpaired kind's is, and certifies nothing (336 item 4(3))."""
    la, ho = tmp_path / "laptop", tmp_path / "host"
    la.mkdir(), ho.mkdir()
    name = f"fixtures_NCAA_{DAY}.json"
    (la / name).write_text(json.dumps({"fixtures": [row("2026-11-11T00:00:00", "A", "B", market=None)]}))
    (ho / name).write_text(json.dumps({"fixtures": [row("2026-11-11T00:00:00", "A", "B", market={"x": 1})]}))
    rc = ce.main([str(la), str(ho), "--since", "0", "--today", DAY])
    out = capsys.readouterr().out
    assert rc == ce.EXIT_NOTHING_TO_COMPARE and ".market: " in out and ce.UNPAIRED_DIFFERS in out, out
    assert f"{ce.HOST_ONLY_LINE}: 0" in out


def test_the_declared_list_and_the_mask_names():
    assert ce.PAIRED_KINDS == {"fixtures_NHL": {"rows": "fixtures", "days": (-1, 0, 1)}}
    for k in ("market", "kalshi", "kalshi_bid", "kalshi_legs", "exec_cost_taker_away", "fee_series", "k_track",
              "input_quality", "desk", "desk_meta", "away_bid", "away_ask", "close_unpriced"):
        assert ce.host_only_key(k), k
    # 336 item 4(1): "never masked by a prefix": a new key of the old prefix families stays visible until placed
    for k in ("home_team", "status", "utc_date", "home_score", "competition", "family", "stage", "matchday", "note",
              "feed_source", "feedback", "fees", "kalshix", "exec_costs", "kalshi_new", "exec_cost_new", "fee_new"):
        assert not ce.host_only_key(k), k
    assert not hasattr(ce, "HOST_ONLY_PREFIXES")
    assert not ce.HOST_ONLY_KEYS & ce.FIXTURE_COMPARED_KEYS and not ce.HOST_ONLY_KEYS & ce.MASKED


def _dict_keys(fn, target: str) -> tuple[set, list]:
    """The string keys of `target = {...}` in `fn` and of every `target["k"] = ...`, and the `**` spreads' source."""
    keys, spreads = set(), []
    for node in ast.walk(ast.parse(inspect.getsource(fn).lstrip())):
        if isinstance(node, ast.Assign) and any(isinstance(x, ast.Name) and x.id == target for x in node.targets) \
                and isinstance(node.value, ast.Dict):
            for k, v in zip(node.value.keys, node.value.values):
                if k is None:
                    spreads.append(ast.unparse(v))
                else:
                    keys.add(k.value)
        if isinstance(node, ast.Assign):
            for x in node.targets:
                if isinstance(x, ast.Subscript) and isinstance(x.value, ast.Name) and x.value.id == target:
                    keys.add(x.slice.value)
    return keys, spreads


def test_every_key_fixture_row_writes_is_compared_or_on_the_declared_mask():
    """336 item 4(1): "every key `_fixture_row` writes is either compared or on the declared mask, so a new key fails
    the test until it is placed". Read from the code: `_fixture_row`'s row literal and its later `row[...]` writes, the
    K-track spread (venue.kalshi_exec's keys, two-sided, and KALSHI_EXEC_NULL's), and the Desk's per-row `desk` and
    file `desk_meta` (desk_policy.annotate). match_id sits under the generic machine-local mask (MASKED)."""
    from src.walters import desk_policy, export, venue
    keys, spreads = _dict_keys(export._fixture_row, "row")
    assert len(spreads) == 1 and "_kexec(" in spreads[0] and "_KNULL" in spreads[0], spreads  # a new spread: place it
    keys |= set(venue.kalshi_exec(0.52, 0.55, "NHL", two_way=True)) | set(venue.KALSHI_EXEC_NULL)
    src = inspect.getsource(desk_policy.annotate)
    assert '["desk"] = desk_block(' in src and 'doc["desk_meta"] = ' in src
    keys |= {"desk", "desk_meta"}
    placed = ce.FIXTURE_COMPARED_KEYS | ce.HOST_ONLY_KEYS | ce.MASKED
    assert keys - placed == set(), f"place these keys (compared or on the declared mask): {sorted(keys - placed)}"
    assert (ce.FIXTURE_COMPARED_KEYS | ce.HOST_ONLY_KEYS) - keys == set()          # nothing declared that is not written
    assert "match_id" in keys and "match_id" in ce.MASKED


def test_every_key_of_the_fixtures_file_is_placed_too():
    """The file around the rows (export_fixtures' payload): compared, the rows, `count` (left out for the in-window
    counts), or the generic mask (git_sha, the exported_at timestamp)."""
    from src.walters import export
    keys, spreads = _dict_keys(export.export_fixtures, "payload")
    assert not spreads
    compared = {"competition_code", "contains_predictions", "note"}
    assert keys == compared | {"fixtures", "count", "git_sha", "exported_at"}, sorted(keys)
    assert "git_sha" in ce.MASKED and ce.TS_KEY.search("exported_at") and not any(ce.host_only_key(k) for k in keys)


def test_a_paired_file_whose_rows_list_is_missing_on_one_side_is_divergent_never_an_error(tmp_path, capsys):
    """Code's review: one side without its rows list crashed the comparator (host side) or cut one side only
    (laptop side). Both orientations now read DIVERGENT, uncut."""
    good = doc([row(t, h, a) for t, h, a in IN], "laptop")
    for lap, hos in ((good, {**good, "fixtures": None}), ({k: v for k, v in good.items() if k != "fixtures"}, good)):
        rc, out = run(tmp_path / str(id(lap)), capsys, lap, hos)
        assert rc == ce.EXIT_DIVERGENT and "VERDICT: ERROR" not in out, out
        assert "outside the window, never compared" not in out


def test_the_same_paired_kind_under_two_names_is_named_as_such(tmp_path, capsys):
    la, ho = tmp_path / "laptop", tmp_path / "host"
    la.mkdir(), ho.mkdir()
    (la / NAME).write_text(json.dumps(doc([row(t, h, a) for t, h, a in IN], "laptop")))
    (ho / "fixtures_NHL_2026-11-10_to_2026-11-12.json").write_text(json.dumps(doc([], "host")))
    rc = ce.main([str(la), str(ho), "--since", "0"])
    out = capsys.readouterr().out
    assert rc == ce.EXIT_DIVERGENT
    assert "PAIRED KIND fixtures_NHL is on both sides under different names, so nothing of it was compared" in out
    assert "PAIRED KIND fixtures_NHL missing on" not in out and "0 missing on a side" in out
    assert "2 paired kind under different names" in out
