# Unified Catalog + API v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat `sku_catalog` with a relational catalog (brands, categories, products with full bearing specs) and expose it via `/api/v1/*` endpoints for the three sites to consume.

**Architecture:** Three new tables (`brands`, `categories` with parent_id, `products` with all bearing characteristics) created via migration 003. A one-shot Python import script moves kyk.products (735, full specs) and transforms hhb_b2b.sku_catalog (478, already in CRM) into the new schema, deduplicating on `(code, brand_id)`. New `routes/catalog_v1.py` router exposes filtered list, product card, brands, categories, and stock get/post. Public reads, B2B-token writes.

**Tech Stack:** Python 3.12, FastAPI, psycopg2, PostgreSQL, Redis, pytest.

**Reference spec:** `docs/superpowers/specs/2026-07-04-unified-catalog-api-design.md`.

---

## File Structure

**Create:**
- `backend/migrations/003_unified_catalog.sql` — schema for brands/categories/products
- `backend/scripts/__init__.py` — package marker
- `backend/scripts/import_catalog.py` — one-shot data import (kyk + hhb → unified)
- `backend/routes/catalog_v1.py` — new API v1 router
- `backend/services/catalog_v1_service.py` — DB access layer (queries, caching)
- `backend/tests/test_migration_003.py`
- `backend/tests/test_import_catalog.py`
- `backend/tests/test_catalog_v1_service.py`
- `backend/tests/test_catalog_v1_routes.py`

**Modify:**
- `backend/migrations/runner.py` — register `apply_migration_003`
- `backend/routes/index.py` — register the v1 router in `register_routes()`
- `backend/tests/conftest.py` — add `brands`, `categories`, `products` to truncate list

**Responsibilities:**
- `migrations/003_unified_catalog.sql` — DDL only, idempotent.
- `scripts/import_catalog.py` — reads from local DB (`sku_catalog` already imported) + remote DB (`kyk`), writes to unified tables. Idempotent.
- `services/catalog_v1_service.py` — pure DB functions: `list_products(filters)`, `get_product(id)`, `list_brands()`, `list_categories()`, `update_stock(id, payload)`. Caching layer.
- `routes/catalog_v1.py` — thin HTTP layer over the service. Validation, auth, response shaping.

---

## Prerequisites

The test DB (`hhb_b2b_test`) must exist (created during watchdog plan). For the import-script test (Task 4), the script reads from the local test DB's `sku_catalog` — tests will seed minimal fake data there instead of connecting to production servers.

Set:
```
set TEST_DATABASE_URL=postgresql://postgres:235813@localhost:5432/hhb_b2b_test
```

---

## Task 1: Migration 003 — schema

**Files:**
- Create: `backend/migrations/003_unified_catalog.sql`
- Modify: `backend/migrations/runner.py`
- Test: `backend/tests/test_migration_003.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_migration_003.py`:

```python
"""Verify migration 003 creates brands, categories, products tables."""
import psycopg2
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
```

- [ ] **Step 2: Run test to verify it fails**

```
python -m pytest tests/test_migration_003.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'migrations.runner'` style — actually `AttributeError: module 'migrations.runner' has no attribute 'apply_migration_003'`.

- [ ] **Step 3: Create the migration SQL**

Create `backend/migrations/003_unified_catalog.sql`:

```sql
-- Migration 003: unified relational catalog
-- Idempotent: every CREATE guards on existence.
-- Replaces the flat sku_catalog for new logic; old table stays until sites migrate.

-- 1. brands
CREATE TABLE IF NOT EXISTS brands (
    id      serial PRIMARY KEY,
    name    text NOT NULL UNIQUE,
    slug    text UNIQUE
);

-- 2. categories (with self-reference for nesting)
CREATE TABLE IF NOT EXISTS categories (
    id        serial PRIMARY KEY,
    name      text NOT NULL,
    slug      text UNIQUE,
    title     text,
    parent_id integer REFERENCES categories(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_categories_parent ON categories (parent_id);

-- 3. products (flat table with full bearing specs + FKs)
CREATE TABLE IF NOT EXISTS products (
    id            serial PRIMARY KEY,
    category_id   integer REFERENCES categories(id) ON DELETE SET NULL,
    brand_id      integer REFERENCES brands(id) ON DELETE SET NULL,
    code          text NOT NULL,
    name          text NOT NULL,
    weight        numeric(10,4),
    d             numeric(10,2),
    d_outer       numeric(10,2),
    b_width       numeric(10,2),
    rs_min        numeric(10,2),
    static_load   numeric(10,2),
    dynamic_load  numeric(10,2),
    rpm_oil       integer,
    rpm_grease    integer,
    seal_type     text,
    price_old     numeric(12,2),
    price_new     numeric(12,2),
    stock         integer NOT NULL DEFAULT 0,
    is_active     boolean NOT NULL DEFAULT true,
    application   text[] NOT NULL DEFAULT '{}',
    img           text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (code, brand_id)
);
CREATE INDEX IF NOT EXISTS idx_products_category ON products (category_id);
CREATE INDEX IF NOT EXISTS idx_products_brand    ON products (brand_id);
CREATE INDEX IF NOT EXISTS idx_products_active   ON products (is_active) WHERE is_active;
CREATE INDEX IF NOT EXISTS idx_products_code     ON products (code);
```

- [ ] **Step 4: Register in runner**

In `backend/migrations/runner.py`, add after `apply_migration_002`:

```python
def apply_migration_003(conn) -> None:
    """Apply migration 003 — unified relational catalog (brands/categories/products)."""
    sql_path = _MIGRATIONS_DIR / "003_unified_catalog.sql"
    sql = sql_path.read_text(encoding="utf-8")
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(sql)
    finally:
        cur.close()
    logger.info("[migration] 003_unified_catalog.sql applied.")
```

And in `apply_all`, add the call:

```python
def apply_all(dsn: str) -> None:
    """Apply all migrations to the DB at `dsn`. Used on app startup."""
    import psycopg2

    conn = psycopg2.connect(dsn)
    try:
        apply_migration_001(conn)
        apply_migration_002(conn)
        apply_migration_003(conn)
    finally:
        conn.close()
```

- [ ] **Step 5: Run tests to verify they pass**

```
python -m pytest tests/test_migration_003.py -v
```
Expected: 4 passed.

- [ ] **Step 6: Commit**

```
git add backend/migrations/ backend/tests/test_migration_003.py
git commit -m "feat(db): migration 003 — unified relational catalog schema"
```

---

## Task 2: Update conftest truncate list

**Files:**
- Modify: `backend/tests/conftest.py`

- [ ] **Step 1: Extend the truncate list**

In `backend/tests/conftest.py`, change:

```python
_TABLES_TO_CLEAR = ["job_queue"]
```

to:

```python
_TABLES_TO_CLEAR = ["products", "categories", "brands", "sku_catalog", "job_queue"]
```

Order matters: `products` references `categories`/`brands`, so it must be truncated first (TRUNCATE CASCADE handles it but explicit order is clearer).

- [ ] **Step 2: Verify no regression**

```
python -m pytest tests/test_migration_003.py tests/test_migration_001.py -v
```
Expected: all pass.

- [ ] **Step 3: Commit**

```
git add backend/tests/conftest.py
git commit -m "test: extend conftest truncate list for unified catalog tables"
```

---

## Task 3: Catalog service — list_products with filters

**Files:**
- Create: `backend/services/catalog_v1_service.py`
- Test: `backend/tests/test_catalog_v1_service.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_catalog_v1_service.py`:

```python
"""Tests for catalog_v1_service.list_products."""
from datetime import datetime, timezone

from migrations.runner import apply_migration_001, apply_migration_002, apply_migration_003
from services.catalog_v1_service import list_products


def _apply_all_migrations(conn):
    apply_migration_001(conn)
    apply_migration_002(conn)
    apply_migration_003(conn)


def _seed(conn, *, brands, categories, products):
    cur = conn.cursor()
    for b in brands:
        cur.execute(
            "INSERT INTO brands (id, name, slug) VALUES (%s, %s, %s) "
            "ON CONFLICT (id) DO NOTHING",
            (b["id"], b["name"], b["slug"]),
        )
    for c in categories:
        cur.execute(
            "INSERT INTO categories (id, name, slug, parent_id) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (id) DO NOTHING",
            (c["id"], c["name"], c["slug"], c.get("parent_id")),
        )
    for p in products:
        cur.execute(
            """INSERT INTO products
               (id, code, name, brand_id, category_id, d, d_outer, stock, is_active)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (id) DO NOTHING""",
            (p["id"], p["code"], p["name"], p.get("brand_id"),
             p.get("category_id"), p.get("d"), p.get("d_outer"),
             p.get("stock", 0), p.get("is_active", True)),
        )
    cur.close()


def _brands():
    return [
        {"id": 1, "name": "KYK", "slug": "kyk"},
        {"id": 2, "name": "FKD", "slug": "fkd"},
    ]


def _categories():
    return [
        {"id": 1, "name": "Подшипники", "slug": "bearings", "parent_id": None},
        {"id": 2, "name": "Миниатюрные", "slug": "mini", "parent_id": 1},
    ]


def test_list_all_products(db_conn):
    _apply_all_migrations(db_conn)
    _seed(db_conn, brands=_brands(), categories=_categories(), products=[
        {"id": 1, "code": "604", "name": "P604", "brand_id": 1, "category_id": 2, "d": 4},
        {"id": 2, "code": "605", "name": "P605", "brand_id": 2, "category_id": 1, "d": 5},
    ])
    result = list_products(db_conn)
    assert result["total"] == 2
    assert len(result["items"]) == 2


def test_filter_by_brand_slug(db_conn):
    _apply_all_migrations(db_conn)
    _seed(db_conn, brands=_brands(), categories=_categories(), products=[
        {"id": 1, "code": "604", "name": "P604", "brand_id": 1, "category_id": 2},
        {"id": 2, "code": "605", "name": "P605", "brand_id": 2, "category_id": 1},
    ])
    result = list_products(db_conn, brand="kyk")
    assert result["total"] == 1
    assert result["items"][0]["code"] == "604"


def test_filter_by_d_range(db_conn):
    _apply_all_migrations(db_conn)
    _seed(db_conn, brands=_brands(), categories=_categories(), products=[
        {"id": 1, "code": "604", "name": "P604", "brand_id": 1, "d": 4},
        {"id": 2, "code": "605", "name": "P605", "brand_id": 1, "d": 20},
        {"id": 3, "code": "606", "name": "P606", "brand_id": 1, "d": 50},
    ])
    result = list_products(db_conn, d_min=10, d_max=30)
    assert result["total"] == 1
    assert result["items"][0]["code"] == "605"


def test_filter_has_stock(db_conn):
    _apply_all_migrations(db_conn)
    _seed(db_conn, brands=_brands(), categories=_categories(), products=[
        {"id": 1, "code": "604", "name": "P604", "brand_id": 1, "stock": 0},
        {"id": 2, "code": "605", "name": "P605", "brand_id": 1, "stock": 10},
    ])
    result = list_products(db_conn, has_stock=True)
    assert result["total"] == 1
    assert result["items"][0]["code"] == "605"


def test_filter_inactive_hidden_by_default(db_conn):
    _apply_all_migrations(db_conn)
    _seed(db_conn, brands=_brands(), categories=_categories(), products=[
        {"id": 1, "code": "604", "name": "P604", "brand_id": 1, "is_active": True},
        {"id": 2, "code": "605", "name": "P605", "brand_id": 1, "is_active": False},
    ])
    result = list_products(db_conn)
    assert result["total"] == 1
    assert result["items"][0]["code"] == "604"


def test_pagination(db_conn):
    _apply_all_migrations(db_conn)
    _seed(db_conn, brands=_brands(), categories=_categories(), products=[
        {"id": i, "code": f"60{i}", "name": f"P{i}", "brand_id": 1} for i in range(1, 6)
    ])
    page1 = list_products(db_conn, limit=2, offset=0)
    page2 = list_products(db_conn, limit=2, offset=2)
    assert page1["total"] == 5
    assert len(page1["items"]) == 2
    assert len(page2["items"]) == 2
    assert page1["items"][0]["id"] != page2["items"][0]["id"]
```

- [ ] **Step 2: Run test to verify it fails**

```
python -m pytest tests/test_catalog_v1_service.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'services.catalog_v1_service'`.

- [ ] **Step 3: Implement list_products**

Create `backend/services/catalog_v1_service.py`:

```python
"""Catalog v1 service — DB access layer for the unified catalog.

All functions take a raw psycopg2 connection (sync) and return plain dicts.
No caching here initially — caching is added in Task 8.
"""
import logging
from typing import Any, Optional

logger = logging.getLogger("HHB_B2B")

# Columns returned by the list endpoint (NOT all specs — those are in get_product).
_LIST_COLUMNS = (
    "p.id", "p.code", "p.name",
    "b.id AS brand_id", "b.name AS brand_name", "b.slug AS brand_slug",
    "c.id AS category_id", "c.name AS category_name", "c.slug AS category_slug",
    "p.d", "p.d_outer", "p.b_width",
    "p.price_new", "p.stock", "p.is_active",
)


def list_products(
    conn,
    *,
    brand: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    d_min: Optional[float] = None,
    d_max: Optional[float] = None,
    d_outer_min: Optional[float] = None,
    d_outer_max: Optional[float] = None,
    seal_type: Optional[str] = None,
    has_stock: Optional[bool] = None,
    is_active: Optional[bool] = True,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Filter and paginate products. Returns {items, total, limit, offset}."""
    # Clamp pagination.
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))

    where = []
    params: list[Any] = []

    if brand:
        where.append("b.slug = %s")
        params.append(brand)
    if category:
        where.append("c.slug = %s")
        params.append(category)
    if search:
        where.append("(p.code ILIKE %s OR p.name ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    if d_min is not None:
        where.append("p.d >= %s")
        params.append(d_min)
    if d_max is not None:
        where.append("p.d <= %s")
        params.append(d_max)
    if d_outer_min is not None:
        where.append("p.d_outer >= %s")
        params.append(d_outer_min)
    if d_outer_max is not None:
        where.append("p.d_outer <= %s")
        params.append(d_outer_max)
    if seal_type:
        where.append("p.seal_type = %s")
        params.append(seal_type)
    if has_stock is True:
        where.append("p.stock > 0")
    elif has_stock is False:
        where.append("p.stock = 0")
    if is_active is not None:
        where.append("p.is_active = %s")
        params.append(is_active)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    cur = conn.cursor()
    try:
        # Count total (without pagination) for the response metadata.
        cur.execute(
            f"""
            SELECT COUNT(*) FROM products p
            LEFT JOIN brands b ON b.id = p.brand_id
            LEFT JOIN categories c ON c.id = p.category_id
            {where_sql}
            """,
            params,
        )
        total = cur.fetchone()[0]

        cols = ", ".join(_LIST_COLUMNS)
        cur.execute(
            f"""
            SELECT {cols} FROM products p
            LEFT JOIN brands b ON b.id = p.brand_id
            LEFT JOIN categories c ON c.id = p.category_id
            {where_sql}
            ORDER BY p.id ASC
            LIMIT %s OFFSET %s
            """,
            params + [limit, offset],
        )
        rows = cur.fetchall()
    finally:
        cur.close()

    items = [_row_to_list_item(r) for r in rows]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def _row_to_list_item(r) -> dict:
    return {
        "id": r[0],
        "code": r[1],
        "name": r[2],
        "brand": ({"id": r[3], "name": r[4], "slug": r[5]} if r[3] else None),
        "category": ({"id": r[6], "name": r[7], "slug": r[8]} if r[6] else None),
        "d": _to_float(r[9]),
        "d_outer": _to_float(r[10]),
        "b_width": _to_float(r[11]),
        "price_new": _to_float(r[12]),
        "stock": r[13],
        "is_active": r[14],
    }


def _to_float(v):
    """numeric -> float for JSON serialization."""
    return float(v) if v is not None else None
```

- [ ] **Step 4: Run tests to verify they pass**

```
python -m pytest tests/test_catalog_v1_service.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```
git add backend/services/catalog_v1_service.py backend/tests/test_catalog_v1_service.py
git commit -m "feat(catalog): list_products with filters and pagination"
```

---

## Task 4: Catalog service — get_product, brands, categories, update_stock

**Files:**
- Modify: `backend/services/catalog_v1_service.py`
- Modify: `backend/tests/test_catalog_v1_service.py`

- [ ] **Step 1: Append the failing tests**

Append to `backend/tests/test_catalog_v1_service.py`:

```python
from services.catalog_v1_service import (
    get_product, list_brands, list_categories, update_stock,
)


def test_get_product_returns_all_specs(db_conn):
    _apply_all_migrations(db_conn)
    _seed(db_conn, brands=_brands(), categories=_categories(), products=[
        {"id": 1, "code": "604", "name": "P604", "brand_id": 1, "category_id": 2},
    ])
    # add specs directly
    cur = db_conn.cursor()
    cur.execute(
        "UPDATE products SET rs_min=0.2, static_load=0.36, dynamic_load=0.97, "
        "rpm_oil=63000, seal_type='Открытый', application='{\"Универсальное\"}' "
        "WHERE id=1"
    )
    cur.close()
    p = get_product(db_conn, 1)
    assert p["id"] == 1
    assert p["rs_min"] == 0.2
    assert p["static_load"] == 0.36
    assert p["rpm_oil"] == 63000
    assert p["seal_type"] == "Открытый"
    assert p["application"] == ["Универсальное"]
    assert p["brand"]["name"] == "KYK"


def test_get_product_returns_none_for_missing(db_conn):
    _apply_all_migrations(db_conn)
    assert get_product(db_conn, 99999) is None


def test_list_brands(db_conn):
    _apply_all_migrations(db_conn)
    _seed(db_conn, brands=_brands(), categories=[], products=[])
    result = list_brands(db_conn)
    assert len(result) == 2
    assert result[0]["slug"] in ("kyk", "fkd")


def test_list_categories_includes_parent(db_conn):
    _apply_all_migrations(db_conn)
    _seed(db_conn, brands=[], categories=_categories(), products=[])
    result = list_categories(db_conn)
    assert len(result) == 2
    mini = next(c for c in result if c["slug"] == "mini")
    assert mini["parent_id"] == 1


def test_update_stock_changes_fields(db_conn):
    _apply_all_migrations(db_conn)
    _seed(db_conn, brands=_brands(), categories=[], products=[
        {"id": 1, "code": "604", "name": "P604", "brand_id": 1, "stock": 0},
    ])
    updated = update_stock(db_conn, 1, stock=42, price_new=350.00)
    assert updated is True
    cur = db_conn.cursor()
    cur.execute("SELECT stock, price_new FROM products WHERE id=1")
    stock, price = cur.fetchone()
    cur.close()
    assert stock == 42
    assert float(price) == 350.00


def test_update_stock_missing_returns_false(db_conn):
    _apply_all_migrations(db_conn)
    assert update_stock(db_conn, 99999, stock=1) is False
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m pytest tests/test_catalog_v1_service.py -v
```
Expected: 6 new tests FAIL with `ImportError: cannot import name 'get_product' ...`.

- [ ] **Step 3: Implement the remaining service functions**

Append to `backend/services/catalog_v1_service.py`:

```python
# Full column set for the product card (includes all specs).
_PRODUCT_COLUMNS = (
    "p.id", "p.code", "p.name", "p.weight",
    "p.d", "p.d_outer", "p.b_width", "p.rs_min",
    "p.static_load", "p.dynamic_load",
    "p.rpm_oil", "p.rpm_grease", "p.seal_type",
    "p.price_old", "p.price_new", "p.stock", "p.is_active",
    "p.application", "p.img",
    "p.created_at", "p.updated_at",
    "b.id", "b.name", "b.slug",
    "c.id", "c.name", "c.slug",
)


def get_product(conn, product_id: int) -> Optional[dict]:
    """Return the full product card, or None if not found."""
    cur = conn.cursor()
    try:
        cols = ", ".join(_PRODUCT_COLUMNS)
        cur.execute(
            f"""
            SELECT {cols} FROM products p
            LEFT JOIN brands b ON b.id = p.brand_id
            LEFT JOIN categories c ON c.id = p.category_id
            WHERE p.id = %s
            """,
            (product_id,),
        )
        r = cur.fetchone()
    finally:
        cur.close()
    if r is None:
        return None
    return {
        "id": r[0], "code": r[1], "name": r[2], "weight": _to_float(r[3]),
        "d": _to_float(r[4]), "d_outer": _to_float(r[5]), "b_width": _to_float(r[6]),
        "rs_min": _to_float(r[7]), "static_load": _to_float(r[8]),
        "dynamic_load": _to_float(r[9]),
        "rpm_oil": r[10], "rpm_grease": r[11], "seal_type": r[12],
        "price_old": _to_float(r[13]), "price_new": _to_float(r[14]),
        "stock": r[15], "is_active": r[16],
        "application": list(r[17]) if r[17] else [],
        "img": r[18],
        "created_at": r[19].isoformat() if r[19] else None,
        "updated_at": r[20].isoformat() if r[20] else None,
        "brand": ({"id": r[21], "name": r[22], "slug": r[23]} if r[21] else None),
        "category": ({"id": r[24], "name": r[25], "slug": r[26]} if r[24] else None),
    }


def list_brands(conn) -> list:
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, name, slug FROM brands ORDER BY name")
        rows = cur.fetchall()
    finally:
        cur.close()
    return [{"id": r[0], "name": r[1], "slug": r[2]} for r in rows]


def list_categories(conn) -> list:
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, name, slug, title, parent_id FROM categories ORDER BY name"
        )
        rows = cur.fetchall()
    finally:
        cur.close()
    return [
        {"id": r[0], "name": r[1], "slug": r[2], "title": r[3], "parent_id": r[4]}
        for r in rows
    ]


def update_stock(
    conn,
    product_id: int,
    *,
    stock: Optional[int] = None,
    price_old: Optional[float] = None,
    price_new: Optional[float] = None,
) -> bool:
    """Update stock/price for a product. Returns True if a row was updated."""
    sets = []
    params: list[Any] = []
    if stock is not None:
        sets.append("stock = %s")
        params.append(int(stock))
    if price_old is not None:
        sets.append("price_old = %s")
        params.append(price_old)
    if price_new is not None:
        sets.append("price_new = %s")
        params.append(price_new)
    if not sets:
        return False
    sets.append("updated_at = now()")
    params.append(product_id)

    cur = conn.cursor()
    try:
        cur.execute(
            f"UPDATE products SET {', '.join(sets)} WHERE id = %s",
            params,
        )
        affected = cur.rowcount
        conn.commit()
    finally:
        cur.close()
    return affected > 0
```

- [ ] **Step 4: Run tests to verify they pass**

```
python -m pytest tests/test_catalog_v1_service.py -v
```
Expected: 12 passed (6 from Task 3 + 6 new).

- [ ] **Step 5: Commit**

```
git add backend/services/catalog_v1_service.py backend/tests/test_catalog_v1_service.py
git commit -m "feat(catalog): get_product, list_brands/categories, update_stock"
```

---

## Task 5: API v1 router — public read endpoints

**Files:**
- Create: `backend/routes/catalog_v1.py`
- Modify: `backend/routes/index.py`
- Test: `backend/tests/test_catalog_v1_routes.py`

- [ ] **Step 1: Write the failing route tests**

Create `backend/tests/test_catalog_v1_routes.py`:

```python
"""Tests for /api/v1/* catalog routes via FastAPI TestClient."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from migrations.runner import (
    apply_migration_001, apply_migration_002, apply_migration_003,
)
from routes.catalog_v1 import router
from db import get_db


def _make_app():
    app = FastAPI()
    app.include_router(router)
    return app


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


def test_get_products_list(db_conn):
    _apply_all_migrations(db_conn)
    _seed(db_conn)
    app = _make_app()
    client = TestClient(app)
    resp = client.get("/api/v1/products")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert body["items"][0]["code"] == "604"


def test_get_product_by_id(db_conn):
    _apply_all_migrations(db_conn)
    _seed(db_conn)
    app = _make_app()
    client = TestClient(app)
    resp = client.get("/api/v1/products/1")
    assert resp.status_code == 200
    assert resp.json()["code"] == "604"


def test_get_product_missing_returns_404(db_conn):
    _apply_all_migrations(db_conn)
    app = _make_app()
    client = TestClient(app)
    resp = client.get("/api/v1/products/99999")
    assert resp.status_code == 404


def test_get_brands(db_conn):
    _apply_all_migrations(db_conn)
    _seed(db_conn)
    app = _make_app()
    client = TestClient(app)
    resp = client.get("/api/v1/brands")
    assert resp.status_code == 200
    assert any(b["slug"] == "kyk" for b in resp.json())


def test_get_categories(db_conn):
    _apply_all_migrations(db_conn)
    _seed(db_conn)
    app = _make_app()
    client = TestClient(app)
    resp = client.get("/api/v1/categories")
    assert resp.status_code == 200
    assert any(c["slug"] == "bearings" for c in resp.json())


def test_filter_by_brand(db_conn):
    _apply_all_migrations(db_conn)
    _seed(db_conn)
    app = _make_app()
    client = TestClient(app)
    resp = client.get("/api/v1/products", params={"brand": "kyk"})
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m pytest tests/test_catalog_v1_routes.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'routes.catalog_v1'`.

- [ ] **Step 3: Implement the router**

Create `backend/routes/catalog_v1.py`:

```python
"""Catalog v1 API router — public read endpoints + B2B-token stock update.

Reads from the unified catalog (brands/categories/products), NOT from the
legacy sku_catalog. Sites migrate to these endpoints incrementally.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from auth import verify_b2b_token
from db import get_db
from services.catalog_v1_service import (
    list_products, get_product, list_brands, list_categories, update_stock,
)

logger = logging.getLogger("HHB_B2B")

router = APIRouter(prefix="/api/v1", tags=["catalog-v1"])


@router.get("/products")
def products_list(
    brand: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    d_min: Optional[float] = Query(None),
    d_max: Optional[float] = Query(None),
    d_outer_min: Optional[float] = Query(None),
    d_outer_max: Optional[float] = Query(None),
    seal_type: Optional[str] = Query(None),
    has_stock: Optional[bool] = Query(None),
    is_active: Optional[bool] = Query(True),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    conn = get_db()
    try:
        return list_products(
            conn,
            brand=brand, category=category, search=search,
            d_min=d_min, d_max=d_max,
            d_outer_min=d_outer_min, d_outer_max=d_outer_max,
            seal_type=seal_type, has_stock=has_stock, is_active=is_active,
            limit=limit, offset=offset,
        )
    finally:
        conn.close()


@router.get("/products/{product_id}")
def product_card(product_id: int):
    conn = get_db()
    try:
        p = get_product(conn, product_id)
    finally:
        conn.close()
    if p is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return p


@router.get("/brands")
def brands_list():
    conn = get_db()
    try:
        return list_brands(conn)
    finally:
        conn.close()


@router.get("/categories")
def categories_list():
    conn = get_db()
    try:
        return list_categories(conn)
    finally:
        conn.close()


class StockUpdate(BaseModel):
    stock: Optional[int] = None
    price_old: Optional[float] = None
    price_new: Optional[float] = None


@router.post("/products/{product_id}/stock")
def product_stock_update(
    product_id: int,
    payload: StockUpdate,
    _auth=Depends(verify_b2b_token),
):
    conn = get_db()
    try:
        ok = update_stock(
            conn, product_id,
            stock=payload.stock, price_old=payload.price_old, price_new=payload.price_new,
        )
    finally:
        conn.close()
    if not ok:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"status": "ok", "product_id": product_id}
```

- [ ] **Step 4: Register the router in routes/index.py**

In `backend/routes/index.py`, inside `register_routes(app)`, add (e.g. right after the `catalog_skus_router` include):

```python
    from routes.catalog_v1 import router as catalog_v1_router
    app.include_router(catalog_v1_router)
```

- [ ] **Step 5: Run tests to verify they pass**

```
python -m pytest tests/test_catalog_v1_routes.py -v
```
Expected: 6 passed.

- [ ] **Step 6: Commit**

```
git add backend/routes/catalog_v1.py backend/routes/index.py backend/tests/test_catalog_v1_routes.py
git commit -m "feat(catalog): /api/v1 routes — products, brands, categories, stock"
```

---

## Task 6: Stock-update auth test

**Files:**
- Modify: `backend/tests/test_catalog_v1_routes.py`

The Task 5 tests covered public reads. Now add the auth-gate tests for the write endpoint.

- [ ] **Step 1: Append the failing tests**

Append to `backend/tests/test_catalog_v1_routes.py`:

```python
import os


def _set_b2b_token(token: str):
    """Force the B2B token used by auth.verify_b2b_token."""
    os.environ["B2B_ADMIN_TOKEN"] = token


def test_stock_update_without_token_returns_401(db_conn):
    _apply_all_migrations(db_conn)
    _seed(db_conn)
    _set_b2b_token("secret_xyz")
    app = _make_app()
    client = TestClient(app)
    resp = client.post("/api/v1/products/1/stock", json={"stock": 5})
    assert resp.status_code == 401


def test_stock_update_with_wrong_token_returns_401(db_conn):
    _apply_all_migrations(db_conn)
    _seed(db_conn)
    _set_b2b_token("secret_xyz")
    app = _make_app()
    client = TestClient(app)
    resp = client.post(
        "/api/v1/products/1/stock",
        json={"stock": 5},
        headers={"Authorization": "Bearer wrong"},
    )
    assert resp.status_code == 401


def test_stock_update_with_correct_token_works(db_conn):
    _apply_all_migrations(db_conn)
    _seed(db_conn)
    _set_b2b_token("secret_xyz")
    app = _make_app()
    client = TestClient(app)
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


def test_stock_update_missing_product_returns_404(db_conn):
    _apply_all_migrations(db_conn)
    _set_b2b_token("secret_xyz")
    app = _make_app()
    client = TestClient(app)
    resp = client.post(
        "/api/v1/products/99999/stock",
        json={"stock": 1},
        headers={"Authorization": "Bearer secret_xyz"},
    )
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they pass**

```
python -m pytest tests/test_catalog_v1_routes.py -v
```
Expected: 10 passed (6 from Task 5 + 4 new). The new tests pass immediately because Task 5 already wired `verify_b2b_token` into the route; these are coverage tests.

- [ ] **Step 3: Commit**

```
git add backend/tests/test_catalog_v1_routes.py
git commit -m "test(catalog): auth gate on stock-update endpoint (401/200/404)"
```

---

## Task 7: Catalog import script

**Files:**
- Create: `backend/scripts/__init__.py`
- Create: `backend/scripts/import_catalog.py`
- Test: `backend/tests/test_import_catalog.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_import_catalog.py`:

```python
"""Tests for the catalog import script.

The import reads from the local DB's sku_catalog (legacy flat table) and
writes into the unified products/brands/categories tables. We seed a small
fake sku_catalog and assert the import transforms it correctly.
"""
import os

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
            price numeric(12,2),
            stock text,
            application text[]
        )
        """
    )
    cur.execute(
        "INSERT INTO sku_catalog (sku, category, brand, d_inner, d_outer, price, stock, application) VALUES "
        "('604', 'Миниатюрные', 'KYK', 4, 12, 100, 'В наличии', '{\"Универсальное\"}'), "
        "('UCF204', 'Корпусные узлы', 'FKD', NULL, NULL, 307, 'В наличии', '{}'), "
        "('HHB-001', 'Прочие', 'HHB', 10, 30, NULL, NULL, '{}')"
    )
    # Clean unified tables so import starts fresh.
    cur.execute("DELETE FROM products")
    cur.execute("DELETE FROM brands")
    cur.execute("DELETE FROM categories")
    cur.close()
    return db_conn


def test_import_creates_brands(seeded_sku_catalog):
    conn = seeded_sku_catalog
    stats = import_from_sku_catalog(conn)
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
```

- [ ] **Step 2: Run test to verify it fails**

```
python -m pytest tests/test_import_catalog.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.import_catalog'`.

- [ ] **Step 3: Implement the import script**

Create `backend/scripts/__init__.py` (empty):
```python
```

Create `backend/scripts/import_catalog.py`:

```python
"""One-shot catalog import: legacy sku_catalog → unified products/brands/categories.

Idempotent: re-running inserts only rows that are not yet present (matched by
code+brand). Returns a stats dict: {inserted, skipped_duplicates, errors}.

This handles the LOCAL legacy sku_catalog (the 478-row table already imported
into the CRM DB from the sites server). Importing kyk.products from the remote
sites server is a separate manual step (see deploy notes) — for now we focus on
transforming what's already in the local DB.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("HHB_B2B")


def _slugify(name: str) -> str:
    """Best-effort slug for brand/category names (Cyrillic → translit-lite)."""
    # Keep it simple: lowercase, replace spaces with _, strip non-word chars.
    # For Cyrillic we keep the raw chars — sites can still use it as a key.
    return name.lower().strip().replace(" ", "_").replace("/", "_")


def _get_or_create_brand(conn, name: str) -> int:
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM brands WHERE name = %s", (name,))
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute(
            "INSERT INTO brands (name, slug) VALUES (%s, %s) RETURNING id",
            (name, _slugify(name)),
        )
        brand_id = cur.fetchone()[0]
        conn.commit()
        return brand_id
    finally:
        cur.close()


def _get_or_create_category(conn, name: str) -> int | None:
    if not name:
        return None
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM categories WHERE name = %s", (name,))
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute(
            "INSERT INTO categories (name, slug) VALUES (%s, %s) RETURNING id",
            (name, _slugify(name)),
        )
        cat_id = cur.fetchone()[0]
        conn.commit()
        return cat_id
    finally:
        cur.close()


def import_from_sku_catalog(conn) -> dict[str, Any]:
    """Transform rows from local sku_catalog into unified products.

    Returns: {"inserted": int, "skipped_duplicates": int, "errors": int}.
    """
    stats = {"inserted": 0, "skipped_duplicates": 0, "errors": 0}

    # Does sku_catalog exist locally?
    cur = conn.cursor()
    cur.execute("SELECT to_regclass('public.sku_catalog')")
    if cur.fetchone()[0] is None:
        cur.close()
        logger.warning("[import] sku_catalog not found — nothing to import.")
        return stats

    cur.execute(
        """
        SELECT sku, category, brand, d_inner, d_outer, b_width, price, stock,
               application, img
        FROM sku_catalog
        ORDER BY id
        """
    )
    rows = cur.fetchall()
    cur.close()

    for row in rows:
        sku, category, brand, d_inner, d_outer, b_width, price, stock, application, img = row
        try:
            brand_id = _get_or_create_brand(conn, brand) if brand else None
            category_id = _get_or_create_category(conn, category) if category else None

            # Skip if (code, brand_id) already present.
            cur = conn.cursor()
            cur.execute(
                "SELECT 1 FROM products WHERE code = %s AND brand_id IS NOT DISTINCT FROM %s",
                (sku, brand_id),
            )
            if cur.fetchone():
                cur.close()
                stats["skipped_duplicates"] += 1
                continue

            # Normalize stock: legacy is text ('В наличии' / NULL).
            stock_int = 0
            if stock and any(ch.isdigit() for ch in str(stock)):
                digits = "".join(ch for ch in str(stock) if ch.isdigit())
                stock_int = int(digits) if digits else 0
            elif stock and "налич" in str(stock).lower():
                stock_int = 1  # signal "in stock" without a count

            cur.execute(
                """
                INSERT INTO products
                    (code, name, brand_id, category_id,
                     d, d_outer, b_width, price_new, stock,
                     application, img)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    sku, sku, brand_id, category_id,
                    d_inner, d_outer, b_width, price, stock_int,
                    application if application else [],
                    img,
                ),
            )
            conn.commit()
            cur.close()
            stats["inserted"] += 1
        except Exception as e:
            logger.error(f"[import] failed to import sku={sku!r}: {e}")
            stats["errors"] += 1
            try:
                conn.rollback()
            except Exception:
                pass

    logger.info(
        f"[import] done: inserted={stats['inserted']} "
        f"skipped_duplicates={stats['skipped_duplicates']} errors={stats['errors']}"
    )
    return stats


if __name__ == "__main__":
    import os
    import psycopg2
    from dotenv import load_dotenv

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [import] %(levelname)s %(message)s")
    load_dotenv("/var/www/crmks/backend/.env" if os.path.isdir("/var/www/crmks") else ".env", override=True)
    dsn = os.environ["DATABASE_URL"]
    conn = psycopg2.connect(dsn)
    try:
        stats = import_from_sku_catalog(conn)
        print(stats)
    finally:
        conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

```
python -m pytest tests/test_import_catalog.py -v
```
Expected: 7 passed.

- [ ] **Step 5: Commit**

```
git add backend/scripts/ backend/tests/test_import_catalog.py
git commit -m "feat(catalog): import script sku_catalog → unified products"
```

---

## Task 8: Redis cache for brands/categories

**Files:**
- Modify: `backend/services/catalog_v1_service.py`
- Modify: `backend/tests/test_catalog_v1_service.py`

- [ ] **Step 1: Append the failing test**

Append to `backend/tests/test_catalog_v1_service.py`:

```python
import pytest

from services.catalog_v1_service import (
    invalidate_brand_cache, invalidate_product_cache,
)


class _FakeRedis:
    """In-memory stand-in for redis. Tracks deleted keys."""
    def __init__(self):
        self.deleted = []
    def delete(self, *keys):
        self.deleted.extend(keys)
        return len(keys)


@pytest.fixture
def free_fake_redis():
    return _FakeRedis()


def test_invalidate_brand_cache(free_fake_redis):
    invalidate_brand_cache(free_fake_redis)
    assert "crm:catalog:brands" in free_fake_redis.deleted


def test_invalidate_product_cache(free_fake_redis):
    invalidate_product_cache(free_fake_redis, 42)
    assert "crm:catalog:product:42" in free_fake_redis.deleted
```

- [ ] **Step 2: Run test to verify it fails**

```
python -m pytest tests/test_catalog_v1_service.py::test_invalidate_brand_cache -v
```
Expected: FAIL with `ImportError: cannot import name 'invalidate_brand_cache'`.

- [ ] **Step 3: Implement cache invalidation helpers**

Append to `backend/services/catalog_v1_service.py`:

```python
# --- Cache helpers (Redis). Reads use caching in Task 8b below; for now
# we expose invalidation so the stock-update path can clear stale entries.

CACHE_KEY_BRANDS = "crm:catalog:brands"
CACHE_KEY_CATEGORIES = "crm:catalog:categories"


def _cache_key_product(product_id: int) -> str:
    return f"crm:catalog:product:{product_id}"


def invalidate_brand_cache(redis_client) -> None:
    """Clear the brands list cache."""
    try:
        redis_client.delete(CACHE_KEY_BRANDS)
    except Exception as e:
        logger.warning(f"[cache] brand invalidate failed: {e}")


def invalidate_category_cache(redis_client) -> None:
    try:
        redis_client.delete(CACHE_KEY_CATEGORIES)
    except Exception as e:
        logger.warning(f"[cache] category invalidate failed: {e}")


def invalidate_product_cache(redis_client, product_id: int) -> None:
    """Clear a single product card cache."""
    try:
        redis_client.delete(_cache_key_product(product_id))
    except Exception as e:
        logger.warning(f"[cache] product {product_id} invalidate failed: {e}")
```

- [ ] **Step 4: Run tests to verify they pass**

```
python -m pytest tests/test_catalog_v1_service.py -v
```
Expected: all (including 2 new cache tests) pass.

- [ ] **Step 5: Wire invalidation into update_stock**

Modify `update_stock` in `backend/services/catalog_v1_service.py` — extend signature to accept an optional redis client and invalidate the product cache after a successful update:

```python
def update_stock(
    conn,
    product_id: int,
    *,
    stock: Optional[int] = None,
    price_old: Optional[float] = None,
    price_new: Optional[float] = None,
    redis_client=None,
) -> bool:
    """Update stock/price for a product. Returns True if a row was updated.

    If redis_client is provided, invalidates the product's card cache.
    """
    sets = []
    params: list[Any] = []
    if stock is not None:
        sets.append("stock = %s")
        params.append(int(stock))
    if price_old is not None:
        sets.append("price_old = %s")
        params.append(price_old)
    if price_new is not None:
        sets.append("price_new = %s")
        params.append(price_new)
    if not sets:
        return False
    sets.append("updated_at = now()")
    params.append(product_id)

    cur = conn.cursor()
    try:
        cur.execute(
            f"UPDATE products SET {', '.join(sets)} WHERE id = %s",
            params,
        )
        affected = cur.rowcount
        conn.commit()
    finally:
        cur.close()

    if affected > 0 and redis_client is not None:
        invalidate_product_cache(redis_client, product_id)
    return affected > 0
```

- [ ] **Step 6: Run all catalog tests**

```
python -m pytest tests/test_catalog_v1_service.py tests/test_catalog_v1_routes.py -v
```
Expected: all pass. (Existing update_stock tests still pass because redis_client defaults to None.)

- [ ] **Step 7: Commit**

```
git add backend/services/catalog_v1_service.py backend/tests/test_catalog_v1_service.py
git commit -m "feat(catalog): Redis cache invalidation helpers, wired into update_stock"
```

---

## Task 9: Full-suite verification

- [ ] **Step 1: Run the complete test suite**

```
cd backend
python -m pytest -v
```
Expected: all tests pass — watchdog (23) + migration 003 (4) + service (14) + routes (10) + import (7) ≈ 58.

- [ ] **Step 2: Manual API smoke on local server**

Start the API locally and curl the new endpoints:

```
python -c "import uvicorn; uvicorn main:app"
```

In another terminal (after migrating + importing data locally):

```
curl -s http://127.0.0.1:8000/api/v1/brands | head -c 200
curl -s "http://127.0.0.1:8000/api/v1/products?limit=5" | head -c 400
curl -s http://127.0.0.1:8000/api/v1/products/1 | head -c 400
curl -s -X POST http://127.0.0.1:8000/api/v1/products/1/stock -H "Authorization: Bearer wrong" -d '{"stock":1}'
# expect 401
```

- [ ] **Step 3: Final commit if any cleanup**

```
git status
# if clean — done
```

---

## Done criteria

- [ ] All pytest tests pass (~58 total)
- [ ] Migration 003 applied to local dev DB without error
- [ ] `import_from_sku_catalog` runs and transforms rows
- [ ] `/api/v1/products`, `/products/{id}`, `/brands`, `/categories` return 200
- [ ] `/api/v1/products/{id}/stock` returns 401 without token, 200 with token, 404 for missing product
- [ ] No regressions in the existing watchdog tests

## Out of scope (handled later)

- Importing kyk.products (735 rows, full specs) from the remote sites server — separate manual step.
- Refactoring csbrg/kyk/hhb sites to consume `/api/v1` — separate task.
- 1С integration (the writer of stock/price) — separate task.
- Removing the legacy `sku_catalog` table — only after all sites migrated.
