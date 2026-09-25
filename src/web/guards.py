"""
Localhost-only guard for the admin endpoints.

Why this exists: the /admin routes can kick off sync jobs, retrain the model,
and (in the destructive case) drop tables. Even on a 'local' app, that's a
real attack surface if the port is forwarded, exposed to another machine, or
hit by a malicious browser extension.

The guard is conservative: only requests originating from the loopback address
get through. If you ever genuinely want admin access from another machine on
your LAN, swap the implementation here — don't bypass the guard at call sites.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import HTTPException, Request

# IPv4 + IPv6 loopback. We accept both because uvicorn may bind to either.
_LOOPBACK_ADDRESSES = {"127.0.0.1", "::1", "localhost"}

# Methods that can change state. Everything else is treated as read-only.
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def allowed_hosts(bind_host: str) -> list[str]:
    """
    Host-header allowlist for TrustedHostMiddleware (DNS-rebinding guard).

    The loopback names always pass; the configured WEB_HOST passes too unless
    it's a wildcard bind (0.0.0.0 / ::), which names no real host.
    """
    hosts = ["127.0.0.1", "localhost", "[::1]"]
    if bind_host and bind_host not in {"0.0.0.0", "::", *hosts, "::1"}:
        hosts.append(bind_host)
    return hosts


def is_cross_site(method: str, host: str | None, origin: str | None,
                  referer: str | None) -> bool:
    """
    True when a state-changing request was sent by a page on another site (CSRF).

    require_localhost can't catch this: a malicious page open in the operator's
    browser sends its requests from 127.0.0.1. Browsers attach Origin (or at
    least Referer) to cross-site POSTs, so the request is rejected unless that
    header names this app's own host. Requests carrying neither header come
    from non-browser clients (curl, scripts), which aren't a CSRF vector.
    Origin "null" (sandboxed frames, opaque redirects) is always rejected.
    """
    if method.upper() not in _UNSAFE_METHODS:
        return False
    source = origin or referer
    if source is None:
        return False
    if source == "null" or not host:
        return True
    return urlsplit(source).netloc.lower() != host.lower()


def require_localhost(request: Request) -> None:
    """FastAPI dependency. Raises 403 if client is not on loopback."""
    client = request.client
    if client is None:
        # Shouldn't happen for HTTP requests but be defensive
        raise HTTPException(status_code=403, detail="Localhost-only endpoint.")
    if client.host not in _LOOPBACK_ADDRESSES:
        raise HTTPException(
            status_code=403,
            detail=(
                f"This endpoint is localhost-only. "
                f"Your request came from {client.host}."
            ),
        )
