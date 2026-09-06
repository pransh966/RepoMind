"""
SQLite persistence for users, repos, and query history.

Plain stdlib sqlite3, no ORM -- this app's data model is simple enough
(3 tables, no complex joins) that SQLAlchemy would be more machinery than
value here. sqlite3.Row gives dict-like row access without one.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from app.config import settings

DB_PATH = Path(settings.data_dir) / "repomind.db"


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS repos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            source TEXT NOT NULL,          -- "git" | "upload"
            source_ref TEXT,               -- git URL, or original zip filename
            chunks_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            repo_id INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            citations TEXT NOT NULL,       -- JSON-encoded list[Citation]
            latency_ms REAL,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# --- users -------------------------------------------------------------

def create_user(email: str, password_hash: str, salt: str) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO users (email, password_hash, salt, created_at) VALUES (?, ?, ?, ?)",
        (email.lower(), password_hash, salt, _now()),
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()
    return user_id


def get_user_by_email(email: str) -> sqlite3.Row | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()
    conn.close()
    return row


def get_user_by_id(user_id: int) -> sqlite3.Row | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return row


# --- repos ---------------------------------------------------------------

def create_repo(user_id: int, name: str, source: str, source_ref: str | None) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO repos (user_id, name, source, source_ref, chunks_count, created_at) VALUES (?, ?, ?, ?, 0, ?)",
        (user_id, name, source, source_ref, _now()),
    )
    conn.commit()
    repo_id = cur.lastrowid
    conn.close()
    return repo_id


def update_repo_chunks(repo_id: int, chunks_count: int) -> None:
    conn = get_conn()
    conn.execute("UPDATE repos SET chunks_count = ? WHERE id = ?", (chunks_count, repo_id))
    conn.commit()
    conn.close()


def get_repo(repo_id: int, user_id: int) -> sqlite3.Row | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM repos WHERE id = ? AND user_id = ?", (repo_id, user_id)).fetchone()
    conn.close()
    return row


def list_repos(user_id: int) -> list[sqlite3.Row]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM repos WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
    ).fetchall()
    conn.close()
    return rows


def delete_repo(repo_id: int) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM repos WHERE id = ?", (repo_id,))
    conn.commit()
    conn.close()


# --- history ---------------------------------------------------------------

def add_history(user_id: int, repo_id: int, question: str, answer: str, citations_json: str, latency_ms: float) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO history (user_id, repo_id, question, answer, citations, latency_ms, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, repo_id, question, answer, citations_json, latency_ms, _now()),
    )
    conn.commit()
    history_id = cur.lastrowid
    conn.close()
    return history_id


def list_history(user_id: int, repo_id: int | None = None, limit: int = 100) -> list[sqlite3.Row]:
    conn = get_conn()
    if repo_id is not None:
        rows = conn.execute(
            "SELECT * FROM history WHERE user_id = ? AND repo_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, repo_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM history WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    conn.close()
    return rows
