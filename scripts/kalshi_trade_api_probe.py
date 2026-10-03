"""
KALSHI TRADE-API PROBE (ARCHITECT 2026-10-03, lane 4): "PROBE (read-only, no
orders): Kalshi trade API — can a limit order be placed and cancelled via the
API from the host (auth model, demo environment, maker/taker flags, fee
fields on fills)? Receipt only; order placement itself is a separate ruling."

READ-ONLY BY CONSTRUCTION: the client sends GET only — any other method raises
before a socket opens. No order is created, amended or cancelled.

What it answers, on the host, with a receipt line each:
  1. REACH     GET /exchange/status on PROD and DEMO (no auth): the host can
               reach the trading API (and the demo environment exists).
  2. AUTH      the auth model — API key id + RSA private key, each request
               signed RSA-PSS (MGF1-SHA256, salt = digest length) over
               timestamp_ms + METHOD + path; headers KALSHI-ACCESS-KEY /
               -TIMESTAMP / -SIGNATURE. With a key configured, GET
               /portfolio/balance proves the signature (and that the key may
               trade-read). Without one: "no key configured" (nothing faked).
  3. ORDERS    GET /portfolio/orders?limit=5: the order objects' keys (type,
               side, action, price fields, post-only / time-in-force flags as
               the API names them) — the shape a limit order and its cancel use.
  4. FILLS     GET /portfolio/fills?limit=20: the fill keys — is_taker (the
               maker/taker flag) and fee_cost (the charged fee) when present,
               with counts over the sample.

Config (env; never printed): KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY_PATH
(PROD), KALSHI_DEMO_API_KEY_ID, KALSHI_DEMO_PRIVATE_KEY_PATH (DEMO; demo keys are
separate). Optional: KALSHI_TRADE_BASE / KALSHI_DEMO_BASE overrides.

    python3 scripts/kalshi_trade_api_probe.py [--demo-only] [--json out.json]
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from collections import Counter

PROD = os.getenv("KALSHI_TRADE_BASE", "https://api.elections.kalshi.com/trade-api/v2")
DEMO = os.getenv("KALSHI_DEMO_BASE", "https://demo-api.kalshi.co/trade-api/v2")


class ReadOnly(RuntimeError):
    pass


def _signer(key_path: str):
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except BaseException:                   # ImportError, or a broken install's panic
        raise ReadOnly("python package `cryptography` is not usable on this machine — RSA-PSS "
                       "signing needs it (finding: add it before any trading lane)")
    with open(key_path, "rb") as f:
        key = serialization.load_pem_private_key(f.read(), password=None)

    def sign(msg: str) -> str:
        sig = key.sign(msg.encode(), padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                                                 salt_length=padding.PSS.DIGEST_LENGTH), hashes.SHA256())
        return base64.b64encode(sig).decode()
    return sign


class Client:
    def __init__(self, base: str, key_id: str | None = None, key_path: str | None = None):
        self.base, self.key_id = base.rstrip("/"), key_id
        self.sign = _signer(key_path) if key_id and key_path else None

    def request(self, method: str, path: str, params: dict | None = None, auth: bool = False):
        if method != "GET":
            raise ReadOnly(f"REFUSED: {method} {path} — this probe is read-only (no orders)")
        import requests
        from urllib.parse import urlparse
        url = self.base + path
        headers = {}
        if auth:
            if not self.sign:
                return None, "no key configured"
            ts = str(int(time.time() * 1000))
            signed_path = urlparse(url).path                 # includes /trade-api/v2, excludes the query
            headers = {"KALSHI-ACCESS-KEY": self.key_id, "KALSHI-ACCESS-TIMESTAMP": ts,
                       "KALSHI-ACCESS-SIGNATURE": self.sign(ts + "GET" + signed_path)}
        r = requests.get(url, params=params or {}, headers=headers, timeout=20)
        try:
            body = r.json()
        except ValueError:
            body = {"_text": r.text[:200]}
        return r.status_code, body


def probe_env(name: str, base: str, key_id: str | None, key_path: str | None) -> dict:
    out = {"env": name, "base": base, "key_configured": bool(key_id and key_path)}
    try:
        c = Client(base, key_id, key_path)
    except ReadOnly as e:
        out["auth"] = str(e)
        c = Client(base)
    except OSError as e:
        out["auth"] = f"private key unreadable: {e.__class__.__name__}"
        c = Client(base)
    try:
        code, body = c.request("GET", "/exchange/status")
        out["reach"] = {"http": code, "body": body}
    except Exception as e:  # noqa: BLE001 — a probe reports, never crashes
        out["reach"] = {"error": f"{e.__class__.__name__}: {e}"}
        return out
    if "auth" in out:
        return out
    code, body = c.request("GET", "/portfolio/balance", auth=True)
    out["auth"] = ("no key configured" if code is None else
                   {"http": code, "ok": code == 200, "keys": sorted(body)[:12] if isinstance(body, dict) else None})
    if code != 200:
        return out
    code, body = c.request("GET", "/portfolio/orders", {"limit": 5}, auth=True)
    orders = (body or {}).get("orders") or []
    out["orders"] = {"http": code, "n_sample": len(orders),
                     "keys": sorted({k for o in orders for k in o}),
                     "types": dict(Counter(o.get("type") for o in orders))}
    code, body = c.request("GET", "/portfolio/fills", {"limit": 20}, auth=True)
    fills = (body or {}).get("fills") or []
    keys = sorted({k for f in fills for k in f})
    out["fills"] = {"http": code, "n_sample": len(fills), "keys": keys,
                    "has_is_taker": "is_taker" in keys,
                    "fee_fields": [k for k in keys if "fee" in k],
                    "is_taker_counts": dict(Counter(str(f.get("is_taker")) for f in fills))}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Kalshi trade-API probe (read-only, no orders)")
    ap.add_argument("--demo-only", action="store_true")
    ap.add_argument("--json", default=None, help="also write the receipt as JSON here (never under data/)")
    a = ap.parse_args(argv)
    envs = [] if a.demo_only else [("PROD", PROD, os.getenv("KALSHI_API_KEY_ID"), os.getenv("KALSHI_PRIVATE_KEY_PATH"))]
    envs.append(("DEMO", DEMO, os.getenv("KALSHI_DEMO_API_KEY_ID"), os.getenv("KALSHI_DEMO_PRIVATE_KEY_PATH")))
    receipt = [probe_env(*e) for e in envs]
    print("KALSHI TRADE-API PROBE (read-only; GET only; no order created, amended or cancelled)")
    for r in receipt:
        print(f"\n== {r['env']} {r['base']} · key configured: {r['key_configured']}")
        print(f"  REACH  {json.dumps(r.get('reach'))[:300]}")
        print(f"  AUTH   {json.dumps(r.get('auth'))[:300]}")
        if "orders" in r:
            print(f"  ORDERS {json.dumps(r['orders'])[:600]}")
        if "fills" in r:
            print(f"  FILLS  {json.dumps(r['fills'])[:600]}")
    if a.json:
        if "data" in os.path.abspath(a.json).split(os.sep):
            print("REFUSED: never write under data/ (law 5)")
            return 2
        with open(a.json, "w") as f:
            json.dump(receipt, f, indent=2, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
