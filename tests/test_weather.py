"""Weather presenter — detection, location extraction, view building (mocked fetch). No network."""

from __future__ import annotations

from jarvis.weather import provider


def test_detection() -> None:
    assert provider.looks_like_weather("what's the weather in Paris?")
    assert provider.looks_like_weather("5-day forecast")
    assert provider.looks_like_weather("how hot is it today")
    assert provider.looks_like_weather("what's the wether like")  # common typo
    assert provider.looks_like_weather("la météo demain")
    assert not provider.looks_like_weather("add milk to my list")


def test_extract_location() -> None:
    assert provider.extract_location("weather in Brussels") == "Brussels"
    assert provider.extract_location("forecast for New York tomorrow") == "New York"
    assert provider.extract_location("what's the weather") is None


def _fake_fetch(geo: dict, forecast: dict):
    def fetch(url: str) -> dict:
        return geo if "geocoding" in url else forecast
    return fetch


def test_weather_view_builds_artifact_data() -> None:
    geo = {"results": [{"latitude": 50.85, "longitude": 4.35, "name": "Brussels",
                        "country": "Belgium"}]}
    forecast = {
        "current": {"temperature_2m": 13.6, "apparent_temperature": 11.9, "weather_code": 3,
                    "wind_speed_10m": 18.4},
        "daily": {"time": ["2026-06-04", "2026-06-05"], "weather_code": [61, 0],
                  "temperature_2m_max": [17.8, 21.1], "temperature_2m_min": [9.2, 11.0]},
    }
    view = provider.weather_view("Brussels", fetch_fn=_fake_fetch(geo, forecast))
    assert view is not None
    assert view["title"] == "Weather · Brussels, Belgium"
    d = view["data"]
    assert d["wind_unit"] == "km/h"
    assert d["current"] == {"temp": 14, "feels": 12, "wind": 18, "code": 3, "label": "Overcast"}
    assert d["daily"][0] == {"date": "2026-06-04", "hi": 18, "lo": 9, "code": 61,
                             "label": "Light rain"}
    assert d["daily"][1]["label"] == "Clear"


def test_geocode_falls_back_to_comma_parts() -> None:
    # Full "Rocourt, Liège, Belgium" doesn't resolve, but the first part "Rocourt" does.
    def fetch(url: str) -> dict:
        if "geocoding" in url:
            if "name=Rocourt&" in url:
                return {"results": [{"latitude": 50.66, "longitude": 5.54, "name": "Rocourt",
                                     "country": "Belgium"}]}
            return {"results": []}
        return {"current": {"temperature_2m": 15, "apparent_temperature": 14, "weather_code": 0,
                            "wind_speed_10m": 10},
                "daily": {"time": [], "weather_code": [], "temperature_2m_max": [],
                          "temperature_2m_min": []}}
    view = provider.weather_view("Rocourt, Liège, Belgium", fetch_fn=fetch)
    assert view is not None and view["data"]["location"] == "Rocourt, Belgium"


def test_weather_view_none_when_place_unknown() -> None:
    view = provider.weather_view("Nowhereville", fetch_fn=_fake_fetch({"results": []}, {}))
    assert view is None  # genuinely not found → None (the caller says "couldn't find it")


def test_weather_view_raises_unavailable_on_fetch_error() -> None:
    import pytest

    def boom(url: str) -> dict:
        raise RuntimeError("HTTP 429 Too Many Requests")
    # With an injected fetch_fn (tests), failure ≠ "no access" → WeatherUnavailable, no real backup.
    with pytest.raises(provider.WeatherUnavailable):
        provider.weather_view("Brussels", fetch_fn=boom)


def test_weather_view_falls_back_to_wttr(monkeypatch) -> None:
    # open-meteo down (429) → coordinator uses the wttr.in backup so weather still works.
    provider._cache.clear()
    def _down(loc, fetch):
        raise provider.WeatherUnavailable("429")
    monkeypatch.setattr(provider, "_open_meteo_view", _down)
    wttr = {
        "current_condition": [{"temp_C": "15", "FeelsLikeC": "13", "windspeedKmph": "21",
                               "weatherCode": "122"}],
        "nearest_area": [{"areaName": [{"value": "Rocourt"}], "country": [{"value": "Belgium"}]}],
        "weather": [{"date": "2026-06-04", "maxtempC": "18", "mintempC": "9",
                     "hourly": [{"weatherCode": "113"}]}],
    }
    monkeypatch.setattr(provider, "_default_fetch", lambda url: wttr)
    v = provider.weather_view("Rocourt")  # fetch_fn=None → cache+fallback path
    assert v is not None and v["data"]["location"] == "Rocourt, Belgium"
    assert v["data"]["current"]["temp"] == 15 and v["data"]["current"]["wind"] == 21
    assert v["data"]["current"]["code"] == 3  # WWO 122 (overcast) → WMO 3
    provider._cache.clear()
