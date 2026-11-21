## 2026-11-21 (#1065: 440-v23-shadow-bar-and-params — the soccer-v23 shadow needs the bar the checkout holds and the v22 params the run read (ARCHITECT 2026-11-21, addendum 440 item 4; #656))
- **src/walters/soccer_v23_shadow.py:**
  - (a) The shadow is dormant, with its reason, unless the entry's gate equals BAR_TEXT (the run's own `bar_state`): "A PASS is shown only as a PASS at the bar the checkout holds."
  - (b) It is dormant unless the run record's `v22_params_sha256` equals `soccer_v23.params_sha256` of the stored v22 poisson params it prices from. A run record without the field, or with a malformed one, is dormant.
- **src/walters/soccer_v23.py:**
  - `record()` writes one more field, `v22_params_sha256`: v22's stored poisson params as the run read them.
  - `params_sha256` names the canonical form: sha256 of `json.dumps(dict(params), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)`, the ASCII bytes.
  - No bar, no fingerprint and no scored row reads the field: BAR_TEXT, `stream_fingerprint` and the scored set are untouched. The harness's one-run test pins that the run's own result does not carry it, and that its fingerprint, verdict and scored count are unchanged.
- **Tests:** three new dormant causes, each byte-identical end to end like the others: a gate that is not BAR_TEXT, a run record without the sha, and params that are not the ones the run read. Also the malformed sha and a null gate as named causes, the canonical form, and the run record's field (tests/test_soccer_v23_harness.py). Nothing run on either machine.
