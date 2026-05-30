# Jarvis gateway image — runs `jarvis serve` (FastAPI + /ws). Reaches postgres/redis by compose
# service name and Ollama via the host. Migrations run on startup (idempotent) before serving.
FROM python:3.11-slim

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
