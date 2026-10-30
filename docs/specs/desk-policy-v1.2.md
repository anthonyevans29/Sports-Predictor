# Desk policy v1.2: the unit is a fraction of the pool (ARCHITECT 2026-10-30, addendum 179, #732)

Policy class. The rule ships in its own small PR first (review stop rule, item 5), and nothing else rides it. The rule is the operator's ruling of 09:26 ET. No dollar figure of any kind appears in this spec, the code, the tests or the ledger entry: names and fractions only.

## The ruling (verbatim, items 1 to 7)

> "1. THE RULING (operator): a unit is 8% of the money pool, growing and shrinking with it. The architect advised 2–3% (quarter-Kelly on noisy edges; the exec >= 4 cohort stands 8–5 and -1.0u) and the operator kept 8%: recorded here as the operator's sizing decision with the architect's advice beside it, not re-opened. The half-unit cohort (0 < exec < 4, QB-clean) is therefore 4% of the pool; LADDER notional and the floor-blocked notional lines stay notional at 1u."

> "2. THE POOL: the Kalshi account's value — cash balance plus open positions at cost; nothing off Kalshi counts (the architect's reading; the operator corrects it if the pool is wider). Law 1 first: Code prints the KEY NAMES of the Kalshi portfolio balance endpoint's real response and, if open positions' cost is not in it, the positions endpoint's — names only, never a value — and builds the read on the names that exist, not on remembered ones."

> "3. THE READ, ONCE A DAY: the day's unit is computed at the day's FIRST Desk page on the host (the first slate stage of the ET day) as floor(UNIT_FRACTION × pool) in whole dollars, written to a small state file under logs/ (never data/) keyed by the ET date, and every later page that day — slates and closings of every family — reads that file; the unit never changes inside a day and never from a bet's own result. The laptop's morning console prints the same read for the record (its own call); the laptop's pages (MLB, when the season returns) read it the same way."

> "4. FLOOR, FAILURE, FALLBACK: the floor is SP_UNIT_FLOOR_USD, set by hand in host.env and the laptop's .env (value never in the repo; blocks check the name only), with the one requirement that a half-unit buys at least one contract at any price. A balance read that fails leaves the day's unit UNREAD: the page carries no order line and says "unit unread — no order" (law 4); a PLAY with no order line is not placed; the previous day's cached unit is NOT reused silently. SP_UNIT_USD is retired from the Desk's sizing (kept in .env only as the ledger's historical unit for rows before the switch)."

> "5. WHAT IS PUBLIC AND WHAT IS NOT: the fraction (UNIT_FRACTION = 0.08, HALF_UNIT_FRACTION = 0.04) and the names are code (desk_policy, v1.2) and may be printed; the pool's dollar value and the day's dollar unit go on the pages (the private mirror) and the laptop's logs only — never the public repo, an Issue, a PR, a test fixture or a ledger entry."

> "6. THE RECORD: W-L and units stay the record; every page's order line stamps the day's unit ("1u = $X") as now, so the ledger's dollar P&L per row is the row's unit × its result; nothing in RESULTS.md, the cohort lines or the tally changes meaning."

> "7. ORDER LINES: contracts = floor(units × unit_dollars / limit) as today, on the day's unit. The Desk's "take at the ask, spread < 3¢" doctrine stays; Code adds to the page the order's size against the visible depth at the ask (contracts available at the limit, from the orderbook read the Desk already makes) and a line "size over the ask's depth: N contracts" when it is — informational; the architect reads it on the first pages at the new size before any doctrine change."

## The code

**`src/walters/desk_policy.py`.** `POLICY_VERSION = "v1.2"`. The module defines these constants:

| Constant | Value |
|---|---|
| `UNIT_FRACTION` | `0.08` |
| `HALF_UNIT_FRACTION` | `0.04` |
| `UNIT_FLOOR_ENV` | `"SP_UNIT_FLOOR_USD"` (the name only) |
| `UNIT_UNREAD_TEXT` | `"unit unread — no order"` |

How sizing works:

- Every call, tier and units count is v1.1's. A unit's dollars are the day's unit.
- A 0.5u row is `HALF_UNIT_FRACTION` of the pool by arithmetic, so the half-unit cohort has no code path of its own.
- LADDER notional and the floor-blocked notional lines are in units and stay so.

`unit_size()` returns the unit in force. When more than one applies, the first in this list wins:

1. `unit_override` (desk-rescore: the file's own basis);
2. `UNIT_PIN` (tests only);
3. the day that `annotate` / `parlays_doc` read once for their own `now` (`_day_scope`);
4. otherwise, a read of the wall clock's ET day.

Each order line is written on that unit:

- **Read day.** The basis is `1u = $<n>`, in the pre-v1.2 label's shape. `contracts = floor(units × n / limit)`.
- **Unread day.** `order.text` and `order.contracts` are null, `order.why` is `UNIT_UNREAD_TEXT` verbatim, and `order.unit` is `unit unread`. The exec gate prices its fee at the reference fill (10 contracts per 1u, the pre-v1.2 default), and `desk.exec` / `desk.ladder_exec` carry `contracts_basis` "reference fill, no order (unit unread)" beside that count. **This is not neutral (judgement J1, for the architect):** the taker fee rounds per fill of the order's own count (#87 v1.1 (h)), so on a read day it rounds at units × the day's unit / limit, and a borderline row's exec edge, tier and units can differ between a read day and an unread one. A synthetic receipt: an NFL row at a 0.55 ask whose exec edge sits at 4pp is a 1u PLAY on an unread day and a 0.5u PLAY on a read day. Which basis is right is the architect's ruling; the record's tier depends on the read until then.

`desk_meta.unit` holds `{state, et_date, label, why, fraction, half_fraction, floor_name}`.

**`src/walters/desk_unit.py`.** The day's file is `logs/desk_unit_<ET date>.json`.

- The folder is `SP_DESK_UNIT_DIR`, else the checkout's `logs/`. A path with a `data` segment is refused (law 5).
- The file is written ONCE: a hidden temporary name, then `os.link`, which refuses an existing name.
- A later read that day, a retried slate or a second process finds the file and never reads the pool again.
- `unit = max(floor(UNIT_FRACTION × pool), floor)` in whole dollars.
  - The floor must be a positive whole number. Half of the floor, and half of the unit, must buy one contract at 0.99, the highest limit an order writes. If not, the day is unread.
  - With the floor unset, no floor is applied and the record says so. The half-unit requirement still holds.
- A failed read writes nothing: that page is unread ("unit unread — no order"), and the next page that day, slate or closing, reads again; the first page whose read succeeds writes the day's file, which then stands (ARCHITECT 2026-10-30 10:15 ET, addendum 180 item 4, verbatim: "the unit file for the ET date is written by the FIRST page that day whose read succeeds; a page that finds no file for its ET date makes the read itself and writes the file on success; a page that finds the file never rewrites it (fixed for the day stands). So a failed read at the first page costs that page its order line, not the day's.").
- A day with no file is unread, and yesterday's file is never read.
- A file that is not this day's `desk_unit_v1` record is unread.

**`src/walters/kalshi_pool.py`.** The pool is cash plus open positions at cost, in dollars. It is a GET read through `scripts/kalshi_trade_api_probe.py`'s `Client` (loaded from its file, with the probe unchanged) and signed with `KALSHI_API_KEY_ID` / `KALSHI_PRIVATE_KEY_PATH`.

- **The key names are not enumerated yet.** `POOL_FIELDS = None`, so every read is unread with "the balance response's key names are not enumerated (#732)", and no request is made.
- When the operator's names-only block lands on #732, one reviewed change fills `POOL_FIELDS` in the shape the module documents:
  - `per_dollar`, the API's money unit, which is a name-level fact too;
  - `cash`;
  - `positions`, one of: `{"included": true}`, `{"balance_key": …}`, or the paged positions endpoint `{path, list, cost, cursor, cursor_param, limit_param}`. The request's paging parameter names (`cursor_param`, and `limit_param` or null for none) are read from the endpoint's own documented request, never borrowed from another endpoint or assumed to equal the response's cursor key.
- A missing key, a non-200 answer, a timeout, a bad value or a spec in another shape is unread, never a partial pool.

**`cli.py desk-unit`.** This runs the read once a day and prints the fractions, the floor's name and the state.

- The pool and the unit in dollars print only where the machine's role reads `laptop`.
- It ends `DESK-UNIT state=… et_date=… new=…`.
- It exits 0, except exit 2 for a `data/` folder.

**`deploy/hosting/closing.py`.** `_slate` runs `read_day_unit` after the backup and before the steps: `python cli.py desk-unit` through the chain's step runner.

- The read is not one of `resolve_steps`' steps.
- Its exit never fails the slate.
- The receipt keeps `unit` {state, et_date, new, exit}, never a figure.
- Pages:
  - On an unread day the slate page adds `unit unread — no order` on its own line.
  - A closing page's PLAY line, and the console summary, print the unread text verbatim in place of the order.
  - An order's `depth_note` follows the order.
- C8 stands: closing.py neither imports the Desk nor names a trading path. The docstring's "never opens Kalshi's trading API" is amended to name the slate's one read (judgement J2).

**Depth (item 7): WITHDRAWN AS WRITTEN (addendum 182 item 5); a follow-up Issue.** Item 7 says "from the orderbook read the Desk already makes". **No orderbook read exists today.** The `/markets` listing's level sizes are received but not stored, so no export leg carries a size, and no depth field's key name has been read from a real response (law 1). So no field name is guessed: `desk_policy.depth_note(contracts, depth)` holds the line's text, "size over the ask's depth: N contracts" (N the depth at the ask, a TAKE order only), and its arithmetic, and `order_line` reads no depth from any leg. The closing page passes an order's `depth_note` through when an export ever writes one; none does. Wiring it (a stored size, under its enumerated key name, and the order's size against the depth on the page, not only the over-depth line) waits for the architect's ruling on #732.

## Ruled (ARCHITECT 2026-10-30 11:20 ET, addendum 182)

- **The merge and tag hold (item 1)** stands as built: the PR is not merge-ready while `POOL_FIELDS` is None. No stub merge, no switch keeping the v1.1 unit, and v1.6.2 does not carry the change until the names are in it. The names land as one reviewed change in this PR, with a test on those names, after the operator's block output is on #732.
- **J1 (item 2), as built.** "The exec edge is the edge of the order the Desk would place; with no order (unread) the reference fill (ORDER_UNIT_CONTRACTS per 1u, the pre-v1.2 basis) is the basis, labelled contracts_basis on the row." The synthetic receipt (the 0.55 ask at 4pp, both bases' tier) is pinned: `test_j1_the_read_can_move_a_borderline_tier`. The thresholds stand.
- **J3 (item 3).** "the floor never funds a unit the pool cannot. A floor above floor(pool) makes the day UNREAD, the reason named ("floor above the pool") ... A floor above the fraction's unit but within the pool applies as the operator's hand-set minimum, said by name as built."
- **J6 (item 4).** Each machine reads its own pool and writes its own file. `compare_exports` masks the unit-bearing fields (order.unit, order.text, order.contracts, desk_meta.unit, and the laptop-only pool field wherever it appears), compares the rest and prints the masked count. That is its own small PR after this one, merged before v1.6.2's compare morning.
- **Item 7 (item 5), withdrawn as written.** The premise ("the orderbook read the Desk already makes") was wrong: there is none. `depth_note`'s text and the page's pass-through stay as built (small, inert). Wiring it is a follow-up Issue, with no date, after the first week at the new size.
- **The Cockpit (item 6)** is one follow-up PR on `tools/cockpit.html` (below).
- **J2, J7, J11, J12 (item 7):** as built.
- **J4 and J5 (addendum 180 item 4).** "the unit file for the ET date is written by the FIRST page that day whose read succeeds; a page that finds no file for its ET date makes the read itself and writes the file on success; a page that finds the file never rewrites it (fixed for the day stands). So a failed read at the first page costs that page its order line, not the day's." A failed read is retried by the next page, and a closing that finds no day file runs `desk-unit` itself before its export, as the slate does.

## Not changed

- W-L and units stay the record.
- Nothing changes in RESULTS.md, the cohort lines, results-tally or exec_cohorts.
- No reader of `SP_UNIT_USD` remains in code.
  - A file exported before the switch carries its basis in its order lines' `unit` label, and desk-rescore reads it there.
  - The rescore receipt (docs/receipts) names a dollar unit, never its figure.
- The Cockpit is a separate lane, republished on the operator's word (a named follow-up on #732):
  - Its `POLICY_VERSION` still says v1.1, so from the switch every v1.2 file draws its source note "⚠ file policy v1.2 ≠ Cockpit v1.1" on the Desk summary line, and the ledger text and summary stamp policy v1.1. **That warning is expected until the Cockpit's constant moves to v1.2**. Until then it is not a real mismatch.
  - Its `fillUnitBasis` / exposure read ONE unit basis from the loaded files and convert EVERY fill in the ledger by it. Under v1.2 the unit moves daily, so past days' fills convert at the loaded file's day unit, and the cap-equivalent flags shift with the pool; files of two ET days loaded together read as a conflict (contracts only). The new `unit unread` label matches neither form and falls back to contracts only. Its comments still say "SP_UNIT_USD set / unset". The fix (restrict the conversion to fills of the file's own ET day, `desk_meta.unit.et_date`, or label the units "at the loaded file's day unit") is in that lane.

## When it takes effect

- **On the laptop**, at merge (`main`). The laptop's morning block runs `desk-unit`.
- **On the host**, on the next tag (v1.6.2) after a compare morning. Until then the host's pages keep the fixed unit (the host deploys tags, never `main`).
- **The switch date** is the first host page on v1.6.2. The first day's read on the host is the architect's block.
- **Before the names land**, every day reads unread (`POOL_FIELDS` is None), so no page carries an order line: on the laptop from the merge, and on the host from the first tag that carries this change. Nothing keeps the fixed unit on a machine running this code. Whether this merges, or a tag carries it, before `POOL_FIELDS` is filled from the operator's names-only block is the architect's ruling (#732); the PR stays out of merge-readiness until then.
