from __future__ import annotations

import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from app.chunking import chunk_file, walk_repo
from app.config import settings
from app.embeddings import embed_texts, embedding_dim
from app.vector_store import VectorStore


def clone_git_repo(git_url: str) -> Path:
    tmp_dir = Path(tempfile.mkdtemp(prefix="repomind_git_"))
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", git_url, str(tmp_dir)],
            check=True, capture_output=True, text=True, timeout=settings.git_clone_timeout_seconds,
        )
    except FileNotFoundError:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise ValueError("git is not installed or not on PATH on this server.")
    except subprocess.TimeoutExpired:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise ValueError("git clone timed out -- check the URL and that the repo is reachable.")
    except subprocess.CalledProcessError as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        stderr = (e.stderr or "").strip()[:300]
        raise ValueError(f"git clone failed: {stderr or 'unknown error'}")
    return tmp_dir


def extract_zip_upload(file_bytes: bytes) -> tuple[Path, Path]:
    tmp_dir = Path(tempfile.mkdtemp(prefix="repomind_upload_"))
    zip_path = tmp_dir / "upload.zip"
    zip_path.write_bytes(file_bytes)

    extract_dir = tmp_dir / "extracted"
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)
    except zipfile.BadZipFile:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise ValueError("That file isn't a valid .zip archive.")

    entries = list(extract_dir.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0], tmp_dir
    return extract_dir, tmp_dir


def ingest_repository(repo_path: str, include_extensions: list[str] | None = None) -> tuple[VectorStore, dict]:
    root = Path(repo_path).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Path does not exist: {root}")

    ext_set = set(include_extensions) if include_extensions else None
    files = walk_repo(root, ext_set)

    all_chunks = []
    skipped: list[str] = []
    for f in files:
        chunks = chunk_file(f)
        if chunks:
            rel = str(f.relative_to(root))
            for c in chunks:
                c.file = rel
            all_chunks.extend(chunks)
        else:
            skipped.append(str(f.relative_to(root)))

    store = VectorStore(dim=embedding_dim())
    if all_chunks:
        vectors = embed_texts([c.text for c in all_chunks])
        store.add(vectors, all_chunks)

    stats = {
        "files_scanned": len(files),
        "files_ingested": len(files) - len(skipped),
        "chunks_created": len(all_chunks),
        "skipped_files": skipped,
    }
    return store, stats
