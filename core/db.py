"""
SQLite persistent storage for Nokia GPON Router device metadata and nicknames.
"""
import os
import sqlite3
from datetime import datetime
from typing import Any, Optional

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DB_DIR, "router.db")


def get_db_connection() -> sqlite3.Connection:
    """Get a SQLite database connection with row factory enabled."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize the database tables if they do not exist."""
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                mac TEXT PRIMARY KEY,
                nickname TEXT,
                hostname TEXT,
                last_ip TEXT,
                last_interface TEXT,
                is_blocked INTEGER DEFAULT 0,
                first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                notes TEXT
            )
        """)
        conn.commit()


# Initialize on import
init_db()


def upsert_device(
    mac: str,
    hostname: Optional[str] = None,
    ip: Optional[str] = None,
    interface: Optional[str] = None,
    is_blocked: Optional[bool] = None,
) -> None:
    """Insert or update device record in database, preserving existing nickname and notes."""
    mac = mac.strip().lower()
    now = datetime.utcnow().isoformat()

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT nickname, notes, is_blocked FROM devices WHERE mac = ?", (mac,))
        existing = cursor.fetchone()

        if existing:
            current_blocked = existing["is_blocked"] if is_blocked is None else (1 if is_blocked else 0)
            cursor.execute("""
                UPDATE devices
                SET hostname = COALESCE(?, hostname),
                    last_ip = COALESCE(?, last_ip),
                    last_interface = COALESCE(?, last_interface),
                    is_blocked = ?,
                    last_seen = ?
                WHERE mac = ?
            """, (hostname, ip, interface, current_blocked, now, mac))
        else:
            blocked_val = 1 if is_blocked else 0
            cursor.execute("""
                INSERT INTO devices (mac, nickname, hostname, last_ip, last_interface, is_blocked, first_seen, last_seen, notes)
                VALUES (?, NULL, ?, ?, ?, ?, ?, ?, NULL)
            """, (mac, hostname, ip, interface, blocked_val, now, now))
        conn.commit()


def set_device_nickname(mac: str, nickname: Optional[str], notes: Optional[str] = None) -> bool:
    """Set or remove nickname and optional notes for a device by MAC address."""
    mac = mac.strip().lower()
    nickname_val = nickname.strip() if nickname and nickname.strip() else None
    now = datetime.utcnow().isoformat()

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT mac FROM devices WHERE mac = ?", (mac,))
        existing = cursor.fetchone()

        if existing:
            cursor.execute("""
                UPDATE devices
                SET nickname = ?,
                    notes = COALESCE(?, notes),
                    last_seen = ?
                WHERE mac = ?
            """, (nickname_val, notes, now, mac))
        else:
            cursor.execute("""
                INSERT INTO devices (mac, nickname, hostname, last_ip, last_interface, is_blocked, first_seen, last_seen, notes)
                VALUES (?, ?, NULL, NULL, NULL, 0, ?, ?, ?)
            """, (mac, nickname_val, now, now, notes))
        conn.commit()
        return True


def get_device(mac: str) -> Optional[dict[str, Any]]:
    """Get device details from database by MAC address."""
    mac = mac.strip().lower()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM devices WHERE mac = ?", (mac,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_all_devices() -> list[dict[str, Any]]:
    """Get all saved devices from database."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM devices ORDER BY last_seen DESC")
        return [dict(row) for row in cursor.fetchall()]


def find_device_by_query(query: str) -> list[dict[str, Any]]:
    """
    Search for devices by matching against nickname, hostname, IP, or MAC.
    Supports exact and partial/case-insensitive matching.
    """
    query = query.strip().lower()
    if not query:
        return []

    with get_db_connection() as conn:
        cursor = conn.cursor()
        # 1. Exact match on MAC
        cursor.execute("SELECT * FROM devices WHERE mac = ?", (query,))
        exact_mac = cursor.fetchall()
        if exact_mac:
            return [dict(r) for r in exact_mac]

        # 2. Exact match on nickname
        cursor.execute("SELECT * FROM devices WHERE LOWER(nickname) = ?", (query,))
        exact_nick = cursor.fetchall()
        if exact_nick:
            return [dict(r) for r in exact_nick]

        # 3. Substring match across nickname, hostname, last_ip, mac
        pattern = f"%{query}%"
        cursor.execute("""
            SELECT * FROM devices
            WHERE LOWER(COALESCE(nickname, '')) LIKE ?
               OR LOWER(COALESCE(hostname, '')) LIKE ?
               OR LOWER(COALESCE(last_ip, '')) LIKE ?
               OR LOWER(mac) LIKE ?
            ORDER BY
               CASE WHEN LOWER(nickname) LIKE ? THEN 1
                    WHEN LOWER(hostname) LIKE ? THEN 2
                    ELSE 3 END,
               last_seen DESC
        """, (pattern, pattern, pattern, pattern, pattern, pattern))
        return [dict(r) for r in cursor.fetchall()]
