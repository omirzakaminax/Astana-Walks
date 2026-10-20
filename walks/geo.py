"""Geographic helpers. All distances here are STRAIGHT-LINE (great-circle).

Walking times are approximations: straight-line distance x detour factor / walking speed.
They are not real routes.
"""
from __future__ import annotations

import math

from . import config

# Rough bounding box around Astana, used to reject obviously wrong coordinates.
ASTANA_BBOX = (50.95, 71.20, 51.30, 71.70)  # (min_lat, min_lon, max_lat, max_lon)


class InvalidCoordinates(ValueError):
    pass


def validate_coords(lat, lon, require_astana: bool = True) -> tuple[float, float]:
    """Return (lat, lon) as floats or raise InvalidCoordinates with a clear message."""
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        raise InvalidCoordinates("Coordinates must be numbers, e.g. 51.0890, 71.4160.") from None
    if math.isnan(lat_f) or math.isnan(lon_f):
        raise InvalidCoordinates("Coordinates must be numbers, e.g. 51.0890, 71.4160.")
    if not (-90 <= lat_f <= 90 and -180 <= lon_f <= 180):
        raise InvalidCoordinates("Latitude must be between -90 and 90, longitude between -180 and 180.")
    if require_astana:
        min_lat, min_lon, max_lat, max_lon = ASTANA_BBOX
        if not (min_lat <= lat_f <= max_lat and min_lon <= lon_f <= max_lon):
            raise InvalidCoordinates(
                "This prototype only covers Astana. Coordinates should be roughly "
                "lat 50.95–51.30, lon 71.20–71.70."
            )
    return lat_f, lon_f


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# Planning assumptions for walking pace (metres per minute along streets). These are
# planning defaults, not a measurement of anyone's actual speed.
PACES = {"leisurely": 45.0, "normal": 75.0, "brisk": 95.0}


def pace_speed(pace: str | None) -> float:
    """Speed in m/min for a pace name. Request-scoped: never stored globally."""
    if pace in PACES:
        return PACES[pace]
    return config.WALK_SPEED_M_PER_MIN


def approx_walk_minutes(straight_line_m: float, speed_m_per_min: float | None = None) -> int:
    """Approximate one-way walking minutes (rounded up, minimum 1).

    Street distance is estimated as straight-line distance x ROUTE_DETOUR_FACTOR.
    """
    speed = speed_m_per_min or config.WALK_SPEED_M_PER_MIN
    route_m = straight_line_m * config.ROUTE_DETOUR_FACTOR
    return max(1, math.ceil(route_m / speed))


def max_reachable_distance_m(budget_min: int, min_visit_min: int, return_to_start: bool,
                             speed_m_per_min: float | None = None) -> float:
    """Largest straight-line distance that still fits the time budget.

    budget >= walk_there (+ walk_back) + minimum visit time
    """
    speed = speed_m_per_min or config.WALK_SPEED_M_PER_MIN
    free_min = budget_min - min_visit_min
    if free_min <= 0:
        return 0.0
    legs = 2 if return_to_start else 1
    walk_min_one_way = free_min / legs
    return walk_min_one_way * speed / config.ROUTE_DETOUR_FACTOR
