"""Verify migration 001 adds watchdog columns and converts timestamps.

Runs against TEST_DATABASE_URL. The fixture creates a 'legacy' job_queue
schema first, then applies the migration, then asserts the new shape.
"""
import psycopg2
import pytest

from migrations.runner import apply_migration_001


@pytest.fixture
def legacy_job_queue(db_conn):
    """Recreate job_queue in its pre-migration shape."""
    cur = db_conn.cursor()
    cur.execute("DROP TABLE IF EXISTS job_queue")
    cur.execute(
        """
        CREATE TABLE job_queue (
            id SERIAL PRIMARY KEY,
            task_type VARCHAR(100) NOT NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'pending',
            payload TEXT NOT NULL,
            retries INTEGER NOT NULL DEFAULT 0,
            max_retries INTEGER NOT NULL DEFAULT 3,
            error_message TEXT,
            created_at VARCHAR(100) NOT NULL,
            updated_at VARCHAR(100) NOT NULL
        )
        """
    )
    cur.close()
    return db_conn


def _column_type(conn, table, column):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT data_type FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
        """,
        (table, column),
    )
    row = cur.fetchone()
    cur.close()
    return row[0] if row else None


def test_migration_adds_claimed_at(legacy_job_queue):
    apply_migration_001(legacy_job_queue)
    assert _column_type(legacy_job_queue, "job_queue", "claimed_at") == "timestamp with time zone"


def test_migration_adds_process_after(legacy_job_queue):
    apply_migration_001(legacy_job_queue)
    assert _column_type(legacy_job_queue, "job_queue", "process_after") == "timestamp with time zone"


def test_migration_converts_created_at_to_timestamptz(legacy_job_queue):
    apply_migration_001(legacy_job_queue)
    assert _column_type(legacy_job_queue, "job_queue", "created_at") == "timestamp with time zone"


def test_migration_converts_updated_at_to_timestamptz(legacy_job_queue):
    apply_migration_001(legacy_job_queue)
    assert _column_type(legacy_job_queue, "job_queue", "updated_at") == "timestamp with time zone"


def test_migration_is_idempotent(legacy_job_queue):
    apply_migration_001(legacy_job_queue)
    apply_migration_001(legacy_job_queue)  # second run must not raise
    assert _column_type(legacy_job_queue, "job_queue", "claimed_at") == "timestamp with time zone"
