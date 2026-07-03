"""Tests for /api/v1/* catalog routes via FastAPI TestClient.

Uses dependency_overrides to point get_db at the test DB connection so the
route reads/writes the same schema the test seeds.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from migrations.runner import (
    apply_migration_001, apply_migration_002, apply_migration_003,
)
from routes.catalog_v1 import router, get_db


def _apply_all_migrations(conn):
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
        "INSERT INTO categories (id, name, slug) VALUES (1, 'Подшипники', 'bearings') "
        "ON CONFLICT (id) DO NOTHING"
    )
    cur.execute(
        "INSERT INTO products (id, code, name, brand_id, category_id, d, stock) "
        "VALUES (1, '604', 'P604', 1, 1, 4, 0) ON CONFLICT (id) DO NOTHING"
    )
    cur.close()


TEST_DATABASE_URL = (
    __import__("os").getenv(
        "TEST_DATABASE_URL",
        "postgresql://postgres:235813@localhost:5432/hhb_b2b_test",
    )
)


def _make_app(db_conn, request):
    """Build a FastAPI app that reads from the test DB.

    routes.catalog_v1 calls get_db() directly (not via Depends), so FastAPI
    dependency_overrides won't help — we monkeypatch the module-level
    `get_db` symbol in routes.catalog_v1 to return a test-DB connection.
    Restoration is done via request.addfinalizer (reliable ordering).
    """
    import psycopg2
    import routes.catalog_v1 as mod

    def _test_get_db():
        return psycopg2.connect(TEST_DATABASE_URL)

    original = mod.get_db
    mod.get_db = _test_get_db
    request.addfinalizer(lambda: setattr(mod, "get_db", original))

    app = FastAPI()
    app.include_router(router)
    return app


def test_get_products_list(db_conn, request):
    _apply_all_migrations(db_conn)
    _seed(db_conn)
    client = TestClient(_make_app(db_conn, request))
    resp = client.get("/api/v1/products")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert body["items"][0]["code"] == "604"


def test_get_product_by_id(db_conn, request):
    _apply_all_migrations(db_conn)
    _seed(db_conn)
    client = TestClient(_make_app(db_conn, request))
    resp = client.get("/api/v1/products/1")
    assert resp.status_code == 200
    assert resp.json()["code"] == "604"


def test_get_product_missing_returns_404(db_conn, request):
    _apply_all_migrations(db_conn)
    client = TestClient(_make_app(db_conn, request))
    resp = client.get("/api/v1/products/99999")
    assert resp.status_code == 404


def test_get_brands(db_conn, request):
    _apply_all_migrations(db_conn)
    _seed(db_conn)
    client = TestClient(_make_app(db_conn, request))
    resp = client.get("/api/v1/brands")
    assert resp.status_code == 200
    assert any(b["slug"] == "kyk" for b in resp.json())


def test_get_categories(db_conn, request):
    _apply_all_migrations(db_conn)
    _seed(db_conn)
    client = TestClient(_make_app(db_conn, request))
    resp = client.get("/api/v1/categories")
    assert resp.status_code == 200
    assert any(c["slug"] == "bearings" for c in resp.json())


def test_filter_by_brand(db_conn, request):
    _apply_all_migrations(db_conn)
    _seed(db_conn)
    client = TestClient(_make_app(db_conn, request))
    resp = client.get("/api/v1/products", params={"brand": "kyk"})
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


# --- Stock-update auth gate ---
import os
import auth as _auth_mod


def _set_b2b_token(request, token):
    """Force the B2B token used by verify_b2b_token (read at import time)."""
    original = _auth_mod.B2B_ADMIN_TOKEN
    _auth_mod.B2B_ADMIN_TOKEN = token
    request.addfinalizer(lambda: setattr(_auth_mod, "B2B_ADMIN_TOKEN", original))


def test_stock_update_without_token_returns_401(db_conn, request):
    _apply_all_migrations(db_conn)
    _seed(db_conn)
    _set_b2b_token(request, "secret_xyz")
    client = TestClient(_make_app(db_conn, request))
    resp = client.post("/api/v1/products/1/stock", json={"stock": 5})
    assert resp.status_code == 401


def test_stock_update_with_wrong_token_returns_401(db_conn, request):
    _apply_all_migrations(db_conn)
    _seed(db_conn)
    _set_b2b_token(request, "secret_xyz")
    client = TestClient(_make_app(db_conn, request))
    resp = client.post(
        "/api/v1/products/1/stock",
        json={"stock": 5},
        headers={"Authorization": "Bearer wrong"},
    )
    assert resp.status_code == 401


def test_stock_update_with_correct_token_works(db_conn, request):
    _apply_all_migrations(db_conn)
    _seed(db_conn)
    _set_b2b_token(request, "secret_xyz")
    client = TestClient(_make_app(db_conn, request))
    resp = client.post(
        "/api/v1/products/1/stock",
        json={"stock": 99, "price_new": 150.0},
        headers={"Authorization": "Bearer secret_xyz"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    # verify DB
    cur = db_conn.cursor()
    cur.execute("SELECT stock, price_new FROM products WHERE id=1")
    stock, price = cur.fetchone()
    cur.close()
    assert stock == 99
    assert float(price) == 150.0


def test_stock_update_missing_product_returns_404(db_conn, request):
    _apply_all_migrations(db_conn)
    _set_b2b_token(request, "secret_xyz")
    client = TestClient(_make_app(db_conn, request))
    resp = client.post(
        "/api/v1/products/99999/stock",
        json={"stock": 1},
        headers={"Authorization": "Bearer secret_xyz"},
    )
    assert resp.status_code == 404

