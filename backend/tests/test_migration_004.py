"""Tests for migration 004: proposal_items.sku_id FK → products(id) RESTRICT."""
import pytest
import psycopg2

from migrations.runner import (
    apply_migration_001, apply_migration_002, apply_migration_003, apply_migration_004,
)


def _apply_all_migrations(conn):
    apply_migration_001(conn)
    apply_migration_002(conn)
    apply_migration_003(conn)


def _create_proposal_items(conn):
    """Create proposal_items with the OLD FK to sku_catalog (mimics db_init state)."""
    cur = conn.cursor()
    # parent tables proposals + clients + users
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS clients (
            id SERIAL PRIMARY KEY, name TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS proposals (
            id SERIAL PRIMARY KEY, client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
            title VARCHAR(300), total_amount NUMERIC(14,2) DEFAULT 0,
            discount_global INTEGER DEFAULT 0, status VARCHAR(50) DEFAULT 'draft',
            email_sent BOOLEAN DEFAULT FALSE, created_at VARCHAR(100), updated_at VARCHAR(100)
        )
        """
    )
    # proposal_items with the legacy FK → sku_catalog(id) ON DELETE CASCADE
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS proposal_items (
            id SERIAL PRIMARY KEY,
            proposal_id INTEGER REFERENCES proposals(id) ON DELETE CASCADE,
            sku_id INTEGER REFERENCES sku_catalog(id) ON DELETE CASCADE,
            qty INTEGER NOT NULL DEFAULT 1,
            price_base NUMERIC(12,2) NOT NULL DEFAULT 0,
            discount_item INTEGER DEFAULT 0,
            price_final NUMERIC(12,2) NOT NULL DEFAULT 0
        )
        """
    )
    cur.close()


def _fk_target(conn, constraint_name: str) -> str | None:
    """Return the referenced table name for a given FK constraint, or None."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT confrelid::regclass::text
        FROM pg_constraint
        WHERE conname = %s AND contype = 'f'
        """,
        (constraint_name,),
    )
    row = cur.fetchone()
    cur.close()
    return row[0] if row else None


def _fk_delete_action(conn, constraint_name: str) -> str | None:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT confdeltype FROM pg_constraint WHERE conname = %s AND contype = 'f'
        """,
        (constraint_name,),
    )
    row = cur.fetchone()
    cur.close()
    # 'a' = NO ACTION, 'r' = RESTRICT, 'c' = CASCADE, 'n' = SET NULL, 'd' = SET DEFAULT
    return row[0] if row else None


def test_migration_repoints_fk_to_products(db_conn):
    """After migration, the FK should reference products(id), not sku_catalog."""
    _apply_all_migrations(db_conn)
    _create_proposal_items(db_conn)

    # Before migration: FK points at sku_catalog
    assert _fk_target(db_conn, "proposal_items_sku_id_fkey") in ("sku_catalog", None)

    apply_migration_004(db_conn)

    # After migration: FK points at products
    assert _fk_target(db_conn, "proposal_items_sku_id_fkey") == "products"


def test_migration_sets_on_delete_restrict(db_conn):
    """The new FK must be ON DELETE RESTRICT (protects historical proposals)."""
    _apply_all_migrations(db_conn)
    _create_proposal_items(db_conn)
    apply_migration_004(db_conn)
    assert _fk_delete_action(db_conn, "proposal_items_sku_id_fkey") == "r"


def test_migration_is_idempotent(db_conn):
    """Running migration twice must not error and must leave FK pointing at products."""
    _apply_all_migrations(db_conn)
    _create_proposal_items(db_conn)
    apply_migration_004(db_conn)
    apply_migration_004(db_conn)  # second run
    assert _fk_target(db_conn, "proposal_items_sku_id_fkey") == "products"
    assert _fk_delete_action(db_conn, "proposal_items_sku_id_fkey") == "r"


def test_migration_tolerant_when_proposal_items_absent(db_conn):
    """If proposal_items doesn't exist, migration is a no-op (fresh test DB)."""
    _apply_all_migrations(db_conn)
    # Do NOT create proposal_items.
    apply_migration_004(db_conn)  # should not raise
