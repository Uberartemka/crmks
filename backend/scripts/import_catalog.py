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
    """Best-effort slug: lowercase, spaces→_, slashes→_."""
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
    stats: dict[str, Any] = {"inserted": 0, "skipped_duplicates": 0, "errors": 0}

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

            # Normalize stock: legacy is text ('В наличии' / NULL / '5').
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
