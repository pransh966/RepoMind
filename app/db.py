from __future__ import annotations

import datetime
from typing import Any

import psycopg2
import psycopg2.extras

from app.config import settings


def get_conn():
    conn = psycopg2.connect(settings.database_url, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn


def init_db() -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS repos (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            source TEXT NOT NULL,          -- 'git' | 'upload'
            source_ref TEXT,               -- git URL, or original zip filename
            chunks_count INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS history (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            repo_id INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            citations TEXT NOT NULL,       -- JSON-encoded list[Citation]
            latency_ms REAL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    conn.commit()
    cur.close()
    conn.close()


def _row_to_dict(row) -> dict[str, Any] | None:
    if row is None:
        return None
    out = dict(row)
    for key, value in out.items():
        if isinstance(value, datetime.datetime):
            out[key] = value.isoformat()
    return out


def create_user(email: str, password_hash: str, salt: str) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (email, password_hash, salt) VALUES (%s, %s, %s) RETURNING id",
        (email.lower(), password_hash, salt),
    )
    user_id = cur.fetchone()["id"]
    conn.commit()
    cur.close()
    conn.close()
    return user_id


def get_user_by_email(email: str) -> dict | None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = %s", (email.lower(),))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return _row_to_dict(row)


def get_user_by_id(user_id: int) -> dict | None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return _row_to_dict(row)


def create_repo(user_id: int, name: str, source: str, source_ref: str | None) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO repos (user_id, name, source, source_ref, chunks_count) "
        "VALUES (%s, %s, %s, %s, 0) RETURNING id",
        (user_id, name, source, source_ref),
    )
    repo_id = cur.fetchone()["id"]
    conn.commit()
    cur.close()
    conn.close()
    return repo_id


def update_repo_chunks(repo_id: int, chunks_count: int) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE repos SET chunks_count = %s WHERE id = %s", (chunks_count, repo_id))
    conn.commit()
    cur.close()
    conn.close()


def get_repo(repo_id: int, user_id: int) -> dict | None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM repos WHERE id = %s AND user_id = %s", (repo_id, user_id))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return _row_to_dict(row)


def list_repos(user_id: int) -> list[dict]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM repos WHERE user_id = %s ORDER BY created_at DESC", (user_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def delete_repo(repo_id: int) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM repos WHERE id = %s", (repo_id,))
    conn.commit()
    cur.close()
    conn.close()


def add_history(user_id: int, repo_id: int, question: str, answer: str, citations_json: str, latency_ms: float) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO history (user_id, repo_id, question, answer, citations, latency_ms) "
        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (user_id, repo_id, question, answer, citations_json, latency_ms),
    )
    history_id = cur.fetchone()["id"]
    conn.commit()
    cur.close()
    conn.close()
    return history_id


def list_history(user_id: int, repo_id: int | None = None, limit: int = 100) -> list[dict]:
    conn = get_conn()
    cur = conn.cursor()
    if repo_id is not None:
        cur.execute(
            "SELECT * FROM history WHERE user_id = %s AND repo_id = %s ORDER BY created_at DESC LIMIT %s",
            (user_id, repo_id, limit),
        )
    else:
        cur.execute(
            "SELECT * FROM history WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
            (user_id, limit),
        )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_history_item(history_id: int, user_id: int) -> dict | None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM history WHERE id = %s AND user_id = %s", (history_id, user_id))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return _row_to_dict(row)


def delete_history_item(history_id: int, user_id: int) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM history WHERE id = %s AND user_id = %s", (history_id, user_id))
    deleted = cur.rowcount > 0
    conn.commit()
    cur.close()
    conn.close()
    return deleted


def clear_history(user_id: int, repo_id: int) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM history WHERE user_id = %s AND repo_id = %s", (user_id, repo_id))
    count = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    return count
