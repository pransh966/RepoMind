from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import faiss
import numpy as np

from app.chunking import Chunk


class VectorStore:
    def __init__(self, dim: int):
        self.dim = dim
        self.index = faiss.IndexFlatIP(dim)
        self.metadata: list[Chunk] = []

    def add(self, vectors: np.ndarray, chunks: list[Chunk]) -> None:
        if len(vectors) != len(chunks):
            raise ValueError("vectors and chunks must be the same length")
        if len(vectors) == 0:
            return
        self.index.add(vectors)
        self.metadata.extend(chunks)

    def search(self, query_vector: np.ndarray, top_k: int) -> list[tuple[Chunk, float]]:
        if self.index.ntotal == 0:
            return []
        top_k = min(top_k, self.index.ntotal)
        scores, indices = self.index.search(query_vector.reshape(1, -1), top_k)
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            results.append((self.metadata[idx], float(score)))
        return results

    def save(self, data_dir: Path) -> None:
        data_dir.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(data_dir / "index.faiss"))
        with open(data_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump([asdict(c) for c in self.metadata], f)

    @classmethod
    def load(cls, data_dir: Path) -> "VectorStore":
        index_path = data_dir / "index.faiss"
        meta_path = data_dir / "metadata.json"
        if not index_path.exists() or not meta_path.exists():
            raise FileNotFoundError(f"No saved index found in {data_dir}. Run /ingest first.")

        index = faiss.read_index(str(index_path))
        with open(meta_path, encoding="utf-8") as f:
            raw = json.load(f)

        store = cls(dim=index.d)
        store.index = index
        store.metadata = [Chunk(**item) for item in raw]
        return store

    @property
    def size(self) -> int:
        return self.index.ntotal
