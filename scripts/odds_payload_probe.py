"""
ODDS PAYLOAD PROBE (ARCHITECT 2026-10-07, addendum 4 E, venue-edge quote age, build step 1): READ-ONLY.

"a read-only payload probe the operator runs for one NHL and one NCAA fixture: every field of the odds response,
any update or timestamp field named (law 1; never guess a key)."
ADDENDUM 32 item 5 (ARCHITECT 2026-10-09): "THE PROBE GAINS SOCCER AND MLB. [...] scripts/odds_payload_probe.py
reads the odds answer of api_football and of api_baseball through each adapter's own odds call, as it does for the
two it has, with the same refusals. Nothing is stored for a sport until its payload has been read."

It calls the SAME provider endpoint the odds syncs use, with the adapter's own base URL, header and key (read the
same way — config.py loads .env, the adapter reads its env var; the key is never printed):
  nhl    sync-odds --competition NHL  -> APIHockeyAdapter.list_odds          GET v1.hockey.api-sports.io/odds?game=<id>
  ncaa   sync-odds-football (NFL+NCAA) -> APIAmericanFootballAdapter.list_odds GET v1.american-football.api-sports.io/odds?game=<id>
  soccer sync-odds --competition <CODE> (IngestionService.sync_odds) -> APIFootballAdapter.list_odds
           GET <adapter base_url>/odds?fixture=<id>   (v3.football.api-sports.io by default; API_FOOTBALL_HOST may
           name the RapidAPI host, whose headers the adapter's own session carries). --competition is REQUIRED: the
           payload's league id must be that code's _CODE_TO_LEAGUE_ID entry (src/adapters/api_football.py).
  mlb    sync-odds --competition MLB --season S (IngestionService.sync_odds_mlb) -> APIBaseballClient:
           --season S alone: list_odds_window, the call the sync makes FIRST and for every game:
             GET v1.baseball.api-sports.io/odds?league=1&season=S   (no game id: the sync matches games by names
             and start time, never by a stored id)
           --season S --game G (or --match-id N): list_odds_for_game, the sync's M11a rollover fallback:
             GET v1.baseball.api-sports.io/odds?league=1&season=S&game=G
and prints:
  1. EVERY field of the response, recursively: key path ([] = list element), JSON type, sample values; EVERY list
     element is scanned (Codex on #340: a field only in a late bookmaker/bet/value is still found); --max-items
     limits only the samples PRINTED per path (the total length and count are printed);
  2. every key whose NAME looks like an update/timestamp field (contains update / time / date / last / stamp /
     modif / created / fetched / ts, case-insensitive) — matched on the keys PRESENT, never assumed; and every
     path whose string VALUE parses as a date-time or date, whatever the key is called;
  3. the paths the adapter's odds call READS vs the paths present that it DROPS (per --sport; ADAPTER_READS_BY_SPORT).
Nothing is written to the DB (no DB is opened). Exit 2 on a refusal.
An UNSUCCESSFUL provider response is refused with its reason and NO verdict (Codex on #340), by the adapters' own
_get checks: a non-2xx HTTP status (401 / 429 / 5xx; raise_for_status / `not r.ok` in the adapter), a body that is
not a JSON object, or a non-empty `errors` field (list, or object with values). A --from-file payload carrying a
non-empty `errors` field is refused the same way.

    python scripts/odds_payload_probe.py --sport nhl  --game <api_hockey game id>            [--out exports/probe_nhl.json]
    python scripts/odds_payload_probe.py --sport ncaa --game <api_american_football game id> [--out exports/probe_ncaa.json]
    python scripts/odds_payload_probe.py --sport soccer --competition PL --game <api_football fixture id>
    python scripts/odds_payload_probe.py --sport mlb --season 2026                        # the sync's window call
    python scripts/odds_payload_probe.py --sport mlb --season 2026 --game <api_baseball game id>   # its fallback
    python scripts/odds_payload_probe.py --from-file exports/probe_nhl.json [--sport nhl]     # offline review / tests

The game id is the match's provider id (matches.external_ids["api_hockey"] / ["api_american_football"] /
["api_football"] / ["api_baseball"]). A fixtures export row carries match_id only: pass --match-id <match_id>
instead of --game and the probe reads that one row's external_ids from the DB (DATABASE_URL, opened READ-ONLY via a
mode=ro URI; a missing DB file is refused, never created; SELECT only). The row's competition must be the asked
one (NHL / NCAA / MLB / the --competition code). An MLB row carries "api_baseball" only where the host's api-sports
fallback wrote it (src/ingestion/mlb_apisports.py); a row without it is refused, never guessed.
--out writes the raw payload (key-redacted) under exports/ only; a path under data/ (or anywhere else) is refused.
"""
from __future__ import annotations

import argparse
import json
import math
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
    # addendum 32 item 5: IngestionService.sync_odds keys matches by adapter.source_name (service.py:718)
    "soccer": ("src.adapters.api_football", "APIFootballAdapter", "sync-odds --competition <soccer code>",
               "api_football"),
    # sync_odds_mlb (service.py:1454) uses APIBaseballClient directly, never the MLBStatsAPIAdapter
    "mlb": ("src.adapters.api_baseball", "APIBaseballClient", "sync-odds --competition MLB (sync_odds_mlb)",
            "api_baseball"),
}
#: The competition a --match-id must belong to, per --sport (NFL and NCAA share the provider id key); soccer's is
#: the --competition given
SPORT_COMPETITION = {"nhl": "NHL", "ncaa": "NCAA", "mlb": "MLB"}
#: The provider league id per --sport (src/adapters/api_hockey.py NHL_LEAGUE_ID; api_american_football.py
#: _CODE_TO_LEAGUE["NCAA"]; api_baseball.py MLB_LEAGUE_ID): a direct --game payload that names another league is
#: refused (Codex on #340). Soccer's comes from --competition via api_football._CODE_TO_LEAGUE_ID (soccer_league_id).
SPORT_LEAGUE_ID = {"nhl": 57, "ncaa": 2, "mlb": 1}


def soccer_league_id(competition: str | None) -> int:
    """The api_football league id the soccer odds sync's competition maps to (_CODE_TO_LEAGUE_ID, read from the
    adapter module, never restated here). An unmapped or missing code is a refusal."""
    from src.adapters.api_football import _CODE_TO_LEAGUE_ID
    code = (competition or "").upper()
    if not code:
        raise Refused("REFUSED: --sport soccer needs --competition <code> (the sync-odds competition; its league id "
                      "is what the payload is checked against)")
    if code not in _CODE_TO_LEAGUE_ID:
        raise Refused(f"REFUSED: competition {code!r} is not in api_football's _CODE_TO_LEAGUE_ID "
                      f"(known: {sorted(_CODE_TO_LEAGUE_ID)})")
    return _CODE_TO_LEAGUE_ID[code]


def _league_target(sport: str, competition: str | None) -> tuple[int, str]:
    """(the league id the payload must name, its label)."""
    if sport == "soccer":
        return soccer_league_id(competition), competition.upper()
    return SPORT_LEAGUE_ID[sport], sport.upper()


def league_check(payload, sport: str, competition: str | None = None) -> tuple[bool | None, str]:
    """(True, ...) when every response[].league.id the payload carries is --sport's league (soccer: --competition's);
    (False, why) when one is another league's; (None, why) when the payload names no league id (unverified, said,
    never assumed). A soccer check without a mapped --competition raises Refused."""
    want, label = _league_target(sport, competition)
    ids, unlabelled = set(), 0
    resp = payload.get("response") if isinstance(payload, dict) else None
    for g in resp if isinstance(resp, list) else []:   # Codex on #340: a scalar container names no league
        lg = g.get("league") if isinstance(g, dict) else None
        if not isinstance(lg, dict) or lg.get("id") is None:
            # Codex on #340: a league-less item whose quotes would drive the verdict leaves the payload unverified
            unlabelled += usable_quotes({"response": [g]}, sport) > 0
            continue
        lid = lg["id"]
        if isinstance(lid, str) and lid.strip().isdigit():
            lid = int(lid)                     # Codex on #340: a numeric-string id is still the league named
        if isinstance(lid, bool) or not isinstance(lid, int):
            return False, (f"REFUSED: the payload carries a malformed league id {_short(lg['id'], 40)}: a league the "
                           "probe cannot read never drives the verdict")
        ids.add(lid)
    if not ids:
        return None, (f"LEAGUE UNVERIFIED: a direct --game id is not checked against the DB and this payload names no "
                      f"response[].league.id (NFL and NCAA share game ids); use --match-id for a verified {label} "
                      "fixture")
    if ids != {want}:
        return False, (f"REFUSED: the payload's league id(s) {sorted(ids)} are not {label}'s ({want}): a "
                       "wrong-league payload never drives the verdict")
    if unlabelled:
        return None, (f"LEAGUE UNVERIFIED: {unlabelled} quote-bearing response item(s) name no response[].league.id "
                      f"(NFL and NCAA share game ids): their quotes are not shown to be {label}'s; use "
                      "--match-id for a verified fixture")
    return True, f"league verified from the payload: {label} ({want})"
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
#: addendum 32 item 5, read from the code (law 1):
#: APIFootballAdapter.list_odds (src/adapters/api_football.py:356-425): response[] -> bookmakers[] -> name (no id),
#: bets[] -> name ("Match Winner" / "Goals Over/Under"), values[] -> value/odd. Nothing else.
_SOCCER_READS = (
    "response", "response[]", "response[].bookmakers", "response[].bookmakers[]",
    "response[].bookmakers[].name",
    "response[].bookmakers[].bets", "response[].bookmakers[].bets[]", "response[].bookmakers[].bets[].name",
    "response[].bookmakers[].bets[].values", "response[].bookmakers[].bets[].values[]",
    "response[].bookmakers[].bets[].values[].value", "response[].bookmakers[].bets[].values[].odd",
    "errors",                                         # _get raises on a non-empty errors field (api_football.py:248)
)
#: APIBaseballClient.list_odds_window / list_odds_for_game -> _parse_game_odds (src/adapters/api_baseball.py:190-302)
#: and the value parsers (:311-356, _MARKET_PARSERS :375): response[] -> game.id, game.date (commence_time),
#: game.teams.home.name / away.name; bookmakers[] -> name (no id); bets[] -> name ("Home/Away" / "Over/Under" /
#: "Asian Handicap"); values[] -> value, odd, handicap (the line). Nothing else.
_MLB_READS = (
    "response", "response[]", "response[].game", "response[].game.id", "response[].game.date",
    "response[].game.teams", "response[].game.teams.home", "response[].game.teams.home.name",
    "response[].game.teams.away", "response[].game.teams.away.name",
    "response[].bookmakers", "response[].bookmakers[]", "response[].bookmakers[].name",
    "response[].bookmakers[].bets", "response[].bookmakers[].bets[]", "response[].bookmakers[].bets[].name",
    "response[].bookmakers[].bets[].values", "response[].bookmakers[].bets[].values[]",
    "response[].bookmakers[].bets[].values[].value", "response[].bookmakers[].bets[].values[].odd",
    "response[].bookmakers[].bets[].values[].handicap",
    "errors",                                         # _get raises on a non-empty errors field (api_baseball.py:143)
)
ADAPTER_READS_BY_SPORT = {"nhl": ADAPTER_READS, "ncaa": ADAPTER_READS, "soccer": _SOCCER_READS, "mlb": _MLB_READS}
#: The adapter call named in the read/drop listing, per --sport (None: a --from-file read with no --sport)
ADAPTER_CALL = {"nhl": "APIHockeyAdapter.list_odds", "ncaa": "APIAmericanFootballAdapter.list_odds",
                "soccer": "APIFootballAdapter.list_odds", "mlb": "APIBaseballClient._parse_game_odds",
                None: "list_odds (nhl/ncaa; no --sport given)"}
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


def dropped(fields: dict, sport: str | None = None) -> list[str]:
    """Paths present in the payload that --sport's odds call never reads (no --sport: the nhl/ncaa list_odds)."""
    reads = ADAPTER_READS_BY_SPORT.get(sport, ADAPTER_READS)
    return sorted(p for p in fields if p not in reads)


def redact(text: str, key: str | None) -> str:
    return text.replace(key, "[REDACTED]") if key and len(key) >= 6 else text


def _short(v, n=80) -> str:
    s = json.dumps(v, ensure_ascii=False, default=str)
    return s if len(s) <= n else s[: n - 1] + "…"


#: The sports whose list_odds share one loop and a _MARKET_MAP / _normalize_selection pair (hockey, football)
_MAP_SPORTS = ("nhl", "ncaa")


def _adapters(sport: str | None) -> list:
    """The adapter class(es) whose list_odds acceptance rules apply: the --sport one, else both (from-file)."""
    import importlib
    sys.path.insert(0, str(REPO))
    keys = [sport] if sport in _MAP_SPORTS else list(_MAP_SPORTS)
    return [getattr(importlib.import_module(SPORTS[k][0]), SPORTS[k][1]) for k in keys]


def _priced(price) -> bool:
    try:
        p = float(price)
    except (TypeError, ValueError):
        return False
    return math.isfinite(p) and p > 1.0       # Codex on #340: 0 / 1 / NaN / inf is no price (close.py needs > 1.0)


def _offline_rows(payload, sport: str) -> list:
    """The rows the soccer / MLB adapter's OWN odds parse makes of this payload, offline (addendum 32 item 5): the
    adapter's _get is replaced by the payload on an instance built without a key or a session, so no request is
    made and nothing is stored. A payload the adapter's parse raises on yields nothing (the sync stores nothing for
    it either: sync_odds counts a raising fetch as skipped)."""
    import importlib
    sys.path.insert(0, str(REPO))
    mod, cls = SPORTS[sport][0], SPORTS[sport][1]
    klass = getattr(importlib.import_module(mod), cls)
    ad = object.__new__(klass)                # no __init__: no key read, no session, no network
    ad._get = lambda path, params=None: payload
    try:
        if sport == "soccer":
            return list(ad.list_odds("probe-offline"))
        return list(ad.list_odds_window(season=0))
    except Exception:                          # noqa: BLE001 — schema drift the adapter cannot parse: no rows
        return []


def usable_quotes(payload, sport: str | None = None) -> int:
    """Quotes the --sport odds call would turn into an odds row (Codex on #340), by the ADAPTER's own rules, at a
    finite decimal price above 1 (what the close reads). nhl / ncaa: a bet whose name is in its _MARKET_MAP, ONE
    values[] object whose odd parses as a float and whose value normalises to a selection for that market
    (_normalize_selection). soccer / mlb (addendum 32 item 5): the rows APIFootballAdapter.list_odds /
    APIBaseballClient.list_odds_window themselves build from the payload (_offline_rows). No --sport: nhl / ncaa
    only, as before, so that the quotes counted come from the same adapter whose reads the drop listing uses
    (Codex on #406): a soccer or MLB payload is read with its --sport. Split fields, unknown markets,
    unnormalisable selections and impossible prices count nothing."""
    if sport in ("soccer", "mlb"):
        return sum(_priced(r.price_decimal) for r in _offline_rows(payload, sport))
    return _map_quotes(payload, sport)


def _map_quotes(payload, sport: str | None) -> int:
    """usable_quotes for the _MARKET_MAP adapters (nhl / ncaa; None = either)."""
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
                        odd = float(v.get("odd"))
                    except (TypeError, ValueError):
                        continue
                    if not (math.isfinite(odd) and odd > 1.0):
                        continue           # Codex on #340: 0 / 1 / NaN / inf is no price (close.py needs > 1.0)
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
    dr = dropped(fields, sport)
    reads = ADAPTER_READS_BY_SPORT.get(sport, ADAPTER_READS)
    lines.append(f"ADAPTER: {ADAPTER_CALL.get(sport, ADAPTER_CALL[None])} reads "
                 f"{len([p for p in fields if p in reads])} of these paths; {len(dr)} present and DROPPED:")
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
    if not payload:
        # Codex on #340: an empty object is no provider response (and, written under exports/, the receipts would
        # refuse it as a damaged export)
        return "REFUSED: the payload is an empty object — no provider response; no verdict, nothing written"
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
    if tgt.exists() and not tgt.is_file():
        return False, f"REFUSED: --out {tgt} exists and is not a file."
    anc = next((a for a in tgt.parents if a.exists()), None)
    if anc is not None and not anc.is_dir():       # Codex on #340: never a FileExistsError from makedirs
        return False, f"REFUSED: --out {tgt}: {anc} is a file, not a directory."
    from src.walters.venue_quote_age import EXPORT_NAME, MIRROR_DIR
    if EXPORT_NAME.search(tgt.name) or (EXPORTS.resolve() / MIRROR_DIR) in tgt.parents:
        # Codex on #340: a generated Desk export name (or the host mirror) is reserved, existing or not: a probe
        # payload there would replace an export or read as a damaged one to the receipts
        return False, (f"REFUSED: --out {tgt.name} is a reserved desk export name/location; use e.g. "
                       "exports/probe_nhl.json.")
    if tgt.is_file():
        # Codex on #340: never replace a desk document under any name
        try:
            with open(tgt) as f:
                doc = json.load(f)
        except (OSError, ValueError, UnicodeDecodeError):
            doc = None
        if isinstance(doc, dict) and "desk_meta" in doc:
            return False, f"REFUSED: --out {tgt} is an existing desk export: the probe never overwrites one."
    try:
        db = db_path()
    except Refused:
        db = None                              # a non-SQLite URL: no DB file to alias
    dbs = () if db is None else (db, *(Path(str(db) + x) for x in ("-wal", "-shm", "-journal")))

    def same(a, b) -> bool:
        try:
            return os.path.samefile(a, b)
        except OSError:
            return False
    # Codex on #340: by file identity too: a hard link to the DB is the DB
    if tgt in dbs or (tgt.exists() and any(x.exists() and same(tgt, x) for x in dbs)):
        # Codex on #340: a DATABASE_URL under exports/ is still the DB; the read-only probe never overwrites it
        return False, f"REFUSED: --out is the configured database (or its sidecar) {db}: the probe is read-only."
    return True, str(tgt)


def db_path() -> Path:
    sys.path.insert(0, str(REPO))
    from config import settings
    url = settings.database_url
    if not url.startswith("sqlite:///"):
        raise Refused(f"REFUSED: --match-id reads a SQLite DATABASE_URL only (got {url.split(':', 1)[0]})")
    return Path(url[len("sqlite:///"):]).resolve()


def game_for_match(sport: str, match_id: int, competition: str | None = None) -> str:
    """The provider game id of one match, read-only (mode=ro URI; never creates the file). The match must be the
    asked competition: NHL / NCAA / MLB by --sport, soccer's the --competition code (mapped in api_football)."""
    if sport == "soccer":
        soccer_league_id(competition)          # an unmapped / missing code refuses before the DB is opened
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
    want = competition.upper() if sport == "soccer" else SPORT_COMPETITION[sport]
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
    gid = ext[src]                         # Codex on #340: the id itself must be a scalar, never [123] / {...}
    if isinstance(gid, bool) or not isinstance(gid, (int, str)) or not str(gid).strip():
        raise Refused(f"REFUSED: match {match_id}'s '{src}' id is not a string or integer ({_short(gid, 60)})")
    return str(gid)


def request_spec(sport: str, game: str | None, season: int | None = None):
    """(adapter instance, base URL, headers, params, timeout, key) for --sport's odds call, built from the adapter's
    OWN attributes (law 1; nothing restated):
      nhl / ncaa: module DIRECT_BASE, instance _headers, params {"game": id}           (api_hockey.py:79,233-234;
                  api_american_football.py list_odds:310)
      soccer:     instance base_url + its session headers (x-apisports-key, or the RapidAPI pair when
                  API_FOOTBALL_HOST names it), params {"fixture": id}                    (api_football.py:211-222,371)
      mlb:        APIBaseballClient.from_env() base_url, header {"x-apisports-key": key}, params
                  {"league": MLB_LEAGUE_ID, "season": S} (list_odds_window, api_baseball.py:207-208), plus
                  "game": id for list_odds_for_game (api_baseball.py:245-247)
    A missing key is a refusal; nothing is fetched."""
    import importlib

    sys.path.insert(0, str(REPO))
    import config  # noqa: F401  (loads .env exactly as cli.py does, before the adapter reads its env var)
    mod, cls, _, _ = SPORTS[sport]
    m = importlib.import_module(mod)
    no_key = "REFUSED: no provider key in env/.env for this adapter — nothing fetched"
    if sport == "soccer":
        try:
            ad = getattr(m, cls)()
        except ValueError:                     # APIFootballAdapter.__init__ raises on a missing API_FOOTBALL_KEY
            raise Refused(no_key) from None
        return ad, ad.base_url, dict(ad._session.headers), {"fixture": game}, 30, ad.api_key or None
    if sport == "mlb":
        ad = getattr(m, cls).from_env()        # None when neither API_BASEBALL_KEY nor API_FOOTBALL_KEY is set
        if ad is None:
            raise Refused(no_key)
        params = {"league": m.MLB_LEAGUE_ID, "season": season}
        if game is not None:
            params["game"] = game
        return ad, ad.base_url, {"x-apisports-key": ad.api_key}, params, 15, ad.api_key
    ad = getattr(m, cls)()
    key = ad._headers.get("x-apisports-key") or None
    if not key:
        raise Refused(no_key)
    return ad, m.DIRECT_BASE, ad._headers, {"game": game}, 30, key


def fetch(sport: str, game: str | None, season: int | None = None) -> tuple[dict, str | None]:
    """One GET through the adapter's own request (same endpoint, header and key as the sync). Returns (payload, key)
    — the key only so it can be redacted from anything printed or written."""
    from urllib.parse import urlencode

    _, base, headers, params, timeout, key = request_spec(sport, game, season)
    # The same request _get makes, and the same acceptance checks (status, JSON object, empty `errors`): a probe
    # wants to SEE an odds payload, never to read an error response as one. No retry: a 429 is refused, stated.
    import requests
    try:
        resp = requests.get(f"{base}/odds", headers=headers, params=params, timeout=timeout)
    except requests.RequestException as e:   # DNS / TLS / connection / timeout: a refusal (Codex on #340)
        raise Refused(redact(f"REFUSED: the request to {base}/odds failed ({type(e).__name__}: {e}); nothing "
                             "fetched, no verdict", key)) from None
    print(f"GET {base}/odds?{urlencode(params)} -> HTTP {resp.status_code} · "
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
    ap.add_argument("--sport", choices=sorted(SPORTS),
                    help="nhl, ncaa, soccer or mlb (the adapter the odds sync uses)")
    ap.add_argument("--game", help="the provider game / fixture id (matches.external_ids[<source>]); mlb: the "
                                   "per-game fallback call (without it, mlb probes the sync's window call)")
    ap.add_argument("--match-id", dest="match_id", type=int,
                    help="read the provider id from this match's external_ids (DB opened read-only)")
    ap.add_argument("--competition", help="soccer only, REQUIRED: the sync-odds competition code (e.g. PL); the "
                                          "payload's league id must be its api_football league")
    ap.add_argument("--season", type=int, help="mlb only, REQUIRED to fetch: the season sync-odds --competition MLB "
                                               "--season passes (league=1&season=S)")
    ap.add_argument("--from-file", dest="from_file", help="read a saved payload instead of calling the provider")
    ap.add_argument("--out", help="write the raw payload (key-redacted) here — under exports/ only")
    ap.add_argument("--max-items", type=int, default=3,
                    help="samples printed per key path (default 3); every list element is always scanned")
    a = ap.parse_args(argv)
    # Codex on #340: one input mode only; a conflicting selector is refused, never silently ignored
    chosen = [n for n, v in (("--from-file", a.from_file), ("--game", a.game), ("--match-id", a.match_id))
              if v is not None]
    if len(chosen) > 1:
        print(f"REFUSED: {' and '.join(chosen)} select different inputs; give exactly one (no verdict)")
        return 2
    # addendum 32 item 5: a selector that does not belong to the sport is refused, never silently ignored
    if a.competition is not None and a.sport != "soccer":
        print("REFUSED: --competition is for --sport soccer only (no verdict)")
        return 2
    if a.season is not None and a.sport != "mlb":
        print("REFUSED: --season is for --sport mlb only (no verdict)")
        return 2
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
        if a.sport:                            # Codex on #340: a saved payload is league-checked like a fetch
            try:
                ok, msg = league_check(payload, a.sport, a.competition)
            except Refused as e:
                print(str(e))
                return 2
            print(msg)
            if ok is False:
                return 2
            if ok is None:
                text = "\n".join(report(payload, a.max_items, a.sport))
                print(text.replace("VERDICT (this payload): ", "VERDICT (this payload; LEAGUE UNVERIFIED): "))
                return _write_out(a, payload, key)
    else:
        try:
            if a.sport == "soccer":
                soccer_league_id(a.competition)   # before the DB or the provider is touched
            if a.sport == "mlb" and a.season is None:
                raise Refused("REFUSED: --sport mlb needs --season (the sync's league=1&season=S call)")
        except Refused as e:
            print(str(e))
            return 2
        if a.sport and not a.game and a.match_id is not None:
            try:
                a.game = game_for_match(a.sport, a.match_id,
                                        **({"competition": a.competition} if a.sport == "soccer" else {}))
            except Refused as e:
                print(str(e))
                return 2
            print(f"match {a.match_id} -> provider game id {a.game}")
        if not (a.sport and (a.game or a.sport == "mlb")):
            print("REFUSED: pass --sport and --game or --match-id (or --from-file); mlb: --season [--game]")
            return 2
        mod, cls, sync, src = SPORTS[a.sport]
        call = ("list_odds_window" if a.game is None else "list_odds_for_game") if a.sport == "mlb" else "list_odds"
        print(f"ODDS PAYLOAD PROBE · {(a.competition or a.sport).upper()} · the endpoint {sync} uses "
              f"({cls}.{call}, provider id key '{src}') · {utc_now_naive():%Y-%m-%dT%H:%M:%SZ}")
        try:
            payload, key = (fetch(a.sport, a.game, season=a.season) if a.sport == "mlb"
                            else fetch(a.sport, a.game))
            ok, msg = league_check(payload, a.sport, a.competition)   # Codex on #340: every fetch
        except Refused as e:
            print(str(e))
            return 2
        if ok is False:
            print(msg)
            return 2
        if a.match_id is None or ok:           # --match-id is DB-verified; a payload with no league id stays quiet
            print(msg)
        if a.match_id is None:
            if ok is None:
                text = "\n".join(report(payload, a.max_items, a.sport))
                text = text.replace("VERDICT (this payload): ", "VERDICT (this payload; LEAGUE UNVERIFIED): ")
                print(redact(text, key))
                return _write_out(a, payload, key)
    text = "\n".join(report(payload, a.max_items, a.sport))
    print(redact(text, key))
    return _write_out(a, payload, key)


def _write_out(a, payload, key) -> int:
    if a.out:
        os.makedirs(os.path.dirname(out_path_ok(a.out)[1]), exist_ok=True)
        with open(out_path_ok(a.out)[1], "w") as f:
            f.write(redact(json.dumps(payload, indent=2, ensure_ascii=False), key))
        print(f"raw payload written: {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
