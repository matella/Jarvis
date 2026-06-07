"""Configuration boundary — typed settings loaded from environment / .env.

Pydantic at the boundary (per CLAUDE.md): every value is validated here so the
rest of the codebase never parses raw env strings. Connection details are
exposed as computed DSNs rather than letting callers assemble URLs by hand.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import computed_field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

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
    cpu_high_pct: float = 85.0  # vs HOST-relative cpu_pct (docker's per-core % ÷ cores)
    mem_high_pct: float = 90.0
    host_cpu_cores: int = 0  # 0 = autodetect; set if the daemon container miscounts host cores
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

    # Contextual notifications — multi-channel (ntfy + generic webhook) + notifier consumer.
    notify_webhook_url: str = ""  # generic JSON POST (Discord/Slack/Gotify relays); empty → off
    # Self-hosted ntfy (local-first push to phone/desktop/watch). Reached internally by service
    # name; subscribe the ntfy app to NTFY_BASE_URL/<topic> via your reverse proxy + VPN. Both
    # url AND topic must be set for the ntfy channel to fire. Topic doubles as a shared secret.
    ntfy_url: str = ""    # e.g. http://ntfy:80 (the publish endpoint, NOT the public base url)
    ntfy_topic: str = ""  # e.g. jarvis-home-7f3a (pick something unguessable)
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
    # Hard ceiling on a single inference so a slow/stuck model (or a GPU swap storm) can't hang a
    # request forever — on timeout the call raises and the caller degrades to a reply, not silence.
    ollama_timeout_s: int = 150

    # Model roles → Ollama tags. Default reasoning model is qwen3:1.7b — the lightest tenant on the
    # shared 8 GB card (qwen3:8b at 6.6 GB crowds out other containers). Same family → the
    # JSON-schema routing stays reliable. Override per-role in .env (MODEL_REASONING=qwen3:4b or
    # qwen3:8b for more capability/headroom).
    model_reasoning: str = "qwen3:1.7b"
    model_coder: str = "qwen2.5-coder:7b"
    model_embedding: str = "nomic-embed-text"
    # Shared agent identity (system prompt). Empty → built-in Jarvis identity (agents/persona.py);
    # the live capability list is always appended. Set SYSTEM_PROMPT to customize tone/identity.
    system_prompt: str = ""
    keep_alive: str = "5m"
    inference_context: int = 8192

    # Execute-to-verify (Wave 1.2) — run model-generated Python in an EPHEMERAL, network-less,
    # read-only Docker container to catch runtime errors, then feed the traceback back for one fix.
    # OFF by default (opt-in); requires Docker on the box. Never touches infra, secrets, or network.
    code_exec_enabled: bool = False
    code_exec_image: str = "python:3.11-slim"
    code_exec_timeout_s: int = 10
    code_exec_memory: str = "256m"

    # Self-hosted homelab apps Jarvis can present/query (read-only), reached from the gateway via
    # the host's published ports. Empty → that capability is off. Hosts must be egress-allowlisted.
    hots_api_url: str = "http://host.docker.internal:5001"
    hots_overlay_url: str = "http://host.docker.internal:8086"
    orpheus_api_url: str = "http://host.docker.internal:3010"
    world_news_url: str = "http://host.docker.internal:8000"  # legacy external app (being retired)

    # News module (Jarvis-native): scrape → pool → tier-A/B. OFF until the schema is migrated.
    news_enabled: bool = False
    news_top_n: int = 10                  # daily tier-B synthesis budget
    news_sim_threshold: float = 0.70      # cluster cosine sim (same-event cross-outlet ≈0.74+)
    news_scrape_interval_s: int = 3600    # hourly RSS fetch
    news_process_interval_s: int = 60     # drain the enrichment backlog this often
    news_synthesize_interval_s: int = 120  # tier-B synthesis of multi-source stories
    gpu_telemetry_interval_s: int = 30     # sample Ollama's resident set → model load/evict events
    # Publish the finished stories into the standalone world-news DB (so the site is independent of
    # Jarvis). Empty → publishing off. e.g. postgresql://worldnews:worldnews@host.docker.internal:5433/worldnews
    world_news_db_url: str = ""
    news_publish_interval_s: int = 300    # republish the read-model this often

    # Multi-backend router — off-GPU Claude (`claude -p`, owner subscription) behind scheduler.chat.
    # Defaults to local (Ollama) so Jarvis never goes dark. Auth = CLAUDE_CODE_OAUTH_TOKEN secret.
    llm_default_backend: Literal["local", "claude"] = "local"
    claude_call_timeout: int = 120           # seconds; hard ceiling on a `claude -p` call
    claude_availability_cache_ttl: int = 60
    claude_breaker_cooldown_s: int = 900     # rate-limit → force local for this long
    claude_daily_call_budget: int = 200      # soft per-UTC-day cap; exhausted → force local
    claude_model: str = ""                   # "" = CLI default; e.g. "claude-sonnet-4-…"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ollama_url(self) -> str:
        return f"http://{self.ollama_host}:{self.ollama_port}"

    # Scheduled routines (cross-cutting A) — proactive briefings. `at` times are interpreted UTC.
    routine_tick_s: int = 60

    # Outcome verification (backlog) — did an action work? Settle, then judge within the window.
    verify_settle_s: int = 60  # give the effect time to manifest before judging
    verify_window_min: int = 30
    verify_interval_s: int = 120

    # Confidence + abstention (backlog) — below this confidence, the agent abstains rather than act.
    abstain_confidence_floor: float = 0.45

    # Cost-aware caching (backlog) — embeddings are deterministic, so cache them (avoid recompute).
    embedding_cache_enabled: bool = True
    embedding_cache_size: int = 2048

    # Governance polish (backlog) — freeze windows (autonomous actions denied) + approval nudges.
    freeze_windows: list[str] = []  # e.g. ["09:00-17:00"] (UTC); autonomous actions denied within
    nudge_pending_threshold: int = 5

    # Plugin SDK (backlog) — register external capability-scoped HTTP tools from YAML manifests.
    plugins_dir: str = ""  # local dir of *.yaml plugin manifests; empty = none

    @field_validator("freeze_windows", mode="before")
    @classmethod
    def _split_freeze_csv(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip()
            if not s or s.startswith("["):
                return [] if not s else v
            return [x.strip() for x in s.split(",") if x.strip()]
        return v

    # Knowledge-base ingest (backlog) — index runbooks/notes/wiki (prose) into memory (kind="kb").
    kb_paths: list[str] = []  # remote dirs/files (over remote_ssh)
    kb_chunk_lines: int = 40
    kb_max_file_bytes: int = 200_000

    @field_validator("kb_paths", mode="before")
    @classmethod
    def _split_kb_csv(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip()
            if not s or s.startswith("["):
                return [] if not s else v
            return [x.strip() for x in s.split(",") if x.strip()]
        return v

    # Statistical anomaly detection (backlog) — flag a metric unusual *for itself* (z-score).
    anomaly_z_threshold: float = 3.5
    anomaly_min_samples: int = 20
    anomaly_history: int = 120  # rolling-history samples per entity/metric
    anomaly_interval_s: int = 90
    anomaly_cooldown_s: int = 900  # debounce repeat alerts per entity+metric

    # Observability ingest (cross-cutting C) — Prometheus scrape + Loki log-spike detection.
    # Hosts must be egress-allowlisted. Enable workers via OBSERVABILITY_ENABLED=prometheus,loki.
    observability_enabled: list[str] = []
    prometheus_url: str = ""  # e.g. http://prometheus.lan:9090
    prometheus_queries: list[str] = []  # PromQL instant queries to sample into `metrics`
    loki_url: str = ""  # e.g. http://loki.lan:3100
    loki_queries: list[str] = []  # LogQL count queries; a spike → a log.spike event
    loki_spike_threshold: int = 50
    observability_interval_s: int = 60

    @field_validator(
        "observability_enabled", "prometheus_queries", "loki_queries", mode="before"
    )
    @classmethod
    def _split_obs_csv(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip()
            if not s or s.startswith("["):
                return [] if not s else v
            return [x.strip() for x in s.split(",") if x.strip()]
        return v

    # Security primitives (5.5c) — egress allowlist for connectors/search/capture (default-deny).
    # Accepts a JSON list or a comma-separated string in env. Bare hosts; matched incl. subdomains.
    # NoDecode: stop pydantic-settings from JSON-parsing the env value first (it would reject a
    # bare host like "searxng" before our validator runs) — the validator owns all parsing.
    egress_allowlist: Annotated[list[str], NoDecode] = []

    @field_validator("egress_allowlist", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return []
            if s.startswith("["):  # JSON list form
                return json.loads(s)
            return [h.strip().lower() for h in s.split(",") if h.strip()]
        return v

    # Connectors (8) — external integrations behind the boundary (read → events, act → gated Tools).
    # Enabled connectors run as periodic ingest workers. Secrets via SecretsProvider, never here.
    connectors_enabled: Annotated[list[str], NoDecode] = []  # e.g. feeds,mail,qbittorrent
    feed_urls: Annotated[list[str], NoDecode] = []  # RSS/Atom URLs (hosts egress-allowlisted)
    feed_poll_interval_s: int = 900
    feed_max_items: int = 20
    # Mail (IMAP read + SMTP send). Creds: MAIL_USERNAME / MAIL_PASSWORD via SecretsProvider.
    imap_host: str = ""
    imap_port: int = 993
    smtp_host: str = ""
    smtp_port: int = 587
    mail_poll_interval_s: int = 300
    mail_max_messages: int = 20
    # Multiple accounts: JSON list, each {label, imap_host, imap_port?, user_secret, pass_secret}
    # where *_secret are SecretsProvider KEY NAMES (never the secret itself). Empty → fall back to
    # the single imap_host + MAIL_USERNAME/MAIL_PASSWORD account above.
    mail_accounts: list[dict] = []
    # Triage (everyday-AI): summarize + classify inbound content (mail/feeds) and push only the
    # important ones via the notifier. Its own spine consumer; one inference per item (BACKGROUND).
    triage_enabled: bool = False
    triage_min_importance: str = "high"  # push items at/above this — high | normal | low
    # Home Assistant (REST). Token: HA_TOKEN via SecretsProvider. ha.set_state acts; the read
    # connector polls watched entities → ha.state_changed events (empty list = read nothing).
    ha_base_url: str = ""  # e.g. http://homeassistant.lan:8123
    ha_watch_entities: Annotated[list[str], NoDecode] = []  # e.g. binary_sensor.door,climate.x
    ha_poll_interval_s: int = 60
    # Calendar (read-only). Secret ICS URLs (CalDAV/Google "secret address in iCal"); upcoming
    # events within the horizon → calendar.event, deduped by UID. Hosts must be egress-allowlisted.
    calendar_ics_urls: Annotated[list[str], NoDecode] = []
    calendar_poll_interval_s: int = 1800
    calendar_horizon_h: int = 24
    # Reminders — self-contained (no external service). The worker fires due reminders → notify.
    reminder_check_interval_s: int = 30
    # qBittorrent (read-only). WebUI base reachable from the container (behind gluetun); creds
    # QBITTORRENT_USER/QBITTORRENT_PASS via SecretsProvider (its localhost-bypass can't apply here).
    qbittorrent_url: str = ""  # e.g. http://host.docker.internal:8088
    qbittorrent_poll_interval_s: int = 60
    # Jellyseerr (media-request hub) — gated actions jellyseerr.request / jellyseerr.approve.
    # Key JELLYSEERR_API_KEY via SecretsProvider. Reachable from the container.
    jellyseerr_url: str = ""  # e.g. http://requests.matelab
    # Inbound webhooks — per-source HMAC secret names resolved via SecretsProvider
    # (e.g. WEBHOOK_SECRET_GITHUB). Empty signature config → that source is rejected.
    webhook_require_signature: bool = True

    # Code module (OpenCode) — repos a coding session may target. Opt-in allowlist (empty = none);
    # the Jarvis repo is refused by default (no self-modification). Absolute paths on the box.
    code_repo_allowlist: Annotated[list[str], NoDecode] = []

    @field_validator(
        "connectors_enabled", "feed_urls", "ha_watch_entities", "calendar_ics_urls",
        "gateway_cors_origins", "code_repo_allowlist", mode="before"
    )
    @classmethod
    def _split_list_csv(cls, v: object) -> object:
        # These fields are NoDecode (pydantic-settings won't JSON-pre-parse them), so the validator
        # owns ALL parsing: empty→[], JSON list→parsed, otherwise comma-separated.
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return []
            if s.startswith("["):
                return json.loads(s)
            return [x.strip() for x in s.split(",") if x.strip()]
        return v

    # GPU scheduler (11) — priority queue in front of the one-resident model.
    sched_max_swaps_per_min: int = 8  # don't thrash the 8 GB card swapping models
    sched_session_token_budget: int = 0  # per-chat-session cap (0 = unlimited)
    sched_plan_token_budget: int = 0  # per-plan cap (0 = unlimited)

    # Voice (10) — local/CPU. STT is faster-whisper IN-PROCESS (no external service, audio stays
    # on the box). whisper_model is a faster-whisper model name (e.g. base.en / base / small);
    # empty → STT off. TTS in the browser by default; set piper_voice for server-side Piper.
    voice_enabled: bool = False
    whisper_model: str = "base.en"  # faster-whisper model; "" disables local STT
    whisper_device: str = "cpu"     # cpu | cuda
    whisper_compute: str = "int8"   # int8 (fast/CPU) | float16 (GPU) | float32
    piper_bin: str = "piper"
    piper_voice: str = ""  # path to a Piper .onnx voice; empty → server TTS off (browser speaks)
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
    # Session login (personal-OS shell). The passphrase hash is a SECRET read via SecretsProvider
    # (`APP_PASSPHRASE_HASH`, format `scrypt$<salt>$<hash>`, mint with `make app-passphrase`)
    # — never a config field, never in DB/git/logs. Unset → login off (bearer-token fallback).
    app_session_ttl_days: int = 30
    app_session_cookie: str = "jarvis_session"
    # CORS — allow the native (Capacitor) app + dev origins to call the REST API cross-origin.
    # The bundled app's origin is capacitor://localhost (Android) / ionic://localhost; localhost
    # covers `cap run` + dev. Add your console's https domain if you serve it from another origin.
    gateway_cors_origins: Annotated[list[str], NoDecode] = [
        "capacitor://localhost", "ionic://localhost", "http://localhost",
        "http://localhost:5173", "https://localhost",
    ]

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
