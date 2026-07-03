"""Verify migration 003 creates brands, categories, products tables."""
import pytest

from migrations.runner import apply_migration_003


@pytest.fixture
def empty_db(db_conn):
    """Drop the unified-catalog tables so migration creates them fresh."""
    cur = db_conn.cursor()
    cur.execute("DROP TABLE IF EXISTS products CASCADE")
    cur.execute("DROP TABLE IF EXISTS categories CASCADE")
    cur.execute("DROP TABLE IF EXISTS brands CASCADE")
    cur.close()
    return db_conn


def _table_exists(conn, table):
    cur = conn.cursor()
    cur.execute("SELECT to_regclass('public.%s')" % table)
    row = cur.fetchone()
    cur.close()
    return row[0] is not None


def _column_type(conn, table, column):
    cur = conn.cursor()
    cur.execute(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name=%s AND column_name=%s",
        (table, column),
    )
    row = cur.fetchone()
    cur.close()
    return row[0] if row else None


def test_creates_brands_table(empty_db):
    apply_migration_003(empty_db)
    assert _table_exists(empty_db, "brands")
    assert _column_type(empty_db, "brands", "name") == "text"
    assert _column_type(empty_db, "brands", "slug") == "text"


def test_creates_categories_table_with_parent(empty_db):
    apply_migration_003(empty_db)
    assert _table_exists(empty_db, "categories")
    assert _column_type(empty_db, "categories", "parent_id") == "integer"


def test_creates_products_table_with_specs(empty_db):
    apply_migration_003(empty_db)
    assert _table_exists(empty_db, "products")
    for col in ("d", "d_outer", "b_width", "rs_min", "static_load",
                "dynamic_load", "rpm_oil", "rpm_grease", "seal_type", "weight"):
        assert _column_type(empty_db, "products", col) is not None, f"missing {col}"
    assert _column_type(empty_db, "products", "application") == "ARRAY"


def test_migration_is_idempotent(empty_db):
    apply_migration_003(empty_db)
    apply_migration_003(empty_db)  # must not raise
    assert _table_exists(empty_db, "products")
