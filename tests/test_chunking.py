from pathlib import Path

from app.chunking import chunk_python_file, chunk_text, walk_repo

SAMPLE_PY = '''\
import os

CONST = 42

def add(a, b):
    """Add two numbers."""
    return a + b


class Greeter:
    def __init__(self, name):
        self.name = name

    def greet(self):
        return f"Hello, {self.name}"
'''


def test_chunk_python_file_splits_by_top_level_def_and_class():
    chunks = chunk_python_file(Path("sample.py"), SAMPLE_PY)
    kinds = sorted(c.kind for c in chunks)
    assert "function" in kinds
    assert "class" in kinds
    assert "module" in kinds  # the import + CONST line

    func_chunk = next(c for c in chunks if c.kind == "function")
    assert "def add(a, b):" in func_chunk.text

    class_chunk = next(c for c in chunks if c.kind == "class")
    assert "class Greeter:" in class_chunk.text
    assert "def greet(self):" in class_chunk.text  # method stays inside its class chunk


def test_chunk_python_file_handles_syntax_errors_gracefully():
    broken = "def broken(:\n    this is not valid python"
    chunks = chunk_python_file(Path("broken.py"), broken)
    # should fall back to text chunking instead of raising
    assert len(chunks) >= 1
    assert chunks[0].kind == "text"


def test_chunk_text_respects_max_lines_and_overlap():
    text = "\n".join(f"line {i}" for i in range(1, 101))  # 100 lines
    chunks = chunk_text(Path("notes.md"), text, max_lines=40, overlap=10)
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 40
    assert chunks[1].start_line == 31  # step = max_lines - overlap = 30
    assert chunks[-1].end_line == 100


def test_walk_repo_skips_ignored_dirs(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("x = 1")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "junk.py").write_text("y = 2")

    files = walk_repo(tmp_path)
    names = [f.name for f in files]
    assert "main.py" in names
    assert "junk.py" not in names
