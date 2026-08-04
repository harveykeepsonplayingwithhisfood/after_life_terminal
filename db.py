"""
Shared SQLite layer for the Afterlife colour bot + website.

Both the Discord bot and the Flask site import this module. Every function
opens its own short-lived connection, which keeps things safe across the
bot's asyncio loop and Flask's request thread without needing a shared
connection object.
"""

import sqlite3
import time
import secrets
import contextlib
import os

DB_PATH = os.environ.get("DB_PATH", "afterlife.db")


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")  # lets bot + website hit it concurrently
    return conn


def init_db():
    with contextlib.closing(_connect()) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS colour_tokens (
                token       TEXT PRIMARY KEY,
                user_id     INTEGER NOT NULL,
                guild_id    INTEGER NOT NULL,
                username    TEXT NOT NULL,
                created_at  INTEGER NOT NULL,
                expires_at  INTEGER NOT NULL,
                status      TEXT NOT NULL DEFAULT 'pending',
                hex_colour  TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_roles (
                user_id     INTEGER NOT NULL,
                guild_id    INTEGER NOT NULL,
                role_id     INTEGER NOT NULL,
                PRIMARY KEY (user_id, guild_id)
            )
        """)
        conn.commit()


def create_token(user_id: int, guild_id: int, username: str, ttl_seconds: int = 600) -> str:
    token = secrets.token_urlsafe(20)
    now = int(time.time())
    with contextlib.closing(_connect()) as conn:
        # invalidate any older unused tokens for this user so only one link is ever live
        conn.execute(
            "UPDATE colour_tokens SET status='superseded' "
            "WHERE user_id=? AND guild_id=? AND status='pending'",
            (user_id, guild_id),
        )
        conn.execute(
            "INSERT INTO colour_tokens (token, user_id, guild_id, username, created_at, expires_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?, 'pending')",
            (token, user_id, guild_id, username, now, now + ttl_seconds),
        )
        conn.commit()
    return token


def get_token(token: str):
    with contextlib.closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM colour_tokens WHERE token=?", (token,)).fetchone()
        return dict(row) if row else None


def is_token_valid(row) -> bool:
    return bool(row) and row["status"] == "pending" and row["expires_at"] >= int(time.time())


def submit_colour(token: str, hex_colour: str) -> bool:
    with contextlib.closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM colour_tokens WHERE token=?", (token,)).fetchone()
        if not row or row["status"] != "pending" or row["expires_at"] < int(time.time()):
            return False
        conn.execute(
            "UPDATE colour_tokens SET status='submitted', hex_colour=? WHERE token=?",
            (hex_colour, token),
        )
        conn.commit()
        return True


def get_pending_submissions():
    with contextlib.closing(_connect()) as conn:
        rows = conn.execute("SELECT * FROM colour_tokens WHERE status='submitted'").fetchall()
        return [dict(r) for r in rows]


def mark_applied(token: str):
    with contextlib.closing(_connect()) as conn:
        conn.execute("UPDATE colour_tokens SET status='applied' WHERE token=?", (token,))
        conn.commit()


def mark_failed(token: str):
    with contextlib.closing(_connect()) as conn:
        conn.execute("UPDATE colour_tokens SET status='failed' WHERE token=?", (token,))
        conn.commit()


def get_user_role(user_id: int, guild_id: int):
    with contextlib.closing(_connect()) as conn:
        row = conn.execute(
            "SELECT role_id FROM user_roles WHERE user_id=? AND guild_id=?",
            (user_id, guild_id),
        ).fetchone()
        return row["role_id"] if row else None


def set_user_role(user_id: int, guild_id: int, role_id: int):
    with contextlib.closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO user_roles (user_id, guild_id, role_id) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, guild_id) DO UPDATE SET role_id=excluded.role_id",
            (user_id, guild_id, role_id),
        )
        conn.commit()
