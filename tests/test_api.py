"""
End-to-end tests against the FastAPI app.

The real embedding model (sentence-transformers) is intentionally swapped for
a tiny deterministic fake here -- these tests are checking API wiring and
control flow (ingest -> store -> retrieve -> answer), not embedding quality,
and a fake keeps the suite fast and runnable with no model download / no
network access, which matters a lot in CI.
"""
import numpy as np
import pytest
from fastapi.testclient import TestClient

FAKE_DIM = 8


def _fake_embed_texts(texts: list[str]) -> np.ndarray:
    """Deterministic, dependency-free stand-in for the real embedding model:
    hashes each text into a fixed-size vector so identical/similar texts land
    near each other, which is enough to exercise retrieval logic in tests."""
    vectors = np.zeros((len(texts), FAKE_DIM), dtype="float32")
    for i, text in enumerate(texts):
        for j, ch in enumerate(text[:64]):
            vectors[i, j % FAKE_DIM] += ord(ch)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return vectors / norms


def _fake_embedding_dim() -> int:
    return FAKE_DIM


@pytest.fixture
def sample_repo(tmp_path):
    repo = tmp_path / "sample_repo"
    repo.mkdir()
    (repo / "auth.py").write_text(
        "def authenticate(user, password):\n"
        "    \"\"\"Check credentials against the users table.\"\"\"\n"
        "    return verify_password(user, password)\n"
    )
    (repo / "README.md").write_text("# Sample Repo\n\nThis service handles authentication.\n")
    return repo


@pytest.fixture
def client(tmp_path, monkeypatch, sample_repo):
    monkeypatch.setattr("app.ingest.embed_texts", _fake_embed_texts)
    monkeypatch.setattr("app.ingest.embedding_dim", _fake_embedding_dim)
    monkeypatch.setattr("app.main.embed_texts", _fake_embed_texts)

    from app import main
    monkeypatch.setattr(main, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(main, "_store", None)

    with TestClient(main.app) as c:
        yield c, sample_repo


def test_health_before_ingest(client):
    c, _ = client
    res = c.get("/health")
    assert res.status_code == 200
    assert res.json()["index_size"] == 0


def test_ingest_then_query_returns_grounded_citation(client):
    c, repo = client

    ingest_res = c.post("/ingest", json={"repo_path": str(repo)})
    assert ingest_res.status_code == 200
    body = ingest_res.json()
    assert body["files_ingested"] == 2
    assert body["chunks_created"] >= 2

    query_res = c.post("/query", json={"question": "How does authentication work?"})
    assert query_res.status_code == 200
    data = query_res.json()

    assert data["citations"], "expected at least one citation"
    assert any("auth.py" in c["file"] for c in data["citations"])
    assert data["latency_ms"] >= 0


def test_query_without_ingest_returns_400(client):
    c, _ = client
    res = c.post("/query", json={"question": "anything"})
    assert res.status_code == 400


def test_ingest_nonexistent_path_returns_404(client):
    c, _ = client
    res = c.post("/ingest", json={"repo_path": "/definitely/does/not/exist"})
    assert res.status_code == 404
