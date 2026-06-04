"""open-meteo weather fetch + the presenter view. `fetch_fn` is injected for headless tests.

open-meteo is free + key-less. Hosts must be egress-allowlisted: `geocoding-api.open-meteo.com`,
`api.open-meteo.com`. Returns a plain dict (title + data) so the conversation agent can wrap it in
an `Artifact(kind="weather", ...)` without a circular import.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable

_GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST = "https://api.open-meteo.com/v1/forecast"

# WMO weather codes → short label (the frontend maps the code → an emoji/icon).
WMO: dict[int, str] = {
    0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog", 51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Showers", 81: "Showers", 82: "Violent showers", 85: "Snow showers", 86: "Snow showers",
    95: "Thunderstorm", 96: "Thunderstorm + hail", 99: "Thunderstorm + hail",
}

Fetch = Callable[[str], dict]


def looks_like_weather(text: str) -> bool:
    return bool(re.search(
        r"\b(weather|wether|forecast|m[ée]t[ée]o|temperature|how (?:hot|cold|warm))\b", text, re.I))


def extract_location(text: str) -> str | None:
    """Pull a place out of 'weather in Brussels' / 'forecast for Paris tomorrow'."""
    pat = r"\b(?:in|for|at)\s+([A-Za-zÀ-ÿ'’.\- ]+?)(?:\s+(?:today|tomorrow|now|this\b).*)?$"
    m = re.search(pat, text.strip(), re.I)
    if m:
        loc = m.group(1).strip(" ?.!")
        return loc or None
    return None


def _default_fetch(url: str) -> dict:
    from jarvis.security.egress import guarded_request

    with guarded_request(url, timeout=10.0) as resp:
        return json.loads(resp.read())


def _label(code: int | None) -> str:
    return WMO.get(int(code), "—") if code is not None else "—"


def weather_view(location: str, *, fetch_fn: Fetch | None = None) -> dict | None:
    """Fetch current + 5-day forecast for `location`. Returns artifact {title, data} or None if the
    place can't be geocoded / the fetch fails. Pure aside from `fetch_fn` (injected in tests)."""
    fetch_fn = fetch_fn or _default_fetch
    try:
        place = _geocode(fetch_fn, location)
        if place is None:
            return None
        lat, lon = place["latitude"], place["longitude"]
        label = ", ".join(p for p in (place.get("name"), place.get("country")) if p)
        params = (
            f"latitude={lat}&longitude={lon}&timezone=auto&forecast_days=5"
            "&current=temperature_2m,apparent_temperature,weather_code,wind_speed_10m"
            "&daily=weather_code,temperature_2m_max,temperature_2m_min"
        )  # open-meteo defaults: °C + km/h (metric — what we display)
        fc = fetch_fn(f"{_FORECAST}?{params}")
    except Exception:  # noqa: BLE001 — a fetch/parse failure degrades to "no card" (caller falls back)
        return None

    cur = fc.get("current") or {}
    daily = fc.get("daily") or {}
    days = daily.get("time") or []
    forecast = [
        {"date": days[i], "hi": round(daily["temperature_2m_max"][i]),
         "lo": round(daily["temperature_2m_min"][i]),
         "code": daily["weather_code"][i], "label": _label(daily["weather_code"][i])}
        for i in range(len(days))
    ]
    return {
        "title": f"Weather · {label}",
        "data": {
            "location": label,
            "unit": "°C",
            "wind_unit": "km/h",
            "current": {
                "temp": round(cur.get("temperature_2m")) if cur.get("temperature_2m") is not None
                else None,
                "feels": round(cur.get("apparent_temperature"))
                if cur.get("apparent_temperature") is not None else None,
                "wind": round(cur.get("wind_speed_10m")) if cur.get("wind_speed_10m") is not None
                else None,
                "code": cur.get("weather_code"),
                "label": _label(cur.get("weather_code")),
            },
            "daily": forecast,
        },
    }


def _geocode(fetch_fn: Fetch, location: str) -> dict | None:
    """Resolve a place to lat/lon. Tries the full string, then comma-parts (so 'Rocourt, Liège,
    Belgium' still resolves via 'Rocourt' / 'Liège'). URL-encodes the name (spaces/accents)."""
    import urllib.parse

    candidates = [location, *[p.strip() for p in location.split(",")]]
    seen: set[str] = set()
    for name in candidates:
        if not name or name in seen:
            continue
        seen.add(name)
        q = urllib.parse.quote(name)
        geo = fetch_fn(f"{_GEOCODE}?name={q}&count=1&language=en&format=json")
        results = geo.get("results") or []
        if results:
            return results[0]
    return None
