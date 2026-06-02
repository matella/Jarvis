"""Config boundary tests — no live services required."""

from jarvis.config import Settings


def _settings(**overrides) -> Settings:
    # _env_file=None so the developer's real .env never leaks into the test.
    defaults = dict(
        postgres_user="u",
        postgres_password="p",
        postgres_db="d",
        postgres_host="db.host",
        postgres_port=6000,
        redis_host="r.host",
        redis_port=6100,
        redis_db=2,
    )
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def test_postgres_dsn_is_assembled_from_parts() -> None:
    assert _settings().postgres_dsn == "postgresql://u:p@db.host:6000/d"


def test_redis_url_includes_db_index() -> None:
    assert _settings().redis_url == "redis://r.host:6100/2"


def test_mode_defaults_to_observe() -> None:
    assert _settings().jarvis_mode == "observe"


def test_egress_allowlist_parses_from_env(monkeypatch) -> None:
    # Must parse from the ENV source (where pydantic-settings would otherwise JSON-pre-parse and
    # reject a bare host) — exactly how the gateway/daemon containers receive EGRESS_ALLOWLIST.
    monkeypatch.setenv("EGRESS_ALLOWLIST", "searxng")
    assert Settings(_env_file=None).egress_allowlist == ["searxng"]

    monkeypatch.setenv("EGRESS_ALLOWLIST", "Searx.lan, API.example.com")
    assert Settings(_env_file=None).egress_allowlist == ["searx.lan", "api.example.com"]

    monkeypatch.setenv("EGRESS_ALLOWLIST", '["a.lan", "b.lan"]')  # JSON list form still works
    assert Settings(_env_file=None).egress_allowlist == ["a.lan", "b.lan"]

    monkeypatch.setenv("EGRESS_ALLOWLIST", "")  # empty = default-deny
    assert Settings(_env_file=None).egress_allowlist == []


def test_router_backend_defaults(monkeypatch) -> None:
    s = Settings(_env_file=None)
    assert s.llm_default_backend == "local"  # safety net: never claude by default
    assert s.claude_breaker_cooldown_s == 900 and s.claude_daily_call_budget > 0
    monkeypatch.setenv("LLM_DEFAULT_BACKEND", "claude")
    assert Settings(_env_file=None).llm_default_backend == "claude"


def test_list_fields_parse_bare_and_csv_from_env(monkeypatch) -> None:
    # Every list field that takes operator input from env must accept a bare value / CSV without
    # the pydantic-settings JSON-pre-parse crash (regression: CONNECTORS_ENABLED=qbittorrent).
    monkeypatch.setenv("CONNECTORS_ENABLED", "qbittorrent")
    assert Settings(_env_file=None).connectors_enabled == ["qbittorrent"]
    monkeypatch.setenv("CONNECTORS_ENABLED", "feeds, mail, qbittorrent")
    assert Settings(_env_file=None).connectors_enabled == ["feeds", "mail", "qbittorrent"]
    monkeypatch.setenv("HA_WATCH_ENTITIES", "light.office,climate.living")
    assert Settings(_env_file=None).ha_watch_entities == ["light.office", "climate.living"]
