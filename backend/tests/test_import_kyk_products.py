"""Tests for the kyk.products import script.

The import reads from a staging table `kyk_products_import` (loaded via
deploy/import_kyk_products.sh from the remote sites server) and writes into
the unified products/brands/categories tables. Existing rows matching
(code, brand) are ENRICHED — NULL characteristic fields filled from source,
non-NULL fields preserved. Brand/category lookup is case-insensitive so
'Kyk' resolves to an existing 'KYK' brand instead of duplicating.
"""
import pytest

from migrations.runner import (
    apply_migration_001, apply_migration_002, apply_migration_003,
)
from scripts.import_kyk_products import import_from_kyk


def _apply_all_migrations(conn):
    apply_migration_001(conn)
    apply_migration_002(conn)
    apply_migration_003(conn)


@pytest.fixture
def seeded_kyk_import(db_conn):
    """Recreate kyk_products_import staging and seed rows that exercise
    insert / enrich / case-insensitive-brand / inactive paths."""
    _apply_all_migrations(db_conn)
    cur = db_conn.cursor()
    cur.execute("DROP TABLE IF EXISTS kyk_products_import")
    # Mirror of the staging schema produced by deploy/import_kyk_products.sh.
    cur.execute(
        """
        CREATE TABLE kyk_products_import (
            id integer,
            code text,
            name text,
            category text,
            brand text,
            weight real,
            price_old real,
            price_new real,
            d real,
            d_outer real,
            b_width real,
            rs_min real,
            static_load real,
            dynamic_load real,
            rpm_oil integer,
            rpm_grease integer,
            seal_type text,
            created_at bigint,
            updated_at bigint,
            stock integer,
            is_active boolean
        )
        """
    )
    # Row 1: brand-new active product with full characteristics.
    # Row 2: brand-new inactive product, no prices (mirrors the 650 hidden).
    # Row 3: same code as a pre-existing KYK product WITHOUT characteristics
    #        → must enrich, not duplicate.
    cur.execute(
        """
        INSERT INTO kyk_products_import
            (id, code, name, category, brand, weight, price_old, price_new,
             d, d_outer, b_width, rs_min, static_load, dynamic_load,
             rpm_oil, rpm_grease, seal_type, created_at, updated_at, stock, is_active)
        VALUES
            (10, '6203 ZZ', 'Подшипник 6203 ZZ', 'Шарикоподшипники с глубоким желобом', 'Kyk',
             0.30, 110.0, 95.0, 17, 40, 12, 0.5, 6.2, 9.5, 14000, 11000, 'ZZ',
             1685448531, 1685448531, 300, true),
            (11, '604', 'Подшипник 604', 'Миниатюрные шарикоподшипники', 'Kyk',
             0.0021, NULL, NULL, 4, 12, 4, 0.2, 0.36, 0.97, 63000, 53000, 'Открытый',
             1685448531, 1685448531, 0, false),
            (12, '605', 'Подшипник 605 (source)', 'Миниатюрные шарикоподшипники', 'Kyk',
             0.0025, 50.0, 45.0, 5, 14, 5, 0.3, 0.5, 1.2, 60000, 50000, 'ZZ',
             1685448531, 1685448531, 10, true)
        """
    )
    # Pre-existing KYK product with NO characteristics — target for enrichment.
    # Note brand created as 'KYK' (uppercase) to test case-insensitive match.
    cur.execute("INSERT INTO brands (name, slug) VALUES ('KYK', 'kyk') RETURNING id")
    kyk_brand_id = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO products (code, name, brand_id, rs_min) VALUES ('605', 'Подшипник 605 (existing)', %s, 999)",
        (kyk_brand_id,),
    )
    # Clean any other products/categories so assertions are deterministic.
    cur.execute("DELETE FROM products WHERE code NOT IN ('605')")
    cur.execute("DELETE FROM categories")
    cur.close()
    return db_conn


def test_import_inserts_new_products(seeded_kyk_import):
    conn = seeded_kyk_import
    stats = import_from_kyk(conn)
    # Rows 1 ('6203 ZZ') and 2 ('604') are new; row 3 ('605') enriches existing.
    assert stats["inserted"] == 2
    assert stats["enriched"] == 1
    assert stats["errors"] == 0


def test_import_maps_all_characteristics(seeded_kyk_import):
    conn = seeded_kyk_import
    import_from_kyk(conn)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT weight, d, d_outer, b_width, rs_min, static_load, dynamic_load,
               rpm_oil, rpm_grease, seal_type
        FROM products WHERE code = '6203 ZZ'
        """
    )
    (weight, d, d_outer, b_width, rs_min, static_load, dynamic_load,
     rpm_oil, rpm_grease, seal_type) = cur.fetchone()
    cur.close()
    assert float(weight) == 0.30
    assert float(d) == 17
    assert float(d_outer) == 40
    assert float(b_width) == 12
    assert float(rs_min) == 0.5
    assert float(static_load) == 6.2
    assert float(dynamic_load) == 9.5
    assert rpm_oil == 14000
    assert rpm_grease == 11000
    assert seal_type == "ZZ"


def test_import_preserves_prices_and_stock(seeded_kyk_import):
    conn = seeded_kyk_import
    import_from_kyk(conn)
    cur = conn.cursor()
    cur.execute("SELECT price_old, price_new, stock FROM products WHERE code='6203 ZZ'")
    price_old, price_new, stock = cur.fetchone()
    cur.close()
    assert float(price_old) == 110.0
    assert float(price_new) == 95.0
    assert stock == 300


def test_import_preserves_is_active(seeded_kyk_import):
    conn = seeded_kyk_import
    import_from_kyk(conn)
    cur = conn.cursor()
    cur.execute("SELECT is_active FROM products WHERE code IN ('6203 ZZ','604') ORDER BY code")
    states = [r[0] for r in cur.fetchall()]
    cur.close()
    assert states == [False, True]   # '604' false, '6203 ZZ' true (ordered by code)


def test_import_converts_unix_timestamps(seeded_kyk_import):
    conn = seeded_kyk_import
    import_from_kyk(conn)
    cur = conn.cursor()
    cur.execute("SELECT created_at FROM products WHERE code='6203 ZZ'")
    created_at = cur.fetchone()[0]
    cur.close()
    # 1685448531 epoch -> 2023-05-30 10:48:51 UTC
    assert created_at.year == 2023
    assert created_at.month == 5


def test_import_enriches_existing_without_overwriting(seeded_kyk_import):
    """Existing '605' (rs_min=999) must be enriched with the other NULL fields,
    but rs_min must NOT be overwritten by source (0.3)."""
    conn = seeded_kyk_import
    stats = import_from_kyk(conn)
    assert stats["enriched"] == 1
    cur = conn.cursor()
    cur.execute(
        "SELECT rs_min, static_load, dynamic_load, d, d_outer, name FROM products WHERE code='605'"
    )
    rs_min, static_load, dynamic_load, d, d_outer, name = cur.fetchone()
    cur.close()
    # Source rs_min=0.3 must NOT overwrite the existing 999.
    assert float(rs_min) == 999
    # But NULL fields are filled from source.
    assert float(static_load) == 0.5
    assert float(dynamic_load) == 1.2
    assert float(d) == 5
    assert float(d_outer) == 14
    # Name (non-NULL) is preserved — source name not forced in.
    assert name == "Подшипник 605 (existing)"


def test_import_resolves_brand_case_insensitive(seeded_kyk_import):
    """Source brand 'Kyk' must resolve to pre-existing 'KYK', not duplicate."""
    conn = seeded_kyk_import
    import_from_kyk(conn)
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM brands WHERE LOWER(name) = 'kyk'")
    n = cur.fetchone()[0]
    cur.close()
    assert n == 1


def test_import_creates_categories(seeded_kyk_import):
    conn = seeded_kyk_import
    import_from_kyk(conn)
    cur = conn.cursor()
    cur.execute("SELECT name FROM categories ORDER BY name")
    names = {r[0] for r in cur.fetchall()}
    cur.close()
    assert "Шарикоподшипники с глубоким желобом" in names
    assert "Миниатюрные шарикоподшипники" in names


def test_import_is_idempotent(seeded_kyk_import):
    conn = seeded_kyk_import
    first = import_from_kyk(conn)
    second = import_from_kyk(conn)
    assert first["inserted"] == 2
    # Second run: nothing new inserted; existing rows re-enriched (no-op COALESCE).
    assert second["inserted"] == 0
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM products WHERE code IN ('6203 ZZ','604','605')")
    assert cur.fetchone()[0] == 3
    cur.close()


def test_import_no_staging_returns_empty(db_conn):
    """If staging table is absent, import is a no-op with empty stats."""
    _apply_all_migrations(db_conn)
    # Do NOT create kyk_products_import.
    stats = import_from_kyk(db_conn)
    assert stats == {"inserted": 0, "enriched": 0, "errors": 0}


def test_import_skips_rows_without_code(seeded_kyk_import):
    """Rows with NULL code must be skipped, not crash the import."""
    conn = seeded_kyk_import
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO kyk_products_import (id, code, name, brand) VALUES (99, NULL, 'no code', 'Kyk')"
    )
    cur.close()
    stats = import_from_kyk(conn)
    # Same 2 inserts + 1 enrich as before; the NULL-code row is filtered in SELECT.
    assert stats["inserted"] == 2
    assert stats["errors"] == 0
