"""Current weather from Open-Meteo (free, no API key; data CC BY 4.0, https://open-meteo.com).

Privacy: we query the weather for the DATASET CENTRE (a public point near EXPO),
never for the user's own coordinates. Results are cached for 15 minutes.
If the request fails, the app simply works without weather.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass

import requests

from . import config

URL = "https://api.open-meteo.com/v1/forecast"
_CACHE: dict[tuple[float, float], tuple[float, "Weather"]] = {}
CACHE_S = 15 * 60


@dataclass
class Weather:
    temperature_c: float
    apparent_c: float | None
    precipitation_mm: float
    wind_ms: float
    code: int
    harsh: bool
    reasons: list[str]          # "cold" | "hot" | "precipitation" | "wind"
    source: str = "Open-Meteo"
    source_url: str = "https://open-meteo.com"
    fetched_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def summary_en(self) -> str:
        """Short factual line for the model prompt."""
        feels = f", feels like {self.apparent_c:.0f}°C" if self.apparent_c is not None else ""
        extra = f"; harsh conditions: {', '.join(self.reasons)}" if self.harsh else "; mild conditions"
        return (f"{self.temperature_c:.0f}°C{feels}, precipitation {self.precipitation_mm:.1f} mm, "
                f"wind {self.wind_ms:.0f} m/s{extra}")


def classify(temp: float, apparent: float | None, precip: float, wind: float) -> tuple[bool, list[str]]:
    feel = apparent if apparent is not None else temp
    reasons = []
    if feel <= -10:
        reasons.append("cold")
    if feel >= 32:
        reasons.append("hot")
    if precip >= 0.3:
        reasons.append("precipitation")
    if wind >= 12:
        reasons.append("wind")
    return bool(reasons), reasons


def current(lat: float, lon: float, session=None, now=time.time) -> Weather | None:
    key = (round(lat, 2), round(lon, 2))
    hit = _CACHE.get(key)
    if hit and now() - hit[0] < CACHE_S:
        return hit[1]
    params = {"latitude": key[0], "longitude": key[1],
              "current": "temperature_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
              "wind_speed_unit": "ms", "timezone": "auto"}
    try:
        r = (session or requests).get(URL, params=params, timeout=config.WEATHER_TIMEOUT_S)
        r.raise_for_status()
        c = r.json()["current"]
        temp = float(c["temperature_2m"])
        app = c.get("apparent_temperature")
        app = float(app) if app is not None else None
        precip = float(c.get("precipitation") or 0)
        wind = float(c.get("wind_speed_10m") or 0)
        harsh, reasons = classify(temp, app, precip, wind)
        w = Weather(temp, app, precip, wind, int(c.get("weather_code") or 0), harsh, reasons,
                    fetched_at=str(c.get("time", "")))
    except Exception:
        return None
    _CACHE[key] = (now(), w)
    return w
