#!/usr/bin/env python3
"""Operator paging: unit failures (OnFailure=sp-notify@%i) and SP-PAGE lines.

    sp_notify.py failure <instance>     # from sp-notify@.service
    sp_notify.py page "<message>"

Always writes a receipt (kind "failure" / "page") and prints to the journal —
the receipts log is the permanent record; a held PASS pages AND logs.
Delivery (H0-13, ruled 2026-09-27): ntfy.sh. POST of the text body to
https://ntfy.sh/<NTFY_TOPIC>, the private topic name read from the checkout's
.env (Anthony subscribes on his phone; no account, zero cost). NTFY_SERVER
overrides the base URL. No topic = receipts + journal only, and the receipt
says `delivered: false` (never claims a page that didn't go).
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
            "web": "sp-web.service", "exports-squash": "sp-exports-squash.service",
            "closing-watch": "sp-closing-watch.service", "cup-observe": "sp-cup-observe.service"}.get(
        instance, f"sp-chain@{instance}.service")


def journal_tail(unit: str, n: int = 30) -> list[str]:
    try:
        out = subprocess.run(["journalctl", "-u", unit, "-n", str(n), "--no-pager", "-o", "cat"],
                             capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [c.redact(x) for x in out.splitlines()]


# ARCHITECT 2026-10-12, addendum 47 item 7(b): "For sp-closing-watch.service, by name, the unit's failure page goes
# out at most once in thirty minutes. Every failure still writes its receipt, and a receipt whose page was held back
# says so and names the page it stands behind." (A unit that ticks every minute would page 1,440 times a day.)
THROTTLED_UNITS = ("sp-closing-watch.service",)
THROTTLE_MIN = 30


def held_behind(unit: str, now=None) -> dict | None:
    """For a throttled unit: the failure page that went out for it within the last THROTTLE_MIN minutes (a receipt
    of kind failure for the unit, not itself held back, and delivered: a page ntfy did not accept, or with no topic,
    did not go out, so the next failure tries again), as {"ts", "title"}; else None (the page goes out)."""
    import json
    from datetime import timedelta
    if unit not in THROTTLED_UNITS:
        return None
    p = c.receipts_path()
    if not p.exists():
        return None
    now = now or c.utc_now()
    since = now - timedelta(minutes=THROTTLE_MIN)
    last = None
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (r.get("kind") == "failure" and r.get("unit") == unit and not r.get("page_held_back")
                and r.get("delivered") is True):   # Codex on #457: a page that was not delivered did not go out
            last = r
    if not last:
        return None
    from datetime import datetime
    try:
        ts = datetime.fromisoformat(str(last["ts"]).replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return None
    return {"ts": last["ts"], "title": last.get("title")} if ts >= since else None


TOPIC_VARS = ("NTFY_TOPIC", "NTFY_CARD_TOPIC")


def _raw_topic(var: str) -> str:
    return c.setting(var) or c._dotenv().get(var) or ""


def topic_problems() -> list[str]:
    """Startup validation (cosmetics lane C, 2026-09-29): an ntfy topic with
    whitespace anywhere (a pasted trailing space or newline, a space inside)
    would page a DIFFERENT topic, or none. The value is never printed: the
    topic name is the only secret on a public ntfy server."""
    out = []
    for var in TOPIC_VARS:
        raw = _raw_topic(var)
        if raw and any(ch.isspace() for ch in raw):
            out.append(f"{var} contains whitespace ({len(raw)} chars; value not shown) — "
                       f"fix it in .env: ntfy would page a different topic, or none")
    return out


def ntfy_url(topic_var: str = "NTFY_TOPIC") -> str | None:
    """topic_var: NTFY_TOPIC (operator pages) or NTFY_CARD_TOPIC (the
    window-card deltas, a SECOND private topic, spec 2026-09-27). A topic
    with whitespace is refused (None), never silently trimmed."""
    raw = _raw_topic(topic_var)
    if any(ch.isspace() for ch in raw):
        return None
    topic = raw
    if not topic:
        return None
    base = (c.setting("NTFY_SERVER") or c._dotenv().get("NTFY_SERVER") or "https://ntfy.sh")
    return f"{base.rstrip('/')}/{topic}"


def deliver(kind: str, title: str, body: str, extra: dict | None = None,
            topic_var: str = "NTFY_TOPIC", priority: str = "high") -> bool:
    url = ntfy_url(topic_var)
    delivered, err = False, None
    if url is None and any(ch.isspace() for ch in _raw_topic(topic_var)):
        err = "invalid_topic_whitespace"
    if url:
        try:
            req = urllib.request.Request(url, data=body.encode()[:4000], method="POST",
                                         headers={"Title": title[:200], "Priority": priority})
            with urllib.request.urlopen(req, timeout=20) as r:
                delivered = 200 <= r.status < 300
        except Exception as e:  # noqa: BLE001 — a failed page must still be receipted
            err = f"{type(e).__name__}"
    c.append_receipt({"kind": kind, "title": title, "body": c.redact(body)[:2000],
                      "delivered": delivered, "channel": "ntfy" if url else None,
                      **({"error": err} if err else {}), **(extra or {})})
    print(f"[{kind}] {title}: {c.redact(body)[:300]} (delivered={delivered})", flush=True)
    return delivered


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    c.load_host_env()
    for p in topic_problems():
        print(f"✗ {p}", flush=True)
    if len(argv) != 2 or argv[0] not in ("failure", "page"):
        print(__doc__)
        return 2
    if argv[0] == "failure":
        unit = unit_for(argv[1])
        tail = journal_tail(unit)
        title = f"sports-predictor FAILED: {unit}"
        body = "\n".join([f"{unit} failed on {c.host_name()}"] + tail)
        behind = held_behind(unit)
        if behind:                    # addendum 47 item 7(b): receipted, the page held back
            c.append_receipt({"kind": "failure", "title": title, "body": c.redact(body)[:2000], "delivered": False,
                              "channel": None, "unit": unit, "page_held_back": True,
                              "stands_behind": behind})
            print(f"[failure] {title}: page held back (at most one in {THROTTLE_MIN} min for {unit}); stands "
                  f"behind the page of {behind['ts']}", flush=True)
            return 0
        deliver("failure", title, body, {"unit": unit})
    else:
        deliver("page", "sports-predictor: operator action", argv[1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
