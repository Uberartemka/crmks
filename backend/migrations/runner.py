"""Idempotent migration runner.

Applies numbered .sql files in order. Each migration is applied inside its
own transaction. No bookkeeping table (YAGNI for now): idempotency is
guaranteed by the SQL itself (every ALTER is guarded by information_schema
checks), so re-running is safe.
"""
import logging
from pathlib import Path

logger = logging.getLogger("HHB_B2B")

_MIGRATIONS_DIR = Path(__file__).parent


def apply_migration_001(conn) -> None:
    """Apply migration 001 to a *raw* psycopg2 connection.

    `conn` must be a sync psycopg2 connection; autocommit is set inside.
    """
    sql_path = _MIGRATIONS_DIR / "001_job_queue_watchdog.sql"
    sql = sql_path.read_text(encoding="utf-8")
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(sql)
    finally:
        cur.close()
    logger.info("[migration] 001_job_queue_watchdog.sql applied.")


def apply_migration_002(conn) -> None:
    """Apply migration 002 to a *raw* psycopg2 connection.

    Adds sku_catalog.application text[] to match the production schema on
    the sites server, so catalog imports preserve the application field.
    """
    sql_path = _MIGRATIONS_DIR / "002_sku_catalog_application.sql"
    sql = sql_path.read_text(encoding="utf-8")
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(sql)
    finally:
        cur.close()
    logger.info("[migration] 002_sku_catalog_application.sql applied.")


def apply_migration_003(conn) -> None:
    """Apply migration 003 — unified relational catalog (brands/categories/products)."""
    sql_path = _MIGRATIONS_DIR / "003_unified_catalog.sql"
    sql = sql_path.read_text(encoding="utf-8")
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(sql)
    finally:
        cur.close()
    logger.info("[migration] 003_unified_catalog.sql applied.")


def apply_migration_004(conn) -> None:
    """Apply migration 004 — repoint proposal_items.sku_id FK to products(id) RESTRICT.

    Safe on fresh DBs (idempotent, guarded). Assumes products + proposal_items
    tables already exist (created by migration 003 and startup/db_init).
    """
    sql_path = _MIGRATIONS_DIR / "004_proposal_items_fk_products.sql"
    sql = sql_path.read_text(encoding="utf-8")
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(sql)
    finally:
        cur.close()
    logger.info("[migration] 004_proposal_items_fk_products.sql applied.")


def apply_migration_005(conn) -> None:
    """Apply migration 005 — add users.client_id (links auth user → clients company).

    Foundation for Group C domains (defects, orders, machinery). Idempotent and
    safe on a fresh DB (guarded by information_schema checks). Assumes users +
    clients tables already exist (created by startup/db_init).
    """
    sql_path = _MIGRATIONS_DIR / "005_users_client_id.sql"
    sql = sql_path.read_text(encoding="utf-8")
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(sql)
    finally:
        cur.close()
    logger.info("[migration] 005_users_client_id.sql applied.")


def apply_migration_006(conn) -> None:
    """Apply migration 006 — defects table (дефектовка оборудования клиентов).

    Idempotent (CREATE TABLE IF NOT EXISTS + information_schema guard). Assumes
    clients + users tables already exist (created by startup/db_init).
    """
    sql_path = _MIGRATIONS_DIR / "006_defects.sql"
    sql = sql_path.read_text(encoding="utf-8")
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(sql)
    finally:
        cur.close()
    logger.info("[migration] 006_defects.sql applied.")


def apply_migration_007(conn) -> None:
    """Apply migration 007 — machinery table (карта оборудования клиентов).

    Idempotent (CREATE TABLE IF NOT EXISTS + information_schema guard). Assumes
    clients + users tables already exist (created by startup/db_init).
    """
    sql_path = _MIGRATIONS_DIR / "007_machinery.sql"
    sql = sql_path.read_text(encoding="utf-8")
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(sql)
    finally:
        cur.close()
    logger.info("[migration] 007_machinery.sql applied.")


def apply_migration_008(conn) -> None:
    """Apply migration 008 — orders table (заказы клиентов).

    Idempotent (CREATE TABLE IF NOT EXISTS + information_schema guard). Assumes
    clients + users tables already exist (created by startup/db_init).
    """
    sql_path = _MIGRATIONS_DIR / "008_orders.sql"
    sql = sql_path.read_text(encoding="utf-8")
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(sql)
    finally:
        cur.close()
    logger.info("[migration] 008_orders.sql applied.")


def apply_migration_009(conn) -> None:
    """Apply migration 009 — chat subsystem (channels/members/messages/read_state).

    Idempotent (CREATE TABLE IF NOT EXISTS + information_schema guards). Assumes
    users table already exists (created by startup/db_init). Also seeds the
    single 'general' channel (protected by a partial UNIQUE index).
    """
    sql_path = _MIGRATIONS_DIR / "009_chat.sql"
    sql = sql_path.read_text(encoding="utf-8")
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(sql)
    finally:
        cur.close()
    logger.info("[migration] 009_chat.sql applied.")


def apply_migration_010(conn) -> None:
    """Apply migration 010 — universal file storage (Подсистема II).

    Creates the 'files' table: uploaded_by → users, storage_path (relative to
    MEDIA_ROOT), thumbnail_path (for images), original_name, mime_type,
    size_bytes, sha256 (integrity + future dedup), is_image.
    """
    sql_path = _MIGRATIONS_DIR / "010_files.sql"
    sql = sql_path.read_text(encoding="utf-8")
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(sql)
    finally:
        cur.close()
    logger.info("[migration] 010_files.sql applied.")


def apply_migration_011(conn) -> None:
    """Apply migration 011 — user avatars (users.avatar_file_id → files)."""
    sql_path = _MIGRATIONS_DIR / "011_user_avatars.sql"
    sql = sql_path.read_text(encoding="utf-8")
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(sql)
    finally:
        cur.close()
    logger.info("[migration] 011_user_avatars.sql applied.")


def apply_migration_012(conn) -> None:
    """Apply migration 012 — chat message attachments (messages.attachment_id → files).

    Idempotent (ADD COLUMN IF NOT EXISTS / CREATE INDEX IF NOT EXISTS). Assumes
    messages + files tables exist (009/010). ON DELETE SET NULL: file removed →
    message survives without attachment (matches reply_to_id + avatar_file_id).
    """
    sql_path = _MIGRATIONS_DIR / "012_chat_attachments.sql"
    sql = sql_path.read_text(encoding="utf-8")
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(sql)
    finally:
        cur.close()
    logger.info("[migration] 012_chat_attachments.sql applied.")


def apply_all(dsn: str) -> None:
    """Apply all migrations to the DB at `dsn`. Used on app startup."""
    import psycopg2

    conn = psycopg2.connect(dsn)
    try:
        apply_migration_001(conn)
        apply_migration_002(conn)
        apply_migration_003(conn)
        apply_migration_004(conn)
        apply_migration_005(conn)
        apply_migration_006(conn)
        apply_migration_007(conn)
        apply_migration_008(conn)
        apply_migration_009(conn)
        apply_migration_010(conn)
        apply_migration_011(conn)
        apply_migration_012(conn)
    finally:
        conn.close()
