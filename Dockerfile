# Jarvis app image — serves `jarvis serve` (gateway) AND runs `jarvis run` (the spine daemon).
# Reaches postgres/redis by compose service name and Ollama via the host. The Docker CLI is included
# so the daemon's ingest/metrics/topology workers can drive the host's Docker via a mounted socket
# (the gateway never uses it). Migrations run on startup (idempotent).
FROM python:3.11-slim

# Docker CLI (static binary) — used only by the daemon (DOCKER_CONTEXT=default + mounted socket).
# openssh-client: the daemon's GPU telemetry runs `ssh $REMOTE_SSH nvidia-smi` (host has the GPU).
ARG DOCKER_CLI_VERSION=27.3.1
RUN set -eux; \
    apt-get update && apt-get install -y --no-install-recommends curl ca-certificates openssh-client; \
    curl -fsSL "https://download.docker.com/linux/static/stable/x86_64/docker-${DOCKER_CLI_VERSION}.tgz" \
      | tar -xz --strip-components=1 -C /usr/local/bin docker/docker; \
    apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*; \
    docker --version

# Node + Claude Code CLI — the off-GPU `claude` backend (`claude -p`). Auth at runtime via the
# CLAUDE_CODE_OAUTH_TOKEN env var (from `make claude-token`); used by the gateway (chat compose) and
# the daemon (postmortems). Pinned for reproducibility; the router defaults to local so this is opt-in.
ARG CLAUDE_CODE_VERSION=2.1.160
RUN set -eux; \
    apt-get update && apt-get install -y --no-install-recommends curl ca-certificates gnupg; \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash -; \
    apt-get install -y --no-install-recommends nodejs; \
    npm install -g "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}"; \
    claude --version; \
    apt-get purge -y curl gnupg && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install the package + its deps (incl. the local-STT 'voice' extra: faster-whisper, on-device).
COPY pyproject.toml alembic.ini ./
COPY jarvis ./jarvis
COPY migrations ./migrations
RUN pip install --no-cache-dir ".[voice]"

# Pre-cache the Whisper model into the image so STT runs offline and audio never leaves the box.
# `base` (multilingual), not `base.en` — the operator speaks French to Jarvis.
ARG WHISPER_MODEL=base
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('${WHISPER_MODEL}', device='cpu', compute_type='int8')"

# Bake the Piper voice (French — Jarvis mirrors the operator's language; the ElevenLabs opt-in
# covers true multilingual). Downloaded at build so local TTS runs fully offline.
ARG PIPER_VOICE_NAME=fr_FR-siwis-medium
ARG PIPER_VOICE_PATH=fr/fr_FR/siwis/medium
RUN set -eux; mkdir -p /voices; \
    python -c "import urllib.request as u; \
base='https://huggingface.co/rhasspy/piper-voices/resolve/main/${PIPER_VOICE_PATH}'; \
u.urlretrieve(base+'/${PIPER_VOICE_NAME}.onnx', '/voices/${PIPER_VOICE_NAME}.onnx'); \
u.urlretrieve(base+'/${PIPER_VOICE_NAME}.onnx.json', '/voices/${PIPER_VOICE_NAME}.onnx.json')"; \
    ls -la /voices
ENV PIPER_VOICE=/voices/${PIPER_VOICE_NAME}.onnx

# Bind all interfaces inside the container so the console service can reach it on the compose net.
ENV GATEWAY_HOST=0.0.0.0 \
    GATEWAY_PORT=8787 \
    PYTHONUNBUFFERED=1

EXPOSE 8787

# Apply schema migrations, then serve. (alembic + the app read the DSN from env via jarvis.config.)
CMD ["sh", "-c", "alembic upgrade head && jarvis serve"]
