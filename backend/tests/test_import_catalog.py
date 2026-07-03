"""Tests for the catalog import script.

The import reads from the local DB's sku_catalog (legacy flat table) and
writes into the unified products/brands/categories tables. We seed a small
fake sku_catalog and assert the import transforms it correctly.
"""
import pytest

from migrations.runner import (
    apply_migration_001, apply_migration_002, apply_migration_003,
)
from scripts.import_catalog import import_from_sku_catalog


def _apply_all_migrations(conn):
    apply_migration_001(conn)
    apply_migration_002(conn)
    apply_migration_003(conn)


@pytest.fixture
def seeded_sku_catalog(db_conn):
    """Recreate sku_catalog (legacy) and seed 3 rows."""
    _apply_all_migrations(db_conn)
    cur = db_conn.cursor()
    cur.execute("DROP TABLE IF EXISTS sku_catalog")
    cur.execute(
        """
        CREATE TABLE sku_catalog (
            id serial PRIMARY KEY,
            sku text NOT NULL,
            category text,
            brand text,
            d_inner numeric(10,2),
            d_outer numeric(10,2),
            b_width numeric(10,2),
            price numeric(12,2),
            stock text,
            application text[],
            img text
        )
        """
    )
    cur.execute(
        "INSERT INTO sku_catalog (sku, category, brand, d_inner, d_outer, b_width, price, stock, application, img) VALUES "
        "('604', 'Миниатюрные', 'KYK', 4, 12, 4, 100, 'В наличии', '{\"Универсальное\"}', NULL), "
        "('UCF204', 'Корпусные узлы', 'FKD', NULL, NULL, NULL, 307, 'В наличии', '{}', NULL), "
        "('HHB-001', 'Прочие', 'HHB', 10, 30, 8, NULL, NULL, '{}', NULL)"
    )
    # Clean unified tables so import starts fresh.
    cur.execute("DELETE FROM products")
    cur.execute("DELETE FROM brands")
    cur.execute("DELETE FROM categories")
    cur.close()
    return db_conn


def test_import_creates_brands(seeded_sku_catalog):
    conn = seeded_sku_catalog
    import_from_sku_catalog(conn)
    cur = conn.cursor()
    cur.execute("SELECT name FROM brands ORDER BY name")
    names = [r[0] for r in cur.fetchall()]
    cur.close()
    assert set(names) >= {"KYK", "FKD", "HHB"}


def test_import_creates_categories(seeded_sku_catalog):
    conn = seeded_sku_catalog
    import_from_sku_catalog(conn)
    cur = conn.cursor()
    cur.execute("SELECT name FROM categories ORDER BY name")
    names = [r[0] for r in cur.fetchall()]
    cur.close()
    assert set(names) >= {"Миниатюрные", "Корпусные узлы", "Прочие"}


def test_import_transforms_rows(seeded_sku_catalog):
    conn = seeded_sku_catalog
    stats = import_from_sku_catalog(conn)
    assert stats["inserted"] == 3
    cur = conn.cursor()
    cur.execute("SELECT code FROM products ORDER BY code")
    codes = [r[0] for r in cur.fetchall()]
    cur.close()
    assert codes == ["604", "HHB-001", "UCF204"]


def test_import_maps_d_inner_to_d(seeded_sku_catalog):
    conn = seeded_sku_catalog
    import_from_sku_catalog(conn)
    cur = conn.cursor()
    cur.execute("SELECT d, d_outer, price_new FROM products WHERE code='604'")
    d, d_outer, price = cur.fetchone()
    cur.close()
    assert float(d) == 4
    assert float(d_outer) == 12
    assert float(price) == 100


def test_import_preserves_application(seeded_sku_catalog):
    conn = seeded_sku_catalog
    import_from_sku_catalog(conn)
    cur = conn.cursor()
    cur.execute("SELECT application FROM products WHERE code='604'")
    app = cur.fetchone()[0]
    cur.close()
    assert app == ["Универсальное"]


def test_import_is_idempotent(seeded_sku_catalog):
    conn = seeded_sku_catalog
    first = import_from_sku_catalog(conn)
    second = import_from_sku_catalog(conn)
    assert first["inserted"] == 3
    # second run: rows already there, no duplicates
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM products")
    count = cur.fetchone()[0]
    cur.close()
    assert count == 3


def test_import_dedups_on_code_brand(seeded_sku_catalog):
    """Same code+brand already in unified table → skip, do not duplicate."""
    conn = seeded_sku_catalog
    # Pre-insert one row with code='604', brand 'KYK'
    cur = conn.cursor()
    cur.execute("INSERT INTO brands (name, slug) VALUES ('KYK', 'kyk') RETURNING id")
    brand_id = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO products (code, name, brand_id, d) VALUES ('604', 'PREEXISTING', %s, 999)",
        (brand_id,),
    )
    cur.close()
    stats = import_from_sku_catalog(conn)
    # Only 2 new inserts (604 is skipped as duplicate)
    assert stats["inserted"] == 2
    assert stats["skipped_duplicates"] == 1
