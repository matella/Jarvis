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

.PHONY: context up down ps logs tunnel health test

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
