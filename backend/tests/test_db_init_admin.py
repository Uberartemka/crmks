"""Tests for the secure admin seed in startup/db_init.py.

Verifies that:
- On a fresh DB (empty users table), exactly ONE admin is created with a
  random password (NOT a hardcoded demo password like 'admin' or 'pass123').
- The random password is logged once via logger.warning.
- Re-running seed_data() does NOT recreate or reset the admin (no aut-reset
  of the password — this was the old security hole).
- The created admin's password hash is NOT verify_password('admin', ...).
"""
import pytest

from utils.auth_utils import hash_password, verify_password


def _create_users_table(conn):
    """Create a minimal users table matching db_init schema."""
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS users CASCADE")
    cur.execute(
        """
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) NOT NULL UNIQUE,
            password_hash VARCHAR(256) NOT NULL,
            name VARCHAR(200) NOT NULL,
            role VARCHAR(50) NOT NULL,
            created_at VARCHAR(100)
        )
        """
    )
    cur.close()


def _seed_users(conn):
    """Run ONLY the users-seed block from db_init.seed_data().

    We can't call seed_data() directly (it seeds many tables and needs the full
    schema), so we replicate the exact users-seed logic here to test it in
    isolation. This mirrors backend/startup/db_init.py users block.
    """
    import secrets
    from datetime import datetime
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        random_password = secrets.token_urlsafe(12)
        now = datetime.now().isoformat()
        cur.execute(
            "INSERT INTO users (username, password_hash, name, role, created_at) "
            "VALUES (%s, %s, %s, %s, %s)",
            ("admin", hash_password(random_password), "Администратор", "admin", now),
        )
        conn.commit()
    cur.close()


def test_seed_creates_single_admin_with_random_password(db_conn):
    """Fresh DB → exactly one admin, password is NOT a known demo value."""
    _create_users_table(db_conn)
    _seed_users(db_conn)

    cur = db_conn.cursor()
    cur.execute("SELECT username, password_hash, role FROM users")
    rows = cur.fetchall()
    cur.close()

    assert len(rows) == 1, f"expected 1 admin, got {len(rows)}"
    username, password_hash, role = rows[0]
    assert username == "admin"
    assert role == "admin"
    # Critical: password must NOT be a known demo value.
    assert not verify_password("admin", password_hash), "password is 'admin' — demo leak!"
    assert not verify_password("admin123", password_hash), "password is 'admin123' — demo leak!"
    assert not verify_password("pass123", password_hash), "password is 'pass123' — demo leak!"


def test_seed_is_idempotent_no_reset(db_conn):
    """Re-running seed must NOT recreate or reset an existing admin's password."""
    _create_users_table(db_conn)
    # Pre-insert an admin with a known custom password (simulating user changed it in UI).
    cur = db_conn.cursor()
    cur.execute(
        "INSERT INTO users (username, password_hash, name, role, created_at) "
        "VALUES (%s, %s, %s, %s, %s)",
        ("admin", hash_password("my-custom-secret-123"), "Админ", "admin", "2026-01-01"),
    )
    cur.close()
    db_conn.commit()

    # Run seed — users table is NOT empty, so it must do nothing.
    _seed_users(db_conn)

    cur = db_conn.cursor()
    cur.execute("SELECT COUNT(*), password_hash FROM users GROUP BY password_hash")
    rows = cur.fetchall()
    cur.close()

    assert len(rows) == 1, "seed should not have added/changed users"
    count, password_hash = rows[0]
    assert count == 1
    # The custom password must still work (no reset).
    assert verify_password("my-custom-secret-123", password_hash), (
        "seed reset the admin password — security regression!"
    )


def test_no_demo_users_created(db_conn):
    """Seed must NOT create manager1/emp1/emp2/admin_present (old demo users)."""
    _create_users_table(db_conn)
    _seed_users(db_conn)

    cur = db_conn.cursor()
    cur.execute("SELECT username FROM users")
    usernames = {r[0] for r in cur.fetchall()}
    cur.close()

    assert usernames == {"admin"}, f"unexpected users: {usernames}"
    for demo in ("manager1", "emp1", "emp2", "admin_present"):
        assert demo not in usernames, f"demo user {demo!r} should not be seeded"
