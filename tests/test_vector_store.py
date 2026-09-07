import numpy as np

from app.chunking import Chunk
from app.vector_store import VectorStore


def _make_chunk(i: int) -> Chunk:
    return Chunk(file=f"file{i}.py", start_line=1, end_line=5, text=f"chunk {i}", kind="function")


def test_add_and_search_returns_closest_vector():
    store = VectorStore(dim=4)
    vectors = np.array([
        [1, 0, 0, 0],
        [0, 1, 0, 0],
        [0, 0, 1, 0],
    ], dtype="float32")
    chunks = [_make_chunk(i) for i in range(3)]
    store.add(vectors, chunks)

    query = np.array([0.9, 0.1, 0, 0], dtype="float32")
    results = store.search(query, top_k=1)

    assert len(results) == 1
    top_chunk, score = results[0]
    assert top_chunk.file == "file0.py"
    assert score > 0.8


def test_search_on_empty_index_returns_empty_list():
    store = VectorStore(dim=4)
    query = np.array([1, 0, 0, 0], dtype="float32")
    assert store.search(query, top_k=5) == []


def test_save_and_load_roundtrip(tmp_path):
    store = VectorStore(dim=4)
    vectors = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype="float32")
    chunks = [_make_chunk(0), _make_chunk(1)]
    store.add(vectors, chunks)
    store.save(tmp_path)

    loaded = VectorStore.load(tmp_path)
    assert loaded.size == 2
    assert loaded.metadata[0].file == "file0.py"
