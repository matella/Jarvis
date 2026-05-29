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

    # Embeddings — dimension is a property of the model; changing it requires a
    # migration + re-embed (a vector column can't silently change width).
    embedding_model: str = "nomic-embed-text"
    embedding_dim: int = 768

    # Docker ingestion — the SSH docker context that targets the remote daemon.
    docker_context: str = "jarvis"

    # SSH target for the remote host (used for nvidia-smi GPU sampling). From .env REMOTE_SSH.
    remote_ssh: str = ""

    # Metrics ingest — poll cadence, retention, and signal thresholds (percent).
    metrics_poll_interval_s: int = 30
    metrics_retention_hours: int = 24
    cpu_high_pct: float = 85.0
    mem_high_pct: float = 90.0
    gpu_util_high_pct: float = 90.0
    gpu_mem_high_pct: float = 90.0

    # Alert correlation — temporal-burst clustering of warning+ alerts.
    incident_cluster_gap_s: int = 300
    incident_min_alerts: int = 2

    # Code intelligence — index a repo on the remote host (read over SSH).
    code_repo_path: str = "/home/matella/homelab"
    code_repo_name: str = "homelab"
    code_chunk_lines: int = 60
    code_max_file_bytes: int = 200_000

    # `jarvis run` daemon — periodic collector cadences (ingest/consume/metrics self-loop).
    topology_interval_s: int = 300
    deploy_interval_s: int = 120

    # Contextual notifications — webhook channel + notifier consumer.
    notify_webhook_url: str = ""  # empty → log-only
    notify_group: str = "jarvis:notifier"
    notify_cooldown_s: int = 300

    # Ambient reactor — auto-propose (gated) on container-down events.
    reactor_enabled: bool = True
    reactor_group: str = "jarvis:reactor"
    reactor_cooldown_s: int = 600

    # Redis Streams — event spine topology.
    events_stream: str = "jarvis:events"
    consumer_group: str = "jarvis:projectors"
    dlq_stream: str = "jarvis:dlq"
    stream_maxlen: int = 100_000
    max_deliveries: int = 5

    # Ollama — reached at 127.0.0.1 via the SSH tunnel (off-LAN, like PG/Redis).
    ollama_host: str = "127.0.0.1"
    ollama_port: int = 11434

    # Model roles → Ollama tags. "Qwen 3.5 9B" (CLAUDE.md) has no literal tag; qwen3:8b is
    # the 8 GB-fit stand-in. Override per-role in .env (e.g. MODEL_REASONING=llama3.2:latest).
    model_reasoning: str = "qwen3:8b"
    model_coder: str = "qwen2.5-coder:7b"
    model_embedding: str = "nomic-embed-text"
    keep_alive: str = "5m"
    inference_context: int = 8192

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ollama_url(self) -> str:
        return f"http://{self.ollama_host}:{self.ollama_port}"

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
