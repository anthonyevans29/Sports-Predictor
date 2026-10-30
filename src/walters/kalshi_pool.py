"""
THE POOL READ (ARCHITECT 2026-10-30 09:30 ET, addendum 179 item 2, #732; Desk policy v1.2), verbatim: "the Kalshi
account's value — cash balance plus open positions at cost; nothing off Kalshi counts (the architect's reading; the
operator corrects it if the pool is wider). Law 1 first: Code prints the KEY NAMES of the Kalshi portfolio balance
endpoint's real response and, if open positions' cost is not in it, the positions endpoint's — names only, never a
value — and builds the read on the names that exist, not on remembered ones."

THE NAMES (the operator's names-only receipt on #732, host v1.6.1, 2026-10-30 ~12:50 ET) AND THEIR READ (ARCHITECT
2026-10-30 13:00 ET, addendum 186, verbatim): "THE MONEY UNIT: the `_dollars` STRING fields, read as Decimal — never
the int fields (balance, portfolio_value), whose unit is not asserted by the response. That settles per_dollar: there
is none to assume." "THE POOL = Decimal(balance_dollars) + Σ Decimal(market_positions[].market_exposure_dollars) over
EVERY page of /portfolio/positions (cursor until empty ...; a page loop past a cap of 20 pages reads UNREAD, never a
partial pool)." "portfolio_value is NOT used (it is Kalshi's own valuation; the pool is at cost, not marked to market).
event_positions is not used (one pool, no double count)."

THE DEFINITIONS (ARCHITECT 2026-10-30 13:20 ET, addendum 187; "read by the architect from the live reference
2026-10-30 (docs.kalshi.com is not reachable from Code's session)"), verbatim:
- https://docs.kalshi.com/api-reference/portfolio/get-positions — market_exposure_dollars: "Cost of the aggregate
  market position in dollars" (the cost basis addendum 179 item 2's "at cost" requires); cursor: "The Cursor
  represents a pointer to the next page of records in the pagination. Use the value returned from the previous
  response to get the next page."; limit: "Parameter to specify the number of results per page. Defaults to 100.";
  the endpoint: "Returns unsettled positions by default"; count_filter: "Restricts the positions to those with any of
  following fields with non-zero values, as a comma separated list. The following values are accepted - position,
  total_traded".
- https://docs.kalshi.com/api-reference/portfolio/get-balance — the endpoint: "Returns the balance and portfolio value
  for a member. Both values include all exchange indexes unless `exchange_index` is provided."; balance_dollars:
  "Member's available balance as a fixed-point dollar string for the requested account and exchange index.";
  balance_breakdown: "User balance breakdown per exchange instance, omitted only when using a subaccount-restricted
  API key." So balance_dollars is the total across the exchange indexes when exchange_index is omitted (the read
  omits it): the breakdown is NOT read, and its absence never makes a day unread (186 item 4's first branch).
- The read (187 item 3): settlement_status omitted (unsettled = open), count_filter=position, limit at the
  documented default, cursor until the response's cursor is empty, the 20-page cap to UNREAD. Item 4, for the record:
  balance_dollars is the AVAILABLE balance, so cash reserved by a resting order is outside the pool until it fills or
  cancels (conservative; the Desk places no resting orders).

A value is a `_dollars` string read as Decimal (never an int, a float or a bool); a missing key, a non-200 answer, a
timeout, a bad value or a spec that is not this shape reads UNREAD with its why, never a partial pool (law 4).

GET ONLY: the request goes through scripts/kalshi_trade_api_probe.py's Client (its signer and its read-only refusal:
any method but GET raises before a socket opens), loaded from the file, its behaviour unchanged. Credentials are its
env names, KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY_PATH; nothing here prints a value.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

# #732's receipt and addenda 186-187: every name below is in the real response or the documented request.
POOL_FIELDS: dict | None = {
    "cash": "balance_dollars",
    "positions": {"path": "/portfolio/positions", "list": "market_positions", "cost": "market_exposure_dollars",
                  "cursor": "cursor", "cursor_param": "cursor", "limit_param": "limit",
                  "params": {"count_filter": "position"}},
}
NOT_ENUMERATED = "the balance response's key names are not enumerated (#732)"
BALANCE_PATH = "/portfolio/balance"
PAGE_LIMIT = 100                     # the documented default page size, sent under the spec's limit_param
PAGED_KEYS = frozenset({"path", "list", "cost", "cursor", "cursor_param", "limit_param", "params"})
MAX_PAGES = 20                       # addendum 186 item 3: a loop past 20 pages reads UNREAD, never a partial pool
# the reference's "Fixed-point US dollar string ... responses emit up to 6" decimal places: ASCII digits, no sign, no
# exponent, no blank (a negative balance or cost is not a pool: law 4, unread)
FIXED_POINT = re.compile(r"[0-9]+(?:\.[0-9]{1,6})?")
PROBE = Path(__file__).resolve().parents[2] / "scripts" / "kalshi_trade_api_probe.py"


def _probe():
    """The trade-API probe module (its Client and signer), loaded from its file: the probe is unchanged."""
    name = "kalshi_trade_api_probe"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, PROBE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def signed_fetch():
    """fetch(path, params) -> (http status, body), signed GET on the PROD trading API; (None, why) with no key."""
    kp = _probe()
    key_id, key_path = os.getenv("KALSHI_API_KEY_ID"), os.getenv("KALSHI_PRIVATE_KEY_PATH")
    if not (key_id and key_path):
        return None
    client = kp.Client(kp.PROD, key_id, key_path)

    def fetch(path, params=None):
        return client.request("GET", path, params or {}, auth=True)
    return fetch


def _unread(why: str) -> dict:
    return {"ok": False, "pool_usd": None, "why": why}


def _amount(body, key: str, where: str):
    """A `_dollars` string read as Decimal dollars (addendum 186 item 2); anything else is a why, never a figure."""
    if not isinstance(body, dict) or key not in body:
        return None, f"key '{key}' is missing from the {where} response"
    v = body[key]
    if not isinstance(v, str) or not FIXED_POINT.fullmatch(v):
        return None, f"key '{key}' of the {where} response is not a dollar string"
    try:
        return Decimal(v), None
    except (InvalidOperation, ValueError):
        return None, f"key '{key}' of the {where} response is not a dollar string"


def _spec_why(f) -> str | None:
    if not isinstance(f, dict) or set(f) != {"cash", "positions"} or not isinstance(f.get("cash"), str) \
            or not f["cash"]:
        return "POOL_FIELDS is not the documented shape (cash)"
    pos = f.get("positions")
    if isinstance(pos, dict) and set(pos) == PAGED_KEYS and all(
            isinstance(pos[k], str) and pos[k] for k in PAGED_KEYS - {"limit_param", "params"}) and (
            pos["limit_param"] is None or (isinstance(pos["limit_param"], str) and pos["limit_param"])) and (
            isinstance(pos["params"], dict) and all(isinstance(k, str) and isinstance(v, str)
                                                    for k, v in pos["params"].items())):
        return None
    return "POOL_FIELDS is not the documented shape (positions)"


def _call(fetch, path, params, where):
    try:
        got = fetch(path, params)
    except Exception as e:  # noqa: BLE001 — a read reports, never crashes (a timeout, a refused socket)
        return None, f"the {where} read failed ({e.__class__.__name__})"
    if not (isinstance(got, tuple) and len(got) == 2):
        return None, f"the {where} read gave no answer"
    code, body = got
    if code is None:
        return None, f"the {where} read: {body if isinstance(body, str) else 'no key configured'}"
    if code != 200:
        return None, f"the {where} read answered HTTP {code}"
    return body, None


def read_pool(fetch=None, fields=None) -> dict:
    """{"ok": True, "pool_usd": Decimal} (balance_dollars + Σ market_positions[].market_exposure_dollars over every
    page; addenda 186-187) or {"ok": False, "why"}.
    `fetch`/`fields`: tests (a fake fetch with synthetic payloads; the spec monkeypatched); else the signed GET and
    POOL_FIELDS. Nothing is printed."""
    f = POOL_FIELDS if fields is None else fields
    if f is None:
        return _unread(NOT_ENUMERATED)
    why = _spec_why(f)
    if why:
        return _unread(why)
    if fetch is None:
        try:
            fetch = signed_fetch()
        except Exception as e:  # noqa: BLE001 — an unusable key or a missing package: the day is unread
            return _unread(f"the request signer is not usable ({e.__class__.__name__})")
        if fetch is None:
            return _unread("no Kalshi API key configured (KALSHI_API_KEY_ID / KALSHI_PRIVATE_KEY_PATH)")
    body, why = _call(fetch, BALANCE_PATH, None, "balance")
    if why:
        return _unread(why)
    cash, why = _amount(body, f["cash"], "balance")
    if why:
        return _unread(why)
    pos = f["positions"]
    held, cursor = Decimal(0), None
    for _ in range(MAX_PAGES):
        params = {**pos["params"], **({pos["limit_param"]: PAGE_LIMIT} if pos["limit_param"] else {}),
                  **({pos["cursor_param"]: cursor} if cursor else {})}
        page, why = _call(fetch, pos["path"], params, "positions")
        if why:
            return _unread(why)
        if not isinstance(page, dict) or not isinstance(page.get(pos["list"]), list):
            return _unread(f"key '{pos['list']}' is missing from the positions response")
        for p in page[pos["list"]]:
            v, why = _amount(p, pos["cost"], "positions")
            if why:
                return _unread(why)
            held += v
        if pos["cursor"] not in page:          # the paging key is in every page (#732): absent is a shape fault
            return _unread(f"key '{pos['cursor']}' is missing from the positions response")
        cursor = page[pos["cursor"]]
        if not isinstance(cursor, str):        # addendum 188 item 2: "the cursor must be a string; "" ends paging;
            return _unread("cursor not a string")   # absent, null or any non-string reads UNREAD, named"
        if cursor == "":
            break
    else:
        return _unread(f"the positions read did not end within {MAX_PAGES} pages")
    return {"ok": True, "pool_usd": cash + held, "why": None}
