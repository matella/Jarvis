"""Configuration boundary — typed settings loaded from environment / .env.

Pydantic at the boundary (per CLAUDE.md): every value is validated here so the
rest of the codebase never parses raw env strings. Connection details are
exposed as computed DSNs rather than letting callers assemble URLs by hand.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Global operational modes. M0 only needs `observe` (propose-only); the rest are
# seeded here to match Hard Rule 6 / DECISIONS and grown in a later phase.
Mode = Literal["observe", "assist", "approval_required", "semi_autonomous", "maintenance_mode"]


class Settings(BaseSettings):
    """Runtime configuration. Field names map case-insensitively to env vars."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Postgres (as reached FROM this machine — 127.0.0.1 via the SSH tunnel).
    postgres_user: str = "jarvis"
    postgres_password: str = "jarvis"
    postgres_db: str = "jarvis"
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432

    # Redis.
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0

    # Global operational mode — defaults to propose-only.
    jarvis_mode: Mode = "observe"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings singleton."""
    return Settings()
