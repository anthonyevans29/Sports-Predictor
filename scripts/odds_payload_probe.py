"""
ODDS PAYLOAD PROBE (ARCHITECT 2026-10-07, addendum 4 E, venue-edge quote age, build step 1): READ-ONLY.

"a read-only payload probe the operator runs for one NHL and one NCAA fixture: every field of the odds response,
any update or timestamp field named (law 1; never guess a key)."

It calls the SAME provider endpoint the odds syncs use, through the adapters' own HTTP method (same base URL, same
header, same key, read the same way — config.py loads .env, the adapter reads its env var; the key is never
printed):
  nhl   sync-odds --competition NHL  -> APIHockeyAdapter.list_odds          GET v1.hockey.api-sports.io/odds?game=<id>
  ncaa  sync-odds-football (NFL+NCAA) -> APIAmericanFootballAdapter.list_odds GET v1.american-football.api-sports.io/odds?game=<id>
and prints:
  1. EVERY field of the response, recursively: key path ([] = list element), JSON type, sample values; EVERY list
     element is scanned (Codex on #340: a field only in a late bookmaker/bet/value is still found); --max-items
     limits only the samples PRINTED per path (the total length and count are printed);
  2. every key whose NAME looks like an update/timestamp field (contains update / time / date / last / stamp /
     modif / created / fetched / ts, case-insensitive) — matched on the keys PRESENT, never assumed; and every
     path whose string VALUE parses as a date-time or date, whatever the key is called;
  3. the paths the adapter READS (list_odds) vs the paths present that it DROPS.
Nothing is written to the DB (no DB is opened). Exit 2 on a refusal.
An UNSUCCESSFUL provider response is refused with its reason and NO verdict (Codex on #340), by the adapters' own
_get checks: a non-2xx HTTP status (401 / 429 / 5xx; raise_for_status in the adapter), a body that is not a JSON
object, or a non-empty `errors` field (list, or object with values). A --from-file payload carrying a non-empty
`errors` field is refused the same way.

    python scripts/odds_payload_probe.py --sport nhl  --game <api_hockey game id>            [--out exports/probe_nhl.json]
    python scripts/odds_payload_probe.py --sport ncaa --game <api_american_football game id> [--out exports/probe_ncaa.json]
    python scripts/odds_payload_probe.py --from-file exports/probe_nhl.json [--sport nhl]     # offline review / tests

The game id is the match's provider id (matches.external_ids["api_hockey"] / ["api_american_football"]). A
fixtures export row carries match_id only: pass --match-id <match_id> instead of --game and the probe reads that
one row's external_ids from the DB (DATABASE_URL, opened READ-ONLY via a mode=ro URI; a missing DB file is refused,
never created; SELECT only).
--out writes the raw payload (key-redacted) under exports/ only; a path under data/ (or anywhere else) is refused.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from src.timeutil import utc_now_naive  # noqa: E402
EXPORTS = REPO / "exports"
DATA = REPO / "data"

#: (adapter module, class, the odds sync that uses it, the provider id key in matches.external_ids)
SPORTS = {
    "nhl": ("src.adapters.api_hockey", "APIHockeyAdapter", "sync-odds --competition NHL", "api_hockey"),
    "ncaa": ("src.adapters.api_american_football", "APIAmericanFootballAdapter", "sync-odds-football",
             "api_american_football"),
}
#: The competition a --match-id must belong to, per --sport (NFL and NCAA share the provider id key)
SPORT_COMPETITION = {"nhl": "NHL", "ncaa": "NCAA"}
#: The paths list_odds READS (src/adapters/api_hockey.py:233-262, src/adapters/api_american_football.py:310-339:
#: identical loops): response[] -> bookmakers[] -> name/id, bets[] -> name, values[] -> value/odd. Nothing else.
ADAPTER_READS = (
    "response", "response[]", "response[].bookmakers", "response[].bookmakers[]",
    "response[].bookmakers[].name", "response[].bookmakers[].id",
    "response[].bookmakers[].bets", "response[].bookmakers[].bets[]", "response[].bookmakers[].bets[].name",
    "response[].bookmakers[].bets[].values", "response[].bookmakers[].bets[].values[]",
    "response[].bookmakers[].bets[].values[].value", "response[].bookmakers[].bets[].values[].odd",
    "errors",                                         # _get raises on a non-empty errors field
)
TIME_NAME = re.compile(r"update|time|date|last|stamp|modif|created|fetched|as_?of|(^|_)ts$", re.I)   # + asOf / as_of (Codex on #340)
TS_CAMEL = re.compile(r"[a-z0-9]T[sS]$")  # quoteTs / quoteTS / oddsTS (Codex on #340), never bets / results
_DT = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?)?(Z|[+-]\d{2}:?\d{2})?$")


def jtype(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "str"
    if isinstance(v, list):
        return "list"
    if isinstance(v, dict):
        return "object"
    return type(v).__name__


def walk(obj, max_items: int = 3) -> dict:
    """{path: {"types": set, "samples": [..], "count": n, "list_len": max len, "dt_sample": first date-time-looking
    value or None}} over EVERY field. A list's elements share the path `<path>[]`; EVERY element is descended, so a
    key present only in a late element is still collected. `max_items` caps only the distinct samples KEPT per path
    (for printing); the date-time test runs on every scalar value, not on the samples."""
    out: dict = {}
    cap = max(1, max_items)

    def rec(v, path):
        e = out.setdefault(path, {"types": set(), "samples": [], "count": 0, "list_len": None, "dt_sample": None})
        e["types"].add(jtype(v))
        e["count"] += 1
        if isinstance(v, dict):
            for k, x in v.items():
                rec(x, f"{path}.{k}" if path else str(k))
        elif isinstance(v, list):
            e["list_len"] = max(e["list_len"] or 0, len(v))
            for x in v:
                rec(x, f"{path}[]")
        else:
            if e["dt_sample"] is None and looks_datetime(v):
                e["dt_sample"] = v
            if len(e["samples"]) < cap and v not in e["samples"]:
                e["samples"].append(v)

    rec(obj, "")
    out.pop("", None)
    return out


def looks_datetime(v) -> bool:
    return isinstance(v, str) and bool(_DT.match(v.strip()))


def time_fields(fields: dict) -> dict:
    """{"by_name": [paths whose LAST key matches TIME_NAME], "by_value": [paths with a date-time-looking sample]}."""
    key = lambda p: re.sub(r"\[\]$", "", p).rsplit(".", 1)[-1]
    by_name = [p for p in fields if TIME_NAME.search(key(p)) or TS_CAMEL.search(key(p))]
    by_value = [p for p, e in fields.items() if e.get("dt_sample") is not None
                or any(looks_datetime(s) for s in e["samples"])]
    return {"by_name": sorted(by_name), "by_value": sorted(by_value)}


def dropped(fields: dict) -> list[str]:
    """Paths present in the payload that list_odds never reads (and that are not under a path it never enters)."""
    return sorted(p for p in fields if p not in ADAPTER_READS)


def redact(text: str, key: str | None) -> str:
    return text.replace(key, "[REDACTED]") if key and len(key) >= 6 else text


def _short(v, n=80) -> str:
    s = json.dumps(v, ensure_ascii=False, default=str)
    return s if len(s) <= n else s[: n - 1] + "…"


def _adapters(sport: str | None) -> list:
    """The adapter class(es) whose list_odds acceptance rules apply: the --sport one, else both (from-file)."""
    import importlib
    sys.path.insert(0, str(REPO))
    keys = [sport] if sport in SPORTS else list(SPORTS)
    return [getattr(importlib.import_module(SPORTS[k][0]), SPORTS[k][1]) for k in keys]


def usable_quotes(payload, sport: str | None = None) -> int:
    """Quotes list_odds would turn into an odds row (Codex on #340), by the ADAPTER's own rules: a bet whose name is
    in its _MARKET_MAP, ONE values[] object whose odd parses as a float and whose value normalises to a selection
    for that market (_normalize_selection). Split fields, unknown markets, unnormalisable selections count nothing."""
    def items(o, k):                       # Codex on #340: a schema-drifted scalar container holds no quotes
        v = o.get(k) if isinstance(o, dict) else None
        return v if isinstance(v, list) else []

    n = 0
    for g in items(payload, "response"):
        for bk in items(g, "bookmakers"):
            for bet in items(bk, "bets"):
                if not isinstance(bet, dict):
                    continue
                for v in items(bet, "values"):
                    if not isinstance(v, dict):
                        continue
                    try:
                        float(v.get("odd"))
                    except (TypeError, ValueError):
                        continue
                    for ad in _adapters(sport):
                        name = bet.get("name")     # Codex on #340: a list / object name is no market, never a
                        market = ad._MARKET_MAP.get(name) if isinstance(name, str) else None   # TypeError
                        if market is not None and ad._normalize_selection(market, str(v.get("value") or ""))[0]:
                            n += 1
                            break
    return n


def report(payload, max_items: int = 3, sport: str | None = None) -> list[str]:
    fields = walk(payload, max_items)
    tf = time_fields(fields)
    lines = [f"FIELDS ({len(fields)} key paths; [] = list element; EVERY list element scanned; up to {max_items} "
             f"sample(s) printed per path)"]
    for p, e in fields.items():
        ln = f" len={e['list_len']}" if e["list_len"] is not None else ""
        smp = "" if not e["samples"] else "  e.g. " + " | ".join(_short(s) for s in e["samples"])
        lines.append(f"  {p}  [{'/'.join(sorted(e['types']))}]{ln} x{e['count']}{smp}")
    lines.append("TIME-LIKE KEY NAMES (update/time/date/last/stamp/modif/created/fetched/as_of/ts, on the keys present):")
    lines += [f"  {p}  e.g. {' | '.join(_short(s) for s in fields[p]['samples']) or '(no scalar sample)'}"
              for p in tf["by_name"]] or ["  (none)"]
    lines.append("DATE-TIME-LOOKING VALUES (any key):")
    lines += [f"  {p}  e.g. {_short(fields[p]['dt_sample'] or fields[p]['samples'][0])}"
              for p in tf["by_value"]] or ["  (none)"]
    dr = dropped(fields)
    lines.append(f"ADAPTER: list_odds reads {len([p for p in fields if p in ADAPTER_READS])} of these paths; "
                 f"{len(dr)} present and DROPPED:")
    lines += [f"  {p}" for p in dr] or ["  (none)"]
    cand = [p for p in tf["by_name"] + tf["by_value"] if p in dr]
    # Codex on #340: a quoted price is a values[] OBJECT carrying both value and odd (what list_odds reads);
    # [null] / ["bad"] / [{}] are no market data
    quoted = usable_quotes(payload, sport)
    if not quoted:
        # Codex on #340: a response with no usable quote says nothing about the schema, either way: a time-like
        # field there (a fixture date, a response stamp) cannot be shown to belong to a quote
        lines.append("VERDICT (this payload): INCONCLUSIVE: no usable bookmaker / bet / value quote in this response "
                     "(odds not published yet?), so nothing can be said about a quote-time field"
                     + (f" (time-like fields seen, unattributable: {', '.join(sorted(set(cand)))})" if cand else "")
                     + "; probe a fixture with odds posted")
        return lines
    lines.append("VERDICT (this payload): " + (
        "a time-like field is present and dropped by the adapter: " + ", ".join(sorted(set(cand)))
        + " — whether it is the QUOTE's own time (vs the response's or the fixture's) is for the ruling"
        if cand else "no time-like field present in this payload — no quote time to store"))
    return lines


class Refused(Exception):
    """A refusal (an unsuccessful provider response, no key, a --match-id preflight failure): printed with its
    reason, exit 2, no verdict."""


def payload_refusal(payload) -> str | None:
    """The adapters' own _get rejection (src/adapters/api_hockey.py / api_american_football.py): the body must be
    a JSON object, and a non-empty `errors` field (a list, or an object with values) is an error, never odds."""
    if not isinstance(payload, dict):
        return f"REFUSED: the payload is not a JSON object ({jtype(payload)}) — the adapter's _get reads a dict"
    errs = payload.get("errors")
    if errs and (errs if isinstance(errs, list) else list(errs.values()) if isinstance(errs, dict) else [errs]):
        return (f"REFUSED: the provider returned errors {_short(errs, 200)} — an error response, not an odds "
                f"payload (the adapter's _get raises on it); no verdict")
    return None


def out_path_ok(path: str) -> tuple[bool, str]:
    """--out lands under exports/ only; anything under data/ (law 5) or elsewhere is refused."""
    tgt = Path(path).resolve()
    if tgt == DATA.resolve() or DATA.resolve() in tgt.parents:
        return False, "REFUSED: never write under data/ (law 5)."
    if EXPORTS.resolve() not in tgt.parents:
        return False, f"REFUSED: --out must be under exports/ ({EXPORTS})."
    return True, str(tgt)


def db_path() -> Path:
    sys.path.insert(0, str(REPO))
    from config import settings
    url = settings.database_url
    if not url.startswith("sqlite:///"):
        raise Refused(f"REFUSED: --match-id reads a SQLite DATABASE_URL only (got {url.split(':', 1)[0]})")
    return Path(url[len("sqlite:///"):]).resolve()


def game_for_match(sport: str, match_id: int) -> str:
    """The provider game id of one match, read-only (mode=ro URI; never creates the file)."""
    import sqlite3
    p = db_path()
    if not p.is_file():
        raise Refused(f"REFUSED: no DB file at {p} (never created by a probe)")
    # mode=ro, never immutable (Codex on #340): immutable skips change detection and could read a page torn by a
    # concurrent checkpoint. SQLite may create its own -wal / -shm sidecars for a WAL DB; the content is never written.
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    try:
        row = con.execute("SELECT m.external_ids, c.code FROM matches m LEFT JOIN competitions c "
                          "ON c.id = m.competition_id WHERE m.id = ?", (match_id,)).fetchone()
    finally:
        con.close()
    if row is None:
        raise Refused(f"REFUSED: match {match_id} not in the DB")
    # Codex on #340: NFL and NCAA share the api_american_football id key; the match must be the asked league's
    want = SPORT_COMPETITION[sport]
    if row[1] != want:
        raise Refused(f"REFUSED: match {match_id} is competition {row[1]!r}, not {want} (--sport {sport}): a "
                      "wrong-league payload never drives the verdict")
    try:                                   # Codex on #340: damaged external_ids is a refusal, never a traceback
        ext = json.loads(row[0]) if isinstance(row[0], str) else row[0]
    except ValueError:
        ext = None
    if ext is None and row[0] is None:
        ext = {}
    if not isinstance(ext, dict):
        raise Refused(f"REFUSED: match {match_id}'s external_ids is not a JSON object ({_short(row[0], 60)})")
    src = SPORTS[sport][3]
    if not ext.get(src):
        raise Refused(f"REFUSED: match {match_id} has no '{src}' id (external_ids keys: {sorted(ext)})")
    return str(ext[src])


def fetch(sport: str, game: str) -> tuple[dict, str | None]:
    """One GET through the adapter's own _get (same endpoint, header and key as the sync). Returns (payload, key)
    — the key only so it can be redacted from anything printed or written."""
    import importlib

    sys.path.insert(0, str(REPO))
    import config  # noqa: F401  (loads .env exactly as cli.py does, before the adapter reads its env var)
    mod, cls, _, _ = SPORTS[sport]
    ad = getattr(importlib.import_module(mod), cls)()
    key = ad._headers.get("x-apisports-key") or None
    if not key:
        raise Refused("REFUSED: no provider key in env/.env for this adapter — nothing fetched")
    # The same request _get makes, and the same acceptance checks (status, JSON object, empty `errors`): a probe
    # wants to SEE an odds payload, never to read an error response as one. No retry: a 429 is refused, stated.
    import requests
    base = importlib.import_module(mod).DIRECT_BASE
    try:
        resp = requests.get(f"{base}/odds", headers=ad._headers, params={"game": game}, timeout=30)
    except requests.RequestException as e:   # DNS / TLS / connection / timeout: a refusal (Codex on #340)
        raise Refused(redact(f"REFUSED: the request to {base}/odds failed ({type(e).__name__}: {e}); nothing "
                             "fetched, no verdict", key)) from None
    print(f"GET {base}/odds?game={game} -> HTTP {resp.status_code} · "
          f"x-ratelimit-requests-remaining {resp.headers.get('x-ratelimit-requests-remaining')}")
    return check_response(resp, key), key


def check_response(resp, key: str | None = None) -> dict:
    """The adapter's acceptance of one HTTP response (raise_for_status + JSON + errors), as a refusal: a non-2xx
    status, a non-JSON body or a non-empty `errors` field raises Refused with the reason (key-redacted)."""
    if not 200 <= resp.status_code < 300:
        try:
            body = _short(resp.json(), 200)
        except ValueError:
            body = "(not JSON)"
        raise Refused(redact(f"REFUSED: HTTP {resp.status_code} — an unsuccessful response (the adapter's "
                             f"raise_for_status raises on it); body {body}; no verdict", key))
    try:
        payload = resp.json()
    except ValueError:
        raise Refused(f"REFUSED: response is not JSON (HTTP {resp.status_code}); no verdict")
    why = payload_refusal(payload)
    if why:
        raise Refused(redact(why, key))
    return payload


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--sport", choices=sorted(SPORTS), help="nhl or ncaa (the adapter the odds sync uses)")
    ap.add_argument("--game", help="the provider game id (matches.external_ids[<source>])")
    ap.add_argument("--match-id", dest="match_id", type=int,
                    help="read the provider id from this match's external_ids (DB opened read-only)")
    ap.add_argument("--from-file", dest="from_file", help="read a saved payload instead of calling the provider")
    ap.add_argument("--out", help="write the raw payload (key-redacted) here — under exports/ only")
    ap.add_argument("--max-items", type=int, default=3,
                    help="samples printed per key path (default 3); every list element is always scanned")
    a = ap.parse_args(argv)
    if a.out:
        ok, msg = out_path_ok(a.out)
        if not ok:
            print(msg)
            return 2
    key = None
    if a.from_file:
        try:
            with open(a.from_file) as f:
                payload = json.load(f)
        except (OSError, ValueError) as e:      # missing / unreadable / truncated: a refusal (Codex on #340)
            print(f"REFUSED: cannot read --from-file {a.from_file!r} as JSON ({type(e).__name__}: {e}); no verdict")
            return 2
        print(f"PAYLOAD from file {a.from_file}" + (f" (sport {a.sport})" if a.sport else ""))
        why = payload_refusal(payload)
        if why:
            print(why)
            return 2
    else:
        if a.sport and not a.game and a.match_id is not None:
            try:
                a.game = game_for_match(a.sport, a.match_id)
            except Refused as e:
                print(str(e))
                return 2
            print(f"match {a.match_id} -> provider game id {a.game}")
        if not (a.sport and a.game):
            print("REFUSED: pass --sport and --game or --match-id (or --from-file)")
            return 2
        mod, cls, sync, src = SPORTS[a.sport]
        print(f"ODDS PAYLOAD PROBE · {a.sport.upper()} · the endpoint {sync} uses ({cls}, provider id key '{src}') · "
              f"{utc_now_naive():%Y-%m-%dT%H:%M:%SZ}")
        try:
            payload, key = fetch(a.sport, a.game)
        except Refused as e:
            print(str(e))
            return 2
    text = "\n".join(report(payload, a.max_items, a.sport))
    print(redact(text, key))
    if a.out:
        os.makedirs(os.path.dirname(out_path_ok(a.out)[1]), exist_ok=True)
        with open(out_path_ok(a.out)[1], "w") as f:
            f.write(redact(json.dumps(payload, indent=2, ensure_ascii=False), key))
        print(f"raw payload written: {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
