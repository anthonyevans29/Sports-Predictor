"""
Weather context for upcoming matches — Phase 9c.

Uses open-meteo.com (free, no API key). Looks up venue coordinates from
a static mapping and pulls forecast for the match's local time.

Indoor venues return None — we don't want to display irrelevant weather.

The venue mapping is hand-curated for the venues in our DB. New venues
will fall through to None (no weather panel shown) and can be added here
as we cover more leagues.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import logging

import requests

log = logging.getLogger(__name__)

#: Venue → (lat, lon, is_indoor). Indoor venues skip weather fetch.
#: Names should match how the upstream API returns Match.venue. May need
#: fuzzy matching later; for now exact match.
VENUE_COORDS: dict[str, tuple[float, float, bool]] = {
    # ===== MLB stadiums =====
    "Coors Field": (39.7559, -104.9942, False),
    "Yankee Stadium": (40.8296, -73.9262, False),
    "Fenway Park": (42.3467, -71.0972, False),
    "Wrigley Field": (41.9484, -87.6553, False),
    "Dodger Stadium": (34.0739, -118.2400, False),
    "Oracle Park": (37.7786, -122.3893, False),
    "Citi Field": (40.7571, -73.8458, False),
    "Petco Park": (32.7073, -117.1573, False),
    "Truist Park": (33.8908, -84.4678, False),
    "loanDepot park": (25.7782, -80.2197, True),     # retractable roof
    "Minute Maid Park": (29.7570, -95.3552, True),    # retractable roof
    "Daikin Park": (29.7570, -95.3552, True),         # Houston — renamed from Minute Maid (2025)
    "Chase Field": (33.4453, -112.0667, True),        # retractable roof
    "Globe Life Field": (32.7473, -97.0832, True),    # retractable roof
    "Rogers Centre": (43.6414, -79.3894, True),       # retractable roof
    "T-Mobile Park": (47.5914, -122.3325, True),      # retractable roof
    "American Family Field": (43.0280, -87.9712, True),  # retractable roof
    "Journey Bank Ballpark": (43.0280, -87.9712, True),  # Milwaukee renamed 2026 (same park)
    "Tropicana Field": (27.7682, -82.6534, True),     # dome
    "Great American Ball Park": (39.0975, -84.5066, False),
    "PNC Park": (40.4469, -80.0058, False),
    "Progressive Field": (41.4962, -81.6852, False),
    "Comerica Park": (42.3390, -83.0485, False),
    "Target Field": (44.9817, -93.2776, False),
    "Kauffman Stadium": (39.0517, -94.4803, False),
    "Guaranteed Rate Field": (41.8300, -87.6338, False),
    "Citizens Bank Park": (39.9061, -75.1665, False),
    "Nationals Park": (38.8730, -77.0074, False),
    "Camden Yards": (39.2839, -76.6217, False),
    "Oriole Park at Camden Yards": (39.2839, -76.6217, False),  # feed's full name
    "Angel Stadium": (33.8003, -117.8827, False),
    "Sutter Health Park": (38.5803, -121.5133, False),  # A's temp 2025+
    "Busch Stadium": (38.6226, -90.1928, False),

    # ===== Premier League grounds (a starter set; add as needed) =====
    "Emirates Stadium": (51.5549, -0.1084, False),
    "Etihad Stadium": (53.4831, -2.2004, False),
    "Old Trafford": (53.4631, -2.2913, False),
    "Anfield": (53.4308, -2.9608, False),
    "Stamford Bridge": (51.4817, -0.1909, False),
    "Tottenham Hotspur Stadium": (51.6043, -0.0664, False),
    "Goodison Park": (53.4388, -2.9663, False),
    "St James' Park": (54.9756, -1.6217, False),
    "Villa Park": (52.5093, -1.8847, False),
    "London Stadium": (51.5386, -0.0166, False),
    "Selhurst Park": (51.3983, -0.0856, False),
    "Vitality Stadium": (50.7352, -1.8383, False),
    "American Express Stadium": (50.8616, -0.0834, False),
    "Molineux Stadium": (52.5904, -2.1303, False),
    "City Ground": (52.9400, -1.1322, False),
    "Turf Moor": (53.7892, -2.2300, False),
    "St. Mary's Stadium": (50.9058, -1.3911, False),
    "Craven Cottage": (51.4750, -0.2217, False),
    "Brentford Community Stadium": (51.4906, -0.2889, False),
    "Gtech Community Stadium": (51.4906, -0.2889, False),  # alias
    "King Power Stadium": (52.6203, -1.1422, False),
    "Portman Road": (52.0550, 1.1444, False),
}


def lookup_venue(venue: str | None) -> tuple[float, float, bool] | None:
    """Return (lat, lon, is_indoor) for a venue name, or None if unknown."""
    if not venue:
        return None
    # Exact match first
    if venue in VENUE_COORDS:
        return VENUE_COORDS[venue]
    # Known renames / naming-rights aliases → canonical map key
    aliases = {
        "Rate Field": "Guaranteed Rate Field",              # CWS, renamed 2025
        "UNIQLO Field at Dodger Stadium": "Dodger Stadium",  # LAD naming rights
        "Daikin Park": "Daikin Park",                        # HOU (already present)
    }
    if venue in aliases and aliases[venue] in VENUE_COORDS:
        return VENUE_COORDS[aliases[venue]]
    # Loose match — try stripping common prefixes/suffixes
    cleaned = venue.replace(" Stadium", "").replace(" Field", "").replace(" Park", "")
    # also drop a "<Sponsor> at " prefix (e.g. "UNIQLO Field at Dodger Stadium")
    if " at " in cleaned:
        cleaned = cleaned.split(" at ", 1)[1]
    for k, v in VENUE_COORDS.items():
        if k.replace(" Stadium", "").replace(" Field", "").replace(" Park", "") == cleaned:
            return v
    return None


def fetch_weather(
    venue: str | None,
    utc_dt: datetime,
    timeout: float = 4.0,
) -> dict | None:
    """
    Fetch weather forecast/observation for a match's venue at its kickoff time.

    Returns a dict ready for templating, or None if:
      - Venue isn't in our coordinate map
      - Venue is indoor (no weather impact)
      - utc_dt is too far in the future (>14 days, beyond forecast range)
      - utc_dt is too far in the past (>5 days, beyond archive defaults)
      - API call fails

    We swallow exceptions and return None — weather is nice-to-have, not
    critical. Network failures shouldn't break the page.
    """
    coords = lookup_venue(venue)
    if coords is None:
        return None
    lat, lon, is_indoor = coords
    if is_indoor:
        return {"indoor": True, "venue": venue}

    # Open-Meteo split: forecast endpoint covers ±~14 days; past_days param
    # also works for very recent history. We'll use the forecast endpoint
    # and let the API decide what's available.
    now = datetime.utcnow()
    delta = utc_dt - now
    if delta.days > 14:
        return None
    if delta.days < -5:
        return None

    # Round to the nearest hour for the forecast lookup
    target_hour = utc_dt.replace(minute=0, second=0, microsecond=0)
    target_iso = target_hour.strftime("%Y-%m-%dT%H:00")

    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,precipitation,wind_speed_10m,wind_direction_10m,weather_code",
        "temperature_unit": "fahrenheit",  # US-centric defaults; can override later
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "UTC",
        "past_days": 5 if delta.days < 0 else 0,
        "forecast_days": max(2, delta.days + 2),
    }

    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params=params,
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.debug("Weather fetch failed for %s: %s", venue, e)
        return None

    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    if not times:
        return None

    # Find the closest hour to target. Times are ISO strings like "2026-05-20T19:00"
    try:
        idx = times.index(target_iso)
    except ValueError:
        # Fall back to nearest neighbor
        target_ts = target_hour.timestamp()
        nearest_idx = None
        nearest_diff = float("inf")
        for i, t in enumerate(times):
            try:
                t_dt = datetime.strptime(t, "%Y-%m-%dT%H:%M")
                diff = abs(t_dt.timestamp() - target_ts)
                if diff < nearest_diff:
                    nearest_diff = diff
                    nearest_idx = i
            except ValueError:
                continue
        idx = nearest_idx
    if idx is None:
        return None

    def _at(key: str):
        arr = hourly.get(key) or []
        return arr[idx] if idx < len(arr) else None

    temp = _at("temperature_2m")
    precip = _at("precipitation")
    wind = _at("wind_speed_10m")
    wind_dir = _at("wind_direction_10m")
    code = _at("weather_code")

    return {
        "indoor": False,
        "venue": venue,
        "temperature_f": round(temp, 1) if temp is not None else None,
        "wind_mph": round(wind, 1) if wind is not None else None,
        "wind_dir_deg": round(wind_dir) if wind_dir is not None else None,
        "precipitation_in": round(precip, 2) if precip is not None else None,
        "condition": _weather_code_label(code),
        "is_high_altitude": venue == "Coors Field",  # callout for context
    }


def fetch_weather_historical(
    venue: str | None,
    utc_dt: datetime,
    timeout: float = 8.0,
) -> dict | None:
    """
    Historical weather for a PAST game via Open-Meteo's ARCHIVE endpoint
    (archive-api.open-meteo.com/v1/archive). Same free API, same variables +
    wind_direction, same return shape as fetch_weather — but pulls reanalysis
    data by date range instead of a forecast. For backfilling game_weather on
    prior-season games so weather can be a trainable signal.

    Returns None for indoor venues, unknown venues, or on any failure (weather
    is nice-to-have; a failed pull shouldn't abort a backfill).
    """
    coords = lookup_venue(venue)
    if coords is None:
        return None
    lat, lon, is_indoor = coords
    if is_indoor:
        return {"indoor": True, "venue": venue}

    target_hour = utc_dt.replace(minute=0, second=0, microsecond=0)
    target_iso = target_hour.strftime("%Y-%m-%dT%H:%M")
    day = target_hour.strftime("%Y-%m-%d")

    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,precipitation,wind_speed_10m,wind_direction_10m,weather_code",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "UTC",
        "start_date": day,
        "end_date": day,
    }

    try:
        r = requests.get(
            "https://archive-api.open-meteo.com/v1/archive",
            params=params,
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.debug("Historical weather fetch failed for %s @ %s: %s", venue, day, e)
        return None

    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    if not times:
        return None

    try:
        idx = times.index(target_iso)
    except ValueError:
        # nearest-hour fallback within the day
        try:
            target_ts = target_hour.timestamp()
            idx = min(range(len(times)),
                      key=lambda i: abs(datetime.fromisoformat(times[i])
                                        .replace(tzinfo=timezone.utc).timestamp() - target_ts))
        except Exception:
            return None

    def _at(key):
        arr = hourly.get(key) or []
        return arr[idx] if idx < len(arr) else None

    temp = _at("temperature_2m")
    precip = _at("precipitation")
    wind = _at("wind_speed_10m")
    wind_dir = _at("wind_direction_10m")
    code = _at("weather_code")

    return {
        "indoor": False,
        "venue": venue,
        "temperature_f": round(temp, 1) if temp is not None else None,
        "wind_mph": round(wind, 1) if wind is not None else None,
        "wind_dir_deg": round(wind_dir) if wind_dir is not None else None,
        "precipitation_in": round(precip, 2) if precip is not None else None,
        "condition": _weather_code_label(code),
        "is_high_altitude": venue == "Coors Field",
    }

# Open-Meteo / WMO weather codes — coarse mapping to human labels
_WMO_LABELS = {
    0: "Clear",
    1: "Mostly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Freezing fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    80: "Rain showers",
    81: "Heavy showers",
    82: "Violent showers",
    95: "Thunderstorm",
    96: "Thunderstorm w/ hail",
    99: "Heavy thunderstorm w/ hail",
}


def _weather_code_label(code) -> str | None:
    if code is None:
        return None
    try:
        return _WMO_LABELS.get(int(code), f"Code {code}")
    except (ValueError, TypeError):
        return None
