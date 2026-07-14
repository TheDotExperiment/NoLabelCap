import sqlite3
import csv
import io
from contextlib import contextmanager

import config


def get_conn():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with open(config.BASE_DIR + "/schema.sql", "r") as f:
        schema = f.read()
    with db() as conn:
        conn.executescript(schema)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def create_user(fields: dict) -> int:
    cols = ", ".join(fields.keys())
    placeholders = ", ".join(["?"] * len(fields))
    with db() as conn:
        cur = conn.execute(
            f"INSERT INTO users ({cols}) VALUES ({placeholders})",
            list(fields.values()),
        )
        return cur.lastrowid


def update_user(user_id: int, fields: dict):
    set_clause = ", ".join(f"{k} = ?" for k in fields.keys())
    with db() as conn:
        conn.execute(
            f"UPDATE users SET {set_clause} WHERE id = ?",
            list(fields.values()) + [user_id],
        )


def get_user(user_id: int):
    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def get_user_by_payment_ref(session_id: str):
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE payment_reference = ?", (session_id,)
        ).fetchone()
        return dict(row) if row else None


def list_users(limit=500, offset=0):
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]


def export_users_csv() -> str:
    with db() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    if not rows:
        return ""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
    writer.writeheader()
    for r in rows:
        writer.writerow(dict(r))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Access codes
# ---------------------------------------------------------------------------

def get_code(code: str):
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM access_codes WHERE code = ?", (code.strip().upper(),)
        ).fetchone()
        return dict(row) if row else None


def increment_code_use(code: str):
    with db() as conn:
        conn.execute(
            "UPDATE access_codes SET uses_count = uses_count + 1 WHERE code = ?",
            (code.strip().upper(),),
        )


def create_code(fields: dict):
    fields = dict(fields)
    fields["code"] = fields["code"].strip().upper()
    cols = ", ".join(fields.keys())
    placeholders = ", ".join(["?"] * len(fields))
    with db() as conn:
        conn.execute(
            f"INSERT INTO access_codes ({cols}) VALUES ({placeholders})",
            list(fields.values()),
        )


def list_codes():
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM access_codes ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
