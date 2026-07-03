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
# Order matters: products references categories/brands, list dependents first.
_TABLES_TO_CLEAR = ["products", "categories", "brands", "sku_catalog", "job_queue"]


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
        # Only truncate if the table actually exists; migration tests may
        # drop/recreate it, and the very first run has no job_queue yet.
        # PostgreSQL does not support TRUNCATE ... IF EXISTS, so we gate on
        # to_regclass() which returns NULL for missing relations.
        cur.execute("SELECT to_regclass('public.%s')" % t)
        if cur.fetchone()[0] is not None:
            cur.execute("TRUNCATE TABLE {} RESTART IDENTITY CASCADE".format(t))
    cur.close()
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture(scope="session")
def test_db_url():
    return TEST_DATABASE_URL
