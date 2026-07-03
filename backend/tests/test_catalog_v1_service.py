"""Tests for catalog_v1_service.list_products."""
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


def test_update_stock_invalidates_product_cache(db_conn, free_fake_redis):
    _apply_all_migrations(db_conn)
    _seed(db_conn, brands=_brands(), categories=[], products=[
        {"id": 1, "code": "604", "name": "P604", "brand_id": 1, "stock": 0},
    ])
    update_stock(db_conn, 1, stock=5, redis_client=free_fake_redis)
    assert "crm:catalog:product:1" in free_fake_redis.deleted


def test_update_stock_no_redis_client_works(db_conn):
    _apply_all_migrations(db_conn)
    _seed(db_conn, brands=_brands(), categories=[], products=[
        {"id": 1, "code": "604", "name": "P604", "brand_id": 1, "stock": 0},
    ])
    # redis_client defaults to None — must not raise.
    ok = update_stock(db_conn, 1, stock=5)
    assert ok is True
