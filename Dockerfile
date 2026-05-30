# Jarvis app image — serves `jarvis serve` (gateway) AND runs `jarvis run` (the spine daemon).
# Reaches postgres/redis by compose service name and Ollama via the host. The Docker CLI is included
# so the daemon's ingest/metrics/topology workers can drive the host's Docker via a mounted socket
# (the gateway never uses it). Migrations run on startup (idempotent).
FROM python:3.11-slim

# Docker CLI (static binary) — used only by the daemon (DOCKER_CONTEXT=default + mounted socket).
ARG DOCKER_CLI_VERSION=27.3.1
RUN set -eux; \
    apt-get update && apt-get install -y --no-install-recommends curl ca-certificates; \
    curl -fsSL "https://download.docker.com/linux/static/stable/x86_64/docker-${DOCKER_CLI_VERSION}.tgz" \
      | tar -xz --strip-components=1 -C /usr/local/bin docker/docker; \
    apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*; \
    docker --version

WORKDIR /app

# Install the package + its deps from a minimal context (pyproject + the package + migrations).
COPY pyproject.toml alembic.ini ./
COPY jarvis ./jarvis
COPY migrations ./migrations
RUN pip install --no-cache-dir .

# Bind all interfaces inside the container so the console service can reach it on the compose net.
ENV GATEWAY_HOST=0.0.0.0 \
    GATEWAY_PORT=8787 \
    PYTHONUNBUFFERED=1

EXPOSE 8787

# Apply schema migrations, then serve. (alembic + the app read the DSN from env via jarvis.config.)
CMD ["sh", "-c", "alembic upgrade head && jarvis serve"]
