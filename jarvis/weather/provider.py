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


class WeatherUnavailable(Exception):
    """The place resolved but the weather service didn't answer (rate-limited / down / timeout).
    Distinct from 'place not found' (None) so the caller can say so accurately, not 'no access'."""


# Short in-process cache: open-meteo data updates ~15 min, and the free tier rate-limits (HTTP 429),
# so caching avoids hammering it AND makes repeat asks instant. Per process; bypassed when a custom
# `fetch_fn` is injected (tests).
_CACHE_TTL = 900.0
_cache: dict[str, tuple[float, dict]] = {}


def weather_view(location: str, *, fetch_fn: Fetch | None = None) -> dict | None:
    """Current + 5-day forecast for `location`. Returns {title, data}, None if the place can't be
    found, or raises WeatherUnavailable if every source is down. Tries open-meteo, then wttr.in as a
    backup (so an open-meteo 429 doesn't kill weather). Cached ~15 min (default fetch path)."""
    use_cache = fetch_fn is None
    if use_cache:
        import time
        hit = _cache.get(location.strip().lower())
        if hit and time.monotonic() - hit[0] < _CACHE_TTL:
            return hit[1]
    fetch = fetch_fn or _default_fetch
    try:
        view = _open_meteo_view(location, fetch)
    except WeatherUnavailable:
        if fetch_fn is not None:
            raise  # tests inject one fetch_fn; don't reach to the real backup
        view = _wttr_view(location, _default_fetch)  # backup source (raises if it also fails)
    if view is None:
        return None  # genuinely couldn't find the place
    if use_cache:
        import time
        _cache[location.strip().lower()] = (time.monotonic(), view)
    return view


def _open_meteo_view(location: str, fetch: Fetch) -> dict | None:
    try:
        place = _geocode(fetch, location)
    except Exception as exc:  # noqa: BLE001 — geocoding service failed (network/429/timeout)
        raise WeatherUnavailable(str(exc)) from exc
    if place is None:
        return None
    lat, lon = place["latitude"], place["longitude"]
    label = ", ".join(p for p in (place.get("name"), place.get("country")) if p)
    params = (
        f"latitude={lat}&longitude={lon}&timezone=auto&forecast_days=5"
        "&current=temperature_2m,apparent_temperature,weather_code,wind_speed_10m"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min"
    )  # open-meteo defaults: °C + km/h (metric — what we display)
    try:
        fc = fetch(f"{_FORECAST}?{params}")
    except Exception as exc:  # noqa: BLE001 — forecast service down → not "no access", just down
        raise WeatherUnavailable(str(exc)) from exc
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
            "location": label, "unit": "°C", "wind_unit": "km/h",
            "current": {
                "temp": round(cur["temperature_2m"]) if cur.get("temperature_2m") is not None
                else None,
                "feels": round(cur["apparent_temperature"])
                if cur.get("apparent_temperature") is not None else None,
                "wind": round(cur["wind_speed_10m"]) if cur.get("wind_speed_10m") is not None
                else None,
                "code": cur.get("weather_code"), "label": _label(cur.get("weather_code")),
            },
            "daily": forecast,
        },
    }


# wttr.in uses WWO codes; map the common ones to WMO so the frontend icon + label stay consistent.
_WWO_TO_WMO = {
    113: 0, 116: 2, 119: 3, 122: 3, 143: 45, 248: 45, 260: 45,
    176: 61, 263: 51, 266: 51, 293: 61, 296: 61, 353: 80, 299: 63, 302: 65, 356: 81, 359: 82,
    179: 71, 182: 71, 227: 73, 230: 75, 323: 71, 326: 73, 368: 85, 371: 86, 395: 86,
    200: 95, 386: 95, 389: 96, 392: 95,
}


def _wmo_from_wwo(code: object) -> int:
    try:
        return _WWO_TO_WMO.get(int(code), 3)
    except (TypeError, ValueError):
        return 3


def _wttr_view(location: str, fetch: Fetch) -> dict | None:
    """Backup forecast via wttr.in (key-less, separate limits). Maps its j1 JSON to our shape."""
    import urllib.parse

    try:
        data = fetch(f"https://wttr.in/{urllib.parse.quote(location)}?format=j1")
    except Exception as exc:  # noqa: BLE001 — backup also down → genuinely unavailable
        raise WeatherUnavailable(str(exc)) from exc
    cc = (data.get("current_condition") or [{}])[0]
    area = (data.get("nearest_area") or [{}])[0]
    name = (area.get("areaName") or [{}])[0].get("value")
    country = (area.get("country") or [{}])[0].get("value")
    label = ", ".join(p for p in (name, country) if p) or location

    def _num(v: object):  # noqa: ANN202
        try:
            return round(float(v))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    daily = []
    for w in (data.get("weather") or [])[:5]:
        hourly = w.get("hourly") or []
        mid = hourly[len(hourly) // 2] if hourly else {}
        wmo = _wmo_from_wwo(mid.get("weatherCode"))
        daily.append({"date": w.get("date"), "hi": _num(w.get("maxtempC")),
                      "lo": _num(w.get("mintempC")), "code": wmo, "label": _label(wmo)})
    code = _wmo_from_wwo(cc.get("weatherCode"))
    return {
        "title": f"Weather · {label}",
        "data": {
            "location": label, "unit": "°C", "wind_unit": "km/h",
            "current": {"temp": _num(cc.get("temp_C")), "feels": _num(cc.get("FeelsLikeC")),
                        "wind": _num(cc.get("windspeedKmph")), "code": code, "label": _label(code)},
            "daily": daily,
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
