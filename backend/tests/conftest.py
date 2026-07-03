"""Shared pytest fixtures. Tests run against a real PostgreSQL test DB.

Requires env var TEST_DATABASE_URL pointing at a throwaway database.
The fixture resets the schema between tests by truncating known tables.
"""
import os
import pytest
import psycopg2

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://postgres:235813@localhost:5432/hhb_b2b_test",
)

# Tables that the watchdog/migration tests touch. Truncated before each test.
_TABLES_TO_CLEAR = ["job_queue"]


def _connect():
    return psycopg2.connect(TEST_DATABASE_URL)


@pytest.fixture
def db_conn():
    """Yield a raw psycopg2 connection to the test DB.

    Each test starts with job_queue empty. Schema (job_queue table) must be
    created by the migration-test setup or by running migrations first.
    """
    conn = _connect()
    conn.autocommit = True
    cur = conn.cursor()
    for t in _TABLES_TO_CLEAR:
        # TRUNCATE only if the table exists; migration tests may drop/recreate it.
        cur.execute(
            "TRUNCATE TABLE IF EXISTS {} RESTART IDENTITY CASCADE".format(t)
        )
    cur.close()
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture(scope="session")
def test_db_url():
    return TEST_DATABASE_URL
