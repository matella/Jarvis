# Drive the REMOTE homelab daemon over an SSH docker context. Never the local daemon.
# Fill REMOTE_SSH / ports in .env first (copy from .env.example).

-include .env
export

CONTEXT  ?= jarvis
REMOTE_SSH ?= user@homelab.lan
POSTGRES_PORT ?= 5432
REDIS_PORT ?= 6379
OLLAMA_PORT ?= 11434

DC = docker --context $(CONTEXT) compose

.PHONY: context up down ps logs tunnel health test deploy deploy-logs deploy-down claude-token app-passphrase google-oauth

## Create/point the SSH docker context at the remote host.
context:
	@docker context create $(CONTEXT) --docker "host=ssh://$(REMOTE_SSH)" 2>/dev/null \
		|| docker context update $(CONTEXT) --docker "host=ssh://$(REMOTE_SSH)"
	@echo "context '$(CONTEXT)' -> ssh://$(REMOTE_SSH)"

## Bring the infra spine up / down on the remote.
up:
	$(DC) up -d
down:
	$(DC) down
ps:
	$(DC) ps
logs:
	$(DC) logs -f

## Forward remote-loopback Postgres/Redis/Ollama to this machine's 127.0.0.1 (blocks).
tunnel:
	ssh -N \
		-L $(POSTGRES_PORT):localhost:$(POSTGRES_PORT) \
		-L $(REDIS_PORT):localhost:$(REDIS_PORT) \
		-L $(OLLAMA_PORT):localhost:$(OLLAMA_PORT) \
		$(REMOTE_SSH)

## M0 acceptance: both services answer through the tunnel.
health:
	python scripts/healthcheck.py

test:
	pytest -q

## Behavioral routing eval — run the 100 example use-cases through fastpath_route and report the
## pass-rate. GPU-free regression gate; run on every routing/model change.
eval:
	python -m jarvis.eval.behavior

## Build + (re)deploy the app containers (gateway + daemon + console + searxng) on THIS host's
## Docker. Run on the box after `git clone` — plain `docker compose`, NOT the SSH context above.
## `search` profile brings up SearXNG so web search (weather, lookups) works out of the box.
deploy:
	docker compose --profile app --profile search up -d --build
deploy-logs:
	docker compose --profile app logs -f gateway daemon console
deploy-down:
	docker compose --profile app --profile search down

## Mint a long-lived Claude subscription token, then paste it into the box .env as
## CLAUDE_CODE_OAUTH_TOKEN (the off-GPU `claude` backend reads it via env_file). One-time; re-run
## when it expires. Uses your Claude Pro/Max subscription — NOT a metered API key.
claude-token:
	docker run --rm -it node:22 sh -c 'npm install -g @anthropic-ai/claude-code >/dev/null 2>&1 && claude setup-token'

## Mint an APP_PASSPHRASE_HASH for the session-login shell. Prompts for a passphrase (hidden) and
## prints `scrypt$<salt>$<hash>` — paste it into the box .env as APP_PASSPHRASE_HASH. The raw
## passphrase is never stored; only this hash. Re-run to rotate.
app-passphrase:
	@./.venv/bin/python -c 'import getpass; from jarvis.gateway.sessions import hash_passphrase; print(hash_passphrase(getpass.getpass("New app passphrase: ")))'

## Mint a Google Calendar refresh token (read-only) for the calendar read-mirror. Run on a machine
## WITH A BROWSER (your Mac). Export the OAuth client first, then approve once; paste the printed
## GOOGLE_OAUTH_REFRESH_TOKEN into the box .env (with the client id/secret).
google-oauth:
	@./.venv/bin/python scripts/google_oauth.py
