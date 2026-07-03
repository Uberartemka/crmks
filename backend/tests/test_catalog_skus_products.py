"""Tests for /api/catalog/skus reading from unified products.

Verifies the endpoint (used by /admin/proposals to list SKU) now reads from
`products` (+ brands + categories) instead of the legacy `sku_catalog`. The
response shape is preserved (sku, brand, d, D, B, type, price) so the existing
frontend keeps working.
"""
import os

import psycopg2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from migrations.runner import (
    apply_migration_001, apply_migration_002, apply_migration_003,
)

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://postgres:235813@localhost:5432/hhb_b2b_test",
)


def _apply_all(conn):
    apply_migration_001(conn)
    apply_migration_002(conn)
    apply_migration_003(conn)


def _seed(conn):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO brands (id, name, slug) VALUES (1, 'KYK', 'kyk') "
        "ON CONFLICT (id) DO NOTHING"
    )
    cur.execute(
        "INSERT INTO categories (id, name, slug) VALUES (1, 'Миниатюрные', 'min') "
        "ON CONFLICT (id) DO NOTHING"
    )
    cur.execute(
        """
        INSERT INTO products (id, code, name, brand_id, category_id, d, d_outer, b_width, price_new, stock, is_active)
        VALUES
            (1, '6203 ZZ', 'Подшипник 6203 ZZ', 1, 1, 17, 40, 12, 95.0, 10, true),
            (2, '604', 'Подшипник 604', 1, 1, 4, 12, 4, NULL, 0, false)
        ON CONFLICT (id) DO NOTHING
        """
    )
    cur.close()


@pytest.fixture
def catalog_client(db_conn, request):
    """Build a FastAPI app with catalog_skus router pointed at the test DB.

    Uses the same monkeypatch pattern as test_catalog_v1_routes: patch the
    module-level `get_db` symbol in routes.catalog_skus.
    """
    _apply_all(db_conn)
    _seed(db_conn)

    import routes.catalog_skus as mod

    def _test_get_db():
        return psycopg2.connect(TEST_DATABASE_URL)

    original = mod.get_db
    mod.get_db = _test_get_db
    request.addfinalizer(lambda: setattr(mod, "get_db", original))

    from routes.catalog_skus import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_list_skus_returns_from_products(catalog_client):
    """6203 ZZ lives in products, not sku_catalog — must be findable now."""
    resp = catalog_client.get("/api/catalog/skus?search=6203")
    assert resp.status_code == 200
    items = resp.json()
    assert any(i["sku"] == "6203 ZZ" for i in items), items


def test_list_skus_preserves_field_shape(catalog_client):
    """Response keeps the legacy field names (sku, brand, d, D, B, price) for frontend compat."""
    resp = catalog_client.get("/api/catalog/skus?search=6203")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    it = items[0]
    # Legacy fields must be present.
    for field in ("id", "sku", "brand", "d", "D", "B", "price", "stock", "type"):
        assert field in it, f"missing field {field}"
    assert it["sku"] == "6203 ZZ"          # products.code
    assert it["brand"] == "KYK"            # brands.name
    assert it["type"] == "Подшипник 6203 ZZ"  # products.name
    assert float(it["d"]) == 17            # products.d
    assert float(it["price"]) == 95.0      # products.price_new


def test_list_skus_d_filter_uses_products(catalog_client):
    """d_min/d_max filters operate on products.d."""
    resp = catalog_client.get("/api/catalog/skus?d_min=10")
    assert resp.status_code == 200
    items = resp.json()
    # Only '6203 ZZ' (d=17) passes; '604' (d=4) is filtered out.
    assert {i["sku"] for i in items} == {"6203 ZZ"}
