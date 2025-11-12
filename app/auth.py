import datetime as dt
from typing import Dict, Optional

from .db import get_connection
from .security import generate_token, verify_password

SESSION_TTL_MINUTES = 720


def create_session(username: str, password: str) -> Optional[Dict]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, password_hash, role FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    if not row or not verify_password(password, row["password_hash"]):
        conn.close()
        return None

    token = generate_token()
    now = dt.datetime.utcnow().isoformat()
    cur.execute(
        "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
        (token, row["id"], now),
    )
    conn.commit()
    conn.close()
    return {"token": token, "role": row["role"], "username": username}


def get_user_by_token(token: str) -> Optional[Dict]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT sessions.token, users.username, users.role, sessions.created_at FROM sessions "
        "JOIN users ON users.id = sessions.user_id WHERE sessions.token = ?",
        (token,),
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        return None

    created_at = dt.datetime.fromisoformat(row["created_at"])
    if dt.datetime.utcnow() - created_at > dt.timedelta(minutes=SESSION_TTL_MINUTES):
        cur.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
        conn.close()
        return None

    conn.close()
    return {"token": row["token"], "username": row["username"], "role": row["role"]}


def delete_session(token: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()
    conn.close()
