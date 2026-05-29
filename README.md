# Jarvis

AI-native operational intelligence for a homelab — event-driven cognition over
infrastructure state. See [CLAUDE.md](CLAUDE.md) for the architecture and rules.

## Quickstart (M0 — infra spine)

Containers run on the **remote** homelab box via an SSH docker context; the Mac only
drives them and reaches Postgres/Redis through an SSH tunnel.

```bash
cp .env.example .env          # set REMOTE_SSH=user@host, adjust creds/ports
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

make context                  # create the 'jarvis' SSH docker context -> remote
make up                       # start pgvector + redis on the remote
make tunnel                   # (separate shell) forward 5432/6379 to 127.0.0.1; blocks
make health                   # acceptance: connects to both, exits 0
```

`make down` stops the stack; `make ps` / `make logs` inspect it; `make test` runs pytest.
