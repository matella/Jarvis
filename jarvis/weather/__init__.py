"""Weather presenter — fetch open-meteo (free, no API key) → a typed `weather` artifact the app
renders as a visual card. Deterministic (data → artifact), so no LLM and no agent loop. The first
example of the presenter pattern: a data source + a `provider.weather_view` that returns structured
artifact data, rendered by the frontend's ArtifactRenderer `case "weather"`.
"""

from jarvis.weather.provider import looks_like_weather, weather_view  # noqa: F401
