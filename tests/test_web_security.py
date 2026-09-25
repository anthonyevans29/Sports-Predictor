"""Web-layer security guards: CSRF origin check + trusted-host allowlist."""
import pytest
from fastapi.testclient import TestClient

from src.web.app import app
from src.web.guards import allowed_hosts, is_cross_site

HOST = "127.0.0.1:8000"


@pytest.fixture
def client():
    # Loopback client address, so require_localhost passes and only the
    # cross-site check decides.
    return TestClient(app, base_url=f"http://{HOST}", client=("127.0.0.1", 50000))


# --- is_cross_site (pure) -----------------------------------------------------

@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
def test_safe_methods_never_cross_site(method):
    assert not is_cross_site(method, HOST, "http://evil.example", None)


def test_same_origin_post_allowed():
    assert not is_cross_site("POST", HOST, f"http://{HOST}", None)


def test_foreign_origin_post_rejected():
    assert is_cross_site("POST", HOST, "http://evil.example", None)


def test_foreign_referer_rejected_when_origin_absent():
    assert is_cross_site("POST", HOST, None, "http://evil.example/page")


def test_null_origin_rejected():
    assert is_cross_site("POST", HOST, "null", None)


def test_headerless_client_allowed():
    # curl / scripts send neither header and aren't a CSRF vector
    assert not is_cross_site("POST", HOST, None, None)


def test_port_mismatch_rejected():
    assert is_cross_site("POST", HOST, "http://127.0.0.1:9999", None)


# --- allowed_hosts ------------------------------------------------------------

def test_allowed_hosts_wildcard_bind_adds_nothing():
    assert allowed_hosts("0.0.0.0") == ["127.0.0.1", "localhost", "[::1]"]


def test_allowed_hosts_named_bind_is_added():
    assert "mybox.lan" in allowed_hosts("mybox.lan")


# --- through the app ----------------------------------------------------------

def test_cross_site_post_to_admin_rejected(client):
    r = client.post("/admin/jobs/evaluate", data={"sport": "soccer"},
                    headers={"Origin": "http://evil.example"})
    assert r.status_code == 403
    assert "Cross-site" in r.text


def test_cross_site_post_to_match_refresh_rejected(client):
    r = client.post("/matches/1/refresh", headers={"Origin": "http://evil.example"})
    assert r.status_code == 403


def test_same_origin_post_reaches_route(client):
    # Unknown action -> the route's own 404, proving the guard let it through
    r = client.post("/admin/jobs/no-such-action", headers={"Origin": f"http://{HOST}"})
    assert r.status_code == 404


def test_rebinding_host_rejected(client):
    r = client.get("/healthz", headers={"Host": "evil.example:8000"})
    assert r.status_code == 400


def test_loopback_host_allowed(client):
    assert client.get("/healthz").json() == {"ok": True}
    assert client.get("/healthz", headers={"Host": "localhost:8000"}).status_code == 200


def test_vendored_assets_served(client):
    for path in ("/static/css/tailwind.css", "/static/vendor/htmx-1.9.10.min.js",
                 "/static/vendor/chart-4.4.0.umd.js"):
        assert client.get(path).status_code == 200, path
