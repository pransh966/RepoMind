"""
Chunking strategy is the single biggest lever on RAG answer quality, and it's
the piece almost every "chat with your docs" tutorial gets lazy about (fixed
N-character windows that cut a function in half, mid-sentence).

This module chunks Python source at AST boundaries -- one chunk per top-level
function or class -- so retrieval returns whole, coherent units of code
instead of arbitrary fragments. Non-Python text files fall back to a
line-based sliding window with overlap, which is still far better than a
character-count window because it respects line structure (useful for diffs,
citations, and not splitting a code fence in half).
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

CODE_EXTENSIONS = {".py"}
TEXT_EXTENSIONS = {".md", ".txt", ".rst", ".yaml", ".yml", ".toml", ".json", ".js", ".ts", ".jsx", ".tsx"}
SUPPORTED_EXTENSIONS = CODE_EXTENSIONS | TEXT_EXTENSIONS

DEFAULT_IGNORED_DIRS = {
    ".git", "__pycache__", "node_modules", "venv", ".venv", "env",
    "dist", "build", ".mypy_cache", ".pytest_cache", "data",
}


@dataclass
class Chunk:
    file: str
    start_line: int
    end_line: int
    text: str
    kind: str  # "function" | "class" | "module" | "text"


def chunk_python_file(path: Path, source: str) -> list[Chunk]:
    """Split a Python file into one chunk per top-level function/class,
    plus one chunk for any remaining module-level code (imports, constants,
    top-level statements) that isn't inside a def/class."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Fall back to text chunking for files that don't parse (e.g. Python 2,
        # partially-written files) rather than dropping them entirely.
        return chunk_text(path, source)

    lines = source.splitlines()
    chunks: list[Chunk] = []
    covered_lines: set[int] = set()

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = node.lineno
            end = getattr(node, "end_lineno", start)
            snippet = "\n".join(lines[start - 1:end])
            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            chunks.append(Chunk(file=str(path), start_line=start, end_line=end, text=snippet, kind=kind))
            covered_lines.update(range(start, end + 1))

    # Capture module-level code not covered by a function/class chunk above
    # (imports, top-level constants, `if __name__ == "__main__"`, etc.)
    leftover_lines = [
        (i + 1, line) for i, line in enumerate(lines) if (i + 1) not in covered_lines and line.strip()
    ]
    if leftover_lines:
        start = leftover_lines[0][0]
        end = leftover_lines[-1][0]
        snippet = "\n".join(line for _, line in leftover_lines)
        chunks.append(Chunk(file=str(path), start_line=start, end_line=end, text=snippet, kind="module"))

    return chunks if chunks else chunk_text(path, source)


def chunk_text(path: Path, source: str, max_lines: int = 60, overlap: int = 10) -> list[Chunk]:
    """Line-based sliding-window chunking for non-Python / non-parseable files."""
    lines = source.splitlines()
    if not lines:
        return []

    chunks: list[Chunk] = []
    step = max(max_lines - overlap, 1)
    for start_idx in range(0, len(lines), step):
        end_idx = min(start_idx + max_lines, len(lines))
        snippet = "\n".join(lines[start_idx:end_idx])
        if snippet.strip():
            chunks.append(
                Chunk(file=str(path), start_line=start_idx + 1, end_line=end_idx, text=snippet, kind="text")
            )
        if end_idx == len(lines):
            break
    return chunks


def chunk_file(path: Path) -> list[Chunk]:
    """Dispatch to the right chunking strategy based on file extension."""
    try:
        source = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []

    if path.suffix in CODE_EXTENSIONS:
        return chunk_python_file(path, source)
    return chunk_text(path, source)


def walk_repo(repo_path: Path, include_extensions: set[str] | None = None) -> list[Path]:
    """Recursively find indexable files, skipping VCS/build/venv noise."""
    extensions = include_extensions or SUPPORTED_EXTENSIONS
    files: list[Path] = []
    for p in repo_path.rglob("*"):
        if not p.is_file():
            continue
        if any(part in DEFAULT_IGNORED_DIRS for part in p.parts):
            continue
        if p.suffix in extensions:
            files.append(p)
    return files
