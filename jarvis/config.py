"""Configuration boundary — typed settings loaded from environment / .env.

Pydantic at the boundary (per CLAUDE.md): every value is validated here so the
rest of the codebase never parses raw env strings. Connection details are
exposed as computed DSNs rather than letting callers assemble URLs by hand.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Default/initial operational mode (the LIVE mode is persisted in DB; see core/modes.py).
# The state machine: observe → approval_required → semi_autonomous, plus maintenance (freeze).
Mode = Literal["observe", "approval_required", "semi_autonomous", "maintenance"]


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

    # Durability — backups (pg_dump via the postgres container), off-box copy, snapshots.
    postgres_container: str = "jarvis-postgres"
    backup_offbox_dir: str = "backups"            # on this machine (off the DB host)
    backup_remote_dir: str = "/home/matella/jarvis-backups"  # a copy on the remote box
    backup_retention_count: int = 14
    backup_interval_s: int = 86_400
    snapshot_heartbeat_min: int = 60              # write a state snapshot at most this often…
    snapshot_change_threshold: int = 1            # …and only if ≥ this many new events since last

    # Self-observability — worker heartbeats (Redis TTL keys) + periodic health.
    heartbeat_ttl_s: int = 90
    selfcheck_interval_s: int = 60

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

    # Predictive observability — project metric trends toward thresholds.
    predict_interval_s: int = 60
    predict_window_min: int = 30
    predict_horizon_min: int = 30
    predict_min_samples: int = 5

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

    # Security primitives (5.5c) — egress allowlist for connectors/search/capture (default-deny).
    # Accepts a JSON list or a comma-separated string in env. Bare hosts; matched incl. subdomains.
    egress_allowlist: list[str] = []

    @field_validator("egress_allowlist", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip()
            if not s or s.startswith("["):  # empty or JSON — let pydantic handle it
                return [] if not s else v
            return [h.strip().lower() for h in s.split(",") if h.strip()]
        return v

    # Connectors (8) — external integrations behind the boundary (read → events, act → gated Tools).
    # Enabled connectors run as periodic ingest workers. Secrets via SecretsProvider, never here.
    connectors_enabled: list[str] = []  # e.g. ["feeds", "mail"]
    feed_urls: list[str] = []  # RSS/Atom URLs (hosts must be egress-allowlisted)
    feed_poll_interval_s: int = 900
    feed_max_items: int = 20
    # Mail (IMAP read + SMTP send). Creds: MAIL_USERNAME / MAIL_PASSWORD via SecretsProvider.
    imap_host: str = ""
    imap_port: int = 993
    smtp_host: str = ""
    smtp_port: int = 587
    mail_poll_interval_s: int = 300
    mail_max_messages: int = 20
    # Home Assistant (REST). Token: HA_TOKEN via SecretsProvider.
    ha_base_url: str = ""  # e.g. http://homeassistant.lan:8123
    # Inbound webhooks — per-source HMAC secret names resolved via SecretsProvider
    # (e.g. WEBHOOK_SECRET_GITHUB). Empty signature config → that source is rejected.
    webhook_require_signature: bool = True

    @field_validator("connectors_enabled", "feed_urls", mode="before")
    @classmethod
    def _split_list_csv(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip()
            if not s or s.startswith("["):
                return [] if not s else v
            return [x.strip() for x in s.split(",") if x.strip()]
        return v

    # Voice (10) — local/CPU transport over the conversation pipeline. Binaries are external.
    voice_enabled: bool = False
    whisper_bin: str = "whisper-cli"  # whisper.cpp CLI
    whisper_model: str = ""  # path to a ggml model; empty → STT unavailable
    piper_bin: str = "piper"
    piper_voice: str = ""  # path to a Piper .onnx voice; empty → TTS unavailable
    wake_word_enabled: bool = False
    wake_silence_ms: int = 1500  # stop buffering after this much trailing silence

    # Real-time search + capture (9) — local-first web RAG via SearXNG; screenshots via Playwright.
    searxng_url: str = ""  # e.g. http://searxng.lan:8080 (host must be egress-allowlisted)
    search_result_limit: int = 5
    capture_timeout_s: int = 20

    # Orchestration + action safety (7) — bounds on a single plan and on action throughput.
    plan_max_steps: int = 12
    plan_max_entities: int = 5  # blast radius: distinct entities an action plan may touch
    action_rate_limit: int = 20  # max real executions per window (rate cap)
    action_rate_window_s: int = 300

    # Conversational gateway (6a) — FastAPI + WebSocket. Local homelab only, no external exposure.
    gateway_host: str = "127.0.0.1"
    gateway_port: int = 8787
    # Bearer token for the chat/read API. Empty = open dev mode (single "local" actor, all scopes);
    # set a token to require it. Real per-user identities flow into the audit log as actor.
    gateway_token: str = ""
    gateway_actor: str = "local"

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
