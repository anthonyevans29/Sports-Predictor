#!/usr/bin/env python3
"""Operator paging: unit failures (OnFailure=sp-notify@%i) and SP-PAGE lines.

    sp_notify.py failure <instance>     # from sp-notify@.service
    sp_notify.py page "<message>"

Always writes a receipt (kind "failure" / "page") and prints to the journal.
Delivery beyond that: if SP_NOTIFY_URL is set, HTTP POST of the text body
(ntfy-style topic URL or any webhook that takes a plain-text body). The
channel itself is ARCHITECT-RULE H0-13 — until ruled, receipts + journal only,
and the receipt says `delivered: false` (never claims a page that didn't go).
"""
from __future__ import annotations

import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_common as c  # noqa: E402


def unit_for(instance: str) -> str:
    return {"backup": "sp-backup.service", "prune": "sp-backup-prune.service",
            "web": "sp-web.service"}.get(instance, f"sp-chain@{instance}.service")


def journal_tail(unit: str, n: int = 30) -> list[str]:
    try:
        out = subprocess.run(["journalctl", "-u", unit, "-n", str(n), "--no-pager", "-o", "cat"],
                             capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [c.redact(x) for x in out.splitlines()]


def deliver(kind: str, title: str, body: str, extra: dict | None = None) -> bool:
    url = c.setting("SP_NOTIFY_URL")
    delivered, err = False, None
    if url:
        try:
            req = urllib.request.Request(url, data=body.encode()[:4000], method="POST",
                                         headers={"Title": title[:200], "Priority": "high"})
            with urllib.request.urlopen(req, timeout=20) as r:
                delivered = 200 <= r.status < 300
        except Exception as e:  # noqa: BLE001 — a failed page must still be receipted
            err = f"{type(e).__name__}"
    c.append_receipt({"kind": kind, "title": title, "body": c.redact(body)[:2000],
                      "delivered": delivered, "channel": "url" if url else None,
                      **({"error": err} if err else {}), **(extra or {})})
    print(f"[{kind}] {title}: {c.redact(body)[:300]} (delivered={delivered})", flush=True)
    return delivered


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    c.load_host_env()
    if len(argv) != 2 or argv[0] not in ("failure", "page"):
        print(__doc__)
        return 2
    if argv[0] == "failure":
        unit = unit_for(argv[1])
        tail = journal_tail(unit)
        deliver("failure", f"sports-predictor FAILED: {unit}",
                "\n".join([f"{unit} failed on {c.host_name()}"] + tail), {"unit": unit})
    else:
        deliver("page", "sports-predictor: operator action", argv[1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
