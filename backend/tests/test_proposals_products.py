"""Tests for proposal-flow reading from unified products (not sku_catalog).

Covers the migration of the 4 SKU touchpoints (proposals.py get_proposal JOIN,
add_proposal_item price read, email_service JOIN, ai_claude_agent ILIKE) to
the products table. Verifies:
- creating a proposal_item reads price from products.price_new
- reading a proposal returns code/name/brand from products+brands
- a non-existent sku_id returns 404

Uses the same monkeypatch pattern as test_catalog_v1_routes: patch the
module-level `get_db` symbol in each route module to return a test-DB conn.
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


def _apply_all_migrations(conn):
    apply_migration_001(conn)
    apply_migration_002(conn)
    apply_migration_003(conn)


def _seed_proposal_tables(conn):
    """Create proposal-flow tables (mimic startup/db_init) and seed one product.

    NOTE: proposal_items is created with FK → products(id) ON DELETE RESTRICT,
    matching migration 004's target state. We do NOT call apply_migration_004
    here because that migration only runs when proposal_items already exists
    with the legacy FK; in the test we create it directly in the target state.
    """
    cur = conn.cursor()
    # Drop dependents + recreate parent tables with a clean schema. The test DB
    # may carry an older `clients` schema from past runs, so IF NOT EXISTS won't
    # add missing columns — we DROP and recreate to guarantee our shape.
    cur.execute("DROP TABLE IF EXISTS proposal_items CASCADE")
    cur.execute("DROP TABLE IF EXISTS proposals CASCADE")
    cur.execute("DROP TABLE IF EXISTS clients CASCADE")
    cur.execute(
        """
        CREATE TABLE clients (
            id SERIAL PRIMARY KEY, name TEXT, email TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE proposals (
            id SERIAL PRIMARY KEY,
            client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
            title VARCHAR(300), total_amount NUMERIC(14,2) DEFAULT 0,
            discount_global INTEGER DEFAULT 0, status VARCHAR(50) DEFAULT 'draft',
            email_sent BOOLEAN DEFAULT FALSE,
            created_at VARCHAR(100), updated_at VARCHAR(100)
        )
        """
    )
    # proposal_items with the target-state FK → products(id) ON DELETE RESTRICT.
    cur.execute(
        """
        CREATE TABLE proposal_items (
            id SERIAL PRIMARY KEY,
            proposal_id INTEGER REFERENCES proposals(id) ON DELETE CASCADE,
            sku_id INTEGER REFERENCES products(id) ON DELETE RESTRICT,
            qty INTEGER NOT NULL DEFAULT 1,
            price_base NUMERIC(12,2) NOT NULL DEFAULT 0,
            discount_item INTEGER DEFAULT 0,
            price_final NUMERIC(12,2) NOT NULL DEFAULT 0
        )
        """
    )
    # Seed: 1 client, 1 proposal, 1 product with brand.
    cur.execute(
        "INSERT INTO clients (name, email) VALUES ('ООО Тест', 't@t.t') "
        "ON CONFLICT DO NOTHING"
    )
    cur.execute(
        "INSERT INTO proposals (id, client_id, title, total_amount, status) "
        "VALUES (1, 1, 'КП тест', 0, 'draft') ON CONFLICT (id) DO NOTHING"
    )
    cur.execute(
        "INSERT INTO brands (name, slug) VALUES ('KYK', 'kyk-test') "
        "ON CONFLICT (name) DO NOTHING"
    )
    cur.execute("SELECT id FROM brands WHERE name='KYK'")
    brand_id = cur.fetchone()[0]
    cur.execute(
        """
        INSERT INTO products (id, code, name, brand_id, price_new, stock)
        VALUES (1, '6203 ZZ', 'Подшипник 6203 ZZ', %s, 95.0, 10)
        ON CONFLICT (id) DO NOTHING
        """,
        (brand_id,),
    )
    cur.close()


@pytest.fixture
def proposals_client(db_conn, request):
    """Wire a TestClient with proposals router pointed at the test DB."""
    _apply_all_migrations(db_conn)
    _seed_proposal_tables(db_conn)

    # Monkeypatch get_db in routes.proposals (where it's imported as a module symbol).
    import routes.proposals as proposals_mod

    def _test_get_db():
        return psycopg2.connect(TEST_DATABASE_URL)

    original = proposals_mod.get_db
    proposals_mod.get_db = _test_get_db
    request.addfinalizer(lambda: setattr(proposals_mod, "get_db", original))

    # Minimal app with just the proposals router.
    from routes.proposals import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_add_item_reads_price_from_products(proposals_client):
    """POST /api/proposals/{id}/items snapshots price from products.price_new."""
    resp = proposals_client.post(
        "/api/proposals/1/items",
        json={"sku_id": 1, "qty": 2, "discount_item": 0},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "added"


def test_add_item_404_on_unknown_sku(proposals_client):
    """A sku_id not in products returns 404."""
    resp = proposals_client.post(
        "/api/proposals/1/items",
        json={"sku_id": 999999, "qty": 1, "discount_item": 0},
    )
    assert resp.status_code == 404


def test_get_proposal_returns_products_data(proposals_client):
    """GET /api/proposals/{id} returns code/name/brand from products+brands."""
    proposals_client.post(
        "/api/proposals/1/items",
        json={"sku_id": 1, "qty": 1, "discount_item": 0},
    )
    resp = proposals_client.get("/api/proposals/1")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    it = items[0]
    assert it["sku"] == "6203 ZZ"             # products.code
    assert it["type"] == "Подшипник 6203 ZZ"  # products.name
    assert it["brand"] == "KYK"               # brands.name
    assert float(it["price_base"]) == 95.0    # products.price_new snapshot


def test_email_enrichment_pulls_from_products(db_conn, request):
    """email_service._get_proposal_for_email reads code/name from products."""
    _apply_all_migrations(db_conn)
    _seed_proposal_tables(db_conn)

    # Insert a proposal_item manually pointing at the seeded product.
    cur = db_conn.cursor()
    cur.execute(
        "INSERT INTO proposal_items (proposal_id, sku_id, qty, price_base, discount_item, price_final) "
        "VALUES (1, 1, 2, 95.0, 0, 95.0)"
    )
    cur.close()

    # email_service uses get_db from the db module — patch that.
    import services.email_service as email_mod

    def _test_get_db():
        return psycopg2.connect(TEST_DATABASE_URL)

    original = email_mod.get_db
    email_mod.get_db = _test_get_db
    request.addfinalizer(lambda: setattr(email_mod, "get_db", original))

    from services.email_service import _get_proposal_for_email
    proposal = _get_proposal_for_email(1)
    assert len(proposal["items"]) == 1
    item = proposal["items"][0]
    assert item["sku"] == "6203 ZZ"             # products.code
    assert item["type"] == "Подшипник 6203 ZZ"  # products.name
