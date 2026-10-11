## 2026-10-11 (kalshi-event-probe — ARCHITECT addendum 37 item 2, Law 1 first)
- `scripts/kalshi_event_probe.py` (new, read-only, GET only, no key): per event ticker (default: the nine KXNCAAFGAME events of the addendum 37 receipt), the event object and its markets at any status, every time field verbatim, the ticker's date stamp as written; `--out` appends one JSON line per event. For the operator's laptop run; its console and file go in the matcher PR before item 2 is built.
- docs/CLI.md: its row. Tests: tests/test_kalshi_event_probe.py (fake fetch, no network).
