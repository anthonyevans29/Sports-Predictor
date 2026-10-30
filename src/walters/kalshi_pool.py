"""
THE POOL READ (ARCHITECT 2026-10-30 09:30 ET, addendum 179 item 2, #732; Desk policy v1.2), verbatim: "the Kalshi
account's value — cash balance plus open positions at cost; nothing off Kalshi counts (the architect's reading; the
operator corrects it if the pool is wider). Law 1 first: Code prints the KEY NAMES of the Kalshi portfolio balance
endpoint's real response and, if open positions' cost is not in it, the positions endpoint's — names only, never a
value — and builds the read on the names that exist, not on remembered ones."

THE NAMES ARE NOT ENUMERATED YET: the operator's names-only block lands its output on #732. Until then POOL_FIELDS is
None and every read is UNREAD with NOT_ENUMERATED: no field name is guessed, and no request is made. When the names
land, POOL_FIELDS is filled from that output (one reviewed change) in this shape; every entry is a name-level fact
read from the real response, the API's money unit included:
    {"per_dollar": <the API's money units per dollar: 100 for integer cents, 1 for dollar amounts>,
     "cash": "<the cash balance's key in GET /portfolio/balance>",
     "positions": one of
        {"included": True}                          the balance's cash already carries open positions at cost
        {"balance_key": "<key>"}                    a key of the balance response holding positions at cost
        {"path": "/portfolio/positions", "list": "<the positions list's key>", "cost": "<a position's cost key>",
         "cursor": "<the response's paging cursor key>", "cursor_param": "<the request's cursor parameter>",
         "limit_param": "<the request's page-size parameter>" or None (none sent)}
                                                    the positions endpoint, paged; the REQUEST's parameter names
                                                    are read from the endpoint's documented request too, never
                                                    borrowed from another endpoint or assumed to equal a response key
    }
A value is an integer or a numeric string (never a bool); a missing key, a non-200 answer, a timeout, a bad value or a
spec that is not this shape reads UNREAD with its why, never a partial pool (law 4).

GET ONLY: the request goes through scripts/kalshi_trade_api_probe.py's Client (its signer and its read-only refusal:
any method but GET raises before a socket opens), loaded from the file, its behaviour unchanged. Credentials are its
env names, KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY_PATH; nothing here prints a value.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

POOL_FIELDS: dict | None = None      # #732: filled from the operator's names-only block, never from memory
NOT_ENUMERATED = "the balance response's key names are not enumerated (#732)"
BALANCE_PATH = "/portfolio/balance"
PAGE_LIMIT = 200                     # the page size sent under the spec's limit_param (none sent when it is None)
PAGED_KEYS = frozenset({"path", "list", "cost", "cursor", "cursor_param", "limit_param"})
MAX_PAGES = 50
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


def _amount(body, key: str, per_dollar: Decimal, where: str):
    if not isinstance(body, dict) or key not in body:
        return None, f"key '{key}' is missing from the {where} response"
    v = body[key]
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        return None, f"key '{key}' of the {where} response is not a number"
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None, f"key '{key}' of the {where} response is not a number"
    if not d.is_finite():
        return None, f"key '{key}' of the {where} response is not a number"
    return d / per_dollar, None


def _spec_why(f) -> str | None:
    if not isinstance(f, dict) or not isinstance(f.get("cash"), str) or not f["cash"]:
        return "POOL_FIELDS is not the documented shape (no cash key)"
    try:
        pd = Decimal(str(f.get("per_dollar")))
    except (InvalidOperation, ValueError):
        return "POOL_FIELDS is not the documented shape (per_dollar)"
    if isinstance(f.get("per_dollar"), bool) or not pd.is_finite() or pd <= 0:
        return "POOL_FIELDS is not the documented shape (per_dollar)"
    pos = f.get("positions")
    if pos == {"included": True}:
        return None
    if isinstance(pos, dict) and set(pos) == {"balance_key"} and isinstance(pos["balance_key"], str):
        return None
    if isinstance(pos, dict) and set(pos) == PAGED_KEYS and all(
            isinstance(pos[k], str) and pos[k] for k in PAGED_KEYS - {"limit_param"}) and (
            pos["limit_param"] is None or (isinstance(pos["limit_param"], str) and pos["limit_param"])):
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
    """{"ok": True, "pool_usd": Decimal} (cash + open positions at cost, in dollars) or {"ok": False, "why"}.
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
    per = Decimal(str(f["per_dollar"]))
    body, why = _call(fetch, BALANCE_PATH, None, "balance")
    if why:
        return _unread(why)
    cash, why = _amount(body, f["cash"], per, "balance")
    if why:
        return _unread(why)
    pos = f["positions"]
    if pos == {"included": True}:
        held = Decimal(0)
    elif "balance_key" in pos:
        held, why = _amount(body, pos["balance_key"], per, "balance")
        if why:
            return _unread(why)
    else:
        held, cursor = Decimal(0), None
        for _ in range(MAX_PAGES):
            params = {**({pos["limit_param"]: PAGE_LIMIT} if pos["limit_param"] else {}),
                      **({pos["cursor_param"]: cursor} if cursor else {})}
            page, why = _call(fetch, pos["path"], params, "positions")
            if why:
                return _unread(why)
            if not isinstance(page, dict) or not isinstance(page.get(pos["list"]), list):
                return _unread(f"key '{pos['list']}' is missing from the positions response")
            for p in page[pos["list"]]:
                v, why = _amount(p, pos["cost"], per, "positions")
                if why:
                    return _unread(why)
                held += v
            cursor = page.get(pos["cursor"])
            if not cursor:
                break
        else:
            return _unread(f"the positions read did not end within {MAX_PAGES} pages")
    return {"ok": True, "pool_usd": cash + held, "why": None}
