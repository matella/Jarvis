"""Code-index unit tests — secret safety, chunking, agent assembly. No DB/ssh/model."""

from jarvis.ingest.code_index import _chunk, _is_indexable, _is_secret_path, _redact


def test_secret_paths_excluded() -> None:
    for p in ["/h/.env", "/h/stack/.env.prod", "/h/tls.key", "/h/cert.pem",
              "/h/secrets.yml", "/h/id_rsa", "/h/db_credentials.txt"]:
        assert _is_secret_path(p), p
    for p in ["/h/docker-compose.yml", "/h/Dockerfile", "/h/run.sh"]:
        assert not _is_secret_path(p), p


def test_indexable_types() -> None:
    for p in ["/h/docker-compose.yml", "/h/compose.yaml", "/h/Dockerfile", "/h/run.sh",
              "/h/app.conf", "/h/pyproject.toml"]:
        assert _is_indexable(p), p
    # generic yaml / markdown / binaries are NOT indexed (compose-focused)
    for p in ["/h/values.yaml", "/h/config.yml", "/h/README.md", "/h/image.png", "/h/.env"]:
        assert not _is_indexable(p), p


def test_redact_strips_secret_values_keeps_keys() -> None:
    text = "\n".join([
        "image: nginx:latest",
        "  PASSWORD=hunter2",
        "  WIREGUARD_PRIVATE_KEY=abc123def",
        "      api_key: sk-secret-xyz",
        "  - POSTGRES_PASSWORD=topsecret",
        "ports:",
        "  - 8080:8080",
    ])
    out = _redact(text)
    assert "hunter2" not in out
    assert "abc123def" not in out
    assert "sk-secret-xyz" not in out
    assert "topsecret" not in out
    assert out.count("<redacted>") == 4
    # non-secret lines untouched
    assert "image: nginx:latest" in out
    assert "8080:8080" in out


def test_chunk_line_windows() -> None:
    text = "\n".join(f"line{i}" for i in range(1, 131))  # 130 lines
    chunks = _chunk(text, 60)
    assert [(s, e) for s, e, _ in chunks] == [(1, 60), (61, 120), (121, 130)]
    assert chunks[0][2].startswith("line1")


def test_chunk_skips_empty() -> None:
    assert _chunk("   \n\n  ", 60) == []


def test_coder_ask_assembles_sources(monkeypatch) -> None:
    import jarvis.agents.coder as coder

    monkeypatch.setattr(coder.router, "embed", lambda q, **k: [0.0] * 8)
    monkeypatch.setattr(
        coder, "search_chunks",
        lambda conn, vec, k=6, repo=None: [
            ("compose/qbittorrent.yml", 1, 10, "network_mode: service:gluetun", 0.1),
        ],
    )
    monkeypatch.setattr(
        coder.router, "chat",
        lambda role, messages, **k: {"message": {"content": "qbittorrent routes via gluetun."}},
    )

    import contextlib

    @contextlib.contextmanager
    def fake_connect(*a, **k):
        yield object()

    monkeypatch.setattr(coder.db, "connect", fake_connect)

    answer = coder.ask("how is qbittorrent networked?")
    assert "gluetun" in answer.answer
    assert answer.sources == ["compose/qbittorrent.yml:1-10"]


def test_coder_ask_handles_empty_index(monkeypatch) -> None:
    import contextlib

    import jarvis.agents.coder as coder

    monkeypatch.setattr(coder.router, "embed", lambda q, **k: [0.0] * 8)
    monkeypatch.setattr(coder, "search_chunks", lambda conn, vec, k=6, repo=None: [])

    @contextlib.contextmanager
    def fake_connect(*a, **k):
        yield object()

    monkeypatch.setattr(coder.db, "connect", fake_connect)
    answer = coder.ask("anything?")
    assert answer.sources == [] and "index" in answer.answer.lower()
