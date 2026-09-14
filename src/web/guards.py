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

from fastapi import HTTPException, Request

# IPv4 + IPv6 loopback. We accept both because uvicorn may bind to either.
_LOOPBACK_ADDRESSES = {"127.0.0.1", "::1", "localhost"}


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
