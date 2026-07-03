"""One-shot import: kyk.products (from sites server) → unified products.

Reads from a staging table `kyk_products_import` that must be loaded into the
local CRM DB beforehand (see deploy/import_kyk_products.sh). For each row:

- If a product matching (code, brand_id) exists → ENRICH: fill only the NULL
  characteristic/price/stock fields from the source (COALESCE — receiver wins,
  non-NULL fields are never overwritten).
- Otherwise → INSERT a new product carrying all fields from the source.

Brand and category lookup are CASE-INSENSITIVE (LOWER(name)) so that a source
brand 'Kyk' resolves to a pre-existing 'KYK' instead of creating a duplicate.
`created_at`/`updated_at` arrive as Unix seconds (bigint) and are converted via
to_timestamp().

Idempotent: re-running inserts nothing new (existing rows are re-enriched with
no-op COALESCE). Returns stats: {"inserted", "enriched", "errors"}.

Pricing model: price_new/price_old are carried 1:1. A future retail/wholesale
scheme is out of scope here (tracked with the multitenancy work).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("HHB_B2B")

# Fields enriched on existing rows via COALESCE(products.<f>, source.<f>):
# geometry + bearing specs + price + stock. Name/category/is_active are NOT
# touched on existing rows (we only enrich technical characteristics).
_ENRICH_FIELDS = [
    "weight", "d", "d_outer", "b_width",
    "rs_min", "static_load", "dynamic_load", "rpm_oil", "rpm_grease", "seal_type",
    "price_old", "price_new", "stock",
]


def _slugify(name: str) -> str:
    """Best-effort slug: lowercase, spaces→_, slashes→_."""
    return name.lower().strip().replace(" ", "_").replace("/", "_")


def _get_or_create_brand_ci(conn, name: str) -> int | None:
    """Case-insensitive get-or-create for brands. 'Kyk' matches 'KYK'."""
    if not name:
        return None
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM brands WHERE LOWER(name) = LOWER(%s)", (name,))
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


def _get_or_create_category_ci(conn, name: str) -> int | None:
    """Case-insensitive get-or-create for categories."""
    if not name:
        return None
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM categories WHERE LOWER(name) = LOWER(%s)", (name,))
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


def import_from_kyk(conn) -> dict[str, Any]:
    """Transform rows from `kyk_products_import` staging into unified products.

    Returns: {"inserted": int, "enriched": int, "errors": int}.
    """
    stats: dict[str, Any] = {"inserted": 0, "enriched": 0, "errors": 0}

    cur = conn.cursor()
    cur.execute("SELECT to_regclass('public.kyk_products_import')")
    if cur.fetchone()[0] is None:
        cur.close()
        logger.warning("[import-kyk] kyk_products_import not found — nothing to import.")
        return stats

    cur.execute(
        """
        SELECT code, name, category, brand,
               weight, d, d_outer, b_width,
               rs_min, static_load, dynamic_load, rpm_oil, rpm_grease, seal_type,
               price_old, price_new, stock, is_active,
               created_at, updated_at
        FROM kyk_products_import
        WHERE code IS NOT NULL
        ORDER BY id
        """
    )
    rows = cur.fetchall()
    cur.close()

    for row in rows:
        (code, name, category, brand,
         weight, d, d_outer, b_width,
         rs_min, static_load, dynamic_load, rpm_oil, rpm_grease, seal_type,
         price_old, price_new, stock, is_active,
         created_at, updated_at) = row
        try:
            brand_id = _get_or_create_brand_ci(conn, brand) if brand else None
            category_id = _get_or_create_category_ci(conn, category) if category else None

            cur = conn.cursor()
            cur.execute(
                "SELECT id FROM products WHERE code = %s AND brand_id IS NOT DISTINCT FROM %s",
                (code, brand_id),
            )
            existing = cur.fetchone()

            if existing is None:
                # INSERT new product with all source fields.
                cur.execute(
                    """
                    INSERT INTO products
                        (code, name, brand_id, category_id,
                         weight, d, d_outer, b_width,
                         rs_min, static_load, dynamic_load, rpm_oil, rpm_grease, seal_type,
                         price_old, price_new, stock, is_active, application,
                         created_at, updated_at)
                    VALUES (%s,%s,%s,%s, %s,%s,%s,%s, %s,%s,%s,%s,%s,%s, %s,%s,%s,%s,%s,
                            to_timestamp(%s), to_timestamp(%s))
                    """,
                    (code, name or code, brand_id, category_id,
                     weight, d, d_outer, b_width,
                     rs_min, static_load, dynamic_load, rpm_oil, rpm_grease, seal_type,
                     price_old, price_new,
                     stock if stock is not None else 0,
                     True if is_active is None else is_active,
                     [],
                     created_at, updated_at),
                )
                conn.commit()
                cur.close()
                stats["inserted"] += 1
            else:
                # ENRICH: fill NULL characteristic/price/stock fields only.
                product_id = existing[0]
                set_clause = ", ".join(
                    f"{f} = COALESCE(products.{f}, %s)" for f in _ENRICH_FIELDS
                )
                cur.execute(
                    f"UPDATE products SET {set_clause}, updated_at = now() WHERE id = %s",
                    (weight, d, d_outer, b_width,
                     rs_min, static_load, dynamic_load, rpm_oil, rpm_grease, seal_type,
                     price_old, price_new, stock, product_id),
                )
                conn.commit()
                cur.close()
                stats["enriched"] += 1
        except Exception as e:
            logger.error(f"[import-kyk] failed to import code={code!r}: {e}")
            stats["errors"] += 1
            try:
                conn.rollback()
            except Exception:
                pass

    logger.info(
        f"[import-kyk] done: inserted={stats['inserted']} enriched={stats['enriched']} "
        f"errors={stats['errors']}"
    )
    return stats


if __name__ == "__main__":
    import os
    import psycopg2
    from dotenv import load_dotenv

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [import-kyk] %(levelname)s %(message)s")
    load_dotenv("/var/www/crmks/backend/.env" if os.path.isdir("/var/www/crmks") else ".env", override=True)
    dsn = os.environ["DATABASE_URL"]
    conn = psycopg2.connect(dsn)
    try:
        stats = import_from_kyk(conn)
        print(stats)
    finally:
        conn.close()
