"""Lane 4 (ARCHITECT 2026-10-03): the Kalshi trade-API probe is READ-ONLY by construction — any non-GET
method is refused before a request is made; the RSA-PSS signature covers timestamp + METHOD + path
(with /trade-api/v2, without the query)."""
import base64
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import kalshi_trade_api_probe as kp  # noqa: E402


def test_non_get_is_refused_before_any_request(monkeypatch):
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: pytest.fail("no request may be made"))
    c = kp.Client("https://example.invalid/trade-api/v2")
    for m in ("POST", "DELETE", "PUT", "PATCH"):
        with pytest.raises(kp.ReadOnly, match="read-only"):
            c.request(m, "/portfolio/orders")


def _crypto():
    try:                                    # a broken install panics (BaseException), not ImportError
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding, rsa
        return hashes, serialization, padding, rsa.generate_private_key(public_exponent=65537, key_size=2048)
    except BaseException as e:  # noqa: B036
        pytest.skip(f"cryptography unusable here ({e.__class__.__name__}); the probe reports it as a finding")


def test_signature_is_rsa_pss_over_timestamp_method_path(tmp_path, monkeypatch):
    hashes, serialization, padding, key = _crypto()
    p = tmp_path / "k.pem"
    p.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption()))
    seen = {}

    class R:
        status_code = 200

        def json(self):
            return {"balance": 1}

    def fake_get(url, params=None, headers=None, timeout=None):
        seen.update(url=url, headers=headers)
        return R()
    import requests
    monkeypatch.setattr(requests, "get", fake_get)
    c = kp.Client("https://x.invalid/trade-api/v2", "kid", str(p))
    assert c.request("GET", "/portfolio/balance", {"limit": 1}, auth=True)[0] == 200
    h = seen["headers"]
    msg = (h["KALSHI-ACCESS-TIMESTAMP"] + "GET" + "/trade-api/v2/portfolio/balance").encode()
    key.public_key().verify(base64.b64decode(h["KALSHI-ACCESS-SIGNATURE"]), msg,
                            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
                            hashes.SHA256())
    assert h["KALSHI-ACCESS-KEY"] == "kid"


def test_no_key_reports_and_fakes_nothing(monkeypatch):
    import requests

    class R:
        status_code = 200

        def json(self):
            return {"exchange_active": True}
    monkeypatch.setattr(requests, "get", lambda *a, **k: R())
    r = kp.probe_env("DEMO", "https://d.invalid/trade-api/v2", None, None)
    assert r["reach"]["http"] == 200 and r["auth"] == "no key configured" and "fills" not in r
