"""
Shared SQLite layer for the Afterlife colour and path bot + website.

One token now drives the whole flow: password, then colour, then path.
Both the Discord bot and the Flask site import this module. Every
function opens its own short-lived connection, which keeps things safe
across the bot's asyncio loop and Flask's request thread without needing
a shared connection object.
"""

import sqlite3
import time
import secrets
import hashlib
import contextlib
import os

DB_PATH = os.environ.get("DB_PATH", "afterlife.db")

# excludes ambiguous characters (0/O, 1/I) so the password is easy to type correctly
PASSWORD_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PASSWORD_LENGTH = 8
MAX_PASSWORD_ATTEMPTS = 5

PATH_CHOICES = ("nomad", "streetkid", "corpo")


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")  # lets bot + website hit it concurrently
    return conn


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def init_db():
    with contextlib.closing(_connect()) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tokens (
                token          TEXT PRIMARY KEY,
                user_id        INTEGER NOT NULL,
                guild_id       INTEGER NOT NULL,
                username       TEXT NOT NULL,
                created_at     INTEGER NOT NULL,
                expires_at     INTEGER NOT NULL,
                status         TEXT NOT NULL DEFAULT 'pending',
                colour_payload TEXT,
                path_payload   TEXT,
                password_hash  TEXT NOT NULL,
                verified       INTEGER NOT NULL DEFAULT 0,
                attempts       INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_roles (
                user_id     INTEGER NOT NULL,
                guild_id    INTEGER NOT NULL,
                kind        TEXT NOT NULL,
                role_id     INTEGER NOT NULL,
                PRIMARY KEY (user_id, guild_id, kind)
            )
        """)
        conn.commit()


def has_completed(user_id: int, guild_id: int) -> bool:
    """True if this member has ever finished the whole flow in this server before."""
    with contextlib.closing(_connect()) as conn:
        row = conn.execute(
            "SELECT 1 FROM tokens WHERE user_id=? AND guild_id=? AND status='applied' LIMIT 1",
            (user_id, guild_id),
        ).fetchone()
        return row is not None


def create_token(user_id: int, guild_id: int, username: str, ttl_seconds: int = 600):
    """Creates a token + one time password. Returns (token, password)."""
    token = secrets.token_urlsafe(20)
    password = "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(PASSWORD_LENGTH))
    now = int(time.time())
    with contextlib.closing(_connect()) as conn:
        # invalidate any older unused token for this user
        conn.execute(
            "UPDATE tokens SET status='superseded' WHERE user_id=? AND guild_id=? AND status='pending'",
            (user_id, guild_id),
        )
        conn.execute(
            "INSERT INTO tokens "
            "(token, user_id, guild_id, username, created_at, expires_at, status, password_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
            (token, user_id, guild_id, username, now, now + ttl_seconds, _hash_password(password)),
        )
        conn.commit()
    return token, password


def get_token(token: str):
    with contextlib.closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM tokens WHERE token=?", (token,)).fetchone()
        return dict(row) if row else None


def get_stage(row: dict) -> str:
    """Where a given token is in the flow: password, colour, path, or done."""
    if not row["verified"]:
        return "password"
    if row["colour_payload"] is None:
        return "colour"
    if row["path_payload"] is None:
        return "path"
    return "done"


def verify_password(token: str, submitted_password: str) -> str:
    """Returns 'ok', 'wrong', 'locked', or 'invalid'."""
    with contextlib.closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM tokens WHERE token=?", (token,)).fetchone()
        if not row or row["status"] != "pending" or row["expires_at"] < int(time.time()):
            return "invalid"
        if row["verified"]:
            return "ok"
        if _hash_password(submitted_password) == row["password_hash"]:
            conn.execute("UPDATE tokens SET verified=1 WHERE token=?", (token,))
            conn.commit()
            return "ok"

        attempts = row["attempts"] + 1
        if attempts >= MAX_PASSWORD_ATTEMPTS:
            conn.execute("UPDATE tokens SET attempts=?, status='failed' WHERE token=?", (attempts, token))
            conn.commit()
            return "locked"
        conn.execute("UPDATE tokens SET attempts=? WHERE token=?", (attempts, token))
        conn.commit()
        return "wrong"


def _is_valid_hex(value: str) -> bool:
    if not value or len(value) != 7 or value[0] != "#":
        return False
    try:
        int(value[1:], 16)
        return True
    except ValueError:
        return False


def submit_colour(token: str, hex_colour: str) -> bool:
    """First step of the flow. Requires verified, and that colour hasn't been set yet."""
    if not _is_valid_hex(hex_colour):
        return False
    with contextlib.closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM tokens WHERE token=?", (token,)).fetchone()
        if not row or row["status"] != "pending" or row["expires_at"] < int(time.time()):
            return False
        if not row["verified"] or row["colour_payload"] is not None:
            return False
        conn.execute("UPDATE tokens SET colour_payload=? WHERE token=?", (hex_colour, token))
        conn.commit()
        return True


def submit_path(token: str, path_choice: str) -> bool:
    """Second step of the flow. Requires colour already set, and path not yet set.
    Setting this also flips status to 'submitted', which is what the bot polls for."""
    if path_choice not in PATH_CHOICES:
        return False
    with contextlib.closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM tokens WHERE token=?", (token,)).fetchone()
        if not row or row["status"] != "pending" or row["expires_at"] < int(time.time()):
            return False
        if not row["verified"] or row["colour_payload"] is None or row["path_payload"] is not None:
            return False
        conn.execute(
            "UPDATE tokens SET path_payload=?, status='submitted' WHERE token=?", (path_choice, token)
        )
        conn.commit()
        return True


def get_pending_submissions():
    with contextlib.closing(_connect()) as conn:
        rows = conn.execute("SELECT * FROM tokens WHERE status='submitted'").fetchall()
        return [dict(r) for r in rows]


def mark_applied(token: str):
    with contextlib.closing(_connect()) as conn:
        conn.execute("UPDATE tokens SET status='applied' WHERE token=?", (token,))
        conn.commit()


def mark_failed(token: str):
    with contextlib.closing(_connect()) as conn:
        conn.execute("UPDATE tokens SET status='failed' WHERE token=?", (token,))
        conn.commit()


def get_user_role(user_id: int, guild_id: int, kind: str):
    with contextlib.closing(_connect()) as conn:
        row = conn.execute(
            "SELECT role_id FROM user_roles WHERE user_id=? AND guild_id=? AND kind=?",
            (user_id, guild_id, kind),
        ).fetchone()
        return row["role_id"] if row else None


def set_user_role(user_id: int, guild_id: int, kind: str, role_id: int):
    with contextlib.closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO user_roles (user_id, guild_id, kind, role_id) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id, guild_id, kind) DO UPDATE SET role_id=excluded.role_id",
            (user_id, guild_id, kind, role_id),
        )
        conn.commit()
