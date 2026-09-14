"""
Ballpark wind orientation: turn an absolute wind direction into a baseball-
relevant "blowing out / in / cross" classification, given each park's compass
bearing from home plate to center field.

Convention notes (these are the easy place to get a sign wrong, so they're
explicit):
  - Open-Meteo `wind_direction_10m` is the METEOROLOGICAL direction the wind
    comes FROM, in degrees (0 = from north, 90 = from east).
  - Park orientation here is the bearing from home plate TOWARD center field,
    degrees from north (0 = CF is due north of the plate).
  - Wind blows OUT (toward the outfield, helping fly balls) when it comes FROM
    behind home plate — i.e. the "from" direction is roughly OPPOSITE the CF
    bearing. Wind blows IN when it comes FROM center field — "from" direction ≈
    CF bearing. So the relevant angle is between the wind's "from" bearing and
    the bearing from CF back to the plate (= orientation + 180).

Orientations below are the documented home-plate→CF bearings (rule 1.04 puts
most parks ENE; all MLB parks fall ~0–150°). Values are approximate (±10–15°)
and good enough for an out/in/cross classification, NOT for fine modeling. Domed
/ retractable-roof parks are omitted (wind doesn't apply when closed); they fall
through to None.
"""
from __future__ import annotations

# venue name (as the feed sends it) -> home-plate→CF bearing in degrees from N.
# Approximate, from public ballpark-orientation references.
PARK_CF_BEARING: dict[str, float] = {
    "Fenway Park": 45,
    "Yankee Stadium": 78,
    "Oriole Park at Camden Yards": 32,
    "Camden Yards": 32,
    "Progressive Field": 0,
    "Comerica Park": 150,
    "Kauffman Stadium": 50,
    "Target Field": 80,
    "Guaranteed Rate Field": 135,         # The Cell points SE
    "Rate Field": 135,                    # CWS renamed 2025
    "Angel Stadium": 45,
    "Daikin Park": 20,                    # Houston (roof often closed)
    "Minute Maid Park": 20,
    "Wrigley Field": 30,
    "Great American Ball Park": 30,
    "PNC Park": 115,
    "Busch Stadium": 65,
    "Citizens Bank Park": 15,
    "Nationals Park": 30,
    "Citi Field": 30,
    "Truist Park": 70,
    "Coors Field": 0,
    "Dodger Stadium": 25,
    "UNIQLO Field at Dodger Stadium": 25,  # LAD naming rights
    "Oracle Park": 90,                    # SF faces ~due east
    "Petco Park": 0,
    "Chase Field": 0,                     # AZ (roof often closed)
    "loanDepot park": 40,                 # Miami (roof often closed)
    "American Family Field": 0,           # Milwaukee (roof often closed)
    "Journey Bank Ballpark": 0,           # Milwaukee renamed 2026 (same park)
    "Globe Life Field": 135,              # Texas (roof often closed)
    "Rogers Centre": 0,                   # Toronto (roof often closed)
    "T-Mobile Park": 0,                   # Seattle (roof sometimes closed)
    "Sutter Health Park": 0,              # A's temp park (approx)
    "PNC Park ": 115,
}


def _ang_diff(a: float, b: float) -> float:
    """Smallest absolute angle between two bearings, 0–180."""
    d = abs((a - b) % 360)
    return min(d, 360 - d)


def wind_effect(venue: str | None, wind_from_deg: float | None,
                wind_mph: float | None) -> dict | None:
    """
    Classify wind relative to the park. Returns:
      {"component": "out"|"in"|"cross", "out_mph": float, "label": str}
    or None if we can't classify (unknown park, missing data).

    out_mph is the wind component along the plate→CF axis: positive = helping
    fly balls (blowing out), negative = suppressing (blowing in). This is the
    number a totals model would actually want.
    """
    if not venue or wind_from_deg is None or wind_mph is None:
        return None
    bearing = PARK_CF_BEARING.get(venue)
    if bearing is None:
        return None

    import math
    # Direction the wind is GOING (toward), vs the plate→CF axis.
    wind_to = (wind_from_deg + 180) % 360
    # angle between where wind is going and where CF is
    theta = _ang_diff(wind_to, bearing)
    # component along plate->CF axis: cos(theta) * speed
    out_mph = round(wind_mph * math.cos(math.radians(theta)), 1)

    if theta <= 45:
        component = "out"
    elif theta >= 135:
        component = "in"
    else:
        component = "cross"

    if component == "out":
        label = f"blowing out to CF ~{abs(out_mph):.0f} mph"
    elif component == "in":
        label = f"blowing in from CF ~{abs(out_mph):.0f} mph"
    else:
        label = f"crosswind ~{wind_mph:.0f} mph"

    return {"component": component, "out_mph": out_mph, "label": label,
            "park_cf_bearing": bearing, "approx": True}
