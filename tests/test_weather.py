"""Weather presenter — detection, location extraction, view building (mocked fetch). No network."""

from __future__ import annotations

from jarvis.weather import provider


def test_detection() -> None:
    assert provider.looks_like_weather("what's the weather in Paris?")
    assert provider.looks_like_weather("5-day forecast")
    assert provider.looks_like_weather("how hot is it today")
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
        "current": {"temperature_2m": 13.6, "apparent_temperature": 11.9, "weather_code": 3},
        "daily": {"time": ["2026-06-04", "2026-06-05"], "weather_code": [61, 0],
                  "temperature_2m_max": [17.8, 21.1], "temperature_2m_min": [9.2, 11.0]},
    }
    view = provider.weather_view("Brussels", fetch_fn=_fake_fetch(geo, forecast))
    assert view is not None
    assert view["title"] == "Weather · Brussels, Belgium"
    d = view["data"]
    assert d["current"] == {"temp": 14, "feels": 12, "code": 3, "label": "Overcast"}
    assert d["daily"][0] == {"date": "2026-06-04", "hi": 18, "lo": 9, "code": 61,
                             "label": "Light rain"}
    assert d["daily"][1]["label"] == "Clear"


def test_weather_view_none_when_place_unknown() -> None:
    view = provider.weather_view("Nowhereville", fetch_fn=_fake_fetch({"results": []}, {}))
    assert view is None


def test_weather_view_none_on_fetch_error() -> None:
    def boom(url: str) -> dict:
        raise RuntimeError("egress blocked")
    assert provider.weather_view("Brussels", fetch_fn=boom) is None
