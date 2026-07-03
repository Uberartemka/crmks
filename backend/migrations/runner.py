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


def apply_all(dsn: str) -> None:
    """Apply all migrations to the DB at `dsn`. Used on app startup."""
    import psycopg2

    conn = psycopg2.connect(dsn)
    try:
        apply_migration_001(conn)
        apply_migration_002(conn)
    finally:
        conn.close()
